# Tạo annotation qualifier theo ý nghĩa nghiệp vụ — Spring Framework Core Container

## 1. Bài toán: chọn đúng bean theo ý nghĩa, không theo tên tình cờ

Một hệ thống gửi thông báo có nhiều bean cùng thực thi interface `Sender`:

- Kênh **EMAIL** cho thị trường **VN**.
- Kênh **EMAIL** cho thị trường **GLOBAL**.
- Kênh **SMS** cho thị trường **VN**.

Nếu một service chỉ có constructor:

~~~java
public NotificationService(Sender sender) {
    this.sender = sender;
}
~~~

Spring thấy ba bean cùng tương thích kiểu `Sender`. Nếu không có dấu hiệu chọn duy nhất, dependency một đối tượng này có thể gặp `NoUniqueBeanDefinitionException`. Đánh dấu tùy tiện một bean `@Primary` sẽ tạo mặc định toàn cục, nhưng không biểu đạt rằng **service ở thị trường VN cần EMAIL**, còn service khác cần **SMS**.

Một phương án có nghĩa nghiệp vụ là **tự tạo qualifier annotations**:

~~~java
public NotificationService(
        @ChannelTag(Channel.EMAIL) @MarketTag("VN") Sender sender) {
    this.sender = sender;
}
~~~

Đây là **snippet minh họa**, chưa có định nghĩa annotation/type; project runnable đầy đủ ở mục 7.

Hai chú giải ở injection point diễn đạt: “Trong các bean thuộc kiểu `Sender`, chọn bean có **kênh EMAIL** và **thị trường VN**”. Ý định vẫn rõ khi người phát triển đổi tên method `@Bean` hoặc implementation class.

**Mục tiêu học tập:**

1. Hiểu qualifier là **metadata lọc candidate theo kiểu**, không tự tạo bean và không nhất thiết trỏ tới một bean name duy nhất.
2. Tạo annotation nghiệp vụ với `@Qualifier` làm **meta-annotation**, `@Retention(RUNTIME)` và `@Target` đúng vị trí.
3. Gắn custom qualifier trên **bean declaration** (`@Bean` method hoặc component class) và trên **injection point** (constructor/field/method parameter).
4. Dùng **nhiều qualifier đồng thời** để diễn đạt các điều kiện kênh/thị trường; hoặc dùng **một annotation nhiều attributes**.
5. Hiểu quy tắc “bean phải khớp các attribute đã yêu cầu”, không có logic wildcard/OR tự phát.
6. Biết áp dụng qualifier lên `List<Sender>` để lọc **nhiều bean cùng kênh**, và dùng `@Order` để sắp collection.
7. Phân biệt `@Primary`, `@Fallback`, `@Named`, `@Resource`, generic qualifiers và lựa chọn qua bean name.
8. Chạy ví dụ **Java 17+ / Spring Framework 6.2.19** với Maven và `javac`/`java`, đối chiếu stdout ổn định.
9. Chẩn đoán thiếu candidate, nhiều candidate cùng qualifier, thiếu `RUNTIME`, đặt annotation sai vị trí hoặc quên đăng ký bean.

**Phạm vi:** custom annotation qualifiers phục vụ **chọn bean theo ngữ nghĩa nghiệp vụ** trong Spring Core Container. Không cần Spring Boot, MVC, persistence, mạng hay tích hợp gửi email/SMS thật.

## 2. Nền tảng: từ @Qualifier("beanName") tới một hợp đồng miền nghiệp vụ

Spring có sẵn:

~~~java
public BillingClient(@Qualifier("vnEmailSender") Sender sender) {
    this.sender = sender;
}
~~~

Với constructor injection, `@Qualifier("vnEmailSender")` có thể thu hẹp về bean tương ứng. Tuy nhiên tên `vnEmailSender` phản ánh cách **đăng ký** nhiều hơn một mô hình nghiệp vụ có thể phát triển.

Một nhu cầu khác:

- Với một consumer, cần sender **EMAIL**, không quan tâm thị trường cụ thể.
- Với consumer khác, cần sender phục vụ **VN**, bất kể EMAIL hay SMS.
- Với một consumer đơn trị, cần chính xác **EMAIL + VN**.

Dùng hai annotation có nghĩa:

~~~java
@ChannelTag(Channel.EMAIL)
@MarketTag("VN")
Sender sender
~~~

thay cho các chuỗi tên bean như `"vnEmailSender"`, `"sender1"`. Chúng diễn đạt **những đặc tính có thể giữ nguyên khi bean name thay đổi**.

| Cách biểu đạt | Ý nghĩa | Điểm đáng chú ý |
| --- | --- | --- |
| `Sender sender` | Yêu cầu một bean kiểu Sender | Có thể mơ hồ nếu nhiều candidates |
| `@Qualifier("vnEmailSender") Sender sender` | Thu hẹp theo qualifier/bean name | Dễ gắn với tên wiring cụ thể |
| `@ChannelTag(EMAIL) Sender sender` | Chỉ nhận Sender thuộc kênh EMAIL | Có thể vẫn nhiều thị trường |
| `@MarketTag("VN") Sender sender` | Chỉ nhận Sender thuộc thị trường VN | Có thể vẫn nhiều kênh |
| `@ChannelTag(EMAIL) @MarketTag("VN") Sender sender` | Sender thỏa **cả hai** điều kiện | Đơn trị nếu chỉ một candidate còn lại |
| `@ChannelTag(EMAIL) List<Sender> senders` | Toàn bộ Sender được đánh dấu EMAIL | Không yêu cầu qualifier duy nhất |

**Từ khóa:** qualifier **thu hẹp** tập ứng viên đã tương thích Java type. Annotation không thể khiến `PaymentGateway` được inject vào tham số `Sender` nếu class không tương thích kiểu. Nó cũng không biến tên bean thành object khi code ngoài Spring chỉ gọi `new`.

## 3. Một annotation tùy biến cần những thành phần nào?

Một qualifier tự viết cho kênh thông báo:

~~~java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

import org.springframework.beans.factory.annotation.Qualifier;

enum Channel {
    EMAIL, SMS
}

@Target({
        ElementType.FIELD,
        ElementType.PARAMETER,
        ElementType.METHOD,
        ElementType.TYPE,
        ElementType.ANNOTATION_TYPE
})
@Retention(RetentionPolicy.RUNTIME)
@Qualifier
public @interface ChannelTag {
    Channel value();
}
~~~

**Đây là mẫu annotation minh họa**, không phải toàn bộ file Java: một file Java không thể vừa có public annotation này vừa có public demo class khác. Ở mục 7, annotation được khai báo **nested trong một public class**, do đó không có lỗi nhiều public top-level types.

### Ba thành phần thiết yếu

**`@Qualifier`:** đây là meta-annotation Spring nhận biết, đặt **trên khai báo annotation của bạn**. Nó nói rằng `@ChannelTag` phải được xem như một qualifier annotation khi Spring chọn ứng viên. Không cần tự viết `BeanPostProcessor` chỉ để thực hiện custom qualifier cơ bản.

**`@Retention(RetentionPolicy.RUNTIME)`:** bảo đảm annotation tồn tại ở runtime để Spring có thể đọc qua metadata/reflection. Nếu chỉ để mặc định `CLASS` hoặc đặt `SOURCE`, việc chọn candidate theo annotation ấy có thể không hoạt động đúng khi container chạy.

**`@Target(...)`:** chọn những vị trí được phép gắn. Trong demo:
- `PARAMETER` cho tham số constructor/factory method.
- `METHOD` để đánh dấu `@Bean` factory method.
- `TYPE` để gắn trên class/component khi dùng component scanning.
- `FIELD` cho field injection được Spring quản lý.
- `ANNOTATION_TYPE` nếu muốn xây một annotation tổng hợp thêm một tầng.

Không bắt buộc dùng tất cả targets; hãy chỉ khai báo đúng **vị trí bạn thật sự hỗ trợ**. Ví dụ chỉ khai báo `FIELD, PARAMETER` mà sau đó đặt qualifier lên `@Bean` method sẽ **không biên dịch được** vì `METHOD` không được phép.

**Member `value()`:** cho phép viết `@ChannelTag(Channel.EMAIL)`, truyền **giá trị enum có type rõ**. Nhờ enum, viết sai `Channel.EMIAL` sẽ bị Java compiler bắt ngay, khác với string literal `"EMIAL"` có thể lọt tới runtime.

### Một qualifier nữa cho thị trường

~~~java
@Target({
        ElementType.FIELD, ElementType.PARAMETER,
        ElementType.METHOD, ElementType.TYPE,
        ElementType.ANNOTATION_TYPE
})
@Retention(RetentionPolicy.RUNTIME)
@Qualifier
public @interface MarketTag {
    String value();
}
~~~

**Snippet minh họa** tương tự. Dùng String như `"VN"`/`"GLOBAL"` có thể đủ ở bài nhỏ; hệ thống lớn nên cân nhắc enum `Market.VN` hoặc value object để tránh typo và bảo vệ hợp đồng.

**Lưu ý về Java:** `ChannelTag` và `MarketTag` ở đây là **annotation types**, khác `ChannelTag.class` là kiểu Class của annotation và khác object bean. Spring **không tạo instance bean** chỉ vì nhìn thấy annotation.

## 4. Dùng qualifier ở cả hai đầu: bean definition và injection point

Đặt metadata trên những beans:

~~~java
@Configuration(proxyBeanMethods = false)
class SenderConfig {
    @Bean("vnEmailSender")
    @ChannelTag(Channel.EMAIL)
    @MarketTag("VN")
    Sender vnEmailSender() {
        return new InMemorySender("VN_EMAIL");
    }

    @Bean("globalEmailSender")
    @ChannelTag(Channel.EMAIL)
    @MarketTag("GLOBAL")
    Sender globalEmailSender() {
        return new InMemorySender("GLOBAL_EMAIL");
    }

    @Bean("vnSmsSender")
    @ChannelTag(Channel.SMS)
    @MarketTag("VN")
    Sender vnSmsSender() {
        return new InMemorySender("VN_SMS");
    }
}
~~~

**Snippet cấu hình**, cần các type/imports và implementation; ví dụ hoàn chỉnh ở mục 7.

Nhìn các bean như những hàng dữ liệu định danh:

| Bean name | Java type | Channel qualifier | Market qualifier |
| --- | --- | --- | --- |
| `vnEmailSender` | `Sender` | EMAIL | VN |
| `globalEmailSender` | `Sender` | EMAIL | GLOBAL |
| `vnSmsSender` | `Sender` | SMS | VN |

Khi consumer yêu cầu:

~~~java
public VnEmailClient(
        @ChannelTag(Channel.EMAIL)
        @MarketTag("VN")
        Sender sender) {
    this.sender = sender;
}
~~~

Spring lọc những beans hợp kiểu `Sender`, sau đó kiểm tra metadata qualifiers cần khớp; chỉ còn `vnEmailSender`. **Không có lý do dựa vào thứ tự method khai báo**.

### Hai annotations đồng thời là điều kiện kết hợp

`@ChannelTag(Channel.EMAIL) @MarketTag("VN")` yêu cầu ứng viên phù hợp **cả hai chiều**. Không phải Spring tự chọn EMAIL *hoặc* VN. Trong bảng:

- `vnEmailSender` khớp **cả hai** → hợp lệ.
- `globalEmailSender` khớp EMAIL, nhưng không khớp VN → loại.
- `vnSmsSender` khớp VN, nhưng không khớp EMAIL → loại.

Nếu bạn chỉ yêu cầu `@ChannelTag(Channel.EMAIL) Sender sender` ở điểm **đơn trị**, có **hai beans EMAIL**, nên vẫn có thể ambiguity. Qualifier không có nghĩa bảo đảm duy nhất; nó chỉ là điều kiện lọc.

**Nguyên tắc tốt:** annotation mô tả **đặc tính nghiệp vụ** của bean. Không nên đặt tên `@ExactBeanWithNameVnEmailSender` rồi coi đó là kiến trúc độc lập tên bean.

## 5. Đặt qualifier trên @Component hay trên @Bean?

Spring hỗ trợ metadata qualifier trên bean component đã được scan:

~~~java
@Component
@ChannelTag(Channel.EMAIL)
@MarketTag("VN")
public final class VietnamEmailSender implements Sender {
    // Implement Sender...
}
~~~

Với bean do `@Bean` method tạo, hãy đặt qualifier ở **factory method/bean definition** như mục 4:

~~~java
@Bean("vnEmailSender")
@ChannelTag(Channel.EMAIL)
@MarketTag("VN")
Sender sender() {
    return new InMemorySender("VN_EMAIL");
}
~~~

**Hai đoạn là snippets thay thế**, không chạy cùng demo. Phân biệt:

- Class-level qualifier có ích khi một class component tương ứng một bộ đặc tính nhất định.
- Method-level qualifier cho phép cùng một implementation class sinh **nhiều beans khác nhau**, mỗi definition có đặc tính kênh/thị trường riêng.
- Không chỉ đánh dấu class `InMemorySender` với `@ChannelTag(EMAIL)` rồi kỳ vọng hai bean SMS/VN và EMAIL/VN tạo từ class ấy tự có metadata khác nhau. Khi biến thể được cấu hình từ factory method, hãy gắn đúng annotation **trên từng method**.
- `@Component` và `@Bean` là các đường đăng ký; `@ChannelTag` một mình **không phải stereotype tạo bean**.
- Class có `@Component` nằm ngoài phạm vi component scan cũng chưa tự xuất hiện; ví dụ runnable gọi `context.register(...)` tường minh.

### Có cần @Autowired trên constructor?

Nếu component class chỉ có **một constructor**, Spring 4.3+ có thể tự chọn constructor đó mà không cần `@Autowired`:

~~~java
@Component
public final class VnEmailClient {
    private final Sender sender;

    public VnEmailClient(
            @ChannelTag(Channel.EMAIL)
            @MarketTag("VN")
            Sender sender) {
        this.sender = java.util.Objects.requireNonNull(sender);
    }
}
~~~

Snippet này cần các types và imports. Spring vẫn đọc **parameter annotations** của constructor duy nhất khi resolve collaborator. `@Autowired` không bắt buộc trong case đó; custom qualifiers không thay thế chức năng đăng ký bean.

Nếu có **nhiều constructors**, hãy làm rõ constructor được dùng bằng cơ chế `@Autowired`/definition phù hợp. Đừng cho rằng đặt qualifier trên một tham số tự buộc Spring chọn overload có tham số đó.

## 6. Bài học về dùng collection và @Order

Một service cần gửi thông điệp qua **tất cả kênh EMAIL**, không cần giới hạn một thị trường:

~~~java
public EmailBatch(
        @ChannelTag(Channel.EMAIL) List<Sender> senders) {
    this.senders = List.copyOf(senders);
}
~~~

Spring có thể inject **hai beans** phù hợp `@ChannelTag(Channel.EMAIL)`: VN_EMAIL và GLOBAL_EMAIL. Qualifier ở đây làm **bộ lọc collection**, không phải yêu cầu chọn một bean duy nhất.

Một service khác chỉ muốn tất cả senders của thị trường VN:

~~~java
public VnBatch(
        @MarketTag("VN") List<Sender> senders) {
    this.senders = List.copyOf(senders);
}
~~~

Nó nhận VN_EMAIL và VN_SMS.

**`@Order` có thể sắp các bean trong List/array injection**. Nếu annotations trên `@Bean` methods:

~~~java
@Bean
@Order(1)
@ChannelTag(Channel.EMAIL)
Sender firstEmail() { /* implementation */ }

@Bean
@Order(2)
@ChannelTag(Channel.EMAIL)
Sender secondEmail() { /* implementation */ }
~~~

đây là snippets **chỉ minh họa về metadata**; các methods cần trả Sender thực và phải tồn tại trong configuration class. Khi Spring inject `List<Sender>`, ordering có thể dựa trên `@Order`. **Không dùng `@Order(1)` để thay `@Primary` khi cần một bean đơn trị**.

**Cẩn thận:** `@Order` không tự bảo đảm singleton khởi tạo theo cùng thứ tự, và cũng không thay đổi điều kiện qualifier. Nó là thông tin sắp xếp kết quả collection. Khi nghiệp vụ cần thứ tự cứng, hãy gắn metadata/test rõ ràng; khi chỉ cần tập hợp không thứ tự, tránh tạo phụ thuộc không cần thiết vào thứ tự registration.

## 7. Ví dụ hoàn chỉnh Java 17+ / Spring Framework 6.2.19

**Ý tưởng:** giữ một interface `Sender`, ba beans cùng type nhưng được gắn nhãn nghiệp vụ. Ba consumers có hai custom qualifiers trong constructor, hai batch consumers lọc collection theo một chiều. Tất cả được Spring quản lý; không có network thực.

Chạy với **JDK 17+**, Maven và Spring Framework **6.2.19** (ghim cho khả năng tái lập, không khẳng định là bản Spring mới nhất). Không cần Spring Boot hoặc một dịch vụ gửi thật.

### 7.1. Cấu trúc project

~~~text
custom-business-qualifier/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── demo/
                └── BusinessQualifierDemo.java
~~~

### 7.2. pom.xml

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>custom-business-qualifier</artifactId>
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
                    <mainClass>demo.BusinessQualifierDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Spring dependencies được Maven resolve. Nếu chạy trực tiếp `javac`/`java`, compile/runtime classpath phải có `spring-context` và các transitive JAR cần thiết.

### 7.3. src/main/java/demo/BusinessQualifierDemo.java

~~~java
package demo;

import java.lang.annotation.Documented;
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.util.List;
import java.util.Objects;
import java.util.stream.Collectors;

import org.springframework.beans.factory.NoUniqueBeanDefinitionException;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.stereotype.Component;

public final class BusinessQualifierDemo {
    private BusinessQualifierDemo() {}

    public enum Channel {
        EMAIL, SMS
    }

    @Documented
    @Retention(RetentionPolicy.RUNTIME)
    @Target({
        ElementType.FIELD, ElementType.PARAMETER,
        ElementType.METHOD, ElementType.TYPE,
        ElementType.ANNOTATION_TYPE
    })
    @Qualifier
    public @interface ChannelTag {
        Channel value();
    }

    @Documented
    @Retention(RetentionPolicy.RUNTIME)
    @Target({
        ElementType.FIELD, ElementType.PARAMETER,
        ElementType.METHOD, ElementType.TYPE,
        ElementType.ANNOTATION_TYPE
    })
    @Qualifier
    public @interface MarketTag {
        String value();
    }

    public interface Sender {
        String send(String recipient);
    }

    public record InMemorySender(String label) implements Sender {
        public InMemorySender {
            Objects.requireNonNull(label);
        }

        @Override
        public String send(String recipient) {
            if (recipient == null || recipient.isBlank()) {
                throw new IllegalArgumentException("recipient required");
            }
            return label + ":" + recipient.strip();
        }
    }

    @Component
    public static final class VnEmailClient {
        private final Sender sender;

        public VnEmailClient(
                @ChannelTag(Channel.EMAIL)
                @MarketTag("VN")
                Sender sender) {
            this.sender = Objects.requireNonNull(sender);
        }

        public Sender sender() {
            return sender;
        }

        public String notify(String recipient) {
            return sender.send(recipient);
        }
    }

    @Component
    public static final class GlobalEmailClient {
        private final Sender sender;

        public GlobalEmailClient(
                @ChannelTag(Channel.EMAIL)
                @MarketTag("GLOBAL")
                Sender sender) {
            this.sender = Objects.requireNonNull(sender);
        }

        public String notify(String recipient) {
            return sender.send(recipient);
        }
    }

    @Component
    public static final class VnSmsClient {
        private final Sender sender;

        public VnSmsClient(
                @ChannelTag(Channel.SMS)
                @MarketTag("VN")
                Sender sender) {
            this.sender = Objects.requireNonNull(sender);
        }

        public String notify(String recipient) {
            return sender.send(recipient);
        }
    }

    @Component
    public static final class EmailBatch {
        private final List<Sender> senders;

        public EmailBatch(@ChannelTag(Channel.EMAIL)
                          List<Sender> senders) {
            this.senders = List.copyOf(senders);
        }

        public int size() {
            return senders.size();
        }

        public String sendAll(String recipient) {
            return senders.stream()
                    .map(sender -> sender.send(recipient))
                    .collect(Collectors.toList()).toString();
        }
    }

    @Component
    public static final class VnBatch {
        private final List<Sender> senders;

        public VnBatch(@MarketTag("VN") List<Sender> senders) {
            this.senders = List.copyOf(senders);
        }

        public String sendAll(String recipient) {
            return senders.stream()
                    .map(sender -> sender.send(recipient))
                    .toList().toString();
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class SenderConfig {
        @Bean("vnEmailSender")
        @ChannelTag(Channel.EMAIL)
        @MarketTag("VN")
        @Order(1)
        public Sender vnEmailSender() {
            return new InMemorySender("VN_EMAIL");
        }

        @Bean("globalEmailSender")
        @ChannelTag(Channel.EMAIL)
        @MarketTag("GLOBAL")
        @Order(2)
        public Sender globalEmailSender() {
            return new InMemorySender("GLOBAL_EMAIL");
        }

        @Bean("vnSmsSender")
        @ChannelTag(Channel.SMS)
        @MarketTag("VN")
        @Order(3)
        public Sender vnSmsSender() {
            return new InMemorySender("VN_SMS");
        }
    }

    public static void main(String[] args) {
        try (AnnotationConfigApplicationContext context =
                new AnnotationConfigApplicationContext()) {
            // Explicit registration; no package scanning assumptions.
            context.register(SenderConfig.class,
                    VnEmailClient.class, GlobalEmailClient.class,
                    VnSmsClient.class, EmailBatch.class, VnBatch.class);
            context.refresh();

            VnEmailClient vnEmail =
                    context.getBean(VnEmailClient.class);
            GlobalEmailClient globalEmail =
                    context.getBean(GlobalEmailClient.class);
            VnSmsClient vnSms =
                    context.getBean(VnSmsClient.class);
            EmailBatch emailBatch = context.getBean(EmailBatch.class);
            VnBatch vnBatch = context.getBean(VnBatch.class);

            System.out.println("vnEmail=" +
                    vnEmail.notify(" Lan "));
            System.out.println("globalEmail=" +
                    globalEmail.notify(" Minh "));
            System.out.println("vnSms=" + vnSms.notify(" An "));
            System.out.println("emailBatch=" +
                    emailBatch.sendAll(" Mai "));
            System.out.println("vnBatch=" +
                    vnBatch.sendAll(" Hoa "));
            System.out.println("sameVnEmail=" +
                    (vnEmail.sender()
                     == context.getBean("vnEmailSender", Sender.class)));
            System.out.println("senderNames=" +
                    java.util.Arrays.stream(
                            context.getBeanNamesForType(Sender.class))
                            .sorted().toList());

            try {
                context.getBean(Sender.class);
                System.out.println("rawTypeLookup=UNEXPECTED");
            } catch (NoUniqueBeanDefinitionException expected) {
                System.out.println("rawTypeLookup=AMBIGUOUS");
            }

            System.out.println("emailBatchCount=" +
                    emailBatch.size());
        }
    }
}
~~~

**Vì sao ví dụ rõ và chạy độc lập:**

- Có đúng một public top-level class `BusinessQualifierDemo`; annotations, enum, records, config và consumer classes là nested types. Tên tệp/package khớp CLI.
- `@ChannelTag` và `@MarketTag` được khai báo `public @interface` nested, có `@Qualifier`, `@Retention(RUNTIME)`, `@Target` và `@Documented`.
- `SenderConfig` đăng ký ba beans có cùng declared return type `Sender` nhưng qualifier metadata khác nhau, qua ba `@Bean` methods riêng.
- Ba client components chỉ có một constructor, nên Spring nhận diện injection constructor không cần `@Autowired`, nhưng các parameter qualifiers vẫn được áp dụng.
- `EmailBatch`/`VnBatch` cũng được đăng ký trực tiếp. `@ChannelTag(EMAIL) List<Sender>` lọc hai bean EMAIL; `@MarketTag("VN") List<Sender>` lọc hai bean VN.
- `@Order(1)`/`@Order(2)`/`@Order(3)` trên từng `@Bean` method làm ordering rõ trong collections. Chỉ có ba labels nên stdout không phụ thuộc order của một HashMap.
- `java.util.Arrays.stream(...).sorted().toList()` sắp tên beans trước khi in, không phụ thuộc thứ tự registration không quan trọng.
- `InMemorySender` là record Java 17, thay sender thật bằng logic đơn giản; không có network, timer, random hoặc I/O ngoài stdout.
- Vì ba beans `Sender` tồn tại song song, `getBean(Sender.class)` không được cung cấp một qualifier/primary; demo bắt đúng `NoUniqueBeanDefinitionException`.
- Beans mặc định singleton trong context này; `sameVnEmail=true` chỉ chứng minh identity của bean được inject trong **một context**, không hứa hẹn về prototype/scoped proxies hoặc contexts khác.

### 7.4. Lệnh chạy bằng Maven

Trong thư mục `custom-business-qualifier`:

~~~bash
java -version
javac -version
mvn -version
mvn -q clean compile exec:java
~~~

**Đúng chín dòng stdout do `main` in khi chương trình thành công:**

~~~text
vnEmail=VN_EMAIL:Lan
globalEmail=GLOBAL_EMAIL:Minh
vnSms=VN_SMS:An
emailBatch=[VN_EMAIL:Mai, GLOBAL_EMAIL:Mai]
vnBatch=[VN_EMAIL:Hoa, VN_SMS:Hoa]
sameVnEmail=true
senderNames=[globalEmailSender, vnEmailSender, vnSmsSender]
rawTypeLookup=AMBIGUOUS
emailBatchCount=2
~~~

Những dòng phiên bản Java/Maven, downloading artifacts hoặc log Spring/Maven (nếu xuất hiện) không thuộc chín dòng do `System.out.println` trong code trên phát ra.

### 7.5. Chạy trực tiếp bằng javac/java

Tạo classpath từ các dependencies do Maven resolve:

~~~bash
mvn -q dependency:build-classpath -Dmdep.outputFile=classpath.txt
~~~

Linux/macOS (bash/zsh):

~~~bash
mkdir -p out
javac --release 17 -encoding UTF-8 \
  -cp "$(cat classpath.txt)" \
  -d out src/main/java/demo/BusinessQualifierDemo.java
java -cp "out:$(cat classpath.txt)" demo.BusinessQualifierDemo
~~~

Windows PowerShell:

~~~powershell
$deps = (Get-Content -Raw classpath.txt).Trim()
New-Item -ItemType Directory -Force out | Out-Null
javac --release 17 -encoding UTF-8 -cp "$deps" -d out src/main/java/demo/BusinessQualifierDemo.java
java -cp "out;$deps" demo.BusinessQualifierDemo
~~~

Trên Unix, classpath separator là `:`; trên Windows là `;`. Hai cách chạy cùng `main`, nên chín dòng do code in là như nhau. Nếu `javac` báo không thấy `org.springframework.*`, cần kiểm tra build/classpath trước khi kết luận custom annotation hoặc bean resolution có lỗi.

## 8. Giải thích kết quả: qualifier thực sự chọn theo nghiệp vụ

| Dòng stdout | Ý nghĩa |
| --- | --- |
| `vnEmail=VN_EMAIL:Lan` | Hai conditions EMAIL + VN chọn đúng sender |
| `globalEmail=GLOBAL_EMAIL:Minh` | EMAIL + GLOBAL chọn implementation khác |
| `vnSms=VN_SMS:An` | SMS + VN chọn bean VN_SMS |
| `emailBatch=[VN_EMAIL:Mai, GLOBAL_EMAIL:Mai]` | Collection lọc theo EMAIL, không giới hạn market |
| `vnBatch=[VN_EMAIL:Hoa, VN_SMS:Hoa]` | Collection lọc theo VN, không giới hạn channel |
| `sameVnEmail=true` | Bean qua custom qualifiers chính là bean Spring tên vnEmailSender |
| `senderNames=[...]` | Cả ba Sender beans đã được đăng ký song song |
| `rawTypeLookup=AMBIGUOUS` | Lookup bằng type trần cần một nhưng không có chọn lựa duy nhất |
| `emailBatchCount=2` | Bộ lọc EMAIL trả đúng hai candidates |

Tại client constructor, `@ChannelTag(Channel.EMAIL)` và `@MarketTag("VN")` là **injection-point metadata**. Trong `SenderConfig`, cùng các annotations ấy là **candidate metadata**. Spring đối chiếu chúng khi resolve một `Sender` dependency.

**Điểm chính:** không có client nào gọi `ApplicationContext.getBean("vnEmailSender")` bên trong business method. Spring resolve dependency ở **composition/wiring phase**; client chỉ gọi interface `Sender`.

## 9. Có thể gộp nhiều điều kiện thành một annotation nhiều attributes

Thay vì hai annotations:

~~~java
@ChannelTag(Channel.EMAIL)
@MarketTag("VN")
Sender sender
~~~

bạn có thể định nghĩa một domain qualifier có hai members:

~~~java
@Target({
    ElementType.FIELD, ElementType.PARAMETER,
    ElementType.METHOD, ElementType.TYPE
})
@Retention(RetentionPolicy.RUNTIME)
@Qualifier
public @interface RouteTag {
    Channel channel();
    String market();
}
~~~

Rồi áp dụng:

~~~java
@Bean
@RouteTag(channel = Channel.EMAIL, market = "VN")
Sender vnEmailSender() {
    return new InMemorySender("VN_EMAIL");
}

public VnClient(
        @RouteTag(channel = Channel.EMAIL, market = "VN")
        Sender sender) {
    this.sender = sender;
}
~~~

**Các đoạn này là snippets thay thế, không phải file thứ hai được chạy.** Trong thực tế, cần import/định nghĩa `Channel`, `Sender`, `InMemorySender`, class `VnClient` và `@Configuration` tương ứng. Trong một custom qualifier có nhiều attributes, bean candidate phải **khớp các attributes được yêu cầu**. Giá trị mặc định của attribute (nếu có) là một giá trị metadata thực, **không tự động là wildcard**.

### Chọn một annotation nhiều attributes hay nhiều annotations độc lập?

| Thiết kế | Phù hợp khi | Điểm cần tránh |
| --- | --- | --- |
| `@ChannelTag(EMAIL) @MarketTag("VN")` | Channel/market là các chiều độc lập, có thể cần lọc từng chiều hoặc kết hợp | Viết annotation thiếu một điều kiện khi consumer cần đủ hai |
| `@RouteTag(channel=EMAIL, market="VN")` | Cặp channel + market tạo một khái niệm nghiệp vụ có tính nguyên khối | Nghĩ bỏ attribute/đặt default sẽ tự có wildcard |
| `@Qualifier("vnEmailSender")` | Hệ thống nhỏ hoặc consumer cần đúng bean với tên ổn định | Khóa vào tên bean khó đổi |
| `@Primary` | Có một default hợp lệ trên phần lớn consumers | Không diễn đạt đúng lựa chọn riêng cho từng thị trường |
| Inject `List<Sender>` có filter qualifier | Consumer cần nhiều strategies cùng đặc tính | Đừng lấy phần tử đầu như cách ngẫu nhiên chọn một |

Nếu business dùng một taxonomy kênh hoặc thị trường chuẩn, ưu tiên **enum** cho giá trị hữu hạn. Nếu metadata có nhiều chiều có thể thay đổi độc lập, các qualifiers nhỏ giúp composition linh hoạt hơn.

## 10. Hợp đồng annotation tốt: đặt tên, kiểu, phạm vi

### 10.1. Đặt tên theo ngữ nghĩa

Tên `@ChannelTag` và `@MarketTag` nói lên đặc tính. Một annotation như `@EmailSenderBean42` hoặc `@BeanImplA` buộc business code biết cách đăng ký implementation. Qualifier nên mô tả **vai trò** thay vì internal bean identity.

Ví dụ các ý nghĩa có thể phù hợp theo domain:

- `@StorageTier(Storage.COLD)` / `@StorageTier(Storage.HOT)`.
- `@Region(Region.APAC)` / `@Region(Region.EMEA)`.
- `@DeliveryChannel(Channel.EMAIL)` / `@DeliveryChannel(Channel.SMS)`.
- `@ReadReplica` / `@PrimaryStore`, nếu thiết kế database routing thực sự cần phân biệt.

Những ví dụ trên chỉ là **tên minh họa**, không phải annotation types có sẵn trong Spring.

### 10.2. Làm rõ cardinality

Một qualifier **không nhất thiết duy nhất** trong toàn bộ context. Có thể có hai beans EMAIL vì hai markets. Với injection một Sender, hãy chắc rằng kết hợp qualifiers/candidate selection thu về đúng một. Với collection injection, việc có nhiều matches là đúng chủ đích.

Nếu một loại business contract yêu cầu **duy nhất một implementation**, cần test startup để phát hiện có hai bean cùng type/qualifiers sau khi thêm module.

### 10.3. Chọn dữ liệu có type

Sử dụng `Channel.EMAIL` thay vì string `"EMAIL"` giúp tránh typo ở compile time. Với `String market`, nên thống nhất hằng hoặc enum nếu danh mục hữu hạn; cẩn thận với casing/locale. Spring không tự hiểu `"VN"` tương đương `"vn"` trong một qualifier string.

### 10.4. Không tạo nghiệp vụ giả trong annotation

Annotations chứa metadata tĩnh; chúng không phải nơi tính quyết định phức tạp dựa trên user, request hoặc thời gian. Nếu khách hàng có thể chuyển kênh theo một input runtime, injection một Sender cố định ở startup có thể không đủ. Hãy inject **Map/list/provider** các strategies phù hợp rồi chọn bằng **domain routing policy** được test. Đừng dùng một annotation mà mong nó thay đổi cho từng HTTP request.

### 10.5. Scope và lifecycle không do qualifier quyết định

Custom qualifier chỉ tham gia **chọn ứng viên**. Nó không biến bean thành singleton/prototype, không làm object thread-safe, không tạo transaction hoặc đổi thời điểm khởi tạo. Chọn đúng bean còn phải kiểm tra lifecycle, scope và tính an toàn khi cùng instance được dùng nhiều luồng.

## 11. Spring xem custom qualifier metadata ở những vị trí nào?

**Component class:**

~~~java
@Component
@ChannelTag(Channel.EMAIL)
public class EmailSender implements Sender {
    // ...
}
~~~

**@Bean factory method:**

~~~java
@Bean
@ChannelTag(Channel.EMAIL)
Sender sender() {
    return new InMemorySender("EMAIL");
}
~~~

**Constructor parameter:**

~~~java
public Client(@ChannelTag(Channel.EMAIL) Sender sender) {
    this.sender = sender;
}
~~~

**Field injection:**

~~~java
@Autowired
@ChannelTag(Channel.EMAIL)
private Sender sender;
~~~

**Setter/method parameter:**

~~~java
@Autowired
public void setSender(
        @ChannelTag(Channel.EMAIL) Sender sender) {
    this.sender = sender;
}
~~~

**Snippets minh họa**, mỗi đoạn cần class/import và definitions tương ứng; không ghép chúng vào project chính vì có thể tạo thêm beans cùng qualifier ngoài ý định. Với collaborator bắt buộc, constructor injection nhìn rõ dependency hơn field/setter injection và dễ unit test bằng Java thuần.

**Không cần đặt `@Autowired` trên mỗi parameter**. Ở Spring, khi method/constructor được chọn làm injection point, metadata như custom qualifier được đọc từ parameter. Với một constructor duy nhất trên component, Spring có thể tự dùng constructor không cần `@Autowired`.

Nếu một class do Java `new` ở ngoài container, việc bạn gắn field `@ChannelTag` và `@Autowired` **không làm JVM tự inject**; đó vẫn là object unmanaged, phải được Spring xử lý hoặc có manual DI.

## 12. @Primary, @Fallback và qualifier tương tác ra sao?

| Cơ chế | Vai trò |
| --- | --- |
| `@Qualifier("...")` | Thu hẹp candidate theo metadata/bean name phù hợp |
| Custom `@ChannelTag`/`@MarketTag` | Thu hẹp theo nghĩa nghiệp vụ có type |
| `@Primary` | Chỉ một preferred candidate mặc định khi phù hợp |
| `@Fallback` | Hạ ưu tiên candidate trong Spring Framework 6.2+ |
| `@Order` | Sắp collection injection; không giải quyết ngầm một bean đơn trị |
| `@Bean(defaultCandidate=false)` | Chỉ dùng khi injection có chỉ dẫn thêm như qualifier phù hợp |
| `@Bean(autowireCandidate=false)` | Loại bean khỏi type-driven autowiring; không phải chỉ là ưu tiên thấp |

Tư duy quan trọng là **chọn trong tập type-compatible candidates có metadata phù hợp**, không nghĩ annotation nào cũng làm bean được đăng ký, tồn tại hoặc bị loại hoàn toàn.

**Ví dụ:** nếu `globalEmailSender` được đánh dấu `@Primary`, injection point đòi **EMAIL+VN** không được âm thầm nhận GLOBAL. Bean GLOBAL không thỏa `@MarketTag("VN")`. Ngược lại, injection chỉ yêu cầu EMAIL có thể nhận primary GLOBAL nếu quy tắc resolution áp dụng phù hợp.

**Không viết nhiều `@Primary` trên các beans cùng type** rồi hy vọng Spring giải quyết ambiguity. Hãy chọn một default có lý do nghiệp vụ hoặc dùng qualifier rõ ở consumer.

## 13. Hai lỗi chính sau khi tự tạo qualifier: không có bean hoặc còn nhiều beans

### Không có candidate phù hợp

Ví dụ consumer yêu cầu `@ChannelTag(Channel.SMS) @MarketTag("GLOBAL") Sender`, nhưng chỉ đăng ký các bean VN_SMS, VN_EMAIL, GLOBAL_EMAIL.

Spring thấy không có bean nào thỏa **cả SMS lẫn GLOBAL**, nên dependency bắt buộc fail. Có thể thấy `UnsatisfiedDependencyException` với nguyên nhân `NoSuchBeanDefinitionException` hoặc thông điệp “No qualifying bean” tùy đường tạo/phiên bản.

**Cách sửa:** đăng ký đúng bean SMS_GLOBAL nếu nghiệp vụ có nó, hoặc sửa ý định consumer nếu bạn yêu cầu sai. **Không** tự đổi thành `@Autowired(required=false)` chỉ để startup thành công khi dependency thực sự bắt buộc.

### Nhiều candidates cùng qualifier

Nếu bạn vô tình có hai bean cùng kiểu `Sender`, cùng `@ChannelTag(EMAIL)` và `@MarketTag("VN")`, injection đơn trị vẫn **có thể ambiguity**. Tên bean khác nhau không giúp qualifier trở nên duy nhất.

**Cách sửa:** xác định có thật cần hai implementations cho cùng route không. Nếu có, consumer cần một quy tắc chọn cụ thể hơn hoặc injection collection/provider. Nếu không, sửa registration để chỉ một bean cho hợp đồng đó. `@Primary` có thể là lựa chọn nếu thật sự có một default, nhưng cần test để tránh giấu lỗi cấu hình.

### Không có annotation vì quên @Retention(RUNTIME)

Một custom annotation không có runtime retention có thể xuất hiện trong source nhưng không được Spring thấy khi resolve metadata. Kiểm tra định nghĩa annotation, không chỉ kiểm tra injection point.

### @Target đặt quá hẹp

Khai báo `@Target(FIELD)` rồi đặt lên method `@Bean` sẽ lỗi compile. Khi annotation dùng cả trên bean definition và parameter, cần `METHOD` và `PARAMETER` (ngoài các targets thích hợp khác).

### Quên @Qualifier trên định nghĩa annotation

Một annotation tự định nghĩa nhưng không có meta-annotation Spring `@Qualifier` (hoặc chưa đăng ký bằng cách Spring hỗ trợ) thường chỉ là metadata Java tùy ý, **không tự trở thành autowiring qualifier**. Nếu muốn qualifier dựa trên Spring, đặt `@Qualifier` đúng chỗ.

Spring còn có `CustomAutowireConfigurer` cho những loại annotation bạn không thể sửa để gắn Spring `@Qualifier`; đó là công cụ infrastructure riêng, **không cần trong demo**.

### Chỉ gắn annotation trên injection point

Nếu bean candidate không có qualifier metadata tương ứng, Spring không thể dựa trên annotation nghiệp vụ đó để xác nhận route. Kiểm tra **cả nơi khai báo bean lẫn nơi inject**, nhất là khi bean sinh từ `@Bean` factory method.

### Sai bean registration và component scan

Class có `@Component` nhưng không được scan/register thì không thành bean. Class có `@ChannelTag` nhưng không phải stereotype hoặc không được khai báo qua `@Bean` cũng không tự thành bean. Đọc thực tế những beans đã có trong context.

### Lỗi type/generic metadata

Qualifier không biến một `Sender<Email>` thành `Sender<Sms>` nếu generic specialization không tương thích. Bean factory method khai báo type quá chung cũng có thể gây khó cho matching; giữ declared return type diễn đạt đầy đủ contract.

## 14. Chẩn đoán bằng phương pháp có hệ thống

| Dấu hiệu | Kiểm tra | Hướng sửa |
| --- | --- | --- |
| `NoUniqueBeanDefinitionException` | Nhiều Sender beans thỏa cùng qualifiers | Bổ sung điều kiện có nghĩa hoặc đổi consumer sang List/Map |
| `NoSuchBeanDefinitionException` | Không có candidate thỏa type + qualifier | Kiểm tra metadata cả bean và injection point |
| `UnsatisfiedDependencyException` | Constructor/factory parameter không resolve được | Đọc `Caused by`, bean names và qualifiers |
| Annotation bị bỏ qua | Thiếu `@Qualifier` meta hoặc `RUNTIME` | Sửa khai báo custom annotation |
| Annotation không thể gắn @Bean | Thiếu `METHOD` trong `@Target` | Bổ sung target đúng chỗ |
| Class có @Component nhưng không có bean | Không scan/register | Cấu hình component scan hoặc register tường minh |
| Chỉ một consumer được đúng bean, consumer khác sai | Khác qualifier, tên/giá trị string typo | So attribute values/casing tại từng injection point |
| List có hai beans nhưng chỉ muốn một | Injection point chọn List thay vì một Sender | Đặt lại cardinality đúng nghiệp vụ |
| Thứ tự List sai | Thiếu/nhầm `@Order` | Gắn order trên đúng @Bean method/component |
| String qualifier không tìm được match | Giá trị không đúng, khác chữ hoa thường | Dùng enum/hằng, thêm wiring test |
| Không có bean khi đổi profile | Bean definition bị loại theo profile/condition | Kiểm tra active profiles và bean registration |
| Dùng @Primary nhưng route sai | Tưởng primary được vượt qua qualifier | Làm rõ type/qualifier set và test identity |
| Test unit new class nhưng field @Autowired null | Object ngoài Spring | Dùng constructor injection hoặc context test cho wiring |
| `javac` thiếu Spring packages | Build/classpath thiếu dependency | Kiểm tra Maven POM và javac -cp |

**Quy trình debug đáng tin:**

1. Xác định **injection point** đang cần kiểu nào, có bao nhiêu qualifier và các attribute values là gì.
2. Liệt kê **bean definitions thực sự đăng ký**; kiểm tra tên, declared return type, scope, qualifier metadata.
3. Kiểm tra tương thích **type/generic** trước, rồi đối chiếu **từng qualifier**.
4. Kiểm tra `@Primary`/`@Fallback`/candidate flags và những điều kiện profile liên quan.
5. Nếu còn nhiều bean, hỏi có cần single candidate hay collection. Nếu không có bean, tìm nguyên nhân registration hoặc metadata mismatch.
6. Dùng Spring context test với ít bean nhất tái lập sự cố; không dựa vào thứ tự source code.
7. Xác minh **bean object identity và hành vi** thay vì chỉ nhìn context đã refresh không lỗi.

### Inspect nhanh trong context

~~~java
String[] names = context.getBeanNamesForType(Sender.class);
java.util.Arrays.sort(names);
System.out.println(java.util.Arrays.toString(names));
~~~

**Snippet** cho biết những bean names cùng type; cần chạy trong scope có context và interface `Sender`. **Sự tồn tại trong danh sách không có nghĩa bean thỏa mọi custom qualifier**. Muốn xác nhận điều kiện đúng, kiểm tra injection thực tế hoặc metadata ở definition phù hợp.

## 15. Kiểm thử để giữ hợp đồng nghiệp vụ

**Unit test Java thuần:** constructor của `VnEmailClient` nhận một `Sender` object. Nếu dùng fake:

~~~java
Sender fake = recipient -> "TEST:" + recipient;
VnEmailClient client = new VnEmailClient(fake);
System.out.println(client.notify("Lan")); // TEST:Lan
~~~

Đây là **snippet** khi có quyền truy cập nested types của demo. Annotation trên constructor parameter không có tác dụng tự chặn caller `new`; unit test Java truyền đúng dependency. Nó kiểm tra hành vi consumer, không xác minh Spring qualifier selection.

**Spring wiring test:** dùng config giống demo, kiểm tra:

- `VnEmailClient.sender() == context.getBean("vnEmailSender", Sender.class)`.
- `GlobalEmailClient` trả GLOBAL_EMAIL, `VnSmsClient` trả VN_SMS.
- `EmailBatch` chỉ chứa hai senders EMAIL và `VnBatch` chỉ chứa hai senders VN, đúng @Order.
- Lookup type trần `context.getBean(Sender.class)` thất bại vì ambiguity.
- Thêm một candidate sai market không làm đổi client đã có qualifier đủ chặt.
- Thiếu một candidate bắt buộc làm context fail trong **negative test riêng**.
- Đăng ký hai beans cùng route khiến single injection báo ambiguity nếu không có lựa chọn khác.

**Không dùng Java `assert` mặc định làm bảo đảm bắt buộc** nếu JVM không bật `-ea`; trong integration test, dùng test framework assertions hoặc if/throw. Không khóa test vào toàn bộ nguyên văn stack trace vì Spring có thể bọc exception/đổi wording giữa các versions.

### Khi nào custom qualifier là quá mức?

Một dự án có đúng **một** `Sender` implementation không cần ba annotation/enum khác nhau. Nếu chỉ có hai beans và một consumer, `@Qualifier("mainSender")` có thể đủ. Custom qualifiers hữu ích khi có **một khái niệm nghiệp vụ ổn định** được nhiều consumer dùng và cách đặt tên bean không biểu đạt hết ý định.

Tính "có giá trị" của abstraction nên được đánh giá qua khả năng hiểu code, tái sử dụng và giảm lỗi wiring, **không phải số annotations được viết**.

## 16. Bài tập tự kiểm tra

**Bài 1.** Ba beans: VN_EMAIL, GLOBAL_EMAIL, VN_SMS. Injection point `@ChannelTag(EMAIL) @MarketTag("VN") Sender` nhận gì?

**Đáp án:** Bean VN_EMAIL. Nó thỏa cả type Sender, channel EMAIL và market VN.

**Bài 2.** Chỉ có `@ChannelTag(EMAIL) Sender` ở một constructor cần đúng một object. Có chắc duy nhất không?

**Đáp án:** Không. Hai beans VN_EMAIL và GLOBAL_EMAIL cùng khớp channel, nên có thể gặp ambiguity.

**Bài 3.** `@ChannelTag(EMAIL) List<Sender>` nhận bao nhiêu phần tử?

**Đáp án:** Hai Senders EMAIL trong demo; qualifier là bộ lọc collection, không phải lệnh chọn một.

**Bài 4.** Vì sao cần `@Retention(RUNTIME)`?

**Đáp án:** Để metadata qualifier còn tồn tại khi Spring thực hiện bean candidate resolution tại runtime.

**Bài 5.** Đặt `@ChannelTag` chỉ trên injection parameter, không đặt trên các bean definitions. Có đủ không?

**Đáp án:** Không theo cấu hình demo; để Spring match theo channel, bean candidates phải có metadata qualifier tương ứng. Cần chú ý cả phía producer và consumer.

**Bài 6.** Dùng `@ChannelTag(EMAIL) @MarketTag("VN")` có nghĩa EMAIL hoặc VN không?

**Đáp án:** Không. Các qualifiers này được dùng kết hợp để ràng buộc candidate phải khớp điều kiện cần thiết, không tạo biểu thức OR tự động.

**Bài 7.** `@Order(1)` trên SMS có khiến single injection luôn nhận SMS không?

**Đáp án:** Không. @Order dùng sắp nhiều beans trong collection; single-valued injection cần quy tắc chọn riêng như qualifier/primary.

**Bài 8.** Có thể dùng cùng `InMemorySender` class cho nhiều bean routes khác nhau không?

**Đáp án:** Có. Đặt qualifier metadata trên từng `@Bean` factory method để phân biệt từng bean definition.

**Bài 9.** Nếu market name đổi từ VN thành VIETNAM ở producer nhưng injection point vẫn ghi VN, chuyện gì xảy ra?

**Đáp án:** Metadata không còn khớp, injection bắt buộc có thể fail. Dùng enum/constants và wiring test để giữ hợp đồng.

**Bài 10.** Khi một service cần chọn kênh theo request runtime, qualifier constructor cố định có giải quyết được không?

**Đáp án:** Không đủ. Hãy thiết kế router/strategy selection ở runtime, có thể inject nhiều Senders rồi ánh xạ theo domain key hợp lệ.

**Bài 11.** Custom qualifier có tự tạo một bean mới không?

**Đáp án:** Không. Nó chỉ là metadata giúp lọc những bean definitions đã được đăng ký qua cơ chế Spring phù hợp.

**Bài 12.** Bao giờ nên dùng một qualifier có nhiều attributes thay vì hai qualifiers độc lập?

**Đáp án:** Khi channel + market là một khái niệm đơn nhất luôn đi cùng nhau. Nếu từng chiều cần lọc collection độc lập, dùng hai qualifiers nhỏ thường linh hoạt hơn.

## 17. Checklist áp dụng

- [ ] Tên annotation nói rõ vai trò nghiệp vụ, không chỉ encode một bean name.
- [ ] Có `@Qualifier` trên **annotation declaration**.
- [ ] Có `@Retention(RetentionPolicy.RUNTIME)`.
- [ ] `@Target` cho phép `PARAMETER`, `METHOD`, `TYPE` hoặc `FIELD` đúng nhu cầu.
- [ ] Member `value()`/named attributes có type rõ, ưu tiên enum khi phù hợp.
- [ ] Gắn qualifier lên từng `@Bean` method hoặc component class cần phân biệt.
- [ ] Gắn đúng qualifier vào injection point, không chỉ producer hoặc chỉ consumer.
- [ ] Nếu nhiều qualifiers, xác định đây là **AND**, không phải OR.
- [ ] Với single-valued injection, xác minh chỉ một candidate hợp lệ.
- [ ] Với collection, xác minh đủ thành viên và thứ tự mong muốn.
- [ ] Không dùng `@Order` thay `@Qualifier`/`@Primary` cho single injection.
- [ ] Không dựa vào tên bean/parameter tình cờ nếu business semantics cần bền vững.
- [ ] Không đánh dấu `@Primary` bừa bãi để che hai bean trùng route.
- [ ] Không nhầm qualifier với stereotype, scope hoặc lifecycle.
- [ ] Có unit tests cho logic và integration tests cho đúng wiring.
- [ ] Chạy Java 17+ Maven/`javac`/`java` và đối chiếu **9 dòng stdout**.
- [ ] Với ứng dụng lớn, document taxonomy kênh/thị trường và sở hữu annotation.
- [ ] Khi version Spring đổi, kiểm tra chính sách candidate selection và tests trước khi deploy.

**Kết luận:** custom qualifier annotations là cách đưa **ngôn ngữ nghiệp vụ** vào ranh giới dependency injection. Thay vì chỉ yêu cầu một bean tên `vnEmailSender`, consumer có thể yêu cầu **Sender kênh EMAIL tại thị trường VN**. Spring lọc những bean tương thích type theo metadata qualifier, chọn một candidate hoặc trả collection các matches theo hợp đồng. Thiết kế annotation tốt cần đúng Java retention/target, producer/injection metadata nhất quán và test wiring để tránh lỗi khi ứng dụng thêm implementation mới.

### Tài liệu Spring chính thức

- [Spring Framework 6.2 — Fine-tuning Annotation-based Autowiring with Qualifiers](https://docs.spring.io/spring-framework/reference/6.2/core/beans/annotation-config/autowired-qualifiers.html)
- [Spring Framework 6.2 — Providing Qualifier Metadata with Annotations](https://docs.spring.io/spring-framework/reference/6.2/core/beans/classpath-scanning.html)
- [Spring Framework 6.2 — Using @Autowired](https://docs.spring.io/spring-framework/reference/6.2/core/beans/annotation-config/autowired.html)
- [Spring API — Qualifier](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/beans/factory/annotation/Qualifier.html)
- [Spring Framework 6.2 — CustomAutowireConfigurer](https://docs.spring.io/spring-framework/reference/6.2/core/beans/annotation-config/custom-autowire-configurer.html)
