# User consent và policy

## Mục tiêu học tập

Trong chương **Token issuance** của học phần bảo mật token, phát hành token không chỉ là thao tác tạo chuỗi JWT hoặc ghi một opaque token vào kho dữ liệu. **Authorization Server (AS) phải xác định client được phép yêu cầu quyền gì, chủ thể có quyền gì, tài nguyên nào là đích, có cần người dùng chấp thuận không và chính sách tổ chức cho phép đến mức nào.**

Sau bài này, bạn có thể:

1. Giải thích **user consent** (sự chấp thuận của người dùng) trong OAuth 2.0/OIDC khác với **authentication** (xác thực), **authorization policy** (chính sách ủy quyền) và **quyền truy cập tại API** như thế nào.
2. Mô tả các yếu tố khiến AS **cho phép, từ chối, giảm scope, yêu cầu tương tác hoặc yêu cầu phê duyệt quản trị** khi phát hành access token.
3. Theo dõi một luồng **Authorization Code + PKCE** có bước consent, biết rõ phía nào kiểm tra scope, audience, client, tenant và tài nguyên.
4. Thiết kế giao diện consent rõ mục đích, giới hạn quyền, tránh cấp quyền quá mức và rủi ro **consent phishing**.
5. Hiểu **incremental consent**, consent đã ghi nhớ, quyền truy cập ngoại tuyến, refresh token, rút lại consent và giới hạn của việc thu hồi JWT.
6. Đề xuất kiểm thử **cả luồng được chấp thuận và bị từ chối**, bảo đảm token chỉ được phát hành theo những quyền thực sự đã được chính sách cho phép.

## 1. Consent là gì, và không phải là gì?

Trong một luồng OAuth có người dùng, **consent** là việc Resource Owner (thường là người dùng) thể hiện chấp thuận cho một **client** truy cập tài nguyên theo một số phạm vi và điều kiện. Ví dụ ứng dụng quản lý đơn hàng xin quyền **chỉ đọc** danh sách đơn để hiển thị lịch sử mua sắm.

Một câu hỏi consent có thể được hiểu là:

> “Bạn có đồng ý cho ứng dụng **Báo cáo mua sắm** xem đơn hàng của bạn tại **Orders API** không? Ứng dụng không được sửa hoặc hủy đơn hàng.”

Sự chấp thuận này **không tự tạo quyền mới mà người dùng vốn không có**. Nếu người dùng chỉ được đọc đơn của mình, họ không thể thông qua nút “Đồng ý” để cấp cho ứng dụng quyền đọc toàn bộ đơn của tổ chức.

### Bốn bước dễ bị đánh đồng

| Hoạt động | Câu hỏi giải quyết | Ví dụ |
|---|---|---|
| **Authentication** | Chủ thể nào đang đăng nhập và có được xác thực theo yêu cầu không? | Người dùng đăng nhập với cơ chế xác thực phù hợp. |
| **User consent** | Chủ thể có chấp thuận một client sử dụng phạm vi truy cập được đề nghị không? | Chấp thuận `orders:read` cho ứng dụng báo cáo. |
| **Authorization Server policy** | Client, người dùng, tenant, resource, grant và scope có **được phép** trong hệ thống không? | AS không cho ứng dụng không được phê duyệt xin `payments:refund`. |
| **Resource Server authorization** | Principal có được thực hiện **hành động này trên đối tượng cụ thể** không? | Orders API từ chối đọc order thuộc tenant khác. |

**Cả consent và policy đều cần được thỏa mãn khi chúng áp dụng.** Consent không thay policy; policy cũng không bảo đảm người dùng đã chấp thuận khi luồng bắt buộc phải hỏi họ.

**Lưu ý về thuật ngữ pháp lý:** “OAuth user consent” là một cơ chế ủy quyền kỹ thuật, **không mặc nhiên là sự đồng ý hợp lệ theo pháp luật bảo vệ dữ liệu**. Các yêu cầu về mục đích xử lý dữ liệu, căn cứ pháp lý, rút lại sự đồng ý và lưu vết cần được đánh giá độc lập theo bối cảnh pháp lý thực tế.

## 2. Tại sao không phát hành token chỉ vì người dùng đã đăng nhập?

Giả sử `shop-web` và `untrusted-exporter` đều đưa người dùng đến cùng một AS và người dùng đã đăng nhập thành công. Nếu AS lập tức phát access token mang `scope=orders:read payments:refund` chỉ vì có phiên đăng nhập, ứng dụng độc hại có thể lạm dụng danh tính người dùng để xin quyền chưa được cho phép.

AS cần xét **nhiều ranh giới**:

1. **Danh tính client:** client nào được đăng ký? Redirect URI, loại client và phương thức xác thực client có phù hợp luồng không?
2. **Grant/luồng được phép:** client có được dùng Authorization Code, Client Credentials hoặc luồng cụ thể đang yêu cầu không?
3. **Người dùng và tenant:** người dùng đã xác thực; có thuộc tenant và có quyền đối với tài nguyên dự kiến không?
4. **Resource Server và audience:** token sẽ dùng ở đâu? AS có cho client xin token đến đích ấy không?
5. **Scope yêu cầu:** những quyền nào được client đăng ký/cho phép xin, và quyền nào thực sự phù hợp với resource?
6. **Consent hoặc phê duyệt:** người dùng/đơn vị quản trị đã cho phép client dùng phạm vi cần thiết chưa, hoặc policy có cho phép cấp mà không hiện màn hình hỏi không?
7. **Rủi ro và điều kiện:** thao tác nhạy cảm có cần xác thực mạnh hơn, phê duyệt, thời hạn ngắn hoặc kiểm tra bổ sung không?

Một cách hiểu đúng là: **authentication cho AS biết ai đang tham gia; policy và consent quyết định AS có thể phát hành quyền gì cho client**.

### Điều kiện cần, không phải phép cộng quyền

Ví dụ client xin:

~~~text
requested_scopes = {orders:read, orders:write, payments:refund}
~~~

Hệ thống biết:

~~~text
client_allowed   = {orders:read, orders:write}
user_entitled    = {orders:read, orders:write}
tenant_policy    = {orders:read}
user_consented   = {orders:read}
resource_support = {orders:read, orders:write}
~~~

Trong ví dụ này, **scope có thể cấp** chỉ là `orders:read`. Đây là cách minh họa bằng giao của các tập quyền; **thực tế policy còn có luật phụ thuộc** như tenant, loại giao dịch, thời điểm xác thực, client assurance và điều kiện nghiệp vụ. AS có thể từ chối toàn bộ yêu cầu thay vì luôn tự động cấp một tập con.

Điều quan trọng không phải phép tính cụ thể mà là **scope được phát hành phải nằm trong phạm vi chính sách cho phép**, không bao giờ mở rộng theo dữ liệu do client tự khai báo.

## 3. Ai quyết định consent và ai thực thi policy?

Các thành phần trong OAuth 2.0:

- **Resource Owner:** chủ thể kiểm soát tài nguyên; thường là người dùng với luồng tương tác.
- **Client:** ứng dụng muốn truy cập, ví dụ ứng dụng báo cáo bên thứ ba.
- **Authorization Server:** thực hiện xác thực/ủy quyền theo luồng phù hợp, áp dụng policy, ghi nhận quyết định liên quan và phát hành token.
- **Resource Server:** API nhận access token, xác minh và thực thi quyền trên thao tác/tài nguyên.
- **Tenant administrator hoặc owner tổ chức:** có thể phê duyệt ứng dụng/phạm vi ở cấp tổ chức khi hệ thống hỗ trợ admin consent.

~~~mermaid
flowchart TD
    A["Client yêu cầu resource + scopes"] --> B{"Client, grant và redirect hợp lệ?"}
    B -- Không --> X["Từ chối yêu cầu"]
    B -- Có --> C{"Người dùng/tenant được phép?"}
    C -- Không --> X
    C -- Có --> D{"Scope và resource có trong policy?"}
    D -- Không --> X
    D -- Có --> E{"Cần consent/phê duyệt mới?"}
    E -- Có --> F["Hiển thị yêu cầu cho đúng người có quyền"]
    F --> G{"Chấp thuận phạm vi cho phép?"}
    G -- Không --> X
    G -- Có --> H["Xác định quyền thực sự được cấp"]
    E -- Không --> H
    H --> I["Phát hành code/token với audience, scope, TTL phù hợp"]
    I --> J["Resource Server vẫn xác minh token và quyền trên dữ liệu"]
~~~

Trong triển khai thực tế, một số bước được kết hợp hoặc xảy ra ở token endpoint, tùy grant và profile. Không nên coi sơ đồ như giao thức chuẩn bắt buộc cho mọi nhà cung cấp; nó thể hiện **các quyết định an toàn phải được kiểm soát**.

### Consent không bắt buộc phải luôn có màn hình

Không phải mọi giao dịch OAuth đều hiện hộp thoại hỏi người dùng:

- Client **đã được người dùng chấp thuận trước đó** cho cùng phạm vi và chính sách cho phép tái sử dụng consent.
- **Ứng dụng nội bộ/first-party** có thể được AS cho phép theo chính sách quản trị.
- **Admin consent** hoặc chính sách tổ chức có thể phê duyệt trước một số quyền.
- **Client Credentials** thường là cấp quyền cho ứng dụng/dịch vụ, **không có người dùng cuối trực tiếp** để hỏi consent trong mỗi lần xin token.

Ngược lại, một consent cũ **không** tự cho phép scope mới, tenant khác hoặc một client khác. AS phải áp dụng các quy tắc đã thiết kế để quyết định khi nào cần hỏi lại.

## 4. Authorization Code + PKCE có consent diễn ra như thế nào?

Xét một ứng dụng tên **Spend Insights** muốn đọc đơn hàng của người dùng qua Orders API. AS hỗ trợ Authorization Code và PKCE; người dùng chưa từng cấp quyền cho ứng dụng.

~~~mermaid
sequenceDiagram
    actor User as Người dùng
    participant Client as Spend Insights
    participant AS as Authorization Server
    participant API as Orders API
    User->>Client: Chọn Kết nối đơn hàng
    Client->>AS: Authorization request (scope, resource, state, PKCE)
    AS->>User: Xác thực nếu cần
    AS->>AS: Kiểm tra client, redirect, tenant, scope, policy
    AS->>User: Consent: quyền đọc đơn của bạn
    alt Từ chối hoặc policy cấm
        User-->>AS: Không đồng ý / không đủ điều kiện
        AS-->>Client: Trả lỗi theo giao thức tại redirect hợp lệ
    else Đồng ý
        User-->>AS: Chấp thuận
        AS->>AS: Lưu grant và giới hạn phạm vi cấp
        AS-->>Client: Authorization code (+ state)
        Client->>AS: Đổi code với PKCE verifier tại token endpoint
        AS-->>Client: Access token cho Orders API
        Client->>API: Bearer access token, GET /orders
        API->>API: Xác minh token, audience, scope và owner/tenant
        API-->>Client: Trả chỉ những đơn được phép
    end
~~~

### Authorization request minh họa

~~~http
GET /authorize?response_type=code&client_id=spend-insights&redirect_uri=https%3A%2F%2Fapp.example.test%2Fcallback&scope=orders%3Aread&resource=https%3A%2F%2Fapi.example.test%2Forders&state=<RANDOM_STATE>&code_challenge=<PKCE_CHALLENGE>&code_challenge_method=S256 HTTP/1.1
Host: auth.example.test
~~~

Đây là ví dụ rút gọn, **không phải yêu cầu hoàn chỉnh có thể dùng nguyên xi**. `resource` chỉ có ý nghĩa khi AS hỗ trợ **RFC 8707**; nó không bắt buộc phải được hỗ trợ ở mọi hệ thống. AS có thể ánh xạ URI tài nguyên thành audience `orders-api`. Giá trị `scope` do client đề nghị **chưa phải quyền đã được cấp**.

### Chuyện gì xảy ra khi người dùng đồng ý?

1. AS xác định người đang tương tác, kiểm tra request và ràng buộc session của người dùng.
2. AS đối chiếu ứng dụng, redirect URI, phạm vi được phép yêu cầu và policy tổ chức/tenant.
3. Nếu cần, AS trình màn hình consent với **ứng dụng, đích truy cập, mục đích, những quyền được xin và lựa chọn đồng ý/từ chối**.
4. Sau khi chấp thuận, AS ghi nhận thông tin cấp quyền và tạo **authorization code** cho client phù hợp.
5. Client đổi code tại **token endpoint**, trình `code_verifier` theo PKCE; confidential client còn phải xác thực client theo cấu hình.
6. AS phát hành **access token** với audience và scope thực sự được cấp, TTL cùng ràng buộc cần thiết. Refresh token chỉ được cấp nếu **chính sách cho phép**.
7. Resource Server nhận access token và tự xác minh, phân quyền theo tài nguyên.

**PKCE** bảo vệ luồng đổi authorization code khỏi một số dạng chặn/chiếm code; **`state`** dùng để liên kết request–response và chống CSRF tương ứng; **consent** là quyết định cấp quyền. Ba biện pháp **không thay thế lẫn nhau**. Không đặt client secret vào mã nguồn trình duyệt hoặc ứng dụng công khai rồi coi đó là bí mật.

### Token response cho thấy quyền thực tế

Ví dụ phản hồi **minh họa**:

~~~json
{
  "access_token": "<OPAQUE_ACCESS_TOKEN_PLACEHOLDER>",
  "token_type": "Bearer",
  "expires_in": 900,
  "scope": "orders:read"
}
~~~

Giá trị `scope` phản ánh phạm vi được cấp theo quy tắc của AS và giao thức; trong OAuth 2.0, trường `scope` trong token response **được yêu cầu khi khác scope đã đề nghị**, còn khi giống có thể được lược bỏ tùy quy tắc giao thức. Client phải biết phạm vi được cấp, không giả định chỉ vì đã đề nghị `orders:write` thì đã được nhận. `expires_in` thể hiện số giây hiệu lực do AS thông báo trong phản hồi, không tự làm client có quyền tự kéo dài hạn token.

## 5. Màn hình consent nên giải thích điều gì?

Consent hữu ích khi người dùng hiểu **ai** đang xin **quyền gì**, **để làm việc gì** và **có thể từ chối/thu hồi như thế nào**.

### Ví dụ hiển thị tốt

~~~text
Spend Insights muốn truy cập đơn hàng của bạn

Ứng dụng được phép:
  ✓ Xem các đơn hàng mà bạn có quyền đọc

Ứng dụng KHÔNG được phép:
  ✗ Sửa, hủy hoặc hoàn tiền đơn hàng

Thông tin thêm:
  Ứng dụng: Spend Insights (nhà phát triển đã được xác minh theo chính sách)
  Nơi truy cập: Orders API
  Bạn có thể quản lý quyền đã cấp trong phần Ứng dụng được kết nối.

  [Từ chối]    [Cho phép đọc đơn hàng]
~~~

Đây chỉ là ví dụ giao diện; thực tế cần hiển thị đúng tình trạng xác minh nhà phát triển và những gì hệ thống thực sự bảo đảm. Không được tự gắn nhãn “đã xác minh” cho client chưa được xác minh.

### Những nguyên tắc thiết kế

| Nguyên tắc | Tại sao quan trọng? | Ví dụ |
|---|---|---|
| **Nêu rõ danh tính client** | Người dùng phải biết quyền cấp cho ứng dụng nào. | Tên ứng dụng, nhà phát hành/đơn vị quản lý được AS kiểm chứng. |
| **Dùng ngôn ngữ hành động dễ hiểu** | Tên scope kỹ thuật thường khó hiểu. | “Xem lịch sử đơn hàng” thay vì chỉ `orders:read`. |
| **Nêu giới hạn thực tế** | Tránh ngộ nhận cho quyền rộng hơn. | “Không được xóa đơn” nếu API và scope thật sự bảo đảm điều đó. |
| **Quyền tối thiểu** | Giảm phạm vi dữ liệu bị lộ khi client có sự cố. | Xin quyền đọc khi chỉ cần dashboard. |
| **Đồng ý và từ chối rõ ràng** | Không ép hoặc đánh lừa người dùng bằng giao diện. | Hai lựa chọn rõ, không giấu nút từ chối. |
| **Phân biệt consent mới và đã có** | Người dùng hiểu tại sao ứng dụng hỏi lại. | “Ứng dụng đang xin thêm quyền xuất báo cáo.” |
| **Có đường rút lại quyền** | Đáp ứng kỳ vọng quản lý truy cập. | Mục quản lý client đã được cấp quyền và thu hồi. |

Tránh **scope bundling** không cần thiết: ép người dùng cấp cả quyền đọc, sửa và hoàn tiền khi ứng dụng chỉ cần đọc. Nếu hệ thống hỗ trợ chấp thuận từng nhóm quyền, AS cần định nghĩa cách xử lý **partial consent** và phản ánh **chính xác** tập scope được cấp. Không tự coi người dùng nhấn “Cho phép” cho một quyền là đồng ý với mọi scope client đã xin.

## 6. Phối hợp consent với policy và entitlement của người dùng

Một chính sách cấp token thường xét **nhiều điều kiện đồng thời**:

| Điều kiện | Ví dụ cho Spend Insights | Kết quả nếu không đáp ứng |
|---|---|---|
| **Client được công nhận** | Client ID tồn tại, redirect URI trùng cấu hình, grant được phép. | Từ chối request trước khi cấp token. |
| **Tài nguyên đích được phép** | Spend Insights được xin token cho `orders-api`, không phải Billing. | Không cấp token cho audience ngoài chính sách. |
| **Scope client được phép yêu cầu** | Chỉ `orders:read`, không có `payments:refund`. | Từ chối hoặc giảm phạm vi theo chính sách. |
| **Quyền của principal** | User chỉ đọc đơn thuộc tenant mình. | Không tạo quyền dữ liệu vượt entitlement thực. |
| **Consent phù hợp** | User chấp thuận client đọc đơn, hoặc có grant trước được phép dùng lại. | Yêu cầu consent hoặc từ chối theo luồng. |
| **Tenant/admin policy** | Tenant có thể cấm ứng dụng bên thứ ba hoặc quyền nhạy cảm. | Consent cá nhân không thể vượt policy tổ chức. |
| **Rủi ro và xác thực** | Hành động nhạy cảm cần xác thực gần đây hoặc policy bổ sung. | Yêu cầu tương tác/xác thực mạnh hơn hoặc từ chối. |

Đặc biệt, **user entitlement** và **scope** không hoàn toàn giống nhau:

- User có quyền đọc đơn của mình; `orders:read` cho client khả năng **yêu cầu thao tác đọc** trong phạm vi ấy.
- User không có quyền đọc đơn của tenant B; consent không “tặng” client quyền đó.
- Nếu client không được cấp `orders:write`, nó không được sửa đơn dù bản thân user có quyền sửa bằng ứng dụng khác.

**Consent và policy ở AS không thay authorization ở Resource Server.** RS vẫn kiểm tra owner, tenant, trạng thái đơn, role/permission hiện hành và những quy tắc nghiệp vụ tương ứng mỗi khi tiếp nhận request.

### Policy thuộc nhiều nơi

| Thành phần | Quyết định điển hình |
|---|---|
| **Authorization Server** | Client và grant nào được phép, token cấp cho audience nào, scope tối đa, có cần consent/MFA/admin approval, TTL/refresh policy. |
| **Resource Server** | Token đúng issuer/audience/type/trạng thái chưa, scope đủ chưa; principal có được làm hành động này trên tài nguyên không. |
| **Hệ thống quản trị tenant** | Ứng dụng nào được cài đặt, nhóm quyền nào chỉ admin được phê duyệt, ai được cấp quyền tổ chức. |
| **Client** | Xin những scope tối thiểu để hoàn thành tính năng; xử lý trường hợp user từ chối hoặc AS cấp ít quyền hơn. |

AS và RS phải thống nhất **ý nghĩa scope** và ranh giới audience, nhưng **không nên** giả định một màn hình consent đủ thay toàn bộ policy nghiệp vụ tại API.

## 7. User consent, admin consent và các luồng không có consent của người dùng

### 7.1. User-delegated consent

Người dùng chấp thuận cho client dùng một số quyền trong phạm vi **quyền của chính người dùng**. Ví dụ client xem đơn của user nhưng không được xem đơn của người khác. AS có thể lưu grant theo **issuer, client, chủ thể, resource, scope và tenant** hoặc khóa tương đương của hệ thống để tránh dùng lại nhầm ngữ cảnh.

### 7.2. Admin consent

Một tổ chức có thể chỉ cho admin phê duyệt quyền nhạy cảm hoặc cài đặt một ứng dụng được tổ chức tin dùng. Ví dụ quyền xem dữ liệu báo cáo của cả bộ phận có thể cần **phê duyệt cấp tenant**.

**Không đồng nghĩa** admin consent là quyền vô hạn. Hệ thống vẫn phải giới hạn API, action, dữ liệu tenant và quyền của service/ứng dụng. Một admin của tenant A không tự có quyền phê duyệt quyền toàn hệ thống hoặc tenant B.

### 7.3. Ứng dụng nội bộ/first-party

Policy có thể cho phép bỏ qua màn hình hỏi nếu client đã được tổ chức kiểm soát và quyền phù hợp. Điều này không có nghĩa có thể bỏ qua xác minh client, quyền tối thiểu hoặc kiểm tra authorization ở API. **First-party là yếu tố của policy, không phải giấy phép cấp mọi scope.**

### 7.4. Client Credentials – không có user consent theo từng yêu cầu

Trong grant `client_credentials`, client xin access token theo **danh tính và quyền ứng dụng/dịch vụ**. Không có end-user trực tiếp chấp thuận mỗi lần phát token. AS vẫn phải kiểm tra client authentication, quyền service, audience, scope và chính sách tổ chức.

~~~mermaid
flowchart LR
    S["Billing Worker (client)"] -->|"Client credentials + requested resource/scope"| AS["Authorization Server"]
    AS -->|"Service access token: aud=billing-api"| S
    S -->|"Access token"| B["Billing API"]
    B -->|"Verify + enforce service permissions"| R["Result"]
~~~

Không trộn **service access token** với **delegated access token của người dùng**. Nếu service cần thực hiện thao tác *thay mặt user*, phải có quy tắc delegation hoặc token exchange phù hợp, thay vì tự thêm `sub=user-123` vào token của service.

## 8. Incremental consent, scope mới và quyền truy cập ngoại tuyến

### Incremental consent

**Incremental consent** là cách client chỉ xin quyền khi tính năng thực sự cần. Ví dụ:

1. Lần đầu, ứng dụng chỉ xin `orders:read` để hiển thị lịch sử đơn.
2. Khi user bật tính năng gắn nhãn đơn, client mới xin quyền thích hợp như `orders:write`.
3. AS đánh giá policy và yêu cầu chấp thuận thêm nếu cần.

Lợi ích là giao diện ban đầu ít yêu cầu quá mức, giảm diện tấn công và giúp user hiểu **tại sao quyền mới được yêu cầu**. Không được lặng lẽ coi consent cũ cho `orders:read` là chấp thuận `orders:write`.

### Re-consent và yêu cầu tương tác OIDC

Trong OIDC, tham số `prompt=consent` có thể được client sử dụng để **yêu cầu Authorization Server hiển thị tương tác consent** theo quy tắc OIDC; nó **không** buộc AS phải phát hành bất kỳ scope nào, không vô hiệu hóa admin policy và không phải cơ chế hợp thức hóa quyền vượt phạm vi. Khi AS không thể thu được consent cần thiết trong một luồng không cho tương tác, giao thức có thể trả lỗi như `consent_required` theo tình huống/profile.

**`prompt=login`, `max_age` và `auth_time`** liên quan đến xác thực/độ mới của xác thực; chúng **khác** consent. Khi nghiệp vụ nhạy cảm, AS có thể cần cả **xác thực mạnh hoặc mới** lẫn **quyền truy cập được phê duyệt**.

### Offline access và refresh token

Khi client cần tiếp tục truy cập sau thời điểm người dùng không còn tương tác trực tiếp, thiết kế có thể yêu cầu **offline access** và **refresh token**.

- Trong OIDC, `offline_access` là một scope đặc biệt được sử dụng trong ngữ cảnh yêu cầu offline access; việc cấp quyền phụ thuộc chính sách OP/AS và những điều kiện của OIDC.
- **Xin `offline_access` không bảo đảm được refresh token**: AS có thể không cấp hoặc hạn chế theo loại client, rủi ro, policy và kết quả ủy quyền.
- Refresh token được trình **chỉ tại token endpoint** để xin access token mới, không được gửi đến Orders API như access token.
- Nếu cấp refresh token, cần bảo vệ nơi lưu, thực hiện rotation hoặc sender-constraining tùy loại client và áp dụng chính sách thời hạn/thu hồi phù hợp.
- Khi dùng refresh token, AS phải kiểm tra grant còn hợp lệ và **không cho scope mới vượt quá quyền đã được ủy quyền**.

Ví dụ client được phép đọc đơn nhưng không được sửa: refresh token của grant đọc đơn **không phải lối tắt** để xin access token `orders:write`.

## 9. Lưu consent, rút lại consent và hiệu lực trên token đang tồn tại

### Consent được lưu theo những chiều nào?

AS có thể lưu các thông tin như:

~~~json
{
  "subject": "user-123",
  "client_id": "spend-insights",
  "tenant_id": "tenant-a",
  "resource": "orders-api",
  "approved_scopes": ["orders:read"],
  "granted_at": "2026-11-23T08:30:00Z",
  "grant_status": "active",
  "policy_version": "policy-v3"
}
~~~

Đây là **schema minh họa**, không phải cấu trúc bắt buộc của OAuth hoặc quy định lưu trữ dữ liệu thực tế. Giá trị `granted_at` ở đây chỉ là ví dụ ngày/giờ lưu quyết định, không phải `auth_time` hay `iat` của JWT. Một hệ thống có thể có nhiều quyết định theo tenant, client, user, resource và scope; phải tránh dùng lại grant của user khác hoặc client khác.

Lưu consent cần có bảo vệ truy cập, thời gian lưu phù hợp, khả năng audit và cơ chế thay đổi/thu hồi. Không cần ghi **nguyên access token** trong bản ghi consent; token và grant là khái niệm khác nhau.

### Rút lại consent có làm mọi token cũ hết hiệu lực ngay?

**Không tự động.** Khi user rút consent hoặc admin thu hồi grant, AS có thể:

1. Đánh dấu grant không còn được sử dụng để cấp token mới.
2. Thu hồi refresh token và token liên quan theo khả năng của hệ thống.
3. Thông báo/cập nhật RS hoặc dùng introspection, denylist, session version hay cơ chế trạng thái khác nếu muốn **vô hiệu hóa access token trước `exp`**.
4. Xử lý cache và độ trễ để chính sách thu hồi đáp ứng mục tiêu an toàn.

Nếu Resource Server chỉ kiểm tra chữ ký JWT và `exp` mà **không** kiểm tra trạng thái/thu hồi, access token đã phát hành trước khi rút consent **có thể tiếp tục được chấp nhận đến khi hết hạn**. Với opaque token dựa vào introspection, khả năng cập nhật trạng thái có thể nhanh hơn nhưng **cache introspection vẫn có độ trễ**.

~~~mermaid
sequenceDiagram
    actor U as Người dùng
    participant AS as Authorization Server
    participant C as Client
    participant API as Orders API
    AS-->>C: Access token A, refresh token R (nếu được cấp)
    U->>AS: Rút quyền đã cấp cho client
    AS->>AS: Vô hiệu hóa grant + refresh token theo policy
    C->>AS: Dùng R xin token mới
    AS-->>C: Từ chối nếu R/grant đã bị thu hồi
    C->>API: Thử trình lại access token A cũ
    Note over API: Kết quả tùy TTL và cơ chế RS kiểm tra thu hồi
    API-->>C: Từ chối nếu đã hết hạn / đã bị chặn
~~~

**Đăng xuất khỏi client** cũng không đồng nghĩa AS đã xóa mọi bản sao access token khỏi thiết bị khác hoặc máy attacker. Thiết kế phải mô tả rõ tác động của từng thao tác: logout, disconnect client, revoke refresh token, revoke grant, disable user và revoke access token.

## 10. AS nên thực thi issuance policy như thế nào?

Một hệ thống có thể tổ chức **Policy Decision Point** ở AS để tính các grant được phép phát hành. Không nên để controller tự “lắp” claims từ nội dung request hoặc dựa vào dữ liệu scope do client tự đưa như quyền mặc định.

### Ví dụ policy rút gọn

~~~yaml
# Đây là policy minh họa để thảo luận, KHÔNG phải cấu hình chuẩn của OAuth.
resource_servers:
  orders-api:
    allowed_scopes:
      - orders:read
      - orders:write
    default_access_token_ttl_seconds: 900
clients:
  spend-insights:
    allowed_grants:
      - authorization_code
    allowed_resources:
      - orders-api
    allowed_scopes:
      - orders:read
    consent_required: true
  billing-worker:
    allowed_grants:
      - client_credentials
    allowed_resources:
      - billing-api
    allowed_scopes:
      - payments:read
    consent_required: false
~~~

Trong ứng dụng thực, một phần chính sách có thể lưu trong database hoặc policy engine, nhưng **mọi nguồn quyết định phải được quản lý phía AS**, không bị client kiểm soát.

### Mã giả ra quyết định cấp token

~~~text
issueAccessToken(request, authenticatedContext):
    client = trustedClientRegistry.find(request.client_id)
    if client missing or grant not in client.allowed_grants:
        deny "unauthorized_client"

    validateRedirectAndPkceWhenRequired(request, client)
    validateClientAuthenticationWhenRequired(client, request)

    target = normalizeAndValidateRequestedResource(request.resource)
    if target not in client.allowed_resources:
        deny "invalid_target_or_policy"

    requested = parseRequestedScopes(request.scope)
    allowed = policy.evaluate(
        client=client,
        principal=authenticatedContext.principal_if_applicable,
        tenant=authenticatedContext.tenant,
        target=target,
        requested=requested,
        grant=request.grant_type,
        risk=authenticatedContext.risk
    )
    if allowed is empty or not policy.permitsIssuance:
        deny

    if policy.requiresUserConsent:
        decision = trustedConsentStore.findApplicableGrant(
            principal, client, tenant, target, allowed
        )
        if decision insufficient:
            obtainConsentFromAuthorizedUserOrDeny(allowed)

    grantedScopes = policy.finalScopesRespectingConsent(allowed)
    if grantedScopes empty:
        deny

    return issueTokenFromTrustedServerState(
        issuer=configuredIssuer,
        subject=verifiedSubjectOrServicePrincipal,
        audience=configuredAudience(target),
        scopes=grantedScopes,
        ttl=policy.accessTokenTtl
    )
~~~

Các tên lỗi và hàm ở trên **chỉ mô tả ý tưởng**; mã sản phẩm phải theo đúng OAuth/OIDC profile và thư viện/AS đang sử dụng. Đặc biệt:

- **Consent phải gắn với phiên/tài khoản đã xác thực**, tránh ghi nhầm grant cho người dùng khác.
- **Scope thực sự cấp** không được vượt policy và consent áp dụng; xử lý từ chối đầy đủ thay vì ép user cho toàn bộ requested scopes.
- **Audience và issuer** đến từ cấu hình AS đáng tin, không lấy payload JWT hay header tùy ý từ client làm giá trị quyền lực.
- **Client công khai** không thể chứng minh danh tính bằng một shared secret nhúng sẵn trong mã nguồn ứng dụng; dùng PKCE và các kiểm soát tương ứng.
- **Refresh token policy** là quyết định riêng, không tự phát hành refresh token mọi khi access token được cấp.

### Các tình huống lỗi cần được thiết kế rõ

| Nguyên nhân | Ví dụ | Hướng phản ứng an toàn |
|---|---|---|
| Client không được phép dùng grant | Public client yêu cầu một luồng không được đăng ký. | Từ chối theo giao thức, không tự chuyển sang luồng kém an toàn. |
| Resource đích không hợp lệ | Client xin token cho Billing dù chỉ được phép Orders. | Từ chối target; không cấp token chung mọi API. |
| Scope vượt policy | Spend Insights xin `payments:refund`. | Từ chối hoặc cấp tập nhỏ hơn theo chính sách và giao thức. |
| User bấm từ chối | Không chấp thuận `orders:read`. | Không phát hành grant/token cho quyền bị từ chối. |
| Admin policy chặn | Tenant cấm client bên thứ ba. | Không cho user consent vượt policy tenant. |
| Consent cũ hết hiệu lực | Scope mới hoặc grant đã bị thu hồi. | Yêu cầu phê duyệt lại khi áp dụng hoặc từ chối. |
| Client cố đổi sang user/tenant khác | Dùng grant của user A để xin token cho user B. | Từ chối, ràng buộc grant với đúng principal và tenant. |
| Không thể kiểm tra policy | Kho quyền/consent lỗi, dữ liệu không đủ tin cậy. | **Fail closed**; không cấp quyền mặc định. |

## 11. Consent phishing và tấn công quanh màn hình chấp thuận

### Consent phishing hoạt động như thế nào?

Attacker có thể tạo một ứng dụng OAuth với tên hoặc biểu tượng gây nhầm lẫn, dẫn người dùng đến **màn hình chấp thuận thực sự của AS**, rồi đề nghị các scope rộng. Nếu user bấm “Cho phép”, AS có thể cấp quyền cho **client của attacker** trong giới hạn chính sách.

Đây khác với việc đánh cắp mật khẩu: **user có thể đăng nhập tại trang AS thật** nhưng vẫn bị dụ cấp access token hợp lệ cho một ứng dụng độc hại. Vì vậy “có login thật” hay “token được ký hợp lệ” **không chứng minh** client đáng tin và việc cấp quyền là phù hợp.

~~~mermaid
flowchart LR
    A["Ứng dụng giả danh thương hiệu"] --> B["Yêu cầu OAuth scopes quá rộng"]
    B --> C["Người dùng gặp consent screen"]
    C --> D{"User đồng ý và policy cho phép?"}
    D -- Có --> E["AS cấp token hợp lệ cho client đó"]
    E --> F["Client sử dụng quyền đã được cấp"]
    D -- Không --> G["Không có grant/token tương ứng"]
~~~

Các biện pháp phòng ngừa tại AS/organization:

1. **Kiểm soát đăng ký và xác minh client**, redirect URI, danh tính nhà phát triển và các scope nhạy cảm.
2. **Hiển thị rõ tên client và tác dụng quyền**, không chỉ hiện một danh sách chuỗi kỹ thuật khó hiểu.
3. **Giới hạn scope theo client** và chỉ cho ứng dụng đã được đánh giá xin quyền nhạy cảm.
4. **Phê duyệt admin** đối với scope có tác động rộng, dựa trên ranh giới tenant và nhu cầu thật.
5. **Phát hiện bất thường** khi một client mới xin scope rộng hoặc nhiều người dùng cấp quyền bất thường.
6. **Cung cấp trang rà soát/rút quyền** đã cấp, hỗ trợ phản ứng sự cố.

Các biện pháp phòng ngừa tại client và luồng giao thức:

- Dùng Authorization Code + PKCE và HTTPS, xác thực redirect URI theo chính sách.
- Liên kết response với request ban đầu bằng `state` hoặc cơ chế tương ứng; áp dụng các kiểm soát chống authorization code injection/mix-up theo profile.
- Không nhúng client secret vào ứng dụng công khai; không ghi authorization code, token hoặc refresh token vào log.
- Không chấp nhận quyền trong token hoặc trong response mà không xác minh đúng issuer/audience/token type khi dùng.

**Consent phishing không được khắc phục bằng cách chỉ tăng độ dài chữ ký JWT.** Rủi ro nằm ở **một client không phù hợp nhận quyền hợp lệ** qua tương tác bị dẫn dắt.

## 12. Sau khi phát hành, Resource Server vẫn là nơi chặn quyền cuối

AS đã cấp access token cho `orders-api` với `scope=orders:read` không có nghĩa user được đọc mọi đơn. Resource Server cần xác minh:

1. Token đúng **issuer** và được xác minh bằng chữ ký/JWKS tin cậy hoặc **opaque introspection** tin cậy.
2. Token đúng **audience**, mục đích access token và thời hạn/trạng thái.
3. Scope `orders:read` được **cấp thực tế** trong token, không phải giá trị do client tự nói.
4. Principal có quyền đọc **order cụ thể**, dựa trên owner, tenant, role/permission hiện hành và policy nghiệp vụ.
5. Proof DPoP/mTLS nếu access token là **sender-constrained** và profile yêu cầu.

Ví dụ:

~~~text
Token:
  iss   = https://auth.example.test
  sub   = user-123
  aud   = orders-api
  scope = orders:read

Request: GET /orders/order-42
Order 42: owner=user-999, tenant=tenant-b
Principal: user-123, tenant=tenant-a

=> DENY nếu không có ủy quyền liên tenant đã được cấp riêng.
~~~

Với bearer access token, attacker đã sao chép được token còn hạn **có thể phát lại** ở đúng API trong phạm vi quyền. Consent không tự chống việc đánh cắp token; cần TLS, lưu trữ an toàn, scope/audience hẹp, TTL ngắn, thu hồi và sender-constrained token khi cần.

### Phân biệt lỗi ở AS và lỗi ở Resource Server

| Tình huống | Thành phần quyết định | Kết quả thường gặp |
|---|---|---|
| User từ chối consent | AS | Không cấp grant/token; trả lỗi ủy quyền theo giao thức. |
| Client xin scope bị policy cấm | AS | Từ chối request hoặc cấp phạm vi nhỏ hơn theo chính sách. |
| Access token thiếu hoặc không hợp lệ | RS | **401 Unauthorized**, có thể kèm `WWW-Authenticate`. |
| Access token hợp lệ nhưng không đủ scope | RS | **403 Forbidden**, có thể báo `insufficient_scope`. |
| Access token có scope nhưng không có quyền trên order | RS | **403** hoặc **404** theo chính sách chống lộ sự tồn tại. |

Tránh nhầm việc user từ chối consent ở AS với **HTTP 403 từ API nghiệp vụ**: đó là hai thời điểm và hai loại quyết định khác nhau.

## 13. Ma trận kiểm thử consent và issuance policy

Giả sử `spend-insights` được đăng ký chỉ đọc Orders API, còn `billing-worker` chỉ được dùng grant service để xem Billing. Các kết quả là **kỳ vọng của policy minh họa**, không phải kết luận bắt buộc cho mọi AS:

| Tình huống | Kỳ vọng | Cơ sở |
|---|---|---|
| Spend Insights xin `orders:read`, user chưa consent, policy cho phép | **Yêu cầu consent** rồi cấp theo quyết định. | Chưa có grant phù hợp. |
| User từ chối `orders:read` | **Không cấp access token cho quyền bị từ chối**. | Consent bắt buộc không đạt. |
| User đồng ý `orders:read` | **Có thể cấp token `aud=orders-api`, scope read**. | Client, resource, user, policy và consent đều phù hợp. |
| Spend Insights xin `orders:write` | **Không tự cấp quyền write**. | Vượt allowed scopes của client. |
| Spend Insights xin `payments:refund` và user đồng ý | **Từ chối quyền refund**. | Consent không vượt client/tenant/RS policy. |
| Scope cũ `orders:read` đã được cấp; client xin thêm `orders:write` | **Yêu cầu quyết định quyền mới hoặc từ chối**. | Không suy quyền ghi từ consent đọc. |
| Tenant admin chặn Spend Insights sau khi user đã consent | **Không cấp token mới theo policy mới**; đánh giá thu hồi token cũ. | Policy tổ chức có hiệu lực cao hơn consent user trong ví dụ. |
| User rút consent, client dùng refresh token | **Từ chối nếu grant/refresh đã bị thu hồi**. | Refresh token không tạo lại consent. |
| User rút consent nhưng JWT access token cũ còn hạn | **Có thể vẫn dùng được nếu RS không kiểm tra thu hồi**. | Cần thiết kế trạng thái thu hồi riêng. |
| Billing Worker dùng client credentials đúng cấu hình | **Có thể cấp service token** không cần user prompt. | Đây là quyền ứng dụng, không phải delegated consent của user. |
| Token Spend Insights đúng scope nhưng đọc order tenant khác | **RS từ chối**. | Consent/scope không thay ownership và tenant. |
| User đồng ý nhưng AS không kiểm tra được kho policy | **Không cấp quyền mặc định**. | Fail closed khi thiếu căn cứ tin cậy. |

Kiểm thử cần bao gồm **thay đổi client ID, user, tenant, resource, scope, policy version, trạng thái grant, số lần thử lại và refresh token**. Phải thử cả việc hệ thống vẫn cấp đúng quyền khi người dùng **thực sự chấp thuận trong phạm vi được phép** và các trường hợp bị từ chối an toàn.

## 14. Tình huống suy luận

**Tình huống A — User cho phép mọi thứ.** Một ứng dụng chưa được phê duyệt xin `payments:refund`; người dùng bấm “Đồng ý”. AS có nên phát token refund không?

**Giải thích:** Không, nếu client/tenant policy không cho phép. Consent chỉ nằm trong **phần giao của quyền có thể cấp**, không thay chính sách an toàn của AS.

**Tình huống B — User đã consent read.** Ba tháng trước user chấp thuận `orders:read`. Hôm nay cùng client xin `orders:write`. Có thể tự cấp thêm không?

**Giải thích:** Không. Cần đánh giá policy và consent cho quyền mới theo quy tắc hiện hành. Không diễn giải consent cũ cho “read” thành quyền “write”.

**Tình huống C — Client Credentials.** Một worker backend xin token `aud=billing-api` bằng client credentials để đồng bộ hóa báo cáo. AS có bắt buộc phải hiện màn hình user consent không?

**Giải thích:** Không. Luồng này thường không có end-user tương tác; AS cần kiểm tra **quyền của service/client**, xác thực client và policy tương ứng.

**Tình huống D — Đồng ý nhưng sai tenant.** User thuộc tenant A đồng ý cho app xem đơn hàng. App gọi Orders API để đọc đơn thuộc tenant B. Token có `orders:read` còn hạn. Có được trả dữ liệu không?

**Giải thích:** Không, trừ khi có ủy quyền liên tenant được thiết kế riêng. RS cần kiểm tra owner/tenant của **từng đơn**, độc lập với consent.

**Tình huống E — Đã rút consent.** User thu hồi quyền của app, nhưng attacker có bản sao bearer JWT access token còn hạn; RS chỉ kiểm tra chữ ký và `exp`. Token có thể được dùng không?

**Giải thích:** Có thể. Cần thiết kế cơ chế thu hồi tại RS, TTL hẹp và các biện pháp ngăn token bị lộ/phát lại. Chỉ thu hồi consent trong AS không tự làm mọi JWT cũ bị RS từ chối ngay.

**Tình huống F — Consent phishing.** User đăng nhập tại AS thật và bấm chấp thuận cho client giả danh một ứng dụng quen thuộc. Vì sao đây vẫn là sự cố?

**Giải thích:** AS có thể cấp **token hợp lệ cho client độc hại** nếu policy không kiểm soát đăng ký, danh tính client và scope nhạy cảm. Đăng nhập thật hoặc chữ ký token đúng không đảm bảo quyết định consent là an toàn.

**Tình huống G — Offline access.** Client xin `offline_access`, user chấp thuận; client có thể coi refresh token chắc chắn được phát và sử dụng mãi mãi không?

**Giải thích:** Không. AS quyết định có cấp refresh token hay không và điều kiện hiệu lực/rotation/thu hồi của nó. Offline access không tạo quyền vượt policy hay token không hết hạn.

## Checklist triển khai user consent và issuance policy

1. **Tách các bước:** authentication, consent, AS policy, token issuance và authorization ở RS có trách nhiệm rõ ràng.
2. **Xác thực/bảo vệ client:** đăng ký client, redirect URI, grant và PKCE; confidential client xác thực phù hợp, public client không nhúng bí mật giả.
3. **Giới hạn quyền phát hành:** theo client, principal, tenant, resource, scope, loại grant, rủi ro và yêu cầu tương tác.
4. **Đảm bảo consent rõ và tự nguyện:** giải thích app, quyền, mục đích và phương án từ chối; tránh yêu cầu quyền không cần thiết.
5. **Gắn grant đúng ngữ cảnh:** không chia sẻ consent giữa client/user/tenant/resource khác; xét hiệu lực và policy version.
6. **Quản lý quyền mới:** incremental consent, yêu cầu phê duyệt lại khi scope tăng, thay đổi đáng kể hoặc grant đã bị thu hồi.
7. **Tách admin và user permission:** ai có quyền phê duyệt scope cấp tổ chức phải được xác minh; consent user không vượt giới hạn tenant.
8. **Kiểm soát refresh/offline:** chỉ cấp khi policy cho phép; bảo vệ refresh token, rotation/sender-constraining, giới hạn scope mới và thu hồi.
9. **Tính đến token đã phát hành:** rút consent, logout và xóa tài khoản phải có chính sách trạng thái, TTL, cache và khả năng thu hồi được mô tả rõ.
10. **Chống lừa consent:** xác minh ứng dụng/nhà phát triển, giám sát scope nhạy cảm, tránh màn hình gây nhầm lẫn và hỗ trợ xem/rút quyền.
11. **Giữ RS làm nơi chặn cuối:** issuer, audience, loại token, scope, trạng thái, chủ thể, tenant, owner và proof khi cần phải được kiểm tra.
12. **Thử cả negative cases:** user từ chối, scope vượt policy, client không được phép, sai tenant, grant đã rút, lỗi kho policy, token cũ và bearer token bị phát lại.

## Ghi nhớ

**User consent là một quyết định chấp thuận có ngữ cảnh cho client; issuance policy là tập luật quyết định quyền nào AS thật sự được phép cấp.** Người dùng đồng ý không tự tạo quyền mới; người dùng đã đăng nhập cũng không tự đồng ý cho mọi client. AS phải ràng buộc grant với đúng client, principal, tenant, resource và scope, phát hành token theo quyền tối thiểu và quản lý refresh/thu hồi. **Resource Server vẫn kiểm tra access token và quyền đối với từng tài nguyên.** Việc rút consent không tự bảo đảm mọi JWT đã phát hành mất hiệu lực ngay, và một bearer token hợp lệ vẫn có thể bị sao chép/phát lại nếu không có bảo vệ vòng đời phù hợp.

### Tài liệu tham khảo

- [RFC 6749 — The OAuth 2.0 Authorization Framework](https://www.rfc-editor.org/rfc/rfc6749)
- [RFC 7636 — Proof Key for Code Exchange (PKCE)](https://www.rfc-editor.org/rfc/rfc7636)
- [RFC 7009 — OAuth 2.0 Token Revocation](https://www.rfc-editor.org/rfc/rfc7009)
- [RFC 7662 — OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662)
- [RFC 8707 — Resource Indicators for OAuth 2.0](https://www.rfc-editor.org/rfc/rfc8707)
- [RFC 8725 — JWT Best Current Practices](https://www.rfc-editor.org/rfc/rfc8725)
- [RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068)
- [RFC 9449 — OAuth 2.0 Demonstrating Proof of Possession (DPoP)](https://www.rfc-editor.org/rfc/rfc9449)
- [RFC 9700 — Best Current Practice for OAuth 2.0 Security](https://www.rfc-editor.org/rfc/rfc9700)
- [OpenID Connect Core 1.0 — Authentication, Consent and Offline Access](https://openid.net/specs/openid-connect-core-1_0.html)
