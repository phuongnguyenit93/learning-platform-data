# Scope hiển thị cho user

Khi một ứng dụng yêu cầu người dùng **“Cho phép ứng dụng truy cập dữ liệu của bạn”**, authorization server (AS) thường có thể hiển thị một màn hình **consent** giải thích ứng dụng nào đang xin quyền và phạm vi quyền đó. Trong OAuth 2.0, ứng dụng có thể gửi `scope=orders.read orders.write`; nhưng chuỗi kỹ thuật này **không phải nội dung dễ hiểu hoặc đủ rõ để người dùng ra quyết định**.

Ví dụ, người dùng đang kết nối một ứng dụng báo cáo với Orders API. Màn hình chỉ hiện `orders.read` có thể không cho họ biết ứng dụng sẽ đọc **đơn hàng của tổ chức nào**, có thể truy cập **bao lâu** hoặc có quyền **sửa/xóa dữ liệu** hay không. Ngược lại, màn hình ghi “Chỉ xem tổng số đơn hàng” trong khi token thực tế có `orders.write` là **mô tả gây hiểu lầm và có nguy cơ vượt quyền được thông báo**.

Bài **“Scope hiển thị cho user”** nằm trong chương **Consent** thuộc module **SECURITY_TOKEN_SECURITY_FUNDAMENTALS**. Bài tập trung vào việc chuyển các **scope kỹ thuật** thành nội dung consent trung thực, có ngữ cảnh, dễ kiểm tra; đồng thời phân biệt quyền yêu cầu/được duyệt/được cấp, JWT và opaque access token, OAuth 2.0/OpenID Connect (OIDC), issuer–audience, tenant, lưu trữ, thu hồi và nguy cơ token bị đánh cắp hoặc phát lại.

> **Nguyên tắc:** **Scope hiển thị là cách diễn giải quyền cho người dùng, không phải nguồn quyền bảo mật.** AS phải quyết định grant theo registration/policy và consent; access token phải phản ánh quyền thực sự được cấp; resource server phải xác minh token và áp quyền tại từng API/tài nguyên.

## 1. Scope là gì và consent liên quan thế nào?

**OAuth 2.0 scope** là cách biểu diễn phạm vi quyền ứng dụng đề nghị được cấp, thường là danh sách chuỗi phân cách bằng khoảng trắng. Ví dụ:

~~~http
GET /authorize?response_type=code
  &client_id=reports-web
  &redirect_uri=https%3A%2F%2Freports.example.com%2Fcallback
  &scope=orders.read%20orders.write
  &state=<random-state>
  &code_challenge=<pkce-s256-challenge>
  &code_challenge_method=S256 HTTP/1.1
Host: auth.example.com
~~~

Đây là request **minh họa đã ngắt dòng**. Trên HTTP thật, URI query nằm trên một dòng và cần URL-encode. `scope` chỉ là **yêu cầu của client**. Authorization server có quyền kiểm tra registration, user/session, consent, tenant, resource và chính sách trước khi cấp token.

Một hệ thống có thể cho phép client yêu cầu `orders.read` nhưng **không được** yêu cầu `orders.write`; hoặc người dùng có thể từ chối một phần/đã cấp quyền trước đó. Client không thể tự tạo quyền chỉ bằng cách thay tham số `scope`.

### 1.1. Consent không đồng nghĩa authentication

| Khái niệm | Câu hỏi cần trả lời | Ví dụ |
| --- | --- | --- |
| **Authentication** | User là ai? | User đăng nhập bằng passkey/MFA |
| **Client authentication** | OAuth client nào đang xin token? | Backend xác thực bằng private-key JWT |
| **Consent** | User có đồng ý cho client yêu cầu một tập quyền trong ngữ cảnh này? | Cho phép báo cáo **đọc đơn hàng** |
| **Authorization/grant policy** | AS có thực sự được phép cấp quyền đó? | Client chỉ được đăng ký `orders.read` |
| **Resource authorization** | Access token này được làm gì với tài nguyên cụ thể? | Chỉ đọc order thuộc tenant Acme |

**User ấn “Đồng ý” không có nghĩa client được quyền làm mọi thứ**. Một người dùng có thể không có quyền xuất dữ liệu nhạy cảm; consent không thể cấp vượt quyền của user hoặc policy AS. Với **client credentials grant**, token app-only không có người dùng đang cho consent trong giao dịch; quyền thường xuất phát từ quản trị viên hoặc policy workload.

### 1.2. OAuth 2.0 không bắt buộc luôn hiện một consent screen

Theo RFC 6749, AS tương tác với resource owner để nhận authorization decision theo chính sách. Một số AS có thể dựa trên **grant đã lưu**, quy tắc first-party hoặc policy quản trị và không hiển thị lại màn hình consent ở mọi lần đăng nhập. Việc **có hiển thị hay không, ai có quyền cấp, scope nào yêu cầu đồng ý tường minh** phụ thuộc issuer, profile, đăng ký client và quy định tổ chức.

Điều quan trọng: dù consent UI có xuất hiện hay không, **AS phải có cơ sở cho grant** và resource server vẫn phải kiểm tra token theo chính sách.

## 2. Phân biệt requested, display, approved và granted scopes

Đừng đồng nhất bốn tập thông tin:

1. **Requested scopes**: quyền client yêu cầu tại authorization endpoint.
2. **Display permissions**: mô tả **phù hợp với tập quyền/điều kiện** mà AS đưa ra cho user nhìn thấy.
3. **Approved permissions**: phần user xác nhận khi có quyền lựa chọn; có thể là toàn bộ, một phần hoặc từ chối.
4. **Granted scopes/authorization details**: quyền **AS quyết định cấp thực sự**, sau khi giao giữa client registration, policy, user entitlements và consent.

~~~mermaid
flowchart TD
    A["Client gửi scopes yêu cầu"] --> B["AS kiểm tra client registration,\nresource/audience, user/tenant policy"]
    B --> C["AS tạo permission display an toàn\nnhãn và mô tả từ catalog được tin"]
    C --> D{"User/administrator có duyệt?"}
    D -->|Từ chối| E["access_denied / dừng grant"]
    D -->|Đồng ý theo phạm vi| F["AS lưu consent/grant theo policy"]
    F --> G["AS phát authorization code và token"]
    G --> H["Client xem quyền thực sự được cấp"]
    H --> I["RS validate access token\nvà quyền trên tài nguyên"]
~~~

Một cách hình dung đơn giản:

~~~text
Requested:      orders.read, orders.write, payments.refund
Registered:     orders.read, orders.write
User decision:  chỉ cho phép orders.read
AS policy:      user không có quyền orders.write

Granted:        orders.read
Display:        “Xem đơn hàng” (không mô tả như có quyền sửa)
API:            GET được xét; POST bị từ chối nếu thiếu quyền
~~~

Đây là **ví dụ giả định**, không phải mọi AS đều cho phép chọn từng scope. Một số OP/AS cấp hoặc từ chối **toàn bộ yêu cầu**; ứng dụng muốn quyền ít hơn có thể phải bắt đầu một authorization request khác.

### 2.1. Quan hệ an toàn giữa những tập quyền

Với mô hình scopes đơn giản, phần được cấp không được vượt quyền AS cho phép:

\[
G \subseteq R \cap C \cap P
\]

Trong đó: \(\,G\,\) là tập quyền được cấp, \(\,R\,\) quyền client yêu cầu, \(\,C\,\) quyền client được đăng ký, \(\,P\,\) quyền policy cho phép. Consent của user (khi áp dụng) là một ràng buộc **bổ sung**, không phải lối đi vượt giới hạn.

Biểu thức chỉ mô tả nguyên tắc, **không thay thuật toán cấp token** của RFC hay semantics của rich authorization. Có scope phụ thuộc nhau, quyền mặc định hoặc policy riêng theo issuer; phải định nghĩa rõ contract thay vì tính tập hợp chuỗi một cách tùy tiện.

### 2.2. Không suy quyền từ text trên màn hình

Sai:

~~~text
if consentScreen.contains("Cho phép đọc đơn hàng"):
    authorize("orders.read")
~~~

Đúng:

~~~text
trusted AS grant -> granted scopes / permissions
                    -> access token / introspection
                    -> RS checks endpoint + object policy

consent text -> giúp user hiểu quyền, KHÔNG phải security authority
~~~

Giao diện có thể thay đổi ngôn ngữ, bị mất kết nối hoặc render không đầy đủ. **Bảo mật phải dựa trên grant/claims/metadata có nguồn gốc xác minh được**, không phân tích chữ trên UI.

## 3. Hiển thị scope kỹ thuật thành quyền dễ hiểu

Một catalog hiển thị được **AS kiểm soát** có thể ánh xạ scope sang nhãn, giải thích và mức độ nhạy cảm:

| Scope kỹ thuật | Nhãn tiếng Việt đề xuất | Mô tả user-facing | Tính chất |
| --- | --- | --- | --- |
| `orders.read` | **Xem đơn hàng** | Xem thông tin các đơn hàng mà bạn có quyền truy cập trong tổ chức đã chọn | Đọc dữ liệu nghiệp vụ |
| `orders.write` | **Tạo và cập nhật đơn hàng** | Tạo hoặc thay đổi đơn hàng trong phạm vi tổ chức được cấp quyền | Ghi/thay đổi dữ liệu |
| `orders.delete` | **Xóa đơn hàng** | Xóa đơn hàng nếu chính sách của tổ chức cho phép | Thao tác rủi ro cao |
| `reports.export` | **Xuất báo cáo** | Tải báo cáo có thể chứa dữ liệu được phép xem | Có nguy cơ phát tán dữ liệu |
| `profile.read` | **Xem hồ sơ** | Đọc thông tin hồ sơ theo chính sách và dữ liệu được cấp | Thông tin người dùng |
| `payments.refund` | **Thực hiện hoàn tiền** | Thực hiện thao tác hoàn tiền trong hạn mức và chính sách đã phê duyệt | Quyền tài chính nhạy cảm |

Các scope trong bảng là **ví dụ của một hệ thống giả định**, không phải scope chuẩn bắt buộc của mọi OAuth server. Tên `orders.write` có thể ở một hệ thống bao gồm xóa, trong khi nơi khác không bao gồm xóa. **Nhãn phải phản ánh chính xác semantics của resource server trong hệ thống đó**.

### 3.1. Không hiển thị chỉ một tên máy

Ví dụ một giao diện chỉ hiện tên scope máy móc sẽ khó hiểu hơn cách diễn đạt quyền rõ ràng:

~~~text
KHÓ HIỂU:
  Ứng dụng yêu cầu scopes:
  orders.write, payments.refund

RÕ RÀNG HƠN:
  Ứng dụng Báo cáo Thu chi muốn:
  - Tạo hoặc cập nhật đơn hàng mà bạn được phép quản lý.
  - Thực hiện hoàn tiền theo quyền và hạn mức được cấp.

  Phạm vi: Tổ chức Acme
  Quyết định: [Từ chối] [Tiếp tục]
~~~

**Cần cẩn trọng với “Tiếp tục”**: nút xác nhận phải cho thấy rõ hệ quả. Với quyền nhạy cảm, “Cho phép các quyền trên” thường rõ nghĩa hơn “Tiếp tục”.

### 3.2. Mô tả không được rộng hơn hoặc hẹp hơn quyền thực tế

| Kiểu sai | Hậu quả |
| --- | --- |
| `orders.write` hiển thị “Chỉ xem đơn hàng” | Người dùng bị che giấu quyền thay đổi dữ liệu |
| `orders.read` hiển thị “Quản lý mọi đơn hàng” | Người dùng có thể hiểu nhầm quyền rất rộng |
| `reports.export` không đề cập tải dữ liệu ra ngoài | Không làm rõ khả năng sao chép/phát tán |
| `payments.refund` chỉ ghi “Quản lý thanh toán” | Không nói rõ thao tác hoàn tiền có rủi ro |
| “Truy cập mọi tổ chức” khi token chỉ dùng cho Acme | Sai ngữ cảnh, dễ gây mất lòng tin |
| “Chỉ tổ chức Acme” nhưng token cho nhiều tenants | Che giấu quyền thực tế nghiêm trọng |

**Một scope có thể trao nhiều API actions.** Khi ánh xạ, phải kiểm tra các endpoint/resource policies liên quan; không suy nghĩa từ hậu tố `.read`/`.write` một cách cơ học.

## 4. Một màn hình consent tốt cần trả lời những gì?

Người dùng nên hiểu tối thiểu:

- **Ứng dụng nào** đang yêu cầu (tên được AS xác minh, publisher/organization khi có).
- **Dùng tài khoản nào**, và **tenant/tổ chức nào** nếu đa tổ chức.
- **Những thao tác gì**: xem, tạo, cập nhật, xóa, xuất, gửi, chi tiền.
- **Dữ liệu nào**: hồ sơ, email, lịch, đơn hàng, khách hàng, thanh toán.
- **Ranh giới phạm vi**: chỉ dữ liệu user được quyền xem hay toàn bộ tài nguyên tổ chức.
- **Thời gian và cách duy trì truy cập**: theo phiên, có offline/refresh không, có thể thu hồi ở đâu.
- **Ai có thể chấp thuận**: user hiện tại hay administrator; quyền nào do policy quyết định.
- **Hậu quả khi từ chối**: ứng dụng có thể mất tính năng nào, nhưng user không bị tự động cấp quyền.

Ví dụ giao diện consent giả định:

~~~text
ỨNG DỤNG MUỐN KẾT NỐI

Báo cáo Nội bộ (đã được quản trị viên tổ chức xác nhận)
Tài khoản: user@example.com
Tổ chức: Acme

Ứng dụng yêu cầu:
  ✓ Xem đơn hàng mà tài khoản này được phép xem
  ✓ Xuất báo cáo từ những đơn hàng đó

Ứng dụng KHÔNG được phép:
  - Tạo, sửa hoặc xóa đơn hàng
  - Thực hiện thanh toán hoặc hoàn tiền

Bạn có thể quản lý/thu hồi quyền kết nối trong phần
Ứng dụng đã kết nối của tài khoản.

[Từ chối]       [Cho phép 2 quyền]
~~~

**Thông tin publisher đã xác minh chỉ hiển thị khi AS thực sự có cơ chế xác minh.** Không nhận tên/logo của client qua một query parameter rồi gắn nhãn “đã xác minh”. Mô tả “KHÔNG được phép” cần dựa trên policy/scopes thực tế, tránh hứa hẹn không đúng nếu các phương thức truy cập khác của app vẫn tồn tại.

## 5. Ai sở hữu nhãn và mô tả scope?

Mô tả quyền hiển thị nên do **authorization server hoặc một catalog nội bộ được AS tin cậy** quản lý, không phải text tự khai không giới hạn từ OAuth client.

~~~mermaid
flowchart LR
    C["OAuth client\nscope=orders.read"] --> AS["Authorization server"]
    REG["Scope catalog có kiểm duyệt\nID, mô tả, risk, i18n"] --> AS
    POL["Client registration\nresource/tenant policy"] --> AS
    AS --> UI["Consent screen đã escape\nclient + quyền + ngữ cảnh"]
    UI --> DEC{"User/admin decision"}
    DEC --> G["AS grant và token"]
    G --> RS["RS verify scope/audience\nvà object-level policy"]
~~~

### 5.1. Catalog cần có cấu trúc

Một bản ghi minh họa:

~~~json
{
  "scope": "orders.read",
  "resource": "https://api.example.com/orders",
  "display": {
    "vi": {
      "title": "Xem đơn hàng",
      "description": "Xem đơn hàng trong tổ chức mà bạn được cấp quyền"
    },
    "en": {
      "title": "Read orders",
      "description": "Read orders in authorized organizations"
    }
  },
  "risk_level": "standard",
  "data_categories": ["orders"],
  "allowed_operations": ["read"],
  "display_version": 3
}
~~~

Đây là **schema ứng dụng tự thiết kế**, không phải JSON chuẩn bắt buộc của OAuth. Các trường `risk_level`, `data_categories`, `display_version` hữu ích để quản trị nội dung và kiểm toán; **không phải claims mặc định được AS tự đưa vào access token**.

### 5.2. Những đặc tính nên enforce

1. **Không có scope lạ ở trạng thái được cấp:** scope chưa đăng ký/không có mapping đúng phải được **từ chối hoặc xử lý theo chính sách an toàn**, không âm thầm ẩn khỏi consent UI rồi vẫn cấp.
2. **Nhãn tách khỏi ngôn ngữ của client:** tránh attacker gửi `display_name=System Administrator` hoặc HTML/JS độc hại.
3. **Resource awareness:** `read` ở Payments API có nghĩa khác `read` ở Orders API; mapping cần biết issuer/resource.
4. **Versioning:** khi semantics của scope đổi, phải cập nhật mapping, xem lại consent đã lưu và yêu cầu xin lại khi cần.
5. **Translation parity:** bản dịch tiếng Việt/Anh diễn đạt cùng quyền; không giấu quyền nhạy cảm trong một ngôn ngữ.
6. **Defense in depth:** escape HTML, CSP, hạn chế markdown/HTML từ nguồn không tin cậy và không dùng client URL làm hyperlink tùy ý.

### 5.3. Vì sao không cho client tùy ý quyết định consent text?

Một ứng dụng ác ý có thể yêu cầu `payments.refund` nhưng tự đặt mô tả “Xem số dư”. Nếu AS hiển thị text do client cung cấp mà không kiểm tra, user sẽ đồng ý dựa trên **thông tin sai lệch**. Client có thể đề xuất metadata khi đăng ký, nhưng AS phải **kiểm duyệt và ràng buộc nội dung với quyền thực tế** trước khi dùng.

## 6. OAuth scope, OIDC scopes và claims cho user

Một yêu cầu OIDC thường chứa các giá trị như:

~~~text
scope=openid profile email
~~~

Trong **OpenID Connect Core**, các scope này có ý nghĩa riêng. Chúng không tương đương với scope API tự định nghĩa như `orders.write`.

| OIDC scope | Nội dung cần diễn giải | Điều không được hứa |
| --- | --- | --- |
| **`openid`** | Ứng dụng yêu cầu sử dụng OIDC để nhận diện user đã xác thực | Không có nghĩa app có quyền đọc mọi hồ sơ hoặc mọi API |
| **`profile`** | Có thể yêu cầu các claims hồ sơ tiêu chuẩn như tên, username, ảnh đại diện, ngôn ngữ… | Không phải mọi claim đều chắc chắn được trả |
| **`email`** | Yêu cầu email và trạng thái email_verified theo OIDC policy | Không mặc định email luôn có/đã xác minh |
| **`phone`** | Yêu cầu số điện thoại/phone_number_verified khi có | Không bảo đảm OP có phone claim |
| **`address`** | Yêu cầu thông tin địa chỉ theo OIDC | Không đảm bảo mọi thành phần địa chỉ có sẵn |
| **`offline_access`** | Yêu cầu quyền truy cập khi user không tương tác, thường liên quan refresh token | **Không** tự bảo đảm refresh token được cấp |

Ví dụ diễn đạt:

~~~text
openid:
  “Đăng nhập vào ứng dụng bằng tài khoản này.”

profile:
  “Xem thông tin hồ sơ cơ bản, chẳng hạn tên và ảnh đại diện
   nếu tài khoản cung cấp các thông tin đó.”

email:
  “Xem địa chỉ email và trạng thái xác minh email nếu có.”
~~~

**Không mô tả `openid` là “toàn quyền tài khoản”.** ID token dành cho OIDC client xác minh kết quả authentication, còn access token dành cho resource server; thông tin profile có thể đến qua ID token/UserInfo tùy profile và scope/consent.

### 6.1. Claims thực tế không phải lúc nào cũng bằng scope danh nghĩa

Client xin `profile` không có nghĩa sẽ nhận đầy đủ tất cả claims. OP có thể trả tập con phụ thuộc consent, privacy policy, claim availability hoặc cấu hình. Giao diện nên dùng cách diễn đạt chính xác như **“có thể xem…”** hoặc liệt kê những claim thực tế được yêu cầu/cho phép theo contract của OP.

### 6.2. Không dùng ID token làm access token tại API

OIDC client có thể nhận ID token với `aud=client_id`. Resource server phải nhận access token dành cho API và verify `iss`, `aud`, thời hạn, scope. **Consent hiển thị OIDC scopes không cho phép lấy ID token gửi vào Orders API như bearer access token**.

## 7. Hiển thị quyền truy cập lâu dài: `offline_access`

`offline_access` đặc biệt dễ khiến người dùng hiểu sai. Nếu một client xin quyền truy cập **khi người dùng không còn mở ứng dụng**, consent screen nên nói rõ hệ quả **được tiếp tục truy cập theo chính sách** và cách quản lý/thu hồi.

Ví dụ:

~~~text
Ứng dụng muốn duy trì quyền kết nối

Ứng dụng Đồng bộ Báo cáo có thể tiếp tục đồng bộ
đơn hàng khi bạn không mở ứng dụng, miễn quyền kết nối
còn hiệu lực và tài khoản/tổ chức vẫn cho phép.

Bạn có thể thu hồi quyền trong mục Ứng dụng đã kết nối.

[Từ chối]       [Cho phép truy cập khi ngoại tuyến]
~~~

**Chỉ hiển thị lời hứa này khi grant thực sự hỗ trợ truy cập nền và theo đúng thời gian/chính sách hiện hành.** OAuth/OIDC có thể cho phép AS trả refresh token, nhưng scope `offline_access` không bảo đảm AS sẽ cấp refresh token. OIDC còn có yêu cầu về consent/response type khi xử lý yêu cầu offline access (ví dụ điều kiện `prompt=consent` trong những ngữ cảnh nhất định).

### 7.1. Refresh token, rotation và nguy cơ replay

Nếu client được cấp refresh token, nó có thể xin access token mới mà user không tương tác lại, trong giới hạn AS. Với public clients, refresh token cần **sender constraint hoặc rotation/reuse detection** theo chính sách/best practices áp dụng. Consent UI không thay thế:

- Lưu refresh token trong nơi được bảo vệ;
- Refresh token rotation và thu hồi grant/token family;
- TTL, session/policy checks và logout semantics;
- Access token audience/scope hạn chế;
- RS authorization trên mỗi API call.

**Đánh cắp refresh token là rủi ro khác với user chỉ đồng ý một scope.** Một refresh token bị sao chép có thể kéo dài khả năng xin token mới đến khi bị phát hiện hoặc thu hồi, nên màn hình phải trung thực về truy cập dài hạn.

## 8. Audience/resource indicator: hiển thị “đọc dữ liệu ở đâu?”

Scope thường không xác định duy nhất **resource server** nhận token. Một client có thể yêu cầu:

~~~text
scope=read
resource=https://api.example.com/orders
~~~

`resource` là tham số được chuẩn hóa trong **RFC 8707** khi AS hỗ trợ. Scope `read` một mình quá mơ hồ. AS có thể dùng resource indicator, registration và policy để quyết định audience của token; RS phải xác minh **`aud`** tương ứng.

Ví dụ nhãn khác nhau:

| Resource | Scope | Permission hiển thị |
| --- | --- | --- |
| Orders API | `read` | Xem đơn hàng được cấp quyền |
| Payments API | `read` | Xem giao dịch thanh toán được cấp quyền |
| Contacts API | `read` | Xem danh bạ được cấp quyền |

**Không chỉ map theo chuỗi `scope=read` nếu issuer có nhiều APIs.** Catalog cần namespace (issuer, resource/audience, scope ID), và consent phải phản ánh resource mà token sẽ dùng.

### 8.1. Resource indicator là yêu cầu, không phải audience chắc chắn

Client gửi `resource=https://api.example.com/orders` không có nghĩa AS phải cấp token cho URL đó. AS phải kiểm tra tài nguyên được cho phép, scopes và grant. **Token thực tế hoặc introspection metadata** mới quyết định quyền mà RS có thể chấp nhận.

### 8.2. Consent cho nhiều resource servers

Nếu một client xin quyền đọc Orders và Payments, màn hình nên **nhóm theo dịch vụ và mức rủi ro**, không gộp thành một dòng “Xem dữ liệu”. Nếu user chỉ đồng ý Orders nhưng hệ thống không hỗ trợ partial grant, AS nên từ chối yêu cầu hoặc buộc client bắt đầu request hẹp hơn theo policy, không âm thầm cấp Payments.

## 9. Scope trong ứng dụng đa tenant và tổ chức

Trong hệ thống đa tổ chức, **`orders.read` chưa nói user muốn chia sẻ dữ liệu của tenant nào**. Một user có thể thuộc Acme và Globex nhưng chỉ muốn kết nối app báo cáo cho Acme.

Màn hình minh họa:

~~~text
Ứng dụng: Báo cáo Nội bộ
Tài khoản: user@example.com

Tổ chức áp dụng: Acme

Quyền đề nghị:
  ✓ Xem đơn hàng trong Acme mà tài khoản có quyền đọc
  ✓ Xuất báo cáo thuộc Acme

Không bao gồm tổ chức Globex.

[Từ chối]       [Cho phép cho Acme]
~~~

**Chỉ dùng diễn đạt “Không bao gồm Globex” nếu token/grant và RS policy thực sự giới hạn đúng Acme.** Nếu AS cấp quyền trên tất cả tổ chức của user, màn hình không được hứa chỉ một tổ chức.

### 9.1. Ràng buộc tenant ở đâu?

Một contract có thể dùng custom claim `tenant_id`, resource-specific authorization details hoặc grants lưu ở AS. Chúng **không phải claims chuẩn có sẵn cho mọi OAuth provider**. RS phải tra quyền dữ liệu thực tế:

~~~sql
SELECT *
FROM orders
WHERE id = :order_id
  AND tenant_id = :verified_tenant_id;
~~~

`:verified_tenant_id` phải đến từ **grant/claims đã xác minh**, không lấy `X-Tenant-Id`, form field hoặc URL do client tự khai rồi coi là bằng chứng quyền.

### 9.2. Admin consent khác user consent

Một tổ chức có thể quy định chỉ **administrator** mới cấp quyền ứng dụng đọc dữ liệu toàn tổ chức. User thường không có quyền cấp `reports.export.all` cho toàn bộ nhân viên.

Giao diện phải phân biệt:

- **User-delegated consent:** ứng dụng thao tác trong phạm vi user đã có quyền, theo grant.
- **Admin/organization consent:** quản trị viên cấp quyền tổ chức theo chính sách đã kiểm chứng.
- **App-only/service grant:** không gắn user đang đăng nhập; quyền từ registration/management policy.

Nút “Cho phép” của user **không phải bằng chứng user được phép tạo organization-wide grant**. AS phải kiểm tra role/admin entitlement bằng nguồn tin cậy.

## 10. Granular consent và lựa chọn từng scope

Một số hệ thống hỗ trợ user bật/tắt từng nhóm quyền:

~~~text
Ứng dụng Báo cáo muốn:

[x] Xem đơn hàng
[x] Xuất báo cáo
[ ] Tạo/cập nhật đơn hàng (không cần cho tính năng cơ bản)

[Từ chối]       [Cho phép quyền đã chọn]
~~~

Đây chỉ là UX **nếu AS thực sự hỗ trợ partial consent**. Có scope phụ thuộc khác; ví dụ `reports.export` có thể chỉ hợp lệ khi `orders.read` được cấp. Nếu user bỏ một scope bắt buộc, AS có thể từ chối hoặc cấp subset, và client phải **xử lý tập quyền thực sự được cấp**.

### 10.1. Tính toàn vẹn giữa UI và server

Không tin các checkbox do browser gửi để cấp thêm scope ngoài giao dịch gốc:

~~~text
original_request = {orders.read, reports.export}
browser_submit  = {orders.read, reports.export, payments.refund}

AS phải reject/ignore scope ngoài original_request,
client registration và policy theo contract.
~~~

Danh sách scope/permission trong HTML form có thể bị sửa bằng developer tools. AS phải kiểm tra lại **request đã gắn với transaction ở server**, các tùy chọn hợp lệ, user/tenant/grant policy và CSRF/Origin protections.

### 10.2. Group scope để giảm quá tải nhận thức, nhưng không giấu quyền

Với hàng chục scopes có thể nhóm:

~~~text
Quyền đọc dữ liệu
  - Xem đơn hàng
  - Xem thông tin khách hàng liên quan

Quyền thay đổi dữ liệu
  - Tạo/cập nhật đơn hàng

Quyền dữ liệu nhạy cảm
  - Xuất danh sách khách hàng
~~~

Nội dung nhóm phải cho phép người dùng **mở xem chi tiết**, nhất là những quyền rủi ro cao. Không gom `payments.refund` và `orders.read` dưới nhãn mơ hồ “Trải nghiệm tốt hơn”.

## 11. Incremental consent: xin quyền khi thực sự cần

**Incremental authorization/consent** là cách ứng dụng ban đầu xin tập quyền tối thiểu, sau đó xin thêm khi user sử dụng một tính năng cần quyền mới. Hành vi cụ thể phụ thuộc AS/provider/profile, không phải mọi authorization server tự động cộng dồn scopes.

Ví dụ:

~~~text
Lần đầu người dùng kết nối:
  requested: openid profile orders.read
  use case:  xem bảng tổng quan đơn hàng

Sau đó người dùng nhấn “Xuất báo cáo”:
  requested: reports.export (và scopes phụ thuộc, nếu cần)
  use case:  tạo file báo cáo

AS kiểm tra grant cũ và chính sách; nếu cần, yêu cầu
consent bổ sung chỉ cho quyền phát sinh.
~~~

**Lợi ích:** người dùng hiểu ngữ cảnh xin quyền, ít bị yêu cầu quá rộng ngay lần đầu, giảm tác động khi token bị lộ. Nhưng client phải dự đoán được trường hợp user từ chối quyền bổ sung và cung cấp UX thay thế.

### 11.1. Không tự hiểu “scope mới = cộng thêm vĩnh viễn”

AS có thể:

- Cấp access token mới với **tập hợp** quyền cũ và mới;
- Cấp token riêng chỉ với **quyền mới/hẹp**;
- Trả token có phạm vi được giảm hoặc yêu cầu user chọn lại;
- Từ chối vì client/user/policy không cho phép.

Client phải đọc **`scope` thực sự được cấp** trong token response hoặc metadata theo contract. Không tái sử dụng assumptions từ consent đã lưu để coi token nào cũng có `reports.export`.

### 11.2. Consent mới khi đổi ngữ nghĩa scope

Nếu trước đây `orders.read` chỉ xem danh sách đơn hàng, nhưng phiên bản mới mở rộng thêm địa chỉ giao hàng/thông tin thanh toán, **mô tả cũ có thể không còn chính xác**. AS/resource owner policy có thể cần:

1. Version catalog và thay đổi được kiểm duyệt;
2. Xác định grant cũ cần **re-consent** hay thu hẹp;
3. Phát hành token với policy nhất quán;
4. Cập nhật audit và giải thích quyền mới;
5. Kiểm tra client không tự sử dụng quyền mới khi user chưa đồng ý hoặc grant chưa được duyệt.

Đừng âm thầm đổi semantics mà vẫn giữ nguyên nhãn mô tả “chỉ xem” nếu app nay có quyền xuất/xóa.

## 12. Scope nhạy cảm và step-up authentication

Quyền như `payments.refund`, `customers.export`, `orders.delete` hoặc quyền quản lý tổ chức có rủi ro cao hơn quyền chỉ đọc thông tin cơ bản. Consent screen phải **diễn đạt đúng tác động**, nhưng đôi khi chỉ đọc và nhấn Cho phép **chưa đủ chính sách bảo mật**.

### 12.1. Có thể cần nhiều lớp kiểm soát

| Lớp | Mục tiêu |
| --- | --- |
| Mô tả rõ trên consent UI | Giúp user hiểu quyền và hậu quả |
| Client registration / app verification | Giới hạn app được xin quyền nhạy cảm |
| Quyền user/administrator | Không cấp quyền vượt thẩm quyền |
| Step-up authentication | Yêu cầu mức/tính mới xác thực cao hơn khi rủi ro lớn |
| Approval workflow | Ví dụ admin/two-person approval theo chính sách nội bộ |
| Token TTL/sender constraint | Giới hạn tác động khi access token bị lấy |
| Resource-server authorization | Kiểm tra số tiền, tenant, object ownership và business rules |

### 12.2. OIDC `prompt`, `max_age`, `acr_values` không phải scopes

Một OIDC request có thể yêu cầu:

~~~text
scope=openid payments.refund
prompt=login
max_age=300
acr_values=urn:example:loa:high
~~~

Những tham số trên liên quan **yêu cầu tương tác và mức/tính mới của authentication**, không tự cấp `payments.refund`. Client phải kiểm tra kết quả authentication thực tế (`auth_time`, `acr`, `amr` khi profile/policy dùng), và AS phải kiểm tra quyền refund độc lập.

`prompt=consent` trong OIDC yêu cầu OP tạo ngữ cảnh xin lại consent theo profile; **không bảo đảm mọi yêu cầu scope được chấp thuận**. Một số hệ thống có thể cần prompt hoặc approval phù hợp khi offline access.

### 12.3. Không giấu quyền nhạy cảm trong scope nhóm

Nếu `payments.manage` thực tế bao gồm **refund** và **payout**, nhãn “Quản lý thanh toán” có thể chưa đủ. User cần thấy rõ thao tác tài chính thực tế hoặc phần giải thích chi tiết. Nếu scope quá rộng để giải thích trung thực, cân nhắc **thiết kế scope nhỏ hơn** theo action/resource thay vì chỉ chỉnh câu chữ.

## 13. Rich Authorization Requests: khi scope đơn giản không đủ

Một scope như `payments.write` không mô tả được **số tiền, người nhận, loại giao dịch hoặc thời hạn**. **RFC 9396 — Rich Authorization Requests (RAR)** định nghĩa cách client biểu diễn `authorization_details` theo cấu trúc, khi AS hỗ trợ.

Ví dụ một request theo profile **giả định**, JSON trước khi URL-encode hoặc đẩy qua back-channel:

~~~json
[
  {
    "type": "payment_initiation",
    "actions": ["initiate"],
    "locations": ["https://api.example.com/payments"],
    "instructedAmount": {
      "currency": "VND",
      "amount": "500000"
    },
    "creditorName": "Nha cung cap A"
  }
]
~~~

Các trường nghiệp vụ minh họa phụ thuộc profile/AS, **không phải schema chung bắt buộc của mọi RAR implementation**. Khi consent cần theo giao dịch, màn hình có thể mô tả:

~~~text
Ứng dụng Thanh toán đề nghị:

Tạo một lệnh chuyển 500.000 VND
Người nhận: Nhà cung cấp A
Nguồn tiền/tài khoản: tài khoản đã chọn và được phép

Chỉ áp dụng cho giao dịch được xác nhận.

[Từ chối]       [Xác nhận yêu cầu]
~~~

**Không để client tự ghi “500.000 VND” vào text consent còn AS thực sự cấp quyền chuyển số tiền tùy ý.** AS phải hiển thị **giá trị đã canonicalize/validate và ràng buộc với authorization details được cấp**. Resource server phải xác minh transaction binding và hạn mức trước khi thực hiện.

### 13.1. Scope và `authorization_details` có thể cùng tồn tại

`scope` mô tả quyền chung (ví dụ xem thanh toán), trong khi `authorization_details` mô tả quyền cụ thể theo một nghiệp vụ. AS cần quyết định sự kết hợp được phép, tránh cấp quyền rộng hơn nội dung user đồng ý.

### 13.2. Bảo vệ dữ liệu RAR khỏi URL/logs

JSON quyền nhạy cảm hoặc dữ liệu cá nhân có thể quá dài và không phù hợp đặt vào browser query. **Pushed Authorization Requests (PAR, RFC 9126)** và **JWT-Secured Authorization Requests (JAR, RFC 9101)** có thể giảm lộ/thay đổi request khi được hỗ trợ. Tuy nhiên, PAR/JAR **không tự bảo đảm consent text chính xác**; AS vẫn phải kiểm tra dữ liệu, render an toàn và áp grant policy.

## 14. Consent phải được gắn với đúng client, user, tenant và resource

Một consent record **không nên chỉ là** `userId=42, consented=true`. Nếu thiếu ngữ cảnh, một lần đồng ý xem hồ sơ có thể vô tình được dùng để cấp quyền ghi dữ liệu ở tổ chức khác.

Một record logic có thể gồm:

~~~text
ConsentGrant:
  grant_id
  issuer_id
  resource_owner_id
  oauth_client_id
  resource_audience
  tenant_id                  (khi chính sách có tenant binding)
  scopes_granted
  authorization_details      (khi áp dụng)
  permission_catalog_version
  consent_ux_version
  approved_at
  expires_at / policy_version
  revoked_at
  approval_actor_type        (user/admin/policy theo contract)
~~~

Đây là **mô hình dữ liệu minh họa**, không phải trường RFC yêu cầu. Một AS có thể có grant từ admin, session, policy hoặc user tương tác; các loại grant phải được phân biệt để tránh nhầm consent user với quyền tổ chức.

### 14.1. Không “tái sử dụng consent” sai ngữ cảnh

| Tình huống | Có nên tự coi consent cũ đủ? |
| --- | --- |
| Cùng client, user, resource, scopes, tenant, policy còn hiệu lực | Có thể, nếu AS cho phép |
| Cùng client nhưng thêm `orders.write` | **Không** tự cấp quyền mới; kiểm tra/re-consent |
| Cùng app nhưng đổi từ Acme sang Globex | **Không** tự mở rộng qua tenant nếu grant không cho |
| Cùng scope name nhưng đổi sang Payments API | **Không** nếu audience/resource khác |
| Client đổi publisher/ownership theo chính sách nghiêm ngặt | Cần đánh giá lại trust/consent |
| Scope được tái định nghĩa nhạy cảm hơn | Cần version/policy và có thể re-consent |
| User bị xóa khỏi organization | Grant/token phải bị giới hạn/thu hồi theo policy |

### 14.2. Consent log khác token storage

Một consent record có thể lưu **metadata về quyền** và thời điểm quyết định. Nó **không nên lưu raw access token, refresh token hoặc authorization code chỉ để audit**. Để truy vết, lưu grant ID/token ID đã kiểm soát, key aliases, client/tenant references và event outcome, giới hạn retention theo chính sách.

### 14.3. Tính đồng thời khi hai cửa sổ consent hoạt động

Hai browser tabs có thể mở hai authorization transactions với state, scopes, tenant khác nhau. AS phải ràng buộc form submit với **đúng transaction**, chống CSRF, kiểm tra transaction còn hiệu lực và **không dùng một biến consent global** cho request mới nhất.

Nếu user đã revoke consent ở tab A trong khi tab B đang approve dựa trên dữ liệu cũ, AS cần chính sách version/consistency phù hợp; không khôi phục quyền đã revoke chỉ vì một form cũ được submit muộn.

## 15. Bảo vệ consent screen khỏi giả mạo và lạm dụng

Consent UI thường ở **authorization server đáng tin**, nhưng attacker vẫn có thể dẫn dụ user tới một authorization request có thật của client độc hại.

### 15.1. Consent phishing

Một attacker tạo app có tên gần giống app nội bộ rồi gửi link:

~~~text
https://auth.example.com/authorize?
  client_id=unverified-lookalike-app
  &scope=profile%20email%20reports.export
  &response_type=code
  &...
~~~

Người dùng thấy **domain đăng nhập thật** nhưng client được phê duyệt có thể là ứng dụng attacker đã đăng ký. OAuth không đảm bảo mọi client được đăng ký đều là ứng dụng đáng tin.

Biện pháp:

- Hiển thị tên client, **publisher đã xác minh khi có**, mức độ tin cậy và các quyền yêu cầu.
- Không chấp nhận brand/logo hoặc nội dung consent từ URL tùy ý.
- App verification/review và restrict sensitive scopes theo registration.
- Cảnh báo “Chỉ phê duyệt nếu bạn chủ động kết nối ứng dụng này”.
- Không buộc user đồng ý các quyền không cần để hoàn tất hành động cơ bản.
- Kiểm tra abuse rate, client provenance và authorization anomalies.

**Trang AS thật không bảo đảm yêu cầu quyền là an toàn.** Consent là quyết định của người dùng trên **một giao dịch cụ thể**, cần đầy đủ thông tin.

### 15.2. Open redirect và giả mạo publisher

AS phải xác minh `redirect_uri` theo đăng ký, không chuyển authorization code sang URI tùy ý; client không được dùng redirect callback làm open redirect. Mô tả permission, tên client hoặc logo từ nguồn ngoài phải được kiểm duyệt/sanitize để tránh XSS và clickjacking.

### 15.3. Chống CSRF và clickjacking trên màn hình consent

Một POST **Approve/Deny** phải gắn với:

1. User session đã xác thực và đúng identity;
2. Authorization transaction/state tương ứng;
3. CSRF token hoặc biện pháp chống CSRF phù hợp;
4. Chính sách Origin/Referer và cookie SameSite khi cần;
5. Client/resource/scopes/tenant đã được server validate;
6. Transaction chưa hết hạn/chưa dùng/chưa bị hủy.

**Không tự động approve qua GET request** hoặc dựa chỉ vào query parameter `approved=true`. Áp các biện pháp chống clickjacking thích hợp (như CSP `frame-ancestors`), session fixation protection và HTTPS.

### 15.4. PKCE không phải cơ chế consent

**PKCE (RFC 7636)** ràng buộc authorization code với verifier để giảm code interception. Nó **không chứng minh user đã xem và đồng ý những quyền được hiển thị**; không thay CSRF defense, app verification, redirect validation hoặc permission catalog.

## 16. Ngôn ngữ, accessibility và minh bạch quyền

Một consent screen chính xác về kỹ thuật nhưng khó đọc, dùng tiếng Anh xen tiếng Việt thiếu nhất quán hoặc ẩn nút từ chối vẫn có thể dẫn đến quyết định sai.

### 16.1. Nguyên tắc viết nhãn

| Nên | Tránh |
| --- | --- |
| “Xem các đơn hàng bạn được phép truy cập” | “read_0x56 / SCOPE_ORDERS_READ” |
| “Thêm hoặc cập nhật đơn hàng” | “Cải thiện trải nghiệm ứng dụng” |
| “Xuất dữ liệu khách hàng” | “Quản lý liên hệ” nếu gồm bulk export |
| “Duy trì kết nối khi bạn không mở ứng dụng” | “Giữ kết nối” nếu không nói tới offline access |
| “Áp dụng cho tổ chức Acme” | “Trên tài khoản của bạn” khi có nhiều tenants |
| “Bạn có thể thu hồi trong phần Ứng dụng đã kết nối” | “Bạn có toàn quyền kiểm soát” nhưng không có cách revoke thực tế |

### 16.2. Khả năng truy cập và thiết bị nhỏ

- Nhãn và mô tả phải có thứ tự đọc rõ cho screen reader;
- Checkbox/button có label, trạng thái focus/keyboard navigation;
- Không dùng màu duy nhất phân biệt quyền đọc/ghi hoặc rủi ro;
- Không đặt quyền nhạy cảm sau nút “Xem thêm” khó phát hiện;
- Hiển thị phạm vi tenant, client identity và consent action trên màn hình nhỏ;
- Có khả năng xem quyền theo nhóm, nhưng **không giấu** quyền riêng tư/tài chính quan trọng.

### 16.3. Tránh kỹ thuật thao túng quyết định

Không đặt nút **Cho phép** nổi bật quá mức và **Từ chối** gần như không nhìn thấy, không dùng thông điệp gây sợ hãi thiếu căn cứ, và không tự đánh dấu mọi scope nhạy cảm là approved nếu policy yêu cầu lựa chọn tường minh.

**Nội dung phải đúng với quyền được cấp**, kể cả khi user đổi ngôn ngữ hoặc UI được thử A/B. Cần đối chiếu định kỳ bản dịch và scope catalog bằng review chuyên môn.

## 17. Java 17: tạo quyền hiển thị từ catalog đáng tin

Ví dụ sau minh họa một **permission catalog server-side**. Authorization server kiểm tra scopes được yêu cầu và client registration, sau đó mới trả danh sách permission view từ catalog đã kiểm duyệt. **Đây là Java domain code minh họa, không phải API có sẵn trong Spring Authorization Server.**

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.Set;

public final class ConsentPermissionCatalog {
    public record PermissionDefinition(
        String scope,
        String titleVi,
        String descriptionVi,
        String risk
    ) {}

    public record PermissionView(
        String scope,
        String title,
        String description,
        String risk
    ) {}

    private static final Map<String, PermissionDefinition> CATALOG =
        Map.of(
            "orders.read",
            new PermissionDefinition(
                "orders.read",
                "Xem đơn hàng",
                "Xem đơn hàng trong tổ chức được cấp quyền",
                "standard"
            ),
            "orders.write",
            new PermissionDefinition(
                "orders.write",
                "Tạo hoặc cập nhật đơn hàng",
                "Thay đổi đơn hàng khi có quyền tương ứng",
                "sensitive"
            ),
            "reports.export",
            new PermissionDefinition(
                "reports.export",
                "Xuất báo cáo",
                "Tải xuống báo cáo trong phạm vi được cấp",
                "sensitive"
            )
        );

    private ConsentPermissionCatalog() {}

    public static List<PermissionView> forConsent(
        Set<String> requested,
        Set<String> clientRegistered,
        Set<String> permittedByPolicy
    ) {
        if (requested == null
            || clientRegistered == null
            || permittedByPolicy == null
            || requested.isEmpty()) {
            throw new IllegalArgumentException("Invalid scope request");
        }

        // Ví dụ cố ý fail closed thay vì lặng lẽ giấu scope lạ.
        if (!CATALOG.keySet().containsAll(requested)
            || !clientRegistered.containsAll(requested)
            || !permittedByPolicy.containsAll(requested)) {
            throw new IllegalArgumentException(
                "Requested scopes are not displayable or permitted"
            );
        }

        List<PermissionView> views = new ArrayList<>();
        requested.stream().sorted().forEach(scope -> {
            PermissionDefinition def = CATALOG.get(scope);
            views.add(new PermissionView(
                def.scope(),
                def.titleVi(),
                def.descriptionVi(),
                def.risk()
            ));
        });
        return List.copyOf(views);
    }
}
~~~

**Ý nghĩa:**

1. Không nhận title/description từ authorization query của client.
2. Scope chưa biết, chưa đăng ký hoặc trái policy **không được im lặng ẩn đi nhưng vẫn cấp token**.
3. Trong ví dụ, server **từ chối toàn bộ** nếu scope không được phép; một AS hỗ trợ **partial grant** có thể dùng thuật toán khác nhưng phải đồng bộ UI/decision/token.
4. Đã có danh sách hiển thị **không đồng nghĩa đã được cấp**. Sau đó AS còn xác thực user, hỏi consent/kiểm tra grant, tạo quyết định và lưu grant.
5. Trong hệ thống thật phải map theo **issuer, resource, client/tenant policy và locale**, xử lý các scope phụ thuộc, risk-level và versioning.
6. HTML rendering vẫn phải escape dữ liệu và dùng template an toàn; không dùng `innerHTML` để chèn text chưa được tin.

### 17.1. Không nhầm scope display với Spring authority

Tại RS, một scope như `orders.read` thường được Spring Security ánh xạ thành `SCOPE_orders.read` khi provider/profile phù hợp. Nhưng **`PermissionView.title()` không phải authority**; thay nhãn tiếng Việt không được thay quyền đang được API kiểm tra.

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class OrdersResourceSecurity {
    @Bean
    SecurityFilterChain filterChain(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .requestMatchers(HttpMethod.POST, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.write")
                .anyRequest().authenticated()
            )
            .oauth2ResourceServer(oauth2 ->
                oauth2.jwt(Customizer.withDefaults()))
            .build();
    }
}
~~~

**Snippet chưa đủ cho production**: cần cấu hình `JwtDecoder` theo trusted issuer, **audience validator**, JWS algorithm/key policy, token type, principal type, tenant/ownership, revocation và CORS/CSRF tùy kiến trúc. Opaque token có thể dùng introspection thay JWT decoder. Scope mapping mặc định có thể phải tùy chỉnh theo AS.

## 18. Quy trình server-side quyết định consent an toàn

Một flow tổng quát, bất kể UI được xây bằng Spring MVC, frontend template hay framework khác:

~~~mermaid
sequenceDiagram
    autonumber
    actor U as User
    participant C as OAuth Client
    participant AS as Authorization Server
    participant DB as Grant/Consent Store
    participant RS as Resource Server
    C->>AS: /authorize với scopes, client_id, state, PKCE
    AS->>AS: Validate registration, redirect, issuer, scopes/resource
    AS->>U: Login nếu cần; render permission catalog đã kiểm duyệt
    U->>AS: Approve subset/All hoặc Deny qua CSRF-protected POST
    AS->>AS: Revalidate transaction, user, policy, scopes
    AS->>DB: Persist consent/grant metadata đúng ngữ cảnh
    AS-->>C: Authorization code + state
    C->>AS: POST /token với code + PKCE verifier
    AS-->>C: Token với quyền thực sự được cấp
    C->>RS: Bearer access token
    RS->>RS: Validate token, scope, tenant và tài nguyên
~~~

**Giao dịch có thể không đi qua consent screen** nếu AS có grant/policy hợp lệ đã lưu. Khi đó AS vẫn phải xác định quyền được cấp qua các nguồn đáng tin, không chỉ tin yêu cầu từ client.

### 18.1. Pseudocode AS

~~~text
handleConsentDecision(transactionId, userSession, submittedSelection):
    require authenticated(userSession)
    require csrf_and_origin_valid()

    tx = trustedStore.load(transactionId)
    require tx.active && !tx.expired && !tx.consumed
    require tx.user_context_matches(userSession)
    require registeredClient(tx.client_id)
    require redirect_uri_and_issuer_binding_valid(tx)

    requested = tx.original_requested_scopes
    registered = policy.registeredScopes(tx.client_id)
    permitted = policy.allowedScopes(userSession, tx.resource, tx.tenant)

    require submittedSelection subset_of requested
    require submittedSelection subset_of registered
    require submittedSelection subset_of permitted
    require dependencies_and_risk_policy_hold()
    require correct_admin_authority_if_needed()

    if user_denied:
        mark_transaction_denied()
        return OAuth_access_denied

    atomically_mark_transaction_approved_and_save_grant(
        subject, client, resource, tenant,
        submittedSelection, policyVersion, catalogVersion
    )

    issue_authorization_code_bound_to_transaction()
~~~

**Không tin `submittedSelection` chỉ vì form do server render.** Browser có thể sửa các checkbox, client ID, tenant, transaction ID và CSRF fields nếu không có bảo vệ. AS phải lấy **original request** từ transaction được server kiểm soát và kiểm tra lại mọi ràng buộc.

### 18.2. Không kết thúc authorization bằng việc ghi một boolean

Sai:

~~~text
userId=42, approved=true
~~~

An toàn hơn: lưu **client, audience/resource, scopes, tenant, quyền cụ thể, actor, phiên bản, expiry và revocation state**. Nếu không thể xác định user đã đồng ý quyền gì, rất khó chứng minh hệ thống không cấp vượt consent trước đó.

## 19. Client phải xử lý scope được cấp thực tế, không tin scope đã xin

Sau khi user đồng ý và client đổi authorization code, AS có thể cấp token response:

~~~json
{
  "access_token": "<opaque-or-jwt-access-token>",
  "token_type": "Bearer",
  "expires_in": 900,
  "scope": "orders.read"
}
~~~

Giả sử client ban đầu yêu cầu `orders.read orders.write`. Trong ví dụ này chỉ `orders.read` được cấp, vì user/policy từ chối `orders.write` hoặc AS downscope theo contract.

### 19.1. Những gì client nên làm

1. Kiểm tra token response hợp lệ, `token_type` được hỗ trợ, hạn và issuer/AS dự kiến.
2. Xác định **tập scope thực tế được cấp** theo token response và contract RFC 6749/provider. Nếu response không có `scope`, hiểu ý nghĩa theo quy tắc giao thức và issuer, **không tự giả định toàn bộ scopes khi AS đã giới hạn quyền theo cách không được biểu diễn**.
3. Chỉ bật các tính năng tương ứng quyền được cấp và điều kiện tài nguyên thực tế.
4. Nếu thiếu scope cần thiết, hướng dẫn user xin thêm quyền/đăng nhập lại theo luồng được AS hỗ trợ, không retry tự động xin quyền rộng vô hạn.
5. Không lưu raw token trong analytics, URL, localStorage bền vững nếu threat model không cho phép.
6. Không tự tuyên bố “Đã kết nối thành công với toàn quyền” nếu grant chỉ là một subset.

### 19.2. RFC 6749 và trường `scope` trong token response

Trong OAuth 2.0, trường `scope` ở token response **bắt buộc khi phạm vi được cấp khác phạm vi client yêu cầu**, theo quy định của profile liên quan. Khi vắng mặt và token response hợp lệ, client có thể áp rules của grant/issuer; nhưng với hệ thống đa resource, nhiều claims hoặc AS extensions, nên thống nhất contract rõ để tránh đoán quyền.

**Bài học thực tế:** giao diện consent có thể ghi “Cho phép xem đơn hàng”, nhưng token cuối cùng vẫn là nguồn mà **resource server phải xác minh** trước khi thực hiện API call.

### 19.3. Client không phải bên quyết định scope cuối cùng

Sai:

~~~javascript
// SAI: chỉ nhìn request cũ mà bỏ qua kết quả AS.
const canDeleteOrders = requestedScopes.includes("orders.delete");
~~~

Tốt hơn về mặt hiển thị chức năng:

~~~javascript
// grantedScopes là dữ liệu đã lấy/được xác nhận theo
// token response và AS contract, không phải URL tự khai.
const canShowDeleteOption = grantedScopes.has("orders.delete");
~~~

**Ẩn/hiện nút ở client chỉ là UX.** API vẫn phải enforce `orders.delete`, tenant, ownership và business policy. Không coi client-side feature flag là authorization.

## 20. Token validation: JWT, opaque và giới hạn của consent

Consent **không phải một token có thể gửi tới API**. Sau khi AS cấp access token, RS kiểm tra token theo profile:

| Kiểm tra | JWT access token | Opaque access token |
| --- | --- | --- |
| Issuer/trust | Signature, JWS algorithm/key, `iss` | AS introspection/lookup theo trust contract |
| Audience | Validate `aud` | Check resource/audience metadata hoặc binding |
| Thời hạn | `exp`, `nbf`, clock skew policy | `active`, `exp` và trạng thái AS theo contract |
| Scope được cấp | Claims/authorities thực tế | Metadata introspection `scope` |
| Principal | User/app-only, client ID/subject theo profile | Metadata principal/grant |
| Quyền resource | Tenant, role, ownership, business rules | Tenant, role, ownership, business rules |
| Thu hồi | Denylist/version/lookup hoặc TTL ngắn | Introspection/cache/invalidation theo AS policy |

### 20.1. Consent `orders.read` không vượt được tenant policy

User Acme approve `orders.read` cho Reports App; token có scope đó. Client gọi:

~~~http
GET /api/tenants/globex/orders/42 HTTP/1.1
Host: api.example.com
Authorization: Bearer <access-token-for-acme>
~~~

Orders API phải từ chối nếu token/grant chỉ cho tenant Acme hoặc user không có quyền với order 42. **Đồng ý cấp scope không cấp thêm quyền sở hữu bản ghi hoặc quyền trên tenant khác.**

### 20.2. Token đã phát có thể còn hiệu lực sau khi consent bị thu hồi

Đây là điểm cần giải thích trung thực trong UX “Thu hồi quyền kết nối”:

~~~text
10:00  User approve orders.read -> AS phát JWT exp=10:15
10:05  User revoke consent/grant
10:06  RS chỉ validate JWT offline, không tra revocation
10:15  JWT hết hạn
~~~

Nếu RS chỉ kiểm tra chữ ký và `exp`, token đã phát có thể còn hiệu lực **đến hạn** dù grant không còn được cấp token mới. Một số hệ thống có denylist, token state checks, TTL ngắn hoặc introspection có thể vô hiệu sớm; với opaque token, cache `active=true` cũng có thể tạo độ trễ.

**Không hứa “thu hồi quyền có hiệu lực tức thì ở mọi API” nếu kiến trúc chưa thực sự bảo đảm.** User-facing text, SLA và xử lý sự cố phải đúng thiết kế thu hồi, token cache và TTL.

### 20.3. Sender-constrained token không thay consent

**DPoP (RFC 9449)** hoặc **mTLS-bound token (RFC 8705)** có thể giảm replay nếu access token bị sao chép. Nhưng sender proof đúng **không tự chứng minh user đồng ý scopes**; RS vẫn kiểm tra quyền, issuer/audience, tenant và policy.

## 21. Quản lý và thu hồi consent

Người dùng nên có một nơi dễ tìm để xem và quản lý các ứng dụng đã kết nối, nếu sản phẩm hỗ trợ delegated grants:

~~~text
ỨNG DỤNG ĐÃ KẾT NỐI

Báo cáo Nội bộ
  Tổ chức: Acme
  Quyền đã cấp:
    - Xem đơn hàng
    - Xuất báo cáo
  Cấp quyền: 15/11/2026
  Trạng thái: Đang hoạt động

  [Xem chi tiết]  [Thu hồi quyền kết nối]
~~~

Các nội dung này phải được lấy từ **consent/grant store đáng tin**, không phải danh sách scopes client tự khai. Các scopes có thể bị giới hạn theo tenant, account và từng resource. Nếu nhiều grants, UI phải tránh thu hồi nhầm toàn bộ client khi người dùng chỉ muốn ngắt kết nối một tổ chức.

### 21.1. Thu hồi consent, token revocation và logout khác nhau

| Hành động | Ý nghĩa | Điều cần chú ý |
| --- | --- | --- |
| **Từ chối consent** | Không cấp grant theo authorization request hiện tại | Không tự xóa grants cũ trừ khi chính sách quy định |
| **Thu hồi consent/grant** | Rút quyền cho client tiếp tục hành động theo grant | AS cần xử lý token/refresh state tương ứng |
| **Token revocation (RFC 7009)** | Yêu cầu AS làm token/grant không còn hiệu lực theo policy | RS cache/JWT offline có thể còn cửa sổ trễ |
| **Logout user khỏi AS/OP** | Kết thúc một user authentication session | Không mặc định thu hồi mọi OAuth access/refresh token đã cấp |
| **Xóa ứng dụng trên máy** | Xóa code/app ở device | Không mặc định thu hồi token đang giữ ở server của app |

Vì vậy, nếu người dùng bấm **“Thu hồi quyền kết nối”**, hệ thống phải định nghĩa cụ thể: thu hồi refresh token family? vô hiệu grant? từ chối refresh mới? access token đã phát có bị denylist/introspect không? Có thể cần quy trình thu hồi tức thời cho quyền nhạy cảm và thông báo đúng thực tế.

### 21.2. Các thay đổi cần kích hoạt đánh giá lại consent

- Client xin **scope mới** hoặc quyền thao tác nhạy cảm hơn;
- Scope cũ có **semantics mới** hoặc dữ liệu bổ sung;
- User chuyển sang **tenant/resource khác**;
- Thay đổi publisher/app ownership theo policy;
- User hoặc admin thu hồi một phần grant;
- User mất membership/role, client bị disable hoặc policy compliance thay đổi;
- Refresh token family có dấu hiệu reuse/compromise.

Không phải mọi thay đổi luôn đòi user tương tác lại; một số policy phải **tự giảm hoặc thu hồi quyền** ngay, không cho user tự cho phép vượt policy.

## 22. Lỗi OAuth và thông báo user-facing

Consent UI cần xử lý cả **Từ chối** lẫn lỗi cấu hình, không biến lỗi kỹ thuật thành “user chưa cấp đủ quyền” theo cách gây hiểu nhầm.

| Lỗi/trạng thái | Nguồn | Hành động đúng |
| --- | --- | --- |
| `access_denied` | User/AS từ chối authorization | Kết thúc giao dịch, thông báo không cấp quyền |
| `invalid_scope` | Scope không hợp lệ/không được phép | Sửa client registration/request, không hiện nhãn scope giả |
| `unauthorized_client` | Client không được dùng flow/permissions | AS từ chối, không buộc user “approve mạnh hơn” |
| `invalid_request` | Authorization request malformed | Không cấp code/token, chẩn đoán parameter |
| `login_required` | OIDC không thể silent authentication | Đưa user vào tương tác thích hợp khi được phép |
| `consent_required` | OIDC thiếu consent khi `prompt=none` | Tương tác consent hợp lệ nếu policy cho phép |
| `invalid_grant` | Token exchange code/reuse/PKCE sai | Khởi tạo flow đúng, không tự tạo scope/consent |
| `401 invalid_token` từ RS | Token thiếu/sai/hết hạn | Xử lý token lifecycle, không sửa consent UI để bỏ validation |
| `403 insufficient_scope` từ RS | Token hợp lệ nhưng thiếu scope endpoint | Có thể đề xuất incremental consent theo AS policy |
| `403`/object denial | Business authorization | Từ chối truy cập, không tự xin scope admin để vượt |

Ví dụ:

~~~http
HTTP/1.1 302 Found
Location: https://reports.example.com/callback?error=access_denied&state=<matching-state>
~~~

Client phải kiểm tra `state` của authorization response **kể cả khi user từ chối**; không render trực tiếp `error_description` không tin cậy thành HTML và không lộ authorization code/token vào log.

### 22.1. Không ép user tiếp tục đồng ý

Nếu user từ chối `reports.export`, ứng dụng có thể tiếp tục chế độ **xem online** nếu có quyền `orders.read`, hoặc giải thích lý do tính năng export không hoạt động. **Không retry vô hạn hoặc dùng scope khác để lách quyết định từ chối.**

## 23. Các tình huống thực tế

**Tình huống A — Hiển thị “Chỉ xem” nhưng AS cấp `orders.write`.**

Màn hình consent sai hoặc grant mapping bị lỗi. Cần kiểm toán catalog, client registration, logic consent và token issuance; không chỉ sửa chữ trong UI. Có thể cần revoke tokens/grants đã cấp vượt thông báo.

**Tình huống B — Client xin `profile email`, user hiểu là đọc toàn bộ tài khoản.**

Mô tả chưa rõ hoặc nhầm OIDC scopes. Cần hiển thị đúng các nhóm claims có thể được chia sẻ, phân biệt `openid` (authentication) với API permissions, tránh hứa mọi dữ liệu chắc chắn có.

**Tình huống C — User Acme approve, Reports App đọc Globex.**

Consent record/AS token thiếu tenant binding hoặc RS bỏ tenant authorization. Phải giới hạn quyền theo grant và record ownership; hiển thị đúng organization.

**Tình huống D — App xin offline access nhưng UI chỉ ghi “Đăng nhập”.**

User không biết app có thể tiếp tục truy cập khi họ không mở ứng dụng. Bổ sung mô tả quyền truy cập nền và nơi revoke; AS/OP vẫn quyết định có cấp refresh token không.

**Tình huống E — User từ chối quyền xuất báo cáo.**

Ứng dụng không được coi requested scopes là granted scopes. Bật tính năng read-only khi policy cho phép và chỉ xin lại export có ngữ cảnh khi user yêu cầu.

**Tình huống F — Client trá hình đặt tên giống ứng dụng nội bộ.**

Trang AS thật không giải quyết nguy cơ consent phishing. AS cần xác minh app/publisher nếu hiển thị “trusted”, hạn chế scope nhạy cảm và giải thích resource/risk rõ.

**Tình huống G — Một scope đổi nghĩa sau bản phát hành API.**

Quyền `customers.read` trước đây chỉ xem tên; nay còn gồm thông tin nhận diện nhạy cảm. Cần review lại catalog, version grant, re-consent hoặc thu hồi/giảm quyền nếu chính sách đòi hỏi.

**Tình huống H — Consent đã revoke nhưng JWT vẫn dùng được thêm vài phút.**

RS xác minh JWT offline nên không thấy grant revoked cho tới `exp`, hoặc cache introspection còn stale. Cần xác định SLA, TTL, revoke/denylist/invalidation và thông báo đúng.

**Tình huống I — Scope `read` của nhiều API được gộp thành một dòng.**

Consent UI chỉ ghi “Xem dữ liệu”, không nêu Orders/Payments. Cần phân biệt `resource`/`audience`, tên dịch vụ và loại dữ liệu để user không đồng ý mù quáng.

**Tình huống J — Nhấn Cho phép khi chưa xác thực người dùng.**

Một form POST approval được xử lý theo session cookie cũ/không đúng user. AS phải enforce authentication, CSRF, transaction binding, đúng user và scope/policy trước khi cấp grant.

## 24. Bộ kiểm thử bảo mật và tính trung thực của consent

| Test case | Kỳ vọng |
| --- | --- |
| Client xin `orders.read` đã đăng ký | AS hiển thị đúng nhãn/description được kiểm duyệt |
| Client xin `orders.write` nhưng UI ghi “Chỉ xem” | Kiểm thử mapping thất bại; không cấp grant sai mô tả |
| Client xin scope không tồn tại | Từ chối/giải quyết theo policy, không cấp scope bị ẩn |
| Client xin scope ngoài registration | Không cấp quyền vượt đăng ký |
| Scope đúng nhưng user không có entitlement | AS không cấp vượt user policy |
| User bỏ chọn scope tùy chọn khi AS hỗ trợ partial grant | Token chỉ chứa phạm vi được cấp |
| Client cố gửi scope mới trong POST consent form | AS từ chối scope ngoài transaction gốc |
| User từ chối hoàn toàn | Không cấp grant; callback `access_denied` đúng state |
| Consent form submit không có CSRF proof | AS không cho approve |
| Consent form được replay sau transaction consumed | Không cấp lại grant/token trái policy |
| Consent form của tab/issuer khác | Không trộn transaction hoặc issuer |
| Client self-reported HTML trong permission description | AS escape/sanitize, không XSS |
| Client đặt tên gần giống ứng dụng đã xác minh | Không tự nhận trạng thái verified |
| Trình duyệt/ngôn ngữ đổi sang English | Permission semantics không thay đổi |
| Screen reader/keyboard-only | Tên quyền và nút từ chối/cho phép dùng được |
| Scope `openid` | Không mô tả như API admin access |
| Scope `profile`/`email` | Không hứa các claims chưa chắc OP cấp |
| Scope `offline_access` | Hiển thị hệ quả truy cập nền khi grant tương ứng |
| OP không cấp refresh token dù xin offline access | Client/UI không giả định token luôn có |
| Audience Orders vs Payments đều có `read` | Hiển thị rõ resource, không gộp sai |
| User approve Acme nhưng request Globex | AS/RS không mở quyền xuyên tenant |
| User không phải admin nhưng xin org-wide grant | AS từ chối cấp grant toàn tổ chức |
| RAR payment amount bị sửa trên browser | AS reject hoặc dùng giá trị transaction gốc |
| Consent đã lưu nhưng scope tăng hoặc đổi nghĩa | Policy re-consent/downscope/revoke được kiểm tra |
| Hai requests consent đồng thời | Grants đúng client/user/resource và state |
| User revoke grant rồi client xin refresh token | AS tuân revocation policy, không âm thầm tái cấp |
| JWT vẫn còn hạn sau revoke | Kiểm thử cửa sổ revoke theo SLA/denylist/TTL |
| Opaque token introspection cache stale | Hạn cache không vượt policy revoke |
| Access token thiếu `orders.write`, API POST orders | RS trả thiếu quyền, không tin consent text |
| Token đúng scope nhưng bản ghi khác tenant | RS từ chối object-level access |
| Token DPoP/mTLS-bound thiếu sender proof | RS từ chối |
| Raw scopes/PII/token/code xuất hiện trong logs | Security/privacy review thất bại |
| UI chỉ có nút Allow, khó tìm Deny | UX/security review thất bại theo yêu cầu sản phẩm |

### 24.1. Kiểm thử tích hợp theo chuỗi AS → client → RS

1. Gửi authorization request với scopes, `client_id`, `redirect_uri`, `state` và PKCE.
2. Xác nhận **catalog UI** hiển thị đúng quyền theo resource/tenant/client.
3. Chọn Approve/Deny/partial theo khả năng AS; thử sửa form bằng test client.
4. Đổi authorization code lấy token và kiểm tra **granted scopes**.
5. Gọi RS với JWT hoặc opaque token đúng/sai audience và scopes.
6. Thu hồi grant rồi thử refresh/reuse token theo policy và TTL.
7. Kiểm tra logs/tracing không lộ code, access token, refresh token hoặc dữ liệu nhạy cảm.

**Unit test mock `Authentication` không chứng minh consent UI chính xác hoặc AS không cấp quyền vượt scope.** Cần kiểm tra toàn bộ đường authorization và resource validation.

### 24.2. Kiểm thử phiên bản catalog

Khi thay đổi định nghĩa scope, tự động so permission mapping với API route policy và grant version. Ví dụ `orders.write` được bổ sung quyền `orders.delete` ở service nhưng không cập nhật mô tả là một thay đổi **phải được review**, không coi đó là sửa tài liệu nhỏ.

## 25. Checklist production cho scope hiển thị

1. **Scope catalog được tin:** không dùng text tự do từ authorization request làm mô tả quyền.
2. **Đúng client identity:** tên/app verification/publisher được AS kiểm tra, không tự tuyên bố verified.
3. **Đúng resource/audience:** scope có ý nghĩa trong ngữ cảnh API nhận token.
4. **Đúng tenant và principal:** user/admin/app-only policy rõ, không tự mở rộng qua organization.
5. **Đúng nội dung quyền:** đọc, ghi, xóa, xuất, thanh toán, offline access phải được diễn đạt trung thực.
6. **Không che quyền nhạy cảm:** mô tả thao tác rủi ro, không gom dưới nhãn mơ hồ.
7. **OIDC scopes đúng nghĩa:** `openid`, `profile`, `email`, `phone`, `address`, `offline_access` khác API scopes.
8. **Granted không vượt requested/registered/policy:** partial consent khi AS hỗ trợ phải nhất quán với token.
9. **Approval POST được bảo vệ:** authenticated session, CSRF/Origin, transaction/state/issuer và một-lần xử lý.
10. **Lưu grant đủ ngữ cảnh:** client, user/admin actor, resource, tenant, scopes, authorization details, version, expiry/revoke.
11. **Incremental consent khi có ích:** xin quyền đúng lúc, tránh yêu cầu quá rộng từ đầu.
12. **RAR/PAR/JAR theo contract:** quyền giao dịch cần canonicalize/binding; không tin dữ liệu client tự khai.
13. **Accessible và đa ngôn ngữ:** screen reader, mobile, keyboard, bản dịch cùng semantics.
14. **Không ép user đồng ý:** nút từ chối rõ, xử lý `access_denied` và tính năng giảm quyền.
15. **Client đọc quyền được cấp thực tế:** token response/introspection/profile, không chỉ requested scopes.
16. **RS enforce độc lập:** signature/issuer/audience/time hoặc introspection, scope, tenant, ownership.
17. **Revocation minh bạch:** phân biệt consent revoke, token revoke và logout; xác định TTL/cache/SLA.
18. **Bảo vệ credential và privacy:** không log raw code/tokens/PII/consent form secrets, bảo vệ audit.
19. **Test trường hợp sai và concurrency:** form tampering, multi-tab, unknown scope, cross-tenant, stale cache, malicious client.
20. **Đánh giá lại khi scope đổi nghĩa:** version catalog, policy update và re-consent/revoke khi cần.

## 26. Tài liệu tham khảo

- [RFC 6749 — The OAuth 2.0 Authorization Framework](https://www.rfc-editor.org/rfc/rfc6749): `scope`, authorization request, user authorization decision, token response và client/resource roles.
- [RFC 9700 — Best Current Practice for OAuth 2.0 Security](https://www.rfc-editor.org/rfc/rfc9700): bảo vệ OAuth grants, redirect, client và token.
- [OpenID Connect Core 1.0](https://openid.net/specs/openid-connect-core-1_0.html): `openid`, standard scopes, claims, `prompt`, `offline_access`, ID token và UserInfo.
- [RFC 8707 — Resource Indicators for OAuth 2.0](https://www.rfc-editor.org/rfc/rfc8707): phân biệt resource/audience với scope.
- [RFC 9396 — OAuth 2.0 Rich Authorization Requests](https://www.rfc-editor.org/rfc/rfc9396): `authorization_details` và quyền có cấu trúc.
- [RFC 9126 — OAuth 2.0 Pushed Authorization Requests](https://www.rfc-editor.org/rfc/rfc9126): bảo vệ request qua PAR.
- [RFC 9101 — JWT-Secured Authorization Request](https://www.rfc-editor.org/rfc/rfc9101): Request Object/JAR.
- [RFC 7636 — Proof Key for Code Exchange (PKCE)](https://www.rfc-editor.org/rfc/rfc7636): code interception protection, không thay consent.
- [RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068): `scope`, issuer/audience và access token validation.
- [RFC 7662 — OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662): trạng thái và metadata opaque/JWT access token.
- [RFC 7009 — OAuth 2.0 Token Revocation](https://www.rfc-editor.org/rfc/rfc7009): thu hồi token/grant và giới hạn.
- [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750): `invalid_token`, `insufficient_scope` và Bearer token security.
- [RFC 9449 — OAuth 2.0 DPoP](https://www.rfc-editor.org/rfc/rfc9449): sender-constrained access token.
- [RFC 8705 — OAuth 2.0 Mutual-TLS](https://www.rfc-editor.org/rfc/rfc8705): certificate-bound access tokens.
- [OWASP API Security Top 10 — Broken Object Level Authorization](https://owasp.org/API-Security/editions/2023/en/0xa1-broken-object-level-authorization/): scope không thay quyền trên bản ghi.
- [Spring Security — OAuth2 Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html): mapping scopes/authorities và validation tại Java API.

**Ghi nhớ:** **Scope hiển thị cho user phải là bản diễn giải trung thực, dễ hiểu và có ngữ cảnh của quyền AS đang xét cấp.** Phải nói rõ **ứng dụng nào**, **loại dữ liệu/thao tác nào**, **resource/tenant nào**, và **có quyền truy cập lâu dài hay không**. Client xin scope không đồng nghĩa AS cấp scope; người dùng đồng ý không thể vượt registration/policy; nhãn consent không phải nguồn quyền. Sau khi cấp, **access token JWT/opaque và resource server mới quyết định quyền thực tế** theo issuer, audience, thời hạn, scope, tenant, ownership, revocation và cơ chế chống token replay phù hợp.
