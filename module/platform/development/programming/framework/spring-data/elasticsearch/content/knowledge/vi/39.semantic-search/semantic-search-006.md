# Kết hợp tìm kiếm từ khóa và vector theo khả năng của Elasticsearch

Tìm kiếm từ khóa và tìm kiếm vector giải quyết hai kiểu truy vấn khác nhau. Tìm kiếm từ khóa phù hợp khi người dùng cần tên, mã, cụm từ hoặc thuật ngữ xuất hiện trong tài liệu. Tìm kiếm vector phù hợp khi người dùng diễn đạt ý định bằng ngôn ngữ tự nhiên và muốn tìm nội dung gần nghĩa dù không có cùng từ ngữ. Một hệ thống tìm kiếm sản phẩm hoặc tài liệu thường cần cả hai.

**Hybrid search** kết hợp kết quả lexical và vector trong cùng một trải nghiệm. Elasticsearch có thể thực hiện các nhánh tìm kiếm này và hợp nhất thứ hạng bằng các khả năng như retriever và Reciprocal Rank Fusion (RRF) ở những phiên bản hỗ trợ. Với phiên bản chưa có API hợp nhất phù hợp, ứng dụng có thể chạy hai nhánh riêng rồi hợp nhất kết quả ở service.

Bài học này giải thích cách hoạt động của BM25 và vector retrieval, cách chuẩn bị embedding và mapping, cách kết hợp hai nhánh, cách dùng Spring Data Elasticsearch làm lớp truy cập, cùng những quyết định về filter, hiệu năng, đánh giá relevance và kiểm thử.

## 1. Vì sao cần kết hợp keyword và vector?

Giả sử người dùng tìm kiếm:

> máy tính nhẹ để mang đi học, pin dùng lâu

Tìm kiếm từ khóa có thể ưu tiên document chứa các từ “máy tính”, “nhẹ”, “pin” hoặc các biến thể đã được analyzer xử lý. Nhưng một sản phẩm mô tả “ultrabook 14 inch, thời lượng pin 12 giờ, trọng lượng 1,1 kg” có thể phù hợp dù không chứa đúng cụm từ người dùng nhập.

Vector search biến câu hỏi và nội dung thành embedding — các vector số biểu diễn ngữ nghĩa. Hai câu có ý nghĩa gần nhau thường có vector gần nhau theo metric của model, kể cả khi dùng từ khác nhau.

Mỗi phương pháp có điểm mạnh riêng:

| Khả năng | Keyword / lexical search | Vector search |
|---|---|---|
| Mã sản phẩm, SKU, tên riêng | Rất phù hợp | Có thể không ổn định |
| Cụm từ chính xác | Phù hợp với term/phrase query | Không bảo đảm khớp chính xác |
| Ý định diễn đạt bằng từ khác | Phụ thuộc analyzer, synonym | Thường xử lý tốt hơn |
| Thuật ngữ hiếm hoặc mã kỹ thuật | Thường mạnh | Embedding có thể làm mờ khác biệt |
| Ngữ nghĩa và nội dung gần nghĩa | Hạn chế hơn | Là thế mạnh |
| Giải thích kết quả | Có thể xem term/query score | Khó diễn giải trực tiếp vector score |
| Chi phí xử lý | Thường thấp hơn | Cần embedding và vector retrieval |

Hybrid search tận dụng lexical match cho mã, tên và từ khóa quan trọng, đồng thời dùng vector để tìm nội dung có ý nghĩa tương tự.

Không nên mặc định vector search luôn tốt hơn keyword search. Với truy vấn “SKU-AX91-RED”, exact term hoặc prefix query có thể chính xác hơn embedding. Với truy vấn mô tả nhu cầu bằng câu dài, vector retrieval có thể bổ sung những kết quả lexical bỏ sót.

## 2. Luồng xử lý hybrid search

Một hệ thống thường có hai thời điểm tạo embedding:

- **Index time:** tạo embedding cho nội dung được lưu trong Elasticsearch.
- **Query time:** tạo embedding cho câu hỏi của người dùng.

Hai vector phải đến từ model tương thích, cùng không gian vector, cùng dimension và cùng quy trình tiền xử lý.

~~~text
                    INDEX TIME
Product/document
      |
      +------------------------------+
      |                              |
      v                              v
Text fields                      Embedding model
      |                              |
      v                              v
Inverted index                  Dense vector
      |                              |
      +---------------+--------------+
                      |
                      v
                Elasticsearch


                    QUERY TIME
User query
      |
      +------------------------------+
      |                              |
      v                              v
Lexical query                    Embedding model
      |                              |
      v                              v
BM25 / standard search          kNN vector search
      |                              |
      +---------------+--------------+
                      |
                      v
                Rank fusion
                      |
                      v
              ProductSearchResponse
~~~

Trong Spring Data Elasticsearch, repository hoặc ElasticsearchOperations chịu trách nhiệm gửi query và ánh xạ kết quả. Việc gọi model embedding có thể nằm trong một EmbeddingService, một inference endpoint hoặc được Elasticsearch quản lý thông qua semantic field tùy phiên bản và cấu hình.

Không nhầm vector field với model. Elasticsearch lưu và tìm kiếm vector; việc tạo embedding cần một model hoặc inference pipeline có khả năng tương ứng.

## 3. Keyword search và BM25

Elasticsearch dùng inverted index cho các field text. Analyzer có thể tách token, chuẩn hóa chữ hoa/thường, loại stop word hoặc áp dụng stemming/synonym tùy cấu hình.

Ví dụ mapping:

~~~json
{
  "properties": {
    "name": {
      "type": "text"
    },
    "description": {
      "type": "text"
    },
    "sku": {
      "type": "keyword"
    },
    "brand": {
      "type": "keyword"
    },
    "status": {
      "type": "keyword"
    }
  }
}
~~~

Các field name và description phù hợp với full-text query. Các field sku, brand và status phù hợp với exact filter hoặc term query.

Ví dụ lexical query:

~~~http
GET /products/_search
{
  "query": {
    "bool": {
      "must": [
        {
          "multi_match": {
            "query": "máy tính nhẹ pin lâu",
            "fields": [
              "name^3",
              "description",
              "categoryText"
            ]
          }
        }
      ],
      "filter": [
        {
          "term": {
            "status": "ACTIVE"
          }
        }
      ]
    }
  }
}
~~~

name^3 tăng boost cho field name. Query trên có thể dùng BM25 để tính relevance dựa trên term match, độ hiếm của term và độ dài field.

### Khi nào lexical match quan trọng hơn?

- SKU, serial number hoặc mã đơn hàng.
- Tên thương hiệu và model cụ thể.
- Thuật ngữ pháp lý hoặc kỹ thuật phải khớp.
- Từ khóa hiếm mang ý nghĩa quyết định.
- Các điều kiện nghiệp vụ exact như status, category hoặc tenant.

Có thể kết hợp match, match_phrase, term, prefix hoặc synonym theo yêu cầu. Không đưa tất cả field vào multi_match một cách máy móc; chọn field và boost theo dữ liệu thật.

## 4. Vector search và embedding

Embedding model chuyển văn bản thành vector có số chiều cố định. Ví dụ một model tạo vector 768 chiều:

~~~text
"laptop nhẹ, pin lâu"
          |
          v
    Embedding model
          |
          v
[0.12, -0.08, 0.44, ..., 0.03]
          |
          v
       768 values
~~~

Một document có thể tạo embedding từ:

- Tên và mô tả sản phẩm.
- Nội dung tài liệu.
- Tiêu đề cộng với phần tóm tắt.
- Các trường được ghép theo template rõ ràng.

Query của người dùng cũng được đưa qua cùng model để tạo vector cùng dimension.

### Dimension phải khớp

Nếu mapping khai báo 768 dimensions, vector index và query vector phải có đúng 768 phần tử. Sai dimension có thể khiến request bị từ chối.

Không đổi model sang model khác có dimension giống nhau rồi mặc định vector vẫn tương thích. Hai model khác nhau thường tạo không gian embedding khác nhau, kể cả khi cùng số chiều. Cần re-embed dữ liệu hoặc duy trì version model tương thích.

### Metric similarity

Các metric phổ biến gồm:

- **cosine:** đo hướng tương đồng của vector; thường dùng với embedding văn bản.
- **dot_product:** tích vô hướng; semantics phụ thuộc cách model chuẩn hóa vector.
- **l2_norm:** khoảng cách Euclidean; vector gần hơn theo khoảng cách này có ý nghĩa tương đồng hơn theo cách model được huấn luyện.

Chọn metric theo model embedding và cách vector được tạo. Không thay metric tùy ý sau khi index dữ liệu.

### Không coi vector score là xác suất

Score từ cosine, dot product hoặc L2 không phải phần trăm độ phù hợp. Giá trị và chiều tốt/xấu phụ thuộc metric, mapping và Elasticsearch version. Không hiển thị “92% match” nếu không có calibration riêng.

## 5. Mapping dense_vector

Với embedding do ứng dụng tạo, một lựa chọn là field dense_vector.

Ví dụ mapping:

~~~http
PUT /products-v1
{
  "mappings": {
    "properties": {
      "name": {
        "type": "text"
      },
      "description": {
        "type": "text"
      },
      "sku": {
        "type": "keyword"
      },
      "status": {
        "type": "keyword"
      },
      "embedding": {
        "type": "dense_vector",
        "dims": 768,
        "index": true,
        "similarity": "cosine"
      }
    }
  }
}
~~~

dims, index, similarity và các tùy chọn vector index cần phù hợp Elasticsearch version. Các phiên bản cũ có giới hạn hoặc default khác với phiên bản mới; kiểm tra mapping capabilities của cluster đang chạy.

Nếu vector chỉ được lưu mà không được index cho ANN search, cách query và hiệu năng có thể khác. Với approximate kNN, cần cấu hình vector index phù hợp.

### Entity Spring Data

Ví dụ entity minh họa:

~~~java
@Document(indexName = "products-v1")
public class ProductDocument {

    @Id
    private String id;

    @Field(type = FieldType.Text)
    private String name;

    @Field(type = FieldType.Text)
    private String description;

    @Field(type = FieldType.Keyword)
    private String sku;

    @Field(type = FieldType.Keyword)
    private String status;

    // Dense vector mapping is configured for the deployed
    // Spring Data Elasticsearch / Elasticsearch version.
    private float[] embedding;
}
~~~

Annotation và conversion của dense vector thay đổi theo release train. Với dự án cần kiểm soát chính xác dims, similarity và index options, quản lý mapping bằng index template hoặc provisioning resource rồi kiểm tra mapping thực tế.

Không cho rằng chỉ khai báo float[] trong entity là đủ để tạo đúng dense_vector mapping trên mọi phiên bản.

## 6. Tạo và lưu embedding

Nếu ứng dụng tự gọi model, nên bọc model sau một interface:

~~~java
public interface EmbeddingService {

    float[] embed(String text);
}
~~~

Implementation có thể gọi model local, model service hoặc inference endpoint:

~~~java
@Service
public class ProductEmbeddingService {

    private final EmbeddingService embeddingService;

    public ProductEmbeddingService(
            EmbeddingService embeddingService) {
        this.embeddingService = embeddingService;
    }

    public ProductDocument prepare(ProductDocument product) {
        String text = product.getName()
            + "\n"
            + product.getDescription();

        product.setEmbedding(
            embeddingService.embed(text)
        );

        return product;
    }
}
~~~

Đây là cấu trúc minh họa. Trong hệ thống thật, cần xử lý timeout, retry có giới hạn, model availability và lỗi dimension. Không gọi model embedding lặp lại cho cùng nội dung nếu có thể tái sử dụng embedding đã tính.

### Index flow

~~~java
public ProductDocument index(ProductDocument product) {
    ProductDocument prepared = embeddingService.prepare(product);
    return repository.save(prepared);
}
~~~

Có thể thực hiện embedding trong ingest pipeline của Elasticsearch nếu cluster được cấu hình inference processor phù hợp. Khi đó, ứng dụng gửi text và Elasticsearch/inference service tạo vector. Cần xác định rõ thành phần nào chịu trách nhiệm tạo embedding để tránh tạo hai lần hoặc ghi đè vector bằng model khác.

### Model version và re-embedding

Lưu hoặc quản lý metadata cho biết vector được tạo bằng model/version nào. Khi đổi model, cần chiến lược migration:

1. Tạo field hoặc index mới cho embedding version mới.
2. Re-embed dữ liệu theo model mới.
3. Kiểm tra dimension và chất lượng retrieval.
4. Chạy shadow query hoặc so sánh offline.
5. Chuyển traffic khi kết quả đạt yêu cầu.
6. Ngừng field/index cũ sau khi rollback window kết thúc.

Không trộn vector từ hai model không tương thích vào cùng một field chỉ vì chúng có cùng dimension.

## 7. kNN search với dense_vector

kNN tìm các vector gần query vector nhất theo metric đã cấu hình. Ví dụ request:

~~~http
GET /products-v1/_search
{
  "knn": {
    "field": "embedding",
    "query_vector": [0.12, -0.08, 0.44],
    "k": 20,
    "num_candidates": 200
  },
  "size": 20
}
~~~

Vector trong ví dụ được rút gọn để minh họa cấu trúc; request thực tế phải chứa đủ số chiều đã khai báo trong mapping.

Các tham số quan trọng:

- field: dense_vector field.
- query_vector: embedding của câu hỏi.
- k: số láng giềng gần nhất cần tìm.
- num_candidates: số ứng viên được xem xét trên mỗi shard trước khi chọn kết quả cuối theo cơ chế ANN.
- size: số hit tối đa trả về.

Tăng num_candidates thường có thể cải thiện recall nhưng tăng chi phí CPU/latency. Chọn k và num_candidates bằng benchmark, không chỉ tăng thật lớn để hy vọng kết quả tốt hơn.

### Approximate kNN và exact search

Approximate nearest neighbor (ANN) dùng cấu trúc index vector để tìm gần đúng nhanh trên tập dữ liệu lớn. Exact vector scoring có thể quét nhiều vector hơn và phù hợp với tập nhỏ hoặc bước rerank trên candidate set giới hạn.

Đánh đổi cơ bản:

| Cách tìm | Điểm mạnh | Giới hạn |
|---|---|---|
| ANN / HNSW | Tìm nhanh trên tập vector lớn | Có thể bỏ sót láng giềng thật |
| Exact scoring trên tập giới hạn | Kiểm soát chính xác candidate set | Không thích hợp quét toàn bộ index lớn |
| Exact scan toàn tập | Kết quả gần nhất chính xác theo metric | Chi phí có thể rất cao |

Không nhầm k với số document cuối cùng của toàn bộ hybrid result. Một nhánh vector có thể lấy candidate set lớn hơn số kết quả cuối để rank fusion có đủ dữ liệu.

## 8. Hybrid search: hai nhánh, một kết quả

Hybrid search có thể được tổ chức thành:

1. Lexical retriever: tìm bằng BM25 hoặc Query DSL.
2. Vector retriever: tìm bằng kNN.
3. Rank fusion: hợp nhất hai danh sách kết quả.
4. Optional reranker: xếp hạng lại một tập candidate nhỏ bằng model hoặc business signals.

~~~text
              User query
                  |
          +-------+-------+
          |               |
          v               v
    Lexical branch    Embedding model
          |               |
          v               v
      BM25 search       kNN search
          |               |
          +-------+-------+
                  |
                  v
             Rank fusion
                  |
                  v
             Top results
                  |
             Optional rerank
                  |
                  v
             API response
~~~

Một document có thể xuất hiện ở cả hai nhánh. Fusion cần hợp nhất theo document identity, tránh trả duplicate và giữ metadata cần thiết từ cả hai nguồn.

### Vì sao không cộng thẳng hai score?

BM25 score và vector similarity score có phân phối khác nhau. Ví dụ BM25 có thể từ 0 đến một giá trị lớn tùy corpus và query; cosine similarity có miền và semantics riêng. Cộng trực tiếp hai giá trị mà không hiệu chỉnh có thể khiến một nhánh lấn át nhánh kia.

Có thể dùng score normalization/weighted combination nếu có dữ liệu đánh giá và calibration rõ. Một lựa chọn thường dùng là Reciprocal Rank Fusion.

## 9. Reciprocal Rank Fusion (RRF)

RRF hợp nhất dựa trên thứ hạng thay vì cộng raw score.

Với mỗi document, điểm RRF là tổng đóng góp từ các danh sách:

\[
RRF(d) = \sum_{r \in R} \frac{1}{k_0 + rank_r(d)}
\]

Trong đó:

- R là tập danh sách kết quả từ các retriever.
- rank_r(d) là vị trí của document trong danh sách retriever r.
- k_0 là rank constant giúp điều chỉnh mức ảnh hưởng của vị trí.

Nếu document không xuất hiện trong một danh sách, nhánh đó không đóng góp điểm cho document.

Ví dụ:

| Document | Lexical rank | Vector rank |
|---|---:|---:|
| P-100 | 1 | 8 |
| P-200 | 3 | 2 |
| P-300 | 2 | Không có |
| P-400 | Không có | 1 |

RRF có thể đưa P-100 và P-200 lên đầu vì chúng được nhiều nhánh đánh giá cao. P-400 có vector rank tốt nhưng không có lexical match; P-300 có lexical rank tốt nhưng không có vector match. Kết quả cuối phụ thuộc rank constant và rank window.

RRF không cần so sánh trực tiếp BM25 score với cosine score, nên thường là điểm khởi đầu tốt cho hybrid retrieval.

### rank_window_size và rank_constant

- rank_window_size xác định số kết quả mỗi retriever được xem xét khi fusion.
- rank_constant điều chỉnh mức đóng góp của thứ hạng.

Nếu rank window quá nhỏ, document tốt nằm ngoài candidate window của một nhánh không thể tham gia fusion. Nếu quá lớn, chi phí và lượng dữ liệu trung gian tăng.

Không có giá trị tối ưu cố định. Hãy đánh giá bằng tập truy vấn đại diện và latency budget.

## 10. Hybrid search bằng retriever API

Các phiên bản Elasticsearch có hỗ trợ retriever API có thể kết hợp standard retriever và kNN retriever bằng RRF ngay trong search request.

Ví dụ Query DSL:

~~~http
GET /products-v1/_search
{
  "retriever": {
    "rrf": {
      "retrievers": [
        {
          "standard": {
            "query": {
              "multi_match": {
                "query": "máy tính nhẹ pin lâu",
                "fields": [
                  "name^3",
                  "description"
                ]
              }
            }
          }
        },
        {
          "knn": {
            "field": "embedding",
            "query_vector": [0.12, -0.08, 0.44],
            "k": 50,
            "num_candidates": 200
          }
        }
      ],
      "rank_window_size": 100,
      "rank_constant": 60
    }
  },
  "size": 20
}
~~~

Vector ở ví dụ được rút gọn. Thay bằng vector đầy đủ do embedding model tạo ra.

Retriever API và các retriever con được hỗ trợ tùy Elasticsearch version. RRF retriever cũng có điều kiện version/license theo phân phối và môi trường triển khai. Trước khi chọn cách này, kiểm tra API capabilities của cluster thực tế.

### Kết hợp filter trong cả hai nhánh

Nếu API tìm kiếm theo tenant hoặc chỉ sản phẩm đang active, filter phải được áp dụng đúng trong từng nhánh retriever.

Ví dụ:

~~~http
GET /products-v1/_search
{
  "retriever": {
    "rrf": {
      "retrievers": [
        {
          "standard": {
            "query": {
              "bool": {
                "must": [
                  {
                    "multi_match": {
                      "query": "laptop pin lâu",
                      "fields": ["name", "description"]
                    }
                  }
                ],
                "filter": [
                  { "term": { "tenantId": "tenant-A" } },
                  { "term": { "status": "ACTIVE" } }
                ]
              }
            }
          }
        },
        {
          "knn": {
            "field": "embedding",
            "query_vector": [0.12, -0.08, 0.44],
            "k": 50,
            "num_candidates": 200,
            "filter": {
              "bool": {
                "filter": [
                  { "term": { "tenantId": "tenant-A" } },
                  { "term": { "status": "ACTIVE" } }
                ]
              }
            }
          }
        }
      ],
      "rank_window_size": 100,
      "rank_constant": 60
    }
  },
  "size": 20
}
~~~

Đây là cấu trúc minh họa cho retriever API hiện đại. Cú pháp và vị trí filter cần đối chiếu với phiên bản Elasticsearch. Điều quan trọng là tenant/status scope phải được áp dụng cho cả lexical lẫn vector retrieval. Nếu chỉ filter một nhánh, kết quả từ nhánh còn lại có thể đưa document ngoài phạm vi vào fusion.

Tenant ID phải được lấy từ authenticated context phía server, không nhận như một giá trị đã được tin cậy từ client.

## 11. Hybrid search trên phiên bản chưa có RRF retriever

Nếu cluster chưa hỗ trợ retriever API hoặc RRF, có thể tổ chức hai truy vấn độc lập:

~~~text
Search service
    |
    +---- lexical query ---> top N lexical hits
    |
    +---- vector query ----> top N vector hits
    |
    v
Application-side RRF
    |
    v
Deduplicate by document ID
    |
    v
Fetch/map response DTO
~~~

Service có thể chạy hai request độc lập song song nếu client, connection pool và resource budget cho phép. Sau đó, ứng dụng tạo bảng rank theo document ID và tính RRF.

Pseudocode:

~~~java
Map<String, Double> scores = new HashMap<>();

addRrfScores(scores, lexicalHits, rankConstant);
addRrfScores(scores, vectorHits, rankConstant);

List<String> orderedIds = scores.entrySet().stream()
    .sorted(Map.Entry.<String, Double>comparingByValue().reversed())
    .map(Map.Entry::getKey)
    .toList();
~~~

Helper:

~~~java
private void addRrfScores(
        Map<String, Double> scores,
        List<SearchHit<Product>> hits,
        int rankConstant) {

    for (int i = 0; i < hits.size(); i++) {
        String id = hits.get(i).getId();
        int rank = i + 1;

        scores.merge(
            id,
            1.0 / (rankConstant + rank),
            Double::sum
        );
    }
}
~~~

Pseudocode giả định document ID duy nhất trong phạm vi kết quả hợp nhất. Nếu ID có thể trùng giữa index/tenant, dùng khóa composite gồm index hoặc tenant và ID theo contract.

### Ưu và nhược điểm của application-side fusion

Ưu điểm:

- Có thể chạy trên cluster cũ.
- Dễ thử nghiệm nhiều công thức fusion.
- Có thể thêm business signal hoặc reranker.
- Tách retrieval strategy khỏi API endpoint.

Nhược điểm:

- Hai request tạo thêm network round trips.
- Service phải giữ và hợp nhất candidate list.
- Pagination trên kết quả đã fusion phức tạp hơn.
- Cần xử lý lỗi partial nếu một nhánh thất bại.
- Phải bảo đảm filter/tenant scope giống nhau ở cả hai nhánh.

Nếu một nhánh lỗi, không tự động trả kết quả của nhánh kia như thể hybrid search đã thành công. Nếu có fallback, response nên biểu đạt degraded mode hoặc log/metric rõ ràng theo contract.

## 12. Spring Data Elasticsearch và NativeQuery

Spring Data Elasticsearch cung cấp ElasticsearchOperations và NativeQuery để xây dựng và thực thi truy vấn bằng Elasticsearch Java API Client abstraction.

Một lexical query:

~~~java
NativeQuery query = NativeQuery.builder()
    .withQuery(q -> q.multiMatch(m -> m
        .query(searchText)
        .fields("name^3", "description")
    ))
    .withPageable(PageRequest.of(0, 50))
    .build();

SearchHits<ProductDocument> hits =
    operations.search(query, ProductDocument.class);
~~~

Sau đó có thể map SearchHit::getContent hoặc giữ hit metadata để xây response.

### Vector và hybrid API phụ thuộc release train

Khả năng biểu diễn kNN, retriever và RRF qua NativeQuery thay đổi theo phiên bản Spring Data Elasticsearch và Elasticsearch Java API Client. Một số release có API cho kNN search; retriever API có thể chưa được expose qua abstraction tương ứng.

Vì vậy, cần xác nhận ba lớp version:

1. Elasticsearch server version và feature availability.
2. Spring Data Elasticsearch version.
3. Elasticsearch Java API Client version được Spring Data quản lý.

Không copy một method builder từ release khác rồi giả định code sẽ compile. Nếu abstraction chưa hỗ trợ retriever cần thiết, có thể dùng Java API Client trực tiếp trong một gateway riêng và map response về application model.

### Tách query gateway

Có thể tạo interface:

~~~java
public interface ProductHybridSearchGateway {

    ProductHybridSearchResult search(
        ProductSearchCriteria criteria,
        float[] queryVector,
        String tenantId
    );
}
~~~

Implementation chịu trách nhiệm:

- Chọn cách chạy hybrid theo version.
- Tạo lexical và vector branch.
- Áp dụng filter bắt buộc.
- Thực hiện RRF hoặc gọi retriever API.
- Giữ metadata cần thiết.
- Chuyển response Elasticsearch thành application result.

Service không cần biết retriever API hay cách fusion được triển khai ở tầng thấp.

## 13. semantic_text và inference do Elasticsearch quản lý

Một số phiên bản Elasticsearch cung cấp semantic_text để đơn giản hóa semantic search. Field này có thể tích hợp inference endpoint để tạo embedding cho nội dung và xử lý semantic query theo cấu hình của cluster.

Mô hình khái quát:

~~~text
Document text
     |
     v
Elasticsearch semantic field
     |
     v
Configured inference endpoint
     |
     v
Embedding + semantic indexing
~~~

Query:

~~~http
GET /products/_search
{
  "query": {
    "semantic": {
      "field": "semanticDescription",
      "query": "máy tính mỏng nhẹ phù hợp đi học"
    }
  }
}
~~~

Cú pháp, field type, inference configuration, model deployment và availability tùy version/distribution/license. Hãy kiểm tra cluster hỗ trợ semantic_text và semantic query tương ứng trước khi thiết kế ứng dụng dựa trên chúng.

### Dense vector tự quản lý và semantic_text khác nhau

| Tiêu chí | dense_vector | semantic_text |
|---|---|---|
| Tạo embedding | Thường do ứng dụng hoặc ingest pipeline quản lý | Có thể do inference integration quản lý |
| Kiểm soát vector | Rõ ràng, trực tiếp | Trừu tượng hóa nhiều chi tiết |
| Model lifecycle | Ứng dụng cần quản lý | Cần quản lý inference endpoint/model của cluster |
| Tùy biến pipeline | Linh hoạt | Phụ thuộc tính năng semantic field |
| Hybrid với lexical | Có thể kết hợp qua retriever/fusion | Có thể dùng cùng lexical branch theo API hỗ trợ |
| Portability | Cần mang theo model và vector schema | Gắn với feature set và inference setup của Elasticsearch |

semantic_text không có nghĩa Elasticsearch tự hiểu mọi nội dung mà không cần model. Vẫn cần inference model, endpoint và cấu hình tương ứng.

## 14. Chunking khi tìm kiếm tài liệu dài

Với tài liệu dài, một embedding cho toàn bộ document có thể làm mất chi tiết. Có thể chia nội dung thành các chunk rồi tạo vector cho từng chunk.

Ví dụ:

~~~text
Document
  |
  +-- Chunk 1 -> embedding 1
  +-- Chunk 2 -> embedding 2
  +-- Chunk 3 -> embedding 3
  +-- Chunk 4 -> embedding 4
~~~

Mỗi chunk thường cần metadata:

- documentId.
- chunkId hoặc vị trí.
- title.
- tenantId/permission scope.
- content.
- embedding.
- source/version.
- parent document reference.

Vector retrieval trả về chunk phù hợp. Ứng dụng có thể group theo documentId, lấy một số chunk tốt nhất hoặc rerank ở cấp document.

### Chọn kích thước chunk

Chunk quá lớn làm embedding pha trộn nhiều chủ đề. Chunk quá nhỏ có thể mất ngữ cảnh và tạo nhiều vector hơn. Có thể dùng overlap để giữ câu hoặc đoạn văn qua ranh giới chunk.

Kích thước và overlap phải được thử với corpus thật, model tokenizer và cách người dùng đặt câu hỏi. Không có một số token tối ưu cho mọi tài liệu.

### Deduplicate ở cấp document

Một tài liệu có nhiều chunk có thể chiếm nhiều vị trí trong vector candidate list. Nếu API trả danh sách tài liệu, cần gom các chunk theo document ID và định nghĩa cách tổng hợp score/rank.

Không đơn giản cộng score các chunk nếu chưa xác định semantics. Có thể dùng max score, top chunk, weighted aggregation hoặc reranker ở cấp document.

## 15. Filter, tenant và quyền truy cập trong hybrid search

Filter cần được áp dụng nhất quán cho mọi nhánh. Ví dụ status, category, time range và tenant scope phải không bị mất ở vector query trong khi vẫn có ở lexical query.

Đối với hệ thống nhiều tenant:

- Tenant ID được lấy từ principal đã xác thực.
- Lexical query có tenant filter.
- kNN query có pre-filter phù hợp.
- Application-side fusion chỉ hợp nhất hit thuộc cùng scope.
- Fetch theo ID sau fusion vẫn phải kiểm tra tenant ownership.

Không dùng routing như cơ chế authorization. Routing chọn shard; tenant filter và quyền truy cập mới giới hạn document được trả về.

### Pre-filter và post-filter trong kNN

Một filter được áp dụng trước ANN candidate selection có thể ảnh hưởng recall và số candidate cần tìm. Filter sau retrieval có thể khiến kết quả cuối ít hơn k nếu nhiều candidate bị loại.

Elasticsearch hỗ trợ các dạng filter trong kNN theo version và API. Kiểm tra semantics pre-filter/post-filter của endpoint đang dùng. Với tenant isolation, không được bỏ filter chỉ để cải thiện recall.

Nếu tập filter quá hẹp, có thể cần tăng candidate budget hoặc thiết kế index/partition phù hợp, nhưng vẫn phải giữ access scope.

## 16. Chọn cách kết hợp score và ranking

Có nhiều chiến lược kết hợp lexical và vector.

### RRF

Kết hợp theo rank, không cần chuẩn hóa raw score. Thường là điểm bắt đầu dễ đánh giá và ít nhạy với scale score.

### Weighted score combination

Có thể chuẩn hóa score rồi kết hợp:

\[
S(d) = \alpha \cdot S_{lexical}(d)
      + (1-\alpha) \cdot S_{vector}(d)
\]

Trong đó alpha điều chỉnh trọng số. Công thức chỉ có ý nghĩa khi hai score đã được chuẩn hóa/calibrate phù hợp. Nếu dùng raw BM25 và raw vector score, kết quả có thể bị một nhánh chi phối.

### Reranking

Lấy top candidates từ hybrid retrieval rồi dùng model reranker hoặc business rule để xếp hạng lại. Reranker thường tốn chi phí hơn nên chỉ áp dụng trên candidate set giới hạn.

Có thể kết hợp các tín hiệu:

- Lexical rank.
- Vector rank.
- Model reranker score.
- Exact SKU/name match.
- Popularity hoặc freshness.
- Business availability.
- Personalization signal đã được phép sử dụng.

Không để business boost làm kết quả vi phạm filter hoặc access policy. Filter bảo mật phải được áp dụng trước khi xếp hạng.

## 17. Pagination và candidate window

Pagination của hybrid search phức tạp hơn query đơn giản vì kết quả đã qua nhiều bước retrieval/fusion.

Cần phân biệt:

- k: số nearest neighbors trong vector branch.
- num_candidates: số vector candidate xem xét trên mỗi shard.
- rank_window_size: số kết quả mỗi retriever đưa vào fusion.
- size: số kết quả cuối trả cho client.

Nếu size = 20, không có nghĩa mỗi nhánh chỉ cần lấy 20 candidate. Một rank window lớn hơn có thể giúp fusion tìm document xuất hiện ở vị trí trung bình của cả hai nhánh.

### Trang sâu

Offset pagination trên kết quả hybrid có thể tốn kém hoặc không được hỗ trợ giống query thông thường tùy retriever API. Nếu cần duyệt sâu, hãy kiểm tra hỗ trợ PIT/search_after hoặc cursor với API hybrid cụ thể.

Không tự lấy top 20 của hai nhánh rồi tính trang 5 bằng cách bỏ 80 kết quả nếu candidate windows không đủ bao phủ. Response nên nói rõ pagination semantics và giới hạn.

Với ứng dụng search tương tác, thường ưu tiên top 10–50 kết quả và refinement query hơn là cho phép page rất sâu.

## 18. Hiệu năng và chi phí vận hành

Hybrid search có thêm chi phí:

- Tạo embedding cho query.
- Lưu vector và index vector.
- ANN candidate search.
- Chạy lexical query.
- Fusion hoặc reranking.
- Network và memory cho candidate list.
- Re-embedding khi model hoặc nội dung thay đổi.

Các yếu tố cần đo:

| Thành phần | Metric cần theo dõi |
|---|---|
| Embedding service | latency, timeout, error rate, queue |
| Lexical branch | latency, hit count, shard fan-out |
| Vector branch | latency, candidate count, recall estimate |
| Fusion | thời gian hợp nhất, candidate size |
| Reranker | latency, throughput, error rate |
| End-to-end | p50/p95/p99, timeout, result count |
| Index | vector count, disk, segment, indexing throughput |

### Caching query embedding

Có thể cache embedding của query lặp lại nếu privacy và freshness policy cho phép. Cache key phải tính đến model version và preprocessing version.

Không cache embedding chỉ theo raw query nếu cùng text nhưng dùng model/version khác. Cache cũng cần giới hạn dung lượng và TTL.

### Batch embedding

Khi ingest nhiều document, batch request tới model có thể hiệu quả hơn gọi từng document. Tuy nhiên, cần giới hạn batch size, retry và backpressure để tránh làm inference service quá tải.

### Vector storage và quantization

Một số Elasticsearch version hỗ trợ vector element type hoặc quantization/index options để giảm memory và disk. Những tùy chọn này có thể ảnh hưởng recall và yêu cầu cấu hình cụ thể. Đánh giá bằng benchmark trước khi bật; không coi quantization là tối ưu miễn phí.

## 19. Relevance evaluation

Hybrid search cần được đánh giá bằng bộ query đại diện và relevance judgments. Một truy vấn thành công về mặt kỹ thuật không chứng minh kết quả hữu ích.

Tạo tập đánh giá gồm:

- Query người dùng thực tế đã được xử lý quyền riêng tư.
- Document hoặc sản phẩm liên quan.
- Nhãn relevance theo mức độ.
- Nhóm truy vấn exact, semantic, mã kỹ thuật và truy vấn dài.
- Tenant/filter context phù hợp.
- Trường hợp không có kết quả phù hợp.

Metric phổ biến:

- **Recall@k:** tỷ lệ tài liệu liên quan được tìm thấy trong top k.
- **Precision@k:** tỷ lệ tài liệu trong top k thực sự liên quan.
- **MRR:** vị trí của kết quả liên quan đầu tiên.
- **nDCG@k:** chất lượng xếp hạng có xét mức độ relevance.
- **Latency p95/p99:** thời gian phản hồi ở tail.

So sánh ít nhất ba baseline:

1. Lexical only.
2. Vector only.
3. Hybrid (RRF hoặc chiến lược fusion khác).

Có thể thêm hybrid + reranker sau khi baseline có kết quả ổn định.

### Phân tích theo nhóm query

Một kết quả trung bình tốt có thể che giấu một nhóm query bị giảm chất lượng. Hãy phân tích riêng:

- Exact SKU/model.
- Brand/product name.
- Natural language intent.
- Synonym và cách diễn đạt địa phương.
- Query rất ngắn.
- Query nhiều điều kiện.
- Query tiếng Việt có dấu và không dấu nếu ứng dụng hỗ trợ.
- Query có typo.

Hybrid thường cải thiện semantic recall nhưng có thể làm exact match bị đẩy xuống nếu fusion/ranking không được điều chỉnh. Cần kiểm tra cả hai nhóm.

## 20. Tuning theo dữ liệu thực tế

Quy trình tuning có thể thực hiện theo vòng lặp:

1. Chốt tập query và relevance judgments.
2. Đo lexical baseline.
3. Đo vector baseline.
4. Thêm RRF với rank window và rank constant ban đầu.
5. Phân tích query mà hybrid cải thiện hoặc làm xấu đi.
6. Điều chỉnh field boost, candidate count và rank window.
7. Thử reranker nếu có đủ lợi ích.
8. Đo latency/cost cùng relevance.
9. Chạy shadow traffic hoặc A/B test.
10. Theo dõi drift khi corpus/model thay đổi.

Không tối ưu chỉ một metric. Tăng Recall@100 có thể không cải thiện top 10. Giảm latency bằng candidate count quá thấp có thể làm mất document quan trọng.

### Exact match boost

Nếu mã SKU hoặc tên chính xác phải đứng đầu, có thể thêm một lexical clause có boost cao hoặc rule ưu tiên exact match trước fusion. Cần test riêng để tránh một exact clause quá rộng làm mọi kết quả cùng score.

### Query rewriting

Có thể chuẩn hóa query, expand synonym hoặc tách entity trước khi retrieval. Giữ query gốc và query đã rewrite trong telemetry phù hợp để phân tích chất lượng, nhưng tránh log thông tin nhạy cảm không cần thiết.

## 21. Testing hybrid search

Một bộ test nên có nhiều cấp.

### Unit test

Mock EmbeddingService để trả vector xác định. Kiểm tra:

- Query text được chuyển đúng tới embedding service.
- Query criteria tạo lexical clauses cần thiết.
- Tenant/status filters được áp dụng.
- Fusion deduplicate theo đúng document identity.
- RRF tính rank đúng.
- Sort và response metadata được map đúng.
- Embedding dimension mismatch được phát hiện trước khi gửi query nếu có thể.

### Integration test với Elasticsearch

Dùng Elasticsearch version tương thích để kiểm tra:

- Mapping dense_vector đúng dimension và similarity.
- Vector indexing và kNN query hoạt động.
- Lexical query trả kết quả theo analyzer.
- Retriever API/RRF hoạt động nếu dùng.
- Filter được áp dụng cho cả hai nhánh.
- Kết quả không chứa document ngoài tenant.
- Score/rank metadata được map đúng.
- Query với vector sai dimension bị xử lý theo contract.

Không dùng một vector ngẫu nhiên rồi assert document đầu tiên nếu không có embedding fixture có ý nghĩa. Tạo vector test có quan hệ khoảng cách đã biết hoặc dùng model fixture ổn định.

### Contract test cho API

Xác nhận response envelope có:

- items đúng schema.
- pagination metadata.
- sort semantics.
- optional score/highlight nếu được yêu cầu.
- cursor hoặc facets nếu endpoint hỗ trợ.
- error response khi embedding service không khả dụng.
- không lộ raw vector hoặc internal index metadata ngoài contract.

### Test lỗi model

Mô phỏng:

- Timeout inference.
- Model endpoint unavailable.
- Response dimension sai.
- Model version không tương thích.
- Embedding trả NaN/Infinity hoặc giá trị không hợp lệ nếu client có thể gặp.

Không retry vô hạn. Nếu vector branch lỗi, chính sách fallback lexical-only phải được định nghĩa và thể hiện qua metric/response semantics.

## 22. Xử lý lỗi và fallback

Hybrid search phụ thuộc nhiều thành phần nên lỗi có thể xảy ra ở một nhánh.

| Lỗi | Hướng xử lý |
|---|---|
| Embedding service timeout | Retry giới hạn hoặc fallback lexical-only nếu policy cho phép |
| Vector dimension mismatch | Dừng query, ghi lỗi cấu hình/model |
| kNN field chưa mapping | Không retry; sửa mapping/index |
| Retriever API không hỗ trợ | Dùng API phù hợp version hoặc application-side fusion |
| Lexical branch lỗi | Báo lỗi hoặc degraded mode theo contract |
| Một nhánh trả rỗng | Vẫn có thể fusion nhánh còn lại nếu semantics được định nghĩa |
| Tenant filter thiếu ở một nhánh | Coi là lỗi correctness/security, không fallback bỏ filter |
| Reranker timeout | Có thể dùng thứ hạng hybrid ban đầu nếu fallback được công bố/quan sát |

Không trả response như thể kết quả là hybrid đầy đủ khi chỉ một nhánh hoạt động mà không ghi nhận degraded mode. Cần metric cho fallback count và error rate theo từng branch.

## 23. Các lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Vector query bị từ chối | Dimension không khớp mapping | Kiểm tra model output và dense_vector dims |
| Vector search trả kết quả khó hiểu | Model/index/query preprocessing không giống nhau | Đồng bộ model và preprocessing version |
| Exact SKU không đứng đầu | Vector rank lấn át lexical | Thêm exact lexical boost hoặc rule ưu tiên |
| Hybrid chậm hơn nhiều | Candidate window quá lớn hoặc embedding latency cao | Đo từng branch, tuning candidate và cache |
| RRF kết quả không như kỳ vọng | Một nhánh không có candidate đủ rộng | Điều chỉnh rank window và candidate count |
| Cộng score tạo ranking lệch | BM25 và vector score khác scale | Dùng RRF hoặc calibration |
| Kết quả thiếu sau filter | Filter áp dụng sau ANN hoặc chỉ một nhánh | Dùng filter đúng semantics trên cả hai branch |
| Có document tenant khác | Một nhánh thiếu tenant filter | Bắt buộc scope ở cả lexical và vector |
| Duplicate document trong response | Cùng ID xuất hiện ở hai nhánh | Deduplicate trước response mapping |
| Kết quả thay đổi sau deploy model | Embedding space thay đổi | Version hóa model và re-embed |
| Search theo tài liệu dài bỏ sót chi tiết | Một vector cho document quá dài | Chunking và aggregate theo parent |
| Trang sâu không ổn định | Candidate window và pagination không đủ | Dùng cursor/API hỗ trợ và giới hạn page depth |
| NativeQuery không có API retriever mong muốn | Spring Data/client version chưa expose feature | Dùng gateway Java API Client hoặc app-side fusion |

## 24. Checklist triển khai hybrid search

- [ ] Xác định truy vấn nào cần lexical, vector hoặc cả hai.
- [ ] Mapping text/keyword phù hợp với analyzer và exact filter.
- [ ] Chọn embedding model phù hợp ngôn ngữ và domain.
- [ ] Quản lý model version và preprocessing version.
- [ ] Dense vector dimension khớp model output.
- [ ] Chọn similarity metric đúng theo model.
- [ ] Tạo embedding ở index time và query time theo cùng pipeline.
- [ ] Đánh giá semantic_text nếu cluster hỗ trợ inference integration.
- [ ] Dùng kNN candidate count và k theo benchmark.
- [ ] Chọn RRF hoặc score fusion đã được calibration.
- [ ] Không cộng raw BM25 và vector score một cách tùy tiện.
- [ ] Kiểm tra retriever API và RRF support theo Elasticsearch version.
- [ ] Kiểm tra khả năng expose API tương ứng trong Spring Data release train.
- [ ] Nếu cần, cô lập direct client hoặc app-side fusion trong gateway.
- [ ] Áp dụng tenant/filter scope ở mọi retrieval branch.
- [ ] Deduplicate kết quả theo document identity.
- [ ] Định nghĩa pagination và cursor semantics.
- [ ] Có chiến lược chunking cho tài liệu dài.
- [ ] Theo dõi embedding, lexical, vector, fusion và end-to-end latency.
- [ ] Đánh giá Recall@k, Precision@k, MRR và nDCG.
- [ ] Test exact identifier cùng semantic intent.
- [ ] Test model timeout, dimension mismatch và degraded mode.
- [ ] Có kế hoạch re-embedding khi đổi model.

Keyword search tìm tốt những gì người dùng viết ra; vector search tìm nội dung gần nghĩa theo embedding; hybrid search kết hợp hai danh sách để tăng khả năng tìm đúng tài liệu trong nhiều kiểu truy vấn. Với Elasticsearch, có thể dùng retriever/RRF khi cluster hỗ trợ, hoặc hợp nhất hai nhánh ở service trên các phiên bản cũ hơn. Spring Data Elasticsearch cung cấp lớp mapping và truy cập, còn model embedding và chiến lược fusion cần được thiết kế rõ. Hãy giữ filter và tenant scope trên cả hai nhánh, version hóa embedding, đánh giá bằng tập query thực tế và cân bằng relevance với latency trước khi đưa hybrid search vào production.

