# Phân biệt tìm kiếm từ khóa và tìm kiếm theo ý nghĩa

Trong Elasticsearch, tìm kiếm từ khóa (lexical search) và tìm kiếm theo ý nghĩa (semantic search) giải quyết hai cách diễn đạt truy vấn khác nhau. Lexical search tìm document dựa trên thuật ngữ xuất hiện trong nội dung đã được phân tích; nó phù hợp khi người dùng biết tên, mã, cụm từ hoặc từ khóa cụ thể. Semantic search biểu diễn truy vấn và nội dung thành vector embedding rồi tìm những document gần nhau trong không gian vector; nó phù hợp khi người dùng mô tả nhu cầu bằng ngôn ngữ tự nhiên, dùng từ đồng nghĩa hoặc không biết chính xác thuật ngữ trong tài liệu.

Hai cách không loại trừ nhau. Keyword search thường chính xác hơn với SKU, tên riêng, số hiệu, thuật ngữ kỹ thuật và điều kiện lọc. Semantic search thường tìm được nội dung liên quan dù không có từ trùng khớp. Hệ thống tìm kiếm tốt thường kết hợp lexical retrieval, vector retrieval và reranking để cân bằng độ chính xác, độ bao phủ và độ phù hợp ngữ nghĩa.

Bài học này giải thích inverted index, analyzer, BM25 và field text/keyword; embedding, vector similarity, kNN và chunking; cách tổ chức mapping và query trong Spring Data Elasticsearch; cách xây hybrid search; cách đánh giá relevance và vận hành pipeline embedding.

## 1. Hai cách hiểu khác nhau về một truy vấn

Giả sử kho tài liệu có một bài viết tên “Cách khôi phục dữ liệu sau khi ổ cứng bị hỏng”. Người dùng nhập:

~~~text
Làm sao lấy lại file khi máy tính không đọc được ổ cứng?
~~~

Keyword search có thể tìm các token như lấy lại, file, ổ cứng. Nếu tài liệu chỉ dùng các từ “khôi phục dữ liệu”, kết quả có thể không được xếp hạng cao do ít token trùng nhau.

Semantic search có thể nhận ra hai cách diễn đạt nói về cùng một ý định: khôi phục file từ ổ đĩa không truy cập được. Nó có thể tìm tài liệu dù các từ chính không trùng hoàn toàn.

Một ví dụ khác:

~~~text
Query: KB-100
Document: Bàn phím không dây model KB-100
~~~

Với truy vấn mã sản phẩm, lexical/exact search thường đáng tin cậy hơn. Embedding không được thiết kế để bảo đảm khớp chính xác từng ký tự của mã.

| Đặc điểm | Keyword / lexical search | Semantic search |
|---|---|---|
| Tín hiệu chính | Token, cụm từ, field và tần suất xuất hiện | Vector embedding và độ tương đồng |
| Từ đồng nghĩa | Phụ thuộc analyzer, synonym graph hoặc query expansion | Có thể tìm được qua ý nghĩa embedding |
| Mã, SKU, tên chính xác | Rất phù hợp khi mapping/query đúng | Có thể kém chính xác |
| Diễn đạt tự nhiên | Phụ thuộc mức trùng token | Thường phù hợp hơn |
| Khả năng giải thích | Có thể xem match, score, field và analyzer | Score biểu diễn độ tương đồng, khó diễn giải trực tiếp |
| Chi phí | Thường thấp, dùng inverted index | Cần tạo/lưu embedding và tính vector similarity |
| Dữ liệu cần chuẩn bị | Text và mapping phù hợp | Text, model embedding, vector mapping |

Không nên gọi mọi kiểu tìm kiếm văn bản là “exact keyword”. Trong Elasticsearch, field type keyword dùng cho giá trị không phân tích thành token; còn full-text search thường dùng field type text với analyzer. Cả hai đều thuộc lexical retrieval, nhưng phục vụ cách so khớp khác nhau.

## 2. Keyword search là gì?

Keyword search thường dựa trên inverted index. Thay vì quét từng document để tìm chuỗi, Elasticsearch phân tích nội dung thành token rồi xây chỉ mục ánh xạ từ token đến document chứa token đó.

Ví dụ các document:

~~~text
Document A: Spring Data Elasticsearch hỗ trợ repository.
Document B: Elasticsearch có thể tìm kiếm vector.
Document C: Spring Boot cấu hình repository.
~~~

Inverted index minh họa:

~~~text
spring        -> A, C
data          -> A
elasticsearch -> A, B
repository    -> A, C
vector        -> B
boot          -> C
~~~

Khi query chứa token Elasticsearch, engine tra inverted index để tìm candidate documents rồi tính điểm relevance.

### 2.1. Phân tích văn bản bằng analyzer

Trước khi lập chỉ mục hoặc chạy full-text query, analyzer có thể thực hiện:

1. Character filters: biến đổi chuỗi đầu vào trước khi tokenization.
2. Tokenizer: chia chuỗi thành token.
3. Token filters: lowercase, stemming, stop words, synonym và các biến đổi khác.

Ví dụ analyzer đơn giản có thể biến:

~~~text
Spring Data Elasticsearch
~~~

thành các token:

~~~text
spring
data
elasticsearch
~~~

Khi query được phân tích bằng analyzer tương thích, Elasticsearch có thể match document theo token thay vì cần chuỗi giống hệt.

Analyzer ảnh hưởng trực tiếp đến khả năng tìm kiếm. Nếu index dùng analyzer tiếng Anh nhưng nội dung là tiếng Việt, stemming và stop-word rules có thể không phù hợp. Với tiếng Việt, cần xem xét tokenizer, dấu tiếng Việt, từ ghép và cách tách từ theo domain.

### 2.2. Field text và field keyword

Elasticsearch có hai field type quan trọng:

- text: được phân tích thành token, phù hợp cho full-text search.
- keyword: giữ giá trị như một term, phù hợp cho exact match, sorting, aggregation và filtering.

Ví dụ mapping:

~~~json
{
  "mappings": {
    "properties": {
      "name": {
        "type": "text",
        "fields": {
          "keyword": {
            "type": "keyword"
          }
        }
      },
      "sku": {
        "type": "keyword"
      },
      "description": {
        "type": "text"
      },
      "category": {
        "type": "keyword"
      }
    }
  }
}
~~~

Với mapping trên:

- name dùng match query để tìm theo token.
- name.keyword dùng term query để khớp toàn bộ giá trị đã index.
- sku dùng term query cho mã sản phẩm.
- description dùng match hoặc các full-text query khác.
- category dùng filter/aggregation.

### 2.3. Exact matching không giống full-text matching

Query term trên field keyword:

~~~json
{
  "query": {
    "term": {
      "sku": "KB-100"
    }
  }
}
~~~

Query match trên field text:

~~~json
{
  "query": {
    "match": {
      "description": "bàn phím không dây"
    }
  }
}
~~~

term tìm một term chính xác theo cách field được index. match phân tích query thành token rồi thực hiện full-text matching. Không dùng term query trên text field với kỳ vọng nó sẽ tự phân tích cụm từ giống match query.

### 2.4. Keyword search không nhất thiết yêu cầu mọi từ phải xuất hiện

Match query mặc định thường kết hợp các token theo operator OR. Có thể yêu cầu AND:

~~~json
{
  "query": {
    "match": {
      "description": {
        "query": "wireless mechanical keyboard",
        "operator": "and"
      }
    }
  }
}
~~~

Với AND, document phải match tất cả token sau khi phân tích. Điều này tăng tính chặt chẽ nhưng có thể bỏ lỡ tài liệu liên quan nếu người viết dùng từ đồng nghĩa hoặc khác cách diễn đạt.

## 3. Relevance scoring và BM25

Lexical search thường xếp hạng document bằng BM25, một thuật toán dựa trên tần suất term trong document, độ hiếm của term trong toàn bộ tập tài liệu và độ dài document.

Các trực giác chính:

- Term xuất hiện nhiều lần trong một document có thể làm document liên quan hơn, nhưng mức tăng không tuyến tính vô hạn.
- Term hiếm trong tập dữ liệu thường có sức phân biệt cao hơn term xuất hiện ở hầu hết document.
- Document dài được điều chỉnh để không luôn có lợi thế chỉ vì chứa nhiều từ.

Một truy vấn có hai term:

~~~text
Spring Elasticsearch
~~~

Document chứa cả hai term trong title có thể được xếp hạng cao hơn document chỉ chứa một term trong phần nội dung dài.

### 3.1. Boost field

Có thể tăng trọng số title so với description:

~~~json
{
  "query": {
    "multi_match": {
      "query": "reactive repository",
      "fields": [
        "title^4",
        "summary^2",
        "content"
      ]
    }
  }
}
~~~

Ký hiệu ^4 và ^2 là field boost. Tên bài được ưu tiên hơn summary, summary ưu tiên hơn content.

### 3.2. Filter và query context

Điều kiện nghiệp vụ nên dùng filter khi không cần score:

~~~json
{
  "query": {
    "bool": {
      "must": [
        {
          "multi_match": {
            "query": "reactive repository",
            "fields": ["title^3", "content"]
          }
        }
      ],
      "filter": [
        {
          "term": {
            "status": "PUBLISHED"
          }
        },
        {
          "term": {
            "tenantId": "tenant-7"
          }
        }
      ]
    }
  }
}
~~~

Query context ảnh hưởng relevance score; filter context chỉ kiểm tra điều kiện có/không và có thể được cache. Không để vector similarity hoặc BM25 thay thế authorization/tenant filtering.

### 3.3. Synonym trong lexical search

Synonym filter hoặc synonym graph giúp lexical search hiểu các từ tương đương đã khai báo:

~~~text
laptop, notebook
cell phone, mobile phone
elasticsearch, es
~~~

Điều này cải thiện recall mà không cần embedding. Tuy nhiên, synonym dictionary cần được quản lý theo domain và có thể làm query rộng hơn. Synonym không tự hiểu mọi cách diễn đạt mới như embedding model.

## 4. Semantic search là gì?

Semantic search chuyển nội dung thành vector số (embedding). Một embedding model nhận text và tạo một vector có nhiều chiều. Các văn bản có ý nghĩa gần nhau thường có vector gần nhau theo metric mà model được huấn luyện hỗ trợ.

Ví dụ minh họa:

~~~text
"cách khôi phục file đã xóa"
          |
          v
     Embedding model
          |
          v
 [0.12, -0.31, 0.08, ...]

"phục hồi tài liệu bị mất"
          |
          v
     Embedding model
          |
          v
 [0.11, -0.29, 0.10, ...]
~~~

Hai vector có thể gần nhau dù câu không chia sẻ nhiều token. Khi tìm kiếm, hệ thống tạo embedding cho query rồi tìm các document vector gần nhất.

### 4.1. Embedding không phải từ điển đồng nghĩa

Embedding học biểu diễn từ ngữ cảnh và dữ liệu huấn luyện. Nó có thể tìm quan hệ ngữ nghĩa mà không cần khai báo từng cặp synonym, nhưng không đảm bảo:

- Hai cụm từ đồng nghĩa luôn có vector gần nhau trong mọi domain.
- Mã sản phẩm hoặc số hiệu được phân biệt chính xác.
- Model hiểu thuật ngữ nội bộ chưa xuất hiện trong dữ liệu huấn luyện.
- Vector score là xác suất đúng.

Chất lượng phụ thuộc model, ngôn ngữ, domain, cách chunk, cách huấn luyện và query distribution.

### 4.2. Query và document phải dùng cùng không gian embedding

Vector của query và document cần được tạo bởi model tương thích:

- Cùng model hoặc model pair được thiết kế tương thích.
- Cùng số chiều (dimensions).
- Cùng cách normalize và preprocessing theo hướng dẫn model.
- Cùng phiên bản embedding contract.

Không thay model tạo query vector mà vẫn so với vector cũ nếu hai model không tương thích. Khi đổi model, thường cần tạo lại embedding cho toàn bộ document hoặc duy trì field/index version riêng.

### 4.3. Dense vector mapping

Một document có thể lưu text và embedding:

~~~json
{
  "mappings": {
    "properties": {
      "title": {
        "type": "text"
      },
      "content": {
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

Ở đây 768 chỉ là ví dụ. Dimensions phải khớp với output của embedding model. Chọn similarity theo model và cách tạo vector; cosine, dot product và L2 là các lựa chọn phổ biến.

### 4.4. Lưu embedding trong entity Spring Data

Ví dụ entity:

~~~java
@Document(indexName = "knowledge-articles")
public class KnowledgeArticle {

    @Id
    private String id;

    @Field(type = FieldType.Text)
    private String title;

    @Field(type = FieldType.Text)
    private String content;

    @Field(type = FieldType.Dense_Vector, dims = 768,
            similarity = "cosine")
    private float[] embedding;
}
~~~

Tên thuộc tính annotation và hỗ trợ vector mapping phụ thuộc Spring Data Elasticsearch release được dùng. Mapping index thực tế phải khớp dimensions, similarity và các tùy chọn dense_vector mà phiên bản Elasticsearch hỗ trợ.

Nếu dùng mapping được quản lý bằng JSON hoặc index template, hãy bảo đảm entity metadata và mapping thực tế không mâu thuẫn. Không để Spring tự tạo mapping dimensions khác với model output.

## 5. Vector similarity và k-nearest neighbors

Khi query đã được chuyển thành vector, Elasticsearch tìm những vector gần nhất bằng k-nearest neighbors (kNN).

Các metric thường gặp:

| Metric | Trực giác | Lưu ý |
|---|---|---|
| cosine similarity | So hướng giữa hai vector | Thường dùng với embedding đã huấn luyện cho cosine |
| dot product | Tích vô hướng | Magnitude có thể ảnh hưởng; model có thể yêu cầu normalize |
| L2 distance | Khoảng cách Euclidean | Giá trị nhỏ hơn biểu thị gần hơn |

Không tự so sánh score giữa hai metric hoặc hai model khác nhau. Score chỉ có ý nghĩa trong cách truy vấn và cấu hình tương ứng.

### 5.1. k và num_candidates

Trong kNN search:

- k là số neighbor mục tiêu được chọn.
- num_candidates là số candidate được xem xét ở mỗi shard trong approximate kNN, thường cần lớn hơn hoặc bằng k.
- Filter có thể giới hạn tập candidate theo điều kiện nghiệp vụ.

Ví dụ REST:

~~~http
POST knowledge-articles/_search
{
  "knn": {
    "field": "embedding",
    "query_vector": [0.12, -0.31, 0.08],
    "k": 10,
    "num_candidates": 100
  }
}
~~~

Vector ví dụ chỉ có ba chiều để minh họa cú pháp; trong index thực tế, số phần tử phải đúng dimensions của mapping.

Tăng num_candidates thường cải thiện recall của approximate search nhưng tăng chi phí tính toán. Chọn bằng benchmark trên dữ liệu và query thật.

### 5.2. Approximate và exact vector search

Approximate nearest neighbor (ANN) dùng cấu trúc chỉ mục vector để tìm nhanh candidate gần nhất, có thể không trả chính xác top-k tuyệt đối. Exact search có thể đánh giá tất cả vector trong tập lọc và thường tốn chi phí hơn khi dữ liệu lớn.

Lựa chọn phụ thuộc:

- Số lượng vector.
- Latency mục tiêu.
- Recall yêu cầu.
- Filter selectivity.
- Bộ nhớ và cấu hình shard.
- Phiên bản Elasticsearch và vector index options.

Không mặc định ANN luôn tốt hơn exact search. Với tập nhỏ hoặc filter rất chặt, exact search có thể phù hợp hơn.

## 6. Tạo embedding cho nội dung

Elasticsearch lưu và tìm vector, nhưng embedding thường được tạo bởi một model bên ngoài hoặc inference service. Pipeline index thường gồm:

~~~text
Source content
      |
      v
Normalize / clean text
      |
      v
Split into chunks (if needed)
      |
      v
Embedding model
      |
      v
Vector + source metadata
      |
      v
Elasticsearch index
~~~

Query pipeline:

~~~text
User query
     |
     v
Query normalization
     |
     v
Same compatible embedding model
     |
     v
Query vector
     |
     v
Elasticsearch kNN / hybrid search
     |
     v
Relevant documents or chunks
~~~

### 6.1. Embedding lúc index và lúc query

Embedding document thường được tính khi tạo hoặc cập nhật nội dung. Embedding query được tính mỗi lần người dùng tìm kiếm.

Hai pipeline phải dùng cùng contract:

- Model ID và model version.
- Output dimensions.
- Text normalization.
- Language handling.
- Prefix/instruction nếu model yêu cầu.
- Vector normalization nếu model yêu cầu.

Nếu document dùng model A nhưng query dùng model B không tương thích, khoảng cách vector không còn phản ánh ý nghĩa đúng.

### 6.2. Embedding model không nhất thiết chạy trong Elasticsearch

Có thể gọi model qua:

- Dịch vụ embedding nội bộ.
- Cloud inference API.
- Model server riêng.
- Elasticsearch inference integration nếu cluster và version hỗ trợ.

Spring Data Elasticsearch tập trung vào mapping và truy vấn dữ liệu. Việc tạo embedding có thể được đóng gói trong một EmbeddingService riêng để dễ thay model và kiểm thử.

Ví dụ contract:

~~~java
public interface EmbeddingService {

    float[] embedDocument(String text);

    float[] embedQuery(String text);
}
~~~

Một số model dùng prompt/instruction khác nhau cho query và document. Khi đó không nên gộp hai method thành một nếu điều đó làm mất khác biệt cần thiết.

## 7. Chunking tài liệu dài

Một document dài có thể chứa nhiều chủ đề. Nếu tạo một embedding cho toàn bộ văn bản, vector có thể làm mờ các ý nhỏ. Chunking chia nội dung thành các đoạn có kích thước phù hợp:

~~~text
Article
  |
  +-- Chunk 0: Giới thiệu và mục tiêu
  +-- Chunk 1: Cấu hình kết nối
  +-- Chunk 2: Authentication
  +-- Chunk 3: Troubleshooting
~~~

Mỗi chunk có thể là một vector riêng:

~~~json
{
  "chunkId": "article-42#2",
  "articleId": "article-42",
  "chunkNumber": 2,
  "title": "Cấu hình authentication",
  "content": "Ứng dụng cấu hình username và API key...",
  "embedding": [0.12, -0.31, 0.08]
}
~~~

### 7.1. Chunk size và overlap

Chunk quá lớn:

- Có thể chứa nhiều chủ đề không liên quan.
- Embedding khó đại diện cho từng ý nhỏ.
- Kết quả trả về nhiều nội dung không cần thiết.

Chunk quá nhỏ:

- Mất ngữ cảnh.
- Tăng số vector và dung lượng index.
- Một ý có thể bị tách giữa hai chunk.

Overlap giữ lại một phần token giữa các chunk liền kề để giảm mất ngữ cảnh ở ranh giới. Kích thước và overlap nên được đo theo tokenizer/model và cấu trúc tài liệu, không chọn một con số chung cho mọi loại dữ liệu.

### 7.2. Lưu metadata để quay về tài liệu gốc

Chunk document nên lưu articleId, chunkNumber, title, source URL, tenantId, permissions và các metadata cần thiết. Sau retrieval, ứng dụng có thể:

- Trả đoạn trích phù hợp.
- Gom các chunk theo tài liệu gốc.
- Loại kết quả trùng cùng article.
- Hiển thị nguồn và vị trí đoạn.
- Kiểm tra quyền truy cập ở cấp tài liệu.

Nếu chỉ lưu vector mà không có source identity, việc hiển thị nguồn và xóa/reindex tài liệu sẽ khó hơn.

## 8. Keyword query với Spring Data Elasticsearch

Spring Data Elasticsearch hỗ trợ repository query method, CriteriaQuery và NativeQuery. Với query đơn giản, repository method có thể đủ:

~~~java
public interface ArticleRepository
        extends ElasticsearchRepository<KnowledgeArticle, String> {

    List<KnowledgeArticle> findByTitle(String title);

    Page<KnowledgeArticle> findByStatus(
            String status,
            Pageable pageable);
}
~~~

Đối với full-text query cần điều khiển operator, field boost hoặc bool query, dùng NativeQuery:

~~~java
NativeQuery query = NativeQuery.builder()
        .withQuery(q -> q
                .multiMatch(m -> m
                        .query("reactive search repository")
                        .fields("title^3", "summary^2", "content")))
        .withPageable(PageRequest.of(0, 10))
        .build();

SearchHits<KnowledgeArticle> hits = operations.search(
        query,
        KnowledgeArticle.class,
        IndexCoordinates.of("knowledge-articles"));
~~~

SearchHits giữ score và metadata của từng hit. Nếu chỉ cần entity, có thể map SearchHit::getContent.

### 8.1. Exact identifier query

Với SKU hoặc external ID:

~~~java
NativeQuery query = NativeQuery.builder()
        .withQuery(q -> q
                .term(t -> t
                        .field("sku")
                        .value("KB-100")))
        .build();
~~~

Field sku nên được mapping keyword. Không đưa mã sản phẩm vào vector search duy nhất rồi kỳ vọng semantic model phân biệt chính xác mọi ký tự.

### 8.2. Filter theo tenant và trạng thái

~~~java
NativeQuery query = NativeQuery.builder()
        .withQuery(q -> q
                .bool(b -> b
                        .must(m -> m
                                .multiMatch(mm -> mm
                                        .query(userQuery)
                                        .fields("title^3", "content")))
                        .filter(f -> f
                                .term(t -> t
                                        .field("tenantId")
                                        .value(tenantId)))
                        .filter(f -> f
                                .term(t -> t
                                        .field("status")
                                        .value("PUBLISHED")))))
        .withPageable(PageRequest.of(0, 10))
        .build();
~~~

Tenant và access filters phải được áp dụng ở server. Không tin tenantId do client tự truyền nếu authorization context của request cung cấp giá trị đáng tin cậy.

## 9. Vector query với Spring Data Elasticsearch

Với Elasticsearch Java API Client, kNN query có thể được biểu diễn trong Query DSL. Một ví dụ NativeQuery:

~~~java
float[] embedding = embeddingService.embedQuery(userQuery);
List<Float> queryVector = toList(embedding);

NativeQuery query = NativeQuery.builder()
        .withQuery(q -> q
                .knn(k -> k
                        .field("embedding")
                        .queryVector(queryVector)
                        .k(10)
                        .numCandidates(100)))
        .build();

SearchHits<KnowledgeArticle> hits = operations.search(
        query,
        KnowledgeArticle.class,
        IndexCoordinates.of("knowledge-articles"));
~~~

Tên method builder và cách biểu diễn kNN có thể thay đổi theo phiên bản Elasticsearch Java API Client/Spring Data Elasticsearch. Hãy đối chiếu API của dependency đang dùng. Nếu phiên bản Spring Data chưa expose một phần Query DSL mới, có thể dùng Elasticsearch Java API Client trực tiếp ở một adapter riêng.

### 9.1. Vector dimensions phải khớp

Nếu mapping khai báo dims = 768, query vector phải có đúng 768 phần tử. Sai dimensions có thể làm request bị từ chối.

Nên kiểm tra dimensions ngay sau khi gọi embedding service:

~~~java
float[] vector = embeddingService.embedQuery(queryText);

if (vector.length != EXPECTED_DIMENSIONS) {
    throw new IllegalStateException("Unexpected embedding dimensions");
}
~~~

Không log toàn bộ vector. Nếu cần debug, log model version và vector length.

### 9.2. Filter trong kNN

Ví dụ query vector có filter tenant:

~~~http
POST knowledge-articles/_search
{
  "knn": {
    "field": "embedding",
    "query_vector": [0.12, -0.31, 0.08],
    "k": 10,
    "num_candidates": 100,
    "filter": {
      "bool": {
        "filter": [
          {"term": {"tenantId": "tenant-7"}},
          {"term": {"status": "PUBLISHED"}}
        ]
      }
    }
  }
}
~~~

Filter giới hạn kết quả trong phạm vi tenant/status được phép. Hãy dùng filter trong vector retrieval nếu version/API hỗ trợ đúng semantics; không chỉ lấy top-k toàn cục rồi lọc ở ứng dụng vì có thể bỏ sót kết quả hợp lệ và tạo rủi ro lộ dữ liệu.

## 10. Hybrid search: kết hợp lexical và semantic

Keyword và semantic có điểm mạnh khác nhau:

- Lexical tìm đúng mã, tên, cụm từ và thuật ngữ cụ thể.
- Semantic tìm nội dung gần về ý nghĩa.

Hybrid search chạy cả hai nguồn retrieval rồi kết hợp kết quả:

~~~text
                  User query
                      |
          +-----------+-----------+
          |                       |
          v                       v
   Lexical retrieval        Query embedding
   BM25 / inverted index           |
          |                        v
          |                 Vector retrieval
          |                   kNN / ANN
          |                        |
          +-----------+------------+
                      |
                      v
               Merge candidates
                      |
                      v
                 Reranking
                      |
                      v
              Final ranked results
~~~

Hybrid search hữu ích khi truy vấn có cả từ khóa chính xác lẫn ý định ngữ nghĩa, ví dụ “cách cấu hình TLS cho Elasticsearch Java client”.

Lexical search có thể tìm đúng Elasticsearch, TLS, Java client. Semantic search có thể tìm bài nói về certificate validation, CA fingerprint hoặc secure transport dù không dùng đúng cụm từ truy vấn.

### 10.1. Kết hợp bằng Reciprocal Rank Fusion

Reciprocal Rank Fusion (RRF) kết hợp thứ hạng từ nhiều retriever mà không cần đưa raw BM25 score và vector score về cùng thang đo.

Công thức trực giác:

\[
\operatorname{RRF}(d) =
\sum_{r \in R}
\frac{1}{k_0 + \operatorname{rank}_r(d)}
\]

Trong đó rank_r(d) là thứ hạng document d ở retriever r, còn k0 là hằng số làm giảm ảnh hưởng của vị trí rất cao. Document xuất hiện tốt trong nhiều danh sách có thể được đẩy lên.

RRF hữu ích vì BM25 score và vector similarity score thường không cùng scale. Không nên cộng trực tiếp hai score mà chưa hiệu chỉnh.

Elasticsearch phiên bản mới hỗ trợ retriever/rrf theo khả năng của cluster. Cú pháp và hỗ trợ Spring Data phụ thuộc version. Nếu abstraction Spring Data hiện tại chưa expose retriever API, có thể gọi search endpoint qua client adapter rồi ánh xạ kết quả về domain model.

### 10.2. Hybrid query bằng nhiều lượt search ở ứng dụng

Một cách triển khai độc lập version là gọi lexical và vector search riêng:

~~~java
List<SearchHit<KnowledgeArticle>> lexical =
        searchLexically(userQuery);

List<SearchHit<KnowledgeArticle>> semantic =
        searchSemantically(embeddingService.embedQuery(userQuery));

List<RankedArticle> merged = fusionService.rrf(
        lexical,
        semantic,
        60);
~~~

Fusion service cần nhận diện cùng một document bằng stable document ID hoặc source ID. Không ghép theo title vì title có thể trùng hoặc thay đổi.

Hai search riêng tạo hai request và có thể nhìn thấy snapshot dữ liệu khác nhau nếu index đang cập nhật. Nếu yêu cầu nhất quán, dùng cơ chế snapshot/PIT hoặc truy vấn hybrid tích hợp được Elasticsearch hỗ trợ.

### 10.3. Không cộng score thô một cách tùy tiện

Ví dụ sai lầm:

~~~java
combinedScore = bm25Score + cosineSimilarity;
~~~

BM25 có thể lớn hơn nhiều và thay đổi theo corpus/query; cosine similarity có scale khác. Cộng trực tiếp có thể làm một retriever áp đảo.

Các cách hợp lý hơn:

- RRF dựa trên rank.
- Normalize score trên tập candidate với phương pháp được đánh giá.
- Train/validate reranker trên relevance labels.
- Dùng hybrid retriever native của Elasticsearch nếu phù hợp.

## 11. Reranking sau retrieval

Retrieval thường ưu tiên recall: tìm được tập candidate đủ rộng. Reranking xếp hạng lại candidate bằng một mô hình hoặc tín hiệu giàu ngữ cảnh hơn.

Ví dụ pipeline:

1. Lexical retrieval lấy top 50.
2. Semantic retrieval lấy top 50.
3. Merge và deduplicate theo document ID.
4. Reranker chấm query-document pair.
5. Trả top 10.

Bi-encoder embedding tạo vector query và document riêng, phù hợp để tìm kiếm nhanh trên index lớn. Cross-encoder nhận query và document cùng lúc, thường có khả năng đánh giá tương tác chi tiết hơn nhưng tốn chi phí hơn trên nhiều candidate.

Không chạy cross-encoder trên toàn bộ corpus. Dùng retrieval để thu hẹp candidate rồi rerank top N.

## 12. Thiết kế index cho lexical và semantic cùng lúc

Một document có thể lưu cả text fields và embedding:

~~~json
{
  "id": "article-42",
  "title": "Cấu hình TLS cho Elasticsearch client",
  "content": "Ứng dụng có thể xác minh CA certificate...",
  "category": "security",
  "status": "PUBLISHED",
  "tenantId": "tenant-7",
  "embedding": [0.12, -0.31, 0.08]
}
~~~

Mapping có thể gồm:

~~~json
{
  "mappings": {
    "properties": {
      "title": {
        "type": "text",
        "fields": {
          "keyword": {"type": "keyword"}
        }
      },
      "content": {"type": "text"},
      "category": {"type": "keyword"},
      "status": {"type": "keyword"},
      "tenantId": {"type": "keyword"},
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

Field text phục vụ lexical retrieval; field keyword phục vụ exact match/filter/sort; dense_vector phục vụ vector retrieval. Một document có thể được truy xuất bằng cả ba kiểu tín hiệu.

### 12.1. Không embedding mọi field

Không nhất thiết đưa SKU, timestamp, tenant ID, trạng thái hoặc số hiệu vào embedding text. Những field có semantics cấu trúc nên được query/filter chính xác.

Text dùng để tạo embedding thường là nội dung đã ghép có chủ đích:

~~~text
Title: Cấu hình TLS cho Elasticsearch client
Category: Security
Content: Ứng dụng xác minh CA certificate...
~~~

Đừng nối mọi metadata một cách tùy tiện; metadata có thể làm embedding lệch khỏi nội dung chính.

### 12.2. Multi-field và analyzer

Một field có thể cần cả full-text và exact form:

~~~json
{
  "title": {
    "type": "text",
    "analyzer": "standard",
    "fields": {
      "keyword": {
        "type": "keyword",
        "ignore_above": 256
      }
    }
  }
}
~~~

Nếu cần sort hoặc exact title match, dùng title.keyword. Nếu cần tìm theo token, dùng title.

## 13. Mapping bằng Spring Data Elasticsearch

Entity có thể dùng annotation:

~~~java
@Document(indexName = "knowledge-articles")
public class KnowledgeArticle {

    @Id
    private String id;

    @Field(type = FieldType.Text)
    private String title;

    @Field(type = FieldType.Text)
    private String content;

    @Field(type = FieldType.Keyword)
    private String category;

    @Field(type = FieldType.Keyword)
    private String tenantId;

    @Field(type = FieldType.Dense_Vector, dims = 768,
            similarity = "cosine")
    private float[] embedding;
}
~~~

Với title cần multi-field keyword, có thể khai báo field mapping phù hợp bằng metadata annotation hoặc quản lý mapping JSON riêng tùy khả năng version. Hãy kiểm tra mapping thực tế bằng get mapping API.

Tạo index/mapping:

~~~java
IndexOperations indexOps = operations.indexOps(KnowledgeArticle.class);

if (!indexOps.exists()) {
    indexOps.createWithMapping();
}
~~~

Mapping dense_vector thường cần được xác định chính xác trước khi index dữ liệu. Thay dimensions hoặc similarity sau khi đã có dữ liệu có thể yêu cầu tạo index mới và reindex.

## 14. Tổ chức dịch vụ embedding

Không nên gọi embedding provider trực tiếp từ controller hoặc repository. Đặt một abstraction:

~~~java
public interface EmbeddingService {
    float[] embedQuery(String text);
    float[] embedDocument(String text);
}
~~~

Indexer:

~~~java
public void indexArticle(Article article) {
    String embeddingText = article.getTitle()
            + "\n"
            + article.getContent();

    float[] vector = embeddingService.embedDocument(embeddingText);

    KnowledgeArticle document = mapper.toDocument(article, vector);
    repository.save(document);
}
~~~

Search:

~~~java
public SearchHits<KnowledgeArticle> semanticSearch(String queryText) {
    float[] vector = embeddingService.embedQuery(queryText);
    return vectorSearchRepository.search(vector);
}
~~~

Lợi ích:

- Có thể đổi provider/model mà không sửa repository.
- Có thể mock embedding service trong unit test.
- Quản lý timeout, retry, rate limit và cache tập trung.
- Ghi nhận model version và dimensions.
- Có thể chạy embedding bất đồng bộ trong ingestion pipeline.

### 14.1. Timeout và retry cho embedding provider

Embedding API là dependency mạng. Cần:

- Timeout phù hợp.
- Retry có giới hạn cho lỗi transient.
- Backoff và jitter để tránh retry storm.
- Rate limit và concurrency control.
- Circuit breaker nếu provider lỗi kéo dài.
- Theo dõi latency, token usage và error rate.

Không retry vô hạn hoặc tạo embedding đồng bộ trong mọi request nếu latency người dùng không cho phép.

### 14.2. Cache embedding query

Query phổ biến có thể được cache nếu privacy policy và freshness cho phép. Cache key nên gồm normalized query, model ID/version, language và instruction context. Khi đổi model, cache cũ không nên được dùng nhầm.

Không cache embedding của query có dữ liệu nhạy cảm trong nơi không được phép lưu trữ.

## 15. Cập nhật và version hóa embedding

Embedding là dữ liệu dẫn xuất từ text và model. Khi nội dung thay đổi, embedding cũ không còn đại diện cho document mới.

Một quy trình cập nhật:

1. Nhận source content mới.
2. Chuẩn hóa/chunk lại nếu cần.
3. Tạo embedding bằng model version hiện tại.
4. Ghi text, metadata, vector và embeddingVersion cùng một document/indexing operation.
5. Đảm bảo query service dùng model tương thích.

Lưu metadata:

~~~json
{
  "embeddingModel": "embedding-model-v3",
  "embeddingVersion": 3,
  "embeddingDimensions": 768
}
~~~

### 15.1. Re-embedding khi đổi model

Không thể giả định vector của model v2 cùng không gian với model v3. Có thể tạo index mới:

~~~text
knowledge-v2
knowledge-v3
      |
      v
Build vectors using model v3
      |
      v
Validate retrieval quality
      |
      v
Switch alias / application config
~~~

Giữ index cũ để rollback trong thời gian chuyển đổi. Không trộn vector từ hai model khác nhau vào cùng field nếu chúng không tương thích.

### 15.2. Embedding drift

Ngay cả khi model không đổi, preprocessing, chunking hoặc source content có thể thay đổi. Theo dõi version của pipeline tạo vector, không chỉ tên model.

## 16. Semantic search và filter bảo mật

Semantic retrieval không thay thế authorization. Một document có vector gần query không có nghĩa người dùng được phép xem document đó.

Mọi truy vấn cần áp dụng filter phù hợp:

- Tenant ID lấy từ authenticated context.
- Trạng thái publish.
- ACL/visibility.
- Phạm vi project hoặc nhóm.
- Ngày hiệu lực nếu nghiệp vụ yêu cầu.

Ví dụ:

~~~json
{
  "knn": {
    "field": "embedding",
    "query_vector": [0.12, -0.31, 0.08],
    "k": 10,
    "num_candidates": 100,
    "filter": {
      "term": {
        "tenantId": "tenant-7"
      }
    }
  }
}
~~~

Nếu dùng nhiều retriever riêng, bảo đảm mọi nhánh lexical và semantic đều áp dụng cùng điều kiện truy cập. Không chỉ lọc sau khi merge nếu candidate đã chứa dữ liệu không được phép gửi ra khỏi tầng search.

## 17. Đánh giá chất lượng tìm kiếm

Không thể chọn keyword, semantic hay hybrid chỉ bằng cảm giác. Cần tập query đại diện và relevance judgments.

Tạo tập đánh giá:

| Query | Document liên quan | Mức relevance |
|---|---|---|
| KB-100 | Product KB-100 | Exact |
| bàn phím không dây | Wireless keyboard article | High |
| khôi phục file bị mất | Data recovery guide | High |
| cách xác minh certificate | TLS verification guide | High |
| Elasticsearch vector dimensions | Dense vector mapping guide | High |

Chạy từng retriever và ghi top-k kết quả. So sánh với relevance labels.

### 17.1. Recall@k

Recall@k đo tỷ lệ document liên quan được tìm thấy trong top k:

\[
\operatorname{Recall@k} =
\frac{\text{relevant documents in top k}}
{\text{all relevant documents}}
\]

Semantic retrieval có thể cải thiện recall khi cách diễn đạt khác nhau.

### 17.2. Precision@k

Precision@k đo tỷ lệ kết quả trong top k thực sự liên quan:

\[
\operatorname{Precision@k} =
\frac{\text{relevant documents in top k}}{k}
\]

Keyword exact search có thể đạt precision cao với mã sản phẩm, nhưng recall thấp khi query dùng từ đồng nghĩa.

### 17.3. MRR và nDCG

- Mean Reciprocal Rank (MRR) đo vị trí kết quả liên quan đầu tiên.
- Normalized Discounted Cumulative Gain (nDCG) đánh giá thứ hạng với mức relevance khác nhau và giảm trọng số của kết quả ở vị trí thấp.

Các metric này hữu ích khi hệ thống có nhiều mức relevance, không chỉ relevant/not relevant.

### 17.4. Đánh giá theo nhóm query

Phân nhóm:

- Exact identifier: SKU, ID, mã lỗi.
- Tên riêng: tên sản phẩm, framework, API.
- Natural-language question.
- Synonym/paraphrase.
- Query đa ngôn ngữ.
- Query dài nhiều ý.
- Query mơ hồ.

Một phương pháp có thể tốt với câu hỏi tự nhiên nhưng kém với SKU. Đánh giá theo nhóm giúp thấy trade-off thay vì chỉ nhìn một metric tổng.

## 18. Quan sát relevance và debug kết quả

Với lexical search:

- Dùng Explain API để hiểu score.
- Kiểm tra analyzer bằng Analyze API.
- Kiểm tra field mapping.
- Kiểm tra token query và token document.
- Điều chỉnh field boost, operator và synonym.

Với semantic search:

- Kiểm tra model version và dimensions.
- Kiểm tra text dùng để tạo embedding.
- Kiểm tra chunk boundaries.
- Kiểm tra similarity metric và vector normalization.
- Kiểm tra filter và candidate count.
- Xem các document gần nhất bằng query thử nghiệm.

Đừng chỉ tăng num_candidates hoặc thay model khi chưa xác định vấn đề nằm ở retrieval, mapping, filter hay data preparation.

## 19. Latency, chi phí và vận hành

Keyword search thường chỉ cần Elasticsearch query. Semantic search thêm bước embedding query và vector retrieval. Hybrid có thể gọi nhiều retriever và reranker.

| Thành phần | Chi phí/độ trễ cần theo dõi |
|---|---|
| Lexical retrieval | Query latency, shard fan-out, analyzer/query complexity |
| Query embedding | Provider latency, tokens, rate limit |
| Vector retrieval | Vector index size, memory, num_candidates, shard count |
| Hybrid fusion | Số request, merge/deduplication |
| Reranking | Model inference latency và candidate count |
| Document embedding | Ingestion throughput, model cost, re-embedding backlog |

Các biện pháp:

- Cache query embedding có version-aware key.
- Batch document embedding khi provider hỗ trợ.
- Dùng async ingestion cho cập nhật lớn.
- Giới hạn candidate count và rerank top N.
- Giữ text/vector index cùng version trong migration.
- Đo p50, p95, p99 latency.
- Theo dõi embedding failure và backlog.

## 20. Khi nào dùng keyword, semantic hay hybrid?

| Use case | Lựa chọn khởi đầu | Lý do |
|---|---|---|
| Tra cứu SKU/order ID/error code | Exact keyword/term | Cần khớp chính xác |
| Tìm bài theo tên API hoặc class | Lexical, có thể kết hợp semantic | Tên kỹ thuật cần match rõ |
| Tìm tài liệu bằng câu hỏi tự nhiên | Semantic hoặc hybrid | Người dùng có thể diễn đạt khác nội dung |
| Tìm sản phẩm theo nhu cầu mô tả | Hybrid | Giữ filter/brand/price chính xác và hiểu ý định |
| Tìm tài liệu có thuật ngữ bắt buộc | Lexical + semantic | Không bỏ mất từ khóa quan trọng |
| Hỏi đáp trên kho tài liệu dài | Semantic/hybrid trên chunks | Cần tìm đoạn liên quan theo ý nghĩa |
| Tìm theo trạng thái, tenant, ngày | Filter/keyword | Đây là điều kiện cấu trúc |
| Tìm theo tên riêng và paraphrase | Hybrid | Kết hợp exact term và ngữ nghĩa |

Nếu dữ liệu nhỏ hoặc query đơn giản, keyword search có thể đã đủ. Không thêm embedding chỉ vì công nghệ mới; semantic pipeline cần chi phí vận hành, đánh giá và cập nhật vector.

## 21. Ví dụ service hybrid trong Spring

Có thể tạo service điều phối:

~~~java
@Service
public class ArticleSearchService {

    private final LexicalArticleSearch lexicalSearch;
    private final SemanticArticleSearch semanticSearch;
    private final EmbeddingService embeddingService;
    private final SearchFusionService fusionService;

    public ArticleSearchService(
            LexicalArticleSearch lexicalSearch,
            SemanticArticleSearch semanticSearch,
            EmbeddingService embeddingService,
            SearchFusionService fusionService) {
        this.lexicalSearch = lexicalSearch;
        this.semanticSearch = semanticSearch;
        this.embeddingService = embeddingService;
        this.fusionService = fusionService;
    }

    public List<ArticleResult> search(String query, String tenantId) {
        List<SearchHit<KnowledgeArticle>> lexical =
                lexicalSearch.search(query, tenantId, 50);

        float[] queryVector = embeddingService.embedQuery(query);

        List<SearchHit<KnowledgeArticle>> semantic =
                semanticSearch.search(queryVector, tenantId, 50);

        return fusionService.rrf(lexical, semantic, 10);
    }
}
~~~

Đây là cấu trúc minh họa; adapter search chịu trách nhiệm tạo NativeQuery và chuyển SearchHits. Với production, có thể chạy hai nhánh song song nếu cả hai độc lập và timeout/cancellation được quản lý. Nếu cần hybrid retriever server-side, dùng API của Elasticsearch version tương ứng.

### 21.1. Dedupe bằng document identity

Fusion service cần map theo document ID hoặc source identity:

~~~java
Map<String, RankedCandidate> candidates = new LinkedHashMap<>();
~~~

Không dedupe bằng title hoặc nội dung hiển thị vì hai document khác nhau có thể cùng title. Nếu index dùng chunk, có thể dedupe ở articleId sau khi chọn các chunk phù hợp.

### 21.2. Giữ score và rank riêng

Khi merge, giữ:

- lexical rank và lexical score.
- semantic rank và semantic score.
- fused rank/score.
- reranker score nếu có.

Điều này giúp quan sát tại sao kết quả được xếp hạng và điều chỉnh fusion. Không gọi fused score là xác suất liên quan nếu chưa hiệu chỉnh/calibrate.

## 22. Những giới hạn của semantic search

Semantic search có thể tìm nội dung gần ý nghĩa nhưng không đảm bảo chính xác từng chi tiết:

- Hai sản phẩm có tên gần nhau nhưng khác model.
- Hai phiên bản API khác nhau.
- Mã lỗi chỉ khác một chữ số.
- Điều kiện phủ định như “không bật TLS”.
- Giá trị số, ngày tháng và ngưỡng.
- Nội dung mới chưa được embedding.
- Query có nhiều ý nhưng một vector duy nhất làm mất trọng tâm.

Với các điều kiện quan trọng, kết hợp filter/exact lexical. Nếu cần hiểu logic phức tạp, có thể dùng query parsing hoặc reranker nhưng vẫn phải kiểm tra dữ liệu.

### 22.1. Semantic similarity không phải sự thật

Một document gần vector không có nghĩa nó trả lời đúng. Model có thể xem hai khái niệm liên quan là gần nhau dù chúng khác về phiên bản, điều kiện hoặc kết quả. Hệ thống nên hiển thị nguồn và cho phép kiểm tra nội dung gốc.

### 22.2. Query ngắn hoặc mơ hồ

Query một từ như “Java” có thể chỉ ngôn ngữ, runtime, coffee hoặc một sản phẩm tên Java. Lexical search có thể trả quá nhiều kết quả; semantic search cũng không thể tự biết ý định nếu thiếu ngữ cảnh.

Có thể:

- Hỏi người dùng làm rõ.
- Dùng filter theo category/context.
- Ưu tiên lịch sử hoặc phạm vi hiện tại nếu có cơ sở.
- Hiển thị các nhóm kết quả khác nhau.

## 23. Các lỗi thường gặp

### Dùng term query trên text field

term không phân tích query như match. Dùng match cho full-text hoặc keyword field cho exact term.

### Dùng match query cho SKU

Analyzer có thể tách hoặc biến đổi mã. Dùng keyword mapping và term query cho exact identifier.

### Cho rằng keyword search chỉ tìm chuỗi giống hệt

Full-text lexical search có thể tokenize, lowercase, stem và dùng synonym. Exact match là trường hợp riêng.

### Cho rằng semantic search tự hiểu mọi từ đồng nghĩa

Embedding phụ thuộc model, ngôn ngữ và domain. Đánh giá trên query thực tế.

### Dùng embedding model khác nhau ở index và query

Vector không còn cùng không gian. Gắn model/version metadata và re-embed khi đổi model.

### Sai dimensions

Vector query phải có đúng số chiều mapping. Validate dimensions ở adapter.

### Chọn similarity không phù hợp

Cosine, dot product và L2 có semantics khác. Theo hướng dẫn model và benchmark.

### Chunk quá lớn hoặc quá nhỏ

Chunk lớn làm mờ ý; chunk nhỏ mất ngữ cảnh và tăng số vector. Đánh giá chunk size/overlap.

### Không lưu source ID trong chunk

Không thể gom kết quả, hiển thị nguồn hoặc xóa/reindex đầy đủ. Lưu articleId và chunk metadata.

### Bỏ qua filter khi vector search

Có thể trả dữ liệu tenant/ACL không được phép. Áp dụng filter bảo mật ở mọi nhánh retrieval.

### Cộng BM25 và cosine score trực tiếp

Hai score khác thang đo. Dùng RRF, normalization có đánh giá hoặc reranker.

### Chỉ dùng semantic cho mã kỹ thuật

Embedding không bảo đảm phân biệt ký tự. Giữ lexical exact matching.

### Không re-embed khi content đổi

Vector cũ đại diện nội dung cũ. Tái tạo embedding theo update pipeline.

### Đổi model nhưng không rebuild vector

Query/document vector không tương thích. Version hóa và migrate index.

### Chỉ đo latency, không đo relevance

Search nhanh nhưng sai vẫn không đạt mục tiêu. Dùng query set và relevance labels.

### Chỉ đánh giá bằng một nhóm query

Kết quả có thể tốt cho câu hỏi tự nhiên nhưng kém cho SKU hoặc tên riêng. Chia nhóm query.

## 24. Quy trình xây dựng tìm kiếm

Khi triển khai search trong Spring Data Elasticsearch:

1. Phân loại query: exact identifier, full-text, natural-language, structured filter hay hỗn hợp.
2. Thiết kế mapping text/keyword cho lexical search.
3. Chọn analyzer phù hợp ngôn ngữ và domain.
4. Dùng BM25/full-text query với field boost và filter rõ ràng.
5. Chọn embedding model tương thích với ngôn ngữ và dữ liệu.
6. Xác định text cần embed và chiến lược chunking.
7. Tạo dense_vector mapping đúng dimensions/similarity.
8. Tách EmbeddingService khỏi repository và version hóa model contract.
9. Tạo query embedding bằng model tương thích với document embedding.
10. Dùng kNN với k, num_candidates và filter phù hợp.
11. Kết hợp lexical và vector retrieval nếu hai tín hiệu bổ sung nhau.
12. Dùng RRF hoặc reranker thay vì cộng score thô.
13. Áp dụng tenant/ACL filters ở mọi nhánh search.
14. Re-embed và reindex có kế hoạch khi model hoặc chunking thay đổi.
15. Đánh giá Recall@k, Precision@k, MRR/nDCG theo nhóm query.
16. Theo dõi latency, provider errors, vector index size và embedding backlog.
17. Kiểm thử exact identifier, paraphrase, synonym, filter, duplicate chunk và model migration.

## 25. Tổng kết

Keyword search (lexical retrieval) dựa trên inverted index, analyzer, token và relevance scoring như BM25. Nó phù hợp cho từ khóa, tên riêng, mã sản phẩm, API, error code và điều kiện chính xác. Trong Elasticsearch, full-text thường dùng field text với match/multi_match; exact matching và filter thường dùng field keyword với term query.

Semantic search chuyển query và document thành embedding vector rồi tìm các vector gần nhau bằng cosine, dot product hoặc L2. Nó có thể tìm tài liệu dùng cách diễn đạt khác nhưng cùng ý nghĩa. Chất lượng phụ thuộc model, ngôn ngữ, chunking, preprocessing, dimensions và cách chọn candidate.

Hybrid search kết hợp lexical và semantic retrieval để giữ độ chính xác của từ khóa và mở rộng recall theo ý nghĩa. Có thể dùng RRF hoặc reranking; tránh cộng raw BM25 và vector score tùy tiện. Spring Data Elasticsearch hỗ trợ mapping/query qua repository, CriteriaQuery và NativeQuery; khi API vector/retriever mới chưa được abstraction expose, đặt Elasticsearch Java API Client trong adapter riêng.

Tìm kiếm ngữ nghĩa không thay thế filter bảo mật hoặc exact matching. Giữ tenant/ACL/status filter trong mọi nhánh, dùng lexical cho identifier và số liệu, version hóa embedding model, re-embed khi nội dung/model thay đổi, và đánh giá bằng query set có relevance labels. Chỉ thêm semantic search khi nó cải thiện chất lượng truy xuất đủ để bù chi phí embedding, vector index và vận hành.

## Tài liệu tham khảo

- [Spring Data Elasticsearch – Query Methods and Repositories](https://docs.spring.io/spring-data/elasticsearch/reference/elasticsearch/repositories.html)
- [Spring Data Elasticsearch – NativeQuery API](https://docs.spring.io/spring-data/elasticsearch/reference/api/java/org/springframework/data/elasticsearch/client/elc/NativeQuery.html)
- [Spring Data Elasticsearch – Field Mapping API](https://docs.spring.io/spring-data/elasticsearch/reference/api/java/org/springframework/data/elasticsearch/annotations/Field.html)
- [Elasticsearch – Full-text search](https://www.elastic.co/guide/en/elasticsearch/reference/current/full-text-search.html)
- [Elasticsearch – Text field type](https://www.elastic.co/guide/en/elasticsearch/reference/current/text.html)
- [Elasticsearch – Keyword field type](https://www.elastic.co/guide/en/elasticsearch/reference/current/keyword.html)
- [Elasticsearch – Dense vector field type](https://www.elastic.co/guide/en/elasticsearch/reference/current/dense-vector.html)
- [Elasticsearch – kNN search](https://www.elastic.co/guide/en/elasticsearch/reference/current/knn-search.html)
- [Elasticsearch – Hybrid search and RRF](https://www.elastic.co/guide/en/elasticsearch/reference/current/rrf.html)
- [Elasticsearch – Semantic search](https://www.elastic.co/guide/en/elasticsearch/reference/current/semantic-search.html)
