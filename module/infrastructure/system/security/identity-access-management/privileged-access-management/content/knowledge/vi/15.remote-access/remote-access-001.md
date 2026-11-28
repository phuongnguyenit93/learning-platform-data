# Remote admin access trong kiến trúc PAM

## 1. Remote admin access là gì?

**Remote admin access** là việc một chủ thể thực hiện công việc quản trị trên tài nguyên từ một môi trường khác với nơi tài nguyên được vận hành trực tiếp. Đường truy cập có thể đi qua Internet, mạng đối tác, mạng nội bộ, vùng quản trị hoặc một nền tảng trung gian.

Trong quản lý truy cập đặc quyền (Privileged Access Management — PAM), trọng tâm là kiểm soát toàn bộ chuỗi:

~~~text
Danh tính người yêu cầu
  → điều kiện của môi trường truy cập
  → quyền và thời gian được phép
  → đường kết nối
  → tài khoản và credential tại đích
  → hành động trong phiên
  → kết thúc, thu hồi và bằng chứng.
~~~

Đối tượng có thể là máy chủ, cơ sở dữ liệu, thiết bị mạng, nền tảng điều khiển, giao diện quản trị hoặc hạ tầng nhạy cảm khác.

Ví dụ, một kỹ sư cần chẩn đoán firewall production từ bên ngoài mạng quản trị. Có đường tới firewall mới chỉ giải quyết kết nối. Hệ thống còn phải xác định kỹ sư là ai, được làm gì, dùng tài khoản nào, trong bao lâu và ai có thể kiểm tra hoạt động.

Mục tiêu của bài học là thiết kế truy cập quản trị từ xa có phạm vi rõ, giảm quyền và phơi lộ credential, quản lý phiên và tạo bằng chứng phù hợp. Các mô hình minh họa không phải cấu hình của một sản phẩm cụ thể.

## 2. Những lớp kiểm soát phải được tách rõ

| Lớp | Câu hỏi | Ví dụ trách nhiệm |
|---|---|---|
| Kết nối | Chủ thể hoặc gateway có tới được endpoint không? | Định tuyến, firewall, cổng và đường mạng |
| Xác thực | Chủ thể là ai? | Danh tính, MFA hoặc cơ chế xác thực workload |
| Ủy quyền | Chủ thể được làm gì? | Role, target, action, thời hạn và điều kiện |
| Credential | Dùng bằng chứng nào tại đích? | Vault, broker, danh tính liên kết hoặc credential tạm |
| Phiên | Tương tác được quản lý thế nào? | Gateway, timeout, resume và kết thúc |
| Năng lực tại đích | Hành động nào thực sự được cho phép? | Quyền hệ điều hành, database, thiết bị hoặc API |
| Giám sát | Điều gì được quan sát và lưu? | Sự kiện, recording và log đích |
| Thu hồi | Làm thế nào ngừng quyền hoặc hoạt động? | Chặn cấp mới, gỡ grant, xử lý credential và phiên |

Các lớp có thể nằm trong cùng một nền tảng, nhưng kết quả của chúng không tương đương.

Một người đã xác thực qua MFA chưa mặc nhiên được quản trị mọi máy chủ. Một đường VPN không tự tạo quyền phù hợp tại đích. Một recording cũng không tự ngăn hành động ngoài phạm vi.

Cần chỉ ra thành phần nào quyết định, thành phần nào thực thi và bằng chứng nào xác nhận từng kết quả.

## 3. Kiểm kê chủ thể, tài nguyên và đường quản trị

### 3.1. Chủ thể cần được định danh riêng

Có thể gồm:

- Quản trị viên nội bộ.
- Kỹ sư hỗ trợ theo ca.
- Nhà cung cấp hoặc đối tác.
- Tài khoản khẩn cấp.
- Workload tự động hóa thực hiện tác vụ quản trị.

Danh tính con người cần được gắn với người chịu trách nhiệm. Không nên dùng một tài khoản chung mang tên đội hoặc nhà cung cấp làm nguồn duy nhất cho quy trách nhiệm.

Workload có vòng đời và cơ chế xác thực khác con người. Không mặc định dùng cùng một luồng đăng nhập tương tác cho cả hai.

### 3.2. Tài nguyên cần có định danh và owner

Hồ sơ tối thiểu có thể gồm:

| Nhóm | Nội dung |
|---|---|
| Định danh | Target ID, loại tài nguyên và phạm vi nền tảng |
| Môi trường | Production, thử nghiệm, dự phòng |
| Owner | Đội kỹ thuật và dịch vụ chịu ảnh hưởng |
| Endpoint | Điểm quản trị, giao thức và đường phân giải |
| Tài khoản | Danh tính và nguồn xác thực tại đích |
| Quyền | Role và hành động cần cho công việc |
| Đường truy cập | Gateway, proxy, VPN, console hoặc API |
| Bằng chứng | Nguồn log, recording và giới hạn quan sát |
| Phục hồi | Đường khẩn cấp cùng phụ thuộc liên quan |

Một tên DNS có thể trỏ tới cụm hoặc đổi sang tài nguyên khác. Cần hiểu target logic, node và cơ chế xác minh máy chủ thay vì chỉ dựa vào tên hiển thị.

### 3.3. Không bỏ sót đường thay thế

Các đường thường cần kiểm kê gồm SSH, giao diện đồ họa từ xa, web quản trị, API, console, controller tập trung và kênh ngoài băng.

Nếu một đường qua PAM nhưng đường khác vẫn nhận credential quản trị rộng không được quản lý, phạm vi kiểm soát chỉ bao phủ một phần truy cập.

Đường ngoài phạm vi cần owner, biện pháp và kế hoạch hoặc ngoại lệ rõ ràng. Không tuyên bố đã kiểm soát toàn bộ chỉ từ một giao thức đã tích hợp.

## 4. Kiến trúc tham chiếu cho truy cập qua PAM

~~~mermaid
flowchart LR
    U["Quản trị viên"] --> C["Môi trường truy cập"]
    C --> E["Điểm vào được kiểm soát"]
    I["Nguồn danh tính và xác thực"] --> P["PAM: policy và quyết định"]
    E -->|Yêu cầu có danh tính và ngữ cảnh| P
    A["Phê duyệt nếu policy yêu cầu"] --> P
    P -->|Phiên và phạm vi được phép| G["Gateway hoặc proxy quản trị"]
    V["Vault hoặc broker"] -->|Credential theo quyền| G
    G -->|Kênh quản trị đã xác minh đích| T["Tài nguyên đích"]
    N["Kiểm soát mạng quản trị"] --> G
    N --> T
    P --> L["Audit và giám sát"]
    G --> L
    T --> L
~~~

Sơ đồ là mô hình logic. Thành phần thật có thể được triển khai theo nhiều cách, và không phải mọi sản phẩm đều có đầy đủ khả năng được mô tả.

### 4.1. Control plane và đường phiên

Control plane quản lý danh tính, policy, yêu cầu và quyết định. Đường phiên vận chuyển tương tác tới đích.

Nếu control plane không hoạt động, ảnh hưởng tới phiên đang mở phụ thuộc kiến trúc. Không mặc định mọi phiên đều dừng hoặc đều được phép tiếp tục không giới hạn.

Cần thiết kế cách xử lý quyết định đã có, độ mới của dữ liệu và thu hồi trong khoảng mất kết nối.

### 4.2. Gateway cũng là một thành phần đặc quyền

Gateway có thể tiếp cận nhiều tài nguyên và dùng credential thay người dùng. Nếu bị xâm phạm, nó có thể trở thành điểm ảnh hưởng rộng.

Cần giới hạn mạng tới đích, quyền dùng secret, quyền quản trị gateway, plugin và danh tính dịch vụ. Không coi thành phần này an toàn chỉ vì nằm trong vùng quản trị.

### 4.3. Connector khởi tạo kết nối ra ngoài có đánh đổi riêng

Một mô hình có thể dùng connector thiết lập kênh tới dịch vụ điều phối để giảm nhu cầu mở kết nối vào mạng đích.

Điều đó không tự loại bỏ rủi ro. Cần bảo vệ danh tính connector, kênh điều khiển, phạm vi tài nguyên được tiếp cận, quyền cập nhật và cơ chế thu hồi.

Hướng mở kết nối là một đặc tính kiến trúc, không phải bằng chứng đủ về quyền hoặc giám sát.

## 5. Điểm vào và xác minh đích

### 5.1. Điểm vào phải được quản trị

Cần xác định ai được tới điểm vào, bằng giao thức nào và từ môi trường nào.

Không để việc biết một địa chỉ trở thành điều kiện đủ để mở phiên quản trị. Cũng không dựa chỉ vào vị trí mạng như một bằng chứng danh tính.

Các giới hạn kết nối cần đi cùng xác thực và policy của chủ thể.

### 5.2. Phân giải tài nguyên từ danh mục được quản lý

Client có thể chọn target hoặc action trong phạm vi cho phép. Gateway cần phân giải chúng theo dữ liệu được quản trị.

Nếu client được gửi tùy ý hostname, cổng hoặc endpoint mà gateway sẽ kết nối bằng quyền rộng, có thể phát sinh truy cập ngoài phạm vi hoặc gửi credential sai đích.

Cần kiểm soát cả target, giao thức và các đường phụ được hỗ trợ. Một menu chỉ hiển thị tài nguyên được duyệt chưa đủ nếu API bên dưới vẫn nhận mọi địa chỉ.

### 5.3. Xác minh danh tính máy chủ

Kênh quản trị cần cơ chế bảo mật phù hợp và xác minh đúng máy chủ, như trust của host key hoặc chứng thư theo giao thức.

Nếu đích thay khóa hoặc chứng thư, phải có cách xác minh và cập nhật hợp lệ. Không bỏ kiểm tra trust chỉ để phiên mở được.

Kết nối mã hóa tới sai máy chủ vẫn không đáp ứng mục tiêu bảo vệ credential và tài nguyên.

### 5.4. Lỗi kết nối cần được phân loại

Không tới được endpoint, trust thất bại, xác thực lỗi và thiếu quyền là các lớp khác nhau.

Không reset credential hoặc mở thêm quyền chỉ từ một thông báo chung chưa được hiểu. Runbook phải giữ được nguồn lỗi và phần trạng thái chưa xác minh.

## 6. Danh tính, MFA và môi trường truy cập

### 6.1. Tách người yêu cầu và tài khoản tại đích

Một người có thể xác thực bằng danh tính cá nhân tại PAM nhưng gateway dùng tài khoản kỹ thuật ở đích.

Cần giữ liên kết giữa:

~~~text
Người yêu cầu
  → quyết định và phạm vi
  → phiên gateway
  → tài khoản hiệu lực tại đích
  → hoạt động quan sát được.
~~~

Không dùng địa chỉ IP của gateway làm bằng chứng duy nhất về người đã thực hiện công việc.

### 6.2. Xác thực theo mức yêu cầu

Policy có thể yêu cầu MFA hoặc step-up cho hành động nhạy cảm. Cần kiểm tra bằng chứng đến từ nguồn tin cậy và còn phù hợp tại thời điểm cấp phiên.

MFA giúp giảm một số rủi ro chiếm danh tính, nhưng không tự bảo vệ phiên đã bị lấy hoặc một client đã bị kiểm soát. Sau xác thực vẫn cần giới hạn quyền, phiên và môi trường sử dụng.

Không tự bỏ yếu tố bắt buộc để tương thích một client mà chưa thay thiết kế theo thẩm quyền.

### 6.3. Tín hiệu thiết bị là đầu vào có giới hạn

Có thể dùng trạng thái môi trường truy cập theo khả năng nền tảng: danh tính thiết bị, mức quản lý hoặc tín hiệu kiểm soát phù hợp.

Cần biết nguồn, độ mới và hành vi khi không xác minh được. Một trường do client tự khai báo không có giá trị tương đương dữ liệu đã được kiểm chứng.

Truy cập qua trình duyệt không làm môi trường đầu cuối tự an toàn. Dữ liệu hiển thị, input và phiên vẫn có thể chịu ảnh hưởng từ client.

### 6.4. Vòng đời danh tính

Tài khoản bị ngừng hiệu lực, người đổi vai trò hoặc hợp đồng đối tác kết thúc cần dẫn tới cập nhật quyền mới và xử lý phiên theo policy.

Không coi một lần đăng nhập thành công trước đó là thẩm quyền tiếp tục mọi phiên vô thời hạn.

## 7. Ủy quyền theo tài nguyên, hành động và thời gian

Một quyết định đủ rõ nên trả lời:

~~~text
Ai
  → từ ngữ cảnh nào
  → được truy cập target nào
  → bằng giao thức hoặc hình thức nào
  → dùng role nào
  → thực hiện nhóm hành động nào
  → trong khoảng nào
  → với điều kiện và bằng chứng gì?
~~~

### 7.1. Tách quyền yêu cầu, phê duyệt và quản trị policy

Người có thể yêu cầu phiên không nhất thiết được tự duyệt. Người vận hành gateway không mặc nhiên cần quyền sử dụng mọi credential.

Quyền sửa target scope, mở secret export hoặc bỏ giới hạn phiên có thể tạo quyền gián tiếp lớn. Các hành động đó cần được quản lý như thay đổi có ảnh hưởng đặc quyền.

### 7.2. Least privilege tại đích

Role ở PAM mang tên “diagnostic” chưa đủ nếu tài khoản ở đích vẫn có toàn quyền.

Cần kiểm tra quyền hiệu lực, kế thừa, khả năng tạo tài khoản hoặc sửa policy và những đường hành động khác. Hạn chế kết nối chỉ tới một host chưa tự hạn chế việc dùng host đó để tiếp cận tài nguyên khác.

### 7.3. JIT và JEA

JIT có thể giới hạn cửa sổ mở phiên, credential hoặc grant theo cơ chế hỗ trợ. Chỉ cho hiển thị mật khẩu trong vài phút chưa chứng minh tài khoản nền đã mất quyền ngoài khoảng đó.

JEA cần giới hạn năng lực cho tác vụ tại role, endpoint, gateway hoặc lớp thực thi phù hợp. Recording hỗ trợ quan sát, không thay thế toàn bộ việc ngăn hành động ngoài phạm vi.

### 7.4. Phê duyệt có phạm vi và độ mới

Ticket hoặc lý do công việc tạo bối cảnh nhưng không tự là thẩm quyền.

Quyết định cần ràng buộc với chủ thể, target, action, thời gian và các điều kiện quan trọng. Trước khi mở phiên hoặc gia hạn, kiểm tra những điều kiện mà policy yêu cầu còn hiệu lực.

Không dùng quyết định cũ cho một target hoặc hình thức cấp rộng hơn sau khi request đã đổi.

## 8. VPN, truy cập theo ứng dụng, jump host và gateway

### 8.1. Các thành phần có thể phối hợp

| Thành phần hoặc mô hình | Vai trò có thể có | Giới hạn phải xem xét |
|---|---|---|
| VPN | Tạo kết nối vào phạm vi mạng được cho phép | Không tự giới hạn quyền quản trị của tài khoản |
| Truy cập theo ứng dụng hoặc dịch vụ | Giới hạn đường tới tài nguyên theo policy | Không tự thay toàn bộ kiểm soát tại đích |
| Jump host | Là điểm trung gian thực hiện công việc | Có thể trở thành nơi tập trung credential và đặc quyền |
| Session gateway | Trung gian giao thức, phiên và có thể recording | Khả năng quan sát phụ thuộc giao thức và triển khai |
| Console hoặc ngoài băng | Phục hồi khi đường chính không dùng được | Vẫn là đường đặc quyền cần quản trị |
| API quản trị | Thực hiện tác vụ qua giao diện dịch vụ | Token, scope và audit có vòng đời riêng |

Các thành phần không nhất thiết loại trừ nhau. Ví dụ, một gateway có thể được tiếp cận qua một điểm vào theo ứng dụng hoặc một phạm vi VPN hẹp.

Không nên dùng tên kiến trúc làm bằng chứng rằng mọi truy cập đều có least privilege.

### 8.2. Giới hạn mạng theo mục tiêu

Cần xác định nguồn nào được tới endpoint quản trị nào và bằng giao thức nào. Hạn chế này nên phản ánh danh mục tài nguyên được quản lý.

Nếu chỉ cho người dùng kết nối gateway nhưng gateway có quyền tới mọi nơi, cần tiếp tục kiểm soát phạm vi target, credential và quyền vận hành gateway.

Nếu tài khoản tại một target có thể mở đường tới hệ thống khác, cần đánh giá cả quyền tại đích và các ranh giới mạng liên quan. Kiểm soát độc lập ngoài một target có đặc quyền rộng có thể cần thiết để giới hạn ảnh hưởng khi target đó bị kiểm soát.

### 8.3. Jump host cần được quản trị như tài nguyên nhạy cảm

Cần kiểm soát ai đăng nhập, quyền cục bộ, cài đặt công cụ, lưu tệp, lấy secret, truy cập Internet và thay đổi cấu hình theo nhu cầu thực tế.

Một jump host được dùng chung với tài khoản quản trị không rõ người dùng có thể làm giảm quy trách nhiệm dù mọi người đều đi qua cùng một máy.

### 8.4. Điểm kết thúc giao thức quyết định khả năng quan sát

Một tunnel chỉ chuyển tiếp luồng mã hóa có thể không nhìn được nội dung thao tác. Một gateway kết thúc giao thức hoặc một thành phần tại endpoint có thể quan sát theo khả năng được hỗ trợ.

Cần hiểu dữ liệu được giải mã và bảo vệ ở đâu. Không tắt mã hóa đường truyền chỉ để có recording.

Tuyên bố về giám sát phải khớp kiến trúc thực tế, không suy ra từ việc có một hộp proxy trên sơ đồ.

## 9. Quản lý credential trong truy cập từ xa

### 9.1. Ba mô hình thường gặp

| Mô hình | Đặc điểm | Điều cần quản lý |
|---|---|---|
| Người dùng dùng danh tính cá nhân tại đích | Có thể giữ định danh trực tiếp theo khả năng | Role, vòng đời account, xác thực và phiên |
| Gateway dùng credential được quản lý | Có thể giữ secret khỏi người dùng trong luồng đó | Quyền của gateway, rotation và ánh xạ người–phiên |
| Broker hoặc issuer cấp credential tạm | Có thể thu hẹp thời gian hoặc phạm vi | TTL thực tế, grant, renew và thu hồi tại đích |

Có thể phối hợp nhiều mô hình theo loại tài nguyên.

### 9.2. Không tiết lộ secret là một thuộc tính có phạm vi

Nếu gateway inject credential, người dùng có thể không nhận giá trị đó trong bước mở phiên. Điều này chưa chứng minh secret không tồn tại ở nguồn khác hoặc không thể lộ qua output, log hay môi trường chạy.

Cần quản lý quyền xuất secret, phiên bản trong vault, consumer và các bản sao đã có từ trước.

Không đưa password hoặc token vào URL, ticket hay log để đơn giản hóa mở phiên.

### 9.3. Credential ngắn hạn không tự làm quyền hẹp

Một token ngắn hạn có quyền rộng vẫn có ảnh hưởng lớn trong thời gian hiệu lực.

Cần kiểm tra role tại đích và các đường quyền gián tiếp. Thời hạn chỉ là một chiều của quyết định.

### 9.4. Kết thúc phiên và vòng đời credential

Khi phiên đóng, có thể cần check-in, rotation, gỡ grant hoặc thu hồi credential theo policy.

Đổi password không tự kết thúc mọi phiên. Đóng phiên cũng không làm secret đã được biết mất hiệu lực tại đích.

Nếu credential dùng chung với một workload, rotation sau lượt truy cập của con người cần xét dependency để tránh làm hỏng dịch vụ. Tách nhu cầu tương tác và tự động hóa có thể giúp giảm ảnh hưởng.

## 10. Luồng mở một phiên quản trị từ xa

### Bước 1: Chọn công việc và target

Người dùng chọn tài nguyên, action và mục đích trong phạm vi được phép. Hệ thống phân giải target từ nguồn quản lý, không tin mọi địa chỉ do client tự gửi.

### Bước 2: Xác thực và thu thập ngữ cảnh

Xác minh danh tính, yếu tố yêu cầu và các điều kiện môi trường theo policy. Ghi độ mới hoặc giới hạn của dữ liệu cần dùng.

### Bước 3: Đánh giá quyền

Kiểm tra role, tài nguyên, giao thức, cửa sổ thời gian, hình thức cấp và các điều kiện bổ sung.

Một ticket hợp lệ không thay thế việc đánh giá quyền của chủ thể.

### Bước 4: Phê duyệt nếu cần

Quyết định được ghi theo thẩm quyền và ràng buộc với phạm vi request. Nếu request thay đổi đáng kể, phải đánh giá lại.

### Bước 5: Đánh giá lại trước khi mở

Tài khoản có thể vừa bị ngừng hiệu lực, cửa sổ đã hết hoặc target đang không đủ điều kiện. Không coi approved là quyền mở phiên bất kỳ lúc nào.

### Bước 6: Chuẩn bị credential hoặc grant

Gateway, broker hoặc nguồn danh tính cung cấp theo cơ chế được phép. Ghi tham chiếu vòng đời mà không ghi giá trị secret.

### Bước 7: Xác minh đích và thiết lập phiên

Kết nối đúng target, xác minh trust và mở phiên bằng role phù hợp. Liên kết session ID với request, chủ thể và tài khoản tại đích.

### Bước 8: Thực thi các giới hạn

Áp dụng kênh được phép, timeout, recording và giới hạn hành động theo khả năng. Mọi tính năng bắt buộc cần được xác minh hoạt động.

### Bước 9: Theo dõi và xử lý thay đổi điều kiện

Giám sát theo phạm vi, xử lý hết hạn, gia hạn, thu hồi hoặc sự kiện làm chủ thể không còn đủ điều kiện.

### Bước 10: Kết thúc và đối soát

Xác minh kết quả đóng phiên ở từng lớp, xử lý credential hoặc grant theo policy và ghi phần chưa hoàn tất.

Một trạng thái “đã gửi yêu cầu kết thúc” khác với “đã xác nhận phiên đích kết thúc”.

### Policy logic minh họa

~~~yaml
remote_admin_policy:
  policy_id: production-network-diagnostics
  subject_scope: approved-network-operators
  target_scope: approved-production-network-targets
  allowed_action: diagnostic-session
  target_role: approved-diagnostic-role

  entry:
    identity_policy: required-operator-authentication
    environment_policy: approved-access-environment
    recheck_before_session_start: true

  delivery:
    path: managed-gateway
    secret_export: restricted-by-policy
    additional_channels: explicit-allow-list

  session:
    lifetime_policy: bounded-approved-session
    recording_policy: required-for-defined-protocol-scope
    resume_policy: reauthenticate-and-reauthorize

  lifecycle:
    credential_handling: defined-per-account
    target_termination_confirmation: tracked-separately
~~~

Đây là cấu trúc minh họa. Viết một trường như target_role hoặc recording_policy không tự tạo ra khả năng tương ứng; nền tảng và điểm thực thi phải hỗ trợ, cấu hình và được kiểm chứng.

## 11. Giao thức và các kênh chức năng bổ sung

### 11.1. Mỗi giao thức có khả năng riêng

| Đường truy cập | Nội dung cần kiểm tra |
|---|---|
| CLI qua SSH | Danh tính đích, tài khoản, mức quyền, các loại kênh và recording |
| Giao diện đồ họa từ xa | Quyền desktop, clipboard, chuyển hướng tài nguyên và trạng thái logoff |
| Web quản trị | Session web, SSO, cookie, tải tệp và API liên quan |
| Database client | Account, role, schema, truy vấn và vòng đời kết nối |
| API quản trị | Danh tính gọi, scope, phương thức, tài nguyên và audit |
| Console hoặc ngoài băng | Quyền tiếp cận vật lý logic, credential, phiên và bằng chứng |

Không coi kiểm soát một kênh CLI là đã bao phủ API hoặc web của cùng thiết bị.

### 11.2. Truyền tệp, clipboard và forwarding là quyết định riêng

Các chức năng như truyền tệp, clipboard, chuyển hướng thiết bị, forwarding hoặc ủy quyền qua agent có thể mở rộng khả năng sử dụng của phiên.

Cần xác định chức năng nào cần cho công việc, phạm vi nào được phép và thành phần nào thực thi. Không mặc định chúng đều nằm trong một recording màn hình hoặc một log lệnh.

Ủy quyền qua agent cũng có thể tạo khả năng sử dụng một danh tính mà không sao chép nguyên private key. Cần đánh giá quyền sử dụng được ủy quyền, không chỉ tìm bản sao khóa.

### 11.3. Giới hạn lệnh có ngữ nghĩa cần kiểm chứng

Một danh sách tên lệnh hoặc bộ lọc chuỗi không mặc định bao phủ mọi cách tạo cùng tác động trong shell, công cụ tương tác hoặc API.

Cần phối hợp với role, quyền dữ liệu và cơ chế tác vụ phù hợp tại đích. Nếu không thể giới hạn hẹp, phải ghi nhận giới hạn và rủi ro còn lại.

### 11.4. Nội dung hiển thị vẫn có thể bị lấy

Chặn clipboard hoặc tải tệp có thể giảm một số đường đưa dữ liệu ra ngoài. Nó không ngăn tuyệt đối việc ghi lại nội dung đã hiển thị.

Cần giới hạn dữ liệu và quyền từ gốc, đồng thời dùng giám sát phù hợp. Không tuyên bố chống mọi rò rỉ chỉ từ một cờ chặn clipboard.

## 12. Vòng đời phiên, timeout và resume

### 12.1. Các giới hạn thời gian khác nhau

Idle timeout dựa trên loại activity được công nhận. Giới hạn tuyệt đối dựa trên tuổi phiên hoặc cửa sổ bắt buộc. Grant và credential có thể có vòng đời riêng.

Keepalive hoặc output nền không tự là bằng chứng người dùng hiện diện. Định nghĩa activity phải rõ và được thực thi ở điểm có thẩm quyền.

### 12.2. Client đóng không đồng nghĩa đích đã logoff

Một phiên có thể có kênh client, gateway và trạng thái tại đích. Ngắt một lớp chưa chứng minh mọi lớp đã kết thúc.

Tác vụ đã gửi tới đích cũng có thể tiếp tục sau khi tương tác bị chặn. Cần bằng chứng riêng nếu mục tiêu yêu cầu hủy công việc.

### 12.3. Resume cần điều kiện hiện tại

Client có cookie hoặc session ID cũ không tự được tiếp tục quyền.

Cần kiểm tra danh tính, trạng thái account, role, target, cửa sổ và giới hạn thời gian. Không đặt lại toàn bộ tuổi phiên chỉ vì network phục hồi hoặc gateway chuyển instance.

### 12.4. Theo dõi kết quả thu hồi

Có thể cần tách:

~~~text
Quyết định thu hồi đã ghi.
Truy cập mới bị chặn.
Tương tác hiện tại đã bị chặn.
Yêu cầu kết thúc đã gửi.
Gateway xác nhận đóng.
Đích xác nhận kết thúc trong phạm vi.
Credential hoặc grant còn cần xử lý.
~~~

Không dùng một nhãn revoked để thay thế mọi kết quả này.

## 13. Recording, log và chuỗi bằng chứng

### 13.1. Bằng chứng cần phục vụ câu hỏi cụ thể

Có thể cần biết:

- Ai khởi tạo và ai phê duyệt.
- Đích, account, role và phạm vi action.
- Phiên mở khi nào, theo policy nào.
- Những kênh nào được phép.
- Điều gì được ghi nhận ở gateway và ở đích.
- Khi nào bị chặn hoặc kết thúc.
- Những phần không quan sát được.

Recording và log tại đích có thể bổ sung cho nhau. Không tự coi một nguồn là đầy đủ cho mọi đường.

### 13.2. Giới hạn quan sát phải được nêu rõ

Một video desktop không nhất thiết giải thích đầy đủ mọi thay đổi phía sau. Log lệnh không tự chứa mọi nội dung truyền tệp. Luồng được mã hóa xuyên qua một tunnel có thể không được proxy đọc.

Nếu policy yêu cầu một mức recording, cần kiểm tra sản phẩm thật sự cung cấp được cho giao thức và tính năng đang dùng.

### 13.3. Bảo vệ tính toàn vẹn và nguồn gốc

Có thể dùng cơ chế phát hiện sửa đổi, quyền lưu trữ, lưu lịch sử và tách trách nhiệm theo yêu cầu.

Một hash không tự chứng minh bản ghi đầy đủ hoặc đúng người thực hiện. Một thành phần bị kiểm soát có thể tạo dữ liệu sai trước khi dữ liệu được bảo vệ.

Cần hiểu nguồn tạo bằng chứng, khả năng mất đoạn và quyền quản trị hệ thống ghi nhận.

### 13.4. Dữ liệu nhạy cảm trong recording

Output, màn hình, truy vấn hoặc file có thể chứa secret và dữ liệu nhạy cảm. Việc che dữ liệu cũng có thể làm giảm một phần khả năng tái hiện.

Cần chọn phạm vi, quyền xem và thời hạn lưu phù hợp. Không gửi recording hoặc log nguyên vẹn cho mọi bên chỉ vì đó là bằng chứng vận hành.

Nếu không lưu được bằng chứng bắt buộc, phải đi theo policy xử lý lỗi đã định, không âm thầm tiếp tục vô thời hạn.

## 14. Tách truy cập con người và tự động hóa

### 14.1. Workload cần danh tính riêng

Một job quản trị nên có danh tính, owner, role, target và vòng đời phù hợp. Không dùng credential cá nhân của một kỹ sư để vận hành liên tục chỉ vì kết nối đó đã có sẵn.

Danh tính gọi vault hoặc API phải có phạm vi và khả năng thu hồi riêng.

### 14.2. Ngữ nghĩa phiên khác nhau

Idle dựa vào bàn phím hoặc chuột không phù hợp với mọi job hoặc API.

Workload có thể cần giới hạn theo request, lần chạy, token, grant hoặc tác vụ. Bằng chứng có thể là audit API và kết quả job thay vì recording màn hình.

Không gọi thiếu recording tương tác là thiếu toàn bộ giám sát nếu mô hình thực tế dùng loại bằng chứng khác phù hợp.

### 14.3. Giữ liên kết người khởi tạo và chủ thể thực thi

Nếu một người yêu cầu automation thực hiện việc quản trị, cần giữ được cả người khởi tạo lẫn workload thực hiện.

Chỉ lưu tên service account có thể làm mất bối cảnh trách nhiệm. Ngược lại, chỉ lưu tên người yêu cầu có thể che danh tính máy và quyền mà automation thật sự sử dụng.

### 14.4. Không biến phiên tương tác thành dịch vụ ngầm

Một phiên mở lâu để chạy các công việc lặp lại có thể làm mất giới hạn thời gian và vòng đời rõ ràng.

Nếu công việc là tự động hóa, nên được mô hình hóa, phân quyền và giám sát như một workload theo khả năng hệ thống. Không duy trì phiên quản trị bằng hoạt động giả để né timeout.

## 15. Truy cập của nhà cung cấp và đối tác

### 15.1. Có người bảo trợ và phạm vi công việc

Truy cập đối tác cần danh tính riêng, đơn vị chịu trách nhiệm, người bảo trợ nội bộ và phạm vi tài nguyên rõ.

Không tạo một tài khoản chung cho mọi kỹ sư của một nhà cung cấp rồi dùng lịch hẹn làm bằng chứng ai đã đăng nhập. Cần quản lý người thực sự sử dụng.

### 15.2. Chỉ cấp những điều kiện cần cho công việc

Cần xác định target, action, giao thức, hình thức tương tác, kênh bổ sung, thời gian và điều kiện phê duyệt.

Nếu chỉ cần chẩn đoán một thiết bị, quyền kết nối tới toàn bộ mạng quản trị thường rộng hơn mục tiêu đó. Khả năng hạn chế phải được thực thi ở các lớp liên quan.

### 15.3. Tài khoản đối tác có vòng đời

Cần quy trình khi kỹ sư đổi vai trò, người bảo trợ thay đổi hoặc hợp đồng kết thúc.

Chặn đăng nhập mới chưa tự xử lý phiên đang mở hoặc credential đã được tiết lộ. Cần đánh giá vòng đời theo phạm vi dữ kiện.

Không giữ quyền lâu dài chỉ vì có thể nhà cung cấp sẽ cần hỗ trợ trong tương lai.

### 15.4. Môi trường truy cập và dữ liệu

Cần hiểu khả năng quản lý môi trường đầu cuối của đối tác, những tín hiệu có thể xác minh và giới hạn còn lại.

Một gateway giữ secret khỏi người dùng trong bước mở phiên có thể giảm phơi lộ credential, nhưng dữ liệu hiển thị và quyền trong phiên vẫn cần kiểm soát.

Nếu có nhu cầu tải log hoặc file hỗ trợ, phải coi đó là chức năng có phạm vi riêng và bảo vệ dữ liệu liên quan.

## 16. Tính sẵn sàng, lỗi và đường khẩn cấp

### 16.1. Nhận diện phụ thuộc

Đường remote admin có thể phụ thuộc vào identity provider, directory, policy, vault, DNS, thời gian, gateway, mạng quản trị và hệ thống audit.

Nhiều instance gateway không đủ nếu tất cả phụ thuộc cùng một thành phần không có phương án phục hồi.

Cần biết lỗi nào ảnh hưởng mở phiên mới, lỗi nào ảnh hưởng phiên đang hoạt động và lỗi nào làm chậm thu hồi.

### 16.2. Hành vi khi chưa xác minh được điều kiện

| Tình huống | Quyết định cần được thiết kế |
|---|---|
| Không xác minh được danh tính | Không coi điều kiện xác thực đã đạt |
| Dữ liệu quyền không còn đủ mới | Xử lý theo policy của hành động và mức rủi ro |
| Vault không cung cấp credential | Trạng thái cấp mới và phục hồi theo phạm vi |
| Recording bắt buộc không hoạt động | Cách chặn, hạn chế hoặc dùng đường khẩn cấp được quản trị |
| Gateway mất kết nối control plane | Giới hạn tiếp diễn và khả năng nhận thu hồi |
| Không tới được đích để kết thúc | Giữ phần xử lý pending và chuyển cấp |
| Mất trạng thái phiên sau failover | Không tự khởi tạo lại mọi giới hạn như một phiên mới |
| Trust của máy chủ không đạt | Không bỏ kiểm tra rồi tiếp tục gửi credential |

Các quyết định phải được thống nhất trước và kiểm chứng trên hệ thống thực tế.

### 16.3. Cache và độ trễ thu hồi

Cache policy, nhóm hoặc credential có thể giúp vận hành nhưng cũng tạo khoảng trễ.

Cần xác định dữ liệu gì được cache, trong bao lâu, ai được đọc và sự kiện nào làm mất hiệu lực. Không dùng last-known-good vô thời hạn khi nguồn không còn được xác minh.

Nếu client hoặc gateway đã có credential, chặn truy cập control plane chưa chắc ngăn credential đó dùng ở đường khác.

### 16.4. Đường break-glass

Đường khẩn cấp phải có điều kiện, chủ thể chịu trách nhiệm, phạm vi, cách bảo vệ credential, bằng chứng và rà soát sau sử dụng.

Nó cần giải quyết đúng điểm hỏng. Nếu đường phục hồi lại phụ thuộc hoàn toàn vào thành phần đang lỗi, nó có thể không dùng được lúc cần.

Không tự mở một cổng quản trị rộng ra ngoài hoặc chia sẻ credential chung để thay thế một gateway đang lỗi. Phương án khẩn cấp phải được thiết kế và quản trị như một đường đặc quyền riêng.

### 16.5. Khôi phục không chỉ là bật lại dịch vụ

Sau phục hồi, cần đối soát phiên, grant, credential, policy version và tác vụ thu hồi còn chờ.

Một gateway mới hoạt động không chứng minh các phiên do gateway cũ mở đã kết thúc. Cần giữ khả năng tìm và xử lý những đối tượng đó theo phạm vi.

## 17. Thu hồi và ứng phó sự cố

### 17.1. Xử lý theo nhiều lớp

Khi có quyết định ngừng truy cập, có thể cần:

1. Chặn chủ thể xác thực hoặc lấy bằng chứng mới.
2. Chặn mở phiên và renew tại PAM.
3. Chặn tương tác hoặc kết thúc các phiên liên quan.
4. Thu hồi grant hoặc role tạm.
5. Rotation hoặc thu hồi credential đã bị phơi lộ.
6. Hạn chế đường mạng liên quan theo phạm vi.
7. Kiểm tra hoạt động và thay đổi bền vững đã xảy ra.
8. Ghi bằng chứng và giới hạn còn lại.

Không cần mọi trường hợp đều thực hiện cùng một tập hành động. Phạm vi phụ thuộc dữ kiện và mục tiêu thu hồi.

### 17.2. Một hành động không thay các lớp khác

Vô hiệu hóa account tại nguồn không mặc định kết thúc mọi phiên đã có. Chặn IP không tự thu hồi token. Đổi password không tự gỡ khóa hoặc tài khoản khác đã được tạo.

Cần bằng chứng từ đúng điểm thực thi để kết luận.

### 17.3. Xác định ảnh hưởng

Các liên kết quan trọng gồm subject ID, request, target, account hiệu lực, credential reference, session ID và thời điểm.

Nếu dùng tài khoản chung tại đích, cần hiểu giới hạn quy trách nhiệm và kiểm tra những đường có thể dùng cùng tài khoản ngoài gateway.

Không dùng việc thiếu một log làm bằng chứng chắc chắn không có hoạt động.

### 17.4. Bảo toàn bằng chứng

Cần giữ dữ liệu có liên quan trong phạm vi chính sách, hạn chế khả năng sửa và ghi rõ chủ thể can thiệp.

Kết thúc phiên có thể ngăn hoạt động tiếp diễn nhưng không đảo ngược thay đổi đã xảy ra. Xử lý hậu quả là công việc riêng.

Không xóa session record để khiến phiên biến mất khỏi danh sách đang mở trong khi chưa rõ trạng thái tại đích.

## 18. Tình huống xuyên suốt: hỗ trợ chẩn đoán firewall

### 18.1. Bối cảnh

Một kỹ sư đối tác cần chẩn đoán firewall production A trong một cửa sổ hỗ trợ. Không có nhu cầu sửa cấu hình hoặc truy cập firewall B.

Giả định nền tảng đích hỗ trợ role chẩn đoán phù hợp và khả năng đó đã được kiểm chứng. Gateway hỗ trợ recording cho giao thức và chức năng được dùng.

Policy của tình huống:

- Danh tính kỹ sư được xác định riêng.
- Có người bảo trợ và quyết định theo phạm vi công việc.
- Chỉ target A và role chẩn đoán được phép.
- Đi qua gateway, không xuất secret theo luồng này.
- Các kênh bổ sung chỉ được phép khi có nhu cầu được duyệt.
- Cửa sổ truy cập có giới hạn.
- Kết quả kết thúc tại gateway và tại đích được theo dõi riêng.

Các điều kiện chỉ minh họa cho tình huống, không phải cấu hình của một sản phẩm cụ thể.

### 18.2. Trước khi mở phiên

PAM xác minh danh tính và điều kiện môi trường theo policy, đối chiếu request cùng quyết định, rồi kiểm tra lại trước khi mở.

Gateway phân giải target A từ danh mục được quản trị và xác minh danh tính máy chủ. Credential được lấy theo quyền của gateway, gắn với session và account tại đích.

Kỹ sư xác thực được vào PAM không tự làm target B trở thành tài nguyên được phép.

### 18.3. Trong phiên

Role tại đích giới hạn hành động theo khả năng đã xác minh. Recording và log được liên kết với người yêu cầu, session và target.

Nếu có nhu cầu tải một file log, đó là thay đổi về chức năng cần được đánh giá theo policy. Không tự bật mọi kênh truyền tệp hoặc forwarding vì phiên đã được duyệt.

Một kiểm chứng khác cần đánh giá các đường từ target A tới tài nguyên khác trong phạm vi thiết kế. Menu chỉ hiển thị A không tự chứng minh không có khả năng truy cập tiếp từ bên trong target.

### 18.4. Khi hết cửa sổ

PAM ngừng cho phép tiếp tục theo policy, gateway chặn tương tác và thực hiện hành động kết thúc được hỗ trợ.

Nếu gateway đã đóng kênh nhưng xác nhận từ đích còn chờ, báo cáo giữ trạng thái pending cho phần đó. Không kết luận mọi tác vụ phía đích đã dừng.

Credential, grant hoặc checkout được xử lý theo vòng đời riêng của account. Không tự rotation một credential dùng chung với dịch vụ khác khi chưa biết dependency.

### 18.5. Nghiệm thu và đóng công việc

Bằng chứng cần cho biết:

~~~text
Ai đã được cấp.
Target và role nào được dùng.
Những kênh nào được cho phép.
Khoảng thời gian và policy có hiệu lực.
Nguồn recording và log.
Kết quả tại gateway.
Kết quả tại đích trong phạm vi xác nhận.
Phần credential hoặc grant cần xử lý.
Giới hạn quan sát và công việc còn lại.
~~~

Khi quyền hỗ trợ không còn nhu cầu, vòng đời danh tính và entitlement phải được xử lý. Một phiên đã đóng không tự chứng minh tài khoản đối tác đã hết quyền cho lần truy cập tiếp theo.

## 19. Kiểm chứng và chỉ số quản trị

### 19.1. Các tình huống cần kiểm chứng

| Tình huống | Kết quả cần quan sát |
|---|---|
| Danh tính hợp lệ nhưng không có quyền target | Không mở phiên chỉ nhờ xác thực thành công |
| Request đổi target sau phê duyệt | Không dùng quyết định cũ cho phạm vi mới |
| Client gửi endpoint ngoài danh mục | Không kết nối tùy ý bằng quyền gateway |
| Trust của đích không đạt | Không tiếp tục gửi credential |
| Role chẩn đoán | Quyền hiệu lực khớp nhu cầu và giới hạn đã định |
| Kênh file hoặc forwarding không được phép | Hạn chế thật sự tại lớp thực thi |
| Truy cập trực tiếp ngoài gateway | Hành vi theo kiểm soát mạng và account đã thiết kế |
| Tài khoản mất quyền trước khi mở hoặc resume | Không tiếp tục từ dữ liệu cũ trái policy |
| Hết idle hoặc giới hạn tuyệt đối | Hành động và bằng chứng đúng từng lớp |
| Thu hồi khi phiên còn mở | Đo được tới kết quả thực thi trong phạm vi |
| Recording bắt buộc lỗi | Hành vi theo policy và giữ trạng thái còn lại |
| Gateway failover | Không mất session tracking hoặc tự cấp lại thời gian |
| Tác vụ nền tiếp tục sau ngắt | Báo đúng phạm vi, không khẳng định đã hủy công việc |
| Đường khẩn cấp được sử dụng | Có bằng chứng và xử lý sau sử dụng |
| Credential bị rotation | Consumer và dependency được kiểm tra theo phạm vi |

Các kiểm chứng cần chọn môi trường và tác vụ phù hợp. Không tạo thay đổi nguy hiểm trên production chỉ để làm bằng chứng.

### 19.2. Tiêu chí đóng trong phạm vi

Có thể cần xác nhận:

- Danh tính, target, account và owner đúng.
- Quyền, hình thức cấp và kênh chức năng đúng.
- Trust, kết nối và phiên được kiểm tra.
- Bằng chứng hoạt động có chất lượng phù hợp.
- Hết hạn, resume và thu hồi đạt theo kế hoạch.
- Phục hồi có thể sử dụng trong những tình huống đã định.
- Ngoại lệ và phần chưa kiểm tra có owner cùng trạng thái rõ.

Không gộp NOT_TESTED hoặc UNKNOWN thành PASS khi tổng hợp.

### 19.3. Chỉ số có ý nghĩa

Có thể theo dõi:

- Target có owner, đường quản trị và role đã xác định.
- Phiên có đầy đủ liên kết request, chủ thể, account và bằng chứng.
- Truy cập dùng secret export so với mô hình không tiết lộ secret.
- Quyền đủ điều kiện và quyền thường trực theo phạm vi.
- Độ trễ thu hồi tới chặn input và kết quả tại đích.
- Hành động kết thúc còn pending hoặc không xác định.
- Recording lỗi hoặc thiếu đoạn trong phạm vi yêu cầu.
- Đường trực tiếp và ngoại lệ chưa xử lý.
- Tài khoản đối tác quá hạn hoặc không còn người bảo trợ.
- Thay đổi policy mở rộng target, thời gian hoặc chức năng.

Tỷ lệ trong tập tài nguyên đã quản lý không chứng minh bao phủ toàn bộ hạ tầng. Mẫu số và phạm vi quan sát cần được ghi rõ.

## 20. Lỗi thường gặp và bài tập áp dụng

### 20.1. Lỗi thường gặp

| Lỗi | Hậu quả | Cách xử lý |
|---|---|---|
| Có VPN là coi đã có PAM | Quyền và phiên chưa được quản lý đầy đủ | Tách kết nối, danh tính và ủy quyền |
| MFA thành công là được quản trị mọi target | Cấp quyền quá rộng | Policy theo role, target và action |
| Gateway nhận mọi hostname từ client | Có thể vượt phạm vi hoặc gửi credential sai đích | Phân giải từ danh mục được quản trị |
| Giữ secret khỏi người dùng là coi không thể lộ | Bỏ sót nguồn khác, output hoặc gateway | Quản lý toàn bộ vòng đời và đường phơi lộ |
| Role ở PAM hẹp nhưng account đích toàn quyền | Giới hạn chỉ tồn tại trên nhãn | Kiểm tra quyền hiệu lực tại đích |
| Ghi hình là coi ngăn được mọi hành động | Quyền ngoài phạm vi vẫn có thể bị dùng | Thực thi giới hạn ở lớp phù hợp |
| CLI qua PAM nhưng API hoặc web còn rộng | Có đường quản trị ngoài phạm vi | Kiểm kê và kiểm soát mọi đường liên quan |
| Tài khoản đối tác dùng chung | Khó quy trách nhiệm | Danh tính riêng và vòng đời rõ |
| Bỏ trust khi thiết bị đổi chứng thư | Có thể kết nối nhầm hoặc lộ credential | Xác minh thay đổi trước khi cập nhật |
| Đóng client là coi đích đã logoff | Phiên hoặc tác vụ có thể tiếp tục | Theo dõi kết quả từng lớp |
| Chặn account mới là coi hết truy cập cũ | Token, phiên hoặc secret đã cấp còn hiệu lực | Thu hồi theo nhiều lớp |
| Gateway lỗi thì mở quyền trực tiếp rộng | Tạo đường khẩn cấp ngoài kiểm soát | Thiết kế break-glass có phạm vi |
| Dùng phiên người dùng cho automation lâu dài | Mất vòng đời và trách nhiệm workload | Mô hình danh tính máy riêng |
| Một hash được coi là bằng chứng đầy đủ | Bỏ sót nguồn gốc hoặc mất đoạn | Bảo vệ và kiểm tra chuỗi bằng chứng |
| Báo bao phủ toàn bộ từ một giao thức | Che đường quản trị khác | Nêu rõ phạm vi và phần chưa biết |

### 20.2. Bài tập

Một đội cho nhà cung cấp VPN vào mạng quản trị rồi dùng tài khoản local chung trên nhiều thiết bị. PAM chỉ lưu mật khẩu và ghi hình một phiên SSH. Web quản trị, API và console chưa được kiểm kê. Khi hợp đồng kết thúc, tài khoản VPN bị khóa nhưng phiên đang mở chưa được kiểm tra. Đội báo đã thu hồi toàn bộ remote admin access.

Hãy phân tích:

1. Những lớp kiểm soát nào đang bị gộp?
2. Vì sao tài khoản chung và credential dùng trên nhiều đích làm tăng phạm vi ảnh hưởng?
3. Recording một phiên đã và chưa chứng minh điều gì?
4. Khóa VPN đã xử lý lớp nào, chưa chắc xử lý lớp nào?
5. Cần kiểm kê và xác minh thêm những đường nào?
6. Một thiết kế có JIT/JEA và bằng chứng phù hợp cần những thay đổi gì?

Hướng phân tích:

- Kết nối mạng, quyền tại đích, credential, phiên và bằng chứng là các trách nhiệm khác nhau.
- Credential chung khó thu hồi theo người và có thể dùng ngoài phiên được quan sát.
- Recording chỉ bao phủ đường, thời gian và chức năng thật sự được hỗ trợ.
- Khóa VPN có thể chặn kết nối mới qua đường đó, chưa chứng minh mọi phiên hoặc credential đã mất hiệu lực.
- Cần xem web, API, console, controller, đường trực tiếp và những phụ thuộc khác trong phạm vi.
- Cần danh tính riêng, target/action có phạm vi, quyền hiệu lực hẹp, thời gian được thực thi và chuỗi thu hồi có kiểm chứng.

## 21. Các điểm cần nắm

Remote admin access là một chuỗi kiểm soát từ danh tính và môi trường truy cập tới target, credential, quyền và phiên. Một đường kết nối an toàn mới là một phần của chuỗi đó.

PAM cần giới hạn người nào được làm gì, qua đường nào, trong bao lâu và với bằng chứng gì. JIT, JEA, vault, gateway và recording có vai trò riêng, cần được kết hợp theo khả năng thực tế.

Khi đánh giá thiết kế, hãy lần theo một request tới quyền hiệu lực tại đích, rồi theo quá trình kết thúc và thu hồi. Chỉ khẳng định phần đã được xác minh, đồng thời giữ rõ owner và trạng thái của phần còn lại.
