# Giải quyết một phụ thuộc có nhiều bean cùng kiểu — Spring Framework Core Container

## 1. Vấn đề: Spring thấy nhiều bean hợp kiểu, nhưng dependency chỉ nhận một

Giả sử ứng dụng có interface `MessageSender` và hai Spring beans:

~~~java
@Bean("emailSender")
MessageSender emailSender() {
    return new EmailSender();
}

@Bean("smsSender")
MessageSender smsSender() {
    return new SmsSender();
}
~~~

**Snippet minh họa:** chưa có interface, implementation và cấu hình đầy đủ; ví dụ Java 17 chạy được nằm ở mục 7.

Một service cần **chính một** sender:

~~~java
public AlertService(MessageSender sender) {
    this.sender = java.util.Objects.requireNonNull(sender);
}
~~~

Spring tìm những bean tương thích kiểu `MessageSender`, nhưng hiện có **hai** ứng viên: `emailSender` và `smsSender`. Nếu không có thêm chỉ dẫn đủ để chọn một, container **không được đoán tùy tiện**. Đối với một dependency đơn trị, Spring thường ném `NoUniqueBeanDefinitionException` (đôi khi được bọc trong `UnsatisfiedDependencyException`/`BeanCreationException` khi xảy ra trong quá trình tạo service).

**Câu hỏi cần giải:** “Trong nhiều bean cùng kiểu đã đăng ký, bean nào được đưa vào điểm injection này?”

Sau bài, bạn có thể:

1. Phân biệt **bean name**, **Java type/interface**, **bean candidate**, **injection point** và bean instance.
2. Nhận diện khác nhau giữa **thiếu ứng viên** và **nhiều ứng viên**.
3. Chọn một implementation mặc định qua `@Primary`; hiểu tình huống **hai primary** vẫn mơ hồ.
4. Dùng `@Qualifier` để yêu cầu một implementation phù hợp cho **một injection point**; hiểu qualifier là *bộ lọc theo kiểu*, không phải tham chiếu String bất chấp type.
5. Sử dụng `@Fallback` của **Spring Framework 6.2** để hạ ưu tiên một bean; hiểu khi nào fallback vẫn được chọn.
6. Phân biệt **injection một bean** với **List/Map/array injection nhiều beans**, bao gồm vai trò của `@Order`.
7. Hiểu name matching, `-parameters`, `@Resource`, generic types và cấu hình `autowireCandidate`/`defaultCandidate` khi phù hợp.
8. Chạy demo độc lập Java 17+ với Spring Framework 6.2.19, Maven và lệnh `javac`/`java`, đối chiếu stdout xác định.
9. Chẩn đoán và sửa ambiguity mà không che lỗi bằng các lựa chọn ngẫu nhiên, `@Autowired(required=false)` hoặc service locator.

**Phạm vi:** cơ chế *chọn bean ứng viên* trong Spring Core Container. Không cần Spring Boot, web, database, email/SMS thực, framework test hay một bộ DI bên ngoài.

## 2. Phân biệt ba kết quả khi resolve một dependency

Cho một điểm injection yêu cầu `MessageSender`:

| Số ứng viên phù hợp sau các quy tắc chọn | Kết quả điển hình |
| --- | --- |
| Không có bean phù hợp | Thiếu dependency; có thể phát sinh `NoSuchBeanDefinitionException` hoặc wrapper |
| Có một bean phù hợp | Spring inject bean object đó |
| Có nhiều bean phù hợp, không có lựa chọn duy nhất | Ambiguity; thường `NoUniqueBeanDefinitionException` |
| Nhiều bean cùng type, nhưng **một @Primary** hợp lệ | Spring chọn primary cho injection đơn trị |
| Nhiều bean cùng type, nhưng **@Qualifier** thu hẹp đúng một | Spring chọn ứng viên khớp qualifier |
| Nhiều bean, có **một non-fallback** và các `@Fallback` | Bean non-fallback được ưu tiên theo quy tắc Spring 6.2 |
| Điểm injection là `List<MessageSender>` | Spring có thể cung cấp **nhiều** bean, không buộc phải chọn một |

**Đặc biệt:** nhiều bean cùng kiểu **không phải lỗi registry**. Hai bean names khác nhau vẫn hợp lệ. Lỗi chỉ xuất hiện khi **một consumer muốn đúng một instance** nhưng container không chọn được duy nhất (hoặc khi lookup bằng type không đủ rõ).

Hai bean definitions cùng **bean name** lại là chuyện khác — chính sách đăng ký và ghi đè definition, không phải trọng tâm giải quyết nhiều candidate theo type.

## 3. Spring chọn ứng viên theo những lớp thông tin nào?

Một cách hiểu thực dụng về quá trình tìm một collaborator:

~~~mermaid
flowchart TD
    I["Injection point: MessageSender"] --> T["Lọc bean phù hợp kiểu"]
    T --> N{"Số candidate?"}
    N -->|"0"| X["Missing dependency"]
    N -->|"1"| OK["Chọn bean duy nhất"]
    N -->|"Nhiều"| Q["Xét qualifier, primary, fallback và quy tắc liên quan"]
    Q --> U{"Có duy nhất ứng viên tốt nhất?"}
    U -->|"Có"| OK
    U -->|"Không"| E["Ambiguous dependency"]
~~~

Đây là **mô hình tư duy**, không mô tả từng bước nội bộ/độ ưu tiên tuyệt đối của mọi nhánh thuật toán Spring. Thực tế Spring dùng `DependencyDescriptor`, bean definitions, type metadata và các quy tắc resolution khác nhau, bao gồm `@Qualifier`, `@Primary`, `@Fallback`, matching tên parameter/field, `@Priority` và trạng thái candidate.

Để áp dụng chính xác, hãy hỏi theo thứ tự:

1. **Type tại injection point là gì?** Interface `MessageSender` hay implementation cụ thể `EmailSender`? Generic arguments có ý nghĩa không?
2. **Những bean nào đã đăng ký?** Bean names, factory methods, scopes và return types có đủ rõ?
3. **Bean nào đủ điều kiện autowiring?** Có `autowireCandidate=false` hoặc metadata hạn chế không?
4. **Injection point có qualifier không?** Có chỉ rõ ý định “EMAIL”, “SMS”, “fast”, “main” hay một tên bean cụ thể không?
5. **Trong những candidate còn lại, có primary/fallback policy không?** Có một lựa chọn độc nhất không?
6. **Có cơ chế phù hợp theo tên injection point không?** Tên parameter có được giữ lúc compile không?
7. **Consumer cần một hay nhiều?** Nếu cần tất cả, injection collection thường phù hợp hơn việc chọn tùy ý.

**Không dùng thứ tự khai báo method trong source làm hợp đồng chọn một bean.** Đăng ký sau, tên đứng đầu bảng chữ cái hoặc component scan đi trước không phải cơ chế nghiệp vụ thay thế cho qualifier/primary rõ ràng.

## 4. @Primary: chọn một bean mặc định khi có nhiều bean cùng kiểu

`@Primary` đánh dấu ứng viên được ưu tiên cho **dependency đơn trị** nếu bean đó vẫn thỏa type, qualifier và các điều kiện autowire. Ví dụ có `emailSender` và `smsSender` cùng type `MessageSender`; đánh dấu EMAIL là primary giúp một tham số `MessageSender sender` nhận EMAIL mà không ép mọi consumer phải ghi qualifier.

Một `@Qualifier("smsSender")` hợp lệ tại injection point vẫn giới hạn lựa chọn sang SMS. Hai primary cùng đáp ứng một dependency không tạo ra mặc định duy nhất. Primary cũng không loại SMS khỏi `List<MessageSender>` hoặc `Map<String, MessageSender>`. Mục 7 kiểm tra các trường hợp này; bài riêng về `@Primary` giải thích sâu về bean definition và các edge case.

## 5. @Qualifier: thu hẹp candidate tại đúng injection point

Với hai bean `MessageSender`, một consumer cần SMS có thể khai `@Qualifier("smsSender") MessageSender sender`. Qualifier là **bộ lọc trong tập ứng viên hợp kiểu**; giá trị trùng bean name có thể được Spring dùng để match, nhưng đừng hiểu nó là thao tác lookup theo tên bất chấp type. Một qualifier có thể mô tả vai trò như `transactional` hoặc `regional` và có thể gắn cho nhiều beans.

Vì vậy `@Qualifier("fast") List<MessageSender>` có thể nhận nhiều beans cùng nhãn, còn `@Qualifier("fast") MessageSender` vẫn mơ hồ khi còn hai beans ngang nhau. Trong demo mục 7, qualifier chỉ định một SMS/EMAIL cụ thể; bài sau về `@Qualifier` và custom qualifier đi sâu vào collection, annotation metadata và ngữ nghĩa nghiệp vụ.

## 6. @Fallback: hạ ưu tiên một bean trong Spring Framework 6.2

Từ **Spring Framework 6.2**, `org.springframework.context.annotation.Fallback` đánh dấu một bean là phương án ưu tiên thấp khi chọn dependency **đơn trị**. Nếu có đúng một bean thường và những bean còn lại là fallback, Spring có thể chọn bean thường. Nếu context chỉ có một bean fallback hợp lệ, bean đó vẫn được inject.

Fallback **không** xóa bean khỏi container, không ngăn nó xuất hiện trong collection, không trì hoãn khởi tạo và không thực hiện failover khi lời gọi nghiệp vụ lỗi. Nếu có nhiều bean thường hoặc nhiều bean fallback cùng đáp ứng một injection point, vẫn cần rule khác để phân định. Context `FallbackConfig` và `OnlyFallbackConfig` ở mục 7 chứng minh hai nhánh; bài `@Fallback` riêng trình bày rõ giới hạn phiên bản và các trường hợp khó.

## 7. Project Java 17+ runnable: chứng minh năm cách xử lý

Dùng **JDK 17+**, Maven và **Spring Framework 6.2.19**. Version được ghim để ví dụ tái lập, không tuyên bố mới nhất. Chạy thuần Spring Core Container, không Spring Boot/MVC, không email/SMS thật.

Demo dùng nhiều contexts độc lập để mỗi tình huống chỉ mang đúng các bean definitions cần kiểm tra:

1. **Plain:** hai Sender cùng type, không có lựa chọn đơn trị; lookup theo type bị từ chối.
2. **Qualified + collection:** chỉ định `@Qualifier("emailSender")` lấy EMAIL, còn `List/Map` nhận cả EMAIL và SMS. `@Order` sắp thứ tự List.
3. **Primary:** EMAIL là `@Primary`, nên lookup không qualifier lấy EMAIL; nhưng qualifier SMS vẫn chọn SMS.
4. **Fallback:** SMS là `@Fallback`, EMAIL là bean thông thường, nên email được ưu tiên.
5. **Only fallback:** chỉ còn một SMS fallback, nó vẫn là bean duy nhất hợp lệ.
6. **Two primaries:** cả email và SMS đều `@Primary`, nên không có một lựa chọn primary duy nhất.

### 7.1. Cấu trúc thư mục

~~~text
candidate-resolution-demo/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── demo/
                └── CandidateResolutionDemo.java
~~~

### 7.2. File pom.xml

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>candidate-resolution-demo</artifactId>
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
                    <mainClass>demo.CandidateResolutionDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Spring dependencies transitively cần thiết do Maven resolve. Với `javac`/`java` trực tiếp, cần đủ JAR của Spring trên classpath.

### 7.3. File src/main/java/demo/CandidateResolutionDemo.java

~~~java
package demo;

import java.util.List;
import java.util.Map;
import java.util.Objects;

import org.springframework.beans.factory.NoUniqueBeanDefinitionException;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Fallback;
import org.springframework.context.annotation.Primary;
import org.springframework.core.annotation.Order;

public final class CandidateResolutionDemo {
    private CandidateResolutionDemo() {}

    public interface Sender {
        String id();
    }

    public record NamedSender(String id) implements Sender {
        public NamedSender {
            Objects.requireNonNull(id);
        }
    }

    public static final class QualifiedClient {
        private final Sender sender;

        public QualifiedClient(Sender sender) {
            this.sender = Objects.requireNonNull(sender);
        }

        public String selected() {
            return sender.id();
        }
    }

    public static final class CollectionClient {
        private final List<Sender> all;
        private final Map<String, Sender> byName;

        public CollectionClient(
                List<Sender> all, Map<String, Sender> byName) {
            this.all = List.copyOf(all);
            this.byName = Map.copyOf(byName);
        }

        public String orderedIds() {
            return all.stream().map(Sender::id).toList().toString();
        }

        public String sortedBeanNames() {
            return byName.keySet().stream().sorted()
                    .toList().toString();
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class PairConfig {
        @Bean("emailSender")
        @Order(2)
        public Sender emailSender() {
            return new NamedSender("EMAIL");
        }

        @Bean("smsSender")
        @Order(1)
        public Sender smsSender() {
            return new NamedSender("SMS");
        }

        @Bean
        public QualifiedClient qualifiedClient(
                @Qualifier("emailSender") Sender sender) {
            return new QualifiedClient(sender);
        }

        @Bean
        public CollectionClient collectionClient(
                List<Sender> senders, Map<String, Sender> sendersByName) {
            return new CollectionClient(senders, sendersByName);
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class PrimaryConfig {
        @Bean("emailSender")
        @Primary
        public Sender emailSender() {
            return new NamedSender("EMAIL");
        }

        @Bean("smsSender")
        public Sender smsSender() {
            return new NamedSender("SMS");
        }

        @Bean
        public QualifiedClient qualifiedClient(
                @Qualifier("smsSender") Sender sender) {
            return new QualifiedClient(sender);
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class FallbackConfig {
        @Bean("emailSender")
        public Sender emailSender() {
            return new NamedSender("EMAIL");
        }

        @Bean("smsSender")
        @Fallback
        public Sender smsSender() {
            return new NamedSender("SMS");
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class OnlyFallbackConfig {
        @Bean("smsSender")
        @Fallback
        public Sender smsSender() {
            return new NamedSender("SMS");
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class TwoPrimaryConfig {
        @Bean("emailSender")
        @Primary
        public Sender emailSender() {
            return new NamedSender("EMAIL");
        }

        @Bean("smsSender")
        @Primary
        public Sender smsSender() {
            return new NamedSender("SMS");
        }
    }

    private static void demonstratePair() {
        try (AnnotationConfigApplicationContext context =
                new AnnotationConfigApplicationContext(PairConfig.class)) {
            try {
                context.getBean(Sender.class);
                System.out.println("plain=UNEXPECTED");
            } catch (NoUniqueBeanDefinitionException expected) {
                System.out.println("plain=AMBIGUOUS");
            }

            QualifiedClient qualified =
                    context.getBean(QualifiedClient.class);
            CollectionClient all =
                    context.getBean(CollectionClient.class);

            System.out.println("qualified=" + qualified.selected());
            System.out.println("ordered=" + all.orderedIds());
            System.out.println("beanNames=" + all.sortedBeanNames());
        }
    }

    private static void demonstratePrimary() {
        try (AnnotationConfigApplicationContext context =
                new AnnotationConfigApplicationContext(PrimaryConfig.class)) {
            Sender selected = context.getBean(Sender.class);
            QualifiedClient sms = context.getBean(QualifiedClient.class);

            System.out.println("primary=" + selected.id());
            System.out.println("qualifierOverPrimary=" + sms.selected());
        }
    }

    private static void demonstrateFallback() {
        try (AnnotationConfigApplicationContext context =
                new AnnotationConfigApplicationContext(FallbackConfig.class)) {
            System.out.println("fallbackPreferred=" +
                    context.getBean(Sender.class).id());
        }

        try (AnnotationConfigApplicationContext context =
                new AnnotationConfigApplicationContext(
                        OnlyFallbackConfig.class)) {
            System.out.println("onlyFallback=" +
                    context.getBean(Sender.class).id());
        }
    }

    private static void demonstrateTwoPrimaries() {
        try (AnnotationConfigApplicationContext context =
                new AnnotationConfigApplicationContext(TwoPrimaryConfig.class)) {
            try {
                context.getBean(Sender.class);
                System.out.println("twoPrimaries=UNEXPECTED");
            } catch (NoUniqueBeanDefinitionException expected) {
                System.out.println("twoPrimaries=AMBIGUOUS");
            }
        }
    }

    public static void main(String[] args) {
        demonstratePair();
        demonstratePrimary();
        demonstrateFallback();
        demonstrateTwoPrimaries();
    }
}
~~~

**Phân tích khả năng chạy và phạm vi của demo:**

- Chỉ có một public top-level class `CandidateResolutionDemo` khớp đường dẫn/package; records, configs và consumers là nested types.
- `Sender` là interface, `NamedSender` là record Java 17 implement interface và giữ ID cố định; không dùng network thực.
- Mỗi `@Configuration` class tạo **context độc lập**. Điều này cô lập các chính sách thay vì đưa năm nhóm cùng tên vào một registry rồi bị ghi đè.
- Các `@Bean` methods có return type `Sender`, đủ để Spring nhìn thấy hai ứng viên thuộc cùng type; chúng được đặt tên khác nhau và không trùng trong một config.
- `PairConfig` đánh dấu `smsSender` `@Order(1)`, `emailSender` `@Order(2)` để List injection có thứ tự `[SMS, EMAIL]`. Đây là sắp xếp collection, **không** chọn một Sender duy nhất.
- `Map<String, Sender>` nhận các bean theo tên; khi in, ta **sort tên** để kết quả không phụ thuộc thứ tự Map iteration.
- `QualifiedClient` chỉ yêu cầu một Sender cụ thể qua `@Qualifier` đặt trên `@Bean` factory-method parameter; các `@Bean` methods không gọi trực tiếp nhau.
- `PrimaryConfig` có một primary EMAIL; explicit qualifier SMS ở consumer khác vẫn yêu cầu SMS.
- `FallbackConfig` có một bean thường EMAIL và một fallback SMS; `OnlyFallbackConfig` chỉ có SMS.
- `TwoPrimaryConfig` có hai primary cùng interface; type-only lookup thiếu unique primary.
- `AnnotationConfigApplicationContext` đóng theo `try-with-resources`. Những exception được dự kiến xảy ra ở **lookup kiểu đơn trị** và được bắt có chủ đích; không in stack trace hay nhét exception message tùy phiên bản vào stdout.
- Không sử dụng đồng hồ, random, dữ liệu người dùng hay mạng; các text đầu ra đều xác định từ mã demo.

### 7.4. Chạy Maven và đối chiếu stdout

Tại thư mục `candidate-resolution-demo`:

~~~bash
java -version
javac -version
mvn -version
mvn -q clean compile exec:java
~~~

**Đúng chín dòng stdout do chương trình Java in khi chạy thành công:**

~~~text
plain=AMBIGUOUS
qualified=EMAIL
ordered=[SMS, EMAIL]
beanNames=[emailSender, smsSender]
primary=EMAIL
qualifierOverPrimary=SMS
fallbackPreferred=EMAIL
onlyFallback=SMS
twoPrimaries=AMBIGUOUS
~~~

Những dòng phiên bản JDK/Maven, log của Maven/Spring (nếu có) không thuộc chín dòng do `main` in trong chương trình. Không lock test vào nội dung đầy đủ của exception vì exception detail có thể thay đổi giữa các Spring versions.

### 7.5. Chạy trực tiếp javac/java trên Linux/macOS và Windows

Trước tiên tạo danh sách JAR dependencies bằng Maven:

~~~bash
mvn -q dependency:build-classpath -Dmdep.outputFile=classpath.txt
~~~

**Linux/macOS — bash/zsh:**

~~~bash
mkdir -p out
javac --release 17 -encoding UTF-8 \
  -cp "$(cat classpath.txt)" \
  -d out src/main/java/demo/CandidateResolutionDemo.java
java -cp "out:$(cat classpath.txt)" demo.CandidateResolutionDemo
~~~

**Windows — PowerShell:**

~~~powershell
$deps = (Get-Content -Raw classpath.txt).Trim()
New-Item -ItemType Directory -Force out | Out-Null
javac --release 17 -encoding UTF-8 -cp "$deps" -d out src/main/java/demo/CandidateResolutionDemo.java
java -cp "out;$deps" demo.CandidateResolutionDemo
~~~

Classpath separator là `:` trên Unix và `;` trên Windows. Cả hai cách chạy cùng phương thức `main`, cho cùng output ứng dụng. Nếu `javac` báo không tìm thấy `org.springframework.*`, cần kiểm tra dependency/classpath trước khi sửa bean resolution.

## 8. Vì sao List/Map injection không gặp lỗi “nhiều bean”?

Có sự khác biệt về **contract** của injection point:

~~~java
public NotificationBatch(
        List<MessageSender> allSenders,
        Map<String, MessageSender> byName) {
    // allSenders: những bean phù hợp kiểu MessageSender
    // byName: key là bean name; value là bean object
}
~~~

**Snippet**, không phải full Java file. Một constructor nhận `MessageSender` đơn trị cần chọn một, nhưng List/Map có nhiệm vụ tập hợp các beans cùng kiểu. Vì vậy tồn tại ba strategies cùng type không tự là lỗi cho collection injection.

Spring hỗ trợ array, collection và `Map<String,T>` injection. Với map, **key type nên là String** để đại diện bean names, và value type phải giữ thông tin phù hợp. Với `List<T>`, thứ tự có thể bị ảnh hưởng bởi `@Order`/`Ordered` và sau đó bởi registration order khi không có policy sắp xếp cụ thể.

**Không suy rằng @Order là “chọn bean có rank nhỏ nhất”:**

- `@Order(1)` và `@Order(2)` giúp sắp phần tử trong một collection được inject.
- Nó **không tương đương** `@Primary` khi consumer chỉ muốn một `MessageSender`.
- Nó cũng **không nhất thiết điều khiển thứ tự khởi tạo singleton**. Trình tự startup phụ thuộc dependency graph, `@DependsOn` và các cơ chế bootstrap.
- Nếu nghiệp vụ cần “thử mọi sender theo thứ tự”, `List<MessageSender>` với order rõ có ích; nếu cần “chỉ một sender”, dùng qualifier/primary/fallback theo hợp đồng.

Nếu collection chỉ nên chứa một nhóm, có thể dùng qualifier để **lọc cả collection**. Ví dụ hai beans đánh dấu `@Qualifier("transactional")` có thể đi vào `@Qualifier("transactional") List<MessageSender>`; qualifier không buộc chỉ ra một bean duy nhất.

### Map là cấu trúc hữu ích cho strategy lookup, nhưng cần kiểm soát key

Ví dụ một registry nghiệp vụ:

~~~java
private final Map<String, MessageSender> senders;

public StrategySelector(Map<String, MessageSender> senders) {
    this.senders = Map.copyOf(senders);
}

public MessageSender forChannel(String beanName) {
    MessageSender sender = senders.get(beanName);
    if (sender == null) {
        throw new IllegalArgumentException("Unknown channel: " + beanName);
    }
    return sender;
}
~~~

**Đoạn này là method snippets thuộc class cần import/khai báo interface phù hợp**, không phải project runnable thứ hai. Nó cho phép lựa chọn *ở runtime* theo một input mà application đã validate. Nhưng tránh để bean name (chi tiết wiring của Spring) trở thành hợp đồng API công khai một cách tình cờ; nên ánh xạ domain channel sang bean strategy hoặc dùng enum/typed key khi thích hợp.

## 9. Parameter name matching: vì sao đôi khi không có @Qualifier mà vẫn chọn được?

Trong một số trường hợp, Spring có thể dùng **tên field/parameter** để chọn bean có tên hoặc alias phù hợp sau khi xem xét những quy tắc lựa chọn khác. Ví dụ `MessageSender emailSender` có thể match bean tên `emailSender`, nhưng tên tham số Java chỉ được phản ánh đáng tin cậy nếu biên dịch với `-parameters` (đặc biệt khi dùng Spring Framework 6.1+).

Name matching là tiện ích có điều kiện, không phải lời bảo đảm rằng Spring luôn inject theo tên trước type hoặc qualifier. Với hợp đồng nghiệp vụ cần một implementation ổn định, qualifier tường minh dễ kiểm chứng hơn. Bài riêng về `-parameters` giải thích bytecode metadata, Maven và cách tự thử với/không với cờ này.

## 10. Generic type và metadata cũng ảnh hưởng ứng viên

Khi có `Store<String>` và `Store<Long>`, một injection point `Store<String>` có thể dùng metadata generic để lọc ứng viên trước khi xét `@Primary`, qualifier hoặc tên. Đây là phân biệt bằng hợp đồng kiểu, khác việc gắn nhãn nghiệp vụ. Nếu có hai bean cùng `Store<String>`, ambiguity vẫn có thể xảy ra; nếu method khai raw `Store`, Spring có thể thiếu thông tin để phân biệt. Phần chuyên sâu về generic types trình bày giới hạn erasure và collection injection.

## 11. Những cách xử lý khác và điểm giới hạn

| Cơ chế | Khi phù hợp | Giới hạn |
| --- | --- | --- |
| `@Primary` | Có một implementation mặc định cho phần lớn consumers | Không giải quyết hai primaries ngang nhau |
| `@Qualifier` | Mỗi consumer cần implementation theo vai trò rõ | Qualifier cần ứng viên phù hợp type; có thể còn nhiều |
| `@Fallback` | Một implementation là fallback trong Spring 6.2+ | Không thay thế policy bắt buộc/không loại bean |
| `List<T>` / `Map<String,T>` | Cần tất cả strategies hoặc lookup động | Consumer phải tự quyết định thứ tự/chọn lúc dùng |
| Tên parameter/field | Tên có ý nghĩa và metadata đáng tin | Dễ thay đổi khi refactor; cần `-parameters` với constructor |
| `@Resource(name=...)` | Cần name-oriented field/setter resolution | Semantics khác type-driven constructor qualifier |
| Generic type | Interface specialization thể hiện ý định hợp đồng | Cần metadata generics đủ cụ thể |
| `ObjectProvider<T>` | Lazy/optional/stream access có chủ đích | `getObject()` đơn trị vẫn có thể gặp ambiguity |
| `@Bean(defaultCandidate=false)` | Bean chỉ nên xuất hiện khi injection có qualifier | Feature 6.2, không phải `@Fallback` |
| `@Bean(autowireCandidate=false)` | Exclude khỏi type-based injection | Không có nghĩa unregister bean hay cấm explicit lookup |
| `@Profile` / điều kiện đăng ký | Mỗi môi trường chỉ đăng ký implementation phù hợp | Cần test cấu hình profile/condition ở môi trường thật |

### Profile và điều kiện có thể giải quyết vấn đề từ gốc

Nếu ứng dụng **không bao giờ cần cả hai implementations trong cùng một môi trường**, một cách khác là làm cho đúng **một definition được đăng ký** theo profile/condition, thay vì luôn đăng ký cả hai rồi chọn qua primary.

Ví dụ conceptual:

~~~java
@Bean
@Profile("dev")
MessageSender devSender() { return new ConsoleSender(); }

@Bean
@Profile("prod")
MessageSender prodSender() { return new RemoteSender(); }
~~~

**Snippet minh họa**, thiếu interfaces/implementations và config. Phải chắc profile phù hợp đang active, nếu không có thể thiếu candidate; nếu nhiều profiles active, có thể lại có nhiều candidate. Đây là vấn đề **tập bean được đăng ký**, khác việc chọn giữa những candidate đã có.

Không dùng `@Conditional` hoặc `@Profile` để che những implementation nghiệp vụ thật sự cần tồn tại đồng thời.

## 12. Chẩn đoán NoUniqueBeanDefinitionException đúng chỗ

Một stack trace có thể có các lớp exception:

~~~text
UnsatisfiedDependencyException
  caused by: NoUniqueBeanDefinitionException:
  expected single matching bean but found 2:
  emailSender, smsSender
~~~

**Đây là ví dụ cấu trúc lỗi, không phải stack trace nguyên văn**. Class/wording của exception wrapper tùy đường tạo bean và phiên bản Spring. Hãy đọc tới bean name, type, candidate count và injection point cụ thể.

Một quy trình đáng tin:

1. **Tìm injection point:** constructor parameter, field, `@Bean` factory method hoặc `context.getBean(Type.class)`?
2. **Xác minh type:** `MessageSender` hay subtype khác, có generic arguments, proxies hoặc factory declared return type ảnh hưởng không?
3. **Liệt kê candidate beans:** dùng `context.getBeanNamesForType(MessageSender.class)` khi context đã chạy; xem definitions của các tên liên quan.
4. **Kiểm tra qualifier và primary:** annotation có ở injection point/bean definition thật không? Có hai primary cùng type?
5. **Kiểm tra fallback, candidate flags, profile:** có bean bị loại khỏi autowiring hoặc bean chỉ dùng theo qualifier không?
6. **Kiểm tra tên parameter/field:** có vô tình khớp với bean name không? Có compile `-parameters` nếu dựa vào điều đó?
7. **Đọc lỗi gốc:** nếu missing bean là do registration không chạy hoặc dependency lỗi, đừng đánh đồng với ambiguity.
8. **Chọn giải pháp tương ứng với nghiệp vụ:** một default → primary; consumer-specific → qualifier; all strategies → List/Map; environment-specific → profile; fallback → @Fallback; thực sự cần đúng một definition → sửa registration.
9. **Viết smoke test:** test context khởi động, kiểm tra identity/type/behavior của bean được inject, không chỉ kiểm tra “không ném exception”.

### API kiểm tra những bean có mặt

~~~java
String[] names = context.getBeanNamesForType(MessageSender.class);
for (String name : names) {
    System.out.println(name);
}
~~~

**Snippet**: cần nằm trong scope có `ApplicationContext context` và `MessageSender` type. Thứ tự array có thể theo registration, nên nếu đưa vào assertion yêu cầu deterministic list hãy sort names trước. Sự có mặt của một bean trong registry **không tự chứng minh nó là candidate hợp lệ cho mọi injection point**; qualifier flags và scopes còn ảnh hưởng.

## 13. Những lỗi thiết kế thường gặp và cách sửa

| Triệu chứng | Hiểu nhầm thường gặp | Hướng sửa |
| --- | --- | --- |
| `NoUniqueBeanDefinitionException` | “Hai bean cùng interface là bất hợp pháp” | Hai bean được phép tồn tại; hãy xác định contract consumer cần một hay nhiều |
| Đánh dấu cả hai beans `@Primary` | “Càng nhiều primary càng chắc chắn chọn được” | Chọn một default rõ hoặc dùng qualifier |
| Thêm `@Order(1)` vào một bean | Nghĩ Spring chọn bean có order nhỏ nhất cho single injection | Dùng primary/qualifier; order cho collection |
| Bỏ qualifier khi refactor | Spring bắt đầu chọn theo tên parameter hoặc báo ambiguity | Khôi phục yêu cầu chọn có chủ đích |
| `@Qualifier` chứa bean name không đúng type | Mong String bean name bất chấp type | Fix declared types/bean definitions |
| `@Fallback` mà vẫn nhiều normal beans | Tưởng fallback giải quyết hết ambiguity | Dùng qualifier/primary hoặc giảm candidate set |
| `@Autowired(required=false)` để “fix” hai candidates | Optional không mang nghĩa chọn tùy ý một bean | Làm rõ candidate selection, đừng che lỗi |
| Đổi `@Bean` method return type quá chung | Metadata không đủ để match subtype/generic | Khai báo return type đủ cụ thể |
| Chỉ sửa ở unit test bằng fake bean | Production config vẫn ambiguous | Có integration test với config thật |
| Chạy được khi bật một profile, lỗi khi bật hai | Hai implementations cùng đăng ký | Kiểm tra profile combinations và candidate policy |
| Dùng `getBean(Class)` trong business service | Runtime lookup dễ thất bại và giấu dependency | Constructor injection vào service |
| Dựa vào tên constructor parameter tình cờ | Refactor đổi tên phá binding | Explicit qualifier khi cần ổn định |
| Đánh dấu `autowireCandidate=false` bừa bãi | Candidate biến mất khỏi type-driven injection | Chỉ exclude đúng bean không nên autowire |
| Dùng Map rồi chọn `values().iterator().next()` | Phụ thuộc thứ tự không phải business policy | Chọn theo domain key/chiến lược rõ |
| Singleton mutable strategy có race | Tưởng bean được chọn đúng là thread-safe | Bảo vệ state và thiết kế scope/concurrency |
| `javac` không thấy Spring API | Thiếu Spring JAR/classpath | Kiểm tra POM và `-cp` trước khi debug DI |

**Nguyên tắc:** lỗi ambiguity thường mang thông tin hữu ích về **một hợp đồng chưa rõ**. Không sửa bằng cách đánh dấu một bean bất kỳ `@Primary` chỉ để ứng dụng chạy, nếu nghiệp vụ không có lý do dùng nó mặc định.

## 14. Kiểm thử chiến lược chọn ứng viên

### Unit test không cần Spring

Một service có constructor nhận interface vẫn có thể test bằng fake:

~~~java
Sender fake = () -> "TEST";
QualifiedClient client = new QualifiedClient(fake);
System.out.println(client.selected()); // TEST
~~~

**Snippet** trong phạm vi truy cập các nested types của demo. Nó kiểm tra logic Java thuần và việc constructor nhận một collaborator, **không** kiểm tra chính sách Spring autowiring.

### Wiring integration test

Trong context với hai Senders, nên kiểm tra:

- Không qualifier/primary/fallback mà yêu cầu `Sender.class` đơn trị → expected ambiguity.
- `@Qualifier("emailSender")` ở một injection point → nhận đúng bean email.
- Một `@Primary` → bare type resolution chọn đúng default.
- Qualifier `smsSender` vẫn chọn SMS dù email primary.
- Một normal + một `@Fallback` → normal được ưu tiên.
- Chỉ một fallback candidate → fallback vẫn được chọn.
- Hai primary → ambiguity (trừ khi có điều kiện phân biệt khác phù hợp).
- `List<Sender>` được sort bởi `@Order`; `Map<String,Sender>` có tên chính xác.
- Bean không được đăng ký trong một profile → thiếu candidate, không phải multiple-candidate error.

**Đừng khóa test theo toàn bộ message của exception**, bởi wrapper và câu chữ có thể thay đổi. Với test framework, dùng assertions cho exception type/cause, bean identity, qualifier semantics và output/behavior.

### Lưu ý phiên bản

Bài dùng **Spring Framework 6.2.19** vì `@Fallback` và `@Bean(defaultCandidate=...)` là các khả năng liên quan đến 6.2. Nếu dự án dùng Spring Framework 6.1 hoặc cũ hơn, **không copy code có `@Fallback` mà chưa xác nhận phiên bản**. Với bản cũ, `@Primary`/`@Qualifier` và cách cấu hình candidate có thể là lựa chọn sẵn có; nâng framework phải theo chính sách tương thích của dự án.

## 15. Bài tập có đáp án

**Bài 1.** Context có `emailSender` và `smsSender` cùng implement `Sender`, không primary/qualifier. `context.getBean(Sender.class)` có chọn bean đăng ký trước không?

**Đáp án:** Không theo hợp đồng autowiring đơn trị. Khi có nhiều candidate không phân biệt, `getBean(Sender.class)` thường ném `NoUniqueBeanDefinitionException`.

**Bài 2.** Có một email `@Primary` và một SMS thường. Factory method nhận `Sender sender` không qualifier lấy gì?

**Đáp án:** EMAIL, vì có đúng một primary hợp lệ.

**Bài 3.** Consumer dùng `@Qualifier("smsSender") Sender sender` nhưng EMAIL primary. Có nhận EMAIL không?

**Đáp án:** Không trong ví dụ. Qualifier thu hẹp candidates theo yêu cầu SMS; Spring inject SMS.

**Bài 4.** Có một bean thường EMAIL và một bean `@Fallback` SMS. Điểm injection bare `Sender` nhận bean nào?

**Đáp án:** EMAIL, ứng viên non-fallback duy nhất.

**Bài 5.** Context chỉ có SMS đánh dấu `@Fallback`. Dependency `Sender` bắt buộc có thiếu không?

**Đáp án:** Không vì SMS vẫn là một candidate hợp lệ; fallback là ưu tiên thấp, không phải loại bỏ bean.

**Bài 6.** Đánh dấu `@Order(1)` cho SMS và `@Order(2)` cho EMAIL sẽ làm `getBean(Sender.class)` tự chọn SMS không?

**Đáp án:** Không. @Order có tác dụng sắp collection injection, không thay @Primary cho lookup đơn trị thông thường.

**Bài 7.** `List<Sender>` nhận gì khi có hai beans khác tên cùng type?

**Đáp án:** Thường nhận cả hai bean tương thích, sắp theo policy ordering phù hợp. Không cần chọn một.

**Bài 8.** Hai beans đều có `@Primary` mà không có lựa chọn khác. Có được một default duy nhất không?

**Đáp án:** Không. Hai primary khiến lựa chọn đơn trị mơ hồ.

**Bài 9.** @Qualifier có thể chọn bean thuộc kiểu không tương thích injection point không?

**Đáp án:** Không. Qualifier thu hẹp **trong tập bean tương thích type**, không ép String name thành object khác kiểu.

**Bài 10.** Vì sao chỉ đổi tên tham số có thể ảnh hưởng wiring nếu không qualifier?

**Đáp án:** Spring có thể dùng tên injection point làm gợi ý khi phù hợp; với Java 6.1+ việc giữ parameter name cần compile `-parameters`. Explicit qualifier phù hợp hơn khi logic lựa chọn phải bền vững qua refactor.

**Bài 11.** Nếu chỉ cần email sender tại tất cả môi trường, có nhất thiết phải tạo thêm SMS bean rồi dùng @Primary không?

**Đáp án:** Không. Nếu SMS không cần tồn tại, đừng đăng ký nó. Profile/conditional hoặc một configuration rõ ràng có thể giúp đảm bảo một bean candidate ngay từ đầu.

**Bài 12.** Khi nào nên inject `Map<String, Sender>` thay vì `Sender`?

**Đáp án:** Khi nghiệp vụ thật sự cần nhiều strategies rồi tự chọn theo một key/điều kiện được validate, không phải khi muốn né việc làm rõ một default.

## 16. Checklist trước khi đưa vào dự án

- [ ] Xác định dependency cần **một** hay **nhiều** beans.
- [ ] Kiểm tra bean names, interface/types, generics và qualifier metadata.
- [ ] Đọc đúng `NoUniqueBeanDefinitionException` thay vì chữa nhầm lỗi thiếu bean.
- [ ] Nếu có một default hợp lệ, đánh dấu **đúng một `@Primary`**.
- [ ] Nếu consumer có ý định riêng, dùng `@Qualifier` ở injection point.
- [ ] Nếu có bean dự phòng, hiểu semantics `@Fallback` của Spring 6.2.
- [ ] Không coi `@Fallback` là remove/exclude bean.
- [ ] Không dùng `@Order` để thay primary trong injection đơn trị.
- [ ] Với `List/Map`, xác nhận các thành phần và ordering theo hợp đồng.
- [ ] Tránh selection phụ thuộc accidental parameter names/registration order.
- [ ] Chỉ dùng `@Bean(defaultCandidate=false)`/`autowireCandidate=false` khi hiểu hậu quả.
- [ ] Khi dùng `@Bean`, khai báo return type đủ cụ thể cho các injection points.
- [ ] Tách unit tests logic khỏi Spring context wiring tests.
- [ ] Test nhiều profile combinations, primary/qualifier/fallback interactions.
- [ ] Chạy Java 17+ bằng Maven và `javac`/`java`, đối chiếu **9 dòng stdout**.
- [ ] Không hardcode chọn strategy “đầu tiên trong Map” mà không có business rule.
- [ ] Khi đổi version Spring, xác nhận support cho `@Fallback` và flags của `@Bean`.

**Ghi nhớ:** Bean cùng kiểu là điều tự nhiên khi triển khai strategy/interface-based design. Spring chỉ cần một cơ chế lựa chọn **rõ ràng và duy nhất** khi injection point yêu cầu một object. `@Primary` nói **“đây là mặc định”**; `@Qualifier` nói **“ở đây cần loại này”**; `@Fallback` nói **“đây là phương án ưu tiên thấp”**; `List/Map` nói **“ở đây cần nhiều triển khai”**. Chọn cơ chế phản ánh đúng nghiệp vụ sẽ làm dependency graph dễ hiểu, dễ kiểm thử và tránh sự cố wiring khi dự án mở rộng.

### Tài liệu Spring chính thức

- [Spring 6.2 — Autowiring Collaborators](https://docs.spring.io/spring-framework/reference/6.2/core/beans/dependencies/factory-autowire.html)
- [Spring 6.2 — Fine-tuning @Primary and @Fallback](https://docs.spring.io/spring-framework/reference/6.2/core/beans/annotation-config/autowired-primary.html)
- [Spring 6.2 — Fine-tuning Autowiring with Qualifiers](https://docs.spring.io/spring-framework/reference/6.2/core/beans/annotation-config/autowired-qualifiers.html)
- [Spring 6.2 — Using @Autowired](https://docs.spring.io/spring-framework/reference/6.2/core/beans/annotation-config/autowired.html)
- [Spring 6.2 — Using Generics as Autowiring Qualifiers](https://docs.spring.io/spring-framework/reference/6.2/core/beans/annotation-config/generics-as-qualifiers.html)
