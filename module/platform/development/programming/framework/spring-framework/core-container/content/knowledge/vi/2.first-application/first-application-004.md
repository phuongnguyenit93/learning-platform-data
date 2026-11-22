# Khởi tạo `AnnotationConfigApplicationContext` trong Spring Framework

## 1. Mục tiêu và ý nghĩa của context

`AnnotationConfigApplicationContext` là một **implementation của `ApplicationContext`** trong `spring-context`, dùng để khởi động Spring IoC container từ cấu hình annotation/Java, không cần file XML. Nó nhận những class cấu hình `@Configuration`, các class thành phần (`@Component`, `@Service`...) hoặc danh sách package cần component scan, sau đó đăng ký **bean definitions**, tạo/wire những bean phù hợp và cung cấp API `getBean(...)`.

Trong bài này, chúng ta học chính xác **lúc nào context được khởi tạo, lúc nào cần `refresh()`, cách lấy bean và cách đóng context**. Đây là một chương trình **Spring Framework thuần**, không dùng `SpringApplication.run(...)`, Spring Boot hay web server.

Kết quả mong muốn:
- Khởi tạo context với `new AnnotationConfigApplicationContext(AppConfig.class)`.
- Hiểu cách làm tương đương bằng `new AnnotationConfigApplicationContext()`, sau đó `register(AppConfig.class)` và `refresh()`.
- Biết khi nào sử dụng `scan("demo.components")`, và vì sao chỉ gắn `@Component` chưa làm bean tự xuất hiện.
- Tra `getBean(Class<T>)`, `containsBean(...)`, kiểm tra singleton và đóng container bằng `try-with-resources`.
- Chẩn đoán lỗi quên `refresh()`, quét nhầm package, trùng bean theo type, thiếu dependency và gọi `refresh()` sai vòng đời.

Điều kiện thực hành: **JDK 17+**, **Maven 3.9+**, truy cập Maven Central/mirror để tải dependency lần đầu. Ví dụ chọn Spring Framework **7.0.9**; Spring 7.0 giữ baseline Java 17. Phiên bản này là mốc tái hiện bài học, không phải yêu cầu dùng cố định trong sản phẩm lâu dài.

## 2. `AnnotationConfigApplicationContext` đứng ở đâu?

Các lớp/giao diện liên quan:

| Loại | Vai trò |
| --- | --- |
| `BeanFactory` | API cơ bản để truy cập bean do container quản lý |
| `ApplicationContext` | Mở rộng khả năng bean factory bằng sự kiện, resource, message source... |
| `ConfigurableApplicationContext` | Hợp đồng cấu hình/quản lý lifecycle của context (gồm `refresh()`, `close()`) |
| `AnnotationConfigApplicationContext` | Implementation thực tế đọc cấu hình annotation, hỗ trợ `register`, `scan`, `registerBean` |

Package cần import khi viết code:

~~~java
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
~~~

Ba dòng trên là **đoạn import minh họa**, được dùng trong chương trình hoàn chỉnh ở mục 5. Chúng không phải một chương trình Java độc lập.

`@Bean` khai báo một **factory method** trả về object được Spring quản lý. `@Configuration` đánh dấu class làm nguồn configuration. `ApplicationContext` là container sử dụng metadata đó để tạo, gắn dependency và quản lý bean; nó **không** tự tạo mọi object Java trên classpath.

Phân biệt:
- `new AnnotationConfigApplicationContext(...)` tạo **container/context**, không phải một service nghiệp vụ.
- `context.getBean(GreetingService.class)` lấy **bean của service** đã được đăng ký và tạo theo scope.
- `new GreetingService(...)` tự tạo Java object bên ngoài Spring; không tự tham gia lifecycle/DI của container.
- `@Component` trên class chỉ thành bean khi class được **đăng ký/scan** qua context phù hợp.

## 3. Ba cách khởi tạo: chỗ nào tự `refresh()`?

| Cách dùng | Context tự `refresh()`? | Khi phù hợp |
| --- | --- | --- |
| `new AnnotationConfigApplicationContext(AppConfig.class)` | **Có** | Có sẵn một hoặc nhiều class cấu hình, muốn mở nhanh |
| `new AnnotationConfigApplicationContext("demo.components")` | **Có** | Biết rõ package để quét, muốn quét ngay khi tạo |
| `new AnnotationConfigApplicationContext()` rồi `register(...)` | **Không**: bạn phải gọi `refresh()` | Muốn kết hợp nhiều nguồn cấu hình hoặc chuẩn bị context trước bootstrap |
| `new AnnotationConfigApplicationContext()` rồi `scan(...)` | **Không**: bạn phải gọi `refresh()` | Muốn chủ động chọn package scan trước bootstrap |

Ví dụ **tóm tắt cú pháp**, sử dụng `AppConfig` được khai báo ở mục 5:

~~~java
// Cách nhanh: constructor nhận class tự refresh trước khi trả về.
try (var ctx = new AnnotationConfigApplicationContext(AppConfig.class)) {
    var service = ctx.getBean(GreetingService.class);
}

// Cách từng bước: bắt buộc tự refresh.
try (var ctx = new AnnotationConfigApplicationContext()) {
    ctx.register(AppConfig.class);
    ctx.refresh();
    var service = ctx.getBean(GreetingService.class);
}
~~~

Khối trên minh họa **đặt trong một phương thức có đúng import/type tương ứng**. Ở phần demo hoàn chỉnh, nó được triển khai thành class Java có thể biên dịch.

Một constructor `new AnnotationConfigApplicationContext(AppConfig.class, MoreConfig.class)` cũng có thể nhận nhiều class. `register(...)` tương tự có thể được gọi nhiều lần **trước khi** `refresh()`. Sau khi bootstrap xong, hãy làm việc với context đang active thay vì cố coi context này là loại refresh lại vô hạn.

**Quan trọng:** `AnnotationConfigApplicationContext` kế thừa `GenericApplicationContext`, có semantics **refresh một lần** cho một context. Đừng gọi `refresh()` lần hai sau khi constructor nhận cấu hình đã tự refresh hoặc sau lần refresh thủ công. Muốn xây lại container từ nguồn mới, thông thường tạo context mới.

## 4. Bên trong bước `refresh()`

Mô hình đơn giản hóa:

~~~text
Tạo context rỗng / truyền cấu hình lúc constructor
                     |
        Đăng ký config class hoặc scan
                     |
      Xác định bean-definition metadata
                     |
                refresh()
                     |
     Chạy các bước hậu xử lý metadata
                     |
       Resolve dependency và scope
                     |
       Khởi tạo bean singleton không lazy
                     |
          Gắn dependency / init hooks
                     |
             Context sẵn sàng
                     |
        getBean(...) / gọi nghiệp vụ
                     |
       close() / destruction callbacks
~~~

`refresh()` không chỉ là “đổi một cờ ready”: đây là **bước bootstrap** cấu hình bean factory, xử lý các định nghĩa cấu hình, đăng ký post-processors, tạo singleton không lazy, phát sự kiện lifecycle và hoàn tất các bước cần thiết để sử dụng context. Các scope và lazy configuration có thể làm một số instance **chưa được tạo ngay** lúc refresh; definition có thể tồn tại trước instance.

Lời gọi `register(AppConfig.class)` chỉ chỉ định **nguồn cấu hình**; các `@Bean` methods chưa nhất thiết được xử lý và bean chưa sẵn sàng để lấy khi chưa refresh.

Với constructor nhận `AppConfig.class`, quá trình `register` và `refresh` diễn ra bên trong constructor **trước khi nó trả về**. Vì vậy, sau dòng `new AnnotationConfigApplicationContext(AppConfig.class)`, việc gọi `getBean` ngay là hợp lệ nếu bootstrap thành công.

**Không đồng nhất thời điểm `refresh()` với thời điểm tạo mọi object.** Bean `@Lazy` và prototype có quy tắc riêng; `getBean` có thể tạo prototype mới, còn singleton mặc định được chia sẻ.

## 5. Dự án Maven Java 17 chạy độc lập: constructor so với `register + refresh`

### 5.1. Cấu trúc

~~~text
context-bootstrap-demo/
├── pom.xml
└── src/main/java/
    └── demo/
        ├── ContextBootstrapDemo.java
        ├── ScanBootstrapDemo.java
        └── components/
            └── ScanGreeting.java
~~~

Đây là **một dự án Maven**, có hai main class. Bạn có thể chạy lần lượt, không cần đổi POM hay thêm Spring Boot. `ScanGreeting` phục vụ cách scan ở mục 6.

### 5.2. `pom.xml`

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>context-bootstrap-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>7.0.9</version>
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
            </plugin>
        </plugins>
    </build>
</project>
~~~

`spring-context` có thể kéo theo những Spring artifacts nền như `spring-core`, `spring-beans` và `spring-expression` theo metadata Maven. Bạn không phải tự thêm `spring-boot-starter`. Maven Compiler Plugin dùng `--release 17` theo property đã khai báo. Exec Maven Plugin thực thi main class được chỉ định bằng `-Dexec.mainClass`.

### 5.3. `src/main/java/demo/ContextBootstrapDemo.java`

~~~java
package demo;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

public final class ContextBootstrapDemo {

    private ContextBootstrapDemo() {
    }

    interface Greeter {
        String greet(String name);
    }

    static final class DefaultGreeter implements Greeter {
        @Override
        public String greet(String name) {
            return "Hello, " + name + "!";
        }
    }

    static final class GreetingService {
        private final Greeter greeter;

        GreetingService(Greeter greeter) {
            this.greeter = greeter;
        }

        String greet(String name) {
            return greeter.greet(name);
        }
    }

    @Configuration(proxyBeanMethods = false)
    static class AppConfig {
        @Bean
        Greeter greeter() {
            return new DefaultGreeter();
        }

        @Bean
        GreetingService greetingService(Greeter greeter) {
            return new GreetingService(greeter);
        }
    }

    private static void inspect(
            String label, AnnotationConfigApplicationContext ctx) {
        GreetingService service = ctx.getBean(GreetingService.class);

        System.out.println(label + ".message=" + service.greet("An"));
        System.out.println(label + ".singleton="
                + (service == ctx.getBean(GreetingService.class)));
        System.out.println(label + ".active=" + ctx.isActive());
    }

    public static void main(String[] args) {
        // Cách 1: constructor nhận config class tự refresh.
        try (var direct =
                     new AnnotationConfigApplicationContext(AppConfig.class)) {
            inspect("direct", direct);
        }

        // Cách 2: tạo context, register, rồi refresh một lần.
        try (var manual = new AnnotationConfigApplicationContext()) {
            manual.register(AppConfig.class);
            manual.refresh();
            inspect("manual", manual);
        }
    }
}
~~~

**Diễn giải code:**

- `AppConfig` được đăng ký như một nguồn cấu hình. Hai factory methods `@Bean` tạo `Greeter` và `GreetingService`.
- `greetingService(Greeter greeter)` nhận phụ thuộc từ container; nó không gọi trực tiếp `greeter()`, phù hợp với `proxyBeanMethods=false`.
- Trong `inspect`, `getBean(GreetingService.class)` lấy bean từ context tương ứng. Vì scope mặc định là singleton, **hai lần lấy trong cùng context** trả cùng reference.
- `direct` và `manual` là **hai context độc lập**, không có nghĩa chúng chia sẻ singleton. Việc mỗi context tạo một bean graph riêng là đúng.
- `isActive()` cho biết context đang active khi gọi `inspect`; `close()` xảy ra sau các lệnh in vì `try-with-resources` tự quản lý tài nguyên.

### 5.4. Build, chạy và expected stdout

Từ thư mục chứa `pom.xml`, kiểm tra:

~~~bash
java -version
javac -version
mvn -version
~~~

Chạy main class thứ nhất; dấu nháy quanh `-Dexec.mainClass=...` dùng được trên Bash và PowerShell:

~~~bash
mvn -q clean compile exec:java "-Dexec.mainClass=demo.ContextBootstrapDemo"
~~~

**Sáu dòng stdout từ chính chương trình** (không tính output của `java -version`/`mvn -version`, log build hoặc logging backend):

~~~text
direct.message=Hello, An!
direct.singleton=true
direct.active=true
manual.message=Hello, An!
manual.singleton=true
manual.active=true
~~~

Không có cổng HTTP được mở. Chương trình kết thúc sau khi hai context lần lượt được đóng. Các log cấu hình Spring có thể xuất hiện tùy môi trường, nhưng không nằm trong sáu dòng do `System.out.println` tạo ra.

Nếu `javac` báo không tìm thấy `org.springframework.context.annotation`, bạn có thể đã compile thủ công không kèm classpath. Hãy chạy từ thư mục đúng, qua Maven để các dependency transitive được resolve.

## 6. Dự án trên, cách thứ ba: component scan

Với component scan, không nhất thiết phải biết trước từng class cụ thể, nhưng bạn **phải chỉ định đúng package** và class cần scan phải có metadata thích hợp (ví dụ `@Component`).

### 6.1. `src/main/java/demo/components/ScanGreeting.java`

~~~java
package demo.components;

import org.springframework.stereotype.Component;

@Component
public class ScanGreeting {
    public String message() {
        return "scanned bean ready";
    }
}
~~~

### 6.2. `src/main/java/demo/ScanBootstrapDemo.java`

~~~java
package demo;

import demo.components.ScanGreeting;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

public final class ScanBootstrapDemo {
    private ScanBootstrapDemo() {
    }

    public static void main(String[] args) {
        try (var context = new AnnotationConfigApplicationContext()) {
            context.scan("demo.components");
            context.refresh();

            ScanGreeting greeting = context.getBean(ScanGreeting.class);
            System.out.println("scan.message=" + greeting.message());
            System.out.println("scan.name="
                    + context.containsBean("scanGreeting"));
            System.out.println("scan.active=" + context.isActive());
        }
    }
}
~~~

`scan("demo.components")` tìm kiếm candidate components trong package được yêu cầu và các package con; nó không tự quét toàn bộ classpath. Class `ScanGreeting` có `@Component`, nên sẽ được đăng ký trong context. Tên mặc định của bean theo component scan ở đây là `scanGreeting` (với cách tạo tên mặc định của Spring).

Chạy lần thứ hai bằng cùng POM:

~~~bash
mvn -q compile exec:java "-Dexec.mainClass=demo.ScanBootstrapDemo"
~~~

**Ba dòng stdout của chương trình thứ hai:**

~~~text
scan.message=scanned bean ready
scan.name=true
scan.active=true
~~~

Dùng constructor có package cũng được: `new AnnotationConfigApplicationContext("demo.components")` sẽ **scan và refresh tự động**. Khi cần điều chỉnh nhiều package hoặc phối hợp `register` và `scan`, tạo context rỗng rồi gọi `refresh()` một lần thường dễ đọc hơn.

**Giới hạn:** `@Component` chỉ có hiệu lực khi class được đăng ký hoặc tìm thấy bởi scan của context hiện hành. Nếu dùng `scan("demo.unrelated")` thay cho package thực tế, `getBean(ScanGreeting.class)` sẽ không tìm được bean. Không phải lỗi cú pháp Java; đó là lỗi cấu hình bean graph.

## 7. Lifecycle: đóng context và xử lý sự cố lúc bootstrap

`AnnotationConfigApplicationContext` hỗ trợ `AutoCloseable` qua hợp đồng context, nên `try-with-resources` giúp gọi `close()` khi thoát khối, kể cả khi phát sinh exception trong phần sử dụng.

~~~java
// Đoạn minh họa đặt trong một phương thức với AppConfig và import phù hợp.
try (var context = new AnnotationConfigApplicationContext(AppConfig.class)) {
    // Use beans here.
} // close() được gọi tự động.
~~~

Đây là đoạn minh họa **không độc lập**; chương trình hoàn chỉnh đã có ở mục 5.

**Đóng context không có nghĩa Java GC ngay lập tức xóa tất cả object.** Spring thực hiện destruction callbacks cho các bean được quản lý phù hợp (đặc biệt singleton); reference Java còn được giữ ở nơi khác vẫn tuân theo quy tắc lifetime/GC thông thường. Prototype có quy tắc destruction khác: container thường không tự quản lý đầy đủ bước hủy sau khi cấp instance.

Một context có thể **khởi động thất bại** nếu:
- Class cấu hình không hợp lệ hoặc factory method ném exception.
- Thiếu bean cần thiết cho constructor/`@Bean` factory method parameter.
- Có nhiều bean candidates cho một dependency type nhưng không có cách phân giải phù hợp.
- Constructor dependencies tạo vòng không thể giải quyết.
- Component scan không tìm thấy thành phần mà ứng dụng kỳ vọng.

Khi gặp lỗi trong constructor đã refresh (chẳng hạn `new AnnotationConfigApplicationContext(AppConfig.class)`), constructor có thể **ném exception trước khi gán biến context**. Đừng dựa vào việc lấy context từ constructor không hoàn tất để gọi `close()`; xử lý exception startup, xem nguyên nhân gốc trong log/stack trace và bảo đảm tài nguyên ngoài container được cleanup thích hợp.

## 8. Những cách sử dụng đúng và sai

| Tình huống | Đúng/sai | Lý do |
| --- | --- | --- |
| `new AnnotationConfigApplicationContext(AppConfig.class)` rồi `getBean` | Đúng | Constructor tự register + refresh |
| `new AnnotationConfigApplicationContext()`, `register(...)`, `refresh()` | Đúng | Tự hoàn tất bootstrap trước lookup |
| `new AnnotationConfigApplicationContext()`, `scan(...)`, `refresh()` | Đúng | Quét package rồi bootstrap |
| Tạo context rỗng, `register(...)` rồi lấy bean **ngay** | Sai | Chưa refresh |
| Constructor nhận class rồi gọi thêm `refresh()` | Sai | Context loại này không phải context refresh nhiều lần |
| `@Component` ở package không được scan và không đăng ký | Không đủ | Không tạo bean từ annotation đứng một mình |
| Gọi `getBean(SomeType.class)` khi chưa có bean | Lỗi lúc chạy | Thường là `NoSuchBeanDefinitionException` |
| Gọi theo type khi có nhiều candidates ngang nhau | Có thể lỗi | Thường là `NoUniqueBeanDefinitionException` |
| Tạo nhiều context, suy ra singleton được chia sẻ toàn JVM | Sai | Singleton thông thường tính theo bean definition/context |
| Không đóng context console dùng tài nguyên | Không nên | Có thể bỏ lỡ lifecycle callbacks và cleanup |

`refresh()` là điểm ranh giới quan trọng giữa **khai báo nguồn cấu hình** và **container đã khởi động**. Một số `BeanDefinition` có thể đăng ký sớm, nhưng dựa vào `getBean` trước refresh là cách sử dụng không đúng của một `ApplicationContext` chưa active.

Với một dự án web/Boot, cơ chế bootstrap và shutdown thường gắn với `SpringApplication`/server. Bài này tập trung hoàn toàn vào cách khởi tạo `AnnotationConfigApplicationContext` **thủ công**.

## 9. Sửa lỗi thường gặp khi chạy mẫu

| Hiện tượng | Nguồn gốc có thể | Cách xác minh/sửa |
| --- | --- | --- |
| `package org.springframework.context... does not exist` | Thiếu `spring-context` trên compile classpath | Kiểm POM, chạy Maven đúng thư mục, reload IDE |
| `NoSuchBeanDefinitionException` với `GreetingService` | Quên register đúng `AppConfig` hoặc chưa xử lý cấu hình | Kiểm danh sách source và gọi `refresh()` |
| `NoSuchBeanDefinitionException` với `ScanGreeting` | Quét sai package / thiếu `@Component` | Xác minh `demo.components`, tên package và annotation |
| `IllegalStateException` về chưa refresh | Tạo context rỗng rồi lookup ngay | Gọi `register`/`scan` trước và `refresh` đúng một lần |
| Exception khi refresh lần thứ hai | Đã refresh qua constructor hoặc trước đó | Không gọi lần hai; tạo context mới nếu cần đổi bootstrap |
| `NoUniqueBeanDefinitionException` | Nhiều beans phù hợp một type | Dùng `@Primary`, `@Qualifier` hoặc lookup theo bean name |
| `BeanCreationException` | Lỗi tạo bean hoặc dependency | Xem `Caused by`, constructor và factory methods |
| Java runtime thấp hơn bản build | JDK/target runtime không đồng bộ | Kiểm `java -version`, `mvn -version`, compile release |
| Maven không tải được `spring-context` | Version/repository/proxy/mirror/offline | Kiểm GAV, Maven Central và cấu hình mạng |
| Chỉ thấy output demo rồi process thoát | Console context đã đóng | Đây là hành vi đúng của demo, không nhất thiết lỗi |

**Ghi nhớ:** một lỗi `getBean` có thể là lỗi **metadata/configuration** chứ không phải lỗi “thiếu JAR”; ngược lại, lỗi `ClassNotFoundException`/compile-time package thường thuộc dependency/classpath. Phân tầng vấn đề trước khi chỉnh code.

### Công cụ hỗ trợ quan sát

- Dùng `context.containsBean("greetingService")` để hỏi bean name có được nhận biết trong context không.
- Dùng `context.getBeanDefinitionCount()` hoặc `getBeanDefinitionNames()` khi debug registration, nhưng **không ghi cứng số lượng toàn context**: Spring có thể đăng ký thêm các bean nội bộ.
- Dùng `context.getBean(GreetingService.class)` để kiểm tra kiểu cụ thể; tránh lạm dụng kiểu này bên trong mọi service vì gây service locator anti-pattern.
- Dùng logger/cause chain khi startup thất bại; đừng phụ thuộc chính xác vào chuỗi exception message vì có thể đổi theo patch.

## 10. Bài tập thực hành độc lập

Hãy làm **từng bài một**, khôi phục source gốc giữa các bài để so với stdout mục 5/6:

1. **Đổi cách bootstrap:** thay constructor `new AnnotationConfigApplicationContext(AppConfig.class)` bằng 3 dòng no-arg/`register`/`refresh`; dự đoán ba dòng `direct.*` có đổi không nếu giữ nhãn tương ứng.
2. **Bỏ `refresh()`** ở nhánh `manual`: quan sát exception khi lấy bean. Giải thích vì sao `register` không đồng nghĩa với đã khởi động context.
3. **Gọi `refresh()` hai lần** trên nhánh no-arg: thử trên bản sao, quan sát lỗi và giải thích vì sao phải dựng context mới để khởi động lại loại context này.
4. **Sai package scan:** đổi sang `demo.missing`; dự đoán `ScanGreeting` có trở thành bean không.
5. **Đổi tên bean:** đặt `@Component("welcomeComponent")` cho `ScanGreeting`, rồi sửa `containsBean(...)`; so sánh lookup theo tên và theo type.
6. **Thêm bean thứ hai cùng kiểu `Greeter`:** dự đoán ambiguous dependency ở `greetingService(Greeter)`; phân giải bằng `@Primary` hoặc `@Qualifier`.
7. **Tách config file:** chuyển `AppConfig` sang `demo.config.AppConfig` public và truyền `AppConfig.class` vào constructor; quan sát output giữ nguyên.
8. **Thêm lifecycle callback:** tạo bean có `@Bean(destroyMethod = "close")` và method `close()` in thông điệp; kiểm tra nó được gọi khi thoát try-with-resources (phân biệt với stdout chuẩn của demo gốc).
9. **So sánh singleton giữa contexts:** lấy một bean từ mỗi context rồi in `==`; giải thích vì sao cùng bean class chưa có nghĩa cùng object cho hai context.
10. **Đổi `@Lazy` hoặc `@Scope("prototype")`:** dự đoán thời điểm tạo và kết quả so reference; hiểu khác biệt với câu hỏi “context đã refresh chưa?”.

### Checklist tự đánh giá

- [ ] Phân biệt class `AnnotationConfigApplicationContext` với bean nghiệp vụ.
- [ ] Biết **hai constructor** tự `refresh` (nhận config classes/nhận package strings).
- [ ] Biết **no-arg** cần `register` hoặc `scan` rồi `refresh()`.
- [ ] Biết `@Configuration`, `@Bean`, `@Component` được đưa vào container thế nào.
- [ ] Chạy được hai main class trong cùng dự án Maven, dự đoán chính xác 6+3 dòng stdout.
- [ ] Không gọi `refresh()` lần hai trên `AnnotationConfigApplicationContext`.
- [ ] Biết đóng context và phân biệt Spring lifecycle với Java garbage collection.

## 11. Tóm tắt và tài liệu chính thức

- **Cách nhanh:** `new AnnotationConfigApplicationContext(AppConfig.class)` — config được đăng ký và context tự refresh.
- **Cách chủ động:** `new AnnotationConfigApplicationContext()` → `register(AppConfig.class)` → `refresh()`.
- **Cách quét:** `new AnnotationConfigApplicationContext()` → `scan("demo.components")` → `refresh()`.
- `getBean(...)` yêu cầu context đã bootstrap thành công; scope/lazy quyết định khi nào các instance được tạo.
- `try-with-resources` đóng context và kích hoạt lifecycle callbacks phù hợp.
- **Không có Spring Boot hay HTTP server** trong các ví dụ; tất cả đều dùng Core Container của Spring Framework.

Tài liệu tra cứu:

- [Spring Framework – Instantiating the Spring Container](https://docs.spring.io/spring-framework/reference/core/beans/java/instantiating-container.html)
- [Spring Framework – Java-based Container Configuration](https://docs.spring.io/spring-framework/reference/core/beans/java.html)
- [Spring Framework – Using @Bean](https://docs.spring.io/spring-framework/reference/core/beans/java/bean-annotation.html)
- [Spring Framework – Annotation-based Container Configuration](https://docs.spring.io/spring-framework/reference/core/beans/annotation-config.html)
- [Spring Framework – Bean Scopes](https://docs.spring.io/spring-framework/reference/core/beans/factory-scopes.html)
- [Spring Framework 7.0 Release Notes](https://github.com/spring-projects/spring-framework/wiki/Spring-Framework-7.0-Release-Notes)

**Kết luận:** Khi tự mở một `AnnotationConfigApplicationContext`, hãy biết chắc **nguồn cấu hình đã được đăng ký hay quét chưa**, **context đã `refresh()` hay chưa**, và **ai chịu trách nhiệm đóng nó**. Nắm ba bước ấy giúp bạn xây và debug ứng dụng IoC/DI đầu tiên mà không nhầm cách khởi tạo với cách lấy bean.