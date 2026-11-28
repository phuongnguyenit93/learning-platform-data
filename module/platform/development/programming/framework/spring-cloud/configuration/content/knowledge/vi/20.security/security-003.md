# Phân quyền đọc cấu hình theo ứng dụng và môi trường

Config Server tập trung cấu hình cho nhiều ứng dụng Spring Boot. Điều đó cũng có nghĩa một endpoint có thể trả về thông tin của nhiều dịch vụ và nhiều môi trường. Nếu mọi client dùng chung một tài khoản có quyền đọc toàn bộ repository, một dịch vụ có thể đọc nhầm hoặc cố ý truy vấn cấu hình của dịch vụ khác, kể cả các giá trị nhạy cảm dành cho production.

Vì vậy, bảo vệ Config Server cần hai lớp: **xác thực** để biết ai đang gọi và **phân quyền** để quyết định danh tính đó được đọc application, profile và label nào. Chính sách phải áp dụng ở phía server cho mọi request, không dựa vào việc client tự khai báo tên ứng dụng một cách trung thực.

## 1. Phạm vi cần bảo vệ

Config Server thường cung cấp cấu hình theo ba selector:

- **Application:** tên ứng dụng, thường là `spring.application.name`, ví dụ `orders-service` hoặc `inventory-service`.
- **Profile:** môi trường hoặc nhóm cấu hình, ví dụ `dev`, `test`, `staging`, `prod`.
- **Label:** phiên bản nguồn cấu hình, thường là branch, tag hoặc commit khi dùng Git.

Endpoint Environment phổ biến có dạng:

```text
/{application}/{profile}
/{application}/{profile}/{label}
```

Ví dụ:

```text
/orders-service/dev/main
/orders-service/prod/release-2026.11
```

Một client có quyền đọc `orders-service/dev` không nên mặc nhiên được đọc `orders-service/prod`, và client của `orders-service` cũng không nên mặc nhiên được đọc `payment-service`. Quyền nên được cấp theo danh tính service, application và môi trường cụ thể.

## 2. Xác thực khác phân quyền

**Xác thực (authentication)** trả lời câu hỏi “request đến từ ai?”. Config Server có thể xác thực bằng HTTP Basic, OAuth 2.0 bearer token/JWT, mTLS tại gateway hoặc cơ chế identity của nền tảng.

**Phân quyền (authorization)** trả lời câu hỏi “danh tính đó được phép làm gì?”. Sau khi xác thực, server cần kiểm tra quyền đọc application/profile/label trong URL trước khi trả cấu hình.

| Lớp | Ví dụ | Kết quả cần có |
|---|---|---|
| Xác thực | Service account `orders-service`, JWT có subject của workload hoặc client certificate. | Xác định được danh tính ổn định của caller. |
| Phân quyền theo application | `orders-service` chỉ đọc `orders-service`. | Không đọc được cấu hình `inventory-service` hay `payment-service`. |
| Phân quyền theo môi trường | Workload dev chỉ đọc `dev`; workload production có quyền đọc `prod`. | Không nâng quyền bằng cách sửa profile trong URL. |
| Phân quyền theo label | Chỉ release agent được đọc tag phát hành hoặc label được phê duyệt. | Giới hạn truy cập các phiên bản cấu hình đặc biệt. |

Một username/password hợp lệ chỉ chứng minh caller có danh tính đã được cấp. Nếu mọi service dùng chung một tài khoản có quyền đọc tất cả application, hệ thống vẫn thiếu phân quyền theo application.

## 3. Thiết kế ma trận quyền

Trước khi cấu hình Spring Security, hãy xác định ma trận quyền ở mức nghiệp vụ. Ví dụ:

| Danh tính | Application | Profile | Quyền |
|---|---|---|---|
| `orders-dev` | `orders-service` | `dev`, `test` | Đọc |
| `orders-prod` | `orders-service` | `prod` | Đọc |
| `inventory-runtime` | `inventory-service` | `dev`, `test`, `prod` | Đọc theo phạm vi workload được cấp |
| `release-operator` | Các application trong đợt phát hành | Profile được phê duyệt | Đọc và kiểm tra phiên bản |
| `config-admin` | Tất cả application | Tất cả profile/label | Quyền quản trị được kiểm soát riêng |

Ma trận là đầu vào của authorization policy. Có thể biểu diễn quyền bằng role, authority, OAuth scope, claim trong JWT hoặc policy lưu ở một dịch vụ quản trị. Ví dụ các authority:

- `CONFIG_APP_ORDERS_READ`
- `CONFIG_APP_INVENTORY_READ`
- `CONFIG_ENV_DEV_READ`
- `CONFIG_ENV_PROD_READ`
- `CONFIG_LABEL_RELEASE_READ`

Trong hệ thống lớn, tránh tạo role cho mọi tổ hợp application/profile nếu số lượng tăng nhanh. Có thể dùng policy dạng dữ liệu với các trường `subject`, `applications`, `profiles` và `labels`, sau đó viết một authorization component đánh giá từng request.

## 4. Bật Spring Security trên Config Server

Thêm Spring Security vào Config Server để bảo vệ các endpoint. Ví dụ Gradle:

```gradle
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'
}
```

Nếu hệ thống dùng JWT từ identity provider, có thể cấu hình resource server:

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://identity.example.internal/issuer
```

Config Server xác minh chữ ký và các claim theo cấu hình issuer/JWK. Việc xác thực token thành công vẫn chưa quyết định application/profile nào được đọc; authorization policy cần kiểm tra tiếp các selector trong request.

Với hệ thống nội bộ nhỏ, HTTP Basic có thể dùng làm ví dụ hoặc giải pháp tạm thời khi kết hợp TLS và credential riêng cho từng workload. Không nên dựa vào một tài khoản mặc định dùng chung cho toàn bộ client. Nếu Spring Security tự tạo user/password khi khởi động, đó không phải mô hình phân quyền production theo application và môi trường.

## 5. Phân quyền dựa trên application và profile trong URL

Config Server nhận application và profile từ URL. Một authorization manager có thể lấy các path variable từ request matcher rồi đối chiếu với quyền của caller.

Ví dụ cấu hình Spring Security 6 dùng `MvcRequestMatcher` cho hai dạng Environment endpoint:

```java
@Configuration
@EnableWebSecurity
public class ConfigServerSecurity {

    @Bean
    SecurityFilterChain configServerFilterChain(
            HttpSecurity http,
            HandlerMappingIntrospector introspector,
            ConfigReadPolicy configReadPolicy) throws Exception {

        MvcRequestMatcher.Builder mvc =
            new MvcRequestMatcher.Builder(introspector);

        AuthorizationManager<RequestAuthorizationContext> readConfig =
            (authentication, context) -> {
                String application =
                    context.getVariables().get("application");
                String profile =
                    context.getVariables().get("profile");

                boolean allowed = configReadPolicy.canRead(
                    authentication.get(), application, profile);

                return new AuthorizationDecision(allowed);
            };

        http.authorizeHttpRequests(authorize -> authorize
            .requestMatchers(mvc.pattern(HttpMethod.GET, "/actuator/health"))
                .permitAll()
            .requestMatchers(
                mvc.pattern(HttpMethod.GET, "/{application}/{profile}"),
                mvc.pattern(HttpMethod.GET, "/{application}/{profile}/{label}"))
                .access(readConfig)
            .anyRequest().denyAll()
        );

        http.oauth2ResourceServer(oauth2 -> oauth2.jwt());
        return http.build();
    }
}
```

`ConfigReadPolicy` là thành phần do ứng dụng triển khai để kiểm tra danh tính và ma trận quyền. Đoạn code minh họa hai dạng JSON Environment endpoint; các endpoint YAML/properties hoặc route tùy chỉnh phải được thêm matcher và áp dụng cùng chính sách nếu hệ thống có bật chúng. `anyRequest().denyAll()` giúp các route chưa được khai báo bị từ chối.

Ví dụ policy ở mức khái niệm:

```java
public boolean canRead(
        Authentication authentication,
        String application,
        String profile) {

    if (application == null || profile == null) {
        return false;
    }

    if (application.contains("*") || profile.contains("*")) {
        return false;
    }

    return accessPolicy.isAllowed(
        authentication.getName(), application, profile);
}
```

Trong triển khai thực tế, cần chuẩn hóa profile list, kiểm tra label nếu có chính sách theo label, và xử lý alias/encoding/path traversal an toàn. Không lấy `spring.application.name` do client gửi làm bằng chứng về danh tính; danh tính phải đến từ token, certificate hoặc credential đã xác thực.

## 6. Kiểm soát profile production

Profile là ranh giới quan trọng vì file `prod` thường chứa endpoint, thông tin tích hợp và tham số vận hành nhạy cảm hơn `dev`. Không nên cho phép mọi service account đọc mọi profile chỉ vì chúng cùng thuộc một application.

Ví dụ policy:

```text
orders-dev:
  application: orders-service
  profiles: [dev, test]

orders-prod:
  application: orders-service
  profiles: [prod]

inventory-runtime:
  application: inventory-service
  profiles: [prod]
```

Nếu client gửi nhiều profile, chẳng hạn `prod,region-apac`, policy cần xác định cách xử lý rõ ràng. Một lựa chọn an toàn là chỉ cho phép request khi mọi profile trong danh sách đều nằm trong tập profile được cấp. Không chỉ kiểm tra chuỗi có chứa `prod` hoặc `dev`, vì cách so khớp chuỗi đơn giản có thể tạo lỗ hổng như profile giả mạo hoặc profile ghép.

Profile không phải cơ chế xác thực môi trường. Một workload dev có thể sửa URL thành `/orders-service/prod` nếu server không kiểm tra quyền. Server phải dựa trên danh tính workload đã xác thực để quyết định profile được phép.

## 7. Bảo vệ cấu hình dùng chung và wildcard

Config Server có thể kết hợp file dùng chung như `application.yml` với file riêng như `orders-service.yml`. Khi client yêu cầu cấu hình cho `orders-service`, response có thể bao gồm cả property source chung và riêng. Vì vậy, quyền đọc application cần tính đến tất cả nguồn cấu hình sẽ được trả về trong request đó.

Đặc biệt cần kiểm soát:

- Request trực tiếp đến application dùng chung như `application`.
- Application wildcard hoặc selector bao trùm nhiều dịch vụ.
- Profile list chứa cả profile được phép và không được phép.
- Label wildcard hoặc label trỏ tới nhánh thử nghiệm ngoài chính sách.
- Endpoint YAML/properties hoặc endpoint tương thích khác có thể truy cập cùng dữ liệu.

Không cấp quyền đọc `application` hoặc wildcard cho service account thông thường chỉ để lấy vài giá trị dùng chung. Client của một ứng dụng nên truy vấn đúng application của nó; Config Server tự kết hợp property source chung theo cơ chế repository.

Nếu một nhóm vận hành cần đọc cấu hình chung, cấp quyền riêng có phạm vi và audit rõ ràng. Mọi endpoint biểu diễn cùng dữ liệu đều phải đi qua cùng authorization policy; bảo vệ JSON endpoint nhưng bỏ quên YAML endpoint sẽ tạo đường vòng.

## 8. Phân quyền label và phiên bản cấu hình

Label thường là branch, tag hoặc commit trong Git backend. Trong một số tổ chức, nhánh `main` dùng cho môi trường phát triển, còn tag phát hành được phê duyệt dùng cho production.

Policy có thể bổ sung quy tắc:

| Caller | Application | Profile | Label |
|---|---|---|---|
| Developer | Ứng dụng thuộc nhóm | `dev`, `test` | `main`, branch feature được phép |
| Runtime production | Ứng dụng được cấp | `prod` | Tag/release label đã phê duyệt |
| Release operator | Ứng dụng trong release | Profile được phê duyệt | Tag hoặc commit được chỉ định |

Nếu không có label trong URL, Config Server có thể sử dụng default label. Authorization policy cần xử lý trường hợp này theo cùng quy tắc, không được xem thiếu label là tự động an toàn. Có thể chuẩn hóa label mặc định trước khi đánh giá hoặc giới hạn client production vào một endpoint/release policy riêng.

Với Native backend, label có thể chỉ tham gia tạo đường dẫn nếu `search-locations` dùng placeholder `{label}`; nó không tự mang ý nghĩa commit như Git. Policy cần biết backend đang dùng để không áp dụng giả định sai về version.

## 9. Xác thực client bằng service identity

Mỗi ứng dụng nên có danh tính riêng khi truy cập Config Server. Một số mô hình:

- OAuth 2.0 client credentials: mỗi workload có client identity và nhận access token với scope phù hợp.
- mTLS: workload dùng client certificate; gateway hoặc Config Server xác minh certificate và ánh xạ sang principal/authority.
- HTTP Basic: mỗi ứng dụng dùng credential riêng, lưu trong secret manager và chỉ truyền qua TLS.
- Workload identity của nền tảng: dùng identity gắn với pod, VM hoặc service account để cấp token ngắn hạn.

Tránh dùng chung một username/password cho tất cả Config Client. Khi một credential bị lộ, tài khoản riêng giúp thu hồi đúng ứng dụng và giảm phạm vi ảnh hưởng.

Với HTTP Basic trong bootstrap cũ, credential có thể được khai báo bằng thuộc tính `spring.cloud.config.username` và `spring.cloud.config.password`. Giá trị phải đến từ secret store hoặc biến môi trường; không commit vào Git. Với Config Data API, cấu hình credential theo cơ chế được hỗ trợ bởi phiên bản Spring Cloud Config đang dùng.

Token nên có thời hạn phù hợp, audience dành cho Config Server và scope chỉ đọc cấu hình. Không dùng token quản trị có quyền gọi `/encrypt`, `/decrypt`, `/monitor` hoặc Actuator cho runtime client thông thường.

## 10. Tách quyền đọc cấu hình khỏi quyền quản trị

Config Server có nhiều nhóm endpoint với mức độ nhạy cảm khác nhau:

| Endpoint | Mục đích | Nhóm quyền nên có |
|---|---|---|
| `/{application}/{profile}[/{label}]` | Đọc Environment của ứng dụng | Config reader theo application/profile |
| `/{application}-{profile}.yml` hoặc `.properties` | Đọc cấu hình dạng file | Cùng policy với Environment endpoint |
| `/encrypt` | Mã hóa giá trị | Secret/configuration operator được ủy quyền |
| `/decrypt` | Giải mã và trả plaintext | Nhóm quyền rất hạn chế, thường chỉ security/config admin |
| `/monitor` | Nhận webhook thay đổi repository | Webhook identity đã xác minh hoặc gateway chuyên dụng |
| `/actuator/health` | Kiểm tra sức khỏe | Monitoring hoặc truy cập nội bộ theo chính sách |
| Các Actuator endpoint quản trị | Quản lý và chẩn đoán server | Operator/admin riêng biệt |

Không cho phép mọi Config Client gọi tất cả endpoint chỉ vì chúng cần đọc cấu hình. Đặc biệt, `/decrypt` có thể trả plaintext và `/monitor` có thể kích hoạt refresh. Các endpoint này cần authorization riêng, audit và giới hạn mạng.

## 11. Cấu hình client và quyền tối thiểu

Client chỉ cần quyền đọc đúng application/profile/label của nó. Ví dụ client `orders-service`:

```yaml
spring:
  application:
    name: orders-service
  config:
    import: "configserver:https://config.example.internal"
```

Tên application trong request giúp Config Server tìm đúng tài liệu; nó không tự cấp quyền. Server xác minh token/certificate trước, sau đó so sánh principal với `orders-service` và profile đang yêu cầu.

Một service account không nên có quyền đọc tất cả ứng dụng chỉ vì cần một thuộc tính dùng chung. Nếu `orders-service` cần cấu hình chung, Config Server sẽ kết hợp `application.yml` vào response theo repository rules. Nếu ứng dụng cần đọc trực tiếp cấu hình của `application` hoặc dịch vụ khác, phải có lý do và quyền riêng được phê duyệt.

## 12. Kiểm thử authorization

Trước khi triển khai production, kiểm thử cả trường hợp được phép và bị từ chối. Ma trận kiểm thử tối thiểu:

| Danh tính | Request | Kết quả mong đợi |
|---|---|---|
| `orders-dev` | `/orders-service/dev/main` | Cho phép |
| `orders-dev` | `/orders-service/prod/main` | Từ chối |
| `orders-dev` | `/payment-service/dev/main` | Từ chối |
| `orders-prod` | `/orders-service/prod/release-2026.11` | Cho phép nếu label nằm trong policy |
| `orders-prod` | `/orders-service/dev/main` | Từ chối nếu không được cấp profile dev |
| `orders-dev` | `/application/prod/main` | Từ chối nếu không có quyền đọc cấu hình chung trực tiếp |
| Anonymous | `/orders-service/dev/main` | Từ chối hoặc yêu cầu xác thực |
| Config Client | `/decrypt` | Từ chối |

Kiểm tra thêm:

- Request không có label và request dùng default label.
- Profile list có nhiều giá trị, trong đó có profile không được cấp.
- Các dạng JSON, YAML và properties nếu server bật nhiều endpoint.
- URL encoding, dấu gạch nối, dấu chấm và ký tự đặc biệt trong selector.
- Tài khoản bị thu hồi hoặc token hết hạn.
- Policy không tìm thấy application/profile phải mặc định từ chối.

Không chỉ kiểm thử HTTP `401` và `403`; cần xác minh response không chứa property source hoặc dữ liệu nhạy cảm khi request bị từ chối.

## 13. Audit và vận hành quyền truy cập

Phân quyền cần được duy trì như một phần của vòng đời ứng dụng:

1. Cấp service identity riêng khi triển khai ứng dụng.
2. Gán application/profile/label theo nguyên tắc least privilege.
3. Review quyền production và quyền đọc cấu hình nhạy cảm bởi người có thẩm quyền.
4. Ghi log principal, application, profile, label, thời điểm và kết quả authorization.
5. Không ghi token, password, plaintext hoặc toàn bộ response cấu hình vào log.
6. Theo dõi request bị từ chối bất thường và các lần truy cập application ngoài phạm vi.
7. Thu hồi credential khi workload bị xóa, thay thế hoặc có dấu hiệu bị xâm nhập.
8. Định kỳ rà soát quyền còn hiệu lực và loại bỏ quyền không còn cần thiết.

Với hệ thống nhiều tenant hoặc nhiều nhóm phát triển, nên quản lý policy ở một nguồn có versioning và quy trình review. Thay đổi quyền production cần có audit trail tương tự thay đổi cấu hình nghiệp vụ.

## 14. Lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| Client đọc được cấu hình của ứng dụng khác | Dùng chung credential hoặc chỉ xác thực mà chưa phân quyền theo path. | Dùng service identity riêng và authorization theo application. |
| Dev đọc được profile prod | Policy chỉ kiểm tra application, bỏ qua profile. | Kiểm tra đồng thời application và mọi profile trong request. |
| JSON bị chặn nhưng YAML vẫn đọc được | Chưa áp dụng policy cho tất cả endpoint biểu diễn cấu hình. | Bổ sung matcher cho YAML/properties và route tương đương. |
| Request `application` trả cấu hình dùng chung cho service thường | Cho phép truy cập trực tiếp wildcard/shared application. | Từ chối selector rộng; cấp quyền đọc chung riêng khi thực sự cần. |
| Client hợp lệ nhận `403` | Authority/claim không được ánh xạ đúng hoặc policy không nhận diện application/profile. | Kiểm tra token claims, role mapping và policy evaluation log. |
| Client nhận `401` | Token/credential thiếu, hết hạn hoặc không hợp lệ. | Kiểm tra issuer, audience, chữ ký, credential và TLS. |
| Quyền mới chưa có hiệu lực | Policy cache hoặc token cũ vẫn còn hiệu lực. | Xác định TTL/cache invalidation và thu hồi token/credential theo quy trình. |

## 15. Tổng kết

- Config Server cần xác thực caller và phân quyền theo application, profile, label; xác thực thành công không đồng nghĩa được đọc mọi cấu hình.
- Dùng service identity riêng cho từng workload và áp dụng least privilege.
- Policy phải kiểm tra selector trong URL ở phía server; không tin tên application do client tự khai báo.
- Phân biệt quyền dev/test với production và xác định cách xử lý profile list, default label và wildcard.
- Bảo vệ mọi endpoint JSON, YAML và properties; tránh đường vòng qua `/application` hoặc selector rộng.
- Tách quyền đọc cấu hình khỏi quyền `/encrypt`, `/decrypt`, `/monitor` và Actuator quản trị.
- Kiểm thử cả request được phép và bị từ chối, đồng thời xác minh response lỗi không làm lộ dữ liệu.
- Audit quyền, thu hồi credential và rà soát policy định kỳ để duy trì bảo mật khi hệ thống phát triển.
