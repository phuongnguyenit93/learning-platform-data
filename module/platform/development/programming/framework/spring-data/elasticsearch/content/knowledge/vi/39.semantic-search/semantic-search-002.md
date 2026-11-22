# Embedding, dense_vector và số chiều dữ liệu

Tìm kiếm từ khóa thường dựa trên sự xuất hiện của từ hoặc cụm từ trong document. Cách này hiệu quả khi người dùng biết chính xác thuật ngữ cần tìm, nhưng có thể bỏ sót những tài liệu diễn đạt cùng một ý bằng từ khác. Tìm kiếm ngữ nghĩa (semantic search) bổ sung một cách biểu diễn nội dung theo ý nghĩa: mô hình embedding chuyển văn bản thành một vector số, và Elasticsearch tìm các vector gần nhau trong không gian nhiều chiều.

Trong Spring Data Elasticsearch, ứng dụng thường lưu vector embedding trong một field kiểu dense_vector, sau đó dùng k-nearest neighbors (kNN) để tìm các document có vector gần vector truy vấn. Để cách này hoạt động đúng, cần quản lý nhất quán:

- Embedding model và phiên bản model.
- Cách chuẩn hóa, chia đoạn và tiền xử lý nội dung.
- Số chiều (dimensions) của vector.
- Kiểu dữ liệu và mapping của field dense_vector.
- Hàm similarity hoặc distance.
- Cách tạo embedding cho document và cho query.
- Quy trình cập nhật, kiểm thử và xây lại index khi model thay đổi.

Số chiều không chỉ là một con số cấu hình. Nó là một phần của hợp đồng giữa embedding model, dữ liệu đã index và vector truy vấn. Vector có sai số chiều hoặc được tạo bởi model không tương thích có thể làm thao tác ghi/query thất bại hoặc tạo ra kết quả không có ý nghĩa.

## 1. Embedding là gì?

Embedding là một biểu diễn số của nội dung. Một mô hình embedding nhận văn bản, hình ảnh hoặc dữ liệu khác và tạo ra một vector gồm nhiều số thực. Trong tìm kiếm văn bản, vector thường được tạo từ một câu, đoạn văn hoặc document.

Ví dụ minh họa:

~~~text
"How do I reset my password?"
              |
              v
       Embedding model
              |
              v
[0.12, -0.08, 0.31, 0.44, ...]
              |
              v
         Dense vector
~~~

Hai câu có cách viết khác nhau nhưng cùng ý nghĩa có thể có vector gần nhau:

- "How can I reset my password?"
- "I forgot my password. How do I create a new one?"

Tìm kiếm ngữ nghĩa tận dụng khoảng cách hoặc độ tương đồng giữa các vector thay vì chỉ so khớp từ.

Embedding không phải bản tóm tắt có thể đọc trực tiếp. Mỗi phần tử trong vector không tương ứng đơn giản với một từ hoặc một đặc tính có tên. Ý nghĩa được phân bố trong toàn bộ vector và được học từ dữ liệu huấn luyện của model.

## 2. Embedding model quyết định vector

Ứng dụng không tự chọn tùy ý số chiều rồi yêu cầu model tạo ra vector có kích thước đó. Model có kiến trúc và cấu hình đầu ra riêng. Khi gọi model, nó trả về một vector với số chiều được xác định bởi model hoặc tùy chọn output dimension mà model hỗ trợ.

Ví dụ các kích thước thường gặp trong những model khác nhau có thể là 384, 512, 768, 1024 hoặc 1536. Đây chỉ là ví dụ; không được suy ra số chiều từ tên model hoặc từ một model khác cùng họ. Luôn đọc metadata và tài liệu của model đang dùng, hoặc kiểm tra độ dài vector trả về trong môi trường tích hợp.

### 2.1. Một model, một hợp đồng embedding

Với một model cụ thể, hợp đồng embedding cần xác định:

| Thuộc tính | Ý nghĩa |
|---|---|
| Model ID | Model nào tạo vector |
| Model revision | Phiên bản hoặc snapshot model |
| Dimensions | Số phần tử của vector |
| Input type | Văn bản, hình ảnh hoặc loại dữ liệu đầu vào |
| Preprocessing | Chuẩn hóa, loại bỏ markup, ngôn ngữ và quy tắc làm sạch |
| Chunking | Cách chia tài liệu dài thành đoạn |
| Normalization | Có chuẩn hóa vector về độ dài đơn vị hay không |
| Similarity | Cosine, dot product hoặc L2 |

Document embedding và query embedding phải tương thích với nhau. Nếu index document bằng model A nhưng tạo query vector bằng model B, cùng số chiều cũng không bảo đảm hai vector nằm trong cùng không gian ngữ nghĩa.

### 2.2. Document embedding và query embedding

Quy trình thường có hai nhánh:

~~~text
        Nội dung nguồn
              |
       Clean / chunk
              |
       Embedding model
              |
        Document vector
              |
       Elasticsearch index

        Câu truy vấn
              |
       Query preprocessing
              |
       Cùng embedding model
              |
         Query vector
              |
       Elasticsearch kNN
              |
       Search results
~~~

Trong một số hệ thống, model cung cấp chế độ encode riêng cho document và query (ví dụ prompt hoặc task type khác nhau). Khi đó cần dùng đúng chế độ theo hướng dẫn model. Hai nhánh vẫn phải thuộc cùng một embedding space tương thích.

Không nên tự thay prompt, pooling strategy hoặc preprocessing ở một nhánh mà không đánh giá lại chất lượng tìm kiếm.

## 3. Số chiều dữ liệu có ý nghĩa gì?

Vector có D chiều là một danh sách gồm D giá trị số:

~~~text
v = [v1, v2, v3, ..., vD]
~~~

Nếu model trả về 768 phần tử, vector đó có 768 dimensions. Field dense_vector được khai báo với số chiều tương ứng. Mỗi document được index vào field phải có đúng số phần tử đó; vector truy vấn cũng phải có cùng số chiều.

Ví dụ:

~~~json
{
  "embedding": [0.12, -0.08, 0.31, 0.44]
}
~~~

Vector trong ví dụ có 4 chiều. Mapping khai báo dims là 4. Nếu một document gửi 3 hoặc 5 phần tử, Elasticsearch có thể từ chối document. Nếu query vector có độ dài khác mapping, truy vấn cũng không hợp lệ.

### 3.1. Dimensions là hợp đồng schema

Số chiều ảnh hưởng tới:

- Mapping của index.
- Kích thước lưu trữ cho mỗi vector.
- Chi phí tính similarity.
- Bộ nhớ và dung lượng index.
- Cấu hình thuật toán approximate nearest neighbor.
- Khả năng tương thích giữa dữ liệu cũ và dữ liệu mới.

Với vector float32 chưa xét overhead, D chiều chiếm xấp xỉ 4 × D bytes cho phần giá trị. Ví dụ 768 chiều khoảng 3 KB mỗi vector, còn 1536 chiều khoảng 6 KB mỗi vector. Đây là ước tính phần payload số học; dung lượng thực tế còn phụ thuộc metadata, cấu trúc index, graph, quantization và overhead của Elasticsearch/Lucene.

### 3.2. Nhiều chiều hơn không tự động tốt hơn

Vector nhiều chiều có thể mang nhiều thông tin hơn, nhưng cũng làm tăng chi phí lưu trữ, indexing và tìm kiếm. Chất lượng phụ thuộc model, dữ liệu, nhiệm vụ và cách đánh giá; không thể kết luận 1536 chiều luôn tốt hơn 384 chiều.

Khi chọn model/dimensions, nên đánh giá:

- Recall@k hoặc metric retrieval phù hợp.
- NDCG/MRR nếu thứ tự kết quả quan trọng.
- Độ trễ p50/p95/p99.
- Throughput và chi phí embedding.
- Dung lượng index và memory.
- Chất lượng trên ngôn ngữ và domain thực tế.

Chọn cấu hình đáp ứng chất lượng và SLA với chi phí chấp nhận được.

## 4. dense_vector trong Elasticsearch

Elasticsearch có field type dense_vector để lưu vector số có độ dài cố định. Mapping khai báo field, số chiều và các tùy chọn similarity/index phù hợp phiên bản.

Ví dụ mapping:

~~~json
PUT products-semantic-v1
{
  "mappings": {
    "properties": {
      "productId": {
        "type": "keyword"
      },
      "name": {
        "type": "text"
      },
      "embedding": {
        "type": "dense_vector",
        "dims": 4,
        "index": true,
        "similarity": "cosine"
      }
    }
  }
}
~~~

Ví dụ này dùng vector 4 chiều để minh họa. Trong ứng dụng thật, thay dims bằng đúng số chiều của model. Các thuộc tính dense_vector và giá trị mặc định thay đổi theo phiên bản Elasticsearch; khai báo rõ cấu hình cần thiết và đối chiếu tài liệu của cluster đang chạy.

### 4.1. dims

dims là số chiều của vector. Đây phải là số chiều model thực sự trả về. Không được chọn số chiều theo ý muốn chỉ để khớp một mapping có sẵn.

Trước khi index, ứng dụng có thể kiểm tra:

~~~java
if (embedding == null || embedding.length != EXPECTED_DIMENSIONS) {
    throw new IllegalArgumentException(
            "Embedding dimension does not match index mapping"
    );
}
~~~

Kiểm tra ở application layer giúp phát hiện lỗi gần nơi tạo dữ liệu. Elasticsearch vẫn là lớp bảo vệ cuối cùng cho mapping.

### 4.2. index

Tùy phiên bản và cấu hình, dense_vector có thể được lưu để dùng trong script scoring hoặc được index cho approximate kNN. Khi cần kNN hiệu quả trên tập dữ liệu lớn, field cần được cấu hình theo khả năng vector indexing của phiên bản đang dùng.

Không nên dựa vào default index nếu hệ thống cần hành vi ổn định qua nâng cấp. Hãy khai báo rõ và xác nhận mapping thực tế sau khi tạo index.

### 4.3. similarity

Các lựa chọn thường gặp:

- cosine: so sánh góc giữa hai vector.
- dot_product: tích vô hướng; yêu cầu về chuẩn hóa phụ thuộc loại vector và cách sử dụng.
- l2_norm: dựa trên khoảng cách Euclidean.

Không chọn similarity chỉ theo tên gọi. Phải dùng hàm phù hợp với model và cách vector được chuẩn hóa. Nếu model khuyến nghị cosine similarity, dùng cosine hoặc lựa chọn tương đương được tài liệu model/Elasticsearch hỗ trợ.

## 5. Cosine, dot product và L2

### 5.1. Cosine similarity

Cosine similarity đo cosine của góc giữa hai vector:

\[
\operatorname{cosine}(a,b)=
\frac{a \cdot b}{\|a\|\|b\|}
\]

Giá trị lớn hơn thường biểu thị hướng vector gần nhau hơn. Cosine ít phụ thuộc độ dài vector hơn dot product vì đã chuẩn hóa theo norm.

### 5.2. Dot product

Dot product:

\[
a \cdot b = \sum_{i=1}^{D} a_i b_i
\]

Nếu hai vector đã được chuẩn hóa L2 về norm bằng 1, dot product bằng cosine similarity. Nếu không chuẩn hóa, độ lớn vector cũng ảnh hưởng score.

Một số model được huấn luyện để dùng dot product trên vector đã chuẩn hóa hoặc theo một scoring convention cụ thể. Hãy theo hướng dẫn model.

### 5.3. L2 distance

Khoảng cách Euclidean:

\[
\operatorname{L2}(a,b)=
\sqrt{\sum_{i=1}^{D}(a_i-b_i)^2}
\]

Khoảng cách càng nhỏ thì vector càng gần. Khi sử dụng L2, cần hiểu cách Elasticsearch chuyển distance thành _score trong kết quả search; score được trả về không nhất thiết chính là khoảng cách thô.

### 5.4. Không so sánh score tùy tiện

Score của cosine, dot product và L2 có thể được biến đổi để phù hợp với cơ chế scoring của Elasticsearch. Không nên so sánh trực tiếp một score giữa hai embedding model khác nhau, hai similarity function khác nhau, hai index có cấu hình vector khác nhau hoặc hai query có cách chuẩn hóa khác nhau.

Để đánh giá, dùng ranking metrics trên bộ query/document có nhãn hoặc kết quả đánh giá thực tế, thay vì đặt một ngưỡng score chung cho mọi model.

## 6. Khai báo dense_vector trong Spring Data Elasticsearch

Tạo một class riêng cho search document:

~~~java
@Document(indexName = "products-semantic-v1")
public class ProductVectorDocument {

    @Id
    private String id;

    @Field(type = FieldType.Keyword)
    private String productId;

    @Field(type = FieldType.Text)
    private String name;

    @Field(type = FieldType.Dense_Vector, dims = 4, similarity = "cosine")
    private float[] embedding;

    @Field(type = FieldType.Keyword)
    private String embeddingModel;

    @Field(type = FieldType.Keyword)
    private String embeddingVersion;

    // getters and setters
}
~~~

Đây là ví dụ mapping theo API Spring Data Elasticsearch có hỗ trợ FieldType.Dense_Vector, dims và similarity. Tên enum/annotation attributes và khả năng ánh xạ kiểu Java phụ thuộc release train. Kiểm tra Javadoc của dependency đang dùng; một số phiên bản có thể hỗ trợ float[], List<Float> hoặc kiểu vector khác với giới hạn riêng.

Nếu phiên bản Spring Data chưa expose thuộc tính mapping cần thiết, có thể quản lý index mapping bằng JSON/index template và dùng client phù hợp để thực thi truy vấn. Điều quan trọng là mapping thực tế trên Elasticsearch phải khớp với vector được ghi.

### 6.1. Lưu model metadata cùng document

Ngoài vector, nên lưu metadata giúp quản lý nguồn gốc:

- embeddingModel: định danh model.
- embeddingVersion: revision hoặc phiên bản embedding pipeline.
- sourceVersion: version của dữ liệu nguồn.
- chunkId: định danh đoạn nếu document được chia chunk.
- contentHash: hash nội dung đã embed để tránh tính lại khi nội dung không đổi.

Không nhất thiết mọi metadata đều cần đưa vào Elasticsearch. Nhưng hệ thống cần một nơi có thể xác định vector được tạo từ model và nội dung nào.

### 6.2. Không dùng cùng field cho các model không tương thích

Nếu model A trả 768 chiều và model B trả 1536 chiều, không thể ghi cả hai vào cùng field dense_vector đã khai báo một dims cố định.

Ngay cả khi A và B cùng trả 768 chiều, không nên trộn vector của chúng trong một field như thể chúng cùng một không gian. Khoảng cách giữa hai vector chỉ có ý nghĩa khi chúng được tạo theo một embedding space tương thích.

## 7. Tạo embedding và kiểm tra trước khi lưu

Embedding thường được tạo bởi một model service hoặc thư viện ML. Spring Data Elasticsearch chịu trách nhiệm lưu và truy vấn document; nó không tự động biến nội dung thành embedding nếu ứng dụng chưa tích hợp model.

Có thể định nghĩa abstraction:

~~~java
public interface EmbeddingService {

    EmbeddingResult embedDocument(String text);

    EmbeddingResult embedQuery(String text);
}

public record EmbeddingResult(
        float[] vector,
        String model,
        String modelVersion
) {
}
~~~

Service gọi model:

~~~java
EmbeddingResult result = embeddingService.embedDocument(
        product.getName() + " " + product.getDescription()
);

if (result.vector().length != EXPECTED_DIMENSIONS) {
    throw new IllegalStateException("Unexpected embedding dimensions");
}

ProductVectorDocument document = new ProductVectorDocument();
document.setId(product.getId().toString());
document.setProductId(product.getId().toString());
document.setName(product.getName());
document.setEmbedding(result.vector());
document.setEmbeddingModel(result.model());
document.setEmbeddingVersion(result.modelVersion());

elasticsearchOperations.save(document);
~~~

Tên method và class là ví dụ domain. Trong production, cần xử lý lỗi model service, timeout, rate limit, batch request, retry có giới hạn và logging phù hợp.

### 7.1. Validate vector

Ngoài độ dài, nên kiểm tra:

- Vector không null.
- Số chiều đúng.
- Không chứa NaN hoặc Infinity.
- Giá trị nằm trong miền model cho phép.
- Norm có hợp lệ nếu pipeline yêu cầu normalized vector.
- Model/version đúng với index đang ghi.

Ví dụ:

~~~java
static void validateEmbedding(float[] vector, int dimensions) {
    if (vector == null || vector.length != dimensions) {
        throw new IllegalArgumentException("Invalid embedding dimensions");
    }

    for (float value : vector) {
        if (!Float.isFinite(value)) {
            throw new IllegalArgumentException(
                    "Embedding contains a non-finite value"
            );
        }
    }
}
~~~

Nếu model tạo vector có norm bằng 0 hoặc có quy tắc normalization cụ thể, cần kiểm tra theo contract của model. Không tự normalize nếu model đã xử lý hoặc nếu việc đó làm sai semantics.

### 7.2. Không tạo embedding trong mỗi lần đọc search

Embedding cho document nên được tạo khi nội dung được tạo/cập nhật hoặc qua pipeline batch. Query embedding được tạo khi người dùng tìm kiếm. Không gọi model để tạo lại embedding của mọi document mỗi khi chạy một search request.

Với query phổ biến, có thể cache query embedding nếu chính sách dữ liệu và latency cho phép. Cache key phải bao gồm model version và preprocessing version để tránh dùng vector được tạo bởi pipeline cũ.

## 8. Index document có vector

Ví dụ document:

~~~json
{
  "productId": "p-100",
  "name": "Wireless Keyboard",
  "embedding": [0.12, -0.08, 0.31, 0.44],
  "embeddingModel": "catalog-embed",
  "embeddingVersion": "v1"
}
~~~

Ứng dụng có thể lưu bằng repository:

~~~java
public interface ProductVectorRepository
        extends ElasticsearchRepository<ProductVectorDocument, String> {
}
~~~

Hoặc qua ElasticsearchOperations:

~~~java
productVectorRepository.save(document);

// Tương đương use case ghi qua operations:
elasticsearchOperations.save(document);
~~~

Repository save thuận tiện cho CRUD. Khi cần bulk indexing, custom routing hoặc API cụ thể, ElasticsearchOperations hay Elasticsearch Java Client có thể phù hợp hơn.

Không tạo embedding ngay bên trong entity setter. Việc gọi model là một tác vụ I/O có thể thất bại và tốn thời gian; nên đặt trong application service hoặc background projection pipeline.

## 9. Truy vấn kNN bằng vector

Sau khi có query embedding, Elasticsearch có thể tìm k vector gần nhất.

Ví dụ Search API:

~~~http
POST /products-semantic-v1/_search
Content-Type: application/json

{
  "knn": {
    "field": "embedding",
    "query_vector": [0.10, -0.07, 0.30, 0.42],
    "k": 10,
    "num_candidates": 100
  },
  "_source": [
    "productId",
    "name",
    "embeddingModel",
    "embeddingVersion"
  ]
}
~~~

k là số kết quả lân cận mong muốn. num_candidates điều khiển số ứng viên được xem xét trong quá trình tìm kiếm approximate kNN theo shard. Tăng num_candidates thường có thể cải thiện recall nhưng tăng chi phí và latency. Hãy đo trên dữ liệu thật.

Các tham số và semantics cụ thể phụ thuộc phiên bản Elasticsearch. Xác nhận API kNN được cluster hỗ trợ trước khi thiết kế request.

### 9.1. Gọi qua Elasticsearch Java Client

Với Elasticsearch Java API Client 8.x có hỗ trợ KnnSearch, cấu trúc lời gọi có dạng:

~~~java
SearchResponse<ProductVectorDocument> response =
        elasticsearchClient.search(search -> search
                .index("products-semantic-v1")
                .knn(knn -> knn
                        .field("embedding")
                        .queryVector(toFloatList(queryVector))
                        .k(10)
                        .numCandidates(100)
                ),
                ProductVectorDocument.class
        );
~~~

Đây là cấu trúc minh họa; builder method và kiểu query vector phải khớp phiên bản Java Client. Nếu đang dùng Spring Data Elasticsearch NativeQuery, hãy dùng API knn search được release train đó hỗ trợ hoặc custom repository gọi Java Client. Không giả định mọi phiên bản Spring Data có cùng builder method.

### 9.2. Filter trong kNN

Thường cần lọc theo status, tenant, category hoặc quyền truy cập. Một số phiên bản hỗ trợ filter trong kNN request để filter tham gia vào quá trình tìm ứng viên. Có thể kết hợp lexical query và vector query theo cơ chế hybrid search.

Ví dụ khái niệm:

~~~json
{
  "knn": {
    "field": "embedding",
    "query_vector": [0.10, -0.07, 0.30, 0.42],
    "k": 10,
    "num_candidates": 100,
    "filter": {
      "bool": {
        "filter": [
          { "term": { "status": "ACTIVE" } },
          { "term": { "categoryId": "cat-7" } }
        ]
      }
    }
  }
}
~~~

Không để client tự quyết định tenant/security filter. Các điều kiện bảo mật phải được thêm ở server-side và áp dụng cho mọi nhánh tìm kiếm.

## 10. Approximate kNN và exact scoring

Tìm nearest neighbors có thể được thực hiện theo hai hướng:

**Exact scoring:** tính điểm cho từng document trong tập được xét, ví dụ dùng script score. Kết quả chính xác trên tập đó nhưng có thể tốn kém khi tập dữ liệu lớn.

**Approximate nearest neighbors (ANN):** dùng cấu trúc index vector, thường là HNSW, để tìm nhanh các lân cận gần nhất với khả năng bỏ sót một số kết quả so với exact search.

| Cách | Ưu điểm | Chi phí/giới hạn |
|---|---|---|
| Exact script scoring | Có thể tính chính xác trên tập candidate/filter đã chọn | Tốn CPU khi phải chấm điểm rất nhiều document |
| Approximate kNN | Tìm nhanh trên tập vector lớn | Có trade-off giữa recall, latency, memory và indexing cost |

Với ANN, HNSW tạo graph liên kết các vector gần nhau. Query đi qua graph để tìm candidate thay vì tính mọi khoảng cách. Các tham số index như m, ef_construction hoặc index_options phụ thuộc phiên bản và cấu hình Elasticsearch/Lucene.

Không nên chọn num_candidates chỉ dựa trên một query demo. Tạo bộ benchmark có query đại diện, ground truth hoặc exact baseline, rồi so sánh recall@k và latency.

### 10.1. Khi nào dùng exact scoring?

Exact scoring có thể phù hợp khi tập dữ liệu nhỏ, bộ lọc thu hẹp candidate xuống số lượng thấp, cần đối chiếu chất lượng ANN hoặc cần một query script đặc biệt mà ANN không biểu diễn được.

Với dữ liệu lớn, chạy script similarity trên toàn bộ index có thể rất tốn tài nguyên. Nên lọc candidate hợp lý và benchmark trước.

## 11. Hybrid search: kết hợp từ khóa và vector

Vector search hiểu ngữ nghĩa nhưng có thể không ưu tiên chính xác mã SKU, tên riêng, số model hoặc cụm từ bắt buộc. Lexical search như BM25 làm tốt các trường hợp khớp từ. Hybrid search kết hợp hai nguồn ranking.

Ví dụ:

- Query: "keyboard for quiet office".
- Vector search tìm các mô tả như "silent typing" hoặc "low-noise keys".
- BM25 tìm document có từ "keyboard", "office" và thuật ngữ cụ thể.
- Hệ thống kết hợp hai danh sách để xếp hạng cuối.

Một cách kết hợp là Reciprocal Rank Fusion (RRF), dựa trên vị trí của document trong từng danh sách:

\[
\operatorname{RRF}(d)=
\sum_{r \in R}
\frac{1}{k_0+\operatorname{rank}_r(d)}
\]

RRF tránh phải chuẩn hóa trực tiếp điểm BM25 và điểm vector vốn có thang điểm khác nhau. Elasticsearch hỗ trợ các cách kết hợp lexical và kNN tùy phiên bản; hãy kiểm tra semantics của query-level kNN, top-level knn và retriever API.

Không cộng trực tiếp BM25 score và cosine score bằng một hệ số tùy ý rồi coi đó là ranking ổn định. Nếu dùng weighted score, cần hiệu chỉnh trên tập đánh giá.

## 12. Chunking tài liệu dài

Một document dài có thể chứa nhiều chủ đề. Tạo một embedding duy nhất cho toàn bộ nội dung có thể làm mờ các đoạn quan trọng. Chunking chia tài liệu thành các đoạn nhỏ rồi tạo embedding cho từng đoạn.

Ví dụ:

~~~text
Long document
   |
   +--> Chunk 1: overview
   |
   +--> Chunk 2: installation
   |
   +--> Chunk 3: troubleshooting
   |
   +--> Chunk 4: examples
~~~

Một vector document có thể có:

~~~json
{
  "documentId": "guide-42",
  "chunkId": "guide-42-03",
  "chunkIndex": 3,
  "title": "Troubleshooting",
  "content": "When the client cannot connect...",
  "embedding": [0.12, -0.08, 0.31, 0.44]
}
~~~

Khi trả kết quả, ứng dụng có thể gom chunk theo document ID, lấy chunk tốt nhất hoặc dùng reranker. Cần lưu chunk index và metadata để hiển thị đúng đoạn trích và liên kết tới nguồn.

### 12.1. Chọn kích thước chunk

Chunk quá nhỏ có thể mất ngữ cảnh; chunk quá lớn có thể vượt token limit hoặc trộn nhiều chủ đề. Chọn dựa trên token limit của model, cấu trúc tài liệu, loại query của người dùng, overlap giữa các chunk và chất lượng retrieval trên tập query thực tế.

Không dùng số ký tự cố định như thể tương đương token ở mọi ngôn ngữ. Tokenization phụ thuộc model và ngôn ngữ. Nên chia theo heading/paragraph trước rồi áp dụng token limit để giữ cấu trúc nội dung.

### 12.2. Overlap

Overlap giữ một phần nội dung cuối chunk trước ở đầu chunk sau để giảm mất ngữ cảnh tại ranh giới. Overlap quá lớn tạo nhiều bản sao gần giống nhau, tăng dung lượng index và làm kết quả search trùng lặp.

Đánh giá overlap bằng retrieval metrics và kiểm tra duplicate result. Có thể collapse kết quả theo document ID hoặc dùng reranking để chọn các chunk đa dạng.

## 13. Quản lý model version và đổi số chiều

Giả sử index hiện tại dùng model A với 768 chiều. Sau đó đội phát triển chọn model B với 1024 chiều. Không thể chỉ đổi annotation dims rồi ghi vector mới vào index cũ:

- Mapping cũ vẫn khai báo 768 chiều.
- Document cũ chứa vector 768 chiều.
- Query vector mới có 1024 chiều.
- Vector của model A và B không cùng embedding space, kể cả khi cùng dimensions.

Chiến lược an toàn thường là tạo index version mới:

~~~text
products-vector-v1
  model A
  dims = 768
        |
        v
Build products-vector-v2
  model B
  dims = 1024
        |
        v
Backfill all documents
        |
        v
Validate retrieval quality
        |
        v
Switch semantic-search alias
~~~

### 13.1. Gắn version với vector

Quản lý ít nhất model identifier và revision, dimension, preprocessing/chunking version, similarity function, index mapping version và thời điểm tạo hoặc source version.

Có thể đặt các metadata này trong document, index settings/alias convention hoặc một registry của ứng dụng. Không dựa vào tên index duy nhất nếu cần audit vector được tạo bởi model nào.

### 13.2. Không trộn vector của model khác nhau

Hai model có thể cùng trả 768 chiều nhưng không có nghĩa vector của chúng có thể so sánh. Model học không gian biểu diễn riêng. KNN giữa vector model A và query vector model B sẽ trả một ranking số học, nhưng ranking đó không có đảm bảo ngữ nghĩa.

Giữ mỗi embedding space trong index/field riêng. Nếu phải chạy migration dần, có thể duy trì hai index và định tuyến query tới index tương ứng với model.

### 13.3. Re-embedding

Khi đổi model hoặc preprocessing, cần tạo lại embedding cho dữ liệu cũ. Quy trình:

1. Chốt model/version và dimensions mới.
2. Tạo index mới với mapping tương ứng.
3. Backfill nội dung nguồn theo batch.
4. Gọi embedding service và kiểm tra vector.
5. Bulk index, lưu checkpoint và xử lý item failure.
6. Replay các thay đổi phát sinh trong lúc backfill.
7. Đánh giá retrieval quality và latency.
8. Chuyển alias/query routing.
9. Giữ index cũ trong thời gian rollback.

Không tính embedding mới rồi ghi đè dần vào index cũ nếu query vẫn tạo vector theo model cũ. Trong giai đoạn migration, document và query phải đi theo cùng model version.

## 14. Kiểm thử dimensions và mapping

Nên có unit test cho embedding contract:

~~~java
@Test
void rejectsEmbeddingWithWrongDimensions() {
    float[] vector = {0.1f, 0.2f, 0.3f};

    assertThatThrownBy(
            () -> validateEmbedding(vector, 4)
    ).isInstanceOf(IllegalArgumentException.class);
}
~~~

Integration test với Elasticsearch thật cần xác nhận:

- Index được tạo với dense_vector và dims mong đợi.
- Document đúng chiều được index thành công.
- Document sai chiều bị từ chối.
- Query vector sai chiều bị từ chối.
- Similarity/index options đúng theo mapping.
- kNN trả kết quả phù hợp trên fixture nhỏ.

Có thể đọc mapping:

~~~http
GET /products-semantic-v1/_mapping
~~~

Kiểm tra field embedding có type dense_vector, dims đúng và similarity/index options như thiết kế. Đừng chỉ kiểm tra annotation Java vì index đã tồn tại có thể giữ mapping cũ.

### 14.1. Test nội dung vector

Không nhất thiết assert toàn bộ vector embedding bằng một mảng số cố định nếu model service có thể cập nhật hoặc kết quả không deterministic hoàn toàn. Thay vào đó:

- Test dimension và giá trị hữu hạn.
- Test model ID/version.
- Test contract với fixture hoặc mocked embedding service ở unit test.
- Dùng integration/acceptance test để đánh giá ranking trên bộ query/document đã biết.

Nếu cần test tái lập tuyệt đối, dùng model snapshot cố định và fixture vector đã được version hóa.

## 15. Đánh giá chất lượng semantic retrieval

Một truy vấn trả về 10 kết quả chưa chứng minh search tốt. Cần bộ dữ liệu đánh giá gồm query và document liên quan đã được gán nhãn.

Các metric phổ biến:

| Metric | Câu hỏi |
|---|---|
| Recall@k | Trong k kết quả đầu, hệ thống tìm được bao nhiêu tài liệu liên quan? |
| Precision@k | Bao nhiêu kết quả đầu thực sự liên quan? |
| MRR | Kết quả liên quan đầu tiên xuất hiện ở vị trí nào? |
| NDCG@k | Ranking có ưu tiên tài liệu liên quan hơn không, kể cả relevance nhiều mức? |
| p95 latency | 95% query hoàn tất trong bao lâu? |

Đánh giá trên query đa dạng: câu hỏi tự nhiên, từ đồng nghĩa, viết sai chính tả, tên riêng, mã sản phẩm, tiếng Việt có dấu/không dấu và truy vấn kết hợp filter.

Nếu có hybrid search, so sánh BM25 baseline, vector kNN, hybrid/RRF và hybrid có reranking (nếu dùng).

Đừng chỉ chọn model có demo đẹp. Model tốt phải cải thiện metric trên dữ liệu domain và vẫn đáp ứng latency/cost.

## 16. Vận hành embedding pipeline

Embedding service là một dependency bên ngoài hoặc một workload ML riêng. Cần xử lý timeout và retry có giới hạn, rate limit và quota, batch size, queue/backpressure, caching theo content hash và model version, dead-letter cho document không thể embed, theo dõi số lượng embedding pending/failed và bảo vệ dữ liệu nhạy cảm trước khi gửi tới model.

Không gọi embedding API trong transaction database dài. Có thể ghi event/outbox rồi worker tạo embedding và cập nhật projection. Nếu cần người dùng thấy kết quả ngay, thiết kế trạng thái như EMBEDDING_PENDING và cập nhật search document sau khi vector sẵn sàng.

### 16.1. Tránh embed lại khi nội dung không đổi

Tạo hash từ nội dung đã chuẩn hóa và metadata pipeline:

~~~text
content hash
  + model version
  + preprocessing version
  + chunking version
        |
        v
embedding cache key
~~~

Nếu các thành phần không đổi, có thể tái sử dụng embedding cũ. Khi model hoặc preprocessing đổi, cache key đổi để tránh trả vector sai phiên bản.

### 16.2. Bảo vệ dữ liệu

Văn bản gửi đến embedding provider có thể chứa dữ liệu cá nhân, thông tin nội bộ hoặc bí mật kinh doanh. Xác định dữ liệu nào được phép gửi, có cần redaction hay không, chính sách lưu trữ của provider và quyền truy cập vào vector index.

Embedding không nên mặc định được xem là dữ liệu vô hại chỉ vì không đọc trực tiếp như văn bản. Nó vẫn có thể là dữ liệu suy ra từ nội dung nguồn và cần được bảo vệ theo chính sách dữ liệu của ứng dụng.

## 17. Các lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| Index document báo vector dimension mismatch | Vector không đúng dims của mapping | Kiểm tra model output và index schema |
| kNN query báo sai số chiều | Query embedding khác dims | Dùng đúng model/index version |
| Vector cùng chiều nhưng kết quả kém | Document và query dùng model khác nhau | Đồng nhất embedding space |
| Search result thay đổi sau khi nâng model | Embedding space hoặc preprocessing thay đổi | Re-embed và đánh giá ranking |
| kNN chậm khi dữ liệu tăng | Candidate count, graph, filter hoặc tài nguyên | Benchmark ANN, shard và index options |
| Exact script score quá chậm | Tính similarity trên quá nhiều document | Thu hẹp candidate hoặc dùng ANN |
| Kết quả thiếu nội dung ở tài liệu dài | Một vector cho toàn bộ document làm mất chi tiết | Chunking và lưu chunk metadata |
| Nhiều kết quả trùng một tài liệu | Nhiều chunk gần nhau cùng đứng đầu | Collapse/group hoặc rerank |
| Score không so sánh được giữa model | Thang điểm và similarity khác nhau | Đánh giá bằng ranking metrics |
| Model service quá tải | Gọi embed đồng bộ, không batch/backpressure | Queue, batch, rate limit và retry |

## 18. Quy trình triển khai semantic search

1. Xác định use case và bộ query/document đánh giá.
2. Chọn embedding model phù hợp ngôn ngữ và domain.
3. Xác định model revision, preprocessing, chunking và dimensions.
4. Chọn similarity theo hướng dẫn model.
5. Tạo index với dense_vector mapping rõ ràng.
6. Tạo class search document riêng trong Spring Data Elasticsearch.
7. Tạo embedding qua service abstraction và validate vector.
8. Index document kèm model/version metadata.
9. Tạo query embedding bằng cùng embedding space.
10. Chạy kNN và áp dụng filter bảo mật/tenant.
11. Đánh giá Recall@k, NDCG/MRR và latency.
12. Cân nhắc hybrid search khi lexical match vẫn quan trọng.
13. Theo dõi embedding pipeline, index health và retrieval quality.
14. Khi đổi model/dimensions, tạo index version mới, re-embed và chuyển alias.

## 19. Kết luận

Embedding biểu diễn nội dung thành vector số để tìm kiếm theo mức độ gần nhau về ngữ nghĩa. Elasticsearch lưu các vector này trong field dense_vector và hỗ trợ kNN, nhưng chất lượng và tính hợp lệ phụ thuộc vào embedding model, preprocessing, số chiều và similarity được chọn.

Dimensions là một phần của schema: vector document và query phải có cùng số chiều, đồng thời phải thuộc cùng embedding space. Hai model cùng số chiều vẫn có thể không tương thích. Vì vậy, lưu model/version metadata, validate vector trước khi index và không trộn vector từ các model khác nhau trong cùng không gian tìm kiếm.

Trong Spring Data Elasticsearch, tạo search document riêng có field dense vector, quản lý mapping theo phiên bản và dùng repository/ElasticsearchOperations hoặc Java Client phù hợp release train để ghi và truy vấn. Đánh giá ANN bằng recall và latency trên dữ liệu thực, kết hợp BM25 khi cần tìm chính xác thuật ngữ, và dùng chunking cho tài liệu dài. Khi đổi model hoặc số chiều, xây index mới, re-embed dữ liệu, kiểm tra chất lượng rồi chuyển alias để giữ tính nhất quán giữa document vector và query vector.
