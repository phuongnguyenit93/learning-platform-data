# Vai trò của mô-đun actuator và actuator-autoconfigure

Bạn thêm dependency Actuator, khởi động ứng dụng và thấy một số điểm truy cập quản trị xuất hiện. Phía sau trải nghiệm đó có hai công việc: cung cấp các kiểu dữ liệu và mã thực thi, rồi cấu hình chúng thành những thành phần phù hợp với ứng dụng đang chạy.

Trong Spring Boot 3.3, hai artifact chính phục vụ hai công việc này là `spring-boot-actuator` và `spring-boot-actuator-autoconfigure`. Hiểu ranh giới giữa chúng giúp bạn đọc dependency, tìm nguyên nhân thiếu bean và tránh nhầm việc có thư viện với việc đã công khai một URL.

Ở đây, “mô-đun” chỉ một thành phần thư viện được đóng gói thành artifact/JAR của Spring Boot. Nó không có nghĩa mỗi ứng dụng phải tạo hai Gradle project riêng hoặc hai tiến trình riêng.

## 1. Bức tranh tổng thể

| Thành phần | Câu hỏi nó trả lời | Ví dụ |
| --- | --- | --- |
| `spring-boot-actuator` | Có những khả năng, API và triển khai vận hành nào để sử dụng? | `Health`, `HealthIndicator`, `HealthEndpoint`, hạ tầng endpoint |
| `spring-boot-actuator-autoconfigure` | Khi nào và bằng cách nào cấu hình các khả năng đó cho ứng dụng này? | `HealthEndpointAutoConfiguration`, các properties và cấu hình tích hợp |
| `spring-boot-starter-actuator` | Nên khai báo tập dependency thông dụng qua điểm vào nào? | Đưa các thư viện liên quan vào đồ thị phụ thuộc |

Spring Boot khuyến nghị thêm `spring-boot-starter-actuator` để sử dụng các tính năng vận hành. Bạn thường không phải khai báo thủ công từng JAR phía dưới. Xem [Spring Boot 3.3 — Enabling Production-ready Features](https://docs.spring.io/spring-boot/3.3/reference/actuator/enabling.html).

Một cách hình dung:

```text
Thêm starter vào dependency
             ↓
Các lớp Actuator và auto-configuration có trên classpath
             ↓
Ứng dụng bật cơ chế auto-configuration
             ↓
Các cấu hình được xét theo điều kiện
             ↓
Các bean phù hợp được đăng ký vào ApplicationContext
             ↓
Nếu có hạ tầng web/JMX và chính sách công khai phù hợp:
các thao tác quản trị được đưa ra qua cơ chế tương ứng
```

**Classpath** là tập vị trí JVM tìm lớp và tài nguyên. **Bean** là đối tượng do Spring quản lý trong **ApplicationContext**, tức ngữ cảnh chứa cấu hình và các thành phần của ứng dụng. Thư viện cung cấp một lớp không đồng nghĩa Spring đã tạo đối tượng của lớp ấy.

## 2. spring-boot-actuator: API cùng mã triển khai khả năng vận hành

Artifact `org.springframework.boot:spring-boot-actuator` chứa những kiểu mà các tính năng Actuator sử dụng lúc chạy. Với kiểm tra sức khỏe, bạn thường gặp:

- `Health`: biểu diễn kết quả sức khỏe.
- `HealthIndicator`: giao diện cho một phép kiểm tra sức khỏe.
- `HealthEndpoint`: triển khai endpoint đọc thông tin sức khỏe.

Chẳng hạn, `HealthEndpoint` thuộc package `org.springframework.boot.actuate.health`, có `@Endpoint(id = "health")` và thao tác đọc `health()`. Định nghĩa API được trình bày trong [HealthEndpoint — Spring Boot 3.3 API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/health/HealthEndpoint.html).

### 2.1. Khả năng sử dụng và đối tượng được quản lý là hai chuyện

Một phép kiểm tra tự viết có thể dùng API `HealthIndicator` để trả kết quả. Nhưng chỉ viết một lớp hoặc tạo một biểu thức lambda chưa khiến ứng dụng tự biết cần thu thập kết quả của nó.

Cần đăng ký thành phần đó với Spring hoặc nối nó vào hạ tầng thích hợp. Sau đó cần một endpoint sử dụng các thành phần kiểm tra. Cuối cùng mới xét đường truy cập ngoài tiến trình.

Ví dụ tương tự trong mã Java thông thường: có lớp `InvoiceService` trên classpath không làm chương trình tự tạo một dịch vụ hóa đơn và gọi nó. Spring cần cấu hình để biết tạo gì và nối với những gì.

### 2.2. Actuator chứa cả hạ tầng và bộ thích nghi, không chỉ kiểu dữ liệu

Không nên hiểu `spring-boot-actuator` là một JAR chỉ có interface hoặc chỉ có endpoint độc lập với giao thức. Nó cũng chứa mã hạ tầng để khám phá, thực thi và tích hợp endpoint.

Ví dụ, `WebMvcEndpointHandlerMapping` thuộc package `org.springframework.boot.actuate.endpoint.web.servlet`. Đây là triển khai ánh xạ endpoint qua HTTP bằng Spring MVC. Xem [WebMvcEndpointHandlerMapping — API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/endpoint/web/servlet/WebMvcEndpointHandlerMapping.html).

Vì vậy, ranh giới chính là **khả năng và triển khai** với **cấu hình tự động để tích hợp chúng**. Không dùng quy tắc “có chữ web thì chắc chắn thuộc actuator-autoconfigure” để đoán vị trí một lớp.

### 2.3. Có JAR không có nghĩa mọi tính năng đều chạy

Một ứng dụng không dùng web vẫn có thể sử dụng các kiểu của Actuator. Một ứng dụng có web cũng không nhất thiết công khai mọi endpoint.

Tính năng có thể cần thêm thư viện, bean cộng tác hoặc cấu hình. Hãy kiểm tra yêu cầu của tính năng cụ thể thay vì coi một JAR là công tắc bật toàn bộ khả năng vận hành.

## 3. spring-boot-actuator-autoconfigure: cấu hình theo điều kiện

Artifact `org.springframework.boot:spring-boot-actuator-autoconfigure` tích hợp các khả năng Actuator vào ứng dụng Spring Boot. Nó chứa những lớp cấu hình tự động và kiểu cấu hình liên quan.

Auto-configuration được ứng dụng bật qua `@EnableAutoConfiguration` hoặc `@SpringBootApplication`. Spring Boot xem xét các dependency và điều kiện hiện tại để quyết định cấu hình nào phù hợp. Xem [Spring Boot 3.3 — Auto-configuration](https://docs.spring.io/spring-boot/3.3/reference/using/auto-configuration.html).

### 3.1. Tự động không có nghĩa vô điều kiện

Các câu hỏi có thể được dùng khi xét cấu hình gồm:

| Loại điều kiện | Câu hỏi tiêu biểu |
| --- | --- |
| Lớp có trên classpath | Thư viện cần cho tính năng đã có chưa? |
| Bean trong context | Đã có thành phần cần thiết hoặc thành phần người dùng tự cung cấp chưa? |
| Thuộc tính cấu hình | Tính năng có được cho phép theo cấu hình hiện tại không? |
| Loại ứng dụng | Đây có phải môi trường web phù hợp không? |
| Khả năng sử dụng endpoint | Endpoint có được bật và công khai theo chính sách được xét không? |

Mỗi cấu hình có bộ điều kiện riêng. Không suy ra rằng tất cả lớp auto-configuration đều dùng đầy đủ các điều kiện trong bảng.

Việc thay dependency, thêm bean hoặc đổi thuộc tính có thể làm cấu hình khớp hoặc không khớp ở lần tạo context tiếp theo. Đây là cơ chế cấu hình lúc khởi tạo ứng dụng, không phải một tiến trình nền liên tục quét các JAR để tùy ý thay mọi bean.

### 3.2. Ví dụ health

`HealthEndpointAutoConfiguration` thuộc package `org.springframework.boot.actuate.autoconfigure.health`. API của lớp cho thấy nó:

- Là một `@AutoConfiguration`.
- Dùng `@ConditionalOnAvailableEndpoint` cho `HealthEndpoint`.
- Kích hoạt binding của `HealthEndpointProperties`.
- Nhập các cấu hình liên quan tới health và các phần mở rộng tương ứng.

Xem [HealthEndpointAutoConfiguration — API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/autoconfigure/health/HealthEndpointAutoConfiguration.html).

Nhờ đó, lớp `HealthEndpoint` ở JAR triển khai được cấu hình bằng các thành phần và chính sách cụ thể của ứng dụng. Hai JAR cùng tham gia một tính năng nhưng làm những phần việc khác nhau.

### 3.3. “Available” là điều kiện cấu hình, không phải kết quả gọi mạng

Trong Spring Boot 3.3, `@ConditionalOnAvailableEndpoint` xét việc bật endpoint và chính sách công khai theo công nghệ liên quan. Nó không gửi một yêu cầu HTTP ra ngoài để kiểm tra URL có truy cập được hay không. Xem [ConditionalOnAvailableEndpoint — API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/autoconfigure/endpoint/condition/ConditionalOnAvailableEndpoint.html).

Sau khi cấu hình khớp, một URL thật còn cần hạ tầng phục vụ, ánh xạ và quyền truy cập phù hợp. Ngược lại, một phép thử context không có máy chủ web vẫn có thể giúp kiểm tra việc tạo một bean endpoint.

### 3.4. Cấu hình cho web là một lớp tích hợp riêng

`WebEndpointAutoConfiguration` có điều kiện môi trường web và cấu hình các thành phần hỗ trợ khám phá, ánh xạ tên và lọc endpoint web. Xem [WebEndpointAutoConfiguration — API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/autoconfigure/endpoint/web/WebEndpointAutoConfiguration.html).

Đọc tới đây, hãy tách ba câu hỏi:

```text
Có lớp HealthEndpoint không?
        ↓
Context này có bean HealthEndpoint không?
        ↓
Ứng dụng này có đường HTTP được phép truy cập tới nó không?
```

Mỗi câu cần một loại bằng chứng khác nhau. Tìm thấy tên lớp trong JAR chỉ trả lời câu đầu tiên.

## 4. Vì sao lại có starter?

Starter là điểm khai báo dependency thuận tiện. Nó giúp ứng dụng lấy tập thư viện thường dùng mà không phải tự duy trì danh sách phiên bản và các dependency chuyển tiếp.

Ở Spring Boot 3.3.5, starter Actuator phụ thuộc vào starter cơ sở, `spring-boot-actuator-autoconfigure` và các thành phần Micrometer liên quan. Xem [khai báo dependency chính thức của starter tại v3.3.5](https://raw.githubusercontent.com/spring-projects/spring-boot/v3.3.5/spring-boot-project/spring-boot-starters/spring-boot-starter-actuator/build.gradle).

Một phần đồ thị đã rút gọn, không liệt kê mọi cạnh:

```text
spring-boot-starter-actuator
├─ spring-boot-starter
├─ spring-boot-actuator-autoconfigure
│  ├─ spring-boot-actuator
│  ├─ spring-boot
│  └─ spring-boot-autoconfigure
└─ Các dependency Micrometer liên quan
```

Phần dưới starter được xác minh từ POM đóng gói của Spring Boot 3.3.5. Đường đi này giải thích vì sao khai báo starter có thể làm cả hai JAR chính xuất hiện dù bạn chỉ viết một dòng dependency.

### 4.1. Ba tên gần nhau nhưng vai trò khác nhau

- `spring-boot-autoconfigure`: hạ tầng và tập cấu hình tự động chung của Spring Boot.
- `spring-boot-actuator-autoconfigure`: tập cấu hình tự động cho các khả năng Actuator.
- `spring-boot-starter-actuator`: tập dependency thuận tiện để sử dụng Actuator.

Không bỏ một artifact chỉ vì thấy artifact khác cũng có chữ `autoconfigure`. Hãy đọc tên đầy đủ và đường phụ thuộc.

Trong dự án đã quản lý phiên bản Spring Boot, cách khai báo thông thường là:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
}
```

Starter này không tự cung cấp một ứng dụng web hoàn chỉnh. Nếu mục tiêu là HTTP, ứng dụng còn cần nền tảng web và cách khởi động phù hợp. Với ứng dụng web đã có, không cần thêm một ứng dụng quản trị thứ hai chỉ để sử dụng Actuator.

### 4.2. Giữ phiên bản nhất quán

Trong một ứng dụng thực tế, dùng cơ chế quản lý dependency của Spring Boot để các thành phần có phiên bản tương thích. Không cố định riêng actuator sang một phiên bản khác chỉ để chữa lỗi thiếu lớp khi chưa hiểu xung đột.

Tên artifact, cạnh phụ thuộc và các chi tiết nội bộ có thể thay đổi giữa các dòng Spring Boot. Bài học này đang giải thích Spring Boot 3.3; khi nâng phiên bản, đối chiếu tài liệu của phiên bản đích.

## 5. Từ ứng viên cấu hình tới bean thực tế

Spring Boot tìm các ứng viên auto-configuration qua tài nguyên:

```text
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
```

Tài nguyên này chứa tên các lớp cấu hình. Các điều kiện xác định ứng viên nào được áp dụng trong ứng dụng cụ thể; nó không phải danh sách mọi bean chắc chắn sẽ tồn tại. Cơ chế và các annotation điều kiện được trình bày trong [Creating Your Own Auto-configuration](https://docs.spring.io/spring-boot/3.3/reference/features/developing-auto-configuration.html).

Trong JAR `spring-boot-actuator-autoconfigure-3.3.5.jar`, có tên `org.springframework.boot.actuate.autoconfigure.health.HealthEndpointAutoConfiguration` trong danh sách ứng viên. Điều này cho phép cơ chế của Boot tìm cấu hình mà bạn không phải quét toàn bộ package nội bộ bằng `@ComponentScan`.

### 5.1. Khi ứng dụng đã cung cấp thành phần riêng

Một số bean mặc định được tạo theo điều kiện `@ConditionalOnMissingBean`: chỉ tạo khi chưa có bean phù hợp. Vì vậy, một bean người dùng tự cung cấp có thể làm cấu hình mặc định nhường chỗ.

Cần đọc điều kiện cụ thể để biết phần nào nhường chỗ. Thêm một `HealthIndicator` nghiệp vụ thường là bổ sung nguồn kết quả kiểm tra, không đồng nghĩa thay toàn bộ `HealthEndpoint` hay tắt toàn bộ Actuator.

Cũng cần phân biệt việc nhường cấu hình theo điều kiện với việc cho phép hai bean cùng tên ghi đè lẫn nhau. Hai cơ chế đó không phải một. Xem điều kiện chính xác ở [ConditionalOnMissingBean — API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnMissingBean.html).

### 5.2. Không lấy chi tiết nội bộ làm điểm mở rộng mặc định

Có thể đọc auto-configuration để hiểu ứng dụng. Khi tùy chỉnh, ưu tiên thuộc tính và các API mở rộng được công bố.

Không gọi trực tiếp một phương thức factory nội bộ của cấu hình chỉ vì nó giúp tạo một đối tượng trong ví dụ. API chính thức lưu ý tên lớp auto-configuration được dùng cho việc loại trừ; các cấu trúc bên trong không được coi là API công khai ổn định.

Phần tiếp theo chỉ dùng tên một lớp cấu hình để xác định nó đến từ JAR nào. Chương trình bật auto-configuration qua cơ chế chuẩn, không gọi các phương thức nội bộ của lớp ấy.

## 6. Thí nghiệm: cùng classpath, kết quả context khác nhau

Ta tạo ba context liên tiếp:

1. `plain`: đăng ký một phép kiểm tra sức khỏe, không bật auto-configuration.
2. `auto`: giữ phép kiểm tra ấy và bật `@EnableAutoConfiguration`.
3. `disabled`: bật auto-configuration nhưng đặt `management.endpoint.health.enabled=false`.

Cả ba dùng cùng classpath. Nhờ vậy, khác biệt về bean có thể được quan sát mà không phải xóa JAR hay thay nhiều dependency cùng lúc.

### 6.1. Chuẩn bị một dự án thử nghiệm riêng

Dùng JDK 17 trở lên và Gradle tương thích. Phiên bản Spring Boot 3.3.5 được cố định để kết quả tên JAR dễ tái lập.

Tạo `settings.gradle`:

```groovy
rootProject.name = 'actuator-module-demo'
```

Tạo `build.gradle`:

```groovy
plugins {
    id 'java'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation platform(
        'org.springframework.boot:spring-boot-dependencies:3.3.5')
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
}

tasks.register('copyDemoLibraries', Copy) {
    from configurations.runtimeClasspath
    into layout.projectDirectory.dir('lib')
}
```

Đây là dự án Java nhỏ dùng BOM Spring Boot để quản lý dependency. Nó không dùng plugin đóng gói Boot, không thêm starter web và không tự chạy máy chủ HTTP.

Để tránh trộn JAR của nhiều lần thử, dùng thư mục mới cho thí nghiệm này. Tác vụ tải dependency cần mạng nếu thư viện chưa có trong bộ nhớ đệm.

### 6.2. Chương trình đầy đủ

Tạo tệp `src/main/java/lab/actuator/ActuatorModuleDemo.java`:

```java
package lab.actuator;

import java.nio.file.Path;
import java.util.Map;

import org.springframework.boot.actuate.autoconfigure.health.HealthEndpointAutoConfiguration;
import org.springframework.boot.actuate.health.Health;
import org.springframework.boot.actuate.health.HealthEndpoint;
import org.springframework.boot.actuate.health.HealthIndicator;
import org.springframework.boot.autoconfigure.EnableAutoConfiguration;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.env.MapPropertySource;

public class ActuatorModuleDemo {
    public static void main(String[] args) throws Exception {
        System.out.println("api.jar=" + jarName(Health.class));
        System.out.println("config.jar="
                + jarName(HealthEndpointAutoConfiguration.class));
        run("plain", false, true);
        run("auto", true, true);
        run("disabled", true, false);
    }

    private static String jarName(Class<?> type) throws Exception {
        return Path.of(type.getProtectionDomain()
                .getCodeSource().getLocation().toURI())
                .getFileName().toString();
    }

    private static void run(String label, boolean auto, boolean enabled) {
        try (AnnotationConfigApplicationContext context =
                new AnnotationConfigApplicationContext()) {
            context.getEnvironment().getPropertySources().addFirst(
                    new MapPropertySource("demo", Map.of(
                            "management.endpoint.health.enabled",
                            Boolean.toString(enabled),
                            "management.health.defaults.enabled", "false")));
            context.register(HealthConfig.class);
            if (auto) {
                context.register(BootConfig.class);
            }
            context.refresh();

            Map<String, HealthEndpoint> endpoints =
                    context.getBeansOfType(HealthEndpoint.class);
            System.out.println(label + ".endpoints=" + endpoints.size());
            if (!endpoints.isEmpty()) {
                HealthEndpoint endpoint = endpoints.values().iterator().next();
                System.out.println(label + ".status="
                        + endpoint.health().getStatus().getCode());
            }
        }
    }

    @Configuration(proxyBeanMethods = false)
    static class HealthConfig {
        @Bean
        HealthIndicator labHealthIndicator() {
            return () -> Health.up().build();
        }
    }

    @Configuration(proxyBeanMethods = false)
    @EnableAutoConfiguration
    static class BootConfig {
    }
}
```

Trong đó:

- `HealthConfig` là cấu hình do ta viết, đăng ký `labHealthIndicator`.
- `BootConfig` bật cơ chế cấu hình tự động chuẩn.
- Thuộc tính được đưa vào môi trường trước `refresh()`, để việc xét điều kiện nhìn thấy giá trị đúng.
- `management.health.defaults.enabled=false` làm thí nghiệm tập trung vào phép kiểm tra do ta đăng ký, thay vì phụ thuộc các kiểm tra mặc định của máy.
- `jarName` đọc nơi nạp lớp để xác định artifact, không dùng nó để thay đổi cấu hình.

Hai context có auto-configuration được tạo độc lập, rồi đóng sau khi kiểm tra. Chương trình không đổi thuộc tính trên một context đang chạy để yêu cầu nó tự tái tạo toàn bộ bean.

### 6.3. Biên dịch và chạy

Tại thư mục gốc của thí nghiệm, dùng PowerShell:

```powershell
gradle copyDemoLibraries
javac -encoding UTF-8 -cp "lib/*" -d out src/main/java/lab/actuator/ActuatorModuleDemo.java
java -cp "out;lib/*" lab.actuator.ActuatorModuleDemo
```

Nếu dự án thử có Gradle Wrapper, có thể dùng wrapper tương ứng thay cho lệnh `gradle`. Trên Linux/macOS, lệnh chạy dùng dấu `:` để phân cách classpath:

```bash
java -cp "out:lib/*" lab.actuator.ActuatorModuleDemo
```

Kết quả stdout của chương trình trong cấu hình thí nghiệm:

```text
api.jar=spring-boot-actuator-3.3.5.jar
config.jar=spring-boot-actuator-autoconfigure-3.3.5.jar
plain.endpoints=0
auto.endpoints=1
auto.status=UP
disabled.endpoints=0
```

Thông báo tải hoặc thực thi Gradle không thuộc stdout minh họa của chương trình Java. Nếu đổi phiên bản thư viện, hai dòng tên JAR phải phản ánh phiên bản thực sự đã nạp.

### 6.4. Đọc từng kết quả như bằng chứng

| Dòng kết quả | Điều nó chứng minh trong thí nghiệm |
| --- | --- |
| `api.jar=...` | Lớp `Health` được nạp từ JAR triển khai Actuator |
| `config.jar=...` | Lớp cấu hình health được nạp từ JAR actuator-autoconfigure |
| `plain.endpoints=0` | Chỉ có các lớp và một indicator chưa làm context tự tạo endpoint |
| `auto.endpoints=1` | Cơ chế tự động cấu hình đã đăng ký endpoint khi điều kiện phù hợp |
| `auto.status=UP` | Endpoint đọc được kết quả tốt từ phép kiểm tra giả lập |
| `disabled.endpoints=0` | Thuộc tính tắt health làm nhánh cấu hình endpoint không được áp dụng |

Cả hai JAR vẫn có thể nạp lớp trong cả ba lần thử. Do đó, không được giải thích `disabled.endpoints=0` là “JVM đã gỡ lớp HealthEndpoint ra khỏi bộ nhớ” hoặc “dependency Actuator đã biến mất”.

### 6.5. Những điều thí nghiệm chưa kiểm tra

Chương trình dùng `AnnotationConfigApplicationContext` thông thường. Nó không tạo hạ tầng web và không mở cổng. Vì thế, `auto.endpoints=1` không chứng minh `http://localhost:8080/actuator/health` đang truy cập được.

`labHealthIndicator` luôn trả `Health.up()` để cô lập cơ chế đăng ký. Kết quả này cũng không kiểm tra cơ sở dữ liệu, hàng đợi hay tính đúng đắn của nghiệp vụ.

Ta đang quan sát việc cấu hình bean, không thử toàn bộ hành vi triển khai một ứng dụng web. Khi cần kiểm tra HTTP, phải dùng một ứng dụng web có cấu hình phù hợp và kiểm tra phản hồi thật.

### 6.6. Một thay đổi để tự kiểm chứng

Trong bản sao thí nghiệm, đổi tên nhãn in của lần thứ ba để dễ nhận diện, rồi giữ `enabled=true` thay vì `false` cho lần đó. Dự đoán số endpoint trước khi chạy.

Nếu các điều kiện khác giữ nguyên, lần thứ ba sẽ có endpoint giống nhánh `auto`. Sau đó khôi phục mã để so sánh. Bài tập giúp bạn kiểm tra mối liên hệ giữa thuộc tính đầu vào và kết quả tạo context, thay vì chỉ ghi nhớ một con số.

## 7. Từ bean tới HTTP: những điều cần kiểm tra thêm

Trong ứng dụng web Spring Boot thực tế, đường đi còn có các lớp tích hợp:

```text
Lớp triển khai endpoint có trên classpath
                  ↓
Điều kiện tạo bean phù hợp
                  ↓
Bean endpoint trong context
                  ↓
Hạ tầng khám phá và công khai endpoint qua web
                  ↓
Ánh xạ trên máy chủ HTTP của ứng dụng
                  ↓
Bộ lọc bảo mật và đường mạng cho phép truy cập
```

Sơ đồ là thứ tự các câu hỏi cần kiểm tra, không phải mô tả tuyệt đối thứ tự khởi tạo mọi bean.

Ví dụ các thuộc tính phục vụ hai mục đích khác nhau trong Spring Boot 3.3:

```yaml
management:
  endpoint:
    health:
      enabled: true
  endpoints:
    web:
      exposure:
        include: "health"
```

Thuộc tính đầu kiểm soát việc bật health; thuộc tính sau chọn điểm truy cập công khai qua HTTP. Một lựa chọn công khai không tự cung cấp dependency còn thiếu và không thay thế quyền truy cập của Spring Security. Chi tiết chính sách được mô tả trong [Spring Boot 3.3 — Endpoints](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html).

Với ứng dụng web đang chạy trên cổng và đường dẫn mặc định, có thể kiểm tra:

```powershell
curl.exe -i "http://localhost:8080/actuator/health"
```

Đọc mã HTTP và nội dung thật. Nếu ứng dụng đổi cổng, đường dẫn hoặc dùng xác thực, phải dùng giá trị tương ứng. Lệnh này dành cho ứng dụng web riêng đang chạy; nó không gọi được chương trình console ở phần 6 vì chương trình ấy đã đóng context và không có máy chủ.

### 7.1. Phân biệt ba dạng thiếu thành phần

**Thiếu lớp:** mã cần một kiểu nhưng kiểu đó không có trên runtime classpath. Kiểm tra dependency và phiên bản.

**Thiếu bean:** lớp có thể nạp nhưng context không có đối tượng quản lý tương ứng. Kiểm tra đăng ký cấu hình, điều kiện, thuộc tính và thành phần người dùng cung cấp.

**Thiếu đường truy cập:** có thành phần phía ứng dụng nhưng không truy cập được theo URL dự kiến. Kiểm tra ứng dụng web, công khai, ánh xạ, quyền, cổng và mạng.

Không dùng một lỗi HTTP đơn lẻ để kết luận ngay rằng thiếu JAR. Ngược lại, tìm thấy JAR trong dependency cũng chưa đủ để loại trừ lỗi tạo bean.

## 8. Đọc dependency và báo cáo điều kiện để tìm nguyên nhân

### 8.1. Xác minh thư viện thực sự được chọn

Trong dự án Gradle, có thể dùng:

```powershell
gradle dependencies --configuration runtimeClasspath
gradle dependencyInsight --dependency spring-boot-actuator --configuration runtimeClasspath
gradle dependencyInsight --dependency spring-boot-actuator-autoconfigure --configuration runtimeClasspath
```

Ở dự án nhiều module, chạy cho đúng project ứng dụng. Cần phân biệt dependency bạn khai báo với phiên bản cuối cùng mà Gradle đã giải quyết.

Nếu có lỗi `NoClassDefFoundError` hoặc `NoSuchMethodError`, ghi lại tên lớp/phương thức và những phiên bản đang có. Không bắt đầu bằng cách thêm cả hai artifact với các phiên bản ngẫu nhiên.

Một ứng dụng có thể biên dịch với một tập dependency nhưng chạy với một tập khác, chẳng hạn do cấu hình đóng gói hoặc runtime của môi trường. Vì vậy, khi cần hãy đối chiếu cả artifact thực tế được chạy.

### 8.2. Xem vì sao cấu hình khớp hoặc không khớp

Với một ứng dụng khởi động qua `SpringApplication`, tùy chọn `--debug` giúp hiển thị báo cáo điều kiện. Ví dụ với JAR ứng dụng:

```powershell
java -jar app.jar --debug
```

`app.jar` là tên ví dụ, phải thay bằng JAR của ứng dụng thật. Đây không phải lệnh dành cho tệp class console đã biên dịch ở phần 6.

Tìm cấu hình liên quan như `HealthEndpointAutoConfiguration`, rồi đọc điều kiện cụ thể. Báo cáo không phải một bảng “mọi dòng không khớp đều là lỗi”: nhiều nhánh không khớp là bình thường vì ứng dụng không dùng những thư viện hoặc công nghệ đó.

Nếu đã có cách truy cập phù hợp, endpoint `conditions` cũng hỗ trợ xem các quyết định cấu hình. Không cần công khai toàn bộ endpoint chỉ để điều tra một trường hợp.

### 8.3. Xác định thay đổi nhỏ nhất để kiểm chứng

| Hiện tượng | Bằng chứng cần tìm | Hướng kiểm chứng |
| --- | --- | --- |
| Mã không tìm thấy `Health` | Compile classpath | Dependency Actuator đã được giải quyết chưa? |
| `HealthEndpoint` có lớp nhưng không có bean | Cấu hình và báo cáo điều kiện | Có bật auto-configuration, có tắt health không? |
| Bean tự viết làm hành vi mặc định thay đổi | Bean thực tế và điều kiện còn thiếu | Thành phần nào đang được dùng thay mặc định? |
| HTTP trả 404 | Điểm truy cập, đường dẫn và loại ứng dụng | Có hạ tầng web và công khai theo đường đang gọi không? |
| HTTP trả 401/403 | Chính sách bảo mật | Bên gọi có quyền theo cơ chế hiện tại không? |
| Thêm thuộc tính không tạo tác dụng | Giá trị cấu hình hiệu lực | Có sai profile hoặc bị nguồn cấu hình khác thay thế không? |

Các mã HTTP là hướng bắt đầu điều tra, không phải ánh xạ chắc chắn cho mọi hệ thống có proxy và quy tắc bảo mật riêng.

Cách làm tốt là ghi một giả thuyết, thay một yếu tố có kiểm soát và đọc lại bằng chứng. Ví dụ thí nghiệm phần 6 giữ nguyên classpath để tập trung kiểm tra vai trò của auto-configuration và thuộc tính health.

## 9. Những cách hiểu cần điều chỉnh

### “actuator-autoconfigure chỉ là dependency để biên dịch”

Các lớp cấu hình được dùng khi ứng dụng tạo context. Nếu dựa vào chúng lúc chạy, chúng phải có trong runtime classpath. Đừng loại chúng khỏi bản đóng gói chỉ vì tên có chữ “configure”.

### “actuator chỉ chứa interface, toàn bộ mã chạy nằm ở autoconfigure”

Actuator chứa cả API lẫn triển khai, bao gồm những thành phần thích nghi với công nghệ. Phần tự động cấu hình tạo và nối những thành phần phù hợp. Tên package đầy đủ cùng nơi nạp lớp là bằng chứng tốt hơn phỏng đoán theo tên ngắn.

### “Có actuator-autoconfigure thì không cần actuator”

Trong đồ thị Spring Boot 3.3.5, artifact cấu hình phụ thuộc artifact triển khai. Nó không thay thế các lớp như `HealthEndpoint`. Có thể bạn chỉ khai báo một artifact nhưng artifact còn lại được lấy chuyển tiếp; cần xem đồ thị trước khi kết luận.

### “Starter là nơi chứa mọi lớp endpoint”

Starter chủ yếu là điểm vào tập dependency. Trong thí nghiệm, `Health` và lớp cấu hình được nạp từ hai JAR riêng, không phải từ `spring-boot-starter-actuator`.

### “Một indicator tự viết sẽ tắt mọi cấu hình Actuator”

Một indicator là nguồn kiểm tra sức khỏe. Cơ chế nhường cấu hình mặc định phụ thuộc kiểu bean và điều kiện cụ thể, không áp dụng đồng loạt cho cả tính năng chỉ vì ứng dụng đã có một bean tự viết.

### “Bật endpoint là người ngoài truy cập được”

Thí nghiệm không có web vẫn tạo được bean endpoint. Với đường HTTP thật, còn cần hạ tầng web, chính sách công khai, ánh xạ và quyền. Hãy dùng đúng bằng chứng cho từng lớp.

## 10. Tự kiểm tra

### Tình huống A

Bạn tìm thấy `HealthEndpoint.class` trong JAR nhưng context tự tạo bằng Spring thông thường không có bean `HealthEndpoint`.

**Giải thích:** mới xác nhận lớp tồn tại. Cần kiểm tra cơ chế đăng ký và cấu hình. Thí nghiệm `plain` cho thấy có thư viện không tự đồng nghĩa có bean.

### Tình huống B

Hai ứng dụng dùng cùng starter và cùng phiên bản, nhưng chỉ một ứng dụng có endpoint mong đợi.

**Giải thích:** so sánh thuộc tính hiệu lực, loại context, điều kiện, thành phần ứng dụng tự cung cấp và cơ chế khởi động. Cùng dependency chưa bảo đảm cùng cấu hình lúc chạy.

### Tình huống C

Bạn muốn đóng một đường quản trị HTTP và đang định loại toàn bộ `spring-boot-actuator-autoconfigure`.

**Giải thích:** việc loại JAR ảnh hưởng nhiều cấu hình, không chỉ đường đó. Trước tiên xác định yêu cầu là tắt khả năng, thay chính sách công khai hay thay quyền truy cập; dùng cơ chế phù hợp với đúng yêu cầu.

### Bài tập áp dụng

Chọn một khả năng Actuator đang dùng và trả lời:

1. Kiểu triển khai chính thuộc artifact và package nào?
2. Lớp cấu hình tự động liên quan tên gì?
3. Những điều kiện nào quan trọng trong ứng dụng hiện tại?
4. Bean nào đang thực sự có trong context?
5. Nếu cần truy cập từ ngoài, cơ chế nào công khai nó và ai được phép gọi?

Bạn hiểu quan hệ hai mô-đun khi giải thích được đường đi từ dependency tới lớp, từ cấu hình tới bean và từ bean tới cách sử dụng trong ứng dụng cụ thể.
