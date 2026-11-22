# Chi phí lập chỉ mục, bộ nhớ và đánh giá chất lượng kết quả

Tìm kiếm ngữ nghĩa dùng vector embedding để biểu diễn ý nghĩa của nội dung. Elasticsearch lưu vector, xây cấu trúc tìm kiếm gần đúng và so sánh vector truy vấn với vector tài liệu. Cách làm này mở ra khả năng tìm nội dung tương đồng về ý nghĩa, kể cả khi người dùng không dùng đúng từ khóa trong tài liệu. Tuy nhiên, semantic search tạo ra chi phí mới: phải sinh embedding, lưu nhiều số trên mỗi document, xây vector index, duy trì cấu trúc HNSW, cấp bộ nhớ và đánh giá chất lượng retrieval.

Một hệ thống semantic search tốt không chỉ trả về kết quả nhanh. Nó phải tìm đúng nội dung, giữ được quyền truy cập, xử lý dữ liệu mới với chi phí chấp nhận được và có thể đánh giá chất lượng bằng tập truy vấn đại diện. Vì vậy cần đo song song:

- Chi phí tạo embedding và cập nhật vector.
- Dung lượng vector, metadata, source và replica.
- CPU, heap, native memory, page cache và disk.
- Thời gian indexing, refresh, merge và reindex.
- Search latency, throughput và khả năng mở rộng.
- Relevance: kết quả top-k có thực sự hữu ích hay không.
- Recall sau khi áp dụng filter quyền truy cập và điều kiện nghiệp vụ.

Trong Spring Data Elasticsearch, ứng dụng thường chịu thêm chi phí gọi embedding model, batching, serialization, mapping và retry. Elasticsearch chịu chi phí lưu trữ và tìm kiếm vector. Cần đánh giá toàn bộ pipeline từ nội dung nguồn đến kết quả API.

## 1. Vòng đời của một vector document

Một luồng semantic search điển hình:

    Nội dung nguồn
         |
         v
    Làm sạch / chuẩn hóa
         |
         v
    Chia đoạn (chunking)
         |
         v
    Embedding model
         |
         v
    Vector + metadata + source
         |
         v
    Elasticsearch indexing
         |
         v
    Vector index / HNSW
         |
         v
    Query embedding
         |
         v
    kNN retrieval + filters
         |
         v
    Rerank / business rules
         |
         v
    Kết quả cho người dùng

Mỗi bước có chi phí riêng. Nếu model embedding chậm, tăng số node Elasticsearch không giải quyết được bottleneck tạo vector. Nếu vector index tốn nhiều RAM hoặc disk, tối ưu prompt/query không giải quyết được capacity. Nếu kết quả không liên quan, tăng num_candidates có thể cải thiện recall nhưng không sửa được embedding model hoặc dữ liệu chunk kém.

## 2. Chi phí tạo embedding

Embedding model chuyển văn bản thành một vector gồm nhiều chiều số. Ví dụ model có 768 dimensions tạo một vector chứa 768 giá trị cho mỗi chunk.

Chi phí embedding phụ thuộc:

- Model và số parameters.
- Số token đầu vào.
- Số chunk cần xử lý.
- Batch size.
- CPU/GPU hoặc dịch vụ embedding bên ngoài.
- Throughput và concurrency.
- Chiều dài văn bản.
- Số lần phải tạo lại embedding khi nội dung hoặc model thay đổi.

Nếu dùng dịch vụ tính phí theo token, chi phí thường tăng theo tổng token được gửi. Nếu tự host model, chi phí chuyển thành GPU/CPU, RAM/VRAM, vận hành và độ trễ.

Không chỉ đo thời gian trung bình cho một câu. Hãy đo token/giây, documents/giây, p95 latency, chi phí trên một triệu token hoặc một triệu chunk và tỷ lệ lỗi.

## 3. Chunking ảnh hưởng trực tiếp đến chi phí

Một document dài thường được chia thành nhiều chunk trước khi tạo embedding. Nếu một tài liệu được chia thành 20 chunk, ứng dụng phải tạo và lưu 20 vector thay vì một vector.

Chunk nhỏ:

- Tăng số vector.
- Tăng chi phí embedding và storage.
- Có thể tăng độ chính xác vị trí nội dung liên quan.
- Có thể làm mất ngữ cảnh nếu chunk quá ngắn.

Chunk lớn:

- Giảm số vector.
- Tăng token mỗi embedding.
- Có thể trộn nhiều chủ đề trong một vector.
- Kết quả trả về ít chính xác về đoạn cụ thể.

Ví dụ, tài liệu 20.000 token được chia thành chunk 500 token với overlap 50 token sẽ tạo khoảng 45 chunk nếu tính gần đúng. Nếu giảm chunk xuống 200 token và overlap 40, số chunk tăng đáng kể. Mỗi chunk thêm một vector, metadata và graph entry.

Chọn chunk size và overlap bằng thử nghiệm trên truy vấn thực tế. Đừng chọn chỉ theo giới hạn token tối đa của model.

## 4. Ước lượng số vector

Nếu mỗi tài liệu tạo trung bình C chunk và có D tài liệu, số vector xấp xỉ:

    vector_count = document_count * average_chunks_per_document

Ví dụ:

| Tài liệu | Chunk trung bình | Vector |
|---:|---:|---:|
| 100.000 | 4 | 400.000 |
| 1.000.000 | 8 | 8.000.000 |
| 5.000.000 | 12 | 60.000.000 |

Vector count có thể lớn hơn document count rất nhiều. Khi capacity planning, cần dựa trên số chunk thực tế, không chỉ số record trong database.

Ngoài chunk hiện tại, hãy tính:

- Vector của bản nội dung cũ còn tồn tại trước khi cleanup.
- Bản index mới trong quá trình reindex.
- Replica shard copies.
- Vector của nhiều ngôn ngữ hoặc nhiều model nếu lưu song song.
- Vector query hoặc cache ở ứng dụng nếu có.

## 5. Kích thước vector thô

Với vector float32, mỗi dimension thường chiếm 4 bytes. Dung lượng vector thô gần đúng:

    raw_vector_bytes = vector_count * dimensions * 4

Ví dụ với 1 triệu vector, mỗi vector 768 chiều:

    1,000,000 * 768 * 4
      = 3,072,000,000 bytes
      ~= 3.07 GB
      ~= 2.86 GiB

Với 10 triệu vector cùng dimensions:

    10,000,000 * 768 * 4
      ~= 30.72 GB

Đây chỉ là kích thước các giá trị float32, chưa gồm HNSW graph, metadata, _source, Lucene segment overhead, doc values nếu có, translog, replica và phần dung lượng tạm thời khi merge/reindex.

Không dùng con số raw vector làm tổng disk sizing. Hãy index một sample đủ đại diện với mapping và cấu hình production, sau đó đo store size thực tế.

## 6. Dimensions ảnh hưởng đến memory và latency

Vector càng nhiều dimensions thì:

- Raw storage trên mỗi vector tăng.
- Số phép tính khoảng cách tăng.
- Chi phí truyền vector query tăng.
- Chi phí embedding có thể tăng tùy model.
- ANN phải truy cập nhiều giá trị hơn.

Ví dụ:

| Dimensions | Float32 bytes/vector |
|---:|---:|
| 128 | 512 bytes |
| 384 | 1.536 bytes |
| 768 | 3.072 bytes |
| 1.024 | 4.096 bytes |
| 1.536 | 6.144 bytes |

Giảm dimensions có thể giảm storage và chi phí tìm kiếm, nhưng có thể làm mất thông tin ngữ nghĩa và giảm relevance. Không tự cắt bớt chiều vector bằng cách lấy 384 chiều đầu của vector 768 chiều nếu model không được huấn luyện cho cách đó.

Nếu muốn dùng dimensions nhỏ hơn, chọn model hỗ trợ output dimension đó hoặc dùng một phương pháp giảm chiều được đánh giá bằng benchmark relevance.

## 7. Chunk metadata cũng chiếm dung lượng

Mỗi chunk thường cần metadata để trả kết quả có ngữ cảnh:

- documentId.
- chunkId.
- tenantId.
- ownerId.
- allowedRoles hoặc ACL.
- sourceType.
- language.
- title.
- section.
- createdAt/updatedAt.
- visibility/status.
- source text hoặc excerpt.

Vector có thể là phần lớn storage, nhưng metadata và source cũng có thể đáng kể, nhất là khi chunk lưu nguyên văn bản dài.

Nếu mỗi chunk lưu cả toàn bộ tài liệu nguồn, storage có thể bị nhân lên nhiều lần. Thường nên lưu nội dung chunk cùng reference đến tài liệu gốc, hoặc lưu source ở nơi phù hợp và chỉ giữ các field cần search/display.

Không bỏ metadata quyền truy cập để giảm vài bytes. Tenant, ACL và trạng thái visibility có thể là điều kiện bắt buộc để không làm lộ dữ liệu.

## 8. HNSW và chi phí vector index

Approximate nearest neighbor (ANN) search thường dùng cấu trúc đồ thị như HNSW. HNSW kết nối các vector thành graph nhiều tầng để tìm những vector gần query mà không cần so sánh chính xác với mọi vector trong index.

HNSW tạo thêm chi phí ngoài vector values:

- Graph links giữa các node.
- Metadata và cấu trúc segment.
- Memory/page cache để truy cập graph và vector values.
- CPU khi xây graph và tìm kiếm.
- Disk và I/O khi lưu/đọc vector index.

HNSW thường cải thiện tốc độ retrieval so với brute-force trên tập lớn, nhưng không miễn phí. Tham số graph ảnh hưởng cả indexing cost, storage và search quality.

## 9. Tham số HNSW: m

Tham số m điều khiển số lượng liên kết tối đa hoặc mục tiêu kết nối của mỗi node trong graph theo cách triển khai HNSW.

Khi tăng m:

- Graph có thể có nhiều kết nối hơn.
- Storage và memory overhead tăng.
- Indexing graph tốn thêm CPU và memory.
- Recall có thể cải thiện ở một số workload.
- Search có thể duyệt graph hiệu quả hơn trong một số trường hợp.

Khi giảm m:

- Graph nhỏ hơn.
- Indexing có thể nhẹ hơn.
- Memory/disk overhead giảm.
- Recall hoặc khả năng tìm đường trong graph có thể giảm.

Không có một giá trị m tốt nhất cho mọi dataset. Hãy benchmark với cùng dataset, query set và recall target.

## 10. Tham số ef_construction

ef_construction điều khiển mức độ tìm kiếm candidate trong lúc xây dựng graph HNSW. Giá trị cao hơn có thể tạo graph chất lượng hơn, nhưng làm indexing chậm và tốn tài nguyên hơn.

Tradeoff:

| ef_construction | Tác động thường gặp |
|---|---|
| Thấp | Build nhanh hơn, graph có thể kém kết nối hơn |
| Cao | Build tốn CPU/thời gian hơn, có thể cải thiện recall |

ef_construction là tham số build-time. Không nhầm nó với số candidate trong một query. Khi đổi tham số build, thường cần tạo/reindex vector index để graph mới được xây dựng.

## 11. num_candidates và chi phí search

Trong kNN search của Elasticsearch, num_candidates quy định số candidate được xem xét ở mỗi shard trước khi hợp nhất để lấy top-k toàn cục theo semantics của API.

Tăng num_candidates thường:

- Tăng cơ hội tìm được nearest neighbors tốt hơn.
- Có thể cải thiện recall.
- Tăng CPU và latency.
- Có thể tăng memory tạm thời và network giữa shard/coordinator.

Giảm num_candidates thường nhanh hơn nhưng có thể bỏ lỡ kết quả gần query.

Ví dụ query:

    {
      "knn": {
        "field": "embedding",
        "query_vector": [0.12, 0.31, 0.08],
        "k": 10,
        "num_candidates": 100
      }
    }

Vector trong ví dụ chỉ có ba chiều để minh họa cú pháp; model thật phải dùng đúng số dimensions đã khai báo trong mapping.

Tuning num_candidates cần cân bằng recall@k và latency p95/p99. Không chỉ tăng thật cao để tìm kết quả tốt hơn nếu chi phí vượt SLO.

## 12. Mapping dense_vector

Một mapping vector điển hình:

    PUT knowledge-chunks
    {
      "mappings": {
        "properties": {
          "chunkId": {
            "type": "keyword"
          },
          "documentId": {
            "type": "keyword"
          },
          "tenantId": {
            "type": "keyword"
          },
          "visibility": {
            "type": "keyword"
          },
          "updatedAt": {
            "type": "date"
          },
          "content": {
            "type": "text"
          },
          "embedding": {
            "type": "dense_vector",
            "dims": 768,
            "index": true,
            "similarity": "cosine",
            "index_options": {
              "type": "hnsw",
              "m": 16,
              "ef_construction": 100
            }
          }
        }
      }
    }

Đây là ví dụ minh họa. Field hỗ trợ, mặc định index, index_options, kiểu vector và giới hạn dimensions thay đổi theo Elasticsearch version. Hãy kiểm tra mapping reference đúng với cluster đang dùng.

Chỉ đặt index=true nếu cần vector search. Nếu chỉ lưu vector để lấy lại hoặc xử lý ở hệ thống khác, việc xây ANN index có thể không cần thiết, nhưng cần cân nhắc API và mapping hỗ trợ.

## 13. Chọn similarity metric đúng với model

Vector search thường dùng:

- cosine similarity.
- dot product.
- L2 distance.

Metric phải tương thích với cách model tạo vector và normalization.

Cosine đo hướng vector, thường hữu ích khi độ lớn vector không mang ý nghĩa chính.

Dot product đo tích vô hướng; với vector đã normalize, thứ hạng có thể tương quan với cosine.

L2 đo khoảng cách Euclidean; vector gần nhau có khoảng cách nhỏ.

Không đổi metric chỉ để thử tăng tốc nếu chưa hiểu semantics. Cùng một cặp vector có thể được xếp hạng khác nhau dưới metric khác.

## 14. Chuẩn hóa vector

Một số model tạo embedding đã normalize vector; một số model thì không. Nếu dùng cosine, Elasticsearch có semantics riêng cho metric. Nếu dùng dot_product, nhiều cấu hình yêu cầu vector được normalize theo giới hạn hoặc cách triển khai tương ứng.

Trước khi index:

- Đọc tài liệu model.
- Kiểm tra dimensions.
- Kiểm tra finite values, không có NaN/Infinity.
- Kiểm tra normalization nếu metric yêu cầu.
- Dùng cùng preprocessing cho document và query.

Nếu normalize document vector nhưng không normalize query vector, hoặc ngược lại, score có thể thay đổi ngoài dự kiến với metric phụ thuộc magnitude.

Không tự normalize hoặc đổi metric mà không đo relevance trên query set có nhãn.

## 15. Quantization giảm chi phí vector

Quantization biểu diễn vector bằng độ chính xác thấp hơn float32. Mục tiêu là giảm storage và memory bandwidth, đôi khi cải thiện tốc độ search.

Ví dụ các dạng thường gặp:

- int8: khoảng một byte mỗi dimension.
- int4: khoảng nửa byte mỗi dimension.
- Binary/bit quantization: khoảng một bit mỗi dimension trước overhead.

Dung lượng thực tế phụ thuộc format, metadata, alignment và cách Elasticsearch/Lucene lưu vector index. Không dùng phép tính lý thuyết làm tổng disk size.

Quantization có tradeoff:

- Ít bytes hơn.
- Có thể giảm memory pressure.
- Có thể giảm I/O.
- Có thể giảm recall hoặc thay đổi thứ hạng.
- Có thể cần oversampling và rescoring bằng vector chính xác hơn.

Chỉ chọn quantization sau khi đo cả recall và latency trên dữ liệu thực tế.

## 16. Float32, int8, int4 và binary

Ước lượng payload vector thuần:

| Representation | Bytes gần đúng mỗi dimension |
|---|---:|
| float32 | 4 |
| int8 | 1 |
| int4 | 0,5 |
| 1-bit | 0,125 |

Với 768 dimensions:

| Representation | Payload thô gần đúng |
|---|---:|
| float32 | 3.072 bytes |
| int8 | 768 bytes |
| int4 | 384 bytes |
| 1-bit | 96 bytes |

Đây không phải dự báo chính xác cho file index. HNSW graph, metadata và encoding overhead vẫn tồn tại. Một số kiểu quantization có bản vector gốc hoặc cách rescoring riêng, nên storage thực tế có thể cao hơn phép tính trên.

## 17. Oversampling và rescoring

Khi vector được quantize, hệ thống có thể tìm một tập candidate lớn hơn k, sau đó tính lại score trên representation chính xác hơn để chọn kết quả cuối.

Luồng:

    Quantized ANN search
          |
          v
    Oversampled candidates
          |
          v
    Rescore with higher precision
          |
          v
       Final top-k

Oversampling có thể cải thiện recall sau quantization nhưng làm tăng CPU và latency vì nhiều candidate phải được xử lý.

Tuning cần đo:

- Recall@k.
- p95/p99 latency.
- Số candidate sau oversampling.
- Rescore cost.
- Disk/memory footprint.

Tên tùy chọn và khả năng rescoring phụ thuộc phiên bản Elasticsearch và vector index type.

## 18. HNSW và memory footprint

Chi phí bộ nhớ của vector index không chỉ là số byte của vector. Graph links, metadata và cấu trúc đọc cũng cần tài nguyên. Một phần dữ liệu có thể được memory-map và phục vụ thông qua filesystem page cache; cách quản lý cụ thể phụ thuộc Lucene/Elasticsearch version và vector index type.

Không nên giả định toàn bộ vector index luôn nằm trong JVM heap. Cũng không nên giả định toàn bộ graph luôn nằm hoàn toàn trong RAM. Theo dõi heap, process RSS, page cache và disk I/O trong workload thực tế.

Nếu working set vector lớn hơn RAM có thể dành cho cache, search ngẫu nhiên có thể tạo nhiều disk reads và tăng tail latency.

## 19. Số shard ảnh hưởng vector search

Một kNN request trên nhiều shard có thể phải tìm candidate trên từng shard rồi hợp nhất kết quả ở coordinating node.

Nhiều shard có thể:

- Tăng song song hóa.
- Tăng số graph phải truy cập.
- Tăng request fan-out và network traffic.
- Tăng metadata và merge overhead.
- Làm candidate merge tốn thêm công việc.

Quá ít shard có thể tạo shard lớn, recovery lâu và hạn chế parallelism. Quá nhiều shard tạo overhead và fan-out.

Benchmark vector query trên đúng shard topology dự kiến. Không suy ra production latency từ một single-shard development index.

## 20. Replica và vector search

Replica tăng storage và indexing cost vì mỗi bản sao phải duy trì dữ liệu/index. Tuy nhiên, search có thể được phân phối qua primary và replica copies, tăng khả năng phục vụ query trong một số workload.

Khi chọn replica count, đo:

- Search throughput.
- p95/p99 latency.
- Indexing throughput.
- Disk usage.
- Recovery time.
- Node distribution.

Replica không làm vector values nhỏ hơn. Nó nhân số bản sao dữ liệu và có thể làm tăng chi phí build/merge/recovery.

## 21. Filter có ảnh hưởng đến vector search cost

Semantic search thường cần giới hạn kết quả theo tenant, ACL, trạng thái, ngôn ngữ, thời gian hoặc loại tài liệu.

Ví dụ điều kiện:

- Chỉ tài liệu của tenant hiện tại.
- Chỉ tài liệu public hoặc được user cấp quyền.
- Chỉ nội dung đã publish.
- Loại document đã xóa mềm.
- Chỉ ngôn ngữ người dùng hỗ trợ.
- Chỉ tài liệu còn hiệu lực.

Filter làm thay đổi tập document hợp lệ. Nếu filter chọn lọc cao, ANN search phải tìm đủ candidate trong tập nhỏ đó. Cách filter được áp dụng có thể ảnh hưởng recall và latency.

Filter bắt buộc về quyền truy cập phải được áp dụng trong chính truy vấn retrieval hoặc một lớp security enforcement đáng tin cậy. Không lấy top-k toàn index rồi chỉ lọc ở frontend.

## 22. Prefilter và post-filter trong kNN

Phân biệt hai khái niệm:

- **Pre-filter:** điều kiện lọc được áp dụng trong quá trình tìm kiếm kNN, để thuật toán tìm nearest neighbors trong tập document thỏa filter.
- **Post-filter:** tìm candidate trước rồi lọc kết quả sau. Một số candidate có thể bị loại, khiến response có ít hơn k kết quả dù còn document hợp lệ khác trong index.

Ví dụ cần 10 kết quả của tenant A:

    Top 10 toàn index
          |
          v
    Lọc tenant A
          |
          v
    Có thể chỉ còn 2 kết quả

Nếu prefilter được áp dụng đúng:

    Tập document tenant A
          |
          v
    kNN trong tập hợp lệ
          |
          v
    Top 10 tenant A nếu đủ dữ liệu

Trong Elasticsearch, kNN query có cơ chế filter gắn bên trong kNN query để thực hiện pre-filter theo semantics của API. Các filter đặt ở vị trí khác như post_filter hoặc một số wrapper query có thể có semantics khác theo phiên bản và loại kNN API.

Hãy đọc kỹ API được sử dụng và kiểm thử số lượng kết quả sau filter. Đừng giả định mọi bool filter bao quanh vector query đều có cùng semantics pre-filter.

## 23. Filter bên trong kNN query

Ví dụ kNN query có filter:

    GET knowledge-chunks/_search
    {
      "size": 10,
      "query": {
        "knn": {
          "field": "embedding",
          "query_vector": [0.12, 0.31, 0.08],
          "k": 10,
          "num_candidates": 100,
          "filter": {
            "bool": {
              "filter": [
                {
                  "term": {
                    "tenantId": "tenant-a"
                  }
                },
                {
                  "term": {
                    "visibility": "PUBLISHED"
                  }
                }
              ]
            }
          }
        }
      }
    }

Vector ví dụ có ba chiều chỉ để minh họa. Thực tế query vector phải có đúng dimensions như field mapping. API và vị trí filter cần được kiểm tra theo Elasticsearch version.

Filter trong kNN query có thể được dùng như pre-filter trong kNN query DSL. Nếu dùng top-level knn search option, API cũng có trường filter riêng theo phiên bản. Không trộn cú pháp hai API một cách tùy tiện.

## 24. Post-filter có thể trả ít hơn k kết quả

Ví dụ:

    GET knowledge-chunks/_search
    {
      "size": 10,
      "knn": {
        "field": "embedding",
        "query_vector": [0.12, 0.31, 0.08],
        "k": 10,
        "num_candidates": 100
      },
      "post_filter": {
        "term": {
          "tenantId": "tenant-a"
        }
      }
    }

Nếu top candidate toàn cục chủ yếu thuộc tenant khác, post_filter loại chúng sau retrieval. Response có thể có ít hơn 10 hits dù tenant A có nhiều document hợp lệ.

Điều này vừa ảnh hưởng trải nghiệm vừa có thể làm lộ vấn đề thiết kế nếu filter quyền chỉ được áp dụng sau retrieval. Dùng pre-filter hoặc cơ chế authorization phù hợp cho điều kiện bắt buộc.

## 25. Mandatory security filters và optional business filters

Nên tách điều kiện thành hai nhóm:

**Mandatory security filters**

- tenantId lấy từ authenticated principal.
- ACL/allowed user hoặc role.
- Document visibility.
- Data classification.
- Soft-delete exclusion.

**Optional business filters**

- Category.
- Language.
- Date range.
- Product status.
- Price range.
- Region.
- Source type.

Mandatory filters phải luôn được áp dụng, bất kể client có truyền điều kiện hay không. Optional filters có thể được kết hợp theo yêu cầu nghiệp vụ nhưng không được làm mất security boundary.

Ví dụ bool filter:

    {
      "bool": {
        "filter": [
          { "term": { "tenantId": "tenant-a" } },
          { "term": { "visibility": "PUBLISHED" } },
          { "term": { "status": "ACTIVE" } },
          { "terms": { "language": ["vi", "en"] } },
          { "range": { "publishedAt": { "lte": "now" } } }
        ]
      }
    }

Filter context không tính relevance score như query context. Điều kiện business và security thường phù hợp với filter context vì chúng quyết định eligibility, không đóng góp điểm tương đồng.

## 26. Tenant filter phải đến từ security context

Không tin tenantId do client gửi như một nguồn quyền:

    GET /search?tenantId=tenant-b

Nếu user hiện tại thuộc tenant A, backend phải xác định tenant A từ principal hoặc security context đã xác thực. Client không được tự đổi tenant để đọc dữ liệu khác.

Luồng an toàn:

1. Authenticate request.
2. Resolve tenant và user identity từ trusted principal.
3. Authorize chức năng search.
4. Tạo mandatory tenant/ACL filters ở backend.
5. Kết hợp business filters đã validate.
6. Gửi query đến Elasticsearch.
7. Map kết quả sang response DTO.

Không cho request DTO ghi đè hoặc loại bỏ mandatory filter. Nếu một endpoint hỗ trợ admin cross-tenant search, đó phải là quyền riêng được kiểm tra rõ ràng.

## 27. ACL theo user và role

Một document có thể được chia sẻ cho một số user hoặc role:

    {
      "documentId": "doc-100",
      "tenantId": "tenant-a",
      "allowedUserIds": ["user-1", "user-7"],
      "allowedRoles": ["EDITOR", "LEGAL"],
      "visibility": "RESTRICTED"
    }

Query có thể dùng terms filter:

    {
      "bool": {
        "filter": [
          { "term": { "tenantId": "tenant-a" } },
          {
            "bool": {
              "should": [
                { "terms": { "allowedUserIds": ["user-1"] } },
                { "terms": { "allowedRoles": ["EDITOR"] } },
                { "term": { "visibility": "PUBLIC" } }
              ],
              "minimum_should_match": 1
            }
          }
        ]
      }
    }

Ví dụ chỉ minh họa logic OR giữa user, role và public. Chính sách thực tế có thể cần AND/OR khác, deny rules, inheritance hoặc group membership. Hãy viết policy rõ ràng trước khi chuyển thành query DSL.

Không lấy role từ request parameter. Role phải được lấy từ principal hoặc authorization service đáng tin cậy.

## 28. Nested ACL khi cần giữ quan hệ thuộc tính

Nếu ACL có nhiều thuộc tính liên quan, nested mapping có thể cần thiết để tránh ghép sai field giữa các phần tử.

Ví dụ:

    "permissions": [
      {
        "principalType": "USER",
        "principalId": "user-1",
        "permission": "READ"
      },
      {
        "principalType": "ROLE",
        "principalId": "EDITOR",
        "permission": "WRITE"
      }
    ]

Nếu permissions là object array thông thường, Elasticsearch có thể flatten field values và một query có thể match principalId từ object này với permission từ object khác. Khi cần đảm bảo các điều kiện thuộc cùng một phần tử, mapping nested và nested query là phù hợp.

Ví dụ:

    {
      "nested": {
        "path": "permissions",
        "query": {
          "bool": {
            "filter": [
              { "term": { "permissions.principalType": "USER" } },
              { "term": { "permissions.principalId": "user-1" } },
              { "term": { "permissions.permission": "READ" } }
            ]
          }
        }
      }
    }

Nested query có chi phí cao hơn object field đơn giản và làm tăng Lucene document count. Chỉ dùng khi semantics quan hệ thực sự cần thiết.

## 29. Điều kiện nghiệp vụ trong semantic search

Ngoài quyền truy cập, kết quả thường phải thỏa điều kiện nghiệp vụ:

- Chỉ sản phẩm đang bán.
- Chỉ tài liệu đã publish.
- Không lấy nội dung hết hạn.
- Chỉ lấy khu vực user hỗ trợ.
- Chỉ lấy phiên bản hiện hành.
- Chỉ lấy ngôn ngữ phù hợp.
- Loại bản ghi soft-deleted.
- Chỉ lấy dữ liệu có inventory.

Các điều kiện này nên nằm trong filter context nếu chúng chỉ xác định document hợp lệ.

Ví dụ:

    {
      "bool": {
        "filter": [
          { "term": { "status": "ACTIVE" } },
          { "term": { "isDeleted": false } },
          { "range": { "validFrom": { "lte": "now" } } },
          {
            "bool": {
              "should": [
                { "range": { "validUntil": { "gte": "now" } } },
                { "bool": { "must_not": { "exists": { "field": "validUntil" } } } }
              ],
              "minimum_should_match": 1
            }
          }
        ]
      }
    }

Điều kiện thời gian phải được định nghĩa theo timezone và business clock thống nhất. Không để client tự truyền now hoặc timezone không được validate nếu điều đó có thể thay đổi eligibility.

## 30. Kết hợp filter với kNN retrieval

Một semantic query thực tế có thể kết hợp:

- Vector similarity.
- Tenant filter.
- ACL filter.
- Visibility/status.
- Language.
- Date range.
- Business category.

Ví dụ:

    GET knowledge-chunks/_search
    {
      "size": 10,
      "query": {
        "knn": {
          "field": "embedding",
          "query_vector": [0.12, 0.31, 0.08],
          "k": 10,
          "num_candidates": 200,
          "filter": {
            "bool": {
              "filter": [
                { "term": { "tenantId": "tenant-a" } },
                { "term": { "visibility": "PUBLISHED" } },
                { "term": { "language": "vi" } },
                { "term": { "isDeleted": false } },
                { "range": { "publishedAt": { "lte": "now" } } }
              ]
            }
          }
        }
      }
    }

Nếu ACL phức tạp, thêm nested ACL condition hoặc dùng security enforcement ở cluster. Không chỉ lọc theo tenant nếu tài liệu trong cùng tenant vẫn có quyền riêng tư.

## 31. Filter selectivity và hiệu năng

Filter selectivity là tỷ lệ document còn lại sau khi áp dụng điều kiện.

Ví dụ:

| Filter | Tỷ lệ document còn lại |
|---|---:|
| status = ACTIVE | 90% |
| language = vi | 35% |
| tenant = small tenant | 0,2% |
| user ACL | 0,01% |

Filter rất chọn lọc có thể làm tập tìm kiếm nhỏ hơn nhiều. Với một số cấu hình và phiên bản, Elasticsearch có thể chọn cách thực hiện exact search trên tập đã lọc khi phù hợp; ở những trường hợp khác ANN vẫn được dùng.

Đừng giả định filter càng chọn lọc thì latency luôn thấp hơn. Nested ACL, số lượng shard, graph traversal và candidate strategy đều ảnh hưởng.

Benchmark theo các mức selectivity:

- Tenant lớn.
- Tenant nhỏ.
- Public.
- Restricted user.
- ACL nhiều role.
- Kết hợp nhiều điều kiện business.

Đo recall và latency cho từng nhóm, không chỉ đo một filter phổ biến.

## 32. Filter làm thay đổi recall

Nếu dùng post-filter, kết quả top-k có thể bị giảm số lượng hoặc bỏ lỡ document phù hợp. Nếu dùng pre-filter, ANN search tìm trong tập đủ điều kiện, nhưng chất lượng ANN vẫn phụ thuộc graph, candidate count và selectivity.

Khi đánh giá recall, ground truth phải được tính trên tập document hợp lệ sau filter. Không so kết quả query của tenant A với nearest neighbors toàn index rồi kết luận recall thấp.

Ví dụ:

1. Lọc tập document tenant A.
2. Tính exact top-k trên vector của tập tenant A.
3. Chạy ANN với cùng filter tenant A.
4. So sánh ID kết quả.

Đây là cách đánh giá đúng hơn cho filtered vector retrieval.

## 33. Exact vector search làm ground truth

ANN là approximate search. Để đo recall, cần một baseline exact nearest neighbors trên tập dữ liệu nhỏ/đủ kiểm soát hoặc một phương pháp brute-force đáng tin cậy.

Có thể dùng script_score để tính vector similarity trên các document đã được filter:

    GET knowledge-chunks/_search
    {
      "size": 10,
      "query": {
        "script_score": {
          "query": {
            "bool": {
              "filter": [
                { "term": { "tenantId": "tenant-a" } },
                { "term": { "visibility": "PUBLISHED" } }
              ]
            }
          },
          "script": {
            "source": "cosineSimilarity(params.query_vector, 'embedding') + 1.0",
            "params": {
              "query_vector": [0.12, 0.31, 0.08]
            }
          }
        }
      }
    }

Ví dụ vector ba chiều chỉ minh họa. script_score có thể phải đánh giá mọi document thỏa filter, nên rất tốn CPU trên tập lớn. Dùng nó để tạo ground truth hoặc cho tập đủ nhỏ, không mặc định dùng cho production scale.

Metric script phải tương thích với metric model/mapping. Cộng hằng số vào cosine score trong ví dụ giúp score không âm ở một số cách dùng, nhưng không thay đổi thứ hạng giữa các document.

## 34. Recall@k

Recall@k đo bao nhiêu kết quả trong exact top-k xuất hiện trong ANN top-k.

    recall@k =
      |ANN_top_k ∩ Exact_top_k| / k

Ví dụ exact top-5:

    [A, B, C, D, E]

ANN top-5:

    [A, C, F, D, G]

Giao nhau có A, C, D nên:

    recall@5 = 3 / 5 = 0.60

Recall đo khả năng ANN tìm lại nearest neighbors theo metric vector. Nó chưa chứng minh những document đó thực sự hữu ích với người dùng; exact vector neighbors có thể vẫn sai về relevance nghiệp vụ.

## 35. Precision@k

Precision@k đo tỷ lệ kết quả top-k được đánh giá là relevant:

    precision@k =
      relevant results in top-k / k

Nếu top-5 có 4 kết quả relevant:

    precision@5 = 4 / 5 = 0.8

Precision cần relevance judgments do người đánh giá hoặc dữ liệu tương tác đáng tin cậy cung cấp. Không thể tính precision chỉ từ vector distance.

## 36. MRR

Mean Reciprocal Rank (MRR) đánh giá vị trí của kết quả relevant đầu tiên.

Với một query:

    reciprocal_rank = 1 / rank_of_first_relevant_result

Nếu kết quả relevant đầu tiên ở vị trí 2:

    RR = 1 / 2 = 0.5

MRR là trung bình reciprocal rank trên nhiều query. MRR phù hợp khi người dùng chủ yếu cần tìm thấy một kết quả đúng đầu tiên, nhưng không phản ánh đầy đủ chất lượng toàn bộ top-k.

## 37. NDCG@k

Normalized Discounted Cumulative Gain (NDCG) đánh giá thứ hạng với relevance grade nhiều mức. Kết quả relevant hơn ở vị trí cao được thưởng nhiều hơn.

DCG thường dùng:

    DCG@k = sum((2^rel_i - 1) / log2(i + 1))

    NDCG@k = DCG@k / IDCG@k

Trong đó rel_i là relevance grade tại vị trí i, IDCG là DCG lý tưởng khi sắp xếp kết quả theo relevance giảm dần.

NDCG phù hợp khi người đánh giá có thể gán mức độ như:

- 0: không liên quan.
- 1: liên quan yếu.
- 2: liên quan.
- 3: rất liên quan.

NDCG giúp so sánh ranking giữa lexical, vector và hybrid retrieval.

## 38. MAP và Hit Rate

Mean Average Precision (MAP) tổng hợp precision tại các vị trí có kết quả relevant, sau đó lấy trung bình trên query. MAP hữu ích khi có nhiều relevant documents cho mỗi query và muốn đánh giá chất lượng thứ hạng tổng thể.

Hit Rate@k đo tỷ lệ query có ít nhất một kết quả relevant trong top-k:

    hit_rate@k =
      queries with >= 1 relevant hit in top-k
      / total queries

Hit Rate dễ giải thích cho use case tìm một tài liệu hoặc sản phẩm phù hợp. Tuy nhiên, nó không cho biết có bao nhiêu kết quả relevant hoặc chúng nằm ở vị trí nào.

## 39. Đánh giá relevance khác với recall ANN

Hai câu hỏi khác nhau:

- ANN recall: vector search có tìm gần đúng những vector gần nhất theo metric không?
- Business relevance: kết quả có giải quyết đúng ý định của người dùng không?

Một hệ thống có recall@10 rất cao nhưng NDCG thấp có thể đang tìm đúng nearest vectors nhưng embedding model không biểu diễn tốt domain semantics.

Ngược lại, một reranker có thể sắp xếp top candidate tốt nhưng ANN recall thấp khiến tài liệu cần thiết không bao giờ lọt vào candidate set.

Do đó cần đánh giá cả retrieval và ranking:

1. Recall@k của ANN so với exact vector neighbors.
2. Precision/NDCG/MRR theo relevance judgments.
3. Latency và throughput.
4. Kết quả sau mandatory filters và business rules.

## 40. Tạo bộ query evaluation

Một evaluation set nên chứa truy vấn thực tế hoặc truy vấn do domain expert viết:

- Query ngắn và dài.
- Câu hỏi tự nhiên.
- Từ đồng nghĩa.
- Lỗi chính tả.
- Tên riêng.
- Câu hỏi nhiều ý.
- Truy vấn đa ngôn ngữ.
- Query không có tài liệu phù hợp.
- Query cần quyền truy cập restricted.
- Query có filter business như status/date/category.

Mỗi query nên có:

- Query text.
- User/tenant context giả lập.
- Business filters.
- Relevant document/chunk IDs.
- Relevance grade nếu dùng NDCG.
- Query family.
- Expected behavior khi không có kết quả.

Đừng chỉ dùng query dễ có từ ngữ giống hệt document. Semantic search phải được đánh giá trên paraphrase, synonyms và cách diễn đạt tự nhiên.

## 41. Tạo relevance judgments

Relevance judgments có thể được tạo bằng:

- Human annotation từ domain experts.
- Pairwise comparison.
- Search logs đã được kiểm tra và loại bias.
- Click/conversion signals có điều chỉnh position bias.
- Synthetic queries được chuyên gia xác nhận.

Không coi click là ground truth tuyệt đối. Người dùng có thể click kết quả đầu tiên vì vị trí, không phải vì nó relevant nhất.

Nên có guideline rõ ràng cho annotator:

- Tài liệu có trả lời đúng câu hỏi không?
- Có đủ thông tin không?
- Có còn hiệu lực không?
- Có đúng tenant/visibility không?
- Có liên quan trực tiếp hay chỉ cùng chủ đề?

Một tập đánh giá tốt cần được version hóa để so sánh model và mapping qua thời gian.

## 42. Train/test split cho query evaluation

Nếu dùng query logs để tuning hoặc huấn luyện reranker, cần tách tập tuning và holdout:

- Development set để phát triển query và filter.
- Validation set để chọn tham số.
- Holdout test set để đánh giá cuối.

Nếu cùng query và labels được dùng lặp đi lặp lại để tuning, kết quả có thể overfit. Một thay đổi cải thiện validation nhưng giảm holdout là dấu hiệu cần điều tra.

Với dữ liệu theo thời gian, có thể dùng time-based split để mô phỏng query mới và tài liệu mới trong tương lai.

## 43. Đánh giá theo tenant và ACL

Một điểm rất quan trọng: relevance chỉ có ý nghĩa trên tập document mà user được phép xem.

Evaluation phải mô phỏng:

- Tenant lớn và nhỏ.
- User có quyền rộng/hẹp.
- Public và restricted documents.
- User thuộc nhiều group.
- ACL thay đổi theo thời gian.
- Document bị revoke permission.

Metrics nên được tính sau khi áp dụng security filter. Một kết quả relevant nhưng user không có quyền xem phải được coi là không hợp lệ, không phải một hit tốt.

Ngoài relevance, cần có security assertions:

- Không có document từ tenant khác.
- Không có document không được ACL cho phép.
- Document đã bị revoke không xuất hiện.
- Post-filter không làm rò rỉ snippet/metadata qua response khác.

## 44. Đánh giá multilingual search

Nếu hệ thống hỗ trợ nhiều ngôn ngữ, evaluation set cần tách theo ngôn ngữ và cross-language queries:

- Query tiếng Việt, document tiếng Việt.
- Query tiếng Anh, document tiếng Anh.
- Query tiếng Việt, document tiếng Anh.
- Query có thuật ngữ kỹ thuật không dịch.
- Query chứa tên riêng hoặc mã sản phẩm.

Embedding model đa ngôn ngữ có thể xử lý cross-language retrieval nhưng chất lượng không đồng đều giữa ngôn ngữ. Đo NDCG/Recall theo từng language pair thay vì chỉ lấy trung bình toàn bộ.

Filter language có thể cải thiện precision hoặc giảm candidate space, nhưng có thể loại kết quả đúng nếu người dùng hỏi bằng một ngôn ngữ và tài liệu hữu ích ở ngôn ngữ khác.

## 45. Đánh giá chunking

Chunking ảnh hưởng retrieval unit. Nếu chunk quá nhỏ, kết quả có thể thiếu ngữ cảnh; nếu chunk quá lớn, vector có thể trộn nhiều ý.

Thử nghiệm:

- Chunk size.
- Overlap.
- Boundary theo đoạn/heading.
- Metadata title/section.
- Parent document retrieval.
- Kết quả trả chunk hay toàn document.

Metrics:

- Recall@k theo chunk ID.
- Recall theo parent document ID.
- NDCG theo relevance của chunk.
- Context completeness.
- Duplicate chunk rate.
- Index size và embedding cost.

Nếu nhiều chunk của cùng một tài liệu chiếm top-k, kết quả có thể thiếu đa dạng. Cân nhắc collapse theo document hoặc rerank để lấy các nguồn khác nhau.

## 46. Đánh giá embedding model

Khi so sánh model:

- Dùng cùng source corpus.
- Dùng cùng chunking strategy.
- Tạo embedding cho cả documents và queries theo model tương ứng.
- Không trộn vector của hai model trong cùng không gian embedding trừ khi model được thiết kế tương thích.
- Tạo index riêng cho từng model/version.
- So relevance, latency, cost và storage.

Một model lớn hơn có thể cải thiện semantic relevance nhưng tạo embedding chậm hơn và vector dimensions lớn hơn. Một model nhỏ hơn có thể giảm cost nhưng kém ở thuật ngữ domain hoặc ngôn ngữ ít phổ biến.

Không chọn model chỉ dựa trên benchmark công khai. Domain vocabulary, tài liệu nội bộ và query distribution có thể khác dữ liệu benchmark.

## 47. Embedding model versioning

Mỗi vector nên gắn metadata về model/version hoặc được quản lý bằng index version:

    {
      "documentId": "doc-100",
      "chunkId": "doc-100-03",
      "embeddingModel": "embedding-model-v2",
      "embeddingVersion": 2,
      "embedding": [ ... ]
    }

Không index vector từ model v1 và query vector từ model v2 vào cùng không gian nếu chúng không tương thích.

Khi đổi model:

1. Tạo index version mới.
2. Re-chunk nếu cần.
3. Sinh embedding mới.
4. Index theo batch.
5. Chạy evaluation set.
6. So latency, storage và relevance.
7. Chuyển alias hoặc routing traffic.
8. Giữ khả năng rollback theo policy.

## 48. Re-embedding có thể là chi phí lớn nhất

Khi đổi model, dimensions hoặc preprocessing, thường phải tạo lại embedding cho toàn bộ corpus.

Chi phí:

- Đọc toàn bộ source.
- Tokenization/chunking.
- Gọi embedding model.
- API cost hoặc GPU time.
- Bulk indexing.
- Disk cho index cũ và mới cùng tồn tại.
- Merge và refresh.
- Validation và cutover.

Ước lượng:

    total_embedding_tokens =
      sum(tokens in all chunks)

    embedding_cost =
      total_embedding_tokens * provider_price_per_token

Nếu self-host, ước lượng theo throughput benchmark và GPU-hour. Thêm retry, failure và backfill margin.

Không chạy re-embedding toàn bộ corpus trong giờ peak nếu job cạnh tranh CPU/GPU/disk với traffic tương tác. Dùng queue, rate limit và backpressure.

## 49. Embedding cache và deduplication

Nếu cùng một nội dung được gửi nhiều lần, có thể cache embedding theo hash của:

- Normalized content.
- Model/version.
- Preprocessing version.
- Chunking configuration.

Cache key phải bao gồm model và preprocessing version. Cùng text nhưng model khác phải tạo embedding khác.

Deduplication có thể giảm chi phí khi tài liệu trùng hoặc chunk trùng, nhưng cần cẩn thận với quyền truy cập và metadata. Hai document có cùng nội dung nhưng thuộc tenant khác không có nghĩa chúng có cùng quyền truy cập hoặc cùng lifecycle.

Không dùng shared cache key để vô tình làm lộ nội dung qua tenant boundary. Cache chỉ lưu vector có thể vẫn cần kiểm soát metadata và retention.

## 50. Batching và concurrency của embedding

Batching có thể tăng throughput model bằng cách giảm overhead mỗi request. Nhưng batch quá lớn:

- Tăng memory/VRAM.
- Tăng latency cho item đầu tiên.
- Dễ vượt token limit.
- Khi batch fail, retry có thể tốn hơn.

Concurrency quá thấp làm GPU/CPU nhàn rỗi; quá cao tạo queue và memory pressure.

Benchmark:

- Batch size theo số input.
- Tổng token mỗi batch.
- Model latency.
- Throughput tokens/second.
- p95/p99 latency.
- GPU memory/utilization hoặc CPU.
- Error/retry rate.

Với dịch vụ embedding bên ngoài, tuân thủ rate limit và retry policy của provider. Không retry lỗi validation hoặc input quá dài vô hạn.

## 51. Spring Data model cho vector document

Một entity có thể chứa vector và metadata:

    @Document(indexName = "knowledge-chunks")
    public class KnowledgeChunk {

        @Id
        private String chunkId;

        private String documentId;
        private String tenantId;
        private String visibility;
        private String language;
        private String content;

        @Field(type = FieldType.Dense_Vector, dims = 768)
        private float[] embedding;
    }

Đây là ví dụ khái quát. Tên enum, thuộc tính annotation, similarity và index options phụ thuộc Spring Data Elasticsearch version. Một số dự án quản lý mapping bằng JSON/index template thay vì annotation để kiểm soát vector index options chính xác.

Dimensions của annotation/mapping phải khớp model. Không index vector có độ dài khác mapping.

## 52. Sinh embedding trước khi lưu

Service thường gọi embedding model trước khi tạo document:

    public KnowledgeChunk indexChunk(SourceChunk source) {
        float[] vector = embeddingClient.embed(source.text());

        KnowledgeChunk chunk = new KnowledgeChunk();
        chunk.setChunkId(source.id());
        chunk.setDocumentId(source.documentId());
        chunk.setTenantId(source.tenantId());
        chunk.setContent(source.text());
        chunk.setEmbedding(vector);

        return repository.save(chunk);
    }

Trong production, không nhất thiết gọi embedding đồng bộ trong request tạo tài liệu. Có thể ghi source và outbox event trước, sau đó worker tạo embedding và index. Cách này giúp kiểm soát retry, throughput và backpressure.

Nếu embedding generation fail, không đánh dấu document đã được semantic-indexed. Lưu trạng thái pending/failed để retry.

## 53. Bulk indexing vector trong Spring Data

Vector document thường được index theo batch:

    List<IndexQuery> queries = chunks.stream()
        .map(chunk -> IndexQuery.builder()
            .withId(chunk.getChunkId())
            .withObject(chunk)
            .build())
        .toList();

    operations.bulkIndex(
        queries,
        BulkOptions.builder()
            .withRefreshPolicy(RefreshPolicy.NONE)
            .build(),
        IndexCoordinates.of("knowledge-chunks")
    );

Batch size cần tính theo bytes. Một batch 1.000 vector 768 chiều float32 chỉ riêng vector thô đã khoảng 3 MB, chưa tính source, metadata, JSON encoding và request overhead. Với 10.000 vectors, payload có thể tăng lên hàng chục MB.

Bulk response có thể có partial failures. Kiểm tra từng item, retry transient failures và đưa lỗi mapping/dimensions vào DLQ hoặc error store. Không retry cả batch vô hạn.

## 54. Query vector qua Spring Data

Spring Data Elasticsearch có các abstraction cho vector search, nhưng API thay đổi theo version và Elasticsearch Java API Client.

Ở các phiên bản hiện đại, NativeQuery có thể biểu diễn kNN search thông qua API vector/kNN tương ứng. Tên builder và kiểu KnnSearch có thể khác giữa các release. Khi code thực tế:

- Kiểm tra version Spring Data Elasticsearch.
- Kiểm tra version Elasticsearch Java API Client được quản lý.
- Dùng API tương ứng với server version.
- Kiểm tra filter được gửi vào đúng vị trí pre-filter.
- Xác nhận request DSL cuối cùng bằng integration test hoặc request logging có redact.

Không sao chép builder API của một major version khác rồi giả định nó tương thích.

## 55. Query DSL với vector filter

Nếu cần kiểm soát chính xác semantics, có thể dùng NativeQuery hoặc Java API Client để tạo kNN request có filter.

Ví dụ DSL:

    {
      "size": 10,
      "query": {
        "knn": {
          "field": "embedding",
          "query_vector": [ ... ],
          "k": 10,
          "num_candidates": 200,
          "filter": {
            "bool": {
              "filter": [
                { "term": { "tenantId": "tenant-a" } },
                { "term": { "visibility": "PUBLISHED" } }
              ]
            }
          }
        }
      }
    }

Filter phải được tạo ở backend từ security context và business policy. Không cho client gửi một DSL tùy ý rồi nối vào query mà không validate.

## 56. Exact scoring với script_score

script_score có thể thực hiện vector similarity trên tập document được filter:

    {
      "query": {
        "script_score": {
          "query": {
            "bool": {
              "filter": [
                { "term": { "tenantId": "tenant-a" } },
                { "term": { "visibility": "PUBLISHED" } }
              ]
            }
          },
          "script": {
            "source": "cosineSimilarity(params.q, 'embedding') + 1.0",
            "params": {
              "q": [ ... ]
            }
          }
        }
      }
    }

Đây là exact scoring trên tập candidate do query con chọn, nhưng thường phải tính score cho mọi document match filter. Nếu tenant có hàng triệu chunks, chi phí có thể cao.

Dùng exact scoring cho:

- Ground truth nhỏ.
- Tập document đã lọc rất nhỏ.
- Use case yêu cầu exhaustive scoring và đã benchmark.

Với corpus lớn, ANN thường phù hợp hơn. Có thể dùng ANN lấy candidate rồi rerank trên candidate set.

## 57. Hybrid search và chi phí kết hợp

Semantic search thường kết hợp vector với lexical search vì vector tốt cho ý nghĩa nhưng lexical tốt cho exact terms, IDs, tên riêng và mã kỹ thuật.

Một pipeline hybrid:

    Lexical retrieval ----\
                           +--> Fusion / rerank --> top results
    Vector retrieval -----/

Hai cách phổ biến:

- Reciprocal Rank Fusion (RRF).
- Weighted score combination hoặc reranker model.

RRF kết hợp thứ hạng thay vì yêu cầu score lexical và vector cùng thang đo. Weighted score cần calibration vì hai loại score có thể có phân phối khác nhau.

Hybrid search tăng chất lượng ở nhiều domain nhưng tạo thêm query cost, candidate merge và có thể thêm model reranking.

Đánh giá lexical-only, vector-only và hybrid trên cùng evaluation set. Không kết luận hybrid tốt hơn chỉ vì có thêm nhiều kết quả.

## 58. Reranking

Reranker nhận candidate documents và query, sau đó đánh giá relevance chi tiết hơn. Nó có thể dùng cross-encoder hoặc model khác.

Reranking có thể cải thiện NDCG/MRR nhưng tăng:

- Model inference cost.
- Latency.
- CPU/GPU.
- Memory.
- Network và payload transfer.

Giới hạn candidate count và chỉ rerank top-N phù hợp. Đo marginal relevance gain so với latency/cost tăng thêm.

Nếu ANN không lấy được document relevant vào candidate set, reranker không thể tự tìm thấy document đó. Candidate recall vẫn là yếu tố quan trọng.

## 59. Đánh giá toàn bộ pipeline

Một hệ thống có nhiều stage:

1. Query normalization.
2. Query embedding.
3. Security/business filter construction.
4. Vector/lexical retrieval.
5. Candidate fusion.
6. Reranking.
7. Duplicate collapse hoặc parent document grouping.
8. Response projection.

Đo latency từng stage và end-to-end:

| Stage | Metric |
|---|---|
| Query embedding | latency, tokens, error, cost |
| Filter construction | duration, policy failures |
| ANN retrieval | took, candidate count, recall |
| Lexical retrieval | latency, hit count |
| Fusion | duration, overlap |
| Rerank | latency, model cost |
| Response mapping | allocation, serialization |
| End-to-end | p50/p95/p99, error rate |

Nếu query embedding chiếm 70% latency, tối ưu HNSW không giúp nhiều cho user-perceived latency. Nếu reranker chậm, giảm candidate count hoặc tối ưu model có thể hiệu quả hơn.

## 60. Đo index throughput và ingestion lag

Semantic indexing có nhiều stage, vì vậy đo documents/second ở Elasticsearch chưa đủ.

Theo dõi:

- Source records discovered.
- Chunks generated/second.
- Embedding tokens/second.
- Embedding latency.
- Embedding failure/retry.
- Vector documents indexed/second.
- Bulk item failures.
- Time from source update to searchable.
- Backlog age.

Một pipeline có thể index rất nhanh nhưng embedding worker không theo kịp, khiến search projection cũ. Hoặc embedding nhanh nhưng Elasticsearch bulk bị reject.

Đặt queue có giới hạn và backpressure giữa chunking, embedding và indexing. Tránh để hàng triệu chunk chờ trong heap.

## 61. Reindex và model migration

Khi thay dimensions, similarity hoặc vector index options, có thể cần index mới. Mapping vector thường không thể thay đổi tùy ý sau khi tạo index.

Quy trình:

1. Tạo index version mới với mapping đúng.
2. Chọn model và preprocessing version.
3. Sinh embedding theo batch.
4. Index và kiểm tra bulk failures.
5. Đo store size, segment, memory và latency.
6. Chạy evaluation set.
7. Đối soát document/chunk count.
8. Chuyển alias hoặc query routing.
9. Theo dõi quality/latency sau cutover.
10. Giữ index cũ để rollback theo retention policy.

Không trộn vector của model không tương thích trong cùng field chỉ để tránh reindex.

## 62. Rebuild HNSW và build-time cost

Khi thay m, ef_construction hoặc vector representation, graph index có thể phải được xây lại. Đây là chi phí khác với query-time tuning num_candidates.

Build cost phụ thuộc:

- Số vector.
- Dimensions.
- Graph parameters.
- Bulk concurrency.
- CPU và disk.
- Shard topology.
- Quantization.

Đo thời gian ingest đến khi index ổn định, không chỉ thời gian gửi bulk request. Refresh và merge có thể tiếp tục sau khi request đã trả response.

Không thay HNSW build parameters trực tiếp trên production index mà không hiểu yêu cầu reindex/version support.

## 63. Disk, RAM và capacity planning cho vector index

Một mô hình capacity:

    vector_raw_bytes =
      vector_count * dimensions * bytes_per_value

    primary_index_size =
      vector_raw_bytes
      + graph_overhead
      + source_and_metadata
      + lucene_overhead

    cluster_storage =
      primary_index_size * (1 + replicas)

    required_capacity =
      cluster_storage
      + merge_and_recovery_headroom
      + reindex_overlap
      + growth_margin

Graph overhead và các phần còn lại phải đo từ sample index. Không có hệ số chung đúng cho mọi mapping, version và vector index type.

RAM cần cho heap, native memory và page cache. Một vector index lớn không đồng nghĩa toàn bộ raw vectors phải nằm trong heap. Hãy đo working set, page cache hit, disk latency và query access pattern.

## 64. Benchmark vector indexing

Một benchmark indexing nên giữ cố định:

- Vector count.
- Dimensions.
- Vector distribution.
- Chunk size.
- Mapping và similarity.
- HNSW parameters.
- Quantization type.
- Shard/replica count.
- Bulk size theo bytes.
- Refresh interval.
- Hardware.

Đo:

- Embedding generation throughput.
- Bulk indexing throughput.
- p95 bulk latency.
- Index size primary/total.
- Segment count.
- Merge time.
- Heap/RSS/page cache.
- Disk throughput/latency.
- 429 và item failures.
- Thời gian đến khi search visibility ổn định.

Chạy nhiều batch size và concurrency. Không chọn batch lớn nhất chỉ vì throughput cao trong vài phút nếu merge backlog và memory tăng liên tục.

## 65. Benchmark vector search

Một benchmark search cần:

- Query set đại diện.
- Ground truth exact top-k.
- Filter theo tenant/ACL/business.
- k và num_candidates khác nhau.
- Shard topology giống production.
- Cache state có ghi nhận.
- Concurrency và arrival rate thực tế.

Đo:

- Recall@k.
- Precision/NDCG/MRR theo labels.
- p50/p95/p99 latency.
- Throughput.
- Error/rejection rate.
- Candidate count.
- CPU, heap, RSS, page cache và disk I/O.
- Số kết quả sau filter.

Không đánh đổi security để tăng recall hoặc giảm latency. Kết quả không được phép truy cập phải bị loại trước khi trả response.

## 66. Đánh giá filtered recall

Đối với từng query và user context:

1. Tạo tập document đủ điều kiện bằng mandatory filters.
2. Tạo exact top-k trên tập đủ điều kiện.
3. Chạy ANN với cùng pre-filter.
4. So sánh tập ID và tính recall@k.
5. Tính relevance metrics trên kết quả hợp lệ.
6. Ghi latency và số hit.

Lặp lại cho tenant lớn/nhỏ, ACL rộng/hẹp, public/restricted, language và date filters.

Nếu post-filter được dùng trong một flow cụ thể, đo tỷ lệ query trả ít hơn k hits và so với pre-filter. Tuy nhiên, mandatory access control không được phụ thuộc vào frontend filtering.

## 67. A/B test và online quality

Offline evaluation giúp so sánh nhanh và tái lập, nhưng online behavior có thể khác do query distribution và user intent thật.

Một A/B test nên:

- Chia traffic ngẫu nhiên và ổn định.
- Giữ security policy giống nhau.
- Không cho một nhóm xem dữ liệu mà nhóm khác không có quyền.
- Đo click, useful result, conversion hoặc task completion.
- Theo dõi latency/error.
- Phân tích theo query family và tenant cohort.
- Có guardrail cho zero-result và restricted access.

Không tối ưu click rate đơn độc nếu click không phản ánh chất lượng. Có thể cần human review, dwell time hoặc task success.

## 68. Cost per useful result

Một metric vận hành hữu ích là chi phí để tạo ra một kết quả được đánh giá hữu ích.

Có thể theo dõi:

    cost_per_useful_result =
      total_embedding_and_search_cost
      / useful_results_count

Đây là metric tổng hợp, cần định nghĩa rõ useful result và cost window. Nó giúp so sánh model lớn/chậm với model nhỏ/nhanh khi chất lượng khác nhau.

Ví dụ model A tốn gấp đôi inference cost nhưng tăng tỷ lệ query có kết quả hữu ích từ 60% lên 90%. Cost per useful result có thể vẫn tốt hơn.

Không chỉ tối ưu cost per vector nếu hệ thống tạo nhiều vector không relevant hoặc chunking kém.

## 69. Theo dõi chi phí theo model và tenant

Có thể ghi nhận:

- Embedding tokens theo model/version.
- Số chunk theo tenant.
- Số lần re-embedding.
- Vector count và index size.
- Query count và rerank count.
- CPU/GPU time.
- Search latency và quality.

Metric tags cần tránh cardinality quá cao. Với tenant lớn, có thể dùng bảng usage hoặc analytics riêng thay vì tạo metric series cho mọi document/user.

Không log nội dung raw chỉ để đo cost. Token count, model name, dimensions và event ID thường đủ cho operational metrics.

## 70. Những lỗi thường gặp

### Chỉ tính storage bằng số document

Một document có thể tạo nhiều chunk và nhiều vector. Tính theo vector count.

### Dùng float32 raw size làm tổng index size

Bỏ sót HNSW graph, metadata, source, Lucene overhead, replica và merge headroom. Đo sample index.

### Tăng dimensions mà không đo quality

Vector lớn hơn tốn storage và search cost, nhưng không đảm bảo relevance tăng. Đánh giá trên query set.

### Giảm dimensions bằng cách cắt vector

Có thể phá embedding space. Dùng model hỗ trợ dimensions hoặc phương pháp reduction được đánh giá.

### Tăng m và ef_construction tùy tiện

Indexing tốn CPU/memory hơn và storage tăng. Benchmark recall/build time.

### Tăng num_candidates vô hạn

Recall có thể tăng nhưng latency/CPU cũng tăng. Tìm điểm cân bằng theo SLO.

### Dùng post-filter cho quyền truy cập

Có thể trả ít hơn k kết quả và tạo rủi ro nếu filter bị bỏ sót ở một response path. Dùng mandatory pre-filter/security enforcement.

### Tin tenantId từ client

Client có thể thay tenant để truy cập dữ liệu khác. Lấy tenant từ authenticated principal.

### Chỉ đánh giá nearest-neighbor recall

Nearest vector không nhất thiết là kết quả relevant. Cần human relevance judgments và NDCG/MRR/Precision.

### Chỉ đánh giá relevance mà không đo ANN recall

Không biết candidate generation đang bỏ lỡ document hay embedding model sai. Đo cả exact-neighbor recall và business relevance.

### Dùng script_score trên corpus lớn như ANN

Exact scoring có thể scan toàn bộ tập đã lọc và tốn CPU. Dùng làm ground truth hoặc trên tập nhỏ.

### Trộn embedding của hai model

Không gian vector có thể không tương thích. Dùng index version riêng và re-embed.

### Re-embedding không có queue/backpressure

Có thể làm cạn GPU, memory hoặc disk. Batch, rate limit và theo dõi backlog.

### Không tính index overlap khi migration

Index cũ và mới cùng tồn tại. Capacity phải có reindex headroom.

### Đánh giá chỉ bằng query dễ

Thiếu paraphrase, multilingual, rare terms, zero-result và ACL scenarios. Dùng query set đại diện.

### Không kiểm thử quyền sau filter

Kết quả relevant nhưng user không có quyền xem vẫn là lỗi bảo mật. Security assertions phải độc lập với relevance metrics.

## 71. Quy trình tối ưu semantic search

Một quy trình có thể thực hiện theo thứ tự:

1. Đo số document, chunk và vector hiện tại.
2. Đo token distribution và embedding cost.
3. Chọn model, dimensions, normalization và similarity phù hợp.
4. Tối ưu chunking bằng evaluation set.
5. Ước lượng raw vector storage rồi index sample để đo thực tế.
6. Benchmark HNSW parameters và quantization.
7. Chọn shard/replica theo throughput, recovery và capacity.
8. Xây mandatory security filters từ trusted principal.
9. Đặt business filters trong filter context.
10. Xác nhận kNN filter được áp dụng pre-filter theo API/version.
11. Tạo exact ground truth trên tập document hợp lệ.
12. Đo recall@k và relevance metrics.
13. Tune num_candidates và reranking theo quality/latency.
14. Chạy mixed workload và benchmark indexing/search đồng thời.
15. Lưu model, mapping, dataset và evaluation version.
16. Reindex qua index version mới khi thay đổi không tương thích.
17. Theo dõi cost, lag, recall, relevance và access violations sau triển khai.

## Kết luận

Semantic search có chi phí ở cả embedding pipeline và Elasticsearch vector index. Số vector phụ thuộc số document và chunking; vector float32 thô cần khoảng dimensions nhân 4 bytes, nhưng tổng index còn có HNSW graph, metadata, source, Lucene segments, replicas và merge/reindex headroom. Dimensions, m, ef_construction, quantization và num_candidates tạo tradeoff giữa indexing time, storage, memory, latency và recall. Cần benchmark trên dữ liệu, query và shard topology gần production.

Kết quả phải được đánh giá ở hai tầng: ANN recall so với exact nearest neighbors và business relevance bằng Precision@k, Recall@k, MRR, NDCG hoặc MAP với relevance judgments. Khi có tenant/ACL và điều kiện nghiệp vụ, ground truth phải được tính trên tập document hợp lệ. Mandatory access filters phải được tạo từ authenticated principal và áp dụng trong retrieval/security layer; không tin tenant từ client hoặc chỉ post-filter ở frontend. Kết hợp monitoring cost, embedding throughput, vector count, disk/RAM, p95/p99, quality và security assertions giúp chọn model, chunking, HNSW, quantization và query strategy có hiệu quả thực tế.
