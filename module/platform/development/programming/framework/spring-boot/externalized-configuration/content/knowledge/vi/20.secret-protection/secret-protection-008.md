# Thay đổi bí mật, vòng đời tiến trình và kế hoạch khởi động lại

> **Chủ đề:** Spring Boot Externalized Configuration  
> **Nhóm:** Bảo vệ bí mật

## 1. Tại sao đổi bí mật không chỉ là đổi một giá trị cấu hình?

Một ứng dụng Spring Boot thường cần **bí mật (secrets)** để kết nối tới tài nguyên được bảo vệ: mật khẩu database, API token, khóa ký JWT, client secret OAuth2, private key TLS hoặc thông tin xác thực của message broker. Những giá trị này có thể được cung cấp bằng biến môi trường, file mount, Secret của Kubernetes, secret manager hoặc cơ chế Config Data.

Ví dụ:

~~~yaml
partner:
  api:
    base-url: "https://partner.example.test"
    # Không đặt token thật ở đây.
~~~

Trong container, token có thể đến từ biến môi trường:

~~~text
PARTNER_API_TOKEN=<giá trị được inject an toàn>
~~~

Hoặc từ một file được mount:

~~~text
/run/secrets/partner.api.token
~~~

Giả sử token được thay đổi lúc 10:00. Một câu hỏi quan trọng là **tiến trình Java đang chạy có tự sử dụng token mới hay không?** Câu trả lời phụ thuộc vào cách secret được cấp và cách ứng dụng đọc nó. Có ba lớp hoàn toàn khác nhau:

1. **Nguồn secret bên ngoài thay đổi:** hệ thống quản lý bí mật, Kubernetes Secret hoặc file mount được cập nhật.
2. **Tiến trình nhìn thấy giá trị mới:** biến môi trường, filesystem view hoặc secret client có phản ánh thay đổi không?
3. **Thành phần ứng dụng thực sự sử dụng giá trị mới:** `Environment`, bean `@ConfigurationProperties`, HTTP client, connection pool hoặc lớp xác thực có đọc lại/rebind/rebuild không?

Thay đổi thành công ở lớp 1 **không tự bảo đảm** thành công ở lớp 2 và lớp 3. Vì vậy, kế hoạch **rotation** (xoay vòng bí mật) phải xét **vòng đời tiến trình**, **thời điểm binding**, **khả năng chấp nhận đồng thời secret cũ/mới** và **chiến lược khởi động lại**.

### Mục tiêu bài học

Sau bài này, bạn có thể:

- Phân biệt secret được inject qua môi trường với secret được mount dưới dạng file.
- Giải thích tại sao `@ConfigurationProperties` thường là ảnh chụp của cấu hình tại thời điểm bean được bind.
- Nhận biết các trường hợp file mount có thể cập nhật nhưng Java client vẫn giữ thông tin xác thực cũ.
- Thiết kế quy trình rotation không làm gián đoạn các instance hiện tại.
- Hiểu kế hoạch rolling restart, graceful shutdown và readiness trong Kubernetes.
- Lập thứ tự cấp secret mới, triển khai ứng dụng mới và thu hồi secret cũ.
- Chọn giữa restart có kiểm soát và dynamic refresh khi thực sự cần.
- Bảo vệ bí mật trong log, endpoint chẩn đoán, manifest, shell và pipeline.
- Viết test và runbook để kiểm chứng secret mới được sử dụng sau restart.

## 2. Bí mật khác cấu hình thông thường ở đâu?

Một property như `server.port` hoặc `client.timeout` có thể được xem là thông tin cấu hình không nhạy cảm. Bí mật đòi chính sách riêng vì **bị lộ** có thể trực tiếp trao quyền truy cập hoặc cho phép giả mạo danh tính.

Ví dụ:

| Nhóm dữ liệu | Ví dụ | Cách quản lý |
| --- | --- | --- |
| Cấu hình công khai | timeout, retry limit, hostname không nhạy cảm | Config Data, env, file |
| Bí mật truy cập | database password, API token, OAuth client secret | Secret manager, Secret/volume an toàn |
| Khóa mật mã | JWT signing key, TLS private key | KMS/HSM hoặc nơi quản lý khóa phù hợp |
| Credential có hạn | access token ngắn hạn, certificate có hạn | Cấp phát/gia hạn tự động và vòng đời |
| Dữ liệu trạng thái | token đã refresh, connection đã xác thực | Cơ chế runtime riêng, không chỉ @ConfigurationProperties |

Một bí mật thường có thêm các thuộc tính vận hành:

- **Ngày hết hạn hoặc thời hạn sử dụng.**
- **Phiên bản/định danh khóa** phục vụ chuyển tiếp.
- **Phạm vi quyền** (đọc, ghi, chỉ một service).
- **Nguồn cấp và chủ sở hữu rotation.**
- **Khả năng server chấp nhận đồng thời nhiều credential.**
- **Tác động nếu thu hồi credential cũ.**

Vì vậy, việc đổi password không chỉ là sửa một chuỗi trong YAML. Bạn phải biết những tiến trình nào đang dùng password cũ, làm sao chuyển sang mới và khi nào an toàn để thu hồi giá trị cũ.

## 3. Vòng đời cấu hình trong một tiến trình Spring Boot

Một vòng đời khái quát:

~~~text
Container/VM nhận cấu hình và secret
                   |
                   v
            JVM bắt đầu chạy
                   |
                   v
    Spring chuẩn bị Environment
      - OS environment
      - system properties
      - Config Data, imports
      - file mount, config tree nếu khai báo
                   |
                   v
      Bind @ConfigurationProperties
      + chuyển kiểu + validation
                   |
                   v
     Tạo beans và resource clients
      - DataSource / Hikari pool
      - HTTP client / authorization header
      - Kafka/Redis/MQ client
      - JWT signer / validator
                   |
                   v
        Ứng dụng nhận traffic
                   |
          Secret nguồn thay đổi?
                   |
       Không mặc định có rebind
       hay xây dựng lại clients
~~~

Một số giá trị có thể được tra cứu mỗi lần sử dụng, nhưng các ứng dụng thường đưa chúng vào **singleton beans** hoặc khởi tạo một client/pool một lần. Khi đó, bí mật được sao chép vào cấu trúc runtime.

Ví dụ:

~~~java
@ConfigurationProperties(prefix = "partner.api")
public record PartnerApiProperties(
        String token,
        String baseUrl
) {}
~~~

Khi bean này được bind, `token()` là giá trị trong object tại thời điểm đó. Nếu một file bên ngoài thay đổi, record **không tự cập nhật component**. Dù object khác đọc file mới, bean record cũ vẫn giữ chuỗi cũ.

**Nguyên tắc vận hành an toàn:** với cấu hình bí mật được bind lúc khởi động, giả định rằng phải **khởi động lại tiến trình hoặc có cơ chế refresh/reconstruction được thiết kế tường minh** để sử dụng secret mới.

### 3.1. Cấu hình nguồn khác secret đã được client sử dụng

Một HTTP client có thể xây dựng interceptor:

~~~java
String header = "Bearer " + properties.token();
~~~

và giữ `header` trong memory. Ngay cả khi sau đó `Environment` thay đổi, interceptor đó vẫn giữ header cũ, trừ khi code được thiết kế để cập nhật.

Một database pool có thể được khởi tạo với password cũ; connection đã được tạo tiếp tục dùng session đã xác thực. Thay password trên database không tự tạo lại toàn bộ connection và không tự cấp password mới cho pool.

### 3.2. Refresh Environment khác rebuild toàn bộ hệ thống

Có thể tồn tại thư viện/framework hỗ trợ refresh bean hoặc tự đọc secret mới. Nhưng **refresh property không đồng nghĩa mọi client đã nhận giá trị mới**:

- Constructor có thể chạy một lần.
- Client builder có thể copy value vào configuration nội bộ.
- Connection pool có thể giữ connection sống và credential khởi tạo.
- Một token có thể được cache ở service khác.
- Thread đang xử lý request có thể đang dùng thông tin cũ.

Do đó, nếu muốn dynamic refresh, cần mô tả chính xác những tài nguyên nào được cập nhật và liệu có cần tạo lại connection/client hoặc đồng bộ truy cập giữa các thread hay không.

## 4. Secret được cấp qua biến môi trường

Một cách phổ biến là inject biến môi trường vào tiến trình:

~~~bash
# Ví dụ minh họa tên biến, không chứa secret thực.
PARTNER_API_TOKEN=<secret-value>
~~~

Trong Spring Boot:

~~~java
@ConfigurationProperties(prefix = "partner.api")
public record PartnerApiProperties(String token) {}
~~~

Theo relaxed binding, `partner.api.token` có thể đến từ `PARTNER_API_TOKEN`.

### 4.1. Môi trường của một tiến trình không tự đổi theo Secret bên ngoài

Nếu Kubernetes tạo container với biến môi trường lấy từ Secret, giá trị được cấp cho tiến trình khi container được khởi tạo. **Cập nhật Kubernetes Secret sau đó không làm environment variables trong container đang chạy thay đổi tự động.**

Đây là điểm quan trọng nhất để tránh triển khai lỗi: đổi Secret object trong cluster rồi quan sát rằng một Pod cũ vẫn gửi credential cũ không phải dấu hiệu Spring Boot Binder bị lỗi; đó là cách cấp biến môi trường hoạt động.

Với mô hình này, **Pod/container mới** thường cần được tạo để nhận giá trị mới. Restart tiến trình trong môi trường không được cấp lại biến môi trường cũng có thể không đủ; cần chắc chắn orchestrator/container được tạo lại hoặc nguồn environment được cập nhật.

### 4.2. Hạn chế của biến môi trường đối với bí mật

Ưu điểm:

- Dễ tích hợp với `@ConfigurationProperties` và nhiều thư viện.
- Không cần logic đọc file riêng.
- Phù hợp với triển khai immutable process, khởi động lại khi thay cấu hình.

Cần lưu ý:

- Mỗi tiến trình đã chạy giữ environment riêng.
- Một số công cụ chẩn đoán/process inspection có thể để lộ biến môi trường nếu phân quyền không đúng.
- Có thể bị in nhầm trong log, crash dumps, support bundles hoặc debug endpoints.
- Secret ngắn hạn cần refresh liên tục có thể không thích hợp để cấp tĩnh qua environment.
- Sửa nguồn env của deployment không bảo đảm Pod hiện tại tự được thay thế nếu template/rollout không thay đổi đúng cách.

Không nên coi env var là “mã hóa bí mật”. Nó là **phương thức vận chuyển giá trị**, và vẫn cần kiểm soát truy cập, quản lý lifecycle.

## 5. Secret được cấp bằng file mount

Thay vì environment variable, secret có thể được mount thành file:

~~~text
/run/secrets/partner.api.token
/run/secrets/database.password
~~~

Spring Boot hỗ trợ Config Data import kiểu configuration tree:

~~~properties
spring.config.import=optional:configtree:/run/secrets/
~~~

Khi đó tên file ở dưới root cấu hình có thể trở thành tên property, còn **nội dung file** là value. Ví dụ file `partner.api.token` chứa token, Bean `@ConfigurationProperties(prefix="partner.api")` có thể bind giá trị tương ứng.

### 5.1. Tại sao mount file được dùng?

- Secret có thể được cấp bởi volume thay vì đưa vào environment.
- Quyền đọc file có thể được hạn chế theo user/group và cấu hình workload.
- Với Kubernetes Secret volume dạng thông thường, nội dung mount có thể được cập nhật sau khi Secret object thay đổi.
- Phù hợp cho certificate chain, private key hoặc dữ liệu không nên ép vào một biến môi trường đơn giản.

Tuy nhiên, “file đã cập nhật” **không bằng** “Java bean đã cập nhật”.

### 5.2. Kubernetes Secret volume có thể cập nhật nhưng không ngay lập tức

Khi một Secret được mount dưới dạng volume thông thường, Kubernetes có cơ chế cập nhật nội dung volume sau khi Secret thay đổi. Việc truyền thay đổi là **eventual**, không nên đặt kỳ vọng millisecond hoặc một thời điểm đồng bộ trên mọi Pod.

Hai ngoại lệ quan trọng:

- Nếu Secret được cấp bằng **environment variables**, container đang chạy không nhận bản mới tự động.
- Nếu mount bằng **`subPath`**, Kubernetes không tự truyền những cập nhật Secret theo cùng cơ chế volume thông thường.

Ngoài ra, khả năng ứng dụng tiếp nhận thay đổi vẫn phụ thuộc vào việc có đọc lại file và reload resource thực sự hay không.

### 5.3. Cấu hình Config Tree không phải file watcher tự động

Ví dụ:

~~~properties
spring.config.import=optional:configtree:/run/secrets/
~~~

Chỉ khai báo cơ chế **nạp Config Data lúc khởi động**. Nó không có nghĩa Spring Boot tự giám sát toàn bộ file và rebind mọi `@ConfigurationProperties` bean mỗi khi file bị sửa.

Ngay cả khi Kubernetes đã làm nội dung volume thay đổi, ứng dụng vẫn cần restart hoặc một cơ chế đọc lại/refresh có chủ đích.

### 5.4. Không xử lý file secret như file log hoặc dữ liệu tạm

Secret volume cần hạn chế quyền và không nên copy vào thư mục công khai, image layer hoặc log. Nếu code đọc file bằng `Files.readString`, phải nghĩ tới:

- Quyền đọc tại runtime.
- Nội dung trailing newline có ý nghĩa với credential hay không.
- Encoding của secret dạng text.
- Thời điểm file được cập nhật.
- Trường hợp file đang thay đổi hoặc bị thay thế atomic.
- Việc tạo lại client nào sau khi đọc giá trị mới.

Không nên dùng `trim()` bừa bãi với secret: việc bỏ khoảng trắng hoặc newline có thể làm biến đổi token hợp lệ. Định dạng của secret phải được xác định rõ.

## 6. Bảng so sánh ba cách cấp bí mật

| Cách cấp | Tiến trình đang chạy tự thấy nguồn đổi? | Bean/client tự dùng giá trị mới? | Biện pháp mặc định an toàn |
| --- | --- | --- | --- |
| Environment variable từ Secret | **Không** tự đổi trong container đang chạy | **Không** | Tạo Pod/container mới |
| Secret volume mount thông thường | File có thể cập nhật sau một độ trễ | **Không mặc định** | Restart hoặc reload được thiết kế |
| Secret volume qua `subPath` | Không có cập nhật tự động như mount thông thường | **Không mặc định** | Tạo lại Pod/mount |
| File externalized do operator sửa | Filesystem có thể thay đổi | **Không mặc định** | Restart hoặc refresh có kiểm soát |
| Secret manager SDK truy vấn theo nhu cầu | Có thể lấy bản mới theo SDK/cache policy | Tùy client và tích hợp | Thiết kế TTL, cache, retry và rotation |
| Token ngắn hạn do client tự refresh | Client có thể làm mới theo protocol | Nếu client hỗ trợ đúng | Theo dõi expiry, refresh và lỗi |

Bảng này nói về **hành vi mặc định và mô hình phổ biến**, không khẳng định mọi thư viện Spring hoặc mọi integration đều giống nhau. Nếu ứng dụng có cơ chế hot reload riêng, cần kiểm tra đúng implementation đó.

## 7. Kế hoạch rotation: bốn giai đoạn cơ bản

Một quy trình rotation bền vững thường có bốn giai đoạn:

~~~text
1. PREPARE
   Tạo secret mới và thiết lập hỗ trợ chuyển tiếp
                   |
                   v
2. DISTRIBUTE
   Cấp secret mới cho nguồn deploy / secret manager
                   |
                   v
3. ACTIVATE
   Restart/rollout hoặc refresh các instance;
   xác minh traffic thực sự dùng credential mới
                   |
                   v
4. REVOKE
   Thu hồi secret cũ sau khi không còn người dùng
                   |
                   v
             THEO DÕI & KẾT THÚC
~~~

### 7.1. PREPARE: hiểu cả phía client lẫn phía server

Trước khi thay secret, trả lời:

- Bên cung cấp dịch vụ có cho phép **hai credential cùng tồn tại** không?
- Secret cũ có thời hạn cuối cụ thể chưa?
- Có bao nhiêu deployment, job, cron job, worker và instance đang dùng secret?
- Client đang cấp token qua env, volume, file riêng hay SDK?
- Có rolling restart hay bắt buộc downtime?
- Mất bao lâu để thay một instance?
- Có kết nối dài hạn hoặc transaction đang chạy không?
- Có thể rollback từ phiên bản mới về cũ khi cần không?
- Có log/metric nào xác nhận credential mới đã hoạt động mà không tiết lộ giá trị?

Không thể chọn đúng thứ tự rotation khi chưa biết **cả hai đầu xác thực**. Ví dụ server cho phép song song hai API keys thì quá trình chuyển tiếp dễ hơn việc database chỉ cho đổi mật khẩu tức thời của cùng một tài khoản.

### 7.2. DISTRIBUTE: cấp secret mới mà không đưa nó vào nơi công khai

Phát hành secret bằng hạ tầng được phê duyệt, ví dụ secret manager hoặc Kubernetes Secret. Tránh:

- Commit secret vào Git.
- Đặt giá trị thật trong tài liệu ví dụ hoặc ticket.
- Dán secret vào kênh chat công khai.
- Dùng command line mà secret xuất hiện trong process arguments và shell history.
- Đưa secret vào Dockerfile `ENV` hoặc build args khiến bí mật lọt vào image layer/history.
- In giá trị secret ra log để “chắc chắn đã đổi”.

Nên có người/bộ phận chịu trách nhiệm phát hành, phạm vi quyền rõ ràng và một mã phiên bản **không nhạy cảm** để đối chiếu.

### 7.3. ACTIVATE: làm cho tiến trình dùng bản mới

Nếu ứng dụng bind secret lúc startup, cần **tạo lại instance**. Trong Kubernetes, đó thường là rolling rollout dựa trên Pod template mới hoặc một thao tác restart có kiểm soát.

Không kết luận thành công chỉ vì Kubernetes Secret object đã cập nhật. Cần xác minh các Pod mới đã được tạo, ready và kết nối thành công với credential mới.

### 7.4. REVOKE: chỉ thu hồi bản cũ khi không còn consumer

Thu hồi quá sớm có thể làm các Pod chưa restart hoặc các batch job còn chạy mất quyền truy cập. Thu hồi quá muộn làm tăng thời gian một credential cũ tiếp tục có hiệu lực.

Một cửa sổ chuyển tiếp nên được xác định bằng: khả năng chấp nhận đồng thời secret cũ/mới, thời gian rollout, thời gian sống của job/connection và thời gian tối đa của giao dịch hoặc token.

Khi tất cả consumer đã chuyển và có bằng chứng vận hành, mới thu hồi secret cũ theo kế hoạch. Việc giữ bí mật cũ vô thời hạn “để rollback cho dễ” không phải rotation hoàn chỉnh.

## 8. Rotation hai pha: chấp nhận cũ và mới trước khi loại bỏ cũ

Để tránh downtime, có thể dùng mô hình **overlap** (nếu hệ thống xác thực hỗ trợ):

~~~text
T0: Server chỉ chấp nhận OLD
T1: Server chấp nhận OLD + NEW
T2: Cấp NEW cho các ứng dụng
T3: Rolling restart các instances
T4: Xác minh mọi instance dùng NEW
T5: Server chỉ chấp nhận NEW, thu hồi OLD
~~~

### 8.1. API key có thể hỗ trợ song song

Một provider API có thể cấp nhiều key hoạt động đồng thời. Trong tình huống đó:

1. Cấp key mới từ hệ thống provider.
2. Đưa key mới vào secret store.
3. Rollout ứng dụng để sử dụng key mới.
4. Theo dõi request success/authentication failures.
5. Xác minh không còn consumer của key cũ.
6. Thu hồi key cũ.

Đây thường là con đường rotation đơn giản nhất vì **client cũ và mới cùng hoạt động trong cửa sổ chuyển tiếp**.

### 8.2. Khi provider chỉ cho một mật khẩu tại một thời điểm

Nếu đổi password khiến password cũ hết hiệu lực ngay, rolling restart có thể xuất hiện một khoảng mà:

- Instance cũ dùng credential cũ và bị từ chối.
- Instance mới có credential mới và hoạt động.
- Connection cũ vẫn tồn tại nhưng reconnect có thể thất bại.

Cần phương án khác tùy hệ thống: tạo tài khoản song song với quyền tối thiểu, chuyển lần lượt consumer, dùng credential manager hỗ trợ nhiều phiên bản hoặc chấp nhận maintenance window đã được lên lịch.

**Không có một công thức zero-downtime áp dụng cho mọi cơ chế xác thực.** Khả năng overlap của phía server là điều kiện nền tảng.

### 8.3. JWT signing keys khác API tokens

Với JWT, một hệ thống có thể **ký token mới bằng key mới** nhưng tiếp tục **xác minh token cũ bằng key cũ** cho tới khi chúng hết hạn. Có thể dùng `kid` trong header token và một key set để chọn khóa xác minh thích hợp.

Trình tự thường là:

1. Phát hành public verification key mới hoặc cho validator biết key mới.
2. Chuyển signer sang ký bằng private key mới.
3. Giữ public/verification key cũ trong thời gian sống hợp lệ của token cũ và độ lệch đồng hồ cho phép.
4. Rút key cũ khỏi tập verify sau thời gian chuyển tiếp.

Không áp dụng mô hình “đổi một secret string và restart mọi thứ” một cách mù quáng cho token còn đang sống hoặc key pair. Việc phân phối khóa và ngữ nghĩa xác minh cần được thiết kế cẩn thận.

## 9. Spring Boot @ConfigurationProperties và validation cho secret

Ví dụ record cấu hình dành cho tích hợp partner:

~~~java
package com.example.partner.config;

import java.net.URI;
import java.time.Duration;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@ConfigurationProperties(prefix = "partner.api")
@Validated
public record PartnerApiProperties(
        @NotNull URI baseUrl,
        @NotBlank String token,
        @NotNull Duration timeout
) {}
~~~

Đăng ký bean:

~~~java
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;

@SpringBootApplication
@ConfigurationPropertiesScan
public class PartnerApplication {}
~~~

Với Maven, thêm validation dependency khi cần:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-validation</artifactId>
</dependency>
~~~

### 9.1. Validation kiểm tra secret tồn tại, không xác nhận nó còn hiệu lực

`@NotBlank` giúp phát hiện token thiếu hoặc toàn khoảng trắng lúc startup. Nhưng nó không thể xác nhận provider sẽ chấp nhận token, token chưa hết hạn hoặc quyền của token là đúng.

Cần tách:

- **Cú pháp và sự hiện diện**: binding/Bean Validation.
- **Khả năng xác thực thật**: một phép gọi an toàn, kiểm tra kết nối hoặc metric.
- **Vòng đời rotation**: phát hành, phân phối, kích hoạt, thu hồi.
- **Quyền và bảo mật**: least privilege, không tiết lộ value.

### 9.2. Không log record chứa secret

Record tự có `toString()` và có thể in ra `token`. Không làm:

~~~java
logger.info("Partner config: {}", properties); // Không an toàn.
~~~

Với một mã phiên bản hoặc key identifier **không nhạy cảm**, có thể log:

~~~java
logger.info("Partner credential configuration loaded");
~~~

Nếu cần xác định phiên bản secret nào đang hoạt động, dùng một **secret version ID riêng không có giá trị xác thực** được hệ thống cấp, hoặc một dấu hiệu quan sát được mà chính sách bảo mật cho phép. Không tự in token hoặc hash tùy tiện vào log; hash của credential ngắn/đoán được cũng có thể gây rủi ro.

### 9.3. Không tạo default secret

Không viết:

~~~java
@DefaultValue("test-secret")
String token
~~~

rồi dùng chung cho mọi môi trường. Một default bí mật công khai hoặc có thể đoán thường làm yếu bảo mật. Với secret bắt buộc, hãy yêu cầu nguồn an toàn cung cấp và fail fast nếu thiếu.

## 10. Kubernetes: Secret qua environment variable

Ví dụ một Deployment dùng giá trị từ Secret có sẵn tên `partner-api-credentials`:

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: partner-service
spec:
  replicas: 3
  selector:
    matchLabels:
      app: partner-service
  template:
    metadata:
      labels:
        app: partner-service
    spec:
      containers:
        - name: app
          image: example/partner-service:1.0
          env:
            - name: PARTNER_API_TOKEN
              valueFrom:
                secretKeyRef:
                  name: partner-api-credentials
                  key: token
~~~

Các container được tạo mới nhận giá trị của key `token` theo cơ chế inject secret.

### 10.1. Điều xảy ra sau khi Secret object đổi

Giả sử Secret trong cluster được cập nhật bằng quy trình quản trị đã được phê duyệt. Deployment spec vẫn có reference tới cùng tên Secret. Những container **đang chạy** tiếp tục giữ biến môi trường cũ.

Nếu không có thay đổi nào làm Pod template sinh rollout mới, chỉ cập nhật Secret có thể không khiến Deployment tạo Pod mới. Cần một **kích hoạt rollout/restart có kiểm soát** hoặc thay Pod template theo hệ thống triển khai đang dùng.

### 10.2. Ví dụ rolling restart

Trong môi trường được phép vận hành:

~~~bash
kubectl rollout restart deployment/partner-service \
  --namespace production
~~~

Sau đó theo dõi:

~~~bash
kubectl rollout status deployment/partner-service \
  --namespace production
~~~

Đây là ví dụ thao tác **chỉ nên thực hiện theo quyền hạn và change plan phù hợp**. Không chạy thử lệnh này trên production chỉ để học. Nó làm Pod thay thế theo chiến lược Deployment; trạng thái rollout phải được kiểm tra.

### 10.3. Restart ở đây nghĩa là gì?

`kubectl rollout restart` khiến Deployment khởi tạo một đợt rollout mới bằng cách thay đổi Pod template annotation. Các Pod mới được tạo và environment của chúng được inject lại từ Secret hiện hành.

Nó **không** có nghĩa tất cả Pod cũ biến mất cùng một lúc, cũng không bảo đảm zero downtime nếu replicas, readiness probe, tài nguyên cluster hoặc rolling strategy được thiết kế sai.

## 11. Kubernetes: Secret qua volume và configtree

Ví dụ một Secret được mount vào `/run/secrets`:

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: partner-service
spec:
  replicas: 2
  selector:
    matchLabels:
      app: partner-service
  template:
    metadata:
      labels:
        app: partner-service
    spec:
      containers:
        - name: app
          image: example/partner-service:1.0
          volumeMounts:
            - name: partner-secrets
              mountPath: /run/secrets
              readOnly: true
          env:
            - name: SPRING_CONFIG_IMPORT
              value: "optional:configtree:/run/secrets/"
      volumes:
        - name: partner-secrets
          secret:
            secretName: partner-config-files
~~~

Để Spring Boot bind `partner.api.token` qua Config Tree, tên file bên dưới mount phải tương ứng với key cần nạp (ví dụ Secret data key `partner.api.token` tạo file cùng tên). Đây là khác biệt với `secretKeyRef` dạng environment variable, nơi bạn chủ động map key `token` vào tên `PARTNER_API_TOKEN`.

### 11.1. File trên volume có thể đổi

Khi `partner-config-files` đổi, Kubernetes có thể cập nhật nội dung Secret volume sau một khoảng trễ. Một tiến trình đọc lại file đúng thời điểm có thể nhận value mới.

Nhưng code sử dụng `PartnerApiProperties.token()` đã bind lúc startup thường **vẫn giữ token cũ**. Có nghĩa là:

~~~text
Kubernetes Secret mới      : YES
File mount trong Pod mới   : YES
File mount trong Pod cũ    : CÓ THỂ, sau một độ trễ
Record đã bind lúc startup : KHÔNG TỰ ĐỔI
Client đã khởi tạo         : KHÔNG TỰ ĐỔI
~~~

### 11.2. SubPath và giới hạn cập nhật

Nếu mount Secret thông qua `subPath`, Kubernetes không cập nhật nội dung Secret theo cách tự động như mount thông thường. Trong quy trình rotation, đừng dựa vào một file `subPath` để hot reload mà không có một cơ chế thay Pod/mount.

### 11.3. Tránh mount nhiều file nhạy cảm không cần thiết

Nếu cùng một Secret chứa nhiều key, mount toàn bộ volume có thể cấp nhiều file hơn nhu cầu của từng container. Hãy áp dụng nguyên tắc least privilege ở phạm vi Secret object, namespace, ServiceAccount và loại key được cấp. Kubernetes Secret object cũng cần RBAC, at-rest encryption và chính sách quản trị phù hợp.

## 12. Thiết kế rolling restart để hạn chế downtime

Giả sử Deployment có nhiều replica phục vụ traffic. Mục tiêu rotation là thay lần lượt Pod để không mất khả năng phục vụ.

Ví dụ:

~~~yaml
spec:
  replicas: 4
  strategy:
    type: RollingUpdate
    rollingUpdate:
      maxUnavailable: 0
      maxSurge: 1
~~~

Ý nghĩa:

- `replicas: 4`: số replica mong muốn.
- `maxUnavailable: 0`: mục tiêu không giảm số Pod sẵn sàng dưới mức yêu cầu trong quá trình rollout.
- `maxSurge: 1`: có thể tạo thêm tối đa một Pod so với số mong muốn trong lúc thay thế.

Đây là **chính sách hỗ trợ** duy trì khả năng phục vụ, nhưng không phải bảo đảm tuyệt đối. Nếu cluster không đủ tài nguyên để tạo Pod mới, rollout có thể bị kẹt. Nếu readiness báo xanh quá sớm hoặc ứng dụng không xử lý shutdown tốt, người dùng vẫn có thể gặp lỗi.

### 12.1. Readiness probe

Ứng dụng chỉ nên được xem là ready khi đủ điều kiện nhận traffic. Ví dụ Spring Boot Actuator có thể cung cấp nhóm health cho readiness khi được cấu hình phù hợp:

~~~yaml
management:
  endpoint:
    health:
      probes:
        enabled: true
~~~

Manifest minh họa:

~~~yaml
readinessProbe:
  httpGet:
    path: /actuator/health/readiness
    port: 8080
  periodSeconds: 5
  failureThreshold: 3
~~~

Chỉ dùng đường dẫn và cổng này khi ứng dụng thực tế có Actuator, endpoint health đã sẵn sàng và network routing đúng. Không tự giả định mọi ứng dụng Boot đều mở endpoint giống nhau.

Một readiness probe tốt nên phản ánh khả năng phục vụ thiết yếu mà không gây kết nối mạng quá nặng hoặc tạo restart loop gián tiếp.

### 12.2. Graceful shutdown

Khi Pod cũ được yêu cầu dừng, cần cho request/transaction đang chạy có cơ hội kết thúc.

Trong Spring Boot trên web server hỗ trợ, có thể cấu hình:

~~~yaml
server:
  shutdown: graceful
spring:
  lifecycle:
    timeout-per-shutdown-phase: 30s
~~~

Đồng thời, cần cấu hình `terminationGracePeriodSeconds` của Pod phù hợp với thời gian mà ứng dụng cần để hoàn tất shutdown:

~~~yaml
spec:
  terminationGracePeriodSeconds: 45
~~~

Các giá trị chỉ mang tính ví dụ. Grace period thực tế phải xét latency, request dài, batch processing, cách server ngừng nhận kết nối mới, preStop hook nếu có và khả năng queue worker dừng an toàn.

### 12.3. Không tắt ngay credential cũ khi còn Pod cũ

Trong rolling update, sẽ có một giai đoạn cả Pod cũ và Pod mới cùng chạy. Nếu credential cũ bị thu hồi ở đầu rollout trong khi Pod cũ vẫn nhận traffic, các request còn ở Pod cũ có thể thất bại.

Do đó, muốn rotation gần zero downtime, **dịch vụ xác thực phía server phải cho phép giai đoạn overlap** hoặc hệ thống phải có kế hoạch chấp nhận gián đoạn ngắn.

## 13. Database password rotation và connection pool

Database có thêm vấn đề kết nối sống lâu. Ví dụ application dùng Spring DataSource và HikariCP, nơi password được cấu hình cho pool lúc startup.

~~~yaml
spring:
  datasource:
    url: "jdbc:postgresql://db.internal:5432/orders"
    username: "orders_app"
    # Password được cấp bằng nguồn secret an toàn.
~~~

Nếu password của tài khoản `orders_app` được đổi trong database:

- Các kết nối đã xác thực có thể vẫn hoạt động tùy DB/protocol và chính sách của server.
- Khi pool tạo kết nối mới, password cũ có thể bị từ chối.
- Chỉ thay biến môi trường của Pod hoặc Secret volume không tự cập nhật mọi tham số của pool.
- Một số pool/client có API cập nhật credential, nhưng cần thiết kế rõ việc tạo mới/recycle connections.

### 13.1. Cách đơn giản: restart từng instance khi credential mới đã hợp lệ

Nếu có cơ chế nhiều account/credential cùng quyền và được phép overlap:

1. Tạo user/credential mới với quyền tối thiểu cần thiết.
2. Xác nhận credential mới kết nối đúng database và đúng scope.
3. Cấp credential mới vào Secret.
4. Rolling restart service.
5. Kiểm tra success rate của kết nối mới, pool metrics và các luồng đọc/ghi chính.
6. Thu hồi credential cũ sau khi không còn consumer.

### 13.2. Nếu chỉ có một password hoạt động

Nếu DB không cho phép đồng thời secret cũ/mới của cùng một identity, có thể cần:

- Kế hoạch maintenance window.
- Phương án dùng user song song trong thời gian migration.
- Credential rotation integration được DB/provider hỗ trợ.
- Chính sách reconnect/retry có giới hạn và thông báo downtime nếu có.

Không nên hứa hẹn zero downtime cho mọi database chỉ bằng `kubectl rollout restart`.

### 13.3. Job nền và cron job dễ bị bỏ sót

Một web Deployment có thể đã chuyển sang credential mới, nhưng còn:

- CronJobs chạy theo lịch.
- Queue consumers ở một Deployment khác.
- Batch jobs đang thực thi dài giờ.
- Admin/migration tools.
- Dịch vụ reporting hoặc audit dùng cùng tài khoản.

Nếu thu hồi secret cũ quá sớm, những thành phần đó có thể bị lỗi ở lần kết nối tiếp theo. Danh sách consumer đầy đủ là một phần quan trọng của runbook rotation.

## 14. Secret manager và refresh động

Một số tổ chức dùng external secret manager để cấp credential và thực hiện rotation theo phiên bản. Có thể có SDK trực tiếp hoặc integration với Spring Boot Config Data/PropertySource.

Cần phân biệt hai thiết kế:

### 14.1. Load-on-startup

Ứng dụng nạp secret khi khởi động rồi giữ trong bean. Nếu secret manager có phiên bản mới, ứng dụng thường phải restart hoặc dùng một cơ chế rebind để nhận bản mới.

Đây là mô hình dễ kiểm soát, nhất là với tiến trình immutable trong container.

### 14.2. Fetch-on-demand hoặc auto-refresh

Client gọi secret manager theo nhu cầu hoặc giữ cache với TTL. Cần giải quyết:

- Thời gian lưu cache và giới hạn request tới secret manager.
- Quy tắc refresh trước expiry.
- Kết nối mạng và outage của secret manager.
- Backoff khi refresh thất bại.
- Chuyển phiên bản đồng thời giữa threads.
- Cách tái tạo clients/connections đang dùng secret cũ.
- Khả năng fallback trong cửa sổ chuyển tiếp.
- Mức độ log/metrics không tiết lộ credential.

Ví dụ thiết kế một interface:

~~~java
public interface CredentialSupplier {
    String currentToken();
}
~~~

Một HTTP interceptor có thể gọi `currentToken()` cho từng request thay vì giữ token trong field được khởi tạo một lần. Nhưng đây chỉ là **mô hình API**, chưa phải một triển khai rotation hoàn chỉnh. Cần cache, đồng bộ, xác thực, timeout, secret zeroization khi khả thi và điều kiện lỗi.

### 14.3. Không cần hot reload nếu restart an toàn hơn

Dynamic refresh tăng độ phức tạp: nhiều bean có thể nhìn thấy phiên bản secret khác nhau, connection pool có thể giữ credential cũ, refresh đồng thời có thể gây race condition. Nếu ứng dụng đã có nhiều replica, rolling restart có readiness/graceful shutdown thường là phương án **dễ kiểm chứng hơn** cho bí mật có thời gian sống đủ dài.

Chỉ thêm hot reload khi mục tiêu kinh doanh yêu cầu hoặc khi loại secret có vòng đời rất ngắn khiến việc restart mỗi lần không hợp lý.

## 15. Tại sao @RefreshScope không giải quyết mọi vấn đề?

Một số hệ sinh thái như Spring Cloud cung cấp cơ chế refresh context/bean. Tuy nhiên, `@RefreshScope` **không phải** tính năng mặc định của Spring Boot thuần, và sự có mặt của nó không bảo đảm mọi client sẽ được cập nhật.

Ví dụ, nếu HTTP client singleton nằm ngoài refresh scope, nó có thể vẫn giữ một authorization header đã tạo với token cũ. Hoặc pool database có thể giữ connection cũ dù properties bean đã được bind lại.

Khi thiết kế refresh:

1. Xác định component nào cần cập nhật.
2. Xác định nơi cache secret.
3. Bảo đảm refresh xảy ra an toàn giữa các request.
4. Xác định việc đóng/tạo lại connection hoặc client.
5. Không mở endpoint refresh không được bảo vệ.
6. Test theo đúng loại secret/provider và version framework.

Tránh làm lộ secret qua Actuator `env`, `configprops` hoặc các endpoints tùy chỉnh. Nếu bật tính năng quản trị, áp dụng authentication, authorization, network restriction và redaction.

## 16. Quản trị Secret: quyền và phiên bản

Rotation là một quy trình bảo mật, nên cần thêm kiểm soát ngoài code.

### 16.1. Least privilege

Mỗi service chỉ nên đọc những secret mà nó thực sự cần. Không cấp quyền rộng để đọc mọi secret trong namespace/project chỉ vì triển khai thuận tiện. Secret manager policies và Kubernetes RBAC cần phù hợp phạm vi workload.

### 16.2. Encryption và truyền dữ liệu

Bí mật nên được mã hóa khi lưu theo khả năng nền tảng, truyền qua kênh bảo vệ, và không đi qua hệ thống log/monitoring ở dạng raw. Kubernetes Secret có biểu diễn base64 trong API; **base64 không phải mã hóa** và không thay thế encryption at rest hay kiểm soát quyền.

### 16.3. Secret version và audit trail

Nên biết phiên bản nào đang được cấp cho từng môi trường, ai phê duyệt thay đổi và lúc nào thu hồi. Có thể dùng một metadata/version ID không nhạy cảm để đối chiếu trong deployment. Tránh in raw value hoặc hash dễ đảo ngược của secret vào deployment annotation hay log.

### 16.4. Tránh vòng đời secret gắn chặt với build artifact

Một mô hình tốt thường không nhúng credential thật vào JAR hoặc Docker image. Image nên có thể triển khai ở nhiều môi trường, còn secret đến từ hạ tầng tại thời điểm chạy.

Điều này giúp rotation không cần rebuild code chỉ để đổi password và giảm nguy cơ lộ credential trong artifact registry.

## 17. Kế hoạch khởi động lại khi ứng dụng chỉ có một instance

Không phải service nào cũng có nhiều replica. Nếu chỉ có một instance:

- Restart có thể tạo khoảng gián đoạn.
- Có thể cần maintenance window đã được thông báo.
- Cần xác nhận job in-flight và dữ liệu không bị mất.
- Cần lưu trạng thái checkpoint hoặc hỗ trợ retry/idempotency.
- Cần kế hoạch rollback an toàn nếu credential mới không hoạt động.

Đối với service xử lý hàng đợi, có thể dừng nhận message mới, chờ các message đang xử lý hoàn tất hoặc trả lại queue theo semantics của broker, sau đó restart và tiếp tục.

Đối với một ứng dụng HTTP một replica, có thể dùng blue-green deployment hoặc chuẩn bị instance song song nếu hạ tầng cho phép, nhưng không nên tuyên bố zero downtime nếu không có readiness, routing và khả năng chấp nhận secret cũ/mới cùng lúc.

## 18. Runbook mẫu cho xoay vòng API token trên Kubernetes

**Phạm vi:** một Spring Boot Deployment nhiều replica, token được cấp qua `secretKeyRef` environment variable và được bind lúc startup.

### 18.1. Trước khi bắt đầu

- [ ] Xác định owner và thời hạn rotation.
- [ ] Liệt kê tất cả consumer của token.
- [ ] Xác nhận provider hỗ trợ hai token cùng lúc.
- [ ] Xác nhận số replica, rolling strategy, readiness và graceful shutdown.
- [ ] Xác nhận quyền cập nhật Secret/Deployment theo quy trình change management.
- [ ] Chuẩn bị tiêu chí thành công và phương án rollback.
- [ ] Kiểm tra không có giá trị raw secret trong log/dashboard.
- [ ] Đảm bảo có khả năng quan sát request success, 401/403, latency và errors.

### 18.2. Phát hành token mới

Cấp token mới qua provider. Không thu hồi token cũ ở bước này. Kiểm tra token mới qua một phép gọi an toàn ở môi trường hoặc công cụ được phê duyệt và không để lộ token vào terminal history.

### 18.3. Cập nhật Secret store

Dùng cơ chế quản trị/CI được cho phép để cập nhật `partner-api-credentials`. Không cần ghi token thật vào tài liệu hay manifest ví dụ.

Nếu dùng GitOps với external-secrets controller, cần phân biệt bước thay secret ở backend, bước controller đồng bộ Kubernetes Secret và bước tạo rollout mới. Mỗi bước có trạng thái và độ trễ riêng.

### 18.4. Kích hoạt rollout

Khi dữ liệu đã được phân phối tới đúng Secret:

~~~bash
kubectl rollout restart deployment/partner-service \
  --namespace production
~~~

Sau đó:

~~~bash
kubectl rollout status deployment/partner-service \
  --namespace production
~~~

Các lệnh chỉ là ví dụ thao tác dành cho người có quyền trong đúng môi trường. Theo dõi Pods mới, readiness và số replica sẵn sàng.

### 18.5. Xác nhận ứng dụng dùng token mới

Không log raw token. Có thể xác nhận bằng:

- Tỷ lệ HTTP 2xx/401/403 tại phía ứng dụng.
- Audit của provider cho credential version hoặc key ID (nếu hỗ trợ).
- Trạng thái readiness và số Pod cũ còn lại.
- Kiểm tra một request nghiệp vụ an toàn qua service mới.
- Không còn lỗi authentication trong một cửa sổ quan sát đã định.

**Chỉ thấy rollout status thành công chưa đủ**, nếu client mới vẫn có thể dùng token cũ do lấy từ sai Secret, sai namespace hoặc cache ở nguồn khác.

### 18.6. Thu hồi token cũ

Sau khi chắc chắn tất cả consumer đã chuyển và không còn batch jobs dùng token cũ, thu hồi token cũ theo cửa sổ đã thống nhất. Theo dõi 401/403 và các job chạy trễ sau thu hồi.

### 18.7. Xử lý rollback

Rollback không luôn chỉ là `kubectl rollout undo`. Nếu token cũ đã bị thu hồi, đưa image/Pod template cũ trở lại có thể khôi phục code nhưng **không khôi phục khả năng xác thực**. Runbook rollback phải bao gồm trạng thái secret ở phía provider và khả năng cấp lại phiên bản hợp lệ.

Nếu có thể, giữ token cũ hoạt động trong suốt cửa sổ rollout và xác nhận rollback, rồi mới thu hồi.

## 19. Khi nào phải thu hồi ngay, không chờ rollout đẹp?

Khi nghi ngờ secret đã **bị lộ hoặc bị khai thác**, ưu tiên an ninh có thể khác quy trình planned rotation. Có thể cần thu hồi credential ngay để chặn truy cập trái phép dù điều đó gây gián đoạn tạm thời.

Trong tình huống incident:

1. Kích hoạt incident response theo chính sách tổ chức.
2. Giới hạn tác động của credential và kiểm soát phạm vi.
3. Cấp/đổi credential an toàn.
4. Thu hồi hoặc vô hiệu hóa secret bị xâm phạm theo mức độ rủi ro.
5. Khởi động lại/reconfigure consumer nhanh nhất có thể.
6. Kiểm tra audit logs, quyền truy cập, dấu hiệu lạm dụng và tài nguyên liên quan.
7. Xử lý nguyên nhân lộ bí mật, không chỉ đổi chuỗi.
8. Ghi lại thời điểm, quyết định và hậu kiểm sau sự cố.

Đừng vì mục tiêu zero downtime mà giữ một credential **đã bị xâm phạm** hoạt động quá lâu. Kế hoạch planned rotation và emergency revocation có mục tiêu ưu tiên khác nhau.

## 20. Testing: xác minh hành vi thay vì giả định

Một chiến lược kiểm thử nên bao gồm cả cấu hình và vòng đời deployment.

### 20.1. Test startup validation

Với `PartnerApiProperties` có `@NotBlank token`:

- Khi token có giá trị và các field khác hợp lệ, bean được bind.
- Khi thiếu token hoàn toàn, context phải thất bại nếu validation được thiết lập đúng.
- Khi token là chuỗi rỗng hoặc chỉ khoảng trắng, validation phải từ chối.

Ví dụ này kiểm tra **sự hiện diện của cấu hình**, không chứng minh remote provider chấp nhận token.

### 20.2. Test ứng dụng giữ giá trị ban đầu

Ở một integration test có kiểm soát:

1. Cấp một token thử nghiệm A qua cấu hình.
2. Khởi tạo context và đọc thuộc tính từ bean.
3. Thay file nguồn bằng token thử nghiệm B.
4. Quan sát bean đã bind thường vẫn có A nếu không có refresh mechanism.
5. Restart context với cùng nguồn B và xác nhận bean mới nhận B.

Bài test nên dùng token giả và hệ thống mock/stub, không dùng credential production.

### 20.3. Test Kubernetes env injection

Trong môi trường sandbox:

1. Tạo Secret giả có key `token=A`.
2. Tạo Pod mẫu nhận env từ Secret.
3. Thay Secret thành `token=B`.
4. Xác nhận Pod hiện tại vẫn có giá trị env được cấp ban đầu (không cần in token; dùng app kiểm tra version ID riêng).
5. Tạo Pod mới và xác nhận nó nhận giá trị cập nhật.

Bài học là phân biệt **nguồn Secret object** và **process environment**.

### 20.4. Test volume mount và Config Tree

Dùng Secret dạng file mount, test theo hai tầng:

- Kỳ vọng filesystem volume cập nhật eventual trong điều kiện Kubernetes phù hợp.
- Kỳ vọng `@ConfigurationProperties` đã bind **không tự đổi** khi không có refresh.
- Khi dùng `subPath`, không kỳ vọng cập nhật tự động giống mount thường.
- Sau restart, bean bind lại từ dữ liệu file hiện tại.

Có thể dùng version ID không nhạy cảm hoặc token giả để kiểm chứng, tránh log secret thực.

### 20.5. Test rolling restart và rollback

Đặt mô hình nhỏ nhiều replica và thiết lập readiness. Khi rollout với secret mới:

- Pod mới chỉ ready sau khi có khả năng xử lý kiểm tra cần thiết.
- Pod cũ có thời gian drain.
- Đảm bảo không có lỗi authentication trong quá trình old/new overlap.
- Tìm trường hợp một replica lỗi binding làm rollout kẹt.
- Diễn tập rollback cả code lẫn trạng thái secret provider.

## 21. Các lỗi thường gặp

| Triệu chứng | Nguyên nhân phổ biến | Hướng xử lý |
| --- | --- | --- |
| Secret object đổi nhưng Spring vẫn dùng giá trị cũ | Bean/HTTP client đã bind lúc startup | Restart hoặc thiết kế refresh/reconstruction |
| Env var trong Pod không đổi | Env injection không cập nhật tiến trình đang chạy | Tạo Pod/container mới |
| File mount đổi nhưng client vẫn gửi token cũ | Client cache token/connection | Rebuild client hoặc restart |
| File qua `subPath` không cập nhật | Giới hạn cập nhật Secret mount | Tạo lại Pod hoặc thay kiểu mount |
| Restart Pod nhưng token vẫn cũ | Secret chưa được đồng bộ, sai name/namespace/key, nguồn ưu tiên khác | Kiểm tra mapping/precedence và version |
| Rollout báo thành công nhưng có 401 | Client mới dùng secret sai, provider từ chối hoặc còn consumer cũ | Xem auth metrics và provider audit |
| Database pool lỗi sau đổi password | Pool tạo connection mới bằng credential cũ | Recreate/update pool hoặc restart có kiểm soát |
| Thu hồi key cũ làm batch lỗi | Job/cron worker chưa chuyển | Liệt kê toàn bộ consumer, cho overlap |
| Rollout bị kẹt | Pod mới không ready hoặc cluster thiếu tài nguyên | Xem readiness, quotas, image, startup errors |
| Rollback code không phục hồi | Credential cũ đã bị thu hồi | Kế hoạch rollback phải bao gồm credential |
| Secret lộ trong log | In record/Environment hoặc debug header | Bỏ log raw value, kiểm soát Actuator |
| Cập nhật GitOps nhưng Pod không restart | Secret sync không đổi Pod template | Trigger rollout theo chiến lược được phê duyệt |
| Giữ cả hai key vô thời hạn | Không có bước revoke/owner rõ | Gắn deadline và xác minh consumer |
| Hot reload gây lỗi ngẫu nhiên | Rebind không đồng bộ, client cũ chưa tái tạo | Test concurrency hoặc chuyển sang restart |

## 22. Một sơ đồ quyết định cho lần thay secret tiếp theo

~~~text
Secret mới được tạo
         |
         v
Secret cũ và mới có thể cùng hợp lệ?
    |                       |
   Có                      Không
    |                       |
    v                       v
Bật overlap              Có cách migration
và lên lịch rollout      song song/maintenance?
    |                       |
    v                       v
App đọc secret khi startup?
    |                       |
   Có                      Không
    |                       |
    v                       v
Rolling restart          Refresh mechanism
hoặc tạo Pod mới         được test đầy đủ?
    |                       |
    v                       v
Kiểm tra readiness,      Reload/rebuild clients,
authentication và jobs   kiểm tra consistency
         \                  /
          \                /
           v              v
       Tất cả consumer đã chuyển?
                   |
          Không ---+--- Có
             |         |
             v         v
       Tiếp tục     Thu hồi secret cũ
       giám sát     và theo dõi hậu kỳ
~~~

Sơ đồ là hướng ra quyết định, không thay thế thiết kế security/protocol của từng provider. Đối với credential có thể bị xâm phạm, chính sách khẩn cấp có thể yêu cầu thu hồi ngay thay vì đi theo đường overlap.

## 23. Bài tập thực hành

### Bài tập A — Nhận biết secret snapshot

Viết một record `@ConfigurationProperties(prefix="lesson.auth")` chứa token và đăng ký bằng `@ConfigurationPropertiesScan`. Khởi động với token giả A. Sửa file cấu hình bên ngoài thành B trong lúc ứng dụng đang chạy. Giải thích vì sao bean record vẫn có thể giữ A; restart để nhận B.

### Bài tập B — Environment vs volume

Trong một Kubernetes sandbox, tạo một Secret giả rồi cấp qua cả `secretKeyRef` environment và volume mount. Sửa Secret. Quan sát sự khác nhau của env và nội dung file, nhưng không in credential thật.

### Bài tập C — @ConfigurationProperties với Config Tree

Tạo file `/run/secrets/lesson.auth.token` trong môi trường thử nghiệm, khai báo:

~~~properties
spring.config.import=optional:configtree:/run/secrets/
~~~

Bind `lesson.auth.token` vào record có `@NotBlank`. Thử thiếu file và file rỗng. Quan sát khi nào validation chặn startup.

### Bài tập D — Lập kế hoạch API key rotation

Giả sử provider cho phép hai key đồng thời và service có ba Pod. Hãy viết runbook theo thứ tự: cấp key mới, cập nhật Secret, restart/rollout, theo dõi Pod và auth metrics, thu hồi key cũ. Liệt kê các điều kiện để rollback an toàn.

### Bài tập E — Database credential

Một service có HikariCP pool và một batch job dùng cùng DB account. Đổi password có thể làm lần tạo connection mới bị lỗi. Hãy chọn giữa user song song, maintenance window hoặc một cơ chế rotation riêng của DB. Giải thích khi nào thu hồi account cũ.

### Bài tập F — JWT signing key

Thiết kế cách đổi key ký JWT mà vẫn xác minh token cũ cho tới khi hết hạn. Xác định thứ tự phân phối verification key, chuyển signer và thời điểm rút key cũ.

### Bài tập G — Rolling restart

Với Deployment có `replicas=4`, `maxUnavailable=0` và `maxSurge=1`, mô tả điều kiện rollout an toàn. Giải thích vì sao vẫn cần readiness, tài nguyên dự phòng và graceful shutdown.

### Bài tập H — Emergency revocation

Giả sử một token bị lộ trong CI log. Hãy xác định bước cần làm khác planned rotation: giới hạn quyền, thu hồi, cấp mới, restart workloads và kiểm tra audit. Không tiếp tục giữ token cũ có hiệu lực chỉ để tránh gián đoạn mà bỏ qua rủi ro.

## 24. Checklist cho production rotation

- [ ] Đã xác định đầy đủ các consumer của secret.
- [ ] Biết secret được cấp qua env, file, Config Tree hay secret manager SDK.
- [ ] Biết lúc nào bean/client hiện tại được khởi tạo và giữ credential.
- [ ] Xác nhận secret mới hoạt động ở phía provider trước khi thu hồi cũ.
- [ ] Có cửa sổ overlap hoặc kế hoạch maintenance thích hợp.
- [ ] Đã cập nhật secret store theo quy trình an toàn.
- [ ] Đã phân biệt Secret object update với Pod rollout.
- [ ] Đã chọn trigger restart/rollout được kiểm soát.
- [ ] Readiness và graceful shutdown phù hợp workload.
- [ ] Còn tài nguyên cluster đủ để rollout theo maxSurge.
- [ ] Có metric authentication failures, latency và success rate.
- [ ] Có cách xác nhận phiên bản secret **không lộ giá trị**.
- [ ] Đã kiểm tra CronJobs, batch workers và consumers ngoài web Deployment.
- [ ] Có rollback plan bao gồm credential và provider state.
- [ ] Có thời điểm/công cụ thu hồi secret cũ.
- [ ] Secret cũ không được giữ hoạt động vô thời hạn.
- [ ] Đã kiểm tra log, Actuator và quyền truy cập Secret.
- [ ] Đã phân biệt planned rotation với emergency incident response.
- [ ] Có ghi nhận owner, thời điểm, outcome và hậu kiểm.

## 25. Ghi nhớ

1. **Thay Secret nguồn không đồng nghĩa ứng dụng đang chạy dùng Secret mới.** Phải xét ba tầng: secret store, process view và bean/client runtime.
2. Với **environment variables**, Pod/container đang chạy không tự nhận giá trị Kubernetes Secret mới; cần tạo Pod/container mới.
3. Với **Secret volume**, file có thể được cập nhật eventual nhưng `@ConfigurationProperties` và client đã bind không tự refresh; mount `subPath` còn có giới hạn cập nhật riêng.
4. **Rolling restart** có thể hỗ trợ chuyển tiếp an toàn khi có nhiều replica, readiness, graceful shutdown và đủ tài nguyên, nhưng không bảo đảm zero downtime trong mọi tình huống.
5. **Overlap old/new credentials** là yếu tố chủ chốt để rotation không gián đoạn khi phía provider hỗ trợ. Thu hồi secret cũ sau khi toàn bộ consumer đã chuyển.
6. **Connection pools và clients có trạng thái** có thể tiếp tục dùng credential cũ dù source đã đổi. Cần restart/rebuild hoặc refresh chuyên biệt được kiểm thử.
7. **Validation startup** kiểm tra secret có được cấp và có đúng hình dạng cơ bản, không tự chứng minh provider còn chấp nhận token.
8. **Rollback code không nhất thiết rollback credential**. Runbook phải bao gồm trạng thái của secret provider và thời điểm revoke.
9. **Không log giá trị secret**, không nhúng vào image/Git và không coi base64 là mã hóa.
10. Khi secret bị xâm phạm, **ưu tiên incident response và thu hồi theo rủi ro**, không máy móc theo kế hoạch planned rotation.

## Tài liệu tham khảo

- [Spring Boot — Externalized Configuration](https://docs.spring.io/spring-boot/reference/features/external-config.html): property sources, Config Data, configtree imports và precedence.
- [Spring Boot — Type-safe Configuration Properties](https://docs.spring.io/spring-boot/reference/features/external-config.html#features.external-config.typesafe-configuration-properties): record binding và validation.
- [Spring Boot — Graceful Shutdown](https://docs.spring.io/spring-boot/reference/web/graceful-shutdown.html): ngừng nhận request và timeout shutdown.
- [Spring Boot Actuator — Kubernetes Probes](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html#actuator.endpoints.kubernetes-probes): readiness/liveness và các lưu ý.
- [Kubernetes — Secret](https://kubernetes.io/docs/concepts/configuration/secret/): cách cấp secret qua environment và volume, cập nhật mounted Secrets và `subPath`.
- [Kubernetes — Deployment](https://kubernetes.io/docs/concepts/workloads/controllers/deployment/): rolling updates và rollout strategy.
- [Kubernetes — Pod Lifecycle](https://kubernetes.io/docs/concepts/workloads/pods/pod-lifecycle/): termination, graceful shutdown và vòng đời Pod.
- [Kubernetes — Encrypting Secret Data at Rest](https://kubernetes.io/docs/tasks/administer-cluster/encrypt-data/): cân nhắc encryption khi lưu Kubernetes Secrets.
- [OWASP — Secrets Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Secrets_Management_Cheat_Sheet.html): quản lý và rotation bí mật theo vòng đời.
