# Push subscription, xác minh token và bảo vệ điểm nhận

## Mục tiêu bài học

Module **SPRING_CLOUD_PROVIDER_INTEGRATION** thực hành tích hợp Spring Boot với các dịch vụ managed của **AWS, Azure và Google Cloud** qua thư viện Spring Cloud tương ứng. Trong hệ thống messaging, pull subscriber chủ động lấy message từ Pub/Sub; push subscription để Pub/Sub chủ động gửi HTTP request tới ứng dụng. Cách push phù hợp với webhook, Cloud Run và các dịch vụ autoscaling, nhưng yêu cầu endpoint luôn sẵn sàng nhận request và xác thực đúng danh tính bên gửi.

Bài này tập trung vào cách xây dựng điểm nhận push an toàn:

- Tạo push subscription trỏ tới HTTPS endpoint.
- Hiểu JSON envelope, payload Base64 và tùy chọn payload unwrapping.
- Xác minh OIDC JWT do Pub/Sub ký trong header `Authorization`.
- Cấu hình service account, audience và IAM đúng phạm vi.
- Xử lý HTTP status để ACK/NACK message.
- Bảo vệ endpoint Spring Boot, phân loại lỗi và chống xử lý trùng.
- Theo dõi push latency, response code, retry và backlog.

Sau bài học, bạn có thể triển khai một webhook Spring Boot nhận message từ Pub/Sub với xác thực OIDC, trả ACK đúng thời điểm và vận hành được khi endpoint lỗi hoặc quá tải.

## 1. Push subscription hoạt động như thế nào?

### 1.1. Pub/Sub gọi endpoint

Với push delivery, Pub/Sub gửi từng message dưới dạng HTTP POST tới endpoint đã cấu hình. Endpoint cần có địa chỉ HTTPS công khai, chứng chỉ TLS hợp lệ và có thể nhận request từ dịch vụ Pub/Sub.

```mermaid
sequenceDiagram
    participant P as Publisher
    participant T as Pub/Sub topic
    participant S as Push subscription
    participant A as Spring Boot endpoint
    P->>T: Publish message
    T->>S: Message sẵn sàng
    S->>A: HTTPS POST + JWT + JSON envelope
    A->>A: Xác minh JWT
    A->>A: Decode và xử lý message
    A-->>S: HTTP 204
    S-->>T: ACK message
```

Pub/Sub điều chỉnh tốc độ gửi dựa trên tỷ lệ phản hồi thành công và độ trễ endpoint. Push không yêu cầu ứng dụng chạy vòng lặp pull hoặc giữ streaming subscriber connection.

### 1.2. So sánh push và pull

| Tiêu chí | Push subscription | Pull subscription |
| --- | --- | --- |
| Bên khởi tạo delivery | Pub/Sub gọi endpoint | Ứng dụng gọi Pull/StreamingPull |
| Giao thức | HTTPS POST | Pub/Sub API và client library |
| ACK | HTTP success status | `ack()`/acknowledgment API |
| NACK | HTTP status không được chấp nhận hoặc timeout | `nack()` hoặc ack deadline hết |
| Gia hạn deadline từng message | Không thể gọi `modifyAckDeadline` cho từng push message | Có thể gia hạn ack deadline |
| Scaling | Pub/Sub điều chỉnh push window theo response/latency | Ứng dụng điều chỉnh pull stream, flow control và concurrency |
| Phù hợp | Webhook, HTTP service, Cloud Run | Worker dài hạn, batch, cần kiểm soát ACK response |

Push delivery vẫn có thể giao lại message. Một request đã xử lý thành công ở ứng dụng nhưng response bị mất trên đường về Pub/Sub có thể khiến Pub/Sub gửi lại cùng message. Vì vậy endpoint phải idempotent.

Push subscription không hỗ trợ Pub/Sub exactly-once delivery; semantics delivery vẫn là at-least-once. Inbox/idempotency theo event ID là bắt buộc nếu side effect không được lặp.

### 1.3. Push không có batch message

Push subscription gửi một message người dùng trong mỗi push request. Nếu ứng dụng cần xử lý batch, hãy gom công việc ở tầng ứng dụng sau khi đã nhận và lưu message bền vững; không giả định một HTTP POST chứa nhiều message như pull response.

## 2. HTTP request và Pub/Sub message envelope

### 2.1. Dạng wrapped mặc định

Mặc định Pub/Sub gửi message trong JSON envelope. Trường `message.data` được Base64 encode vì payload gốc là bytes:

```json
{
  "message": {
    "data": "eyJldmVudElkIjoiZXZ0LTEwMDEiLCJvcmRlcklkIjoib3JkLTEwMDEifQ==",
    "attributes": {
      "eventType": "OrderCreated",
      "schemaVersion": "1"
    },
    "messageId": "2070443601311540",
    "message_id": "2070443601311540",
    "publishTime": "2026-11-24T08:30:00.000Z",
    "publish_time": "2026-11-24T08:30:00.000Z"
  },
  "subscription": "projects/acme-commerce-dev/subscriptions/orders-push-sub",
  "deliveryAttempt": 2
}
```

Các trường đáng chú ý:

| Trường | Ý nghĩa |
| --- | --- |
| `message.data` | Payload gốc được Base64 encode |
| `message.attributes` | Metadata dạng chuỗi do publisher gửi |
| `message.messageId` | ID do Pub/Sub cấp cho message |
| `message.publishTime` | Thời điểm Pub/Sub ghi nhận publish |
| `message.orderingKey` | Ordering key nếu message có key |
| `subscription` | Tên đầy đủ của subscription gửi request |
| `deliveryAttempt` | Số lần delivery gần đúng khi subscription có DLQ policy |

Một số trường có cả dạng camelCase và snake_case để tương thích. DTO nên bỏ qua field chưa biết và chỉ dựa vào trường được hợp đồng ứng dụng sử dụng.

### 2.2. Decode payload

Với Java:

```java
byte[] payload = Base64.getDecoder()
        .decode(envelope.message().data());

OrderCreated event = objectMapper.readValue(
        payload,
        OrderCreated.class
);
```

Không decode Base64 lần thứ hai nếu đã bật payload unwrapping. Với wrapped delivery, `data` trong envelope là Base64; với unwrapped delivery, HTTP body chứa trực tiếp payload gốc.

### 2.3. Payload unwrapping

Push subscription có tùy chọn bỏ JSON wrapper:

- **Wrapped:** request body là JSON envelope; giữ `messageId`, attributes, publish time và metadata trong body.
- **Unwrapped:** request body chỉ chứa payload gốc.
- **Write metadata:** nếu bật cùng unwrapped, Pub/Sub đưa một số metadata đã bỏ khỏi body vào HTTP headers.

Wrapped thường dễ vận hành hơn vì message ID, attributes và subscription name nằm trong cùng request. Chỉ bật unwrapped khi endpoint cần nhận raw payload hoặc tích hợp với webhook có wire format cố định. Nếu unwrapped mà không bật Write metadata, ứng dụng sẽ mất nhiều metadata cần thiết để deduplicate và điều tra.

## 3. HTTP status là ACK/NACK

### 3.1. Status xác nhận thành công

Endpoint ACK message bằng cách trả một trong các status:

| HTTP status | Ý nghĩa |
| --- | --- |
| `102` | Processing |
| `200` | OK |
| `201` | Created |
| `202` | Accepted |
| `204` | No Content |

Trong webhook Spring Boot, `204 No Content` thường phù hợp vì Pub/Sub chỉ cần biết message đã được tiếp nhận thành công; không cần response body.

### 3.2. Status khiến Pub/Sub thử lại

Các status khác nhóm trên được xem là negative acknowledgment. Ví dụ:

- `400`: payload không hợp lệ.
- `401`/`403`: authentication hoặc authorization thất bại.
- `429`: endpoint quá tải.
- `500`/`503`: lỗi server hoặc dependency tạm thời.
- Timeout/connection reset: Pub/Sub không nhận được response thành công.

Pub/Sub sẽ gửi lại message theo retry policy và push backoff. Vì vậy, không trả `400` cho một message lỗi vĩnh viễn rồi để nó retry vô hạn. Hãy ghi message vào quarantine/DLQ một cách bền vững rồi trả success status được Pub/Sub chấp nhận, hoặc cấu hình dead-letter topic để cô lập message sau các lần delivery.

### 3.3. Commit trước khi trả success status

Một luồng xử lý an toàn:

1. Xác minh JWT.
2. Parse envelope và validate payload.
3. Ghi inbox/event ID và cập nhật database trong cùng transaction.
4. Chờ transaction commit.
5. Trả HTTP 204.

Nếu trả 204 trước khi commit, process có thể crash sau response và message đã được ACK trong khi nghiệp vụ chưa lưu. Nếu commit thành công nhưng response bị mất, message có thể được gửi lại; inbox/idempotency phải ngăn side effect lặp.

### 3.4. Không thể gia hạn deadline cho push message

Push endpoint không có API để sửa ack deadline của từng message. Thời gian xử lý phải nằm trong ack deadline của subscription. Nếu tác vụ lâu:

- Tăng ack deadline subscription trong giới hạn dịch vụ và kiểm soát timeout endpoint.
- Chỉ lưu job bền vững trong request, trả success status sau khi lưu job, rồi xử lý bất đồng bộ.
- Nếu cần kiểm soát lease từng message, cân nhắc pull subscription.

Không trả success status ngay khi chỉ đưa payload vào một queue RAM không bền vững.

## 4. Xác thực push bằng OIDC JWT

### 4.1. Pub/Sub gửi JWT trong Authorization header

Khi bật authenticated push, Pub/Sub ký một OpenID Connect JWT và gửi trong HTTP header:

```http
Authorization: Bearer eyJhbGciOiJSUzI1NiIs...
```

JWT chứa các claim quan trọng:

| Claim | Ý nghĩa | Kiểm tra ở endpoint |
| --- | --- | --- |
| `iss` | Issuer, thường là `https://accounts.google.com` | Phải đúng issuer tin cậy |
| `aud` | Audience mà token được phát hành cho | Phải khớp audience đã cấu hình |
| `email` | Email của push authentication service account | Phải đúng service account được subscription chọn |
| `email_verified` | Trạng thái xác minh email | Phải là `true` |
| `exp` | Thời điểm hết hạn | Phải còn hiệu lực |
| `iat` | Thời điểm token được phát hành | Dùng kiểm tra tính hợp lệ, không tự đặt cửa sổ vài giây |
| `sub` | Subject ID của service account | Có thể ghi nhận phục vụ audit |

Token do Google ký. Endpoint phải xác minh chữ ký bằng public key/JWK của Google, kiểm tra thời gian hiệu lực và các claim identity/audience. Chỉ Base64 decode JWT không phải xác minh chữ ký.

Google có thể tái sử dụng token đã ký trong một khoảng thời gian; request push có thể mang token đã được tạo trước đó tới một giờ. Không từ chối token chỉ vì `iat` không nằm trong vài giây gần nhất. Hãy dựa vào `exp`, chữ ký, issuer, audience và email.

### 4.2. Audience phải khớp

Audience là một chuỗi do subscription cấu hình. Nếu không override, Pub/Sub dùng endpoint URL làm audience mặc định. Có thể chỉ định audience riêng để endpoint kiểm tra một định danh ổn định:

```text
https://orders.example.com/pubsub/push
```

Audience trong JWT phải khớp audience mà ứng dụng mong đợi. Không dùng hostname từ request header như `Host` hoặc `X-Forwarded-Host` để tự suy ra audience; cấu hình một giá trị tin cậy từ environment/config.

Nếu endpoint được bảo vệ bởi Identity-Aware Proxy (IAP), audience có thể phải là IAP Client ID thay vì URL endpoint. Kiểm tra cấu hình IAP cụ thể.

### 4.3. Phân biệt hai service account

Authenticated push dùng hai identity khác nhau:

| Identity | Vai trò |
| --- | --- |
| Pub/Sub service agent | Danh tính dịch vụ ký/phát OIDC token |
| User-managed push auth service account | Danh tính xuất hiện trong claim `email` của JWT và được endpoint xác thực |

Pub/Sub service agent có dạng:

```text
service-PROJECT_NUMBER@gcp-sa-pubsub.iam.gserviceaccount.com
```

Push auth service account là tài khoản do bạn tạo, ví dụ:

```text
pubsub-push-invoker@acme-commerce-dev.iam.gserviceaccount.com
```

Push auth service account phải thuộc cùng project với subscription. Không dùng service agent làm danh tính ứng dụng hoặc cấp cho service agent quyền truy cập database nghiệp vụ.

## 5. Cấu hình IAM cho authenticated push

### 5.1. Tạo push auth service account

```bash
gcloud iam service-accounts create pubsub-push-invoker \
  --project=acme-commerce-dev \
  --display-name="Pub/Sub push invoker"
```

Đặt biến:

```bash
PROJECT_ID="acme-commerce-dev"
PROJECT_NUMBER="123456789012"
PUSH_AUTH_SA="pubsub-push-invoker@${PROJECT_ID}.iam.gserviceaccount.com"
PUBSUB_SERVICE_AGENT="service-${PROJECT_NUMBER}@gcp-sa-pubsub.iam.gserviceaccount.com"
```

Các giá trị project/account trong ví dụ là placeholder; thay bằng tài nguyên thật của môi trường.

### 5.2. Cho phép Pub/Sub service agent phát token

Pub/Sub service agent cần quyền `iam.serviceAccounts.getOpenIdToken`, nằm trong role `roles/iam.serviceAccountTokenCreator`, trên push auth service account:

```bash
gcloud iam service-accounts add-iam-policy-binding "${PUSH_AUTH_SA}" \
  --project="${PROJECT_ID}" \
  --member="serviceAccount:${PUBSUB_SERVICE_AGENT}" \
  --role="roles/iam.serviceAccountTokenCreator"
```

Đây là quyền cho Pub/Sub service agent ký/phát token. Nếu thiếu quyền, push request có thể không được xác thực và subscription không gửi được message như mong đợi.

### 5.3. Cho phép người tạo subscription gắn service account

Principal tạo hoặc cập nhật subscription cần `iam.serviceAccounts.actAs` trên push auth service account. Role thường dùng là `roles/iam.serviceAccountUser`:

```bash
gcloud iam service-accounts add-iam-policy-binding "${PUSH_AUTH_SA}" \
  --project="${PROJECT_ID}" \
  --member="user:platform-admin@example.com" \
  --role="roles/iam.serviceAccountUser"
```

Thay `user:platform-admin@example.com` bằng principal thực tế hoặc nhóm vận hành được ủy quyền. Không cấp role này rộng cho mọi developer/runtime account.

### 5.4. Cho phép service account gọi Cloud Run

Nếu endpoint là Cloud Run service được bảo vệ bằng IAM, push auth service account cần `roles/run.invoker` trên đúng Cloud Run service:

```bash
gcloud run services add-iam-policy-binding orders-api \
  --project="${PROJECT_ID}" \
  --region=asia-southeast1 \
  --member="serviceAccount:${PUSH_AUTH_SA}" \
  --role="roles/run.invoker"
```

Cloud Run có thể xác thực token ở tầng nền tảng trước khi request vào container. Trong mô hình này, IAM binding trên service là điều kiện để Pub/Sub gọi được endpoint. Nếu tự triển khai JWT verification trong ứng dụng, vẫn phải bảo đảm endpoint không thể bị gọi qua đường public bypass Cloud Run IAM.

Với App Engine/IAP hoặc Cloud Functions, dùng role invoker/IAP tương ứng theo loại endpoint.

### 5.5. Nguyên tắc least privilege

- Pub/Sub service agent chỉ cần Token Creator trên push auth service account.
- Push auth service account chỉ cần quyền invoke endpoint.
- Runtime service account của Spring Boot chỉ cần quyền database, secret và dịch vụ nghiệp vụ mà ứng dụng dùng.
- Principal quản trị subscription chỉ cần `actAs` trên push auth service account và quyền quản lý subscription.
- Không tạo service account key JSON để nhúng vào ứng dụng; Pub/Sub tạo token thay mặt service account qua IAM.

## 6. Tạo và cập nhật push subscription

### 6.1. Tạo subscription bằng gcloud

Ví dụ:

```bash
PUSH_ENDPOINT="https://orders.example.com/pubsub/push"
PUSH_AUDIENCE="https://orders.example.com/pubsub/push"

gcloud pubsub subscriptions create orders-push-sub \
  --project="${PROJECT_ID}" \
  --topic=orders \
  --push-endpoint="${PUSH_ENDPOINT}" \
  --push-auth-service-account="${PUSH_AUTH_SA}" \
  --push-auth-token-audience="${PUSH_AUDIENCE}" \
  --ack-deadline=60 \
  --min-retry-delay=10s \
  --max-retry-delay=300s
```

Endpoint phải là HTTPS public với certificate hợp lệ. Giá trị audience là chuỗi mà Spring endpoint sẽ kiểm tra.

Nếu endpoint chạy trên Cloud Run, audience thường phải là service URL của Cloud Run hoặc custom audience đã được cấu hình trên service. Khi endpoint URL có path như `/pubsub/push`, không mặc định dùng URL có path làm audience Cloud Run nếu service chưa chấp nhận custom audience đó. Đồng bộ `PUSH_AUDIENCE` với cấu hình Cloud Run và validator của ứng dụng.

### 6.2. Cập nhật push configuration

Đổi endpoint hoặc identity:

```bash
gcloud pubsub subscriptions update orders-push-sub \
  --push-endpoint="https://orders-v2.example.com/pubsub/push" \
  --push-auth-service-account="${PUSH_AUTH_SA}" \
  --push-auth-token-audience="https://orders-v2.example.com/pubsub/push"
```

Sau khi thay đổi, xác minh:

```bash
gcloud pubsub subscriptions describe orders-push-sub
```

Kiểm tra `pushConfig.pushEndpoint`, `pushConfig.oidcToken.serviceAccountEmail`, `pushConfig.oidcToken.audience`, retry policy và ack deadline.

### 6.3. Payload unwrapping và dead-letter

Push subscription cũng hỗ trợ retry policy, dead-letter topic và payload unwrapping. Nếu endpoint cần DLQ, cấu hình dead-letter policy và cấp IAM cho Pub/Sub service agent như bài về retry/DLQ. Việc bật authenticated push không tự động tạo DLQ.

### 6.4. Điểm nhận private network

Pub/Sub hoạt động ngoài VPC và không thể push trực tiếp tới địa chỉ IP private trong VPC. Nếu Spring Boot endpoint chỉ có private address, có thể dùng Eventarc làm lớp định tuyến tới Cloud Run/Workflows hoặc dịch vụ nằm trong VPC. Không mở firewall một cách tùy tiện để biến endpoint private thành public; hãy thiết kế đường vào có xác thực và kiểm soát mạng.

## 7. Xác minh JWT trong Spring Boot

### 7.1. Dùng Spring Security OAuth2 Resource Server

Với Spring Boot chạy trên GKE, Compute Engine hoặc nền tảng HTTP do đội ứng dụng quản lý, có thể dùng Spring Security OAuth2 Resource Server để xác minh Bearer JWT. Thư viện Nimbus kiểm tra chữ ký bằng Google JWK; validator bổ sung kiểm tra issuer, audience, email và `email_verified`.

Push delivery được nhận qua HTTP controller như một webhook. `PubSubTemplate.subscribe()` là API cho pull/streaming pull; không dùng nó để nhận push request. `PubSubTemplate`/`PubSubAdmin` vẫn có thể được dùng cho publish hoặc quản lý tài nguyên nếu ứng dụng cần.

Dependency:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-oauth2-resource-server</artifactId>
</dependency>
```

Cấu hình tin cậy trong `application.yml`:

```yaml
app:
  pubsub:
    push:
      audience: https://orders.example.com/pubsub/push
      service-account: pubsub-push-invoker@acme-commerce-dev.iam.gserviceaccount.com
```

Không đặt service account key trong cấu hình. Giá trị `service-account` ở đây chỉ là email identity để so sánh claim, không phải credential bí mật.

### 7.2. Cấu hình `JwtDecoder`

```java
import java.util.List;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.core.DelegatingOAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidatorResult;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.security.oauth2.jwt.JwtValidators;
import org.springframework.security.oauth2.jwt.NimbusJwtDecoder;

@Configuration
public class PubSubPushJwtConfiguration {

    @Bean
    JwtDecoder pubSubPushJwtDecoder(
            @Value("${app.pubsub.push.audience}") String expectedAudience,
            @Value("${app.pubsub.push.service-account}") String expectedServiceAccount) {

        NimbusJwtDecoder decoder = NimbusJwtDecoder
                .withJwkSetUri("https://www.googleapis.com/oauth2/v3/certs")
                .build();

        OAuth2TokenValidator<Jwt> issuerAndTimeValidator =
                JwtValidators.createDefaultWithIssuer(
                        "https://accounts.google.com");

        OAuth2TokenValidator<Jwt> audienceValidator = jwt -> {
            boolean matches = jwt.getAudience().stream()
                    .anyMatch(value -> value.equalsIgnoreCase(expectedAudience));
            return matches
                    ? OAuth2TokenValidatorResult.success()
                    : OAuth2TokenValidatorResult.failure(
                            new OAuth2Error("invalid_token", "Invalid audience", null));
        };

        OAuth2TokenValidator<Jwt> identityValidator = jwt -> {
            String email = jwt.getClaimAsString("email");
            Boolean verified = jwt.getClaim("email_verified");
            boolean expectedIdentity = expectedServiceAccount.equalsIgnoreCase(email);
            if (expectedIdentity && Boolean.TRUE.equals(verified)) {
                return OAuth2TokenValidatorResult.success();
            }
            return OAuth2TokenValidatorResult.failure(
                    new OAuth2Error("invalid_token", "Unexpected push identity", null));
        };

        decoder.setJwtValidator(new DelegatingOAuth2TokenValidator<>(
                issuerAndTimeValidator,
                audienceValidator,
                identityValidator
        ));
        return decoder;
    }
}
```

`NimbusJwtDecoder` lấy public key theo `kid` từ Google JWK endpoint và hỗ trợ key rotation. `JwtValidators.createDefaultWithIssuer()` kiểm tra issuer và các claim thời gian mặc định; validator riêng kiểm tra audience, email và email verification. Nếu JWT không hợp lệ, Spring Security trả 401 trước khi controller xử lý body.

### 7.3. Bảo vệ route push

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class PubSubPushSecurityConfiguration {

    @Bean
    SecurityFilterChain applicationSecurity(HttpSecurity http) throws Exception {
        return http
                .csrf(csrf -> csrf.ignoringRequestMatchers("/pubsub/push"))
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/pubsub/push").authenticated()
                        .anyRequest().permitAll())
                .oauth2ResourceServer(oauth2 ->
                        oauth2.jwt(Customizer.withDefaults()))
                .build();
    }
}
```

Đây là cấu hình tối giản cho ví dụ. Trong ứng dụng có API người dùng, thay `permitAll()` bằng policy xác thực/authorization thực tế cho các route khác. Chỉ miễn CSRF cho webhook machine-to-machine không dùng cookie/session; không tắt CSRF toàn ứng dụng một cách mặc định.

Spring Security đọc `Authorization: Bearer ...`, gọi `JwtDecoder` và chỉ cho request đi vào controller khi chữ ký, issuer, thời gian, audience và identity đều hợp lệ. Không tự parse JWT trong controller rồi tin claim chưa được xác minh.

## 8. Xây dựng HTTP endpoint nhận message

### 8.1. DTO cho wrapped push request

```java
import com.fasterxml.jackson.annotation.JsonAlias;
import com.fasterxml.jackson.annotation.JsonIgnoreProperties;
import java.util.Map;

@JsonIgnoreProperties(ignoreUnknown = true)
public record PubSubPushEnvelope(
        PushMessage message,
        String subscription,
        Integer deliveryAttempt
) {
    @JsonIgnoreProperties(ignoreUnknown = true)
    public record PushMessage(
            String data,
            Map<String, String> attributes,
            @JsonAlias("message_id")
            String messageId,
            @JsonAlias("publish_time")
            String publishTime,
            String orderingKey
    ) {}
}
```

DTO bỏ qua field không biết để tương thích khi Pub/Sub bổ sung metadata. Nếu ứng dụng cần nhận cả alias snake_case, có thể khai báo `@JsonAlias` trên field tương ứng; không yêu cầu mọi field metadata phải có mặt vì envelope tối thiểu có thể chỉ chứa `data`, message ID và subscription.

DTO và controller bên dưới dành cho **wrapped delivery**. Nếu bật unwrapped payload, endpoint phải nhận raw request body (ví dụ `byte[]`) và đọc metadata từ các header được bật bằng Write metadata; không dùng DTO `PubSubPushEnvelope` cho request raw.

### 8.2. Controller chỉ trả success status sau khi lưu bền vững

```java
import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.util.Base64;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/pubsub")
public class OrderPushController {
    private final ObjectMapper objectMapper;
    private final OrderService orderService;
    private final QuarantineService quarantineService;

    public OrderPushController(
            ObjectMapper objectMapper,
            OrderService orderService,
            QuarantineService quarantineService) {
        this.objectMapper = objectMapper;
        this.orderService = orderService;
        this.quarantineService = quarantineService;
    }

    @PostMapping("/push")
    public ResponseEntity<Void> receive(
            @RequestBody PubSubPushEnvelope envelope) {
        final OrderCreated event;
        try {
            byte[] payload = Base64.getDecoder()
                    .decode(envelope.message().data());
            event = objectMapper.readValue(payload, OrderCreated.class);
        } catch (IllegalArgumentException | JsonProcessingException invalidPayload) {
            quarantineService.store(envelope, "INVALID_PAYLOAD");
            return ResponseEntity.noContent().build();
        }

        try {
            // Method @Transactional commit xong trước khi trả về.
            orderService.processIdempotently(
                    event, envelope.message().messageId());
            return ResponseEntity.noContent().build();
        } catch (TransientDependencyException temporaryFailure) {
            // Status không được chấp nhận: Pub/Sub sẽ retry theo retry policy/push backoff.
            return ResponseEntity.status(HttpStatus.SERVICE_UNAVAILABLE).build();
        } catch (PermanentBusinessException permanentFailure) {
            // Chỉ ACK sau khi quarantine đã ghi bền vững.
            quarantineService.store(envelope, "PERMANENT_BUSINESS_FAILURE");
            return ResponseEntity.noContent().build();
        }
    }
}
```

`OrderService.processIdempotently()` phải ghi inbox và side effect trong cùng transaction. Khi method transactional trả về bình thường, transaction proxy hoàn tất commit trước khi controller trả HTTP 204. `QuarantineService.store()` cũng phải ghi bền vững; nếu ghi quarantine lỗi, để exception tạo response 5xx để Pub/Sub thử lại.

Ví dụ cố ý ACK message có payload lỗi sau khi lưu quarantine thành công. Nếu chính sách muốn Pub/Sub chuyển message vào DLQ, có thể trả status không được chấp nhận và để dead-letter policy thực hiện việc cô lập. Không trả success status chỉ vì đã log lỗi.

Nếu JSON envelope không parse được, Spring có thể trả 400 trước khi controller được gọi. Quyết định rõ đây là lỗi cần retry hay poison request cần quarantine; nếu muốn quarantine raw body, dùng `HttpMessageNotReadableException` handler có khả năng nhận/lưu raw request bytes trước khi trả success status.

### 8.3. Chọn status theo loại lỗi

| Kết quả xử lý | HTTP response | Pub/Sub |
| --- | --- | --- |
| Transaction commit thành công | `204` | ACK |
| Event đã được inbox xử lý trước đó | `204` | ACK |
| Dependency tạm thời lỗi | `503` | NACK/retry |
| Database timeout trước commit | `503` | NACK/retry |
| Payload sai nhưng quarantine đã lưu | `204` | ACK |
| Quarantine store lỗi | `500`/`503` | NACK/retry |
| JWT thiếu/sai chữ ký/audience | `401` | Delivery thất bại; kiểm tra auth/IAM |
| Service account không được endpoint cho phép | `403` | Delivery thất bại; kiểm tra authorization |

Lỗi authentication không nên được xử lý bằng cách ACK message; cần sửa cấu hình IAM/audience. Nếu endpoint trả 401/403 liên tục, Pub/Sub tiếp tục thử theo retry/backoff và backlog sẽ tăng.

## 9. Cloud Run: xác thực ở tầng nền tảng

Nếu Spring Boot chạy trên Cloud Run và service yêu cầu authentication, Cloud Run có thể xác minh Google-signed identity token trước khi request vào container. Trong trường hợp này:

1. Cấu hình authenticated push bằng user-managed push auth service account.
2. Gán `roles/run.invoker` cho service account đó trên đúng Cloud Run service.
3. Gán `roles/iam.serviceAccountTokenCreator` cho Pub/Sub service agent trên push auth service account.
4. Cấu hình audience phù hợp với Cloud Run service URL hoặc custom audience đã được Cloud Run chấp nhận.
5. Ứng dụng vẫn phải xác minh/đảm bảo body, schema, idempotency và transaction.

Cloud Run platform authentication không tự cung cấp Spring `@AuthenticationPrincipal Jwt` trong container. Nếu ứng dụng cần đọc claim trong code, hãy xác minh JWT riêng bằng Spring Security như phần trước hoặc dùng cơ chế identity được nền tảng cung cấp phù hợp. Không vừa giả định platform đã xác thực, vừa để một đường ingress public khác bypass IAM.

Ví dụ IAM binding:

```bash
gcloud run services add-iam-policy-binding orders-api \
  --region=asia-southeast1 \
  --member="serviceAccount:${PUSH_AUTH_SA}" \
  --role="roles/run.invoker"
```

Sau khi thay đổi IAM, có thể cần một khoảng thời gian để policy propagation hoàn tất. Trong thời gian đó, Pub/Sub có thể nhận 403 từ endpoint.

## 10. Bảo vệ điểm nhận HTTP

### 10.1. Chỉ nhận POST và giới hạn request

- Chỉ expose route cần thiết, ví dụ `POST /pubsub/push`.
- Giới hạn kích thước request body ở load balancer/API gateway và Spring server theo giới hạn message thực tế.
- Đặt timeout xử lý thấp hơn ack deadline subscription, có buffer cho commit và response.
- Dùng HTTPS với certificate hợp lệ; không nhận token qua HTTP không mã hóa.
- Kiểm tra `Content-Type` và JSON schema; từ chối body quá lớn hoặc không đúng định dạng.
- Không tin `X-Forwarded-For`, `Host` hoặc query parameter làm bằng chứng danh tính nếu proxy chưa được cấu hình trust boundary rõ ràng.

### 10.2. Không tự viết JWT verifier sơ sài

Không làm các việc sau:

- Chỉ Base64 decode JWT rồi đọc `email`/`aud`.
- Chỉ kiểm tra header bắt đầu bằng `Bearer` mà không xác minh chữ ký.
- Chỉ kiểm tra email mà bỏ qua issuer, audience và expiration.
- Chấp nhận mọi service account trong project.
- Tải certificate/JWK mỗi request mà không cache theo cơ chế thư viện.
- Gọi tokeninfo endpoint cho mọi request ở tải cao nếu có thể xác minh offline bằng Google public keys.

Dùng thư viện OIDC/JWT được duy trì, hỗ trợ key rotation và kiểm tra claim. Nếu cache key thủ công, phải xử lý `kid` mới và lịch xoay khóa của Google.

### 10.3. Token verification không thay thế authorization

JWT hợp lệ chứng minh request được ký bởi danh tính đã cấu hình. Ứng dụng vẫn cần authorization theo subscription/topic/event type nếu một endpoint nhận nhiều luồng message. Ví dụ, chỉ cho `orders-push-sub` gửi `OrderCreated`; không dùng claim email để suy ra mọi quyền nghiệp vụ.

Nếu có nhiều push subscription gọi chung endpoint, cân nhắc allowlist subscription name trong envelope và mapping subscription → handler. Tuy nhiên, envelope body chỉ đáng tin sau khi JWT đã được xác minh; kiểm tra subscription name không thay thế token validation.

### 10.4. Bảo vệ dữ liệu và log

- Không log raw JWT hoặc Authorization header.
- Không log toàn bộ payload chứa thông tin cá nhân, payment data hoặc secret.
- Ghi message ID, event ID, subscription, delivery attempt, response status và correlation ID theo chính sách.
- Giữ secret/config audience trong Secret Manager hoặc cấu hình deployment phù hợp; audience và service account email không phải private key nhưng vẫn nên quản lý có kiểm soát.
- Áp dụng IAM tối thiểu cho service account, runtime và DLQ/quarantine store.

### 10.5. Endpoint private và VPC Service Controls

Pub/Sub không thể gọi trực tiếp địa chỉ private VPC. Dùng Eventarc để route tới dịch vụ trong VPC khi cần. Với project có VPC Service Controls, push endpoint bị giới hạn theo loại đích và URL; custom domain có thể không được hỗ trợ trong một số cấu hình. Kiểm tra tài liệu VPC Service Controls trước khi chọn kiến trúc endpoint.

## 11. Retry policy và push backoff

### 11.1. Hai cơ chế độc lập

Push subscription chịu ảnh hưởng của hai cơ chế:

- **Subscription retry policy:** immediate redelivery hoặc exponential backoff khi message không được ACK.
- **Push backoff:** Pub/Sub tạm giảm/ngừng gửi request khi endpoint trả nhiều NACK hoặc phản hồi chậm.

Hai cơ chế độc lập. Nếu cả hai cùng áp dụng, thời gian chờ giao lại thực tế chịu ảnh hưởng bởi giá trị lớn hơn giữa push backoff và retry backoff. Push backoff dùng exponential algorithm và có thể nằm trong khoảng khoảng 100 ms đến 60 giây.

Ví dụ cấu hình retry policy:

```bash
gcloud pubsub subscriptions update orders-push-sub \
  --min-retry-delay=10s \
  --max-retry-delay=300s
```

Không xem `min-retry-delay` là thời điểm giao lại chính xác. Push backoff và trạng thái endpoint có thể làm thời gian thực tế dài hơn.

### 11.2. Adaptive push window

Pub/Sub điều chỉnh số request outstanding dựa trên chất lượng phản hồi:

- Khi endpoint ACK trên 99% message và độ trễ trung bình dưới một giây, push window có thể mở rộng để tăng throughput.
- Khi latency trung bình vượt một giây hoặc tỷ lệ ACK giảm dưới 99%, window giảm để bảo vệ endpoint.
- Sau khoảng 3.000 message outstanding mỗi region, window tăng theo cách tuyến tính nhằm tránh dồn quá nhiều request tới endpoint.

Đây là cơ chế tự điều chỉnh của dịch vụ, không phải một concurrency setting cố định trong Spring Boot. Endpoint trả success status nhanh và ổn định sẽ giúp Pub/Sub mở rộng delivery window; endpoint trả lỗi hoặc chậm làm backlog tăng.

### 11.3. Không dùng HTTP 429 như một bộ điều tiết tùy tiện

HTTP 429 không nằm trong nhóm status ACK được Pub/Sub chấp nhận nên được xem như NACK và kích hoạt retry/backoff. Nếu endpoint quá tải, có thể trả 503 để báo lỗi tạm thời; đồng thời cần capacity planning, bounded worker queue và scale out. Trả 429 liên tục mà không có kế hoạch phục hồi chỉ làm message retry và backlog tăng.

Nếu cần tạm dừng push delivery, có thể đổi subscription sang pull; thay đổi có thể mất vài phút để có hiệu lực. Chỉ làm khi đã có kế hoạch consumer thay thế và cách xử lý backlog.

## 12. Monitoring push subscription

### 12.1. Metrics chính

| Metric | Nhãn/ý nghĩa | Cách sử dụng |
| --- | --- | --- |
| `subscription/push_request_count` | Số lần push, nhóm theo `response_code` và `response_class` | Tìm tỷ lệ ACK, 4xx, 5xx và timeout |
| `subscription/push_request_latencies` | Phân phối latency của request push | Theo dõi p50/p95/p99 endpoint |
| `subscription/num_outstanding_messages` | Số message đang outstanding | Phát hiện endpoint không theo kịp |
| `subscription/oldest_unacked_message_age_by_region` | Tuổi message chưa ACK lâu nhất | Phát hiện backlog bị kẹt |
| `subscription/delivery_latency_health_score` | Điểm sức khỏe delivery latency | Tìm yếu tố làm chậm delivery |
| `subscription/dead_letter_message_count` | Số message được forward sang DLQ | Phát hiện poison message hoặc lỗi kéo dài |

Các response class thường gặp gồm `ack`, `deadline_exceeded`, `internal`, `invalid`, `remote_server_4xx`, `remote_server_5xx` và `unreachable`.

### 12.2. Dashboard cần có

Tối thiểu nên có:

1. Tỷ lệ ACK/response class theo subscription.
2. Push request latency p50/p95/p99.
3. Outstanding messages và oldest unacked age.
4. DLQ count và tốc độ message được forward.
5. HTTP status/exception của Spring endpoint.
6. CPU, memory, thread pool, database connection pool và downstream latency.

Pub/Sub khuyến nghị giữ outstanding message thấp trong phần lớn tình huống; khoảng dưới 1.000 là điểm tham khảo ban đầu, không phải giới hạn cố định hay bảo đảm throughput. Dịch vụ có thể điều chỉnh giới hạn khi throughput cao.

### 12.3. Alert gợi ý

- `response_class` khác `ack` tăng liên tục.
- `deadline_exceeded` xuất hiện kéo dài.
- `remote_server_4xx` tăng: kiểm tra JWT, audience, service account và IAM.
- `remote_server_5xx` tăng: kiểm tra application/dependency.
- `push_request_latencies` p95 vượt SLO.
- Outstanding messages và oldest unacked age cùng tăng.
- DLQ count tăng đột biến.

Không chỉ alert theo một spike ngắn. Kết hợp tỷ lệ lỗi, latency và backlog để phân biệt burst ngắn với sự cố kéo dài.

## 13. Kiểm thử push endpoint

### 13.1. Unit test JWT validator

Tạo các test case cho `JwtDecoder` hoặc validator:

| Token | Kết quả |
| --- | --- |
| Chữ ký hợp lệ, issuer đúng, audience đúng, email đúng, email verified | Chấp nhận |
| Chữ ký bị thay đổi | Từ chối |
| Issuer không phải Google | Từ chối |
| Audience khác cấu hình | Từ chối |
| Email là service account khác | Từ chối |
| `email_verified=false` | Từ chối |
| Token hết hạn | Từ chối |
| Thiếu Authorization Bearer | Spring Security trả 401 |

Không dùng token giả chỉ có payload Base64 để test xác minh chữ ký. Dùng JWT ký bằng key test và JWK test server cho unit test, sau đó xác minh với token thật trong sandbox.

### 13.2. Unit test controller

Mock `OrderService` và `QuarantineService` để xác minh:

- Transaction/business handler thành công → controller trả 204.
- Event đã có trong inbox → trả 204, không tạo side effect lặp.
- Dependency lỗi tạm thời → trả 503.
- Payload sai nhưng quarantine lưu thành công → trả 204.
- Quarantine store lỗi → response 5xx.
- Envelope thiếu `message` hoặc `data` → xử lý lỗi có kiểm soát, không trả 204 giả.

Test controller không thay thế test JWT filter; dùng `spring-security-test` để kiểm thử route authenticated riêng.

### 13.3. Test local bằng MockMvc

Có thể kiểm thử luồng HTTP và controller mà không cần Pub/Sub:

Thêm dependency test:

```xml
<dependency>
    <groupId>org.springframework.security</groupId>
    <artifactId>spring-security-test</artifactId>
    <scope>test</scope>
</dependency>
```

```java
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.jwt;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import java.util.List;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest
@AutoConfigureMockMvc
class OrderPushControllerTest {
    @Autowired
    MockMvc mockMvc;

    @Test
    void acceptsAuthenticatedPush() throws Exception {
        String body = """
                {
                  "message": {
                    "data": "eyJldmVudElkIjoiZXZ0LTEwMDEifQ==",
                    "messageId": "msg-1001"
                  },
                  "subscription": "projects/test/subscriptions/orders-push-sub"
                }
                """;

        mockMvc.perform(post("/pubsub/push")
                        .with(jwt().jwt(jwt -> jwt
                                .issuer("https://accounts.google.com")
                                .audience(List.of(
                                        "https://orders.example.com/pubsub/push"))
                                .claim("email",
                                        "pubsub-push-invoker@acme-commerce-dev.iam.gserviceaccount.com")
                                .claim("email_verified", true)))
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(body))
                .andExpect(status().isNoContent());
    }
}
```

Ví dụ dùng mock JWT để test authorization/controller mapping. `jwt()` trong `spring-security-test` tạo Authentication giả cho test; nó không xác minh chữ ký Google và không chứng minh JWK decoder hoạt động. Phải có test riêng cho `JwtDecoder`.

### 13.4. Cloud sandbox test với push subscription thật

Trong project sandbox:

1. Deploy endpoint HTTPS.
2. Tạo push auth service account và cấp IAM.
3. Tạo push subscription có `--push-auth-service-account` và audience.
4. Publish một message test.
5. Xác minh Spring Security chấp nhận JWT.
6. Xác minh controller decode đúng payload và lưu event.
7. Xác minh response 204 làm message được ACK.
8. Cho endpoint trả 503 một lần rồi 204; quan sát redelivery.
9. Gửi token sai audience/email qua test endpoint riêng và xác minh 401.
10. Làm dependency test chậm để quan sát push latency/backoff.

Pub/Sub emulator có thể hữu ích để test envelope, decode payload và business handler, nhưng không thay thế test authenticated push JWT, service agent IAM hoặc push window trên dịch vụ thật.

### 13.5. Kiểm thử duplicate

Push delivery là at-least-once. Tạo tình huống endpoint commit database nhưng đóng kết nối trước khi trả 204. Pub/Sub có thể gửi lại message. Kết quả cần đạt:

- Cùng event ID chỉ tạo một side effect nghiệp vụ.
- Lần nhận lại đọc inbox và trả 204.
- Không tạo bản ghi đơn hàng/payment trùng.
- Log/metric ghi nhận duplicate mà không log payload nhạy cảm.

## 14. Troubleshooting

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| Subscription không gửi request | Endpoint URL sai, không public HTTPS hoặc TLS certificate lỗi | Kiểm tra URL, DNS, certificate và network |
| HTTP 401 | JWT thiếu, chữ ký/issuer/exp/audience sai | Kiểm tra Bearer header, JWK, audience và đồng hồ hệ thống |
| HTTP 403 | Push auth service account không có invoker role hoặc firewall/network chặn | Kiểm tra `roles/run.invoker`, IAP, ingress và service agent |
| `permission denied` khi tạo subscription | Người tạo thiếu `iam.serviceAccounts.actAs` | Cấp `roles/iam.serviceAccountUser` trên push auth service account |
| Không tạo được OIDC token | Pub/Sub service agent thiếu Token Creator | Cấp `roles/iam.serviceAccountTokenCreator` cho service agent trên push auth service account |
| JWT hợp lệ nhưng bị app từ chối | Audience/email config không khớp | So sánh `aud`, `email`, `email_verified` với cấu hình subscription |
| Endpoint nhận body không parse được | Ứng dụng kỳ vọng raw body nhưng subscription đang wrapped hoặc ngược lại | Đồng bộ payload unwrapping và DTO |
| Payload decode lỗi | Quên Base64 decode hoặc decode hai lần | Decode đúng một lần với wrapped delivery |
| Message lặp | Endpoint commit nhưng response mất/timeout | Inbox/idempotency theo event ID |
| Backlog tăng, `deadline_exceeded` cao | Endpoint chậm, timeout hoặc quá tải | Giảm xử lý đồng bộ, tăng capacity và kiểm tra downstream |
| Push latency tăng sau deploy | Cold start, thread pool hoặc database pool thiếu | Kiểm tra startup, warm capacity và connection pool |
| 4xx/5xx liên tục | Exception handler trả status không phù hợp | Phân loại lỗi permanent/transient và cấu hình DLQ |
| DLQ không nhận message | Dead-letter policy/IAM service agent thiếu | Kiểm tra DLQ policy và quyền Pub/Sub service agent |

### 14.1. Kiểm tra theo thứ tự

1. `gcloud pubsub subscriptions describe orders-push-sub`.
2. Xác minh `pushEndpoint`, `oidcToken.serviceAccountEmail` và `oidcToken.audience`.
3. Kiểm tra push auth service account cùng project với subscription.
4. Kiểm tra Pub/Sub service agent có Token Creator trên push auth service account.
5. Kiểm tra push auth service account có quyền invoke endpoint.
6. Kiểm tra JWT issuer, audience, email, email verification và expiration.
7. Kiểm tra HTTP response code và latency trong Cloud Monitoring.
8. Kiểm tra retry policy, push backoff, backlog và DLQ.

## 15. So sánh với AWS và Azure

| Khía cạnh | Google Cloud Pub/Sub push | AWS | Azure |
| --- | --- | --- | --- |
| Mô hình | Pub/Sub POST tới HTTPS endpoint | SNS HTTP/S subscription hoặc EventBridge API destination | Event Grid webhook; Service Bus thường dùng receiver/processor |
| Xác thực | OIDC JWT do Pub/Sub ký, service account và audience | SNS raw delivery/signature verification hoặc auth qua endpoint/API destination tùy dịch vụ | Event Grid validation handshake và Microsoft Entra ID/webhook auth theo cấu hình |
| ACK | HTTP status `102`, `200`, `201`, `202`, `204` | HTTP success response theo giao thức SNS; SQS consumer xóa message | HTTP success response theo Event Grid; Service Bus complete message qua SDK |
| Retry | Subscription retry policy kết hợp push backoff | SNS delivery retry policy hoặc EventBridge retry policy | Event Grid retry policy và dead-letter destination |
| Gia hạn từng message | Không hỗ trợ `modifyAckDeadline` cho push | Không tương đương trực tiếp với visibility timeout của SQS pull | Event Grid webhook không có lock renew như Service Bus |
| Duplicate | At-least-once; consumer idempotent | Có thể giao lại; consumer idempotent | Có thể giao lại; consumer idempotent |

Không đồng nhất push subscription với SQS/Service Bus receiver. AWS SNS và Azure Event Grid gần với mô hình webhook push; SQS và Service Bus receiver gần với mô hình pull/lock. Khi chuyển cloud, thiết kế lại cơ chế token/signature validation, HTTP acknowledgment, retry và dead-letter theo dịch vụ đích.

## Tổng kết

Push subscription để Pub/Sub gửi HTTP POST tới endpoint HTTPS. Với wrapped delivery, payload nằm trong `message.data` dưới dạng Base64; endpoint trả một trong các success status được Pub/Sub chấp nhận (`102`, `200`, `201`, `202`, `204`) để ACK. Status khác hoặc timeout khiến message được giao lại; push không cho phép sửa ack deadline của từng message.

Authenticated push gửi Google-signed OIDC JWT trong `Authorization: Bearer`. Endpoint cần xác minh chữ ký, issuer, expiration, audience, email và `email_verified`. Pub/Sub service agent cần Token Creator trên push auth service account; principal tạo subscription cần `actAs`; push auth service account cần quyền invoke endpoint như `roles/run.invoker` với Cloud Run.

Spring Boot có thể dùng Spring Security OAuth2 Resource Server và Google JWK để xác minh JWT. Controller chỉ trả success status sau khi transaction nghiệp vụ hoặc quarantine đã ghi bền vững. Push vẫn là at-least-once, vì vậy inbox/idempotency theo event ID là bắt buộc. Theo dõi `push_request_count`, `push_request_latencies`, outstanding messages, oldest unacked age và DLQ để phát hiện endpoint chậm hoặc cấu hình IAM sai.

## Tài liệu tham khảo

- [Google Cloud Pub/Sub — Push subscriptions](https://docs.cloud.google.com/pubsub/docs/push) — workflow, wrapped/unwrapped payload, HTTP ACK status, push backoff và delivery window.
- [Google Cloud Pub/Sub — Authentication for push subscriptions](https://docs.cloud.google.com/pubsub/docs/authenticate-push-subscriptions) — OIDC JWT, claims, service agent, Token Creator và token validation.
- [Google Cloud Pub/Sub — Create push subscriptions](https://docs.cloud.google.com/pubsub/docs/create-push-subscription) — HTTPS endpoint, audience, service account, payload unwrapping và private VPC limitation.
- [Google Cloud Pub/Sub — Monitor Pub/Sub](https://docs.cloud.google.com/pubsub/docs/monitoring) — push response count, latency, outstanding messages và delivery health.
- [Google Cloud Pub/Sub — Troubleshoot push subscriptions](https://docs.cloud.google.com/pubsub/docs/push-troubleshooting) — lỗi endpoint, response class và retry.
- [Google Cloud Run — Authenticate service-to-service](https://docs.cloud.google.com/run/docs/authenticating/service-to-service) — `roles/run.invoker` và authenticated invocation.
- [Spring Security — OAuth 2.0 Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html) — `JwtDecoder`, issuer/audience validation và JWK rotation.
