# Kiểm thử Token Exchange và giới hạn scope, audience

Token Exchange cho phép một client đã được ủy quyền đổi token đầu vào thành token mới dành cho một ngữ cảnh truy cập khác. Ví dụ, gateway nhận access token dùng cho `orders-api`, sau đó cần gọi `shipping-api`. Nếu chuyển tiếp nguyên token ban đầu, dịch vụ shipping có thể nhận nhiều quyền hơn mức cần thiết. Với OAuth 2.0 Token Exchange (RFC 8693), Authorization Server có thể phát hành token mới với subject, actor, audience, scope và thời hạn được giới hạn theo chính sách delegation.

Kiểm thử chức năng của luồng này phải chứng minh cả hai điều: request hợp lệ nhận đúng token cho resource đích, và request vượt quyền bị từ chối hoặc được thu hẹp theo chính sách đã công bố. Chỉ kiểm tra HTTP 200 hoặc sự hiện diện của `access_token` là chưa đủ. Cần kiểm tra token mới, authorization persistence, Resource Server đích và các trường hợp âm tính để phát hiện lỗi confused deputy hoặc privilege escalation.

## 1. Xác định hợp đồng của Token Exchange

RFC 8693 định nghĩa grant type:

```text
urn:ietf:params:oauth:grant-type:token-exchange
```

Các tham số thường gặp:

| Tham số | Ý nghĩa | Yêu cầu kiểm thử |
|---|---|---|
| `grant_type` | Xác định Token Exchange grant | Server nhận đúng grant và không nhầm với refresh token |
| `subject_token` | Token đại diện cho subject được trao đổi | Chữ ký/issuer/audience/thời hạn và trạng thái token phải được xác minh |
| `subject_token_type` | Loại token đầu vào | Chỉ chấp nhận loại được cấu hình, ví dụ access token |
| `actor_token` | Token của actor thực hiện hành động thay mặt subject, nếu có | Xác minh độc lập actor và quan hệ delegation |
| `actor_token_type` | Loại của actor token | Không suy đoán loại token từ nội dung không đáng tin cậy |
| `requested_token_type` | Loại token client muốn nhận | Chỉ phát hành loại token server hỗ trợ |
| `audience` | Resource/audience đích | Chỉ chấp nhận audience nằm trong policy của client và subject |
| `resource` | URI resource đích theo Resource Indicators, nếu hỗ trợ | Kiểm tra URI chính xác và ánh xạ đến resource được cho phép |
| `scope` | Quyền client yêu cầu trong token mới | Không cấp rộng hơn quyền subject, client và resource đích cho phép |

Ví dụ request:

```bash
curl -X POST https://identity.example.com/oauth2/token \
  -u 'orders-gateway:<client-secret>' \
  -H 'Content-Type: application/x-www-form-urlencoded' \
  --data-urlencode 'grant_type=urn:ietf:params:oauth:grant-type:token-exchange' \
  --data-urlencode 'subject_token=<subject-access-token>' \
  --data-urlencode 'subject_token_type=urn:ietf:params:oauth:token-type:access_token' \
  --data-urlencode 'requested_token_type=urn:ietf:params:oauth:token-type:access_token' \
  --data-urlencode 'audience=shipping-api' \
  --data-urlencode 'scope=shipment.create'
```

Các giá trị trong lệnh là placeholder. Client phải xác thực bằng phương thức đã đăng ký. Không đưa secret, token thật hoặc dữ liệu người dùng vào source control, tài liệu lab hoặc log.

Response thành công thường có dạng:

```json
{
  "access_token": "<new-access-token>",
  "issued_token_type": "urn:ietf:params:oauth:token-type:access_token",
  "token_type": "Bearer",
  "expires_in": 300,
  "scope": "shipment.create"
}
```

`scope` trong response có thể được lược bỏ khi bằng scope được yêu cầu theo quy tắc OAuth token response. Vì vậy, kiểm tra quyền thực tế trong JWT hoặc qua introspection; không dựa riêng vào việc response có trường `scope` hay không. Token đầu ra cũng có thể là opaque token thay vì JWT, tùy cấu hình server.

## 2. Thiết kế policy kiểm soát scope và audience

Trước khi viết test, xác định rõ policy cho một luồng nghiệp vụ. Ví dụ gateway `orders-gateway` cần tạo shipment sau khi xử lý đơn hàng:

| Thành phần | Giá trị minh họa |
|---|---|
| Client thực hiện exchange | `orders-gateway` |
| Subject token issuer | `https://identity.example.com` |
| Subject token audience | `orders-api` |
| Subject token scope | `orders.read shipment.request` |
| Audience đích được phép | `shipping-api` |
| Scope đích được phép | `shipment.create` |
| Scope nhạy cảm bị cấm | `payment.refund`, `admin` |
| Thời hạn tối đa token mới | 5 phút hoặc ngắn hơn theo thời gian còn lại của subject token |

Một quyết định cấp quyền có thể được biểu diễn bằng giao của nhiều tập quyền:

```text
S_granted = intersection(
    S_requested,
    S_subject,
    S_client_policy,
    S_resource
)
```

Trong đó:

- `S_requested` là scope client yêu cầu.
- `S_subject` là quyền mà subject token thể hiện và policy cho phép delegation.
- `S_client_policy` là scope mà client được phép trao đổi.
- `S_resource` là scope mà resource đích hỗ trợ.

Nếu client yêu cầu `shipment.create payment.refund`, kết quả không thể chứa `payment.refund` khi policy gateway chỉ cho phép shipment. Ứng dụng cần chọn một hành vi nhất quán: từ chối toàn bộ request nếu có scope ngoài policy, hoặc chỉ cấp phần giao hợp lệ. Cả hai cách đều có thể được thiết kế, nhưng phải được công bố, kiểm thử và áp dụng đồng nhất. Không âm thầm cấp scope rộng hơn yêu cầu.

Audience cần được kiểm soát độc lập với scope. Token có `shipment.create` nhưng audience là `admin-api` vẫn có thể bị dùng sai ở resource khác. Chỉ cấp token cho audience đã được allowlist theo client, subject và quan hệ delegation. Nếu client gửi nhiều `audience` hoặc `resource`, kiểm tra toàn bộ danh sách và không chấp nhận giá trị không được phép chỉ vì một giá trị khác hợp lệ.

Thời hạn token mới nên bị giới hạn bởi policy và thời gian còn lại của subject token. Nếu token đầu vào gần hết hạn, không tạo token mới có thời hạn dài hơn chỉ vì client yêu cầu. Nếu subject token bị thu hồi hoặc không còn hợp lệ theo chính sách, exchange phải thất bại.

## 3. Phân tầng kiểm thử

Một bộ kiểm thử tốt có bốn tầng. Mỗi tầng xác minh một phần hợp đồng và giúp khoanh vùng lỗi nhanh hơn.

| Tầng | Thành phần | Điều cần chứng minh |
|---|---|---|
| Unit test policy | Service tính audience, scope, thời hạn và delegation | Quyết định quyền đúng với từng tổ hợp client/subject/resource |
| Provider test | `AuthenticationProvider` của custom grant hoặc provider tương ứng | Xác minh token đầu vào, client và policy; lỗi không tạo token |
| Endpoint integration test | Token endpoint qua MockMvc hoặc HTTP thật | Client authentication, request parsing, OAuth error và response token đúng |
| Resource Server integration test | API nhận token mới | Chỉ token đúng issuer, audience và scope mới được chấp nhận |

Nếu phiên bản Spring Authorization Server có implementation Token Exchange phù hợp, hãy kiểm thử qua API đó. Nếu ứng dụng tự mở rộng token endpoint bằng `AuthenticationConverter` và `AuthenticationProvider`, test phải đi qua converter/provider thực tế. Chỉ đăng ký `AuthorizationGrantType` trong `RegisteredClient` không chứng minh grant đã được xử lý.

## 4. Chuẩn bị dữ liệu kiểm thử

Tạo fixture riêng cho mỗi test hoặc reset persistence giữa các test để tránh token, authorization và trạng thái thu hồi rò rỉ qua nhau. Một bộ fixture hữu ích gồm:

| Fixture | Thuộc tính cần có |
|---|---|
| Client hợp lệ | `orders-gateway`, client authentication đúng, grant Token Exchange được phép |
| Client không được exchange | Client đã đăng ký nhưng không có quyền dùng grant |
| Subject token hợp lệ | Issuer tin cậy, audience `orders-api`, scope `orders.read shipment.request`, chưa hết hạn |
| Subject token sai audience | Audience `billing-api` hoặc resource không được phép |
| Subject token hết hạn | `exp` nằm trong quá khứ |
| Subject token sai issuer/chữ ký | Không thể xác minh bằng trust configuration được khai báo |
| Subject token bị thu hồi | Introspection hoặc trạng thái authorization thể hiện inactive/revoked |
| Actor token hợp lệ | Actor được policy cho phép đại diện subject |
| Actor token không hợp lệ | Sai issuer, hết hạn hoặc không có quan hệ delegation |
| Resource đích | `shipping-api` hỗ trợ `shipment.create`; `admin-api` không nằm trong allowlist |

Với JWT fixture, ký token bằng khóa kiểm thử riêng và cấu hình decoder chỉ tin issuer/JWK Set của test. Không dùng token production hoặc tắt kiểm tra chữ ký để làm test dễ chạy. Với opaque token, mock introspection response theo các trường hợp active/inactive, issuer, audience và scope mà implementation của bạn yêu cầu.

## 5. Kiểm thử policy scope và audience ở unit level

Tách quyết định quyền khỏi controller và việc serialize token. Một policy service có thể nhận client, subject context, actor context, audience và scope yêu cầu, rồi trả về kết quả đã chuẩn hóa hoặc lỗi nghiệp vụ.

Ví dụ hợp đồng service minh họa:

```java
public interface TokenExchangePolicy {
    ExchangeDecision evaluate(ExchangeContext context);
}

public record ExchangeContext(
        RegisteredClient client,
        VerifiedToken subject,
        VerifiedToken actor,
        Set<String> requestedAudiences,
        Set<String> requestedScopes) {}

public record ExchangeDecision(
        Set<String> grantedAudiences,
        Set<String> grantedScopes,
        Instant expiresAt) {}
```

`VerifiedToken` và `ExchangeDecision` là kiểu dữ liệu ứng dụng minh họa. Chúng phải được tạo sau khi token được xác minh; không khởi tạo từ claim hoặc parameter chưa tin cậy. Dùng `Set` giúp loại bỏ scope/audience trùng lặp và làm rõ phép giao tập hợp.

Các unit test nên bao gồm:

1. Scope yêu cầu là tập con hợp lệ: cấp đúng scope được yêu cầu.
2. Scope yêu cầu có một quyền ngoài policy: từ chối toàn bộ hoặc thu hẹp theo quyết định đã chọn.
3. Scope yêu cầu rỗng: áp dụng default scope được định nghĩa cho resource hoặc từ chối nếu không có default.
4. Client hợp lệ nhưng subject không có quyền tương ứng: không cấp scope đó.
5. Subject có quyền nhưng client không được delegate: không cấp scope đó.
6. Resource đích không hỗ trợ scope: không cấp scope không tồn tại ở resource.
7. Audience yêu cầu nằm trong allowlist: cấp đúng audience đó.
8. Audience không được phép hoặc chứa cả giá trị hợp lệ lẫn không hợp lệ: xử lý đúng chính sách all-or-nothing hoặc lọc đã công bố.
9. Token đầu vào gần hết hạn: token mới không vượt thời hạn tối đa.
10. Actor không được phép: từ chối delegation ngay cả khi subject và client hợp lệ.

Ví dụ kiểm tra phép giao scope:

```java
@Test
void grantsOnlyScopesAllowedBySubjectClientAndResource() {
    Set<String> requested = Set.of("shipment.create", "payment.refund");
    Set<String> subjectScopes = Set.of("shipment.create", "orders.read");
    Set<String> clientScopes = Set.of("shipment.create");
    Set<String> resourceScopes = Set.of("shipment.create", "shipment.read");

    Set<String> granted = policy.intersectScopes(
            requested, subjectScopes, clientScopes, resourceScopes);

    assertThat(granted).containsExactly("shipment.create");
    assertThat(granted).doesNotContain("payment.refund");
}
```

Nếu policy chọn từ chối khi có scope không được phép, test phải xác minh policy trả lỗi thay vì trả tập con. Điều quan trọng là hành vi có chủ đích và không làm tăng quyền.

## 6. Kiểm thử token endpoint bằng MockMvc

Endpoint test cần dùng filter chain, client authentication, converter/provider và token generator thật của ứng dụng. Mock những dependency ngoài ranh giới test như introspection server hoặc clock nếu cần, nhưng không mock chính policy đang muốn xác minh.

Ví dụ test happy path với confidential client dùng HTTP Basic:

```java
@SpringBootTest
@AutoConfigureMockMvc
class TokenExchangeEndpointTests {

    @Autowired
    MockMvc mockMvc;

    @Test
    void exchangesSubjectTokenForRestrictedAudienceAndScope() throws Exception {
        String subjectToken = tokenFixtures.validOrdersAccessToken();

        mockMvc.perform(post("/oauth2/token")
                        .with(httpBasic("orders-gateway", "test-secret"))
                        .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                        .param("grant_type",
                                "urn:ietf:params:oauth:grant-type:token-exchange")
                        .param("subject_token", subjectToken)
                        .param("subject_token_type",
                                "urn:ietf:params:oauth:token-type:access_token")
                        .param("requested_token_type",
                                "urn:ietf:params:oauth:token-type:access_token")
                        .param("audience", "shipping-api")
                        .param("scope", "shipment.create"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.access_token").isNotEmpty())
                .andExpect(jsonPath("$.issued_token_type").value(
                        "urn:ietf:params:oauth:token-type:access_token"))
                .andExpect(jsonPath("$.token_type").value("Bearer"));
    }
}
```

`tokenFixtures`, client registration và password encoder là fixture của ứng dụng kiểm thử. Endpoint path, client authentication method và response fields cần khớp implementation thực tế. Không dùng `@WithMockUser` để thay cho client authentication ở token endpoint: người dùng đăng nhập và OAuth client là hai principal khác nhau.

Sau khi nhận response, xác minh token mới bằng đúng cách resource server sẽ xác minh. Nếu access token là JWT, decode và xác minh chữ ký qua decoder test; nếu là opaque token, gọi introspection endpoint hoặc kiểm tra authorization persistence trong test. Không chỉ base64-decode JWT rồi tin claim.

## 7. Kiểm tra claim và token response

Với JWT access token, các thuộc tính cần kiểm tra gồm:

| Claim/thuộc tính | Điều kiện mong đợi |
|---|---|
| `iss` | Issuer đúng của Authorization Server |
| `sub` | Giữ đúng subject theo policy; không biến actor thành subject ngoài ý muốn |
| `aud` | Chỉ chứa resource đích được phép, ví dụ `shipping-api` |
| `scope` hoặc `scp` | Chỉ có scope được cấp theo policy và định dạng token đã chọn |
| `exp` | Không vượt quá thời hạn policy và thời gian còn lại của subject token |
| `iat` | Thời điểm phát hành hợp lệ, không nằm trong tương lai ngoài clock skew cho phép |
| `act` | Chỉ có khi profile delegation sử dụng actor claim; giá trị khớp actor đã xác minh |
| `jti` | Nếu được dùng, token mới có định danh riêng theo policy chống replay/audit |

Tên claim scope có thể phụ thuộc token format và converter. Với opaque token, kiểm tra các thuộc tính tương ứng qua introspection response, chẳng hạn `active`, `sub`, `aud`, `scope`, `iss` và `exp` nếu server công bố chúng. So sánh audience theo kiểu dữ liệu và quy tắc JWT: `aud` có thể là một chuỗi hoặc một mảng chuỗi.

Response token exchange cần kiểm tra `issued_token_type` đúng loại đã phát hành và `token_type` đúng loại bearer hoặc loại khác mà implementation hỗ trợ. `expires_in` phải phù hợp thời hạn thực của token. Nếu response trả `scope`, giá trị đó phải tương ứng với quyền thực tế; nếu response lược bỏ `scope`, kiểm tra JWT/introspection để xác nhận quyền.

Ví dụ xác minh JWT bằng decoder đã cấu hình issuer/JWK tin cậy:

```java
Jwt jwt = jwtDecoder.decode(response.accessToken());

assertThat(jwt.getIssuer()).isEqualTo(URI.create("https://identity.example.com"));
assertThat(jwt.getSubject()).isEqualTo("user-123");
assertThat(jwt.getAudience()).containsExactly("shipping-api");
assertThat(jwt.getClaimAsStringList("scope"))
        .containsExactly("shipment.create");
assertThat(jwt.getExpiresAt()).isBeforeOrEqualTo(policyExpiry);
```

Đây là ví dụ với access token JWT và kiểu claim scope dạng list. Nếu token generator của ứng dụng dùng claim `scope` dạng chuỗi, `scp` hoặc opaque token, viết assertion tương ứng. Điều cần giữ nguyên là xác minh chữ ký/active state, issuer, subject, audience, scope và thời hạn.

## 8. Kiểm thử các trường hợp từ chối

Không nên chỉ kiểm tra request hợp lệ. Những ca âm tính sau giúp phát hiện việc xác thực thiếu hoặc policy bị bỏ qua:

| Tình huống | Kết quả mong đợi |
|---|---|
| Client không được đăng ký hoặc secret sai | Client authentication thất bại; không phát hành token |
| Client hợp lệ nhưng không được phép Token Exchange | Từ chối grant theo policy |
| Thiếu `subject_token` hoặc `subject_token_type` | Từ chối request không hợp lệ |
| `subject_token_type` không được hỗ trợ | Từ chối; không đoán loại token |
| Subject token sai chữ ký hoặc issuer | Từ chối `invalid_grant` hoặc lỗi OAuth tương ứng theo implementation |
| Subject token hết hạn/chưa có hiệu lực | Từ chối exchange |
| Subject token inactive hoặc đã revoke | Từ chối exchange |
| Subject token có audience không phù hợp với policy | Từ chối hoặc áp dụng delegation rule đã định nghĩa; không cấp quyền mặc định |
| Audience đích không được allowlist | Từ chối target theo error mapping đã công bố |
| Scope chứa quyền vượt policy | Từ chối hoặc chỉ cấp phần giao theo policy; tuyệt đối không cấp scope vượt quyền |
| Actor token không hợp lệ | Từ chối delegation |
| `requested_token_type` không hỗ trợ | Từ chối loại token yêu cầu |
| Subject token bị dùng với client khác | Chỉ chấp nhận nếu quan hệ delegation cho phép rõ ràng |
| Request thiếu hoặc lặp tham số theo cách không hợp lệ | Từ chối theo parser và profile của endpoint |

OAuth error cụ thể phụ thuộc loại lỗi và profile mà server triển khai. Ví dụ `invalid_client`, `unauthorized_client`, `unsupported_grant_type`, `invalid_request`, `invalid_grant` và `invalid_scope` có ý nghĩa khác nhau. Nếu implementation dùng lỗi mở rộng cho target/resource không hợp lệ, tài liệu hóa và test chính xác mã lỗi đó. Không biến mọi lỗi thành HTTP 500 hoặc một response 200 chứa token rỗng.

Ví dụ test xác minh scope ngoài policy bị từ chối:

```java
@Test
void rejectsExchangeWhenRequestedScopeExceedsPolicy() throws Exception {
    String subjectToken = tokenFixtures.validOrdersAccessToken();

    mockMvc.perform(post("/oauth2/token")
                    .with(httpBasic("orders-gateway", "test-secret"))
                    .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                    .param("grant_type",
                            "urn:ietf:params:oauth:grant-type:token-exchange")
                    .param("subject_token", subjectToken)
                    .param("subject_token_type",
                            "urn:ietf:params:oauth:token-type:access_token")
                    .param("audience", "shipping-api")
                    .param("scope", "shipment.create payment.refund"))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.error").value("invalid_scope"));
}
```

Test này giả định policy từ chối toàn bộ request khi có scope ngoài allowlist và ánh xạ lỗi sang `invalid_scope`. Nếu hệ thống chọn thu hẹp scope, thay assertion bằng kiểm tra token chỉ có `shipment.create` và không chứa `payment.refund`. Không kiểm tra status một cách cứng nhắc nếu implementation có error handler khác; kiểm tra đúng hợp đồng OAuth đã định nghĩa.

Sau mỗi trường hợp bị từ chối, xác minh không có authorization/token mới được lưu. Có thể kiểm tra qua `OAuth2AuthorizationService`, repository test hoặc introspection. Đây là điều kiện quan trọng để phát hiện provider tạo token trước khi hoàn tất toàn bộ policy validation.

## 9. Kiểm thử actor và delegation

Nếu luồng dùng `actor_token`, subject và actor phải được xác minh độc lập. Subject là người hoặc workload mà quyền truy cập hướng tới; actor là client/service thực hiện hành động thay mặt subject. Không lấy `actor` từ request parameter rồi ghi thẳng vào claim token.

Các test cần có:

- Actor token hợp lệ, issuer tin cậy và còn hạn được chấp nhận khi client có quyền đại diện.
- Actor token sai issuer, sai chữ ký, hết hạn hoặc inactive bị từ chối.
- Actor hợp lệ nhưng không có quan hệ delegation với subject bị từ chối.
- Client có quyền exchange nhưng không có quyền dùng actor cụ thể vẫn bị từ chối.
- Token mới giữ đúng `sub` và biểu diễn actor theo claim/profile đã chọn, chẳng hạn `act` khi triển khai RFC 8693 JWT actor claim.
- Chuỗi delegation nhiều tầng được giới hạn độ sâu và không tạo vòng lặp actor.

Nếu ứng dụng không dùng actor token, test phải xác minh server không tự suy ra actor từ header hoặc dữ liệu request không đáng tin cậy. Ghi audit subject và client thực hiện exchange bằng định danh nội bộ đã được bảo vệ.

## 10. Kiểm thử Resource Server nhận token mới

Token Exchange chỉ hoàn chỉnh khi Resource Server đích chấp nhận token mới đúng cách. Dùng một Resource Server thử nghiệm với hai endpoint:

```java
@RestController
class ShippingController {

    @GetMapping("/shipments")
    @PreAuthorize("hasAuthority('SCOPE_shipment.read')")
    List<String> listShipments() {
        return List.of("shipment-001");
    }

    @PostMapping("/shipments")
    @PreAuthorize("hasAuthority('SCOPE_shipment.create')")
    String createShipment() {
        return "created";
    }
}
```

Resource Server cần xác minh issuer và audience. Có thể thêm validator cho audience mong đợi cùng issuer validator:

```java
OAuth2TokenValidator<Jwt> audienceValidator = jwt ->
        jwt.getAudience().contains("shipping-api")
                ? OAuth2TokenValidatorResult.success()
                : OAuth2TokenValidatorResult.failure(
                        new OAuth2Error("invalid_token", "Invalid audience", null));

JwtDecoder decoder = JwtDecoders.fromIssuerLocation("https://identity.example.com");
((NimbusJwtDecoder) decoder).setJwtValidator(
        new DelegatingOAuth2TokenValidator<>(
                JwtValidators.createDefaultWithIssuer("https://identity.example.com"),
                audienceValidator));
```

Đoạn cấu hình minh họa cách ghép issuer validator và audience validator; dùng bean `JwtDecoder` thực tế của ứng dụng và tránh tạo nhiều decoder cạnh tranh. `JwtDecoders.fromIssuerLocation` cần discovery/JWKS truy cập được trong môi trường test; có thể dùng decoder với JWK Set test cố định cho integration test.

Các test end-to-end cần chứng minh:

1. Token exchange hợp lệ cho `shipping-api` gọi được endpoint có scope đã cấp.
2. Cùng token đó gọi endpoint yêu cầu scope chưa cấp bị `403`.
3. Token có audience `orders-api` bị `401` tại `shipping-api`, dù chữ ký hợp lệ.
4. Token hết hạn hoặc issuer sai bị `401`.
5. Token mới không được resource khác chấp nhận chỉ vì cùng issuer.
6. Token có scope hợp lệ nhưng audience sai vẫn bị từ chối.

Kiểm tra cả `401 Unauthorized` (token không hợp lệ hoặc không được chấp nhận) và `403 Forbidden` (token hợp lệ nhưng thiếu authority). Phân biệt hai trạng thái giúp xác định lỗi nằm ở xác minh token hay phân quyền endpoint.

## 11. Kiểm thử thời hạn, thu hồi và tính nhất quán

Token Exchange tạo một authorization/token mới nên cần kiểm tra vòng đời của nó. Dùng clock có thể điều khiển trong unit test để tránh test phụ thuộc thời gian thực. Với integration test, tạo token có thời hạn ngắn trong môi trường test và xác minh hành vi sau khi hết hạn.

Các trường hợp nên kiểm tra:

- `expires_in` và `exp` khớp thời hạn được policy cho phép.
- Token đầu vào gần hết hạn không tạo token mới sống lâu hơn giới hạn delegation.
- Token subject bị thu hồi trước khi exchange thì request thất bại.
- Token mới bị thu hồi thì Resource Server xử lý theo cơ chế revocation/introspection hoặc thời hạn JWT đã thiết kế.
- Nếu token mới là JWT tự chứa, kiểm tra rõ giới hạn thu hồi: resource server chỉ xác minh chữ ký có thể tiếp tục chấp nhận JWT đến `exp` nếu không có cơ chế kiểm tra trạng thái.
- Hai request exchange đồng thời không làm vượt quota delegation hoặc tạo quyền khác nhau do đọc policy không nhất quán.
- Mọi instance dùng cùng client registration, policy, authorization persistence và khóa ký.

Nếu policy có quota hoặc giới hạn số lần exchange, kiểm thử concurrency bằng nhiều request đồng thời và xác minh giới hạn được thực thi ở kho dùng chung. Không dựa vào biến đếm trong bộ nhớ của một instance khi triển khai nhiều node.

## 12. Audit và bảo vệ dữ liệu kiểm thử

Audit event nên cho biết client nào yêu cầu exchange, subject nào được đại diện, actor nào tham gia, audience và scope nào được cấp, kết quả, thời điểm và correlation ID. Không ghi `subject_token`, `actor_token`, client secret, access token mới hoặc toàn bộ form body vào log.

Trong test, dùng token giả lập và khóa riêng test. Sau khi test, dọn dữ liệu authorization và token fixture. Nếu bật debug log của Spring Security hoặc HTTP client, kiểm tra log không chứa `Authorization: Basic`, Bearer token hoặc secret. Test log nên xác minh sự vắng mặt của các chuỗi bí mật đã biết.

## 13. Ma trận kiểm thử chức năng

| Nhóm | Ca kiểm thử | Kết quả mong đợi |
|---|---|---|
| Client | Client hợp lệ và được phép exchange | Request được xử lý |
| Client | Secret sai hoặc client không được phép | Từ chối, không cấp token |
| Subject | Token đúng issuer/chữ ký/audience/thời hạn | Có thể tiếp tục đánh giá policy |
| Subject | Token sai chữ ký, issuer, audience, hết hạn hoặc revoke | Từ chối exchange |
| Actor | Actor token hợp lệ và được ủy quyền | Token đầu ra biểu diễn delegation đúng |
| Actor | Actor không hợp lệ hoặc không có quan hệ với subject | Từ chối |
| Scope | Scope nằm trong giao policy | Token chỉ có scope được phép |
| Scope | Scope vượt quyền subject/client/resource | Từ chối hoặc thu hẹp theo policy đã chọn |
| Audience | Audience đích trong allowlist | Token có đúng audience đích |
| Audience | Audience ngoài allowlist hoặc nhiều audience có giá trị lạ | Từ chối theo policy; không cấp token rộng |
| Token response | Loại token và thời hạn đúng | Response và token claims khớp nhau |
| Resource Server | Token đúng audience và scope | Endpoint được phép truy cập |
| Resource Server | Sai audience hoặc thiếu scope | Lần lượt trả 401 hoặc 403 theo loại lỗi |
| Persistence | Request thất bại | Không lưu authorization/token mới |
| Audit | Exchange thành công/thất bại | Có event đủ truy vết, không lộ token |

## 14. Checklist hoàn thành

- [ ] Đã xác định client nào được phép Token Exchange và grant đã được xử lý thực sự ở token endpoint.
- [ ] Subject token được xác minh chữ ký hoặc introspection, issuer, audience, thời hạn và trạng thái.
- [ ] Actor token và quan hệ delegation được xác minh nếu luồng có actor.
- [ ] Audience/resource đích chỉ lấy từ allowlist policy phía server.
- [ ] Scope token mới không vượt quyền subject, client và resource đích.
- [ ] Thời hạn token mới tuân theo giới hạn delegation và thời gian còn lại của token đầu vào.
- [ ] Token response, JWT/introspection claims và authorization persistence nhất quán.
- [ ] Resource Server xác minh issuer, audience và scope; test đủ cả 401 và 403.
- [ ] Các trường hợp âm tính không tạo token hoặc authorization mới.
- [ ] Test concurrency và nhiều instance nếu policy có quota hoặc persistence phân tán.
- [ ] Log/audit không chứa token, secret hoặc credential thô.

Một bộ kiểm thử Token Exchange đáng tin cậy xác minh toàn bộ đường đi từ client authentication, subject/actor token validation, policy scope/audience, token generation đến Resource Server. Khi mỗi lớp đều chứng minh được quyền được giữ trong giới hạn đã định, Token Exchange mới thực sự giảm phạm vi token giữa các dịch vụ thay vì trở thành một đường cấp quyền rộng hơn.
