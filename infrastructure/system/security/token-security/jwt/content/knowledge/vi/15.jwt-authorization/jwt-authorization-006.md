# Kiểm tra quyền sở hữu đối tượng và tránh truy cập chéo người dùng

## 1. Đăng nhập hợp lệ không có nghĩa được đọc dữ liệu của người khác

Một hệ thống sử dụng JSON Web Token (JWT) có thể xác minh thành công access token và nhận diện người gọi là một người dùng hợp lệ. Tuy nhiên, điều đó chưa chứng minh người dùng có quyền truy cập mọi hồ sơ, đơn hàng, hóa đơn, tài liệu hoặc tệp trong hệ thống.

Ví dụ, một ứng dụng quản lý hồ sơ cá nhân có hai người dùng:

~~~text
User A: user-100
User B: user-200

Profile P-A: owner = user-100
Profile P-B: owner = user-200
~~~

User A gửi request:

~~~http
GET /profiles/P-A HTTP/1.1
Authorization: Bearer <token-of-user-A>
~~~

API xác minh JWT, đọc claim sub = user-100, tải hồ sơ P-A và kiểm tra chủ sở hữu. Request có thể được cho phép.

Nhưng nếu User A thay ID thành P-B:

~~~http
GET /profiles/P-B HTTP/1.1
Authorization: Bearer <token-of-user-A>
~~~

thì API phải từ chối nếu User A không có quan hệ chia sẻ, vai trò quản lý hoặc quyền đặc biệt đối với hồ sơ P-B. Việc token vẫn hợp lệ không thay đổi chủ sở hữu của hồ sơ.

Đây là bài toán **kiểm tra quyền sở hữu đối tượng (ownership authorization)** và **ngăn truy cập chéo người dùng (cross-user access)**. Mỗi request cần xác minh quan hệ giữa chủ thể đã xác thực và tài nguyên thực tế.

> **JWT cho biết token đại diện cho chủ thể nào; dữ liệu tài nguyên và chính sách của ứng dụng mới xác định chủ thể đó có quyền với đối tượng nào.**

Bài học này thuộc phạm vi Security chung của JSON Web Token (JWT), áp dụng cho API và ứng dụng nói chung. Các nguyên tắc không phụ thuộc một ngôn ngữ lập trình hoặc framework cụ thể.

## 2. Chủ sở hữu, chủ thể và người thực hiện hành động

Trong một quyết định quyền, cần phân biệt ba vai trò:

- **Principal:** chủ thể đã được xác định từ JWT đã xác minh, ví dụ người dùng hoặc tài khoản dịch vụ.
- **Owner:** chủ sở hữu hoặc thực thể chịu trách nhiệm đối với tài nguyên theo mô hình nghiệp vụ.
- **Actor:** chủ thể thực hiện hành động hiện tại. Actor có thể trùng principal hoặc là một dịch vụ/người đại diện thực hiện thay mặt principal.

Ví dụ:

~~~text
Principal: user-100
Actor: user-100
Resource: document-501
Owner: user-100
Action: document.read
~~~

Nếu người dùng A đọc tài liệu của mình, principal và owner có thể trùng nhau.

Trong một trường hợp khác:

~~~text
Principal: user-100
Actor: support-agent-9
Resource: document-501
Owner: user-100
Action: document.read
~~~

Một nhân viên hỗ trợ đang thao tác thay mặt user-100. Đây không phải quyền sở hữu của nhân viên hỗ trợ; nó là một quan hệ ủy quyền cần được kiểm tra riêng.

Không nên rút gọn mọi trường hợp thành điều kiện so sánh một ID. Hệ thống cần xác định **ai là chủ thể, ai đang hành động, tài nguyên thuộc về ai và quan hệ nào cho phép hành động đó**.

### 2.1. Nhận diện chủ thể từ JWT

Một JWT access token có thể chứa:

~~~json
{
  "iss": "https://identity.example.test",
  "sub": "user-100",
  "aud": "https://api.example.test/profiles",
  "exp": 1900003600,
  "scope": "profile:read profile:update"
}
~~~

Đây là payload minh họa đã giải mã, không phải token hoàn chỉnh có chữ ký thực. Các claim iss, sub, aud và exp có ngữ nghĩa theo JWT; scope phụ thuộc profile/hợp đồng phát hành.

Khi ánh xạ chủ thể sang tài khoản nội bộ, nên xét cặp **(iss, sub)** vì subject thường chỉ duy nhất trong không gian định danh của issuer. Không mặc định sub luôn là ID của người dùng trong cơ sở dữ liệu nghiệp vụ.

### 2.2. Owner ID phải lấy từ tài nguyên đáng tin cậy

Giả sử client gửi:

~~~json
{
  "profile_id": "P-200",
  "owner_id": "user-100"
}
~~~

API không được tin owner_id do client cung cấp để kết luận P-200 thuộc user-100. Server phải tải hồ sơ từ nguồn dữ liệu có thẩm quyền và lấy owner thực tế từ bản ghi.

Tương tự, các thuộc tính sau phải được kiểm soát:

- **owner_id:** chủ sở hữu hiện tại.
- **created_by:** người tạo bản ghi.
- **tenant_id:** tổ chức sở hữu hoặc quản lý dữ liệu.
- **shared_with:** danh sách hoặc quan hệ chia sẻ.
- **delegated_to:** người được ủy quyền.
- **status:** trạng thái nghiệp vụ ảnh hưởng quyền thao tác.

Client có thể gửi các giá trị này như dữ liệu đầu vào của một quy trình đặc biệt, nhưng API phải xác minh quyền thay đổi chúng và không được tự động gán chúng vào tài nguyên.

## 3. Ownership authorization khác với authentication và scope

| Lớp | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| **Authentication** | Xác minh token và nhận diện chủ thể. | JWT hợp lệ, principal là user-100. |
| **Endpoint/function authorization** | Kiểm tra chủ thể có thể gọi chức năng hay không. | Token có scope profile:read. |
| **Ownership authorization** | Kiểm tra quan hệ giữa principal và object. | profile.owner_id = user-100. |
| **Relationship/exception policy** | Kiểm tra quyền bổ sung ngoài ownership trực tiếp. | Tài liệu được chia sẻ cho user-100 hoặc user-100 là người giám hộ hợp lệ. |

Scope profile:read là điều kiện có thể cần để đọc hồ sơ, nhưng không tự động cho phép đọc hồ sơ của tất cả người dùng. Quyền đọc một loại tài nguyên và quyền đọc một bản ghi cụ thể là hai câu hỏi khác nhau.

Một chính sách đơn giản:

~~~text
ALLOW profile.read khi:
    JWT hợp lệ cho Profile API
    AND token có scope profile:read
    AND principal được xác định
    AND (
        profile.owner_id = principal.id
        OR có quan hệ chia sẻ còn hiệu lực
        OR có quyền đại diện/quản trị hợp lệ
    )

Mọi trường hợp khác: DENY
~~~

Nếu API chỉ kiểm tra JWT và scope rồi tải profile theo ID, API có thể mắc lỗi truy cập chéo người dùng.

## 4. IDOR và BOLA trong truy cập chéo người dùng

**Insecure Direct Object Reference (IDOR)** mô tả tình huống ứng dụng dùng một định danh trực tiếp do client tham chiếu nhưng không kiểm tra quyền phù hợp trên đối tượng đó.

**Broken Object Level Authorization (BOLA)** là thuật ngữ trong OWASP API Security Top 10 mô tả lỗi API không thực thi đúng quyền của chủ thể đối với object được yêu cầu.

Ví dụ:

~~~text
User A có token hợp lệ.
User A có scope order:read.
API nhận GET /orders/ORDER-200.
ORDER-200 thuộc User B.
API chỉ kiểm tra token và scope rồi trả đơn hàng.
~~~

Đây là lỗi ownership authorization. Việc ID là UUID khó đoán không giải quyết nguyên nhân: người dùng có thể lấy ID từ email, lịch sử trình duyệt, log, liên kết chia sẻ, dữ liệu xuất hoặc một endpoint khác.

### 4.1. Các vị trí ID có thể xuất hiện

Đừng chỉ kiểm tra ID ở URL path. Object ID có thể được gửi qua:

- Path parameter: /orders/{orderId}.
- Query parameter: ?orderId=...
- JSON body: {"order_id":"..."}.
- Header tùy chỉnh.
- Danh sách ID trong bulk request.
- ID cha và ID con trong endpoint lồng nhau.
- Cursor, export job ID hoặc file ID.
- GraphQL argument hoặc nested field.

Mỗi đường truy cập phải đưa ra quyết định quyền trên đúng object.

### 4.2. Thay ID là một phép thử bảo mật cơ bản

Với hai người dùng A và B:

~~~text
User A + Resource A -> ALLOW nếu chính sách cho phép
User A + Resource B -> DENY nếu không có quan hệ bổ sung
User B + Resource B -> ALLOW nếu chính sách cho phép
User B + Resource A -> DENY nếu không có quan hệ bổ sung
~~~

Kiểm thử nên thực hiện cả khi ID tuần tự, UUID, ID được lấy từ response hợp lệ và ID được truyền qua body hoặc query.

## 5. Các mô hình quan hệ sở hữu

Không phải mọi tài nguyên đều có đúng một owner. Mô hình dữ liệu cần phản ánh đúng quan hệ nghiệp vụ.

### 5.1. Một owner duy nhất

Ví dụ hồ sơ cá nhân hoặc ghi chú riêng:

~~~text
profile_id | owner_id
-----------|---------
P-100      | user-100
P-200      | user-200
~~~

Chính sách:

~~~text
ALLOW profile.read nếu profile.owner_id = principal.id
~~~

Mô hình này dễ hiểu, nhưng vẫn cần xác minh loại hành động và trạng thái. Chủ sở hữu có thể được đọc nhưng không được xóa một bản ghi đang bị lưu trữ theo quy định.

### 5.2. Một tài nguyên thuộc về tổ chức

Một hóa đơn có thể thuộc công ty chứ không thuộc một nhân viên:

~~~text
invoice_id | tenant_id | created_by
-----------|-----------|-----------
INV-100    | company-a | user-100
INV-200    | company-a | user-200
INV-300    | company-b | user-100
~~~

User-100 tạo INV-300 không có nghĩa họ sở hữu hoặc được xem hóa đơn đó. Tư cách thành viên của company-b, quyền theo role và chính sách của tổ chức mới quyết định truy cập.

Phải phân biệt:

- **tenant owner:** tổ chức sở hữu dữ liệu.
- **record creator:** chủ thể đã tạo bản ghi.
- **business owner:** người chịu trách nhiệm nghiệp vụ.
- **current assignee:** người đang được giao xử lý.

Các trường này không đồng nghĩa. Không dùng created_by thay owner_id nếu nghiệp vụ cho phép chuyển giao hoặc phân công lại.

### 5.3. Nhiều người cùng sở hữu

Một workspace, dự án hoặc tài khoản chung có thể có nhiều chủ sở hữu:

~~~text
resource_id | principal_id | relation
------------|--------------|---------
WS-100      | user-100     | owner
WS-100      | user-200     | owner
WS-100      | user-300     | editor
~~~

Khi đó, ownership là một quan hệ nhiều-nhiều. API phải tra cứu quan hệ và kiểm tra loại quan hệ có đủ cho action hay không. Người là editor không mặc nhiên được xóa workspace hoặc chuyển quyền sở hữu.

### 5.4. Chia sẻ và cộng tác

Một tài liệu có thể thuộc user-100 nhưng được chia sẻ cho user-200:

~~~text
document_id | principal_id | permission
------------|--------------|-----------
DOC-100     | user-100     | owner
DOC-100     | user-200     | reader
DOC-100     | user-300     | editor
~~~

User-200 có thể đọc nhờ quan hệ chia sẻ, nhưng không trở thành owner. Khi chia sẻ bị thu hồi, API cần nhận biết trạng thái mới theo yêu cầu thu hồi của hệ thống.

### 5.5. Delegation và đại diện

Một người có thể được ủy quyền thao tác thay mặt người khác:

~~~text
delegator = user-100
delegate  = user-200
resource  = account-500
actions   = [account.read, payment.create]
validity  = 2026-11-01 through 2026-11-30
~~~

Ủy quyền cần có phạm vi, action, thời hạn và điều kiện rõ ràng. Việc được ủy quyền không biến delegate thành owner. Khi đánh giá request, cần biết ai là người được đại diện, ai là actor và quyền nào đã được trao.

## 6. Kiểm tra owner và quan hệ cho từng action

Quyền sở hữu không nhất thiết bao gồm mọi hành động. Một chính sách cần định nghĩa riêng:

| Action | Điều kiện ví dụ |
| --- | --- |
| **Read** | Owner hoặc người được chia sẻ có quyền đọc. |
| **Update** | Owner hoặc editor; chỉ các trường được phép. |
| **Delete** | Owner có quyền xóa và tài nguyên chưa bị khóa/retention. |
| **Transfer ownership** | Owner hiện tại hoặc quản trị viên có quyền chuyển giao; người nhận hợp lệ. |
| **Share** | Owner hoặc người có permission chia sẻ; không được cấp vượt quyền của mình. |
| **Approve** | Người duyệt được chỉ định, không vi phạm tách nhiệm vụ và trạng thái cho phép. |
| **Export** | Có quyền đọc tập dữ liệu và quyền xuất dữ liệu theo chính sách. |

### 6.1. Quyền đọc

Một user có thể xem tài liệu nếu là owner, được chia sẻ hoặc có quan hệ nghiệp vụ được công nhận. API phải đánh giá quan hệ đó ở thời điểm request theo mức nhất quán yêu cầu.

### 6.2. Quyền sửa

Có quyền đọc không có nghĩa có quyền sửa. Người được chia sẻ với vai trò reader không thể cập nhật nội dung hoặc thay owner.

Ngoài kiểm tra object, API phải lọc trường được phép cập nhật. Ví dụ người dùng có thể đổi title nhưng không thể đổi owner_id, tenant_id, classification hoặc approved.

### 6.3. Quyền xóa

Xóa có thể cần điều kiện bổ sung:

- Chủ sở hữu hiện tại.
- Tài nguyên chưa bị khóa.
- Không còn nghĩa vụ lưu trữ.
- Không có giao dịch liên quan đang xử lý.
- Không bị policy/legal hold ngăn xóa.

Không nên coi quyền update tổng quát là quyền delete.

### 6.4. Chuyển quyền sở hữu

Chuyển owner là thao tác nhạy cảm vì nó thay đổi ai có quyền kiểm soát tài nguyên. API cần:

1. Xác minh người chuyển là owner hiện tại hoặc actor có quyền quản trị phù hợp.
2. Xác minh người nhận tồn tại và đủ điều kiện nhận.
3. Kiểm tra tenant hoặc phạm vi tổ chức có cho phép chuyển giao không.
4. Xác định quan hệ chia sẻ, delegate và quyền cũ sẽ được giữ, chuyển hay thu hồi.
5. Thực hiện cập nhật có kiểm soát đồng thời.
6. Ghi audit về owner cũ, owner mới, actor, lý do và thời điểm.

Không cho client gửi owner_id mới trong một request cập nhật thông thường rồi tự động ghi vào bản ghi.

## 7. Tạo tài nguyên: gán owner từ danh tính đã xác minh

Một lỗi phổ biến là tin owner do client gửi:

~~~json
{
  "title": "Ghi chú cá nhân",
  "owner_id": "user-999"
}
~~~

Nếu request được gửi bởi user-100 và API chấp nhận owner_id tùy ý, user-100 có thể tạo tài nguyên dưới danh nghĩa người khác hoặc lợi dụng quy trình để thao túng quyền.

Đối với tài nguyên cá nhân, một quy tắc an toàn thường là:

~~~text
owner_id = verifiedPrincipal.id
~~~

Server lấy principal từ JWT đã xác minh và gán owner theo chính sách. Client có thể không cần gửi owner_id.

Nếu nghiệp vụ cho phép tạo tài nguyên thay mặt người khác, cần một action riêng như resource.create_for_user, kiểm tra quyền ủy quyền và ghi nhận actor cùng subject được đại diện.

### 7.1. Không nhầm created_by và owner_id

~~~text
created_by = user-100
owner_id   = user-200
~~~

Trạng thái này có thể hợp lệ khi user-100 tạo hồ sơ thay mặt user-200 theo quy trình được ủy quyền. Quyền sở hữu và dấu vết người tạo phải được lưu riêng nếu nghiệp vụ cần cả hai.

## 8. Chống mass assignment và thay đổi thuộc tính sở hữu

Giả sử API nhận request cập nhật:

~~~json
{
  "display_name": "Tài liệu mới",
  "owner_id": "user-999",
  "tenant_id": "company-b",
  "shared_with": ["user-999"],
  "access_level": "admin"
}
~~~

Nếu API tự động sao chép tất cả trường vào tài nguyên, client có thể:

- Chuyển quyền sở hữu sang tài khoản khác.
- Chuyển tài nguyên sang tenant khác.
- Tự chia sẻ với một người dùng.
- Tự nâng quyền truy cập.

Đây là nhóm lỗi **mass assignment / over-posting**. Quyền cập nhật object không đồng nghĩa quyền sửa mọi thuộc tính.

Nên chia trường theo mức tin cậy:

| Nhóm trường | Ví dụ | Cách xử lý |
| --- | --- | --- |
| Client có thể sửa | title, description | Cho phép sau khi kiểm tra update permission. |
| Server quản lý | owner_id, tenant_id, created_by | Không bind trực tiếp từ payload thông thường. |
| Quy trình đặc biệt | shared_with, access_level, delegate | Chỉ thay đổi qua action riêng có policy. |
| Trạng thái nghiệp vụ | approved, paid, archived | Chỉ chuyển qua transition hợp lệ và actor có quyền. |

Hợp đồng request nên chỉ định rõ trường được chấp nhận. Nếu client gửi trường nhạy cảm không được hỗ trợ, API có thể từ chối request hoặc bỏ qua theo một quy tắc được công bố; không được âm thầm gán trường đó vào tài nguyên.

## 9. Truy vấn tài nguyên trong phạm vi người dùng

Kiểm tra quyền sau khi tải object có thể đúng nếu được thực hiện đầy đủ, nhưng truy vấn ngay trong phạm vi principal thường giúp giảm nguy cơ trả nhầm object và giảm việc tải dữ liệu ngoài quyền.

### 9.1. Mẫu truy vấn nguy hiểm

~~~sql
SELECT *
FROM documents
WHERE document_id = :document_id;
~~~

Truy vấn chỉ tìm theo ID. Nếu code phía sau quên kiểm tra owner hoặc relationship, object của người khác có thể bị trả về.

### 9.2. Giới hạn theo owner

~~~sql
SELECT *
FROM documents
WHERE document_id = :document_id
  AND owner_id = :verified_principal_id;
~~~

verified_principal_id phải được ánh xạ từ principal đã xác minh. Không lấy giá trị này từ request body.

### 9.3. Giới hạn theo quan hệ

Với mô hình có chia sẻ, truy vấn cần xét quan hệ được phép:

~~~sql
SELECT d.*
FROM documents d
WHERE d.document_id = :document_id
  AND (
      d.owner_id = :verified_principal_id
      OR EXISTS (
          SELECT 1
          FROM document_shares s
          WHERE s.document_id = d.document_id
            AND s.principal_id = :verified_principal_id
            AND s.permission IN ('reader', 'editor')
            AND s.revoked_at IS NULL
      )
  );
~~~

Đây là ví dụ truy vấn minh họa. Quyền thực tế cần phân biệt reader/editor và action cụ thể; truy vấn cho phép đọc không tự cho phép cập nhật hoặc xóa.

### 9.4. Danh sách tài nguyên

Một endpoint:

~~~http
GET /my/documents?page=1
Authorization: Bearer <access-token>
~~~

nên xác định tập tài nguyên mà principal được phép xem trước khi áp dụng pagination:

~~~text
1. Xác minh principal.
2. Xác định tài nguyên do principal sở hữu hoặc được chia sẻ hợp lệ.
3. Áp dụng bộ lọc tìm kiếm trên tập được phép.
4. Tính total và phân trang trên tập đó.
5. Trả metadata chỉ phản ánh tài nguyên được phép.
~~~

Nếu tải toàn bộ tài liệu rồi lọc sau khi phân trang, hệ thống có thể làm lộ total, thứ tự, cursor hoặc tạo các trang rỗng bất thường.

## 10. Quyền sở hữu trong các tình huống đặc biệt

### 10.1. Tài khoản gia đình hoặc nhóm

Một tài khoản gia đình có thể có chủ tài khoản, thành viên, người giám hộ và trẻ phụ thuộc. Quan hệ không thể được rút gọn thành owner ID duy nhất.

Chính sách cần định nghĩa:

- Ai có thể xem dữ liệu của ai.
- Quan hệ nào cho phép xem, sửa hoặc quản lý.
- Có cần xác minh độ tuổi hoặc quyền giám hộ theo nghiệp vụ không.
- Quan hệ có hiệu lực trong khoảng thời gian nào.
- Điều gì xảy ra khi thành viên rời nhóm.

### 10.2. Tài khoản tổ chức

Một nhân viên có thể tạo dữ liệu trong tenant nhưng không sở hữu dữ liệu đó. Khi nhân viên rời tổ chức, dữ liệu vẫn có thể thuộc công ty; quyền truy cập của nhân viên cần bị thu hồi theo membership và role hiện hành.

Không tự động xóa dữ liệu chỉ vì người tạo đã rời tổ chức. Ownership phải phản ánh quy tắc nghiệp vụ, không chỉ lịch sử tạo.

### 10.3. Dịch vụ tự động

Một service principal có thể tạo báo cáo hoặc bản sao dữ liệu. Tài nguyên có thể thuộc tổ chức hoặc người dùng mà job đại diện. Cần lưu riêng:

- Service/actor thực hiện.
- Subject hoặc tenant được đại diện.
- Phạm vi ủy quyền.
- Chủ sở hữu nghiệp vụ của tài nguyên.

Không gán owner là service chỉ vì service đã ghi bản ghi nếu nghiệp vụ quy định tài nguyên thuộc về user hoặc tenant.

### 10.4. Tài nguyên công khai hoặc chia sẻ bằng liên kết

Một số ứng dụng cho phép công khai tài liệu hoặc tạo liên kết chia sẻ. Khi đó quyền truy cập không nhất thiết dựa trên owner trực tiếp, nhưng vẫn phải là một policy rõ ràng:

- Chủ sở hữu có quyền bật/tắt chia sẻ.
- Liên kết có phạm vi action (read/download/edit).
- Liên kết có thời hạn và có thể thu hồi.
- Có thể yêu cầu secret/token riêng hoặc xác minh bổ sung.
- Không để link công khai vượt qua tenant, classification hoặc chính sách dữ liệu.

Một URL khó đoán không tự trở thành cơ chế authorization đủ mạnh. Nếu liên kết là bearer capability, người sở hữu liên kết có thể sử dụng nó; cần xem xét vòng đời, khả năng thu hồi và nguy cơ rò rỉ.

## 11. Cache và dữ liệu quyền sở hữu

Cache có thể làm rò dữ liệu chéo người dùng nếu không gắn ngữ cảnh quyền.

Ví dụ cache nguy hiểm:

~~~text
cache key = document_id
value = document response
~~~

User A tải DOC-100 hợp lệ, response được lưu theo document ID. User B gọi cùng ID và nhận response từ cache mà không chạy kiểm tra quyền.

### 11.1. Cache key phải có ngữ cảnh phù hợp

Tùy mô hình, cache key có thể cần xét:

~~~text
issuer
principal
tenant
action
resource_id
authorization_version
representation/field policy
~~~

Không phải mọi cache đều phải chứa mọi trường trên, nhưng cache chứa dữ liệu hoặc quyết định authorization phải phân vùng theo những thuộc tính làm thay đổi kết quả. Cách an toàn hơn trong một số trường hợp là cache dữ liệu thô ở tầng nội bộ và áp dụng policy/field projection riêng cho mỗi request trước khi trả response.

### 11.2. Thu hồi chia sẻ và thay đổi owner

Khi owner thay đổi hoặc một share bị thu hồi:

- Invalidate cache dữ liệu/quyết định liên quan.
- Đảm bảo các API và vùng triển khai nhận thay đổi trong giới hạn thời gian chấp nhận.
- Không dùng response đã cache từ principal trước để phục vụ principal khác.
- Cân nhắc version quan hệ hoặc policy để phát hiện cache cũ.

Đối với dữ liệu nhạy cảm, cache ALLOW lâu có thể tạo cửa sổ truy cập sau khi quyền đã bị thu hồi.

## 12. Tệp, export và background job

Kiểm tra owner trên API metadata nhưng quên bảo vệ đường truy cập gián tiếp vẫn có thể dẫn tới cross-user access.

### 12.1. File download

Một user có thể có quyền đọc metadata nhưng không có quyền tải nội dung tệp. API cần kiểm tra quyền trước khi cấp URL tải và ràng buộc URL vào đúng file, hành động và thời hạn.

Nếu URL ký số tồn tại 24 giờ nhưng share bị thu hồi sau 1 phút, người giữ URL có thể vẫn tải file trong thời gian còn lại tùy cơ chế storage. Khi cần thu hồi nhanh, cân nhắc proxy qua API hoặc kiểm tra trạng thái tại storage gateway.

### 12.2. Export job

Một người dùng yêu cầu export tài liệu của mình. Job chạy sau vài phút:

~~~text
T0: User tạo export job khi có quyền.
T1: Quyền truy cập tài liệu bị thu hồi.
T2: Background worker bắt đầu chạy.
T3: File export được tạo.
T4: User hoặc người khác tải file.
~~~

Hệ thống cần định nghĩa quyền được kiểm tra ở thời điểm nào:

- Khi tạo job.
- Khi job thực thi và đọc từng tài nguyên.
- Khi file kết quả được tải.

Đối với dữ liệu nhạy cảm, kiểm tra lại quyền khi job chạy và khi tải kết quả giúp tránh việc một quyền cũ tạo ra bản sao có thể truy cập lâu dài.

### 12.3. Job ID cũng là object reference

Không cho phép người dùng tải kết quả chỉ vì họ biết job_id. Cần xác minh job thuộc principal/tenant hoặc được chia sẻ hợp lệ, đồng thời kiểm tra quyền trên dữ liệu kết quả.

## 13. Delegation, support access và break-glass

Một số nghiệp vụ cần người khác truy cập tài nguyên thay mặt owner:

- Nhân viên hỗ trợ xử lý yêu cầu khách hàng.
- Người quản lý được xem hồ sơ của nhân viên trong nhóm.
- Người giám hộ quản lý tài khoản phụ thuộc.
- Nhân viên thay thế xử lý công việc khi người phụ trách vắng mặt.
- Quản trị viên thực hiện thao tác khẩn cấp theo quy trình break-glass.

Đây là các ngoại lệ có kiểm soát, không phải lý do để bỏ kiểm tra owner.

### 13.1. Quy tắc delegation

Một bản ghi ủy quyền nên xác định:

~~~text
delegator
delegate
resource_scope
allowed_actions
valid_from
valid_until
status
reason
~~~

API phải kiểm tra:

1. Delegation được tạo bởi chủ thể có quyền.
2. Delegate đúng là người thực hiện request.
3. Resource nằm trong phạm vi ủy quyền.
4. Action nằm trong tập được cấp.
5. Ủy quyền còn hiệu lực và chưa bị thu hồi.
6. Không vượt qua các giới hạn khác như tenant, classification hoặc trạng thái tài nguyên.

### 13.2. Không nâng quyền qua delegation

Nếu owner chỉ có quyền đọc, owner không thể cấp cho delegate quyền xóa hoặc quản trị rộng hơn quyền mà chính sách cho phép. Quy tắc thường là:

~~~text
Delegated permissions
    subset of
Permissions that delegator is allowed to delegate
~~~

Một số hệ thống cho phép quản trị viên cấp quyền độc lập với owner; khi đó đây là một luồng quản trị riêng, cần audit và kiểm soát rõ.

### 13.3. Support access và break-glass

Quyền hỗ trợ hoặc khẩn cấp nên có:

- Lý do và ticket/case liên quan.
- Phạm vi tài nguyên cụ thể.
- Thời hạn ngắn.
- Action được phép.
- Xác thực tăng cường nếu phù hợp.
- Audit đầy đủ và khả năng rà soát sau sự kiện.

Không dùng một role support hoặc admin toàn cục để mặc nhiên đọc mọi dữ liệu người dùng trong mọi tình huống.

## 14. Pseudocode: kiểm tra quyền sở hữu một tài liệu

Ví dụ dưới đây mô tả một API đọc tài liệu. Hàm xác minh JWT phải kiểm tra chữ ký, issuer, audience, thời gian và mục đích access token trước khi claims được tin cậy.

~~~text
function readDocument(request):
    verified = validateAccessToken(
        extractBearerToken(request.headers),
        trustedIssuer = "https://identity.example.test",
        expectedAudience = "https://api.example.test/documents"
    )
    if verified.failed:
        return HTTP 401

    principal = resolvePrincipal(verified.claims.iss, verified.claims.sub)
    if principal is null:
        return HTTP 403

    if not exactScopeContains(verified.claims.scope, "document:read"):
        return HTTP 403

    document = loadDocument(request.path.documentId)
    if document is null:
        return HTTP 404

    relationship = loadRelationship(
        principal,
        document,
        currentTime()
    )

    allowed = (
        document.owner_id == principal.id
        OR relationship.hasPermission("document.read")
        OR validDelegationAllows(principal, document, "document.read")
    )

    if not allowed:
        auditDenied(principal, "document.read", document.id)
        return HTTP 404

    return HTTP 200 with permittedDocumentFields(document, principal)
~~~

Đây là pseudocode minh họa. Trong hệ thống multi-tenant, cần thêm kiểm tra tenant và membership. Với dữ liệu nhạy cảm, quan hệ và delegation phải lấy từ nguồn hiện hành hoặc cache có giới hạn độ trễ được chấp nhận.

## 15. Pseudocode: chuyển quyền sở hữu an toàn

~~~text
function transferOwnership(request):
    verified = validateAccessToken(request.token, expectedAudience = "Resource API")
    if verified.failed:
        return HTTP 401

    actor = resolvePrincipal(verified.claims.iss, verified.claims.sub)
    resource = loadResourceForUpdate(request.resourceId)
    if resource is null:
        return HTTP 404

    if not policy.canTransferOwnership(actor, resource):
        return HTTP 404

    newOwner = resolveEligibleOwner(request.newOwnerId)
    if newOwner is null:
        return HTTP 400

    if not policy.canReceiveOwnership(newOwner, resource):
        return HTTP 400

    oldOwner = resource.owner_id
    updateOwner(resource, newOwner.id)
    revokeOrReevaluateOldOwnerShares(resource, oldOwner)
    recordAudit(
        actor = actor,
        action = "resource.transfer_ownership",
        resource = resource.id,
        oldOwner = oldOwner,
        newOwner = newOwner.id
    )
    return HTTP 200
~~~

Trong triển khai thực tế, kiểm tra quyền và cập nhật owner cần có cơ chế giao dịch hoặc version để tránh hai lần chuyển giao đồng thời. Chính sách cũng phải xác định quan hệ chia sẻ, delegate và quyền cũ được giữ hay thu hồi sau khi chuyển.

## 16. Những sai lầm thường gặp

| Sai lầm | Rủi ro | Cách phòng tránh |
| --- | --- | --- |
| Chỉ xác minh JWT và scope | User A có thể đọc object của User B. | Kiểm tra ownership/relationship trên từng object. |
| Tin owner_id từ request | Client tự nhận quyền sở hữu hoặc chuyển object. | Lấy owner từ nguồn dữ liệu tin cậy. |
| Dùng created_by thay owner_id | Dữ liệu được tạo thay mặt người khác bị phân quyền sai. | Phân biệt creator, owner, tenant owner và assignee. |
| Coi UUID là cơ chế bảo mật | ID vẫn có thể bị lộ và sử dụng lại. | Authorization phải được kiểm tra dù ID khó đoán. |
| Cho owner mọi action | Chủ sở hữu có thể xóa, chuyển hoặc duyệt ngoài quy tắc. | Định nghĩa permission riêng cho từng action. |
| Không kiểm tra share/delegation hết hạn | Người đã mất quyền vẫn truy cập. | Kiểm tra trạng thái và thời hạn quan hệ. |
| Cho phép cập nhật owner bằng payload chung | Mass assignment có thể chuyển tài nguyên cho người khác. | Dùng action transfer riêng và kiểm tra quyền. |
| Cache chỉ theo resource ID | Response của User A có thể trả cho User B. | Cache theo ngữ cảnh quyền hoặc kiểm tra lại trước khi trả. |
| Kiểm tra quyền sau pagination | Total, cursor hoặc thứ tự có thể làm lộ dữ liệu. | Lọc theo quyền trước count và pagination. |
| Bảo vệ API nhưng quên file/job | Link tải hoặc export vẫn truy cập được sau khi quyền bị thu hồi. | Kiểm tra quyền ở mọi đường truy cập và vòng đời kết quả. |
| Delegation cấp quyền rộng hơn người ủy quyền | Delegate vượt quá quyền có thể trao. | Giới hạn quyền được ủy quyền theo chính sách. |
| Không ghi audit chuyển owner | Khó điều tra thay đổi quyền sở hữu trái phép. | Ghi actor, owner cũ/mới, resource, thời điểm và lý do. |

## 17. Kiểm thử tránh truy cập chéo người dùng

Kiểm thử cần tạo nhiều principal, nhiều object và nhiều loại quan hệ. Mục tiêu là chứng minh API không chỉ hoạt động cho owner mà còn từ chối đúng các request ngoài phạm vi.

### 17.1. Ma trận owner cơ bản

| Principal | Resource A (owner A) | Resource B (owner B) |
| --- | --- | --- |
| User A | ALLOW theo policy | DENY nếu không có quan hệ khác |
| User B | DENY nếu không có quan hệ khác | ALLOW theo policy |
| User C | DENY | DENY |

### 17.2. Ma trận quan hệ chia sẻ

| Quan hệ của User B với Resource A | Read | Update | Delete | Transfer owner |
| --- | :---: | :---: | :---: | :---: |
| Không có quan hệ | DENY | DENY | DENY | DENY |
| Reader còn hiệu lực | ALLOW | DENY | DENY | DENY |
| Editor còn hiệu lực | ALLOW | ALLOW theo field policy | DENY | DENY |
| Share đã bị thu hồi | DENY | DENY | DENY | DENY |
| Delegation chỉ cho read | ALLOW | DENY | DENY | DENY |

Đây là ma trận ví dụ; quyền thật cần theo hợp đồng nghiệp vụ.

### 17.3. Kiểm thử IDOR/BOLA

- Thay ID trong path.
- Thay ID trong query.
- Thay ID trong body.
- Dùng ID lấy từ response của user khác.
- Dùng ID tuần tự và UUID.
- Ghép parent ID hợp lệ với child ID của object khác.
- Gửi danh sách object ID có cả object được phép và không được phép.

### 17.4. Kiểm thử ownership mutation

- Gửi owner_id khác trong request create.
- Gửi owner_id mới trong request update thông thường.
- Gửi tenant_id khác.
- Tự thêm shared_with hoặc access_level.
- Chuyển owner sang người không hợp lệ.
- Chuyển owner hai lần đồng thời.
- Xác minh share và delegation cũ sau khi owner thay đổi.

### 17.5. Kiểm thử cache, file và background job

- User A tải object, sau đó User B yêu cầu cùng object qua cache.
- Share bị thu hồi nhưng cache chưa invalidated.
- User bị thu hồi quyền trước khi export job chạy.
- Job hoàn tất khi owner thay đổi; người tải kết quả phải được xác minh lại.
- URL ký số hết hạn hoặc bị thu hồi theo chính sách.
- Download và preview không vượt qua quyền trên tài liệu gốc.

### 17.6. Kiểm thử không có side effect

Khi request bị từ chối, xác minh:

- Không có dữ liệu bị cập nhật/xóa.
- Không tạo file hoặc export job ngoài quyền.
- Không gửi notification tiết lộ thông tin người khác.
- Không thay đổi owner, share hoặc delegation.
- Không trả metadata nhạy cảm trong lỗi.

Kiểm thử nên gọi endpoint thực tế, không chỉ kiểm tra một hàm so sánh owner ID.

## 18. Checklist thiết kế ownership authorization

Trước khi đưa một loại tài nguyên vào sử dụng, hãy xác định:

1. **Principal:** JWT được xác minh thế nào và ánh xạ (iss, sub) ra sao?
2. **Owner:** tài nguyên thuộc cá nhân, tenant, tổ chức hay nhiều chủ thể?
3. **Creator và assignee:** có khác owner không; khi chuyển giao thì trường nào thay đổi?
4. **Relationships:** có share, group, manager, guardian hoặc delegation không?
5. **Actions:** read, update, delete, transfer, share, approve và export có quyền riêng không?
6. **Ownership source:** owner/tenant/relationship lấy từ nguồn dữ liệu nào?
7. **Create/update:** server gán owner thế nào; các trường nhạy cảm có bị mass assignment không?
8. **Queries:** truy vấn và pagination có giới hạn theo principal/relationship trước khi trả dữ liệu không?
9. **Indirect access:** file, export, job, cache, search và preview có áp dụng cùng chính sách không?
10. **Revocation:** share/delegation/ownership thay đổi có hiệu lực trong bao lâu?
11. **Concurrency:** chuyển owner và thao tác ghi có chống race condition không?
12. **Audit:** có ghi lại actor, owner cũ/mới, resource, action và lý do cần thiết không?
13. **Testing:** có thử chéo user, IDOR, mass assignment, cache, bulk và delegation không?

## 19. Ghi nhớ trọng tâm

- JWT xác minh danh tính/chủ thể; nó không tự chứng minh quyền sở hữu một object.
- **Owner**, **creator**, **tenant owner**, **assignee**, **principal** và **actor** có thể là những thực thể khác nhau.
- Không tin owner ID hoặc tenant ID do client gửi; lấy thuộc tính sở hữu từ nguồn dữ liệu có thẩm quyền.
- Kiểm tra riêng từng action; quyền đọc không tự bao gồm quyền sửa, xóa, chia sẻ hoặc chuyển ownership.
- Chia sẻ và delegation là quan hệ quyền có phạm vi, thời hạn và khả năng thu hồi; chúng không biến người được cấp quyền thành owner.
- Chống IDOR/BOLA bằng kiểm tra quan hệ trên từng object, không dựa vào ID khó đoán.
- Bảo vệ cả list, pagination, cache, file download, export job và mọi đường truy cập gián tiếp.
- Thay đổi owner hoặc quan hệ quyền phải được kiểm soát đồng thời và ghi audit.

**Tài liệu tham khảo kỹ thuật:** OWASP API Security Top 10 (2023), API1: Broken Object Level Authorization; OWASP Authorization Cheat Sheet; CWE-639 (Authorization Bypass Through User-Controlled Key); CWE-862 (Missing Authorization); NIST SP 800-162 (Guide to Attribute Based Access Control). Các tài liệu này bổ sung hướng dẫn về kiểm soát truy cập và thuộc tính; mô hình ownership, chia sẻ và delegation cụ thể vẫn phải được định nghĩa theo nghiệp vụ của ứng dụng.
