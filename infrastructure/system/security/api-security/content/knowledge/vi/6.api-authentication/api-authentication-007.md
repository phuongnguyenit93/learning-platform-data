# Không coi API key là đủ cho tài nguyên nhạy cảm

API key là một cách đơn giản để nhận diện ứng dụng hoặc tích hợp đang gọi API. Tuy nhiên, một API key thường là chuỗi bí mật tĩnh: bất kỳ ai lấy được key đều có thể gửi request bằng danh tính của ứng dụng được gắn với key đó. Key không tự chứng minh người dùng cuối là ai, người đó có quyền gì trên một bản ghi cụ thể, hay thao tác có phù hợp với ngữ cảnh nghiệp vụ hay không.

Vì vậy, API key có thể hữu ích cho API công khai, quota, phân biệt đối tác hoặc một số tác vụ tự động có rủi ro thấp. Với dữ liệu cá nhân, tài chính, thông tin nội bộ, thao tác ghi/xóa, quản trị hoặc tài nguyên thuộc nhiều tenant, không nên coi việc gửi đúng API key là đủ để cấp quyền. Cần chọn cơ chế xác thực phù hợp với loại client và độ nhạy tài nguyên, sau đó kiểm tra quyền chức năng, quyền trên từng đối tượng và điều kiện nghiệp vụ ở server.

## 1. API key thực sự chứng minh điều gì?

API key thường là một giá trị ngẫu nhiên do nhà cung cấp API phát hành cho một ứng dụng, đối tác hoặc project. Client gửi key trong request để server tra cứu bản ghi key, xác định ứng dụng và áp dụng chính sách gắn với key đó.

Ví dụ:

```http
GET /v1/catalog/products HTTP/1.1
Host: api.example.test
X-API-Key: <api-key>
Accept: application/json
```

Server có thể tra cứu key để biết request đến từ tích hợp `partner-catalog-01`, kiểm tra key còn hiệu lực và áp quota. Nhưng kết quả đó chỉ cho biết request đang sở hữu một bí mật được cấp cho tích hợp này. Nó không tự trả lời:

- Người đang sử dụng ứng dụng đối tác là người dùng nào?
- Người dùng đó đã đăng nhập và được xác thực bằng phương thức nào?
- Người dùng có quyền đọc hồ sơ, hóa đơn hoặc giao dịch cụ thể nào?
- Người dùng có thuộc tenant sở hữu dữ liệu được yêu cầu không?
- Thao tác có cần MFA, xác nhận giao dịch hoặc phê duyệt bổ sung không?

### 1.1. API key là thông tin xác thực dạng bearer

Phần lớn API key hoạt động theo mô hình *bearer secret*: bên nào sở hữu giá trị key có thể trình nó để được nhận diện như client đã đăng ký. Nếu key bị sao chép khỏi log, source code, trình duyệt hoặc máy build, kẻ tấn công có thể phát lại request từ một máy khác.

Key đủ dài và được sinh ngẫu nhiên giúp khó đoán, nhưng entropy cao chỉ giảm nguy cơ dò tìm. Nó không ngăn việc key bị lấy cắp rồi sử dụng hợp lệ theo giao thức. HTTPS bảo vệ key trên đường truyền giữa các điểm TLS, nhưng không ngăn key bị lộ ở endpoint client, log, proxy, thiết bị đã nhiễm mã độc hoặc kho mã nguồn.

### 1.2. Phân biệt API key với các loại danh tính khác

| Cơ chế | Thường đại diện cho | Điều cần kiểm tra thêm |
|---|---|---|
| API key | Ứng dụng, project hoặc tích hợp | Quyền của ứng dụng, quota, trạng thái key và phạm vi API |
| Mật khẩu người dùng | Người dùng đăng nhập | MFA, trạng thái tài khoản, session và quyền nghiệp vụ |
| Session cookie | Phiên đăng nhập của người dùng | Chữ ký/trạng thái session, CSRF, thời hạn và quyền đối tượng |
| OAuth 2.0 access token | Client hoặc người dùng được cấp quyền truy cập | Issuer, audience, expiry, scope, subject và authorization tại tài nguyên |
| OpenID Connect ID token | Kết quả xác thực người dùng cho client | Issuer, audience, nonce và mục đích sử dụng; không dùng thay access token cho API |
| mTLS client certificate | Workload/client sở hữu private key tương ứng | Danh tính workload, trạng thái chứng thư và quyền được cấp |
| Chữ ký request/HMAC | Bên có khóa ký request | Xác minh chữ ký, timestamp, nonce, body và chống phát lại |

Các cơ chế có thể kết hợp với nhau. Ví dụ một đối tác có thể dùng mTLS để chứng minh danh tính workload, OAuth 2.0 để mang quyền của client, và một access token được ủy quyền để truy cập API. Không nên suy luận rằng dùng nhiều header xác thực tự động tạo ra bảo mật mạnh hơn; mỗi cơ chế phải có mục đích, ranh giới tin cậy và cách kiểm tra rõ ràng.

## 2. Vì sao API key không đủ cho tài nguyên nhạy cảm?

### 2.1. Key bị lộ có thể bị phát lại

Nếu API key là bí mật tĩnh và không ràng buộc với thiết bị hoặc khóa riêng, kẻ tấn công có thể sao chép key rồi gọi API từ nơi khác. Giới hạn IP có thể giảm một số tình huống nhưng không phải bằng chứng danh tính chắc chắn: IP có thể dùng chung qua NAT, thay đổi theo mạng, hoặc chính máy được allowlist đã bị xâm nhập.

### 2.2. Không phân biệt người dùng cuối

Một ứng dụng mobile hoặc frontend web có thể được hàng nghìn người dùng cài đặt. Nếu tất cả cùng chứa một API key, server chỉ nhìn thấy cùng một client key. Server khó biết request nào do người dùng A hay B tạo ra nếu ứng dụng không có một cơ chế xác thực người dùng riêng.

Điều này làm yếu khả năng phân quyền, kiểm toán và thu hồi. Khi một người dùng rời tổ chức, không thể thu hồi riêng quyền của người đó bằng cách xoay vòng một key đang được cả ứng dụng sử dụng.

### 2.3. Khó giới hạn quyền theo người dùng và đối tượng

API key thường gắn với một tích hợp, không phải từng tài khoản, hồ sơ hoặc bản ghi. Nếu endpoint chỉ kiểm tra key rồi truy vấn theo `accountId` do client gửi, người gọi có thể thử ID của người khác. Đây là dạng Broken Object Level Authorization (BOLA/IDOR).

Một key hợp lệ không đồng nghĩa với quyền đọc mọi đơn hàng, tài liệu hoặc tenant. Server phải lấy principal từ cơ chế xác thực phù hợp và kiểm tra quan hệ giữa principal với đối tượng dữ liệu ở mỗi endpoint.

### 2.4. Quyền của key dễ trở nên quá rộng

Để tránh làm gián đoạn tích hợp, đội vận hành có thể cấp một key lâu dài với quyền đọc/ghi/quản trị rộng. Khi key bị lộ, phạm vi ảnh hưởng cũng rộng theo. Nếu nhiều ứng dụng hoặc môi trường dùng chung key, rất khó xác định nguồn request và thu hồi riêng một client.

### 2.5. Thiếu ngữ cảnh xác thực và chống gian lận

API key không tự cho biết người dùng đã thực hiện MFA gần đây hay chưa, thiết bị có đáng tin không, giao dịch có được người dùng xác nhận không, hoặc có dấu hiệu chiếm tài khoản hay không. Với thao tác chuyển tiền, đổi thông tin nhận tiền, xuất dữ liệu lớn hoặc thay đổi quyền, hệ thống có thể cần xác thực tăng cường (step-up authentication) và kiểm tra rủi ro theo ngữ cảnh.

## 3. Phân loại tài nguyên trước khi chọn cơ chế xác thực

Không phải endpoint nào cũng cần cùng mức xác thực. Hãy phân loại dữ liệu và thao tác theo tác động nếu một credential bị lộ.

| Mức | Ví dụ tài nguyên/thao tác | Hướng thiết kế thường phù hợp |
|---|---|---|
| Công khai | Danh mục sản phẩm công khai, tài liệu API, dữ liệu không nhạy cảm | Có thể không cần xác thực; API key chỉ dùng để quota/nhận diện client nếu cần |
| Hạn chế | Dữ liệu đối tác, trạng thái tích hợp, thông tin vận hành không chứa dữ liệu cá nhân nhạy cảm | Danh tính client rõ ràng, key riêng, scope hẹp, quota và giám sát |
| Nhạy cảm | Hồ sơ cá nhân, đơn hàng riêng tư, hóa đơn, dữ liệu khách hàng, báo cáo nội bộ | Xác thực người dùng hoặc workload phù hợp, access token ngắn hạn, authorization theo chức năng và object/tenant |
| Rất nhạy cảm/ảnh hưởng cao | Thanh toán, chuyển tiền, thay đổi người thụ hưởng, quản trị, xuất dữ liệu hàng loạt, cấp quyền | Xác thực mạnh, step-up/MFA hoặc xác nhận giao dịch, phân tách nhiệm vụ, kiểm soát gian lận và audit |

Việc phân loại phải dựa trên tác động thực tế và quy định áp dụng. Một endpoint đọc dữ liệu có thể nhạy cảm như endpoint ghi dữ liệu nếu nó trả về thông tin cá nhân hoặc bí mật kinh doanh. Một endpoint công khai cũng có thể cần quota để ngăn lạm dụng tài nguyên, nhưng quota không phải authorization.

### Ví dụ phân loại endpoint

| Endpoint | Dữ liệu/thao tác | Có nên chỉ dựa vào API key? |
|---|---|---|
| `GET /catalog/products` | Danh mục công khai | Có thể dùng key để quota/nhận diện; không cần coi key là quyền truy cập dữ liệu riêng tư |
| `GET /partners/{id}/status` | Trạng thái tích hợp của đối tác | Key riêng của đối tác có thể là một phần xác thực; vẫn phải kiểm tra đúng partner ID và phạm vi |
| `GET /users/{id}/profile` | Hồ sơ cá nhân | Không; cần danh tính người dùng và kiểm tra quyền trên hồ sơ |
| `GET /accounts/{id}/transactions` | Giao dịch tài chính | Không; cần xác thực người dùng/workload phù hợp và kiểm tra quyền tài khoản/tenant |
| `POST /payments` | Tạo thanh toán | Không; cần quyền nghiệp vụ, giới hạn giao dịch và xác nhận bổ sung theo rủi ro |
| `PATCH /admin/users/{id}/roles` | Thay đổi quyền | Không; cần xác thực quản trị mạnh, kiểm soát chức năng/object và audit |

## 4. Chọn cơ chế xác thực phù hợp với loại client

### 4.1. Người dùng truy cập qua web hoặc mobile

Với ứng dụng có người dùng cuối, nên dùng luồng đăng nhập dựa trên OAuth 2.0/OpenID Connect phù hợp với loại client. Ứng dụng web hoặc mobile công khai thường sử dụng Authorization Code Flow với PKCE. Người dùng xác thực tại authorization server; client nhận token theo luồng đã đăng ký; API nhận access token để kiểm tra quyền.

Các điểm cần bảo đảm:

- Dùng Authorization Code + PKCE cho public client; không nhúng `client_secret` cố định vào JavaScript hoặc binary mobile.
- Xác minh issuer, audience, thời hạn, chữ ký hoặc trạng thái token theo loại token.
- Access token chỉ có scope cần thiết, đúng resource server và thời hạn phù hợp.
- Refresh token cần được bảo vệ, xoay vòng và thu hồi khi phát hiện tái sử dụng hoặc khi người dùng đăng xuất/thu hồi quyền.
- Nếu ứng dụng dùng cookie session, bảo vệ cookie bằng `Secure`, `HttpOnly`, `SameSite` phù hợp và có biện pháp CSRF.
- Với thao tác nhạy cảm, yêu cầu step-up authentication hoặc xác nhận giao dịch theo chính sách.

Không đưa API key của hệ thống vào JavaScript frontend hoặc ứng dụng mobile với kỳ vọng giữ bí mật. Mã chạy trên thiết bị người dùng có thể bị kiểm tra, trích xuất và sửa đổi. Nếu cần gọi dịch vụ bên thứ ba có secret, đặt secret ở backend của tổ chức và cho frontend gọi backend đó theo phiên người dùng đã xác thực.

### 4.2. Service-to-service hoặc đối tác máy chủ

Với workload hoặc backend đối tác, xác thực nên gắn với danh tính workload/client. Có thể dùng:

- OAuth 2.0 Client Credentials để lấy access token dành cho service, với scope và audience hẹp.
- mTLS để xác thực hai chiều giữa workload và API gateway/service.
- `private_key_jwt` hoặc cơ chế client assertion để client chứng minh quyền sở hữu private key khi lấy token.
- Workload identity hoặc credential ngắn hạn do nền tảng cấp thay cho secret tĩnh dài hạn.
- HMAC request signing cho giao thức tích hợp đặc thù, nếu có quy tắc canonicalization và chống replay rõ ràng.

Với service-to-service, không nhất thiết phải có người dùng cuối. Tuy vậy, server vẫn cần biết workload nào đang gọi, token/key được cấp quyền gì, dữ liệu nào thuộc tenant/đối tác đó và thao tác có nằm trong policy hay không. Nếu một service thay mặt người dùng thực hiện thao tác, cần mang hoặc truyền ngữ cảnh ủy quyền của người dùng theo thiết kế được tin cậy; không suy ra quyền người dùng chỉ từ client identity của service.

### 4.3. API key kết hợp với cơ chế khác

API key vẫn có thể hữu ích như một lớp nhận diện bổ sung. Ví dụ:

- API key xác định đối tác để áp quota, trong khi OAuth access token xác định quyền client/user.
- API key chọn cấu hình tích hợp, còn mTLS xác thực workload đang kết nối.
- API key phục vụ thống kê hoặc phân loại lưu lượng; authorization dữ liệu vẫn dựa trên principal riêng.

Khi kết hợp, server phải xác định rõ từng bằng chứng dùng cho mục đích nào. Không cho phép API key có quyền rộng hơn token hoặc ghi đè principal đã xác thực. Nếu hai credential mâu thuẫn, từ chối request và ghi nhận sự kiện; không tự chọn danh tính có quyền cao hơn.

## 5. Giới hạn cách sử dụng API key

Nếu API key được dùng, hãy thiết kế nó như một credential có vòng đời và phạm vi rõ ràng.

### 5.1. Cấp phát riêng và quyền tối thiểu

- Sinh key bằng bộ sinh số ngẫu nhiên mật mã, đủ entropy; tránh chuỗi dựa trên tên công ty, ID tuần tự hoặc timestamp.
- Cấp key riêng cho từng đối tác, ứng dụng, môi trường và mục đích. Không dùng chung production key cho staging hoặc cho nhiều tích hợp không liên quan.
- Gắn key với chủ sở hữu, client ID, mục đích, scope, ngày tạo, ngày hết hạn, trạng thái và người chịu trách nhiệm.
- Chỉ cấp endpoint, hành động và quota cần thiết. Key chỉ phục vụ đọc catalog không được dùng để sửa dữ liệu hoặc truy cập admin API.
- Tách quyền đọc, ghi và quản trị; giới hạn theo tenant, resource group hoặc IP/mạng nguồn khi điều đó phù hợp với mô hình triển khai.

### 5.2. Lưu trữ và truyền tải

- Chỉ gửi key qua HTTPS trong header được quy ước, chẳng hạn `X-API-Key`; không đặt trong query string, path hoặc fragment URL.
- Không nhúng key bí mật vào frontend, source map, ứng dụng mobile, file cấu hình công khai, image hoặc repository.
- Lưu key trong secret manager; cấp quyền đọc cho đúng workload và tránh in key ra terminal/log.
- Ở server, có thể lưu hash/HMAC của key thay vì giá trị gốc nếu thiết kế xác thực cho phép; dùng phần prefix/ID không bí mật để tra cứu bản ghi.
- Redact key ở application log, gateway, tracing, APM, crash report và hệ thống analytics.

Không coi header tùy chỉnh là cơ chế mã hóa. `X-API-Key` chỉ là tên header; bí mật vẫn cần được bảo vệ bằng TLS và quy trình quản lý secret.

### 5.3. Thời hạn, xoay vòng và thu hồi

Key nên có ngày hết hạn hoặc chu kỳ xem xét. Quy trình xoay vòng thường gồm phát hành key mới, cập nhật client, xác minh request đã chuyển sang key mới, sau đó thu hồi key cũ. Nếu cần thời gian chồng lấp, đặt thời hạn kết thúc và cảnh báo trước khi hết hạn.

Hệ thống cần có khả năng thu hồi key riêng lẻ mà không phải vô hiệu hóa mọi đối tác. Khi key bị lộ, coi nó đã bị xâm phạm: thu hồi hoặc vô hiệu hóa, tìm request bất thường, kiểm tra các secret downstream mà key có thể truy cập và xoay vòng các credential phụ thuộc nếu cần.

### 5.4. Giới hạn lạm dụng

Áp quota, rate limit, concurrency limit, request size, timeout và giới hạn chi phí theo client/key. Theo dõi đột biến lưu lượng, endpoint mới, IP/ASN lạ, thời điểm bất thường và tỷ lệ lỗi cao. Những biện pháp này giảm tác động khi key bị lạm dụng nhưng không thay thế xác thực hoặc phân quyền.

## 6. Kiểm tra quyền độc lập với API key

Một request đến tài nguyên nhạy cảm cần qua các lớp kiểm tra riêng biệt:

1. **Xác thực transport/client:** kết nối TLS, mTLS nếu cần, và xác minh danh tính workload/client.
2. **Xác thực principal:** xác minh access token/session hoặc cơ chế danh tính người dùng/workload phù hợp.
3. **Authorization chức năng:** principal có quyền thực hiện hành động như `invoice:read`, `payment:create` hoặc `user:role:update` không?
4. **Authorization đối tượng:** principal có quyền trên đúng invoice, account, payment, user hoặc tenant đang được yêu cầu không?
5. **Điều kiện nghiệp vụ:** trạng thái tài khoản, hạn mức, thời điểm, phê duyệt, step-up authentication và quy tắc chống gian lận có cho phép thao tác không?
6. **Giới hạn tài nguyên và audit:** request có vượt quota/rate limit không; sự kiện có được ghi nhận an toàn không?

Không tin `userId`, `tenantId`, role hoặc owner do client gửi trong body/query. Lấy principal từ cơ chế xác thực đáng tin cậy và đối chiếu với dữ liệu ở server. Mỗi endpoint đọc, cập nhật, xóa hoặc xuất dữ liệu đều cần kiểm tra quyền đối tượng.

### Ví dụ BOLA khi chỉ kiểm tra API key

Giả sử một đối tác được cấp API key để gọi API tra cứu hồ sơ khách hàng. Endpoint có dạng:

```http
GET /api/customers/C-1001/profile HTTP/1.1
X-API-Key: <partner-api-key>
```

Nếu server chỉ kiểm tra key hợp lệ rồi trả hồ sơ theo customer ID, người sở hữu key có thể thay `C-1001` thành ID của khách hàng khác. API key xác định tích hợp đối tác, nhưng không chứng minh đối tác có quyền truy cập mọi hồ sơ.

Server phải kiểm tra customer thuộc tập dữ liệu mà đối tác được ủy quyền truy cập. Nếu request thay mặt một người dùng cụ thể, cần xác thực người dùng và kiểm tra cả quyền của người dùng đó. Ví dụ pseudocode:

```java
public CustomerProfile getProfile(
        UUID customerId,
        AuthenticatedPrincipal principal) {

    Customer customer = customerRepository
            .findByIdAndTenantId(customerId, principal.tenantId())
            .orElseThrow(NotFoundException::new);

    authorizationService.requirePermission(
            principal, "customer:read", customer);

    return CustomerProfile.from(customer);
}
```

`AuthenticatedPrincipal` phải được tạo từ token/session hoặc danh tính workload đã xác minh. Nếu tích hợp đối tác có quyền truy cập theo danh sách khách hàng được ủy quyền, policy phải đối chiếu danh sách/quan hệ đó; không lấy `tenantId` tùy ý từ request để tạo phạm vi truy cập.

### Ví dụ endpoint thanh toán

Một API key đối tác có thể xác định cổng thanh toán được phép gửi request, nhưng không đủ để cho phép tạo bất kỳ giao dịch nào. Trước khi tạo thanh toán, server cần xác minh:

- Client/workload đúng đối tác và key/token còn hiệu lực.
- Người dùng hoặc hệ thống khởi tạo có quyền trên order/account liên quan.
- Số tiền, loại tiền, người thụ hưởng và trạng thái đơn hàng khớp dữ liệu server.
- Giao dịch chưa được xử lý trước đó; idempotency key được quản lý đúng để tránh tạo trùng.
- Hạn mức, risk policy, phê duyệt và step-up authentication được đáp ứng.
- Sự kiện được audit mà không ghi thông tin thẻ hoặc credential nhạy cảm.

## 7. Ví dụ mô hình xác thực trong Spring Security

Với API nhạy cảm dành cho người dùng, một hướng triển khai phổ biến là cấu hình resource server để xác minh access token, sau đó dùng service authorization để kiểm tra quyền trên đối tượng.

Ví dụ cấu hình khung:

```java
@Bean
SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
    return http
            .authorizeHttpRequests(auth -> auth
                    .requestMatchers("/api/public/**").permitAll()
                    .requestMatchers(HttpMethod.GET, "/api/accounts/**")
                        .hasAuthority("SCOPE_account:read")
                    .requestMatchers(HttpMethod.POST, "/api/payments/**")
                        .hasAuthority("SCOPE_payment:create")
                    .anyRequest().authenticated())
            .oauth2ResourceServer(oauth -> oauth.jwt())
            .build();
}
```

Đoạn cấu hình minh họa xác thực JWT và kiểm tra scope ở mức route. Nó chưa kiểm tra quyền trên từng account/payment; phần đó phải được thực hiện trong service/domain policy. Cấu hình production còn cần issuer/audience validation, quy tắc CSRF phù hợp với kiểu client, CORS đúng origin, error handling và các kiểm soát vận hành liên quan.

Nếu cần nhận diện một đối tác bằng API key, nên đặt việc tra cứu key ở một filter riêng với quyền hẹp, tạo một client/workload principal có danh tính rõ ràng. Không tự gán `ROLE_ADMIN` hoặc bỏ qua authorization chỉ vì key tồn tại. Endpoint nhạy cảm vẫn phải yêu cầu principal và scope phù hợp; với thao tác thay mặt người dùng, phải có cơ chế ủy quyền người dùng tương ứng.

## 8. Phát hiện và ứng phó khi API key bị lộ

Khi key xuất hiện trong repository, log, ticket, source map hoặc nơi không được phép, hãy coi key đã bị lộ dù chưa thấy request đáng ngờ.

1. **Xác định phạm vi:** key thuộc client nào, môi trường nào, quyền nào, endpoint và dữ liệu downstream nào có thể truy cập.
2. **Thu hồi hoặc vô hiệu hóa:** chặn key bị lộ; nếu cần duy trì dịch vụ, phát hành key mới cho đúng client và đặt thời điểm thu hồi key cũ.
3. **Điều tra:** tìm request theo key ID/client ID, IP, user agent, thời điểm, endpoint, số lượng bản ghi và các thay đổi nghiệp vụ bất thường.
4. **Đánh giá dữ liệu:** xác định có đọc, sửa, xóa hoặc xuất dữ liệu hay không; kiểm tra các hệ thống được key dùng làm cầu nối.
5. **Xoay vòng phụ thuộc:** thay secret downstream nếu key đã cho phép truy cập tới chúng hoặc có khả năng bị lộ cùng lúc.
6. **Khôi phục và giám sát:** xác minh client đã dùng key mới, key cũ bị từ chối, quota và policy được áp dụng, cảnh báo được bật.
7. **Khắc phục nguyên nhân:** xóa secret khỏi nguồn rò rỉ, bổ sung scanning/redaction, giảm quyền và cập nhật quy trình cấp phát.

Xóa key khỏi file hiện tại không làm key mất hiệu lực và cũng không xóa bản sao trong lịch sử Git, fork, artifact hoặc log. Phải thu hồi/rotate key ở nơi xác thực và đánh giá toàn bộ bản sao có thể đã bị truy cập.

### Dữ liệu nên giám sát

- Key/client ID, trạng thái, scope và chủ sở hữu; không ghi giá trị key.
- Lưu lượng theo client, endpoint, tenant, thời điểm và kết quả authorization.
- IP/ASN, user agent, vị trí mạng hoặc thiết bị bất thường theo chính sách riêng tư.
- Tỷ lệ `401`/`403`, thử key sai, request tăng đột biến và truy cập nhiều object liên tiếp.
- Các thao tác nhạy cảm như xuất dữ liệu, tạo giao dịch, thay đổi người thụ hưởng, cấp key mới hoặc thay đổi quyền.
- Sự kiện tạo, xoay vòng, thu hồi và thay đổi scope của key.

Log phục vụ điều tra phải tránh chứa raw API key, access token, cookie, mật khẩu hoặc dữ liệu nhạy cảm không cần thiết. Giới hạn quyền xem log và bảo vệ log khỏi bị sửa/xóa trái phép.

## 9. Kiểm thử bảo mật

Kiểm thử phải chứng minh API key chỉ cấp đúng phạm vi đã thiết kế và không thể thay thế danh tính người dùng hoặc quyền trên đối tượng.

| Nhóm kiểm thử | Tình huống | Kết quả mong đợi |
|---|---|---|
| Key thiếu/sai | Không gửi key, key ngẫu nhiên hoặc key sai định dạng | Từ chối xác thực client; không trả dữ liệu nhạy cảm |
| Key hết hạn/thu hồi | Dùng key đã hết hạn hoặc bị vô hiệu hóa | Request bị từ chối |
| Sai môi trường | Dùng key staging trên production | Bị từ chối |
| Sai scope | Key chỉ đọc catalog gọi endpoint ghi hoặc admin | Bị từ chối |
| Truy cập chéo tenant | Key của đối tác A yêu cầu dữ liệu thuộc đối tác B | Không truy cập được dữ liệu B |
| Thiếu danh tính người dùng | Chỉ có API key nhưng gọi endpoint yêu cầu người dùng đăng nhập | Bị từ chối hoặc yêu cầu luồng xác thực người dùng |
| BOLA/IDOR | Thay ID object trong URL/body bằng ID của người khác | Không đọc/sửa được object ngoài phạm vi |
| Key frontend | Kiểm tra bundle, source map, binary và log | Không có secret production nhúng trong client |
| Replay | Phát lại request đã ký hoặc request có credential bị sao chép | Bị chặn theo expiry/nonce/idempotency/policy thiết kế |
| Rate limit | Dùng một key gọi vượt quota/tần suất | Giới hạn được áp dụng và có sự kiện giám sát |
| Rotation | Client chuyển sang key mới rồi thử key cũ | Key mới hoạt động, key cũ bị từ chối sau thời điểm thu hồi |
| Audit | Thực hiện thao tác nhạy cảm bằng principal hợp lệ | Có log đủ truy vết nhưng không chứa raw secret |

Nên kiểm thử cả đường đi qua API gateway, reverse proxy và service. Một key bị từ chối ở ứng dụng vẫn có thể được gateway log nguyên văn; một endpoint có scope đúng vẫn có thể có lỗi BOLA ở service layer.

## 10. Checklist thiết kế trước khi phát hành

- [ ] Đã phân loại độ nhạy dữ liệu và mức ảnh hưởng của thao tác.
- [ ] Đã xác định API key đại diện cho ứng dụng/workload nào và mục đích của key.
- [ ] Không dùng API key đơn lẻ cho hồ sơ cá nhân, tài chính, quản trị hoặc thao tác ảnh hưởng cao.
- [ ] Client người dùng dùng cơ chế xác thực người dùng phù hợp; service-to-service có danh tính workload riêng.
- [ ] Access token có issuer, audience, thời hạn và scope phù hợp; refresh token được bảo vệ và có thể thu hồi.
- [ ] API key riêng cho từng client/môi trường, scope hẹp, có chủ sở hữu và quy trình rotate/revoke.
- [ ] Key không nằm trong frontend, mobile binary, URL, source code, log hoặc artifact công khai.
- [ ] Authorization kiểm tra cả quyền chức năng và quyền trên object/tenant ở server.
- [ ] Endpoint nhạy cảm có kiểm tra trạng thái, hạn mức, step-up/phê duyệt nếu nghiệp vụ yêu cầu.
- [ ] Có rate limit, quota, timeout, request size limit và cảnh báo bất thường.
- [ ] Có kiểm thử key sai/hết hạn/thu hồi, sai scope, cross-tenant, BOLA, replay và rotation.
- [ ] Log/audit không lưu raw key/token và đủ thông tin để điều tra sự cố.

API key là một công cụ nhận diện client đơn giản và hữu ích khi được giới hạn đúng mục đích. Với tài nguyên nhạy cảm, quyết định truy cập phải dựa trên danh tính người dùng hoặc workload đã xác minh, quyền chức năng, quan hệ với đối tượng dữ liệu và điều kiện nghiệp vụ. Khi key chỉ đóng vai trò một phần của mô hình xác thực, giới hạn quyền, thời hạn, khả năng thu hồi và giám sát sẽ giúp giảm thiệt hại nếu bí mật bị lộ.
