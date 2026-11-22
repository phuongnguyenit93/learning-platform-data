# 16.5. Dùng AuthorizedClientServiceOAuth2AuthorizedClientManager trong job và scheduler

## 1. Bài toán: job không có trình duyệt và người dùng đăng nhập

Một ứng dụng Spring Boot có thể vừa phục vụ người dùng qua giao diện web, vừa chạy những công việc định kỳ:

- Đồng bộ danh mục từ một API nội bộ vào lúc 02:00 hằng ngày.
- Lấy dữ liệu báo cáo theo lịch bằng một service account.
- Gọi API quản lý hóa đơn hoặc tồn kho từ worker.
- Gửi dữ liệu tổng hợp sang một hệ thống đối tác.
- Chạy scheduled task để đối chiếu trạng thái các giao dịch.

Các công việc này không có người dùng đang nhấn nút đăng nhập, không có trình duyệt để redirect tới Identity Provider và thông thường cũng không có <code>HttpServletRequest</code> hay HTTP session.

Nếu cố lấy <code>OAuth2AuthorizedClient</code> từ phiên đăng nhập của một người dùng bất kỳ, job sẽ gặp nhiều vấn đề:

1. Token gắn với người dùng có thể hết hạn, bị thu hồi hoặc không có quyền của service.
2. Job không biết phải dùng session và principal của người dùng nào.
3. Một lần người dùng logout không được phép làm một quy trình hạ tầng phụ thuộc vào session đó thất bại bất ngờ.
4. Dùng token người dùng cho một tác vụ service có thể vi phạm audience, scope và ranh giới ủy quyền.

Với nhu cầu **service-to-service** không cần End-User, OAuth 2.0 cung cấp **Client Credentials Grant**. Spring Security có sẵn manager phù hợp với môi trường ngoài Servlet request:

**<code>AuthorizedClientServiceOAuth2AuthorizedClientManager</code>**.

Manager này phối hợp <code>ClientRegistrationRepository</code>, <code>OAuth2AuthorizedClientService</code> và <code>OAuth2AuthorizedClientProvider</code> để xin, tái sử dụng và cấp lại access token trong service hoặc background job.

> **Nguyên tắc:** Job/scheduler chạy bằng quyền của **Client/service** nên sử dụng ClientRegistration dành riêng cho workload và một authorized-client manager không phụ thuộc HTTP request. <code>principal</code> dùng làm khóa quản lý token, **không phải End-User được giả lập**.

## 2. Phân biệt manager dùng trong web và manager dùng trong service

Spring Security có hai implementation thường gặp:

| Tiêu chí | <code>DefaultOAuth2AuthorizedClientManager</code> | <code>AuthorizedClientServiceOAuth2AuthorizedClientManager</code> |
|---|---|---|
| Ngữ cảnh chủ đạo | Servlet web request | Service layer, job, scheduler, background process |
| Phụ thuộc <code>HttpServletRequest</code> | Có ngữ cảnh request/response thông qua repository | Không |
| Thành phần lưu authorized client | <code>OAuth2AuthorizedClientRepository</code> | <code>OAuth2AuthorizedClientService</code> |
| Có thể xử lý client credentials | Có nếu được cấu hình và ngữ cảnh phù hợp | Có, đặc biệt phù hợp |
| Phù hợp khi không có browser/session | Không phải lựa chọn chính | Có |
| Cần <code>ClientRegistrationRepository</code> | Có | Có |
| Cần grant provider phù hợp | Có | Có |

Đây không phải hai giao thức OAuth 2.0 khác nhau. Cả hai thực thi interface:

~~~java
org.springframework.security.oauth2.client.OAuth2AuthorizedClientManager
~~~

Sự khác biệt chính là **ngữ cảnh và cơ chế lưu trữ**.

### 2.1. Vì sao không nên lấy SecurityContextHolder trong scheduler?

Trong web request đã xác thực, <code>SecurityContextHolder</code> thường có <code>Authentication</code> của người dùng hiện tại. Một scheduled task chạy trên thread của scheduler, không mặc nhiên mang SecurityContext của request nào.

Ví dụ cách làm dễ sai:

~~~java
Authentication authentication =
    SecurityContextHolder.getContext().getAuthentication();

String principal = authentication.getName();
~~~

Trong scheduled task, <code>authentication</code> có thể là <code>null</code>. Ngay cả khi có một SecurityContext được truyền qua thread, job hạ tầng cũng không nên tự động sử dụng quyền của một người dùng để lấy service token.

Đối với Client Credentials Grant, hãy chọn một **principal tổng hợp do backend định nghĩa**, ví dụ <code>nightly-sync-worker</code>, để manager biết nên lưu authorized client dưới khóa nào.

### 2.2. Manager không đồng nghĩa token client

Các khái niệm cần tách biệt:

| Thành phần | Vai trò |
|---|---|
| <code>ClientRegistration</code> | Cấu hình Client ID, client authentication, grant type, token endpoint và scope |
| <code>OAuth2AuthorizeRequest</code> | Một yêu cầu authorize theo registration và principal |
| <code>OAuth2AuthorizedClientProvider</code> | Thực hiện grant tương ứng khi đủ điều kiện |
| <code>OAuth2AuthorizedClientManager</code> | Điều phối provider với registration và authorized-client storage |
| <code>OAuth2AuthorizedClient</code> | ClientRegistration + principalName + access token + refresh token tùy chọn |
| <code>OAuth2AuthorizedClientService</code> | Lưu, tra cứu, xóa authorized client theo registration/principal |

Đừng nhầm <code>OAuth2AuthorizedClientService</code> với <code>ClientRegistrationRepository</code>. Repository registration chỉ giữ **metadata Client**, không phải token đã được cấp.

## 3. Luồng Client Credentials khi job chạy

Với một job dùng <code>reports-job</code>:

~~~mermaid
sequenceDiagram
    autonumber
    participant S as Spring Scheduler
    participant J as ReportsJob
    participant M as AuthorizedClientServiceOAuth2AuthorizedClientManager
    participant Store as OAuth2AuthorizedClientService
    participant OP as Authorization Server
    participant API as Reports Resource Server

    S->>J: Chạy theo lịch
    J->>M: authorize(registrationId=reports-job, principal=reports-worker)
    M->>Store: loadAuthorizedClient(reports-job, reports-worker)
    alt Chưa có token hoặc access token cần cấp lại
        M->>OP: POST /token, grant_type=client_credentials
        OP-->>M: Access token, expiry, scope
        M->>Store: saveAuthorizedClient
    else Access token hiện hành còn dùng được
        Store-->>M: Authorized client đã lưu
    end
    M-->>J: OAuth2AuthorizedClient
    J->>API: Gọi API bằng Bearer access token
    API-->>J: Kết quả theo quyền service
    J-->>S: Kết thúc lượt chạy
~~~

Luồng này **không có** authorization endpoint, redirect URI, browser callback hay authorization code. Client xác thực trực tiếp với Token Endpoint theo Client Credentials Grant đã đăng ký.

Một token response minh họa:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
Cache-Control: no-store

{
  "access_token": "ACCESS_TOKEN_PLACEHOLDER",
  "token_type": "Bearer",
  "expires_in": 1800,
  "scope": "reports.read"
}
~~~

Giá trị token chỉ là placeholder. Theo thiết kế thông thường, **Client Credentials Grant không cần refresh token**: khi access token hết hạn, manager có thể xin một token mới bằng cùng grant nếu Client vẫn được phép.

## 4. Cấu hình ClientRegistration dành riêng cho job

### 4.1. Dependencies

Với Spring Boot 3 / Spring Security 6, ứng dụng server-side có thể dùng:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-client'
    implementation 'org.springframework.boot:spring-boot-starter-web'
}
~~~

<code>spring-boot-starter-web</code> trong ví dụ cung cấp các thành phần HTTP tiện dùng, gồm <code>RestClient</code> trên Spring Framework 6.1+ (điển hình Spring Boot 3.2+). Worker không nhất thiết phải chạy một web server chỉ để sử dụng OAuth2 Client; có thể dùng các dependency HTTP client phù hợp với kiến trúc và tắt web application type khi cần.

### 4.2. application.yml

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          reports-job:
            provider: service-auth
            client-id: reports-worker
            client-secret: ${REPORTS_WORKER_CLIENT_SECRET}
            client-authentication-method: client_secret_basic
            authorization-grant-type: client_credentials
            scope:
              - reports.read
        provider:
          service-auth:
            token-uri: https://auth.example.org/oauth2/token

app:
  reports-api:
    base-url: https://api.example.org
  reports-job:
    cron: "0 15 2 * * *"
~~~

Giải thích:

| Thuộc tính | Chức năng |
|---|---|
| <code>registration.reports-job</code> | ID nội bộ để manager chọn ClientRegistration |
| <code>client-id</code> | Định danh Client được Authorization Server cấp |
| <code>client-secret</code> | Bí mật confidential Client; lấy từ biến môi trường/secret manager |
| <code>client-authentication-method</code> | Cách Client xác thực tại Token Endpoint; phải trùng cấu hình OP |
| <code>authorization-grant-type</code> | <code>client_credentials</code> |
| <code>scope</code> | Quyền API tối thiểu mà service thực sự cần |
| <code>provider.service-auth.token-uri</code> | Token Endpoint đúng của Authorization Server |
| <code>app.reports-api.base-url</code> | Resource Server đích; không phải Token Endpoint |
| <code>app.reports-job.cron</code> | Lịch chạy của ứng dụng, không phải thuộc tính OAuth2 Client |

Các domain, Client ID và cron trên chỉ là ví dụ, không đại diện cho hệ thống thật. Credential phải được cấp hợp lệ và **không commit giá trị bí mật** vào source.

Client Credentials Grant không cần <code>redirect-uri</code>, <code>authorization-uri</code> hay scope <code>openid</code> cho việc đăng nhập End-User. Nếu provider hỗ trợ OAuth2/OIDC, việc dùng cùng Authorization Server không biến service job thành một OIDC Login Client.

### 4.3. Token được cấp cho ai?

Trong Client Credentials Grant, Authorization Server cấp access token cho **Client/service identity** theo scope và policy. Token không mặc nhiên chứa danh tính người dùng đã đăng nhập.

<code>principal("reports-worker-runtime")</code> trong yêu cầu manager không phải một chỉ thị để OP phát token “thay mặt người dùng reports-worker-runtime”. Nó chỉ là **khóa principal dùng lưu/tra cứu authorized client trong Spring Security**, độc lập với token subject/audience do OP quyết định.

## 5. Tạo AuthorizedClientServiceOAuth2AuthorizedClientManager

Ví dụ cấu hình:

~~~java
package example.security;

import java.time.Duration;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.client.AuthorizedClientServiceOAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientProvider;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientProviderBuilder;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientService;
import org.springframework.security.oauth2.client.registration.ClientRegistrationRepository;

@Configuration
public class ReportsOAuth2ClientConfig {

    @Bean("reportsAuthorizedClientManager")
    OAuth2AuthorizedClientManager reportsAuthorizedClientManager(
            ClientRegistrationRepository registrations,
            OAuth2AuthorizedClientService authorizedClients) {

        OAuth2AuthorizedClientProvider provider =
            OAuth2AuthorizedClientProviderBuilder.builder()
                .clientCredentials(configurer -> configurer
                    .clockSkew(Duration.ofSeconds(60)))
                .build();

        var manager =
            new AuthorizedClientServiceOAuth2AuthorizedClientManager(
                registrations, authorizedClients);

        manager.setAuthorizedClientProvider(provider);
        return manager;
    }
}
~~~

Từng bước:

1. Spring Boot tạo các registration từ <code>spring.security.oauth2.client.registration.*</code> khi auto-configuration phù hợp.
2. <code>ClientRegistrationRepository</code> cho biết <code>reports-job</code> dùng Client ID, grant type, scope và token endpoint nào.
3. <code>OAuth2AuthorizedClientService</code> giữ các authorized client đã cấp token; Spring Boot/Spring Security có thể cung cấp implementation mặc định, tùy cấu hình.
4. <code>OAuth2AuthorizedClientProviderBuilder.builder().clientCredentials()</code> chỉ bật **Client Credentials Grant** cho manager này.
5. <code>clockSkew(Duration.ofSeconds(60))</code> cho phép xem access token sắp hết hạn là cần cấp lại sớm, tránh việc token hết hạn giữa một lời gọi API.
6. Manager được đặt tên <code>reportsAuthorizedClientManager</code> để có thể inject đúng bean khi ứng dụng có nhiều manager.

Trong production, tùy lifetime của access token và độ lệch đồng hồ, có thể điều chỉnh skew nhỏ hơn/lớn hơn. Skew không tăng lifetime thực của token và không bảo đảm mọi request API thành công.

### 5.1. Vì sao chỉ chọn clientCredentials()?

Job này không cần browser hoặc user authorization:

~~~java
OAuth2AuthorizedClientProvider provider =
    OAuth2AuthorizedClientProviderBuilder.builder()
        .clientCredentials()
        .build();
~~~

Không bắt buộc thêm <code>authorizationCode()</code> và <code>refreshToken()</code>. Thêm các provider khác không biến registration thành grant khác, nhưng sẽ làm cấu hình khó đọc và có thể mở đường cho hành vi ngoài mong muốn nếu về sau thay đổi registration/manager.

<code>OAuth2AuthorizedClientProviderBuilder</code> quyết định những grant provider manager có thể dùng; <code>ClientRegistration.authorizationGrantType</code> và chính sách Authorization Server quyết định grant thực tế của Client.

### 5.2. Service storage mặc định và thay thế

<code>OAuth2AuthorizedClientService</code> có thể là:

- <code>InMemoryOAuth2AuthorizedClientService</code>: lưu trong memory tiến trình; phù hợp demo/single-instance.
- <code>JdbcOAuth2AuthorizedClientService</code>: lưu trong database theo schema tương ứng; phù hợp khi cần persistence.
- Implementation tùy biến có mã hóa, cache hoặc distributed store theo yêu cầu dự án.

Một ví dụ bean in-memory nếu ứng dụng cần cấu hình tường minh:

~~~java
@Bean
OAuth2AuthorizedClientService authorizedClientService(
        ClientRegistrationRepository registrations) {
    return new InMemoryOAuth2AuthorizedClientService(registrations);
}
~~~

Khi sử dụng đoạn này cần import các class tương ứng. **Không tạo bean trùng khi Spring Boot đã tự cung cấp service**, trừ khi chủ động thay thế auto-configuration bằng một thiết kế rõ ràng.

Không phải cứ chạy nhiều instance là nhất thiết phải chia sẻ một access token; với Client Credentials, mỗi instance có thể tự xin token nếu chính sách OP cho phép. Nhưng token rate limit, concurrent token requests, security, storage và hiệu năng sẽ khác; cần cân nhắc thực tế.

## 6. Tạo scheduler và gọi manager từ một job

Ví dụ này sử dụng Spring Scheduling và <code>RestClient</code>. Phần HTTP client chỉ gọi một API giả định trả dữ liệu báo cáo.

### 6.1. Bật scheduling

~~~java
package example;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.scheduling.annotation.EnableScheduling;

@SpringBootApplication
@EnableScheduling
public class ReportsApplication {
    public static void main(String[] args) {
        SpringApplication.run(ReportsApplication.class, args);
    }
}
~~~

<code>@EnableScheduling</code> kích hoạt việc xử lý <code>@Scheduled</code>. Với Spring cron expression trong ví dụ:

~~~text
0 15 2 * * *
~~~

có **sáu trường**: giây, phút, giờ, ngày trong tháng, tháng, thứ. Với timezone UTC được chỉ định, job chạy lúc **02:15 UTC** theo lịch cron. Đây không phải Unix cron năm trường.

### 6.2. Tạo RestClient cho Resource Server

~~~java
package example.security;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.client.RestClient;

@Configuration
public class ReportsApiConfig {

    @Bean("reportsApiClient")
    RestClient reportsApiClient(
            RestClient.Builder builder,
            @Value("${app.reports-api.base-url}") String baseUrl) {
        return builder.baseUrl(baseUrl).build();
    }
}
~~~

Token Endpoint và Resource Server là hai đích HTTP khác nhau:

~~~text
Token Endpoint: https://auth.example.org/oauth2/token
Reports API:    https://api.example.org/v1/reports/daily
~~~

Trong hệ thống thật, cấu hình HTTP client cần có timeout, TLS validation, connection management và giới hạn dữ liệu trả về. Ví dụ dùng builder tối giản để tập trung vào OAuth2 manager.

### 6.3. Viết scheduled job

~~~java
package example.jobs;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.security.oauth2.client.OAuth2AuthorizeRequest;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClient;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientManager;
import org.springframework.stereotype.Component;
import org.springframework.web.client.RestClient;

@Component
public class DailyReportsJob {

    private static final Logger log =
        LoggerFactory.getLogger(DailyReportsJob.class);

    private static final String REGISTRATION_ID = "reports-job";
    private static final String JOB_PRINCIPAL = "reports-worker-runtime";

    private final OAuth2AuthorizedClientManager authorizedClientManager;
    private final RestClient reportsApi;

    public DailyReportsJob(
            @Qualifier("reportsAuthorizedClientManager")
            OAuth2AuthorizedClientManager authorizedClientManager,
            @Qualifier("reportsApiClient") RestClient reportsApi) {
        this.authorizedClientManager = authorizedClientManager;
        this.reportsApi = reportsApi;
    }

    @Scheduled(cron = "${app.reports-job.cron}", zone = "UTC")
    public void run() {
        OAuth2AuthorizeRequest authorizeRequest =
            OAuth2AuthorizeRequest
                .withClientRegistrationId(REGISTRATION_ID)
                .principal(JOB_PRINCIPAL)
                .build();

        OAuth2AuthorizedClient authorizedClient =
            authorizedClientManager.authorize(authorizeRequest);

        if (authorizedClient == null) {
            throw new IllegalStateException(
                "No authorized client for reports-job");
        }

        String accessToken =
            authorizedClient.getAccessToken().getTokenValue();

        String report = reportsApi.get()
            .uri("/v1/reports/daily")
            .headers(headers -> headers.setBearerAuth(accessToken))
            .retrieve()
            .body(String.class);

        if (report == null) {
            throw new IllegalStateException("Reports API returned no data");
        }

        // Minh họa: tại đây gọi domain service xử lý dữ liệu báo cáo.
        // Không ghi nội dung báo cáo hoặc accessToken ra log.
        log.info("Reports job completed, response length={}",
            report.length());
    }
}
~~~

Tại thời điểm job chạy:

1. <code>OAuth2AuthorizeRequest</code> cho biết registration <code>reports-job</code> và principal tổng hợp của workload.
2. Manager tra storage theo cặp registration/principal.
3. Nếu đã có access token còn dùng được, manager có thể trả lại authorized client hiện hành.
4. Nếu chưa có token hoặc token cần cấp lại, Client Credentials Provider gửi token request.
5. Manager lưu authorized client sau khi cấp token thành công theo success handler cấu hình.
6. Job lấy access token và gọi Resource Server.

Ví dụ cố tình **không tạo một HTTP endpoint trả token**. Access token chỉ được dùng trong backend để gọi đúng API.

Trong production, thay xử lý response dạng <code>String</code> bằng DTO có validation, giới hạn kích thước response, quy tắc idempotency và domain service phù hợp. Không log PII hoặc raw JSON chỉ vì muốn kiểm tra job.

### 6.4. Vì sao phải dùng @Qualifier?

Ứng dụng có thể có:

- Web manager để phục vụ OAuth2 Login/authorization code.
- Service manager dành cho job <code>reports-job</code>.
- Service manager khác dành cho việc xuất hóa đơn.

Khi có nhiều bean <code>OAuth2AuthorizedClientManager</code>, dùng <code>@Qualifier</code> giúp inject đúng manager với provider/storage đã thiết kế. Nếu inject nhầm web manager từ một scheduler không có Servlet request, kết quả có thể là lỗi thiếu request context hoặc không authorize như mong muốn.

## 7. OAuth2AuthorizeRequest: registrationId và principal là hai khóa khác nhau

Đoạn code tối thiểu:

~~~java
OAuth2AuthorizeRequest request =
    OAuth2AuthorizeRequest
        .withClientRegistrationId("reports-job")
        .principal("reports-worker-runtime")
        .build();
~~~

Ý nghĩa:

| Trường | Mục đích |
|---|---|
| <code>clientRegistrationId</code> | Chọn ClientRegistration và token endpoint/grant/client authentication tương ứng |
| <code>principal</code> | Phân vùng authorized-client storage cho ngữ cảnh workload |

Một authorized client về cơ bản được tìm trong service theo:

~~~text
(registrationId, principalName)
~~~

Ví dụ:

~~~text
(reports-job, reports-worker-runtime)
(billing-job, billing-worker-runtime)
(reports-job, tenant-a-reports-worker)
~~~

Điểm cần hiểu là **principal tổng hợp không biến thành subject người dùng trong access token**. Authorization Server xác định service identity, scope, audience và các claim token.

### 7.1. Chọn principal tổng hợp như thế nào?

Tốt:

~~~text
reports-worker-runtime
inventory-import-service
tenant-a-report-sync
~~~

Cần tránh:

~~~java
.principal(request.getParameter("principal"))
~~~

Trong trường hợp có HTTP endpoint kích hoạt job, không bao giờ để caller tự chọn principal để truy xuất token đặc quyền. Principal key phải do backend định nghĩa hoặc suy ra từ ngữ cảnh tenant đã được xác thực và kiểm soát.

### 7.2. Một registration nhưng nhiều principal tổng hợp

Với Client Credentials, nếu nhiều principal cùng dùng **một ClientRegistration với cùng credential/scope/audience**, chúng có thể khiến manager lưu nhiều bản access token cho cùng service identity. Điều này không tạo ra nhiều quyền độc lập tại Authorization Server, chỉ tạo thêm các **bucket lưu trữ**.

Nếu mục tiêu là tách tenant về bảo mật, chỉ đổi principalName **chưa đủ**. Có thể cần ClientRegistration/Client ID riêng, scope khác, audience khác hoặc chính sách cấp quyền ở Resource Server.

### 7.3. Không thay principal tùy tiện giữa các lượt chạy

Sai về hiệu quả cache:

~~~java
.principal(UUID.randomUUID().toString())
~~~

Mỗi lần chạy tạo principal mới khiến manager không thể tìm lại authorized client từ lần trước dưới cùng khóa, nên có thể xin token mới nhiều hơn cần thiết.

Nên dùng key ổn định theo workload/tenant. Nếu cần chủ động tách state theo phiên xử lý, đó là quyết định có lý do rõ ràng chứ không phải ngẫu nhiên mỗi lần gọi.

## 8. Cấp lại access token và thời gian hết hạn

### 8.1. Manager có tự xin token ở mỗi lần chạy không?

Không nhất thiết. Nếu authorized client đã tồn tại và access token chưa cần cấp lại, manager có thể **tái sử dụng token**. Điều này giảm request tới Token Endpoint và giúp giảm nguy cơ rate limit.

Ví dụ:

~~~text
02:15 Job lần 1
  → storage chưa có authorized client
  → xin access token mới, expiresAt = 02:45

02:20 Job được kích hoạt lại theo một sự kiện
  → access token còn dùng được
  → có thể tái sử dụng

02:44 Job chạy
  → token gần hết hạn; clock skew = 60 giây
  → xin access token mới qua client_credentials
~~~

Đây là ví dụ thời điểm để hiểu hành vi; quyết định thực tế tùy thời gian hết hạn và cấu hình provider.

### 8.2. Refresh token có cần cho client_credentials không?

Thông thường không. Với Client Credentials, Client có thể dùng Client ID/credential của chính mình để xin một access token mới. Nhiều Authorization Server không cấp refresh token cho grant này.

Vì vậy:

~~~java
OAuth2AuthorizedClientProviderBuilder.builder()
    .clientCredentials()
    .build();
~~~

thường đáp ứng use case. Thêm <code>.refreshToken()</code> chỉ vì thấy access token hết hạn là không cần thiết cho đa số client credentials workloads.

### 8.3. Clock skew không phải gia hạn token

Khi đặt:

~~~java
.clientCredentials(configurer ->
    configurer.clockSkew(Duration.ofSeconds(60)))
~~~

manager có thể coi token sắp hết hạn trong 60 giây là cần làm mới. Điều đó không thay đổi <code>expiresAt</code> do Authorization Server cấp và không cho phép dùng token sau khi Resource Server từ chối.

Clock skew quá lớn với token lifetime ngắn có thể khiến job xin token liên tục. Cần chọn giá trị hợp lý và đồng bộ đồng hồ hệ thống.

## 9. AuthorizedClientService lưu token ở đâu?

<code>AuthorizedClientServiceOAuth2AuthorizedClientManager</code> sử dụng <code>OAuth2AuthorizedClientService</code> để lưu/tra cứu authorized client.

Các phương thức quan trọng:

~~~java
OAuth2AuthorizedClient loadAuthorizedClient(
    String clientRegistrationId,
    String principalName);

void saveAuthorizedClient(
    OAuth2AuthorizedClient authorizedClient,
    Authentication principal);

void removeAuthorizedClient(
    String clientRegistrationId,
    String principalName);
~~~

### 9.1. In-memory

<code>InMemoryOAuth2AuthorizedClientService</code> giữ token trong memory:

- Đơn giản cho demo và ứng dụng single-node.
- Mất token khi restart, nhưng Client Credentials Manager có thể xin lại nếu credential hợp lệ.
- Không chia sẻ token giữa các instance.
- Không bảo vệ khỏi token request trùng khi nhiều node cùng chạy job.

Mất token local sau restart **không đồng nghĩa Authorization Server thu hồi token đã cấp trước đó**. Token cũ có thể vẫn còn hiệu lực ở Resource Server cho đến khi hết hạn hoặc bị thu hồi.

### 9.2. JDBC/persistent storage

<code>JdbcOAuth2AuthorizedClientService</code> hoặc storage tùy biến phù hợp khi cần:

- Tái sử dụng authorized client qua restart.
- Chia sẻ trạng thái giữa nhiều instance.
- Quản lý lưu trữ tập trung, giám sát và lifecycle.
- Thiết kế concurrency khi có nhiều lượt authorize đồng thời.

Tuy nhiên cần bảo vệ token trong database vì access token là credential. Áp dụng quyền truy cập tối thiểu, TLS tới database, encryption-at-rest hoặc mã hóa ở lớp ứng dụng nếu phù hợp, audit và retention policy.

### 9.3. Có nhất thiết phải dùng JDBC cho mọi job?

Không. Với Client Credentials Grant, việc xin token mới có thể đơn giản và đúng giao thức. Nếu ứng dụng chỉ có một instance và Token Endpoint có thể đáp ứng nhu cầu, in-memory service có thể phù hợp.

Khi số instance tăng hoặc Authorization Server có rate limit thấp, persistent storage/caching tập trung có thể giúp giảm request xin token. Nhưng chia sẻ authorized client cũng tạo bài toán cập nhật đồng thời và quyền truy cập storage; phải đánh giá tổng thể, không chỉ chọn theo hiệu năng.

## 10. Scheduled task chạy trên nhiều instance

<code>@Scheduled</code> là cơ chế lập lịch **trong tiến trình ứng dụng**. Nếu triển khai ba instance cùng bật scheduling, cả ba có thể chạy cùng job theo cron:

~~~text
02:15  Instance A → chạy job
02:15  Instance B → chạy job
02:15  Instance C → chạy job
~~~

<code>AuthorizedClientServiceOAuth2AuthorizedClientManager</code> **không khóa việc chạy job** và cũng không tự biến scheduler thành một distributed job coordinator.

### 10.1. Tách hai vấn đề: lịch chạy và token

| Vấn đề | Cơ chế cần xem |
|---|---|
| Chỉ một instance được thực thi nghiệp vụ | Distributed scheduler, leader election, distributed lock hoặc worker queue |
| Không chạy chồng hai lượt của cùng job | Lock, concurrency policy, deduplication |
| Token có thể tái sử dụng giữa các node | Shared authorized-client storage nếu cần |
| Hai node cùng xin token | Throttling/concurrency coordination hoặc chấp nhận token độc lập theo chính sách |
| Job không gây side effect lặp | Idempotency key, transaction boundary và domain logic |

Ngay cả khi chỉ một node được chạy nghiệp vụ, các node khác vẫn có thể cần token cho workload khác. Lock job và storage token **không phải cùng một khóa**.

### 10.2. Lock job không thay thế tính idempotent

Một lock có thể bị hết hạn khi job vẫn chạy, node có thể crash sau khi gửi yêu cầu nhưng trước khi ghi trạng thái thành công, hoặc scheduler có thể retry. Vì vậy đối với API thay đổi dữ liệu:

- Dùng **idempotency key** khi API đích hỗ trợ.
- Thiết kế cập nhật dữ liệu có version hoặc unique constraint.
- Phân biệt lỗi trước khi gửi request với kết quả “không biết server đã xử lý hay chưa”.
- Không retry vô hạn một POST chỉ vì timeout.

Đây là thiết kế vận hành của job, không phải chức năng của OAuth2 Authorized Client Manager.

### 10.3. Token reuse giữa các node

Nếu các node dùng chung client credentials và cùng principal key trong một JDBC service, một node có thể lưu authorized client để node khác đọc.

Nhưng cần lưu ý:

- Hai node cùng thấy access token sắp hết hạn có thể cùng xin token mới.
- Các node có thể ghi đè authorized client vào cùng một hàng.
- Nếu một provider có policy token rotation/revocation đặc biệt, trạng thái cập nhật muộn có thể gây lỗi.
- Storage có thể cần optimistic locking, caching hoặc điều phối theo khóa nếu tính nhất quán là yêu cầu.

Token do Client Credentials cấp thường không chứa End-User, nhưng vẫn phải tuân thủ scope, audience và authorization của workload.

## 11. Xử lý lỗi authorize trong job

Hai nhóm lỗi phải phân biệt:

1. **Lỗi xin token:** Client Credentials authorization thất bại trước khi job gọi API.
2. **Lỗi Resource Server:** manager đã trả token nhưng API đích từ chối token hoặc không xử lý được yêu cầu.

### 11.1. Token Endpoint từ chối Client

Các mã OAuth2 Token Endpoint thường gặp:

| Mã lỗi | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| <code>invalid_client</code> | Client ID/secret hoặc client authentication sai | Kiểm tra secret rotation, cấu hình OP, môi trường |
| <code>unauthorized_client</code> | Client không được phép dùng client credentials | Kiểm tra grant được cấp phép |
| <code>unsupported_grant_type</code> | Endpoint/Authorization Server không hỗ trợ grant | Kiểm tra token URI và grant type |
| <code>invalid_scope</code> | Scope không tồn tại hoặc không được phép | Kiểm tra scopes tại OP và Resource Server |
| <code>invalid_request</code> | Form/token request sai | Kiểm tra cấu hình Client và converter |

Với những lỗi cấu hình có tính quyết định như <code>invalid_client</code> hoặc <code>unauthorized_client</code>, retry ngay nhiều lần hiếm khi có ích và có thể khiến tài khoản service bị rate limit/khóa.

Ví dụ bắt lỗi để phân loại ở ranh giới job:

~~~java
import org.springframework.security.oauth2.core.OAuth2AuthorizationException;

try {
    OAuth2AuthorizedClient client = manager.authorize(authorizeRequest);
    if (client == null) {
        throw new IllegalStateException("No client credentials provider result");
    }
    // Tiếp tục gọi API khi có client phù hợp.
} catch (OAuth2AuthorizationException ex) {
    // Chỉ ghi mã lỗi đã kiểm soát, không ghi raw token response hoặc secret.
    String code = ex.getError().getErrorCode();
    throw new IllegalStateException(
        "Service OAuth2 authorization failed, errorCode=" + code, ex);
}
~~~

Đoạn này minh họa cách nhận lỗi. Trong production, <code>errorCode</code> cũng là dữ liệu phía provider: nên dùng allowlist hoặc giới hạn ký tự/độ dài khi đưa vào telemetry. Không trả raw <code>error_description</code> của Token Endpoint ra UI hay log, và không in stack trace chứa HTTP request nếu HTTP client có thể chứa credential.

### 11.2. HTTP 401 của Resource Server

Giả sử manager vừa trả token, nhưng API trả:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer error="invalid_token"
~~~

Nguyên nhân có thể:

- Access token hết hạn trước/sát khi được sử dụng.
- Token bị thu hồi.
- Token có issuer hoặc audience không đúng Resource Server.
- Resource Server không tin khóa ký hoặc introspection endpoint gặp lỗi.
- Cache/storage của Client chứa token không còn dùng được.

**Không giả định mọi 401 chỉ cần gọi <code>authorize()</code> lần nữa là hết.** Nếu token chưa gần hết hạn theo manager, lần gọi lại có thể tái sử dụng chính token cũ. Cần có chính sách loại bỏ authorized client stale, xác minh audience/scope, và chỉ retry có giới hạn khi thực sự có khả năng hồi phục.

Một số interceptor/HTTP integration của Spring Security có cơ chế xử lý authorized client failure khi Resource Server từ chối token. Nếu tự gắn Bearer header thủ công như ví dụ mục 6, **ứng dụng phải tự xử lý HTTP error và cleanup/retry policy phù hợp**; manager không thể quan sát HTTP 401 từ lời gọi RestClient nếu bạn không đưa thông tin đó vào cơ chế tương ứng.

### 11.3. HTTP 403 của Resource Server

HTTP 403 thường có thể biểu thị token được xác nhận nhưng **không đủ quyền** cho thao tác. Nếu API đích báo <code>insufficient_scope</code>, cần điều chỉnh ClientRegistration scope/permission và chính sách cấp quyền, không chỉ xoá token rồi xin một token mới y hệt.

### 11.4. Timeout, 429 và HTTP 5xx

| Lỗi | Khuyến nghị |
|---|---|
| Timeout khi xin token | Phân loại transport failure; retry có giới hạn, backoff/jitter phù hợp |
| HTTP 429 từ Token Endpoint | Tôn trọng rate limit và <code>Retry-After</code> khi đáng tin, giảm token requests |
| HTTP 502/503 từ Token Endpoint | Giám sát outage, dùng bounded retry nếu policy cho phép |
| Timeout khi gọi API nghiệp vụ | Xác định khả năng side effect đã xảy ra trước khi retry |
| HTTP 503 từ API | Circuit breaker/backoff; không tự quy mọi lỗi cho OAuth2 token |

Đối với Client Credentials, xin lại token có thể ít rủi ro “code đã dùng một lần” hơn Authorization Code Flow; tuy nhiên vẫn phải giới hạn retry và không giả định mọi token endpoint đều idempotent hoàn toàn ở mọi extension.

### 11.5. @Scheduled báo lỗi thế nào?

Một method <code>@Scheduled</code> trả <code>void</code> không tự có người dùng để hiển thị lỗi. Tùy scheduler/error handler, exception có thể được log rồi lượt chạy tiếp theo vẫn được thực hiện.

Ứng dụng cần có:

- Metric về lượt chạy thành công/thất bại và duration.
- Alert khi nhiều lượt thất bại liên tiếp hoặc vượt thời gian kỳ vọng.
- Correlation ID nội bộ để đối chiếu request API.
- Chính sách retry/recovery được định nghĩa rõ, không phụ thuộc việc một exception bất kỳ làm scheduler ngừng vĩnh viễn.
- Không ghi access token, secret, raw response có PII vào logs/metrics.

Đừng coi “không thấy exception trong console” là bằng chứng công việc đã hoàn tất. Job phải tự xác nhận kết quả nghiệp vụ cần thiết.

## 12. Success handler, failure handler và trạng thái token

<code>AuthorizedClientServiceOAuth2AuthorizedClientManager</code> có các handler để quyết định lưu hoặc xử lý authorized client sau authorize.

Thông thường:

~~~text
manager.authorize(...)
    → Provider thực hiện Client Credentials Grant
    → Token response hợp lệ
    → OAuth2AuthorizedClient mới
    → AuthorizationSuccessHandler lưu qua OAuth2AuthorizedClientService
~~~

Manager mặc định được cấu hình để lưu authorized client khi cấp token thành công. Không cần tự gọi <code>service.saveAuthorizedClient(...)</code> sau **mỗi** <code>manager.authorize(...)</code> trong ví dụ thông thường.

Nếu ứng dụng **ghi đè success handler**, cần đảm bảo token mới vẫn được lưu theo thiết kế. Một handler chỉ ghi log và không lưu có thể làm mỗi lần chạy job đều xin token mới.

Khi provider trả lỗi, manager có failure handler theo cấu hình/version. Không nên giả định **mọi lỗi** đều khiến authorized client cũ bị xóa; cũng không nên tự xóa tất cả authorized clients khi Authorization Server tạm thời mất kết nối.

Các mã như <code>invalid_grant</code> có thể cho thấy refresh token không còn hợp lệ trong những flow dùng refresh grant. Với Client Credentials thường không có refresh token, nên cần đánh giá lỗi đúng grant đang chạy thay vì áp dụng một policy cleanup chung cho mọi loại token.

## 13. Điều chỉnh tần suất và giảm request token không cần thiết

Mỗi lần <code>@Scheduled</code> chạy, code thường gọi <code>manager.authorize(...)</code>. Điều này **không có nghĩa mỗi lần đều gửi POST /token**.

Manager/service có thể tái sử dụng authorized client còn hiệu lực.

Tuy nhiên nếu:

- Principal key thay đổi mỗi lần.
- Registration ID sai hoặc thay đổi.
- Dùng in-memory storage và các instance thường restart.
- Clock skew quá lớn.
- Token rất ngắn hạn.
- Success handler không lưu kết quả.
- Storage phân tán không nhất quán.

thì Token Endpoint có thể bị gọi nhiều hơn dự kiến.

### 13.1. Anti-pattern: principal ngẫu nhiên

~~~java
OAuth2AuthorizeRequest request =
    OAuth2AuthorizeRequest
        .withClientRegistrationId("reports-job")
        .principal(java.util.UUID.randomUUID().toString())
        .build();
~~~

Mỗi lần chạy tạo một principal mới khiến lookup khó tìm lại authorized client cũ. Không nên dùng cách này chỉ để có “ID độc nhất”.

### 13.2. Anti-pattern: gọi Token Endpoint trực tiếp tại mọi job

~~~text
Mỗi job run:
    POST /token với client secret
    gọi API bằng access token vừa cấp
    bỏ token sau request
~~~

Cách đó có thể hoạt động về mặt giao thức nhưng khó quản lý token reuse, lỗi, retry và rate limit. Dùng manager/service thường rõ ràng và nhất quán hơn.

### 13.3. Không cache chuỗi token bằng static field

Token là credential với expiry và có thể bị thu hồi. Một static String trong singleton không giữ được đầy đủ thông tin registration/principal/expiry và dễ bị dùng sai giữa tenant hoặc workload.

<code>OAuth2AuthorizedClient</code> và service/manager cung cấp mô hình vòng đời phù hợp hơn.

## 14. Một job cần nhiều API hoặc nhiều registration

Giả sử job phải gọi:

~~~text
Reports API: registrationId=reports-job, scope=reports.read
Billing API: registrationId=billing-job, scope=billing.write
~~~

Nên định nghĩa hai ClientRegistration riêng nếu client credential, audience hoặc policy cấp quyền khác nhau.

Ví dụ:

~~~java
OAuth2AuthorizeRequest reportsRequest =
    OAuth2AuthorizeRequest
        .withClientRegistrationId("reports-job")
        .principal("nightly-worker")
        .build();

OAuth2AuthorizeRequest billingRequest =
    OAuth2AuthorizeRequest
        .withClientRegistrationId("billing-job")
        .principal("nightly-worker")
        .build();
~~~

Hai authorized client khác nhau vì registration ID khác nhau, dù dùng chung principal tổng hợp. Tuy vậy, nên chọn principal riêng cho từng workload nếu có yêu cầu rõ về isolation, vận hành hoặc rotation.

Không lấy access token của <code>reports-job</code> gửi sang Billing API chỉ vì cả hai dùng Bearer token. Resource Server phải chấp nhận đúng issuer, audience, scope và chính sách authorization.

### 14.1. Một manager hay nhiều manager?

Nếu các job cùng dùng client credentials, cùng storage và cùng chính sách token handling, **một service manager** có thể phục vụ nhiều registration.

Khi một nhóm job cần client credentials nhưng một nhóm khác cần authorization/refresh token theo người dùng, nên cân nhắc manager riêng:

- Manager cho web OAuth2 Login, gắn với HTTP request.
- Manager cho service jobs, không phụ thuộc HTTP request.

Tách manager giúp cấu hình provider tối thiểu và tránh lẫn user token với service token.

### 14.2. Job đa tenant

Với tenant A/B, chỉ đổi principalName không luôn đủ:

~~~text
Tenant A: client ID A, audience A, scope A
Tenant B: client ID B, audience B, scope B
~~~

Nếu quyền/Client credentials tách nhau theo tenant, cần registration riêng hoặc cơ chế registration động được quản lý đúng. Principal key phải có namespace để tránh token bị ghi đè giữa các tenant.

Không cho request HTTP tự khai tenant rồi dùng trực tiếp để chọn service token đặc quyền. Phải xác minh tenant context bằng cơ chế authentication/authorization của backend.

## 15. Bảo mật credential trong scheduler

Một job không có user vẫn phải tuân thủ đầy đủ yêu cầu bảo vệ OAuth2 credentials.

### 15.1. Giữ secret ở backend

Không hardcode:

~~~yaml
client-secret: my-real-secret-value
~~~

Nên dùng biến môi trường hoặc secret store:

~~~yaml
client-secret: ${REPORTS_WORKER_CLIENT_SECRET}
~~~

Khi rotate secret, cần có kế hoạch triển khai an toàn. Nếu Authorization Server đổi secret nhưng job vẫn dùng cấu hình cũ, token endpoint có thể trả <code>invalid_client</code>.

### 15.2. Không ghi token vào log

Không log:

- <code>authorizedClient.getAccessToken().getTokenValue()</code>.
- Refresh token, nếu có.
- Client secret hoặc Authorization header.
- Raw token response.
- URL chứa credential trong query string.

Telemetry an toàn hơn:

~~~text
job=reports-daily
registrationId=reports-job
authorizedClientFound=true
tokenRefreshOrIssueResult=success
apiStatus=200
durationMs=1420
~~~

Ngay cả job name, tenant ID, principal key và response metadata cũng nên được giới hạn theo chính sách bảo vệ thông tin nội bộ.

### 15.3. Không dùng ID Token cho job

Client Credentials Grant không phải OIDC End-User authentication. Job không nên cố lấy <code>OidcUser</code>, ID Token hoặc Session để chứng minh quyền service. Credential phải do Authorization Server cấp đúng cho Client Credentials và API đích.

### 15.4. Token audience và scope

Một access token hợp lệ từ Token Endpoint chưa chắc được Reports API chấp nhận:

- Audience có thể trỏ tới API khác.
- Scope thiếu <code>reports.read</code>.
- Resource Server có chính sách IP, tenant hoặc entitlement riêng.
- Token có thể hết hạn/bị thu hồi.

Job phải xử lý response 401/403 của API, không chỉ kiểm tra manager có trả token hay không.

## 16. Vận hành scheduler đáng tin cậy

### 16.1. Time zone và lịch

Ví dụ:

~~~java
@Scheduled(cron = "${app.reports-job.cron}", zone = "UTC")
public void run() { ... }
~~~

Chỉ định timezone giúp tránh lệch lịch do timezone của máy chạy. Nếu yêu cầu “02:15 theo giờ địa phương”, hãy sử dụng zone ID phù hợp trong thiết kế và lưu ý DST ở vùng có chuyển đổi giờ.

Với cron sáu trường, một biểu thức hợp lệ cần được kiểm tra theo tài liệu Spring, không sao chép trực tiếp Unix crontab năm trường mà không chuyển đổi.

### 16.2. Scheduling thread pool

Khi có nhiều job, cần cấu hình thread pool, task timeout và độ ưu tiên theo nhu cầu. Số thread không càng lớn càng tốt: nhiều job chạy đồng thời có thể làm tăng lượng token requests và lưu lượng API.

Không nên block tất cả job hạ tầng vì một API chậm. Thiết kế timeout cho HTTP client là yêu cầu quan trọng.

### 16.3. Không đặt network call trong transaction dài

Job nên tách phần gọi Token Endpoint/Resource Server khỏi transaction database kéo dài nếu không thật sự cần. Giữ transaction mở trong lúc chờ HTTP có thể làm tăng contention và gây deadlock.

Với workflow phức tạp, có thể dùng outbox, idempotent processing hoặc trạng thái job tường minh thay vì một transaction xuyên nhiều hệ thống.

### 16.4. Shutdown và restart

Nếu tiến trình restart giữa một lượt job, scheduled method có thể chưa hoàn tất. Khi lên lại:

- In-memory authorized client có thể đã mất, manager sẽ xin token mới khi cần.
- Persistent authorized client có thể được tái sử dụng nếu còn phù hợp.
- Kết quả nghiệp vụ của lượt chạy trước có thể đã ghi một phần.

Vì vậy cần **checkpoint/idempotency** cho nghiệp vụ. Token persistence không chứng minh job đã hoàn tất.

## 17. Phân biệt một số lựa chọn thiết kế

| Nhu cầu | Lựa chọn phù hợp | Điều cần tránh |
|---|---|---|
| Background job không có End-User | <code>AuthorizedClientServiceOAuth2AuthorizedClientManager</code> + <code>clientCredentials()</code> | Dùng user session/authorization code flow |
| Servlet web login OIDC | <code>oauth2Login()</code> với web security chain | Dùng service token như ID Token |
| API gọi thay mặt user đã đăng nhập | Authorized client của user, scope/audience hợp lệ | Dùng client credentials token để giả làm user |
| Lưu token across restarts | Persistent <code>OAuth2AuthorizedClientService</code> | Tin rằng in-memory tồn tại qua restart |
| Một job chạy một lần trong cluster | Distributed scheduler/lock | Tưởng <code>@Scheduled</code> tự phối hợp toàn cluster |
| Tránh token request quá nhiều | Principal ổn định, manager reuse, expiry policy | Principal ngẫu nhiên hoặc tự xin token mỗi lần |
| Quyền giữa các tenant khác nhau | ClientRegistration và principal namespace thích hợp | Chỉ đổi tên principal rồi giả định quyền đã tách |
| API trả 401 | Phân loại token/audience/expiry, cleanup có kiểm soát | Retry vô hạn với cùng token |

## 18. Lỗi thường gặp và cách chẩn đoán

| Hiện tượng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| <code>manager.authorize()</code> trả null | Registration/grant provider/context không phù hợp | Kiểm tra <code>registrationId</code>, grant type, provider list |
| <code>NoSuchBeanDefinitionException</code> cho <code>OAuth2AuthorizedClientService</code> | Chưa có OAuth2 Client auto-config/bean phù hợp | Kiểm tra dependency, registration, bean |
| Job báo thiếu HttpServletRequest | Inject nhầm web manager | Dùng <code>AuthorizedClientServiceOAuth2AuthorizedClientManager</code> |
| <code>invalid_client</code> | Client ID/secret hoặc auth method sai | Kiểm tra secret rotation, môi trường, token endpoint |
| <code>unauthorized_client</code> | Service chưa được phép dùng client credentials | Kiểm tra registration ở Authorization Server |
| <code>invalid_scope</code> | Scope job yêu cầu không được cấp | Điều chỉnh scope/permission |
| Job xin token mỗi lần chạy | Principal luôn đổi, storage không lưu, skew quá lớn hoặc token quá ngắn | Ổn định principal, kiểm tra service/success handler |
| Token bị mất sau restart | In-memory authorized client storage | Dùng persistence nếu thật sự cần |
| Hai node cùng chạy một job | <code>@Scheduled</code> chạy ở mỗi instance | Distributed scheduling/lock và idempotency |
| Resource Server trả 401 | Token hết hạn/revoked/sai audience | Kiểm tra audience, token validity, policy xử lý lỗi |
| Resource Server trả 403 | Thiếu scope/authorization | Kiểm tra quyền API, không chỉ đổi token |
| Token Endpoint bị rate limit | Token requests quá nhiều, instances tạo token đồng thời | Giảm cấp token, cache/storage, backoff |
| Bean manager không đúng | Có nhiều manager và thiếu <code>@Qualifier</code> | Đặt tên/inject rõ ràng |
| API timeout nhưng job vẫn được đánh dấu success | Business handling bỏ qua exception hoặc không xác minh kết quả | Tách rõ hoàn thành nghiệp vụ với việc có token |
| Lỗi quyền sau khi rotate secret | Deployment đang dùng secret cũ | Kiểm tra thời gian rotate và rollout |

### 18.1. Quy trình khoanh vùng

~~~text
Job có thực sự được @Scheduled kích hoạt?
    |
    v
Đúng OAuth2AuthorizedClientManager không phụ thuộc Servlet?
    |
    v
ClientRegistration ID tồn tại và grant = client_credentials?
    |
    v
OAuth2AuthorizedClientProvider có clientCredentials()?
    |
    v
Principal tổng hợp có ổn định?
    |
    v
OAuth2AuthorizedClientService có token còn dùng được?
    |
    +-- Có --> Sử dụng access token theo scope/audience
    |
    +-- Không --> Gọi Token Endpoint
                    |
                    v
              Client auth + scope được chấp nhận?
                    |
                    v
              Authorized client có được lưu?
                    |
                    v
              Resource Server chấp nhận token?
                    |
                    v
              Nghiệp vụ job có hoàn tất/idempotent?
~~~

## 19. Tình huống và bài tập thực hành

### Bài 1 — Chọn đúng manager

Một nhóm triển khai job đọc báo cáo hằng đêm. Họ dùng:

~~~java
DefaultOAuth2AuthorizedClientManager manager = ...;
~~~

nhưng job không có HTTP request.

**Câu hỏi:** Vì sao mô hình này không phù hợp? Nên chọn abstraction nào?

**Gợi ý đáp án:** Web manager dựa trên request context và <code>OAuth2AuthorizedClientRepository</code>. Scheduled service nên dùng <code>AuthorizedClientServiceOAuth2AuthorizedClientManager</code> cùng <code>OAuth2AuthorizedClientService</code>.

### Bài 2 — Principal không phải user

Code:

~~~java
OAuth2AuthorizeRequest.withClientRegistrationId("reports-job")
    .principal("reports-worker-runtime")
    .build();
~~~

**Câu hỏi:** Token có bắt buộc mang subject là <code>reports-worker-runtime</code> không?

**Đáp án:** Không. Đây là khóa principal để quản lý authorized client trong Spring Security. Subject/audience/scope của access token do Authorization Server xác định theo service ClientRegistration.

### Bài 3 — Không có refresh token

Token response client credentials chỉ có access token, token type và expiry. Code kiểm tra <code>getRefreshToken()==null</code>.

**Câu hỏi:** Đây có phải lỗi?

**Đáp án:** Thông thường không. Client Credentials Grant không cần refresh token để lấy token mới; provider <code>clientCredentials()</code> có thể xin access token mới khi cần.

### Bài 4 — Chạy đồng thời ở ba instance

Ứng dụng triển khai ba replica cùng bật <code>@Scheduled(cron="0 15 2 * * *")</code>.

**Câu hỏi:** Có thể xảy ra gì?

**Đáp án:** Cả ba replica có thể chạy job cùng lúc; token manager không giải quyết vấn đề này. Cần distributed scheduler/lock, workflow idempotent và chính sách concurrency độc lập với token storage.

### Bài 5 — Token sai API

Client được cấp token <code>reports.read</code> dành cho Reports API nhưng job gửi token sang Billing API.

**Câu hỏi:** Vì sao manager không bảo đảm việc gọi thành công?

**Đáp án:** Manager chỉ nhận token trong phạm vi grant/registration. Resource Server vẫn kiểm tra issuer, audience, scope và authorization. Phải dùng đúng ClientRegistration/token dành cho Billing API.

### Bài 6 — Xin token mỗi lần chạy

Lần nào job cũng tạo:

~~~java
.principal(java.util.UUID.randomUUID().toString())
~~~

**Câu hỏi:** Điều gì có thể xảy ra?

**Đáp án:** Mỗi principal mới khiến storage không tìm được authorized client đã lưu dưới principal cũ; token request tăng và có thể bị rate limit. Dùng principal ổn định theo workload/tenant.

### Bài 7 — Xử lý 401 từ API

Job lấy authorized client thành công nhưng API trả HTTP 401.

**Câu hỏi:** Có nên cứ gọi <code>manager.authorize()</code> trong vòng lặp đến khi API nhận token?

**Đáp án:** Không. Có thể token sai audience hoặc manager trả lại token cũ chưa gần expiry. Cần phân loại lỗi, kiểm tra registration/scope, dùng failure handling/cleanup có kiểm soát và bounded retry khi thực sự có khả năng hồi phục.

### Bài 8 — Thiết kế một job hoàn chỉnh

Hãy phác thảo:

1. ClientRegistration <code>inventory-sync</code> với <code>authorization-grant-type=client_credentials</code> và scope chỉ đọc.
2. Manager không phụ thuộc Servlet, chứa provider <code>clientCredentials()</code>.
3. <code>OAuth2AuthorizeRequest</code> dùng principal tổng hợp ổn định.
4. HTTP client gọi Inventory API bằng Bearer access token.
5. Timeout và cơ chế ghi nhận job success/failure.
6. Chính sách không chạy trùng trên nhiều replica và xử lý idempotent.
7. Log không chứa token, secret hoặc raw nội dung API.

## 20. Ghi nhớ

- **<code>AuthorizedClientServiceOAuth2AuthorizedClientManager</code>** phù hợp job, scheduler và service không có <code>HttpServletRequest</code>.
- Kết hợp **<code>ClientRegistrationRepository</code>**, **<code>OAuth2AuthorizedClientService</code>** và **<code>OAuth2AuthorizedClientProviderBuilder.builder().clientCredentials()</code>** để xử lý Client Credentials Grant.
- Job gọi <code>manager.authorize(OAuth2AuthorizeRequest)</code> với **registration ID đúng** và **principal tổng hợp ổn định**. Principal này là khóa lưu token, không phải danh tính End-User trong token.
- Manager có thể **tái sử dụng access token còn hiệu lực** và **xin token mới khi cần**; client credentials thông thường không cần refresh token.
- <code>@Scheduled</code> không tự điều phối cluster. Cần tách bài toán **một job chạy một lần**, **token storage**, **HTTP retry** và **idempotency nghiệp vụ**.
- Access token chỉ được gửi tới Resource Server đúng audience/scope; lỗi 401/403 không tự động được giải quyết bằng xin token liên tục.
- Bảo vệ client secret/token, dùng TLS, giới hạn retry, chú ý clock skew và không đưa token/credential vào log.
- Khi ứng dụng vừa có web login vừa có background job, ưu tiên **manager đúng ngữ cảnh** và cấu hình riêng cho user token/service token để tránh lẫn quyền.

### Tài liệu tham khảo

- **Spring Security Reference — OAuth2 Client:** Authorized Client Manager, Authorized Client Provider, Client Credentials Grant và Authorized Client Service.
- **Spring Security Java API — AuthorizedClientServiceOAuth2AuthorizedClientManager:** constructor, provider, success/failure handler và cơ chế storage.
- **Spring Security Java API — OAuth2AuthorizedClientProviderBuilder:** <code>clientCredentials()</code>, clock skew và khả năng cấu hình grant.
- **Spring Security Java API — OAuth2AuthorizeRequest, OAuth2AuthorizedClient và OAuth2AuthorizedClientService:** mối liên kết registration/principal/token và vòng đời lưu trữ.
- **Spring Framework Reference — Task Execution and Scheduling:** <code>@EnableScheduling</code>, <code>@Scheduled</code>, cron expression và scheduling thread pool.
- **RFC 6749 — The OAuth 2.0 Authorization Framework, Section 4.4:** Client Credentials Grant và Token Endpoint.
- **RFC 6750 — OAuth 2.0 Bearer Token Usage:** cách sử dụng Bearer access token tại Resource Server.
- **RFC 7009 — OAuth 2.0 Token Revocation:** hành vi thu hồi token khi Authorization Server hỗ trợ.
