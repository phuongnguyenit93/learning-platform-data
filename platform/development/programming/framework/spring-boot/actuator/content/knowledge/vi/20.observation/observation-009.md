# Sử dụng @Observed cùng cơ chế aspect khi cần quan sát phương thức

## 1. Quan sát một thao tác nghiệp vụ có nghĩa là gì?

Giả sử ứng dụng đã đo được thời gian xử lý HTTP, nhưng bạn cần biết riêng thao tác tính giá chạy bao nhiêu lần, mất bao lâu và có phát sinh ngoại lệ hay không. Ranh giới HTTP bao gồm nhiều công việc; một phép đo tại phương thức nghiệp vụ giúp nhìn rõ phần tính giá trong toàn bộ yêu cầu.

`@Observed` thuộc Micrometer, có tên đầy đủ là `io.micrometer.observation.annotation.Observed`. Annotation này khai báo rằng một phương thức hoặc các phương thức phù hợp của một lớp cần được bao quanh bởi một lần quan sát (`Observation`). Nó không tự chạy logic đo đạc.

Các thành phần phối hợp như sau:

| Thành phần | Vai trò trong lời gọi |
| --- | --- |
| `@Observed` | Cung cấp tên và các nhãn mô tả thao tác |
| `ObservedAspect` | Chặn lời gọi phù hợp, quản lý vòng đời observation và gọi phương thức thật |
| Proxy của Spring AOP | Đối tượng trung gian mà bên gọi phải đi qua để aspect được thực thi |
| `ObservationRegistry` | Giữ cấu hình observation, các bộ xử lý và ngữ cảnh quan sát hiện tại |
| `ObservationHandler` | Phản ứng với vòng đời observation; tùy cấu hình có thể ghi metric, tạo span hoặc xử lý sự kiện khác |

Một annotation chỉ trở thành dữ liệu quan sát khi chuỗi này được nối đúng. Handler đo metric có thể tạo `Timer`; handler truy vết có thể tạo span. Chỉ thêm `@Observed` không đồng nghĩa với việc dữ liệu đã được gửi tới Prometheus hoặc một hệ thống tracing. [Micrometer giải thích các thành phần Observation](https://docs.micrometer.io/micrometer/reference/1.13/observation/components.html).

Nên chọn một thao tác có ý nghĩa như tính giá, duyệt hồ sơ hoặc tạo báo cáo. Không cần gắn annotation lên mọi hàm phụ trợ. Nếu hệ thống đã quan sát đúng thao tác đó, hãy kiểm tra dữ liệu hiện có trước khi bổ sung một lớp đo khác.

## 2. Aspect bao quanh phương thức như thế nào?

Với phương thức đồng bộ và cấu hình thông thường, có thể hình dung luồng thực thi:

```text
Bên gọi
  -> proxy Spring AOP
     -> ObservedAspect tạo và bắt đầu observation
     -> mở scope cho lời gọi
     -> phương thức nghiệp vụ
        -> trả kết quả hoặc ném ngoại lệ
     -> ghi nhận lỗi nếu ngoại lệ thoát ra
     -> đóng scope và dừng observation
  -> trả kết quả hoặc chuyển tiếp ngoại lệ cho bên gọi
```

Scope là phạm vi mà observation được xem là hiện tại. Trong một lời gọi đồng bộ, mã chạy bên trong phạm vi đó có thể tìm observation hiện tại qua registry. Nếu đã có observation cha trong ngữ cảnh, observation mới có thể nằm dưới nó; việc biểu diễn thành cây span còn phụ thuộc cấu hình tracing.

Aspect không đổi kết quả nghiệp vụ thành một đối tượng observation. Phương thức trả `42` thì bên gọi vẫn nhận `42`; ngoại lệ nghiệp vụ thoát ra vẫn phải được bên gọi xử lý. Observation cần kết thúc cả khi thành công lẫn khi có lỗi, và scope phải được khôi phục sau lời gọi. [Vòng đời và scope trong Micrometer](https://docs.micrometer.io/micrometer/reference/1.13/observation/introduction.html).

Có hai phân biệt cần nhớ:

- Phương thức tự bắt ngoại lệ rồi trả một giá trị bình thường thì aspect không tự biết nghiệp vụ đã thất bại. Một kết quả như `false` hoặc trạng thái “từ chối” cũng không tự trở thành lỗi kỹ thuật.
- Có observation trong bộ nhớ, có metric trong registry và có dữ liệu ở hệ thống giám sát là ba mức kiểm chứng khác nhau. Không suy ra mức cuối chỉ từ việc annotation đã được nhận diện.

## 3. Tích hợp vào ứng dụng Spring Boot

### 3.1. Các điều kiện cần có

Trong ứng dụng Spring Boot 3.3.x, hãy bảo đảm:

1. Có Micrometer Observation và một `ObservationRegistry` được nối với hạ tầng Actuator.
2. Có Spring AOP và AspectJ runtime cần thiết cho aspect.
3. Có đúng một `ObservedAspect` phù hợp dùng registry của ứng dụng.
4. Phương thức thuộc bean được Spring quản lý và lời gọi đi qua proxy.

Với dự án đã áp dụng plugin/BOM của Spring Boot, phần dependency Gradle thường cần:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
    implementation 'org.springframework.boot:spring-boot-starter-aop'
}
```

Đây là phần bổ sung vào một ứng dụng Boot đã có cấu hình build, không phải toàn bộ `build.gradle`. Để Boot quản lý các phiên bản Micrometer, Spring và AspectJ tương thích; không tùy ý ghép các phiên bản riêng lẻ vào module hiện có.

### 3.2. Đăng ký aspect khi tự cấu hình

Có thể dùng cấu hình dưới đây trong phạm vi quét của ứng dụng:

```java
package example.observed;

import io.micrometer.observation.ObservationRegistry;
import io.micrometer.observation.aop.ObservedAspect;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class ObservationMethodConfig {
    @Bean
    @ConditionalOnMissingBean(ObservedAspect.class)
    ObservedAspect observedAspect(ObservationRegistry registry) {
        return new ObservedAspect(registry);
    }
}
```

Nếu ứng dụng đã có `ObservedAspect` từ cấu hình chung hoặc auto-configuration, hãy dùng bean đó. Điều kiện `@ConditionalOnMissingBean` giúp cấu hình này không chủ động thêm một bean cùng kiểu đã tồn tại. Cần kiểm tra cấu hình thực tế để tránh đăng ký nhiều aspect bằng những đường khác nhau.

Cách ví dụ này kích hoạt aspect là khai báo bean trực tiếp. Không giả định một thuộc tính cấu hình có trong mọi phiên bản Boot, hoặc chỉ đặt một thuộc tính rồi bỏ qua việc xác minh bean/proxy. Các điều kiện auto-configuration phải được đối chiếu đúng phiên bản đang chạy. [Mã cấu hình Observation của Spring Boot 3.3.5](https://raw.githubusercontent.com/spring-projects/spring-boot/v3.3.5/spring-boot-project/spring-boot-actuator-autoconfigure/src/main/java/org/springframework/boot/actuate/autoconfigure/observation/ObservationAutoConfiguration.java).

Với starter AOP và auto-configuration AOP đang bật, Boot có thể tạo proxy cho bean phù hợp. Nếu đã tắt `spring.aop.auto` hoặc thay cơ chế cấu hình AOP, phải kiểm tra lại. Trong ứng dụng Spring thuần, có thể bật proxy bằng `@EnableAspectJAutoProxy`, như chương trình thực nghiệm ở phần sau.

Hãy inject registry do Boot quản lý vào aspect. Không tạo thêm một `ObservationRegistry.create()` trong cấu hình sản phẩm chỉ để truyền cho aspect: registry riêng có thể không có các handler mà Boot đã thiết lập. Việc tạo registry thủ công ở ví dụ độc lập bên dưới nhằm thể hiện rõ từng thành phần của thí nghiệm.

### 3.3. Đánh dấu phương thức và gọi qua bean

Ví dụ tệp `PricingService.java` trong ứng dụng Boot:

```java
package example.observed;

import io.micrometer.observation.annotation.Observed;
import org.springframework.stereotype.Service;

@Service
public class PricingService {
    @Observed(name = "pricing.quote", contextualName = "calculate-price",
            lowCardinalityKeyValues = {"channel", "web"})
    public int quote(boolean fail) {
        if (fail) {
            throw new IllegalArgumentException("invalid input");
        }
        return 42;
    }
}
```

Một bean khác nhận `PricingService` qua constructor injection rồi gọi `pricingService.quote(false)`. Đó là đường gọi thích hợp để đi qua proxy. Không thay dependency được inject bằng `new PricingService()`.

Đoạn service này cần đặt trong một ứng dụng Boot đang có; nó không có `main` riêng và không tự khởi động ứng dụng. Cấu hình aspect ở trên và service phải cùng nằm trong phạm vi được Spring phát hiện.

## 4. Đặt tên và nhãn cho observation

Trong ví dụ:

```java
@Observed(name = "pricing.quote", contextualName = "calculate-price",
        lowCardinalityKeyValues = {"channel", "web"})
```

- `name` là tên kỹ thuật ổn định của observation, phù hợp cho việc gom nhóm số liệu.
- `contextualName` mô tả thao tác theo ngữ cảnh, hữu ích khi handler tracing tạo tên span. Nó không phải tên thay thế cho metric.
- `lowCardinalityKeyValues` gồm các cặp khóa–giá trị liên tiếp: `"channel", "web"`. Số phần tử phải chẵn.
- Aspect mặc định còn cung cấp các nhãn như `class` và `method`; cần tính cả những nhãn này khi phân tích các chuỗi số liệu.

Nhãn có số lượng giá trị hữu hạn (`low cardinality`) nên mô tả những nhóm ổn định: kênh gọi, loại thao tác hoặc nhóm kết quả đã chuẩn hóa. Mỗi tổ hợp nhãn có thể tạo thêm một chuỗi số liệu. Không dùng mã đơn hàng, UUID, địa chỉ email, token hay nội dung yêu cầu làm nhãn metric.

Giá trị trong annotation là hằng chuỗi Java. Viết `"channel", "#channel"` không tự khiến `@Observed` đọc tham số `channel` bằng SpEL; khi không có cơ chế mở rộng riêng, đó là giá trị chuỗi được khai báo.

Khi cần nhãn dựa trên dữ liệu lúc chạy hoặc một phạm vi đo nhỏ hơn toàn bộ phương thức, cân nhắc Observation API thủ công hoặc convention phù hợp. Ví dụ minh họa trong một phương thức đã có các biến cần thiết:

```java
return Observation.createNotStarted("pricing.quote", registry)
        .lowCardinalityKeyValue("channel", normalizedChannel)
        .observe(() -> calculatePrice(input));
```

Ở đây `registry`, `normalizedChannel`, `input` và `calculatePrice` là các thành phần của mã nghiệp vụ bao quanh, không phải một chương trình độc lập. `normalizedChannel` phải được chuẩn hóa thành một tập giá trị có giới hạn.

Trong hạ tầng Boot thông thường, nhãn ít giá trị được dùng cho metric và trace; nhãn nhiều giá trị không được chuyển thành nhãn metric bởi handler metric mặc định. Điều đó không làm dữ liệu nhạy cảm trở nên phù hợp để thu thập. [Phân biệt nhãn trong Spring Boot Observability](https://docs.spring.io/spring-boot/3.3/reference/actuator/observability.html).

## 5. Giới hạn của proxy và các trường hợp dễ hiểu sai

### 5.1. Gọi nội bộ không đi qua aspect

Nếu cùng một đối tượng gọi `this.quote(false)`, lời gọi đi thẳng vào đối tượng thật. Annotation trên `quote` không được chặn lần nữa chỉ vì phương thức đó có annotation.

```java
public int forward() {
    return this.quote(false);
}
```

Nếu bên ngoài gọi `forward()` qua proxy nhưng `forward` không được quan sát, còn `quote` chỉ được gọi qua `this`, sẽ không có observation cho `quote`. Nếu `forward` cũng được quan sát, observation của `forward` vẫn không chứng minh rằng lời gọi nội bộ vào `quote` đã được aspect chặn riêng.

Cách xử lý thường rõ ràng nhất là tách thao tác cần quan sát sang một bean khác và inject bean đó. Nếu chỉ cần quan sát một khối bên trong phương thức, dùng API thủ công cho khối ấy. Tránh thay đổi thiết kế chỉ để truy cập proxy bằng mẹo gọi vòng.

### 5.2. Loại phương thức và loại proxy có ảnh hưởng

| Trường hợp | Điều cần kiểm tra |
| --- | --- |
| Đối tượng tạo trực tiếp bằng `new` | Thông thường không có proxy; annotation không tự có tác dụng |
| Phương thức `private` hoặc `static` | Không phải lời gọi được Spring AOP proxy chặn theo cách này |
| Lớp `final` khi dùng proxy lớp | CGLIB không thể tạo lớp con để làm proxy |
| Phương thức `final` khi dùng proxy lớp | Không thể override để chặn bằng CGLIB |
| Proxy JDK | Lời gọi được chặn qua interface mà proxy cung cấp; không áp nguyên xi giới hạn override của CGLIB |
| Gọi trong constructor hoặc quá sớm trong khởi tạo | Không giả định đối tượng đã sẵn sàng được gọi qua proxy |

Để bắt đầu, dùng phương thức `public`, không `final`, trên lớp không `final`, đặt annotation trực tiếp trên phương thức triển khai và gọi qua bean được inject. Cách này giảm các khác biệt khó nhìn thấy do kiểu proxy. Annotation ở cấp lớp cũng chịu các giới hạn chặn lời gọi; nó không làm mọi lời gọi nội bộ trở thành lời gọi qua proxy. [Spring Framework giải thích proxy và self-invocation](https://docs.spring.io/spring-framework/reference/core/aop/proxying.html).

### 5.3. Bất đồng bộ và reactive cần kiểm chứng riêng

Không áp dụng máy móc sơ đồ đồng bộ cho mọi kiểu trả về. `ObservedAspect` trong Micrometer 1.13.0 có xử lý riêng cho phương thức khai báo trả về `CompletionStage`: observation được kết thúc khi stage hoàn tất. Điều này khác việc chỉ đo đến lúc phương thức trả một đối tượng future.

Tuy vậy, không suy ra rằng observation hiện tại tự được truyền tới mọi thread hoặc mọi callback. Với `@Async`, thứ tự aspect và ranh giới đổi thread cũng ảnh hưởng phạm vi quan sát.

Tương tự, một phương thức trả `Mono` hoặc `Flux` có thể chỉ tạo một chuỗi xử lý chưa được thực thi. Không dùng sự có mặt của `@Observed` làm bằng chứng rằng toàn bộ subscription, lỗi và hủy đã được đo đúng. Cần dùng tích hợp Reactor/Observation và kiểm thử tương ứng với thư viện đang dùng. Bài này tập trung vào phương thức đồng bộ; các ranh giới khác phải có thí nghiệm riêng.

## 6. Thực nghiệm độc lập, chạy được bằng JDK 21

Thí nghiệm sau dùng Spring Framework 6.1.8, Micrometer 1.13.0 và AspectJ 1.9.22, tương ứng thế hệ thư viện của Boot 3.3.0. Phiên bản được cố định để tái lập thí nghiệm; trong ứng dụng Boot, tiếp tục dùng dependency management của Boot.

Chương trình dùng Spring context và bean proxy nhưng không khởi động web server. Nhờ vậy, không cần một endpoint HTTP hay hệ thống giám sát bên ngoài để kiểm chứng cơ chế aspect.

### 6.1. Chuẩn bị dependency

Trong một thư mục thực nghiệm riêng, tạo `pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>observed-demo</artifactId>
    <version>1.0.0</version>
    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.1.8</version>
        </dependency>
        <dependency>
            <groupId>org.aspectj</groupId>
            <artifactId>aspectjweaver</artifactId>
            <version>1.9.22</version>
        </dependency>
        <dependency>
            <groupId>io.micrometer</groupId>
            <artifactId>micrometer-core</artifactId>
            <version>1.13.0</version>
        </dependency>
    </dependencies>
</project>
```

`micrometer-core` kéo theo các dependency Micrometer Observation cần thiết; Maven giải quyết các dependency bắc cầu còn lại.

### 6.2. Toàn bộ chương trình ObservedDemo.java

Lưu tệp ở cùng thư mục với `pom.xml`, không khai báo package:

```java
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import io.micrometer.core.instrument.observation.DefaultMeterObservationHandler;
import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationHandler;
import io.micrometer.observation.ObservationRegistry;
import io.micrometer.observation.annotation.Observed;
import io.micrometer.observation.aop.ObservedAspect;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableAspectJAutoProxy;

public class ObservedDemo {
    public static void main(String[] args) {
        try (var context = new AnnotationConfigApplicationContext(Config.class)) {
            var service = context.getBean(PricingService.class);
            var recorder = context.getBean(Recorder.class);
            var registry = context.getBean(ObservationRegistry.class);
            var meters = context.getBean(SimpleMeterRegistry.class);

            System.out.println("raw=" + new PricingService().quote(false));
            System.out.println("after.raw=" + recorder.stops);
            System.out.println("proxied=" + service.quote(false));
            System.out.println("after.proxied=" + recorder.stops);
            System.out.println("self=" + service.forward());
            System.out.println("after.self=" + recorder.stops);

            try {
                service.quote(true);
            } catch (IllegalArgumentException ex) {
                System.out.println("error=" + ex.getClass().getSimpleName());
            }

            System.out.println("starts=" + recorder.starts);
            System.out.println("stops=" + recorder.stops);
            System.out.println("errors=" + recorder.errors);
            System.out.println("success.count=" + meters.get("pricing.quote")
                    .tag("error", "none").timer().count());
            System.out.println("failure.count=" + meters.get("pricing.quote")
                    .tag("error", "IllegalArgumentException").timer().count());
            System.out.println("current.cleared="
                    + (registry.getCurrentObservation() == null));

            if (recorder.starts != 2 || recorder.stops != 2
                    || recorder.errors != 1
                    || registry.getCurrentObservation() != null) {
                throw new AssertionError("Unexpected observation lifecycle");
            }
        }
    }

    public static class PricingService {
        @Observed(name = "pricing.quote", contextualName = "calculate-price",
                lowCardinalityKeyValues = {"channel", "demo"})
        public int quote(boolean fail) {
            if (fail) {
                throw new IllegalArgumentException("invalid input");
            }
            return 42;
        }

        public int forward() {
            return this.quote(false);
        }
    }

    public static class Recorder implements ObservationHandler<Observation.Context> {
        int starts;
        int stops;
        int errors;

        @Override
        public boolean supportsContext(Observation.Context context) {
            return "pricing.quote".equals(context.getName());
        }

        @Override
        public void onStart(Observation.Context context) {
            starts++;
        }

        @Override
        public void onStop(Observation.Context context) {
            stops++;
        }

        @Override
        public void onError(Observation.Context context) {
            errors++;
        }
    }

    @Configuration(proxyBeanMethods = false)
    @EnableAspectJAutoProxy(proxyTargetClass = true)
    public static class Config {
        @Bean
        SimpleMeterRegistry meterRegistry() {
            return new SimpleMeterRegistry();
        }

        @Bean
        Recorder recorder() {
            return new Recorder();
        }

        @Bean
        ObservationRegistry observationRegistry(
                SimpleMeterRegistry meters, Recorder recorder) {
            var registry = ObservationRegistry.create();
            registry.observationConfig()
                    .observationHandler(new DefaultMeterObservationHandler(meters))
                    .observationHandler(recorder);
            return registry;
        }

        @Bean
        ObservedAspect observedAspect(ObservationRegistry registry) {
            return new ObservedAspect(registry);
        }

        @Bean
        PricingService pricingService() {
            return new PricingService();
        }
    }
}
```

`Recorder` chỉ là bộ đếm phục vụ thí nghiệm một luồng. Nó không phải bộ thu metric dành cho ứng dụng nhiều luồng. `DefaultMeterObservationHandler` mới là thành phần nối observation với `SimpleMeterRegistry`.

### 6.3. Biên dịch và chạy trên PowerShell

Cần JDK 21 đang được chọn cho cả `javac` và `java`, cùng Maven. Lần đầu cần truy cập kho dependency:

```powershell
mvn org.apache.maven.plugins:maven-dependency-plugin:3.7.0:build-classpath "-Dmdep.outputFile=classpath.txt"
$demoClasspath = (Get-Content -Raw classpath.txt).Trim()
javac --release 21 -encoding UTF-8 -cp "$demoClasspath" ObservedDemo.java
java -cp ".;$demoClasspath" ObservedDemo
```

Chỉ chạy bước tiếp theo khi bước trước thành công. Dấu `;` trong classpath là dấu phân cách trên Windows; Linux/macOS dùng `:`.

Stdout của chương trình, không tính thông báo tải dependency của Maven:

```text
raw=42
after.raw=0
proxied=42
after.proxied=1
self=42
after.self=1
error=IllegalArgumentException
starts=2
stops=2
errors=1
success.count=1
failure.count=1
current.cleared=true
```

### 6.4. Giải thích từng kết quả

| Bằng chứng | Ý nghĩa |
| --- | --- |
| `raw=42`, `after.raw=0` | Mã nghiệp vụ vẫn chạy khi tạo trực tiếp đối tượng, nhưng không có aspect quản lý observation |
| `proxied=42`, `after.proxied=1` | Bean lấy từ context được gọi qua proxy; observation đã kết thúc và kết quả vẫn là 42 |
| `self=42`, `after.self=1` | Lời gọi nội bộ từ `forward` vào `quote` không tạo thêm observation |
| `error=IllegalArgumentException` | Ngoại lệ từ phương thức được chuyển ra cho bên gọi |
| `starts=2`, `stops=2`, `errors=1` | Hai lời gọi trực tiếp vào phương thức qua proxy đều kết thúc; một lời gọi có lỗi |
| `success.count=1`, `failure.count=1` | Handler metric tạo hai timer theo nhãn lỗi; mỗi timer ghi một lần |
| `current.cleared=true` | Sau lời gọi không còn observation hiện tại bị giữ lại trong ngữ cảnh của luồng |

Không dự đoán một giá trị thời gian cố định cho timer vì thời lượng phụ thuộc máy và lần chạy. Bài kiểm chứng số lần ghi và vòng đời thay vì gán một con số thời gian giả định.

Mỗi timer đã có số lần ghi (`count`), nên nếu chỉ cần biết số lượt của chính thao tác này, không nhất thiết phải thêm một counter nữa.

## 7. Kiểm chứng trong ứng dụng Boot thật

Thí nghiệm độc lập chứng minh cơ chế Spring proxy + Micrometer aspect. Khi đưa vào ứng dụng, vẫn cần kiểm tra đường gọi và cấu hình thực tế:

1. Lấy service từ Spring context hoặc inject vào một bean khác; không dựng service bằng `new` trong phần kiểm thử đường gọi qua proxy.
2. Xác nhận context có aspect đúng registry. Có thể dùng `AopUtils.isAopProxy(service)` để kiểm tra đối tượng có là proxy, nhưng kết quả `true` chưa chứng minh riêng `ObservedAspect` đã chạy.
3. Thực hiện một lượt thành công và một lượt ném ngoại lệ; xác nhận tên observation, nhãn, lỗi và trạng thái đã dừng.
4. Kiểm tra `MeterRegistry` để biết handler metric đã ghi dữ liệu. Với tracing, kiểm tra riêng bridge, exporter, cấu hình sampling và dữ liệu span thực tế.
5. Kiểm tra không rò scope và không đếm trùng khi thêm observation mới vào đường gọi đã có instrumentation.

Có thể dùng `micrometer-observation-test` và `TestObservationRegistry` để viết assertion về observation thay cho bộ đếm minh họa. Test phải dùng chính registry đó cho aspect và vẫn gọi qua proxy. Thư viện hỗ trợ kiểm tra tên, nhãn, lỗi, trạng thái bắt đầu/kết thúc và observation hiện tại. [Hướng dẫn kiểm thử Micrometer Observation](https://docs.micrometer.io/micrometer/reference/1.13/observation/testing.html).

Khi dùng `@SpringBootTest` hoặc test theo lát cắt, cần phân biệt cấu hình kiểm thử với cấu hình sản phẩm. Chẳng hạn, các thành phần gửi tracing và các registry xuất metric ra hệ thống bên ngoài không được tự cấu hình giống hệt lúc chạy thật; `@AutoConfigureObservability` có vai trò tùy loại kiểm thử. Không kết luận “aspect hỏng” chỉ vì không thấy dữ liệu ở hệ thống giám sát bên ngoài trong test. [Spring Boot: kiểm thử observability](https://docs.spring.io/spring-boot/3.3/reference/testing/spring-boot-applications.html).

Nếu ứng dụng web đã có Actuator HTTP endpoint và chủ động cho phép truy cập `metrics`, có thể dùng endpoint metric để kiểm tra số liệu sau khi thực sự gọi phương thức. Bản thân `@Observed` không tạo HTTP endpoint và cũng không bật việc công khai endpoint quản trị.

## 8. Lỗi thường gặp và cách khoanh vùng

| Hiện tượng | Kiểm tra và hướng xử lý |
| --- | --- |
| Có annotation nhưng không có dữ liệu quan sát | Kiểm tra aspect, AOP, bean proxy, registry và handler; không chỉ kiểm tra dependency |
| Gọi trực tiếp thì có dữ liệu, gọi từ phương thức cùng lớp thì không | Xem lại self-invocation; cân nhắc bean riêng hoặc API thủ công |
| Có proxy nhưng không thấy observation mong muốn | Proxy có thể do transaction hoặc cơ chế khác; xác minh aspect và phương thức được khớp |
| Observation chạy nhưng không thấy metric | Kiểm tra handler metric, meter registry, tên và nhãn được dùng khi tìm timer |
| Có metric nhưng không có trace ở backend | Kiểm tra hạ tầng tracing và xuất dữ liệu; đây là bước sau cơ chế annotation |
| Đếm nhiều hơn số thao tác mong đợi | Tìm aspect trùng, `@Timed` đo cùng thao tác, hoặc chồng lên instrumentation có sẵn |
| Không thấy lỗi dù nghiệp vụ bị từ chối | Phân biệt ngoại lệ thoát ra với kết quả nghiệp vụ bình thường hoặc ngoại lệ đã bị bắt |
| Số chuỗi số liệu tăng nhanh | Kiểm tra nhãn và tên metric có chứa giá trị biến động như UUID/mã đơn hàng hay không |

Một observation nghiệp vụ nằm bên trong observation HTTP có thể là chủ đích hợp lý: chúng trả lời hai câu hỏi khác nhau. Ngược lại, thêm hai cách đo cùng một ranh giới mà không có mục đích rõ ràng có thể làm dữ liệu khó diễn giải. Không cộng thời gian của các observation cha–con rồi xem đó là thời gian xử lý yêu cầu.

## 9. Bài tập tự kiểm tra

1. Chạy chương trình nguyên bản và đối chiếu đủ các dòng stdout.
2. Bỏ annotation khỏi `quote`, giữ phần gọi phương thức, rồi dự đoán số observation. Khi timer không còn được tạo, các lệnh `meters.get(...).timer()` cũng phải được bỏ hoặc thay bằng cách tìm cho phép không có kết quả; không nhầm lỗi tra timer với lỗi nghiệp vụ.
3. Thay `forward()` bằng lời gọi tới một bean tính giá riêng được inject. Kiểm tra số observation tăng như dự đoán.
4. Cho `quote(true)` bắt ngoại lệ và trả giá trị dự phòng. Giải thích vì sao aspect không tự đánh dấu lỗi nếu ngoại lệ không thoát ra.
5. Chọn một phương thức nghiệp vụ thật, đặt tên ổn định, chọn một nhãn có tập giá trị hữu hạn, rồi viết kiểm thử cho cả kết quả thành công và ngoại lệ.

Sau mỗi thay đổi, lý giải bằng đường đi của lời gọi qua proxy và vòng đời observation, thay vì chỉ nhìn annotation trong mã nguồn.
