# Access review evidence trong Privileged Access Management

## 1. Bằng chứng access review cần chứng minh điều gì?

Access review là hoạt động rà soát quyền truy cập để xác nhận một chủ thể còn cần những quyền nào, quyền nào phải điều chỉnh hoặc thu hồi, và ngoại lệ nào được chấp nhận trong thời gian xác định. Trong Privileged Access Management (PAM), đối tượng rà soát là những đường dẫn có thể dẫn đến quyền quản trị: tài khoản cá nhân, tài khoản quản trị dùng riêng, tài khoản dịch vụ, nhóm đặc quyền, vai trò cloud, quyền lấy secret từ vault, quyền mở phiên qua gateway và quyền truy cập khẩn cấp.

**Access review evidence** là tập bằng chứng cho phép người khác kiểm tra lại cuộc rà soát đó. Một bằng chứng tốt giúp trả lời đồng thời các câu hỏi:

1. Tại thời điểm rà soát, ai hoặc workload nào có thể thực hiện hành động đặc quyền trên tài nguyên nào?
2. Danh sách đó được lấy từ đâu, có bao phủ đầy đủ phạm vi đã công bố không?
3. Ai có thẩm quyền đánh giá nhu cầu nghiệp vụ và ai thực sự đưa ra quyết định?
4. Mỗi quyền được giữ, giảm, thu hồi hay cho phép ngoại lệ vì lý do gì?
5. Quyết định đã được thực thi và được xác minh trên hệ thống đích chưa?
6. Sau khi hoàn tất, còn quyền, ngoại lệ hoặc vấn đề nào chưa được xử lý?

Một ảnh chụp màn hình có chữ “Approved” thường không trả lời đủ sáu câu hỏi. Một ticket được đóng cũng chưa chứng minh quyền đã mất hiệu lực. Mục tiêu của bằng chứng là nối được **quyền thực tế → người chịu trách nhiệm → quyết định → thay đổi → kết quả xác minh**.

Bài học này trình bày cách xây dựng chuỗi bằng chứng đó cho hệ thống PAM. Các chu kỳ rà soát, thời hạn lưu giữ và thẩm quyền phê duyệt trong ví dụ là thiết kế minh họa; tổ chức phải xác định chúng từ phạm vi kiểm soát, chính sách và yêu cầu áp dụng của mình.

## 2. Phân biệt quyền được cấp và quyền đã được sử dụng

Trong PAM, rất dễ nhầm bằng chứng access review với báo cáo phiên truy cập. Hai loại thông tin hỗ trợ nhau nhưng trả lời các câu hỏi khác nhau.

| Loại thông tin | Câu hỏi chính | Ví dụ | Giới hạn khi đứng một mình |
|---|---|---|---|
| Danh sách quyền | Ai có khả năng truy cập? | Thành viên nhóm quản trị, quyền đọc secret, quyền assume role | Không cho biết quyền đã được sử dụng hay còn cần thiết |
| Log hoạt động | Ai đã sử dụng quyền, lúc nào? | Phiên SSH, thao tác lấy credential, lần kích hoạt JIT | Không phát hiện đầy đủ quyền có sẵn nhưng chưa dùng |
| Quyết định review | Ai xác nhận quyền còn phù hợp? | Giữ quyền kèm lý do và người phê duyệt | Không chứng minh thay đổi đã thực hiện |
| Bằng chứng thực thi | Hệ thống đã thay đổi thế nào? | Xóa membership, giảm policy, thu hồi eligibility | Không tự chứng minh mọi quyền trong phạm vi đã được review |
| Bằng chứng xác minh | Quyền thực tế sau thay đổi là gì? | Export lại entitlement, kiểm tra effective permission | Không thay thế danh sách đầu vào và quyết định nghiệp vụ |

Ví dụ, tài khoản `admin-lan` không có phiên truy cập trong 90 ngày có thể là quyền dư thừa, nhưng cũng có thể là tài khoản phục hồi được thiết kế để ít sử dụng. Người review cần biết mục đích, owner, đường truy cập và kiểm soát đi kèm trước khi quyết định.

Ngược lại, một phiên truy cập hợp lệ hôm qua không tự động chứng minh người dùng cần quyền quản trị thường trực trong tháng tới. Nhu cầu có thể được đáp ứng bằng JIT, JEA hoặc một vai trò hẹp hơn.

### 2.1. Ba dạng quyền phải nhận diện riêng

- **Quyền thường trực:** Có thể sử dụng khi đăng nhập hoặc khi đáp ứng các điều kiện thông thường.
- **Quyền đủ điều kiện kích hoạt:** Chưa có quyền quản trị hiệu lực ngay nhưng có thể yêu cầu hoặc tự kích hoạt theo policy JIT.
- **Quyền đang được kích hoạt:** Quyền JIT đang có hiệu lực trong khoảng thời gian cụ thể.

Một bản export chỉ hiển thị quyền đang kích hoạt sẽ bỏ sót người có thể kích hoạt quyền trong tương lai. Một bản export chỉ hiển thị eligibility lại không phản ánh phiên hoặc token đang hoạt động. Cuộc review phải công bố đang đánh giá dạng nào và lấy dữ liệu thích hợp cho từng dạng.

## 3. Đơn vị review nên là một quan hệ cấp quyền

Chỉ review danh sách tài khoản thường không đủ. Một người có thể có quyền quản trị hợp lệ trên môi trường thử nghiệm nhưng có quyền dư thừa trên hệ thống production. Một workload có thể cần đọc một secret cụ thể nhưng không cần quyền quản lý toàn bộ vault.

Đơn vị review thực dụng là một quan hệ cấp quyền có thể truy vết:

```text
Chủ thể
  → tài khoản hoặc danh tính sử dụng
  → đường cấp quyền
  → vai trò/quyền và phạm vi tài nguyên
  → điều kiện, thời hạn và cách kích hoạt
```

Ví dụ:

```text
Nhân viên: person-018
Tài khoản quản trị: adm-018
Đường cấp quyền: group-platform-ops → role-db-maintainer
Tài nguyên: cụm database production cụ thể
Hình thức: đủ điều kiện JIT, mỗi lần kích hoạt tối đa theo policy
Quyền liên quan: được mở phiên qua PAM gateway
```

Nếu cùng tài khoản còn thuộc nhóm quản trị cục bộ trên database host, xóa eligibility của `role-db-maintainer` không loại bỏ đường quản trị thứ hai. Vì vậy, bằng chứng nên thể hiện cả quan hệ được cấu hình và quyền hiệu lực khi có thể xác định.

### 3.1. Các danh tính cần được nối với owner

| Loại chủ thể | Thông tin cần xác định | Câu hỏi review quan trọng |
|---|---|---|
| Người dùng nội bộ | Mã danh tính ổn định, trạng thái làm việc, bộ phận | Vai trò công việc hiện tại có còn cần quyền không? |
| Nhà cung cấp | Đơn vị bảo trợ, hợp đồng hoặc nhiệm vụ, ngày kết thúc | Quyền có còn cần sau thời hạn hỗ trợ không? |
| Tài khoản dịch vụ | Workload, owner kỹ thuật, owner nghiệp vụ | Quyền có khớp đúng tác vụ tự động đang chạy không? |
| Tài khoản dùng chung | Owner, người được phép sử dụng, cơ chế attribution | Có truy được người thực hiện qua PAM không? |
| Tài khoản break-glass | Người chịu trách nhiệm, điều kiện sử dụng, cơ chế giám sát | Quyền phục hồi có được giới hạn và kiểm soát đúng thiết kế không? |
| Danh tính pipeline hoặc robot | Job, repository, môi trường, cơ chế lấy credential | Quyền quản trị có bị cấp rộng hơn phạm vi triển khai không? |

Không tìm được owner là một phát hiện cần xử lý, không phải lý do để mặc định giữ quyền. Với tài khoản dịch vụ, không thể thay người review bằng một tên nhóm chung mà không có người nhận trách nhiệm cụ thể.

## 4. Xác định phạm vi trước khi thu thập bằng chứng

Một cuộc review có thể được tổ chức theo chu kỳ, sau thay đổi vai trò, sau sự cố hoặc trước một đợt kiểm toán. Dù bắt đầu từ đâu, cần một bản mô tả phạm vi được chốt trước khi đưa danh sách cho reviewer.

Bản mô tả tối thiểu gồm:

- Mã cuộc review, mục tiêu, người điều phối và khoảng thời gian thực hiện.
- Danh sách hệ thống, môi trường, tenant, domain, vault, subscription hoặc account thuộc phạm vi.
- Các loại quyền và danh tính được đưa vào review.
- Thời điểm chụp dữ liệu và cách xử lý thay đổi phát sinh sau thời điểm đó.
- Nguồn dữ liệu, bộ lọc, cơ chế phân trang và giới hạn của từng nguồn.
- Quy tắc chọn reviewer và người phê duyệt ngoại lệ.
- Hạn ra quyết định, hạn thực thi và điều kiện đóng cuộc review.
- Các loại trừ, lý do, người chấp thuận và cuộc review khác bao phủ chúng nếu có.

### 4.1. Ranh giới PAM không chỉ là danh sách account trong vault

Một tài khoản chưa được đưa vào PAM vẫn có thể có quyền quản trị. Nếu mục tiêu là rà soát quyền đặc biệt trên production, việc chỉ export account được quản lý trong vault sẽ tạo ra một điểm mù.

Cần đối chiếu các nguồn như directory, IAM của hệ thống đích, nhóm quản trị cục bộ, cơ chế sudo, cloud role assignment và danh sách quyền trên PAM. Tùy kiến trúc, các nguồn này có thể cho thấy:

- Tài khoản có quyền quản trị nhưng chưa được onboard vào PAM.
- Người được phép lấy credential của tài khoản dùng chung.
- Người được phép sửa policy của vault hoặc thay đổi thành viên nhóm được review.
- Đường truy cập trực tiếp bỏ qua gateway.
- Secret, SSH key hoặc credential tự động hóa vẫn cho phép workload thực hiện hành động đặc quyền.

Nếu chỉ review một phần, báo cáo phải ghi rõ phần đó. Không đổi tên một cuộc review giới hạn thành “review toàn bộ PAM” sau khi hoàn tất.

### 4.2. Chu kỳ review và thời hạn quyền là hai khái niệm khác nhau

Quyền hết hạn sau một giờ vẫn cần được xem xét nếu người dùng có thể liên tục kích hoạt lại. Ngược lại, một cuộc review định kỳ không thay thế việc thu hồi ngay khi có thông tin người dùng rời tổ chức hoặc thay đổi nhiệm vụ.

Tần suất review nên phản ánh mức độ đặc quyền, tác động của tài nguyên, biến động danh tính và khả năng phát hiện thay đổi. Trong bằng chứng, ghi chính sách hoặc quyết định nội bộ đang được áp dụng, không chỉ ghi “theo yêu cầu compliance”.

## 5. Chứng minh danh sách đầu vào đầy đủ và đúng thời điểm

Đây là bước quyết định chất lượng của access review evidence. Nếu danh sách đầu vào thiếu quyền, mọi quyết định trên danh sách còn lại vẫn có thể hợp lệ nhưng kết luận về độ bao phủ sẽ sai.

### 5.1. Lưu dấu vết cách xuất dữ liệu

Với mỗi nguồn, nên lưu:

| Nhóm thông tin | Nội dung cần lưu |
|---|---|
| Danh tính nguồn | Tên hệ thống, instance/tenant, phạm vi môi trường |
| Thời gian | Bắt đầu, kết thúc, múi giờ hoặc thời gian UTC |
| Phương pháp | Report/API/query được dùng, bộ lọc và phạm vi quyền của tài khoản đọc |
| Độ đầy đủ | Số trang, số bản ghi, lỗi truy vấn, phần không truy cập được |
| Định danh artifact | Tên file, phiên bản, vị trí lưu, checksum nếu dùng |
| Hạn chế | Nguồn không hỗ trợ snapshot, độ trễ đồng bộ, quyền kế thừa chưa phân giải |

Không lưu access token, password, private key hoặc secret value vào bằng chứng. Một report về quyền đọc secret cần định danh secret và policy, không cần nội dung bí mật của nó.

Một API trả HTTP thành công không chứng minh đã lấy đủ dữ liệu. Có thể thiếu trang cuối, bị giới hạn theo tenant, bị lọc mất account disabled hoặc chỉ thấy tài nguyên mà tài khoản xuất dữ liệu có quyền đọc. Các giới hạn đó phải được kiểm tra và ghi nhận.

### 5.2. Đối soát theo định danh ổn định

Tên hiển thị có thể trùng hoặc thay đổi. Nên dùng mã danh tính, account ID, group ID, role ID và resource ID ổn định để nối dữ liệu. Tên hiển thị được lưu thêm để reviewer đọc dễ hơn.

Một bảng chuẩn hóa có thể gồm:

```text
grant_id
principal_id
account_id
principal_type
owner_id
resource_id
entitlement_id
assignment_type
grant_path
valid_from
valid_until
source_system
snapshot_at
```

`grant_id` phải định danh đủ quan hệ được review. Nếu nguồn không có mã cấp quyền duy nhất, tổ chức có thể tạo mã nội bộ từ tập thuộc tính chuẩn hóa. Khi đó cần giữ cả thuộc tính nguồn và quy tắc tạo mã; không dùng một số thứ tự thay đổi sau mỗi lần export để nối quyết định giữa các bản chụp.

### 5.3. Phân giải nhóm lồng và quyền kế thừa

Reviewer cần thấy người hưởng quyền cuối cùng và đường dẫn dẫn đến quyền đó, không chỉ tên nhóm cấp cao.

```text
person-018
  → group-team-a
  → group-platform-ops
  → role-db-maintainer
  → database-production
```

Nếu membership của `group-team-a` được quản lý tại directory nhưng role assignment được quản lý tại cloud IAM, bằng chứng phải nối được hai nguồn. Với quyền kế thừa từ cấp tổ chức hoặc project, ghi cấp gốc và phạm vi tài nguyên nhận quyền.

Khi chưa phân giải được một đường cấp quyền, đánh dấu là giới hạn hoặc phát hiện còn mở. Không đánh dấu “không có quyền” chỉ vì công cụ export chưa hiển thị được quyền hiệu lực.

### 5.4. Chụp dữ liệu không đồng thời

Không phải hệ thống nào cũng hỗ trợ snapshot nhất quán tại cùng một thời điểm. Ví dụ, export directory hoàn tất lúc 02:05 UTC còn export cloud IAM hoàn tất lúc 02:20 UTC. Membership thay đổi trong khoảng giữa có thể làm phép nối dữ liệu sai.

Có thể xử lý bằng cách ghi rõ cửa sổ thu thập, lấy change log trong cửa sổ đó và xuất lại những bản ghi bị ảnh hưởng. Nếu không thể bù đầy đủ, ghi giới hạn và cách xử lý rủi ro. Không gán một `snapshot_at` chung như thể tất cả nguồn được đọc nguyên tử.

### 5.5. Quản lý thay đổi trong thời gian review

Nên tách danh sách nền tại thời điểm bắt đầu với danh sách thay đổi phát sinh. Một cách đối soát là:

```text
Tập quyền cuối kỳ
  = Tập quyền đầu kỳ
  + quan hệ cấp quyền mới
  - quan hệ đã bị xóa
  + các điều chỉnh thuộc tính làm thay đổi phạm vi hoặc mức quyền
```

Đây là quan hệ giữa các tập bản ghi, không phải phép cộng số lượng đơn giản khi dữ liệu có bản ghi trùng hoặc một grant được tách thành nhiều grant. Cần đối soát theo mã và thuộc tính để tránh đếm sai.

Quyền mới phát sinh có thể được đưa vào đợt review bổ sung hoặc được bao phủ bởi quy trình cấp quyền đã phê duyệt, tùy phạm vi kiểm soát. Báo cáo phải chỉ rõ cách xử lý; không để quyền mới biến mất khỏi cả hai quy trình.

## 6. Thiết kế bản ghi quyết định có thể kiểm tra lại

Mỗi quyết định cần gắn với đúng quan hệ cấp quyền và đúng bản chụp dữ liệu mà reviewer đã xem.

| Trường | Ý nghĩa |
|---|---|
| `review_id`, `grant_id` | Cuộc review và quan hệ cấp quyền cụ thể |
| `input_version` | Phiên bản danh sách đầu vào được review |
| `reviewer_id` | Danh tính người ra quyết định |
| `reviewer_basis` | Vì sao người đó có thẩm quyền đánh giá quyền này |
| `decision` | Giữ, giảm, thu hồi, chuyển sang JIT/JEA hoặc đề nghị ngoại lệ |
| `rationale` | Lý do nghiệp vụ và phạm vi còn cần |
| `decided_at` | Thời điểm ra quyết định có múi giờ |
| `due_at` | Hạn thực thi nếu có hành động |
| `action_ref` | Liên kết công việc thực thi |
| `exception_ref` | Mã ngoại lệ khi áp dụng |
| `verification_ref` | Bằng chứng kiểm tra kết quả |

### 6.1. Người review cần đủ hiểu biết và thẩm quyền

Quản lý trực tiếp thường hiểu nhiệm vụ của người dùng, còn owner của hệ thống hiểu tác động của quyền. Với quyền đặc biệt nhạy cảm, có thể cần cả hai góc nhìn. Security hoặc PAM team có thể kiểm tra cấu hình và tính đầy đủ nhưng không phải lúc nào cũng có đủ thông tin để xác nhận nhu cầu nghiệp vụ.

Nếu người dùng đồng thời là owner hệ thống, cần một người review hoặc cấp phê duyệt độc lập theo cơ chế đã xác định. Việc một người tự xác nhận quyền của mình phải được nhận diện như một xung đột, không được che bằng tên tài khoản phê duyệt chung.

Đối với service account, reviewer nên xác nhận workload còn tồn tại, quyền còn khớp tác vụ và có người chịu trách nhiệm. Câu “đây là tài khoản kỹ thuật” không phải lý do đủ để giữ mọi quyền.

### 6.2. Lý do giữ quyền phải có nội dung

Các lý do như “cần cho công việc”, “đã dùng từ trước” hoặc “không có vấn đề” khó kiểm tra lại. Lý do có chất lượng nối nhu cầu với phạm vi quyền:

```text
Chủ thể thuộc nhóm trực vận hành database production.
Cần quyền thực hiện bảo trì trên cụm db-prod-a trong ca được phân công.
Giữ eligibility cho role bảo trì; không giữ quyền sửa IAM hoặc quản lý vault.
Việc kích hoạt tiếp tục chịu phê duyệt và ghi nhận phiên theo policy hiện hành.
```

Mức chi tiết phải phù hợp rủi ro và tránh sao chép thông tin nhạy cảm không cần thiết. Với nhiều quyền thật sự tương đương, có thể review theo nhóm nếu vẫn truy vết được từng grant, tiêu chí nhóm và mọi ngoại lệ. Một nút “Approve all” không thay thế việc chứng minh reviewer đã nhận được danh sách đầy đủ và hiểu nội dung được xác nhận.

### 6.3. Bảo toàn lịch sử sửa quyết định

Reviewer có thể thay đổi quyết định sau khi nhận thêm thông tin. Hệ thống nên giữ quyết định cũ, quyết định mới, thời gian, người sửa và lý do. Không sửa trực tiếp bản export đã ký nhận rồi giữ nguyên ngày phê duyệt cũ.

Nếu dữ liệu đầu vào thay đổi đáng kể, quyết định trên phiên bản cũ không tự động có hiệu lực cho bản mới. Cần review bổ sung phần thay đổi và liên kết hai phiên bản.

## 7. Từ quyết định đến quyền thực tế sau xử lý

Phê duyệt thu hồi mới là điểm bắt đầu của công việc thực thi. Một chuỗi bằng chứng đầy đủ cần phân biệt ít nhất ba trạng thái:

```text
DECIDED → IMPLEMENTED → VERIFIED
```

- `DECIDED`: Reviewer đã xác định hành động cần làm.
- `IMPLEMENTED`: Người hoặc hệ thống thực thi báo đã áp dụng thay đổi.
- `VERIFIED`: Có kết quả kiểm tra cho thấy thay đổi đã đạt mục tiêu.

Không gộp cả ba thành một checkbox “Done”.

### 7.1. Thu hồi đúng đường cấp quyền

Với mỗi quyết định, cần xác định nơi có thẩm quyền quản lý quyền. Ví dụ:

| Quyết định | Nơi thực thi có thể liên quan | Bằng chứng xác minh phù hợp |
|---|---|---|
| Xóa quyền qua nhóm lồng | Directory hoặc hệ thống quản lý nhóm nguồn | Membership mới và effective entitlement trên đích |
| Bỏ quyền lấy credential | Policy của vault/PAM | Policy sau thay đổi, quyền truy cập hiệu lực |
| Thu hồi eligibility JIT | Hệ thống quản lý role | Eligibility đã mất, xử lý activation còn tồn tại nếu có |
| Giảm quyền workload | Policy IAM và cấu hình workload | Policy mới, quyền hiệu lực, kiểm tra chức năng đã phê duyệt |
| Chặn truy cập nhà cung cấp | Directory, gateway, target và credential liên quan | Trạng thái trên từng đường truy cập thuộc phạm vi |
| Thu hồi đường truy cập bằng SSH key | Nơi quản lý key và máy đích liên quan | Key không còn được chấp nhận theo cơ chế đã xác định |

Xóa người khỏi danh sách cho phép mở phiên trên gateway có thể không ngăn được đường SSH trực tiếp. Xóa membership trong directory có thể chưa chấm dứt session hoặc token đã được cấp trước đó. Cần xác định rõ mục tiêu của hành động và xử lý các trạng thái còn hiệu lực theo cơ chế của hệ thống.

### 7.2. Credential đã được lộ cho người dùng

Nếu người dùng từng xem hoặc nhận credential dùng chung, việc xóa quyền đọc secret không làm họ quên giá trị cũ. Tùy loại credential và kiến trúc, hành động có thể cần gồm đổi credential, vô hiệu hóa phiên hoặc token liên quan và xác minh hệ thống phụ thuộc đã chuyển sang giá trị mới.

Bằng chứng access review nên tham chiếu kết quả luân chuyển hoặc thu hồi, không đính kèm credential cũ và mới. Với service account, cần phối hợp để thay đổi quyền hoặc credential mà không làm đứt tác vụ quan trọng ngoài kế hoạch.

### 7.3. Xác minh bằng nguồn có ý nghĩa

Export lại từ hệ thống đích thường mạnh hơn việc chỉ đọc trạng thái ticket. Tuy nhiên, export cũng cần kiểm tra thời gian đồng bộ và cache. Nếu thay đổi chưa lan truyền, không kết luận đã thu hồi chỉ vì cấu hình nguồn đã đổi.

Kết quả xác minh nên ghi:

- Grant hoặc đường cấp quyền được kiểm tra.
- Phương pháp và nguồn kiểm tra.
- Thời điểm sau thực thi và khoảng chờ đồng bộ nếu có.
- Kết quả thực tế so với kết quả mong đợi.
- Người hoặc job thực hiện xác minh.
- Phần chưa xác minh được và hành động tiếp theo.

Không bắt buộc mọi trường hợp phải thử đăng nhập bằng tài khoản thật. Có thể dùng truy vấn policy, membership, mô phỏng quyền hoặc kiểm tra kiểm soát đã phê duyệt, tùy khả năng hệ thống. Nếu cần thử truy cập, thực hiện trong phạm vi được cho phép và tránh đưa credential vào log kiểm thử.

## 8. Ngoại lệ phải có vòng đời riêng

Một quyền không còn phù hợp nhưng chưa thể thu hồi ngay không nên được đổi thành “giữ quyền hợp lệ” chỉ để đóng cuộc review. Cần thể hiện đây là ngoại lệ, với người chịu trách nhiệm và rủi ro còn lại.

Một bản ghi ngoại lệ nên có:

```text
Mã ngoại lệ
Grant và tài nguyên bị ảnh hưởng
Lý do chưa thể áp dụng quyết định chuẩn
Tác động và rủi ro còn lại
Người chấp thuận rủi ro có thẩm quyền
Biện pháp kiểm soát bù và bằng chứng đang vận hành
Ngày bắt đầu, ngày hết hạn, ngày xem xét lại
Owner xử lý và kế hoạch kết thúc ngoại lệ
```

Ví dụ, một service account cũ cần quyền rộng cho đến khi thay đổi phần mềm. Ngoại lệ có thể yêu cầu giới hạn nơi credential được sử dụng, tăng giám sát, giới hạn đường mạng và có kế hoạch giảm quyền. Những biện pháp đó chỉ có giá trị khi có bằng chứng đã triển khai; một dòng ghi “được giám sát” không đủ.

Ngoại lệ hết hạn không được tự gia hạn bằng cách sao chép bản ghi cũ. Nếu chưa thể kết thúc, cần quyết định mới từ người có thẩm quyền, cập nhật rủi ro và ghi nhận tình trạng quá hạn nếu đã xảy ra.

## 9. Tổ chức gói bằng chứng để người khác có thể tái dựng

Một gói bằng chứng cần có bản mục lục và liên kết giữa các artifact. Cấu trúc dưới đây là ví dụ logic cho tài liệu vận hành, không phải cấu trúc bắt buộc của một sản phẩm PAM:

```text
PAM-AR-EXAMPLE/
├── scope-and-method/
│   ├── scope
│   └── collection-method
├── source-snapshots/
│   ├── directory-entitlements
│   ├── target-entitlements
│   └── pam-policies
├── normalized-population/
│   ├── grants
│   └── reconciliation
├── decisions/
│   ├── review-records
│   └── reviewer-authority
├── remediation/
│   ├── action-records
│   └── verification-results
├── exceptions/
└── closure/
    ├── summary
    └── evidence-index
```

### 9.1. Mục lục bằng chứng

Mỗi artifact có một mã ổn định, mô tả, nguồn, thời gian và vị trí lưu. Bản ghi quyết định chỉ cần tham chiếu mã đó; không nên sao chép hàng chục phiên bản của cùng một file vào từng ticket.

Một bản ghi minh họa bằng YAML có thể như sau:

```yaml
review_id: PAM-AR-EXAMPLE
grant_id: grant-0156
input_version: population-v1
principal_id: workload-032
resource_id: vault-prod-app-a
entitlement: read-required-secret
decision: REDUCE
rationale: Chỉ giữ quyền đọc secret của ứng dụng A, bỏ phạm vi toàn vault.
reviewer_id: owner-app-a
decided_at: '2026-11-20T09:00:00Z'
action:
  reference: change-0842
  state: VERIFIED
  implemented_at: '2026-11-21T03:00:00Z'
  verified_at: '2026-11-21T03:20:00Z'
  verification_reference: evidence-021
exception_reference: null
```

Ví dụ chỉ minh họa cách liên kết dữ liệu. Trạng thái, tên trường và giá trị phải được định nghĩa nhất quán trong quy trình thật. Không ghi các dữ liệu vận hành này vào metadata của bài học hoặc dùng chúng làm bằng chứng cho một cuộc review chưa diễn ra.

### 9.2. Tính toàn vẹn và nguồn gốc

Checksum có thể giúp phát hiện file khác với phiên bản đã được ghi nhận. Checksum đứng một mình không chứng minh file xuất từ đúng hệ thống, không chứng minh nội dung đúng và không ngăn người có quyền sửa cả file lẫn danh sách checksum.

Vì vậy, cần kết hợp khả năng lưu phiên bản, kiểm soát quyền sửa, log truy cập, cơ chế bảo vệ hoặc khóa lưu giữ phù hợp và nguồn xuất dữ liệu có thể truy vết. Chữ ký hoặc dấu thời gian chỉ có ý nghĩa khi người kiểm tra hiểu chúng bảo đảm điều gì và khóa ký được quản lý thế nào.

Tránh phụ thuộc hoàn toàn vào URL của một ticket hoặc dashboard sống. Nội dung ở đó có thể thay đổi hoặc mất sau khi hệ thống được thay thế. Có thể lưu bản xuất tại thời điểm đóng review và giữ liên kết về nguồn để hỗ trợ truy nguyên.

### 9.3. Bảo mật và lưu giữ

Danh sách quyền quản trị, owner và tài nguyên production là thông tin nhạy cảm. Người làm kiểm toán có thể cần đọc nhưng không cần quyền chỉnh sửa hoặc quyền sử dụng credential tương ứng.

Phân quyền kho bằng chứng theo vai trò, giới hạn chia sẻ, ghi nhận truy cập và bảo vệ bản sao dự phòng theo thiết kế của tổ chức. Thời hạn lưu giữ cần phù hợp chính sách được phê duyệt và yêu cầu áp dụng; không mặc định một thời hạn duy nhất cho mọi ngành hoặc mọi cuộc review.

Nếu phải che thông tin khi chia sẻ, giữ quan hệ giữa bản đầy đủ và bản đã che, người thực hiện, thời điểm và phạm vi bị che. Bản chia sẻ cần vẫn đủ để kiểm tra kết luận trong phạm vi được phép.

## 10. Ví dụ xuyên suốt: rà soát quyền quản trị production

Một tổ chức review 156 quan hệ cấp quyền đặc biệt thuộc phạm vi production đã xác định. Đây là số grant, không phải số người hay số tài khoản. Danh sách nền được lấy từ directory, IAM của hệ thống đích và PAM; các đường truy cập ngoài gateway cũng được đưa vào phạm vi.

### 10.1. Thu thập và đối soát

Nhóm điều phối lưu ba nhóm dữ liệu nguồn, ghi thời gian thu thập và xác nhận việc phân trang hoàn tất. Họ chuẩn hóa mã danh tính, phân giải nhóm lồng và nối service account với owner.

Một quyền xuất hiện đồng thời trong report PAM và report target không được đếm thành hai grant chỉ vì có hai nguồn. Ngược lại, hai đường cấp quyền độc lập đến cùng tài nguyên cần được phân biệt để có thể thu hồi đúng.

Sau đối soát, danh sách chính thức được gắn phiên bản `population-v1` với 156 grant. Reviewer được phân công theo owner hệ thống và nhu cầu nghiệp vụ; các trường hợp có xung đột được chuyển sang người có thẩm quyền phù hợp.

### 10.2. Ra quyết định

Kết quả trên danh sách nền:

| Quyết định | Số grant | Bằng chứng phải có |
|---|---:|---|
| Giữ quyền | 144 | Reviewer, lý do và phạm vi còn cần |
| Thu hồi | 8 | Quyết định, hạn xử lý và công việc thực thi |
| Ngoại lệ có thời hạn | 4 | Chấp thuận rủi ro, kiểm soát bù và ngày hết hạn |
| Tổng | 156 | Khớp đúng danh sách nền |

Tất cả 156 grant đã có quyết định, nên độ bao phủ quyết định trên danh sách nền là 156/156. Điều này chưa đồng nghĩa mọi hành động đã hoàn tất.

### 10.3. Thực thi và xác minh

Ở lần tổng hợp đầu, tám ticket thu hồi đều báo đã thực hiện nhưng chỉ sáu grant có bằng chứng xác minh. Hai grant còn lại chưa có export sau thay đổi từ hệ thống đích.

Báo cáo lúc này phải ghi rõ:

```text
Quyết định trên danh sách nền: 156/156
Thu hồi đã báo thực thi: 8/8
Thu hồi đã xác minh: 6/8
Thu hồi còn chờ xác minh: 2
Ngoại lệ có thời hạn: 4
```

Không báo “100% thu hồi hoàn tất” dựa trên trạng thái ticket. Sau khi kiểm tra hai grant còn lại, nhóm phát hiện một quyền vẫn tồn tại qua nhóm lồng. Họ sửa đúng membership nguồn, chờ đồng bộ và xác minh lại quyền hiệu lực.

Khi cả tám grant đã được xác minh, cuộc review có thể đạt điều kiện đóng theo quy trình đã xác định nếu bốn ngoại lệ được phê duyệt hợp lệ và được chuyển sang cơ chế theo dõi riêng. Báo cáo đóng vẫn phải nêu bốn ngoại lệ còn hiệu lực; không biến chúng thành quyền đã được loại bỏ.

### 10.4. Xử lý phát sinh trong kỳ

Các quyền được cấp mới sau bản chụp nền được theo dõi trong danh sách thay đổi riêng và xử lý theo cơ chế đã công bố. Báo cáo tách kết quả của danh sách nền khỏi kết quả bổ sung để người đọc biết mẫu số của từng chỉ số.

Nếu một grant trong danh sách nền bị xóa trước khi reviewer ra quyết định, có thể ghi nhận nó đã được thu hồi theo nguồn thay đổi có thể kiểm tra. Không xóa dòng khỏi lịch sử để làm danh sách trông đơn giản hơn.

## 11. Chỉ số hữu ích và những cách tính dễ gây hiểu nhầm

Một dashboard nên trình bày riêng tiến độ quyết định, tiến độ hành động và mức tồn đọng rủi ro.

| Chỉ số | Cách hiểu | Điểm cần công bố |
|---|---|---|
| Độ bao phủ quyết định | Grant đã có quyết định hợp lệ / grant phải review | Phiên bản population và cách xử lý delta |
| Tỷ lệ hành động đã xác minh | Hành động cần làm đã được xác minh / tổng hành động cần làm | Không dùng ticket đã đóng thay tử số |
| Thu hồi quá hạn | Hành động thu hồi chưa đạt mục tiêu sau hạn | Tách chưa thực thi và chưa xác minh |
| Grant không có owner | Quan hệ cấp quyền chưa xác định được trách nhiệm | Không loại khỏi mẫu số để làm đẹp chỉ số |
| Ngoại lệ còn hiệu lực | Số grant hoặc hồ sơ ngoại lệ đang được chấp thuận | Ghi rõ đơn vị đếm và ngày hết hạn |
| Giới hạn dữ liệu | Nguồn hoặc phạm vi chưa thu thập/phân giải đầy đủ | Chưa biết không được tính thành không có quyền |

Không trộn số người, tài khoản, grant và ticket trong cùng một phân số. Một ticket có thể xử lý nhiều grant; một grant có thể cần nhiều hành động trên các hệ thống khác nhau. Chỉ số phải chỉ rõ đang đếm đơn vị nào và khi nào một đơn vị được xem là hoàn tất.

Tỷ lệ giữ quyền cao không tự chứng minh review kém, cũng như tỷ lệ thu hồi cao không tự chứng minh review tốt. Cần xem danh sách đầu vào, chất lượng lý do, tính độc lập của reviewer và kết quả xử lý thực tế.

## 12. Những lỗi thường gặp và cách sửa bằng chứng

### Chỉ giữ ảnh chụp dashboard tổng hợp

Dashboard có thể cho biết 100% hoàn thành nhưng không nối được từng quyền với quyết định. Cần giữ danh sách đầu vào có phiên bản và bản ghi quyết định ở mức đủ chi tiết; ảnh tổng hợp chỉ là lớp hỗ trợ.

### Chỉ export account đã onboard vào PAM

Cách này bỏ sót quyền quản trị chưa được quản lý hoặc đường truy cập trực tiếp. Đối soát với hệ thống đích và công bố rõ giới hạn phạm vi nếu cuộc review chỉ bao phủ inventory của PAM.

### Xem account disabled là chắc chắn hết mọi khả năng truy cập

Trạng thái disabled ở một nguồn có thể chưa phản ánh token, session, credential dùng chung hoặc account khác của cùng chủ thể. Xác minh theo kiến trúc và các đường cấp quyền liên quan thay vì suy luận từ một cột trạng thái.

### Reviewer phê duyệt mà không có danh sách quyền

Một email “đồng ý” không gắn với phiên bản danh sách có thể khiến người kiểm tra không biết nội dung đã được chấp thuận. Liên kết quyết định với population cụ thể và giữ nội dung mà reviewer thực sự đã xem.

### Phê duyệt ngoại lệ không có ngày hết hạn

Ngoại lệ dễ trở thành quyền thường trực ngoài kiểm soát. Bổ sung owner, thời hạn, cơ chế nhắc việc, người chấp thuận rủi ro và bằng chứng của kiểm soát bù; theo dõi việc kết thúc hoặc gia hạn có quyết định mới.

### Đóng ticket trước khi kiểm tra quyền hiệu lực

Một thao tác cấu hình có thể thất bại, bị đồng bộ ngược hoặc vẫn còn đường cấp quyền khác. Giữ trạng thái chờ xác minh và chỉ đóng hành động khi có bằng chứng đạt mục tiêu đã xác định.

### Dùng dữ liệu cũ nhưng ghi thời điểm mới

Ngày tải file lên kho không phải ngày snapshot. Giữ riêng thời gian nguồn, thời gian xuất và thời gian lưu trữ. Khi dùng dữ liệu cũ, công bố khoảng trễ và cách đối soát thay đổi.

### Đính kèm secret để “chứng minh đã đổi”

Việc này tạo thêm bản sao credential và mở rộng rủi ro. Chỉ giữ mã tham chiếu, phiên bản hoặc sự kiện luân chuyển phù hợp, thời gian và kết quả xác minh; không lưu giá trị bí mật.

## 13. Bài tập thực hành

Giả sử bạn nhận một gói bằng chứng gồm bảng 60 tài khoản, email phê duyệt của quản lý và 5 ticket thu hồi đã đóng. Bảng không có thời gian xuất, không có đường cấp quyền và không phân biệt tài khoản cá nhân với service account.

Hãy thiết kế lại gói bằng chứng theo các bước sau:

1. Xác định phạm vi tài nguyên và đơn vị review. Giải thích vì sao 60 tài khoản chưa phải mẫu số đủ cho số grant cần review.
2. Liệt kê nguồn cần đối soát để tìm quyền kế thừa, nhóm lồng và quyền lấy credential từ vault.
3. Đề xuất các trường tối thiểu để nối danh tính, owner, entitlement và bản chụp dữ liệu.
4. Xác định reviewer phù hợp cho service account và tình huống người dùng tự review quyền của mình.
5. Viết một lý do giữ quyền có thể kiểm tra lại, một quyết định chuyển sang JIT và một ngoại lệ có thời hạn.
6. Chọn bằng chứng để xác minh từng ticket thu hồi, bao gồm trường hợp credential dùng chung đã được người dùng biết.
7. Viết báo cáo đóng phân biệt quyết định hoàn tất, hành động đã xác minh, phát hiện còn mở và ngoại lệ.

Kết quả tốt không cần nhiều ảnh chụp hơn. Nó cần một chuỗi dữ liệu đủ rõ để người khác đi từ phạm vi đến từng grant, từ grant đến quyết định và từ quyết định đến kết quả trên hệ thống đích.

## 14. Các điểm cần nhớ

- Bằng chứng access review phải chứng minh cả độ bao phủ danh sách đầu vào và kết quả xử lý từng quyền.
- Tài khoản, người dùng, grant, phiên truy cập và ticket là những đơn vị khác nhau; không dùng chúng thay thế nhau khi tính tiến độ.
- Log sử dụng quyền hỗ trợ quyết định nhưng không thay thế inventory về khả năng truy cập.
- Quyền JIT cần review cả eligibility, điều kiện kích hoạt và trạng thái còn hiệu lực phù hợp phạm vi.
- Quyết định thu hồi chỉ hoàn tất khi được thực thi đúng đường cấp quyền và xác minh đạt mục tiêu.
- Ngoại lệ cần người chấp thuận, thời hạn, kiểm soát bù và cơ chế theo dõi sau khi cuộc review đóng.
- Kho bằng chứng cần giữ được nguồn gốc, phiên bản và tính toàn vẹn, đồng thời bảo vệ thông tin về quyền đặc biệt và không chứa secret.
