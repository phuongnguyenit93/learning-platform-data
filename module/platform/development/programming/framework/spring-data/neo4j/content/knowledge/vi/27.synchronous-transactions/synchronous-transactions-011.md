# Phân biệt giao dịch Spring với giao dịch tự mở bằng Driver

Khi ứng dụng Spring Data Neo4j (SDN) ghi dữ liệu, transaction có thể được quản lý bởi Spring hoặc được mở trực tiếp từ Neo4j Java Driver. Hai cách đều có thể bảo đảm một nhóm lệnh Cypher được commit hoặc rollback cùng nhau, nhưng chúng có vòng đời và cơ chế tham gia khác nhau.

Với transaction do Spring quản lý, service xác định ranh giới nghiệp vụ bằng `@Transactional` hoặc `TransactionTemplate`. Repository, `Neo4jTemplate` và `Neo4jClient` sử dụng transaction hiện hành do Spring cung cấp. Với transaction tự mở bằng Driver, code trực tiếp tạo `Session`, gọi `beginTransaction()`, rồi tự commit, rollback và đóng tài nguyên. Một transaction Driver được mở thủ công không tự động tham gia transaction Spring chỉ vì cả hai cùng dùng một `Driver` bean.

Bài học này giúp chọn đúng cơ chế cho ứng dụng đồng bộ, tránh vô tình chia một nghiệp vụ thành hai transaction độc lập và quản lý đúng vòng đời của session/transaction.

## 1. Transaction bảo vệ điều gì?

Một transaction nhóm các thay đổi dữ liệu thành một đơn vị. Ví dụ, khi phát hành một phim, ứng dụng có thể:

1. Cập nhật trạng thái phim thành `PUBLISHED`.
2. Ghi thời điểm phát hành.
3. Tạo relationship tới người phê duyệt.
4. Ghi một node sự kiện kiểm toán.

Nếu bước thứ tư thất bại, nghiệp vụ có thể yêu cầu ba bước trước cũng phải được hoàn tác. Khi tất cả thao tác chạy trong cùng một transaction Neo4j, database chỉ commit khi toàn bộ công việc thành công; nếu transaction rollback, các thay đổi của transaction đó không được lưu.

Transaction không thay thế validation nghiệp vụ. Trước khi ghi, ứng dụng vẫn phải kiểm tra quyền, trạng thái hợp lệ và các quy tắc như mã phim duy nhất. Transaction bảo vệ tính nhất quán của những thay đổi được thực hiện trong ranh giới của nó.

## 2. Hai cách quản lý transaction đồng bộ

<table>
  <table-row>
    <table-cell width="50%">
      **Spring-managed transaction**

      - Ranh giới đặt ở service.
      - Dùng `@Transactional` hoặc `TransactionTemplate`.
      - Spring mở và hoàn tất transaction.
      - Repository, template và client tham gia transaction hiện hành.
      - Phù hợp với phần lớn nghiệp vụ trong ứng dụng Spring.
    </table-cell>
    <table-cell width="50%">
      **Driver-managed transaction**

      - Code trực tiếp mở `Session` và `Transaction`.
      - Dùng `session.beginTransaction()`.
      - Code tự commit hoặc rollback.
      - Code tự đóng transaction và session.
      - Phù hợp khi cần dùng trực tiếp Driver API ngoài luồng repository/template.
    </table-cell>
  </table-row>
</table>

Hai cách này là hai cơ chế quản lý transaction khác nhau. Cần chọn một cơ chế làm chủ ranh giới nghiệp vụ. Nếu một method Spring đang chạy trong transaction mà lại mở thêm transaction Driver thủ công, hai transaction đó là độc lập và có thể commit/rollback riêng.

## 3. Transaction do Spring quản lý với @Transactional

Trong ứng dụng imperative, SDN tích hợp với transaction abstraction của Spring thông qua `Neo4jTransactionManager`. Spring Boot thường tự cấu hình transaction manager phù hợp khi dependency và cấu hình Neo4j được thiết lập. Nếu tự cấu hình ứng dụng, cần khai báo transaction manager và bật transaction management theo cấu hình Spring.

Đặt `@Transactional` ở service để bao trùm toàn bộ thao tác tạo thành một nghiệp vụ:

```java
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class MoviePublishingService {
    private final MovieRepository movieRepository;
    private final AuditRepository auditRepository;

    public MoviePublishingService(
            MovieRepository movieRepository,
            AuditRepository auditRepository) {
        this.movieRepository = movieRepository;
        this.auditRepository = auditRepository;
    }

    @Transactional
    public void publish(String movieCode, String approverCode) {
        movieRepository.markPublished(movieCode);
        movieRepository.linkApprover(movieCode, approverCode);
        auditRepository.recordPublished(movieCode, approverCode);
    }
}
```

Ví dụ giả định các repository method thực hiện lệnh ghi bằng SDN và dùng cùng Neo4j transaction manager. Nếu cả ba lời gọi thành công, Spring commit khi method kết thúc. Nếu một lời gọi ném exception làm transaction rollback, các thay đổi đã thực hiện trong transaction đó được hoàn tác.

Các thao tác SDN tham gia transaction hiện hành:

- `Neo4jRepository` và các repository method được gọi trong service.
- `Neo4jTemplate`.
- `Neo4jClient` imperative.

Vì vậy, service có thể phối hợp nhiều repository và template mà không phải tự truyền `Session` hoặc `Transaction` qua từng method.

### Ranh giới transaction nằm ở đâu?

`@Transactional` được xử lý bởi Spring AOP/proxy. Khi một bean khác gọi method được proxy quản lý, Spring áp dụng transaction attribute trước khi chạy method. Một lời gọi nội bộ từ method này sang method khác trong cùng object (`this.otherMethod()`) thường không đi qua proxy, do đó annotation trên method được gọi nội bộ có thể không tạo ranh giới transaction mới.

Đặt transaction ở public service method được gọi từ bên ngoài bean là cách dễ hiểu và dễ kiểm tra. Không đặt annotation rải rác ở mọi repository method nếu nghiệp vụ cần một transaction xuyên suốt nhiều thao tác.

### Rollback theo exception

Theo mặc định của Spring, transaction rollback khi method ném `RuntimeException` hoặc `Error`. Checked exception không tự động kích hoạt rollback theo quy tắc mặc định. Nếu nghiệp vụ yêu cầu rollback cả checked exception, khai báo rõ:

```java
@Transactional(rollbackFor = Exception.class)
public void publish(String movieCode, String approverCode)
        throws Exception {
    movieRepository.markPublished(movieCode);
    auditRepository.recordPublished(movieCode, approverCode);
    validateExternalApproval(movieCode);
}
```

Chọn rollback rule theo loại exception thực tế. Nếu code bắt exception rồi không ném lại, Spring có thể xem method đã hoàn tất bình thường và commit; trong trường hợp muốn rollback sau khi bắt lỗi, có thể đánh dấu transaction rollback-only bằng cơ chế Spring phù hợp.

## 4. Dùng TransactionTemplate khi muốn điều khiển bằng code

Không phải lúc nào cũng cần annotation. `TransactionTemplate` cho phép chạy một khối công việc trong transaction do Spring quản lý:

```java
import org.springframework.stereotype.Service;
import org.springframework.transaction.support.TransactionTemplate;

@Service
public class MovieImportService {
    private final TransactionTemplate transactionTemplate;
    private final MovieRepository movieRepository;
    private final AuditRepository auditRepository;

    public MovieImportService(
            TransactionTemplate transactionTemplate,
            MovieRepository movieRepository,
            AuditRepository auditRepository) {
        this.transactionTemplate = transactionTemplate;
        this.movieRepository = movieRepository;
        this.auditRepository = auditRepository;
    }

    public void importOne(MovieInput input) {
        transactionTemplate.executeWithoutResult(status -> {
            movieRepository.upsert(input);
            auditRepository.recordImported(input.code());
        });
    }
}
```

`TransactionTemplate` vẫn sử dụng transaction manager của Spring. Các repository method bên trong callback tham gia cùng transaction. Đây là quản lý transaction theo chương trình của Spring, không phải mở transaction trực tiếp bằng Driver.

Chọn `TransactionTemplate` khi ranh giới transaction cần được quyết định trong luồng code, ví dụ chỉ mở transaction cho từng phần tử của một import hoặc cần bắt lỗi và xử lý kết quả ngay quanh callback. Với ranh giới ổn định quanh service method, `@Transactional` thường dễ đọc hơn.

## 5. Transaction do Driver quản lý thủ công

Neo4j Java Driver cho phép code làm việc trực tiếp với `Driver`, `Session` và `Transaction`. Khi dùng explicit transaction, ứng dụng chịu trách nhiệm bắt đầu, commit/rollback và đóng tài nguyên.

Ví dụ tạo một phim và ghi sự kiện kiểm toán bằng một transaction Driver:

```java
import java.util.Map;

import org.neo4j.driver.Driver;
import org.neo4j.driver.Session;
import org.neo4j.driver.Transaction;

public class DriverMovieWriter {
    private final Driver driver;

    public DriverMovieWriter(Driver driver) {
        this.driver = driver;
    }

    public void createMovie(String code, String title) {
        try (Session session = driver.session()) {
            try (Transaction tx = session.beginTransaction()) {
                tx.run(
                    "CREATE (:Movie {code: $code, title: $title})",
                    Map.of("code", code, "title", title)
                ).consume();

                tx.run(
                    "CREATE (:AuditEvent {type: $type, movieCode: $code})",
                    Map.of("type", "MOVIE_CREATED", "code", code)
                ).consume();

                tx.commit();
            }
        }
    }
}
```

Nếu cả hai câu lệnh thành công, `tx.commit()` xác nhận thay đổi. Nếu code thoát khỏi khối `try` trước khi commit, đóng explicit transaction chưa commit sẽ rollback transaction; session cũng được đóng bởi try-with-resources.

Khi cần xử lý lỗi rõ ràng, có thể gọi `rollback()` trong `catch`, sau đó ném lại exception. Luôn để transaction và session được đóng kể cả khi query hoặc commit thất bại.

### Vòng đời Session và Transaction

```text
Driver (được quản lý lâu dài bởi ứng dụng)
  └── Session (ngắn hạn, không chia sẻ giữa các thread)
        └── Transaction (một đơn vị công việc)
              ├── tx.run(...)
              ├── tx.run(...)
              └── commit() hoặc rollback()
        └── close Session
```

`Driver` là đối tượng thread-safe, thường được quản lý như singleton bean và đóng khi ứng dụng dừng. `Session` và `Transaction` không thread-safe; tạo chúng cho một đơn vị công việc, không chia sẻ cho nhiều thread đồng thời. Dùng try-with-resources để tránh rò rỉ tài nguyên.

Nếu ứng dụng dùng nhiều database, có thể chỉ định database khi tạo session:

```java
import org.neo4j.driver.SessionConfig;

try (Session session = driver.session(
        SessionConfig.builder().withDatabase("neo4j").build())) {
    // Thực hiện công việc với database đã chọn.
}
```

Không giữ một session mở suốt vòng đời ứng dụng hoặc dùng một session làm field chia sẻ giữa các request.

## 6. Transaction function của Driver khác explicit transaction

Driver còn cung cấp transaction function như `executeRead` và `executeWrite`. Chúng vẫn là transaction do Driver quản lý, nhưng Driver điều khiển vòng đời transaction và có thể retry transaction function khi gặp lỗi transient phù hợp.

```java
import java.util.Map;

import org.neo4j.driver.Driver;
import org.neo4j.driver.Session;

public class DriverMovieReader {
    private final Driver driver;

    public DriverMovieReader(Driver driver) {
        this.driver = driver;
    }

    public String findTitle(String code) {
        try (Session session = driver.session()) {
            return session.executeRead(tx ->
                tx.run(
                    "MATCH (m:Movie {code: $code}) RETURN m.title AS title",
                    Map.of("code", code)
                ).single().get("title").asString()
            );
        }
    }
}
```

Với write transaction function, dùng `session.executeWrite(tx -> { ... })`. Driver quản lý commit/rollback và có thể chạy lại callback khi retry. Vì callback có thể được thực thi nhiều lần, không đặt side effect bên ngoài Neo4j bên trong callback, ví dụ gửi email hoặc ghi file. Những side effect đó có thể lặp nếu Driver retry transaction function.

Explicit transaction qua `beginTransaction()` hữu ích khi code cần tự điều khiển chính xác thời điểm commit. Transaction function hữu ích khi muốn Driver quản lý vòng đời và retry theo cơ chế của Driver.

## 7. Điểm khác biệt quan trọng: transaction Driver không tự tham gia transaction Spring

Đây là lỗi thiết kế dễ tạo ra dữ liệu không nhất quán.

Giả sử service có `@Transactional`, sau đó gọi repository để cập nhật phim và mở một session Driver mới để ghi audit:

```java
@Transactional
public void publish(String code) {
    movieRepository.markPublished(code); // Transaction Spring

    try (Session session = driver.session();
         Transaction tx = session.beginTransaction()) {
        tx.run(
            "CREATE (:AuditEvent {movieCode: $code})",
            Map.of("code", code)
        ).consume();
        tx.commit(); // Transaction Driver riêng
    }

    throw new IllegalStateException("Simulated failure");
}
```

Khi exception xuất hiện:

- Transaction Spring có thể rollback cập nhật phim.
- Transaction Driver đã commit audit trước đó, nên audit vẫn tồn tại.

Hai thao tác dùng cùng một `Driver` bean cũng không làm chúng tự động trở thành cùng transaction. Spring transaction manager quản lý tài nguyên transaction mà nó đã mở và gắn với transaction context hiện hành; session được tạo độc lập bằng `driver.session()` không tự tham gia context đó.

<table>
  <table-row>
    <table-cell width="50%">
      **Luồng một transaction**

      `@Transactional`

      - Repository update
      - Neo4jTemplate write
      - Neo4jClient write

      Spring commit/rollback cả nhóm.
    </table-cell>
    <table-cell width="50%">
      **Hai transaction độc lập**

      `@Transactional`

      - Repository update

      `driver.session()` + `beginTransaction()`

      Driver commit/rollback riêng.
    </table-cell>
  </table-row>
</table>

Nếu cần các thao tác cùng atomic, hãy dùng `Neo4jRepository`, `Neo4jTemplate` hoặc `Neo4jClient` trong transaction Spring. Đừng mở một explicit Driver transaction mới bên trong service chỉ để chạy thêm một câu Cypher.

## 8. Khi nào nên dùng trực tiếp Driver trong ứng dụng Spring?

Có thể có tình huống cần tính năng cấp thấp của Driver mà abstraction repository hoặc template chưa cung cấp. Trước tiên, hãy xem `Neo4jClient` có đáp ứng được hay không. `Neo4jClient` cho phép viết Cypher tùy chỉnh nhưng vẫn tích hợp với transaction Spring hiện hành.

Chỉ dùng raw Driver khi thực sự cần API đặc thù, ví dụ thao tác quản lý session, bookmark hoặc chức năng Driver mà `Neo4jClient` không bộc lộ. Nếu raw Driver được dùng độc lập, hãy để transaction Driver sở hữu toàn bộ nhóm công việc đó và quản lý session/transaction rõ ràng.

Nếu một service cần phối hợp thao tác SDN và một đoạn query đặc thù, ưu tiên đưa đoạn query qua `Neo4jClient` hoặc `Neo4jTemplate` để mọi thao tác cùng tham gia transaction Spring.

Không lấy `Driver` rồi tạo session mới trong mỗi repository method để thay thế SDN. Cách đó bỏ qua transaction manager, mapping và các abstraction sẵn có, khiến ứng dụng khó kiểm soát nhất quán dữ liệu.

## 9. Propagation và transaction lồng nhau trong Spring

Spring cung cấp propagation để quyết định cách method tham gia transaction hiện hành:

| Propagation | Hành vi khái quát | Trường hợp sử dụng |
|---|---|---|
| `REQUIRED` (mặc định) | Tham gia transaction hiện hành; nếu chưa có thì tạo mới | Hầu hết service nghiệp vụ |
| `REQUIRES_NEW` | Tạm treo transaction hiện hành và mở transaction mới | Một thao tác cần commit độc lập theo yêu cầu rõ ràng |
| `SUPPORTS` | Tham gia nếu có transaction; nếu không thì chạy không có transaction | Một số thao tác có thể chạy trong hoặc ngoài transaction |
| `MANDATORY` | Yêu cầu phải có transaction hiện hành | Method chỉ hợp lệ khi được gọi trong transaction |
| `NOT_SUPPORTED` | Tạm treo transaction hiện hành và chạy không có transaction | Công việc không nên giữ transaction mở |

Ví dụ:

```java
import org.springframework.transaction.annotation.Propagation;

@Transactional(propagation = Propagation.REQUIRES_NEW)
public void recordIndependentAudit(String code) {
    auditRepository.recordPublished(code);
}
```

`REQUIRES_NEW` vẫn là transaction do Spring quản lý. Nó không tương đương với việc tự mở `driver.session().beginTransaction()`. Dùng propagation khác mặc định khi nghiệp vụ thực sự yêu cầu semantics đó, vì transaction độc lập có thể commit dù transaction bên ngoài rollback.

Lưu ý rằng khả năng nested transaction vật lý phụ thuộc transaction manager và database. Không mặc định rằng `NESTED` tạo savepoint trong Neo4j; hãy kiểm tra hỗ trợ của `Neo4jTransactionManager` trong phiên bản đang dùng.

## 10. Thread, async và ranh giới transaction

Imperative Spring transaction thường gắn với thread hiện tại. Vì vậy, khi code tạo thread mới, gửi tác vụ sang executor hoặc dùng `@Async`, transaction của thread gọi không tự động truyền sang thread mới.

Ví dụ không nên kỳ vọng thao tác trong thread mới tham gia transaction của method bên ngoài:

```java
@Transactional
public void publish(String code) {
    movieRepository.markPublished(code);

    executor.execute(() ->
        auditRepository.recordPublished(code)
    );
}
```

Tác vụ executor chạy ngoài transaction context của thread gọi. Nếu cần tính atomic, hãy thực hiện các thao tác trong cùng thread/transaction trước khi trả về. Nếu tác vụ bất đồng bộ là một nghiệp vụ độc lập, hãy đặt transaction riêng ở bean được gọi trong thread worker và thiết kế retry/idempotency cho nó.

Không truyền `Session` hoặc `Transaction` Driver sang thread khác. Chúng không thread-safe. Hãy tạo session và transaction mới trong thread thực thi công việc.

## 11. Transaction và xử lý batch

Với import hàng trăm nghìn node, mở một transaction duy nhất cho toàn bộ job có thể giữ transaction và tài nguyên quá lâu. Thường nên chia dữ liệu thành batch, mỗi batch có transaction riêng:

```java
public void importMovies(List<MovieInput> inputs) {
    for (List<MovieInput> batch : partition(inputs, 500)) {
        transactionTemplate.executeWithoutResult(status -> {
            for (MovieInput input : batch) {
                movieRepository.upsert(input);
            }
        });
    }
}
```

Ví dụ dùng `TransactionTemplate` để mỗi batch là một transaction độc lập. Nếu batch thứ tư thất bại, ba batch trước có thể đã commit; job cần checkpoint hoặc cơ chế chạy lại an toàn để tiếp tục. Chọn kích thước batch dựa trên thời gian query, lượng dữ liệu và giới hạn tài nguyên thực tế.

`partition(inputs, 500)` trong ví dụ là hàm tiện ích chia danh sách thành các nhóm tối đa 500 phần tử; hãy dùng implementation phù hợp với dự án hoặc thư viện đang có.

Nếu toàn bộ batch phải thành công hoặc thất bại cùng nhau theo yêu cầu nghiệp vụ, phải giữ chúng trong cùng transaction và chấp nhận chi phí của transaction dài. Đây là quyết định về semantics nghiệp vụ, không chỉ là tối ưu hiệu năng.

## 12. Bảng so sánh chi tiết

| Tiêu chí | Spring `@Transactional` / `TransactionTemplate` | Driver `beginTransaction()` |
|---|---|---|
| Ai mở transaction? | Spring transaction manager | Code ứng dụng |
| Cách xác định ranh giới | Service method hoặc callback | Khối code quanh `beginTransaction()` |
| Repository/Template/Client có tham gia? | Có, khi dùng cùng transaction manager/context | Không tự động tham gia transaction Driver được mở riêng |
| Commit/rollback | Spring quản lý theo kết quả method/callback và rollback rule | Code gọi `commit()`/`rollback()`; đóng transaction chưa commit sẽ rollback |
| Session lifecycle | Transaction manager quản lý session gắn với transaction | Code phải đóng session |
| Retry | Theo cơ chế Spring/ứng dụng; không tự giả định method được chạy lại | Explicit transaction không có retry transaction-function tự động; `executeRead/executeWrite` có retry phù hợp |
| Tích hợp với service nghiệp vụ | Tự nhiên trong ứng dụng Spring | Cần tự quản lý và phối hợp |
| Dùng khi | Hầu hết nghiệp vụ SDN | Cần Driver API trực tiếp và chấp nhận tự quản lý vòng đời |

## 13. Kiểm thử transaction

Một bài kiểm thử transaction nên chứng minh cả trường hợp commit và rollback.

**Trường hợp commit:**

1. Gọi service có `@Transactional` để cập nhật phim và ghi audit.
2. Để method hoàn tất bình thường.
3. Đọc lại bằng repository hoặc Cypher.
4. Xác nhận cả trạng thái phim và audit đều tồn tại.

**Trường hợp rollback:**

1. Gọi service thực hiện cùng các thay đổi.
2. Làm phát sinh `RuntimeException` sau bước ghi.
3. Đọc lại sau khi transaction kết thúc.
4. Xác nhận cả trạng thái phim và audit đều trở về dữ liệu trước transaction.

**Kiểm tra transaction độc lập:**

1. Trong một service `@Transactional`, cập nhật node bằng repository.
2. Mở explicit Driver transaction riêng và commit audit.
3. Ném exception để transaction Spring rollback.
4. Xác nhận cập nhật node bị rollback nhưng audit đã commit vẫn còn.

Test thứ ba minh họa vì sao không trộn hai transaction nếu kỳ vọng atomicity. Khi dùng test method có `@Transactional`, hãy chú ý dữ liệu có thể được rollback sau test; nếu cần quan sát trạng thái đã commit, hãy kiểm tra ngoài transaction test hoặc cấu hình test phù hợp.

## 14. Lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Repository rollback nhưng query raw Driver vẫn còn dữ liệu | Driver session mở transaction độc lập và đã commit | Dùng `Neo4jClient`/`Neo4jTemplate` trong transaction Spring |
| Repository method không rollback khi lỗi | Không có transaction Spring bao quanh toàn nghiệp vụ hoặc exception bị bắt | Đặt `@Transactional` ở service và kiểm tra rollback rule |
| Checked exception không rollback | Spring mặc định rollback cho runtime exception và error | Cấu hình `rollbackFor` nếu cần |
| Annotation `@Transactional` không có tác dụng | Self-invocation không đi qua proxy hoặc thiếu transaction manager | Gọi qua Spring bean proxy và kiểm tra cấu hình |
| Session/connection bị giữ lâu | Quên đóng Session/Transaction hoặc giữ session trong field | Dùng try-with-resources và phạm vi session ngắn |
| Lỗi khi chia sẻ session giữa request | Session và Transaction không thread-safe | Tạo session riêng cho đơn vị công việc |
| Transaction không bao gồm tác vụ async | Transaction imperative gắn với thread gọi | Mở transaction riêng trong worker hoặc giữ thao tác trong cùng transaction |
| Callback Driver gửi email lặp | `executeWrite` có thể retry transaction function | Chỉ đặt thao tác Neo4j có thể retry trong callback; xử lý side effect ngoài callback |
| Batch job giữ transaction quá lâu | Toàn bộ job chạy trong một transaction lớn | Chia batch và đặt transaction theo batch nếu nghiệp vụ cho phép |

## 15. Quy trình chọn cơ chế

1. Xác định các thao tác nào phải commit hoặc rollback cùng nhau.
2. Nếu thao tác dùng repository, `Neo4jTemplate` hoặc `Neo4jClient`, đặt ranh giới ở service bằng `@Transactional` hoặc `TransactionTemplate`.
3. Nếu cần raw Driver, kiểm tra trước xem `Neo4jClient` có đáp ứng được hay không.
4. Nếu mở transaction bằng Driver, tự quản lý `Session`, `Transaction`, commit/rollback và close.
5. Không giả định transaction Driver mở thủ công sẽ tham gia transaction Spring đang chạy.
6. Tránh chạy thao tác cần atomicity ở thread khác hoặc trong transaction độc lập.
7. Với batch lớn, chọn transaction theo batch hoặc toàn job dựa trên yêu cầu nghiệp vụ.
8. Kiểm thử commit, rollback, exception và trường hợp hai transaction độc lập.

## 16. Tự kiểm tra

1. `@Transactional` trong ứng dụng SDN được thực thi thông qua thành phần nào của Spring?
2. Vì sao repository và `Neo4jClient` có thể tham gia cùng transaction do Spring quản lý?
3. `TransactionTemplate` có phải là transaction tự mở bằng Driver không? Giải thích.
4. Khi dùng `driver.session().beginTransaction()`, code phải quản lý những thao tác vòng đời nào?
5. Vì sao cùng dùng một `Driver` bean không làm explicit transaction tự tham gia transaction Spring?
6. Điều gì xảy ra nếu transaction Driver đã commit nhưng transaction Spring bên ngoài rollback?
7. Khác biệt giữa `beginTransaction()` và `session.executeWrite(...)` là gì?
8. Vì sao callback của `executeWrite` không nên gửi email hoặc ghi file?
9. Tại sao transaction imperative không tự truyền sang thread `@Async`?
10. Khi nào nên dùng transaction riêng cho từng batch trong một import lớn?

## Tài liệu tham khảo

- [Spring Data Neo4j — Managing Transactions](https://docs.spring.io/spring-data/neo4j/reference/faq.html)
- [Spring Framework — Declarative Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative.html)
- [Neo4j Java Driver — Transactions](https://neo4j.com/docs/java-manual/current/transactions/)
- [Neo4j Java Driver — Sessions and Transactions](https://neo4j.com/docs/api/java-driver/current/org.neo4j.driver/org/neo4j/driver/Session.html)
