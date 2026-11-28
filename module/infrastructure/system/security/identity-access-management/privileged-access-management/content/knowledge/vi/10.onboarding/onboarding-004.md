# Onboard network device: đưa thiết bị mạng vào quản lý PAM

## 1. Mục tiêu và phạm vi

**Onboard network device** là quá trình đưa đường truy cập quản trị của thiết bị mạng vào phạm vi quản lý truy cập đặc quyền (Privileged Access Management — PAM), từ kiểm kê đối tượng, quản lý tài khoản và credential đến kiểm soát phiên, rotation, phục hồi và lưu bằng chứng.

Đối tượng có thể là router, switch, firewall, bộ cân bằng tải, thiết bị VPN hoặc bộ điều khiển mạng. Thiết bị có thể có nhiều đường quản trị: CLI qua SSH, giao diện web, API, console, nền tảng điều khiển tập trung và các giao thức quản lý khác.

Mục tiêu không chỉ là lưu một mật khẩu vào vault. Một thiết bị được đưa vào quản lý đúng phạm vi cần trả lời được:

1. Thiết bị và các thành phần của nó được định danh bằng gì?
2. Tài khoản nào được dùng cho người quản trị, tự động hóa và khẩn cấp?
3. Ai được truy cập, qua đường nào, với quyền gì và trong bao lâu?
4. Credential được lấy, sử dụng, đổi và thu hồi như thế nào?
5. Hoạt động nào được ghi nhận và có thể quy trách nhiệm tới đâu?
6. Làm thế nào để phục hồi khi PAM, AAA hoặc đường quản trị gặp lỗi?

Đây là bài học về quy trình và kiến trúc triển khai. Các cấu trúc minh họa không phải lệnh hoặc cú pháp của một hãng thiết bị cụ thể. Khả năng thực tế cần được xác minh cho từng dòng thiết bị, phiên bản phần mềm và connector.

## 2. Phân biệt các lớp kiểm soát

| Lớp | Chức năng | Điều không thể tự suy ra |
|---|---|---|
| Vault | Bảo vệ credential, quản lý truy cập và phiên bản | Credential chưa từng bị sao chép ra ngoài |
| Broker hoặc connector PAM | Cấp, sử dụng, kiểm tra hoặc đổi credential theo khả năng | Thiết bị đã được giới hạn quyền đúng nhu cầu |
| Gateway quản trị | Trung gian kết nối và có thể ghi nhận phiên | Mọi đường truy cập trực tiếp đều đã bị chặn |
| AAA | Xác thực, ủy quyền và ghi nhận hoạt động theo cấu hình | Mọi lệnh trên mọi giao thức đều được kiểm soát giống nhau |
| Role hoặc cơ chế quyền tại thiết bị | Giới hạn hành động tại đích | Phiên cũ tự mất quyền ngay khi role thay đổi |
| Hệ thống quản lý cấu hình | Duy trì cấu hình mong muốn và triển khai thay đổi | Thay đổi cục bộ của PAM luôn được giữ lại |
| Audit và giám sát | Liên kết quyết định, phiên và hoạt động tại đích | Có đủ bằng chứng cho những đường chưa được thu thập |

AAA gồm ba trách nhiệm khác nhau:

- **Authentication:** xác minh chủ thể đăng nhập.
- **Authorization:** quyết định chủ thể được thực hiện hành động nào.
- **Accounting:** ghi nhận hoạt động theo cơ chế được hỗ trợ.

Một thiết bị xác thực thành công qua hệ thống tập trung chưa chứng minh đã có ủy quyền lệnh phù hợp. Một bản ghi đăng nhập cũng chưa chứng minh đầy đủ nội dung phiên.

Khi dùng TACACS+, RADIUS hoặc cơ chế AAA khác, cần kiểm tra chức năng được thiết bị và nền tảng hỗ trợ. Không lựa chọn dựa chỉ trên tên giao thức hoặc mặc định rằng mọi tính năng PAM sẽ tự có.

## 3. Kiểm kê thiết bị và toàn bộ đường quản trị

### 3.1. Định danh thiết bị

Không nên dùng một địa chỉ IP làm định danh duy nhất. IP có thể đổi hoặc được chuyển sang thiết bị khác; tên DNS cũng có thể đại diện một cụm thay vì một node.

Hồ sơ tối thiểu có thể gồm:

| Nhóm thông tin | Nội dung cần xác định |
|---|---|
| Định danh | Asset ID, serial hoặc định danh nền tảng phù hợp |
| Chức năng | Router biên, firewall, switch lõi, controller |
| Môi trường | Production, thử nghiệm, dự phòng |
| Owner | Đội chịu trách nhiệm kỹ thuật và dịch vụ liên quan |
| Nền tảng | Dòng thiết bị, phiên bản phần mềm, loại connector |
| Điểm quản trị | Địa chỉ, tên, cổng, giao thức và phạm vi mạng |
| Cấu trúc | Thiết bị độc lập, cụm, node và điểm truy cập logic |
| Cơ chế xác thực | Tài khoản local, AAA, khóa, token hoặc chứng thư |
| Phụ thuộc | DNS, thời gian, AAA, PAM, hệ thống điều khiển |
| Phục hồi | Console, đường ngoài băng và người chịu trách nhiệm |

Cần phân biệt thiết bị vật lý hoặc node với một endpoint logic của cụm. Nếu một địa chỉ quản trị có thể tới nhiều node, phải hiểu danh tính máy chủ và credential nào có hiệu lực ở từng nơi.

### 3.2. Liệt kê đường vào trước khi áp dụng kiểm soát

~~~text
Quản trị viên
  → gateway PAM → SSH → thiết bị
  → giao diện web → thiết bị
  → console server → console thiết bị
  → controller mạng → thiết bị

Tự động hóa
  → API → thiết bị hoặc controller
  → tác vụ backup/triển khai → giao thức quản trị được dùng
~~~

Không coi thiết bị đã được kiểm soát đầy đủ nếu mới đưa SSH qua PAM nhưng web, API hoặc console vẫn dùng credential rộng được chia sẻ.

Mục đích kiểm kê là xác định phạm vi thực tế. Một đường chưa được tích hợp cần owner, biện pháp kiểm soát và kế hoạch xử lý hoặc ngoại lệ rõ ràng.

### 3.3. Kiểm kê consumer của credential

Một mật khẩu có thể được dùng bởi công cụ backup, hệ thống triển khai, tác vụ chẩn đoán và người vận hành.

Nếu chỉ thay mật khẩu rồi kiểm tra một phiên SSH, các consumer khác có thể hỏng sau đó. Cần biết consumer lấy credential từ đâu, có cache không và cập nhật theo cơ chế nào.

## 4. Nhận diện đúng tài khoản và loại credential

| Loại | Mục đích | Điểm cần chú ý |
|---|---|---|
| Tài khoản quản trị cá nhân qua AAA | Gắn danh tính người dùng với truy cập | Role và phạm vi lệnh phải được kiểm tra tại đích |
| Tài khoản local quản trị thường ngày | Truy cập khi mô hình yêu cầu | Tránh chia sẻ rộng hoặc dùng cùng credential trên nhiều thiết bị |
| Tài khoản local khẩn cấp | Phục hồi trong tình huống được quy định | Cần bảo vệ và khả năng sử dụng độc lập với điểm hỏng liên quan |
| Tài khoản tự động hóa | Backup, triển khai hoặc tích hợp | Có consumer, owner và quyền theo tác vụ |
| Secret nâng mức đặc quyền | Chuyển sang chế độ có quyền cao hơn khi nền tảng có cơ chế này | Có thể là đối tượng khác với mật khẩu đăng nhập |
| Khóa SSH của client | Xác thực tài khoản quản trị | Phải quản lý private key, public key được cài và việc thu hồi |
| Token hoặc khóa API | Truy cập API | Kiểm tra scope, thời hạn và khả năng thu hồi |
| Credential quản lý khác | Giám sát hoặc quản lý qua giao thức riêng | Không coi tự động được bảo vệ chỉ nhờ onboard tài khoản SSH |

**Khóa máy chủ SSH** dùng để xác minh thiết bị khác với khóa của client dùng để đăng nhập. Nhầm hai đối tượng có thể dẫn tới quản lý sai vòng đời hoặc kết nối tới thiết bị giả mạo.

Một tài khoản đăng nhập cũng có thể cần secret riêng để nâng quyền. Connector phải hỗ trợ đúng luồng; không coi kiểm tra đăng nhập ở chế độ thấp là bằng chứng đã quản lý được toàn bộ quyền cần dùng.

Nếu tài khoản được xác thực tại AAA hoặc directory, cần xác định đúng nguồn quản lý credential. Một credential tập trung dùng cho nhiều thiết bị không nên bị mô hình hóa như các mật khẩu local độc lập rồi rotation từng bản sao.

## 5. Chọn mô hình truy cập phù hợp

### 5.1. Credential local được vault quản lý

PAM lưu và dùng credential của tài khoản local, có thể qua gateway để người dùng không cần nhận giá trị secret.

Ưu điểm là phù hợp với nhiều thiết bị cũ. Các giới hạn cần quản lý gồm:

- Tài khoản có thể dùng chung cho nhiều người.
- Danh tính tại đích có thể chỉ hiện tên tài khoản kỹ thuật.
- Việc đổi mật khẩu phụ thuộc khả năng connector và thiết bị.
- Credential có thể vẫn dùng được qua đường truy cập khác.
- Quyền có thể thường trực dù việc mở phiên được cấp theo thời gian.

### 5.2. Danh tính cá nhân qua AAA, PAM kiểm soát đường phiên

Thiết bị sử dụng AAA để xác thực hoặc xác định quyền, còn PAM làm trung gian truy cập và giám sát theo khả năng.

Cần kiểm tra luồng danh tính: thiết bị thấy người dùng thật hay một tài khoản trung gian, AAA nhận thuộc tính gì và bằng chứng nào nối phiên PAM với phiên tại đích.

Không suy ra rằng có AAA thì PAM không cần quản lý tài khoản local. Tài khoản khẩn cấp và tài khoản tự động hóa vẫn có thể tồn tại.

### 5.3. Truy cập qua API hoặc controller

Với một số hạ tầng, công việc quản trị thực hiện qua controller thay vì từng node.

Khi đó, đối tượng cần onboard có thể bao gồm controller, token truy cập và các tài khoản quản trị trực tiếp tại node. Phải hiểu thay đổi nào được controller duy trì và thay đổi cục bộ nào có thể bị ghi đè.

### 5.4. Các mô hình có thể phối hợp

~~~mermaid
flowchart LR
    U["Quản trị viên"] -->|Danh tính và yêu cầu| P["PAM"]
    P -->|Phiên được cho phép| G["Gateway"]
    V["Vault"] -->|Credential được kiểm soát| G
    G -->|Kênh quản trị| D["Thiết bị hoặc node"]
    D -.->|Xác thực, quyền, accounting theo thiết kế| A["AAA"]
    W["Workload tự động hóa"] -->|Yêu cầu theo danh tính workload| B["Broker hoặc tích hợp secret"]
    B -->|Credential hoặc token có phạm vi| W
    W -->|API quản trị| C["Controller hoặc API thiết bị"]
    G --> L["Audit và giám sát"]
    D --> L
    C --> L
~~~

Sơ đồ là kiến trúc logic. Không phải mọi thiết bị đều hỗ trợ tất cả các đường hoặc cơ chế này.

## 6. Điều kiện chuẩn bị trước khi thay đổi

Trước khi chuyển đường quản trị hoặc bật rotation, cần có các điều kiện phù hợp với phạm vi:

1. Owner và danh mục tài khoản được xác nhận.
2. Nhu cầu quyền được xác định theo công việc.
3. Connector tương thích với nền tảng và luồng xác thực.
4. Đường mạng quản trị và kiểm tra danh tính máy chủ được chuẩn bị.
5. Các consumer và phụ thuộc được nhận diện.
6. Phương án phục hồi có thể sử dụng.
7. Thời điểm triển khai phù hợp với ảnh hưởng dịch vụ.
8. Bằng chứng trạng thái ban đầu và cấu hình liên quan được bảo vệ.
9. Tiêu chí nghiệm thu và điều kiện dừng được thống nhất.

Một phiên quản trị đang mở có thể giúp xử lý một số tình huống, nhưng không thay thế đường phục hồi đáng tin cậy. Phiên có thể hết hạn, đứt kết nối hoặc không có quyền cần thiết.

Không nên thay cùng lúc AAA, ACL quản trị, credential và quyền của tài khoản nếu chưa có cách phân biệt lỗi và phục hồi. Chia thay đổi thành các bước có thể xác minh giúp giảm trạng thái không xác định.

## 7. Thiết lập kết nối quản trị và tin cậy máy chủ

### 7.1. Đúng đường mạng

Gateway hoặc connector cần tới đúng endpoint quản trị. Cần xác định nguồn kết nối, đích, cổng, giao thức, đường trả về và các cơ chế phân tách mạng liên quan.

Không chỉ kiểm tra “có kết nối TCP”. Kết nối được chưa chứng minh đăng nhập thành công, đủ quyền hoặc đúng thiết bị.

Nếu kết nối đi qua NAT, load balancer hoặc endpoint cụm, phải hiểu thiết bị thật nào xử lý phiên và cách log biểu diễn nguồn truy cập.

### 7.2. Xác minh danh tính thiết bị

Với SSH, cần quản lý trust của host key. Với HTTPS, cần xác minh danh tính máy chủ và chuỗi tin cậy phù hợp.

Thông tin trust ban đầu nên được đối chiếu qua nguồn đáng tin cậy. Không tự chấp nhận bất kỳ khóa mới hoặc chứng thư bất kỳ nào chỉ để hoàn thành onboarding.

Thay đổi host key hoặc chứng thư có thể hợp lệ do thay node, nâng cấp hoặc rotation, nhưng vẫn cần được xác minh. Bỏ qua cảnh báo làm mất khả năng phát hiện kết nối nhầm đích.

### 7.3. Tách lỗi trust khỏi lỗi credential

Nếu kiểm tra danh tính máy chủ thất bại, không nên tiếp tục gửi credential rồi diễn giải kết quả như lỗi đăng nhập.

Cần phân loại ít nhất:

~~~text
Không tới được endpoint
Không xác minh được máy chủ
Không xác thực được tài khoản
Xác thực được nhưng thiếu quyền
Connector không hiểu luồng hoặc phản hồi
Lệnh thành công nhưng chưa rõ trạng thái cuối
~~~

Phân loại đúng giúp tránh rotation hoặc reset credential không cần thiết.

## 8. Đăng ký đối tượng và credential vào vault

Một hồ sơ onboard có thể biểu diễn:

~~~yaml
asset:
  asset_id: net-edge-firewall-prod
  environment: production
  management_model: two-node-cluster
  owner_team: network-operations

managed_account:
  account_id: local-pam-maintenance
  identity_source: device-local
  intended_role: approved-maintenance-role
  credential_reference: vault-object-017
  shared_across_devices: false

access:
  preferred_path: pam-gateway
  protocol: ssh
  target_scope: approved-management-endpoints
  secret_export: restricted-by-policy

lifecycle:
  rotation_state: pending-validation
  recovery_path_state: verified-for-defined-scenarios
  onboarding_state: registered
~~~

Đây là dữ liệu logic minh họa. Không chứa password, private key hoặc token thật; không phải file cấu hình để chạy trực tiếp.

Các điểm cần giữ rõ:

- Credential reference là tham chiếu quản lý, không phải giá trị secret.
- Một đối tượng vault không chứng minh credential đã được xác thực tại đích.
- Trạng thái registered chưa tương đương ready-for-production.
- Phạm vi tài khoản phải chỉ ra credential thuộc từng node, cả cụm hay một nguồn tập trung.
- Quyền xem metadata, dùng credential và xuất secret nên được phân biệt.

Credential ban đầu cần được đưa vào bằng cơ chế bảo mật phù hợp. Không sao chép vào ticket, chat, bảng kiểm công khai hoặc ảnh chụp dùng làm bằng chứng.

## 9. Xác minh connector trước khi bật tự động hóa

Thiết bị mạng có thể có nhiều chế độ CLI, dấu nhắc, bước xác thực, cơ chế phân trang hoặc quy trình xác nhận. Connector phải xử lý đúng luồng được dùng.

Cần xác minh:

| Khả năng | Câu hỏi kiểm tra |
|---|---|
| Đăng nhập | Có tới đúng node và tài khoản không? |
| Nhận diện chế độ | Connector biết đang ở mức quyền nào không? |
| Nâng quyền | Có quản lý đúng secret và bước chuyển quyền nếu cần không? |
| Thực hiện tác vụ | Hành động có đúng cú pháp, phạm vi và quyền không? |
| Đọc phản hồi | Có phân biệt lỗi, cảnh báo và thành công không? |
| Kết thúc | Có đóng phiên và lưu kết quả cần thiết không? |
| Rotation | Có đổi và xác minh credential đúng nguồn không? |
| Phục hồi trạng thái không xác định | Có đối soát trước khi thử lại không? |

Một connector đăng nhập được nhưng không nhận diện đúng chế độ cấu hình có thể thực hiện nhầm hoặc kết luận sai kết quả.

Nếu thiết bị có banner, thay đổi ngôn ngữ, xác thực nhiều bước hoặc phản hồi khác theo phiên bản, cần kiểm tra tác động trong phạm vi hỗ trợ. Không mở rộng quyền tài khoản chỉ để che lỗi connector.

Các bước kiểm tra ban đầu nên dùng hành động ít tác động, có mục đích rõ. Một lệnh chỉ đọc vẫn có thể hiển thị secret hoặc cấu hình nhạy cảm; bằng chứng và log cần được xử lý phù hợp.

## 10. Quy trình đưa một đường CLI vào PAM

### Bước 1: Đối chiếu đối tượng

Xác minh asset, endpoint, node, tài khoản và nguồn credential. Đảm bảo không đưa nhầm tài khoản tập trung vào quy trình rotation local.

### Bước 2: Chuẩn bị phương án phục hồi

Kiểm tra đường console hoặc ngoài băng trong phạm vi cần thiết, người có quyền sử dụng và cách lấy credential khẩn cấp. Xác định những phụ thuộc có thể cùng hỏng.

### Bước 3: Kiểm tra credential hiện tại có giới hạn

Thực hiện kiểm tra được kiểm soát để tránh gây khóa tài khoản do thử lặp. Khi thất bại, phân loại lỗi trước khi thử lại.

### Bước 4: Mở phiên qua PAM

Xác minh danh tính người yêu cầu, điều kiện phê duyệt nếu có và tập tài nguyên được phép. Kiểm tra gateway tới đúng thiết bị.

### Bước 5: Kiểm tra quyền tại đích

Thực hiện tác vụ đại diện cho role. Kiểm tra các giới hạn bằng phương pháp phù hợp, tránh tạo thay đổi nguy hiểm chỉ để chứng minh bị từ chối.

### Bước 6: Kiểm tra bằng chứng

Đối chiếu người dùng PAM, tài khoản tại thiết bị, thời gian, định danh phiên và log liên quan. Làm rõ phần nào được ghi lại, phần nào không.

### Bước 7: Kiểm tra rotation theo kế hoạch

Đổi credential trong phạm vi đã chuẩn bị, xác minh đăng nhập mới và cập nhật các consumer cần thiết. Xử lý việc lưu cấu hình và đồng bộ theo mô hình thiết bị.

### Bước 8: Thu hẹp đường truy cập cũ

Sau khi đường mới đạt yêu cầu, xử lý quyền hoặc đường trực tiếp theo chính sách. Giữ đường khẩn cấp có kiểm soát thay vì để mọi đường cũ tiếp tục hoạt động không giới hạn.

### Bước 9: Nghiệm thu và bàn giao

Ghi rõ tài khoản, đường truy cập, chức năng đã xác minh, giới hạn còn lại, lịch rotation và người nhận cảnh báo.

Không chuyển sang bước tiếp theo chỉ vì một thao tác trả về mã thành công. Cần bằng chứng phù hợp với điều đang tuyên bố, như đăng nhập mới sau rotation hoặc trạng thái quyền đọc lại tại đích.

## 11. Phối hợp với AAA và directory

### 11.1. Thiết bị có thể thấy danh tính khác với PAM

Nếu gateway dùng một tài khoản local chung, thiết bị có thể chỉ thấy tài khoản đó. Việc quy trách nhiệm cá nhân cần dựa vào ánh xạ phiên PAM và bằng chứng liên quan.

Nếu danh tính cá nhân được truyền tới AAA hoặc thiết bị, cần xác minh đúng chủ thể và thuộc tính quyền thực tế. Không chỉ nhìn tên hiển thị trong giao diện PAM.

### 11.2. Kiểm tra riêng xác thực, quyền và accounting

Một bộ kiểm chứng nên phân biệt:

- Người dùng hợp lệ, đủ quyền.
- Người dùng hợp lệ, không có quyền trên thiết bị này.
- Tài khoản đã bị ngừng hiệu lực.
- Role không được phép thực hiện hành động nhạy cảm.
- Accounting không tới được nơi thu thập.
- Nguồn AAA tạm thời không sẵn sàng.

Kết quả mong đợi cần dựa trên chính sách và khả năng nền tảng. Không giả định một lỗi accounting luôn chặn truy cập hoặc luôn được phép bỏ qua.

### 11.3. Fallback phải được hiểu theo tình huống

Thiết bị có thể xử lý khác nhau khi AAA từ chối người dùng và khi không liên lạc được AAA. Thứ tự phương thức, điều kiện chuyển tiếp và ảnh hưởng tới tài khoản local phụ thuộc triển khai.

Cần kiểm tra hành vi thực tế theo thiết kế. Không mặc định rằng cấu hình “AAA rồi local” luôn cho phép cứu hộ khi cần hoặc luôn từ chối đúng trường hợp.

Một tài khoản local trùng tên tài khoản tập trung có thể làm việc phân tích luồng khó hơn. Cần biết danh tính nào đã được dùng và nguồn nào quyết định quyền.

### 11.4. Gỡ nhóm không tự xử lý mọi phiên

Khi một người bị gỡ quyền trong directory hoặc AAA, PAM cần ngừng cấp truy cập mới theo chính sách. Các phiên đã mở, credential đã xuất và quyền được cache có thể cần cơ chế xử lý riêng.

Bằng chứng thu hồi phải đi tới điểm thực thi, không dừng ở việc nhóm nguồn đã thay đổi.

## 12. Least privilege, JIT và JEA cho thiết bị mạng

### 12.1. Tách nhu cầu chẩn đoán và thay đổi

Người xem trạng thái đường truyền không nhất thiết cần quyền sửa ACL, thay định tuyến hoặc quản lý tài khoản.

Một mô hình role có thể phân biệt:

| Nhu cầu | Phạm vi cần xem xét |
|---|---|
| Theo dõi và chẩn đoán | Trạng thái, thông tin vận hành được cho phép |
| Backup cấu hình | Đọc phần cấu hình cần thiết và bảo vệ dữ liệu xuất |
| Thay đổi cấu hình | Tài nguyên, tác vụ, thời gian và điều kiện triển khai |
| Quản trị tài khoản | Tạo, sửa, thu hồi danh tính và credential |
| Phục hồi khẩn cấp | Phạm vi đặc biệt, bằng chứng và rà soát sau sự kiện |

Tên role không chứng minh quyền hiệu lực. Cần kiểm tra tại đích và xét những lệnh hoặc API có thể dẫn tới hành động rộng hơn.

### 12.2. JIT phải có giới hạn thực thi

Giới hạn cửa sổ mở phiên có thể giảm thời gian truy cập qua gateway. Tuy nhiên, một tài khoản local luôn có quyền quản trị vẫn là quyền nền thường trực nếu còn có thể dùng ngoài cửa sổ đó.

Nếu dùng grant tạm hoặc role assignment có thời hạn, phải xác định thành phần nào thu hồi và hành vi của phiên đã được cấp.

### 12.3. JEA phụ thuộc năng lực nền tảng

Một số hệ thống hỗ trợ giới hạn lệnh, role hoặc tác vụ; một số khác chỉ có các mức quyền rộng. Khi không thể thu hẹp theo tác vụ, cần giữ rõ giới hạn và cân nhắc đường thực hiện khác.

Không gọi việc ghi hình phiên là thay thế cho giới hạn hành động. Ghi hình hỗ trợ phát hiện và điều tra; nó không tự ngăn một cấu hình gây gián đoạn.

## 13. Onboard API, khóa SSH và tự động hóa

### 13.1. API là đường đặc quyền riêng

Onboard CLI không tự quản lý token API. Cần kiểm kê từng token hoặc danh tính tích hợp, scope, owner, consumer, thời hạn và cách thu hồi.

Nếu API dùng HTTPS, cần xác minh danh tính máy chủ. Nếu token được gửi qua header, phải bảo đảm proxy, trace và log không ghi nguyên giá trị.

### 13.2. Khóa SSH có hai phía cần quản lý

Đối với xác thực bằng khóa của client:

- Private key cần được bảo vệ và giới hạn chủ thể có thể dùng.
- Public key hoặc cơ chế tin cậy tương ứng tại đích cần được kiểm kê.
- Thu hồi phải làm mất hiệu lực đường xác thực tại đích.
- Việc thay private key trong vault chưa tự xóa public key cũ trên thiết bị.

Nếu nền tảng dùng chứng thư ngắn hạn, cần hiểu thời hạn, nguồn ký và khả năng thu hồi. Không mặc định một lease tại PAM đã được thiết bị thực thi.

### 13.3. Tự động hóa cần danh tính và credential riêng

Tác vụ backup hoặc triển khai không nên dùng credential của quản trị viên cá nhân chỉ vì có sẵn.

Cần tách theo nhu cầu, giới hạn quyền và quản lý cách lấy secret. Nếu phải trả credential cho workload, phải đánh giá nơi lưu, cache, log và bản sao.

Khi nhiều consumer cùng dùng một credential, rotation cần được phối hợp. Phân tách tài khoản theo chức năng thường giúp giảm phạm vi ảnh hưởng, nhưng phải phù hợp khả năng thiết bị và vận hành.

## 14. Rotation credential mà không làm mất quyền quản trị

### 14.1. Hiểu đúng đối tượng bị thay

Trước khi rotation, phải xác định:

~~~text
Credential thuộc:
  tài khoản local của một node?
  tài khoản dùng chung của cụm?
  tài khoản được xác thực ở AAA?
  secret nâng quyền?
  token của controller?
  credential của một tác vụ tự động hóa?
~~~

Thay sai nguồn có thể không đổi credential cần quản lý hoặc ảnh hưởng nhiều thiết bị ngoài dự kiến.

### 14.2. Luồng rotation tham chiếu

~~~text
Xác nhận phạm vi và consumer
  → kiểm tra điều kiện phục hồi
  → chuẩn bị credential mới qua cơ chế an toàn
  → áp dụng thay đổi tại đúng nguồn
  → ghi nhận kết quả hoặc trạng thái không xác định
  → cập nhật phiên bản quản lý và consumer theo thiết kế
  → xác minh bằng kết nối mới
  → xử lý lưu bền vững và đồng bộ liên quan
  → xác nhận trạng thái cuối và bằng chứng.
~~~

Đây không phải giao dịch nguyên tử giữa thiết bị, vault và consumer. Trình tự cụ thể cần phù hợp cơ chế hỗ trợ và cách tránh mất đồng bộ.

### 14.3. Không đồng nhất phản hồi với trạng thái thực tế

Thiết bị có thể đã đổi credential nhưng kết nối bị đứt trước khi connector nhận kết quả. Nếu tự động chạy lại mà không đối soát, PAM có thể tạo thêm trạng thái lệch.

Nên phân biệt:

- Chắc chắn chưa áp dụng.
- Đã áp dụng và xác minh.
- Có thể đã áp dụng nhưng chưa xác minh.
- Vault hoặc consumer chưa đồng bộ.
- Đã khôi phục bằng quy trình được cho phép.

Trạng thái không xác định cần được xử lý theo runbook, không được đánh dấu rotation thành công chỉ vì tác vụ đã kết thúc.

### 14.4. Xác minh mới và xử lý credential cũ

Kết nối đang mở có thể tiếp tục sau khi mật khẩu đổi. Vì vậy, cần mở kết nối mới để kiểm tra credential mới theo phạm vi.

Không thử sai credential cũ hàng loạt để chứng minh hết hiệu lực nếu có thể gây khóa tài khoản hoặc ảnh hưởng thiết bị. Chọn phương pháp xác minh phù hợp khả năng nền tảng và giới hạn số lần thử.

Đổi mật khẩu không mặc nhiên đóng phiên cũ, thu hồi token khác hoặc xóa khóa SSH. Những đối tượng đó cần được xử lý riêng nếu mục tiêu là thu hồi truy cập.

## 15. Lưu cấu hình, cụm HA và controller

### 15.1. Thay đổi đang chạy khác với thay đổi bền vững

Một số thiết bị phân biệt cấu hình ứng viên, đang chạy hoặc được lưu để khởi động lại. Một số nền tảng có mô hình khác.

Cần biết thay đổi tài khoản hoặc credential được lưu ở đâu, khi nào có hiệu lực và có còn sau khởi động hoặc chuyển trạng thái không.

Không tự suy ra lệnh đổi mật khẩu đã làm mọi lớp cấu hình bền vững. Cũng không thực hiện thao tác lưu rộng nếu nó có thể đưa những thay đổi chưa được duyệt khác vào trạng thái bền vững.

### 15.2. Cụm HA cần ánh xạ node và đối tượng logic

Các câu hỏi cần trả lời:

- Credential được đồng bộ giữa các node hay quản lý riêng?
- Endpoint quản trị đi tới node active, một địa chỉ logic hay từng node?
- Thay đổi trên node nào là nguồn?
- Có thời gian trễ đồng bộ không?
- Sau failover, host key hoặc chứng thư nào được quan sát?
- Có thể kiểm tra trạng thái từng node bằng cách nào?

Không mặc định một lần rotation qua endpoint logic đã cập nhật mọi node. Nếu credential local không được đồng bộ, có thể cần đối tượng quản lý riêng.

Kiểm tra failover hoặc khởi động lại chỉ thực hiện trong kế hoạch phù hợp với ảnh hưởng dịch vụ. Khi chưa kiểm chứng được một tình huống, hồ sơ phải nêu rõ giới hạn thay vì tuyên bố đã xác nhận.

### 15.3. Controller và cấu hình mong muốn

Một controller hoặc công cụ triển khai có thể ghi lại tài khoản, khóa hoặc cấu hình AAA theo template.

Nếu PAM đổi credential cục bộ nhưng nguồn cấu hình mong muốn vẫn chứa giá trị cũ, lần triển khai sau có thể ghi đè hoặc tạo sai lệch.

Cần thống nhất nguồn có thẩm quyền, cách tham chiếu secret và trách nhiệm cập nhật. Backup cấu hình cũng cần được bảo vệ vì có thể chứa dữ liệu nhạy cảm hoặc thông tin giúp khôi phục credential.

## 16. Phục hồi, reconcile và break-glass

### 16.1. Reconcile là hành động đặc quyền

Trong bối cảnh quản lý credential, reconcile thường chỉ cơ chế đưa credential tại đích và trạng thái quản lý trở lại đồng bộ, có thể thông qua một danh tính có quyền reset.

Tài khoản reconcile phải có phạm vi, owner và điều kiện sử dụng. Không dùng một credential quản trị toàn bộ hạ tầng chỉ để đơn giản hóa mọi trường hợp lỗi.

Trước khi reset, cần biết đối tượng và consumer bị ảnh hưởng. Reset một credential tập trung có thể làm gián đoạn nhiều hệ thống.

### 16.2. Đường khẩn cấp phải giải quyết đúng điểm hỏng

Nếu PAM không hoạt động, tài khoản khẩn cấp chỉ nằm trong vault cần chính PAM để truy cập có thể không phục vụ mục tiêu phục hồi.

Nếu AAA không hoạt động, cần biết đường local hoặc console có thực sự dùng được trong tình huống đó. Nếu mạng quản trị bị lỗi, một đường console cũng đi qua cùng điểm hỏng có thể không giúp được.

Thiết kế cần chỉ ra phụ thuộc và cách tiếp cận đã được kiểm tra trong phạm vi cần thiết, cùng cơ chế bảo vệ và giám sát phù hợp.

### 16.3. Rollback dựa trên trạng thái thực tế

Rollback có thể là phục hồi cấu hình, sửa ánh xạ, điều chỉnh connector hoặc thiết lập credential thay thế. Không phải lúc nào cũng là đưa mật khẩu cũ trở lại.

Nếu credential cũ bị nghi lộ, tái sử dụng nó để khôi phục truy cập có thể khôi phục cả đường xâm nhập. Phương án xử lý cần xét nguyên nhân và rủi ro còn lại.

Sau sử dụng break-glass, cần rà soát hành động, thu hồi quyền tạm, xử lý credential đã tiết lộ và bổ sung bằng chứng. Việc khẩn cấp không biến đường truy cập thành ngoại lệ thường trực.

## 17. Bằng chứng nghiệm thu và tiêu chí hoàn thành

### 17.1. Bằng chứng theo từng tuyên bố

| Tuyên bố | Bằng chứng phù hợp |
|---|---|
| Đã đăng ký đối tượng | Hồ sơ có asset, tài khoản, owner và phạm vi |
| Đã xác minh kết nối | Đúng endpoint, danh tính máy chủ và kết quả kết nối |
| Credential dùng được | Xác thực mới tại đúng nguồn và đúng tài khoản |
| Quyền phù hợp | Kết quả kiểm tra role hoặc tác vụ đại diện tại đích |
| Phiên được kiểm soát | Yêu cầu, quyết định, phiên và danh tính được liên kết |
| Rotation hoạt động | Thay đổi, phiên bản quản lý và xác thực sau thay đổi |
| Consumer được cập nhật | Kết quả từ từng consumer trong phạm vi |
| Cụm được đồng bộ | Bằng chứng node hoặc cơ chế đồng bộ đã xác minh |
| Có khả năng phục hồi | Kết quả kiểm tra các tình huống phục hồi đã xác định |
| Đường truy cập cũ được xử lý | Cấu hình, kiểm tra hoặc ngoại lệ có owner rõ ràng |

Một ảnh chụp “account added” không chứng minh rotation, quyền hoặc phục hồi đã đạt yêu cầu.

### 17.2. Nội dung hồ sơ nghiệm thu

Có thể ghi nhận các tham chiếu:

~~~text
asset_id
node_ids_or_logical_endpoint
managed_account_id
credential_reference_and_version
access_policy_version
connector_profile_and_supported_platform
session_test_reference
rotation_test_reference
consumer_validation_references
recovery_validation_reference
remaining_exceptions
owner_and_handover_reference
~~~

Không đưa giá trị secret vào hồ sơ. Các bản ghi CLI, cấu hình hoặc video có thể chứa dữ liệu nhạy cảm nên cần quyền truy cập và cơ chế bảo vệ phù hợp.

### 17.3. Giới hạn của bằng chứng phiên

Nếu người dùng truy cập bằng tài khoản chung qua gateway, có thể liên kết người yêu cầu với phiên gateway. Tuy nhiên, một kết nối ngoài gateway dùng cùng tài khoản có thể không được quy trách nhiệm tương đương.

Cần đối chiếu log tại đích, thời gian và đường truy cập. Đồng bộ thời gian hỗ trợ tương quan, nhưng không thay thế định danh phiên hoặc bằng chứng đường kết nối.

Không tuyên bố ghi nhận mọi thao tác nếu chỉ thu thập màn hình của một giao diện trong khi API hoặc console chưa nằm trong phạm vi.

## 18. Tình huống xuyên suốt: onboard một cặp firewall

### 18.1. Hiện trạng

Một cặp firewall production có:

- Hai endpoint quản trị node và một endpoint logic.
- AAA cho quản trị viên.
- Một tài khoản local khẩn cấp.
- Một tài khoản API cho công cụ backup.
- Một công cụ điều khiển tập trung duy trì cấu hình.
- Đường console phục vụ phục hồi.

Mục tiêu là đưa phiên quản trị qua PAM, quản lý credential local, thu hẹp token backup và có bằng chứng rotation.

### 18.2. Làm rõ phạm vi trước khi cấu hình

Đội triển khai cần xác định credential local có được đồng bộ giữa hai node không, endpoint logic tới đâu và controller có ghi đè thay đổi local không.

Tài khoản API được lập hồ sơ riêng vì không đi qua phiên SSH. Role backup được đánh giá theo dữ liệu cần đọc, đồng thời bảo vệ cấu hình xuất ra.

AAA tiếp tục là một nguồn quyết định danh tính hoặc quyền theo thiết kế. PAM cần giữ ánh xạ giữa quản trị viên, phiên gateway và tài khoản tại đích.

### 18.3. Triển khai từng lớp

Một trình tự có thể là:

1. Xác minh trust và kết nối tới các endpoint đã xác định.
2. Đăng ký tài khoản và đối tượng vault đúng nguồn.
3. Thử một phiên chẩn đoán qua gateway.
4. Kiểm tra quyền, log và điều kiện phê duyệt.
5. Thử rotation local trong phạm vi được chuẩn bị.
6. Xác minh credential mới và trạng thái từng node theo mô hình.
7. Kiểm tra controller không đưa trạng thái cũ trở lại.
8. Xác minh tích hợp backup theo credential hoặc token mới.
9. Thu hẹp đường trực tiếp và bàn giao phương án khẩn cấp.

Nếu bước 6 chưa có bằng chứng cho node còn lại, hồ sơ cần giữ trạng thái chưa hoàn tất phần đó. Không suy rộng kết quả từ một node sang cả cụm.

### 18.4. Sự cố trong rotation

Giả sử tác vụ báo timeout sau bước đổi credential. Vault còn phiên bản cũ, nhưng chưa rõ thiết bị đã áp dụng thay đổi hay chưa.

Cách xử lý cần:

- Dừng retry không kiểm soát.
- Xác định node và đối tượng đã tác động.
- Dùng cơ chế xác minh hoặc phục hồi phù hợp.
- Đối soát credential tại đích với trạng thái vault.
- Cập nhật consumer trong phạm vi.
- Xác minh lại bằng kết nối mới.
- Ghi rõ khoảng không xác định và kết quả cuối.

Không đánh dấu thành công chỉ vì phiên cũ còn mở. Cũng không reset mọi tài khoản trên cả cụm khi chưa biết phạm vi lỗi.

## 19. Mở rộng ra nhiều thiết bị và giám sát sau onboarding

### 19.1. Triển khai theo nhóm có đặc điểm tương đồng

Có thể phân theo dòng thiết bị, phiên bản phần mềm, cơ chế xác thực, mô hình HA và connector.

Một profile đã hoạt động trên một thiết bị không chứng minh phù hợp cho toàn bộ đội thiết bị. Cần chọn nhóm đại diện, kiểm tra khác biệt và mở rộng có kiểm soát.

Tránh bật rotation đồng loạt cho nhiều thiết bị đang dùng cùng credential mà chưa hiểu nguồn và phụ thuộc. Sự cố có thể trở thành mất quyền quản trị diện rộng.

### 19.2. Theo dõi sai lệch

Sau onboarding, cần phát hiện:

- Tài khoản local hoặc khóa mới ngoài danh mục.
- Role bị mở rộng.
- Credential không khớp hoặc rotation thất bại.
- Controller ghi đè cấu hình quản lý.
- Đường quản trị trực tiếp mới được mở.
- Host key hoặc chứng thư thay đổi chưa được giải thích.
- Consumer tiếp tục dùng credential cũ.
- Phiên đặc quyền không có yêu cầu hoặc bằng chứng tương ứng.

Phát hiện sai lệch cần dẫn tới phân loại và xử lý, không phải tự động xóa mọi đối tượng chưa biết mà chưa hiểu ảnh hưởng.

### 19.3. Chỉ số hữu ích

| Chỉ số | Ý nghĩa |
|---|---|
| Thiết bị có owner, tài khoản và đường quản trị đã kiểm kê | Độ rõ của phạm vi quản lý |
| Tài khoản đã xác minh rotation theo nền tảng | Khả năng quản lý vòng đời credential |
| Lần rotation lỗi hoặc không xác định | Nguy cơ lệch trạng thái và gián đoạn |
| Thời gian từ thu hồi tới mất hiệu lực tại đích | Hiệu quả ứng phó |
| Phiên có liên kết yêu cầu, người dùng và tài khoản đích | Chất lượng quy trách nhiệm |
| Đường truy cập chưa qua kiểm soát đã có phương án | Phần rủi ro còn tồn tại |
| Credential được nhiều thiết bị hoặc consumer dùng chung | Phạm vi ảnh hưởng khi lộ lọt |
| Kiểm tra phục hồi còn phù hợp với cấu hình hiện tại | Khả năng xử lý khi điểm kiểm soát gặp lỗi |

Không dùng số thiết bị được thêm vào vault làm thước đo duy nhất. Con số đó chưa phản ánh quyền, phiên, rotation hay đường phục hồi.

## 20. Lỗi thường gặp và bài tập áp dụng

### 20.1. Các lỗi thường gặp

| Lỗi | Hậu quả | Cách xử lý |
|---|---|---|
| Chỉ lưu mật khẩu rồi coi đã onboard xong | Bỏ sót quyền, phiên và consumer | Nghiệm thu theo khả năng và phạm vi |
| Dùng một mật khẩu cho cả đội thiết bị | Lộ một credential ảnh hưởng diện rộng | Phân tách credential theo mô hình phù hợp |
| Rotation tài khoản AAA như tài khoản local | Sai nguồn, có thể ảnh hưởng nhiều thiết bị | Xác định nguồn credential trước khi đổi |
| Bỏ kiểm tra host key hoặc chứng thư | Có thể gửi credential tới đích giả | Quản lý trust và vòng đời thay đổi |
| Thử lại đăng nhập liên tục | Gây khóa tài khoản hoặc làm nhiễu điều tra | Phân loại lỗi và giới hạn retry |
| Kiểm tra bằng phiên cũ sau đổi mật khẩu | Không chứng minh credential mới hoạt động | Xác thực bằng kết nối mới |
| Bỏ qua consumer backup hoặc tự động hóa | Tác vụ hỏng sau rotation | Kiểm kê và xác minh consumer |
| Giả định cụm tự đồng bộ credential | Node còn credential cũ hoặc mất truy cập | Kiểm tra mô hình và bằng chứng từng phạm vi |
| Controller giữ cấu hình cũ | Thay đổi của PAM bị ghi đè | Thống nhất nguồn cấu hình có thẩm quyền |
| Ghi hình được coi là ngăn mọi hành động | Quyền tại đích vẫn quá rộng | Giới hạn role và tác vụ tại điểm thực thi |
| Tài khoản khẩn cấp phụ thuộc cùng điểm hỏng | Không phục hồi được khi cần | Thiết kế đường phục hồi theo tình huống |
| Báo thành công khi kết quả rotation chưa rõ | Vault và thiết bị có thể lệch | Đối soát và xác nhận trạng thái cuối |

### 20.2. Bài tập

Một đội chuẩn bị onboard 40 switch. Tất cả dùng cùng tài khoản local. Công cụ backup giữ mật khẩu trong cấu hình riêng. Connector đăng nhập thành công trên một switch, và đội muốn bật rotation đồng loạt. Chưa xác định switch nào được controller quản lý; chưa kiểm tra console; chưa biết thay mật khẩu có được lưu bền vững không.

Hãy trả lời:

1. Kết quả đăng nhập thành công đã chứng minh điều gì?
2. Những phụ thuộc nào có thể khiến rotation ảnh hưởng nhiều thiết bị?
3. Vì sao không thể suy rộng từ một switch sang cả nhóm?
4. Cần phân biệt những trạng thái nào khi rotation timeout?
5. Những bằng chứng nào cần có trước khi nghiệm thu?
6. Có thể chia triển khai thành những bước nhỏ nào?

Hướng phân tích:

- Đăng nhập thành công chỉ chứng minh một đường xác thực trong điều kiện đã thử, chưa chứng minh rotation hoặc phục hồi.
- Credential dùng chung, công cụ backup và controller có thể tạo phụ thuộc hoặc ghi đè.
- Dòng thiết bị, phiên bản, chế độ quản lý và mô hình lưu cấu hình có thể khác nhau.
- Cần phân biệt chưa áp dụng, đã áp dụng, không xác định và chưa đồng bộ consumer.
- Cần bằng chứng đúng nguồn credential, quyền, kết nối mới, vòng đời, consumer và đường phục hồi.
- Nên kiểm kê, chọn nhóm đại diện, xác minh từng khả năng rồi mở rộng theo phạm vi đã hiểu.

## 21. Các điểm cần nắm

Onboard thiết bị mạng vào PAM là quản lý một chuỗi truy cập đặc quyền từ danh tính người yêu cầu tới tài khoản, credential, quyền và phiên tại đích.

Một thiết bị chỉ được nghiệm thu trong phạm vi có bằng chứng. Lưu secret, đăng nhập được, rotation thành công, đồng bộ cụm và phục hồi được là những khả năng khác nhau cần được xác minh riêng.

Khi thiết kế hoặc vận hành, hãy lần theo từng đường quản trị và từng consumer. Mỗi đối tượng cần có owner, cơ chế thực thi, vòng đời và bằng chứng trạng thái cuối phù hợp.
