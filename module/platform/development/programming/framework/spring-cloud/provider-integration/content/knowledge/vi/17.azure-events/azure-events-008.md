# Xác minh điểm nhận sự kiện và xử lý sự kiện trùng lặp

Một webhook nhận Azure Event Grid cần giải quyết hai vấn đề độc lập. Trước tiên, Event Grid phải xác minh endpoint đồng ý nhận sự kiện. Sau đó, ứng dụng phải xác thực request, kiểm tra nguồn và nội dung event, rồi xử lý an toàn khi cùng một event được giao lại. Nếu nhầm lẫn bước xác minh endpoint với xác thực danh tính, webhook có thể chấp nhận request giả mạo. Nếu chỉ dựa vào HTTP response mà không có cơ chế idempotency, retry hợp lệ của Event Grid có thể làm cập nhật dữ liệu hoặc thực hiện side effect nhiều lần.

Bài học thuộc chương **Sự kiện Azure** của mô-đun **SPRING_CLOUD_PROVIDER_INTEGRATION**. Mô-đun thực hành tích hợp Spring Boot với dịch vụ managed của AWS, Azure và Google Cloud qua các thư viện Spring Cloud tương ứng; học cấu hình danh tính và quyền, truy cập storage, messaging, dữ liệu, bảo vệ secret, kiểm thử tích hợp và đánh giá khác biệt giữa cloud provider. Trong bài này, trọng tâm là xác minh webhook Event Grid schema và CloudEvents 1.0, bảo vệ endpoint bằng Microsoft Entra ID, chống duplicate bằng inbox/idempotency, xử lý event sai thứ tự và kiểm thử delivery/retry.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

- Phân biệt endpoint validation với authentication và authorization.
- Thực hiện synchronous hoặc manual validation cho Event Grid schema.
- Triển khai CloudEvents abuse-protection handshake bằng HTTP OPTIONS.
- Cấu hình Spring Security để xác thực bearer token do Event Grid gửi đến webhook.
- Kiểm tra source/topic, event type, subject, schema version và payload trước khi xử lý.
- Thiết kế khóa dedup phù hợp cho Event Grid schema và CloudEvents.
- Dùng inbox/processed-event table với unique constraint và transaction để chống side effect lặp.
- Xử lý duplicate, event đến sai thứ tự, event identity conflict và batch delivery.
- Hiểu response code nào được retry, dead-letter hoặc bị drop.
- Xây dựng test cho validation handshake, authentication, duplicate, replay và failure recovery.

## 2. Hai bài toán khác nhau: endpoint validation và authentication

**Endpoint validation** chứng minh địa chỉ webhook đã đăng ký đồng ý nhận traffic từ Event Grid. Đây là cơ chế bảo vệ sender khỏi việc một người đăng ký nhầm hoặc cố tình trỏ Event Grid tới một website không mong muốn.

**Authentication** xác minh request thực sự được gửi bởi một principal được tin cậy. **Authorization** xác định principal đó có được phép gọi endpoint hoặc gửi loại event này không.

| Cơ chế | Câu hỏi được trả lời | Ví dụ |
|---|---|---|
| Endpoint validation | Endpoint có đồng ý nhận delivery từ Event Grid không? | Validation event hoặc CloudEvents OPTIONS |
| Authentication | Request đến từ danh tính nào? | Microsoft Entra bearer token |
| Authorization | Danh tính đó có quyền gọi webhook không? | App role hoặc policy của API |
| Event validation | Event có đúng nguồn, loại và contract không? | Topic/source allow-list, event type, schema version |
| Idempotency | Event này đã tạo side effect chưa? | Unique key source + event ID |

Không dùng validation handshake làm bằng chứng request đã được xác thực. Một hệ thống bên ngoài cũng có thể gửi HTTP OPTIONS hoặc giả mạo header Origin nếu endpoint không kiểm tra token và quyền. Microsoft yêu cầu dùng HTTPS cho webhook Event Grid.

## 3. Luồng xử lý webhook an toàn

~~~mermaid
flowchart TD
    EG["Azure Event Grid"] --> HTTPS["HTTPS webhook"]
    HTTPS --> AUTH["Authenticate bearer token / secret"]
    AUTH --> VALID{"Validation handshake?"}
    VALID -->|Event Grid schema| EGVAL["Check validation event and echo code"]
    VALID -->|CloudEvents| CEVAL["Check OPTIONS origin agreement"]
    EGVAL --> ACK["Return required validation response"]
    CEVAL --> ACK
    VALID -->|Normal event| SRC["Validate source, topic, type and schema"]
    SRC --> DEDUP["Insert inbox key: source + id"]
    DEDUP --> DUP{"Already processed?"}
    DUP -->|Yes, same payload| ACK2["Return 2xx without side effect"]
    DUP -->|No| TX["Commit business effect + inbox"]
    TX --> ACK2
    DUP -->|Same key, different payload| QUAR["Quarantine and alert"]
~~~

Thứ tự quan trọng:
1. Xác thực request theo cơ chế bảo vệ endpoint đã cấu hình.
2. Xử lý handshake đúng với schema.
3. Với event nghiệp vụ, kiểm tra nguồn và contract.
4. Ghi nhận event ID và side effect trong transaction hoặc lưu inbox bền vững.
5. Chỉ trả response thành công sau khi ứng dụng đã nhận trách nhiệm xử lý bền vững.

## 4. Event Grid schema: synchronous validation

Khi event subscription dùng Event Grid schema và destination là webhook, Event Grid gửi một request POST chứa một event có:

- Header: **aeg-event-type: SubscriptionValidation**.
- Event type: **Microsoft.EventGrid.SubscriptionValidationEvent**.
- Data: **validationCode**; với một số API version còn có **validationUrl**.

Với **synchronous handshake**, webhook phải trả HTTP **200 OK** và JSON có trường **validationResponse** bằng chính xác **validationCode**. Request phải hoàn tất trong 30 giây. HTTP 202 Accepted không được chấp nhận cho bước validation này.

Ví dụ body nhận được:

~~~json
[
  {
    "id": "validation-event-id",
    "topic": "/subscriptions/example/resourceGroups/rg/providers/Microsoft.EventGrid/topics/orders",
    "subject": "",
    "data": {
      "validationCode": "random-validation-code"
    },
    "eventType": "Microsoft.EventGrid.SubscriptionValidationEvent",
    "eventTime": "2026-11-24T10:00:00Z",
    "metadataVersion": "1",
    "dataVersion": "1"
  }
]
~~~

Response đồng bộ:

~~~json
{
  "validationResponse": "random-validation-code"
}
~~~

Validation event được gửi riêng, không trộn với event nghiệp vụ. Endpoint nên xác nhận topic/subscription thuộc allow-list dự kiến trước khi phản hồi code. Không ghi validation code hoặc validation URL vào log.

### 4.1. Manual validation handshake

Nếu endpoint không thể trả validation code đồng bộ, Event Grid hỗ trợ manual handshake khi subscription được tạo bằng API version phù hợp. Event validation chứa **validationUrl**. Endpoint trả HTTP 200 để xác nhận đã nhận validation request; sau đó người vận hành hoặc automation có thẩm quyền thực hiện GET tới URL đó trong vòng 10 phút.

- URL chỉ có hiệu lực 10 phút.
- Subscription ở trạng thái AwaitingManualAction trong thời gian chờ.
- Nếu không hoàn tất trong thời gian này, subscription chuyển sang Failed và phải tạo lại.
- Validation URL dùng cổng 553; firewall/network policy phải cho phép luồng cần thiết.
- Không công khai URL này cho người dùng cuối hoặc ghi nó vào log.

Với Spring Boot webhook có thể phản hồi ngay, synchronous handshake thường dễ tự động hóa và kiểm thử hơn.

## 5. Spring Boot controller cho Event Grid schema

Azure SDK for Java cung cấp **EventGridEvent.fromString()** để deserialize một event hoặc một JSON array thành danh sách event. Event Grid thường gửi payload dạng array ngay cả khi chỉ có một event.

Ví dụ controller dưới đây xử lý synchronous validation trước, sau đó chuyển event nghiệp vụ sang service riêng:

~~~java
import com.azure.messaging.eventgrid.EventGridEvent;
import java.util.List;
import java.util.Map;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/webhooks/event-grid")
class EventGridWebhookController {
    private final OrderEventHandler handler;
    private final String expectedTopic;

    EventGridWebhookController(
            OrderEventHandler handler,
            WebhookProperties properties) {
        this.handler = handler;
        this.expectedTopic = properties.expectedTopic();
    }

    @PostMapping(consumes = MediaType.APPLICATION_JSON_VALUE)
    ResponseEntity<?> receive(
            @RequestHeader(
                    name = "aeg-event-type",
                    required = false) String aegEventType,
            @RequestBody String body) {

        List<EventGridEvent> events = EventGridEvent.fromString(body);

        boolean validationHeader =
                "SubscriptionValidation".equalsIgnoreCase(aegEventType);
        boolean validationBody = events.size() == 1
                && "Microsoft.EventGrid.SubscriptionValidationEvent"
                        .equals(events.get(0).getEventType());

        if (validationHeader || validationBody) {
            if (!validationBody || events.get(0).getData() == null) {
                return ResponseEntity.badRequest().build();
            }

            EventGridEvent validationEvent = events.get(0);
            if (validationEvent.getTopic() != null
                    && !expectedTopic.equals(validationEvent.getTopic())) {
                return ResponseEntity.status(403).build();
            }

            Map<?, ?> data =
                    validationEvent.getData().toObject(Map.class);
            Object code = data.get("validationCode");

            if (!(code instanceof String validationCode)
                    || validationCode.isBlank()) {
                return ResponseEntity.badRequest().build();
            }

            return ResponseEntity.ok(
                    Map.of("validationResponse", validationCode));
        }

        if (events.isEmpty()) {
            return ResponseEntity.badRequest().build();
        }

        for (EventGridEvent event : events) {
            if (event.getTopic() != null
                    && !expectedTopic.equals(event.getTopic())) {
                return ResponseEntity.status(403).build();
            }

            handler.handle(event);
        }

        return ResponseEntity.ok().build();
    }
}
~~~

**WebhookProperties** là cấu hình ứng dụng, ví dụ bind **app.webhook.expected-topic** với resource ID của topic đã được chấp thuận. Với custom topic không gắn domain, **getTopic()** có thể không có giá trị; khi đó dựa vào identity, endpoint/subscription đã cấu hình và allow-list event type/subject. Không chấp nhận một topic bất kỳ chỉ vì body parse được.

Controller cần chạy sau Spring Security filter. Nếu validation event không có đúng header/body, trả lỗi thay vì phản hồi thành công cho một request không xác định. Trong production, giới hạn kích thước request, thời gian xử lý, số event mỗi batch và schema version.

## 6. CloudEvents 1.0: OPTIONS abuse-protection handshake

CloudEvents 1.0 dùng cơ chế handshake riêng thay cho **SubscriptionValidationEvent**. Event Grid gửi HTTP OPTIONS đến đúng URI đăng ký. Request có header:

- **WebHook-Request-Origin**: tên DNS đại diện cho hệ thống gửi event.
- Sender có thể dùng OPTIONS lúc đăng ký hoặc làm preflight trước delivery.

Nếu endpoint đồng ý nhận event, response cần có:
- **WebHook-Allowed-Origin**: origin được chấp thuận; nên trả đúng giá trị đã allow-list.
- **WebHook-Allowed-Rate**: tốc độ request được chấp nhận, đơn vị request/phút.
- **Allow: POST**: cho biết endpoint nhận POST delivery.

Sau handshake, mỗi request delivery có header **Origin** với giá trị phải khớp origin đã thỏa thuận.

**OPTIONS handshake không xác thực danh tính.** Nó chỉ ghi nhận endpoint đồng ý nhận traffic từ origin được nêu. Không dùng wildcard * nếu không có lý do rõ ràng; không phản chiếu mọi giá trị origin mà client gửi.

### 6.1. Spring Boot OPTIONS endpoint

~~~java
import org.springframework.http.HttpMethod;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/webhooks/cloudevents")
class CloudEventValidationController {
    private final String allowedOrigin;

    CloudEventValidationController(WebhookProperties properties) {
        this.allowedOrigin = properties.allowedOrigin();
    }

    @RequestMapping(method = RequestMethod.OPTIONS)
    ResponseEntity<Void> validate(
            @RequestHeader("WebHook-Request-Origin")
                    String requestedOrigin) {

        if (!allowedOrigin.equals(requestedOrigin)) {
            return ResponseEntity.status(403).build();
        }

        return ResponseEntity.ok()
                .header("WebHook-Allowed-Origin", allowedOrigin)
                .header("WebHook-Allowed-Rate", "300")
                .allow(HttpMethod.POST)
                .build();
    }
}
~~~

Giá trị 300 là ví dụ request/phút, phải điều chỉnh theo capacity endpoint. Cấu hình allow-list:

~~~yaml
app:
  webhook:
    allowed-origin: eventgrid.azure.net
~~~

Thay giá trị minh họa bằng origin thực tế được Event Grid gửi trong **WebHook-Request-Origin**. Nếu ứng dụng nhận từ nhiều sender, dùng allow-list có quản lý thay vì chấp nhận mọi origin.

### 6.2. Kiểm tra Origin trên mỗi delivery

~~~java
import com.azure.core.models.CloudEvent;
import java.util.List;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/webhooks/cloudevents")
class CloudEventWebhookController {
    private final CloudEventHandler handler;
    private final String allowedOrigin;

    CloudEventWebhookController(
            CloudEventHandler handler,
            WebhookProperties properties) {
        this.handler = handler;
        this.allowedOrigin = properties.allowedOrigin();
    }

    @PostMapping(consumes = MediaType.APPLICATION_JSON_VALUE)
    ResponseEntity<Void> receive(
            @RequestHeader(
                    value = HttpHeaders.ORIGIN,
                    required = false) String origin,
            @RequestBody String body) {

        if (origin == null || !allowedOrigin.equals(origin)) {
            return ResponseEntity.status(403).build();
        }

        List<CloudEvent> events = CloudEvent.fromString(body);
        if (events.isEmpty()) {
            return ResponseEntity.badRequest().build();
        }

        for (CloudEvent event : events) {
            handler.handle(event);
        }

        return ResponseEntity.accepted().build();
    }
}
~~~

Đây mới là kiểm tra agreement theo CloudEvents webhook protocol. Request vẫn phải qua Spring Security authentication và authorization. Một client có thể tự gửi header **Origin**; do đó header này không thể thay thế bearer token hoặc cơ chế xác thực khác.

## 7. Bảo vệ webhook bằng Microsoft Entra ID

Với webhook production, nên cấu hình Event Grid gửi bearer token tới API được bảo vệ bởi Microsoft Entra ID. Quy trình tổng quát:

1. Đăng ký ứng dụng/API đại diện cho webhook.
2. Khai báo Application ID URI hoặc audience mà API chấp nhận.
3. Tạo app role dành cho Event Grid delivery, ví dụ **EventGrid.Receive**.
4. Cấu hình event subscription dùng Microsoft Entra authentication với tenant ID và application ID/URI của API.
5. Cấp role/quan hệ ứng dụng cần thiết cho Event Grid service principal theo hướng dẫn bảo mật hiện hành.
6. Trong Spring Security, xác minh chữ ký, issuer, tenant, audience, thời hạn token và role/scope.
7. Chỉ cho phép POST event delivery nếu principal có quyền; OPTIONS CloudEvents có thể được permit riêng nhưng vẫn phải kiểm tra origin allow-list.

Event Grid chỉ hỗ trợ HTTPS webhook. Validation handshake phải được thực hiện dù webhook đã bật Entra authentication; hai cơ chế phục vụ hai mục đích khác nhau.

### 7.1. Dependency và cấu hình resource server

Dependency Spring Security OAuth2 Resource Server:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-oauth2-resource-server</artifactId>
</dependency>
~~~

Cấu hình issuer:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://login.microsoftonline.com/TENANT_ID/v2.0
~~~

Cấu hình issuer giúp Spring Security tìm metadata và kiểm tra token theo issuer. Ứng dụng còn phải xác minh audience đúng Application ID URI của webhook và quyền/app role mong đợi; không coi token có chữ ký hợp lệ từ bất kỳ API nào trong tenant là đủ.

Ví dụ kiểm tra audience bằng JwtDecoder tùy chỉnh:

~~~java
import java.util.List;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.core.DelegatingOAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.core.validator.JwtClaimValidator;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.security.oauth2.jwt.JwtValidators;
import org.springframework.security.oauth2.jwt.NimbusJwtDecoder;

@Configuration
@EnableConfigurationProperties(WebhookSecurityProperties.class)
class WebhookJwtConfiguration {

    @Bean
    JwtDecoder webhookJwtDecoder(WebhookSecurityProperties properties) {
        String issuer = properties.issuer();
        String audience = properties.audience();
        NimbusJwtDecoder decoder =
                NimbusJwtDecoder.withIssuerLocation(issuer).build();

        OAuth2TokenValidator<Jwt> issuerValidator =
                JwtValidators.createDefaultWithIssuer(issuer);

        OAuth2TokenValidator<Jwt> audienceValidator =
                new JwtClaimValidator<List<String>>(
                        "aud",
                        values -> values != null
                                && values.contains(audience));

        decoder.setJwtValidator(
                new DelegatingOAuth2TokenValidator<>(
                        issuerValidator,
                        audienceValidator));

        return decoder;
    }
}

@ConfigurationProperties(prefix = "app.security")
record WebhookSecurityProperties(String issuer, String audience) {}
~~~

Trong ví dụ này, **aud** được giả định là danh sách string theo token của API. Kiểm tra token thực tế của tenant để xác định kiểu claim và audience; nếu định dạng khác, điều chỉnh validator tương ứng. Thêm kiểm tra app role trong authorization layer hoặc JwtAuthenticationConverter.

Bean JwtDecoder ở trên được Spring Security sử dụng tự động bởi SecurityFilterChain bên dưới. Nếu API yêu cầu app role, cấu hình JwtAuthenticationConverter đọc claim roles và ánh xạ thành authority; chỉ kiểm tra authenticated là chưa đủ để phân quyền theo nghiệp vụ.

### 7.2. SecurityFilterChain cho webhook

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
class WebhookSecurityConfiguration {

    @Bean
    SecurityFilterChain webhookSecurity(HttpSecurity http)
            throws Exception {
        http
            .csrf(csrf -> csrf.ignoringRequestMatchers("/webhooks/**"))
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(
                        HttpMethod.OPTIONS,
                        "/webhooks/cloudevents").permitAll()
                .requestMatchers("/webhooks/**").authenticated()
                .anyRequest().authenticated())
            .oauth2ResourceServer(oauth ->
                oauth.jwt(Customizer.withDefaults()));

        return http.build();
    }
}
~~~

Ví dụ dùng **authenticated()** để tập trung vào xác minh token; production nên bổ sung converter/policy để chỉ app role được phép gọi webhook. OPTIONS được mở riêng vì CloudEvents preflight không thiết lập authentication context; controller vẫn kiểm tra origin allow-list. POST delivery vẫn cần bearer token hợp lệ.

### 7.3. Shared secret qua query parameter

Event Grid cũng hỗ trợ client secret trong query parameter của webhook URL. Nếu phải dùng:
- Sinh secret ngẫu nhiên đủ mạnh, chỉ dùng cho một subscription.
- Lưu secret trong secret manager và giới hạn người có quyền đọc subscription endpoint.
- Không log URL đầy đủ ở application, reverse proxy, APM hoặc WAF.
- So sánh constant-time khi kiểm tra secret.
- Khi rotate, tạm thời chấp nhận secret cũ và mới trong một khoảng ngắn; cập nhật subscription rồi thu hồi secret cũ.
- Ưu tiên Entra bearer token cho endpoint production nếu kiến trúc cho phép.

Không nhầm query secret hoặc Origin header với endpoint validation code. Validation code là nonce cho quá trình xác minh endpoint, không phải credential dùng cho mọi request delivery.

## 8. Kiểm tra nguồn và contract của event

Sau khi xác thực request, ứng dụng vẫn phải xác minh event phù hợp với subscription và nghiệp vụ.

Các kiểm tra nên có:

- **Source/topic:** chỉ nhận topic/resource ID đã cấu hình. Với CloudEvents, kiểm tra thuộc tính **source**; với Event Grid schema, kiểm tra **topic** khi có và đối chiếu subscription/endpoint đã cấu hình.
- **Event type:** allow-list các type ứng dụng hỗ trợ; không dispatch mọi event đến một handler tổng quát.
- **Subject:** kiểm tra prefix/path nếu nghiệp vụ chỉ quan tâm một loại resource.
- **Schema version:** hỗ trợ rõ các version; từ chối hoặc quarantine version không tương thích.
- **Data:** validate required field, kiểu dữ liệu, giới hạn kích thước và invariant.
- **Timestamp/version nghiệp vụ:** không dùng timestamp làm khóa dedup; dùng aggregate version để phát hiện stale/out-of-order event.
- **Correlation ID:** giữ để truy vết qua producer, Event Grid và consumer.

Filter của event subscription giảm lượng event không liên quan, nhưng consumer vẫn phải kiểm tra source/type. Cấu hình filter có thể thay đổi hoặc subscription có thể được tạo sai; kiểm tra ở application boundary là lớp bảo vệ cuối.

## 9. Nhận dạng một event để chống duplicate

### 9.1. Event Grid schema

Event Grid schema có trường **id** duy nhất cho event do publisher tạo. Khi delivery retry, cùng event được giao lại với cùng ID. Ứng dụng có thể dùng event ID cùng định danh nguồn/topic và consumer logic làm khóa dedup.

Với Event Grid domain, event có thể chứa topic cụ thể. Với topic đơn, cấu hình resource ID của topic làm source scope nếu event envelope không có topic field.

### 9.2. CloudEvents 1.0

Theo CloudEvents, cặp **source + id** xác định một event duy nhất. Không chỉ dùng **id** nếu consumer nhận event từ nhiều source khác nhau, vì hai source có thể dùng cùng chuỗi ID.

Khóa dedup đề xuất:

| Schema | Khóa dedup |
|---|---|
| Event Grid schema | consumer name + configured topic/source + event id |
| CloudEvents | consumer name + source + id |

**Consumer name** phân biệt mục tiêu xử lý. Ví dụ **order-projection** và **fraud-detection** có thể xử lý cùng event nhưng có tiến độ và side effect khác nhau. Nếu dùng cùng một bảng dedup cho mọi consumer mà không có consumer name, một consumer có thể khiến consumer khác bỏ qua event hợp lệ.

## 10. Inbox table và unique constraint

Cách phổ biến là lưu event đã xử lý trong bảng inbox/processed-event. Khóa chính ngăn hai request đồng thời cùng ghi nhận một event như hai event mới.

Ví dụ PostgreSQL:

~~~sql
CREATE TABLE processed_event (
    consumer_name varchar(100) NOT NULL,
    event_source varchar(500) NOT NULL,
    event_id varchar(200) NOT NULL,
    payload_sha256 char(64) NOT NULL,
    processed_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (consumer_name, event_source, event_id)
);
~~~

Lệnh insert idempotent:

~~~sql
INSERT INTO processed_event (
    consumer_name,
    event_source,
    event_id,
    payload_sha256
)
VALUES (
    'order-projection',
    :event_source,
    :event_id,
    :payload_sha256
)
ON CONFLICT DO NOTHING;
~~~

Nếu insert tạo một row mới, transaction có quyền tiếp tục xử lý nghiệp vụ. Nếu không tạo row, event đã được ghi nhận trước đó. So sánh payload hash đã lưu với hash hiện tại:
- Cùng source + id và cùng hash: duplicate hợp lệ, bỏ qua side effect.
- Cùng source + id nhưng hash khác: identity conflict, ghi audit/quarantine và cảnh báo; không âm thầm bỏ qua.

Không dùng cache in-memory làm dedup store duy nhất. Cache mất khi restart, không chia sẻ giữa nhiều replica và có thể cho phép hai instance xử lý cùng event đồng thời.

## 11. Xử lý event và dedup trong cùng transaction

Quy tắc quan trọng: ghi processed-event và cập nhật dữ liệu nghiệp vụ trong **cùng một transaction database**. Nếu tách hai transaction, process có thể ghi dedup thành công rồi chết trước khi cập nhật nghiệp vụ; lần retry sau đó bị coi là duplicate và side effect bị mất.

Ví dụ service PostgreSQL dùng JdbcTemplate:

~~~java
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.HexFormat;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
class OrderEventHandler {
    private final JdbcTemplate jdbc;

    OrderEventHandler(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional
    public boolean handle(
            String consumerName,
            String source,
            String eventId,
            byte[] payload,
            String orderId,
            String newStatus) {

        String hash = sha256(payload);

        int inserted = jdbc.update(
                """
                INSERT INTO processed_event
                    (consumer_name, event_source, event_id, payload_sha256)
                VALUES (?, ?, ?, ?)
                ON CONFLICT DO NOTHING
                """,
                consumerName, source, eventId, hash);

        if (inserted == 0) {
            String storedHash = jdbc.queryForObject(
                    """
                    SELECT payload_sha256
                    FROM processed_event
                    WHERE consumer_name = ?
                      AND event_source = ?
                      AND event_id = ?
                    """,
                    String.class,
                    consumerName, source, eventId);

            if (!hash.equals(storedHash)) {
                throw new IllegalStateException(
                        "Event identity was reused with a different payload");
            }

            return false;
        }

        int updated = jdbc.update(
                """
                UPDATE order_projection
                SET status = ?
                WHERE order_id = ?
                """,
                newStatus, orderId);

        if (updated != 1) {
            throw new IllegalStateException(
                    "Expected exactly one order projection to be updated");
        }

        return true;
    }

    private static String sha256(byte[] payload) {
        try {
            byte[] digest = MessageDigest.getInstance("SHA-256")
                    .digest(payload);
            return HexFormat.of().formatHex(digest);
        } catch (NoSuchAlgorithmException exception) {
            throw new IllegalStateException(exception);
        }
    }
}
~~~

Đây là ví dụ cho PostgreSQL và Spring transaction. Table processed_event và order_projection phải nằm trong cùng datasource/transaction. Trong production cần validate payload trước khi gọi handler, kiểm tra số row cập nhật và ghi identity conflict vào quarantine bằng transaction riêng nếu transaction chính rollback. Không log payload nhạy cảm; hash chỉ dùng phát hiện nội dung thay đổi, không phải cơ chế mã hóa.

Khi controller gọi một service bean có @Transactional qua Spring proxy, transaction commit trước khi lời gọi service trả về. Vì vậy controller có thể trả HTTP 2xx sau khi service hoàn tất. Tránh đặt transaction trên controller và trả ACK trước khi transaction interceptor commit.

Adapter chuyển envelope Event Grid hoặc CloudEvents về cùng handler nghiệp vụ. Event Grid schema dùng topic đã cấu hình làm source scope khi trường topic không có; CloudEvents dùng thuộc tính source:

~~~java
import com.azure.core.models.CloudEvent;
import com.azure.messaging.eventgrid.EventGridEvent;
import org.springframework.stereotype.Service;

record OrderEventData(String orderId, String status) {}

@Service
class OrderEventAdapter {
    private final OrderEventHandler handler;
    private final String configuredTopic;

    OrderEventAdapter(
            OrderEventHandler handler,
            WebhookProperties properties) {
        this.handler = handler;
        this.configuredTopic = properties.expectedTopic();
    }

    void handle(EventGridEvent event) {
        if (event.getData() == null || event.getId() == null) {
            throw new IllegalArgumentException("Invalid Event Grid envelope");
        }
        OrderEventData data = event.getData().toObject(OrderEventData.class);
        String source = event.getTopic() == null
                ? configuredTopic : event.getTopic();
        handler.handle(
                "order-projection", source, event.getId(),
                event.getData().toBytes(), data.orderId(), data.status());
    }

    void handle(CloudEvent event) {
        if (event.getData() == null) {
            throw new IllegalArgumentException("Missing CloudEvent data");
        }
        OrderEventData data = event.getData().toObject(OrderEventData.class);
        handler.handle(
                "order-projection", event.getSource(), event.getId(),
                event.getData().toBytes(), data.orderId(), data.status());
    }
}
~~~

Adapter phải validate event type, source và payload schema trước khi gọi handler. Nếu identity conflict là lỗi vĩnh viễn, ghi quarantine bằng transaction riêng rồi ACK theo policy; hoặc để Event Grid chuyển event vào dead-letter sau retry policy đã cấu hình. Không trả 5xx vô hạn cho một payload không thể sửa.

## 12. Inbox bền vững rồi xử lý bất đồng bộ

Nếu xử lý nghiệp vụ mất nhiều thời gian, webhook không nên giữ HTTP request mở lâu. Có thể dùng inbox pattern:

1. Xác thực và validate event.
2. Ghi payload/metadata vào inbox với unique key source + id và trạng thái PENDING.
3. Commit transaction.
4. Trả HTTP 202 Accepted cho Event Grid.
5. Worker Spring Boot lấy inbox PENDING và xử lý theo transaction/idempotency.
6. Ghi trạng thái DONE hoặc FAILED; event lỗi vĩnh viễn chuyển quarantine.

Không được đưa event vào queue RAM rồi trả 202. Nếu process dừng sau ACK, công việc chỉ nằm trong bộ nhớ sẽ mất. Inbox table, Service Bus queue hoặc broker bền vững mới là điểm tiếp nhận an toàn.

Inbox cũng cần giới hạn payload, encryption, retention, retry count và quyền truy cập. Nếu lưu raw event, chỉ lưu các trường cần thiết và áp dụng chính sách dữ liệu nhạy cảm.

## 13. Duplicate, retry và response code

Event Grid cung cấp durable delivery theo mô hình **at-least-once** cho mỗi subscription phù hợp. Event có thể được gửi lại khi endpoint không ACK, timeout hoặc phản hồi bị mất. Event Grid không bảo đảm thứ tự delivery. Mặc định Event Grid gửi từng event một; payload vẫn là JSON array có một phần tử. Nếu bật batch delivery, một request có thể chứa nhiều event và delivery có semantics all-or-none.

Với webhook, các response 200, 201, 202, 203 và 204 được xem là ACK thành công. Các mã 400, 413, 401 và 403 là lỗi không được retry theo policy thông thường; nếu dead-letter chưa cấu hình, event có thể bị drop. Các lỗi khác, bao gồm nhiều lỗi 5xx và timeout, thường được retry theo exponential backoff.

| Tình huống | Response/hành động |
|---|---|
| Event đã xử lý thành công | 200 hoặc 202 sau khi commit/persist bền vững |
| Event duplicate, payload giống | Bỏ qua side effect và trả 2xx |
| Event chưa xử lý, DB tạm thời lỗi | Trả 5xx để Event Grid retry |
| Request không hợp lệ vĩnh viễn | 400; cấu hình dead-letter nếu cần giữ event |
| Authentication sai | 401/403; sửa cấu hình token và dead-letter |
| Payload vượt giới hạn | 413; điều chỉnh batch/request size |
| Identity conflict | Quarantine, alert và xử lý theo policy; không ACK như duplicate hợp lệ |

Event Grid mặc định retry tối đa 30 lần hoặc đến TTL 1.440 phút (24 giờ), tùy giới hạn nào đến trước. Endpoint có thể nhận duplicate ngay cả khi đã phản hồi thành công do việc loại event khỏi retry queue là best-effort. Vì vậy, ACK đúng một lần không thay thế idempotency.

### 13.1. Dead-letter

Dead-letter không được bật mặc định cho mọi subscription. Cấu hình Blob Storage làm dead-letter destination khi cần giữ event không thể giao. Đảm bảo:
- Storage account/container tồn tại trước khi tạo subscription.
- Event Grid identity có quyền ghi phù hợp nếu dùng managed identity.
- Có alert khi dead-letter xuất hiện.
- Có quy trình kiểm tra payload, sửa nguyên nhân và replay.
- Có retention/lifecycle và quyền đọc archive riêng.

Dead-letter destination không khả dụng cũng có thể làm event bị drop. Không xem dead-letter là nơi tự động xử lý lại; nó là nơi giữ event để điều tra và replay có kiểm soát.

## 14. Xử lý event đến sai thứ tự

Event Grid không bảo đảm thứ tự. Nếu hai event cùng order được gửi gần nhau, event version 5 có thể tới trước version 4. Idempotency ngăn cùng một event bị áp dụng hai lần, nhưng không tự giải quyết event cũ đến sau event mới.

Nên đưa aggregate version hoặc sequence vào payload:

~~~json
{
  "eventId": "evt-order-1001-v5",
  "aggregateId": "order-1001",
  "aggregateVersion": 5,
  "eventType": "OrderShipped",
  "data": {
    "status": "SHIPPED"
  }
}
~~~

Consumer có thể:
- Bỏ qua version thấp hơn version đã áp dụng.
- Chỉ áp dụng version kế tiếp nếu nghiệp vụ yêu cầu không có gap.
- Lưu event đến sớm vào bảng pending để chờ version còn thiếu.
- Đối soát trạng thái aggregate nếu event gap kéo dài.
- Không dùng eventTime làm thứ tự tuyệt đối vì clock và delivery có thể khác nhau.

Với nghiệp vụ thanh toán, tồn kho hoặc trạng thái đơn hàng, cần state transition guard ở database. Idempotency và version check giải quyết hai vấn đề khác nhau.

## 15. Side effect ngoài database và transactional outbox

Nếu handler vừa cập nhật database vừa gửi email, thanh toán hoặc gọi API đối tác, transaction database không thể rollback side effect bên ngoài. Ví dụ DB commit thành công nhưng HTTP request đối tác timeout; consumer không biết thao tác đã thực hiện hay chưa.

Các cách xử lý:
- Truyền idempotency key source + event ID tới API đích nếu API hỗ trợ.
- Ghi yêu cầu side effect vào outbox cùng transaction với processed_event và cập nhật nghiệp vụ.
- Worker riêng gửi outbox và đánh dấu trạng thái.
- Nếu response ngoài không rõ, query trạng thái hoặc retry với cùng idempotency key.
- Không tạo key mới mỗi lần retry.

~~~mermaid
flowchart TD
    EG["Event Grid delivery"] --> IN["Webhook / inbox"]
    IN --> TX["Database transaction"]
    TX --> DEDUP["Insert processed_event"]
    TX --> STATE["Update business state"]
    TX --> OUT["Insert outbox command"]
    OUT --> WORKER["Outbox dispatcher"]
    WORKER --> API["External API with idempotency key"]
    API --> DONE["Mark outbox complete"]
~~~

Outbox không tạo exactly-once xuyên database và API ngoài. Nó bảo đảm yêu cầu side effect không bị quên sau commit; API đích vẫn cần idempotency hoặc cơ chế đối soát.

## 16. Kiểm tra batch delivery

Event Grid mặc định gửi từng event một nhưng body vẫn là array. Nếu bật batch delivery ở subscription, một request có thể chứa nhiều event. Delivery theo batch có semantics all-or-none: endpoint phải xử lý được toàn batch trong timeout của Event Grid.

Một chiến lược an toàn:
- Deserialize toàn bộ batch.
- Validate từng event trước khi xử lý.
- Mỗi event có dedup key riêng.
- Commit từng event hoặc commit cả batch trong transaction tùy yêu cầu nghiệp vụ.
- Nếu một event lỗi và trả 5xx, Event Grid có thể giao lại cả batch; event đã commit trước đó phải được dedup.
- Nếu event lỗi vĩnh viễn, lưu quarantine bền vững trước khi ACK batch theo policy.

Không trả 2xx khi chỉ xử lý thành công một phần nhưng không lưu lại event còn lại. Nếu muốn xử lý độc lập, inbox từng event rồi ACK sau khi mọi event đã được persist bền vững.

## 17. Cấu hình Spring Boot và deployment

Ví dụ application properties cho webhook:

~~~yaml
app:
  webhook:
    expected-topic: /subscriptions/SUBSCRIPTION_ID/resourceGroups/RESOURCE_GROUP/providers/Microsoft.EventGrid/topics/orders
    allowed-origin: eventgrid.azure.net
  security:
    issuer: https://login.microsoftonline.com/TENANT_ID/v2.0
    audience: api://ORDER_WEBHOOK_APP_ID
~~~

Các giá trị là cấu hình môi trường minh họa. Dùng secret manager hoặc platform configuration để cấp audience, issuer và endpoint; không đưa secret thật vào Git.

Khi triển khai:
- Đăng ký event subscription với đúng webhook URL HTTPS và output schema.
- Cấu hình Entra bearer token hoặc secret query parameter theo policy.
- Cấu hình CloudEvents origin allow-list nếu dùng CloudEvents.
- Mở network path cho validation request và POST delivery; kiểm tra WAF không chặn header/body validation.
- Cấu hình dead-letter destination và retry TTL/attempts.
- Cấp quyền Blob dead-letter cho Event Grid identity nếu dùng managed identity.
- Theo dõi deployment rollout để endpoint cũ và mới cùng xử lý an toàn trong thời gian chuyển đổi.

Nếu dùng Entra authentication, xác minh cả issuer, audience và app role của token mà Event Grid gửi. Chỉ kiểm tra tenant hoặc chữ ký là chưa đủ để chứng minh token dành cho API này.

## 18. Kiểm thử endpoint validation và duplicate

Dùng topic, subscription, webhook URL và database riêng cho test. Không tạo validation request giả trên production endpoint hoặc cố ý trả lỗi để kích hoạt retry trên subscription thật.

| Kịch bản | Cách kiểm thử | Kết quả mong đợi |
|---|---|---|
| Event Grid synchronous validation | POST validation event có header aeg-event-type | HTTP 200 và validationResponse đúng |
| Sai validation code | Trả code khác payload | Subscription validation thất bại |
| Validation trả 202 | Dùng 202 thay 200 | Event Grid không coi handshake thành công |
| Manual validation | Trả 200, sau đó GET validationUrl trong 10 phút | Subscription chuyển sang validated |
| Validation URL hết hạn | Chờ quá 10 phút | Subscription thất bại; cần tạo lại |
| CloudEvents OPTIONS | Gửi WebHook-Request-Origin hợp lệ | Có WebHook-Allowed-Origin/Rate và Allow POST |
| Origin không được phép | Gửi origin ngoài allow-list | Không cấp consent |
| Origin header sai khi POST | Gửi delivery với Origin không khớp | Request bị từ chối |
| JWT sai issuer/audience | Gửi token của API khác | Spring Security từ chối |
| JWT thiếu app role | Token hợp lệ nhưng không có quyền nhận event | Authorization từ chối |
| Duplicate cùng source + id | Gửi lại cùng event hai lần | Chỉ một side effect |
| Same id, different source | Hai source dùng cùng id | Hai event được phân biệt |
| Same source + id, payload khác | Gửi identity conflict | Quarantine/alert, không bỏ qua âm thầm |
| Crash sau DB commit | Dừng process trước HTTP ACK | Retry không lặp side effect |
| DB unavailable | Làm database test lỗi tạm thời | Endpoint trả 5xx, Event Grid retry |
| Batch có một event lỗi | Gửi batch gồm event tốt và event lỗi | Không mất event chưa được persist |
| Event sai thứ tự | Gửi aggregate version đảo thứ tự | Consumer phát hiện stale/gap |
| Dead-letter | Cấu hình test endpoint trả lỗi không retry | Event được giữ ở storage DLQ |

Unit test kiểm tra validation code, origin allow-list, source/type allow-list, unique constraint và payload hash. Integration test xác minh Spring Security, PostgreSQL transaction, Event Grid delivery retry và dead-letter thật.

## 19. Quan sát và runbook

Theo dõi ít nhất:

| Nhóm | Chỉ số |
|---|---|
| Validation | Số lần handshake, validation failure, OPTIONS rejection |
| Authentication | JWT invalid, issuer/audience mismatch, unauthorized/forbidden |
| Delivery | Request count, 2xx/4xx/5xx, latency, delivery attempts |
| Idempotency | Duplicate suppressed, identity conflict, inbox insert conflict |
| Business | Handler success/failure, aggregate version gap, transaction rollback |
| Persistence | Inbox backlog, outbox backlog, DB latency, connection pool |
| Dead-letter | Event count, oldest event age, reason, replay count |
| Security | Secret rotation, role assignment, endpoint URL changes, WAF rejection |

Runbook khi validation thất bại:
1. Xác minh endpoint HTTPS và certificate hợp lệ.
2. Kiểm tra WAF, API Gateway, reverse proxy và firewall.
3. Kiểm tra header aeg-event-type hoặc OPTIONS request có tới controller không.
4. Kiểm tra Event Grid schema có trả đúng validationResponse trong 30 giây không.
5. Nếu manual handshake, kiểm tra validationUrl và cổng 553 trong cửa sổ 10 phút.
6. Với CloudEvents, kiểm tra WebHook-Request-Origin và hai response header.
7. Kiểm tra JWT/secret filter không chặn validation request hợp lệ.

Runbook khi duplicate tăng:
1. Kiểm tra Event Grid retry, endpoint latency và response timeout.
2. Kiểm tra deployment/restart có làm mất trạng thái dedup không.
3. Kiểm tra unique constraint và transaction inbox/business state.
4. Kiểm tra side effect ngoài database có idempotency key không.
5. Kiểm tra event source/id có ổn định qua retry không.
6. Đối soát business state trước khi replay hoặc gửi lại event.

## 20. Lỗi thiết kế thường gặp

| Lỗi | Hậu quả | Cách sửa |
|---|---|---|
| Coi validation handshake là authentication | Webhook có thể nhận request giả mạo | Xác thực JWT/secret độc lập |
| Chỉ kiểm tra Origin | Header có thể bị giả mạo | Dùng Entra bearer token và allow-list |
| Trả 202 cho Event Grid schema validation | Subscription không được xác minh | Trả 200 và validationResponse |
| Dùng CloudEvents OPTIONS như cơ chế auth | Request POST không được xác thực | Kiểm tra JWT/role trên delivery |
| Dùng event id làm khóa toàn cục cho nhiều source | Hai source có thể va chạm | Dùng source + id |
| Chỉ dedup trong memory/cache cục bộ | Restart/scale-out làm mất bảo vệ | Unique constraint trong persistent store |
| Ghi dedup trước, business state sau bằng transaction riêng | Event bị đánh dấu xong dù nghiệp vụ chưa commit | Cùng transaction |
| Trả 2xx trước khi persist | Process crash làm mất event | Persist inbox/outbox trước ACK |
| Trả 401/403 khi JWT cấu hình sai mà không DLQ | Event có thể bị drop do không retry | Cấu hình auth đúng và dead-letter |
| Giả định event đến đúng thứ tự | State có thể bị ghi lùi | Aggregate version/state transition guard |
| Xóa dedup record quá sớm | Replay tạo side effect cũ | Retention theo retry TTL và replay policy |
| Bật batch nhưng xử lý một phần rồi ACK | Event còn lại bị mất | Persist từng event hoặc xử lý batch atomic |

## 21. Checklist trước production

- **Endpoint:** HTTPS, certificate hợp lệ, WAF/firewall cho phép validation và delivery.
- **Validation:** Event Grid schema trả đúng 200 + validationResponse; CloudEvents OPTIONS dùng allow-list origin.
- **Authentication:** Entra JWT hoặc secret được xác minh ở mỗi POST; issuer, audience, tenant và app role đúng.
- **Authorization:** Endpoint chỉ cho phép Event Grid principal và các role cần thiết.
- **Source:** Topic/source, event type, subject và schema version được allow-list.
- **Idempotency:** Khóa dedup gồm consumer name + source + event ID; unique constraint ở persistent store.
- **Transaction:** Dedup và business state cùng transaction; external side effect dùng outbox/idempotency key.
- **Ordering:** Aggregate version và policy xử lý stale/gap rõ ràng.
- **Response:** Chỉ ACK sau khi persist/commit; hiểu response nào Event Grid retry hoặc drop.
- **Dead-letter:** Đã cấu hình storage, RBAC, encryption, retention, alert và replay runbook.
- **Batch:** Payload size, timeout và all-or-none semantics được kiểm thử.
- **Observability:** Validation, JWT failure, duplicate, identity conflict, delivery retry, inbox và DLQ có metric/alert.
- **Testing:** Đã test sync/manual validation, CloudEvents OPTIONS, auth, duplicate, crash, out-of-order và DLQ.
- **Retention:** Dedup record được giữ đủ lâu so với retry TTL và thời gian replay nghiệp vụ.

## 22. Tổng kết

Xác minh endpoint và xác thực request là hai lớp riêng. Event Grid schema dùng **SubscriptionValidationEvent** với synchronous response HTTP 200 hoặc manual validation URL; CloudEvents dùng OPTIONS với **WebHook-Request-Origin** và các response header **WebHook-Allowed-Origin/Rate**. Cả hai chỉ xác nhận endpoint đồng ý nhận traffic, không chứng minh danh tính request. Webhook production cần HTTPS và authentication như Microsoft Entra bearer token, đồng thời kiểm tra source/topic và event contract.

Event Grid giao at-least-once và không bảo đảm thứ tự, vì vậy duplicate và out-of-order là tình huống bình thường. Với CloudEvents, dùng **source + id**; với Event Grid schema, dùng topic/source scope + id. Ghi inbox và business state trong cùng transaction, giữ event ID ổn định, dùng aggregate version để bảo vệ thứ tự và cấu hình dead-letter để giữ event không giao được. Khi Spring Boot thực hiện đúng các bước này, webhook có thể xác minh endpoint, từ chối request không tin cậy và xử lý retry mà không lặp side effect.

## Tài liệu tham khảo

- [Endpoint validation with Event Grid event schema](https://learn.microsoft.com/en-us/azure/event-grid/end-point-validation-event-grid-events-schema)
- [Endpoint validation with CloudEvents schema](https://learn.microsoft.com/en-us/azure/event-grid/end-point-validation-cloud-events-schema)
- [Troubleshoot Event Grid subscription validation](https://learn.microsoft.com/en-us/azure/event-grid/troubleshoot-subscription-validation)
- [Authenticate event delivery to event handlers](https://learn.microsoft.com/en-us/azure/event-grid/security-authentication)
- [Secure webhook delivery with Microsoft Entra ID](https://learn.microsoft.com/en-us/azure/event-grid/secure-webhook-delivery)
- [Event Grid delivery and retry](https://learn.microsoft.com/en-us/azure/event-grid/delivery-and-retry)
- [EventGridEvent class in Azure SDK for Java](https://learn.microsoft.com/en-us/java/api/com.azure.messaging.eventgrid.eventgridevent?view=azure-java-stable)
- [CloudEvent class in Azure SDK for Java](https://learn.microsoft.com/en-us/java/api/com.azure.core.models.cloudevent?view=azure-java-stable)

