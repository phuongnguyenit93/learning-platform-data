# Tích hợp SMS với mẫu thông báo và xử lý kết quả gửi

## 1. Bài toán và mục tiêu

Một ứng dụng Spring Boot cần gửi mã xác minh khi người dùng đăng nhập, thông báo khi đơn hàng được xác nhận và tin nhắn nhắc lịch. Ứng dụng phải chọn đúng API theo quốc gia nhận tin, dùng đúng chữ ký/sender ID và mẫu đã được duyệt, giữ thông tin xác thực an toàn, rồi cập nhật trạng thái theo kết quả từ nhà mạng.

Alibaba Cloud **Short Message Service (SMS)** cung cấp API gửi tin nhắn, tra cứu trạng thái và nhận delivery receipt. Việc tích hợp không chỉ dừng ở lời gọi gửi thành công: hệ thống còn phải quản lý template, consent, quota, phí, retry và callback bất đồng bộ.

Bài học thuộc chương **Alibaba Cloud** trong module **SPRING_CLOUD_PROVIDER_INTEGRATION**. Module thực hành tích hợp Spring Boot với các dịch vụ managed của AWS, Azure, Google Cloud và Alibaba Cloud qua thư viện tương ứng; người học cần cấu hình danh tính/quyền, storage, messaging, dữ liệu, bảo vệ secret, kiểm thử tích hợp và đánh giá khác biệt giữa cloud provider.

Sau bài này, bạn có thể:

1. Phân biệt luồng Go China và Go Globe để chọn đúng SMS API.
2. Chuẩn bị chữ ký, sender ID, template và thông tin tuân thủ.
3. Gọi SMS OpenAPI bằng Java SDK V2 từ Spring Boot.
4. Quản lý RAM credentials/STS và quyền gửi/tra cứu SMS.
5. Phân biệt request được chấp nhận với SMS đã được nhà mạng giao.
6. Nhận delivery receipt qua HTTP webhook hoặc Simple Message Queue (SMQ).
7. Xử lý callback trùng, callback thiếu, trạng thái không đồng nhất, retry và QPS limit.
8. Đánh giá legacy SMS starter và quyết định khi nào nên dùng SDK trực tiếp.

## 2. Vòng đời của một SMS

~~~mermaid
flowchart TD
    A["Nghiệp vụ phát sinh<br/>OTP / đơn hàng / nhắc lịch"]
    B["Lưu notification intent<br/>Outbox / queue"]
    C["SMS worker<br/>Kiểm tra consent, quota, template"]
    D["Alibaba Cloud SMS API"]
    E["MessageId + RequestId<br/>Submission accepted"]
    F["Nhà mạng xử lý và giao tin"]
    G["SmsReport / GlobeSmsReport<br/>HTTP callback hoặc SMQ"]
    H["Receipt processor<br/>Deduplicate + cập nhật trạng thái"]
    I["QueryMessage / reconciliation"]
    A --> B --> C --> D --> E --> F --> G --> H
    H --> I
~~~

Có ba thời điểm khác nhau:

- **Ứng dụng gửi request:** SDK trả về response và request ID.
- **SMS platform chấp nhận request:** response thường có ResponseCode = OK và MessageId. Điều này cho biết nền tảng đã tiếp nhận yêu cầu.
- **Nhà mạng trả kết quả giao tin:** delivery receipt hoặc QueryMessage cho biết tin đang giao, đã giao hoặc thất bại.

Không được coi ResponseCode = OK là bằng chứng điện thoại đã nhận SMS. Lưu MessageId để đối chiếu delivery receipt sau đó.

## 3. Chọn đúng API theo quốc gia nhận tin

Alibaba Cloud chia API thành hai luồng chính:

| Luồng | Đối tượng nhận | API gửi | Cách truyền nội dung |
| --- | --- | --- | --- |
| **Go China** | Số điện thoại tại Trung Quốc đại lục | SendMessageWithTemplate | Chữ ký đã duyệt + TemplateCode + TemplateParam |
| **Go Globe** | Hong Kong, Macao, Taiwan và các quốc gia/vùng lãnh thổ ngoài Trung Quốc đại lục | SendMessageToGlobe hoặc BatchSendMessageToGlobe | Sender ID nếu được hỗ trợ + nội dung Message |

**Điểm cần nhớ:** SendMessageWithTemplate chỉ gửi tới Trung Quốc đại lục. Nếu gửi tới Việt Nam hoặc một quốc gia khác ngoài Trung Quốc đại lục, hãy dùng SendMessageToGlobe. Bạn có thể quản lý mẫu nội dung trong ứng dụng rồi render thành Message, nhưng không truyền TemplateCode của Go China vào API Go Globe.

### 3.1. Go China: chữ ký và template

Mỗi tin nhắn gửi tới Trung Quốc đại lục cần có:

- **SMS signature:** tên tổ chức/ứng dụng xuất hiện ở phần đầu tin nhắn.
- **Message template:** nội dung đã được duyệt, có thể chứa biến.
- **TemplateCode:** mã do SMS Console cấp sau khi template được duyệt.
- **TemplateParam:** JSON chứa giá trị của từng biến trong template.

Ví dụ template:

~~~text
Mã xác minh của bạn là ${code}. Mã có hiệu lực trong ${minutes} phút.
~~~

Khi gọi API, TemplateParam phải chứa đúng tên biến, ví dụ:

~~~json
{
  "code": "483921",
  "minutes": "5"
}
~~~

Tên biến phân biệt chính xác theo template đã duyệt. Thiếu biến, sai tên biến hoặc vượt giới hạn độ dài có thể làm request bị từ chối.

### 3.2. Go Globe: Sender ID và nội dung

Với SMS quốc tế, kiểm tra quy định của quốc gia đích. Một số nước yêu cầu đăng ký Sender ID hoặc dùng số gửi nội địa. Từ ngày 08/09/2025, tài liệu Alibaba Cloud mô tả khách hàng International SMS đã chuyển sang Sender ID mode; luồng quốc tế không yêu cầu quy trình signature/template Go China, nhưng vẫn phải đáp ứng quy định đăng ký của từng nước.

API SendMessageToGlobe nhận:

- To: số điện thoại gồm mã quốc gia và số thuê bao.
- From: Sender ID nếu cần/được hỗ trợ ở quốc gia đích.
- Message: nội dung tin nhắn đã được ứng dụng render.
- Type: OTP, NOTIFY hoặc MKT.

Sender ID có thể chỉ chứa chữ và số; giới hạn độ dài phụ thuộc loại ký tự. Ví dụ tài liệu API quy định tối đa 11 ký tự nếu có chữ và tối đa 15 chữ số nếu chỉ có số. Một số quốc gia có quy tắc riêng, chẳng hạn yêu cầu đăng ký DLT hoặc Sender ID trước khi gửi.

**Lưu ý chi phí:** với International SMS, phí được tính theo trạng thái submit của tin nhắn. Bạn vẫn có thể bị tính phí dù carrier receipt sau đó báo Failed. Vì vậy, cần phân loại lỗi và đối soát trước khi gửi lại; retry mù có thể tạo tin trùng và tăng chi phí.

### 3.3. Chuẩn bị tài khoản và tuân thủ

Trước khi tích hợp:

1. Hoàn tất xác minh danh tính doanh nghiệp và kích hoạt SMS.
2. Kiểm tra tài khoản đã có số dư hoặc resource package phù hợp với destination.
3. Với Go China, tạo signature và template, chờ trạng thái Approved.
4. Với Go Globe, kiểm tra sender registration và quy định của quốc gia nhận.
5. Xác định loại tin nhắn: OTP, notification hay promotional.
6. Lưu bằng chứng consent và quy trình unsubscribe cho nội dung quảng cáo.

SMS template đã được duyệt không thể sửa trực tiếp nội dung/biến. Nếu cần thay đổi, tạo template mới hoặc clone template; hệ thống cấp TemplateCode mới và ứng dụng phải cập nhật mã này sau khi được duyệt.

Với template quảng cáo, cần có lựa chọn từ chối nhận tin theo quy định áp dụng và chỉ gửi khi người nhận đã đồng ý. Không dùng template OTP để gửi nội dung marketing.

## 4. Quản lý signature và template

### 4.1. Trạng thái duyệt

| Trạng thái | Ý nghĩa | Hành động |
| --- | --- | --- |
| **Pending Approval** | Đang được xem xét | Chưa dùng để gửi; chờ kết quả |
| **Approved** | Đã được chấp thuận | Có thể dùng khi gọi API |
| **Failed** | Bị từ chối | Xem lý do, điều chỉnh hồ sơ/nội dung và gửi lại |

Tài liệu bắt đầu sử dụng SMS cập nhật ngày 27/10/2026 ước tính signature được xét trong tối đa khoảng 24 giờ nếu nộp trong giờ làm việc, template mất khoảng 2–4 giờ; thời gian đăng ký Sender ID thay đổi theo quốc gia. Đây là mốc tham khảo, không phải SLA bảo đảm. Không hard-code thời gian duyệt vào quy trình release.

### 4.2. Quy tắc biến trong template

Một số quy tắc quan trọng của template Go China:

- Dùng định dạng biến ${variable_name}.
- Mỗi biến có giới hạn độ dài theo quy định template; tài liệu hướng dẫn hiện hành nêu khoảng 1–35 ký tự cho biến.
- Không dùng biến ghép hoặc hai biến liền nhau.
- Không tạo template chỉ gồm biến.
- Khuyến nghị không quá ba biến để giảm rủi ro bị nhà mạng từ chối.
- Biến mã xác minh thường dùng 4–6 chữ số hoặc ký tự theo mẫu được chấp thuận.
- Nội dung quảng cáo cần có hướng dẫn unsubscribe ở cuối.

Các giới hạn có thể khác theo loại template và thay đổi quy định nhà mạng. Luôn đối chiếu hướng dẫn cho đúng template type trước khi gửi duyệt.

### 4.3. API quản lý signature/template đã được cập nhật

Từ thông báo cập nhật API ngày 20/01/2026, các API cũ được thay bằng API mới:

| API cũ | API mới |
| --- | --- |
| AddSmsSign | CreateSmsSign |
| ModifySmsSign | UpdateSmsSign |
| QuerySmsSign | GetSmsSign |
| AddSmsTemplate | CreateSmsTemplate |
| ModifySmsTemplate | UpdateSmsTemplate |
| QuerySmsTemplate | GetSmsTemplate |

Các API mới bổ sung thông tin qualification để đáp ứng yêu cầu quản lý nội dung SMS. Có thể quản lý signature/template qua Console thay vì tự động hóa các API quản trị này; nếu tự động hóa, dùng API mới theo tài liệu hiện hành.

## 5. Kiến trúc Spring Boot nên dùng

Không nên gọi SMS trực tiếp trong transaction nghiệp vụ như đặt hàng hoặc đăng ký tài khoản. Hãy lưu yêu cầu gửi cùng transaction, sau đó worker xử lý bất đồng bộ.

~~~mermaid
flowchart LR
    API["Order / Identity API"] --> DB[("Database<br/>Business + Outbox")]
    DB --> P["Outbox publisher"]
    P --> Q["Queue / job worker"]
    Q --> W["SMS worker"]
    W --> SDK["Alibaba SMS SDK"]
    SDK --> SMS(("SMS platform"))
    SMS --> R["Receipt callback / SMQ"]
    R --> RP["Receipt processor"]
    RP --> DB
~~~

Luồng thực hiện:

1. Service nghiệp vụ ghi bản ghi outbox, gồm notificationId, loại tin, người nhận, template key và dữ liệu biến.
2. Worker đọc outbox/queue và kiểm tra consent, template version, quota, số lần gửi.
3. Worker gọi SMS API.
4. Nếu nền tảng chấp nhận, lưu MessageId, RequestId, thời điểm gửi và trạng thái SUBMITTED.
5. Receipt processor nhận callback hoặc SMQ message, đối chiếu MessageId và cập nhật trạng thái giao tin.
6. Job reconciliation dùng QueryMessage cho các message chưa nhận receipt hoặc cần xác minh lại.

Dùng khóa nghiệp vụ như orderId + notificationType + templateVersion để ngăn tạo nhiều notification intent ngoài ý muốn. MessageId là khóa liên kết với nhà cung cấp; notificationId là khóa của nghiệp vụ trong hệ thống.

## 6. Thêm Alibaba Cloud SMS Java SDK V2

Tài liệu Java SDK hiện hành dùng artifact **com.aliyun:dysmsapi20180501**. Tại snapshot ngày **24/11/2026**, Maven Central công bố version **1.0.12**. Để dùng RAM role/STS credential provider, có thể thêm **credentials-java**; Maven Central công bố version **1.0.8**.

~~~xml
<dependencies>
    <dependency>
        <groupId>com.aliyun</groupId>
        <artifactId>dysmsapi20180501</artifactId>
        <version>1.0.12</version>
    </dependency>
    <dependency>
        <groupId>com.aliyun</groupId>
        <artifactId>credentials-java</artifactId>
        <version>1.0.8</version>
    </dependency>
</dependencies>
~~~

SDK Java V2 dùng package com.aliyun.dysmsapi20180501. Không nhầm với legacy artifact aliyun-java-sdk-dysmsapi thuộc SDK V1 hoặc API client cũ.

Kiểm tra Maven dependency tree khi nâng SDK để phát hiện conflict với tea, tea-openapi, tea-util hoặc credentials library. Nếu SDK đã kéo dependency chung theo version tương thích, không tự thêm một version cũ khác.

## 7. Cấu hình credentials và SMS client trong Spring Boot

### 7.1. Dùng default credential chain

Cấu hình một Credentials client và SMS client singleton trong Spring context. Credentials tool có thể lấy thông tin xác thực từ environment variables/profile ở local, ECS RAM role hoặc OIDC/RRSA trên ACK tùy môi trường.

~~~java
package demo.sms.config;

import com.aliyun.credentials.Client;
import com.aliyun.teaopenapi.models.Config;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@ConfigurationProperties(prefix = "aliyun.sms")
record SmsProperties(String endpoint) {}

@Configuration
@EnableConfigurationProperties(SmsProperties.class)
public class SmsClientConfiguration {

    @Bean
    public Client aliyunCredentialsClient() throws Exception {
        // Default chain: profile/environment/workload role/OIDC.
        return new Client();
    }

    @Bean
    public com.aliyun.dysmsapi20180501.Client smsClient(
            Client aliyunCredentialsClient,
            SmsProperties properties) throws Exception {

        Config config = new Config();
        config.setCredential(aliyunCredentialsClient);
        config.setEndpoint(properties.endpoint());

        return new com.aliyun.dysmsapi20180501.Client(config);
    }
}
~~~

Tạo client một lần trong Spring context để tái sử dụng connection và credential cache. Không khởi tạo Credentials client hoặc product client mới cho mỗi request.

### 7.2. Cấu hình endpoint

Ví dụ application YAML:

~~~yaml
aliyun:
  sms:
    endpoint: dysmsapi.ap-southeast-1.aliyuncs.com
~~~

Endpoint phải thuộc đúng SMS API và region/network path. Tài liệu endpoint hiện hành liệt kê Singapore dysmsapi.ap-southeast-1.aliyuncs.com, Indonesia dysmsapi.ap-southeast-5.aliyuncs.com, Frankfurt dysmsapi.eu-central-1.aliyuncs.com; nhiều region Trung Quốc dùng dysmsapi.aliyuncs.com. Với VPC, dùng endpoint VPC được công bố cho region tương ứng. Không tự ghép endpoint từ tên region.

### 7.3. Cấu hình RAM permission

Tạo RAM role hoặc RAM user dành riêng cho SMS worker. Cấp các action cần thiết, ví dụ:

| Nghiệp vụ | RAM action |
| --- | --- |
| Gửi SMS Go China | dysms:SendMessageWithTemplate |
| Gửi SMS Go Globe | dysms:SendMessageToGlobe |
| Gửi batch quốc tế | dysms:BatchSendMessageToGlobe |
| Tra cứu trạng thái | dysms:QueryMessage |

API gửi/tra cứu có thể yêu cầu Resource = "*", theo bảng RAM authorization của từng API. Không cấp quyền quản trị signature/template nếu workload chỉ gửi tin. Nếu có job quản trị template riêng, dùng role khác.

Ở production, ưu tiên ECS instance RAM role hoặc ACK RRSA/OIDC. Local development có thể dùng RAM user test qua biến môi trường:

~~~text
ALIBABA_CLOUD_ACCESS_KEY_ID=<RAM_USER_ACCESS_KEY_ID>
ALIBABA_CLOUD_ACCESS_KEY_SECRET=<RAM_USER_ACCESS_KEY_SECRET>
~~~

Không dùng AccessKey của root account, không commit secret vào application.yml, Docker image hoặc log. Nếu dùng STS tĩnh, phải có cơ chế lấy token mới trước khi hết hạn; workload chạy lâu nên dùng credential provider có cache/auto-refresh.

## 8. Gửi SMS theo template bằng Java SDK

### 8.1. Gửi notification template tới Trung Quốc đại lục

Ví dụ service gọi SendMessageWithTemplate. Template và signature phải ở trạng thái Approved; TemplateParam được serialize từ map để tránh lỗi JSON escaping.

~~~java
package demo.sms.service;

import com.aliyun.dysmsapi20180501.models.SendMessageWithTemplateRequest;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.stereotype.Service;

import java.util.Map;

@Service
public class ChinaSmsSender {

    private final com.aliyun.dysmsapi20180501.Client smsClient;
    private final ObjectMapper objectMapper;

    public ChinaSmsSender(
            com.aliyun.dysmsapi20180501.Client smsClient,
            ObjectMapper objectMapper) {
        this.smsClient = smsClient;
        this.objectMapper = objectMapper;
    }

    public SmsSubmission sendNotification(
            String phoneNumber,
            String signature,
            String templateCode,
            Map<String, String> templateParams) throws Exception {

        String templateParamJson =
                objectMapper.writeValueAsString(templateParams);

        SendMessageWithTemplateRequest request =
                new SendMessageWithTemplateRequest()
                        .setTo(phoneNumber)
                        .setFrom(signature)
                        .setTemplateCode(templateCode)
                        .setTemplateParam(templateParamJson);

        var response = smsClient.sendMessageWithTemplate(request);
        var body = response.getBody();

        if (body == null || !"OK".equals(body.getResponseCode())) {
            throw new IllegalStateException(
                    "SMS submission rejected: "
                            + (body == null ? "empty response"
                            : body.getResponseDescription()));
        }

        return new SmsSubmission(
                body.getMessageId(),
                body.getRequestId(),
                body.getResponseCode(),
                body.getSegments());
    }

    public record SmsSubmission(
            String messageId,
            String requestId,
            String responseCode,
            String segments) {}
}
~~~

Ví dụ gọi service:

~~~java
Map<String, String> params = Map.of(
        "orderNo", "ORD-2026-001",
        "status", "confirmed");

SmsSubmission submission = sender.sendNotification(
        "8613800000000",
        "ApprovedSignature",
        "SMS_123456",
        params);
~~~

To phải có mã quốc gia theo định dạng API yêu cầu. Ví dụ 86 là mã Trung Quốc; không lấy nguyên số nội địa nếu thiếu mã quốc gia. From là tên signature được duyệt; TemplateCode là mã template đã duyệt.

Response ResponseCode = OK và MessageId chỉ xác nhận yêu cầu được SMS platform chấp nhận. Lưu MessageId ngay sau khi nhận response để theo dõi delivery receipt.

### 8.2. Gửi SMS quốc tế

Với quốc gia ngoài Trung Quốc đại lục, dùng SendMessageToGlobe. Nội dung Message có thể được render từ template nội bộ của ứng dụng; sender ID phải tuân thủ quy định destination.

~~~java
import com.aliyun.dysmsapi20180501.models.SendMessageToGlobeRequest;

public String sendInternationalNotification(
        com.aliyun.dysmsapi20180501.Client smsClient,
        String phoneNumber,
        String senderId,
        String message) throws Exception {

    SendMessageToGlobeRequest request =
            new SendMessageToGlobeRequest()
                    .setTo(phoneNumber)
                    .setFrom(senderId)
                    .setMessage(message)
                    .setType("NOTIFY");

    var response = smsClient.sendMessageToGlobe(request);
    var body = response.getBody();

    if (body == null || !"OK".equals(body.getResponseCode())) {
        throw new IllegalStateException(
                "SMS submission rejected: "
                        + (body == null ? "empty response"
                        : body.getResponseDescription()));
    }

    return body.getMessageId();
}
~~~

Các loại Type gồm OTP, NOTIFY và MKT. Không gửi nội dung quảng cáo dưới loại notification để né chính sách; loại tin phải phản ánh mục đích thực tế. Nếu destination yêu cầu Sender ID registration, chỉ gửi sau khi ID được duyệt.

## 9. Nhận delivery receipt và tra cứu trạng thái

### 9.1. Hai cách nhận receipt

Sau khi gửi, cấu hình một trong hai cơ chế ở SMS Console:

| Cơ chế | Cách hoạt động | Khi phù hợp |
| --- | --- | --- |
| **HTTP callback** | SMS POST batch JSON tới URL công khai đã cấu hình | Ứng dụng có endpoint nhận webhook |
| **SMQ queue** | SMS đẩy receipt vào queue; worker pull và xử lý | Muốn buffer, pull theo năng lực và tách receipt processing khỏi web request |

Các loại message thường gặp:

- SmsReport: delivery receipt cho SMS.
- GlobeSmsReport: delivery receipt cho SMS quốc tế.
- SmsUp: tin nhắn người dùng gửi ngược về (mobile originated).

Không nhầm SmsUp với delivery receipt của tin nhắn đi. Callback có thể gồm nhiều bản ghi trong một lần POST; consumer phải xử lý theo batch.

### 9.2. Payload callback HTTP

Tài liệu webhook mô tả request HTTP POST với body JSON array. Một phần tử có thể chứa:

~~~json
[
  {
    "To": "84901234567",
    "Status": "1",
    "MessageId": "1234567890123456",
    "SmsSize": "1",
    "SendDate": "Tue, 24 Nov 2026 10:00:00 +0800",
    "ReceiveDate": "Tue, 24 Nov 2026 10:00:30 +0800",
    "ErrorCode": "success",
    "ErrorDescription": "success"
  }
]
~~~

Các field quan trọng:

| Field | Ý nghĩa |
| --- | --- |
| To | Số điện thoại nhận |
| Status | Trạng thái theo schema callback đang dùng |
| MessageId | ID message đã gửi |
| SmsSize | Số segment tính cước |
| SendDate | Thời điểm gửi tới nhà mạng |
| ReceiveDate | Thời điểm nhận receipt |
| ErrorCode / ErrorDescription | Mã và mô tả kết quả |

Ví dụ controller Spring Boot:

~~~java
package demo.sms.web;

import com.fasterxml.jackson.annotation.JsonProperty;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

import java.util.List;

@RestController
@RequestMapping("/webhooks/aliyun/sms")
public class SmsReceiptController {

    private final SmsReceiptService receiptService;

    public SmsReceiptController(SmsReceiptService receiptService) {
        this.receiptService = receiptService;
    }

    @PostMapping(
            path = "/report",
            consumes = MediaType.APPLICATION_JSON_VALUE)
    public ResponseEntity<ReceiptAck> receive(
            @RequestBody List<SmsReport> reports) {

        receiptService.persistIdempotently(reports);
        return ResponseEntity.ok(new ReceiptAck(0, "received"));
    }

    public record SmsReport(
            @JsonProperty("To") String to,
            @JsonProperty("Status") String status,
            @JsonProperty("MessageId") String messageId,
            @JsonProperty("SmsSize") String smsSize,
            @JsonProperty("SendDate") String sendDate,
            @JsonProperty("ReceiveDate") String receiveDate,
            @JsonProperty("ErrorCode") String errorCode,
            @JsonProperty("ErrorDescription") String errorDescription) {}

    public record ReceiptAck(int code, String msg) {}
}
~~~

Chỉ trả HTTP 200 sau khi receipt đã được ghi nhận bền vững (hoặc đã được đẩy vào queue nội bộ). Nếu lưu trữ thất bại, trả lỗi để có thể được gửi lại theo cơ chế callback. Endpoint nên dùng HTTPS, giới hạn network ingress và xác minh MessageId có tương ứng một tin nhắn do ứng dụng gửi. Không coi payload JSON là bằng chứng xác thực danh tính; nếu cần kênh nhận riêng tư hơn, cân nhắc SMQ consumer.

### 9.3. Status callback và QueryMessage có enum khác nhau

Đây là chi tiết dễ gây lỗi khi mapping:

| Nguồn | Giá trị | Ý nghĩa theo tài liệu |
| --- | --- | --- |
| **SMS webhook receipt** | 1 | Sent / đã gửi tới nhà mạng theo schema callback |
| **SMS webhook receipt** | 2 | Failed |
| **SMS webhook receipt** | 6 | Expired |
| **QueryMessage API** | 1 | Delivered |
| **QueryMessage API** | 2 | Delivery failed |
| **QueryMessage API** | 3 | Delivering |

Không dùng một enum số chung cho mọi loại callback/API. Lưu thêm nguồn receipt (SmsReport, GlobeSmsReport, QueryMessage), destination và raw status để mapping đúng theo tài liệu của loại message đang dùng. Từ “Sent” ở receipt không nhất thiết có cùng nghĩa với “Delivered” trong kết quả query.

### 9.4. Tra cứu bằng QueryMessage

Nếu callback bị thiếu hoặc cần xác minh, gọi QueryMessage bằng MessageId. API trả về delivery status, ErrorCode, ReceiveDate, SendDate, thông tin nhà mạng và RequestId.

~~~java
import com.aliyun.dysmsapi20180501.models.QueryMessageRequest;

public String queryStatus(
        com.aliyun.dysmsapi20180501.Client smsClient,
        String messageId) throws Exception {

    QueryMessageRequest request =
            new QueryMessageRequest().setMessageId(messageId);

    var response = smsClient.queryMessage(request);
    var body = response.getBody();

    if (body == null) {
        throw new IllegalStateException("Empty QueryMessage response");
    }

    return body.getStatus();
}
~~~

Theo tài liệu API hiện hành, QueryMessage có giới hạn công bố **300 QPS cho một user trong cùng Alibaba Cloud account**. Không polling dồn dập cho từng message; chỉ query message còn ở trạng thái chưa xác định hoặc dùng job reconciliation theo lô/nhịp phù hợp.

## 10. Idempotency, retry và điều tiết tải

### 10.1. Callback có thể trùng hoặc bị thiếu

Alibaba Cloud cảnh báo delivery receipt không bảo đảm idempotent; lỗi mạng hoặc timeout có thể gây receipt trùng hoặc thiếu. Vì vậy:

- Không cập nhật nghiệp vụ bằng cách cộng số lần nhận callback.
- Không gửi thêm SMS chỉ vì nhận callback trùng.
- Lưu event receipt vào bảng riêng để audit.
- Dùng khóa deduplication dựa trên MessageId, status, receive time và error code hoặc hash payload.
- Cập nhật trạng thái message theo state machine, không cho trạng thái cũ ghi đè trạng thái mới hơn.
- Dùng QueryMessage hoặc Delivery Report để reconcile các message chưa có receipt.

Nếu dùng HTTP callback, trả 200 sau khi đã lưu/queue thành công. Với SMQ, chỉ acknowledge/delete message sau khi xử lý bền vững; nếu lỗi nghiệp vụ tạm thời, để message được redeliver theo cơ chế queue.

### 10.2. Không retry mù khi request timeout

Nếu client timeout trước khi nhận response, không thể kết luận SMS API chưa tiếp nhận request. Request có thể đã tới SMS platform nhưng response bị mất. Nếu gửi lại ngay, người nhận có thể nhận hai SMS và hệ thống bị tính phí hai lần.

Đặt trạng thái trung gian như SUBMISSION_UNKNOWN khi không biết kết quả. Ghi log RequestId nếu có, giữ business key, kiểm tra Messaging Records hoặc reconciliation; chỉ gửi lại khi có cơ sở xác định request trước chưa được tiếp nhận. Với OTP, áp dụng giới hạn số lần phát hành và thời gian hiệu lực.

### 10.3. QPS và quota

Tài liệu flow-control hiện hành công bố các giới hạn tham khảo:

| API | QPS công bố |
| --- | ---: |
| SendMessageWithTemplate | 1.500 |
| SendMessageToGlobe | 2.000 |
| BatchSendMessageToGlobe | 1 |
| QueryMessage | 300 |

Giới hạn thực tế có thể thay đổi theo account, API và region; kiểm tra Quota Center trước khi chạy chiến dịch lớn. Dùng rate limiter trong ứng dụng, batch theo đúng API, backoff có jitter khi gặp throttling và theo dõi QPS_LIMIT_CONTROL.

Với Go Globe, tài liệu nêu batch API hỗ trợ tối đa 1.000 người nhận mỗi request. Batch có thể có độ trễ khác với gửi từng tin; OTP thường cần gửi đơn lẻ để ưu tiên tính kịp thời.

### 10.4. Trạng thái đề xuất trong ứng dụng

| Trạng thái nội bộ | Ý nghĩa |
| --- | --- |
| PENDING | Notification intent đã được lưu |
| SENDING | Worker đang gọi SMS API |
| SUBMITTED | SMS platform chấp nhận request và đã có MessageId |
| SUBMISSION_UNKNOWN | Timeout hoặc lỗi khiến chưa xác định request có được tiếp nhận hay không |
| DELIVERING | QueryMessage báo đang giao |
| DELIVERED | Nhà mạng xác nhận giao theo nguồn receipt tương ứng |
| FAILED | Gửi/giao thất bại |
| EXPIRED | Message hết thời gian hiệu lực |
| RECONCILIATION_REQUIRED | Thiếu receipt hoặc dữ liệu callback/query mâu thuẫn |

Lưu raw status và nguồn trạng thái bên cạnh enum nội bộ. Với SMS, Delivered thường là trạng thái nhà mạng xác nhận, không chứng minh người nhận đã đọc tin nhắn.

## 11. Bảo mật và vận hành

- Dùng RAM role/STS và quyền tối thiểu; không dùng root AccessKey.
- Không ghi số điện thoại đầy đủ, OTP, nội dung tin nhắn hoặc token vào log thông thường.
- Mã OTP cần được tạo bằng secure random, lưu hash phía server, có TTL và giới hạn số lần nhập.
- Kiểm tra quyền của user trước khi gửi SMS tới số điện thoại; chống lợi dụng API để spam hoặc gây phát sinh chi phí.
- Lưu consent và trạng thái unsubscribe cho SMS marketing.
- Mã hóa số điện thoại và dữ liệu template parameter khi lưu trữ nếu chính sách dữ liệu yêu cầu.
- Chỉ giữ dữ liệu SMS theo retention cần thiết; giới hạn quyền truy cập vào delivery report.
- Không để public endpoint callback chấp nhận payload tùy ý làm thay đổi trạng thái bất kỳ MessageId nào.
- Theo dõi request rate, số tin đã gửi, segment bị tính phí, delivery success/failure, QPS throttle, callback lag và message chưa reconcile.

### 11.1. Lỗi thường gặp

| Mã/lỗi | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| SMS_SIGN_NAME_ILLEGAL | Signature không tồn tại, bị từ chối hoặc sai chính tả | Kiểm tra signature đã Approved và From khớp chính xác |
| SMS_CONTENT_CODE_ILLEGAL | Template không tồn tại, chưa duyệt hoặc bị từ chối | Kiểm tra TemplateCode và trạng thái duyệt |
| CONTENT_MISSING_PARAMETERS | Thiếu biến hoặc sai tên biến | So sánh JSON TemplateParam với template |
| PARAM_LENGTH_LIMIT | Giá trị biến quá dài | Rút gọn và tuân theo giới hạn của template |
| INVALID_SENDERID | Sender ID quốc tế sai hoặc chưa được duyệt | Kiểm tra Sender ID theo destination |
| MOBILE_NUMBER_ILLEGAL | Số điện thoại sai định dạng | Chuẩn hóa country code và số thuê bao |
| RAM_PERMISSION_DENY | RAM principal thiếu action | Kiểm tra policy dysms:* cần thiết |
| QPS_LIMIT_CONTROL | Vượt quota API | Giảm tốc độ, backoff và kiểm tra Quota Center |
| AMOUNT_NOT_ENOUGH | Hết resource package hoặc số dư | Kiểm tra billing/resource package |
| SMS_SECURITY_INTERCEPTED | Bị risk-control policy chặn | Kiểm tra nội dung, tần suất và quy định SMS |
| SYSTEM_ERROR | Lỗi nền tảng tạm thời | Ghi RequestId, retry có giới hạn sau khi phân loại |

Không retry vô hạn lỗi permission, signature/template, số điện thoại, risk-control hoặc hết quota. Các lỗi này cần sửa cấu hình, nội dung hoặc tài khoản trước.

## 12. Đánh giá Aliyun SMS Spring Boot Starter legacy

Alibaba có aliyun-sms-spring-boot-starter thuộc dự án aliyun-spring-boot. Artifact trên Maven Central là **1.0.0**. POM của starter kéo:

- aliyun-java-sdk-core
- aliyun-java-sdk-dysmsapi
- aliyun-sdk-mns
- aliyun-context-spring-boot-starter

Sample của dự án sử dụng ISmsService, SendSmsRequest, SmsReportMessageListener và cấu hình alibaba.cloud.access-key, alibaba.cloud.secret-key, alibaba.cloud.sms.report-queue-name. Đây là API và cách cấu hình legacy, không phải ví dụ của Java OpenAPI SDK V2 dysmsapi20180501.

README của repository chỉ công bố hỗ trợ Spring Boot 2 trở lên, không có ma trận cụ thể chứng minh tương thích Boot 3/4. Do đó:

- **Ứng dụng hiện hữu đã dùng starter:** có thể giữ nếu đã test đúng Boot/JDK, API và MNS queue; kiểm tra version SDK transitive, credentials và callback behavior.
- **Dự án mới hoặc Boot 3/4:** ưu tiên Java OpenAPI SDK V2 trực tiếp, tạo bean/client và adapter rõ ràng.
- **Cần tính năng mới của SMS API:** kiểm tra API V2 hiện hành trước; không giả định starter legacy đã bọc các API mới như SendMessageWithTemplate hoặc QueryMessage.

Nếu giữ starter, đọc sample và source của đúng version trước khi sao chép property. Không trộn ISmsService legacy với generated SDK V2 client trong cùng một luồng gửi mà không có adapter và kiểm soát version.

## 13. Bài tập thực hành

**Bài tập:** xây dựng notification service gửi SMS xác nhận đơn hàng và xử lý delivery receipt.

1. Tạo SMS account test và hoàn tất các yêu cầu xác minh.
2. Với Go China, tạo signature/template notification và chờ Approved; với Go Globe, kiểm tra sender ID và quy định quốc gia đích.
3. Thêm dysmsapi20180501 và credentials-java vào Spring Boot.
4. Tạo Credentials client và SMS client singleton, cấu hình endpoint theo region.
5. Viết SmsSender adapter gọi SendMessageWithTemplate cho Go China hoặc SendMessageToGlobe cho quốc tế.
6. Ghi notification intent vào outbox và để worker gửi bất đồng bộ.
7. Lưu MessageId, RequestId, template version, số segment và trạng thái SUBMITTED.
8. Cấu hình SmsReport hoặc GlobeSmsReport qua HTTP callback/SMQ.
9. Viết receipt processor idempotent và kiểm thử callback trùng, callback batch, callback đến trễ.
10. Dùng QueryMessage để reconcile message thiếu receipt.
11. Mô phỏng timeout, template bị từ chối, số điện thoại sai, hết quota và QPS throttling.
12. So sánh SDK V2 trực tiếp với aliyun-sms-spring-boot-starter 1.0.0 về API, credentials, callback và khả năng nâng cấp.

**Câu hỏi ôn tập:**

1. Vì sao Go China và Go Globe dùng hai API gửi khác nhau?
2. SendMessageWithTemplate có thể gửi tới số điện thoại Việt Nam không? Vì sao?
3. ResponseCode = OK khác Status = Delivered như thế nào?
4. TemplateParam phải khớp template ra sao?
5. Vì sao signature/template đã duyệt không thể được chỉnh trực tiếp?
6. MessageId và RequestId dùng để làm gì?
7. Tại sao callback receipt phải được xử lý idempotent?
8. Vì sao callback Status = 1 không nên tự động ánh xạ giống QueryMessage.Status = 1?
9. Khi SDK timeout nhưng chưa nhận response, vì sao không nên gửi lại ngay?
10. Khi nào dùng HTTP webhook và khi nào dùng SMQ queue?
11. RAM role cần action nào để gửi và query SMS?
12. Vì sao dự án mới nên đánh giá Java OpenAPI SDK V2 thay cho starter legacy 1.0.0?

## 14. Tài liệu tham khảo

- [Alibaba Cloud SMS — Integration overview](https://www.alibabacloud.com/help/en/sms/developer-reference/using-openapi): cách chọn API/SDK, Go China và Go Globe.
- [Alibaba Cloud SMS — Getting started](https://www.alibabacloud.com/help/en/sms/getting-started/get-started-with-sms): điều kiện kích hoạt, compliance, thời gian duyệt và billing.
- [Alibaba Cloud SMS — Java SDK](https://www.alibabacloud.com/help/en/sms/developer-reference/using-java-openapi-example): dependency dysmsapi20180501, credentials và Java sample.
- [SendMessageWithTemplate](https://www.alibabacloud.com/help/en/sms/developer-reference/api-dysmsapi-2018-05-01-sendmessagewithtemplate): API template cho Trung Quốc đại lục, request/response và RAM action.
- [SendMessageToGlobe](https://www.alibabacloud.com/help/en/sms/developer-reference/api-dysmsapi-2018-05-01-sendmessagetoglobe): API SMS quốc tế, sender ID, type và quota.
- [QueryMessage](https://www.alibabacloud.com/help/en/sms/developer-reference/api-dysmsapi-2018-05-01-querymessage): tra cứu delivery status theo MessageId.
- [SMS endpoints](https://www.alibabacloud.com/help/en/sms/developer-reference/api-dysmsapi-2018-05-01-endpoint): endpoint public/VPC theo region.
- [Signature and template review](https://www.alibabacloud.com/help/en/sms/user-guide/approval-process): trạng thái và quy trình duyệt.
- [Create SMS template](https://www.alibabacloud.com/help/en/sms/user-guide/create-message-templates): loại template, biến, giới hạn và consent.
- [API updates for signatures and templates](https://help.aliyun.com/en/sms/announcement-on-sms-service-update-signature-template-interface): API quản lý signature/template mới.
- [Configure SMS delivery receipts](https://www.alibabacloud.com/help/en/sms/developer-reference/obtain-delivery-receipt/): HTTP callback và SMQ queue.
- [SMS webhook](https://www.alibabacloud.com/help/en/sms/developer-reference/sms-webhook): payload receipt, message type và xử lý queue.
- [SMS flow-control information](https://www.alibabacloud.com/help/en/sms/developer-reference/api-dysmsapi-2018-05-01-quota): QPS limit theo operation.
- [International SMS error codes](https://www.alibabacloud.com/help/en/sms/developer-reference/error-codes): lỗi API, sender, template, quota và delivery.
- [Aliyun Spring Boot Starters](https://github.com/alibaba/aliyun-spring-boot): source và sample của SMS starter legacy.
- [Maven Central — dysmsapi20180501](https://central.sonatype.com/artifact/com.aliyun/dysmsapi20180501): version SDK Java V2.
- [Maven Central — aliyun-sms-spring-boot-starter](https://central.sonatype.com/artifact/com.alibaba.cloud/aliyun-sms-spring-boot-starter): POM và dependency của starter legacy.

**Kết quả mong đợi:** người học tích hợp được SMS vào Spring Boot theo đúng luồng Go China/Go Globe, dùng signature/template hoặc sender ID hợp lệ, quản lý RAM credentials, lưu MessageId, nhận và đối soát delivery receipt, xử lý callback trùng/thiếu và kiểm soát quota, retry cùng chi phí gửi tin.
