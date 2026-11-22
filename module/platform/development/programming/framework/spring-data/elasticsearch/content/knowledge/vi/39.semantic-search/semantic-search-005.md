# Thực hiện truy vấn qua NativeQuery hoặc client theo phiên bản hỗ trợ

Tìm kiếm ngữ nghĩa (semantic search) dùng vector embedding để tìm document có nội dung gần với ý nghĩa của câu hỏi. Thay vì chỉ so khớp từ khóa, ứng dụng chuyển văn bản thành vector số rồi tìm các vector gần nhất trong Elasticsearch.

Trong Spring Data Elasticsearch, cách phổ biến để gửi truy vấn nâng cao là **NativeQuery**. NativeQuery sử dụng các query builder của Elasticsearch Java API Client, nên có thể biểu diễn kNN, bool query, filter, aggregation và nhiều tính năng Query DSL khác. Khi phiên bản Spring Data hoặc builder chưa expose một tính năng server mới, ứng dụng có thể gọi trực tiếp Elasticsearch Java API Client đã được cấu hình.

Điểm cần chú ý là API thay đổi theo release. Từ Spring Data Elasticsearch 5.4, **NativeQueryBuilder.withKnnQuery** được thay bằng **withKnnSearches** cho kNN search cấp cao nhất. **KnnSearch** và **KnnQuery** là hai kiểu khác nhau trong Elasticsearch Java API Client. Sao chép code từ một phiên bản khác mà không kiểm tra dependency có thể dẫn tới compile error hoặc tạo request có semantics khác dự kiến.

Bài này trình bày cách chuẩn bị vector, mapping dense_vector, xây NativeQuery cho kNN và hybrid search, gọi client trực tiếp khi cần, chọn API theo version, đọc SearchHits và xử lý các lỗi thường gặp.

## 1. Luồng tìm kiếm ngữ nghĩa

### 1.1. Embedding là gì?

Embedding là vector số biểu diễn nội dung. Một mô hình embedding nhận văn bản và tạo ra một dãy số có số chiều cố định.

~~~text
"wireless keyboard"
    -> embedding model
    -> [0.12, -0.08, 0.31, ..., 0.04]
~~~

Hai câu có ý nghĩa gần nhau thường có vector gần nhau theo metric mà mô hình và hệ thống tìm kiếm sử dụng. Vector không phải bản tóm tắt dễ đọc; nó là representation để so sánh bằng phép tính số học.

### 1.2. Hai lần tạo embedding

Một pipeline semantic search thường có hai nhánh:

1. **Indexing time**: tạo embedding cho nội dung document và lưu vector vào Elasticsearch.
2. **Query time**: tạo embedding cho câu hỏi của người dùng bằng cùng mô hình và tìm các vector gần nhất.

~~~mermaid
flowchart TD
    A[Source document] --> B[Text preprocessing]
    B --> C[Embedding model]
    C --> D[Document vector]
    D --> E[(Elasticsearch dense_vector)]
    F[User query] --> G[Same embedding model]
    G --> H[Query vector]
    H --> I[kNN NativeQuery]
    E --> I
    I --> J[Ranked SearchHits]
~~~

Nếu document vector được tạo bởi model A nhưng query vector được tạo bởi model B, cùng số chiều cũng không bảo đảm hai vector nằm trong cùng không gian ngữ nghĩa.

### 1.3. Trách nhiệm của Spring Data và embedding model

Spring Data Elasticsearch chịu trách nhiệm gửi query, mapping document và đọc kết quả. Việc tạo embedding có thể do:

- Một embedding service riêng.
- Một model chạy nội bộ.
- Một dịch vụ inference được quản lý.
- Elasticsearch inference endpoint hoặc semantic field workflow nếu phiên bản và cấu hình hỗ trợ.

Không giả định NativeQuery tự tạo embedding từ câu hỏi. Với dense_vector thông thường, ứng dụng phải gửi queryVector đã được tạo trước. Nếu dùng server-side inference/query vector builder, request phải khai báo model và cấu trúc được Elasticsearch version hỗ trợ.

### 1.4. Dùng cùng model cho hai phía

Lưu metadata model cùng document hoặc trong projection metadata:

~~~json
{
  "id": "DOC-1001",
  "embeddingModel": "catalog-embedding-v3",
  "embeddingVersion": 3,
  "embedding": [0.12, -0.08, 0.31, 0.04]
}
~~~

Metadata này giúp xác định vector được tạo từ model nào. Trong thực tế, không nhất thiết phải duplicate model ID trong mọi document nếu index chỉ chứa một model version, nhưng cần có cách kiểm soát model version khi re-embed hoặc migrate.

### 1.5. Chuẩn hóa nội dung trước khi embedding

Document text và query text nên dùng preprocessing tương thích:

- Xác định field nào được embed: title, description, body hay nội dung đã ghép.
- Loại bỏ markup hoặc boilerplate không có giá trị tìm kiếm.
- Giữ ngữ cảnh quan trọng như tên sản phẩm, mã, ngôn ngữ và đơn vị.
- Giới hạn độ dài theo input token limit của model.
- Tránh dùng hai pipeline preprocessing khác nhau nếu không có chủ đích.

Nếu document embedding được tạo từ title + description nhưng query embedding được tạo từ một cấu trúc khác, cần đánh giá chất lượng retrieval bằng dữ liệu thực tế.

## 2. Chọn kiểu tìm kiếm vector

### 2.1. Approximate kNN

Approximate k-nearest neighbors (kNN) dùng cấu trúc vector index như HNSW để tìm các vector gần nhất mà không phải chấm điểm mọi document.

Ưu điểm:

- Độ trễ thấp hơn khi tập dữ liệu lớn.
- Phù hợp cho retrieval top-k ở quy mô production.
- Có thể kết hợp filter để giới hạn tập ứng viên.

Đổi lại, kết quả là gần đúng. Một số neighbor thật sự gần nhất có thể không nằm trong tập candidate được duyệt.

### 2.2. Exact vector scoring bằng script_score

Exact search có thể tính similarity trên mọi document khớp query/filter bằng script_score.

Ưu điểm:

- Tính điểm chính xác trên tập document đã lọc.
- Có thể hữu ích khi tập ứng viên nhỏ.
- Dễ kết hợp một điều kiện nghiệp vụ làm pre-filter.

Nhược điểm:

- Chi phí tăng theo số document được chấm điểm.
- Không phù hợp để brute-force toàn index lớn.
- Script phải được thiết kế và giới hạn cẩn thận.

### 2.3. So sánh

| Tiêu chí | Approximate kNN | Exact script_score |
|---|---|---|
| Cách tính | Tìm qua vector index | Chấm điểm từng document trong tập lọc |
| Độ chính xác | Gần đúng | Chính xác trên tập được chấm |
| Khả năng mở rộng | Phù hợp tập lớn | Phù hợp tập nhỏ/đã lọc hẹp |
| Tham số chính | k, num_candidates | Query filter và vector scoring script |
| Tình huống | Semantic retrieval phổ biến | Subset nhỏ, cần exact scoring |

Đừng chọn exact chỉ vì tên “exact” nghe tốt hơn. Nếu filter vẫn khớp hàng triệu document, script_score có thể tạo tải rất lớn.

### 2.4. kNN query và kNN search là hai cách đặt request

Elasticsearch có hai vị trí quan trọng cho kNN:

- Top-level knn trong search request, thường được biểu diễn bằng KnnSearch.
- Query DSL knn nằm trong query, được biểu diễn bằng KnnQuery.

Chúng có tham số và cách kết hợp khác nhau. Với một search request có thể kết hợp top-level knn và query lexical. Với một query DSL, KnnQuery có thể được đặt trong bool/query composition theo semantics được server hỗ trợ.

## 3. Chuẩn bị dense_vector mapping

### 3.1. Khai báo vector field

Một vector field cần có số chiều khớp với model embedding. Ví dụ model trả 768 chiều:

~~~json
{
  "mappings": {
    "properties": {
      "title": {
        "type": "text"
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

dims phải khớp số phần tử của mọi vector được index và query. Với approximate kNN, vector field cần được cấu hình indexing phù hợp; hãy kiểm tra mapping và default của Elasticsearch version đang chạy thay vì giả định.

### 3.2. Ánh xạ bằng Spring Data Elasticsearch

Spring Data có FieldType.Dense_Vector và thuộc tính dims:

~~~java
@Document(indexName = "articles-v1")
public class ArticleDocument {

    @Id
    private String id;

    @Field(type = FieldType.Text)
    private String title;

    @Field(type = FieldType.Text)
    private String content;

    @Field(type = FieldType.Dense_Vector, dims = 768)
    private float[] embedding;
}
~~~

Ví dụ giả định model trả vector 768 chiều. Có thể dùng float[], List<Float> hoặc kiểu phù hợp với converter/client của dự án. Hãy xác nhận kiểu Java được hỗ trợ bởi phiên bản Spring Data và serializer đang dùng.

### 3.3. Các thuộc tính Dense_Vector theo version

Spring Data Elasticsearch thêm hỗ trợ vector mapping qua nhiều release:

- dims cho FieldType.Dense_Vector có từ Spring Data Elasticsearch 4.2.
- elementType, knnSimilarity và knnIndexOptions có từ 5.4.
- Tên enum và cách serialize mapping phải khớp phiên bản Spring Data/Elasticsearch đang chạy.

Nếu muốn cấu hình similarity hoặc index options bằng annotation, kiểm tra API docs của đúng release. Đừng copy thuộc tính chỉ xuất hiện từ 5.4 vào dự án 5.3 hoặc cũ hơn.

### 3.4. Chọn similarity

Các metric phổ biến gồm:

- cosine: so sánh góc giữa vector.
- dot_product: tích vô hướng; semantics và yêu cầu phụ thuộc element type/vector normalization.
- l2_norm: dựa trên khoảng cách Euclidean.
- max_inner_product: phù hợp với một số embedding và scoring setup.

Metric phải phù hợp với cách model tạo vector. Không thay similarity chỉ để tăng score. Nếu đổi metric hoặc model, cần đánh giá retrieval và thường phải reindex/re-embed.

### 3.5. Kiểm tra vector trước khi index

Trước khi lưu:

- Đảm bảo vector không null.
- Đảm bảo số chiều đúng.
- Đảm bảo mọi giá trị là số hữu hạn, không phải NaN hoặc Infinity.
- Áp dụng normalization nếu model/metric yêu cầu.
- Lưu model/version metadata.
- Không trộn vector từ nhiều model trong cùng field nếu chúng không tương thích.

Có thể kiểm tra trong application service:

~~~java
private void validateEmbedding(float[] vector, int expectedDimensions) {
    if (vector == null || vector.length != expectedDimensions) {
        throw new IllegalArgumentException("Unexpected embedding dimensions");
    }

    for (float value : vector) {
        if (!Float.isFinite(value)) {
            throw new IllegalArgumentException("Embedding contains a non-finite value");
        }
    }
}
~~~

Kiểm tra ở ứng dụng giúp phát hiện lỗi sớm; Elasticsearch vẫn kiểm tra mapping và payload khi nhận request.

### 3.6. Index document có vector

Ví dụ với Spring Data:

~~~java
ArticleDocument document = new ArticleDocument();
document.setId("A-1001");
document.setTitle("Designing resilient services");
document.setContent("...");
document.setEmbedding(embeddingModel.embed(document.getContent()));

articleRepository.save(document);
~~~

embeddingModel là abstraction của ứng dụng, không phải class mặc định của Spring Data Elasticsearch. Có thể gọi embedding provider trước khi save hoặc xây dựng indexing pipeline riêng để retry và batch độc lập.

## 4. NativeQuery là gì?

### 4.1. Vai trò của NativeQuery

Spring Data Elasticsearch cung cấp một số query abstraction:

- CriteriaQuery: tạo query qua API tiêu chí đơn giản.
- StringQuery: gửi Query DSL dạng JSON string.
- NativeQuery: dùng các query builder của Elasticsearch Java API Client.

NativeQuery phù hợp khi cần query phức tạp hoặc tính năng không biểu diễn thuận tiện bằng Criteria API, ví dụ kNN, aggregation, nested query, script, highlight và các cấu trúc Query DSL nâng cao.

### 4.2. Import NativeQuery đúng package

Với Elasticsearch Java API Client integration (ELC), NativeQuery nằm trong package:

~~~java
import org.springframework.data.elasticsearch.client.elc.NativeQuery;
~~~

Không nhầm với các lớp query cũ từ những thế hệ client trước. Kiểm tra dependency tree và IDE import để chắc chắn class được lấy từ Spring Data Elasticsearch release mà dự án sử dụng.

### 4.3. Ví dụ query thông thường

~~~java
NativeQuery query = NativeQuery.builder()
    .withQuery(q -> q
        .match(m -> m
            .field("title")
            .query("resilient services")
        )
    )
    .withPageable(PageRequest.of(0, 10))
    .build();

SearchHits<ArticleDocument> hits =
    operations.search(query, ArticleDocument.class);
~~~

Builder dùng lambda của Elasticsearch Java API Client. Đây là một trong những điểm khác với query builder của RestHighLevelClient cũ.

### 4.4. NativeQuery không phải raw HTTP

NativeQuery tạo request thông qua Java API Client. Ứng dụng không cần tự ghép URL hoặc JSON string cho từng query.

Lợi ích:

- Compile-time API cho nhiều cấu trúc query.
- Type-safe builder.
- Kết hợp với Spring Data mapping.
- Kết quả được chuyển thành SearchHits<T>.
- Có thể thêm pageable, sort, filter, aggregation và source filtering.

Nếu API mới của Elasticsearch chưa được NativeQueryBuilder expose, có thể dùng Java API Client trực tiếp.

## 5. Thực hiện kNN bằng NativeQuery

### 5.1. Ví dụ với Spring Data Elasticsearch 5.4 trở lên

Từ 5.4, builder cung cấp withKnnSearches để khai báo top-level kNN search:

~~~java
import org.springframework.data.elasticsearch.client.elc.NativeQuery;
import org.springframework.data.elasticsearch.core.SearchHits;

List<Float> queryVector = embeddingService.embed(queryText);

NativeQuery query = NativeQuery.builder()
    .withKnnSearches(knn -> knn
        .field("embedding")
        .queryVector(queryVector)
        .k(10)
        .numCandidates(100)
    )
    .withPageable(PageRequest.of(0, 10))
    .build();

SearchHits<ArticleDocument> hits =
    operations.search(query, ArticleDocument.class);
~~~

Các giá trị ví dụ:

- field: tên dense_vector field trong mapping.
- queryVector: vector của câu hỏi.
- k: số nearest neighbors cần lấy.
- numCandidates: số candidate được xem xét trên mỗi shard trước khi hợp nhất kết quả.

Vector query phải có cùng số chiều và cùng embedding space với vector đã index.

### 5.2. Thêm filter vào kNN

Ví dụ chỉ tìm trong tenant và trạng thái được phép:

~~~java
NativeQuery query = NativeQuery.builder()
    .withKnnSearches(knn -> knn
        .field("embedding")
        .queryVector(queryVector)
        .k(10)
        .numCandidates(100)
        .filter(filter -> filter
            .bool(bool -> bool
                .filter(f -> f
                    .term(term -> term
                        .field("tenantId")
                        .value(tenantId)
                    )
                )
                .filter(f -> f
                    .term(term -> term
                        .field("published")
                        .value(true)
                    )
                )
            )
        )
    )
    .withPageable(PageRequest.of(0, 10))
    .build();
~~~

Filter trong kNN search có semantics pre-filter: Elasticsearch tìm top k trong tập document thỏa filter. Điều này quan trọng khi tenant hoặc trạng thái phải được áp dụng trước khi chọn nearest neighbors.

Điều kiện tenant vẫn phải được xác định từ principal đã xác thực. Không tin tenantId tùy ý do client gửi lên như một cơ chế authorization.

### 5.3. Chọn k và num_candidates

- k là số kết quả vector mong muốn.
- num_candidates là số candidate được xem xét trên mỗi shard.
- num_candidates phải đủ lớn so với k và chịu giới hạn của server version.
- Tăng num_candidates thường cải thiện recall nhưng tăng CPU/latency.

Bắt đầu bằng một giá trị vừa phải rồi đo recall và latency với dữ liệu thật. Không đặt num_candidates cực lớn theo mặc định.

### 5.4. Dùng SearchHits để đọc score

Spring Data trả SearchHits<T>:

~~~java
for (SearchHit<ArticleDocument> hit : hits) {
    ArticleDocument article = hit.getContent();
    float score = hit.getScore();

    log.debug("articleId={}, score={}", article.getId(), score);
}
~~~

Score biểu thị mức phù hợp theo scoring của query. Không coi score như xác suất hoặc phần trăm độ tương đồng nếu chưa có bước calibration riêng.

### 5.5. Lấy kết quả trong ReactiveElasticsearchOperations

Có thể truyền cùng loại Query vào reactive operations:

~~~java
Mono<ReactiveSearchHits<ArticleDocument>> result =
    reactiveOperations.search(query, ArticleDocument.class);
~~~

ReactiveSearchHits cung cấp metadata của search và stream các SearchHit<T> theo API của phiên bản. Dùng reactive pipeline để xử lý kết quả; không gọi block() trong event-loop của ứng dụng.

## 6. Khác biệt NativeQueryBuilder trước và sau Spring Data 5.4

### 6.1. Thay đổi tên và kiểu builder

Một điểm breaking change quan trọng:

| Spring Data Elasticsearch | API top-level kNN trong NativeQueryBuilder |
|---|---|
| 4.4 đến 5.3 | Có API withKnnQuery theo phiên bản |
| 5.4 trở lên | withKnnSearches |

Từ 5.4, Spring Data thay withKnnQuery bằng withKnnSearches cho top-level kNN search. Không phải chỉ đổi tên method: Elasticsearch Java API Client có hai class khác nhau:

- KnnSearch: top-level kNN trong search request.
- KnnQuery: kNN query nằm trong Query DSL.

### 6.2. Nếu cần KnnQuery trong Query DSL ở 5.4+

Tạo query bằng Elasticsearch Java API Client rồi truyền vào withQuery:

~~~java
import co.elastic.clients.elasticsearch._types.query_dsl.Query;

Query knnQuery = Query.of(q -> q
    .knn(knn -> knn
        .field("embedding")
        .queryVector(queryVector)
        .k(10)
        .numCandidates(100)
    )
);

NativeQuery query = NativeQuery.builder()
    .withQuery(knnQuery)
    .withPageable(PageRequest.of(0, 10))
    .build();
~~~

Đây là Query DSL kNN, không phải top-level KnnSearch. Dùng cách này khi cần đặt kNN trong cấu trúc query DSL mà server version hỗ trợ.

### 6.3. Không thay KnnSearch bằng KnnQuery một cách máy móc

Hai class có thể có tên field tương tự nhưng được gửi ở vị trí khác nhau trong search request. Hãy quyết định dựa trên semantics:

- Muốn top-level vector retrieval kết hợp lexical query ở search request: xem withKnnSearches.
- Muốn kNN nằm bên trong bool/query composition: tạo KnnQuery qua withQuery.
- Muốn API mới chưa được builder hỗ trợ: gọi Elasticsearch Java API Client trực tiếp.

### 6.4. Dự án 5.3 trở xuống

Nếu dependency đang ở 5.3 hoặc cũ hơn, đừng copy code 5.4+ mà kỳ vọng compile. Kiểm tra Javadoc và migration guide đúng version để xác định builder method hiện có.

Nếu cần một tính năng chưa được expose, có thể dùng Java API Client tương thích với release train đang dùng, nhưng không override client dependency tùy tiện. Tốt hơn là nâng Spring Data theo dependency management đã được hỗ trợ khi tính năng yêu cầu API mới.

### 6.5. Dự án trước Spring Data Elasticsearch 4.4

Các ví dụ cũ có thể sử dụng NativeSearchQuery, NativeSearchQueryBuilder và RestHighLevelClient. Đây là thế hệ API khác.

Không trộn:

- NativeSearchQuery với NativeQuery.
- Builder của RestHighLevelClient với builder của Elasticsearch Java API Client.
- Client dependency version tùy ý với Spring Data dependency management.

Khi nâng cấp từ API cũ, đọc migration guide theo từng release và kiểm tra compatibility matrix giữa Spring Data và Elasticsearch server.

## 7. Hybrid search: kết hợp từ khóa và vector

### 7.1. Vì sao cần hybrid search?

Vector retrieval tìm nội dung tương đồng về ý nghĩa, nhưng có thể bỏ qua một số tín hiệu exact-match quan trọng:

- SKU hoặc mã sản phẩm.
- Tên riêng.
- Số hiệu model.
- Từ khóa bắt buộc.
- Cụm từ chính xác trong tiêu đề.

BM25/full-text search tìm lexical match tốt, còn vector search tìm semantic similarity. Kết hợp hai nguồn có thể tăng chất lượng retrieval.

### 7.2. Kết hợp query lexical và top-level kNN

Ví dụ với Spring Data 5.4+:

~~~java
NativeQuery query = NativeQuery.builder()
    .withQuery(q -> q
        .match(m -> m
            .field("content")
            .query(queryText)
            .boost(1.0f)
        )
    )
    .withKnnSearches(knn -> knn
        .field("embedding")
        .queryVector(queryVector)
        .k(50)
        .numCandidates(200)
        .boost(1.0f)
        .filter(f -> f
            .term(t -> t
                .field("published")
                .value(true)
            )
        )
    )
    .withPageable(PageRequest.of(0, 10))
    .build();
~~~

Search request kết hợp kết quả lexical và vector theo semantics top-level kNN. Elasticsearch có thể hợp nhất score từ các nhánh này. boost thay đổi trọng số nhưng không tự làm cho hai thang điểm trở nên tương đương.

### 7.3. Vì sao cộng score trực tiếp có thể không ổn định?

BM25 score và vector similarity có phân phối khác nhau. Nếu chỉ cộng score với boost tùy ý:

- Một nhánh có thể lấn át nhánh kia.
- Kết quả có thể thay đổi mạnh theo corpus.
- Điều chỉnh model embedding có thể làm ranking lệch.
- Một số query exact-match có thể bị vector result đẩy xuống.

Cần đánh giá ranking trên tập query có nhãn hoặc relevance judgment thay vì chọn boost bằng cảm tính.

### 7.4. Reciprocal Rank Fusion (RRF)

RRF kết hợp thứ hạng của nhiều retriever thay vì cộng trực tiếp raw score. Nó giúp cân bằng kết quả lexical và vector khi hai score không cùng thang đo.

Elasticsearch hỗ trợ retriever APIs và RRF theo phiên bản server/client. Nếu Spring Data NativeQueryBuilder của dự án chưa expose retriever structure cần dùng, gọi Elasticsearch Java API Client trực tiếp với request model mà client version hỗ trợ.

Không giả định một retriever API có mặt trong mọi Elasticsearch 8.x hoặc mọi Spring Data release. Kiểm tra server version và generated Java client trước khi triển khai.

### 7.5. Hybrid query không tự tạo embedding

Ví dụ hybrid trên vẫn cần queryVector được tạo trước. Phần lexical query nhận queryText, còn vector branch nhận embedding từ cùng model đã dùng lúc index.

Giữ hai nhánh input cùng một request context để tránh lexical search theo query A nhưng vector search theo query B.

## 8. Dùng script_score cho exact semantic scoring

### 8.1. Giới hạn tập document trước khi tính vector score

Ví dụ Query DSL:

~~~json
{
  "query": {
    "script_score": {
      "query": {
        "bool": {
          "filter": [
            { "term": { "tenantId": "tenant-1" } },
            { "term": { "published": true } }
          ]
        }
      },
      "script": {
        "source": "cosineSimilarity(params.query_vector, 'embedding') + 1.0",
        "params": {
          "query_vector": [0.12, -0.08, 0.31, 0.04]
        }
      }
    }
  }
}
~~~

Đây là ví dụ rút gọn; vector thực tế phải có đúng số chiều của mapping. Query filter thu hẹp tập document trước khi script tính similarity.

### 8.2. Dùng NativeQuery với script_score

Có thể xây query qua Elasticsearch Java API Client:

~~~java
NativeQuery query = NativeQuery.builder()
    .withQuery(q -> q
        .scriptScore(ss -> ss
            .query(inner -> inner
                .bool(b -> b
                    .filter(f -> f
                        .term(t -> t
                            .field("tenantId")
                            .value(tenantId)
                        )
                    )
                )
            )
            .script(script -> script
                .source(
                    "cosineSimilarity(params.query_vector, 'embedding') + 1.0"
                )
                .params("query_vector", JsonData.of(queryVector))
            )
        )
    )
    .withPageable(PageRequest.of(0, 10))
    .build();
~~~

Tên builder method và cách truyền JsonData cần khớp Elasticsearch Java API Client version của dự án. Nếu builder không expose một script option cụ thể, có thể tạo Query trực tiếp từ client model rồi truyền vào NativeQuery.

### 8.3. Không dùng script_score cho toàn index lớn

script_score tính điểm cho từng document trong tập query bên trong. Nếu inner query match quá rộng, CPU cost có thể cao.

Dùng nó khi:

- Filter đã thu hẹp dữ liệu đáng kể.
- Cần exact scoring.
- Corpus nhỏ.
- Đang đánh giá chất lượng hoặc làm reranking một tập candidate.

Với tập lớn, approximate kNN thường là lựa chọn phù hợp hơn.

## 9. Gọi Elasticsearch Java API Client trực tiếp

### 9.1. Khi nào cần client trực tiếp?

Dùng client trực tiếp khi:

- Spring Data builder chưa expose request option mới.
- Cần retriever API hoặc search feature mới.
- Cần response metadata mà abstraction không cung cấp.
- Cần dùng API Elasticsearch chuyên biệt.
- Muốn kiểm soát chính xác request/response của một integration.

Nếu chỉ cần bool, match, filter, kNN hoặc aggregation mà NativeQuery hỗ trợ, giữ query ở Spring Data thường đơn giản hơn.

### 9.2. Inject client đã được cấu hình

Ví dụ service nhận ElasticsearchClient từ Spring:

~~~java
import co.elastic.clients.elasticsearch.ElasticsearchClient;

@Service
public class SemanticSearchClient {

    private final ElasticsearchClient client;

    public SemanticSearchClient(ElasticsearchClient client) {
        this.client = client;
    }
}
~~~

Bean phải được tạo từ cùng cấu hình endpoint, TLS và credential mà ứng dụng sử dụng. Không tạo một client thứ hai với endpoint hoặc authentication khác chỉ để chạy một query.

Tên bean và cách auto-configuration phụ thuộc Spring Boot/Spring Data release; inject theo type hoặc cấu hình bean rõ ràng trong dự án.

### 9.3. Chạy top-level kNN trực tiếp

~~~java
SearchResponse<ArticleDocument> response =
    client.search(search -> search
        .index("articles-v1")
        .knn(knn -> knn
            .field("embedding")
            .queryVector(queryVector)
            .k(10)
            .numCandidates(100)
        )
        .size(10),
        ArticleDocument.class
    );
~~~

Đây là Java API Client style. Generated method và kiểu vector có thể thay đổi theo Elasticsearch client major version. Kiểm tra API docs của đúng co.elastic.clients:elasticsearch-java trong dependency tree.

### 9.4. Gọi client trực tiếp khác với Spring Data mapping

Khi dùng ElasticsearchOperations.search, Spring Data áp dụng mapping metadata và conversion service của domain type.

Khi gọi ElasticsearchClient.search trực tiếp, client dùng JsonpMapper/serializer của transport để deserialize response. Không mặc định mọi annotation hoặc custom converter của Spring Data đều được áp dụng giống hệt.

Nếu entity phụ thuộc custom conversion, field name mapping hoặc type conversion của Spring Data, hãy cân nhắc:

- Dùng NativeQuery qua ElasticsearchOperations.
- Tạo response DTO riêng cho low-level client.
- Chuyển đổi response bằng mapper rõ ràng.
- Kiểm tra source/field names trong JSON.

### 9.5. Không dùng client cũ trong code mới

RestHighLevelClient là client thế hệ cũ. Spring Data Elasticsearch hiện đại dùng Elasticsearch Java API Client trong ELC integration. Một dự án cũ có thể còn dùng client cũ theo version, nhưng không nên trộn API cũ và mới trong cùng ví dụ mà không nêu rõ dependency.

## 10. Chọn cách query theo phiên bản

### 10.1. Bắt đầu từ dependency thực tế

Kiểm tra version Spring Data Elasticsearch và Elasticsearch Java API Client mà build resolve. Đừng chỉ dựa vào version ghi trong build.gradle nếu Spring Boot BOM hoặc dependency constraint quản lý version gián tiếp.

Maven:

~~~bash
mvn dependency:tree -Dincludes=org.springframework.data:spring-data-elasticsearch,co.elastic.clients:elasticsearch-java
~~~

Gradle:

~~~bash
./gradlew dependencyInsight --dependency spring-data-elasticsearch --configuration runtimeClasspath
./gradlew dependencyInsight --dependency elasticsearch-java --configuration runtimeClasspath
~~~

### 10.2. Compatibility matrix là nguồn quyết định

Spring Data công bố bảng version theo release train, bao gồm Spring Data Elasticsearch và Elasticsearch server version tương ứng.

Ví dụ các release train gần đây trong compatibility table:

| Spring Data release train | Spring Data Elasticsearch | Elasticsearch được tham chiếu |
|---|---:|---:|
| 2026.0 | 6.1.x | 9.4.7 |
| 2025.1 | 6.0.x | 9.2.2 |
| 2025.0 | 5.5.x | 8.18.1 |
| 2024.1 | 5.4.x | 8.15.5 |
| 2024.0 | 5.3.x | 8.13.4 |
| 2023.1 | 5.2.x | 8.11.1 |

Các con số trên là mốc trong compatibility table tại thời điểm tài liệu được tham khảo; chúng không phải lời khuyên nâng mọi ứng dụng lên version mới nhất. Hãy kiểm tra bảng hiện hành và release train mà Spring Boot của dự án đang sử dụng.

### 10.3. Hướng dẫn chọn API

| Phiên bản Spring Data Elasticsearch | Cách tiếp cận |
|---|---|
| Trước 4.4 | Có thể gặp NativeSearchQuery/RestHighLevelClient API cũ; đọc migration guide |
| 4.4 đến 5.3 | NativeQuery dùng Elasticsearch Java API Client; kiểm tra API kNN của đúng minor |
| 5.4 trở lên | withKnnSearches cho top-level kNN; KnnQuery có thể được tạo trong Query DSL |
| 6.x | Dùng Java API Client version được release train quản lý; kiểm tra API server 9.x tương ứng |

Không lấy bảng này thay thế compatibility matrix chính thức. Nó chỉ định hướng lựa chọn API.

### 10.4. Khi nâng từ 5.3 lên 5.4

Migration guide nêu rõ withKnnQuery trong NativeQueryBuilder được thay bằng withKnnSearches cho kNN search. Đồng thời phân biệt KnnSearch top-level và KnnQuery trong Query DSL.

Khi nâng:

1. Cập nhật Spring Data theo release train tương thích.
2. Kiểm tra version Java API Client được resolve.
3. Sửa import và builder method.
4. Xác định query đang dùng top-level kNN hay Query DSL kNN.
5. Chạy integration test với server version được hỗ trợ.
6. Đánh giá lại filter và ranking semantics.

### 10.5. Không override Elasticsearch Java API Client tùy tiện

Spring Data phụ thuộc các class generated từ client version cụ thể. Nếu tự nâng client riêng, có thể gặp:

- NoSuchMethodError.
- ClassNotFoundException.
- Lỗi serialize/deserialize.
- Request model không khớp server.
- API builder không có method trong code mẫu.

Ưu tiên để Spring Boot BOM/Spring Data dependency management chọn client version. Chỉ override khi có compatibility evidence và test đầy đủ.

## 11. Semantic field và inference do Elasticsearch quản lý

### 11.1. dense_vector với embedding tự tạo

Với dense_vector thông thường:

1. Ứng dụng tạo document embedding.
2. Lưu vector trong field.
3. Ứng dụng tạo query embedding.
4. Gửi query_vector trong kNN request.

Đây là mô hình bring-your-own-vectors. Ứng dụng kiểm soát model, preprocessing và version.

### 11.2. semantic_text và inference workflow

Một số Elasticsearch version hỗ trợ semantic_text và inference integration để tạo hoặc sử dụng embedding trong Elasticsearch. Khi dùng field loại này, request có thể dùng text input và query vector builder theo model/inference configuration.

Điểm quan trọng:

- Tính năng phụ thuộc Elasticsearch server version và inference setup.
- Model/deployment phải sẵn sàng.
- Document và query phải dùng cùng model semantics.
- Không giả định semantic_text có thể dùng mọi top-level kNN parameter giống dense_vector.

### 11.3. Top-level knn và semantic_text

Tài liệu Elasticsearch hiện hành phân biệt:

- Top-level knn search option hỗ trợ dense_vector đã index.
- Với semantic hoặc semantic_text field, dùng knn query trong Query DSL theo hướng dẫn của server version.
- Có thể dùng match query trên semantic_text trong một số workflow để server thực hiện inference phù hợp.

Vì vậy, nếu dùng semantic_text, không copy ví dụ top-level withKnnSearches cho dense_vector rồi kỳ vọng tự hoạt động. Hãy chọn đúng query form được server hỗ trợ.

### 11.4. Query vector builder

Một request có thể dùng query_vector_builder thay vì truyền vector đã tạo:

~~~json
{
  "query": {
    "knn": {
      "field": "semantic_field",
      "k": 10,
      "num_candidates": 100,
      "query_vector_builder": {
        "text_embedding": {
          "model_id": "my-embedding-model",
          "model_text": "How do I design resilient services?"
        }
      }
    }
  }
}
~~~

Đây là ví dụ Elasticsearch Query DSL. Với semantic_text, model ID có thể được suy ra từ mapping tùy cấu hình; với dense_vector hoặc model khác, có thể cần chỉ định rõ model. Kiểm tra đúng API version trước khi triển khai.

## 12. Bộ lọc và bảo mật trong semantic search

### 12.1. Filter trước khi lấy nearest neighbors

Nếu người dùng chỉ được tìm trong một tenant, filter phải nằm trong request kNN theo semantics pre-filter được hỗ trợ.

Không lấy top 10 vector trên toàn bộ index rồi mới lọc tenant ở Java. Cách đó có thể:

- Làm mất kết quả hợp lệ của tenant vì top 10 toàn cục thuộc tenant khác.
- Tốn tài nguyên không cần thiết.
- Tạo nguy cơ lộ metadata nếu kết quả trung gian bị log hoặc xử lý sai.

### 12.2. Filter theo trạng thái nghiệp vụ

Có thể lọc theo:

- published = true.
- language.
- documentType.
- tenantId.
- accessLevel.
- validFrom/validTo.
- deleted = false.

Các filter phải dùng field mapping phù hợp, thường là keyword, boolean hoặc date.

### 12.3. Đừng nhầm relevance với authorization

Semantic score chỉ xếp hạng mức liên quan. Nó không quyết định người dùng được phép đọc document hay không.

Authorization phải được thực hiện ở service/security layer và filter phù hợp phải được đưa vào Elasticsearch request. Nếu cần isolation mạnh, cân nhắc index/key riêng hoặc Elasticsearch security features.

### 12.4. Filter ảnh hưởng recall

Filter quá hẹp có thể làm query không có kết quả dù vector gần nhất nằm ngoài filter. Điều này không nhất thiết là lỗi embedding.

Khi debug, ghi nhận filter criteria (không chứa dữ liệu nhạy cảm), số document khớp filter và số hit trả về.

## 13. Pagination, score và kết quả tìm kiếm

### 13.1. Top-k là contract chính của vector retrieval

kNN thường được thiết kế để lấy top-k nearest neighbors. Không giả định có thể dùng offset pagination sâu như search lexical thông thường với mọi kNN request.

Nếu giao diện cần nhiều trang, hãy đánh giá chiến lược retrieval, candidate window và API paging của server version. Có thể dùng một bước reranking hoặc lưu danh sách candidate theo session nếu cần trải nghiệm paging ổn định.

### 13.2. SearchHits cung cấp metadata

Spring Data SearchHits<T> có thể chứa:

- Total hits và relation.
- Max score.
- Danh sách SearchHit<T>.
- Score từng hit.
- Sort values.
- Highlight fields.
- Aggregations và suggest results nếu query yêu cầu.

Dùng metadata này để xây response DTO. Không trả toàn bộ Elasticsearch internal response ra public API nếu không cần.

### 13.3. Score không phải xác suất

Vector score phụ thuộc similarity function và cách Elasticsearch biến metric thành score. BM25 score cũng có semantics riêng.

Không diễn giải 0.82 thành “82% giống nhau” nếu không có calibration dataset và định nghĩa thống kê phù hợp.

### 13.4. Reranking

Một pipeline có thể:

1. Lấy 50-200 candidate bằng lexical và vector retrieval.
2. Kết hợp candidate bằng RRF.
3. Rerank một tập nhỏ bằng cross-encoder hoặc model chuyên biệt.
4. Trả top 10.

Reranking tăng chi phí và latency, nên giới hạn số candidate. Có thể chạy model reranker bên ngoài Elasticsearch hoặc dùng tính năng server hỗ trợ trong phiên bản cụ thể.

## 14. Tối ưu chất lượng và hiệu năng

### 14.1. Đo recall và latency

Theo dõi:

- Recall@k hoặc metric relevance tương đương.
- NDCG/MRR nếu có relevance judgments.
- Query latency p50/p95/p99.
- Indexing throughput.
- Kích thước vector index.
- Memory/page cache.
- Candidate count và filter selectivity.
- Số document không có embedding.

Không đánh giá chất lượng chỉ bằng một vài query tự chọn.

### 14.2. Tuning num_candidates

Tăng num_candidates thường cải thiện recall nhưng tăng chi phí. Thử một số mức trên tập dữ liệu đại diện và so sánh latency/recall.

Không dùng một giá trị cố định cho mọi index nếu shard count, vector dimension và dữ liệu khác nhau đáng kể.

### 14.3. Vector dimension và memory

Vector dimension lớn làm tăng dung lượng và chi phí tính toán. Không chọn model chỉ vì dimension cao hơn.

Đánh giá:

- Chất lượng semantic retrieval.
- Memory footprint.
- Index size.
- Ingest throughput.
- Query latency.
- Chi phí embedding inference.

Quantization và index options có thể giảm footprint nhưng có trade-off về recall/accuracy; hỗ trợ phụ thuộc server version và mapping configuration.

### 14.4. Tối ưu filter và shard layout

Filter theo tenant, language hoặc document type có thể ảnh hưởng số candidate. Đánh giá shard count và data partitioning cùng query workload.

Không tạo quá nhiều shard nhỏ chỉ để filter nhanh. Shard design cần xét cả ingest, search concurrency, memory và cluster overhead.

### 14.5. Giữ vector trong page cache

Approximate kNN cần vector index được truy cập hiệu quả. Nếu vector data không phù hợp với memory/page cache, latency có thể tăng mạnh.

Theo dõi node memory, page cache, disk I/O và search thread pool. Cấu hình heap Elasticsearch không thay thế nhu cầu memory/page cache cho vector index.

## 15. Lỗi thường gặp

| Dấu hiệu | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| withKnnSearches không compile | Spring Data đang ở trước 5.4 hoặc dependency bị lệch | Kiểm tra dependency tree và migration guide |
| withKnnQuery không còn tồn tại | Đã nâng lên 5.4+ | Dùng withKnnSearches hoặc tạo KnnQuery trong withQuery |
| KnnSearch và KnnQuery bị nhầm | Dùng sai vị trí kNN trong request | Xác định top-level search hay Query DSL |
| 400 vector dimension mismatch | Vector query không khớp dims | Kiểm tra model output và mapping |
| 400 field không hỗ trợ kNN | Field không phải dense_vector/indexed vector hoặc server không hỗ trợ | Kiểm tra mapping và server version |
| Query trả 0 hit | Filter quá hẹp, vector không được index hoặc model mismatch | Kiểm tra filter, dữ liệu và embedding pipeline |
| Recall kém | num_candidates thấp hoặc model/preprocessing không phù hợp | Đo recall và tune candidate/model |
| Query quá chậm | Candidate quá lớn, script_score trên tập rộng hoặc memory/page cache thiếu | Giảm phạm vi, dùng approximate kNN và đo tài nguyên |
| Score lexical lấn át vector | Hai score scale khác nhau | Tune boost bằng relevance test hoặc dùng RRF |
| Query chạy được nhưng mapping annotation lỗi | Thuộc tính vector chưa có trong Spring Data version | Kiểm tra FieldType/@Field Javadoc của release |
| Lỗi NoSuchMethodError | Spring Data và Elasticsearch Java API Client không tương thích | Để BOM quản lý client và kiểm tra dependency tree |
| Kết quả sai tenant | Filter không được áp dụng đúng hoặc tenant ID không đáng tin | Đưa authorization-derived filter vào request |
| Semantic text query bị từ chối | Dùng top-level knn không hỗ trợ field type đó | Dùng Query DSL kNN hoặc match theo server docs |
| Direct client deserialize sai field | Không dùng Spring Data mapping/converter | Dùng DTO hoặc mapping adapter riêng |
| Re-embed làm ranking bất thường | Trộn vector từ hai model version | Reindex/re-embed đồng bộ theo model version |

## 16. Quy trình triển khai semantic query

Khi xây semantic search bằng Spring Data Elasticsearch:

1. Xác định use case, loại nội dung và filter authorization.
2. Chọn embedding model và ghi nhận model version.
3. Xác định vector dimensions, metric và preprocessing.
4. Tạo index mapping dense_vector phù hợp với server version.
5. Sinh embedding cho document và index bằng ID ổn định.
6. Sinh query vector bằng cùng model.
7. Kiểm tra Spring Data release và Elasticsearch Java API Client version.
8. Dùng NativeQuery cho query builder được hỗ trợ.
9. Từ Spring Data 5.4+, dùng withKnnSearches cho top-level kNN search.
10. Nếu cần KnnQuery trong Query DSL, tạo query model và truyền qua withQuery.
11. Nếu builder không expose feature cần thiết, dùng Java API Client đã được cấu hình.
12. Thêm pre-filter cho tenant, trạng thái và quyền truy cập.
13. Kết hợp lexical/vector retrieval nếu use case cần exact match và semantic relevance.
14. Đánh giá RRF/reranking bằng relevance dataset.
15. Đo recall, latency, memory và indexing throughput.
16. Test integration với Elasticsearch server version tương thích.
17. Khi đổi model/dimension/mapping, tạo index version mới và re-embed có kiểm soát.

## 17. Những điểm cần ghi nhớ

- Semantic search cần embedding cho cả document và query; hai phía phải dùng cùng model semantics.
- dense_vector mapping phải khai báo đúng dimensions và cấu hình index/similarity phù hợp.
- NativeQuery dùng query builder của Elasticsearch Java API Client.
- ElasticsearchOperations.search giúp giữ Spring Data mapping và trả SearchHits<T>.
- Approximate kNN phù hợp retrieval quy mô lớn; script_score exact phù hợp tập nhỏ đã filter.
- k xác định số nearest neighbors, num_candidates ảnh hưởng recall và latency.
- Filter trong kNN nên áp dụng trước retrieval khi cần giới hạn tenant hoặc trạng thái.
- Từ Spring Data Elasticsearch 5.4, dùng withKnnSearches cho top-level kNN; KnnSearch khác KnnQuery.
- KnnQuery có thể được tạo từ Elasticsearch Java API Client và truyền qua NativeQueryBuilder.withQuery.
- Với version cũ, đọc Javadoc/migration guide tương ứng; không copy API mới vào dependency cũ.
- Gọi client trực tiếp khi Spring Data builder chưa hỗ trợ tính năng cần thiết, nhưng phải quản lý mapping/serialization rõ ràng.
- Hybrid search kết hợp lexical và vector; raw scores có thể khác thang đo, nên cân nhắc RRF.
- semantic_text và inference query có semantics/version khác dense_vector; chọn đúng query form.
- Score không phải xác suất và cần đánh giá bằng relevance data.
- Khi đổi embedding model hoặc dimension, không trộn vector không tương thích; hãy re-embed/reindex có versioning.
- Theo dõi recall, latency, page cache, memory, candidate count và lỗi mapping/query.

NativeQuery là đường tích hợp thuận tiện giữa Spring Data và Elasticsearch Java API Client cho các truy vấn semantic phức tạp. Khi chọn đúng query type, đúng builder theo release, đồng bộ embedding model và kiểm soát filter/ranking, ứng dụng có thể kết hợp semantic retrieval với các tính năng search khác mà vẫn giữ được mapping và kết quả trong hệ sinh thái Spring Data.

