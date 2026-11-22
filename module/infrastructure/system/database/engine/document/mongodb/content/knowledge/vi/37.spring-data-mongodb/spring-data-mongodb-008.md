# @Version, optimistic locking và xử lý cập nhật xung đột trong Spring Data MongoDB

Một document MongoDB có thể được đọc và chỉnh sửa đồng thời từ nhiều người dùng, nhiều request hoặc nhiều instance của một ứng dụng Spring Boot. Ví dụ, hai nhân viên cùng mở biểu mẫu chỉnh sửa một bài viết. Người thứ nhất đổi tiêu đề và nhấn Lưu; người thứ hai, đang giữ bản dữ liệu cũ, đổi phần nội dung rồi nhấn Lưu. Nếu cả hai request đều ghi đè **toàn bộ document** theo thứ tự đến server, thay đổi của người thứ nhất có thể biến mất mà không có cảnh báo.

Trong chương **Spring Data MongoDB** của module **Database Engine Document MongoDB**, bài **“@Version, optimistic locking và xử lý cập nhật xung đột”** giải thích cách dùng annotation `@Version` để phát hiện và ngăn **lost update**, cách hoạt động của phép ghi có điều kiện theo version, cách trả lỗi cho API, khi nào nên retry, và giới hạn của cơ chế này đối với các thao tác cập nhật khác, giao dịch nhiều document, cũng như side effects nghiệp vụ.

Sau bài học, bạn có thể:

1. Nhận diện tình huống **read–modify–write** gây lost update.
2. Ánh xạ một trường phiên bản với `org.springframework.data.annotation.Version`.
3. Hiểu vì sao Spring Data kiểm tra **`_id` cộng `version`** khi lưu một entity đã có.
4. Xử lý `OptimisticLockingFailureException` thay vì ghi đè thay đổi của người khác.
5. Truyền **expectedVersion** từ client để phát hiện biểu mẫu đã cũ qua nhiều HTTP requests.
6. Áp dụng compare-and-set (CAS) bằng `MongoTemplate.updateFirst()` hoặc `findAndModify()` khi không muốn save toàn document.
7. Phân biệt version checking với atomic updates, unique indexes, pessimistic locks và MongoDB transactions.
8. Thiết kế retry, conflict resolution, audit, migration, monitoring và kiểm thử cạnh tranh.

> **Phạm vi:** ví dụ giả định Spring Boot với Spring Data MongoDB và MongoDB replica set/standalone lab hỗ trợ các thao tác mô tả. API, thời điểm khởi tạo version, codec và kết quả lỗi có thể phụ thuộc phiên bản Spring Data. Các đoạn mã là bài học thực hành; hãy chạy trong môi trường thử nghiệm, không trực tiếp sửa dữ liệu production.

## 1. Lost update là lỗi gì?

Giả sử collection `articles` có:

```javascript
{
  _id: "article-1001",
  title: "MongoDB cơ bản",
  body: "Nội dung ban đầu"
}
```

Hai người mở cùng bài viết:

```text
Thời gian       Người A                     Người B
   |
   |       GET article-1001
   |       title = "MongoDB cơ bản"
   |       body  = "Nội dung ban đầu"
   |
   |                                    GET article-1001
   |                                    title = "MongoDB cơ bản"
   |                                    body  = "Nội dung ban đầu"
   |
   |       đổi title thành
   |       "MongoDB nâng cao"
   |
   |       SAVE toàn document
   |       -> thành công
   |
   |                                    đổi body thành
   |                                    "Ví dụ CRUD mới"
   |
   |                                    SAVE toàn document cũ
   |                                    -> thành công
   |
   v

Kết quả có thể:
  title = "MongoDB cơ bản"      <-- thay đổi của A bị mất
  body  = "Ví dụ CRUD mới"
```

Vấn đề không phải MongoDB ghi hai lệnh cùng lúc vào một document một cách không nguyên tử. **Mỗi phép ghi single-document vẫn có tính nguyên tử theo MongoDB.** Lỗi phát sinh vì **điều kiện kinh doanh gồm cả bước đọc trước khi ghi**, trong khi phép ghi thứ hai dựa trên một bản dữ liệu đã lỗi thời.

### Lost update khác lỗi duplicate key

- **Duplicate key:** hai thao tác tạo giá trị vi phạm unique index.
- **Lost update:** một thay đổi hợp lệ bị ghi đè bởi bản dữ liệu đọc trước đó.
- **Write conflict:** một loại xung đột có thể phát sinh ở tầng database/transaction.
- **Optimistic locking failure:** ứng dụng phát hiện phiên bản mà client muốn sửa không còn đúng.

Các lỗi này có thể xảy ra trong cùng hệ thống nhưng không phải cùng một khái niệm.

## 2. Giải pháp: gắn version vào mỗi document

Thêm trường `version`:

```javascript
{
  _id: "article-1001",
  version: NumberLong("4"),
  title: "MongoDB cơ bản",
  body: "Nội dung ban đầu"
}
```

Hai người đều đọc bản **version 4**. Khi lưu, thay vì chỉ tìm theo `_id`, ứng dụng yêu cầu:

```text
Chỉ chấp nhận update nếu:
  _id == "article-1001"
  VÀ
  version == 4
```

Nếu điều kiện khớp, cập nhật data và tăng version thành 5 **trong cùng thao tác ghi nguyên tử trên document**.

```text
Người A đọc v4                 Người B đọc v4
     |                              |
     v                              v
SAVE where id=1001, version=4    SAVE where id=1001, version=4
     |                              |
     v                              v
Matched document                  Không còn version=4
     |                              |
     v                              v
Ghi data + version=5             XUNG ĐỘT: ghi bị từ chối
```

Trong Spring Data MongoDB, `@Version` giúp tự động hóa cơ chế này cho những thao tác entity được framework hỗ trợ, đặc biệt là `save()`.

## 3. Optimistic locking là gì?

**Optimistic locking** giả định xung đột ghi không xảy ra ở mọi thao tác. Nó không giữ một mutex hoặc database lock độc quyền xuyên suốt từ khi người dùng mở biểu mẫu đến lúc người đó nhấn Lưu. Thay vào đó:

1. Đọc document cùng **version hiện tại**.
2. Người dùng hoặc service tính thay đổi.
3. Ghi với điều kiện **version vẫn bằng giá trị đã đọc**.
4. Nếu ghi thành công, tăng version.
5. Nếu điều kiện không khớp, trả **conflict** và quyết định cách giải quyết.

Đây là một dạng **compare-and-set (CAS)** ở cấp document.

### Optimistic và pessimistic locking

| Tiêu chí | Optimistic locking | Pessimistic locking |
| --- | --- | --- |
| Cách bảo vệ | Phát hiện thay đổi trước khi ghi | Giữ khóa/ngăn cạnh tranh theo giao thức |
| Khi không có xung đột | Ít điều phối | Có thể phải giữ lock |
| Khi có xung đột | Một writer thất bại và cần xử lý | Writer khác có thể phải chờ |
| Tác động request dài | Không giữ lock suốt thời gian sửa form | Khóa dài dễ gây contention |
| Cách Spring Data MongoDB thường làm | `@Version` và CAS | Không có mặc định “khóa form” dựa trên `@Version` |

Không nhầm chữ **locking** trong tên với việc Spring Data đang “lock toàn bộ document trong nhiều phút”. `@Version` là cơ chế **phát hiện xung đột**, không cấp quyền sở hữu lâu dài cho người đang xem dữ liệu.

## 4. `@Version` ở đâu trong Spring Data MongoDB?

Annotation:

```java
import org.springframework.data.annotation.Version;
```

Đây là annotation của **Spring Data**, không phải `jakarta.persistence.Version` dùng cho JPA. Cả hai có ý tưởng optimistic locking, nhưng MongoDB mapping và storage behavior được Spring Data MongoDB triển khai riêng.

Một document domain:

```java
import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.Version;
import org.springframework.data.mongodb.core.mapping.Document;

@Document(collection = "articles")
public class Article {

    @Id
    private String id;

    @Version
    private Long version;

    private String title;
    private String body;

    public Article() {
    }

    public Article(String id, String title, String body) {
        this.id = id;
        this.title = title;
        this.body = body;
    }

    public String getId() {
        return id;
    }

    public void setId(String id) {
        this.id = id;
    }

    public Long getVersion() {
        return version;
    }

    public void setVersion(Long version) {
        this.version = version;
    }

    public String getTitle() {
        return title;
    }

    public void setTitle(String title) {
        this.title = title;
    }

    public String getBody() {
        return body;
    }

    public void setBody(String body) {
        this.body = body;
    }
}
```

Giải thích:

- `@Document(collection = "articles")` ánh xạ class vào MongoDB collection.
- `@Id` ánh xạ `id` tới BSON `_id`.
- `@Version` đánh dấu property mà Spring Data dùng để quản lý **entity version**.
- Dùng `Long` (wrapper) giúp biểu diễn trạng thái **chưa có version** bằng `null` trước lần insert đầu.
- Thông thường application code **không nên tự tăng `version`** khi dùng `Repository.save()`; framework quản lý trong các code paths được hỗ trợ.

### Vì sao không dùng `@jakarta.persistence.Version`?

Một dự án Spring Boot có cả JPA và MongoDB có thể import nhầm annotation. Nếu entity thuộc Spring Data MongoDB, hãy dùng:

```java
org.springframework.data.annotation.Version
```

Không giả định annotation từ JPA sẽ được MongoDB converter hiểu theo cùng cơ chế.

## 5. Thêm repository

Spring Data MongoDB hỗ trợ repository API:

```java
import org.springframework.data.mongodb.repository.MongoRepository;

public interface ArticleRepository
        extends MongoRepository<Article, String> {
}
```

Với Spring Boot, dependency thường là Spring Data MongoDB starter, ví dụ trong Maven:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-data-mongodb</artifactId>
</dependency>
```

Các version cụ thể nên được quản lý thống nhất qua **Spring Boot dependency management/BOM** phù hợp. Đừng trộn tùy tiện các Spring Data artifacts từ những major versions khác nhau.

Ứng dụng cũng phải cấu hình URI, authentication, TLS và database name đúng môi trường; ví dụ:

```properties
# Placeholder; lấy URI thật từ secret management.
spring.data.mongodb.uri=${MONGODB_URI}
```

Đây là cú pháp tham chiếu biến môi trường trong Spring configuration. Không commit mật khẩu thật vào `application.properties`.

## 6. Tạo document mới và version ban đầu

Một service tạo document:

```java
Article article = new Article(
    "article-1001",
    "MongoDB cơ bản",
    "Nội dung ban đầu"
);

Article saved = articleRepository.save(article);

System.out.println(saved.getVersion());
```

Trong Spring Data MongoDB, framework có quy tắc khởi tạo version cho entity mới. Theo quy ước thông dụng được tài liệu Spring Data mô tả, **wrapper numeric version** như `Long` thường bắt đầu ở **0**, trong khi **primitive numeric version** thường có giá trị khởi đầu **1** do cách framework phân biệt new entity.

Vì vậy **không hard-code một giá trị ban đầu cho mọi model và mọi version**. Lựa chọn `Long version` nullable, để Spring Data quyết định insert state, sau đó đọc lại giá trị thực trong integration test là cách ít gây nhầm lẫn.

### Không tự set version trên create request

Không nên để frontend gửi bất kỳ version rồi gán nguyên vào entity mới:

```json
{
  "id": "article-1001",
  "version": 99,
  "title": "MongoDB cơ bản"
}
```

Version là **metadata đồng bộ hóa do server quản lý**. Đối với create, request DTO nên chứa nội dung nghiệp vụ; phiên bản được xác định bởi persistence layer. Với update, client có thể gửi **expectedVersion** để chỉ ra phiên bản nó đang sửa, nhưng không được coi đó là một số có thể viết trực tiếp theo ý muốn.

## 7. Spring Data xử lý `save()` thế nào?

Với một entity đã tồn tại và đã có version, Spring Data MongoDB thực hiện update có kiểm tra version. Có thể hình dung điều kiện logic:

```javascript
db.articles.updateOne(
  {
    _id: "article-1001",
    version: NumberLong("4")
  },
  {
    $set: {
      title: "MongoDB nâng cao",
      body: "Nội dung ban đầu"
    },
    $inc: { version: NumberLong("1") }
  }
);
```

Đây là **pseudocode về ý tưởng**, không phải cam kết `Repository.save()` luôn phát ra đúng lệnh `updateOne` với cùng tổ hợp operators. MongoDB converter/framework có thể chọn cách tạo BSON update khác theo version và entity mapping. Điểm cốt lõi là:

- Ghi được thực hiện **có điều kiện trên version**.
- Version được tăng khi update thành công qua đường persistence được hỗ trợ.
- Nếu bản version cũ không còn khớp, Spring Data ném lỗi **optimistic locking failure**.

**Không cần tạo unique index trên `{_id, version}`** để CAS hoạt động: `_id` vốn có unique index; `version` là điều kiện bổ sung của phép ghi nguyên tử.

### Vì sao vẫn cần atomicity của MongoDB?

Hai request đồng thời:

```text
WHERE id = X AND version = 4
```

phải được kiểm tra **cùng lúc ghi**. Nếu ứng dụng chỉ làm:

```text
SELECT version
IF version = 4:
    UPDATE by id only
```

thì có thể có một writer khác chen vào giữa bước SELECT và UPDATE. MongoDB single-document conditional update giải quyết khoảng hở này.

## 8. Minh họa hai entity cũ và một xung đột

Ví dụ code tuần tự nhưng mô phỏng hai request đã đọc trước khi ai ghi:

```java
Article copyA = articleRepository
    .findById("article-1001")
    .orElseThrow();

Article copyB = articleRepository
    .findById("article-1001")
    .orElseThrow();

// Giả sử cả hai đều đọc version 4.

copyA.setTitle("MongoDB nâng cao");
Article savedA = articleRepository.save(copyA);

// Database đã chuyển sang version 5.
copyB.setBody("Ví dụ CRUD mới");

// Lần lưu thứ hai không thể ghi như thể vẫn là version 4.
articleRepository.save(copyB);
```

Khi optimistic locking hoạt động theo cấu hình hỗ trợ và write concern có acknowledgment, lần `save(copyB)` sẽ thất bại với một exception thuộc họ:

```java
org.springframework.dao.OptimisticLockingFailureException
```

Điều này **ngăn ghi đè âm thầm**; nó **chưa tự trộn** phần tiêu đề mới của A với phần nội dung của B.

### Trạng thái document sau ví dụ

```javascript
{
  _id: "article-1001",
  version: NumberLong("5"),
  title: "MongoDB nâng cao",
  body: "Nội dung ban đầu"
}
```

Thay đổi body của B **chưa được lưu**. Ứng dụng phải thông báo hoặc giải quyết xung đột theo nghiệp vụ.

## 9. Exception và điều kiện để phát hiện xung đột

Lỗi tiêu biểu:

```java
import org.springframework.dao.OptimisticLockingFailureException;
```

Spring Data báo lỗi khi cập nhật entity có version nhưng **không tìm thấy document khớp với ID và expected version** theo semantics của operation.

Ví dụ:

```java
try {
    articleRepository.save(copyB);
} catch (OptimisticLockingFailureException ex) {
    // Không ghi đè bản mới; trả conflict hoặc
    // reload rồi áp dụng quy tắc merge rõ ràng.
    throw ex;
}
```

**Không bắt rồi nuốt exception**:

```java
try {
    articleRepository.save(copyB);
} catch (OptimisticLockingFailureException ex) {
    // SAI: bỏ qua rồi trả "Lưu thành công".
}
```

Làm vậy khiến client nghĩ dữ liệu đã được lưu dù write bị từ chối.

### Phải có write concern được xác nhận

Optimistic locking cần kết quả ghi cho biết có document nào được matched/modified. **Unacknowledged writes (`w:0`) không cung cấp kết quả xác nhận đáng tin cậy** để Spring Data phát hiện phiên bản không khớp. Do đó phải dùng **acknowledged write concern**.

Ví dụ cấu hình ở mức MongoDB database:

```java
import com.mongodb.WriteConcern;

MongoDatabase db = mongoClient
    .getDatabase("appdb")
    .withWriteConcern(WriteConcern.ACKNOWLEDGED);
```

Đây là minh họa nguyên tắc, không phải cách duy nhất cấu hình Spring Data. Nếu yêu cầu độ bền khi failover, có thể cân nhắc `MAJORITY` theo topology/RPO; **`ACKNOWLEDGED` là yêu cầu có phản hồi**, còn `MAJORITY` là chính sách replication acknowledgment mạnh hơn, không phải cơ chế optimistic locking riêng.

## 10. @Version chưa đủ để bảo vệ biểu mẫu HTTP bị stale

Xem hai request web cách nhau nhiều phút:

```text
10:00  User A GET /articles/1001    -> version 4
10:01  User B chỉnh sửa và SAVE      -> version 5
10:05  User A gửi form cũ            -> mong muốn lưu dữ liệu dựa trên v4
```

Một cách viết service **sai mục tiêu phát hiện form cũ**:

```java
public Article update(String id, UpdateRequest request) {
    Article current = articleRepository.findById(id)
        .orElseThrow();

    current.setTitle(request.title());
    current.setBody(request.body());

    return articleRepository.save(current);
}
```

Vì service **vừa đọc lại version mới nhất**, rồi save ngay, request của User A có thể ghi đè những field đã thay đổi của User B mà không gặp conflict nào. `@Version` chỉ bảo vệ khoảng thời gian **giữa lần đọc của chính service và lần ghi của service**; nó không biết client đã dựa trên bản v4 trừ khi application truyền expected version qua HTTP.

### Giải pháp: client gửi expectedVersion

Response GET:

```json
{
  "id": "article-1001",
  "version": 4,
  "title": "MongoDB cơ bản",
  "body": "Nội dung ban đầu"
}
```

Request update:

```json
{
  "expectedVersion": 4,
  "title": "MongoDB cơ bản",
  "body": "Ví dụ CRUD mới"
}
```

Backend phải so expectedVersion với phiên bản hiện tại rồi **vẫn ghi có CAS**. Chỉ so trước bằng một lệnh read không đủ để ngăn race xảy ra sau bước kiểm tra.

## 11. Thiết kế DTO update với expectedVersion

Ví dụ Java record:

```java
public record UpdateArticleRequest(
    Long expectedVersion,
    String title,
    String body
) {
}
```

Một service xử lý:

```java
import java.util.Objects;
import org.springframework.dao.OptimisticLockingFailureException;
import org.springframework.stereotype.Service;

@Service
public class ArticleService {

    private final ArticleRepository repository;

    public ArticleService(ArticleRepository repository) {
        this.repository = repository;
    }

    public Article updateArticle(
            String id, UpdateArticleRequest request) {

        if (request.expectedVersion() == null) {
            throw new IllegalArgumentException(
                "expectedVersion là bắt buộc");
        }

        Article current = repository.findById(id)
            .orElseThrow(() ->
                new IllegalArgumentException("Không thấy article"));

        if (!Objects.equals(
                current.getVersion(),
                request.expectedVersion())) {
            throw new OptimisticLockingFailureException(
                "Document đã thay đổi; tải lại trước khi lưu");
        }

        current.setTitle(request.title());
        current.setBody(request.body());

        // Vẫn bắt buộc CAS tại database:
        return repository.save(current);
    }
}
```

Ở đây có **hai lần bảo vệ**:

1. Check early: dễ trả lỗi rõ nghĩa khi client đã gửi form cũ.
2. CAS khi `save()`: bảo vệ tình huống một request khác update **sau lần read và trước lần save**.

Nếu service chỉ làm check early mà gọi raw `updateOne({_id:id},...)` không có version condition, hệ thống vẫn có race condition.

### DTO không nên trực tiếp là persistence entity

Không nên lấy request JSON rồi bind trực tiếp thành `Article` với `@Version` và gọi `save()` khi các field không được kiểm soát. Client có thể gửi hoặc bỏ fields ngoài ý muốn; việc save nguyên entity có thể ghi đè dữ liệu không nằm trong form.

Sử dụng **request DTO** tách khỏi entity và whitelist những fields cho phép cập nhật.

## 12. Trả HTTP 409 Conflict cho optimistic locking

Khi một request muốn lưu bản version cũ, một lựa chọn API phổ biến là:

```http
HTTP/1.1 409 Conflict
Content-Type: application/json

{
  "code": "VERSION_CONFLICT",
  "message": "Dữ liệu đã được thay đổi. Hãy tải lại trước khi lưu."
}
```

Spring có thể ánh xạ exception bằng `@RestControllerAdvice`:

```java
import java.util.Map;
import org.springframework.dao.OptimisticLockingFailureException;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
public class ConflictExceptionHandler {

    @ExceptionHandler(
        OptimisticLockingFailureException.class)
    public ResponseEntity<Map<String, String>> conflict(
            OptimisticLockingFailureException ex) {

        return ResponseEntity
            .status(HttpStatus.CONFLICT)
            .body(Map.of(
                "code", "VERSION_CONFLICT",
                "message",
                "Dữ liệu đã thay đổi; tải lại bản mới"));
    }
}
```

Đừng trả nội dung exception thô chứa thông tin nhạy cảm của entity/database cho client. Server logs có thể ghi correlation ID và stack trace với chính sách bảo mật phù hợp.

### Có luôn dùng 409 không?

Không bắt buộc mọi API đều dùng 409. Nếu thiết kế HTTP theo **conditional requests** với `If-Match`/ETag, việc precondition không còn đúng thường tương ứng **412 Precondition Failed**. Nếu API không dùng HTTP precondition mà nhận `expectedVersion` trong body và phát hiện xung đột nghiệp vụ, **409 Conflict** là lựa chọn phổ biến.

Quy tắc quan trọng hơn mã cụ thể là **API contract ổn định**, lỗi có thể phân biệt được và client biết nên làm gì tiếp theo.

## 13. ETag và If-Match: optimistic concurrency ở tầng HTTP

Một REST API có thể trả version bằng ETag:

```http
HTTP/1.1 200 OK
ETag: "v4"
Content-Type: application/json

{
  "id": "article-1001",
  "title": "MongoDB cơ bản",
  "body": "Nội dung ban đầu"
}
```

Client gửi:

```http
PUT /articles/article-1001
If-Match: "v4"
Content-Type: application/json

{
  "title": "MongoDB nâng cao",
  "body": "Nội dung ban đầu"
}
```

Backend diễn giải ETag thành expected version **theo hợp đồng do server thiết kế** và thực hiện CAS khi ghi. Nếu current version đã thành 5, trả:

```http
HTTP/1.1 412 Precondition Failed
```

**ETag là representation token của HTTP**, không nhất thiết phải expose raw MongoDB field trực tiếp. Cách xây ETag có thể dựa vào version, hash của representation hoặc một token opaque; phải quy định **strong/weak ETag** và cách so sánh phù hợp HTTP conditional requests.

### ETag có thay CAS không?

Không. Đọc If-Match rồi so với version trong một lệnh `findById()` **chưa đủ**. Database write vẫn phải có condition version để không có request khác chen vào giữa.

## 14. MongoTemplate.save() với @Version

Ngoài repository, Spring Data MongoDB cung cấp `MongoTemplate`:

```java
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.stereotype.Service;

@Service
public class ArticleTemplateService {
    private final MongoTemplate template;

    public ArticleTemplateService(MongoTemplate template) {
        this.template = template;
    }

    public Article rename(String id, String newTitle) {
        Article current = template.findById(
            id, Article.class);

        if (current == null) {
            throw new IllegalArgumentException(
                "Article không tồn tại");
        }

        current.setTitle(newTitle);
        return template.save(current);
    }
}
```

Với `Article` có `@Version`, `MongoTemplate.save()` cũng hỗ trợ optimistic version checking trên entity đang tồn tại.

**Nhưng giống repository**, ví dụ này chỉ chống xung đột giữa lần template đọc và lần save trong cùng luồng. Nó **không tự phát hiện** một form HTTP đã được mở từ trước nếu người dùng không truyền expectedVersion.

## 15. Partial update: CAS bằng MongoTemplate.updateFirst()

Không phải lúc nào cũng nên load entity và save toàn document. Giả sử API chỉ thay `title`, không được làm thay đổi `body`.

Một CAS update trực tiếp:

```java
import com.mongodb.client.result.UpdateResult;
import org.springframework.dao.OptimisticLockingFailureException;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.data.mongodb.core.query.Update;

public void updateTitle(
        MongoTemplate template,
        String id,
        long expectedVersion,
        String newTitle) {

    Query query = Query.query(
        Criteria.where("_id").is(id)
            .and("version").is(expectedVersion)
    );

    Update update = new Update()
        .set("title", newTitle)
        .inc("version", 1L);

    UpdateResult result =
        template.updateFirst(query, update, Article.class);

    if (result.getMatchedCount() == 0) {
        throw new OptimisticLockingFailureException(
            "Version không khớp hoặc document đã bị xóa");
    }
}
```

Đây là **một lệnh MongoDB atomic update trên một document** với điều kiện ID + version.

### Vì sao dùng `getMatchedCount()`?

Nếu không có document khớp `{_id,version}`, điều kiện CAS thất bại. `getMatchedCount() == 0` giúp xác định việc không ghi được do không match (dù chưa biết chính xác là document bị xóa hay version đã thay đổi).

`getModifiedCount()` trả số document thực sự sửa đổi, có thể khác matched count trong một số update operations; để xác nhận CAS condition có match, **matched count** là tín hiệu trực tiếp hơn.

### Spring Data có thể tự tăng version trong Update API

Với những phiên bản Spring Data MongoDB được tài liệu mô tả, update operations theo entity mapping có thể **tự tăng field `@Version` nếu update chưa chỉ định field version**. Trong ví dụ trên, `.inc("version", 1L)` được viết **tường minh**, nên cần bảo đảm cấu hình/mapping không thực hiện tăng version lần thứ hai.

Quan trọng hơn: **chỉ tự tăng version mà không có điều kiện expected version trong query không biến update thành optimistic locking CAS**. Khi dùng `updateFirst()`/`updateMulti()`/bulk operations, phải hiểu chính xác query và update BSON thực tế của code path.

### Cẩn thận với mapped field name

Nếu domain property version được ánh xạ bằng `@Field("revision")` hoặc field name strategy khác, query/update phải dùng mapping phù hợp. Khi thao tác qua `MongoTemplate` với entity class, Spring Data có thể map Java property names sang BSON names; khi thao tác raw driver, cần dùng **tên field thực trong MongoDB**.

## 16. findAndModify: CAS và trả document sau update

Một API muốn nhận chính phiên bản mới ngay sau update có thể dùng `findAndModify()`:

```java
import org.springframework.dao.OptimisticLockingFailureException;
import org.springframework.data.mongodb.core.FindAndModifyOptions;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.data.mongodb.core.query.Update;

public Article updateTitleReturningNew(
        MongoTemplate template,
        String id,
        long expectedVersion,
        String newTitle) {

    Query query = Query.query(
        Criteria.where("_id").is(id)
            .and("version").is(expectedVersion));

    Update update = new Update()
        .set("title", newTitle)
        .inc("version", 1L);

    Article updated = template.findAndModify(
        query,
        update,
        FindAndModifyOptions.options().returnNew(true),
        Article.class
    );

    if (updated == null) {
        throw new OptimisticLockingFailureException(
            "Không tìm thấy phiên bản cần cập nhật");
    }

    return updated;
}
```

`returnNew(true)` yêu cầu nhận **document sau cập nhật** theo semantics của operation. Nếu filter không match, API có thể trả `null`.

Không bật `upsert(true)` cho một thao tác **chỉ được phép sửa record đã tồn tại theo expected version**. Nếu upsert bật nhầm, một request conflict có thể chuyển thành ý định tạo document mới ngoài hợp đồng nghiệp vụ.

## 17. So sánh save và cập nhật từng field

| Cách làm | Điểm mạnh | Rủi ro/chú ý |
| --- | --- | --- |
| `repository.save(entity)` | Dễ dùng, @Version được Spring Data quản lý trên entity | Đọc/sửa toàn entity; cần expectedVersion từ client để nhận biết form cũ |
| `mongoTemplate.save(entity)` | Tương tự repository nhưng linh hoạt template | Vẫn có read–modify–write và phiên bản entity |
| `updateFirst(query id+version, update)` | Ghi partial fields với CAS tường minh | Developer phải giữ đúng filter và version increment |
| `findAndModify(id+version, update)` | CAS và trả bản mới trong một round trip logic | Phải xử lý null/no-match và không bật upsert tùy tiện |
| Raw MongoDB driver CAS update | Kiểm soát chính xác lệnh BSON | Không có Spring Data tự quản lý version |
| `updateMany()` với filter rộng | Phù hợp bulk operation có chủ đích | Không tự cung cấp per-entity stale state protection |

Trong hệ thống CRUD có form chỉnh sửa, `Repository.save()` + expectedVersion thường dễ đọc. Trong API thay một field hoặc trạng thái, **CAS update có điều kiện** thường diễn đạt ý đồ tốt hơn và giảm nguy cơ ghi đè field không liên quan.

## 18. Đừng mặc định mọi update đều đi qua @Version

Annotation `@Version` không biến MongoDB server thành một hệ thống **tự từ chối mọi writer** khi version sai. Nó hoạt động thông qua những operation/mapping được Spring Data triển khai.

Các đường ghi khác có thể gồm:

- `MongoRepository.save()`.
- `MongoTemplate.save()`.
- `MongoTemplate.updateFirst()`, `findAndModify()`.
- Bulk operations.
- `MongoCollection.updateOne()` từ Java Sync Driver.
- `mongosh` hoặc MongoDB Compass.
- Migration scripts, data repair jobs.
- CDC/ETL writers, background processors.

Nếu một script chạy:

```javascript
db.articles.updateOne(
  { _id: "article-1001" },
  { $set: { title: "Tiêu đề từ script" } }
);
```

thì lệnh đó **không tự biết annotation Java `@Version`**. Nó có thể đổi title mà **không tăng version**. Một request Spring Data đang giữ cùng version có thể vẫn vượt qua CAS sau đó và ghi đè thay đổi của script.

### Quy tắc cho mọi writer

Nếu hệ thống chọn version là cơ chế chống lost update, **mọi đường cập nhật những trường cần bảo vệ** nên tuân theo một contract:

1. Có expected version (trừ những update nguyên tử được cố ý thiết kế khác).
2. Query gồm ID và version hoặc điều kiện trạng thái có ý nghĩa tương đương.
3. Update dữ liệu và tăng version **trong cùng operation**.
4. Kiểm tra matched count/no-match.
5. Có xử lý conflict và metrics.

Script tự động không được bỏ qua contract chỉ vì chạy ngoài Spring Boot.

## 19. Viết CAS bằng MongoDB Java Sync Driver

Nếu có một process không dùng Spring Data, vẫn có thể phối hợp optimistic locking bằng MongoDB atomic updates:

```java
import com.mongodb.client.MongoCollection;
import com.mongodb.client.model.Filters;
import com.mongodb.client.model.Updates;
import com.mongodb.client.result.UpdateResult;
import org.bson.Document;

UpdateResult result = collection.updateOne(
    Filters.and(
        Filters.eq("_id", "article-1001"),
        Filters.eq("version", 4L)
    ),
    Updates.combine(
        Updates.set("title", "Tiêu đề mới"),
        Updates.inc("version", 1L)
    )
);

if (result.getMatchedCount() == 0) {
    // Conflict: không có bản (_id, version) kỳ vọng.
}
```

Ví dụ giả định `collection` có kiểu `MongoCollection<Document>` và field `version` thực sự được lưu như BSON Int64. Khi schema dùng BSON Int32 hoặc field name khác, cần query type/convention phù hợp.

Đây là cùng ý tưởng CAS mà `@Version` tự động hóa cho những repository operations được hỗ trợ.

## 20. Vì sao chỉ đọc version rồi update by ID là sai?

Một cách triển khai sai:

```java
Article current = repository.findById(id).orElseThrow();

if (current.getVersion().equals(expectedVersion)) {
    // SAI: query chỉ có id, không kiểm tra version khi ghi.
    template.updateFirst(
        Query.query(Criteria.where("_id").is(id)),
        new Update().set("title", newTitle),
        Article.class
    );
}
```

Giữa lệnh read và update, writer khác có thể sửa document. Kể cả Spring Data tự tăng version khi update, lệnh trên vẫn có thể **đè title mới** vì không yêu cầu current version phải bằng expectedVersion.

Đúng hơn:

```java
Query query = Query.query(
    Criteria.where("_id").is(id)
        .and("version").is(expectedVersion));

Update update = new Update()
    .set("title", newTitle)
    .inc("version", 1L);
```

Điều kiện version phải nằm trong **cùng atomic database operation** với thay đổi.

## 21. @Version có thay thế update nguyên tử như $inc không?

Không. Một số tác vụ không cần đọc–sửa–ghi toàn entity:

```javascript
db.counters.updateOne(
  { _id: "views-article-1001" },
  { $inc: { count: 1 } }
);
```

Hai writers cùng dùng `$inc` sẽ không bị **lost increment** theo cùng kiểu hai client đọc count rồi `save(count + 1)`. Mỗi `$inc` là update atomic trên document.

### Chọn công cụ theo invariant

| Bài toán | Kỹ thuật thường phù hợp |
| --- | --- |
| Hai người cùng sửa toàn bộ biểu mẫu | `@Version` + expectedVersion |
| Tăng bộ đếm lượt xem | Atomic `$inc` |
| Thêm ID vào tập không trùng | Atomic `$addToSet` |
| Chuyển trạng thái NEW → APPROVED nếu vẫn NEW | Conditional update theo status + có thể theo version |
| Trừ tồn kho nếu đủ | Filter `available >= quantity` + atomic `$inc` |
| Ghi hai collections cần nhất quán toàn cục | Transaction/business workflow phù hợp |

**Version không tự sửa bất biến nghiệp vụ.** Một phép CAS có thể ngăn một stale writer nhưng vẫn cho phép một client hợp lệ đặt số lượng tồn kho thành số âm nếu không có validation/điều kiện domain.

## 22. Ví dụ giữ tồn kho không âm

Giả sử document:

```javascript
{
  _id: "SKU-A",
  available: 10,
  version: NumberLong("7")
}
```

Một request muốn giữ chỗ 3 sản phẩm. Nếu chỉ load 10 rồi `save(7)`, nhiều request đồng thời dễ xung đột. Nếu nghiệp vụ chỉ cần atomic decrement khi đủ hàng, có thể dùng:

```java
Query query = Query.query(
    Criteria.where("_id").is("SKU-A")
        .and("available").gte(3));

Update update = new Update()
    .inc("available", -3)
    .inc("version", 1L);

UpdateResult result =
    template.updateFirst(query, update, InventoryItem.class);

if (result.getMatchedCount() == 0) {
    throw new IllegalStateException(
        "Không đủ hàng hoặc SKU không tồn tại");
}
```

Ở đây **điều kiện inventory** là `available >= 3`, không phải chỉ kiểm tra version. Version vẫn được tăng để các writers dùng `@Version` biết document đã thay đổi.

### Cẩn thận: có hai chiến lược cạnh tranh

- **CAS theo version:** muốn request thất bại nếu bất kỳ writer nào đã đổi document từ lúc client đọc.
- **Conditional atomic update theo business state:** cho phép nhiều request cùng thao tác nếu invariant vẫn đúng.

Hai chiến lược có thể kết hợp, nhưng không nên áp version gate không cần thiết cho bộ đếm đang có hàng nghìn updates/giây, vì nó sẽ tạo nhiều conflicts và retry trong khi `$inc` đã giải quyết dạng lost increment.

## 23. Điều gì xảy ra khi hai người sửa những field khác nhau?

Giả sử:

```text
User A: sửa title
User B: sửa body
```

Nếu hai người đều có version 4, optimistic locking cấp document sẽ **chỉ cho một người lưu trước**. Dù hai thay đổi về mặt nội dung không đụng cùng field, version của cả document vẫn thay đổi, khiến người còn lại gặp conflict.

Đây là **xung đột bảo thủ**, không nhất thiết là một lỗi của framework. Nó ngăn việc tự merge khi chưa biết invariant nghiệp vụ.

### Những lựa chọn giải quyết

1. Trả conflict, buộc người dùng reload và áp dụng lại thay đổi.
2. Xây **field-level merge** có kiểm tra: nếu title chưa bị ai sửa thì có thể áp title của A, v.v.
3. Sử dụng PATCH atomic vào những fields độc lập, có thêm điều kiện theo domain.
4. Tách document lớn thành những aggregates độc lập nếu contention quá cao.
5. Chọn concurrency strategy khác cho dữ liệu có tần suất ghi rất lớn.

Không giả định “hai field khác nhau nên merge luôn an toàn”. Một field có thể ảnh hưởng tới validation của field khác; ví dụ đổi `status` có thể khiến `approvedBy` bắt buộc.

## 24. Phân biệt xung đột và document bị xóa

Khi CAS:

```text
WHERE _id = X AND version = 4
MatchedCount = 0
```

có thể vì:

- Document vẫn tồn tại nhưng đã chuyển sang version 5.
- Document đã bị xóa.
- ID/query mapping không đúng.
- Dữ liệu legacy không có version hoặc version type khác.

Một lệnh `findById()` sau đó có thể giúp **phân loại lỗi để trả message**, nhưng vì có concurrency, kết quả read bổ sung cũng chỉ phản ánh thời điểm của read ấy.

Ví dụ API:

- **404 Not Found** khi tài nguyên hiện không tồn tại và policy muốn công bố điều đó.
- **409 Conflict** khi tồn tại nhưng version không khớp.
- **412 Precondition Failed** khi request có If-Match và precondition thất bại.

Đừng leak thông tin tài nguyên/tenant khác khi phân loại. Security authorization vẫn cần áp dụng trước và sau những read/updates phù hợp.

## 25. Delete có liên quan @Version không?

Spring Data MongoDB có những đường xóa entity **theo phiên bản**. Với các phiên bản hỗ trợ, việc xóa một entity đã đọc cùng `@Version` có thể kiểm tra version và báo optimistic locking failure nếu document đã được thay đổi trước khi xóa.

Ví dụ:

```java
Article current = repository.findById(id)
    .orElseThrow();

repository.delete(current);
```

Thao tác xóa **theo entity** có thể được thực hiện có điều kiện version. Trong khi đó, một thao tác xóa **theo ID hoặc query** có thể không có precondition version nếu API không nhận expected version.

### Hai delete APIs không nhất thiết tương đương

```java
repository.delete(current);  // Có entity/version để kiểm tra.
repository.deleteById(id);   // Chỉ có ID; không biết bản client đã đọc.
```

Behavior chính xác của từng delete API cần đối chiếu với **Spring Data MongoDB version** đang dùng. Không tự cho rằng mọi delete theo ID sẽ bảo vệ request cũ.

### Delete từ giao diện

Nếu người dùng nhấn Xóa từ một form v4 nhưng server đã lên v5, API nên nhận expectedVersion/ETag và thực hiện conditional delete phù hợp.

Chẳng hạn, với `MongoTemplate`:

```java
Query query = Query.query(
    Criteria.where("_id").is(id)
        .and("version").is(expectedVersion));

DeleteResult result =
    template.remove(query, Article.class);

if (result.getDeletedCount() == 0) {
    throw new OptimisticLockingFailureException(
        "Không thể xóa: document không còn phiên bản cũ");
}
```

Khi biên dịch ví dụ, import `com.mongodb.client.result.DeleteResult` và các Spring Data query classes. Với hệ thống có audit, hard delete có thể không phải chính sách đúng; hãy xem soft delete.

## 26. Soft delete và thay đổi trạng thái

Một số ứng dụng dùng:

```javascript
{
  _id: "article-1001",
  version: NumberLong("8"),
  status: "ACTIVE",
  deletedAt: null
}
```

thay vì xóa hẳn. Soft delete nên là **state transition có điều kiện**:

```javascript
db.articles.updateOne(
  {
    _id: "article-1001",
    version: NumberLong("8"),
    status: "ACTIVE"
  },
  {
    $set: {
      status: "DELETED",
      deletedAt: ISODate("2026-11-14T08:00:00Z")
    },
    $inc: {
      version: NumberLong("1")
    }
  }
);
```

Lệnh này chỉ diễn giải tư duy CAS. Trong Spring Data, dùng `MongoTemplate` hoặc domain service có query, update và matched-count check tương đương.

**Không chỉ kiểm tra version mà bỏ business state**: một document version 8 nhưng status đã khóa/archived cũng không nên được xóa khi policy cấm.

## 27. @Version có thay transaction không?

Không. `@Version` bảo vệ một phần của **concurrent update trên một entity/document**. Nó không tự làm cho nhiều lệnh ghi vào nhiều collections thành một giao dịch nguyên tử.

Ví dụ tạo đơn hàng:

```text
1. Giảm inventory.available
2. Insert orders document
3. Insert payment-intent record
```

Nếu bước 1 thành công và bước 2 thất bại, dù inventory có `@Version`, hệ thống vẫn cần xử lý tính nhất quán giữa nhiều records.

Các lựa chọn:

- MongoDB **multi-document transaction** khi topology/driver/session hỗ trợ và cần atomicity.
- Application-level workflow/saga với compensating actions.
- Đổi thiết kế aggregate để invariant quan trọng nằm trong một document nếu hợp lý.
- Idempotent event processing và outbox pattern cho side effects.

### Transactions cũng có concurrency conflicts

Một transaction không loại bỏ mọi xung đột. Các transactions đồng thời có thể bị write conflict hoặc transient errors, và cần retry theo semantics của driver/Spring transaction management. `@Version` có thể bổ sung business-level stale version detection, nhưng hai cơ chế có ranh giới khác nhau.

**Không bọc toàn bộ quá trình người dùng mở form trong một transaction MongoDB dài vài phút.** Transaction database không được thiết kế để giữ cho những biểu mẫu người dùng không bị sửa trong nhiều phút.

## 28. @Transactional và @Version

Spring có annotation:

```java
import org.springframework.transaction.annotation.Transactional;
```

Đối với MongoDB, muốn dùng transactions qua Spring Data cần cấu hình transaction manager, MongoDB sessions và deployment hỗ trợ transactions (ví dụ replica set/sharded cluster theo phiên bản). Không phải cứ thêm `@Transactional` vào một method là mọi MongoDB operation tự chạy trong transaction đúng ý.

Ví dụ khái niệm:

```java
@Transactional
public void changeTwoDocuments(...) {
    // Các repository/template operations trong
    // MongoDB transaction nếu đã cấu hình đúng.
}
```

Trong transaction:

- Writes có thể cùng commit/abort theo semantics được hỗ trợ.
- Optimistic locking failure phải dẫn tới rollback/handling phù hợp.
- Retry transaction có thể gặp business side effects nếu method gọi external API ở giữa.

Vì thế không được coi `@Version` và `@Transactional` là các công tắc có thể thay thế nhau.

## 29. Retry optimistic locking: khi nào nên và không nên?

Khi `OptimisticLockingFailureException` xảy ra, một lựa chọn là retry:

```text
Read v4
  |
Save v4 -> conflict
  |
Reload v5
  |
Recompute thay đổi trên v5
  |
Save v5 -> success hoặc conflict khác
```

Nhưng **retry nguyên request cũ một cách mù quáng** có thể biến lỗi lost update đã được phát hiện thành **ghi đè có chủ đích**.

### Tác vụ thường có thể retry có kiểm soát

- Cập nhật giá trị được tính lại từ trạng thái hiện hành.
- Merge thay đổi độc lập đã được xác minh.
- Recompute một derived field không có side effect.
- State transition có điều kiện rõ.

### Tác vụ không nên tự retry để ghi đè

- Người dùng đã sửa một biểu mẫu từ bản cũ và cần thấy thay đổi của người khác.
- Thay đổi số tiền, quyền truy cập hoặc trạng thái đã phê duyệt mà không có merge policy.
- Thao tác tạo side effects ngoài MongoDB mà chưa có idempotency.
- Một lệnh update dựa trên giả định “status vẫn NEW” khi hiện tại đã APPROVED.

**Tư duy đúng:** optimistic conflict là tín hiệu **nghiệp vụ cần quyết định**, không phải lúc nào cũng là lỗi mạng để retry tự động.

## 30. Retry bounded với reload và kiểm tra invariant

Một ví dụ service cho thay đổi mà domain cho phép tính lại mỗi lần:

```java
import org.springframework.dao.OptimisticLockingFailureException;

public Article addSuffixToTitle(
        ArticleRepository repository,
        String id,
        String suffix) {

    int maxAttempts = 3;

    for (int attempt = 1; attempt <= maxAttempts; attempt++) {
        Article latest = repository.findById(id)
            .orElseThrow(() ->
                new IllegalArgumentException("Article không tồn tại"));

        // Ví dụ chỉ khi domain cho phép phép biến đổi này.
        latest.setTitle(latest.getTitle() + suffix);

        try {
            return repository.save(latest);
        } catch (OptimisticLockingFailureException ex) {
            if (attempt == maxAttempts) {
                throw ex;
            }
            // Lần sau phải reload và đánh giá lại.
        }
    }

    throw new IllegalStateException("Không đến được");
}
```

Đoạn code có chủ đích **không dùng lại object stale** sau khi catch. Nó cũng không thích hợp cho mọi domain: hai request thực hiện cùng một phép nối suffix có thể tạo chuỗi lặp nếu nghiệp vụ không bảo đảm idempotency.

Trong workload nhiều contention, cần thêm giới hạn thời gian và backoff/jitter phù hợp thay vì retry lập tức liên tục. Nếu operation chỉ là cộng một bộ đếm, **atomic `$inc` thường tốt hơn** vòng lặp optimistic retry.

## 31. Không retry side effects hai lần

Ví dụ một luồng xử lý:

```text
1. Gửi email xác nhận
2. Load entity
3. Save entity -> optimistic conflict
4. Retry method từ đầu
5. Gửi email lần thứ hai
```

Đây là lỗi thiết kế **side-effect duplication**. Tương tự với gọi cổng thanh toán, phát message Kafka hoặc kích hoạt công việc từ bên ngoài.

### Hướng thiết kế tốt hơn

- Chỉ tạo side effect **sau khi business state update thành công** theo hợp đồng.
- Với event publication, cân nhắc **transactional outbox** hoặc cơ chế đảm bảo message consistency phù hợp.
- Dùng **idempotency key** để external service nhận biết request đã xử lý.
- Không đặt network call không idempotent trong đoạn code có thể được tự động retry nguyên method.
- Lưu trạng thái hoàn tất sự kiện hoặc token nghiệp vụ để chống thực hiện lặp.

**@Version ngăn mất update trên document; nó không tự bảo đảm exactly-once delivery đối với email, payment hay events.**

## 32. Xung đột giữa nhiều service instances

Trong production, cùng một collection có thể được cập nhật bởi:

```text
Spring Boot instance A
Spring Boot instance B
Background worker C
Scheduled job D
Data migration process E
```

Không thể dùng `synchronized` trên một Java object trong instance A để bảo vệ toàn bộ hệ thống nhiều process.

Với `@Version` và MongoDB conditional update, mọi instance **dùng cùng database** có thể cùng tham gia CAS trên document, miễn các writers tuân theo contract.

### Vì sao CAS tốt hơn khóa trong memory?

`synchronized` hoặc `ReentrantLock` trong JVM chỉ bảo vệ code trên JVM ấy. Khi service scale nhiều replicas, mỗi JVM có bộ khóa riêng.

`@Version` thực hiện điều kiện tại MongoDB server, nơi có document được ghi; đây là điểm đồng bộ dùng chung.

### Nhưng tất cả writers phải tham gia

Nếu worker C dùng raw `updateOne({_id}, {$set...})` không đụng `version`, nó có thể làm cơ chế CAS của A/B mất khả năng phát hiện một thay đổi. Cần thống nhất data access policy trên toàn bộ services, không chỉ trong một repository.

## 33. @Version và MongoDB write concern

Hai khái niệm khác nhau:

**Optimistic concurrency:** kiểm tra version để tránh ghi theo state cũ.

**Durability/replication acknowledgment:** xác định khi nào một write được coi là thành công theo write concern.

Ví dụ:

```text
Update WHERE id=1 AND version=4
  |
  v
Database matched version 4
  |
  v
Write acknowledged theo write concern
  |
  v
Spring Data trả success và entity version mới
```

Khi `w:0`, client không có xác nhận đáng tin cậy để biết update match hay không; optimistic locking không có đầu vào kết quả phù hợp.

Với replica set, `w:"majority"` có thể tăng độ bền/khả năng chịu rollback so với `w:1` trong các tình huống failover, nhưng **không biến một version conflict thành success** và không thay xử lý business conflicts.

### Timeout khác conflict

- **OptimisticLockingFailureException:** CAS không match theo semantics của framework.
- **MongoSocketTimeoutException/timeout:** client có thể không biết operation đã hoàn tất hay chưa.
- **WriteConcern timeout:** acknowledgement không đạt yêu cầu trong thời gian quy định; thao tác có thể đã được áp dụng.

Không gộp cả ba thành cùng một hành vi retry. Với timeout không rõ kết quả, cần idempotency và đối soát.

## 34. Version property trong entity mới và dữ liệu legacy

Giả sử collection cũ chưa từng có field version:

```javascript
{
  _id: "article-old",
  title: "Bản ghi cũ"
}
```

Sau khi thêm:

```java
@Version
private Long version;
```

property `version` có thể được decode thành `null`. Spring Data còn dùng version property để **xác định entity mới hay đã tồn tại** trong một số code paths. Việc đem entity cũ không có version đi `save()` có thể bị coi như entity mới và dẫn đến hành vi insert/duplicate key ngoài mong đợi, thay vì tự động CAS an toàn.

### Kế hoạch migration khi bật @Version

1. Thống kê những documents đã có field version và chưa có.
2. Kiểm tra type phiên bản đang lưu (Int32/Int64/string/null).
3. Chọn convention thống nhất cho dữ liệu hiện hành.
4. Chuyển dữ liệu thiếu version theo phương thức được duyệt.
5. Chặn hoặc cập nhật những writers không dùng version.
6. Xác nhận index và repository behavior trên staging.
7. Thực hiện rollout có kiểm soát khi nhiều app versions cùng chạy.
8. Theo dõi số lượng optimistic locking failures.

### Ví dụ backfill chỉ trong staging

```javascript
db.articles.updateMany(
  { version: { $exists: false } },
  { $set: { version: NumberLong("0") } }
);
```

Đây chỉ là ví dụ kỹ thuật **gán version ban đầu** khi migration có policy phù hợp. Không chạy trực tiếp trên production đang có writers cũ/mới mà chưa có kế hoạch đóng băng/điều phối và xác nhận cách Spring Data version đã dùng trong collection.

### Vì sao cập nhật từng document legacy phải cẩn thận?

Khi backfill đồng thời với writers cũ không quản lý version, một số updates có thể lọt qua mà không tăng version, khiến lần save sau không phát hiện thay đổi. Tốt nhất nên quản lý **migration cutover**, không chỉ đặt field một lần rồi mặc định mọi thứ đã an toàn.

## 35. Primitive long hay wrapper Long?

```java
@Version
private long version;   // primitive, mặc định 0
```

so với:

```java
@Version
private Long version;   // wrapper, có thể null
```

Khác biệt:

- Primitive không thể biểu diễn `null`; giá trị mặc định là 0.
- Wrapper có thể phân biệt entity chưa có version với entity đã được gán 0.
- Spring Data có **quy ước phát hiện entity mới/khởi tạo version** khác nhau theo primitive/wrapper.
- Cần chú ý JSON serialization của `Long` và client-side validation.

Với ứng dụng mới, `Long` nullable là lựa chọn dễ diễn đạt lifecycle entity; tuy nhiên vẫn phải kiểm tra behavior của driver/framework version thực. Không đổi `long` thành `Long` giữa production deployment mà bỏ qua document formats/DTO tests.

### Version không phải business revision string

Nếu ứng dụng muốn phiên bản hiển thị kiểu `v1.2.0` hoặc `draft-2026-11`, đó có thể là field **businessRevision** riêng. `@Version` thường dùng một property số có thể tăng để làm CAS token. Không trộn business revision với concurrency counter nếu lifecycle của chúng khác nhau.

## 36. Tránh tự tăng version khi repository đã quản lý

Một anti-pattern:

```java
Article current = repository.findById(id).orElseThrow();
current.setTitle(newTitle);
current.setVersion(current.getVersion() + 1);
repository.save(current);
```

Khi `save()` dùng current version làm expected version, hành vi có thể bị sai: Spring Data tìm document theo version đã bị tăng trước đó, dẫn tới failure hoặc lệch contract.

**Cách đúng khi dùng repository entity save:** thay đổi fields nghiệp vụ, để Spring Data quản lý version.

Ngược lại, **khi tự viết raw CAS update**, bạn phải chủ động tăng version cùng lệnh ghi, vì MongoDB server không biết annotation Java. Sự khác biệt nằm ở **đường ghi nào quản lý version**.

## 37. Có nên index field version?

Trong phép update điển hình:

```javascript
{ _id: "article-1001", version: NumberLong("4") }
```

MongoDB có thể tìm document theo unique index `_id` rồi kiểm tra version. Vì thế **không cần một index chỉ trên version** cho trường hợp CAS phổ biến.

Index:

```javascript
db.articles.createIndex({ version: 1 });
```

không tự làm optimistic locking chính xác hơn. Nó có chi phí lưu trữ và update vì version thay đổi qua mỗi write. Chỉ tạo index nếu có một query workload thực sự cần truy vấn/sắp xếp theo version, và đã xem `explain`/index design.

### Unique index không thay version

Unique index trên `_id` chỉ ngăn hai documents trùng ID, không ngăn hai requests tuần tự cùng sửa **cùng một document**. Optimistic locking dùng version predicate để giải quyết lost update, không phải uniqueness của ID.

## 38. @Version và domain invariants

Giả sử một đơn hàng:

```javascript
{
  _id: "ORD-1001",
  version: NumberLong("3"),
  status: "PAID",
  amount: NumberDecimal("125000.00")
}
```

Một request với đúng version 3 muốn chuyển status trực tiếp từ PAID sang NEW. CAS có thể match version, nhưng **trạng thái nghiệp vụ vẫn sai** nếu domain cấm chuyển ngược.

Service phải kiểm tra:

```text
expectedVersion == currentVersion
AND
status transition được business policy cho phép
AND
user có quyền thao tác
AND
other invariants được đáp ứng
```

Với state transition atomic, query nên thể hiện invariant:

```javascript
db.orders.updateOne(
  {
    _id: "ORD-1001",
    version: NumberLong("3"),
    status: "PAID"
  },
  {
    $set: { status: "SHIPPED" },
    $inc: { version: NumberLong("1") }
  }
);
```

Như vậy version và business state cùng được kiểm tra **trong một atomic update**. Validation/schema/authorization vẫn cần ở các lớp tương ứng.

## 39. Tách document khi write contention quá cao

Một document lớn có nhiều fields thay đổi độc lập:

```javascript
{
  _id: "user-1001",
  version: NumberLong("100"),
  profile: {...},
  preferences: {...},
  lastSeenAt: ISODate("..."),
  counters: {...}
}
```

Nếu mọi thay đổi `lastSeenAt` hoặc counter đều tăng version, người dùng đang chỉnh profile có thể gặp conflict liên tục.

Các hướng giải quyết:

1. Dùng atomic operators và chỉ kiểm soát đúng invariant.
2. Tách high-frequency telemetry/counters khỏi aggregate/profile document.
3. Giảm số fields trong một entity được full-save.
4. Định nghĩa rõ những updates nào phải tham gia cùng concurrency token.
5. Nếu chia document, đánh giá thêm transaction consistency cho các invariants xuyên document.

**Không loại bỏ version increment chỉ để giảm lỗi** nếu những writers còn lại cần biết document đã bị thay đổi. Cần xem lại boundary của aggregate và concurrency policy, không tạo lỗ hổng lost update mới.

## 40. Tích hợp với Spring Data auditing

Spring Data có các annotation:

```java
import org.springframework.data.annotation.CreatedDate;
import org.springframework.data.annotation.LastModifiedDate;
```

Ví dụ:

```java
@CreatedDate
private Instant createdAt;

@LastModifiedDate
private Instant updatedAt;

@Version
private Long version;
```

**Auditing timestamp và version là hai cơ chế khác nhau**:

- `updatedAt` cho biết thời điểm cập nhật theo policy của ứng dụng/auditing callback.
- `version` là concurrency token.
- Timestamp có độ phân giải/clock semantics riêng và không nên thay version một cách mặc định.

Nếu auditing được bật và mapping/codec hỗ trợ, callbacks có thể cập nhật timestamp tự động. Nhưng cũng giống @Version, **raw MongoDB writers không tự tuân theo auditing callbacks của Spring Data**.

### Có nên dùng updatedAt làm CAS token?

Có thể xây conditional update theo timestamp trong một số schema, nhưng dễ gặp giới hạn precision, sự khác biệt client clocks và các writes trùng milliseconds. Numeric version do server/application layer tăng có kiểm soát thường dễ kiểm chứng hơn cho optimistic concurrency.

## 41. Kiểm thử optimistic locking với hai bản sao

Một integration test rõ nghĩa nên:

1. Tạo entity mới trong **database thử nghiệm**.
2. Đọc thành hai **object instances khác nhau**.
3. Save bản A.
4. Cố save bản B với version cũ.
5. Xác nhận exception xảy ra.
6. Đọc database cuối cùng và kiểm tra bản A không bị ghi đè.

Ví dụ với JUnit 5 và Spring Data repository được inject:

```java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.dao.OptimisticLockingFailureException;

import static org.junit.jupiter.api.Assertions.*;

class ArticleOptimisticLockTest {

    @Autowired
    ArticleRepository repository;

    @Test
    void staleCopyMustNotOverwriteNewerVersion() {
        String id = "test-article-optimistic-lock";

        repository.save(
            new Article(id, "Ban đầu", "Body cũ")
        );

        Article copyA = repository.findById(id)
            .orElseThrow();
        Article copyB = repository.findById(id)
            .orElseThrow();

        copyA.setTitle("Tiêu đề A");
        Article savedA = repository.save(copyA);

        copyB.setBody("Body B");

        assertThrows(
            OptimisticLockingFailureException.class,
            () -> repository.save(copyB)
        );

        Article actual = repository.findById(id)
            .orElseThrow();

        assertEquals("Tiêu đề A", actual.getTitle());
        assertEquals("Body cũ", actual.getBody());
        assertEquals(savedA.getVersion(), actual.getVersion());
    }
}
```

Đây là **hạt nhân ví dụ**, chưa phải toàn bộ test setup: cần `@DataMongoTest`/Spring context phù hợp, database cô lập, cleanup test data và MongoDB instance thật. ID cố định trong ví dụ chỉ phù hợp với test đã dọn dữ liệu; không dùng ID trùng trong một môi trường chia sẻ.

### Vì sao test tuần tự vẫn chứng minh optimistic locking?

Vì cả hai object A và B đã được **đọc trước khi A ghi**. B giữ stale version sau khi A save. Điều đó đủ kiểm tra cơ chế CAS ngay cả khi không có hai threads chạy đồng thời.

## 42. Kiểm thử concurrency thật với nhiều threads

Đối với service quan trọng, nên có integration test nhiều writers:

```text
Thread A: đọc v0 ------\
                       +--> Barrier: cả hai đã đọc v0
Thread B: đọc v0 ------/
                       |
                       +--> cùng thử save
                       |
                  một write thắng
                  một write conflict
```

Có thể dùng `CountDownLatch` hoặc `CyclicBarrier` để điều phối test, nhưng phải:

- Đảm bảo mỗi thread lấy **entity instance riêng**.
- Không dùng một mutable object chung rồi gây Java data race.
- Dùng database/test collection cô lập.
- Chờ threads hoàn tất và assert tất cả exceptions đúng loại.
- Không phụ thuộc thứ tự A/B thắng; chỉ assert invariant **một save thắng từ cùng version**.
- Đảm bảo write concern acknowledged và môi trường MongoDB đang hoạt động.

Trong một load test thực tế, còn cần đo **tỷ lệ conflict**, p95/p99 latency, số retries, số operations cuối cùng được áp dụng và nghiệp vụ còn đúng.

## 43. Kiểm thử conflict ở API/HTTP

Một integration test end-to-end:

```text
1. POST /articles
   -> article id = X, version = 0

2. GET /articles/X
   -> snapshot v0 cho User A

3. GET /articles/X
   -> snapshot v0 cho User B

4. PUT /articles/X, expectedVersion=0, title="A"
   -> 200 OK, version=1

5. PUT /articles/X, expectedVersion=0, body="B"
   -> 409 Conflict hoặc 412 theo API contract

6. GET /articles/X
   -> title="A", body chưa bị B ghi đè
```

Nếu service chỉ load bản mới từ repository rồi save mà không so expectedVersion từ request, bước 5 có thể **thành công sai**. Đây là lý do test nên bao gồm **API layer**, không chỉ test `Repository.save()`.

### Kiểm tra authorization

Một user không có quyền sửa article không được bypass kiểm tra permission chỉ vì họ biết expectedVersion chính xác. Version không phải token xác thực. ObjectId, version và ETag có thể nhìn thấy bởi client hợp lệ nhưng không thay AuthN/AuthZ.

## 44. Theo dõi optimistic locking trong production

Các metrics hữu ích:

| Metric/signal | Ý nghĩa |
| --- | --- |
| Optimistic conflicts per endpoint | Tần suất request bị từ chối do stale version |
| Conflicts per entity type | Loại document có contention cao |
| Retry attempts/success | Đánh giá retry có hiệu quả không |
| Conflict-to-success ratio | Cân nhắc UX/workload strategy |
| Time between GET and save | Biểu mẫu mở lâu dễ stale |
| HTTP 409/412 rate | Trải nghiệm client và API behavior |
| Database write latency | Có thể ảnh hưởng thời gian race window |
| Version jump rate | Một entity bị sửa với tần suất cao |
| Raw writer version drift | Có writer bỏ qua version contract |
| Side-effect duplicates | Retry gây email/event/payment lặp |

### Conflict tăng có phải luôn là sự cố?

Không nhất thiết. Optimistic locking **đang bảo vệ dữ liệu** khi nó báo conflict. Tuy nhiên tỷ lệ tăng đột biến có thể chỉ ra:

- Màn hình cho phép người dùng giữ form rất lâu.
- Một job cập nhật cùng document quá thường xuyên.
- Nhiều service update toàn entity thay vì partial fields.
- Một chiến lược retry quá hung hăng.
- Dữ liệu bị chia aggregate chưa hợp lý.

Không giảm số errors bằng cách **bỏ version filter**. Hãy giải quyết nguyên nhân contention hoặc cải thiện luồng làm việc.

## 45. Runbook xử lý conflict

Khi log hoặc API xuất hiện `OptimisticLockingFailureException`:

### Bước 1 — Xác định operation

- Entity type, document ID (được mask khi cần).
- Endpoint/worker đang ghi.
- Expected version và version thực tế theo read phù hợp.
- Operation là full save, partial update, delete hay raw driver write.

### Bước 2 — Kiểm tra đường ghi

- Entity có `@Version` Spring Data đúng không?
- Repository/template operation có hỗ trợ kiểm tra version không?
- Có writer nào update trực tiếp mà không tăng version không?
- Write concern có acknowledgment không?
- Client có truyền expectedVersion hay service chỉ reload phiên bản mới?

### Bước 3 — Phân loại xung đột

1. **User edit stale:** trả 409/412, cho reload/compare/merge.
2. **Idempotent background transform:** có thể reload, recompute và retry bounded.
3. **Business state changed:** dừng, yêu cầu tái đánh giá workflow.
4. **Document deleted:** xử lý Not Found theo API policy.
5. **Legacy missing version:** thực hiện migration/compatibility plan.
6. **Non-version-aware writer:** sửa code path hoặc dùng CAS trực tiếp.

### Bước 4 — Bảo vệ side effects

- Kiểm tra request idempotency.
- Không phát message hay gọi payment lại nếu kết quả trước chưa rõ.
- Xác nhận downstream activity, audit và outbox state.

### Bước 5 — Theo dõi và cải thiện

- Bổ sung tests stale-form và two-copies.
- Đo conflict frequency/contention.
- Xem có nên dùng atomic operators/tách aggregate.
- Bổ sung UX compare-and-resolve khi sửa thủ công.

## 46. Những nhầm lẫn thường gặp

| Nhận định sai | Vì sao sai? | Cách hiểu đúng |
| --- | --- | --- |
| “MongoDB single-document atomic nên không thể lost update” | Atomic write không bảo vệ read–modify–write dùng snapshot cũ | Cần CAS/version hoặc atomic operator |
| “@Version tạo database lock dài hạn” | Cơ chế là optimistic version predicate | Không khóa biểu mẫu người dùng |
| “Chỉ cần @Version, API không phải gửi version” | Service reload mới rồi save vẫn có thể ghi đè form cũ | Client gửi expectedVersion/ETag |
| “Check version bằng findById là đủ” | Có race giữa read và write | Phải CAS trong update operation |
| “@Version ngăn mọi raw MongoDB update” | MongoDB không đọc annotation Java | Mọi writer cần tuân thủ version contract |
| “Tự `setVersion(v+1)` rồi save” | Framework cần version cũ để match | Để repository quản lý |
| “MongoTemplate.updateFirst mặc nhiên có CAS” | Có thể tự tăng version nhưng query không chứa expectedVersion | Tự thêm predicate version |
| “Nếu có lỗi conflict cứ retry form cũ” | Có thể ghi đè nội dung người khác | Reload và áp dụng merge policy |
| “409 nghĩa là server down” | Xung đột dữ liệu là một kết quả nghiệp vụ | Client xử lý reload/merge |
| “@Version bảo đảm exactly-once email” | External side effects ở ngoài write | Idempotency/outbox |
| “@Version thay multi-document transaction” | Nó bảo vệ một entity | Transaction/workflow riêng |
| “Transaction làm @Version vô ích” | Hai cơ chế có mục đích khác | Có thể bổ sung cho nhau |
| “Mọi deleteById đều check version từ form” | API chỉ có ID có thể thiếu expectedVersion | Delete có điều kiện |
| “Version phải được index riêng” | CAS tìm theo unique _id và kiểm tra version | Chỉ index nếu workload cần |
| “Version giống updatedAt” | Timestamp không phải concurrency counter tương đương | Tách auditing và CAS |
| “Có version đúng thì mọi business transition hợp lệ” | Domain invariant độc lập | Kiểm tra status, quyền và điều kiện khác |
| “Dữ liệu cũ thiếu version sẽ tự an toàn” | Có thể bị xem như new entity/insert | Migration version có kiểm soát |
| “Mọi update tăng version giống nhau” | Tùy operation/framework version | Xem code path và tests |
| “Conflict luôn là lỗi cần triệt tiêu” | Nó ngăn mất dữ liệu âm thầm | Đo và giảm contention đúng cách |
| “@Version dùng làm quyền sửa dữ liệu” | Không phải security token | AuthN/AuthZ riêng |

## 47. Bài tập và đáp án

### Bài 1. Lost update

Hai service đều đọc entity version 3. Service A save thành công, service B giữ bản cũ rồi save. Với `@Version` và acknowledged write concern, điều gì xảy ra?

**Đáp án:** A cập nhật và tăng version. B không còn match version 3 nên gặp optimistic locking failure; thay đổi của A không bị B ghi đè âm thầm.

### Bài 2. Import annotation

Entity của Spring Data MongoDB nên dùng annotation nào?

**Đáp án:** `org.springframework.data.annotation.Version`, không phải mặc định dùng annotation JPA.

### Bài 3. Vì sao version chỉ đọc không đủ?

Developer đọc version 4, thấy khớp, rồi cập nhật chỉ theo `_id`. Vẫn có race không?

**Đáp án:** Có. Request khác có thể sửa giữa read và write. Version predicate phải nằm trong cùng atomic update.

### Bài 4. @Version và client form

User A mở form v4, user B lưu thành v5. Khi A nhấn Lưu, service lại `findById()` để đọc v5 và save dữ liệu form của A. Có chắc phát hiện stale form không?

**Đáp án:** Không. Service đã dùng v5 làm expectedVersion. Client phải truyền version v4 của bản đã sửa và server phải kiểm tra/CAS.

### Bài 5. HTTP status

API phát hiện expectedVersion đã cũ. Status code nào phổ biến?

**Đáp án:** 409 Conflict khi đó là domain conflict; 412 Precondition Failed khi dùng HTTP If-Match và precondition thất bại. Chọn contract nhất quán.

### Bài 6. Repository.save()

Khi dùng `repository.save(entity)` với `@Version`, có nên tự tăng property version trước không?

**Đáp án:** Không. Spring Data quản lý version trong save path; tự tăng có thể làm query tìm sai version.

### Bài 7. MongoTemplate.updateFirst()

Filter chỉ có `_id` nhưng Update tăng version. Có thành CAS chống stale write không?

**Đáp án:** Không. Version chỉ tăng chưa đủ; query phải so expectedVersion nếu yêu cầu optimistic check.

### Bài 8. Matched count

CAS update trả `matchedCount=0`. Có đủ khẳng định document đã bị xóa không?

**Đáp án:** Không. Có thể document vẫn tồn tại nhưng version khác. Cần read bổ sung và chính sách phân loại lỗi.

### Bài 9. findAndModify

Muốn CAS và nhận document sau khi cập nhật, nên dùng tùy chọn nào?

**Đáp án:** `FindAndModifyOptions.options().returnNew(true)` cùng query ID+version và update có increment version. Xử lý null khi không match.

### Bài 10. Upsert

Trong CAS sửa một document bắt buộc đã tồn tại, có nên bật `upsert(true)`?

**Đáp án:** Thường không. Có thể dẫn tới tạo document mới ngoài ý định khi query version không match.

### Bài 11. Raw driver

Một background job dùng `updateOne({_id: X}, {$set: {title: ...}})` và không tăng version. Có ảnh hưởng Spring Data @Version không?

**Đáp án:** Có. Spring Data có thể không biết document đã đổi và cho phép stale save sau đó. Mọi writer cần tuân thủ concurrency contract.

### Bài 12. Counter

1.000 users đồng thời tăng lượt xem. Dùng `save(count+1)` với @Version và retry hay dùng `$inc`?

**Đáp án:** Atomic `$inc` thường thích hợp hơn cho counter, tránh lost increment và nhiều conflicts không cần thiết.

### Bài 13. Trừ tồn kho

Muốn trừ 3 sản phẩm nếu tồn kho còn ít nhất 3. Chỉ check version có đủ không?

**Đáp án:** Không. Cần điều kiện nghiệp vụ `available >= 3` trong atomic update; có thể thêm version nếu policy yêu cầu.

### Bài 14. Hai field khác nhau

User A sửa title, user B sửa body từ cùng version. Tại sao một người vẫn gặp conflict?

**Đáp án:** Version áp cho toàn document. Cơ chế không tự biết hai edits độc lập; merge cần policy riêng.

### Bài 15. Retry

Một service bắt conflict rồi ngay lập tức gọi `save(staleEntity)` lại nhiều lần. Cách này đúng không?

**Đáp án:** Không. Cần reload version mới và recompute/merge theo domain; retry bounded chỉ khi an toàn.

### Bài 16. External payment

Code gọi cổng thanh toán, sau đó save entity nhưng gặp version conflict. Tự retry cả method có nguy cơ gì?

**Đáp án:** Gọi thanh toán nhiều lần. Cần idempotency key, quản lý side effects/outbox và quy trình xử lý kết quả không rõ.

### Bài 17. Transaction

@Version trên `Order` có tự bảo đảm update `Inventory` và insert `Payment` cùng thành công/rollback không?

**Đáp án:** Không. Cần transaction/workflow theo invariant và topology phù hợp.

### Bài 18. Delete

API xóa chỉ nhận ID trong khi form được mở ở version cũ. Có thể dùng riêng `deleteById(id)` để biết form stale không?

**Đáp án:** Không chắc. Cần expectedVersion/ETag và conditional delete tương ứng.

### Bài 19. Primitive version

Điểm khác nhau giữa `long version` và `Long version`?

**Đáp án:** Primitive không thể null và default 0; wrapper có thể null. Spring Data có quy tắc khởi tạo/detect new entity khác nhau.

### Bài 20. Dữ liệu cũ

Document được tạo trước khi thêm `@Version` không có field version. Có thể triển khai code mới mà mặc định mọi save an toàn không?

**Đáp án:** Không. Cần migration và kiểm thử entity state detection/insert-vs-update, cùng kiểm soát các writers cũ.

### Bài 21. Unique index

Collection có unique `_id`. Điều đó đã ngăn lost update chưa?

**Đáp án:** Chưa. Unique index bảo vệ sự duy nhất của ID, không buộc writer kiểm tra document có đổi từ lúc đọc hay không.

### Bài 22. Version index

Có nhất thiết tạo index `{version: 1}` để repository CAS chạy đúng?

**Đáp án:** Không. Query CAS thường dùng unique `_id` và thêm condition version; index riêng trên version không bắt buộc.

### Bài 23. Auditing

`updatedAt` và `version` có tương đương không?

**Đáp án:** Không. Timestamp phục vụ audit/thời điểm; numeric version phục vụ CAS. Precision/clock khác nhau.

### Bài 24. Multi-instance

Hai Spring Boot instances khác JVM cùng save một entity version 6. `synchronized` ở mỗi instance có đủ không?

**Đáp án:** Không. JVM locks không phối hợp giữa instances; MongoDB CAS theo version mới có điểm kiểm tra chung.

### Bài 25. Write concern

Vì sao không dùng `w:0` với optimistic locking?

**Đáp án:** Không có acknowledged write result đáng tin cậy để biết condition version đã match hay không.

### Bài 26. Conflict không phải mất dữ liệu

Một endpoint tăng số 409 sau khi bổ sung @Version. Có nên bỏ version predicate để giảm errors?

**Đáp án:** Không. Conflicts có thể đang ngăn lost updates. Phải phân tích contention, UX, partial updates/retries theo chính sách.

### Bài 27. Status transition

Đơn hàng version 4 hiện status PAID. Request muốn chuyển sang SHIPPED. Điều kiện version 4 đã đủ chưa?

**Đáp án:** Không chắc. Cần kiểm tra status PAID và các business invariants liên quan ngay trong atomic predicate/logic.

### Bài 28. ETag

Server trả `ETag: "v4"`, client gửi `If-Match: "v4"` nhưng resource đã lên v5. Status nào phù hợp với HTTP precondition?

**Đáp án:** 412 Precondition Failed khi áp dụng semantics If-Match.

### Bài 29. Test đúng

Integration test tạo hai object copies cùng v0, save A và B. Invariant quan trọng là gì?

**Đáp án:** Chỉ một update từ cùng stale version được chấp nhận; lần lưu còn lại bị từ chối và dữ liệu người thắng không bị ghi đè.

### Bài 30. Business approval

Hai request đều có expectedVersion phù hợp tại thời điểm riêng. Một request muốn chuyển trạng thái APPROVED → DRAFT, nhưng workflow cấm. @Version có chặn vì workflow không?

**Đáp án:** Không. Version chỉ bảo vệ concurrency token, không tự thực thi state machine/authorization. Cần business validation riêng.

## 48. Checklist áp dụng @Version trong dự án

### Mapping và persistence

- [ ] Dùng đúng `org.springframework.data.annotation.Version` trên entity MongoDB.
- [ ] Chọn kiểu numeric version phù hợp, thường `Long` nullable.
- [ ] Để Spring Data quản lý version khi save entity.
- [ ] Xác nhận behavior insert/version initialization bằng integration test.
- [ ] Dữ liệu legacy thiếu version đã có migration plan.
- [ ] Mọi writers/migrations cùng tuân thủ version contract.
- [ ] Dùng acknowledged write concern để phát hiện CAS failure.

### API và UI

- [ ] GET response cung cấp version/ETag cho client nếu cần stale-form detection.
- [ ] Update request mang expectedVersion hoặc If-Match.
- [ ] API không bind raw client fields tùy ý vào entity.
- [ ] Có CAS tại database, không chỉ check version trước.
- [ ] Trả 409/412 phù hợp, message cho reload/merge.
- [ ] UI hỗ trợ giữ input đang sửa và hiển thị bản mới khi conflict.
- [ ] Không leak dữ liệu của người khác trong conflict response.

### Updates và nghiệp vụ

- [ ] Phân biệt full save và partial update.
- [ ] Với updateFirst/findAndModify, query có predicate version khi cần CAS.
- [ ] Với raw driver, tăng version trong cùng atomic update.
- [ ] Không dùng upsert ngoài ý định.
- [ ] Dùng atomic `$inc`/`$addToSet` khi phù hợp thay vì CAS toàn document.
- [ ] Kiểm tra business invariants/status/authorization song song với version.
- [ ] Delete/soft delete có expectedVersion nếu client cần bảo vệ stale state.
- [ ] Không coi @Version là multi-document transaction.

### Retry, testing và vận hành

- [ ] Retry bounded, reload và recompute, không ghi lại stale entity mù quáng.
- [ ] External side effects có idempotency/outbox hoặc cơ chế phù hợp.
- [ ] Test hai copies cùng version và API stale-form case.
- [ ] Test concurrent requests giữa nhiều service instances khi cần.
- [ ] Monitor optimistic conflict rate, retry count và user impact.
- [ ] Đối chiếu performance/contention trước khi thay aggregate boundaries.
- [ ] Có runbook phân biệt conflict, deletion, timeout và write concern error.

## 49. Tổng kết

**`@Version` trong Spring Data MongoDB** là một công cụ **optimistic locking** nhằm tránh tình huống một entity đã đọc từ trước bị ghi đè lên phiên bản mới hơn. Trên đường `Repository.save()` hoặc `MongoTemplate.save()` được hỗ trợ, Spring Data sử dụng version hiện tại làm một phần của điều kiện ghi, tăng version khi cập nhật thành công và báo **`OptimisticLockingFailureException`** nếu điều kiện không còn khớp.

Nhưng annotation **không giải quyết mọi dạng concurrency**. Nếu service luôn đọc bản mới ngay trước save, nó có thể ghi đè một **form HTTP đã cũ** trừ khi client gửi **expectedVersion/ETag**. Nếu một background job dùng raw driver và không tăng version, các writers qua Spring Data có thể không nhận biết thay đổi. Nếu cần cập nhật một field hoặc thực thi invariant, một **conditional atomic update** với ID, version và điều kiện nghiệp vụ có thể phù hợp hơn full-document save.

Khi có conflict, không nên mặc định retry nguyên dữ liệu cũ. Hãy **reload, so sánh, áp dụng merge policy hoặc trả 409/412** cho client. Chỉ retry có giới hạn khi operation có thể được tính lại an toàn; external side effects phải có idempotency. Với các thao tác nhiều documents, còn phải thiết kế transaction/workflow riêng.

Tư duy cần nhớ là **“đọc phiên bản nào thì chỉ được ghi nếu phiên bản ấy còn hiện hành”**. Việc kiểm tra phải nằm trong **cùng atomic database update**, và mọi code path có thể sửa document cần tuân theo cùng quy tắc. Khi áp dụng nhất quán, optimistic locking giúp ứng dụng phát hiện xung đột rõ ràng thay vì âm thầm làm mất dữ liệu của người dùng.

### Tài liệu tham khảo chính thức

- [Spring Data MongoDB Reference — Optimistic Locking](https://docs.spring.io/spring-data/mongodb/reference/mongodb/template-crud-operations.html#mongo-template.optimistic-locking)
- [Spring Data MongoDB Reference — Saving, Updating, and Removing Documents](https://docs.spring.io/spring-data/mongodb/reference/mongodb/template-crud-operations.html)
- [Spring Data MongoDB Reference — Object Mapping](https://docs.spring.io/spring-data/mongodb/reference/mongodb/mapping/mapping.html)
- [Spring Data MongoDB — MongoRepository API](https://docs.spring.io/spring-data/mongodb/reference/mongodb/repositories/repositories.html)
- [MongoDB Manual — Atomicity and Transactions](https://www.mongodb.com/docs/manual/core/write-operations-atomicity/)
- [MongoDB Manual — updateOne](https://www.mongodb.com/docs/manual/reference/method/db.collection.updateOne/)
- [MongoDB Manual — Write Concern](https://www.mongodb.com/docs/manual/reference/write-concern/)
- [HTTP Semantics — If-Match and Precondition Failed](https://www.rfc-editor.org/rfc/rfc9110.html)
