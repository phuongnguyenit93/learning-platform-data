# InitializingBean.afterPropertiesSet và @Bean(initMethod) trong vòng đời bean Spring

## 1. Vì sao bean cần giai đoạn initialization?

Spring IoC Container không chỉ gọi constructor để tạo một object. Container còn xác định dependency, inject cấu hình, chạy các bean post-processor và cho phép bean thực hiện **khởi tạo sau khi dependency đã sẵn sàng** (*initialization callback*). Đây là nơi bean có thể xác thực cấu hình, xây dựng cấu trúc dữ liệu dẫn xuất hoặc mở tài nguyên cần thiết cho hoạt động của chính nó.

Hai cơ chế trọng tâm của bài:

- `InitializingBean.afterPropertiesSet()`: bean **implements interface của Spring** và Spring gọi method này sau khi properties/dependencies được thiết lập.
- `@Bean(initMethod = "tenMethod")`: cấu hình bean definition để Spring **gọi một method tùy chọn trên bean được factory method tạo ra**, không bắt class đó implements interface Spring.

Chúng là hai cách khác nhau để tham gia **cùng pha initialization**. Có thể dùng cả hai trên một bean; khi đó phải hiểu thứ tự callback và trách nhiệm của từng callback để không khởi tạo lặp hoặc tạo side effect không mong muốn.

Kết quả mong đợi sau bài:

1. Chỉ ra vị trí chính xác của hai callback trong vòng đời bean.
2. Khai báo và sử dụng đúng `InitializingBean` lẫn `@Bean(initMethod = ...)`.
3. Biết thứ tự khi kết hợp với `@PostConstruct` và vòng đời destroy.
4. Viết một ví dụ Spring Framework 6.x/Java 17+ chạy được, kiểm chứng thứ tự callback bằng stdout.
5. Phân biệt callback khởi tạo với constructor, `@Bean` factory method, `BeanPostProcessor`, `@Lazy` và các startup hook như `ApplicationRunner`.
6. Chẩn đoán lỗi method không tồn tại, dependency chưa có, callback throw exception, hoặc thực hiện initialization hai lần.

**Phạm vi:** Spring Framework Core Container. Các ví dụ chạy bằng Java 17 và Spring Context 6.1.x; không bắt buộc Spring Boot hoặc máy chủ HTTP.

## 2. Mô hình vòng đời: callback nằm ở đâu?

Một thứ tự đơn giản hóa cho một bean Spring thông thường:

~~~text
Đọc bean definition
        |
        v
Chọn constructor / factory method
        |
        v
Tạo object Java
        |
        v
Điền dependency, properties và thực hiện aware callbacks
        |
        v
BeanPostProcessor trước initialization
  (ví dụ xử lý @PostConstruct)
        |
        v
InitializingBean.afterPropertiesSet()
        |
        v
Custom init method từ bean definition
  (ví dụ @Bean(initMethod = "connect"))
        |
        v
BeanPostProcessor sau initialization
  (có thể tạo proxy AOP)
        |
        v
Bean sẵn sàng được sử dụng qua container
        |
        v
Khi scope kết thúc: destruction callbacks được hỗ trợ
~~~

Sơ đồ mô tả luồng phổ biến của một bean được container tạo thành công. Trên thực tế có nhiều extension point khác nhau, lazy bean, scoped proxy, circular dependency và các bean post-processor có thể thay đổi chi tiết. Điều cần ghi nhớ là **các init callback chạy sau khi dependency của bean đã được gán, trước khi hoàn tất initialization của bean**.

Nếu ba cơ chế đều có mặt **trên cùng một bean** và tên method khác nhau, thứ tự được Spring tài liệu hóa là:

1. Method gắn `@PostConstruct`.
2. `InitializingBean.afterPropertiesSet()`.
3. Custom init method được khai báo bằng `@Bean(initMethod = "...")` hoặc metadata tương đương.

Các `BeanPostProcessor` được Spring gọi trước và sau giai đoạn initialization, không đồng nghĩa mọi post-processor hoạt động ở cùng một thời điểm. Ví dụ xử lý `@PostConstruct` là công việc trong bước *before initialization*. Bean có thể được AOP bọc sau các callback initialization, nên không nên giả định lời gọi trong init method đã đi qua proxy cuối cùng.

## 3. `InitializingBean.afterPropertiesSet()`

### 3.1. Interface và hợp đồng

`InitializingBean` thuộc package:

~~~java
import org.springframework.beans.factory.InitializingBean;
~~~

Interface định nghĩa một method:

~~~java
public interface InitializingBean {
    void afterPropertiesSet() throws Exception;
}
~~~

Đây là chữ ký hợp đồng của interface để giải thích API; bạn **không cần tự khai báo lại interface** trong project. Spring gọi method một lần cho mỗi lần **container thực hiện initialization của bean instance đó**, sau khi đã cung cấp dependencies/properties qua cơ chế quản lý bean tương ứng.

Ví dụ class bean:

~~~java
import org.springframework.beans.factory.InitializingBean;

public class ReportFormatter implements InitializingBean {
    private String prefix;

    public void setPrefix(String prefix) {
        this.prefix = prefix;
    }

    @Override
    public void afterPropertiesSet() {
        if (prefix == null || prefix.isBlank()) {
            throw new IllegalStateException("prefix must not be blank");
        }
    }

    public String format(String value) {
        return prefix + value;
    }
}
~~~

Đây là **class có thể biên dịch nếu có Spring Beans trên classpath**; muốn được Spring gọi `afterPropertiesSet()` tự động, cần đăng ký instance bằng Spring bean definition (ví dụ `@Bean` hoặc `@Component` cùng cấu hình dependency).

Spring đảm bảo các dependency thuộc quá trình lắp ráp bình thường đã được gán trước callback. Do đó `afterPropertiesSet()` phù hợp cho:

- Xác thực nhiều properties phụ thuộc nhau.
- Chuyển đổi cấu hình thành cấu trúc dữ liệu sẵn dùng.
- Chuẩn bị tài nguyên nội bộ yêu cầu các dependency đã được cung cấp.
- Phát hiện cấu hình bất hợp lệ ngay khi container khởi tạo bean thay vì chờ đến request đầu tiên.

Tuy nhiên, **“properties đã được gán” không có nghĩa toàn bộ ứng dụng hoặc mọi bean khác đã khởi tạo xong**. Tránh coi đây là hook cho công việc cần tất cả service của ứng dụng đã hoàn tất startup.

### 3.2. Có thể throw exception

Method trong interface khai báo `throws Exception`. Nếu initialization thất bại, bạn có thể ném exception có ý nghĩa:

~~~java
@Override
public void afterPropertiesSet() {
    if (endpoint == null || endpoint.isBlank()) {
        throw new IllegalStateException("endpoint is required");
    }
    if (retryCount < 0) {
        throw new IllegalArgumentException("retryCount must be >= 0");
    }
}
~~~

Đoạn này minh họa một method nằm bên trong class đã có fields `endpoint` và `retryCount`. Nó không phải file Java độc lập.

Khi callback ném exception, việc tạo bean **không hoàn tất thành công**. Với singleton được tạo eagerly khi context refresh, lỗi thường khiến context khởi động thất bại, được bọc trong ngoại lệ tạo bean có cause gốc. Với lazy bean, lỗi có thể chỉ xuất hiện ở lần lấy bean đầu tiên.

### 3.3. Mặt đánh đổi

Ưu điểm:

- Method rõ ràng, tên thống nhất, không phải cấu hình chuỗi tên method.
- IDE và compiler kiểm tra việc implements interface.
- Phù hợp khi class thuộc ứng dụng Spring và bạn muốn biểu đạt contract “cần được khởi tạo sau injection”.

Nhược điểm:

- Class business phụ thuộc API Spring qua `InitializingBean`.
- Không thể thêm interface này vào class thư viện bên thứ ba mà bạn không sửa được.
- Nếu gọi `afterPropertiesSet()` thủ công hoặc gọi lại trong logic bình thường, có thể tạo side effect lặp; chỉ nên để container quản lý lifecycle.

Nếu cần giữ class không phụ thuộc Spring, hãy cân nhắc custom init method ở bean definition.

## 4. `@Bean(initMethod = "...")`

### 4.1. Cú pháp

`@Bean` thuộc `org.springframework.context.annotation.Bean`. Thuộc tính `initMethod` nhận **tên method của bean instance mà factory method trả về**.

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class FormatterConfig {

    @Bean(initMethod = "prepare")
    public ExternalFormatter externalFormatter() {
        return new ExternalFormatter("ORDER-");
    }
}
~~~

Class phụ thuộc:

~~~java
public class ExternalFormatter {
    private final String prefix;
    private boolean prepared;

    public ExternalFormatter(String prefix) {
        this.prefix = prefix;
    }

    public void prepare() {
        if (prefix == null || prefix.isBlank()) {
            throw new IllegalStateException("prefix missing");
        }
        prepared = true;
    }

    public String format(String value) {
        if (!prepared) {
            throw new IllegalStateException("formatter not initialized");
        }
        return prefix + value;
    }
}
~~~

Hai đoạn trên thuộc **hai file class trong cùng package**; khi đăng ký `FormatterConfig` vào một `ApplicationContext`, Spring gọi `externalFormatter()` để tạo object, sau đó gọi `prepare()` như custom init callback. Không cần viết `implements InitializingBean` trong `ExternalFormatter`.

Nên khai báo custom initialization là một instance method không tham số; ví dụ điển hình là `public void prepare()`. Tránh thiết kế method init phụ thuộc tham số nghiệp vụ: hãy inject chúng trước bằng constructor/setter/factory method rồi init dựa trên state đã có.

### 4.2. Method nào được Spring gọi?

Phân biệt hai method:

~~~java
@Bean(initMethod = "prepare")
public ExternalFormatter externalFormatter() { // Factory method
    return new ExternalFormatter("ORDER-");
}
~~~

- `externalFormatter()` thuộc **class cấu hình**: phương thức factory tạo và trả bean object.
- `prepare()` thuộc **ExternalFormatter instance**: initialization callback được Spring gọi **sau khi object đã được tạo và lắp ráp**.
- String `"prepare"` là tên method được lookup từ bean instance; không phải tên bean và không phải tên factory method.

Nếu factory method tự gọi `prepare()` rồi vẫn khai báo `initMethod = "prepare"`, nhiều khả năng cùng công việc chạy **hai lần**: một lần thủ công trong factory method và một lần khi Spring gọi init callback. Hãy chọn một nơi chịu trách nhiệm gọi.

### 4.3. Khác gì với `@PostConstruct`?

`@PostConstruct` đặt trực tiếp trên method của bean class:

~~~java
import jakarta.annotation.PostConstruct;

public class ExternalFormatter {
    @PostConstruct
    public void validate() {
        // Được gọi trong pha before initialization nếu processor được đăng ký.
    }
}
~~~

Đây là đoạn minh họa cho **một class khác hoặc phiên bản thay thế** của ví dụ; để chạy cần Jakarta Annotation API và processor tương ứng trong Spring context.

`@PostConstruct` có ích khi bạn sở hữu class và muốn khai báo lifecycle ngay tại class. `@Bean(initMethod)` có ích khi bạn muốn giữ class thuần Java hoặc class đến từ thư viện ngoài mà không thể thêm annotation vào source.

Trong Spring Framework 6.x, package tiêu chuẩn là `jakarta.annotation.PostConstruct`. Không import nhầm `javax.annotation.PostConstruct` từ ứng dụng đời cũ mà không kiểm tra khả năng tương thích.

## 5. Ví dụ hoàn chỉnh Java 17 + Spring Context 6.1: quan sát ba callback

Ví dụ này đặt toàn bộ Java code vào một file `LifecycleDemo.java`, dùng Maven để tải dependency. Nó chứng minh:

- `@Bean` factory method chạy khi container cần tạo bean.
- Constructor chạy khi Java object được tạo.
- `@PostConstruct` chạy trước `afterPropertiesSet()`.
- `afterPropertiesSet()` chạy trước `@Bean(initMethod = "open")`.
- Chỉ sau các callback đó, ta lấy bean đã ready từ context.
- Khi context đóng, custom destroy callback chạy.

### 5.1. Cấu trúc

~~~text
lifecycle-demo/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── com/
                └── example/
                    └── lifecycle/
                        └── LifecycleDemo.java
~~~

### 5.2. File `pom.xml`

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>com.example</groupId>
    <artifactId>lifecycle-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.1.13</version>
        </dependency>
        <dependency>
            <groupId>jakarta.annotation</groupId>
            <artifactId>jakarta.annotation-api</artifactId>
            <version>2.1.1</version>
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
                <version>3.3.0</version>
                <configuration>
                    <mainClass>com.example.lifecycle.LifecycleDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

### 5.3. File `src/main/java/com/example/lifecycle/LifecycleDemo.java`

~~~java
package com.example.lifecycle;

import jakarta.annotation.PostConstruct;
import org.springframework.beans.factory.InitializingBean;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

public class LifecycleDemo {

    public static void main(String[] args) {
        try (AnnotationConfigApplicationContext context =
                     new AnnotationConfigApplicationContext(Config.class)) {

            ManagedClient client = context.getBean(ManagedClient.class);
            System.out.println("5. Application uses ready bean: " + client.isReady());
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class Config {

        @Bean(initMethod = "open", destroyMethod = "shutdown")
        public ManagedClient managedClient() {
            System.out.println("0. @Bean factory method");
            return new ManagedClient("demo-endpoint");
        }
    }

    public static class ManagedClient implements InitializingBean {
        private final String endpoint;
        private boolean postConstructDone;
        private boolean afterPropertiesSetDone;
        private boolean ready;

        public ManagedClient(String endpoint) {
            this.endpoint = endpoint;
            System.out.println("1. Constructor");
        }

        @PostConstruct
        public void annotatedInit() {
            if (endpoint == null || endpoint.isBlank()) {
                throw new IllegalStateException("Endpoint is required");
            }
            postConstructDone = true;
            System.out.println("2. @PostConstruct");
        }

        @Override
        public void afterPropertiesSet() {
            if (!postConstructDone) {
                throw new IllegalStateException("@PostConstruct was not called");
            }
            afterPropertiesSetDone = true;
            System.out.println("3. InitializingBean.afterPropertiesSet");
        }

        public void open() {
            if (!afterPropertiesSetDone) {
                throw new IllegalStateException("Properties are not ready");
            }
            ready = true;
            System.out.println("4. @Bean(initMethod = open)");
        }

        public boolean isReady() {
            return ready;
        }

        public void shutdown() {
            ready = false;
            System.out.println("6. @Bean(destroyMethod = shutdown)");
        }
    }
}
~~~

`Config` được đăng ký bằng `AnnotationConfigApplicationContext(Config.class)`. Bean `ManagedClient` được tạo bởi method `managedClient()`. `AnnotationConfigApplicationContext` cũng đăng ký các annotation processors tiêu chuẩn; khi `jakarta.annotation.PostConstruct` có mặt trên classpath, callback `annotatedInit()` được xử lý bởi `CommonAnnotationBeanPostProcessor`.

Class `ManagedClient` là `static` nested class, vì vậy không phụ thuộc outer instance. Các method và import đều có trong file, không cần servlet, database hoặc kết nối mạng để chạy chương trình.

### 5.4. Lệnh chạy

Yêu cầu: JDK 17 trở lên, Maven 3.9.x. Từ thư mục `lifecycle-demo` chạy:

~~~bash
mvn -q compile exec:java
~~~

Những dòng `System.out.println` của chương trình, theo đúng thứ tự:

~~~text
0. @Bean factory method
1. Constructor
2. @PostConstruct
3. InitializingBean.afterPropertiesSet
4. @Bean(initMethod = open)
5. Application uses ready bean: true
6. @Bean(destroyMethod = shutdown)
~~~

Maven, logging framework và plugin có thể phát sinh log bên ngoài các dòng trên; đây là **stdout do các method trong ví dụ tạo ra**. Thứ tự này thể hiện rõ hai phương thức khởi tạo `afterPropertiesSet()` và `open()` được container gọi trước khi `context.getBean(...)` cung cấp bean hoàn tất initialization cho đoạn mã `main`.

### 5.5. Vì sao `shutdown()` chỉ chạy khi đóng context?

Ví dụ sử dụng `try-with-resources` vì `AnnotationConfigApplicationContext` implements `AutoCloseable`. Kết thúc block, `context.close()` được gọi tự động; với bean singleton và `destroyMethod = "shutdown"`, Spring thực thi custom destroy method. Trong ứng dụng chạy liên tục, destruction callback có thể chạy khi context được đóng, chẳng hạn lúc shutdown hợp lệ.

`initMethod` và `destroyMethod` là hai callback độc lập. Không suy ra bean prototype được container tự hủy ở cuối một request/công việc: Spring **không tự theo dõi để hủy prototype đã giao cho caller** như đối với singleton. Phạm vi bean ảnh hưởng số lần khởi tạo và nơi quản lý hủy.

## 6. So sánh hai cơ chế chính

| Tiêu chí | `InitializingBean.afterPropertiesSet()` | `@Bean(initMethod = "...")` |
| --- | --- | --- |
| Khai báo ở đâu? | Trong bean class bằng `implements InitializingBean` | Ở bean factory method/bean definition trong class cấu hình |
| Tên method | Cố định: `afterPropertiesSet()` | Tên tùy ý, dạng chuỗi trong `initMethod` |
| Dependency vào API Spring trong class | Có | Không bắt buộc |
| Có thể cấu hình cho class thư viện ngoài không sửa source? | Không trực tiếp | Có |
| Khi nào gọi? | Sau khi dependency/properties của instance được lắp ráp | Sau `afterPropertiesSet()` nếu có, cùng pha init |
| Validation bằng compiler | Bảo đảm implements method đúng interface | Chuỗi tên method không được compiler kiểm tra lúc build Java |
| Thường dùng cho | Bean do project sở hữu, muốn lifecycle contract tường minh | Bean từ thư viện, bean thuần Java, cấu hình init bên ngoài class |
| Có áp dụng cho `@Component` không? | Có, nếu class implements interface và được Spring quản lý | `@Bean(initMethod)` chỉ đặt trên `@Bean` method; với component có thể dùng `@PostConstruct` hoặc metadata khác |

**Không có quy tắc rằng phải luôn kết hợp cả hai.** Nếu chỉ cần xác thực dependency, chọn một callback là đủ. Kết hợp nhiều callback chỉ khi có lý do rõ ràng cho mỗi giai đoạn; tránh phân tán một giao thức khởi tạo qua quá nhiều method khó kiểm tra.

### Khác nhau giữa “factory tạo object” và “init hoàn tất object”

Ví dụ:

~~~java
@Bean(initMethod = "initialize")
public CacheIndex cacheIndex() {
    CacheIndex index = new CacheIndex();
    index.setCapacity(100);
    return index;
}
~~~

Spring gọi `cacheIndex()` để nhận object, sau đó gọi `initialize()` theo bean metadata. Đây là **đoạn minh họa**; class `CacheIndex` cần có constructor, setter và method `initialize()` tương ứng.

Nếu bạn viết:

~~~java
@Bean(initMethod = "initialize")
public CacheIndex cacheIndex() {
    CacheIndex index = new CacheIndex();
    index.setCapacity(100);
    index.initialize();
    return index;
}
~~~

Thì `initialize()` đã được gọi trong factory và sẽ lại được container gọi như init method. Không viết cả hai trừ khi method thật sự được thiết kế idempotent và có lý do gọi lặp (thường là dấu hiệu cấu hình sai).

## 7. Tính nhất quán: `@PostConstruct`, `afterPropertiesSet` và custom init

Khi kết hợp ba cách trên, chúng phải có **tên method riêng biệt** để các trách nhiệm rõ ràng:

~~~java
public class IndexBuilder implements InitializingBean {
    @PostConstruct
    public void validateConfiguration() {
        // 1. Kiểm tra giá trị đã inject.
    }

    @Override
    public void afterPropertiesSet() {
        // 2. Tính cấu trúc dữ liệu dựa trên cấu hình.
    }

    public void warmUp() {
        // 3. Chuẩn bị dữ liệu cần thiết để phục vụ request.
    }
}
~~~

Cấu hình:

~~~java
@Bean(initMethod = "warmUp")
public IndexBuilder indexBuilder() {
    return new IndexBuilder();
}
~~~

Hai đoạn trên minh họa cách khai báo cùng một bean; để chạy cần import `InitializingBean`, `PostConstruct` và `Bean`, cùng context hỗ trợ annotation. Spring bảo đảm thứ tự **`validateConfiguration()` → `afterPropertiesSet()` → `warmUp()`** trong trường hợp callback được đăng ký thành công và không ném exception.

Nếu một method được khai báo trùng tên theo nhiều cơ chế lifecycle, Spring có xử lý chống gọi trùng theo hợp đồng lifecycle; tuy nhiên đừng dùng điều đó để tạo cấu hình khó đọc. Tốt hơn là **không gán một method vừa làm `@PostConstruct`, vừa được khai báo là `initMethod`**.

### Khi nào class không nên implements `InitializingBean`?

Đối với domain model hoặc thư viện độc lập Spring, tách hành vi khởi tạo thành method thuần:

~~~java
public class RuleEngine {
    public void prepare() {
        // Logic thuần Java, không phụ thuộc framework.
    }
}
~~~

Sau đó gắn method vào bean definition:

~~~java
@Bean(initMethod = "prepare")
public RuleEngine ruleEngine() {
    return new RuleEngine();
}
~~~

Thiết kế này vẫn cho phép test class bằng `new RuleEngine()` trong unit test, bằng cách gọi `prepare()` rõ ràng. Spring chỉ tự kích hoạt method khi object được container tạo như bean.

## 8. Vòng đời phụ thuộc scope và lazy initialization

### 8.1. Singleton mặc định

Một bean singleton non-lazy thường được Spring khởi tạo trong quá trình refresh context. Do đó `afterPropertiesSet()` và custom `initMethod` thường chạy khi ứng dụng khởi động. Các lần gọi `getBean(...)` sau đó trả singleton đã khởi tạo; chúng **không lặp lại init callback**.

~~~java
@Bean(initMethod = "initialize")
public ServiceRegistry serviceRegistry() {
    return new ServiceRegistry();
}
~~~

Đây là ví dụ minh họa; class `ServiceRegistry` có method `initialize()` không tham số. Việc gọi `context.getBean(ServiceRegistry.class)` 100 lần không khiến `initialize()` tự chạy 100 lần nếu chỉ có một singleton bean definition trong context đó.

### 8.2. Prototype

Với prototype, mỗi lần container được yêu cầu cung cấp target mới thì tạo một instance mới và thực hiện initialization trên instance đó:

~~~java
@Bean(initMethod = "prepare")
@Scope(ConfigurableBeanFactory.SCOPE_PROTOTYPE)
public WorkSession workSession() {
    return new WorkSession();
}
~~~

Bean này yêu cầu import `Scope` và `ConfigurableBeanFactory`; class `WorkSession` phải có method `prepare()`. Nếu gọi `context.getBean(WorkSession.class)` hai lần, Spring khởi tạo hai object khác nhau và `prepare()` chạy cho từng object.

**Lưu ý:** Spring không tự thực hiện destroy callbacks cho prototype sau khi giao object. Nếu `prepare()` mở resource cần đóng, phía lấy prototype cần chủ động quản lý resource và cleanup, ví dụ dùng `AutoCloseable` khi phù hợp.

### 8.3. Lazy singleton

~~~java
@Bean(initMethod = "prepare")
@Lazy
public ExpensiveIndex expensiveIndex() {
    return new ExpensiveIndex();
}
~~~

Đây là đoạn minh họa cần import `Lazy` và class `ExpensiveIndex` tương ứng. Khi lazy singleton thực sự được tạo lần đầu, callback mới chạy. Tuy nhiên nếu một non-lazy singleton khác cần dependency này trong quá trình startup, Spring vẫn có thể tạo nó sớm để thỏa mãn dependency.

**Phân biệt:** Scope quyết định *bao nhiêu instance*, còn lazy initialization quyết định *khi nào instance được tạo*. Callback chạy theo quá trình tạo instance, không theo mỗi lần sử dụng một method thông thường.

### 8.4. Request/session và scoped bean

Callback initialization của một request-scoped hoặc session-scoped target diễn ra khi target thật được tạo trong scope tương ứng, không phải chỉ bởi việc singleton giữ một scoped proxy. Với `@RequestScope`, mỗi request có thể tạo target riêng và chạy init callback riêng.

Nếu init method của singleton cố lấy request-scoped target ngay tại startup khi request scope chưa active, có thể dẫn tới `ScopeNotActiveException`. Đừng mở HTTP request giả hoặc thay đổi scope toàn cục chỉ để cho callback chạy: tách việc khởi tạo vào đúng ngữ cảnh.

## 9. Lỗi thường gặp với `@Bean(initMethod)`

### 9.1. Method không tồn tại hoặc sai tên

~~~java
@Bean(initMethod = "intialize") // Sai chính tả: thiếu chữ "i".
public WorkerClient workerClient() {
    return new WorkerClient();
}
~~~

Nếu class `WorkerClient` chỉ có method `initialize()` thì configuration trỏ đến method khác tên. Spring có thể thất bại khi tạo bean, với cause phản ánh việc không tìm thấy init method hợp lệ.

Vì `initMethod` là **chuỗi ký tự**, IDE không phải lúc nào cũng bắt lỗi này lúc compile. Khi đổi tên method, nhớ sửa bean definition và có integration test khởi tạo context.

### 9.2. Method init yêu cầu tham số nghiệp vụ

~~~java
public void initialize(String path) {
    // Method này không phù hợp cho initMethod chỉ định theo tên.
}
~~~

Custom init method theo cấu hình nên là **method không tham số**. Truyền `path` vào constructor hoặc qua dependency:

~~~java
public WorkerClient(String path) {
    this.path = path;
}

public void initialize() {
    // Dùng this.path đã có.
}
~~~

Hai đoạn là minh họa cho cùng một class `WorkerClient` có field `path` và các import/cấu hình liên quan.

### 9.3. Không đăng ký bean với Spring

~~~java
WorkerClient client = new WorkerClient("logs");
client.doWork();
~~~

Đoạn này tạo object bằng Java `new`. Spring không tự nhìn thấy instance nên **không chạy** `InitializingBean.afterPropertiesSet()` hoặc `@Bean(initMethod)` cho object ấy. Nếu muốn Spring quản lý initialization, phải lấy bean qua Spring context/bean definition thay vì tự tạo rồi mong callback tự chạy.

### 9.4. Gọi method khởi tạo thủ công hai lần

~~~java
@Bean(initMethod = "initialize")
public WorkerClient workerClient() {
    WorkerClient client = new WorkerClient("logs");
    client.initialize(); // Gọi thủ công lần 1.
    return client;        // Spring gọi lần 2 theo initMethod.
}
~~~

Đoạn này minh họa **anti-pattern**. Khi initialization có side effect như tạo kết nối, đăng ký listener hoặc ghi dữ liệu, gọi hai lần có thể gây rò tài nguyên, tạo duplicate registration hoặc thay đổi state khó dự đoán.

### 9.5. Callback ném exception nhưng root cause bị che khuất

Một số thông báo xuất hiện dưới dạng `BeanCreationException`, `UnsatisfiedDependencyException` hoặc lỗi refresh context. Lần theo `Caused by` đến exception được ném bên trong `afterPropertiesSet()` hoặc custom init method.

Không xử lý bằng cách bắt toàn bộ exception rồi im lặng để container giữ một bean chưa sẵn sàng. Nếu bean bắt buộc phải có cấu hình hợp lệ, **fail fast với lỗi rõ ràng** thường an toàn hơn.

### 9.6. Dùng callback để làm việc dài hoặc phụ thuộc startup toàn hệ thống

Không khuyến nghị chạy một công việc hàng phút, gọi API mạng thiếu timeout hoặc khởi chạy vô hạn background thread trực tiếp trong `afterPropertiesSet()`. Điều này trì hoãn việc tạo bean/container và làm khó shutdown.

Tùy bài toán, hãy phân biệt:

- Khởi tạo **nội bộ bean**: `@PostConstruct`, `afterPropertiesSet`, custom `initMethod`.
- Hành vi **sau khi Spring Boot application đã tạo context**: cân nhắc `ApplicationRunner`/`CommandLineRunner` (nếu sử dụng Boot).
- Quản lý start/stop service nền theo vòng đời application context: `Lifecycle`/`SmartLifecycle` khi phù hợp.

Đây là các hợp đồng có mục đích khác nhau. Không đồng nhất `afterPropertiesSet()` với “ứng dụng hoàn toàn ready để phục vụ tất cả request”.

## 10. Khi bean dùng dependency đã inject

Một use case phù hợp là object được tạo bởi `@Bean` cần dependency ở constructor, sau đó khởi tạo cấu trúc dùng dependency ấy.

~~~java
public class PriceRuleIndex {
    private final RuleRepository repository;
    private List<String> rules;

    public PriceRuleIndex(RuleRepository repository) {
        this.repository = repository;
    }

    public void rebuild() {
        this.rules = List.copyOf(repository.loadRuleNames());
    }

    public List<String> rules() {
        return rules;
    }
}
~~~

Cấu hình:

~~~java
@Configuration(proxyBeanMethods = false)
class PriceRuleConfig {

    @Bean(initMethod = "rebuild")
    PriceRuleIndex priceRuleIndex(RuleRepository repository) {
        return new PriceRuleIndex(repository);
    }
}
~~~

Đây là **mã ghép minh họa**, không phải chương trình độc lập: cần interface `RuleRepository` với `loadRuleNames()`, các import Java/Spring và một implementation của repository được Spring đăng ký.

Spring resolve `RuleRepository` vào tham số `priceRuleIndex(...)` trước khi tạo index. Sau khi factory method trả index, Spring gọi `rebuild()` để tạo snapshot. Nếu method `rebuild()` throw exception, bean creation thất bại.

Cần cân nhắc ứng dụng thực tế: nếu `repository.loadRuleNames()` gọi database/network trong startup thì cần timeout, retry policy và yêu cầu sẵn sàng của hạ tầng. Init callback không phải transaction boundary mặc định; nếu cần cơ chế transaction/AOP, phải kiểm tra lúc proxy được tạo và cách tương tác với service tương ứng.

### Vì sao không gọi transaction-proxied method bằng `this` trong init?

Các lifecycle callbacks ban đầu làm việc với bean target trước khi một số AOP proxy được hoàn thiện. Lời gọi `this.transactionalMethod()` trong `afterPropertiesSet()` không thể dựa vào advice `@Transactional` của proxy ngoài.

Nếu init cần nghiệp vụ giao dịch, tách phần đó sang một component đã được container quản lý ở thời điểm phù hợp, hoặc sử dụng API programmatic như `TransactionTemplate` theo thiết kế transaction, thay vì giả định self-invocation đi qua proxy.

## 11. Phân biệt callback với `BeanPostProcessor`

`InitializingBean` là một **interface do chính bean triển khai**, còn `BeanPostProcessor` là extension point áp dụng xử lý tới những bean khác.

Hai method tổng quát:

~~~java
Object postProcessBeforeInitialization(Object bean, String beanName);
Object postProcessAfterInitialization(Object bean, String beanName);
~~~

Đây là chữ ký ý tưởng của `BeanPostProcessor`; trong API có khai báo mặc định và nullable contract theo phiên bản, vì vậy đoạn trên chỉ minh họa vị trí xử lý, không phải định nghĩa interface đầy đủ.

Đối với một bean bình thường:

1. Spring gọi các `BeanPostProcessor.postProcessBeforeInitialization(...)`.
2. Một processor xử lý `@PostConstruct` khi có.
3. Spring gọi `InitializingBean.afterPropertiesSet()`.
4. Spring gọi custom init method từ bean definition.
5. Spring gọi các `BeanPostProcessor.postProcessAfterInitialization(...)`.

Trong thực tế có thứ tự và cơ chế nội bộ của nhiều processors; mục tiêu ở đây là phân biệt trách nhiệm. Đừng tự gọi `afterPropertiesSet()` bên trong `BeanPostProcessor` nếu container sẽ tự gọi, tránh duplicate callback.

Nếu cần kiểm tra toàn bộ pipeline, hãy viết integration test có một processor log event và assert thứ tự theo hành vi mong muốn; trong bài này ví dụ `LifecycleDemo` đã chứng minh thứ tự ba initialization mechanisms.

## 12. Cách kiểm thử initialization hiệu quả

### 12.1. Test contract của chính class

Với bean thuần Java, tạo object và gọi custom init method để kiểm thử validation hoặc state nội bộ:

~~~java
ExternalFormatter formatter = new ExternalFormatter("ORDER-");
formatter.prepare();
System.out.println(formatter.format("42"));
~~~

Output của ví dụ class ở mục 4:

~~~text
ORDER-42
~~~

Đoạn chạy cần class `ExternalFormatter` đúng theo mẫu mục 4. Nó là test hành vi Java thuần, **không** chứng minh Spring tự gọi `prepare()`.

### 12.2. Test thực tế qua Spring container

Để kiểm tra `@Bean(initMethod)` thực sự được cấu hình, khởi tạo `AnnotationConfigApplicationContext` chứa class `@Configuration`, gọi `getBean(...)` rồi assert trạng thái:

~~~java
try (var context =
         new AnnotationConfigApplicationContext(FormatterConfig.class)) {
    ExternalFormatter bean = context.getBean(ExternalFormatter.class);
    if (!"ORDER-42".equals(bean.format("42"))) {
        throw new AssertionError("Initialization callback did not run");
    }
}
~~~

Đoạn trên là phần code có thể đặt trong `main` hoặc test method và cần import `AnnotationConfigApplicationContext`. Nó dùng `FormatterConfig` và `ExternalFormatter` ở mục 4.

### 12.3. Kiểm tra số lần gọi

Với một singleton bean, initialization chỉ xảy ra **khi instance được tạo**, không phải sau mỗi `getBean()`. Đối với prototype, mỗi instance do Spring tạo có vòng đời initialization riêng.

Nếu muốn test số lần gọi mà không phụ thuộc log, tạo class `CounterBean` với một field đếm trong init callback và assert. Tuy nhiên tránh dùng `static` counter dùng chung nhiều test/context nếu không reset đúng cách; nó có thể khiến test không độc lập.

### 12.4. Kiểm tra failure path

Tạo một bean với cấu hình thiếu bắt buộc, ví dụ blank endpoint trong `afterPropertiesSet()`, rồi khởi tạo context và assert nó thất bại với cause có ý nghĩa. Điều này hữu ích hơn chỉ kiểm tra “context starts” vì xác nhận chính sách **fail fast** khi cấu hình sai.

## 13. Câu hỏi hay gặp

**Vì sao dùng `@Bean(initMethod)` khi đã có constructor?**

Constructor nên bảo đảm object được tạo hợp lệ và gán các dependency bắt buộc. Custom init hữu ích khi cần thực hiện một bước riêng **sau khi Spring đã lắp ráp bean**, nhất là với setter injection hoặc bean class của thư viện ngoài. Nếu logic đơn giản và có đủ dữ liệu trong constructor, không cần thêm init callback.

**`afterPropertiesSet()` có được gọi sau khi “mọi bean trong toàn ứng dụng” đã sẵn sàng không?**

Không. Nó đảm bảo quá trình lắp ráp **bean hiện tại** đã đến pha initialization. Nhiều bean khác có thể chưa được tạo, đặc biệt lazy bean. Không dùng method này làm tín hiệu toàn ứng dụng đã ready.

**Nếu class implements `InitializingBean` nhưng được tạo bằng `new` thì sao?**

Chỉ là object Java. Method `afterPropertiesSet()` không tự chạy. Phải có một bean factory của Spring trực tiếp quản lý instance qua bean definition và thực hiện lifecycle.

**`@Bean(initMethod)` có dùng được trên `@Component` class không?**

Không đặt `@Bean(initMethod)` lên class; `@Bean` là annotation của **method tạo bean**. Với component class, thường dùng `@PostConstruct` hoặc implements `InitializingBean`. Custom init name cũng có thể khai báo qua bean definition programmatic/XML nếu thiết kế yêu cầu.

**Nếu class vừa có `@PostConstruct`, vừa `InitializingBean`, vừa custom `initMethod` thì thứ tự ra sao?**

`@PostConstruct` trước, tiếp đó `afterPropertiesSet()`, cuối cùng custom init method, với điều kiện các callback đã được đăng ký và có tên khác nhau.

**Callback có chạy qua Spring AOP proxy hay `@Transactional` không?**

Không nên giả định như vậy. Initialization thường chạy trên target trước khi proxy AOP hoàn tất. Nếu logic init cần transaction, tổ chức luồng thực thi phù hợp với thời điểm proxy và transaction manager hoạt động.

**Có thể dùng `@Bean(initMethod)` để tự tạo connection pool không?**

Có thể cấu hình callback cho class bên thứ ba, nhưng hầu hết thư viện/framework pool đã có vòng đời và factory config riêng. Phải hiểu ownership và destroy callback để tránh mở pool hai lần hoặc không đóng tài nguyên đúng lúc.

## 14. Các lỗi thường gặp và hướng khắc phục

| Biểu hiện | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| `afterPropertiesSet()` không chạy | Class bị tạo bằng `new` hoặc chưa được đăng ký bean | Đăng ký vào Spring context và lấy từ container |
| Spring báo không tìm thấy init method | Sai chuỗi `initMethod` hoặc method không có chữ ký phù hợp | Kiểm tra tên, tham số, accessibility và bean class thực tế |
| Callback chạy hai lần | Factory method gọi init thủ công rồi khai báo `initMethod` | Để Spring gọi một lần; tránh trùng trách nhiệm |
| Exception lúc context startup | Init callback throw exception trên eager singleton | Đọc root cause, kiểm tra cấu hình và dependency |
| Lỗi chỉ xuất hiện ở lần `getBean()` đầu tiên | Bean `@Lazy` | Test cả đường truy xuất lazy |
| Kết quả init khác giữa các lần lấy prototype | Mỗi lookup tạo và init một instance mới | Xem lại scope nếu kỳ vọng dùng chung |
| `@Transactional` không có tác dụng trong init | Target chưa đi qua proxy hoặc gọi self-invocation | Tách logic transactional sang luồng phù hợp |
| Bean giữ socket/file sau khi context đóng | Thiếu cleanup hoặc dùng prototype và kỳ vọng container hủy | Dùng destroy lifecycle với singleton hoặc cleanup thủ công với prototype |
| Một bean cần bean khác “đã hoàn tất startup” | Coi init callback là global startup hook | Dùng cơ chế startup orchestration phù hợp, tránh dependency ngầm |
| `@PostConstruct` không chạy | Thiếu processor/annotation dependency hoặc import API sai | Kiểm tra `jakarta.annotation` và Spring bean post-processing |

## 15. Checklist áp dụng trong dự án thực tế

Trước khi thêm lifecycle initialization, tự kiểm tra:

1. **Bean do Spring quản lý?** Nếu chỉ tạo bằng `new`, callback của Spring không tự chạy.
2. **Cần hook sau injection thật không?** Nếu constructor đã đủ, hãy giữ logic trong constructor.
3. **Đã chọn một cơ chế rõ ràng?** `InitializingBean` khi chấp nhận phụ thuộc Spring; `@Bean(initMethod)` khi muốn class thuần hoặc thư viện ngoài.
4. **Init callback có idempotent không?** Không nên vô tình đăng ký hai cơ chế hoặc gọi thủ công lặp.
5. **Dependency cần thiết đã được inject?** Xác thực state và fail fast bằng thông báo rõ ràng.
6. **Có I/O ngoài process không?** Đặt timeout và chính sách lỗi, tránh startup treo vô hạn.
7. **Có phụ thuộc AOP/transaction không?** Nhớ callback chạy trong lifecycle trước khi proxy cuối cùng được trả.
8. **Scope là gì?** Singleton, prototype, lazy, request/session đều quyết định khi nào và bao nhiêu lần initialization diễn ra.
9. **Ai cleanup tài nguyên?** Cấu hình destroy method phù hợp, đặc biệt nếu bean thuộc prototype.
10. **Đã có test thực sự tạo Spring context?** Unit test gọi init thủ công không thay thế được test annotation/bean definition.

## 16. Tài liệu chính thức

- [Spring Framework — Customizing the Nature of a Bean](https://docs.spring.io/spring-framework/reference/core/beans/factory-nature.html): initialization callbacks, `InitializingBean`, custom init method và thứ tự khi kết hợp lifecycle mechanisms.
- [Spring Framework 6.1 — `InitializingBean` Javadoc](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/beans/factory/InitializingBean.html): API và ý nghĩa `afterPropertiesSet()`.
- [Spring Framework 6.1 — `@Bean` Javadoc](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/context/annotation/Bean.html): `initMethod` và `destroyMethod`.
- [Spring Framework — Using the `@Bean` Annotation](https://docs.spring.io/spring-framework/reference/core/beans/java/bean-annotation.html): cách factory method đăng ký bean definition.
- [Spring Framework — Bean Scopes](https://docs.spring.io/spring-framework/reference/core/beans/factory-scopes.html): khác biệt lifecycle theo singleton, prototype và các scope khác.
