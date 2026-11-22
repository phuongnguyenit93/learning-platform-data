# Thiết kế thuộc tính annotation rõ nghĩa và dễ kiểm thử cho Spring Aspect

## 1. Annotation là hợp đồng cấu hình giữa nghiệp vụ và Spring Aspect

Trong Spring AOP, annotation tùy chỉnh giúp người viết service **khai báo ý định** tại phương thức, còn `@Aspect` chịu trách nhiệm thực thi quy tắc liên quan. Ví dụ, `@Audited(operation = Operation.CREATE, tag = "book")` tuyên bố rằng khi phương thức này được gọi **qua Spring proxy**, aspect cần ghi nhận kết quả của thao tác tạo sách.

Annotation chỉ chứa **metadata bất biến**; bản thân nó không tự chặn lời gọi, không tự ghi log và không bảo đảm Spring AOP áp dụng được nếu lời gọi không đi qua proxy. Để annotation dễ hiểu, dễ đổi và dễ kiểm thử, hãy thiết kế đồng thời ba phần:

1. **Hợp đồng công khai:** thuộc tính nào có nghĩa gì, bắt buộc hay tùy chọn, giá trị mặc định là gì.
2. **Cách Spring Aspect diễn giải:** pointcut nào chọn phương thức, advice nào đọc thuộc tính, khi thành công/thất bại làm gì.
3. **Bằng chứng bằng test:** kiểm tra metadata riêng và kiểm tra hành vi đi qua Spring proxy bằng một ứng dụng Spring nhỏ.

Một annotation tốt cần cho người đọc hiểu tác dụng ngay tại nơi sử dụng. Nó không nên buộc người đọc đoán một chuỗi rỗng, một số `0` hay vài cờ boolean mơ hồ sẽ khiến aspect hành xử ra sao.

## 2. Bắt đầu từ các câu hỏi thiết kế

Giả sử nhóm cần ghi nhận thao tác tại service. Bảng sau cho thấy một hợp đồng có thể kiểm chứng được:

| Thuộc tính | Kiểu | Bắt buộc | Ý nghĩa | Cách xác minh |
| --- | --- | --- | --- | --- |
| `operation()` | `Operation` (enum) | Có | Loại thao tác nghiệp vụ được ghi nhận | Kiểm tra enum trong annotation và trong bản ghi của aspect |
| `tag()` | `String` | Không, mặc định `""` | Nhãn ổn định để phân nhóm; rỗng nghĩa là không có nhãn | Kiểm tra cả nhãn có giá trị và giá trị mặc định |
| `logFailures()` | `boolean` | Không, mặc định `true` | Có ghi nhận lần thực thi ném lỗi hay không | Tạo lời gọi lỗi với cả `true` và `false` |

Các nguyên tắc gắn với Spring Aspect:

- **Đặt tên theo ý nghĩa quan sát được.** `logFailures` nói rõ nó điều khiển việc ghi nhận lỗi; `enabled` có thể gây hiểu nhầm là tắt luôn proxy, chặn, bảo mật hay chỉ tắt log.
- **Một thuộc tính, một trách nhiệm.** Không dùng `mode = "CREATE:STRICT:FULL"` rồi tách chuỗi trong advice; enum/thuộc tính riêng mang kiểu và lỗi biên dịch hữu ích hơn.
- **Bắt buộc khi không có mặc định an toàn.** Nếu `operation` quyết định loại sự kiện, để không có `default` buộc nơi sử dụng chọn rõ.
- **Mặc định phải ổn định và được tài liệu hóa.** Thêm `logFailures() default true` mang nghĩa cụ thể; thay mặc định sau này có thể đổi hành vi mọi phương thức không khai báo thuộc tính ấy.
- **Không mặc định ghi tham số nhạy cảm.** Dữ liệu ghi nhận cần được chọn lọc ở aspect; một thuộc tính như `includeArgs = true` dễ vô tình đưa mật khẩu, token hoặc thông tin cá nhân vào log.
- **Dùng `value()` khi thực sự chỉ có một giá trị chính.** Khi có nhiều thuộc tính hoặc cần dễ đọc tại nơi gọi, `operation = ...` rõ nghĩa hơn tên rút gọn. Không tạo cả `value` và `operation` như hai tên đồng nghĩa nếu chưa thiết kế quy tắc alias rõ ràng.

### Hai cách viết và tác động đến người đọc

```java
// Khó hiểu: khó biết 2, true và "x" nghĩa gì ở aspect.
@AuditFlag(level = 2, enabled = true, value = "x")

// Rõ hơn: cấu hình nêu trực tiếp loại thao tác và trường hợp lỗi.
@Audited(operation = Operation.CREATE, tag = "book", logFailures = true)
```

Đây là đoạn minh họa ý tưởng, không phải hai khai báo annotation chạy độc lập. Điều cần tránh là đặt một thuộc tính trông rõ nghĩa nhưng thực tế bị aspect bỏ qua. **Mọi thuộc tính được công bố phải có một hành vi hoặc quy tắc kiểm chứng cụ thể.**

## 3. Khai báo annotation đúng phạm vi Spring AOP

Đối với annotation đánh dấu **phương thức service** để aspect chặn:

```java
@Documented
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.METHOD)
public @interface Audited {
    Operation operation();             // Bắt buộc
    String tag() default "";           // Rỗng: không có nhãn
    boolean logFailures() default true; // Ghi sự kiện thất bại
}
```

- `@Retention(RUNTIME)` cho phép Spring/AspectJ đọc metadata khi chạy. Với `SOURCE` hay `CLASS`, cấu hình pointcut dựa trên annotation tại runtime không thể hoạt động như mong đợi.
- `@Target(METHOD)` thu hẹp lời hứa: aspect chỉ đánh dấu method execution, không áp dụng tùy ý lên class, field hay parameter.
- `@Documented` đưa annotation vào tài liệu Javadoc của phần tử được chú thích; nó không tự tạo advice.
- Enum `Operation` giới hạn giá trị tại lúc biên dịch, tránh lỗi chính tả của các chuỗi `"CREATE"` / `"CRETAE"`.
- Tên `logFailures` mô tả chính xác việc **ghi sự kiện**. Dù `false`, exception của nghiệp vụ **vẫn phải được ném tiếp**; annotation không biến lỗi thành thành công.

**Giới hạn quan trọng:** Spring AOP dựa trên proxy và chủ yếu chặn method execution trên Spring beans. `private`, `final` và self-invocation (`this.someMethod()`) có giới hạn theo kiểu proxy. `@Target(METHOD)` cũng không có nghĩa mọi lời gọi Java vào method được đánh dấu đều bị chặn.

## 4. Ví dụ đầy đủ: annotation, aspect và service

Ví dụ sau dùng **Java 17+, Spring Framework 6.2.8 và JUnit 5**. Nó gồm một annotation có thuộc tính bắt buộc/mặc định, aspect đọc đúng các thuộc tính, một service trả kết quả, một service method ném lỗi và một method không có annotation. Bộ ghi nhận được lưu trong bộ nhớ để test có thể so sánh dữ liệu thực tế thay vì phụ thuộc cách hiển thị console log.

Cấu trúc dự án:

```text
spring-aop-annotation-contract/
├── pom.xml
├── src/main/java/example/AuditAnnotationApp.java
└── src/test/java/example/AuditAnnotationAppTest.java
```

`pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <groupId>example</groupId>
  <artifactId>spring-aop-annotation-contract</artifactId>
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
      <artifactId>spring-aop</artifactId>
      <version>6.2.8</version>
    </dependency>
    <dependency>
      <groupId>org.aspectj</groupId>
      <artifactId>aspectjweaver</artifactId>
      <version>1.9.22</version>
    </dependency>
    <dependency>
      <groupId>org.junit.jupiter</groupId>
      <artifactId>junit-jupiter</artifactId>
      <version>5.11.4</version>
      <scope>test</scope>
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
        <groupId>org.apache.maven.plugins</groupId>
        <artifactId>maven-surefire-plugin</artifactId>
        <version>3.5.2</version>
      </plugin>
      <plugin>
        <groupId>org.codehaus.mojo</groupId>
        <artifactId>exec-maven-plugin</artifactId>
        <version>3.5.0</version>
      </plugin>
    </plugins>
  </build>
</project>
```

`src/main/java/example/AuditAnnotationApp.java`:

```java
package example;

import java.lang.annotation.Documented;
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.util.List;
import java.util.Locale;
import java.util.concurrent.CopyOnWriteArrayList;

import org.aspectj.lang.ProceedingJoinPoint;
import org.aspectj.lang.annotation.Around;
import org.aspectj.lang.annotation.Aspect;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableAspectJAutoProxy;

public class AuditAnnotationApp {
    enum Operation {
        CREATE, FIND
    }

    @Documented
    @Retention(RetentionPolicy.RUNTIME)
    @Target(ElementType.METHOD)
    @interface Audited {
        Operation operation();
        String tag() default "";
        boolean logFailures() default true;
    }

    record AuditEvent(Operation operation, String tag, String outcome) {}

    static class AuditRecorder {
        private final List<AuditEvent> events = new CopyOnWriteArrayList<>();

        void record(AuditEvent event) {
            events.add(event);
        }

        List<AuditEvent> snapshot() {
            return List.copyOf(events);
        }
    }

    static class BookService {
        @Audited(operation = Operation.CREATE, tag = "book")
        public String create(String title) {
            return "book:" + title.toUpperCase(Locale.ROOT);
        }

        @Audited(operation = Operation.FIND, logFailures = false)
        public String find(String id) {
            throw new IllegalArgumentException("not-found:" + id);
        }

        public String plain() {
            return "plain";
        }
    }

    @Aspect
    static class AuditAspect {
        private final AuditRecorder recorder;

        AuditAspect(AuditRecorder recorder) {
            this.recorder = recorder;
        }

        @Around(value = "@annotation(audited)", argNames = "audited")
        public Object around(
                ProceedingJoinPoint joinPoint,
                Audited audited) throws Throwable {

            try {
                Object result = joinPoint.proceed();
                recorder.record(new AuditEvent(
                        audited.operation(), audited.tag(), "SUCCESS"));
                return result;
            } catch (Throwable error) {
                if (audited.logFailures()) {
                    recorder.record(new AuditEvent(
                            audited.operation(), audited.tag(), "FAILURE"));
                }
                throw error; // Giữ nguyên lỗi và hợp đồng của service.
            }
        }
    }

    @Configuration(proxyBeanMethods = false)
    @EnableAspectJAutoProxy(proxyTargetClass = true)
    static class Config {
        @Bean
        BookService bookService() {
            return new BookService();
        }

        @Bean
        AuditRecorder auditRecorder() {
            return new AuditRecorder();
        }

        @Bean
        AuditAspect auditAspect(AuditRecorder recorder) {
            return new AuditAspect(recorder);
        }
    }

    public static void main(String[] args) {
        try (var context =
                new AnnotationConfigApplicationContext(Config.class)) {
            BookService service = context.getBean(BookService.class);

            System.out.println("result=" + service.create("spring"));

            try {
                service.find("404");
            } catch (IllegalArgumentException e) {
                System.out.println("caught=" + e.getMessage());
            }

            System.out.println("plain=" + service.plain());
            System.out.println("events="
                    + context.getBean(AuditRecorder.class).snapshot());
        }
    }
}
```

Chạy ứng dụng:

```bash
mvn -q compile exec:java -Dexec.mainClass=example.AuditAnnotationApp
```

Kết quả stdout của logic ví dụ:

```text
result=book:SPRING
caught=not-found:404
plain=plain
events=[AuditEvent[operation=CREATE, tag=book, outcome=SUCCESS]]
```

Vì `create` mang `@Audited(operation = CREATE, tag = "book")`, aspect ghi một sự kiện thành công với nhãn `book`. Vì `find` đặt `logFailures = false`, phương thức **vẫn ném lỗi**, nhưng recorder không thêm sự kiện thất bại. Vì `plain` không có annotation, pointcut không chọn nó. Bài tập mở rộng đơn giản: bỏ `logFailures = false` ở `find`; mặc định `true` khiến recorder thêm `AuditEvent[operation=FIND, tag=, outcome=FAILURE]` khi method ném lỗi.

Đây là ví dụ ghi sự kiện trong bộ nhớ để kiểm chứng hợp đồng, không phải hệ thống audit production: ghi sự kiện vào kho lưu trữ thực tế cần xử lý độ bền, giao dịch, tải, dữ liệu nhạy cảm và thất bại của chính kênh audit theo yêu cầu nghiệp vụ.

## 5. Hai lớp kiểm thử: metadata và hành vi qua proxy

Một test chỉ dùng reflection có thể chứng minh `operation` hoặc `logFailures` được khai báo đúng; nó **chưa chứng minh Spring Aspect thực sự đọc và áp dụng** những thuộc tính đó. Ngược lại, một integration test chỉ gọi service có thể bỏ sót việc mặc định của annotation bị đổi ngoài ý muốn. Vì vậy cần cả hai.

`src/test/java/example/AuditAnnotationAppTest.java`:

```java
package example;

import java.lang.reflect.Method;
import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

class AuditAnnotationAppTest {

    @Test
    void annotationMetadataHasExplicitAndDefaultValues() throws Exception {
        Method create = AuditAnnotationApp.BookService.class
                .getMethod("create", String.class);
        AuditAnnotationApp.Audited creation =
                create.getAnnotation(AuditAnnotationApp.Audited.class);

        assertNotNull(creation);
        assertEquals(AuditAnnotationApp.Operation.CREATE, creation.operation());
        assertEquals("book", creation.tag());
        assertTrue(creation.logFailures()); // default true

        Method find = AuditAnnotationApp.BookService.class
                .getMethod("find", String.class);
        AuditAnnotationApp.Audited lookup =
                find.getAnnotation(AuditAnnotationApp.Audited.class);

        assertNotNull(lookup);
        assertEquals(AuditAnnotationApp.Operation.FIND, lookup.operation());
        assertEquals("", lookup.tag()); // default empty
        assertFalse(lookup.logFailures());

        Method plain = AuditAnnotationApp.BookService.class.getMethod("plain");
        assertNull(plain.getAnnotation(AuditAnnotationApp.Audited.class));
    }

    @Test
    void springProxyUsesAnnotationPropertiesAndPreservesErrors() {
        try (var context = new AnnotationConfigApplicationContext(
                AuditAnnotationApp.Config.class)) {
            var service = context.getBean(AuditAnnotationApp.BookService.class);
            var recorder = context.getBean(AuditAnnotationApp.AuditRecorder.class);

            assertEquals("book:SPRING", service.create("spring"));

            var failure = assertThrows(IllegalArgumentException.class,
                    () -> service.find("404"));
            assertEquals("not-found:404", failure.getMessage());

            assertEquals("plain", service.plain());

            assertEquals(
                    List.of(new AuditAnnotationApp.AuditEvent(
                            AuditAnnotationApp.Operation.CREATE,
                            "book",
                            "SUCCESS")),
                    recorder.snapshot());
        }
    }
}
```

Lệnh chạy:

```bash
mvn -q test
```

Hai test thể hiện hai lớp cam kết:

| Test | Bảo vệ hành vi nào? |
| --- | --- |
| `annotationMetadataHasExplicitAndDefaultValues` | Thuộc tính `operation` bắt buộc, `tag` mặc định rỗng, `logFailures` mặc định `true`, method không gắn annotation không bị đánh dấu |
| `springProxyUsesAnnotationPropertiesAndPreservesErrors` | Spring proxy chặn phương thức có annotation, aspect đọc thuộc tính, không ghi lỗi khi `logFailures=false`, giữ exception gốc và bỏ qua method thường |

**Test hợp đồng riêng biệt:** muốn xác minh mặc định bằng reflection một cách tường minh hơn, có thể đọc `Audited.class.getMethod("logFailures").getDefaultValue()` và so với `Boolean.TRUE`. Test hiện tại chứng minh mặc định qua metadata được Java cung cấp ở nơi sử dụng.

**Test đường đi proxy:** luôn lấy service bằng `context.getBean(...)`. Việc dùng `new BookService().create(...)` để test hành vi advice sẽ bỏ qua Spring proxy nên chỉ kiểm tra thân phương thức, không kiểm tra AOP.

## 6. Kiểm tra đầu vào và xử lý cấu hình không hợp lệ

Annotation là cấu hình viết tại thời điểm biên dịch, nhưng không phải kiểu dữ liệu nào cũng chặn được mọi giá trị không hợp lệ. Ví dụ `tag = "   "` là chuỗi hợp lệ của Java nhưng có thể không hợp lệ với hệ thống audit. Phải định nghĩa quy tắc một cách rõ ràng:

- Nếu `tag` **thực sự tùy chọn**, chuẩn hóa chuỗi rỗng thành “không gắn nhãn” ở một chỗ. Không diễn giải rỗng vừa là “bỏ qua audit” vừa là “lấy tên phương thức” ở những nhánh khác nhau.
- Nếu `tag` **bắt buộc**, bỏ `default` hoặc kiểm tra `isBlank()`. Đối với metadata cố định, kiểm tra sớm khi khởi tạo bean hoặc khi kiểm tra ứng dụng; không cần để lỗi trôi đến một request ngẫu nhiên.
- Nếu chỉ một tập giá trị hợp lệ, dùng `enum` thay chuỗi. Ví dụ `Operation.CREATE` được compiler kiểm tra; đổi tên enum sẽ bộc lộ các nơi dùng cần sửa.
- Nếu cần chọn đối tượng áp dụng chính sách, dùng thuộc tính nêu rõ phạm vi: `operation`, `resourceType`; tránh giá trị có nhiều nghĩa như `mode = 1`.
- Nếu lỗi cấu hình liên quan đến kiểm soát quyền hoặc bảo mật, thiết kế rõ nguyên tắc **từ chối hay cho qua khi lỗi**; không để aspect tự mặc định cho qua vì một thuộc tính trống.

**Phân biệt hai loại thất bại:** (1) giá trị annotation sai nên application không có cấu hình đáng tin; (2) method nghiệp vụ ném exception khi cấu hình hợp lệ. `logFailures=false` trong ví dụ chỉ điều khiển ghi bản ghi của loại (2), không tắt xác thực cấu hình và không nuốt exception.

### Ràng buộc tốt và không tốt

```java
// Dễ kiểm thử: enum có tập giá trị đóng và bắt buộc.
@Audited(operation = Operation.CREATE, tag = "book")

// Dễ gây tranh cãi: “default” là sự kiện CREATE, READ
// hay “tự suy ra tên method”?
// @Audited(value = "default", options = "true,false,2")
```

Phần thứ hai là phản ví dụ về thiết kế, không phải annotation đã được định nghĩa trong chương trình runnable.

## 7. Annotation trên interface, override và annotation tổng hợp

### Nên đặt annotation ở đâu?

Một hệ thống có interface service và implementation có thể đặt annotation ở một trong hai vị trí. Nhưng proxy JDK và proxy dựa trên lớp nhìn thấy các phương thức khác nhau; reflection bằng `joinPoint.getSignature()` có thể trả phương thức interface thay vì implementation. Cách tránh lỗi:

1. Quy định **vị trí chuẩn** của annotation (ví dụ trên implementation method) cho module.
2. Viết integration test chạy với **kiểu proxy mà ứng dụng thật dùng**.
3. Nếu advice cần tra cứu metadata từ method, dùng `MethodSignature` để lấy method, `AopUtils.getMostSpecificMethod(method, targetClass)` để tìm implementation, và API annotation của Spring phù hợp thay cho đoán rằng `getAnnotation()` ở interface luôn đủ.
4. Đừng coi `@Inherited` là giải pháp cho method override: `@Inherited` chỉ có tác dụng trong quy tắc kế thừa annotation **trên class**, không tự kế thừa annotation từ method cha sang method override.

`@annotation(audited)` trong ví dụ là **pointcut có ràng buộc giá trị annotation**, nên Spring cung cấp một đối tượng `Audited` đã match trực tiếp vào advice. Nếu cần xử lý nhiều nơi khai báo annotation (interface, implementation, meta-annotation), phải thiết kế **cả quy tắc pointcut lẫn quy tắc đọc metadata** đồng bộ.

### Composed annotation và `@AliasFor` không tự áp dụng cho mọi aspect

Spring cung cấp `@AliasFor` và API `MergedAnnotations` / `AnnotatedElementUtils` để hỗ trợ annotation tổng hợp, override và alias ở những thành phần được thiết kế để đọc theo cơ chế merged annotations. Tuy nhiên:

- Chỉ thêm một meta-annotation `@Audited` vào annotation mới **không đảm bảo** pointcut `@annotation(audited)` hiện tại chọn mọi method dùng annotation tổng hợp đó như khi gắn `@Audited` trực tiếp.
- Chỉ khai báo `@AliasFor` **không khiến Java reflection thông thường** (`getAnnotation()`) tự hợp nhất alias. Thành phần đọc phải dùng cơ chế merged annotations tương ứng của Spring.
- Nếu mở rộng `Audited` để làm meta-annotation, `@Target` của nó cần cho phép `ANNOTATION_TYPE` ngoài `METHOD` và thiết kế điểm match tương ứng.
- Với hệ thống có cả annotation trực tiếp và tổng hợp, nên dùng một phương thức giải nghĩa chính sách nhất quán, kiểm thử xung đột/default/alias; chỉ triển khai khi có nhu cầu thật sự.

Các trường hợp này ảnh hưởng **hợp đồng Spring AOP**, không chỉ cú pháp annotation Java. Việc thay `@annotation` bằng một pointcut khác mà không có test hồi quy có thể vô tình mở rộng hoặc thu hẹp phạm vi chặn.

## 8. Thay đổi annotation mà không phá vỡ các service đã sử dụng

Annotation là một API của module. Ví dụ:

```java
// V1
@interface Recorded {
    Operation operation();
}

// V2: thuộc tính mới có default giúp phần lớn source cũ tiếp tục biên dịch.
@interface Recorded {
    Operation operation();
    boolean logFailures() default true;
}
```

Với hai khai báo minh họa này, thêm một thuộc tính **không có mặc định** sẽ buộc cập nhật mọi nơi sử dụng `@Recorded` khi biên dịch lại. Ngay cả thuộc tính có `default`, đổi giá trị mặc định có thể đổi hành vi tất cả method cũ. Khi thay đổi hợp đồng:

- Giữ giá trị mặc định cũ nếu cần tương thích ngược.
- Tránh đổi tên thuộc tính hoặc enum constant vô cớ; những tên này là phần của API mà compiler sử dụng.
- Test cả nơi sử dụng **tường minh** và nơi **dựa vào mặc định**.
- Không biến thuộc tính từng chỉ dùng để log thành điều kiện cho phép thực thi mà không định nghĩa lại hợp đồng, vì đó là thay đổi ý nghĩa lớn.
- Nếu cần chính sách khác biệt thật sự, cân nhắc annotation mới hoặc enum rõ ràng thay cho tích lũy nhiều cờ boolean khó tổ hợp.

## 9. Danh sách kiểm thử nâng cao cho Spring Aspect

| Tình huống | Kết quả cần kiểm chứng |
| --- | --- |
| Có annotation, thuộc tính bắt buộc được khai báo | Advice đọc đúng enum và thực hiện đúng chính sách |
| Không khai báo thuộc tính tùy chọn | Aspect nhận giá trị `default` đúng tài liệu |
| Thuộc tính boolean `false` | Chỉ hành vi được chỉ rõ bị tắt, lỗi nghiệp vụ không bị nuốt |
| Method không có annotation | Không bị aspect tương ứng chặn |
| Lời gọi qua Spring bean/proxy | Advice thực sự được thực thi |
| Lời gọi `this.method()` trong cùng target | Không dựa vào đó để kiểm thử interception mặc định |
| Exception ở method | Advice dọn tài nguyên và ném lại lỗi; ghi hay không ghi theo chính sách |
| Method có overload / implementation trên interface | Chọn đúng phương thức và annotation với kiểu proxy thực tế |
| Annotation tổng hợp, alias, inheritance | Test khả năng match và độ ưu tiên; không tự giả định sẽ hoạt động |
| Nhiều advice cùng match | Thứ tự có thể tác động kết quả; kiểm tra `@Order`/advisor liên quan nếu cần |
| Bất đồng bộ hoặc reactive | Ghi nhận thời điểm trả object hay thời điểm tác vụ hoàn tất phải theo hợp đồng đã xác định |

Nếu annotation dùng để đo latency, định nghĩa rõ đơn vị và phạm vi: `@Around` với method đồng bộ có thể đo thời gian `proceed()`; với `CompletableFuture` hoặc reactive publisher, thời điểm trả future/publisher **không đồng nghĩa** thời điểm nghiệp vụ hoàn tất. Nếu yêu cầu ghi sự kiện khi hoàn tất bất đồng bộ, advice cần xử lý kết quả bất đồng bộ phù hợp, có test riêng.

Nếu annotation kiểm soát truy cập, test cả lời gọi bị từ chối và lỗi khi thu thập policy; không dùng ví dụ ghi audit làm minh chứng rằng một kiểm tra bảo mật đã an toàn. Khi nhiều aspect tương tác với `@Transactional`, `@Async` hoặc Spring Security, thứ tự advice và ranh giới proxy/luồng cần được kiểm tra trực tiếp.

## 10. Cách đánh giá một thiết kế hoàn chỉnh

Một annotation Spring Aspect được coi là rõ nghĩa khi người dùng đọc `@Audited(operation = CREATE, tag = "book")` hiểu ngay mục đích của nó; các mặc định có ý nghĩa cố định; Java compiler hạn chế nhập sai; aspect có một nơi giải nghĩa; lỗi được xử lý đúng hợp đồng; và test chứng minh cả metadata, đường đi proxy, trường hợp không match và tình huống exception.

Thực hành: thêm phương thức `remove(String id)` với `@Audited(operation = DELETE, tag = "book")` sau khi mở rộng enum `Operation`. Viết test kiểm tra có **một** sự kiện `DELETE` khi gọi qua bean và **không** có sự kiện khi gọi method không gắn annotation. Sau đó thêm một tùy chọn mới có `default`, viết test bảo đảm mọi lời gọi cũ giữ nguyên hành vi. Qua đó bạn kiểm tra được việc thiết kế annotation như **hợp đồng ổn định giữa service và Spring Aspect**, thay vì chỉ kiểm tra annotation có mặt bằng reflection.

### Tài liệu Spring chính thức

- Spring AOP và phạm vi proxy: https://docs.spring.io/spring-framework/reference/core/aop.html
- Pointcut `@annotation` và các designator Spring hỗ trợ: https://docs.spring.io/spring-framework/reference/core/aop/ataspectj/pointcuts.html
- Binding annotation và `argNames` trong advice: https://docs.spring.io/spring-framework/reference/core/aop/ataspectj/advice.html
- Proxy và self-invocation: https://docs.spring.io/spring-framework/reference/core/aop/proxying.html
- Spring `@AliasFor` và cách diễn giải annotation tổng hợp: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/core/annotation/AliasFor.html
- `AnnotatedElementUtils`: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/core/annotation/AnnotatedElementUtils.html
