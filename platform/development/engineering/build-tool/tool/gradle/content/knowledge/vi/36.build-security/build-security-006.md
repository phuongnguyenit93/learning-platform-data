# Giảm dữ liệu nhạy cảm trong log, test report và Build Scan của Gradle

## 1. Vì sao bài học này quan trọng?

Gradle là công cụ build, nhưng cũng là nơi tập trung rất nhiều dữ liệu kỹ thuật: cấu hình repository, thông báo lỗi biên dịch, kết quả kiểm thử, đầu ra của tiến trình Java, đường dẫn máy phát triển, tên tài khoản, thông tin hệ điều hành, nhật ký CI và metadata khi phát hành. Những dữ liệu này giúp chẩn đoán lỗi, nhưng một dòng log thiếu kiểm soát có thể làm lộ mật khẩu repository, API token, thông tin cá nhân hoặc dữ liệu khách hàng.

Một rủi ro thường bị bỏ qua: **một bí mật có thể xuất hiện đồng thời ở nhiều nơi**. Chẳng hạn, test in access token bằng System.out.println; tùy cấu hình, chuỗi đó có thể đi vào:

- Console của Gradle hoặc IDE.
- Log đã lưu bởi CI provider.
- JUnit XML, phần system-out hay system-err.
- HTML test report hoặc binary test results được dùng để tạo reports.
- Build Scan/Develocity nếu bật thu thập đầu ra kiểm thử.
- Artifact được upload tự động lên dịch vụ lưu trữ CI.
- Ticket, chat hoặc ảnh chụp màn hình do người điều tra sao chép.

Chỉ “ẩn dòng trên console” không có nghĩa các bản sao khác đã an toàn. Đặt mục tiêu **không sinh nội dung nhạy cảm trong logs và reports ngay từ đầu**, sau đó dùng cấu hình Gradle, quyền truy cập và quy trình kiểm tra như những lớp phòng vệ bổ sung.

Bài thuộc chủ đề **Build Tool Gradle**, nhóm **An toàn build**, với đề bài **“Giảm dữ liệu nhạy cảm trong log, test report và Build Scan”**.

Sau khi hoàn thành, bạn có thể:

1. Nhận diện secrets, dữ liệu cá nhân, thông tin nội bộ và metadata nhạy cảm trong build.
2. Lập bản đồ đường đi của dữ liệu qua stdout/stderr, exception messages, JUnit XML/HTML, Build Scan và CI artifacts.
3. Phân biệt **giảm thu thập**, **redaction/masking**, **obfuscation**, **giới hạn truy cập** và **xóa sau sự cố**.
4. Cấu hình Groovy DSL để giảm console test logging và không xuất stdout/stderr vào JUnit XML.
5. Hiểu tại sao lỗi kiểm thử và HTML report vẫn có thể chứa dữ liệu dù đã tắt XML stdout.
6. Lấy credentials qua Gradle typed APIs hoặc environment providers, không hardcode hay in chúng.
7. Cấu hình Develocity Gradle plugin để tắt build/test output capture và obfuscate một số identifying metadata, với giới hạn được giải thích rõ.
8. Viết một lab **Java 17 + Gradle + JUnit 5** có kết quả xác định và không cần secrets thật.
9. Chạy trình quét report canary bằng Java 17 mà không in lại nội dung phát hiện.
10. Thiết kế CI fail-closed cho báo cáo chưa được kiểm tra, có kiểm soát retention và permissions.
11. Phản ứng đúng nếu dữ liệu đã xuất hiện trong log, test report hoặc Build Scan.
12. Tránh hiểu nhầm bảo mật từ **--quiet**, **--stacktrace**, **--debug**, **showStandardStreams=false**, masking của CI hay một quyền xem Build Scan.

## 2. “Dữ liệu nhạy cảm” trong bối cảnh Gradle là gì?

Có nhiều mức độ nhạy cảm:

| Nhóm | Ví dụ | Nguy cơ nếu lọt vào log |
| --- | --- | --- |
| **Secret xác thực** | Password Maven repository, token deploy, SSH private key, OIDC token, signing key | Kẻ khác có thể truy cập hệ thống hoặc phát hành artifact giả |
| **Thông tin cá nhân** | Email thật, số điện thoại, địa chỉ, user ID nội bộ, session identifier | Vi phạm riêng tư, giúp định danh người dùng |
| **Thông tin hệ thống** | Username/hostname, IP nội bộ, user home, đường dẫn workspace | Tiết lộ cấu trúc tổ chức/hạ tầng |
| **Thông tin sản phẩm** | Tên dự án mật, endpoint nội bộ, tên nhánh hoặc task chứa mã khách hàng | Lộ roadmap, kiến trúc, tổ chức vận hành |
| **Dữ liệu kiểm thử** | Nội dung request/response, fixture từ production, assertion values, stack traces | Có thể chứa PII hoặc nội dung kinh doanh thật |
| **Báo cáo/artefact** | JUnit XML, HTML report, log bundles, ZIP build outputs, Gradle cache | Có thể giữ bản sao lâu hơn console ban đầu |
| **Diagnostic metadata** | Build Scan tags/custom values, commit messages, environment info | Chia sẻ ra dịch vụ hoặc người xem ngoài ý muốn |

**Không phải dữ liệu nào cũng là secret**, nhưng việc có thể quan sát một giá trị khi truy cập nội bộ không đồng nghĩa được phép xuất bản nó ra dịch vụ bên ngoài.

Ví dụ minh họa luôn sử dụng **canary giả lập**, không dùng mật khẩu hoặc dữ liệu khách hàng thật. Một chuỗi có tên **TRAINING_CANARY_NOT_A_SECRET** chỉ là văn bản đào tạo, không thể xác thực với hệ thống nào.

## 3. Threat model: ai có thể nhìn thấy đầu ra?

Trước khi bật logging hoặc scan, hãy trả lời bốn câu hỏi:

1. **Nguồn**: Giá trị nào có thể nhạy cảm? Nó đến từ CI secret store, file .env, response của API, database hay kết quả test?
2. **Kênh**: Giá trị có thể đi vào stdout, stderr, stack trace, build script logger, JUnit XML, HTML, Build Scan, artifact hoặc Gradle daemon log không?
3. **Người xem**: Ai có thể truy cập CI log, build artifact, máy agent, Build Scan link, issue tracker và chat?
4. **Thời gian lưu**: Dữ liệu có retention bao lâu? Ai có quyền xóa? Có backup hoặc bản sao không thể thu hồi ngay không?

Một mô hình:

~~~text
CI secret store / repository credential / test fixture
                         |
                         v
              Gradle settings + build logic
                         |
        +----------------+----------------+
        |                |                |
        v                v                v
  Task logger       Java/Test JVM     Plugin/HTTP client
        |                |                |
        +--------+-------+----------------+
                 |
        stdout / stderr / failures
                 |
       +---------+------------+----------------+
       |                      |                |
       v                      v                v
  CI console log          JUnit results      Build Scan
       |                 XML / HTML / binary    |
       v                      |                v
  CI retention            artifact upload    scan server
       |                      |                |
       +----------------------+----------------+
                              |
                         người đọc
~~~

Lớp bảo vệ bền vững nhất nằm **trước thời điểm data trở thành log/report**. Xóa sau khi đã chia sẻ chỉ là biện pháp giảm hậu quả.

### 3.1. Đường truyền bí mật phải càng ngắn càng tốt

Thay vì đọc token vào một String rồi in kèm request, hãy truyền secret qua API xác thực đúng, tránh giữ bản sao không cần thiết và không thêm giá trị vào task description, path, build scan custom value hoặc exception.

### 3.2. Biến môi trường không tự động an toàn

Lưu token trong environment variable an toàn hơn hardcode vào Git, **nhưng vẫn nguy hiểm** nếu code thực hiện:

~~~groovy
logger.lifecycle(System.getenv('PRIVATE_REPOSITORY_PASSWORD'))
~~~

Đây là **ví dụ sai để nhận diện**, không đưa vào lab chạy được. Đọc từ environment chỉ an toàn khi build logic và plugins **không tiết lộ nó ra bất cứ output channel nào**.

## 4. Thứ tự ưu tiên khi giảm rò rỉ

Áp dụng nhiều lớp, theo thứ tự:

1. **Data minimization**: test dùng synthetic data; logs chỉ chứa trạng thái, count, latency, correlation ID được cho phép.
2. **Safe-by-design APIs**: credentials được truyền vào repository/publishing APIs; không tự build log có kèm secret.
3. **Structured logging**: chỉ cho phép các fields công khai được duyệt, không stringify toàn bộ request/response.
4. **Report configuration**: giảm stdout/stderr trong JUnit XML; cấu hình testLogging.
5. **Scan capture controls**: tắt những loại Build Scan output không cần thiết, obfuscate identifying fields cụ thể.
6. **Access control**: CI artifacts/scan chỉ nhóm cần biết xem được, dùng authentication, TLS, retention ngắn.
7. **Detection**: quét report, log và artifacts bằng synthetic canaries/test patterns; theo dõi policy violations.
8. **Incident response**: revoke/rotate secrets, hạn chế quyền xem, xóa/quarantine bản sao và điều tra nguồn rò.

Masking dựa trên chuỗi chỉ là **phòng vệ dự phòng**, không thể bảo đảm loại hết token biến đổi, URL-encoded, base64-encoded, JSON-escaped, multiline hoặc stack traces chứa một phần giá trị.

## 5. Gradle console logging: những gì người dùng nhìn thấy

Gradle có các logging levels như QUIET, LIFECYCLE, INFO, DEBUG. Các lệnh thường gặp:

~~~bash
./gradlew test --console=plain
./gradlew test --quiet
./gradlew test --info
./gradlew test --debug
./gradlew test --stacktrace
~~~

**Cảnh báo chính:**

- **--quiet** giảm số dòng in ở console nhưng không biến một secret đã được đưa vào exception thành an toàn. Nó cũng không tự làm sạch JUnit XML, HTML hoặc Build Scan.
- **--info** và nhất là **--debug** có thể làm xuất hiện chi tiết bổ sung từ tasks, plugins, HTTP clients và Gradle internals. Không chạy debug trên CI chứa credentials nếu chưa kiểm soát log output.
- **--stacktrace** giúp chẩn đoán lỗi nhưng exception message, file path, package name và nested causes có thể nhạy cảm.
- **--console=plain** chỉ thay cách định dạng console; không phải một security feature.
- **logger.lifecycle**, **logger.info**, **println** và **System.out.println** đều không nên nhận token hoặc dữ liệu cá nhân thô.
- Build scripts/plugins có thể ghi logs ngay trong configuration phase, trước khi Test tasks chạy.

### 5.1. Ví dụ chống lại logging vô tội vạ

Không nên:

~~~groovy
def accessToken = providers
        .environmentVariable('DEPLOY_TOKEN')
        .orNull

logger.lifecycle('Deploy token: ' + accessToken)
~~~

Đây là anti-pattern, **không chạy với secret thật**. Khi muốn kiểm tra cấu hình đã đủ, chỉ báo thông tin không tiết lộ giá trị:

~~~groovy
def hasToken = providers
        .environmentVariable('DEPLOY_TOKEN')
        .map { !it.isBlank() }
        .getOrElse(false)

logger.lifecycle('Deploy credential configured: ' +
        (hasToken ? 'yes' : 'no'))
~~~

Dòng thứ hai chỉ minh họa tín hiệu **có/không**. Đối với một số hệ thống, ngay cả việc cho biết credential có được cấp cũng là metadata không nên công bố; tốt hơn nữa là chỉ thực hiện validation khi task cần secret được chọn.

### 5.2. Không đưa secret vào task name hoặc command line

Tránh:

~~~bash
./gradlew publish -PreleasePassword=THIS_IS_NOT_A_REAL_PASSWORD
~~~

Dù chuỗi là giả lập, **cách truyền này không nên dùng cho secret thật**: CLI arguments có thể xuất hiện trong shell history, process inspection hoặc hệ thống ghi command invocation.

Tương tự, một task tên chứa email/user ID thật có thể xuất hiện trong timeline, reports và Build Scan. Tạo task names ổn định và không mang dữ liệu người dùng.

## 6. Ưu tiên Gradle typed credentials APIs

Gradle có Typed Credentials API giúp việc xử lý repository credentials rõ ràng và tránh phải tự in hoặc gắn token vào URL. Gradle security guidance khuyến nghị dùng typed credentials và secret store thay vì đưa secrets vào checked-in gradle.properties.

**Ví dụ repository tùy chọn** (không thuộc lab runnable, vì miền .invalid cố ý không có server thật):

~~~groovy
repositories {
    maven {
        name = 'privateArtifacts'
        url = uri('https://repository.example.invalid/releases')
        credentials(PasswordCredentials)
    }
}
~~~

Gradle có cơ chế đọc credentials theo tên repository: ví dụ **privateArtifactsUsername** và **privateArtifactsPassword** qua Gradle properties/environment-backed project properties. CI có thể cung cấp chúng qua secret store với dạng environment variables:

~~~text
ORG_GRADLE_PROJECT_privateArtifactsUsername
ORG_GRADLE_PROJECT_privateArtifactsPassword
~~~

Không ghi giá trị thật của các biến này vào build.gradle, gradle.properties được commit, log hoặc test reports. Với repository giả **.invalid**, snippet chỉ để minh họa API, không thể dùng để resolve dependencies thật.

### 6.1. Tại sao typed credentials tốt hơn tự tạo URL?

Không nên tạo URL như:

~~~text
https://username:password@repository-host/path
~~~

vì URL có thể bị in khi request fail, qua proxy logs, exception messages hoặc diagnostic tools.

Với **credentials(PasswordCredentials)**, Gradle quản lý credential fields theo API, có cơ chế hỗ trợ redaction cho những kênh do Gradle/Build Scan quản lý. **Đây không phải lá chắn tuyệt đối:** plugin tự logger.lifecycle(password) vẫn có thể làm lộ giá trị.

### 6.2. Đặt secrets ở đúng nơi

- **CI**: dùng secret store do runner cấp, role/permission tối thiểu, environment variables chỉ dành cho trusted jobs.
- **Máy phát triển**: ưu tiên credential manager/environment provider thay vì plain-text files.
- **Gradle User Home**: bảo vệ filesystem permissions vì có thể lưu Gradle properties, init scripts, credentials và daemon logs.
- **Repository source**: không commit token; không hardcode sample credential “tạm thời” rồi quên xóa.
- **Untrusted PRs**: không cấp publish/signing tokens, và không cho tùy ý gọi trusted credentialed jobs.

### 6.3. Configuration cache và secrets

Configuration cache lưu state của phần cấu hình build. Không resolve secret sớm ở configuration phase rồi lưu String vào task input, cacheable output hoặc static object. Dùng Provider/typed credential API theo đúng vòng đời, tránh biến secret thành dữ liệu có thể được serialize/logged.

Truyền secrets qua providers cũng **không loại trừ nhu cầu kiểm toán plugin**: build.gradle, settings.gradle, buildSrc và init scripts có thể chạy mã tùy ý dưới quyền người dùng.

## 7. Test JVM stdout/stderr và Gradle console khác nhau

Một Test task chạy JUnit trong forked JVM. Test code có thể gọi:

~~~java
System.out.println("Status: OK");
System.err.println("Diagnostic: safe-category");
~~~

Đây là các **string an toàn**, chỉ dùng làm ví dụ. Nếu thay bằng body của HTTP response hoặc object.toString() có chứa credential, nội dung sẽ trở nên nhạy cảm.

Trong Gradle Groovy DSL, điều khiển console logging:

~~~groovy
tasks.withType(Test).configureEach {
    testLogging {
        events 'failed', 'skipped'
        showStandardStreams = false
        exceptionFormat =
                org.gradle.api.tasks.testing.logging
                    .TestExceptionFormat.SHORT
    }
}
~~~

**Ý nghĩa:**

- Chỉ yêu cầu console test events failed/skipped theo policy đã chọn.
- **showStandardStreams=false** không yêu cầu Gradle hiển thị STDOUT/STDERR của tests lên console.
- **exceptionFormat=SHORT** bớt chi tiết stack traces trong dòng test log thường.
- Cấu hình này **không thay đổi bản chất failures**, không sửa nội dung mà test thực sự viết và không làm sạch mọi report.
- Các log levels/plugin listeners khác vẫn có thể hiển thị thêm thông tin; **--debug** không phải một cam kết bảo mật.

Không đặt **showExceptions=false** để che test failures một cách mù quáng. Điều quan trọng là **exception messages của code và tests phải được viết an toàn**.

## 8. JUnit XML: mặc định có thể chứa stdout/stderr

Gradle Test task mặc định tạo JUnit-compatible XML (và HTML/binary results). Theo Gradle Java testing documentation, các tùy chọn:

- **includeSystemOutLog** mặc định **true**.
- **includeSystemErrLog** mặc định **true**.

Vì vậy, ngay cả khi console không hiện dòng System.out, XML vẫn có thể chứa nó.

Để ngăn đưa stdout/stderr vào XML:

~~~groovy
tasks.withType(Test).configureEach {
    reports {
        junitXml {
            required = true
            includeSystemOutLog = false
            includeSystemErrLog = false
        }
    }
}
~~~

Cấu hình này chỉ điều khiển **system-out/system-err elements trong JUnit XML**. Nó **không đảm bảo** XML không chứa dữ liệu nhạy cảm trong:

- **testcase name** hoặc dynamic/parameterized test display name.
- **failure message** và assertion actual/expected values.
- **stack trace** hoặc exception causes.
- **class/package names** và source paths.
- **Các report formats khác** do Gradle hoặc plugin tạo.

### 8.1. Ví dụ rò rỉ từ assertion

Không nên:

~~~java
assertEquals(expectedSecret, actualSecret);
~~~

khi một assertion failure có thể in cả actual/expected values vào JUnit XML và CI console.

Nên kiểm tra **hành vi không tiết lộ dữ liệu** hoặc kết quả đã được sanitize. Ví dụ:

~~~java
assertTrue(result.isAuthorized());
~~~

với kiểu dữ liệu phù hợp, và tránh tạo message thất bại chứa password, token, cookie hoặc raw payload. **Không thay assertion mạnh bằng assertion mơ hồ chỉ để tránh log:** hãy thiết kế assertion vẫn kiểm tra được logic nhưng phần dữ liệu hiện ra khi fail là an toàn.

### 8.2. Tên test cũng là dữ liệu có thể rò

Không nên tạo dynamic test name:

~~~text
test_login_user@example.com_token_XYZ
~~~

nếu email/token là dữ liệu thật. Tên test xuất hiện ở XML, HTML, Build Scan và CI test history. Nên dùng tên theo *hành vi*:

~~~text
rejectsExpiredCredential
returnsUnauthorizedForInvalidSession
masksSensitiveFields
~~~

### 8.3. Dữ liệu test từ production

Không đưa production user records hoặc raw database dumps vào fixtures chỉ vì chúng giúp tái hiện bug nhanh. Tạo synthetic dataset giữ hình dạng/constraints cần thiết và dùng user IDs giả, email miền **.invalid** hoặc **.example**, token canary không có quyền.

## 9. HTML và binary test results vẫn là một kênh riêng

Gradle Java testing tạo HTML report, JUnit XML và binary results phục vụ reporting. Mỗi loại có thể có chính sách lưu khác nhau.

- HTML test report thường nằm ở **build/reports/tests/test/**.
- XML results thường nằm ở **build/test-results/test/**.
- Binary test results có thể nằm dưới **build/test-results/test/binary/**; không nên upload toàn bộ folder khi chỉ cần XML.
- Một plugin aggregate test reports có thể sao chép/thể hiện lỗi hoặc stdout ở nơi khác.
- CI JUnit parsers có thể trích failure text và hiển thị nó trên web UI.

**Không suy rằng tắt includeSystemOutLog/includeSystemErrLog cũng làm sạch HTML/binary reports.** Hành vi chứa stdout/error của những formats có thể khác theo Gradle/plugin version. Quan trọng nhất: **test code không được in secrets**.

### 9.1. Chỉ upload thứ CI cần

Nếu CI chỉ cần test outcome, ưu tiên upload đúng những file phù hợp sau khi kiểm tra chính sách. Tránh:

~~~yaml
path: |
  .
~~~

vì upload toàn workspace có thể gồm caches, .env, build intermediates, key files và debug logs.

Nên hạn chế phạm vi:

~~~yaml
path: |
  build/test-results/test/TEST-*.xml
~~~

Ngay cả JUnit XML đã bỏ stdout/stderr vẫn cần audit failure messages và test names. Nếu tổ chức bắt buộc lưu HTML, hãy áp dụng cùng chính sách kiểm tra và permissions/retention, không coi nó là bản sao XML đã được lọc.

## 10. Build Scan là gì và nó có thể nhìn thấy gì?

Build Scan/Develocity giúp xem task graph, dependency behavior, cache hits, test outcomes, JVM/environment metadata và những diagnostics khác. Nó rất hữu ích nhưng cũng là **một kênh phát tán dữ liệu**.

Ví dụ một invocation:

~~~bash
./gradlew build --scan
~~~

Tùy phiên bản Gradle/Develocity plugin, cấu hình và dịch vụ, lệnh này có thể tự áp dụng scan integration hoặc dùng plugin đã được khai báo. Nếu scan được publish lên dịch vụ bên ngoài, dữ liệu rời khỏi local/CI environment. Trước khi bật cần kiểm tra:

1. Server/tenant nào nhận scan?
2. Tài khoản nào xem được?
3. Điều khoản và phạm vi thu thập dữ liệu nào đang được áp dụng?
4. Dữ liệu có chứa source-derived identifiers, test failures hay environment metadata không?
5. Có cơ chế obfuscation/capture control nào được bật?
6. Link scan có được đưa vào public CI logs hoặc issue tracker không?
7. Chính sách retention, delete, access audit và incident response là gì?

Không đưa một Build Scan link vào public chat chỉ vì URL khó đoán. **Khó đoán URL không thay thế phân quyền.**

### 10.1. Những nhóm metadata đáng chú ý

Tùy plugin/version/cấu hình, scan có thể ghi nhận:

- Gradle/JDK/OS details.
- Username, hostname, IP addresses và user home information.
- Tasks, dependencies, project names và source file paths.
- VCS metadata, branch/commit information.
- Test class names, results, durations và failures.
- Console build output hoặc test output nếu capture được bật.
- Custom values, tags và links do team tự thêm.
- Resource/process information.
- Các compiler/test errors có thể chứa dữ liệu từ source hay fixture.

Theo Develocity documentation, **source code và produced artifacts không được upload như một bộ mã nguồn đầy đủ mặc định**, nhưng thông báo lỗi và metadata có thể tiết lộ nội dung. Không biến phát biểu đó thành lời hứa “scan không có dữ liệu nhạy cảm”.

## 11. Tắt thu thập build/test outputs trong Develocity

Với Develocity Gradle plugin hiện đại, có các thuộc tính capture. **Đây là cấu hình tùy chọn ở settings.gradle cho những tổ chức đã phê duyệt Develocity**, không thuộc lab cơ bản chạy không cần scan plugin.

Ví dụ Groovy DSL:

~~~groovy
plugins {
    id 'com.gradle.develocity' version '4.6.0'
}

rootProject.name = 'gradle-report-privacy-lab'

develocity {
    buildScan {
        capture {
            buildLogging = false
            testLogging = false
            resourceUsage = false
        }
    }
}
~~~

Từng điều kiện:

- Plugin cần resolve từ nguồn được phép, version phải tương thích Gradle Wrapper đang dùng.
- **buildLogging=false** tắt capture build output logging vào scan.
- **testLogging=false** tắt capture test output logging vào scan.
- **resourceUsage=false** giảm một loại telemetry hệ thống khi không cần.
- **Điều cực kỳ quan trọng:** Theo Develocity docs, **tắt test output capturing không tắt việc thu thập test failures**. Exception/failure text vẫn có thể tiết lộ PII/secrets.
- Cấu hình trên **không ngăn Gradle console hoặc JUnit XML/HTML lưu dữ liệu**; phải quản lý từng kênh riêng.
- Nó cũng không làm sạch scan đã publish trước đó.

Trong môi trường có server riêng, cấu hình **develocity.server** và authentication/tenant policy theo tài liệu tổ chức. Không hardcode scan access key, bỏ TLS verification hoặc tự động chấp nhận điều khoản cho người dùng khác.

### 11.1. Tắt output capture qua JVM system properties

Theo Develocity Gradle plugin, khi được áp dụng đúng, có thể dùng:

~~~bash
./gradlew build \
  -Dscan.capture-build-logging=false \
  -Dscan.capture-test-logging=false \
  --scan
~~~

Các system properties là một lớp capture control, **không phải secret redactor**. Nếu plugins tự thêm custom values chứa token, nếu failure text có PII hoặc nếu dữ liệu nằm trong metadata khác, chúng vẫn có thể xuất hiện.

### 11.2. Không bật --scan khi chưa được phê duyệt

Nếu dữ liệu cần giữ hoàn toàn nội bộ và chưa có Develocity server đã duyệt, hãy dùng **--profile**, **--info** có kiểm soát trên local và JVM profilers được quản trị thay vì xuất bản scan. Không bật scan trên PRs từ nguồn không tin cậy hoặc khi test fixtures chưa được synthetic/sanitized.

## 12. Obfuscation trong Build Scan: phạm vi và giới hạn

Develocity plugin có các obfuscation functions cho một số trường identifying metadata. Ví dụ **bổ sung vào khối develocity.buildScan ở settings**, không phải một Gradle core plugin tự có:

~~~groovy
develocity {
    buildScan {
        obfuscation {
            username { ignored -> 'hidden-user' }
            hostname { ignored -> 'hidden-host' }
            ipAddresses { addresses ->
                addresses.collect { address -> '0.0.0.0' }
            }
            externalProcessName { ignored -> 'external-process' }
        }
    }
}
~~~

Đây là Groovy DSL minh họa theo Develocity 4.6.0. Trong production, nên kiểm tra exact API plugin version. Obfuscation chỉ tác động **những fields tương ứng**, không phải regex chạy trên toàn bộ scan.

Ví dụ username được thay **hidden-user** không đồng nghĩa:

- Email thật trong test exception bị ẩn.
- Token trong custom value bị ẩn.
- Secret được ghi trong task path không xuất hiện.
- Nơi khác của scan không còn tên host/IP.
- Username bị ẩn trong CI console/JUnit HTML.
- Các scans đã publish từ hôm qua được cập nhật.

**Obfuscation thuộc tính không phải global redaction**. Nếu yêu cầu bảo vệ toàn diện cao hơn mức plugin cung cấp, không publish scan hoặc dùng server/capture policy hạn chế hơn.

## 13. Không đưa secrets vào custom Build Scan data

Build Scan hỗ trợ tags, links và custom values để phân tích build theo environment/CI job. Chỉ thêm thông tin đã được xác nhận là không nhạy cảm.

**Ví dụ dữ liệu phù hợp:** Loại job **verify**, Gradle version, public build type, category **jdk17** nếu policy cho phép.

**Không phù hợp:**

- CI token hoặc signing private key.
- Raw environment variables.
- Basic Authorization header.
- Full URL chứa userinfo/query token.
- User/customer email lấy từ production fixture.
- Database connection string.
- Nội dung HTTP request/response chưa sanitize.
- Số điện thoại, tên người hoặc internal hostname không cần thiết.

Không dùng:

~~~groovy
// ANTI-PATTERN: minh họa, tuyệt đối không áp dụng thật.
develocity {
    buildScan {
        value 'deploy-token',
                System.getenv('DEPLOY_TOKEN')
    }
}
~~~

Kể cả khi Team/CI cho phép private scans, không biến chúng thành kho secrets. Build Scan có thể có quyền truy cập rộng hơn so với secret manager.

## 14. Lab Java 17 — an toàn ngay từ nguồn

Ta xây một Java 17 Gradle project đơn giản, không cần secret thật. Mục tiêu:

- Một hàm nhận các thông tin **giả lập** rồi chỉ trả summary đã redact.
- Một Java Main in duy nhất summary công khai.
- JUnit 5 tests xác minh hàm **không đưa input nhạy cảm vào output**.
- Gradle Test task không in stdout/stderr vào console hoặc JUnit XML.
- Giữ JUnit XML để CI đọc kết quả, nhưng nhắc rằng HTML/failure messages vẫn cần kiểm tra.
- Một Java 17 tool nhỏ quét các reports/fixtures bằng synthetic canary mà **không in nội dung match**.
- Một CI workflow chỉ upload reports sau khi bước audit thành công.

**Cây thư mục:**

~~~text
gradle-report-privacy-lab/
├── settings.gradle
├── build.gradle
├── gradlew
├── gradlew.bat
├── gradle/wrapper/
│   ├── gradle-wrapper.jar
│   └── gradle-wrapper.properties
├── src/
│   ├── main/java/org/example/safety/ReportSummary.java
│   └── test/java/org/example/safety/ReportSummaryTest.java
├── tools/
│   └── src/main/java/org/example/audit/ArtifactAudit.java
├── audit-fixtures/
│   ├── clean/report.xml
│   └── leaky/report.xml
└── .github/workflows/report-hygiene.yml
~~~

Cần JDK 17 và Gradle Wrapper tương thích. Nếu chưa có wrapper, tạo từ Gradle installation đã được tổ chức tin cậy bằng **gradle wrapper**, xác minh Wrapper JAR/distribution URL/SHA-256 theo chính sách rồi commit các file wrapper. Không chạy wrapper của repository lạ trước khi xem xét trust boundary.

### 14.1. settings.gradle

~~~groovy
rootProject.name = 'gradle-report-privacy-lab'
~~~

Lab **không tự bật Build Scan**. Đây là lựa chọn có chủ ý: ví dụ bảo mật đầu tiên phải chạy local mà không tự gửi metadata ra dịch vụ bên ngoài. Chỉ áp dụng cấu hình Develocity ở mục 11 sau khi có server/approval thực.

### 14.2. build.gradle

~~~groovy
plugins {
    id 'application'
}

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

application {
    mainClass = 'org.example.safety.ReportSummary'
}

dependencies {
    testImplementation 'org.junit.jupiter:junit-jupiter:5.11.4'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher:1.11.4'
}

tasks.withType(JavaCompile).configureEach {
    options.encoding = 'UTF-8'
    options.release.set(17)
}

tasks.withType(Test).configureEach {
    useJUnitPlatform()

    testLogging {
        events 'failed', 'skipped'
        showStandardStreams = false
        exceptionFormat =
                org.gradle.api.tasks.testing.logging
                    .TestExceptionFormat.SHORT
    }

    reports {
        junitXml {
            required = true
            includeSystemOutLog = false
            includeSystemErrLog = false
        }
        html.required = true
    }
}
~~~

**Giải thích chi tiết:**

- **application** thêm Java plugin và task **run**.
- Java toolchain và **options.release** cố định target 17.
- JUnit Jupiter/Launcher nằm trên test classpath, không phải production runtimeClasspath.
- **useJUnitPlatform()** được cấu hình cho Test tasks.
- **showStandardStreams=false** giảm console output do test JVM.
- **includeSystemOutLog=false/includeSystemErrLog=false** ngăn XML lưu stdout/stderr.
- **html.required=true** giữ HTML để chẩn đoán; HTML không tự được đảm bảo sạch. Lab an toàn vì tests không in sensitive inputs; trước khi upload HTML từ ứng dụng thật phải audit.
- **exceptionFormat=SHORT** giảm thông tin stack traces ở console thông thường, nhưng không sửa exception messages.
- Không thêm task in environment variables, không có secrets trong build script và không bật --scan.

### 14.3. ReportSummary.java

Tạo **src/main/java/org/example/safety/ReportSummary.java**:

~~~java
package org.example.safety;

import java.util.Objects;

public final class ReportSummary {
    private ReportSummary() {
    }

    public static String safeSummary(
            String principal,
            String credential,
            int processed) {

        Objects.requireNonNull(principal);
        Objects.requireNonNull(credential);

        if (processed < 0) {
            throw new IllegalArgumentException(
                    "processed must be non-negative");
        }

        return "STATUS=OK;processed=" + processed
                + ";principal=[REDACTED]"
                + ";credential=[REDACTED]";
    }

    public static void main(String[] args) {
        String result = safeSummary(
                "person@example.invalid",
                "TRAINING_CANARY_NOT_A_SECRET",
                3);

        System.out.println(result);
    }
}
~~~

**Stdout chính xác của Java Main:**

~~~text
STATUS=OK;processed=3;principal=[REDACTED];credential=[REDACTED]
~~~

Không có secret thật trong mã. Cả email và credential đều là synthetic test data. **Hàm safeSummary không trả lại hai giá trị đó**, chỉ xuất trạng thái/counter và marker cố định.

Đối với production, không nhất thiết phải truyền token vào hàm summary: kiến trúc tốt hơn là tách hoàn toàn authentication/secret-handling khỏi chức năng logging. Lab cố tình nhận giá trị để học cách ngăn tiết lộ.

### 14.4. ReportSummaryTest.java

Tạo **src/test/java/org/example/safety/ReportSummaryTest.java**:

~~~java
package org.example.safety;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertThrows;

class ReportSummaryTest {
    @Test
    void masksSensitiveInputs() {
        String actual = ReportSummary.safeSummary(
                "person@example.invalid",
                "TRAINING_CANARY_NOT_A_SECRET",
                3);

        assertEquals(
                "STATUS=OK;processed=3;principal=[REDACTED]"
                + ";credential=[REDACTED]",
                actual);

        assertFalse(
                actual.contains("person@example.invalid"));

        assertFalse(
                actual.contains("TRAINING_CANARY_NOT_A_SECRET"));
    }

    @Test
    void rejectsNegativeCountWithoutEchoingInputs() {
        assertThrows(
                IllegalArgumentException.class,
                () -> ReportSummary.safeSummary(
                        "person@example.invalid",
                        "TRAINING_CANARY_NOT_A_SECRET",
                        -1));
    }
}
~~~

Hai JUnit test methods được thiết kế để pass. Không dùng **System.out.println** trong test và không thêm messages chứa input values vào assertions.

**Nếu lỗi phát sinh:** assertion về expected string cố định có thể hiển thị string summary an toàn. Exception **processed must be non-negative** không chứa principal/credential. Đây là một ví dụ về thiết kế exception message không tiết lộ dữ liệu.

### 14.5. Chạy lab bằng Gradle

Linux/macOS:

~~~bash
./gradlew clean test --console=plain
./gradlew -q run
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat clean test --console=plain
.\gradlew.bat -q run
~~~

Stdout chương trình chính:

~~~text
STATUS=OK;processed=3;principal=[REDACTED];credential=[REDACTED]
~~~

Gradle có thể thêm task status trong lệnh test; không có stdout chính xác cố định cho toàn bộ build log.

### 14.6. Biên dịch/chạy Java 17 không cần Gradle

Linux/macOS từ root:

~~~bash
mkdir -p out
javac --release 17 -encoding UTF-8 \
  -d out \
  src/main/java/org/example/safety/ReportSummary.java
java -cp out org.example.safety.ReportSummary
~~~

Windows PowerShell:

~~~powershell
New-Item -ItemType Directory -Force out | Out-Null

javac --release 17 -encoding UTF-8 -d out src\main\java\org\example\safety\ReportSummary.java

java -cp out org.example.safety.ReportSummary
~~~

Stdout giống hệt:

~~~text
STATUS=OK;processed=3;principal=[REDACTED];credential=[REDACTED]
~~~

Lệnh javac/java kiểm tra Java source và stdout, **không kiểm chứng Gradle logging, JUnit XML hay Build Scan settings**. Các phần đó cần quan sát Gradle tasks/reports thật.

## 15. Java 17 ArtifactAudit: phát hiện canary mà không in secret

Một lỗi phổ biến khi quét log là dùng grep in nguyên dòng match rồi lại đưa giá trị nhạy cảm vào log CI. Công cụ dưới đây chỉ in **PASS/FAIL và số file**, không in content hoặc matching lines.

Tạo **tools/src/main/java/org/example/audit/ArtifactAudit.java**:

~~~java
package org.example.audit;

import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.Locale;
import java.util.stream.Stream;

public final class ArtifactAudit {
    private ArtifactAudit() {
    }

    public static void main(String[] args) throws Exception {
        if (args.length != 2) {
            throw new IllegalArgumentException(
                    "Usage: ArtifactAudit <directory> <synthetic-canary>");
        }

        Path directory = Path.of(args[0]);
        String canary = args[1];

        if (!Files.isDirectory(directory) ||
                canary.isBlank()) {
            throw new IllegalArgumentException(
                    "A report directory and canary are required");
        }

        List<Path> files;

        try (Stream<Path> stream = Files.walk(directory)) {
            files = stream
                    .filter(Files::isRegularFile)
                    .filter(path -> {
                        String name = path.getFileName()
                                .toString().toLowerCase(Locale.ROOT);

                        return name.endsWith(".xml")
                                || name.endsWith(".html")
                                || name.endsWith(".txt")
                                || name.endsWith(".log")
                                || name.endsWith(".json");
                    })
                    .sorted()
                    .toList();
        }

        if (files.isEmpty()) {
            throw new IllegalStateException(
                    "No eligible report files found");
        }

        int matchedFiles = 0;

        for (Path file : files) {
            String content = Files.readString(
                    file, StandardCharsets.UTF_8);

            if (content.contains(canary)) {
                matchedFiles++;
            }
        }

        if (matchedFiles == 0) {
            System.out.printf(
                    Locale.ROOT,
                    "AUDIT=PASS;FILES=%d%n", files.size());
        } else {
            System.out.printf(
                    Locale.ROOT,
                    "AUDIT=FAIL;FILES=%d;MATCHED_FILES=%d%n",
                    files.size(), matchedFiles);
            System.exit(2);
        }
    }
}
~~~

Ưu điểm:

- **Không in nội dung match**, kể cả trong trường hợp lỗi.
- Không in tên file, vì filename cũng có thể chứa private identifier.
- Scan các định dạng text thường gặp của report (XML/HTML/TXT/LOG/JSON).
- **Exit code 2** khi có canary; CI có thể fail.
- **Fail closed** khi directory không tồn tại, canary trống hoặc không có file.
- Sử dụng Java 17 **Stream.toList()**, Files.readString, UTF-8 và try-with-resources.

**Giới hạn:** Đây chỉ là công cụ đào tạo cho một *synthetic canary*. Nó không phát hiện mọi token/PII, nhiều kiểu encoding, data binary, compressed archives hoặc hình ảnh. Một security scanner thực tế cần policy/multi-pattern detection được quản lý và không nên ghi nội dung nhạy cảm khi báo finding.

### 15.1. Hai fixture minh họa

Tạo **audit-fixtures/clean/report.xml**:

~~~xml
<testsuite tests="1" failures="0">
    <testcase name="safeTest"/>
</testsuite>
~~~

Tạo **audit-fixtures/leaky/report.xml**:

~~~xml
<testsuite tests="1" failures="0">
    <testcase name="unsafeTest"/>
    <system-out>TRAINING_CANARY_NOT_A_SECRET</system-out>
</testsuite>
~~~

Nội dung thứ hai **cố tình rò một canary vô hại** để kiểm tra scanner. Không dùng secret thật. Hai fixtures là file đào tạo độc lập, không phải reports của Gradle Test task và không được upload cùng production artifacts.

### 15.2. Biên dịch và chạy scanner

Linux/macOS:

~~~bash
mkdir -p out
javac --release 17 -encoding UTF-8 \
  -d out \
  tools/src/main/java/org/example/audit/ArtifactAudit.java

java -cp out org.example.audit.ArtifactAudit \
  audit-fixtures/clean TRAINING_CANARY_NOT_A_SECRET
~~~

Stdout chính xác:

~~~text
AUDIT=PASS;FILES=1
~~~

Chạy với fixture có canary:

~~~bash
java -cp out org.example.audit.ArtifactAudit \
  audit-fixtures/leaky TRAINING_CANARY_NOT_A_SECRET
~~~

Stdout chính xác trước khi process trả exit code 2:

~~~text
AUDIT=FAIL;FILES=1;MATCHED_FILES=1
~~~

Windows PowerShell:

~~~powershell
New-Item -ItemType Directory -Force out | Out-Null

javac --release 17 -encoding UTF-8 -d out tools\src\main\java\org\example\audit\ArtifactAudit.java

java -cp out org.example.audit.ArtifactAudit audit-fixtures\clean TRAINING_CANARY_NOT_A_SECRET
~~~

**Chỉ dùng synthetic canary làm CLI argument.** Không đưa credential thật vào process argument để quét: secret có thể nằm trong shell history/process list. Công cụ production nên nhận detection rules từ file/secret-safe channel mà bản thân nó không tiết lộ.

### 15.3. Scan kết quả test Gradle

Sau khi **./gradlew test** thành công:

~~~bash
java -cp out org.example.audit.ArtifactAudit \
  build/test-results/test TRAINING_CANARY_NOT_A_SECRET

java -cp out org.example.audit.ArtifactAudit \
  build/reports/tests/test TRAINING_CANARY_NOT_A_SECRET
~~~

Số file có thể thay theo Gradle version, nên không hứa stdout FILES cố định. Trong lab, các reports được thiết kế không chứa canary vì tests không log giá trị, assertion/exception text an toàn và JUnit XML stdout/stderr bị tắt.

**Quan trọng:** Scanner kiểm tra canary trong text reports; nó không phải bằng chứng không có bất cứ dữ liệu riêng tư nào. Test thất bại với raw exception messages từ một module khác vẫn có thể làm rò secrets mà canary scanner không phát hiện.

## 16. Vì sao giảm console + XML vẫn chưa đủ?

Phân tích một test lỗi:

~~~java
throw new IllegalStateException(
        "Authentication failed for user=" + userEmail
        + ";token=" + accessToken);
~~~

Đây là **anti-pattern minh họa**, không áp dụng vào lab. Dù **showStandardStreams=false** và **includeSystemOutLog=false**, exception message có thể đi vào **JUnit XML failure element**, HTML, CI test summary hoặc Build Scan failure records.

Cách tốt hơn:

~~~java
throw new IllegalStateException(
        "Authentication failed: CREDENTIAL_REJECTED");
~~~

Nhà vận hành vẫn biết loại lỗi mà không cần biết email hoặc token. Nếu muốn correlation để điều tra, sinh mã định danh đã được policy cho phép và không chứa PII/secret; dùng mã ấy tra cứu trong một hệ thống có quyền truy cập riêng.

### 16.1. Assertion failure

Không build một assertion message bằng toàn bộ HTTP response hoặc object.toString() của đối tượng chứa token. Thay bằng:

- HTTP status code.
- Error category đã chuẩn hóa.
- Tên field không nhạy cảm.
- Số item hoặc booleans.
- Request ID được phép chia sẻ.
- Kết quả đã sanitize.

### 16.2. Stack trace

Ngay cả khi exception message an toàn, file paths, class names, SQL error context hoặc nested cause có thể nhạy cảm. **exceptionFormat=SHORT** chỉ kiểm soát một dạng hiển thị. Với production exceptions, xây exception hierarchy và safe error envelopes để bảo vệ ở nguồn.

### 16.3. Test fixture

Dùng fake user records, synthetic access tokens và endpoint .invalid. Nếu phải tái hiện lỗi từ production, tạo **sanitized reproduction** qua quy trình được phép; không copy database rows thô vào Git/CI.

## 17. Gradle daemon logs, caches và nơi khác có bản sao

Nội dung một lần build có thể được giữ ở ngoài thư mục **build/reports/**:

- Gradle Daemon log dưới **GRADLE_USER_HOME/daemon/**.
- CI job logs/console capture.
- IDE run/debug logs.
- Gradle local configuration cache dưới **.gradle/configuration-cache/**.
- Task output build cache khi task outputs chứa dữ liệu.
- External report aggregation services.
- Notification/webhook/email/chat của CI.
- Build Scan server và scan link metadata.

**Không hiểu nhầm**:

- **Task output build cache** chứa outputs của cacheable tasks, có thể gây rủi ro nếu task đưa secret vào output.
- **Dependency cache** chứa Maven artifacts/metadata, không phải một nơi an toàn để đặt private user files.
- **Configuration cache** lưu configuration state; có cơ chế bảo vệ riêng nhưng không nên cố tình serialise secrets vào task model.
- **Daemon** là tiến trình chạy lâu, có thể giữ state/log qua nhiều builds. Không tái sử dụng chung user home/daemon giữa jobs không cùng trust boundary.

Tắt Build Scan **không xóa nội dung đã có trong các caches/log files khác**. Trong incident response cần nhận diện từng bản sao.

## 18. CI: kiểm tra trước khi upload report

Một GitHub Actions workflow cho **lab**, không dùng secrets thật:

Tạo **.github/workflows/report-hygiene.yml**:

~~~yaml
name: Gradle report hygiene

on:
  push:
  pull_request:

permissions:
  contents: read

jobs:
  verify:
    runs-on: ubuntu-latest

    steps:
      - name: Checkout
        uses: actions/checkout@v4

      - name: Java 17
        uses: actions/setup-java@v4
        with:
          distribution: temurin
          java-version: '17'

      - name: Gradle environment
        uses: gradle/actions/setup-gradle@v6

      - name: Verify tests without Build Scan
        run: |
          ./gradlew --no-daemon test --console=plain

      - name: Compile report auditor
        shell: bash
        run: |
          mkdir -p out
          javac --release 17 -encoding UTF-8 \
            -d out \
            tools/src/main/java/org/example/audit/ArtifactAudit.java

      - name: Audit JUnit XML
        run: |
          java -cp out org.example.audit.ArtifactAudit \
            build/test-results/test \
            TRAINING_CANARY_NOT_A_SECRET

      - name: Audit HTML report
        run: |
          java -cp out org.example.audit.ArtifactAudit \
            build/reports/tests/test \
            TRAINING_CANARY_NOT_A_SECRET

      - name: Upload reviewed JUnit XML
        if: success()
        uses: actions/upload-artifact@v4
        with:
          name: safe-test-summary
          path: build/test-results/test/TEST-*.xml
          if-no-files-found: error
          retention-days: 7
~~~

**Điểm bảo mật có chủ đích:**

- Không tự chạy **--scan** hay dùng **--debug**.
- Không inject signing/repository tokens vào untrusted pull requests.
- **permissions: contents: read** giới hạn quyền GitHub token của job.
- Không bật test **showStandardStreams**.
- Auditor chạy trên JUnit XML và HTML bằng synthetic canary.
- Chỉ upload JUnit XML khi tests + audit thành công.
- Không upload HTML/binary reports hoặc toàn workspace.
- **retention-days: 7** là mức minh họa; phải theo retention policy của tổ chức.
- Các tests fail vẫn làm CI đỏ; không **continue-on-error** hoặc **|| true**.

**Giới hạn:** Nếu tests fail, bước scan/archival mặc định không chạy; điều đó giảm nguy cơ upload reports chưa review nhưng cũng không có diagnostics artifact trong CI. Với production, thiết kế một kênh **quarantine/limited-access** để lưu diagnostic reports sau khi đã được scanner/quy trình redaction phù hợp kiểm tra, kể cả khi tests fail. Không “sửa” bằng cách upload tất cả failure logs công khai.

### 18.1. GitHub secret masking không thay thế thiết kế an toàn

CI providers có thể mask những secrets đã khai báo, nhưng masking thường không đảm bảo với:

- Giá trị bị biến đổi (hash, base64, URL encoding).
- Đoạn con của một token.
- Structured JSON hoặc multiline output.
- Dynamic secrets chưa được đăng ký với runner.
- Reports/artifacts không đi qua console masker.
- Dữ liệu được xuất bản trước khi masking được áp dụng.

Hãy ngăn code ghi secrets, sau đó mới dùng masking như lớp phòng vệ bổ sung. Không dùng **echo** để kiểm tra secret masking hoạt động trên secret thật.

## 19. Kiểm tra bằng cách tạo canary giả lập

Một kỹ thuật kiểm chứng không cần secrets thật:

1. Dùng canary dễ nhận ra nhưng **không có quyền truy cập** vào bất kỳ hệ thống nào.
2. Cho canary đi vào input của một hàm xử lý/report **an toàn**.
3. Chạy unit tests và Gradle build.
4. Quét các kênh được phép kiểm tra: JUnit XML, HTML, CI log, custom reports.
5. Đảm bảo scanner **không in giá trị** nếu phát hiện.
6. Sửa lỗi ở nguồn nếu canary xuất hiện.
7. Lặp lại ở các plugins và custom tasks có thể log.
8. Không công bố scan cho tới khi đã kiểm tra capture policy và server access.

Canary scanner chỉ là một regression check cho **đường đi đã chọn**. Nó không phát hiện mọi dạng secrets/PII; để quản trị thực tế nên dùng approved secret scanners, DLP policies, code reviews và kiểm tra permissions.

### 19.1. Tại sao không grep ra cả matching line?

Một lệnh như:

~~~bash
grep -R "TRAINING_CANARY_NOT_A_SECRET" build/reports
~~~

trong đào tạo với canary giả không nguy hiểm, nhưng tương tự với **real secret pattern** có thể làm lộ thêm dữ liệu trên CI console. Scanner của lab in **số lượng file match**, không in dòng chứa dữ liệu.

### 19.2. Không cho scanner tạo bản sao nhạy cảm khác

Tránh scan output có:
- Full matching line.
- Raw binary dumps.
- Raw JSON payloads.
- Stack traces chứa secret.
- File paths chứa customer name khi không cần.

Một finding an toàn có thể có category, severity, count và internal incident ID; chi tiết nhạy cảm chỉ được lưu vào kho quarantine có quyền hạn.

## 20. Chính sách cho Test task trong nhiều modules

Trong multi-project build, mỗi module có thể dùng JUnit/TestNG và Test task riêng. Nếu chỉ cấu hình root task **:test**, các modules **:api:test**, **:cli:test** hoặc **integrationTest** có thể giữ default stdout/stderr XML capture.

Nên đóng gói policy thành convention plugin hoặc áp dụng có chủ đích:

~~~groovy
// Đoạn minh họa bên trong một Java convention plugin.
tasks.withType(Test).configureEach {
    testLogging {
        events 'failed', 'skipped'
        showStandardStreams = false
    }
    reports.junitXml.includeSystemOutLog = false
    reports.junitXml.includeSystemErrLog = false
}
~~~

**Điểm chính:** Dùng **configureEach** để áp dụng cho cả Test tasks được tạo sau. Plugin policy nên do modules opt-in hoặc tổ chức enforce qua cơ chế đã được duyệt. Không dùng một block root **subprojects {}** vô tội vạ mà không hiểu task graph, isolated projects và plugin scope.

### 20.1. Thực thi Test tasks khác

- Unit Test, IntegrationTest, ContractTest có thể có source/output khác nhau.
- Report plugins bên thứ ba có thể tạo XML/HTML riêng với cấu hình riêng.
- Test retry plugin có thể ghi failed attempts; những lỗi ban đầu vẫn có thể chứa dữ liệu nhạy cảm.
- Test report aggregation tạo thêm nơi lưu/công bố.
- JUnit parameterized display names phải được sanitize dù TestLogging không hiển thị stdout.

### 20.2. Không tắt toàn bộ test diagnostics

Chặn hoàn toàn failures để “không có rò rỉ” dễ làm lỗi bị bỏ qua. Giải pháp đúng là:
- Safe exception and assertion messages.
- Limited detail trong public CI.
- Quarantine diagnostics chi tiết có access control.
- Build red status khi có test failure.
- Structured failure categories thay vì dump request/response.

## 21. Dependency/publishing failures cũng có thể chứa data

Mặc dù bài tập tập trung logs/test reports/Build Scans, Gradle dependency và publishing tasks là một nguồn rò rỉ phổ biến:

- HTTP 401/403 response body có thể echo request context.
- Repository URL có chứa userinfo hoặc query token.
- Proxy/HTTP debug output có thể chứa headers tùy thư viện/plugin.
- Publishing exception chứa destination URL, artifact coordinate và stack trace.
- Task description hoặc custom logger in credentials khi debug.
- Gradle build scan ghi project/task/plugin/dependency metadata.

Khuyến nghị:

1. Không nhúng credentials trong repository URLs.
2. Dùng **credentials(PasswordCredentials)**, environment/secret providers hoặc giải pháp signing đã duyệt.
3. Không bật HTTP wire logging trong jobs có token nếu chưa có redaction.
4. Tách trusted release jobs khỏi PR verification.
5. Chỉ báo status code/category và request ID được policy cho phép.
6. Không tự động in nguyên response body khi authentication fail.
7. Review plugin versions, Wrapper integrity và init scripts vì chúng chạy với quyền của người dùng build.

## 22. Quản trị Build Scan và artifact access

### 22.1. Access control

- Chỉ nhân viên/nhóm có nhu cầu mới được xem scans có project details nhạy cảm.
- Dùng identity provider/SSO theo chính sách.
- Không coi URL là bí mật duy nhất bảo vệ dữ liệu.
- Không gửi scan links vào các ticket hoặc public forums chưa phân loại dữ liệu.
- Cấu hình quyền xem, retention và delete policy theo server.
- Có audit trail khi access/exports được phép.

### 22.2. Data retention

Nếu reports chỉ cần cho CI debugging 7 ngày, không mặc định giữ 365 ngày. Tuy nhiên retention tối thiểu có thể bị ràng buộc bởi compliance/audit; chọn theo chính sách, không xóa bằng cảm tính.

**Retention không thay thế source prevention**: một log chứa secret trong vòng vài giây vẫn có thể bị truy cập trước khi hết hạn.

### 22.3. Không mở quyền công khai để sửa lỗi permissions

Khi Build Scan/CI artifact không mở được, không chuyển nó sang public chỉ để gửi link cho một người ngoài. Dùng cơ chế request access hoặc bản tóm tắt đã sanitize.

## 23. Phân biệt masking, redaction và obfuscation

| Kỹ thuật | Ví dụ | Lợi ích | Giới hạn |
| --- | --- | --- | --- |
| **Không tạo dữ liệu** | Log chỉ STATUS=OK thay vì toàn request | Ít rủi ro nhất | Cần thiết kế từ nguồn |
| **Redaction** | Credential=[REDACTED] | Vẫn giữ nghĩa của field | Cần bao phủ mọi path |
| **Masking** | CI thay một token đã biết bằng dấu che | Lớp dự phòng cho console | Có thể bỏ sót biến thể, artifacts |
| **Obfuscation** | Scan username → hidden-user | Giảm định danh trong field | Không có nghĩa scan được làm sạch toàn bộ |
| **Truncation** | Chỉ in 30 ký tự đầu | Giảm lượng nội dung | Với tokens, chỉ một phần vẫn có thể nhạy cảm |
| **Hash** | Băm user ID | Giữ khả năng đối chiếu | Dễ bị brute force/reidentification nếu input space nhỏ |
| **Access control** | Scan chỉ cho project team | Giảm người xem | Không xóa dữ liệu khỏi kho |
| **Retention** | Reports xóa sau policy window | Giảm thời gian phơi lộ | Không thu hồi bản đã bị sao chép |

**Không tự động tin tưởng “hash”** là ẩn danh nếu email/phone có không gian giá trị nhỏ. Nếu cần correlation, cân nhắc keyed HMAC hoặc opaque correlation ID do hệ thống sinh theo policy bảo mật. Không in signing/HMAC key vào logs.

## 24. Kiểm tra lỗi và tình huống thường gặp

| Triệu chứng | Hiểu nhầm/nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Console không thấy stdout nhưng XML vẫn có | showStandardStreams chỉ là console | Tắt XML includeSystemOutLog/ErrLog |
| Đã tắt XML stdout nhưng failure có token | Assertion/exception message chứa token | Sửa exception/assertion ở nguồn |
| HTML report có input nhạy cảm | HTML là kênh khác XML | Tránh log raw data, audit HTML |
| Build Scan vẫn có lỗi test | testLogging capture false không loại test failures | Safe failure messages hoặc không publish scan |
| Username vẫn lộ nơi khác | Obfuscation chỉ tác động field cụ thể | Kiểm tra toàn bộ scan metadata |
| Build Scan link được đưa vào public issue | Chia sẻ sai trust boundary | Hạn chế access, thu hồi/xóa theo policy |
| --quiet rồi tưởng không còn log | Chỉ giảm console verbosity | Audit report/artifact/scan khác |
| --debug để lộ token | Plugin/library debug output | Tắt debug, rotate token nếu lộ |
| Credential in URL | Embedded userinfo/query token | Typed credentials, secret store |
| Email lộ qua test name | Dynamic display name chứa real user | Đặt tên theo hành vi, synthetic data |
| Test output bị upload trong ZIP | Upload toàn workspace | Allowlist artifacts cần thiết |
| Canary scan PASS nhưng vẫn có secret | Scanner chỉ biết một marker | Scanner nhiều luật/DLP và review |
| CI masked console nhưng artifact lộ | Masker không chạy trên ZIP/XML | Kiểm tra riêng từng artifact |
| Build cache có secret output | Task đã cache dữ liệu nhạy cảm | Không cache secret-dependent task |
| Configuration cache chứa value nhạy cảm | Secret đọc sớm ở configuration | Providers/typed credentials, protect cache dir |
| CI job fail không có report | Upload bị hạn chế sau security check | Kênh quarantine có quyền hạn |
| Output bị in trong stacktrace | Exception chứa raw payload | Safe exception envelope |
| Plugin cộng đồng tự log header | Third-party logging | Review/update/replace plugin |
| Token đã xuất hiện nhưng log bị xóa | Token vẫn có thể đã bị sao chép | Revoke/rotate trước, incident process |
| Không thể xóa scan ngay | Server retention/delete policy | Admin/security team, hạn chế quyền trong lúc xử lý |

## 25. Incident response khi phát hiện secret trong log

Nếu một credential thực đã xuất hiện trong CI console, JUnit report hoặc Build Scan:

1. **Dừng việc chia sẻ** link/report; hạn chế quyền truy cập nếu có thể.
2. **Phân loại dữ liệu**: token nào, quyền gì, môi trường nào, có PII hay không.
3. **Revoke/rotate secret ngay** theo policy; không đợi chỉ vì “link riêng tư”.
4. **Xác định nơi đã có bản sao**: CI log, artifacts, binary results, HTML, Build Scan, daemon logs, caches, chat/issues, backups.
5. **Liên hệ security/incident team** để xóa hoặc quarantine dữ liệu theo retention/compliance rules.
6. **Xem xét truy cập** (audit logs) và dấu hiệu lạm dụng credential.
7. **Sửa nguồn rò**: exception, test stdout, plugin logger, request dump, CI script, custom scan tags.
8. **Kiểm thử lại bằng synthetic canary**, không tái in secret thật để “xác minh”.
9. **Bổ sung regression gate** và cập nhật quy trình onboarding/review.
10. **Ghi lại lessons learned** bằng thông tin đã sanitize, không copy credential vào postmortem.

Chỉ xóa file report là **chưa đủ**: secret có thể tồn tại ở bản sao, logs do CI quản lý hoặc người khác đã tải trước đó. Rotation/revocation thường là biện pháp bắt buộc.

### 25.1. Khi dữ liệu là PII nhưng không phải credential

Không phải lúc nào cũng có “token để rotate”. Cần thực hiện quy trình privacy incident theo chính sách tổ chức: hạn chế truy cập, điều tra phạm vi, xóa/quarantine bản sao, đánh giá nghĩa vụ thông báo nếu có, và sửa code để tránh tạo dữ liệu đó nữa.

### 25.2. Không tự xóa bằng chứng trái quy định

Sự cố có thể cần bảo toàn evidence theo quy trình. Đừng xóa logs tùy tiện trên production/CI trước khi security team hướng dẫn. Việc hạn chế access và rotation có thể làm ngay theo runbook, còn retention/legal hold phải tuân thủ quy định.

## 26. Checklist code review dành cho Gradle build logic

Khi review build.gradle, settings.gradle, convention plugins, buildSrc hoặc init scripts, hỏi:

- Có **println/logger.lifecycle/info/debug** ghép token, password, cookie hoặc PII không?
- Có **System.getenv()** rồi in tên/value hoặc dump toàn env không?
- Có truyền secret vào **-P/-D/command line** không?
- Có repository URL chứa username/password không?
- Có Gradle properties chứa secret được commit không?
- Có task name, output directory hoặc build scan custom value mang dữ liệu khách hàng không?
- Có HTTP request/response dumping không?
- Test assertions/failures có stringify raw actual/expected sensitive objects không?
- Dynamic test display names có chứa PII không?
- **showStandardStreams** có bị bật trong CI không?
- **includeSystemOutLog/includeSystemErrLog** có đúng policy không?
- HTML/binary report outputs có được audit/giới hạn upload không?
- Có Build Scan capture/obfuscation/access policy không?
- Có tự publish scan khi chưa có consent/approval không?
- Có upload toàn **build/**, **.gradle/**, **~/.gradle/** hoặc environment dumps không?
- Có tách trusted release credentials khỏi untrusted PR jobs không?
- Cache/configuration cache/daemon có được bảo vệ giữa trust boundaries không?
- Có synthetic canary regression test và cách báo finding không tiết lộ nội dung không?
- Có incident response owner, retention và revoke policy không?

## 27. Bài tập thực hành

### Bài 1 — Bản đồ dữ liệu

Vẽ đường đi của một biến environment **PUBLISH_TOKEN** (không dùng giá trị thật) qua build.gradle, HTTP client, console, JUnit XML, HTML, CI artifact và Build Scan. Kênh nào là mặc định, kênh nào cần config?

### Bài 2 — Console và XML

Chạy lab test, mở **build/test-results/test/** và **build/reports/tests/test/**. Giải thích vì sao việc tắt **showStandardStreams** khác với **includeSystemOutLog=false**.

### Bài 3 — Assertion message

Trong nhánh thử nghiệm, viết một assertion thất bại chỉ với synthetic canary (không phải secret). Quan sát failure text ở XML/HTML. Sau đó đổi assertion sang safe status và hoàn tác lỗi.

### Bài 4 — Test name

Tạo JUnit parameterized test có display name mang một fake email. Kiểm tra tên test có đi vào report không; viết lại thành tên theo behavior.

### Bài 5 — ArtifactAudit

Chạy scanner trên **audit-fixtures/clean** và **audit-fixtures/leaky**; xác nhận PASS và FAIL mà không in canary trong stdout scanner.

### Bài 6 — Scanner limitation

Thử tạo một fixture dùng base64 encoding của synthetic canary. Vì sao simple substring matcher không thấy? Phác thảo cách phát hiện có kiểm soát mà không in raw data.

### Bài 7 — Credentials

Chuyển một ví dụ repository chứa userinfo URL giả sang **credentials(PasswordCredentials)**. Đặt tên properties và giải thích vì sao vẫn phải review plugin logging.

### Bài 8 — Configuration cache

Tìm một chỗ build script resolve env var sớm và lưu String secret trong task model (chỉ dùng fake canary). Sửa để dùng Provider/typed credential API. Nêu rủi ro với serialized state.

### Bài 9 — Scan capture

Trên sandbox được phép xuất bản scan, bật Develocity capture false và so sánh những categories còn lại. Vì sao test failure metadata vẫn có thể xuất hiện?

### Bài 10 — Obfuscation

Đặt scan username/hostname/IP obfuscation theo tài liệu plugin. Kiểm tra một custom value có email giả vẫn không tự được xóa.

### Bài 11 — CI artifact allowlist

Đổi workflow từ upload toàn build/ thành chỉ upload XML khi audit PASS. Giải thích tác động tới HTML/binary reports và retention.

### Bài 12 — Security incident

Giả định một token giả có quyền deploy được in trong CI log. Viết thứ tự xử lý: revoke, containment, audit copies, rotation, regression test; vì sao xóa log chưa đủ?

### Bài 13 — Build Scan link sharing

Một người đề nghị công khai scan để dễ debug. Thiết kế cách chia sẻ thông tin đã sanitize thay vì mở quyền scan cho mọi người.

### Bài 14 — Third-party plugin

Review một plugin tạo report JSON/HTML riêng. Vì sao chỉ cấu hình Gradle JUnit XML chưa đủ? Những fields cần kiểm toán?

### Bài 15 — DLP gate

Lập policy scanner nhiều loại secret/PII, phân loại severity, không in matching lines, có false-positive review và fail-closed artifact upload.

## 28. Câu hỏi tự kiểm tra

1. Vì sao secret có thể có nhiều bản sao sau một lần test?
2. showStandardStreams=false có làm JUnit XML sạch hoàn toàn không?
3. includeSystemOutLog mặc định là true hay false?
4. includeSystemErrLog mặc định là true hay false?
5. Những fields nào của JUnit XML còn có thể tiết lộ dữ liệu sau khi tắt stdout?
6. Vì sao HTML test report cần kiểm tra riêng?
7. Build Scan có thể chứa những nhóm thông tin nào?
8. buildLogging=false của Develocity có chặn JUnit XML không?
9. testLogging=false của Develocity có loại test failures không?
10. Obfuscate username có tự che email trong exception không?
11. Vì sao không đưa token vào custom Build Scan value?
12. --quiet khác security redaction như thế nào?
13. Vì sao --debug tăng rủi ro rò?
14. Vì sao credential trong URL nguy hiểm?
15. Gradle typed credentials API giúp gì?
16. Có thể commit gradle.properties chứa password không?
17. Vì sao một CI environment variable vẫn có thể bị lộ?
18. Vì sao không đưa real token vào CLI args?
19. Vì sao assertEquals(rawSecret, rawSecret) có thể không an toàn khi thất bại?
20. Vì sao tên dynamic test có thể nhạy cảm?
21. ArtifactAudit của lab có tự phát hiện mọi secret không?
22. Vì sao ArtifactAudit không in matching lines?
23. Vì sao canary phải giả lập và không có quyền?
24. Nếu JUnit XML scanner FAIL thì có nên upload artifact công khai không?
25. Khi test fail, làm sao giữ diagnostics mà vẫn bảo mật?
26. Vì sao masking không bảo vệ ZIP artifacts?
27. Vì sao Build Scan link khó đoán không phải access control?
28. Configuration cache có thể lưu những state nào?
29. Vì sao cache output chứa credential nguy hiểm?
30. Khi secret đã lộ, bước quan trọng nhất nào không thể thay bằng xóa log?
31. Những người nào cần được tham gia incident response?
32. Vì sao Build Scan source code không được upload mặc định vẫn có thể rò?
33. Các build entry points nào chạy mã trước task bình thường?
34. Khi nào không nên dùng --scan?
35. Vì sao phòng ngừa ở nguồn mạnh hơn redaction downstream?

**Đáp án gợi ý:** (1) console/report/scan/CI đều có capture; (2) không; (3) true; (4) true; (5) failure/stack/name/class; (6) format khác; (7) environment/task/dependencies/tests/logs; (8) không; (9) không; (10) không; (11) scan không phải secret store; (12) chỉ giảm verbosity; (13) thêm diagnostic; (14) URL dễ lộ; (15) API quản trị/redaction; (16) không; (17) code có thể log; (18) history/process capture; (19) failure in raw values; (20) reports lưu tên; (21) không; (22) tránh secondary leak; (23) không làm lộ secret thật; (24) không; (25) quarantine/restricted channels; (26) console masker không sửa file; (27) cần quyền xem; (28) task graph/configuration model; (29) cache phân phối output; (30) revoke/rotate; (31) security/privacy/owners; (32) metadata/failures tiết lộ; (33) init/buildSrc/included builds/plugins; (34) chưa có policy/server approval; (35) giảm mọi bản sao.

## 29. Checklist đưa vào CI và đội phát triển

- [ ] Không dùng production credentials hoặc PII trong test fixtures.
- [ ] Chỉ log structured safe fields; không dump request/response object.
- [ ] Exception messages không chứa token, password, cookie hoặc personal identifiers.
- [ ] Assertions không đưa raw sensitive expected/actual values vào failure.
- [ ] Dynamic test names và report links không chứa PII.
- [ ] Gradle TestLogging giảm stdout/stderr console theo policy.
- [ ] JUnit XML includeSystemOutLog=false, includeSystemErrLog=false nếu không cần.
- [ ] Không giả XML settings cũng sanitize HTML/binary reports.
- [ ] Tất cả Test tasks, kể cả integration tests, tuân policy.
- [ ] Build Scan server/tenant và Terms of Use được duyệt.
- [ ] Develocity output capture/obfuscation đúng plugin version.
- [ ] Hiểu rõ test failures vẫn được thu khi tắt test output capture.
- [ ] Không thêm secrets vào Build Scan tags/custom values/links.
- [ ] Build Scan access control và retention được quản lý.
- [ ] CI không có --debug tùy tiện khi chứa secrets.
- [ ] Credentials ở secret store/typed APIs, không hardcode vào source.
- [ ] Tránh secrets trong CLI args hoặc repository URL.
- [ ] Gradle User Home và daemon logs được bảo vệ theo quyền.
- [ ] Không chia sẻ configuration cache/build cache qua trust boundary không phù hợp.
- [ ] Chỉ upload artifact allowlist sau khi đã kiểm tra.
- [ ] Artifact scanners không in matching lines hoặc secret values.
- [ ] Có synthetic canary regression tests và scanner policy mở rộng.
- [ ] Có kênh quarantine cho failure reports cần giữ để điều tra.
- [ ] Có CI retention phù hợp và log access auditing.
- [ ] Không gộp logs/artifacts vào public support ticket.
- [ ] Có procedure revoke/rotate nếu token lộ.
- [ ] Có privacy incident workflow riêng cho PII.
- [ ] Có security review cho third-party Gradle plugins.
- [ ] Không tự publish --scan trên untrusted code/fixtures chưa review.
- [ ] Kiểm chứng runtime Gradle/JUnit/Develocity version trước khi dựa vào một property.
- [ ] Mọi security policy được kiểm thử với báo cáo thực, không chỉ đọc build.gradle.

## 30. Tài liệu chính thức

- [Gradle — Securing the Build Tool](https://docs.gradle.org/current/userguide/securing_build_tool.html)
- [Gradle — Testing in Java & JVM Projects](https://docs.gradle.org/current/userguide/java_testing.html)
- [Gradle — Test Task DSL](https://docs.gradle.org/current/dsl/org.gradle.api.tasks.testing.Test.html)
- [Gradle — TestLogging DSL](https://docs.gradle.org/current/dsl/org.gradle.api.tasks.testing.logging.TestLogging.html)
- [Gradle — Build Scan Basics](https://docs.gradle.org/current/userguide/build_scans.html)
- [Gradle — Logging and Output](https://docs.gradle.org/current/userguide/logging.html)
- [Gradle — Build Environment Configuration](https://docs.gradle.org/current/userguide/build_environment.html)
- [Gradle — Supported Repository Protocols and Credentials](https://docs.gradle.org/current/userguide/supported_repository_protocols.html)
- [Gradle — Configuration Cache](https://docs.gradle.org/current/userguide/configuration_cache.html)
- [Gradle — Best Practices for Security](https://docs.gradle.org/current/userguide/best_practices_security.html)
- [Develocity Gradle Plugin 4.6 User Manual](https://docs.develocity.ai/gradle/4.6/gradle-plugin/)
- [Gradle — Command-Line Interface](https://docs.gradle.org/current/userguide/command_line_interface.html)
- [GitHub Actions — Security Hardening for GitHub Actions](https://docs.github.com/en/actions/security-for-github-actions/security-guides/security-hardening-for-github-actions)

**Kết luận:** Bảo mật logs, reports và Build Scan bắt đầu từ việc **không đưa dữ liệu nhạy cảm vào các kênh ấy**. Gradle cung cấp các công cụ để giảm console test output và cấu hình JUnit XML; Develocity hỗ trợ giới hạn output capture và obfuscate một số thông tin định danh. Nhưng các controls này **không tự sanitize exceptions, assertions, test names, HTML/binary reports, custom values hoặc dữ liệu đã được publish**. Với Java 17 lab, synthetic canary, scanner fail-closed, CI artifact allowlist, typed credentials và incident response rõ ràng, nhóm có thể giữ thông tin chẩn đoán cần thiết mà giảm đáng kể nguy cơ rò dữ liệu.
