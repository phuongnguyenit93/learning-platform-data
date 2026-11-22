# Khai báo cấu hình tối thiểu bằng @Configuration và @Bean trong Spring Framework

## 1. Kết quả học tập

Ứng dụng Spring Framework đầu tiên có thể chỉ cần **JDK 17+, dependency `spring-context`, một lớp `@Configuration`, vài factory method `@Bean` và một phương thức `main`**. Không cần Spring Boot, XML, server HTTP hoặc cơ sở dữ liệu để quan sát container quản lý bean.

Kết thúc bài này, bạn có thể:

- Tạo project Maven với `spring-context` và biên dịch Java 17.
- Giải thích `@Configuration` đăng ký nguồn cấu hình; `@Bean` mô tả factory method cung cấp object bean cho container.
- Khai báo hai bean hợp tác với nhau, inject dependency qua tham số của phương thức `@Bean`, không để lớp nghiệp vụ gọi container.
- Khởi tạo `AnnotationConfigApplicationContext`, xác nhận tên bean, lấy bean theo kiểu, kiểm tra wiring và scope mặc định.
- Phân biệt gọi phương thức Java thông thường với Spring gọi factory method, nhất là với `proxyBeanMethods=false`.
- Đóng context an toàn và đối chiếu lệnh chạy/đầu ra Java 17 chính xác.
- Chẩn đoán thiếu bean, nhiều ứng viên, tên bean sai, cấu hình không được nạp, classpath thiếu và cách đăng ký trùng.

Phạm vi bài là **JavaConfig tối thiểu**. Những cơ chế component scanning, property injection, custom scope và Spring Boot auto-configuration chỉ nhắc tới khi giúp bạn không nhầm khái niệm.

## 2. Trước Spring: lớp sử dụng và lớp cung cấp dependency

Giả sử chương trình cần chào người dùng. Ta có một hợp đồng `GreetingTemplate` và service dùng hợp đồng đó:

~~~java
interface GreetingTemplate {
    String render(String name);
}

final class VietnameseTemplate implements GreetingTemplate {
    @Override
    public String render(String name) {
        return "Xin chao, " + name + "!";
    }
}

final class GreetingService {
    private final GreetingTemplate template;

    GreetingService(GreetingTemplate template) {
        this.template = java.util.Objects.requireNonNull(template);
    }

    String greet(String name) {
        return template.render(name.strip());
    }
}
~~~

Đây là **đoạn code minh họa**, chưa phải file chạy độc lập (thiếu lớp `main`). Nếu tự lắp ghép bằng Java thuần:

~~~java
GreetingTemplate template = new VietnameseTemplate();
GreetingService service = new GreetingService(template);
System.out.println(service.greet(" Lan ")); // Xin chao, Lan!
~~~

Đó đã là **constructor dependency injection**: service nhận collaborator được chọn từ bên ngoài, thay vì tự gọi `new VietnameseTemplate()` trong class nghiệp vụ. Spring giúp **lắp ghép đối tượng theo bean definitions**, không tạo ra một ngôn ngữ Java mới và cũng không cấm `new`: bên trong một factory method `@Bean`, `new` là cách tự nhiên để cung cấp object.

Một lớp service biết `GreetingTemplate`, không cần biết `ApplicationContext` hay Maven. Nếu đổi sang `EnglishTemplate` trong cấu hình, mã service không phải đổi miễn hợp đồng vẫn được đáp ứng.

## 3. Cấu hình tối thiểu gồm những gì?

Một cấu hình Java ngắn:

~~~java
@Configuration(proxyBeanMethods = false)
class AppConfig {
    @Bean
    GreetingTemplate greetingTemplate() {
        return new VietnameseTemplate();
    }

    @Bean
    GreetingService greetingService(GreetingTemplate template) {
        return new GreetingService(template);
    }
}
~~~

Đây là **minh họa**, thiếu import và các định nghĩa lớp liên quan. Ví dụ hoàn chỉnh ở mục 5.

| Cú pháp | Nghĩa trong bài này |
| --- | --- |
| `@Configuration` | Lớp chứa cấu hình để Spring xử lý thành bean definitions |
| `@Bean` | Factory method tạo/trả về object bean được container quản lý |
| `greetingTemplate()` | Tên bean mặc định thường là `greetingTemplate` |
| `greetingService(GreetingTemplate template)` | Tham số factory method chỉ ra dependency cần resolve |
| `new GreetingService(template)` | Constructor được gọi bởi factory method để lắp ghép dependency |
| `proxyBeanMethods=false` | Không intercept các lời gọi Java trực tiếp giữa các factory methods `@Bean` |

**Điều quan trọng:** factory method `greetingService(...)` không tự gọi `greetingTemplate()`. Spring thấy tham số cần một `GreetingTemplate` rồi cung cấp bean phù hợp. Từ đó service nhận đúng object do container quản lý.

~~~mermaid
flowchart LR
    C["ApplicationContext"] --> R["Bean: greetingTemplate"]
    C --> S["Bean: greetingService"]
    S -->|"constructor dependency"| R
~~~

Hướng cạnh `greetingService → greetingTemplate` nghĩa là **service phụ thuộc template**, không phải service phải giữ reference tới context. Bean có thể được tạo theo thứ tự bảo đảm dependency cần thiết, không phải theo vị trí method trên file.

### Bean definition khác bean instance

- **Bean definition**: metadata mà container lưu về tên, factory method, kiểu/scope có thể xác định, cách tạo và các thiết lập liên quan.
- **Bean instance**: đối tượng thực tế do factory method cung cấp/được container quản lý. Nó không tự xuất hiện chỉ vì source có annotation; lớp cấu hình phải **được đăng ký và xử lý**.
- **Dependency injection**: cung cấp collaborator vào constructor, tham số factory hoặc điểm injection được hỗ trợ.
- **Scope mặc định**: `singleton` theo **một bean definition trong một context**, không phải một instance toàn JVM.

Với context thông thường, singleton **không lazy** được tạo trong giai đoạn refresh; bean lazy/prototype có quy tắc thời điểm khởi tạo khác. Không được kết luận mọi bean đã tạo tức thì ngay khi registry nhận metadata.

## 4. Tạo dự án Maven bằng Java 17

Dùng **Spring Framework 7.0.9** cùng mốc với phần chuẩn bị dependency; đây là **phiên bản được ghim để tái lập**, không phải khẳng định phiên bản mới nhất. Cần JDK 17 trở lên và Maven. Không cần Spring Boot.

Cấu trúc thư mục:

~~~text
minimal-spring-config/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── demo/
                └── MinimalConfigDemo.java
~~~

File package `demo` nằm ở thư mục `src/main/java/demo/`. Java yêu cầu tên tệp khớp public top-level class `MinimalConfigDemo`.

### 4.1. pom.xml

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>minimal-spring-config</artifactId>
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
                <version>3.14.1</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.1</version>
                <configuration>
                    <mainClass>demo.MinimalConfigDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Module `spring-context` dùng các dependency transitively từ các Spring modules liên quan. Maven tải chúng tự động; đừng tự chép một JAR rời rồi cho rằng classpath đã đầy đủ. Khi offline, Maven chỉ chạy nếu các artifacts cần thiết có sẵn trong cache.

### 4.2. File Java hoàn chỉnh

Tạo `src/main/java/demo/MinimalConfigDemo.java`:

~~~java
package demo;

import java.util.Objects;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

public final class MinimalConfigDemo {
    private MinimalConfigDemo() {}

    public interface GreetingTemplate {
        String render(String name);
    }

    public static final class VietnameseTemplate
            implements GreetingTemplate {
        @Override
        public String render(String name) {
            return "Xin chao, " + name + "!";
        }
    }

    public static final class GreetingService {
        private final GreetingTemplate template;

        public GreetingService(GreetingTemplate template) {
            this.template = Objects.requireNonNull(
                    template, "template must not be null");
        }

        public String greet(String rawName) {
            if (rawName == null || rawName.isBlank()) {
                throw new IllegalArgumentException("name must not be blank");
            }
            return template.render(rawName.strip());
        }

        public GreetingTemplate template() {
            return template;
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class AppConfig {
        @Bean
        public GreetingTemplate greetingTemplate() {
            return new VietnameseTemplate();
        }

        @Bean
        public GreetingService greetingService(
                GreetingTemplate template) {
            return new GreetingService(template);
        }
    }

    public static void main(String[] args) {
        AnnotationConfigApplicationContext context =
                new AnnotationConfigApplicationContext(AppConfig.class);

        try (context) {
            boolean definitions =
                    context.containsBeanDefinition("greetingTemplate")
                    && context.containsBeanDefinition("greetingService");

            GreetingTemplate template =
                    context.getBean(GreetingTemplate.class);
            GreetingService service =
                    context.getBean(GreetingService.class);

            System.out.println("definitions=" + definitions);
            System.out.println("injectedSame=" +
                    (service.template() == template));
            System.out.println("serviceSingleton=" +
                    (service == context.getBean(GreetingService.class)));
            System.out.println("greeting=" +
                    service.greet(" Lan "));
        }

        System.out.println("contextActiveAfterClose=" + context.isActive());
    }
}
~~~

**Tính runnable:** chỉ có một public top-level class `MinimalConfigDemo`; các type khác nằm bên trong. `AppConfig` được khai báo là nested class `public static` nên Spring có thể sử dụng làm configuration class. `greetingService(GreetingTemplate)` yêu cầu một collaborator và context có đúng một bean phù hợp.

**Về `try (context)`:** Java 17 cho phép sử dụng biến local effectively final làm tài nguyên, và Spring `AnnotationConfigApplicationContext` có thể đóng qua `close()`. Sau khối, `context.isActive()` trả `false`; không tiếp tục lấy/dùng bean bằng một context đã đóng.

### 4.3. Lệnh chạy bằng Maven và expected output

Trong thư mục `minimal-spring-config`:

~~~bash
java -version
javac -version
mvn -version
mvn -q clean compile exec:java
~~~

**Năm dòng stdout do phương thức `main` của ứng dụng in khi thành công:**

~~~text
definitions=true
injectedSame=true
serviceSingleton=true
greeting=Xin chao, Lan!
contextActiveAfterClose=false
~~~

Ý nghĩa:

- `definitions=true`: context đã đăng ký **hai bean names của ứng dụng**. Không suy ra tổng số bean definitions trong context chỉ bằng hai (có thể có infrastructure definitions).
- `injectedSame=true`: reference template mà service giữ chính là bean `GreetingTemplate` context cung cấp.
- `serviceSingleton=true`: lấy bean `GreetingService` hai lần trong cùng context vẫn là cùng instance theo default singleton.
- `greeting=...`: hành vi từ method của service/template Java thông thường, không phải annotation tự động tạo câu chào.
- `contextActiveAfterClose=false`: context không còn active sau khi đóng.

Kết quả lệnh `java -version`, `javac -version`, `mvn -version` và bất kỳ log phụ Maven nào không nằm trong năm dòng stdout ứng dụng. Các phép kiểm tra reference `==` được dùng có chủ đích để chứng minh **identity của singleton ở cấu hình này**, không phải quy tắc cho mọi scope hoặc mọi proxy.

### 4.4. Tự biên dịch bằng javac / chạy bằng java

Mã dùng Spring nên cần các JAR liên quan trong classpath. Tạo danh sách classpath từ Maven:

~~~bash
mvn -q dependency:build-classpath -Dmdep.outputFile=classpath.txt
~~~

Linux/macOS (bash hoặc zsh):

~~~bash
mkdir -p out
javac --release 17 -encoding UTF-8 \
  -cp "$(cat classpath.txt)" \
  -d out src/main/java/demo/MinimalConfigDemo.java
java -cp "out:$(cat classpath.txt)" demo.MinimalConfigDemo
~~~

Windows PowerShell:

~~~powershell
$deps = (Get-Content -Raw classpath.txt).Trim()
New-Item -ItemType Directory -Force out | Out-Null
javac --release 17 -encoding UTF-8 -cp "$deps" -d out src/main/java/demo/MinimalConfigDemo.java
java -cp "out;$deps" demo.MinimalConfigDemo
~~~

Trong classpath, Unix phân tách entry bằng dấu `:`, Windows bằng dấu `;`. Lệnh `javac --release 17` biên dịch với Java 17 API/language target; launcher chạy class `demo.MinimalConfigDemo`. Nếu gặp `package org.springframework... does not exist`, nguyên nhân đầu tiên cần kiểm tra là **classpath/dependency**, không phải “Spring không inject được”.

## 5. Spring đã làm gì ở thời điểm startup?

Container nhận `AppConfig.class` khi khởi tạo:

~~~java
new AnnotationConfigApplicationContext(AppConfig.class)
~~~

Đây là đoạn rút ra từ file demo, dùng khi tạo context. Về logic:

1. Spring xử lý `@Configuration`, đăng ký các bean definitions được khai báo bằng `@Bean` (cùng những infrastructure definitions cần thiết).
2. Khi cần tạo singleton `greetingTemplate`, factory method trả `VietnameseTemplate`.
3. Khi cần tạo singleton `greetingService`, Spring thấy factory method yêu cầu `GreetingTemplate`, resolve bean tương ứng và truyền nó vào.
4. Factory method xây dựng `GreetingService(template)`. Service giữ reference đó trong trường `final`.
5. Ứng dụng lấy service qua `context.getBean(GreetingService.class)` và gọi `greet(" Lan ")`.
6. Khi đóng context, Spring thực hiện các callback hủy/đóng phù hợp của các managed singleton. Trong demo không có tài nguyên I/O do service/template giữ.

~~~mermaid
sequenceDiagram
    participant Main as main
    participant Context as SpringContext
    participant Config as AppConfig
    participant Template as GreetingTemplate
    participant Service as GreetingService
    Main->>Context: new Context(AppConfig.class)
    Context->>Config: process @Configuration / @Bean
    Context->>Config: greetingTemplate()
    Config-->>Context: VietnameseTemplate
    Context->>Config: greetingService(template)
    Config-->>Context: GreetingService
    Main->>Context: getBean(GreetingService.class)
    Context-->>Main: singleton service
    Main->>Service: greet(" Lan ")
    Service->>Template: render("Lan")
    Template-->>Service: "Xin chao, Lan!"
    Main->>Context: close()
~~~

Đây là **mô hình minh họa luồng phụ thuộc**, không phải quy định logger hoặc mọi bean có chung thứ tự như thế. Thứ tự hai bean ở đây có quan hệ dependency: service cần template. Hai bean độc lập không có thứ tự khởi tạo tổng quát cố định dựa vào tên method.

**BeanFactory vs ApplicationContext:** `BeanFactory` là giao diện nền tảng truy xuất bean; `ApplicationContext` mở rộng nó bằng lifecycle, message resources, application events và những tiện ích khác. Ứng dụng thực tế thường chọn `ApplicationContext`. Spring không yêu cầu service phụ thuộc trực tiếp vào `ApplicationContext`; service chỉ cần `GreetingTemplate`.

## 6. @Configuration mặc định và proxyBeanMethods=false

Có thể thấy hai cách khai báo:

~~~java
@Configuration
class DefaultConfig {
    @Bean
    GreetingTemplate greetingTemplate() {
        return new VietnameseTemplate();
    }

    @Bean
    GreetingService greetingService() {
        return new GreetingService(greetingTemplate());
    }
}
~~~

Đây là **mã minh họa không độc lập**. `@Configuration` mặc định có `proxyBeanMethods=true`: Spring tăng cường/intercept các lời gọi thích hợp giữa `@Bean` methods trong cấu hình được quản lý, để giữ bean semantics như singleton.

Trong demo runnable, ta dùng:

~~~java
@Configuration(proxyBeanMethods = false)
class AppConfig {
    @Bean
    GreetingTemplate greetingTemplate() {
        return new VietnameseTemplate();
    }

    @Bean
    GreetingService greetingService(GreetingTemplate template) {
        return new GreetingService(template);
    }
}
~~~

Ở chế độ `proxyBeanMethods=false`, lời gọi **trực tiếp** từ một factory method đến method `@Bean` khác là lời gọi Java bình thường, **không được intercept** để trả bean scoped tương ứng. Ví dụ:

~~~java
@Bean
GreetingService wrongStyle() {
    return new GreetingService(greetingTemplate());
}
~~~

Nếu cấu hình áp dụng chế độ `false`, `greetingTemplate()` ở đây tự chạy như method Java và có thể tạo một object khác với bean `greetingTemplate` trong context. Điều đó phá kỳ vọng collaborator được chia sẻ, nhất là khi template có trạng thái/tài nguyên.

**Lựa chọn dễ hiểu cho người mới:** truyền dependency qua tham số factory method, như `greetingService(GreetingTemplate template)`; Spring tự resolve bean. Cách này làm mối quan hệ phụ thuộc rõ ràng và không cần gọi trực tiếp factory method khác. Không chọn `proxyBeanMethods=false` mù quáng nếu configuration của bạn phụ thuộc vào inter-bean method calls.

## 7. Tên bean, kiểu, scope và các biến thể

Mặc định `@Bean` dùng tên method:

~~~java
@Bean
GreetingService greetingService(GreetingTemplate template) { ... }
~~~

Đây là **mẫu chữ ký**, không phải Java source có thể compile nguyên văn vì có dấu `...`. Trong code thực tế, thân method phải trả về object phù hợp.

Có thể đặt tên khác:

~~~java
@Bean("greetingServicePrimary")
GreetingService buildGreetingService(GreetingTemplate template) {
    return new GreetingService(template);
}
~~~

Lúc đó `getBean("greetingServicePrimary")` tra bằng tên mới; không nên nhầm tên **Java method**, tên **bean definition** và kiểu **GreetingService**. Chỉ dùng phương thức có tên/đăng ký đúng trong một cấu hình cụ thể, tránh copy thêm snippet vào demo rồi trùng đăng ký.

Một số API tra cứu:

~~~java
GreetingService s1 = context.getBean(GreetingService.class);
Object s2 = context.getBean("greetingService");
boolean exists = context.containsBeanDefinition("greetingService");
~~~

Đây là **snippet** giả sử có biến context hợp lệ; type lookup cần giải quyết ứng viên. Khi chỉ có một `GreetingService` trong demo, `getBean(GreetingService.class)` thành công.

### Scope không đồng nghĩa static

- `singleton` là scope mặc định: một bean instance cho một bean definition trong một context, trừ các cơ chế/proxy đặc biệt làm cần hiểu thêm identity.
- `prototype` có thể tạo instance mới khi có yêu cầu phù hợp. Nếu inject prototype vào singleton bằng cách thông thường, dependency được resolve khi singleton được khởi tạo, không tự đổi prototype ở mọi method call.
- `@Lazy` có thể hoãn khởi tạo khi chưa cần; không xóa dependency logic.
- Scope theo request/session cần môi trường web tương ứng; project Java thuần ở đây không có sẵn chúng.

Đừng đánh đồng singleton bean với **lớp có trường static** hoặc một global instance toàn JVM. Hai Spring contexts có thể sở hữu hai singleton khác nhau của cùng một bean definition logic.

## 8. Lỗi thường gặp và cách chẩn đoán

| Hiện tượng | Vì sao | Cách kiểm tra |
| --- | --- | --- |
| `cannot find symbol` / `package org.springframework... does not exist` | Tên/import/classpath/dependency compile sai | Kiểm tra JDK, Maven pom, `javac -cp`, package |
| Context không tìm thấy `GreetingService` | Class cấu hình chưa được nạp hoặc không có method `@Bean` hợp lệ | Kiểm tra `AppConfig.class` khi tạo context và method registration |
| `UnsatisfiedDependencyException` | Service cần bean `GreetingTemplate` nhưng thiếu ứng viên | Đăng ký collaborator hoặc sửa kiểu factory parameter |
| `NoUniqueBeanDefinitionException` | Hai/nhiều ứng viên cho một injection point cần một | Chọn bằng `@Qualifier`/`@Primary` hoặc giảm bean trùng |
| `BeanCreationException` | Factory method, constructor hoặc init thất bại | Đọc sâu `Caused by` và method/class đang tạo |
| `BeanCurrentlyInCreationException` | Có chu trình constructor/factory dependencies | Vẽ A→B→A, thiết kế lại dependency |
| Service tạo bằng `new` ngoài context không có lifecycle Spring | Object không được container quản lý | Inject thủ công hoặc lấy managed bean qua context |
| Cùng type có hai bean do đăng ký `@Component` lẫn `@Bean` | Đăng ký trùng không chủ đích | Chọn một cơ chế hoặc chỉ định candidate rõ |
| `injectedSame=false` sau thay đổi | Tự gọi `@Bean` method ở chế độ `proxyBeanMethods=false` | Dùng tham số factory method để Spring resolve |
| `getBean` thất bại khi context đã đóng | Sử dụng container sau shutdown | Dùng trong vòng đời context, đóng đúng nơi |
| Output lời chào sai dù context chạy | Logic Java/dữ liệu template sai | Unit test service/template, không quy mọi lỗi cho Spring |

### Phép thử âm đơn giản

1. **Thiếu bean:** xóa/không đăng ký method `@Bean GreetingTemplate greetingTemplate()` trong một cấu hình thử riêng. Vì `greetingService(GreetingTemplate)` yêu cầu dependency, context thường thất bại khi tạo service. Kiểm tra lỗi thiếu bean, không tự chèn null để chạy qua.
2. **Hai ứng viên:** thêm hai bean cùng kiểu `GreetingTemplate` rồi giữ injection point đơn trị không qualifier/primary. Nếu quy tắc chọn không có lựa chọn duy nhất, Spring báo mơ hồ. Lưu ý các quy tắc name/qualifier/primary có thể khiến một số trường hợp vẫn được giải quyết; không khẳng định cứ có hai bean là luôn thất bại.
3. **Chưa đăng ký config:** có class chứa `@Configuration` trong source nhưng context không được cung cấp class/scan/import tương ứng. Annotation không tự làm bean xuất hiện.
4. **Đổi tên method:** một lookup theo name có thể hỏng dù lookup theo type vẫn hoạt động. Hãy kiểm tra chính xác bean name thực tế.

Các thử nghiệm âm nên tách khỏi happy-path project. Không cần đóng đinh toàn bộ văn bản stack trace vì thông điệp và wrapper có thể thay đổi theo JDK/Spring/config.

### Đọc lỗi từ gốc

Lỗi ở service có thể chỉ là hiệu ứng của factory method tạo template thất bại. Trong exception chain, xác định bean name, injection point, factory method và **nguyên nhân đầu tiên có ý nghĩa**. Nếu `mvn` fail do không tải được dependency, đó chưa phải lỗi bean wiring. Nếu `javac` báo thiếu package Spring, chưa tới bước context xử lý annotation.

## 9. Kiểm thử logic và kiểm thử cấu hình

**Unit test Java thuần:** dùng fake template, không cần Spring:

~~~java
GreetingTemplate fake = name -> "TEST: " + name;
GreetingService service = new GreetingService(fake);
System.out.println(service.greet(" An ")); // TEST: An
~~~

Đây là đoạn minh họa trong phạm vi có quyền truy cập các nested types, không phải file độc lập. Nó chứng minh service có thể dùng collaborator khác do caller cung cấp.

**Smoke test Spring wiring:** khởi tạo context với cấu hình thật, lấy bean và kiểm tra reference:

~~~java
try (AnnotationConfigApplicationContext context =
        new AnnotationConfigApplicationContext(AppConfig.class)) {
    GreetingTemplate expected = context.getBean(GreetingTemplate.class);
    GreetingService actual = context.getBean(GreetingService.class);
    if (actual.template() != expected) {
        throw new IllegalStateException("unexpected injection");
    }
}
~~~

Đây cũng là snippet đặt trong method/class có import và quyền truy cập đầy đủ. Nó kiểm tra **cấu hình của container**, không chứng minh mọi hành vi nghiệp vụ hoặc mọi môi trường chạy đều đúng.

Một unit test PASS không chứng minh Spring đã đăng ký bean; ngược lại context refresh thành công không chứng minh logic câu chào đúng. Trong project thật, có thể đưa cả hai nhóm vào test tự động (ví dụ JUnit/Spring Test) khi công việc đủ lớn.

### Không dùng Java assert để thay kiểm tra bắt buộc

Java `assert` mặc định có thể bị tắt nếu không bật `-ea`. Nếu mục tiêu là **bắt buộc phát hiện sai wiring** trong test/ứng dụng, dùng assertion của test framework hoặc kiểm tra thường ném exception. Phần demo này in các giá trị boolean để quan sát; trong hệ thống nghiêm túc, nên **fail test** khi giá trị không đúng, không chỉ ghi log rồi tiếp tục.

## 10. Bài tập có đáp án

**Bài 1.** Một method `@Bean GreetingService greetingService(GreetingTemplate template)` được gọi như thế nào khi chỉ có một bean kiểu `GreetingTemplate`?

**Đáp án:** Spring resolve bean tương ứng theo kiểu/quy tắc injection, truyền nó vào tham số factory method và gọi method để lấy service. Bạn không phải tự gọi `greetingTemplate()`.

**Bài 2.** Nếu đã có `@Bean greetingService(...)` thì có cần thêm `@Component` cho `GreetingService` không?

**Đáp án:** Không. `@Bean` đã đăng ký factory tạo service; đăng ký thêm bằng scanning không chủ đích có thể tạo ứng viên trùng hoặc ambiguity.

**Bài 3.** Vì sao `serviceSingleton=true` trong demo?

**Đáp án:** `@Bean` mặc định có scope singleton trong cùng context. Hai lần `getBean(GreetingService.class)` trả về cùng instance, không phải vì class có trường static.

**Bài 4.** `@Configuration(proxyBeanMethods=false)` có intercept `greetingTemplate()` khi một method khác gọi trực tiếp nó không?

**Đáp án:** Không. Khi gọi trực tiếp, đó là lời gọi Java thường và có thể tạo thêm instance, vì vậy ví dụ chuẩn khai báo dependency ở tham số method.

**Bài 5.** Có thể tạo app Spring bằng chỉ `new AnnotationConfigApplicationContext(AppConfig.class)` không có Spring Boot không?

**Đáp án:** Có. Đây là Spring Framework Core Container thuần; module `spring-context`, cấu hình Java và JDK/Maven đủ cho ví dụ này.

**Bài 6.** Tại sao `context.containsBeanDefinition("greetingService")` thích hợp hơn việc khẳng định toàn context chỉ có hai bean definitions?

**Đáp án:** Context còn có thể có infrastructure definitions. Chỉ hai method `@Bean` của ứng dụng được kiểm tra theo **tên mục tiêu**, không phải tổng đếm tất cả definitions.

**Bài 7.** Một object `new GreetingService(new VietnameseTemplate())` ngoài context có phải Spring bean?

**Đáp án:** Không, đó là object Java thường, dù constructor injection bằng tay vẫn đúng. Nó không tự nhận lifecycle/scope của container.

## 11. Checklist hoàn thành bài

- [ ] Dùng đúng JDK 17+, Maven và module `spring-context`.
- [ ] Tên `pom.xml`, package, tên file, class public nhất quán.
- [ ] `AppConfig` có `@Configuration` và được nạp vào context.
- [ ] Hai factory methods dùng `@Bean` và có tên/kiểu rõ.
- [ ] `GreetingService` nhận `GreetingTemplate` qua constructor, không tự lấy bean từ context.
- [ ] `greetingService(GreetingTemplate)` dùng tham số do Spring resolve, không tự gọi `greetingTemplate()`.
- [ ] Hiểu default singleton và ý nghĩa của `proxyBeanMethods=false`.
- [ ] Chạy `mvn -q clean compile exec:java`, đối chiếu 5 dòng stdout.
- [ ] Nếu chạy `javac`/`java` trực tiếp, có classpath đủ JAR của Spring.
- [ ] Đóng context khi app sở hữu lifecycle nó và không dùng context sau close.
- [ ] Phân biệt kiểm tra registration, wiring, behavior và lỗi classpath.
- [ ] Thử ca thiếu bean/nhầm tên/cấu hình không được nạp trong test riêng.

**Kết luận:** Với `@Configuration`, Spring biết **nguồn cấu hình**; với `@Bean`, Spring biết **factory method cung cấp đối tượng**. `AnnotationConfigApplicationContext` xử lý metadata, resolve tham số phụ thuộc, tạo/giữ bean theo scope và cho ứng dụng dùng bean đó. Bạn đã có một ứng dụng Spring Core Container đầu tiên mà **không cần Spring Boot**.

### Tài liệu Spring chính thức

- [Java-based Container Configuration](https://docs.spring.io/spring-framework/reference/core/beans/java.html)
- [Using @Bean](https://docs.spring.io/spring-framework/reference/core/beans/java/bean-annotation.html)
- [Using @Configuration](https://docs.spring.io/spring-framework/reference/core/beans/java/configuration-annotation.html)
- [Dependency Injection and Collaborators](https://docs.spring.io/spring-framework/reference/core/beans/dependencies/factory-collaborators.html)
