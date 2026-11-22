# Ưu tiên một ứng viên bằng `@Primary` trong Spring Core Container

## 1. Vấn đề: nhiều beans cùng type nhưng chỉ cần một dependency

Spring IoC Container cho phép có **nhiều bean definitions cùng tương thích một Java type**. Ví dụ `FastTransport`, `SafeTransport` và `BackupTransport` cùng implement interface `Transport`. Một service có constructor chỉ nhận `Transport` cần **một reference duy nhất**, trong khi cả ba đều có thể gán vào tham số ấy.

Nếu không có quy tắc phân giải phù hợp, việc inject một dependency duy nhất theo type có thể thất bại vì **không xác định được bean nào được chọn** (`NoUniqueBeanDefinitionException`, đôi khi được bọc trong `UnsatisfiedDependencyException`).

`@Primary`, thuộc package `org.springframework.context.annotation`, đánh dấu **một bean được ưu tiên** giữa những autowire candidates cùng đáp ứng một injection point. Khi sau khi lọc có **đúng một primary bean hợp lệ**, Spring dùng bean đó cho single-valued dependency.

~~~java
// Snippet minh họa trong một @Configuration class:
@Bean("fastTransport")
@Primary
Transport fastTransport() {
    return new FastTransport();
}

@Bean("safeTransport")
Transport safeTransport() {
    return new SafeTransport();
}
~~~

Trong tình huống thông thường, injection point nhận `Transport` sẽ lấy bean `fastTransport`, miễn cả hai beans được đăng ký và không có điều kiện lọc khác khiến primary không còn phù hợp.

**Những điều `@Primary` không làm:** không tạo bean, không đổi Java type, không đổi bean name, không thay scope, không đảm bảo thread safety, không xóa các bean khác, không làm cho mọi điểm inject đều nhận primary và cũng không thay thế một qualifier chỉ định rõ bean khác.

Mục tiêu học là hiểu **khi nào Spring cần primary, primary tham gia quá trình chọn ứng viên ra sao, giới hạn của nó và các trường hợp đối chứng**. Bài sử dụng Java 17+, Spring Framework 7.0.9 và Maven, có code hoàn chỉnh, lệnh chạy và expected stdout.

## 2. Nơi khai báo `@Primary` và phạm vi tác dụng

### Trên phương thức `@Bean`

~~~java
@Configuration(proxyBeanMethods = false)
class AppConfig {
    @Bean
    @Primary
    Transport fastTransport() {
        return new FastTransport();
    }
}
~~~

Khi dùng **Java configuration** với `@Bean`, hãy đặt `@Primary` trên **factory method đăng ký bean** muốn ưu tiên. Metadata primary thuộc **bean definition**, không phải một trạng thái mà JVM tự gắn vào mọi instance của cùng class.

### Trên component được quét

~~~java
@Component
@Primary
class FastTransport implements Transport {
    @Override
    public String id() {
        return "FAST";
    }
}
~~~

Class phải nằm trong phạm vi **component scan** hoặc được đăng ký theo một cơ chế Spring hỗ trợ. Chỉ có class `@Component @Primary` trên classpath không có nghĩa mọi context đều chứa bean ấy.

### Cấu hình XML tương đương

~~~xml
<bean id="fastTransport" class="demo.FastTransport" primary="true"/>
<bean id="safeTransport" class="demo.SafeTransport"/>
~~~

XML này là **snippet minh họa**, không phải file được dùng trong project Maven ở mục 7; trong project đó, classes được khai báo bên trong một source Java khác nên tên `demo.FastTransport` chỉ là ví dụ cho class public độc lập tương ứng. Thuộc tính XML `primary="true"` diễn đạt ý tưởng ưu tiên của cùng Spring bean-definition metadata.

**Lưu ý quan trọng về nơi đặt annotation:** Nếu một Java class mang `@Primary` nhưng bean ấy được đăng ký bằng một `@Bean` method cụ thể, đừng giả định class-level annotation luôn là metadata được Spring dùng cho definition từ method. Khai `@Primary` tại **`@Bean` method** để hợp đồng rõ ràng.

**Scope ưu tiên:** primary áp dụng với những bean definitions có thể được xét làm **candidate của một dependency đang được resolve**, không phải “bean ưu tiên toàn cục” có thể ghi đè mọi yêu cầu. Một interface khác hoặc qualifier khác có thể tạo tập candidate khác.

## 3. Quy trình Spring chọn một candidate

Khi Spring cần cấp `Transport` cho constructor/method/field, quy trình khái niệm gồm:

~~~text
Injection point yêu cầu Transport
                |
                v
   Tìm bean có type tương thích
                |
                v
  Lọc autowire candidates và metadata
     (qualifier, generic, điều kiện khác)
                |
                v
    Một candidate hay nhiều candidates?
          /                 \
      Một hợp lệ          Nhiều hợp lệ
          |                    |
          v                    v
       Chọn nó       Có đúng một @Primary?
                            /        \
                          Có         Không
                           |           |
                           v           v
                      Chọn primary   Xét luật
                                    ưu tiên khác
                                    hoặc báo mơ hồ
~~~

Đây là **sơ đồ học cơ chế**, không phải thứ tự đầy đủ từng nhánh của `DefaultListableBeanFactory`. Spring còn cân nhắc `@Fallback`, default-candidate, name matching, self references, priority và các quy tắc đặc biệt theo injection point.

Kết luận thực dụng:
- **Một candidate duy nhất:** dependency được cấp mà **không cần** `@Primary`.
- **Nhiều candidates, một primary:** primary có thể phân giải yêu cầu một bean.
- **Nhiều candidates, không primary:** có thể còn cách phân giải khác; nếu không, lỗi không duy nhất.
- **Nhiều candidates, từ hai primary trở lên:** primary không còn chọn được **một** bean; vẫn có thể báo mơ hồ.
- **Primary không khớp type/qualifier:** nó không được đưa vào tập ứng viên cuối cùng; không thể tự thắng.
- **Không có candidate:** `@Primary` trên một type khác không giải quyết được vấn đề thiếu bean.

Một primary bean thường được **pre-instantiate** khi là eager singleton trong application context, nhưng `@Primary` **không tự quyết định lúc nào bean được tạo**. Scope/lazy/factory rules vẫn có hiệu lực như bình thường.

## 4. Khác biệt quan trọng: injection một bean và injection nhiều beans

`@Primary` chủ yếu ảnh hưởng tới **single-valued dependency**, ví dụ:

~~~java
@Autowired
private Transport defaultTransport;
~~~

Hoặc constructor:

~~~java
// Snippet Java 17: constructor injection.
final class Dispatcher {
    private final Transport transport;

    Dispatcher(Transport transport) {
        this.transport = transport;
    }
}
~~~

Ngược lại, Spring có thể inject **tất cả các ứng viên phù hợp** vào:

~~~java
@Autowired
private List<Transport> transports;

@Autowired
private Map<String, Transport> transportByName;
~~~

Với ba beans được phép autowire:
- Một `Transport` không chỉ định cụ thể thường nhận **primary**.
- Một `List<Transport>` có thể chứa **cả ba** (kể cả primary và fallback phù hợp).
- Một `Map<String,Transport>` có thể chứa cả ba; **keys là bean names**, không phải Java class names.
- `@Primary` **không** loại `safeTransport` hay `backupTransport` khỏi collection/map.
- `@Order` hoặc `Ordered` (khi có) tác động tới **thứ tự danh sách**, không biến một bean thành primary.

Vì vậy không được dùng số lượng `List<Transport>` để kết luận primary “không hoạt động”. Primary là tín hiệu khi container cần **chọn đúng một reference** từ nhiều candidates; collections có hợp đồng khác.

Trong ví dụ hoàn chỉnh, kết quả danh sách được **sort** trước khi in để không phụ thuộc vào thứ tự bean registration hoặc order metadata. Đây là cách kiểm chứng nội dung thay vì áp đặt thứ tự không được đảm bảo cho mọi cấu hình.

## 5. `@Qualifier` có thể chọn một bean khác với primary

Giả sử:
- `fastTransport` được đánh dấu `@Primary`;
- `safeTransport` cũng có type `Transport`, nhưng **không** primary;
- một điểm inject có `@Qualifier("safeTransport")`.

~~~java
// Snippet trong @Bean factory method:
@Bean
Dispatcher safeDispatcher(
        @Qualifier("safeTransport") Transport transport) {
    return new Dispatcher(transport);
}
~~~

Ở đây, qualifier giới hạn **tập ứng viên** theo metadata/name phù hợp với type được yêu cầu. Chỉ `safeTransport` có thể thỏa điều kiện, nên Spring chọn nó **dù `fastTransport` là primary**.

**Không nói “primary luôn đè qualifier”.** Nếu primary bean không thỏa qualifier, nó không phải ứng viên hợp lệ của injection point đó. Quy tắc type/qualifier phải được xét trước khi kết luận ai được chọn.

So sánh:

| Injection point | Các candidates phù hợp | Kết quả thông thường |
| --- | --- | --- |
| `Transport t` không qualifier | FAST, SAFE, BACKUP | FAST khi FAST là primary |
| `@Qualifier("safeTransport") Transport t` | SAFE | SAFE |
| `@Qualifier("missingTransport") Transport t` | Không có bean phù hợp | Lỗi required dependency |
| `SmsTransport t` | Chỉ beans kiểu SmsTransport | Không chọn FAST nếu FAST không assignable |
| `List<Transport> list` | Các Transport hợp lệ | Nhiều beans, không chỉ FAST |

`@Qualifier` về bản chất là **bộ lọc trong tập type matches**, không phải câu lệnh tùy tiện lấy một bean khác type. Với yêu cầu **đúng bean name** ở field/setter, `jakarta.annotation.Resource(name="...")` là cơ chế by-name khác, nhưng không cần nó để giải thích `@Primary`.

**Đừng dựa vào tên tham số thay cho qualifier minh bạch** khi code có nhiều implementations. Spring có thể xét tên field/parameter cùng nhiều tiêu chí khác; việc đổi tên field hoặc thay compiler metadata có thể đổi behavior không mong muốn.

## 6. `@Fallback` là một chiến lược khác, không phải `@Primary` đảo ngược

Spring Framework 6.2+ có `@Fallback`:

~~~java
@Bean
Transport fastTransport() {
    return new FastTransport();
}

@Bean
@Fallback
Transport backupTransport() {
    return new BackupTransport();
}
~~~

Khi có **một bean thường** (không fallback) và những beans còn lại đều là fallback, bean thường ấy có thể được chọn như lựa chọn mặc định cho dependency đơn. Trong ví dụ chỉ có FAST thường và BACKUP fallback, yêu cầu một `Transport` chọn **FAST dù không có `@Primary`**.

So sánh ngắn:

| Khái niệm | Ý nghĩa |
| --- | --- |
| `@Primary` | Ưu tiên bean được đánh dấu khi có nhiều qualified candidates cho **một dependency** |
| `@Fallback` | Đánh dấu bean là dự phòng, có thể ưu tiên những candidate thường còn lại |
| `@Qualifier` | Lọc candidates theo điều kiện của injection point |
| `@Bean(autowireCandidate=false)` | Loại bean khỏi cơ chế autowiring thông thường |
| `@Order` | Sắp thứ tự khi thu thập nhiều beans theo một số quy tắc |
| `@Lazy` | Liên quan thời điểm khởi tạo; không phải thứ tự chọn candidate |
| `@Scope` | Quy định phạm vi instance; không tự chọn bean thay thế |

Một bean fallback **vẫn là bean thật** và có thể được lookup bằng tên. `@Fallback` không nhất thiết khiến bean không có mặt trong `List<Transport>`. Theo cơ chế Spring, các type-matching beans vẫn có thể tham gia collection/map injection tùy autowire eligibility.

Đặt đồng thời primary, fallback, qualifiers và default-candidate flags trên nhiều beans có thể khó đọc: cần kiểm tra tập **candidate thực tế ở từng injection point**, chứ không suy diễn từ một annotation đơn lẻ. Trong dự án, cố ý dùng cấu hình đơn giản để chứng minh từng khác biệt.

## 7. Demo Spring Framework 7.0.9 + Maven + Java 17

Demo tạo năm tình huống độc lập:

1. **PrimaryConfig:** ba beans cùng type, FAST là `@Primary`, BACKUP là `@Fallback`. Một dependency đơn chọn FAST, `@Qualifier("safeTransport")` chọn SAFE, collection/map chứa cả ba.
2. **NoPrimaryConfig:** FAST và SAFE đều bình thường; lookup đơn theo type không có tiêu chí phân giải → lỗi **không duy nhất**.
3. **TwoPrimaryConfig:** FAST và SAFE **đều `@Primary`** → không thể chọn một primary duy nhất.
4. **FallbackOnlyConfig:** FAST bình thường và SAFE `@Fallback`, không có primary → FAST vẫn được chọn.
5. **OnlyOneConfig:** duy nhất FAST → Spring chọn FAST dù bean không cần `@Primary`.

Mỗi tình huống dùng một `AnnotationConfigApplicationContext` **riêng**, tránh accidental bean registrations từ cấu hình trước. Tình huống thất bại được catch có chủ đích; không khóa expected stdout vào thông điệp exception/stack trace của Spring.

### 7.1. Cấu trúc project

~~~text
primary-selection-demo/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── demo/
                └── PrimarySelectionDemo.java
~~~

Yêu cầu **JDK 17+**, **Maven 3.9+**, và quyền tải Spring dependencies từ Maven Central/mirror ở lần chạy đầu. Đây là **Spring Framework thuần**, không cần Spring Boot, servlet hay cơ sở dữ liệu.

### 7.2. `pom.xml`

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>primary-selection-demo</artifactId>
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
                    <mainClass>demo.PrimarySelectionDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Maven compiler plugin chạy `javac` theo target Java 17; Exec Maven Plugin đưa Spring dependencies lên runtime classpath. `spring-context` kéo theo các Spring modules cần thiết qua Maven dependency resolution; không tự thêm từng JAR vào CLI.

### 7.3. Tệp `src/main/java/demo/PrimarySelectionDemo.java`

~~~java
package demo;

import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;

import org.springframework.beans.factory.NoUniqueBeanDefinitionException;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Fallback;
import org.springframework.context.annotation.Primary;

public final class PrimarySelectionDemo {
    private PrimarySelectionDemo() {
    }

    @FunctionalInterface
    interface Transport {
        String id();
    }

    static final class FastTransport implements Transport {
        @Override
        public String id() {
            return "FAST";
        }
    }

    static final class SafeTransport implements Transport {
        @Override
        public String id() {
            return "SAFE";
        }
    }

    static final class BackupTransport implements Transport {
        @Override
        public String id() {
            return "BACKUP";
        }
    }

    static final class Dashboard {
        private final Transport selected;
        private final Transport qualified;
        private final List<Transport> all;
        private final Map<String, Transport> byName;

        Dashboard(Transport selected, Transport qualified,
                List<Transport> all, Map<String, Transport> byName) {
            this.selected = selected;
            this.qualified = qualified;
            this.all = all;
            this.byName = byName;
        }

        String selectedId() {
            return selected.id();
        }

        String qualifiedId() {
            return qualified.id();
        }

        boolean sameAs(Transport expected) {
            return selected == expected;
        }

        boolean qualifiedSameAs(Transport expected) {
            return qualified == expected;
        }

        String allIds() {
            return all.stream().map(Transport::id)
                    .sorted().collect(Collectors.joining(","));
        }

        String beanNames() {
            return byName.keySet().stream()
                    .sorted().collect(Collectors.joining(","));
        }

        boolean hasBackup() {
            return byName.containsKey("backupTransport");
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class PrimaryConfig {
        @Bean("fastTransport")
        @Primary
        public Transport fastTransport() {
            return new FastTransport();
        }

        @Bean("safeTransport")
        public Transport safeTransport() {
            return new SafeTransport();
        }

        @Bean("backupTransport")
        @Fallback
        public Transport backupTransport() {
            return new BackupTransport();
        }

        @Bean
        public Dashboard dashboard(Transport transport,
                @Qualifier("safeTransport") Transport safeTransport,
                List<Transport> transports,
                Map<String, Transport> transportByName) {
            return new Dashboard(transport, safeTransport,
                    transports, transportByName);
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class NoPrimaryConfig {
        @Bean
        public Transport fastTransport() {
            return new FastTransport();
        }

        @Bean
        public Transport safeTransport() {
            return new SafeTransport();
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class TwoPrimaryConfig {
        @Bean
        @Primary
        public Transport fastTransport() {
            return new FastTransport();
        }

        @Bean
        @Primary
        public Transport safeTransport() {
            return new SafeTransport();
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class FallbackOnlyConfig {
        @Bean
        public Transport fastTransport() {
            return new FastTransport();
        }

        @Bean
        @Fallback
        public Transport safeTransport() {
            return new SafeTransport();
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class OnlyOneConfig {
        @Bean
        public Transport fastTransport() {
            return new FastTransport();
        }
    }

    public static void main(String[] args) {
        try (var context =
                new AnnotationConfigApplicationContext(PrimaryConfig.class)) {
            Dashboard dashboard = context.getBean(Dashboard.class);
            Transport fast = context.getBean("fastTransport", Transport.class);
            Transport safe = context.getBean("safeTransport", Transport.class);

            System.out.println("main.selected=" + dashboard.selectedId());
            System.out.println("main.qualified=" + dashboard.qualifiedId());
            System.out.println("main.samePrimary="
                    + dashboard.sameAs(fast));
            System.out.println("main.sameQualified="
                    + dashboard.qualifiedSameAs(safe));
            System.out.println("main.allIds=" + dashboard.allIds());
            System.out.println("main.mapNames=" + dashboard.beanNames());
            System.out.println("main.mapHasFallback="
                    + dashboard.hasBackup());
            System.out.println("main.byType="
                    + context.getBean(Transport.class).id());
            System.out.println("main.fast.primary="
                    + context.getBeanFactory()
                            .getBeanDefinition("fastTransport").isPrimary());
            System.out.println("main.safe.primary="
                    + context.getBeanFactory()
                            .getBeanDefinition("safeTransport").isPrimary());
            System.out.println("main.backup.fallback="
                    + context.getBeanFactory()
                            .getBeanDefinition("backupTransport").isFallback());
            System.out.println("main.backup.byName="
                    + context.getBean("backupTransport", Transport.class).id());
        }

        try (var context =
                new AnnotationConfigApplicationContext(NoPrimaryConfig.class)) {
            context.getBean(Transport.class);
            System.out.println("noPrimary.unexpected");
        } catch (NoUniqueBeanDefinitionException expected) {
            System.out.println("noPrimary.ambiguous=true");
        }

        try (var context =
                new AnnotationConfigApplicationContext(TwoPrimaryConfig.class)) {
            context.getBean(Transport.class);
            System.out.println("twoPrimary.unexpected");
        } catch (NoUniqueBeanDefinitionException expected) {
            System.out.println("twoPrimary.ambiguous=true");
        }

        try (var context =
                new AnnotationConfigApplicationContext(FallbackOnlyConfig.class)) {
            System.out.println("fallbackOnly.selected="
                    + context.getBean(Transport.class).id());
            System.out.println("fallbackOnly.backup="
                    + context.getBean("safeTransport", Transport.class).id());
        }

        try (var context =
                new AnnotationConfigApplicationContext(OnlyOneConfig.class)) {
            System.out.println("onlyOne.selected="
                    + context.getBean(Transport.class).id());
            System.out.println("onlyOne.isPrimary="
                    + context.getBeanFactory()
                            .getBeanDefinition("fastTransport").isPrimary());
        }
    }
}
~~~

### 7.4. Cách đọc code

- **PrimaryConfig:** FAST, SAFE và BACKUP đều thuộc `Transport`. FAST được đánh dấu `@Primary`, BACKUP có `@Fallback`.
- **Tham số `Transport transport` của `dashboard(...)`:** không có qualifier, Spring chọn FAST vì nó là primary hợp lệ; `selectedId()="FAST"`.
- **Tham số `@Qualifier("safeTransport") Transport safeTransport`:** chỉ SAFE thỏa qualifier nên được cấp vào `Dashboard.qualified`, không lấy FAST.
- **`List<Transport>` / `Map<String,Transport>`:** cả ba beans vẫn được đưa vào collection/map trong ví dụ; `@Primary` và `@Fallback` không xóa chúng khỏi type matches. Output sort để ổn định.
- **BeanDefinition metadata:** `isPrimary()` chỉ true cho FAST; `isFallback()` true cho BACKUP. Đây là metadata của definitions, không phải static flags trên Java class.
- **NoPrimaryConfig:** chỉ có FAST/SAFE, không qualifier và không primary; `getBean(Transport.class)` không thể chọn duy nhất một candidate.
- **TwoPrimaryConfig:** hai beans cùng primary, cũng thiếu quy tắc chọn một duy nhất. Annotation không có nghĩa “chọn bean đăng ký đầu tiên”.
- **FallbackOnlyConfig:** FAST bình thường, SAFE fallback; với đúng một candidate thường, Spring chọn FAST. Nhưng SAFE vẫn có thể được lấy theo tên.
- **OnlyOneConfig:** chỉ có FAST; `getBean(Transport.class)` hoạt động dù `isPrimary=false`. Không nên gắn `@Primary` cho mọi bean nếu chỉ có một implementation.

**Khả năng biên dịch:** file dùng Java 17, `@Configuration`, `@Bean`, `@Primary`, `@Fallback`, `@Qualifier` của Spring 7.0.9; không cần thêm JUnit/Mockito hoặc XML. `@FunctionalInterface` trên `Transport` hợp lệ vì chỉ khai một abstract method `id()` ngoài các methods từ `Object`.

## 8. Chạy CLI và đối chiếu stdout

Trong thư mục `primary-selection-demo` chứa `pom.xml`:

~~~bash
java -version
javac -version
mvn -version
mvn -q clean compile exec:java
~~~

Ba lệnh đầu kiểm tra version JDK/Maven và có output tùy máy. Lệnh cuối biên dịch bằng Maven Compiler Plugin (`--release 17`) rồi chạy `demo.PrimarySelectionDemo`.

**18 dòng stdout do chính chương trình in** (không tính log của Maven, Spring và các báo cáo/stack trace phụ thuộc môi trường):

~~~text
main.selected=FAST
main.qualified=SAFE
main.samePrimary=true
main.sameQualified=true
main.allIds=BACKUP,FAST,SAFE
main.mapNames=backupTransport,fastTransport,safeTransport
main.mapHasFallback=true
main.byType=FAST
main.fast.primary=true
main.safe.primary=false
main.backup.fallback=true
main.backup.byName=BACKUP
noPrimary.ambiguous=true
twoPrimary.ambiguous=true
fallbackOnly.selected=FAST
fallbackOnly.backup=SAFE
onlyOne.selected=FAST
onlyOne.isPrimary=false
~~~

Các kết quả trên không dựa vào ngẫu nhiên, thời gian hoặc network. `Map.keySet()` và `List` được sort trước khi in. Hai context cố tình mơ hồ có thể sinh diagnostic ngoài stdout ứng dụng; chương trình catch đúng loại `NoUniqueBeanDefinitionException` và in boolean ổn định.

**Cách diễn giải trọng tâm:**

| Output | Điều chứng minh |
| --- | --- |
| `main.selected=FAST` | FAST được chọn cho một dependency `Transport` không qualifier |
| `main.qualified=SAFE` | Qualifier chọn SAFE dù FAST là primary |
| `main.samePrimary=true` | Dependency và bean lookup theo tên FAST cùng reference singleton trong context |
| `main.allIds=BACKUP,FAST,SAFE` | Primary/fallback không loại beans khỏi injected list |
| `main.mapNames=...` | Tất cả eligible beans vẫn xuất hiện trong injected map với bean names |
| `main.fast.primary=true` | Metadata trên bean definition FAST đã nhận annotation `@Primary` |
| `noPrimary.ambiguous=true` | Hai candidates ngang hàng không tự được phân giải |
| `twoPrimary.ambiguous=true` | Đánh dấu hai primaries không tạo tiêu chí chọn một |
| `fallbackOnly.selected=FAST` | `@Fallback` có thể ưu tiên candidate thường mà không dùng primary |
| `onlyOne.isPrimary=false` | Một candidate duy nhất không cần đánh dấu primary |

Nếu bạn cố tình sửa cấu hình, output sẽ thay đổi; hãy so với source gốc trước khi đánh giá đúng/sai. Không cố định exception message vì Spring phiên bản/logging khác có thể diễn đạt lỗi khác nhau.

## 9. Ví dụ Java 17 thuần: tư duy chọn một mặc định

`@Primary` là quy tắc của Spring, nhưng có thể hiểu logic bằng Java thuần: một registry có nhiều implementations và một **tên lựa chọn mặc định**. Tạo file `ManualPrimaryChoice.java` riêng biệt (không phụ thuộc Maven/Spring):

~~~java
import java.util.Map;

public class ManualPrimaryChoice {
    interface Transport {
        String id();
    }

    public static void main(String[] args) {
        Map<String, Transport> registry = Map.of(
                "fast", () -> "FAST",
                "safe", () -> "SAFE");

        String defaultName = "fast";
        Transport selected = registry.get(defaultName);
        Transport explicitlyChosen = registry.get("safe");

        System.out.println("default=" + selected.id());
        System.out.println("explicit=" + explicitlyChosen.id());
        System.out.println("available=" + registry.size());
        System.out.println("same=" + (selected == explicitlyChosen));
    }
}
~~~

Chạy với JDK 17+ tại thư mục chứa file:

~~~bash
javac ManualPrimaryChoice.java
java ManualPrimaryChoice
~~~

Stdout:

~~~text
default=FAST
explicit=SAFE
available=2
same=false
~~~

Đây **không** phải cách Spring nội bộ lưu primary: `Map` và `defaultName` được chúng ta tạo thủ công, không có BeanFactory, type filtering hay lifecycle. Nó chỉ minh họa ý tưởng **“có nhiều lựa chọn hợp lệ, nhưng chỉ định một lựa chọn mặc định cho yêu cầu không đặc tả thêm”**.

Spring bổ sung các yếu tố khác: bean metadata, `@Qualifier`, fallback, generic type, scope, conditional registrations và exception khi không thể phân giải. Đừng tự thay Spring BeanFactory bằng một map toàn cục trong business code nếu không có lý do kiến trúc đặc biệt.

## 10. Các tình huống cần đặc biệt cẩn trọng

### 10.1. Primary chỉ có tác dụng trong tập candidates hợp lệ

Nếu bean FAST bị đặt `autowireCandidate=false` hoặc không đáp ứng qualifier/generic của injection point, annotation primary không buộc Spring inject nó. Một bean bị exclude khỏi autowiring vẫn có thể được tra theo tên trong những trường hợp thích hợp, nhưng **không còn là candidate để chọn cho injection point đó**.

Nếu bean FAST không có type tương thích `Transport`, đừng mong `@Primary` làm JVM ép kiểu một object sai interface.

### 10.2. Primary và generic type

Giả sử có các bean `Store<String>` và `Store<Integer>`, Spring có thể dùng **generic type arguments như implicit qualifier**. Một `Store<Integer>` được đánh dấu primary không nhất thiết là candidate cho injection point yêu cầu `Store<String>`. Hãy khai báo factory method return type cụ thể để Spring có metadata generic tin cậy.

### 10.3. Primary và parent/child contexts

Một hệ thống có nhiều `ApplicationContext` (cha/con). Bean visibility và local overrides có thể ảnh hưởng candidate set; primary metadata ở context cha không tự biến mọi lookup trong context con thành một quy tắc toàn JVM.

Một số type-discovery APIs như `getBeanNamesForType` còn có phạm vi local khác với các tiện ích ancestor-aware. Khi debug, hãy chỉ rõ **context nào đang resolve dependency**.

### 10.4. Primary và AOP proxy

Proxy có thể thay runtime class nhìn thấy qua `getClass()` hoặc chỉ phơi interface, tùy JDK dynamic proxy/class-based proxy. `@Primary` không sửa type assignability hoặc tạo interface thiếu. Nếu injection point yêu cầu concrete class mà proxy không tương thích, điều đó phải được giải quyết ở thiết kế type/proxy, không phải bằng cách tăng độ ưu tiên.

### 10.5. Primary trên class và đăng ký bằng XML

Javadoc của `@Primary` có giới hạn liên quan nguồn metadata. Với XML `<bean>`, nên khai rõ **`primary="true"`** trong bean definition thay vì giả định class annotation được đọc giống component scan. Với Java `@Bean`, đặt `@Primary` tại `@Bean` method.

### 10.6. Scope singleton không có nghĩa bean primary có một instance cho cả JVM

Bean singleton mặc định thuộc **bean definition trong một Spring container**. Hai contexts độc lập có thể tạo hai instances khác nhau của cùng một `@Bean @Primary`. `@Primary` quyết định ưu tiên dependency candidate, không thay đổi scope hoặc lifecycle.

### 10.7. Primary không thay thế fail-fast khi thiếu required bean

Nếu không có implementation thỏa type, `@Primary` trên một definition không được đăng ký không giúp ích. Với một required dependency, container nên fail sớm và chỉ ra thiếu bean thay vì lặng lẽ tạo `null`. Nếu optional thật sự, biểu đạt bằng `Optional<T>`, provider hoặc default strategy theo hợp đồng; đừng dùng annotation primary để che lỗi.

## 11. Lỗi thường gặp và cách chẩn đoán

| Triệu chứng | Cách hiểu đúng | Cách xử lý |
| --- | --- | --- |
| `NoUniqueBeanDefinitionException` khi inject type `T` | Có nhiều candidates mà không xác định được một | Kiểm type matches; dùng một primary hoặc qualifier theo ý định |
| Hai `@Primary` cùng type | Không có primary duy nhất | Chọn một bean mặc định, hoặc thêm qualifier tại từng điểm inject |
| `@Qualifier("safeTransport")` không nhận FAST primary | Đây là hành vi đúng: FAST không thỏa qualifier SAFE | Kiểm hợp đồng điểm inject, không đổi primary để chữa |
| `@Primary` nhưng `getBean("safeTransport")` vẫn lấy SAFE | Lookup **theo tên explicit**, không phải lựa chọn theo type | Phân biệt getBean(name) với getBean(type) |
| `List<Transport>` chứa cả FAST và SAFE | Primary chỉ giúp chọn **một** dependency | Dùng collection đúng mục đích; lọc/sắp nếu cần |
| Bean primary không có mặt trong collection injection | Có thể bị loại bởi type/qualifier/autowireCandidate | Kiểm bean registration và candidate filtering |
| Bỏ `@Primary` nhưng injection vẫn chạy | Có thể chỉ còn một candidate, hoặc có qualifier/name/fallback khác | Quan sát injection point thực tế và tập candidates |
| Class có `@Primary` nhưng bean không được ưu tiên | Metadata đăng ký không đến từ component scan hoặc annotation ở sai nơi | Với `@Bean`, đặt `@Primary` trên method; XML dùng primary attr |
| Bean cùng type ở 2 contexts cho behavior khác | Candidate set/hierarchy khác nhau | Xem context cụ thể, profile/registration/parent hierarchy |
| Primary bean có type implementation khác | Chỉ type tương thích mới là candidate | Đổi interface hợp đồng hoặc type đăng ký phù hợp |
| App chạy nhưng chọn implementation sai | `@Primary` bị dùng quá rộng cho nhiều use cases | Dùng `@Qualifier` cho điểm inject cụ thể, test composition root |
| Circular dependencies không biến mất | Primary chọn candidate, không sửa đồ thị chu trình | Refactor quan hệ phụ thuộc |
| Bean được đánh `@Primary` nhưng init lỗi | Primary không bỏ qua constructor/lifecycle failure | Đọc root cause của bean creation |
| Không thấy `@Primary` trên type discovery | Type-discovery APIs thường không thể hiện trực tiếp ưu tiên | Xem bean definition `isPrimary()` hoặc phép lookup thực |
| Ngộ nhận `@Order` là `@Primary` | Ordering khác candidate preference | Dùng đúng annotation theo nhu cầu |

**Checklist debug:** xác định injection point đang cần **một bean hay collection**; kiểm bean registrations và type compatibility; xem qualifier/generic/primary/fallback và `autowireCandidate`; xác minh primary metadata ở **bean definition**; rồi quan sát kết quả `getBean(Type.class)` hoặc wiring integration test trong **đúng context**.

## 12. Bài tập dự đoán trước khi chạy

Làm từng thay đổi trên một bản sao code, khôi phục source gốc giữa các bài để so expected stdout.

1. **Đổi primary:** chuyển `@Primary` từ FAST sang SAFE trong PrimaryConfig. Dự đoán `main.selected=SAFE`, còn `main.qualified=SAFE` vẫn giữ.
2. **Bỏ primary:** xóa `@Primary` ở PrimaryConfig nhưng giữ FAST/SAFE thường. Dự đoán `dashboard(Transport transport,...)` có thể gây ambiguity khi context refresh.
3. **Thêm primary thứ hai:** đánh `@Primary` cho SAFE khi FAST vẫn primary. Giải thích tại sao hai primary không tạo ra “thứ tự ưu tiên” và context có thể fail vì Dashboard cần một Transport.
4. **Đổi qualifier:** sửa `@Qualifier("safeTransport")` thành `@Qualifier("fastTransport")`; dự đoán `main.qualified=FAST` và `main.sameQualified` phải so với đúng reference.
5. **Bỏ qualifier:** bỏ `@Qualifier` ở tham số safeTransport. Dự đoán cả hai `Transport` parameters sẽ chọn FAST primary nếu không có ràng buộc khác.
6. **Thêm fallback:** đánh `@Fallback` cho SAFE (không primary). Dự đoán các beans nào vẫn có mặt trong list/map.
7. **Thêm implementation:** tạo `ExperimentalTransport`, đăng ký `@Bean` mới. Nếu giữ đúng một primary FAST, single injection vẫn có thể chọn FAST, collection sẽ mở rộng.
8. **Thay collection:** dùng `List<Transport>` và in `size()`. Vì sao số lượng không trở thành 1 chỉ vì có primary?
9. **Đổi scope:** đặt `@Scope("prototype")` trên FAST, lấy hai lần theo tên để quan sát identity. Phân biệt candidate priority và number of instances.
10. **Đổi declared return type:** khai báo một `@Bean` có interface type vs concrete class type; xem ảnh hưởng của metadata trong lookup theo implementation.
11. **Dùng `@Qualifier` với SAFE không primary:** xác nhận qualifier vẫn chọn đúng SAFE; vì sao primary không phải “bộ lọc mạnh nhất”?
12. **Dùng XML:** tạo định nghĩa độc lập với `primary="true"` và so cơ chế với annotation trên method `@Bean`.
13. **Không có bean:** loại tất cả Transport beans khỏi một config và gọi `getBean(Transport.class)`; phân biệt `NoSuchBeanDefinitionException` với `NoUniqueBeanDefinitionException`.
14. **Chạy Java thuần:** thêm lựa chọn `backup` vào map của `ManualPrimaryChoice`; thấy việc chỉ định default không ngăn caller yêu cầu một key khác.
15. **Tách tests:** viết unit test Dashboard với các transport fake truyền trực tiếp và integration test dùng `AnnotationConfigApplicationContext` để kiểm chứng `@Primary`.

### Checklist hoàn thành

- [ ] Hiểu `@Primary` là **preference cho single-valued dependency**, không phải tạo bean hoặc loại beans khác.
- [ ] Khai báo được `@Primary` đúng nơi trên `@Bean` hoặc component class.
- [ ] Biết một candidate duy nhất không cần primary.
- [ ] Biết hai primary có thể tạo ambiguity.
- [ ] Phân biệt `@Primary`, `@Qualifier`, `@Fallback`, `@Order` và `autowireCandidate=false`.
- [ ] Không nhầm `getBean(name)` với `getBean(Type.class)`.
- [ ] Giải thích vì sao list/map injection vẫn nhận nhiều beans.
- [ ] Nhận diện đúng scope/context, qualifier và generic type khi primary không được chọn.
- [ ] Chạy Maven Java 17 ra đúng 18 dòng stdout ứng dụng và Java thuần ra đúng 4 dòng.
- [ ] Biết điều tra root cause khi bean selection bị thiếu hoặc mơ hồ.

## 13. Tóm tắt và tài liệu tra cứu

**Ghi nhớ:** Khi nhiều bean definitions cùng có thể đáp ứng một dependency, `@Primary` đánh dấu bean nên được **ưu tiên** nếu phải chọn **một** và bean ấy **còn là ứng viên hợp lệ** sau khi xét type, qualifiers và các ràng buộc liên quan. Nó không xóa bean khác, không đổi lifecycle/scope và không ép override một yêu cầu tên tường minh.

Tài liệu chính thức:
- [Spring Framework — Primary and Fallback](https://docs.spring.io/spring-framework/reference/core/beans/annotation-config/autowired-primary.html)
- [Spring Framework — Fine-tuning Autowiring with Qualifiers](https://docs.spring.io/spring-framework/reference/core/beans/annotation-config/autowired-qualifiers.html)
- [Spring Framework — Using @Autowired](https://docs.spring.io/spring-framework/reference/core/beans/annotation-config/autowired.html)
- [Spring Framework — Autowiring Collaborators](https://docs.spring.io/spring-framework/reference/core/beans/dependencies/factory-autowire.html)
- [Spring Framework — Java Configuration and @Bean](https://docs.spring.io/spring-framework/reference/core/beans/java/bean-annotation.html)
- [Spring API — Primary](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/context/annotation/Primary.html)
- [Spring API — Fallback](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/context/annotation/Fallback.html)
- [Spring API — BeanDefinition](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/beans/factory/config/BeanDefinition.html)

**Kết luận thực hành:** Hãy xem `@Primary` là **một policy mặc định khi Spring phải chọn một ứng viên**, không phải cách che mọi lỗi DI. Nếu một use case cần implementation cụ thể, dùng qualifier rõ ràng; nếu cần tất cả implementations, dùng collection; nếu muốn một lựa chọn dự phòng, cân nhắc fallback. Kiểm chứng từng policy bằng một context nhỏ và output quan sát được.