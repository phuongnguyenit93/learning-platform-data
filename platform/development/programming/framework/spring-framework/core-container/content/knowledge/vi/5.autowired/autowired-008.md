# `@Named`, `@Qualifier` và phạm vi hỗ trợ của chuẩn Jakarta

## 1. Ba tên annotation cần phân biệt

Spring Framework 6 hỗ trợ một tập annotation **Jakarta Dependency Injection (JSR-330)** thuộc package `jakarta.inject` bên cạnh các annotation riêng của Spring. Sử dụng các annotation chuẩn có thể làm lớp tiêu thụ ít phụ thuộc API Spring hơn, nhưng không có nghĩa mọi khả năng của Core Container đều thuộc Jakarta DI.

- **`jakarta.inject.Named`**: đặt tên cho component hoặc chỉ rõ ứng viên cần inject bằng tên, chẳng hạn `@Named("upperPort")`.
- **`jakarta.inject.Qualifier`**: **meta-annotation** để định nghĩa qualifier tùy chỉnh (`@Fast`, `@Offline`). Nó không nhận một giá trị String theo cú pháp `@Qualifier("upperPort")`.
- **`org.springframework.beans.factory.annotation.Qualifier`**: annotation **riêng của Spring** dùng trực tiếp ở injection point, có thể nhận chuỗi như `@Qualifier("upperPort")`.

Để hiểu cách chọn đối tượng, còn cần biết `jakarta.inject.Inject` là annotation chỉ điểm injection và `jakarta.inject.Provider<T>` cho lookup theo nhu cầu.

~~~text
                    Spring ApplicationContext
                        |
    +-------------------+------------------+
    |                   |                  |
@Named("upperPort") @Named("lowerPort") @Named("textService")
  UpperPort           LowerPort             TextService
    |                   |                        |
    +------ TextPort ----+              @Inject constructor
                                             |
                             @Named("upperPort") TextPort
                             Provider<RequestToken>
                                             |
                                   gọi process(text)
                                             |
                               Provider.get() lấy token
                               UpperPort.format(text)
~~~

Nếu không có quy tắc chọn rõ, hai bean cùng thực hiện `TextPort` có thể khiến một injection point kiểu `TextPort` bị mơ hồ. `@Named("upperPort")` trên tham số giải quyết lựa chọn **tại chính điểm tiêu thụ**.

## 2. `@Named` trên bean và trên injection point

### Trên class: đặt bean name

~~~java
import jakarta.inject.Named;

@Named("upperPort")
public class UpperPort implements TextPort {
    // Phải triển khai đủ method của TextPort.
}
~~~

Đây là **đoạn minh họa**, chưa runnable vì còn thiếu định nghĩa `TextPort` và method. Trong Spring, class có `@Named` có thể được component scanning nhận diện gần giống `@Component`. Nếu không chỉ định tên trong `@Named`, Spring có thể áp dụng cơ chế tự sinh bean name.

**Quan trọng:** chỉ có annotation trên class **không tự làm class xuất hiện trong mọi container**. Spring phải được cấu hình component scan đúng package, hoặc đăng ký class rõ bằng `context.register(...)`, hoặc có bean definition tương ứng.

### Trên tham số: hạn chế ứng viên

~~~java
import jakarta.inject.Inject;
import jakarta.inject.Named;

@Inject
public TextService(@Named("upperPort") TextPort port) {
    this.port = port;
}
~~~

Đây cũng là snippet minh họa. `@Named("upperPort")` ở đây nói rằng tham số cần bean có kiểu tương thích với `TextPort` và phù hợp tên/qualifier `upperPort`. Nó không tạo thêm instance, cũng không sửa bean khác tên `lowerPort`.

Nếu tên ứng viên thực tế là `primaryUpperPort` nhưng injection lại ghi `upperPort`, Spring có thể báo thiếu dependency. Khi sửa bean name, cần cập nhật nơi yêu cầu tên ấy hoặc thiết kế qualifier trừu tượng hơn.

### `@Named` khác Java class name

`UpperPort` là tên class; `upperPort` là bean name trong container. Một class có thể được đăng ký nhiều bean definitions khác nhau; ngược lại một bean definition có tên riêng không bắt buộc giống tên class. `@Named` dựa vào cấu hình tên/qualifier, không chọn implementation “đầu tiên” theo thứ tự khai báo.

## 3. Jakarta `@Qualifier` là meta-annotation

Một custom qualifier có ý nghĩa nghiệp vụ là `@Fast`. Tạo file `Fast.java`:

~~~java
package demo;

import jakarta.inject.Qualifier;
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Qualifier
@Retention(RetentionPolicy.RUNTIME)
@Target({
    ElementType.TYPE,
    ElementType.FIELD,
    ElementType.PARAMETER,
    ElementType.METHOD
})
public @interface Fast {}
~~~

Đây là **file minh họa định nghĩa annotation**, không phải phần bắt buộc của ứng dụng runnable ở mục 7. `@Qualifier` trong import là `jakarta.inject.Qualifier` và nằm trên **khai báo `Fast`**. Retention runtime giúp container đọc được annotation khi giải quyết dependency.

Có thể dùng:

~~~java
@Fast
@Named("fastPort")
class FastPort implements TextPort {
    // ...
}

@Inject
public SomeService(@Fast TextPort port) {
    this.port = port;
}
~~~

Hai khối **chưa compile độc lập** vì phải khai báo các kiểu, method và đăng ký bean. Khi container hỗ trợ custom qualifier, ứng viên được đánh dấu `@Fast` có thể được chọn cho tham số cùng qualifier.

**Sai:**

~~~java
// Không hợp lệ với jakarta.inject.Qualifier:
// @jakarta.inject.Qualifier("fastPort")
~~~

Annotation Jakarta `Qualifier` không có thuộc tính `value()` kiểu String. Nếu muốn chọn theo tên String, dùng `@Named("fastPort")`. Nếu muốn custom qualifier, tạo annotation riêng có `@Qualifier` làm meta-annotation.

## 4. Spring `@Qualifier` khác Jakarta `@Qualifier`

Ví dụ dùng annotation riêng của Spring:

~~~java
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;

@Autowired
public SomeService(@Qualifier("upperPort") TextPort port) {
    this.port = port;
}
~~~

Đây là đoạn minh họa. Trong file này, `@Qualifier("upperPort")` là **Spring Qualifier**, không phải Jakarta. Hai annotation có cùng simple name, vì thế nếu cần cả hai trong cùng source Java, phải dùng **tên đầy đủ** cho ít nhất một cái để tránh import collision.

| Ý định | Jakarta DI | Spring |
| --- | --- | --- |
| Chọn ứng viên tên `upperPort` | `@Named("upperPort")` | `@Qualifier("upperPort")` |
| Định nghĩa marker `@Fast` | Meta `@jakarta.inject.Qualifier` | Meta `@org.springframework.beans.factory.annotation.Qualifier` |
| Cấp dependency | `@Inject` | `@Autowired` |
| Bean name / stereotype | `@Named` | `@Component` và các stereotype liên quan |

**Tính đúng của qualifier phụ thuộc cách bean được đăng ký.** Không nên mặc định `@Primary` sẽ bỏ qua một yêu cầu qualifier cụ thể hoặc một `@Named` không khớp tên sẽ được sửa tự động. Lựa chọn nhiều ứng viên cần cấu hình nhất quán và test.

## 5. `@Inject` thay `@Autowired` đến mức nào?

`@Inject` có thể được Spring xử lý trên constructor, field và method injection points:

~~~java
import jakarta.inject.Inject;

@Inject
public void setInventory(InventoryPort inventory) {
    this.inventory = inventory;
}
~~~

Snippet cần `InventoryPort` và field nếu muốn biên dịch. Khi bean do Spring quản lý, container tìm bean phù hợp và áp dụng injection tại thời điểm cấu hình.

| Tính năng | `@Autowired` của Spring | `@Inject` Jakarta |
| --- | --- | --- |
| Constructor injection | Có | Có |
| Field injection | Có | Có |
| Method injection | Có | Có |
| `required=false` trên annotation | Có | **Không có** |
| `Optional<T>` tại injection point trong Spring | Có | Có nhờ Spring tích hợp |
| `new` ngoài container có được autowire tự động? | Không | Không |

Sai cú pháp:

~~~java
// Không được hỗ trợ:
// @Inject(required = false)
~~~

`jakarta.inject.Inject` không định nghĩa thuộc tính `required`. Nếu dependency là tùy chọn trong Spring, một giải pháp là:

~~~java
@Inject
public void setMetrics(java.util.Optional<MetricsPort> metrics) {
    this.metrics = metrics;
}
~~~

Đây chỉ là minh họa. Spring có thể truyền `Optional.empty()` nếu không có ứng viên thích hợp. Khả năng Spring xử lý `Optional<T>` **không đồng nghĩa tất cả DI containers đều phải có semantics giống hệt**.

Khi bean class chỉ có một constructor, Spring Framework hiện đại thường có thể chọn constructor đó ngay cả khi không ghi `@Autowired` hoặc `@Inject`, miễn bean đã được đăng ký và dependency được resolve đúng. Tuy nhiên `@Inject` có thể làm mục đích DI rõ hơn.

## 6. `Provider<T>` và scope của bean đích

`jakarta.inject.Provider<T>` là một API chuẩn để trì hoãn việc **yêu cầu một bean đích** cho đến khi `get()` được gọi.

~~~java
private final Provider<RequestToken> tokens;

@Inject
public TextService(Provider<RequestToken> tokens) {
    this.tokens = tokens;
}

public RequestToken nextToken() {
    return tokens.get();
}
~~~

Ví dụ chỉ minh họa, chưa đủ field/import/class nếu tách riêng. Trong Spring:

- Provider cho **singleton** thường trả cùng instance ở nhiều lần `get()`.
- Provider cho **prototype** có thể trả một instance mới mỗi lần `get()`.
- Provider đích không có bean, nhiều bean mơ hồ hoặc bean creation lỗi có thể gây exception **lúc gọi `get()`**.
- Spring `ObjectProvider<T>` cung cấp thêm các API như `getIfAvailable()`, `stream()`, không có đầy đủ trong Jakarta `Provider<T>`.

**Provider không thay scope.** Nó chỉ thay cách/thời điểm yêu cầu dependency. Vì vậy ví dụ runnable sẽ chủ động gắn Spring `@Scope("prototype")` vào bean `RequestToken`.

### `@Singleton` và default scope

Jakarta `@Singleton` mô tả một scope chuẩn, nhưng **trong Spring** các bean được đăng ký qua `@Named` vẫn theo mặc định **singleton theo bean definition trong mỗi container** nếu không cấu hình khác. Đây không phải global singleton duy nhất cho toàn JVM. Không suy từ quy tắc default của một DI runtime khác rằng Spring `@Named` mặc định prototype.

Spring muốn scope prototype thì dùng `@Scope("prototype")` hoặc bean definition metadata. `jakarta.inject.Scope` là **meta-annotation** dùng tạo custom scope annotation; nó không tự gán một bean vào scope request/prototype.

## 7. Chương trình Java 17 / Spring Framework 6.2 chạy hoàn chỉnh

Ví dụ có hai implementations của một interface `TextPort`, dùng `@Named` để định danh và inject đúng một implementation. `TextService` còn nhận `Provider<RequestToken>` để kiểm tra đối tượng prototype mới cho mỗi lần xử lý. Không dùng Spring Boot, server hoặc database.

### 7.1. Cấu trúc và `pom.xml`

Cần JDK 17+, Maven:

~~~text
jakarta-named-demo/
├── pom.xml
└── src/main/java/demo/JakartaNamedDemo.java
~~~

`pom.xml`:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>edu.example</groupId>
    <artifactId>jakarta-named-demo</artifactId>
    <version>1.0-SNAPSHOT</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.0</version>
        </dependency>
        <dependency>
            <groupId>jakarta.inject</groupId>
            <artifactId>jakarta.inject-api</artifactId>
            <version>2.0.0</version>
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
                <version>3.5.0</version>
                <configuration>
                    <mainClass>demo.JakartaNamedDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

### 7.2. Source `JakartaNamedDemo.java`

~~~java
package demo;

import jakarta.inject.Inject;
import jakarta.inject.Named;
import jakarta.inject.Provider;

import java.util.Locale;
import java.util.Objects;
import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Scope;

public final class JakartaNamedDemo {
    private JakartaNamedDemo() {}

    public interface TextPort {
        String format(String input);
    }

    @Named("upperPort")
    public static final class UpperPort implements TextPort {
        @Override
        public String format(String input) {
            return input.toUpperCase(Locale.ROOT);
        }
    }

    @Named("lowerPort")
    public static final class LowerPort implements TextPort {
        @Override
        public String format(String input) {
            return input.toLowerCase(Locale.ROOT);
        }
    }

    public record RequestToken(int number) {}

    @Named("textService")
    public static final class TextService {
        private final TextPort port;
        private final Provider<RequestToken> tokens;

        @Inject
        public TextService(@Named("upperPort") TextPort port,
                           Provider<RequestToken> tokens) {
            this.port = Objects.requireNonNull(port);
            this.tokens = Objects.requireNonNull(tokens);
        }

        public String process(String input) {
            RequestToken token = tokens.get();
            return token.number() + ":" + port.format(input);
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class AppConfig {
        private final AtomicInteger counter = new AtomicInteger();

        @Bean
        @Scope("prototype")
        public RequestToken requestToken() {
            return new RequestToken(counter.incrementAndGet());
        }
    }

    public static void main(String[] args) {
        try (AnnotationConfigApplicationContext context =
                     new AnnotationConfigApplicationContext()) {

            // Đăng ký tường minh: không cần @ComponentScan.
            context.register(AppConfig.class,
                    UpperPort.class, LowerPort.class, TextService.class);
            context.refresh();

            TextService service = context.getBean(TextService.class);
            System.out.println("PORT_COUNT "
                    + context.getBeanNamesForType(TextPort.class).length);
            System.out.println("FIRST " + service.process("Hello"));
            System.out.println("SECOND " + service.process("Java"));
            System.out.println("LOWER "
                    + context.getBean("lowerPort", TextPort.class)
                             .format("SpRiNg"));
            System.out.println("SAME "
                    + (service == context.getBean(TextService.class)));
        }
    }
}
~~~

Nested classes ở đây là `public static` nên có thể được đăng ký tường minh bằng `register(...)`. `@Named("upperPort")` và `@Named("lowerPort")` giúp Spring đặt tên hai bean; `@Inject` trên constructor yêu cầu ứng viên `upperPort`. `AppConfig` tạo token prototype bằng annotation scope riêng của Spring.

### 7.3. Chạy và stdout

Tại thư mục `jakarta-named-demo`:

~~~bash
mvn -version
mvn -q compile exec:java
~~~

`javac/java` trực tiếp sẽ cần classpath có các Spring và Jakarta dependency jars. Vì vậy dùng Maven để giải quyết dependency và chạy ứng dụng là cách chính xác, đơn giản hơn trong ví dụ này; `maven.compiler.release=17` yêu cầu biên dịch tương thích Java 17.

**Dòng stdout do chương trình in:**

~~~text
PORT_COUNT 2
FIRST 1:HELLO
SECOND 2:JAVA
LOWER spring
SAME true
~~~

Maven và JVM có thể in thông tin/log khác; khối trên chỉ là các dòng do `System.out.println` chủ động tạo.

### 7.4. Vì sao có output đó?

1. `context.register` đăng ký `AppConfig` và ba class, sau đó `refresh` xử lý bean definitions.
2. `getBeanNamesForType(TextPort.class).length` bằng **2** vì hai bean khác nhau cùng interface.
3. `TextService` nhận `upperPort` nhờ qualifier `@Named("upperPort")` ở tham số, không bị mơ hồ với `lowerPort`.
4. `process("Hello")` yêu cầu token qua `Provider.get()`. Bean `RequestToken` là prototype; lần đầu nhận ID 1, UpperPort trả `HELLO`.
5. Lần thứ hai provider yêu cầu token mới ID 2, UpperPort trả `JAVA`.
6. `getBean("lowerPort", TextPort.class)` chọn implementation còn lại, chuyển `SpRiNg` thành `spring`.
7. `TextService` theo scope singleton mặc định trong Spring, nên hai lần lookup trả cùng reference và in `SAME true`.

**Provider không bắt buộc luôn tạo mới**; chính `@Scope("prototype")` làm factory tạo một `RequestToken` mới mỗi lần được yêu cầu.

## 8. Chuẩn Jakarta hỗ trợ tới đâu và thiếu những gì?

| Tính năng Spring | Jakarta DI tương ứng | Ghi chú |
| --- | --- | --- |
| `@Autowired` | `@Inject` | Không có thuộc tính `required` |
| `@Component` | `@Named` | Không có mô hình composed stereotypes đầy đủ như Spring |
| `@Qualifier("beanName")` | `@Named("beanName")` | `jakarta.inject.Qualifier` chỉ là meta-annotation |
| Qualifier annotation tự định nghĩa | `@jakarta.inject.Qualifier` | Cần custom annotation với retention, targets phù hợp |
| `@Scope("singleton")` | `@Singleton` | Spring giữ default singleton khi dùng `@Named` |
| `@Scope("prototype")` | Không có tương đương trực tiếp cho Spring prototype | Thường dùng Spring `@Scope` |
| `@Lazy` | Không có annotation tương đương trực tiếp | Spring `@Lazy` hoặc provider |
| `@Value` | Không có annotation tương đương trực tiếp | Spring property configuration |
| `ObjectFactory<T>` | `Provider<T>` | Jakarta cung cấp `get()`; Spring có mở rộng |
| `@Profile`/`@Conditional` | Không thuộc `jakarta.inject` | Cần Spring configuration |

`@Named` không tự biến service thành HTTP-scoped hay kích hoạt AOP, transaction, retry. Đây là các tính năng không được bảo đảm bởi Jakarta DI API.

### `jakarta.inject` khác `jakarta.annotation`

`@Inject`, `@Named`, `@Qualifier`, `@Singleton`, `Provider<T>` thuộc Jakarta DI/JSR-330. `@PostConstruct`, `@PreDestroy` và `@Resource` thuộc Jakarta Annotations/JSR-250; **không** đi kèm trong `jakarta.inject-api`. Khi cần chúng phải có dependency tương ứng, như `jakarta.annotation-api`.

### Spring 6 và `javax.inject` cũ

Các tutorial Spring đời cũ có thể import `javax.inject.*`. Ví dụ cho Spring Framework 6 nên dùng `jakarta.inject.*` cùng artifact thích hợp. Không thay thế import máy móc khi chưa kiểm tra phiên bản Spring và dependencies hiện có.

### `@Value` hay `@Lazy` không có trong `jakarta.inject`

Ví dụ Spring-specific:

~~~java
// Chỉ minh họa Spring, không phải API Jakarta DI.
@org.springframework.beans.factory.annotation.Value("${app.title:Demo}")
private String title;
~~~

Để giữ domain ít phụ thuộc Spring, có thể đọc configuration ở composition root rồi truyền value qua constructor, hoặc inject một config object đã được validate. `Provider<T>` là công cụ lazy lookup, **không thay** cơ chế placeholder property.

## 9. Sử dụng custom qualifier có ý nghĩa nghiệp vụ

Nếu hệ thống có nhiều adapter theo vai trò và tên bean dễ đổi, custom qualifier giúp thể hiện ý nghĩa `@Offline` hay `@Preferred`. Chẳng hạn:

~~~java
package demo;

import jakarta.inject.Qualifier;
import java.lang.annotation.*;

@Qualifier
@Retention(RetentionPolicy.RUNTIME)
@Target({ElementType.TYPE, ElementType.PARAMETER})
public @interface Offline {}
~~~

Đây là file `Offline.java` minh họa, không phải file chạy của mục 7. Gắn `@Offline` trên bean candidate và ở injection point, đồng thời bảo đảm bean registration và type phù hợp. Spring hỗ trợ qualifier metadata do Jakarta meta-annotation đánh dấu.

Không nên định nghĩa hàng chục marker qualifiers nếu chỉ khác tên một bean đơn giản. Ngược lại, dùng tên chuỗi `@Named("adapter23")` rải khắp domain có thể làm business code gắn cứng với registry; cân nhắc qualifier biểu đạt vai trò hoặc lựa chọn implementation tại configuration.

## 10. Lỗi điển hình và cách chẩn đoán

| Vấn đề | Cách xử lý |
| --- | --- |
| Import `jakarta.inject.Inject` bị lỗi compiler | Thêm đúng `jakarta.inject-api` vào dependency/classpath |
| Bean `@Named` không tồn tại | Xác minh scan đúng package hoặc register class |
| `@Named("upperPort")` không chọn được bean | Kiểm tra tên bean thực tế và type/qualifier |
| Hai bean cùng interface gây ambiguity | Chỉ định qualifier hoặc strategy rõ |
| `@jakarta.inject.Qualifier("upperPort")` không compile | Jakarta `Qualifier` không nhận String; dùng `@Named` |
| Import hai `Qualifier` cùng simple name | Dùng fully-qualified annotation cho một loại |
| `@Inject(required=false)` không compile | Jakarta Inject không có `required` |
| `Provider.get()` trả cùng instance | Scope đích singleton |
| `Provider.get()` ném exception | Candidate vắng mặt, mơ hồ hoặc bean creation lỗi |
| `@Named` bị hiểu là prototype | Spring default singleton; dùng `@Scope` nếu cần |
| `@Value` được tìm trong `jakarta.inject` | Không có; dùng Spring property injection/config |
| `javax.inject` cũ không hoạt động như dự kiến | Kiểm tra migration Jakarta trên Spring 6 |
| Dùng `new` rồi trông đợi annotation tự inject | Phải để Spring quản lý/cấu hình instance |
| Dùng custom qualifier nhưng vẫn lựa sai | Kiểm tra meta annotation, runtime retention, target, candidate registration |
| Nghĩ bean singleton mặc định thread-safe | Scope không cung cấp đồng bộ tự động |

Quy trình chẩn đoán: kiểm tra dependency Jakarta → bean registration → tên/loại candidate → injection qualifier → scope/provider → nguyên nhân gốc trong bean creation exception. Đừng chữa lỗi bằng cách đánh dấu mọi bean `@Primary`.

## 11. Bài tập có đáp án

**1.** `@jakarta.inject.Qualifier("upperPort")` có hợp lệ không?

**Đáp án:** Không. `jakarta.inject.Qualifier` là meta-annotation; dùng `@Named("upperPort")` hoặc custom qualifier như `@Fast`.

**2.** `@Named("upperPort")` trên class và ở tham số có khác nhau không?

**Đáp án:** Trên class định danh component ứng viên, trên tham số giới hạn bean cần nhận theo tên/qualifier.

**3.** Nếu có `upperPort` và `lowerPort` cùng `TextPort`, Spring tự chọn cái khai báo trước?

**Đáp án:** Không được dựa vào thứ tự khai báo; nếu không phân giải được có thể lỗi mơ hồ. Dùng qualifier.

**4.** `@Inject(required=false)` có hợp lệ không?

**Đáp án:** Không. Jakarta `@Inject` không có thuộc tính required. Trong Spring có thể dùng `Optional<T>` hoặc phương án optional DI khác.

**5.** Bean `@Named` mặc định scope gì trong Spring?

**Đáp án:** Singleton theo bean definition/context, không phải global singleton toàn JVM.

**6.** Vì sao hai lần `Provider.get()` trong demo có số 1 và 2?

**Đáp án:** Bean đích `RequestToken` được đặt `@Scope("prototype")`; mỗi lần yêu cầu Spring chạy factory method và tăng counter.

**7.** Nếu đổi `RequestToken` sang singleton, provider có vẫn luôn tạo token mới?

**Đáp án:** Không. Provider thực hiện lookup, còn scope quyết định instance được cấp.

**8.** `jakarta.annotation.PostConstruct` có trong `jakarta.inject-api` không?

**Đáp án:** Không. Đó là API Jakarta Annotations riêng (JSR-250), khác `jakarta.inject`.

**9.** Tại sao custom `@Offline` cần `@Retention(RUNTIME)`?

**Đáp án:** Metadata qualifier cần hiện diện khi container thực hiện resolution. Nếu không giữ annotation ở runtime, cơ chế đọc metadata có thể không nhận biết được.

**10.** `@Named` có thay thế đầy đủ `@Value`, `@Lazy`, `@Scope` không?

**Đáp án:** Không. Nó chỉ hỗ trợ naming/qualifier/stereotype đơn giản, không định nghĩa các chức năng Spring kia.

**11.** Lớp được gắn `@Named` nhưng không scan/register, `getBean(Class)` có thành công không?

**Đáp án:** Không thể trông chờ. Context phải có bean definition đã đăng ký tương ứng.

## 12. Checklist áp dụng

- [ ] Spring Framework 6.x, Java 17+ và `jakarta.inject-api` được khai báo khi dùng Jakarta DI annotations.
- [ ] Phân biệt `jakarta.inject.Named`, `jakarta.inject.Qualifier` và Spring `Qualifier`.
- [ ] Bean có tên/qualifier được đăng ký trong đúng context.
- [ ] Injection point có type và tên/qualifier khớp ứng viên.
- [ ] Không viết `@jakarta.inject.Qualifier("...")` hoặc `@Inject(required=false)`.
- [ ] Khi cần custom qualifier, định nghĩa annotation với meta qualifier, retention runtime và targets phù hợp.
- [ ] Dùng `Provider.get()` khi thật sự cần lookup theo nhu cầu, hiểu scope bean đích.
- [ ] Không hiểu provider đồng nghĩa prototype.
- [ ] Không mặc định mọi Jakarta implementation có chính xác default singleton của Spring.
- [ ] Không coi Jakarta DI có `@Value`, `@Lazy` hoặc Spring profiles/conditions.
- [ ] Phân biệt `jakarta.inject` JSR-330 và `jakarta.annotation` JSR-250.
- [ ] Khi migrate, kiểm tra `javax.inject` vs `jakarta.inject` và dependency thực tế.
- [ ] Test các ứng viên cùng type, trường hợp thiếu bean và resolution theo tên.
- [ ] Không dựa vào thứ tự scan/định nghĩa để chọn dependency.
- [ ] Tách business logic khỏi bean lookup tùy tiện, không biến annotation thành nơi giấu quy tắc nghiệp vụ.

### Nguồn tham khảo Spring

- [Using JSR 330 Standard Annotations — Spring 6.2](https://docs.spring.io/spring-framework/reference/6.2/core/beans/standard-annotations.html)
- [Autowiring with Qualifiers](https://docs.spring.io/spring-framework/reference/core/beans/annotation-config/autowired-qualifiers.html)
- [Bean Scopes](https://docs.spring.io/spring-framework/reference/core/beans/factory-scopes.html)

**Kết luận:** `@Named` của Jakarta dùng để **định danh ứng viên hoặc chọn theo tên**. `jakarta.inject.Qualifier` chỉ là meta-annotation tạo qualifier tùy chỉnh, không phải cú pháp chuỗi `@Qualifier("...")` của Spring. `@Inject` và `Provider<T>` kết hợp tốt với Spring Core Container nhưng không thay thế toàn bộ `@Autowired(required=false)`, `@Value`, `@Lazy` hoặc `@Scope`. Hiểu đúng API, phạm vi và nơi đăng ký bean giúp dependency injection rõ ràng, ít nhầm import và dễ kiểm thử.