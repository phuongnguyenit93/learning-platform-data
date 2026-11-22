# Claims danh tính và quyết định cho phép truy cập tài nguyên

## 1. Tại sao xác minh JWT chưa đồng nghĩa với cấp quyền?

Trong một hệ thống sử dụng JSON Web Token (JWT), một access token có thể giúp API nhận biết **ai hoặc ứng dụng nào đang gọi**, **token được phát hành bởi ai**, **dành cho API nào**, **còn hiệu lực hay không** và **những quyền được khai báo trong token**. Tuy nhiên, một JWT hợp lệ về mặt chữ ký và thời gian **không tự động cho phép** mọi thao tác trên mọi tài nguyên.

Cần phân biệt ba câu hỏi:

1. **Xác thực (authentication):** Bằng chứng được trình ra có hợp lệ không, và chủ thể (principal) được xác nhận là ai?
2. **Ủy quyền (authorization):** Chủ thể đó có được phép thực hiện hành động cụ thể trên tài nguyên cụ thể, trong ngữ cảnh hiện tại không?
3. **Thực thi chính sách (policy enforcement):** API kiểm tra quyết định cấp quyền trước khi đọc, sửa, xóa hoặc tiết lộ tài nguyên ở đâu và như thế nào?

Ví dụ, một nhân viên đã đăng nhập có access token hợp lệ và có quyền đọc hóa đơn. Điều đó vẫn chưa chứng minh họ được đọc **hóa đơn của công ty khác**, **hóa đơn thuộc bộ phận bị giới hạn**, hay **hóa đơn đã bị khóa bởi một quy tắc nghiệp vụ**.

Quy tắc nền tảng:

> **JWT cung cấp các phát biểu (claims) đã được xác minh trong một phạm vi tin cậy; quyết định truy cập phải kết hợp các claims đó với chính sách và dữ liệu tài nguyên hiện tại.**

Các nguyên tắc trong bài áp dụng cho API, ứng dụng web, dịch vụ nội bộ và kiến trúc phân tán nói chung; chúng không phụ thuộc một ngôn ngữ lập trình hay framework cụ thể.

## 2. Claims là gì và cần tin vào điều gì?

Một claim là một thuộc tính được khai báo trong phần payload của JWT. Claim có thể mô tả:

- **Nguồn phát hành:** hệ thống nào đưa ra phát biểu này.
- **Chủ thể:** người dùng, tài khoản dịch vụ hoặc thực thể được token đại diện.
- **Đích sử dụng:** API hoặc dịch vụ nào được phép tiếp nhận token.
- **Thời gian:** token có hiệu lực trong khoảng nào.
- **Phạm vi quyền được cấp:** ví dụ quyền đọc hóa đơn.
- **Ngữ cảnh định danh:** ví dụ tổ chức hiện hành, ứng dụng khách, phiên đăng nhập.

JWT có thể được bảo vệ bằng chữ ký hoặc mã hóa theo cấu hình sử dụng. Trong trường hợp access token dạng JWT **có chữ ký**, chữ ký giúp bên nhận kiểm tra tính toàn vẹn và nguồn ký theo khóa đáng tin cậy. Chữ ký **không biến mọi nội dung claim thành một quyết định nghiệp vụ luôn đúng**. Chẳng hạn, quyền của một nhân viên có thể đã bị thu hồi sau thời điểm phát hành token.

### 2.1. Ví dụ access token cho API hóa đơn

Giả sử hệ thống xác thực phát hành access token cho API quản lý hóa đơn. Ví dụ sau mô tả **header và payload đã giải mã**, không phải token hoàn chỉnh và không chứa chữ ký có thể dùng thực tế.

Header minh họa cho một hệ thống sử dụng profile JWT access token có định kiểu:

~~~json
{
  "alg": "RS256",
  "typ": "at+jwt",
  "kid": "signing-key-01"
}
~~~

Payload minh họa:

~~~json
{
  "iss": "https://identity.example.test",
  "sub": "user-8472",
  "aud": "https://api.example.test/invoices",
  "iat": 1893452400,
  "nbf": 1893452400,
  "exp": 1893456000,
  "jti": "token-6f8d9a",
  "client_id": "billing-portal",
  "scope": "invoice:read invoice:create",
  "tenant_id": "company-a",
  "roles": ["billing_reader"]
}
~~~

Các giá trị, URL, thời điểm và tên claim ở trên chỉ phục vụ giải thích. Riêng các claim như **tenant_id** và **roles** là quy ước của hệ thống ví dụ, **không phải claim phân quyền chuẩn mà mọi JWT đều có**.

| Claim | Ý nghĩa và cách sử dụng đúng |
| --- | --- |
| **iss** (issuer) | Bên phát hành token. API phải đối chiếu với issuer đã cấu hình tin cậy. |
| **sub** (subject) | Định danh chủ thể trong ngữ cảnh của issuer. Cặp **(iss, sub)** thường là cơ sở nhận diện an toàn hơn chỉ dùng **sub**. Không mặc định **sub** luôn là người dùng; đó có thể là tài khoản dịch vụ. |
| **aud** (audience) | Bên nhận được dự kiến. API chỉ chấp nhận token có audience phù hợp với chính API đó; giá trị có thể là chuỗi hoặc mảng theo JWT. |
| **iat** (issued at) | Thời điểm phát hành; hỗ trợ kiểm tra tuổi token và chính sách phiên, không tự chứng minh token còn hợp lệ. |
| **nbf** (not before) | Token chưa được sử dụng trước thời điểm này. |
| **exp** (expiration time) | Thời điểm hết hạn. Token hết hạn phải bị từ chối, có thể áp dụng sai lệch đồng hồ nhỏ theo chính sách. |
| **jti** (JWT ID) | Định danh token nếu issuer cung cấp; có thể hỗ trợ truy vết hoặc danh sách thu hồi. Không thay thế kiểm tra chữ ký và quyền. |
| **client_id** | Ứng dụng khách liên quan đến token theo hợp đồng phát hành; không đồng nghĩa với danh tính người dùng. |
| **scope** | Danh sách phạm vi quyền được cấp. Trong một số profile OAuth, đây là chuỗi các mục phân cách bởi dấu cách; API cần kiểm tra từng mục **chính xác**. |
| **roles** | Vai trò do hệ thống tự định nghĩa, ví dụ bộ phận xem hóa đơn. Quyền cụ thể phải được suy ra theo chính sách do API hoặc hệ thống phân quyền kiểm soát. |
| **tenant_id** | Tổ chức/ngữ cảnh thuê bao của token theo quy ước riêng; phải được đối chiếu với tài nguyên và quyền thành viên hiện tại. |

**Các claim đăng ký trong JWT** (chẳng hạn **iss**, **sub**, **aud**, **exp**, **nbf**, **iat**, **jti**) có ý nghĩa được mô tả trong chuẩn JWT. Các claim như **roles**, **permissions**, **tenant_id**, **groups**, **scp** hay tên trường nghiệp vụ khác chỉ có ý nghĩa khi hệ thống thống nhất hợp đồng dữ liệu, kiểu giá trị và quy tắc diễn giải. Không được mặc định hai nhà phát hành dùng cùng tên claim thì có cùng ngữ nghĩa.

### 2.2. Ba cấp độ tin cậy cần tách biệt

| Cấp độ | Câu hỏi | Kết luận có thể rút ra |
| --- | --- | --- |
| **Dữ liệu được gửi đến** | Client gửi chuỗi JWT có payload gì? | Chưa tin được; bất kỳ ai cũng có thể tự tạo hoặc sửa chuỗi JWT. |
| **Token đã được xác minh** | Chữ ký, issuer, audience, thời gian, thuật toán và loại token có đạt yêu cầu không? | Có thể tin rằng các phát biểu trong token đến từ bên phát hành hợp lệ, cho đúng mục đích đã kiểm tra. |
| **Chính sách truy cập được đánh giá** | Chủ thể có quyền với hành động và tài nguyên này ngay lúc này không? | Mới có cơ sở ra quyết định **ALLOW** hoặc **DENY**. |

Chỉ **giải mã Base64URL để đọc payload** không phải là xác minh JWT. Dữ liệu claim phải được dùng **sau khi** token đã đi qua toàn bộ bước xác minh cần thiết.

## 3. Claims danh tính khác claims phân quyền như thế nào?

**Claims danh tính** trả lời câu hỏi "chủ thể này là ai theo nhà phát hành?". **Claims liên quan đến phân quyền** mô tả "những khả năng hoặc vai trò nào đã được cấp tại thời điểm phát hành?". Chúng phục vụ hai mục đích khác nhau.

### 3.1. Định danh chủ thể không tự cấp quyền

Giả sử API đã xác minh được:

~~~text
iss = https://identity.example.test
sub = user-8472
~~~

API có thể dùng cặp này để ánh xạ đến một tài khoản nội bộ. Nhưng không được suy ra "đã đăng nhập thì được đọc mọi hóa đơn". Một người đã đăng nhập vẫn có thể bị từ chối ở từng tài nguyên.

Trong lời gọi giữa hai dịch vụ, **sub** có thể biểu diễn danh tính dịch vụ hoặc thực thể không phải con người. Khi thao tác yêu cầu một người dùng cụ thể, API phải kiểm tra token thực sự biểu diễn loại chủ thể được phép; không thể chỉ thấy trường **sub** tồn tại là đủ.

### 3.2. Scope, role và permission mang ý nghĩa khác nhau

| Khái niệm | Ví dụ | Cách hiểu |
| --- | --- | --- |
| **Scope** | **invoice:read** | Khả năng mà token được cấp cho một API/ngữ cảnh nhất định. Scope không mặc nhiên cấp quyền trên từng đối tượng cụ thể. |
| **Role** | **billing_reader** | Nhóm trách nhiệm trong một tổ chức; API hoặc dịch vụ phân quyền ánh xạ role thành các quyền cụ thể. |
| **Permission** | **invoice.read** | Quyền chi tiết do hệ thống định nghĩa, thường gắn với một hành động. |
| **Thuộc tính tài nguyên** | **invoice.tenant_id**, **invoice.owner_id** | Dữ liệu để đánh giá chính sách tại thời điểm truy cập; cần lấy từ nguồn tài nguyên đáng tin cậy. |
| **Thuộc tính ngữ cảnh** | Thời điểm, loại phiên, trạng thái tài khoản | Điều kiện bổ sung quyết định có cho phép thao tác hay không. |

Ví dụ, scope **invoice:read** nói rằng token được phép *yêu cầu* thao tác đọc hóa đơn trong phạm vi được cấp. Để đọc hóa đơn **INV-100**, API vẫn cần xác định hóa đơn thuộc tổ chức nào, người gọi có là thành viên hợp lệ của tổ chức đó không, và chính sách cho phép xem hóa đơn này hay không.

**Không kiểm tra scope bằng phép tìm chuỗi con.** Chẳng hạn, tìm xem chuỗi scope có chứa chữ **read** sẽ có thể khớp nhầm với quyền khác. Hãy phân tách theo định dạng mà issuer đã cam kết và so khớp tên scope chính xác. Tương tự, tên role phải được ánh xạ theo chính sách nội bộ, không tự tạo quyền chỉ vì chuỗi role nghe có vẻ mạnh.

### 3.3. Claims là ảnh chụp tại thời điểm phát hành

Giả sử nhân viên **user-8472** được cấp role **billing_reader** lúc 09:00 và bị gỡ khỏi công ty lúc 09:10, trong khi token hết hạn lúc 09:30. Nếu API chỉ nhìn role được đóng gói trong JWT, nhân viên có thể tiếp tục truy cập cho đến khi token hết hạn.

Vì vậy, đối với quyền có thể thay đổi nhanh hoặc tài nguyên nhạy cảm, cần cân nhắc kiểm tra **trạng thái thành viên và quyền hiện tại** tại dịch vụ phân quyền/cơ sở dữ liệu đáng tin cậy. JWT ngắn hạn giúp thu hẹp khoảng rủi ro, nhưng **không tạo khả năng thu hồi tức thì**.

## 4. Luồng quyết định quyền truy cập một tài nguyên

Một API an toàn thường cần thực hiện các bước theo thứ tự sau:

1. **Nhận bằng chứng truy cập:** đọc access token từ kênh đã quy định, thường là header HTTP **Authorization: Bearer**; không tin định danh người dùng do client tùy ý gửi trong body hoặc query.
2. **Xác minh token:** kiểm tra chữ ký bằng khóa thuộc issuer được tin cậy, thuật toán được cho phép, issuer, audience, kiểu/token profile, thời điểm và các yêu cầu bổ sung của hệ thống.
3. **Tạo principal nội bộ:** lấy danh tính và ngữ cảnh từ **claims đã xác minh**; ánh xạ chủ thể vào mô hình tài khoản phù hợp.
4. **Kiểm tra quyền yêu cầu hành động:** scope hoặc permission có cho phép loại thao tác này hay không?
5. **Định vị và xác minh tài nguyên:** lấy tài nguyên từ nguồn dữ liệu đáng tin cậy; kiểm tra chủ sở hữu, tổ chức, trạng thái và các giới hạn liên quan.
6. **Đánh giá chính sách tại thời điểm yêu cầu:** kết hợp principal, quyền hiện hành, hành động, tài nguyên và ngữ cảnh; mặc định **DENY** nếu thiếu dữ kiện cần thiết.
7. **Thực thi kết quả:** chỉ đọc/sửa/xóa hoặc trả dữ liệu sau khi chính sách ra quyết định **ALLOW**.

~~~mermaid
flowchart TD
    A["Yêu cầu tới API kèm access token"] --> B{"JWT hợp lệ cho API này?"}
    B -- "Không" --> C["401 Unauthorized"]
    B -- "Có" --> D["Tạo principal từ claims đã xác minh"]
    D --> E["Lấy tài nguyên và dữ liệu quyền hiện tại"]
    E --> F{"Chính sách cho phép hành động này?"}
    F -- "Không" --> G["403 Forbidden hoặc 404 theo chính sách che giấu"]
    F -- "Có" --> H["Thực thi hành động, trả kết quả"]
~~~

Trong HTTP, **401 Unauthorized** thường thể hiện yêu cầu thiếu thông tin xác thực hợp lệ hoặc token không được chấp nhận; **403 Forbidden** thường thể hiện đã nhận diện được bên gọi nhưng không đủ quyền. Một số API chủ động trả **404 Not Found** để tránh tiết lộ sự tồn tại của tài nguyên mà bên gọi không được biết. Mã phản hồi phải nhất quán với hợp đồng và chính sách bảo mật của API.

## 5. Xây dựng chính sách: chủ thể, hành động, tài nguyên, ngữ cảnh

Một cách mô tả phổ biến là quyết định dựa trên bốn thành phần:

**ALLOW/DENY = Policy(Principal, Action, Resource, Context)**

Trong đó:

- **Principal:** chủ thể được xác định bởi **iss + sub**, loại chủ thể, tổ chức đang hoạt động và quyền liên quan.
- **Action:** thao tác cụ thể như **invoice.read**, **invoice.create**, **invoice.approve**.
- **Resource:** hóa đơn nào, thuộc tổ chức nào, do ai sở hữu, ở trạng thái nào.
- **Context:** trạng thái thành viên hiện tại, mức bảo đảm phiên, điều kiện nghiệp vụ hoặc các hạn chế bổ sung.

Chính sách minh họa cho việc đọc một hóa đơn:

~~~text
ALLOW invoice.read KHI VÀ CHỈ KHI:
    token hợp lệ cho API hóa đơn
    AND token có scope "invoice:read"
    AND tài khoản còn là thành viên đang hoạt động của tenant
    AND invoice.tenant_id = tenant đã được xác minh cho yêu cầu
    AND (
        invoice.owner_id = tài khoản nội bộ của chủ thể
        OR thành viên có role "invoice_auditor" đang hiệu lực
    )
    AND invoice.state != "SEALED"

Mọi trường hợp khác: DENY
~~~

Ở đây, **owner_id** lấy từ bản ghi hóa đơn, role đang hiệu lực lấy từ nguồn quyền do hệ thống kiểm soát, và tenant của token chỉ được sử dụng theo hợp đồng phát hành đáng tin cậy. Nếu có nhiều nguồn đưa ra thông tin mâu thuẫn, chính sách phải định nghĩa cách xử lý; an toàn nhất là từ chối khi không thể xác định được quyền.

### 5.1. Phân biệt các mô hình phân quyền

- **RBAC (Role-Based Access Control):** quyết định từ vai trò, ví dụ người kiểm toán được đọc hóa đơn trong tổ chức của mình. Phù hợp để gom nhóm nhiệm vụ, nhưng role đơn lẻ thường quá thô cho quyền trên từng tài nguyên.
- **ABAC (Attribute-Based Access Control):** kết hợp thuộc tính của principal, hành động, tài nguyên và ngữ cảnh, ví dụ chỉ được xem hóa đơn cùng tenant và chưa niêm phong.
- **Quan hệ/ACL:** kiểm tra quan hệ sở hữu, thành viên, người được chia sẻ hoặc danh sách kiểm soát truy cập của tài nguyên.

Các mô hình có thể kết hợp. JWT có thể mang một số thuộc tính đầu vào, còn **chính sách và trạng thái tài nguyên có thể nằm ngoài token**. Không nên nhồi toàn bộ đồ thị quyền phức tạp vào một JWT dài hạn rồi coi đó là nguồn quyết định duy nhất.

### 5.2. Ví dụ đa tổ chức (multi-tenant)

Hệ thống quản lý hóa đơn có hai tổ chức **company-a** và **company-b**. API nhận yêu cầu:

~~~http
GET /tenants/company-b/invoices/INV-100 HTTP/1.1
Host: api.example.test
Authorization: Bearer <access-token>
~~~

Giả sử token hợp lệ nhưng claim **tenant_id = company-a**. API phải ngăn truy cập hóa đơn của **company-b**, ngay cả khi token có scope **invoice:read** hoặc role **billing_reader**. Không được lấy riêng tenant từ đường dẫn do client điều khiển để thay thế phạm vi tenant đã xác minh.

Ngược lại, nếu token ghi **company-a** và URL cũng là **company-a**, điều đó **vẫn chưa đủ**: tài nguyên có thể không thuộc tenant này, quyền thành viên có thể bị thu hồi, hoặc hóa đơn bị hạn chế theo trạng thái/sở hữu.

Nếu một người có quyền trong nhiều tenant, hệ thống phải định nghĩa cơ chế chọn ngữ cảnh tenant rõ ràng, các nguồn tin cậy cho tư cách thành viên và quy tắc kiểm tra đối chiếu. Không suy rằng quyền ở một tenant tự động áp dụng cho tenant khác.

## 6. Pseudocode: kiểm tra quyền đọc hóa đơn ở API

Ví dụ sau diễn đạt thuật toán độc lập ngôn ngữ. Hàm **validateAccessToken** được giả định đã thực hiện **đầy đủ** các kiểm tra chữ ký, issuer, audience, thuật toán, thời gian và profile access token theo cấu hình; không chỉ giải mã payload.

~~~text
function readInvoice(request):
    token = extractBearerToken(request.headers.Authorization)

    verified = validateAccessToken(
        token,
        trustedIssuer = "https://identity.example.test",
        expectedAudience = "https://api.example.test/invoices",
        allowedAlgorithms = ["RS256"],
        requiredTokenProfile = "at+jwt"
    )

    if verified.failed:
        return HTTP 401

    claims = verified.claims
    principal = resolvePrincipal(claims.iss, claims.sub)
    if principal is null:
        return HTTP 403

    if not containsExactScope(claims.scope, "invoice:read"):
        return HTTP 403

    requestedTenant = request.path.tenantId
    if requestedTenant != claims.tenant_id:
        return HTTP 404

    invoice = loadInvoice(requestedTenant, request.path.invoiceId)
    if invoice is null:
        return HTTP 404

    membership = loadCurrentMembership(principal, requestedTenant)
    if membership is null or not membership.active:
        return HTTP 403

    if not policyCanReadInvoice(principal, membership, invoice):
        return HTTP 403

    return HTTP 200 with invoice
~~~

**Giới hạn của ví dụ:** thuộc tính **requiredTokenProfile = "at+jwt"** chỉ phù hợp khi hệ thống phát hành cam kết dùng profile đó. Những hệ thống khác phải áp dụng dấu hiệu phân biệt access token theo hợp đồng của mình. Trả **404** khi tenant không khớp là một lựa chọn che giấu tài nguyên; một API khác có thể trả **403** nếu chính sách yêu cầu. Pseudocode cũng lược bỏ xử lý lỗi hạ tầng, audit và giao dịch dữ liệu.

Đặc biệt, thao tác **ghi hoặc sửa** phải áp dụng kiểm tra tương tự ngay tại điểm thay đổi dữ liệu. Không chỉ bảo vệ trang giao diện, danh sách tài nguyên hoặc một endpoint "kiểm tra quyền" riêng rồi bỏ qua quyền trong endpoint thực thi.

## 7. Kiểm tra token đúng trước khi dùng claims

Một token với các claim phân quyền trông hợp lệ vẫn phải bị từ chối nếu không vượt qua yêu cầu xác minh. Các kiểm tra quan trọng gồm:

| Kiểm tra | Lý do |
| --- | --- |
| **Nguồn khóa tin cậy và chữ ký** | Chỉ chấp nhận khóa được liên kết an toàn với issuer đã tin cậy; không dùng khóa tùy ý do token hoặc client chỉ định. |
| **Danh sách thuật toán được chấp nhận** | Chặn token dùng thuật toán ngoài cấu hình, lựa chọn thuật toán không an toàn hoặc tình huống nhầm lẫn loại khóa. Không chấp nhận token không chữ ký khi API yêu cầu JWT có chữ ký. |
| **iss** | Token không được phát hành bởi issuer dành cho hệ thống này phải bị loại. |
| **aud** | Access token cấp cho dịch vụ khác không được dùng lại trên API này, kể cả khi cùng issuer. |
| **exp, nbf và giới hạn thời gian** | Token hết hạn, chưa có hiệu lực hoặc vượt chính sách thời gian phải bị từ chối; độ lệch đồng hồ cần được giới hạn. |
| **Mục đích và loại token** | Token dùng để đăng nhập ở client, token làm mới hoặc loại bằng chứng khác không được tự động chấp nhận như API access token. |
| **Claims bắt buộc theo hợp đồng** | Kiểm tra kiểu, định dạng, tập giá trị hợp lệ của tenant, scope, client hay những claim mà API thực sự cần. |

**ID token và access token có mục đích khác nhau.** Trong OpenID Connect, ID token thường hướng đến ứng dụng khách để xác nhận thông tin đăng nhập; API tài nguyên phải yêu cầu access token được cấp cho chính API theo hợp đồng tương ứng. Không được suy ra "đều có JWT và chữ ký đúng" nên có thể thay thế cho nhau.

**JWT được ký thường đọc được nội dung payload.** Chữ ký không đồng nghĩa với mã hóa. Tránh đưa mật khẩu, bí mật, dữ liệu nhạy cảm hoặc những thông tin không cần thiết vào claims; sử dụng HTTPS và hạn chế ghi token vào log, URL hay công cụ phân tích.

Đối với khóa ký được công bố qua tập khóa công khai, trường **kid** chỉ nên giúp chọn khóa **trong tập đã tin cậy**. Không lấy URL khóa bên trong một token chưa tin cậy rồi tải và sử dụng tùy ý. Việc quay vòng khóa cũng phải duy trì kiểm soát nguồn khóa và chính sách thuật toán.

## 8. Tình huống quyết định: một token, nhiều kết quả

Giả sử API có quy tắc: người dùng phải có scope **invoice:read**, còn là thành viên đang hoạt động của tenant; người sở hữu được đọc hóa đơn của mình, người giữ role **invoice_auditor** hiện hành được đọc hóa đơn khác trong cùng tenant, và hóa đơn **SEALED** không được đọc theo thao tác thông thường.

| Yêu cầu | Những dữ kiện quyết định | Kết quả minh họa |
| --- | --- | --- |
| Nhân viên đọc hóa đơn của chính mình trong **company-a** | Token hợp lệ, đúng audience, đúng scope; còn tư cách thành viên; tài nguyên cùng tenant và chưa bị khóa. | **ALLOW** |
| Nhân viên đọc hóa đơn của người khác trong **company-a** | Token hợp lệ, đúng scope, nhưng không là chủ sở hữu và không có role kiểm toán hiện hành. | **DENY (403)** |
| Người có role quản trị **company-a** đọc hóa đơn **company-b** | Role có thể mạnh nhưng tài nguyên nằm ngoài tenant được phép. | **DENY (403 hoặc 404)** |
| Người sở hữu đọc hóa đơn **SEALED** | Danh tính và scope đúng, nhưng quy tắc trạng thái tài nguyên cấm. | **DENY (403)** |
| Người được phép đọc nhưng access token hết hạn | Token không vượt qua xác minh thời gian. | **Từ chối xác thực (401)** |
| Client gửi token dành cho một API khác | **aud** không phù hợp với API hóa đơn. | **Từ chối xác thực (401)** |
| Nhân viên bị thu hồi tư cách thành viên sau lúc phát hành token | Claim role cũ vẫn còn nhưng dữ liệu thành viên hiện tại không cho phép. | **DENY (403)** |
| Tài khoản dịch vụ gọi API chỉ dành cho nhân viên | Token có thể hợp lệ nhưng loại principal không đáp ứng chính sách nghiệp vụ. | **DENY (403)** |

Các mã HTTP là lựa chọn điển hình, không phải một phép ánh xạ bắt buộc cho mọi hệ thống. Điều bất biến là **không thực thi thao tác khi thiếu bằng chứng quyền truy cập phù hợp**.

## 9. Những lỗi phân quyền thường gặp

| Sai lầm | Rủi ro | Hướng xử lý |
| --- | --- | --- |
| Giải mã payload rồi dùng **sub**, **roles** ngay | Bên gọi có thể tự sửa claim nếu token chưa được xác minh. | Xác minh token hoàn chỉnh trước khi xây dựng principal. |
| Chỉ kiểm tra chữ ký, bỏ qua **aud** hoặc **iss** | Token phát hành cho ứng dụng/dịch vụ khác có thể bị dùng nhầm. | Ràng buộc issuer và audience cho từng API. |
| Coi **authenticated = authorized** | Người đăng nhập được truy cập tài nguyên vượt quyền. | Kiểm tra hành động và tài nguyên ở mỗi thao tác nhạy cảm. |
| Coi **scope = quyền trên mọi đối tượng** | Đọc/sửa tài nguyên của người khác hoặc tổ chức khác. | Kết hợp scope với kiểm tra sở hữu, tenant và chính sách tài nguyên. |
| Tin **tenant_id** hoặc **user_id** tùy ý trong URL/body | Vượt ranh giới tổ chức hoặc mạo danh chủ thể. | Dùng danh tính đã xác minh, đối chiếu dữ liệu tài nguyên từ nguồn tin cậy. |
| Tin role đã nhúng vào JWT mãi đến khi hết hạn | Người bị gỡ quyền vẫn có thể thao tác. | Giới hạn tuổi token; kiểm tra quyền hiện tại hoặc cơ chế thu hồi khi cần. |
| Quyền được kiểm tra ở giao diện, bỏ quên API | Gọi trực tiếp API để vượt kiểm soát. | Thực thi phân quyền ở backend tại điểm truy cập và thay đổi dữ liệu. |
| Chấp nhận ID token như access token | Token sai mục đích được dùng để truy cập API. | Phân biệt profile, audience và mục đích token. |
| Cho phép mặc định nếu thiếu role, scope hoặc dữ liệu quyền | Lỗi dữ liệu/hạ tầng làm mở rộng quyền. | **Deny by default**, ghi nhận lỗi và xử lý thiếu dữ kiện rõ ràng. |
| Nhúng thông tin quá nhạy cảm vào claims | Thông tin có thể lộ vì JWT có chữ ký không nhất thiết được mã hóa. | Chỉ đưa thông tin tối thiểu và bảo vệ đường truyền/lưu trữ. |

### 9.1. Nếu quyền thay đổi, nên xử lý thế nào?

Có thể kết hợp các kỹ thuật, tùy nhu cầu nghiệp vụ:

- **Access token có thời hạn ngắn:** giảm thời gian claim cũ còn được chấp nhận; không có tác dụng thu hồi tức thì.
- **Kiểm tra trạng thái tập trung tại thời điểm yêu cầu:** dùng nguồn dữ liệu/quyết định quyền hiện hành cho thao tác quan trọng.
- **Thu hồi hoặc chặn token:** sử dụng ID token hoặc trạng thái phiên theo cơ chế của hệ thống, đồng thời cân nhắc chi phí lưu trữ và độ trễ.
- **Phiên bản chính sách/quyền:** so sánh phiên bản quyền trong token với phiên bản được server kiểm soát khi cần nhận biết thay đổi.
- **Introspection hoặc token tham chiếu:** phù hợp trong hệ thống cần xác định trạng thái token tập trung; không phải mọi access token đều cần hoặc hỗ trợ cơ chế này.

Không có một lựa chọn duy nhất cho mọi sản phẩm. API tài chính hoặc thao tác quản trị có thể cần quyền cập nhật sát thời gian thực, trong khi truy cập nội dung ít nhạy cảm có thể chấp nhận một khoảng trễ ngắn phù hợp với thời hạn access token.

## 10. Thiết kế hợp đồng claims và kiểm thử quyết định

Khi xây dựng hệ thống phát hành và tiếp nhận JWT, nên định nghĩa rõ:

1. **Issuer và audience nào được chấp nhận?** API nào dùng token, phân biệt access token với những loại token khác ra sao?
2. **Chủ thể là loại thực thể nào?** Người dùng, tài khoản dịch vụ hay một tác nhân được ủy quyền; cách ánh xạ **(iss, sub)** sang tài khoản nội bộ.
3. **Claims nào do issuer bảo đảm?** Kiểu dữ liệu, tập giá trị, định dạng scope, các claim bắt buộc và cách xử lý giá trị không nhận biết.
4. **Nguồn nào quyết định quyền hiện hành?** Vai trò từ token, cơ sở dữ liệu phân quyền, dịch vụ chính sách, quan hệ sở hữu hoặc tổ hợp của chúng.
5. **Ranh giới tài nguyên là gì?** Chủ sở hữu, tenant, trạng thái tài nguyên và các ràng buộc nghiệp vụ có thể làm thay đổi kết quả.
6. **Quy tắc từ chối và ghi nhận là gì?** Tình huống trả 401/403/404; log quyết định với định danh tối thiểu cần thiết, không lộ toàn bộ JWT.

Một tập kiểm thử phân quyền có giá trị cần bao phủ **cả trường hợp được phép lẫn bị từ chối**:

~~~text
Token hợp lệ + đúng scope + đúng tài nguyên      -> ALLOW (nếu chính sách phù hợp)
Token hợp lệ + thiếu scope                      -> DENY
Token hợp lệ + sai tenant                       -> DENY
Token hợp lệ + tài nguyên của người khác        -> DENY nếu không có quyền đặc biệt
Token hợp lệ + quyền thành viên đã bị thu hồi   -> DENY theo chính sách hiện hành
Token hợp lệ + trạng thái tài nguyên bị cấm     -> DENY
Token hết hạn / sai issuer / sai audience       -> từ chối token
Không có token bắt buộc                         -> từ chối xác thực
~~~

Kiểm thử nên thực hiện trên **endpoint thực sự đọc hoặc thay đổi tài nguyên**, không chỉ trên hàm kiểm tra role, để phát hiện lỗi bỏ sót phân quyền ở mức đối tượng (object-level authorization).

## 11. Ghi nhớ trọng tâm

- **sub** trả lời chủ thể được issuer khai báo là ai; **scope**, **roles** hoặc **permissions** chỉ cung cấp dữ kiện cho chính sách.
- **iss**, **aud**, chữ ký, thời gian và mục đích sử dụng token phải hợp lệ **trước** khi API được tin vào claims.
- **JWT hợp lệ ≠ quyền truy cập hợp lệ**: quyền phụ thuộc hành động, tài nguyên, tenant và ngữ cảnh hiện tại.
- Cần đánh giá quyền trên **từng tài nguyên** ở API, nhất là ranh giới người dùng và tổ chức.
- Claims có thể cũ; thời hạn token, thu hồi và kiểm tra quyền hiện tại phải phù hợp mức độ nhạy cảm.
- Khi không đủ bằng chứng để cho phép, **mặc định từ chối** và chỉ thực thi khi chính sách trả **ALLOW**.

**Tài liệu chuẩn để tra cứu:** RFC 7519 (JSON Web Token, định nghĩa các registered claims); RFC 8725 (JWT Best Current Practices, các nguyên tắc kiểm tra an toàn); RFC 9068 (JWT Profile for OAuth 2.0 Access Tokens, trong những hệ thống áp dụng profile này); RFC 6750 (OAuth 2.0 Bearer Token Usage, cách mang bearer token và phản hồi lỗi liên quan). Cần đối chiếu thêm hợp đồng phát hành token và chính sách phân quyền của hệ thống thực tế.
