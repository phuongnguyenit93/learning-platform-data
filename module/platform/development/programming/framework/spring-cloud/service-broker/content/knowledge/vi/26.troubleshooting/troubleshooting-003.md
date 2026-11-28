# Yêu cầu bị từ chối do phiên bản giao thức, xác thực hoặc phân quyền

## Mục tiêu và bối cảnh

Khi Cloud Foundry hoặc một platform khác gọi Spring Cloud Service Broker, request có thể bị từ chối trước khi nghiệp vụ provision, update, bind hoặc deprovision được thực thi. Ba nguyên nhân thường gặp là platform gửi phiên bản Open Service Broker API (OSB API) mà broker không hỗ trợ, credentials giữa platform và broker không hợp lệ, hoặc caller đã được xác thực nhưng không có quyền trên tài nguyên.

Các nguyên nhân này có biểu hiện khác nhau và cần cách chẩn đoán riêng:

- **Phiên bản giao thức không được hỗ trợ:** broker không thể xử lý request theo phiên bản OSB API mà platform khai báo. Với phiên bản được khai báo nhưng không được hỗ trợ, broker trả HTTP 412 Precondition Failed.
- **Lỗi xác thực:** broker không xác minh được credentials của platform. Response thường là HTTP 401 Unauthorized.
- **Lỗi phân quyền:** broker xác minh được caller nhưng caller không được phép thực hiện hành động hoặc truy cập tenant/resource đó. Response thường là HTTP 403 Forbidden; có thể dùng 404 theo chính sách che giấu sự tồn tại của resource.

Một lỗi kết nối TLS, route sai hoặc provider từ chối credentials của chính broker cũng có thể khiến thao tác thất bại, nhưng đó không phải cùng một loại lỗi với platform bị broker từ chối. Bài học này giúp phân biệt các lớp đó để tìm đúng điểm cần sửa.

Sau bài học, bạn có thể:

- Chẩn đoán lỗi X-Broker-API-Version và HTTP 412.
- Phân biệt HTTP 401, 403 và 404 theo nguyên nhân.
- Kiểm tra credentials Cloud Foundry dùng để gọi broker.
- Xác minh ownership và quyền trên service instance/binding.
- Nhận diện lỗi do reverse proxy, TLS, route hoặc provider credentials.
- Cấu hình exception handling trong Spring Security/WebFlux.
- Kiểm thử response OSB API và bảo đảm request bị từ chối không tạo side effect.

## 1. Xác định request bị từ chối ở tầng nào

Không bắt đầu bằng việc thay đổi credentials hoặc sửa logic provision ngay khi thấy một request thất bại. Trước tiên hãy xác định request đã tới broker chưa và broker từ chối ở lớp nào.

~~~mermaid
flowchart TD
    A[Platform gửi request] --> B{TLS / DNS / Route thành công?}
    B -->|Không| NET[Lỗi kết nối, TLS hoặc routing]
    B -->|Có| C{OSB API version được hỗ trợ?}
    C -->|Không| V412[412 Precondition Failed]
    C -->|Có| D{Authentication thành công?}
    D -->|Không| A401[401 Unauthorized]
    D -->|Có| E{Authorization thành công?}
    E -->|Không| A403[403 hoặc 404 theo policy]
    E -->|Có| F[Validate nghiệp vụ và thực thi]
    F --> G{Provider thành công?}
    G -->|Không| PERR[Lỗi dependency / operation]
    G -->|Có| OK[Trả kết quả OSB API]
~~~

Thứ tự thực thi cụ thể phụ thuộc cách broker và framework tổ chức filter, nhưng các câu hỏi chẩn đoán vẫn có giá trị. Ví dụ, nếu TLS handshake thất bại thì broker chưa thể trả HTTP 401 hoặc 412 vì request chưa đi tới tầng HTTP của ứng dụng.

Hãy thu thập các thông tin sau trước khi thay đổi cấu hình:

- Timestamp và correlation/trace ID.
- HTTP method, path và status code.
- Giá trị X-Broker-API-Version nhận được, nếu có.
- Caller/platform registration đang sử dụng.
- Response body đã được che thông tin nhạy cảm.
- Log security filter và application service.
- Việc request có tới provider hay chưa.

Không ghi Authorization header hoặc password vào log để phục vụ chẩn đoán.

## 2. Lỗi phiên bản OSB API: X-Broker-API-Version và HTTP 412

Platform gửi header X-Broker-API-Version để cho broker biết phiên bản OSB API được dùng cho request. Broker phải kiểm tra phiên bản này theo phạm vi phiên bản mà implementation hỗ trợ.

Ví dụ request:

~~~http
GET /v2/catalog HTTP/1.1
Host: broker.example.com
Authorization: Basic <platform-credentials>
X-Broker-API-Version: <major>.<minor>
Accept: application/json
~~~

Nếu platform khai báo một phiên bản mà broker không hỗ trợ, broker trả HTTP 412 Precondition Failed. Đây là lỗi tương thích giao thức, không phải lỗi username/password và cũng không phải lỗi service plan.

### 2.1. Dấu hiệu của lỗi version mismatch

Các dấu hiệu thường gặp:

- Catalog call bị từ chối ngay cả khi credentials đã được xác minh.
- Response status là 412.
- Error body có description nói phiên bản API không được hỗ trợ.
- Log ghi nhận version header nằm ngoài supported range.
- Các thao tác lifecycle cũng bị từ chối trước khi vào handler nghiệp vụ.

Response minh họa:

~~~http
HTTP/1.1 412 Precondition Failed
Content-Type: application/json
~~~

~~~json
{
  "description": "The requested Open Service Broker API version is not supported by this broker."
}
~~~

OSB error body dùng trường description để giải thích lỗi. Không đưa danh sách dependency, stack trace hoặc thông tin nội bộ vào response.

### 2.2. Kiểm tra giá trị header

Khi điều tra version mismatch:

1. Xác nhận platform thực sự gửi X-Broker-API-Version.
2. Ghi lại giá trị header mà ứng dụng nhận được sau reverse proxy.
3. Kiểm tra broker khai báo các phiên bản được hỗ trợ.
4. Kiểm tra logic parse major/minor version.
5. Xác nhận framework adapter không vô tình loại bỏ hoặc thay đổi header.
6. So sánh phiên bản platform gửi với phiên bản broker triển khai.
7. Chạy contract test cho các phiên bản nằm trong supported range.

Không so sánh version bằng chuỗi đơn giản. Ví dụ so sánh từ điển có thể xếp "2.9" lớn hơn "2.10" dù thứ tự phiên bản thực tế ngược lại. Hãy parse thành các thành phần số theo định dạng phiên bản mà OSB API quy định.

### 2.3. Thiết kế supported range rõ ràng

Broker nên có chính sách phiên bản được hỗ trợ có thể kiểm tra và kiểm thử. Ví dụ minh họa:

~~~java
public record ApiVersion(int major, int minor) {}

public boolean supports(ApiVersion requested) {
    ApiVersion minimum = new ApiVersion(2, 14);
    ApiVersion maximum = new ApiVersion(2, 17);

    return requested.major() == 2
            && requested.minor() >= minimum.minor()
            && requested.minor() <= maximum.minor();
}
~~~

Các con số trong ví dụ chỉ minh họa cách biểu diễn range; hãy thay bằng các phiên bản mà broker thực sự triển khai và đã kiểm thử. Nếu broker hỗ trợ nhiều major version, policy cần mô tả riêng compatibility của từng major.

Không chỉ tăng maximum version trong cấu hình để làm request qua được. Broker phải thực sự hiểu các semantics mới, field mới và quy tắc response của phiên bản đó.

### 2.4. Khi header bị thiếu hoặc bị proxy làm mất

OSB API platform request có header phiên bản. Nếu broker không nhận được header, hãy xác định request bị thiếu từ client hay bị loại bỏ trên đường truyền:

- Kiểm tra request log ở ingress/reverse proxy.
- Kiểm tra cấu hình forward header.
- Kiểm tra middleware hoặc gateway có allowlist header hay không.
- So sánh request từ platform với request kiểm thử trực tiếp.

Không tự động gán một phiên bản mới nhất khi header bị thiếu. Cách xử lý cần tuân theo hợp đồng OSB API và policy của broker. Phân biệt rõ trường hợp header vắng mặt với trường hợp header có giá trị nhưng phiên bản không được hỗ trợ.

### 2.5. Không nhầm API version với service plan version

X-Broker-API-Version là phiên bản giao thức giữa platform và broker. Nó không phải:

- Phiên bản Spring Boot.
- Phiên bản Spring Cloud Open Service Broker dependency.
- Version của service offering.
- Version của service plan.
- Version schema parameters của một sản phẩm database.

Khi response 412 xuất hiện, hãy kiểm tra protocol header trước. Đổi plan hoặc đổi service offering không giải quyết được lỗi version mismatch.

## 3. Lỗi xác thực: HTTP 401 Unauthorized

Authentication xác minh platform/caller có đúng credentials để gọi broker hay không. Trong nhiều triển khai Cloud Foundry, administrator đăng ký broker cùng username và password. Cloud Controller dùng thông tin đó khi gửi request tới endpoint broker.

Ví dụ lệnh đăng ký:

~~~bash
cf create-service-broker spring-cloud-broker broker-cf-user "<broker-password>" https://broker.example.com
~~~

Nếu broker dùng HTTP Basic, credentials được gửi trong Authorization header. Khi broker không xác minh được credentials, response thường là HTTP 401 Unauthorized.

### 3.1. Dấu hiệu của lỗi 401

- Broker log cho thấy thiếu Authorization header.
- Username không tồn tại hoặc password không khớp.
- Password đã rotate ở broker nhưng chưa cập nhật trong Cloud Controller.
- Broker đọc nhầm environment variable hoặc secret.
- Reverse proxy loại bỏ Authorization header.
- Security filter đang dùng một authentication provider khác với cấu hình mong đợi.

Response minh họa:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Basic realm="service-broker"
Content-Type: application/json
~~~

~~~json
{
  "description": "Authentication credentials are missing or invalid."
}
~~~

Không phân biệt password nào sai trong response công khai. Không tiết lộ username có tồn tại hay không, giá trị hash hoặc cấu hình identity provider.

### 3.2. Phân biệt credentials platform-to-broker và broker-to-provider

Đây là điểm thường gây nhầm lẫn:

| Credentials | Dùng để làm gì? | Khi sai |
|---|---|---|
| Cloud Controller → Broker | Xác thực platform khi gọi OSB API | Broker trả 401 cho request platform |
| Broker → Cloud Provider | Broker xác thực khi gọi API provider | Provider trả 401/403 cho broker |
| Workload → Service | Ứng dụng dùng binding credentials truy cập database/queue | Backend từ chối workload |

Nếu provider từ chối API token của broker, caller platform vẫn có thể đã xác thực thành công với broker. Không chuyển lỗi provider thành 401 của OSB request một cách máy móc. Hãy ghi nhận dependency failure, sửa provider credentials và cập nhật operation theo mô hình đồng bộ/bất đồng bộ.

### 3.3. Kiểm tra Cloud Foundry broker registration

Dùng CLI với tài khoản quản trị phù hợp:

~~~bash
cf service-brokers
~~~

Xác nhận đúng broker registration và endpoint. Nếu credentials đã thay đổi, cập nhật registration:

~~~bash
cf update-service-broker spring-cloud-broker broker-cf-user "<new-broker-password>" https://broker.example.com
~~~

Kiểm tra kỹ tên broker và foundation đang target. Không nhầm credentials đăng nhập CLI của operator với credentials mà Cloud Controller dùng để gọi broker.

Quy trình kiểm tra:

1. Xác nhận broker app đang chạy.
2. Xác nhận security configuration đọc đúng secret.
3. Gọi catalog trực tiếp bằng credentials đã cấp.
4. Xác nhận Cloud Controller đang giữ cùng username/password.
5. Cập nhật registration nếu có chênh lệch.
6. Gọi lại catalog và kiểm tra log security.

Ví dụ kiểm tra endpoint trực tiếp:

~~~bash
curl -i \
  --user "$BROKER_USER:$BROKER_PASSWORD" \
  -H "X-Broker-API-Version: $OSB_API_VERSION" \
  -H "Accept: application/json" \
  "$BROKER_URL/v2/catalog"
~~~

Dùng credentials giả trong tài liệu và môi trường test. Tránh lưu password thật vào shell history, CI output hoặc command log dùng chung.

### 3.4. Rotate credentials không gây gián đoạn

Khi thay password, broker và Cloud Controller phải chuyển sang cùng một giá trị. Một quy trình có thể là:

1. Cấu hình broker chấp nhận credentials mới; nếu có thể, hỗ trợ overlap ngắn giữa cũ và mới.
2. Cập nhật Cloud Foundry registration bằng cf update-service-broker.
3. Gọi catalog và kiểm tra một request an toàn.
4. Theo dõi lỗi 401 trong log.
5. Thu hồi credentials cũ sau khi xác nhận platform dùng cấu hình mới.

Nếu đổi password ở broker trước và lập tức thu hồi giá trị cũ, Cloud Controller có thể nhận 401 trong khoảng thời gian chưa cập nhật registration.

## 4. Lỗi phân quyền: HTTP 403 Forbidden

Authorization quyết định caller đã được xác thực có được phép thực hiện hành động trên resource hay không.

Ví dụ Cloud Controller dùng credentials hợp lệ để gọi broker, nhưng request deprovision tham chiếu một instance thuộc tenant/platform khác. Broker nhận diện được platform, song không cho phép platform đó xóa instance.

Đây là lỗi authorization. Đổi password sẽ không giải quyết được vấn đề.

### 4.1. Các phạm vi quyền cần kiểm tra

| Phạm vi | Câu hỏi |
|---|---|
| Broker registration | Platform nào được phép gọi broker? |
| Tenant/organization | Platform có quản lý tenant này không? |
| Service instance | Instance có thuộc platform/tenant đang gọi không? |
| Binding | Binding có thuộc đúng instance và consumer không? |
| Operation | Caller có được thực hiện update/deprovision khi operation khác đang chạy không? |
| Administrative action | Caller có quyền thao tác quản trị ngoài OSB API không? |

Thông tin như organization_guid, space_guid, instance_id hoặc binding_id có thể xuất hiện trong request tùy operation và platform. Broker phải kiểm tra chúng với dữ liệu ownership đã lưu. Không tin một tenant ID do client gửi như bằng chứng quyền truy cập.

### 4.2. HTTP 403 hay 404?

HTTP 403 biểu thị caller đã được xác thực nhưng không có quyền. Tuy nhiên, với tài nguyên đa tenant, trả 403 có thể xác nhận một instance ID tồn tại.

Nếu chính sách bảo mật yêu cầu che sự tồn tại của resource, broker có thể trả 404 cho cả trường hợp resource không tồn tại và trường hợp caller không được phép nhìn thấy nó.

| Tình huống | Hành vi |
|---|---|
| Caller không có quyền trên endpoint công khai | 403 |
| Instance tồn tại nhưng thuộc tenant khác và cần che existence | 404 theo policy |
| Instance thực sự không tồn tại | 404 |
| Caller có quyền nhưng state transition không hợp lệ | Business conflict, thường là 409 |

Nếu dùng 404 để che ownership, response body và cách xử lý cần nhất quán. Audit nội bộ vẫn phải phân biệt RESOURCE_NOT_FOUND và RESOURCE_ACCESS_DENIED để vận hành có thể điều tra.

### 4.3. Kiểm tra ownership trong repository

Có thể giới hạn phạm vi truy vấn theo platform và tenant đã xác thực:

~~~sql
SELECT instance_id,
       service_id,
       current_plan_id,
       tenant_id,
       state
FROM service_instance
WHERE instance_id = :instanceId
  AND platform_id = :authenticatedPlatformId
  AND tenant_id = :authorizedTenantId;
~~~

Nếu không có kết quả, application service xử lý theo chính sách not found/forbidden. Cách này giảm nguy cơ đọc dữ liệu của tenant khác rồi mới kiểm tra quyền.

Với binding, cần kiểm tra cặp instance/binding và ownership. Không chỉ kiểm tra binding_id riêng lẻ.

### 4.4. Phân quyền theo thao tác

Một platform có thể được phép đọc catalog nhưng không được phép gọi administrative endpoint. Trong broker đa tenant hoặc có API quản trị riêng, cần phân biệt quyền:

- Đọc catalog.
- Provision instance.
- Update plan/parameters.
- Deprovision instance.
- Bind consumer.
- Unbind binding.
- Reconcile hoặc can thiệp operation.

Không suy ra quyền trên một hành động từ việc caller đã được xác thực hoặc đã có quyền trên hành động khác.

## 5. Phân biệt 401, 403, 404 và 412

Bốn status này thường bị nhầm lẫn khi điều tra lỗi platform-to-broker.

| Status | Ý nghĩa | Câu hỏi đầu tiên |
|---|---|---|
| 401 Unauthorized | Broker không xác minh được caller | Authorization header và credentials có đúng không? |
| 403 Forbidden | Caller đã xác thực nhưng không được phép | Caller có quyền trên endpoint/tenant/resource không? |
| 404 Not Found | Resource không tồn tại hoặc được che theo policy | ID, namespace và ownership scope có đúng không? |
| 412 Precondition Failed | Phiên bản OSB API được khai báo không được broker hỗ trợ | X-Broker-API-Version có nằm trong supported range không? |

Không dùng status code như một nhãn chung cho mọi request bị từ chối. Client/platform có thể xử lý từng status theo cách khác nhau:

- 401: kiểm tra hoặc cấp lại credentials.
- 403: sửa quyền hoặc scope.
- 404: kiểm tra resource identity và chính sách visibility.
- 412: điều chỉnh compatibility giữa platform và broker.

### 5.1. Error body cần an toàn và nhất quán

OSB API dùng JSON error response với trường description. Ví dụ:

~~~json
{
  "description": "The requested API version is not supported."
}
~~~

Không trả:

- Authorization header hoặc password.
- Stack trace.
- SQL query và database hostname.
- Provider access token.
- Tenant/resource metadata mà caller không có quyền xem.
- Nội dung cấu hình nội bộ của Spring Security.

Có thể ghi internal error code và correlation ID trong log. Nếu trả correlation ID cho caller, nó chỉ nên dùng để liên hệ log, không chứa dữ liệu bí mật.

## 6. Chẩn đoán reverse proxy, ingress và TLS

Không phải mọi lỗi request đều do broker application. Một reverse proxy hoặc ingress có thể thay đổi header, path hoặc TLS trước khi request tới Spring Boot.

### 6.1. Authorization header bị loại bỏ

Một số proxy cần cấu hình rõ để forward header Authorization. Nếu header bị xóa:

- Broker thấy request không có credentials.
- Security filter trả 401.
- Gọi trực tiếp broker có thể thành công, nhưng gọi qua route platform lại thất bại.

So sánh request tại ingress và broker app bằng log đã che dữ liệu. Chỉ ghi nhận header có mặt hay không và loại authentication, không ghi giá trị header.

### 6.2. X-Broker-API-Version bị loại bỏ hoặc thay đổi

Nếu proxy allowlist header không bao gồm X-Broker-API-Version, broker có thể thấy header bị thiếu và từ chối request như một lỗi protocol.

Kiểm tra:

- Ingress header allowlist.
- Gateway transformation rule.
- Middleware có đổi tên header không.
- Có nhiều proxy hop và mỗi hop có policy khác nhau không.

HTTP header không phân biệt chữ hoa/thường theo chuẩn, nhưng tên header và giá trị phải được giữ đúng ngữ nghĩa. Không tự sửa giá trị version tại proxy để che lỗi compatibility.

### 6.3. TLS và routing

Các dấu hiệu:

| Triệu chứng | Kiểm tra |
|---|---|
| TLS handshake failure | Certificate chain, hostname, expiry, CA trust |
| DNS lookup failure | DNS record và network namespace |
| Connection refused | Route, port, service endpoint và pod readiness |
| 404 từ ingress | Host/path rule và base path |
| 502/503 từ gateway | Upstream service, health và timeout |
| 401 chỉ qua ingress | Authorization forwarding và auth middleware |
| 412 chỉ qua ingress | Version header forwarding |

TLS failure xảy ra trước khi HTTP request được xử lý. Vì vậy không cố sửa AuthenticationEntryPoint nếu client không hoàn thành được TLS handshake.

## 7. Tổ chức xử lý trong Spring Security và WebFlux

Trong WebFlux, Spring Security thường xử lý authentication/authorization ở security filter chain trước khi request tới handler OSB. Lỗi tại filter chain cần được ánh xạ riêng với business exception trong application service.

Ví dụ cấu hình khái niệm:

~~~java
@Bean
SecurityWebFilterChain brokerSecurity(
        ServerHttpSecurity http,
        ServerAuthenticationEntryPoint osbEntryPoint,
        ServerAccessDeniedHandler osbDeniedHandler) {

    return http
            .authorizeExchange(exchanges -> exchanges
                    .pathMatchers("/v2/**").authenticated()
                    .anyExchange().denyAll()
            )
            .httpBasic(Customizer.withDefaults())
            .exceptionHandling(exceptions -> exceptions
                    .authenticationEntryPoint(osbEntryPoint)
                    .accessDeniedHandler(osbDeniedHandler)
            )
            .build();
}
~~~

Cấu hình thực tế cần điều chỉnh theo security mechanism, health/management endpoints, phiên bản Spring Security và topology TLS. Không sao chép nguyên mẫu nếu project có nhiều filter chain.

### 7.1. AuthenticationEntryPoint trả 401

ServerAuthenticationEntryPoint xử lý trường hợp chưa xác thực. Với HTTP Basic, response 401 cần challenge WWW-Authenticate phù hợp.

~~~java
@Component
public class OsbAuthenticationEntryPoint
        implements ServerAuthenticationEntryPoint {

    private final OsbErrorWriter errorWriter;

    public OsbAuthenticationEntryPoint(OsbErrorWriter errorWriter) {
        this.errorWriter = errorWriter;
    }

    @Override
    public Mono<Void> commence(
            ServerWebExchange exchange,
            AuthenticationException exception) {

        exchange.getResponse().getHeaders()
                .set(HttpHeaders.WWW_AUTHENTICATE,
                        "Basic realm=\"service-broker\"");

        return errorWriter.write(
                exchange,
                HttpStatus.UNAUTHORIZED,
                "Authentication credentials are missing or invalid."
        );
    }
}
~~~

Đây là ví dụ minh họa. OsbErrorWriter cần ghi JSON có trường description, xử lý response đã commit và không để lỗi serialization tạo ra một response thứ hai.

### 7.2. AccessDeniedHandler trả 403

ServerAccessDeniedHandler xử lý caller đã xác thực nhưng không được phép.

~~~java
@Component
public class OsbAccessDeniedHandler
        implements ServerAccessDeniedHandler {

    private final OsbErrorWriter errorWriter;

    public OsbAccessDeniedHandler(OsbErrorWriter errorWriter) {
        this.errorWriter = errorWriter;
    }

    @Override
    public Mono<Void> handle(
            ServerWebExchange exchange,
            AccessDeniedException exception) {

        return errorWriter.write(
                exchange,
                HttpStatus.FORBIDDEN,
                "The authenticated platform is not permitted to perform this operation."
        );
    }
}
~~~

Nếu policy dùng 404 để che resource, quyết định đó nên được thực hiện ở application/resource authorization layer nơi broker biết resource và tenant scope. Không biến mọi AccessDeniedException thành 404 nếu endpoint công khai cần trả 403.

### 7.3. Kiểm tra OSB API version trước khi vào handler

Có thể đặt version validation ở middleware hoặc lớp tích hợp OSB nếu framework chưa tự kiểm tra. Mục tiêu là bảo đảm request có version được hỗ trợ trước khi thực thi nghiệp vụ.

Pseudo-code:

~~~java
ApiVersion requested =
        ApiVersion.parse(exchange.getRequest()
                .getHeaders()
                .getFirst("X-Broker-API-Version"));

if (requested == null || !supportedVersions.contains(requested)) {
    return errorWriter.write(
            exchange,
            HttpStatus.PRECONDITION_FAILED,
            "The requested Open Service Broker API version is not supported."
    );
}

return chain.filter(exchange);
~~~

Đây là pseudocode để minh họa vị trí kiểm tra. Cần phân biệt header thiếu với header chứa phiên bản không hỗ trợ theo contract đang triển khai. Nếu Spring Cloud Open Service Broker version hiện tại đã kiểm tra header, không thêm một filter thứ hai có thể mâu thuẫn với framework.

### 7.4. Business exception không phải security exception

Nếu caller có quyền nhưng instance đang ở trạng thái không cho phép update, đây là lỗi nghiệp vụ. Application service có thể phát InstanceStateConflictException và ánh xạ thành response phù hợp, thường là 409.

Không dùng AccessDeniedException cho mọi trường hợp không thể thực hiện thao tác. Việc phân loại đúng giúp platform và operator biết cần sửa quyền hay chờ lifecycle operation.

## 8. Quy trình chẩn đoán từng bước

Khi nhận ticket “Cloud Foundry không gọi được service broker”, thực hiện theo trình tự sau:

### Bước 1: Xác nhận request tới đúng endpoint

- Kiểm tra broker route và base URL.
- Xác minh /v2/catalog được map đúng.
- Kiểm tra DNS, TLS và ingress.
- Phân biệt lỗi kết nối với HTTP response do broker trả.

### Bước 2: Đọc status và response description

- 412: kiểm tra X-Broker-API-Version.
- 401: kiểm tra platform credentials và Authorization header.
- 403: kiểm tra caller identity và policy.
- 404: kiểm tra resource ID, scope và anti-enumeration policy.

Đừng chỉ dựa vào thông báo CLI; lấy status/body từ Cloud Controller logs hoặc broker access logs đã sanitize.

### Bước 3: Kiểm tra header đã tới ứng dụng

Ghi nhận an toàn:

- X-Broker-API-Version có mặt và giá trị.
- Authorization header có mặt hay không.
- Host và path sau proxy.
- Correlation ID.
- HTTP method.

Không ghi nội dung Authorization header.

### Bước 4: Kiểm tra registration và credentials

- Xác nhận đúng Cloud Foundry foundation.
- Chạy cf service-brokers.
- Kiểm tra tên broker, URL và registration được quản trị.
- Nếu credentials thay đổi, dùng cf update-service-broker.
- Gọi catalog trực tiếp với cùng credentials để so sánh.

### Bước 5: Kiểm tra quyền và ownership

- Platform registration có được phép gọi broker không?
- Instance có thuộc đúng platform/tenant không?
- Binding có thuộc đúng instance không?
- Hành động hiện tại có được phép theo policy không?
- Có đang che existence bằng 404 hay không?

### Bước 6: Xác minh provider chưa bị gọi

Với 412, 401 hoặc 403, thông thường request nên bị từ chối trước side effect provider. Kiểm tra provider adapter call count, audit và operation record. Nếu backend đã bị gọi trước khi authorization hoàn tất, cần sửa thứ tự kiểm tra.

### Bước 7: Retest và quan sát

Sau khi sửa:

- Gọi catalog.
- Thử một request lifecycle trên service instance thử nghiệm.
- Xác nhận status/body đúng.
- Kiểm tra không có duplicate operation hoặc resource.
- Theo dõi log 401/403/412 sau khi cập nhật.

## 9. Ma trận chẩn đoán nhanh

| Dấu hiệu | Nguyên nhân ưu tiên | Hành động |
|---|---|---|
| Catalog trả 412 | OSB API version không hỗ trợ | So sánh header với supported range |
| Header version không có tại app nhưng có ở proxy | Proxy strip header | Sửa header forwarding |
| Catalog trả 401 | Platform credentials sai/thiếu | Kiểm tra registration và Basic Auth |
| 401 chỉ xuất hiện sau rotate | Cloud Controller và broker chưa đồng bộ password | Cập nhật registration |
| 401 chỉ qua ingress | Authorization header bị loại bỏ hoặc auth middleware xung đột | Kiểm tra proxy chain |
| Request trả 403 | Caller xác thực được nhưng thiếu quyền | Kiểm tra platform/tenant/action policy |
| 404 cho instance tồn tại | Có thể ownership policy đang che resource | Kiểm tra audit và tenant scope |
| 403/404 xảy ra sau khi provider bị gọi | Authorization đặt sai vị trí | Chuyển kiểm tra quyền lên trước side effect |
| Provider log có 401 nhưng broker access log không có 401 | Provider từ chối broker credentials | Sửa credentials broker-to-provider |
| TLS error, không có HTTP status | Certificate, DNS hoặc route | Kiểm tra TLS/network trước security |
| 412 sau deploy mới | Broker/framework đổi supported version range | Kiểm tra compatibility và regression test |

## 10. Kiểm thử response 412, 401 và 403

Không chỉ kiểm thử code path thành công. Mỗi nhóm từ chối cần có test riêng và xác nhận broker không gọi provider.

### 10.1. Test version mismatch

Gửi một version ngoài supported range:

~~~http
GET /v2/catalog
X-Broker-API-Version: 99.99
Authorization: Basic <test-credentials>
~~~

Kỳ vọng:

- HTTP 412.
- Body JSON có description.
- Không gọi application operation hoặc provider adapter.
- Log ghi version đã nhận theo cách không chứa secret.

Ngoài version không hỗ trợ, cần test phiên bản thấp nhất và cao nhất mà broker cam kết hỗ trợ.

### 10.2. Test authentication

Dùng WebTestClient hoặc HTTP test client:

~~~java
webTestClient.get()
        .uri("/v2/catalog")
        .header("X-Broker-API-Version", supportedVersion)
        .exchange()
        .expectStatus().isUnauthorized()
        .expectHeader().exists(HttpHeaders.WWW_AUTHENTICATE)
        .expectBody()
        .jsonPath("$.description").exists();
~~~

Kỳ vọng:

- Không credentials nhận 401.
- Credentials sai nhận 401.
- Response không tiết lộ username/password nào sai.
- Catalog/application service không bị gọi nếu filter chain từ chối trước đó.

### 10.3. Test authorization

~~~java
webTestClient.delete()
        .uri("/v2/service_instances/{id}?service_id={service}&plan_id={plan}",
                "instance-owned-by-another-tenant",
                "managed-postgresql",
                "standard")
        .headers(headers -> headers.setBasicAuth(
                "valid-platform",
                "valid-password"
        ))
        .header("X-Broker-API-Version", supportedVersion)
        .exchange()
        .expectStatus().isForbidden();
~~~

Nếu policy che existence, test có thể mong đợi 404 thay vì 403. Trong cả hai trường hợp:

- Không gọi provider delete.
- Không tạo operation deprovision.
- Không trả dữ liệu của tenant khác.
- Audit ghi nhận authorization denial.

### 10.4. Test phân biệt provider credentials

Giả lập provider trả 401 trong khi platform credentials hợp lệ. Kỳ vọng broker ghi dependency authentication failure và xử lý operation theo policy; không trả nhầm 401 để yêu cầu platform đăng nhập lại. Với async operation, lỗi được lưu trong operation và phản ánh qua last_operation.

## 11. Log, audit và metric phục vụ điều tra

Để tìm nguyên nhân nhanh mà không làm lộ bí mật, log nên có:

- Correlation ID hoặc trace ID.
- Broker registration/platform ID.
- HTTP method và route template.
- OSB API version nhận được.
- Kết quả authentication: success/failure.
- Kết quả authorization: allowed/denied và policy code.
- Internal error code.
- HTTP status.
- Resource ID đã được che hoặc băm nếu cần.
- Provider call có xảy ra hay không.

Không log:

- Authorization header.
- Password hoặc token.
- Binding credentials.
- Raw request parameters có secret.
- Toàn bộ thông tin tenant khác mà caller không được phép xem.

Metric có thể gồm:

| Metric | Ý nghĩa |
|---|---|
| osb_api_version_rejected_total | Số request bị từ chối vì version |
| broker_authentication_failure_total | Số request 401 |
| broker_authorization_denied_total | Số request bị từ chối quyền |
| broker_resource_visibility_404_total | Số request trả 404 theo policy |
| broker_provider_auth_failure_total | Số lần provider từ chối credentials của broker |
| broker_request_rejected_total | Tổng request bị từ chối theo category |

Dùng label có cardinality thấp như endpoint group, status và error category. Không dùng username, password, tenant ID hoặc instance ID làm metric label.

## 12. Những lỗi xử lý thường gặp

- **Trả 401 cho version mismatch:** platform sẽ kiểm tra credentials dù vấn đề nằm ở protocol header.
- **Trả 412 cho password sai:** che khuất lỗi authentication và khiến việc sửa cấu hình sai hướng.
- **So sánh version bằng chuỗi:** có thể chấp nhận hoặc từ chối nhầm phiên bản.
- **Mặc định version khi header bị thiếu:** che lỗi proxy/client và tạo hành vi không nhất quán.
- **Nhầm provider 401 với platform 401:** yêu cầu platform đổi credentials dù broker-to-provider mới là bên sai.
- **Trả 403 cho resource thuộc tenant khác trong mọi trường hợp:** có thể làm lộ sự tồn tại của resource.
- **Dùng 404 cho mọi lỗi:** platform không biết request sai ID hay bị policy từ chối.
- **Kiểm tra quyền sau khi gọi provider:** có thể tạo side effect trái phép.
- **Chỉ kiểm tra authentication ở ingress:** request nội bộ hoặc route khác có thể bỏ qua bảo vệ.
- **Tin X-Broker-API-Originating-Identity như credentials:** header này không thay thế authentication của platform.
- **Rotate password không đồng bộ:** Cloud Controller tiếp tục gửi credentials cũ.
- **Tắt TLS verification để xử lý lỗi kết nối:** làm suy yếu bảo mật và che nguyên nhân thật.

## 13. Quy trình phòng ngừa tái diễn

Khi triển khai hoặc nâng cấp broker, hãy duy trì các kiểm tra sau:

1. Công bố rõ OSB API version range được hỗ trợ.
2. Chạy contract test cho version thấp nhất, cao nhất và version không hỗ trợ.
3. Kiểm tra reverse proxy giữ nguyên X-Broker-API-Version và Authorization.
4. Quản lý broker registration credentials trong secret store.
5. Có quy trình rotate credentials đồng bộ giữa broker và platform.
6. Tách authentication, authorization và business exception mapping.
7. Kiểm tra platform/tenant ownership trước khi gọi backend.
8. Áp dụng policy 403/404 nhất quán để bảo vệ resource visibility.
9. Phân biệt provider credentials với platform credentials.
10. Theo dõi metric 401/403/412 và cảnh báo khi tăng bất thường.
11. Kiểm thử từ đường mạng mà Cloud Controller thực sự sử dụng.
12. Retest catalog và lifecycle sau mỗi lần thay đổi security, ingress hoặc OSB dependency.

## Kết luận

Request bị từ chối vì phiên bản giao thức, xác thực hoặc phân quyền là ba nhóm lỗi khác nhau. HTTP 412 chỉ ra phiên bản OSB API được khai báo không được broker hỗ trợ; HTTP 401 cho biết broker không xác minh được credentials của platform; HTTP 403 cho biết caller đã xác thực nhưng không có quyền. HTTP 404 có thể được dùng theo policy để che sự tồn tại của resource thuộc tenant khác.

Trong Spring Cloud Service Broker, hãy kiểm tra X-Broker-API-Version, credentials Cloud Controller dùng khi đăng ký broker, security filter chain và ownership policy theo đúng thứ tự. Đồng thời phân biệt lỗi platform-to-broker với lỗi broker-to-provider, vì hai đường xác thực có credentials và cách phản hồi khác nhau. Response OSB cần có description an toàn, log cần đủ correlation để điều tra, và mọi request bị từ chối phải được xác minh là không tạo side effect ngoài ý muốn.
