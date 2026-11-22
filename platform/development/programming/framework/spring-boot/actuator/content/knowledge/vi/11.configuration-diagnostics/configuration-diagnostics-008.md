# Đối chiếu endpoint chẩn đoán với log, profile và cấu hình môi trường

## 1. Vì sao phải ghép nhiều nguồn bằng chứng?

Một ứng dụng chạy đúng trên máy cá nhân nhưng dùng thời gian chờ khác khi triển khai. Tệp cấu hình ghi tính năng đã bật nhưng bean vẫn không xuất hiện. Một dòng DEBUG không có trong log khiến người vận hành nghi ngờ nhánh mã chưa chạy.

Cả ba tình huống đều cần đối chiếu, vì mỗi công cụ chỉ trả lời một phần câu hỏi:

| Nguồn quan sát | Câu hỏi chính |
| --- | --- |
| Log khởi động và log của ứng dụng | Chuyện gì đã xảy ra trong lần chạy nào? |
| Profile đang hoạt động | Những phần cấu hình theo môi trường nào được chọn? |
| Endpoint `env` | Giá trị đang được phân giải từ nguồn cấu hình nào? |
| Endpoint `configprops` | Đối tượng `@ConfigurationProperties` đã nhận dữ liệu gì? |
| Endpoint `conditions` | Điều kiện nào được ghi nhận là khớp hoặc không khớp? |
| Endpoint `beans` | Định nghĩa bean nào có trong context đang xem? |
| Endpoint `loggers` | Logger đang có mức cấu hình và mức hiệu lực nào? |

Đích đến không phải là thu thập mọi JSON hoặc bật mọi loại log. Đích đến là giải thích được một hành vi bằng những bằng chứng thuộc cùng ứng dụng và cùng lần chạy.

Ví dụ, câu “timeout là 9 giây” chưa đủ. Câu hữu ích hơn là:

> Ở lần chạy đang xét, profile sandbox được kích hoạt; thuộc tính timeout đến từ biến môi trường; đối tượng cấu hình nhận 9 giây; bean thử nghiệm đã được tạo với giá trị đó. Tệp profile chứa 2 giây nhưng không phải nguồn thắng.

Các endpoint của Actuator cung cấp những góc nhìn bổ sung cho nhau, không phải các bản sao thay thế được cho nhau. [Spring Boot 3.3 — các endpoint tích hợp](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html).

## 2. Mô hình cần nắm trước khi chẩn đoán

Có thể hình dung quá trình nạp cấu hình như sau:

~~~text
Nguồn cấu hình và tham số khởi động
        ↓
Profile hoạt động + các tài liệu cấu hình được chọn
        ↓
Environment phân giải thuộc tính theo độ ưu tiên
        ↓
Bind sang kiểu Java và đánh giá điều kiện ở các giai đoạn phù hợp
        ↓
Đăng ký / tạo bean
        ↓
Mã ứng dụng sử dụng cấu hình và phát sinh hành vi, log
~~~

Đây là mô hình để đặt câu hỏi, không phải khẳng định mọi bước bind và mọi điều kiện đều xảy ra theo một thứ tự tuyến tính duy nhất trong nội bộ Spring.

Ba khái niệm thường bị trộn lẫn:

- **Giá trị khai báo:** nội dung trong một nguồn, ví dụ `application-sandbox.properties` ghi `2s`.
- **Giá trị hiệu lực:** kết quả mà `Environment` phân giải sau khi xét các nguồn.
- **Giá trị đã bind:** dữ liệu đã chuyển sang kiểu Java của một đối tượng cấu hình, ví dụ `Duration` tương ứng 9.000 mili giây.

Có thêm một tầng nữa là **giá trị mà mã thực tế sử dụng**. Một thành phần có thể giữ bản sao được tạo khi khởi động, dùng hằng số hoặc đọc một đối tượng khác. Nhìn thấy giá trị trong `env` chưa chứng minh mọi thành phần đã dùng giá trị đó.

Bởi vậy, hãy đi từ câu hỏi cụ thể đến tầng bằng chứng phù hợp; chỉ đi sang tầng tiếp theo khi còn điều chưa giải thích được.

## 3. Chốt đúng lần chạy trước khi so sánh

Trước khi đọc sâu endpoint, ghi lại:

1. Ứng dụng, phiên bản và instance hoặc pod đang xét.
2. Thời điểm bắt đầu tiến trình, thời điểm lấy log và thời điểm gọi endpoint.
3. Địa chỉ và cổng quản trị thực tế; endpoint có đi qua bộ cân bằng tải không?
4. Profile được kỳ vọng và profile thực sự hoạt động.
5. Thuộc tính hoặc bean cụ thể cần kiểm tra.

Nếu log thuộc pod A còn yêu cầu HTTP được chuyển tới pod B, hai bằng chứng có thể khác nhau mà không có lỗi phân giải cấu hình. Nếu đã khởi động lại, log trước lần khởi động không mô tả trạng thái mới.

Khi so sánh nhiều instance, ưu tiên định danh instance sẵn có trong nền tảng và log; không cần tự công bố thêm dữ liệu nội bộ chỉ để phân biệt tiến trình.

Báo cáo endpoint là ảnh chụp ở thời điểm đọc, còn log mô tả sự kiện tại thời điểm phát sinh. Một log cấu hình lúc khởi động không tự thay đổi khi hệ thống sau đó có cơ chế cập nhật cấu hình.

## 4. Chuẩn bị quyền đọc và hiểu giá trị bị che

Trong một ứng dụng web Spring Boot 3.3.x có dependency Actuator, chỉ công bố các endpoint phục vụ việc kiểm tra đã được phép. Ví dụ thực hành phía dưới chạy trên loopback và giữ nguyên cơ chế che giá trị:

~~~properties
server.address=127.0.0.1
management.endpoints.web.exposure.include=health,env,configprops,conditions,beans,loggers
management.endpoint.env.show-values=never
management.endpoint.configprops.show-values=never
~~~

`enabled` và công bố qua HTTP là hai việc riêng. Nếu endpoint đã bị vô hiệu hóa hoặc bị liệt kê trong `exposure.exclude`, chỉ thêm tên vào `exposure.include` chưa đủ. Khi có Spring Security, còn phải thỏa điều kiện xác thực và phân quyền.

`env` và `configprops` mặc định che giá trị bằng `******` trong Spring Boot 3.3. Dấu sao không có nghĩa thuộc tính bị thiếu, rỗng hoặc bind thất bại. Thông tin về nguồn và vị trí khai báo có thể vẫn hữu ích để truy nguyên.

Bài thực hành không yêu cầu đặt `show-values=always`. Các dòng kiểm chứng trong chương trình chỉ in các trường đã biết là không nhạy cảm của dữ liệu giả lập. Không áp dụng cách in toàn bộ cấu hình cho mật khẩu, token, URL chứa thông tin xác thực hoặc dữ liệu cá nhân.

[Spring Boot 3.3 — che giá trị trong endpoint](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html#actuator.endpoints.sanitization).

## 5. Hai nguyên tắc về độ ưu tiên và profile

### 5.1. File được nạp chưa chắc là nguồn thắng

Trong nhóm nguồn thường dùng của một ứng dụng chạy thông thường, có thể bắt đầu kiểm tra theo quan hệ sau:

~~~text
Tham số dòng lệnh
    có thể ghi đè Java system properties (-D...)
        có thể ghi đè biến môi trường của tiến trình
            có thể ghi đè dữ liệu từ application.properties / YAML
~~~

Đây là lát cắt để điều tra, không phải toàn bộ danh sách `PropertySource` của Spring Boot. Cấu hình JSON, môi trường kiểm thử, container và các nguồn khác có thể tham gia; phải đọc nguồn thực tế được báo cáo thay vì suy luận từ sơ đồ rút gọn.

Với cùng vị trí nạp, tệp theo profile có thể ghi đè tệp chung. Tuy nhiên, việc kích hoạt profile không làm tệp profile vượt lên trên mọi biến môi trường hoặc tham số dòng lệnh.

Ví dụ về cách đặt system property và tham số ứng dụng:

~~~shell
java -Ddemo.client.timeout=5s -jar app.jar --demo.client.timeout=700ms
~~~

`-D...` nằm trước `-jar`; `--demo.client.timeout=...` là tham số ứng dụng. Trong cách chạy Spring Boot mặc định này, tham số ứng dụng thắng. Không đặt `-D...` sau tên JAR rồi mặc định coi nó là system property.

Tên biến môi trường tương ứng với `demo.client.timeout` là `DEMO_CLIENT_TIMEOUT`. Với tên có dấu gạch ngang, cần tuân theo quy tắc ánh xạ của Spring Boot, không máy móc thay mọi ký tự bằng dấu gạch dưới.

[Spring Boot 3.3 — nguồn cấu hình và độ ưu tiên](https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html).

### 5.2. Profile là lựa chọn cấu hình, không phải tên môi trường suy đoán

Đối chiếu profile từ log khởi động và danh sách `activeProfiles` của endpoint `env`. Một biến trong công cụ triển khai ghi “production” không tự chứng minh Spring đang kích hoạt profile tên `production`.

Nếu không có profile được kích hoạt tường minh, `activeProfiles` có thể là mảng rỗng trong khi profile mặc định vẫn được dùng. Ngoài ra, include hoặc nhóm profile có thể làm tập profile hoạt động nhiều hơn một tên được truyền vào.

`@Profile("sandbox")` giới hạn cấu hình Java theo profile. `application-sandbox.properties` là tài liệu thuộc tính được chọn theo profile. Hai cơ chế có liên quan nhưng không đồng nhất: có thuộc tính phù hợp không tự làm một lớp Java có profile khác được nạp.

Các khóa kích hoạt như `spring.profiles.active` không được đặt trong chính tệp cấu hình dành riêng cho profile. Hãy chọn profile từ nguồn hợp lệ và kiểm tra kết quả sau khi khởi động. [Spring Boot 3.3 — profile](https://docs.spring.io/spring-boot/3.3/reference/features/profiles.html).

## 6. Dự án thực hành: một thuộc tính đi qua nhiều nguồn

Dùng JDK 21 và Gradle 8.5. Ví dụ cố định Spring Boot 3.3.0 để tái lập hành vi trong dòng 3.3; đây không phải chỉ dẫn thay đổi phiên bản của hệ thống đang vận hành.

Cấu trúc tệp cần tạo:

~~~text
actuator-correlation-lab/
├── settings.gradle
├── build.gradle
└── src/main/
    ├── java/demo/DiagnosticCorrelationApplication.java
    └── resources/
        ├── application.properties
        └── application-sandbox.properties
~~~

### 6.1. Build và hai nguồn thuộc tính

`settings.gradle`:

~~~groovy
rootProject.name = 'actuator-correlation-lab'
~~~

`build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.0'
    id 'io.spring.dependency-management' version '1.1.5'
}

version = '1.0.0'

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
}
~~~

`src/main/resources/application.properties`:

~~~properties
server.address=127.0.0.1
management.endpoints.web.exposure.include=health,env,configprops,conditions,beans,loggers
management.endpoint.env.show-values=never
management.endpoint.configprops.show-values=never
logging.level.demo=INFO
demo.client.enabled=false
demo.client.timeout=1s
~~~

`src/main/resources/application-sandbox.properties`:

~~~properties
demo.client.enabled=true
demo.client.timeout=2s
~~~

Trong tệp chung, tính năng bị tắt và timeout là 1 giây. Tệp sandbox đổi thành bật tính năng và 2 giây. Chưa có cấu hình gửi dữ liệu ra dịch vụ ngoài.

### 6.2. Chương trình đầy đủ

`src/main/java/demo/DiagnosticCorrelationApplication.java`:

~~~java
package demo;

import java.time.Duration;
import java.util.Arrays;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.ObjectProvider;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.SpringBootConfiguration;
import org.springframework.boot.autoconfigure.EnableAutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Import;
import org.springframework.context.annotation.Profile;
import org.springframework.core.env.Environment;

@SpringBootConfiguration(proxyBeanMethods = false)
@EnableAutoConfiguration
@EnableConfigurationProperties(DiagnosticCorrelationApplication.ClientProperties.class)
@Import(DiagnosticCorrelationApplication.SandboxClientConfiguration.class)
public class DiagnosticCorrelationApplication {

    private static final Logger LOG =
        LoggerFactory.getLogger(DiagnosticCorrelationApplication.class);

    public static void main(String[] args) {
        SpringApplication.run(DiagnosticCorrelationApplication.class, args);
    }

    @Bean
    ApplicationRunner diagnosticSnapshot(
            Environment environment,
            ClientProperties properties,
            ObjectProvider<DemoClient> clients) {
        return args -> {
            String status = clients.getIfAvailable() == null ? "absent" : "present";
            System.out.printf(
                "DIAG profiles=%s enabled=%s timeoutMs=%d client=%s%n",
                Arrays.toString(environment.getActiveProfiles()),
                properties.enabled(),
                properties.timeout().toMillis(),
                status
            );
            LOG.debug("DIAG_DETAIL snapshotCompleted=true");
        };
    }

    @ConfigurationProperties(prefix = "demo.client")
    public record ClientProperties(boolean enabled, Duration timeout) {
    }

    public record DemoClient(Duration timeout) {
    }

    @Configuration(proxyBeanMethods = false)
    @Profile("sandbox")
    public static class SandboxClientConfiguration {

        @Bean
        @ConditionalOnProperty(
            prefix = "demo.client", name = "enabled", havingValue = "true"
        )
        DemoClient demoClient(ClientProperties properties) {
            return new DemoClient(properties.timeout());
        }
    }
}
~~~

Vai trò của các phần trong mã:

- `ClientProperties` là dữ liệu cấu hình có kiểu; `Duration` giúp phân biệt giá trị thời gian với một số chưa rõ đơn vị.
- `SandboxClientConfiguration` chỉ được nạp khi profile `sandbox` hoạt động.
- `demoClient` còn yêu cầu `demo.client.enabled=true`.
- `DemoClient` là đối tượng mô phỏng lưu timeout, không thực hiện cuộc gọi mạng.
- Runner in một dòng stdout gồm profile, cờ bật, timeout đã bind và sự hiện diện của client.
- Một thông điệp DEBUG riêng giúp kiểm tra ảnh hưởng của mức log.

Dòng `DIAG` dùng `System.out` nên không bị lọc theo mức của logger. Dòng `DIAG_DETAIL` đi qua SLF4J và phụ thuộc cấu hình logging. Cố ý tách hai đường này để có mốc kiểm chứng ngay cả khi DEBUG bị ẩn.

Ví dụ dùng `@SpringBootConfiguration` + `@EnableAutoConfiguration` và nhập cấu hình Java cụ thể bằng `@Import`. Không có quét component ngầm cần suy đoán.

### 6.3. Đóng gói và chuẩn bị terminal

Tại thư mục dự án, tạo wrapper bằng Gradle 8.5 nếu chưa có:

~~~shell
gradle wrapper --gradle-version 8.5
~~~

Sau đó trên PowerShell:

~~~powershell
java -version
.\gradlew.bat bootJar
~~~

Lệnh `java` dùng để chạy JAR cần trỏ đến JDK 21. Lần đầu build cần truy cập kho plugin và Maven Central. Các lớp Spring cần dependency của dự án, vì vậy không biên dịch tệp Java này bằng một lệnh `javac` không có classpath.

Trong terminal thử nghiệm riêng, bỏ biến timeout của các lần thử trước:

~~~powershell
Remove-Item -LiteralPath Env:DEMO_CLIENT_TIMEOUT -ErrorAction SilentlyContinue
~~~

Biến môi trường rỗng và biến không tồn tại là hai trạng thái khác nhau; không đặt `$env:DEMO_CLIENT_TIMEOUT=""` để mô phỏng việc biến hoàn toàn không được khai báo.

Mỗi thí nghiệm dưới đây cần dừng tiến trình trước đó bằng Ctrl+C. Gọi endpoint từ terminal thứ hai, sau khi ứng dụng đã khởi động xong.

## 7. Lấy bộ bằng chứng gọn cho mỗi lần chạy

Các ví dụ dùng cổng 8080 và đường dẫn quản trị mặc định. Nếu hệ thống đổi cổng quản trị, base path hoặc có proxy, dùng địa chỉ thực tế của instance đã xác định.

### 7.1. Đọc đúng một thuộc tính từ env

~~~powershell
$base = 'http://127.0.0.1:8080/actuator'
$timeoutReport = Invoke-RestMethod "$base/env/demo.client.timeout"

$timeoutReport.activeProfiles
$timeoutReport.defaultProfiles
$timeoutReport.property | Format-List

$timeoutReport.propertySources |
    Where-Object { $null -ne $_.property } |
    Select-Object name, @{
        Name = 'origin'
        Expression = { $_.property.origin }
    }
~~~

Ở phản hồi cho **một thuộc tính**:

- `property.source` là nguồn của kết quả phân giải.
- `property.value` có thể bị che.
- `propertySources` cho biết các nguồn liên quan theo thứ tự ưu tiên; đọc thêm `origin` nếu có.
- Không nhầm cấu trúc `propertySources[].property` của phản hồi này với `propertySources[].properties` khi đọc toàn bộ `/env`.

Không phải nguồn nào cũng có tệp và số dòng. Biến môi trường hoặc tham số dòng lệnh có thể được mô tả bằng tên nguồn hoặc tên biến. [Spring Boot 3.3 — truy vấn một thuộc tính](https://docs.spring.io/spring-boot/3.3/api/rest/actuator/env.html).

### 7.2. Xem đối tượng cấu hình đã bind

~~~powershell
$boundReport = Invoke-RestMethod "$base/configprops/demo.client"
$boundReport.contexts.PSObject.Properties.Name

$boundReport.contexts.application.beans.PSObject.Properties |
    Where-Object { $_.Value.prefix -eq 'demo.client' } |
    ForEach-Object {
        $_.Name
        $_.Value | ConvertTo-Json -Depth 10
    }
~~~

Các lệnh phía sau dùng context `application` của dự án thực hành. Với ứng dụng có ID khác hoặc nhiều context, chọn đúng ID vừa liệt kê thay vì cố định tên đó.

Đọc `prefix`, `properties` và `inputs`. `inputs` có thể giữ nguồn gốc dữ liệu dùng khi bind; `properties` phản ánh dạng thuộc tính của đối tượng Java. Tên bean thường chứa prefix và tên kiểu, nên lọc theo `prefix` thay vì chép cứng toàn bộ tên.

Với cấu hình che giá trị của bài, có thể thấy:

~~~json
{
  "prefix": "demo.client",
  "properties": {
    "enabled": "******",
    "timeout": "******"
  },
  "inputs": {
    "timeout": {
      "value": "******",
      "origin": "System Environment Property \"DEMO_CLIENT_TIMEOUT\""
    }
  }
}
~~~

Đoạn JSON đã lược bớt trường; origin này tương ứng tình huống biến môi trường ở phần sau. Giá trị bị che không ngăn việc nhận ra nguồn dữ liệu đã tham gia bind. Dòng `DIAG` của chương trình cung cấp mốc so sánh cho những trường không nhạy cảm trong ví dụ.

`configprops` không phải báo cáo cho mọi field, mọi `@Value` hoặc mọi hằng số trong mã. [Spring Boot 3.3 — configprops theo prefix](https://docs.spring.io/spring-boot/3.3/api/rest/actuator/configprops.html).

### 7.3. Đối chiếu định nghĩa bean và điều kiện

~~~powershell
$beanReport = Invoke-RestMethod "$base/beans"
$beanReport.contexts.application.beans.demoClient

$conditionReport = Invoke-RestMethod "$base/conditions"
foreach ($side in @('positiveMatches', 'negativeMatches')) {
    $conditionReport.contexts.application.$side.PSObject.Properties |
        Where-Object { $_.Name -like '*SandboxClientConfiguration*' } |
        ForEach-Object {
            $side
            $_.Name
            $_.Value | ConvertTo-Json -Depth 10
        }
}
~~~

`beans` giúp đối chiếu tên, kiểu, phạm vi và các phụ thuộc được báo cáo của bean. Nó không thay thế một phép thử hành vi; đặc biệt không suy ra dịch vụ bên ngoài khỏe chỉ vì có định nghĩa client.

Trong `conditions`, đọc thông báo ở đúng lớp hoặc phương thức. Với negative, tìm lý do ở `notMatched`; các điều kiện đã khớp có thể vẫn được liệt kê bên cạnh. Không dùng số lượng negative làm thước đo số lỗi của ứng dụng.

Có một giới hạn quan trọng cho bài này: không mặc định mọi kết quả `@Profile` đều xuất hiện thành dòng dễ tìm trong báo cáo điều kiện của Spring Boot. Nếu lớp bị loại do profile, hãy đối chiếu chính `@Profile`, tập profile hoạt động và bằng chứng bean; đừng đòi phải có một dòng negative của phương thức bên trong.

[Spring Boot 3.3 — cấu trúc beans](https://docs.spring.io/spring-boot/3.3/api/rest/actuator/beans.html), [báo cáo conditions](https://docs.spring.io/spring-boot/3.3/api/rest/actuator/conditions.html).

### 7.4. Kiểm tra mức log có hiệu lực

~~~powershell
Invoke-RestMethod "$base/loggers/demo.DiagnosticCorrelationApplication"
~~~

`configuredLevel` là mức đặt trực tiếp cho logger đó, nếu có; `effectiveLevel` là mức thực sự có hiệu lực. `configuredLevel=null` không có nghĩa logging bị tắt: logger có thể kế thừa từ logger cha.

Endpoint `loggers` mô tả cấu hình mức log, không trả lại các dòng log đã phát sinh. Khi thiếu một thông điệp, còn phải kiểm tra thời điểm thực thi, logger đúng tên, appender, bộ lọc và hệ thống thu gom log.

Phần thực hành chỉ dùng GET để quan sát. [Spring Boot 3.3 — đọc mức của một logger](https://docs.spring.io/spring-boot/3.3/api/rest/actuator/loggers.html).

## 8. Bảy tình huống để nối các bằng chứng

### A. Chạy không kích hoạt profile

~~~powershell
java -jar build/libs/actuator-correlation-lab-1.0.0.jar
~~~

Dòng stdout do runner tạo ra:

~~~text
DIAG profiles=[] enabled=false timeoutMs=1000 client=absent
~~~

Đối chiếu:

- Log khởi động cho biết không có profile được chọn tường minh và có sử dụng profile mặc định.
- `env` cho thấy timeout đến từ `application.properties`.
- `configprops` có bean cấu hình prefix `demo.client`.
- `DemoClient` không xuất hiện vì cấu hình Java yêu cầu `sandbox` chưa được chọn.
- Dòng DEBUG của ví dụ chưa hiện vì mức hiệu lực đang là INFO.

Mảng profile rỗng ở stdout được tạo từ `getActiveProfiles()`; không dùng nó để kết luận Spring không có khái niệm profile mặc định.

### B. Chọn sandbox để nạp cấu hình theo profile

~~~powershell
java -jar build/libs/actuator-correlation-lab-1.0.0.jar --spring.profiles.active=sandbox
~~~

~~~text
DIAG profiles=[sandbox] enabled=true timeoutMs=2000 client=present
~~~

Bằng chứng cần khớp:

- Profile của endpoint và log khởi động đều chứa `sandbox`.
- Nguồn timeout là `application-sandbox.properties`.
- `inputs.timeout.origin` của cấu hình đã bind chỉ về tệp profile.
- Phương thức `SandboxClientConfiguration#demoClient` có điều kiện thuộc tính khớp.
- Endpoint `beans` có `demoClient` và runner đã nhận được đối tượng đó.

`2s` và `2000` trong trường `timeoutMs` không phải hai cấu hình khác nhau: một bên là chuỗi đầu vào có đơn vị, một bên là biểu diễn sau khi bind và đổi sang mili giây.

### C. Biến môi trường ghi đè timeout trong tệp profile

Trong terminal chạy ứng dụng, đặt biến rồi khởi động lại:

~~~powershell
$env:DEMO_CLIENT_TIMEOUT = '9s'
java -jar build/libs/actuator-correlation-lab-1.0.0.jar --spring.profiles.active=sandbox
~~~

~~~text
DIAG profiles=[sandbox] enabled=true timeoutMs=9000 client=present
~~~

Tệp sandbox vẫn ghi 2 giây. Việc nó vẫn được nạp không khiến 2 giây thắng biến môi trường.

Ở lần này:

- `env/demo.client.timeout` báo nguồn `systemEnvironment`.
- `configprops` có thể báo origin mang tên `DEMO_CLIENT_TIMEOUT`.
- Runner nhận `Duration` tương ứng 9.000 mili giây.
- Profile và điều kiện tạo client không đổi so với B.

Nếu chỉ mở tệp trên đĩa rồi sửa 2 giây thành 3 giây, bạn đang sửa một nguồn có độ ưu tiên thấp hơn nguồn thắng hiện tại.

### D. Tham số dòng lệnh ghi đè biến môi trường

Giữ biến môi trường 9 giây từ C, dừng ứng dụng rồi chạy:

~~~powershell
java -jar build/libs/actuator-correlation-lab-1.0.0.jar --spring.profiles.active=sandbox --demo.client.timeout=700ms
~~~

~~~text
DIAG profiles=[sandbox] enabled=true timeoutMs=700 client=present
~~~

Bây giờ nguồn thắng là `commandLineArgs`. Biến môi trường vẫn tồn tại nhưng không còn quyết định timeout. Đối chiếu cùng lúc nguồn trong `env`, origin dùng để bind và dòng kiểm chứng.

Sự hiện diện của một nguồn trong danh sách không có nghĩa nguồn đó thắng; cũng không xóa được nguyên nhân bằng cách chỉ sửa tệp profile.

### E. Tắt thuộc tính khi profile vẫn đúng

Giữ biến timeout 9 giây, chạy lại:

~~~powershell
java -jar build/libs/actuator-correlation-lab-1.0.0.jar --spring.profiles.active=sandbox --demo.client.enabled=false
~~~

~~~text
DIAG profiles=[sandbox] enabled=false timeoutMs=9000 client=absent
~~~

Lần này việc thiếu client không đến từ sai profile. Truy vấn thêm cờ bật:

~~~powershell
Invoke-RestMethod "$base/env/demo.client.enabled"
~~~

Cần nối được:

1. `sandbox` đang hoạt động.
2. Cờ bật hiệu lực đến từ `commandLineArgs`.
3. Đối tượng cấu hình nhận `enabled=false`.
4. `OnPropertyCondition` của phương thức `demoClient` không khớp.
5. Bean client không có, phù hợp dòng stdout.

Timeout vẫn bind thành 9 giây dù client không được tạo. Có đối tượng cấu hình không đồng nghĩa có mọi bean sử dụng đối tượng đó.

### F. Thuộc tính đúng nhưng profile không phù hợp

Bỏ biến timeout trong terminal thử nghiệm:

~~~powershell
Remove-Item -LiteralPath Env:DEMO_CLIENT_TIMEOUT -ErrorAction SilentlyContinue
java -jar build/libs/actuator-correlation-lab-1.0.0.jar --spring.profiles.active=prod --demo.client.enabled=true
~~~

~~~text
DIAG profiles=[prod] enabled=true timeoutMs=1000 client=absent
~~~

Dự án không có tệp `application-prod.properties`; thuộc tính chung vẫn cung cấp timeout 1 giây. Cờ bật từ dòng lệnh đã là true nhưng cấu hình Java chỉ dành cho `sandbox`, nên vẫn không có client.

Đây là tình huống không thể giải thích chỉ bằng một truy vấn `env/demo.client.enabled`. Cần thêm profile thực sự hoạt động và điều kiện `@Profile` trong mã. Nguồn phương thức `demoClient` có thể không được ghi nhận trong báo cáo `conditions` vì cấu hình bao ngoài đã không tham gia.

Không “sửa” bằng cách bật lại cờ vốn đã true. Trước hết xác nhận ứng dụng cần chạy cấu hình nào, rồi chọn profile hoặc thiết kế điều kiện đúng với yêu cầu.

### G. Chỉ đổi mức log để quan sát DEBUG

Sau F, biến timeout đã được bỏ. Chạy lại với sandbox và bật DEBUG cho package của ví dụ:

~~~powershell
java -jar build/libs/actuator-correlation-lab-1.0.0.jar --spring.profiles.active=sandbox --logging.level.demo=DEBUG
~~~

Dòng stdout vẫn là:

~~~text
DIAG profiles=[sandbox] enabled=true timeoutMs=2000 client=present
~~~

Ngoài ra, phần message của một dòng DEBUG là:

~~~text
DIAG_DETAIL snapshotCompleted=true
~~~

Định dạng log đầy đủ có thời gian, PID và thông tin khác tùy cấu hình; đoạn trên chỉ là message do chương trình phát ra.

GET logger riêng của lớp cho thấy `effectiveLevel=DEBUG`. Mức cấu hình trực tiếp của lớp vẫn có thể là null vì thiết lập được đặt ở logger cha `demo`.

Thay đổi khả năng quan sát không đồng nghĩa thay đổi timeout, profile hay điều kiện tạo bean. Việc message chỉ xuất hiện sau khi bật DEBUG không chứng minh runner mới bắt đầu chạy; dòng stdout trước đó đã là bằng chứng runner được thực thi.

[Spring Boot 3.3 — cấu hình mức log](https://docs.spring.io/spring-boot/3.3/reference/features/logging.html#features.logging.log-levels).

### Bảng đối chiếu các lần chạy

| Lần chạy | Profile hoạt động | Nguồn timeout thắng | Timeout đã bind, ms | Client | Điểm cần giải thích |
| --- | --- | --- | ---: | --- | --- |
| A | Không chọn tường minh | Tệp chung | 1000 | absent | Cấu hình Java theo sandbox chưa tham gia |
| B | sandbox | Tệp sandbox | 2000 | present | Tệp theo profile và điều kiện thuộc tính phù hợp |
| C | sandbox | systemEnvironment | 9000 | present | Biến môi trường ghi đè tệp |
| D | sandbox | commandLineArgs | 700 | present | Dòng lệnh ghi đè biến môi trường |
| E | sandbox | systemEnvironment | 9000 | absent | Cờ enabled bị dòng lệnh đổi thành false |
| F | prod | Tệp chung | 1000 | absent | Cờ bật đúng nhưng profile Java không phù hợp |
| G | sandbox | Tệp sandbox | 2000 | present | DEBUG thay đổi khả năng thấy message |

Bảng giả định chỉ có các nguồn đã nêu và các bước dọn biến được thực hiện đúng. Nếu kết quả khác, đó là lý do để đọc nguồn hiệu lực, không phải để sửa bảng trước khi tìm nguyên nhân.

## 9. Áp dụng thành quy trình chẩn đoán một sự cố thật

Giả sử yêu cầu là “client phải có timeout 2 giây” nhưng log kiểm chứng cho thấy 9 giây.

Thực hiện theo thứ tự:

1. **Chốt đối tượng so sánh.** Xác nhận endpoint và log thuộc cùng phiên bản, instance và lần chạy.
2. **Xác nhận profile.** Đối chiếu log khởi động, `activeProfiles` và cấu hình Java có `@Profile` liên quan.
3. **Truy một khóa.** Dùng `env/<tên-thuộc-tính>` để tìm nguồn thắng và các origin cạnh tranh.
4. **Kiểm tra bind.** Tìm đúng prefix trong `configprops`; phân biệt dữ liệu đầu vào, kiểu Java và giá trị bị che.
5. **Kiểm tra thành phần.** Đọc điều kiện liên quan và đối chiếu tên/kiểu bean trong context.
6. **Kiểm tra hành vi và log.** Xác định thành phần có dùng đối tượng cấu hình đó không; đối chiếu thời điểm, mức log và phép thử phù hợp.
7. **Thay một yếu tố rồi kiểm chứng lại.** Ví dụ bỏ nguồn ghi đè không mong muốn theo quy trình triển khai, khởi động lại nếu cần, rồi lấy lại cùng bộ bằng chứng.

Một ghi nhận chẩn đoán tốt cho tình huống C có thể là:

> Instance đang xét chạy sandbox. Tệp profile khai báo 2 giây nhưng env báo systemEnvironment là nguồn timeout thắng; configprops ghi nhận đầu vào từ DEMO_CLIENT_TIMEOUT và dòng kiểm chứng cho thấy 9.000 ms. Bean client tồn tại. Nguyên nhân lệch kỳ vọng là nguồn biến môi trường ghi đè, chưa có bằng chứng lỗi đọc tệp profile.

Không cần đưa nguyên bản toàn bộ môi trường hay bí mật vào báo cáo. Chỉ ghi tên khóa, nguồn, giá trị không nhạy cảm đã được phép và bằng chứng cần thiết.

Đối với ví dụ, client chỉ là một record. Sự hiện diện của nó không chứng minh một máy chủ từ xa đáp ứng trong timeout; yêu cầu đó cần một phép thử kết nối và hành vi thực tế riêng.

## 10. Khi các bằng chứng có vẻ mâu thuẫn

| Quan sát | Hướng kiểm tra |
| --- | --- |
| Tệp đã sửa nhưng env chưa đổi | Tiến trình đã nạp lại chưa; có nguồn ưu tiên cao hơn; có đọc đúng tệp và đúng instance không |
| env đúng nhưng đối tượng cấu hình khác kỳ vọng | Prefix, kiểu dữ liệu, đơn vị, origin dùng khi bind, giá trị mặc định, bản sao giữ từ lúc khởi tạo |
| configprops có dữ liệu nhưng bean chức năng thiếu | Profile, điều kiện lớp/phương thức, đăng ký cấu hình và context |
| conditions khớp nhưng chức năng lỗi | Lỗi tạo bean, khởi tạo trễ, dependency bên ngoài hoặc lỗi lúc sử dụng; đọc exception và hành vi |
| Không tìm thấy một nguồn trong conditions | Cấu hình có được xử lý không; điều kiện ở lớp bao ngoài; không mặc định mọi điều kiện Spring đều được báo cáo |
| DEBUG không có nhưng stdout của runner có | Mức logger hiệu lực, logger cha, appender/filter và hệ thống thu log |
| env/configprops chỉ có dấu sao | Cơ chế che dữ liệu; tiếp tục truy nguồn/origin hoặc dùng bằng chứng không nhạy cảm đã được phép |
| Endpoint trả 404/401/403 | Đường dẫn, cổng, bật/công bố endpoint và quyền truy cập trước khi suy luận về cấu hình nghiệp vụ |

Không mặc định việc gọi lại GET sẽ bind lại một record hoặc dựng lại một bean. Trong ứng dụng Spring Boot thông thường không có cơ chế refresh bổ sung, thay tệp hoặc thay môi trường của terminal không tự cấu hình lại tiến trình đã chạy. Khởi động lại theo quy trình của ứng dụng rồi lấy dữ liệu mới.

Nếu ứng dụng lỗi trước khi HTTP server sẵn sàng, endpoint chưa phải nguồn có thể truy cập. Đọc log khởi động, lỗi bind và chuỗi nguyên nhân exception. Có thể dùng `--debug` để bổ sung báo cáo điều kiện trong log; không nhầm nó với việc đặt toàn bộ logger ứng dụng ở DEBUG hoặc tự mở quyền truy cập endpoint.

Khi cần lần theo tài liệu cấu hình được nạp, có thể bật tạm log có phạm vi hẹp cho `org.springframework.boot.context.config` ở mức TRACE trong môi trường được phép. Kiểm soát thời gian bật và dữ liệu ghi ra; không dùng log chi tiết toàn hệ thống làm bước đầu tiên cho mọi sự cố.

## 11. Tự kiểm tra

**Câu 1:** Profile sandbox đã hoạt động, tệp sandbox có 2 giây, nhưng timeout đã bind là 9 giây. Có đủ bằng chứng kết luận tệp sandbox không được nạp không?

Chưa. Kiểm tra nguồn thắng và origin. Tệp vẫn có thể được nạp nhưng bị biến môi trường ghi đè.

**Câu 2:** `enabled=true` xuất hiện trong dữ liệu cấu hình, vậy client chắc chắn có mặt?

Không. Tình huống F cho thấy profile của cấu hình Java vẫn có thể loại bean.

**Câu 3:** `configuredLevel` của logger là null, vậy DEBUG chắc chắn bị tắt?

Không. Phải đọc `effectiveLevel` vì logger có thể kế thừa mức từ cha.

**Câu 4:** `configprops` hiển thị timeout là `******`, vậy phải đặt show-values=always mới chẩn đoán được?

Không. Nguồn, origin, profile, cấu hình logger và mốc kiểm chứng không nhạy cảm có thể đã đủ. Quyền đọc giá trị thật phải theo chính sách của hệ thống.

**Câu 5:** Sau khi đổi biến môi trường trong terminal, ứng dụng đang chạy vẫn giữ giá trị cũ. Điều đó có bất thường không?

Không nhất thiết. Tiến trình đã khởi động có môi trường riêng; đối tượng cấu hình và bean cũng đã được tạo theo lần nạp tương ứng.

**Bài tập:** Chạy lại C, D và F. Với mỗi lần, ghi một đoạn giải thích có đủ profile, nguồn thuộc tính, dữ liệu đã bind, tình trạng bean và bằng chứng log. Chỉ ra điều gì đã được chứng minh và điều gì vẫn cần phép thử hành vi. Mục tiêu là có một chuỗi lập luận kiểm tra lại được, thay vì một ảnh chụp endpoint đứng riêng.
