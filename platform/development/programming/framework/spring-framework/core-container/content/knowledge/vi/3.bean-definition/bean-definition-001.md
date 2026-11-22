# BeanDefinition mô tả cách tạo và quản lý một bean — Spring Framework Core Container

## 1. Mục tiêu bài học

Khi nhìn một đoạn Spring `@Bean` hoặc `@Component`, bạn có thể tưởng container chỉ “thấy annotation rồi gọi `new`”. Thực tế, Spring trước hết đăng ký **thông tin mô tả một bean** để biết *bean tên gì, có thể tạo bằng cách nào, nhận dependency nào, có scope/lifecycle ra sao*. Bản mô tả đó được biểu diễn bằng giao diện **`BeanDefinition`** trong Spring IoC container.

`BeanDefinition` không phải object nghiệp vụ. Nó là **metadata/công thức** mà `BeanFactory` dùng khi tạo và quản lý bean. Việc Spring biết metadata của một bean **không đồng nghĩa** bean instance đã tồn tại.

Kết thúc bài, bạn có thể:

1. Giải thích đúng quan hệ giữa `BeanDefinition`, `BeanDefinitionRegistry`, `BeanFactory`, `ApplicationContext` và bean instance.
2. Đọc các trường metadata quan trọng: bean name, class/factory method, scope, lazy initialization, dependency, init/destroy callbacks, constructor/property values.
3. Phân biệt *đăng ký definition*, *giải quyết dependency*, *tạo instance*, *khởi tạo* và *hủy bean*.
4. Hiểu vì sao `@Bean` và component scanning cũng tạo definition, không chỉ các thao tác đăng ký bằng API.
5. Chạy một ví dụ **Spring Framework thuần + Java 17** có cả `@Configuration`/`@Bean` và `BeanDefinitionBuilder` để quan sát metadata, singleton/prototype, injection và callback hủy.
6. Biết khi nào đăng ký bean definitions bằng API, và tránh các lỗi liên quan tên, kiểu, scope, thời điểm đăng ký, truy cập metadata.

**Phạm vi:** Đây là bài về **ý nghĩa và cách dùng BeanDefinition ở Core Container**. Không cần Spring Boot, server web, AOP, database hoặc tự viết BeanFactory để hiểu được nó.

## 2. Bốn đối tượng/cơ chế dễ nhầm

| Khái niệm | Nó là gì? | Câu hỏi trả lời |
| --- | --- | --- |
| `BeanDefinition` | Metadata/cấu hình mô tả cách Spring tạo và quản lý bean | “Bean này được định nghĩa thế nào?” |
| `BeanDefinitionRegistry` | Nơi đăng ký, tra cứu, xóa định nghĩa bean theo tên | “Container có những definition nào?” |
| `BeanFactory` | Cơ chế truy xuất/tạo/resolve bean theo quy tắc Spring | “Khi cần bean, làm sao có instance phù hợp?” |
| Bean instance | Object Java thật do container quản lý theo definition/scope | “Dịch vụ đang dùng object nào?” |
| `ApplicationContext` | Giao diện container cấp cao với registration, lifecycle, event, môi trường... tùy implementation | “Ứng dụng khởi động và làm việc với toàn bộ context thế nào?” |

Ví dụ hai tầng:

~~~text
Metadata:
  Bean name: "greetingService"
  Factory:   AppConfig.greetingService(TextFormatter)
  Scope:     singleton (mặc định)
  Depends:   TextFormatter

Runtime:
  Bean instance: GreetingService #1
     |
     +-- field formatter -> UppercaseFormatter #1
~~~

**Không phải một BeanDefinition = một object trong mọi scope.** Một định nghĩa singleton thông thường tương ứng một instance trong container; một definition prototype có thể tạo nhiều object khi mỗi lần được yêu cầu.

**Không phải mọi object Java là Spring bean.** Nếu trong method nghiệp vụ có `new StringBuilder()` hay `new Helper()`, object đó không tự nhiên trở thành managed bean chỉ vì được tạo trong ứng dụng Spring.

### Tưởng tượng BeanDefinition là công thức

- Công thức ghi: cần nguyên liệu nào, cách thực hiện, số lần tạo, bước dọn dẹp.
- Bean instance là kết quả thực tế khi công thức được áp dụng.
- BeanFactory là bộ máy sử dụng công thức để cung cấp kết quả.
- Registry giữ các công thức dưới tên phân biệt.

Phép so sánh này giúp hiểu mô hình, nhưng nhớ rằng **container còn có cơ chế mở rộng**, post-processors, factory methods, proxies, scopes và nhiều quy tắc lựa chọn bean. Không suy ra quá trình tạo mọi bean chỉ bằng một thao tác `new` đơn giản.

## 3. BeanDefinition lưu thông tin gì?

Các thuộc tính điển hình (không phải tất cả bắt buộc có giá trị không rỗng):

| Nhóm metadata | Ví dụ | Dùng để làm gì? |
| --- | --- | --- |
| Bean name | `"greetingService"` | Registry/lookup dùng làm khóa đăng ký; **tên thường được quản lý bởi registry**, không phải một field bean name cố định bên trong mọi `BeanDefinition` |
| Bean class hoặc cách tạo | `HealthProbe.class` hoặc factory method `greetingService` | Chỉ dẫn Spring khởi tạo/nhận object |
| Scope | `singleton`, `prototype` | Quy tắc giữ/dùng lại instance hoặc tạo theo yêu cầu |
| Lazy initialization | `true/false` | Có hoãn tạo bean cho tới lúc cần hay không, theo ngữ cảnh |
| Constructor arguments | Các giá trị hoặc bean references | Cung cấp tham số khi constructor được sử dụng |
| Property values | Giá trị cho setter/property phù hợp | Cấu hình instance sau khi tạo |
| Depends-on | `@DependsOn("bootstrap")` | Ràng buộc khởi tạo/hủy có chủ đích theo tên bean |
| Autowire candidate / primary | Quy tắc ứng viên injection | Giúp container chọn collaborator khi có nhiều lựa chọn |
| Init/destroy method | `init`, `shutdown` | Lifecycle callbacks khi bean được tạo/hủy phù hợp |
| Role/source/description | Metadata về nguồn khai báo | Hỗ trợ tooling, chẩn đoán hoặc infrastructure |

**Điều quan trọng:** `BeanDefinition` hỗ trợ nhiều **hình thức tạo bean**. Với method `@Bean`, Spring có thể ghi **factory bean/factory method** thay vì một bean class thông thường. Vì vậy đừng giả sử `getBeanClassName()` của mọi definition đều là tên class instance thực tế. Với `FactoryBean` hoặc proxy, thông tin kiểu runtime có thể phức tạp hơn.

### Mặc định scope không nhất thiết được ghi thành chữ singleton

Khi một definition không ghi scope tường minh, `BeanDefinition.getScope()` có thể chứa chuỗi rỗng/metadata mặc định tùy đường đăng ký. Spring **hiểu scope mặc định là singleton** cho bean ứng dụng thông thường. Đừng dùng kiểm tra `"singleton".equals(def.getScope())` để kết luận mọi bean mặc định không phải singleton.

Trong chương trình runnable, ta dùng:

~~~java
context.isSingleton("greetingService");
context.isPrototype("healthProbe");
~~~

Đây là **snippet** lấy từ một chương trình có biến `context` hợp lệ. Hai method trên hỏi về **scope thực tế của bean theo container**; `getScope()` vẫn hữu ích để đọc giá trị cấu hình tường minh trong metadata.

### Constructor injection và metadata

Với:

~~~java
@Bean
GreetingService greetingService(TextFormatter formatter) {
    return new GreetingService(formatter);
}
~~~

Spring ghi nhận factory method và phải **resolve một bean `TextFormatter`** để truyền vào tham số khi tạo `GreetingService`. Điều đó khác việc code gọi trực tiếp `greetingService(new UppercaseFormatter())` như phương thức Java thường. BeanDefinition hướng dẫn container làm việc; constructor vẫn là cơ chế Java bình thường.

## 4. BeanDefinition từ đâu xuất hiện?

Ba con đường phổ biến:

**(A) Java configuration:** Spring xử lý các method có `@Bean` trong một lớp cấu hình được đăng ký, từ đó sinh bean definitions cho factory methods.

~~~java
@Configuration(proxyBeanMethods = false)
class AppConfig {
    @Bean
    TextFormatter textFormatter() {
        return new UppercaseFormatter();
    }
}
~~~

**(B) Component scanning:** `@Component`, `@Service`, `@Repository` và các stereotype được scan theo cấu hình phù hợp cũng được chuyển thành bean definitions. Annotation trên một class ở package không được quét **không** tự động làm class đó xuất hiện trong context.

**(C) Đăng ký bằng code:** gọi `registerBeanDefinition(beanName, definition)` trên registry/container hỗ trợ. Bạn tạo metadata bằng `BeanDefinitionBuilder`, `RootBeanDefinition` hoặc các API phù hợp rồi đăng ký dưới tên rõ ràng.

~~~java
BeanDefinition definition = BeanDefinitionBuilder
        .genericBeanDefinition(HealthProbe.class)
        .setScope(BeanDefinition.SCOPE_PROTOTYPE)
        .setLazyInit(true)
        .getBeanDefinition();

context.registerBeanDefinition("healthProbe", definition);
~~~

Đây là **snippet**, cần import và các class ở ví dụ chạy đầy đủ bên dưới. Nó không gọi `new HealthProbe()`; nó chỉ đăng ký công thức. Khi bean prototype được yêu cầu, Spring mới sử dụng definition để tạo object.

~~~mermaid
flowchart TD
    A["Nguồn metadata"] --> B["BeanDefinitionRegistry"]
    A1["@Bean / JavaConfig"] --> A
    A2["@ComponentScan"] --> A
    A3["Đăng ký bằng API"] --> A
    B --> C["BeanDefinition metadata"]
    C --> D["BeanFactory: resolve và create"]
    D --> E["Bean instance"]
    E --> F["Init / sử dụng / destruction theo scope"]
~~~

**Lưu ý thứ tự:** Các thay đổi đăng ký/metadata cho ứng dụng cần được thực hiện **trước khi context refresh** (hoặc tại extension point được thiết kế cho việc đó). Đăng ký động sau khi bean đã được tạo không tự tái khởi tạo các singleton cũ và dễ dẫn đến trạng thái khó dự đoán.

## 5. Chương trình Java 17+ chạy độc lập

Đây là ví dụ Spring Framework Core Container thuần sử dụng **JDK 17+, Maven và `spring-context` phiên bản `6.2.19`** (ghim cho tính tái lập, không phải khẳng định mới nhất). Không cần Spring Boot hoặc server web.

Ứng dụng có ba bean từ `@Bean`:

- `textFormatter`: một `TextFormatter` được triển khai bởi `UppercaseFormatter`.
- `greetingService`: một service nhận `TextFormatter` qua tham số factory method.
- `traceSink`: một bean có method `shutdown` để Spring gọi khi context đóng.

Một bean khác `healthProbe` được đăng ký **bằng API**, cấu hình `prototype` và `lazyInit=true`. Ta sẽ kiểm tra **definition metadata và scope** trước/sau khi lấy instance.

~~~text
bean-definition-demo/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── demo/
                └── BeanDefinitionDemo.java
~~~

### 5.1. File `pom.xml`

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>bean-definition-demo</artifactId>
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
                    <mainClass>demo.BeanDefinitionDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Chỉ cần khai báo trực tiếp `spring-context` trong `pom.xml`; Maven sẽ giải quyết thêm những dependency transitively cần thiết. `spring-beans` (nơi định nghĩa `BeanDefinition` và `BeanDefinitionBuilder`) được kéo về qua phụ thuộc của Spring Context.

### 5.2. File `src/main/java/demo/BeanDefinitionDemo.java`

~~~java
package demo;

import java.util.Locale;
import java.util.Objects;

import org.springframework.beans.factory.config.BeanDefinition;
import org.springframework.beans.factory.support.BeanDefinitionBuilder;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

public final class BeanDefinitionDemo {
    private BeanDefinitionDemo() {}

    public interface TextFormatter {
        String normalize(String input);
    }

    public static final class UppercaseFormatter
            implements TextFormatter {
        @Override
        public String normalize(String input) {
            return input.strip().toUpperCase(Locale.ROOT);
        }
    }

    public static final class GreetingService {
        private final TextFormatter formatter;

        public GreetingService(TextFormatter formatter) {
            this.formatter = Objects.requireNonNull(formatter);
        }

        public String greet(String name) {
            return "HELLO " + formatter.normalize(name);
        }

        public TextFormatter formatter() {
            return formatter;
        }
    }

    public static final class HealthProbe {
        public HealthProbe() {}
    }

    public static final class TraceSink {
        public void shutdown() {
            System.out.println("destroy=traceSink");
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class AppConfig {
        @Bean
        public TextFormatter textFormatter() {
            return new UppercaseFormatter();
        }

        @Bean
        public GreetingService greetingService(TextFormatter formatter) {
            return new GreetingService(formatter);
        }

        @Bean(destroyMethod = "shutdown")
        public TraceSink traceSink() {
            return new TraceSink();
        }
    }

    public static void main(String[] args) {
        AnnotationConfigApplicationContext context =
                new AnnotationConfigApplicationContext();

        try (context) {
            context.register(AppConfig.class);

            BeanDefinition probeDefinition = BeanDefinitionBuilder
                    .genericBeanDefinition(HealthProbe.class)
                    .setScope(BeanDefinition.SCOPE_PROTOTYPE)
                    .setLazyInit(true)
                    .getBeanDefinition();

            context.registerBeanDefinition("healthProbe", probeDefinition);
            context.refresh();

            BeanDefinition serviceDefinition = context.getBeanFactory()
                    .getBeanDefinition("greetingService");
            BeanDefinition savedProbeDefinition = context.getBeanFactory()
                    .getBeanDefinition("healthProbe");

            System.out.println("serviceDefinition=" +
                    context.containsBeanDefinition("greetingService"));
            System.out.println("factoryMethod=" +
                    serviceDefinition.getFactoryMethodName());
            System.out.println("serviceSingleton=" +
                    context.isSingleton("greetingService"));
            System.out.println("probePrototype=" +
                    context.isPrototype("healthProbe"));
            System.out.println("probeLazyMetadata=" +
                    savedProbeDefinition.isLazyInit());

            HealthProbe first = context.getBean(HealthProbe.class);
            HealthProbe second = context.getBean(HealthProbe.class);
            System.out.println("differentProbes=" + (first != second));

            GreetingService service = context.getBean(GreetingService.class);
            TextFormatter formatter = context.getBean(TextFormatter.class);
            System.out.println("injectedSame=" +
                    (service.formatter() == formatter));
            System.out.println("greeting=" + service.greet(" Lan "));
        }

        System.out.println("afterActive=" + context.isActive());
    }
}
~~~

**Vì sao ví dụ đáng học:**

- `context.register(AppConfig.class)` chỉ ra nguồn JavaConfig; `context.registerBeanDefinition("healthProbe", ...)` đưa metadata đăng ký bằng code vào cùng registry **trước `refresh()`**.
- `BeanDefinitionBuilder` tạo mô tả bean `HealthProbe` chứ **không tạo HealthProbe instance** ngay trong câu lệnh.
- `serviceDefinition.getFactoryMethodName()` trả tên method `@Bean`: `greetingService`. Đừng đánh đồng nó với constructor của object runtime.
- `savedProbeDefinition.isLazyInit()` đọc metadata do bạn đặt trong builder; còn `context.isPrototype("healthProbe")` kiểm tra scope hiệu lực theo container.
- Hai lần `getBean(HealthProbe.class)` trả **hai instances khác nhau**, bởi probe có scope `prototype`. Chương trình chỉ so identity, không dựa vào mã hash ngẫu nhiên.
- Bean `greetingService` mặc định singleton; `TextFormatter` được truyền vào factory method, nên service giữ đúng instance mà context trả về.
- Khi `try (context)` kết thúc, Spring xử lý shutdown và gọi `TraceSink.shutdown()` do `@Bean(destroyMethod="shutdown")`. Sau đó mã ngoài khối mới in `afterActive=false`.

### 5.3. Lệnh Maven và expected stdout

Từ thư mục `bean-definition-demo`:

~~~bash
java -version
javac -version
mvn -version
mvn -q clean compile exec:java
~~~

**Đúng 10 dòng stdout do mã ứng dụng in khi chạy thành công:**

~~~text
serviceDefinition=true
factoryMethod=greetingService
serviceSingleton=true
probePrototype=true
probeLazyMetadata=true
differentProbes=true
injectedSame=true
greeting=HELLO LAN
destroy=traceSink
afterActive=false
~~~

Các lệnh kiểm tra version và các log do Maven/framework có thể sinh ra không nằm trong 10 dòng stdout được in bởi chương trình này. `-q` giúp giảm output Maven, không làm thay đổi mã `System.out.println`.

### 5.4. Chạy trực tiếp bằng `javac` và `java`

Vì source import các class Spring, cần classpath chứa Spring JAR và dependencies transitive. Có thể nhờ Maven tạo file classpath:

~~~bash
mvn -q dependency:build-classpath -Dmdep.outputFile=classpath.txt
~~~

**Linux/macOS (bash/zsh):**

~~~bash
mkdir -p out
javac --release 17 -encoding UTF-8 \
  -cp "$(cat classpath.txt)" \
  -d out src/main/java/demo/BeanDefinitionDemo.java
java -cp "out:$(cat classpath.txt)" demo.BeanDefinitionDemo
~~~

**Windows PowerShell:**

~~~powershell
$deps = (Get-Content -Raw classpath.txt).Trim()
New-Item -ItemType Directory -Force out | Out-Null
javac --release 17 -encoding UTF-8 -cp "$deps" -d out src/main/java/demo/BeanDefinitionDemo.java
java -cp "out;$deps" demo.BeanDefinitionDemo
~~~

Dấu phân cách classpath là `:` trên Unix, `;` trên Windows. Hai cách chạy dùng **cùng một `main`** và in 10 dòng tương ứng.

## 6. Diễn giải kết quả theo từng loại metadata

| Output | Kiểm chứng điều gì? | Không suy ra được điều gì? |
| --- | --- | --- |
| `serviceDefinition=true` | Registry có bean definition mang tên `greetingService` | Không có nghĩa mọi bean đều đã được sử dụng |
| `factoryMethod=greetingService` | Metadata bean service chỉ ra factory method do Spring cấu hình | Không phải service có method nghiệp vụ cùng tên |
| `serviceSingleton=true` | Bean service trong context này có scope singleton | Không phải toàn JVM chỉ có một GreetingService |
| `probePrototype=true` | Probe là bean prototype | Không chứng minh mọi bean đều có scope prototype |
| `probeLazyMetadata=true` | Metadata lazy-init được đặt thành true | Không có nghĩa mọi dependency sẽ mãi không được khởi tạo |
| `differentProbes=true` | Hai lần yêu cầu probe tạo ra hai reference khác nhau | Không dựa vào `equals()` do class tự cài |
| `injectedSame=true` | Collaborator service giữ trùng reference bean formatter hiện có | Không đảm bảo business logic ở mọi input là đúng |
| `greeting=HELLO LAN` | Service sử dụng formatter để chuẩn hóa dữ liệu | Không có logic dịch vụ nào tự chạy chỉ nhờ definition |
| `destroy=traceSink` | Callback được Spring gọi khi hủy managed singleton | Không có nghĩa prototype cũng được tự hủy |
| `afterActive=false` | Context đã đóng sau khi rời try-with-resources | Không có nghĩa object Java đã bị GC ngay |

**Đọc metadata khác đọc instance:** Trong ví dụ, probe definition có thể được tra cứu từ registry trước khi ứng dụng gọi `getBean(HealthProbe.class)`. Metadata tồn tại độc lập với việc một instance cụ thể đã được tạo.

### Có nhất thiết phải tạo thử bean để xem BeanDefinition?

**Không.** Bạn có thể dùng `getBeanDefinition("beanName")` trên registry/factory để đọc metadata. Dù vậy, một số thao tác tra cứu loại bean hoặc ứng viên trong Spring có thể kích hoạt các cơ chế động (ví dụ `FactoryBean`), nên không nên khẳng định *mọi API dò bean đều không bao giờ gây instantiation*.

**Không nên sửa metadata tùy tiện sau khi context đang phục vụ ứng dụng.** Metadata ban đầu có thể đã được xử lý/merge/cache, và instance singleton đã tạo sẽ không tự đổi vì definition bị sửa. Hãy ưu tiên cấu hình rõ lúc bootstrap.

## 7. Tên bean, class và factory method

Có ba tên cần phân biệt:

- **Bean name:** khóa registry, ví dụ `greetingService`.
- **Java class của instance:** `GreetingService`.
- **Factory method:** `AppConfig.greetingService(TextFormatter)`.

Trong Spring JavaConfig, bean name mặc định thường lấy từ tên method `@Bean`; có thể đặt tên rõ:

~~~java
@Bean("primaryFormatter")
TextFormatter textFormatter() {
    return new UppercaseFormatter();
}
~~~

**Snippet minh họa, không thêm đồng thời** method trùng chữ ký vào cấu hình chính. Nếu đổi tên definition, lookup theo string name phải dùng `primaryFormatter`; injection theo `TextFormatter` vẫn phụ thuộc quy tắc chọn ứng viên phù hợp.

Với bean từ constructor trực tiếp bằng `genericBeanDefinition(HealthProbe.class)`, metadata có thể biết class tạo object. Với method `@Bean` hoặc các factory mechanisms khác, nó có thể chứa factory bean/method name và kiểu được suy luận. Không được suy ra mọi definition sẽ in chính xác class runtime qua `getBeanClassName()`.

**BeanDefinitionRegistry không quản lý chỉ các bean ứng dụng.** Context có thể có definitions nội bộ do Spring cần xử lý cấu hình. Vì vậy `context.getBeanDefinitionCount()` có thể lớn hơn số method `@Bean` mà bạn viết; kiểm tra các **tên mục tiêu** để biết cấu hình bạn muốn có mặt hay chưa.

## 8. Các metadata bổ sung: constructor, property, depends-on và lifecycle

### Constructor arguments và property values

Khi đăng ký definition programmatically, một builder có thể mang **constructor arguments** hoặc **property values**. Ví dụ minh họa:

~~~java
BeanDefinition workerDefinition = BeanDefinitionBuilder
        .genericBeanDefinition(JobWorker.class)
        .addConstructorArgValue("daily")
        .getBeanDefinition();

// registry.registerBeanDefinition("jobWorker", workerDefinition);
~~~

**Mã minh họa không độc lập:** `JobWorker` chưa định nghĩa và `registry` cần là đối tượng `BeanDefinitionRegistry`. Cần class có constructor phù hợp kiểu/giá trị mà bạn khai báo. Metadata chỉ dẫn cách Spring tạo object, nhưng nếu constructor không khớp thì việc tạo bean sẽ thất bại.

Tương tự, `addPropertyValue("enabled", true)` có ý nghĩa khi bean có property writable phù hợp. Đừng tự hiểu property values là thao tác gán trực tiếp vào mọi field private của Java.

### Phụ thuộc theo tên và injection theo kiểu

`@DependsOn("startupLogger")` đặt **ràng buộc khởi tạo** của một bean với bean tên `startupLogger`; nó không tự động inject bean đó như constructor argument. Trong khi đó, tham số `TextFormatter formatter` ở `@Bean greetingService(...)` là một **điểm injection thật sự**: Spring phải chọn được instance thích hợp.

Hai quan hệ có thể ảnh hưởng thứ tự tạo bean, nhưng khác mục đích. Dùng dependency khai báo công khai nếu consumer thực sự cần collaborator; dùng depends-on cho trường hợp cần side effect init trước, không thay thế dependency bị giấu.

### Init/destroy method

Có thể khai báo:

~~~java
@Bean(initMethod = "start", destroyMethod = "stop")
ResourceManager resourceManager() {
    return new ResourceManager();
}
~~~

**Snippet không độc lập:** cần `ResourceManager` có các method đúng chữ ký. Khi container tạo và khởi tạo bean thích hợp, callback init chạy theo lifecycle; khi singleton được hủy lúc context đóng, callback destroy chạy theo điều kiện phù hợp.

Đối với `prototype`, Spring thường chỉ quản lý các bước tới khi giao bean cho caller, **không tự theo dõi và thực hiện trọn destruction callback** của tất cả prototype sau đó. Code sử dụng prototype có tài nguyên phải có chiến lược đóng riêng.

Một bean được tạo bằng `new` ngoài container không tự nhận bất cứ lifecycle callback nào chỉ vì nó giống class của managed bean.

## 9. Những điều BeanDefinition KHÔNG tự bảo đảm

1. **Không bảo đảm có instance ngay lập tức.** Lazy/prototype và thời điểm request chi phối lúc tạo.
2. **Không tự chứng minh dependency hợp lệ.** Bean cần formatter nhưng không có candidate thì việc tạo có thể thất bại.
3. **Không bảo đảm lựa chọn type duy nhất.** Nhiều `TextFormatter` có thể gây ambiguity; dùng qualifier/primary hoặc thiết kế lại.
4. **Không tự làm method nghiệp vụ chạy.** Chỉ có bean được tạo; `GreetingService.greet` chạy vì caller gọi.
5. **Không tự quản lý object tạo ngoài container.** Một `new HealthProbe()` trong code thường không thuộc registry.
6. **Không bảo đảm toàn bộ bean có cùng scope.** Singleton/prototype/custom scopes khác nhau.
7. **Không bảo đảm mọi hủy tài nguyên hoàn tất.** Destroy callbacks phụ thuộc scope/ownership và mã bean.
8. **Không nhất thiết mô tả “class instance cuối cùng” giản đơn.** Factory methods, proxies, `FactoryBean` có semantics riêng.
9. **Không phải quy ước thứ tự khởi tạo theo tên.** Cạnh dependency và cơ chế khởi tạo quan trọng hơn thứ tự alphabet/khai báo.
10. **Không đồng nghĩa annotation.** XML, programmatic registration và component scanning cũng tạo metadata.

## 10. Các lỗi thường gặp và cách chẩn đoán

| Triệu chứng | Nguyên nhân khả dĩ | Cách kiểm tra |
| --- | --- | --- |
| `NoSuchBeanDefinitionException` | Không đăng ký definition hoặc tra sai tên/type | Kiểm tra registry, `@Bean`/scan, bean name/condition |
| `UnsatisfiedDependencyException` | Bean definition tồn tại nhưng dependency không giải quyết được | Xác định factory/constructor parameter nào thiếu ứng viên |
| `NoUniqueBeanDefinitionException` | Nhiều ứng viên cho injection một bean | `@Qualifier`, `@Primary`, giảm bean trùng |
| `BeanCreationException` | Constructor/factory/init method thất bại | Đọc chuỗi `Caused by`, xác định bean và metadata |
| `BeanCurrentlyInCreationException` | Vòng constructor/factory dependency | Vẽ A→B→A, tách trách nhiệm |
| Sai scope khi nhìn `getScope()` | Metadata mặc định có thể để rỗng | Hỏi container `isSingleton`/`isPrototype` cho tên bean cụ thể |
| Method `@Bean` trả một class nhưng `getBeanClassName()` trống/khác kỳ vọng | Definition có thể dựa trên factory method thay vì bean class trực tiếp | Xem `getFactoryMethodName()` và loại registration |
| `getBeanDefinitionCount()` lớn hơn số bean tự viết | Spring thêm infrastructure definitions | Chỉ kiểm tra các tên ứng dụng quan tâm |
| Registration API gọi sau khi refresh | Thời điểm không phù hợp với lifecycle và caches | Đăng ký trước `refresh()` hoặc dùng extension point đúng |
| Một prototype trông giống singleton | Consumer singleton giữ dependency inject từ khi nó được tạo | Dùng provider/lookup theo mỗi thao tác nếu thật sự cần |
| Bean có `@Bean(destroyMethod=...)` nhưng không thấy callback | Context chưa được đóng, bean chưa tạo hoặc scope khác | Kiểm tra lifecycle và tên method |
| `package org.springframework... does not exist` | Classpath thiếu dependency compile | Kiểm tra Maven `spring-context` và `javac -cp` |

**Đừng sửa trực tiếp BeanDefinition sau mỗi request** để “cấu hình lại” service đang chạy. Với nhiều trường hợp, instance đã được tạo/cached, và thay đổi metadata không làm Spring tái inject hay xây lại toàn bộ graph.

## 11. Khi nào nên thao tác BeanDefinition bằng API?

Phần lớn ứng dụng có thể dùng `@Configuration`, `@Bean` và component scanning. API của BeanDefinition phù hợp khi:

- Viết framework starter/infrastructure tích hợp class do người dùng cung cấp.
- Sinh nhiều bean definitions từ metadata/lược đồ khác, nhưng vẫn muốn Spring quản lý lifecycle.
- Tạo các registration động có kiểm soát **trước bootstrap** khi không tiện biểu đạt bằng vài method `@Bean`.
- Viết tooling cần kiểm tra tên/role/source/loại/thuộc tính definition.
- Tùy biến metadata trước instantiation qua extension points được thiết kế, chẳng hạn `BeanFactoryPostProcessor` hoặc `BeanDefinitionRegistryPostProcessor`.

**Phân biệt hai extension point nổi bật:**

| Extension point | Thao tác mục tiêu | Khi nào |
| --- | --- | --- |
| `BeanDefinitionRegistryPostProcessor` | Có thể đăng ký/sửa thêm bean definitions | Giai đoạn bootstrap trước tạo bean ứng dụng |
| `BeanFactoryPostProcessor` | Điều chỉnh metadata các bean definitions đã được đăng ký | Trước giai đoạn khởi tạo bean bình thường |
| `BeanPostProcessor` | Tác động lên **bean instances** khi khởi tạo | Không phải công cụ chỉ để sửa metadata |

Thứ tự/cách gọi chính xác phụ thuộc cơ chế của Spring; bài này chỉ cần nhận diện **registry metadata** và **instance processing** là hai cấp khác nhau.

Nếu chỉ cần kết nối hai service trong app, việc dùng trực tiếp `BeanDefinitionBuilder` thường **phức tạp hơn cần thiết**. Cấu hình Java đơn giản sẽ rõ ràng và dễ bảo trì hơn.

## 12. Bài tập có đáp án

**Bài 1 — Definition và instance.** Đăng ký một bean `prototype` mà chưa gọi `getBean`. Có phải bạn đã tạo instance không?

**Đáp án:** Chưa, registration chủ yếu tạo/lưu metadata. Instance prototype thường được tạo khi có yêu cầu phù hợp.

**Bài 2 — Vì sao scope trống?** `@Bean GreetingService greetingService(...)` không gắn `@Scope`. Nếu `definition.getScope()` là chuỗi rỗng, bean có phải prototype?

**Đáp án:** Không. Default scope đối với bean thông thường là singleton. Kiểm tra scope có hiệu lực bằng `context.isSingleton("greetingService")` thay vì kết luận từ chuỗi rỗng.

**Bài 3 — Hai lần lấy prototype.** Nếu `healthProbe` là prototype, `context.getBean(HealthProbe.class)` hai lần có chung reference không?

**Đáp án:** Không trong ví dụ này: Spring tạo hai instances, vì vậy `differentProbes=true`.

**Bài 4 — Method factory.** Vì sao service definition có `getFactoryMethodName()=="greetingService"`?

**Đáp án:** Bean service được đăng ký từ `@Bean greetingService(TextFormatter)`, nên metadata biết factory method cung cấp bean. Đây không phải tên method nghiệp vụ `greet`.

**Bài 5 — Destroy callback.** Tại sao `destroy=traceSink` xuất hiện trước `afterActive=false`?

**Đáp án:** Rời `try (context)` gọi `close()`. Spring hủy bean singleton có `destroyMethod="shutdown"` trước khi chương trình tiếp tục tới câu lệnh sau khối.

**Bài 6 — Thiếu collaborator.** Nếu xóa bean `textFormatter` nhưng giữ `greetingService(TextFormatter)`, điều gì xảy ra?

**Đáp án:** Context có thể thất bại khi tạo service vì không resolve được tham số bắt buộc. Definition có mặt không tự bảo đảm được instantiation.

**Bài 7 — Registry vs lookup.** `containsBeanDefinition("name")` có hoàn toàn giống `containsBean("name")`?

**Đáp án:** Không. Câu đầu hỏi bean definition được đăng ký trực tiếp trong registry tương ứng; câu sau hỏi container có nhận diện bean theo tên qua cơ chế tra cứu hay không (có thể tính cả alias/parent/registration khác tùy context). Trong các trường hợp đơn giản hai kết quả trùng, nhưng chúng không phải cùng API.

## 13. Checklist hoàn thành

- [ ] Phân biệt `BeanDefinition`, registry, factory và instance.
- [ ] Nắm bean name là khóa registry và biết đường tạo bean (class vs factory method).
- [ ] Biết scope singleton/prototype và tác dụng của lazy metadata.
- [ ] Hiểu constructor/factory args, property values và lifecycle callbacks.
- [ ] Biết `@Bean`/component scanning/registration API đều tạo metadata.
- [ ] Tạo context bằng JavaConfig và đăng ký programmatic definition trước refresh.
- [ ] Chạy Java 17+ với `mvn -q clean compile exec:java`, đối chiếu đúng 10 dòng stdout.
- [ ] Nếu tự chạy `javac`/`java`, chuẩn bị đầy đủ Spring classpath.
- [ ] Phân biệt đọc metadata `getBeanDefinition` với lấy instance `getBean`.
- [ ] Không suy đoán scope mặc định chỉ từ `definition.getScope()` có thể rỗng.
- [ ] Không chỉnh metadata tùy tiện sau khi bean đã khởi tạo.
- [ ] Biết đọc lỗi missing/ambiguous bean, vòng dependency, factory/init failures.
- [ ] Phân biệt bean lifecycle managed với object do code Java tạo ngoài container.

**Kết luận:** `BeanDefinition` là **hợp đồng metadata** mô tả Spring biết về một bean: cách tạo, cách resolve dependency và các thiết lập scope/lifecycle. Container dùng metadata để cung cấp **bean instance thực tế** khi cần. Nắm được điểm này giúp bạn hiểu vì sao cùng một Spring API có thể tạo singleton, prototype, lazy bean hoặc bean qua factory method — và vì sao **đăng ký definition khác với khởi tạo object**.

### Tài liệu đọc thêm

- [Spring IoC Container](https://docs.spring.io/spring-framework/reference/core/beans/introduction.html)
- [Bean Overview / Definition](https://docs.spring.io/spring-framework/reference/core/beans/definition.html)
- [Java Configuration — @Bean](https://docs.spring.io/spring-framework/reference/core/beans/java/bean-annotation.html)
- [Spring BeanDefinition API](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/beans/factory/config/BeanDefinition.html)
