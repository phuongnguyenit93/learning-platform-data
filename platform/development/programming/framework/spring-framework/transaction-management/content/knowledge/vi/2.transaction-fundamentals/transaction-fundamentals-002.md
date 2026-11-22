# Begin, commit, rollback và trạng thái kết thúc của transaction trong Spring Framework

## 1. Giao dịch bắt đầu và kết thúc ở đâu?

**Transaction (giao dịch)** gom một nhóm thao tác trên tài nguyên hỗ trợ giao dịch (thường là cơ sở dữ liệu) thành một đơn vị xử lý: hoặc các thay đổi hợp lệ được **commit**, hoặc các thay đổi còn nằm trong giao dịch được **rollback**. Ví dụ chuyển 200 đơn vị từ tài khoản A sang B phải trừ A và cộng B trong cùng giao dịch; không thể chấp nhận chỉ thực hiện một nửa.

Trong Spring, hãy phân biệt ba lớp:

| Lớp | Vai trò | Điều cần nhớ |
| --- | --- | --- |
| Lời gọi nghiệp vụ | Method service, JDBC/JPA thao tác dữ liệu | Thông thường không gọi SQL `BEGIN`/`COMMIT` trực tiếp |
| Ranh giới giao dịch của Spring | `@Transactional`, `TransactionTemplate` hoặc `PlatformTransactionManager` | Quyết định tạo mới, tham gia, commit hay rollback theo chính sách |
| Giao dịch vật lý của tài nguyên | JDBC connection, JPA transaction, JTA... | Database/resource thực sự xác nhận hay hủy các thay đổi |

Một **logical transaction scope** là phạm vi giao dịch theo một method/callback của Spring. Nhiều scope `PROPAGATION_REQUIRED` có thể dùng chung **một physical transaction**; vì vậy "method con kết thúc" chưa chắc nghĩa là database đã commit. Ngoài ra, một method mang `@Transactional` không mặc nhiên khởi tạo giao dịch mới: điều đó phụ thuộc propagation và transaction hiện tại.

Giả định chính của bài: xử lý **imperative/synchronous** bằng `PlatformTransactionManager` và tài nguyên JDBC/JPA. Với luồng reactive, Spring dùng `ReactiveTransactionManager` và Reactor Context; cơ chế gắn transaction với thread được nêu bên dưới không áp dụng nguyên xi.

## 2. Begin: tiến vào giao dịch

Với `@Transactional` theo cơ chế proxy thông thường, luồng chuẩn là:

1. Caller gọi **Spring bean qua proxy**; `TransactionInterceptor` đọc thuộc tính như propagation, isolation, timeout, readOnly và rollback rules.
2. Transaction manager nhận yêu cầu (`getTransaction(TransactionDefinition)` ở API imperative) và **tạo giao dịch mới, tham gia giao dịch hiện có, hoặc chạy không có giao dịch** theo propagation.
3. Khi tạo giao dịch vật lý JDBC, transaction manager sử dụng connection phù hợp, chuẩn bị các thuộc tính được hỗ trợ và điều khiển auto-commit; database có thể bắt đầu transaction theo cơ chế riêng. **Không đồng nhất "begin" với việc Spring luôn gửi một lệnh SQL `BEGIN`.**
4. Thao tác dữ liệu thực hiện trong phạm vi tài nguyên đã liên kết với giao dịch. Khi method/callback rời phạm vi, Spring quyết định hoàn tất hoặc bàn giao quyết định cho scope bên ngoài.

`PROPAGATION_REQUIRED` (mặc định) có nghĩa: chưa có transaction phù hợp thì tạo; đã có thì tham gia. `REQUIRES_NEW` yêu cầu giao dịch vật lý độc lập, tạm đình chỉ giao dịch ngoài khi hạ tầng hỗ trợ. `SUPPORTS` có thể chạy mà không có transaction; `NOT_SUPPORTED` cố ý không tham gia transaction. Vì vậy, gọi `getTransaction` hoặc chạy method `@Transactional` không phải bằng chứng rằng vừa mở một giao dịch vật lý mới.

Để kiểm tra từ API Spring imperative: `TransactionStatus.isNewTransaction()` cho biết scope đó có mở transaction mới theo manager hay không; `TransactionStatus.hasSavepoint()` cho biết scope lồng nhau dựa trên savepoint (nếu có). Các cờ này phục vụ quan sát, không thay thế kiểm chứng hành vi tài nguyên.

## 3. Commit: xác nhận thay đổi

Khi phần nghiệp vụ kết thúc **bình thường**, transaction advice thường yêu cầu commit. Trình tự ở mức khái niệm:

1. Spring kiểm tra transaction có bị đánh dấu **rollback-only** hay không.
2. Với giao dịch đủ điều kiện commit, các thao tác đồng bộ hóa/flush cần thiết có thể diễn ra trước commit (phụ thuộc JDBC, JPA, Hibernate và transaction manager).
3. Transaction manager yêu cầu tài nguyên commit. Chỉ khi resource xác nhận thành công mới có thể xem thay đổi của transaction vật lý là đã commit.
4. Spring chạy các callback hoàn tất phù hợp và dọn trạng thái giao dịch: giải phóng/trả connection, gỡ liên kết tài nguyên và khôi phục transaction đã tạm đình chỉ nếu có.

**Flush khác commit.** JPA/Hibernate có thể gửi SQL xuống database ở thời điểm flush, nhưng kết quả vẫn có thể bị rollback trước khi commit. Ràng buộc khóa ngoại/unique, deadlock, timeout hoặc lỗi kết nối có thể làm commit thất bại; "method chạy đến cuối" không bảo đảm dữ liệu đã được lưu vĩnh viễn.

Nếu scope chỉ **tham gia** một transaction `REQUIRED` đang tồn tại, yêu cầu commit của scope đó không commit vật lý ngay: transaction ngoài còn quyền quyết định kết quả. Nếu transaction đã bị đánh dấu rollback-only, lời gọi commit có thể dẫn đến rollback; một trường hợp điển hình là `UnexpectedRollbackException` khi transaction ngoài cố commit mà scope trong đã khiến giao dịch chung phải rollback.

Không đồng nhất một exception ném ra khỏi method với "chắc chắn rollback": nếu quy tắc rollback không khớp (ví dụ checked exception theo mặc định), Spring có thể commit rồi vẫn chuyển tiếp exception cho caller.

## 4. Rollback: hủy thay đổi của phạm vi giao dịch

Rollback yêu cầu tài nguyên bỏ những thay đổi **chưa commit** thuộc giao dịch vật lý. Ví dụ A vừa bị trừ 200 nhưng có lỗi trước khi cộng B: rollback trả các bản ghi có tham gia transaction về trạng thái trước giao dịch. Điều này không đảo ngược các side effect bên ngoài như email đã gửi, HTTP call, ghi file, hoặc một giao dịch khác đã commit; sequence/identity và DDL cũng có thể có hành vi riêng tùy database.

Spring có hai đường thường gặp:

- **Rollback do exception:** mặc định `@Transactional` rollback khi `RuntimeException` hoặc `Error` đi xuyên qua ranh giới được proxy quản lý. Checked `Exception` thường **không** kích hoạt rollback mặc định; dùng `@Transactional(rollbackFor = IOException.class)` hoặc chính sách thích hợp nếu nghiệp vụ cần.
- **Rollback theo quyết định chủ động:** code đánh dấu `TransactionStatus.setRollbackOnly()` hoặc sử dụng `PlatformTransactionManager.rollback(status)`. `setRollbackOnly()` chỉ ghi nhận quyết định, **không rollback ngay tại dòng gọi**; manager thực thi khi kết thúc phạm vi phù hợp.

Nếu code **bắt và nuốt** `RuntimeException` bên trong method `@Transactional` rồi trả về bình thường, proxy không nhìn thấy exception đó; kết quả có thể là commit trừ khi code đánh dấu rollback-only hoặc rethrow. Ngược lại, gọi một method annotated khác **bằng `this.method()` trong cùng bean** thường không đi qua proxy, nên annotation ở method được gọi không tự tạo ranh giới giao dịch mới trong proxy mode.

Lưu ý về rollback thủ công: `rollback(status)` đối với scope đã tham gia giao dịch bên ngoài có thể chỉ đánh dấu transaction chung rollback-only; nó không tùy ý "quay ngược phần riêng của method" khi các thao tác dùng chung physical transaction. Rollback một phần cần savepoint/`NESTED` nếu driver và transaction manager hỗ trợ.

## 5. Trạng thái và kết quả kết thúc

Sơ đồ dưới đây biểu diễn **logic điều khiển**, không phải một finite-state machine có tên state giống hệt API của mọi transaction manager.

~~~mermaid
flowchart TD
    A["Bên ngoài transaction"] --> B["Vào proxy / TransactionTemplate"]
    B --> C["Tạo mới hoặc tham gia transaction"]
    C --> D["Thực thi nghiệp vụ"]
    D --> E{"Kết thúc bình thường hoặc exception?"}
    E -->|Bình thường| F{"Rollback-only?"}
    E -->|"Exception theo rollback rule"| R["Yêu cầu rollback"]
    E -->|"Exception không theo rollback rule"| F
    F -->|Không| M["Yêu cầu commit"]
    F -->|Có| R
    M --> S["COMMITTED khi resource xác nhận"]
    M --> U["Commit thất bại / kết quả có thể chưa rõ"]
    R --> T["ROLLED_BACK khi rollback hoàn tất"]
    S --> X["Callback hoàn tất và cleanup"]
    U --> X
    T --> X
~~~

Các khái niệm dễ nhầm:

| Tên/cờ | Ý nghĩa đúng | Không nên suy ra |
| --- | --- | --- |
| Đang trong scope | Logic nghiệp vụ đang chạy trong ranh giới quản lý | Chắc chắn đang có **transaction vật lý mới** |
| `status.isRollbackOnly()` | Đã có yêu cầu không được commit như bình thường | Rollback đã xảy ra |
| `status.isCompleted()` | `TransactionStatus` này đã hoàn tất (commit/rollback ở mức scope do manager xử lý) | Biết chắc kết quả là committed hay rolled back; với scope tham gia, transaction vật lý ngoài cũng đã kết thúc |
| `status.isNewTransaction()` | Scope được manager xem là transaction mới | Mọi method con đều mở connection/transaction riêng |
| `TransactionSynchronization.STATUS_COMMITTED` | Callback `afterCompletion` nhận kết quả commit | Có thể dùng như cờ `isCommitted()` trên `TransactionStatus` (API không có cờ đó) |
| `TransactionSynchronization.STATUS_ROLLED_BACK` | Callback được thông báo rollback | Tự động hoàn tác tác dụng ngoài transaction |
| `TransactionSynchronization.STATUS_UNKNOWN` | Hạ tầng không thể xác định chắc trạng thái hoàn tất trong một số trường hợp | Có thể mặc định là rollback thành công |

Một `TransactionStatus` đã completed **không được** dùng lại để commit/rollback: các thao tác lặp có thể dẫn đến `IllegalTransactionStateException`. Khi `commit(status)` ném exception, transaction manager vẫn phải thực hiện quy trình hoàn tất/cleanup; **không gọi `rollback(status)` sau một commit đã được thử và ném lỗi**. Lỗi mạng lúc commit có thể đòi hỏi đối soát trạng thái thật của database, thay vì tự kết luận chắc chắn commit hoặc rollback.

Bốn tình huống để dự đoán kết quả:

| Diễn biến | Chính sách mặc định | Kết quả kỳ vọng |
| --- | --- | --- |
| Hai câu UPDATE thành công, method trả về bình thường, không rollback-only | `REQUIRED`, transaction mới | Commit cả hai |
| UPDATE thứ nhất thành công, sau đó ném `IllegalStateException` xuyên qua proxy | `RuntimeException` kích hoạt rollback | Không lưu UPDATE thứ nhất |
| UPDATE thành công rồi ném checked `IOException` xuyên qua proxy | Không có `rollbackFor` | Có thể commit dù caller nhận exception |
| Inner `REQUIRED` đánh dấu transaction chung rollback-only; outer bắt exception và cố commit | Một physical transaction dùng chung | Rollback toàn bộ; outer có thể nhận `UnexpectedRollbackException` |

Ở hàng cuối, `UnexpectedRollbackException` là cơ chế bảo vệ để caller không hiểu nhầm một yêu cầu commit đã thành công. Không nên viết code nghiệp vụ dựa vào assumption rằng mọi kiểu `setRollbackOnly()` đều nhất thiết ném exception; khác biệt local/global marker và vị trí scope có thể làm hành vi báo lỗi khác nhau.

## 6. Ví dụ chạy được: chứng minh rollback và commit bằng H2

Ví dụ Java 17+ dùng Spring Boot 3.3.x, Spring JDBC và H2 **chỉ để tạo môi trường chạy nhỏ**; nguyên lý transaction là của Spring Framework. Toàn bộ chương trình chạy với ba tệp sau, không cần server web. Hai method chuyển tiền được gọi qua **Spring bean** để `@Transactional` thực sự được áp dụng.

**`pom.xml`**

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>
    <groupId>example</groupId>
    <artifactId>tx-lifecycle</artifactId>
    <version>1.0.0</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-jdbc</artifactId>
        </dependency>
        <dependency>
            <groupId>com.h2database</groupId>
            <artifactId>h2</artifactId>
            <scope>runtime</scope>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
~~~

**`src/main/java/example/TxApplication.java`**

~~~java
package example;

import java.util.LinkedHashMap;
import java.util.Map;
import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.jdbc.core.JdbcTemplate;

@SpringBootApplication
public class TxApplication {
    public static void main(String[] args) {
        SpringApplication.run(TxApplication.class, args);
    }

    @Bean
    CommandLineRunner demo(JdbcTemplate jdbc, TransferService transfers) {
        return args -> {
            jdbc.execute("CREATE TABLE account (id INT PRIMARY KEY, balance INT NOT NULL)");
            jdbc.update("INSERT INTO account(id, balance) VALUES (?, ?)", 1, 1000);
            jdbc.update("INSERT INTO account(id, balance) VALUES (?, ?)", 2, 500);

            System.out.println("Ban đầu: " + balances(jdbc));
            try {
                transfers.transfer(1, 2, 200, true);
            } catch (IllegalStateException ex) {
                System.out.println("Đã bắt: " + ex.getMessage());
            }
            System.out.println("Sau rollback: " + balances(jdbc));

            transfers.transfer(1, 2, 200, false);
            System.out.println("Sau commit: " + balances(jdbc));
        };
    }

    private static Map<Integer, Integer> balances(JdbcTemplate jdbc) {
        return jdbc.query(
            "SELECT id, balance FROM account ORDER BY id",
            rs -> {
                Map<Integer, Integer> result = new LinkedHashMap<>();
                while (rs.next()) {
                    result.put(rs.getInt("id"), rs.getInt("balance"));
                }
                return result;
            }
        );
    }
}
~~~

**`src/main/java/example/TransferService.java`**

~~~java
package example;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class TransferService {
    private final JdbcTemplate jdbc;

    public TransferService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional
    public void transfer(int from, int to, int amount, boolean failAfterDebit) {
        if (amount <= 0) {
            throw new IllegalArgumentException("amount must be positive");
        }

        int debited = jdbc.update(
            "UPDATE account SET balance = balance - ? WHERE id = ? AND balance >= ?",
            amount, from, amount
        );
        if (debited != 1) {
            throw new IllegalStateException("insufficient funds");
        }

        if (failAfterDebit) {
            throw new IllegalStateException("simulated-after-debit");
        }

        int credited = jdbc.update(
            "UPDATE account SET balance = balance + ? WHERE id = ?",
            amount, to
        );
        if (credited != 1) {
            throw new IllegalStateException("destination not found");
        }
    }
}
~~~

Chạy ở thư mục chứa `pom.xml` (cần JDK 17+ và Maven):

~~~bash
mvn spring-boot:run
~~~

Các dòng **do chương trình in ra** (không tính log khởi động của Spring):

~~~text
Ban đầu: {1=1000, 2=500}
Đã bắt: simulated-after-debit
Sau rollback: {1=1000, 2=500}
Sau commit: {1=800, 2=700}
~~~

Giải thích đối chiếu:

- Lần đầu, debit đã thực hiện trong transaction nhưng exception xuất hiện **trước credit**. Proxy nhận `IllegalStateException`, yêu cầu rollback; việc debit không được commit.
- `catch` ở `CommandLineRunner` nằm **ngoài** lời gọi proxy nên việc bắt exception tại đây không cản Spring rollback. Khác với bắt exception ngay bên trong `transfer` rồi trả về bình thường.
- Lần hai, cả debit và credit hoàn tất; khi `transfer` trả về, Spring thực hiện commit. Hai số dư thay đổi cùng nhau.
- Ba câu lệnh tạo/khởi tạo dữ liệu ở runner nằm ngoài service transaction; chúng thiết lập trạng thái ban đầu cho hai lần thử và **không** thuộc transaction của `transfer`.

Có thể đặt breakpoint trước lệnh ném exception: một câu UPDATE đã được gửi tới DB, nhưng quan sát sau khi proxy hoàn tất rollback vẫn thấy dữ liệu cũ. Đó là khác biệt thiết yếu giữa "SQL đã chạy" và "transaction đã commit".

## 7. Điều khiển begin/commit/rollback bằng API Spring

`@Transactional` phù hợp với ranh giới service thông thường, còn API dưới đây giúp hiểu ai quyết định kết thúc.

**Cách được khuyến nghị cho logic imperative: `TransactionTemplate`.** Đoạn sau là **trích đoạn trong một Spring bean có sẵn `TransactionTemplate` và `JdbcTemplate`**, không phải chương trình chạy độc lập:

~~~java
transactionTemplate.executeWithoutResult(status -> {
    jdbc.update("UPDATE account SET balance = balance - 100 WHERE id = 1");
    boolean businessRuleRejected = true;
    if (businessRuleRejected) {
        status.setRollbackOnly();
        return;
    }
    jdbc.update("UPDATE account SET balance = balance + 100 WHERE id = 2");
});
~~~

`TransactionTemplate` tạo/tham gia transaction khi vào callback, kết thúc tự động khi callback rời. `setRollbackOnly()` yêu cầu rollback của scope, dù callback trả về bình thường. Trong thực tế, điều kiện nghiệp vụ phải được kiểm tra hợp lý (ví dụ không debit trước khi xác nhận nếu có thể), và các thao tác cần nằm trên cùng transaction manager/resource.

**Dùng trực tiếp `PlatformTransactionManager`** khi thực sự cần điều khiển thủ công (trích đoạn, giả định `work()` chỉ ném unchecked exception):

~~~java
TransactionStatus status =
    txManager.getTransaction(new DefaultTransactionDefinition());

try {
    work();
} catch (RuntimeException | Error ex) {
    txManager.rollback(status);
    throw ex;
}

txManager.commit(status);
~~~

Ba thao tác tương ứng là `getTransaction` (begin/join), `commit`, `rollback`. **Đặt `commit` ngoài `try` bắt lỗi nghiệp vụ** để không vô tình gọi rollback lần nữa nếu `commit` tự ném exception. Khi cần hỗ trợ checked exception, điều chỉnh luồng bắt/ném một cách tường minh. Transaction manager là đối tượng chủ quản của `TransactionStatus`; không ghép status từ manager này với manager khác.

## 8. Tác động của propagation đến thời điểm kết thúc

Xét `outer()` gọi `inner()` thông qua **hai Spring bean/proxy**, có cấu hình transaction:

| Propagation ở `inner` | Quan hệ transaction | Ý nghĩa commit/rollback ở `inner` |
| --- | --- | --- |
| `REQUIRED` | Cùng physical transaction với `outer` (nếu outer đã có) | Kết thúc scope inner **không commit vật lý**; rollback-only có thể khiến toàn bộ outer rollback |
| `REQUIRES_NEW` | Transaction vật lý độc lập; outer tạm dừng | Inner commit/rollback riêng. Outer sau đó vẫn có thể rollback mà không hủy commit của inner |
| `NESTED` | Thường cùng physical transaction với savepoint | Inner có thể rollback về savepoint; kết quả commit vật lý cuối cùng vẫn do outer quyết định, nếu hạ tầng hỗ trợ |

Ví dụ rủi ro: `inner(REQUIRED)` ném lỗi; outer bắt lỗi và muốn bỏ qua. Nếu transaction chung đã bị đánh dấu rollback-only, outer không thể commit "những phần còn lại" bằng cách chỉ bắt exception. Lúc outer commit có thể xuất hiện `UnexpectedRollbackException`. Muốn cô lập phần inner cần thiết kế ranh giới giao dịch phù hợp, không chỉ thêm `try/catch`.

`REQUIRES_NEW` thường cần thêm connection trong khi outer đang giữ connection của nó; cấu hình pool không đủ có thể gây bế tắc chờ tài nguyên. `NESTED` phụ thuộc hỗ trợ savepoint (phổ biến với JDBC), không mặc nhiên dùng được với mọi JPA/JTA manager.

## 9. Theo dõi trạng thái sau commit/rollback và side effect

Nếu cần chạy hành động **sau khi database đã commit**, có thể dùng `@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)` hoặc đăng ký `TransactionSynchronization` khi transaction synchronization đang hoạt động. Callback `afterCompletion(int status)` phân biệt `STATUS_COMMITTED`, `STATUS_ROLLED_BACK`, `STATUS_UNKNOWN`. Với cơ chế event, nên nắm rõ thời điểm event được publish và mặc định event không chạy nếu không có transaction đang quản lý (trừ khi cấu hình fallback).

Đừng gửi email, publish message không có giao dịch chung, hoặc gọi dịch vụ ngoài rồi tin rằng rollback database sẽ thu hồi các side effect đó. Nếu dữ liệu và message phải nhất quán, xem xét **transactional outbox**: lưu ý định phát event trong cùng database transaction rồi chuyển tiếp bất đồng bộ sau commit. Cơ chế này vượt phạm vi vòng đời cơ bản nhưng giải thích vì sao "rollback" chỉ có hiệu lực trên tài nguyên thực sự tham gia giao dịch.

Đối với lỗi commit mà ứng dụng không thể xác định kết quả (ví dụ mất kết nối ngay khi xác nhận), nên quan sát bằng khóa nghiệp vụ/idempotency key và truy vấn trạng thái để đối soát. Không retry mù một thao tác ghi tiền khi chưa biết nó đã commit hay chưa.

## 10. Lỗi thường gặp và cách kiểm tra

1. **Đặt `@Transactional` trên method nhưng gọi nội bộ bằng `this`.** Trong proxy mode, self-invocation bỏ qua proxy; tách thành bean khác hoặc thiết kế lại điểm gọi.
2. **Cho rằng cứ có exception là rollback.** Theo mặc định checked exception không làm rollback; kiểm tra `rollbackFor`/`noRollbackFor` và nơi exception bị bắt.
3. **Bắt exception trong cùng method rồi trả về.** Nếu nghiệp vụ cần hủy thay đổi, rethrow hoặc đánh dấu rollback-only một cách có chủ đích.
4. **Cho rằng `save()`/`flush()` là commit.** Query có thể đã chạy, nhưng transaction vẫn chờ kết thúc; xác nhận bằng đọc dữ liệu sau khi transaction kết thúc.
5. **Gọi `rollback(status)` sau khi `commit(status)` ném lỗi.** Status đã hoàn tất/cleanup; cần xử lý lỗi và đối soát, không rollback lặp.
6. **Tách thao tác qua thread mới nhưng nghĩ dùng chung transaction imperative.** Transaction JDBC/JPA thông thường được liên kết với thread đang thực thi; `@Async`, `new Thread(...)` hoặc tác vụ ngoài thread không tự thừa hưởng.
7. **Nhầm inner `REQUIRED` với giao dịch độc lập.** Inner commit chỉ kết thúc scope của nó; transaction chung do outer quyết định.

Checklist kiểm chứng một luồng giao dịch:

- Có chắc lời gọi vào đúng Spring bean/proxy và đúng transaction manager không?
- `Propagation` đang tạo mới, tham gia, hay không tạo transaction?
- Exception thuộc loại nào, có đi xuyên qua proxy, và rule nào áp dụng?
- Trạng thái rollback-only đã được đánh dấu ở scope nào?
- Sau khi **ranh giới ngoài cùng hoàn tất**, dữ liệu thực tế là gì?
- Có side effect ngoài database hoặc callback sau completion nào phải điều phối riêng không?

**Bài tập tự kiểm tra:** Trong ví dụ H2, đổi nhánh `failAfterDebit` thành một checked exception được khai báo trên service. Thử không cấu hình và có cấu hình `@Transactional(rollbackFor = Exception.class)`, rồi dự đoán hai số dư sau mỗi lần chạy; sau đó kiểm tra bằng một lần đọc từ connection ngoài transaction. Khi sửa ví dụ, phải giữ cho transaction thực sự đi qua proxy và chạy lại trên database khởi tạo sạch.

## Tài liệu tham khảo chính thức

- Spring Framework — Transaction Management: https://docs.spring.io/spring-framework/reference/data-access/transaction.html
- Transaction abstraction và `PlatformTransactionManager`: https://docs.spring.io/spring-framework/reference/data-access/transaction/strategies.html
- Cấu hình `@Transactional` và rollback rules: https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html
- Propagation `REQUIRED` / `REQUIRES_NEW` / `NESTED`: https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-propagation.html
- Programmatic transaction management: https://docs.spring.io/spring-framework/reference/data-access/transaction/programmatic.html
