# Chuẩn bị vector và giữ đồng bộ với nội dung tài liệu

Tìm kiếm ngữ nghĩa trong Spring Data Elasticsearch bắt đầu từ việc biến nội dung thành vector embedding. Mỗi vector là một biểu diễn số của văn bản do một mô hình embedding tạo ra. Elasticsearch có thể so sánh các vector để tìm những đoạn nội dung gần nhau về ngữ nghĩa, kể cả khi chúng không dùng cùng từ khóa.

Chất lượng của tìm kiếm phụ thuộc vào cả quá trình chuẩn bị dữ liệu. Nếu ứng dụng embed sai văn bản, chia chunk không nhất quán, dùng model hoặc số chiều khác nhau, hay để vector cũ tồn tại sau khi tài liệu thay đổi, kết quả nearest-neighbor sẽ không còn phản ánh nội dung hiện tại.

Vì vậy, vector cần được quản lý như một projection có thể tái tạo từ nội dung nguồn. Ứng dụng phải biết vector được tạo từ phiên bản nội dung nào, model nào, cấu hình chunking nào và khi nào cần tạo lại. Bài này trình bày cách chuẩn bị embedding input, chia tài liệu thành chunk, lưu dense_vector, giữ đồng bộ khi tạo/sửa/xóa tài liệu, xử lý retry và thay model, cùng cách kiểm thử pipeline.

## 1. Vector embedding trong tìm kiếm ngữ nghĩa

Embedding model nhận văn bản và trả về một dãy số thực. Ví dụ minh họa:

~~~text
"Spring Data Elasticsearch hỗ trợ tìm kiếm vector"
                  |
                  v
             Embedding model
                  |
                  v
[0.12, -0.08, 0.31, 0.44, ...]
~~~

Mỗi vector có số chiều cố định do model quy định. Một model có thể trả 384, 768, 1024 hoặc một kích thước khác. Số chiều thực tế phải được lấy từ contract của model, không được tự đoán hoặc cắt vector để vừa mapping.

Trong tìm kiếm ngữ nghĩa:

1. Ứng dụng chuẩn hóa và chia nội dung thành các đơn vị phù hợp.
2. Embedding model tạo vector cho từng đơn vị.
3. Ứng dụng lưu text, metadata và vector trong Elasticsearch.
4. Khi người dùng tìm kiếm, cùng embedding model tạo vector cho query.
5. Elasticsearch so sánh query vector với vector đã lưu và trả các chunk gần nhất.

Một vector không tự chứa nội dung văn bản có thể đọc được. Hãy lưu text và metadata cùng vector để có thể hiển thị kết quả, truy nguồn tài liệu và tái tạo embedding khi cần.

## 2. Xác định nguồn dữ liệu chuẩn

Elasticsearch nên được xem là search index hoặc projection phục vụ truy vấn. Nguồn dữ liệu chuẩn (source of truth) thường là database, CMS, object store hoặc kho tài liệu của ứng dụng.

Ví dụ một tài liệu có thể có:

~~~json
{
  "documentId": "guide-1001",
  "title": "Spring Data Elasticsearch",
  "body": "Nội dung tài liệu...",
  "version": 17,
  "updatedAt": "2026-11-13T10:30:00Z"
}
~~~

Từ record này, pipeline tạo một hoặc nhiều chunk và vector. Không nên chỉ lưu nội dung ở Elasticsearch rồi không còn cách xác định phiên bản gốc, model hoặc quy tắc đã tạo vector.

Giữ source of truth giúp:

- Tái tạo vector nếu index bị mất.
- Re-embed khi model thay đổi.
- Chạy lại chunking khi chiến lược chia đoạn thay đổi.
- Xử lý document update/delete có kiểm soát.
- So sánh nội dung đã index với nội dung hiện tại.
- Phục hồi sau lỗi hoặc event bị xử lý trễ.

Mỗi document nên có một định danh ổn định và một version tăng đơn điệu hoặc revision token đáng tin cậy. Version giúp nhận biết event cũ và tránh một job chậm ghi đè kết quả mới hơn.

## 3. Chuẩn bị văn bản trước khi gọi embedding model

Embedding nên được tạo từ đúng nội dung mà người dùng mong muốn tìm thấy. Trước khi gọi model, xác định rõ các bước biến đổi văn bản.

Một pipeline thường gồm:

~~~text
Raw source
    |
    v
Extract text
    |
    v
Normalize content
    |
    v
Remove/transform unwanted markup
    |
    v
Split into chunks
    |
    v
Build embedding input
    |
    v
Embedding model
    |
    v
Vector + chunk metadata
~~~

### 3.1. Trích xuất nội dung

Tài liệu có thể đến từ HTML, Markdown, PDF, DOCX, email hoặc record database. Trích xuất cần giữ cấu trúc quan trọng:

- Tiêu đề và heading.
- Đoạn văn.
- Danh sách.
- Bảng và nhãn cột.
- Mã nguồn hoặc cấu hình.
- Caption và chú thích có ý nghĩa.
- Đường dẫn hoặc định danh nguồn.

Không nối toàn bộ nội dung đã trích xuất thành một chuỗi không phân biệt cấu trúc. Heading và ngữ cảnh giúp chunk có nghĩa khi được truy xuất riêng lẻ.

### 3.2. Chuẩn hóa nhưng không phá nội dung

Các phép chuẩn hóa có thể gồm:

- Chuẩn hóa newline và khoảng trắng.
- Loại bỏ markup không có ý nghĩa tìm kiếm.
- Giữ dấu tiếng Việt và Unicode đúng.
- Chuẩn hóa encoding.
- Loại bỏ boilerplate lặp lại nếu có quy tắc rõ.
- Giữ code, tên API và identifier chính xác khi chúng quan trọng.

Không xóa dấu tiếng Việt chỉ để đơn giản hóa embedding. Không chuyển mọi văn bản thành lowercase nếu điều đó làm mất semantics của mã, tên class hoặc token phân biệt hoa thường. Model embedding thường có preprocessing riêng; ứng dụng cần theo đúng hướng dẫn model và dùng cùng quy trình cho document lẫn query.

### 3.3. Phân biệt nội dung với metadata

Metadata như documentId, tenantId, sourceVersion, access level và timestamp thường nên được lưu thành field riêng để filter, sort hoặc truy nguồn.

Chỉ đưa metadata vào embedding text khi nó thực sự có ý nghĩa ngữ nghĩa. Ví dụ tiêu đề tài liệu thường hữu ích để ghép vào chunk text; internal database ID thường không giúp semantic similarity.

Một embedding input có thể được tạo như sau:

~~~text
Document title: Spring Data Elasticsearch
Section: Vector search
Content: Elasticsearch stores dense vectors and supports kNN search...
~~~

Giữ một hàm buildEmbeddingText nhất quán và version hóa quy tắc này. Nếu đổi cách ghép title/heading/body, vector cần được tạo lại vì model đang nhận một input khác.

## 4. Chia tài liệu thành chunk

Một tài liệu dài thường vượt giới hạn input của embedding model và cũng không phải đơn vị truy xuất tốt nhất. Chia tài liệu thành chunk giúp embedding tập trung vào một chủ đề và cho phép trả về đoạn liên quan thay vì toàn bộ tài liệu.

Ví dụ:

~~~text
Document: guide-1001
  Chunk 0: Giới thiệu và khái niệm
  Chunk 1: Cấu hình mapping
  Chunk 2: Tạo vector
  Chunk 3: Truy vấn kNN
  Chunk 4: Cập nhật và đồng bộ
~~~

### 4.1. Chunk theo cấu trúc trước khi cắt theo kích thước

Nếu tài liệu có heading và đoạn văn, ưu tiên ranh giới ngữ nghĩa:

1. Tách theo section hoặc heading.
2. Giữ heading làm ngữ cảnh cho các chunk con.
3. Chia section quá dài thành đoạn nhỏ.
4. Tránh tách giữa câu, bảng hoặc code block nếu có thể.
5. Giữ thứ tự chunk và vị trí trong tài liệu.

Chia đều mỗi 500 ký tự có thể cắt mất câu hoặc tách phần giải thích khỏi ví dụ. Chunk theo token thường phù hợp hơn khi model giới hạn input theo token.

### 4.2. Kích thước chunk

Không có một kích thước chunk tối ưu cho mọi loại tài liệu. Kích thước phụ thuộc:

- Token limit của embedding model.
- Độ dài và cấu trúc nội dung.
- Query người dùng thường đặt.
- Độ chính xác cần có ở mức đoạn.
- Chi phí embedding và số lượng vector.
- Chi phí lưu trữ và nearest-neighbor search.

Chunk quá lớn có thể chứa nhiều chủ đề, làm vector ít tập trung. Chunk quá nhỏ có thể mất ngữ cảnh và tạo rất nhiều vector. Hãy benchmark trên bộ query đại diện và đánh giá retrieval quality.

### 4.3. Overlap

Có thể cho hai chunk liền kề chồng lấn một phần nội dung để giữ ngữ cảnh qua ranh giới.

Ví dụ:

~~~text
Chunk 0: tokens 0 - 400
Chunk 1: tokens 340 - 740
Chunk 2: tokens 680 - 1080
~~~

Overlap giúp giảm nguy cơ một câu quan trọng bị chia đôi, nhưng làm tăng số token được embed, số vector và duplicate context trong kết quả. Chọn overlap vừa đủ, không áp dụng máy móc.

### 4.4. Giữ ngữ cảnh section

Chunk được truy xuất độc lập nên có thể cần title hoặc heading của tài liệu. Ví dụ chunk text:

~~~text
Title: Spring Data Elasticsearch
Section: Keeping vectors synchronized
Content: When a source document changes, regenerate affected chunks...
~~~

Heading giúp embedding hiểu chunk đang nói về chủ đề nào. Nhưng không lặp toàn bộ metadata vào mọi chunk nếu nó làm tăng token cost mà không cải thiện retrieval.

## 5. Thiết kế identity và metadata của chunk

Mỗi chunk cần một ID ổn định để có thể cập nhật hoặc xóa đúng phần dữ liệu.

Một document có thể được biểu diễn bằng các Elasticsearch document riêng cho từng chunk:

~~~json
{
  "chunkId": "guide-1001-v17-c03",
  "documentId": "guide-1001",
  "sourceVersion": 17,
  "chunkNumber": 3,
  "title": "Spring Data Elasticsearch",
  "section": "Keeping vectors synchronized",
  "content": "When a source document changes...",
  "embeddingModel": "embedding-model-v2",
  "embeddingVersion": 2,
  "contentHash": "sha256:...",
  "updatedAt": "2026-11-13T10:30:00Z"
}
~~~

Metadata hữu ích:

- documentId: định danh tài liệu nguồn.
- chunkId: định danh chunk.
- sourceVersion: revision của nội dung nguồn.
- chunkNumber hoặc ordinal: thứ tự trong tài liệu.
- section/title: ngữ cảnh.
- contentHash: hash của embedding input.
- embeddingModel: model tạo vector.
- embeddingVersion: version của preprocessing/chunking contract.
- tenantId/access metadata: phạm vi truy cập.
- source URI: đường dẫn tới tài liệu gốc.
- updatedAt: thời điểm projection được cập nhật.

### 5.1. Chọn chunk ID xác định

Có thể tạo ID từ document ID, version, chunking version và ordinal:

~~~text
documentId + ":" + sourceVersion + ":" + chunkingVersion + ":" + chunkNumber
~~~

Hoặc hash canonical key nếu ID dài. ID ổn định giúp retry cùng một lần xử lý ghi đè đúng chunk thay vì tạo document mới.

Nếu ID chỉ là random UUID được tạo lại mỗi lần retry, cùng một chunk có thể xuất hiện nhiều lần. Nếu ID dựa trên ordinal nhưng nội dung thay đổi và chunk bị dịch chuyển, cần cập nhật hoặc xóa các ordinal cũ không còn dùng.

### 5.2. Content hash

Tính hash từ chính embedding input sau normalization, cộng với model/preprocessing version trong cache key:

~~~text
hashKey = SHA-256(
    modelVersion + "|" +
    preprocessingVersion + "|" +
    normalizedEmbeddingText
)
~~~

Hash giúp:

- Bỏ qua embedding khi input không đổi.
- Phát hiện nội dung chunk đã thay đổi.
- Tái sử dụng embedding cache nếu chính sách cho phép.
- Chẩn đoán vector được tạo từ nội dung nào.

Hash không thay thế sourceVersion. Hai revision có thể khác metadata nhưng cùng text; ngược lại cùng sourceVersion không nên được dùng nếu nội dung đã thay đổi ngoài contract.

## 6. Mapping dense_vector trong Elasticsearch

Elasticsearch dùng field type dense_vector để lưu vector số thực. Mapping cần khai báo số chiều phù hợp với output của embedding model.

Ví dụ:

~~~http
PUT knowledge-chunks-v1
{
  "mappings": {
    "properties": {
      "chunkId": {
        "type": "keyword"
      },
      "documentId": {
        "type": "keyword"
      },
      "sourceVersion": {
        "type": "long"
      },
      "chunkNumber": {
        "type": "integer"
      },
      "title": {
        "type": "text"
      },
      "section": {
        "type": "keyword"
      },
      "content": {
        "type": "text"
      },
      "contentHash": {
        "type": "keyword"
      },
      "embeddingModel": {
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

Trong ví dụ, 768 chỉ là giá trị minh họa. Hãy thay bằng đúng số chiều của model đã chọn. Không thể ghi vector có số phần tử khác dims đã khai báo.

Các thuộc tính quan trọng:

- dims: số chiều của vector.
- index: có tạo cấu trúc hỗ trợ approximate kNN hay không, tùy phiên bản và cấu hình.
- similarity: hàm similarity được dùng cho vector search, ví dụ cosine, dot_product hoặc l2_norm.
- element_type/index_options: các tùy chọn khác phụ thuộc Elasticsearch version và loại vector.

Với vector được index để tìm kiếm kNN, Elasticsearch có thể xây dựng cấu trúc approximate nearest-neighbor như HNSW. Việc bật index làm tăng chi phí lưu trữ và indexing nhưng hỗ trợ tìm kiếm hiệu quả hơn ở quy mô phù hợp.

### 6.1. Chọn similarity nhất quán

Các lựa chọn thường gặp:

- cosine: so sánh hướng của hai vector.
- dot_product: tích vô hướng; yêu cầu chuẩn hóa vector theo contract của field/model trong các cấu hình float thông dụng.
- l2_norm: khoảng cách Euclidean.
- max_inner_product: phù hợp với một số model/training objective.

Không chọn similarity chỉ vì tên nghe quen thuộc. Dùng metric được khuyến nghị bởi model provider và đảm bảo query vector được tạo bằng cùng model, preprocessing và quy tắc normalization.

Không trộn vector từ hai model khác nhau chỉ vì chúng có cùng số chiều. Không gian embedding của chúng có thể hoàn toàn khác nhau.

### 6.2. Vector không index

Một số workflow chỉ cần lưu vector để tính toán hoặc script, không cần approximate kNN index. Trong trường hợp đó, mapping có thể không bật vector index nếu version hỗ trợ. Cách truy cập và chi phí khác với indexed vector; hãy xác định rõ use case trước khi chọn.

## 7. Entity Spring Data Elasticsearch cho chunk

Có thể ánh xạ một chunk thành entity:

~~~java
import java.time.Instant;

import org.springframework.data.annotation.Id;
import org.springframework.data.elasticsearch.annotations.Document;
import org.springframework.data.elasticsearch.annotations.Field;
import org.springframework.data.elasticsearch.annotations.FieldType;

@Document(indexName = "knowledge-chunks-v1")
public class KnowledgeChunk {

    @Id
    private String chunkId;

    @Field(type = FieldType.Keyword)
    private String documentId;

    @Field(type = FieldType.Long)
    private Long sourceVersion;

    @Field(type = FieldType.Integer)
    private Integer chunkNumber;

    @Field(type = FieldType.Text)
    private String title;

    @Field(type = FieldType.Keyword)
    private String section;

    @Field(type = FieldType.Text)
    private String content;

    @Field(type = FieldType.Keyword)
    private String contentHash;

    @Field(type = FieldType.Keyword)
    private String embeddingModel;

    private float[] embedding;

    @Field(type = FieldType.Date)
    private Instant updatedAt;

    // constructors, getters and setters
}
~~~

Mapping vector bằng annotation có thể khác nhau theo Spring Data Elasticsearch version. Một số phiên bản hỗ trợ FieldType.Dense_Vector và các thuộc tính vector tương ứng; các phiên bản khác có thể cần mapping tường minh qua IndexOperations hoặc mapping JSON.

Đừng giả định một float[] tự động được map thành dense_vector trong mọi version. Kiểm tra Javadoc và mapping thực tế trên cluster. Nếu annotation không biểu diễn đủ dims/similarity/index options, tạo mapping tường minh trước khi index dữ liệu.

### 7.1. Tạo index và mapping rõ ràng

Spring Data Elasticsearch cung cấp IndexOperations để quản lý index:

~~~java
IndexOperations indexOperations =
    operations.indexOps(KnowledgeChunk.class);

if (!indexOperations.exists()) {
    indexOperations.create();
    indexOperations.putMapping(
        indexOperations.createMapping()
    );
}
~~~

Đoạn này minh họa lifecycle tổng quát. Nếu mapping vector được quản lý bằng JSON riêng, hãy tạo index với settings và mapping đó qua API tương ứng, rồi xác nhận mapping bằng GET index/_mapping.

Không để ứng dụng production tự tạo index với mapping mặc định không đúng dims rồi mới thử ghi vector. Mapping phải được provision trước khi ingest.

## 8. Gọi embedding model theo batch

Embedding model thường có chi phí network/compute. Gửi từng chunk một có thể làm tăng latency và overhead. Nếu provider hỗ trợ batch embeddings, gom nhiều input vào một request trong giới hạn token và số phần tử.

Interface ứng dụng có thể được định nghĩa như sau:

~~~java
public interface EmbeddingService {

    int dimensions();

    String modelVersion();

    Mono<List<float[]>> embed(List<String> inputs);
}
~~~

Đây là interface minh họa. Với ứng dụng imperative, có thể dùng List<float[]> trực tiếp; với reactive service, trả Mono/Flux theo contract.

Một service tạo chunk:

~~~java
public Mono<List<EmbeddedChunk>> embedChunks(
        List<TextChunk> chunks) {

    List<String> inputs = chunks.stream()
        .map(TextChunk::embeddingText)
        .toList();

    return embeddingService.embed(inputs)
        .map(vectors -> {
            if (vectors.size() != chunks.size()) {
                throw new IllegalStateException(
                    "Embedding count does not match chunk count"
                );
            }

            List<EmbeddedChunk> result = new ArrayList<>();

            for (int i = 0; i < chunks.size(); i++) {
                float[] vector = vectors.get(i);

                if (vector.length != embeddingService.dimensions()) {
                    throw new IllegalStateException(
                        "Unexpected embedding dimensions"
                    );
                }

                result.add(
                    new EmbeddedChunk(chunks.get(i), vector)
                );
            }

            return result;
        });
}
~~~

Cần kiểm tra response count, dimension, giá trị hữu hạn và thứ tự vector so với input. Nếu provider trả vector theo thứ tự input, giữ mapping index tương ứng. Nếu response có input index, dùng index đó thay vì dựa vào thứ tự ngầm định.

### 8.1. Kiểm tra vector trước khi lưu

Trước khi index:

- Số phần tử đúng dims.
- Không có NaN hoặc Infinity.
- Vector không rỗng.
- Norm phù hợp với metric/model.
- Model version đúng.
- Embedding input hash khớp metadata.
- Chunk text và vector thuộc cùng một sourceVersion.

Một vector lỗi có thể làm bulk item thất bại hoặc làm chất lượng search suy giảm mà không có lỗi rõ ràng.

## 9. Pipeline ingest từ nội dung tới vector

Một pipeline có thể chia thành các bước độc lập:

~~~text
Document source
      |
      v
Read current revision
      |
      v
Extract + normalize text
      |
      v
Split into chunks
      |
      v
Compute chunk IDs + content hashes
      |
      v
Reuse unchanged embeddings
      |
      v
Generate missing embeddings
      |
      v
Validate vectors
      |
      v
Bulk index chunk documents
      |
      v
Remove stale chunks
      |
      v
Record indexed source version
~~~

Mỗi bước nên có input/output rõ ràng và có thể retry an toàn.

Không đánh dấu document đã được index thành công trước khi tất cả chunk cần thiết đã được ghi. Nếu embedding provider lỗi giữa chừng, giữ trạng thái job để tiếp tục mà không tạo duplicate.

### 9.1. Tách extraction, chunking và embedding

Không gộp tất cả logic vào một callback persistence nếu quy trình có I/O, model call hoặc retry phức tạp.

Có thể tổ chức:

- DocumentExtractor: đọc nội dung nguồn.
- TextNormalizer: chuẩn hóa.
- Chunker: tạo chunk và metadata.
- EmbeddingService: gọi model.
- VectorDocumentMapper: tạo entity/document.
- VectorIndexer: bulk ghi vào Elasticsearch.
- SyncCoordinator: quản lý version, retry và trạng thái.

Tách thành phần giúp test từng phần và thay model/chunker mà không thay logic source repository.

## 10. Khi nội dung tài liệu thay đổi

Một thay đổi ở source document có thể làm:

- Nội dung của một hoặc nhiều chunk thay đổi.
- Số lượng chunk tăng hoặc giảm.
- Thứ tự chunk thay đổi.
- Title/heading thay đổi.
- Embedding input thay đổi dù body gần như giống nhau.
- Quyền truy cập hoặc tenant metadata thay đổi.

Vì vậy, không chỉ update một field content rồi giữ vector cũ. Vector cũ mô tả văn bản cũ và sẽ tạo kết quả tìm kiếm sai.

Quy trình cập nhật:

1. Nhận biết source revision mới.
2. Đọc nội dung canonical mới nhất.
3. Chuẩn hóa và chunk theo phiên bản chunker hiện tại.
4. Tính chunk IDs và content hashes.
5. Tái sử dụng vector chỉ khi input hash và model contract còn khớp.
6. Tạo embedding cho chunk mới/thay đổi.
7. Validate toàn bộ vector cần ghi.
8. Index các chunk mới hoặc đã thay đổi.
9. Xóa chunk cũ không còn tồn tại.
10. Ghi nhận revision đã được đồng bộ.
11. Refresh theo yêu cầu read-after-write và chính sách ứng dụng.

### 10.1. Chỉ embed lại chunk thay đổi

Nếu document gồm 100 chunk nhưng chỉ một section thay đổi, có thể chỉ tạo embedding cho chunk bị ảnh hưởng.

Để làm được điều này, cần chunking ổn định và content hash. Nếu thay đổi một đoạn khiến mọi chunk sau đó dịch ordinal, hash sẽ cho biết nội dung nào thực sự thay đổi dù ID theo ordinal có thể khác.

Một lựa chọn là ID dựa trên hash nội dung/section, nhưng cần xử lý hai chunk giống hệt nhau trong cùng tài liệu. Một lựa chọn khác là ID theo document + generation + ordinal và so sánh hash để quyết định có cần embed lại hay không.

Chọn strategy theo tính ổn định của chunker, yêu cầu dedup và khả năng cập nhật/xóa.

### 10.2. Xóa chunk dư

Nếu document cũ có 8 chunk và bản mới chỉ còn 6, hai chunk cuối phải được xóa. Nếu chỉ upsert 6 chunk đầu, hai chunk cũ vẫn còn và có thể tiếp tục xuất hiện trong semantic search.

Có thể lưu danh sách chunk ID hiện tại trong source metadata hoặc truy vấn theo documentId/sourceVersion để xác định chunk cũ. Delete by query có thể thuận tiện nhưng cần chú ý chi phí và tính bất đồng bộ; xóa theo ID chính xác thường dễ kiểm soát hơn khi đã biết danh sách.

## 11. Giữ đồng bộ bằng event/outbox

Một request cập nhật database rồi gọi embedding provider và Elasticsearch theo kiểu tuần tự có thể gặp lỗi giữa các bước:

~~~text
Database commit thành công
        |
        v
Embedding provider timeout
        |
        v
Elasticsearch chưa cập nhật
~~~

Nguồn dữ liệu đã đổi nhưng search index vẫn cũ. Nếu API trả lỗi rồi caller retry toàn bộ transaction, có thể tạo các side effect không mong muốn.

Một mô hình đáng tin cậy là transactional outbox:

1. Trong cùng transaction database, cập nhật document và ghi một outbox event.
2. Worker đọc event và xử lý bất đồng bộ.
3. Worker lấy nội dung canonical mới nhất.
4. Tạo chunk/vector.
5. Ghi Elasticsearch.
6. Chỉ đánh dấu event complete sau khi projection được ghi thành công.

Sơ đồ:

~~~text
Application
    |
    v
Database transaction
    |                 |
    | update document |
    | write outbox    |
    v                 v
Commit atomically
        |
        v
Outbox worker
        |
        v
Extract -> Chunk -> Embed
        |
        v
Elasticsearch bulk index
        |
        v
Mark event processed
~~~

Outbox không làm embedding và Elasticsearch trở thành một transaction phân tán. Nó bảo đảm event cần xử lý không bị mất khi database commit; worker vẫn cần retry, idempotency và reconciliation.

Nếu dùng message broker, có thể publish outbox event tới broker rồi consumer cập nhật vector index. Cần xác định ack chỉ sau khi projection hoàn tất hoặc sau khi công việc đã được lưu bền vững ở một retry queue.

## 12. Xử lý event đến sai thứ tự

Giả sử document có version 20 và 21:

~~~text
Event v20 bắt đầu embed, xử lý chậm
Event v21 bắt đầu sau, hoàn tất trước
Event v20 hoàn tất sau cùng
~~~

Nếu worker v20 ghi sau v21 mà không kiểm tra version, vector mới có thể bị ghi đè bởi nội dung cũ.

Cần lưu sourceVersion và kiểm tra version trước khi ghi hoặc trước khi công bố trạng thái đồng bộ. Các chiến lược:

- Serialize xử lý theo documentId.
- Partition queue theo documentId.
- Đọc canonical latest revision ngay trước khi index.
- Bỏ qua job nếu version đã cũ hơn version hiện tại.
- Dùng external versioning hoặc cơ chế compare-and-set phù hợp với write API.
- Lưu indexedVersion để biết revision nào đang có trong Elasticsearch.

Đọc lại source mới nhất giúp giảm khả năng xử lý event cũ, nhưng vẫn cần xử lý race giữa lần đọc và lần ghi. Nếu yêu cầu nghiêm ngặt, dùng version condition ở tầng lưu trữ hoặc coordinator theo document.

Không chỉ dựa vào timestamp vì clock có thể lệch và hai event có thể có cùng thời điểm. Revision/sequence tăng đơn điệu đáng tin cậy hơn.

## 13. Tránh trạng thái nửa cũ nửa mới khi cập nhật nhiều chunk

Elasticsearch không cung cấp transaction nguyên tử cho toàn bộ chunk của một tài liệu. Khi ghi 10 chunk, một số item có thể thành công và một số item thất bại.

Cần định nghĩa consistency contract:

- Eventual consistency: chấp nhận trong một khoảng ngắn có chunk mới và chunk cũ.
- Per-document consistency: chỉ hiển thị generation mới khi toàn bộ chunk mới đã sẵn sàng.
- Strong read-after-write: cần coordinator/architecture bổ sung để chỉ xác nhận hoàn tất khi projection và refresh đã đáp ứng yêu cầu.

Một chiến lược generation:

1. Tạo generation ID mới cho document.
2. Index toàn bộ chunk mới với generation ID đó.
3. Xác nhận tất cả item thành công.
4. Cập nhật trạng thái active generation trong source of truth/coordinator.
5. Query chỉ chấp nhận generation đang active.
6. Dọn generation cũ sau khi không còn cần.

Cần thiết kế cách query biết active generation. Có thể dùng metadata được đồng bộ qua một nguồn truy cập hoặc một bước publish phù hợp với workload. Nếu phải cập nhật một marker trên từng chunk, thao tác đó cũng không nguyên tử; đừng giả định một bulk update tạo atomic switch.

Với nhiều hệ thống, eventual consistency cùng reconciliation có thể đơn giản và thực tế hơn. Ghi rõ giới hạn này trong API và vận hành.

## 14. Xóa tài liệu và vector liên quan

Khi document nguồn bị xóa, mọi chunk vector của nó cần được xóa hoặc đánh dấu không còn khả dụng.

Một delete event nên chứa:

- documentId.
- sourceVersion/tombstone version.
- tenantId nếu cần.
- eventId.
- thời điểm xóa.

Worker xóa chunk theo documentId hoặc danh sách chunk IDs. Nếu dùng delete by query, cần kiểm soát số lượng document và task status. Nếu document có hàng nghìn chunk, delete operation cũng cần retry và quan sát kết quả.

### 14.1. Tombstone để chống event cũ hồi sinh dữ liệu

Một tình huống nguy hiểm:

1. Document bị xóa ở version 30.
2. Delete event được xử lý và chunk bị xóa.
3. Một job embed cũ của version 29 hoàn tất muộn.
4. Job cũ index lại chunk và làm tài liệu xuất hiện trở lại.

Dùng tombstone/version để từ chối mọi job có version nhỏ hơn hoặc bằng revision xóa. Lưu trạng thái xóa đủ lâu theo thời hạn tối đa của retry/event replay; không xóa tombstone quá sớm nếu event cũ vẫn có thể tới.

### 14.2. Xóa và quyền riêng tư

Nếu tài liệu chứa dữ liệu cần xóa theo yêu cầu privacy, phải xác định mọi nơi nội dung/vector/cache/backup được lưu. Xóa Elasticsearch document không tự xóa source of truth, outbox payload, embedding cache hoặc backup.

Vector là dữ liệu được suy ra từ nội dung và vẫn có thể mang thông tin nhạy cảm. Áp dụng retention, access control và deletion policy cho cả vector index.

## 15. Retry và idempotency trong embedding pipeline

Các bước có thể thất bại độc lập:

- Đọc source.
- Trích xuất nội dung.
- Gọi embedding provider.
- Validate vector.
- Ghi bulk.
- Xóa chunk cũ.
- Cập nhật indexedVersion.

Thiết kế mỗi bước có thể retry.

### 15.1. Embedding request

Nếu provider timeout, có thể không biết request đã được xử lý hay chưa. Gọi lại cùng input thường không làm thay đổi source data, nhưng có thể phát sinh chi phí inference lần nữa.

Dùng cache key dựa trên model version, preprocessing version và content hash để tránh embed lại nội dung không đổi. Không giả định provider có exactly-once execution.

### 15.2. Elasticsearch upsert với ID ổn định

Index chunk bằng ID xác định và cùng payload sẽ dễ retry hơn:

~~~http
PUT knowledge-chunks-v1/_doc/guide-1001-v17-c03
{
  "documentId": "guide-1001",
  "sourceVersion": 17,
  "chunkNumber": 3,
  "contentHash": "sha256:...",
  "content": "When a source document changes...",
  "embeddingModel": "embedding-model-v2",
  "embedding": [0.12, -0.08, 0.31]
}
~~~

Nếu cùng ID và payload được gửi lại, document state được cập nhật về cùng giá trị. Nhưng nếu có writer mới hơn ghi cùng ID trong lúc retry cũ, payload cũ có thể ghi đè. Vì vậy ID ổn định cần đi cùng version guard.

### 15.3. Bulk partial failure

Bulk request có thể trả một số item thành công và một số item thất bại. Kiểm tra từng item, retry subset có thể khắc phục và giữ permanent failures trong retry/dead-letter queue.

Không retry toàn bộ batch một cách mù quáng. Khi retry, giữ nguyên chunk ID, sourceVersion, contentHash và model version để operation có thể được đối chiếu.

### 15.4. Backoff và retry budget

Dùng exponential backoff với jitter cho lỗi transient như 429 hoặc một số lỗi 5xx. Đặt giới hạn số lần thử, thời gian tồn tại của job và concurrency. Lỗi mapping/dimension mismatch là lỗi dữ liệu hoặc cấu hình; retry liên tục không giải quyết được.

Khi hết retry budget, chuyển job sang trạng thái failed/quarantine có thể replay sau khi sửa nguyên nhân.

## 16. Model version và thay đổi embedding model

Embedding model có thể được nâng cấp, đổi provider hoặc đổi preprocessing. Vector của model khác không nên được so sánh trực tiếp chỉ vì có cùng số chiều.

Lưu metadata:

- model name/identifier.
- model version.
- output dimensions.
- similarity metric.
- preprocessing version.
- chunking version.
- thời điểm tạo.

Nếu đổi model hoặc cách build embedding text, cần re-embed. Có thể triển khai migration:

1. Tạo index mới hoặc vector field mới cho model version mới.
2. Giữ index cũ phục vụ truy vấn trong lúc backfill.
3. Reprocess source documents theo batch.
4. Kiểm tra dimension và retrieval quality.
5. Chạy shadow query hoặc so sánh kết quả.
6. Chuyển traffic sang index/model mới.
7. Giữ rollback window.
8. Xóa index/vector cũ theo retention policy.

Không trộn vector từ model cũ và mới trong cùng một kNN candidate set nếu chúng thuộc hai không gian embedding khác nhau. Nếu cần hybrid search qua nhiều generation, lọc model version hoặc truy vấn từng index rồi hợp nhất kết quả theo chiến lược được đánh giá.

## 17. Chunking version cũng là một phần của schema

Thay đổi chunk size, overlap, cách giữ heading hoặc normalization sẽ làm thay đổi embedding input. Vì vậy, chunking config cần được version hóa.

Ví dụ:

~~~json
{
  "documentId": "guide-1001",
  "sourceVersion": 17,
  "chunkingVersion": "section-token-v3",
  "embeddingModel": "embedding-model-v2",
  "embeddingVersion": 2
}
~~~

Nếu chỉ đổi chunker mà không cập nhật metadata, khó xác định vector nào cần tái tạo. Có thể giữ version trong document fields hoặc index name.

Khi thay chunker:

- Tạo chunk set mới.
- So sánh số chunk và kích thước.
- Đánh giá retrieval metrics.
- Reindex/re-embed.
- Xóa chunk cũ sau khi generation mới sẵn sàng.
- Không để hai chunking version trộn lẫn mà query không filter/biết semantics.

## 18. Query kNN với vector từ cùng model

Khi người dùng gửi câu hỏi, ứng dụng phải dùng đúng model và preprocessing contract để tạo query vector.

Ví dụ kNN DSL:

~~~http
POST knowledge-chunks-v1/_search
{
  "knn": {
    "field": "embedding",
    "query_vector": [0.12, -0.08, 0.31],
    "k": 10,
    "num_candidates": 100
  },
  "_source": [
    "documentId",
    "chunkId",
    "title",
    "section",
    "content",
    "sourceVersion"
  ]
}
~~~

Vector trong ví dụ được rút gọn để minh họa; request thực tế phải có đúng số chiều. k là số kết quả mong muốn, num_candidates ảnh hưởng trade-off giữa recall và chi phí tính toán trong approximate search.

Nếu dùng filter tenant, ACL hoặc trạng thái tài liệu, đặt filter trong kNN query theo semantics của phiên bản Elasticsearch để tránh trả nội dung không được phép. Phân biệt pre-filter và post-filter vì chúng có thể cho kết quả và recall khác nhau.

### 18.1. Query vector không được dùng model khác

Nếu document vector được tạo bởi embedding-model-v2, query vector phải được tạo bằng model và preprocessing tương thích. Dùng model khác có thể tạo vector cùng dims nhưng tọa độ không cùng semantic space.

Không lấy vector đã lưu từ một tài liệu làm query vector nếu ứng dụng chưa xác định rõ model/version của nó.

### 18.2. Hybrid search

Semantic search có thể kết hợp full-text BM25 với kNN vector search. Hybrid search hữu ích khi query chứa mã, tên API hoặc từ khóa chính xác mà embedding không luôn giữ được.

Có thể:

- Chạy lexical và vector query riêng.
- Kết hợp qua reciprocal rank fusion hoặc cơ chế ranking phù hợp.
- Dùng filter chung cho tenant/access.
- Đánh giá kết quả trên bộ query có relevance labels.

Đừng giả định vector search thay thế hoàn toàn lexical search. Hai cách tìm kiếm bổ sung cho nhau.

## 19. Giữ vector đồng bộ khi metadata thay đổi

Không phải mọi thay đổi metadata đều yêu cầu tạo embedding mới.

Ví dụ:

| Trường thay đổi | Có cần re-embed? |
|---|---|
| Nội dung chunk | Có |
| Title được ghép vào embedding input | Có |
| Heading được ghép vào embedding input | Có |
| Chunking config | Có |
| Embedding model/version | Có |
| Tenant ID | Không, nếu chỉ là metadata filter; nhưng cần cập nhật quyền |
| ACL/access level | Không, nếu không nằm trong embedding text; phải đồng bộ ngay để bảo vệ dữ liệu |
| UpdatedAt | Thường không |
| Display URL | Thường không |
| Chunk ordinal | Tùy identity/chunking; kiểm tra lại mapping chunk |

Quy tắc là re-embed khi embedding input hoặc embedding contract thay đổi. Nhưng metadata filter và quyền truy cập vẫn phải được đồng bộ ngay cả khi vector không đổi.

Nếu title được thêm vào embedding input, thay đổi title phải tạo vector mới. Nếu title chỉ dùng để hiển thị, không cần re-embed.

## 20. Refresh và read-after-write

Sau khi index chunk, document có thể chưa xuất hiện ngay trong search vì Elasticsearch refresh theo chu kỳ. Index API thành công không nhất thiết đồng nghĩa search ngay lập tức nhìn thấy document.

Chính sách refresh:

- Dùng refresh mặc định cho ingest throughput thông thường.
- Dùng refresh=wait_for khi cần chờ lần refresh kế tiếp trong workflow read-after-write.
- Dùng refresh=true chỉ khi thật sự cần immediate visibility và hiểu chi phí.
- Với bulk import lớn, tránh refresh=true cho từng batch nếu không cần.

Trong Spring Data, refresh policy có thể cấu hình ở operations hoặc request tùy version. Kiểm tra API hiện tại và chọn policy phù hợp.

Đừng nhầm trạng thái “đã ghi thành công” với “đã searchable”. Theo dõi hai mốc riêng nếu nghiệp vụ cần.

## 21. Đồng bộ quyền truy cập và tenant metadata

Semantic search có thể trả đoạn văn bản nhạy cảm. Filter bảo mật phải được áp dụng trước khi kết quả được trả cho người dùng.

Mỗi chunk nên mang metadata cần thiết:

- tenantId.
- visibility/access level.
- owner hoặc ACL reference.
- document status.
- deleted/tombstone state nếu dùng.
- sourceVersion.

Query cần kết hợp kNN với filter tenant/ACL theo cách được Elasticsearch version hỗ trợ. Không chỉ lọc kết quả sau khi đã trả chúng về application nếu điều đó có thể làm lộ nội dung trong logs, traces hoặc response nội bộ.

Khi ACL thay đổi, update metadata của mọi chunk liên quan hoặc dùng một cơ chế authorization lookup đáng tin cậy. Đừng để vector index giữ quyền cũ trong khi source đã thu hồi quyền.

## 22. Kiểm thử pipeline tạo vector

Nên tách test theo trách nhiệm.

### 22.1. Unit test normalization và chunking

Kiểm tra:

- Unicode/tiếng Việt được giữ đúng.
- Heading được ghép vào chunk theo contract.
- Không cắt code block/bảng theo cách làm mất ý nghĩa nếu có quy tắc giữ cấu trúc.
- Kích thước chunk nằm trong token limit.
- Overlap đúng cấu hình.
- Thứ tự chunk ổn định.
- Cùng input và config tạo cùng chunk IDs/hashes.

### 22.2. Unit test embedding adapter

Dùng fake embedding provider để kiểm tra:

- Số vector bằng số input.
- Thứ tự mapping input/output.
- Dimension chính xác.
- Không có NaN/Infinity.
- Timeout và lỗi provider được truyền đúng.
- Batch được chia theo limit.
- Cache không trả vector từ model version khác.

Không gọi model production trong mọi unit test. Dùng fixture vector xác định để test mapping và query orchestration.

### 22.3. Integration test mapping

Với Elasticsearch test instance:

1. Tạo index có dense_vector dims và similarity đúng.
2. Index chunk có vector hợp lệ.
3. Xác nhận mapping.
4. Gửi kNN query với vector đúng dims.
5. Xác nhận document phù hợp được trả về.
6. Thử vector sai dims và xác nhận bị từ chối.
7. Thử filter tenant/ACL.
8. Đọc lại chunk để xác nhận metadata và text.

Cấu hình vector indexing và kNN có thể khác theo Elasticsearch version. Integration test phải chạy trên version tương ứng production.

## 23. Kiểm thử đồng bộ update, delete và retry

Các kịch bản cần có:

| Kịch bản | Kết quả mong đợi |
|---|---|
| Tạo document mới | Tạo đủ chunk và vector |
| Gửi lại cùng event | Không tạo duplicate chunk |
| Sửa một section | Chunk thay đổi được embed lại |
| Sửa title trong embedding input | Các chunk phụ thuộc title được tạo vector mới |
| Giảm số chunk | Chunk dư được xóa |
| Provider timeout | Job retry, source/index state được theo dõi |
| Bulk partial failure | Chỉ retry item lỗi có thể khắc phục |
| Event version cũ đến trễ | Không ghi đè revision mới |
| Xóa document | Mọi chunk bị xóa/ẩn |
| Delete event đến trước job cũ | Job cũ không hồi sinh document |
| Đổi embedding model | Tạo vector mới và migration có kiểm soát |
| ACL bị thu hồi | Search không trả chunk cũ có quyền đã thu hồi |
| Refresh chưa xảy ra | Hành vi read-after-write đúng contract |

Một test update quan trọng là xác nhận vector cũ không còn được dùng sau khi nội dung thay đổi. Có thể dùng fake embedding model trả vector khác nhau theo input để dễ quan sát.

## 24. Quan sát và vận hành pipeline

Metrics hữu ích:

- Số document chờ embedding.
- Số chunk được tạo.
- Số token/input size gửi tới model.
- Embedding latency và error rate.
- Provider rate limit/429.
- Vector dimension mismatch.
- Bulk item success/failure.
- Số chunk cũ được xóa.
- Số job retry/dead-letter.
- Độ trễ từ source commit tới searchable.
- Số document có indexedVersion nhỏ hơn sourceVersion.
- Index size, vector index build time và kNN latency.

Log nên chứa documentId, sourceVersion, chunkId, model version, batch ID và correlation ID. Không log toàn bộ nội dung hoặc vector trong production nếu không cần thiết.

Reconciliation job có thể định kỳ so sánh sourceVersion với indexedVersion để tìm document bị bỏ sót. Có thể kiểm tra số chunk kỳ vọng, content hash và model/chunking version để phát hiện projection lệch.

## 25. Các lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Lỗi khi index vector | Vector length khác dims | Kiểm tra model dimensions và mapping |
| kNN không trả kết quả phù hợp | Query vector từ model khác | Giữ model/preprocessing contract giống nhau |
| Nội dung mới nhưng kết quả vẫn cũ | Vector chưa được tạo lại | Re-embed chunk thay đổi |
| Document bị lặp trong kết quả | Chunk ID không ổn định hoặc retry tạo ID mới | Dùng deterministic ID và upsert |
| Chunk cũ vẫn xuất hiện | Không xóa chunk dư sau update | Theo dõi chunk set và delete stale IDs |
| Job cũ ghi đè job mới | Không kiểm tra sourceVersion | Version guard và ordering theo document |
| Document đã xóa xuất hiện lại | Job cũ chạy sau delete | Tombstone và reject stale version |
| Bulk ghi một phần | Item-level failure không được xử lý | Đọc từng item và retry subset |
| Embedding cost tăng bất thường | Embed lại mọi chunk dù input không đổi | Content hash và embedding cache |
| Model mới cho kết quả kém | Trộn vector model version hoặc chưa reindex | Tách generation/index và đánh giá lại |
| Query vector sai dimension | Model/query adapter không khớp index | Validate dimensions trước query |
| Search chưa thấy chunk vừa ghi | Chưa refresh | Chọn refresh policy theo yêu cầu |
| Lộ tài liệu tenant khác | Thiếu filter tenant/ACL trong vector search | Áp dụng filter truy cập trong query |
| Số chunk tăng quá nhanh | Chunk quá nhỏ hoặc overlap lớn | Benchmark chunk size/overlap |
| Reindex gây downtime | Migration không có generation/alias plan | Backfill, validate và cutover có kiểm soát |

## 26. Quy trình triển khai end-to-end

Một quy trình có thể áp dụng:

1. Chọn embedding model và ghi nhận model version, dimensions, metric.
2. Xác định source of truth và source revision.
3. Định nghĩa text extraction, normalization và embedding input.
4. Thiết kế chunking theo cấu trúc, token limit và query pattern.
5. Tạo deterministic chunk ID và content hash.
6. Tạo dense_vector mapping có dims/similarity/index options phù hợp.
7. Tạo index trước khi ingest.
8. Batch embedding và validate vector.
9. Bulk index chunk với metadata/version.
10. Kiểm tra item-level bulk response.
11. Xóa chunk cũ sau khi chunk mới được ghi thành công.
12. Dùng outbox/event worker để giữ source và search projection đồng bộ.
13. Bảo vệ update/delete bằng version guard và tombstone.
14. Thiết lập retry/backoff, idempotency và dead-letter.
15. Đồng bộ tenant/ACL metadata.
16. Đặt refresh policy theo read-after-write contract.
17. Đánh giá retrieval quality và latency.
18. Theo dõi backlog, indexedVersion và lỗi để reconciliation.

## 27. Bảng tra cứu nhanh

| Nhu cầu | Cách làm |
|---|---|
| Biến văn bản thành vector | Embedding model với contract cố định |
| Giữ ngữ cảnh tài liệu dài | Chunk theo section/token và overlap có kiểm soát |
| Lưu vector | dense_vector với dims đúng |
| Tìm nearest neighbors | kNN query với query vector cùng model |
| Theo dõi nguồn gốc vector | documentId, sourceVersion, model/chunking version |
| Phát hiện nội dung đổi | Content hash và source revision |
| Retry không tạo duplicate | Chunk ID xác định và upsert |
| Chỉ embed phần đổi | So sánh embedding input hash |
| Xóa chunk cũ | Theo dõi chunk IDs và stale chunks |
| Chống event cũ | Version guard và tombstone |
| Không mất sự kiện cập nhật | Transactional outbox hoặc durable queue |
| Đổi model | Re-embed và migration index/generation |
| Đồng bộ quyền | tenant/ACL metadata và filter |
| Kiểm tra ghi vector | Dimension, finite values, model version |
| Đảm bảo searchable | Refresh policy phù hợp |
| Phát hiện index lệch nguồn | Reconciliation sourceVersion/indexedVersion |

Vector chỉ phản ánh đúng nội dung nếu embedding input, chunking và model contract được quản lý nhất quán. Hãy giữ nguồn dữ liệu chuẩn, tạo chunk có identity ổn định, lưu sourceVersion/contentHash/modelVersion cùng dense_vector và kiểm tra số chiều trước khi index. Khi tài liệu thay đổi, tạo lại vector cho chunk bị ảnh hưởng và xóa chunk cũ; khi xóa tài liệu, dùng tombstone/version để job cũ không thể làm dữ liệu xuất hiện trở lại. Transactional outbox, retry có giới hạn, bulk item handling và reconciliation giúp search projection theo kịp source trong môi trường bất đồng bộ. Khi thay model hoặc chunking, hãy tạo generation/index mới, re-embed và chuyển traffic sau khi xác nhận chất lượng.
