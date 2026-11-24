# Test revoked refresh token: kiểm thử thu hồi refresh token

## 1. Bối cảnh và mục tiêu

Trong OAuth 2.0, **refresh token** cho phép một client xin access token mới khi access token hiện tại hết hạn hoặc cần được làm mới. Refresh token thường có vòng đời dài hơn access token và có thể duy trì quyền truy cập qua nhiều lần cấp token. Khi người dùng đăng xuất, thu hồi quyền của ứng dụng, quản trị viên khóa phiên hoặc hệ thống phát hiện token bị đánh cắp, authorization server cần có khả năng **thu hồi refresh token** và từ chối mọi lần sử dụng tiếp theo theo chính sách.

Kiểm thử revoked refresh token xác minh rằng:

- Client gửi yêu cầu thu hồi đến đúng endpoint và được xác thực phù hợp.
- Authorization server đánh dấu refresh token đã thu hồi, không tiếp tục cấp access token từ token đó.
- Token rotation, phát hiện reuse và thu hồi token family hoạt động đúng theo cấu hình.
- Access token đã phát hành trước đó được xử lý theo chính sách thu hồi thực tế.
- Việc thu hồi được áp dụng nhất quán qua nhiều node, cache và resource server.
- Token không bị lộ trong log, trace, response lỗi, test report hoặc dữ liệu kiểm thử.

Bài thuộc chương **Testing token security** của module **SECURITY_TOKEN_SECURITY_FUNDAMENTALS**. Nội dung liên hệ mô hình tin cậy và vòng đời token, phân biệt JWT/opaque token, access/refresh token, OAuth 2.0/OIDC, issuer, claims, scope, audience, lưu trữ, thu hồi và phòng chống token bị đánh cắp hoặc phát lại.

Sau bài học, người học có thể:

1. Mô tả vòng đời refresh token và vị trí của thao tác revocation.
2. Phân biệt phản hồi thành công của revocation endpoint với bằng chứng token thực sự không thể dùng lại.
3. Viết kiểm thử tích hợp xác nhận refresh token đã thu hồi không thể cấp access token mới.
4. Kiểm tra token rotation, reuse detection, client binding, token family và các tình huống cạnh tranh.
5. Đánh giá ảnh hưởng của revocation lên access token đã phát hành, cache introspection và nhiều resource server.
6. Thiết kế test data, cleanup, log và báo cáo kiểm thử an toàn.

## 2. Phân biệt refresh token và access token

Refresh token và access token có mục đích khác nhau:

| Thuộc tính | Access token | Refresh token |
| --- | --- | --- |
| Mục đích | Truy cập resource server/API | Xin access token mới tại authorization server |
| Nơi gửi | Resource server có audience phù hợp | Token endpoint của authorization server |
| Quyền | Scope/audience cho API cụ thể | Quyền tiếp tục phiên/authorization grant theo policy |
| Thời hạn | Thường ngắn hơn | Thường dài hơn, có thể có idle/absolute lifetime |
| Định dạng | JWT hoặc opaque | Thường opaque; có thể là định dạng khác theo issuer |
| Bên được phép dùng | Client được cấp token và các chặng được policy cho phép | OAuth client đã được cấp và được phép lưu/refresh token |
| Rủi ro khi lộ | Kẻ tấn công có thể gọi API đến khi token hết hạn/thu hồi | Kẻ tấn công có thể liên tục xin access token mới trong phạm vi grant |

Refresh token **không** phải credential để gọi API nghiệp vụ. Không gửi refresh token đến Orders API, Inventory API hoặc downstream chỉ vì nó cũng là một chuỗi token. Resource server thường chỉ chấp nhận access token dành cho chính nó.

### 2.1. Vòng đời cơ bản

~~~mermaid
sequenceDiagram
    autonumber
    participant C as OAuth Client
    participant AS as Authorization Server
    participant RS as Resource Server

    C->>AS: Authorization grant / token request
    AS-->>C: access_token + refresh_token
    C->>RS: API request + access_token
    RS-->>C: Resource response
    Note over C: access token hết hạn
    C->>AS: grant_type=refresh_token + refresh_token
    AS->>AS: Kiểm token, client, grant, expiry và trạng thái
    AS-->>C: access_token mới (và refresh_token mới nếu rotation)
    C->>RS: API request + access_token mới
~~~

Khi người dùng đăng xuất hoặc client cần chấm dứt quyền truy cập, client có thể gọi **revocation endpoint** theo RFC 7009. Với refresh token bị thu hồi, lần refresh tiếp theo phải bị từ chối. Nếu hệ thống dùng refresh token rotation, token cũ đã dùng để đổi token mới cũng không được tiếp tục chấp nhận.

## 3. Revocation endpoint theo RFC 7009

OAuth 2.0 Token Revocation (RFC 7009) định nghĩa endpoint để client yêu cầu authorization server thu hồi token. Client gửi HTTP POST với `application/x-www-form-urlencoded`; tham số quan trọng là `token`, còn `token_type_hint` có thể chỉ rõ loại token.

Request minh họa:

~~~http
POST /oauth2/revoke HTTP/1.1
Host: auth.example.com
Content-Type: application/x-www-form-urlencoded
Authorization: Basic <client-authentication>

token=<refresh-token>&token_type_hint=refresh_token
~~~

Đây là ví dụ; đường dẫn endpoint, phương thức xác thực client và chính sách hỗ trợ phụ thuộc authorization server. Trong hệ thống thực, endpoint phải được khám phá/cấu hình từ issuer tin cậy, sử dụng HTTPS và client authentication phù hợp. Không gửi token qua URL query string.

### 3.1. Ý nghĩa phản hồi HTTP 200

Một điểm rất quan trọng khi viết test: theo RFC 7009, authorization server trả **HTTP 200** khi token đã được thu hồi hoặc token không còn hợp lệ/không được nhận diện. Thiết kế này tránh để endpoint trở thành oracle dễ dàng tiết lộ token nào đang tồn tại.

Do đó:

- HTTP 200 cho biết yêu cầu revocation được xử lý theo giao thức.
- HTTP 200 **không tự chứng minh** token vừa gửi trước đó là token hợp lệ.
- Bằng chứng quan trọng là lần sử dụng refresh token tiếp theo không còn được cấp access token mới.
- Khi authorization server không thể xử lý yêu cầu do lỗi dịch vụ, có thể trả lỗi hạ tầng như 503; client cần xử lý retry theo chính sách.

Một bài test chỉ kiểm tra `status == 200` là chưa đủ. Test phải xác minh **hành vi sau revocation** tại token endpoint.

### 3.2. Client authentication và token type hint

Revocation endpoint thường yêu cầu client xác thực theo cơ chế của OAuth server. Test cần xác minh:

- Client hợp lệ có thể thu hồi token được cấp cho client đó theo policy.
- Client khác không thể thu hồi token của client hiện tại nếu server áp dụng client binding.
- Thiếu/sai client authentication bị xử lý đúng.
- `token_type_hint=refresh_token` được gửi đúng; nếu hint không chính xác, server có thể thử nhận diện token theo quy tắc hỗ trợ.
- Token không hợp lệ/không tồn tại không làm lộ thông tin nhạy cảm qua response.

Không giả định mọi authorization server có cùng response body, error code hoặc yêu cầu xác thực. Test cần bám theo contract và cấu hình của issuer đang sử dụng.

## 4. Những gì cần xác minh sau khi thu hồi

Một kịch bản cốt lõi gồm các bước:

1. Dùng test client hợp lệ xin access token và refresh token.
2. Gọi resource server bằng access token để xác nhận token ban đầu hoạt động.
3. Gửi refresh token đến revocation endpoint với client authentication hợp lệ.
4. Kiểm tra phản hồi revocation theo contract, thường là HTTP 200.
5. Gửi refresh token đã thu hồi đến token endpoint với `grant_type=refresh_token`.
6. Xác minh authorization server từ chối, thường là OAuth error `invalid_grant`, và **không phát hành access token mới**.
7. Nếu có rotation hoặc token family, kiểm tra cả token cũ, token mới và chính sách reuse.

~~~mermaid
sequenceDiagram
    autonumber
    participant T as Integration Test
    participant AS as Authorization Server
    participant RS as Resource Server

    T->>AS: Xin token bằng test client
    AS-->>T: access_token A + refresh_token R1
    T->>RS: Gọi API với access_token A
    RS-->>T: 200 OK
    T->>AS: POST revoke token=R1
    AS-->>T: 200 OK
    T->>AS: POST token grant_type=refresh_token, token=R1
    AS->>AS: Phát hiện R1 đã thu hồi
    AS-->>T: invalid_grant
    Note over T,AS: Không có access token mới được cấp
~~~

Kết quả mong đợi của bước refresh là thất bại theo contract của token endpoint. Với OAuth 2.0, `invalid_grant` thường được dùng khi refresh token không hợp lệ, hết hạn, bị thu hồi hoặc không thể dùng trong grant hiện tại. Không chỉ kiểm tra HTTP 400; hãy xác minh error code và không có token trong response.

## 5. Phân biệt revocation của refresh token với access token đang tồn tại

Thu hồi refresh token ngăn client dùng token đó để xin access token mới. Việc này **không tự động bảo đảm mọi access token đã phát hành trước đó lập tức bị từ chối** ở tất cả resource server.

| Cách resource server xác minh access token | Tác động có thể thấy sau khi refresh token bị thu hồi |
| --- | --- |
| JWT xác minh offline chỉ dựa vào chữ ký và `exp` | JWT đã phát hành có thể vẫn hợp lệ đến `exp`, trừ khi có denylist, grant/session version hoặc cơ chế kiểm tra thu hồi bổ sung. |
| Opaque token qua introspection | Authorization server có thể trả `active=false` nếu access token liên quan cũng bị vô hiệu hóa; cache introspection có thể tạo độ trễ. |
| JWT có kiểm tra trạng thái phiên/grant tập trung | Có thể từ chối sớm khi session/grant bị revoke, tùy kiến trúc và độ sẵn sàng của nguồn trạng thái. |
| Resource server dùng cache riêng | Có thể tiếp tục chấp nhận kết quả cũ đến khi cache hết hạn hoặc được invalidated. |

RFC 7009 mô tả quan hệ thu hồi giữa refresh token và các access token dựa trên cùng authorization grant; cách triển khai cần tuân theo yêu cầu của RFC và contract của authorization server. Tuy nhiên, resource server xác minh JWT hoàn toàn offline không tự biết trạng thái thu hồi nếu không có cơ chế phân phối trạng thái. Vì vậy test phải tách hai khẳng định:

- **Khẳng định A:** refresh token đã thu hồi không thể được dùng để xin access token mới.
- **Khẳng định B:** access token cũ không còn được resource server chấp nhận.

Khẳng định B chỉ được đưa vào test nếu hệ thống đã thiết kế và cấu hình cơ chế thu hồi access token tương ứng. Nếu access token JWT được thiết kế sống đến hết hạn, expected result có thể là token cũ vẫn được chấp nhận trong khoảng thời gian còn hiệu lực, trong khi refresh token đã bị chặn.

## 6. Refresh token rotation và reuse detection

Với **refresh token rotation**, mỗi lần refresh thành công, authorization server phát hành refresh token mới và vô hiệu hóa refresh token cũ:

~~~mermaid
flowchart TD
    R1[Refresh token R1] -->|Refresh thành công| A1[Access token A1]
    R1 -->|Rotation| R2[Refresh token R2]
    R2 -->|Refresh thành công| A2[Access token A2]
    R2 -->|Rotation| R3[Refresh token R3]
    R1 -->|Dùng lại R1 cũ| D[Reuse detection]
    D --> F[Thu hồi token family theo policy]
~~~

Rotation giúp giảm giá trị của token bị đánh cắp: sau khi R1 được dùng thành công, client chỉ nên giữ R2. Nếu kẻ tấn công hoặc một bản client cũ tiếp tục dùng R1, authorization server có thể phát hiện reuse và thu hồi token family/grant theo chính sách.

Không phải hệ thống nào cũng bật rotation hoặc reuse detection. Test phải đọc cấu hình/contract đã được chọn; không được mặc định một lần dùng token cũ luôn thu hồi toàn bộ session ở mọi nhà cung cấp.

### 6.1. Các trường hợp cần test

| Kịch bản | Kết quả mong đợi khi rotation được bật |
| --- | --- |
| Dùng R1 lần đầu | Refresh thành công; nhận access token mới và R2. |
| Dùng lại R1 sau rotation | Bị từ chối; phát hiện reuse nếu server hỗ trợ. |
| Dùng R2 sau khi R1 đã được thay thế | Thành công nếu R2 vẫn còn hiệu lực và chưa bị revoke. |
| Thu hồi R2 | Refresh bằng R2 bị từ chối. |
| Dùng R3 sau khi token family đã bị revoke do reuse | Bị từ chối nếu policy thu hồi toàn family. |
| Refresh token thuộc client khác | Bị từ chối theo client binding. |

### 6.2. Kiểm thử cạnh tranh (race condition)

Hai request đồng thời dùng cùng R1 có thể xảy ra khi hai tab, hai thread hoặc hai replica cùng refresh. Hệ thống cần có semantics rõ ràng:

- Với rotation nghiêm ngặt, chỉ một request có thể thành công; request còn lại có thể bị coi là reuse.
- Một số hệ thống hỗ trợ grace period ngắn để xử lý retry do mạng; khi đó cần kiểm thử đúng khoảng grace và quy tắc trả lại token mới.
- Client phải serialize thao tác refresh hoặc có cơ chế phối hợp để không vô tình gửi cùng refresh token đồng thời.

Không viết test race chỉ dựa vào sleep cố định rồi hy vọng hai request chạy cùng lúc. Dùng barrier/latch hoặc cơ chế đồng bộ test để tạo tình huống cạnh tranh lặp lại được; kiểm tra kết quả và trạng thái token family sau cả hai request.

## 7. Thiết kế test fixture và dữ liệu an toàn

Một test tích hợp tốt tạo token riêng cho mỗi test hoặc mỗi test class, dùng OAuth client chuyên dụng và resource server test. Không dùng token người dùng thật, tài khoản production hoặc client secret thật.

Fixture nên quản lý:

| Dữ liệu | Cách tạo và sử dụng |
| --- | --- |
| OAuth client | Client test riêng, quyền giới hạn; secret/key được inject từ môi trường test. |
| User/test subject | Tài khoản giả lập hoặc subject chuyên dụng; chỉ cấp scope cần thiết. |
| Refresh token | Xin từ authorization server trong test; giữ trong memory của test runner khi có thể. |
| Access token | Lấy cùng grant; dùng để kiểm tra API trước/sau revocation nếu kịch bản yêu cầu. |
| Revocation endpoint | Lấy từ cấu hình/metadata issuer tin cậy; không suy ra bằng cách nối URL tùy tiện. |
| Token family/session reference | Chỉ lưu ID tham chiếu không nhạy cảm nếu server cung cấp, không lưu raw token vào report. |
| Cleanup | Thu hồi token/grant hoặc xóa dữ liệu fixture sau test; cleanup phải chạy cả khi assertion thất bại. |

Nếu authorization server không hỗ trợ xóa fixture trực tiếp, dùng tenant/client test cô lập và TTL ngắn. Không đưa refresh token vào exception message hoặc assertion failure; chỉ in một mã test reference không bí mật.

### 7.1. Cô lập giữa các test

- Mỗi test có token riêng để tránh test thu hồi ảnh hưởng test khác.
- Không chạy song song hai test cùng thao tác một refresh token, trừ test race được thiết kế có chủ đích.
- Reset trạng thái mock/stub, clock và cache giữa các test.
- Nếu dùng shared authorization server test, tạo subject/client namespace riêng theo run ID.
- Đảm bảo cleanup idempotent; thu hồi token đã thu hồi trước đó không làm cleanup thất bại.

## 8. Test matrix cho revoked refresh token

| ID | Kịch bản | Bước chính | Kết quả mong đợi |
| --- | --- | --- | --- |
| RT-001 | Revocation cơ bản | Xin R1, revoke R1, refresh R1 | Revocation endpoint xử lý; refresh bị từ chối, không cấp token mới. |
| RT-002 | Token đã revoke gửi lại endpoint | Revoke R1 lần nữa | Phản hồi không tiết lộ trạng thái token; theo RFC thường vẫn 200. |
| RT-003 | Token không tồn tại | Gửi chuỗi token giả tới revoke | Không lộ thông tin token có tồn tại hay không; không phát hành token. |
| RT-004 | Token hết hạn | Xin token ngắn hạn, chờ/điều khiển clock hết hạn | Refresh bị từ chối; response không chứa credential mới. |
| RT-005 | Client không đúng | Dùng client B refresh token được cấp cho client A | Từ chối theo client binding. |
| RT-006 | Client auth sai tại revoke | Gửi revoke thiếu/sai credential | Không thu hồi trái phép; trả lỗi xác thực theo contract. |
| RT-007 | Sai token type hint | Hint không phù hợp với token | Server xử lý theo quy tắc nhận diện token; không lộ trạng thái nhạy cảm. |
| RT-008 | Refresh token rotation | R1 refresh thành công, nhận R2, thử lại R1 | R1 bị từ chối/reuse detection theo cấu hình. |
| RT-009 | Revoke token mới nhất | Revoke R2, thử refresh R2 | Bị từ chối, không cấp token tiếp theo. |
| RT-010 | Reuse detection | Dùng R1 cũ sau rotation | Phát hiện reuse; family bị revoke nếu policy quy định. |
| RT-011 | Hai refresh đồng thời | Gửi hai request dùng cùng R1 | Kết quả phù hợp semantics rotation/grace; không có hai nhánh token family không kiểm soát. |
| RT-012 | Access token cũ | Revoke refresh R1 rồi gọi API bằng access token A1 | Kết quả đúng chính sách access-token revocation đã thiết kế; không suy diễn từ refresh failure. |
| RT-013 | Introspection sau revoke | Revoke grant rồi introspect access token liên quan | `active` phản ánh trạng thái theo policy; đo và ghi nhận độ trễ cache. |
| RT-014 | Multi-node | Revoke qua node A, refresh qua node B | Node B cũng từ chối sau độ trễ đồng bộ được cam kết. |
| RT-015 | Logout | Client logout/revoke token | Refresh token không dùng lại được; cookie/session client được xử lý theo ứng dụng. |
| RT-016 | User disabled | Khóa subject hoặc thu hồi consent/grant | Refresh bị từ chối theo policy; audit có reason code phù hợp. |
| RT-017 | Scope/resource thay đổi | Quyền grant bị giảm trước lần refresh | Token mới không giữ scope/resource đã bị thu hồi. |
| RT-018 | Log hygiene | Kiểm log, trace, APM, test output | Không có raw refresh token, access token, client secret hoặc Authorization header. |
| RT-019 | STS unavailable | Revocation endpoint timeout/5xx | Client không báo logout/revocation chắc chắn thành công; retry/hiển thị trạng thái theo policy. |
| RT-020 | Cleanup sau test lỗi | Cố ý làm assertion thất bại | Fixture vẫn được dọn hoặc có quy trình cleanup an toàn. |

## 9. Ví dụ HTTP test thủ công

Các ví dụ dưới đây dùng placeholder. Không copy token thật vào terminal history hoặc tài liệu chia sẻ.

### 9.1. Xin token trong môi trường test

~~~http
POST /oauth2/token HTTP/1.1
Host: auth.test.example
Content-Type: application/x-www-form-urlencoded
Authorization: Basic <test-client-auth>

grant_type=authorization_code&code=<one-time-test-code>&redirect_uri=https%3A%2F%2Fclient.test%2Fcallback
~~~

Giả sử response có `refresh_token=R1` và `access_token=A1`. Trong test tự động, giữ các giá trị này trong memory và tránh in chúng ra console.

### 9.2. Thu hồi refresh token

~~~http
POST /oauth2/revoke HTTP/1.1
Host: auth.test.example
Content-Type: application/x-www-form-urlencoded
Authorization: Basic <test-client-auth>

token=<R1>&token_type_hint=refresh_token
~~~

Theo RFC 7009, response HTTP 200 không xác nhận R1 trước đó có hợp lệ hay không. Bước tiếp theo mới kiểm chứng trạng thái sử dụng.

### 9.3. Thử refresh lại token đã thu hồi

~~~http
POST /oauth2/token HTTP/1.1
Host: auth.test.example
Content-Type: application/x-www-form-urlencoded
Authorization: Basic <test-client-auth>

grant_type=refresh_token&refresh_token=<R1>
~~~

Expected result: token endpoint trả lỗi OAuth phù hợp, thường là `invalid_grant`; response không có `access_token` mới. Không chấp nhận trường hợp server trả HTTP 200 cùng token mới từ R1 đã thu hồi.

## 10. Ví dụ kiểm thử tích hợp Java/JUnit

Đoạn mã sau là pseudocode theo phong cách JUnit 5. Các helper `testIssuer`, `tokenClient` và `tokenResponse` đại diện cho adapter HTTP của test suite; không phải API chuẩn của Spring hoặc OAuth.

~~~java
class RefreshTokenRevocationIT {

    @Test
    void revokedRefreshTokenCannotMintAnotherAccessToken() {
        // Tạo grant mới trong issuer test, không dùng credential production.
        TokenResponse issued = testIssuer.issueTokensForTestClient();
        String refreshToken = issued.refreshToken();

        // Xác nhận refresh token ban đầu dùng được.
        TokenResponse firstRefresh =
            tokenClient.refresh(issued.client(), refreshToken);
        assertThat(firstRefresh.accessToken()).isNotBlank();

        // Nếu issuer bật rotation, lần refresh trên có thể trả refresh token mới.
        // Kịch bản revoke phải thu hồi token hiện hành của test.
        String currentRefresh = firstRefresh.refreshToken() != null
            ? firstRefresh.refreshToken()
            : refreshToken;

        RevocationResponse revoked =
            tokenClient.revoke(issued.client(), currentRefresh, "refresh_token");
        assertThat(revoked.httpStatus()).isEqualTo(200);

        // HTTP 200 ở revoke endpoint chưa đủ; kiểm tra hành vi sử dụng lại.
        OAuthError error = tokenClient.refreshExpectingError(
            issued.client(), currentRefresh);
        assertThat(error.error()).isEqualTo("invalid_grant");
        assertThat(error.accessToken()).isNull();
    }
}
~~~

Nếu muốn kiểm tra thu hồi ngay refresh token ban đầu, không refresh nó trước; chỉ cần issue → revoke → refresh lại. Ví dụ trên có bước refresh đầu tiên để minh họa rotation và phải revoke token hiện hành trả về từ lần refresh đó. Test cần được điều chỉnh theo semantics chính xác của issuer.

### 10.1. Kiểm tra access token cũ riêng biệt

~~~java
@Test
void refreshRevocationAndExistingAccessTokenHaveSeparateExpectations() {
    TokenResponse tokens = testIssuer.issueTokensForTestClient();

    tokenClient.revoke(tokens.client(), tokens.refreshToken(), "refresh_token");

    OAuthError refreshError =
        tokenClient.refreshExpectingError(tokens.client(), tokens.refreshToken());
    assertThat(refreshError.error()).isEqualTo("invalid_grant");

    // Expected phụ thuộc cách resource server kiểm tra trạng thái access token.
    // JWT offline có thể còn hợp lệ đến exp; opaque/introspection hoặc denylist
    // có thể từ chối sớm theo chính sách revocation của hệ thống.
    ResourceResult oldAccessResult =
        resourceClient.callWithBearer(tokens.accessToken());
    assertThat(oldAccessResult.status())
        .isIn(testPolicy.expectedStatusesForPreviouslyIssuedAccessToken());
}
~~~

Không để assertion `isIn(...)` chung chung trong test production. Thay nó bằng expected status cụ thể từ thiết kế: ví dụ 200 nếu JWT offline còn hạn và hệ thống chấp nhận tới `exp`, hoặc 401 nếu có cơ chế thu hồi access token đã được triển khai. Mục đích của ví dụ là nhấn mạnh hai hợp đồng cần test riêng.

## 11. Test phân tán, cache và nhất quán trạng thái

Authorization server thường chạy nhiều instance. Refresh token có thể được lưu trong database, cache hoặc token store; revocation có thể phát sự kiện để các node cập nhật trạng thái. Test cần xác minh:

1. Revoke qua node A rồi refresh qua node B: token phải bị từ chối theo giới hạn đồng bộ đã cam kết.
2. Cache token lookup hoặc session state được invalidated đúng; không có node tiếp tục chấp nhận token đã thu hồi vô thời hạn.
3. Khi database/replication hoặc event bus chậm, hệ thống có hành vi fail-safe theo policy; không mặc định token còn hiệu lực chỉ vì node chưa nhận sự kiện.
4. Restart node không làm token đã revoke sống lại do trạng thái chỉ nằm trong memory.
5. Clock skew không khiến token hết hạn hoặc thời điểm revocation bị diễn giải sai.

Nếu hệ thống cho phép một khoảng thời gian lan truyền revocation, ghi rõ **SLO/maximum propagation delay** và kiểm tra đúng giới hạn. Không viết test mong đợi đồng bộ tức thì nếu kiến trúc không cam kết điều đó; cũng không chấp nhận độ trễ vô hạn.

### 11.1. Cache introspection tại resource server

Với opaque access token, resource server có thể cache kết quả introspection. Khi grant bị revoke, cache `active=true` cũ có thể khiến access token tiếp tục được chấp nhận đến khi TTL hết. Test nên:

- Đo thời gian từ revoke tới lúc introspection trả `active=false`.
- Đo thời gian từ revoke tới khi resource server từ chối request.
- Kiểm tra cơ chế invalidation chủ động nếu có.
- Đảm bảo TTL và độ trễ phù hợp yêu cầu rủi ro.

Không dùng kết quả introspection cache làm bằng chứng refresh token còn được phép refresh. Hai endpoint/loại credential có semantics riêng.

## 12. Các lỗi kiểm thử thường gặp

| Lỗi | Vì sao không đủ | Cách sửa |
| --- | --- | --- |
| Chỉ assert revoke endpoint trả 200 | 200 có thể được trả cả khi token không hợp lệ/không tồn tại | Thử refresh lại và xác nhận bị từ chối. |
| Chỉ thử token hết hạn | Hết hạn khác với bị thu hồi | Dùng token còn hạn, revoke rõ ràng rồi refresh. |
| Thu hồi access token nhưng kết luận refresh token cũng bị revoke | Nhầm loại token và quan hệ grant | Test riêng từng token và policy liên kết. |
| Giả định access token cũ lập tức invalid | JWT offline có thể còn hợp lệ tới `exp` | Kiểm tra kiến trúc revocation thực tế và viết expected riêng. |
| Dùng cùng refresh token cho nhiều test | Test tác động lẫn nhau, kết quả không ổn định | Tạo token mới cho mỗi test. |
| Bỏ qua token rotation | Test token cũ nhưng không kiểm token mới/family | Test R1 → R2, reuse R1, revoke R2 và trạng thái family. |
| Chạy song song không kiểm soát | Race ngẫu nhiên gây flaky test | Dùng barrier/latch và xác định semantics cạnh tranh. |
| Ghi token ra console khi fail | Credential tồn tại trong log CI | Redact token và chỉ log test reference. |
| Chỉ test một node | Node khác có thể tiếp tục chấp nhận token | Test multi-node, cache, restart và propagation. |
| Mock toàn bộ authorization server | Không xác minh semantics revoke thật | Có integration test với issuer test/staging ngoài unit test. |
| Cleanup không chạy khi assertion lỗi | Test data và token còn tồn tại | Dùng `try/finally`, teardown hoặc disposable tenant. |

## 13. Bảo mật dữ liệu và vận hành test

Refresh token là credential có giá trị cao. Test suite phải bảo vệ nó như secret:

- Dùng authorization server test/staging, OAuth client và subject chuyên dụng.
- Không dùng token hoặc client secret production.
- Không đặt token trong source code, fixture version control, command-line argument dễ bị ghi history hoặc test snapshot.
- Không log HTTP body của token endpoint/revocation endpoint; cấu hình proxy/APM để scrub `Authorization`, `refresh_token`, `access_token` và `token`.
- Không đưa token vào assertion message; nếu cần đối chiếu, dùng ID fixture không nhạy cảm.
- Giới hạn quyền truy cập artifact CI và thời gian lưu report.
- Thu hồi token fixture sau test; cleanup phải idempotent và có cảnh báo nếu không hoàn tất.
- Khi test thất bại, tránh chụp request/response chứa token vào screenshot hoặc bug report.

Nếu cần kiểm tra nội dung token JWT, chỉ làm trong test cô lập với token giả lập và không lưu nguyên chuỗi token. Đối với refresh token opaque, không cố parse token để suy luận trạng thái; kiểm tra qua endpoint và hành vi token endpoint.

## 14. Checklist hoàn thành kiểm thử

- [ ] Test tạo refresh token còn hiệu lực từ OAuth client test riêng.
- [ ] Test xác nhận token ban đầu có thể refresh trước khi revoke.
- [ ] Test gọi revocation endpoint bằng HTTPS và client authentication phù hợp.
- [ ] Test hiểu đúng HTTP 200 của RFC 7009; không coi riêng status đó là bằng chứng đủ.
- [ ] Test refresh lại token đã thu hồi và xác nhận không có access token mới.
- [ ] Test refresh token hết hạn, sai client, không tồn tại và đã revoke.
- [ ] Test rotation, reuse detection, token family và refresh đồng thời nếu tính năng được bật.
- [ ] Test access token đã phát hành theo chính sách riêng; không đồng nhất với refresh token.
- [ ] Test introspection cache, nhiều node, restart và độ trễ lan truyền revocation.
- [ ] Test scope/resource/consent bị thay đổi không được cấp lại trái policy.
- [ ] Test không rò token qua log, trace, APM, exception, report và artifact CI.
- [ ] Test cleanup và cô lập dữ liệu giữa các lần chạy.

## 15. Kết luận và tài liệu tham khảo

Một kiểm thử **revoked refresh token** chỉ hoàn chỉnh khi chứng minh được token đã thu hồi không thể tiếp tục được dùng để cấp access token mới. HTTP 200 ở revocation endpoint là phản hồi giao thức, không đủ để kết luận token đã tồn tại và được thu hồi. Hãy kiểm tra hành vi refresh sau revocation, kiểm tra rotation/reuse nếu được bật, và đánh giá access token cũ theo cơ chế thu hồi thực tế của resource server.

Điều quan trọng là tách ba trạng thái: **refresh token bị thu hồi**, **access token đã phát hành**, và **phiên/authorization grant**. Chúng có quan hệ nhưng không thể mặc định mọi hệ thống cập nhật đồng thời hoặc theo cùng một cách. Test cần bám theo contract của issuer, policy của ứng dụng và độ trễ nhất quán đã cam kết.

Tài liệu tiêu chuẩn liên quan:

- **RFC 7009 — OAuth 2.0 Token Revocation:** endpoint thu hồi token, client authentication và phản hồi.
- **RFC 6749 — OAuth 2.0 Authorization Framework:** refresh token grant và xử lý lỗi `invalid_grant`.
- **RFC 6750 — OAuth 2.0 Bearer Token Usage:** sử dụng access token ở resource server.
- **RFC 7662 — OAuth 2.0 Token Introspection:** kiểm tra trạng thái active của opaque access token.
- **RFC 9700 — Best Current Practice for OAuth 2.0 Security:** khuyến nghị bảo vệ refresh token, rotation và phát hiện reuse.
- **OpenID Connect Core:** ngữ cảnh phiên đăng nhập và token trong hệ thống OIDC.
