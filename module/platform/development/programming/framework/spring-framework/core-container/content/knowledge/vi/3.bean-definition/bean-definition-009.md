# Xung đột tên và chính sách ghi đè định nghĩa — Spring Framework Core Container

## 1. Mục tiêu: cùng tên bean là một xung đột về định danh

Trong Spring IoC container, mỗi **bean definition** được đăng ký với một **bean name**. Nếu hai nguồn cấu hình cố đăng ký **hai định nghĩa khác nhau dưới cùng một tên** trong cùng registry, xảy ra **xung đột tên bean definition**. Spring có thể cho phép đăng ký sau thay thế định nghĩa cũ, hoặc từ chối thao tác ghi đè, tùy **chính sách của container**.

Điểm then chốt:

- **Xung đột tên:** nhiều bean definitions cố dùng cùng **tên**, dù class có thể khác hoặc giống nhau.
- **Nhiều bean cùng kiểu:** hai bean **khác tên** cùng kiểu Java là hợp lệ, nhưng một injection point theo kiểu có thể gặp lỗi **không chọn được một candidate**. Đây là vấn đề *autowiring ambiguity*, không phải lỗi trùng tên.
- **Bean alias:** tên phụ trỏ tới **một bean**; không tạo thêm một bean definition độc lập. Alias có thể liên quan tới kiểm tra xung đột tên, nhưng không được nhầm với ghi đè hai definitions.
- **Ghi đè definition:** nếu được cho phép, definition mới thay definition cũ dưới **cùng registry key**. Không phải phép “hợp nhất hai bean” và cũng không tạo hai instance cạnh tranh cùng tên.

Kết thúc bài, bạn có thể:

1. Phân biệt `BeanDefinitionOverrideException` với `NoUniqueBeanDefinitionException`.
2. Hiểu `DefaultListableBeanFactory.setAllowBeanDefinitionOverriding(boolean)` và cách điều khiển chính sách qua `AnnotationConfigApplicationContext`.
3. Giải thích sự khác nhau giữa **mặc định của Spring Framework** và **mặc định của Spring Boot**.
4. Chạy chương trình Java 17+ kiểm chứng hai nhánh **REJECTED** khi cấm và **SECOND** khi cho phép ghi đè, với output xác định.
5. Hiểu ảnh hưởng của registration order, alias, bean name, `@Bean`/component scan, bean scope và thời điểm refresh.
6. Biết cách chọn chính sách và gỡ lỗi trong dự án thật; không bật ghi đè tùy tiện chỉ để ứng dụng khởi động.

**Phạm vi:** tập trung vào bean name và bean definition overriding trong Spring Core Container. Không cần Spring Boot để chạy ví dụ chính.

## 2. Bean name, bean definition, instance và alias

Một bean definition cung cấp **metadata** để Spring tạo/quản lý object: class hoặc factory method, scope, lazy, dependency, init/destroy metadata và các thuộc tính khác. Registry ánh xạ **tên** sang definition.

~~~text
BeanDefinitionRegistry
  "notificationClient" -> BeanDefinition #A -> new ChannelClient("FIRST")
  "metricsClient"      -> BeanDefinition #B -> new ChannelClient("METRICS")
  
Bean aliases (nếu đăng ký)
  "preferredClient" -> "notificationClient"
~~~

Trong ví dụ trên, `notificationClient` và `metricsClient` là **hai bean names khác nhau**, dù cùng class `ChannelClient`. `preferredClient` chỉ là **alias**, không có definition thứ ba.

Nếu tiếp tục đăng ký:

~~~text
registerBeanDefinition("notificationClient", BeanDefinition #C)
~~~

thì registry phải xử lý việc `notificationClient` **đã tồn tại**. Tùy chính sách, nó từ chối definition #C hoặc thay ánh xạ cũ bằng definition #C.

### Bảng phân biệt bốn trường hợp

| Tình huống | Có phải xung đột tên definition? | Kết quả chủ yếu |
| --- | --- | --- |
| Hai bean definitions cùng bean name trong cùng registry | Có | Từ chối hoặc thay definition cũ theo chính sách |
| Hai bean khác tên, cùng class Java | Không | Hai bean hợp lệ; có thể gây ambiguity khi inject chỉ bằng kiểu |
| Một bean name với một hoặc nhiều alias | Không tự là hai definitions | Các tên cùng trỏ một bean |
| Hai bean definitions cùng tên nhưng ở hai contexts độc lập | Không nhất thiết | Mỗi context có registry riêng; cần xét quan hệ parent-child nếu có |

Lỗi `NoUniqueBeanDefinitionException` nói về việc container không giải quyết được **một ứng viên từ nhiều bean** khi tra cứu/inject theo type. Ngược lại, `BeanDefinitionOverrideException` xuất hiện ở giai đoạn **đăng ký definition trùng bean name bị cấm**. Hướng sửa khác nhau, đừng đổi qualifier để chữa nhầm một lỗi registry name collision.

## 3. Spring Framework và Spring Boot có mặc định khác nhau

Với `DefaultListableBeanFactory` của **Spring Framework 6.2**, mặc định **cho phép bean definition overriding**; khi đăng ký definition khác cùng tên, definition đến sau có thể thay definition trước.

Spring cung cấp API:

~~~java
context.setAllowBeanDefinitionOverriding(false);
context.setAllowBeanDefinitionOverriding(true);
~~~

Đây là **các lựa chọn thay thế**, không gọi nối tiếp hai dòng trong cùng chương trình để “kết hợp” chính sách. `AnnotationConfigApplicationContext` kế thừa API này từ `GenericApplicationContext`; cũng có thể cấu hình trực tiếp underlying `DefaultListableBeanFactory`.

**Spring Boot mặc định không cho phép ghi đè bean definition** trong cấu hình thông thường. Boot có property:

~~~properties
spring.main.allow-bean-definition-overriding=false
~~~

Đây là **ví dụ property của Spring Boot**, không có tác dụng khi chỉ dùng `new AnnotationConfigApplicationContext()` của Spring Framework thuần và không có Boot làm host. Nếu thật sự muốn thay đổi chính sách trong Boot, có thể cấu hình:

~~~properties
spring.main.allow-bean-definition-overriding=true
~~~

Nhưng **không nên dùng cờ true như cách sửa mọi lỗi trùng tên**: nó có thể giấu lỗi cấu hình, khiến bean dự kiến bị thay bằng implementation không mong muốn.

| Ngữ cảnh | Mặc định điển hình | Cách thể hiện rõ |
| --- | --- | --- |
| Spring Framework `DefaultListableBeanFactory` | Cho phép ghi đè | `setAllowBeanDefinitionOverriding(false/true)` |
| Spring `GenericApplicationContext` / `AnnotationConfigApplicationContext` thuần | Theo BeanFactory, mặc định cho phép | `context.setAllowBeanDefinitionOverriding(false/true)` |
| Spring Boot | Mặc định cấm | Property `spring.main.allow-bean-definition-overriding` hoặc API Boot tương ứng |

**Khuyến nghị cho demo và test:** luôn **đặt chính sách tường minh** ngay khi tạo context, trước lúc đăng ký các definitions có nguy cơ trùng tên. Điều này giúp kết quả không phụ thuộc giả định về framework host và phiên bản.

## 4. Chính sách cấm ghi đè: fail fast ngay lúc registration

Giả sử registry đang có:

~~~java
context.registerBeanDefinition(
        "notificationClient",
        createDefinition("FIRST"));
~~~

Khi chính sách là `false`, việc tiếp tục đăng ký:

~~~java
context.registerBeanDefinition(
        "notificationClient",
        createDefinition("SECOND"));
~~~

sẽ **bị từ chối** vì trùng bean name. Ở trường hợp gọi `registerBeanDefinition` programmatically, `BeanDefinitionOverrideException` được ném ngay từ thao tác đăng ký thứ hai, **trước khi gọi `refresh()`**. Định nghĩa cũ vẫn tồn tại, chưa bị thay bởi definition mới thất bại.

Lợi ích của việc cấm:

- Phát hiện lỗi tên trùng giữa các module/configuration từ sớm.
- Hạn chế nguy cơ một thành phần bị thay thế âm thầm khi refactor, cập nhật thư viện hoặc mở rộng component scanning.
- Làm hợp đồng registration dễ dự đoán: tên đã dùng không thể bị chiếm bởi một definition khác.
- Phù hợp với môi trường cần cấu hình nghiêm ngặt và kiểm thử startup rõ ràng.

Điều này **không** ngăn có nhiều bean cùng class với **tên khác nhau**, và cũng không giải quyết ambiguity của dependency theo type. Một Spring registry có thể cấm overriding nhưng vẫn chứa hai beans `MailSender` khác tên.

## 5. Chính sách cho phép ghi đè: definition đến sau thay definition cũ

Khi đặt `setAllowBeanDefinitionOverriding(true)`:

~~~java
context.registerBeanDefinition(
        "notificationClient",
        createDefinition("FIRST"));

context.registerBeanDefinition(
        "notificationClient",
        createDefinition("SECOND"));
~~~

trong trường hợp đăng ký tuần tự trước `refresh()` ở ví dụ, definition thứ hai thay thế definition thứ nhất **dưới cùng một tên**. Khi context khởi tạo bean `notificationClient`, nó sử dụng definition còn hiệu lực và tạo object có source `SECOND`.

Cần phân biệt rõ:

- Đây là **thay definition**, không phải tạo hai bean singleton cùng tên.
- Definition cũ **không còn** được tra cứu bằng bean name đó. Vì ví dụ đăng ký hai lần **trước refresh**, không có chuyện một singleton cũ đã tồn tại rồi mới bị thay đổi trong chương trình này.
- **Không sửa metadata/ghi đè bean definitions tùy tiện sau khi context đã refresh và instance đã được tạo**. Cache, dependency graph và lifecycle có thể đã tồn tại; hành vi đổi cấu hình runtime không tương đương một bootstrap mới.
- Trong cấu hình có `@Configuration`, `@Bean`, component scan, import và các post-processors, Spring có nhiều bước xử lý nguồn cấu hình. **Không dựa vào thứ tự tình cờ giữa nhiều nguồn** để chọn “ai thắng”. Điều kiện registration và các cơ chế phát hiện trùng tên có thể ảnh hưởng kết quả cụ thể. Demo dùng API đăng ký tuần tự để kết quả xác định.

### Vì sao không nên dùng ghi đè như cơ chế chọn implementation thông thường?

Nếu cần chọn một trong hai implementation theo môi trường, thường nên thiết kế rõ bằng **bean name riêng, qualifier, primary, profile, condition hoặc factory method có chủ đích**, tùy ngữ cảnh; đừng cố tình đăng ký trùng tên và hy vọng source load order nhất quán. Ghi đè có thể hữu ích cho test override hoặc infrastructure có kiểm soát, nhưng phải nêu rõ nơi đăng ký và bằng chứng được kiểm tra.

## 6. Chương trình Java 17+ chạy độc lập

Ví dụ dùng **JDK 17+**, Maven và **Spring Framework 6.2.19** (module `spring-context`). Đây là phiên bản được ghim để tái lập, không phải lời khẳng định bản Spring mới nhất.

Demo tạo **hai context độc lập**:

- Context thứ nhất có policy **false**: registration thứ hai bị từ chối; bean hiện hành vẫn là FIRST.
- Context thứ hai có policy **true**: registration thứ hai thay định nghĩa; bean hiện hành là SECOND.
- Context thứ hai còn đăng ký một alias để chứng minh alias **không phải bean definition mới**.

Không cần Spring Boot, database, network server hoặc Spring MVC.

~~~text
bean-override-demo/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── demo/
                └── BeanOverridePolicyDemo.java
~~~

### 6.1. File pom.xml

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>bean-override-demo</artifactId>
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
                    <mainClass>demo.BeanOverridePolicyDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Maven tải `spring-context` và các module phụ thuộc theo cấu hình POM. Với `javac`/`java` thủ công, cần đưa các JAR đó vào compile/runtime classpath.

### 6.2. File src/main/java/demo/BeanOverridePolicyDemo.java

~~~java
package demo;

import java.util.Objects;

import org.springframework.beans.factory.config.BeanDefinition;
import org.springframework.beans.factory.support.BeanDefinitionBuilder;
import org.springframework.beans.factory.support.BeanDefinitionOverrideException;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

public final class BeanOverridePolicyDemo {
    private BeanOverridePolicyDemo() {}

    public static final class ChannelClient {
        private final String source;

        public ChannelClient(String source) {
            this.source = Objects.requireNonNull(source);
        }

        public String source() {
            return source;
        }
    }

    private static BeanDefinition definition(String source) {
        return BeanDefinitionBuilder
                .genericBeanDefinition(ChannelClient.class)
                .addConstructorArgValue(source)
                .getBeanDefinition();
    }

    private static void demonstrateDenied() {
        try (AnnotationConfigApplicationContext context =
                new AnnotationConfigApplicationContext()) {
            context.setAllowBeanDefinitionOverriding(false);

            context.registerBeanDefinition(
                    "notificationClient", definition("FIRST"));

            System.out.println("denyPolicy=" +
                    context.getDefaultListableBeanFactory()
                            .isAllowBeanDefinitionOverriding());

            try {
                context.registerBeanDefinition(
                        "notificationClient", definition("SECOND"));
                System.out.println("denyResult=UNEXPECTED");
            } catch (BeanDefinitionOverrideException ex) {
                System.out.println("denyResult=REJECTED");
                System.out.println("denyName=" + ex.getBeanName());
            }

            context.refresh();
            ChannelClient retained =
                    context.getBean("notificationClient", ChannelClient.class);
            System.out.println("denyActiveDefinition=" + retained.source());
        }
    }

    private static void demonstrateAllowed() {
        try (AnnotationConfigApplicationContext context =
                new AnnotationConfigApplicationContext()) {
            context.setAllowBeanDefinitionOverriding(true);

            context.registerBeanDefinition(
                    "notificationClient", definition("FIRST"));
            context.registerBeanDefinition(
                    "notificationClient", definition("SECOND"));
            context.registerAlias("notificationClient", "preferredClient");
            context.refresh();

            ChannelClient selected =
                    context.getBean("notificationClient", ChannelClient.class);
            ChannelClient byAlias =
                    context.getBean("preferredClient", ChannelClient.class);

            System.out.println("allowPolicy=" +
                    context.getDefaultListableBeanFactory()
                            .isAllowBeanDefinitionOverriding());
            System.out.println("allowResult=" + selected.source());
            System.out.println("beanNamesForType=" +
                    context.getBeanNamesForType(ChannelClient.class).length);
            System.out.println("aliasSameInstance=" +
                    (selected == byAlias));
            System.out.println("aliasIsDefinition=" +
                    context.containsBeanDefinition("preferredClient"));
            System.out.println("sameSingleton=" +
                    (selected == context.getBean(
                            "notificationClient", ChannelClient.class)));
        }
    }

    public static void main(String[] args) {
        demonstrateDenied();
        demonstrateAllowed();
    }
}
~~~

**Giải thích vì sao ví dụ có output đáng tin:**

- `ChannelClient` là nested public static class có constructor công khai nhận một String; definition builder lưu constructor argument `FIRST` hoặc `SECOND`.
- `context.setAllowBeanDefinitionOverriding(...)` được gọi **trước registration**, policy không thay đổi giữa chừng.
- Trong nhánh denied, exception được bắt **đúng loại**; sau lỗi, definition đầu tiên vẫn tồn tại. `refresh()` sau đó tạo một instance từ definition FIRST.
- Trong nhánh allowed, hai registration xảy ra tuần tự **trước refresh**, nên definition SECOND còn hiệu lực khi bean được tạo.
- Alias `preferredClient` trỏ tới `notificationClient`; không tạo definition thứ hai, do vậy tra cứu bằng alias trả cùng object singleton.
- `getBeanNamesForType(ChannelClient.class).length` trong context allowed là 1: **một bean name chính** thuộc kiểu đó; alias không xuất hiện như definition độc lập trong danh sách này.
- Hai context được đóng bằng `try-with-resources`. Output không dựa vào log framework, giá trị random, thời gian hoặc class hash codes.

### 6.3. Chạy bằng Maven và stdout

Tại thư mục `bean-override-demo`:

~~~bash
java -version
javac -version
mvn -version
mvn -q clean compile exec:java
~~~

**Chính xác 10 dòng stdout do code Java in khi chạy thành công:**

~~~text
denyPolicy=false
denyResult=REJECTED
denyName=notificationClient
denyActiveDefinition=FIRST
allowPolicy=true
allowResult=SECOND
beanNamesForType=1
aliasSameInstance=true
aliasIsDefinition=false
sameSingleton=true
~~~

Lệnh `java -version`, `javac -version`, `mvn -version` và log Maven/Spring (nếu có) không thuộc **10 dòng do ứng dụng phát ra**. Chuỗi exception nội bộ có thể chứa nhiều metadata/log khác nhau; demo **không in stack trace** mà chỉ in kết quả đã được bắt và name, nên stdout ổn định.

### 6.4. Chạy bằng javac và java trực tiếp

Để Java compiler tìm thấy Spring API, tạo classpath bằng Maven:

~~~bash
mvn -q dependency:build-classpath -Dmdep.outputFile=classpath.txt
~~~

**Linux/macOS (bash/zsh):**

~~~bash
mkdir -p out
javac --release 17 -encoding UTF-8 \
  -cp "$(cat classpath.txt)" \
  -d out src/main/java/demo/BeanOverridePolicyDemo.java
java -cp "out:$(cat classpath.txt)" demo.BeanOverridePolicyDemo
~~~

**Windows PowerShell:**

~~~powershell
$deps = (Get-Content -Raw classpath.txt).Trim()
New-Item -ItemType Directory -Force out | Out-Null
javac --release 17 -encoding UTF-8 -cp "$deps" -d out src/main/java/demo/BeanOverridePolicyDemo.java
java -cp "out;$deps" demo.BeanOverridePolicyDemo
~~~

Lưu ý dấu phân tách classpath **`:`** trên Unix và **`;`** trên Windows. Hai cách chạy dùng cùng class `demo.BeanOverridePolicyDemo` nên stdout theo cùng một kịch bản.

## 7. Diễn giải từng kiểm chứng

| Dòng output | Ý nghĩa |
| --- | --- |
| `denyPolicy=false` | Context thứ nhất cấm override bằng cấu hình tường minh |
| `denyResult=REJECTED` | Đăng ký definition thứ hai cùng name bị từ chối |
| `denyName=notificationClient` | Exception chỉ đúng bean name bị xung đột |
| `denyActiveDefinition=FIRST` | Sau registration bị từ chối, definition đầu vẫn được sử dụng |
| `allowPolicy=true` | Context thứ hai bật override tường minh |
| `allowResult=SECOND` | Definition mới thay definition cũ trước refresh |
| `beanNamesForType=1` | Registry còn một bean name chính thuộc kiểu ChannelClient |
| `aliasSameInstance=true` | Alias tra cùng bean object, không phải bean thứ hai |
| `aliasIsDefinition=false` | Alias không tạo thêm BeanDefinition |
| `sameSingleton=true` | Trong cùng context, lấy bean singleton nhiều lần trả cùng reference |

**Điều chưa chứng minh bằng output này:** rằng mọi cách đăng ký xung đột qua annotation/scan/XML có cùng thứ tự thắng hoặc loại exception tại cùng thời điểm; đó là các nguồn metadata và bước xử lý bổ sung, cần kiểm tra riêng.

## 8. Xung đột có thể đến từ đâu trong dự án thực tế?

- **Hai phương thức `@Bean` khác lớp cấu hình** dùng cùng bean name mặc định vì cùng tên method, hoặc dùng `@Bean("notificationClient")` trùng tường minh.
- **Component scanning** phát hiện nhiều component cùng tên (theo cơ chế đặt tên/naming strategy) hoặc trùng với bean đã được khai báo bằng JavaConfig.
- **Thư viện và ứng dụng cùng đăng ký một tên**, ví dụ code của dự án cố dùng tên infrastructure đã được thư viện khác sử dụng.
- **XML bean declarations** hoặc programmatic registration trùng key với metadata từ JavaConfig.
- **Thay đổi tên method/class/package hoặc scope quét** khiến các bean bắt đầu va chạm sau refactor/update dependency.
- **Alias đã dùng** làm tên cho một đăng ký khác, hoặc hai alias definitions cạnh tranh; kiểm tra conflict ở registry/alias mechanism liên quan.
- **Context con và context cha:** không nhất thiết là đăng ký cùng registry. Child context có thể shadow bean name ở parent theo lookup hierarchy; không đồng nghĩa hai definitions trong **cùng bean factory** ghi đè nhau. Cần phân biệt registry scope trước khi kết luận là collision.

### Hành vi của @Bean khi cùng tên

Spring xử lý các method `@Bean` thông qua configuration parsing và bean definition registration. Không nên đơn giản hóa thành “method nào nằm dưới sẽ luôn thắng”. Tùy nguồn định nghĩa, thứ tự xử lý, sự trùng giữa method và component, cùng các quy tắc dành cho metadata, một cấu hình có thể bị từ chối, bị bỏ qua trong giai đoạn đăng ký, hoặc được xử lý theo quy tắc riêng.

**Muốn một kiểm chứng có kết quả chắc chắn**, hãy xem bean definitions đã đăng ký, logging của quá trình bootstrap và test context thực tế; đừng dựa vào phán đoán thứ tự method xuất hiện trong source code.

## 9. Xung đột tên khác xung đột theo type

~~~java
@Bean("firstChannel")
ChannelClient firstChannel() {
    return new ChannelClient("FIRST");
}

@Bean("secondChannel")
ChannelClient secondChannel() {
    return new ChannelClient("SECOND");
}
~~~

Đây là **snippet minh họa**, không phải file hoàn chỉnh. Hai bean có **tên khác nhau**, dù cùng class. Không vi phạm `allowBeanDefinitionOverriding=false` vì registry không phải ghi đè một tên đang có.

Tuy nhiên:

~~~java
ChannelClient client = context.getBean(ChannelClient.class);
~~~

nếu không có candidate nào được ưu tiên theo quy tắc phù hợp, tra theo type đơn trị có thể thất bại với `NoUniqueBeanDefinitionException`. Giải pháp là chọn **đúng ứng viên**, không phải bật bean overriding:

- `@Qualifier("firstChannel")` tại injection point cần bean thứ nhất.
- `@Primary` khi một bean thực sự nên là lựa chọn mặc định.
- Tra bằng bean name tại composition root, ví dụ `context.getBean("firstChannel", ChannelClient.class)`.
- Injection list/map khi nghiệp vụ cần tất cả strategies hoặc channels.

Ngược lại, `BeanDefinitionOverrideException` liên quan đến **cùng bean name** bị đăng ký thêm khi policy cấm. Không có lý do dùng `@Qualifier` để cho phép ghi đè một tên đã bị chiếm.

## 10. Chính sách và thời điểm thiết lập

Đối với context do ứng dụng tự tạo, nên đặt policy **trước register/refresh**:

~~~java
try (AnnotationConfigApplicationContext context =
        new AnnotationConfigApplicationContext()) {
    context.setAllowBeanDefinitionOverriding(false);
    context.register(AppConfig.class);
    context.refresh();
    // Sử dụng bean khi context còn active.
}
~~~

Đây là **snippet minh họa**; `AppConfig` phải được định nghĩa ở chương trình riêng. Cách tạo bằng constructor không tham số rồi cấu hình có lợi khi cần sửa chính sách **trước bước bootstrap**. Nếu dùng ngay `new AnnotationConfigApplicationContext(AppConfig.class)`, constructor thường refresh context trước khi bạn có cơ hội gọi setter policy trên instance đã tạo; không nên dùng cú pháp đó khi bài toán đòi đặt policy trước registration.

Với Spring Boot, option `spring.main.allow-bean-definition-overriding` thuộc về cấu hình khởi động Boot, **không phải một `@Bean` String property tự động áp dụng cho context Spring thuần**.

### Có thể thay đổi một bean đang chạy bằng cách đăng ký lại không?

Không coi override là cơ chế hot swap bean sau startup. Nếu singleton đã được tạo, nó có thể đang được inject vào nhiều consumer, có cached metadata, post-processors, lifecycle và tài nguyên đang chạy. Việc thay đổi definition sau đó **không bảo đảm tự thay mọi reference cũ**, có thể tạo trạng thái không nhất quán. Nếu cần cấu hình lại dịch vụ đang chạy, hãy chọn cơ chế reconfiguration được hỗ trợ, tạo context mới hoặc thiết kế provider phù hợp.

**Quy tắc an toàn:** các bean definitions phải có cấu hình dự kiến hoàn chỉnh **trước refresh**, policy phải rõ, và startup test cần kiểm tra implementation thực tế được cung cấp.

## 11. Quy trình chẩn đoán tên trùng

1. **Đọc bean name trong exception** (ví dụ `notificationClient`), không chỉ đọc “could not start”.
2. **Xác định hai nguồn đăng ký:** `@Bean` methods, component scan, XML, library auto-registration hay API.
3. **Xác định registry/context:** chúng có thật sự vào cùng BeanFactory, hay một bean ở parent và một ở child?
4. **Kiểm tra policy:** context/framework host đang cho override hay cấm? Đừng đoán dựa vào kinh nghiệm từ dự án dùng Spring Boot nếu hiện tại chạy Framework thuần.
5. **Kiểm tra bean definition metadata:** factory method, bean class, resource/source, role, scope và qualifiers (khi có).
6. **Quyết định đúng nghiệp vụ:** hai bean đáng lẽ độc lập khác tên, hay chỉ cần một bean? Có vô tình scan trùng không?
7. **Đổi tên hoặc hợp nhất cấu hình có chủ đích**; chọn qualifier/primary khi vấn đề thật sự là ambiguity theo type.
8. **Chạy startup smoke test và kiểm tra runtime**: bean name, object type, cấu hình/identity, hành vi; không chỉ dựa vào log thiếu exception.
9. **Kiểm tra module/environment khác:** test/prod có thể thêm cấu hình hoặc scan package làm lộ collision khác.

### Các API hữu ích

~~~java
context.containsBeanDefinition("notificationClient");
context.isBeanNameInUse("notificationClient");
context.getBeanDefinition("notificationClient");
context.getAliases("notificationClient");
context.getBean("notificationClient");
~~~

Đây là các snippet **minh họa trong scope có context phù hợp**, không phải full Java file. Chú ý `isBeanNameInUse` tính cả alias/bean name liên quan trong registry; `containsBeanDefinition` hỏi **definition đăng ký trực tiếp**, còn `getBean` lấy **instance** (có thể tạo bean nếu chưa có).

Dùng API tra cứu definition **không đồng nghĩa** cho phép thay đổi definition đang chạy: metadata inspection là việc khác với mutation.

## 12. Lỗi phổ biến và cách khắc phục

| Vấn đề | Sai lầm thường gặp | Cách khắc phục |
| --- | --- | --- |
| `BeanDefinitionOverrideException` | Cùng bean name được đăng ký hai lần trong policy cấm | Tìm hai nguồn, đổi tên hợp lý hoặc loại đăng ký trùng |
| `NoUniqueBeanDefinitionException` | Hai bean khác tên nhưng injection một type mơ hồ | Qualifier/primary/tái thiết kế selection, không bật overriding |
| “Đã bật true nhưng runtime vẫn sai” | Bean mong muốn bị thay bởi definition khác | Kiểm tra nguồn đăng ký, implementation thực tế, startup tests |
| “Alias cũng là bean thứ hai” | Đếm alias thành definition mới | Dùng `isAlias`, `containsBeanDefinition`, so identity |
| “Bean cuối cùng trong source sẽ thắng” | Dựa vào thứ tự văn bản JavaConfig | Kiểm tra order/registering pipeline, đừng lập hợp đồng ngầm |
| Trùng tên do component scan | Hai component đặt tên giống nhau hoặc scan phạm vi sai | Đổi bean names/naming strategy hoặc giới hạn scan |
| Cấu hình thư viện và ứng dụng đụng tên | Tái dùng một bean name generic | Đặt tên có namespace/rõ module, xem extension points chính thức |
| Parent/child context cùng bean name | Nhầm shadowing với override trong một registry | Xem hierarchy và quy tắc lookup ở context thực tế |
| “Đổi policy sau refresh để sửa lỗi” | Thay chính sách quá muộn | Cấu hình trước register/refresh và khởi động lại |
| Ghi đè sau khi singleton đã tạo | Mong những consumer đã inject tự cập nhật reference | Không dùng override làm hot reload; thiết kế lifecycle/reconfiguration |
| Spring Framework và Boot khác mặc định | Áp dụng giả định của framework khác | Kiểm tra policy của runtime thực, đặt tường minh |
| Bean type trùng nhưng name khác | Coi đó là lỗi registry | Chọn bean theo type/qualifier thích hợp |
| Bean name trùng nhưng class khác | Nghĩ khác class thì không xung đột | Registry key theo tên, nên class khác vẫn collision |

**Nguyên tắc vận hành:** “ứng dụng chạy được” không chứng minh đã chọn đúng bean. Khi override được bật, **đặc biệt cần kiểm tra bean thực tế** vì lỗi vô tình thay definition có thể không làm startup thất bại.

## 13. Khi nào override có thể có chủ đích?

Có những trường hợp hệ thống cần đăng ký một implementation thay cho definition mặc định: môi trường test cung cấp fake, framework integration cố ý cho custom registration hoặc một hệ thống cấu hình cho phép thay thế. Nhưng phải xác định:

- Ai sở hữu bean name đó và ai được phép thay?
- Có hợp đồng/documentation chính thức về override hay không?
- Registration order có được định nghĩa rõ trong tình huống này?
- Bean được thay có lifecycle/resource/configuration nào?
- Test nào chứng minh bean cuối cùng đúng loại và đúng hành vi?
- Chính sách ở các môi trường (dev/test/prod) có giống nhau?

Trong Spring Boot tests, có thể có **các cơ chế override bean chuyên biệt của hệ sinh thái test**; chúng không đồng nghĩa việc luôn cần bật property overriding cho toàn ứng dụng. Với code sản phẩm, ưu tiên configuration/extension points chính thức thay vì dùng trùng tên tình cờ.

**Ví dụ lựa chọn ít rủi ro:** thay vì đăng ký hai beans cùng name, cấu hình một method `@Bean` duy nhất chọn implementation từ một property hợp lệ rồi trả interface chung; hoặc đăng ký hai tên rõ và chọn bằng qualifier/profile khi đúng nhu cầu.

## 14. Bài tập và đáp án

**Bài 1.** Hai `@Bean` cùng tên `client` nhưng một trả `MailClient`, một trả `SmsClient`. Đã có xung đột tên chưa?

**Đáp án:** Có thể có nếu cả hai định nghĩa cùng được đưa vào **một registry dưới name client**; class khác không làm mất va chạm. Xử lý thực tế qua `@Bean` parsing có thể có các bước riêng; kiểm tra kết quả đăng ký thay vì suy diễn chắc thứ tự thắng.

**Bài 2.** Hai beans tên `firstClient` và `secondClient` cùng implement interface `Client`. `allowBeanDefinitionOverriding=false` có chặn chúng không?

**Đáp án:** Không vì tên khác nhau. Nếu injection một `Client` không có lựa chọn duy nhất, đó là autowiring ambiguity và cần qualifier/primary/tái thiết kế.

**Bài 3.** Trong nhánh denied, vì sao sau lỗi vẫn nhận `FIRST`?

**Đáp án:** Registration SECOND bị từ chối trước refresh, definition FIRST không bị thay. Context vẫn có thể refresh với definition hợp lệ còn lại.

**Bài 4.** Trong nhánh allowed, tại sao chỉ có một bean name `notificationClient` dù đăng ký hai lần?

**Đáp án:** Định nghĩa mới đã thay định nghĩa cũ **dưới cùng key** trước refresh, không tạo hai beans riêng cùng tên trong registry.

**Bài 5.** Alias `preferredClient` là một bean mới không?

**Đáp án:** Không. Nó là tên phụ tra cùng bean; `aliasSameInstance=true` và `aliasIsDefinition=false` chứng minh điều đó.

**Bài 6.** Vì sao một ứng dụng Spring Boot báo lỗi override còn demo Framework thuần có thể cho phép?

**Đáp án:** Mặc định policy khác nhau. Framework DefaultListableBeanFactory thường cho phép; Boot đặt mặc định cấm. Xác minh policy ở môi trường thật và chỉ bật override nếu có chủ đích.

**Bài 7.** Có nên chuyển policy sang true sau khi context đã chạy để đổi implementation không?

**Đáp án:** Không coi đây là cách hot swap. Metadata và singleton references có thể đã được cache/inject; nên cấu hình đúng từ bootstrap hoặc dùng cơ chế reconfiguration phù hợp.

## 15. Checklist ứng dụng thực tế

- [ ] Mỗi bean có tên rõ ràng, tránh chiếm name generic mà thư viện khác có thể dùng.
- [ ] Biết bean name là registry key, không phải class name, alias hay type.
- [ ] Phân biệt collision cùng name với ambiguity nhiều beans cùng type.
- [ ] Nắm `setAllowBeanDefinitionOverriding(false/true)` và mặc định Framework/Boot.
- [ ] Đặt policy **trước khi đăng ký/refresh** nếu tự sở hữu context.
- [ ] Nếu cấm: biết đọc `BeanDefinitionOverrideException` và tên gây xung đột.
- [ ] Nếu cho phép: kiểm tra bean runtime thực sự là definition mong muốn.
- [ ] Hiểu alias không sinh bean definition thứ hai.
- [ ] Không tin rằng thứ tự source code của nhiều cấu hình bảo đảm ai thắng.
- [ ] Không dùng overriding làm cơ chế thay bean đã khởi tạo.
- [ ] Kiểm tra các nguồn @Bean, scanning, XML/API và framework integration.
- [ ] Chạy Java 17+ Maven/`javac`/`java` và đối chiếu **10 dòng stdout**.
- [ ] Có startup smoke test phát hiện collision bất ngờ khi thêm module.
- [ ] Chỉ cho phép override khi có hợp đồng rõ và có test chứng minh đúng implementation.

**Kết luận:** Xung đột tên trong Spring là xung đột **cùng registry key của BeanDefinition**. Khi cấm overriding, đăng ký trùng bị từ chối; khi cho phép, definition đến sau có thể thay definition trước theo quy tắc đăng ký. Hãy dùng **chính sách tường minh**, phân biệt alias và nhiều bean cùng kiểu, đồng thời ưu tiên **sửa thiết kế registration** trước khi bật override chỉ để ứng dụng khởi động.

### Tài liệu chính thức

- [DefaultListableBeanFactory — Bean Definition Overriding](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/beans/factory/support/DefaultListableBeanFactory.html)
- [GenericApplicationContext — registerBeanDefinition / setAllowBeanDefinitionOverriding](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/context/support/GenericApplicationContext.html)
- [BeanDefinitionOverrideException API](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/beans/factory/support/BeanDefinitionOverrideException.html)
- [Spring Boot — Common Application Properties](https://docs.spring.io/spring-boot/appendix/application-properties/)
