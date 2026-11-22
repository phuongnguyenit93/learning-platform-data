# Thiết kế hợp đồng xử lý không tồn tại và xung đột phiên bản trong Repository JPA

Trong ứng dụng dùng **Java Persistence API (JPA)** và **Spring Data JPA**, Repository thường cung cấp các thao tác tìm, lưu và xóa thực thể. Tuy nhiên, chữ ký phương thức như `findById()` hay `save()` chưa đủ để nói rõ điều gì xảy ra khi bản ghi không còn tồn tại hoặc khi hai người dùng đồng thời sửa cùng một dữ liệu. Nếu những trường hợp này không có hợp đồng rõ ràng, tầng dịch vụ dễ trả sai lỗi, ghi đè thay đổi của người khác hoặc tạo ra hành vi khó đoán giữa các endpoint.

Bài học này xây dựng hợp đồng xuyên suốt **Repository → Service → API**, tập trung vào hai tình huống:

1. **Không tồn tại (not found):** tài nguyên có mã định danh được yêu cầu không có trong trạng thái dữ liệu đang quan sát.
2. **Xung đột phiên bản (version conflict):** tài nguyên tồn tại hoặc vừa tồn tại, nhưng lệnh ghi dựa trên một phiên bản cũ nên không còn an toàn để áp dụng.

Đây là hai tình huống có nguyên nhân, cách phản hồi và hướng xử lý khác nhau. Một thiết kế tốt cần thể hiện sự khác biệt ấy ngay trong hợp đồng, đồng thời bảo vệ dữ liệu khỏi điều kiện tranh chấp (*race condition*).

## 1. Hợp đồng cần định nghĩa những gì?

Trước khi viết code, hãy thống nhất năm câu hỏi:

- **Đơn vị dữ liệu nào được quản lý?** Ví dụ: một `Article` có `id`, `title` và `version`.
- **Không tìm thấy có phải lỗi không?** Tìm một bài viết bắt buộc phải tồn tại khác với tìm kiếm danh sách có thể rỗng.
- **Lệnh ghi dựa vào phiên bản nào?** Phiên bản mà người dùng đã đọc trước đó, hay phiên bản được đọc lại ngay lúc thực thi?
- **Ai chịu trách nhiệm phát hiện xung đột?** Service kiểm tra phiên bản do client gửi; JPA/DB kiểm tra thay đổi xảy ra đồng thời.
- **Người gọi có thể làm gì khi thất bại?** Sửa lại ID, tải bản mới để hòa giải nội dung, hay thử lại một thao tác an toàn?

Ví dụ về hợp đồng thường gặp:

| Thao tác | Tình huống | Hành vi đề xuất |
|---|---|---|
| `findById(id)` | Không có bản ghi | Trả `Optional.empty()`; việc coi là lỗi thuộc Service |
| `GET /articles/{id}` | ID không tồn tại | HTTP `404 Not Found` |
| `GET /articles?keyword=...` | Không có kết quả | `200 OK` với danh sách rỗng `[]` |
| Cập nhật một ID | ID không tồn tại lúc đọc | `404 Not Found` |
| Cập nhật một ID | Phiên bản client gửi đã cũ | `409 Conflict`; nếu dùng HTTP `If-Match`, thường là `412 Precondition Failed` |
| Cập nhật một ID | Phiên bản thay đổi sau khi Service đã đọc | Từ chối commit/flush bằng optimistic locking; ánh xạ lỗi xung đột |
| Xóa một ID | ID không tồn tại | Chọn nhất quán `404` hoặc `204` theo hợp đồng xóa |
| Tạo mới với khóa nghiệp vụ bị trùng | Vi phạm ràng buộc duy nhất | Xung đột nghiệp vụ, thường là `409`; **không** đánh đồng với xung đột `@Version` |

Các mã HTTP trong bảng là **chính sách ở biên API**. Repository nên biểu diễn đúng trạng thái dữ liệu, không cần biết HTTP.

## 2. Thiết kế ngữ nghĩa “không tồn tại”

### 2.1. Repository trả `Optional` cho truy vấn một thực thể

Với Spring Data JPA, cách diễn đạt rõ nhất cho “có thể không có dữ liệu” là:

```java
public interface ArticleRepository extends JpaRepository<Article, Long> {
    // JpaRepository đã có Optional<Article> findById(Long id).
}
```

Tầng Service quyết định có chuyển `Optional.empty()` thành lỗi nghiệp vụ hay không:

```java
Article article = repository.findById(id)
    .orElseThrow(() -> new ArticleNotFoundException(id));
```

Không nên trả về `null` rồi để mọi caller tự đoán ý nghĩa. Cũng không nên dùng `getReferenceById(id)` để xác nhận tồn tại: phương thức này có thể trả **proxy** chưa truy vấn database; lỗi chỉ xuất hiện khi truy cập proxy, tùy provider và thời điểm tải.

Phân biệt rõ hai kiểu sử dụng:

- **Truy vấn có thể thiếu:** `Optional<Article> findById(id)` là hợp đồng phù hợp.
- **Lệnh cần thực thể tồn tại:** Service gọi `orElseThrow(...)`, tạo lỗi có ý nghĩa ở miền nghiệp vụ.

Một câu truy vấn tìm kiếm trả danh sách rỗng không có nghĩa là “tài nguyên không tồn tại”; do đó không cần tự động biến mọi kết quả rỗng thành `404`.

### 2.2. Chọn chính sách xóa trước khi triển khai

Hai hợp đồng xóa đều có thể hợp lệ:

**Xóa nghiêm ngặt:** `DELETE /articles/42` trả `404` nếu không có Article 42 tại thời điểm kiểm tra. Dùng khi caller cần được báo rằng mã đích sai hoặc đã mất.

**Xóa bảo đảm trạng thái cuối:** trả `204 No Content` ngay cả khi ID đã vắng mặt. Dùng khi mục tiêu là “sau yêu cầu, tài nguyên không còn tồn tại”. Cách này thuận tiện cho retry.

HTTP `DELETE` được xem là *idempotent* theo hiệu quả mong muốn lên trạng thái server; các lần gọi liên tiếp không bắt buộc phải trả cùng mã trạng thái. Vì vậy hợp đồng nghiêm ngặt có thể trả `204` lần đầu và `404` lần sau mà vẫn giữ tính idempotent về hiệu quả.

Không nên suy ra trực tiếp ngữ nghĩa API từ `repository.deleteById(id)`. Hành vi với ID không tồn tại có thể khác theo phiên bản Spring Data hoặc cách triển khai; nếu cần hợp đồng xác định, hãy kiểm tra tồn tại và xử lý trong Service. Tuy nhiên, **kiểm tra rồi xóa vẫn không loại bỏ race condition**: một transaction khác có thể thay đổi hoặc xóa bản ghi giữa hai bước.

## 3. Vì sao cần phân biệt xung đột phiên bản?

Giả sử hai người dùng cùng mở bài viết `id=42` tại `version=7`:

| Thời điểm | Người dùng A | Người dùng B |
|---|---|---|
| T1 | Đọc tiêu đề “Bản nháp”, version 7 | Đọc cùng tiêu đề, version 7 |
| T2 | Đổi thành “Bản đã duyệt” | Vẫn đang sửa bản cũ |
| T3 | Lưu thành công; version lên 8 | Gửi tiêu đề “Bản sửa của B” với expectedVersion=7 |
| T4 | — | Phải nhận lỗi xung đột; không được âm thầm ghi đè bản của A |

Nếu ứng dụng chỉ tải Article mới nhất rồi `save()` dữ liệu từ client, lần ghi của B có thể **ghi đè thay đổi của A**. Việc B gửi `expectedVersion=7` là lời khẳng định: “Tôi chỉ cho phép sửa nếu bản ghi vẫn là phiên bản 7”.

Một bài toán khác xảy ra **ngay trong cùng thời gian xử lý trên server**: hai transaction cùng đọc version 7, cùng kiểm tra điều kiện hợp lệ, rồi cùng ghi. Kiểm tra thủ công tại Service không đủ để ngăn race này.

Do đó cần hai lớp bảo vệ bổ sung nhau:

1. **Kiểm tra phiên bản do caller biết** để phát hiện yêu cầu đã cũ trước khi ghi, kể cả khi lần cập nhật trước đã hoàn tất từ lâu.
2. **Optimistic locking ở JPA/database** để phát hiện một transaction khác thay đổi bản ghi sau lần đọc của transaction hiện tại.

Chỉ khai báo `@Version` **không tự động phát hiện** một client gửi bản cũ nếu Service vừa tải bản mới nhất từ database và áp dụng nội dung cũ lên nó. Client phải mang theo phiên bản hoặc điều kiện tương đương để Service kiểm tra.

## 4. Dùng `@Version` cho optimistic locking

JPA hỗ trợ trường phiên bản do persistence provider quản lý. Ví dụ dưới đây dùng **Jakarta Persistence** (Spring Boot 3+):

```java
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import jakarta.persistence.Version;
import java.util.Objects;

@Entity
@Table(name = "articles")
public class Article {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Version
    @Column(nullable = false)
    private Long version;

    @Column(nullable = false, length = 200)
    private String title;

    protected Article() {
        // JPA yêu cầu constructor không tham số.
    }

    public Article(String title) {
        rename(title);
    }

    public Long id() {
        return id;
    }

    public Long version() {
        return version;
    }

    public String title() {
        return title;
    }

    public void rename(String newTitle) {
        Objects.requireNonNull(newTitle, "title is required");
        if (newTitle.isBlank()) {
            throw new IllegalArgumentException("title must not be blank");
        }
        this.title = newTitle;
    }
}
```

Provider quản lý `version` trong vòng đời thực thể. Với một thay đổi được theo dõi bình thường, ORM thường phát SQL tương đương:

```sql
UPDATE articles
SET title = :new_title,
    version = :next_version
WHERE id = :id
  AND version = :version_read_before;
```

Nếu bản ghi đã có phiên bản khác, số hàng được cập nhật sẽ không như mong đợi và provider báo lỗi optimistic locking. Thời điểm lỗi có thể là lúc `flush()` hoặc khi commit transaction. **Không tự tăng/set `version` trong entity của lệnh ghi thông thường:** việc tăng và kiểm tra này thuộc provider.

Optimistic locking phù hợp khi xung đột tương đối hiếm và không muốn giữ khóa ghi trong suốt thao tác đọc. Nó **không thay thế** unique constraint, validation nghiệp vụ hoặc chiến lược khóa riêng cho những bất biến liên quan đến nhiều hàng.

## 5. Ví dụ thiết kế Repository và Service đầy đủ

Giả sử API yêu cầu client gửi `expectedVersion` khi đổi tiêu đề. Service trả phiên bản mới để client dùng cho thao tác tiếp theo.

### 5.1. DTO và lỗi miền nghiệp vụ

```java
public record RenameArticleCommand(String title, long expectedVersion) {}

public record ArticleView(Long id, String title, Long version) {
    public static ArticleView from(Article article) {
        return new ArticleView(
            article.id(),
            article.title(),
            article.version()
        );
    }
}
```

```java
public class ArticleNotFoundException extends RuntimeException {
    public ArticleNotFoundException(Long id) {
        super("Article " + id + " does not exist");
    }
}

public class VersionConflictException extends RuntimeException {
    public VersionConflictException(Long id, long expected, Long actual) {
        super("Article " + id + " expected version " + expected
            + " but current version is " + actual);
    }
}
```

Các exception này là kiểu lỗi Service công bố. Không đưa `HttpStatus` vào entity hay Repository; như vậy một Service vẫn dùng được trong REST, batch hoặc messaging.

### 5.2. Repository và transaction boundary

```java
import org.springframework.data.jpa.repository.JpaRepository;

public interface ArticleRepository extends JpaRepository<Article, Long> {
}
```

```java
import java.util.Objects;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class ArticleCommandService {
    private final ArticleRepository repository;

    public ArticleCommandService(ArticleRepository repository) {
        this.repository = repository;
    }

    @Transactional(readOnly = true)
    public ArticleView getRequired(Long id) {
        Article article = findRequired(id);
        return ArticleView.from(article);
    }

    @Transactional
    public ArticleView rename(Long id, RenameArticleCommand command) {
        Article article = findRequired(id);
        requireVersion(article, command.expectedVersion());

        article.rename(command.title());

        // Buộc ORM thực thi câu UPDATE sớm trong transaction.
        // @Version vẫn là cơ chế phát hiện race condition.
        repository.flush();
        return ArticleView.from(article);
    }

    @Transactional
    public void deleteStrict(Long id, long expectedVersion) {
        Article article = findRequired(id);
        requireVersion(article, expectedVersion);
        repository.delete(article);
        repository.flush();
    }

    private Article findRequired(Long id) {
        return repository.findById(id)
            .orElseThrow(() -> new ArticleNotFoundException(id));
    }

    private void requireVersion(Article article, long expectedVersion) {
        if (!Objects.equals(article.version(), expectedVersion)) {
            throw new VersionConflictException(
                article.id(), expectedVersion, article.version());
        }
    }
}
```

Một số điểm đáng chú ý:

- `@Transactional` đặt ở **Service**, bao trùm đọc, so sánh phiên bản, thay đổi entity và flush. Nếu lỗi runtime phát sinh, transaction sẽ rollback theo cơ chế mặc định của Spring.
- Entity lấy bằng `findById()` đang được quản lý trong persistence context; **dirty checking** đủ để ghi thay đổi. Không cần tạo entity mới chỉ có `id` rồi `save()`, vì thao tác merge detached entity thiếu trường có thể dẫn đến ghi đè dữ liệu không mong muốn.
- `repository.flush()` ép provider gửi SQL trước khi phương thức kết thúc để lỗi cạnh tranh thường xuất hiện gần thao tác ghi. **Flush chưa phải commit**; transaction vẫn có thể thất bại ở bước commit.
- Kiểm tra `expectedVersion` bắt yêu cầu cũ đã tồn tại **trước khi** transaction bắt đầu. Điều kiện `@Version` của DB tiếp tục bắt thay đổi **sau khi** Service tải Article.
- Nếu transaction khác xóa Article sau `findRequired()`, lỗi khi ghi có thể được biểu diễn như xung đột đồng thời. Không thể luôn phân biệt chính xác “đã bị xóa” với “đã bị cập nhật” chỉ từ một optimistic-lock exception.

Với lệnh xóa, chính sách ở ví dụ là **xóa nghiêm ngặt kèm điều kiện phiên bản**. Nếu sản phẩm chọn “xóa đảm bảo trạng thái cuối”, hãy thiết kế một phương thức Service khác có chủ đích; không dùng `catch (Exception)` để nuốt toàn bộ lỗi bởi vì nó có thể che lỗi database thực sự.

## 6. Ánh xạ lỗi sang hợp đồng REST

REST controller chỉ chuyển input thành lệnh và chuyển kết quả Service thành response. Một cách dùng `ProblemDetail` của Spring Framework 6:

```java
import jakarta.persistence.OptimisticLockException;
import org.springframework.dao.OptimisticLockingFailureException;
import org.springframework.http.HttpStatus;
import org.springframework.http.ProblemDetail;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
public class ArticleExceptionHandler {
    @ExceptionHandler(ArticleNotFoundException.class)
    public ProblemDetail notFound(ArticleNotFoundException exception) {
        ProblemDetail body = ProblemDetail.forStatusAndDetail(
            HttpStatus.NOT_FOUND, exception.getMessage());
        body.setTitle("Article not found");
        body.setProperty("code", "ARTICLE_NOT_FOUND");
        return body;
    }

    @ExceptionHandler(VersionConflictException.class)
    public ProblemDetail staleClient(VersionConflictException exception) {
        ProblemDetail body = ProblemDetail.forStatusAndDetail(
            HttpStatus.CONFLICT, exception.getMessage());
        body.setTitle("Article version conflict");
        body.setProperty("code", "ARTICLE_VERSION_CONFLICT");
        return body;
    }

    @ExceptionHandler({
        OptimisticLockingFailureException.class,
        OptimisticLockException.class
    })
    public ProblemDetail concurrentWrite(Exception exception) {
        ProblemDetail body = ProblemDetail.forStatusAndDetail(
            HttpStatus.CONFLICT,
            "The article changed during this operation; reload and retry.");
        body.setTitle("Concurrent modification");
        body.setProperty("code", "CONCURRENT_MODIFICATION");
        return body;
    }
}
```

Spring có thể dịch lỗi của provider thành `ObjectOptimisticLockingFailureException` (một lớp con của `OptimisticLockingFailureException`). Với một số đường đi commit, lỗi gốc có thể được bọc trong exception khác; cấu hình xử lý cần xét chuỗi nguyên nhân theo stack đang sử dụng. Không nên xuất stack trace, SQL hoặc thông tin transaction nội bộ ra response.

Ví dụ trao đổi:

```http
GET /articles/42

HTTP/1.1 200 OK
Content-Type: application/json

{"id":42,"title":"Bản nháp","version":7}
```

```http
PATCH /articles/42
Content-Type: application/json

{"title":"Bản đã duyệt","expectedVersion":7}

HTTP/1.1 200 OK
Content-Type: application/json

{"id":42,"title":"Bản đã duyệt","version":8}
```

Nếu một client khác vẫn gửi `expectedVersion=7` sau đó, Service trả `409` với `code=ARTICLE_VERSION_CONFLICT`. Client cần tải lại Article 42, so sánh nội dung và quyết định có gửi thay đổi mới hay không.

### 6.1. Dùng HTTP `ETag` và `If-Match` khi phù hợp

Thay vì trường `expectedVersion` trong JSON, API cũng có thể biểu diễn phiên bản bằng ETag:

```http
GET /articles/42

HTTP/1.1 200 OK
ETag: "v7"

{"id":42,"title":"Bản nháp","version":7}
```

```http
PATCH /articles/42
If-Match: "v7"
Content-Type: application/json

{"title":"Bản đã duyệt"}
```

Với hợp đồng **conditional request** này, nếu điều kiện `If-Match` sai, phản hồi thích hợp là **`412 Precondition Failed`**. Nếu endpoint quy định bắt buộc có điều kiện nhưng client không gửi, có thể chọn **`428 Precondition Required`**. Cần xây dựng và kiểm tra ETag nhất quán cho *đúng representation* được trả về; một số representation biến đổi mà không đổi `@Version` sẽ khiến ETag chỉ từ version không còn đủ mạnh. Đừng đồng thời dùng `409` và `412` tùy hứng cho cùng một loại yêu cầu.

Nếu API dùng `If-Match`, thành phần chuyển đổi HTTP → Service phải đọc ETag và truyền version vào lệnh; kiểm tra header ở controller **không thay thế** `@Version` của JPA trong transaction.

## 7. Phân biệt race condition trong thực tế

Có ba thời điểm khác nhau:

**Trường hợp A — ID chưa tồn tại khi đọc:** `findById(42)` trả rỗng; Service trả `ArticleNotFoundException`. Không cần tạo entity giả hoặc gọi `save()` để “tự sửa” dữ liệu.

**Trường hợp B — Client đã cũ từ trước:** DB đang ở version 8, client gửi 7. `findById()` thành công nhưng `requireVersion()` từ chối. Đây là xung đột do hợp đồng client–server xác định.

**Trường hợp C — Hai transaction đua nhau:** cả hai cùng đọc version 7 và vượt qua `requireVersion()`. Transaction A ghi trước, tăng version lên 8; transaction B tiếp tục ghi theo version 7 và bị cơ chế optimistic locking của JPA/DB từ chối.

Như vậy, **`existsById()` rồi `save()` không phải một giải pháp chống xung đột**. Hai câu truy vấn rời nhau không thể bảo đảm trạng thái vẫn giữ nguyên tới lúc ghi. Tương tự, bắt `OptimisticLockException` rồi lập tức tải entity mới và ghi lại dữ liệu cũ có thể vô hiệu hóa mục đích bảo vệ thay đổi của người dùng khác.

## 8. Các lựa chọn Repository khác và giới hạn cần hiểu

### 8.1. Lệnh cập nhật có điều kiện ở mức SQL/JPQL

Nếu thực sự cần một câu lệnh cập nhật nguyên tử theo version, có thể dùng *compare-and-set*:

```java
import org.springframework.data.jpa.repository.Modifying;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

public interface ArticleRepository extends JpaRepository<Article, Long> {
    @Modifying
    @Query("""
        update Article a
           set a.title = :title,
               a.version = a.version + 1
         where a.id = :id and a.version = :expectedVersion
        """)
    int renameIfVersionMatches(
        @Param("id") Long id,
        @Param("title") String title,
        @Param("expectedVersion") long expectedVersion
    );
}
```

Phương thức này cần được gọi trong transaction. `int` là số hàng bị tác động: `1` cho biết điều kiện khớp; `0` có thể là **không có ID hoặc version không khớp**. Nếu API cần phân biệt `404` và `409`, phải có bước xác minh thêm, đồng thời thừa nhận rằng kết quả đọc bổ sung cũng có thể thay đổi do concurrency.

**Cảnh báo:** Bulk JPQL update bỏ qua cơ chế dirty checking, entity callback và optimistic-lock checking tự động theo từng entity; phiên bản phải được cập nhật có chủ đích như trong ví dụ. Persistence context có thể giữ entity cũ nếu đã tải trước bulk update. Không trộn cách này với update entity quản lý mà chưa có chiến lược đồng bộ context rõ ràng.

### 8.2. Khóa bi quan

`@Lock(LockModeType.PESSIMISTIC_WRITE)` có thể phù hợp khi mỗi giao dịch cần độc quyền sửa một thực thể hoặc xung đột xảy ra thường xuyên. Đổi lại, giao dịch có thể chờ khóa, deadlock hoặc timeout. Khóa bi quan cũng **không giải quyết** trường hợp người dùng giữ form cũ trong nhiều phút; nếu API cần bảo vệ dữ liệu người dùng đã đọc, vẫn cần điều kiện version ở biên lệnh ghi.

### 8.3. Ràng buộc nghiệp vụ

Trùng `slug`/`email` được bảo vệ bằng unique constraint là **xung đột khóa nghiệp vụ**, không phải optimistic locking. Kiểm tra trước `existsBySlug()` chỉ giúp thông báo thân thiện; unique constraint trong DB mới bảo đảm không có hai transaction tạo giá trị trùng nhau. Mapping nên có mã lỗi riêng, ví dụ `ARTICLE_SLUG_CONFLICT`.

## 9. Hợp đồng ngoại lệ và cách retry

Một ứng dụng lớn nên thống nhất mã lỗi có thể đọc bằng máy:

| Mã lỗi | Ý nghĩa | Hành động khả thi |
|---|---|---|
| `ARTICLE_NOT_FOUND` | ID không tồn tại ở thời điểm kiểm tra | Kiểm tra ID, điều hướng về danh sách hoặc thông báo đã xóa |
| `ARTICLE_VERSION_CONFLICT` | `expectedVersion` client gửi không còn khớp | Tải dữ liệu mới, hòa giải sửa đổi, gửi lại với version mới nếu còn phù hợp |
| `CONCURRENT_MODIFICATION` | Bị transaction khác sửa/xóa khi đang xử lý | Tải lại trạng thái; cân nhắc retry theo loại lệnh |
| `ARTICLE_SLUG_CONFLICT` | Vi phạm khóa duy nhất nghiệp vụ | Chọn slug khác |

Không tự động retry mọi lệnh `PATCH`/`DELETE` sau khi gặp `409`: một lệnh có thể tạo side effect hoặc tính toán dựa trên nội dung cũ. Nếu có retry, phải mở **transaction mới**, xem lại dữ liệu và chỉ áp dụng khi nghiệp vụ cho phép. Với thao tác có side effect bên ngoài (gửi email, thanh toán, phát sự kiện), cần thiết kế idempotency hoặc cơ chế outbox riêng để tránh lặp tác động.

Không nên trả nguyên số phiên bản hiện tại cho mọi loại lỗi nếu việc đó làm lộ dữ liệu không được phép truy cập. **Authorization phải được kiểm tra trước** hoặc trong query có giới hạn quyền; API có thể cố ý ẩn sự tồn tại tài nguyên và trả `404` theo chính sách bảo mật.

## 10. Những trường hợp cần kiểm chứng khi triển khai

Khi tích hợp Repository, Service và HTTP adapter, những tình huống sau là tiêu chí hành vi cần kiểm chứng:

1. **GET ID không có:** không tạo bản ghi; trả đúng lỗi “not found”.
2. **Danh sách trống:** trả mảng rỗng, không báo lỗi “not found”.
3. **Đổi tiêu đề với version đúng:** lưu một lần, trả phiên bản mới.
4. **Gửi lại version cũ sau khi có thay đổi:** không ghi đè, trả lỗi xung đột xác định.
5. **Hai transaction cập nhật cùng version:** chỉ một thành công; transaction còn lại bị optimistic locking ngăn lại.
6. **Bản ghi bị xóa giữa đọc và ghi:** không được tự tạo lại bản ghi, không báo cập nhật thành công giả.
7. **Xóa ID vắng mặt:** kết quả đúng chính sách nghiêm ngặt hoặc đảm bảo trạng thái cuối mà API đã công bố.
8. **Vi phạm unique constraint:** trả mã lỗi nghiệp vụ riêng; không ngụy trang thành lỗi `@Version`.
9. **Rollback và side effect:** khi transaction bị xung đột, dữ liệu và những tác động phụ liên quan phải được xử lý đúng chiến lược.

Để kiểm chứng concurrency thật, cần **hai transaction/persistence context độc lập** cùng đọc một phiên bản rồi ghi xen kẽ. Một bài test chỉ gọi tuần tự hai lần trong cùng transaction sẽ không mô phỏng được race condition.

## 11. Nguyên tắc thiết kế có thể áp dụng lại

Trong thiết kế Repository JPA, hãy để phương thức truy vấn mô tả đúng sự vắng mặt bằng `Optional`, để Service định nghĩa khi nào sự vắng mặt là lỗi, và để API chuyển lỗi ấy thành hợp đồng dễ hiểu. Với thao tác cập nhật/xóa có nguy cơ ghi đè, yêu cầu client cung cấp phiên bản đã quan sát, kiểm tra trong transaction và dùng `@Version` để ngăn cuộc đua ghi ở database. Cuối cùng, phân biệt rõ **không tồn tại**, **xung đột phiên bản** và **vi phạm ràng buộc nghiệp vụ** trong mã lỗi và cách phục hồi; đó là nền tảng để hệ thống xử lý đồng thời một cách có thể dự đoán.
