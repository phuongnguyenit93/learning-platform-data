# Firewall administrator

Firewall administrator là danh tính được phép quản lý cấu hình hoặc hoạt động của firewall. Quyền này có thể nằm trên thiết bị, một virtual firewall, hệ thống quản lý tập trung hoặc API của nền tảng mạng.

Trong Privileged Access Management (PAM), đây là quyền đặc biệt vì một thay đổi có thể mở đường tới dữ liệu nhạy cảm, làm mất phân đoạn mạng, chặn dịch vụ hoặc làm gián đoạn chính đường quản trị. Người quản trị firewall không nhất thiết có tài khoản trên database hay máy chủ ứng dụng, nhưng có thể thay đổi điều kiện để những hệ thống đó được tiếp cận.

Bài học tập trung vào danh tính quản trị, phân tách quyền, cấp quyền có hạn, quản lý phiên, phê duyệt thay đổi và bằng chứng. Các policy, tên thiết bị và địa chỉ trong ví dụ là giả định phục vụ thiết kế hoặc lab; không phải cấu hình dùng trực tiếp cho một sản phẩm cụ thể.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

- Xác định phạm vi quyền quản trị firewall trên thiết bị và hệ thống tập trung.
- Phân biệt quyền xem, soạn thay đổi, kiểm tra, áp dụng và quản trị tài khoản.
- Thiết kế JIT và JEA theo nhiệm vụ thay vì cấp tài khoản toàn quyền thường trực.
- Ràng buộc phê duyệt vào đúng nội dung và phạm vi triển khai.
- Bảo vệ đường quản trị và có phương án phục hồi khi thay đổi làm mất kết nối.
- Phân biệt thu hồi phiên quản trị, thu hồi rule và xử lý kết nối đang tồn tại.
- Xây dựng bằng chứng nối người dùng, phiên, cấu hình và tác động mạng thực tế.

## 2. Vì sao firewall administrator là quyền có tác động rộng?

### 2.1. Tác động tới ranh giới tin cậy

Một firewall thường tham gia bảo vệ ranh giới giữa:

- Người dùng và dịch vụ.
- Các vùng ứng dụng.
- Production và môi trường khác.
- Hệ thống nội bộ và Internet.
- Mạng quản trị và mạng nghiệp vụ.
- Chi nhánh, trung tâm dữ liệu hoặc cloud.
- Đối tác và tổ chức.

Quyền sửa firewall có thể làm thay đổi những ranh giới này mà không cần sửa hệ thống đích.

Ví dụ, một rule cho phép truy cập dịch vụ quản trị từ vùng người dùng có thể biến một credential máy chủ bị lộ thành khả năng truy cập thực tế. Vì vậy, đánh giá đặc quyền phải xét cả đường mạng và danh tính ở hệ thống đích.

### 2.2. Không chỉ là thêm hoặc xóa một rule

Tùy sản phẩm và quyền được cấp, quản trị viên có thể thay:

- Policy cho phép hoặc từ chối.
- Thứ tự hoặc vị trí policy.
- Address object và service object.
- NAT.
- Route hoặc interface.
- VPN và quan hệ kết nối.
- Cấu hình nhận diện ứng dụng.
- Kiểm tra bảo mật hoặc logging.
- Tài khoản quản trị và cơ chế xác thực.
- Chứng thư hoặc trust.
- Đồng bộ HA.
- Cấu hình gửi log.
- Backup, restore hoặc firmware.

Một thay đổi ở shared object có thể ảnh hưởng nhiều rule. Một lần restore có thể đưa lại nhiều cấu hình ngoài thay đổi đang được duyệt.

### 2.3. Tác động tới bảo mật, toàn vẹn và tính sẵn sàng

| Mặt tác động | Ví dụ |
| --- | --- |
| Bảo mật | Mở đường tới dữ liệu, xuất thông tin cấu hình hoặc packet capture nhạy cảm |
| Toàn vẹn | Đổi policy, NAT, route hoặc cơ chế xác thực |
| Tính sẵn sàng | Chặn luồng hợp lệ, gây mất kết nối quản trị hoặc ảnh hưởng HA |
| Khả năng điều tra | Tắt log, đổi đích gửi hoặc làm mất lịch sử cấu hình |
| Quyền tiếp tục tồn tại | Tạo admin, API token hoặc đường truy cập mới |

Đánh giá phải dựa trên năng lực thực tế, không chỉ tên role như operator, network-admin hoặc support.

## 3. Tách management plane, policy và luồng dữ liệu

### 3.1. Management plane

Management plane là nơi quản trị thiết bị hoặc hệ thống quản lý, chẳng hạn:

- Web console.
- SSH hoặc CLI.
- API.
- Console ngoài băng.
- Hệ thống quản lý tập trung.
- Công cụ automation.

PAM cần quản lý ai được vào, vào bằng credential nào, được làm gì và phiên được ghi như thế nào.

### 3.2. Cấu hình và quá trình áp dụng

Một sản phẩm có thể tách bản cấu hình đang soạn khỏi bản có hiệu lực; sản phẩm khác áp dụng thay đổi theo cơ chế khác. Hệ thống quản lý tập trung còn có thể có bước lưu, commit và push xuống thiết bị.

Cần xác định chính xác:

~~~text
Nội dung được sửa ở đâu?
        |
        v
Nội dung được duyệt là bản nào?
        |
        v
Ai được áp dụng?
        |
        v
Thiết bị nào đã nhận?
        |
        v
Policy nào thực sự đang hoạt động?
~~~

Không dùng trạng thái “saved” như thể nó luôn có nghĩa dữ liệu đang đi qua policy mới.

### 3.3. Luồng dữ liệu

Luồng dữ liệu là kết nối giữa các endpoint được firewall xử lý. Nó khác với phiên quản trị.

Một admin kết thúc phiên không tự làm rule vừa tạo biến mất. Xóa rule cũng không được coi là bằng chứng chắc chắn mọi kết nối đã tồn tại đều bị ngắt.

Thiết kế phải quản lý riêng:

- Phiên quản trị.
- Vòng đời cấu hình.
- Trạng thái kết nối mạng.

## 4. Inventory quyền quản trị

### 4.1. Kiểm kê thiết bị và miền quản lý

Danh mục nên có:

- Device ID hoặc serial theo khả năng.
- Vị trí và owner.
- Môi trường.
- Phiên bản.
- Hệ thống quản lý tập trung.
- Nhóm thiết bị hoặc tenant.
- Virtual system, VDOM hoặc miền quản trị tương ứng nếu có.
- Thành viên HA.
- Đường quản trị.
- Đích audit.
- Phương án phục hồi.

Tên hiển thị có thể thay đổi hoặc bị trùng. Cần định danh đủ để tránh áp policy lên sai thiết bị.

### 4.2. Kiểm kê principal

Bao gồm:

- Admin cá nhân.
- Nhóm qua hệ thống danh tính.
- Tài khoản local.
- Tài khoản khẩn cấp.
- API administrator.
- Service account của automation.
- Connector PAM.
- Tài khoản của nhà cung cấp hoặc đối tác.
- Danh tính quản trị hệ thống tập trung.

Không bỏ qua tài khoản không có giao diện tương tác. Một token automation có thể đẩy thay đổi tới nhiều thiết bị.

### 4.3. Bản ghi quyền tối thiểu

| Thuộc tính | Nội dung cần biết |
| --- | --- |
| Principal | Người, nhóm hoặc workload |
| Owner | Ai chịu trách nhiệm |
| Đích | Thiết bị, miền và môi trường |
| Phương thức | Web, SSH, API, console hoặc manager |
| Quyền | Xem, sửa, commit, push, quản trị danh tính |
| Phạm vi | Thiết bị, tenant, object hoặc chức năng |
| Mục đích | Công việc cần đáp ứng |
| Credential | Nguồn cấp, nơi giữ và cách luân chuyển |
| Thời hạn | Thường trực hoặc theo grant |
| Bằng chứng | Log xác thực, phiên, cấu hình và kết quả |
| Đường thay thế | Quyền khác có thể đạt cùng khả năng |
| Ngoại lệ | Owner, lý do và thời điểm đánh giá lại |

### 4.4. Quyền gián tiếp

Cần đánh giá cả quyền:

- Sửa pipeline triển khai cấu hình.
- Đổi template hoặc shared object.
- Quản trị hệ thống AAA.
- Đổi role mapping.
- Lấy credential từ vault.
- Đặt lại tài khoản.
- Sửa PAM connector.
- Truy cập backup cấu hình.
- Quản trị nền tảng chạy virtual firewall.

Một người không có quyền trực tiếp trên firewall vẫn có thể kiểm soát người hoặc hệ thống đang có quyền đó.

## 5. Phân tách chức năng quản trị

### 5.1. Ma trận nhiệm vụ tham khảo

| Vai trò nghiệp vụ | Khả năng cần thiết | Khả năng nên tách nếu không cần |
| --- | --- | --- |
| Người rà soát | Xem policy và bằng chứng đã giới hạn | Sửa và áp dụng |
| Người soạn thay đổi | Tạo bản đề xuất trong phạm vi | Tự duyệt và phát hành ngoài phạm vi |
| Người phê duyệt | Đánh giá nội dung và tác động | Tùy ý thay payload đã duyệt |
| Người phát hành | Áp đúng bản thay đổi được phép | Sửa mọi nội dung hoặc đổi danh tính |
| Người quản trị tài khoản | Quản lý admin và role mapping | Tác nghiệp policy thường ngày nếu không cần |
| Người quản trị audit | Quản lý nguồn và đích log | Tự che hoạt động của chính mình |
| Automation | Thao tác đã xác định trên đúng đích | Quản trị toàn bộ hệ thống |

Đây là ma trận thiết kế, không có nghĩa sản phẩm nào cũng cung cấp mọi ranh giới ở cùng độ chi tiết.

Nếu không thể phân tách một khả năng quan trọng bằng quyền native, cần nêu rõ khoảng trống và cơ chế bù đắp có thể kiểm chứng.

### 5.2. Khả năng role khác nhau theo sản phẩm

Ví dụ, PAN-OS hỗ trợ Admin Role Profile và các quyền quản trị tương ứng. Khả năng trên từng giao diện phải được cấu hình theo profile và phạm vi được hỗ trợ. [Admin Role Profile của Palo Alto Networks](https://docs.paloaltonetworks.com/ngfw/administration/firewall-administration/manage-firewall-administrators/configure-an-admin-role-profile).

FortiOS có administrator profile để giới hạn các vùng chức năng và quyền CLI; nhóm lệnh chẩn đoán cũng cần được đánh giá vì có khả năng đặc biệt. [Administrator profiles trong FortiOS 7.6.6](https://docs.fortinet.com/document/fortigate/7.6.6/administration-guide/294491/administrator-profiles).

Không sao chép ý nghĩa của một role giữa các hãng hoặc phiên bản. Cần kiểm thử quyền hiệu lực trên thiết bị mục tiêu.

### 5.3. Quyền commit là một khả năng riêng

Một người được sửa một bản candidate chưa chắc phải có quyền áp dụng mọi thay đổi.

PAN-OS có các lựa chọn quản lý commit, save và validate; quyền Commit For Other Admins ảnh hưởng việc commit hoặc revert thay đổi do người khác tạo. [Giới hạn quyền commit và validate](https://docs.paloaltonetworks.com/ngfw/administration/firewall-administration/reference-web-interface-administrator-access/web-interface-access-privileges/restrict-administrator-access-to-commit-and-validate-functions).

Hệ quả thiết kế: cần biết lần commit bao gồm thay đổi của ai và phần cấu hình nào, không chỉ biết người bấm nút commit.

### 5.4. Quyền xem cũng có thể nhạy cảm

Read-only có thể cho thấy:

- Sơ đồ mạng.
- Địa chỉ nội bộ.
- Quy tắc truy cập.
- Thông tin VPN.
- Metadata chứng thư.
- Log người dùng.
- Dữ liệu chẩn đoán.
- Cấu hình hoặc backup có secret theo cách sản phẩm xử lý.

Cần kiểm tra dữ liệu thực tế được trả về. Không mặc định quyền xem mọi cấu hình phù hợp cho mọi nhân viên hỗ trợ.

## 6. Bảo vệ đường quản trị

### 6.1. Dùng danh tính có thể quy trách nhiệm

Ưu tiên tài khoản cá nhân hoặc phiên được ánh xạ rõ tới người thật. Với automation, dùng danh tính workload riêng theo mục đích.

Nếu phải dùng một tài khoản thiết bị chung qua PAM:

- Xác thực người dùng riêng ở PAM.
- Có mã phiên và grant.
- Kiểm soát lấy credential.
- Hạn chế đường trực tiếp.
- Nối tới log thiết bị.
- Quản lý việc nhiều người dùng đồng thời.
- Luân chuyển theo quy trình phù hợp.

Một log chỉ ghi admin không đủ xác định ai đã thao tác nếu nhiều người biết cùng credential.

### 6.2. Xác thực, phân quyền và ghi nhận là ba chức năng

Đăng nhập thành công chưa chứng minh người dùng được phép sửa đúng đối tượng. Ghi command chưa chứng minh command đã được cho phép theo nhiệm vụ.

Cần kiểm tra riêng:

- Cơ chế xác thực và điều kiện tăng cường.
- Mapping danh tính tới role.
- Phân quyền thao tác.
- Ghi nhận hoạt động.
- Hành vi khi dịch vụ xác thực hoặc accounting không sẵn sàng.

Nếu có fallback local, phải biết khi nào nó được dùng và mức quyền nào được cấp. Không bật tài khoản rộng thường trực chỉ để tránh mọi khả năng phụ thuộc hệ thống danh tính.

### 6.3. Giới hạn nguồn và endpoint

Có thể dùng mạng quản trị, gateway hoặc các ranh giới phù hợp để giới hạn nguồn truy cập.

Điều cần chứng minh:

- Chỉ nguồn được quản lý có thể vào endpoint cần bảo vệ.
- Kết nối dùng giao thức và cơ chế tin cậy phù hợp.
- API không thành đường bỏ qua.
- Endpoint của hệ thống tập trung và thiết bị đều được kiểm kê.
- IPv4, IPv6 hoặc đường VPN liên quan không tạo ngoại lệ âm thầm.

Một whitelist địa chỉ không thay thế xác thực danh tính. Nhiều người hoặc workload có thể đi ra cùng một địa chỉ NAT.

### 6.4. Quyền quản trị chính firewall chứa đường quản trị của nó

Đây là quan hệ dễ tạo tự khóa:

~~~text
Admin kết nối qua một đường mạng
                  |
                  v
Admin sửa policy, route, VPN hoặc interface
                  |
                  v
Thay đổi ảnh hưởng chính đường đang dùng để quản trị
~~~

Quy trình phải có cách phục hồi đã kiểm thử. Không chỉ kiểm tra “còn mở được tab cũ” vì phiên đã tồn tại có thể không phản ánh khả năng mở kết nối mới.

## 7. JIT và JEA cho firewall administrator

### 7.1. Grant theo công việc

Một grant nên xác định:

- Principal yêu cầu.
- Thiết bị và miền quản lý.
- Môi trường.
- Nhóm thao tác.
- Thay đổi hoặc runbook.
- Điều kiện phê duyệt.
- Thời gian được mở phiên.
- Thời hạn phiên.
- Recording hoặc audit bắt buộc.
- Khả năng gia hạn.
- Điều kiện thu hồi.

JIT giới hạn thời gian sử dụng. JEA giới hạn khả năng theo nhiệm vụ. Một phiên super-admin ngắn vẫn có phạm vi rộng.

### 7.2. Grant minh họa

~~~yaml
grantId: FW-GRANT-2841
requester: operator-017
target:
  managerId: network-manager-prod
  deviceSet:
    - fw-billing-01
    - fw-billing-02
  administrativeDomain: billing-production
capabilities:
  - propose-policy-change
  - inspect-approved-change
changeReference: FW-CHG-2841
validity:
  startsAt: "2026-11-26T14:00:00+07:00"
  endsAt: "2026-11-26T14:30:00+07:00"
session:
  maximumDurationSeconds: 900
  recordingRequired: true
approvalState: approved
~~~

Đây là mô hình nghiệp vụ của PAM, không phải policy của thiết bị cụ thể. Các capability phải được ánh xạ sang quyền thật.

Nếu sản phẩm chỉ có role rộng, đừng báo grant đã được giới hạn tới từng rule khi cơ chế kỹ thuật chưa thực hiện được.

### 7.3. Tránh grant chỉ tồn tại trên giao diện

Nếu người dùng được yêu cầu xin duyệt trên PAM nhưng vẫn có credential và quyền trực tiếp tương đương, quy trình chưa kiểm soát toàn bộ đường truy cập.

Kiểm thử cần có trường hợp:

- Không có grant nhưng truy cập endpoint trực tiếp.
- Có grant cho thiết bị A nhưng chọn thiết bị B.
- Đổi từ web sang API hoặc CLI.
- Dùng credential cũ.
- Dùng tài khoản local thay danh tính tập trung.

Mỗi đường được phép ngoài PAM phải được xác định rõ, không bị lẫn với đường bỏ qua không mong muốn.

## 8. Yêu cầu thay đổi firewall phải có ngữ nghĩa mạng

### 8.1. Nhu cầu không chỉ là “mở port”

Một yêu cầu cần mô tả:

- Nguồn và owner.
- Đích và owner.
- Hướng kết nối.
- Giao thức và dịch vụ.
- Mục đích nghiệp vụ.
- Môi trường.
- Thời gian cần.
- Dữ liệu hoặc hệ thống nhạy cảm liên quan.
- Cách kiểm thử cho phép và từ chối.
- Cách thu hồi.
- Tác động tới rule hoặc object đang tồn tại.

Không dùng any-any như lời giải mặc định cho một thông tin còn thiếu.

### 8.2. Ví dụ luồng cần mở

~~~yaml
changeId: FW-CHG-2841
businessPurpose: Kiem tra ket noi Billing toi reporting service
source:
  address: 10.20.30.10
  owner: billing-application-team
destination:
  address: 10.40.50.20
  owner: reporting-team
transport:
  protocol: tcp
  destinationPort: 8443
environment: lab
requestedWindow:
  startsAt: "2026-11-26T14:00:00+07:00"
  endsAt: "2026-11-26T14:30:00+07:00"
requirements:
  auditChange: true
  verifyAllowedFlow: true
  verifyDeniedBoundaries: true
  verifyCleanup: true
~~~

Đây là yêu cầu trừu tượng trong lab, không phải lệnh cài đặt rule. Firewall còn cần xác định zone, đối tượng, NAT, route hoặc các thuộc tính phù hợp theo sản phẩm và topology.

### 8.3. Phân tích shared object

Nếu source object là một nhóm dùng bởi nhiều policy, thêm một địa chỉ vào nhóm có thể mở rộng nhiều đường hơn rule mà người đề xuất đang nhìn.

Bản đánh giá nên nêu:

- Object nào thay đổi.
- Nó được tham chiếu ở đâu.
- Tập policy và thiết bị bị ảnh hưởng.
- Có thay đổi nào ngoài ý định không.
- Cách kiểm chứng sau phát hành.

Không chỉ duyệt screenshot của một rule nếu payload còn sửa object chung.

### 8.4. Rule order, NAT và route

Cách đánh giá policy và các bước xử lý có thể khác giữa nền tảng. Cần đối chiếu đúng mô hình của thiết bị.

Một rule trông đúng vẫn có thể:

- Không được áp do policy khác.
- Không khớp vì zone hoặc địa chỉ được xét ở giai đoạn khác.
- Không có route phù hợp.
- Chỉ áp trên một thành viên.
- Dùng object khác với tên hiển thị mà người đọc nghĩ tới.

Do đó, kiểm tra cú pháp và so sánh text chỉ là một phần nghiệm thu.

## 9. Ràng buộc phê duyệt vào nội dung thật

### 9.1. Đề xuất và bản áp dụng phải nối được

Phê duyệt nên gắn với:

- Đích.
- Phiên bản nguồn.
- Nội dung thay đổi đã được chuẩn hóa.
- Các object phụ thuộc.
- Phạm vi commit hoặc push.
- Người hoặc workload phát hành.
- Cửa sổ và điều kiện.
- Tiêu chí xác minh.
- Phương án rollback.

Nếu payload đổi sau phê duyệt, cần đánh giá lại theo policy. Một ticket còn mở không tự cho phép mọi thay đổi phát sinh.

### 9.2. Kiểm soát đồng thời

Nhiều người có thể sửa cấu hình cùng lúc. Cần biết:

- Ai đang giữ candidate hoặc workspace.
- Bản nguồn có thay đổi từ lúc duyệt không.
- Commit có gom phần của người khác không.
- Một lần push có ảnh hưởng nhiều thiết bị không.
- Quyền áp dụng có giới hạn đúng phạm vi không.

Không xóa thay đổi chưa commit của người khác chỉ để làm sạch bản triển khai. Cần xử lý xung đột theo cơ chế sản phẩm và ownership được xác định.

### 9.3. Approval không thay thế quyền native

PAM có thể biết người được duyệt thay một rule, nhưng thiết bị vẫn cấp quyền sửa toàn bộ policy. Khi đó, khoảng cách giữa phạm vi nghiệp vụ và phạm vi kỹ thuật phải được ghi rõ.

Có thể giảm khoảng cách bằng role hẹp, automation kiểm soát payload, gateway hoặc phương án được kiểm thử. Không tuyên bố ranh giới mạnh hơn khả năng thực tế.

## 10. Áp dụng và xác minh thay đổi

### 10.1. Trình tự tham khảo

~~~text
Đọc trạng thái hiện tại
        |
        v
Đối chiếu bản nguồn và phê duyệt
        |
        v
Validate hoặc kiểm tra tương ứng
        |
        v
Áp dụng đúng phạm vi
        |
        v
Xác minh thiết bị đích và phiên bản hiệu lực
        |
        v
Kiểm thử luồng được phép và ranh giới bị cấm
        |
        v
Lưu bằng chứng và theo dõi sau thay đổi
~~~

Không có một tên trạng thái commit chung cho mọi hãng. Cần chuyển các trạng thái sản phẩm thành ý nghĩa nghiệp vụ đúng.

### 10.2. Trạng thái job thành công chưa phải bằng chứng đầy đủ

Một hệ thống tập trung có thể báo nhận hoặc xử lý job trước khi mọi thiết bị đạt trạng thái mong đợi.

Cần xác minh:

- Danh sách thiết bị thực nhận.
- Phiên bản hoặc object hiệu lực.
- Kết quả trên từng thành viên theo mô hình.
- Thiết bị chưa đồng bộ hoặc bị loại.
- Phần cấu hình bị ghi đè hoặc không được áp.
- Cảnh báo liên quan.

Không gán một trạng thái success toàn bộ khi chỉ một phần phạm vi đã đạt.

### 10.3. Kiểm thử kết nối có nguyên nhân rõ

Một phép thử cho phép cần chứng minh request đi từ đúng nguồn tới đúng đích theo điều kiện dự kiến.

Một phép thử từ chối cần xác định thất bại do ranh giới muốn kiểm tra, không chỉ vì:

- Dịch vụ chưa chạy.
- DNS sai.
- Route lỗi.
- Sai cổng.
- Thiếu chứng thư ứng dụng.
- Mất mạng ở nơi khác.

Có thể đối chiếu policy hit, traffic log, trạng thái kết nối và bằng chứng ứng dụng theo khả năng. Không coi ping thành công là chứng minh dịch vụ TCP cụ thể đã được cho phép đúng.

### 10.4. Kiểm tra điều không được phép

Ngoài luồng cần mở, thử trong lab hoặc phạm vi được phép:

- Nguồn khác.
- Đích khác.
- Cổng khác.
- Hướng không được duyệt.
- Truy cập tới endpoint quản trị.
- Đường qua miền hoặc thiết bị khác.

Một phép thử thành công không chứng minh rule không mở rộng ngoài nhu cầu.

## 11. Chống tự khóa và rollback

### 11.1. Phương án phục hồi phải có trước thay đổi

Xác định:

- Đường console hoặc quản trị ngoài băng.
- Danh tính khẩn cấp.
- Người có thể thao tác.
- Phạm vi truy cập vật lý hoặc từ xa.
- Bản cấu hình phục hồi.
- Điều kiện kích hoạt.
- Cách bảo vệ credential.
- Cách ghi bằng chứng.

Một đường được gọi là out-of-band nhưng vẫn phụ thuộc chính VPN hoặc policy đang sửa có thể không độc lập như dự kiến.

### 11.2. Confirmed commit chỉ dùng khi sản phẩm hỗ trợ

Junos có cơ chế commit confirmed để áp candidate với yêu cầu xác nhận; nếu không được xác nhận trong thời hạn, hệ thống quay lại cấu hình trước theo cơ chế của nó. Đây là ví dụ giảm rủi ro thay đổi làm mất đường quản trị, không phải khả năng mặc định của mọi firewall. [Commit và automatic rollback trong Junos](https://www.juniper.net/documentation/us/en/software/junos/cli/topics/topic-map/junos-configuration-commit.html).

Khi dùng cơ chế tương tự, cần kiểm thử đúng phiên bản và xác minh cả trạng thái rollback lẫn kết nối. Không tự động xác nhận chỉ vì một job trung gian trả thành công.

### 11.3. Rollback cũng là thay đổi có tác động

Bản cũ có thể:

- Thiếu một bản sửa bảo mật mới.
- Chứa tài khoản đã bị loại bỏ.
- Dùng object hoặc endpoint không còn phù hợp.
- Làm mất thay đổi hợp lệ của người khác.
- Không tương thích với phiên bản hiện tại.

Cần chọn phạm vi khôi phục phù hợp. Restore toàn bộ cấu hình không nên là nút undo mặc định cho một lỗi nhỏ.

### 11.4. Bảo vệ backup cấu hình

Backup có thể chứa topology, account, certificate hoặc secret theo cách sản phẩm lưu.

Quản lý:

- Ai được tạo và tải.
- Mã hóa và quyền đọc.
- Nơi giữ.
- Thời gian lưu.
- Khả năng phục hồi.
- Cách xử lý sau khi credential bị lộ.
- Quyền restore.

Người chỉ cần xem một rule không nên tự có quyền tải toàn bộ backup.

## 12. HA và quản lý tập trung

### 12.1. Phạm vi ảnh hưởng của manager

Một credential quản trị tập trung có thể mạnh hơn credential trên một thiết bị vì nó quản lý:

- Nhiều firewall.
- Shared object.
- Template.
- Nhóm thiết bị.
- Policy chung.
- Luồng push.
- Tài khoản hoặc mapping quản trị.

Cần giới hạn connector và automation theo miền hoặc nhóm thiết bị khi nền tảng hỗ trợ.

### 12.2. Không coi HA là bản sao đơn giản

Tùy kiến trúc, các thành viên có vai trò, cấu hình riêng và trạng thái đồng bộ khác nhau.

Quy trình cần biết:

- Thành viên nào nhận thay đổi.
- Thành phần nào được đồng bộ.
- Có phần cấu hình riêng theo node không.
- Trạng thái trước và sau thay đổi.
- Hành vi nếu failover giữa lúc áp dụng.
- Thay đổi có còn đúng sau failover không.

Không yêu cầu mọi byte cấu hình giống nhau nếu sản phẩm có thông tin riêng theo node; so sánh đúng các phần cần đạt.

### 12.3. Partial deployment

Nếu một trong hai thiết bị không đạt phiên bản mới:

- Ghi rõ trạng thái từng thiết bị.
- Đánh giá luồng nào đang chịu policy nào.
- Ngăn báo hoàn thành toàn bộ.
- Quyết định retry, rollback hoặc ngoại lệ theo runbook.
- Lưu bằng chứng cho phần đã áp.

Không lặp push mù khi chưa hiểu thay đổi đang ở trạng thái nào.

## 13. Phiên quản trị, rule tạm và kết nối đang tồn tại

### 13.1. Ba vòng đời riêng

| Đối tượng | Ví dụ kết thúc | Điều không tự được bảo đảm |
| --- | --- | --- |
| Phiên admin | Hết hạn grant hoặc đóng gateway | Rule vừa tạo bị xóa |
| Rule hoặc policy tạm | Hết lịch hoặc được thu hồi | Mọi flow cũ đã bị ngắt |
| Kết nối dữ liệu | Timeout hoặc được xử lý theo cơ chế nền tảng | Quyền tạo rule mới đã mất |

Một yêu cầu “mở trong 30 phút” cần xác định nó giới hạn đối tượng nào.

### 13.2. Hành vi stateful cần được xác minh

Ví dụ, với Amazon EC2 security group, thay rule không lập tức ngắt các connection đang được theo dõi; hành vi còn khác giữa luồng tracked và untracked. Đây là ví dụ cụ thể về việc không được suy “xóa rule là dừng mọi flow” cho một cơ chế stateful. [Security group connection tracking](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/security-group-connection-tracking.html).

Security group không đồng nhất với mọi sản phẩm firewall. Với thiết bị đang quản lý, phải kiểm tra tài liệu và thử nghiệm hành vi tương ứng.

Nếu cần ngắt flow, biện pháp phải được chọn theo sản phẩm, đúng phạm vi và có đánh giá tác động. Không xóa toàn bộ session table như thao tác cleanup mặc định cho một kết nối.

### 13.3. Cleanup rule tạm

Cần xác minh:

- Đúng rule hoặc object.
- Đúng thiết bị và miền.
- Không còn bị tham chiếu theo cách giữ đường mở.
- Không có rule khác tạo quyền tương đương.
- Policy hiệu lực đã cập nhật.
- Flow cũ được xử lý theo yêu cầu.
- Có bằng chứng hoàn tất.

Không chỉ xóa một dòng trong manager rồi đóng ticket.

### 13.4. Thu hồi quyền quản trị

Sau quyết định thu hồi:

- Ngừng cấp hoặc refresh credential theo policy.
- Chặn login mới.
- Xử lý phiên đang mở theo khả năng.
- Thu hồi API token hoặc quyền liên quan.
- Dọn quyền tạm.
- Kiểm tra quyền từ nhóm hoặc tài khoản local khác.
- Đối soát thay đổi đã tạo.

Đổi password không nên được coi là bằng chứng mọi web session, token hoặc job đã dừng. Cần kiểm tra từng loại.

## 14. Vault, API token và automation

### 14.1. Credential của người và máy

Tách:

- Tài khoản cá nhân.
- Tài khoản broker.
- Token của pipeline.
- Tài khoản backup.
- Tài khoản giám sát.
- Credential khẩn cấp.

Không dùng cùng một super-admin token cho mọi chức năng nếu có thể phân quyền hẹp hơn.

### 14.2. Vai trò của vault

Vault hỗ trợ quản lý secret, quyền lấy và luân chuyển theo khả năng sản phẩm. Nó không tự thu hẹp quyền profile trên firewall.

Cần xác định:

- Token hoặc password được lộ cho ai.
- Có thể dùng lại ở đâu.
- Cache tồn tại bao lâu.
- Connector có thể tự chọn thiết bị không.
- Luân chuyển có ảnh hưởng manager, HA hoặc automation không.
- Credential cũ còn mở được kết nối mới không.
- Phiên hiện hữu được xử lý thế nào.

### 14.3. Automation phải áp đúng thay đổi

Một pipeline có credential mạnh cần kiểm tra:

- Nguồn mã.
- Payload đã duyệt.
- Đích được phép.
- Phiên bản nguồn.
- Phạm vi commit hoặc push.
- Quyền sửa script.
- Artifact sau phê duyệt.
- Run ID và bằng chứng.

Nếu người đề xuất sửa được script kiểm tra hoặc thay payload sau phê duyệt, kiểm soát ban đầu có thể không còn hiệu lực.

### 14.4. Không tự mở rộng quyền để sửa lỗi automation

Khi connector thiếu quyền, xác định thao tác nào bị từ chối và vì sao. Không chuyển toàn bộ tài khoản sang super-admin chỉ để mọi job tiếp tục chạy.

Cần cập nhật ma trận quyền và kiểm thử lại theo phạm vi thay đổi thật.

## 15. Giám sát và bằng chứng

### 15.1. Các nguồn cần kết hợp

| Nguồn | Có thể hỗ trợ |
| --- | --- |
| Hệ thống danh tính | Ai xác thực và điều kiện nào |
| PAM | Ai xin quyền, grant và phiên |
| CLI hoặc web recording | Ngữ cảnh tương tác quan sát được |
| API audit | Yêu cầu automation và kết quả theo nguồn |
| Configuration log | Ai sửa gì và thay đổi nào |
| Commit hoặc deployment log | Bản nào được áp tới đâu |
| Traffic log | Luồng nào được cho phép hoặc chặn theo cấu hình |
| HA và hệ thống | Đồng bộ, failover và tình trạng vận hành |

Không dùng traffic log thay cho log quản trị. Một kết nối được cho phép không tự cho biết ai đã tạo rule làm nó được phép.

### 15.2. Bản ghi chuẩn hóa minh họa

~~~json
{
  "event": "firewall_change_verified",
  "grantId": "FW-GRANT-2841",
  "changeId": "FW-CHG-2841",
  "requester": "operator-017",
  "appliedBy": "network-deploy-pipeline",
  "managerId": "network-manager-prod",
  "targetDevices": ["fw-billing-01", "fw-billing-02"],
  "administrativeDomain": "billing-production",
  "approvedRevision": "proposal-019",
  "deploymentReference": "deploy-044",
  "deviceVerification": "all-targets-verified",
  "allowedFlowTest": "pass",
  "deniedBoundaryTests": "pass",
  "cleanupRequired": true,
  "correlationId": "fw-operation-019"
}
~~~

Đây là schema nghiệp vụ đề xuất, không phải log native chung. Chỉ dùng trạng thái verified hoặc pass khi có kiểm tra thật hỗ trợ.

### 15.3. Nội dung cần giữ

- Principal thật và tài khoản trực tiếp.
- Mã phiên, grant và change.
- Thiết bị, miền và phiên bản.
- Bản nguồn và bản thay đổi được duyệt.
- Diff phù hợp, có xử lý dữ liệu nhạy cảm.
- Phạm vi commit.
- Kết quả từng thiết bị.
- Phép thử lưu lượng.
- Rollback hoặc ngoại lệ.
- Thời điểm, múi giờ và nguồn.
- Kết quả thu hồi và cleanup.

Hash hoặc revision giúp đối chiếu bản thay đổi, nhưng không tự chứng minh nội dung đã được người có trách nhiệm duyệt hoặc đã áp thành công.

### 15.4. Bảo vệ bằng chứng và phát hiện mất log

Theo dõi:

- Nguồn còn gửi.
- Đích còn nhận.
- Độ trễ.
- Lỗi parse.
- Khoảng thời gian thiếu dữ liệu.
- Thay đổi filter.
- Thay đổi thời gian hoặc đích log.
- Quyền đọc và xóa.
- Khả năng truy xuất bản lịch sử.

Nếu firewall hoặc manager có thể sửa log cục bộ, cần ranh giới lưu bằng chứng phù hợp ngoài quyền tác nghiệp đó.

## 16. Tình huống thực hành: mở tạm một luồng ứng dụng

### 16.1. Bối cảnh

Billing cần kết nối từ nguồn 10.20.30.10 tới dịch vụ lab 10.40.50.20 qua TCP 8443 trong một cửa sổ kiểm thử.

Hiện tại:

- Nhóm vận hành dùng tài khoản admin chung.
- Người tạo rule cũng tự commit.
- Shared address group được dùng bởi nhiều policy.
- Ticket chỉ ghi “mở port test”.
- Không có xác minh cleanup.
- Một manager quản lý hai firewall.

### 16.2. Thiết kế cần nộp

1. Inventory principal, thiết bị và đường quản trị.
2. Ma trận quyền người soạn, người duyệt và người phát hành.
3. Yêu cầu luồng có owner, hướng và thời hạn.
4. Phân tích shared object.
5. Ràng buộc phê duyệt vào payload và đích.
6. Kế hoạch kiểm tra đường quản trị và phục hồi.
7. Kế hoạch phát hành tới hai thiết bị.
8. Phép thử cho phép và ranh giới bị cấm.
9. Policy xử lý phiên admin, rule tạm và flow cũ.
10. Bằng chứng và quy trình đóng thay đổi.

### 16.3. Những câu hỏi bắt buộc

- Nguồn nào chứng minh người thật sau tài khoản quản trị?
- Nếu người soạn đổi source thành một subnet rộng hơn sau phê duyệt, ai chặn?
- Nếu commit gom thay đổi của người khác, cách phát hiện là gì?
- Nếu chỉ một firewall nhận cấu hình, trạng thái công việc là gì?
- Nếu tab quản trị cũ vẫn mở, đã chứng minh login mới còn hoạt động chưa?
- Nếu rule hết hạn nhưng flow cũ còn chạy, chính sách yêu cầu xử lý ra sao?
- Nếu shared object mở thêm luồng ngoài dự kiến, ai chịu trách nhiệm đánh giá?
- Nếu manager mất kết nối, phương án phục hồi có thật sự độc lập không?

Không có một kiến trúc duy nhất. Bài đạt khi mỗi bảo đảm có điểm thực thi và bằng chứng kiểm thử phù hợp.

## 17. Ma trận kiểm thử nghiệm thu

| Tình huống | Kết quả mong đợi |
| --- | --- |
| Principal hợp lệ và grant đúng đích | Có quyền theo phạm vi thiết kế |
| Không có grant nhưng vào đường quản trị bắt buộc | Bị từ chối |
| Đổi sang API hoặc CLI | Không vượt quyền chỉ vì đổi giao diện |
| Grant cho miền A, truy cập miền B | Bị giới hạn theo quyền thực tế |
| Role chỉ soạn thay đổi thử commit | Bị chặn nếu đây là ranh giới được hỗ trợ và yêu cầu |
| Payload thay sau phê duyệt | Không áp bằng phê duyệt cũ |
| Shared object ảnh hưởng nhiều rule | Phạm vi được phát hiện và đánh giá |
| Candidate có phần của người khác | Không áp nhầm ngoài phạm vi |
| Một thiết bị chưa nhận thay đổi | Không báo toàn bộ đã hoàn tất |
| Luồng đúng nguồn, đích và dịch vụ | Hoạt động và có bằng chứng phù hợp |
| Nguồn hoặc cổng ngoài yêu cầu | Bị chặn bởi đúng ranh giới mong đợi |
| Thay đổi gây mất đường quản trị trong lab | Phục hồi theo cơ chế đã thử |
| Grant hết hạn | Chặn cấp mới và xử lý phiên theo policy |
| Rule tạm hết hạn | Xác minh policy hiệu lực và hành vi flow cũ |
| API token bị thu hồi | Không tiếp tục dùng theo cơ chế đã xác nhận |
| Recorder hoặc đích log lỗi | Có hành vi và cảnh báo theo policy |
| Failover trong lab | Đánh giá cấu hình và quyền sau chuyển vai |
| Break-glass được kích hoạt | Có bằng chứng và hậu kiểm |
| Restore cấu hình | Rà soát tài khoản, policy và audit được phục hồi |

Mỗi phép thử cần môi trường được phép, đầu vào, kết quả mong đợi và tiêu chí PASS. Không dùng dữ liệu thật hoặc gián đoạn production chỉ để chứng minh quyền.

## 18. Những ngộ nhận cần tránh

| Ngộ nhận | Cách hiểu đúng |
| --- | --- |
| Quản trị firewall chỉ là mở port | Có thể tác động route, NAT, VPN, danh tính và audit |
| Có MFA nên mọi thao tác đã được kiểm soát | Phải kiểm tra quyền và đường đi vòng |
| Tài khoản read-only luôn không nhạy cảm | Cấu hình và log có thể chứa thông tin quan trọng |
| Người sửa candidate tự nhiên có quyền commit | Đây là năng lực cần quản lý riêng theo nền tảng |
| Job thành công là mọi thiết bị đã áp | Cần xác minh từng đích và cấu hình hiệu lực |
| Một luồng được phép chạy là rule đã hẹp | Phải kiểm tra cả trường hợp ngoài phạm vi |
| Hết phiên PAM thì rule tạm cũng hết | Phiên và cấu hình có vòng đời khác nhau |
| Xóa rule là mọi flow lập tức dừng | Cần kiểm tra state và hành vi nền tảng |
| Backup chỉ là tệp tiện ích | Nó có thể chứa cấu hình và secret nhạy cảm |
| Đổi password sẽ hủy mọi token và phiên | Cần quản lý từng loại credential và kết nối |
| Rollback luôn an toàn | Có thể đưa lại quyền hoặc policy cũ |
| Tài khoản manager giống một thiết bị | Manager có thể ảnh hưởng cả hệ thống rộng hơn |

## 19. Chỉ số duy trì kiểm soát

Các chỉ số có ích:

- Số admin hoặc token toàn quyền thường trực.
- Tỷ lệ tài khoản có owner và mục đích.
- Tỷ lệ đường quản trị nằm trong phạm vi được giám sát.
- Tỷ lệ phiên nối được với người hoặc workload và grant.
- Tỷ lệ thay đổi nối được phê duyệt với payload hiệu lực.
- Số triển khai một phần chưa được xử lý.
- Số rule tạm chưa cleanup đúng hạn.
- Số ngoại lệ shared object chưa được đánh giá.
- Thời gian chặn login mới sau quyết định thu hồi.
- Kết quả kiểm thử phục hồi đường quản trị.
- Tỷ lệ hậu kiểm break-glass hoàn tất.
- Số khoảng trống audit chưa có owner xử lý.

Không dùng số rule hoặc số lần đăng nhập làm thước đo duy nhất. Một token toàn quyền trên manager có thể tạo phạm vi ảnh hưởng lớn dù số tài khoản ít.

## 20. Câu hỏi tự kiểm tra

**Vì sao firewall administrator được xem là quyền đặc biệt dù không có tài khoản ứng dụng?**

Vì người đó có thể thay ranh giới mạng và điều kiện tiếp cận ứng dụng, dữ liệu hoặc hệ thống quản trị.

**Có phê duyệt ticket thì payload nào cũng được áp không?**

Không. Cần ràng buộc phê duyệt vào đúng đích, nội dung, phiên bản và điều kiện.

**Vì sao cần xét shared object?**

Một sửa đổi nhỏ có thể ảnh hưởng nhiều policy hoặc thiết bị đang tham chiếu object đó.

**Có thể dùng trạng thái commit của manager làm bằng chứng duy nhất không?**

Chưa đủ. Cần xác minh kết quả trên thiết bị và hành vi lưu lượng phù hợp.

**Phiên admin đã hết hạn có làm rule đã tạo mất hiệu lực không?**

Không tự bảo đảm. Cần quản lý vòng đời rule riêng.

**Rule đã bị xóa có chứng minh mọi kết nối cũ đã dừng không?**

Không. Phải xét trạng thái và hành vi của nền tảng, rồi xử lý đúng phạm vi nếu yêu cầu.

**Vì sao out-of-band phải được kiểm thử?**

Vì đường mang tên ngoài băng vẫn có thể phụ thuộc thành phần đang thay đổi hoặc credential chưa dùng được.

**Vault có tự giảm quyền profile trên firewall không?**

Không. Vault quản lý credential; quyền và phạm vi thao tác phải được thực thi tại các lớp tương ứng.

Firewall administrator cần được quản lý theo khả năng tác động thực tế lên ranh giới mạng. Danh tính riêng, quyền theo nhiệm vụ, thay đổi được phê duyệt đúng nội dung, xác minh trên từng đích và quản lý riêng phiên–policy–flow giúp PAM giữ được quyền này trong phạm vi có thể giải thích và kiểm chứng.
