# Độ tương đồng, kNN và đánh đổi giữa tốc độ với độ chính xác

Tìm kiếm vector biểu diễn mỗi document và câu truy vấn thành một dãy số (embedding), sau đó xếp hạng document theo mức gần nhau của hai vector. Elasticsearch hỗ trợ nhiều phép đo độ tương đồng và hai hướng tìm kiếm chính: tìm kiếm chính xác trên toàn bộ tập document phù hợp (exact kNN) và tìm kiếm gần đúng bằng cấu trúc chỉ mục như HNSW (approximate kNN).

Exact search cho kết quả đúng theo metric đã chọn nhưng phải chấm điểm mọi vector trong tập ứng viên. Approximate kNN bỏ qua phần lớn vector để giảm độ trễ, đổi lại có thể bỏ lỡ một số hàng xóm gần nhất. Trong Elasticsearch, `k` xác định số hàng xóm cần lấy, còn `num_candidates` điều khiển lượng ứng viên được khám phá trên mỗi shard. Tăng `num_candidates` thường cải thiện recall nhưng làm truy vấn chậm hơn.

Spring Data Elasticsearch cung cấp `FieldType.Dense_Vector`, `KnnSimilarity` và `NativeQuery.withKnnSearches(...)` để khai báo field và gửi truy vấn kNN. Việc chọn metric, embedding model, kích thước vector, cấu hình HNSW và ngưỡng candidate cần được đánh giá cùng dữ liệu thực tế.

## 1. Vector similarity và k-nearest neighbors

Một embedding là vector số biểu diễn đặc trưng ngữ nghĩa của văn bản, hình ảnh hoặc dữ liệu khác. Ví dụ một model có thể chuyển câu “máy tính xách tay nhẹ” thành vector 384 chiều:

~~~text
[0.12, -0.08, 0.31, ..., -0.04]
~~~

Document và query được đưa qua cùng một embedding model để tạo vector trong cùng không gian. Hệ thống đo khoảng cách hoặc độ tương đồng giữa query vector và document vector, sau đó xếp hạng document.

**k-nearest neighbors (kNN)** là bài toán tìm `k` vector gần query nhất theo một metric cụ thể. Chữ `k` trong kNN có nghĩa là số hàng xóm cần lấy, không phải tên của một metric.

Ví dụ:

- Query vector biểu diễn câu hỏi về “cách nấu phở bò”.
- Elasticsearch tìm các document có embedding gần vector query.
- Kết quả có thể chứa bài viết về nước dùng phở, cách chọn thịt bò và cách trụng bánh phở.
- Các document này có thể không chứa nguyên văn từ khóa trong câu hỏi nhưng có nội dung gần về ngữ nghĩa.

Kết quả chỉ có ý nghĩa khi embedding model và metric phù hợp. Nếu vector của document được tạo bằng model A nhưng query vector được tạo bằng model B, hai vector có thể cùng số chiều nhưng không cùng không gian biểu diễn. Khi đó phép đo khoảng cách không còn đáng tin cậy.

### 1.1. Similarity và distance

Hai cách diễn đạt thường gặp:

- **Similarity:** giá trị càng lớn thì hai vector càng giống nhau.
- **Distance:** giá trị càng nhỏ thì hai vector càng gần nhau.

Elasticsearch xếp hạng theo `_score` tăng dần về mức liên quan: score cao hơn được ưu tiên. Với một số metric dựa trên distance, Elasticsearch chuyển đổi distance thành score dương để có cùng quy tắc xếp hạng.

Không so sánh trực tiếp giá trị similarity thô với `_score`. Chúng là hai đại lượng khác nhau. Cũng không mặc định `_score = 0.9` có nghĩa xác suất liên quan là 90%.

## 2. Các metric similarity phổ biến

Elasticsearch hỗ trợ các metric chính cho dense vector:

- `cosine`
- `dot_product`
- `max_inner_product`
- `l2_norm`

Việc chọn metric phải phù hợp với cách embedding model được huấn luyện và chuẩn hóa.

### 2.1. Cosine similarity

Cosine similarity đo góc giữa hai vector, không phụ thuộc trực tiếp vào độ lớn (magnitude) của vector.

Với vector A và B:

\[
\operatorname{cosine}(A,B)
=
\frac{A \cdot B}{\|A\| \|B\|}
\]

Giá trị toán học nằm trong khoảng từ -1 đến 1:

| Giá trị | Ý nghĩa hình học |
| ---: | --- |
| 1 | Cùng hướng. |
| 0 | Vuông góc. |
| -1 | Ngược hướng. |

Ví dụ hai vector cùng hướng nhưng khác độ lớn:

~~~text
A = [1, 2]
B = [2, 4]
~~~

Cosine similarity bằng 1 vì hai vector cùng hướng. Euclidean distance giữa chúng lại khác 0.

Cosine thường phù hợp với embedding văn bản và nhiều embedding ngữ nghĩa, nhất là khi độ lớn vector không mang ý nghĩa liên quan. Không thể kết luận mọi model đều phải dùng cosine; cần xem cách model được huấn luyện.

Với mapping `similarity: cosine`, Elasticsearch tự chuẩn hóa vector document khi index để tối ưu phép tính nội bộ. Vector có magnitude bằng 0 không hợp lệ cho cosine vì không xác định được hướng.

Elasticsearch chuyển cosine thành document score:

\[
\_score = \frac{1 + \operatorname{cosine}(q,d)}{2}
\]

Vì vậy score được đưa về khoảng không âm. Đây là phép biến đổi để xếp hạng, không phải xác suất.

### 2.2. Dot product

Dot product là tổng tích từng chiều:

\[
A \cdot B = \sum_{i=1}^{n} A_i B_i
\]

Dot product nhạy với cả hướng và magnitude. Nếu vector đã được chuẩn hóa về unit length, dot product tương đương cosine similarity.

Với `element_type: float`, Elasticsearch yêu cầu cả document vector và query vector phải có độ dài đơn vị (unit length) khi mapping dùng `similarity: dot_product`. Score được tính:

\[
\_score = \frac{1 + (q \cdot d)}{2}
\]

Ưu điểm là phép tính có thể hiệu quả. Rủi ro là nếu ứng dụng quên chuẩn hóa query vector hoặc document vector, kết quả không tuân theo giả định của metric.

Dùng dot product khi model hoặc pipeline embedding quy định vector đã được chuẩn hóa. Không chọn chỉ vì tên metric nghe đơn giản hoặc vì thấy score cao hơn.

### 2.3. Maximum inner product

`max_inner_product` (MIP) cũng dựa trên inner product nhưng không yêu cầu vector chuẩn hóa. Magnitude của vector có thể ảnh hưởng mạnh tới score.

Metric này phù hợp với một số mô hình được huấn luyện bằng maximum inner product search, nơi magnitude có ý nghĩa trong hàm mục tiêu.

Elasticsearch chuyển đổi kết quả để score không âm:

- Nếu inner product nhỏ hơn 0: `score = 1 / (1 - inner_product)`.
- Nếu inner product lớn hơn hoặc bằng 0: `score = inner_product + 1`.

Không dùng MIP thay cosine một cách tùy tiện. Hai metric có thể xếp hạng khác nhau vì một metric chú ý magnitude còn metric kia tập trung hướng vector.

### 2.4. L2 norm (Euclidean distance)

L2 norm đo khoảng cách Euclidean giữa hai vector:

\[
d(A,B) = \sqrt{\sum_{i=1}^{n}(A_i-B_i)^2}
\]

Khoảng cách càng nhỏ thì vector càng gần nhau. Elasticsearch chuyển distance thành score:

\[
\_score = \frac{1}{1 + d(q,d)^2}
\]

Do đó document có khoảng cách nhỏ hơn sẽ có score cao hơn.

L2 phù hợp khi không gian vector và mục tiêu huấn luyện sử dụng khoảng cách Euclidean. Nếu magnitude thay đổi có ý nghĩa, L2 có thể phản ánh cả khác biệt về hướng lẫn độ lớn.

### 2.5. So sánh các metric

| Metric | Đại lượng chính | Chuẩn hóa vector | Khi nên cân nhắc |
| --- | --- | --- | --- |
| `cosine` | Góc giữa hai vector | Không cần chuẩn hóa ở client; Elasticsearch chuẩn hóa vector lưu trữ | Embedding ngữ nghĩa mà magnitude không quan trọng. |
| `dot_product` | Tích vô hướng | Với float, query và document phải unit length | Model được thiết kế cho vector chuẩn hóa và inner product. |
| `max_inner_product` | Inner product, có tính magnitude | Không bắt buộc unit length | Model dùng MIP và magnitude có ý nghĩa. |
| `l2_norm` | Khoảng cách Euclidean | Không bắt buộc | Model được huấn luyện hoặc đánh giá bằng L2 distance. |

Điều cần giữ nhất quán là metric được dùng khi đánh giá model, cấu hình field và truy vấn. Không đổi metric chỉ để thay đổi thứ tự kết quả mà chưa benchmark lại relevance.

### 2.6. Không so sánh score giữa các metric hoặc model khác nhau

Giả sử một truy vấn cosine trả `_score = 0.82` và một truy vấn L2 trả `_score = 0.82`. Hai score này không nhất thiết biểu thị cùng mức liên quan.

Score còn phụ thuộc:

- Metric và phép biến đổi score.
- Embedding model và phiên bản model.
- Vector normalization.
- Dimension và preprocessing.
- Boost, filter, hybrid query và rescoring.
- Cấu hình quantization.

Nếu cần ngưỡng như “chỉ nhận kết quả đủ gần”, hãy hiệu chỉnh ngưỡng trên tập validation theo metric/model cụ thể. Elasticsearch có tham số `similarity` của kNN query để đặt ngưỡng raw similarity; tham số này không phải document `_score`.

## 3. Chuẩn bị vector trước khi index

Chất lượng vector search bắt đầu từ pipeline tạo embedding. Cấu hình HNSW tốt không thể sửa embedding không phù hợp.

### 3.1. Dùng cùng model cho document và query

Document vector và query vector phải được tạo bởi cùng embedding model hoặc các model được thiết kế tương thích trong cùng vector space.

Giữ lại metadata về:

- Model ID và model version.
- Dimension.
- Text normalization/preprocessing.
- Chunking strategy nếu tài liệu được chia đoạn.
- Metric và normalization.
- Thời điểm hoặc pipeline version tạo vector.

Khi đổi embedding model, dù dimension vẫn là 384, vector cũ và mới có thể không tương thích. Thường cần tạo field/index mới, tái tạo vector cho dữ liệu cũ và chuyển alias sau khi kiểm chứng.

### 3.2. Dimension phải khớp

Nếu field khai báo `dims: 384`, mỗi document vector và query vector phải có đúng 384 phần tử.

Lỗi thường gặp:

- Model trả vector 768 chiều nhưng mapping khai báo 384.
- Model mới đổi dimension nhưng index vẫn dùng schema cũ.
- Một số document bị cắt hoặc nối vector sai.
- Query vector bị serialize mất phần tử cuối.
- Dùng vector của model khác dù cùng dimension.

Kiểm tra dimension trước khi gửi request và ghi metric cho các vector không hợp lệ. Không để lỗi dimension chỉ được phát hiện sau khi bulk đã gửi hàng nghìn item.

### 3.3. Không đưa vector rỗng hoặc giá trị không hữu hạn

Kiểm tra:

- Vector không null.
- Có đúng số chiều.
- Không chứa `NaN` hoặc positive/negative infinity.
- Với cosine, vector không có magnitude bằng 0.
- Với dot product float, vector đã được chuẩn hóa unit length.

Ví dụ kiểm tra Java:

~~~java
static void validateEmbedding(float[] vector, int expectedDims) {
    if (vector == null || vector.length != expectedDims) {
        throw new IllegalArgumentException("Invalid embedding dimensions");
    }

    double normSquared = 0.0;

    for (float value : vector) {
        if (!Float.isFinite(value)) {
            throw new IllegalArgumentException("Embedding contains non-finite value");
        }
        normSquared += value * value;
    }

    if (normSquared == 0.0) {
        throw new IllegalArgumentException("Zero vector is invalid for cosine");
    }
}
~~~

Nếu model yêu cầu unit vector, có thể kiểm tra norm gần 1 với sai số cho phép. Đừng tự normalize nếu model pipeline quy định không được làm như vậy hoặc nếu metric là MIP và magnitude mang ý nghĩa.

### 3.4. Chunking ảnh hưởng đến chất lượng nearest neighbors

Nếu một tài liệu dài được chia thành nhiều đoạn, mỗi đoạn có embedding riêng. Query sẽ trả về đoạn gần nhất, nhưng ứng dụng có thể cần hiển thị tài liệu gốc.

Hãy lưu các metadata như:

- `documentId`
- `chunkId`
- `chunkIndex`
- `title`
- `tenantId`
- `embeddingModelVersion`

Nếu chỉ index một vector cho toàn bộ tài liệu, các chủ đề nhỏ trong tài liệu dài có thể bị làm loãng. Nếu chia quá nhỏ, ngữ cảnh bị mất và kết quả có thể thiếu ý nghĩa. Chunk size và overlap cần được đánh giá cùng embedding model.

## 4. Mapping dense_vector trong Elasticsearch

Elasticsearch dùng field type `dense_vector` để lưu vector số.

Ví dụ mapping:

~~~http
PUT products
Content-Type: application/json

{
  "mappings": {
    "properties": {
      "productId": {
        "type": "keyword"
      },
      "name": {
        "type": "text"
      },
      "tenantId": {
        "type": "keyword"
      },
      "embedding": {
        "type": "dense_vector",
        "dims": 384,
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
~~~

Các thuộc tính quan trọng:

- `dims`: số chiều của vector.
- `index`: bật cấu trúc chỉ mục phục vụ approximate kNN.
- `similarity`: metric dùng để so sánh vector.
- `index_options`: chọn loại vector index và các tham số xây dựng cấu trúc.
- `m`, `ef_construction`: tham số xây dựng HNSW khi dùng loại index hỗ trợ chúng.

Các giá trị `m: 16` và `ef_construction: 100` là baseline thường gặp để bắt đầu benchmark, không phải cấu hình tối ưu cho mọi dữ liệu. Mapping của Elasticsearch có thể tự chọn kiểu index mặc định theo version, dimension và element type; nếu cần kiểm soát, khai báo rõ và xác nhận mapping thực tế.

### 4.1. Khai báo vector field bằng Spring Data Elasticsearch

Spring Data Elasticsearch có `FieldType.Dense_Vector`, `dims` và `knnSimilarity`.

Ví dụ entity:

~~~java
import java.util.List;
import org.springframework.data.annotation.Id;
import org.springframework.data.elasticsearch.annotations.Document;
import org.springframework.data.elasticsearch.annotations.Field;
import org.springframework.data.elasticsearch.annotations.FieldType;
import org.springframework.data.elasticsearch.annotations.KnnSimilarity;

@Document(indexName = "products")
public class ProductDocument {

    @Id
    private String id;

    @Field(type = FieldType.Keyword)
    private String tenantId;

    @Field(type = FieldType.Text)
    private String description;

    @Field(
        type = FieldType.Dense_Vector,
        dims = 384,
        knnSimilarity = KnnSimilarity.COSINE
    )
    private List<Float> embedding;

    // Constructor, getters và setters
}
~~~

`knnSimilarity` có các lựa chọn `COSINE`, `DOT_PRODUCT`, `L2_NORM`, `MAX_INNER_PRODUCT` và `DEFAULT`. Tên enum viết hoa theo Java API.

Nếu cần tùy chỉnh HNSW, Spring Data hiện hành cũng có `knnIndexOptions` và `KnnIndexOptions`; cách khai báo phụ thuộc các option mà phiên bản Spring Data và Elasticsearch hỗ trợ. Có thể quản lý mapping bằng JSON/index template nếu muốn schema rõ ràng và tách khỏi entity.

Không chỉ nhìn annotation rồi giả định index đã được tạo đúng. Nếu index đã tồn tại, Spring Data không thể đổi dimension hoặc similarity field một cách tùy ý. Hãy kiểm tra `GET /products/_mapping`.

### 4.2. Index document có embedding

Ví dụ dữ liệu:

~~~http
PUT /products/_doc/P-100
Content-Type: application/json

{
  "productId": "P-100",
  "tenantId": "tenant-001",
  "name": "Wireless keyboard",
  "embedding": [0.12, -0.08, 0.31, 0.07]
}
~~~

Vector trong ví dụ chỉ có bốn phần tử để minh họa. Với mapping `dims: 384`, vector thực tế phải có 384 phần tử.

Có thể ghi hàng loạt vector bằng Bulk API. Việc xây dựng graph vector làm tăng chi phí indexing và bộ nhớ so với chỉ lưu một field keyword/text. Hãy benchmark cả ingest throughput lẫn search latency.

### 4.3. Dense vector không phải field để sort hoặc aggregate

`dense_vector` được thiết kế cho vector search và scoring. Không dùng nó như field số thông thường để sort hoặc terms aggregation. Nếu cần thống kê theo category, giá, tenant hoặc trạng thái, lưu các field scalar riêng với mapping thích hợp.

## 5. Exact kNN: tìm kiếm chính xác bằng brute force

Exact kNN tính similarity cho mọi document có vector trong tập document phù hợp. Nó không bỏ qua vector dựa trên exploration cutoff.

Ưu điểm:

- Kết quả chính xác theo metric đã chọn trên tập document được lọc.
- Là ground truth để đo recall của ANN.
- Hữu ích khi tập ứng viên nhỏ.
- Có thể dùng khi cần scoring chính xác hoặc kết hợp với query/filter phức tạp.

Nhược điểm:

- Chi phí tăng theo số vector cần chấm điểm và dimension.
- Có thể rất chậm nếu index lớn.
- Không tận dụng HNSW để bỏ qua phần lớn vector.

### 5.1. Exact search bằng script_score

Ví dụ REST request dùng cosine:

~~~http
POST /products/_search
Content-Type: application/json

{
  "size": 10,
  "query": {
    "script_score": {
      "query": {
        "bool": {
          "filter": [
            {
              "term": {
                "tenantId": "tenant-001"
              }
            }
          ]
        }
      },
      "script": {
        "source": "cosineSimilarity(params.query_vector, 'embedding') + 1.0",
        "params": {
          "query_vector": [0.12, -0.08, 0.31, 0.07]
        }
      }
    }
  }
}
~~~

Script được chạy trên mọi document khớp query bên trong `script_score`. Vì vậy hãy đặt filter hẹp trong query con để giảm tập document cần chấm điểm.

`cosineSimilarity(...) + 1.0` dịch score để tránh score âm. Cách này chỉ là ví dụ cho cosine; với metric khác, dùng hàm và phép biến đổi phù hợp.

Không chạy `script_score` trên toàn bộ hàng triệu document chỉ để tìm top 10 nếu approximate kNN đã đáp ứng recall mục tiêu.

### 5.2. Exact search trong tập dữ liệu nhỏ

Ví dụ một tenant có 2.000 document, và filter theo `tenantId` chỉ còn 300 document. Exact scoring trên 300 vector có thể hợp lý, đặc biệt khi yêu cầu chính xác cao và latency vẫn nằm trong SLA.

Ngược lại, nếu filter chỉ còn 2 triệu document, exact scoring có thể tốn CPU và làm tăng latency. Khi đó cần benchmark ANN hoặc phân vùng index để giảm candidate set.

### 5.3. Exact không đồng nghĩa relevance hoàn hảo

Exact kNN chỉ bảo đảm tìm đúng top k theo metric trên các vector đã index. Nó không bảo đảm các kết quả phù hợp với ý định người dùng.

Nếu embedding model biểu diễn sai ngữ nghĩa, dữ liệu có nhiễu hoặc chunking kém, exact search vẫn trả về những document gần nhất trong một không gian không phù hợp.

Cần phân biệt:

- **Search recall:** ANN có tìm lại các nearest neighbors mà exact search tìm được không?
- **Human relevance:** người dùng có thấy các document đó thực sự hữu ích không?

Hai chỉ số cần được đo riêng.

## 6. Approximate kNN và HNSW

Approximate kNN (ANN) giảm số vector cần xem xét bằng cách xây dựng cấu trúc tìm kiếm trước khi query.

Elasticsearch sử dụng HNSW (Hierarchical Navigable Small World) cho nhiều loại dense vector index. HNSW xây dựng đồ thị nhiều tầng, trong đó mỗi vector được kết nối với một số vector lân cận. Khi tìm kiếm, thuật toán bắt đầu từ một điểm vào graph và lần theo các cạnh để tiến gần query vector.

~~~text
                Entry point
                    |
                    v
             Upper graph layers
                /       \
               v         v
           Layer 1     Layer 1
             /  \        |
            v    v       v
          Layer 0: graph of vector neighbors
          o---o---o---o---o---o---o
             \   \     /     /
              o---o---o-----o
~~~

Sơ đồ chỉ minh họa ý tưởng. Graph thực tế có cấu trúc nhiều tầng và kết nối phức tạp hơn.

HNSW không cần chấm điểm mọi vector. Nó khám phá một tập candidate có khả năng gần query, rồi xếp hạng candidate đó.

### 6.1. Vì sao HNSW nhanh hơn?

Với brute force, hệ thống phải tính similarity cho toàn bộ vector trong tập ứng viên. Với HNSW, thuật toán đi qua graph và tập trung vào vùng có khả năng chứa nearest neighbors.

Đổi lại, graph search có thể bỏ qua một vector thực sự nằm trong top k. Đây là lý do ANN có thể nhanh nhưng không luôn trả đúng kết quả như exact search.

### 6.2. Tham số xây dựng graph: m

`m` là số neighbor connections mà mỗi node có trong graph theo cách triển khai HNSW.

Ảnh hưởng thường gặp:

- `m` lớn hơn: graph dày hơn, có thể cải thiện khả năng điều hướng và recall.
- `m` lớn hơn: tốn thêm bộ nhớ và chi phí xây dựng/merge graph.
- `m` nhỏ hơn: graph nhẹ hơn nhưng có thể khó tìm các vùng lân cận tốt.

Không tăng `m` chỉ vì muốn query nhanh hơn. Đây là tham số xây dựng index, ảnh hưởng storage, indexing và recall.

### 6.3. Tham số xây dựng graph: ef_construction

`ef_construction` điều khiển số candidate được xem xét khi xây dựng danh sách neighbor cho node mới.

Thông thường:

- Giá trị cao hơn có thể tạo graph chất lượng hơn.
- Indexing chậm hơn vì phải khám phá nhiều candidate.
- Có thể tăng recall ở search time.
- Tăng chi phí CPU và thời gian ingest.

`ef_construction` là tham số index-time. Nó khác `num_candidates`, vốn điều khiển search-time candidate exploration trong kNN query.

### 6.4. Tham số tìm kiếm: num_candidates

`num_candidates` là số nearest-neighbor candidate cần xem xét trong quá trình tìm kiếm trên mỗi shard/segment theo cơ chế Elasticsearch.

Quy luật:

- Tăng `num_candidates`: thường cải thiện recall, nhưng latency và CPU tăng.
- Giảm `num_candidates`: thường giảm thời gian tìm kiếm, nhưng có thể bỏ lỡ nearest neighbors.
- Giá trị phải lớn hơn hoặc bằng `k`.
- Với HNSW, Elasticsearch giới hạn giá trị tối đa là 10.000.

`num_candidates` thường là tham số quan trọng nhất để cân bằng tốc độ và recall trong HNSW query.

## 7. Phân biệt k, num_candidates và size

Ba tham số này có ý nghĩa khác nhau:

| Tham số | Ý nghĩa |
| --- | --- |
| `k` | Số nearest neighbors cần lấy từ mỗi shard trước khi merge kết quả toàn cục. |
| `num_candidates` | Số candidate được khám phá trên mỗi shard/segment trong approximate search. |
| `size` | Số search hit cuối cùng trả về cho client. |

Ví dụ:

~~~json
{
  "size": 10,
  "knn": {
    "field": "embedding",
    "query_vector": [0.12, -0.08, 0.31, 0.07],
    "k": 10,
    "num_candidates": 100
  }
}
~~~

Ý nghĩa:

1. Elasticsearch khám phá candidate theo `num_candidates`.
2. Mỗi shard giữ các kết quả vector tốt nhất theo `k`.
3. Kết quả từ shard được merge.
4. Search response trả tối đa `size` hit.

Với nhiều shard, tổng lượng candidate được khám phá có thể lớn hơn nhiều so với `num_candidates` của một shard. Nếu index có nhiều segment, HNSW graph được tìm riêng trên các segment và số segment cũng ảnh hưởng chi phí.

Không đặt `num_candidates = size` theo thói quen. Nếu `size = 10`, `num_candidates = 10` có thể là cấu hình quá chặt và recall thấp. Hãy thử các tỷ lệ khác nhau, ví dụ 2x, 5x hoặc 10x `k`, rồi đo trên dữ liệu thật.

### 7.1. Ví dụ điều chỉnh candidate budget

Giả sử `k = 10`:

| num_candidates | Xu hướng | Rủi ro |
| ---: | --- | --- |
| 10 | Candidate budget thấp nhất hợp lệ. | Có thể bỏ lỡ nearest neighbors. |
| 30 | Khám phá nhiều hơn. | Latency tăng so với 10. |
| 100 | Candidate set rộng hơn. | Tốn CPU hơn nhưng thường cải thiện recall. |
| 500 | Khám phá rất rộng. | Có thể latency tăng mà recall chỉ cải thiện ít. |

Đây là ví dụ để thiết kế benchmark, không phải mức mặc định hoặc khuyến nghị cho mọi hệ thống. Dataset, dimension, số shard, filter selectivity và HNSW graph đều ảnh hưởng.

## 8. kNN query trong Elasticsearch

Ví dụ top-level kNN search:

~~~http
POST /products/_search
Content-Type: application/json

{
  "size": 10,
  "knn": {
    "field": "embedding",
    "query_vector": [0.12, -0.08, 0.31, 0.07],
    "k": 10,
    "num_candidates": 100,
    "filter": {
      "term": {
        "tenantId": "tenant-001"
      }
    }
  }
}
~~~

Field `embedding` phải là dense_vector có indexing enabled và query vector phải có cùng dimension.

`filter` bên trong `knn` là pre-filter. Elasticsearch áp dụng điều kiện này trong quá trình approximate search để tìm đủ candidate thỏa điều kiện.

### 8.1. Pre-filter và post-filter

Đây là khác biệt quan trọng khi lọc theo tenant, category hoặc trạng thái.

**Pre-filter** đặt bên trong `knn.filter`:

~~~json
{
  "knn": {
    "field": "embedding",
    "query_vector": [0.12, -0.08, 0.31, 0.07],
    "k": 10,
    "num_candidates": 100,
    "filter": {
      "term": {
        "tenantId": "tenant-001"
      }
    }
  }
}
~~~

Pre-filter được áp dụng trong quá trình tìm nearest neighbors để kết quả kNN có thể lấy đủ `k` document thỏa điều kiện nếu có đủ document phù hợp.

**Post-filter** đặt ở query scope bên ngoài kNN, ví dụ:

~~~json
{
  "query": {
    "bool": {
      "must": [
        {
          "knn": {
            "field": "embedding",
            "query_vector": [0.12, -0.08, 0.31, 0.07],
            "k": 10,
            "num_candidates": 100
          }
        }
      ],
      "filter": [
        {
          "term": {
            "tenantId": "tenant-001"
          }
        }
      ]
    }
  }
}
~~~

Post-filter chạy sau khi approximate search đã chọn candidate. Nếu nhiều candidate không thuộc tenant, kết quả cuối có thể ít hơn 10 dù trong index vẫn có đủ document của tenant đó.

Khi cần lấy top k trong một phạm vi nghiệp vụ như tenant, category hoặc quyền truy cập, ưu tiên đặt filter đúng trong `knn.filter`. Không dựa vào post-filter để thay thế pre-filter.

### 8.2. Filter selectivity và hành vi thực tế

Pre-filter không có nghĩa Elasticsearch luôn thực hiện cùng một cách trong mọi tình huống. Khi filter khớp một tỷ lệ lớn document trên shard, Elasticsearch có thể tìm approximate candidates không lọc trước rồi lọc candidate sau. Nếu candidate phù hợp quá ít, Elasticsearch có thể chuyển sang lọc trong quá trình search để bảo đảm semantics kết quả.

Vì vậy, hãy đo query với các mức filter selectivity khác nhau. Một tenant chiếm 80% index và tenant chỉ chiếm 0,1% index có thể có profile latency khác nhau.

## 9. Filtering, shard và số lượng kết quả

Một truy vấn kNN qua index nhiều shard cần merge kết quả shard-level thành global top k.

Ví dụ index có 4 shard:

~~~text
Query vector
     |
     +------> Shard 0: local candidates
     |
     +------> Shard 1: local candidates
     |
     +------> Shard 2: local candidates
     |
     +------> Shard 3: local candidates
                    |
                    v
             Coordinator merge
                    |
                    v
             Global top k hits
~~~

Một shard có thể chứa document gần query hơn shard khác. Elasticsearch cần lấy đủ candidate từ từng shard để kết quả merge có cơ hội tìm đúng top k toàn cục.

Một số tác động:

- Nhiều shard có thể tăng fan-out và chi phí merge.
- Nhiều segment có thể tăng số graph được khám phá.
- Shard mất cân bằng làm latency không đều.
- Filter chọn lọc mạnh có thể giảm số document phù hợp nhưng cũng thay đổi cách search xử lý.
- Số lượng document trả về không nhất thiết bằng `k` nếu `size`, filter hoặc dữ liệu phù hợp không đủ.

Không tăng số shard chỉ để tăng song song vector search. Mỗi shard bổ sung overhead và cần benchmark với kích thước shard phù hợp.

## 10. Exact và approximate: chọn theo quy mô và SLA

| Tiêu chí | Exact kNN | Approximate kNN (HNSW) |
| --- | --- | --- |
| Cách làm | Chấm điểm mọi vector phù hợp. | Dò graph để tìm candidate gần query. |
| Độ chính xác nearest neighbor | Chính xác theo metric trên tập đã lọc. | Có thể bỏ lỡ một số hàng xóm thật. |
| Latency trên tập lớn | Tăng theo số vector cần chấm điểm. | Thường thấp hơn nếu graph được cấu hình tốt. |
| CPU | Cao khi tập candidate lớn. | Phụ thuộc graph traversal và candidate budget. |
| Indexing | Không cần xây HNSW graph nếu dùng flat/exact path. | Tốn thêm chi phí xây graph. |
| Memory/storage | Lưu vector và dữ liệu cần cho scoring. | Thêm graph và có thể thêm cấu trúc quantization. |
| Tập dữ liệu nhỏ | Thường phù hợp. | Có thể không cần thiết. |
| Tập dữ liệu lớn | Có thể không đáp ứng SLA. | Thường phù hợp với production retrieval. |
| Ground truth benchmark | Là baseline để đo recall. | Được so sánh với exact top k. |

Không có ngưỡng số document cố định để chuyển từ exact sang ANN. Tập 50.000 vector 384 chiều trên phần cứng mạnh có thể khác đáng kể so với 50.000 vector 3.072 chiều trên node nhỏ. Filter có thể làm candidate set giảm đủ nhỏ để exact search vẫn phù hợp.

## 11. Quantization: giảm bộ nhớ, đánh đổi độ chính xác

Vector float32 cần khoảng 4 byte cho mỗi dimension trước khi tính overhead. Một vector 768 chiều vì vậy cần khoảng 3 KB cho raw float values. Khi có hàng chục hoặc hàng trăm triệu vector, chi phí lưu trữ và bộ nhớ có thể lớn.

Quantization giảm số bit dùng để biểu diễn vector:

- `int8_hnsw`: lượng tử hóa scalar 8-bit.
- `int4_hnsw`: lượng tử hóa scalar 4-bit.
- `bbq_hnsw`: binary quantization.
- `bbq_disk`: kiểu vector search hướng disk-based, phụ thuộc phiên bản và license.

Các kiểu nén này có thể giảm bộ nhớ và storage nhưng làm mất một phần thông tin vector. Mức mất mát phụ thuộc phân bố dữ liệu, model và query.

### 11.1. Chọn quantization

| Kiểu | Ý tưởng | Đánh đổi tổng quát |
| --- | --- | --- |
| float32 + HNSW | Giữ vector float đầy đủ. | Fidelity cao, chi phí bộ nhớ cao. |
| int8 | Lượng tử hóa 8-bit. | Tiết kiệm bộ nhớ, có thể giảm recall nhẹ. |
| int4 | Lượng tử hóa 4-bit. | Nén mạnh hơn, thường mất thêm fidelity. |
| BBQ | Biểu diễn vector bằng binary quantization. | Tiết kiệm bộ nhớ lớn, cần kiểm tra recall và rescoring. |

Các mặc định index type thay đổi theo Elasticsearch version và dimension. Không dựa vào mặc định của một cluster khác. Kiểm tra mapping `index_options` và tài liệu đúng version đang triển khai.

### 11.2. Oversampling và rescoring

Với vector quantized, có thể lấy nhiều candidate hơn `k`, sau đó tính lại similarity bằng vector gốc để cải thiện thứ tự.

Ví dụ:

~~~json
{
  "knn": {
    "field": "embedding",
    "query_vector": [0.12, -0.08, 0.31, 0.07],
    "k": 10,
    "num_candidates": 100,
    "rescore_vector": {
      "oversample": 2.0
    }
  }
}
~~~

Nếu `k = 10` và `oversample = 2`, Elasticsearch có thể rescoring khoảng 20 candidate tốt nhất mỗi shard bằng vector gốc trước khi merge kết quả cuối.

Oversampling có ích khi quantization làm thay đổi thứ tự các vector gần nhau. Đổi lại, rescoring cần đọc thêm vector gốc và tăng CPU/latency. Chọn oversample bằng benchmark, không có một hệ số tối ưu chung cho mọi model.

`rescore_vector` áp dụng cho các dense vector field được quantize. Với vector không quantized, việc rescoring theo cách này không đem lại lợi ích tương tự vì search đã dùng vector gốc.

## 12. Tuning HNSW: index-time và search-time

Có hai nhóm tham số cần tách biệt.

| Thời điểm | Tham số | Ảnh hưởng |
| --- | --- | --- |
| Tạo graph/index | `m` | Số kết nối graph, memory và chất lượng graph. |
| Tạo graph/index | `ef_construction` | Số candidate dùng khi xây graph, chất lượng graph và indexing time. |
| Truy vấn | `k` | Số nearest neighbors cần lấy. |
| Truy vấn | `num_candidates` | Candidate budget, recall và latency. |
| Truy vấn với quantized vector | `rescore_vector.oversample` | Số candidate được chấm lại bằng vector gốc. |

Nếu recall thấp, có thể cần tăng `num_candidates`, cải thiện graph qua `m`/`ef_construction`, hoặc xem lại embedding model. Nếu latency cao, giảm candidate budget có thể giúp nhưng phải đo recall sau khi thay đổi.

Thay đổi `m` hoặc `ef_construction` thường cần xây lại graph cho dữ liệu đã index, bằng reindex/merge theo khả năng của Elasticsearch version. Không nhầm chúng với tham số query có thể thay đổi ngay mỗi request.

## 13. kNN trong Spring Data Elasticsearch

Spring Data Elasticsearch sử dụng Elasticsearch Java API Client ở bên dưới. Với các phiên bản mới, `NativeQueryBuilder.withKnnSearches(...)` tạo top-level `knn` option trong Search API.

### 13.1. Entity có dense vector

~~~java
import java.util.List;
import org.springframework.data.annotation.Id;
import org.springframework.data.elasticsearch.annotations.Document;
import org.springframework.data.elasticsearch.annotations.Field;
import org.springframework.data.elasticsearch.annotations.FieldType;
import org.springframework.data.elasticsearch.annotations.KnnSimilarity;

@Document(indexName = "products")
public class ProductDocument {

    @Id
    private String id;

    @Field(type = FieldType.Keyword)
    private String tenantId;

    @Field(type = FieldType.Text)
    private String description;

    @Field(
        type = FieldType.Dense_Vector,
        dims = 384,
        knnSimilarity = KnnSimilarity.COSINE
    )
    private List<Float> embedding;

    // Constructor, getters và setters
}
~~~

Đảm bảo kiểu Java được converter của phiên bản Spring Data trong dự án hỗ trợ cho dense vector. `List<Float>` thể hiện vector dưới dạng danh sách số; query vector truyền vào Java API Client cũng phải có 384 giá trị.

### 13.2. Tạo kNN NativeQuery

Ví dụ dùng top-level kNN search:

~~~java
import co.elastic.clients.elasticsearch._types.FieldValue;
import co.elastic.clients.elasticsearch._types.KnnSearch;
import org.springframework.data.elasticsearch.client.elc.NativeQuery;
import org.springframework.data.elasticsearch.core.ElasticsearchOperations;
import org.springframework.data.elasticsearch.core.SearchHit;
import org.springframework.data.elasticsearch.core.SearchHits;

public class ProductVectorSearchService {

    private final ElasticsearchOperations operations;

    public ProductVectorSearchService(ElasticsearchOperations operations) {
        this.operations = operations;
    }

    public List<ProductDocument> findSimilar(
            List<Float> queryVector,
            String tenantId) {

        KnnSearch knnSearch = KnnSearch.of(knn -> knn
                .field("embedding")
                .queryVector(queryVector)
                .k(10)
                .numCandidates(100)
                .filter(filter -> filter.term(term -> term
                        .field("tenantId")
                        .value(FieldValue.of(tenantId))
                ))
        );

        NativeQuery query = NativeQuery.builder()
                .withKnnSearches(knnSearch)
                .build();

        SearchHits<ProductDocument> hits =
                operations.search(query, ProductDocument.class);

        return hits.getSearchHits().stream()
                .map(SearchHit::getContent)
                .toList();
    }
}
~~~

Ví dụ minh họa API Spring Data Elasticsearch hiện hành:

- `KnnSearch` đến từ Elasticsearch Java API Client.
- `NativeQuery` nằm trong package `org.springframework.data.elasticsearch.client.elc`.
- `withKnnSearches(...)` cấu hình top-level kNN.
- `ElasticsearchOperations.search(...)` trả `SearchHits<T>`.
- Filter được đặt bên trong `KnnSearch` để làm pre-filter.

Các phiên bản Spring Data cũ hơn có API khác. Từ Spring Data Elasticsearch 5.4, `withKnnQuery` được thay bằng `withKnnSearches` cho top-level kNN search. `KnnQuery` là query nằm bên trong query DSL; `KnnSearch` là top-level knn option. Không nhầm hai class này.

### 13.3. SearchHit và score

Có thể lấy metadata của từng hit:

~~~java
for (SearchHit<ProductDocument> hit : hits) {
    ProductDocument product = hit.getContent();

    String id = hit.getId();
    float score = hit.getScore();

    // Dùng score để sắp xếp/hiển thị theo contract của ứng dụng.
}
~~~

`_score` là score do Elasticsearch tính. Nếu query kết hợp vector score với text score hoặc boost, score cuối có thể đã được kết hợp. Không dùng một threshold cố định cho mọi loại query mà chưa hiệu chỉnh.

### 13.4. ReactiveElasticsearchOperations

Trong ứng dụng reactive, có thể dùng `ReactiveElasticsearchOperations` với cùng `NativeQuery`:

~~~java
public Flux<ProductDocument> findSimilarReactive(
        List<Float> queryVector,
        String tenantId) {

    KnnSearch knnSearch = KnnSearch.of(knn -> knn
            .field("embedding")
            .queryVector(queryVector)
            .k(10)
            .numCandidates(100)
            .filter(filter -> filter.term(term -> term
                    .field("tenantId")
                    .value(FieldValue.of(tenantId))
            ))
    );

    NativeQuery query = NativeQuery.builder()
            .withKnnSearches(knnSearch)
            .build();

    return reactiveOperations.search(query, ProductDocument.class)
            .map(SearchHit::getContent);
}
~~~

Reactive pipeline cần được subscribe bởi framework/caller. Không gọi `block()` hoặc `subscribe()` bên trong service chỉ để chờ kết quả. Giới hạn số request đồng thời nếu nhiều query vector chạy song song.

### 13.5. Exact query trong Spring Data

Nếu cần exact scoring, có thể tạo `NativeQuery` từ Elasticsearch Java API Client `Query` chứa `script_score`, sau đó gọi `ElasticsearchOperations.search(...)`. Hoặc gọi REST/API client trực tiếp khi cần một request option chưa được abstraction hỗ trợ.

Exact query phải giới hạn tập document trước khi script chạy. Không gọi script_score trên toàn index lớn nếu mục tiêu là low-latency semantic retrieval.

## 14. Kết hợp vector search với filter nghiệp vụ

Vector similarity không thay thế filter nghiệp vụ. Một ứng dụng thường cần kết hợp:

- Tenant isolation.
- Trạng thái active.
- Ngôn ngữ.
- Danh mục.
- Quyền truy cập.
- Thời gian xuất bản.
- Loại document.

Ví dụ query vector với tenant và trạng thái:

~~~json
{
  "knn": {
    "field": "embedding",
    "query_vector": [0.12, -0.08, 0.31, 0.07],
    "k": 10,
    "num_candidates": 100,
    "filter": {
      "bool": {
        "filter": [
          { "term": { "tenantId": "tenant-001" } },
          { "term": { "status": "ACTIVE" } },
          { "term": { "language": "vi" } }
        ]
      }
    }
  }
}
~~~

Filter phải được tạo từ context đã xác thực ở server. Không để client gửi tenant filter tùy ý rồi xem đó là security boundary.

### 14.1. Filter quá chọn lọc

Nếu filter chỉ còn một vài document, HNSW graph có thể không phải đường tìm kiếm hiệu quả nhất. Elasticsearch có thể chuyển sang brute-force trong một số trường hợp khi tập filtered document nhỏ hoặc candidate search không hiệu quả.

Điều này không phải lỗi. Cần benchmark theo filter selectivity thực tế. Có thể thiết kế index partition hoặc routing nếu workload tenant/filter quá đặc thù, nhưng routing không thay thế filter bảo mật.

## 15. Hybrid search: kết hợp lexical và vector

Vector search tốt với ngữ nghĩa, nhưng lexical search vẫn quan trọng cho:

- Mã sản phẩm.
- Tên riêng.
- Mã lỗi.
- Từ khóa hiếm.
- Chuỗi chính xác.
- Thuật ngữ cần khớp nguyên văn.

Hybrid search kết hợp kết quả text query và vector query. Một cách tiếp cận là chạy hai retriever rồi hợp nhất kết quả bằng Reciprocal Rank Fusion (RRF), hoặc kết hợp score theo cấu hình phù hợp.

Ví dụ minh họa request có text query và top-level kNN:

~~~http
POST /products/_search
Content-Type: application/json

{
  "size": 10,
  "query": {
    "match": {
      "description": "wireless keyboard for office"
    }
  },
  "knn": {
    "field": "embedding",
    "query_vector": [0.12, -0.08, 0.31, 0.07],
    "k": 50,
    "num_candidates": 200
  }
}
~~~

Khi kết hợp top-level `query` và `knn`, Elasticsearch có thể hợp nhất các document match theo semantics của Search API. Nếu score text và vector có scale khác nhau, cộng score trực tiếp có thể khiến một nhánh lấn át nhánh còn lại.

RRF dựa trên thứ hạng thay vì cộng raw score trực tiếp, thường là lựa chọn tốt để bắt đầu khi hai retriever có score distribution khác nhau. Dù dùng cách nào, cần đo relevance bằng tập query có nhãn.

## 16. Đo độ chính xác: recall@k

Khi tuning ANN, cần có exact baseline để biết ANN bỏ lỡ bao nhiêu nearest neighbors.

**Recall@k** của ANN so với exact top k:

\[
\operatorname{Recall@k}
=
\frac{|\operatorname{ANNTopK} \cap \operatorname{ExactTopK}|}{k}
\]

Ví dụ exact top 5:

~~~text
Exact:      A, B, C, D, E
ANN result: A, B, D, F, E
~~~

Có 4 document trùng nhau trên 5:

\[
\operatorname{Recall@5} = \frac{4}{5} = 0.8
\]

Recall@k = 0.8 nghĩa là ANN tìm lại 80% document thuộc exact top k trong ví dụ. Nó không có nghĩa 80% kết quả là hữu ích với người dùng.

### 16.1. Exact ground truth phải cùng điều kiện

Để so sánh công bằng, exact và ANN cần dùng:

- Cùng query vector.
- Cùng embedding model/version.
- Cùng metric.
- Cùng tập document hợp lệ.
- Cùng filter và tenant scope.
- Cùng k.
- Cùng dữ liệu và thời điểm benchmark.

Nếu exact query không dùng tenant filter mà ANN có filter, recall calculation không còn cùng tập tìm kiếm.

### 16.2. Recall và relevance là hai bài toán

Recall@k đo độ gần với exact vector ranking. Các metric như nDCG@k, MRR hoặc precision@k dựa trên nhãn relevance đo mức hữu ích của kết quả theo đánh giá nghiệp vụ.

Một ANN có recall 99% vẫn có thể trả kết quả kém nếu embedding model không hiểu domain. Ngược lại, một ANN recall 95% có thể đạt relevance tốt nếu những neighbor bị bỏ lỡ không quan trọng với người dùng.

Nên đo cả hai nếu hệ thống là search product-facing.

## 17. Benchmark tốc độ và độ chính xác

Không chọn `num_candidates` chỉ bằng cảm giác. Tạo benchmark có query đại diện và đo nhiều mức candidate budget.

Ví dụ ma trận:

| Thử nghiệm | k | num_candidates | Mục tiêu |
| --- | ---: | ---: | --- |
| A | 10 | 10 | Baseline candidate thấp. |
| B | 10 | 30 | Kiểm tra recall tăng ở mức vừa. |
| C | 10 | 100 | Candidate budget rộng hơn. |
| D | 10 | 300 | Xem recall còn cải thiện không. |
| E | 10 | 500 | Kiểm tra điểm lợi ích giảm dần. |

Đo tối thiểu:

- Recall@k so với exact.
- p50, p95 và p99 latency.
- Query throughput (QPS).
- CPU utilization.
- Heap và memory pressure.
- Vector memory / filesystem cache.
- Disk I/O.
- Indexing throughput.
- Thời gian refresh/merge khi ingest song song.
- Kích thước index và HNSW graph.

Tăng `num_candidates` có thể làm recall tăng nhưng p95/p99 latency cũng tăng. Điểm tối ưu là mức đạt recall và SLA đã định, không phải mức recall tuyệt đối cao nhất.

### 17.1. Dùng query thực tế

Bộ query benchmark nên bao gồm:

- Query ngắn và dài.
- Query tiếng Việt có dấu và không dấu nếu hệ thống hỗ trợ cả hai.
- Query đa ngôn ngữ.
- Query hiếm và query phổ biến.
- Query có filter rộng và filter hẹp.
- Query không có kết quả tốt.
- Query ở tenant nhỏ và tenant lớn.
- Query có nhiều document gần nhau (near-ties).

Không chỉ benchmark bằng vector ngẫu nhiên. Vector ngẫu nhiên không phản ánh phân bố embedding và mức độ khó của truy vấn thực tế.

### 17.2. Kiểm tra nhiều trạng thái index

HNSW search có thể chịu ảnh hưởng bởi số segment. Index vừa ingest nhiều có thể có nhiều segment hơn, còn sau merge graph có thể được xây lại. Benchmark cần đại diện cho trạng thái index production, không chỉ một index mới tạo.

Nếu dữ liệu liên tục ingest, đo cả lúc có merge và refresh. Nếu chỉ benchmark lúc index yên tĩnh, latency production có thể khác.

## 18. Tuning theo mục tiêu nghiệp vụ

### 18.1. Ưu tiên latency thấp

Nếu SLA yêu cầu phản hồi nhanh:

- Bắt đầu với `k` vừa đủ cho UI.
- Giữ `num_candidates` ở mức nhỏ nhưng vẫn đạt recall chấp nhận được.
- Giới hạn filter và document scope hợp lý.
- Kiểm tra số shard/segment.
- Cân nhắc quantization nếu memory là bottleneck.
- Chỉ rescore số candidate cần thiết.
- Cache query vector hoặc embedding khi phù hợp với tính nhất quán dữ liệu.

Không giảm candidate budget quá thấp mà không kiểm tra recall. Kết quả nhanh nhưng thiếu các document tốt có thể làm trải nghiệm tệ hơn.

### 18.2. Ưu tiên độ chính xác

Nếu yêu cầu recall cao:

- Tăng `num_candidates` từng bước.
- Tăng `m` hoặc `ef_construction` khi tạo graph mới nếu benchmark cho thấy cần.
- Cân nhắc exact search trên tập candidate đã lọc nhỏ.
- Dùng oversampling và rescoring cho quantized vector.
- Xem lại embedding model và chunking.
- So sánh ANN với exact ground truth thường xuyên.

Không giả định chỉ tăng `num_candidates` có thể sửa mọi vấn đề. Nếu graph kém chất lượng hoặc embedding không phù hợp, cần cải thiện index/model.

### 18.3. Ưu tiên memory/storage

Nếu vector dataset quá lớn:

- Đánh giá int8/int4/binary quantization theo version hỗ trợ.
- Dùng `bbq_disk` khi phù hợp license và kiến trúc.
- Đo ảnh hưởng của quantization lên recall.
- Cân nhắc on-disk rescoring nếu vector gốc không vừa RAM.
- Kiểm soát số replica và số shard.
- Giữ node có memory và filesystem cache đủ cho workload.

Nén vector có thể giảm memory nhưng không miễn phí. Query có thể cần rescoring để phục hồi recall, làm tăng disk I/O hoặc latency.

### 18.4. Ưu tiên throughput ingest

Indexing vector tốn công hơn index field scalar vì phải xây cấu trúc vector index.

Có thể xem xét:

- Bulk indexing với batch size và concurrency được kiểm soát.
- Refresh interval phù hợp với ingestion window.
- HNSW `m`/`ef_construction` không quá cao so với yêu cầu.
- Tạo index mới rồi alias swap cho initial load.
- Theo dõi merge, disk và vector memory.

Không hy sinh recall hoặc tăng indexing pressure mà không đo. Cần cân bằng tốc độ ingest với chất lượng graph và khả năng search.

## 19. Lỗi thường gặp khi triển khai kNN

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| kNN query báo dimension mismatch | Query vector khác `dims` của field. | Kiểm tra model version và dimension. |
| Không có kết quả | Vector field thiếu giá trị, filter không match hoặc sai index. | Kiểm tra mapping, `_source`, filter và index. |
| Kết quả ngữ nghĩa kém | Query/document dùng model khác hoặc preprocessing khác. | Chuẩn hóa pipeline embedding và đánh giá model. |
| Score âm hoặc không như mong đợi | Nhầm raw similarity với `_score` hoặc dùng metric khác. | Kiểm tra metric và công thức score. |
| Dot product cho kết quả bất thường | Float vector không được normalize unit length. | Chuẩn hóa cả document và query vector theo model contract. |
| Cosine báo lỗi vector zero | Vector có magnitude bằng 0. | Loại vector rỗng và kiểm tra pipeline embedding. |
| Trả ít hơn k kết quả | Post-filter làm rơi candidate hoặc không đủ document phù hợp. | Đưa điều kiện vào `knn.filter` và kiểm tra filter selectivity. |
| Latency cao | `num_candidates` lớn, nhiều shard/segment hoặc memory pressure. | Đo candidate budget, shard và cache. |
| Recall thấp | Candidate budget thấp, graph chưa tốt, quantization hoặc model. | Tăng `num_candidates`, benchmark graph và rescoring. |
| Ingest chậm | Xây graph vector tốn CPU/memory và bulk quá lớn. | Điều chỉnh batch/concurrency và HNSW build parameters. |
| Kết quả khác sau khi đổi model | Embedding space thay đổi. | Re-embed dữ liệu và chuyển sang index version mới. |
| Search alias gặp hành vi không nhất quán | Các index có mapping/dimension/model khác nhau. | Kiểm tra mapping và version từng index. |
| Hybrid score bị lệch | Text và vector score có scale khác nhau. | Dùng RRF hoặc tuning boost theo relevance set. |

## 20. Kiểm tra mapping và dữ liệu khi chẩn đoán

### 20.1. Kiểm tra mapping

~~~http
GET /products/_mapping
~~~

Xác nhận:

- Field type là `dense_vector`.
- `dims` đúng với model.
- `similarity` đúng metric.
- `index` được bật nếu dùng approximate kNN.
- `index_options` đúng loại graph/quantization.
- Không có index cùng alias với mapping khác dimension.

### 20.2. Kiểm tra document

~~~http
GET /products/_doc/P-100
~~~

Kiểm tra vector có được ghi vào document hay không và số chiều có đúng. Nếu cấu hình `_source` hoặc vector storage của version đang dùng không trả raw vector như mong đợi, kiểm tra API field/docvalue tương ứng và mapping storage.

### 20.3. Kiểm tra Field Capabilities

Khi search qua nhiều index:

~~~http
GET /products-*/_field_caps?fields=embedding
~~~

Field capabilities giúp phát hiện mapping type conflict. Tuy nhiên, dimension và similarity của dense vector vẫn cần kiểm tra mapping từng index.

### 20.4. Đo query profile

Có thể dùng `profile: true` trong Search API để xem chi phí thực thi query:

~~~http
POST /products/_search
Content-Type: application/json

{
  "profile": true,
  "size": 10,
  "knn": {
    "field": "embedding",
    "query_vector": [0.12, -0.08, 0.31, 0.07],
    "k": 10,
    "num_candidates": 100
  }
}
~~~

Profile hữu ích để điều tra query nhưng tạo thêm overhead. Không bật cho mọi request production và không dùng profile latency làm số đo benchmark bình thường.

## 21. Quy trình triển khai và tuning

Một quy trình thực tế:

1. Chọn embedding model và xác định version.
2. Xác định dimension, normalization và metric theo model.
3. Tạo index mapping có `dense_vector`, dims và similarity tường minh.
4. Index một tập dữ liệu đại diện.
5. Tạo exact baseline bằng brute-force scoring trên tập document phù hợp.
6. Chạy approximate kNN với `k` và `num_candidates` ban đầu.
7. So sánh ANN với exact bằng recall@k.
8. Tăng/giảm candidate budget để tìm điểm cân bằng latency và recall.
9. Nếu recall vẫn thấp, xem graph parameters, quantization và embedding quality.
10. Kiểm tra filter pre-filter/post-filter và số shard.
11. Benchmark với query thực tế, filter thực tế và workload ingest/search đồng thời.
12. Đặt SLA cho recall, p95/p99 latency và QPS.
13. Theo dõi drift khi thay model, mapping, index type hoặc dữ liệu.
14. Reindex và chuyển alias khi dimension/model space thay đổi.

Lưu lại cấu hình và benchmark result theo version. Nếu thay `num_candidates`, `m`, `ef_construction`, quantization hoặc embedding model, cần có số liệu trước/sau để biết thay đổi cải thiện chỉ số nào.

## 22. Tài liệu tham khảo

- [Spring Data Elasticsearch — Field annotation](https://docs.spring.io/spring-data/elasticsearch/reference/api/java/org/springframework/data/elasticsearch/annotations/Field.html)
- [Spring Data Elasticsearch — FieldType](https://docs.spring.io/spring-data/elasticsearch/reference/api/java/org/springframework/data/elasticsearch/annotations/FieldType.html)
- [Spring Data Elasticsearch — KnnSimilarity](https://docs.spring.io/spring-data/elasticsearch/reference/api/java/org/springframework/data/elasticsearch/annotations/KnnSimilarity.html)
- [Spring Data Elasticsearch — NativeQueryBuilder](https://docs.spring.io/spring-data/elasticsearch/reference/api/java/org/springframework/data/elasticsearch/client/elc/NativeQueryBuilder.html)
- [Spring Data Elasticsearch — Migration guide 5.3 to 5.4](https://docs.spring.io/spring-data/elasticsearch/reference/migration-guides/migration-guide-5.3-5.4.html)
- [Elasticsearch — Dense vector field type](https://www.elastic.co/docs/reference/elasticsearch/mapping-reference/dense-vector)
- [Elasticsearch — kNN query](https://www.elastic.co/docs/reference/query-languages/query-dsl/query-dsl-knn-query)
- [Elasticsearch — Dense vector query](https://www.elastic.co/docs/reference/query-languages/query-dsl/query-dsl-dense-vector-query)
- [Elasticsearch — Optimize approximate kNN performance and accuracy](https://www.elastic.co/docs/solutions/search/vector/knn/optimize-performance-accuracy)
- [Elasticsearch — kNN search](https://www.elastic.co/docs/solutions/search/vector/knn)

Metric quyết định ý nghĩa của “gần”; exact kNN tạo baseline chính xác theo metric, còn HNSW giảm chi phí bằng cách chỉ khám phá một phần vector. Trong Elasticsearch, `k` là số hàng xóm cần lấy, `num_candidates` điều khiển candidate budget và filter bên trong `knn` là pre-filter. Hãy đo recall@k so với exact cùng latency p95/p99 trên query và filter thực tế, sau đó điều chỉnh graph, candidate budget và quantization theo SLA. Spring Data Elasticsearch tích hợp các khả năng này qua dense vector mapping và `NativeQuery.withKnnSearches(...)`.

