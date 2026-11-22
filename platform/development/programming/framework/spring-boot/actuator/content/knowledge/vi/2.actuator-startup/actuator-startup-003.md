# Nhận diện các thành phần được cấu hình tự động theo classpath và bean

## 1. Vì sao cùng thêm Actuator nhưng kết quả lại khác nhau?

Hai ứng dụng cùng khai báo `spring-boot-starter-actuator` nhưng có thể nhận những bean khác nhau:

- Ứng dụng thứ nhất chỉ cần đo số liệu trong bộ nhớ.
- Ứng dụng thứ hai có thêm thư viện xuất số liệu sang Prometheus.
- Ứng dụng thứ ba tự khai báo một nơi ghi nhận số liệu.
- Một ứng dụng web có các thành phần đưa endpoint ra HTTP; ứng dụng không có web không có cùng các thành phần đó.

Spring Boot không tạo một danh sách bean cố định chỉ vì nhìn thấy tên starter. **Cấu hình tự động (auto-configuration)** lựa chọn những cấu hình phù hợp với thư viện, bean, thuộc tính và môi trường ứng dụng.

Để đọc được hành vi này, cần phân biệt:

| Khái niệm | Câu hỏi nó trả lời |
| --- | --- |
| `Classpath` | Lúc chạy, ứng dụng có thể tìm và nạp những lớp/thư viện nào? |
| `Bean` | Đối tượng hoặc định nghĩa đối tượng nào đã được đăng ký để Spring quản lý? |
| `ApplicationContext` | Spring đang quản lý các bean và cấu hình trong ngữ cảnh nào? |
| Điều kiện cấu hình | Với những đầu vào hiện có, cấu hình hoặc phương thức tạo bean này có được áp dụng không? |
| Báo cáo điều kiện | Vì sao cấu hình được chọn hoặc bị bỏ qua? |

Mục tiêu bài này là nhận ra **thành phần nào được tạo, đầu vào nào làm nó được tạo và bằng chứng nào xác nhận điều đó**. Không cần ghi nhớ toàn bộ lớp cấu hình của Actuator.

## 2. Mô hình từ thư viện đến bean

Có thể hình dung quá trình theo sơ đồ sau:

~~~text
Thư viện ở runtime classpath
           +
Các bean/định nghĩa bean đã được Spring nhận diện
           +
Thuộc tính và loại ứng dụng
           ↓
Đánh giá điều kiện của cấu hình tự động
           ↓
Đăng ký những bean phù hợp
           ↓
Khởi tạo, kết nối và sử dụng các bean
~~~

Đây là mô hình để đọc quan hệ điều kiện, không phải mô tả rằng mọi loại điều kiện luôn được đánh giá tại cùng một thời điểm.

Spring Boot kích hoạt cấu hình tự động qua `@EnableAutoConfiguration` hoặc `@SpringBootApplication`. Các ứng viên cấu hình tự động được thư viện đăng ký theo cơ chế của Boot; không cần đặt các package của Boot dưới package ứng dụng để component scan tìm chúng. Xem [Spring Boot 3.3 — Auto-configuration](https://docs.spring.io/spring-boot/3.3/reference/using/auto-configuration.html).

### 2.1. Class có mặt khác với bean có mặt

Ví dụ thư viện có lớp `SimpleMeterRegistry` nghĩa là mã ứng dụng có thể sử dụng kiểu đó. Nó chưa có nghĩa Spring đã quản lý một đối tượng thuộc kiểu đó.

Câu lệnh sau chỉ tạo một đối tượng Java cục bộ:

~~~java
SimpleMeterRegistry registry = new SimpleMeterRegistry();
~~~

Đây là đoạn minh họa bên trong một phương thức, cần import kiểu tương ứng; đối tượng chưa được đăng ký thành bean chỉ vì được tạo bằng `new`.

Ngược lại, một phương thức `@Bean` trong cấu hình được Spring nạp có thể đăng ký đối tượng trả về vào context:

~~~java
@Bean
public SimpleMeterRegistry manualRegistry() {
    return new SimpleMeterRegistry();
}
~~~

Đoạn này cần đặt trong một lớp cấu hình được nạp và có các import thích hợp. Phần thực nghiệm phía dưới cung cấp tệp Java hoàn chỉnh.

### 2.2. Tên lớp cấu hình, tên bean và kiểu bean

Ba định danh thường xuất hiện cùng nhau nhưng không tương đương:

~~~text
SimpleMetricsExportAutoConfiguration → lớp cấu hình tự động
simpleMeterRegistry                 → tên một bean do cấu hình tạo
SimpleMeterRegistry                 → kiểu của đối tượng bean đó
~~~

Khi một điều kiện xét kiểu `MeterRegistry`, một bean `SimpleMeterRegistry` có thể đáp ứng vì nó thuộc hệ kiểu đó. Tên bean không cần giống tên lớp.

Trong báo cáo, dạng `SomeAutoConfiguration#someBean` chỉ đến một phương thức tạo bean. Một cấu hình khớp điều kiện chưa có nghĩa mọi phương thức bên trong cũng khớp: phương thức có thể có điều kiện riêng.

## 3. Đọc các điều kiện quan trọng

### 3.1. ConditionalOnClass: có thư viện cần thiết không?

`@ConditionalOnClass` kiểm tra sự hiện diện của những lớp được chỉ định trên classpath. Nó không tự tạo bean thuộc các lớp đó.

Ví dụ cách đọc:

~~~text
Điều kiện yêu cầu ObservationRegistry có trên classpath
→ Có lớp: tiếp tục xét cấu hình
→ Thiếu lớp: không áp dụng nhánh cấu hình đó
~~~

Cần xem **runtime classpath của đúng ứng dụng**, không chỉ danh sách import trong IDE hoặc dependency của phía kiểm thử. Một dependency chỉ có khi kiểm thử không bảo đảm tồn tại lúc chạy ứng dụng chính.

Một lớp có mặt cũng chưa đủ nếu cấu hình còn đòi hỏi bean, thuộc tính hoặc môi trường khác. Xem [ConditionalOnClass API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnClass.html).

### 3.2. ConditionalOnBean: đã có thành phần để phối hợp chưa?

`@ConditionalOnBean` yêu cầu Spring đã nhận diện bean đáp ứng các tiêu chí của điều kiện. Tiêu chí có thể dựa trên kiểu, tên hoặc annotation, tùy khai báo.

Chẳng hạn, một khả năng kiểm tra cơ sở dữ liệu cần một `DataSource` được Spring quản lý để biết kiểm tra nguồn dữ liệu nào. Chỉ thêm một JDBC driver không tự chứng minh context có `DataSource`.

Điều kiện bean được đánh giá theo những định nghĩa đã được xử lý tại thời điểm đó. Thứ tự cấu hình và phạm vi tìm kiếm context vì thế có thể quan trọng. Không nên tự chép điều kiện này vào các lớp tùy ý rồi coi nó là phép kiểm tra “sau khi mọi thứ đã khởi tạo”. Xem [ConditionalOnBean API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnBean.html).

### 3.3. ConditionalOnMissingBean: dùng mặc định khi ứng dụng chưa cung cấp

`@ConditionalOnMissingBean` thường giúp Boot cung cấp một bean mặc định mà vẫn cho ứng dụng tự quyết định.

Cách đọc cho một điều kiện xét kiểu:

~~~text
Ứng dụng chưa có bean kiểu cần tìm
→ cấu hình mặc định có thể được áp dụng nếu các điều kiện khác cũng đạt

Ứng dụng đã có bean kiểu cần tìm
→ nhánh mặc định có điều kiện missing-bean sẽ bị bỏ qua
~~~

Cơ chế **nhường cấu hình (back off)** này không xóa bean ứng dụng đã khai báo. Nó cũng không có nghĩa mọi cấu hình tự động đều bị tắt.

Khi đọc điều kiện thực tế, kiểm tra nó xét **kiểu hay tên** và xét trong context nào. Một bean đổi tên vẫn có thể làm điều kiện theo kiểu không còn khớp. Ngược lại, điều kiện theo tên có hành vi khác. Xem [ConditionalOnMissingBean API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnMissingBean.html).

### 3.4. Thuộc tính và loại ứng dụng cũng tham gia

Điều kiện có thể phụ thuộc thuộc tính hoặc môi trường:

| Nhóm điều kiện | Câu hỏi cần đặt |
| --- | --- |
| Classpath | Có lớp mà khả năng này cần không? |
| Bean đã tồn tại | Có thành phần để tích hợp không? |
| Bean chưa tồn tại | Ứng dụng đã thay thế mặc định chưa? |
| Thuộc tính | Khả năng có bị tắt hoặc đặt giá trị khác không? |
| Web | Đây là Servlet, reactive hay ứng dụng không có web? |

Với `@ConditionalOnProperty`, phải đọc cả giá trị mong đợi và cách xử lý khi thiếu thuộc tính. Không có quy tắc rằng “không khai báo luôn là bật” hoặc “không khai báo luôn là tắt”; các tùy chọn `havingValue` và `matchIfMissing` quyết định chi tiết. Xem [ConditionalOnProperty API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnProperty.html).

Actuator cũng có các điều kiện chuyên biệt cho endpoint, health indicator và hệ thống xuất metrics. Không nên tự thay mọi điều kiện đó bằng một suy luận chung về true/false.

## 4. Các thành phần Actuator tiêu biểu và đầu vào của chúng

### 4.1. ObservationRegistry

`ObservationRegistry` là nơi phối hợp các quan sát trong Micrometer Observation. Trong Spring Boot 3.3.0, `ObservationAutoConfiguration` xét sự hiện diện của lớp này và chỉ tạo bean registry mặc định khi chưa có bean tương ứng.

Các nhánh bên trong còn phụ thuộc Micrometer metrics hoặc tracing. Vì vậy, có một registry không đồng nghĩa mọi loại bộ xử lý đã tồn tại hoặc trace đã được gửi tới nơi lưu trữ. Có thể đối chiếu [mã nguồn ObservationAutoConfiguration 3.3.0](https://raw.githubusercontent.com/spring-projects/spring-boot/v3.3.0/spring-boot-project/spring-boot-actuator-autoconfigure/src/main/java/org/springframework/boot/actuate/autoconfigure/observation/ObservationAutoConfiguration.java).

Một ứng dụng có thể bổ sung bean `ObservationPredicate`, `ObservationFilter` hoặc `ObservationHandler` để tham gia cơ chế quan sát khi hạ tầng tương ứng được cấu hình. Đây là ví dụ về **phối hợp với bean đã có**, không chỉ tạo một bean thay thế. Xem [Spring Boot 3.3 — Observability](https://docs.spring.io/spring-boot/3.3/reference/actuator/observability.html).

### 4.2. Nền tảng metrics và nơi ghi nhận số liệu

`MeterRegistry` là giao diện trung tâm để đăng ký và ghi nhận các phép đo. `SimpleMeterRegistry` là một triển khai lưu trong bộ nhớ.

Trong Boot 3.3.0, `MetricsAutoConfiguration` cung cấp các thành phần nền, chẳng hạn đồng hồ Micrometer khi chưa có bean đồng hồ tương ứng. Điều này giải thích vì sao một khả năng có thể phụ thuộc vào bean do cấu hình khác tạo ra. Xem [mã nguồn MetricsAutoConfiguration 3.3.0](https://raw.githubusercontent.com/spring-projects/spring-boot/v3.3.0/spring-boot-project/spring-boot-actuator-autoconfigure/src/main/java/org/springframework/boot/actuate/autoconfigure/metrics/MetricsAutoConfiguration.java).

`SimpleMetricsExportAutoConfiguration` tạo registry dự phòng khi các điều kiện phù hợp, trong đó có:

- Đã có bean đồng hồ Micrometer.
- Chưa có bean `MeterRegistry`.
- Việc xuất metrics dạng simple được cho phép theo cấu hình.

Nếu ứng dụng tự có một bean `MeterRegistry`, registry dự phòng không cần được tạo thêm. Đây là trường hợp sẽ kiểm chứng trực tiếp trong phần thực nghiệm. Xem [mã nguồn SimpleMetricsExportAutoConfiguration 3.3.0](https://raw.githubusercontent.com/spring-projects/spring-boot/v3.3.0/spring-boot-project/spring-boot-actuator-autoconfigure/src/main/java/org/springframework/boot/actuate/autoconfigure/metrics/export/simple/SimpleMetricsExportAutoConfiguration.java).

### 4.3. Registry cho hệ thống bên ngoài

Khi thêm một triển khai registry được hỗ trợ, chẳng hạn `micrometer-registry-prometheus`, Boot có cơ sở để cấu hình tích hợp tương ứng. Kết quả còn phụ thuộc thuộc tính bật/tắt và các bean hiện có; ứng dụng có thể có registry tổng hợp khi dùng nhiều nơi nhận metrics.

Không nên đoán một danh sách bean cố định cho mọi ứng dụng có Prometheus. Hãy kiểm tra cây dependency, report và bean thực tế. Xem [Spring Boot 3.3 — Metrics](https://docs.spring.io/spring-boot/3.3/reference/actuator/metrics.html).

Đồng thời, registry Prometheus và HTTP endpoint `/actuator/prometheus` là hai mắt xích khác nhau: có thành phần ghi nhận số liệu chưa chứng minh URL đã được mở.

### 4.4. Thành phần kiểm tra DataSource

Trong Boot 3.3.0, cấu hình health cho JDBC xét các lớp liên quan, bean `DataSource` và việc bật health indicator `db`. Phương thức tạo contributor mặc định còn xét việc chưa có bean mang các tên thay thế cụ thể.

Trường hợp này cho thấy hai điểm:

1. Có JDBC trên classpath chưa đủ để kết luận health của cơ sở dữ liệu được tạo.
2. Quy tắc nhường cấu hình có thể xét theo **tên**, không chỉ theo kiểu như ví dụ metrics.

Xem [mã nguồn DataSourceHealthContributorAutoConfiguration 3.3.0](https://raw.githubusercontent.com/spring-projects/spring-boot/v3.3.0/spring-boot-project/spring-boot-actuator-autoconfigure/src/main/java/org/springframework/boot/actuate/autoconfigure/jdbc/DataSourceHealthContributorAutoConfiguration.java).

Không cần thêm một cơ sở dữ liệu giả vào ứng dụng chỉ để “có đủ thành phần Actuator”. Khả năng vận hành nên phản ánh các thành phần ứng dụng thực sự dùng.

### 4.5. HTTP endpoint và tracing

Với một endpoint Actuator trên HTTP, còn phải có môi trường web phù hợp, endpoint khả dụng, được đưa ra HTTP và có đường truy cập hợp lệ. Cấu hình `management.endpoints.web.exposure.include` không tải một thư viện bị thiếu và không tự tạo mọi bean cần thiết. Xem [Spring Boot 3.3 — Endpoints](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html).

Tương tự, `ObservationRegistry` có mặt không tự chứng minh đã có tracing hoàn chỉnh. Tích hợp tracing cần các thư viện bridge/tracer và cấu hình xuất phù hợp với giải pháp được chọn. Xem [Spring Boot 3.3 — Tracing](https://docs.spring.io/spring-boot/3.3/reference/actuator/tracing.html).

## 5. Thực nghiệm: cùng classpath, thay một bean

Thực nghiệm dùng **Spring Boot 3.3.0 và JDK 21**, với mã Java dùng được từ Java 17. Ứng dụng chạy không có web để tập trung vào quyết định tạo bean, không cần mở cổng HTTP.

Hai lần chạy giữ cùng thư viện; chỉ thay đổi profile để bật cấu hình bean do ứng dụng khai báo.

### 5.1. Cấu hình Gradle cho dự án thử nghiệm

Dự án giả định có Gradle wrapper 8.5 và JDK 21. Trong `settings.gradle`:

~~~groovy
rootProject.name = 'actuator-conditions-demo'
~~~

Trong `build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.0'
}

group = 'example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation platform('org.springframework.boot:spring-boot-dependencies:3.3.0')
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
}
~~~

BOM quản lý phiên bản dependency. Chỉ thêm starter Actuator vì thực nghiệm không cần máy chủ web. Cách khai báo starter được nêu trong [Spring Boot 3.3 — Enabling Production-ready Features](https://docs.spring.io/spring-boot/3.3/reference/actuator/enabling.html).

Đặt dự án thử nghiệm trong package riêng, không kèm các cấu hình registry khác; những bean bổ sung sẽ làm thay đổi đầu vào thí nghiệm.

### 5.2. Tệp Java hoàn chỉnh

Tạo `src/main/java/example/actuatorconditions/ActuatorConditionsApplication.java`:

~~~java
package example.actuatorconditions;

import java.util.Arrays;
import java.util.Map;

import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import io.micrometer.observation.ObservationRegistry;
import org.springframework.boot.Banner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Profile;

@SpringBootApplication
public class ActuatorConditionsApplication {
    public static void main(String[] args) {
        SpringApplication application =
                new SpringApplication(ActuatorConditionsApplication.class);
        application.setWebApplicationType(WebApplicationType.NONE);
        application.setBannerMode(Banner.Mode.OFF);
        application.setLogStartupInfo(false);
        application.setDefaultProperties(Map.of(
                "spring.jmx.enabled", "false",
                "management.metrics.use-global-registry", "false"));

        try (ConfigurableApplicationContext context = application.run(args)) {
            String[] registryNames = context.getBeanNamesForType(MeterRegistry.class);
            Arrays.sort(registryNames);
            System.out.println("registryBeans=" + Arrays.toString(registryNames));
            System.out.println("observationRegistry="
                    + (context.getBeanNamesForType(ObservationRegistry.class).length == 1));
        }
    }

    @Configuration(proxyBeanMethods = false)
    @Profile("manual")
    public static class ManualRegistryConfiguration {
        @Bean
        public SimpleMeterRegistry manualRegistry() {
            return new SimpleMeterRegistry();
        }
    }
}
~~~

Ý nghĩa các lựa chọn trong chương trình:

- `WebApplicationType.NONE` giữ ứng dụng ở chế độ không có web.
- `ManualRegistryConfiguration` chỉ được nạp khi profile `manual` hoạt động.
- Phương thức `manualRegistry` công bố rõ kiểu `SimpleMeterRegistry` để Spring nhận diện.
- Các tên bean được sắp xếp trước khi in để dễ đối chiếu.
- `try-with-resources` đóng context sau khi lấy kết quả.
- Không dùng global registry tĩnh để thực nghiệm tập trung vào bean trong context hiện tại.

Hai dòng in của chương trình là bằng chứng trực tiếp về bean được đăng ký. Các dòng log khác của môi trường không được coi là đầu ra cố định.

### 5.3. Lần A: để Boot cung cấp registry dự phòng

Trong thư mục dự án thử nghiệm:

~~~powershell
.\gradlew.bat bootRun
~~~

Với đúng tập dependency và cấu hình trên, hai dòng do chương trình in là:

~~~text
registryBeans=[simpleMeterRegistry]
observationRegistry=true
~~~

Không có bean registry do ứng dụng tự khai báo. Các điều kiện của nhánh dự phòng đạt nên Boot tạo `simpleMeterRegistry`.

`observationRegistry=true` ở đây chỉ có nghĩa chương trình tìm thấy đúng một bean thuộc kiểu `ObservationRegistry`. Nó không kiểm tra việc xuất traces hay trạng thái một máy chủ giám sát.

### 5.4. Lần B: ứng dụng cung cấp registry riêng

Chạy lại với profile:

~~~powershell
.\gradlew.bat bootRun --args="--spring.profiles.active=manual"
~~~

Hai dòng mong đợi:

~~~text
registryBeans=[manualRegistry]
observationRegistry=true
~~~

Classpath không đổi; lớp `SimpleMeterRegistry` vẫn tồn tại. Điều thay đổi là context có định nghĩa bean `manualRegistry` từ cấu hình đang hoạt động.

Vì bean này thuộc kiểu `MeterRegistry`, điều kiện “chưa có MeterRegistry” của nhánh dự phòng không đạt. Boot bỏ qua nhánh đó, còn registry ứng dụng vẫn được giữ.

Đây không phải hai bean trùng tên đè lên nhau: `manualRegistry` và `simpleMeterRegistry` là hai tên khác nhau. Quyết định bỏ qua mặc định trong ví dụ dựa trên **kiểu bean**.

### 5.5. Vì sao không cần Primary trong ví dụ?

`@Primary` giúp chọn một ứng viên ưu tiên khi nhiều bean phù hợp cùng tham gia việc tiêm một phụ thuộc đơn. Nó không có nghĩa bean đó là bean duy nhất tồn tại, và không đồng nghĩa xóa các bean khác.

Ví dụ đang dùng cơ chế missing-bean: khi registry ứng dụng đã có, registry dự phòng không được đăng ký. Không cần thêm Primary để buộc kết quả đó. Xem [Spring Framework — Autowiring with Primary](https://docs.spring.io/spring-framework/reference/core/beans/annotation-config/autowired-primary.html).

Cũng không cần bật `spring.main.allow-bean-definition-overriding` để thực hiện thí nghiệm này. Cho phép đè định nghĩa cùng tên là một vấn đề khác với việc cấu hình mặc định tự nhường chỗ.

## 6. Dùng báo cáo điều kiện để giải thích kết quả

### 6.1. Bật báo cáo khi khởi động

Với ví dụ Gradle:

~~~powershell
.\gradlew.bat bootRun --args="--debug"
~~~

Với profile manual:

~~~powershell
.\gradlew.bat bootRun --args="--debug --spring.profiles.active=manual"
~~~

Nếu đang có một JAR chạy được đã đóng gói, dạng lệnh tương ứng là:

~~~powershell
java -jar .\build\libs\actuator-conditions-demo-0.0.1-SNAPSHOT.jar --debug
~~~

Lệnh JAR giả định artifact đó đã được tạo, chẳng hạn bằng `bootJar` của dự án có cấu hình như trên. Không gọi `javac` riêng cho một tệp Spring rồi mong thư viện tự xuất hiện: chương trình cần classpath đầy đủ do công cụ dựng hoặc môi trường chạy cung cấp.

`--debug` giúp Boot in báo cáo đánh giá điều kiện và bật debug cho một số logger liên quan; nó không có nghĩa toàn bộ logger của mọi thư viện đều chuyển sang DEBUG. Xem [Spring Boot 3.3 — Auto-configuration](https://docs.spring.io/spring-boot/3.3/reference/using/auto-configuration.html).

### 6.2. Nhận diện các phần của report

| Phần | Cách đọc |
| --- | --- |
| Positive matches | Những cấu hình/nhánh đạt điều kiện đã được đánh giá |
| Negative matches | Những cấu hình/nhánh không đạt; xem lý do cụ thể |
| Exclusions | Những cấu hình đã bị loại theo cấu hình ứng dụng |
| Unconditional classes | Những ứng viên không có điều kiện được liệt kê ở cấp đó; không suy ra mọi bean bên trong luôn tồn tại |

Tên cấu hình hoặc cách trình bày có thể khác theo phiên bản. Hãy đọc đúng report của lần chạy đang điều tra, không dùng report từ một máy khác có profile hay dependency khác.

**Negative match thường là hành vi bình thường.** Một ứng dụng không có web có thể bỏ qua cấu hình Servlet và reactive; một ứng dụng có registry riêng bỏ qua registry dự phòng. Không cần sửa mọi dòng negative cho thành positive.

### 6.3. Đối chiếu hai lần chạy

Tìm `SimpleMetricsExportAutoConfiguration`.

Ở lần A, các lý do cần nhận ra là:

~~~text
Có bean đồng hồ micrometerClock
Chưa tìm thấy bean thuộc kiểu MeterRegistry
Nhánh simple export được cho phép
~~~

Ở lần B, lý do quyết định là:

~~~text
Điều kiện missing-bean không đạt
Đã có bean MeterRegistry tên manualRegistry
~~~

Đây là **diễn giải nội dung report**, không phải bản sao nguyên văn console. Report thực tế có thể chứa tên condition, package và mô tả dài hơn.

Một cấu hình có thể đạt một số điều kiện nhưng vẫn không được chọn vì một điều kiện khác không đạt. Trong lần B, việc cấu hình export còn được cho phép không loại bỏ sự thật rằng bean ứng dụng đã tồn tại.

### 6.4. Nếu ứng dụng web đang có endpoint conditions

Với một ứng dụng web thử nghiệm có sẵn, có thể đưa endpoint conditions ra HTTP theo phạm vi cần dùng:

~~~yaml
server:
  address: 127.0.0.1

management:
  endpoints:
    web:
      exposure:
        include: health,conditions
~~~

Sau đó gọi đúng port/base path của ứng dụng, ví dụ với cổng 8080 mặc định:

~~~powershell
curl.exe --silent --show-error http://127.0.0.1:8080/actuator/conditions
~~~

Endpoint trả báo cáo theo context, có các mục như `positiveMatches` và `negativeMatches`; một negative match có thể tách lý do đạt và không đạt. Xem [Spring Boot 3.3 — Conditions REST API](https://docs.spring.io/spring-boot/3.3/api/rest/actuator/conditions.html).

**Ví dụ Java ở trên đặt NONE nên không cung cấp URL này.** Chỉ thêm YAML exposure vào thực nghiệm không có web sẽ không tự tạo máy chủ HTTP. Có thể dùng báo cáo console để hoàn thành toàn bộ việc đối chiếu.

Trong ứng dụng có Spring Security, lời gọi còn chịu chính sách xác thực/phân quyền. Báo cáo có thể tiết lộ thông tin kỹ thuật nên cần giới hạn quyền truy cập. Không mở toàn bộ endpoint chỉ để tìm một điều kiện.

## 7. Quy trình nhận diện một thành phần trong ứng dụng thực tế

Giả sử không tìm thấy registry hoặc một health contributor mong đợi:

1. **Nêu rõ thành phần cần tìm.** Đang tìm kiểu bean, tên bean, endpoint hay dữ liệu xuất? “Actuator chưa chạy” là mô tả quá rộng.
2. **Kiểm tra runtime classpath.** Đúng thư viện, đúng phiên bản và đúng module đang chạy chưa? Đọc dependency tree/insight khi cần.
3. **Kiểm tra cấu hình ứng dụng có được nạp.** Bean tự viết nằm trong vùng scan/import hợp lệ không? Profile của nó có hoạt động không?
4. **Đọc report của đúng lần khởi động.** Tìm lớp cấu hình và phương thức liên quan; ghi lại điều kiện không đạt thay vì chỉ ghi “negative”.
5. **Đối chiếu bean thực tế.** Kiểu, tên và context có khớp tiêu chí không? Đối tượng được tạo ngoài Spring chưa phải bằng chứng về bean.
6. **Nếu đang tìm một URL, kiểm tra lớp web tiếp theo.** Port, base path, exposure và security là những đầu vào cần xét riêng.
7. **Thay đổi một đầu vào rồi chạy lại.** Giữ các đầu vào khác ổn định để thấy quan hệ nguyên nhân.

Không nên đồng thời thêm nhiều thư viện, đổi tên bean, bật nhiều thuộc tính và xóa cache rồi kết luận một thay đổi cụ thể đã giải quyết vấn đề.

Khi report ghi missing-bean tìm thấy một bean, hãy kiểm tra bean đó đến từ đâu. Nó có thể do ứng dụng, thư viện khác hoặc một cấu hình tự động đã áp dụng trước đó cung cấp.

### Thời điểm và phạm vi cần nhớ

Các điều kiện thường phục vụ quá trình dựng context. Đổi một biến cấu hình sau khi ứng dụng đã khởi động không mặc nhiên khiến Boot chạy lại toàn bộ cấu hình tự động để thay registry.

Điều kiện bean dựa trên thông tin có thể nhận diện. Công bố kiểu trả về quá chung như `Object` trong phương thức `@Bean` có thể làm việc suy luận kiểu ở thời điểm cấu hình thiếu chính xác. Nên công bố kiểu phù hợp với bean được cung cấp. Với một số cấu hình, còn phải xét quan hệ context cha/con và thứ tự các định nghĩa được xử lý. Xem [Spring Boot 3.3 — Developing Auto-configuration](https://docs.spring.io/spring-boot/3.3/reference/features/developing-auto-configuration.html).

Không sửa thứ tự bằng cách đổi tên tệp Java hoặc di chuyển phương thức trong source; đó không phải hợp đồng điều phối của auto-configuration.

## 8. Những kết luận dễ sai

| Kết luận vội | Điều cần kiểm chứng |
| --- | --- |
| JAR có lớp X nên context chắc chắn có bean X | Có cấu hình tạo bean và mọi điều kiện cần thiết không? |
| Đã new một đối tượng nên missing-bean phải nhận ra | Đối tượng có được đăng ký để Spring quản lý không? |
| Có một bean tự viết thì toàn bộ Actuator ngừng tự cấu hình | Nhánh cụ thể nào nhường chỗ? Các cấu hình khác vẫn có thể hoạt động |
| Có registry là dữ liệu đã tới Prometheus/Zipkin | Có exporter, đường xuất và nơi nhận tương ứng chưa? |
| Không thấy URL nghĩa là không có bean | Phân biệt bean, môi trường web, exposure và quyền truy cập |
| Negative matches là danh sách lỗi | Đọc xem nhánh đó có phù hợp với ứng dụng và có cần áp dụng không |
| Primary làm bean khác biến mất | Kiểm tra riêng tập bean và quy tắc chọn khi tiêm phụ thuộc |
| Đổi tên registry sẽ làm missing-bean theo kiểu không nhận ra | Điều kiện đang xét tên hay kiểu? |
| Report của lần trước đủ giải thích lần chạy hiện tại | Classpath, profile, thuộc tính và context có còn giống nhau không? |

### Tự thực hành

1. Chạy hai lần thực nghiệm và ghi lại tên bean, kiểu bean cùng lý do report chọn/bỏ nhánh dự phòng.
2. Ở profile manual, đổi tên phương thức `manualRegistry` thành `teamRegistry`. Dự đoán registry mặc định có quay lại không và giải thích dựa vào loại điều kiện.
3. Giữ thư viện JDBC nhưng không có bean DataSource: đã đủ bằng chứng để khẳng định có health contributor cho database chưa?
4. Trong ứng dụng không có web, bật exposure cho conditions. Giải thích vì sao vẫn chưa có URL HTTP.
5. Tìm một negative match bình thường trong report và nêu đầu vào khiến nó không khớp.

**Gợi ý đối chiếu:** ví dụ registry dự phòng xét theo kiểu MeterRegistry nên đổi tên bean ứng dụng không làm kiểu đó biến mất. Classpath và bean là hai điều kiện khác nhau. Report giải thích quyết định cấu hình; việc đọc bean xác nhận kết quả trong context; việc truy cập HTTP cần những điều kiện tiếp theo.
