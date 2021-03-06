#!/bin/bash -e

model_dir=models/keras/spelling/convnet
data_dir=data/spelling/experimental/

experiment_name=$(echo $0 | sed -r 's/.*-(exp[0-9][0-9]-..*).sh/\1/')
experiment_dir=$model_dir/$experiment_name
mkdir -p $experiment_dir

n_embed_dims=10 
n_filters=3000
filter_width=6
n_fully_connected=1
n_residual_blocks=0
n_hidden=1000

for operation in delete insert substitute transpose
do
    for n_operations in 1 2
    do
        for n_errors_per_word in 3 10
        do
            model_dest=$experiment_dir/op_${operation}_n_ops_${n_operations}_n_errors_per_word_${n_errors_per_word}
            if [ -d $model_dest ]
            then
                continue
            fi
            echo ./train_keras.py $model_dir \
                $data_dir/op-${operation}-distance-${n_operations}-errors-per-word-${n_errors_per_word}.h5 \
                $data_dir/op-${operation}-distance-${n_operations}-errors-per-word-${n_errors_per_word}.h5 \
                marked_chars \
                --target-name binary_target \
                --model-dest $model_dest \
                --n-embeddings 61 \
                --model-cfg n_embed_dims=$n_embed_dims n_filters=$n_filters filter_width=$filter_width n_fully_connected=$n_fully_connected n_residual_blocks=$n_residual_blocks n_hidden=$n_hidden patience=10 \
                --shuffle \
                --confusion-matrix \
                --classification-report \
                --class-weight-auto \
                --class-weight-exponent 3 \
                --early-stopping-metric val_f2 \
                --checkpoint-metric val_f2 \
                --verbose \
                --log
            break
        done
    done
done | parallel --gnu -j 2
