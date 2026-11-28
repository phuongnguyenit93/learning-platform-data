# RACI cho PAM

Trong quản lý truy cập đặc quyền (Privileged Access Management — PAM), một sự cố vận hành có thể bắt đầu từ khoảng trống trách nhiệm: đội PAM cho rằng chủ ứng dụng phải xác nhận quyền, chủ ứng dụng nghĩ đội bảo mật đã kiểm tra, còn tài khoản quản trị vẫn tồn tại mà không ai quyết định có nên giữ lại.

**RACI** giúp làm rõ ai thực hiện, ai chịu trách nhiệm cuối cùng, ai cần được tham vấn và ai cần được thông báo cho từng hoạt động. Với PAM, ma trận này cần nối được việc kiểm kê tài khoản, xác nhận ownership, cấp quyền tối thiểu, JIT/JEA, quản lý vault, luân chuyển credential, giám sát phiên, kiểm toán và ứng phó sự cố.

Bài học thuộc chương **Governance**, tập trung vào tài khoản quản trị, tài khoản dịch vụ và hạ tầng nhạy cảm. Các vai trò và ma trận bên dưới là mẫu thiết kế để điều chỉnh theo tổ chức, không phải một cơ cấu trách nhiệm bắt buộc hoặc cấu hình của sản phẩm PAM.

## 1. Kết quả cần đạt

Sau bài học, bạn có thể:

- Diễn giải đúng bốn thành phần R, A, C, I và phân biệt trách nhiệm với quyền truy cập kỹ thuật.
- Chia một quy trình PAM thành các hoạt động có đầu ra đủ rõ để phân công.
- Lập ma trận có một đầu mối A cho mỗi hoạt động, không bỏ trống người thực hiện.
- Xử lý trường hợp một người giữ nhiều vai trò, người phê duyệt vắng mặt hoặc owner không còn hợp lệ.
- Liên kết RACI với workflow, bằng chứng và đường escalation trong vận hành thực tế.

## 2. Hiểu đúng R, A, C và I

| Ký hiệu | Ý nghĩa | Câu hỏi cần trả lời |
| --- | --- | --- |
| R — Responsible | Người hoặc đội trực tiếp thực hiện công việc | Ai tạo ra đầu ra hoặc thực hiện hành động? |
| A — Accountable | Đầu mối chịu trách nhiệm cuối cùng về kết quả của hoạt động | Ai phải bảo đảm công việc được hoàn tất đúng và xử lý khi không đạt? |
| C — Consulted | Bên được tham vấn trước hoặc trong quá trình ra quyết định | Cần ý kiến của ai để làm đúng và hiểu tác động? |
| I — Informed | Bên được thông báo về quyết định hoặc kết quả | Ai cần biết để phối hợp hoặc theo dõi? |

Trong mô hình của bài học, **mỗi hoạt động có đúng một A và ít nhất một R**. Có thể có nhiều R khi công việc cần nhiều bên, nhưng phải ghi rõ phần việc và điểm bàn giao. Một vai trò có thể đồng thời là A và R nếu không vi phạm yêu cầu phân tách nhiệm vụ.

C là trao đổi hai chiều để lấy ý kiến cần thiết. I chủ yếu là thông báo; được đưa vào danh sách nhận thông báo không tạo ra quyền phủ quyết hoặc thẩm quyền phê duyệt.

### 2.1. A không đồng nghĩa có mọi quyền kỹ thuật

Một resource owner có thể chịu trách nhiệm quyết định phạm vi truy cập nhưng không cần biết mật khẩu quản trị. Account owner có thể chịu trách nhiệm nhu cầu tài khoản nhưng không được tự phê duyệt yêu cầu đặc quyền của chính mình.

RACI mô tả trách nhiệm tổ chức. Quyền gọi API, đọc secret, sửa policy hoặc mở phiên phải được quản lý riêng bằng cơ chế phân quyền, xác thực và phê duyệt phù hợp.

```text
RACI: ai chịu trách nhiệm cho hoạt động?
Phân quyền: ai được thực hiện thao tác trên hệ thống?
Workflow: yêu cầu đi qua những quyết định và bước nào?
Evidence: điều gì chứng minh quyết định và hành động đã xảy ra?
```

Bốn lớp cần khớp nhau. Việc sửa một ô trong ma trận không tự thay đổi cấu hình quyền trên hệ thống đích.

### 2.2. Một A không có nghĩa bỏ qua mọi thẩm quyền khác

Nếu một yêu cầu gồm quyết định nhu cầu tài khoản, quyết định quyền trên tài nguyên và chấp nhận ngoại lệ rủi ro, đó là các hoạt động khác nhau. Mỗi hoạt động cần A riêng đúng thẩm quyền.

Không nên ghép cả quy trình thành một hàng rồi chỉ định nhiều A để thể hiện rằng nhiều bên cùng tham gia. Cách đó làm mất ranh giới quyết định. Hãy tách hoạt động và mô tả điều kiện để bước sau được phép bắt đầu.

## 3. Chọn đúng vai trò trước khi lập ma trận

Các ký hiệu sau dùng nhất quán trong bài. Khi áp dụng, cần ánh xạ chúng tới đơn vị và người có thẩm quyền thực tế.

| Ký hiệu | Vai trò | Phạm vi chính |
| --- | --- | --- |
| GOV | Chủ sở hữu chương trình/chính sách PAM | Phạm vi chương trình, quy tắc trách nhiệm và điều phối các khoảng trống |
| AO | Account owner | Mục đích, nhu cầu tồn tại và vòng đời tài khoản |
| RO | Resource owner | Điều kiện và phạm vi tác động lên tài nguyên |
| TECH | Technical owner/đội vận hành dịch vụ | Phụ thuộc ứng dụng, tính đúng kỹ thuật và khôi phục dịch vụ |
| OPS | Đội vận hành IAM/PAM | Thực thi quản lý tài khoản, vault, phiên và cơ chế cấp/thu hồi được giao |
| SEC | Đội bảo mật/giám sát | Phân tích rủi ro, giám sát và hỗ trợ xử lý bất thường |
| REQ | Người hoặc chủ thể yêu cầu | Cung cấp nhu cầu và thực hiện công việc trong phạm vi được cấp |
| APP | Người phê duyệt được ủy quyền | Quyết định truy cập trong phạm vi ủy quyền của RO hoặc chính sách tương ứng |
| IC | Người điều phối sự cố được chỉ định | Điều phối quyết định và phối hợp theo quy trình ứng phó |
| RISK | Người có thẩm quyền chấp nhận rủi ro | Quyết định ngoại lệ trong phạm vi được tổ chức giao |
| REV | Bên xem xét/đánh giá độc lập | Kiểm tra bằng chứng và kết luận với mức độc lập phù hợp |

Không mặc định OPS là owner nghiệp vụ của mọi tài khoản trong vault. Không mặc định SEC có quyền chấp nhận mọi rủi ro vì họ hiểu bảo mật. Quyền quyết định cần xuất phát từ cơ chế ủy quyền của tổ chức.

Một người có thể là AO và TECH của một dịch vụ. Một nhóm có thể thực hiện cả OPS và SEC ở tổ chức nhỏ. Những trường hợp đó phải được xử lý ở cấp danh tính và hành động, không chỉ nhìn tên vai trò khác nhau trong bảng.

## 4. Chia hoạt động theo kết quả có thể kiểm chứng

Một hàng như “quản lý tài khoản đặc quyền” quá rộng vì bao gồm nhiều quyết định và hành động. Nên chia thành các đầu ra rõ ràng:

```text
Xác nhận nhu cầu tồn tại
  -> đầu ra: mục đích và owner được xác nhận

Phê duyệt phạm vi quyền
  -> đầu ra: capability, tài nguyên và điều kiện được duyệt

Triển khai quyền đã duyệt
  -> đầu ra: cấu hình thực tế khớp hồ sơ phê duyệt

Thu hồi sau thời hạn
  -> đầu ra: quyền mất hiệu lực trên phạm vi đích, hoặc trạng thái chưa xác định

Xem xét độc lập
  -> đầu ra: kết luận, phát hiện và việc cần khắc phục
```

Với mỗi hoạt động, cần bổ sung điều kiện đầu vào, thời hạn theo profile, nguồn bằng chứng và đường escalation. RACI không thay runbook, nhưng phải đủ rõ để biết ai sở hữu kết quả khi runbook thất bại.

### Khi có nhiều R

Ví dụ, TECH và OPS cùng tham gia luân chuyển credential:

- TECH xác định consumer, cách cập nhật, ảnh hưởng và kiểm tra dịch vụ.
- OPS thực hiện phần quản lý credential/vault được giao và ghi kết quả.
- A của hoạt động bảo đảm các phần được phối hợp, xử lý lỗi và không đóng việc khi còn consumer chưa rõ.

“Nhiều R” không nên có nghĩa ai cũng nghĩ bên kia sẽ bắt đầu. Cần chỉ định người điều phối hoặc điểm tiếp nhận công việc trong workflow.

## 5. Ma trận cho inventory và vòng đời tài khoản

Trong các bảng, cột A chỉ có một vai trò. Một vai trò xuất hiện cả A và R nghĩa là vừa chịu trách nhiệm cuối cùng vừa thực hiện phần việc tương ứng. Danh sách C/I có thể được điều chỉnh để tránh thông báo không cần thiết hoặc lộ thông tin nhạy cảm.

| Mã | Hoạt động và đầu ra | A | R | C | I |
| --- | --- | --- | --- | --- | --- |
| L1 | Duy trì phạm vi và quy tắc trách nhiệm của chương trình PAM | GOV | GOV, SEC | OPS, AO, RO, TECH | Các đơn vị áp dụng |
| L2 | Phát hiện, định danh và ghi nhận tài khoản trong phạm vi | GOV | OPS | TECH, RO, SEC | AO nếu đã xác định |
| L3 | Xác nhận nhu cầu tồn tại và nhận ownership tài khoản | AO | AO, TECH | RO, SEC | OPS, GOV |
| L4 | Xác nhận phạm vi quyền cần thiết trên tài nguyên | RO | TECH, AO | OPS, SEC | GOV |
| L5 | Triển khai tài khoản/quyền đúng hồ sơ đã được duyệt | OPS | OPS | TECH, RO | AO, SEC |
| L6 | Xác nhận hết nhu cầu sử dụng tài khoản | AO | AO, TECH | RO, SEC | OPS |
| L7 | Thực hiện thu hồi theo quyết định hợp lệ và ghi kết quả | OPS | OPS, TECH | RO, SEC | AO |
| L8 | Điều phối xử lý tài khoản chưa có owner hợp lệ | GOV | OPS, TECH | RO, SEC | Bên sở hữu dịch vụ liên quan |

### Giải thích các ranh giới quan trọng

**L2 và L3:** phát hiện một tài khoản chưa có owner vẫn phải có đầu mối chịu trách nhiệm điều phối. Không để L2 phụ thuộc vào một AO chưa tồn tại. Khi tìm được owner ứng viên, cần xác nhận thẩm quyền và việc nhận trách nhiệm trước khi coi L3 hoàn tất.

**L4 và L5:** RO chịu trách nhiệm về phạm vi quyền được chấp nhận trên tài nguyên. OPS chịu trách nhiệm triển khai đúng quyết định đó. OPS không được tự mở rộng quyền để “cho chạy được” rồi xem đó là một phần triển khai thông thường.

**L6 và L7:** AO xác nhận nhu cầu đã kết thúc; OPS/TECH thực hiện việc thu hồi và kiểm tra. Một email “không dùng nữa” chưa chứng minh principal, credential và phiên trên đích đã mất tác dụng.

**L8:** GOV chịu trách nhiệm giải quyết khoảng trống điều phối, không tự trở thành owner nghiệp vụ vĩnh viễn. Nếu có trách nhiệm tạm thời, cần ghi phạm vi, thời hạn và người chấp nhận đúng thẩm quyền.

Các bước bắt buộc theo sự kiện nhân sự hoặc ứng phó sự cố cần tuân theo chính sách tương ứng. Không để việc chưa tìm được AO làm trì hoãn vô thời hạn một quyết định thu hồi đã có thẩm quyền.

## 6. Ma trận cho sử dụng quyền và vận hành PAM

| Mã | Hoạt động và đầu ra | A | R | C | I |
| --- | --- | --- | --- | --- | --- |
| O1 | Lập yêu cầu truy cập đúng mục đích, đích và thời gian | REQ | REQ | TECH | AO, RO |
| O2 | Quyết định truy cập theo phạm vi ủy quyền | RO | APP | TECH, SEC khi điều kiện yêu cầu | REQ, OPS |
| O3 | Kích hoạt quyền JIT/phiên theo quyết định hợp lệ | OPS | OPS | TECH | REQ, APP |
| O4 | Luân chuyển credential có đánh giá phụ thuộc và kết quả dịch vụ | TECH | TECH, OPS | AO, RO | SEC |
| O5 | Thu thập, bảo vệ và chuyển bằng chứng tới nơi quản lý | OPS | OPS | SEC, TECH | GOV |
| O6 | Giám sát, phân loại và xử lý tín hiệu truy cập bất thường | SEC | SEC | OPS, TECH | AO, RO theo phạm vi |
| O7 | Thu hồi quyền/phiên theo thời hạn và xác minh kết quả | OPS | OPS, TECH | SEC | REQ, AO, RO |
| O8 | Xem xét định kỳ quyền còn cần thiết trên tài nguyên | RO | AO, TECH | OPS, SEC | GOV |

### O2: phê duyệt được ủy quyền vẫn phải có ranh giới

APP thực hiện quyết định trong phạm vi được RO hoặc cơ chế thẩm quyền tương ứng ủy quyền; RO là đầu mối chịu trách nhiệm cuối cùng về hoạt động này trong ma trận mẫu.

Điều đó không có nghĩa mọi yêu cầu luôn cần hai lần bấm duyệt của RO và APP. Workflow phải xác định rõ ai được ra quyết định cho trường hợp cụ thể. Nếu cần nhiều cấp phê duyệt, hãy mô tả từng điều kiện và trách nhiệm riêng, không tự suy từ số người xuất hiện trong RACI.

Nếu RO trực tiếp quyết định thì người giữ vai trò RO cũng thực hiện R của O2. Dù cách nào, cần kiểm tra người phê duyệt không phải người yêu cầu khi chính sách yêu cầu độc lập, và quyết định không vượt tài nguyên, capability hoặc thời gian được ủy quyền.

### O3: OPS thực thi quyết định, không thay thế quyết định

OPS có thể vận hành một cơ chế kích hoạt tự động. RACI vẫn phải chỉ ra đội chịu trách nhiệm khi cơ chế đó cấp sai quyền hoặc bỏ qua điều kiện.

Nếu yêu cầu bị lỗi kỹ thuật, OPS không tự chuyển sang một tài khoản toàn quyền ngoài hồ sơ đã duyệt. Thay đổi phạm vi phải quay lại quyết định đúng thẩm quyền hoặc đường khẩn cấp đã được định nghĩa.

### O4: luân chuyển không kết thúc ở vault

TECH chịu trách nhiệm phối hợp đánh giá consumer, cập nhật ứng dụng, cache, kết nối dài hạn và kiểm tra dịch vụ. OPS thực hiện các phần quản lý secret/vault được giao và cung cấp bằng chứng.

Cần ghi rõ ai xác nhận credential cũ hết tác dụng, ai xác nhận workload hoạt động và ai quyết định phương án khôi phục khi lỗi. Một sự kiện vault báo thành công chưa đủ để đóng toàn bộ O4.

### O5 và O6: có log khác với có người xử lý

OPS giữ trách nhiệm vận hành đường thu thập và bảo vệ bằng chứng được giao. SEC chịu trách nhiệm phân tích và xử lý tín hiệu theo quy trình. Nếu pipeline log hỏng, không đẩy toàn bộ trách nhiệm sang người phân tích; nếu log đã có nhưng cảnh báo không được xử lý, cần xem hoạt động O6.

Giới hạn lưu giữ, quyền xem bằng chứng và cách lọc secret phải được quy định trong chính sách liên quan. I không có nghĩa được đọc mọi bản ghi phiên hoặc dữ liệu nhạy cảm.

### O7: thu hồi cần một kết quả có thể tin cậy

Phải phân biệt hết hạn theo yêu cầu, hành động thu hồi đã gửi và quyền thực tế không còn hiệu lực. Khi chưa xác nhận được, OPS giữ trạng thái chưa xác định, phối hợp TECH/SEC và escalation theo profile; không đóng việc chỉ vì hết thời gian chờ.

Việc cùng OPS thực hiện và kiểm tra kỹ thuật thường ngày không tự thay thế đánh giá độc lập. Những hoạt động yêu cầu tách người triển khai với người xác nhận phải được thể hiện trong workflow và ma trận chi tiết phù hợp.

## 7. Ma trận cho ngoại lệ, sự cố và đánh giá độc lập

| Mã | Hoạt động và đầu ra | A | R | C | I |
| --- | --- | --- | --- | --- | --- |
| G1 | Quyết định ngoại lệ rủi ro có phạm vi và thời hạn | RISK | AO, TECH lập hồ sơ | RO, SEC, OPS | GOV và bên thực hiện liên quan |
| G2 | Điều phối containment và xử lý sự cố đặc quyền | IC | SEC, OPS, TECH | AO, RO | GOV, RISK theo mức độ |
| G3 | Điều phối sử dụng break-glass theo chính sách khẩn cấp | IC | OPS, TECH | RO, SEC nếu có thể liên hệ | AO, GOV |
| G4 | Xem xét độc lập bằng chứng và kết luận đánh giá | REV | REV | AO, RO, TECH, OPS, SEC | GOV, RISK theo phạm vi |

### Ngoại lệ không chỉ là một phê duyệt kỹ thuật

Trong G1, AO/TECH lập hồ sơ về nhu cầu, hạn chế, tác động, kiểm soát bù và kế hoạch xử lý. SEC tham vấn về rủi ro; RISK ra quyết định trong thẩm quyền được giao.

Chấp nhận rủi ro không tự cấp quyền trên mọi tài nguyên. Nếu ngoại lệ kéo theo thay đổi phạm vi truy cập, quyết định của RO và triển khai tương ứng vẫn cần được thực hiện. Các điều kiện này là các hoạt động khác nhau nên không tạo thêm A trong cùng một hàng.

### Thẩm quyền khẩn cấp phải được xác định trước

G2 và G3 chỉ áp dụng khi tổ chức có quy trình chỉ định IC và ủy quyền tương ứng. Bảng RACI không tự cho phép bất kỳ người nào xưng là người điều phối rồi bỏ qua kiểm soát.

Nếu quy trình ứng phó cần quyết định khẩn cấp khi một bên C không liên hệ được, phải có điều kiện, phạm vi và bằng chứng cho tình huống đó. Không đặt một người không thể liên hệ thành điểm chặn tuyệt đối mà chưa thiết kế đường dự phòng.

Break-glass cần giữ được danh tính người dùng thực tế, lý do, thời gian, phạm vi và xem xét sau sử dụng. Việc review sau sự kiện không thay thế yêu cầu có thẩm quyền tại thời điểm sử dụng, trừ khi chính sách khẩn cấp đã xác định cơ chế đó.

### Độc lập phải được xét ở cấp con người

G4 dùng vai trò REV để tách kết luận đánh giá khỏi người tự triển khai kiểm soát. Nếu cùng một người vừa triển khai vừa đóng vai REV, tên cột khác nhau không tạo ra độc lập.

Ở tổ chức nhỏ, có thể cần reviewer từ đội khác, kiểm tra của cấp có thẩm quyền hoặc cơ chế kiểm soát bù đã được chấp thuận. Cần ghi giới hạn và lý do thay vì tuyên bố độc lập hình thức.

## 8. Ánh xạ RACI vào người thực và workflow

### 8.1. Role phải phân giải được theo phạm vi

`RO` không phải một người duy nhất cho cả tổ chức. Người giữ vai trò phụ thuộc tài nguyên, môi trường, đơn vị và thời điểm. `AO` cũng cần liên kết đúng principal và vòng đời tài khoản.

Một bản ghi ánh xạ nên chứa:

```text
Vai trò tổ chức
Phạm vi tài nguyên/tài khoản
Người hoặc nhóm được chỉ định
Người chịu trách nhiệm hiện tại có thể liên hệ
Nguồn thẩm quyền và bằng chứng nhận trách nhiệm
Thời gian hiệu lực
Đại diện dự phòng và giới hạn ủy quyền
Đường escalation
```

Một mailbox nhóm chỉ là kênh liên hệ nếu không có cơ chế giao việc và người nhận trách nhiệm. Một nhóm có nhiều thành viên vẫn cần cách xác định ai là người tiếp nhận và ai được ra quyết định cho công việc cụ thể.

### 8.2. Phân giải từ nguồn tin cậy

Workflow phải lấy người phê duyệt và phạm vi thẩm quyền từ nguồn được quản lý. Không tin trường `approver_id`, `owner_id` hoặc nhãn môi trường do chính người yêu cầu gửi lên mà chưa đối chiếu.

Giả mã dưới đây chỉ minh họa ý tưởng, không phải chương trình triển khai:

```text
subject = authenticated_subject()
request = validate_request_schema(input)
targets = resolve_verified_targets(request.target_ids)

role_mapping = load_authorized_role_mapping(targets, current_time)
approver = select_valid_delegate(role_mapping, request)

require(approver.authority_covers(request.action, targets, request.time_window))
require_separation_of_duties(subject, approver, applicable_policy)

record_request_and_routing(subject, request, role_mapping.version)
route_to_approval(approver, request)
```

Nếu phạm vi yêu cầu đi qua nhiều RO, có thể phải tách thành các quyết định theo tài nguyên hoặc dùng cơ chế ủy quyền liên phạm vi được phê duyệt. Không chọn ngẫu nhiên một RO rồi coi người đó có thẩm quyền với tất cả đích.

### 8.3. Workflow phải giữ được dấu vết từng vai trò

Mỗi lần thực hiện nên liên kết được:

- Mã hoạt động RACI và phiên bản ma trận áp dụng.
- Danh tính người yêu cầu, người quyết định và người thực hiện thực tế.
- Tài khoản, capability, tài nguyên và khoảng thời gian liên quan.
- Nguồn ủy quyền, quyết định, thay đổi cấu hình và kết quả trên đích.
- Phần chưa xác định, escalation và người tiếp nhận tiếp theo.

Không nhất thiết phải chép toàn bộ ma trận vào mỗi sự kiện. Cần tham chiếu được tới phiên bản và giữ đủ thông tin để giải thích ai giữ vai trò nào tại thời điểm hành động.

### 8.4. Người vắng mặt và chuyển giao trách nhiệm

Người dự phòng chỉ được xử lý trong phạm vi ủy quyền còn hiệu lực. Không tự chọn người đang online hoặc người đã từng bấm duyệt một yêu cầu cũ.

Khi AO/RO chuyển vị trí, cập nhật ánh xạ và chuyển giao có chấp nhận. Nếu người cũ không còn hợp lệ mà chưa có người mới, phải thể hiện khoảng trống và dùng escalation; không tiếp tục ghi họ là A để bảng trông đầy đủ.

RACI cần nêu nơi tiếp nhận khi có khoảng trống. Với tài khoản thiếu owner, hoạt động L8 bảo đảm có trách nhiệm điều phối mà chưa giả vờ đã có owner nghiệp vụ.

## 9. Ví dụ: yêu cầu JIT trên database production

Một người trực cần thực hiện tác vụ bảo trì đã được định nghĩa trên database production trong 20 phút. Con số này chỉ mô tả tình huống, không phải thời lượng chuẩn cho mọi môi trường.

### Luồng bình thường

1. **O1:** REQ nêu tác vụ, đích, thời gian và lý do. TECH được hỏi nếu cần làm rõ ảnh hưởng kỹ thuật.
2. **O2:** APP được phân giải từ nguồn thẩm quyền của RO, kiểm tra phạm vi và xung đột với REQ. RO chịu trách nhiệm cuối cùng cho cơ chế quyết định trong phạm vi của mình.
3. **O3:** OPS hoặc cơ chế tự động do OPS vận hành chỉ kích hoạt capability trên tập đích được duyệt, trong khoảng thời gian được cấp.
4. **O5/O6:** bằng chứng được thu thập; SEC theo dõi các tín hiệu thuộc quy trình giám sát.
5. **O7:** khi đến hạn, OPS/TECH kiểm tra kết thúc quyền, gồm những token hoặc phiên liên quan theo khả năng nền tảng. Phần chưa xác nhận được tiếp tục là việc đang mở.

### Khi người trực đồng thời là quản trị viên PAM

Người đó có thể giữ vai trò REQ và cũng thuộc đội OPS. Điều này không cho phép họ dùng quyền sửa workflow để tự trở thành APP hoặc đổi target của yêu cầu.

Cần kiểm soát quyền sửa chính sách, ánh xạ approver và cấu hình thực thi. Nếu chính sách yêu cầu độc lập, một người khác đúng thẩm quyền phải quyết định truy cập. Log phải giữ danh tính thực tế thay vì chỉ ghi “đội PAM”.

### Khi thu hồi chưa được xác nhận

PAM báo đã kết thúc lần kích hoạt nhưng kết nối database vẫn có khả năng thực hiện tác vụ. OPS không được đóng O7 theo thông báo phía PAM. TECH xác định hành vi phiên/token, SEC hỗ trợ đánh giá rủi ro và việc được escalation theo profile.

Nếu chuyển thành sự cố, IC tiếp nhận trách nhiệm điều phối G2. Điều đó không xóa lịch sử O7 hoặc biến kết quả chưa xác định thành đã thu hồi; workflow phải giữ liên kết giữa công việc vận hành và hồ sơ sự cố.