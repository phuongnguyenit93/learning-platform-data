# Thay đổi hoặc khôi phục mức log của logger và logger group khi ứng dụng đang chạy

## 1. Tại sao cần thay đổi mức log trong lúc chạy?

Một nhánh xử lý đang gặp lỗi nhưng log INFO chưa đủ để thấy diễn biến. Nếu chỉ đổi tệp cấu hình rồi triển khai lại, bạn có thể làm mất trạng thái hoặc bỏ lỡ thời điểm cần quan sát. Endpoint `loggers` của Spring Boot Actuator cho phép đọc và thay đổi mức log trong tiến trình đang chạy.

Một phiên quan sát nên có đủ vòng đời:

~~~text
Đọc trạng thái hiện tại
    → lưu trạng thái cần khôi phục
    → thay đổi phạm vi nhỏ nhất đủ dùng
    → tạo hoặc chờ hành vi cần quan sát
    → đọc lại mức hiệu lực và log mới
    → khôi phục
    → xác nhận trạng thái sau khôi phục
~~~

Điểm cần học không chỉ là gửi một POST với `DEBUG`. Bạn cần biết POST tác động lên logger nào, logger con sẽ kế thừa ra sao và thao tác khôi phục nào thực sự trả lại cấu hình ban đầu.

Bài dùng Spring Boot 3.3.x với Logback mặc định từ starter. Các request mẫu áp dụng cho ứng dụng thực hành trên loopback. Khi làm việc với một hệ thống khác, dùng đúng URL quản trị, instance và quyền vận hành đã được cấp. [Spring Boot 3.3 — quản lý logger](https://docs.spring.io/spring-boot/3.3/reference/actuator/loggers.html).

## 2. Ba khái niệm quyết định cách thay đổi và khôi phục

### 2.1. Logger và cây tên

Logger là đối tượng có tên dùng để phát sinh log. Tên thường theo tên lớp hoặc package, nhưng cũng có thể do lập trình viên chọn.

Ví dụ:

~~~text
ROOT
└── demo
    ├── demo.alpha
    │   ├── demo.alpha.Worker
    │   └── demo.alpha.Fixed
    └── demo.beta
        └── demo.beta.Worker
~~~

Trong Logback, quan hệ kế thừa được xác định theo tên có dấu chấm. `demo.alpha.Worker` là hậu duệ của `demo.alpha`. Tên logger phân biệt chữ hoa/thường; tên hiển thị rút gọn trên console không nhất thiết là tên đầy đủ cần gửi vào endpoint.

### 2.2. configuredLevel và effectiveLevel

Một phản hồi logger có thể có dạng:

~~~json
{
  "configuredLevel": null,
  "effectiveLevel": "INFO"
}
~~~

- `configuredLevel`: mức được gán trực tiếp cho chính logger đang hỏi.
- `effectiveLevel`: mức có hiệu lực sau khi xét kế thừa.

Giá trị null, hoặc trường configuredLevel không được hiển thị khi cách tuần tự hóa bỏ trường null, nghĩa là logger không có mức gán trực tiếp. Nó vẫn có thể phát sinh log nhờ kế thừa từ logger cha.

Nếu `demo.alpha=INFO` và `demo.alpha.Worker` chưa có mức riêng, Worker có mức hiệu lực INFO. Đặt trực tiếp Worker thành DEBUG sẽ cho phép Worker phát sinh thêm DEBUG. Xóa mức trực tiếp của Worker sẽ khiến nó kế thừa trở lại, không phải “tắt logger”.

Một logger con đã có mức riêng có thể tiếp tục giữ mức đó khi logger cha đổi. Ví dụ `demo.alpha.Fixed=WARN` vẫn là WARN dù `demo.alpha` chuyển thành DEBUG.

Với Logback, mức ROOT không phải một trần chung buộc mọi logger con phải giữ nguyên: logger con có mức DEBUG riêng vẫn có thể phát sinh DEBUG khi ROOT là INFO. Các appender hoặc bộ lọc vẫn có thể ảnh hưởng việc xuất thông điệp.

[Logback — cây logger, kế thừa mức và quy tắc chọn log](https://logback.qos.ch/manual/architecture.html).

### 2.3. Logger group là tập tên logger, không phải một logger cha

Spring Boot cho phép khai báo:

~~~properties
logging.group.diagnostics=demo.alpha,demo.beta
~~~

Group `diagnostics` gom hai tên logger để thao tác cùng lúc. Nó không chèn một nút cha tên diagnostics vào cây kế thừa.

Khi đặt mức của group thành DEBUG, Spring Boot áp dụng mức đó lên các logger thành viên. Logger con chưa có mức riêng có thể hưởng DEBUG qua kế thừa từ thành viên. Logger con đã có mức riêng không vì thế tự bị xóa mức.

Một logger hoặc nhánh có thể nằm trong nhiều group. Thay đổi các group chồng lấn sẽ tác động lên cùng một số logger; không có một “mức ưu tiên group” độc lập với mức thực tế của các logger đó.

Tên group phải được khai báo và xác minh trước. Không POST một tên tùy ý rồi mặc định rằng đã tạo ra group với các thành viên mong muốn. Chọn tên group rõ ràng, tránh trùng tên logger để người vận hành không nhầm đích.

[Spring Boot 3.3 — khai báo logging group](https://docs.spring.io/spring-boot/3.3/reference/features/logging.html).

## 3. Hợp đồng HTTP cần dùng

Với đường dẫn quản trị mặc định:

| Mục đích | Request | Kết quả chính |
| --- | --- | --- |
| Đọc logger, group và các mức được hỗ trợ | `GET /actuator/loggers` | JSON có `levels`, `loggers`, `groups` |
| Đọc một logger | `GET /actuator/loggers/{loggerName}` | Mức gán trực tiếp và mức hiệu lực |
| Đọc một group | `GET /actuator/loggers/{groupName}` | Các thành viên và mức đã đặt cho group, nếu có |
| Đặt mức cho logger hoặc group | `POST /actuator/loggers/{name}` với `{"configuredLevel":"DEBUG"}` | Thao tác ghi; bình thường trả HTTP 204 |
| Xóa mức gán trực tiếp | Cùng POST, body `{}` | Bỏ mức đang gán, không đọc lại cấu hình ban đầu |

Dùng `Content-Type: application/json` cho các POST. Body `{}` là một đối tượng JSON rỗng; nó khác request không có body, chuỗi JSON `"{}"` hoặc body có sai tên trường.

HTTP 204 không có JSON để đọc. Sau khi ghi, dùng GET để xác nhận mức; không diễn giải body trống của response 204 thành request thất bại.

Danh sách `levels` phản ánh các mức hệ thống hỗ trợ. Không tự gửi một chuỗi như `VERBOSE` hoặc `ALL` vì thấy tên đó trong một công cụ khác. Ví dụ dưới đây dùng `DEBUG`, `INFO` và `WARN`.

Group không có một trường effectiveLevel dùng để đại diện chắc chắn cho mọi thành viên. Hãy đọc members rồi kiểm tra logger liên quan. [Spring Boot 3.3 — REST API loggers](https://docs.spring.io/spring-boot/3.3/api/rest/actuator/loggers.html).

## 4. Dự án thực hành có kết quả quan sát được

Dùng Java 21, Gradle 8.5 và Spring Boot 3.3.0 để tái lập ví dụ. Phiên bản được cố định cho bài học, không phải yêu cầu đổi phiên bản một dự án đang vận hành.

### 4.1. Tệp build và cấu hình

`settings.gradle`:

~~~groovy
rootProject.name = 'runtime-loggers-lab'
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
management.endpoint.loggers.enabled=true
management.endpoints.web.exposure.include=health,loggers
logging.level.root=INFO
logging.group.diagnostics=demo.alpha,demo.beta
logging.level.demo.alpha=INFO
logging.level.demo.beta=WARN
logging.level.demo.alpha.Fixed=WARN
~~~

Chỉ công bố `health` và `loggers`. Ứng dụng thực hành không thêm Spring Security và chỉ lắng nghe trên loopback. Cấu hình này không phải mẫu công bố endpoint quản trị cho Internet.

Các mức khởi đầu được chọn có chủ ý:

- `demo.alpha` có mức riêng INFO.
- `demo.beta` có mức riêng WARN.
- `demo.alpha.Fixed` có mức riêng WARN.
- Hai logger Worker không có mức riêng, nên kế thừa.
- Group diagnostics được khai báo thành viên nhưng chưa được đặt một mức chung.

### 4.2. Chương trình Java đầy đủ

Tạo `src/main/java/demo/RuntimeLoggersApplication.java`:

~~~java
package demo;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class RuntimeLoggersApplication {

    public static void main(String[] args) {
        SpringApplication.run(RuntimeLoggersApplication.class, args);
    }

    @RestController
    public static class LogProbeController {

        private static final Logger ALPHA =
            LoggerFactory.getLogger("demo.alpha.Worker");
        private static final Logger BETA =
            LoggerFactory.getLogger("demo.beta.Worker");
        private static final Logger FIXED =
            LoggerFactory.getLogger("demo.alpha.Fixed");

        @GetMapping(value = "/demo/log", produces = "text/plain")
        public String emit() {
            ALPHA.debug("ALPHA_DEBUG");
            ALPHA.info("ALPHA_INFO");
            ALPHA.warn("ALPHA_WARN");
            BETA.debug("BETA_DEBUG");
            BETA.info("BETA_INFO");
            BETA.warn("BETA_WARN");
            FIXED.debug("FIXED_DEBUG");
            FIXED.info("FIXED_INFO");
            FIXED.warn("FIXED_WARN");
            return "emitted\n";
        }
    }
}
~~~

Các tên logger được viết tường minh để dễ đối chiếu. Chúng không phải ba lớp Java khác nhau. Mỗi lần GET `/demo/log`, phương thức gọi đủ các câu lệnh DEBUG/INFO/WARN; hệ thống logging quyết định những sự kiện nào được phát ra.

Phản hồi của API thử nghiệm luôn là:

~~~text
emitted
~~~

Phản hồi này chỉ xác nhận handler đã chạy, không chứng minh mọi thông điệp DEBUG đã được xuất.

### 4.3. Build và chạy

Nếu dự án chưa có wrapper, dùng Gradle 8.5 để tạo:

~~~shell
gradle wrapper --gradle-version 8.5
~~~

Sau đó tại thư mục dự án, trong PowerShell:

~~~powershell
java -version
.\gradlew.bat bootJar
java -jar build/libs/runtime-loggers-lab-1.0.0.jar
~~~

Dùng JDK 21 cho lệnh chạy Java. Lần build đầu cần truy cập kho plugin và Maven Central. Đây là chương trình Spring Boot cần classpath của các dependency; không dùng `javac RuntimeLoggersApplication.java` đơn lẻ.

Giữ ứng dụng chạy trong terminal thứ nhất. Các request ở phần sau được gửi từ terminal thứ hai, tới chính ứng dụng thực hành này.

## 5. Đổi rồi khôi phục một logger

### 5.1. Hai hàm PowerShell để đọc và ghi có kiểm tra status

Trong terminal gửi request, khai báo:

~~~powershell
$loggerBase = 'http://127.0.0.1:8080/actuator/loggers'
$probeUri = 'http://127.0.0.1:8080/demo/log'

function Read-LogTarget {
    param([string]$Name)

    $encodedName = [Uri]::EscapeDataString($Name)
    Invoke-RestMethod -Method Get -Uri "$loggerBase/$encodedName" -ErrorAction Stop
}

function Write-LogTarget {
    param(
        [string]$Name,
        [AllowNull()][string]$Level
    )

    $body = if ([string]::IsNullOrEmpty($Level)) {
        '{}'
    } else {
        @{ configuredLevel = $Level } | ConvertTo-Json -Compress
    }

    $encodedName = [Uri]::EscapeDataString($Name)
    $request = @{
        Method = 'Post'
        Uri = "$loggerBase/$encodedName"
        ContentType = 'application/json'
        Body = $body
        UseBasicParsing = $true
        ErrorAction = 'Stop'
    }
    $response = Invoke-WebRequest @request

    if ($response.StatusCode -ne 204) {
        throw "Unexpected HTTP status: $($response.StatusCode)"
    }
}
~~~

Trong hàm ghi, null/chuỗi rỗng được đổi thành body `{}`. Một mức khác được đổi thành đối tượng JSON có khóa configuredLevel. Các lệnh giữ cùng biến `$loggerBase` trong terminal này.

Đọc tổng quan:

~~~powershell
$catalog = Invoke-RestMethod -Uri $loggerBase
$catalog.levels
$catalog.groups.diagnostics
~~~

Xác nhận group có đúng `demo.alpha` và `demo.beta` trước khi dùng nó.

### 5.2. Ghi nhận trạng thái đầu tiên

~~~powershell
$loggerName = 'demo.alpha.Worker'
$beforeLogger = Read-LogTarget -Name $loggerName
$beforeLogger

Invoke-RestMethod -Uri $probeUri
~~~

Worker có configuredLevel null và effectiveLevel INFO. Phần message của các log từ endpoint thử nghiệm, theo thứ tự, là:

~~~text
ALPHA_INFO
ALPHA_WARN
BETA_WARN
FIXED_WARN
~~~

Không đưa thời gian, PID hoặc thread vào kết quả cố định: những trường đó thay đổi theo lần chạy. Nếu có log khác từ framework, đối chiếu riêng các message bắt đầu bằng ALPHA_, BETA_ hoặc FIXED_.

### 5.3. Đặt trực tiếp Worker thành DEBUG

~~~powershell
Write-LogTarget -Name $loggerName -Level 'DEBUG'
Read-LogTarget -Name $loggerName
Invoke-RestMethod -Uri $probeUri
~~~

GET logger cần cho thấy configuredLevel DEBUG và effectiveLevel DEBUG. Lần gọi probe mới phát ra:

~~~text
ALPHA_DEBUG
ALPHA_INFO
ALPHA_WARN
BETA_WARN
FIXED_WARN
~~~

Đây là thay đổi của đúng Worker, không phải bật DEBUG cho mọi logger của ứng dụng. `demo.alpha` vẫn giữ INFO; logger beta và Fixed không được đổi bởi thao tác này.

Việc log cũ không có ALPHA_DEBUG vẫn là bình thường. Thay mức hiện tại không tái tạo những sự kiện đã bị loại trước đó.

### 5.4. Khôi phục theo mức gán trực tiếp đã lưu

~~~powershell
Write-LogTarget -Name $loggerName -Level $beforeLogger.configuredLevel
Read-LogTarget -Name $loggerName
Invoke-RestMethod -Uri $probeUri
~~~

Vì configuredLevel ban đầu là null, hàm gửi `{}`. Worker không còn mức riêng và trở về kế thừa INFO trong cấu hình hiện tại. Các message của probe trở lại bốn dòng ban đầu.

Đừng ghi `INFO` chỉ vì trước đó nhìn thấy effectiveLevel INFO. Làm vậy sẽ tạo một mức riêng mới và khiến Worker không còn theo thay đổi mức của logger cha về sau.

Quy tắc khôi phục một logger thường:

| Trạng thái đã lưu | Request khôi phục |
| --- | --- |
| configuredLevel null, effectiveLevel INFO | Gửi `{}` để trả về kế thừa |
| configuredLevel WARN | Gửi `{"configuredLevel":"WARN"}` |
| configuredLevel DEBUG | Gửi `{"configuredLevel":"DEBUG"}` |

Nếu logger cha đã đổi trong lúc quan sát, khôi phục configuredLevel null có thể cho một effectiveLevel khác trước. Khi đó phải phân biệt “đã trả lại chính sách kế thừa” với “toàn bộ cây logger đã về trạng thái cũ”.

ROOT là gốc của cây và không có logger cha để kế thừa như Worker. Nếu có lý do phải đổi ROOT, lưu và khôi phục mức tường minh của ROOT; không dùng thao tác xóa mức của một logger thường làm khuôn chung cho ROOT.

## 6. Đổi mức của một group và nhìn đúng phạm vi tác động

Thực hiện phần này sau khi Worker đã được khôi phục ở mục 5. Giữ nguyên tiến trình ứng dụng để quan sát thay đổi trong lúc chạy.

### 6.1. Lưu group và từng thành viên trước khi ghi

~~~powershell
$groupName = 'diagnostics'
$beforeGroup = Read-LogTarget -Name $groupName

$beforeMembers = @(
    foreach ($member in $beforeGroup.members) {
        $state = Read-LogTarget -Name $member
        [pscustomobject]@{
            name = $member
            configuredLevel = $state.configuredLevel
            effectiveLevel = $state.effectiveLevel
        }
    }
)

$beforeGroup
$beforeMembers | Format-Table name, configuredLevel, effectiveLevel
~~~

Trong ví dụ, bản ghi trước thay đổi là:

| Đích | configuredLevel | effectiveLevel |
| --- | --- | --- |
| group diagnostics | Chưa đặt | Không có một effectiveLevel chung trong phản hồi group |
| demo.alpha | INFO | INFO |
| demo.beta | WARN | WARN |

`members` cũng là một phần của bản ghi. Không chỉ lưu mức group: group chưa có mức chung không đồng nghĩa mọi thành viên đều chưa có mức riêng.

### 6.2. Đặt group thành DEBUG

~~~powershell
Write-LogTarget -Name $groupName -Level 'DEBUG'

Read-LogTarget -Name $groupName
Read-LogTarget -Name 'demo.alpha'
Read-LogTarget -Name 'demo.beta'
Read-LogTarget -Name 'demo.alpha.Worker'
Read-LogTarget -Name 'demo.alpha.Fixed'

Invoke-RestMethod -Uri $probeUri
~~~

Kết quả cần giải thích được:

- Hai thành viên demo.alpha và demo.beta được gán DEBUG trực tiếp.
- Worker của hai nhánh chưa có mức riêng nên kế thừa DEBUG.
- demo.alpha.Fixed vẫn giữ WARN vì có mức riêng.
- ROOT vẫn có thể là INFO; đó không phải mâu thuẫn với DEBUG của các nhánh con.

Các message của probe:

~~~text
ALPHA_DEBUG
ALPHA_INFO
ALPHA_WARN
BETA_DEBUG
BETA_INFO
BETA_WARN
FIXED_WARN
~~~

Mức của group không xóa mức riêng của mọi logger nằm sâu trong nhánh. Muốn biết một lớp hoặc tên logger cụ thể có thực sự ở DEBUG, đọc chính logger đó và kiểm tra log mới.

### 6.3. Mức hiển thị của group không bảo đảm các thành viên luôn đồng nhất

Có thể thử thêm, trong cùng phiên thực hành:

~~~powershell
Write-LogTarget -Name 'demo.beta' -Level 'ERROR'

Read-LogTarget -Name $groupName
Read-LogTarget -Name 'demo.beta'
Read-LogTarget -Name 'demo.beta.Worker'

Invoke-RestMethod -Uri $probeUri
~~~

Trong Spring Boot 3.3 của ví dụ, mức đã đặt cho group vẫn được báo là DEBUG, nhưng demo.beta đã được đổi riêng thành ERROR. Không có cơ chế khóa mọi thành viên mãi mãi theo mức cuối cùng đặt qua group.

Vì probe beta chỉ gọi DEBUG, INFO và WARN, không message nào của beta được phát ra ở lần này:

~~~text
ALPHA_DEBUG
ALPHA_INFO
ALPHA_WARN
FIXED_WARN
~~~

Đây cũng là lý do một giá trị group nhìn có vẻ đúng chưa đủ để kết luận logger của thành phần đang quan sát có mức mong muốn.

## 7. Xóa mức tạm của group khác với khôi phục bản ghi ban đầu

### 7.1. Điều gì xảy ra khi gửi {} cho group?

Tiếp tục trong cùng phiên:

~~~powershell
Write-LogTarget -Name $groupName -Level $null

Read-LogTarget -Name 'demo.alpha'
Read-LogTarget -Name 'demo.beta'
Invoke-RestMethod -Uri $probeUri
~~~

Lệnh này xóa mức gán trên các thành viên của group. Nó không lấy lại lần lượt INFO và WARN từ bản ghi bạn đã lưu.

Trong cây logger của bài:

| Thành viên | Trước thay đổi group | Sau khi xóa mức group |
| --- | --- | --- |
| demo.alpha | configured INFO, effective INFO | configured null, kế thừa INFO |
| demo.beta | configured WARN, effective WARN | configured null, kế thừa INFO |

Ngay cả alpha có effectiveLevel giống lúc đầu, configuredLevel của nó vẫn đã khác. Với beta, cả ý nghĩa cấu hình và mức hiệu lực đã thay đổi.

Các message của probe lúc này là:

~~~text
ALPHA_INFO
ALPHA_WARN
BETA_INFO
BETA_WARN
FIXED_WARN
~~~

BETA_INFO xuất hiện thêm so với trạng thái khởi đầu. Đó là bằng chứng cụ thể rằng “xóa DEBUG của group” chưa bằng “khôi phục đúng trạng thái trước khi bật DEBUG”.

Endpoint không duy trì một ngăn xếp các mức cũ để mỗi lần gửi `{}` lại quay về một lần cấu hình trước. Bản ghi trước thay đổi do người vận hành hoặc công cụ quản lý phiên quan sát giữ.

### 7.2. Khôi phục đúng group và từng thành viên

Để trả lại bản ghi ở mục 6.1, thứ tự là:

1. Khôi phục mức của group, nhằm trả lại cả trạng thái group được báo cáo.
2. Khôi phục configuredLevel của từng thành viên, nhằm giữ được các ngoại lệ riêng đã tồn tại.
3. Đọc lại group, thành viên và logger con liên quan.

Không đảo thứ tự hai thao tác ghi đầu: ghi group sau cùng sẽ lại áp dụng một mức chung lên các thành viên vừa được khôi phục.

Với dữ liệu đã lưu trong terminal, có thể thực hiện:

~~~powershell
Write-LogTarget -Name $groupName -Level $beforeGroup.configuredLevel

foreach ($saved in $beforeMembers) {
    Write-LogTarget -Name $saved.name -Level $saved.configuredLevel
}

Read-LogTarget -Name $groupName
foreach ($saved in $beforeMembers) {
    Read-LogTarget -Name $saved.name
}

Read-LogTarget -Name 'demo.alpha.Worker'
Read-LogTarget -Name 'demo.beta.Worker'
Read-LogTarget -Name 'demo.alpha.Fixed'
Invoke-RestMethod -Uri $probeUri
~~~

Trong ví dụ, group trở về chưa có mức chung, demo.alpha trở về mức riêng INFO, demo.beta trở về mức riêng WARN và Fixed vẫn WARN. Worker tiếp tục kế thừa từ đúng nhánh.

Các message lại là:

~~~text
ALPHA_INFO
ALPHA_WARN
BETA_WARN
FIXED_WARN
~~~

Nếu trước khi quan sát group có mức INFO nhưng một thành viên đã được đổi riêng thành WARN, cũng cần lưu cả hai tầng: trả group về INFO trước, rồi trả ngoại lệ của thành viên về WARN.

Các kết quả ở mục 6–7 là hành vi quan sát được từ cấu hình Spring Boot 3.3/Logback của dự án này. Khi thay backend hoặc cơ chế quản lý logging, xác minh lại cách thao tác lên group và cách kế thừa thay vì đoán từ tên group.

## 8. Tổ chức một phiên thay đổi có khôi phục rõ ràng

### 8.1. Dùng finally và báo lỗi khôi phục theo từng đích

Các thao tác ở phần trước giúp hiểu từng bước. Khi gom thành một phiên thử nghiệm, dùng `try/finally` để vẫn thử khôi phục khi phần quan sát phát sinh exception.

Đoạn sau dùng lại hai hàm Read-LogTarget và Write-LogTarget đã khai báo. Chạy sau khi hoàn tất khôi phục ở mục 7. Nó giả định bạn là người duy nhất thay đổi các đích này trong phiên thực hành.

~~~powershell
$sessionGroupName = 'diagnostics'
$sessionGroupBefore = Read-LogTarget -Name $sessionGroupName

$sessionMembersBefore = @(
    foreach ($member in $sessionGroupBefore.members) {
        $state = Read-LogTarget -Name $member
        [pscustomobject]@{
            name = $member
            configuredLevel = $state.configuredLevel
            effectiveLevel = $state.effectiveLevel
        }
    }
)

try {
    Write-LogTarget -Name $sessionGroupName -Level 'DEBUG'
    Read-LogTarget -Name $sessionGroupName
    Read-LogTarget -Name 'demo.alpha.Worker'
    Read-LogTarget -Name 'demo.beta.Worker'
    Invoke-RestMethod -Uri $probeUri -ErrorAction Stop
}
finally {
    $restoreErrors = [System.Collections.Generic.List[string]]::new()

    try {
        Write-LogTarget -Name $sessionGroupName -Level $sessionGroupBefore.configuredLevel
    }
    catch {
        $restoreErrors.Add("group $sessionGroupName : $($_.Exception.Message)")
    }

    foreach ($saved in $sessionMembersBefore) {
        try {
            Write-LogTarget -Name $saved.name -Level $saved.configuredLevel
        }
        catch {
            $restoreErrors.Add("logger $($saved.name) : $($_.Exception.Message)")
        }
    }

    if ($restoreErrors.Count -gt 0) {
        throw "Restore incomplete: $($restoreErrors -join '; ')"
    }
}
~~~

Khôi phục một đích thất bại không làm bỏ qua các đích còn lại trong finally. Tuy vậy, các POST riêng biệt không phải một giao dịch nguyên tử: nếu một request thất bại, trạng thái có thể chỉ được trả lại một phần.

Không thông báo “đã khôi phục” chỉ vì khối finally đã chạy. Cần đọc lại sau khi ghi:

~~~powershell
$groupAfter = Read-LogTarget -Name $sessionGroupName

if ([string]$groupAfter.configuredLevel -ne [string]$sessionGroupBefore.configuredLevel) {
    throw 'Group configuredLevel was not restored'
}

$expectedMembers = @($sessionGroupBefore.members | Sort-Object) -join '|'
$actualMembers = @($groupAfter.members | Sort-Object) -join '|'

if ($actualMembers -ne $expectedMembers) {
    throw 'Group membership changed during the session'
}

foreach ($saved in $sessionMembersBefore) {
    $actual = Read-LogTarget -Name $saved.name

    if ([string]$actual.configuredLevel -ne [string]$saved.configuredLevel) {
        throw "Configured level mismatch: $($saved.name)"
    }

    if ([string]$actual.effectiveLevel -ne [string]$saved.effectiveLevel) {
        throw "Effective level mismatch: $($saved.name)"
    }
}

Read-LogTarget -Name 'demo.alpha.Fixed'
Invoke-RestMethod -Uri $probeUri -ErrorAction Stop
~~~

Phép so sánh chuyển configuredLevel sang chuỗi để coi trường không có và null là cùng trạng thái không gán mức trong phản hồi của bài. Phần so effectiveLevel giúp phát hiện ảnh hưởng từ logger cha nếu có thay đổi ngoài dự kiến.

Một phiên bị đóng cưỡng bức, tiến trình PowerShell bị kill hoặc mất kết nối không được bảo đảm sẽ hoàn tất finally. Cần có người hoặc công cụ tiếp tục xác minh và khôi phục, thay vì chỉ tin rằng mã dọn dẹp luôn chạy.

### 8.2. Bản ghi cần gắn với đúng tiến trình

Trong vận hành có nhiều instance, mức log là trạng thái của tiến trình nhận request. POST qua bộ cân bằng tải có thể đổi instance A, còn GET tiếp theo lại đọc B.

Lưu bản ghi cùng định danh ứng dụng, instance, thời gian, logger/group và mục đích quan sát. Xác nhận các request đọc/ghi đến đúng đích. Một bản ghi lấy trước khi ứng dụng khởi động lại không được áp dụng mù quáng vào tiến trình mới.

Nếu có người hoặc công cụ khác cùng thay đổi mức, bản ghi ban đầu có thể không còn là trạng thái cần trả lại. Trước khi khôi phục, kiểm tra trạng thái live còn phù hợp với thay đổi của phiên mình hay đã bị một thay đổi khác thay thế. Khi có xung đột, dừng việc ghi đè theo bản ghi cũ và phối hợp người đang sở hữu thay đổi.

### 8.3. Phạm vi thời gian và dữ liệu

Thay đổi qua endpoint không tự sửa application.properties, YAML hay biến môi trường. Nó cũng không có tham số thời hạn tự trả về trong hợp đồng POST của bài. Nếu cần một cửa sổ quan sát ngắn, đặt rõ thời điểm kết thúc và trách nhiệm khôi phục ở công cụ hoặc quy trình bên ngoài endpoint.

Khởi động lại sẽ nạp cấu hình logging theo các nguồn lúc khởi động; việc backend tự nạp lại cấu hình hoặc một bộ điều khiển bên ngoài can thiệp cũng có thể thay đổi mức. Vì vậy, dùng GET loggers để đọc trạng thái live, không chỉ nhìn giá trị logging.level trong tệp hoặc Environment.

DEBUG/TRACE có thể tăng lượng log, chi phí xử lý và dữ liệu được ghi. Chọn logger hoặc group nhỏ đủ cho vấn đề; không mặc định đổi ROOT hoặc một group rộng để tìm một lỗi hẹp. Mức log không làm dữ liệu nhạy cảm tự được che, nên phần code phát sinh log vẫn phải phù hợp với dữ liệu được phép ghi.

Khi kết thúc, xác nhận cả cấu hình và lượng log mới đã trở về trạng thái cần thiết. Những log đã phát sinh trong cửa sổ DEBUG vẫn tồn tại theo chính sách lưu trữ của hệ thống; khôi phục mức không xóa chúng.

## 9. Phân loại lỗi khi request hoặc kết quả chưa đúng

| Hiện tượng | Điều cần kiểm tra |
| --- | --- |
| GET/POST trả 404 | Dependency Actuator, bật endpoint, công bố HTTP, base path/cổng quản trị và địa chỉ đúng instance |
| POST trả 401/403 | Xác thực, phân quyền, chính sách bảo vệ request ghi và CSRF nếu dùng Spring Security |
| POST trả 400 | JSON, tên khóa configuredLevel và mức có trong danh sách được hỗ trợ |
| POST trả 415 | Content-Type và dạng body thực tế được gửi |
| POST trả 204 nhưng client chờ JSON | 204 không có response body; tiếp tục GET để xác nhận |
| GET cho thấy DEBUG nhưng không có dòng DEBUG mới | Đúng logger chưa, có thực thi nhánh mã sau khi đổi không, bộ lọc/appender có chặn không, đang đọc log đúng instance chưa |
| Group báo DEBUG nhưng một logger con vẫn WARN | Mức riêng của logger con, thao tác riêng lên thành viên hoặc group chồng lấn |
| Gửi {} nhưng không về đúng mức cũ | Đã xóa mức gán trực tiếp; chưa khôi phục bản ghi hoặc logger cha đã thay đổi |
| Tệp vẫn ghi WARN nhưng GET live là DEBUG | Thay đổi runtime chưa làm nguồn cấu hình trên đĩa đổi theo |

Không mặc định mọi tên logger gõ sai đều bị từ chối rõ ràng: tùy backend, tên mới vẫn có thể được tạo hoặc được hỏi với mức kế thừa. Xác nhận tên từ mã hoặc danh sách logger thay vì xem một request thành công là bằng chứng đã chọn đúng thành phần.

POST có thể bị chặn dù GET cùng endpoint thành công. Trong ứng dụng có Spring Security, giữ cơ chế bảo vệ request ghi phù hợp với cách xác thực; không vô hiệu hóa CSRF toàn ứng dụng chỉ để một lệnh thử đi qua.

Nếu ứng dụng đổi cổng quản trị hoặc đường dẫn Actuator, dùng URL thực tế. Các mã HTTP ở bảng là hướng phân loại, không thay thế việc đọc response và kiểm tra proxy hoặc chính sách cụ thể của hệ thống. [Spring Boot 3.3 — công bố và bảo vệ endpoint](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html).

## 10. Tự kiểm tra

**Câu 1:** Logger Worker ban đầu có configuredLevel null và effectiveLevel INFO. Sau khi quan sát ở DEBUG, đặt Worker thành INFO có khôi phục chính xác không?

Không. Bạn đã tạo một mức trực tiếp. Muốn trả lại chính sách cũ, bỏ mức trực tiếp để Worker tiếp tục kế thừa; sau đó kiểm tra effectiveLevel trong cây hiện tại.

**Câu 2:** Hai thành viên của group ban đầu lần lượt INFO và WARN. Bật group DEBUG rồi gửi {} cho group có đủ không?

Không. Thao tác xóa mức không nhớ hai mức ban đầu. Cần bản ghi của từng thành viên và khôi phục chúng.

**Câu 3:** Group báo DEBUG nhưng demo.alpha.Fixed vẫn WARN. Có nhất thiết là endpoint lỗi không?

Không. Logger Fixed có mức trực tiếp WARN. Đọc đúng logger đó để phân biệt mức group, mức thành viên và mức của logger con.

**Câu 4:** Sau khi đổi runtime, application.properties vẫn ghi WARN. Vì sao?

Endpoint thay đổi mức của hệ thống logging đang chạy, không phải một trình chỉnh sửa tệp cấu hình. Trạng thái live cần đọc từ loggers.

**Câu 5:** Khôi phục các thành viên trước, rồi khôi phục group sau có luôn giữ đúng các ngoại lệ cũ không?

Không. Thao tác group sau cùng có thể áp dụng lại một mức chung lên các thành viên. Trả mức group trước, rồi trả mức riêng của từng thành viên và xác minh.

**Bài tập:** Thực hiện trọn một phiên với group diagnostics. Ghi trước mức của group, hai thành viên và Fixed; bật DEBUG; tạo log; xóa mức group để quan sát sự khác biệt; sau đó khôi phục từ bản ghi. Chỉ kết luận hoàn tất khi configuredLevel, effectiveLevel và các message từ probe phù hợp trạng thái đã lưu.
