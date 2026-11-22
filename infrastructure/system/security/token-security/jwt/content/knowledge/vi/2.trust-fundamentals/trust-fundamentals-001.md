# Phân biệt xác thực danh tính, phân quyền và toàn vẹn dữ liệu

Trong hệ thống bảo mật sử dụng JSON Web Token (JWT), ba khái niệm **xác thực danh tính** (*authentication*), **phân quyền** (*authorization*) và **toàn vẹn dữ liệu** (*integrity*) thường xuất hiện trong cùng một luồng xử lý. Tuy có liên quan, chúng giải quyết những câu hỏi khác nhau và cần được kiểm tra độc lập. Đây là nền tảng tin cậy để thiết kế và đánh giá cơ chế bảo mật JWT cho ứng dụng web, API, dịch vụ và hệ thống phân tán ở bất kỳ ngôn ngữ lập trình nào.

## 1. Ba câu hỏi bảo mật khác nhau

| Khái niệm | Câu hỏi cần trả lời | Bằng chứng hoặc cơ chế thường dùng | Nếu thiếu kiểm tra |
| --- | --- | --- | --- |
| **Xác thực danh tính (authentication)** | Bên đang tương tác được xác nhận là ai, hoặc đang đại diện cho thực thể nào? | Mật khẩu kết hợp MFA, khóa bảo mật, chứng chỉ, phiên đăng nhập, hoặc thông tin xác thực do bên cấp tin cậy phát hành | Có thể gán yêu cầu cho sai thực thể hoặc chấp nhận yêu cầu không có danh tính đáng tin |
| **Phân quyền (authorization)** | Thực thể đó được phép làm **hành động nào** trên **tài nguyên nào**, trong **điều kiện nào**? | Chính sách truy cập, quyền, phạm vi (scope), vai trò, quyền sở hữu, thuộc tính tài nguyên và ngữ cảnh | Người dùng hợp lệ có thể đọc hoặc sửa dữ liệu vượt quyền |
| **Toàn vẹn dữ liệu (integrity)** | Nội dung có bị thay đổi trái phép trong phạm vi được bảo vệ hay không? | Chữ ký số, mã xác thực thông điệp (MAC), cơ chế toàn vẹn trong mã hóa có xác thực, TLS trong quá trình truyền | Nội dung bị chỉnh sửa có thể bị sử dụng như dữ liệu hợp lệ |

Hai thuộc tính liên quan cũng cần phân biệt:

- **Tính xác thực của nguồn gốc (authenticity):** ai hoặc bên nào đã phát hành/thể hiện nội dung? Chữ ký hoặc MAC có thể giúp xác minh nguồn phát hành khi khóa được quản lý và gắn với bên tin cậy.
- **Tính bí mật (confidentiality):** bên không được phép có đọc được nội dung hay không? Mã hóa và kiểm soát truy cập giải quyết vấn đề này; chữ ký số tự nó không che giấu nội dung.

Ví dụ: Alice đăng nhập thành công vào một dịch vụ hóa đơn. Máy chủ có thể xác thực rằng yêu cầu sử dụng thông tin đăng nhập của Alice, nhưng vẫn phải kiểm tra Alice có quyền xem **hóa đơn số 42** hay không. Nếu một kẻ tấn công sửa nội dung token từ Alice thành quản trị viên, kiểm tra chữ ký sẽ phát hiện thay đổi khi token được ký và xác minh đúng cách. Cả ba phép kiểm tra cùng cần thiết.

## 2. Xác thực danh tính: «Ai đang tương tác?»

**Danh tính** là cách một hệ thống nhận diện một thực thể: người dùng, dịch vụ, thiết bị hoặc một ứng dụng. Một định danh như `user-42` chỉ là tên/khóa nhận diện. **Xác thực** là quá trình kiểm tra bằng chứng để có cơ sở tin cậy rằng thực thể đang tương tác đúng với danh tính được khai báo hoặc đang sở hữu thông tin xác thực phù hợp.

Một luồng phổ biến:

1. Người dùng chứng minh danh tính với hệ thống xác thực, chẳng hạn bằng mật khẩu và yếu tố xác thực bổ sung.
2. Bên phát hành token, sau khi kiểm tra điều kiện cần thiết, phát hành token chứa các tuyên bố (*claims*) về chủ thể, mục đích sử dụng và thời hạn.
3. API nhận token ở yêu cầu tiếp theo, kiểm tra token do nguồn đáng tin phát hành, dành cho API này và còn hợp lệ.
4. API hình thành **ngữ cảnh chủ thể** cho yêu cầu; sau đó mới quyết định người đó được phép thực hiện tác vụ hay không.

JWT không tự thực hiện bước đăng nhập ban đầu. JWT là **định dạng mang các claims**. Một JWT được ký hợp lệ có thể giúp bên nhận tin rằng các claims không bị chỉnh sửa sau khi bên nắm khóa ký phát hành. Nhưng bên nhận vẫn cần biết **bên phát hành có đáng tin không**, token có đúng mục đích không và có đủ điều kiện để chấp nhận yêu cầu hiện tại không.

### Danh tính trong JWT không đồng nghĩa với sự hiện diện của người dùng

Claim `sub` (*subject*) có thể định danh người dùng, ứng dụng hoặc một chủ thể khác. Đọc chuỗi `sub` từ payload chưa chứng minh được điều gì: payload có thể được tạo hoặc thay đổi tùy ý trước khi token được xác minh. Ngay cả sau khi xác minh token, `sub` cho biết **chủ thể được bên phát hành tuyên bố**, không nhất thiết chứng minh chính người đó đang trực tiếp thao tác ở thời điểm yêu cầu.

Đặc biệt, với **bearer token**, ai sở hữu token hợp lệ thường có khả năng sử dụng token đó. Nếu token bị đánh cắp, chữ ký vẫn hợp lệ nhưng người gửi yêu cầu có thể là kẻ tấn công. Các biện pháp như TLS, bảo vệ nơi lưu token, thời hạn ngắn, phát hiện hoặc thu hồi token bị lộ và token ràng buộc với bên gửi (khi thích hợp) giải quyết những rủi ro bổ sung này.

## 3. Phân quyền: «Được làm gì trên tài nguyên nào?»

Xác thực thành công là **đầu vào** của một quyết định phân quyền, không phải quyết định phân quyền. Câu hỏi đầy đủ thường có dạng:

> Chủ thể **S** có được phép thực hiện hành động **A** trên tài nguyên **R**, trong ngữ cảnh **C** không?

Ví dụ, API nhận `GET /invoices/42` cùng token hợp lệ có `sub=user-42` và `scope=invoice:read`. Các kiểm tra tiếp theo có thể gồm:

1. Token này có được cấp quyền gọi chức năng đọc hóa đơn không?
2. Hóa đơn 42 có thuộc tài khoản, tổ chức hoặc vùng dữ liệu mà `user-42` được truy cập không?
3. Có chính sách bổ sung như giới hạn trạng thái hóa đơn, thời gian, thiết bị hoặc mức phê duyệt không?

Chỉ khi chính sách yêu cầu được thỏa mãn thì API mới cung cấp dữ liệu. Một scope chung như `invoice:read` **không tự động** cho phép đọc mọi hóa đơn trong hệ thống.

Các mô hình thường gặp:

| Mô hình | Cách quyết định | Điểm cần lưu ý |
| --- | --- | --- |
| RBAC (*Role-Based Access Control*) | Vai trò, ví dụ `auditor`, gắn với tập quyền | Vai trò là một đầu vào; vẫn cần giới hạn tài nguyên và phạm vi tổ chức |
| ABAC (*Attribute-Based Access Control*) | Thuộc tính của chủ thể, tài nguyên, hành động và môi trường | Phù hợp quy tắc theo tổ chức, độ nhạy dữ liệu, trạng thái, thời gian |
| Quyền theo quan hệ hoặc quyền sở hữu | Quan hệ giữa chủ thể và tài nguyên, ví dụ chủ sở hữu, người được chia sẻ | Cần đọc quan hệ từ nguồn dữ liệu đáng tin; không suy đoán từ ID trên URL |
| Scope/permission trong access token | Quyền/phạm vi được bên phát hành cho phép hoặc ủy quyền | Phải khớp chính sách của API; scope thường chỉ là một giới hạn, không thay thế kiểm tra quyền trên đối tượng |

Những claim như `role`, `permissions` hay `scope` có thể hỗ trợ quyết định phân quyền **sau khi token được xác minh và các claims được kiểm tra**. Tuy nhiên, chúng có thể đã cũ nếu quyền của người dùng thay đổi trước khi token hết hạn. Với quyền nhạy cảm hoặc cần thu hồi ngay, API có thể cần tra cứu chính sách hiện hành, dùng token sống ngắn hoặc cơ chế thu hồi/phát hiện vô hiệu.

**Nguyên tắc thực hành:** kiểm tra quyền ở nơi thực thi thao tác; không mặc định rằng việc giao diện đã ẩn nút hoặc client đã kiểm tra quyền thì API được phép bỏ qua.

## 4. Toàn vẹn dữ liệu: «Nội dung có bị can thiệp không?»

Toàn vẹn nhằm phát hiện thay đổi trái phép đối với **phần dữ liệu cụ thể được cơ chế bảo vệ bao phủ**.

- **Hàm băm (hash)** tạo dấu vân tay của dữ liệu; bản thân hash không chứng minh ai đã tạo dữ liệu nếu bên tấn công có thể thay cả dữ liệu lẫn hash.
- **MAC/HMAC** kiểm tra toàn vẹn và tính xác thực nguồn đối với các bên cùng biết khóa bí mật.
- **Chữ ký số bất đối xứng** dùng khóa riêng để ký và khóa công khai tương ứng để kiểm chứng; chỉ có giá trị tin cậy khi khóa xác minh thực sự gắn với bên phát hành dự kiến.
- **Mã hóa có xác thực** có thể cung cấp đồng thời bí mật và kiểm tra tính toàn vẹn của thông điệp đã mã hóa.
- **TLS** bảo vệ kết nối trong quá trình truyền, nhưng không tự thay thế các kiểm tra quyền hoặc tính đúng đắn của dữ liệu đã lưu.

### Chữ ký JWT bảo vệ cái gì?

JWT thường được phát hành dưới dạng **JWS Compact Serialization** gồm ba phần ngăn bằng dấu chấm:

~~~text
BASE64URL(header).BASE64URL(payload).BASE64URL(signature)
~~~

Ví dụ về header và payload **đã giải mã để minh họa**, chưa phải một token hoàn chỉnh.

Header:

~~~json
{
  "alg": "RS256",
  "typ": "JWT"
}
~~~

Payload:

~~~json
{
  "iss": "https://identity.example.org",
  "sub": "user-42",
  "aud": "https://billing-api.example.org",
  "exp": 2000000000,
  "scope": "invoice:read",
  "tenant_id": "org-7"
}
~~~

Trong JWS, chữ ký/MAC được tính trên **biểu diễn đã mã hóa Base64url của header và payload theo định dạng JWS**. Nếu thay `sub` từ `user-42` thành `admin`, thay scope hoặc sửa header mà không thể tạo lại chữ ký hợp lệ, phép xác minh phải thất bại. Tuy nhiên:

- Base64url chỉ là **mã hóa biểu diễn**, không phải mã hóa để giữ bí mật: người nhìn thấy JWS có thể đọc header và payload.
- Chữ ký hợp lệ không khẳng định claims đúng với hiện trạng cơ sở dữ liệu, không khẳng định người giữ token là chủ thể thật, và không đồng nghĩa với việc cho phép mọi thao tác.
- Chữ ký token không tự bảo vệ nội dung body của một yêu cầu HTTP, dữ liệu lưu trong cơ sở dữ liệu hoặc kết quả trả về. Mỗi phần cần cơ chế bảo vệ đúng phạm vi.
- JWT cũng có thể được bảo vệ dưới dạng **JWE** (mã hóa; Compact Serialization thường có năm thành phần), hoặc có những biểu diễn không ký. Vì thế không được giả định mọi chuỗi JWT đều được ký chỉ vì nó có tên JWT.

**HS256** là ví dụ thuật toán MAC sử dụng khóa bí mật dùng chung; **RS256** là ví dụ chữ ký bất đối xứng với khóa riêng/khóa công khai. Việc lựa chọn phải theo cấu hình tin cậy của hệ thống; không cho token tự chỉ định một thuật toán hoặc nguồn khóa ngoài chính sách cho phép.

## 5. JWT tham gia vào một chuỗi quyết định như thế nào?

~~~mermaid
flowchart TD
    A["Yêu cầu đến API kèm access token"] --> B{"Token được cung cấp và đúng định dạng?"}
    B -- "Không" --> X["Từ chối: chưa có thông tin xác thực hợp lệ"]
    B -- "Có" --> C{"Xác minh mật mã bằng khóa đáng tin và thuật toán được phép?"}
    C -- "Không" --> X
    C -- "Có" --> D{"Kiểm tra claims: issuer, audience, thời hạn, mục đích?"}
    D -- "Không" --> X
    D -- "Có" --> E["Lập ngữ cảnh chủ thể và quyền liên quan"]
    E --> F{"Chính sách có cho hành động trên tài nguyên này?"}
    F -- "Không" --> Y["Từ chối vì không đủ quyền"]
    F -- "Có" --> G["Thực thi và trả kết quả"]
~~~

Sơ đồ minh họa một trường hợp API dùng access token dạng JWT được ký. Trong HTTP API, thiếu/hỏng/không hợp lệ thông tin xác thực thường tương ứng **401 Unauthorized** (kèm yêu cầu/challenge xác thực thích hợp); danh tính đã được chấp nhận nhưng không đủ quyền thường tương ứng **403 Forbidden**. Mã phản hồi cụ thể còn tùy hợp đồng API và chính sách tránh tiết lộ sự tồn tại của tài nguyên.

### Tại sao phải kiểm tra cả chữ ký lẫn claims?

Giả sử hệ thống nhận một token có chữ ký mật mã hợp lệ. Điều đó vẫn **chưa đủ** để chấp nhận:

| Kiểm tra | Ý nghĩa | Ví dụ lỗi dù chữ ký hợp lệ |
| --- | --- | --- |
| Khóa tin cậy và thuật toán | Xác minh bằng khóa gắn với bên phát hành được hệ thống tin cậy; chỉ nhận các thuật toán đã cho phép | Token từ nguồn lạ hoặc cấu hình thuật toán sai |
| `iss` (*issuer*) | Token được cấp bởi nguồn phát hành được chấp nhận và khớp với bộ khóa xác minh | Token do nhà cung cấp khác cấp |
| `aud` (*audience*) | Token dành cho chính API/dịch vụ nhận | Token hợp lệ dành cho dịch vụ A bị gửi sang dịch vụ B |
| `exp` (*expiration time*) | Chưa hết hạn theo chính sách, có thể tính độ lệch đồng hồ nhỏ | Token từng hợp lệ nhưng đã hết hạn |
| `nbf` (*not before*) | Chưa được dùng trước thời điểm cho phép, nếu có claim này | Token phát hành cho thời điểm trong tương lai |
| `iat` (*issued at*) | Thời điểm phát hành, nếu có; có thể dùng trong chính sách về tuổi token | Token quá cũ theo chính sách riêng dù chưa đến `exp` |
| Loại token và mục đích | Đúng loại thông tin xác thực cho luồng xử lý; có thể ràng buộc bằng header `typ` và các quy tắc cụ thể | ID token dành cho client bị dùng như access token của API |
| Claims và ngữ cảnh truy cập | Chủ thể, scope/quyền, tổ chức, tài nguyên, trạng thái hiện hành đều phù hợp | Scope đọc hóa đơn nhưng truy cập hóa đơn của tổ chức khác |

Những trường không bắt buộc xuất hiện trong **mọi** JWT theo chuẩn: ứng dụng phải quy định chính xác claim nào là bắt buộc trong từng loại token và từ chối token không đáp ứng hợp đồng đó. Không được xem việc giải mã payload, đọc `role` hoặc so sánh riêng `exp` là đã hoàn thành xác minh token.

## 6. Năm tình huống dễ nhầm lẫn

### Tình huống A — Sửa claim để tăng quyền

Một client lấy token có `scope=invoice:read`, chỉnh payload thành `scope=invoice:write`, rồi gửi API. Nếu API xác minh chữ ký và thuật toán đúng cách, token bị sửa phải bị từ chối. Đây là **kiểm soát toàn vẹn**, diễn ra trước bước phân quyền.

### Tình huống B — Token hợp lệ nhưng người dùng không được xem tài nguyên

Alice sở hữu token đã xác thực với scope đọc hóa đơn, nhưng gọi `GET /invoices/42` trong khi hóa đơn 42 thuộc Bob. Chữ ký, thời hạn và danh tính có thể đều hợp lệ; API vẫn phải từ chối theo **phân quyền trên tài nguyên**.

### Tình huống C — Token hợp lệ dành cho dịch vụ khác

Một access token do bên phát hành tin cậy ký, có `aud=service-A`, được gửi tới `service-B`. Dù chữ ký có thể xác minh được, `service-B` phải từ chối vì **audience không khớp**. Đây là kiểm tra token đúng đối tượng sử dụng, không phải quyết định xem người dùng có quyền với tài nguyên nào.

### Tình huống D — Token bị đánh cắp

Kẻ tấn công sao chép bearer token còn hạn của Alice. Token không bị sửa, chữ ký vẫn hợp lệ và claims vẫn thể hiện Alice. Điều này cho thấy **toàn vẹn token không ngăn chiếm dụng token**. Cần bảo vệ kênh truyền và nơi lưu, giảm thời gian sống, quản lý phiên/thu hồi khi cần và cân nhắc cơ chế ràng buộc token với bên gửi.

### Tình huống E — Quyền thay đổi sau khi phát hành

Alice bị thu hồi vai trò quản trị, nhưng access token đã cấp trước đó vẫn chứa `role=admin` và chưa hết hạn. Chữ ký chứng tỏ token chưa bị sửa, **không chứng minh quyền admin còn hiệu lực ở hiện tại**. Hệ thống phải chọn chính sách chấp nhận độ trễ, giảm TTL, tra cứu quyền tại thời điểm yêu cầu hoặc có cơ chế vô hiệu token khi thay đổi quyền.

## 7. Phân biệt ID token, access token và JWT

JWT là **định dạng** biểu diễn claims; **ID token** và **access token** mô tả **mục đích sử dụng**. Chúng không đồng nhất:

| Thành phần | Vai trò chính | Bên tiếp nhận dự kiến | Lưu ý |
| --- | --- | --- | --- |
| JWT | Cách đóng gói các claims; có thể được ký hoặc mã hóa | Tùy hợp đồng giữa bên phát hành và bên nhận | Không tự động mang nghĩa “đã đăng nhập” hoặc “được quyền truy cập API” |
| ID token trong OpenID Connect | Truyền thông tin về sự kiện xác thực và chủ thể cho ứng dụng client | Ứng dụng client có audience phù hợp | Không dùng thay access token để cấp quyền gọi API |
| OAuth 2.0 access token | Đại diện quyền truy cập được cấp cho client theo phạm vi và điều kiện | Resource server/API được chỉ định | Có thể có dạng JWT hoặc chuỗi opaque; API phải kiểm tra bằng cơ chế tương ứng |
| Refresh token | Xin cấp access token mới theo chính sách của authorization server | Bên cấp token | Không phải bằng chứng cho phép API trực tiếp trả dữ liệu tài nguyên |

Ví dụ, một ID token đúng chữ ký và còn hạn vẫn có thể **không hợp lệ đối với billing API**, vì audience thường là client ứng dụng thay vì billing API. Ngược lại, một access token cấp cho tác vụ máy–máy có thể đại diện cho **ứng dụng/dịch vụ** chứ không có người dùng cuối đang đăng nhập.

## 8. Các nguyên tắc thiết kế và kiểm tra thực tế

1. **Xác định ranh giới tin cậy:** API chấp nhận token từ issuer nào, dùng bộ khóa đáng tin nào, dành cho audience và loại token nào.
2. **Xác minh trước khi sử dụng claims:** kiểm tra chữ ký/MAC hoặc cơ chế bảo vệ token tương ứng, sử dụng danh sách thuật toán được phép, xác minh nguồn khóa. Không dựa vào `alg` hay `kid` chưa được kiểm soát để tin một khóa tùy ý do token chỉ đến.
3. **Kiểm tra thời hạn và mục đích:** bắt buộc các claims phù hợp với loại token; kiểm tra `iss`, `aud`, `exp`, `nbf` khi áp dụng, và quy tắc về `iat`, `typ` hoặc các claims bổ sung theo hệ thống.
4. **Phân quyền theo hành động và tài nguyên:** scope/role chỉ là đầu vào. Luôn xét quyền sở hữu, tổ chức/tenant, điều kiện hiện tại và nguyên tắc quyền tối thiểu ở phía máy chủ.
5. **Tách toàn vẹn khỏi bí mật:** token được ký thường đọc được; không đặt mật khẩu, khóa bí mật hoặc dữ liệu nhạy cảm không cần thiết trong payload. Dùng mã hóa thích hợp khi cần bảo mật nội dung.
6. **Giảm tác động của token bị lộ:** bắt buộc kết nối an toàn, bảo vệ nơi lưu, giới hạn thời gian sống và áp dụng chiến lược thu hồi hoặc token ràng buộc bên gửi khi mô hình đe dọa cần.
7. **Phân biệt lỗi để điều tra:** ghi nhận lý do từ chối ở mức phù hợp (sai chữ ký, sai audience, hết hạn, thiếu quyền), đồng thời tránh ghi nguyên token hoặc thông tin bí mật vào nhật ký.
8. **Kiểm thử theo các tình huống độc lập:** token bị sửa, token hết hạn, sai issuer/audience, token hợp lệ không đủ scope, và token đủ scope nhưng không có quyền trên tài nguyên cụ thể.

### Bài tự kiểm tra

Với mỗi trường hợp, hãy xác định vấn đề chính:

| Trường hợp | Vấn đề chính | Giải thích |
| --- | --- | --- |
| Payload bị sửa nhưng chữ ký cũ được giữ nguyên | **Toàn vẹn** | Token phải bị từ chối ở bước xác minh mật mã |
| Token được ký đúng nhưng `aud` là API khác | **Tính hợp lệ/ngữ cảnh của token** | Không được chấp nhận token ngoài đối tượng nhận dự kiến |
| Token hợp lệ của Alice đọc dữ liệu riêng của Bob | **Phân quyền** | Xác thực Alice không mang lại quyền với dữ liệu của Bob |
| Kẻ gian dùng bearer token hợp lệ đã đánh cắp | **Chiếm dụng thông tin xác thực** | Token còn toàn vẹn nhưng người gửi yêu cầu có thể là kẻ gian |
| Dữ liệu nhạy cảm bị lộ khi ai đó giải mã Base64url payload JWS | **Tính bí mật** | Ký không phải là mã hóa nội dung |

## 9. Ghi nhớ mối quan hệ giữa ba khái niệm

**Xác thực** thiết lập ngữ cảnh chủ thể đáng tin cho yêu cầu. **Phân quyền** quyết định chủ thể đó có thể làm gì trên tài nguyên cụ thể. **Toàn vẹn** giúp phát hiện nội dung được bảo vệ có bị sửa đổi trái phép. JWT có thể vận chuyển các claims và, khi được bảo vệ/kiểm tra đúng cơ chế, hỗ trợ xác thực nguồn phát hành và toàn vẹn claims. JWT **không tự thay thế** bước xác thực ban đầu, kiểm tra quyền trên từng tài nguyên, bảo vệ chống đánh cắp token hay kiểm soát bí mật dữ liệu.

### Tài liệu chuẩn để tra cứu

- [RFC 7519 — JSON Web Token (JWT)](https://www.rfc-editor.org/rfc/rfc7519)
- [RFC 7515 — JSON Web Signature (JWS)](https://www.rfc-editor.org/rfc/rfc7515)
- [RFC 7516 — JSON Web Encryption (JWE)](https://www.rfc-editor.org/rfc/rfc7516)
- [RFC 8725 — JSON Web Token Best Current Practices](https://www.rfc-editor.org/rfc/rfc8725)
- [RFC 9068 — JSON Web Token Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068)
- [OpenID Connect Core 1.0](https://openid.net/specs/openid-connect-core-1_0.html)
