# Switch administrator

Một kỹ thuật viên cần bật một cổng access nhưng được cấp tài khoản quản trị toàn bộ switch. Tài khoản đó cũng có thể thay trunk, sửa VLAN quản trị, tắt logging hoặc tạo người dùng mới. Một thao tác nhầm trên uplink có thể làm mất kết nối của nhiều hệ thống, kể cả đường truy cập dùng để sửa chính lỗi vừa gây ra.

Trong Privileged Access Management (PAM), switch administrator không chỉ là một username có quyền cao. Đó là khả năng thay đổi ranh giới kết nối, tính sẵn sàng và đường quản trị của mạng. Cần biết ai được dùng khả năng này, trên thiết bị nào, ở phạm vi cổng hoặc chức năng nào và trong thời gian bao lâu.

Bài học trình bày cách quản trị đặc quyền đối với switch từ kiểm kê, phân quyền, AAA, credential và giám sát phiên đến quy trình thay đổi, phục hồi và thu hồi. Các ví dụ chính sách là mô hình minh họa, không phải cấu hình có thể chép trực tiếp vào thiết bị của mọi hãng.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

- Xác định phạm vi tác động của quyền quản trị switch.
- Tách nhiệm vụ quan sát, vận hành cổng, cấu hình mạng, quản lý danh tính và bảo trì nền tảng.
- Phân biệt xác thực, phân quyền phiên, phân quyền lệnh và accounting.
- Thiết kế truy cập có thời hạn qua PAM mà vẫn biết quyền hiệu lực trên thiết bị.
- Bảo vệ CLI, API, SNMP, console và đường tự động hóa nhất quán.
- Thực hiện thay đổi có bằng chứng, phương án phục hồi và kiểm tra quyền tồn dư.

## 2. Quyền quản trị switch ảnh hưởng những gì?

Switch có thể thực hiện nhiều vai trò: access, aggregation, core, phân phối lưu lượng trong datacenter hoặc cung cấp chức năng lớp 3. Tác động cần đánh giá theo cấu hình thực tế, không chỉ theo tên thiết bị.

| Nhóm cấu hình | Tác động có thể phát sinh |
| --- | --- |
| Cổng vật lý | Ngắt kết nối endpoint, máy chủ, uplink hoặc thành viên liên kết gộp |
| VLAN và trunk | Thay phạm vi kết nối, cách ly và lưu lượng giữa các miền |
| Cơ chế chống vòng lặp | Ảnh hưởng hội tụ và khả năng chuyển tiếp của mạng |
| Liên kết gộp hoặc dự phòng | Làm mất đường chịu lỗi hoặc gây phân phối lưu lượng không đúng |
| ACL và chức năng lọc | Cho phép hoặc ngăn luồng dữ liệu, kể cả đường quản trị |
| Định tuyến nếu thiết bị hỗ trợ | Ảnh hưởng đường đi và kết nối ngoài một VLAN |
| AAA và người dùng | Thay ai được vào thiết bị và quyền được cấp |
| Quản trị, logging và thời gian | Làm mất quan sát, bằng chứng hoặc khả năng truy vết |
| Firmware và khởi động | Tác động khả năng hoạt động lâu dài của thiết bị |

Một thay đổi nhỏ về số dòng chưa chắc có phạm vi tác động nhỏ. Đổi VLAN trên một uplink khác hoàn toàn đổi VLAN trên cổng endpoint được phân công.

### 2.1. Ba lớp cần nhìn cùng nhau

Có thể phân tích:

- **Management plane:** đường quản trị như CLI, API, giao diện web, SNMP và dịch vụ điều khiển.
- **Control plane:** các cơ chế giúp thiết bị quyết định trạng thái mạng và cách chuyển tiếp.
- **Data plane:** lưu lượng thực tế được thiết bị chuyển tiếp hoặc lọc.

Quyền thay đổi management plane có thể mở đường kiểm soát các lớp khác. Ngược lại, thay đổi dữ liệu hoặc định tuyến có thể cắt luôn đường tới AAA, PAM và hệ thống log.

Vì vậy, một phiên quản trị cần được thiết kế cùng phương án duy trì hoặc phục hồi kết nối.

### 2.2. Ranh giới của thiết bị và của hệ thống điều khiển

Một switch có thể được quản lý trực tiếp hoặc thông qua controller, nền tảng cấu hình tập trung và pipeline tự động hóa.

Người có quyền sửa cấu hình mong muốn trên controller có thể gián tiếp tác động nhiều switch. Một principal không có password trực tiếp của switch chưa chứng minh họ không có quyền quản trị mạng.

Cần kiểm kê cả nơi ra quyết định và principal thực hiện lệnh trên thiết bị.

## 3. Định nghĩa nhiệm vụ trước khi chọn role

Không bắt đầu từ câu “người này là network admin nên cấp toàn quyền”. Hãy mô tả công việc:

> Kỹ thuật viên được xem trạng thái và đưa một nhóm cổng access đã chỉ định về trạng thái vận hành theo ticket; không được sửa uplink, trunk, AAA hoặc logging.

Sau đó kiểm tra thiết bị và nền tảng phân quyền có cưỡng chế được mô tả đó hay không.

| Nhiệm vụ | Quyền cần thiết để bắt đầu thiết kế | Quyền cần xem xét riêng |
| --- | --- | --- |
| Quan sát | Đọc trạng thái cổng, bộ đếm và thông tin phù hợp | Đọc cấu hình chứa secret, xuất toàn bộ dữ liệu |
| Vận hành access port | Thay những thuộc tính được giao trên cổng đã xác định | Uplink, trunk, liên kết gộp, VLAN quản trị |
| Thay cấu hình mạng | Cấu hình đã duyệt trên thiết bị và phạm vi cụ thể | AAA, tài khoản, firmware, logging |
| Quản lý danh tính | User, role, khóa và tích hợp AAA | Thay cấu hình chuyển tiếp không liên quan |
| Bảo trì nền tảng | Firmware, boot, restart theo quy trình | Tự cấp quyền thường trực hoặc tắt audit |
| Tự động hóa | Tác vụ và tập thiết bị của job | Shell hoặc cấu hình tùy ý bằng credential toàn quyền |

Bảng không phải một danh sách role bắt buộc. Nó giúp tách phạm vi trước khi ánh xạ sang cơ chế của từng nền tảng.

### 3.1. Quyền đọc cấu hình cũng có thể nhạy cảm

Bản cấu hình có thể chứa username, secret, định tuyến quản trị, ACL, thông tin tích hợp hoặc metadata mạng.

Không mặc định mọi lệnh hiển thị đều an toàn cho tất cả người dùng. Một lệnh chẩn đoán hoặc xuất dữ liệu còn có thể tiêu tốn tài nguyên, tạo file hoặc chuyển thông tin ra ngoài.

### 3.2. Privilege level không tự mô tả nhiệm vụ

Một số nền tảng sử dụng mức quyền, role, command set hoặc view. Tên và số mức có ngữ nghĩa riêng.

Cần kiểm tra quyền thực tế của phiên và những đường nâng quyền. Không dùng một con số privilege trong hồ sơ làm bằng chứng duy nhất rằng chủ thể chỉ quản lý được một cổng.

## 4. Kiểm kê đường vào và quyền hiệu lực

Một danh mục quản trị nên ghi:

| Thành phần | Thông tin cần xác định |
| --- | --- |
| Thiết bị | Định danh, vị trí, vai trò mạng, model và phiên bản |
| Phạm vi | Thiết bị độc lập, stack, cặp dự phòng hoặc miền controller |
| Endpoint quản trị | Địa chỉ, mạng hoặc VRF quản trị, cổng kết nối |
| Đường vào | SSH, HTTPS, API, SNMP, console hoặc nền tảng tập trung |
| Principal | Người dùng, nhóm, workload và tài khoản khẩn cấp |
| Quyền | Role thiết bị, command set, phạm vi interface hoặc đối tượng |
| Credential | Cơ chế xác thực, nơi bảo quản, chủ sở hữu, vòng đời |
| Bằng chứng | Accounting, syslog, ghi phiên và cấu hình trước/sau |
| Phục hồi | OOB, console server, người tại chỗ và quy trình liên quan |

### 4.1. Cổng không chỉ là một nhãn

Cần liên kết cổng với chức năng thực tế và chủ sở hữu. Ví dụ, một cổng ghi “spare” trong bảng cũ có thể đã trở thành uplink cho một thiết bị khác.

Khi thiết bị là stack hoặc có nhiều thành viên, kiểm tra đúng định danh thành viên và interface. Nếu phần cứng đã thay, tên cổng có thể không phản ánh cùng kết nối như trước.

Không dựa vào mô tả interface do người dùng tự nhập như nguồn duy nhất để quyết định quyền.

### 4.2. Những đường dễ bị bỏ sót

- Tài khoản local không còn người quản lý.
- Một secret nâng quyền dùng chung.
- SNMP có quyền ghi.
- Giao diện web hoặc API ít được dùng nhưng vẫn mở.
- Console server có tài khoản riêng.
- Bộ công cụ sao lưu cấu hình dùng credential quản trị.
- Controller hoặc agent tự động hóa có quyền rộng.
- Cấu hình khởi động hoặc bản dự phòng còn chứa credential cũ.

Mỗi đường cần được đặt trong phạm vi PAM hoặc có lý do, kiểm soát và chủ sở hữu rõ ràng.

## 5. Kiến trúc truy cập tham khảo

```text
Người vận hành bằng danh tính cá nhân
                 |
                 v
        Xác thực và PAM
    yêu cầu, phê duyệt, giới hạn phiên
                 |
                 v
   Proxy / bastion hoặc đường được phép
                 |
                 v
               Switch
   xác thực + quyền phiên + quyền thao tác
                 |
                 v
       Cấu hình và trạng thái thực tế

AAA, accounting, log thiết bị và bản ghi thay đổi
được liên kết với cùng yêu cầu.
```

PAM và AAA có vai trò liên quan nhưng không thay thế nhau.

PAM có thể quản lý yêu cầu, credential, thời hạn và bản ghi phiên. Thiết bị hoặc controller vẫn cần thực thi những quyền phù hợp tại nơi thao tác xảy ra.

### 5.1. Chặn đường bỏ qua cổng quản trị

Nếu tất cả kiểm soát chỉ nằm ở bastion nhưng người dùng vẫn biết password và có thể vào trực tiếp, quyền thực tế rộng hơn thiết kế.

Có thể giới hạn nguồn quản trị, tách mạng quản lý và bảo vệ credential để giữ đường sử dụng được kiểm soát. Cần kiểm tra cả các giao thức ngoài SSH.

### 5.2. Cổng dùng principal backend chung

Nếu PAM đăng nhập switch bằng một principal dùng chung, audit tại switch có thể chỉ thấy danh tính đó.

Cần liên kết người yêu cầu, lần cấp phiên, principal backend, thiết bị, thời gian và thao tác. Nếu nhiều người dùng đồng thời mà không phân biệt được, phải ghi nhận và xử lý giới hạn quy trách nhiệm.

Không coi địa chỉ IP của bastion là danh tính đầy đủ của người đang thao tác.

## 6. Authentication, authorization và accounting

Ba thành phần cần được thiết kế riêng:

- **Authentication:** chứng minh principal nào đang yêu cầu truy cập.
- **Authorization:** quyết định principal được vào phiên nào và làm gì.
- **Accounting:** ghi hoạt động đã diễn ra theo phạm vi triển khai.

TACACS+ tách ba chức năng này và hỗ trợ bối cảnh quản trị thiết bị, bao gồm kiểm soát hoặc ghi nhận lệnh tùy triển khai. Bật xác thực TACACS+ không tự chứng minh đã bật đủ phân quyền lệnh và accounting. [RFC 8907](https://www.rfc-editor.org/rfc/rfc8907).

### 6.1. Xác thực cá nhân và workload

Con người cần danh tính cá nhân hoặc cơ chế liên kết có thể quy trách nhiệm. Công cụ tự động hóa cần principal riêng theo mục đích.

Không dùng cùng một tài khoản cho kỹ thuật viên, job sao lưu và hệ thống cấu hình. Khi nghi credential bị lộ, cần thu hồi được đúng phạm vi mà không làm mọi hoạt động dừng cùng lúc.

Xác thực tăng cường cần được đặt tại điểm mà nền tảng hỗ trợ và được kiểm tra. Một switch cũ không tự thực thi MFA cho mỗi lệnh chỉ vì người dùng đã vào một cổng PAM có MFA.

### 6.2. Quyền phiên khác với quyền lệnh

Một người có thể được phép mở shell nhưng không được vào chế độ cấu hình hoặc thực hiện mọi lệnh bên trong.

Cần kiểm tra:

- Phiên nhận role hoặc mức quyền nào?
- Thiết bị có gửi yêu cầu phân quyền lệnh không?
- Những lệnh, mode và giao thức nào được kiểm tra?
- Có đường nâng quyền bằng secret hoặc cơ chế khác không?
- Khi hệ thống phân quyền không phản hồi, hành vi là gì?

### 6.3. Bảo vệ kênh AAA

Không suy rằng TACACS+ nguyên bản cung cấp kênh bảo mật hiện đại chỉ từ tên giao thức. RFC 8907 nêu giới hạn của cơ chế obfuscation; RFC 9887 định nghĩa TACACS+ qua TLS 1.3. Khả năng sử dụng phụ thuộc thiết bị và server thực tế. [RFC 8907](https://www.rfc-editor.org/rfc/rfc8907), [RFC 9887](https://www.rfc-editor.org/rfc/rfc9887).

Cần bảo vệ đường truyền, kiểm tra khả năng tương thích và quản trị danh tính của hai đầu theo phương thức được hỗ trợ. Không bật một tùy chọn transport trên server rồi báo rằng mọi client đã sử dụng kênh đó.

Shared secret thiết bị và credential của người dùng là hai loại bí mật khác nhau. Chúng có vòng đời và phạm vi ảnh hưởng riêng.

## 7. Phân quyền lệnh và giới hạn chức năng

### 7.1. Phạm vi phải bao gồm tham số và ngữ cảnh

Cho phép một họ lệnh cấu hình interface chưa chắc giới hạn được đúng cổng access.

Cần đánh giá tên interface, tập interface, mode hiện tại, tham số và tác động. Một lệnh trên uplink hoặc một nhóm interface có thể rộng hơn một thao tác được duyệt cho một port.

Nếu cơ chế thiết bị không cưỡng chế được phạm vi đó, cần công cụ thực thi hẹp hơn hoặc quy trình kiểm soát phù hợp. Không mô tả một command set rộng là phân quyền theo cổng khi chưa có ranh giới thực tế.

### 7.2. Kiểm tra các đường biểu diễn khác

Một tác vụ có thể được thực hiện qua CLI, API, tải file cấu hình hoặc controller.

Cần kiểm tra alias, dạng viết tắt, thao tác nhiều dòng, chức năng import/replace, script và khả năng shell nếu nền tảng có. Mục tiêu là xác định kiểm soát có bao phủ hành động thật hay chỉ một chuỗi lệnh hiển thị.

Không dùng một regex đơn giản làm bằng chứng duy nhất rằng mọi cách sửa AAA hoặc tạo user đều bị chặn.

### 7.3. Kiểm soát chức năng quản trị nhạy cảm riêng

Các nhóm sau thường cần quyền hoặc quy trình riêng:

- Tạo user, role hoặc khóa đăng nhập.
- Sửa AAA và hành vi fallback.
- Thay management endpoint hoặc ACL quản trị.
- Tắt audit, syslog hoặc đồng bộ thời gian.
- Xuất cấu hình và dữ liệu chẩn đoán.
- Thay firmware, boot hoặc khởi động lại.
- Bật giao thức quản trị mới.
- Thay quyền của controller hoặc tài khoản tự động hóa.

Tài liệu Cisco IOS XE nêu vai trò của command authorization, accounting và quản lý cấu hình trong kiểm soát thiết bị. Khi áp dụng cần đối chiếu model và phiên bản cụ thể. [Cisco IOS XE Software Integrity Assurance](https://sec.cloudapps.cisco.com/security/center/resources/ios_xe_integrity_assurance.html).

## 8. Cấp quyền JIT cho tác vụ switch

Một yêu cầu có thể được mô tả như sau:

```yaml
request_id: CHG-example-418
requester: engineer-example
device_ids:
  - SW-LAB-16
scope:
  interfaces:
    - access-port-12
  actions:
    - inspect-link
    - apply-approved-access-profile
change_artifact: profile-example-v3
approval_expires_at: "2026-01-12T04:00:00Z"
requires_recovery_path: true
```

Đây là hồ sơ chính sách minh họa, không phải cấu hình switch. Trường hết hạn không tự làm switch kết thúc phiên hoặc role.

### 8.1. Xác minh đầu vào phía server

Hệ thống cấp quyền cần ánh xạ device_id và interface tới tài sản tin cậy, đối chiếu người yêu cầu và artifact được duyệt.

Không tin một nhãn access-port do client gửi để bỏ qua kiểm tra. Phải biết cổng thực tế có phải uplink, thành viên liên kết gộp hoặc mang dịch vụ khác không.

### 8.2. Thời hạn có nhiều lớp

Phân biệt:

- Thời hạn phê duyệt thay đổi.
- Thời hạn người dùng được nhận credential hoặc mở phiên.
- Thời hạn grant trên AAA hoặc thiết bị.
- Tuổi thọ kết nối đang mở.

Một phiên SSH còn hoạt động có thể cần xử lý riêng khi grant kết thúc. Idle timeout cũng không mặc định là giới hạn thời gian tuyệt đối của phiên đang được sử dụng.

### 8.3. Credential ngắn hạn không thay quyền hẹp

Một credential toàn quyền có hạn ngắn vẫn có thể tạo user, đổi AAA hoặc sửa cấu hình tồn tại sau phiên.

JIT cần kết hợp phạm vi quyền và kiểm tra sau sử dụng. Khi kết thúc, phải biết có grant, tài khoản, khóa hoặc cấu hình mới nào ngoài nội dung đã được phép hay không.

## 9. Bảo vệ mọi giao diện quản trị

### 9.1. Mạng quản trị và nguồn truy cập

Giới hạn endpoint quản trị tới những nguồn và đường được phép. Sử dụng mạng, VRF hoặc kiến trúc quản lý phù hợp với nền tảng và mức tác động.

Một VLAN quản trị không tự là mạng out-of-band độc lập. Nếu nó vẫn đi qua cùng switch, uplink hoặc cấu hình đang thay đổi, sự cố có thể làm mất cả đường điều khiển.

Cần phân biệt:

- Đường quản trị dùng hằng ngày.
- Đường quan sát hoặc tự động hóa.
- Đường phục hồi khi đường chính mất.
- Những phụ thuộc chung còn tồn tại giữa chúng.

### 9.2. CLI và giao diện web

Chọn giao thức và cơ chế xác thực phù hợp với thiết bị, bảo vệ tính bí mật và toàn vẹn của phiên. Xác minh host hoặc endpoint theo phương thức được hỗ trợ.

Không chấp nhận mọi thay đổi host key hoặc chứng thư một cách máy móc. Một endpoint bị nhầm hoặc giả có thể nhận credential quản trị.

Tắt dịch vụ không sử dụng theo quy trình thay đổi. Trước khi tắt, kiểm tra các hệ thống quản lý, giám sát và phục hồi còn phụ thuộc vào chúng.

### 9.3. API và tự động hóa

Danh tính API cần quyền theo tác vụ và tập thiết bị. API key của controller không nên được dùng như tài khoản cá nhân hoặc đưa cho mọi kỹ thuật viên.

Nếu CLI bị giới hạn nhưng API cho phép thay toàn bộ cấu hình, ranh giới quyền chưa nhất quán.

Đối với job tự động, giữ liên kết giữa người hoặc quy trình khởi phát, artifact được duyệt, principal thực thi và kết quả trên switch.

### 9.4. SNMP là một đường quyền riêng

SNMP có thể phục vụ giám sát và, tùy quyền được cấp, thay đổi đối tượng quản trị.

SNMPv3 có mô hình bảo vệ thông điệp; cần chọn mức xác thực và bảo mật nội dung phù hợp, không chỉ bật tên phiên bản rồi coi dữ liệu đã được bảo vệ. [Mô hình USM](https://www.rfc-editor.org/rfc/rfc3414).

Phân quyền đọc, ghi và phạm vi đối tượng phải được xem xét riêng. VACM mô tả kiểm soát truy cập theo view và loại truy cập; danh tính giám sát không mặc định cần quyền ghi. [Mô hình VACM](https://www.rfc-editor.org/rfc/rfc3415).

Kiểm tra thuật toán và khả năng được hỗ trợ trên phiên bản thực tế. Không sao chép nguyên những lựa chọn cũ từ một ví dụ giao thức mà không đánh giá chính sách hiện tại.

### 9.5. Console và đường vật lý

Console server và truy cập tại chỗ có thể bỏ qua một phần đường quản trị thông thường. Chúng vẫn cần danh tính, thẩm quyền, bảo quản credential và bằng chứng.

Người có quyền vào console server không mặc nhiên được vào mọi switch nối tới nó. Phân quyền theo cổng console và tài sản nếu nền tảng hỗ trợ.

Quản lý vật lý, thiết bị lưu cấu hình, phương tiện nâng cấp và quy trình phục hồi password cũng thuộc phạm vi rủi ro quản trị. Không để một đường phục hồi không được kiểm kê trở thành quyền quản trị ngoài PAM.

## 10. Hành vi khi AAA hoặc PAM gặp sự cố

Tính sẵn sàng và kiểm soát quyền phải được thiết kế cùng nhau.

### 10.1. Phân biệt từ chối với không liên lạc được

Một server trả lời rằng người dùng không được phép khác với tình huống server không phản hồi.

Không cấu hình hoặc mô tả fallback như một cơ chế chuyển mọi yêu cầu bị từ chối sang tài khoản local rộng hơn. Hành vi chính xác tùy thiết bị, phương thức và cấu hình, nên cần thử từng trường hợp.

Ma trận cần kiểm tra:

| Tình huống | Câu hỏi vận hành |
| --- | --- |
| Server xác thực từ chối | Thiết bị có giữ quyết định từ chối đúng thiết kế không? |
| Server xác thực không tới được | Có đường dự phòng nào được phép? |
| Xác thực được nhưng phân quyền lệnh lỗi | Lệnh bị từ chối, chờ hay được xử lý theo policy nào? |
| Accounting không gửi được | Tác vụ nào tiếp tục, ghi đệm hoặc phải dừng? |
| Một server trong cụm AAA mất | Chuyển sang server khác có giữ nguyên policy không? |
| PAM mất nhưng switch và AAA còn hoạt động | Có được mở đường khẩn cấp; ai quyết định? |

Đăng nhập thành công trong một lần thử không chứng minh các nhánh lỗi đều an toàn.

### 10.2. Credential local khẩn cấp

Nếu cần tài khoản local để phục hồi, xác định rõ:

- Mục đích và điều kiện sử dụng.
- Thiết bị áp dụng.
- Người được nhận credential.
- Nơi bảo quản không phụ thuộc hoàn toàn vào đường đang dự phòng.
- Phạm vi truy cập và cách ghi bằng chứng.
- Cách xử lý credential sau sử dụng.

Không phát một password local chung cho toàn bộ mạng để “phòng khi AAA hỏng”.

### 10.3. Đường out-of-band thực sự còn hoạt động không?

Kiểm tra mạng console, nguồn điện, DNS, xác thực và người giữ phương tiện. Nếu console server vẫn cần cùng IdP đang mất, phải ghi nhận giới hạn đó.

Đường OOB giúp xử lý một số lỗi kết nối hoặc cấu hình, nhưng không bảo đảm sửa được thiết bị hỏng phần cứng hay control plane không đáp ứng. Cần nhánh chuyển cấp và phương án tại chỗ phù hợp.

### 10.4. Khôi phục quyền không đồng nghĩa tắt mọi kiểm soát

Nếu một thay đổi AAA làm mất truy cập, ưu tiên sửa đúng cấu hình gây lỗi từ nguồn đáng tin.

Không mặc định mở quản trị từ mọi địa chỉ, bỏ phân quyền lệnh hoặc tắt logging. Nếu phải áp dụng ngoại lệ trong quy trình được phép, ghi phạm vi, thời hạn và bước đóng ngoại lệ.

## 11. Credential và luân chuyển

Switch có thể có nhiều loại bí mật:

| Loại | Ví dụ phạm vi |
| --- | --- |
| Credential người dùng | Danh tính cá nhân hoặc local được quản lý |
| Secret nâng quyền | Cơ chế chuyển mức quyền nếu nền tảng có |
| Bí mật AAA | Quan hệ tin cậy giữa thiết bị và server |
| Credential tự động hóa | Job cấu hình, backup hoặc giám sát |
| Credential SNMP | Xác thực và bảo vệ thông điệp theo cấu hình |
| Khóa hoặc chứng thư quản trị | SSH, HTTPS, API hoặc cơ chế tương ứng |

Không coi thay một password là đã luân chuyển toàn bộ đường quản trị.

### 11.1. Giới hạn phạm vi chia sẻ

Một secret dùng cho nhiều thiết bị có phạm vi ảnh hưởng rộng khi lộ. Thiết kế nên phân chia theo khả năng và mức vận hành, có chủ sở hữu rõ ràng.

Không đồng nhất username trên các thiết bị với việc bắt buộc dùng cùng một password. Cũng không dùng credential của con người cho job định kỳ chỉ vì job đã chạy ổn định từ trước.

### 11.2. Thay đổi cần kiểm tra hai đầu

Với shared secret hoặc quan hệ tin cậy, cập nhật sai thứ tự có thể cắt đường AAA hoặc tự động hóa.

Chuẩn bị cách chuyển đổi được nền tảng hỗ trợ, xác minh kết nối mới và giữ phương án phục hồi hợp lệ. Nếu thiết bị hỗ trợ nhiều khóa hoặc giai đoạn chuyển tiếp, kiểm tra cơ chế cụ thể trước khi dựa vào nó.

Không giả định mọi switch hỗ trợ đổi secret mà không gián đoạn.

### 11.3. Bản backup cũng chứa bí mật

Cấu hình được sao lưu có thể chứa secret hoặc dữ liệu đủ nhạy cảm để hỗ trợ truy cập trái phép. Bảo vệ kho backup, quyền tải, lịch sử phiên bản và kênh truyền.

Một lần restore cấu hình cũ có thể đưa lại credential, user hoặc policy đã bị thu hồi. Kiểm tra nội dung bảo mật trước khi phục hồi.

Đổi secret hiện tại không làm một bản backup không được bảo vệ trở thành dữ liệu công khai an toàn.

### 11.4. Khi nghi credential bị lộ

Xác định credential nào, thiết bị nào và đường nào bị ảnh hưởng. Bảo toàn bằng chứng phù hợp rồi giới hạn khả năng sử dụng theo quy trình ứng phó.

Kiểm tra phiên còn hoạt động, user hoặc khóa mới, thay đổi AAA và cấu hình persist. Luân chuyển credential không tự đảo những thay đổi kẻ sử dụng credential đã thực hiện.

## 12. Quy trình thay đổi cấu hình an toàn

### 12.1. Trước thay đổi

Xác định:

- Đúng thiết bị, vai trò và phạm vi vật lý hoặc logic.
- Cổng, VLAN và các dịch vụ liên quan.
- Cấu hình trước, artifact dự kiến và phần chênh lệch.
- Các đường quản trị, AAA và logging có thể bị ảnh hưởng.
- Người phê duyệt và cửa sổ thực hiện.
- Phương án phục hồi và người có thể thực hiện.
- Tiêu chí thành công, dừng hoặc chuyển cấp.

Không chỉ kiểm tra một interface riêng lẻ nếu nó là thành viên của liên kết gộp hoặc có phụ thuộc ở thiết bị đối diện.

### 12.2. Trong thay đổi

Xác minh principal và quyền hiệu lực, áp dụng nội dung đã được duyệt và quan sát kết quả từng bước theo thiết kế.

Nếu cấu hình quản lý tập trung, xác định nguồn cấu hình mong muốn. Thay đổi trực tiếp có thể bị controller hoàn nguyên; một nguồn sai cũng có thể liên tục áp dụng lại lỗi.

Không cho nhiều người sửa chồng cùng phạm vi mà không có điều phối. Cần biết ai đang giữ phiên và thay đổi nào đang diễn ra.

### 12.3. Cơ chế commit, lưu và rollback khác nhau

Các nền tảng có thể sử dụng cấu hình hiệu lực ngay, cấu hình ứng viên, commit hoặc cơ chế lưu để tồn tại sau khởi động lại.

Cần biết:

- Thay đổi đã tác động forwarding chưa?
- Có tồn tại sau restart không?
- Có bước xác nhận hoặc lưu riêng không?
- Quyền của người thực hiện có cho phép bước đó không?
- Rollback khôi phục phần nào và có ảnh hưởng thay đổi của người khác không?

Nếu nền tảng hỗ trợ xác nhận có thời hạn hoặc rollback tự động, kiểm tra điều kiện và tác dụng thực tế. Không giả định cơ chế này có trên mọi switch hoặc thay thế hoàn toàn đường OOB.

### 12.4. Sau thay đổi

Kiểm tra cả trạng thái cấu hình và hoạt động:

- Cổng, liên kết và đường dự phòng đúng kỳ vọng.
- Phạm vi VLAN hoặc chức năng kết nối không bị mở rộng ngoài yêu cầu.
- Endpoint và ứng dụng liên quan hoạt động.
- Đường PAM, AAA và logging còn sử dụng được.
- Cấu hình hiệu lực và trạng thái lưu đúng thiết kế.
- Không còn phiên hoặc grant ngoài nhiệm vụ.
- Nguồn cấu hình tập trung đã đồng bộ phù hợp.

Một thông báo CLI chấp nhận câu lệnh không chứng minh dịch vụ đầu cuối đã hoạt động đúng.

## 13. Audit và giám sát phiên

Chuỗi bằng chứng cần nối được:

```text
Người hoặc workload
  → yêu cầu và phê duyệt
  → phiên PAM / principal thiết bị
  → lệnh hoặc thao tác API
  → thay đổi cấu hình thực tế
  → ảnh hưởng và kết quả kiểm tra
  → kết thúc quyền và phiên
```

### 13.1. Nhiều loại bằng chứng bổ sung nhau

- Accounting giúp ghi hoạt động theo phạm vi đã cấu hình.
- Syslog giúp quan sát sự kiện của thiết bị.
- Bản ghi phiên cho thấy tương tác qua đường được ghi.
- Config diff cho thấy trạng thái thay đổi.
- Kiểm tra mạng và ứng dụng cho thấy tác động thực tế.

Không coi command accounting là bằng chứng đầy đủ rằng mọi thay đổi thành công. Cũng không coi config diff là bằng chứng về người thực hiện nếu không có liên kết danh tính và thời gian.

### 13.2. Dữ liệu nhạy cảm trong bản ghi

Output, transcript, accounting và cấu hình có thể chứa secret, địa chỉ quản trị hoặc thông tin mạng nội bộ.

Bảo vệ quyền đọc bản ghi, thời hạn lưu và các bản export. Tránh ghi credential trong tham số lệnh hoặc kênh tự động hóa có log rộng.

Không xóa tùy tiện bằng chứng vì phát hiện secret trong log. Cần xử lý sự cố bí mật và bảo quản dữ liệu theo quy trình có thẩm quyền.

### 13.3. Những tín hiệu đáng điều tra

- Đăng nhập quản trị từ nguồn hoặc thời điểm bất thường.
- Nhiều lần bị từ chối rồi dùng tài khoản local khẩn cấp.
- Tạo user, khóa hoặc secret nâng quyền mới.
- Thay AAA, fallback, quản trị hoặc logging.
- Mở giao thức quản trị trước đó không được dùng.
- Thay nhiều switch ngoài phạm vi job.
- Tạo cơ chế mirror hoặc xuất dữ liệu ngoài nhiệm vụ.
- Thay firmware, boot hoặc cấu hình persist ngoài kế hoạch.
- Một principal chỉ backup bắt đầu sửa cấu hình.
- Khoảng trống log trùng với thay đổi quyền cao.

Tín hiệu không tự chứng minh có tấn công. Cần đối chiếu nhiệm vụ, principal, thiết bị, nội dung và kết quả.

### 13.4. Đồng bộ thời gian và bảo vệ nơi lưu

Sai lệch thời gian có thể làm việc nối phiên, lệnh và sự kiện khó hơn. Cần theo dõi nguồn thời gian và ghi nhận sai lệch khi điều tra.

Một người có quyền quản trị switch có thể sửa những thành phần ghi log nằm trong phạm vi thiết bị. Đưa bằng chứng tới nơi được bảo vệ và kiểm tra quyền ở cả collector, kho lưu và nền tảng quản lý.

Không tuyên bố bằng chứng độc lập chỉ vì syslog gửi tới một IP khác nếu cùng principal có thể xóa toàn bộ nơi nhận.

## 14. Kết thúc phiên và thu hồi

### 14.1. Đóng đúng những lớp đã cấp

Khi nhiệm vụ xong:

1. Ngừng cấp phiên hoặc credential mới cho yêu cầu.
2. Kết thúc grant trên AAA, controller hoặc thiết bị theo thiết kế.
3. Xử lý phiên CLI, API hoặc kết nối còn hoạt động.
4. Kiểm tra user, khóa và quyền mới phát sinh.
5. Xử lý credential đã được tiết lộ hoặc dùng chung theo chính sách.
6. Đối chiếu cấu hình với phạm vi thay đổi.
7. Lưu bằng chứng và ghi tồn dư nếu còn.

Đóng trang PAM không tự chứng minh phiên trên switch đã chấm dứt.

### 14.2. Kiểm tra phiên cũ và đăng nhập mới

Gỡ người dùng khỏi nhóm có thể không làm mọi phiên nhận quyền trước đó mất hiệu lực ngay. Hành vi tùy hệ thống và loại authorization.

Cần thử những hành động quan trọng theo cơ chế thực tế. Phân biệt “không mở được phiên mới” với “không còn thao tác được trong phiên cũ”.

### 14.3. Quyền và cấu hình tồn dư

Đặc biệt kiểm tra:

- Local user hoặc SSH key ngoài kiểm kê.
- Role, privilege hoặc secret nâng quyền bị đổi.
- AAA fallback rộng hơn trước.
- Dịch vụ quản trị mới được bật.
- Logging hoặc ACL quản trị bị nới.
- Cấu hình lưu lâu dài khác với cấu hình đã duyệt.
- Controller có thể tái tạo ngoại lệ.
- Cổng, VLAN hoặc đường mirror ngoài phạm vi yêu cầu.

Credential ngắn hạn đã hết hiệu lực không làm những thay đổi này tự biến mất.

## 15. Tình huống thực hành: đổi cấu hình một access port

Một kỹ thuật viên được giao đưa một endpoint thử nghiệm vào mạng được phê duyệt trên SW-LAB-16. Hệ thống trước đây cấp tài khoản local toàn quyền để người đó tự làm.

### 15.1. Xác định phạm vi thật

Đối chiếu inventory và trạng thái hiện tại để xác nhận cổng đích đúng là cổng endpoint được giao.

Kiểm tra nó có đang là uplink, thành viên liên kết gộp, kết nối tới thiết bị đa dịch vụ hoặc mang những chức năng khác không. Một mô tả cũ không đủ để kết luận.

Xác định profile hoặc phần cấu hình được phép, thiết bị đối diện và điều kiện kiểm tra đầu cuối.

### 15.2. Thiết kế quyền

Có thể dùng một công cụ áp profile access đã duyệt trên đúng cổng, hoặc role thiết bị hẹp nếu nền tảng thực thi được cả chức năng và tham số cần thiết.

Kỹ thuật viên không cần được sửa AAA, tạo user, tải toàn bộ cấu hình hoặc đổi uplink.

Nếu công cụ backend có quyền rộng, nó phải tự kiểm tra cổng và artifact, không chỉ nhận chuỗi lệnh tùy ý từ client.

### 15.3. Thực hiện

Người được giao đăng nhập bằng danh tính cá nhân và nhận phiên theo thời hạn.

Hệ thống ghi thiết bị, interface, cấu hình trước và profile đích. Thao tác được áp dụng theo quy trình có kiểm tra kết quả, trạng thái lưu và đường quản trị.

Nếu tác động khác dự kiến, dừng hoặc phục hồi theo điều kiện đã định nghĩa. Không tiếp tục sửa nhiều cổng để thử tìm kết nối trong khi không cập nhật phạm vi.

### 15.4. Đóng nhiệm vụ

Kiểm tra endpoint đúng mạng, dịch vụ cần thiết hoạt động và không có thay đổi ở uplink hoặc cổng khác.

Kết thúc phiên, thu hồi quyền và đối chiếu audit. Xác nhận không có local user hoặc ngoại lệ mới được giữ lại.

Kết quả tốt không chỉ là endpoint có kết nối, mà còn là người thực hiện không còn quyền ngoài nhiệm vụ sau khi việc đã xong.

## 16. Bộ kiểm tra nghiệm thu

| Tình huống | Điều cần chứng minh |
| --- | --- |
| Người quan sát đọc trạng thái được phép | Hoàn thành nhiệm vụ hợp lệ |
| Người quan sát yêu cầu output chứa dữ liệu nhạy cảm | Phạm vi đọc được kiểm soát |
| Kỹ thuật viên đổi cổng access được giao | Thực hiện đúng chức năng và tham số |
| Chọn uplink hoặc nhóm interface rộng hơn | Bị kiểm soát theo thiết kế |
| Dùng dạng lệnh, mode hoặc đường API khác | Không vượt được ranh giới quyền tương ứng |
| Dùng SNMP hoặc controller thay CLI | Quyền hiệu lực nhất quán với mục đích |
| Một job backup yêu cầu sửa cấu hình | Không được cho phép ngoài nhiệm vụ |
| AAA trả từ chối | Không tự chuyển thành quyền rộng qua fallback |
| AAA không phản hồi | Nhánh dự phòng đúng chính sách và có bằng chứng |
| Phân quyền lệnh lỗi trong phiên đã xác thực | Hành vi được kiểm tra rõ |
| Accounting hoặc nơi lưu log mất | Có phát hiện và hành vi được định nghĩa |
| Thay credential hai đầu | Kết nối mới hoạt động và đường cũ được xử lý |
| Grant hết hạn khi phiên vẫn mở | Phiên được giới hạn hoặc kết thúc đúng thiết kế |
| Người dùng có thể truy cập trực tiếp ngoài PAM | Đường bỏ qua được phát hiện và xử lý |
| Restore bản cấu hình cũ | Không âm thầm đưa lại user hoặc secret ngoài quản lý |
| Thay đổi đã áp dụng nhưng chưa lưu persist | Trạng thái được nhận diện theo nền tảng |
| Controller reconcile sau thay đổi tay | Không tái tạo cấu hình sai hoặc ngoại lệ ngoài phạm vi |
| Mất đường quản trị chính | Đường phục hồi còn khả dụng trong kịch bản đã thiết kế |
| Kết thúc quyền cao | Không còn user, key, phiên hoặc cấu hình tồn dư chưa giải thích |

Các phép thử làm thay đổi forwarding, AAA hoặc khởi động thiết bị phải nằm trong môi trường và phạm vi được phép. Không tạo mất kết nối production để chứng minh có đường phục hồi nếu chưa có kế hoạch được ủy quyền.

## 17. Bài tập áp dụng

Bạn tiếp nhận một nhóm switch có các tình trạng:

- Cả đội dùng một password local toàn quyền.
- AAA chỉ được dùng cho đăng nhập, chưa kiểm tra phân quyền lệnh.
- SNMP giám sát và sao lưu cấu hình dùng cùng credential.
- Người dùng vẫn có thể vào trực tiếp ngoài PAM.
- Chưa diễn tập khi AAA mất hoặc khi thay VLAN quản trị sai.
- Config backup nằm trong thư mục chia sẻ rộng.

Hãy thiết kế phương án:

1. Kiểm kê đường vào, principal, thiết bị và phạm vi cổng.
2. Tách vai trò quan sát, vận hành access, cấu hình mạng và quản lý danh tính.
3. Ánh xạ quyền vào khả năng thiết bị hoặc công cụ thực thi hẹp.
4. Xây dựng JIT và kiểm tra phiên còn hoạt động.
5. Bảo vệ CLI, API, SNMP, controller và console.
6. Thiết kế fallback và đường phục hồi có thể kiểm chứng.
7. Luân chuyển credential và bảo vệ backup.
8. Xác định audit cùng bộ kiểm tra kết thúc quyền.

Một đáp án tốt chỉ rõ nơi cưỡng chế từng giới hạn. Đưa password vào vault hoặc bật AAA đăng nhập chưa đủ để giải quyết toàn bộ bài toán.

## 18. Tiêu chí hoàn thành

Quản trị đặc quyền switch đạt mục tiêu khi chứng minh được:

- Nhiệm vụ, thiết bị, cổng và phạm vi tác động được xác định chính xác.
- Danh tính con người và workload có chủ sở hữu, có thể quy trách nhiệm.
- Quyền phiên và quyền thao tác được kiểm tra theo khả năng nền tảng.
- Những giới hạn không thể cưỡng chế tại thiết bị được xử lý và mô tả rõ.
- CLI, API, SNMP, controller và console không tạo đường bỏ qua ngoài quản lý.
- Credential và quan hệ tin cậy AAA được bảo vệ theo vòng đời.
- Thay đổi cấu hình có nội dung được duyệt, kiểm tra và phương án phục hồi.
- Bằng chứng nối được người thực hiện với trạng thái thiết bị và kết quả dịch vụ.
- Grant, phiên và cấu hình tồn dư được đối chiếu khi kết thúc.
- Đường phục hồi được bảo quản và diễn tập theo kịch bản thực tế.

Switch administrator nắm quyền tác động trực tiếp tới kết nối và ranh giới mạng. Đưa quyền này vào PAM nghĩa là cung cấp đủ khả năng cho công việc, giữ rõ phạm vi thực thi và chứng minh được cả thay đổi đã làm lẫn quyền đã kết thúc.

