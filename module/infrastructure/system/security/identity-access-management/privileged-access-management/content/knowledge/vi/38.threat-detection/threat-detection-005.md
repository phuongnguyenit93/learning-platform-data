# Privilege escalation: phát hiện leo thang đặc quyền trong hệ thống PAM

## 1. Mục tiêu và phạm vi

Privilege escalation là việc một chủ thể đạt được khả năng truy cập hoặc thực hiện hành động vượt khỏi ranh giới quyền trước đó của mình. Trong giám sát PAM, câu hỏi cần trả lời là: **ai đã đạt quyền gì, bằng con đường nào, trên tài nguyên nào và có được phép tại thời điểm đó hay không?**

Một kỹ sư dùng quyền vận hành ứng dụng để trở thành quản trị viên máy chủ là ví dụ leo thang theo chiều dọc. Một tài khoản lấy được quyền của tài khoản ngang cấp để tiếp cận một tập tài nguyên khác thường được gọi là dịch chuyển theo chiều ngang. Hai tình huống có thể xuất hiện trong cùng một chuỗi tấn công, nhưng bài này tập trung vào việc phát hiện **quyền hiệu lực tăng lên hoặc ranh giới đặc quyền bị vượt qua**.

Không phải mọi lần dùng quyền quản trị đều là tấn công. PAM có thể chủ động cấp quyền tạm thời bằng JIT, giới hạn thao tác bằng JEA và ghi lại phiên làm việc. Ngược lại, việc một phiên đã đi qua PAM không bảo đảm tất cả hành động trong phiên đều hợp lệ.

Sau bài học, người học cần có khả năng:

- Phân biệt yêu cầu nâng quyền, quyền được cấp, quyền thực sự có hiệu lực và việc sử dụng quyền đó.
- Nối dữ liệu PAM với dữ liệu danh tính, tiến trình, hệ điều hành và mặt phẳng quản trị.
- Viết giả thuyết phát hiện có bằng chứng, có điều kiện dữ liệu và có cách xử lý ngoại lệ.
- Phân loại cảnh báo theo mức xác thực và mức ảnh hưởng.
- Thiết kế phản ứng có kiểm soát, đồng thời giữ được bằng chứng phục vụ điều tra.

Bài học sử dụng log và quy tắc giả lập để diễn giải cơ chế. Các tên field, định dạng và ngưỡng thời gian minh họa không phải cấu hình dùng trực tiếp cho một sản phẩm PAM, EDR hay SIEM cụ thể.

## 2. Nhận diện đúng sự thay đổi đặc quyền

### 2.1. Bốn trạng thái cần tách biệt

Một yêu cầu cấp quyền có thể bị từ chối. Một yêu cầu được phê duyệt có thể chưa được áp dụng. Một thay đổi đã ghi vào thư mục danh tính có thể chưa có mặt trong token hoặc phiên hiện tại. Một chủ thể đã có quyền có thể chưa sử dụng quyền đó.

| Trạng thái | Bằng chứng điển hình | Điều có thể kết luận |
| --- | --- | --- |
| Yêu cầu hoặc thử nâng quyền | Yêu cầu JIT, xác thực thất bại, thao tác bị từ chối | Có ý định hoặc có lần thử; chưa chứng minh thành công |
| Cấp hoặc thay đổi quyền | Thêm thành viên nhóm, sửa policy, tạo binding | Cấu hình quyền đã thay đổi; cần xác minh phạm vi và hiệu lực |
| Nhận ngữ cảnh đặc quyền | Phiên mới có token đặc quyền, tiến trình có effective UID khác, nhận vai trò mới | Chủ thể đã có ngữ cảnh đặc quyền tại điểm quan sát |
| Dùng khả năng đặc quyền | Thay đổi cấu hình nhạy cảm, thực hiện hành động quản trị được ghi nhận | Quyền đã được sử dụng cho một hành động cụ thể |

Không nâng mức kết luận từ “thử” lên “thành công” chỉ vì nhiều lần thử xảy ra liên tiếp. Khi dữ liệu chỉ có sự kiện sửa nhóm, nên báo “thay đổi quyền quản trị được quan sát” thay vì khẳng định đã có tiến trình quản trị chạy.

### 2.2. Quyền danh nghĩa và quyền hiệu lực

Quyền danh nghĩa là những gì cấu hình đang thể hiện: thành viên nhóm, role assignment, ACL, policy hoặc binding. Quyền hiệu lực còn phụ thuộc vào những yếu tố như:

- Token, vé xác thực, phiên đăng nhập hoặc credential đang được dùng.
- Phạm vi tài nguyên, điều kiện của policy và các ràng buộc từ chối.
- Nhóm lồng nhau, vai trò kế thừa hoặc cơ chế ủy quyền.
- Thời gian hiệu lực và độ trễ đồng bộ.
- Ranh giới máy chủ, tenant, namespace, container hoặc miền quản trị.

Vì vậy, một role mang tên “read-only” chưa đủ để kết luận an toàn nếu nó cho phép sửa một đối tượng có thể cấp quyền tiếp. Ngược lại, tài khoản mang tên “admin” không tự chứng minh rằng phiên đang xét có toàn quyền.

Để phát hiện, cần mô hình hóa các khả năng có ảnh hưởng thực tế: thay đổi quyền truy cập, cấp credential, sửa dịch vụ chạy đặc quyền, truy cập bí mật hoặc thực hiện hành động quản trị trên tài nguyên quan trọng.

### 2.3. Nâng quyền hợp lệ và leo thang trái phép

Một lần nâng quyền hợp lệ phải khớp nhiều chiều, không chỉ khớp tên người dùng:

- Đúng người hoặc workload được cấp quyền.
- Đúng tài khoản, vai trò và tài nguyên đích.
- Đúng thời gian hiệu lực.
- Đúng loại thao tác và ràng buộc JEA nếu có.
- Đúng nguồn truy cập và đường đi được chính sách yêu cầu.
- Có căn cứ phê duyệt hoặc căn cứ chính sách tương ứng.

Ví dụ, quyền JIT cho phép khởi động lại một dịch vụ trên máy chủ ứng dụng trong 20 phút không bao hàm quyền thêm tài khoản vào nhóm quản trị miền. Mã ticket có thật không làm mọi hành động cùng phiên trở thành hợp lệ.

## 3. Những con đường cần quan sát

### 3.1. Từ phiên người dùng đến tiến trình đặc quyền trên máy chủ

Trên Linux, việc chuyển từ UID người dùng sang effective UID đặc quyền có thể là kết quả hợp lệ của sudo, chương trình set-user-ID hoặc một dịch vụ trung gian. Linux capabilities cũng có thể cấp các khả năng nhạy cảm mà không cần effective UID bằng 0.

Trên Windows, cần quan sát token, mức integrity, tài khoản hiệu lực và chuỗi tiến trình. UAC elevation của một tài khoản quản trị là thay đổi ngữ cảnh cần kiểm tra; nó không đồng nghĩa với việc tiến trình trở thành SYSTEM. Khác biệt giữa tài khoản gốc của người vận hành và tài khoản dùng cho tiến trình phải được giữ lại trong dữ liệu.

Những tín hiệu đáng điều tra gồm:

- Tiến trình đặc quyền xuất phát từ chuỗi tiến trình không phù hợp với vai trò máy.
- Tài khoản dịch vụ xuất hiện trong phiên tương tác không được dự kiến.
- Công cụ nâng quyền hợp lệ được gọi ngoài phạm vi JEA hoặc ngoài cửa sổ JIT.
- Một tiến trình bắt đầu truy cập tài nguyên quản trị trong khi dữ liệu cấp quyền không giải thích được sự thay đổi.

Một executable có tên quen thuộc không đủ để cho phép hành vi. Cần kiểm tra nguồn thực thi, danh tính, tiến trình cha, loại phiên, tài nguyên và hành động.

### 3.2. Từ quyền sửa cấu hình đến quyền điều khiển

Một chủ thể có thể không được phép đăng nhập bằng tài khoản quản trị nhưng lại có quyền sửa đối tượng mà một dịch vụ đặc quyền sẽ sử dụng. Ví dụ: cấu hình dịch vụ, định nghĩa tác vụ, tệp cấu hình nhạy cảm hoặc cơ chế triển khai tự động.

Giả thuyết phòng thủ ở đây là: **chủ thể ít quyền sửa một đầu vào có ảnh hưởng đến thực thi đặc quyền, sau đó xuất hiện thực thi hoặc hành động đặc quyền liên quan**.

Cần phân biệt:

1. Có khả năng sửa đối tượng.
2. Đối tượng thực sự bị sửa.
3. Thành phần đặc quyền thực sự dùng bản sửa.
4. Hành động nhạy cảm tiếp theo đã xảy ra.

Phát hiện chỉ ở bước 2 có giá trị cảnh báo thay đổi nguy hiểm, nhưng chưa đủ để khẳng định bước 3 và bước 4.

### 3.3. Từ thay đổi danh tính đến quyền quản trị

Các sự kiện cần quan sát gồm thêm thành viên vào nhóm đặc quyền, sửa ACL cho đối tượng danh tính, thay đổi quyền ủy quyền hoặc sửa policy có khả năng cấp quyền.

Với nhóm lồng nhau, một lần thêm thành viên vào nhóm ít nổi bật có thể tạo quyền quản trị gián tiếp. Cần xét đồ thị quyền tại thời điểm thay đổi, thay vì chỉ kiểm tra danh sách tên nhóm cố định.

Quyền mới có thể chỉ xuất hiện sau một lần xác thực hoặc nhận token tiếp theo. Khi điều tra, cần ghi nhận cả thời điểm thay đổi cấu hình và thời điểm ngữ cảnh quyền mới được quan sát.

### 3.4. Từ workload đến mặt phẳng quản trị

Trong môi trường đám mây hoặc Kubernetes, cần chú ý những quyền cho phép tạo quyền khác:

- Tạo hoặc sửa vai trò và policy.
- Gán vai trò cho một principal khác.
- Tạo binding tới vai trò đặc quyền.
- Sử dụng cơ chế impersonation được cấu hình.
- Truy cập credential hoặc bí mật có phạm vi lớn hơn quyền hiện tại.
- Sửa workload có khả năng chạy với danh tính hoặc ngữ cảnh đặc quyền hơn.

Trong Kubernetes, cần xem cả RoleBinding, ClusterRoleBinding, đối tượng role được tham chiếu và phạm vi namespace hoặc cluster. Các quyền đặc biệt như bind, escalate và impersonate phải được đánh giá theo ngữ nghĩa RBAC thực tế của hệ thống.

Không mặc định rằng root trong container tương đương root trên máy chủ. Muốn kết luận vượt ranh giới host phải có bằng chứng về tài nguyên host, namespace, mount, capability hoặc hành động trên host có liên quan.

### 3.5. Credential bị sử dụng sai và leo thang đặc quyền

Việc sử dụng credential quản trị bị lấy cắp có thể tạo ra một phiên đặc quyền mà không xuất hiện sự kiện sửa quyền trên máy đích. Trong trường hợp đó, phát hiện chỉ dựa vào “nhóm quản trị vừa thay đổi” sẽ bỏ sót.

Cần nối thêm dữ liệu như lấy bí mật từ vault, phiên truy cập quản trị, xác thực vào đích và hành động tiếp theo. Việc không tìm thấy sự kiện checkout vault chỉ có ý nghĩa khi luồng checkout được yêu cầu và nguồn dữ liệu đó đang đầy đủ.

Một cảnh báo có thể đồng thời mang nhãn sử dụng credential trái phép, dịch chuyển ngang và sử dụng đặc quyền. Nhãn mô tả không thay thế chuỗi bằng chứng.

## 4. Thiết kế dữ liệu để nối được người, phiên và quyền

### 4.1. Các nguồn dữ liệu chủ yếu

| Nguồn | Dữ liệu cần lấy | Giá trị đối với phát hiện |
| --- | --- | --- |
| PAM | Request, approval, grant, revoke, phiên, tài khoản đích, kết quả thao tác | Đối chiếu quyền được phép với hành vi thực tế |
| IdP hoặc thư mục danh tính | Xác thực, thay đổi nhóm, role, ACL, đối tượng đích | Nhận diện ai thay đổi quyền và ai hưởng quyền |
| Hệ điều hành hoặc EDR | Tiến trình, tài khoản hiệu lực, token hoặc UID, chuỗi tiến trình | Chứng minh ngữ cảnh thực thi |
| Control plane | Thay đổi policy, role assignment, binding, impersonation | Nhìn thấy con đường cấp quyền qua API |
| Vault | Truy xuất, cấp, thay đổi, thu hồi credential | Nối việc nhận bí mật với sử dụng đặc quyền |
| CMDB và quản lý thay đổi | Chủ sở hữu, mức quan trọng, lịch bảo trì, mục đích thay đổi | Đánh giá phạm vi ảnh hưởng và ngoại lệ |

PAM session recording rất hữu ích nhưng không bao phủ mặc nhiên mọi đường truy cập. Cần biết rõ tài nguyên nào còn cho phép truy cập trực tiếp, API nào không đi qua proxy và workload nào không dùng cơ chế PAM tương tác.

### 4.2. Mô hình sự kiện chuẩn hóa

Một schema tối thiểu có thể gồm:

```yaml
event_id: evt-005
event_time: "2026-11-20T02:03:04Z"
ingest_time: "2026-11-20T02:03:08Z"
source: host_audit
event_type: privileged_context_observed
outcome: success

actor_id: user:ops-17
effective_principal_id: account:root@app-01
beneficiary_id: user:ops-17
target_id: host:app-01
scope: host
action: service_restart

session_id: pam-session-417
host_session_id: app-01:boot-42:login-806
process_entity_id: app-01:boot-42:process-5329
parent_process_entity_id: app-01:boot-42:process-5310
grant_id: jit-208

privilege_before: app_operator
privilege_after: local_admin
raw_event_reference: evidence/host-audit/evt-005
```

Các field có thể không xuất hiện trong mọi nguồn. Không tự điền grant_id hoặc actor_id theo suy đoán chỉ để làm cho phép join thành công. Khi liên kết bằng suy luận, lưu rõ phương pháp, độ tin cậy và những ứng viên có thể bị nhầm.

Ba danh tính cần tách riêng:

- **Actor:** người hoặc workload thực hiện thao tác.
- **Effective principal:** danh tính mà hành động thực sự chạy dưới quyền.
- **Beneficiary:** chủ thể nhận được quyền từ thay đổi.

Nếu một quản trị viên thêm tài khoản B vào nhóm đặc quyền, actor là quản trị viên và beneficiary là B. Nếu kỹ sư điều khiển phiên dùng tài khoản quản trị được vault cấp, người vận hành và tài khoản đích là hai thực thể khác nhau.

### 4.3. Khóa tương quan và chất lượng thời gian

Tên tài khoản, PID hoặc địa chỉ IP đơn lẻ thường không phải khóa đủ mạnh. PID có thể tái sử dụng; IP có thể dùng chung hoặc thay đổi; cùng tên đăng nhập có thể tồn tại ở nhiều miền.

Ưu tiên các định danh ổn định như object ID, SID, ID principal của nhà cung cấp, ID phiên PAM và định danh tiến trình do EDR tạo. Các định danh cục bộ phải đi kèm host, phạm vi nguồn và vòng đời phù hợp, chẳng hạn boot ID.

Dùng event_time để phân tích chuỗi hành vi và ingest_time để đánh giá độ trễ nhận log. Thiết kế cửa sổ tương quan phải tính tới:

- Sai lệch đồng hồ đã đo được.
- Độ trễ truyền và xử lý từng nguồn.
- Sự kiện đến không đúng thứ tự.
- Sự kiện trùng lặp hoặc được gửi lại.
- Thời điểm áp dụng quyền khác thời điểm phê duyệt.

Không làm rộng cửa sổ tùy ý để bù dữ liệu kém. Cửa sổ quá lớn dễ nối một yêu cầu hợp lệ với một hành động không liên quan.

## 5. Diễn giải tín hiệu theo môi trường

### 5.1. Linux

Đối với sudo, cần giữ tài khoản gọi, tài khoản đích, command hoặc loại hành động, host, phiên và kết quả. Log chấp nhận một lần gọi sudo chưa luôn đủ để chứng minh toàn bộ hành động bên trong đã hoàn tất thành công.

Đối với dữ liệu audit hoặc EDR, các giá trị như real UID, effective UID và login UID có vai trò khác nhau. Login UID, khi được thiết lập và bảo toàn đúng, giúp nối hành động về phiên đăng nhập ban đầu; nó không phải bằng chứng tuyệt đối về con người thực sự điều khiển phiên.

Các trường hợp cần tách khỏi nhau:

- Dịch vụ root khởi động theo cấu hình thông thường.
- Người vận hành nâng quyền theo một grant còn hiệu lực.
- Người dùng chạy công cụ hợp lệ nhưng với hành động ngoài phạm vi.
- Tiến trình có capability nhạy cảm dù effective UID không bằng 0.
- Tiến trình chuyển sang đặc quyền mà nguồn quan sát hiện có không giải thích được.

Đừng dùng quy tắc “mọi tiến trình root đều đáng ngờ”. Hãy phát hiện sự thay đổi hoặc con đường bất thường so với chức năng tài nguyên, đồng thời đối chiếu phạm vi cấp quyền.

### 5.2. Windows

Một số sự kiện Windows Security thường được dùng làm thành phần tương quan:

| Sự kiện | Cách sử dụng | Giới hạn diễn giải |
| --- | --- | --- |
| 4624 | Nhận diện đăng nhập thành công, tài khoản và ngữ cảnh phiên | Không tự chứng minh có hành động quản trị |
| 4648 | Nhận diện lần thử dùng credential được chỉ định rõ | Không tự chứng minh xác thực ở đích thành công |
| 4672 | Nhận diện đặc quyền đặc biệt được gán cho một lần đăng nhập | Thường có ở tài khoản hệ thống hoặc quản trị hợp lệ; không tự chứng minh tấn công |
| 4688 | Nhận diện tiến trình mới và dữ liệu tiến trình được audit cung cấp | Khả năng có command line, token và thông tin liên quan phụ thuộc cấu hình, phiên bản và nguồn thu thập |
| 4728, 4732, 4756 | Theo dõi thêm thành viên vào nhóm bảo mật global, local hoặc universal tương ứng | Phải xét nhóm đích, phạm vi quản trị và quyền hiệu lực thực tế |

Chỉ kỳ vọng các sự kiện khi audit policy, nguồn ghi và pipeline thu thập tương ứng đã được cấu hình. “Không có 4688” có thể là khoảng trống quan sát, không phải bằng chứng rằng không có tiến trình.

Khi nối Logon ID, cần giữ phạm vi host và vòng đời phù hợp. Không join một Logon ID giữa nhiều máy như một ID toàn cục. Khi có telemetry tiến trình chất lượng hơn, ưu tiên định danh tiến trình bền vững của nguồn đó.

Command line có thể chứa dữ liệu nhạy cảm. Quy trình thu thập và điều tra cần giới hạn người đọc, tránh sao chép bí mật vào ticket và ưu tiên tham chiếu đến bằng chứng gốc được kiểm soát.

### 5.3. Cloud và Kubernetes

Với control plane, log thay đổi quyền cần cho biết actor, beneficiary, policy hoặc role bị thay đổi, scope, outcome và request ID. Khi có chuỗi assume-role hoặc impersonation, cần giữ cả principal gọi và principal được sử dụng.

Một thay đổi role assignment chưa chứng minh mọi API đích đã chấp nhận quyền mới. Cần tìm lần nhận credential, token hoặc hành động nhạy cảm tiếp theo nếu mục tiêu cảnh báo là “đã sử dụng quyền”.

Các hệ thống phân quyền có điều kiện, quyền từ chối hoặc cơ chế kế thừa khác nhau. Đánh giá hiệu lực phải theo môi trường đang vận hành. Không đồng nhất một role tên “Owner” hoặc “Administrator” giữa các nền tảng.

## 6. Xây dựng giả thuyết phát hiện

Một giả thuyết tốt nêu rõ hành vi, điều kiện dữ liệu, phạm vi và cách xác minh. Có thể bắt đầu với bốn nhóm sau.

### 6.1. Ngữ cảnh đặc quyền không có grant phù hợp

**Giả thuyết:** một phiên trên tài nguyên thuộc phạm vi PAM nhận hoặc sử dụng đặc quyền mà không có grant hợp lệ cho cùng chủ thể, đích, hành động và thời gian.

Điều kiện triển khai:

- Biết tài nguyên nào bắt buộc dùng PAM.
- Biết nguồn grant và revoke đang hoạt động.
- Có khóa nối phiên hoặc danh tính đủ tin cậy.
- Có bằng chứng về quyền hiệu lực hoặc hành động đặc quyền.

Kết quả đối chiếu grant nên có ít nhất ba trạng thái:

```text
MATCHED:
  Có grant phù hợp và có đủ dữ liệu để kiểm tra các ràng buộc.

UNMATCHED:
  Đã tìm trên dữ liệu đầy đủ trong phạm vi xét nhưng không có grant phù hợp.

UNKNOWN:
  Thiếu nguồn, dữ liệu đến muộn, không nối được identity hoặc thiếu policy.
```

UNKNOWN cần được điều tra hoặc đưa vào cảnh báo chất lượng dữ liệu. Không tự động coi UNKNOWN là hợp lệ, cũng không mô tả nó như bằng chứng chắc chắn rằng người dùng đã vượt PAM.

### 6.2. Thay đổi quyền rồi sử dụng đặc quyền

**Giả thuyết:** một chủ thể được thêm vào nhóm hoặc vai trò đặc quyền, sau đó xuất hiện ngữ cảnh hoặc hành động đặc quyền trên tài nguyên liên quan.

Phép tương quan phải nối đúng beneficiary của thay đổi quyền với effective principal hoặc danh tính được dùng tiếp theo. Không chỉ nối actor của sự kiện sửa nhóm với người đăng nhập.

Cần kiểm tra thêm:

- Actor có được phép cấp quyền này không?
- Thay đổi có nằm trong ticket hoặc quy trình được phê duyệt không?
- Quyền có phạm vi rộng hơn yêu cầu không?
- Có thu hồi đúng hạn không?
- Hành động tiếp theo có phù hợp mục tiêu cấp quyền không?

Một lần cấp quyền hợp lệ vẫn có thể tạo ra cảnh báo khi quyền vượt phạm vi hoặc không được thu hồi.

### 6.3. Sửa đối tượng nhạy cảm rồi có thực thi đặc quyền

**Giả thuyết:** tài khoản ít quyền sửa một đối tượng có ảnh hưởng đến thực thi, sau đó thành phần đặc quyền sử dụng đối tượng đó.

Chuỗi bằng chứng nên có định danh đối tượng ổn định, phiên bản hoặc hash khi phù hợp, actor sửa, thời điểm áp dụng và tiến trình hoặc hành động chịu ảnh hưởng.

Chỉ dựa vào “hai sự kiện gần nhau” dễ tạo liên kết sai. Một đợt triển khai hợp lệ có thể sửa hàng trăm đối tượng trước khi dịch vụ khởi động lại. Phải nối được chính đối tượng hoặc bản cấu hình được tiêu thụ.

### 6.4. Sử dụng quyền sau khi hết hạn hoặc thu hồi

**Giả thuyết:** hành động đặc quyền tiếp tục sau khi grant hết hạn hoặc đã có sự kiện revoke.

Cần phân biệt:

- Grant đã hết hạn trên hệ thống quản lý.
- Nhóm hoặc policy đã được gỡ.
- Credential hoặc token đã được vô hiệu hóa.
- Phiên đang chạy đã bị đóng hoặc giảm quyền.
- Hệ thống đích thực sự từ chối các hành động mới.

Tùy nền tảng, xóa membership hoặc đổi mật khẩu không lập tức làm mọi token và phiên đã cấp mất hiệu lực. Cảnh báo nên chỉ ra khoảng cách giữa ý định thu hồi và hiệu lực quan sát được, không hứa rằng một thao tác duy nhất xử lý hết mọi ngữ cảnh.

## 7. Logic tương quan minh họa

Đoạn sau là pseudocode, không phải cú pháp của một SIEM cụ thể:

```text
for each successful privileged_event:
    if duplicate(event_id, source):
        continue

    identity = resolve_actor_and_effective_principal(privileged_event)
    coverage = evaluate_required_source_coverage(
        target=privileged_event.target_id,
        event_time=privileged_event.event_time
    )

    grants = find_candidate_grants(
        identity=identity,
        target=privileged_event.target_id,
        event_time=privileged_event.event_time
    )

    match = evaluate_grant_constraints(
        candidates=grants,
        action=privileged_event.action,
        source_context=privileged_event.source_context,
        session_id=privileged_event.session_id
    )

    if identity.is_ambiguous or coverage.is_incomplete:
        emit_investigation(
            classification="authorization_unknown",
            observed_evidence=privileged_event,
            missing_evidence=coverage.missing_sources
        )
    else if match == "UNMATCHED":
        emit_alert(
            classification="unapproved_privileged_activity",
            observed_evidence=privileged_event,
            authorization_evidence=grants
        )
    else if violates_session_policy(privileged_event, grants):
        emit_alert(
            classification="privileged_activity_outside_scope",
            observed_evidence=privileged_event,
            authorization_evidence=grants
        )
```

Trong triển khai thực tế, việc đối chiếu phải hỗ trợ các policy không phụ thuộc session ID, như một số luồng workload hoặc JIT không qua proxy. Không bỏ qua ràng buộc cần thiết chỉ vì một trường khóa không có trong nguồn.

Đối với dữ liệu đến muộn, có thể phát cảnh báo sơ bộ rồi cập nhật khi đủ bằng chứng. Phải giữ lịch sử đánh giá để người điều tra biết vì sao cảnh báo đổi phân loại.

### Gói bằng chứng của một cảnh báo

Một cảnh báo hữu ích nên chứa:

- Hành vi đã quan sát và mức kết luận: thử, thay đổi quyền, nhận quyền hay sử dụng quyền.
- Actor, effective principal, beneficiary và tài nguyên đích.
- Mốc thời gian sự kiện và độ trễ dữ liệu liên quan.
- Grant hoặc policy đã đối chiếu cùng lý do khớp hay không khớp.
- Định danh phiên, tiến trình, đối tượng quyền và sự kiện nguồn.
- Khoảng trống dữ liệu, độ tin cậy của liên kết và ảnh hưởng dự kiến.
- Liên kết đến bằng chứng gốc có kiểm soát truy cập.

Không đưa credential, token hoặc toàn bộ bản ghi phiên nhạy cảm vào phần mô tả cảnh báo.

## 8. Bài thực hành với log giả lập

### 8.1. Bối cảnh

Máy chủ app-01 thuộc phạm vi bắt buộc quản trị qua PAM. Người vận hành ops-17 được cấp quyền khởi động lại dịch vụ billing-api từ 02:00 đến trước 02:20 UTC. Grant không cho phép sửa danh tính hoặc thêm tài khoản quản trị.

Các nguồn PAM, audit host và thư mục danh tính đều được xác nhận đầy đủ cho khoảng thời gian bài thực hành. Thời gian được chuẩn hóa và độ trễ log đã nằm trong cửa sổ chờ của phép tương quan.

```yaml
events:
  - id: e1
    time: "2026-11-20T02:00:00Z"
    type: grant_activated
    grant_id: jit-208
    actor: user:ops-17
    target: host:app-01
    allowed_action: restart_service:billing-api
    valid_until: "2026-11-20T02:20:00Z"

  - id: e2
    time: "2026-11-20T02:05:00Z"
    type: privileged_action
    outcome: success
    actor: user:ops-17
    effective_principal: account:root@app-01
    target: host:app-01
    action: restart_service:billing-api
    session_id: pam-session-417
    grant_id: jit-208

  - id: e3
    time: "2026-11-20T02:08:00Z"
    type: privileged_group_member_added
    outcome: success
    actor: user:ops-17
    beneficiary: user:temp-ops
    target: group:local-admin@app-01
    session_id: pam-session-417

  - id: e4
    time: "2026-11-20T02:10:00Z"
    type: privileged_context_observed
    outcome: success
    actor: user:temp-ops
    effective_principal: account:temp-ops@app-01
    target: host:app-01
    privilege_after: local_admin
    host_session_id: app-01:boot-42:login-990
```

Ở đây, privileged_group_member_added là sự kiện chuẩn hóa do bài thực hành quy ước. Tên này không giả định mọi hệ điều hành dùng cùng cơ chế nhóm hoặc cùng event ID.

### 8.2. Cách phân tích

**Sự kiện e2:** hành động khớp chủ thể, máy đích, thời gian và loại thao tác của jit-208. Với giả định dữ liệu và ràng buộc trong bài đầy đủ, đây là sử dụng đặc quyền được phê duyệt.

**Sự kiện e3:** đã có bằng chứng thêm thành viên vào nhóm quản trị. Grant jit-208 không cho phép thay đổi này. Cần phát hiện hành động ngoài phạm vi, dù e3 dùng cùng phiên PAM với e2.

**Sự kiện e4:** beneficiary của e3 là temp-ops, trùng danh tính nhận ngữ cảnh quản trị trong e4. Chuỗi e3 → e4 tăng độ tin cậy rằng thay đổi quyền đã có hiệu lực. Cần xác nhận quan hệ giữa nhóm local-admin và quyền local_admin bằng dữ liệu quyền của môi trường, thay vì chỉ dựa vào tên.

Chưa có bằng chứng temp-ops đã đọc bí mật, sửa dịch vụ hoặc phá hoại máy chủ. Báo cáo đúng là đã quan sát cấp quyền ngoài phạm vi và ngữ cảnh quản trị tiếp theo, không phải đã chứng minh mọi hậu quả có thể xảy ra.

### 8.3. Các biến thể để kiểm tra

| Biến thể | Kết quả mong đợi |
| --- | --- |
| e3 bị từ chối, không có thay đổi quyền thành công | Cảnh báo lần thử nếu policy yêu cầu; không kết luận đã cấp quyền |
| e3 do hệ thống cấp quyền hợp lệ thực hiện, có grant riêng đúng phạm vi | Đối chiếu grant riêng; không gán nhầm jit-208 |
| Chỉ có e3, thiếu e4 | Báo thay đổi quyền ngoài phạm vi; chưa khẳng định đã sử dụng ngữ cảnh mới |
| Có e4 nhưng nguồn PAM bị mất log trong khoảng xét | Đánh dấu thiếu bằng chứng cấp quyền; điều tra authorization_unknown |
| Có e4 ở máy khác không chịu tác động của nhóm trong e3 | Không nối trực tiếp; xác minh đồ thị quyền và phạm vi tài nguyên |
| e4 đến SIEM trước e3 do độ trễ | Tương quan theo thời gian sự kiện và cập nhật sau khi đủ dữ liệu |
| e2 xảy ra sau 02:20 UTC | Kiểm tra hết hạn, hiệu lực thu hồi và policy cho phiên đang mở |
| temp-ops có quyền quản trị từ trước, e3 chỉ thay đổi một đường cấp quyền khác | Không khẳng định đây là lần đầu đạt quyền; vẫn xét thay đổi ngoài phạm vi |

Bài thực hành chỉ cần dữ liệu giả lập. Không cần thử leo thang trên máy thật để kiểm tra tính đúng của phép tương quan.

## 9. Triage và phản ứng

### 9.1. Xác minh cảnh báo

Người phân tích nên lần lượt xác định:

1. Sự kiện nguồn có chứng minh thành công hay chỉ ghi nhận yêu cầu?
2. Danh tính gốc, danh tính hiệu lực và người nhận quyền đã được phân biệt chưa?
3. Phạm vi quyền trước và sau thay đổi là gì?
4. Grant hoặc policy nào giải thích hành động, và có khớp đầy đủ ràng buộc không?
5. Có bằng chứng quyền đã được sử dụng không?
6. Những phiên, credential, máy chủ và tài nguyên nào còn có thể bị ảnh hưởng?

Lưu cả bằng chứng ủng hộ lẫn bằng chứng phản bác giả thuyết. Nếu dữ liệu chưa đủ, diễn đạt rõ điều chưa biết và nguồn cần thu thập.

### 9.2. Ưu tiên theo ảnh hưởng và độ tin cậy

Mức ảnh hưởng và độ tin cậy là hai trục khác nhau. Một thay đổi quyền trên hệ thống cấp danh tính trung tâm có thể có ảnh hưởng rất lớn nhưng liên kết actor còn mơ hồ. Một hành động ngoài phạm vi trên máy thử nghiệm có thể rất chắc chắn nhưng phạm vi tác động nhỏ hơn.

Những yếu tố làm tăng ưu tiên gồm quyền quản trị hạ tầng danh tính, khả năng cấp credential tiếp, tài nguyên chứa bí mật, số lượng đích chịu ảnh hưởng và việc còn phiên đặc quyền hoạt động.

Không chọn một ngưỡng điểm tùy ý rồi coi nó là bằng chứng. Nếu dùng điểm rủi ro, cần hiệu chỉnh bằng dữ liệu vận hành và giữ lại lý do đóng góp của từng yếu tố.

### 9.3. Hành động ứng phó

Phản ứng có thể gồm thu hồi grant, ngắt phiên PAM, vô hiệu hóa token hoặc credential theo khả năng nền tảng, cô lập máy, gỡ quyền cấp sai và chặn đường truy cập liên quan.

Chọn hành động theo mức bằng chứng, phạm vi ảnh hưởng và runbook đã được phê duyệt. Việc dừng tài khoản dịch vụ hoặc ngắt một phiên khẩn cấp có thể gây gián đoạn, nên cần biết chủ sở hữu và phương án duy trì dịch vụ.

Trước hoặc song song với containment, bảo toàn các bằng chứng dễ mất: định danh phiên, metadata tiến trình, policy trước/sau, lịch sử grant/revoke và vị trí log gốc. Không trì hoãn containment cần thiết chỉ để hoàn thành một danh sách thu thập không phù hợp tình huống.

Sau khi thu hồi, phải xác minh hiệu lực tại đích. “API revoke trả về thành công” và “không còn khả năng thực hiện hành động quản trị” là hai điều khác nhau.

## 10. Giảm nhiễu và theo dõi điểm mù

### 10.1. Ngoại lệ có phạm vi

Triển khai tự động, bảo trì, vận hành backup và tài khoản khẩn cấp có thể tạo hành vi đặc quyền hợp lệ. Ngoại lệ nên ràng buộc vào chủ thể, đích, loại hành động, thời gian và chủ sở hữu, kèm ngày hết hạn.

Không miễn toàn bộ cảnh báo chỉ vì tài khoản nằm trong nhóm quản trị hoặc có tên chứa chuỗi “service”. Không miễn cả phiên khi chỉ một hành động đã được giải thích.

Break-glass là luồng ngoại lệ được giám sát, không phải vùng miễn phát hiện. Cần đối chiếu căn cứ kích hoạt, phạm vi sử dụng, giám sát tăng cường và việc hoàn trả quyền sau sự cố.

### 10.2. Điểm mù cần ghi nhận

- Đường truy cập quản trị trực tiếp không đi qua PAM.
- Workload hoặc API không có session recording.
- Thiếu process telemetry hoặc audit policy.
- Mất log thay đổi quyền trong thư mục danh tính.
- Credential đã cấp được dùng ngoài phiên được quan sát.
- Quyền gián tiếp qua nhóm lồng nhau hoặc đối tượng có thể sửa.
- Dữ liệu grant không phản ánh việc token vẫn còn hiệu lực.
- Audit pipeline bị gián đoạn hoặc bị can thiệp.

Nên có cảnh báo sức khỏe nguồn dữ liệu riêng. Nếu coverage thay đổi, độ tin cậy của các phát hiện phụ thuộc nguồn đó cũng phải được cập nhật.

### 10.3. Chỉ số vận hành

Theo dõi tỷ lệ tài nguyên đặc quyền có telemetry phù hợp, tỷ lệ sự kiện nối được actor với effective principal, độ trễ phát hiện và thời gian từ revoke đến xác minh mất quyền.

Có thể đo thêm số cảnh báo có đủ bằng chứng, tỷ lệ UNKNOWN do thiếu dữ liệu và số ngoại lệ quá hạn. Một hệ thống ít cảnh báo chưa chắc tốt nếu nguồn dữ liệu đang mất hoặc phạm vi quan sát quá hẹp.

## 11. Những lỗi thiết kế thường gặp

| Lỗi | Hệ quả | Cách điều chỉnh |
| --- | --- | --- |
| Coi một sự kiện đặc quyền đơn lẻ là bằng chứng tấn công | Nhiễu lớn, kết luận quá mức | Ghép ngữ cảnh, grant và bằng chứng hành động |
| Join bằng tên tài khoản hoặc IP đơn lẻ | Gán nhầm chủ thể và phiên | Dùng định danh ổn định cùng phạm vi nguồn |
| Chỉ kiểm tra quyền root hoặc SYSTEM | Bỏ sót capability, role và quyền cấp quyền | Mô hình hóa khả năng nhạy cảm theo tài nguyên |
| Coi ticket tồn tại là đủ hợp lệ | Bỏ qua hành động vượt mục đích | Kiểm tra chủ thể, đích, thời gian và thao tác |
| Coi thiếu grant trong SIEM là chắc chắn không có grant | Sai kết luận khi dữ liệu đến muộn | Đánh giá coverage và dùng trạng thái UNKNOWN |
| Coi gỡ nhóm hoặc đổi mật khẩu là thu hồi toàn bộ | Bỏ sót token và phiên còn sống | Xác minh hiệu lực tại từng lớp liên quan |
| Chỉ phát hiện thay đổi quyền | Bỏ sót credential quản trị bị sử dụng sai | Quan sát cả nhận ngữ cảnh và hành động đặc quyền |
| Đóng cảnh báo khi rollback cấu hình xong | Bỏ qua quyền đã phát sinh ở nơi khác | Kiểm tra phiên, credential và thay đổi tiếp theo |

## 12. Tiêu chí tự kiểm tra

Một thiết kế phát hiện privilege escalation có thể đưa vào thử nghiệm khi trả lời rõ các câu hỏi sau:

- Hành vi nào được phát hiện và mức kết luận tối đa của bằng chứng hiện có?
- Quyền trước, quyền sau và ranh giới tài nguyên được xác định thế nào?
- Actor, effective principal và beneficiary được nối bằng khóa nào?
- Cấp quyền hợp lệ được kiểm tra theo những ràng buộc nào?
- Thiếu dữ liệu, log đến muộn và định danh mơ hồ được xử lý ra sao?
- Có kiểm thử cả hành vi hợp lệ, hành vi ngoài phạm vi, lần thử thất bại và trường hợp UNKNOWN không?
- Cảnh báo có đủ tham chiếu bằng chứng để người khác kiểm tra lại không?
- Thu hồi có được xác minh tại đích và có kiểm tra phiên hoặc token còn hiệu lực không?

Phát hiện hiệu quả dựa vào mối liên hệ giữa **quyền được phép, quyền có hiệu lực và hành động đã xảy ra**. Khi ba lớp này được quan sát riêng và nối đúng, PAM vừa cung cấp căn cứ cấp quyền, vừa cung cấp bằng chứng để nhận ra hành vi vượt khỏi căn cứ đó.
