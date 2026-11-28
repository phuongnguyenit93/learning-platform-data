# Network device admin

## 1. Quản trị thiết bị mạng là một miền đặc quyền

Network device admin là khả năng quản lý cấu hình, danh tính, trạng thái và chức năng của thiết bị hoặc hệ thống điều khiển mạng. Đối tượng có thể là router, switch, firewall, thiết bị cân bằng tải, wireless controller, thiết bị VPN hoặc controller quản lý nhiều thiết bị.

Đặc quyền này có thể ảnh hưởng lớn hơn một tài nguyên đơn lẻ:

- Đổi đường đi của lưu lượng.
- Mở hoặc chặn kết nối giữa các vùng.
- Thay cơ chế xác thực quản trị.
- Tiếp cận cấu hình chứa credential hoặc khóa.
- Tắt hoặc làm thiếu bằng chứng.
- Gây gián đoạn khả năng quản trị từ xa.
- Tạo đường truy cập tồn tại sau khi phiên ban đầu kết thúc.

Trong PAM, cần kiểm soát cả ai được kết nối và họ làm được gì sau khi vào thiết bị. Quyền truy cập một bastion hoặc VPN không tự chứng minh quyền trên thiết bị đã tối thiểu.

Ví dụ, kỹ sư chỉ cần kiểm tra trạng thái một đường uplink nhưng nhận cùng tài khoản quản trị với người được đổi chính sách firewall. Hai nhu cầu khác nhau đang bị gộp vào một phạm vi quyền quá rộng.

Sau bài học, bạn có thể kiểm kê đường quản trị, tách role theo tác vụ, thiết kế AAA và JIT phù hợp, quản lý credential và tạo bằng chứng về thay đổi lẫn kết thúc quyền.

## 2. Phân biệt management plane, control plane và data plane

Một cách phân tích hữu ích là tách:

| Miền | Vai trò | Ví dụ tác động của quản trị |
|---|---|---|
| Management plane | Tiếp nhận và xử lý hoạt động quản trị | Đăng nhập, API quản lý, thay cấu hình |
| Control plane | Xây dựng trạng thái điều khiển mạng | Quan hệ định tuyến, thông tin chọn đường |
| Data plane | Xử lý và chuyển tiếp lưu lượng | Chuyển gói, thực thi tập quy tắc chuyển tiếp |

Ranh giới kỹ thuật phụ thuộc kiến trúc thiết bị. Một thao tác management plane có thể làm control plane thay đổi rồi tác động rộng tới data plane.

Vì vậy, một tác vụ quản trị cần được đánh giá theo hậu quả, không chỉ tên lệnh.

Ví dụ:

- Đọc trạng thái interface là nhu cầu quan sát.
- Tắt interface có thể cắt dịch vụ hoặc chính đường quản trị.
- Sửa cấu hình định tuyến có thể đổi đường của nhiều hệ thống.
- Sửa AAA có thể thay ai được quản trị thiết bị.
- Sửa audit có thể giảm khả năng phát hiện và điều tra.

Không xem “network admin” là một quyền đồng nhất. Hãy mô tả các năng lực cụ thể mà tổ chức đang ủy quyền.

## 3. Kiểm kê cả thiết bị và đường quản trị

Inventory nên bao phủ thiết bị vật lý, thiết bị ảo và các hệ thống điều khiển chúng.

### Hồ sơ một tài nguyên

- Định danh tài nguyên ổn định.
- Vai trò mạng và mức ảnh hưởng.
- Đơn vị sở hữu cùng người chịu trách nhiệm.
- Môi trường, site và vùng quản trị.
- Hệ điều hành, phiên bản và khả năng phân quyền liên quan.
- Endpoint quản trị được duyệt.
- Nguồn danh tính và AAA.
- Role đang dùng.
- Credential cục bộ và tài khoản khẩn cấp.
- Kênh console hoặc out-of-band.
- Controller, automation hoặc API có thể sửa cấu hình.
- Nguồn audit và backup cấu hình.
- Phương án khôi phục khi mất truy cập.

### Những đường thường bị bỏ sót

| Đường | Câu hỏi cần trả lời |
|---|---|
| SSH hoặc console dòng lệnh | Ai đăng nhập, được vào ngữ cảnh quyền nào? |
| Giao diện web | Có dùng cùng nguồn danh tính và policy với CLI không? |
| API quản trị | Token hoặc certificate nào, scope nào? |
| NETCONF hoặc RESTCONF | Ai được thao tác operation và dữ liệu cấu hình nào? |
| Giao thức giám sát có quyền ghi | Danh tính giám sát có làm thay đổi thiết bị không? |
| Serial console hoặc console server | Ai quản lý console server và tài khoản thiết bị? |
| Controller tập trung | Quyền trên controller ảnh hưởng bao nhiêu thiết bị? |
| Automation và backup | Credential nào được lưu, lấy và sử dụng? |
| Cổng quản trị nền tảng cloud | Có thể thay thiết bị ảo hoặc đường mạng ngoài luồng thiết bị không? |

Một thiết bị không còn được dùng để đăng nhập tương tác vẫn có thể giữ credential trong công cụ tự động.

Khi thay kiến trúc truy cập, phải đối soát các đường song song. Chỉ bảo vệ một kênh SSH chưa đủ để tuyên bố mọi quản trị đều đi qua PAM.

## 4. Phân loại tác vụ trước khi cấp role

Bắt đầu từ nhu cầu:

> Cần kiểm tra lỗi interface uplink của thiết bị Edge-A và thu bộ trạng thái được duyệt cho yêu cầu INCIDENT-EX-017.

Nhu cầu này khác:

> Cần sửa tập chính sách truy cập cho dịch vụ Orders trong cửa sổ CHANGE-EX-042.

Một ma trận minh họa:

| Nhóm vai trò | Năng lực có thể cấp | Năng lực không được mặc định đi kèm |
|---|---|---|
| Quan sát vận hành | Xem trạng thái và chỉ số cần thiết | Đọc mọi secret hoặc thay cấu hình |
| Vận hành giới hạn | Tác vụ phục hồi đã định nghĩa trong scope | Sửa AAA, tạo admin hoặc đổi audit |
| Quản lý cấu hình | Áp dụng thay đổi đã duyệt | Tự phê duyệt hoặc tự mở rộng role |
| Quản trị truy cập | Quản lý danh tính và role theo quy trình | Tùy ý thay định tuyến hoặc chính sách nghiệp vụ |
| Kiểm toán | Đọc bằng chứng và cấu hình phù hợp | Xóa log hoặc sửa policy |
| Khẩn cấp | Quyền cần cho một sự cố cụ thể | Sử dụng thường ngày hoặc giữ vô thời hạn |

Đây không phải tên role chuẩn của một hãng. Mỗi ô cần ánh xạ thành cấu hình cụ thể trên nền tảng thật.

### Đừng đánh đồng “xem” với không nhạy cảm

Cấu hình hiển thị có thể chứa địa chỉ nội bộ, topology, thông tin xác thực hoặc dữ liệu giúp hiểu ranh giới bảo mật.

Một role chỉ đọc vẫn cần scope và kiểm soát dữ liệu đầu ra. Không cấp quyền xem toàn bộ cấu hình chỉ vì người dùng không được ghi.

### Đừng để tên chức danh thay thế nhu cầu

Một trưởng nhóm không tự cần quyền sửa mọi thiết bị. Một công cụ backup không tự cần quyền tạo tài khoản quản trị.

Cấp theo tác vụ, tài nguyên, môi trường và thời gian giúp tổ chức giải thích được vì sao mỗi đặc quyền tồn tại.

## 5. AAA: xác thực, phân quyền và accounting là ba việc riêng

AAA gồm:

1. Authentication: xác minh chủ thể.
2. Authorization: quyết định hành động hoặc phạm vi được phép.
3. Accounting: ghi nhận hoạt động để đối soát.

TACACS+ được thiết kế tách ba chức năng này; một triển khai không nhất thiết đã sử dụng đầy đủ cả ba. Vì vậy, đăng nhập thành công qua một máy chủ AAA không chứng minh đã có kiểm soát từng lệnh và accounting đầy đủ. [RFC 8907: TACACS+](https://www.rfc-editor.org/rfc/rfc8907.html).

### Kiểm tra từng giai đoạn

| Giai đoạn | Bằng chứng cần có |
|---|---|
| Xác thực | Đúng danh tính, nguồn và trạng thái tài khoản |
| Nhận role | Đúng nhóm hoặc role ánh xạ tới thiết bị |
| Vào ngữ cảnh quyền | Không tự được cấp cấp độ mạnh ngoài nhu cầu |
| Thực hiện tác vụ | Lệnh hoặc operation chịu policy đã cấu hình |
| Ghi nhận | Có sự kiện với thời gian, chủ thể, đích và kết quả phù hợp |
| Kết thúc | Phiên và đường cấp quyền tiếp theo được xử lý |

Cần phân biệt tài khoản con người, tài khoản dịch vụ và danh tính của chính thiết bị khi nó gọi AAA.

Một thiết bị có thể hỗ trợ AAA theo những cách khác nhau ở CLI, web và API. Cần kiểm chứng từng kênh, không suy từ một lần thử đăng nhập SSH sang toàn bộ chức năng quản trị.

### Mapping từ nhóm sang quyền cũng là đặc quyền

Ai sửa được nhóm người dùng, profile AAA hoặc role mapping có thể làm nhiều người nhận thêm quyền.

Quản lý thay đổi cần xem cả:

- Thành viên nhóm.
- Nội dung role.
- Điều kiện kích hoạt.
- Thiết bị hoặc nhóm thiết bị áp dụng.
- Phạm vi accounting.
- Quy tắc fallback.

Chỉ rà soát danh sách tài khoản trên thiết bị có thể bỏ sót nguồn quyền tập trung.

## 6. Bảo vệ luồng từ thiết bị tới AAA

Kết nối SSH từ người dùng tới thiết bị và kết nối từ thiết bị tới máy chủ AAA là hai chặng khác nhau.

TACACS+ gốc sử dụng cơ chế che giấu nội dung không tương đương bảo vệ mật mã hiện đại; RFC 8907 yêu cầu môi trường triển khai bảo vệ đường truyền. Không dựa riêng vào shared secret để kết luận toàn bộ kênh AAA an toàn. [RFC 8907: Security Considerations](https://www.rfc-editor.org/rfc/rfc8907.html#section-10).

RFC 9887 bổ sung TACACS+ qua TLS 1.3. Khả năng dùng phụ thuộc hỗ trợ và cấu hình của client thiết bị cùng server; không mặc định mọi triển khai TACACS+ đã dùng TLS. [RFC 9887: TACACS+ over TLS 1.3](https://www.rfc-editor.org/rfc/rfc9887.html).

### Các điểm cần quản lý

- Nguồn thiết bị nào được gọi AAA.
- Đích AAA nào được thiết bị tin cậy.
- Đường mạng và cơ chế bảo vệ phù hợp.
- Credential hoặc khóa thiết bị dùng để xác thực với AAA.
- Certificate và trust nếu cơ chế sử dụng.
- Chính sách rotation.
- Đồng bộ thời gian và khả năng đối soát.
- Độ sẵn sàng cùng hành vi khi lỗi.

Tên giao thức không thay cho bằng chứng cấu hình. Hãy ghi rõ đang dùng chế độ nào, phiên bản nào và điểm nào thực thi bảo vệ.

## 7. Thiết kế management network và kênh quản trị

Một mạng hoặc vùng quản trị riêng có thể giảm số nguồn tiếp cận endpoint. Tuy nhiên, việc đặt tên VLAN là “management” không tự tạo phân quyền.

Cần xác định:

- Nguồn quản trị được phép.
- Tài nguyên và cổng quản trị được phép tới.
- Vai trò bastion hoặc proxy.
- Tách lưu lượng quản trị khỏi nguồn không tin cậy.
- Đường out-of-band và những phụ thuộc còn chung.
- Chính sách xác thực ngay trên thiết bị.
- Cách quan sát truy cập trực tiếp và truy cập ngoài cổng chuẩn.

### SSH và xác minh thiết bị

SSH cung cấp xác thực máy chủ và bảo vệ kênh; việc client xác minh đúng host key là một phần của thiết kế tin cậy. Không bỏ qua kiểm tra danh tính thiết bị chỉ vì kết nối đi trong mạng nội bộ. [RFC 4253: SSH Transport Layer Protocol](https://www.rfc-editor.org/rfc/rfc4253.html).

Trong vận hành:

- Quản lý định danh thiết bị và host key.
- Đánh giá thay đổi host key hợp lệ khi thay thiết bị hoặc rotate.
- Điều tra mismatch thay vì chấp nhận tự động.
- Bảo vệ cả client–proxy và proxy–thiết bị nếu có hai chặng.
- Chọn cấu hình mật mã theo phiên bản và chính sách đang dùng.

Một bastion có thể ghi phiên, nhưng cần biết nó chỉ chuyển tiếp hay thực sự kiểm soát kênh. Không giả định có transcript đầy đủ của một kênh mã hóa mà nó không quan sát được nội dung.

### Console vật lý và out-of-band

Console là đường khôi phục quan trọng nhưng có thể là đường đi vòng policy thông thường.

Cần quản lý danh tính trên console server, quyền chọn cổng, quyền tại thiết bị, vị trí vật lý và bằng chứng. Một console server dùng chung tài khoản quản trị cho nhiều kỹ sư vẫn tạo vấn đề quy trách nhiệm.

Out-of-band cũng cần được kiểm thử: nếu nó dùng cùng đường mạng, nguồn điện hoặc AAA đang gặp sự cố, mức độc lập có thể không như sơ đồ.

## 8. Quyền theo lệnh và quyền theo operation

### CLI: ngữ cảnh quan trọng hơn chuỗi ký tự

Một quy tắc chỉ dựa vào tiền tố lệnh có thể không mô tả đầy đủ:

- Ngữ cảnh cấu hình hiện tại.
- Tài nguyên hoặc interface được chọn.
- Tham số và tập giá trị.
- Alias hoặc dạng rút gọn.
- Lệnh gọi script, shell hoặc hệ thống tệp.
- Tác động gián tiếp lên credential và audit.
- Việc áp dụng hoặc lưu thay đổi.

Cần kiểm thử trên đúng phiên bản thiết bị. Một rule hợp lệ cho một hệ điều hành mạng không tự dùng được cho hệ điều hành khác.

Không coi việc được vào một “privilege level” là bằng chứng đủ cho JEA. Nếu người dùng vẫn làm được mọi thao tác cấu hình, giới hạn tác vụ chưa được thực thi.

### API: kiểm soát operation và nội dung

NETCONF hoặc RESTCONF có thể cho phép quản lý dữ liệu có cấu trúc. NACM định nghĩa mô hình kiểm soát quyền đối với operation và nội dung cho những giao thức này. Việc áp dụng phụ thuộc triển khai và cấu hình thực tế. [RFC 8341: Network Configuration Access Control Model](https://www.rfc-editor.org/rfc/rfc8341.html).

Một role API nên được đánh giá theo:

- Operation nào được gọi.
- Đối tượng hoặc nhánh dữ liệu nào được đọc, sửa.
- Scope thiết bị và môi trường.
- Hành động thực thi như reboot, reset hoặc kích hoạt thay đổi.
- Quyền sửa chính policy phân quyền.
- Những đường API khác hoặc giao diện khác cấp quyền tương đương.

Không chuyển một role CLI sang API bằng cách chỉ đổi tên role. Hai kênh có thể có mô hình quyền khác nhau.

## 9. JIT cho truy cập con người

Một luồng minh họa:

~~~mermaid
flowchart LR
    A[Yêu cầu gắn với thiết bị và tác vụ] --> B[Kiểm tra danh tính và scope]
    B --> C[Phê duyệt phù hợp]
    C --> D[Kích hoạt role có thời hạn]
    D --> E[Mở phiên qua kênh được duyệt]
    E --> F[Thực hiện và thu bằng chứng]
    F --> G[Hết hạn hoặc thu hồi]
    G --> H[Kiểm chứng phiên và quyền tồn dư]
~~~

Thông tin cấp quyền cần có người, thiết bị hoặc tập thiết bị, role, lý do, mã thay đổi, người duyệt, thời điểm bắt đầu và kết thúc.

### Không để đường thường trực làm vô hiệu ý nghĩa JIT

Nếu kỹ sư vẫn giữ một tài khoản cục bộ quản trị hoặc một key được chấp nhận trực tiếp, việc thêm một role JIT ở cổng không làm quyền hiệu lực trở thành tạm thời.

Cần đối soát:

- Gán quyền AAA.
- Tài khoản cục bộ.
- Key được thiết bị chấp nhận.
- Token API.
- Quyền trên controller.
- Console và bastion khác.
- Credential trong automation.

### Hết hạn tác vụ và trạng thái cấu hình là hai vòng đời

Một thay đổi cấu hình hợp lệ có thể phải tồn tại sau khi quyền quản trị đã kết thúc. Hết lease không tự yêu cầu hoàn tác mọi thay đổi.

Điều cần chứng minh là sau mốc kết thúc, chủ thể không tiếp tục dùng quyền ngoài yêu cầu, và các hiện vật như tài khoản mới hoặc token mới được xử lý theo kế hoạch.

## 10. Credential cục bộ, key và tài khoản khẩn cấp

Credential trên thiết bị có nhiều loại và vòng đời:

- Tài khoản quản trị cục bộ.
- Mật khẩu cho ngữ cảnh đặc quyền nếu nền tảng dùng.
- SSH key hoặc certificate.
- Shared secret với AAA.
- Token API.
- Credential của controller hoặc automation.
- Thông tin xác thực cho cơ chế giám sát.
- Credential để xuất cấu hình, backup hoặc gọi dịch vụ khác.

Phải kiểm kê đúng loại trước khi thiết kế rotation.

### Mỗi credential cần có chủ sở hữu và mục đích

Một mật khẩu cục bộ được dùng trên toàn bộ thiết bị làm tăng phạm vi ảnh hưởng khi bị lộ. Nếu cần credential cục bộ, nên có phạm vi quản lý phù hợp và lưu trong kho có kiểm soát.

Người dùng không nên nhận credential quản trị dài hạn chỉ để hoàn thành một tác vụ ngắn nếu có cơ chế cấp phiên thích hợp.

Nếu thiết bị cũ buộc dùng tài khoản chia sẻ, cần ghi nhận giới hạn và kiểm soát bù như:

- Cấp phát qua PAM.
- Liên kết lượt dùng với cá nhân và mã tác vụ.
- Kiểm soát nguồn kết nối.
- Giám sát phiên trong khả năng thực tế.
- Rotate theo quy trình.
- Đối soát tài khoản, key và token còn tồn tại.

Các biện pháp này không tự làm log trên thiết bị có danh tính cá nhân nếu thiết bị vẫn chỉ thấy cùng một tài khoản.

### Rotation phải bao gồm consumer

Thay shared secret AAA ở một phía mà phía còn lại chưa đổi có thể làm mất xác thực. Thay key automation có thể làm job backup hoặc kiểm tra cấu hình ngừng chạy.

Runbook cần có:

1. Credential và consumer bị ảnh hưởng.
2. Khả năng dùng song song hai phiên bản nếu có.
3. Thứ tự chuyển đổi phù hợp.
4. Kiểm thử xác thực mới và tác vụ hợp lệ.
5. Xử lý phiên hoặc credential cũ.
6. Phương án khôi phục.
7. Bằng chứng không chứa bí mật.

Không coi thay mật khẩu thành công là đã chấm dứt mọi phiên đang hoạt động.

## 11. AAA lỗi và hành vi fallback

Fallback là một phần của mô hình truy cập đặc quyền, không chỉ là lựa chọn giúp tăng độ sẵn sàng.

Cần phân biệt:

| Trạng thái | Ý nghĩa cần hiểu |
|---|---|
| Xác thực bị từ chối | Nguồn xác thực đã trả lời không chấp nhận |
| Không tới được AAA | Chưa xác minh được qua nguồn đó |
| Authorization từ chối | Danh tính có thể hợp lệ nhưng không được làm thao tác |
| Accounting gặp lỗi | Có thể thiếu bằng chứng dù truy cập đang hoạt động |
| Nguồn nhóm hoặc policy lỗi | Có thể không quyết định được scope chính xác |

Những trạng thái này không nên bị gộp thành “thử tài khoản khác cho đến khi vào được”.

Hành vi thực tế phụ thuộc thiết bị, thứ tự nguồn và cấu hình. Phải kiểm thử cả từ chối, timeout và các lỗi liên quan.

### Thiết kế fallback có chủ đích

Một phương án có thể dành tài khoản cục bộ cho console khẩn cấp hoặc nguồn quản trị hạn chế, thay vì cho mọi kết nối từ xa đi vào role mạnh khi AAA không sẵn sàng.

Cần xác định:

- Ai được kích hoạt.
- Nguồn nào được sử dụng.
- Có giới hạn quyền nào còn áp dụng.
- Có yêu cầu phê duyệt hoặc thông báo nào.
- Bằng chứng được giữ ở đâu khi accounting trung tâm lỗi.
- Khi AAA phục hồi, quyền khẩn cấp được kết thúc thế nào.

Không nên coi một lần AAA trả về từ chối là sự cố hạ tầng để tự mở quyền mạnh qua đường khác.

### Tránh phụ thuộc vòng tròn

Thiết bị mạng có thể nằm trên chính đường tới AAA, PAM, DNS, thời gian và nơi lưu log. Thay đổi cấu hình có thể làm tất cả các nguồn quản trị này mất liên lạc.

Đồ thị phụ thuộc nên thể hiện:

~~~text
Nguồn quản trị
  -> Bastion hoặc PAM
  -> Mạng quản trị
  -> Thiết bị

Thiết bị
  -> AAA
  -> Nguồn thời gian
  -> Đích log
  -> Controller hoặc kho cấu hình
~~~

Nếu nhiều mũi tên đi qua cùng một link hoặc firewall đang được thay, kế hoạch cần một đường khôi phục thực sự độc lập hoặc một cửa sổ gián đoạn đã được đánh giá.

## 12. Thay đổi cấu hình an toàn

Quyền cấu hình cần đi cùng một kế hoạch thay đổi có thể kiểm chứng.

### Trước thay đổi

- Xác định thiết bị và phạm vi ảnh hưởng.
- Thu baseline cần thiết.
- Đối chiếu cấu hình hiện tại với yêu cầu.
- Chuẩn bị diff hoặc tập thao tác được duyệt.
- Xác định các phụ thuộc quản trị bị ảnh hưởng.
- Có bản phục hồi và người có quyền sử dụng.
- Kiểm chứng kênh khôi phục.
- Đặt tiêu chí thành công và điều kiện dừng.
- Xác định ai được xác nhận thay đổi cuối cùng.

Không đưa credential nguyên vẹn vào diff hoặc ticket chỉ để mọi người xem đủ cấu hình.

### Trong thay đổi

Thực hiện theo nhóm nhỏ phù hợp và kiểm chứng sau mỗi điểm quan trọng. Đối với thiết bị có cơ chế candidate, validation hoặc commit có xác nhận, cần hiểu đúng khả năng được hỗ trợ.

NETCONF định nghĩa các capability như candidate và confirmed commit. Chúng không phải một bảo đảm mặc định trên mọi server; client phải biết capability và ngữ nghĩa thực tế. [RFC 6241: NETCONF](https://www.rfc-editor.org/rfc/rfc6241.html).

Một kế hoạch khái niệm:

~~~text
Xác định baseline
    -> Chuẩn bị thay đổi đúng scope
    -> Kiểm tra hoặc validate nếu hỗ trợ
    -> Áp dụng theo cơ chế nền tảng
    -> Kiểm tra đường quản trị và chức năng mạng
    -> Xác nhận hoặc xử lý khôi phục
    -> Lưu bằng chứng trạng thái cuối
~~~

Không dựa vào một thao tác “save” có tên quen thuộc để suy rằng mọi hệ điều hành mạng có cùng mô hình cấu hình.

### Sau thay đổi

Cần phân biệt:

- Câu lệnh đã được cho phép.
- Thiết bị đã chấp nhận request.
- Cấu hình đã có hiệu lực.
- Cấu hình có tồn tại sau restart theo thiết kế không.
- Lưu lượng và chức năng nghiệp vụ có đúng không.
- AAA và audit còn hoạt động không.

Một request thành công ở management plane chưa chứng minh data plane đạt kết quả mong muốn.

Nếu có controller reconcile cấu hình, phải xác nhận nguồn mong muốn đã được cập nhật đúng. Một sửa trực tiếp có thể bị controller thay lại hoặc tạo drift cần xử lý.

## 13. Tác vụ có nguy cơ tự khóa đường quản trị

Những thay đổi đáng chú ý gồm:

- Sửa địa chỉ hoặc interface quản trị.
- Sửa route tới nguồn quản trị.
- Sửa ACL hoặc firewall bảo vệ endpoint.
- Sửa AAA, role mapping hoặc credential.
- Thay host key, certificate và trust.
- Thay cấu hình controller.
- Thay cơ chế lưu hoặc áp dụng cấu hình.

### Kiểm chứng truy cập mới trước khi kết thúc change

Trong một cửa sổ thay đổi được kiểm soát, cần thử một kết nối mới bằng danh tính và nguồn đúng với thiết kế.

Một phiên cũ đang mở có thể còn dùng được dù cấu hình đăng nhập mới đã sai. Ngược lại, chỉ giữ một phiên cũ không phải phương án khôi phục đáng tin cậy nếu đường mạng có thể bị cắt.

Kế hoạch phải xác định khi nào kết thúc phiên cũ, ai theo dõi và bằng chứng truy cập mới.

### Không thử trên mọi thành viên đồng thời theo thói quen

Một cặp thiết bị hoặc cụm HA có thể chia sẻ hoặc tự đồng bộ một số cấu hình. Cần hiểu phạm vi đồng bộ trước khi đổi một thành viên.

Nếu cả hai mất cùng một đường AAA hoặc cùng nhận cấu hình quản trị lỗi, việc có hai thiết bị không tạo đường khôi phục độc lập.

Cửa sổ thay đổi phải xét sức khỏe, đường kết nối và khả năng rollback thực tế, không chỉ số lượng thiết bị.

## 14. Quyền của automation và hệ thống giám sát

### Danh tính máy khác danh tính con người

Job lấy backup hoặc kiểm tra trạng thái cần danh tính riêng, không dùng tài khoản của kỹ sư đã rời đội.

Mỗi automation cần:

- Chủ sở hữu.
- Tác vụ và tài nguyên đích.
- Permission tối thiểu.
- Nguồn chạy được tin cậy.
- Kho credential hoặc cơ chế cấp phù hợp.
- Rotation và thu hồi.
- Mã job để liên kết bằng chứng.
- Kiểm soát ai sửa mã và danh sách thiết bị.

Một người sửa pipeline có thể làm automation chạy lệnh khác dưới danh tính máy. Vì vậy, quyền sửa mã automation là một phần đường đặc quyền.

### Giám sát có thể có quyền nhạy cảm

Cần phân biệt đọc telemetry, lấy toàn bộ cấu hình và ghi cấu hình.

Với SNMPv3 USM, cơ chế xác thực và riêng tư là các thành phần cần được cấu hình theo mục tiêu. Chỉ thấy nhãn “SNMPv3” chưa chứng minh đang dùng mức bảo vệ và quyền đọc/ghi phù hợp. [RFC 3414: SNMPv3 USM](https://www.rfc-editor.org/rfc/rfc3414.html).

Không sao chép lựa chọn thuật toán cũ từ ví dụ giao thức rồi coi là chính sách mật mã hiện tại. Cấu hình phải phù hợp phiên bản, khả năng hỗ trợ và yêu cầu của môi trường.

### Backup cấu hình cũng là dữ liệu cần bảo vệ

Backup có thể chứa:

- Tài khoản và cấu hình xác thực.
- Shared secret hoặc dữ liệu liên quan.
- Địa chỉ, topology và chính sách mạng.
- Certificate, key hoặc tham chiếu bí mật.
- Thông tin giúp khôi phục quyền cũ.

Cần quản lý quyền đọc, mã hóa phù hợp, vòng đời và khả năng khôi phục. Bản backup trước khi thu hồi một admin có thể chứa cấu hình khôi phục lại quyền đó nếu được áp dụng thiếu đối soát.

## 15. Accounting, ghi phiên và bằng chứng cấu hình

Ba loại bằng chứng bổ sung cho nhau:

| Loại | Có thể hỗ trợ chứng minh | Giới hạn cần ghi nhận |
|---|---|---|
| AAA accounting | Danh tính, phiên hoặc lệnh theo dữ liệu thiết bị gửi | Không tự chứng minh mọi tác động và trạng thái cuối |
| Ghi phiên ở PAM | Tương tác đi qua điểm quan sát | Không bao phủ đường khác hoặc nội dung không nhìn thấy |
| Snapshot và diff cấu hình | Cấu hình trước, sau và phần thay đổi | Chưa chứng minh ai thực hiện nếu thiếu liên kết |
| Telemetry và kiểm tra chức năng | Hệ thống đang hoạt động thế nào | Không tự thay lịch sử quản trị |
| Log controller hoặc API | Job và request được điều phối | Có thể cần đối chiếu trạng thái thực tế từng thiết bị |

Cần nối chúng bằng mã yêu cầu, thời gian, thiết bị, danh tính và định danh phiên hoặc job.

### Không suy kết quả chỉ từ authorization

Một lệnh được AAA cho phép vẫn có thể bị thiết bị từ chối do trạng thái, lỗi cú pháp hoặc điều kiện khác.

Một lệnh được thực hiện có thể chưa làm cấu hình tồn tại sau restart, tùy mô hình nền tảng.

Vì vậy, trạng thái audit nên phân biệt cho phép, gửi, thực thi, xác minh và lưu trạng thái cần thiết.

### Bảo vệ log khỏi chính người được giám sát

Người quản trị thiết bị có thể có đường sửa log cục bộ hoặc cấu hình xuất log nếu role quá rộng.

Cần một đích lưu được bảo vệ phù hợp và phân tách quyền quản trị bằng chứng. Đồng thời, phải quản lý khả năng:

- Tắt accounting.
- Đổi đích log.
- Thay nguồn thời gian.
- Xóa hoặc thay bản backup.
- Sửa cấu hình PAM.
- Đổi khóa hoặc trust bảo vệ đường thu thập.

Một recording có mật khẩu hoặc key trong nội dung lại trở thành nơi chứa bí mật. Cần che, giảm dữ liệu hoặc kiểm soát quyền xem theo mục đích, không ghi mọi thứ rồi coi là mặc nhiên tốt hơn.

### Thời gian phải đối soát được

Nếu đồng hồ thiết bị, AAA và PAM lệch đáng kể, việc nối sự kiện có thể sai.

Cần ghi nguồn thời gian, cách phát hiện lệch và phương pháp đối soát. Không tự quy một lệnh cho người chỉ vì nó xuất hiện gần một lần đăng nhập mà thiếu mapping đủ chắc chắn.

## 16. Thu hồi quyền và xử lý phiên đang mở

Thu hồi network admin cần xử lý nhiều đường:

1. Quyền tại nguồn danh tính và nhóm.
2. Mapping AAA hoặc role.
3. Tài khoản cục bộ.
4. SSH key hoặc certificate được chấp nhận.
5. Token API.
6. Quyền trên controller và automation.
7. Lease tại PAM.
8. Phiên đang mở trên thiết bị.
9. Hiện vật hoặc credential được tạo trong phiên trước.

Không mặc định việc bỏ người khỏi nhóm đã kết thúc mọi phiên hoặc chặn mọi lệnh tiếp theo. Hành vi phụ thuộc thiết bị và điểm kiểm tra authorization.

### Cần thử cả truy cập mới và phiên cũ

Trong phạm vi được phép:

- Kết nối mới bằng đường chuẩn phải bị xử lý đúng.
- Đường cục bộ hoặc trực tiếp không giữ quyền ngoài ý định.
- Phiên cũ không tiếp tục thao tác ngoài chính sách kết thúc.
- Token hoặc key khác của cùng chủ thể được đối soát.
- Quyền nghiệp vụ hoặc quan sát còn hợp lệ không bị ảnh hưởng ngoài nhu cầu.

Một lỗi mạng không phải bằng chứng đã thu hồi permission. Cần phản hồi của cơ chế xác thực hoặc phân quyền và trạng thái thực tế.

### Thay đổi có hiệu lực lâu hơn phiên

Trong khoảng quyền tạm thời, người dùng có thể tạo một tài khoản khác, thêm key, đổi AAA hoặc mở policy mạng nếu được phép.

Hết lease không tự xóa các thay đổi này. Phải đối soát hiện vật theo tác vụ và điều tra khi có dấu hiệu vượt phạm vi.

Nếu mục tiêu là loại bỏ một thay đổi trái phép, cần một change khôi phục hoặc xử lý bù riêng với đánh giá tác động. Không tùy ý hoàn tác mọi cấu hình trong phiên nếu có thay đổi hợp lệ cần giữ.

## 17. Break-glass và khôi phục khi AAA không sẵn sàng

Một thiết kế chỉ hoạt động khi mọi hệ thống đều khỏe chưa đủ cho quản trị mạng.

Đường khẩn cấp cần:

- Điều kiện sử dụng rõ ràng.
- Người hoặc nhóm có thẩm quyền.
- Credential được bảo vệ.
- Nguồn kết nối và thiết bị trong scope.
- Giới hạn thời gian.
- Bằng chứng hoặc phương án ghi nhận khi hệ thống trung tâm lỗi.
- Rà soát sau sử dụng.
- Rotation hoặc thu hồi credential theo kế hoạch.

### Kiểm thử khả năng khôi phục

Cần kiểm chứng trong lab hoặc cửa sổ được phép:

- Console server có truy cập được khi link quản trị chính mất không?
- Tài khoản khẩn cấp có đúng role và không bị chính policy mới khóa không?
- Người chịu trách nhiệm lấy credential bằng cách nào?
- Có đủ quyền sửa phần cấu hình gây mất truy cập không?
- Sau khôi phục, quyền khẩn cấp được kết thúc thế nào?
- Có khôi phục nhầm credential hoặc role đã bị thu hồi từ backup không?

Một tài khoản khẩn cấp không được dùng trong thời gian dài nhưng chưa từng thử có thể không hữu dụng lúc cần.

Ngược lại, dùng tài khoản khẩn cấp hàng ngày làm yếu JIT và quy trách nhiệm. Cần phát hiện và xử lý việc sử dụng ngoài mục đích.

## 18. Hồ sơ cấp quyền minh họa

Mẫu sau mô tả quản trị, không phải cú pháp cấu hình thiết bị hoặc AAA cụ thể:

~~~yaml
network_admin_access:
  request_reference: INCIDENT-EX-017
  user_reference: "<danh tính cá nhân đã xác minh>"
  accountable_owner: network-operations

  target:
    device_reference: edge-a-training
    site_reference: lab-site-a
    environment: training
    management_endpoint_reference: "<đích đã đăng ký>"

  task:
    purpose: inspect-uplink-health
    role_reference: network-observer
    permitted_scope_reference: "<tập trạng thái được duyệt>"
    configuration_write_required: false

  access:
    authentication_source_reference: "<nguồn danh tính>"
    aaa_policy_revision: "<revision hiệu lực>"
    approved_channel_reference: "<kênh quản trị>"
    approval_reference: APPROVAL-EX-017
    activation_start: "<thời điểm có múi giờ>"
    activation_end: "<thời điểm có múi giờ>"

  credential:
    mechanism_reference: "<cơ chế thực tế>"
    vault_reference: "<tham chiếu nếu cần>"
    disclosure_to_user: "<chính sách thực tế>"

  evidence:
    aaa_record_reference: EVID-AAA-EX-017
    pam_session_reference: EVID-PAM-EX-017
    device_result_reference: EVID-DEVICE-EX-017
    raw_secret_logging: forbidden

  closure:
    new_access_verification_required: true
    existing_session_handling_reference: CLOSE-EX-017
    residual_access_review_required: true
~~~

Mọi trường phải được ánh xạ thành cấu hình hoặc quy trình có bằng chứng.

Ví dụ, configuration_write_required: false không tự ngăn sửa cấu hình nếu role trên thiết bị vẫn là quản trị toàn phần. Khi phát hiện mâu thuẫn, phải xử lý quyền thực tế thay vì chỉ sửa hồ sơ cho đẹp.

## 19. Tình huống thực tế: đổi AAA và mất đường đăng nhập

### Bối cảnh

Đội mạng chuyển Edge-A sang profile AAA mới. Họ đổi role mapping và đường tới AAA trong cùng một cửa sổ.

Phiên SSH đang mở vẫn hoạt động, nên người thực hiện kết luận thành công. Sau khi đóng phiên, một kết nối mới không đăng nhập được. Console server cũng phụ thuộc cùng đường vừa thay.

### Những vấn đề trong kế hoạch

- Dùng phiên cũ làm bằng chứng cho xác thực mới.
- Gộp nhiều thay đổi có phụ thuộc mà chưa tách điểm kiểm tra.
- Chưa xác nhận đường out-of-band độc lập.
- Chưa có bằng chứng đủ về role được cấp sau mapping mới.
- Chưa kiểm thử các trạng thái AAA từ chối và không tới được.

### Thiết kế phù hợp hơn

Trước change, đội kiểm kê đường quản trị và chuẩn bị phương án khôi phục đã thử. Họ tách phần thay đổi theo rủi ro và xác định kiểm tra sau từng bước.

Sau khi áp dụng mapping, một danh tính đúng scope mở kết nối mới. Đội kiểm tra tác vụ được phép và thao tác phải bị từ chối. Họ cũng đối chiếu accounting và trạng thái cấu hình.

Chỉ khi có bằng chứng truy cập mới và kết quả đúng, đội mới kết thúc phiên phục vụ change theo kế hoạch.

Nếu một kiểm tra thất bại, đội dừng chuyển bước, xác định nguyên nhân và dùng phương án đã đánh giá. Không mở quyền quản trị cho mọi người chỉ để nhanh chóng khôi phục màn hình đăng nhập.

### Điều kiện đóng change

- Nguồn quản trị hợp lệ truy cập được.
- Role đúng tác vụ, không rộng hơn ngoài ý định.
- Các thao tác ngoài scope bị từ chối.
- AAA và audit hoạt động đúng.
- Đường khôi phục vẫn có thể dùng.
- Cấu hình hiệu lực và trạng thái lưu được xác minh.
- Các quyền tạm, key hoặc tài khoản tạo trong change được đối soát.

## 20. Ma trận kiểm thử

| Ca kiểm thử | Kết quả mong đợi |
|---|---|
| Người không thuộc tập được cấp quyền | Không mở được đặc quyền ngoài ý định |
| Người đủ điều kiện nhưng chưa kích hoạt | Chưa thực hiện được tác vụ yêu cầu JIT |
| Role quan sát xem đúng trạng thái | Thành công |
| Role quan sát sửa cấu hình | Bị từ chối |
| Role vận hành giới hạn sửa AAA | Bị từ chối nếu ngoài tác vụ |
| Đổi sang thiết bị khác sau phê duyệt | Đánh giá lại hoặc từ chối |
| Truy cập qua web hoặc API | Cùng chịu hợp đồng quyền phù hợp từng kênh |
| AAA trả về từ chối | Không tự biến thành quyền mạnh qua fallback ngoài chính sách |
| AAA không sẵn sàng | Hành vi đúng phương án đã thiết kế |
| Accounting lỗi | Có tín hiệu và cách xử lý theo chính sách |
| Kết nối mới sau đổi AAA | Xác thực và role đúng |
| Host key thay ngoài kế hoạch | Không bị chấp nhận tự động |
| Hết hạn khi phiên còn mở | Xử lý quyền và phiên đúng tiêu chí |
| Thu hồi key hoặc token | Đường cấp mới và phiên cũ được kiểm tra riêng |
| Automation đổi credential | Job dùng được bản mới và giữ scope |
| Thay đổi qua controller | Trạng thái mong muốn và thiết bị được đối chiếu |
| Khôi phục từ backup | Không tái tạo quyền đã thu hồi ngoài ý định |
| Dùng break-glass | Có bằng chứng, thời hạn và đối soát sau sự kiện |

Thực hiện trong môi trường và phạm vi được phép. Các ca kiểm thử từ chối nên dùng thao tác ít tác động; không cần cắt link production để chứng minh role bị giới hạn.

Kết quả cần ghi nguồn bằng chứng và giới hạn kết luận. “Không kết nối được” do lỗi mạng không tương đương “IAM đã chặn đúng”.

## 21. Những lỗi thường gặp

### Dùng một tài khoản admin cho cả đội

Làm yếu quy trách nhiệm, khó thu hồi một cá nhân và tăng phạm vi tác động khi credential bị lộ.

### Chỉ kiểm soát VPN hoặc bastion

Thiết bị vẫn có thể cấp role rộng hoặc có đường web, API, console khác.

### Bật AAA nhưng bỏ authorization hoặc accounting

Đăng nhập tập trung chưa chứng minh thao tác được giới hạn và có đủ bằng chứng.

### Tin tên role hoặc cấp độ quyền

Cần kiểm tra các tác vụ thực tế, ngữ cảnh, tham số và các đường nâng quyền.

### Coi lệnh xem cấu hình luôn ít rủi ro

Thông tin đầu ra có thể chứa dữ liệu nhạy cảm hoặc credential.

### Coi mọi TACACS+ đều được bảo vệ cùng mức

Phải biết chế độ, đường truyền và khả năng triển khai thực tế của client–server.

### Cho phép fallback mạnh sau mọi lỗi

Có thể làm một quyết định từ chối ở nguồn tập trung mất tác dụng.

### Thay cấu hình mà chưa có đường khôi phục

Có thể cắt chính đường tới AAA, PAM và console đang được dùng.

### Kiểm tra bằng phiên cũ rồi đóng change

Phiên cũ không chứng minh cấu hình xác thực mới hoạt động.

### Chỉ nhìn cấu hình, không kiểm tra chức năng

Request được chấp nhận chưa chứng minh trạng thái điều khiển và lưu lượng đúng.

### Thu hồi nhóm nhưng quên key và controller

Những đường quyền khác có thể tiếp tục giữ khả năng quản trị.

### Giữ credential trong backup không được bảo vệ

Backup cấu hình có thể thành nguồn lộ bí mật hoặc khôi phục quyền cũ.

## 22. Bài thực hành

Thiết kế quản trị cho một môi trường lab có router Edge-A, switch Access-A và controller quản lý chúng.

Nhu cầu:

- Đội hỗ trợ chỉ xem trạng thái cần thiết.
- Đội vận hành được làm một số tác vụ phục hồi đã định nghĩa.
- Đổi cấu hình cần yêu cầu và phê duyệt.
- Quản lý AAA là đặc quyền riêng.
- Automation backup có danh tính riêng.
- Có đường khẩn cấp khi AAA không sẵn sàng.
- Có thể thu hồi một kỹ sư mà không làm mất quản trị hợp lệ của cả đội.

Sản phẩm cần tạo:

1. Inventory thiết bị và các đường quản trị.
2. Đồ thị phụ thuộc AAA, PAM, thời gian, log và out-of-band.
3. Ma trận role theo tác vụ, tài nguyên và kênh.
4. Luồng JIT cho một change.
5. Chính sách fallback phân biệt từ chối với không sẵn sàng.
6. Kế hoạch credential và rotation cho người, thiết bị, automation.
7. Kế hoạch thay đổi có kiểm tra kết nối mới.
8. Chuỗi bằng chứng AAA, PAM và trạng thái thiết bị.
9. Ma trận kiểm thử gồm ca từ chối và sau thu hồi.
10. Phương án break-glass cùng bước đối soát sau sử dụng.

Nếu thiết bị lab không hỗ trợ một giới hạn, ghi rõ khoảng trống và biện pháp bù. Không tuyên bố quyền theo lệnh đã có chỉ vì hồ sơ mô tả một tập thao tác mong muốn.

## 23. Câu hỏi tự kiểm tra

**Vì sao network device admin cần PAM dù đã có mạng quản trị riêng?**

Vì đường mạng chỉ là một phần kiểm soát. Danh tính, role, credential, phiên và thay đổi trên thiết bị vẫn cần được quản lý.

**Đăng nhập AAA thành công chứng minh đủ cả ba chức năng chưa?**

Chưa. Phải kiểm tra riêng xác thực, authorization và accounting đã được dùng như thế nào.

**Tại sao quyền sửa role mapping cũng là đặc quyền?**

Vì nó có thể làm nhiều principal nhận quyền mạnh hơn mà không tạo tài khoản mới trên thiết bị.

**Một phiên SSH cũ còn hoạt động có chứng minh change AAA đúng không?**

Không. Cần một kết nối mới và kiểm tra role cùng tác vụ được phép.

**Fallback nên phân biệt những trạng thái nào?**

Tối thiểu phải hiểu nguồn trả về từ chối, nguồn không sẵn sàng và các lỗi ở authorization hoặc accounting, rồi áp dụng chính sách phù hợp.

**Tại sao hết lease không tự hoàn tác cấu hình?**

Vòng đời quyền quản trị và vòng đời thay đổi là hai việc khác nhau. Thay đổi hợp lệ có thể cần tiếp tục tồn tại.

**Backup cấu hình có liên quan đến thu hồi quyền không?**

Có. Nó có thể chứa credential hoặc cấu hình gán quyền cũ; khôi phục thiếu đối soát có thể đưa quyền đó trở lại.

**Điều gì chứng minh job quản trị đã kết thúc?**

Có bằng chứng về kết quả tác vụ, trạng thái cuối, quyền tạm, phiên đang mở và truy cập tồn dư trong phạm vi đã xác định.
