# Xác minh chữ ký, xác nhận subscription và xử lý thông báo HTTP

## 1. Vì sao HTTP endpoint phải xác minh thông điệp SNS?

Trong kiến trúc tích hợp Spring Boot với cloud managed services, một publisher gửi thông báo vào **Amazon Simple Notification Service (SNS)**, sau đó SNS chuyển HTTP POST tới một **HTTPS endpoint** đã đăng ký. Endpoint có thể là dịch vụ Java trong AWS hoặc một hệ thống bên ngoài AWS. Đây là cách kết nối các ứng dụng khi consumer không nhận trực tiếp từ Amazon SQS.

Điểm quan trọng: bất kỳ khách hàng Internet nào biết URL webhook đều có thể thử gửi HTTP POST đến đó. **Header mang tên x-amz-sns-message-type, JSON có trường TopicArn, hoặc User-Agent giống SNS không phải bằng chứng xác thực.** Endpoint chỉ nên xử lý thông báo sau khi **xác minh chữ ký số**, kiểm tra **topic ARN được cho phép** và xác nhận rằng thông điệp đến từ SNS.

Bài học này thuộc chương **Amazon SNS và SES**, trong module **SPRING_CLOUD_PROVIDER_INTEGRATION**. Module hướng đến thực hành Spring Boot tích hợp dịch vụ managed của AWS, Azure và Google Cloud qua thư viện Spring Cloud, đồng thời học danh tính, quyền, messaging, quản lý secret, kiểm thử tích hợp và so sánh provider. Trọng tâm bài là **quy trình nhận thông báo SNS qua HTTP/S, xác minh chữ ký, xác nhận subscription và xử lý thông báo an toàn**. SES là dịch vụ gửi email giao dịch riêng biệt; ứng dụng có thể nhận sự kiện SNS rồi gọi SES ở một bước nghiệp vụ sau đó.

**Mục tiêu học tập:**

- Mô tả vòng đời subscription HTTP/S: tạo, nhận **SubscriptionConfirmation**, xác nhận, nhận **Notification** và phản ứng với **UnsubscribeConfirmation**.
- Đọc đúng SNS JSON envelope và HTTP headers, bao gồm trường tùy chọn **Subject**.
- Hiểu cơ chế xác minh chữ ký SNS **SignatureVersion 1/2**, canonical string, SigningCertURL và các điều kiện ngăn giả mạo/SSRF.
- Xây REST endpoint Spring Boot nhận content type **text/plain** mặc định, xử lý từng loại message và trả mã HTTP phù hợp.
- Phân biệt việc webhook xác nhận nhận message với việc xử lý nghiệp vụ, triển khai **idempotent inbox** và thử lại khi lỗi.
- Kiểm thử các trường hợp chữ ký sai, topic không được phép, xác nhận sai, retry, duplicate và lỗi đầu cuối.

## 2. Vòng đời HTTPS subscription

~~~mermaid
sequenceDiagram
    participant A as Operator / IaC
    participant S as Amazon SNS
    participant W as Spring Boot HTTPS webhook
    participant D as Durable inbox
    participant C as Consumer

    A->>S: Subscribe(topic, https endpoint)
    S->>W: POST SubscriptionConfirmation
    W->>W: Validate body, topic, signer URL and signature
    W->>S: ConfirmSubscription(topicArn, token)
    S-->>W: SubscriptionArn
    W-->>S: HTTP 2xx
    A->>S: Publish event
    S->>W: POST Notification
    W->>W: Verify SNS signature and allowed topic
    W->>D: Persist message once
    D-->>W: Commit successful
    W-->>S: HTTP 204
    C->>D: Read and process event
~~~

**Ba loại thông báo SNS HTTP/S:**

| Giá trị Type | Khi nào xuất hiện? | Hành động hợp lý |
| --- | --- | --- |
| **SubscriptionConfirmation** | Khi một HTTP/S endpoint mới được subscribe | Kiểm tra chữ ký, topic cho phép, token rồi gọi **ConfirmSubscription** hoặc thực hiện quy trình xác nhận đã duyệt |
| **Notification** | Sau khi subscription đã xác nhận, có message được publish và được chọn để giao | Xác minh chữ ký rồi ghi sự kiện vào durable inbox/queue; trả 2xx khi chấp nhận thành công |
| **UnsubscribeConfirmation** | Khi subscription bị hủy | Xác minh; ghi nhận và cảnh báo cho vận hành; chỉ khôi phục subscription theo quy trình đã duyệt |

Endpoint **không nhận Notification** cho đến khi subscription được xác nhận. Một yêu cầu subscribe có thể đang ở trạng thái **PendingConfirmation**. Nếu tự động xác nhận thì ứng dụng phải ràng buộc chặt với **TopicArn** đã được phê duyệt; nếu triển khai xác nhận thủ công, cần lưu token trong kho bảo vệ và thực hiện trước khi hết hiệu lực.

### 2.1. HTTP request có hình dạng nào?

Theo mặc định, SNS POST đến HTTP/S endpoint với **Content-Type: text/plain; charset=UTF-8** dù body là một JSON document. Vì vậy, một controller chỉ khai báo nhận **application/json** có thể trả **415 Unsupported Media Type** trước cả khi đọc được message.

Ví dụ rút gọn:

~~~http
POST /webhooks/sns HTTP/1.1
Content-Type: text/plain; charset=UTF-8
x-amz-sns-message-type: Notification
x-amz-sns-message-id: 55ee4dbe-1111-4444-9999-123456789abc
x-amz-sns-topic-arn: arn:aws:sns:ap-southeast-1:123456789012:order-events

{
  "Type": "Notification",
  "MessageId": "55ee4dbe-1111-4444-9999-123456789abc",
  "TopicArn": "arn:aws:sns:ap-southeast-1:123456789012:order-events",
  "Message": "{\"eventId\":\"evt-1001\",\"eventType\":\"ORDER_CREATED\"}",
  "Timestamp": "2026-11-24T08:00:00.000Z",
  "SignatureVersion": "2",
  "Signature": "<base64-rsa-signature>",
  "SigningCertURL": "https://sns.ap-southeast-1.amazonaws.com/SimpleNotificationService-example.pem"
}
~~~

Đoạn trên là **ví dụ minh họa cấu trúc**, không có chữ ký hợp lệ để gửi trực tiếp làm test dương tính. Ngoài JSON body, SNS gửi các header như **x-amz-sns-message-type**, **x-amz-sns-message-id**, **x-amz-sns-topic-arn** và có thể có **x-amz-sns-subscription-arn**. Header hữu ích để định tuyến/quan sát, nhưng **không thay thế xác minh chữ ký** của body.

Với một **Notification**, các trường quan trọng thường gồm **Type**, **MessageId**, **TopicArn**, **Message**, **Timestamp**, **SignatureVersion**, **Signature**, **SigningCertURL**, cùng **Subject**, **MessageAttributes**, **UnsubscribeURL** khi có. Trường **Message** có thể là chuỗi JSON đã escape: trước hết parse *envelope*, sau đó mới parse chuỗi **Message** thành sự kiện nghiệp vụ.

Với **SubscriptionConfirmation** và **UnsubscribeConfirmation**, các trường dùng cho xác nhận/khôi phục gồm **Token** và **SubscribeURL**. Đừng truy cập SubscribeURL khi chưa xác minh toàn bộ thông điệp.

## 3. Cơ chế chữ ký của Amazon SNS

SNS ký những trường cố định trong thông điệp. Endpoint lấy khóa công khai từ chứng thư được công bố tại **SigningCertURL** thuộc miền AWS SNS đáng tin cậy, tạo lại chuỗi dữ liệu đúng thứ tự, giải mã **Signature** Base64 rồi kiểm tra RSA signature.

### 3.1. SignatureVersion 1 và 2

| Phiên bản | Thuật toán Java/JCA | Nhận xét |
| --- | --- | --- |
| **1** | **SHA1withRSA** | Tương thích cấu hình SNS truyền thống; AWS dùng mặc định cho topic nếu chưa đổi |
| **2** | **SHA256withRSA** | Được AWS khuyến nghị cho hệ thống mới |

Đặt topic sử dụng phiên bản chữ ký mạnh hơn:

~~~bash
aws sns set-topic-attributes \
  --topic-arn "$TOPIC_ARN" \
  --attribute-name SignatureVersion \
  --attribute-value 2 \
  --region ap-southeast-1
~~~

Khi ứng dụng chỉ chấp nhận version 2, hãy chắc chắn topic đã thực sự được cấu hình 2 và quá trình chuyển đổi không làm gián đoạn endpoint. Các ví dụ sau xử lý cả hai version để diễn giải giao thức; với topic kiểm soát hoàn toàn, có thể ràng buộc **SignatureVersion=2** ở mức policy của ứng dụng.

### 3.2. Dựng đúng chuỗi cần xác minh

SNS dùng **tên trường + ký tự xuống dòng LF + giá trị + LF** theo một **thứ tự cố định**. Phải giữ nguyên nội dung đã giải mã JSON, bao gồm xuống dòng thực trong **Message/Subject**. Không ký lại toàn bộ JSON, không sắp xếp theo thứ tự key từ bản request, và không thêm khoảng trắng tùy ý.

| Type | Thứ tự các trường trong canonical string |
| --- | --- |
| **Notification** | Message, MessageId, **Subject nếu có**, Timestamp, TopicArn, Type |
| **SubscriptionConfirmation** | Message, MessageId, SubscribeURL, Timestamp, Token, TopicArn, Type |
| **UnsubscribeConfirmation** | Message, MessageId, SubscribeURL, Timestamp, Token, TopicArn, Type |

Ví dụ cấu trúc canonical string cho Notification **không có Subject**:

~~~text
Message
{"eventId":"evt-1001","eventType":"ORDER_CREATED"}
MessageId
55ee4dbe-1111-4444-9999-123456789abc
Timestamp
2026-11-24T08:00:00.000Z
TopicArn
arn:aws:sns:ap-southeast-1:123456789012:order-events
Type
Notification
~~~

Sau dòng **Notification** cuối cùng còn **một ký tự LF**. Trong mã Java, dùng UTF-8 và nối rõ ràng **\n** sau mỗi tên và giá trị.

### 3.3. Ràng buộc SigningCertURL để tránh SSRF

**SigningCertURL đến từ dữ liệu chưa xác thực**. Nếu tải trực tiếp bất kỳ URL nào trong body, kẻ tấn công có thể ép server yêu cầu địa chỉ nội bộ, cloud metadata endpoint hoặc chứng thư do họ tự tạo. Trước khi tải chứng thư, cần:

1. Chỉ cho phép giao thức **https** và **hostname SNS đúng region/partition đã phê duyệt** (với bài này là **sns.ap-southeast-1.amazonaws.com**).
2. So sánh **hostname chính xác**, không dùng quy tắc **contains("amazonaws.com")** hoặc hậu tố chuỗi có thể bị lừa.
3. Từ chối userinfo, cổng tùy ý, query/fragment và đường dẫn không có dạng chứng thư SNS được mong đợi.
4. Không tự động follow redirect; bật TLS hostname verification và CA trust mặc định khi tải từ endpoint AWS.
5. Kiểm tra thời hạn, chuỗi tin cậy/nguồn phát hành chứng thư theo chính sách an ninh và xác minh RSA signature; không coi **checkValidity()** đơn lẻ là kiểm tra trust chain.
6. Giới hạn kích thước tải về, kết nối và thời gian đáp ứng; cache chứng thư đã kiểm tra với TTL phù hợp nếu lưu lượng lớn.

**Quan trọng:** Chữ ký có thể đúng với một topic khác mà bạn không tin dùng. Phải so khớp **TopicArn bằng chính xác ARN cho phép**, đồng thời hạn chế region và AWS account theo cấu hình. Chữ ký xác nhận nguồn và tính toàn vẹn của thông điệp; cơ chế **idempotency** và chính sách phát lại vẫn cần ở tầng nghiệp vụ.

## 4. Tạo topic và đăng ký HTTPS endpoint

Giả sử Spring Boot công khai endpoint **https://api.example.com/webhooks/sns** với chứng thư HTTPS hợp lệ. Endpoint phải hoạt động trước khi gọi Subscribe để nhận được confirmation message.

~~~bash
aws sns subscribe \
  --topic-arn "$TOPIC_ARN" \
  --protocol https \
  --notification-endpoint "https://api.example.com/webhooks/sns" \
  --region ap-southeast-1
~~~

Lệnh Subscribe tạo đăng ký đang chờ xác nhận. Khi SNS POST **SubscriptionConfirmation**, ứng dụng có hai lựa chọn:

- **Có kiểm soát và tự động:** Sau khi kiểm tra chữ ký và TopicArn, gọi **ConfirmSubscription** với **Token**; lưu lại SubscriptionArn.
- **Có bước duyệt:** Lưu thông tin yêu cầu vào kho nội bộ, thông báo người có quyền duyệt và chỉ gọi ConfirmSubscription sau khi duyệt. Không ghi token/SubscribeURL lên log công khai.

AWS cũng cho phép truy cập **SubscribeURL** đã ký để xác nhận. Với ứng dụng Java có quyền AWS và kiểm soát được topic, gọi **ConfirmSubscription API** bằng token thường dễ quản lý và tránh tạo HTTP GET từ URL do request cung cấp.

Sau xác nhận, kiểm tra thông tin subscription:

~~~bash
aws sns list-subscriptions-by-topic \
  --topic-arn "$TOPIC_ARN" \
  --region ap-southeast-1
~~~

Subscription phải có **SubscriptionArn** thực, không còn PendingConfirmation. Ở môi trường AWS thương mại, nên cấu hình HTTPS endpoint, DNS và certificate hợp lệ với CA mà SNS tin cậy.

### 4.1. Không bật raw delivery cho webhook xác minh envelope

Với **RawMessageDelivery=false** (mặc định), HTTP/S body chứa SNS envelope với Signature, SigningCertURL và các trường cần kiểm chứng. Nếu bật **RawMessageDelivery=true**, SNS gửi body message gốc và loại bỏ lớp SNS envelope: handler dùng thuật toán xác minh envelope của bài này sẽ **không còn đủ trường để xác minh chữ ký SNS**. Vì vậy ví dụ giữ **RawMessageDelivery=false**.

Điều này khác với SNS → SQS nơi raw delivery thường được dùng để worker đọc trực tiếp JSON domain.

## 5. Cấu hình Spring Boot

Ví dụ dùng **Spring Boot 3.x**, **Java 17+**, **AWS SDK for Java v2** và **Spring Cloud AWS 3.x**. Chọn phiên bản Spring Cloud AWS BOM tương thích với Spring Boot của dự án.

~~~groovy
dependencies {
    implementation(platform("io.awspring.cloud:spring-cloud-aws-dependencies:${springCloudAwsVersion}"))
    implementation("io.awspring.cloud:spring-cloud-aws-starter-sns")
    implementation("org.springframework.boot:spring-boot-starter-web")
    implementation("org.springframework.boot:spring-boot-starter-jdbc")
    runtimeOnly("org.postgresql:postgresql")
}
~~~

**application.yml** (các giá trị nhạy cảm lấy từ môi trường/secret manager):

~~~yaml
spring:
  cloud:
    aws:
      region:
        static: ${AWS_REGION:ap-southeast-1}
  datasource:
    url: ${DB_URL}
    username: ${DB_USER}
    password: ${DB_PASSWORD}

app:
  sns:
    expected-topic-arn: ${ORDER_EVENTS_TOPIC_ARN}
    expected-signing-cert-host: sns.ap-southeast-1.amazonaws.com
~~~

Không commit thông tin xác thực AWS hoặc mật khẩu database vào Git. Trong AWS, ưu tiên **IAM role** gắn với workload; ở máy phát triển dùng AWS profile/credentials provider chain. Client SNS phải truy cập đúng region của topic. Cấp quyền theo nguyên tắc tối thiểu; **ConfirmSubscription** có thể phụ thuộc điều kiện xác thực/quyền của SNS topic và cấu hình subscription.

## 6. Xây lớp xác minh chữ ký

Đoạn Java sau minh họa **thuật toán xác minh và các giới hạn URL**. Nó giả định endpoint thuộc partition AWS thương mại và host SNS được cấu hình đúng region. Khi đưa vào production, cần dùng verifier đã được kiểm thử hoặc bổ sung kiểm tra PKIX/issuer và chính sách trust của tổ chức cho chính signing certificate; **TLS của kết nối tải file và certificate.checkValidity() chưa thay thế toàn bộ kiểm tra trust chain**.

~~~java
package demo.sns;

import com.fasterxml.jackson.databind.JsonNode;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

import java.io.ByteArrayInputStream;
import java.io.IOException;
import java.io.InputStream;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.security.Signature;
import java.security.cert.CertificateFactory;
import java.security.cert.X509Certificate;
import java.time.Duration;
import java.util.Base64;
import java.util.List;

@Component
public class SnsSignatureVerifier {
    private static final int MAX_CERT_BYTES = 65536;

    private final String expectedTopicArn;
    private final String expectedCertHost;
    private final HttpClient http = HttpClient.newBuilder()
            .connectTimeout(Duration.ofSeconds(3))
            .followRedirects(HttpClient.Redirect.NEVER)
            .build();

    public SnsSignatureVerifier(
            @Value("${app.sns.expected-topic-arn}") String expectedTopicArn,
            @Value("${app.sns.expected-signing-cert-host}") String expectedCertHost) {
        this.expectedTopicArn = expectedTopicArn;
        this.expectedCertHost = expectedCertHost;
    }

    public boolean verify(JsonNode sns) throws Exception {
        if (!expectedTopicArn.equals(value(sns, "TopicArn"))) {
            return false;
        }

        String type = value(sns, "Type");
        String version = value(sns, "SignatureVersion");
        if (!version.equals("1") && !version.equals("2")) {
            return false;
        }

        List<String> fields = switch (type) {
            case "Notification" -> List.of(
                    "Message", "MessageId", "Subject",
                    "Timestamp", "TopicArn", "Type");
            case "SubscriptionConfirmation", "UnsubscribeConfirmation" ->
                    List.of("Message", "MessageId", "SubscribeURL",
                            "Timestamp", "Token", "TopicArn", "Type");
            default -> List.of();
        };
        if (fields.isEmpty()) {
            return false;
        }

        StringBuilder canonical = new StringBuilder();
        for (String field : fields) {
            if (field.equals("Subject") && !sns.has("Subject")) {
                continue; // Subject là trường tùy chọn của Notification
            }
            canonical.append(field).append('\n')
                    .append(value(sns, field)).append('\n');
        }

        URI certificateUri = URI.create(value(sns, "SigningCertURL"));
        if (!trustedSignerUri(certificateUri)) {
            return false;
        }

        X509Certificate certificate = fetchSigningCertificate(certificateUri);
        certificate.checkValidity();

        Signature verifier = Signature.getInstance(
                version.equals("2") ? "SHA256withRSA" : "SHA1withRSA");
        verifier.initVerify(certificate.getPublicKey());
        verifier.update(canonical.toString().getBytes(StandardCharsets.UTF_8));

        byte[] decodedSignature = Base64.getDecoder()
                .decode(value(sns, "Signature"));
        return verifier.verify(decodedSignature);
    }

    private boolean trustedSignerUri(URI uri) {
        return "https".equalsIgnoreCase(uri.getScheme())
                && expectedCertHost.equalsIgnoreCase(uri.getHost())
                && uri.getPort() == -1
                && uri.getRawUserInfo() == null
                && uri.getRawQuery() == null
                && uri.getRawFragment() == null
                && uri.getRawPath() != null
                && uri.getRawPath().matches(
                        "/SimpleNotificationService-[A-Za-z0-9-]+\\.pem");
    }

    private X509Certificate fetchSigningCertificate(URI uri)
            throws Exception {
        HttpRequest request = HttpRequest.newBuilder(uri)
                .timeout(Duration.ofSeconds(6))
                .GET()
                .build();

        HttpResponse<InputStream> response = http.send(
                request, HttpResponse.BodyHandlers.ofInputStream());

        try (InputStream stream = response.body()) {
            if (response.statusCode() != 200) {
                throw new IOException("SNS signing certificate unavailable");
            }

            byte[] data = stream.readNBytes(MAX_CERT_BYTES + 1);
            if (data.length > MAX_CERT_BYTES) {
                throw new IOException("SNS certificate too large");
            }
            return (X509Certificate) CertificateFactory
                    .getInstance("X.509")
                    .generateCertificate(new ByteArrayInputStream(data));
        }
    }

    private static String value(JsonNode json, String field) {
        JsonNode node = json.get(field);
        if (node == null || !node.isTextual() || node.asText().isBlank()) {
            throw new IllegalArgumentException("Missing or invalid " + field);
        }
        return node.asText();
    }
}
~~~

**Giải thích lựa chọn:**

- Đúng **TopicArn**, phiên bản chữ ký và **Type** được kiểm tra trước khi xác minh.
- **Subject** chỉ xuất hiện trong canonical string nếu trường đó tồn tại.
- **SubscribeURL** và **Token** thuộc canonical string của confirmation/unsubscribe, nên không thể bị thay đổi mà chữ ký vẫn hợp lệ.
- **URI** phải có HTTPS và hostname **khớp chính xác**. Không follow redirect; giới hạn thời gian và kích thước chứng thư để giảm ảnh hưởng của yêu cầu độc hại.
- **Signature.verify** dùng khóa công khai của signing certificate; chuỗi đầu vào được nối bằng **LF** và mã hóa UTF-8.
- **Không dùng phép so sánh trực tiếp Signature string với một hash**: chữ ký SNS là RSA signature được Base64-encode.
- Ví dụ không tự triển khai cơ chế cache chứng thư và PKIX trust-chain độc lập; bổ sung những phần này trong triển khai production và kiểm thử với chứng thư/chữ ký SNS thật.

**Phân biệt các lỗi:** chữ ký không đúng, trường sai hay URL chứng thư không được phép phải bị từ chối. Nếu AWS certificate endpoint tạm thời lỗi hoặc mạng không thể truy cập, có thể trả lỗi server 5xx để SNS thử lại, nhưng phải giới hạn thời gian và ghi log lỗi gọn, không in token/chữ ký.

## 7. REST controller nhận và xử lý ba loại message

Controller nhận **@RequestBody String** và không cố định **consumes=application/json**, bởi SNS có thể gửi **text/plain**. So sánh header và Type trong body, sau đó gọi verifier **trước mọi tác động nghiệp vụ hoặc xác nhận**.

Ví dụ bên dưới sử dụng **SnsClient** từ AWS SDK v2, cùng **SnsInboxRepository** được giới thiệu ở mục 8. Giả định verifier đã được cấu hình và mọi request tới endpoint trải qua TLS termination được tin cậy.

~~~java
package demo.sns;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;
import software.amazon.awssdk.services.sns.SnsClient;
import software.amazon.awssdk.services.sns.model.ConfirmSubscriptionRequest;

import java.security.GeneralSecurityException;

@RestController
@RequestMapping("/webhooks/sns")
public class SnsWebhookController {
    private static final Logger log =
            LoggerFactory.getLogger(SnsWebhookController.class);

    private final ObjectMapper mapper;
    private final SnsSignatureVerifier verifier;
    private final SnsClient sns;
    private final SnsInboxRepository inbox;
    private final String allowedTopicArn;

    public SnsWebhookController(
            ObjectMapper mapper,
            SnsSignatureVerifier verifier,
            SnsClient sns,
            SnsInboxRepository inbox,
            @Value("${app.sns.expected-topic-arn}") String allowedTopicArn) {
        this.mapper = mapper;
        this.verifier = verifier;
        this.sns = sns;
        this.inbox = inbox;
        this.allowedTopicArn = allowedTopicArn;
    }

    @PostMapping
    public ResponseEntity<Void> accept(
            @RequestHeader(value = "x-amz-sns-message-type",
                    required = false) String headerType,
            @RequestBody String rawBody) throws Exception {

        final JsonNode body;
        try {
            body = mapper.readTree(rawBody);
        } catch (JsonProcessingException e) {
            return ResponseEntity.badRequest().build();
        }

        if (body == null || !body.isObject()) {
            return ResponseEntity.badRequest().build();
        }

        String messageType = body.path("Type").asText("");
        if (!messageType.equals(headerType)) {
            return ResponseEntity.badRequest().build();
        }

        if (!messageType.equals("Notification")
                && !messageType.equals("SubscriptionConfirmation")
                && !messageType.equals("UnsubscribeConfirmation")) {
            return ResponseEntity.badRequest().build();
        }

        try {
            if (!verifier.verify(body)) {
                return ResponseEntity.status(HttpStatus.FORBIDDEN).build();
            }
        } catch (IllegalArgumentException | GeneralSecurityException e) {
            return ResponseEntity.status(HttpStatus.FORBIDDEN).build();
        }
        // Lỗi mạng/tải chứng thư và lỗi hạ tầng được trả 5xx để SNS thử lại.

        switch (messageType) {
            case "SubscriptionConfirmation" -> {
                sns.confirmSubscription(ConfirmSubscriptionRequest.builder()
                        .topicArn(allowedTopicArn)
                        .token(body.path("Token").asText())
                        .build());
                log.info("Confirmed subscription for {}", allowedTopicArn);
                return ResponseEntity.noContent().build();
            }
            case "Notification" -> {
                inbox.saveOnce(
                        body.path("MessageId").asText(),
                        allowedTopicArn,
                        body.path("Message").asText()
                );
                return ResponseEntity.noContent().build();
            }
            case "UnsubscribeConfirmation" -> {
                log.warn("SNS subscription removed for topic {}", allowedTopicArn);
                // Cảnh báo vận hành; không tự ý resubscribe.
                return ResponseEntity.noContent().build();
            }
            default -> {
                return ResponseEntity.badRequest().build();
            }
        }
    }
}
~~~

**Giải thích luồng:**

1. Parse JSON envelope bằng Jackson, kiểm tra **Type** trong body và header phải tương ứng.
2. Gọi **SnsSignatureVerifier.verify**. Nếu thất bại, trả 403, không xử lý nội dung và không xác nhận subscription.
3. Với **SubscriptionConfirmation**, dùng **Token đã nằm trong dữ liệu có chữ ký** để gọi **ConfirmSubscription** tới topic đã cho phép. Không gửi HTTP GET tới một **SubscribeURL** bất kỳ do client cung cấp.
4. Với **Notification**, ghi message đã xác minh vào kho bền vững **trước khi trả HTTP 204**. Worker xử lý nghiệp vụ sau đó.
5. Với **UnsubscribeConfirmation**, phát cảnh báo để điều tra nguyên nhân; không âm thầm đăng ký lại topic khi có thể người quản trị đã chủ động hủy.

Ví dụ tự động xác nhận này phù hợp khi endpoint chỉ cho phép **một topic đã được cấu hình và phê duyệt**. Nếu tổ chức yêu cầu duyệt từng subscription, thay nhánh confirmation bằng ghi **pending request** vào kho an toàn và chỉ gọi ConfirmSubscription trong luồng phê duyệt riêng.

**Lưu ý vận hành:** mã 400/403 cho request sai định dạng hoặc chữ ký là lỗi client thường không được SNS retry; mã 5xx hoặc 429 phù hợp cho lỗi tạm thời cần thử lại. Lỗi khi xác nhận, khi ghi inbox hoặc khi gọi AWS có thể khiến endpoint trả 5xx và nhận lại cùng message, nên handler phải idempotent.

## 8. Xử lý Notification bằng durable inbox

### 8.1. Vì sao không trả 200 trước khi lưu dữ liệu?

Nếu endpoint trả 200 ngay khi đọc HTTP POST rồi mới xử lý trong một thread nền **không bền vững**, tiến trình có thể bị dừng sau khi trả 200; SNS coi giao nhận thành công, còn sự kiện bị mất. Mô hình **durable inbox** ghi message vào database hoặc queue trước khi trả 2xx.

Ví dụ với PostgreSQL (chỉ minh họa một lựa chọn; có thể dùng SQS/stream/kho sự kiện tương đương):

~~~sql
CREATE TABLE sns_inbox (
    message_id VARCHAR(100) PRIMARY KEY,
    topic_arn VARCHAR(350) NOT NULL,
    event_payload TEXT NOT NULL,
    received_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    processed_at TIMESTAMPTZ
);
~~~

Repository idempotent theo **MessageId** của SNS:

~~~java
package demo.sns;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;

@Repository
public class SnsInboxRepository {
    private final JdbcTemplate jdbc;

    public SnsInboxRepository(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    public void saveOnce(String messageId, String topicArn, String payload) {
        jdbc.update("""
                INSERT INTO sns_inbox(message_id, topic_arn, event_payload)
                VALUES (?, ?, ?)
                ON CONFLICT (message_id) DO NOTHING
                """, messageId, topicArn, payload);
    }
}
~~~

Câu SQL **ON CONFLICT DO NOTHING** giúp SNS retry cùng **MessageId** không tạo bản ghi trùng. Sau đó một worker đọc các bản ghi có **processed_at IS NULL**, áp dụng nghiệp vụ trong giao dịch phù hợp rồi cập nhật trạng thái. Nếu ứng dụng nhận nhiều topic, có thể chọn khóa tổng hợp **(topic_arn, message_id)** để làm idempotency key.

**Không có nghĩa mọi tác động nghiệp vụ tự động exactly-once.** Nếu worker thực thi thao tác ngoài database (gửi email, gọi API, chuyển tiền), cần idempotency ở chính tác động đó dựa trên **eventId**, transaction/outbox hoặc khóa nghiệp vụ phù hợp. **MessageId** ổn định với lần SNS retry cùng message; **eventId** do publisher tạo có thể phù hợp hơn khi cùng sự kiện được publish lại trong một yêu cầu mới.

### 8.2. Parse nội dung Message sau xác minh

Sau khi envelope đã qua verifier:

~~~java
String messageJson = verifiedEnvelope.path("Message").asText();
OrderCreated event = objectMapper.readValue(messageJson, OrderCreated.class);
~~~

Trong đó **OrderCreated** là DTO của ứng dụng. Nếu subscriber nhận thông báo text thuần không chứa JSON, hãy định nghĩa hợp đồng dữ liệu tương ứng. Không dùng chuỗi **Message** chưa được xác minh để chạy SQL, gọi endpoint nội bộ hay ra quyết định nghiệp vụ.

## 9. HTTP response, retry và dead-letter queue

SNS coi các mã HTTP **2xx** là giao nhận thành công. Đối với HTTP/S, SNS xem **5xx** và **429** là lỗi có thể thử lại theo delivery policy; các lỗi **4xx khác** thường bị coi là lỗi vĩnh viễn và không retry theo chính sách thông thường. Xem chính sách delivery hiện hành vì số lần thử và thời gian có thể được tùy chỉnh.

| Tình huống | Mã trả về đề xuất | Tác động |
| --- | --- | --- |
| Chữ ký sai hoặc topic không cho phép | **403** | Từ chối; không xử lý |
| JSON envelope sai, thiếu Type hoặc header không khớp | **400** | Không xử lý dữ liệu không hợp lệ |
| Notification đã ghi durable inbox thành công hoặc trùng đã nhận | **204** | Chấp nhận; SNS dừng retry |
| Confirmation đã được xử lý thành công | **204** | Subscription được xác nhận |
| Database/inbox tạm thời lỗi | **500/503** | SNS có thể retry theo policy |
| Server quá tải có kiểm soát | **429** | SNS có thể retry theo policy |

Tuy HTTP endpoint không nên xử lý lâu, bạn vẫn phải đảm bảo lưu dữ liệu bền vững **trước khi** trả 2xx. AWS mô tả HTTP endpoint có khoảng timeout ở mức **15 giây** cho một yêu cầu delivery; hãy thiết kế nhanh, có timeout khi tải chứng thư và khi gọi database. Với nhiều message, cache chứng thư đã xác minh trong thời gian hợp lý thay vì tải lại vô hạn.

Cấu hình **DeliveryPolicy** tại topic hoặc subscription để thay đổi retry/backoff/throttle. Ví dụ policy cho một subscription trong môi trường có tải cao:

~~~json
{
  "healthyRetryPolicy": {
    "minDelayTarget": 1,
    "maxDelayTarget": 60,
    "numRetries": 8,
    "numNoDelayRetries": 0,
    "numMinDelayRetries": 2,
    "numMaxDelayRetries": 2,
    "backoffFunction": "exponential"
  },
  "throttlePolicy": {
    "maxReceivesPerSecond": 20
  },
  "requestPolicy": {
    "headerContentType": "text/plain"
  }
}
~~~

Đây là ví dụ chính sách, cần cân đối theo SLA và quy mô tải thực tế. Muốn không mất message bị lỗi vĩnh viễn sau thử lại, cấu hình **SNS subscription DLQ** là một SQS queue để lưu message giao thất bại, cùng quyền cho SNS gửi vào DLQ. **Subscription DLQ** xử lý giao HTTP thất bại, không giống **SQS consumer DLQ** khi worker đã nhận message nhưng xử lý lỗi.

## 10. Kiểm thử chữ ký và webhook

Kiểm thử cần phân biệt **unit tests xác minh bộ lọc an ninh** với **integration tests giao nhận thực**. Có thể kiểm thử unit bằng một tập thông điệp chuẩn và chứng thư test có chuỗi tin cậy được kiểm soát; integration test dùng SNS ở AWS sandbox sẽ phản ánh chữ ký thực, TLS, domain và retry tốt hơn.

| Kiểm thử | Dữ liệu/biến đổi | Kết quả cần đạt |
| --- | --- | --- |
| **Notification hợp lệ** | Thông điệp SNS thật từ topic cho phép | Chữ ký hợp lệ; chỉ một inbox record; HTTP 204 |
| **Sai TopicArn** | Có thể hợp lệ về chữ ký nhưng topic khác allowlist | HTTP 403; không lưu |
| **Message bị sửa** | Thay eventType/orderId sau khi SNS ký | Chữ ký không hợp lệ; HTTP 403 |
| **Sai Signature** | Thay một byte trong chữ ký Base64 | HTTP 403; không lưu |
| **SigningCertURL giả** | URL HTTP, domain attacker, userinfo hoặc redirect | Từ chối; tuyệt đối không fetch host lạ |
| **Type/header bất đồng** | Header Notification nhưng body SubscriptionConfirmation | HTTP 400 |
| **Subject vắng mặt** | Notification không có Subject | Canonical string bỏ qua Subject, xác minh vẫn đúng |
| **Subject có mặt** | Notification có Subject | Canonical string bao gồm Subject theo đúng vị trí |
| **SignatureVersion không hỗ trợ** | Version khác 1 hoặc 2 | Từ chối |
| **Confirmation hợp lệ** | Token và SubscribeURL từ SNS thật | Xác minh rồi mới gọi ConfirmSubscription |
| **Confirmation giả** | Token tự tạo hoặc topic không cho phép | Không gọi ConfirmSubscription |
| **Notification retry** | Gửi lại cùng MessageId | Một inbox record, trả 2xx an toàn |
| **Inbox hỏng** | Database tạm thời không khả dụng | Trả 5xx, SNS có thể retry |
| **UnsubscribeConfirmation** | Thông điệp đã ký từ SNS | Ghi cảnh báo, không tự resubscribe |

**Lưu ý:** JSON giả với **Signature="EXAMPLE"** từ tài liệu không thể dùng làm positive test vì chữ ký không hợp lệ. Để kiểm thử lớp xác minh trong môi trường biệt lập, có thể thiết kế điểm tiêm **certificate loader/trust policy** cho signer test và dựng canonical string đúng thuật toán; production phải giữ allowlist SNS và trust chain nghiêm ngặt.

### 10.1. Quy trình tích hợp thử nghiệm

1. Deploy ứng dụng HTTPS có certificate hợp lệ; kiểm tra từ Internet và health endpoint phù hợp.
2. Tạo topic trong region mong muốn, bật SignatureVersion 2 và thiết lập IAM role cho workload.
3. Gọi Subscribe; theo dõi POST **SubscriptionConfirmation** và xác nhận rằng subscription thoát trạng thái pending.
4. Publish một JSON event bằng SNS, kiểm tra HTTP 204, record inbox và eventId.
5. Giả lập database lỗi để webhook trả 5xx, kiểm tra retry và **MessageId** không đổi trong lần gửi lại.
6. Kiểm tra điều kiện 403/400, metrics **NumberOfNotificationsFailed** và khả năng nhận message ở subscription DLQ.
7. Thử ngắt hệ thống trong lúc xử lý để bảo đảm đã lưu bền vững trước khi trả 2xx và inbox vẫn chống xử lý lặp.

CLI phát thông báo:

~~~bash
aws sns publish \
  --topic-arn "$TOPIC_ARN" \
  --message '{"eventId":"evt-1001","eventType":"ORDER_CREATED","orderId":"ord-1001"}' \
  --region ap-southeast-1
~~~

**Không** gửi HTTP POST trực tiếp với JSON giả rồi mong verifier trả 204; để xác minh luồng end-to-end, hãy publish thật qua SNS hoặc dùng test signer được cấu hình riêng cho test.

## 11. Bảo mật và vận hành: những lỗi thường gặp

### 11.1. Các lỗi an ninh cần tránh

- **Tin header không có chữ ký:** request do người ngoài tự dựng cũng có thể chứa **x-amz-sns-message-type: Notification**.
- **Tải chứng thư từ mọi URL:** mở đường cho SSRF và dùng khóa giả.
- **Chỉ gọi checkValidity():** kiểm tra thời hạn X.509 không chứng minh chuỗi CA hoặc xuất xứ từ SNS; cần kiểm tra trust phù hợp.
- **Chỉ kiểm tra Signature hợp lệ:** một thông báo từ topic khác vẫn có thể được SNS ký hợp lệ; bắt buộc allowlist TopicArn.
- **Truy cập SubscribeURL/UnsubscribeURL chưa kiểm chứng:** có thể xác nhận nhầm một subscription không mong muốn hoặc tạo HTTP GET không an toàn.
- **Auto-confirm tất cả topic:** dễ bị lợi dụng để gửi thông điệp từ topic ngoài ý muốn vào webhook.
- **Bật RawMessageDelivery** cho handler phụ thuộc envelope: mất trường signature cần kiểm chứng.
- **Log toàn bộ body/Token/SubscribeURL:** có thể rò rỉ thông tin nhạy cảm và dữ liệu khách hàng.
- **Trả 2xx trước khi lưu:** mất sự kiện nếu process chết ngay sau response.
- **Không idempotent:** message retry có thể khiến gửi email, ghi database hoặc gọi API hai lần.

### 11.2. Khắc phục sự cố vận hành

| Triệu chứng | Khả năng gây ra | Cách kiểm tra |
| --- | --- | --- |
| Subscription mãi PendingConfirmation | Endpoint không truy cập được, TLS lỗi, handler chưa xác nhận, confirmation bị trả 4xx | Logs, response HTTP, danh sách subscription |
| Endpoint nhận 415 | Controller chỉ nhận application/json, SNS gửi text/plain | Bỏ ràng buộc consumes hoặc cấu hình delivery policy |
| Verify signature thất bại với message thật | Sai canonical order, Subject xử lý sai, JSON escaped newline chưa decode, version sai | So sánh các trường gốc, dựng lại canonical string chính xác |
| SigningCertURL bị từ chối | Host/region khác cấu hình hoặc whitelist thiếu | Kiểm tra region topic và allowlist cert host |
| Vẫn nhận HTTP POST nhưng không có inbox record | Verifier từ chối hoặc database lỗi | Mã response, log lỗi gọn, metrics |
| Cùng event được xử lý nhiều lần | SNS retry hoặc worker retry | Khóa idempotency và MessageId/eventId |
| Không thấy retry | Webhook trả 400/403 thay vì lỗi tạm thời 5xx/429 | Delivery policy và HTTP status |
| SNS báo giao thành công nhưng nghiệp vụ thất bại | Handler trả 2xx trước khi lưu hoặc consumer xử lý sau đó bị lỗi | Durable inbox, worker retry/DLQ |

Giữ giới hạn độ lớn body tại gateway, rate limiting hợp lý, HTTPS bắt buộc, request timeout và metric cho tỷ lệ signature failure. Nếu cần bảo vệ endpoint hơn nữa, có thể giới hạn nguồn truy cập bằng cơ chế mạng/WAF phù hợp, nhưng **network allowlist không thay thế xác minh chữ ký**.

## 12. Câu hỏi tự kiểm tra và tài liệu tham khảo

**Bài tập:** xây một webhook Spring Boot nhận **SubscriptionConfirmation**, **Notification** và **UnsubscribeConfirmation** cho SNS topic **order-events**. Bật SignatureVersion 2, viết verifier có allowlist topic/cert host, ghi thông điệp vào PostgreSQL inbox, dùng SQL chống duplicate và mô phỏng một lần database lỗi để quan sát retry. Giải thích vì sao webhook không nên trực tiếp thực hiện tác vụ tốn thời gian ngay trong request.

**Câu hỏi cần trả lời:**

1. Vì sao chỉ dựa vào header x-amz-sns-message-type có thể bị giả mạo?
2. Canonical string của Notification có Subject khác trường hợp không có Subject thế nào?
3. SignatureVersion 1 và 2 sử dụng thuật toán gì? Vì sao nên ưu tiên 2?
4. Vì sao cần xác minh cả **SigningCertURL** và **TopicArn**?
5. Vì sao phải xác minh chữ ký trước khi gọi **ConfirmSubscription** bằng token?
6. RawMessageDelivery=true ảnh hưởng thế nào đến handler xác minh JSON envelope?
7. Trường hợp nào trả 204, 403, 429 hoặc 503? SNS sẽ retry trong tình huống nào?
8. Phân biệt **MessageId** của SNS và **eventId** của sự kiện; tại sao cần cả hai khi xử lý idempotent?

**Tài liệu chính thức:**

- [Amazon SNS — Verifying the signatures of SNS messages](https://docs.aws.amazon.com/sns/latest/dg/sns-verify-signature-of-message.html)
- [Amazon SNS — Canonical string and verifying a message signature](https://docs.aws.amazon.com/sns/latest/dg/sns-verify-signature-of-message-verify-message-signature.html)
- [Amazon SNS — Configure SignatureVersion](https://docs.aws.amazon.com/sns/latest/dg/sns-verify-signature-of-message-configure-message-signature.html)
- [Amazon SNS — HTTP/S subscription confirmation JSON](https://docs.aws.amazon.com/sns/latest/dg/http-subscription-confirmation-json.html)
- [Amazon SNS — HTTP/S notification JSON](https://docs.aws.amazon.com/sns/latest/dg/http-notification-json.html)
- [Amazon SNS — Unsubscribe confirmation JSON](https://docs.aws.amazon.com/sns/latest/dg/http-unsubscribe-confirmation-json.html)
- [Amazon SNS — HTTP/S endpoint preparation](https://docs.aws.amazon.com/sns/latest/dg/SendMessageToHttp.prepare.html)
- [Amazon SNS — Delivery retry policy](https://docs.aws.amazon.com/sns/latest/dg/sns-message-delivery-retries.html)
- [Amazon SNS — Raw message delivery](https://docs.aws.amazon.com/sns/latest/dg/sns-large-payload-raw-message-delivery.html)
- [AWS API — ConfirmSubscription](https://docs.aws.amazon.com/sns/latest/api/API_ConfirmSubscription.html)

**Kết quả mong đợi:** Người học có thể triển khai HTTPS webhook của Spring Boot với đầy đủ ba loại thông điệp SNS, chỉ xác nhận subscription và xử lý notification **sau khi xác minh chữ ký**, áp dụng giới hạn tin cậy cho SigningCertURL, lưu bền vững trước khi trả 2xx và kiểm tra được cơ chế retry/duplicate trong tích hợp managed messaging của AWS.
