#!/bin/bash -e

model_dir=models/keras/spelling/convnet
data_dir=data/spelling/experimental/old/
distance=1
errors=3

experiment_name=$(echo $0 | sed -r 's/.*-(exp[0-9][0-9]-..*).sh/\1/')
experiment_dir=$model_dir/$experiment_name
mkdir -p $experiment_dir

for operation in delete
do
    for n_embed_dims in 10 30 100
    do
        for n_filters in 100 200 300 
        do
            for filter_width in 2 4 6 8
            do
                for n_fully_connected in 1
                do
                    for n_residual_blocks in 0
                    do
                        for n_hidden in 100 200 300
                        do
                            model_dest=$experiment_dir/op_${operation}_n_embed_dims_${n_embed_dims}_n_filters_${n_filters}_filter_width_${filter_width}_n_fully_connected_${n_fully_connected}_n_residual_blocks_${n_residual_blocks}_n_hidden_${n_hidden} 
                            if [ -d $model_dest ]
                            then
                                continue
                            fi
                            echo ./train_keras.py $model_dir \
                                $data_dir/$operation-${errors}errors1word-distance-$distance${nonce}.h5 \
                                $data_dir/$operation-${errors}errors1word-distance-$distance${nonce}.h5 \
                                word \
                                --target-name target \
                                --model-dest $model_dest \
                                --n-embeddings 61 \
                                --model-cfg n_embed_dims=$n_embed_dims n_filters=$n_filters filter_width=$filter_width n_fully_connected=${n_fully_connected} n_residual_blocks=$n_residual_blocks n_hidden=$n_hidden patience=5 \
                                --shuffle \
                                --confusion-matrix \
                                --classification-report \
                                --class-weight-auto \
                                --class-weight-exponent 3 \
                                --early-stopping-metric f2 \
                                --verbose \
                                --log
                        done
                    done
                done
            done
        done
    done
done | parallel --gnu -j 2
