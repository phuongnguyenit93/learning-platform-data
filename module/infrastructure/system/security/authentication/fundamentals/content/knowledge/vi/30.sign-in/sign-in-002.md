# Login identifier

## 1. Login identifier là gì?

**Login identifier** là giá trị mà người dùng cung cấp để hệ thống tìm đúng tài khoản trong quá trình đăng nhập. Identifier có thể là username, email, số điện thoại, mã nhân viên, mã khách hàng hoặc một định danh do tổ chức cấp. Sau khi tìm được tài khoản, hệ thống mới xác minh người dùng bằng credential như password, passkey, security key, certificate hoặc một phương thức xác thực khác.

Identifier trả lời câu hỏi **“đang tìm tài khoản nào?”**; credential trả lời câu hỏi **“người đang đăng nhập có chứng minh được quyền kiểm soát tài khoản đó không?”**. Hai khái niệm thường xuất hiện cạnh nhau trên màn hình đăng nhập nhưng có vai trò bảo mật khác nhau.

Trong module **SECURITY_AUTHENTICATION_FUNDAMENTALS**, login identifier là điểm đầu của luồng xác thực. Cách thiết kế identifier ảnh hưởng tới khả năng tìm tài khoản, quyền riêng tư, account linking, khôi phục tài khoản, chống dò tìm và quản lý vòng đời danh tính. Một identifier dễ nhớ giúp người dùng đăng nhập thuận tiện, nhưng cần tránh coi email hoặc số điện thoại là định danh nội bộ bất biến.

Sau bài học, người học có thể:

- Phân biệt login identifier, internal subject ID, username và credential.
- Lựa chọn identifier phù hợp với loại ứng dụng và đối tượng sử dụng.
- Thiết kế uniqueness, namespace và tenant scope.
- Chuẩn hóa email, số điện thoại và Unicode một cách nhất quán.
- Xử lý thay đổi, xác minh, tái sử dụng và thu hồi identifier.
- Thiết kế tra cứu tài khoản mà không làm lộ tài khoản có tồn tại hay không.
- Bảo vệ luồng account linking, recovery và migration.
- Kiểm thử collision, enumeration, normalization và các trường hợp biên.

## 2. Identifier, subject và credential khác nhau thế nào?

Một hệ thống định danh thường có nhiều giá trị liên quan tới cùng một người dùng. Không nên dùng tất cả chúng như thể có cùng ý nghĩa.

| Khái niệm | Vai trò | Ví dụ |
| --- | --- | --- |
| **Login identifier** | Giá trị người dùng nhập để tìm tài khoản | username, email, số điện thoại |
| **Internal subject ID** | Khóa ổn định để hệ thống tham chiếu một principal | UUID hoặc ID ngẫu nhiên do hệ thống cấp |
| **Display name** | Tên hiển thị trong giao diện | Tên đầy đủ hoặc nickname |
| **Credential** | Bằng chứng dùng để xác thực quyền kiểm soát | Password, passkey, security key |
| **Contact attribute** | Kênh liên hệ có thể dùng cho thông báo hoặc recovery | Email, số điện thoại |
| **Federated subject** | Định danh chủ thể trong phạm vi một issuer | Cặp issuer và subject từ OIDC |

Ví dụ, người dùng đăng nhập bằng email, nhưng database nên tham chiếu tài khoản bằng internal subject ID ổn định. Nếu người dùng đổi email, subject ID không cần thay đổi; các bản ghi đơn hàng, quyền, audit và session vẫn liên kết tới cùng principal.

Email có thể là login identifier và contact attribute cùng lúc, nhưng hai vai trò này cần trạng thái riêng. Email được người dùng nhập chưa chắc đã xác minh; email đã xác minh hôm nay có thể được đổi chủ hoặc mất quyền kiểm soát sau này. Không dùng giá trị email làm khóa liên kết vĩnh viễn giữa các hệ thống nếu không có hợp đồng identity rõ ràng.

### 2.1. Identifier không phải bí mật xác thực

Username, email và số điện thoại thường được dùng để nhận diện hoặc tra cứu. Chúng không nên được xem như password hoặc yếu tố xác thực. Một người biết email của bạn không vì thế có quyền đăng nhập vào tài khoản.

Tương tự, internal subject ID có thể xuất hiện trong log hoặc URL nội bộ tùy thiết kế, nhưng không được dùng làm credential. Nếu một hệ thống cho phép đăng nhập chỉ bằng cách biết user ID, đó là lỗi xác thực nghiêm trọng.

### 2.2. Một người có thể có nhiều identifier

Một tài khoản có thể hỗ trợ username và email, hoặc nhiều email đã xác minh, hoặc nhiều phương thức liên hệ theo policy. Những identifier này cần trỏ về cùng một principal nhưng phải có quy tắc uniqueness và lifecycle rõ ràng.

Ví dụ:

- Username dùng để đăng nhập hằng ngày.
- Email dùng để đăng nhập hoặc nhận thông báo.
- Số điện thoại dùng cho recovery nếu policy cho phép.
- Mã nhân viên dùng trong hệ thống nội bộ.
- Federated subject dùng để liên kết với một IdP.

Không nên mặc định mọi identifier đều có cùng mức độ tin cậy hoặc được dùng cho mọi mục đích.

## 3. Chọn loại login identifier

Lựa chọn identifier phụ thuộc vào đối tượng người dùng, cách vận hành tài khoản, mức độ nhạy cảm và khả năng hỗ trợ.

| Loại identifier | Ưu điểm | Hạn chế và rủi ro |
| --- | --- | --- |
| **Username** | Ổn định theo tài khoản, không cần kênh liên hệ riêng | Người dùng có thể quên; cần xử lý uniqueness và đổi tên |
| **Email** | Dễ nhớ, thuận tiện cho liên hệ và recovery | Có thể đổi chủ, bị chiếm hộp thư, alias hoặc normalization khác nhau |
| **Số điện thoại** | Thuận tiện trên mobile và OTP | Có thể tái cấp, chuyển mạng, SIM swap hoặc dùng chung |
| **Employee/customer ID** | Có thể phù hợp trong tổ chức có nguồn cấp mã chính thức | Không nên lộ thông tin nội bộ; cần namespace và quy trình cấp lại |
| **Opaque account handle** | Khó đoán và ổn định nếu được quản lý tốt | Khó nhớ; không tự tạo authentication |
| **Federated identifier** | Cho phép đăng nhập qua IdP | Chỉ duy nhất trong phạm vi issuer; có thể thay đổi theo cấu hình IdP |

### 3.1. Username

Username phù hợp khi ứng dụng muốn một tên đăng nhập do người dùng chọn hoặc tổ chức cấp. Cần xác định:

- Username có phân biệt chữ hoa/chữ thường không?
- Có cho phép dấu cách, ký tự Unicode hoặc dấu chấm không?
- Có được đổi username sau khi tạo không?
- Username đã dùng có được cấp lại sau khi tài khoản đóng không?
- Có từ dành riêng như admin, support, root hoặc tên hệ thống không?
- Có áp dụng uniqueness toàn hệ thống hay theo tenant?

Không nên để username giống tên hiển thị rồi mặc định người dùng không thể thay đổi. Display name có thể trùng và không cần uniqueness; login username thường cần quy tắc rõ hơn.

### 3.2. Email

Email có thể thuận tiện cho login, nhưng địa chỉ email không phải định danh con người bất biến. Hộp thư có thể được chuyển giao, bị chiếm quyền, dùng chung, đổi tên hoặc bị nhà cung cấp thu hồi.

Cần phân biệt:
- Email người dùng khai báo.
- Email đã xác minh quyền kiểm soát.
- Email đang được dùng làm login identifier.
- Email dùng để nhận thông báo.
- Email recovery đã được xác minh theo policy.

Một email đã xác minh không nên tự động được coi là an toàn vĩnh viễn. Khi đổi email, xác minh địa chỉ mới và áp dụng thông báo/step-up phù hợp. Không tự động gộp hai tài khoản chỉ vì chúng cùng khai báo một email.

### 3.3. Số điện thoại

Nếu dùng số điện thoại làm identifier, lưu và xử lý theo định dạng quốc tế thống nhất, thường là E.164 khi phù hợp. Ví dụ số điện thoại Việt Nam cần được chuẩn hóa cùng mã quốc gia thay vì so sánh chuỗi nhập theo nhiều cách khác nhau.

Số điện thoại có thể được tái cấp cho người khác hoặc bị chuyển quyền kiểm soát. Vì vậy:
- Xác minh số mới trước khi dùng làm identifier hoặc recovery.
- Có quy trình thay đổi số với xác thực đủ mạnh.
- Không xem SMS OTP là bằng chứng danh tính pháp lý.
- Có thời gian chờ hoặc kiểm tra bổ sung khi thay đổi số có rủi ro cao.
- Xem xét khả năng số điện thoại dùng chung trong gia đình hoặc tổ chức.

### 3.4. Federated identifier

Trong OIDC, định danh subject cần được hiểu trong phạm vi issuer. Cặp **iss + sub** là định danh ổn định theo hợp đồng của OpenID Provider; không nên chỉ dùng sub mà bỏ issuer vì hai issuer khác nhau có thể phát hành cùng giá trị sub.

Email claim trong ID token không phải lúc nào cũng duy nhất hoặc bất biến. Nếu dùng email để gợi ý liên kết, cần kiểm tra email_verified theo hợp đồng và vẫn yêu cầu quy trình account linking an toàn. Không dùng email làm khóa duy nhất thay cho cặp issuer/subject.

## 4. Internal subject ID: khóa ổn định của principal

Một thiết kế phổ biến là cấp một internal subject ID ngẫu nhiên, không mang ý nghĩa nghiệp vụ và không thay đổi khi username/email/phone thay đổi.

Ví dụ mô hình:

~~~text
Principal
  subject_id: 8b3d... (opaque stable ID)
  status: active

LoginIdentifiers
  - type: username
    value: minh.nguyen
    verified: not_applicable
  - type: email
    value: minh@example.test
    verified: true
  - type: phone
    value: +84901234567
    verified: true
~~~

Đây là mô hình khái niệm. Trong hệ thống thực tế, identifier có thể được lưu trong bảng riêng để hỗ trợ nhiều giá trị, trạng thái, lịch sử, uniqueness và truy vấn.

Lợi ích của internal subject ID:

- Quan hệ dữ liệu không bị phá vỡ khi người dùng đổi email hoặc username.
- Audit log có thể tham chiếu principal ổn định.
- Có thể liên kết nhiều login identifier với một tài khoản.
- Dễ quản lý account merge/split có kiểm soát.
- Tránh lộ email hoặc số điện thoại trong khóa chính của nhiều bảng.
- Tách danh tính nội bộ khỏi các định danh bên ngoài.

Không dùng số thứ tự dễ đoán làm cơ chế bảo vệ. Opaque ID giảm khả năng đoán và rò rỉ thông tin, nhưng authorization vẫn phải kiểm tra quyền trên từng object.

## 5. Uniqueness và namespace

Một identifier cần có quy tắc xác định phạm vi duy nhất. “Email phải duy nhất” có thể có nghĩa duy nhất toàn hệ thống, duy nhất trong một tenant hoặc duy nhất trong một loại tài khoản.

Ví dụ:

| Mô hình | Quy tắc | Trường hợp sử dụng |
| --- | --- | --- |
| Global uniqueness | Một identifier chỉ thuộc một tài khoản trên toàn hệ thống | Dịch vụ consumer dùng chung một identity store |
| Tenant-scoped uniqueness | Identifier chỉ cần duy nhất trong tenant | SaaS đa tenant, mỗi tổ chức quản lý user riêng |
| Issuer-scoped uniqueness | Identifier duy nhất trong issuer | Federated identity |
| Type-scoped uniqueness | Username và email có namespace riêng | Hệ thống cho phép cùng chuỗi xuất hiện ở loại identifier khác nhau |

### 5.1. Tenant-scoped identifier

Trong hệ thống đa tenant, cùng một email có thể hợp lệ ở hai tổ chức khác nhau. Ví dụ, một người có tài khoản nhân viên ở công ty A và tài khoản khách hàng ở công ty B. Nếu hệ thống cần tách hai principal, uniqueness có thể được định nghĩa theo tenant.

Tuy nhiên, tenant ID phải đến từ context đã được xác thực và tin cậy. Không cho client gửi tenant tùy ý rồi tra cứu identifier trong tenant đó mà không kiểm tra quyền. Cần chống tenant confusion và kiểm tra issuer/audience/organization binding.

### 5.2. Race condition khi đăng ký

Kiểm tra identifier chưa tồn tại rồi mới insert là chưa đủ nếu hai request đồng thời cùng đăng ký một giá trị. Cả hai có thể đọc “chưa tồn tại” trước khi một request ghi dữ liệu.

Dùng unique constraint hoặc thao tác transaction nguyên tử tại database để bảo đảm uniqueness. Ứng dụng cần xử lý conflict rõ ràng, không dựa vào kiểm tra ở frontend.

### 5.3. Reserved và prohibited identifiers

Có thể cần chặn tên gây nhầm lẫn hoặc mạo danh như support, security, administrator, tên thương hiệu hoặc tên hệ thống. Quy tắc phải rõ ràng và có quy trình ngoại lệ cho tài khoản quản trị được cấp chính thức.

Không dùng blacklist tùy tiện khiến người dùng hợp lệ không thể chọn tên của mình. Hãy phân biệt tên gây nhầm lẫn về quyền sở hữu, tên hệ thống và từ ngữ thông thường.

## 6. Chuẩn hóa identifier trước khi tra cứu

Nếu lúc đăng ký và lúc đăng nhập dùng quy tắc chuẩn hóa khác nhau, người dùng có thể không tìm thấy tài khoản hoặc hai giá trị khác nhau có thể bị coi là một.

Quy trình chuẩn hóa nên được định nghĩa theo từng loại identifier, không dùng một hàm chung cho tất cả.

### 6.1. Email normalization

Có thể trim khoảng trắng ngoài địa chỉ và chuẩn hóa domain theo quy tắc hostname/IDN phù hợp. Nhưng cần thận trọng với phần local-part trước dấu @:

- Quy tắc chữ hoa/chữ thường của local-part phụ thuộc hệ thống nhận thư; không tự ý lowercase mọi email rồi giả định tất cả nhà cung cấp xử lý giống nhau.
- Dấu chấm hoặc phần cộng thêm trong một số nhà cung cấp không phải quy tắc chung của email.
- Không tự loại bỏ dấu +tag hoặc dấu chấm để gộp địa chỉ nếu không có hợp đồng với nhà cung cấp.
- Không dùng một phép biến đổi có thể khiến hai mailbox khác nhau bị nhập thành một account.

Nếu sản phẩm quyết định so sánh email không phân biệt hoa/thường, phải định nghĩa rõ, áp dụng nhất quán và xử lý collision trước khi triển khai. Giữ giá trị người dùng cung cấp để hiển thị hoặc audit khi cần, đồng thời lưu canonical lookup value riêng.

### 6.2. Phone normalization

Số điện thoại cần được parse theo quốc gia/region context và chuyển về định dạng chuẩn trước khi tra cứu. Không chỉ xóa mọi ký tự không phải số rồi nối chuỗi, vì số nội hạt, mã quốc gia và số máy lẻ có quy tắc riêng.

Ví dụ khái niệm:

~~~text
Input: 0901 234 567
Region: VN
Canonical form: +84901234567
~~~

Ứng dụng cần xác định cách xử lý số nội hạt, mã quốc gia bị thiếu, extension, số không hợp lệ và số chưa được xác minh. Không tự đoán region nếu người dùng có thể nhập số quốc tế.

### 6.3. Unicode và username

Username Unicode có thể chứa ký tự có nhiều cách biểu diễn tương đương hoặc ký tự nhìn giống nhau. Ví dụ chữ có dấu có thể được biểu diễn bằng ký tự dựng sẵn hoặc ký tự cơ sở cộng dấu kết hợp. Một số ký tự Latin, Cyrillic và Greek có hình dạng gần giống nhưng code point khác nhau.

Các nguyên tắc:
- Xác định bộ ký tự được phép và quy tắc normalization.
- Cân nhắc NFC cho canonical equivalence nếu phù hợp với sản phẩm.
- Không áp dụng NFKC một cách mù quáng nếu có thể làm thay đổi ý nghĩa hoặc gộp ký tự ngoài mong muốn.
- Phát hiện hoặc hạn chế confusable trong identifier nhạy cảm.
- Hiển thị identifier theo cách giúp người dùng nhận ra ký tự bất thường.
- Dùng cùng quy tắc ở registration, login, change identifier và recovery.
- Không tự động chuyển mọi ký tự Unicode thành ASCII nếu sản phẩm hỗ trợ ngôn ngữ quốc tế.

Normalization phải được thiết kế như một phần của hợp đồng dữ liệu. Thay đổi thuật toán normalization sau khi đã có nhiều tài khoản có thể tạo collision; cần kiểm tra trước và có migration plan.

## 7. Lookup flow trong đăng nhập

Một login flow điển hình có thể:

1. Nhận identifier từ form hoặc client.
2. Kiểm tra kích thước, encoding và định dạng đầu vào.
3. Xác định tenant/issuer context từ nguồn tin cậy.
4. Chuẩn hóa identifier theo loại đã chọn.
5. Tra cứu principal và trạng thái identifier.
6. Nếu tài khoản có nhiều phương thức, chọn flow xác thực phù hợp.
7. Xác minh credential.
8. Áp dụng MFA, risk policy và authentication context.
9. Tạo session/token sau khi xác thực thành công.
10. Ghi audit an toàn.

~~~mermaid
flowchart TD
    A[Người dùng nhập identifier] --> B[Validate kích thước và định dạng]
    B --> C[Resolve tenant / issuer context]
    C --> D[Normalize theo identifier type]
    D --> E[Lookup principal]
    E --> F{Tài khoản và identifier hợp lệ?}
    F -- Không --> G[Phản hồi chung, không tiết lộ trạng thái]
    F -- Có --> H[Chọn credential / authentication flow]
    H --> I[Verify credential]
    I --> J{Xác thực đạt?}
    J -- Không --> K[Rate limit, audit và phản hồi an toàn]
    J -- Có --> L[MFA / risk / step-up nếu policy yêu cầu]
    L --> M[Tạo session hoặc token]
~~~

Lookup chỉ xác định principal tiềm năng. Không tạo session hoặc tiết lộ thông tin tài khoản trước khi credential được xác minh. Nếu identifier không tồn tại, bị khóa hoặc credential sai, phản hồi bên ngoài nên tránh cung cấp thông tin giúp dò tìm tài khoản.

### 7.1. Nhiều identifier trên một form

Nếu form chấp nhận username hoặc email, backend cần xác định loại identifier một cách rõ ràng và không tạo hành vi nhập nhằng. Có thể dùng trường duy nhất “username hoặc email” với parser có quy tắc; hoặc yêu cầu người dùng chọn loại identifier.

Không thử hàng loạt namespace khác nhau mà không giới hạn, khiến một chuỗi có thể trỏ tới tài khoản khác tùy tenant hoặc loại identifier. Nếu một giá trị có thể là username của người này và email của người khác, cần quy tắc ưu tiên hoặc thiết kế namespace để loại bỏ ambiguity.

### 7.2. Tránh account enumeration

Account enumeration là việc attacker xác định tài khoản có tồn tại hay không thông qua phản hồi đăng nhập, đăng ký, recovery hoặc thay đổi identifier.

Tránh:
- Thông báo “email không tồn tại” trong khi trường hợp password sai báo khác.
- Thời gian phản hồi khác biệt quá rõ giữa tài khoản tồn tại và không tồn tại.
- API trả status code, error code hoặc metadata tiết lộ trạng thái tài khoản.
- Form recovery xác nhận trực tiếp một email có tài khoản.
- Gửi thông báo khác nhau có thể bị quan sát từ bên ngoài mà không có biện pháp giảm rủi ro.

Có thể dùng phản hồi chung như “Nếu thông tin phù hợp với tài khoản, chúng tôi sẽ gửi hướng dẫn tiếp theo”. Bên trong hệ thống vẫn ghi reason code cụ thể để hỗ trợ vận hành. Rate limit và giám sát cần áp dụng theo IP, device/risk context và identifier đã băm hoặc bảo vệ phù hợp.

Không làm chậm mọi request một cách cực đoan để che timing; cần cân bằng UX, chống automation và hành vi nhất quán.

## 8. Identifier lifecycle

Identifier có vòng đời riêng, khác với internal subject và credential.

Một trạng thái có thể gồm:

- **Pending:** vừa được khai báo nhưng chưa xác minh.
- **Verified:** đã hoàn tất quy trình xác minh phù hợp.
- **Active:** được phép dùng cho login hoặc liên hệ theo policy.
- **Suspended:** tạm ngừng sử dụng do rủi ro hoặc tranh chấp.
- **Retired:** không còn được dùng cho mục đích hiện tại.
- **Revoked:** bị thu hồi do sai, bị chiếm quyền hoặc lý do quản trị.

Không phải mọi hệ thống cần tất cả trạng thái, nhưng cần phân biệt giá trị chưa xác minh với giá trị được phép dùng làm recovery hoặc login.

### 8.1. Đổi identifier

Khi đổi email, phone hoặc username:

1. Xác thực lại người đang yêu cầu theo mức rủi ro.
2. Kiểm tra identifier mới chưa được cấp cho principal khác trong namespace tương ứng.
3. Xác minh quyền kiểm soát identifier mới nếu nó là email/phone.
4. Thông báo tới kênh cũ theo policy.
5. Cập nhật identifier mới trong transaction an toàn.
6. Thu hồi hoặc đánh dấu retired identifier cũ.
7. Cập nhật recovery, federation mapping và các hệ thống phụ thuộc.
8. Ghi audit và theo dõi dấu hiệu takeover.

Không chuyển identifier sang trạng thái active chỉ vì người dùng đã nhập nó. Nếu bước xác minh thất bại, giữ trạng thái pending hoặc hủy yêu cầu.

### 8.2. Reuse và cooling-off period

Một email hoặc số điện thoại cũ có thể được tái sử dụng bởi người khác. Nếu hệ thống giữ identifier cũ mãi mãi, người dùng mới có thể không đăng ký được; nếu tái cấp ngay, người mới có thể nhận email recovery của tài khoản cũ.

Policy có thể dùng thời gian chờ trước khi identifier được cấp lại, thông báo tới kênh cũ và quy trình tách identifier khỏi account đã đóng. Độ dài thời gian phụ thuộc loại identifier, luật và nguy cơ chiếm quyền. Không dùng một khoảng chờ cố định cho mọi loại dữ liệu.

Với username, việc tái cấp có thể khiến người khác nhận thông báo hoặc liên kết cũ. Cân nhắc giữ username cũ ở trạng thái reserved hoặc không tái cấp nếu có nguy cơ nhầm lẫn.

### 8.3. Tài khoản đóng hoặc bị xóa

Xóa tài khoản không nhất thiết đồng nghĩa mọi identifier được giải phóng ngay. Cần xem:
- Có nghĩa vụ lưu dữ liệu hoặc audit không?
- Identifier có thể được dùng để khôi phục tài khoản đã xóa không?
- Có nguy cơ người mới nhận lại kênh liên hệ cũ?
- Có cần giữ tombstone chống tái tạo hoặc nhầm tài khoản?
- Việc xóa có ảnh hưởng tới liên kết federated và session đang hoạt động không?

Giữ dữ liệu tối thiểu cần thiết theo retention policy, không giữ identifier nhạy cảm vô thời hạn chỉ để phòng ngừa chung chung.

## 9. Identifier trong account recovery

Recovery thường bắt đầu bằng email, số điện thoại hoặc username. Nhưng biết identifier không chứng minh người yêu cầu là chủ tài khoản.

Một recovery flow cần:
- Không tiết lộ tài khoản có tồn tại.
- Gửi thử thách tới kênh đã xác minh hoặc yêu cầu bằng chứng phù hợp.
- Đánh giá độ mới và mức tin cậy của kênh.
- Yêu cầu credential/MFA dự phòng khi rủi ro cao.
- Thông báo tới các kênh hiện có khi thay đổi identifier/recovery.
- Thu hồi session/token khi có dấu hiệu takeover.
- Có quy trình review cho người dùng mất quyền truy cập identifier cũ.

Không dùng email hoặc số điện thoại vừa được thêm trong cùng một session đáng ngờ làm bằng chứng duy nhất để recovery ngay lập tức. Attacker chiếm session có thể thêm kênh mới rồi dùng nó để chiếm tài khoản vĩnh viễn.

### 9.1. Identifier không phải recovery secret

Không dùng câu hỏi như “email của bạn là gì?” hoặc “số điện thoại của bạn là gì?” như bằng chứng xác thực. Đây là dữ liệu nhận diện/tra cứu, không phải bí mật đủ mạnh. Security questions dựa trên thông tin cá nhân dễ đoán hoặc tìm thấy cũng không nên là yếu tố recovery duy nhất.

### 9.2. Thông báo và bảo vệ sau recovery

Sau khi đổi identifier hoặc hoàn tất recovery, có thể cần:
- Thông báo tới kênh cũ và mới.
- Hủy session cũ hoặc session có rủi ro.
- Thu hồi refresh token và credential bị nghi compromise.
- Đặt hạn chế tạm thời cho thay đổi tiếp theo hoặc giao dịch nhạy cảm.
- Cho phép người dùng báo cáo thay đổi không do họ thực hiện.
- Ghi audit và cung cấp quy trình hỗ trợ.

## 10. Account linking và federated login

Account linking kết nối tài khoản nội bộ với một identity từ IdP hoặc một phương thức đăng nhập khác. Không nên tự động liên kết chỉ vì hai tài khoản có cùng email hiển thị.

Với OIDC:
- Xác minh chữ ký ID token, issuer, audience, expiry và nonce.
- Dùng cặp issuer + subject làm khóa federated identity theo profile.
- Chỉ dùng email claim nếu policy cho phép và kiểm tra trạng thái verified theo issuer.
- Yêu cầu người dùng đã đăng nhập vào tài khoản hiện tại xác nhận liên kết.
- Nếu liên kết tài khoản khác, yêu cầu xác thực độc lập cho cả hai phía.
- Chống replay và CSRF trong quá trình linking.
- Ghi audit, cho phép xem và gỡ liên kết theo policy.

Ví dụ: tài khoản nội bộ đã có email minh@example.test. Người dùng đăng nhập qua một IdP trả về cùng email. Nếu hệ thống tự động gộp, attacker có thể khai thác IdP yếu hoặc email chưa xác minh để chiếm tài khoản. Cần một flow linking được xác thực rõ ràng và kiểm tra issuer/subject.

### 10.1. Một identifier có thể xuất hiện ở nhiều issuer

Hai IdP có thể phát hành cùng email hoặc cùng giá trị sub. Không bỏ issuer khỏi định danh liên kết. Cặp issuer/subject giúp phân biệt các không gian định danh.

Nếu IdP thay đổi subject hoặc chuyển từ pairwise subject sang public subject, cần migration theo hợp đồng với nhà cung cấp. Không suy luận rằng email giống nhau nghĩa là federated identity vẫn là cùng principal.

## 11. Migration identifier

Khi thay đổi login identifier scheme, ví dụ chuyển từ username sang email hoặc thêm phone login, cần tránh khóa nhầm tài khoản và tạo collision.

Quy trình migration có thể:

1. Xác định namespace cũ và mới.
2. Phân tích collision theo quy tắc normalization mới.
3. Xác định nguồn xác minh cho identifier mới.
4. Giữ internal subject ID ổn định.
5. Thêm identifier mới ở trạng thái pending.
6. Xác minh và kích hoạt theo từng principal.
7. Duy trì khả năng đăng nhập bằng identifier cũ trong giai đoạn chuyển đổi nếu policy cho phép.
8. Thông báo và hỗ trợ người dùng có collision.
9. Thu hồi identifier cũ sau khi hoàn tất.
10. Audit các thay đổi và theo dõi login failure.

Không đổi hàng loạt email/username bằng một phép lowercase hoặc Unicode normalization mà không kiểm tra va chạm trước. Migration cần backup, rollback plan và test trên dữ liệu đã khử nhạy cảm.

## 12. Lưu trữ và tra cứu an toàn

Một mô hình dữ liệu có thể tách principal khỏi các identifier:

~~~sql
CREATE TABLE principal (
  subject_id UUID PRIMARY KEY,
  status VARCHAR(20) NOT NULL
);

CREATE TABLE login_identifier (
  identifier_id UUID PRIMARY KEY,
  subject_id UUID NOT NULL REFERENCES principal(subject_id),
  identifier_type VARCHAR(20) NOT NULL,
  namespace_id VARCHAR(100) NOT NULL,
  canonical_value VARCHAR(320) NOT NULL,
  display_value VARCHAR(320),
  status VARCHAR(20) NOT NULL,
  verified_at TIMESTAMP NULL,
  created_at TIMESTAMP NOT NULL,
  UNIQUE (identifier_type, namespace_id, canonical_value)
);
~~~

Đây là schema minh họa; kiểu dữ liệu, độ dài, index, collation, mã hóa và constraint cần điều chỉnh theo database và quy tắc identifier thực tế.

Lưu ý:
- Unique constraint phải áp dụng trên canonical value theo namespace.
- Không lưu password trong bảng identifier; password cần kho/format lưu credential riêng với password hashing phù hợp.
- Hạn chế quyền đọc identifier, đặc biệt email/phone.
- Dùng encryption hoặc tokenization khi cần bảo vệ dữ liệu ở trạng thái lưu.
- Index tra cứu không nên làm lộ dữ liệu trong dashboard hoặc query log.
- Audit thay đổi identifier nhưng không ghi credential hoặc token.
- Cân nhắc keyed hash/HMAC lookup index nếu mô hình threat yêu cầu; hash thường của email/phone có thể bị dò bằng dictionary.
- Dùng transaction để cập nhật identifier và trạng thái verified nhất quán.

Không dùng MD5/SHA-1 hoặc hash nhanh thông thường để “bảo vệ” email/phone. Không gian giá trị của email/phone có thể đoán được; hash không khóa vẫn có thể bị dò. Nếu dùng keyed index, khóa HMAC phải được bảo vệ và có kế hoạch rotation/migration.

## 13. Rate limiting và chống dò identifier

Login endpoint có thể bị lạm dụng để thử hàng loạt email, username hoặc phone nhằm phát hiện tài khoản hoặc chuẩn bị credential stuffing.

Các kiểm soát có thể gồm:
- Rate limit theo IP, account candidate, device/session và network reputation.
- Theo dõi phân tán để attacker không né bằng cách đổi IP liên tục.
- Giới hạn số lần thử password/OTP riêng với lookup.
- Progressive delay hoặc challenge bổ sung theo rủi ro.
- Phản hồi lỗi chung, không tiết lộ account state.
- Phát hiện password spraying và credential stuffing.
- Cảnh báo khi một identifier bị thử từ nhiều nguồn hoặc nhiều identifier bị thử từ một nguồn.
- Không khóa tài khoản vĩnh viễn chỉ dựa vào số lần thử từ bên ngoài, tránh denial of service.

Khi áp dụng rate limit theo identifier, có thể dùng representation bảo vệ hoặc keyed hash trong telemetry thay vì log email/phone thô. Cần bảo đảm key và dữ liệu log có quyền truy cập hạn chế.

### 13.1. Không biến identifier lookup thành oracle

Một endpoint kiểm tra “email đã được đăng ký chưa?” có thể bị dùng để thu thập danh sách người dùng. Nếu sản phẩm cần kiểm tra availability khi đăng ký, hãy giới hạn tốc độ, tránh trả dữ liệu profile và cân nhắc phản hồi có kiểm soát.

Đối với hệ thống doanh nghiệp, việc tiết lộ một mã nhân viên có tài khoản hay không cũng có thể là dữ liệu nhạy cảm. Không mặc định identifier là thông tin công khai.

## 14. Các lỗi triển khai thường gặp

| Lỗi | Hậu quả | Cách xử lý |
| --- | --- | --- |
| Dùng email làm primary key vĩnh viễn | Đổi email làm đứt quan hệ dữ liệu | Dùng internal subject ID ổn định |
| Coi email/phone là credential | Người biết identifier có thể bị nhầm là đã xác thực | Xác minh credential riêng |
| Auto-link theo email | Có thể chiếm tài khoản qua email chưa xác minh hoặc IdP yếu | Flow linking xác thực hai phía và issuer/subject |
| Lowercase mọi email không theo policy | Có thể gộp mailbox khác nhau | Định nghĩa canonicalization và xử lý collision |
| Bỏ +tag/dấu chấm của email | Gộp địa chỉ ngoài quy tắc nhà cung cấp | Không áp dụng provider-specific rule toàn cục |
| Dùng chuỗi Unicode nhìn giống nhau | Có thể mạo danh username | Normalization, confusable detection và hiển thị rõ |
| Không có namespace/tenant | Collision hoặc truy cập nhầm principal | Unique constraint theo scope |
| Check-then-insert không atomic | Hai tài khoản cùng nhận identifier | Database unique constraint/transaction |
| Báo “tài khoản không tồn tại” | Account enumeration | Response chung và rate limit |
| Coi số điện thoại đã xác minh là vĩnh viễn | Người nhận số mới có thể recovery tài khoản cũ | Lifecycle, revalidation và notification |
| Dùng identifier làm recovery secret | Attacker chỉ cần biết dữ liệu công khai | Recovery proof riêng và step-up |
| Tái cấp identifier ngay sau xóa | Người mới nhận liên kết hoặc recovery cũ | Cooling-off/tombstone theo policy |
| Dùng sub không kèm issuer | Trộn subject từ nhiều IdP | Khóa bằng issuer + subject |
| Log identifier thô ở mọi nơi | Rò rỉ dữ liệu cá nhân và danh sách account | Mask, access control và retention |

## 15. Ví dụ: thiết kế đăng nhập cho dịch vụ đa tenant

Một dịch vụ SaaS phục vụ nhiều công ty. Người dùng có thể đăng nhập bằng email công việc nhưng cùng một email có thể được mời vào nhiều tenant với vai trò khác nhau.

Một thiết kế có thể:

1. Người dùng nhập email.
2. Hệ thống xác minh định dạng và chuẩn hóa theo policy email.
3. Hệ thống xác định tenant bằng invitation, organization selection hoặc domain discovery đã được kiểm soát; không tin tenant ID tùy ý từ client.
4. Hệ thống tìm principal theo namespace/tenant và identifier.
5. Nếu chưa xác định được tenant, hiển thị flow chọn tổ chức mà không tiết lộ danh sách tenant không được phép.
6. Người dùng xác thực bằng passkey/password hoặc IdP được tenant cấu hình.
7. Backend kiểm tra principal membership, tenant status và quyền.
8. Session gắn với subject ID và tenant context đã xác minh.
9. Nếu người dùng đổi email, cập nhật login identifier nhưng giữ subject và membership.
10. Nếu tenant thu hồi quyền, vô hiệu membership/session theo policy.

Trong kiến trúc này, email chỉ là đầu vào tra cứu. Quyền truy cập tenant đến từ membership đã được xác minh và authorization phía server.

~~~mermaid
sequenceDiagram
    participant U as Người dùng
    participant W as Login UI
    participant I as Identity Service
    participant T as Tenant Directory
    participant A as Authenticator
    U->>W: Nhập email
    W->>I: Login identifier
    I->>I: Normalize theo policy
    I->>T: Resolve tenant context đáng tin
    T-->>I: Namespace và membership candidates
    I->>A: Bắt đầu xác thực principal phù hợp
    A-->>I: Credential verification result
    I->>I: Kiểm tra trạng thái và policy
    I-->>W: Session gắn subject + tenant
~~~

## 16. Checklist review login identifier

| Câu hỏi | Dấu hiệu thiết kế tốt |
| --- | --- |
| Identifier và credential có tách biệt? | Identifier chỉ tra cứu; credential mới xác thực |
| Có internal subject ID ổn định? | Thay email/username không đổi khóa principal |
| Loại identifier có phù hợp? | Có lý do cho username, email, phone hoặc federated subject |
| Uniqueness có namespace rõ? | Global, tenant hoặc issuer scope được định nghĩa |
| Normalization có đặc tả? | Cùng quy tắc ở register/login/change/recovery |
| Email được xử lý thận trọng? | Không tự gộp +tag, dấu chấm hoặc local-part |
| Phone được chuẩn hóa? | Region và E.164 được xử lý rõ |
| Unicode có kiểm soát? | Normalization và confusable policy được test |
| Identifier có trạng thái? | Pending, verified, active, suspended, retired |
| Thay đổi identifier có an toàn? | Reauth, verify new value, notify old channel, audit |
| Reuse có policy? | Cooling-off/reservation và account deletion được xét |
| Recovery không dựa vào identifier đơn thuần? | Có proof độc lập và risk controls |
| Account linking có xác minh? | Issuer + subject và linking flow được bảo vệ |
| Lookup chống enumeration? | Error và timing được kiểm soát; rate limit |
| Database bảo đảm uniqueness? | Unique constraint và transaction nguyên tử |
| Log có bảo vệ? | Mask hoặc keyed representation, retention giới hạn |
| Tenant context đáng tin? | Membership và scope được kiểm tra ở backend |
| Có migration plan? | Collision analysis, rollback và user support |

### Tình huống tự kiểm tra

**Tình huống 1:** Người dùng đổi email đăng nhập. Có nên thay email làm primary key của mọi bảng?

**Trả lời:** Không. Dùng internal subject ID ổn định; email chỉ là một identifier có thể thay đổi.

**Tình huống 2:** Hai người có cùng email được trả về từ hai issuer khác nhau. Có phải cùng một federated identity không?

**Trả lời:** Không thể kết luận chỉ từ email. Dùng cặp issuer + subject và quy trình account linking được xác thực.

**Tình huống 3:** Một người nhập email vào recovery form. Hệ thống trả “email không tồn tại”. Rủi ro là gì?

**Trả lời:** Attacker có thể dùng endpoint để thu thập danh sách tài khoản. Dùng phản hồi chung, rate limit và audit nội bộ.

**Tình huống 4:** Một nhà cung cấp email bỏ qua dấu cộng trong địa chỉ, nên hệ thống tự xóa mọi phần sau dấu cộng trước khi lookup. Có an toàn không?

**Trả lời:** Không. Đây không phải quy tắc chung của mọi mailbox. Chỉ áp dụng quy tắc đặc thù khi có hợp đồng rõ với nhà cung cấp; không gộp email tùy tiện.

**Tình huống 5:** Người dùng xác minh số điện thoại hai năm trước. Có thể dùng số đó làm recovery duy nhất hôm nay không?

**Trả lời:** Không mặc nhiên. Số có thể đã được tái cấp hoặc bị chiếm quyền. Cần đánh giá freshness, xác minh lại và kết hợp bằng chứng theo policy.

**Tình huống 6:** Một username Unicode có ký tự nhìn giống chữ Latin nhưng thực tế thuộc bảng chữ cái khác. Hệ thống nên xử lý thế nào?

**Trả lời:** Cần chính sách Unicode/confusable rõ ràng, cảnh báo hoặc hạn chế ký tự gây nhầm lẫn, và giữ quy tắc nhất quán giữa đăng ký và đăng nhập.

## 17. Ghi nhớ

**Login identifier giúp hệ thống tìm principal; nó không chứng minh người đang nhập có quyền kiểm soát tài khoản.** Email, số điện thoại, username và federated subject có đặc tính và vòng đời khác nhau. Dùng internal subject ID ổn định để liên kết dữ liệu, xác định namespace/tenant rõ ràng và tách trạng thái khai báo khỏi trạng thái đã xác minh.

Một thiết kế an toàn cần normalization nhất quán, xử lý Unicode và collision có chủ đích, uniqueness ở database, lifecycle khi đổi/reuse identifier, recovery và account linking được bảo vệ, cùng phản hồi chống enumeration. Identifier chỉ nên được dùng trong phạm vi mục đích đã xác định; credential và authorization vẫn phải được kiểm tra độc lập trong mọi luồng truy cập.
