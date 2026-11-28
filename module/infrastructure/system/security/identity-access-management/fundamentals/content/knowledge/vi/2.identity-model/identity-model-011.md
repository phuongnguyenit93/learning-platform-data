# Identity uniqueness

## Mục tiêu bài học

Hai nhà cung cấp danh tính cùng có người dùng mang mã `u-42`. Hai tenant cùng có tài khoản đăng nhập tên `admin`. Một địa chỉ email được chuyển từ nhân viên đã nghỉ việc sang người mới. Trong cả ba tình huống, so sánh một chuỗi định danh đơn lẻ có thể làm hệ thống nhận nhầm chủ thể.

**Identity uniqueness**, hay tính duy nhất của danh tính, là yêu cầu giúp hệ thống phân biệt chính xác các chủ thể trong phạm vi định danh đã xác định. Đối với IAM, yêu cầu này phải được xem xét cùng với nguồn phát hành, vòng đời, ánh xạ tài khoản và cách tham chiếu quyền.

Sau bài học này, bạn có thể:

- Xác định phạm vi mà một định danh được bảo đảm duy nhất.
- Phân biệt định danh nội bộ, định danh bên ngoài và bí danh đăng nhập.
- Chọn khóa phù hợp cho ứng dụng nhiều tenant và liên kết danh tính.
- Tránh cấp nhầm quyền do tái sử dụng email, mất phạm vi hoặc hợp nhất tài khoản sai.
- Hiểu vai trò của ràng buộc dữ liệu và giao dịch khi nhiều yêu cầu cấp phát chạy đồng thời.

## 1. Duy nhất phải đi kèm phạm vi

Một identifier là giá trị dùng để chỉ đến một chủ thể hoặc bản ghi. Nó chỉ có ý nghĩa duy nhất khi biết **namespace**, tức không gian định danh mà trong đó giá trị được cấp và diễn giải.

```text
identifier = "u-42"
```

Chỉ với giá trị này, chưa biết chủ thể thuộc hệ thống nào. Khi bổ sung phạm vi:

```text
(namespace = Directory A, identifier = u-42)
(namespace = Directory B, identifier = u-42)
```

ta có thể đang nói về hai chủ thể khác nhau. Không có xung đột nếu mỗi directory chỉ cam kết duy nhất trong phạm vi của mình. Xung đột xuất hiện khi ứng dụng bỏ namespace và gộp cả hai thành cùng một người dùng.

Một phát biểu đầy đủ cần trả lời:

1. Giá trị được cấp bởi nguồn nào?
2. Duy nhất trong một ứng dụng, tenant, tổ chức hay nhiều hệ thống?
3. Duy nhất tại một thời điểm hay không được tái cấp trong suốt vòng đời?
4. Quy tắc so sánh và chuẩn hóa giá trị là gì?

Ví dụ, “username duy nhất” còn thiếu thông tin. “Username sau chuẩn hóa theo quy tắc của tenant, duy nhất giữa các tài khoản trong tenant đó” mới chỉ ra được một yêu cầu có thể triển khai và kiểm tra.

## 2. Duy nhất không đồng nghĩa một người chỉ có một tài khoản

Một người có thể có tài khoản cá nhân, tài khoản nhân viên và tài khoản quản trị tách biệt. Một workload có thể có danh tính khác nhau cho development và production. Việc có nhiều danh tính như vậy không tự vi phạm tính duy nhất.

Điều cần tránh là **hai chủ thể khác nhau bị diễn giải thành cùng một danh tính** hoặc **một tham chiếu không chỉ rõ đang nói đến chủ thể nào**.

Ngược lại, hai tài khoản khác nhau có thể thực sự thuộc cùng một người ngoài đời. UUID khác nhau không chứng minh đó là hai con người khác nhau. Muốn bảo đảm mỗi người chỉ có một hồ sơ trong một quy trình nghiệp vụ, cần thêm cơ chế đối chiếu và thẩm tra phù hợp; không thể chỉ dựa vào khóa chính của bảng tài khoản.

| Yêu cầu | Ý nghĩa | Cơ chế thường liên quan |
|---|---|---|
| Định danh bản ghi duy nhất | Hai bản ghi không dùng cùng khóa trong phạm vi quy định | Primary key, unique constraint |
| Liên kết danh tính ngoài duy nhất | Một danh tính từ nguồn ngoài không bị gắn nhầm sang nhiều principal trong mô hình đã chọn | Khóa có namespace, ràng buộc ánh xạ |
| Một hồ sơ cho mỗi người theo nghiệp vụ | Phát hiện và xử lý hồ sơ có thể trùng người | Đối chiếu dữ kiện, thẩm tra, xử lý xung đột |
| Tách tài khoản đặc quyền | Một người có nhiều tài khoản cho mục đích khác nhau | Chính sách tài khoản, quản lý đặc quyền, kiểm toán |

**Principal** là biểu diễn chủ thể mà hệ thống dùng để quản lý trạng thái và đánh giá quyền. Chủ thể có thể là người dùng hoặc workload. Mô hình cần chỉ rõ mỗi principal đại diện cho điều gì, thay vì mặc định mọi principal đều tương ứng với một người duy nhất ngoài đời.

## 3. Những thuộc tính dễ bị nhầm với tính duy nhất

| Thuộc tính | Câu hỏi | Quan hệ với tính duy nhất |
|---|---|---|
| Stability — ổn định | Giá trị có giữ nguyên khi hồ sơ thay đổi không? | Một email có thể duy nhất hôm nay nhưng thay đổi ngày mai |
| Non-reassignment — không tái cấp | Giá trị cũ có được cấp lại cho chủ thể khác không? | Duy nhất tại một thời điểm chưa bảo vệ tham chiếu lịch sử |
| Unpredictability — khó đoán | Bên ngoài có dễ đoán giá trị tiếp theo không? | ID tuần tự vẫn có thể duy nhất; UUID khó đoán vẫn cần kiểm tra quyền |
| Secrecy — bí mật | Giá trị có được dùng như bằng chứng bí mật không? | Mã tài khoản thường là định danh, không phải credential |
| Readability — dễ đọc | Con người có dễ ghi nhớ và nhập không? | Tên dễ nhớ vẫn có thể trùng hoặc thay đổi |

Một ID ngẫu nhiên có không gian đủ lớn giúp giảm khả năng va chạm, nhưng hệ thống vẫn cần bảo đảm không lưu hai bản ghi cùng khóa. Mặt khác, chọn ID khó đoán không thay thế kiểm soát truy cập trên đối tượng.

Không nên mã hóa vai trò hoặc phòng ban vào khóa danh tính lâu dài. Khi người dùng chuyển bộ phận, thuộc tính và quyền cần thay đổi, còn tham chiếu đến chủ thể vẫn cần ổn định.

## 4. Tách định danh ổn định khỏi bí danh đăng nhập

Một mô hình thường có ba lớp:

```text
Bí danh hoặc định danh đăng nhập
  -> Liên kết đã được kiểm chứng
  -> Principal nội bộ ổn định
  -> Membership, vai trò, quyền và dữ liệu sở hữu
```

### 4.1. Định danh nội bộ

`principal_id` có thể là một giá trị không mang ý nghĩa nghiệp vụ, được cấp một lần cho principal. Quyền, phiên, dữ liệu sở hữu và bản ghi kiểm toán tham chiếu đến giá trị này cùng phạm vi cần thiết.

Các đặc tính mong muốn gồm:

- Duy nhất trong mô hình lưu trữ và phạm vi sử dụng đã chọn.
- Không thay đổi khi người dùng đổi tên, email hoặc vai trò.
- Không được tái cấp cho một chủ thể khác.
- Có quy trình xử lý khi nhập dữ liệu, di chuyển hoặc hợp nhất hệ thống.

### 4.2. Bí danh đăng nhập

Email hoặc username có thể dùng để tìm tài khoản. Chúng cần quy tắc so sánh, chuẩn hóa, xác minh và quản lý vòng đời riêng.

Ví dụ, người dùng đổi email từ `lan.old@example.test` sang `lan.new@example.test` nhưng vẫn giữ `principal-801`. Quyền và lịch sử không cần chuyển sang một chủ thể mới chỉ vì địa chỉ liên hệ thay đổi.

Nếu một trường đăng nhập chấp nhận nhiều loại bí danh, phải tránh tình huống một chuỗi đồng thời ánh xạ đến hai tài khoản theo các quy tắc khác nhau. Có thể yêu cầu xác định loại định danh hoặc thiết kế namespace bí danh sao cho việc tra cứu không mơ hồ.

### 4.3. Định danh bên ngoài

Ứng dụng cần giữ nguồn phát hành đi cùng định danh chủ thể. Với OIDC, cặp `issuer` và `sub` đã được xác minh dùng để nhận diện chủ thể theo giao thức:

```text
(verified_issuer, verified_sub) -> principal_id

(Issuer A, u-42) -> principal-801
(Issuer B, u-42) -> principal-916
```

Không lấy `sub` từ payload chưa xác minh để tạo principal. Trước khi dùng khóa ánh xạ, bên nhận phải kiểm tra phản hồi hoặc token theo giao thức và cấu hình tin cậy, bao gồm ngữ cảnh bên nhận và hiệu lực cần thiết.

Các chuỗi issuer và subject phải được so sánh theo quy tắc của giao thức. Không tùy tiện chuyển chữ thường, bỏ dấu gạch chéo hoặc sửa URL để ghép hai nguồn thành một. Việc đổi issuer hoặc di chuyển IdP cần một quy trình ánh xạ có kiểm soát.

Một số cấu hình OIDC tạo subject khác nhau cho các ứng dụng hoặc nhóm ứng dụng khác nhau. Không dùng sự khác nhau đó để kết luận chắc chắn hai tài khoản thuộc hai người khác nhau. Với giao thức khác, cần chọn định danh có phạm vi và tính ổn định tương ứng thay vì áp dụng máy móc mô hình OIDC.

## 5. Tính duy nhất trong ứng dụng nhiều tenant

Tenant là một phạm vi tổ chức hoặc khách hàng trong ứng dụng. Có hai mô hình phổ biến, mỗi mô hình kéo theo cách đặt khóa khác nhau.

### Mô hình A: principal chung, membership theo tenant

Ứng dụng có một principal nội bộ duy nhất cho một chủ thể được liên kết, và principal đó có thể tham gia nhiều tenant:

```text
principal-801
  -> thành viên tenant-A, vai trò reader
  -> thành viên tenant-B, vai trò editor
```

`principal_id` duy nhất ở mức ứng dụng. Quan hệ thành viên được xác định bằng cặp `(tenant_id, principal_id)`. Vai trò và quyền vẫn phải gắn với phạm vi tenant hoặc tài nguyên thích hợp.

Việc chủ thể là quản trị viên tenant A không làm họ trở thành quản trị viên tenant B. Khóa principal chung giúp nhận diện chủ thể; nó không hợp nhất quyền giữa các tenant.

### Mô hình B: danh tính cục bộ theo tenant

Mỗi tenant quản lý không gian tài khoản riêng. Khi đó, mã tài khoản cục bộ có thể trùng:

```text
(tenant-A, user-42)
(tenant-B, user-42)
```

Khóa đầy đủ phải bao gồm tenant. API, cache, sự kiện, hàng đợi và log cần giữ phạm vi này. Chỉ dùng `user-42` làm khóa cache có thể khiến dữ liệu hoặc quyền của tenant này bị đọc cho tenant khác.

Không có một mô hình bắt buộc cho mọi sản phẩm. Điều cần thống nhất là phạm vi định danh trong dữ liệu, hợp đồng API, phiên và các quyết định truy cập.

### Khóa đúng vẫn cần kiểm tra quyền

Client có thể gửi một `tenantId` và `userId` tạo thành khóa hợp lệ nhưng vẫn không có quyền truy cập. Máy chủ phải xác nhận tenant đang hoạt động thuộc phạm vi mà principal được phép sử dụng, rồi kiểm tra hành động trên tài nguyên.

Tính duy nhất trả lời “đang nói đến chủ thể nào”; xác thực và phân quyền trả lời những câu hỏi khác.

## 6. Ví dụ ràng buộc dữ liệu

Lược đồ SQL dưới đây minh họa mô hình principal chung với liên kết OIDC. Đây là ví dụ thiết kế dữ liệu, không phải yêu cầu triển khai cho mọi nền tảng.

```sql
CREATE TABLE principal (
    principal_id UUID PRIMARY KEY,
    principal_type TEXT NOT NULL,
    status TEXT NOT NULL
);

CREATE TABLE external_identity (
    issuer TEXT NOT NULL,
    subject TEXT NOT NULL,
    principal_id UUID NOT NULL REFERENCES principal(principal_id),
    status TEXT NOT NULL,
    PRIMARY KEY (issuer, subject)
);

CREATE TABLE tenant_membership (
    tenant_id UUID NOT NULL,
    principal_id UUID NOT NULL REFERENCES principal(principal_id),
    status TEXT NOT NULL,
    PRIMARY KEY (tenant_id, principal_id)
);
```

Ba ràng buộc có tác dụng khác nhau:

- Khóa chính của `principal` ngăn hai bản ghi dùng cùng một ID nội bộ.
- Khóa `(issuer, subject)` ngăn một danh tính ngoài bị ghi thành hai liên kết khác nhau trong mô hình này.
- Khóa `(tenant_id, principal_id)` ngăn tạo lặp một quan hệ thành viên đang được biểu diễn bằng một bản ghi.

Khi triển khai thực tế, kiểu dữ liệu và quy tắc đối chiếu chuỗi phải giữ đúng ngữ nghĩa phân biệt giá trị của giao thức. Nếu cơ sở dữ liệu có cấu hình so sánh không phù hợp, ràng buộc duy nhất có thể gộp nhầm hai giá trị khác nhau.

Các constraint không tự xác minh issuer đáng tin, subject có thật hoặc người gọi được phép tạo membership. Ứng dụng vẫn cần kiểm tra giao thức, chính sách cấp phát, trạng thái và quyền quản trị.

## 7. Cấp phát đồng thời: kiểm tra trước chưa đủ

Hai request đăng nhập lần đầu có thể cùng kiểm tra và đều thấy chưa có liên kết danh tính:

```text
Request A: chưa có (Issuer A, u-42)
Request B: chưa có (Issuer A, u-42)

A tạo principal-801
B tạo principal-802

Cả hai cùng muốn tạo liên kết cho một danh tính ngoài.
```

Nếu chỉ dùng logic “SELECT rồi INSERT” mà thiếu ràng buộc duy nhất tại kho dữ liệu có thẩm quyền, có thể tạo hai principal và các quan hệ quyền không nhất quán.

Một hướng xử lý là kết hợp giao dịch, ràng buộc duy nhất và quy tắc lặp lại an toàn:

```text
function resolveOrProvision(verifiedExternalIdentity):
    key = (
        verifiedExternalIdentity.issuer,
        verifiedExternalIdentity.subject
    )

    existing = findBinding(key)
    if existing is present:
        requireAllowedBindingAndPrincipalState(existing)
        return existing.principalId

    requireProvisioningAllowed(verifiedExternalIdentity)

    try:
        transaction:
            principal = insertNewPrincipalWithFreshId()
            insertExternalBinding(key, principal.id)
        return principal.id
    catch DuplicateExternalBindingKey:
        rollbackFailedTransaction()
        existing = readCommittedBinding(key)
        requireAllowedBindingAndPrincipalState(existing)
        return existing.principalId
```

Giả mã giả định thao tác tạo principal và liên kết nằm trong cùng giao dịch; nếu liên kết thất bại, principal mới cũng không được để lại như một bản ghi mồ côi. Cơ chế đọc sau xung đột cần phù hợp với mức cô lập và cơ sở dữ liệu đang dùng.

Chỉ nhánh xung đột đúng khóa liên kết đã xác minh mới được xử lý theo cách này. Không bắt mọi lỗi unique rồi tự gộp tài khoản. Xung đột email, một liên kết cũ bị vô hiệu hóa hoặc dữ liệu nhập sai có thể cần xử lý riêng.

Giải quyết principal xong cũng không được tự cấp lại quyền đã thu hồi. JIT provisioning cần chính sách rõ ràng; membership và vai trò được tạo theo nghiệp vụ được phép, không phải tác dụng phụ của mọi lần đăng nhập.

## 8. Duy nhất theo thời gian: không chuyển danh tính cũ cho người mới

Giả sử Lan có email `support@example.test`, principal là `principal-801`, và từng có quyền xuất dữ liệu. Sau khi Lan nghỉ việc, email được cấp cho Minh.

Nếu hệ thống lấy email làm khóa duy nhất lâu dài rồi tự gắn lần đăng nhập của Minh vào principal-801, Minh có thể nhận quyền và lịch sử của Lan.

Một mô hình đúng cần giữ sự khác biệt giữa:

- Địa chỉ email được tái sử dụng theo quy trình của tổ chức.
- Principal đại diện cho tài khoản hoặc chủ thể trước đây.
- Quyền cần cấp mới cho người tiếp nhận công việc.

Minh không được trở thành principal-801 chỉ vì có cùng email. Nếu cần chuyển quyền hoặc tài nguyên công việc, đó là thao tác nghiệp vụ riêng, có kiểm tra và lưu vết.

### Khi vô hiệu hóa hoặc xóa tài khoản

Không tái cấp `principal_id` của tài khoản cũ cho một chủ thể khác. Các tham chiếu lịch sử, sự kiện hoặc cache cũ không được vô tình trỏ đến người mới.

Cách lưu bản ghi đã vô hiệu hóa, dấu vết định danh đã dùng hoặc dữ liệu đã ẩn danh cần tuân theo chính sách lưu trữ và quyền riêng tư của hệ thống. Mục tiêu không phải giữ mọi dữ liệu cá nhân vô thời hạn, mà là duy trì tính đúng đắn của tham chiếu và ngăn tái cấp gây nhầm danh tính.

Nếu cùng một người quay lại làm việc, việc khôi phục principal cũ hay tạo principal mới là quyết định của chính sách tài khoản. Dù chọn cách nào, không tự khôi phục toàn bộ quyền trước đây chỉ vì email hoặc tên giống nhau.

## 9. Hợp nhất, tách và di chuyển danh tính

Trong quá trình vận hành có thể phát hiện hai principal thuộc cùng một người, hoặc một ánh xạ đã được tạo sai. Đây không chỉ là thao tác sửa một khóa ngoại.

Trước khi hợp nhất cần xác minh quan hệ giữa các danh tính và xem xét:

- Quyền của hai principal có được cộng dồn không, và ai có thẩm quyền quyết định?
- Các tenant có cho phép liên kết những danh tính đó không?
- Phiên, token, yếu tố MFA và phương thức khôi phục đang gắn với principal nào?
- Quyền sở hữu tài nguyên và lịch sử kiểm toán được bảo toàn ra sao?
- Có liên kết sai nào cần tách thay vì hợp nhất không?

Không tự động hợp nhất chỉ vì tên, email hoặc số điện thoại trùng. Một thao tác hợp nhất có thể vô tình đưa quyền quản trị vào một đường đăng nhập có mức bảo đảm thấp hơn.

Khi di chuyển IdP, issuer hoặc subject có thể thay đổi. Cần ánh xạ bằng dữ kiện có thẩm quyền và quy trình được kiểm soát, xử lý xung đột trước khi chuyển quyền. Không coi mọi subject giống nhau ở nguồn mới là cùng chủ thể với nguồn cũ.

Kiểm toán nên ghi lại thao tác liên kết hoặc chuyển đổi, người thực hiện, căn cứ, thời điểm và quan hệ trước–sau. Không sửa toàn bộ log cũ để làm như danh tính mới đã tồn tại từ đầu.

## 10. Áp dụng cho workload, phiên và quyền

### Workload có phạm vi định danh riêng

Tên `report-exporter` có thể xuất hiện trong nhiều cụm hoặc môi trường. Thiết kế cần xác định danh tính logic của dịch vụ, nguồn cấp và phạm vi môi trường; không để workload thử nghiệm được nhận quyền production vì trùng tên.

Một dịch vụ logic cũng có thể chạy nhiều instance với credential hoặc định danh instance riêng. Credential được xoay vòng không nhất thiết tạo một principal logic mới. Ngược lại, hai workload khác chức năng không nên dùng chung principal chỉ để tiện quản lý secret nếu cần phân quyền và kiểm toán riêng.

### Phiên và token phải giữ đúng chủ thể

Phiên nên tham chiếu principal ổn định thay vì tra lại chủ thể chỉ bằng email ở mỗi request. Token hoặc ngữ cảnh xác thực phải được xác minh trước khi ánh xạ; trạng thái tài khoản và quyền hiện tại được áp dụng theo thiết kế.

Tính duy nhất không bảo đảm thu hồi tức thời. Vô hiệu hóa tài khoản hay đổi liên kết cần xác định ảnh hưởng đến phiên, token và cache. Dữ liệu cũ trong các thành phần này có thể tiếp tục có hiệu lực nếu cơ chế thu hồi không xử lý chúng.

### RBAC và ABAC cần khóa chủ thể nhất quán

RBAC gán vai trò cho đúng principal và phạm vi. ABAC sử dụng thuộc tính gắn với đúng principal, tài nguyên và nguồn có thẩm quyền. Cả hai đều có thể quyết định sai nếu tầng định danh đã gộp nhầm người dùng hoặc làm mất tenant.

SSO và federation cũng cần ánh xạ duy nhất trước khi thiết lập phiên cục bộ. MFA giúp tăng mức bảo đảm xác thực nhưng không sửa được một ánh xạ tài khoản sai.

## 11. Những tình huống cần tự phân tích

| Tình huống | Vấn đề cần nhận diện | Hướng xử lý |
|---|---|---|
| Hai IdP cùng trả `sub=u-42` | Mất namespace nếu chỉ lưu subject | Giữ nguồn phát hành đã xác minh cùng subject |
| Hai tenant cùng có user ID `42` | Khóa cục bộ bị dùng như khóa toàn cục | Truyền và kiểm tra đầy đủ phạm vi tenant |
| Email đổi làm dữ liệu sở hữu bị mất liên kết | Bí danh bị dùng làm khóa danh tính ổn định | Tham chiếu principal ổn định và quản lý bí danh riêng |
| Nhân viên mới nhận email của người cũ và có quyền cũ | Tái cấp bí danh bị diễn giải thành tái sử dụng danh tính | Không tự liên kết bằng email; cấp quyền theo nghiệp vụ |
| Hai lần JIT tạo hai principal | Thiếu ràng buộc hoặc xử lý đồng thời | Dùng constraint và giao dịch, xử lý đúng loại xung đột |
| Đăng nhập lại làm quyền đã thu hồi xuất hiện lại | Cấp phát bị nhầm với cấp quyền mặc định mỗi lần đăng nhập | Tách chính sách JIT, membership và vòng đời quyền |
| Hai tài khoản cùng tên bị hợp nhất | Tên hiển thị bị dùng làm bằng chứng cùng chủ thể | Xác minh quan hệ trước khi liên kết hoặc hợp nhất |
| UUID hợp lệ được dùng để đọc dữ liệu người khác | Nhầm tính duy nhất với quyền truy cập | Kiểm tra principal, tenant, hành động và tài nguyên |

Khi chọn một khóa danh tính, hãy viết rõ phạm vi duy nhất, quy tắc so sánh, tính ổn định và chính sách không tái cấp. Sau đó giữ những điều kiện đó nhất quán từ kho danh tính đến API, phiên, cache, hàng đợi và log. Nhờ vậy, hệ thống IAM mới có nền tảng chính xác để xác thực, cấp quyền ít nhất và giải trình ai đã thực hiện từng hành động.
