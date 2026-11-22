# @Fallback và điều kiện phiên bản từ Spring Framework 6.2

## 1. @Fallback giải quyết vấn đề gì?

Một thư viện hoặc module có thể cung cấp **implementation mặc định** để ứng dụng chạy ngay. Khi ứng dụng đăng ký implementation riêng, ta muốn Spring **ưu tiên implementation riêng mà không buộc người dùng thêm @Primary**.

Từ **Spring Framework 6.2**, annotation `org.springframework.context.annotation.Fallback` phục vụ đúng tình huống này: đánh dấu một bean là **ứng viên dự phòng** khi Spring tự động chọn bean cho **dependency đơn** (*single-valued autowiring*).

~~~java
@Bean
@Fallback
MessageCodec defaultCodec() {
    return new DefaultCodec();
}
~~~

Khối này chỉ là **minh họa**; cần định nghĩa các class/interface, import và cấu hình Spring. Phần chạy hoàn chỉnh nằm ở mục 5.

Nếu context chỉ có bean `defaultCodec` phù hợp, Spring vẫn inject bean đó bình thường. Nếu ứng dụng đăng ký thêm một bean `MessageCodec` **thông thường (không fallback)** và đó là ứng viên thông thường duy nhất, Spring chọn bean thông thường.

~~~text
Injection point: MessageCodec codec
                  |
       ứng viên đúng type MessageCodec
                  |
        +---------+---------+
        |                   |
    defaultCodec         customCodec
    @Fallback            thông thường
        |                   |
        +---------+---------+
                  |
      có đúng 1 ứng viên thông thường?
                  |
            Có -> customCodec
            Không -> cần xét thêm các quy tắc chọn
                    / thiếu / mơ hồ
~~~

**Ba điểm không được hiểu sai:**

- `@Fallback` **không xóa hoặc vô hiệu hóa** bean. Bean vẫn có thể lấy theo tên, inject theo qualifier thích hợp và xuất hiện trong `List<MessageCodec>`, `Map<String, MessageCodec>` hoặc stream từ provider.
- `@Fallback` **không đồng nghĩa @Lazy, @Conditional hay @Profile**. Nó không đợi tới lúc implementation khác thất bại rồi thay thế bean đang được service sử dụng.
- `@Fallback` **không có trước Spring Framework 6.2**. Source import annotation này không compile với Spring 6.1.x hoặc các phiên bản trước vì API tương ứng chưa tồn tại.

Trong mô hình này, "fallback" mô tả **ưu tiên ứng viên khi autowire một object**, không phải kỹ thuật chịu lỗi, circuit breaker hay retry của ứng dụng.

## 2. Điều kiện áp dụng và quy tắc chọn bean

`@Fallback` có dạng marker annotation (không cần tham số):

~~~java
import org.springframework.context.annotation.Fallback;
~~~

Theo API Spring 6.2, nó có thể được đặt trên **class** (`TYPE`) hoặc **method** (`METHOD`), với retention runtime. Hai vị trí thường dùng:

~~~java
// Minh họa bean factory method:
@Bean
@Fallback
MessageCodec fallbackCodec() {
    return new DefaultCodec();
}
~~~

~~~java
// Minh họa component class:
@Component
@Fallback
class DefaultCodec implements MessageCodec {
    // Triển khai các method MessageCodec
}
~~~

Hai khối trên chỉ minh họa; không là file chạy độc lập. Với component, phải bật component scanning đúng package hoặc đăng ký class vào context. Với `@Bean`, class `@Configuration` chứa factory method phải được Spring đăng ký.

### 2.1. Bảng quyết định cho dependency đơn

Giả sử `MessageCodec` là interface, bean candidates đã đúng type và không có qualifier/điều kiện đặc biệt khác.

| Bean phù hợp | Kết quả mong đợi khi inject `MessageCodec` đơn |
| --- | --- |
| Một bean fallback, không có bean khác | Chọn bean fallback |
| Một bean thông thường + một bean fallback | Chọn bean thông thường |
| Một bean thông thường + nhiều bean fallback | Chọn bean thông thường |
| Hai bean thông thường + một bean fallback | Còn mơ hồ nếu không có quy tắc chọn thêm |
| Hai bean fallback, không bean thông thường | Có thể mơ hồ vì chỉ đánh dấu fallback chưa xác định duy nhất |
| Một bean `@Primary` phù hợp + những ứng viên không primary | Bean primary thường được ưu tiên cho injection đơn |
| Không có bean phù hợp | Required dependency không giải quyết được |

Quy tắc do tài liệu Spring nêu rõ: **nếu trong nhiều ứng viên chỉ có một bean không đánh dấu fallback, bean đó được ưu tiên**, gần như có hiệu lực primary ở tình huống này.

**Không suy rộng** rằng "cứ có @Fallback là Spring luôn chọn được một bean". Khi còn hai beans thông thường, `@Fallback` trên bean thứ ba không thể tự phân biệt hai bean chính. Khi có hai fallbacks và không có bean thường, cũng vẫn cần lựa chọn rõ hoặc thay cấu hình.

### 2.2. Một bean fallback duy nhất vẫn dùng được

Đây là điều kiện giúp một thư viện đóng gói implementation mặc định:

- Thư viện cung cấp `@Fallback MessageCodec defaultCodec()`.
- Ứng dụng không override: service nhận `defaultCodec`, chạy ngay.
- Ứng dụng bổ sung `@Bean MessageCodec customCodec()`: service nhận `customCodec` mà không phải thêm `@Primary` lên bean mới.

Cách này thuận tiện cho **library starter, module mở rộng hoặc tích hợp có implementation mặc định**. Nhưng annotation không tự quyết định nên có bao nhiêu bean được đăng ký; cơ chế đăng ký vẫn qua `@Bean`, component scan, import, bean definition hay configuration tương ứng.

### 2.3. Bean fallback vẫn hiện diện trong container

`@Fallback` không xóa bean cũ và cũng không ngăn Spring tạo singleton non-lazy. Nếu `defaultCodec` có singleton scope, nó vẫn có thể được tạo khi context refresh theo vòng đời thông thường.

Khi gọi:

~~~java
MessageCodec selected = context.getBean(MessageCodec.class);
MessageCodec backup = context.getBean(
        "defaultCodec", MessageCodec.class);
~~~

trong context có cả một bean thường duy nhất và một fallback, type-based lookup có thể chọn bean thường, còn **lookup tường minh tên `defaultCodec` vẫn lấy fallback**. Đây là hai dạng yêu cầu bean khác nhau, đừng dùng chúng như cùng một phép đo.

## 3. So sánh @Fallback, @Primary và @Qualifier

| Annotation | Vai trò chính | Khi nào nên dùng? |
| --- | --- | --- |
| `@Fallback` | Hạ mức ưu tiên của bean dự phòng trong chọn dependency đơn | Module cung cấp default implementation, muốn application-specific bean tự được ưu tiên |
| `@Primary` | Nâng mức ưu tiên một bean khi có nhiều candidates đơn | Có một lựa chọn mặc định rõ giữa các implementations |
| `@Qualifier("name")` | **Lọc** các ứng viên theo tiêu chí/metadata | Injection point cần implementation mang vai trò cụ thể |
| Không annotation đặc biệt | Phân giải theo type và những metadata khác | Chỉ có một candidate đúng type hoặc Spring có rule rõ |

### 3.1. Khác nhau về hướng ưu tiên

Với `@Primary`:

~~~java
@Bean
@Primary
MessageCodec preferredCodec() {
    return new PreferredCodec();
}
~~~

Bean `preferredCodec` được đánh dấu là lựa chọn ưu tiên khi có nhiều ứng viên. Với `@Fallback`:

~~~java
@Bean
@Fallback
MessageCodec defaultCodec() {
    return new DefaultCodec();
}
~~~

Bean `defaultCodec` tuy vẫn đủ điều kiện cung cấp `MessageCodec` nhưng **nhường chỗ cho bean không fallback** nếu chỉ còn đúng một bean thường trong các candidates.

Hai đoạn cần class tương ứng và import Spring mới compile độc lập. Chúng giải thích hai hướng thiết kế: **chỉ định bean nào là ưu tiên** so với **chỉ định bean nào là dự phòng**.

### 3.2. Qualifier vẫn quan trọng

Nếu cả `customA` và `customB` đều là beans thông thường cùng type `MessageCodec`, `@Fallback` trên bean thứ ba không phân biệt được hai ứng viên ấy. Có thể đặt:

~~~java
public Renderer(
        @Qualifier("customA") MessageCodec codec) {
    this.codec = codec;
}
~~~

Đây là snippet minh họa. `@Qualifier` của Spring đặt trên tham số để yêu cầu ứng viên phù hợp tên/metadata. Spring giải quyết qualifier trong **tập đã phù hợp type**, nên đừng nghĩ qualifier có thể biến một bean khác kiểu thành `MessageCodec`.

Bạn cũng có thể chủ động yêu cầu bean dự phòng qua qualifier rõ (ví dụ `@Qualifier("defaultCodec")` nếu metadata/tên bean thực tế tương ứng). Khi đó annotation fallback không có ý nghĩa "cấm sử dụng" bean; nó chỉ ảnh hưởng ưu tiên khi chọn theo kiểu.

### 3.3. @Primary không làm collection nhỏ lại

`@Primary` và `@Fallback` đều chủ yếu ảnh hưởng **chọn một object** khi có nhiều candidates. Nếu inject `List<MessageCodec>`, Spring vẫn có thể cung cấp cả beans thường, primary và fallback đúng type. Để giới hạn collection có chủ đích, hãy dùng qualifier hoặc một strategy/filter trong code thích hợp.

## 4. Collection, Map và ObjectProvider vẫn bao gồm fallback

Ví dụ:

~~~java
@Autowired
public void configure(List<MessageCodec> codecs,
                      Map<String, MessageCodec> codecsByName) {
    this.codecs = codecs;
    this.codecsByName = codecsByName;
}
~~~

Đây là code minh họa chưa định nghĩa field/interface. Spring có thể inject mọi bean đúng type vào `List`, và `Map<String, MessageCodec>` có **bean name** làm key và bean instance làm value.

`@Fallback` không loại thành viên khỏi tập này. Tài liệu API cũng chỉ rõ các array, collection, map và stream từ `ObjectProvider` bao gồm tất cả ứng viên type-matching.

Nếu chỉ cần **một implementation khi service hoạt động**, inject `MessageCodec` đơn. Nếu muốn **khám phá tất cả providers/strategies**, inject collection hoặc provider stream có chủ đích; khi đó hãy tự quyết định có bỏ qua fallback trong logic hay không, thay vì giả định container đã loại nó.

**Chú ý thứ tự:** collection injection không nên dựa vào thứ tự bean source hoặc scan package. Nếu thứ tự quan trọng, dùng Spring `@Order`/`Ordered` thích hợp hoặc sắp xếp dữ liệu trước khi in/xử lý.

### 4.1. ObjectProvider không có nghĩa chỉ trả bean thường

Nếu code gọi:

~~~java
ObjectProvider<MessageCodec> provider =
        context.getBeanProvider(MessageCodec.class);
var names = provider.stream().map(MessageCodec::name).toList();
~~~

đó là **ví dụ minh họa** cần khai báo interface, context và imports đầy đủ. Stream có thể liệt kê cả beans fallback. Trái lại, `getObject()` hoặc các biến thể single-object resolution của provider tuân theo quy tắc chọn candidate cụ thể và có thể bị mơ hồ nếu không có một ứng viên cuối.

Không nhầm việc có bean fallback với cơ chế `getIfAvailable()` trả null khi **thực sự không có bean**; fallback vẫn là bean đã đăng ký.

## 5. Ví dụ chạy đầy đủ: Spring Framework 6.2 và Java 17

Chương trình này tạo hai `ApplicationContext` độc lập:

- **Context thứ nhất:** chỉ đăng ký một `MessageCodec` fallback. Bean tiêu thụ được tiêm default.
- **Context thứ hai:** đăng ký thêm một `MessageCodec` thông thường. Bean tiêu thụ tự chọn implementation thường, nhưng collection vẫn có cả fallback; fallback vẫn lấy trực tiếp theo tên được.

### 5.1. Cấu trúc và Maven

Yêu cầu JDK 17+, Apache Maven. Dùng **Spring Framework 6.2.0** và `spring-context`; không dùng Spring Boot, web server hay database.

~~~text
spring-fallback-demo/
├── pom.xml
└── src/main/java/demo/FallbackDemo.java
~~~

Tạo tệp `pom.xml`:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/xsd/maven-4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>edu.example</groupId>
    <artifactId>spring-fallback-demo</artifactId>
    <version>1.0-SNAPSHOT</version>
    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.0</version>
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
                    <mainClass>demo.FallbackDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

### 5.2. Java source hoàn chỉnh

Tạo `src/main/java/demo/FallbackDemo.java`:

~~~java
package demo;

import java.util.List;
import java.util.Objects;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Fallback;
import org.springframework.context.annotation.Import;

public final class FallbackDemo {
    private FallbackDemo() {}

    public interface MessageCodec {
        String name();
        String render(String message);
    }

    public record PrefixCodec(String name, String prefix)
            implements MessageCodec {
        @Override
        public String render(String message) {
            return prefix + message;
        }
    }

    public static final class Processor {
        private final MessageCodec selected;
        private final List<MessageCodec> all;

        public Processor(MessageCodec selected, List<MessageCodec> all) {
            this.selected = Objects.requireNonNull(selected);
            this.all = List.copyOf(all);
        }

        public String selectedName() {
            return selected.name();
        }

        public String allNames() {
            return all.stream()
                    .map(MessageCodec::name)
                    .sorted()
                    .toList()
                    .toString();
        }

        public String process(String message) {
            return selected.render(message);
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class DefaultsConfig {
        @Bean
        @Fallback
        public MessageCodec defaultCodec() {
            return new PrefixCodec("fallback", "DEFAULT:");
        }

        @Bean
        public Processor processor(MessageCodec codec,
                                   List<MessageCodec> allCodecs) {
            return new Processor(codec, allCodecs);
        }
    }

    @Configuration(proxyBeanMethods = false)
    @Import(DefaultsConfig.class)
    public static class ExtensionConfig {
        @Bean
        public MessageCodec customCodec() {
            return new PrefixCodec("custom", "CUSTOM:");
        }
    }

    public static void main(String[] args) {
        inspect("-- fallback only --", DefaultsConfig.class);
        inspect("-- with regular bean --", ExtensionConfig.class);
    }

    private static void inspect(String heading, Class<?> configuration) {
        try (AnnotationConfigApplicationContext context =
                     new AnnotationConfigApplicationContext(configuration)) {
            Processor processor = context.getBean(Processor.class);
            System.out.println(heading);
            System.out.println("SELECTED " + processor.selectedName());
            System.out.println("ALL " + processor.allNames());
            System.out.println("RESULT " + processor.process("HELLO"));
            System.out.println("DEFAULT_DIRECT "
                    + context.getBean("defaultCodec", MessageCodec.class)
                             .render("HELLO"));
        }
    }
}
~~~

Trong `DefaultsConfig`, bean `defaultCodec` là fallback. Vì nó là bean `MessageCodec` duy nhất trong context đầu, Spring vẫn chọn nó cho tham số `MessageCodec codec`.

Trong `ExtensionConfig`, `@Import(DefaultsConfig.class)` làm cả `defaultCodec` lẫn `customCodec` xuất hiện. Vì có đúng một ứng viên **không đánh dấu fallback** là `customCodec`, container chọn nó cho tham số đơn `codec`. Tuy nhiên, `List<MessageCodec> allCodecs` chứa cả hai bean.

**Những quyết định đảm bảo stdout ổn định:**

- `PrefixCodec` không in gì trong constructor hoặc factory method.
- `Processor.allNames()` sắp xếp tên bằng `sorted()` thay vì phụ thuộc thứ tự bean được liệt kê.
- Hai contexts tách biệt, mỗi context đóng qua try-with-resources.
- Lookup `defaultCodec` có tên tường minh và loại bean đúng.

### 5.3. Lệnh chạy và stdout dự kiến

Tại thư mục `spring-fallback-demo`:

~~~bash
mvn -version
mvn -q compile exec:java
~~~

Vì chương trình phụ thuộc Spring jars, lệnh `javac/java` trực tiếp đòi classpath đầy đủ; Maven quản lý dependency và main class cho bản chạy trên. `maven.compiler.release=17` bảo đảm compile theo Java 17.

**Stdout do code chủ động in theo đúng thứ tự:**

~~~text
-- fallback only --
SELECTED fallback
ALL [fallback]
RESULT DEFAULT:HELLO
DEFAULT_DIRECT DEFAULT:HELLO
-- with regular bean --
SELECTED custom
ALL [custom, fallback]
RESULT CUSTOM:HELLO
DEFAULT_DIRECT DEFAULT:HELLO
~~~

Lệnh `mvn -version` in phiên bản; Maven có thể in thông tin tải dependencies hoặc plugin logs. Khối trên chỉ biểu diễn các dòng `System.out.println` trong `FallbackDemo`.

### 5.4. Phân tích kết quả

1. `AnnotationConfigApplicationContext(DefaultsConfig.class)` refresh context đầu và đăng ký `defaultCodec` cùng `processor`.
2. `@Fallback` không làm `defaultCodec` biến mất. `processor(MessageCodec codec, ...)` nhận fallback vì không còn candidate nào khác cùng type.
3. `Processor` in tên `fallback`; list có một bean nên `ALL [fallback]`.
4. `process("HELLO")` trả `DEFAULT:HELLO`. Lookup theo tên `defaultCodec` cũng trả implementation mặc định.
5. Context thứ hai import cấu hình default và bổ sung `customCodec` như **bean thường**, không gắn `@Primary`.
6. Khi Spring tạo `processor`, type `MessageCodec` có hai candidates nhưng một candidate fallback. Spring ưu tiên bean `customCodec` cho injection đơn nên `SELECTED custom`.
7. `List<MessageCodec>` vẫn nhận cả hai candidates, nên `ALL [custom, fallback]` sau khi sort.
8. `process("HELLO")` dùng custom codec trả `CUSTOM:HELLO`; lookup trực tiếp `defaultCodec` vẫn trả `DEFAULT:HELLO`.
9. `@Fallback` chỉ quyết định lúc autowiring; nó **không thay dependency của một Processor đã được tạo** khi bạn thêm bean definition hay thay environment về sau.

Ví dụ không dùng `@ComponentScan`; tất cả beans được khai báo bằng `@Configuration`/`@Bean`. Không có Spring Boot auto-configuration hoặc điều kiện đặc biệt nào tác động tới việc chọn bean.

## 6. Java 17 thuần: mô phỏng quy tắc fallback để hiểu rõ

Java 17 không có `@Fallback` của Spring và không tự tạo container. Để minh họa tiêu chí chọn, hãy viết một chương trình riêng thực hiện **phiên bản rút gọn** của quy tắc:

- Nếu có đúng **một bean thường**, chọn nó.
- Nếu **không có bean thường** nhưng chỉ có một candidate, chọn candidate ấy.
- Nếu còn nhiều ứng viên không phân giải được, báo mơ hồ.

Đây là **mô hình giảng dạy**, không thay thế thuật toán Spring thực tế (còn có qualifier, primary, scope, type matching và các quy tắc resolution khác).

Tạo file `FallbackSelection.java`:

~~~java
import java.util.List;

public final class FallbackSelection {
    public record Candidate(String name, boolean fallback) {}

    static Candidate select(List<Candidate> candidates) {
        List<Candidate> regular = candidates.stream()
                .filter(candidate -> !candidate.fallback())
                .toList();
        List<Candidate> considered =
                regular.isEmpty() ? candidates : regular;

        if (considered.size() != 1) {
            throw new IllegalStateException(
                    "ambiguous: " + considered.size());
        }
        return considered.get(0);
    }

    public static void main(String[] args) {
        Candidate base = new Candidate("default", true);
        Candidate custom = new Candidate("custom", false);
        Candidate another = new Candidate("another", false);

        System.out.println("BASE "
                + select(List.of(base)).name());
        System.out.println("CUSTOM "
                + select(List.of(base, custom)).name());

        try {
            select(List.of(base, custom, another));
        } catch (IllegalStateException ex) {
            System.out.println("MULTIPLE " + ex.getMessage());
        }
    }
}
~~~

Tại thư mục chứa file này, chạy JDK 17+:

~~~bash
javac --release 17 -encoding UTF-8 FallbackSelection.java
java FallbackSelection
~~~

**Stdout chính xác:**

~~~text
BASE default
CUSTOM custom
MULTIPLE ambiguous: 2
~~~

Dòng cuối thể hiện trường hợp có **hai bean thường** còn tồn tại sau khi bỏ qua bean fallback để chọn một dependency đơn. Không có quy tắc `@Primary` hoặc qualifier nào được mô phỏng nên code báo mơ hồ. Đây chính là lý do `@Fallback` **không thay được** toàn bộ bean candidate resolution.

## 7. Điều kiện phiên bản và khả năng tương thích

### 7.1. Version tối thiểu

- `@Fallback` được giới thiệu **từ Spring Framework 6.2.0**.
- Package và import chính xác: `org.springframework.context.annotation.Fallback`.
- Với `spring-context:6.2.0`, demo dùng API có thật và Java 17, không cần Java preview syntax.
- **Spring Framework 6.1.x trở xuống không có `@Fallback`**; thêm import trên những phiên bản ấy gây lỗi biên dịch kiểu `cannot find symbol`/`Fallback cannot be resolved to a type`.
- Không nhầm `@Fallback` với `@Primary`, vốn đã có ở các phiên bản Spring trước đó.

### 7.2. Spring Boot và quản lý phiên bản dependency

Nếu project dùng Spring Boot, phiên bản Spring Framework thường do **BOM/dependency management** của Boot quyết định. Đừng mặc định rằng phiên bản được viết trong `pom.xml` của một module phụ sẽ luôn là phiên bản framework thực tế khi chạy một ứng dụng khác.

Khi nghi ngờ version mismatch:

~~~bash
mvn -version
mvn dependency:tree -Dincludes=org.springframework:spring-context
~~~

Nếu project dùng Gradle, kiểm tra dependency resolution bằng công cụ tương ứng như `./gradlew dependencies --configuration runtimeClasspath`, với tên configuration tùy project. Lệnh Maven trên không yêu cầu chạy ứng dụng; nó giúp nhìn `spring-context` được resolve thành version nào.

**Nên đồng bộ các module Spring Framework** qua BOM hoặc dependency management tương thích. Ép riêng một JAR Spring lên 6.2 trong một ứng dụng vẫn có các JAR lõi Spring 6.1 có thể tạo classloading/compatibility problems. Muốn dùng `@Fallback`, bảo đảm toàn bộ Spring dependency graph phù hợp, không chỉ biên dịch được một source file.

### 7.3. Nếu chưa thể nâng lên 6.2

Trong Spring cũ, một cách tương đối đơn giản là:

- Đánh dấu implementation muốn ưu tiên bằng `@Primary` nếu bạn kiểm soát cấu hình ứng dụng.
- Hoặc dùng `@Qualifier` để chọn đúng implementation tại injection point.
- Hoặc thiết kế conditional bean registration bằng cơ chế/framework thích hợp, nếu thực sự muốn **không đăng ký** default bean khi có custom bean.

Đây là các **phương án thay thế theo yêu cầu cụ thể**, không có nghĩa một annotation `@Primary` trên default bean sẽ cho cùng hành vi với `@Fallback`. Nếu đánh dấu **default** là primary, nó sẽ được ưu tiên thay vì nhường chỗ cho custom bean — ngược hẳn mục tiêu.

### 7.4. Java 17 và import

Spring Framework 6.2 yêu cầu nền Java phù hợp với thế hệ Spring 6; dùng **Java 17+** là lựa chọn nền tảng cho các ví dụ ở đây. Mã của mục 5 có record, stream `toList()` và try-with-resources — đều được Java 17 hỗ trợ.

Annotation có thể dùng trên class hoặc method:

~~~java
@Fallback
class DefaultCodec implements MessageCodec {
    // ...
}

@Bean
@Fallback
MessageCodec defaultCodec() {
    return new DefaultCodec();
}
~~~

Đây là hai kiểu khai báo **minh họa thay thế nhau**. Không copy cả hai vào cùng bean graph rồi kỳ vọng chỉ có một fallback bean: mỗi bean definition sẽ được Spring xét riêng.

## 8. Những điều @Fallback KHÔNG làm

| Hiểu nhầm | Sự thật |
| --- | --- |
| "Bean fallback chỉ được tạo nếu không có bean thường." | Không; annotation không phải điều kiện đăng ký/khởi tạo bean. |
| "Fallback tự xóa default bean khi custom bean xuất hiện." | Không; default bean vẫn nằm trong context. |
| "Fallback có nghĩa là failover khi bean chính ném exception." | Không; đây là metadata chọn candidate, không phải cơ chế chịu lỗi runtime. |
| "Có @Fallback rồi, hai bean thường sẽ tự hết mơ hồ." | Không; hai beans thường vẫn cần rule chọn. |
| "Fallback luôn bị loại khỏi `List<T>` hoặc `Map<String,T>`." | Không; collection/map/provid​er streams vẫn có các beans phù hợp. |
| "Đánh dấu @Fallback lên injection parameter." | Không đúng target; annotation dành cho bean class hoặc factory method. |
| "Fallback giống @Primary." | Ngược hướng ưu tiên: primary nâng ưu tiên, fallback nhường chỗ cho bean thường. |
| "Fallback giống @Qualifier." | Qualifier lọc theo tiêu chí; fallback đánh dấu mức ưu tiên trong giải quyết dependency đơn. |
| "Fallback dùng được trên Spring 6.1." | Không; cần Spring 6.2+. |
| "Fallback luôn làm bean @Lazy." | Không; lazy initialization là cấu hình riêng. |
| "Bean fallback là candidate sai kiểu cũng được inject." | Không; cần match type/metadata của dependency. |
| "Annotation tự động chọn bean theo nội dung từng request." | Không; autowiring không phải business runtime routing. |

### Khi có nhiều beans fallback

Nếu chỉ có hai beans fallback cùng type, injection đơn vẫn có thể không chọn được duy nhất. Đừng tưởng "cả hai là backup" có nghĩa Spring sẽ tự dùng bản được khai báo trước. Nếu muốn một lựa chọn mặc định cố định trong nhóm, cần một rule chọn thêm hoặc đơn giản hóa bean graph; nếu muốn cả hai, inject collection.

### @Fallback và @Qualifier cùng tồn tại

Qualifier thường giúp chọn **một tập ứng viên hợp lệ cho injection point**. Fallback vẫn mang ý nghĩa mức ưu tiên khi Spring cần quyết định ứng viên đơn. Vì vậy lựa chọn theo tên/qualifier có thể chủ động đưa một bean fallback vào vị trí cần dùng; nhưng đừng dựa vào một thứ tự ưu tiên tưởng tượng áp dụng cho mọi cấu hình. Khi có nhiều qualifier/primary/fallback, kiểm thử bean graph bằng integration test là cách tốt nhất.

## 9. Kiểm thử hành vi selection

Bài demo xác minh hai trường hợp quan trọng mà không cần network/database:

- Chỉ fallback: processor nhận `defaultCodec`.
- Fallback + một regular bean: processor nhận `customCodec`, nhưng `List<MessageCodec>` vẫn chứa cả hai.

Trong dự án thực, nên thêm integration tests:

1. Context chỉ có bean fallback → inject thành công.
2. Context có fallback và một bean thường → chọn bean thường.
3. Context có fallback và **hai bean thường** → xem kết quả theo qualifier/primary/name matching thực tế; nếu thiếu rule phải phát hiện ambiguity.
4. Inject `List<T>` hoặc typed `Map<String,T>` → xác minh bean fallback vẫn có mặt.
5. Lookup bean fallback theo tên → bean vẫn được phép truy cập.
6. Kết quả dependency tree thể hiện Spring Framework phiên bản 6.2+ đồng bộ.

Không nên viết unit test chỉ assert source có `@Fallback` mà không khởi tạo context: annotation đứng trên bean là metadata, cần một Spring container thật để xác nhận injection resolution.

### Dấu hiệu lỗi và cách debug

- `cannot find symbol: Fallback`: version Spring cũ hoặc import sai package.
- `NoSuchBeanDefinitionException`: không có candidate matching type/qualifier, hoặc configuration chưa được register.
- `NoUniqueBeanDefinitionException`: vẫn có nhiều candidates cuối cùng, thường là nhiều bean thường cùng type.
- `BeanCreationException`: candidate hoặc factory method lỗi khi khởi tạo; `@Fallback` không tự xử lý exception này.
- App đã nâng Spring nhưng vẫn chọn bean khác dự kiến: kiểm tra qualifier, `@Primary`, bean name, `@Fallback` trên đúng bean definition, và thứ tự/nguồn cấu hình.
- Collection không có fallback như mong đợi: kiểm tra fallback bean có thực sự được đăng ký và có type tương thích hay không, không tự quy lỗi cho annotation.

## 10. Bài tập kèm đáp án

**1.** Chỉ có một `@Fallback MessageCodec`, injection đơn `MessageCodec` có dùng được không?

**Đáp án:** Có. Khi nó là candidate duy nhất, Spring có thể inject bean fallback.

**2.** Thêm một bean `MessageCodec` thông thường, không có `@Primary`; Spring chọn ai?

**Đáp án:** Với đúng một bean thường phù hợp, Spring chọn bean thường, không chọn fallback.

**3.** Nếu có hai beans thường và một fallback, injection đơn chắc chắn chọn bean thường khai báo trước?

**Đáp án:** Không. Khi còn hai candidates thường, cần một quy tắc rõ để chọn cuối cùng; nếu không có có thể bị lỗi mơ hồ.

**4.** `List<MessageCodec>` có hai phần tử khi context có một fallback và một regular bean không?

**Đáp án:** Có, nếu cả hai cùng type và là ứng viên autowire phù hợp. Annotation fallback không loại bean khỏi collection.

**5.** `@Fallback` có làm `getBean("defaultCodec")` thất bại không?

**Đáp án:** Không. Bean vẫn được đăng ký; explicit lookup theo tên có thể lấy nó.

**6.** Có thể dùng `@Fallback` thay circuit breaker nếu implementation chính ngắt mạng?

**Đáp án:** Không. Fallback annotation chỉ xử lý candidate selection lúc wiring, không retry/failover tự động giữa các lần gọi nghiệp vụ.

**7.** Tại sao Spring 6.1 báo không tìm thấy class `Fallback`?

**Đáp án:** Vì annotation được thêm từ Spring Framework 6.2. Muốn dùng cần nâng framework phù hợp hoặc chọn cách cấu hình tương thích version cũ.

**8.** `@Primary` có giống `@Fallback` không?

**Đáp án:** Không. Primary đánh dấu bean được ưu tiên; fallback đánh dấu bean sẽ nhường chỗ khi có lựa chọn thông thường phù hợp.

**9.** Một bean `@Fallback` có thể xuất hiện trong `ObjectProvider<T>.stream()` không?

**Đáp án:** Có, nếu type và các điều kiện autowire phù hợp; fallback không tự loại nó khỏi provider stream.

**10.** Nếu framework starter cung cấp default implementation, nên dùng `@Primary` lên default hay `@Fallback`?

**Đáp án:** Trong Spring 6.2+, `@Fallback` thường thích hợp khi muốn bean do ứng dụng đăng ký **được ưu tiên tự nhiên** mà không cần người dùng ghi `@Primary`. Nếu starter muốn chỉ tạo bean khi hoàn toàn chưa có bean loại đó, cần xét **conditional registration** riêng, không đánh đồng với fallback metadata.

**11.** Vì sao demo sắp xếp tên trong `allNames()`?

**Đáp án:** Để stdout không phụ thuộc thứ tự Spring đưa bean vào collection; chuỗi `[custom, fallback]` ổn định.

## 11. Checklist áp dụng trong dự án

- [ ] Đã xác định yêu cầu Java 17+ và Spring Framework **6.2+** nếu dùng `@Fallback`.
- [ ] Import đúng `org.springframework.context.annotation.Fallback`.
- [ ] Annotation đặt trên bean class hoặc `@Bean` factory method, không trên injection parameter.
- [ ] Có bean default đăng ký hợp lệ; không tưởng annotation tự tạo bean.
- [ ] Dependency đơn chỉ còn một bean thường nếu muốn nó thắng fallback một cách tự nhiên.
- [ ] Không nghĩ `@Fallback` loại bean khỏi collection/Map/provider stream.
- [ ] Nếu có nhiều regular beans, thiết kế rule chọn rõ bằng qualifier/primary khi phù hợp.
- [ ] Không áp `@Primary` cho default nếu mong custom bean luôn được ưu tiên.
- [ ] Không coi fallback bean là điều kiện `@ConditionalOnMissingBean` hay failover runtime.
- [ ] Kiểm tra Spring dependency tree/bom để tránh sai phiên bản.
- [ ] Unit test logic xử lý riêng với integration test candidate resolution.
- [ ] Test cả context có và không có bean override.
- [ ] Không dựa vào thứ tự quét package làm rule chọn bean.
- [ ] Với bean singleton, cân nhắc lifecycle/thread safety riêng; annotation fallback không ảnh hưởng các yêu cầu đó.
- [ ] Khi giữ backward compatibility với Spring trước 6.2, không import API chưa có.
- [ ] Kiểm tra stdout ứng dụng tách khỏi log Maven.

### Tài liệu chính thức

- [Fine-tuning Annotation-based Autowiring with @Primary or @Fallback](https://docs.spring.io/spring-framework/reference/core/beans/annotation-config/autowired-primary.html)
- [@Fallback API — Spring Framework 6.2](https://docs.spring.io/spring-framework/docs/6.2.16/javadoc-api/org/springframework/context/annotation/Fallback.html)
- [Spring Framework 6.2 Release Notes — Support for fallback beans](https://github.com/spring-projects/spring-framework/wiki/Spring-Framework-6.2-Release-Notes)
- [Fine-tuning Autowiring with Qualifiers](https://docs.spring.io/spring-framework/reference/core/beans/annotation-config/autowired-qualifiers.html)

**Kết luận:** `@Fallback` là một công cụ **ưu tiên bean candidate** có từ **Spring Framework 6.2**. Nó cho phép module đăng ký implementation mặc định nhưng tự nhường cho một implementation thông thường được ứng dụng bổ sung. Bean fallback vẫn tồn tại trong context và trong injection theo collection. Hiểu giới hạn này, điều kiện version và khác biệt với `@Primary`/`@Qualifier` giúp bạn cung cấp default behavior một cách chủ động mà không biến annotation thành cơ chế thay thế bean hay xử lý lỗi runtime.