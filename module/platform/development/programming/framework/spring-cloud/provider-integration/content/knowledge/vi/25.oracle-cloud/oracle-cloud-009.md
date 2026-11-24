# Tích hợp Logging, Email Delivery và gọi Functions theo nhu cầu

Spring Boot trên Oracle Cloud Infrastructure (OCI) thường cần ba năng lực bổ sung ngoài database, storage và messaging: gửi log ứng dụng tới nơi tập trung để tìm kiếm; gửi email giao dịch qua hạ tầng Email Delivery; và gọi một tác vụ serverless khi cần xử lý độc lập hoặc mở rộng theo nhu cầu. OCI cung cấp các dịch vụ managed tương ứng là Logging, Email Delivery và Functions. Spring Cloud Oracle 2.0.4 có starter riêng để đưa chúng vào ứng dụng theo các API quen thuộc của Spring.

Ba tích hợp này giải quyết ba loại luồng khác nhau:

- **Logging** chuyển thông tin chẩn đoán từ ứng dụng vào log đã tạo trong OCI Logging. Dịch vụ cũng nhận service logs và audit logs từ OCI.
- **Email Delivery** nhận email qua SMTP hoặc HTTPS, kiểm tra sender và domain, rồi chuyển tiếp tới mail server của người nhận.
- **Functions** nhận invocation đã xác thực, chạy function đã triển khai trong một Functions application và trả kết quả đồng bộ hoặc tiếp tục chạy ở chế độ detached.

Không nên xem ba starter là một hệ thống tự động hoàn chỉnh. Logging starter không tự biến mọi dòng SLF4J thành custom log; Email Delivery không đảm bảo thư vào inbox chỉ vì SMTP chấp nhận; Functions detached không phải một transaction đồng bộ với database của Spring Boot. Ứng dụng vẫn phải thiết kế buffer/retry, identity, quyền, idempotency, audit và cách xử lý kết quả.

Bài dùng document-service làm ví dụ: service ghi log nghiệp vụ và kỹ thuật, gửi email báo trạng thái xử lý hợp đồng, rồi gọi function để tạo thumbnail hoặc kiểm tra file. Các ví dụ dùng Spring Cloud Oracle 2.0.4; khi chọn phiên bản khác, đối chiếu compatibility matrix với Spring Boot, Java và OCI SDK của dự án.

## 1. Mục tiêu học tập và kiến trúc

Sau bài học, bạn có thể:

1. Phân biệt OCI Audit Logs, Service Logs và Custom Logs.
2. Tạo log group/log object và cấu hình Spring Cloud Oracle Logging starter.
3. Dùng LogService để gửi custom log và biết giới hạn của API này.
4. Cấp IAM permission riêng cho writer, reader và logging administrator.
5. Thiết kế log có cấu trúc, correlation ID và quy tắc loại bỏ secret/PII.
6. Hiểu retention, search, archive, Connector Hub và chi phí ingestion.
7. Provision Email Domain, SPF, DKIM và Approved Sender theo region.
8. Tạo SMTP credential riêng, lưu secret và cấu hình Spring Mail.
9. Dùng MailSender/JavaMailSender để gửi text, HTML và attachment.
10. Xử lý bounce, suppression, quota, retry và email delivery status.
11. Tích hợp OCI Functions starter và gọi function qua Spring bean.
12. Phân biệt Sync với Detached invocation, timeout và result destination.
13. Cấp quyền fn-invocation theo từng application/function.
14. Thiết kế outbox, idempotency, timeout và observability cho ba tích hợp.
15. Viết unit/integration test và runbook xử lý lỗi.

~~~mermaid
flowchart TD
    A["Spring Boot document-service"] --> B["Application logging"]
    A --> C["Email notification service"]
    A --> D["Function invocation service"]
    B --> E["Spring Cloud OCI LogService"]
    E --> F["OCI Logging custom log"]
    F --> G["Search / alert / Connector Hub"]
    C --> H["Spring MailSender / JavaMailSender"]
    H --> I["OCI Email Delivery SMTP"]
    I --> J["Approved sender + SPF/DKIM"]
    J --> K["Recipient mail server"]
    D --> L["Spring Cloud OCI Function"]
    L --> M["OCI Functions invoke endpoint"]
    M --> N["Function application"]
    N --> O["Sync response or detached result"]
~~~

Ba dịch vụ có identity và quyền khác nhau. Workload identity của Spring Boot được OCI dùng để xác thực API Logging/Functions; Email Delivery SMTP dùng một SMTP username/password được Oracle sinh ra. Vì vậy, không thể dùng một credential duy nhất cho cả ba luồng.

## 2. Phân biệt ba dịch vụ và luồng dữ liệu

| Dịch vụ | Đầu vào | Đầu ra | Dùng cho |
| --- | --- | --- | --- |
| OCI Logging | Audit/service/custom log entries | Search, alert, archive, export | Chẩn đoán, vận hành và điều tra |
| OCI Email Delivery | SMTP message hoặc HTTPS submission | Hàng đợi gửi email, delivery/bounce/suppression logs | Email giao dịch và thông báo |
| OCI Functions | Signed invocation với function OCID và payload | Kết quả Sync hoặc trạng thái Detached | Xử lý độc lập, tác vụ theo sự kiện và serverless compute |

### 2.1. Logging không thay thế audit nghiệp vụ

OCI Audit service ghi nhận API call tới public endpoint của tenancy. OCI Service Logs ghi nhận hoạt động từ dịch vụ OCI hỗ trợ. Custom Logs nhận dữ liệu do ứng dụng hoặc agent gửi lên. Một log line trong Spring Boot không tự trở thành OCI Audit event.

Nếu cần chứng minh user nào đã tải một hợp đồng, hãy tạo application audit event ở tầng nghiệp vụ và nối nó với request ID/trace ID. Cloud Audit Logs có thể bổ sung principal OCI, operation và resource; hai nguồn có vai trò bổ sung nhau.

### 2.2. Email được chấp nhận chưa chắc đã được giao

SMTP server có thể trả thành công khi nhận message vào queue. Sau đó recipient mail server có thể từ chối, mailbox có thể bounce hoặc địa chỉ bị suppression. Cần theo dõi Email Delivery logs, bounce và suppression list; không đánh dấu nghiệp vụ là "đã nhận email" chỉ dựa trên SMTP send không lỗi.

### 2.3. Detached function không trả kết quả nghiệp vụ ngay

Sync invocation chờ function hoàn tất và trả response. Detached invocation trả về khi quá trình thực thi bắt đầu; function tiếp tục xử lý độc lập. Nếu ứng dụng cần biết kết quả cuối cùng, phải cấu hình success/failure destination hoặc một kênh trạng thái khác. HTTP 202 không có nghĩa tác vụ nghiệp vụ đã thành công.

## 3. OCI Logging: loại log, log group và log object

### 3.1. Ba loại log

OCI Logging cung cấp ba nhóm chính:

| Loại | Nguồn phát | Ví dụ |
| --- | --- | --- |
| Audit Logs | OCI Audit service | User tạo bucket, thay IAM policy, gọi API |
| Service Logs | OCI native services | API Gateway, Functions, Load Balancer, Object Storage, VCN Flow Logs |
| Custom Logs | Ứng dụng, agent hoặc nguồn ngoài | Spring Boot event, application diagnostics, log từ VM |

Các loại log được tổ chức và tìm kiếm qua Logging Search. Service log categories khác nhau theo từng dịch vụ; bật Object Storage read/write access logs không tự bật Functions logs.

### 3.2. Log group và log object

Một log group là container logic nằm trong compartment. Một log là tài nguyên riêng có OCID và nằm trong log group. Mỗi custom log hoặc service log phải được gắn vào log group.

Nên tổ chức log group theo mục đích và độ nhạy cảm, ví dụ:

~~~text
Compartment Observability
├── app-runtime-logs
│   ├── document-service-prod
│   └── document-worker-prod
├── security-logs
│   ├── privileged-access
│   └── sensitive-document-access
└── platform-service-logs
    ├── functions-invocation
    └── object-storage-access
~~~

Log group giúp áp dụng IAM policy theo nhóm dữ liệu. Có thể đặt log chứa PII trong log group riêng và chỉ cho security/auditor role được đọc. Không cần tạo một compartment mới cho mọi log category nếu log group đã tạo được ranh giới truy cập cần thiết.

### 3.3. Tạo custom log trước khi gửi

Luồng chuẩn:

1. Chọn compartment dành cho log.
2. Tạo log group.
3. Tạo custom log trong log group.
4. Lưu log OCID.
5. Cấp quyền push cho workload principal.
6. Cấu hình log OCID trong Spring Boot.
7. Gửi test event và xác minh trên Logging Search.

Spring Cloud Oracle Logging starter yêu cầu destination log ID qua property:

~~~yaml
spring:
  cloud:
    oci:
      logging:
        enabled: true
        logId: REPLACE_WITH_CUSTOM_LOG_OCID
~~~

Tên property dùng trong Spring Cloud Oracle là spring.cloud.oci.logging.logId. Log phải được tạo sẵn và nằm trong compartment mà principal có quyền ghi. Không dùng display name thay OCID.

### 3.4. Service Logs và Custom Logs

Để bật Service Logs, chọn resource tương ứng trong OCI Console, vào phần Logs và bật category cần thu thập. Một số resource mới có log được bật tự động theo mặc định hoặc cấu hình tạo resource; vẫn cần kiểm tra trạng thái thực tế.

Custom Logs có thể được gửi trực tiếp qua Logging Ingestion API hoặc Unified Monitoring Agent. Agent dựa trên Fluentd và chạy trên OCI Compute để thu thập log từ máy. Với container/Kubernetes, có thể dùng agent/collector phù hợp kiến trúc và route log tới custom log.

### 3.5. Encoding và nội dung

OCI Logging hỗ trợ UTF-8 text. Nếu muốn log có cấu trúc, ứng dụng có thể serialize JSON thành một chuỗi UTF-8 rồi gửi. Giữ schema ổn định để query theo timestamp, level, service, environment, traceId, eventType và outcome.

Không ghi vào log:

- Password, SMTP credential, OAuth token, private key hoặc wallet.
- Authorization header, cookie hoặc signed URL/PAR URL.
- Nội dung đầy đủ của hợp đồng, file upload hoặc request body nhạy cảm.
- Email/phone/định danh cá nhân đầy đủ nếu không cần.
- SQL bind parameter chứa dữ liệu cá nhân.
- Stack trace có connection string hoặc secret.

Dùng opaque identifier, reason code và field đã pseudonymize. Log archive cũng là dữ liệu nhạy cảm, cần IAM, retention và audit riêng.

## 4. Spring Cloud Oracle Logging starter

### 4.1. Dependency

Maven:

~~~xml
<dependency>
    <groupId>com.oracle.cloud.spring</groupId>
    <artifactId>spring-cloud-oci-starter-logging</artifactId>
</dependency>
~~~

Gradle:

~~~kotlin
dependencies {
    implementation("com.oracle.cloud.spring:spring-cloud-oci-starter-logging")
}
~~~

Quản lý version thông qua BOM/version catalog của Spring Cloud Oracle phù hợp với Spring Boot. Không trộn starter 2.0.4 với Spring Framework/Boot version không tương thích.

Release Spring Cloud Oracle 2.0.4 công bố nâng cấp lên Spring Boot 4.1.1. Nếu dự án đang dùng Spring Boot 3.x hoặc Java baseline khác, kiểm tra release notes và compatibility trước khi thêm starter; không ép dependency transitive về một version không được hỗ trợ.

### 4.2. Authentication và region

Starter dùng OCI Core authentication/configuration. Ví dụ trên OCI Compute:

~~~yaml
spring:
  cloud:
    oci:
      config:
        type: INSTANCE_PRINCIPAL
      region:
        static: ap-singapore-1
      logging:
        enabled: true
        logId: REPLACE_WITH_CUSTOM_LOG_OCID
~~~

Local development có thể dùng FILE profile:

~~~yaml
spring:
  cloud:
    oci:
      config:
        type: FILE
        profile: DEFAULT
        file: C:/Users/developer/.oci/config
      region:
        static: ap-singapore-1
      logging:
        enabled: true
        logId: REPLACE_WITH_TEST_LOG_OCID
~~~

Trên OKE enhanced cluster, có thể chọn WORKLOAD_IDENTITY nếu starter/SDK version và cluster hỗ trợ. Không tự fallback từ instance/workload identity sang API key nếu authentication thất bại; điều đó có thể che giấu lỗi policy và làm workload dùng một danh tính mạnh hơn dự kiến.

### 4.3. LogService bean

Starter tự cấu hình bean LogService. API cơ bản theo tài liệu Spring Cloud Oracle:

~~~java
import com.oracle.cloud.spring.logging.LogService;
import org.springframework.stereotype.Service;

@Service
public class OciLogPublisher {

    private final LogService logService;

    public OciLogPublisher(LogService logService) {
        this.logService = logService;
    }

    public void publish(String logText) {
        logService.putLog(logText);
    }
}
~~~

putLog nhận chuỗi log và trả PutLogsResponse. Ví dụ tối giản trên bỏ qua response; production nên xử lý exception, metric và backpressure theo yêu cầu độ tin cậy.

### 4.4. Gửi structured JSON log

LogService API cơ bản nhận chuỗi. Có thể serialize một record thành JSON:

~~~java
import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.oracle.cloud.spring.logging.LogService;
import java.time.Instant;
import org.springframework.stereotype.Service;

public record ApplicationLogEvent(
        Instant timestamp,
        String level,
        String service,
        String environment,
        String eventType,
        String traceId,
        String requestId,
        String outcome,
        String message) {
}

@Service
public class StructuredOciLogPublisher {

    private final LogService logService;
    private final ObjectMapper objectMapper;

    public StructuredOciLogPublisher(
            LogService logService,
            ObjectMapper objectMapper) {
        this.logService = logService;
        this.objectMapper = objectMapper;
    }

    public void publish(ApplicationLogEvent event)
            throws JsonProcessingException {
        String json = objectMapper.writeValueAsString(event);
        logService.putLog(json);
    }
}
~~~

Record trên chỉ chứa metadata cần thiết. Không đưa raw user input hoặc payload nhạy cảm vào message. Có thể bổ sung exception class/code, nhưng cần redact stack trace và tránh lộ secret.

### 4.5. Logging starter không tự thu mọi SLF4J event

LogService là API tường minh để gửi log. Chỉ thêm starter không có nghĩa mọi lệnh logger.info/logger.error của ứng dụng tự động được đẩy lên OCI Logging.

Có hai hướng:

- Gọi LogService ở những điểm cần gửi custom event cụ thể.
- Giữ logging backend/SLF4J ghi stdout hoặc file, sau đó dùng Unified Monitoring Agent/collector để chuyển log vào OCI Logging.

Không gọi Logging API đồng bộ cho mọi dòng debug trong hot path nếu lưu lượng lớn. Với volume cao, dùng batch ingestion, agent hoặc pipeline bất đồng bộ. Cần xác định queue capacity, retry, drop policy và cảnh báo khi sink không khả dụng.

### 4.6. Quyền IAM cho Logging

Principal ghi custom log cần quyền trên log-content trong compartment chứa log:

~~~text
Allow dynamic-group DocumentService to use log-content in compartment Observability
~~~

Nhóm đọc log cần quyền đọc nội dung và metadata:

~~~text
Allow group LogReaders to read log-content in compartment Observability
Allow group LogReaders to read log-groups in compartment Observability
~~~

Nhóm quản trị log group/log object có thể cần:

~~~text
Allow group LoggingAdmins to manage log-groups in compartment Observability
~~~

Không cấp manage log-groups cho application runtime chỉ để gửi log. Nếu log group/log object đã được provision, workload chỉ cần quyền push log-content. Tùy policy scope, có thể giới hạn quyền vào log group cụ thể bằng target.loggroup.id.

### 4.7. Search và query

Log có thể tìm kiếm qua Console, API và CLI. Khi debug, lọc theo:

- Timestamp/time range.
- Service/environment.
- Log group/log OCID.
- Trace ID/request ID.
- Event type và outcome.
- OCI principal/resource nếu là service/audit log.

Dùng correlation ID xuyên các log và function invocation để nối một request từ API tới database, Object Storage, Email Delivery và Functions.

## 5. Retention, archive và chi phí Logging

### 5.1. Retention

Retention của một log có thể đặt theo bậc 30 ngày, tối đa 180 ngày. Khi giảm retention từ sáu tháng xuống một tháng, dữ liệu cũ hơn một tháng không còn searchable trong log đó. Hãy kiểm tra retention trước khi thay đổi.

Nếu yêu cầu điều tra/compliance vượt 180 ngày, đừng coi Logging Search là kho lưu trữ dài hạn duy nhất.

### 5.2. Connector Hub archive

Connector Hub có thể chuyển log sang Object Storage để archive, hoặc gửi tới Streaming/đích khác được hỗ trợ. Ví dụ:

~~~mermaid
flowchart LR
    A["OCI Logging"] --> B["Connector Hub"]
    B --> C["Object Storage archive"]
    B --> D["OCI Streaming"]
    B --> E["Monitoring / downstream processor"]
~~~

Object Storage archive cần lifecycle, encryption, IAM và retention riêng. Nếu dùng immutable bucket, thiết kế legal hold và thời gian giữ trước khi khóa policy.

### 5.3. Chi phí và volume

Chi phí/usage phụ thuộc lượng byte ingest, lưu trữ, truy vấn và dịch vụ liên quan. Kiểm soát bằng cách:

- Chỉ bật service log categories thực sự cần.
- Không log request/response body lớn.
- Chọn level phù hợp theo môi trường.
- Sampling debug/trace ở tải cao.
- Không ghi cùng một event ở nhiều lớp nếu không có mục đích.
- Dùng log group theo phân loại để quản lý retention/access.
- Đặt alert khi bytes ingested tăng bất thường.
- Archive log cũ thay vì kéo dài retention search cho mọi log.

## 6. OCI Email Delivery: kiến trúc và chuẩn bị

### 6.1. SMTP và HTTPS submission

OCI Email Delivery hỗ trợ gửi email qua SMTP hoặc HTTPS API. Spring Cloud Oracle Email starter tích hợp với Spring Mail qua SMTP, cung cấp MailSender và JavaMailSender.

SMTP phù hợp khi ứng dụng đã dùng JavaMail/Spring Mail. HTTPS submission phù hợp khi muốn gọi Email Delivery API trực tiếp bằng OCI SDK/authentication. Không nhầm Email Delivery với OCI Notifications: Notifications phù hợp publish message tới topic/subscriber, còn Email Delivery phục vụ email giao dịch/marketing.

### 6.2. Các bước provision

Trước khi gửi email:

1. Tạo IAM user riêng cho SMTP sender.
2. Tạo group/policy cho Email Delivery.
3. Tạo SMTP credentials cho user.
4. Tạo Email Domain cho domain do tổ chức sở hữu.
5. Cấu hình SPF trong DNS.
6. Cấu hình DKIM và publish record được OCI sinh.
7. Tạo Approved Sender trong region gửi.
8. Lấy SMTP endpoint/port của region.
9. Cấu hình TLS và secret trong Spring Boot.
10. Gửi test email tới địa chỉ kiểm soát và kiểm tra delivery log.

Domain gửi phải do tổ chức sở hữu/kiểm soát DNS. Không dùng Gmail, Yahoo, Hotmail hoặc domain mailbox public làm sender domain cho Email Delivery.

### 6.3. Approved Sender

Mọi địa chỉ trong From header gửi qua OCI Email Delivery phải là Approved Sender; nếu không, message bị từ chối. Approved Sender:

- Gắn với compartment.
- Chỉ tồn tại ở region tạo sender.
- Phải tạo riêng ở mỗi region mà ứng dụng gửi email.
- Nên được tạo trong compartment ứng dụng/email, không tạo trong root compartment.
- Nên khớp địa chỉ SMTP envelope From với header From.

Nếu gửi nhiều địa chỉ trong From header, DMARC alignment và xác minh sender có thể phức tạp hơn. Dùng một địa chỉ From đã approved cho mỗi loại email.

### 6.4. Approved domain

Sau khi DKIM của Email Domain đã active, có thể tạo approved sender dạng @domain.com để bao phủ các địa chỉ cùng domain theo khả năng dịch vụ. DKIM key chỉ ký sender có domain khớp chính xác, bao gồm subdomain. Ví dụ key cho sub.example.com không tự ký sender ở example.com.

### 6.5. SPF

SPF là TXT record cho phép mail receiver kiểm tra hạ tầng nào được gửi thay mặt domain. Với Asia/Pacific commercial regions, record mẫu OCI công bố:

~~~text
v=spf1 include:ap.rp.oracleemaildelivery.com ~all
~~~

Với Americas và Europe, include domain khác. Chọn đúng giá trị theo sending region trong OCI Console/tài liệu. Nếu domain đã có SPF, hợp nhất include vào một TXT SPF record hợp lệ; không tạo nhiều SPF record độc lập cho cùng domain.

### 6.6. DKIM

DKIM ký email bằng private key và công bố public key qua DNS. OCI tạo selector và record CNAME (hoặc loại record theo realm), sau đó domain owner thêm record vào DNS provider đang quản lý nameserver.

- Chỉ tạo DKIM cho domain tổ chức kiểm soát.
- Kiểm tra record được publish ở đúng selector._domainkey.
- Chờ DNS propagation và dùng chức năng verification của OCI.
- Email Delivery hỗ trợ tối đa hai DKIM keys cho một email domain, nhưng chỉ một key active tại một thời điểm.
- Oracle khuyến nghị rotate DKIM key định kỳ, tài liệu hiện hành nêu chu kỳ sáu tháng.

SPF/DKIM giúp xác thực sender và cải thiện deliverability; DMARC giúp domain owner xác định chính sách xử lý email không đạt alignment. Cấu hình DMARC theo chính sách domain của tổ chức.

## 7. SMTP credentials, IAM và regional endpoint

### 7.1. SMTP credentials

SMTP credentials là cặp username/password do Oracle sinh ra. Không thể tự đặt giá trị. Một IAM user có tối đa hai SMTP credential cùng lúc; credential không tự hết hạn.

Thực hành tốt:

- Tạo IAM user riêng chỉ phục vụ SMTP.
- Không dùng credential Console/admin của developer.
- Lưu username/password trong OCI Vault hoặc secret manager.
- Không commit vào application.yml, Docker image hoặc CI log.
- Rotate bằng cách tạo credential thứ hai, cập nhật ứng dụng, xác minh gửi được rồi xóa credential cũ.
- Nếu user có hai credential đang hoạt động, phải xóa một credential trước khi tạo thêm.
- Không để SMTP password trong exception/log/metrics.

### 7.2. IAM policy

Principal gửi email cần quyền sử dụng Approved Sender trong compartment:

~~~text
Allow group EmailSenders to use approved-senders in compartment EmailDelivery
~~~

Nhóm quản trị sender có thể cần quyền quản lý Approved Sender:

~~~text
Allow group EmailAdmins to manage approved-senders in compartment EmailDelivery
~~~

Quản lý suppression list có scope tenancy theo chính sách dịch vụ:

~~~text
Allow group EmailAdmins to manage suppressions in tenancy
~~~

Tách EmailSenders khỏi EmailAdmins. Runtime service chỉ gửi mail; nó không cần tạo/xóa sender hoặc chỉnh suppression list. Tài liệu OCI có policy template riêng cho credential SMTP và email-family; xác minh policy chính xác theo identity domain/compartment đang dùng.

### 7.3. SMTP credential global, sender regional

SMTP credentials gắn với IAM user và có thể dùng ở nhiều region. Approved Sender và suppression list là tài nguyên regional. Khi mở region mới:

1. Tạo Approved Sender ở region mới.
2. Kiểm tra SPF/DKIM cho domain và region.
3. Dùng SMTP endpoint của region đó.
4. Xem xét tạo SMTP user riêng theo region để tách quyền/credential.
5. Kiểm tra suppression list và delivery logs ở region tương ứng.

Không dùng endpoint Phoenix với Approved Sender chỉ được tạo ở Singapore.

### 7.4. SMTP endpoint và TLS

SMTP endpoint có dạng theo region, ví dụ:

~~~text
smtp.email.ap-singapore-1.oci.oraclecloud.com
~~~

OCI hỗ trợ các port SMTP 25, 587 và 465. Port 465 dùng TLS ngay khi bắt đầu kết nối (implicit TLS). Port 587 thường dùng STARTTLS; port 25 cũng có thể được hỗ trợ tùy network path. Ưu tiên TLS và dùng endpoint/port được hiển thị trong trang Configuration của region.

Ví dụ cấu hình port 465:

~~~yaml
spring:
  mail:
    host: smtp.email.ap-singapore-1.oci.oraclecloud.com
    port: 465
    username: SMTP_USERNAME_FROM_SECRET
    password: SMTP_PASSWORD_FROM_SECRET
    properties:
      mail:
        smtp:
          auth: true
          ssl:
            enable: true
            checkserveridentity: true
          starttls:
            enable: false
          connectiontimeout: 5000
          timeout: 10000
          writetimeout: 10000
~~~

Nếu chọn port 587, bật STARTTLS và yêu cầu TLS:

~~~yaml
spring:
  mail:
    port: 587
    properties:
      mail:
        smtp:
          auth: true
          ssl:
            enable: false
          starttls:
            enable: true
            required: true
~~~

Không bật implicit SSL và STARTTLS cùng lúc. Không tắt certificate/hostname verification để chữa lỗi TLS; kiểm tra JavaMail version, JDK trust store, endpoint và cấu hình TLS.

## 8. Spring Cloud Oracle Email Delivery starter

### 8.1. Dependency

Maven:

~~~xml
<dependency>
    <groupId>com.oracle.cloud.spring</groupId>
    <artifactId>spring-cloud-oci-starter-email</artifactId>
</dependency>
~~~

Gradle:

~~~kotlin
dependencies {
    implementation("com.oracle.cloud.spring:spring-cloud-oci-starter-email")
}
~~~

Starter cung cấp tích hợp Spring Mail. Cấu hình SMTP theo chuẩn Spring Boot và sử dụng endpoint/credential của OCI Email Delivery.

### 8.2. MailSender

Starter auto-configures MailSender với qualifier ociMailSender. Ví dụ:

~~~java
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.mail.MailSender;
import org.springframework.mail.SimpleMailMessage;
import org.springframework.stereotype.Service;

@Service
public class ContractEmailService {

    private final MailSender mailSender;

    public ContractEmailService(
            @Qualifier("ociMailSender") MailSender mailSender) {
        this.mailSender = mailSender;
    }

    public void sendStatus(
            String from,
            String recipient,
            String subject,
            String text) {

        SimpleMailMessage message = new SimpleMailMessage();
        message.setFrom(from);
        message.setTo(recipient);
        message.setSubject(subject);
        message.setText(text);

        mailSender.send(message);
    }
}
~~~

From phải là Approved Sender của region. Recipient phải được validate theo nghiệp vụ và consent/policy. Không nhận From tùy ý từ request body để tránh open relay hoặc spoofing.

### 8.3. JavaMailSender cho HTML và attachment

Starter cũng cung cấp JavaMailSender với qualifier ociJavaMailSender. Dùng khi cần MIME multipart, HTML hoặc attachment:

~~~java
import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.core.io.ByteArrayResource;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;
import org.springframework.stereotype.Service;

@Service
public class RichEmailService {

    private final JavaMailSender mailSender;

    public RichEmailService(
            @Qualifier("ociJavaMailSender") JavaMailSender mailSender) {
        this.mailSender = mailSender;
    }

    public void sendHtml(
            String from,
            String recipient,
            String subject,
            String html) throws MessagingException {

        MimeMessage message = mailSender.createMimeMessage();
        MimeMessageHelper helper =
                new MimeMessageHelper(message, true, "UTF-8");

        helper.setFrom(from);
        helper.setTo(recipient);
        helper.setSubject(subject);
        helper.setText(html, true);

        mailSender.send(message);
    }

    public void sendAttachment(
            String from,
            String recipient,
            String subject,
            String text,
            byte[] fileBytes,
            String safeFileName) throws MessagingException {

        MimeMessage message = mailSender.createMimeMessage();
        MimeMessageHelper helper =
                new MimeMessageHelper(message, true, "UTF-8");

        helper.setFrom(from);
        helper.setTo(recipient);
        helper.setSubject(subject);
        helper.setText(text, false);
        helper.addAttachment(
                safeFileName,
                new ByteArrayResource(fileBytes),
                "application/pdf");

        mailSender.send(message);
    }
}
~~~

Ví dụ attachment dùng byte[] nên chỉ phù hợp file nhỏ. OCI Email Delivery giới hạn message size theo tổng message sau Base64 encoding và headers; giới hạn hiện hành là 2 MB. Với file lớn, nên lưu trong Object Storage và gửi link có thời hạn đã được kiểm soát thay vì attach.

### 8.4. Template email

Không ghép HTML từ input tùy ý. Dùng template engine, escape biến và kiểm soát link. Với email giao dịch, nên có:

- Subject rõ ràng.
- From đã approved.
- Recipient đã xác minh.
- Plain-text fallback nếu gửi HTML.
- Request/correlation ID không nhạy cảm.
- Link dẫn tới ứng dụng với quyền xác thực.
- Thông tin hỗ trợ hoặc unsubscribe nếu email thuộc loại cần.
- Nội dung không tiết lộ hợp đồng hoặc dữ liệu nhạy cảm nếu gửi nhầm người.

### 8.5. Email không nằm trong database transaction

Không gọi SMTP trong khi giữ transaction database mở. Nếu database commit nhưng SMTP timeout, ứng dụng không biết email đã được nhận hay chưa. Nếu SMTP thành công nhưng transaction rollback, người nhận có thể nhận thông báo cho một thay đổi không tồn tại.

Dùng transactional outbox:

1. Trong transaction nghiệp vụ, cập nhật dữ liệu và ghi notification outbox.
2. Worker đọc outbox sau commit.
3. Worker gửi email.
4. Lưu trạng thái ACCEPTED/FAILED/RETRYING cùng message ID nếu có.
5. Retry lỗi transient theo backoff.
6. Đưa lỗi vĩnh viễn vào trạng thái cần xử lý thủ công.

SMTP không cung cấp exactly-once delivery ở tầng ứng dụng. Gửi lại sau timeout có thể tạo duplicate. Dùng notification ID, idempotency và template phù hợp để giảm tác động của duplicate.

## 9. Suppression, bounce và deliverability

### 9.1. Suppression list

OCI Email Delivery duy trì suppression list theo region. Địa chỉ bị hard bounce hoặc complaint có thể bị đưa vào suppression để bảo vệ sender reputation. Không cố gửi lặp lại tới địa chỉ đã bị suppress.

Quy trình:

- Kiểm tra suppression trước chiến dịch gửi hàng loạt nếu cần.
- Xử lý bounce/complaint từ logs hoặc event.
- Cập nhật trạng thái email trong application database.
- Cho phép thao tác gỡ suppression chỉ qua role có trách nhiệm.
- Không tự động xóa suppression để ép gửi lại.
- Kiểm tra suppression list đúng region đang gửi.

### 9.2. SMTP response quan trọng

| SMTP code | Ý nghĩa thường gặp | Hướng xử lý |
| --- | --- | --- |
| 421 | Timeout, quá nhiều kết nối hoặc auth failures | Backoff, kiểm tra credential và concurrency |
| 455 | Vượt send rate/day quota | Queue, throttle, xin tăng quota nếu có căn cứ |
| 535 | Credential sai hoặc sender không được authorize | Kiểm tra SMTP credential, IAM và Approved Sender |
| 553 | Email address không hợp lệ | Validate recipient |
| 554 | Message format lỗi | Kiểm tra MIME/header/content |
| 552 | Message vượt byte limit | Giảm attachment hoặc gửi link |

Một SMTP response thành công chỉ xác nhận service đã nhận message để xử lý. Kiểm tra Email Delivery logs và delivery status để xác định kết quả cuối.

### 9.3. Sender reputation

- Dùng domain riêng và xác minh SPF/DKIM.
- Cấu hình DMARC theo policy domain.
- Không gửi tới danh sách mua hoặc địa chỉ không có consent.
- Xử lý hard bounce và complaint nhanh.
- Không gửi nhiều From address khác domain.
- Tăng volume dần khi mới triển khai sender.
- Theo dõi quota và suppression.
- Không retry hard bounce hoặc địa chỉ bị suppress.

## 10. OCI Functions và invocation model

### 10.1. Function application và function

OCI Functions là nền tảng Functions-as-a-Service. Một Function được triển khai trong Functions Application, chạy trên OCI Functions infrastructure và có invoke endpoint.

Spring Boot có thể gọi function để:

- Tạo thumbnail sau khi upload document.
- Quét file hoặc kiểm tra định dạng.
- Render PDF/report.
- Chuyển đổi dữ liệu.
- Chạy một tác vụ độc lập không cần giữ thread HTTP của API chính.
- Thực hiện xử lý theo sự kiện hoặc lịch.

Function không phải một method nội bộ của Spring. Invocation đi qua OCI API, cần identity/signature, function OCID, endpoint và IAM permission.

### 10.2. Sync và Detached

| Kiểu invocation | Hành vi | HTTP response | Dùng khi |
| --- | --- | --- | --- |
| Sync | Caller chờ function hoàn tất | 200 khi thành công | Kết quả nhanh cần trả ngay |
| Detached | Caller trả về khi function bắt đầu; function tiếp tục chạy | 202 | Tác vụ dài hoặc xử lý nền |

Sync invocation phụ thuộc read timeout của client và function execution timeout. Detached invocation dùng detachedModeTimeoutInSeconds riêng, có thể cấu hình từ 5 giây tới 3600 giây theo tài liệu hiện hành.

Detached invocation có thể cấu hình success destination và failure destination tới Notifications, Queue hoặc Streaming. Khi đó OCI Functions gửi invocation record tới destination tương ứng sau khi chạy xong.

### 10.3. Function endpoint

Mỗi function có invoke endpoint. Khi dùng OCI SDK, client dùng phần base endpoint, ví dụ:

~~~text
https://<function-endpoint-id>.<region>.functions.oci.oraclecloud.com
~~~

Không truyền toàn bộ path /20181201/functions/<function-ocid>/actions/invoke vào SDK client nếu API yêu cầu base endpoint. SDK sẽ ghép function OCID và resource path.

Nếu gửi signed HTTP request thủ công, request phải có signature và compartment OCID theo OCI request signing. Dùng OCI SDK/Spring starter giúp tránh tự triển khai request signer.

Fn Project CLI hữu ích cho phát triển và thử nghiệm tại terminal, nhưng Oracle không khuyến nghị dùng nó làm cơ chế invoke production. Trong ứng dụng Spring Boot production, dùng OCI SDK/Spring starter hoặc OCI CLI/API có identity và policy được quản lý.

## 11. Spring Cloud Oracle Functions starter

### 11.1. Dependency

Maven:

~~~xml
<dependency>
    <groupId>com.oracle.cloud.spring</groupId>
    <artifactId>spring-cloud-oci-starter-function</artifactId>
</dependency>
~~~

Gradle:

~~~kotlin
dependencies {
    implementation("com.oracle.cloud.spring:spring-cloud-oci-starter-function")
}
~~~

Starter auto-configures bean Function để gọi OCI Functions. Property spring.cloud.oci.function.enabled điều khiển việc bật module; mặc định true.

### 11.2. Authentication và region

Ví dụ workload chạy trên Compute:

~~~yaml
spring:
  cloud:
    oci:
      config:
        type: INSTANCE_PRINCIPAL
      region:
        static: ap-singapore-1
      function:
        enabled: true
~~~

Local development có thể dùng FILE profile. Production nên dùng instance principal hoặc OKE workload identity phù hợp runtime. Không lưu API private key trong image chỉ để gọi function.

### 11.3. Invoke Sync từ Spring Boot

Spring Cloud Oracle Function bean có method invokeFunction nhận function OCID, base endpoint, invocation mode và request body InputStream.

~~~java
import com.oracle.bmc.functions.requests.InvokeFunctionRequest;
import com.oracle.bmc.functions.responses.InvokeFunctionResponse;
import com.oracle.cloud.spring.function.Function;
import java.io.ByteArrayInputStream;
import java.io.InputStream;
import org.springframework.stereotype.Service;

@Service
public class ThumbnailFunctionInvoker {

    private final Function function;

    public ThumbnailFunctionInvoker(Function function) {
        this.function = function;
    }

    public InvokeFunctionResponse createThumbnail(
            String functionOcid,
            String functionBaseEndpoint,
            byte[] jsonPayload) {

        try (InputStream body =
                     new ByteArrayInputStream(jsonPayload)) {

            return function.invokeFunction(
                    functionOcid,
                    functionBaseEndpoint,
                    InvokeFunctionRequest.FnInvokeType.Sync,
                    body);
        } catch (java.io.IOException exception) {
            throw new java.io.UncheckedIOException(exception);
        }
    }
}
~~~

Payload nên là JSON có schema version, event ID, document ID, object key reference, tenant reference đã xác minh và trace/correlation ID. Không gửi password, wallet, SMTP credential hoặc nội dung file lớn qua invocation body nếu có thể truyền object reference.

### 11.4. Invoke Detached

Với tác vụ dài, có thể dùng mode Detached:

~~~java
public InvokeFunctionResponse startBackgroundScan(
        String functionOcid,
        String functionBaseEndpoint,
        byte[] jsonPayload) {

    try (InputStream body =
                 new ByteArrayInputStream(jsonPayload)) {

        return function.invokeFunction(
                functionOcid,
                functionBaseEndpoint,
                InvokeFunctionRequest.FnInvokeType.Detached,
                body);
    } catch (java.io.IOException exception) {
        throw new java.io.UncheckedIOException(exception);
    }
}
~~~

Khi nhận response 202, lưu invocation/request reference và trạng thái PENDING. Kết quả cuối cần được function gửi tới Queue/Streaming/Notifications destination hoặc cập nhật vào một datastore mà ứng dụng theo dõi. Không đánh dấu document là SCANNED chỉ vì invocation trả 202.

### 11.5. IAM policy chỉ cho invoke function cụ thể

Resource type fn-invocation cho phép gọi function. Ví dụ cấp cho dynamic group của document-service quyền gọi đúng một function:

~~~text
Allow dynamic-group DocumentService to use fn-invocation in compartment AppFunctions
where target.function.id = '<FUNCTION_OCID>'
~~~

Có thể giới hạn theo application:

~~~text
Allow dynamic-group DocumentService to use fn-invocation in compartment AppFunctions
where target.app.id = '<FUNCTION_APPLICATION_OCID>'
~~~

Không cấp manage functions-family cho runtime workload nếu chỉ cần invoke. Policy manage functions-family có thể bao gồm cả quyền quản lý và invoke. Tách deployer khỏi invoker:

~~~text
Allow group FunctionDeployers to manage fn-app in compartment AppFunctions
Allow group FunctionDeployers to manage fn-function in compartment AppFunctions
~~~

Các statement quản lý riêng này không tự cấp quyền invoke. Cấp fn-invocation riêng cho principal thực sự cần gọi.

### 11.6. Private subnet không thay IAM

Đặt Function Application trong private subnet không tự ngăn truy cập internet tới invoke endpoint. Hãy kiểm soát ai được invoke bằng IAM policy và điều kiện phù hợp. Network placement, route và IAM authorization là hai lớp riêng.

### 11.7. Detached success/failure destinations

Nếu function chạy detached và gửi invocation result tới Queue, Notifications hoặc Streaming, OCI Functions cần quyền ghi destination. Policy mẫu cho Queue:

~~~text
Allow any-user to use queues in compartment Processing
where all {
  request.principal.type = 'fnapp',
  target.queue.id = '<QUEUE_OCID>',
  request.principal.compartment.id = '<FUNCTION_APP_COMPARTMENT_OCID>'
}
~~~

Policy tương tự có thể dùng cho ONS topic hoặc stream với resource type và target ID tương ứng. Chỉ cấp quyền ghi đúng destination, không mở quyền trên toàn compartment nếu không cần.

## 12. Thiết kế workflow kết hợp Logging, Email và Functions

### 12.1. Luồng document-service

Ví dụ sau khi người dùng upload hợp đồng:

1. API xác thực user và tenant.
2. Lưu metadata/document state trong database.
3. Lưu object vào Object Storage.
4. Ghi outbox event trong cùng transaction database.
5. Worker publish log/metric và gọi function tạo thumbnail hoặc scan.
6. Function trả kết quả hoặc gửi detached invocation record tới Queue.
7. Worker cập nhật trạng thái xử lý.
8. Notification worker gửi email cho người dùng.
9. Log các bước với cùng trace ID và event ID.

~~~mermaid
sequenceDiagram
    participant API as Spring Boot API
    participant DB as Autonomous Database
    participant OS as Object Storage
    participant Q as Queue / Outbox Worker
    participant FN as OCI Functions
    participant LOG as OCI Logging
    participant MAIL as Email Delivery

    API->>OS: Upload contract
    API->>DB: Save document + outbox
    DB-->>API: Commit
    API->>LOG: Log accepted event
    Q->>FN: Invoke scan/thumbnail
    FN-->>Q: Result or detached status
    Q->>DB: Update document state
    Q->>MAIL: Send status email
    MAIL-->>Q: SMTP accepted/rejected
    Q->>LOG: Log outcome and correlation ID
~~~

### 12.2. Correlation và idempotency

Dùng các identifier:

- requestId: một HTTP request.
- traceId: distributed trace qua service.
- eventId: sự kiện nghiệp vụ duy nhất.
- functionInvocationId/requestId: tham chiếu invocation.
- notificationId: một email notification cụ thể.

Không dùng email address hoặc document content làm correlation ID. Khi retry function hoặc email, dùng cùng event/notification ID để deduplicate ở database và tránh tạo nhiều kết quả nghiệp vụ.

### 12.3. Outbox cho email và function invocation

Không gọi Email Delivery hoặc Functions trước khi transaction nghiệp vụ commit nếu operation phụ thuộc dữ liệu vừa ghi. Outbox đảm bảo ý định gửi notification/invoke function được lưu cùng transaction.

Worker có thể retry khi gặp timeout. Tuy nhiên timeout không chứng minh request chưa được nhận. Trước khi retry, dùng idempotency key hoặc kiểm tra trạng thái event. Function cần xử lý idempotent vì caller có thể gửi lại cùng event.

### 12.4. Phân loại lỗi và retry

| Lỗi | Logging | Email | Functions |
| --- | --- | --- | --- |
| 401/403 | Kiểm tra principal/policy, không retry vô hạn | Kiểm tra SMTP credential/approved sender | Kiểm tra fn-invocation permission |
| 429/quota | Giảm ingestion hoặc batch | Queue và throttle theo quota | Backoff nếu service trả throttling |
| Timeout | Kiểm tra sink, tránh mất event quan trọng | Có thể SMTP đã nhận; kiểm tra delivery log trước retry | Invocation có thể đã bắt đầu; dùng idempotency |
| 5xx/transient | Retry có giới hạn | Retry với backoff/jitter | Retry có giới hạn, kiểm tra SDK policy |
| Payload invalid | Sửa schema/encoding | Sửa MIME/header/recipient | Sửa function input contract |
| Permanent reject | Không retry payload lỗi | Xử lý bounce/suppression | Đưa event vào failure path/DLQ |

Không retry 401/403 như lỗi mạng. Retry có exponential backoff và jitter; giới hạn số lần thử, ghi attempt count và chuyển lỗi lâu dài sang DLQ/manual review.

## 13. Security, secrets và dữ liệu nhạy cảm

### 13.1. Tách credential theo dịch vụ

| Credential/identity | Dùng cho | Nơi lưu |
| --- | --- | --- |
| OCI workload identity | Logging API và Functions invoke | OCI runtime identity, không lưu private key dài hạn |
| SMTP username/password | Email Delivery SMTP | OCI Vault/secret manager |
| Log OCID | Chọn destination log | Application configuration |
| Function OCID/base endpoint | Chọn function đích | Application configuration |
| Approved Sender | From identity | OCI Email Delivery configuration |

Không dùng một IAM user admin để tạo log, gửi email và invoke function. Tách principal/permission theo service.

### 13.2. Email security

- SMTP credential chỉ có quyền gửi trong phạm vi sender cần thiết.
- Không log SMTP AUTH username/password.
- Dùng TLS và xác minh certificate.
- Approved Sender phải thuộc domain do tổ chức kiểm soát.
- Không nhận From từ người dùng cuối.
- Không đưa secret hoặc PII vào subject/body không cần thiết.
- Hạn chế attachment và dùng link có thời hạn cho file lớn.
- Xử lý suppression list để không gửi lại địa chỉ hard bounce/complaint.

### 13.3. Function security

- Cấp fn-invocation cho đúng function/application.
- Validate payload và schema version.
- Không tin tenant ID hoặc object key nếu không xác minh quyền ở caller/function.
- Dùng resource principal/workload identity bên trong function để truy cập OCI resources.
- Cấp policy cho function runtime riêng với caller.
- Không ghi payload nhạy cảm vào Function logs.
- Đặt timeout/memory/concurrency phù hợp và giới hạn egress khi cần.

### 13.4. Logging security

- Tách writer và reader.
- Dùng log group riêng cho dữ liệu nhạy cảm.
- Redact secret trước khi gọi LogService.
- Hạn chế quyền export/search.
- Thiết lập retention và archive theo phân loại dữ liệu.
- Audit ai thay đổi log destination/retention.
- Không coi custom application log là audit evidence bất biến nếu chưa có kiểm soát bổ sung.

## 14. Observability và vận hành

### 14.1. Logging metrics

Theo dõi:

- Bytes ingested.
- Số log events và lỗi gửi.
- Thời gian từ event tới khi searchable.
- Log search success.
- Queue backlog nếu dùng async logging.
- Archive/export failure.
- Retention và storage usage.

### 14.2. Email metrics

Theo dõi:

- Số email accepted/sent theo region.
- SMTP 4xx/5xx.
- Bounce và complaint.
- Suppression count.
- Quota/day và send rate.
- TLS/auth failures.
- Thời gian gửi và delivery status.

Không ghi địa chỉ email đầy đủ trong metric labels. Dùng domain hoặc recipient hash/pseudonymous ID nếu cần phân tích.

### 14.3. Functions metrics

Theo dõi:

- Invocation count theo function.
- Sync success/error/timeout.
- Detached accepted/completed/failed.
- Execution duration.
- Cold start và resource utilization.
- Retry count và duplicate event.
- Success/failure destination delivery.
- Queue backlog hoặc event age.

### 14.4. Runbook và lifecycle

Ghi rõ owner cho:

- Tạo log group/log OCID và retention.
- Thay IAM policy.
- Rotate SMTP credentials.
- Thay Approved Sender/SPF/DKIM.
- Mở region gửi email mới.
- Deploy function và đổi OCID/endpoint.
- Điều chỉnh detached timeout/destination.
- Xử lý bounce/suppression và DLQ.

Không lưu log OCID/Function OCID/SMTP username cùng raw secret trong tài liệu vận hành công khai.

## 15. Troubleshooting lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| LogService 404/NotFound | Sai log OCID hoặc log chưa được tạo | Kiểm tra logId, region và log group |
| LogService 403 | Principal thiếu use log-content hoặc sai compartment | Kiểm tra workload identity và policy |
| Log gửi thành công nhưng không tìm thấy | Sai log destination, thời gian ingest hoặc query filter | Kiểm tra log OCID, timestamp và Logging Search |
| Log không có JSON field | Payload gửi là text không phải JSON hợp lệ | Kiểm tra serializer và UTF-8 |
| Logging chi phí tăng | Debug volume lớn hoặc duplicate event | Giảm log level, sampling và batch |
| SMTP 535 | SMTP credential sai hoặc không được authorize | Rotate credential, kiểm tra IAM và Approved Sender |
| SMTP 535 address not authorized | From chưa approved hoặc policy thiếu | Kiểm tra sender theo region và use approved-senders |
| SMTP 421 | Timeout, quá nhiều connection/auth failures | Giảm concurrency, sửa credential, backoff |
| SMTP 455 | Vượt quota gửi | Throttle, queue và kiểm tra limit hiện tại |
| SMTP 552 | Message vượt size limit | Giảm attachment hoặc gửi link |
| Email accepted nhưng không vào inbox | Bounce, suppression, SPF/DKIM/DMARC hoặc recipient policy | Kiểm tra Email Delivery logs và suppression |
| DKIM inactive | CNAME sai selector/zone hoặc DNS chưa propagate | Kiểm tra DNS record đúng tên/value |
| Email sender hợp lệ ở region A nhưng bị từ chối ở B | Approved Sender là regional | Tạo sender ở region B |
| Function 404 | Sai function OCID hoặc endpoint | Dùng function base endpoint đúng region |
| Function 401/403 | Request signature/identity hoặc fn-invocation policy thiếu | Kiểm tra OCI auth và IAM |
| Function Sync timeout | Function chạy lâu hoặc client read timeout thấp | Dùng Detached hoặc điều chỉnh timeout |
| Detached trả 202 nhưng không có kết quả | Chưa cấu hình destination hoặc function không publish state | Kiểm tra success/failure destination và function logs |
| Function gọi được nhưng truy cập storage thất bại | Function runtime thiếu policy resource principal | Cấp quyền cho principal của Function |
| Duplicate function execution | Caller retry sau timeout hoặc event redelivery | Dùng event ID/idempotency và deduplicate |
| Function invoke endpoint bị gọi từ internet | Private subnet không tự chặn public invoke endpoint | Giới hạn IAM fn-invocation và policy condition |

## 16. Kiểm thử tích hợp

### 16.1. Logging tests

- Gửi một JSON custom log và xác minh xuất hiện trong đúng log OCID.
- Principal runtime chỉ push được log, không xóa log group.
- LogReader đọc được nội dung nhưng không thay đổi cấu hình.
- Log payload không chứa token, password hoặc PII.
- Kiểm tra retention và archive pipeline.
- Kiểm tra ứng dụng xử lý Logging API unavailable mà không làm mất business transaction.

### 16.2. Email tests

- SMTP credential đúng và TLS handshake thành công.
- Approved Sender đúng region/compartment.
- SPF/DKIM verification pass.
- Gửi plain text và HTML.
- Gửi attachment dưới giới hạn.
- Gửi tới recipient bị suppression và xác minh không retry vô hạn.
- Test invalid credential, sender chưa approved và quota exceeded.
- Test SMTP timeout sau khi server đã nhận message để kiểm tra duplicate protection.

### 16.3. Functions tests

- Gọi function Sync và xác minh response.
- Gọi Detached và xác minh caller nhận trạng thái accepted.
- Kiểm tra function chỉ nhận invocation từ principal được cấp.
- Test function OCID/endpoint sai.
- Test payload invalid và timeout.
- Test function runtime đọc Object Storage/Queue bằng identity riêng.
- Test success/failure destination.
- Gửi cùng event ID hai lần và xác minh function idempotent.

### 16.4. End-to-end test

Mô phỏng upload hợp đồng:

1. API lưu metadata/object và outbox.
2. Worker gửi log event.
3. Worker invoke function scan.
4. Function trả kết quả hoặc detached result.
5. Worker cập nhật document state.
6. Email worker gửi notification.
7. Kiểm tra Logging Search, Email Delivery logs và Function logs.
8. Kiểm tra trace/event ID xuyên suốt.
9. Kiểm tra retry không tạo duplicate email hoặc side effect.
10. Kiểm tra quyền bị từ chối khi dùng principal ngoài scope.

Không chạy test gửi email hàng loạt hoặc invoke function tốn tài nguyên trên production. Dùng compartment, log, sender và function test riêng.

## 17. Bài tập thực hành tổng hợp

Bạn được giao triển khai document-service trên OCI. Ứng dụng cần gửi log tập trung, gửi email cho khách hàng khi hợp đồng được xử lý và gọi function để tạo thumbnail.

**Nhiệm vụ:**

1. Tạo compartment Observability và log group app-runtime-logs.
2. Tạo custom log, lưu log OCID và cấu hình Logging starter.
3. Cấp log-content permission cho workload, read permission cho LogReaders.
4. Viết StructuredOciLogPublisher với trace ID và event ID.
5. Bật service logs cho Functions/Object Storage cần điều tra.
6. Cấu hình retention và Connector Hub archive nếu cần giữ lâu hơn 180 ngày.
7. Tạo Email Domain cho domain tổ chức sở hữu.
8. Cấu hình SPF/DKIM và xác minh DNS.
9. Tạo SMTP-only IAM user, SMTP credentials và Approved Sender ở region gửi.
10. Cấu hình Email Delivery starter, MailSender và JavaMailSender.
11. Tạo transactional outbox cho email notification.
12. Tạo OCI Functions Application và function tạo thumbnail.
13. Cấp fn-invocation cho đúng function OCID.
14. Tích hợp Function bean và thử Sync/Detached.
15. Cấu hình detached success/failure destination nếu cần.
16. Viết unit/integration/negative tests cho IAM, log, SMTP và function invocation.
17. Tạo dashboard/alert và runbook cho bounce, quota, function timeout và log ingestion failure.

**Câu hỏi tự đánh giá:**

- OCI Audit Logs, Service Logs và Custom Logs khác nhau như thế nào?
- Vì sao Spring Cloud Logging starter không tự thu mọi SLF4J event?
- Log group giúp kiểm soát quyền như thế nào?
- Vì sao retention Logging tối đa 180 ngày cần archive riêng nếu yêu cầu lâu hơn?
- Principal ghi log cần quyền IAM nào?
- SMTP credential khác OCI API signing key như thế nào?
- Vì sao Approved Sender phải tạo riêng ở từng region?
- SPF và DKIM giải quyết vấn đề gì?
- Vì sao SMTP credential nên thuộc IAM user riêng?
- Port 465 khác 587 ở cách thiết lập TLS như thế nào?
- Vì sao SMTP success không đồng nghĩa email vào inbox?
- Suppression list có vai trò gì?
- MailSender và JavaMailSender khác nhau ở use case nào?
- Vì sao email nên gửi qua outbox sau khi transaction commit?
- Function Sync và Detached khác nhau như thế nào?
- Vì sao Detached 202 không phải kết quả nghiệp vụ thành công?
- Vì sao OCI SDK cần base invoke endpoint thay vì full path?
- fn-invocation khác manage functions-family ở điểm nào?
- Vì sao private subnet không thay IAM policy cho invoke endpoint?
- Làm sao xử lý duplicate khi caller retry sau timeout?
- Vì sao function runtime cần policy riêng với caller?
- Những field nào không nên đưa vào log hoặc email?

**Đáp án định hướng:** Audit logs ghi API calls của OCI Audit; service logs do OCI services phát; custom logs do app/agent gửi; starter chỉ cung cấp LogService API tường minh; log group là boundary IAM cho logs; retention search tối đa 180 ngày nên dùng Connector Hub archive; writer cần use log-content; SMTP credentials là Oracle-generated username/password cho SMTP, khác API signing key; Approved Sender và suppression list regional; SPF xác minh nguồn gửi, DKIM ký domain; SMTP-only user giảm blast radius; port 465 implicit TLS còn 587 STARTTLS; SMTP acceptance không đảm bảo recipient delivery; suppression ngăn gửi lại địa chỉ hard bounce/complaint; MailSender phù hợp text, JavaMailSender hỗ trợ MIME/HTML/attachment; outbox tránh email trước commit; Sync chờ kết quả, Detached trả 202; 202 chỉ cho biết invocation đã bắt đầu; SDK dùng base endpoint và tự ghép path; fn-invocation chỉ cấp quyền gọi, manage functions-family rộng hơn; private subnet không tự đóng public invoke endpoint; dùng idempotency/event ID; function runtime có principal riêng; log/email không nên chứa token, secret hoặc payload nhạy cảm.

## 18. Tài liệu tham khảo chính thức

### Spring Cloud Oracle 2.0.4

- [OCI Logging Integration](https://oracle.github.io/spring-cloud-oracle/site/docs/oci/logging/): dependency, LogService bean, putLog và logId property.
- [OCI Email Delivery Integration](https://oracle.github.io/spring-cloud-oracle/site/docs/oci/email-delivery/): MailSender, JavaMailSender, SMTP configuration và sample.
- [OCI Functions Integration](https://oracle.github.io/spring-cloud-oracle/site/docs/oci/functions/): Function bean, invokeFunction và starter configuration.
- [OCI Core](https://oracle.github.io/spring-cloud-oracle/site/docs/oci/core/): OCI authentication, region và compartment configuration.
- [Spring Cloud Oracle Release Notes](https://oracle.github.io/spring-cloud-oracle/site/docs/releases/changelog/): phiên bản và compatibility.

### OCI Logging

- [Logging Overview](https://docs.oracle.com/en-us/iaas/Content/Logging/Concepts/loggingoverview.htm): Audit/Service/Custom Logs, log group, search, Connector Hub và encryption.
- [Logs and Log Groups](https://docs.oracle.com/en-us/iaas/Content/Logging/Task/managinglogs.htm): log group, IAM boundary và policy.
- [Ingesting Custom Logs](https://docs.oracle.com/en-us/iaas/Content/Logging/Concepts/using_the_api_customlogs.htm): PutLogs Logging Ingestion API.
- [Getting a Log's Details](https://docs.oracle.com/en-us/iaas/Content/Logging/Task/get-logging-log.htm): retention 30-day increments và tối đa 180 ngày.
- [Details for Logging IAM Policy](https://docs.oracle.com/en-us/iaas/Content/Identity/Reference/loggingpolicyreference.htm): log-content và log-groups permissions.

### OCI Email Delivery

- [Email Delivery Getting Started](https://docs.oracle.com/en-us/iaas/Content/Email/Reference/gettingstarted.htm): trình tự cấu hình domain, SPF, DKIM, sender và SMTP.
- [Overview of Email Delivery](https://docs.oracle.com/en-us/iaas/Content/Email/Concepts/overview.htm): regional assets, SMTP credential và endpoint.
- [Creating an Approved Sender](https://docs.oracle.com/en-us/iaas/Content/Email/Reference/gettingstarted_topic-Create_an_approved_sender.htm): sender theo compartment/region.
- [Managing Approved Senders](https://docs.oracle.com/en-us/iaas/Content/Email/Tasks/managingapprovedsenders.htm): domain ownership và From alignment.
- [Configuring SPF](https://docs.oracle.com/en-us/iaas/Content/Email/Tasks/configurespf.htm): TXT record theo region.
- [Configuring DKIM](https://docs.oracle.com/en-us/iaas/Content/Email/Tasks/configure-dkim-using-the-console.htm): DKIM CNAME, key rotation và verification.
- [Configuring SMTP Connection](https://docs.oracle.com/en-us/iaas/Content/Email/Reference/gettingstarted_topic-Configure_the_SMTP_connection.htm): endpoint, port và TLS.
- [Working with SMTP Credentials](https://docs.oracle.com/en-us/iaas/Content/Identity/access/working-with-smtp-credentials.htm): SMTP credential lifecycle và giới hạn.
- [Securing Email Delivery](https://docs.oracle.com/en-us/iaas/Content/Security/Reference/email_security.htm): SMTP-only user, IAM và secret protection.
- [Troubleshooting Email Delivery](https://docs.oracle.com/en-us/iaas/Content/Email/Concepts/troubleshooting.htm): SMTP status, quota, suppression và TLS.
- [Email Delivery IAM Policy Reference](https://docs.oracle.com/en-us/iaas/Content/Identity/policyreference/emailpolicyreference.htm): approved-senders và suppressions permissions.

### OCI Functions

- [Invoking Functions](https://docs.oracle.com/en-us/iaas/Content/Functions/Tasks/functionsinvokingfunctions.htm): signed invocation, SDK, Sync/Detached, timeout và result destinations.
- [Controlling Access to Invoke and Manage Functions](https://docs.oracle.com/en-us/iaas/Content/Functions/Tasks/functionsrestrictinguseraccess.htm): fn-invocation policy và scope.
- [Functions IAM Policy Reference](https://docs.oracle.com/en-us/iaas/Content/Identity/policyreference/functionspolicyreference.htm): fn-app, fn-function và fn-invocation permissions.
- [OCI Java SDK FunctionsInvoke](https://docs.oracle.com/en-us/iaas/tools/java/latest/com/oracle/bmc/functions/FunctionsInvoke.html): invoke API, endpoint và request handling.

**Ghi nhớ:** Logging starter gửi custom log qua LogService; Email Delivery starter dùng Spring Mail với SMTP credential và Approved Sender theo region; Functions starter dùng OCI identity để invoke function bằng OCID và base endpoint. Tách quyền và credential theo từng dịch vụ, dùng outbox/idempotency cho luồng bất đồng bộ, bảo vệ log/email khỏi secret/PII và theo dõi kết quả cuối thay vì chỉ dựa vào HTTP/SMTP acceptance.
