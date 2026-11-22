# Chọn bean theo tên bằng `jakarta.annotation.Resource` trong Spring Core Container

## 1. `@Resource` giải quyết vấn đề gì?

Trong Spring IoC Container, ứng dụng có thể đăng ký **nhiều beans cùng Java type**, ví dụ hai implementation của `Channel`: `emailChannel` và `smsChannel`. Khi yêu cầu tiêm một `Channel`, cần có quy tắc xác định **bean nào** sẽ được cấp cho đối tượng.

Annotation **`jakarta.annotation.Resource`** cho phép mô tả một phụ thuộc **chủ yếu theo bean name**, thường áp dụng cho **instance field** hoặc **JavaBean property setter** của một Spring-managed bean. Đây là annotation chuẩn Jakarta Annotations (nguồn gốc JSR-250), không phải `org.springframework.beans.factory.annotation.Resource`.

Cú pháp rõ nhất:

~~~java
// Snippet: các type/bean này được định nghĩa trong dự án hoàn chỉnh ở mục 6.
@Resource(name = "smsChannel")
private Channel selected;
~~~

Khi Spring tạo bean chứa field này, nó tìm bean có **tên `smsChannel`** và đưa reference phù hợp vào field. Spring **không tạo một `Channel` mới** chỉ vì nhìn thấy annotation. Nếu bean `smsChannel` không được đăng ký, injection thường thất bại thay vì tự chọn bean tên khác.

**Nội dung cốt lõi của bài:**
- Cách chỉ định tên tường minh bằng `@Resource(name="...")`;
- Cách lấy tên **mặc định** từ field hoặc tên property của setter;
- Cách xử lý **alias**;
- **Ngoại lệ fallback theo type khi không chỉ định tên tường minh**;
- Khác biệt với `@Autowired`, `@Qualifier` và `@Primary`;
- Nguyên tắc chọn bean đúng type, xử lý thiếu/trùng/sai tên và kiểm chứng bằng Java 17+.

**Phạm vi**: Spring Framework Core Container thuần, Java 17, Maven; không dùng Spring Boot, database, HTTP server hoặc cơ chế auto-configuration.

## 2. Quy tắc chọn: tên tường minh, tên mặc định rồi fallback có điều kiện

Đọc quy trình khái niệm:

~~~text
          Injection point mang @Resource
                        |
                 Có name="..."?
                /                \
              CÓ                KHÔNG
               |                   |
               v                   v
       Lấy tên chỉ định   Lấy tên field/setter property
               |                   |
               v                   v
       Tìm bean theo tên  Có bean mang tên mặc định?
               |              /           \
          Tên có?          CÓ             KHÔNG
          /    \             |               |
        CÓ    KHÔNG           v               v
         |      |       Dùng bean tên ấy  Fallback theo type
         v      v           |             (mặc định được bật)
   Kiểm tra type  LỖI        v               |
         |             Kiểm tra type     Resolve candidate
         v                  |             theo type/primary
      Inject               Inject            |
                                              v
                                            Inject
~~~

**Trường hợp 1 — Có `name` tường minh.** Với `@Resource(name="smsChannel")`, Spring tìm **bean có chính tên được nêu** (hoặc alias hợp lệ). Không có bean ấy thì **không** âm thầm chuyển qua `emailChannel` dù email được `@Primary`. Nếu bean cùng tên có **type không tương thích**, injection cũng không thành công.

**Trường hợp 2 — Không chỉ định `name`.** Với `@Resource private Channel smsChannel;`, tên mặc định là **`smsChannel`**, xuất phát từ tên field. Với `@Resource void setArchiveChannel(Channel c)`, tên mặc định là tên JavaBean property **`archiveChannel`**, không phải tên tham số `c`.

**Trường hợp 3 — Tên mặc định không tồn tại.** Trong cấu hình Spring thông thường, `CommonAnnotationBeanPostProcessor` cho phép fallback từ tên mặc định sang **type matching** (cờ `fallbackToDefaultTypeMatch`, mặc định `true`). Nếu có một candidate nổi bật nhờ `@Primary` hoặc chỉ có một bean phù hợp, fallback có thể resolve thành công. Nếu nhiều candidates mơ hồ, có thể thất bại.

**Kết luận đúng:** `@Resource` là **by-name trước**, nhưng phát biểu “`@Resource` chỉ bao giờ tìm theo tên và không thể theo type” là **không chính xác** khi `name` bị bỏ trống. Ngược lại, không được dựa vào fallback để che một tên bean gõ sai có chủ đích; đặt tên tường minh khi hợp đồng thực sự cần một bean duy nhất.

## 3. `@Resource` và `@Autowired`/`@Qualifier` khác nhau thế nào?

| Tiêu chí | `@Resource` | `@Autowired` + `@Qualifier` |
| --- | --- | --- |
| Annotation | `jakarta.annotation.Resource` | `org.springframework.beans.factory.annotation.Autowired`, `Qualifier` |
| Ý nghĩa chủ đạo | **Tham chiếu một bean theo tên** | **Dependency theo type**, qualifier thu hẹp candidates |
| Tên chỉ định | `@Resource(name="smsChannel")` | `@Autowired @Qualifier("smsChannel")` |
| Nếu `name` tường minh không tìm được | Lỗi name lookup, không tự đổi sang bean khác | Candidate matching theo type+qualifier có thể thất bại |
| Nếu không ghi tên | Tên field/setter property rồi fallback theo type nếu không có bean mang tên ấy | Resolution theo type, metadata và quy tắc ưu tiên; tên field/parameter có thể hỗ trợ chọn candidate |
| Constructor injection | **Không dùng `@Resource` để đánh dấu constructor** | `@Autowired` hỗ trợ constructor; một constructor duy nhất thường không cần annotation |
| Phương thức nhiều tham số | Không dùng `@Resource` làm generic arbitrary multi-argument method injection | `@Autowired` hỗ trợ method nhiều tham số |
| Nhiều beans cùng type | Chọn bằng tên trực tiếp, kiểm tra type cuối cùng | `@Qualifier`, `@Primary`, generic/metadata giúp resolve |
| Tiện ích phù hợp | Integration points, tên bean cố định, chuyển tiếp alias, setter theo property name | Constructor DI, code theo interface, lựa chọn candidate theo vai trò/type |

`@Qualifier("smsChannel")` **không phải tuyệt đối đồng nghĩa** với `@Resource(name="smsChannel")`. Spring mô tả qualifier như **tiêu chí lọc bên trong tập beans khớp type**, không phải một yêu cầu tên chính duy nhất tách khỏi type. Còn `@Resource(name=...)` diễn đạt rõ mục tiêu **định danh theo bean name**.

**Đừng nhầm import:**

~~~java
import jakarta.annotation.Resource;
// Khác hoàn toàn với:
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
~~~

Ba import này chỉ minh họa vị trí API, không phải một chương trình Java độc lập. Một project cần **`jakarta.annotation-api`** trên compile classpath để import `@Resource`. Không dùng import cũ `javax.annotation.Resource` cho mã Spring Framework 7/Jakarta hiện đại.

### Có cần `@Primary` khi dùng `@Resource(name="...")`?

Không: nếu tên chỉ định tồn tại và bean có type phù hợp, Spring chọn theo tên ấy **ngay cả khi bean cùng type khác mang `@Primary`**. `@Primary` có ý nghĩa trong những tình huống cần resolve theo type, chẳng hạn fallback không có tên mặc định. Ví dụ mục 6 cố tình khai báo `emailChannel` là primary nhưng `@Resource(name="smsChannel")` vẫn lấy **SMS**.

## 4. Vị trí annotation được Spring hỗ trợ

### 4.1. Field (bao gồm private instance field)

~~~java
@Resource(name = "smsChannel")
private Channel selectedChannel;
~~~

Spring có thể gán field sau khi Java constructor tạo bean. Không cần setter công khai để dùng field injection. Tuy nhiên, object được tạo bằng `new Client()` ngoài Spring **không** được xử lý annotation. Nếu field chưa được gán, truy cập nó có thể gây `NullPointerException`.

Field injection giấu dependency khỏi constructor và không phù hợp để cung cấp dependency bắt buộc vào field `final`. Với code mới cần invariant và dễ unit test, cân nhắc constructor injection (qua `@Autowired` hoặc một constructor duy nhất) thay vì dùng `@Resource` chỉ để tránh vài dòng constructor.

### 4.2. JavaBean setter và tên property mặc định

~~~java
// Cần bean có tên "archiveChannel".
private Channel selected;

@Resource(name = "archiveChannel")
public void setSelected(Channel selected) {
    this.selected = selected;
}
~~~

Khi có `name` tường minh, bean name **`archiveChannel`** được chọn. Tên setter `setSelected` không bắt buộc trùng bean name.

Ngược lại:

~~~java
// Không chỉ định name. Tên property suy ra là "smsChannel".
private Channel selected;

@Resource
public void setSmsChannel(Channel channel) {
    this.selected = channel;
}
~~~

Spring sử dụng **`smsChannel`** từ property tương ứng với tên method `setSmsChannel` theo quy ước JavaBeans; **không** dùng tên local parameter `channel` để đặt tên mặc định.

**Giới hạn:** `@Resource` dùng theo hợp đồng field/bean property setter — không giống `@Autowired` tùy ý annotate một `configure(A, B)` có nhiều tham số. Nếu cần một constructor hoặc arbitrary multi-parameter config method, ưu tiên `@Autowired`/factory method injection có type rõ ràng.

### 4.3. Alias là một tên hợp lệ

Khi bean được đăng ký với tên chính và alias:

~~~java
@Bean(name = {"archiveChannel", "oldArchiveChannel"})
Channel archiveChannel() {
    return () -> "ARCHIVE";
}
~~~

`@Resource(name="oldArchiveChannel")` vẫn tra cứu được **cùng bean** với `getBean("archiveChannel")`. Alias không tạo bean definition thứ hai, không sao chép instance và không biến singleton thành prototype.

## 5. Hạ tầng Spring xử lý `@Resource` và các lỗi quan trọng

Annotation `@Resource` được Spring nhận diện nhờ **`CommonAnnotationBeanPostProcessor`**, khác với `AutowiredAnnotationBeanPostProcessor` xử lý chủ yếu `@Autowired` và các annotation injection có liên quan.

~~~text
Đăng ký @Bean / class target
             |
       context.refresh()
             |
       Tạo Java instance
             |
 CommonAnnotationBeanPostProcessor
       nhận diện @Resource
             |
  Resolve theo bean name / fallback type
             |
    Gán field hoặc gọi property setter
             |
          Init hooks
             |
    Bean được trả cho client
~~~

`AnnotationConfigApplicationContext` thường đăng ký sẵn hạ tầng annotation này, khi các classes Jakarta tương ứng **có mặt trên classpath**. Với XML context tự cấu hình, `<context:annotation-config/>` hoặc component scan phù hợp có thể giúp kích hoạt các bean post-processors cần thiết.

**Không quên dependency compile/runtime**: `spring-context` là Spring Core Container, còn API khai báo `jakarta.annotation.Resource` được cung cấp bởi **`jakarta.annotation:jakarta.annotation-api`**. Bài thực hành khai báo cả hai trực tiếp để không phụ thuộc tình cờ vào transitive dependencies.

Một số quy tắc quan trọng khác:

- **Required theo tên đã chỉ định:** `@Resource(name="missingChannel")` không có tùy chọn `required=false` giống `@Autowired`; thiếu bean theo tên thường làm bean creation fail.
- **Sai type:** bean mang tên được chỉ định phải **tương thích với type của field/property**. Spring không tiêm một `String` vào field `Channel` chỉ vì cùng bean name.
- **Trùng type:** nhiều Channel beans không phải lỗi nếu `@Resource(name=...)` chỉ rõ một name hợp lệ.
- **Không auto-create:** `@Resource` trên class không được Spring quản lý hoặc bean class chưa đăng ký không tự tạo ra bean definition.
- **JNDI:** `mappedName`/các cấu hình JNDI trong môi trường Jakarta EE là câu chuyện khác. Trong Spring Core Container thông thường, `name` được resolve thành **bean name**; không mặc nhiên nói `@Resource(name=...)` luôn gọi JNDI. Nếu cấu hình `SimpleJndiBeanFactory` hoặc tùy chọn JNDI đặc thù, đường đi có thể khác.
- **Không thay thế Spring `Resource` API:** `jakarta.annotation.Resource` là **annotation DI**; `org.springframework.core.io.Resource` là **interface trừu tượng nguồn dữ liệu** như classpath/file/URL. Tên “Resource” giống nhau nhưng công dụng khác.

Lỗi thường xuất hiện khi eager singleton được tạo trong `refresh()`; nếu lazy/prototype, có thể đến lúc yêu cầu bean mới xuất hiện. Đừng dùng regex trên thông điệp exception thay cho việc đọc root cause và xác minh tên/type thực tế.

## 6. Project Maven Java 17 chạy độc lập: lựa chọn name và fallback

Demo có:
- Ba `Channel` beans: `emailChannel` (**`@Primary`**), `smsChannel`, `archiveChannel` cùng alias `oldArchiveChannel`.
- **ExplicitNameClient** có `@Resource(name="smsChannel")` → chọn SMS dù EMAIL là primary.
- **DefaultFieldClient** có field tên `smsChannel` → chọn SMS theo tên field.
- **ExplicitSetterClient** có `@Resource(name="archiveChannel")` trên `setSelected` → chọn ARCHIVE.
- **DefaultSetterClient** có setter `setArchiveChannel` → chọn ARCHIVE theo tên property.
- **AliasClient** dùng tên alias → cùng instance bean archive.
- **FallbackClient** có field tên không trùng bean nào → fallback theo type, chọn `emailChannel` do `@Primary`.
- Hai tình huống lỗi riêng: tên không tồn tại và bean có tên đúng nhưng sai type.

Dự án chỉ tạo console context và in các kiểm chứng định danh. **Không có mạng, file I/O, Spring Boot hay HTTP.**

### 6.1. Cấu trúc

~~~text
resource-by-name-demo/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── demo/
                └── ResourceByNameDemo.java
~~~

Yêu cầu: **JDK 17+**, Maven 3.9+ và repository Maven Central/mirror để tải dependencies lần đầu.

### 6.2. `pom.xml`

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>resource-by-name-demo</artifactId>
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
        <dependency>
            <groupId>jakarta.annotation</groupId>
            <artifactId>jakarta.annotation-api</artifactId>
            <version>3.0.0</version>
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
                    <mainClass>demo.ResourceByNameDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

`maven.compiler.release=17` yêu cầu biên dịch với target Java 17; Maven Compiler Plugin gọi `javac` với đúng classpath. Dùng import `jakarta.annotation.Resource` với dependency 3.0.0, không dùng `javax.annotation.Resource`. Không cần tự bật annotation processing plugin của Java compiler: injection thực thi **ở runtime bởi Spring**, không phải quá trình sinh code lúc compile.

### 6.3. `src/main/java/demo/ResourceByNameDemo.java`

~~~java
package demo;

import jakarta.annotation.Resource;
import org.springframework.beans.BeansException;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Primary;

public final class ResourceByNameDemo {
    private ResourceByNameDemo() {
    }

    @FunctionalInterface
    public interface Channel {
        String label();
    }

    public static final class ExplicitNameClient {
        @Resource(name = "smsChannel")
        private Channel selected;

        public String selected() {
            return selected.label();
        }

        public boolean same(Channel expected) {
            return selected == expected;
        }
    }

    public static final class DefaultFieldClient {
        @Resource
        private Channel smsChannel;

        public String selected() {
            return smsChannel.label();
        }
    }

    public static final class ExplicitSetterClient {
        private Channel selected;
        private int calls;

        @Resource(name = "archiveChannel")
        public void setSelected(Channel selected) {
            this.selected = selected;
            calls++;
        }

        public String selected() {
            return selected.label();
        }

        public int calls() {
            return calls;
        }
    }

    public static final class DefaultSetterClient {
        private Channel selected;

        @Resource
        public void setArchiveChannel(Channel value) {
            selected = value;
        }

        public String selected() {
            return selected.label();
        }
    }

    public static final class AliasClient {
        @Resource(name = "oldArchiveChannel")
        private Channel selected;

        public boolean same(Channel expected) {
            return selected == expected;
        }
    }

    public static final class FallbackClient {
        @Resource
        private Channel noSuchDefaultName;

        public String selected() {
            return noSuchDefaultName.label();
        }

        public boolean same(Channel expected) {
            return noSuchDefaultName == expected;
        }
    }

    public static final class MissingNameClient {
        @Resource(name = "missingChannel")
        private Channel selected;
    }

    public static final class WrongTypeClient {
        @Resource(name = "labelBean")
        private Channel selected;
    }

    @Configuration(proxyBeanMethods = false)
    public static class AppConfig {
        @Bean("emailChannel")
        @Primary
        public Channel emailChannel() {
            return () -> "EMAIL";
        }

        @Bean("smsChannel")
        public Channel smsChannel() {
            return () -> "SMS";
        }

        @Bean(name = {"archiveChannel", "oldArchiveChannel"})
        public Channel archiveChannel() {
            return () -> "ARCHIVE";
        }

        @Bean("labelBean")
        public String labelBean() {
            return "NOT_A_CHANNEL";
        }
    }

    public static void main(String[] args) {
        // 1) Context hợp lệ: ba beans cùng Channel type.
        try (var context = new AnnotationConfigApplicationContext()) {
            context.register(AppConfig.class);
            context.registerBean(ExplicitNameClient.class);
            context.registerBean(DefaultFieldClient.class);
            context.registerBean(ExplicitSetterClient.class);
            context.registerBean(DefaultSetterClient.class);
            context.registerBean(AliasClient.class);
            context.registerBean(FallbackClient.class);
            context.refresh();

            Channel sms = context.getBean("smsChannel", Channel.class);
            Channel archive =
                    context.getBean("archiveChannel", Channel.class);
            Channel email = context.getBean("emailChannel", Channel.class);

            ExplicitNameClient explicit =
                    context.getBean(ExplicitNameClient.class);
            ExplicitSetterClient setter =
                    context.getBean(ExplicitSetterClient.class);
            FallbackClient fallback =
                    context.getBean(FallbackClient.class);

            System.out.println("explicit.name=" + explicit.selected());
            System.out.println("explicit.sameSms=" + explicit.same(sms));
            System.out.println("default.field="
                    + context.getBean(DefaultFieldClient.class).selected());
            System.out.println("setter.explicit=" + setter.selected());
            System.out.println("setter.calls=" + setter.calls());
            System.out.println("setter.default="
                    + context.getBean(DefaultSetterClient.class).selected());
            System.out.println("alias.sameArchive="
                    + context.getBean(AliasClient.class).same(archive));
            System.out.println("alias.hasDefinition="
                    + context.containsBeanDefinition("oldArchiveChannel"));
            System.out.println("fallback.primary=" + fallback.selected());
            System.out.println("fallback.sameEmail=" + fallback.same(email));
            System.out.println("context.beanByType="
                    + context.getBean(Channel.class).label());
        }

        // 2) Có bean Channel, nhưng không có tên explicit cần tìm.
        try (var missing = new AnnotationConfigApplicationContext()) {
            missing.register(AppConfig.class);
            missing.registerBean(MissingNameClient.class);
            missing.refresh();
        } catch (BeansException expected) {
            System.out.println("missingExplicit.failed=true");
        }

        // 3) Có bean tên labelBean, nhưng đó là String, không phải Channel.
        try (var wrong = new AnnotationConfigApplicationContext()) {
            wrong.register(AppConfig.class);
            wrong.registerBean(WrongTypeClient.class);
            wrong.refresh();
        } catch (BeansException expected) {
            System.out.println("wrongType.failed=true");
        }
    }
}
~~~

### 6.4. Tại sao demo này kiểm tra đúng by-name?

1. Spring thấy cả `emailChannel` và `smsChannel` cùng là Channel, nhưng `@Resource(name="smsChannel")` chọn **SMS** rõ ràng. `@Primary` của email không thay đổi tên được yêu cầu.
2. `DefaultFieldClient.smsChannel` không khai `name`, nên tên mặc định từ **field** khớp `smsChannel`. Dù email primary, **bean name match** được sử dụng trước.
3. `setSelected(...)` có annotation tên `archiveChannel`, nên tên Java setter **không quyết định** bean name.
4. `setArchiveChannel(...)` không khai `name`, nên tên JavaBeans property **`archiveChannel`** khớp bean.
5. `oldArchiveChannel` là **alias** cho bean `archiveChannel`. Spring nhận alias khi lookup; phép `==` xác nhận cùng object singleton.
6. `noSuchDefaultName` không có bean cùng tên. Chỉ lúc này lookup mới fallback theo **type**; `emailChannel` được `@Primary`, nên chọn EMAIL.
7. Trong `MissingNameClient`, **explicit name không tồn tại** dù có ba beans cùng type. Spring không bỏ `name` để tùy ý chọn bean khác.
8. Trong `WrongTypeClient`, bean `labelBean` tồn tại nhưng là String; không thể gán vào field Channel. `@Resource` không bắt một Java field nhận một type sai.
9. `@Bean` và `registerBean` tạo nguồn metadata cho context; các lớp Client không bắt buộc có `@Component` nếu đã được **đăng ký tường minh**. Spring xử lý `@Resource` trên những instance do container tạo.

**Đây là console demo chủ đích:** hai context lỗi có thể phát thông báo khởi động thất bại từ logger. Expected stdout chỉ tính các lệnh `System.out.println` trong `main`, không áp đặt exact stack trace của Spring.

## 7. Lệnh chạy và expected stdout

Mở terminal ở thư mục `resource-by-name-demo`, kiểm tra:

~~~bash
java -version
javac -version
mvn -version
~~~

Phiên bản Java/Maven hiển thị tùy môi trường. Từ thư mục có `pom.xml`, chạy:

~~~bash
mvn -q clean compile exec:java
~~~

**13 dòng stdout do chính chương trình Java in**, không tính Maven/logging backend:

~~~text
explicit.name=SMS
explicit.sameSms=true
default.field=SMS
setter.explicit=ARCHIVE
setter.calls=1
setter.default=ARCHIVE
alias.sameArchive=true
alias.hasDefinition=false
fallback.primary=EMAIL
fallback.sameEmail=true
context.beanByType=EMAIL
missingExplicit.failed=true
wrongType.failed=true
~~~

Các giá trị này là deterministic: không phụ thuộc timezone, random, network, `hashCode()` hay tên nội bộ của Spring. Trong phép so `==`, chỉ kiểm tra **reference identity** của những singleton lấy từ **cùng context**; `String.equals` sẽ dùng khi so giá trị nội dung.

Lưu ý `context.getBean(Channel.class)` chọn primary vì có nhiều candidates cùng type. Nếu bỏ `@Primary` và không có qualifier/other discriminator, chính lookup theo type có thể mơ hồ, trong khi `@Resource(name="smsChannel")` vẫn có thể tìm được SMS bằng tên.

## 8. Java 17 thuần: phân biệt tra theo tên với tra theo type

Để thấy ý nghĩa by-name mà không nhầm với annotation runtime, tạo tệp độc lập **`ManualNameSelection.java`**, chạy bằng `javac`/`java` (không cần Spring/Jakarta):

~~~java
import java.util.Map;

public class ManualNameSelection {
    interface Channel {
        String label();
    }

    public static void main(String[] args) {
        Map<String, Channel> beans = Map.of(
                "emailChannel", () -> "EMAIL",
                "smsChannel", () -> "SMS");

        Channel chosen = beans.get("smsChannel");
        System.out.println("selected=" + chosen.label());
        System.out.println("missingName="
                + (beans.get("unknownChannel") == null));
        System.out.println("otherAvailable="
                + beans.containsKey("emailChannel"));
    }
}
~~~

Chạy từ thư mục chứa file:

~~~bash
javac ManualNameSelection.java
java ManualNameSelection
~~~

Stdout:

~~~text
selected=SMS
missingName=true
otherAvailable=true
~~~

Map Java ở đây **không phải Spring BeanFactory**; nó chỉ giúp hình dung rằng tra tên `smsChannel` khác tra tên `emailChannel`, và một tên không tồn tại không có nghĩa không có objects khác. Spring bổ sung type checking, bean definitions, scope, lifecycle, alias và optional fallback với **trường hợp không khai tên tường minh**.

**Không suy từ map Java rằng Spring luôn phải có `@Primary`**. Đối với explicit name, dù có nhiều implementations cùng type, một name match hợp lệ đủ để xác định bean cần tiêm (với điều kiện type tương thích).

## 9. Các trường hợp nâng cao và giới hạn cần nhớ

### `@Resource` không phải một annotation optional tổng quát

Annotation `jakarta.annotation.Resource` **không có** thuộc tính `required=false` như Spring `@Autowired`. Nếu một dependency thật sự optional theo nghiệp vụ, xem xét `Optional<T>`/provider hoặc cách thiết kế default strategy tương thích với Spring; không giả định một `@Resource(name="...")` sai tên sẽ im lặng.

Một Spring bean có nhiều `@Resource` fields vẫn phụ thuộc vào những resources ấy theo từng injection point. Nếu một required resource không resolve được, bean creation có thể fail ngay cả khi các fields khác đã được inject trước đó.

### Fallback có thể được cấu hình

`CommonAnnotationBeanPostProcessor` có setting `setFallbackToDefaultTypeMatch(boolean)`, mặc định `true`. Trong cấu hình custom đặt `false`, `@Resource` **không tên tường minh** cũng phải tìm theo tên mặc định; không còn fallback theo type khi thiếu default name. Đừng xây business behavior dựa trên một custom setting mà chưa kiểm tra.

### Tham chiếu những hạ tầng được Spring tự cung cấp

Tài liệu Spring ghi nhận khi `@Resource` không có `name`, fallback theo type còn có thể resolve một số dependency well-known như `ApplicationContext`, `BeanFactory`, `ResourceLoader` hoặc `ApplicationEventPublisher`. Điều này không có nghĩa bạn đã đăng ký thêm một bean definition dưới mọi tên field tùy ý.

### Trùng tên bean không phải cùng việc với alias

Đăng ký hai bean definitions cùng tên có thể gây lỗi overriding hoặc phụ thuộc vào chính sách override. Ngược lại alias như `oldArchiveChannel` trỏ tới **một definition** duy nhất. Khi debug, `containsBean("oldArchiveChannel")` có thể trả `true` nhưng `containsBeanDefinition("oldArchiveChannel")` là `false`.

### `lookup`, `mappedName`, JNDI

`@Resource` còn có những attributes phục vụ môi trường Jakarta/JNDI tùy cách cấu hình. Chúng **không** phải lý do thay `@Resource(name=...)` thành một JNDI lookup trong Spring application thông thường. Hãy đối chiếu tài liệu Spring và annotation API nếu ứng dụng chạy trên Jakarta EE server.

### Độ ổn định của bean name là hợp đồng cấu hình

Nếu một service được viết `@Resource(name="smsChannel")`, việc rename bean này có thể làm ứng dụng không khởi động. Khi cần đổi tên để refactor, dùng alias có kiểm soát trong thời gian chuyển đổi hoặc cập nhật injection points và tests đồng bộ. Không thêm nhiều aliases tùy tiện để giải quyết mơ hồ do thiết kế.

## 10. Lỗi phổ biến và hướng chẩn đoán

| Triệu chứng | Nguyên nhân khả dĩ | Kiểm tra/cách sửa |
| --- | --- | --- |
| `package jakarta.annotation does not exist` | Thiếu Jakarta Annotations API trên compile classpath | Thêm dependency `jakarta.annotation:jakarta.annotation-api` và sync Maven |
| `@Resource` field vẫn null khi object được `new` | Object ngoài Spring IoC Container | Lấy Spring bean hoặc truyền dependency qua constructor trong unit test |
| Bean tồn tại nhưng `@Resource(name="...")` báo không tìm thấy | Tên explicit không trùng bean name hoặc alias thực | Kiểm `@Bean(name=...)`, tên scan, alias, context hiện hành |
| Có bean name đúng nhưng injection fail type | Type field/setter không tương thích với bean thực | Sửa bean name hoặc khai báo type; không ép cast sai |
| `@Resource` trùng tên một `String`, field cần Channel | Name match nhưng wrong type | Sửa tên field/name hoặc definition tương ứng |
| `@Resource` không tên chọn primary ngoài ý muốn | Default field/property name không có bean → fallback type | Đặt `name` tường minh hoặc sửa tên field cho rõ |
| Không thể chọn bean vì nhiều candidates fallback | Không có primary/selection rule phù hợp | Đặt tên explicit cho `@Resource`, hoặc cấu hình type resolution |
| `@Primary` không thắng `@Resource(name=...)` | Explicit by-name có ưu tiên; đây là hành vi đúng | Đừng dựa vào primary để thay tên đã chỉ định |
| Setter method không được gọi | Không phải Spring-managed bean, processor thiếu hoặc method không phải property setter phù hợp | Kiểm registration, annotation, chữ ký JavaBean setter |
| `@Resource` trên constructor/method nhiều tham số không hoạt động | Vị trí annotation không được hỗ trợ cho DI kiểu đó | Dùng `@Autowired`/constructor/factory-method injection |
| Có `javax.annotation.Resource` trên Spring 7 nhưng không hoạt động | Package cũ, không phải `jakarta.annotation.Resource` được hỗ trợ | Dùng Jakarta import/dependency đúng version |
| Log lỗi startup xuất hiện dù catch exception | Spring logger có thể ghi sự cố khi refresh fail | So từng dòng stdout do application in, xem root cause thực tế |
| XML context không xử lý `@Resource` | Annotation processor chưa được đăng ký | Dùng `<context:annotation-config/>` hoặc cấu hình thích hợp |
| `@Resource` nhầm với file resource | Cùng chữ “Resource” nhưng khác API | So `jakarta.annotation.Resource` và `org.springframework.core.io.Resource` |
| Bean cùng interface nhưng `@Autowired` chọn sai | Type/qualifier candidate resolution khác by-name | Dùng qualifier/primary đúng contract hoặc explicit `@Resource` |

**Kiểm tra có thứ tự:** (1) bean đích có được Spring quản lý không; (2) Jakarta import có đúng không; (3) `CommonAnnotationBeanPostProcessor` có chạy không; (4) name explicit/default là gì; (5) bean name/alias tồn tại không; (6) type tương thích không; (7) có fallback/type ambiguity không. Phân biệt lỗi Maven/classpath với lỗi Spring bean resolution.

Không suy luận rằng trùng Java class name dẫn đến trùng bean name; class `EmailChannel` và tên đăng ký `emailChannel` có thể là hai lớp định danh khác nhau. Khi kiểm thử bằng tên, thay đổi strategy component scan hoặc đổi tên method `@Bean` cũng có thể thay hợp đồng nếu không khai báo tên tường minh.

## 11. Thực hành dự đoán và kiểm chứng

Hãy làm **từng thay đổi độc lập** trong một bản sao dự án rồi khôi phục source gốc trước khi so expected stdout mục 7:

1. **Đổi explicit name:** `@Resource(name="emailChannel")` ở ExplicitNameClient. Dự đoán `explicit.name=EMAIL`, `explicit.sameSms=false`.
2. **Bỏ `@Primary`:** để ba beans Channel cùng type. Phần by-name nào vẫn thành công, và FallbackClient/lookup theo type sẽ thay đổi ra sao?
3. **Đổi field name:** sửa `DefaultFieldClient.smsChannel` thành `selectedChannel` nhưng không thêm `name`. Dự đoán khả năng fallback primary thay vì chọn SMS.
4. **Chỉ định field name:** thêm `@Resource(name="smsChannel")` sau khi rename field. Kiểm chứng name explicit làm hành vi trở lại SMS.
5. **Rename setter:** đổi `setArchiveChannel` thành `setSmsChannel` trong DefaultSetterClient, giữ một tham số và không khai `name`. Dự đoán `setter.default=SMS`.
6. **Explicit setter:** đổi `setSelected` thành tên setter khác nhưng giữ `@Resource(name="archiveChannel")`. Bean được chọn có đổi không?
7. **Alias:** bỏ `oldArchiveChannel` khỏi danh sách `@Bean(name={...})`. Quan sát AliasClient fail bootstrap; không có bean thứ hai nào bị xóa.
8. **Sai type:** đổi kiểu field `WrongTypeClient.selected` thành `String`. Dự đoán tình huống name match `labelBean` trở nên hợp lệ.
9. **Không có bean:** thử `@Resource(name="missingChannel")` rồi thêm đúng bean name này ở configuration; quan sát context không còn báo thiếu name.
10. **Tùy biến fallback:** nghiên cứu `CommonAnnotationBeanPostProcessor.setFallbackToDefaultTypeMatch(false)`, dự đoán ảnh hưởng tới FallbackClient nhưng không ảnh hưởng name explicit.
11. **Kiểm tra identity:** in `context.getBean("oldArchiveChannel")==context.getBean("archiveChannel")`; với singleton mặc định sẽ `true`.
12. **Constructor injection:** viết class có constructor nhận Channel và được tạo bằng `@Bean` method; dùng `@Qualifier` ở factory-method argument thay vì đặt `@Resource` trên constructor.
13. **Unit test Java thuần:** truyền `Channel` fake vào constructor class nghiệp vụ. So sánh khả năng test với field-injected class đòi context/reflection.
14. **Nhiều contexts:** tạo hai contexts từ AppConfig, so instances `smsChannel`; Spring singleton mặc định theo mỗi bean definition/context, không phải global JVM singleton.

### Checklist

- [ ] Import đúng **`jakarta.annotation.Resource`**, không phải `javax.annotation.Resource`.
- [ ] Biết `@Resource(name="x")` tìm **bean name/alias x** và kiểm tra type.
- [ ] Biết tên mặc định đến từ **field name** hoặc **JavaBean setter property name**.
- [ ] Biết fallback theo type **chỉ dành cho trường hợp không khai name tường minh**, khi default name không có và cấu hình cho phép.
- [ ] Hiểu tác động `@Primary` trong fallback, không nhầm với explicit by-name.
- [ ] Dùng `@Resource` đúng vị trí field/property setter, không tự áp dụng như `@Autowired` trên constructor/multi-param method.
- [ ] Phân biệt alias với bean definition mới.
- [ ] Biết khi thiếu name hoặc sai type, bean creation có thể thất bại.
- [ ] Chạy được Maven demo Java 17 ra chính xác 13 dòng stdout, và Java thuần `javac`/`java` ra 3 dòng.
- [ ] Biết vai trò `CommonAnnotationBeanPostProcessor` và dependency `jakarta.annotation-api`.

## 12. Tóm tắt và tài liệu chính thức

`@Resource` thể hiện **một tham chiếu bean theo tên** trong Spring Core Container:

- **Có `name`:** resolve bean theo tên đó/alias; không tùy ý chuyển sang bean cùng type khác khi name không tồn tại.
- **Không có `name`:** dùng tên field hoặc tên JavaBean property của setter. Nếu bean name ấy không có, Spring có thể fallback sang type matching theo chính sách processor mặc định.
- **Kiểu dữ liệu luôn quan trọng:** name match không làm biến mất quy tắc type-safety của Java.
- **`@Primary` và `@Qualifier` không thay thế định nghĩa name của `@Resource`**; chúng chủ yếu thuộc việc chọn dependency theo type/qualifier.
- Bean phải thuộc Spring context và annotation processor phải có mặt. Tự tạo object bằng `new` không thực hiện injection.

Tài liệu:
- [Spring Framework — Injection with @Resource](https://docs.spring.io/spring-framework/reference/core/beans/annotation-config/resource.html)
- [Spring Framework — Annotation-based Container Configuration](https://docs.spring.io/spring-framework/reference/core/beans/annotation-config.html)
- [Spring Framework — Fine-tuning Autowiring with Qualifiers](https://docs.spring.io/spring-framework/reference/core/beans/annotation-config/autowired-qualifiers.html)
- [Spring Framework — Bean Definition Naming and Aliasing](https://docs.spring.io/spring-framework/reference/core/beans/definition.html)
- [Spring API — CommonAnnotationBeanPostProcessor](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/context/annotation/CommonAnnotationBeanPostProcessor.html)
- [Jakarta Annotations API — `Resource`](https://jakarta.ee/specifications/annotations/3.0/apidocs/jakarta.annotation/jakarta/annotation/resource)
- [Maven Central — Jakarta Annotations API 3.0.0](https://central.sonatype.com/artifact/jakarta.annotation/jakarta.annotation-api/3.0.0)

**Kết luận thực hành:** Khi `@Resource` chọn một bean gây bất ngờ, đừng vội đổi `@Primary`. Trước hết xác định **name tường minh hay mặc định**, xem bean/alias có tồn tại không, kiểm tra **type**, rồi mới xét **fallback theo type**. Phân biệt thứ tự ấy giúp bạn dùng `@Resource` nhất quán, dễ kiểm thử và tránh lỗi wiring trong ứng dụng Spring.