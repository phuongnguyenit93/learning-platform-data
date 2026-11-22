# Bắt lỗi, nuốt lỗi hoặc đổi loại ngoại lệ làm thay đổi kết quả rollback trong Spring

## 1. Quy tắc cốt lõi: transaction advice nhìn thấy lỗi nào?

Trong Spring Framework, một phương thức `@Transactional` không tự động rollback vì “bên trong đã từng xảy ra lỗi”. Với declarative transaction theo Spring AOP, **`TransactionInterceptor` xét kết quả đi qua ranh giới method được advice quản lý**. Nếu method trả về bình thường, advice thường đi theo đường commit (trừ khi transaction đã rollback-only, tài nguyên lỗi hoặc có quy tắc hoàn tất đặc biệt). Nếu một exception thoát ra, advice áp dụng **rollback rules** cho exception được quan sát ở ranh giới đó.

Vì vậy, ba thao tác tưởng là xử lý lỗi thông thường có thể làm kết quả khác hẳn:

1. **Bắt lỗi rồi nuốt lỗi** ngay trong method transactional: caller thấy thành công, advice không nhận exception đó và có thể commit dữ liệu trước khi lỗi xảy ra.
2. **Bắt lỗi bên ngoài proxy**: lỗi đã đi qua transaction advice, nên quyết định rollback/commit thường đã được áp dụng; caller bắt lỗi để phản hồi HTTP hoặc ghi log không đảo ngược quyết định đã hoàn tất.
3. **Đổi loại ngoại lệ** (wrap/translate) **trước khi lỗi đi qua boundary**: advice thấy exception mới. Chuyển checked `IOException` thành unchecked `IllegalStateException` có thể biến “commit theo mặc định” thành “rollback”; chuyển ngược chiều có thể tạo tác dụng đối nghịch.

Đây là bài về **vị trí catch, loại exception tại điểm chặn, và trạng thái rollback-only**. Một method annotated nhưng bị gọi bằng self-invocation không đi qua proxy sẽ không tự có lần interception riêng; để các tình huống sau có ý nghĩa, giả định invocation đến từ bean khác qua Spring proxy, trừ khi nói khác.

### Sơ đồ quyết định tổng quát

~~~mermaid
flowchart TD
    A["Caller -> Spring proxy"] --> B["TransactionInterceptor mở/tham gia scope"]
    B --> C["Thực thi method @Transactional"]
    C --> D{"Có exception thoát khỏi method?"}
    D -->|"Không; catch và return"| E{"Có rollback-only hoặc lỗi tài nguyên?"}
    D -->|"Có"| F["Xác định loại exception cuối cùng ở boundary"]
    F --> G{"Rollback rule có khớp?"}
    G -->|"Có, rollback"| H["Rollback hoặc đánh dấu rollback-only"]
    G -->|"Không / noRollbackFor"| I["Yêu cầu commit rồi chuyển tiếp exception"]
    E -->|"Không"| J["Yêu cầu commit"]
    E -->|"Có"| H
    J --> K["Hoàn tất; caller nhận return"]
    I --> L["Caller nhận exception sau khi boundary xử lý"]
    H --> M["Hoàn tất rollback hoặc đợi outer scope"]
~~~

Chữ “commit” trong sơ đồ là **yêu cầu commit**, không cam kết thành công trong mọi trường hợp: database constraint, lỗi connection, rollback-only từ inner scope, hoặc tài nguyên ngoài giao dịch có thể làm kết quả khác. Với `PROPAGATION_REQUIRED` tham gia giao dịch đã có, việc hoàn tất logical scope còn phụ thuộc physical transaction bên ngoài.

## 2. Bảng quy tắc mặc định và các giới hạn

Với `@Transactional` của Spring Framework theo **mặc định thông dụng**:

| Exception thoát khỏi method transactional | Quyết định mặc định |
| --- | --- |
| `RuntimeException` và các lớp con (`IllegalStateException`, `DataAccessException`, ...) | Rollback |
| `Error` và các lớp con | Rollback |
| Checked `Exception` (`IOException`, ngoại lệ nghiệp vụ checked, ...) | Không tự rollback; Spring có thể commit rồi chuyển exception ra caller |
| Không có exception thoát ra, method return bình thường | Thường commit, trừ khi đã bị rollback-only hoặc lỗi khi hoàn tất |

**Không có nghĩa checked exception “luôn commit” hay RuntimeException “luôn rollback”.** Các thuộc tính `rollbackFor`, `noRollbackFor`, rule toàn cục, transaction đã rollback-only và trạng thái tài nguyên có thể thay đổi hành vi.

Các ví dụ runnable trong bài dùng **Spring Boot 3.3.5 / Spring Framework 6.1.x** và rollback policy mặc định để kết quả rõ ràng. Từ **Spring Framework 6.2**, ứng dụng có thể cấu hình `@EnableTransactionManagement(rollbackOn = RollbackOn.ALL_EXCEPTIONS)`; khi bật, checked exception cũng là lý do rollback mặc định. Rule riêng trên method vẫn được ưu tiên khi khớp. Không suy đoán policy chỉ từ việc thấy annotation; phải biết framework version và cấu hình thực tế.

**Điểm nhìn nhận quan trọng:** Spring mặc định dựa vào exception mà transaction infrastructure **thấy tại thời điểm hoàn tất scope**, không duyệt lịch sử exception đã xuất hiện và bị xử lý trong Java code.

## 3. Catch ở trong hay ngoài boundary: cùng một exception, kết quả khác

### 3.1. Bắt và nuốt RuntimeException ngay trong method

~~~java
@Transactional
public void updateThenSwallow() {
    jdbc.update("UPDATE account SET amount = amount + 10 WHERE id = 1");
    try {
        throw new IllegalStateException("business validation failed");
    } catch (IllegalStateException ex) {
        log.warn("Ignored in this example", ex);
    }
    // Method return bình thường.
}
~~~

Đây là đoạn minh họa (giả định `jdbc`/`log` được inject). Lỗi được catch **trước khi rời method**, nên advice ở method này **không nhìn thấy** `IllegalStateException`. Nếu transaction mới, tài nguyên khỏe mạnh và chưa có rollback-only từ nơi khác, Spring commit thay đổi +10. Việc có một dòng log mức ERROR/WARN không làm rollback tự động.

Đừng sử dụng kết quả này để kết luận mọi exception của database đều có thể nuốt an toàn. Một câu SQL lỗi có thể khiến DB connection/transaction **đã rơi vào trạng thái aborted hoặc rollback-only**, đặc biệt khi DB phát hiện lỗi dữ liệu; khi đó commit có thể thất bại dù Java đã catch. Ví dụ trên cố ý ném exception **sau một UPDATE hợp lệ**, không dựa vào vendor-specific error handling.

### 3.2. Để exception thoát khỏi method, catch ở caller bên ngoài proxy

~~~java
// Trong một Spring bean khác hoặc entrypoint, với service là bean proxy:
try {
    service.updateThenThrow();
} catch (IllegalStateException ex) {
    log.warn("Returned user-friendly error", ex);
}
~~~

Giả định `service.updateThenThrow()` là `@Transactional`, cập nhật dữ liệu rồi ném unchecked exception ra ngoài. **Spring proxy thấy exception trước caller**, xử lý rollback theo policy, sau đó mới chuyển tiếp exception. Caller catch để tạo response hoặc tiếp tục luồng không làm transaction đã rollback “quay lại” thành commit.

Tương tự, nếu method ném **checked exception** và advice đã quyết định commit theo default, caller bên ngoài catch rồi wrap thành `RuntimeException` **quá muộn** để đảo ngược commit đã diễn ra. Điều quan trọng là **loại exception và vị trí biến đổi tại boundary nào**.

### 3.3. Catch để làm cleanup rồi rethrow

~~~java
@Transactional
public void updateThenRethrow() {
    try {
        updateRows();
    } catch (IllegalStateException ex) {
        recordLocalDiagnostic(ex);
        throw ex; // Exception vẫn đi qua transaction advice.
    }
}
~~~

Đây là đoạn minh họa có helper chưa định nghĩa, không phải chương trình độc lập. Với rollback default, rethrow cùng unchecked exception cho phép Spring rollback như mong đợi. Cần bảo đảm `recordLocalDiagnostic` không vô tình tạo side effect ngoài transaction mà nghiệp vụ tưởng rollback sẽ hoàn tác (ví dụ gửi HTTP/email).

**Quy tắc thực hành:** muốn transaction rollback theo exception, **cho exception phù hợp đi qua boundary** hoặc đánh dấu rollback-only có chủ ý. Catch chỉ để đổi cách trả lỗi cho người dùng thường nên thực hiện **bên ngoài** service transaction.

## 4. Đổi loại exception trước boundary làm thay đổi rule áp dụng

### 4.1. Checked sang unchecked

~~~java
@Transactional
public void importFile() {
    jdbc.update("UPDATE account SET amount = amount + 10 WHERE id = 1");
    try {
        callCheckedOperation(); // có thể ném IOException
    } catch (IOException ex) {
        throw new IllegalStateException("Import failed", ex);
    }
}
~~~

Giả định `callCheckedOperation()` là helper có khai báo `throws IOException`. Nếu `IOException` trực tiếp thoát khỏi `@Transactional` với default 6.1, transaction thường **không rollback** vì checked exception. Nhưng khi code chuyển thành `IllegalStateException` **trước khi thoát method**, transaction interceptor nhìn thấy **unchecked exception** và yêu cầu rollback.

Sử dụng constructor có `cause` giữ thông tin nguồn để debug: `new IllegalStateException("...", ex)`. Việc wrap **không tự làm exception trở thành rollbackable trong mọi cấu hình**; chính **rule được áp dụng cho loại được quan sát** mới quyết định. Nếu method có `noRollbackFor = IllegalStateException.class`, kết quả sẽ khác.

### 4.2. Unchecked sang checked

~~~java
@Transactional
public void importWithCheckedApi() throws IOException {
    jdbc.update("UPDATE account SET amount = amount + 10 WHERE id = 1");
    try {
        operationThatThrowsIllegalState();
    } catch (IllegalStateException ex) {
        throw new IOException("Converted to checked error", ex);
    }
}
~~~

Đây cũng là đoạn minh họa thiếu helper và field; mục tiêu là đường chuyển exception. Với rollback default 6.1, Spring thấy `IOException` thay vì `IllegalStateException`, nên **có thể commit** rồi ném `IOException` cho caller. Nếu nghiệp vụ yêu cầu atomicity, chỉ thay loại exception nhằm thống nhất API mà bỏ qua rollback rule là lỗi thiết kế.

Cách giải quyết là ghi `@Transactional(rollbackFor = IOException.class)` cho boundary thích hợp, hoặc dùng unchecked exception có ý nghĩa nghiệp vụ nếu contract cho phép. Không nên phụ thuộc vào việc “trước kia đã từng có một RuntimeException” — exception đó đã bị catch rồi.

### 4.3. Chuyển exception **sau** transactional method không sửa được quyết định cũ

~~~java
// Trong controller/facade, giả định service đã được advice bằng @Transactional:
try {
    service.importChecked(); // Thoát ra với IOException; Spring đã xử lý boundary.
} catch (IOException ex) {
    throw new IllegalStateException("API error", ex);
}
~~~

Nếu service `importChecked()` mặc định commit trước khi ném checked exception, controller wrap thành unchecked exception **sau khi service proxy đã kết thúc** thì transaction của service **không tự rollback ngược thời gian**. Nếu controller/facade còn có một transaction ngoài cùng, đó là **một boundary khác** và cần phân tích riêng theo propagation.

### 4.4. Exception translation trong @Repository

Spring có khả năng chuyển lỗi truy cập dữ liệu của provider (SQLException, JPA persistence exceptions, ...) thành hệ `DataAccessException` **unchecked** thông qua các abstraction như `JdbcTemplate` và exception translation trên repository được cấu hình phù hợp. Điều đó có thể khiến exception mà **service transactional advice** nhận được là `DataAccessException` thay vì checked exception gốc.

Không thể suy ra một quy tắc duy nhất cho mọi thư viện: thời điểm translation, thứ tự advice, driver, loại exception và việc catch ở DAO/service đều ảnh hưởng. Khi phân tích, hãy ghi rõ **exception cuối cùng rời mỗi bean proxy** và **boundary nào có @Transactional**. Đừng bắt toàn bộ `Exception` trong repository rồi trả `null` hay giá trị mặc định mà không báo lỗi; hành vi ấy có thể biến một giao dịch phải rollback thành thành công giả.

## 5. Bảng ma trận theo vị trí catch, loại lỗi và kết quả

Giả định **không có transaction ngoài, không có rollback-only sẵn có, tài nguyên commit được, và default rollback policy của Spring Framework 6.1**:

| Tình huống | Exception advice của method nhìn thấy | Kết quả có cơ sở kỳ vọng |
| --- | --- | --- |
| Method UPDATE, tự catch `IllegalStateException` và return | Không có exception | Commit |
| Method UPDATE rồi throw `IllegalStateException`, caller catch ngoài proxy | `IllegalStateException` | Rollback |
| Method UPDATE rồi throw `IOException`, caller catch ngoài proxy | `IOException` | Commit |
| Method catch `IOException`, wrap `IllegalStateException` trước khi return | `IllegalStateException` | Rollback |
| Method catch `IllegalStateException`, wrap `IOException` trước khi return | `IOException` | Commit |
| Method `@Transactional(rollbackFor=IOException.class)` throw `IOException` | `IOException` | Rollback |
| Method `@Transactional(noRollbackFor=IllegalStateException.class)` throw `IllegalStateException` | `IllegalStateException` | Commit |
| Method catch, gọi `setRollbackOnly()`, return | Không có exception, nhưng rollback-only | Rollback |
| Inner `REQUIRED` qua proxy throw unchecked, outer catch rồi return | Outer không thấy exception; inner đã đánh dấu global rollback-only | Rollback transaction chung; outer có thể nhận `UnexpectedRollbackException` |

Ma trận là một **mô hình có điều kiện**, không phải hứa hẹn mọi cấu hình database sẽ giống nhau. Việc một scope đang tham gia outer transaction, một operation đã bị DB từ chối, hoặc rollback rule của nhiều advice có thể thay đổi kết quả.

## 6. Rollback rules: đổi exception phải xét cả rule cụ thể

### 6.1. Chọn checked exception nào phải rollback

~~~java
@Transactional(rollbackFor = IOException.class)
public void processFile() throws IOException {
    // Khi IOException rời method qua proxy, Spring đánh dấu rollback.
}
~~~

`rollbackFor` nhận **lớp exception và các subclass**, nên cách này ít rủi ro hơn rule dạng chuỗi như `rollbackForClassName = "Exception"`, vì pattern rộng có thể khớp ngoài ý muốn. Khi viết API nghiệp vụ trả checked exception hợp lý, nên đặt rollback rule phản ánh **nghĩa nghiệp vụ**, thay vì wrap mọi lỗi thành RuntimeException chỉ để ép rollback.

### 6.2. Cho phép một unchecked exception không rollback

~~~java
@Transactional(noRollbackFor = PaymentNoticeException.class)
public void recordPaymentNotice() {
    // Có thể commit dữ liệu mặc dù PaymentNoticeException thoát ra
    // nếu rule chuyên biệt thắng và transaction còn commit được.
}
~~~

Đây là code minh họa, `PaymentNoticeException` là một loại nghiệp vụ giả định. `noRollbackFor` không bảo đảm commit trong mọi hoàn cảnh: nếu transaction đã rollback-only hoặc database không thể commit, Spring vẫn phải xử lý trạng thái thực tế.

### 6.3. Khi có nhiều rule cùng khớp

~~~java
@Transactional(
    rollbackFor = Exception.class,
    noRollbackFor = NonFatalBusinessException.class
)
public void settle() {
    // Nếu NonFatalBusinessException là subclass của Exception,
    // noRollbackFor cụ thể hơn sẽ có ưu tiên với loại này.
}
~~~

Spring chọn **matching rule mạnh nhất/cụ thể nhất**. Nếu code wrap `NonFatalBusinessException` thành `IllegalStateException`, rule riêng theo `NonFatalBusinessException` có thể không còn khớp **exception bên ngoài** (Spring không mặc nhiên duyệt toàn bộ `getCause()` để tìm rule). Việc vẫn giữ `cause` hữu ích cho debug, nhưng rollback rules mặc định so khớp **loại throwable được truyền đến advice**.

Khi định nghĩa rules, tránh dùng cùng exception type trong `rollbackFor` và `noRollbackFor`. Thiết kế exception hierarchy và policy nhất quán sẽ dễ kiểm tra hơn các pattern chồng chéo.

## 7. Nuốt lỗi không phải lúc nào cũng dẫn đến commit: inner REQUIRED đã đánh dấu rollback-only

Một vấn đề đặc biệt trong Spring là nhiều **logical transaction scope** có thể tham gia cùng **physical transaction** với propagation `REQUIRED`.

Sơ đồ:

~~~mermaid
flowchart TD
    A["Caller"] --> B["OuterService proxy<br/>@Transactional REQUIRED"]
    B --> C["OuterService.outer()"]
    C --> D["InnerService proxy<br/>@Transactional REQUIRED"]
    D --> E["InnerService.inner()"]
    E --> F["Ném RuntimeException"]
    F --> G["Inner interceptor đánh dấu<br/>transaction chung rollback-only"]
    G --> H["Outer catch exception<br/>và return bình thường"]
    H --> I["Outer interceptor yêu cầu commit"]
    I --> J["Không thể commit vì rollback-only"]
    J --> K["Rollback và có thể ném<br/>UnexpectedRollbackException"]
~~~

Ví dụ hai Spring bean khác nhau:

~~~java
@Service
class OuterService {
    private final InnerService inner;

    OuterService(InnerService inner) {
        this.inner = inner;
    }

    @Transactional
    public void outer() {
        try {
            inner.fail(); // Đi qua proxy của InnerService.
        } catch (IllegalStateException ex) {
            // Outer xử lý lỗi và muốn tiếp tục.
        }
        // Kết thúc bình thường, nhưng transaction chung đã rollback-only.
    }
}

@Service
class InnerService {
    @Transactional(propagation = Propagation.REQUIRED)
    public void fail() {
        throw new IllegalStateException("inner failed");
    }
}
~~~

Đây là **mã minh họa thiếu imports/bootstrapping**, chưa là chương trình độc lập. Trong tình huống mặc định, inner advice đánh dấu transaction vật lý chung rollback-only khi unchecked exception đi qua inner proxy. Outer catch lỗi **không xóa được marker**; khi outer cố commit có thể ném `UnexpectedRollbackException` để caller không hiểu nhầm rollback là commit thành công.

Điều này khác với **self-invocation** trong một bean: nếu `outer()` gọi `this.inner()`, advice của inner không được chạy riêng; chỉ throw/catch thuần Java có thể không đánh dấu rollback-only, trừ khi outer advice sau đó thấy exception hoặc code/tài nguyên khác chủ động đánh dấu.

Cũng khác với inner `REQUIRES_NEW`: inner rollback có thể độc lập với transaction ngoài, tùy cấu hình tài nguyên và propagation. Không thay propagation chỉ để che `UnexpectedRollbackException`; hãy chọn hành vi atomicity đúng yêu cầu.

## 8. Đã catch nhưng vẫn muốn rollback: các cách diễn đạt chủ đích

### 8.1. Rethrow exception phù hợp

Phổ biến nhất khi nghiệp vụ coi thất bại là thất bại của toàn transaction:

~~~java
@Transactional
public void transfer() {
    try {
        performTransfer();
    } catch (RuntimeException ex) {
        recordDiagnostic(ex);
        throw ex;
    }
}
~~~

Đây là đoạn minh họa có helper chưa định nghĩa. Caller có thể xử lý exception **sau khi** service proxy hoàn tất rollback. Đừng nuốt exception trong service rồi hy vọng `@Transactional` tự hiểu rằng transfer thất bại.

### 8.2. rollbackFor cho checked exception có ý nghĩa

~~~java
@Transactional(rollbackFor = ValidationException.class)
public void validateAndSave() throws ValidationException {
    // ValidationException là checked exception tùy biến.
}
~~~

Đây là đoạn minh họa; cần định nghĩa `ValidationException extends Exception` nếu đưa vào ứng dụng thực tế. Cách này giữ API contract của checked exception và chính sách commit/rollback rõ ràng.

### 8.3. Chủ động đánh dấu rollback-only rồi return

Có trường hợp phải catch exception để trả một kết quả nghiệp vụ mà không ném lỗi. Khi đó Spring cung cấp API:

~~~java
@Transactional
public Result saveAndReturnResult() {
    try {
        performWrites();
        return Result.success();
    } catch (BusinessException ex) {
        TransactionAspectSupport.currentTransactionStatus().setRollbackOnly();
        return Result.failed(ex.getMessage());
    }
}
~~~

Đây là **đoạn minh họa** với `Result`, `BusinessException` và `performWrites()` giả định. `TransactionAspectSupport.currentTransactionStatus()` chỉ hợp lệ khi lời gọi hiện hành có trạng thái transaction do Spring interceptor quản lý; nếu gọi trực tiếp ngoài advice, API có thể lỗi. `setRollbackOnly()` đánh dấu scope cần rollback và phụ thuộc manager thực thi khi kết thúc; nó **không tự rollback ngay tại câu lệnh gọi**. Nếu method đang tham gia transaction khác, marker có thể làm outer rollback và có thể gây `UnexpectedRollbackException` ở ranh giới ngoài.

Nếu không muốn business code phụ thuộc vào `TransactionAspectSupport`, cân nhắc tách service boundary cho phép ném exception đến caller hoặc dùng `TransactionTemplate` với `status.setRollbackOnly()` trong callback.

### 8.4. Trả object chứa lỗi không đồng nghĩa ném exception

Các kiểu trả về như `Result.failure(...)` hay trả `null` **không tự là exception** với `@Transactional` truyền thống. Tuy nhiên Spring có **một số tích hợp đặc biệt**: tài liệu rollback của Spring mô tả hỗ trợ `Vavr Try.Failure` và, từ Spring Framework 6.1, `Future/CompletableFuture` **đã exceptionally completed ngay lúc method return** trong những trường hợp hỗ trợ. Không suy luận rằng **mọi** object kết quả lỗi đều được Spring hiểu là rollback. Đối với `CompletableFuture` hoàn thành lỗi **sau** khi synchronous transaction boundary đã đóng, không thể mặc nhiên rollback transaction đó về sau.

## 9. Ví dụ Java 17+ chạy được: cùng một bảng, tám kiểu xử lý lỗi

Ví dụ dưới đây chạy một ứng dụng CLI Spring Boot 3.3.5 / Spring Framework 6.1.x với H2 in-memory. Nó cố định policy ở mức mặc định và dùng một `JdbcTransactionManager` quản lý một `DataSource`. Chạy tuần tự từng scenario, in số dư **sau khi ranh giới giao dịch hoàn tất** để phân biệt commit/rollback. Không cần server hay cấu hình DB ngoài.

**Cấu trúc đầy đủ (bốn tệp):**

~~~text
exception-outcome-demo/
├── pom.xml
└── src/main/java/example/txexceptions/
    ├── ExceptionOutcomeApplication.java
    ├── ScenarioService.java
    └── NestedService.java
~~~

### 9.1. pom.xml

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
    <artifactId>exception-outcome-demo</artifactId>
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
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-aop</artifactId>
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

### 9.2. src/main/java/example/txexceptions/ExceptionOutcomeApplication.java

~~~java
package example.txexceptions;

import java.io.IOException;
import javax.sql.DataSource;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.support.JdbcTransactionManager;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.UnexpectedRollbackException;
import org.springframework.transaction.annotation.EnableTransactionManagement;

@SpringBootApplication
@EnableTransactionManagement
public class ExceptionOutcomeApplication {
    public static void main(String[] args) {
        SpringApplication.run(ExceptionOutcomeApplication.class, args);
    }

    @Bean
    PlatformTransactionManager transactionManager(DataSource dataSource) {
        return new JdbcTransactionManager(dataSource);
    }

    @Bean
    CommandLineRunner demo(JdbcTemplate jdbc, ScenarioService scenario) {
        return args -> {
            jdbc.execute(
                "CREATE TABLE ledger (id INT PRIMARY KEY, amount INT NOT NULL)"
            );
            jdbc.update(
                "INSERT INTO ledger (id, amount) VALUES (?, ?)", 1, 100
            );
            System.out.println("START=" + amount(jdbc));

            scenario.swallowRuntime();
            System.out.println("AFTER_SWALLOW=" + amount(jdbc));

            try {
                scenario.throwRuntime();
            } catch (IllegalStateException ex) {
                System.out.println("RUNTIME_CAUGHT=" + ex.getMessage());
            }
            System.out.println("AFTER_RUNTIME=" + amount(jdbc));

            try {
                scenario.throwChecked();
            } catch (IOException ex) {
                System.out.println("CHECKED_CAUGHT=" + ex.getMessage());
            }
            System.out.println("AFTER_CHECKED=" + amount(jdbc));

            try {
                scenario.wrapChecked();
            } catch (IllegalStateException ex) {
                System.out.println(
                    "WRAPPED_CAUGHT=" + ex.getClass().getSimpleName()
                    + "/cause=" + ex.getCause().getClass().getSimpleName()
                );
            }
            System.out.println("AFTER_WRAPPED=" + amount(jdbc));

            try {
                scenario.checkedRollback();
            } catch (IOException ex) {
                System.out.println("RULE_CAUGHT=" + ex.getMessage());
            }
            System.out.println("AFTER_RULE=" + amount(jdbc));

            try {
                scenario.runtimeNoRollback();
            } catch (IllegalStateException ex) {
                System.out.println(
                    "NO_ROLLBACK_CAUGHT=" + ex.getMessage()
                );
            }
            System.out.println("AFTER_NO_ROLLBACK=" + amount(jdbc));

            scenario.swallowAndMarkRollbackOnly();
            System.out.println("AFTER_MARK_ONLY=" + amount(jdbc));

            try {
                scenario.outerCatchesInner();
            } catch (UnexpectedRollbackException ex) {
                System.out.println(
                    "OUTER_END=" + ex.getClass().getSimpleName()
                );
            }
            System.out.println("AFTER_OUTER=" + amount(jdbc));
        };
    }

    private static Integer amount(JdbcTemplate jdbc) {
        return jdbc.queryForObject(
            "SELECT amount FROM ledger WHERE id = ?", Integer.class, 1
        );
    }
}
~~~

### 9.3. src/main/java/example/txexceptions/ScenarioService.java

~~~java
package example.txexceptions;

import java.io.IOException;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.transaction.interceptor.TransactionAspectSupport;

@Service
public class ScenarioService {
    private final JdbcTemplate jdbc;
    private final NestedService nested;

    public ScenarioService(JdbcTemplate jdbc, NestedService nested) {
        this.jdbc = jdbc;
        this.nested = nested;
    }

    // 1: Exception bị catch trong method -> advice thấy return.
    @Transactional
    public void swallowRuntime() {
        add(10);
        try {
            throw new IllegalStateException("internal-failure");
        } catch (IllegalStateException ex) {
            System.out.println("INSIDE_CAUGHT=" + ex.getMessage());
        }
    }

    // 2: RuntimeException đi qua proxy -> rollback.
    @Transactional
    public void throwRuntime() {
        add(20);
        throw new IllegalStateException("runtime-leaked");
    }

    // 3: IOException checked đi qua proxy -> default commit.
    @Transactional
    public void throwChecked() throws IOException {
        add(30);
        throw new IOException("checked-leaked");
    }

    // 4: Wrap checked exception thành unchecked trước boundary.
    @Transactional
    public void wrapChecked() {
        add(40);
        try {
            throw new IOException("io-problem");
        } catch (IOException ex) {
            throw new IllegalStateException("wrapped-runtime", ex);
        }
    }

    // 5: Giữ checked exception nhưng yêu cầu rollback rõ ràng.
    @Transactional(rollbackFor = IOException.class)
    public void checkedRollback() throws IOException {
        add(50);
        throw new IOException("explicit-check");
    }

    // 6: Unchecked exception nhưng rule riêng yêu cầu không rollback.
    @Transactional(noRollbackFor = IllegalStateException.class)
    public void runtimeNoRollback() {
        add(60);
        throw new IllegalStateException("keep-change");
    }

    // 7: Nuốt lỗi và đánh dấu rollback-only.
    @Transactional
    public void swallowAndMarkRollbackOnly() {
        add(70);
        try {
            throw new IllegalStateException("handled-but-failed");
        } catch (IllegalStateException ex) {
            TransactionAspectSupport.currentTransactionStatus()
                .setRollbackOnly();
            System.out.println(
                "MARKED_ROLLBACK_ONLY="
                + TransactionAspectSupport.currentTransactionStatus()
                    .isRollbackOnly()
            );
        }
    }

    // 8: Inner REQUIRED đã đi qua proxy và đánh dấu rollback-only.
    @Transactional
    public void outerCatchesInner() {
        add(80);
        try {
            nested.requiredThrows();
        } catch (IllegalStateException ex) {
            System.out.println("OUTER_CAUGHT=" + ex.getMessage());
        }
        add(5);
    }

    private void add(int delta) {
        jdbc.update(
            "UPDATE ledger SET amount = amount + ? WHERE id = 1", delta
        );
    }
}
~~~

### 9.4. src/main/java/example/txexceptions/NestedService.java

~~~java
package example.txexceptions;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;

@Service
public class NestedService {
    private final JdbcTemplate jdbc;

    public NestedService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional(propagation = Propagation.REQUIRED)
    public void requiredThrows() {
        jdbc.update(
            "UPDATE ledger SET amount = amount + ? WHERE id = 1", 90
        );
        throw new IllegalStateException("nested-runtime");
    }
}
~~~

**Chạy tại thư mục `exception-outcome-demo`** (JDK 17+ và Maven đã cài; Maven tải dependency nếu cần):

~~~bash
mvn -q spring-boot:run
~~~

Các dòng **do chương trình in**, theo đúng thứ tự; bỏ qua log khởi động Spring/Hikari:

~~~text
START=100
INSIDE_CAUGHT=internal-failure
AFTER_SWALLOW=110
RUNTIME_CAUGHT=runtime-leaked
AFTER_RUNTIME=110
CHECKED_CAUGHT=checked-leaked
AFTER_CHECKED=140
WRAPPED_CAUGHT=IllegalStateException/cause=IOException
AFTER_WRAPPED=140
RULE_CAUGHT=explicit-check
AFTER_RULE=140
NO_ROLLBACK_CAUGHT=keep-change
AFTER_NO_ROLLBACK=200
MARKED_ROLLBACK_ONLY=true
AFTER_MARK_ONLY=200
OUTER_CAUGHT=nested-runtime
OUTER_END=UnexpectedRollbackException
AFTER_OUTER=200
~~~

### 9.5. Giải thích chính xác các mốc dữ liệu

| Case | Số dư trước | Thao tác trong transaction | Lý do kết quả | Số dư sau |
| --- | ---: | --- | --- | ---: |
| Nuốt unchecked | 100 | +10 | Advice chỉ thấy return; commit | 110 |
| Unchecked thoát ra | 110 | +20 | Default rollback | 110 |
| Checked thoát ra | 110 | +30 | Default 6.1 không rollback checked | 140 |
| Wrap checked thành unchecked | 140 | +40 | Advice thấy `IllegalStateException`; rollback | 140 |
| `rollbackFor = IOException.class` | 140 | +50 | Rule explicit khiến checked rollback | 140 |
| `noRollbackFor = IllegalStateException.class` | 140 | +60 | Rule explicit cho phép commit, exception vẫn được ném | 200 |
| Catch và `setRollbackOnly()` | 200 | +70 | Method return nhưng transaction đã rollback-only | 200 |
| Outer catch inner `REQUIRED` | 200 | outer +80, inner +90, outer +5 | Inner proxy đặt rollback-only; outer commit thất bại | 200 |

Một vài chi tiết quan trọng của ví dụ:

- `CommandLineRunner` được Spring inject **`ScenarioService` proxy**, không tạo service bằng `new`. Với tình huống inner, `NestedService` là một bean Spring khác được inject vào `ScenarioService` để lời gọi **đi qua proxy của nested**.
- Những UPDATE dùng `JdbcTemplate` và cùng một `DataSource` được `JdbcTransactionManager` quản lý. Không có external HTTP call, không có second database, nên rollback/commit kiểm chứng trực tiếp bằng số dư.
- `IOException` được ném **sau UPDATE hợp lệ**, giúp tách logic Spring rollback policy khỏi lỗi vendor SQL.
- Với case `noRollbackFor`, exception vẫn thoát ra caller dù database được commit. **Caller thấy lỗi không đồng nghĩa transaction rollback.**
- Với `setRollbackOnly()` trên một transaction mới, method có thể trả về bình thường và rollback diễn ra khi kết thúc; không bắt buộc ném `UnexpectedRollbackException` cho mọi thao tác đánh dấu local rollback-only.
- Trong case inner `REQUIRED`, inner advice nhìn thấy unchecked exception và đánh dấu **transaction chung** rollback-only. Outer catch không xóa marker. Khi outer cố commit, `UnexpectedRollbackException` là kết quả dự kiến của mô hình này.
- Kết quả trên giả định Spring Framework 6.1.x, quy tắc mặc định, driver H2 hoạt động bình thường, không có external transaction hoặc test-level transaction bọc runner.

## 10. Hướng dẫn xử lý lỗi mà vẫn giữ atomicity

### 10.1. Xác định ai sở hữu transaction boundary

Nên đặt `@Transactional` ở service method được caller khác gọi **qua Spring proxy**. Nếu một bean có `outer()` gọi `this.inner()` mà annotation chỉ nằm trên `inner()`, proxy advice của inner bị bỏ qua; khi đó cách phân tích về rollback rules của inner không còn đúng. Tách bean hoặc đưa transaction boundary ra entrypoint phù hợp khi cần.

### 10.2. Quyết định chính sách nghiệp vụ trước khi chọn catch/wrap

Ba mẫu tình huống:

- **Lỗi làm toàn thao tác thất bại:** rethrow một exception được rollback rules nhận diện, hoặc khai báo `rollbackFor` cho checked exception.
- **Lỗi không quan trọng và được phép tiếp tục:** catch có chủ đích, nhưng chỉ khi hệ thống chấp nhận **commit các thay đổi trước đó** và tài nguyên chưa bị đánh dấu rollback-only.
- **Lỗi đã xử lý để trả kết quả nhưng dữ liệu phải hủy:** catch và đánh dấu rollback-only, hoặc tổ chức một service boundary khác trả kết quả sau khi transaction rollback.

Không chuyển sang unchecked chỉ vì muốn có “lỗi nghiêm trọng” mà quên public API contract; cũng không chuyển sang checked chỉ để tránh rollback mà quên tính nhất quán dữ liệu.

### 10.3. Đặt catch bên ngoài transaction khi xử lý response

Ví dụ controller REST hoặc adapter:

~~~java
try {
    paymentService.pay(request);
    return ResponseEntity.ok().build();
} catch (PaymentRejectedException ex) {
    return ResponseEntity.unprocessableEntity().build();
}
~~~

Đây là **trích đoạn chưa chạy độc lập**. `paymentService.pay()` cần một rollback policy đúng với `PaymentRejectedException` **trước** khi exception được chuyển đến controller. Nếu `PaymentRejectedException` checked và service không có `rollbackFor` (hoặc global default phù hợp), controller trả HTTP 422 **không có nghĩa** database đã rollback. Tầng API và tầng transaction có trách nhiệm khác nhau.

### 10.4. Tránh nuốt mọi exception trong repository

Một anti-pattern:

~~~java
try {
    repository.save(entity);
} catch (Exception ex) {
    return false; // Cấu trúc minh họa; có nguy cơ che lỗi.
}
~~~

Với transaction ở caller, trả `false` có thể khiến outer commit dữ liệu không hoàn chỉnh. Mặt khác, nếu repository proxy đã tự đánh dấu transaction chung rollback-only, outer vẫn có thể nhận `UnexpectedRollbackException`. Nên phân biệt **business validation** có thể xử lý trước khi ghi và **persistence failure** cần rollback rõ ràng.

### 10.5. Side effect bên ngoài DB không được rollback cùng JDBC

Nếu code đã gửi email, gọi HTTP hoặc publish message ra broker độc lập rồi rollback database, side effect thường không tự được thu hồi. Việc catch/wrap exception **không thay đổi ranh giới tài nguyên**. Với yêu cầu đồng bộ trạng thái DB và event, có thể cân nhắc transactional outbox và xử lý sau commit. Không dùng `noRollbackFor` để “cứu” side effect đã lỡ gửi mà bỏ qua consistency.

## 11. Debug một ca “có exception nhưng dữ liệu vẫn commit”

Đọc theo **thứ tự thời gian** thay vì chỉ grep tên exception:

1. **Xác định boundary:** method nào thực sự được gọi qua Spring proxy, annotation/rule nào được áp dụng, manager nào quản lý database?
2. **Xác định nơi exception phát sinh:** trước hay sau SQL, trong try nào, có bị library/repository chuyển loại không?
3. **Đọc đường catch:** catch nằm trong transactional method, trong transactional inner bean, hay ở controller ngoài proxy?
4. **Ghi loại exception rời boundary:** checked hay unchecked; là object ngoài cùng nào? Có `getCause()` nào chỉ phục vụ debug, không tự quyết định rollback?
5. **Kiểm tra rule:** `rollbackFor`, `noRollbackFor`, rule mạnh nhất, và global `rollbackOn` nếu framework/config hỗ trợ.
6. **Kiểm tra rollback-only:** scope bên trong có đánh dấu global rollback-only không? Nếu outer return bình thường mà cuối cùng vẫn rollback, nghĩ đến `UnexpectedRollbackException`.
7. **Quan sát commit/rollback thật:** bật log transaction manager và xác nhận dữ liệu từ bên ngoài transaction sau khi method kết thúc.
8. **Loại trừ transaction test:** trong Spring TestContext, một `@Transactional` test có thể tạo outer transaction và rollback mặc định sau test, khiến kết quả commit ở service bị hiểu sai.
9. **Kiểm tra tài nguyên:** repository và manager có dùng đúng `DataSource`/`ConnectionFactory` không? DB có lỗi khiến giao dịch không còn commitable?

Với Spring Boot, trong môi trường test có thể bật:

~~~properties
logging.level.org.springframework.transaction.interceptor=TRACE
logging.level.org.springframework.jdbc.datasource=DEBUG
~~~

Thông điệp log khác nhau theo version/manager. Đừng dùng “không thấy exception ở cuối method” làm bằng chứng đủ cho commit thành công; sau method còn có flush, DB constraint và commit phase. Ngược lại, không thấy rollback log ở inner khi nó tham gia transaction ngoài không đồng nghĩa database đã commit.

### Phân biệt các kết quả khi điều tra

| Quan sát | Điều cần kiểm tra tiếp |
| --- | --- |
| Caller bắt RuntimeException, dữ liệu vẫn tăng | `noRollbackFor`? catch/translate trước advice? Transaction manager/resource sai? UPDATE ngoài transaction? |
| Caller bắt checked IOException, dữ liệu vẫn tăng | Có `rollbackFor=IOException.class` không? Có global ALL_EXCEPTIONS không? |
| Method return bình thường, dữ liệu không tăng | `setRollbackOnly()`? Inner `REQUIRED`? Database tự rollback? |
| Outer catch inner, rồi nhận `UnexpectedRollbackException` | Inner proxy đã đánh dấu rollback-only của physical transaction chung? |
| Controller đổi IOException thành RuntimeException, service data vẫn commit | Controller đổi loại **sau** khi service proxy đã commit? |
| Có `@Transactional` nhưng không thấy advice ở method | Self-invocation, bean không do Spring quản lý, hạn chế proxy, transaction infrastructure chưa bật? |

## 12. Câu hỏi luyện tập: xác định đúng exception tại boundary

**Bài 1.** Một method `@Transactional` UPDATE +10 rồi `throw new IllegalStateException()`. Method tự catch `IllegalStateException` và return một DTO lỗi. Không có inner proxy/rollback-only/DB error. Transaction có rollback không? **Không theo default: advice thấy return nên có thể commit +10.**

**Bài 2.** Service `@Transactional` UPDATE +10 rồi ném checked `IOException`. Controller catch và ném `IllegalStateException`. Spring Framework 6.1 dùng default rule, không có outer transaction. Transaction service rollback không? **Không: service advice thấy checked IOException, có thể commit trước khi controller wrap.**

**Bài 3.** Service catch `IOException` trong method rồi wrap thành `IllegalStateException` có cause. Không có rule đặc biệt. Kết quả? **Rollback vì unchecked exception đi qua advice**, dù root cause là checked exception.

**Bài 4.** Outer `@Transactional` gọi inner bean `@Transactional(REQUIRED)`; inner throw unchecked, outer catch rồi return. Tại sao outer có thể nhận `UnexpectedRollbackException`? **Vì inner proxy đã đánh dấu physical transaction chung rollback-only trước khi outer catch.**

**Bài 5.** Outer cùng class gọi `this.inner()`, inner có `@Transactional(rollbackFor=IOException.class)`. Vì sao custom rollback rule có thể không chạy? **Vì self-invocation ở proxy mode bỏ qua interception của inner; phải kiểm tra transaction boundary thực sự.**

**Bài 6.** Một service có `@Transactional(noRollbackFor = IllegalArgumentException.class)` nhưng JDBC đã gặp lỗi khiến transaction ở trạng thái aborted. Throw `IllegalArgumentException` rồi kết thúc. Có chắc commit không? **Không.** Rule cho phép **thử commit** với exception ấy; nó không sửa được trạng thái tài nguyên/rollback-only.

## 13. Kết luận về thiết kế đường lỗi

Khi dự đoán kết quả của `@Transactional`, hãy đặt ngón tay vào **điểm mà transaction advice nhận quyền điều khiển trở lại**: Java method đã return, đã throw unchecked, đã throw checked, hay transaction đã mang rollback-only? Sau đó xét manager, propagation và trạng thái DB.

**Catch và nuốt lỗi** có thể đổi một transaction đáng lẽ rollback thành commit. **Wrap/translate ngoại lệ** có thể đổi loại lỗi mà rollback rules so khớp. **Catch ở bên ngoài proxy** không thể sửa quyết định đã hoàn tất ở boundary bên trong. **Catch outer sau khi inner `REQUIRED` đã đánh dấu rollback-only** không khôi phục khả năng commit.

Đặt chính sách rollback ở đúng service boundary, giữ nguyên cause khi chuyển loại exception, kiểm chứng bằng failure integration test và dữ liệu sau transaction. Đó là cách bảo đảm kết quả không phụ thuộc tình cờ vào vị trí một `try/catch`.

## Tài liệu tham khảo chính thức

- [Spring Framework — Rolling Back a Declarative Transaction](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/rolling-back.html): default checked/unchecked, rollback rules, strongest match, rollback-only, Vavr Try và Future.
- [Spring Framework — Using @Transactional](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html): rollbackFor/noRollbackFor, transaction metadata và default ALL_EXCEPTIONS từ 6.2.
- [Spring Framework — Understanding PROPAGATION_REQUIRED](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-propagation.html): logical/physical scope, rollback-only, UnexpectedRollbackException.
- [Spring Framework — Understanding Declarative Transaction Implementation](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-decl-explained.html): transaction AOP proxy và interceptor.
- [Spring Framework — Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction.html): tổng quan declarative và programmatic transaction.
