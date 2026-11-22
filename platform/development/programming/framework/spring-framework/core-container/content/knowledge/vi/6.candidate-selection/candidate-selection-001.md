# Tra cứu ứng viên theo kiểu có thể gán trong Spring Core Container

## 1. Từ kiểu được yêu cầu đến tập bean ứng viên

Spring Dependency Injection thường bắt đầu từ câu hỏi: **“Có những bean nào có kiểu có thể gán (*assignable*) vào kiểu mà injection point yêu cầu?”** Ví dụ một service có constructor nhận `Channel`, nhưng container có hai class `EmailChannel` và `SmsChannel` cùng implement `Channel`. Cả hai có thể **khớp về kiểu** mà vẫn chưa thể chọn một bean duy nhất.

Hãy phân biệt ba việc:

1. **Type matching (khớp kiểu):** bean được khai báo hoặc được suy ra là có type phù hợp với interface/superclass được yêu cầu không?
2. **Autowire candidate filtering (lọc ứng viên):** bean khớp kiểu ấy có được phép tham gia quá trình tự động tiêm dependency tại điểm inject không? Có bị loại bởi `autowireCandidate=false`, qualifier, điều kiện khác không?
3. **Single-candidate selection (chọn một bean):** nếu còn nhiều ứng viên hợp lệ, Spring dùng `@Primary`, `@Qualifier`, metadata và các quy tắc ưu tiên khác để chọn hoặc báo ambiguity.

**Một bean khớp type chưa chắc là một autowire candidate hợp lệ; một danh sách nhiều type matches cũng không có nghĩa injection luôn thất bại.** Với collection injection, Spring còn có thể đưa **nhiều beans** thích hợp vào cùng `List<T>` hoặc `Map<String,T>`.

| Câu hỏi | API/cơ chế | Trả lời |
| --- | --- | --- |
| Class Java có thể gán vào một interface hoặc superclass? | `isAssignableFrom`, `instanceof` | Quan hệ kiểu trong **Java** |
| Container biết tên những beans nào khớp type? | `getBeanNamesForType(Type.class)` | Danh sách **tên beans phù hợp type**, chưa nhất thiết lọc đúng injection point |
| Cần instances của các beans khớp type? | `getBeansOfType(Type.class)` | Map **bean name → bean object**, có thể khởi tạo beans |
| Một bean cụ thể có khớp type? | `isTypeMatch("beanName", Type.class)` | Kiểm tra type của bean được chỉ định |
| Cần đúng một bean theo type? | `getBean(Type.class)` | Trả bean hoặc lỗi nếu thiếu/mơ hồ, với quy tắc ưu tiên tương ứng |
| Một constructor cần type `T`? | `@Autowired`/factory-method parameter | Resolution của một **injection point**, còn phải lọc candidates |
| Cần tất cả beans được phép autowire kiểu `T`? | `@Autowired List<T>`, `Map<String,T>` | Tập các dependency candidates phù hợp, có thể được sắp thứ tự |

Mục tiêu bài: đọc đúng quan hệ **assignable type**, kiểm chứng tác động của inheritance/interface/generic, nhìn rõ khác biệt giữa **tra cứu theo type** và **lọc ứng viên autowiring**, rồi xác định khi nào phải dùng `@Primary`/`@Qualifier`.

Bài sử dụng **Java 17+**, **Spring Framework 7.0.9**, Maven và CLI. Đây là Spring Core Container thuần, không yêu cầu Spring Boot hoặc môi trường web.

## 2. “Có thể gán” trong Java nghĩa là gì?

Trong Java, `Child extends Parent` và `Implementation implements Contract` tạo các quan hệ kiểu. Nếu phương thức cần `Parent`, một object `Child` hợp lệ có thể được truyền vào; nếu cần `Contract`, object của class implement `Contract` cũng hợp lệ.

~~~java
// Snippet minh họa, không phải file biên dịch độc lập.
interface Channel {
    String id();
}
abstract class BaseChannel implements Channel { }
class EmailChannel extends BaseChannel {
    public String id() { return "EMAIL"; }
}
class SmsChannel extends BaseChannel {
    public String id() { return "SMS"; }
}
~~~

Những biểu thức sau có ý nghĩa:

~~~java
Channel a = new EmailChannel();        // Hợp lệ: EmailChannel implements Channel gián tiếp.
BaseChannel b = new SmsChannel();      // Hợp lệ: SmsChannel extends BaseChannel.
boolean yes = Channel.class.isAssignableFrom(SmsChannel.class);
boolean no = SmsChannel.class.isAssignableFrom(Channel.class);
~~~

**Đọc đúng hướng của `Class.isAssignableFrom`:**

`Target.class.isAssignableFrom(Source.class)` hỏi: một value thuộc **Source** có thể dùng tại vị trí mong đợi **Target** theo quan hệ kiểu thông thường không? Vì vậy:
- `Channel.class.isAssignableFrom(EmailChannel.class)` → `true`;
- `BaseChannel.class.isAssignableFrom(SmsChannel.class)` → `true`;
- `EmailChannel.class.isAssignableFrom(Channel.class)` → `false`.

Đây là ví dụ về **reference type compatibility**, không phải chuyển đổi giá trị tùy ý. Nếu một bean thực là `SmsChannel`, Spring không thể tiêm nó vào field kiểu `EmailChannel` chỉ vì cả hai cùng có interface `Channel`. Chúng là hai class sibling, không có quan hệ assignability từ SMS sang Email.

**Ghi nhớ chiều matching**: injection point đòi `Channel` thì `SmsChannel` có thể phù hợp; injection point đòi `SmsChannel` thì một bean chỉ biết là `Channel` **không được mặc nhiên coi là** `SmsChannel`.

Spring còn sử dụng **type metadata, factory methods, generics và proxy information**. Do đó việc Spring biết/tiên đoán type trước khi tạo object có thể phức tạp hơn một lần gọi `isAssignableFrom` với runtime class của object.

## 3. Spring lấy thông tin type từ đâu?

Nguồn thông tin type không chỉ có một:

- **Component-scanned class:** từ bean class được phát hiện (`@Component`, `@Service`, …), class hierarchy, interfaces và metadata đăng ký.
- **`@Bean` factory method:** Spring có thể dựa vào **declared return type** của factory method trước khi instance thực được tạo.
- **XML bean definitions:** từ `class`, factory-method/factory-bean metadata và những thông tin container suy ra.
- **Bean instance đã được tạo:** Spring có thể dùng type đã biết của instance khi thích hợp; tuy nhiên proxy có thể thay đổi runtime class/kiểu mà caller nhìn thấy.
- **`FactoryBean<T>`:** tên bean thường đại diện cho **sản phẩm** `T`, trong khi bản thân factory được tham chiếu bằng dạng `&beanName`. Type prediction còn liên quan `getObjectType()`.
- **Generic metadata:** `ResolvableType` và chữ ký generic giúp phân biệt `Store<String>` với `Store<Integer>`.

Ví dụ cần chú ý khi cấu hình `@Bean`:

~~~java
// Snippet minh họa, không phải project độc lập:
@Bean
Channel smsChannel() {
    return new SmsChannel();
}
~~~

Dù method **trả về instance** của `SmsChannel`, *declared return type* của nó là `Channel`. Trước khi bean được tạo, Spring **không nhất thiết biết** nó có type cụ thể `SmsChannel` để resolve một injection point yêu cầu subclass. Vì vậy tài liệu Spring khuyến nghị chữ ký `@Bean` **đủ cụ thể** khi bạn định inject theo implementation type:

~~~java
@Bean
SmsChannel smsChannel() {
    return new SmsChannel();
}
~~~

Khi injection chỉ cần `Channel`, cả hai kiểu khai báo có thể đáp ứng; nhưng nếu injection yêu cầu `SmsChannel`, kiểu trả về cụ thể làm metadata ổn định và rõ ràng hơn.

**Không dùng kết quả runtime `getClass()` làm lý do bỏ qua chữ ký public API**. Với generic, proxies, `FactoryBean` và lazy beans, dựa vào class runtime duy nhất rất dễ dự đoán sai những type matches mà Spring có thể biết trong từng giai đoạn.

## 4. Hai nhóm API: khám phá type và lấy dependency

### 4.1. `getBeanNamesForType`: khám phá tên

~~~java
String[] names = context.getBeanNamesForType(Channel.class);
~~~

API thuộc `ListableBeanFactory` (được `ApplicationContext` cung cấp) trả về tên của các beans có type tương thích với `Channel`, **bao gồm subclass/implementation**.

- Không cần giả định chỉ tìm bean có `getClass() == Channel.class`: interface thường không thể instantiate trực tiếp.
- Trả về **tên**, không phải `Channel` objects.
- Kết quả có thể gồm bean mà **autowire-candidate filtering** sẽ loại khi xử lý injection point.
- Đây không phải danh sách aliases: alias không tự nhân số bean definitions/instances.
- Thứ tự trả về có thể liên quan thứ tự đăng ký; muốn assert chính xác trong bài, hãy **sort** trước khi in.
- Container nội bộ có nhiều infrastructure beans; chỉ liệt kê **type cụ thể của chủ đề**, không in toàn bộ `getBeanDefinitionNames()` rồi kết luận số lượng cố định.

### 4.2. `getBeansOfType`: lấy cả instances

~~~java
Map<String, Channel> beans = context.getBeansOfType(Channel.class);
~~~

API trả map tên→instance, có thể gây khởi tạo bean và callbacks liên quan. Nó **khác** việc Spring inject `Map<String,Channel>` tại một injection point:

- `getBeansOfType(Channel.class)` là **liệt kê tất cả beans khớp type** theo hành vi của API.
- `@Autowired Map<String,Channel>` còn chịu **autowire candidate rules**: bean `autowireCandidate=false` có thể bị bỏ khỏi injected map, dù vẫn xuất hiện trong các API discovery/get-by-name.

Đây là bẫy phổ biến khi debug: “`getBeanNamesForType` tìm thấy ba beans, sao `List<Channel>` được tiêm chỉ có hai?” — vì **type matching và injectability là hai bước khác nhau**.

### 4.3. `isTypeMatch`, `getBean(Class)` và `getBean(name, Class)`

- `context.isTypeMatch("smsChannel", BaseChannel.class)` kiểm tra named bean có phù hợp với superclass này không.
- `context.getBean(Channel.class)` cần chọn **một bean** có thể gán cho type ấy; nhiều ứng viên không có quy tắc ưu tiên phù hợp có thể ném `NoUniqueBeanDefinitionException`.
- `context.getBean("smsChannel", Channel.class)` lấy **bean theo tên**, đồng thời kiểm tra type tương thích; không chọn một bean khác ngẫu nhiên.

`@Primary`, `@Qualifier`, bean name và những chính sách khác tham gia resolution theo ngữ cảnh cụ thể. Đừng suy luận rằng một bean được trả về do “chính xác type trùng tên method” mà không xét metadata.

## 5. Type matching không đồng nghĩa autowire candidate selection

**`autowireCandidate=false`** cho phép giữ một bean trong context để tra cứu chủ động nhưng **loại nó khỏi type-based autowiring** thông thường.

~~~java
// Snippet nằm trong @Configuration phù hợp:
@Bean(name = "localChannel", autowireCandidate = false)
LocalChannel localChannel() {
    return new LocalChannel();
}
~~~

Hệ quả:
1. Bean `localChannel` vẫn có tên/định nghĩa, Spring vẫn có thể tạo object theo cơ chế bean.
2. `getBean("localChannel")` vẫn có thể truy cập nó theo tên.
3. `getBeanNamesForType(Channel.class)` vẫn có thể **phát hiện** type match của nó.
4. Nhưng Spring **không dùng nó làm candidate autowiring** cho `@Autowired Channel`, `@Autowired List<Channel>` hay constructor parameter cần `Channel`.

Với Spring 7, `@Bean` còn có metadata `defaultCandidate`, `@Primary`, `@Fallback` và các cách fine-tune độ ưu tiên khi chọn bean. Không nên gom tất cả thành một boolean duy nhất “match hoặc không match”. `autowireCandidate=false` là **loại bean khỏi autowiring candidates**, còn `@Primary` nói rằng một candidate được ưu tiên trong một số tình huống lựa chọn **một** dependency.

| Trạng thái bean | Type match? | Có thể xuất hiện trong discovery? | Candidate autowiring thông thường? |
| --- | --- | --- | --- |
| `EmailChannel` bình thường | Có, với `Channel` và `BaseChannel` | Có | Có |
| `SmsChannel` bình thường | Có | Có | Có |
| `LocalChannel` với `autowireCandidate=false` | Có | Có | **Không** |
| `EmailChannel` đánh dấu `@Primary` | Có | Có | Có, thường được ưu tiên khi cần một bean |
| Class hoàn toàn không implements `Channel` | Không | Không theo type `Channel` | Không theo type `Channel` |

**Lưu ý:** `getBeanNamesForType` là API **khám phá đối tượng phù hợp type**, không phải API “lấy duy nhất tất cả candidate cuối cùng ở mọi injection point”. `@Qualifier`, generic type và thông tin injection point có thể lọc tập kết quả theo những cách mà một call `getBeanNamesForType(Channel.class)` không diễn đạt đủ.

## 6. Khi nhiều ứng viên cùng có thể gán, Spring chọn thế nào?

Kết quả `getBeanNamesForType(Channel.class)` có thể chứa nhiều bean hợp kiểu, nhưng một điểm tiêm `Channel` chỉ nhận **một** bean. Khi đó Spring còn kiểm tra quyền tham gia autowiring, các qualifier, quy tắc ưu tiên và metadata của injection point. Nếu còn nhiều ứng viên ngang nhau, phép chọn đơn trị có thể thất bại với `NoUniqueBeanDefinitionException`.

| Nhu cầu | Hướng giải quyết | Ranh giới |
| --- | --- | --- |
| Một implementation mặc định | `@Primary` | Không xóa ứng viên khác và không sắp thứ tự khởi tạo |
| Một implementation theo vai trò | `@Qualifier` tại injection point | Chỉ lọc những bean vẫn hợp kiểu và đủ điều kiện |
| Một bean dự phòng | `@Fallback` (Spring 6.2+) | Hạ ưu tiên, không tạo failover khi chạy |
| Tất cả implementations | `List<Channel>` / `Map<String, Channel>` | Chọn tập hợp, không yêu cầu một ứng viên duy nhất |

Bài kế tiếp phân tích từng nhánh resolution với các context độc lập. Ở bài này, điểm cần giữ là **type discovery là điều kiện đầu vào, chưa phải kết quả dependency injection**.

## 7. Generic types cũng tham gia xác định candidates

Khi điểm tiêm yêu cầu `Store<Channel>`, Spring có thể dùng chữ ký generic đã biết của bean definition hoặc factory method để lọc ngoài kiểm tra raw type. `Store<Channel>` và `Store<String>` đều có raw type `Store`, nhưng không mặc nhiên thay thế nhau. Chữ ký `@Bean Store<Channel> channelStore()` thể hiện hợp đồng rõ hơn `@Bean Store rawStore()`.

Đây là metadata ở cấp khai báo; Spring không “phục hồi” mọi tham số kiểu từ object sau type erasure. Nếu factory method khai raw type, generic metadata có thể thiếu và cần điều tra dựa trên khai báo thực tế. Generic filtering cũng **không** giải quyết mơ hồ khi có hai bean cùng đầy đủ type. Bài chuyên sâu về generic qualifier sẽ thử trường hợp này với single bean, collection và qualifier bổ sung.

## 8. Demo đầy đủ Java 17 + Maven + Spring 7.0.9

Demo cho thấy:
- Hai class `EmailChannel` và `SmsChannel` **extends `BaseChannel` và implements `Channel`**, còn SMS thêm interface `Auditable`.
- `LocalChannel` vẫn match type `Channel` nhưng khai `autowireCandidate=false`; nó **có trong type discovery nhưng vắng khỏi injected list/map**.
- `EmailChannel` là `@Primary`; single dependency `Channel` chọn EMAIL.
- Injection theo `Auditable` nhận SMS; generic `Vault<String>` khác `Vault<Integer>`.
- Một context khác không có primary sẽ dẫn tới ambiguity khi tra đúng một `Channel` theo type.

Toàn bộ code nằm trong **một file Java**, không cần database, web server hoặc Spring Boot. Các thao tác in danh sách luôn được `Arrays.sort`/`sorted()` để có **stdout ổn định**, không phụ thuộc vào thứ tự bean registrations.

### 8.1. Cấu trúc project

~~~text
assignable-candidates-demo/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── demo/
                └── AssignableCandidatesDemo.java
~~~

Yêu cầu **JDK 17+**, **Maven 3.9+**, kết nối Maven Central/mirror nếu thư viện chưa nằm trong local cache.

### 8.2. `pom.xml`

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>assignable-candidates-demo</artifactId>
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
                <configuration>
                    <mainClass>demo.AssignableCandidatesDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

`spring-context` đem theo các Spring modules cơ bản qua Maven transitive dependency resolution. `maven.compiler.release=17` dùng Java 17 bytecode/API. Ví dụ chỉ có Java configuration.

### 8.3. `src/main/java/demo/AssignableCandidatesDemo.java`

~~~java
package demo;

import java.util.Arrays;
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;

import org.springframework.beans.factory.NoUniqueBeanDefinitionException;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Primary;
import org.springframework.core.ResolvableType;

public final class AssignableCandidatesDemo {
    private AssignableCandidatesDemo() {
    }

    interface Channel {
        String id();
    }

    interface Auditable {
        String auditTag();
    }

    abstract static class BaseChannel implements Channel {
    }

    static final class EmailChannel extends BaseChannel {
        @Override public String id() {
            return "EMAIL";
        }
    }

    static final class SmsChannel extends BaseChannel implements Auditable {
        @Override public String id() {
            return "SMS";
        }

        @Override public String auditTag() {
            return "SMS-AUDIT";
        }
    }

    static final class LocalChannel extends BaseChannel {
        @Override public String id() {
            return "LOCAL";
        }
    }

    @FunctionalInterface
    interface Vault<T> {
        String kind();
    }

    static final class Consumer {
        private final Channel primary;
        private final Auditable audit;
        private final List<Channel> channels;
        private final Map<String, Channel> channelMap;
        private final Vault<String> stringVault;
        private final List<Vault<Integer>> integerVaults;

        Consumer(Channel primary, Auditable audit,
                List<Channel> channels, Map<String, Channel> channelMap,
                Vault<String> stringVault, List<Vault<Integer>> integerVaults) {
            this.primary = primary;
            this.audit = audit;
            this.channels = channels;
            this.channelMap = channelMap;
            this.stringVault = stringVault;
            this.integerVaults = integerVaults;
        }

        String primaryName() {
            return primary.id();
        }

        String auditTag() {
            return audit.auditTag();
        }

        String channelList() {
            return channels.stream().map(Channel::id)
                    .sorted().collect(Collectors.joining(","));
        }

        String mapKeys() {
            return channelMap.keySet().stream()
                    .sorted().collect(Collectors.joining(","));
        }

        String textKind() {
            return stringVault.kind();
        }

        String integerKinds() {
            return integerVaults.stream().map(Vault::kind)
                    .sorted().collect(Collectors.joining(","));
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class AppConfig {
        @Bean("emailChannel")
        @Primary
        public EmailChannel email() {
            return new EmailChannel();
        }

        @Bean("smsChannel")
        public SmsChannel sms() {
            return new SmsChannel();
        }

        @Bean(name = "localChannel", autowireCandidate = false)
        public LocalChannel local() {
            return new LocalChannel();
        }

        @Bean
        public Vault<String> stringVault() {
            return () -> "STRING";
        }

        @Bean
        public Vault<Integer> integerVault() {
            return () -> "INTEGER";
        }

        @Bean
        public Consumer consumer(
                Channel selected,
                @Qualifier("smsChannel") Auditable audit,
                List<Channel> channels,
                Map<String, Channel> channelsByName,
                Vault<String> stringVault,
                List<Vault<Integer>> integerVaults) {
            return new Consumer(selected, audit, channels,
                    channelsByName, stringVault, integerVaults);
        }
    }

    // Cố ý không dùng @Primary để minh họa ambiguity.
    @Configuration(proxyBeanMethods = false)
    public static class AmbiguousConfig {
        @Bean
        public EmailChannel first() {
            return new EmailChannel();
        }

        @Bean
        public SmsChannel second() {
            return new SmsChannel();
        }
    }

    private static String names(String[] values) {
        Arrays.sort(values);
        return String.join(",", values);
    }

    private static String keys(Map<String, ?> map) {
        return map.keySet().stream()
                .sorted().collect(Collectors.joining(","));
    }

    public static void main(String[] args) {
        System.out.println("java.channelFromEmail="
                + Channel.class.isAssignableFrom(EmailChannel.class));
        System.out.println("java.emailFromChannel="
                + EmailChannel.class.isAssignableFrom(Channel.class));
        System.out.println("java.baseFromSms="
                + BaseChannel.class.isAssignableFrom(SmsChannel.class));
        System.out.println("java.auditFromSms="
                + Auditable.class.isAssignableFrom(SmsChannel.class));

        try (var context =
                new AnnotationConfigApplicationContext(AppConfig.class)) {
            System.out.println("type.channel="
                    + names(context.getBeanNamesForType(Channel.class)));
            System.out.println("type.base="
                    + names(context.getBeanNamesForType(BaseChannel.class)));
            System.out.println("type.email="
                    + names(context.getBeanNamesForType(EmailChannel.class)));
            System.out.println("type.audit="
                    + names(context.getBeanNamesForType(Auditable.class)));
            System.out.println("type.unknown="
                    + context.getBeanNamesForType(Runnable.class).length);
            System.out.println("type.smsIsBase="
                    + context.isTypeMatch("smsChannel", BaseChannel.class));
            System.out.println("type.localRegistered="
                    + context.containsBeanDefinition("localChannel"));
            System.out.println("type.localByName="
                    + context.getBean("localChannel", Channel.class).id());
            System.out.println("type.allObjects="
                    + keys(context.getBeansOfType(Channel.class)));

            Consumer consumer = context.getBean(Consumer.class);
            System.out.println("wire.primary=" + consumer.primaryName());
            System.out.println("wire.audit=" + consumer.auditTag());
            System.out.println("wire.list=" + consumer.channelList());
            System.out.println("wire.map=" + consumer.mapKeys());
            System.out.println("wire.stringVault=" + consumer.textKind());
            System.out.println("wire.integerVaults=" + consumer.integerKinds());

            ResolvableType textType =
                    ResolvableType.forClassWithGenerics(
                            Vault.class, String.class);
            ResolvableType intType =
                    ResolvableType.forClassWithGenerics(
                            Vault.class, Integer.class);
            System.out.println("type.vault.text="
                    + names(context.getBeanNamesForType(textType)));
            System.out.println("type.vault.integer="
                    + names(context.getBeanNamesForType(intType)));
        }

        // Với hai candidates cùng type nhưng không có primary.
        try (var context = new AnnotationConfigApplicationContext(
                AmbiguousConfig.class)) {
            context.getBean(Channel.class);
            System.out.println("unexpected");
        } catch (NoUniqueBeanDefinitionException expected) {
            System.out.println("ambiguousLookup.failed=true");
        }
    }
}
~~~

### 8.4. Vì sao ví dụ là một phép so sánh hợp lệ?

- `emailChannel`, `smsChannel` và `localChannel` đều có Java class extends `BaseChannel`. Vì `BaseChannel implements Channel`, **cả ba types** đều assignable sang `Channel`.
- Chỉ `SmsChannel` implements `Auditable`, nên `getBeanNamesForType(Auditable.class)` có đúng một bean tên `smsChannel`.
- `EmailChannel` và `SmsChannel` đủ điều kiện autowiring; `LocalChannel` bị loại nhờ `@Bean(autowireCandidate=false)`.
- `getBeanNamesForType(Channel.class)` có thể phát hiện **cả ba**, vì API là **type discovery**, không phải autowiring candidate resolution cho một injection point.
- Inject một `Channel` vào method `consumer(...)` chọn **EMAIL** vì `@Primary` chỉ định một bean ưu tiên trong những candidates còn hợp lệ.
- Inject `List<Channel>` và `Map<String,Channel>` chỉ nhận **EMAIL/SMS**, không có `LOCAL`; đó là chứng cứ autowiring filtering không giống type discovery.
- Type `Auditable` + `@Qualifier("smsChannel")` chọn **SMS** bằng cả hợp đồng interface và qualifier.
- `Vault<String>`/ `Vault<Integer>` có chung raw interface nhưng tách theo **generic argument** nhờ metadata từ `@Bean` return signatures.
- Trong `AmbiguousConfig`, hai `Channel` cùng match type, không primary; `getBean(Channel.class)` không được tùy ý chọn một nên thất bại.

**Chú ý runtime:** `@Bean("emailChannel")` khai báo return type cụ thể là `EmailChannel`; `@Bean("smsChannel")` trả `SmsChannel`. Điều này giúp Spring nhận biết type tương ứng trước khi object được tạo. Demo không buộc Spring đoán implementation từ một factory method chỉ khai return type `Channel`.

## 9. Lệnh chạy và expected stdout

Trong thư mục `assignable-candidates-demo` chứa `pom.xml`, kiểm tra:

~~~bash
java -version
javac -version
mvn -version
mvn -q clean compile exec:java
~~~

Ba lệnh kiểm tra phiên bản có kết quả tùy máy. Lệnh Maven cuối chạy `javac` qua Compiler Plugin và sử dụng dependency classpath để chạy `demo.AssignableCandidatesDemo`.

**22 dòng stdout do chính chương trình in** (không tính Maven/backend logging):

~~~text
java.channelFromEmail=true
java.emailFromChannel=false
java.baseFromSms=true
java.auditFromSms=true
type.channel=emailChannel,localChannel,smsChannel
type.base=emailChannel,localChannel,smsChannel
type.email=emailChannel
type.audit=smsChannel
type.unknown=0
type.smsIsBase=true
type.localRegistered=true
type.localByName=LOCAL
type.allObjects=emailChannel,localChannel,smsChannel
wire.primary=EMAIL
wire.audit=SMS-AUDIT
wire.list=EMAIL,SMS
wire.map=emailChannel,smsChannel
wire.stringVault=STRING
wire.integerVaults=INTEGER
type.vault.text=stringVault
type.vault.integer=integerVault
ambiguousLookup.failed=true
~~~

**Quan sát then chốt:**
1. Bốn dòng `java.*` kiểm chứng Java `Class.isAssignableFrom`: interface/superclass nhận subclass/implementation, nhưng hướng ngược không hợp lệ.
2. `type.channel` và `type.base` đều có ba beans, còn `type.audit` chỉ có SMS — Spring xét **quan hệ type**, không chỉ so tên class bằng nhau.
3. `type.localRegistered=true`, `type.localByName=LOCAL` chứng minh bean loại khỏi autowiring **vẫn tồn tại và có thể lookup**.
4. `type.allObjects` liệt kê cả LOCAL, còn `wire.list`/`wire.map` **không có LOCAL**. Đây là sự phân biệt quan trọng nhất của ví dụ.
5. `wire.primary=EMAIL`: Spring chọn một trong những candidates nhờ `@Primary`, nhưng `wire.list` vẫn chứa SMS; primary không có nghĩa loại những beans khác khỏi injected collection.
6. `type.vault.*` tách đúng hai generic specializations; `Vault<String>` không bị coi như `Vault<Integer>`.
7. `ambiguousLookup.failed=true` là thất bại **có chủ đích** của lookup không có primary; chương trình catch `NoUniqueBeanDefinitionException`.

Lưu ý: nếu cố tình thay cấu hình tạo bean khác hoặc thay generic return signatures, **stdout chuẩn sẽ không còn đúng**. Nếu logger ghi thêm thông báo startup failure, chỉ so 22 dòng ứng dụng đã nêu; không cố định mọi stack trace ở terminal.

## 10. Java 17 thuần với `javac`/`java`

Tạo một file độc lập **`JavaAssignableTypes.java`**, không cần Maven hay Spring, để quan sát nền Java của khái niệm *assignable*.

~~~java
public class JavaAssignableTypes {
    interface Sender {
        String send();
    }

    abstract static class BaseSender implements Sender {
    }

    static final class SmsSender extends BaseSender {
        @Override
        public String send() {
            return "SMS";
        }
    }

    static final class EmailSender extends BaseSender {
        @Override
        public String send() {
            return "EMAIL";
        }
    }

    public static void main(String[] args) {
        Sender sms = new SmsSender();
        BaseSender email = new EmailSender();

        System.out.println("senderFromSms="
                + Sender.class.isAssignableFrom(SmsSender.class));
        System.out.println("baseFromEmail="
                + BaseSender.class.isAssignableFrom(EmailSender.class));
        System.out.println("smsFromSender="
                + SmsSender.class.isAssignableFrom(Sender.class));
        System.out.println("values=" + sms.send() + "," + email.send());
    }
}
~~~

Chạy trong thư mục chứa file:

~~~bash
javac JavaAssignableTypes.java
java JavaAssignableTypes
~~~

Stdout chính xác:

~~~text
senderFromSms=true
baseFromEmail=true
smsFromSender=false
values=SMS,EMAIL
~~~

Đây là **quan hệ kiểu Java thuần**. Spring tận dụng metadata của Java class/interface và bổ sung BeanDefinition, qualifier, scope, proxy và các quy tắc autowire candidate. Hãy hiểu quan hệ Java trước khi suy luận cách container chọn một bean từ nhiều registrations.

## 11. Các trường hợp đặc biệt và giới hạn của việc tra cứu type

### 11.1. Scope và lazy beans

`getBeanNamesForType(Class)` có thể tìm tên dựa trên metadata type của singleton, prototype, và các beans khác theo khả năng suy ra. Overload:

~~~java
context.getBeanNamesForType(Channel.class, true, false);
~~~

có hai cờ:
- `includeNonSingletons=true`: cho phép bao gồm prototype hoặc scoped beans;
- `allowEagerInit=false`: yêu cầu tránh một số kiểu eager initialization để xác định type, như khởi tạo `FactoryBean` hoặc factory tham chiếu cần xét type.

**Kết quả của hai overload có thể khác nhau**, nhất là khi type chưa thể biết mà không khởi tạo thêm metadata-producing objects. Đừng dùng một type-query với `allowEagerInit=true` trong code tưởng như chỉ “kiểm tra” rồi mặc nhiên suy luận không có tác dụng phụ hoặc startup cost.

### 11.2. `FactoryBean` và dấu `&`

Giả sử `widgetFactory` là một `FactoryBean<Widget>`:
- `getBean("widgetFactory")` có thể trả **Widget product**;
- `getBean("&widgetFactory")` trả **FactoryBean instance**;
- `getBeanNamesForType(Widget.class)` nhằm tìm type của **product**, nếu container có đủ metadata;
- Type prediction có thể dựa vào `getObjectType()` và chính sách `allowEagerInit`.

Vì vậy, nếu bạn debug mà thấy tên bean match một interface nhưng class của factory không implement interface ấy, hãy kiểm tra có `FactoryBean` hay không. Không nhầm `@Bean` factory method với việc class implements `FactoryBean<T>`: đây là hai cơ chế khác.

### 11.3. AOP proxy và type prediction

AOP có thể bọc đối tượng target trong một proxy. Với **JDK dynamic proxy**, proxy có thể chỉ lộ các interfaces, không phải concrete target class; với class-based proxy, quan hệ kiểu có thể khác. Khi một injection point đòi implementation class nhưng proxy chỉ phơi interface, type matching/injection có thể gặp vấn đề.

**Thực hành:** hãy inject qua một **interface hợp đồng** khi thích hợp, khai báo return type factory method rõ ràng và kiểm tra proxy mode. Không dựa vào `bean.getClass() == Implementation.class` để kết luận bean không phù hợp, vì đó có thể là proxy hợp lệ.

### 11.4. Parent/child application contexts

Một `ListableBeanFactory` lookup có thể chỉ tra **bean definitions cục bộ**; tài liệu API lưu ý những `getBeanNamesForType` methods không phải lúc nào cũng hợp nhất parent factory. Nếu thực sự cần names từ ancestor contexts, Spring có `BeanFactoryUtils.beanNamesForTypeIncludingAncestors(...)`.

Đừng nhầm **parent ApplicationContext** với `parent="templateBean"` trong bean definition inheritance. Một cái là hệ phân cấp containers, cái kia là kế thừa metadata của definitions.

### 11.5. Alias, visibility và no candidate

Bean alias không tạo additional bean definition. Một bean mang alias `backupSender` vẫn đại diện cho một bean, không làm danh sách type matches tự nhân đôi các instances.

`autowireCandidate=false` ảnh hưởng autowiring, không biến bean thành “không tồn tại”. Ngược lại, một class chỉ có trên classpath nhưng chưa được Spring đăng ký bằng `@Bean`, component scan hoặc API khác **không tự xuất hiện trong các type queries**.

**Đừng hiểu “chỉ tìm được một bean theo type” là chắc chắn bean hợp lệ ở mọi injection point**: qualifier có thể yêu cầu tên cụ thể khác, generic type có thể không khớp, hoặc candidate có thể bị loại bởi metadata. Những điều kiện ấy phải được xem trong ngữ cảnh của điểm tiêm.

## 12. Debug type matching và những lỗi thường gặp

| Hiện tượng hoặc nhận định sai | Nguyên nhân/cách điều tra đúng |
| --- | --- |
| `getBeanNamesForType(Channel.class)` trả nhiều tên | Nhiều subclasses/implementations cùng assignable; chưa phải lỗi |
| `getBean(Channel.class)` báo `NoUniqueBeanDefinitionException` | Lookup cần **một** instance nhưng nhiều candidates không có chính sách chọn |
| `@Autowired Channel` thiếu bean dù class implementation có trong project | Class chưa đăng ký thành bean, scope/profile/config không active hoặc bị lọc |
| Type discovery thấy bean nhưng `List<Channel>` không có nó | Có thể `autowireCandidate=false` hoặc qualifier/generic filtering |
| `@Primary` giúp inject một bean nhưng list vẫn có nhiều | Primary chỉ ưu tiên **single-valued resolution**, không xóa candidates khỏi collection |
| Injection theo implementation class thất bại | `@Bean` return type quá rộng, bean proxy chỉ lộ interface hoặc metadata không đủ |
| `getBeanNamesForType(SmsChannel.class)` không thấy bean do factory tạo | Kiểm tra declared return type, `FactoryBean`/type prediction, lazy init |
| Generic injection `Vault<String>` chọn sai/không tìm thấy | Kiểm chữ ký return type, generic metadata, `ResolvableType` |
| Bean excluded khỏi autowiring vẫn truy cập được bằng tên | `autowireCandidate=false` chỉ loại candidate chứ không xóa bean |
| `isAssignableFrom` trả ngược dự đoán | Nhầm hướng Target/Source: `Target.isAssignableFrom(Source)` |
| Lấy theo type có cảnh báo type không duy nhất | Thử `getBeanNamesForType` để quan sát candidate names rồi dùng primary/qualifier |
| Có bean nhưng class bị proxy | Kiểm interface/class proxy, đừng so runtime class bằng equality |
| `getBeansOfType` làm ứng dụng khởi tạo sớm | API trả **instances**, có thể tạo beans/lifecycle callbacks |
| Bean tên giống field nhưng type không khớp | Name không làm Java reference trở nên assignable; sửa hợp đồng type |
| Không thấy bean từ parent context | Tìm hiểu context hierarchy và `BeanFactoryUtils` |
| Khó đọc log lỗi autowiring | Xem `UnsatisfiedDependencyException`, `NoSuchBeanDefinitionException`, `NoUniqueBeanDefinitionException` và cause chain |

**Quy trình debug đề xuất:**
1. Xác nhận đúng context/bean registrations và `@Bean` declared return types.
2. Kiểm thử `getBeanNamesForType(RequiredType.class)`; sort kết quả nếu cần snapshot.
3. Nếu đã có type matches nhưng injection thiếu, kiểm metadata **`autowireCandidate`**, qualifier, generic type, primary/fallback và visibility.
4. Nếu có nhiều candidates, xác định injection đang cần một bean hay collection/map.
5. Nếu xảy ra ambiguity, dùng `@Primary` hoặc qualifier **có chủ đích**, không chỉ đổi tên field để dựa vào fallback.
6. Với factory/proxy/generics, sử dụng `ResolvableType`, `isTypeMatch`, API bean factory và debugger khi cần.
7. Test riêng hành vi Java class, container wiring và integration boundaries; đừng trông đợi type matching tự chứng minh behavior nghiệp vụ.

## 13. Bài tập tự kiểm chứng và checklist

Làm từng thử nghiệm trên bản sao và khôi phục code trước khi so expected stdout:

1. **Thêm subclass:** tạo `PushChannel extends BaseChannel`, đăng ký `@Bean PushChannel`. Dự đoán type lists và injected list/map thay đổi thế nào.
2. **Đổi @Primary:** chuyển primary từ Email sang SMS; dự đoán `wire.primary=SMS` nhưng `wire.list` vẫn chứa cả hai.
3. **Bỏ @Primary:** ở `AppConfig`, hai candidates hợp lệ `Channel` sẽ trở nên mơ hồ tại factory method `consumer(Channel selected,...)`; context có thể fail sớm.
4. **Đổi autowireCandidate:** bỏ `autowireCandidate=false` của Local. Dự đoán discovery giữ nguyên ba beans nhưng injected list/map giờ có thêm LOCAL.
5. **Lấy Local bằng tên:** thực hiện `context.getBean("localChannel", Channel.class)` và giải thích vì sao nó vẫn hoạt động khi Local excluded from autowiring.
6. **Đổi type injection:** thay `Channel` bằng `SmsChannel` trong một method parameter, giải thích vì sao chỉ SMS thỏa.
7. **Thử interface riêng:** inject `Auditable`, quan sát chỉ `SmsChannel` implement interface ấy.
8. **Đổi kiểu trả về `@Bean`:** sửa `SmsChannel sms()` thành `Channel sms()`, so kết quả type prediction trước khi khởi tạo.
9. **Thêm qualifier:** sử dụng `@Qualifier("smsChannel")` trên `Channel` parameter của consumer thay vì dựa vào primary; xác nhận cách lọc.
10. **Generic mismatch:** đổi `Vault<String>` thành `Vault<Integer>` cho parameter `stringVault`, nghiên cứu vì sao generic metadata dẫn tới thay candidate hoặc fail vì không tương thích mong đợi.
11. **Thêm Vault<Long>:** đăng ký thêm một bean `Vault<Long>`; kiểm `getBeanNamesForType(ResolvableType.forClassWithGenerics(...))` theo từng type argument.
12. **Thử prototype:** đặt `@Scope("prototype")` trên một channel và so `getBeanNamesForType` với `getBean` lặp lại; type membership không hàm ý identity singleton.
13. **No unique bean:** chạy `AmbiguousConfig`, giải thích vì sao `getBean(Channel.class)` không chọn “first” dù thứ tự đăng ký rõ ràng.
14. **Tách self-reference:** thử autowire chính bean đang tạo và xem vì sao self-injection là fallback, không phải lựa chọn primary thông thường.
15. **Java standalone:** sửa `JavaAssignableTypes` cho `EmailSender` implement một interface mới, dùng `Class.isAssignableFrom` kiểm tra loại nào có thể gán.
16. **FactoryBean:** tạo thử một `FactoryBean<Channel>`, phân biệt lookup bằng bean name và `&beanName`; đọc `getObjectType()` trước khi nhận định type-query.

### Checklist

- [ ] Hiểu `Target.class.isAssignableFrom(Source.class)` theo **đúng chiều**.
- [ ] Biết bean implementation/subclass có thể match interface/superclass injection point.
- [ ] Không nhầm `getBeanNamesForType` với tập candidates đã qua autowiring filters.
- [ ] Biết `autowireCandidate=false` vẫn cho phép lookup theo tên hoặc type discovery.
- [ ] Biết `@Primary` giải quyết single-valued injection, không xóa bean khỏi list/map.
- [ ] Biết `@Qualifier`, generic type và `@Fallback` có thể ảnh hưởng lựa chọn.
- [ ] Đọc đúng `getBeanNamesForType`, `getBeansOfType`, `isTypeMatch`, `getBean(Class)`.
- [ ] Phân biệt raw generic type với `ResolvableType` và declared `@Bean` return type.
- [ ] Dự đoán chính xác 22 dòng stdout Spring Maven và 4 dòng Java thuần.
- [ ] Biết các giới hạn FactoryBean, lazy/scope, proxy và parent contexts.

## 14. Kết luận và tài liệu chính thức

**Kết luận:** *Assignable type* là **bước xác định tập beans có kiểu phù hợp**, nhưng lựa chọn ứng viên trong Spring còn phụ thuộc **autowire eligibility, qualifiers, generics, primary/fallback, scope và bối cảnh injection point**. Một bean có type khớp **không mặc nhiên** được inject; ngược lại, nhiều type matches có thể được Spring resolve thành đúng một bean hoặc một collection có chủ đích.

Nguồn tra cứu:
- [Spring Framework — Using @Autowired](https://docs.spring.io/spring-framework/reference/core/beans/annotation-config/autowired.html)
- [Spring Framework — Autowiring Collaborators](https://docs.spring.io/spring-framework/reference/core/beans/dependencies/factory-autowire.html)
- [Spring Framework — Fine-tuning Annotation-based Autowiring with Qualifiers](https://docs.spring.io/spring-framework/reference/core/beans/annotation-config/autowired-qualifiers.html)
- [Spring Framework — Primary and Fallback](https://docs.spring.io/spring-framework/reference/core/beans/annotation-config/autowired-primary.html)
- [Spring Framework — Generics as Autowiring Qualifiers](https://docs.spring.io/spring-framework/reference/core/beans/annotation-config/generics-as-qualifiers.html)
- [Spring API — `ListableBeanFactory`](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/beans/factory/ListableBeanFactory.html)
- [Spring API — `ResolvableType`](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/core/ResolvableType.html)
- [Java 17 — `Class.isAssignableFrom`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html#isAssignableFrom(java.lang.Class))

**Ghi nhớ để áp dụng:** Khi debug một dependency chưa được inject, hãy đi theo thứ tự **Java type compatibility → Spring type discovery → autowire filtering → chọn single candidate hoặc nhiều candidates → instance lifecycle**. Cách suy luận này chính xác hơn câu nói “Spring thấy cùng interface là tự tiêm vào”.