# Lộ trình từ mô hình khái niệm đến kiểm chứng cấu hình — Spring Core Container

## 1. Mục tiêu: từ hiểu nguyên lý đến có bằng chứng ứng dụng hoạt động

Học **Spring Framework Core Container** không nên dừng ở việc thuộc tên `IoC`, `DI`, `bean` hay `ApplicationContext`. Một cấu hình chỉ thực sự hữu ích khi bạn chỉ ra được **ai cần ai**, **bean nào đáp ứng nhu cầu đó**, **container đã tạo và inject đúng đối tượng hay chưa**, và **các giả định vận hành đã được kiểm tra bằng hành vi chạy thật**.

Bài này hướng dẫn một **lộ trình có thể lặp lại** cho ứng dụng nhỏ dùng Java 17+ và Spring Framework: từ bản vẽ khái niệm, thiết kế hợp đồng, khai báo cấu hình, chạy chương trình, kiểm tra bean graph cho đến chẩn đoán một cấu hình sai. Đây là bài **kết nối tư duy với kiểm chứng**; không phải danh mục tất cả annotation của Spring.

### Sau bài này, bạn cần làm được

1. Chuyển yêu cầu nghiệp vụ ngắn thành **các thành phần, ranh giới và dependency có hướng**.
2. Chọn cấu hình Java với `@Configuration`/`@Bean` và **constructor injection** để lắp ghép đúng mô hình.
3. Biết **bean definition**, **bean instance**, **hợp đồng kiểu Java** và **đối tượng không do Spring quản lý** khác nhau thế nào.
4. Chạy một `AnnotationConfigApplicationContext` độc lập, không cần Spring Boot/web server.
5. Kiểm chứng **đăng ký bean**, **identity của các collaborator**, **scope singleton**, **hành vi nghiệp vụ**, **kết quả đầu ra** và **đóng context**.
6. Đưa ra phép thử âm cho **thiếu bean**, **nhiều bean ứng viên**, **vòng constructor**, **cấu hình không được nạp**.
7. Biết khi nào unit test Java thuần là đủ và khi nào phải khởi động Spring context để test wiring.

> **Nguyên tắc học:** Mỗi bước phải có **đầu ra kiểm chứng được**. “Context khởi động không lỗi” chỉ là một dấu hiệu, không chứng minh tất cả logic nghiệp vụ hoặc mọi cạnh phụ thuộc đã đúng.

## 2. Bản đồ toàn bộ lộ trình

~~~mermaid
flowchart TD
    A["Nhu cầu nghiệp vụ"] --> B["Mô hình đối tượng và dependency graph"]
    B --> C["Hợp đồng Java: interface / constructor"]
    C --> D["Bean definitions: @Configuration / @Bean"]
    D --> E["ApplicationContext: đăng ký và refresh"]
    E --> F{"Context khởi tạo được?"}
    F -->|Không| G["Đọc exception: thiếu / trùng / vòng dependency"]
    G --> C
    F -->|Có| H["Lấy bean, kiểm tra identity và scope"]
    H --> I["Chạy hành vi và so sánh stdout"]
    I --> J["Thử test âm, đóng context, cải tiến cấu hình"]
~~~

Có thể tách thành **6 mốc nghiệm thu**:

| Mốc | Sản phẩm phải có | Bằng chứng đạt |
| --- | --- | --- |
| 1 — Concept | Một dependency graph có chiều cạnh rõ | Nói được “consumer cần collaborator nào” |
| 2 — Design | Interface, constructor, hợp đồng method | Có thể khởi tạo/test Java thuần |
| 3 — Configuration | Tập hợp bean definitions tương ứng | Tên/kiểu bean và điểm injection xác định |
| 4 — Bootstrap | `ApplicationContext` chạy được | `refresh()`/khởi tạo hoàn thành |
| 5 — Verification | Phép kiểm tra registration, wiring, behavior | Kết quả PASS/đầu ra kỳ vọng |
| 6 — Failure & lifecycle | Ca thiếu/trùng/vòng dependency, cleanup | Biết cách tái hiện và chẩn đoán lỗi |

**Không đảo lộn hai bước:** nếu chưa biết dependency graph đúng là gì, bạn có thể đăng ký đủ bean để context khởi động nhưng vẫn nối sai triển khai. Ngược lại, một sơ đồ đúng trên giấy chưa bảo đảm container có bean definitions phù hợp.

## 3. Mốc 1 — Mô hình hóa trước khi cấu hình

Giả sử ứng dụng cần tạo lời chào cho người dùng, đồng thời lưu lại mã người đã được phục vụ. Nhu cầu chỉ gồm ba trách nhiệm:

- **Tra tên hiển thị:** `UserDirectory` biết tra một mã người dùng để lấy tên.
- **Tạo lời chào:** `GreetingService` dùng `UserDirectory`, không tự quyết định cách lưu dữ liệu.
- **Điều phối và audit:** `GreetingFacade` sử dụng `GreetingService` cùng `AuditTrail`.

Một sơ đồ hợp lý:

~~~mermaid
flowchart LR
    Facade["greetingFacade : GreetingFacade"]
    Service["greetingService : GreetingService"]
    Directory["userDirectory : UserDirectory"]
    Audit["auditTrail : AuditTrail"]
    Facade -->|"cần"| Service
    Facade -->|"cần"| Audit
    Service -->|"cần"| Directory
~~~

Hướng mũi tên là **consumer → dependency**. `GreetingFacade` không nhất thiết biết lớp triển khai của directory, chỉ cần một service đáp ứng hợp đồng.

Mô hình này gồm bốn bean ứng dụng. Spring còn có thể đăng ký **infrastructure bean definitions** cho chính cơ chế xử lý annotation; vì vậy **không** nên khẳng định toàn bộ `getBeanDefinitionCount()` của context bằng 4. Ta sẽ kiểm tra **bốn tên bean mà chính ứng dụng chủ động đăng ký**.

### Phân biệt ba lớp mô hình

| Lớp | Ví dụ | Điều cần xác minh |
| --- | --- | --- |
| Hợp đồng Java | `interface UserDirectory` | Phương thức, kiểu, ràng buộc đầu vào/đầu ra |
| Dependency logic | `GreetingService → UserDirectory` | Lớp consumer thật sự nhận collaborator đúng |
| Spring configuration | `@Bean UserDirectory userDirectory()` | Container có bean tương thích tại runtime |

**Không phải mọi lệnh `new` đều là lỗi IoC.** `new` trong factory method hoặc composition root là bình thường; vấn đề là lớp nghiệp vụ tự tìm/tạo những dependency mà nó không nên chịu trách nhiệm cấu hình.

### Đặt hợp đồng thành những câu hỏi có thể kiểm thử

- `UserDirectory.displayName("lan")` phải trả `"Lan"` trong triển khai demo.
- `GreetingService.greet("lan")` phải trả `"Xin chao, Lan!"`.
- `GreetingFacade.send("lan")` phải ghi một sự kiện audit **sau khi** tạo lời chào thành công.
- Service và facade phải nhận **cùng các bean singleton** mà context trả về (trong cấu hình minh họa).
- Nếu thiếu `UserDirectory` bắt buộc, cấu hình không được âm thầm thay bằng `null`.

Đây là **acceptance criteria**, không phải nhận định mơ hồ như “Spring chạy tốt”.

## 4. Mốc 2 — Từ dependency sang thiết kế Java

Hãy ưu tiên **constructor injection** cho dependency bắt buộc:

~~~java
interface UserDirectory {
    String displayName(String userId);
}

final class GreetingService {
    private final UserDirectory directory;

    GreetingService(UserDirectory directory) {
        this.directory = java.util.Objects.requireNonNull(directory);
    }

    String greet(String id) {
        return "Xin chao, " + directory.displayName(id) + "!";
    }
}
~~~

**Đây là đoạn minh họa, chưa phải chương trình độc lập.** Nó thể hiện:

1. Service chỉ phụ thuộc **interface**, không phụ thuộc cơ chế lưu dữ liệu cụ thể.
2. Constructor chỉ nhận một collaborator; lớp service **không gọi `ApplicationContext.getBean(...)`** ở trong domain logic.
3. Dependency được lưu vào trường `final`, hạn chế việc đổi tham chiếu sau khởi tạo.
4. Có thể unit test bằng implementation giả **không cần Spring**:

~~~java
UserDirectory fake = id -> "Test";
GreetingService service = new GreetingService(fake);
System.out.println(service.greet("anything")); // Xin chao, Test!
~~~

Ở đây ta đã có **DI theo nghĩa thiết kế**, dù chưa tạo một Spring container. Spring chỉ tự động hóa phần **đăng ký, tìm ứng viên, khởi tạo, injection và lifecycle**.

### Khi nào không cần abstraction?

Đừng tạo interface chỉ vì “học Spring phải có interface”. Nó có giá trị khi biểu thị một hợp đồng rõ, có nhiều cách triển khai, cần fake trong test hoặc phân tách domain với infrastructure. Với một utility thuần tính toán không chứa trạng thái, dùng lớp Java đơn giản vẫn phù hợp.

## 5. Mốc 3 — Đăng ký bean definitions

Trong Spring Java configuration:

~~~java
@Configuration(proxyBeanMethods = false)
class AppConfig {
    @Bean
    UserDirectory userDirectory() {
        return new InMemoryDirectory();
    }

    @Bean
    GreetingService greetingService(UserDirectory directory) {
        return new GreetingService(directory);
    }
}
~~~

**Minh họa chưa độc lập** vì `InMemoryDirectory` chưa xuất hiện ở đoạn riêng này. Mỗi `@Bean` khai báo một **bean definition** từ factory method; **tên bean mặc định thường là tên method**. Tham số `UserDirectory directory` chính là điểm Spring phải resolve từ những bean có sẵn.

Phải biết phân biệt:

- **Đăng ký bean definition:** context biết *cách* tạo bean.
- **Tạo bean instance:** context thực sự chạy factory/constructor ở thời điểm phù hợp.
- **Injection:** đối tượng đã phù hợp được cung cấp cho điểm cần dependency.
- **Use:** code nghiệp vụ chủ động gọi method như bình thường, Spring không tự động gọi `greet` chỉ vì bean được đăng ký.

Với `@Configuration(proxyBeanMethods = false)`, đừng gọi trực tiếp `@Bean` method khác để “lấy bean singleton”. Đó có thể chỉ là lời gọi Java trực tiếp. Hãy khai báo dependency bằng **tham số factory method**, như `greetingService(UserDirectory directory)`, để container giải quyết.

### BeanFactory và ApplicationContext

`BeanFactory` cung cấp cơ chế lõi tra cứu bean; `ApplicationContext` mở rộng khả năng quản lý lifecycle, event, message resource và quá trình bootstrap thuận tiện. Bài này dùng `AnnotationConfigApplicationContext` để khởi động thuần Java.

Mặc định singleton thông thường được khởi tạo khi `ApplicationContext` refresh; `@Lazy` hoặc scope khác có thể trì hoãn. **Bean definition tồn tại không có nghĩa instance đã được tạo**. Đừng dựa vào thứ tự các method được liệt kê làm hợp đồng thứ tự khởi tạo.

## 6. Mốc 4–5 — Dự án hoàn chỉnh với phép kiểm tra chạy thật

Dự án sau dùng **Java 17**, **Maven**, **Spring Framework 6.2.19** qua `spring-context`. Đây là một phiên bản được ghim để tái lập ví dụ, **không phải khẳng định nó là phiên bản Spring mới nhất**. Chương trình không cần Spring Boot, database hay HTTP server.

~~~text
config-verification-demo/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── demo/
                └── ConfigurationVerificationDemo.java
~~~

### 6.1. `pom.xml`

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>config-verification-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.19</version>
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
                    <mainClass>demo.ConfigurationVerificationDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Maven tự tải `spring-context` cùng dependency transitively cần thiết. Nếu cố dùng riêng một file JAR của Spring ở classpath, compiler hoặc runtime có thể báo thiếu lớp từ các module khác.

### 6.2. `src/main/java/demo/ConfigurationVerificationDemo.java`

~~~java
package demo;

import java.util.ArrayList;
import java.util.List;
import java.util.Objects;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

public final class ConfigurationVerificationDemo {
    private ConfigurationVerificationDemo() {}

    public interface UserDirectory {
        String displayName(String userId);
    }

    public static final class InMemoryDirectory
            implements UserDirectory {
        @Override
        public String displayName(String userId) {
            if ("lan".equals(userId)) {
                return "Lan";
            }
            throw new IllegalArgumentException("unknown user");
        }
    }

    public static final class GreetingService {
        private final UserDirectory directory;

        public GreetingService(UserDirectory directory) {
            this.directory = Objects.requireNonNull(directory);
        }

        public String greet(String userId) {
            return "Xin chao, " + directory.displayName(userId) + "!";
        }

        public UserDirectory directory() {
            return directory;
        }
    }

    public static final class AuditTrail {
        private final List<String> events = new ArrayList<>();

        public void record(String userId) {
            events.add(userId);
        }

        public List<String> snapshot() {
            return List.copyOf(events);
        }
    }

    public static final class GreetingFacade {
        private final GreetingService service;
        private final AuditTrail audit;

        public GreetingFacade(GreetingService service, AuditTrail audit) {
            this.service = Objects.requireNonNull(service);
            this.audit = Objects.requireNonNull(audit);
        }

        public String send(String userId) {
            String message = service.greet(userId);
            audit.record(userId);
            return message;
        }

        public GreetingService service() {
            return service;
        }

        public AuditTrail audit() {
            return audit;
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class AppConfig {
        @Bean
        public UserDirectory userDirectory() {
            return new InMemoryDirectory();
        }

        @Bean
        public AuditTrail auditTrail() {
            return new AuditTrail();
        }

        @Bean
        public GreetingService greetingService(UserDirectory directory) {
            return new GreetingService(directory);
        }

        @Bean
        public GreetingFacade greetingFacade(
                GreetingService service, AuditTrail audit) {
            return new GreetingFacade(service, audit);
        }
    }

    private static void require(boolean condition, String message) {
        if (!condition) {
            throw new IllegalStateException(message);
        }
    }

    public static void main(String[] args) {
        try (AnnotationConfigApplicationContext context =
                new AnnotationConfigApplicationContext(AppConfig.class)) {

            String[] appBeanNames = {
                "userDirectory", "auditTrail",
                "greetingService", "greetingFacade"
            };
            for (String beanName : appBeanNames) {
                require(context.containsBeanDefinition(beanName),
                        "missing bean definition: " + beanName);
            }
            System.out.println("definitions=4/4");

            UserDirectory directory = context.getBean(UserDirectory.class);
            GreetingService service =
                    context.getBean(GreetingService.class);
            AuditTrail audit = context.getBean(AuditTrail.class);
            GreetingFacade facade = context.getBean(GreetingFacade.class);

            require(service.directory() == directory,
                    "service is wired to wrong directory");
            require(facade.service() == service,
                    "facade is wired to wrong service");
            require(facade.audit() == audit,
                    "facade is wired to wrong audit");
            System.out.println("wiring=PASS");

            require(context.getBean(GreetingService.class) == service,
                    "greetingService is not singleton");
            System.out.println("singleton=PASS");

            System.out.println("message=" + facade.send("lan"));
            System.out.println("audit=" + audit.snapshot());
        }
    }
}
~~~

Chương trình có một lớp top-level `public` khớp tên file, các kiểu hỗ trợ là nested types. Các factory method `@Bean` truyền dependency qua **tham số**, không tự gọi nhau. Không cần `@Autowired` trên các factory method: Spring phân giải method arguments của `@Bean`.

Các kiểm tra `require(...)` **luôn được thực thi**. Khác với Java `assert`, chúng **không bị bỏ qua** khi chạy mặc định thiếu cờ `-ea`.

### 6.3. Chạy bằng Maven

Đứng trong thư mục `config-verification-demo`:

~~~bash
java -version
mvn -version
mvn -q clean compile exec:java
~~~

**Stdout chính xác do ứng dụng in khi các kiểm tra PASS:**

~~~text
definitions=4/4
wiring=PASS
singleton=PASS
message=Xin chao, Lan!
audit=[lan]
~~~

Lệnh `java -version`, `mvn -version` và các dòng log Maven/Spring (nếu cấu hình logging hiển thị) không thuộc **năm dòng stdout ứng dụng** này. Nếu một phép kiểm tra `require` thất bại, chương trình **không được phép** in tiếp các dòng PASS sau đó; exception chỉ rõ giả định nào sai.

### 6.4. Biên dịch và chạy trực tiếp bằng `javac`/`java`

Với mã Spring, classpath phải có Spring JAR và các dependency transitively cần thiết. Có thể nhờ Maven tạo file classpath:

~~~bash
mvn -q dependency:build-classpath -Dmdep.outputFile=classpath.txt
~~~

**Linux/macOS (bash/zsh):**

~~~bash
mkdir -p out
javac --release 17 -encoding UTF-8 \
  -cp "$(cat classpath.txt)" \
  -d out src/main/java/demo/ConfigurationVerificationDemo.java
java -cp "out:$(cat classpath.txt)" demo.ConfigurationVerificationDemo
~~~

**Windows PowerShell:**

~~~powershell
$deps = (Get-Content -Raw classpath.txt).Trim()
New-Item -ItemType Directory -Force out | Out-Null
javac --release 17 -encoding UTF-8 -cp "$deps" -d out src/main/java/demo/ConfigurationVerificationDemo.java
java -cp "out;$deps" demo.ConfigurationVerificationDemo
~~~

Dấu `:` phân tách classpath trên Unix; dấu `;` trên Windows. Chạy lại cùng class cho cùng **năm dòng stdout** ở mục 6.3. Lỗi `package org.springframework... does not exist` thường cho biết classpath chưa chứa Spring, **không tự chứng minh logic IoC sai**.

## 7. Đọc các phép kiểm tra: kiểm chứng từng tầng

| Kiểm tra thực hiện | Bằng chứng | Điều nó **không** chứng minh |
| --- | --- | --- |
| `containsBeanDefinition(name)` cho bốn tên | Bốn bean definitions ứng dụng đã được đăng ký | Bean nào đó chắc chắn đã khởi tạo đúng mọi hành vi |
| `getBean(Type.class)` | Container có thể cung cấp một ứng viên kiểu phù hợp | Mọi use case kinh doanh đều đúng |
| So sánh `service.directory() == directory` | Chính bean directory được inject vào service | Implementation directory không có lỗi nghiệp vụ |
| So sánh `facade.service() == service` và `facade.audit() == audit` | Các cạnh wiring được nối đúng object | Mọi đường đi runtime đều gọi collaborator |
| Gọi lại `getBean(GreetingService.class) == service` | Cùng instance singleton trong context này | Mọi bean đều singleton hoặc singleton toàn JVM |
| `facade.send("lan")` và `audit.snapshot()` | Logic lời chào và ghi audit của ca mẫu đúng | Cấu hình môi trường khác cũng đúng |
| `try-with-resources` đóng context | Code đóng context khi thoát khối | Mọi resource tự tạo ngoài container đã được dọn |

**Không nhầm số lượng:** `definitions=4/4` là *bốn bean name ứng dụng có mặt*, **không phải** `context.getBeanDefinitionCount() == 4`. Spring đăng ký các infrastructure definitions khác để hỗ trợ annotation/configuration.

**Không dùng `==` bừa:** so sánh reference ở đây là phép kiểm tra identity trong cấu hình singleton cụ thể. Nó không có nghĩa mọi bean cùng type trong các context khác nhau đều là cùng một object, hoặc prototype/scoped proxy luôn tuân theo các giả định đó.

### Vì sao kiểm tra wiring bằng identity hữu ích?

Một context có thể khởi tạo thành công nhưng chọn sai triển khai của một interface khi nhiều bean cùng tương thích. Nếu biết **đích mong muốn** là một bean cụ thể, có thể kiểm tra tham chiếu được inject khớp bean đó trong test wiring. Với proxy/scoped bean, phải điều chỉnh bằng hợp đồng phù hợp thay vì ép kiểm tra identity của implementation thô.

## 8. Mốc 6 — Thử cấu hình sai một cách có kiểm soát

Sau đường chạy thành công, thử các **negative tests** trên cấu hình tách biệt. Đừng làm hỏng `AppConfig` đang dùng cho happy path rồi mới đánh giá mơ hồ.

### Ca A: thiếu dependency bắt buộc

Ví dụ mã minh họa, cần đặt trong lớp/config phù hợp:

~~~java
@Configuration(proxyBeanMethods = false)
class MissingDirectoryConfig {
    @Bean
    GreetingService greetingService(UserDirectory directory) {
        return new GreetingService(directory);
    }
}
~~~

Khi **chỉ** nạp `MissingDirectoryConfig` và không có bean `UserDirectory` khác, container không thể resolve tham số `directory` cho factory method. Context thường không refresh thành công; chuỗi ngoại lệ có thể gồm `UnsatisfiedDependencyException` hoặc `NoSuchBeanDefinitionException`.

**Quan sát đáng tin:** *context thất bại vì thiếu bean bắt buộc*, không phụ thuộc từng chữ của stack trace — nội dung thông báo, line number và wrapper có thể đổi theo phiên bản/cấu hình.

### Ca B: nhiều bean cạnh tranh

~~~java
@Bean
UserDirectory directoryOne() { return new InMemoryDirectory(); }

@Bean
UserDirectory directoryTwo() { return new InMemoryDirectory(); }
~~~

Đây là **mã minh họa** trong một configuration khác. Nếu một injection point yêu cầu **duy nhất `UserDirectory`** mà có hai ứng viên tương đương, Spring có thể báo `NoUniqueBeanDefinitionException`. Cân nhắc:

- Chọn một bean bằng `@Qualifier` ở injection point.
- Đặt `@Primary` ở bean ứng viên ưu tiên khi có lý do rõ.
- Bỏ đăng ký không cần thiết hoặc sửa thiết kế để hợp đồng trở nên rõ.
- Nếu ứng dụng cần nhiều implementation, inject collection hoặc `ObjectProvider<UserDirectory>` theo nhu cầu.

Lưu ý: Spring có nhiều quy tắc chọn bean (qualifier, primary, fallback, tên tham số, v.v.). **Hai bean cùng kiểu không có nghĩa mọi injection đều chắc chắn thất bại**, nhưng đó là tình huống cần kiểm tra có chủ đích.

### Ca C: vòng constructor

~~~java
final class A {
    A(B b) {}
}

final class B {
    B(A a) {}
}
~~~

Nếu đăng ký A và B đều cần nhau ngay ở constructor, dependency graph có chu trình A→B→A. Không thể hoàn tất thông thường bằng cách “khởi tạo bean nào trước”; bạn cần **đổi thiết kế/ranh giới trách nhiệm**, không dùng field injection như một miếng vá mặc định.

### Ca D: class cấu hình không được đăng ký

Một `@Configuration` hoặc `@Component` tồn tại trong source **không tự động xuất hiện trong context**. Nếu chỉ nạp `OtherConfig.class`, bean trong `AppConfig.class` không được đăng ký trừ khi import/scan/đăng ký nó qua cơ chế tương ứng. Hãy kiểm tra **đối tượng cấu hình đã được cung cấp cho context nào** chứ không chỉ nhìn source có annotation.

### Ca E: dùng `new` ngoài container

~~~java
GreetingService manual = new GreetingService(
        userId -> "Manual");
System.out.println(manual.greet("x")); // Xin chao, Manual!
~~~

Đây là đoạn minh họa bên trong một method có thể truy cập nested classes. `manual` là đối tượng Java thông thường, **không phải bean Spring**. Nó có thể chạy đúng vì caller đã truyền dependency thủ công; đừng kỳ vọng nó nhận callbacks/bean scope của context tự động.

## 9. Lộ trình kiểm tra khi thất bại ở từng giai đoạn

| Giai đoạn | Triệu chứng | Hướng kiểm tra đầu tiên |
| --- | --- | --- |
| Compile Java | `cannot find symbol` / `package org.springframework... does not exist` | Tên class, package, Maven dependency, classpath, JDK |
| Context refresh | `UnsatisfiedDependencyException` | Bean nào cần loại dependency nào; thiếu đăng ký hoặc không scan |
| Candidate selection | `NoUniqueBeanDefinitionException` | Có bao nhiêu bean phù hợp, qualifier/primary, hợp đồng injection |
| Circular wiring | `BeanCurrentlyInCreationException` | Vẽ chu trình dependency constructor/factory |
| Runtime behavior | Xuất sai câu chào | Kiểm tra implementation directory, input, logic service; không quy mọi lỗi cho Spring |
| Scope | Hai lần lấy bean khác identity ngoài mong muốn | Kiểm tra scope, provider, lazy, proxy và context có cùng hay không |
| Lifecycle | Resource chưa đóng hoặc callback không được gọi | Bean có được container quản lý, có đúng scope/lifecycle hook không |
| Startup vs test | Unit test PASS, context FAIL | Unit test không kiểm tra bean registration/wiring; thêm integration smoke test |

**Đọc ngoại lệ từ gốc:** một `BeanCreationException` ở bean cấp trên thường chỉ là hệ quả của bean phụ thuộc bị lỗi. Theo chuỗi `Caused by` để tìm điểm injection, bean definition hoặc constructor/factory đầu tiên gặp vấn đề.

**Đừng** bắt mọi `BeansException` rồi tiếp tục với dependency null: một cấu hình thiếu dependency bắt buộc nên **fail fast** thay vì âm thầm tạo một ứng dụng ở trạng thái sai.

## 10. Kiểm thử theo hai tầng, không phụ thuộc máy móc vào annotation

### Unit test thiết kế Java thuần

Một fake không cần Spring:

~~~java
UserDirectory fake = id -> "Tester";
GreetingService service = new GreetingService(fake);
System.out.println(service.greet("x")); // Xin chao, Tester!
~~~

Đây là đoạn minh họa **không phải file Java độc lập**; có thể đặt trong một method test hoặc trong lớp ví dụ. Unit test tập trung vào kết quả khi thay implementation, xử lý input và tác dụng phụ của logic.

### Integration/smoke test cho cấu hình Spring

Khởi tạo context với configuration thật:

~~~java
try (AnnotationConfigApplicationContext context =
        new AnnotationConfigApplicationContext(AppConfig.class)) {
    GreetingFacade facade = context.getBean(GreetingFacade.class);
    // Kiểm tra bean graph, collaborator identity và hành vi.
}
~~~

Đây cũng là snippet nằm trong chương trình/test có quyền truy cập các nested classes. Kiểm tra cấu hình thật: tên bean đúng, dependency rõ ràng, không thiếu/trùng, scope và hành vi mẫu. Nếu hệ thống có nhiều profile/conditional beans, cần test những **tổ hợp môi trường thực sự được hỗ trợ**, không chỉ một context mặc định.

Không bắt buộc dùng toàn bộ Spring test infrastructure cho ví dụ nhỏ; khi đã có JUnit/Spring Test, có thể đưa phép kiểm tra tương tự vào test tự động. Cần phân biệt: **unit test đúng không chứng minh wiring đúng; wiring đúng không chứng minh business logic đúng**.

## 11. Cách nâng dần độ khó sau ví dụ

Khi đã thấy năm dòng stdout kỳ vọng, tiến theo thứ tự:

1. **Đổi implementation:** tạo một `UserDirectory` khác (ví dụ trả tên từ cấu hình), chọn rõ bean bằng `@Qualifier` khi có nhiều candidate. Kiểm chứng kết quả đổi đúng, không sửa `GreetingService`.
2. **Tách configuration:** chia các factory methods thành config cho infrastructure và service; dùng `@Import` hoặc đăng ký rõ chúng vào context. Kiểm tra không vô tình mất bean.
3. **Thử optional dependency:** nếu audit là tùy chọn theo hợp đồng, nghiên cứu `ObjectProvider<AuditTrail>`/cơ chế nullable phù hợp; đừng biến bắt buộc thành tùy chọn để che lỗi.
4. **Thử scope/lazy:** so sánh singleton với prototype, nhưng không dựa vào `==` cho những scope khác; theo dõi điểm tạo instance.
5. **Quan sát lifecycle:** thêm một bean sở hữu tài nguyên giả với callback destroy rồi đóng context. Phân biệt bean container quản lý và object tạo tay.
6. **Tách unit và integration test:** một bộ test chỉ cần Java thuần, bộ kia thật sự boot context. Chạy trong pipeline build khi hệ thống lớn hơn.

### Khi nào hoàn thành một bài cấu hình?

Một cấu hình được xem là có bằng chứng tối thiểu khi:

- Có mô hình dependency/hợp đồng rõ, không chỉ annotation.
- Đăng ký đủ bean definitions cho các dependency bắt buộc.
- Context có thể bootstrap ở môi trường dự kiến.
- Các điểm wiring quan trọng được kiểm tra, không chỉ `getBean` một lớp bất kỳ.
- Có ca hành vi cho kết quả cụ thể.
- Có ít nhất một ca lỗi cấu hình được hiểu và chẩn đoán đúng.
- Context được đóng khi ứng dụng sở hữu lifecycle của nó.
- Không dựa vào thứ tự init tình cờ, bean name/bean count không kiểm chứng, hoặc môi trường máy riêng.

## 12. Những nhầm lẫn cần tránh

- **“Đọc annotation là biết ứng dụng đã đúng.”** Annotation chỉ nêu metadata; kiểm tra runtime vẫn cần.
- **“Spring container tự làm mọi nghiệp vụ.”** Container cung cấp wiring/lifecycle; hành vi phương thức vẫn do code Java của bạn.
- **“Context khởi động là xong mọi bài test.”** Có thể wiring được nhưng chọn sai implementation hoặc logic sai.
- **“Bean count phải bằng số method `@Bean` mình viết.”** Có thể có infrastructure definitions và cơ chế đăng ký khác; kiểm tra tên mục tiêu thay vì tổng không hiểu rõ.
- **“Singleton là một object trên mọi JVM.”** Singleton mặc định theo một bean definition trong một container.
- **“Có interface thì Spring tự chọn implementation đúng.”** Phải có bean phù hợp; nhiều ứng viên cần phân giải rõ.
- **“`@Lazy` xóa dependency.”** Không; nó chỉ thay đổi thời điểm giải quyết/tạo trong những cấu hình phù hợp.
- **“Cứ bật `-ea` mới kiểm tra được cấu hình.”** Không; dùng phép kiểm tra runtime thông thường/test assertion chạy độc lập với cờ assertions của JVM.
- **“Có Spring Boot mới dùng được IoC.”** Không; ví dụ chạy bằng Spring Framework thuần và Maven.

## 13. Bài tập tự kiểm tra và đáp án

**Bài 1.** `GreetingFacade` phụ thuộc `GreetingService` và `AuditTrail`; `GreetingService` phụ thuộc `UserDirectory`. Vẽ các cạnh, hướng và số bean definitions ứng dụng.

**Đáp án:** Ba cạnh: facade→service, facade→audit, service→directory. Bốn bean definitions ứng dụng được đăng ký. Không suy ra `getBeanDefinitionCount() == 4` cho cả context.

**Bài 2.** Giữ nguyên config nhưng đổi `InMemoryDirectory` để nó trả `"Mai"` khi id là `"lan"`. Cần sửa class nào, stdout nào đổi?

**Đáp án:** Chỉ sửa triển khai directory hoặc cách factory tạo nó; `GreetingService` không phải sửa. Dòng `message=...` thay đổi theo dữ liệu, còn wiring/singleton có thể tiếp tục PASS.

**Bài 3.** Tại sao so sánh `facade.service() == context.getBean(GreetingService.class)` có ý nghĩa trong demo, nhưng không phải quy tắc chung cho mọi scope?

**Đáp án:** Trong demo cả hai lấy cùng singleton từ cùng context. Prototype/scoped proxy/provider có semantics khác, nên không dùng mặc định cùng một phép so identity cho mọi thiết kế.

**Bài 4.** Đăng ký hai bean `UserDirectory` khác nhau, giữ một tham số `UserDirectory directory` không qualifier. Cần kiểm tra gì?

**Đáp án:** Xem toàn bộ quy tắc chọn candidate và xác minh thực tế bean nào được inject. Nếu không có lựa chọn duy nhất, context thất bại vì ambiguity; nên dùng qualifier/primary hoặc thay đổi cách đăng ký.

**Bài 5.** Unit test với fake PASS nhưng `new AnnotationConfigApplicationContext(AppConfig.class)` thất bại. Có mâu thuẫn không?

**Đáp án:** Không. Unit test chỉ chứng minh service làm đúng khi caller truyền dependency; integration test cần xác nhận Spring có **đăng ký và resolve** được dependency thật.

## 14. Checklist áp dụng

- [ ] Viết được yêu cầu nghiệp vụ và các lớp chịu trách nhiệm rõ ràng.
- [ ] Vẽ bean graph theo hướng **consumer → dependency**, tránh phụ thuộc vòng.
- [ ] Thiết kế hợp đồng và constructor injection trước khi đặt annotation.
- [ ] Liệt kê mỗi bean definition: tên, kiểu, factory, scope và dependency.
- [ ] Bootstrap `ApplicationContext` bằng configuration chính xác cần kiểm tra.
- [ ] Kiểm tra sự tồn tại của **bean names mục tiêu**, không giả định tổng số definitions.
- [ ] Kiểm tra wiring thực tế (reference hoặc behavior) ở các cạnh quan trọng.
- [ ] Kiểm tra singleton/lifecycle theo đúng ngữ nghĩa scope.
- [ ] Chạy hành vi mẫu và đối chiếu stdout chuẩn.
- [ ] Chuẩn bị ca lỗi thiếu/trùng bean, vòng constructor, config không được nạp.
- [ ] Đóng context và theo dõi resource thuộc sở hữu ứng dụng.
- [ ] Phân chia test Java thuần và test Spring wiring; không thay thế cái này bằng cái kia.

**Kết luận:** Lộ trình hiệu quả là **mô hình đúng → hợp đồng rõ → bean definitions chính xác → container bootstrap → kiểm chứng wiring và hành vi → kiểm tra các ca thất bại**. Bằng chứng runtime làm cho hiểu biết về IoC/DI và Core Container trở thành năng lực triển khai thực tế.

### Tài liệu chính thức

- [Spring IoC Container — Introduction](https://docs.spring.io/spring-framework/reference/6.2/core/beans/introduction.html)
- [Dependency Injection](https://docs.spring.io/spring-framework/reference/6.2/core/beans/dependencies/factory-collaborators.html)
- [Using @Bean](https://docs.spring.io/spring-framework/reference/6.2/core/beans/java/bean-annotation.html)
- [BeanFactory and ApplicationContext](https://docs.spring.io/spring-framework/reference/6.2/core/beans/beanfactory.html)
