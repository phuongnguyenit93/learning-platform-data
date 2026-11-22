# Try hoặc Future thất bại: Spring rollback theo phiên bản và thời điểm trả về

Trong Spring Framework, câu lệnh **@Transactional** thường được giải thích bằng quy tắc “method ném RuntimeException thì transaction rollback; method kết thúc bình thường thì commit”. Cách hiểu đó là điểm xuất phát, nhưng chưa đầy đủ khi method **trả về đối tượng biểu diễn thất bại** thay vì ném exception ra ngoài. Hai trường hợp đặc biệt cần nhận biết là **io.vavr.control.Try** ở trạng thái Failure và **java.util.concurrent.Future / CompletableFuture** đã hoàn tất bằng exception.

Điểm quyết định gồm **phiên bản Spring**, **trạng thái của giá trị tại thời điểm transactional interceptor nhận kết quả trả về**, và **loại exception bên trong có khớp rollback rule không**. Một Future hoàn tất lỗi nhiều giây sau khi method trả về không thể quay ngược một JDBC transaction đã commit.

Bài này tập trung vào **Spring declarative transaction với @Transactional và PlatformTransactionManager (JDBC/JPA imperative)**. Để tránh nhầm lẫn, ta sẽ phân biệt lời gọi method ném exception, Try.Failure, Future đã thất bại sẵn, Future còn pending, và reactive Publisher. Có một chương trình Java 17+ chạy với Spring 6.2, H2 và Vavr để quan sát số liệu DB sau từng lần gọi.

## 1. Cơ chế rollback mặc định khi không có kiểu trả về đặc biệt

Một service Spring được gọi **qua transactional proxy**:

~~~java
// Trích đoạn minh họa, cần được gọi qua Spring-managed proxy.
@Transactional
public void update() {
    repository.updateA();
    repository.updateB();
    throw new IllegalStateException("failed");
}
~~~

Lời gọi qua proxy đi theo luồng:

~~~text
Caller -> Spring proxy -> TransactionInterceptor
                              |
                              +-- lấy TransactionManager/TransactionDefinition
                              +-- tạo hoặc tham gia transaction
                              +-- gọi method nghiệp vụ
                              +-- quan sát exception hoặc kết quả trả về
                              +-- đánh giá rollback rule
                              +-- yêu cầu commit/rollback
                              +-- cleanup, trả connection về DataSource/pool
~~~

Với cấu hình mặc định thường gặp:

- **RuntimeException** và **Error** thoát ra qua boundary làm Spring yêu cầu rollback.
- **Checked Exception** thông thường không làm rollback tự động, trừ khi khai báo rollbackFor hoặc chính sách mặc định khác.
- **@Transactional(rollbackFor=SomeCheckedException.class)** mở rộng quy tắc rollback cho loại checked đó.
- **@Transactional(noRollbackFor=SomeRuntimeException.class)** có thể yêu cầu commit dù loại runtime exception này bị ném.
- Nếu mã ứng dụng catch exception rồi trả về bình thường, interceptor không quan sát thấy exception thoát ra; transaction có thể commit nếu chưa bị đánh dấu rollback-only.

Với Try và Future, Spring ở các phiên bản hỗ trợ có thêm một nhánh **kiểm tra kết quả trả về** trước khi commit. Nhánh này xét **nguyên nhân lỗi bên trong** theo cùng chính sách rollback, chứ không coi mọi đối tượng báo lỗi là yêu cầu rollback vô điều kiện.

## 2. Bảng phiên bản: tính năng nào xuất hiện từ lúc nào?

| Dạng thất bại | Phiên bản Spring Framework | Spring quan sát như thế nào |
| --- | --- | --- |
| Method ném RuntimeException/Error ra ngoài | Hành vi truyền thống của declarative transactions | Interceptor bắt exception thoát khỏi method và đánh giá rollback rule |
| Method trả về **Vavr Try.Failure** | **Từ Spring Framework 5.2** | Khi trả về, Spring phát hiện Try.Failure; xét cause theo rollback rule rồi đánh dấu rollback-only nếu khớp |
| Method trả về **Future/CompletableFuture đã hoàn tất ngoại lệ** | **Từ Spring Framework 6.1** | Khi method trả về, nếu Future đã done, Spring kiểm tra exception cause và đánh dấu rollback-only nếu khớp |
| **Future chỉ thất bại sau khi method đã trả về và commit** | Không có hỗ trợ rollback hồi tố trong cơ chế imperative này | Transaction đã kết thúc; tín hiệu lỗi đến sau không thể làm rollback giao dịch cũ |
| Mono/Flux trả về Publisher trong reactive transaction | Dùng ReactiveTransactionManager với reactive workflow phù hợp | Transaction lifecycle gắn với subscription/reactive context, không theo phép kiểm tra Future imperative |

**Lưu ý lịch sử:** tài liệu Spring 5.2 và 6.0 đã mô tả hỗ trợ Vavr Try.Failure; ví dụ Future/CompletableFuture hoàn tất lỗi chỉ được nêu như cơ chế bổ sung **từ Spring 6.1**. Nếu dự án đang chạy Spring 5.x/6.0, không được dựa vào nhánh rollback Future mới hơn. Cần kiểm tra **Spring Framework version thực sự trên runtime classpath**, không chỉ version Spring Boot ghi trong pom.xml/build.gradle.

**Thay đổi khác từ Spring 6.2:** có thể chọn mặc định rollback trên mọi exception, kể cả checked exception, bằng **@EnableTransactionManagement(rollbackOn = RollbackOn.ALL_EXCEPTIONS)** khi dùng annotation transaction infrastructure. Thay đổi này ảnh hưởng đến đánh giá cause của Try/Future nếu không có rule riêng; nó không khiến một Future thất bại *sau khi transaction đã đóng* có thể rollback hồi tố. Ví dụ chạy ở phần 7 **giữ mặc định rollback cho unchecked** để dễ nhìn rõ sự khác nhau.

Các ví dụ phía dưới dùng Spring 6.2.x; cần đọc release notes/chính sách hiện hành của dự án nếu nâng cấp hoặc có custom transaction interceptor.

## 3. Vavr Try: thất bại được gói trong giá trị trả về

### 3.1. Try.Success và Try.Failure là gì?

**Vavr** là thư viện Java độc lập, thường được dùng để biểu diễn kết quả tính toán có thể thành công hoặc thất bại. Kiểu **io.vavr.control.Try<T>** có hai dạng:

- **Success(value):** có giá trị thành công.
- **Failure(Throwable):** giữ nguyên nhân thất bại dưới dạng Throwable.

Ví dụ không phụ thuộc Spring:

~~~java
import io.vavr.control.Try;

Try<Integer> ok = Try.of(() -> 2 + 3);
Try<Integer> failed = Try.of(() -> {
    throw new IllegalStateException("cannot calculate");
});

System.out.println(ok.isSuccess());       // true
System.out.println(failed.isFailure());    // true
~~~

Đây là đoạn trích dùng trong chương trình có dependency Vavr, chưa phải file Java độc lập vì thiếu class/main. Vavr Try thường bắt exception được ném khi lambda chạy rồi chuyển thành Failure. Do đó, khi method khai báo @Transactional trả về **Try.Failure**, interceptor **không thấy exception thoát khỏi method** theo đường thông thường.

### 3.2. Spring xử lý Try.Failure như thế nào?

Từ Spring 5.2, khi transactional method trả về một Vavr Try, Spring nhận ra giá trị này và xét Failure **trước khi hoàn tất transaction**. Về ý nghĩa:

~~~text
@Transactional method
    |
    +-- SQL UPDATE
    +-- return Try.Failure(cause)
    |
transaction interceptor nhận result
    |
    +-- result là Try?
    +-- là Failure?
    +-- rollbackOn(cause) theo policy?
          |
          +-- true  -> đánh dấu transaction rollback-only
          +-- false -> không tự đánh dấu rollback-only từ Failure này
    |
    +-- manager hoàn tất transaction theo trạng thái hiện tại
~~~

Ví dụ:

~~~java
// Trích đoạn: service được Spring quản lý và JdbcTemplate nằm trong transaction.
@Transactional
public Try<String> updateAndReturnFailure() {
    jdbcTemplate.update("UPDATE demo_state SET amount=amount+1 WHERE id=1");
    return Try.failure(new IllegalStateException("invalid"));
}
~~~

Ở phiên bản hỗ trợ, **Failure chứa IllegalStateException** khớp default rollback rule nên transaction được yêu cầu rollback dù method đã return bình thường. Trả về Success sau UPDATE thường cho phép commit, miễn không có rollback-only hoặc lỗi khác.

**Failure không tự đồng nghĩa rollback cho mọi Throwable.** Ví dụ một Failure chứa **IOException** (checked exception) có thể vẫn dẫn tới commit dưới mặc định thông thường:

~~~java
@Transactional
public Try<String> checkedFailure() {
    jdbcTemplate.update("UPDATE demo_state SET amount=amount+1 WHERE id=1");
    return Try.failure(new java.io.IOException("checked failure"));
}
~~~

Muốn rollback checked cause này, khai báo:

~~~java
@Transactional(rollbackFor = java.io.IOException.class)
public Try<String> checkedFailureWithRule() {
    jdbcTemplate.update("UPDATE demo_state SET amount=amount+1 WHERE id=1");
    return Try.failure(new java.io.IOException("checked failure"));
}
~~~

Hai đoạn là minh họa, cần imports, class/service và DataSource cấu hình sẵn. Trong cấu hình Spring 6.2 với ALL_EXCEPTIONS, nhánh checked có thể rollback mặc định; luôn biết policy runtime thực tế.

### 3.3. Trạng thái Try được tạo *sau* khi method trả về thì sao?

Try thông thường là kết quả đã chứa trạng thái Success/Failure khi được trả về; Spring có thể kiểm tra Failure ngay tại boundary. Nhưng nếu method trả về **Try.Success chứa một Future** hoặc một callback sẽ thất bại về sau, Spring **không đào sâu vào Future lồng trong Success** để dự đoán tương lai.

Ví dụ:

~~~java
// Đây chỉ là sketch về cấu trúc kiểu dữ liệu.
Try<CompletableFuture<String>> value =
        Try.success(new CompletableFuture<>());

// value.isSuccess() == true dù CompletableFuture ở trong còn pending.
~~~

Đừng nhầm “Try bọc thao tác bất đồng bộ” với “Try.Failure đã tồn tại ngay khi method trả về”. Cần xác định **đối tượng trực tiếp được transactional interceptor kiểm tra** và thời điểm thất bại thực sự xảy ra.

## 4. Future/CompletableFuture: mốc kiểm tra là lúc method trả về

### 4.1. Tại sao Future khác Try?

**Future<T>** của JDK biểu thị một công việc có thể chưa hoàn tất. **CompletableFuture<T>** có thể ở trạng thái:

- **Pending:** chưa có kết quả, isDone() == false.
- **Completed normally:** đã có kết quả thành công.
- **Completed exceptionally:** đã kết thúc với Throwable.

Từ **Spring 6.1**, khi một method transactional imperative trả về một Future, Spring xét trạng thái của Future **ở thời điểm nhận return value**. Nếu Future đã **done** và **get() cho biết completed exceptionally**, Spring có thể lấy nguyên nhân lỗi, áp dụng rollback rule, đánh dấu transaction rollback-only rồi kết thúc transaction.

Ví dụ Future đã thất bại ngay khi trả về:

~~~java
// Trích đoạn minh họa trong Spring service.
@Transactional
public CompletableFuture<String> failedImmediately() {
    jdbcTemplate.update("UPDATE demo_state SET amount=amount+1 WHERE id=1");
    return CompletableFuture.failedFuture(
            new IllegalStateException("failed now"));
}
~~~

Trong Spring 6.1+, cause IllegalStateException khớp default rollback rule và Future đã hoàn tất lỗi **trước khi method return**, nên Spring có thể rollback UPDATE. Phía caller nhận về một CompletableFuture ở trạng thái exceptionally completed; **method không bắt buộc ném exception trực tiếp** để rollback xảy ra.

### 4.2. Future đang pending khi method trả về

~~~java
@Transactional
public CompletableFuture<String> failedLater() {
    jdbcTemplate.update("UPDATE demo_state SET amount=amount+1 WHERE id=1");
    return new CompletableFuture<>(); // Chưa hoàn tất khi return.
}
~~~

Ở thời điểm interceptor quan sát, **isDone() == false**. Nó không thể biết tương lai thành công hay thất bại; Spring hoàn tất transaction theo trạng thái hiện tại. Nếu không có rollback-only hoặc lỗi khác, JDBC transaction **commit**. Sau khi caller nhận Future rồi gọi completeExceptionally(...), trạng thái Future đổi thành lỗi nhưng transaction JDBC **đã kết thúc**.

~~~text
T0: Spring mở transaction
T1: UPDATE thành công trong transaction
T2: method trả CompletableFuture đang pending
T3: interceptor thấy isDone=false, không phát hiện exceptional completion
T4: manager commit và giải phóng JDBC Connection
T5: caller/worker khác hoàn tất Future bằng exception
T6: Future báo lỗi cho caller; dữ liệu T4 không tự rollback
~~~

Nếu có một worker concurrent hoàn tất Future sát T2/T3, thời điểm nó chuyển sang done có thể khiến kết quả rollback/commit khác nhau. **Không thiết kế tính đúng đắn dữ liệu dựa trên race condition “Future sẽ kịp thất bại trước khi transaction đóng”.**

### 4.3. Trường hợp CompletableFuture.completedFuture(...) hoặc failedFuture(...)

| Giá trị method trả về | Trạng thái lúc trả về | Ý nghĩa với rollback trong Spring 6.1+ |
| --- | --- | --- |
| CompletableFuture.completedFuture("ok") | Done, thành công | Không tạo yêu cầu rollback chỉ từ handle |
| CompletableFuture.failedFuture(new IllegalStateException(...)) | Done, lỗi runtime | Có thể rollback theo default rules |
| CompletableFuture.failedFuture(new IOException(...)) | Done, lỗi checked | Mặc định thường không rollback; dùng rollbackFor=IOException.class hoặc chính sách phù hợp |
| new CompletableFuture<>() | Pending | Không có lỗi để đánh giá lúc return, nên transaction có thể commit |
| Future pending rồi completeExceptionally(...) sau transaction | Lỗi đến muộn | Không hồi tố rollback được giao dịch đã commit |
| Method trực tiếp throw IllegalStateException | Không return Future | Xử lý đường exception thông thường; default rollback |

**Chú ý:** không nên coi isCompletedExceptionally() của CompletableFuture là hàm Spring luôn gọi. Với implementation của Spring 6.2, luồng xử lý tổng quát xét Future.isDone(), gọi Future.get(), sau đó xử lý cause của ExecutionException theo rollback rule. Cách nhận diện chi tiết thuộc implementation/version; contract quan trọng là **Future đã thất bại khi method trả về**.

Không đánh đồng một Future **đã done thành công** với **đã done thất bại**. Cũng không suy luận hủy Future bằng cancel(...) có chính sách rollback giống mọi ExecutionException; hủy/chặn/ngắt có semantics riêng, cần test đúng phiên bản và API dùng thực tế.

## 5. Rollback rules vẫn quyết định cả Try và Future

Spring đánh giá nguyên nhân Throwable của Try.Failure hoặc của Future đã failed theo policy của transaction, không theo tên class của wrapper.

| Cause | Annotation / policy | Hành vi kỳ vọng trong Spring 6.2 |
| --- | --- | --- |
| IllegalStateException (RuntimeException) | @Transactional mặc định | Rollback khi Try.Failure hoặc Future exceptional đã có ở thời điểm kiểm tra |
| IOException (checked) | @Transactional mặc định, rollbackOn chưa đổi | Thường commit nếu không có rollback-only khác |
| IOException (checked) | @Transactional(rollbackFor=IOException.class) | Rollback khi cause có thể được kiểm tra kịp thời |
| IllegalStateException | @Transactional(noRollbackFor=IllegalStateException.class) | Không rollback chỉ bởi cause đó; có thể commit |
| IOException (checked) | Spring 6.2 với rollbackOn=ALL_EXCEPTIONS | Rollback mặc định, trừ rule riêng mạnh hơn |
| Bất kỳ cause nào | Future chưa done lúc return | Chưa có cause để áp dụng quy tắc rollback ở thời điểm đó |

**Đừng đánh giá default một cách tuyệt đối.** Spring 6.2 cho phép đặt mặc định ALL_EXCEPTIONS; dự án có thể dùng cấu hình XML rollback rules, custom TransactionAttributeSource hoặc noRollbackFor. Quy tắc cụ thể của method có thể ghi đè mặc định. Khi có transaction ngoài đã rollback-only, manager vẫn có thể rollback dù cause của result wrapper không khớp.

**Về checked exception:** một method trả Try.Failure(new IOException(...)) khác về chữ ký Java với method trực tiếp throws IOException, nhưng trong Spring 6.2 chúng có điểm chung ở khâu **đánh giá rollback rule trên IOException**. Sự khác nhau nằm ở đường tiếp nhận lỗi: Try được xem là result, exception ném được xem qua catch của interceptor.

## 6. Vì sao @Async không giải quyết rollback trễ?

Tài liệu Spring 6.1+ mô tả Future-return handling nhằm hỗ trợ tình huống **@Transactional + @Async** có chữ ký trả CompletableFuture. Một ví dụ gọn:

~~~java
// Trích đoạn, cần @EnableAsync và @EnableTransactionManagement
// cùng Spring bean/proxy, transaction manager và repository tương ứng.
@Async
@Transactional
public CompletableFuture<String> writeAsync() {
    try {
        repository.persist();
        return CompletableFuture.completedFuture("ok");
    } catch (DataAccessException ex) {
        return CompletableFuture.failedFuture(ex);
    }
}
~~~

Ở đây code method có thể phải trả về handle theo API @Async, nhưng lỗi DB xảy ra **trong chính lời gọi transactional method** và nó trả về Future **đã thất bại**. Spring có thể nhận diện lỗi trước khi kết thúc transaction trên luồng thực thi method.

**Giới hạn quan trọng:**

1. Transaction của PlatformTransactionManager truyền theo execution context của **thread**. Không giả định transaction đang mở trên thread caller tự truyền sang mọi worker thread.
2. @Async thay đổi **nơi và lúc method thực thi**; transaction manager cần bao quanh phần SQL thực sự chạy, với advisor/proxy và thứ tự xử lý đúng.
3. Nếu method chỉ gọi CompletableFuture.supplyAsync(...) để **lên lịch SQL chạy sau đó**, rồi trả một Future pending, transaction của method có thể commit **trước khi SQL trong worker chạy**. Worker thường dùng connection/transaction khác.
4. Không giữ transaction JDBC vô hạn đến khi Future hoàn tất chỉ vì phương thức có kiểu trả CompletableFuture.
5. Nếu đích là một workflow có nhiều tác vụ bất đồng bộ, cần thiết kế ranh giới transaction riêng cho từng tác vụ và consistency giữa chúng.

**Sai lầm thiết kế phổ biến:** một service ghi DB, trả Future chưa hoàn tất, sau đó gửi HTTP hoặc publish message trong callback rồi mong ngoại lệ callback khiến JDBC transaction của service rollback. Callback xảy ra sau commit không thể đảo ngược giao dịch đó. Có thể cần transactional outbox, saga/bù trừ hoặc thiết kế lại đơn vị nghiệp vụ.

## 7. Chương trình Java 17+ kiểm chứng cả Try và Future

Ví dụ này dùng **Spring Framework 6.2.12**, **Vavr 0.10.5** và **H2 2.3.232**. Tất cả các method được gọi **qua Spring bean proxy**; cùng một DataSource và JdbcTransactionManager được sử dụng. Cột amount bắt đầu từ 0. Mỗi method tăng amount lên 1 trước khi trả kết quả; số lượng commit còn lại cho thấy Spring có rollback hay không.

Mục tiêu của demo:

- Try.Failure runtime → rollback, amount không tăng.
- Try.Failure checked dưới mặc định → commit, amount tăng.
- Try.Failure checked + rollbackFor → rollback.
- Try.Failure runtime + noRollbackFor → commit.
- Future đã thất bại runtime → rollback.
- Future đã thất bại checked dưới mặc định → commit.
- Future đã thất bại checked + rollbackFor → rollback.
- Future pending lúc return → commit; completeExceptionally sau đó không thể rollback.
- Try.Success → commit.

### 7.1. Cấu trúc và pom.xml

~~~text
return-value-rollback-demo/
├── pom.xml
└── src/main/java/demo/ReturnValueRollbackDemo.java
~~~

**pom.xml**

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>return-value-rollback-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.12</version>
        </dependency>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-jdbc</artifactId>
            <version>6.2.12</version>
        </dependency>
        <dependency>
            <groupId>io.vavr</groupId>
            <artifactId>vavr</artifactId>
            <version>0.10.5</version>
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
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.1</version>
                <configuration>
                    <mainClass>demo.ReturnValueRollbackDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Ứng dụng Spring Boot thật nên dùng dependency management/BOM phù hợp thay vì copy cứng tất cả version từ demo. Vavr phải thực sự có trên runtime classpath để Spring phát hiện kiểu Try; sử dụng Một loại Result hoặc Either tự viết **không tự kế thừa** cơ chế nhận diện Vavr Try.

### 7.2. Chương trình Spring hoàn chỉnh

**src/main/java/demo/ReturnValueRollbackDemo.java**

~~~java
package demo;

import io.vavr.control.Try;
import java.io.IOException;
import java.util.concurrent.CompletableFuture;
import javax.sql.DataSource;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DriverManagerDataSource;
import org.springframework.jdbc.support.JdbcTransactionManager;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.annotation.EnableTransactionManagement;
import org.springframework.transaction.annotation.Transactional;

public final class ReturnValueRollbackDemo {
    private ReturnValueRollbackDemo() {}

    private static int amount(JdbcTemplate jdbc) {
        Integer result = jdbc.queryForObject(
                "SELECT amount FROM demo_state WHERE id = 1",
                Integer.class);
        if (result == null) {
            throw new IllegalStateException("Row not found");
        }
        return result;
    }

    public static void main(String[] args) {
        try (var context = new AnnotationConfigApplicationContext(Config.class)) {
            JdbcTemplate jdbc = context.getBean(JdbcTemplate.class);
            DemoService service = context.getBean(DemoService.class);

            jdbc.execute("CREATE TABLE demo_state ("
                    + "id INT PRIMARY KEY, amount INT NOT NULL)");
            jdbc.update(
                    "INSERT INTO demo_state(id, amount) VALUES (?, ?)", 1, 0);

            System.out.println("start=" + amount(jdbc));

            Try<String> r1 = service.tryRuntimeFailure();
            System.out.printf("try runtime: failure=%s, amount=%d%n",
                    r1.isFailure(), amount(jdbc));

            Try<String> r2 = service.tryCheckedDefault();
            System.out.printf("try checked default: failure=%s, amount=%d%n",
                    r2.isFailure(), amount(jdbc));

            Try<String> r3 = service.tryCheckedExplicit();
            System.out.printf("try checked rollbackFor: failure=%s, amount=%d%n",
                    r3.isFailure(), amount(jdbc));

            Try<String> r4 = service.tryRuntimeNoRollback();
            System.out.printf("try runtime noRollbackFor: failure=%s, amount=%d%n",
                    r4.isFailure(), amount(jdbc));

            CompletableFuture<String> f1 = service.futureImmediateRuntimeFailure();
            System.out.printf("future runtime immediate: exceptional=%s, amount=%d%n",
                    f1.isCompletedExceptionally(), amount(jdbc));

            CompletableFuture<String> f2 = service.futureImmediateCheckedDefault();
            System.out.printf("future checked default: exceptional=%s, amount=%d%n",
                    f2.isCompletedExceptionally(), amount(jdbc));

            CompletableFuture<String> f3 = service.futureImmediateCheckedExplicit();
            System.out.printf("future checked rollbackFor: exceptional=%s, amount=%d%n",
                    f3.isCompletedExceptionally(), amount(jdbc));

            CompletableFuture<String> pending = service.futureStillPending();
            System.out.printf("future pending on return: done=%s, amount=%d%n",
                    pending.isDone(), amount(jdbc));

            pending.completeExceptionally(
                    new IllegalStateException("completed after transaction"));
            System.out.printf("future failed later: exceptional=%s, amount=%d%n",
                    pending.isCompletedExceptionally(), amount(jdbc));

            Try<String> success = service.trySuccess();
            System.out.printf("try success: success=%s, amount=%d%n",
                    success.isSuccess(), amount(jdbc));
        }
    }

    @Configuration(proxyBeanMethods = false)
    @EnableTransactionManagement(proxyTargetClass = true)
    public static class Config {
        @Bean
        public DataSource dataSource() {
            DriverManagerDataSource dataSource = new DriverManagerDataSource();
            dataSource.setDriverClassName("org.h2.Driver");
            dataSource.setUrl("jdbc:h2:mem:return_demo;DB_CLOSE_DELAY=-1");
            dataSource.setUsername("sa");
            dataSource.setPassword("");
            return dataSource;
        }

        @Bean
        public JdbcTemplate jdbcTemplate(DataSource dataSource) {
            return new JdbcTemplate(dataSource);
        }

        @Bean
        public PlatformTransactionManager transactionManager(DataSource dataSource) {
            return new JdbcTransactionManager(dataSource);
        }

        @Bean
        public DemoService demoService(JdbcTemplate jdbcTemplate) {
            return new DemoService(jdbcTemplate);
        }
    }

    public static class DemoService {
        private final JdbcTemplate jdbc;

        public DemoService(JdbcTemplate jdbc) {
            this.jdbc = jdbc;
        }

        private void increment() {
            jdbc.update(
                    "UPDATE demo_state SET amount = amount + 1 WHERE id = 1");
        }

        @Transactional
        public Try<String> tryRuntimeFailure() {
            increment();
            return Try.failure(new IllegalStateException("runtime"));
        }

        @Transactional
        public Try<String> tryCheckedDefault() {
            increment();
            return Try.failure(new IOException("checked"));
        }

        @Transactional(rollbackFor = IOException.class)
        public Try<String> tryCheckedExplicit() {
            increment();
            return Try.failure(new IOException("checked with rule"));
        }

        @Transactional(noRollbackFor = IllegalStateException.class)
        public Try<String> tryRuntimeNoRollback() {
            increment();
            return Try.failure(new IllegalStateException("no rollback rule"));
        }

        @Transactional
        public CompletableFuture<String> futureImmediateRuntimeFailure() {
            increment();
            return CompletableFuture.failedFuture(
                    new IllegalStateException("future runtime"));
        }

        @Transactional
        public CompletableFuture<String> futureImmediateCheckedDefault() {
            increment();
            return CompletableFuture.failedFuture(
                    new IOException("future checked"));
        }

        @Transactional(rollbackFor = IOException.class)
        public CompletableFuture<String> futureImmediateCheckedExplicit() {
            increment();
            return CompletableFuture.failedFuture(
                    new IOException("future checked with rule"));
        }

        @Transactional
        public CompletableFuture<String> futureStillPending() {
            increment();
            return new CompletableFuture<>();
        }

        @Transactional
        public Try<String> trySuccess() {
            increment();
            return Try.success("ok");
        }
    }
}
~~~

**Vì sao chương trình này đủ để kiểm tra điều kiện rollback?**

1. Annotation @EnableTransactionManagement(proxyTargetClass=true) kích hoạt transactional proxy cho class DemoService.
2. Caller lấy **DemoService từ ApplicationContext**, không tự new service; lời gọi vào public transactional methods đi qua proxy.
3. JdbcTransactionManager và JdbcTemplate dùng **cùng một DataSource**.
4. Mỗi method ghi đúng một UPDATE trước khi trả result, nên amount tăng chỉ khi transaction được commit.
5. Các lần đọc amount(...) xảy ra sau khi method trả về qua proxy, tức transaction cục bộ của lần gọi đó đã hoàn tất.
6. Future pending được completeExceptionally **bên ngoài method và sau khi proxy trả về**, khiến so sánh thời điểm có tính xác định, không phụ thuộc scheduler.
7. Demo dùng default rollback behavior cho checked exception; các method muốn thay chính sách dùng rollbackFor/noRollbackFor ngay trên method.

### 7.3. Lệnh chạy và kết quả cần quan sát

Trong thư mục **return-value-rollback-demo**, chạy:

~~~bash
mvn -q compile exec:java
~~~

**Stdout dự kiến do chính chương trình in** (các log thư viện hoặc Maven không nằm trong đoạn này):

~~~text
start=0
try runtime: failure=true, amount=0
try checked default: failure=true, amount=1
try checked rollbackFor: failure=true, amount=1
try runtime noRollbackFor: failure=true, amount=2
future runtime immediate: exceptional=true, amount=2
future checked default: exceptional=true, amount=3
future checked rollbackFor: exceptional=true, amount=3
future pending on return: done=false, amount=4
future failed later: exceptional=true, amount=4
try success: success=true, amount=5
~~~

Đọc từng dòng:

- **Try runtime Failure** trả về result thất bại nhưng SQL rollback, amount vẫn 0.
- **Try checked Failure mặc định** trả về result thất bại nhưng cause IOException không nằm trong default rollback rules, nên amount tăng 1.
- **Try checked với rollbackFor** làm amount giữ nguyên 1.
- **Try runtime với noRollbackFor** trả Failure nhưng amount tăng lên 2 vì rule yêu cầu không rollback bởi cause đó.
- **Future failed runtime đã done** được Spring 6.2 phát hiện tại return boundary, amount vẫn 2.
- **Future failed checked mặc định** được phát hiện nhưng không khớp rule, amount tăng 3.
- **Future failed checked với rollbackFor** rollback, amount vẫn 3.
- **Future pending** khi method trả về: interceptor chưa thấy failure, transaction commit, amount thành 4.
- Caller hoàn tất future đó bằng exception sau khi return: Future báo lỗi nhưng amount vẫn 4, chứng minh **không có rollback hồi tố**.
- **Try.Success** commit bình thường, amount thành 5.

Phần stdout trên xác định theo các dữ liệu/transaction đã khai báo trong một chương trình chạy tuần tự. Nếu dự án thêm các bean/aspect tùy biến, thay đổi rollback policy toàn cục hoặc đổi manager, kết quả có thể khác và cần giải thích theo cấu hình thực tế.

## 8. Một cách kiểm tra bằng log và transaction status

Khi tìm lỗi trong ứng dụng, log giúp đối chiếu thời điểm interceptor quyết định rollback. Trong Spring Boot, thử:

~~~properties
logging.level.org.springframework.transaction.interceptor=TRACE
logging.level.org.springframework.jdbc.datasource=DEBUG
logging.level.org.springframework.jdbc.support=DEBUG
~~~

Những dấu hiệu có thể gặp:

~~~text
Getting transaction for [demo.DemoService.futureImmediateRuntimeFailure]
Creating new transaction ...
Completing transaction for [demo.DemoService.futureImmediateRuntimeFailure]
Initiating transaction rollback
Rolling back JDBC transaction on Connection [...]
Releasing JDBC Connection [...] after transaction
~~~

Dòng chữ và logger cụ thể thay đổi theo implementation/version. Với **Try.Failure/Future failed return**, method có thể kết thúc **không ném exception trực tiếp**, nhưng manager vẫn nhìn thấy transaction rollback-only trước khi hoàn tất.

Nếu case Future pending cho log **Initiating transaction commit** rồi callback bên ngoài log lỗi sau đó, điều này phù hợp với thời điểm đã mô tả. Không dùng log của callback làm bằng chứng Spring đã rollback transaction trước đó.

Có thể kiểm tra trong snippet chương trình:

~~~java
// Chỉ dùng trong một @Transactional method đang được interceptor quản lý.
boolean active =
        org.springframework.transaction.support.TransactionSynchronizationManager
                .isActualTransactionActive();
System.out.println("transaction active=" + active);
~~~

**active=true** chỉ chứng minh context transaction hiện hành, không xác nhận method sẽ commit hay rollback. Đọc dữ liệu đã hoàn tất từ một connection/transaction độc lập vẫn là kiểm chứng mạnh hơn.

## 9. Những tình huống không được suy diễn thành tự động rollback

### 9.1. Future lỗi sau một phép toán kéo dài

~~~java
// Minh họa ý tưởng: công việc bên trong supplier có thể chạy sau khi method return.
@Transactional
public CompletableFuture<String> scheduleWork() {
    return CompletableFuture.supplyAsync(() -> {
        // Tác vụ chạy trên worker khác.
        return externalOperation();
    });
}
~~~

Đoạn này không phải chương trình chạy độc lập. Transaction gắn với lời gọi method hiện tại có thể kết thúc trước khi supplier chạy; JDBC code trong supplier không tự dùng transaction đã đóng. Cần dịch chuyển ranh giới transaction vào bean/task thực sự thực thi SQL.

### 9.2. Try.Success chứa lỗi bất đồng bộ ở bên trong

~~~java
Try<CompletableFuture<String>> result =
        Try.success(new CompletableFuture<>());
~~~

Try hiện là **Success**, vì vậy Spring không đánh dấu rollback dựa trên Vavr Failure. Future bên trong chưa được xử lý qua cơ chế nhận diện Future trực tiếp của return type; cần tự thiết kế transaction cho công việc bất đồng bộ.

### 9.3. Custom Result/Either/Optional/ResponseEntity

Hỗ trợ nhận diện Vavr Try và Future ở đây **không có nghĩa** bất kỳ object có phương thức isFailure(), isError() hoặc HTTP status 500 đều tự làm Spring rollback. Ví dụ một service trả về **Either.Left(error)** hoặc **ResponseEntity.status(500)** nhưng không ném exception và không đặt rollback-only có thể vẫn commit. Khi dùng Result kiểu tự định nghĩa, cần chuyển lỗi thành exception đúng boundary hoặc dùng transaction API rõ ràng.

### 9.4. Nuốt exception rồi trả Future đã thành công

~~~java
// Snippet minh họa: nếu không có rollback-only khác, Spring có thể commit.
@Transactional
public CompletableFuture<String> silentlyRecover() {
    try {
        repository.write();
        repository.operationThatFails();
    } catch (RuntimeException ex) {
        return CompletableFuture.completedFuture("recovered");
    }
    return CompletableFuture.completedFuture("ok");
}
~~~

Nếu exception bị catch, Spring không nhìn thấy lỗi thoát ra. Future trả về hoàn tất **thành công**, nên không có Future exceptional failure để đánh dấu rollback. Mặt khác, nếu một repository transaction scope ở bên trong đã đánh dấu transaction vật lý rollback-only, outer vẫn có thể rollback hoặc nhận UnexpectedRollbackException; không nên khẳng định nó luôn commit.

### 9.5. Future thành công khi method trả về, lỗi ở nơi khác sau đó

Không thể kết luận transaction “phải rollback” chỉ vì downstream consumer, webhook hoặc UI sau này thất bại. Giao dịch cục bộ có một ranh giới đã kết thúc. Để phối hợp DB và message/event, dùng transactional outbox, idempotency, xử lý bù trừ hay workflow phù hợp thay vì mong Future exceptional completion điều khiển lại commit cũ.

### 9.6. Không có proxy hoặc manager phù hợp

Chính @Transactional chỉ là metadata. Tự gọi this.method() trong cùng object ở Spring proxy mode có thể bỏ qua transaction advice. Tạo object bằng new ở ngoài Spring context cũng vậy. Future/Try handling cần **transactional interception thực sự**; kiểm tra bean được gọi qua Spring proxy, transaction manager và DataSource đúng.

## 10. Phân biệt với transaction reactive

Với **ReactiveTransactionManager** (ví dụ R2DBC), Spring xử lý Mono/Flux dựa trên **reactive subscription và Reactor Context**. Công việc có thể bắt đầu sau khi reactive method đã trả Publisher mà transaction vẫn được đặt đúng xung quanh publisher subscription.

Điều này khác với **PlatformTransactionManager JDBC imperative** được dùng ở bài này. Không dùng nhận định “Future failed after method return không rollback” để suy ra một quy tắc tương tự cho mọi Mono.error hoặc Flux error. Cũng không mặc nhiên cho JDBC code chạy trong reactive chain tham gia R2DBC transaction.

Nếu ứng dụng dùng @Transactional với reactive return type và ReactiveTransactionManager, phải đọc tài liệu reactive transaction tương ứng. Nếu nó dùng JDBC blocking và trả Future, phải hiểu chính xác boundary của JDBC transaction được mở lúc nào và trên thread nào.

## 11. Bảng chẩn đoán các ca dễ sai

| Triệu chứng | Nguyên nhân khả dĩ | Việc cần kiểm chứng |
| --- | --- | --- |
| Try.Failure(RuntimeException) vẫn commit | Spring trước 5.2, không đi qua proxy, noRollbackFor, sai manager, transaction khác đã commit | Version Spring, rollback rule, bean/proxy, DataSource |
| Try.Failure(IOException) commit | Checked cause không khớp default rollback rule | rollbackFor, ALL_EXCEPTIONS và policy khác |
| CompletableFuture.failedFuture(RuntimeException) vẫn commit | Spring trước 6.1, Future không trực tiếp là result được intercept, sai proxy/manager | Version, return type thật, interceptor trace |
| Future failed sau vài giây nhưng DB không rollback | Future pending tại return, transaction đã commit | Timeline return vs completeExceptionally; readback DB |
| Future thất bại đã done nhưng DB vẫn ghi | Cause checked, noRollbackFor, outer context khác hoặc transaction manager không tham gia SQL | Cause thực sự và rollback rule, resource mapping |
| Future isCompletedExceptionally=true khi caller kiểm tra nhưng dữ liệu vẫn commit | Future có thể vừa hoàn tất *sau* return; caller nhìn thấy trạng thái sau đó | Timestamp tại chính transactional boundary |
| @Async method chạy SQL không tham gia transaction của caller | Context imperative thường gắn thread, @Async chuyển execution | Advisor/proxy, thread, manager trong worker |
| @Transactional return Either.Left nhưng DB vẫn commit | Không phải Vavr Try.Failure; không có exception/rollback-only | Return type và cơ chế rollback được hỗ trợ |
| Rollback xảy ra nhưng caller vẫn nhận Try.Failure/Future failed | Spring có thể giữ nguyên return value rồi rollback | Dữ liệu DB sau transaction và trạng thái handle |
| UnexpectedRollbackException tại outer | Inner REQUIRED đánh dấu rollback-only | Logical scopes, rollback-only và transaction owner |

Một quy trình debug hiệu quả:

1. **Xác định Spring Framework version** thực tế của application runtime.
2. **Xác định method được interceptor chặn**; tránh self-invocation, @Async nhầm thread và method nằm ngoài Spring bean.
3. **Xác định return type thật**: Throwable ném trực tiếp, Vavr Try, Future, nested Future, hoặc custom result.
4. **Xác định thời điểm** result là Failure/exceptionally completed: trước hay sau transactional method return.
5. **Xác định Throwable cause và rollback rules**: runtime, checked, rollbackFor/noRollbackFor, ALL_EXCEPTIONS.
6. **Xác định transaction owner và tài nguyên**, đặc biệt khi propagation REQUIRED đã tham gia outer transaction.
7. **Đọc lại dữ liệu từ transaction/connection độc lập** sau khi hoàn tất để khẳng định có commit hoặc rollback.
8. **Đọc log/metrics** nếu còn nghi vấn về SQL, connection pool, async thread hoặc commit failure.

## 12. Những câu hỏi tự kiểm tra

**Câu 1.** Một method @Transactional ở Spring 6.2 trả Try.failure(new IllegalStateException(...)) sau UPDATE. Có cần ném exception ra ngoài để rollback không?  
**Đáp án:** Không, nếu Vavr Try.Failure là giá trị trực tiếp interceptor quan sát và rollback rule khớp, Spring đánh dấu rollback-only khi kiểm tra kết quả.

**Câu 2.** Try.Failure(new IOException(...)) có chắc rollback mặc định không?  
**Đáp án:** Không. Với default unchecked-only, IOException là checked nên có thể commit. Thêm rollbackFor=IOException.class hoặc cấu hình default ALL_EXCEPTIONS trong Spring 6.2 nếu phù hợp.

**Câu 3.** Spring 6.0 có tự nhận diện CompletableFuture.failedFuture(...) để rollback theo cơ chế mới không?  
**Đáp án:** Không nên dựa vào tính năng đó; hỗ trợ Future/CompletableFuture failed-return theo tài liệu có từ Spring 6.1. Cần ném exception phù hợp hoặc dùng API transaction rõ ràng trên bản cũ.

**Câu 4.** Spring 6.2 method trả new CompletableFuture<>() pending rồi caller completeExceptionally sau khi method trả về. Giao dịch trước đó có tự rollback không?  
**Đáp án:** Không. Khi interceptor kiểm tra, Future chưa done nên không có cause; local transaction có thể đã commit. Hoàn tất Future sau đó không đảo ngược dữ liệu.

**Câu 5.** Vì sao có thể thấy Future isCompletedExceptionally=true ở caller nhưng DB vẫn commit?  
**Đáp án:** Caller có thể quan sát Future sau khi nó hoàn tất, trong khi tại thời điểm return ban đầu nó còn pending. Ngoài ra cause có thể không khớp rollback rule hoặc transaction khác đã commit.

**Câu 6.** Một Future đã failed với IOException tại return, method @Transactional(rollbackFor=IOException.class). Điều gì xảy ra ở Spring 6.2?  
**Đáp án:** Spring nhận cause IOException khi Future đã done và có thể đánh dấu rollback-only, làm transaction được rollback khi manager hoàn tất.

**Câu 7.** @Async có làm JDBC transaction của thread caller tự truyền sang mọi worker không?  
**Đáp án:** Không. Cần mở transaction tại boundary chạy SQL trong worker, dùng manager/resource phù hợp. @Async và @Transactional phải được áp dụng theo proxy/advisor và runtime context đúng.

**Câu 8.** Mono.error(...) có tương đương CompletableFuture.failedFuture(...) trong logic trên không?  
**Đáp án:** Không suy diễn. Mono/Flux dùng reactive transaction với ReactiveTransactionManager và subscription context; quy tắc Future tại return thuộc imperative transaction.

## 13. Kết luận thực hành

- **Vavr Try.Failure:** Spring hỗ trợ nhận diện từ **5.2**; cần cause khớp rollback rule.
- **Future/CompletableFuture failed:** Spring hỗ trợ kiểm tra kiểu trả về từ **6.1**; Future phải **đã hoàn tất bằng exception tại thời điểm method trả về** và cause khớp rule.
- **Future pending rồi thất bại sau đó:** không rollback hồi tố transaction cục bộ đã hoàn tất.
- **Rollback rule luôn quan trọng:** RuntimeException/Error khác checked Exception; rollbackFor, noRollbackFor và từ Spring 6.2 có thể cấu hình ALL_EXCEPTIONS.
- **Hạ tầng phải thực sự hoạt động:** Spring proxy/interceptor, TransactionManager và DataSource đúng tài nguyên.
- **Đo bằng dữ liệu DB sau transaction:** log, isFailure/isCompletedExceptionally và exception ở caller là tín hiệu bổ sung, không tự chứng minh thay đổi đã commit hoặc bị rollback.

## Tài liệu tham khảo

- [Spring Framework 6.2 — Rolling Back a Declarative Transaction](https://docs.spring.io/spring-framework/reference/6.2/data-access/transaction/declarative/rolling-back.html)
- [Spring Framework 6.2 — Using @Transactional và rollbackOn=ALL_EXCEPTIONS](https://docs.spring.io/spring-framework/reference/6.2/data-access/transaction/declarative/annotations.html)
- [Spring Framework 6.2 — Transaction Management](https://docs.spring.io/spring-framework/reference/6.2/data-access/transaction.html)
- [Spring Framework 5.2 — Data Access: Vavr Try rollback support](https://docs.spring.io/spring-framework/docs/5.2.24.RELEASE/spring-framework-reference/data-access.html)
- [Spring Framework 6.2.12 — TransactionAspectSupport implementation](https://github.com/spring-projects/spring-framework/blob/v6.2.12/spring-tx/src/main/java/org/springframework/transaction/interceptor/TransactionAspectSupport.java)
- [Vavr — Try documentation](https://docs.vavr.io/#_try)
- [Java SE 17 — CompletableFuture API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CompletableFuture.html)
