# TransactionSynchronization và callback trong Spring Framework

## 1. Transaction synchronization là gì?

Trong Spring Framework, **transaction synchronization** là cơ chế cho phép mã ứng dụng hoặc thành phần hạ tầng đăng ký callback để nhận thông báo tại những mốc trong vòng đời một transaction: trước commit, trước khi hoàn tất, sau commit, và sau khi hoàn tất (commit hoặc rollback). API cốt lõi cho transaction quản lý bằng `PlatformTransactionManager` là:

- `org.springframework.transaction.support.TransactionSynchronization`: giao diện khai báo các callback.
- `org.springframework.transaction.support.TransactionSynchronizationManager`: giữ và quản lý các synchronization đang đăng ký trong ngữ cảnh transaction hiện tại.
- `PlatformTransactionManager`, chẳng hạn `DataSourceTransactionManager`: thực thi transaction và kích hoạt callback tại thời điểm tương ứng.

Điều này đặc biệt quan trọng khi **Spring Framework Application Events** gắn với nghiệp vụ có transaction. Ví dụ một đơn hàng chỉ nên được thông báo cho hệ thống ngoài sau khi bản ghi đơn hàng commit thành công. Ngược lại, nếu transaction rollback, việc thông báo như thể đơn hàng đã được tạo sẽ làm sai trạng thái giữa các hệ thống.

Transaction synchronization cho phép đặt logic vào một **giai đoạn transaction** cụ thể. Tuy nhiên nó không tự biến tác vụ thành message được lưu bền vững, không thay thế một transaction khác khi cần ghi dữ liệu sau commit và không có nghĩa các bước là một distributed transaction.

## 2. Phân biệt callback với transaction chính

Một transaction thường đi qua đường đi khái quát:

```text
Bắt đầu transaction
        |
Thực thi logic nghiệp vụ, thay đổi dữ liệu
        |
        +---- Chọn COMMIT ----------------------------+
        |                                              |
        |   beforeCommit(readOnly)                     |
        |   beforeCompletion()                         |
        |   database commit                            |
        |   afterCommit()                              |
        |   afterCompletion(COMMITTED)                  |
        |                                              |
        +----------------------------------------------+
        |
        +---- Chọn ROLLBACK ---------------------------+
                                                       |
            beforeCompletion()                         |
            database rollback                          |
            afterCompletion(ROLLED_BACK)                |
                                                       |
            Kết thúc, dọn tài nguyên, trả quyền điều khiển
```

Sơ đồ mô tả các mốc chính của một transaction thông thường do `AbstractPlatformTransactionManager` điều phối. Nó bỏ qua những chi tiết như suspend/resume, flush, rollback do lỗi ngay lúc commit, JTA, transaction lồng nhau, và thứ tự callback giữa nhiều synchronization.

**Điểm mấu chốt:** `beforeCommit` chưa bảo đảm dữ liệu chắc chắn commit. Ngay sau đó, commit vẫn có thể thất bại và transaction có thể rollback. Ngược lại, `afterCommit` chỉ chạy trên nhánh commit thành công; lúc ấy thay đổi DB gốc đã được commit.

## 3. Những callback quan trọng của TransactionSynchronization

| Callback | Khi nào được gọi? | Mục đích phù hợp | Điều cần tránh |
| --- | --- | --- | --- |
| `beforeCommit(boolean readOnly)` | Trước khi tiến hành commit | Kiểm tra/flush dữ liệu cần hoàn tất trước commit | Gửi email hoặc side effect ngoài hệ thống và giả định chắc chắn sẽ commit |
| `beforeCompletion()` | Trước khi hoàn tất transaction, kể cả khi rollback | Dọn trạng thái tạm, đóng tài nguyên phụ | Dùng làm tín hiệu “sắp commit thành công” |
| `afterCommit()` | Sau khi transaction commit thành công | Kích hoạt bước chỉ hợp lệ sau commit, thông báo, lên lịch job | Nghĩ rằng có thể làm transaction gốc rollback nếu callback này lỗi |
| `afterCompletion(int status)` | Sau khi transaction kết thúc | Cleanup bất kể kết quả; biết commit, rollback hay chưa rõ | Dùng status `COMMITTED` khi thực tế status chưa rõ |
| `flush()` | Khi cơ chế transaction yêu cầu flush đồng bộ | Đẩy trạng thái tạm của tài nguyên đến transaction resource | Giả định mọi transaction luôn tự gọi callback này vào cùng một thời điểm |
| `suspend()` / `resume()` | Khi synchronization bị tạm ngưng/khôi phục, tùy transaction manager | Unbind/bind lại tài nguyên thread-bound do synchronization sở hữu | Tự ý thao tác resource thuộc sở hữu framework |
| `getOrder()` | Khi framework sắp xếp các synchronization | Xác định ưu tiên callback so với các synchronization khác | Xem thứ tự callback là phương án thay thế thiết kế phụ thuộc nghiệp vụ |

Một `TransactionSynchronization` mới có các phương thức mặc định, vì thế có thể chỉ override callback cần dùng. Cơ chế có thể kích hoạt các callback ở những thời điểm khác nhau tùy transaction manager và cấu hình. Không nên giả định mọi hook đều xuất hiện trong mọi giao dịch.

**Giá trị status của `afterCompletion(int status)`** nằm trên chính interface:
- `TransactionSynchronization.STATUS_COMMITTED`: giao dịch đã commit.
- `TransactionSynchronization.STATUS_ROLLED_BACK`: giao dịch đã rollback.
- `TransactionSynchronization.STATUS_UNKNOWN`: không xác định chắc chắn trạng thái kết thúc; cần xử lý thận trọng.

Interface **không có `afterRollback()` riêng**. Nếu cần làm việc sau rollback, kiểm tra `STATUS_ROLLED_BACK` trong `afterCompletion` hoặc dùng listener event với `TransactionPhase.AFTER_ROLLBACK`.

## 4. Đăng ký synchronization đúng cách

Trong transaction **sử dụng transaction manager của Spring**, nơi cần gắn callback gọi:

```java
if (!TransactionSynchronizationManager.isSynchronizationActive()
        || !TransactionSynchronizationManager.isActualTransactionActive()) {
    throw new IllegalStateException("Requires an active Spring transaction");
}

TransactionSynchronizationManager.registerSynchronization(
    new TransactionSynchronization() {
        @Override
        public void afterCommit() {
            // Chạy sau khi transaction hiện tại commit thành công.
        }

        @Override
        public void afterCompletion(int status) {
            // Cleanup và quan sát kết quả kết thúc.
        }
    }
);
```

Đây là **đoạn minh họa tích hợp**, không phải file Java độc lập. Phải dùng trong service đang chạy với một transaction Spring phù hợp, ví dụ `@Transactional` qua proxy Spring hoặc `TransactionTemplate`.

- `isSynchronizationActive()` cho biết có ngữ cảnh để đăng ký callback. Nếu false, `registerSynchronization` ném `IllegalStateException`.
- `isActualTransactionActive()` giúp phân biệt trường hợp framework kích hoạt synchronization nhưng không có transaction thực tế (có thể gặp với một số propagation và synchronization policy). Nếu side effect chỉ hợp lệ sau **commit thực tế**, kiểm tra cả hai điều kiện.
- `TransactionSynchronizationManager` ở cơ chế imperative truyền thống sử dụng ngữ cảnh gắn với **thread**. Không tự động mang synchronization sang thread mới, `@Async` hay một tác vụ chạy qua executor. Trong ứng dụng reactive, có API transaction synchronization riêng dựa trên Reactor Context.

Một hàm đăng ký callback nên được gọi **khi transaction hiện tại vẫn đang hoạt động**, không phải sau khi `@Transactional` service đã trả về. Nếu việc đăng ký được thực hiện sau đó, transaction manager không còn mốc lifecycle để thông báo.

## 5. Ví dụ Java 17+ chạy được: commit và rollback

Ví dụ này dùng `TransactionTemplate`, `DataSourceTransactionManager`, `JdbcTemplate` và H2 in-memory database. Ta đăng ký **cùng một nhóm callback** cho một transaction sẽ commit và một transaction chủ động rollback, sau đó kiểm tra DB chỉ còn bản ghi đã commit.

Không cần Spring Boot hay container ngoài.

Cấu trúc:

```text
transaction-synchronization-demo/
├── build.gradle
└── src/main/java/demo/TransactionSynchronizationDemo.java
```

Nội dung `build.gradle`:

```groovy
plugins {
    id 'java'
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework:spring-jdbc:6.1.21'
    runtimeOnly 'com.h2database:h2:2.3.232'
}

application {
    mainClass = 'demo.TransactionSynchronizationDemo'
}
```

`spring-jdbc` mang theo các thành phần Spring Transaction cần thiết. H2 cung cấp JDBC driver tại runtime.

Nội dung `src/main/java/demo/TransactionSynchronizationDemo.java`:

```java
package demo;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DataSourceTransactionManager;
import org.springframework.jdbc.datasource.DriverManagerDataSource;
import org.springframework.transaction.support.TransactionSynchronization;
import org.springframework.transaction.support.TransactionSynchronizationManager;
import org.springframework.transaction.support.TransactionTemplate;

public final class TransactionSynchronizationDemo {

    private static String statusName(int status) {
        return switch (status) {
            case TransactionSynchronization.STATUS_COMMITTED -> "COMMITTED";
            case TransactionSynchronization.STATUS_ROLLED_BACK -> "ROLLED_BACK";
            default -> "UNKNOWN";
        };
    }

    private static void registerCallbacks(String label) {
        if (!TransactionSynchronizationManager.isSynchronizationActive()
                || !TransactionSynchronizationManager.isActualTransactionActive()) {
            throw new IllegalStateException("An active transaction is required");
        }

        TransactionSynchronizationManager.registerSynchronization(
            new TransactionSynchronization() {
                @Override
                public void beforeCommit(boolean readOnly) {
                    System.out.println(
                        label + " beforeCommit(readOnly=" + readOnly + ")"
                    );
                }

                @Override
                public void beforeCompletion() {
                    System.out.println(label + " beforeCompletion");
                }

                @Override
                public void afterCommit() {
                    System.out.println(label + " afterCommit");
                }

                @Override
                public void afterCompletion(int status) {
                    System.out.println(
                        label + " afterCompletion(" + statusName(status) + ")"
                    );
                }
            }
        );
    }

    public static void main(String[] args) {
        DriverManagerDataSource dataSource = new DriverManagerDataSource();
        dataSource.setDriverClassName("org.h2.Driver");
        dataSource.setUrl(
            "jdbc:h2:mem:transaction_sync_demo;DB_CLOSE_DELAY=-1"
        );
        dataSource.setUsername("sa");
        dataSource.setPassword("");

        JdbcTemplate jdbc = new JdbcTemplate(dataSource);
        jdbc.execute(
            "CREATE TABLE demo_event " +
            "(id INT PRIMARY KEY, description VARCHAR(50))"
        );

        DataSourceTransactionManager manager =
            new DataSourceTransactionManager(dataSource);
        TransactionTemplate transactions = new TransactionTemplate(manager);

        System.out.println("=== COMMIT ===");
        transactions.executeWithoutResult(status -> {
            registerCallbacks("commit");
            jdbc.update(
                "INSERT INTO demo_event(id, description) VALUES (?, ?)",
                1, "committed"
            );
            System.out.println("commit business saved");
        });
        System.out.println("commit returned");

        System.out.println("=== ROLLBACK ===");
        transactions.executeWithoutResult(status -> {
            registerCallbacks("rollback");
            jdbc.update(
                "INSERT INTO demo_event(id, description) VALUES (?, ?)",
                2, "rolled back"
            );
            System.out.println("rollback business saved");
            status.setRollbackOnly();
        });
        System.out.println("rollback returned");

        Integer persisted = jdbc.queryForObject(
            "SELECT COUNT(*) FROM demo_event", Integer.class
        );
        System.out.println("rows persisted=" + persisted);
    }
}
```

Chạy bằng JDK 17+ và Gradle có sẵn:

```bash
gradle run --quiet
```

**Kết quả stdout kỳ vọng từ chương trình:**

```text
=== COMMIT ===
commit business saved
commit beforeCommit(readOnly=false)
commit beforeCompletion
commit afterCommit
commit afterCompletion(COMMITTED)
commit returned
=== ROLLBACK ===
rollback business saved
rollback beforeCompletion
rollback afterCompletion(ROLLED_BACK)
rollback returned
rows persisted=1
```

Điểm cần kiểm tra trong output:

1. Cả hai transaction đều ghi vào DB ở trong `TransactionTemplate`, nhưng chỉ bản ghi đầu tồn tại sau khi hoàn tất (`rows persisted=1`).
2. Đường **commit** gọi `beforeCommit`, `beforeCompletion`, `afterCommit` và `afterCompletion(COMMITTED)`. Thuộc tính `readOnly` của `TransactionTemplate` mặc định là `false`.
3. Đường **rollback** không gọi `beforeCommit` hay `afterCommit`; nó gọi `beforeCompletion` và `afterCompletion(ROLLED_BACK)`.
4. Dòng `commit returned` / `rollback returned` được in **sau** các callback vì các callback trong ví dụ chạy đồng bộ trong vòng kết thúc transaction của `TransactionTemplate`.

Bài dùng `DriverManagerDataSource` cho demo đơn giản; hệ thống thật nên dùng connection pool được quản lý. Việc gọi `JdbcTemplate` trong transaction của `DataSourceTransactionManager` dùng đúng transaction-bound connection theo cơ chế Spring nên phần insert rollback thực sự.

## 6. Điều gì xảy ra khi callback ném lỗi?

Lỗi từ callback có ngữ nghĩa khác nhau theo thời điểm:

| Hook | Hành vi lỗi cần hiểu |
| --- | --- |
| `beforeCommit` | `RuntimeException` có thể lan đến quá trình commit, và trong đường đi transaction manager thông thường dẫn đến rollback. `beforeCompletion` vẫn được kích hoạt khi `beforeCommit` lỗi. |
| `beforeCompletion` | Lỗi được framework ghi log thay vì coi đây là cách đáng tin để hủy commit. Nên dành hook cho dọn trạng thái và tránh side effect dễ lỗi. |
| `afterCommit` | Transaction chính **đã commit**. Runtime exception có thể lan về caller, nhưng không thể đảo ngược commit trước đó. |
| `afterCompletion` | Chủ yếu để cleanup; lỗi được ghi log, không dùng làm điều kiện thay đổi kết quả transaction đã hoàn tất. |

Với callback `afterCommit`, việc caller nhận exception không tự chứng minh dữ liệu DB đã rollback. Đây là nguồn lỗi nghiệp vụ thường gặp:

```text
DB commit thành công
    -> afterCommit gọi dịch vụ thông báo
       -> dịch vụ thông báo lỗi
    -> caller có thể nhận exception
    -> bản ghi DB đã commit vẫn tồn tại
```

Để xử lý điều này, hãy theo dõi kết quả riêng của tác vụ sau commit, thiết kế retry/idempotency và tránh cho caller gửi lại toàn bộ nghiệp vụ một cách mù quáng. Trường hợp cần đảm bảo chắc chắn thông báo được gửi dù tiến trình crash, nên dùng **transactional outbox** hoặc hạ tầng giao nhận bền vững phù hợp.

## 7. Quan hệ với Spring Application Events

Trong Spring Framework Application Events có hai kiểu listener cần phân biệt:

### 7.1. `@EventListener`: xử lý ngay khi event được phát

Với multicaster đồng bộ mặc định, `@EventListener` nhận event trong lời gọi `publishEvent`. Nếu publisher gọi `publishEvent` **bên trong transaction**, listener cũng có thể chạy trước khi transaction commit. Gửi email hoặc gọi API từ listener thông thường có rủi ro tạo side effect trong lúc giao dịch DB sau đó rollback.

Ví dụ minh họa trong Spring-managed bean:

```java
@EventListener
public void onOrderPlaced(OrderPlacedEvent event) {
    // Được dispatch ngay; transaction của publisher có thể chưa commit.
    auditService.recordEventObserved(event.orderId());
}
```

Đoạn này giả định `OrderPlacedEvent` và `auditService` có sẵn; nó **không phải chương trình chạy độc lập**.

### 7.2. `@TransactionalEventListener`: xử lý theo transaction phase

`@TransactionalEventListener` cung cấp cách viết khai báo để gắn việc xử lý event với transaction synchronization. Các phase:

| `TransactionPhase` | Ý nghĩa |
| --- | --- |
| `BEFORE_COMMIT` | Xử lý trước khi commit |
| `AFTER_COMMIT` | Xử lý sau commit thành công; đây là **mặc định** |
| `AFTER_ROLLBACK` | Xử lý sau rollback |
| `AFTER_COMPLETION` | Xử lý sau transaction kết thúc, bất kể commit/rollback |

Ví dụ trong một Spring-managed bean:

```java
@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
public void onOrderPlaced(OrderPlacedEvent event) {
    notificationJobService.enqueue(event.orderId());
}
```

Để biên dịch đoạn tích hợp này, import `org.springframework.transaction.event.TransactionalEventListener` và `org.springframework.transaction.event.TransactionPhase`; ứng dụng cần khai báo `OrderPlacedEvent`, `notificationJobService` và cấu hình transaction/event phù hợp.

Trong service giao dịch, có thể phát một event:

```java
@Transactional
public void placeOrder(Order order) {
    orderRepository.save(order);
    applicationEventPublisher.publishEvent(
        new OrderPlacedEvent(order.getId())
    );
}
```

Đây cũng là **đoạn minh họa trong ứng dụng**, giả định các kiểu, field và component đã được khai báo. Listener `AFTER_COMMIT` được ràng buộc với **kết quả transaction**, chứ không được chạy ngay tại lúc `publishEvent` bên trong transaction đang mở.

**Lưu ý hai điểm quan trọng:**

- Theo mặc định, `@TransactionalEventListener` **không thực thi nếu không có transaction thích hợp**. Có thể đặt `fallbackExecution = true` để cho phép thực thi trong trường hợp không có transaction, nhưng điều đó làm thay đổi ngữ nghĩa “chỉ sau commit”, nên phải cân nhắc.
- `TransactionPhase.AFTER_COMMIT` mang ý nghĩa sau commit, nhưng cơ chế callback nội bộ của transactional event listener được thực hiện trong giai đoạn after-completion của synchronization. Không dựa vào thứ tự tương đối giữa một listener event `AFTER_COMMIT` và callback thủ công `afterCommit()` để tạo phụ thuộc nghiệp vụ. Nếu có phụ thuộc thực sự, hãy điều phối tường minh.

### 7.3. Khi nào dùng callback thủ công?

Dùng `TransactionSynchronizationManager.registerSynchronization(...)` khi muốn tự kiểm soát lifecycle của một tài nguyên hoặc đơn vị công việc được đăng ký trong transaction hiện tại: cleanup, flush, khôi phục trạng thái tài nguyên, hoặc một callback kỹ thuật theo kết quả giao dịch.

Dùng `@TransactionalEventListener` khi mục tiêu chính là **xử lý một event nghiệp vụ** gắn với phase của transaction. Annotation làm rõ ý định trong kiến trúc event-driven và dễ tổ chức consumer độc lập hơn.

Cả hai vẫn phải xét ngoại lệ, ranh giới transaction, thứ tự callback và độ bền của side effect. Chọn API không tự cung cấp giao nhận guaranteed exactly-once.

## 8. Vấn đề tài nguyên vẫn bound sau commit

Sau khi physical transaction commit, Spring có thể vẫn đang trong quá trình cleanup, với resource/connection còn gắn với thread trong một phần callback lifecycle. Vì thế, code DB trong `afterCommit` hoặc một listener `AFTER_COMMIT` có thể vẫn “thấy” resource cũ, nhưng các thay đổi mới **không được đảm bảo commit như một transaction mới**.

Nếu phải tạo một bản ghi DB mới **sau** khi transaction gốc commit, hãy gọi một Spring service khác mở transaction mới, ví dụ:

```java
@Service
public class NotificationJobService {

    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void createJob(long orderId) {
        jobRepository.insertPendingJob(orderId);
    }
}
```

Đây là đoạn **minh họa tích hợp**, cần `@Service`, `@Transactional`, `Propagation`, `jobRepository` và kiểu tương ứng trong ứng dụng. `REQUIRES_NEW` tạo transaction riêng theo chính sách transaction manager. Phải gọi phương thức qua proxy Spring phù hợp; **self-invocation trong cùng bean** thường bỏ qua interceptor `@Transactional` ở chế độ proxy mặc định.

Ngay cả khi có `REQUIRES_NEW`, lỗi sau commit vẫn không rollback transaction gốc. Nếu job mới là thông tin **bắt buộc phải tồn tại đồng thời với order**, thiết kế mạnh hơn là lưu **outbox/job record trong chính transaction tạo order**, rồi xử lý việc gửi sau đó.

## 9. Các tình huống nâng cao

### 9.1. Propagation `REQUIRES_NEW`, `NESTED` và suspend/resume

Nếu một transaction gọi phương thức với `REQUIRES_NEW`, transaction bên ngoài có thể bị suspend; transaction mới bắt đầu và có synchronization riêng. Sau khi transaction mới hoàn tất, transaction ngoài được resume. Vì vậy, callback đăng ký trong mỗi transaction gắn với **phạm vi transaction tương ứng**.

Với `NESTED` dựa trên JDBC savepoint, việc rollback về savepoint không giống rollback toàn bộ transaction ngoài. Nếu ứng dụng tạo logic cần biết chính xác savepoint, Spring Framework **6.2+** bổ sung callback `savepoint(Object savepoint)` và `savepointRollback(Object savepoint)` cho `TransactionSynchronization`. Những callback này không có trong interface phiên bản 6.1.x được dùng ở ví dụ chính. Không dựa vào `afterCompletion(ROLLED_BACK)` để đại diện cho mọi lần rollback đến savepoint: transaction ngoài có thể vẫn tiếp tục và commit.

### 9.2. Ordering

`TransactionSynchronization` hỗ trợ contract `Ordered`, và một synchronization có thể cung cấp `getOrder()`. Framework cũng đăng ký những synchronization nội bộ cho tài nguyên của nó. Ưu tiên gọi callback có thể quan trọng cho cleanup/infrastructure, nhưng **không nên dùng thứ tự ngầm** để buộc các bước nghiệp vụ phải phụ thuộc nhau.

`@Order` trên một `@EventListener` thông thường là việc sắp thứ tự **dispatch listener**; `getOrder()` của synchronization là việc sắp thứ tự **callback trong vòng đời transaction**. Hai khái niệm không tương đương.

### 9.3. Reactive transaction và async

Các ví dụ bên trên áp dụng cho mô hình **imperative** với `PlatformTransactionManager` và `TransactionSynchronizationManager` dùng ThreadLocal. Reactive transaction của Spring dùng API `org.springframework.transaction.reactive.TransactionSynchronizationManager` và transaction context theo Reactor; không được lấy `isActualTransactionActive()` trên ThreadLocal rồi kết luận trạng thái transaction reactive.

Tương tự, nếu phát event sang một thread khác, callback đăng ký ở thread đó không tự gắn với transaction của thread tạo event. Với reactive event listener từ Spring 6.1+, ngữ cảnh transaction reactive cần được mang theo cách phù hợp với API và event context. Không coi `@Async` là phương án kế thừa transaction context.

### 9.4. Hạn chế làm việc nặng trong callback

Callback được kích hoạt trong chính luồng kết thúc transaction trong mô hình imperative thông thường. Gọi HTTP kéo dài 10 giây trong `afterCommit` có thể giữ request/worker đang chờ `commit()` trả về dù database đã commit. Cân nhắc chuyển phần việc sau commit sang job/queue có giám sát, nhưng phải cân nhắc nguy cơ mất job nếu chỉ giao vào executor ở bộ nhớ.

## 10. Kiểm thử callback và event theo phase

Một bộ test tốt không chỉ kiểm tra một đường commit thành công:

| Kịch bản | Thiết kế test | Điều cần xác nhận |
| --- | --- | --- |
| Commit | Dùng `TransactionTemplate`, đăng ký callback, ghi DB rồi commit | `beforeCommit`, `beforeCompletion`, `afterCommit`, `afterCompletion(COMMITTED)` theo mốc dự kiến; dữ liệu tồn tại |
| Rollback chủ động | Gọi `status.setRollbackOnly()` | Không có `afterCommit`; nhận `afterCompletion(ROLLED_BACK)`; thay đổi DB bị đảo |
| Exception trước commit | Ném `RuntimeException` trong logic nghiệp vụ | Transaction rollback; callback theo nhánh rollback; lỗi không bị nuốt |
| Exception trong `beforeCommit` | Cho callback ném lỗi và quan sát transaction | Không giả định đã commit; xác minh rollback, `beforeCompletion` và outcome thật |
| Exception trong `afterCommit` | Cho callback ném lỗi sau commit | Dữ liệu nghiệp vụ vẫn đã commit; cần quan sát lỗi tác vụ hậu commit |
| Event ngoài transaction | Phát event khi không có transaction | `@TransactionalEventListener` mặc định không xử lý; nếu `fallbackExecution` bật thì test ngữ nghĩa mới |
| `REQUIRES_NEW` | Mở transaction mới trong transaction ngoài | Callback từng phạm vi chạy theo kết quả transaction của chính nó |

Với `@Transactional` trong integration test, cần cẩn thận: một số test framework tự mở transaction và rollback khi kết thúc, khiến listener `AFTER_COMMIT` **không chạy**. Nếu mục tiêu là kiểm tra commit thật, có thể dùng `TransactionTemplate` hoặc cơ chế kết thúc transaction do test framework hỗ trợ, sau đó kiểm tra side effect đúng thời điểm.

Trong test, tránh chỉ assert danh sách callback theo thứ tự khi có nhiều synchronization của framework hoặc nhiều listener khác nhau. Đặt trọng tâm vào **phase đúng, trạng thái cuối, số lần gọi, rollback thật, và tính idempotent**.

## 11. Sai lầm thường gặp

1. **Đưa email/API vào `beforeCommit` vì nghĩ chắc chắn sẽ commit.** Transaction vẫn có thể rollback; side effect ngoài không rollback theo DB.
2. **Xem `beforeCompletion` tương đương commit.** Nó cũng được gọi trên nhánh rollback.
3. **Chỉ xử lý thành công trong `afterCommit` mà không có retry.** Lỗi sau commit không thể hủy commit cũ.
4. **Ghi thêm DB trong `afterCommit` nhưng không mở transaction mới.** Resource có thể vẫn bound, khiến trạng thái commit bị hiểu sai.
5. **Đăng ký callback khi không có synchronization active.** `registerSynchronization` có thể ném `IllegalStateException`.
6. **Đăng ký callback trên thread `@Async` rồi mong nó bám theo transaction gốc.** ThreadLocal transaction context không tự truyền qua thread.
7. **Giả định `@TransactionalEventListener` chạy cả khi không có transaction.** Mặc định không; cần hiểu rõ `fallbackExecution`.
8. **Dùng callback để điều phối một chuỗi nghiệp vụ phức tạp theo thứ tự ẩn.** Một workflow hoặc bước event tiếp theo rõ ràng dễ theo dõi và retry hơn.
9. **Coi `AFTER_COMMIT` là giao nhận bền vững.** Nếu tiến trình dừng đúng thời điểm không có bằng chứng event đã được lưu để xử lý tiếp.
10. **Coi rollback savepoint như rollback toàn transaction.** Với nested transaction, trạng thái callback cần được hiểu theo transaction và savepoint thực tế.

## 12. Checklist áp dụng

- Transaction là imperative hay reactive? Transaction manager có đang quản lý synchronization không?
- Callback được đăng ký **bên trong** transaction thực tế và trong thread/context phù hợp chứ?
- Tác vụ cần chạy trước commit, sau commit, sau rollback, hay cleanup bất kể kết quả?
- Có phân biệt `beforeCommit`, `beforeCompletion`, `afterCommit` và `afterCompletion` đúng nghĩa không?
- Nếu callback sau commit lỗi, hệ thống có hiểu DB đã commit và có kế hoạch retry/idempotency không?
- Nếu thao tác sau commit phải ghi DB, đã tạo transaction mới đúng cách chưa?
- Nếu không được phép mất thông báo/side effect, đã có outbox hoặc cơ chế giao nhận bền vững chưa?
- Test có xác nhận cả commit, rollback, ngoại lệ và trường hợp không có transaction không?

**Ghi nhớ:** `TransactionSynchronization` cung cấp callback theo vòng đời transaction. `@TransactionalEventListener` là cách khai báo để xử lý sự kiện theo phase. Cả hai đều cần dùng đúng ranh giới commit và cơ chế phục hồi khi side effect nằm ngoài transaction.

## Tài liệu tham khảo

- [Spring Framework API — TransactionSynchronization](https://docs.spring.io/spring-framework/docs/6.1.21/javadoc-api/org/springframework/transaction/support/TransactionSynchronization.html)
- [Spring Framework API — TransactionSynchronizationManager](https://docs.spring.io/spring-framework/docs/6.1.21/javadoc-api/org/springframework/transaction/support/TransactionSynchronizationManager.html)
- [Spring Framework — Transaction-bound Events](https://docs.spring.io/spring-framework/reference/data-access/transaction/event.html)
- [Spring Framework API — TransactionalEventListener](https://docs.spring.io/spring-framework/docs/6.1.21/javadoc-api/org/springframework/transaction/event/TransactionalEventListener.html)
- [Spring Framework API — DataSourceTransactionManager](https://docs.spring.io/spring-framework/docs/6.1.21/javadoc-api/org/springframework/jdbc/datasource/DataSourceTransactionManager.html)
