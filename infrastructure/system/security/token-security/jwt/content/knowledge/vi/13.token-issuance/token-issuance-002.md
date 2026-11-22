# Thu thập claims từ các nguồn dữ liệu được tin cậy

> **Module:** `SECURITY_TOKEN_SECURITY_JWT` — **Security - JSON Web Token (JWT)**. **Chương:** Cấp phát token. Bài học áp dụng cho hệ thống bảo mật JWT nói chung, không phụ thuộc ngôn ngữ lập trình, thư viện hay framework.

## 1. Claims là gì và tại sao nguồn dữ liệu quan trọng?

**Claim** là một phát biểu về chủ thể hoặc ngữ cảnh liên quan, được biểu diễn bằng cặp tên–giá trị trong payload của JWT. Chẳng hạn:

- `sub`: chủ thể mà token nói tới;
- `iss`: tổ chức hoặc dịch vụ phát hành token;
- `aud`: bên dự kiến nhận token;
- `exp`: thời điểm token hết hạn;
- `scope`, `roles`, `tenant_id`: những claim có thể mang thông tin quyền hoặc ngữ cảnh theo thiết kế của hệ thống.

Khi ký JWT, **issuer chịu trách nhiệm về những claim đã phát hành**. Chữ ký chỉ giúp bên nhận biết payload có bị thay đổi và xác minh nguồn ký. Chữ ký **không biến thông tin đầu vào sai, cũ hoặc không được phép cấp thành sự thật**. Vì vậy, quá trình chuẩn bị payload phải xác định claim được lấy từ đâu, ai có thẩm quyền xác nhận nó và nó còn hợp lệ tại thời điểm cấp token hay không.

Phân biệt hai khái niệm:

- **Nguồn dữ liệu đáng tin cậy:** hệ thống hoặc bằng chứng đã được xác minh về tính xác thực, tính toàn vẹn, phạm vi thẩm quyền và độ mới đối với một loại claim cụ thể.
- **Nguồn dữ liệu có thể truy cập:** hệ thống trả về dữ liệu, kể cả cơ sở dữ liệu nội bộ, header HTTP, request body hoặc một JWT nhận được từ bên ngoài. Chỉ truy cập được nguồn **không có nghĩa** dữ liệu đủ điều kiện để đưa thẳng vào JWT.

**Nguyên tắc cốt lõi:** Mỗi claim phải có **nguồn có thẩm quyền (authoritative source)** và **quy tắc phát hành** rõ ràng. Một nguồn có thể đáng tin cho tên hiển thị nhưng không có thẩm quyền cấp quyền quản trị.

## 2. Xác định nguồn có thẩm quyền theo từng claim

Không có một danh sách nguồn nào đúng cho mọi hệ thống. Bảng sau minh họa cách phân chia trách nhiệm:

| Nguồn | Dữ liệu có thể cung cấp | Điều kiện tin cậy và giới hạn |
| --- | --- | --- |
| Hệ thống danh tính nội bộ | Định danh ổn định, trạng thái tài khoản, loại chủ thể | Đã xác thực hoặc có bằng chứng hợp lệ; ánh xạ đúng bản ghi và tenant |
| Nhà cung cấp danh tính liên kết (IdP/SSO) | Định danh bên ngoài, thời điểm và phương thức xác thực | Kiểm tra đúng issuer, chữ ký, audience, thời hạn, nonce/state nếu giao thức yêu cầu; chỉ dùng các thuộc tính mà IdP có thẩm quyền xác nhận |
| Client registry / máy chủ ủy quyền | Client identity, grant được phép, audience và scope được cho phép | Quyết định từ cấu hình máy chủ; không tin client tự khai quyền |
| Hệ thống phân quyền (IAM/Policy Engine) | Quyền hiệu lực, scope được cấp, vai trò theo tài nguyên/tenant | Kiểm tra chính sách, ngữ cảnh yêu cầu, trạng thái grant; không sao chép mù quáng danh sách role |
| Directory, hệ thống tổ chức hoặc quản lý tenant | Tư cách thành viên, đơn vị, trạng thái tổ chức | Kiểm tra bản ghi còn hiệu lực và ràng buộc chính xác với chủ thể/tenant |
| Dịch vụ nghiệp vụ | Thuộc tính nghiệp vụ cần thiết cho resource server | Chỉ sử dụng nếu dịch vụ đó là nguồn chuẩn cho thuộc tính và bên nhận thật sự cần |
| Chính dịch vụ phát hành token | `iss`, `iat`, `exp`, `nbf`, `jti`, loại token, chính sách ký | Dùng cấu hình và đồng hồ đáng tin cậy của issuer |
| Client gửi yêu cầu | Scope/audience mong muốn, lựa chọn tenant, tham số luồng | **Chỉ là đề xuất/đầu vào yêu cầu**; luôn xác minh và giới hạn bởi chính sách |

Một hệ thống có thể triển khai nhiều vai trò trong cùng một dịch vụ hoặc phân tán qua nhiều hệ thống. **Nơi đặt dữ liệu không tự quyết định mức tin cậy**; cần xác định ai được quyền đưa ra sự thật cho mỗi claim.

### 2.1. Nhận diện chủ thể đã được xác minh

Không gán `sub` chỉ dựa vào `username`, email hoặc `user_id` do bên gọi tự gửi. Quy trình thông dụng là:

1. Một cơ chế xác thực phù hợp (phiên đăng nhập đã xác minh, chứng thư, grant đã được kiểm tra, assertion hợp lệ, v.v.) tạo ra **ngữ cảnh danh tính đã xác thực**.
2. Hệ thống ánh xạ danh tính ấy tới một định danh ổn định trong miền issuer; ví dụ dựa vào cặp **(external issuer, external subject)** khi dùng liên kết danh tính.
3. Kiểm tra trạng thái của chủ thể, ràng buộc tenant và quyền sử dụng luồng phát hành.
4. Chỉ sau đó lấy định danh đã chuẩn hóa để tạo `sub`.

Email và tên hiển thị có thể đổi theo thời gian hoặc trùng giữa các tổ chức; không nên mặc định chúng là khóa danh tính duy nhất. Với token dịch vụ–dịch vụ, chủ thể có thể là **client hoặc workload**, không phải một người dùng.

### 2.2. Danh tính đáng tin không đồng nghĩa quyền đáng tin

Một IdP có thể được tin để xác nhận “chủ thể A vừa đăng nhập” nhưng chưa chắc được phép quyết định “A là quản trị viên của tenant B”. Tương tự, ứng dụng có thể nhận nhóm người dùng từ directory nhưng cần một policy engine để chuyển nhóm thành quyền truy cập thực tế.

Ví dụ, hệ thống chỉ được đưa `orders:refund` vào `scope` khi đồng thời thỏa mãn các yếu tố liên quan: quyền hiệu lực của chủ thể, quyền của client, audience, grant, tenant và chính sách nghiệp vụ. Claim `role=admin` trong một request hay một token bên ngoài **không tự động trở thành role nội bộ**.

## 3. Thiết kế hợp đồng dữ liệu cho claims

Trước khi viết mã thu thập dữ liệu, nên có **claim mapping contract** (hợp đồng ánh xạ) mô tả tối thiểu:

- **Tên và ngữ nghĩa:** claim dùng để mô tả điều gì; có phải claim chuẩn của JWT, claim của một profile giao thức hay claim riêng?
- **Nguồn có thẩm quyền:** hệ thống nào được quyết định giá trị; bằng chứng nào chứng minh đã lấy từ đúng nguồn?
- **Định danh liên kết:** giá trị thuộc về chủ thể, client, tenant, phiên hay tài nguyên nào?
- **Biến đổi:** quy tắc chuẩn hóa kiểu, mã giá trị, lọc thuộc tính, hợp nhất và xử lý mâu thuẫn.
- **Độ mới:** giá trị có thể cũ tối đa bao lâu; khi nào phải tra cứu lại hoặc từ chối?
- **Quy tắc phát hành:** loại token và audience nào có thể nhận claim; claim bắt buộc hay tùy chọn; giới hạn kích thước và độ nhạy cảm.
- **Khi lỗi:** không cấp token, bỏ claim tùy chọn hay dùng cache còn hiệu lực theo chính sách nào.

Ví dụ hợp đồng rút gọn cho **access token dành cho API đơn hàng**:

| Claim | Nguồn có thẩm quyền | Xử lý trước khi phát hành |
| --- | --- | --- |
| `iss` | Cấu hình issuer | Chọn hằng số đã cấu hình, không nhận từ request |
| `sub` | Kho danh tính + ngữ cảnh đã xác thực | Ánh xạ ra định danh ổn định nội bộ |
| `aud` | Client registry + chính sách audience | Chỉ chọn API mà client được phép gọi |
| `tenant_id` | Hệ thống thành viên tổ chức | Xác minh chủ thể còn thuộc tenant được chọn |
| `scope` | Máy chủ ủy quyền/Policy Engine | Tính tập quyền hiệu lực trong grant, client, audience và tenant |
| `iat`, `exp` | Đồng hồ và chính sách issuer | Dùng mốc thời gian NumericDate (giây từ Unix epoch), giới hạn TTL |
| `jti` | Bộ tạo định danh của issuer (nếu sử dụng) | Sinh giá trị khó trùng, không lấy từ client |
| `display_name` | Profile service (nếu cần) | Chỉ thêm cho bên nhận có nhu cầu; cân nhắc thay bằng tra cứu profile |

**Không nhất thiết đưa tất cả claim lên mọi token.** Ví dụ `scope` thường có ích cho access token theo OAuth, nhưng nhiều access token khác dùng cấu trúc quyền khác. ID token dành cho client xác thực danh tính có ngữ nghĩa và tập claim khác; không sao chép cùng payload cho mọi loại token.

### 3.1. Phân biệt đầu vào do client yêu cầu và dữ kiện đã được phép cấp

Giả sử yêu cầu chứa:

~~~json
{
  "requested_tenant": "tenant-b",
  "requested_scope": "orders:read orders:refund",
  "user_id": "usr-100",
  "role": "superadmin"
}
~~~

Không có trường nào tự động chứng minh rằng client được phép hoạt động ở `tenant-b` hoặc rằng người dùng có quyền hoàn tiền. Hệ thống có thể dùng `requested_tenant` và `requested_scope` làm **điều kiện đầu vào để tính quyền**, còn `user_id` và `role` phải lấy từ ngữ cảnh/nguồn đã được xác minh hoặc bị bỏ qua.

## 4. Quy trình thu thập và quyết định phát hành

Một pipeline điển hình:

~~~mermaid
flowchart TD
    A["Yêu cầu cấp JWT"] --> B["Xác minh bằng chứng và client / grant"]
    B --> C{"Ngữ cảnh tin cậy hợp lệ?"}
    C -- "Không" --> X["Từ chối phát hành"]
    C -- "Có" --> D["Ánh xạ subject, client, tenant"]
    D --> E["Truy vấn các nguồn có thẩm quyền"]
    E --> F["Kiểm tra nguồn, ràng buộc và độ mới"]
    F --> G{"Dữ liệu bắt buộc hợp lệ?"}
    G -- "Không" --> X
    G -- "Có" --> H["Chuẩn hóa và giải quyết mâu thuẫn"]
    H --> I["Áp dụng chính sách audience, scope, privacy"]
    I --> J{"Claims đủ và đúng quyền?"}
    J -- "Không" --> X
    J -- "Có" --> K["Tạo claims hệ thống: iss, iat, exp..."]
    K --> L["Kiểm tra payload cuối; ký JWT; trả an toàn"]
~~~

**Bước A — Xây dựng ngữ cảnh đã xác thực.** Đầu vào để thu thập claim phải gồm chủ thể đã xác minh, client/grant đã kiểm tra, loại token và mục tiêu sử dụng. Nếu chứng cứ đến từ hệ thống liên kết, xác minh assertion hoặc token nhận vào theo **đúng giao thức** trước khi lấy giá trị.

**Bước B — Truy vấn theo định danh gắn chặt với ngữ cảnh.** Tra cứu bằng khóa chuẩn, ràng buộc cả subject lẫn tenant. Không dùng tham số do client tự khai để chọn bản ghi của người khác.

**Bước C — Kiểm tra thẩm quyền, toàn vẹn, tính mới.** Xác minh nguồn được cấu hình cho loại claim đó, kết quả thuộc đúng chủ thể, không bị thu hồi/quá hạn và có mức tin cậy phù hợp. Với nguồn liên kết, kiểm tra chữ ký, issuer, audience, expiry và các ràng buộc liên quan; với dịch vụ nội bộ, bảo vệ đường truyền/xác thực dịch vụ và xác minh quyền truy cập dữ liệu.

**Bước D — Chuẩn hóa/hợp nhất theo hợp đồng.** Chuyển đổi về kiểu dữ liệu và ý nghĩa đã thống nhất, xử lý nguồn mâu thuẫn, giới hạn danh sách quyền và bỏ các trường không có trong allowlist.

**Bước E — Áp dụng chính sách trước khi ký.** Chọn claim theo audience, token type, mục đích sử dụng, mức tin cậy đạt được và yêu cầu tối thiểu về dữ liệu cá nhân. Sinh claim hệ thống rồi kiểm tra payload lần cuối trước thao tác ký.

## 5. Kiểm tra nguồn dữ liệu trước khi tin claims

### 5.1. Nguồn liên kết: xác minh bằng chứng, không chỉ giải mã

Khi đọc claim từ ID token, assertion hoặc một JWT bên ngoài:

1. Chỉ chấp nhận issuer và giao thức đã được thiết lập quan hệ tin cậy.
2. Xác minh chữ ký bằng khóa gắn với issuer và **thuật toán cho phép**, chống nhầm lẫn thuật toán/khóa.
3. Kiểm tra đối tượng nhận (`aud`), thời hạn (`exp`), thời điểm hiệu lực (`nbf` nếu áp dụng), và các ràng buộc giao thức như `nonce` khi yêu cầu.
4. Kiểm tra token hoặc assertion có đúng **loại và mục đích** làm bằng chứng đầu vào; ID token không tự động là access token cho API khác.
5. Chỉ trích xuất những claim mà issuer bên ngoài **có thẩm quyền cung cấp**; áp dụng ánh xạ nội bộ và chính sách trước khi phát hành JWT mới.

**Lưu ý:** Việc token hợp lệ về chữ ký và thời gian không bảo đảm vai trò hoặc trạng thái tổ chức trong đó có thể được dùng cho authorization nội bộ.

### 5.2. Nguồn nội bộ: vẫn phải kiểm chứng tính đúng đắn

Một response đến từ dịch vụ nội bộ cũng có thể sai, cũ hoặc bị truy vấn nhầm bản ghi:

- Xác thực dịch vụ gọi và dịch vụ trả dữ liệu; bảo vệ kênh truyền và bí mật truy cập.
- Phân quyền chính dịch vụ phát hành được đọc những thuộc tính cần thiết.
- Dùng định danh chuẩn kết hợp tenant; không tra cứu quyền của tenant A rồi gắn vào token tenant B.
- Kiểm tra schema, kiểu dữ liệu, trạng thái bản ghi, phiên bản/cập nhật gần nhất khi cần.
- Tôn trọng vùng thẩm quyền: một service profile có thể trả `display_name` nhưng không được “đè” lên kết quả `scope` của policy engine.
- Giới hạn số lượng claim, độ dài chuỗi và số phần tử trong danh sách; không tin JSON hoặc dữ liệu động ở dạng không kiểm soát.

## 6. Chuẩn hóa, hợp nhất và xử lý mâu thuẫn

### 6.1. Định nghĩa rõ kiểu và miền giá trị

- **`sub`:** dùng định danh ổn định, đúng namespace của issuer. Không tự động lower-case hay cắt ký tự nếu việc đó có thể thay đổi danh tính.
- **`aud`:** chuỗi hoặc mảng đối tượng nhận theo cấu trúc JWT; chỉ gồm các audience được cấp phép.
- **`iat`, `nbf`, `exp`:** là NumericDate (số giây kể từ Unix epoch), không nhầm mili giây với giây.
- **`scope`:** theo profile áp dụng có thể là chuỗi phân cách bởi dấu cách; không tự ý thay định dạng mà bên nhận không hiểu.
- **`roles`, `permissions`:** nếu dùng claim riêng, quy định rõ namespace, loại dữ liệu, phạm vi tenant và ý nghĩa; không mặc định danh sách nhóm trong directory tương đương vai trò được cấp.
- **Claim riêng:** chọn tên tránh va chạm với registered/public claims, thiết kế namespace rõ ràng cho những claim dùng giữa nhiều hệ thống.

Đối với trường chưa hợp lệ, **không cố ép kiểu để tạo ra quyền**. Ví dụ `"admin"` không được tự động chuyển thành `true` khi chính sách yêu cầu boolean đã xác minh.

### 6.2. Quy tắc ưu tiên và xung đột

Nếu hai nguồn báo thông tin khác nhau, không dùng quy tắc “nguồn nào trả về sau thì thắng”. Cần ưu tiên theo **loại claim và chính sách đã thống nhất**:

| Tình huống | Cách xử lý phù hợp |
| --- | --- |
| Profile service báo `role=admin`, policy engine báo chỉ có quyền xem | Dùng quyết định phân quyền của policy engine; không nâng quyền từ profile |
| IdP trả email cũ, hồ sơ nội bộ đã đổi email | Chọn nguồn chuẩn của email theo hợp đồng; không mặc định email làm khóa định danh |
| Directory ghi user thuộc tenant X, nguồn thành viên chuẩn ghi đã rời X | Không cấp claim quyền tenant X; xác minh trạng thái tại nguồn chuẩn |
| Cache quyền còn hiệu lực theo TTL nhưng có tín hiệu thu hồi | Ưu tiên tín hiệu thu hồi; không phát hành token mang quyền đã bị rút |
| Một claim bắt buộc thiếu/không thể xác minh | Dừng phát hành loại token yêu cầu claim đó |
| Claim tùy chọn thiếu/không còn đủ tin cậy | Bỏ claim nếu hợp đồng cho phép, không suy đoán giá trị |

Khi có nhiều nguồn cùng thẩm quyền, cần một quy tắc hợp nhất **xác định và kiểm thử được**; với dữ liệu cấp quyền nhạy cảm, mâu thuẫn thường phải giải quyết trước khi cấp token.

## 7. Độ mới, cache và thay đổi quyền

JWT thường cho phép bên nhận tự xác minh chữ ký mà không gọi issuer mỗi lần. Điều này hữu ích cho hiệu năng nhưng làm nảy sinh một bài toán: **quyền hoặc trạng thái tài khoản có thể đổi ngay sau khi JWT được phát hành**.

Khi thu thập claims, nên xác định:

- **Độ mới tối đa theo claim:** trạng thái khóa tài khoản và quyền nhạy cảm thường cần dữ liệu mới hơn tên hiển thị hoặc ngôn ngữ giao diện.
- **TTL của cache:** cache phải gắn với đúng khóa subject–tenant–client/tài nguyên; TTL phải phù hợp mức rủi ro và chính sách; khi có thể, dùng sự kiện thay đổi/thu hồi để vô hiệu hóa cache.
- **Xử lý khi nguồn chậm/lỗi:** claim bắt buộc phục vụ quyết định quyền phải có chiến lược an toàn như từ chối phát hành hoặc chỉ dùng dữ liệu cache được chính sách cho phép và còn hiệu lực. Không tự nâng quyền dựa trên giá trị mặc định.
- **Thời gian sống của JWT:** token càng lâu hết hạn, quyền lưu trong token càng dễ trở nên lỗi thời. Có thể chọn access token ngắn hạn và cơ chế tra cứu/introspection, thu hồi hoặc chính sách kiểm soát khác khi cần phản ứng nhanh.
- **Kiểm tra khi sử dụng:** resource server vẫn phải xác minh token và phân quyền với tài nguyên cụ thể; claim hợp lệ tại thời điểm cấp không thay cho mọi kiểm tra ở thời điểm truy cập.

Ví dụ: quyền `orders:refund` bị thu hồi lúc 10:05, nhưng JWT cấp lúc 10:00 có `exp` lúc 11:00. Nếu resource server chỉ nhìn scope trong JWT và không có cơ chế thu hồi/đánh giá quyền động, quyền ấy có thể còn được chấp nhận cho đến khi token hết hạn. Thiết kế phát hành cần tính tới giới hạn này.

## 8. Ví dụ: thu thập claim cho API đơn hàng đa tenant

**Bối cảnh:** Người dùng truy cập bảng điều khiển, đã xác thực qua IdP liên kết, yêu cầu access token để đọc đơn hàng tại `tenant-a`.

Các nguồn đã được cấu hình:

| Bước | Nguồn và dữ kiện | Điều kiện / quyết định |
| --- | --- | --- |
| 1 | IdP trả định danh ngoài `ext-73` | Chỉ nhận sau khi xác minh assertion đúng issuer, audience, chữ ký, thời gian và ràng buộc giao thức |
| 2 | Identity mapping ánh xạ `(idp-1, ext-73) → usr-84` | Xác định `sub=usr-84` của issuer nội bộ |
| 3 | Tenant membership ghi `usr-84` đang hoạt động ở `tenant-a` | Cho phép giữ ngữ cảnh `tenant_id=tenant-a` |
| 4 | Client registry cho phép `dashboard` yêu cầu `orders-api` | Chọn audience đúng API và client hiện tại |
| 5 | Policy engine cho phép `orders:read`, từ chối `orders:refund` | Chỉ phát hành quyền đọc, dù request xin cả hai |
| 6 | Issuer tạo metadata và ký | Sinh `iss`, `iat`, `exp`, `jti` theo cấu hình; không đưa dữ liệu bí mật vào payload |

Payload **minh họa** trước khi ký (giá trị thời gian là ví dụ, không phải token dùng thực tế):

~~~json
{
  "iss": "https://auth.example.net",
  "sub": "usr-84",
  "aud": "https://api.example.net/orders",
  "iat": 1900000000,
  "exp": 1900000900,
  "jti": "tok-random-id-01",
  "client_id": "dashboard",
  "tenant_id": "tenant-a",
  "scope": "orders:read"
}
~~~

Những claim này chỉ có ý nghĩa nếu dịch vụ nhận token biết cách kiểm tra chúng theo hợp đồng chung. `tenant_id` và `client_id` ở đây là **claim riêng theo profile thiết kế**, không phải claim bắt buộc của mọi JWT; `jti` ví dụ chỉ minh họa định danh, triển khai thực tế cần sinh giá trị phù hợp chính sách.

**Nếu thay đổi dữ kiện đầu vào:**

- Request gửi `tenant-b` trong khi người dùng không thuộc tenant đó → từ chối phát hành token cho `tenant-b`.
- Một hồ sơ người dùng trả về `role=owner` nhưng policy engine không cấp quyền hoàn tiền → không phát hành `orders:refund`.
- Policy engine không phản hồi và hệ thống không có dữ liệu quyền còn hiệu lực được phép dùng → từ chối cấp token cần quyền ấy; không tự thêm scope.
- Email đã đổi nhưng định danh nội bộ `usr-84` giữ nguyên → tiếp tục dùng `sub` ổn định, không tạo hai danh tính dựa trên email.

## 9. Mã giả triển khai độc lập công nghệ

~~~text
function collectClaimsForAccessToken(request, verifiedContext):
    require verifiedContext.authenticated
    require verifiedContext.clientAllowedForGrant

    subject = identityStore.resolveSubject(
        verifiedContext.issuer,
        verifiedContext.authenticatedSubject
    )
    require subject.exists and subject.active

    tenant = tenantRegistry.resolveRequestedTenant(request.tenant, subject)
    require tenant.active and tenant.hasActiveMember(subject.id)

    audience = clientRegistry.authorizeAudience(
        verifiedContext.clientId,
        request.requestedAudience
    )
    require audience.allowed

    requestedScopes = parseAllowedScopeSyntax(request.requestedScope)
    grantedScopes = policyEngine.authorizeScopes(
        subject.id,
        verifiedContext.clientId,
        tenant.id,
        audience.value,
        verifiedContext.grant,
        requestedScopes
    )
    require grantedScopes.valid and grantedScopes.freshEnough

    issuedAt = trustedClock.epochSeconds()
    claims = {
        "iss": issuerConfig.issuer,
        "sub": subject.stableId,
        "aud": audience.value,
        "iat": issuedAt,
        "exp": issuedAt + issuerPolicy.accessTokenTtlSeconds,
        "jti": secureIdGenerator.next(),
        "tenant_id": tenant.id,
        "scope": formatScopes(grantedScopes.allowedSubset)
    }

    claims = claimPolicy.validateAndMinimize(claims, audience.value)
    require claims.meetRequiredSchema and claims.withinSizeLimits
    return claims

function issueToken(request, verifiedContext):
    claims = collectClaimsForAccessToken(request, verifiedContext)
    token = jwtSigner.signUsingConfiguredKeyAndAlgorithm(claims)
    auditWithoutRawTokensOrSecrets(verifiedContext, claims)
    return deliverSecurely(token)
~~~

Hàm giả định tầng xác thực đã tạo `verifiedContext` đáng tin cậy. Thực tế phải xử lý lỗi phụ thuộc, timeout, giới hạn tài nguyên và nhất quán trạng thái; chính sách fail-safe là một phần của hàm `require`/`claimPolicy`. Ví dụ trên minh họa **thu thập và kiểm soát nguồn claim**, không đặc tả một giao thức ủy quyền cụ thể.

## 10. Bảo mật và quyền riêng tư khi đưa dữ liệu vào JWT

1. **Tối thiểu hóa:** chỉ thêm claim mà đối tượng nhận cần để quyết định xử lý; ưu tiên ID ổn định hoặc tham chiếu thay cho cả hồ sơ. Tránh đặt mật khẩu, OTP, khóa bí mật, số giấy tờ hoặc dữ liệu nhạy cảm không cần thiết trong JWT.
2. **Không nhầm ký với mã hóa:** JWS ký thông thường không bảo mật nội dung payload; người giữ token có thể giải mã các phần Base64URL. Chỉ dùng claim nhạy cảm khi thật sự cần và có biện pháp thích hợp (ví dụ mã hóa, token tham chiếu hoặc truy vấn backend).
3. **Giới hạn chia sẻ:** scope, role và tenant có thể tiết lộ cấu trúc nội bộ; mỗi audience nên nhận tập claim riêng theo quyền cần biết.
4. **Chống chèn claim:** dùng allowlist, schema đã khai báo và API dựng payload kiểm soát. Không gộp tự động toàn bộ JSON profile, header hoặc request body vào payload; không cho dữ liệu ngoài ghi đè `iss`, `sub`, `aud`, `exp`.
5. **Theo dõi nguồn gốc:** ghi nội bộ phiên bản chính sách, mã nguồn dữ liệu, thời điểm xác minh và ID tương quan phục vụ điều tra. Không nhất thiết đưa provenance nội bộ vào JWT; tránh log toàn bộ token hoặc bí mật.
6. **Ràng buộc tenant:** tách rõ chủ thể và tổ chức. Quyền và membership phải cùng tenant với claim đã cấp; không trộn cache hoặc role giữa các tenant.
7. **Kiểm soát kích thước:** token được gửi trong HTTP header/cookie hoặc các kênh khác có giới hạn. Claim quá nhiều còn tăng nguy cơ rò rỉ; xem xét lưu quyền phức tạp ở máy chủ thay vì đóng gói toàn bộ.

## 11. Các lỗi thường gặp và cách phòng ngừa

| Sai lầm | Hậu quả | Cách phòng ngừa |
| --- | --- | --- |
| Sao chép trực tiếp `role` từ request | Nâng quyền trái phép | Dựa trên policy engine; client chỉ nêu yêu cầu |
| Dùng mọi claim của ID token ngoài hệ thống làm quyền nội bộ | Tin sai phạm vi thẩm quyền của IdP | Kiểm chứng token đầu vào, định nghĩa claim mapping và chủ thể nội bộ |
| Dùng email làm `sub` mà không có hợp đồng định danh | Mất liên kết khi email đổi, nhầm chủ thể | Dùng ID ổn định, ràng buộc với issuer |
| Lấy claim từ cache mà không ràng buộc tenant | Rò rỉ hoặc cấp nhầm quyền giữa tổ chức | Cache key đầy đủ và kiểm tra membership |
| Gộp dữ liệu theo kiểu “nguồn trả sau ghi đè” | Quyền phụ thuộc thứ tự gọi dịch vụ | Xác định nguồn có thẩm quyền và quy tắc xung đột |
| Nguồn quyền bị lỗi thì giữ nguyên quyền mặc định cao | Fail-open, vượt quyền | Fail-safe, quản lý freshness và TTL |
| Đưa toàn bộ profile vào JWT | Lộ dữ liệu, token lớn, dữ liệu cũ | Tối thiểu hóa theo audience, chỉ phát hành claim cần thiết |
| Giả định quyền trong token luôn mới | Quyền đã thu hồi vẫn có thể được dùng | TTL phù hợp, thu hồi/introspection/kiểm tra khi truy cập theo nhu cầu |

## 12. Checklist kiểm thử khâu thu thập claims

- **Nguồn:** nguồn đúng nhưng trả sai subject; nguồn không có thẩm quyền trả role; assertion bên ngoài sai audience/chữ ký → không phát hành claim sai.
- **Định danh:** người dùng hai tenant có cùng email; thay đổi email; external subject trùng giữa hai IdP → vẫn ánh xạ đúng chủ thể và tenant.
- **Quyền:** request yêu cầu scope cao; client không được phép audience; policy engine chỉ cấp một phần quyền → payload không vượt quyền.
- **Thời gian và trạng thái:** membership bị thu hồi; bản ghi stale; cache quá TTL; nguồn quyền timeout → quyết định theo chính sách an toàn.
- **Dữ liệu:** nguồn trả null, sai kiểu, danh sách quyền dài bất thường, trùng claim hoặc trường lạ → normalize, loại bỏ hoặc từ chối theo hợp đồng.
- **Riêng tư:** claim không cần thiết không xuất hiện; payload không chứa mật khẩu/OTP; log không lưu token hoặc credential nguyên vẹn.
- **Tính đúng đắn:** mọi claim đã phát hành có nguồn và quy tắc ánh xạ; `iss`, `aud`, `iat`, `exp` từ dữ liệu tin cậy; access token đúng định dạng mà bên nhận mong đợi.

## 13. Tài liệu tham khảo

- [RFC 7519 — JSON Web Token (JWT)](https://www.rfc-editor.org/rfc/rfc7519): mô hình claim, registered claim names và NumericDate.
- [RFC 8725 — JSON Web Token Best Current Practices](https://www.rfc-editor.org/rfc/rfc8725): xác thực issuer/audience, kiểm tra thuật toán và tách mục đích token.
- [RFC 9068 — JSON Web Token (JWT) Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068): claim và profile của JWT access token theo OAuth 2.0.
- [RFC 9700 — Best Current Practice for OAuth 2.0 Security](https://www.rfc-editor.org/rfc/rfc9700): các lưu ý bảo mật mới cho luồng cấp quyền và token.
- [OpenID Connect Core 1.0](https://openid.net/specs/openid-connect-core-1_0.html): xác thực liên kết và quy tắc kiểm chứng ID token.

**Ghi nhớ:** Thu thập claims là quá trình **kiểm chứng nguồn, ánh xạ danh tính, tính quyền, xử lý tính mới và giới hạn dữ liệu** trước khi issuer ký JWT. Mỗi claim phải có người chịu trách nhiệm về tính đúng đắn, đúng đối tượng và đúng thời điểm; token ký hợp lệ không thể sửa được lỗi tin sai nguồn dữ liệu.
