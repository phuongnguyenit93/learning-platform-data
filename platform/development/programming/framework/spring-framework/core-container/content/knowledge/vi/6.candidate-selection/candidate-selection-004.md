# Lọc tập ứng viên bằng `@Qualifier` trong Spring Core Container

## 1. Bản chất: chọn từ tập bean đã khớp kiểu

Khi Spring cần cung cấp dependency cho một constructor, field, method hoặc `@Bean` factory method, container trước hết xét **những bean phù hợp kiểu** của injection point. Nếu có nhiều ứng viên cùng interface, `@Qualifier` của Spring cho phép **thu hẹp tập ứng viên** theo một đặc điểm, nhãn hoặc tên phù hợp.

~~~text
                  Bean definitions
        fastA: Channel + qualifier "fast"
        fastB: Channel + qualifier "fast"
        slowC: Channel + qualifier "slow"
        formatter: Formatter + qualifier "fast"
                           |
                yêu cầu type Channel
                           |
                {fastA, fastB, slowC}
                           |
                @Qualifier("fast")
                           |
                    {fastA, fastB}
                      /        \
                List<Channel>  Channel
                   2 phần tử    2 ứng viên:
                                có thể mơ hồ
~~~

Điều quan trọng nhất của bài: **`@Qualifier` là bộ lọc trong số các bean tương thích kiểu, không mặc nhiên là khóa tham chiếu duy nhất tới một bean ID**. Hai bean cùng qualifier `"fast"` vẫn đều phù hợp khi inject một `List<Channel>`. Ngược lại, một injection point yêu cầu **một `Channel` duy nhất** sẽ còn mơ hồ nếu sau khi lọc vẫn có hai ứng viên và không có quy tắc chọn bổ sung. Đây là semantics được Spring nêu trực tiếp trong tài liệu tham khảo. 

Vì vậy, với `@Autowired` hoặc injection vào tham số `@Bean`, hãy hình dung ba bước:

1. Xác định **required type** tại injection point, có tính đến generic type và assignability.
2. Áp dụng các giới hạn/metadata như `@Qualifier` để **lọc những bean được phép làm ứng viên**.
3. Nếu yêu cầu một object, container phải chọn được **một** ứng viên cuối cùng; nếu yêu cầu collection, container có thể cung cấp **tất cả** ứng viên còn lại theo quy tắc tương ứng.

**Mục tiêu học:** dùng qualifier trực tiếp trên tham số, đánh dấu ứng viên bằng annotation, lọc `List`/`Set`, phân biệt với `@Primary` và lookup theo tên, xây custom qualifier, kiểm tra lỗi thiếu/mơ hồ, và chạy ví dụ Maven Java 17.

## 2. Cú pháp tối thiểu của Spring `@Qualifier`

Annotation ở đây là:

~~~java
import org.springframework.beans.factory.annotation.Qualifier;
~~~

Đừng nhầm với `jakarta.inject.Qualifier`: cái thứ hai là **meta-annotation** để định nghĩa qualifier tùy chỉnh, không nhận String trực tiếp theo cùng cú pháp.

### Trên bean definition: mô tả ứng viên

Với Java configuration:

~~~java
@Bean
@Qualifier("fast")
DeliveryPort fastGateway() {
    return new FastGateway();
}
~~~

Đây là **đoạn minh họa**, cần định nghĩa `DeliveryPort` và `FastGateway` nếu biên dịch độc lập. Nó công bố một bean tên mặc định `fastGateway`, type `DeliveryPort`, với metadata qualifier `"fast"`.

Cùng annotation cũng có thể được đặt trên một Spring component class:

~~~java
@Component
@Qualifier("fast")
final class FastGateway implements DeliveryPort {
    // Cần triển khai interface trong project thực.
}
~~~

Đây là cấu hình **thay thế minh họa**, không phải class thêm vào chương trình chính. Nó chỉ được đăng ký khi Spring scan đúng package hoặc bean được đăng ký theo cơ chế phù hợp.

### Trên injection point: chỉ nhận nhóm đã lọc

~~~java
@Autowired
public Sender(@Qualifier("fast") DeliveryPort gateway) {
    this.gateway = gateway;
}
~~~

Đây là snippet minh họa constructor injection. Spring tìm bean phù hợp type `DeliveryPort` **và** qualifier `"fast"`, rồi cần lựa chọn cuối cùng cho tham số đơn `gateway`. Nếu còn nhiều bean `"fast"` cùng type, chỉ ghi qualifier này chưa bảo đảm kết quả duy nhất.

Nếu class managed bean chỉ có một constructor, Spring Framework 4.3+ thường không cần `@Autowired` trên constructor ấy. Tuy nhiên **`@Qualifier` trên tham số vẫn có ý nghĩa**:

~~~java
public Sender(@Qualifier("fast") DeliveryPort gateway) {
    this.gateway = gateway;
}
~~~

Một lần nữa, mã trên chỉ minh họa khi `Sender` và collaborator được đăng ký đúng.

### Áp dụng trên từng tham số

~~~java
@Autowired
public void configure(
        @Qualifier("fast") DeliveryPort foreground,
        @Qualifier("slow") DeliveryPort background) {
    this.foreground = foreground;
    this.background = background;
}
~~~

Mỗi tham số được giải quyết riêng. Annotation trên `foreground` không tác động tới `background`. Phương thức có thể tên `configure`, không cần `set...`. Điều kiện là bean thực sự được Spring quản lý, các type/qualifiers phù hợp và không mơ hồ. Đoạn này không độc lập vì chưa định nghĩa các field/interface.

## 3. Qualifier là bộ lọc, **không buộc phải duy nhất**

Giả sử ba bean cùng kiểu `DeliveryPort`:

| Bean name | Type | Qualifier khai báo |
| --- | --- | --- |
| `fastA` | `DeliveryPort` | `fast` |
| `fastB` | `DeliveryPort` | `fast` |
| `slowC` | `DeliveryPort` | `slow` |

Các yêu cầu:

| Injection point | Tập ứng viên sau lọc | Kết quả thông thường |
| --- | --- | --- |
| `DeliveryPort` không qualifier | `fastA, fastB, slowC` | Mơ hồ nếu không có rule chọn |
| `@Qualifier("fast") DeliveryPort` | `fastA, fastB` | Vẫn có thể mơ hồ |
| `@Qualifier("slow") DeliveryPort` | `slowC` | Chọn `slowC` |
| `@Qualifier("fast") List<DeliveryPort>` | `fastA, fastB` | Inject cả hai |
| `@Qualifier("slow") Set<DeliveryPort>` | `slowC` | Inject tập gồm một bean |
| `@Qualifier("missing") DeliveryPort` | Không có bean phù hợp | Required injection thường lỗi |

Bảng trên giả định bean không có các metadata chọn bổ sung như `@Primary`, tên parameter mang ý nghĩa đặc biệt, hay điều kiện khác; nó minh họa chính quy tắc **thu hẹp theo type và qualifier**.

### Vì sao List vẫn nhận hai bean?

Bởi vì `@Qualifier("fast")` không có điều khoản “chỉ một bean duy nhất được phép mang nhãn fast”. Nó có nghĩa “chỉ xét những bean có đặc trưng fast”. Khi injection target là `List<DeliveryPort>` hoặc `Set<DeliveryPort>`, Spring có thể cung cấp tất cả bean phù hợp với cả type lẫn qualifier. Đây là trường hợp rất tự nhiên khi muốn nhiều handler, rule engine, notifier hay adapter cùng nhóm.

### Một bean ID không phải định nghĩa của qualifier

Spring cho phép **bean name làm giá trị fallback qualifier** trong tập bean đã đúng type. Nhờ đó, trong nhiều trường hợp có thể viết:

~~~java
@Autowired
public Sender(@Qualifier("fastA") DeliveryPort gateway) {
    this.gateway = gateway;
}
~~~

dù bean `fastA` chưa được đánh dấu riêng `@Qualifier("fastA")`, vì Spring có thể xét tên bean `fastA`. Nhưng đây vẫn là **type-driven autowiring**; một bean sai type không trở thành `DeliveryPort` chỉ vì tên khớp.

**Khuyến nghị:** nhãn qualifier mô tả thuộc tính ổn định như `"fast"`, `"eu"` hoặc `"persistent"` thường bền hơn chuỗi bean name `"fastGatewayV2"`. Còn nếu mục tiêu thật sự là tham chiếu **duy nhất theo tên**, `@Resource(name="...")` từ Jakarta Annotations/JSR-250 có semantics lookup theo tên khác với `@Autowired` + qualifier; cần classpath/annotation support phù hợp.

## 4. Ví dụ Spring Framework 6.2 / Java 17 runnable

Chương trình console có **hai bean cùng qualifier `fast`** và một bean qualifier `slow`. Spring inject toàn bộ nhóm fast vào một `List<DeliveryPort>` nhưng chỉ một slow vào dependency đơn.

### 4.1. Cấu trúc project

Cần JDK 17+ và Maven:

~~~text
qualifier-filter-demo/
├── pom.xml
└── src/main/java/demo/QualifierFilterDemo.java
~~~

Tạo `pom.xml`:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>edu.example</groupId>
    <artifactId>qualifier-filter-demo</artifactId>
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
                    <mainClass>demo.QualifierFilterDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

### 4.2. Mã nguồn đầy đủ

Tạo `src/main/java/demo/QualifierFilterDemo.java`:

~~~java
package demo;

import java.util.List;
import java.util.Objects;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.beans.factory.annotation.Qualifier;

public final class QualifierFilterDemo {
    private QualifierFilterDemo() {}

    public interface DeliveryPort {
        String code();
        String send(String text);
    }

    public record DemoDelivery(String code) implements DeliveryPort {
        @Override
        public String send(String text) {
            return code + ":" + text;
        }
    }

    public static final class Router {
        private final List<DeliveryPort> fast;
        private final DeliveryPort slow;

        public Router(List<DeliveryPort> fast, DeliveryPort slow) {
            this.fast = List.copyOf(Objects.requireNonNull(fast));
            this.slow = Objects.requireNonNull(slow);
        }

        public String fastNames() {
            return fast.stream()
                    .map(DeliveryPort::code)
                    .sorted()
                    .toList()
                    .toString();
        }

        public int fastCount() {
            return fast.size();
        }

        public String slowName() {
            return slow.code();
        }

        public String deliverSlow(String text) {
            return slow.send(text);
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class AppConfig {
        @Bean
        @Qualifier("fast")
        public DeliveryPort fastA() {
            return new DemoDelivery("fast-a");
        }

        @Bean
        @Qualifier("fast")
        public DeliveryPort fastB() {
            return new DemoDelivery("fast-b");
        }

        @Bean
        @Qualifier("slow")
        public DeliveryPort slowC() {
            return new DemoDelivery("slow-c");
        }

        @Bean
        public Router router(
                @Qualifier("fast") List<DeliveryPort> fast,
                @Qualifier("slow") DeliveryPort slow) {
            return new Router(fast, slow);
        }
    }

    public static void main(String[] args) {
        try (AnnotationConfigApplicationContext context =
                     new AnnotationConfigApplicationContext(AppConfig.class)) {
            Router router = context.getBean(Router.class);

            System.out.println("TYPE_COUNT "
                    + context.getBeanNamesForType(DeliveryPort.class).length);
            System.out.println("FAST_NAMES " + router.fastNames());
            System.out.println("FAST_COUNT " + router.fastCount());
            System.out.println("SLOW_NAME " + router.slowName());
            System.out.println("SLOW_RESULT "
                    + router.deliverSlow("PING"));
            System.out.println("SAME_ROUTER "
                    + (router == context.getBean(Router.class)));
        }
    }
}
~~~

Điểm quan trọng: `@Qualifier("fast")` trên **hai `@Bean` methods** tạo metadata cho hai beans cùng nhóm. `@Qualifier("fast")` ở tham số `List<DeliveryPort>` của factory method `router` lọc ra đúng hai bean. `Router` là Java class không import Spring, còn quyết định wiring nằm ở configuration.

### 4.3. Lệnh chạy

Từ thư mục `qualifier-filter-demo`:

~~~bash
mvn -version
mvn -q compile exec:java
~~~

Trong ví dụ này, `maven.compiler.release=17` dùng trình biên dịch Java tương thích release 17. Nếu dùng `javac/java` trực tiếp thì cần classpath đầy đủ gồm Spring và dependencies; Maven giúp xử lý classpath và chạy main.

**Stdout từ `System.out.println` theo đúng thứ tự:**

~~~text
TYPE_COUNT 3
FAST_NAMES [fast-a, fast-b]
FAST_COUNT 2
SLOW_NAME slow-c
SLOW_RESULT slow-c:PING
SAME_ROUTER true
~~~

`mvn -version` cũng in phiên bản Maven/JDK; Maven có thể in log và tải dependency. Khối trên **chỉ mô tả output ứng dụng chủ động in**, không khẳng định terminal không có log khác.

### 4.4. Giải thích kết quả

1. Khi `AnnotationConfigApplicationContext(AppConfig.class)` refresh, Spring đăng ký ba bean `DeliveryPort` là `fastA`, `fastB`, `slowC`, cùng bean `Router`.
2. `getBeanNamesForType(DeliveryPort.class)` có độ dài 3. Đây là đếm **theo type**, chưa áp qualifier.
3. Factory method `router(...)` nhận `List<DeliveryPort> fast` với qualifier `"fast"`. Spring cung cấp cả `fastA` và `fastB`; vì vậy `FAST_COUNT 2`.
4. `Router.fastNames()` sắp xếp các code trước khi in, để stdout không phụ thuộc thứ tự container duyệt bean cùng nhóm: `[fast-a, fast-b]`.
5. Tham số đơn `@Qualifier("slow") DeliveryPort slow` sau lọc chỉ còn `slowC`, nên `SLOW_NAME slow-c`.
6. `deliverSlow("PING")` dùng reference đã nhận để trả `slow-c:PING`, không yêu cầu container chọn lại candidate ở mỗi lần gọi.
7. `Router` là singleton theo mặc định trong một context; lookup hai lần trả cùng object, nên `SAME_ROUTER true`.

Đầu ra không có println trong factory methods/constructor, tránh phụ thuộc thứ tự tạo singleton không liên quan. `List.copyOf` bảo vệ field list khỏi bị sửa từ bên ngoài, nhưng không tự làm mỗi `DeliveryPort` immutable/thread-safe.

## 5. Ví dụ Java 17 thuần: filtering và injection là hai khâu khác nhau

Để nhìn rõ ý tưởng lọc, có thể thử một ví dụ **không dùng Spring**. Đây **không phải** Spring qualifier resolution; Java code chủ động lọc theo tag để mô phỏng cơ chế chọn.

Tạo `CandidateFilter.java`:

~~~java
import java.util.List;

public final class CandidateFilter {
    public record Candidate(String beanName, String type, String tag) {}

    public static void main(String[] args) {
        List<Candidate> beans = List.of(
            new Candidate("fastA", "Channel", "fast"),
            new Candidate("fastB", "Channel", "fast"),
            new Candidate("slowC", "Channel", "slow"),
            new Candidate("formatA", "Formatter", "fast")
        );

        List<String> matches = beans.stream()
            .filter(b -> b.type().equals("Channel"))
            .filter(b -> b.tag().equals("fast"))
            .map(Candidate::beanName)
            .sorted()
            .toList();

        System.out.println("MATCHES " + matches);
        System.out.println("COUNT " + matches.size());
        System.out.println("UNIQUE " + (matches.size() == 1));
    }
}
~~~

Tại thư mục chứa file:

~~~bash
javac --release 17 -encoding UTF-8 CandidateFilter.java
java CandidateFilter
~~~

**Stdout chính xác:**

~~~text
MATCHES [fastA, fastB]
COUNT 2
UNIQUE false
~~~

Hai bước filter mô phỏng rằng `formatA` cùng nhãn fast nhưng **khác type** không được chọn, còn hai Channel cùng nhãn fast vẫn tồn tại sau lọc. Trong Spring thực tế, các type còn có inheritance, generic metadata, qualifiers và nhiều rule candidate resolution khác; code này chỉ dùng để củng cố ý tưởng **type first, qualifier narrowing**.

## 6. `@Primary` và `@Qualifier` phối hợp thế nào?

`@Primary` là một quy tắc ưu tiên khi Spring cần chọn **một bean** trong nhiều ứng viên. `@Qualifier` giới hạn đối tượng được xét. Không nên hiểu `@Primary` là cơ chế bỏ qua mọi qualifier.

Ví dụ giả định:

- `fastA` và `fastB` mang qualifier `fast`.
- `slowC` mang qualifier `slow` và được đánh dấu `@Primary`.

Nếu injection point yêu cầu `@Qualifier("fast") DeliveryPort`, Spring **không chọn slowC chỉ vì slowC là primary**, bởi slowC không thỏa qualifier yêu cầu.

Còn nếu đánh dấu `fastA` làm primary duy nhất trong nhóm `fast`, Spring có thể chọn `fastA` cho dependency đơn có qualifier fast (khi không có điều kiện khác). Nhưng với `@Qualifier("fast") List<DeliveryPort>`, **cả fastA và fastB vẫn phù hợp để xuất hiện trong collection**; primary không tự biến bộ lọc thành chọn một phần tử.

~~~java
// Biến thể minh họa, không thêm đồng thời vào file runnable:
// @Bean
// @Primary
// @Qualifier("fast")
// DeliveryPort fastA() { return new DemoDelivery("fast-a"); }
~~~

Cần import `org.springframework.context.annotation.Primary` nếu áp dụng thật. Đừng dùng `@Primary` để giải quyết logic chọn adapter **theo dữ liệu runtime** của mỗi giao dịch; đó là thiết kế strategy/router nghiệp vụ, không phải bean candidate resolution.

### Khi cả nhóm không có ứng viên

`@Qualifier("missing") DeliveryPort` không tạo bean mới. Với injection point required thông thường, Spring báo lỗi thiếu bean phù hợp. Đối với `List<DeliveryPort>` required trên field/method, thiếu phần tử phù hợp cũng có thể dẫn tới lỗi; ở một số đường injection qua constructor/factory method, Spring có quy tắc đặc biệt cho multi-element arguments. Vì vậy nếu nhóm có thể rỗng, hãy thiết kế/test theo phiên bản và signature thực tế thay vì tự tin Spring luôn trả list rỗng.

## 7. Lọc `List`, `Set`, `Map`, array

Spring hỗ trợ injection theo type cho typed collections và arrays. Qualifier có thể giới hạn những bean lọt vào nhóm.

~~~java
@Autowired
public void configure(
        @Qualifier("fast") List<DeliveryPort> fastPorts,
        @Qualifier("slow") DeliveryPort slowPort) {
    this.fastPorts = fastPorts;
    this.slowPort = slowPort;
}
~~~

Đây là ví dụ minh họa chưa độc lập; các field/interface cần được định nghĩa. Các hình thức tương tự có thể là:

- `Set<DeliveryPort>`: nhóm beans phù hợp, không phụ thuộc vào thứ tự ngẫu nhiên khi sử dụng.
- `DeliveryPort[]`: array các ứng viên phù hợp.
- `Map<String, DeliveryPort>`: key thông thường là bean name, value là bean instance phù hợp; qualifier cũng có thể thu hẹp candidates theo những điều kiện resolution tương ứng.
- `List<DeliveryPort>`: có thể giữ order theo `@Order`/`Ordered` cho injection theo nhóm, nếu có quy tắc order được khai báo. Không dùng thứ tự ngẫu nhiên của component scan làm logic.

Một qualifier **có thể khớp nhiều beans**, nên phù hợp tự nhiên với chain handlers, batch processors, multiple notifications hoặc các chiến lược cùng một vai trò.

### Phân biệt group filtering và strategy runtime

Inject danh sách “mọi kênh fast” là **cấu hình thành phần** tại lúc Spring lắp bean graph. Nếu use case cần chọn “fast hay slow” dựa trên yêu cầu người dùng trong mỗi lần gọi, logic đó thuộc service/router runtime. `@Qualifier` không đánh giá nội dung request để tự chuyển bean.

## 8. Custom qualifier mang ý nghĩa nghiệp vụ

Một chuỗi `@Qualifier("fast")` dễ dùng, nhưng string rải nhiều nơi có thể khó đổi tên. Khi một nhãn là quy ước quan trọng, có thể tạo annotation riêng.

Ví dụ file `Fast.java`:

~~~java
package demo;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import org.springframework.beans.factory.annotation.Qualifier;

@Target({ElementType.TYPE, ElementType.METHOD,
         ElementType.FIELD, ElementType.PARAMETER})
@Retention(RetentionPolicy.RUNTIME)
@Qualifier
public @interface Fast {}
~~~

Đây là **file annotation minh họa**, không được thêm vào project runnable ở mục 4. Có thể đặt `@Fast` trên candidate bean/class và trên injection point. Spring sẽ xem annotation đó như qualifier metadata, không phải một method được tự gọi.

Cũng có thể định nghĩa một annotation có thuộc tính, ví dụ `@Region("EMEA")`:

~~~java
@Target({ElementType.TYPE, ElementType.METHOD,
         ElementType.FIELD, ElementType.PARAMETER})
@Retention(RetentionPolicy.RUNTIME)
@Qualifier
public @interface Region {
    String value();
}
~~~

Đây là minh họa cần imports giống `Fast.java`. Khi đặt `@Region("EMEA")` và `@Region("APAC")` lên các beans phù hợp, injection point mang `@Region("EMEA")` sẽ lọc theo giá trị cụ thể.

**Lưu ý:** không nhầm Spring meta `@Qualifier` với `jakarta.inject.Qualifier`; cả hai đều có thể liên quan qualifier tùy chỉnh trong một số cấu hình, nhưng package và cơ chế framework cần được nhận biết. Bài này tập trung **Spring `@Qualifier`**.

### Dùng XML bean definitions

Với XML, có thể gắn metadata qualifier trực tiếp:

~~~xml
<bean id="fastGateway" class="demo.FastGateway">
    <qualifier value="fast"/>
</bean>
~~~

Đây là **đoạn XML minh họa**, không chạy độc lập; cần class và XML root/schema hợp lệ. Spring xét qualifier metadata khi giải quyết dependency qua annotation. Không nhầm XML `<qualifier>` với Java method `setQualifier` trên bean; nó là metadata của bean definition.

## 9. Injection theo tên và sự khác biệt với `@Resource`

Spring có fallback matching theo bean name hoặc alias trong quá trình type-driven resolution khi không có chỉ dẫn mạnh hơn như qualifier/primary/fallback. Trên Spring 6.1+, matching dựa **tên tham số Java** đòi thông tin tên tham số được giữ lại khi compile, thường dùng tùy chọn `-parameters`; Spring 6.2 còn tối ưu shortcut cho name matching trong một số trường hợp.

Vì vậy code:

~~~java
public Sender(DeliveryPort fastA) {
    this.gateway = fastA;
}
~~~

có thể chọn bean tên `fastA` khi có nhiều `DeliveryPort` phù hợp và không có metadata ưu tiên khác, **nếu** thông tin tên tham số được giữ lại và các rule resolution thỏa. Không nên dựa vào việc này khi yêu cầu nghiệp vụ thực tế cần một vai trò cụ thể: `@Qualifier("fast")` hoặc qualifier custom có ý nghĩa rõ và ít phụ thuộc tên biến Java hơn.

`@Resource(name="fastA")` đến từ Jakarta Annotations (JSR-250, package `jakarta.annotation`), là cách lookup thiên về tên bean và có quy tắc riêng. Nó phù hợp hơn khi mục tiêu rõ là lấy một object theo name, nhưng `@Resource` không có cùng phạm vi áp dụng như `@Autowired` trên constructor/method nhiều tham số; cần phân biệt.

## 10. Các sai lầm thường gặp

| Hiểu nhầm / lỗi | Giải thích / cách khắc phục |
| --- | --- |
| “`@Qualifier("fast")` luôn chọn đúng một bean.” | Nó lọc tập bean theo type; có thể còn hai bean fast. |
| “Qualifier là một ID tuyệt đối, bất kể type.” | Type-driven selection vẫn áp dụng; qualifier không làm bean sai type hợp lệ. |
| “Một qualifier chỉ được dùng trên một bean.” | Nhiều beans có thể cùng qualifier, đặc biệt để inject collection. |
| “Gắn `@Qualifier` lên parameter là đủ dù bean chưa đăng ký.” | Bean phải tồn tại và mang type/metadata phù hợp. |
| “`@Primary` luôn thắng mọi qualifier.” | Primary không cho phép chọn bean không thỏa qualifier. |
| “`@Primary` trên một bean fast làm List fast chỉ còn bean đó.” | Collection có thể nhận tất cả candidates thỏa qualifier. |
| “Gắn `@Qualifier` lên method business làm method tự chạy.” | Annotation có ý nghĩa trên bean definition/injection point phù hợp, không gọi business logic. |
| “`@Qualifier` và `jakarta.inject.Qualifier` là một.” | Spring annotation nhận String; Jakarta annotation thường là meta-annotation. |
| “Tên parameter trùng bean name luôn đủ để autowire.” | Có điều kiện metadata và cần `-parameters` trên Spring 6.1+ cho name match. |
| “Không bean fast thì list injection luôn nhận [] mà không lỗi.” | Còn phụ thuộc đường injection/required semantics; phải test đúng signature. |
| “Inject mọi bean là thực thi tất cả bean mỗi request.” | Injection là wiring; gọi business methods cần code chủ động. |
| “Qualifier giải quyết transaction/HTTP route/đa luồng.” | Nó chỉ ảnh hưởng candidate selection, không tự thêm hạ tầng khác. |
| “Bean name fallback biến `@Autowired` thành `@Resource`.” | Semantics khác; `@Autowired` vẫn lọc type trước. |
| “Thứ tự quét package xác định implementation được chọn.” | Không dựa vào thứ tự scan; dùng rule rõ. |

### Chẩn đoán khi ứng dụng không tạo được context

- `NoSuchBeanDefinitionException` hoặc `UnsatisfiedDependencyException`: có thể thiếu type/qualifier match. Kiểm tra bean definitions, component scanning và `@Bean` names.
- `NoUniqueBeanDefinitionException`: sau filtering vẫn nhiều candidates cho **single-valued injection point**; cần qualifier cụ thể hơn, một primary phù hợp hoặc thay kiến trúc injection.
- `BeanCreationException`: bean candidate phù hợp nhưng constructor/factory/initialization thất bại; `@Qualifier` không tự nuốt lỗi.
- Sai import `Qualifier`: kiểm tra package `org.springframework.beans.factory.annotation.Qualifier`, không copy cú pháp String sang `jakarta.inject.Qualifier`.
- Lỗi thiếu nguyên nhóm sau khi cấu hình `@Qualifier("fast") List<Port>`: kiểm tra bean thực sự mang metadata fast, tên/aliases và cơ chế injection đúng.

**Cách debug hiệu quả:** trước tiên liệt kê candidates cùng interface; sau đó xem từng metadata qualifier và injection point; cuối cùng xác định target cần một bean hay một nhóm. Đừng xử lý lỗi mơ hồ bằng cách đánh dấu mọi implementation là primary.

## 11. Bài tập có đáp án

**1.** Spring có hai `DeliveryPort` mang qualifier fast. Inject `@Qualifier("fast") DeliveryPort` có chắc chắn chọn một không?

**Đáp án:** Không. Nếu sau lọc còn hai ứng viên và không có thêm quy tắc chọn, single-valued injection có thể mơ hồ.

**2.** Với cùng cấu hình, inject `@Qualifier("fast") List<DeliveryPort>` nhận gì?

**Đáp án:** Cả hai bean fast, khi chúng phù hợp type và metadata.

**3.** Một bean `Formatter` mang qualifier fast có vào `List<DeliveryPort>` với qualifier fast không?

**Đáp án:** Không, nếu Formatter không phải một DeliveryPort. Qualifier lọc **sau type matching**, không thay type.

**4.** Nếu `slowC` là `@Primary` nhưng injection yêu cầu qualifier fast, slowC có được chọn không?

**Đáp án:** Không chỉ vì primary; nó không thỏa qualifier fast.

**5.** Nếu gắn `@Primary` lên fastA nhưng giữ hai bean fast, `List<DeliveryPort>` qualifier fast còn fastB không?

**Đáp án:** Có, primary dùng để ưu tiên một candidate khi injection đơn, không tự loại bean khác khỏi group.

**6.** `@Qualifier("fastA")` có thể match bean tên fastA chưa gắn qualifier cùng tên không?

**Đáp án:** Trong Spring có bean name fallback trong tập beans type-compatible; nhưng đó vẫn là narrowing theo type, không phải lookup bean ID tuyệt đối.

**7.** Tại sao ví dụ runnable sắp xếp tên trước khi in?

**Đáp án:** Vì không muốn output phụ thuộc thứ tự Spring trả ứng viên; sort bảo đảm `[fast-a, fast-b]`.

**8.** Trong ví dụ, vì sao `FAST_COUNT 2` nhưng `TYPE_COUNT 3`?

**Đáp án:** TYPE_COUNT đếm cả ba bean đúng type; FAST_COUNT đếm các bean còn lại sau qualifier fast.

**9.** Vì sao không dùng `@Resource` thay thế hoàn toàn `@Qualifier`?

**Đáp án:** `@Resource` có semantics và injection targets khác, thường nhấn mạnh tên, không phải công cụ thay thế trực tiếp qualifier lọc groups trong constructor hay multi-arg method.

**10.** Một qualifier string thay đổi nhiều lần, làm sao giảm rủi ro typo?

**Đáp án:** Có thể định nghĩa custom meta-annotated qualifier như `@Fast` hoặc `@Region`, và dùng nhất quán trên candidate/injection point.

## 12. Checklist áp dụng

- [ ] Hiểu `@Qualifier` là điều kiện **lọc trong tập bean đúng type**.
- [ ] Biết rõ injection point cần **một bean** hay **collection**.
- [ ] Bean candidates đã được đăng ký bằng `@Bean`, component scan hoặc registry.
- [ ] Đã gắn qualifier metadata cho bean ứng viên phù hợp.
- [ ] `@Qualifier` được dùng đúng package Spring khi viết dạng String.
- [ ] Mỗi injection parameter có type/qualifier rõ ràng nếu nhiều beans.
- [ ] Không tự cho rằng một qualifier được dùng tối đa một lần.
- [ ] Không dựa vào thứ tự khai báo để chọn một ứng viên.
- [ ] Hiểu sự khác nhau giữa `@Primary` và qualifier filtering.
- [ ] Chỉ sử dụng bean name fallback khi đã hiểu điều kiện matching.
- [ ] Không đánh đồng Spring `@Qualifier` với Jakarta `@Qualifier`.
- [ ] Khi tạo custom qualifier, sử dụng runtime retention và target phù hợp.
- [ ] Test một ứng viên, nhiều ứng viên cùng qualifier và trường hợp thiếu.
- [ ] Nếu inject danh sách/map, kiểm soát order hoặc sort nếu output cần xác định.
- [ ] Giữ lựa chọn runtime theo business data trong service/router, không giấu ở annotation.
- [ ] Không dùng `@Qualifier` như giải pháp cho lỗi transaction, lifecycle hay concurrency.

### Nguồn tham khảo chính thức

- [Spring — Fine-tuning Annotation-based Autowiring with Qualifiers](https://docs.spring.io/spring-framework/reference/core/beans/annotation-config/autowired-qualifiers.html)
- [Spring — Using `@Autowired`](https://docs.spring.io/spring-framework/reference/core/beans/annotation-config/autowired.html)
- [Spring — Using Generics as Autowiring Qualifiers](https://docs.spring.io/spring-framework/reference/core/beans/annotation-config/generics-as-qualifiers.html)

**Kết luận:** `@Qualifier` của Spring thu hẹp **những bean cùng khớp kiểu** dựa trên nhãn hoặc metadata cần thiết. Nếu cần một bean thì lọc xong vẫn phải còn ứng viên duy nhất (hoặc có rule chọn thêm); nếu cần `List`/`Set`, nhiều bean mang cùng qualifier có thể được nhận đồng thời. Đây là điểm khác biệt giữa **lọc tập ứng viên** và **lookup chính xác một bean name**, và là cơ sở để thiết kế DI dễ mở rộng mà không lựa chọn implementation theo thứ tự ngẫu nhiên.