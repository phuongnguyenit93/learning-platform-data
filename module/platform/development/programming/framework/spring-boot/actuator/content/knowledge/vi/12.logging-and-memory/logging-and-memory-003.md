# Phân biệt thay đổi mức log tạm thời với cấu hình được lưu lâu dài

## 1. Hai nơi khác nhau có thể cùng nói về mức log

Khi cần điều tra một lỗi đang xảy ra, ta có thể tăng mức chi tiết của log ngay trên tiến trình đang chạy. Nhưng khi cần mọi lần triển khai sau đều dùng một mức log nhất định, ta phải thay đổi nguồn cấu hình được dùng để khởi động ứng dụng.

Hai thao tác có thể làm logger cùng hiện `DEBUG` vào một thời điểm, nhưng có vòng đời khác nhau:

~~~text
Nguồn cấu hình được lưu
    └── được đọc khi khởi động ──> trạng thái của hệ thống ghi log

Actuator loggers
    └── thay đổi lúc chạy ───────> trạng thái của hệ thống ghi log
~~~

Endpoint `loggers` của Spring Boot điều khiển mức log trong hệ thống ghi log hiện tại. Nó không có thao tác lưu ngược mức vừa đặt vào `application.properties`, YAML, biến môi trường hay tệp cấu hình triển khai.

Từ **tạm thời** ở đây nghĩa là thay đổi không tự trở thành cấu hình cho những lần khởi động sau. Nó **không** có nghĩa là mức log sẽ tự hết hạn sau vài phút.

Bài này dùng Spring Boot **3.3.0**, Java **21** và Logback do starter mặc định cung cấp để kiểm chứng hành vi. Nội dung tập trung vào vòng đời của mức log, thao tác khôi phục và cách làm thay đổi có thể tái lập sau khởi động lại.

| Tiêu chí | Đổi qua Actuator lúc chạy | Đổi nguồn cấu hình được lưu |
| --- | --- | --- |
| Tác động trực tiếp | Hệ thống ghi log của ứng dụng nhận thao tác. | Nguồn dữ liệu dùng cho lần nạp cấu hình. |
| Có cần khởi động lại để thao tác có tác dụng? | Thường không, mức mới được áp dụng lúc chạy. | Với cấu hình Boot thông thường, cần khởi động lại để nạp giá trị mới. |
| Tự sửa tệp cấu hình không? | Không. | Có nếu chính ta sửa và lưu đúng tệp/nguồn quản lý. |
| Sau khi thay tiến trình/JVM | Mức đặt lúc chạy không tự chuyển sang tiến trình mới. | Được nạp lại nếu nguồn đó vẫn được cấp và có hiệu lực. |
| Tự có thời hạn? | Không có thời hạn hoàn tác mặc định từ yêu cầu đặt mức log. | Phụ thuộc vòng đời và quy trình quản lý nguồn cấu hình. |
| Dùng khi nào? | Điều tra có phạm vi, cần quan sát thêm ngay. | Muốn quy tắc ghi log được áp dụng nhất quán trong các lần chạy sau. |

Khả năng đọc và đổi mức log lúc chạy được mô tả trong [Actuator Loggers của Boot 3.3](https://docs.spring.io/spring-boot/3.3/reference/actuator/loggers.html).

## 2. Phân biệt mức đặt trực tiếp với mức có hiệu lực

Một logger có thể nhận mức trực tiếp hoặc kế thừa mức của logger cha.

Ví dụ cây tên:

~~~text
ROOT
└── lab
    └── lab.orders                 INFO
        └── lab.orders.CheckoutService   WARN
~~~

Trong phản hồi của một logger:

- `configuredLevel` là mức đặt trực tiếp trên logger đó, nếu có.
- `effectiveLevel` là mức đang có hiệu lực sau khi xét kế thừa.

Với logger con trên, cả hai trường đều là `WARN`. Nếu bỏ mức trực tiếp của logger con, nó kế thừa `INFO` từ `lab.orders`. Khi đó `configuredLevel` vắng hoặc có giá trị `null`, còn `effectiveLevel` là `INFO`.

Tên `configuredLevel` dễ gây hiểu nhầm: nó không chứng minh mức ấy đang được lưu trong tệp. Sau khi đặt `DEBUG` qua Actuator, trường này cũng là `DEBUG`, dù tệp vẫn khai báo `WARN`.

Một lần đọc `loggers` cho biết trạng thái hiện tại; nó không cho biết đầy đủ ai đặt mức đó, lúc nào, đến từ tệp nào hoặc nó có tồn tại sau lần triển khai tiếp theo không. Muốn trả lời các câu hỏi về nguồn gốc phải đối chiếu cấu hình và lịch sử thao tác riêng.

Quy tắc kế thừa theo tên logger được giải thích trong [kiến trúc Logback](https://logback.qos.ch/manual/architecture.html#effectiveLevel). Logger có mức riêng sẽ dùng mức riêng; đổi cha sang `DEBUG` không tự hạ một logger con đang đặt rõ `WARN`.

## 3. Thực hành với cấu hình nền WARN và một logger có thể kích hoạt

Tạo dự án riêng:

~~~text
log-level-lab/
├── settings.gradle
├── build.gradle
└── src/main/
    ├── java/lab/
    │   ├── LogLevelLabApplication.java
    │   ├── DemoController.java
    │   └── orders/CheckoutService.java
    └── resources/application.properties
~~~

### 3.1. Cấu hình build và mức log ban đầu

Nội dung `settings.gradle`:

~~~groovy
rootProject.name = 'log-level-lab'
~~~

Nội dung `build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.0'
}

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
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
}
~~~

Nội dung `src/main/resources/application.properties`:

~~~properties
spring.application.name=log-level-lab
server.address=127.0.0.1
server.port=8080
management.endpoints.web.exposure.include=health,loggers
management.endpoint.loggers.enabled=true
logging.level.root=INFO
logging.level.lab.orders=INFO
logging.level.lab.orders.CheckoutService=WARN
~~~

Ở đây ta cố ý đặt logger cha `INFO` và logger lớp `WARN`. Hai mức khác nhau sẽ giúp phân biệt thao tác **xóa mức riêng** với thao tác **khôi phục mức nền**.

Chỉ công bố `health` và `loggers` qua HTTP. Trong Boot 3.3, endpoint được bật không đồng nghĩa đã được công bố qua HTTP; mặc định chỉ `health` được công bố. Thao tác ghi còn chịu quy tắc bảo mật của ứng dụng. Xem [công bố và bảo vệ endpoint](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html).

Máy chủ của bài chỉ lắng nghe trên loopback và không thêm Spring Security. Không dùng cấu hình mở quyền của môi trường thực hành làm quy tắc quản trị cho hệ thống triển khai.

### 3.2. Mã nguồn

Tệp `src/main/java/lab/LogLevelLabApplication.java`:

~~~java
package lab;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class LogLevelLabApplication {
    public static void main(String[] args) {
        SpringApplication.run(LogLevelLabApplication.class, args);
    }
}
~~~

Tệp `src/main/java/lab/orders/CheckoutService.java`:

~~~java
package lab.orders;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;

@Service
public class CheckoutService {
    private static final Logger log =
            LoggerFactory.getLogger(CheckoutService.class);

    public void inspect() {
        log.debug("checkout diagnostic: phase=validate");
        log.info("checkout demo invoked");
        log.warn("checkout demo warning");
    }
}
~~~

Tệp `src/main/java/lab/DemoController.java`:

~~~java
package lab;

import java.util.Map;
import lab.orders.CheckoutService;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class DemoController {
    private final CheckoutService checkoutService;

    public DemoController(CheckoutService checkoutService) {
        this.checkoutService = checkoutService;
    }

    @GetMapping("/demo/checkout")
    public Map<String, String> inspect() {
        checkoutService.inspect();
        return Map.of("status", "inspected");
    }
}
~~~

Đường dẫn `/demo/checkout` chỉ kích hoạt ba câu log cố định để quan sát. Nó không tạo đơn hàng hoặc xử lý dữ liệu thanh toán.

Tên logger là tên đầy đủ của lớp `lab.orders.CheckoutService`. Vì thế khóa cấu hình và tên trong URL Actuator phải khớp tên này, kể cả chữ hoa/thường.

### 3.3. Chạy dự án

Với Gradle 8.5 đã cài, tạo wrapper một lần tại thư mục dự án:

~~~powershell
gradle wrapper --gradle-version 8.5
~~~

Chạy trên Windows:

~~~powershell
.\gradlew.bat bootRun
~~~

Trên Linux/macOS dùng `./gradlew bootRun`. Lần đầu cần tải Gradle và thư viện. Các tệp Java cần classpath Spring; đây không phải chương trình chỉ có một tệp để chạy bằng `javac` trần.

Mở PowerShell khác để gọi:

~~~powershell
Invoke-RestMethod -Uri 'http://127.0.0.1:8080/demo/checkout'
~~~

Phản hồi có `status=inspected`. Với cấu hình nền của bài, trong ba câu log của `CheckoutService` chỉ câu sau được ghi:

~~~text
checkout demo warning
~~~

Đây là phần nội dung thông điệp; dòng console thực tế còn có thời gian, mức log, tên logger và thông tin định dạng khác. Không nhầm log khởi động của Spring với ba câu log của phép thử.

## 4. Đổi mức lúc chạy, đọc lại và khôi phục đúng trạng thái

Các đoạn PowerShell dưới đây thao tác trên **một ứng dụng thực hành cục bộ**, với giả định không có người khác cùng đổi mức log. Chạy tuần tự trong cùng phiên PowerShell.

### 4.1. Chụp trạng thái trước khi thay đổi

~~~powershell
$base = 'http://127.0.0.1:8080'
$loggerName = 'lab.orders.CheckoutService'
$loggerUri = "$base/actuator/loggers/$loggerName"

$before = Invoke-RestMethod -Uri $loggerUri
$before | ConvertTo-Json
~~~

Kết quả ban đầu:

~~~json
{
  "configuredLevel": "WARN",
  "effectiveLevel": "WARN"
}
~~~

Lưu `configuredLevel` trước khi đổi, không chỉ lưu `effectiveLevel`. Nếu một logger ban đầu kế thừa `INFO`, khôi phục bằng cách đặt cứng `INFO` sẽ tạo mức riêng mới và làm thay đổi quan hệ kế thừa.

Phạm vi của trạng thái chụp còn gắn với đúng instance/tiến trình đang được hỏi. Nếu đi qua bộ cân bằng tải, phải có cách xác định rằng các yêu cầu đọc và ghi đến cùng instance.

### 4.2. Đặt DEBUG và kiểm tra tác dụng

~~~powershell
$debugRequest = @{
    Method = 'Post'
    Uri = $loggerUri
    ContentType = 'application/json'
    Body = '{"configuredLevel":"DEBUG"}'
}
Invoke-RestMethod @debugRequest
Invoke-RestMethod -Uri $loggerUri | ConvertTo-Json
Invoke-RestMethod -Uri "$base/demo/checkout"
~~~

Thao tác ghi dùng `POST`, nội dung JSON chứa `configuredLevel`. Khi thành công qua HTTP, Boot thông thường trả **204 No Content**; không cần có một tài liệu JSON ở phản hồi POST. Yêu cầu GET sau đó mới xác minh trạng thái:

~~~json
{
  "configuredLevel": "DEBUG",
  "effectiveLevel": "DEBUG"
}
~~~

Lần kích hoạt `/demo/checkout` này cho thấy đủ ba thông điệp:

~~~text
checkout diagnostic: phase=validate
checkout demo invoked
checkout demo warning
~~~

Không phải chỉ câu DEBUG mới được ghi. Trong ví dụ Logback này, mức `DEBUG` cho phép các câu ở DEBUG và các mức cao hơn; TRACE vẫn chưa được bật.

Mức `INFO` trên ROOT không tạo một “trần toàn cục” chặn mọi logger con đặt rõ DEBUG. Tuy nhiên, bộ lọc của appender hoặc hệ thống thu thập log vẫn có thể loại bỏ sự kiện ở bước khác.

API đặt và đọc mức log được mô tả tại [Loggers REST API của Boot 3.3](https://docs.spring.io/spring-boot/3.3/api/rest/actuator/loggers.html).

### 4.3. Xóa mức riêng: vì sao lại thành INFO?

Theo API Boot 3.3, gửi đối tượng JSON rỗng `{}` để xóa mức đặt riêng:

~~~powershell
$clearRequest = @{
    Method = 'Post'
    Uri = $loggerUri
    ContentType = 'application/json'
    Body = '{}'
}
Invoke-RestMethod @clearRequest
Invoke-RestMethod -Uri $loggerUri | ConvertTo-Json
Invoke-RestMethod -Uri "$base/demo/checkout"
~~~

Logger con không còn mức trực tiếp và kế thừa từ cha `lab.orders=INFO`. Phản hồi có `effectiveLevel=INFO`; `configuredLevel` không có giá trị, có thể bị lược khỏi JSON. Một biểu diễn thường gặp:

~~~json
{
  "effectiveLevel": "INFO"
}
~~~

Lần kích hoạt tiếp theo chỉ còn hai thông điệp:

~~~text
checkout demo invoked
checkout demo warning
~~~

**Xóa mức riêng không có nghĩa là đọc lại `logging.level.lab.orders.CheckoutService=WARN` từ tệp.** Thao tác này cũng không phải đặt mức `OFF`, không xóa logger và không xóa các dòng log đã ghi.

Nếu mục tiêu là về lại `WARN` của ví dụ, phải khôi phục mức đó hoặc nạp lại cấu hình theo quy trình thích hợp.

### 4.4. Khôi phục giá trị đã chụp

~~~powershell
$restoreBody = if ($null -eq $before.configuredLevel) {
    '{}'
} else {
    @{ configuredLevel = $before.configuredLevel } | ConvertTo-Json -Compress
}

$restoreRequest = @{
    Method = 'Post'
    Uri = $loggerUri
    ContentType = 'application/json'
    Body = $restoreBody
}
Invoke-RestMethod @restoreRequest
$afterRestore = Invoke-RestMethod -Uri $loggerUri
$afterRestore | ConvertTo-Json
~~~

Với `$before` của ví dụ, yêu cầu khôi phục đặt `WARN`; đọc lại được WARN/WARN và phép thử chỉ ghi câu cảnh báo.

Nếu trạng thái trước đó không có mức riêng, đoạn mã gửi `{}` để trả lại cơ chế kế thừa. Nó không đặt cứng mức hiệu lực đã chụp. Nếu logger cha cũng đã thay đổi trong thời gian điều tra thì mức hiệu lực có thể khác, dù mức riêng của logger con được khôi phục đúng.

Không dùng chuỗi `"null"` để thay cho việc xóa mức riêng: đó là một chuỗi ký tự, không phải giá trị null hay đối tượng JSON rỗng.

### 4.5. Theo dõi cả chuỗi trạng thái

Các trạng thái này đã được kiểm chứng với `LoggersEndpoint` của Boot 3.3.0 và Logback:

| Thao tác | Mức riêng của logger con | Mức có hiệu lực | Ba câu log của ví dụ xuất hiện |
| --- | --- | --- | --- |
| Khởi động từ tệp gốc | WARN | WARN | WARN |
| Đổi riêng logger cha thành DEBUG | WARN | WARN | WARN |
| Giữ cha INFO, đặt con DEBUG | DEBUG | DEBUG | DEBUG, INFO, WARN |
| Xóa mức riêng của con | Không có | INFO | INFO, WARN |
| Khôi phục mức riêng đã chụp | WARN | WARN | WARN |
| Đặt DEBUG rồi khởi động JVM mới, vẫn dùng tệp gốc | WARN | WARN | WARN |

Bảng giả định không có bộ lọc/appender tùy biến làm thay đổi đầu ra và không có nguồn cấu hình khác ghi đè.

### 4.6. Hoàn tác trong một phiên chẩn đoán ngắn

Ở dự án cục bộ chỉ có một người thao tác, có thể đặt bước khôi phục vào `finally`. Đoạn này dùng `$base`, `$loggerUri` và `$debugRequest` đã khai báo ở trên:

~~~powershell
$original = Invoke-RestMethod -Uri $loggerUri
$originalBody = if ($null -eq $original.configuredLevel) {
    '{}'
} else {
    @{ configuredLevel = $original.configuredLevel } | ConvertTo-Json -Compress
}

try {
    Invoke-RestMethod @debugRequest
    Invoke-RestMethod -Uri "$base/demo/checkout"
} finally {
    $rollbackRequest = @{
        Method = 'Post'
        Uri = $loggerUri
        ContentType = 'application/json'
        Body = $originalBody
    }
    Invoke-RestMethod @rollbackRequest
    Invoke-RestMethod -Uri $loggerUri | ConvertTo-Json
}
~~~

Đây là hoàn tác sau khi khối công việc kết thúc, không phải tính năng tự hết hạn của Actuator. Nếu đóng cưỡng bức PowerShell, mất máy hoặc tiến trình điều khiển bị dừng, không nên coi `finally` là cam kết hoàn tác chắc chắn.

Trong hệ thống dùng chung, cần phối hợp quyền thay đổi và kiểm tra có thao tác mới hơn trước khi khôi phục; không ghi đè mức mà người khác vừa chủ ý đặt.

## 5. Chứng minh thay đổi lúc chạy không trở thành cấu hình khởi động

Thực hiện phép thử trên dự án cục bộ:

1. Giữ dòng cấu hình logger lớp là `WARN`.
2. Dùng Actuator đặt logger lớp thành `DEBUG`.
3. Xác minh GET trả DEBUG/DEBUG.
4. Dừng ứng dụng rồi chạy lại với cùng nguồn cấu hình.
5. Đọc lại logger: kết quả trở về WARN/WARN.

Điều bị mất là thay đổi mức trong tiến trình cũ. Các dòng log DEBUG đã được ghi trước đó không vì thế bị xóa khỏi nơi lưu log.

Tương tự, thay đổi mức qua `loggers` không tự đổi giá trị `logging.level...` trong Spring `Environment`. Do đó có thể đồng thời quan sát:

~~~text
Nguồn cấu hình / Environment: WARN
Trạng thái logger lúc chạy:   DEBUG
~~~

Hai thông tin này trả lời hai câu hỏi khác nhau. Muốn biết logger đang dùng mức nào, đọc `loggers`; muốn điều tra giá trị cấu hình đến từ nguồn nào, đối chiếu nguồn cấu hình và công cụ chẩn đoán phù hợp.

Một tiến trình có thể tồn tại nhiều ngày. Nếu không chủ động hoàn tác và không có sự kiện nạp lại cấu hình khác, mức “tạm thời” có thể kéo dài suốt thời gian đó. Endpoint không tự gắn hạn 5 phút hay 15 phút vào yêu cầu `configuredLevel`.

## 6. Làm thay đổi được lưu và có thể tái lập

### 6.1. Sửa đúng nguồn cấu hình

Nếu chủ đích là dùng DEBUG cho những lần chạy sau của môi trường thực hành, thay dòng tương ứng trong `application.properties`:

~~~properties
logging.level.lab.orders.CheckoutService=DEBUG
~~~

Lưu tệp, dừng và chạy lại. Nếu cấu hình này được đóng gói trong JAR, bản JAR cũ không tự thay đổi khi sửa tệp nguồn; cần tạo bản build mới để triển khai.

Các cách cung cấp cấu hình được Boot hỗ trợ bao gồm tệp properties/YAML, cấu hình theo profile, biến môi trường và tham số khởi động. Nguồn ở ngoài ứng dụng có thể ghi đè cấu hình được đóng gói. Xem [cấu hình từ bên ngoài trong Boot 3.3](https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html).

Có thể giữ cấu hình cho riêng môi trường phát triển trong `application-dev.properties` và kích hoạt đúng profile. Một tệp đã lưu nhưng không được nạp không tạo ra tác dụng.

### 6.2. Tham số khởi động có giá trị đến khi nào?

Ví dụ chạy bằng wrapper trên Windows:

~~~powershell
.\gradlew.bat bootRun --args="--logging.level.lab.orders.CheckoutService=DEBUG"
~~~

Tham số này cấu hình mức log cho lần khởi động đó và có thể ghi đè dòng WARN trong tệp. Nó không sửa tệp.

Nếu muốn các lần khởi động sau tiếp tục có cùng tham số, phải lưu nó trong cấu hình chạy, công cụ quản lý dịch vụ hoặc đặc tả triển khai. Việc gõ một lần trong terminal không tự làm mọi lần triển khai sau kế thừa lệnh đó.

Tương tự, biến môi trường chỉ “lâu dài” theo vòng đời nơi lưu và cấp lại biến. Biến chỉ đặt trong một phiên shell không đồng nghĩa đã được lưu trong cấu hình triển khai.

Riêng tên logger là lớp có chữ hoa/thường như `CheckoutService`, không suy ra một biến `LOGGING_LEVEL_...` thông thường sẽ giữ nguyên tên lớp: cơ chế liên kết biến môi trường chuyển tên về chữ thường. Dùng tệp cấu hình, tham số khởi động hoặc `SPRING_APPLICATION_JSON` theo đúng quy tắc của Boot nếu cần cấu hình lớp cụ thể. Xem [cấu hình mức log và biến môi trường](https://docs.spring.io/spring-boot/3.3/reference/features/logging.html#features.logging.log-levels).

### 6.3. Đã lưu chưa có nghĩa đang có hiệu lực

Với Boot thông thường, chỉ sửa tệp không bảo đảm một tiến trình đang chạy tự đọc lại tệp. Thao tác “lưu” và thao tác “áp dụng vào tiến trình” là hai việc cần kiểm tra riêng.

Nếu hệ thống có công cụ nạp lại cấu hình, Logback scanning hoặc nền tảng điều khiển cấu hình tập trung, hành vi áp dụng do cơ chế đó quyết định. Nó có thể ghi đè một mức vừa đặt qua Actuator. Không mặc định rằng Boot và `loggers` cung cấp sẵn một cơ chế đồng bộ hai chiều.

Các cấu hình native như `logback-spring.xml` cũng là nguồn có thể được quản lý lâu dài. Cần hiểu nơi nào đang đặt mức log, tránh sửa nhiều nguồn mà không biết thứ tự tác động. `loggers` không lưu ngược thay đổi vào những tệp này.

Một lần kiểm tra sau triển khai nên xác nhận:

- Nguồn cấu hình thay đổi đã được lưu ở nơi được quản lý.
- Tiến trình mới thực sự nhận đúng nguồn/profile/tham số.
- `configuredLevel` và `effectiveLevel` sau khởi động phù hợp mục tiêu.
- Một yêu cầu thử tạo ra những log cần thiết.

Không dùng một POST thành công để thay cho cả bốn bằng chứng trên.

## 7. Những lỗi dễ mắc khi vận hành

### “DEBUG đã hiện trong configuredLevel nên chắc chắn đã được lưu”

Không đúng. Trường này biểu thị mức hiện được gán trực tiếp. Đặt qua Actuator cũng làm nó thay đổi, dù các nguồn cấu hình vẫn nguyên vẹn.

### “Xóa mức riêng sẽ khôi phục chính xác cấu hình ban đầu”

Không đúng nếu ban đầu logger có mức riêng. Trong ví dụ, xóa mức riêng cho INFO kế thừa; khôi phục mức đã chụp mới cho WARN. Với nhiều logger, cần lưu trạng thái riêng của từng đối tượng đã đổi.

### “Đổi ROOT hoặc logger cha sẽ làm mọi nơi phát DEBUG”

Logger con có mức riêng có thể giữ mức khác. Bộ lọc ở appender, cấu hình gửi log và bộ thu thập còn có thể loại bỏ sự kiện. Dùng logger có phạm vi nhỏ nhất đáp ứng câu hỏi điều tra.

Cờ `--debug` của Boot cũng không đồng nghĩa đặt toàn bộ mã ứng dụng về DEBUG; nó bật thêm chi tiết cho một số logger do Boot chọn. Muốn kiểm soát lớp cụ thể, đặt đúng tên logger. Xem [chế độ debug trong tài liệu logging](https://docs.spring.io/spring-boot/3.3/reference/features/logging.html#features.logging.console-output).

### “Một lần POST sẽ cập nhật cả cụm”

Actuator không tự phát tán thay đổi cho các instance khác. Sau thay thế container, khởi động lại hoặc mở rộng số instance, các tiến trình mới lấy cấu hình khởi động của chúng.

Nếu nhiều instance đang có mức khác nhau, các lần GET qua bộ cân bằng tải có thể cho kết quả khác nhau. Cần biết chính xác instance đã thay đổi và đọc lại trên cùng đích; cấu hình muốn dùng cho toàn cụm phải được cấp qua cơ chế triển khai thích hợp.

### “Có thể khôi phục một nhóm logger bằng một mức chụp duy nhất”

Nhóm logger có thể chứa nhiều thành viên với các mức riêng khác nhau. Đặt mức cho nhóm có thể tác động nhiều logger; gán lại một mức chung không tái tạo được mọi trạng thái trước đó. Không mở rộng thí nghiệm một logger của bài thành thay đổi nhóm hoặc ROOT mà bỏ qua phạm vi và cách hoàn tác.

### “Không thấy nội dung phản hồi POST nghĩa là lỗi”

Thành công có thể là 204 không có thân phản hồi. Hãy xem trạng thái HTTP và GET xác nhận. Nếu gặp 401/403, kiểm tra xác thực, phân quyền và chính sách CSRF cho thao tác ghi; đừng mặc định phải vô hiệu hóa toàn bộ bảo mật.

### “Mức tạm thời không cần theo dõi vì sắp tự mất”

Không có hạn hoàn tác mặc định. Khi cần tăng DEBUG/TRACE để chẩn đoán, nên xác định logger, instance, mục đích, người chịu trách nhiệm và điều kiện kết thúc. Mức chi tiết cao có thể làm tăng lượng log hoặc làm lộ dữ liệu mà mã ứng dụng đã đưa vào câu log.

Ví dụ của bài chỉ ghi thông điệp cố định để tránh trộn vấn đề cấu hình mức với việc xử lý dữ liệu nhạy cảm.

## 8. Bài tập tự kiểm chứng

**Bài 1 — Xóa khác khôi phục.** Khởi động từ cấu hình gốc, chụp trạng thái, đặt DEBUG rồi gửi `{}`. Sau đó khôi phục mức đã chụp.

Đối chiếu: WARN/WARN → DEBUG/DEBUG → không có mức riêng/INFO → WARN/WARN. Giải thích vì sao bước thứ ba không trở về WARN.

**Bài 2 — Quan hệ cha–con.** Khi logger con vẫn đặt WARN, đổi logger cha `lab.orders` sang DEBUG và kích hoạt phép thử.

Đối chiếu: logger con vẫn WARN/WARN. Sau bài thử, trả logger cha về INFO; không chỉ hoàn tác logger con rồi bỏ quên logger cha.

**Bài 3 — Qua ranh giới tiến trình.** Đặt con DEBUG qua Actuator, xác minh, rồi dừng và chạy lại mà không sửa nguồn cấu hình.

Đối chiếu: JVM mới đọc lại WARN của tệp gốc. Kết quả này không nói rằng những dòng DEBUG đã lưu trong hệ thống log bị xóa.

**Bài 4 — Cấu hình được lưu.** Sửa đúng dòng logger lớp thành DEBUG trong nguồn cấu hình, lưu và chạy lại. Sau đó tạm đặt WARN qua Actuator rồi khởi động lại lần nữa.

Đối chiếu: khi nguồn DEBUG được nạp lại và không bị nguồn khác ghi đè, tiến trình mới trở về DEBUG. Mức WARN lúc chạy không ghi đè lâu dài lên tệp.

**Bài 5 — Trạng thái ban đầu là kế thừa.** Trong dự án thực hành, bỏ riêng dòng cấu hình logger lớp, giữ cha INFO rồi khởi động lại. Chụp trạng thái, đặt DEBUG và khôi phục từ trạng thái đã chụp.

Đối chiếu: mức riêng ban đầu không có, mức hiệu lực INFO; khôi phục bằng `{}` để trả lại kế thừa, không đặt cứng INFO cho lớp.

Sau các phép thử, trả lại cấu hình và mức log mong muốn của môi trường thực hành. Điều cần phân biệt là: **mức hiện tại**, **mức kế thừa**, **nguồn cấu hình được lưu** và **cơ chế nạp lại nguồn đó**.
