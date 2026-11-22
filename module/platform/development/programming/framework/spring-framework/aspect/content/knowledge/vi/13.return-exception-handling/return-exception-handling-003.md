# Checked exception, unchecked exception và chữ ký proxy interface trong Spring AOP

## 1. Vì sao cùng một exception lại có thể đổi kiểu khi đi qua Spring proxy?

Khi dùng Spring `@Aspect`, bạn có thể nhìn thấy tình huống tưởng như nghịch lý:

- Trong `@Around` advice, lệnh `throw new IOException("...")` được thực thi.
- Nhưng caller của service lại bắt được **`java.lang.reflect.UndeclaredThrowableException`**, không phải `IOException` trực tiếp.
- Với `IllegalStateException`, caller lại nhận đúng exception gốc.
- Nếu interface method có khai báo `throws IOException`, `IOException` có thể truyền qua JDK proxy mà không bị bọc.

Khác biệt này liên quan trực tiếp đến **hợp đồng `throws` của method được gọi trên JDK dynamic proxy**. Spring AOP dùng proxy để chặn method execution của Spring-managed beans; khi chọn **JDK dynamic proxy**, proxy thực thi giao diện Java. JVM/JDK generated proxy có quy tắc rất cụ thể đối với checked exception được `InvocationHandler` ném ra.

Điều kiện tổng quát:

> Một JDK proxy có thể truyền trực tiếp unchecked `RuntimeException`/`Error` và checked exception **tương thích với `throws` được method trên proxy interface khai báo**. Nếu invocation handler ném một checked exception không tương thích với hợp đồng đó, lời gọi trên proxy sẽ ném `java.lang.reflect.UndeclaredThrowableException` chứa exception gốc.

Đây là quy tắc của JDK proxy mà Spring AOP phải hoạt động bên trong, **không phải mọi `IOException` trong Spring tự động bị bọc**.

**Phạm vi bài:** Cách Spring `@AspectJ` advice tác động đến exception qua **Spring AOP proxy**, đặc biệt interface method, JDK proxy, class-based CGLIB proxy, `@Around` và `@AfterThrowing`. Không đi sâu lý thuyết exception Java chung không liên quan Spring, cũng không bàn AspectJ bytecode weaving ngoài Spring.

### Kết quả học tập

Sau bài học, bạn có thể:

1. Phân biệt checked `Exception` với unchecked `RuntimeException`/`Error` **khi truyền qua Spring JDK proxy**.
2. Hiểu sự khác nhau giữa `throws` của **proxy interface method**, `throws` của implementation method và `throws Throwable` trên advice.
3. Giải thích chính xác lúc nào xuất hiện `java.lang.reflect.UndeclaredThrowableException` và cách tìm cause gốc.
4. Viết `@Around` quan sát/rethrow kết quả mà không vô ý làm thay đổi hợp đồng exception.
5. Bind `@AfterThrowing(throwing="...")` đúng và hiểu vị trí advisor ảnh hưởng exception advice quan sát.
6. Phân biệt giới hạn JDK proxy với class-based CGLIB proxy mà không kết luận quá rộng.
7. Chạy Java 17/Spring Framework demo đầy đủ: normal return, checked declared, checked undeclared từ advice, unchecked exception.
8. Chẩn đoán vấn đề exception cùng với proxy type, self-invocation, transaction và nhiều advisors.

## 2. Ba lớp hợp đồng liên quan đến một lời gọi

Giả sử caller thực hiện:

```java
ReportApi api = context.getBean(ReportApi.class);
api.load();
```

Trong Spring AOP có ba lớp cần tách:

| Lớp | Ví dụ | Vai trò |
| --- | --- | --- |
| **Proxy interface API** | `interface ReportApi { String load() throws IOException; }` | Hợp đồng mà caller sử dụng; JDK-generated proxy method có danh sách checked exceptions được phép khai báo |
| **Target implementation** | `class ReportService implements ReportApi` | Chứa mã Java nghiệp vụ; có thể trả kết quả hoặc throw |
| **Spring advice/interceptor** | `@Around ... throws Throwable` | Có thể gọi `proceed()`, bắt/rethrow hoặc tạo exception mới trước/sau target |

Đường đi thông thường:

```text
Caller (kiểu ReportApi)
    |
    v
JDK-generated Spring AOP proxy
    |
    v
JdkDynamicAopProxy / InvocationHandler
    |
    +--> Spring advisor/interceptor chain
    |       |
    |       +--> @Around advice (throws Throwable)
    |       |
    |       +--> other advisors, if any
    |       |
    |       +--> target method
    |
    v
Proxy method boundary checks outgoing Throwable
    |
    +--> checked exception compatible with interface throws: pass through
    +--> RuntimeException / Error: pass through
    +--> undeclared checked exception: wrap in UndeclaredThrowableException
    |
    v
Caller
```

Điểm quan trọng là **`throws Throwable` ở advice không “mở rộng” chữ ký của `ReportApi.load()`**. Java source có thể cho phép advice khai báo `throws Throwable` vì `ProceedingJoinPoint.proceed()` ném `Throwable`, nhưng proxy interface vẫn có hợp đồng `throws` riêng.

## 3. Checked và unchecked trong hợp đồng JDK proxy

### 3.1. Checked exception được interface khai báo

```java
public interface ReportApi {
    String load() throws IOException;
}
```

`IOException` là checked exception được interface method khai báo. Nếu target hoặc advice ném `IOException` và không có interceptor khác biến đổi nó, JDK proxy có thể truyền trực tiếp `IOException` cho caller.

Nếu method khai báo `throws Exception`, `IOException` cũng phù hợp (vì là subtype của `Exception`). Nếu chỉ khai báo `throws FileNotFoundException`, một `IOException` chung không tự động phù hợp vì không phải subtype của `FileNotFoundException`.

Một interface khai báo `throws IOException` **không buộc** mọi lời gọi phải ném `IOException`; nó chỉ nêu rằng method có thể throw. `RuntimeException`/`Error` vẫn có thể được ném mà không cần liệt kê trong `throws`.

### 3.2. Unchecked exception không cần khai báo trong interface

```java
public interface ReportApi {
    String load();
}
```

Nếu target hoặc advice ném `IllegalStateException`, nó là subtype của `RuntimeException`, nên không gặp hạn chế checked-exception signature của JDK proxy.

Tương tự, `Error` và các subtype là unchecked. Không nên chủ động catch tất cả `Error` rồi thay thành trạng thái thành công; lỗi hệ thống nghiêm trọng cần được truyền/giám sát phù hợp.

### 3.3. Checked exception không có trong proxy interface throws

```java
public interface ReportApi {
    String load();
}
```

Nếu một **Spring `@Around` advice** ném `new IOException("from advice")` khi method `load()` không khai báo `throws IOException`, JDK generated proxy không thể trình bày nó như một checked exception hợp lệ của interface method. Nó bọc exception gốc:

```text
java.lang.reflect.UndeclaredThrowableException
    |
    +-- getUndeclaredThrowable() -> java.io.IOException("from advice")
```

Caller có thể kiểm tra `ex.getUndeclaredThrowable()` hoặc cause để tìm lỗi gốc, nhưng cách sửa bền vững không phải “lúc nào cũng unwrap ở caller”: **cần thiết kế hợp đồng lỗi của service và advice cho đúng**.

### 3.4. Bảng kết quả mong đợi với JDK dynamic proxy

| Throwable thoát khỏi interceptor chain | `interface method throws` | Caller thường nhận |
| --- | --- | --- |
| `new IOException("disk")` | `throws IOException` | `IOException` |
| `new FileNotFoundException("file")` | `throws IOException` | `FileNotFoundException` |
| `new IOException("disk")` | không khai báo checked exception | `UndeclaredThrowableException` chứa `IOException` |
| `new IOException("disk")` | `throws SQLException` | `UndeclaredThrowableException` chứa `IOException` |
| `new IllegalStateException("bad")` | không có `throws` | `IllegalStateException` |
| `new AssertionError("broken")` | không có `throws` | `AssertionError` |
| `new IOException("disk")` | `throws Exception` | `IOException` |

**Giả định:** Đang nói về `java.lang.reflect.Proxy` thông qua Spring JDK proxy, exception thực sự thoát ra từ invocation handler và không bị advisor khác đổi trước boundary. Kết quả khi nhiều interface có cùng method signature nhưng ràng buộc `throws` khác nhau cần xem kỹ hợp đồng của proxy method tương ứng; tránh dựa vào một mặt interface rồi bỏ qua những interface cùng được proxy.

## 4. Lỗi quan trọng: implementation không thể tự mở rộng checked throws

Giả sử:

```java
interface JobApi {
    void run();
}
```

Đoạn implementation dưới đây **không hợp lệ tại compile time**:

```java
class JobService implements JobApi {
    @Override
    public void run() throws IOException {
        throw new IOException("disk");
    }
}
```

Java không cho overriding method tự thêm **checked exception mới, rộng hơn hoặc không tương thích** với hợp đồng interface method. Đây là lỗi `javac`, **không phải lỗi Spring proxy runtime**.

Vậy `IOException` undeclared xuất hiện từ đâu khi interface vẫn không khai báo? Những nguồn thực tế có thể là:
- `@Around` advice tự tạo `IOException` với signature `throws Throwable`.
- Advice `@Before`, `@After`, `@AfterThrowing` hoặc custom interceptor ném checked exception không phù hợp interface.
- Một thư viện/reflection/sneaky-throw technique truyền checked exception qua đường không bị compiler kiểm tra như source-level override.
- Advisor đổi một exception đã khai báo sang checked exception khác không tương thích.

**Mẫu cần tránh:** thay đổi exception trong aspect rồi kỳ vọng caller `catch(IOException)` luôn bắt được dù interface method không khai báo `throws IOException`.

## 5. @Around: proceed() và rethrow đúng để giữ hợp đồng

```java
@Aspect
public class ExceptionAspect {

    @Around("execution(* com.example.app.service..*.*(..))")
    public Object observe(ProceedingJoinPoint pjp) throws Throwable {
        try {
            return pjp.proceed();
        } catch (Throwable error) {
            System.out.println(
                "aspect:saw:" + error.getClass().getSimpleName());
            throw error;
        }
    }
}
```

Đây là snippet minh họa chưa có Spring configuration hoàn chỉnh; code chạy đầy đủ có ở phần 9.

**Vì sao khai báo `throws Throwable`?** `ProceedingJoinPoint.proceed()` khai báo `throws Throwable`. Advice có quyền quan sát rồi rethrow nguyên Throwable; nhưng quyết định cuối cùng caller nhận exception trực tiếp hay wrapper vẫn chịu ảnh hưởng của **proxy method contract và các advisor khác**.

Không viết:

```java
catch (Throwable error) {
    throw new IOException("wrapped", error);
}
```

nếu pointcut advice bao phủ nhiều service methods mà một số method không khai báo `IOException`. Nếu dùng JDK proxy, phần lớn những lời gọi ấy có thể bắt đầu sinh `UndeclaredThrowableException` ở caller.

### 5.1. Lỗi được tạo **trước** khi proceed

```java
@Around("execution(* com.example.api.JobApi.run(..))")
public Object validate(ProceedingJoinPoint pjp) throws Throwable {
    throw new IOException("validation infrastructure failure");
}
```

Đây là snippet giả định interface method `run()` tồn tại, với checked exception chưa khai báo. Nếu Spring JDK proxy thực hiện method không có `throws IOException`, advice đã ném checked exception và **target không được chạy**; caller có thể nhận wrapper `UndeclaredThrowableException`.

### 5.2. Lỗi từ target và lỗi từ advice khác nhau

Trong logging, nên phân biệt:
- `target_failure`: target logic thực sự đã ném exception;
- `advice_failure`: instrumentation/logging/auditing aspect tự ném exception;
- `proxy_boundary_wrapping`: JDK proxy đổi exception **được phát ra ngoài interceptor chain** thành wrapper do `throws` không tương thích.

Lưu ý `UndeclaredThrowableException` **không chứng minh target ném lỗi**. Nó có thể chỉ là bằng chứng một aspect đã ném checked exception sai hợp đồng, trong khi target không hề được gọi.

### 5.3. Không biến catch-all thành hành vi nuốt lỗi

```java
catch (Throwable error) {
    return null;
}
```

không phải cách sửa `UndeclaredThrowableException`. Nếu target trả primitive hoặc cần kết quả không-null, `null` có thể làm caller lỗi khác. Nếu operation thay đổi trạng thái nghiệp vụ, return bình thường sau lỗi còn có thể làm sai transaction rollback và hành vi ứng dụng. Hãy dùng exception policy có chủ đích, tránh conceal nguyên nhân.

## 6. @AfterThrowing quan sát gì?

Spring `@AfterThrowing` chạy khi **join point phù hợp kết thúc bằng exception**, và có thể bind exception qua `throwing`:

```java
@AfterThrowing(
    pointcut = "execution(* com.example.app.service..*.*(..))",
    throwing = "cause",
    argNames = "cause"
)
public void onThrown(Throwable cause) {
    System.out.println(cause.getClass().getSimpleName());
}
```

Snippet nằm trong Spring `@Aspect` bean. Nếu dùng `Throwable`, binding không tự loại checked exceptions; nếu đổi thành `RuntimeException`, advice có thể chỉ chạy với exception thuộc runtime hierarchy.

**Điểm tinh tế:** Trong JDK proxy, `java.lang.reflect.UndeclaredThrowableException` có thể được tạo **ở lớp proxy/generated method sau khi Spring AOP interceptor chain đã ném IOException ra ngoài**. `@AfterThrowing` nằm **bên trong** Spring AOP chain có thể quan sát `IOException` gốc, trong khi caller bên ngoài nhận `UndeclaredThrowableException`. Không lấy `@AfterThrowing` log làm cam kết exception type cuối cùng của caller.

Ngược lại, nếu một advisor ở phía trong đã tạo wrapper trước khi `@AfterThrowing` chạy, advice có thể nhìn thấy wrapper. Thực tế quan sát luôn phụ thuộc **vị trí interceptor**.

### 6.1. Binding không đổi exception type

```java
@AfterThrowing(
    pointcut = "execution(* com.example.app.service..*.*(..))",
    throwing = "error",
    argNames = "error"
)
public void onChecked(IOException error) {
    // Chỉ quan sát IOException phù hợp; không tự chuyển
    // IOException thành RuntimeException.
}
```

Một `@AfterThrowing` chỉ log và return bình thường **không swallow exception gốc**. Nếu advice tự ném exception mới, exception mới có thể ghi đè exception cũ. Cần cân nhắc tương thích `throws` của proxy method trước khi ném checked exception từ chính advice.

### 6.2. Nếu target tự catch IOException rồi return?

```java
public String safeLoad() {
    try {
        return fetch();
    } catch (IOException ex) {
        return "FALLBACK";
    }
}
```

Đây là snippet minh họa, chưa định nghĩa `fetch()`. Nếu exception được target bắt và method return bình thường, `@AfterThrowing` cho `safeLoad` **không chạy** vì không có exceptional completion của method execution, dù bên trong source đã từng ném `IOException`.

### 6.3. @AfterReturning và @After

- `@AfterReturning` xử lý normal completion; `null` vẫn là normal return.
- `@AfterThrowing` xử lý exceptional completion đi ra từ join point.
- `@After` có semantics finally trên normal/exception.
- `@Around` kiểm soát `proceed()`, có thể catch/rethrow/fallback nên outcome ở bên ngoài chain có thể khác outcome của target.

Cả bốn đều phải được Spring AOP chặn qua proxy mới có hiệu lực.

## 7. JDK proxy và CGLIB: so sánh đúng giới hạn

Spring Framework hỗ trợ hai cơ chế proxy phổ biến:

| Tiêu chí | JDK dynamic proxy | CGLIB class-based proxy |
| --- | --- | --- |
| Tạo proxy bằng | `java.lang.reflect.Proxy` / interface implementations | Subclass runtime của target class |
| Method client có thể gọi qua proxy | Những method expose bởi interfaces được proxy | Những method có thể truy cập/override theo class proxy |
| Quan hệ với target implementation class | Proxy thường **không instanceof** implementation | Proxy là subclass của implementation |
| Kiểm tra checked exception không khai báo | JDK `InvocationHandler` rule: checked không phù hợp `throws` dẫn đến `java.lang.reflect.UndeclaredThrowableException` | Không tự áp quy tắc `java.lang.reflect.Proxy` của JDK; hành vi thực tế phụ thuộc generated method/interceptor, phải test |
| `final` class | Có thể proxy qua interface nếu target class final vẫn implement interface phù hợp | Không thể subclass final class |
| `final` / `private` target method | JDK proxy có thể intercept interface method được expose (không override target class method) | Không thể override final/private method |
| Self-invocation | Bypass Spring AOP proxy | Bypass Spring AOP proxy |

**Không kết luận “CGLIB bảo đảm mọi checked exception ném trực tiếp không wrap”.** CGLIB có interceptor/code-generation riêng và có những kiểu wrapper của chính CGLIB hoặc framework. Quy tắc đặc thù `java.lang.reflect.UndeclaredThrowableException` phía trên được chuẩn JDK đảm bảo cho **JDK dynamic proxy**. Nếu chọn CGLIB, hãy kiểm tra thực nghiệm loại exception/cause trên phiên bản Spring ứng dụng đang chạy và trên signature target cụ thể.

Cũng **không đổi sang CGLIB chỉ để che một interface throws contract sai**. Nếu API có lỗi Checked exception contract, sửa interface, đổi exception policy hoặc chuyển lỗi thành unchecked loại có ý nghĩa là thiết kế bền vững hơn.

### 7.1. Tham khảo cấu hình Spring

```java
@Configuration
@EnableAspectJAutoProxy(proxyTargetClass = false)
public class JdkProxyConfig {
}
```

Trong một Spring context phù hợp, `proxyTargetClass=false` cho phép chọn JDK proxy khi target triển khai interface. Muốn class-based proxy:

```java
@Configuration
@EnableAspectJAutoProxy(proxyTargetClass = true)
public class CglibProxyConfig {
}
```

Đây là **hai snippet cấu hình thay thế**, không nên import đồng thời hai configuration vào cùng context rồi dự đoán mỗi bean có một kiểu proxy; thiết lập class-based proxy có thể được hợp nhất giữa các cơ chế auto-proxy. Ví dụ runnable tiếp theo chỉ dùng JDK proxy để kết quả được suy ra chắc chắn từ `InvocationHandler` Javadoc.

## 8. Checked exceptions trong API design và Spring aspects

### 8.1. Giữ hợp đồng explicit khi caller thực sự xử lý lỗi

Nếu caller cần bắt và phục hồi khi `IOException`:

```java
public interface DocumentApi {
    byte[] load(String id) throws IOException;
}
```

Implementation được phép throw `IOException` hoặc subtype. Trong `@Around`, nếu service method và advice rethrow `IOException`, JDK proxy nhận exception phù hợp `throws`.

Một API khai báo `throws Exception` cũng có thể cho phép `IOException`, nhưng nó quá rộng và đẩy gánh nặng xử lý lỗi sang caller. Chọn checked type cụ thể khi contract thật sự cần biểu diễn lỗi phục hồi được.

### 8.2. Khi không thể hoặc không nên khai báo checked exception

Có thể chọn **unchecked domain exception** rõ ràng:

```java
public class ReportUnavailableException extends RuntimeException {
    public ReportUnavailableException(String message, Throwable cause) {
        super(message, cause);
    }
}
```

Trong Spring advice:

```java
try {
    return pjp.proceed();
} catch (IOException ex) {
    throw new ReportUnavailableException("Cannot load report", ex);
}
```

Cả hai là **snippets cần đặt trong project thật**; không dán vào demo nếu chưa đổi code/expected stdout. Chuyển sang unchecked domain exception là **thay đổi hợp đồng lỗi có chủ đích**. Không dùng `RuntimeException` chung không message/cause; cần giữ nguyên `ex` làm cause để debug.

### 8.3. Đừng mở rộng throws chỉ để vừa logging aspect

Một `@Before` ghi log không nên cố throw `IOException` chỉ vì log sink bị lỗi, rồi bắt toàn bộ service interfaces khai báo `throws IOException`. Với instrumentation không critical, cân nhắc logging fallback/retry nội bộ và metric báo lỗi instrument. Với audit bắt buộc, thiết kế contract/thất bại kiểm soát rõ, không vô tình thay exception type tại JDK proxy boundary.

### 8.4. Khi nhiều interfaces có cùng method

JDK proxy có thể implement **nhiều** interfaces. Nếu chúng có method với cùng tên/chữ ký tham số nhưng `throws` khác nhau, exception type được phép có thêm ràng buộc. Đừng chỉ kiểm tra interface mà caller tình cờ cast vào; xem tất cả proxied interfaces có liên quan, compiler/JDK proxy quy tắc cho duplicate method signatures và viết integration test trên proxy thực.

## 9. Ví dụ Java 17 + Spring Framework đầy đủ

Ví dụ sử dụng một Spring service implementing interface có bốn operations:

1. `success()`: trả bình thường.
2. `declaredChecked() throws IOException`: target ném `IOException` đã khai báo hợp lệ.
3. `undeclaredChecked()`: **không có `throws IOException`**, nhưng `@Around` tự ném `IOException` trước khi target được gọi.
4. `failUnchecked()`: target ném `IllegalStateException` (unchecked).

Điểm mấu chốt: sự khác nhau giữa **checked được phép** và **checked không được phép** xuất hiện tại method boundary của **JDK dynamic proxy**, chứ không cần viết implementation Java không hợp lệ.

**Môi trường**: Java 17+, Spring Framework `6.1.14`, AspectJ Weaver `1.9.22.1`, Gradle. Dùng Spring Framework thuần, không phụ thuộc Spring Boot auto-configuration.

### 9.1. Cấu trúc project

```text
spring-aop-exception-contract/
├── settings.gradle
├── build.gradle
└── src/main/java/demo/proxycase/
    ├── ReportApi.java
    ├── ReportService.java
    ├── CheckedAspect.java
    ├── AppConfig.java
    └── DemoApplication.java
```

### 9.2. Gradle

`settings.gradle`:

```groovy
rootProject.name = 'spring-aop-exception-contract'
```

`build.gradle`:

```groovy
plugins {
    id 'java'
    id 'application'
}

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    implementation 'org.springframework:spring-context:6.1.14'
    implementation 'org.springframework:spring-aop:6.1.14'
    implementation 'org.aspectj:aspectjweaver:1.9.22.1'
}

application {
    mainClass = 'demo.proxycase.DemoApplication'
}
```

### 9.3. Interface contract

`src/main/java/demo/proxycase/ReportApi.java`:

```java
package demo.proxycase;

import java.io.IOException;

public interface ReportApi {
    String success();

    String declaredChecked() throws IOException;

    String undeclaredChecked();

    String failUnchecked();
}
```

Trong bốn methods, **chỉ `declaredChecked()` khai báo `throws IOException`**. Đây là chi tiết quyết định behavior JDK proxy ở phần kiểm chứng.

### 9.4. Target implementation

`src/main/java/demo/proxycase/ReportService.java`:

```java
package demo.proxycase;

import java.io.IOException;

public class ReportService implements ReportApi {

    @Override
    public String success() {
        System.out.println("target:success");
        return "OK";
    }

    @Override
    public String declaredChecked() throws IOException {
        System.out.println("target:declaredChecked");
        throw new IOException("disk");
    }

    @Override
    public String undeclaredChecked() {
        System.out.println("target:undeclaredChecked");
        return "UNEXPECTED";
    }

    @Override
    public String failUnchecked() {
        System.out.println("target:failUnchecked");
        throw new IllegalStateException("boom");
    }
}
```

`undeclaredChecked` được viết **hợp lệ**: nó không khai báo và cũng không tự ném checked exception. Trong demo, exception checked không được khai báo sẽ xuất phát từ Spring `@Around`, không phải từ override Java trái luật.

### 9.5. Aspect tạo và quan sát các đường exception

`src/main/java/demo/proxycase/CheckedAspect.java`:

```java
package demo.proxycase;

import java.io.IOException;
import org.aspectj.lang.ProceedingJoinPoint;
import org.aspectj.lang.annotation.Around;
import org.aspectj.lang.annotation.Aspect;

@Aspect
public class CheckedAspect {

    @Around(
        "target(demo.proxycase.ReportService)"
        + " && execution(public * *(..))"
    )
    public Object observe(ProceedingJoinPoint pjp) throws Throwable {
        String method = pjp.getSignature().getName();

        System.out.println("around:enter:" + method);

        try {
            if ("undeclaredChecked".equals(method)) {
                throw new IOException("advice-checked");
            }
            return pjp.proceed();
        } catch (Throwable error) {
            System.out.println(
                "around:throw:" + method
                + ":" + error.getClass().getSimpleName());
            throw error;
        } finally {
            System.out.println("around:finally:" + method);
        }
    }
}
```

**Vì sao `@Around` khai báo `throws Throwable` không vi phạm Java compile?** Đây là advice method riêng, không phải implementation của `ReportApi`. Spring gọi nó trong interceptor chain, và `proceed()` có hợp đồng `throws Throwable`. Khi exception đi **ra ngoài** chain để JDK proxy trả cho caller, `throws` của **`ReportApi` method** mới là ranh giới cần xét.

**Điều demo cố ý làm:** Với `undeclaredChecked`, aspect ném `IOException` *trước khi gọi `proceed()`*. Vì thế **không có** dòng `target:undeclaredChecked` trên stdout. Nếu xuất hiện dòng ấy, advice đã đi vào target và demo không còn minh họa “checked do advice tạo trước target” như dự định.

### 9.6. Cấu hình Spring

`src/main/java/demo/proxycase/AppConfig.java`:

```java
package demo.proxycase;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableAspectJAutoProxy;

@Configuration(proxyBeanMethods = false)
@EnableAspectJAutoProxy(proxyTargetClass = false)
public class AppConfig {

    @Bean
    public ReportApi reportApi() {
        return new ReportService();
    }

    @Bean
    public CheckedAspect checkedAspect() {
        return new CheckedAspect();
    }
}
```

`@Bean reportApi()` trả về interface `ReportApi`; runtime object thực là `ReportService` implementing interface. `@EnableAspectJAutoProxy(proxyTargetClass = false)` dùng proxy theo interface trong cấu hình này.

`@Bean checkedAspect()` đăng ký aspect; `@Aspect` riêng lẻ không biến một Java class thành Spring bean. Vì pointcut xét target `ReportService`, advice áp dụng cho method execution của service qua proxy, không tự advise Spring infrastructure hoặc chính aspect.

### 9.7. Main kiểm tra exception phía caller

`src/main/java/demo/proxycase/DemoApplication.java`:

```java
package demo.proxycase;

import java.io.IOException;
import java.lang.reflect.UndeclaredThrowableException;
import org.springframework.aop.support.AopUtils;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

public class DemoApplication {

    public static void main(String[] args) {
        try (AnnotationConfigApplicationContext context =
                new AnnotationConfigApplicationContext(AppConfig.class)) {

            ReportApi api = context.getBean(ReportApi.class);
            System.out.println(
                "jdkProxy=" + AopUtils.isJdkDynamicProxy(api));

            System.out.println("caller:success:" + api.success());

            try {
                api.declaredChecked();
            } catch (IOException ex) {
                System.out.println("caller:declared:"
                    + ex.getClass().getSimpleName()
                    + ":" + ex.getMessage());
            }

            try {
                api.undeclaredChecked();
            } catch (UndeclaredThrowableException ex) {
                Throwable original = ex.getUndeclaredThrowable();
                System.out.println("caller:undeclared:"
                    + ex.getClass().getSimpleName()
                    + ":" + original.getClass().getSimpleName()
                    + ":" + original.getMessage());
            }

            try {
                api.failUnchecked();
            } catch (IllegalStateException ex) {
                System.out.println("caller:unchecked:"
                    + ex.getClass().getSimpleName()
                    + ":" + ex.getMessage());
            }
        }
    }
}
```

**Lưu ý thiết kế:** Caller của `api.undeclaredChecked()` **không thể** viết `catch(IOException ex)` quanh riêng lời gọi ấy trong Java source nếu không có statement nào khác trong vùng try có thể throw IOException: compiler có thể báo checked exception “never thrown”. Vì vậy demo bắt `UndeclaredThrowableException`, một `RuntimeException`.

Trong xử lý lỗi production, thường nên thiết kế interface/advice consistent để caller không phải unwrap wrapper. Đoạn `getUndeclaredThrowable()` ở đây chỉ nhằm **minh họa nguyên nhân**.

### 9.8. Chạy project

Tại thư mục chứa `build.gradle`:

```bash
gradle run
```

Nếu project có Gradle Wrapper, sử dụng `./gradlew run` (Linux/macOS) hoặc `gradlew.bat run` (Windows).

### 9.9. Stdout dự kiến của Java code

```text
jdkProxy=true
around:enter:success
target:success
around:finally:success
caller:success:OK
around:enter:declaredChecked
target:declaredChecked
around:throw:declaredChecked:IOException
around:finally:declaredChecked
caller:declared:IOException:disk
around:enter:undeclaredChecked
around:throw:undeclaredChecked:IOException
around:finally:undeclaredChecked
caller:undeclared:UndeclaredThrowableException:IOException:advice-checked
around:enter:failUnchecked
target:failUnchecked
around:throw:failUnchecked:IllegalStateException
around:finally:failUnchecked
caller:unchecked:IllegalStateException:boom
```

Đây là những dòng do Java code tự in, không tính Gradle, Spring logging hoặc các thông tin môi trường khác.

### 9.10. Phân tích output theo chữ ký interface

| Phương thức | Checked `throws` trên `ReportApi` | Exception gốc trong advice/target | Caller nhận |
| --- | --- | --- | --- |
| `success()` | Không | Không | `"OK"` |
| `declaredChecked()` | `IOException` | `IOException("disk")` từ target | `IOException("disk")` |
| `undeclaredChecked()` | Không | `IOException("advice-checked")` từ `@Around` | `java.lang.reflect.UndeclaredThrowableException` |
| `failUnchecked()` | Không | `IllegalStateException("boom")` từ target | `IllegalStateException("boom")` |

Ba đặc điểm đáng quan sát:

1. Log `around:throw:undeclaredChecked:IOException` xuất hiện **trước** dòng caller nhận `UndeclaredThrowableException`. Advice nhìn thấy exception gốc, còn JDK proxy boundary thay đổi hình thức ngoại lệ.
2. Không có `target:undeclaredChecked`: ngoại lệ checked được tạo **trong aspect**, target chưa chạy. Do đó không được kết luận target thất bại chỉ từ việc caller nhận `UndeclaredThrowableException`.
3. `failUnchecked` được truyền nguyên loại `IllegalStateException` vì nó là unchecked; interface method không cần liệt kê `throws IllegalStateException`.

Đây là kết quả của cấu hình demo JDK proxy. Nếu thêm một aspect khác để catch, wrap hoặc swallow exception trước khi tới generated proxy, output phải được cập nhật theo advisor ordering mới.

## 10. Khi nào @Around tạo UndeclaredThrowableException ngoài mong muốn?

Có một số pattern lỗi phổ biến.

### 10.1. Logging aspect ném checked exception mới

```java
@Around("execution(* demo.proxycase..*.*(..))")
public Object log(ProceedingJoinPoint pjp) throws Throwable {
    auditSink.write("start"); // giả sử có thể throw IOException
    return pjp.proceed();
}
```

Đây là snippet **không độc lập**: `auditSink` là dependency giả định. Nếu `auditSink.write` throw checked `IOException` và proxy interface method được advice không khai báo IOException, JDK proxy có thể bọc. Thực tế target có thể chưa chạy.

Biện pháp: quyết định rõ **audit failure policy**. Nếu audit bắt buộc, thể hiện lỗi trong service contract/domain unchecked exception. Nếu audit không critical, kiểm soát/log lỗi instrumentation riêng thay vì vô tình làm mọi API bị wrapper.

### 10.2. After-throwing advice thay exception gốc bằng checked type khác

```java
@AfterThrowing(
    pointcut = "execution(* demo.proxycase..*.*(..))",
    throwing = "error",
    argNames = "error"
)
public void changeFailure(Throwable error) throws IOException {
    throw new IOException("audit failed", error);
}
```

Đoạn này **không khuyến nghị**. Khi target đã throw `IllegalStateException` nhưng after-throwing advice đổi thành checked `IOException` mà interface method không khai báo, JDK proxy có thể wrap `IOException`. Caller mất cái nhìn trực tiếp về lỗi target; original exception chỉ còn dưới cause. Một advice quan sát lỗi nên log và return, không ném exception mới trừ khi có policy cụ thể.

### 10.3. Sai lầm “advice throws Throwable là đủ”

`throws Throwable` trên advice chỉ khiến Java compiler chấp nhận những exception đi qua lời gọi `proceed()`. Nó **không chỉnh bytecode method signature của interface** và không thông báo cho caller nên bắt `IOException`. Cần đánh giá tầng API interface và tầng advice riêng.

### 10.4. Luôn unwrap ở caller thay vì sửa hợp đồng

Việc unwrap `UndeclaredThrowableException` có thể hữu ích trong diagnostics, nhưng nếu ứng dụng phải unwrap ở mọi caller vì aspect liên tục tạo checked exception sai interface contract, đó là dấu hiệu sai thiết kế. Hãy thống nhất:
- Những checked exception caller cần xử lý;
- Những unchecked domain exceptions mô tả lỗi không thể phục hồi ở tầng này;
- Những lỗi instrumentation không nên phá operation;
- Thứ tự các advisor được phép catch/wrap.

## 11. Spring transaction và rollback: không đồng nhất với checked/unchecked qua proxy

Với Spring Framework 6.1, Spring declarative transaction thường mặc định rollback với `RuntimeException` hoặc `Error`; checked `Exception` thường không tự kích hoạt rollback nếu không cấu hình `rollbackFor` phù hợp.

**Đây là quy tắc transaction**, **khác** quy tắc JDK proxy wrapping:

- JDK proxy quyết định caller nhìn thấy direct checked exception hay `UndeclaredThrowableException` từ interface `throws`.
- Spring transaction interceptor quyết định rollback theo exception mà **nó quan sát tại vị trí trong advisor chain** và rollback rules.
- Một exception checked có thể được `@Around` catch thành unchecked hoặc ngược lại trước khi transaction interceptor quan sát, tùy order.
- Nếu transaction interceptor đã quyết định rollback rồi, outer advice đổi exception thành fallback không tự hoàn nguyên quyết định đó.

Không suy ra “caller thấy `UndeclaredThrowableException` nên transaction chắc chắn rollback”. Cần inspect vị trí transaction advisor và exception thực sự mà nó đã nhận.

### Ví dụ policy theo domain

Nếu một thao tác ghi database phải rollback khi `BusinessCheckedException` thoát ra, có thể khai báo:

```java
@Transactional(rollbackFor = BusinessCheckedException.class)
public void applyChanges() throws BusinessCheckedException {
    // ...
}
```

Đây là snippet minh họa cần `@Transactional`, class `BusinessCheckedException`, Spring transaction manager và transaction AOP config. Nó không làm JDK proxy interface tự thêm `throws BusinessCheckedException`. Nếu service được gọi qua interface JDK proxy, interface contract vẫn phải tương thích để caller thấy checked exception trực tiếp.

## 12. JDK proxy có luôn được Spring sử dụng khi có interface?

Trong Spring AOP, nếu target triển khai interface, mặc định thường chọn JDK dynamic proxy, nhưng **không thể chỉ nhìn “có interface” là kết luận chắc chắn**:
- `@EnableAspectJAutoProxy(proxyTargetClass = true)` buộc class-based proxy;
- Spring Boot có thể cung cấp mặc định khác tùy phiên bản/properties/configuration;
- Các auto-proxy creators trong cùng context có thể hợp nhất cấu hình;
- Custom `ProxyFactory` có thể được thiết lập `setProxyTargetClass(true)`.

Kiểm tra thực tế:

```java
Object proxy = context.getBean("reportApi");
System.out.println(AopUtils.isAopProxy(proxy));
System.out.println(AopUtils.isJdkDynamicProxy(proxy));
System.out.println(AopUtils.isCglibProxy(proxy));
```

Đây là snippet chẩn đoán cần biến `context` và import `AopUtils`, không phải một file Java chạy độc lập.

Với JDK proxy, cách tốt nhất thường là inject interface và giữ checked `throws` contract rõ ràng. Với CGLIB, client có thể nhận class-based proxy, nhưng cần hiểu giới hạn `final`/`private` và không kỳ vọng checked-exception wrapping y hệt JDK proxy.

## 13. Self-invocation và ngoại lệ: proxy boundary bị bỏ qua

Giả sử target implementation:

```java
public void outer() {
    inner();
}

public void inner() {
    throw new IllegalStateException("boom");
}
```

Nếu caller gọi `outer()` qua Spring proxy:
- Advice match `outer()` có thể chạy.
- Lời gọi `this.inner()` ở **bên trong target** không qua proxy, nên advice chỉ match `inner()` không được kích hoạt cho lời gọi nội bộ.
- Ngoại lệ từ `inner()` vẫn có thể thoát qua `outer()` rồi tới proxy caller, nơi các rules exception/proxy interface signature áp dụng cho **method `outer()` được gọi**.

Đó là khác biệt giữa “Spring advice không chạy” và “Java exception không lan truyền”. Self-invocation không vô hiệu hóa Java exception; nó chỉ bypass Spring AOP interceptor chain cho lời gọi nội bộ.

Nếu muốn advice cho `inner()`, tách nó sang một Spring-managed collaborator và gọi qua proxy của collaborator. Đừng dùng `getTarget()` gọi trực tiếp rồi mong transaction/logging interceptors vẫn chạy.

## 14. Bảng xử lý lỗi nhanh

| Triệu chứng | Giải thích khả dĩ | Cách khắc phục |
| --- | --- | --- |
| Caller thấy `UndeclaredThrowableException` sau lời gọi JDK proxy | Checked exception không phù hợp `throws` của proxied interface method | Xem `getUndeclaredThrowable()`, xác định advice/target tạo lỗi, sửa API/policy |
| Aspect log `IOException` nhưng caller thấy wrapper | Wrapping diễn ra ở boundary JDK generated proxy sau inner chain | Phân biệt exception trong aspect với caller-visible exception |
| `IllegalStateException` qua proxy không bị wrap | Unchecked exception không cần `throws` | Đây là hành vi bình thường |
| Đã khai báo `throws IOException` trên advice nhưng vẫn wrap | Advice signature không thay interface signature | Khai báo checked type trong interface nếu contract cho phép |
| Implementation tự thêm `throws IOException` khi interface không cho phép, build fail | Java override rule không cho broaden checked exceptions | Sửa interface/implementation design, không phải Spring config |
| `@AfterThrowing` không thấy lỗi từ aspect ngoài | Advice đó chưa đi qua pointcut/interceptor hoặc exception sinh ở ngoài vị trí nó quan sát | Kiểm tra advisor chain/order |
| Target không chạy nhưng caller thấy IOException wrapper | `@Around`/`@Before` ném lỗi trước `proceed()` | Kiểm tra code instrumentation, dòng trước proceed |
| Caller `catch(IOException)` không compile cho API không khai báo | Java compiler xét method contract | Bắt wrapper RuntimeException để debug, sửa API |
| Đổi CGLIB và lỗi biến đổi | Kiểu proxy thực đã đổi; class-based proxy có cơ chế intercept khác | Test exception/cause, không che lỗi contract bằng đổi proxy |
| Spring transaction không rollback dù aspect log exception | Checked exception hoặc catch/fallback và order/rules | Kiểm tra transaction advisor vị trí, `rollbackFor` |
| Exception ném nội bộ nhưng after-throwing không chạy | Target đã catch rồi return, hoặc self-invocation không đi qua proxy | Kiểm tra đường gọi/return của target |
| Đổi exception trong `@AfterThrowing` làm mất lỗi gốc | Advice tự throw lỗi mới thay lỗi trước | Preserve original exception/cause, log an toàn |
| JDK proxy không expose method implementation thêm | Interface chưa khai báo method | Thiết kế public service API hoặc dùng class proxy nếu thật sự cần |
| Không thấy proxy type dự đoán | `proxyTargetClass`/Boot/custom infrastructure khác dự kiến | Dùng `AopUtils.isJdkDynamicProxy`, `isCglibProxy` |

## 15. Checklist thiết kế @Aspect xử lý exceptions

- [ ] Xác nhận proxy đang là **JDK dynamic proxy** hay **CGLIB**, không suy đoán từ tên target class.
- [ ] Nếu JDK proxy, kiểm tra `throws` của **interface method mà caller invoke**.
- [ ] Không cố khai báo checked exception rộng hơn ở implementation override.
- [ ] `@Around` mặc định `return pjp.proceed()`, log rồi **rethrow nguyên exception** nếu không có fallback policy.
- [ ] `@Before`/`@AfterThrowing`/`@After` không vô tình ném checked exception mới mà interface không cho phép.
- [ ] Không dùng `throws Throwable` trên advice như cách “mở rộng” interface exception contract.
- [ ] Nếu đã gặp `UndeclaredThrowableException`, tìm underlying checked cause trước khi phân tích business failure.
- [ ] Bảo toàn `cause` khi chủ đích chuyển sang domain unchecked exception.
- [ ] Không log hoặc nuốt `Throwable` rộng một cách nguy hiểm; cân nhắc `Error` và fatal problems.
- [ ] Khi xét `@AfterThrowing`, biết chính xác nó nằm đâu trong advisor chain và quan sát exception nào.
- [ ] Với transaction, đặt rollback rules đúng và kiểm thử trên Spring proxy thật.
- [ ] Có tests normal/checked declared/checked undeclared/unchecked exception.
- [ ] Có tests cho proxy type và interface exposure khi ứng dụng có thể thay đổi AOP config.
- [ ] Không quên self-invocation: `this.method()` không tạo một Spring AOP intercepted invocation mới.
- [ ] Với multi-interface duplicate signatures, kiểm thử checked-exception contract và generated proxy thực tế.

## 16. Kết luận

Trong Spring AOP, exception caller nhìn thấy được quyết định **đồng thời** bởi:

1. **Outcome của target/advice/interceptor chain** — nó ném exception gốc hay trả bình thường?
2. **Proxy type** — dùng JDK dynamic proxy hay class-based CGLIB?
3. **Method contract tại proxy boundary** — với JDK proxy, checked exception có tương thích danh sách `throws` của interface method không?

**`IOException` là checked exception; `IllegalStateException` là unchecked.** Một checked exception phù hợp `throws` của interface có thể truyền trực tiếp qua JDK proxy; một checked exception do Spring advice ném ra nhưng không được interface method cho phép có thể bị bọc thành **`java.lang.reflect.UndeclaredThrowableException`**. Unchecked exception thường truyền trực tiếp.

**`throws Throwable` của `@Around` không thay đổi hợp đồng `throws` của interface.** Vì vậy, đừng tìm cách chữa lỗi bằng việc chỉ sửa advice signature. Thiết kế interface, domain exceptions, proxy configuration và advisor ordering có chủ đích; khi debug, quan sát cả exception trong advice và exception phía caller.

### Tài liệu tham khảo

- [Spring Framework — Proxying Mechanisms](https://docs.spring.io/spring-framework/reference/core/aop/proxying.html): JDK dynamic proxy, CGLIB, lựa chọn proxy và các giới hạn.
- [Spring Framework — AOP Proxies](https://docs.spring.io/spring-framework/reference/core/aop/introduction-proxies.html): mặc định proxy theo interface, class-based proxy.
- [Spring Framework — Declaring Advice](https://docs.spring.io/spring-framework/reference/core/aop/ataspectj/advice.html): `@Around`, `@AfterThrowing`, propagation và binding.
- [Spring Framework — Advice API](https://docs.spring.io/spring-framework/reference/core/aop-api/advice.html): behavior when advice throws checked exception not compatible with signature.
- [Java SE 17 — InvocationHandler](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/InvocationHandler.html): quy tắc `throws` từ handler và `UndeclaredThrowableException`.
- [Java SE 17 — UndeclaredThrowableException](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/UndeclaredThrowableException.html): wrapper RuntimeException cho undeclared checked exception.
- [Spring Framework — Declarative Transaction Rollback](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/rolling-back.html): rollback rules độc lập với quy tắc JDK proxy wrapping.
