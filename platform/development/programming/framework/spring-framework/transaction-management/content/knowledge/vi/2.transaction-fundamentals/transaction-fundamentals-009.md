# Lỗi tại thời điểm commit và kết quả có thể chưa xác định

## 1. Mục tiêu và vấn đề cốt lõi

Một lỗi khi lưu dữ liệu không phải lúc nào cũng đồng nghĩa với “chưa có thay đổi nào được lưu”. Đặc biệt, **khi một hệ thống mất kết nối hoặc không nhận được phản hồi trong lúc `commit`**, phía gọi có thể không biết CSDL đã commit thành công hay chưa. Đây là **kết quả chưa xác định** (ambiguous/unknown commit outcome, đôi khi gọi là *in-doubt outcome*).

Sau bài này, bạn có thể:

- Xác định thời điểm Spring thực hiện commit so với thời điểm chạy phần thân phương thức `@Transactional` và gửi phản hồi cho client.
- Phân biệt **rollback đã xác nhận**, **commit đã xác nhận** và **không đủ chứng cứ để kết luận**.
- Hiểu tại sao một exception ở giai đoạn commit hoặc sau commit không tự chứng minh transaction đã rollback.
- Thiết kế thao tác nghiệp vụ có `operationId` / idempotency key, tra cứu trạng thái và retry an toàn khi phản hồi bị mất.
- Viết kiểm thử chứng minh một lời gọi có thể báo lỗi **sau khi dữ liệu đã commit**, đồng thời chỉ ra giới hạn của bài thử so với sự cố vật lý ngay trong lệnh commit.

Đề bài thuộc nhóm *Nền tảng giao dịch* của Spring Framework. Trọng tâm là cách hiểu đúng **kết quả cuối của một giao dịch** và cách ứng dụng phản ứng trước bất định, thay vì khảo sát toàn bộ các mức isolation hay cơ chế giao dịch phân tán.

## 2. Dòng thời gian: phương thức đã chạy xong chưa chắc giao dịch đã commit

Trong Spring dùng **declarative transaction, imperative API** với `@Transactional` và proxy, lời gọi thực tế có dạng:

```text
Caller / Controller                Spring transaction interceptor                   Database
      |                                       |                                         |
      |------ gọi service qua proxy -------->|                                         |
      |                                       |-- BEGIN / tham gia transaction ------>|
      |                                       |-- chạy phần thân method -------------->|
      |                                       |     các INSERT/UPDATE/DELETE           |
      |                                       |<-- method trả về giá trị --------------|
      |                                       |-- flush/beforeCommit (nếu có) -------->|
      |                                       |-- COMMIT ----------------------------->|
      |                                       |<-- kết quả COMMIT (nếu nhận được) ------|
      |                                       |-- afterCommit/afterCompletion --------|
      |<---- return hoặc exception -----------|                                         |
      |-- tạo HTTP response cho client        |                                         |
```

**Điểm dễ nhầm:** câu lệnh `return` trong `@Transactional` chỉ kết thúc phần thân Java; nó chưa nhất thiết đưa kết quả tới người gọi. Spring còn phải hoàn tất transaction rồi proxy mới trả kết quả. Với `@Transactional(propagation = REQUIRED)` tham gia transaction đang có, method bên trong cũng có thể kết thúc trước khi **transaction vật lý của scope bên ngoài** commit.

Tùy transaction manager (JDBC, JPA, JTA...), một số lệnh SQL có thể được gửi sớm; các thay đổi JPA được trì hoãn đến `flush` hoặc commit; constraint hay deadlock có thể chỉ xuất hiện muộn. Do đó, “không lỗi trong business method” chưa đảm bảo commit thành công.

### 2.1. Ba mốc khác nhau

1. **Phần thân nghiệp vụ kết thúc:** method có thể trả kết quả, nhưng transaction interceptor chưa hoàn tất.
2. **CSDL quyết định commit/rollback:** trạng thái lưu bền của dữ liệu được quyết định theo cơ chế CSDL.
3. **Phía gọi nhận được xác nhận:** kết quả của transaction manager, HTTP server hoặc client. Một phản hồi có thể bị lỗi/mất sau khi dữ liệu đã được commit.

Không có một phép kiểm `catch(Exception)` đơn giản nào biến ba mốc này thành một sự kiện nguyên tử. Mất phản hồi khác với rollback.

### 2.2. Ví dụ một thanh toán hoặc ghi có

Client gửi yêu cầu `credit(account=1, amount=100, operationId="op-001")`. Server ghi tăng số dư và lưu bản ghi kết quả, rồi database commit. Đúng lúc DB phản hồi `COMMIT`, mạng bị ngắt:

- Nếu commit chưa được DB chấp nhận, giao dịch có thể bị rollback khi connection bị hủy.
- Nếu DB đã chấp nhận commit nhưng **ACK bị mất**, dữ liệu đã tồn tại dù server thấy lỗi.
- Nếu server đã nhận ACK nhưng **HTTP response bị mất**, client cũng không biết yêu cầu của mình thành công.

Chỉ từ một timeout hay lỗi kết nối phía caller **không thể suy ra** nhánh nào đã xảy ra. Việc lập tức gửi lại một yêu cầu không định danh có thể nhân đôi thao tác.

## 3. Phân loại kết quả theo chứng cứ, không theo cảm giác

| Tình huống | Có thể kết luận gì? | Hành động phù hợp |
| --- | --- | --- |
| Validate dữ liệu thất bại trước khi bắt đầu transaction và chắc chắn chưa ghi | Chưa thực hiện thay đổi ở transaction này | Báo lỗi đầu vào; không retry mù quáng |
| Spring biết transaction bị đánh dấu rollback-only và đã rollback | Rollback đã xảy ra trong phạm vi giao dịch ấy | Sửa nguyên nhân; retry có kiểm soát nếu phù hợp |
| CSDL phản hồi commit thành công, application nhận xác nhận | Commit đã thành công theo cam kết của tài nguyên | Trả trạng thái thành công hoặc tiếp tục quy trình sau commit |
| Driver ném lỗi giữa `Connection.commit()` / coordinator mất liên lạc | **Có thể chưa xác định** nếu không có chứng cứ DB chắc chắn | Gắn trạng thái tạm “unknown”, xác minh bằng operation ID |
| `afterCommit()` ném lỗi, hoặc lỗi gửi HTTP response sau khi transaction đã hoàn tất | Transaction chính **có thể đã commit**; với `afterCommit()` đã vào callback là commit thành công | Không coi exception là bằng chứng rollback; tra cứu trạng thái |
| Client timeout sau khi gửi request | Client không biết server đã xử lý đến đâu | Tra cứu và retry bằng **cùng idempotency key** |

Phải đánh giá **đúng lỗi và transaction manager cụ thể**. Không được nói rằng **mọi** exception ở `commit` đều tạo kết quả UNKNOWN. Ví dụ, Spring có thể ném `UnexpectedRollbackException` khi transaction được đánh dấu rollback-only và rollback thay vì commit. Còn `TransactionSystemException` có thể bọc lỗi tài nguyên/commit; cần xem nguyên nhân gốc, tín hiệu từ DB và log. Lỗi constraint phát sinh khi flush có thể dẫn đến rollback rõ ràng; lỗi mất kết nối ngay thời điểm commit có thể không đủ thông tin.

Đặc biệt với các tài nguyên có nhiều participant hoặc coordinator, có thể tồn tại trạng thái heuristic/mixed; không áp dụng suy luận của local JDBC transaction cho mọi hệ thống. Trong một transaction DB đơn lẻ, nguyên tử ở phía DB **không giải quyết được** sự không chắc chắn của client về ACK.

### 3.1. Phân biệt “transaction thành công” và “request thành công”

Transaction DB có thể commit, nhưng request HTTP bị trả mã 500 vì thao tác **sau commit** như cập nhật cache, gọi hệ thống ngoài hoặc ghi response gặp lỗi. Ngược lại, một server có thể gửi thông báo thành công quá sớm khi công việc thực tế vẫn ở queue. Hợp đồng API phải chỉ rõ kết quả nào được đảm bảo và cách tra cứu.

### 3.2. “Không tìm thấy bản ghi” chưa luôn nghĩa là thất bại

Ngay sau timeout, truy vấn trạng thái có thể đọc replica đang trễ hoặc thao tác gốc vẫn đang chạy ở server khác. Không thấy `operationId` ở một nơi đọc không đủ để tuyên bố rollback. Nên đọc nguồn dữ liệu có bảo đảm nhất quán thích hợp, xem trạng thái xử lý, áp dụng khoảng chờ/retry hữu hạn, và có đường chuyển đến đối soát hoặc hỗ trợ vận hành nếu chưa thể kết luận.

## 4. Exception của Spring ở đâu trong quá trình commit?

Trong Spring Framework, `PlatformTransactionManager` quản lý `getTransaction`, `commit` và `rollback`. Với Spring Boot + JDBC, manager thường quản lý transaction trên JDBC connection lấy từ `DataSource`. Với JPA, flush có thể xảy ra khi commit. Transaction manager hoàn tất/dọn scope kể cả khi lệnh `commit` ném lỗi; **đừng gọi rollback trên cùng TransactionStatus sau một lần commit bị lỗi** và kỳ vọng đảo ngược được commit đã hoàn tất.

Các nhóm dấu hiệu thường gặp:

- **`UnexpectedRollbackException`:** một scope `REQUIRED` phía trong đã đánh dấu rollback-only, scope ngoài tưởng có thể commit nhưng manager rollback. Spring chủ ý báo lỗi để caller không nhầm đó là commit.
- **`TransactionSystemException`:** lỗi cấp hệ thống/transaction manager; cần xem `cause`, trạng thái commit thực và thông tin từ DB.
- **`DataAccessException` / lỗi ràng buộc trong flush/commit:** có thể do SQL hoặc ORM đồng bộ dữ liệu muộn; riêng loại lỗi này không đủ để xác nhận UNKNOWN, phải xem DB đã kết thúc ra sao.
- **`HeuristicCompletionException`:** dấu hiệu coordinator quyết định kết quả heuristic trong môi trường hỗ trợ kiểu giao dịch đó; có thể cần điều tra trạng thái thành phần.
- **Exception từ `TransactionSynchronization.afterCommit()`:** callback chạy sau khi main transaction đã commit. Runtime exception từ `afterCommit` có thể truyền tới caller, dù phần dữ liệu đã ghi không thể tự bị callback đó rollback.

Ví dụ tưởng tượng:

```java
@Transactional
public Receipt pay(Command command) {
    savePayment(command);
    return new Receipt("ACCEPTED");
}
```

Mã trên chỉ là minh họa, thiếu định nghĩa `Receipt`, `Command` và `savePayment`. `return` không đảm bảo caller đã nhận `Receipt`: interceptor còn có giai đoạn commit/after-commit. Không nên bao `@Transactional` chỉ quanh code trong controller rồi gửi “success” trước khi transaction thực sự hoàn tất.

**Ngoại lệ đáng chú ý về proxy:** nếu phương thức `@Transactional` bị gọi nội bộ qua `this.method()` trong cùng bean thì với proxy mode mặc định advice có thể không chạy. Nếu service tham gia transaction ở ngoài, commit xảy ra ở scope ngoài. Khi phân tích lỗi, phải biết transaction **nào** và **ai** thực sự sở hữu bước commit.

## 5. Vì sao retry trực tiếp có thể gây sai dữ liệu?

Hãy xem một API “cộng 100”:

```sql
UPDATE wallet SET balance = balance + 100 WHERE id = 1;
```

Lệnh này **không idempotent**: thực hiện hai lần tạo hiệu ứng cộng 200. Nếu lần đầu đã commit mà phản hồi mất, retry mù quáng khiến số dư sai.

Trong khi đó, thao tác có `operationId` bền vững có thể định nghĩa: **một ý định nghiệp vụ xác định chỉ được ghi nhận một lần**, dù client gửi nhiều request:

```text
Client giữ nguyên operationId = op-001
      |
      v
Server bắt đầu transaction
      |
      +--> Kiểm tra operationId đã có kết quả chưa?
      |       +-- Có, cùng tham số: trả kết quả cũ (không cộng thêm)
      |       +-- Có, khác tham số: từ chối trùng khóa sai mục đích
      |
      +--> Chưa có: cập nhật số dư + lưu operationId với kết quả
                  (cùng MỘT transaction DB)
      |
      v
Commit: thành công hoặc phản hồi không chắc chắn
      |
      +--> Nếu response mất: client tra cứu / gửi lại CÙNG operationId
```

**Idempotency key** không phải cờ trong RAM. Nó cần được giữ ổn định theo ý định nghiệp vụ và được bảo vệ bằng constraint unique của DB hoặc cơ chế đồng bộ tương đương. Nên lưu cả định danh, tham số cốt lõi (hoặc hash chuẩn hóa), trạng thái và kết quả cần trả. Yêu cầu cùng key nhưng payload khác phải bị từ chối, tránh dùng lại key cho ý định khác.

### 5.1. Bất biến khi ghi trên một CSDL

Trong **một local DB transaction**, thao tác tài chính và bản ghi nhận diện operation được commit cùng nhau:

```text
BEGIN
    UPDATE wallet SET balance = balance + amount WHERE id = accountId;
    INSERT INTO credit_operation(operation_id, amount, state) VALUES (...);
COMMIT
```

Nếu rollback, cả cập nhật số dư và kết quả operation đều mất. Nếu commit, cả hai tồn tại. Truy vấn operation đã commit giúp phân biệt “đã áp dụng” khi ACK ban đầu bị mất. Với cạnh tranh đồng thời, `UNIQUE(operation_id)`/khóa chính là hàng rào cuối cùng: pattern “SELECT thấy chưa có rồi INSERT” tự nó **không đủ chống race**.

Lưu ý rằng bảo đảm này chỉ áp dụng cho những thay đổi **cùng tham gia transaction CSDL ấy**. Gọi cổng thanh toán, gửi email, hay publish trực tiếp vào broker khác không tự nằm trong commit của DB.

### 5.2. Không coi “retry có key” là lời hứa không cần giới hạn

Client cần deadline, timeout, exponential backoff + jitter, tối đa số lần thử và đường đối soát khi trạng thái kéo dài. Key phải có định dạng/tính duy nhất đủ tốt, thời gian lưu phù hợp nghiệp vụ và bảo vệ khỏi đoán/chiếm dụng. Nếu xóa bảng key quá sớm rồi client retry sau hạn, hiệu ứng trùng có thể quay lại. Với thanh toán, có thể cần giữ business ID/ledger bền hơn cache idempotency ngắn hạn.

## 6. Ví dụ chạy được: exception sau commit nhưng dữ liệu vẫn tồn tại

**Mục đích bài chạy:** tái hiện một trạng thái dễ bị hiểu nhầm: caller nhận `IllegalStateException` nhưng DB **đã commit thành công**; lần gửi lại với cùng `operationId` không cộng tiền lần hai.

Chương trình dùng Java 17+, Spring Boot 3.5.16, Spring JDBC và H2 in-memory. Chỉ có **một DB**, một bean service được Spring quản lý và một `CommandLineRunner` gọi service qua proxy. Ví dụ cố ý ném exception ở `TransactionSynchronization.afterCommit()`. Đây là **mô phỏng chắc chắn lỗi sau commit**, **không** phải tái tạo sự cố mất ACK của lệnh `Connection.commit()`; cách xử lý trạng thái UNKNOWN của lỗi vật lý sẽ bàn tiếp ở phần sau.

### 6.1. Các tệp của dự án

```text
commit-outcome-demo/
├── settings.gradle
├── build.gradle
└── src/main/
    ├── java/example/commit/
    │   ├── CommitOutcomeApplication.java
    │   └── CreditService.java
    └── resources/
        ├── schema.sql
        └── data.sql
```

**`settings.gradle`**

```groovy
rootProject.name = 'commit-outcome-demo'
```

**`build.gradle`**

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.16'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'example.commit'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

tasks.withType(JavaCompile).configureEach {
    options.encoding = 'UTF-8'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-jdbc'
    runtimeOnly 'com.h2database:h2'
}
```

Cần JDK 17+, Gradle 8.x tương thích với Spring Boot 3.5; ví dụ không yêu cầu web server. Bản phát hành được ghim để có thể tái hiện; dự án triển khai thật cần theo nhánh Spring Boot còn được hỗ trợ.

**`src/main/resources/schema.sql`**

```sql
CREATE TABLE wallet (
    id BIGINT PRIMARY KEY,
    balance BIGINT NOT NULL CHECK (balance >= 0)
);

CREATE TABLE credit_operation (
    operation_id VARCHAR(64) PRIMARY KEY,
    account_id BIGINT NOT NULL REFERENCES wallet(id),
    amount BIGINT NOT NULL CHECK (amount > 0),
    state VARCHAR(16) NOT NULL CHECK (state = 'SUCCEEDED')
);
```

**`src/main/resources/data.sql`**

```sql
INSERT INTO wallet (id, balance) VALUES (1, 1000);
```

Một `operation_id` chỉ có thể tồn tại một lần nhờ PRIMARY KEY. Việc tăng số dư và chèn `credit_operation` phải nằm trong cùng transaction; nếu chèn bị lỗi (kể cả trùng key đồng thời), cập nhật số dư của **lần gọi lỗi** phải rollback.

### 6.2. Service thực hiện và ghi nhận một thao tác

**`src/main/java/example/commit/CreditService.java`**

```java
package example.commit;

import java.util.List;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.transaction.support.TransactionSynchronization;
import org.springframework.transaction.support.TransactionSynchronizationManager;

@Service
public class CreditService {
    private final JdbcTemplate jdbc;

    public CreditService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional
    public String credit(
            String operationId,
            long accountId,
            long amount,
            boolean failAfterCommitForDemo) {

        if (operationId == null || operationId.isBlank()
                || operationId.length() > 64 || amount <= 0) {
            throw new IllegalArgumentException("Tham số không hợp lệ");
        }

        List<RecordedCredit> previous = jdbc.query(
            "SELECT account_id, amount FROM credit_operation WHERE operation_id = ?",
            (rs, row) -> new RecordedCredit(
                rs.getLong("account_id"), rs.getLong("amount")),
            operationId
        );

        if (!previous.isEmpty()) {
            RecordedCredit old = previous.get(0);
            if (old.accountId() != accountId || old.amount() != amount) {
                throw new IllegalArgumentException(
                    "operationId đã được dùng cho tham số khác");
            }
            return "ALREADY_SUCCEEDED";
        }

        int rows = jdbc.update(
            "UPDATE wallet SET balance = balance + ? WHERE id = ?",
            amount, accountId
        );
        if (rows != 1) {
            throw new IllegalArgumentException("Tài khoản không tồn tại");
        }

        jdbc.update(
            "INSERT INTO credit_operation " +
            "(operation_id, account_id, amount, state) " +
            "VALUES (?, ?, ?, 'SUCCEEDED')",
            operationId, accountId, amount
        );

        if (failAfterCommitForDemo) {
            TransactionSynchronizationManager.registerSynchronization(
                new TransactionSynchronization() {
                    @Override
                    public void afterCommit() {
                        throw new IllegalStateException(
                            "Mất phản hồi sau commit (mô phỏng)");
                    }
                }
            );
        }

        return "SUCCEEDED";
    }

    private record RecordedCredit(long accountId, long amount) {}
}
```

Giải thích thứ tự:

1. `@Transactional` mở/đưa method vào transaction khi gọi qua Spring proxy.
2. Nếu `operationId` đã có và tham số trùng, trả `ALREADY_SUCCEEDED` mà không cập nhật số dư.
3. Nếu chưa có, cập nhật số dư và tạo bản ghi kết quả trong **cùng transaction**.
4. Với chế độ demo, đăng ký `afterCommit` ném `IllegalStateException`. Sau khi `credit` trả khỏi phần thân, Spring commit DB trước, rồi callback ném lỗi tới người gọi.
5. Do đó, dù caller bắt exception, cả hai thay đổi SQL đã commit. Lần gửi lại cùng khóa đọc `credit_operation` và tránh cộng lặp.

**Giới hạn concurrency:** hai lời gọi cùng `operationId` có thể cùng thấy chưa có ở bước SELECT. Khóa chính sẽ chặn việc **cả hai** chèn thành công; lời gọi bị trùng phải rollback toàn bộ transaction của nó. Trong môi trường thật, cần chuyển lỗi unique/transient conflict sang chính sách “kết thúc transaction lỗi → tra cứu trạng thái bằng transaction mới → có thể trả kết quả cũ”; không nuốt exception insert rồi tiếp tục dùng connection/transaction đã lỗi. Ví dụ này minh họa retry **tuần tự**, không tự giải quyết toàn bộ tranh chấp đồng thời.

### 6.3. Caller nhận lỗi nhưng đọc thấy dữ liệu đã commit

**`src/main/java/example/commit/CommitOutcomeApplication.java`**

```java
package example.commit;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.jdbc.core.JdbcTemplate;

@SpringBootApplication
public class CommitOutcomeApplication {
    public static void main(String[] args) {
        SpringApplication.run(CommitOutcomeApplication.class, args);
    }

    @Bean
    CommandLineRunner demo(CreditService service, JdbcTemplate jdbc) {
        return args -> {
            try {
                service.credit("op-001", 1L, 100L, true);
                System.out.println("Lần đầu: thành công");
            } catch (IllegalStateException ex) {
                System.out.println("Lần đầu: " + ex.getMessage());
            }

            System.out.println("Số dư sau lỗi: " + balance(jdbc));
            System.out.println("Trạng thái operation: " +
                jdbc.queryForObject(
                    "SELECT state FROM credit_operation " +
                    "WHERE operation_id = ?",
                    String.class, "op-001"));

            System.out.println("Gửi lại: " +
                service.credit("op-001", 1L, 100L, false));
            System.out.println("Số dư cuối: " + balance(jdbc));
        };
    }

    private static Long balance(JdbcTemplate jdbc) {
        return jdbc.queryForObject(
            "SELECT balance FROM wallet WHERE id = 1", Long.class);
    }
}
```

Spring Boot tự chạy `schema.sql`, `data.sql` với H2 embedded khi khởi động. Đứng tại thư mục `commit-outcome-demo` và chạy Gradle 8.x:

```bash
gradle bootRun
```

Nếu đã tạo Gradle Wrapper phù hợp thì dùng `./gradlew bootRun` (Linux/macOS) hoặc `gradlew.bat bootRun` (Windows). Bỏ qua log framework, **năm dòng từ chương trình** có nội dung:

```text
Lần đầu: Mất phản hồi sau commit (mô phỏng)
Số dư sau lỗi: 1100
Trạng thái operation: SUCCEEDED
Gửi lại: ALREADY_SUCCEEDED
Số dư cuối: 1100
```

**Vì sao kết quả này đáng chú ý?**

- Caller bắt `IllegalStateException`, nhưng số dư tăng từ 1000 lên 1100; `credit_operation` chứa `op-001`. Exception đã xảy ra **sau commit**.
- Retry cùng `op-001` và cùng payload chỉ trả lại kết quả, số dư **không** trở thành 1200.
- Nếu client tạo `op-002` cho cùng ý định khi retry, DB sẽ coi đó là **nghiệp vụ mới** và có thể cộng thêm 100.
- `failAfterCommitForDemo` là công tắc thử nghiệm; không nên đưa cờ như thế vào nghiệp vụ sản xuất.

Bài thử tái hiện **caller thấy lỗi dù kết quả DB đã thành công**; nó **không chứng minh** rằng mọi exception từ JDBC `commit` đều là commit thành công. Muốn thử lỗi “không biết ACK commit” thực sự cần can thiệp mạng/DB/proxy ở thời điểm chính xác, thu thập bằng chứng và xử lý được cả hai kết quả.

## 7. Thiết kế response và state machine cho một kết quả chưa xác định

Một hệ thống cần tách **trạng thái xử lý nội bộ** khỏi **trạng thái quan sát được ở client**. Có thể định nghĩa:

- `SUCCEEDED`: có bằng chứng giao dịch nghiệp vụ đã commit theo nguồn dữ liệu đáng tin.
- `FAILED`: có bằng chứng thao tác bị từ chối hoặc rollback trước khi có hiệu ứng, và không còn xử lý song song có thể commit.
- `PENDING`: yêu cầu đã được nhận hoặc đang xử lý; chưa có kết quả cuối.
- `UNKNOWN`: phía quan sát mất tín hiệu xác nhận, chưa đủ cơ sở gán `SUCCEEDED` hay `FAILED`.

Đây là **mô hình xử lý** gợi ý, không phải bộ enum có sẵn được Spring tự động lưu. Một record “PENDING” được ghi ở transaction khác có thể tồn tại ngay cả khi thao tác nghiệp vụ chưa commit; phải định nghĩa rõ nguồn sự thật. Thường có thể dùng DB operation record như ở ví dụ, hoặc một ledger/trạng thái workflow được cập nhật bằng giao dịch tương ứng.

### 7.1. API gợi ý

```http
POST /credits
Idempotency-Key: op-001
Content-Type: application/json

{"accountId": 1, "amount": 100}
```

Nếu transaction đã xác nhận commit, server có thể trả `200 OK` hoặc `201 Created` với `operationId` và trạng thái. Nếu xử lý còn đang diễn ra, `202 Accepted` cùng vị trí tra cứu là hợp lý. Nếu server chưa biết kết quả vì timeout nội bộ, nó nên phản ánh sự **chưa chắc chắn** theo hợp đồng API, không tự khẳng định đã rollback; nếu còn kết nối với client, có thể trả thông tin cho phép client tiếp tục tra cứu. Nếu mất kết nối hoàn toàn, client cần tự giữ `operationId`.

```http
GET /operations/op-001
```

Trả dữ liệu trạng thái lấy từ nguồn đáng tin và áp dụng chính sách truy cập phù hợp. Khi thấy `SUCCEEDED` với payload khớp, client dừng retry hiệu ứng nghiệp vụ. Khi chưa kết luận, giữ nguyên key để thử lại **cùng ý định**, hoặc chuyển cho tiến trình đối soát. Không lấy một mã HTTP duy nhất làm kết luận về commit nếu lỗi xảy ra sau phần xử lý DB.

### 7.2. Pseudocode xử lý retry (mang tính thiết kế)

```text
operationId = ID ổn định do client tạo cho MỘT ý định
payload     = dữ liệu bất biến cho ý định đó

gửi POST với operationId và payload
  nếu được xác nhận SUCCEEDED:
      hoàn tất
  nếu thất bại vĩnh viễn đã xác nhận:
      thông báo lỗi có chứng cứ
  nếu timeout / mất response / server báo chưa rõ:
      tra GET status theo operationId trên nguồn đọc phù hợp
      nếu SUCCEEDED:
          hoàn tất, KHÔNG thực hiện thao tác mới
      nếu PENDING/UNKNOWN hoặc tạm thời không đọc được:
          backoff + jitter, tiếp tục tra cứu hoặc gửi lại
          CHÍNH operationId + payload đó
      nếu quá ngưỡng:
          chuyển sang đối soát/cảnh báo, KHÔNG tự tạo operationId mới
```

Không tự động dùng `REQUIRES_NEW` để “xác nhận” một giao dịch vừa lỗi: transaction độc lập có thể tạo record gây hiểu nhầm hoặc ghi dấu “FAILED” trong khi giao dịch gốc đã commit. Trạng thái đối soát cần được thiết kế theo **độ tin cậy của nguồn dữ liệu**.

## 8. Khi nào biết chắc rollback, khi nào phải đối soát?

### 8.1. Trường hợp đã rollback xác nhận

Với một `UnexpectedRollbackException` thông thường do rollback-only trong transaction do manager quản lý, Spring báo rằng commit không diễn ra, transaction đã rollback. Một lỗi nghiệp vụ được ném trước commit và được manager rollback thành công cũng có kết quả được biết rõ. Tuy nhiên, phải bảo đảm có bằng chứng rollback đã hoàn tất, không chỉ “đã gọi hàm rollback”.

**Không gộp mọi exception vào UNKNOWN**: điều đó khiến hệ thống chờ/đối soát không cần thiết.

### 8.2. Trường hợp lỗi tại lệnh COMMIT thực sự

Giả sử JDBC driver gửi lệnh `COMMIT`, DB đã ghi log commit, nhưng kết nối rơi trước khi driver đọc ACK. Ở phía Spring có thể thấy exception nhưng không thể đảo ngược dữ liệu đã commit bằng một lệnh `rollback` mới. Phải tra cứu hiệu ứng bền vững sau khi kết nối phục hồi, dựa vào business operation ID, transaction ledger hoặc nguồn đối soát phù hợp.

Ngược lại, nếu DB chắc chắn trả về lỗi constraint trong giai đoạn flush trước commit và transaction rollback thành công, outcome khác với ví dụ ACK thất lạc. Phân tích cần **timestamp, transaction ID nếu có, stack trace gốc, driver, DB logs và trạng thái dữ liệu**. Một chuỗi thông báo như “commit failed” tự nó không đủ.

### 8.3. Transaction có nhiều tài nguyên

Local `@Transactional` với một `DataSourceTransactionManager`/JPA transaction manager không đồng nghĩa “cập nhật DB + publish Kafka + gửi email” cùng commit. Nếu bước ngoài DB thành công còn DB không thành công, hoặc ngược lại, có thể xảy ra trạng thái từng phần. Với business event, một cách thường dùng là **transactional outbox**: lưu business state và outbox event trong cùng transaction DB; worker phát thông điệp sau đó, consumer deduplicate bằng event ID. Outbox thường cung cấp delivery có thể lặp nên listener vẫn cần idempotency.

Nếu dùng JTA/XA nhiều tài nguyên, lỗi heuristic hoặc mất liên lạc coordinator đòi hỏi quy trình phục hồi và đối soát riêng. Đừng tự suy diễn status tất cả participant chỉ từ exception phía một service.

## 9. Những lỗi vận hành thường gặp

**Lỗi 1 — Tự động retry mỗi exception.** Khi kết quả có thể đã commit, một lệnh `UPDATE balance = balance + amount` chạy lại gây tác dụng hai lần. Khắc phục: operationId ổn định, lưu kết quả cùng transaction, tra cứu trạng thái và chỉ retry an toàn.

**Lỗi 2 — Tự tạo idempotency key mới cho mỗi lần gửi.** Bên server thấy các yêu cầu khác nhau và không thể nhận ra cùng business intent. Khắc phục: client/producer sinh ID một lần và giữ qua timeout/restart, gắn payload cố định.

**Lỗi 3 — `SELECT` trước `INSERT` là đủ chống trùng.** Hai thread có thể cùng thấy chưa tồn tại. Khắc phục: khóa unique trong DB và chiến lược xử lý conflict/rollback/re-query; không cố tiếp tục transaction sau khi SQL báo lỗi.

**Lỗi 4 — Catch exception ở controller rồi ghi “FAILED”.** Nếu exception đến từ `afterCommit`, hiệu ứng đã thành công. Khắc phục: phân loại có chứng cứ, dùng trạng thái UNKNOWN khi chưa rõ.

**Lỗi 5 — Ghi dấu thành công ở transaction khác.** Bản ghi trạng thái có thể không còn đồng nhất với cập nhật nghiệp vụ nếu hai transaction có kết quả khác nhau. Khắc phục: cập nhật business effect và operation record atomically trên cùng DB; phần ngoài DB có quy trình riêng.

**Lỗi 6 — Gửi thông báo ngoài DB ngay trước commit.** Email/webhook có thể đã đến trong khi DB rollback. Khắc phục: after-commit cho tác vụ chấp nhận mất thông báo theo điều kiện cụ thể; nếu cần độ tin cậy cao, ưu tiên outbox và consumer idempotent. `afterCommit` không phải durable queue; lỗi ở callback không tự rollback main transaction.

**Lỗi 7 — Chỉ đọc replica ngay sau timeout.** Replica có thể chưa nhận commit. Khắc phục: endpoint kiểm tra đọc nguồn phù hợp với bảo đảm consistency, hoặc báo kết quả chưa thể kết luận thay vì “không tồn tại”.

**Lỗi 8 — Tự bù trừ ngay vì thấy timeout.** Nếu tiền đã cộng mà sau đó tự trừ trong lúc retry khác đang chạy, nghiệp vụ càng khó kiểm soát. Khắc phục: đối soát trước; compensation phải là nghiệp vụ có ID, nhật ký và quy tắc riêng.

**Lỗi 9 — Log thiếu khóa tương quan.** Không thể nối request đầu, retry, transaction exception và record đã commit. Khắc phục: log `operationId`, correlation ID, thời điểm lỗi, kết quả truy vấn, transaction manager, nhưng tránh ghi dữ liệu nhạy cảm vào log.

## 10. Kiểm thử và quan sát để chứng minh thiết kế

Kiểm thử nên phân biệt bốn nhóm:

1. **Rollback đã biết:** đưa lỗi runtime trước commit, kiểm tra bảng business và operation đều không thay đổi sau khi scope kết thúc.
2. **Commit thành công:** cùng `operationId` và payload phải ghi đúng một effect, lần gọi lặp trả kết quả cũ; payload khác phải bị từ chối.
3. **Lỗi sau commit:** như `afterCommit` trong demo; xác nhận caller thấy exception nhưng DB chứa hiệu ứng và receipt. Retry cùng key không lặp hiệu ứng.
4. **Lỗi tại commit / mất ACK thật:** trong môi trường integration có DB thật, fault-injection/network proxy phù hợp; cần thử cả khả năng commit và rollback rồi đối soát. Không thể giả lập trung thực chỉ bằng `throw new RuntimeException()` ở cuối business method.

Thử **concurrency** với nhiều request cùng key và cùng amount để chắc chắn một effect duy nhất; thử key giống nhưng amount khác; thử restart, retry nhiều lần, timeout và khóa hết hạn. Nếu cần đối soát sau mất kết nối, kiểm tra rằng endpoint trạng thái không trả “FAILED” quá sớm khi một lần gọi vẫn có thể hoàn tất. Với tài nguyên ngoài DB, thử event trùng và phát lại outbox.

Trong Spring Test, một test gắn `@Transactional` thường tự rollback khi kết thúc. Nếu kiểm tra “commit đã xảy ra”, đừng để transaction của test bao quanh toàn bộ lần gọi rồi kết luận từ trạng thái tạm; có thể dùng test không transactional hoặc `TestTransaction` để điều khiển kết thúc transaction, sau đó đọc trạng thái DB mới.

Chỉ số vận hành nên gắn với hành động: số lượng commit/after-commit failures, các operation UNKNOWN quá thời hạn, số idempotency conflicts (cùng key khác payload), thời gian đối soát, số event retry và kết quả reconciled. Nếu không có quy trình xử lý UNKNOWN, việc đơn thuần bắt exception rồi log “failed” là chưa đủ.

## 11. Checklist xử lý sự cố tại thời điểm commit

Khi nhận một lỗi gần thời điểm commit:

- **Xác định phạm vi:** method nào là transaction owner, propagation gì, transaction manager và tài nguyên nào tham gia?
- **Xác định điểm lỗi:** SQL/flush/beforeCommit, chính lệnh commit, afterCommit, hay phản hồi HTTP sau commit?
- **Xác định chứng cứ:** DB xác nhận commit/rollback, Spring rollback-only, mã lỗi/`cause` của driver, operation record, database log?
- **Nếu chưa đủ chứng cứ:** đánh dấu outcome UNKNOWN ở góc nhìn caller, **không mặc định rollback**.
- **Chặn nhân đôi:** giữ nguyên operationId và payload, dùng unique constraint và transaction chứa cả effect/receipt.
- **Đối soát:** đọc nguồn dữ liệu đủ consistency, xử lý in-flight, đặt giới hạn chờ và escalation.
- **Mở rộng sang ngoài DB:** outbox, delivery trùng, idempotent consumer hoặc workflow trạng thái nhiều bước.
- **Xác minh:** chạy ca commit success, known rollback, after-commit failure, lost response và concurrent duplicate.

## 12. Câu hỏi tự kiểm tra

**Câu 1.** `@Transactional` method chạy hết và trả `"OK"` nhưng caller nhận `TransactionSystemException`. Có chắc đã rollback?  
**Trả lời:** Không. Phần thân có thể kết thúc trước khi commit. Cần biết lỗi từ giai đoạn nào và có bằng chứng DB commit/rollback hay chưa; nếu không, coi outcome là chưa xác định.

**Câu 2.** Khi nào `UnexpectedRollbackException` thường có ý nghĩa cụ thể hơn một lỗi mất kết nối tại `COMMIT`?  
**Trả lời:** Với tình huống rollback-only chuẩn của Spring, manager chủ động rollback và báo lỗi để caller không hiểu lầm đã commit. Trong sự cố mất ACK tại COMMIT, caller có thể không biết DB đã chấp nhận commit hay chưa.

**Câu 3.** Nếu server gửi lỗi HTTP 500 sau khi `afterCommit` ném exception, client có nên gửi lại yêu cầu cộng tiền với operation ID mới?  
**Trả lời:** Không. Một phần dữ liệu đã commit có thể đã tồn tại; cần tra cứu và giữ **cùng operationId** cho cùng ý định.

**Câu 4.** Tại sao vẫn cần `PRIMARY KEY(operation_id)` nếu code đã `SELECT` kiểm tra key?  
**Trả lời:** Hai request đồng thời có thể cùng đọc “chưa có”; ràng buộc unique do DB thực thi bảo đảm chúng không cùng ghi receipt với cùng ID. Cần rollback/đọc lại sau conflict.

**Câu 5.** Ví dụ `afterCommit` chứng minh được điều gì và không chứng minh điều gì?  
**Trả lời:** Chứng minh exception có thể đến caller **sau khi main transaction đã commit**. Nó không mô phỏng lỗi kết nối ngay trong `Connection.commit()`, nên không kết luận mọi commit exception đều có kết quả thành công.

## Tài liệu tham khảo

- Spring Framework — Declarative transaction management: https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative.html
- Spring Framework — Transaction propagation và `UnexpectedRollbackException`: https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-propagation.html
- Spring Framework 6.1 Javadoc — `PlatformTransactionManager.commit`: https://docs.spring.io/spring-framework/docs/6.1.21/javadoc-api/org/springframework/transaction/PlatformTransactionManager.html
- Spring Framework 6.1 Javadoc — `TransactionSynchronization.afterCommit`: https://docs.spring.io/spring-framework/docs/6.1.21/javadoc-api/org/springframework/transaction/support/TransactionSynchronization.html
- Spring Boot — Database initialization: https://docs.spring.io/spring-boot/how-to/data-initialization.html

**Điểm cần nhớ:** Exception không phải là chứng từ rollback. Một transaction có thể đã commit khi caller nhận lỗi; nếu không biết kết quả, giải pháp là **giữ nguyên định danh nghiệp vụ, tra cứu trạng thái đáng tin, thiết kế idempotency và đối soát**, không lặp lại tác dụng phụ theo phỏng đoán.