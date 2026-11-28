# Entitlement theo action — Cấp quyền theo hành động trong PAM

## 1. Từ “được vào hệ thống” đến “được thực hiện việc gì”

Trong quản lý truy cập đặc quyền (Privileged Access Management — PAM), việc cho phép một người mở phiên trên máy chủ không trả lời đầy đủ câu hỏi người đó được làm gì sau khi kết nối.

Một kỹ sư có thể cần xem trạng thái và khởi động lại một dịch vụ. Nếu chỉ có hai lựa chọn “không truy cập” và “administrator”, tổ chức dễ cấp nhiều quyền hơn nhu cầu công việc.

**Entitlement theo action** là cách biểu diễn và cấp quyền dựa trên hành động cụ thể, gắn với tài nguyên và các điều kiện áp dụng. Thay vì chỉ nói “người này là quản trị viên”, hệ thống có thể nói:

~~~text
Người thao tác: engineer-17
Hành động: service.restart
Tài nguyên: dịch vụ payments-api trên một instance production cụ thể
Thời gian: trong cửa sổ đã được duyệt
Điều kiện: qua PAM, đủ xác thực, có phê duyệt còn hiệu lực
~~~

Một entitlement có thể được hiểu là quyền được gán cho chủ thể hoặc quyền đủ điều kiện để kích hoạt theo chính sách. Cần phân biệt quyền đang có hiệu lực với quyền mới chỉ đủ điều kiện yêu cầu.

Trong bài học này, một entitlement theo action gồm ít nhất:

- Chủ thể hoặc nhóm chủ thể.
- Hành động được phép.
- Tài nguyên thuộc phạm vi.
- Điều kiện kích hoạt và thực thi.
- Thời hạn hoặc vòng đời.
- Nguồn thẩm quyền và bằng chứng liên quan.

Mục tiêu là đưa least privilege vào thao tác thực tế: cấp đúng khả năng cần dùng, trong thời gian cần dùng, và kiểm chứng được rằng các khả năng khác không được cấp ngoài ý muốn.

## 2. Action không chỉ là tên một nút hoặc câu lệnh

### 2.1. Action là khả năng có ý nghĩa

Một action cần có ý nghĩa rõ trong miền quản trị. Ví dụ:

| Action minh họa | Ý nghĩa dự kiến |
|---|---|
| service.status.read | Xem trạng thái của dịch vụ thuộc phạm vi |
| service.restart | Khởi động lại một dịch vụ được chỉ định |
| service.config.update | Thay đổi cấu hình dịch vụ theo hợp đồng đã định nghĩa |
| secret.metadata.read | Xem metadata được phép của secret |
| secret.value.read | Đọc giá trị secret |
| credential.checkout | Nhận credential theo một yêu cầu |
| session.open | Mở một loại phiên truy cập |
| iam.role.assign | Gán một role theo phạm vi quản trị |
| audit.events.read | Đọc bằng chứng hoạt động được phép |

Các tên trên là ví dụ thiết kế, không phải bộ action chuẩn cho mọi sản phẩm.

Đọc metadata secret khác với đọc giá trị secret. Mở phiên khác với quyền thay đổi IAM. Được restart dịch vụ khác với được chỉnh file mà dịch vụ sẽ thực thi.

### 2.2. HTTP method không đủ diễn tả quyền

Cùng một phương thức POST có thể tạo yêu cầu, restart dịch vụ, xuất dữ liệu hoặc thay đổi chính sách. Quy tắc “được POST” không đủ để giới hạn thao tác đặc quyền.

Ngược lại, cùng một khả năng có thể xuất hiện qua nhiều đường:

- Nút trên portal.
- API.
- CLI.
- Tác vụ tự động.
- Một endpoint cũ.
- Đường quản trị trực tiếp.

Mọi đường thuộc phạm vi phải được ánh xạ về quyền tương ứng và kiểm tra ở điểm thực thi. Ẩn nút trên giao diện không ngăn được một lời gọi API trực tiếp.

### 2.3. Action quá rộng làm mất mục tiêu giới hạn quyền

Các tên như execute, manage hoặc admin thường che giấu nhiều khả năng khác nhau. Chúng có thể vẫn cần tồn tại ở một số cấp quản trị, nhưng không nên được dùng như lời giải mặc định cho mọi nhu cầu.

Ví dụ, action execute-command nhận chuỗi lệnh tùy ý có thể tương đương một shell có quyền cao. Đặt tên nó là “maintenance” không làm giảm quyền thực tế.

Một action tốt cần mô tả:

- Đầu vào được chấp nhận.
- Tài nguyên được tác động.
- Tác dụng chính và tác dụng phụ quan trọng.
- Dữ liệu được trả về.
- Danh tính thực thi ở backend.
- Hạn chế và điều kiện.
- Cách ghi nhận và xử lý lỗi.

## 3. Mô hình subject–action–resource–condition

Một quyết định có thể biểu diễn khái niệm như sau:

~~~text
Chủ thể S có được thực hiện hành động A
trên tài nguyên R
với tham số P
trong ngữ cảnh C hay không?
~~~

### 3.1. Subject: ai thực sự thao tác?

Subject phải được lấy từ danh tính đã xác thực hoặc một quan hệ ủy quyền đáng tin cậy. Không lấy tên người dùng tùy ý từ request rồi dùng làm cơ sở cấp quyền.

Cần phân biệt:

- Người gửi yêu cầu.
- Người trực tiếp thao tác.
- Workload thực thi.
- Tài khoản kỹ thuật trên hệ thống đích.
- Người phê duyệt.

Nếu một dịch vụ thao tác thay người dùng, phải giữ cả danh tính người khởi tạo và danh tính thực thi. Không chỉ kiểm tra rằng dịch vụ có quyền rộng rồi cho nó làm mọi việc theo tham số client.

### 3.2. Resource: đối tượng cụ thể nào?

Tài nguyên có thể là máy chủ, dịch vụ, tài khoản, secret, cơ sở dữ liệu hoặc một đối tượng quản trị.

Nên dùng định danh ổn định và phân giải phía máy chủ. Tên hiển thị hoặc nhãn dễ sửa không nên tự quyết định toàn bộ phạm vi.

Ví dụ, quyền restart trên dịch vụ A không tự áp dụng cho:

- Dịch vụ B trên cùng máy.
- Bản production khi chỉ được duyệt cho staging.
- Tất cả dịch vụ có tên tương tự.
- Một nhóm đích mới được thêm sau phê duyệt.

Nếu dùng nhóm tài nguyên động, chính sách phải quy định ranh giới và cách đánh giá thay đổi. Không để việc thêm nhãn tài nguyên trở thành đường mở rộng quyền ngoài ý định phê duyệt.

### 3.3. Parameters: hành động được thực hiện theo cách nào?

Một action hẹp vẫn có thể trở nên rộng nếu tham số không bị giới hạn.

Ví dụ:

- Restart một dịch vụ hay toàn bộ nhóm dịch vụ?
- Đọc một khoảng log hay xuất tất cả dữ liệu?
- Cập nhật trường cấu hình được phép hay thay toàn bộ file?
- Gán một role cố định hay role tùy ý do người gọi chọn?
- Thao tác trên một object đã phân giải hay một đường dẫn có thể trỏ sang object khác?

Tham số có ảnh hưởng quyền phải được kiểm tra cùng quyết định. Không kiểm tra action trên một đối tượng rồi thực thi với tham số đã bị thay đổi sau đó.

### 3.4. Conditions: trong hoàn cảnh nào?

Các điều kiện có thể gồm:

- Phê duyệt đúng phạm vi và phiên bản.
- Cửa sổ truy cập đang mở.
- Mức xác thực và độ mới phù hợp.
- Thiết bị hoặc đường truy cập đáp ứng chính sách.
- Principal còn hoạt động.
- Mức rủi ro chưa vượt điều kiện cho phép.
- Giới hạn số lần hoặc khối lượng thao tác.
- Ghi nhận bắt buộc có khả năng thực hiện.

Không nên dùng điều kiện không thể quan sát hoặc không có điểm thực thi mà vẫn tuyên bố quyền đã bị giới hạn theo điều kiện đó.

## 4. Không trộn action và resource thành một tích quyền rộng hơn

Một lỗi thiết kế quan trọng là hợp nhất riêng tập action và tập resource, rồi cho phép mọi kết hợp giữa chúng.

Giả sử một người có:

~~~text
Grant 1: service.restart trên dịch vụ A
Grant 2: service.status.read trên dịch vụ B
~~~

Quyền hợp lệ là hai cặp đã nêu. Nó không bao gồm service.restart trên dịch vụ B.

Nếu hệ thống lấy:

~~~text
Actions = {service.restart, service.status.read}
Resources = {A, B}
~~~

rồi cho mọi action chạy trên mọi resource, nó đã tự tạo thêm quyền.

Phải giữ quan hệ đầy đủ giữa action, tài nguyên và điều kiện trong từng grant.

Một mô hình đánh giá khái niệm:

~~~text
Có ít nhất một grant đang hiệu lực
    khớp subject
    VÀ khớp action
    VÀ khớp resource
    VÀ đáp ứng điều kiện của chính grant đó

Đồng thời:
    đáp ứng các ràng buộc bắt buộc chung
    VÀ không bị một quy tắc từ chối có hiệu lực chặn
~~~

Cách kết hợp allow và deny phải được định nghĩa rõ trong hệ thống. Ví dụ bài học dùng mô hình ưu tiên quy tắc từ chối áp dụng; không nên giả định mọi sản phẩm có cùng cách kết hợp chính sách.

Không có grant khớp thì từ chối theo mô hình mặc định. Một action không được biết đến cũng không nên rơi vào nhánh cho phép chung.

## 5. Quan hệ với RBAC, ABAC, JIT và JEA

### 5.1. RBAC tổ chức các quyền, action mô tả khả năng

Role có thể là một tập entitlement:

~~~text
Role: service-operator
    → service.status.read trên tập dịch vụ được giao
    → service.restart trên tập dịch vụ được phép bảo trì
~~~

Action-based entitlement không buộc phải bỏ RBAC. Nó làm rõ nội dung thực tế của role.

Cần tránh một role tên nhẹ nhưng chứa quyền quá rộng. Người duyệt nên hiểu một role có thể làm gì, không chỉ nhìn tên “operator” hoặc “support”.

### 5.2. ABAC bổ sung điều kiện

Chính sách theo thuộc tính có thể giới hạn action theo môi trường, đơn vị sở hữu, loại dữ liệu hoặc trạng thái thiết bị.

Thuộc tính phải đến từ nguồn có thẩm quyền. Nếu người yêu cầu tự sửa được thuộc tính environment hoặc owner của tài nguyên, cần kiểm soát để họ không tự đưa tài nguyên vào phạm vi được phép.

Thiếu một thuộc tính bắt buộc không nên được diễn giải thành “không có giới hạn”.

### 5.3. JIT giới hạn lúc quyền có hiệu lực

Một người có thể đủ điều kiện yêu cầu service.restart nhưng chỉ được kích hoạt sau phê duyệt, trong khoảng 30 phút minh họa.

Kết thúc khoảng đó, người dùng không được tiếp tục tạo thao tác bằng grant cũ. Gia hạn phải tuân thủ chính sách, không tự xảy ra do phiên vẫn hoạt động.

Nếu action đã khởi chạy một công việc dài hạn, vòng đời công việc cần được quản lý riêng. Hết quyền tương tác không tự có nghĩa mọi tác vụ đã dừng.

### 5.4. JEA giới hạn khả năng thực thi

JEA hướng tới chỉ cho người dùng thực hiện phần quản trị cần thiết. Action-based entitlement cung cấp cách diễn đạt khả năng đó, nhưng phải có một cơ chế thực thi tương ứng.

Ví dụ:

- Tác vụ restart được đóng gói.
- API có hành động và tham số giới hạn.
- Endpoint quản trị hạn chế.
- Cơ chế điều khiển quyền trên hệ thống đích.

Nếu PAM chỉ mở một shell toàn quyền rồi ghi trên giao diện “chỉ được restart”, đó là giới hạn về kỳ vọng, chưa phải giới hạn kỹ thuật tương đương.

## 6. Thiết kế danh mục action có thể quản trị

### 6.1. Định nghĩa hợp đồng cho mỗi action

Một bản mô tả action nên có:

| Thành phần | Ví dụ cho service.restart |
|---|---|
| Mục đích | Khởi động lại đúng dịch vụ được duyệt |
| Loại tài nguyên | Instance dịch vụ đã được đăng ký |
| Đầu vào | Định danh dịch vụ, tùy chọn nằm trong tập cho phép |
| Phạm vi tác động | Một instance hoặc phạm vi được khai báo rõ |
| Dữ liệu trả về | Trạng thái thao tác, không trả credential |
| Backend thực thi | Adapter hoặc runner được quản trị |
| Điều kiện | Quyền, phê duyệt, cửa sổ và xác thực |
| Bằng chứng | Ai, grant nào, đích nào, đầu vào nào, kết quả gì |
| Xử lý lỗi | Phân biệt từ chối, chưa chạy, đang chạy và kết quả chưa xác định |

Một action có thể cần nhiều bước nội bộ, chẳng hạn dừng và khởi động lại một dịch vụ. Hợp đồng phải mô tả hành vi đó. Người dùng không vì được gọi action mà được quyền tùy ý gọi mọi thao tác nội bộ của runner.

### 6.2. Không coi mọi action đọc là ít rủi ro

Đọc giá trị secret, log có dữ liệu nhạy cảm hoặc bản sao lưu có thể tạo ảnh hưởng lớn dù không sửa trạng thái hệ thống.

Cần phân biệt:

- Metadata với nội dung.
- Trạng thái vận hành với log chi tiết.
- Dữ liệu tổng hợp với dữ liệu định danh.
- Một object với thao tác liệt kê hoặc xuất hàng loạt.

Quyền đọc cũng cần phạm vi, điều kiện và giám sát phù hợp.

### 6.3. Action có thể tạo đường leo thang gián tiếp

Quyền sửa script mà một dịch vụ đặc quyền sẽ chạy có thể tạo khả năng lớn hơn tên “sửa file” gợi ý. Quyền gán role hoặc sửa chính sách có thể dẫn đến tự cấp thêm quyền.

Khi thiết kế cần xem xét tác dụng kết hợp, không chỉ từng action riêng lẻ.

Ví dụ, một người được restart dịch vụ và được sửa tùy ý mã hoặc cấu hình thực thi của dịch vụ đó có thể có khả năng thực thi dưới danh tính của dịch vụ. Cần đánh giá cặp quyền này thay vì kết luận restart tự nó luôn an toàn.

Các action quản trị chính sách, danh mục action và ánh xạ quyền cần được kiểm soát đặc biệt vì chúng quyết định ý nghĩa của các entitlement khác.

### 6.4. Quản lý phiên bản ngữ nghĩa

Nếu action service.restart ban đầu chỉ tác động một instance nhưng sau đó được sửa thành restart cả cụm, các phê duyệt cũ có thể không còn phản ánh đúng tác động.

Cần quản lý:

- Phiên bản action hoặc hợp đồng thực thi.
- Chủ sở hữu định nghĩa.
- Người được thay đổi ánh xạ backend.
- Kiểm thử tác động đến policy và phê duyệt.
- Cách chuyển đổi grant đang tồn tại.

Không thay nội dung một action dưới cùng một tên rồi mặc định mọi người đã chấp thuận khả năng mới.

## 7. Ví dụ: cấp quyền restart một dịch vụ production

### 7.1. Yêu cầu có cấu trúc

Một yêu cầu minh họa:

~~~json
{
  "request_id": "PAM-REQ-3105",
  "action": "service.restart",
  "resource_id": "svc-prod-payments-02",
  "parameters": {
    "strategy": "graceful"
  },
  "reason_reference": "INC-3105"
}
~~~

Đây không phải API của một sản phẩm. Strategy chỉ hợp lệ nếu adapter được thiết kế hỗ trợ giá trị đó với hành vi rõ ràng.

Backend phải tự phân giải resource_id sang đối tượng được quản trị. Người gọi không được tự chọn một đường dẫn chương trình, tài khoản thực thi hoặc một chuỗi lệnh thay thế.

### 7.2. Phạm vi phê duyệt

Chủ hệ thống đồng ý:

~~~text
Người thực hiện: engineer-17
Action: service.restart
Action contract: phiên bản đã định nghĩa
Resource: svc-prod-payments-02
Tham số được phép: strategy = graceful
Khoảng hiệu lực: cửa sổ được duyệt
Đường thực thi: runner PAM được quản lý
Không bao gồm: sửa cấu hình, đọc secret, mở shell quản trị
~~~

Phê duyệt phải gắn với phiên bản yêu cầu. Nếu resource hoặc action đổi, không được tái sử dụng quyết định cũ ngoài quy tắc đã định nghĩa.

### 7.3. Chính sách minh họa

~~~yaml
action_entitlement:
  id: "grant-example-3105"
  subject: "engineer-17"
  action: "service.restart"
  action_contract_version: "1"

  resource:
    id: "svc-prod-payments-02"
    environment: "production"

  parameter_constraints:
    strategy:
      allowed_values:
        - "graceful"

  activation:
    request_reference: "PAM-REQ-3105"
    current_approval_required: true
    approved_window_required: true
    suitable_authentication_required: true

  enforcement:
    route: "managed-service-runner"
    arbitrary_shell_input: false
    arbitrary_execution_identity: false

  evidence:
    record_decision_and_execution: true
    exclude_reusable_credentials: true
~~~

Cấu hình chỉ diễn tả ý định. Từng ràng buộc phải được chuyển thành kiểm tra và thực thi có hiệu lực.

### 7.4. Các thao tác vẫn phải bị từ chối

Có grant trên không đồng nghĩa được:

- Restart một dịch vụ khác.
- Restart toàn bộ cụm.
- Thay strategy bằng giá trị không được chấp nhận.
- Gọi service.config.update.
- Checkout mật khẩu tài khoản runner.
- Mở shell dưới tài khoản kỹ thuật.
- Dùng lại grant sau cửa sổ.
- Thực hiện dưới danh tính người khác.

Đó là điểm khác biệt giữa quyền theo công việc và một quyền quản trị rộng có lời nhắc sử dụng cẩn thận.

## 8. Thực thi ở backend và hệ thống đích

### 8.1. Kiểm tra trước tác dụng phụ

Luồng khái niệm:

~~~mermaid
flowchart TD
    A[Nhận yêu cầu hành động] --> B[Lấy danh tính đã xác thực]
    B --> C[Phân giải action, hợp đồng và tài nguyên]
    C --> D[Kiểm tra tham số theo schema và phạm vi]
    D --> E[Đánh giá grant, phê duyệt, thời gian và điều kiện]
    E --> F{Được phép?}
    F -- Không --> G[Từ chối và ghi quyết định]
    F -- Có --> H[Ràng buộc quyết định với thao tác đã chuẩn hóa]
    H --> I[Thực thi qua adapter được quản lý]
    I --> J[Ghi kết quả và đối soát trạng thái]
    J --> K[Kết thúc hoặc thu hồi quyền theo vòng đời]
~~~

Không thực hiện một phần thao tác rồi mới kiểm tra quyền vì “cần chạy để biết tài nguyên là gì”. Việc đọc metadata phục vụ phân giải cũng cần được thiết kế theo mức quyền và tránh lộ thông tin không cần thiết.

### 8.2. Không chỉ kiểm tra chuỗi tên lệnh

Một danh sách tên lệnh được phép có thể không đủ nếu người dùng kiểm soát tham số, đường dẫn, môi trường hoặc nội dung file được lệnh sử dụng.

Cần ưu tiên:

- Đầu vào có cấu trúc.
- Tập tham số và giá trị được giới hạn.
- Ánh xạ tài nguyên phía máy chủ.
- Adapter có hành vi xác định.
- Không ghép đầu vào tùy ý thành shell command.
- Không cho người gọi chọn một runtime hoặc chương trình thay thế.
- Kiểm soát đối tượng thực tế tại lúc thao tác.

Nếu xử lý đường dẫn hoặc tài nguyên có thể thay đổi giữa kiểm tra và sử dụng, cần cơ chế ràng buộc với đối tượng thực tế. Chỉ so sánh một chuỗi đường dẫn ban đầu chưa chắc đủ.

### 8.3. Bảo vệ danh tính runner

Runner có thể cần quyền kỹ thuật cao hơn người dùng để thực hiện tác vụ. Điều đó tạo một ranh giới tin cậy quan trọng.

Cần tránh để người dùng:

- Đọc credential của runner.
- Sửa mã hoặc cấu hình runner.
- Gọi endpoint nội bộ bỏ qua kiểm tra.
- Chọn tài khoản thực thi tùy ý.
- Sửa tham số sau khi đã có quyết định.
- Chạy trực tiếp dưới cùng tài khoản qua một đường khác.

Nếu runner bị lợi dụng để thực hiện một công việc ngoài phạm vi người gọi, hệ thống trở thành một bên có quyền bị dùng làm trung gian. Kiểm tra quyền phải giữ đúng danh tính và ý định của người khởi tạo, không chỉ nhìn quyền rộng của runner.

### 8.4. Gateway không nhìn thấy mọi hành động

Một gateway chuyển tiếp phiên có thể biết người dùng đang kết nối, nhưng không nhất thiết hiểu đầy đủ mọi hành động trong một giao thức hoặc ứng dụng.

Nếu không quan sát và kiểm soát được thao tác, không nên tuyên bố entitlement action đã được thực thi chỉ vì gateway có log phiên.

Có thể cần một API quản trị, endpoint hạn chế hoặc kiểm soát trên đích. Phải mô tả đúng mức bảo đảm thực tế và khoảng trống còn lại.

## 9. Đánh giá quyết định và tránh mở rộng quyền ngoài ý muốn

### 9.1. Mã giả cấp quyền

~~~text
authorize_action(connection, request):
    actor = require_authenticated_principal(connection)

    action = resolve_known_action_contract(request.action)
    resource = resolve_managed_resource(request.resource_id)
    parameters = normalize_and_validate(action.schema, request.parameters)

    require(actor.is_active)
    require(resource.belongs_to_expected_environment)

    grant = find_effective_grant_matching_complete_tuple(
        actor,
        action,
        resource,
        parameters
    )

    require(grant.exists)
    require(no_applicable_deny_rule(actor, action, resource))
    require(grant.conditions_are_satisfied)

    require(approval_matches_current_request_and_contract(request, action))
    require(access_window_is_open)
    require(authentication_assurance_is_sufficient)

    return bounded_decision(
        actor,
        grant,
        action.version,
        resource.stable_id,
        parameters,
        current_policy_version
    )
~~~

Mã giả thể hiện ý định, chưa phải triển khai hoàn chỉnh. Các thuộc tính có ảnh hưởng phải đến từ nguồn đáng tin cậy; không điền actor hoặc trạng thái phê duyệt bằng dữ liệu client tự khai.

### 9.2. Khoảng đua giữa quyết định và thực thi

Sau khi kiểm tra, tài nguyên, quyền hoặc yêu cầu có thể thay đổi. Cần ràng buộc quyết định với thao tác thực tế và xử lý phiên bản hoặc trạng thái khi cần.

Các cách tiếp cận có thể gồm:

- Quyết định có thời hạn ngắn và phạm vi rõ.
- Kiểm tra lại tại điểm thực thi.
- Gắn phiên bản yêu cầu, grant và action.
- Ngăn client sửa nội dung sau khi nhận quyết định.
- Thu hồi hoặc vô hiệu hóa quyết định chưa dùng khi điều kiện thay đổi.

Không có một cơ chế duy nhất phù hợp mọi hệ thống. Cần chứng minh rằng thay đổi không làm thao tác vượt ranh giới đã được cho phép.

### 9.3. Cache quyết định phải giữ đủ ngữ cảnh

Cache theo riêng tên người dùng dễ làm quyền trên một tài nguyên bị dùng nhầm cho tài nguyên khác.

Một cache, nếu có, cần phân biệt các yếu tố ảnh hưởng quyết định, chẳng hạn action, resource, môi trường, phiên bản chính sách và điều kiện. Tuổi cache và cơ chế vô hiệu hóa phải phù hợp yêu cầu thu hồi.

Không biến quyết định cho phép cũ thành quyền vô thời hạn khi dịch vụ policy không khả dụng.

### 9.4. Default deny và lỗi phụ thuộc

Nếu action không tồn tại, tham số không hợp lệ, thiếu thuộc tính bắt buộc hoặc không xác minh được điều kiện, luồng thường không nên cấp quyền mới.

Nếu cần khẩn cấp, dùng tuyến có chính sách riêng. Không ánh xạ mọi lỗi về một action admin để “đảm bảo tác vụ chạy được”.

## 10. Batch, retry và thao tác dài hạn

### 10.1. Một action trên nhiều tài nguyên

Yêu cầu restart mười dịch vụ cần đánh giá phạm vi của cả mười. Không chỉ kiểm tra phần tử đầu tiên rồi cho cả batch chạy.

Có thể chọn mô hình:

- Tất cả đều đủ quyền mới thực thi.
- Chỉ thực thi phần được phép và báo rõ phần bị từ chối.

Mô hình nào cũng cần được định nghĩa và hiển thị rõ. Không âm thầm chạy một phần khiến người vận hành tưởng cả hệ thống đã được xử lý.

Ngoài quyền trên từng tài nguyên, có thể cần giới hạn số lượng, tốc độ, thứ tự hoặc mức tác động đồng thời.

### 10.2. Giới hạn số lần thực thi

Một grant có thể cho phép một số lần thao tác theo yêu cầu. Khi có nhiều request đồng thời, bộ đếm cần được quản lý nhất quán; không để mỗi worker đọc cùng một giá trị rồi cùng cho phép.

Cần định nghĩa bộ đếm áp dụng cho lần khởi tạo, lần thành công hay một tiêu chí khác. Không để việc đổi request ID tự làm mới hạn mức của cùng grant.

### 10.3. Retry không được làm hành động lặp ngoài ý muốn

Một timeout có thể xảy ra sau khi restart đã bắt đầu. Nếu gửi lại ngay, có thể tạo thêm một lần restart.

Cần dùng định danh thao tác, đối soát trạng thái và cơ chế idempotency phù hợp. Cùng một khóa idempotency với nội dung khác phải được xử lý rõ ràng, không coi như cùng thao tác.

Idempotency không tự bảo đảm “đúng một lần” trong mọi sự cố phân tán. Những kết quả chưa xác định cần được theo dõi và đối soát, không tự báo chưa chạy rồi thử tiếp vô hạn.

### 10.4. Quyền khởi tạo khác quyền thực thi của job

Một action có thể tạo công việc kéo dài hơn thời gian người dùng còn quyền tương tác.

Thiết kế cần nêu:

- Ai được khởi tạo.
- Job chạy dưới danh tính nào.
- Phạm vi và thời hạn của job.
- Ai được xem, hủy hoặc thay đổi.
- Điều gì xảy ra khi grant của người dùng hết hạn.
- Cách thu hồi quyền hoặc credential của job.

Không dùng một job nền để giữ quyền tương tác của người dùng tồn tại ngoài cửa sổ đã duyệt.

## 11. Bằng chứng và quản trị thay đổi

### 11.1. Ghi cả quyết định và kết quả

Một log quyết định nên cho biết:

| Nhóm | Dữ liệu gợi ý |
|---|---|
| Danh tính | Người khởi tạo, principal đã xác thực, danh tính runner |
| Quyền | Grant, role hoặc nguồn thẩm quyền, phiên bản policy |
| Hành động | Action và phiên bản hợp đồng |
| Phạm vi | Định danh tài nguyên và môi trường |
| Điều kiện | Tham chiếu phê duyệt, cửa sổ, kết quả kiểm tra |
| Thực thi | Operation ID, thời điểm bắt đầu, kết quả và trạng thái chưa xác định |
| Kết thúc | Hết hạn, hủy, thu hồi và kết quả xác minh |

Không ghi secret, token hoặc credential vào tham số được lưu. Một action có dữ liệu nhạy cảm cần quy tắc che hoặc tách dữ liệu phù hợp.

Quyết định ALLOW không chứng minh thao tác đã thành công. Kết quả restart thành công cũng không tự chứng minh việc cấp quyền trước đó đúng. Cần liên kết cả hai.

### 11.2. Đối chiếu phạm vi được duyệt với thực tế

Có thể kiểm tra:

- Action đã chạy có nằm trong yêu cầu được duyệt không?
- Tài nguyên thực tế có đúng định danh không?
- Tham số có nằm trong giới hạn không?
- Runner có dùng một tài khoản hoặc đường truy cập khác không?
- Có thao tác sau hết hạn không?
- Có quyền hoặc credential tồn tại sau khi công việc kết thúc không?

Các sai lệch cần được xử lý theo mức độ, không chỉ ghi thành một cảnh báo rồi bỏ qua.

### 11.3. Quản trị các quyền có thể sửa quyền

Người được sửa danh mục action, policy, resource mapping hoặc runner có thể làm thay đổi khả năng của nhiều người.

Các thay đổi này nên có:

- Phân công thẩm quyền rõ.
- Tách biệt nhiệm vụ khi yêu cầu.
- Kiểm tra tác động.
- Phiên bản và lịch sử.
- Khả năng khôi phục.
- Giám sát việc tự mở rộng quyền.

Một chính sách action chi tiết không giúp nhiều nếu người dùng có thể tự đổi ánh xạ của action sang một tác vụ toàn quyền.

## 12. Tình huống: hỗ trợ vận hành không cần quyền full admin

Đội hỗ trợ cần xử lý dịch vụ không phản hồi. Trước đây, mỗi người được thêm vào nhóm quản trị máy chủ để có thể restart.

Khi chuyển sang entitlement theo action:

1. Chủ hệ thống xác định nhóm cần xem trạng thái và restart một số dịch vụ.
2. Danh mục tách service.status.read, service.restart và service.config.update.
3. Role hỗ trợ chỉ chứa các grant phù hợp trên những dịch vụ được giao.
4. Quyền restart production yêu cầu kích hoạt JIT và phê duyệt.
5. Backend chỉ chấp nhận định danh dịch vụ và tham số đã định nghĩa.
6. Runner thực hiện tác vụ giới hạn; người dùng không nhận credential của runner.
7. Mọi quyết định được liên kết với thao tác thực tế.
8. Quyền kích hoạt kết thúc theo cửa sổ, và các kết quả chưa xác định được đối soát.

Trong một ca xử lý, kỹ sư phát hiện cần sửa cấu hình. Họ không được dùng action restart để chèn một thao tác cấu hình khác. Yêu cầu mới cần phạm vi và quyết định tương ứng.

Nếu kiến trúc vẫn cho kỹ sư đăng nhập trực tiếp bằng tài khoản full admin trên cùng máy, ranh giới action chưa bao phủ đường đó. Tổ chức cần xử lý đường truy cập liên quan hoặc ghi rõ giới hạn, không chỉ triển khai một portal đẹp hơn.

Kết quả mong muốn là đội hỗ trợ làm được công việc cần thiết mà không phải giữ quyền quản trị rộng cho mọi tình huống.

## 13. Kiểm chứng trước khi triển khai

Kiểm thử cần bao phủ cả quyết định và điểm thực thi.

| Tình huống | Kết quả cần đạt |
|---|---|
| Subject có action nhưng sai resource | Bị từ chối |
| Subject có resource nhưng sai action | Bị từ chối |
| Có restart A và read B | Không suy ra restart B |
| Role tên operator nhưng chứa quyền rộng ngoài ý định | Được phát hiện trong đối chiếu quyền |
| Client đổi danh tính người thao tác trong request | Không thay được principal đã xác thực |
| Client chọn resource khác sau phê duyệt | Quyết định cũ không tự áp dụng |
| Tham số vượt schema hoặc phạm vi | Bị chặn trước tác dụng phụ |
| Action chưa biết hoặc phiên bản không phù hợp | Không rơi vào nhánh cho phép |
| Gọi API khi nút giao diện bị ẩn | Backend vẫn kiểm tra quyền |
| Đi qua CLI hoặc endpoint cũ | Áp dụng kiểm soát tương ứng, không có đường bỏ qua |
| Sửa nhãn tài nguyên để mở rộng phạm vi | Không tự tạo quyền trái chính sách |
| Grant hoặc phê duyệt hết hạn | Không khởi tạo thao tác bằng quyền cũ |
| Thu hồi trong lúc quyết định chưa được thực thi | Hành vi đúng giới hạn và cơ chế đã công bố |
| Batch chứa tài nguyên không được phép | Xử lý đúng mô hình toàn bộ hoặc một phần đã định nghĩa |
| Retry sau timeout | Không tạo thao tác lặp ngoài ý muốn; có đối soát |
| Người dùng thử chọn credential hoặc runner tùy ý | Bị chặn |
| Sửa định nghĩa action làm tăng tác động | Có quản trị thay đổi và đánh giá lại liên quan |
| Kiểm tra log | Có cả quyết định và kết quả, không lộ bí mật |
| Kết thúc công việc | Grant, job và credential được xử lý đúng vòng đời |

Entitlement theo action giúp chuyển ý định least privilege thành khả năng có thể kiểm tra. Để đạt được điều đó, quyền phải giữ đúng quan hệ giữa chủ thể, hành động, tài nguyên, tham số và điều kiện; backend phải thực thi cùng ranh giới, còn PAM phải theo dõi được việc cấp, sử dụng và kết thúc quyền.
