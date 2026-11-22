# Đọc endpoint conditions để giải thích cấu hình tự động khớp hoặc không khớp

## 1. Từ câu hỏi “vì sao bean này có hoặc không có?” đến báo cáo điều kiện

Một ứng dụng có thư viện cần thiết nhưng vẫn không tạo bean bạn mong đợi. Ở ứng dụng khác, bean mặc định biến mất sau khi bạn khai báo bean riêng. Chỉ nhìn dependency hoặc tệp cấu hình chưa đủ để giải thích hai tình huống đó.

Cấu hình tự động (auto-configuration) của Spring Boot là những cấu hình có điều kiện. Một cấu hình có thể đòi hỏi một lớp tồn tại, một thuộc tính có giá trị phù hợp, ứng dụng chạy theo mô hình web nhất định hoặc chưa có bean thay thế. Endpoint `conditions` cho biết những điều kiện được ghi nhận đã khớp hay không khớp và lý do đi kèm.

Mục tiêu của bài là đọc một báo cáo để lập luận được:

> Trong context nào, điều kiện của cấu hình hoặc phương thức nào đã được đánh giá, kết quả là gì, và cần kiểm tra bằng chứng nào tiếp theo?

Cần phân biệt ba tầng bằng chứng:

| Câu hỏi | Bằng chứng phù hợp |
| --- | --- |
| Vì sao cấu hình có thể tham gia hoặc phải nhường lại? | `conditions` và thông báo của điều kiện |
| Bean nào thực sự được đăng ký? | Danh sách bean trong context, có thể đối chiếu endpoint `beans` |
| Chức năng có hoạt động đúng khi sử dụng không? | Lời gọi thực tế, kiểm thử, log hoặc kiểm tra sức khỏe phù hợp |

Một dòng khớp trong báo cáo không chứng minh kết nối cơ sở dữ liệu thành công, không chứng minh mọi bean con đều tồn tại và không chứng minh ứng dụng có thể phục vụ mọi yêu cầu.

[Spring Boot 3.3 — ý nghĩa endpoint conditions](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html).

## 2. Lấy được báo cáo trước khi đọc nội dung

Trong một ứng dụng web Spring Boot 3.3.x đã có `spring-boot-starter-actuator`, cấu hình tối thiểu cho bài thực hành cục bộ là:

~~~properties
server.address=127.0.0.1
management.endpoint.conditions.enabled=true
management.endpoints.web.exposure.include=health,conditions
~~~

Hai thuộc tính management giải quyết hai việc khác nhau:

- `enabled` cho phép endpoint tồn tại.
- `exposure.include` đưa endpoint ra giao thức HTTP.

Bật endpoint chưa đồng nghĩa với công bố endpoint qua HTTP. Trong Spring Boot 3.3, mặc định chỉ `health` được công bố. Nếu `exposure.exclude` đồng thời có `conditions`, thiết lập loại trừ được ưu tiên. Các cấu hình trên không tự cấp quyền truy cập qua Spring Security.

Với cổng và đường dẫn mặc định:

~~~shell
curl -i http://127.0.0.1:8080/actuator/conditions
~~~

Trên Windows PowerShell, có thể dùng `curl.exe` để gọi đúng chương trình curl. Phân loại kết quả trước khi kết luận:

| Kết quả | Kiểm tra trước |
| --- | --- |
| HTTP 200 và JSON có `contexts` | Bắt đầu đọc báo cáo |
| HTTP 404 | Dependency Actuator, bật/công bố endpoint, đường dẫn, cổng và proxy |
| HTTP 401 hoặc 403 | Cơ chế xác thực, phân quyền và các lớp kiểm soát truy cập |
| Không kết nối được | Tiến trình, cổng lắng nghe, địa chỉ bind, giao thức và mạng |

HTTP 404 không phải là một mục `negativeMatches`. HTTP 403 cũng không chứng minh cấu hình tự động không khớp.

Nếu ứng dụng dùng `management.server.port`, `management.endpoints.web.base-path` hoặc đường dẫn ngữ cảnh riêng, phải gọi địa chỉ thực tế. Ví dụ trong bài dùng một ứng dụng cục bộ chưa có Spring Security và không có proxy. Khi áp dụng vào hệ thống khác, giữ chính sách bảo vệ endpoint của hệ thống đó; báo cáo có thể lộ tên lớp, bean và thuộc tính nội bộ.

[Spring Boot 3.3 — bật, công bố và bảo vệ endpoint](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html#actuator.endpoints.exposing).

## 3. Đọc đúng cấu trúc JSON

Bắt đầu từ `contexts`. Mỗi khóa bên dưới là ID của một application context. Không mặc định mọi ứng dụng đều chỉ có context tên `application`.

| Thành phần | Cách đọc |
| --- | --- |
| `contexts.<id>.positiveMatches` | Nguồn cấu hình hoặc phương thức có các điều kiện được ghi nhận là khớp |
| `positiveMatches.<source>[]` | Danh sách các cặp `condition` / `message` cho nguồn đó |
| `contexts.<id>.negativeMatches` | Nguồn có điều kiện không khớp |
| `negativeMatches.<source>.notMatched[]` | Những điều kiện được ghi nhận không khớp; đây là nơi tìm nguyên nhân chặn |
| `negativeMatches.<source>.matched[]` | Những điều kiện đã khớp trên cùng nguồn, dù nguồn vẫn có điều kiện không khớp |
| `contexts.<id>.unconditionalClasses` | Các lớp cấu hình tự động được báo cáo là không có điều kiện |
| `contexts.<id>.parentId` | ID context cha, nếu có |

`condition` là tên bộ kiểm tra, chẳng hạn `OnPropertyCondition`. `message` mới mô tả thuộc tính, lớp hoặc bean cụ thể khiến điều kiện khớp hay không khớp. Chỉ đếm số mục positive/negative sẽ bỏ mất thông tin chẩn đoán quan trọng.

Tên nguồn thường có hai dạng:

~~~text
ReportAutoConfiguration
ReportAutoConfiguration#defaultReportClient
~~~

Dạng đầu nói về lớp cấu hình; dạng sau nói về phương thức trong lớp. Ký hiệu `#` không phải đường dẫn HTTP. Tên đầy đủ, tên lớp lồng nhau và cách rút gọn tên có thể khác giữa các nguồn hoặc phiên bản; tìm theo phần tên ổn định rồi đọc khóa thực tế.

Báo cáo có thể chứa lớp cấu hình thông thường sử dụng điều kiện của Spring Boot, không chỉ các lớp có hậu tố `AutoConfiguration`. Đây cũng không phải danh sách đầy đủ mọi bean hoặc mọi annotation điều kiện của Spring.

[Spring Boot 3.3 — cấu trúc phản hồi conditions](https://docs.spring.io/spring-boot/3.3/api/rest/actuator/conditions.html#actuator.conditions.retrieving.response-structure).

## 4. Một ví dụ JSON và cách giải thích có căn cứ

Đây là JSON minh họa đã rút gọn để học cách đọc, không phải toàn bộ phản hồi của một ứng dụng:

~~~json
{
  "contexts": {
    "application": {
      "positiveMatches": {
        "ReportAutoConfiguration#defaultReportClient": [
          {
            "condition": "OnBeanCondition",
            "message": "No ReportClient bean was found"
          }
        ]
      },
      "negativeMatches": {
        "AuditAutoConfiguration": {
          "notMatched": [
            {
              "condition": "OnPropertyCondition",
              "message": "demo.audit.enabled does not have the required value true"
            }
          ],
          "matched": [
            {
              "condition": "OnClassCondition",
              "message": "Required AuditClient class was found"
            }
          ]
        }
      },
      "unconditionalClasses": []
    }
  }
}
~~~

Các câu trong `message` ở ví dụ này được diễn đạt lại để dễ học; không dùng chúng làm chuỗi đối chiếu chính xác với Spring Boot.

Có thể kết luận:

1. Điều kiện thiếu bean tại phương thức `defaultReportClient` đã khớp: tại lúc kiểm tra, không thấy bean thỏa tiêu chí.
2. `AuditAutoConfiguration` có điều kiện về lớp đã khớp.
3. Điều kiện về giá trị thuộc tính của `AuditAutoConfiguration` không khớp, nên việc tìm thấy lớp chưa đủ để cấu hình này tham gia.
4. Muốn biết giá trị thuộc tính hiệu lực đến từ đâu, phải kiểm tra môi trường cấu hình; báo cáo này chưa trả lời nguồn ghi đè.

Không thể kết luận “ứng dụng lỗi vì có negative”. Một ứng dụng bình thường có thể loại bỏ nhiều cấu hình không phù hợp với dependency, mô hình web hoặc lựa chọn tính năng hiện tại.

### Đọc kết quả của điều kiện phủ định

Đặc biệt chú ý `@ConditionalOnMissingBean`:

| Điều quan sát được | Kết quả điều kiện |
| --- | --- |
| Không tìm thấy bean thỏa tiêu chí | Điều kiện “thiếu bean” khớp |
| Đã có bean thỏa tiêu chí | Điều kiện “thiếu bean” không khớp |

Vì vậy, `did not find any beans` có thể nằm trong positive. Ngược lại, thông báo tìm thấy bean có thể nằm trong negative. Phải đọc theo ý nghĩa annotation thay vì suy luận từ từ “found” hoặc “missing”.

Với cấu hình tự động, việc không tạo bean mặc định vì người dùng đã cung cấp bean phù hợp thường là hành vi nhường lại (back off) đúng thiết kế. Điều kiện xét các định nghĩa bean đã được xử lý tại thời điểm đánh giá, cùng kiểu, tên và phạm vi tìm kiếm được khai báo; không nên diễn giải thành một phép tìm kiếm độc lập với thứ tự cấu hình.

[Spring Boot 3.3 — ConditionalOnMissingBean](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnMissingBean.html).

## 5. Thực hành có kiểm soát: thay một yếu tố và đọc lại báo cáo

Ví dụ sau tạo một cấu hình tự động nhỏ để quan sát ba hiện tượng:

- Thiếu thuộc tính nên không khớp.
- Thuộc tính phù hợp và chưa có bean nên cấu hình mặc định tham gia.
- Đã có bean riêng nên phương thức tạo bean mặc định nhường lại.

Đây là dự án thực hành độc lập dùng Java 21, Gradle 8.5 và Spring Boot 3.3.0. Phiên bản được cố định để tái lập ví dụ, không phải khuyến nghị nâng hoặc hạ phiên bản của dự án khác. Các ví dụ Java không thể chạy bằng `javac ConditionsLab.java` đơn lẻ vì cần dependency Spring.

### 5.1. Hai tệp Gradle

Tạo `settings.gradle`:

~~~groovy
rootProject.name = 'conditions-lab'
~~~

Tạo `build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.0'
    id 'io.spring.dependency-management' version '1.1.5'
}

group = 'demo'
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

Dùng Gradle 8.5 để tạo wrapper nếu chưa có:

~~~shell
gradle wrapper --gradle-version 8.5
~~~

Lần đầu chuẩn bị dependency cần kết nối đến kho plugin và Maven Central.

### 5.2. Cấu hình ứng dụng

Tạo `src/main/resources/application.properties`:

~~~properties
server.address=127.0.0.1
management.endpoint.conditions.enabled=true
management.endpoints.web.exposure.include=health,conditions
demo.report.custom=false
~~~

Cố ý chưa đặt `demo.report.enabled`. Không thêm dependency Security trong dự án thực hành này.

### 5.3. Toàn bộ chương trình Java

Tạo `src/main/java/demo/ConditionsLab.java`:

~~~java
package demo;

import java.time.Clock;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.SpringBootConfiguration;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.EnableAutoConfiguration;
import org.springframework.boot.autoconfigure.ImportAutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnClass;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Import;

@SpringBootConfiguration(proxyBeanMethods = false)
@EnableAutoConfiguration
@Import(ConditionsLab.UserConfiguration.class)
@ImportAutoConfiguration(ConditionsLab.ReportAutoConfiguration.class)
public class ConditionsLab {

    public static void main(String[] args) {
        var context = SpringApplication.run(ConditionsLab.class, args);
        var client = context.getBeanProvider(ReportClient.class).getIfAvailable();
        System.out.println("REPORT_CLIENT=" + (client == null ? "none" : client.owner()));
    }

    public record ReportClient(String owner) {
    }

    @AutoConfiguration
    @ConditionalOnClass(Clock.class)
    @ConditionalOnProperty(
        prefix = "demo.report", name = "enabled", havingValue = "true"
    )
    public static class ReportAutoConfiguration {

        @Bean
        @ConditionalOnMissingBean(ReportClient.class)
        ReportClient defaultReportClient() {
            return new ReportClient("auto");
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class UserConfiguration {

        @Bean
        @ConditionalOnProperty(
            prefix = "demo.report", name = "custom", havingValue = "true"
        )
        ReportClient customReportClient() {
            return new ReportClient("custom");
        }
    }
}
~~~

`ReportClient` chỉ giữ nhãn nguồn tạo bean; ví dụ không thực hiện kết nối mạng hay gửi báo cáo ra bên ngoài.

Cách tổ chức phục vụ thí nghiệm:

- `@SpringBootConfiguration` và `@EnableAutoConfiguration` khởi động cấu hình Spring Boot; ví dụ chủ động không dùng quét component.
- `@Import` đưa cấu hình bean riêng của người dùng vào ứng dụng.
- `@ImportAutoConfiguration` đưa đúng cấu hình tự động cần thí nghiệm vào quy trình xử lý cấu hình tự động.
- `@ConditionalOnClass(Clock.class)` tạo một điều kiện về lớp luôn khớp trong môi trường Java 21 của bài.
- `@ConditionalOnProperty` tại lớp yêu cầu `demo.report.enabled=true`.
- `@ConditionalOnMissingBean` tại phương thức chỉ cho tạo bean mặc định khi chưa có `ReportClient`.
- Bean riêng có công tắc độc lập `demo.report.custom`.

Việc nhập cấu hình trực tiếp ở đây giúp giữ ví dụ trong một tệp. Đây không phải hướng dẫn đóng gói starter. Khi viết thư viện dùng lại, cơ chế khai báo ứng viên cấu hình tự động và thứ tự xử lý cần tuân theo hợp đồng dành cho auto-configuration.

[Spring Boot 3.3 — ImportAutoConfiguration](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/ImportAutoConfiguration.html), [hướng dẫn xây dựng cấu hình tự động](https://docs.spring.io/spring-boot/3.3/reference/features/developing-auto-configuration.html).

### 5.4. Trường hợp A — chưa có thuộc tính bật tính năng

Chạy tại thư mục dự án, với JDK 21:

~~~shell
./gradlew bootRun
~~~

Trên PowerShell dùng `.\gradlew.bat bootRun`.

Sau các dòng log khởi động, dòng do chương trình in ra là:

~~~text
REPORT_CLIENT=none
~~~

Mở terminal khác, lấy báo cáo:

~~~powershell
$report = Invoke-RestMethod 'http://127.0.0.1:8080/actuator/conditions'
$report.contexts.PSObject.Properties.Name
~~~

Nếu danh sách ID thực tế có `application`, chọn context đó:

~~~powershell
$ctx = $report.contexts.application
$ctx.negativeMatches.PSObject.Properties |
    Where-Object { $_.Name -like '*ReportAutoConfiguration*' } |
    ForEach-Object {
        $_.Name
        $_.Value.notMatched | Format-Table condition, message -Wrap
        $_.Value.matched | Format-Table condition, message -Wrap
    }
~~~

Nếu ID khác, chọn ID vừa đọc được, chẳng hạn `$report.contexts.'ten-context-thuc-te'`; không coi tên `application` là bất biến.

Ở mục của lớp `ReportAutoConfiguration`, tìm `OnPropertyCondition` trong `notMatched` và đọc thông báo thiếu thuộc tính `enabled`. Đồng thời có thể thấy `OnClassCondition` đã khớp trong `matched`.

Giải thích: có lớp `Clock` chưa đủ; cổng thuộc tính ở cấp lớp vẫn chặn cấu hình. Vì `matchIfMissing` mặc định là `false`, không khai báo thuộc tính không được hiểu là đồng ý bật.

[Spring Boot 3.3 — ConditionalOnProperty và matchIfMissing](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnProperty.html).

### 5.5. Trường hợp B — bật tính năng, chưa có bean riêng

Dừng lần chạy A bằng Ctrl+C, rồi chạy:

~~~shell
./gradlew bootRun --args="--demo.report.enabled=true"
~~~

Trên PowerShell thay `./gradlew` bằng `.\gradlew.bat`.

Dòng chương trình in ra:

~~~text
REPORT_CLIENT=auto
~~~

Gọi lại endpoint để lấy báo cáo mới; biến `$report` cũ không tự cập nhật:

~~~powershell
$report = Invoke-RestMethod 'http://127.0.0.1:8080/actuator/conditions'
$ctx = $report.contexts.application
$ctx.positiveMatches.PSObject.Properties |
    Where-Object { $_.Name -like '*ReportAutoConfiguration*' } |
    ForEach-Object {
        $_.Name
        $_.Value | Format-Table condition, message -Wrap
    }
~~~

Đọc riêng hai nguồn:

1. Nguồn cấp lớp: điều kiện về lớp và thuộc tính đã khớp.
2. Nguồn `#defaultReportClient`: `OnBeanCondition` khớp vì chưa thấy `ReportClient` phù hợp.

Ghép với `REPORT_CLIENT=auto`, có bằng chứng rằng ví dụ đang dùng bean mặc định. Thứ tự mục JSON và toàn bộ câu chữ của thông báo không phải tiêu chí kiểm tra ổn định; hãy bám vào nguồn, điều kiện và nguyên nhân.

### 5.6. Trường hợp C — bật tính năng và cung cấp bean riêng

Dừng lần chạy B, rồi chạy:

~~~shell
./gradlew bootRun --args="--demo.report.enabled=true --demo.report.custom=true"
~~~

Dòng chương trình in ra:

~~~text
REPORT_CLIENT=custom
~~~

Lấy báo cáo mới và lọc phương thức mặc định:

~~~powershell
$report = Invoke-RestMethod 'http://127.0.0.1:8080/actuator/conditions'
$ctx = $report.contexts.application
$ctx.negativeMatches.PSObject.Properties |
    Where-Object { $_.Name -like '*ReportAutoConfiguration#defaultReportClient' } |
    ForEach-Object {
        $_.Name
        $_.Value.notMatched | Format-Table condition, message -Wrap
    }
~~~

Nguồn cấp lớp vẫn nằm trong positive, nhưng nguồn `#defaultReportClient` nằm trong negative. `OnBeanCondition` cho biết đã tìm thấy bean riêng `customReportClient`.

Lập luận đầy đủ:

- Công tắc tính năng đã thỏa điều kiện của lớp.
- Người dùng đã cung cấp bean `ReportClient`.
- Điều kiện “chưa có ReportClient” tại phương thức mặc định không còn đúng.
- Bean mặc định không được đăng ký từ phương thức này; bean riêng được sử dụng.
- Đây là cơ chế nhường lại, không phải lỗi thiếu dependency và cũng không phải hai bean trùng tên ghi đè nhau.

Không sửa tình huống này bằng `spring.main.allow-bean-definition-overriding=true`. Hai khái niệm “không đăng ký vì điều kiện” và “cho phép ghi đè định nghĩa bean” giải quyết những việc khác nhau.

### 5.7. Trường hợp D — đặt false một cách tường minh

Dừng lần chạy C, rồi chạy:

~~~shell
./gradlew bootRun --args="--demo.report.enabled=false"
~~~

`demo.report.custom` trở lại giá trị `false` từ tệp cấu hình. Kết quả:

~~~text
REPORT_CLIENT=none
~~~

Lần này `OnPropertyCondition` không khớp vì thuộc tính tồn tại nhưng có giá trị khác `true`. Nguyên nhân khác với A, dù cả hai cùng không tạo bean mặc định.

| Lần chạy | enabled | custom | Nhãn bean | Bằng chứng chính |
| --- | --- | --- | --- | --- |
| A | Không khai báo | false | none | Điều kiện cấp lớp không khớp do thiếu thuộc tính |
| B | true | false | auto | Điều kiện lớp và điều kiện thiếu bean đều khớp |
| C | true | true | custom | Lớp khớp; phương thức mặc định không khớp vì có bean riêng |
| D | false | false | none | Điều kiện cấp lớp không khớp do giá trị không phù hợp |

Các dòng `REPORT_CLIENT=...` là phần stdout do mã ví dụ tạo ra, không phải toàn bộ log của Spring Boot. Mỗi lần chạy phải dừng tiến trình trước đó và lấy lại báo cáo để tránh đọc trạng thái cũ.

## 6. Chuyển thông báo thành bước kiểm tra tiếp theo

Một kết luận chẩn đoán nên có dạng:

> Context → nguồn cấu hình/phương thức → điều kiện → thông báo quan sát được → giả thuyết → bằng chứng xác nhận.

| Nhóm điều kiện/thông báo | Câu hỏi tiếp theo | Việc không nên suy diễn |
| --- | --- | --- |
| `OnClassCondition` thiếu lớp | Lớp đó có trong classpath lúc chạy không? Phiên bản dependency có đúng không? | Chỉ có dependency lúc biên dịch là đủ |
| `OnPropertyCondition` thiếu thuộc tính | Tên khóa, profile và nguồn cấu hình hiệu lực có đúng không? | Thêm một khóa vào bất kỳ tệp YAML nào cũng sẽ sửa được |
| `OnPropertyCondition` giá trị không phù hợp | Có biến môi trường, tham số dòng lệnh hoặc cấu hình khác ghi đè không? | Giá trị nhìn thấy trong Git luôn là giá trị đang chạy |
| `OnBeanCondition` với điều kiện thiếu bean | Bean nào đã tồn tại, theo kiểu/tên nào và trong phạm vi context nào? | Có bean riêng là lỗi |
| Điều kiện mô hình web không khớp | Ứng dụng cần Servlet, Reactive hay không có web? | Mọi cấu hình web đều cần khớp |
| Điều kiện lớp khớp nhưng phương thức không khớp | Điều kiện riêng của phương thức là gì? | Positive ở lớp bảo đảm mọi bean trong lớp |

Đây là các hướng điều tra, chưa phải kết luận về một hệ thống cụ thể. Từ báo cáo hãy lấy đúng tên lớp, thuộc tính hoặc bean rồi kiểm tra nguồn tương ứng. `env` giúp truy nguồn thuộc tính, `configprops` giúp xem cấu hình đã bind, `beans` giúp đối chiếu bean; chỉ truy cập những endpoint đã được phép công bố và đọc.

Khi cần chứng minh có bean, kiểm tra đúng kiểu và đúng context. Khi cần chứng minh chức năng hoạt động, thực hiện thao tác đại diện của chức năng đó. Không thay phép kiểm chứng hành vi bằng việc đếm dòng positive.

## 7. Các giới hạn cần nhớ khi báo cáo chưa giải thích đủ

### Nguồn hoàn toàn không xuất hiện

Không tìm thấy tên cấu hình không đồng nghĩa với điều kiện đã khớp hay đã không khớp. Kiểm tra lần lượt:

1. Đang xem đúng ứng dụng, phiên bản, profile và context chưa?
2. Dependency và lớp cấu hình có thực sự được đưa vào ứng dụng không?
3. Cấu hình có được đăng ký bằng cơ chế phù hợp không?
4. Có loại trừ qua `@SpringBootApplication(exclude=...)` hoặc `spring.autoconfigure.exclude` không?
5. Điều kiện ở lớp bao ngoài có khiến phần cấu hình bên trong không được xử lý không?

Không tự giả định endpoint có trường JSON tên `exclusions`. Đối với hợp đồng phản hồi Spring Boot 3.3 được dùng trong bài, phải kiểm tra loại trừ từ cấu hình và báo cáo log phù hợp. Các cấu hình bị loại trừ không nên bị diễn giải như một dòng negative thông thường.

[Spring Boot 3.3 — thay thế và loại trừ cấu hình tự động](https://docs.spring.io/spring-boot/3.3/reference/using/auto-configuration.html).

### Báo cáo không phải lịch sử đầy đủ của mọi điều kiện

Điều kiện có thứ tự và có thể dừng khi đã đủ cơ sở loại cấu hình. Danh sách đang đọc là những kết quả được ghi nhận, không bảo đảm mọi điều kiện về sau đều đã được đánh giá. Một mục vắng mặt hoặc mảng `matched` rỗng không cho phép tự suy ra kết quả của những điều kiện không được ghi nhận.

`unconditionalClasses` cũng không có nghĩa “mọi phương thức tạo bean trong lớp đều vô điều kiện”. Luôn kiểm tra điều kiện ở đúng mức lớp/phương thức đang quan tâm.

### Thay đổi tệp không làm ứng dụng tự cấu hình lại

Báo cáo phản ánh kết quả đánh giá của context hiện tại; việc gọi GET không yêu cầu Spring Boot dựng lại toàn bộ bean theo tệp vừa sửa. Với dự án thực hành thông thường, sửa thuộc tính rồi khởi động lại ứng dụng và lấy báo cáo mới.

### Ứng dụng chưa khởi động được

Nếu khởi động thất bại, HTTP endpoint có thể chưa tồn tại. Dùng log lỗi và bật báo cáo điều kiện khi khởi động:

~~~shell
./gradlew bootRun --args="--debug"
~~~

Hoặc với executable JAR thực tế:

~~~shell
java -jar application.jar --debug
~~~

`application.jar` ở đây là tên minh họa cho JAR của ứng dụng. `--debug` hỗ trợ xem báo cáo trong log; nó không tự công bố `/actuator/conditions`. Khi lỗi nằm trong quá trình tạo bean hoặc kết nối tài nguyên, đọc nguyên nhân exception liên quan; positive không loại trừ những lỗi đó.

[Spring Boot 3.3 — xem báo cáo bằng debug khi khởi động](https://docs.spring.io/spring-boot/3.3/reference/using/auto-configuration.html#using.auto-configuration.replacing).

## 8. Tự kiểm tra cách lập luận

**Tình huống 1:** `OnClassCondition` khớp nhưng `OnPropertyCondition` không khớp trên cùng lớp. Có nên thêm lại thư viện ngay không?

Không. Bằng chứng hiện tại hướng đến thuộc tính. Cần đọc tên khóa, yêu cầu của điều kiện và giá trị hiệu lực trước.

**Tình huống 2:** Lớp có trong positive, phương thức mặc định có trong negative vì đã có bean riêng. Có mâu thuẫn không?

Không. Đây là hai nguồn ở hai mức khác nhau. Kết quả cho thấy cấu hình lớp được chấp nhận nhưng phương thức mặc định phải nhường lại.

**Tình huống 3:** `OnBeanCondition` positive chứa ý “không tìm thấy bean”. Vì sao lại positive?

Vì điều kiện đang kiểm tra việc thiếu bean. Cần xác định annotation cụ thể, không đọc kết quả theo cảm giác về câu chữ.

**Tình huống 4:** Bật công tắc trong YAML, gọi endpoint lần nữa nhưng kết quả chưa đổi. Điều đó đã chứng minh Spring Boot bỏ qua YAML chưa?

Chưa. Cần kiểm tra tiến trình đã nạp cấu hình mới chưa, profile và nguồn ghi đè, rồi khởi động lại theo cách quản lý cấu hình của ứng dụng.

**Thực hành thêm:** Chạy lại B và C, ghi cho mỗi lần một câu giải thích có đủ context, nguồn, điều kiện, lý do và nhãn `REPORT_CLIENT`. Sau đó so sánh A với D: cùng kết quả thiếu bean nhưng khác nguyên nhân. Nếu giải thích được sự khác biệt này từ báo cáo, bạn đã dùng `conditions` để chẩn đoán thay vì chỉ tìm từ khóa.
