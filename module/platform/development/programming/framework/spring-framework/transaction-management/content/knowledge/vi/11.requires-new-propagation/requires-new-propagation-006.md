# Nguy cơ cạn connection pool hoặc chờ khóa khi dùng REQUIRES_NEW

> **Spring Framework — Transaction Management → REQUIRES_NEW.** Vì sao một lời gọi `@Transactional(propagation = Propagation.REQUIRES_NEW)` có thể khiến ứng dụng đứng chờ, hết connection, timeout, hoặc bị chặn bởi chính transaction bên ngoài? Bài học này giải thích hai nhóm rủi ro khác nhau: **cạn pool do outer transaction vẫn giữ connection** và **chờ khóa do outer transaction vẫn giữ database locks**. Đồng thời trình bày cách dự toán pool, nhận diện triệu chứng và thiết kế lại transaction boundaries.

## 1. Điều cốt lõi: suspend không có nghĩa đã giải phóng tài nguyên

`Propagation.REQUIRES_NEW` yêu cầu **một physical transaction độc lập** mỗi khi method được Spring transaction infrastructure intercept, kể cả khi caller đã ở trong transaction.

Khi một method `outer()` đang giữ transaction T1 và gọi `inner()` với `REQUIRES_NEW`:

1. Spring tạm treo transaction context của outer ở thread hiện tại.
2. **Connection/tài nguyên đã gắn với T1 vẫn thuộc về T1**, không được trả về pool chỉ vì Java call stack tạm chuyển sang inner.
3. Inner cần bắt đầu transaction T2 bằng tài nguyên riêng, thường là **một JDBC connection khác** từ cùng pool.
4. T2 commit hoặc rollback độc lập; connection của T2 được trả về pool khi manager hoàn tất và cleanup.
5. Spring khôi phục transaction context T1; outer mới tiếp tục và về sau mới commit/rollback T1.

Điều này không có nghĩa database hỗ trợ một “lệnh SUSPEND TRANSACTION” nhả toàn bộ locks. Spring chủ yếu **tạm treo sự liên kết transaction/resource với execution context**, trong khi physical T1 vẫn còn mở.

```text
Cùng một thread, một DataSource + connection pool

outer()  @Transactional(REQUIRED)
  |
  |-- lấy Connection A từ pool
  |-- BEGIN T1; ghi dữ liệu; có thể giữ locks
  |
  +-- inner() @Transactional(REQUIRES_NEW)
  |      |
  |      |-- suspend context T1, KHÔNG trả A về pool
  |      |-- yêu cầu Connection B từ cùng pool
  |      |      |
  |      |      +-- có B --> BEGIN T2 --> commit/rollback --> trả B
  |      |      |
  |      |      +-- hết pool --> CHỜ --> connection timeout / thất bại
  |      |
  |      +-- khôi phục context của T1
  |
  +-- outer tiếp tục với A
  +-- commit/rollback T1 --> trả A về pool
```

**Nhớ một câu:** Trong lúc gọi `REQUIRES_NEW`, outer transaction có thể **vẫn giữ connection và khóa**, còn inner cần thêm connection và có thể bị chặn bởi khóa của outer. Đây là hai nút thắt **độc lập**: tăng pool chỉ giải quyết bài toán thiếu connection, không tự mở được database lock.

Tài liệu Spring nêu rõ: chỉ dùng `PROPAGATION_REQUIRES_NEW` khi connection pool được định cỡ thích hợp, ít nhất phải có dung lượng lớn hơn số thread đồng thời có outer transaction giữ connection; nếu không có thể xảy ra cạn pool và deadlock kiểu chờ tài nguyên. Phần sizing chi tiết cần tính cả nhu cầu của ứng dụng và hệ quản trị CSDL.

## 2. Phân biệt ba loại trạng thái “đang chờ”

| Hiện tượng | Chờ tài nguyên nào? | Tài nguyên ở đâu? | Dấu hiệu thường gặp | Tăng kích thước pool có đủ không? |
| --- | --- | --- | --- | --- |
| **Pool starvation / pool exhaustion** | Một connection chưa có sẵn | HikariCP/tầng pool của ứng dụng | `active == maximumPoolSize`, `idle = 0`, threads awaiting connection; sau đó lấy connection bị timeout | Có thể giúp, nếu DB chịu được số kết nối và không có nút thắt khác |
| **Database lock wait** | Row/table/index/key-range/advisory lock | Database engine | Query của inner đã có connection nhưng chờ lock, lock timeout/deadlock/statement timeout | **Không**. Connection thứ hai đã có nhưng transaction ngoài chưa nhả lock |
| **Thread starvation hoặc queueing chung** | Worker thread, executor slot, CPU hoặc request capacity | Application/server runtime | Request latency tăng, queue dài, CPU thấp/cao tùy nguyên nhân | Không nhất thiết; phải chẩn đoán đúng cổ chai |

Cùng biểu hiện “request treo” không chứng minh cùng nguyên nhân. Hãy nhìn thứ tự:

```text
Borrow connection
  |
  +-- Chờ tại pool / getConnection()
  |     => Pool starvation
  |
  v
Connection đã cấp, thực thi SQL
  |
  +-- Chờ tại database lock manager
  |     => Lock wait / lock timeout / deadlock
  |
  v
SQL hoàn tất
  |
  +-- Chờ commit / log / network / replication / I/O
        => Một loại bottleneck khác
```

Cần phân tích metric và stack traces để biết hệ thống đang chờ ở bước nào. Nhiều vấn đề có thể xuất hiện cùng lúc: outer giữ connection A, inner lấy B rồi chờ row lock; trong lúc chờ, cả A **và** B đều chiếm chỗ của pool, kéo theo các request khác chờ connection.

## 3. Vì sao REQUIRES_NEW lấy thêm physical connection?

### 3.1. Transaction độc lập cần ranh giới commit/rollback độc lập

Ví dụ service ghi đơn hàng và ghi audit record:

```java
@Service
class OrderService {
    private final AuditService audit;

    OrderService(AuditService audit) {
        this.audit = audit;
    }

    @Transactional // REQUIRED
    public void placeOrder() {
        // Ghi bảng order ở transaction T1.
        audit.logAttempt(); // Gọi qua injected Spring bean proxy.
        // T1 có thể commit/rollback sau khi audit đã xong.
    }
}

@Service
class AuditService {
    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void logAttempt() {
        // Ghi audit trong T2 độc lập.
    }
}
```

Đây là **fragment minh họa**, không phải mã chạy độc lập: cần imports, repository/JDBC và Spring configuration. T1 và T2 có thể có kết quả khác nhau:

- T2 commit, rồi T1 rollback: bản audit vẫn còn (nếu không có lỗi khác).
- T2 rollback, T1 vẫn có thể commit nếu outer xử lý lỗi phù hợp và không bị đánh dấu rollback-only.
- T2 cần connection độc lập để commit trước khi T1 kết thúc. Với JDBC local transaction cùng datasource, không thể lấy chính connection A đang có transaction T1 và đồng thời yêu cầu nó làm transaction T2 độc lập rồi trả về T1 như chưa có gì.

### 3.2. Spring thực sự “suspend” điều gì?

Với `PlatformTransactionManager` dạng imperative và các implementation như `JdbcTransactionManager`/`DataSourceTransactionManager`, Spring có thể tạm tháo resource holder và transaction synchronization của T1 ra khỏi thread, rồi gắn resource của T2. Sau khi T2 hoàn tất, trạng thái T1 được khôi phục.

**Không đồng nhất suspend trong Spring với giải phóng lock ở database.** Trên cơ sở dữ liệu thông thường, lock do transaction T1 sở hữu chỉ được nhả theo semantics của database: commit, rollback, một số thao tác savepoint/lock cụ thể hoặc hành vi provider. Tạm chuyển Java thread sang T2 **không kết thúc T1**.

### 3.3. Có nhất thiết mỗi REQUIRES_NEW đều lấy hai connection không?

Không nên phát biểu như một luật cho mọi manager và mọi thời điểm. Trong mô hình **JDBC local transaction, cùng một pool, outer đã mượn physical connection**, inner `REQUIRES_NEW` thường cần thêm một connection đang sử dụng đồng thời. Nhưng còn các trường hợp:

- Outer chưa thực sự mượn physical connection nhờ `LazyConnectionDataSourceProxy` hoặc lazy acquisition khác.
- Inner dùng datasource hoặc pool khác; áp lực dồn lên pool của inner thay vì pool của outer.
- JPA có thời điểm lấy/release JDBC connection phụ thuộc provider và transaction settings.
- JTA có cơ chế enlistment/suspend riêng.
- R2DBC dùng `ConnectionFactory` và reactive context, không diễn giải trực tiếp mọi metric theo JDBC pool.

**Số “outer transactions” không luôn bằng số connection đang active.** Sizing phải dựa vào trạng thái sử dụng physical connections thực tế, transaction manager và cách các operations được thực thi.

## 4. Kịch bản cạn pool đơn giản nhất: một thread, pool size = 1

Giả sử pool chỉ cho mượn **một** JDBC connection:

```text
Pool: maximumPoolSize = 1

Thread-1:
  outer T1 --> borrow A                         [Pool 1/1 active]
     |
     +--> inner REQUIRES_NEW --> wants B        [Pool 1/1 active]
              |
              +--> B unavailable
              +--> waits for connectionTimeout
              |
     outer không thể commit/rollback T1
     cho đến khi inner trả quyền điều khiển

Pool không thể cấp B vì A vẫn được T1 giữ
=> Inner timeout / CannotCreateTransactionException
```

Đây là **pool starvation trong cùng call stack**, không cần nhiều threads hay database locks. Inner thường không được vào thân phương thức: lỗi xảy ra **trước** khi Spring gọi business method của inner, khi transaction manager cố khởi tạo T2 và mượn connection.

Với HikariCP, thao tác borrow chờ tối đa `connectionTimeout`. Nếu vẫn không có connection, Hikari ném `SQLException`; Spring JDBC transaction manager thường chuyển thành `CannotCreateTransactionException`. Exception propagate ra outer. Nếu outer không bắt, rollback rule cho runtime exception thường khiến T1 rollback, sau đó A được trả về pool.

**Điểm dễ nhầm:** tăng `connectionTimeout` từ 2 giây lên 30 giây không tạo thêm connection. Trong kịch bản một thread trên, A không được nhả khi inner chưa kết thúc; chỉ kéo dài thời gian chờ. Timeout phù hợp giúp lỗi được phát hiện rõ hơn, không giải quyết thiếu capacity.

### Vòng chờ với nhiều threads

Giả sử 8 request đồng thời, mỗi request mở outer transaction trên cùng pool size 8, rồi đều gọi inner `REQUIRES_NEW`:

```text
Pool maximum = 8

Thread 1: outer giữ A1 --> cần B1
Thread 2: outer giữ A2 --> cần B2
Thread 3: outer giữ A3 --> cần B3
...
Thread 8: outer giữ A8 --> cần B8

Pool: 8/8 connections đang bị giữ bởi outer
      0 connections còn lại cho inner

Tất cả threads đang chờ, không thread nào
tiếp tục outer để nhả A1..A8
=> chờ vòng / pool deadlock kiểu starvation
=> connectionTimeout sau một khoảng thời gian
```

Trong thực tế một số request có thể kết thúc trước đó, hoặc pool đang có idle connection nên sự cố không xảy ra trong mọi lần chạy. Đây là lý do vấn đề thường **chỉ xuất hiện khi tăng concurrency**, khó tái hiện ở môi trường dev nhưng bùng phát dưới tải production.

## 5. Định cỡ connection pool: tránh công thức máy móc

### 5.1. Ngưỡng tránh chờ vòng

Spring cảnh báo: pool nên **lớn hơn số threads đồng thời** có thể giữ outer transaction connection, **ít nhất một connection** cho inner. Nếu có N threads và mỗi thread đã chiếm một outer connection, pool size đúng bằng N khiến mọi inner bị chặn. N+1 cho phép **một** inner tiến lên, commit và trả connection, rồi các inner khác có cơ hội lần lượt tiến lên.

Ví dụ:

| Số outer transactions đang giữ connection | Pool size | Connection còn cho inner | Ý nghĩa |
| ---: | ---: | ---: | --- |
| 1 | 1 | 0 | Inner `REQUIRES_NEW` không thể bắt đầu cho đến khi có connection nhả ra; cùng thread dễ tự chờ |
| 8 | 8 | 0 | Nếu cả 8 cùng đòi inner, có thể cùng chờ đến timeout |
| 8 | 9 | 1 | Có ít nhất một connection cho inner tiến lên, nếu không có người dùng khác |
| 8 | 16 | 8 | Có chỗ cho 8 inner đồng thời, **nếu DB chịu được** và không có nhu cầu khác |

**N+1 không phải sizing tối ưu chung.** Nó là nhận xét về tránh kẹt vòng cụ thể, không phải cam kết latency tốt, không bảo đảm đủ connection cho retry, nhiều tầng `REQUIRES_NEW`, các thread khác, scheduled tasks hoặc hoạt động health check.

### 5.2. Mô hình capacity để tính theo workload

Một mô hình gần đúng tại đỉnh tải:

```text
required_concurrent_connections
  ~= outer connections vẫn đang giữ
   + REQUIRES_NEW connections đồng thời
   + connections của work khác dùng cùng pool
   + safety margin hợp lý
```

Giả sử 12 request đồng thời, mỗi request giữ 1 outer connection và có thể gọi một inner transaction đồng thời:

```text
Outer đang giữ:                 12
Inner tối đa cùng lúc:          12
Query/background work khác:     3
-------------------------------
Nhu cầu đỉnh minh họa:         27+
```

Con số này **chỉ là bài toán capacity minh họa**, không phải khuyến nghị mặc định đặt pool 27. Cần đối chiếu khả năng database cho phép connection, TPS/latency, thời gian giữ connection, đỉnh request, và các workload khác. Pool quá lớn có thể khiến database quá tải vì cạnh tranh CPU, I/O, locks và memory.

Nếu có chuỗi `outer → innerA(REQUIRES_NEW) → innerB(REQUIRES_NEW)`, một thread có thể giữ nhiều transaction resources cùng lúc, khiến peak demand vượt mô hình “mỗi thread tối đa 2 connections”. Vì vậy cần rà toàn call graph chứ không chỉ một annotation.

### 5.3. Dùng đo đạc thay vì chỉ đếm request threads

HikariCP cung cấp các metric hữu ích:

- `ActiveConnections`: số connection đang được cho mượn.
- `IdleConnections`: số connection đang sẵn trong pool.
- `TotalConnections`: tổng connection mà pool đang quản lý.
- `ThreadsAwaitingConnection`: số threads đang đợi lấy connection.
- Thời gian acquisition, timeout count, wait duration; thường tích hợp Micrometer/Actuator/JMX tùy cấu hình.

Đừng nhìn mỗi `maximumPoolSize`. Pool size 20 nhưng `active=20`, `idle=0`, `awaiting=30` kéo dài trong các lần request có `REQUIRES_NEW` là dấu hiệu rõ của capacity contention. Cần kiểm tra query latency và DB locks song song, vì một inner bị chặn bởi DB lock cũng giữ connection B lâu, làm pool cạn theo hiệu ứng dây chuyền.

## 6. Kịch bản thứ hai: inner lấy được connection nhưng chờ khóa của outer

Một connection thứ hai có sẵn **không** bảo đảm transaction T2 chạy được. Nếu T1 đã khóa dữ liệu mà T2 cần:

```text
Connection A / T1 (outer):
    UPDATE accounts SET balance = balance - 100 WHERE id = 42;
    [T1 giữ exclusive lock trên row id=42]
                       |
                       | outer gọi inner REQUIRES_NEW
                       v
Connection B / T2 (inner):
    UPDATE accounts SET status = 'VERIFIED' WHERE id = 42;
    [T2 chờ exclusive lock do T1 nắm giữ]
                       |
                       v
    T1 chỉ có thể commit sau khi inner trả quyền điều khiển
    T2 lại chỉ có thể tiếp tục sau khi T1 nhả lock

=> Wait cycle, lock timeout hoặc deadlock detection
```

Trong kịch bản đồng bộ cùng thread này, T1 bị “tạm treo” ở call stack Java nhưng **vẫn còn mở trong DB**. T1 không thể commit/rollback để nhả lock cho đến khi inner kết thúc. T2 chờ lock do T1 nắm giữ, nên hai bên chặn nhau theo quan hệ nhân quả.

Tùy hệ quản trị, lock manager có thể phát hiện deadlock và chọn nạn nhân, hoặc SQL của T2 chờ đến khi vượt `lock_timeout`/`statement_timeout` rồi ném exception. Không phải engine nào cũng báo một lỗi tên “deadlock” cho cấu trúc chờ kiểu này; **lock timeout** là kết quả rất phổ biến.

### Phân biệt với thiếu connection

| Pool đã cho inner connection B? | SQL của inner đã bắt đầu? | Nguyên nhân chủ đạo |
| --- | --- | --- |
| Chưa | Chưa | Chờ pool |
| Rồi | Rồi, nhưng chờ lock | Chờ khóa trong DB |
| Rồi | Rồi, query CPU/I/O nặng | Chậm query hoặc bottleneck DB khác |

Tăng `maximumPoolSize` từ 2 lên 100 **không nhả lock của T1**. Ngược lại, nó có thể làm nhiều inner transactions cùng bị kẹt và cùng chiếm thêm connections, khiến ảnh hưởng lan rộng.

### “Đã commit inner rồi thì outer sẽ thấy dữ liệu mới” cũng không tuyệt đối

Dù T2 commit độc lập, T1 có thể vẫn dùng snapshot/isolation cũ hoặc persistence context của JPA; nó không nhất thiết nhìn thấy mọi thay đổi của T2 ngay lập tức. Ngược lại, T2 có thể **không nhìn thấy uncommitted changes** của T1, nên logic như “đọc order vừa insert ở outer rồi update audit liên quan đến order đó” có thể lỗi hoặc chờ lock/foreign key vì order chưa commit.

Cần phân tích isolation, MVCC snapshot, foreign-key locks và cache/persistence context, không chỉ số lượng connection.

## 7. Một ví dụ lỗi thiết kế và cách chuyển hướng

### 7.1. Thiết kế dễ rơi vào chờ khóa

```java
@Service
class BookingService {
    private final BookingRepository bookingRepository;
    private final StatusService statusService;

    @Transactional
    public void reserve(long bookingId) {
        bookingRepository.markReserved(bookingId); // T1 khóa row
        statusService.verify(bookingId);           // T2 cần cùng row
        // T1 không kết thúc cho tới khi verify() trả về.
    }
}

@Service
class StatusService {
    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void verify(long bookingId) {
        bookingRepository.markVerified(bookingId);
    }
}
```

Đây là **fragment cấu trúc**, chưa phải mã biên dịch độc lập; các constructor/imports/repository được lược bớt. Việc markReserved ở outer và markVerified ở inner cùng một row rất dễ tạo chờ khóa, dù hai methods cùng dùng một database.

### 7.2. Nếu hai bước phải rollback cùng nhau: dùng REQUIRED

Nếu cập nhật trạng thái “reserved” và “verified” bắt buộc atomic cùng một transaction, chọn một boundary `REQUIRED` (inner cũng `REQUIRED` hoặc không tự khai báo boundary) để cùng thao tác trên T1. Khi cùng transaction, không có T2 tranh lock với T1 chỉ vì `REQUIRES_NEW`.

```java
@Transactional
public void reserveAndVerify(long bookingId) {
    bookingRepository.markReserved(bookingId);
    bookingRepository.markVerified(bookingId);
}
```

Đây là fragment. Các câu lệnh vẫn có thể bị block bởi **transaction khác**; `REQUIRED` không giải quyết mọi contention. Nhưng nó loại bỏ vấn đề “chính inner độc lập của cùng call stack đang cần lock do outer giữ” trong trường hợp minh họa.

### 7.3. Nếu hai bước cần commit độc lập: thay đổi ranh giới

Nếu bước verify thực sự cần transaction độc lập, cân nhắc dời nó **ra sau khi outer commit**:

```text
T1: reserve booking --> commit, nhả locks
                      |
                      v
T2: verify booking --> commit độc lập
```

Việc tách có thể làm phát sinh khoảng thời gian giữa hai trạng thái, nên cần xử lý retry, idempotency và lỗi trung gian. Nếu yêu cầu là ghi event đáng tin cậy sau khi transaction nghiệp vụ commit, transactional outbox trong cùng T1 rồi có worker phát event là một lựa chọn thường dùng.

**Không cứ thấy cần lưu audit/log là mặc nhiên đặt `REQUIRES_NEW`.** Audit có thể cần độc lập vì yêu cầu pháp lý/nghiệp vụ, nhưng thiết kế phải tính đến pool, lock order, data visibility và khả năng retry.

## 8. Ví dụ chạy được Java 17+: pool size 1 thất bại, pool size 2 chạy được

Ví dụ dưới đây mô tả **pool exhaustion** bằng Spring Framework 6.2.x + `JdbcTransactionManager` + HikariCP 5.1.0 + H2 in-memory. Không cần Spring Boot hoặc DB server.

Cả hai kịch bản chạy cùng một chương trình, lần lượt tạo Spring context với pool có 1 và 2 connections:

- Outer `@Transactional` ghi vào bảng `outer_events`, giữ connection A.
- Inner `@Transactional(REQUIRES_NEW)` ghi vào bảng `audit_events`; cần một connection B độc lập.
- Nếu inner chạy được, outer **cố tình ném exception** để rollback. Khi pool 2, inner đã commit nên audit vẫn còn.
- Khi pool 1, inner không thể mượn B trong `connectionTimeout`, nên fail **trước khi inner SQL chạy**; outer rollback.

Sử dụng **hai bảng khác nhau** để tránh tự gây lock conflict: ví dụ này minh họa cạn pool một cách độc lập với bài toán database locks ở mục 6.

### 8.1. Cấu trúc dự án

```text
requires-new-pool-demo/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── dev/
                └── learning/
                    └── RequiresNewPoolDemo.java
```

Tạo `pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>dev.learning</groupId>
    <artifactId>requires-new-pool-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.8</version>
        </dependency>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-jdbc</artifactId>
            <version>6.2.8</version>
        </dependency>
        <dependency>
            <groupId>com.zaxxer</groupId>
            <artifactId>HikariCP</artifactId>
            <version>5.1.0</version>
        </dependency>
        <dependency>
            <groupId>com.h2database</groupId>
            <artifactId>h2</artifactId>
            <version>2.3.232</version>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
                <configuration>
                    <release>17</release>
                </configuration>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.0</version>
                <configuration>
                    <mainClass>dev.learning.RequiresNewPoolDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

### 8.2. Tạo `src/main/java/dev/learning/RequiresNewPoolDemo.java`

```java
package dev.learning;

import javax.sql.DataSource;

import com.zaxxer.hikari.HikariConfig;
import com.zaxxer.hikari.HikariDataSource;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.support.JdbcTransactionManager;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.annotation.EnableTransactionManagement;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;

public final class RequiresNewPoolDemo {

    // Một settings bean riêng để hai scenario dùng chung Config,
    // không phải sửa global static state hoặc hệ thống property.
    public record DemoSettings(int poolSize) {}

    @Configuration(proxyBeanMethods = false)
    @EnableTransactionManagement
    public static class Config {

        @Bean(destroyMethod = "close")
        HikariDataSource dataSource(DemoSettings settings) {
            HikariConfig cfg = new HikariConfig();
            cfg.setJdbcUrl(
                    "jdbc:h2:mem:pool_" + settings.poolSize()
                            + ";DB_CLOSE_DELAY=-1");
            cfg.setUsername("sa");
            cfg.setPassword("");
            cfg.setMaximumPoolSize(settings.poolSize());
            cfg.setMinimumIdle(settings.poolSize());

            // Cho inner chờ tối đa 2 giây khi pool hết connection.
            // Tăng timeout không chữa được vòng chờ same-thread.
            cfg.setConnectionTimeout(2_000);
            return new HikariDataSource(cfg);
        }

        @Bean
        JdbcTemplate jdbcTemplate(DataSource dataSource) {
            return new JdbcTemplate(dataSource);
        }

        @Bean
        PlatformTransactionManager transactionManager(
                DataSource dataSource) {
            return new JdbcTransactionManager(dataSource);
        }

        @Bean
        AuditService auditService(JdbcTemplate jdbc) {
            return new AuditService(jdbc);
        }

        @Bean
        OrderService orderService(JdbcTemplate jdbc, AuditService audit) {
            return new OrderService(jdbc, audit);
        }
    }

    public static class AuditService {
        private final JdbcTemplate jdbc;

        public AuditService(JdbcTemplate jdbc) {
            this.jdbc = jdbc;
        }

        @Transactional(propagation = Propagation.REQUIRES_NEW)
        public void writeAudit() {
            jdbc.update(
                    "INSERT INTO audit_events(id, description) "
                            + "VALUES (?, ?)",
                    2, "inner committed");
        }
    }

    public static class OrderService {
        private final JdbcTemplate jdbc;
        private final AuditService audit;

        public OrderService(JdbcTemplate jdbc, AuditService audit) {
            this.jdbc = jdbc;
            this.audit = audit;
        }

        @Transactional
        public void placeOrderThenFail() {
            jdbc.update(
                    "INSERT INTO outer_events(id, description) "
                            + "VALUES (?, ?)",
                    1, "outer rolled back");

            // Cần connection thứ hai trong cùng pool.
            // Spring proxy của AuditService áp dụng REQUIRES_NEW.
            audit.writeAudit();

            // Khi pool=2, audit đã commit; outer vẫn có thể rollback.
            throw new IllegalStateException("outer failed");
        }
    }

    private static int count(JdbcTemplate jdbc, String table) {
        return jdbc.queryForObject(
                "SELECT COUNT(*) FROM " + table,
                Integer.class);
    }

    private static void runScenario(int poolSize) {
        try (AnnotationConfigApplicationContext context =
                     new AnnotationConfigApplicationContext()) {

            // Đăng ký settings trước khi refresh context.
            context.registerBean(
                    DemoSettings.class,
                    () -> new DemoSettings(poolSize));
            context.register(Config.class);
            context.refresh();

            JdbcTemplate jdbc = context.getBean(JdbcTemplate.class);
            jdbc.execute(
                    "CREATE TABLE outer_events "
                            + "(id INT PRIMARY KEY, description VARCHAR(80))");
            jdbc.execute(
                    "CREATE TABLE audit_events "
                            + "(id INT PRIMARY KEY, description VARCHAR(80))");

            String failureType = "none";
            try {
                // Lấy Spring bean proxy, không tự new OrderService.
                context.getBean(OrderService.class)
                        .placeOrderThenFail();
            } catch (RuntimeException ex) {
                failureType = ex.getClass().getSimpleName();
            }

            System.out.println(
                    "pool=" + poolSize + " failure=" + failureType);
            System.out.println(
                    "pool=" + poolSize
                            + " outer=" + count(jdbc, "outer_events")
                            + " audit=" + count(jdbc, "audit_events"));
        }
    }

    public static void main(String[] args) {
        runScenario(1);
        runScenario(2);
    }
}
```

### 8.3. Chạy demo

Yêu cầu **JDK 17+**, **Maven 3.x** và Internet lần đầu để lấy dependencies. Đứng trong thư mục `requires-new-pool-demo`:

```bash
mvn -q clean compile exec:java
```

**Các dòng do chương trình in ra** với dependencies/cấu hình trên, không tính logging có thể xuất hiện từ Maven, Spring, HikariCP hoặc SLF4J:

```text
pool=1 failure=CannotCreateTransactionException
pool=1 outer=0 audit=0
pool=2 failure=IllegalStateException
pool=2 outer=0 audit=1
```

**Diễn giải kết quả:**

1. **Pool 1:** Outer T1 đã lấy connection duy nhất và ghi `outer_events`. Spring cố bắt đầu T2 cho `AuditService.writeAudit()` nhưng không có connection khác. Sau `connectionTimeout`, HikariCP báo không cấp được connection; `JdbcTransactionManager` chuyển lỗi khởi tạo transaction thành `CannotCreateTransactionException`. Transaction ngoài rollback theo exception; không có dòng nào trong hai bảng. Body của inner **chưa chạy**, nên `audit=0`.
2. **Pool 2:** Outer T1 giữ connection A; inner T2 lấy connection B. Hai bảng khác nhau nên không tự tranh row locks trong kịch bản này. T2 ghi audit và commit, trả B về pool. Outer sau đó cố tình ném `IllegalStateException`, nên T1 rollback. Dòng audit đã commit độc lập vẫn tồn tại: `outer=0 audit=1`.
3. Hai contexts dùng database H2 in-memory khác nhau (`pool_1`, `pool_2`), tránh dữ liệu thí nghiệm trước ảnh hưởng lần sau.
4. Khi `runScenario()` kết thúc, Spring đóng context và Hikari datasource tương ứng; connection pool không bị giữ mở vô thời hạn.

**Vì sao ví dụ này hữu ích hơn việc chỉ tăng pool?** Kịch bản minh họa luôn cả semantics độc lập của `REQUIRES_NEW`. Đặt pool đúng cho phép inner chạy, nhưng **không khiến T1 và T2 trở thành một atomic transaction**. Nếu ứng dụng đòi “audit chỉ tồn tại nếu order commit”, ví dụ pool=2 cũng cho thấy cấu hình nghiệp vụ sai: audit đã commit trước khi order rollback.

### 8.4. Tự kiểm tra thêm bằng thay đổi có chủ đích

**Thử A — Thay inner thành `REQUIRED`.** Trên cùng JDBC datasource, inner tham gia connection/transaction của outer; pool size 1 vẫn có thể chạy call chain (miễn không có nhu cầu connection khác), rồi khi outer ném exception cả hai writes rollback: `outer=0 audit=0`. Như vậy việc thiếu connection thứ hai gắn trực tiếp với `REQUIRES_NEW`.

**Thử B — Bỏ exception ở outer.** Với pool size 2, cả T1 và T2 commit, hai bảng đều có một record. Với pool size 1, inner vẫn không có connection thứ hai nên flow chưa thể thành công.

**Thử C — Giữ pool size 2 nhưng làm cả hai transaction cập nhật cùng một row.** Khi T1 giữ lock và T2 cần row đó, inner có thể chờ lock/timeout dù pool còn connection. Đây là bài toán **khác** với pool starvation; hãy đặt DB lock timeout ngắn trong môi trường test và không áp dụng code gây chờ vào production.

**Thử D — Đặt pool size đủ lớn nhưng giả lập nhiều outer calls đồng thời.** Dùng concurrency tests có timeout và giới hạn số threads; quan sát metric active/idle/pending và thời gian mượn connection. Không chạy test load không giới hạn trên DB production.

## 9. Tình huống chờ row lock: fragment cho integration test

Nếu muốn tái hiện riêng lock wait, cần dùng **hai connections thực sự** và cùng một row đã tồn tại trước transaction:

```sql
CREATE TABLE accounts (
    id BIGINT PRIMARY KEY,
    balance BIGINT NOT NULL,
    verified BOOLEAN NOT NULL
);

INSERT INTO accounts(id, balance, verified)
VALUES (42, 1000, FALSE);
```

Luồng giao dịch giả định:

```java
// Trong Spring bean OuterService.
@Transactional
public void outer() {
    jdbc.update(
            "UPDATE accounts SET balance = balance - 100 WHERE id = ?",
            42L);                         // T1 khóa row 42.

    innerService.verifySameAccount();     // T2 cần row 42.
    // T1 chỉ có thể kết thúc sau lời gọi inner.
}

// Trong bean InnerService khác; gọi qua Spring proxy.
@Transactional(propagation = Propagation.REQUIRES_NEW)
public void verifySameAccount() {
    jdbc.update(
            "UPDATE accounts SET verified = TRUE WHERE id = ?",
            42L);                         // T2 chờ lock của T1.
}
```

Đây là **fragment, không phải chương trình độc lập**, vì chưa có imports, beans, setup DB và cơ chế chặn timeout. Nó minh họa luồng có thể **bị block bởi chính outer transaction**.

Khi thử trong sandbox/test DB, hãy đặt một database lock timeout ngắn và hủy test nếu vượt thời hạn. Với H2 có thể cấu hình `LOCK_TIMEOUT`; PostgreSQL có `lock_timeout` và `statement_timeout`; MySQL InnoDB có `innodb_lock_wait_timeout`. Các thiết lập này không đồng nhất về phạm vi và semantics giữa hệ quản trị; tra tài liệu driver và DBMS trước khi áp dụng.

**Đừng dùng ví dụ chờ khóa vô hạn trong bài học chạy tự động.** Nó có thể chiếm connection, worker thread và làm test suite đứng trong môi trường CI.

### Lock ngoài “cùng một row” cũng gây chờ

Tình huống thực tế phức tạp hơn một UPDATE:

- T1 insert parent record chưa commit, T2 insert child record cần kiểm tra foreign key tham chiếu parent.
- T1 update một unique/index entry, T2 insert hoặc update key liên quan.
- T1 dùng `SELECT ... FOR UPDATE`/pessimistic lock, T2 cũng cần row/range đó.
- T1 giữ table lock/DDL lock hoặc advisory lock mà T2 cần.
- T2 đọc dữ liệu chưa commit của T1 dưới isolation không cho dirty read và có thể thấy bản cũ/không thấy dữ liệu hoặc chờ tùy DBMS/operation.
- T1 đã dùng JPA `EntityManager` chưa flush; T2 trên connection khác không tự thấy những thay đổi vẫn còn trong persistence context.

Vì vậy **“Inner ghi bảng khác” không luôn có nghĩa không có lock contention**. Foreign keys, indexes, triggers và relationships có thể gián tiếp tạo xung đột.

## 10. Bốn anti-pattern làm rủi ro tăng mạnh

### 10.1. Transaction ngoài quá dài

```java
@Transactional
public void fulfillOrder() {
    repository.save(order);

    callExternalHttpService();  // Chậm hoặc timeout.
    generateLargeReport();      // Tốn CPU/I/O.
    auditService.writeInRequiresNewTransaction();
}
```

Fragment minh họa. Outer có thể giữ connection và locks trong lúc chờ HTTP hoặc CPU; khi tới inner lại giữ lâu hơn. Hãy cố gắng chỉ bao các thao tác thực sự cần atomicity trong transaction; đưa phần I/O độc lập ra ngoài transaction boundary khi phù hợp.

### 10.2. Inner REQUIRES_NEW cũng làm công việc chậm

Nếu inner gửi HTTP, xử lý file hoặc chạy query nặng khi đang giữ connection B, nó kéo dài thời gian outer giữ A và inner giữ B. Pool demand gần như tăng gấp đôi cho cùng một request trong khoảng thời gian đó.

**Chiến lược:** inner chỉ thực hiện công việc DB thật cần commit độc lập, ngắn và dự đoán được; tránh long-running operations trong cả T1/T2.

### 10.3. Nhiều tầng REQUIRES_NEW

```text
A @Transactional(REQUIRED)             -> giữ conn 1
  B @Transactional(REQUIRES_NEW)        -> giữ conn 2, suspend A
    C @Transactional(REQUIRES_NEW)      -> cần conn 3, suspend B
      D @Transactional(REQUIRES_NEW)    -> cần conn 4, suspend C
```

Các connection được giữ tại nhiều scopes cùng call stack. Một pool đủ cho “outer + 1 inner” có thể vẫn cạn nếu có chuỗi REQUIRES_NEW lồng sâu. Đặc biệt nguy hiểm khi một method chung của audit/metrics vô tình có REQUIRES_NEW và được gọi từ nhiều tầng.

### 10.4. Bắt lỗi thiếu connection rồi tiếp tục commit outer

```java
@Transactional
public void placeOrder() {
    repository.save(order);

    try {
        auditService.writeInRequiresNewTransaction();
    } catch (RuntimeException ignored) {
        // Có thể đang nuốt lỗi mượn connection hoặc lỗi DB nghiêm trọng.
    }

    // Outer có thể kết thúc bình thường và commit,
    // khiến audit bị thiếu mà không ai phát hiện.
}
```

Fragment minh họa. Nếu việc ghi audit là yêu cầu bắt buộc, **đừng lặng lẽ bỏ qua lỗi**. Cần quyết định rõ: rollback outer, ghi vào outbox để retry, hoặc báo trạng thái partial failure. Ngoài ra, một số lỗi DB có thể đã đánh dấu transaction rollback-only, nên bắt exception không đảm bảo commit thành công.

## 11. Các phương án giảm rủi ro — chọn theo yêu cầu nghiệp vụ

| Phương án | Khi nên dùng | Lợi ích | Đánh đổi / giới hạn |
| --- | --- | --- | --- |
| **Đổi inner về `REQUIRED`** | Các writes phải commit/rollback cùng nhau | Cùng physical transaction, thường không cần connection B cho cùng datasource; tránh lock tự tranh giữa T1/T2 | Inner không còn commit độc lập; rollback-only của inner có thể ảnh hưởng outer |
| **Giữ `REQUIRES_NEW`, định cỡ pool dựa trên load** | Inner thực sự cần commit độc lập | Giảm lỗi mượn connection nếu DB đủ capacity | Không giải quyết lock contention; dùng thêm DB connections |
| **Rút ngắn outer transaction** | Outer đang bao HTTP/CPU hoặc nhiều bước không cần atomic | Giảm thời gian giữ A/locks | Cần thiết kế lại boundaries, xử lý lỗi giữa các bước |
| **Dời inner sang sau outer commit** | Inner cần hoạt động sau một commit thành công | T1 nhả lock trước T2; không giữ đồng thời A và B trong cùng stack | Giao đoạn giữa hai commits; cần retry/idempotency |
| **Transactional outbox** | Cần đảm bảo event/side effect được ghi nhận cùng dữ liệu nghiệp vụ | Outbox record được commit cùng T1; publisher xử lý sau | Thêm worker, retry, duplicate handling/idempotent consumers |
| **`NESTED` / savepoint** | Cần partial rollback trong một JDBC physical transaction | Không luôn cần connection B riêng, tránh independent commit | Phụ thuộc JDBC savepoint/manager; inner không commit độc lập |
| **Tách pools/datasources** | Tài nguyên thực sự độc lập, có lý do phân chia | Tránh một loại tác vụ chiếm toàn bộ cùng pool | Không xóa lock contention nếu trỏ về cùng DB/row; phức tạp vận hành |
| **Giới hạn đồng thời / bulkhead** | Spikes tạo nhiều outer+inner đồng thời | Giảm request pressure, kiểm soát tail latency | Cần timeout/backpressure, có thể giảm throughput |
| **Tối ưu SQL/index/lock order** | Inner đã có connection nhưng chờ DB locks | Giảm lock duration và contention | Cần phân tích execution plans và data access patterns |

**Đừng dùng `REQUIRES_NEW` như một “miếng vá” cho mọi rollback-only issue.** Nó tạo transaction độc lập, nhưng đổi cả semantics commit/rollback và mức sử dụng tài nguyên.

### Dời inner ra sau commit có điều kiện gì?

Nếu inner chỉ được chạy khi T1 thành công, có thể dùng cơ chế event sau commit, task queue hoặc outbox. Tuy nhiên cần hiểu một số transaction synchronization callbacks diễn ra khi transaction đã commit nhưng resource binding có thể chưa hoàn tất cleanup; một data write mới trong callback cần **transaction mới phù hợp**, không giả định lời gọi JDBC lúc đó sẽ tự commit. Với yêu cầu độ tin cậy cao, transactional outbox + consumer idempotent là một lựa chọn vững hơn việc chỉ phát sự kiện trong memory.

Nếu inner cần ghi audit **ngay cả khi outer rollback**, đó là một yêu cầu khác: dời sau commit không còn đáp ứng mục tiêu. Khi đó cần cân nhắc transaction độc lập nhưng tránh truy cập row dữ liệu bị outer khóa, giới hạn độ dài/cấp connection, hoặc dùng cơ chế ghi nhận lỗi bên ngoài.

## 12. Chẩn đoán production theo thứ tự

### 12.1. Kiểm tra transaction boundary và proxy trước

`@Transactional(propagation = Propagation.REQUIRES_NEW)` chỉ được áp dụng khi lời gọi đi qua Spring AOP proxy (với proxy mode mặc định). Nếu outer gọi `this.inner()` trong cùng object, inner annotation có thể bị bypass. Khi đó test dường như “không thiếu connection”, nhưng thực ra **không hề có physical T2 độc lập**.

```java
public void outer() {
    this.inner();  // Self-invocation: bỏ qua proxy cho inner.
}

@Transactional(propagation = Propagation.REQUIRES_NEW)
public void inner() {
    // Không tự có new transaction trong lời gọi this.inner().
}
```

Đây là fragment. Tách thành bean khác và inject proxy là phương án dễ hiểu. Khi kiểm thử pool, xác nhận thực sự có hai physical transaction/connection ở đúng cấu hình, không suy từ annotation.

### 12.2. Quan sát pool

Bên trong ứng dụng có bean `HikariDataSource hikari` (fragment):

```java
var metrics = hikari.getHikariPoolMXBean();

System.out.println("active=" + metrics.getActiveConnections());
System.out.println("idle=" + metrics.getIdleConnections());
System.out.println("total=" + metrics.getTotalConnections());
System.out.println(
        "awaiting=" + metrics.getThreadsAwaitingConnection());
```

Các giá trị thay đổi theo thời điểm và concurrency; không ghi một sample là “mặc định” của Hikari. Cần quan sát **theo thời gian**, đặc biệt quanh những request gọi inner REQUIRES_NEW. Kết hợp metrics request concurrency, pool wait time, acquisition timeout và database sessions.

Nếu `awaiting>0` kéo dài cùng `active=max` và `idle=0`, kiểm tra pool exhaustion. Nếu `active` không sát max nhưng request vẫn chậm, tìm DB lock/SQL/network bottleneck trước khi tăng pool.

### 12.3. Thread dumps và application traces

- Nếu thread stack đang ở `HikariPool.getConnection(...)` / borrow connection, có thể đang chờ pool.
- Nếu đang ở JDBC driver `PreparedStatement.execute...` hoặc socket read, thread có thể đang chờ SQL/DB; không thể kết luận ngay là lock mà không nhìn database wait events.
- Trace timing quanh outer begin, call inner, connection acquisition, first SQL, inner commit và outer completion sẽ chỉ ra chỗ trễ.
- Khi bật transaction logs, ghi kèm request/correlation ID để phân biệt các transactions trong cùng request.

Trong Spring Boot, có thể bật chẩn đoán khi cần:

```properties
logging.level.org.springframework.transaction=TRACE
logging.level.org.springframework.jdbc.datasource=DEBUG
logging.level.com.zaxxer.hikari=DEBUG
```

Đây là **cấu hình minh họa**. Không nên bật TRACE/DEBUG kéo dài trên production nếu chi phí log, dữ liệu nhạy cảm hoặc mức load không cho phép. Hãy dùng sampling và thời hạn quan sát có kiểm soát.

### 12.4. Kiểm tra database locks

Theo DBMS, dùng công cụ hệ thống:

- PostgreSQL: `pg_stat_activity`, `pg_locks`, `pg_blocking_pids(pid)`; xem session nào đang block session nào, transaction start và SQL đang chạy.
- MySQL InnoDB: `performance_schema.data_locks`, `performance_schema.data_lock_waits`, các views/diagnostic tools tương ứng.
- SQL Server: DMVs về waiting tasks/requests/locks.
- Oracle: views về sessions, locks và wait events.

**Đừng chỉ nhìn một câu SQL của inner.** Query blocker thường là transaction ngoài đã UPDATE/INSERT trước khi inner được gọi, chứ không phải query hiện tại đang xuất hiện trên thread ứng dụng.

### 12.5. Chẩn đoán khác nhau, cách sửa khác nhau

```text
Request bị chậm trong outer -> inner(REQUIRES_NEW)
                          |
                          v
               Đã borrow được connection B?
                /                      \
             CHƯA                      RỒI
              |                         |
      active=max, awaiting>0       SQL đã chạy?
              |                    /        \
      Pool capacity / leaks      CHƯA       RỒI
              |                   |          |
      Sizing, release,         driver/net  DB wait state?
      backpressure                           |
                                     lock wait / I/O?
                                            |
                                  kiểm tra blocking session
                                  và T1 còn giữ khóa
```

Lưu ý “connection leak” và “connection được giữ hợp lệ nhưng quá lâu” là hai chuyện khác. Trong `REQUIRES_NEW`, outer giữ connection A đến khi kết thúc T1 là hành vi **đúng theo transaction semantics**, nhưng có thể là lựa chọn kiến trúc tốn kém.

## 13. Timeout nào giải quyết điều gì?

| Timeout | Vị trí áp dụng | Tác dụng chủ yếu | Không bảo đảm |
| --- | --- | --- | --- |
| `Hikari connectionTimeout` | Đợi connection từ pool | Chặn việc mượn connection chờ vô hạn; trả lỗi khi pool không có connection | Không hủy transaction ngoài đang giữ connection |
| Spring `@Transactional(timeout = ...)` | Transaction manager / operations có nhận biết timeout | Giới hạn thời gian transaction theo khả năng manager/tài nguyên | Không tự thay thế mọi DB statement/lock timeout; không nhất thiết giới hạn thời gian chờ pool ở mọi bước |
| DB `lock_timeout` / lock wait timeout | Lấy locks | Dừng SQL bị chặn quá lâu | Không tăng pool hoặc giải quyết logic tranh lock |
| DB statement/query timeout | Thực thi SQL | Ngắt/chặn query quá lâu theo cơ chế DB/driver | Không bảo đảm transaction có thể tiếp tục commit sau lỗi |
| HTTP/request timeout | Caller hoặc gateway | Giới hạn thời gian chờ của request | Không tự rollback transaction nếu backend tiếp tục chạy |

Không nên chỉ tăng timeout để “giảm lỗi” trong hệ thống đang pool-starved: latency P99 và số threads bị giữ có thể tăng lên. Timeout nên đi cùng capacity planning, giảm thời gian giữ resource và xử lý lỗi/retry có kiểm soát.

### Retry cũng có thể làm tình hình tệ hơn

Nếu nhiều requests cùng timeout vì pool cạn rồi tự retry ngay lập tức, ta tạo **retry storm** và dồn áp lực trở lại pool/DB. Sử dụng backoff có jitter, bounded retries, circuit breaker/bulkhead và idempotency khi thật sự cần. Việc retry nên đặt ở ranh giới transaction phù hợp; không tái sử dụng một `TransactionStatus` đã hoàn tất hoặc đã rollback-only.

## 14. So sánh REQUIRES_NEW, REQUIRED và NESTED dưới góc resource

| Thuộc tính | `REQUIRED` | `REQUIRES_NEW` | `NESTED` (khi hỗ trợ savepoint) |
| --- | --- | --- | --- |
| Inner có physical transaction riêng khi outer đang active? | Không, tham gia T1 | **Có, T2 độc lập** | Không; savepoint trong T1 |
| Cần thêm JDBC connection cùng lúc cho một datasource? | Thường không | **Thường có**, khi outer đang giữ connection | Thường không, dùng connection T1 |
| Outer locks còn giữ khi inner chạy? | Cùng transaction | **Có**, T1 suspend không nhả lock | Locks vẫn thuộc physical T1; savepoint rollback có giới hạn riêng |
| Inner có thể commit độc lập và tồn tại khi outer rollback? | Không | **Có** | Không |
| Inner thất bại có thể gây outer rollback-only? | Có, theo rule/manager | Không tự propagate rollback-only từ T2 sang T1; exception vẫn có thể khiến outer rollback | Có thể rollback phần savepoint mà outer tiếp tục; tùy manager/driver |
| Có nguy cơ pool starvation do thêm connection? | Không vì propagation tự thân (với cùng resource) | **Cao hơn** | Thường thấp hơn theo đường savepoint |
| Có hỗ trợ trên mọi manager? | Rộng | Phụ thuộc transaction manager suspend/new transaction support | Không; phụ thuộc savepoints/JDBC/JPA configuration |

**`NESTED` không phải giải pháp thay thế khi cần audit commit độc lập.** Savepoint chỉ cho phép hoàn tác một phần thay đổi **trong cùng physical transaction**; nếu outer rollback, mọi thay đổi còn trong T1 cũng rollback.

## 15. Checklist khi code review REQUIRES_NEW

- [ ] **Vì sao inner phải commit độc lập?** Có invariant hay yêu cầu cụ thể, hay chỉ đang muốn né rollback của outer?
- [ ] **Inner có được gọi qua proxy không?** Không phải self-invocation hay object tạo bằng `new`.
- [ ] **Outer giữ physical connection từ lúc nào đến lúc nào?** Có lazy connection acquisition hay pool riêng không?
- [ ] **Có bao nhiêu outer transactions đồng thời ở peak load?** Đã đo active/idle/awaiting trên pool chưa?
- [ ] **Một thread có thể giữ bao nhiêu nested connections?** Có nhiều tầng `REQUIRES_NEW` không?
- [ ] **Pool có ít nhất một connection dự phòng khi tất cả outer giữ connection?** Đã sizing theo latency và DB limit, không chỉ N+1?
- [ ] **Inner có truy cập rows/foreign keys/indexes mà outer vừa khóa không?** Đã kiểm tra DB lock waits?
- [ ] **Thời gian giữ T1 và T2 có tối thiểu cần thiết?** Có HTTP/CPU/report xử lý bên trong transaction không?
- [ ] **Connection timeout, lock timeout và transaction timeout được cấu hình riêng rõ ràng?**
- [ ] **Khi inner không lấy được connection hoặc lock timeout, outer làm gì?** Rollback, retry, hay cho phép partial success có giám sát?
- [ ] **Inner commit, outer rollback có phải kết quả nghiệp vụ chấp nhận được?**
- [ ] **Đã có integration test/load test có giới hạn và quan sát SQL/pool metrics?**
- [ ] **Kết quả sau rollback/commit được xác nhận bằng query độc lập?**
- [ ] **Không tăng pool vô hạn vượt sức chịu của database?**

## 16. Câu hỏi tự kiểm tra

**Câu 1.** Outer đã mở T1 rồi gọi inner `REQUIRES_NEW`. “Spring suspend T1” có nghĩa là connection A được trả về pool ngay không?

*Không.* T1 vẫn còn physical transaction đang mở; resource đã gắn với T1 thường tiếp tục bị giữ. Inner phải mượn connection B nếu dùng JDBC local transaction cùng pool và T1 đã giữ connection A.

**Câu 2.** Vì sao pool size=1 có thể gây timeout ngay cả khi ứng dụng chỉ chạy một thread?

*Vì outer đang giữ connection duy nhất, còn inner REQUIRES_NEW phải có connection khác trước khi chạy. Outer không thể nhả connection cho đến khi lời gọi inner trả về; inner không thể chạy cho đến khi có connection.*

**Câu 3.** Nếu 10 threads đồng thời mỗi thread giữ một connection trong pool size=10 và tất cả bắt đầu REQUIRES_NEW, chuyện gì có thể xảy ra?

*Không còn connection cho inner; cả 10 threads có thể cùng chờ đến timeout. Pool size=11 cho phép ít nhất một inner tiến lên nếu không có người dùng khác, nhưng chưa chắc đủ throughput tốt.*

**Câu 4.** Pool size đã tăng lên 100, nhưng inner vẫn timeout khi cập nhật row outer đã UPDATE. Tại sao?

*Đây là lock wait chứ không phải thiếu connection. T1 vẫn giữ lock trên row; T2 có connection B nhưng không lấy được lock trong khi T1 không thể kết thúc trước khi inner trả về.*

**Câu 5.** Nếu inner `REQUIRES_NEW` ghi audit đã commit, sau đó outer ném exception và rollback, audit có còn không?

*Có thể còn.* Inner T2 commit độc lập với T1. Đó là semantics mong muốn của `REQUIRES_NEW`, nhưng phải kiểm tra có phù hợp nghiệp vụ hay không.

**Câu 6.** Thay `REQUIRES_NEW` bằng `NESTED` có luôn tránh được cạn pool và vẫn giữ commit độc lập không?

*Không.* `NESTED` dựa trên savepoint cùng physical transaction khi được hỗ trợ; thường không cần B nhưng **không có independent commit**. Nếu outer rollback thì dữ liệu inner vẫn rollback.

**Câu 7.** Vì sao test một request đơn lẻ thường không phát hiện sự cố sản xuất?

*Khi concurrency thấp, pool còn idle connections và lock contention ít. Khi nhiều outer transactions đồng thời giữ connection/locks, nhu cầu inner tăng đột biến; cần kiểm thử có concurrency, timeout và metrics.*

**Câu 8.** Có nên tăng `connectionTimeout` lên vài phút để tránh lỗi pool starvation?

*Không nên dùng làm cách chữa gốc.* Timeout dài chỉ kéo dài việc thread chờ connection. Nên giảm thời gian giữ outer resources, định cỡ pool theo workload, tránh lock conflict và có backpressure/retry phù hợp.

**Câu 9.** Nếu inner không sử dụng cùng datasource với outer, có còn rủi ro cạn pool không?

*Có thể.* Rủi ro chuyển sang pool của datasource inner và các workloads dùng pool đó. Nếu inner truy cập cùng DB rows qua datasource khác thì locks vẫn có thể tranh nhau. Cần xác định đúng datasource/transaction manager và tài nguyên vật lý.

**Câu 10.** Có thể suy ra `REQUIRES_NEW` không chạy vì không thấy pool thêm connection?

*Không đủ.* Có thể outer chưa lấy physical connection, metrics được đo sai thời điểm, dùng pool khác, hoặc inner bị self-invocation. Cần xác minh proxy, transaction manager, actual connections và SQL trên các sessions thực tế.

## 17. Kết luận cần ghi nhớ

- **`REQUIRES_NEW` tạo physical transaction độc lập** với outer; inner có thể commit trước khi outer hoàn tất.
- **Suspend của Spring không kết thúc outer transaction và không mặc nhiên trả connection/nhả database locks.**
- Với cùng JDBC pool, outer giữ connection A và inner cần B: **pool phải đủ cho các connections đồng thời**, không chỉ số request threads.
- **Pool size bằng số outer threads** có thể làm mọi inner cùng chờ; thêm ít nhất một slot tránh kẹt vòng đơn giản nhưng chưa đủ để bảo đảm latency/throughput.
- **Đủ connection chưa chắc đủ lock**: inner dùng B vẫn có thể chờ khóa mà T1 nắm giữ, nhất là khi hai scopes đụng cùng row/index/foreign key.
- **Tăng pool không chữa lock wait**, tăng timeout không tạo capacity. Phải tìm đúng choke point.
- **Giảm thời gian giữ outer transaction, xem lại ranh giới nghiệp vụ và test hai dạng lỗi** là trọng tâm thiết kế an toàn.

## Tài liệu tham khảo chính thức

1. [Spring Framework — Transaction Propagation](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-propagation.html): `PROPAGATION_REQUIRES_NEW`, cảnh báo connection pool exhaustion, điều kiện pool lớn hơn số concurrent threads ít nhất một connection, và so sánh `REQUIRED`/`NESTED`.
2. [Spring Framework — Declarative Transaction Implementation](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-decl-explained.html): transaction proxy, `TransactionInterceptor`, manager begin/suspend/commit/resume.
3. [Spring Framework — `AbstractPlatformTransactionManager` Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/transaction/support/AbstractPlatformTransactionManager.html): hỗ trợ transaction suspension/resumption và commit/rollback lifecycle.
4. [Spring Framework — JDBC Connection Management](https://docs.spring.io/spring-framework/reference/data-access/jdbc/connections.html): `DataSourceTransactionManager`/`JdbcTransactionManager`, JDBC connection binding và `LazyConnectionDataSourceProxy`.
5. [HikariCP — Connection Pool Configuration](https://github.com/brettwooldridge/HikariCP#configuration-knobs-baby): `maximumPoolSize`, `connectionTimeout`, `minimumIdle`.
6. [HikariCP — `HikariPoolMXBean`](https://javadoc.io/doc/com.zaxxer/HikariCP/5.1.0/com/zaxxer/hikari/HikariPoolMXBean.html): active/idle/total/waiting connections.
7. [PostgreSQL — Monitoring Database Activity](https://www.postgresql.org/docs/current/monitoring-stats.html): `pg_stat_activity` và wait events.
8. [PostgreSQL — Explicit Locking](https://www.postgresql.org/docs/current/explicit-locking.html): locks, deadlocks và cách engine quản lý blocking transactions.
