# Associated group trong inventory và ownership của PAM

## 1. Associated group dùng để làm gì?

Trong bài này, **associated group** được hiểu là nhóm được liên kết với một bản ghi tài khoản, tài nguyên hoặc đối tượng quản lý trong inventory PAM nhằm biểu diễn một vai trò xác định. Vai trò đó có thể là chịu trách nhiệm về tài khoản, vận hành kỹ thuật, rà soát quyền hoặc tham gia một chính sách truy cập.

Tên trường và cách triển khai tùy hệ thống. Không giả định associated group là một loại nhóm chuẩn chung, cũng không giả định việc thêm liên kết trong inventory tự cấp quyền ở tài nguyên đích.

Ví dụ, bản ghi tài khoản dịch vụ svc-pay-deploy có thể liên kết với:

- Nhóm Payment-Service-Owners: chịu trách nhiệm về nhu cầu tồn tại và mục đích sử dụng tài khoản.
- Nhóm PAM-Operations: vận hành cơ chế lưu trữ và luân chuyển credential theo phạm vi được giao.
- Nhóm Production-Access-Reviewers: rà soát tính phù hợp của quyền trong một quy trình đã định.
- Nhóm Deploy-Job-Identity: có quan hệ cấp quyền với workload nếu chính sách thực tế quy định như vậy.

Các liên kết này phục vụ những câu hỏi khác nhau. Nếu chỉ lưu một chuỗi tên nhóm mà không ghi vai trò, người đọc khó biết ai phải xử lý sự cố, ai được phê duyệt thay đổi và ai có thể sử dụng credential.

Trong PAM, mục đích của associated group là giúp nối inventory với con người, đội vận hành và chính sách. Một liên kết có giá trị phải có chủ thể rõ ràng, phạm vi rõ ràng, bằng chứng và vòng đời được quản lý.

Mục tiêu học tập:

1. Phân loại đúng các kiểu nhóm liên kết với tài khoản và tài nguyên.
2. Phân biệt quan hệ ownership với quan hệ cấp quyền.
3. Xây dựng bản ghi có định danh ổn định, vai trò và bằng chứng.
4. Xử lý nhóm bị đổi tên, xóa, mất chủ sở hữu hoặc thay đổi thành viên.
5. Dùng liên kết để hỗ trợ least privilege, JIT/JEA, vault, rotation, kiểm toán và ứng phó sự cố.

## 2. Bốn câu hỏi cần tách riêng

| Câu hỏi | Loại thông tin cần có |
|---|---|
| Ai chịu trách nhiệm về lý do tồn tại của tài khoản? | Nhóm ownership và người đại diện chịu trách nhiệm |
| Ai thực hiện công việc kỹ thuật liên quan? | Nhóm vận hành, phạm vi nhiệm vụ và quy trình |
| Ai được sử dụng quyền hoặc credential? | Chính sách truy cập thực tế tại PAM và tài nguyên |
| Ai đánh giá hoặc phê duyệt một yêu cầu? | Vai trò trong quy trình, điều kiện và cơ chế phân tách nhiệm vụ |

Một nhóm có thể tham gia nhiều vai trò nếu thiết kế cho phép. Tuy nhiên, phải ghi từng quan hệ riêng và đánh giá việc chồng vai trò. Không suy ra rằng người thuộc nhóm owner tự động được đọc secret, dùng tài khoản quản trị hoặc tự duyệt yêu cầu của mình.

Tương tự, người quản trị vault có khả năng cấu hình một cơ chế không có nghĩa người đó phải được sử dụng mọi credential bên trong. Quyền cấu hình, quyền sử dụng, quyền phê duyệt và trách nhiệm nghiệp vụ cần được xem xét độc lập theo khả năng của nền tảng.

### 2.1. Liên kết không thay thế trách nhiệm cụ thể

Gán tài khoản cho một nhóm có 200 thành viên nhưng không có người đại diện hoặc quy trình xử lý yêu cầu có thể chỉ tạo ra cảm giác rằng đã có owner.

Một mô hình thực tế cần biết:

- Nhóm nào nhận trách nhiệm chính.
- Người hoặc vai trò nào đại diện cho nhóm tại thời điểm hiện tại.
- Cách liên hệ và thời gian xử lý theo yêu cầu của tổ chức.
- Ai thay thế khi đầu mối chính vắng mặt.
- Ai tiếp nhận khi nhóm tái cơ cấu hoặc ngừng hoạt động.

Không cần biến mọi thành viên thành chủ thể chịu trách nhiệm ngang nhau. Cần một cơ chế phân công rõ ràng và có thể vận hành.

## 3. Phân loại các quan hệ nhóm

Các tên dưới đây là mô hình minh họa để biểu diễn rõ ý nghĩa. Chúng không phải tập giá trị bắt buộc của mọi sản phẩm.

| Kiểu quan hệ | Trách nhiệm hoặc ý nghĩa | Không được tự suy ra |
|---|---|---|
| ACCOUNTABLE_OWNER | Chịu trách nhiệm về mục đích, nhu cầu quyền và vòng đời đối tượng | Có quyền đăng nhập hay đọc secret |
| TECHNICAL_CUSTODIAN | Thực hiện nhiệm vụ kỹ thuật được giao | Được quyết định mọi thay đổi nghiệp vụ |
| CREDENTIAL_CUSTODIAN | Vận hành lưu trữ, cấp phát hoặc rotation theo chính sách | Được sử dụng credential ngoài nhiệm vụ |
| ACCESS_REVIEWER | Tham gia rà soát quyền theo phạm vi | Có quyền phê duyệt mọi loại yêu cầu |
| REQUEST_APPROVER | Tham gia quyết định cho yêu cầu cụ thể | Được tự phê duyệt hoặc được cấp quyền tại đích |
| ACCESS_ENTITLEMENT | Nhóm có liên hệ với một cơ chế cấp quyền đã xác minh | Mọi thành viên luôn có quyền hoạt động |
| SUPPORT_CONTACT | Đầu mối tiếp nhận yêu cầu hỗ trợ | Là owner hoặc chủ thể được cấp đặc quyền |

Một liên kết ACCESS_ENTITLEMENT cần có tham chiếu tới chính sách hoặc điểm gán quyền thật. Nếu chỉ biết nhóm “có liên quan” mà chưa xác định được cách cấp quyền, lưu trạng thái chờ xác minh thay vì khẳng định quyền hiệu lực.

Một danh sách thư hoặc nhóm hỗ trợ có thể hữu ích làm đầu mối trách nhiệm. Tuy nhiên, nó không nhất thiết là nhóm bảo mật có thể dùng để xác thực hoặc phân quyền. Loại nhóm và nguồn quản lý phải được ghi đúng.

### 3.1. Tách vai trò chính và vai trò bổ trợ

Một tổ chức có thể quy định một nhóm owner chính cho mỗi tài khoản trong một phạm vi, kèm nhóm vận hành và đầu mối dự phòng. Đây là lựa chọn quản trị cần công bố, không phải quy luật kỹ thuật bắt buộc.

Nếu dùng quy tắc một owner chính, phải xác định rõ khóa phạm vi:

~~~text
Một owner chính cho:
  tài khoản cụ thể + môi trường + phạm vi trách nhiệm.
~~~

Một danh tính dùng chung cho nhiều dịch vụ có thể khiến trách nhiệm khó phân chia. Khi đó cần mô hình liên kết nhiều dịch vụ, xác định bên chịu trách nhiệm cuối cùng hoặc xem xét tách danh tính; không chỉ ghi nhiều nhóm owner mà không có quy tắc phối hợp.

### 3.2. Không dùng thứ tự danh sách làm ý nghĩa

Mẫu mơ hồ:

~~~yaml
associated_groups:
  - Payment-Service-Owners
  - PAM-Operations
  - Production-Reviewers
~~~

Không thể biết nhóm đầu tiên có phải owner chính hay không, nhóm nào được sử dụng tài khoản và liên kết đã được xác nhận chưa.

Mô hình rõ hơn là lưu từng quan hệ với vai trò và phạm vi. Thứ tự hiển thị có thể thay đổi mà không làm thay đổi ý nghĩa quản trị.

## 4. Định danh đúng đối tượng và nhóm

### 4.1. Định danh đối tượng inventory

Không dùng tên tài khoản làm khóa duy nhất. Ví dụ, tài khoản local-admin trên host-a và local-admin trên host-b là hai đối tượng khác nhau.

Một khóa khái niệm có thể gồm:

~~~text
account_key = authority_namespace + immutable_account_id
~~~

Nếu nguồn không có định danh bất biến phù hợp, cần khóa theo nguồn và phạm vi tài nguyên kèm cơ chế xử lý đổi tên, xóa và tạo lại. Phải ghi rõ giới hạn của cách nhận diện đó.

Với tài khoản dịch vụ, giữ tham chiếu tới workload hoặc ứng dụng sử dụng tài khoản. Với tài khoản quản trị cá nhân, giữ liên kết tới danh tính con người theo quy trình của tổ chức.

### 4.2. Định danh nhóm

Nhóm nên được tham chiếu bằng:

~~~text
group_key = group_authority_namespace + immutable_group_id
~~~

Kèm theo tên hiển thị để con người đọc, nhưng tên không là căn cứ duy nhất để đồng bộ.

Hai nhóm có cùng tên ở hai miền hoặc tenant không được tự động gộp. Nhóm bị xóa rồi tạo lại cùng tên cũng không mặc nhiên kế thừa trách nhiệm hoặc quyền của nhóm cũ.

### 4.3. Phạm vi của liên kết

Một nhóm có thể chịu trách nhiệm cho tài khoản ở môi trường thử nghiệm nhưng không phải ở sản xuất. Một nhóm vận hành có thể chỉ chịu trách nhiệm rotation, trong khi việc thay vai trò do nhóm khác quản lý.

Mỗi liên kết cần trả lời:

- Áp dụng cho đối tượng nào?
- Ở môi trường hoặc tài nguyên nào?
- Với nhiệm vụ gì?
- Trong khoảng thời gian nào?
- Theo nguồn và quyết định nào?

Không suy owner của tài khoản chỉ từ owner của máy chủ, người tạo tài khoản hoặc người đăng nhập gần nhất. Các dữ liệu đó là manh mối để xác minh; chúng chưa đủ để chuyển trách nhiệm.

## 5. Mô hình bản ghi liên kết có thể kiểm toán

### 5.1. Các trường cốt lõi

| Nhóm dữ liệu | Trường gợi ý | Mục đích |
|---|---|---|
| Định danh | relation_id, object_reference, group_reference | Phân biệt liên kết và hai đầu quan hệ |
| Ý nghĩa | relation_type, responsibility_scope | Tránh nhầm ownership với quyền sử dụng |
| Nguồn | source_system, source_record, source_version | Truy nguồn và xử lý mâu thuẫn |
| Trạng thái | proposed, verified, active, retiring, ended, unresolved | Theo dõi vòng đời thay vì chỉ có một cờ có/không |
| Thời gian | valid_from, valid_until, last_confirmed_at | Biết liên kết có hiệu lực lúc nào và còn mới không |
| Xác nhận | confirmed_by, decision_reference | Biết ai xác nhận theo thẩm quyền nào |
| Liên hệ | representative_reference, support_route | Đưa công việc đến đúng người hoặc vai trò |
| Độ đầy đủ | evidence_status, unresolved_reason | Không che giấu thiếu dữ liệu |

Tên trạng thái cần được thống nhất trong hệ thống. Nếu verified biểu thị “đã xác minh” còn active biểu thị “đang có hiệu lực”, phải biết hai khái niệm được kết hợp như thế nào; không dùng chúng thay thế tùy lúc.

Không phải mọi trường đều phải nằm trong cùng một bảng. Có thể tách bản ghi quan hệ, lịch sử xác nhận và tham chiếu chính sách, miễn vẫn liên kết được bằng định danh ổn định.

### 5.2. Ví dụ một liên kết owner

Mẫu sau là dữ liệu inventory minh họa, không phải cấu hình để nạp trực tiếp vào sản phẩm PAM:

~~~json
{
  "relation_id": "assoc-005-01",
  "object_reference": {
    "source": "identity-prod",
    "object_id": "acct-pay-deploy-18",
    "object_type": "service_account"
  },
  "group_reference": {
    "source": "directory-prod",
    "group_id": "group-payment-owners-31",
    "display_name": "Payment-Service-Owners"
  },
  "relation_type": "ACCOUNTABLE_OWNER",
  "responsibility_scope": {
    "environment": "production",
    "service_id": "payment-api",
    "duties": [
      "justify_account_purpose",
      "confirm_required_privileges",
      "coordinate_account_lifecycle"
    ]
  },
  "status": "active",
  "verification_status": "verified",
  "valid_from": "2026-11-26T09:00:00+07:00",
  "last_confirmed_at": "2026-11-26T09:00:00+07:00",
  "representative_reference": "role-payment-service-owner",
  "decision_reference": "ownership-decision-204",
  "source_record": "service-registry/payment-api/ownership",
  "source_version": "revision-12"
}
~~~

Liên kết này xác định trách nhiệm; nó chưa chứa quyết định cho phép ai sử dụng credential. Nếu một quy trình cấp quyền sử dụng dữ liệu owner để chọn người duyệt, cần có cấu hình và kiểm soát riêng cho quy trình đó.

### 5.3. Liên kết tới chính sách truy cập phải tường minh

Đối với ACCESS_ENTITLEMENT, nên giữ thêm:

- Policy ID hoặc assignment ID.
- Phạm vi tài nguyên và tập thao tác.
- Cơ chế kích hoạt, thời hạn hoặc điều kiện nếu có.
- Nguồn xác nhận quan hệ giữa nhóm và chính sách.
- Thời điểm đánh giá và giới hạn của bằng chứng.

Ví dụ, nhóm Deploy-Operators có thể đủ điều kiện yêu cầu một phiên JIT để sửa một deployment. Điều đó khác với quyền thường trực đọc mật khẩu tài khoản triển khai.

Không ghi “nhóm có access” nếu chưa rõ access là được xem bản ghi inventory, được gửi yêu cầu, được kích hoạt grant, được mở phiên hay được đọc secret.

## 6. Nguồn dữ liệu và quy tắc đối soát

### 6.1. Mỗi nguồn có thể đáng tin cậy cho một loại thông tin

| Nguồn | Thông tin thường cần xác minh tại nguồn đó |
|---|---|
| Nguồn danh tính | Nhóm có tồn tại, định danh, loại nhóm và thành viên |
| Danh mục dịch vụ | Dịch vụ, đơn vị chịu trách nhiệm và đầu mối vận hành |
| Hệ thống PAM hoặc vault | Chính sách sử dụng credential, vai trò và cấu hình liên quan |
| Tài nguyên đích | Quyền thực tế được gán hoặc thực thi tại đích |
| Quy trình thay đổi hoặc xác nhận ownership | Ai đã chấp nhận trách nhiệm, phạm vi và thời điểm |
| Hệ thống nhân sự hoặc tổ chức theo thẩm quyền | Trạng thái tổ chức hoặc người đại diện khi cần |

Việc nguồn danh tính xác nhận nhóm tồn tại không chứng minh nhóm chấp nhận ownership. Ngược lại, một bản ghi owner trong danh mục dịch vụ chưa chứng minh nhóm có quyền truy cập ở máy chủ.

Nên quy định nguồn có thẩm quyền theo từng thuộc tính. Không dùng một quy tắc “nguồn nào cập nhật sau cùng thì thắng” cho mọi loại dữ liệu.

### 6.2. Khi dữ liệu mâu thuẫn

Ví dụ, danh mục dịch vụ nói Payment-Service-Owners là owner, còn bản ghi cũ trong vault ghi Legacy-Payment-Team.

Quy trình xử lý nên:

1. Giữ cả hai giá trị cùng nguồn và thời điểm quan sát.
2. Xác định chúng nói về cùng đối tượng, cùng môi trường và cùng trách nhiệm hay không.
3. Đối chiếu quyết định ownership có thẩm quyền.
4. Yêu cầu xác minh theo quy trình đã thiết kế nếu mâu thuẫn chưa giải quyết được.
5. Ghi kết luận, lý do và thời điểm cập nhật; giữ lịch sử cũ.

Có thể hai nhóm đang thực hiện hai vai trò khác nhau, không thực sự mâu thuẫn. Nếu một nhóm là owner nghiệp vụ và nhóm kia vận hành vault, nên biểu diễn hai quan hệ thay vì chọn một nhóm rồi xóa thông tin còn lại.

### 6.3. Không tự chuyển thông tin suy đoán thành trách nhiệm

Những tín hiệu sau chỉ nên tạo ứng viên xác minh:

- Tên tài khoản chứa tiền tố giống tên đội.
- Người tạo tài khoản là thành viên một nhóm.
- Nhóm đăng nhập gần đây nhất.
- Nhóm sở hữu máy chủ nơi tài khoản được tìm thấy.
- Nhóm nằm trong một mô tả tự do hoặc tag do người dùng nhập.

Tên, tag và mô tả có thể sai hoặc bị thay đổi. Nếu thông tin này được dùng để tự động chọn người duyệt hoặc cấp quyền, sai lệch metadata có thể ảnh hưởng đến kiểm soát truy cập.

Ứng viên chưa xác nhận nên có trạng thái proposed hoặc unresolved. Không hiển thị nó như ownership đã có hiệu lực.

## 7. Quy trình thiết lập associated group

### Bước 1: Nhận diện đúng đối tượng

Xác minh account ID, nguồn quản lý, tài nguyên và môi trường. Tránh liên kết nhầm hai tài khoản cùng tên hoặc hai nhóm cùng tên.

Giữ rõ đối tượng được giao ownership là tài khoản, credential, tài nguyên hay dịch vụ. Owner của dịch vụ có thể liên quan tới tài khoản, nhưng sự liên hệ cần được xác nhận theo phạm vi quản trị.

### Bước 2: Chọn loại quan hệ

Xác định cần nhóm chịu trách nhiệm, nhóm kỹ thuật, nhóm rà soát hay nhóm tham gia cấp quyền. Nếu chưa biết mục đích, chưa nên tạo một liên kết chung không có kiểu.

Phạm vi nhiệm vụ phải đủ cụ thể để xử lý câu hỏi thực tế: ai xác nhận quyền vẫn cần, ai phối hợp rotation, ai xử lý account bị nghi lộ credential.

### Bước 3: Xác minh nhóm và khả năng vận hành

Kiểm tra nhóm tồn tại, đúng nguồn, đúng loại và có đầu mối chịu trách nhiệm. Nếu nhóm có trạng thái ngừng hoạt động, không đủ người xử lý hoặc không có đường liên hệ, liên kết có thể chưa đáp ứng yêu cầu vận hành.

Không nhất thiết nhóm owner phải là nhóm có quyền bảo mật. Nhưng nếu dùng nó trong chính sách truy cập hoặc phê duyệt tự động, cần xác minh nó phù hợp với cơ chế đó.

### Bước 4: Xác nhận trách nhiệm và thẩm quyền

Bên xác nhận phải có thẩm quyền đối với loại quan hệ được tạo. Với owner, cần bằng chứng nhóm tiếp nhận trách nhiệm và phạm vi liên quan.

Việc tự gán mình làm owner không nên tự tạo quyền duyệt hoặc quyền đọc credential. Nếu hệ thống có liên kết giữa ownership và workflow, phải kiểm tra ai được thay đổi liên kết và cách ngăn thao tác đó trở thành đường tăng quyền.

### Bước 5: Ghi liên kết và giới hạn tác động

Lưu quan hệ, bằng chứng, thời điểm và trạng thái. Nếu việc ghi inventory có thể kích hoạt đồng bộ chính sách, phải có luồng rõ ràng: đề xuất, xác minh, áp dụng theo cơ chế có thẩm quyền và đối soát kết quả.

Không giả định rằng cập nhật một dòng inventory đã hoàn thành thay đổi ở mọi hệ thống liên quan. Giữ trạng thái metadata và trạng thái áp dụng chính sách riêng khi có độ trễ hoặc lỗi.

### Bước 6: Kiểm tra khả năng sử dụng trong quy trình

Xác nhận yêu cầu được gửi tới đúng nhóm, đầu mối tiếp nhận còn hoạt động và các vai trò không bị hiểu nhầm. Đối chiếu rằng liên kết owner không vô tình trở thành quyền sử dụng tài khoản.

Nếu không hoàn tất được, ghi vấn đề cụ thể và người xử lý; không đánh dấu “đã có owner hợp lệ” chỉ vì trường tên nhóm không còn rỗng.

## 8. Vòng đời và thay đổi nhóm liên kết

~~~mermaid
stateDiagram-v2
    [*] --> Proposed
    Proposed --> Verified: Đủ bằng chứng và được xác nhận
    Proposed --> Unresolved: Thiếu dữ liệu hoặc có mâu thuẫn
    Verified --> Active: Đến thời điểm có hiệu lực
    Active --> ReviewRequired: Có thay đổi cần rà soát
    ReviewRequired --> Active: Xác nhận lại còn phù hợp
    Active --> Retiring: Chuẩn bị chuyển trách nhiệm
    Retiring --> Ended: Hoàn tất bàn giao và kết thúc
    Unresolved --> Proposed: Bổ sung dữ liệu
    Ended --> [*]
~~~

Đây là mô hình quản lý quan hệ, không phải vòng đời đăng nhập hoặc trạng thái bật/tắt tài khoản. Việc quan hệ chuyển sang ReviewRequired không tự có nghĩa tài khoản đã mất quyền tại đích.

### 8.1. Nhóm đổi tên

Nếu group ID và nguồn quản lý không đổi, đổi tên hiển thị thường không cần tạo một quan hệ ownership mới. Cập nhật tên và giữ dấu vết thay đổi theo cơ chế của nguồn.

Tuy nhiên, đổi tên có thể đi cùng tái cơ cấu hoặc thay mục đích. Khi đó vẫn cần xác minh trách nhiệm, không chỉ đồng bộ chuỗi tên mới.

### 8.2. Nhóm bị xóa rồi tạo lại

Nhóm mới cùng tên nhưng khác định danh là một đối tượng mới. Không tự gắn lại các quan hệ owner hoặc policy cũ chỉ bằng tên.

Quan hệ cũ nên giữ bằng chứng lịch sử và trạng thái không còn phân giải hoặc đã kết thúc theo xác nhận. Quan hệ mới cần được thiết lập theo quy trình phù hợp.

### 8.3. Nhóm không còn thành viên hoặc đầu mối

Một nhóm rỗng có thể không đáp ứng khả năng tiếp nhận công việc, nhưng phải xác minh nguồn đã đọc đầy đủ. Không kết luận rỗng khi truy vấn lỗi hoặc không đủ quyền xem thành viên.

Nhóm có thành viên cũng chưa chắc có người chịu trách nhiệm trực ca hay người đủ thẩm quyền xác nhận thay đổi. Cần kiểm tra theo nhiệm vụ của quan hệ, không chỉ số lượng thành viên.

Nếu đây là nhóm owner của tài khoản quan trọng, tạo vấn đề cần xử lý và đường chuyển cấp. Không tự vô hiệu hóa tài khoản dịch vụ chỉ vì nhóm owner tạm thời không đủ thông tin.

### 8.4. Chuyển ownership giữa hai đội

Một lần bàn giao cần làm rõ:

1. Nhóm cũ và nhóm mới, định danh và phạm vi.
2. Thời điểm chuyển trách nhiệm có hiệu lực.
3. Tài khoản, credential, job và tài nguyên liên quan.
4. Trách nhiệm xử lý yêu cầu đang mở hoặc sự cố đang diễn ra.
5. Bằng chứng bên mới tiếp nhận và bên có thẩm quyền xác nhận.
6. Những thay đổi chính sách truy cập phải thực hiện riêng, nếu có.

Có thể có giai đoạn phối hợp hai nhóm. Nếu quy tắc yêu cầu một owner chính, cần ghi ai là owner chính trong từng khoảng thời gian; không để hai dòng active mâu thuẫn mà không có ý nghĩa rõ ràng.

Đừng mặc định bàn giao ownership phải cấp cho nhóm mới mọi quyền của nhóm cũ. Trước khi chuyển quyền, đối chiếu nhu cầu công việc và least privilege.

### 8.5. Thay đổi thành viên của nhóm

Nếu nhóm được dùng cho cấp quyền hoặc phê duyệt, thay đổi thành viên có thể làm thay đổi ai được thực hiện các hành động đó. Tác động phụ thuộc chính sách và cơ chế thành viên của nền tảng.

Với nhóm chỉ phục vụ trách nhiệm inventory, thay đổi thành viên vẫn có thể làm đầu mối vận hành không còn phù hợp. Hai loại tác động nên được theo dõi riêng.

Nested group, nhóm động và thành viên bên ngoài có thể khiến danh sách người thực sự tham gia phức tạp hơn thành viên trực tiếp. Khi kết luận về người có quyền, cần kiểm kê đúng ngữ nghĩa đó; một liên kết group ID trong inventory chưa đủ.

## 9. Ví dụ xuyên suốt: svc-pay-deploy

### 9.1. Tình huống

svc-pay-deploy phục vụ pipeline triển khai payment-api ở production. Tài khoản cần cập nhật một deployment cụ thể; không có nhu cầu quản trị toàn cụm hoặc cho mọi thành viên đội ứng dụng xem credential.

Inventory cần thể hiện các quan hệ:

| Nhóm | Vai trò liên kết | Phạm vi |
|---|---|---|
| Payment-Service-Owners | ACCOUNTABLE_OWNER | Mục đích tài khoản, nhu cầu quyền và vòng đời |
| PAM-Credential-Operations | CREDENTIAL_CUSTODIAN | Vận hành lưu trữ và rotation theo cơ chế được giao |
| Production-Access-Reviewers | ACCESS_REVIEWER | Rà soát quyền production của tài khoản |
| Deployment-Workload-Operators | ACCESS_ENTITLEMENT | Liên kết tới chính sách đã xác minh cho công việc triển khai |

Một nhóm có thể không trực tiếp thực hiện mọi thao tác của vai trò liên kết. Ví dụ, credential có thể được cấp cho workload bằng cơ chế tự động; nhóm custodian chịu trách nhiệm vận hành cơ chế đó.

### 9.2. Tách đường trách nhiệm và đường sử dụng

~~~mermaid
flowchart LR
    O["Payment-Service-Owners"] -->|chịu trách nhiệm| A["Inventory: svc-pay-deploy"]
    C["PAM-Credential-Operations"] -->|vận hành credential| A
    R["Production-Access-Reviewers"] -->|rà soát quyền| A
    A -->|tham chiếu| P["Chính sách triển khai đã xác minh"]
    W["Workload đã xác thực"] -->|yêu cầu grant theo chính sách| P
    P -->|giới hạn phạm vi và thời hạn| T["Deployment payment-api"]
~~~

Sơ đồ không biểu thị nhóm owner được đọc secret. Nếu trong thực tế có quyền đó, phải ghi bằng chính sách và bằng chứng riêng.

### 9.3. Yêu cầu rotation

Khi cần luân chuyển credential, liên kết nhóm giúp xác định:

- Nhóm custodian vận hành quy trình rotation.
- Nhóm owner phối hợp xác nhận nơi sử dụng và yêu cầu sẵn sàng của dịch vụ.
- Workload hoặc pipeline nào cần cập nhật tham chiếu credential.
- Ai theo dõi kết quả và xử lý lỗi.

Associated group không tự chứng minh tài khoản đã sẵn sàng rotation. Còn cần kiểm kê consumer, phương thức nhận credential, khả năng cập nhật và cách xử lý khi thay đổi chưa đồng bộ.

Không đưa credential vào nội dung bàn giao ownership hoặc thông báo công việc. Dùng tham chiếu tới đối tượng được quản lý và kênh cấp phát phù hợp.

### 9.4. Yêu cầu truy cập khẩn cấp

Một người thuộc Payment-Service-Owners yêu cầu mở phiên quản trị để xử lý sự cố. Hệ thống không nên cho phép chỉ vì người đó thuộc nhóm owner.

Cần đánh giá chính sách truy cập khẩn cấp, danh tính, phạm vi thao tác, thời hạn và các điều kiện liên quan. Nếu người đó được phân công phê duyệt, vẫn cần xử lý xung đột khi họ chính là người yêu cầu.

Khi cơ chế khẩn cấp phải dùng quyền rộng hơn bình thường, ghi lại phần bảo đảm giảm đi, cảnh báo và hoạt động rà soát sau sự kiện theo thiết kế của tổ chức.

### 9.5. Kết quả mong đợi

Từ một bản ghi inventory, người vận hành có thể trả lời:

~~~text
Ai chịu trách nhiệm về tài khoản?
Ai phối hợp khi credential gặp vấn đề?
Ai rà soát nhu cầu quyền?
Chính sách nào cho phép sử dụng tài khoản hoặc grant?
Phạm vi đó được xác nhận lần cuối khi nào?
Còn liên kết nào chưa được xác minh?
~~~

Không thể chỉ từ danh sách nhóm liên kết mà kết luận toàn bộ quyền hiệu lực của svc-pay-deploy. Cần đối chiếu quyền ở tài nguyên, đường thành viên, quyền kế thừa và grant đang hoạt động nếu liên quan.

## 10. Tự động hóa đồng bộ một cách có kiểm soát

### 10.1. Tách phát hiện, đề xuất và áp dụng

Một luồng khái niệm:

~~~text
read_authoritative_records()
    → normalize_object_and_group_identifiers()
    → compare_typed_relationships()
    → classify_new_changed_missing_conflicting()
    → create_proposal_or_apply_authorized_update()
    → read_back_and_reconcile()
    → preserve_decision_and_evidence()
~~~

Không dùng một chuỗi đồng bộ chung để biến mọi nhãn nhóm mới phát hiện thành quyền truy cập. Loại cập nhật được phép tự động phải được xác định theo vai trò, nguồn và phạm vi.

Ví dụ, cập nhật tên hiển thị từ nguồn nhóm có thẩm quyền khác với đổi nhóm owner. Đổi nhóm owner lại khác với thay nhóm được quyền đọc credential.

### 10.2. Pseudocode xử lý một ứng viên

~~~text
process_candidate(candidate):
    object = resolve_inventory_object(candidate.object_key)
    group = resolve_authoritative_group(candidate.group_key)

    if object is unresolved or group is unresolved:
        record_unresolved(candidate)
        return

    if candidate.relation_type is not recognized:
        record_validation_error(candidate)
        return

    evidence = verify_source_and_responsibility(candidate)

    if evidence is incomplete or conflicting:
        preserve_as_proposal(candidate, evidence)
        return

    if creates_primary_owner_conflict(candidate):
        route_for_conflict_resolution(candidate)
        return

    if candidate.affects_access_or_approval_policy:
        route_to_authorized_policy_change(candidate)
        return

    apply_metadata_update_if_authorized(candidate, evidence)
    verify_saved_relationship(candidate)
    append_audit_event(candidate, evidence)
~~~

Đoạn này chỉ mô tả luồng thiết kế. Các hàm như verify_source_and_responsibility phải kiểm tra bằng chứng và thẩm quyền thực sự; không được thay bằng phép kiểm tra “có tên nhóm là đủ”.

Một liên kết owner tuy là metadata vẫn có thể ảnh hưởng việc chọn người duyệt hoặc chuyển giao công việc. Hệ thống phải biết các phụ thuộc đó khi phân loại tác động.

### 10.3. Tính lặp lại và xử lý lỗi

Đồng bộ cùng một dữ liệu không nên tạo nhiều liên kết active trùng nhau. Khóa chống trùng thường cần đối tượng, group ID, kiểu quan hệ, phạm vi và khoảng hiệu lực phù hợp.

Nếu cập nhật inventory thành công nhưng cập nhật workflow thất bại, không báo đồng bộ toàn bộ đã hoàn tất. Giữ trạng thái lệch, bằng chứng và tác vụ xử lý.

Nếu một nguồn tạm thời không đọc được, không xóa hàng loạt liên kết hiện có như thể chúng đã chấm dứt. Cần phân biệt “không còn tồn tại đã xác nhận” và “chưa quan sát lại được”.

## 11. Rà soát định kỳ và chất lượng inventory

### 11.1. Những gì cần xác nhận lại

Rà soát không chỉ là hỏi nhóm còn tồn tại hay không. Với mỗi quan hệ quan trọng, cần xác nhận:

1. Đúng đối tượng, nguồn danh tính và môi trường.
2. Đúng loại trách nhiệm hoặc chính sách được liên kết.
3. Nhóm còn nhận nhiệm vụ và có đầu mối vận hành.
4. Phạm vi còn phù hợp với mục đích tài khoản.
5. Không có xung đột owner chính hoặc chồng vai trò chưa xử lý.
6. Bằng chứng còn đủ mới theo mức độ quan trọng của đối tượng.
7. Các hệ thống phụ thuộc đang phản ánh cùng trạng thái đã được xác nhận.

Chu kỳ rà soát phụ thuộc mức độ nhạy cảm, tần suất thay đổi và quy trình tổ chức. Không có một khoảng thời gian chung phù hợp cho mọi tài khoản.

Ngoài lịch định kỳ, nên kích hoạt rà soát khi có sự kiện như bàn giao dịch vụ, tái cơ cấu đội, xóa nhóm, thay đầu mối, phát hiện quyền rộng hoặc sự cố credential.

### 11.2. Phân loại vấn đề cụ thể

| Trạng thái vấn đề | Ý nghĩa |
|---|---|
| Missing association | Chưa có quan hệ cần thiết theo chính sách inventory |
| Unverified association | Có dữ liệu liên kết nhưng chưa đủ bằng chứng |
| Unresolved group | Không phân giải được nhóm hoặc chưa đọc được nguồn |
| Ownership conflict | Nhiều khai báo trách nhiệm mâu thuẫn trong cùng phạm vi |
| Unreachable responsibility | Có tên nhóm nhưng không có đường tiếp nhận công việc phù hợp |
| Stale confirmation | Lần xác nhận đã quá cũ theo yêu cầu áp dụng |
| Policy mismatch | Liên kết và cấu hình truy cập hoặc workflow không thống nhất |

Không gộp tất cả thành “orphan account”. Một tài khoản không có owner đã xác minh khác với tài khoản có owner nhưng nguồn nhóm đang lỗi. Mỗi loại vấn đề cần cách xử lý khác nhau.

Một tài khoản không có chủ sở hữu rõ ràng cũng chưa đủ căn cứ kết luận không còn sử dụng. Cần kiểm kê hoạt động và phụ thuộc trước khi thay đổi vòng đời tài khoản.

### 11.3. Chỉ số nên theo dõi

| Chỉ số | Cách hiểu |
|---|---|
| Tỷ lệ tài khoản đặc quyền có owner đã xác minh | Chỉ tính những bản ghi đáp ứng tiêu chí bằng chứng và phạm vi |
| Tỷ lệ liên kết phân giải được bằng định danh ổn định | Đo chất lượng liên kết tới nguồn nhóm |
| Số vấn đề owner mâu thuẫn hoặc thiếu đầu mối | Phản ánh khả năng vận hành trách nhiệm |
| Tỷ lệ lần rà soát hoàn tất đúng yêu cầu | Đo việc xác nhận lại, không chỉ việc gửi yêu cầu |
| Thời gian xử lý bàn giao | Từ lúc phát sinh thay đổi tới lúc trách nhiệm mới có hiệu lực và được đối soát |
| Số chênh lệch giữa inventory và chính sách | Làm rõ những trường hợp dữ liệu và cấu hình không thống nhất |

Nêu rõ mẫu số và phạm vi. Nếu chưa kiểm kê đủ tài khoản đặc quyền, tỷ lệ owner đầy đủ trong tập đã biết không chứng minh toàn bộ hệ thống đã được bao phủ.

Việc một nhóm có nhiều thành viên không tự làm tăng chất lượng ownership. Chỉ số cần phản ánh trách nhiệm có thể thực thi, không khuyến khích gán tài khoản vào nhóm lớn cho đủ trường dữ liệu.

## 12. Bằng chứng kiểm toán và điều tra sự cố

### 12.1. Giữ lịch sử thay vì chỉ trạng thái cuối

Mỗi lần tạo, sửa hoặc kết thúc quan hệ nên có:

- Giá trị trước và sau theo định danh.
- Loại quan hệ và phạm vi bị tác động.
- Chủ thể thực hiện và chủ thể xác nhận nếu có.
- Lý do, quyết định hoặc hồ sơ tham chiếu.
- Thời điểm có hiệu lực và thời điểm ghi nhận.
- Kết quả đối soát với hệ thống phụ thuộc.
- Ngoại lệ hoặc phần chưa hoàn tất.

Phân biệt thời điểm có hiệu lực với thời điểm nhập dữ liệu. Một lần bàn giao được nhập muộn không nên làm mất khả năng xác định ai chịu trách nhiệm vào thời điểm xảy ra sự cố.

Lịch sử thay đổi thành viên nhóm cũng có thể cần thiết khi điều tra ai được phê duyệt hoặc sử dụng quyền trong quá khứ. Thành viên hiện tại không đủ để tái hiện thành viên ở thời điểm trước.

### 12.2. Khi credential bị nghi lộ

Associated group hỗ trợ tìm đúng bên phối hợp, nhưng cần đi cùng bằng chứng kỹ thuật:

~~~text
Bản ghi tài khoản
  → nhóm owner và nhóm custodian tại thời điểm sự cố
  → consumer hoặc workload sử dụng
  → credential hoặc grant liên quan
  → phiên và tài nguyên đã truy cập
  → hoạt động ứng phó và kết quả
~~~

Nhóm owner giúp xác định nhu cầu và ảnh hưởng nghiệp vụ. Nhóm custodian hỗ trợ thao tác theo cơ chế được giao. Người chỉ có vai trò nhận thông báo không tự trở thành người có thẩm quyền thu hồi, rotation hoặc truy cập secret.

Trong quy trình ứng phó khẩn cấp đã thiết kế, cần có đường thực hiện phù hợp khi nhóm owner không phản hồi. Khoảng trống liên hệ không nên dẫn đến việc chia sẻ credential qua kênh không được kiểm soát.

### 12.3. Bảo vệ chính dữ liệu liên kết

Người có thể sửa associated group có thể gây tác động đáng kể nếu trường đó được dùng để chọn người duyệt hoặc xác định phạm vi quản lý.

Cần kiểm soát:

- Ai được đề xuất, xác nhận và áp dụng thay đổi.
- Những trường nào chỉ nhận dữ liệu từ nguồn có thẩm quyền.
- Những thay đổi nào cần đối soát với chính sách.
- Cách phát hiện tự gán ownership hoặc sửa đầu mối bất thường.
- Quyền xem và xuất cấu trúc nhóm, tài khoản và trách nhiệm.

Bản ghi inventory không nên chứa mật khẩu, token hoặc private key. Liên kết tới đối tượng credential được quản lý là đủ cho mục đích kiểm kê và truy vết khi hệ thống hỗ trợ.

## 13. Những lỗi thường gặp

| Lỗi | Hậu quả | Cách xử lý |
|---|---|---|
| Chỉ lưu tên nhóm | Nhầm nhóm giữa nguồn hoặc sau khi tạo lại | Dùng định danh ổn định kèm nguồn |
| Một trường nhóm cho mọi mục đích | Không biết ai chịu trách nhiệm và ai có quyền | Tách kiểu quan hệ và phạm vi |
| Đồng nhất owner với người được sử dụng credential | Tạo quyền rộng hoặc gây hiểu nhầm | Đối chiếu chính sách truy cập riêng |
| Gán nhóm nhưng không có người đại diện | Yêu cầu không được xử lý | Xác minh khả năng vận hành trách nhiệm |
| Lấy người đăng nhập gần nhất làm owner | Gán trách nhiệm sai | Dùng tín hiệu đó làm ứng viên xác minh |
| Đồng bộ tên nhóm thành quyền tự động | Metadata có thể tạo đường tăng quyền | Tách đề xuất và luồng thay đổi chính sách |
| Nhóm bị xóa được nối lại theo tên | Chuyển trách nhiệm hoặc quyền sang đối tượng mới | Xác minh lại bằng group ID |
| Lỗi nguồn bị hiểu thành nhóm không còn tồn tại | Xóa liên kết hoặc tác động dịch vụ sai | Giữ trạng thái chưa xác định |
| Thêm owner mới nhưng không kết thúc owner cũ | Mâu thuẫn trách nhiệm | Quản lý khoảng hiệu lực và bàn giao |
| Xóa liên kết là coi đã thu hồi quyền | Quyền ở PAM hoặc tài nguyên vẫn còn | Đối soát chính sách, grant và phiên liên quan |

## 14. Bài tập áp dụng

Inventory có tài khoản svc-backup-prod với dữ liệu:

~~~text
Owner group được ghi theo tên: Infrastructure-Team
Nhóm vận hành vault: PAM-Custodians
Nhóm rà soát quyền: Production-Reviewers
Tài khoản được sử dụng bởi hai job backup ở production.
Nhóm Infrastructure-Team cũ đã bị xóa.
Một nhóm mới cùng tên vừa được tạo ở cùng nguồn.
Chưa có bằng chứng nhóm mới tiếp nhận trách nhiệm.
~~~

Hãy thiết kế cách xử lý:

1. Những liên kết nào có thể giữ nguyên và cần kiểm tra thêm?
2. Vì sao không tự chuyển owner sang nhóm mới cùng tên?
3. Cần bằng chứng nào để xác nhận ownership mới?
4. Làm thế nào duy trì xử lý sự cố trong thời gian chưa có owner hợp lệ?
5. Có nên vô hiệu hóa svc-backup-prod ngay chỉ vì vấn đề owner?
6. Nếu nhóm owner mới cần sử dụng tài khoản, còn phải đánh giá những gì?

Hướng phân tích:

- Quan hệ owner cũ cần được ghi nhận theo định danh và trạng thái lịch sử, không xóa dấu vết.
- Nhóm mới là đối tượng mới; cần xác nhận phạm vi trách nhiệm và thẩm quyền.
- Các liên kết custodian và reviewer không tự mất hiệu lực chỉ vì owner thay đổi, nhưng cần đối soát tính phù hợp.
- Hai job backup là phụ thuộc quan trọng trước khi thay đổi vòng đời tài khoản hoặc credential.
- Cần đầu mối tạm thời hoặc đường chuyển cấp theo quy trình đã định, với trách nhiệm và thời hạn rõ ràng.
- Quyền sử dụng tài khoản của nhóm mới phải được đánh giá riêng theo nhu cầu, least privilege và JIT/JEA nếu phù hợp.

Có thể mở rộng bài tập bằng việc cho hai nhóm cùng khai báo owner chính ở cùng phạm vi. Hãy chỉ ra cách giữ bằng chứng, giải quyết mâu thuẫn và xác định thời điểm chuyển trách nhiệm mà không tự cấp quyền truy cập.

## 15. Ghi nhớ

Associated group là liên kết có ý nghĩa giữa đối tượng inventory và một nhóm, phục vụ một trách nhiệm hoặc một quan hệ chính sách xác định. Chất lượng của liên kết nằm ở định danh, vai trò, phạm vi, bằng chứng và khả năng vận hành.

Trong PAM, biết nhóm nào “liên quan” chưa đủ. Cần biết ai chịu trách nhiệm, ai làm công việc kỹ thuật, ai được phê duyệt và ai có quyền sử dụng theo chính sách thực tế. Tách rõ các câu hỏi đó giúp quản lý tài khoản đặc quyền, credential và phiên truy cập một cách có thể kiểm toán.
