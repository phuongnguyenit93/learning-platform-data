# Admin endpoint

Một ứng dụng có thể bảo vệ chặt chẽ giao diện người dùng nhưng vẫn để một endpoint quản trị có quyền quá rộng. Chẳng hạn, nút “Khởi động lại worker” chỉ xuất hiện với đội vận hành, còn API phía sau lại chấp nhận yêu cầu từ bất kỳ người dùng đã đăng nhập nào. Người không có nút vẫn có thể gửi yêu cầu trực tiếp tới API.

Một trường hợp khác: endpoint chỉ mở trong mạng nội bộ và dùng một API key chung. Khi key bị lộ từ một workload, hệ thống không phân biệt được ai đã gọi, tài nguyên nào được phép tác động hay việc phê duyệt còn hiệu lực hay không.

Trong quản lý truy cập đặc quyền — Privileged Access Management, viết tắt là PAM — admin endpoint là một điểm thực thi quyền đặc biệt. Nó cần được quản lý như một đường truy cập vào tài nguyên nhạy cảm, với danh tính, quyền theo nhiệm vụ, giới hạn thời gian và bằng chứng đầy đủ.

Bài học này trình bày cách thiết kế và vận hành admin endpoint trong phạm vi đặc quyền ứng dụng. Trọng tâm là kiểm soát hành động thực tế mà endpoint có thể thực hiện, không chỉ bảo vệ tên đường dẫn.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

- Nhận diện admin endpoint dựa trên tác động và quyền thực thi.
- Phân biệt xác thực, phân quyền và phê duyệt đối với thao tác quản trị.
- Thiết kế quyền theo hành động, tài nguyên, môi trường và thời hạn.
- Xây dựng endpoint có chức năng hẹp thay vì mở đường chạy lệnh tùy ý.
- Kiểm soát chuỗi yêu cầu, hàng đợi và worker để tránh lạm dụng quyền của thành phần trung gian.
- Kiểm thử truy cập bị từ chối và giữ bằng chứng phục vụ kiểm toán hoặc ứng phó sự cố.

## 2. Admin endpoint là gì?

Admin endpoint là giao diện mà qua đó một chủ thể có thể quan sát thông tin nhạy cảm hoặc thay đổi trạng thái vận hành, bảo mật hay quản trị của hệ thống.

Nó có thể là HTTP API, RPC, cổng quản lý hoặc giao diện điều khiển khác. Trong bài học này, các ví dụ dùng HTTP để dễ mô tả, nhưng nguyên tắc phân quyền áp dụng cả ngoài HTTP.

Ví dụ về chức năng quản trị:

| Chức năng | Quyền hoặc tác động cần xem xét |
| --- | --- |
| Thay đổi cấu hình runtime | Có thể thay đổi hành vi ứng dụng hoặc điểm kết nối |
| Khởi động lại, dừng hoặc tạm ngưng worker | Có thể ảnh hưởng tính sẵn sàng và xử lý công việc |
| Chạy lại job | Có thể tạo tác động trùng lặp hoặc xử lý dữ liệu vượt phạm vi |
| Thu hồi phiên hoặc khóa principal | Có thể ảnh hưởng truy cập của người dùng và workload |
| Đổi quyền, gán vai trò | Thay đổi ranh giới truy cập của hệ thống |
| Kích hoạt xoay credential | Tác động vòng đời bí mật và kết nối phụ thuộc |
| Xuất bản ghi chẩn đoán | Có thể đưa dữ liệu nhạy cảm hoặc thông tin nội bộ ra ngoài |
| Đọc cấu hình bảo mật | Có thể lộ cấu trúc quyền hoặc metadata nhạy cảm |
| Chạy tác vụ sửa dữ liệu | Có thể thay đổi trạng thái nghiệp vụ với quyền cao |

Không phải mọi endpoint chứa từ `admin` đều có cùng mức rủi ro. Ngược lại, một đường dẫn tên `/support/fix` vẫn là admin endpoint nếu có thể sửa dữ liệu production.

Cần phân loại theo hành vi và tài nguyên bị tác động, không theo tên thư mục hoặc giao diện.

## 3. Phân biệt các nhóm endpoint

Việc phân loại giúp cấp quyền chính xác thay vì gom mọi chức năng vào một vai trò quản trị toàn năng.

### 3.1. Endpoint nghiệp vụ thông thường

Phục vụ hành động của người dùng trong phạm vi nghiệp vụ được cấp. Ví dụ, một khách hàng xem hóa đơn của chính mình.

Nó vẫn cần phân quyền đối tượng và dữ liệu. Tuy nhiên, quyền này không nên bị trộn với quyền vận hành hạ tầng hoặc sửa trạng thái toàn hệ thống.

### 3.2. Endpoint quản trị nghiệp vụ

Ví dụ, người được phân công duyệt một giao dịch hoặc xử lý một yêu cầu hỗ trợ trong đúng đơn vị.

Phạm vi thường gắn với tenant, tổ chức, quy trình và loại dữ liệu. Chức danh “admin của tenant A” không mặc nhiên cho phép tác động tenant B hoặc nền tảng chung.

### 3.3. Endpoint vận hành và bảo mật

Ví dụ, dừng worker, thay cấu hình, quản lý credential, đọc dữ liệu chẩn đoán hoặc thay đổi quyền.

Những endpoint này thường cần được tách khỏi đường truy cập người dùng thông thường và áp dụng kiểm soát đặc quyền phù hợp.

### 3.4. Endpoint health và quan sát

Một phép kiểm tra sống tối thiểu có thể cần được gọi bởi nền tảng mà không dùng quyền quản trị của con người. Điều đó không có nghĩa có thể công khai toàn bộ cấu hình, biến môi trường, stack trace hoặc bản dump.

Nên tách thông tin tối thiểu phục vụ điều phối khỏi thông tin chẩn đoán chi tiết. Quyền đọc cũng cần được phân loại theo dữ liệu mà nó làm lộ.

## 4. Mô hình quyền: ai, làm gì, trên đâu, khi nào?

Một quyết định quản trị cần ít nhất các thành phần:

```text
Danh tính đã xác thực
    + Hành động được yêu cầu
    + Tài nguyên cụ thể
    + Môi trường / tenant
    + Điều kiện và thời hạn
    + Ràng buộc phê duyệt nếu có
    → Cho phép hoặc từ chối
```

Ví dụ, “được phép restart” chưa đủ rõ. Cần biết restart service nào, trong môi trường nào, với lý do và giới hạn gì.

Một quyền có thể được diễn đạt là:

> Người vận hành được restart invoice-worker ở staging trong ca trực đã được cấp; restart production cần quyền tạm thời gắn với thay đổi được duyệt.

Đây là mô tả chính sách minh họa. Quy tắc thực tế phụ thuộc mô hình vận hành và mức ảnh hưởng của tổ chức.

### 4.1. Xác thực không thay thế phân quyền

Xác thực trả lời chủ thể là ai. Nó không tự trả lời chủ thể có được dừng dịch vụ hay xem dữ liệu chẩn đoán hay không.

Token hợp lệ nhưng được cấp cho ứng dụng khác, sai môi trường hoặc thiếu quyền quản trị vẫn phải bị từ chối tại đúng ranh giới.

### 4.2. Vai trò rộng không thay thế quyền theo hành động

Một vai trò `ADMIN` chung dễ trở thành tập hợp quyền lớn khó giải thích.

Có thể chia thành quyền theo nhiệm vụ như:

- Xem trạng thái vận hành.
- Yêu cầu restart một service được giao.
- Thay đổi một nhóm cấu hình đã định nghĩa.
- Kích hoạt quy trình xoay credential.
- Phê duyệt tác vụ sửa dữ liệu.
- Quản lý chính sách truy cập.

Không mặc định rằng người có quyền đọc trạng thái cũng được đọc secret hoặc thay cấu hình.

### 4.3. Phê duyệt không thay thế quyền truy cập

Một mã ticket tồn tại không có nghĩa bất kỳ ai cầm mã đó cũng được thực hiện thao tác.

Cần kiểm tra người yêu cầu, trạng thái phê duyệt, phạm vi hành động, tài nguyên, thời hạn và các ràng buộc liên quan. Ticket là một phần của bằng chứng hoặc chính sách, không phải password dùng chung.

## 5. Vị trí của admin endpoint trong kiến trúc

Một kiến trúc tham khảo có thể gồm:

```text
Người vận hành bằng danh tính cá nhân
                  │
                  ▼
      Đường truy cập quản trị được kiểm soát
                  │
                  ▼
          Admin API / bộ điều phối
       xác thực và phân quyền theo thao tác
                  │
                  ▼
        Tác vụ quản trị có phạm vi hẹp
                  │
                  ▼
        Tài nguyên hoặc hệ thống đích

Bằng chứng được nối từ yêu cầu đến kết quả thực thi.
```

Danh tính của Admin API khi gọi tài nguyên đích thường là danh tính workload riêng. Điều đó tạo ra hai câu hỏi khác nhau:

1. Người gọi có quyền yêu cầu hành động này không?
2. Bộ thực thi có đúng quyền để thực hiện hành động đã được cho phép không?

Nếu Admin API có credential toàn quyền rồi thực hiện mọi nội dung người gọi gửi, nó có thể trở thành công cụ sử dụng đặc quyền thay cho người không có quyền.

Đường quản trị có thể được triển khai qua mạng riêng, proxy, cổng PAM hoặc cơ chế truy cập phù hợp. Mạng riêng giúp giới hạn nguồn tiếp cận, nhưng không thay thế xác thực và phân quyền tại ứng dụng.

Tách host, port hoặc đường dẫn cũng không tự tạo ranh giới quyền nếu có một đường truy cập khác tới cùng chức năng mà không áp dụng kiểm soát tương đương.

## 6. Xác thực và ranh giới tin cậy

### 6.1. Nhận diện đúng loại chủ thể

Con người nên sử dụng danh tính cá nhân để có thể quy trách nhiệm. Tác vụ tự động nên sử dụng danh tính workload riêng với quyền phục vụ đúng công việc.

Không dùng một API key quản trị chung cho cả đội và tất cả pipeline. Khi có sự cố, việc phân biệt nguồn yêu cầu và thu hồi theo phạm vi sẽ khó hơn.

Với hành động nhạy cảm, có thể yêu cầu xác thực tăng cường hoặc phiên đặc quyền theo chính sách. Việc này cần gắn với đúng chủ thể và thao tác, không chỉ kiểm tra rằng người đó từng đăng nhập mạnh ở một thời điểm xa trước đó.

### 6.2. Token phải được kiểm tra trong ngữ cảnh của endpoint

Khi sử dụng token, hệ thống cần xác minh bằng cơ chế được hỗ trợ và cấu hình đúng: nguồn phát hành tin cậy, đối tượng nhận phù hợp, thời hạn và các thuộc tính cần thiết.

Không chỉ giải mã phần dữ liệu rồi tin trường `role` hoặc `scope`. Dữ liệu đọc được từ token chưa được xác minh không phải bằng chứng về quyền.

Cũng không lấy `userId`, `tenantId` hoặc `isAdmin` do client gửi làm quyết định phân quyền mà không đối chiếu với ngữ cảnh đã xác thực và chính sách server.

### 6.3. Header do proxy thêm phải có ranh giới tin cậy

Nếu ứng dụng tin một header định danh do proxy thêm, phải bảo đảm:

- Proxy xác thực người gọi theo thiết kế.
- Header giả từ client được loại bỏ hoặc thay thế ở ranh giới phù hợp.
- Backend chỉ chấp nhận nguồn hoặc kênh đã được xác thực theo kiến trúc.
- Đường truy cập trực tiếp không cho phép bỏ qua proxy và tự khai danh tính.
- Tính toàn vẹn của thông tin định danh được duy trì giữa các thành phần.

Một header tên `X-Admin-User` không phải là cơ chế xác thực chỉ vì nó có tên mang ý nghĩa quản trị.

### 6.4. Xác thực kênh không tự cấp quyền hành động

Một kết nối được xác thực giữa hai service có thể chứng minh danh tính của bên gọi. Nó không mặc nhiên cho phép bên gọi thực hiện mọi thao tác quản trị.

Vẫn cần ánh xạ principal sang hành động và tài nguyên được phép. Tương tự, hạn chế địa chỉ nguồn là một lớp bổ sung, không phải danh tính của người đang thao tác.

## 7. Phân quyền tại nơi thực hiện hành động

Một endpoint quản trị cần được bảo vệ ở phía server. Ẩn nút trên giao diện không đủ; kiểm tra tại gateway cũng không nên là lớp duy nhất khi bên trong còn các đường gọi khác.

### 7.1. Kiểm tra hành động và đối tượng

Giả sử endpoint nhận:

```text
POST /admin/v1/services/{serviceId}/restarts
```

Server cần xác định:

- `serviceId` có tồn tại và ánh xạ tới tài nguyên nào?
- Tài nguyên thuộc môi trường hoặc tenant nào theo dữ liệu tin cậy?
- Người gọi được phép restart tài nguyên đó không?
- Trạng thái hiện tại có cho phép restart không?
- Quyền hoặc phê duyệt có còn hiệu lực không?

Không chấp nhận một trường `environment: staging` trong body rồi dùng nó để phân quyền trong khi `serviceId` thực tế trỏ tới production.

### 7.2. Kiểm tra lại ở ranh giới thực thi quan trọng

Nếu cùng chức năng được gọi qua HTTP, hàng đợi và một công cụ nội bộ, cần bảo đảm các đường đều đi qua kiểm soát thích hợp.

Quyền thường nên được thực thi tại lớp ứng dụng hoặc dịch vụ nghiệp vụ có đủ ngữ cảnh, bên cạnh kiểm soát giao diện vào. Tránh một helper có quyền cao có thể được gọi trực tiếp để bỏ qua bước phân quyền.

### 7.3. Không tin các thuộc tính quyết định quyền từ client

Các trường như sau cần do server xác định hoặc xác minh với nguồn tin cậy:

```text
requester_identity
approved
approval_owner
effective_role
target_environment
allowed_target_set
executor_principal
```

Client có thể gửi mã tham chiếu phê duyệt, nhưng server phải tự lấy và kiểm tra hồ sơ phê duyệt. Không sử dụng `approved: true` làm bằng chứng.

### 7.4. Không tự mở rộng quyền khi thành phần chính sách lỗi

Nếu không thể xác minh danh tính, quyền hoặc phê duyệt bắt buộc, endpoint không nên chuyển sang cho phép mọi người để duy trì khả dụng.

Cần thiết kế hành vi lỗi rõ ràng: từ chối, chờ xác minh lại hoặc sử dụng một quy trình khẩn cấp đã được quản trị. Quy trình khẩn cấp phải là đường đặc quyền riêng có phạm vi và bằng chứng, không phải nhánh bỏ kiểm tra âm thầm.

## 8. Thiết kế chức năng hẹp thay vì endpoint toàn năng

Một endpoint nhận `command`, `script`, `sql` hoặc địa chỉ đích tùy ý rồi chạy bằng quyền quản trị có phạm vi rất khó kiểm soát.

Ưu tiên những hành động đã được định nghĩa:

| Thiết kế quá rộng | Thiết kế hẹp hơn |
| --- | --- |
| Chạy mọi câu lệnh trên host | Restart đúng service đã đăng ký |
| Thực thi SQL tùy ý | Chạy quy trình sửa dữ liệu cụ thể với tham số đã kiểm tra |
| Đọc file theo đường dẫn client cung cấp | Lấy loại log được phép của workload được giao |
| Gọi URL bất kỳ bằng credential nội bộ | Gọi tác vụ đã định nghĩa trên hệ thống đích được đăng ký |
| Nhận toàn bộ object cấu hình rồi ghi đè | Chỉ thay các trường cho phép, có kiểm tra phiên bản |
| Xuất toàn bộ credential để chẩn đoán | Trả metadata không bí mật cần cho phép kiểm tra |

Thiết kế hẹp không có nghĩa chỉ kiểm tra tên thao tác. Cần kiểm tra tham số và tài nguyên bên trong thao tác.

Ví dụ, “restart service” vẫn quá rộng nếu người gọi được tự chỉ định executable hoặc host bất kỳ. “Xem log” có thể trở thành đọc file tùy ý nếu đường dẫn không được ánh xạ và giới hạn an toàn.

Các giá trị đích nên được phân giải từ danh mục tài nguyên tin cậy. Nếu phải nhận địa chỉ hoặc đường dẫn, cần xử lý đầy đủ rủi ro truy cập tài nguyên ngoài phạm vi; chỉ kiểm tra tiền tố chuỗi thường không đủ.

## 9. Ví dụ: endpoint restart worker

Giả sử đội vận hành cần restart `invoice-worker` khi nó không tiến triển. Thay vì cấp shell trên host, hệ thống cung cấp một thao tác có phạm vi rõ.

### 9.1. Hợp đồng yêu cầu

Ví dụ HTTP dưới đây chỉ minh họa cấu trúc:

```http
POST /admin/v1/services/invoice-worker-prod/restarts
Content-Type: application/json
Idempotency-Key: restart-request-example-17

{
  "reason": "Worker không tiến triển theo tiêu chí vận hành",
  "approvalReference": "change-example-204",
  "expectedVersion": "service-state-example-8"
}
```

Người gọi không được chọn credential của executor, sửa trạng thái phê duyệt hoặc truyền lệnh hệ điều hành.

Server phân giải `invoice-worker-prod` tới tài nguyên được quản lý và lấy môi trường từ danh mục tin cậy. Quyền quyết định dựa trên principal đã xác thực và tài nguyên đã được phân giải.

### 9.2. Luồng xử lý

Mã giả dưới đây mô tả trách nhiệm, không phải API của một thư viện hay framework:

```text
handle_restart(request, authenticated_context):
    actor = require_verified_identity(authenticated_context)
    input = validate_restart_request(request)

    target = resolve_registered_service(request.service_id)
    require_supported_restart_target(target)

    approval = load_approval_from_trusted_source(input.approval_reference)

    decision = authorize(
        actor = actor,
        action = "service.restart",
        target = target,
        approval = approval,
        now = trusted_current_time()
    )

    require_allowed(decision)
    require_target_version(target, input.expected_version)

    operation = reserve_operation_for_authorized_request(
        actor = actor,
        action = "service.restart",
        target = target,
        validated_input = input,
        idempotency_key = request.idempotency_key
    )

    record_request_and_decision(operation, decision)
    dispatch_bounded_restart_operation(operation)

    return accepted_operation_reference(operation)
```

Việc kiểm tra phiên bản và ghi nhận thao tác cần được triển khai với cơ chế đồng thời phù hợp. Một kiểm tra đọc rồi ghi tách rời không tự ngăn được mọi thay đổi cạnh tranh.

Nếu tài nguyên đích ở hệ thống khác, không được giả định có giao dịch nguyên tử xuyên qua mọi hệ thống. Cần thiết kế cơ chế điều phối, kiểm tra trước hành động có tác động và xử lý kết quả không xác định theo khả năng thực tế.

### 9.3. Quyền của bộ thực thi

Executor chỉ cần quyền thực hiện tác vụ được giao trên tài nguyên tương ứng. Không nên mặc định có quyền quản trị toàn bộ cluster hoặc toàn bộ tài khoản cloud.

Tách quyền của người gọi và executor giúp giới hạn phạm vi, nhưng cũng đòi hỏi bảo vệ thông điệp điều phối. Người không có quyền không được tự đưa một job giả vào hàng đợi để dùng quyền của executor.

## 10. Phê duyệt, JIT và JEA

PAM thường kết hợp quyền tạm thời với phạm vi hành động hẹp.

- **JIT — Just-in-Time:** quyền được cấp khi cần và có thời hạn.
- **JEA — Just Enough Administration:** chỉ cung cấp đủ khả năng quản trị cho nhiệm vụ cụ thể, theo cơ chế nền tảng hỗ trợ.

Một phiên “admin trong 30 phút” vẫn quá rộng nếu nó cho phép thay đổi mọi tài nguyên. Một endpoint chỉ có một chức năng vẫn có thể gây tác động lớn nếu chạy trên toàn bộ production.

### 10.1. Gắn phê duyệt với đúng yêu cầu

Hồ sơ phê duyệt nên ràng buộc những thuộc tính có ý nghĩa:

- Người hoặc nhóm được phép thực hiện.
- Hành động cụ thể.
- Tài nguyên hoặc tập tài nguyên được duyệt.
- Môi trường và tenant.
- Tham số hoặc giới hạn tác động cần thiết.
- Khoảng thời gian hiệu lực.
- Số lần sử dụng hoặc điều kiện tái sử dụng.
- Người phê duyệt và chính sách phân tách trách nhiệm.

Không dùng phê duyệt restart staging để thực hiện restart production. Không tái sử dụng phê duyệt đọc chẩn đoán để xuất toàn bộ dữ liệu.

### 10.2. Thay đổi yêu cầu sau phê duyệt

Nếu người gọi thay đích, tham số nhạy cảm hoặc tập đối tượng sau khi phê duyệt, cần đánh giá lại hoặc phê duyệt lại theo chính sách.

Có thể lưu bản yêu cầu bất biến và dấu kiểm tra tính toàn vẹn trong hệ thống phê duyệt. Dấu băm tự nó không chứng minh có phê duyệt; nó chỉ giúp so khớp nội dung khi nằm trong một quy trình đáng tin cậy.

Với thao tác hàng loạt, cần định nghĩa rõ phê duyệt áp dụng cho danh sách đối tượng cụ thể hay cho một quy tắc chọn có ràng buộc. Một truy vấn động có thể chọn thêm đối tượng sau thời điểm duyệt nếu không được kiểm soát.

### 10.3. Phân tách người yêu cầu và người duyệt

Các tác vụ có tác động lớn có thể cần người duyệt độc lập. Quy tắc phải được thực thi bằng danh tính và quyền thực tế.

Hai tài khoản khác nhau do cùng một người kiểm soát không tạo ra phân tách trách nhiệm có ý nghĩa nếu chính sách yêu cầu hai người độc lập.

## 11. Tác vụ bất đồng bộ và quyền tại thời điểm thực thi

Một Admin API có thể chỉ tiếp nhận yêu cầu, còn worker chạy sau vài phút. Đây là ranh giới dễ bỏ sót.

Cần ghi rõ chính sách quyền theo thời gian:

- Quyền phải còn hiệu lực khi tiếp nhận hay cả khi bắt đầu thực thi?
- Nếu người yêu cầu bị thu hồi quyền trong lúc job đang chờ thì sao?
- Phê duyệt hết hạn trước khi worker bắt đầu có được dùng không?
- Job đã bắt đầu được xử lý thế nào nếu quyền bị thu hồi giữa chừng?
- Có điểm dừng an toàn trước bước không thể đảo ngược hay không?

Không có một câu trả lời chung cho mọi tác vụ. Tuy nhiên, câu trả lời phải được thiết kế rõ và được kiểm thử.

### 11.1. Nội dung giao việc cần được bảo vệ

Một envelope tác vụ có thể gồm:

```json
{
  "operationId": "admin-operation-example-31",
  "requesterId": "operator-example",
  "action": "service.restart",
  "targetId": "invoice-worker-prod",
  "approvalReference": "change-example-204",
  "policyVersion": "policy-example-12",
  "requestedAt": "recorded-request-time",
  "notAfter": "approved-execution-deadline",
  "requestReference": "immutable-request-example-31"
}
```

Đây là schema minh họa. Các chuỗi thời gian phải được biểu diễn và xác minh theo định dạng hệ thống thực tế.

Envelope phải được tạo bởi thành phần có thẩm quyền, truyền qua kênh được bảo vệ và kiểm tra tại worker. Không tin các trường trên chỉ vì chúng xuất hiện trong một bản tin hàng đợi.

### 11.2. Không dùng quyền executor thay cho quyền người yêu cầu

Worker có thể có quyền restart nhiều service để thực hiện công việc. Điều đó không cho phép mọi người gửi job restart tất cả các service ấy.

Worker cần xác minh nguồn job, tính toàn vẹn, phạm vi đích và điều kiện thực thi. Tùy thiết kế, nó kiểm tra quyết định còn hiệu lực hoặc xác minh một ủy quyền thực thi có giới hạn do thành phần tin cậy cấp.

Ủy quyền thực thi cũng phải có phạm vi, thời hạn và quy tắc thu hồi rõ ràng; không trở thành một bearer credential quản trị vô thời hạn.

### 11.3. Job đang chạy và thu hồi quyền

Dừng một job giữa chừng có thể để lại trạng thái chưa hoàn tất. Do đó, thu hồi không phải lúc nào cũng đồng nghĩa hủy ngay mọi bước.

Cần xác định điểm kiểm tra lại, điểm có thể hủy, hành động bù hoặc phương án hoàn tất an toàn. Trước bước nhạy cảm hoặc không thể đảo ngược, áp dụng kiểm soát tương ứng với mức tác động.

Bằng chứng phải cho thấy việc tiếp tục hoặc dừng job tuân theo chính sách đã định, không phải worker bỏ qua thu hồi một cách ngẫu nhiên.

## 12. Kiểm soát lặp lại, đồng thời và phạm vi tác động

### 12.1. Idempotency không thay thế phân quyền

Client có thể gửi lại yêu cầu vì timeout. Idempotency giúp hệ thống tránh lặp tác động theo thiết kế.

Khóa idempotency cần được ràng buộc với ngữ cảnh thích hợp: chủ thể, hành động, tài nguyên và nội dung yêu cầu đã được chuẩn hóa. Không cho phép người khác đoán khóa rồi xem kết quả quản trị hoặc lấy lại dữ liệu nhạy cảm.

Khi nhận yêu cầu lặp, vẫn xác thực và phân quyền truy cập bản ghi thao tác. Nếu cùng khóa nhưng nội dung khác, cần xử lý xung đột rõ ràng.

### 12.2. Giới hạn đồng thời

Hai yêu cầu restart có thể không gây thay đổi dữ liệu nhưng vẫn tạo gián đoạn. Hai yêu cầu sửa cấu hình có thể ghi đè lẫn nhau.

Có thể cần kiểm tra phiên bản, cơ chế điều phối theo tài nguyên, giới hạn số tác vụ đang chạy hoặc cửa sổ bảo trì. Chọn cơ chế theo hệ thống đích và xác minh hành vi cạnh tranh.

### 12.3. Giới hạn tác động và tốc độ

Một người có quyền thực hiện một thao tác không nhất thiết được phép lặp thao tác đó không giới hạn.

Cân nhắc giới hạn theo người, workload, tài nguyên, môi trường và loại hành động. Đối với tác vụ hàng loạt, giới hạn số đối tượng hoặc yêu cầu duyệt bổ sung khi vượt ngưỡng.

Rate limit chỉ giới hạn tần suất; nó không thay thế kiểm tra quyền hay giới hạn tài nguyên của từng yêu cầu.

### 12.4. Kết quả không xác định

Nếu hệ thống đích đã thực hiện thao tác nhưng phản hồi bị mất, endpoint không nên luôn tuyên bố thất bại rồi chạy lại mù quáng.

Cần có mã thao tác, trạng thái và cách đối chiếu kết quả. Với hành động không thể đảo ngược, quy trình retry cần đặc biệt rõ để không tạo tác động trùng.

## 13. Admin endpoint được gọi từ trình duyệt

Nếu endpoint dùng session cookie hoặc credential được trình duyệt tự động gửi, phải xem xét việc một nguồn khác có thể khiến trình duyệt gửi yêu cầu ngoài ý muốn.

Các điểm cần thiết kế gồm:

- Kiểm soát CSRF phù hợp với cơ chế xác thực.
- Chính sách cookie và kiểm tra nguồn theo kiến trúc.
- Không sử dụng GET cho thao tác thay đổi trạng thái.
- Xác minh quyền phía server cho từng hành động.
- Tránh đưa credential quản trị vào URL.
- Giới hạn và kiểm tra nội dung đầu vào.

Dùng POST không tự ngăn CSRF. CORS cũng không phải cơ chế phân quyền của API; client không phải trình duyệt không bị ràng buộc bởi cùng hành vi kiểm soát đó.

Nếu dùng bearer token được ứng dụng chủ động gắn vào yêu cầu, vẫn phải xem xét nơi lưu token, nguy cơ mã độc phía client và toàn bộ cơ chế xác thực. Không nên suy ra “không dùng cookie” đồng nghĩa endpoint đã an toàn trước mọi yêu cầu trái phép.

Một hộp thoại xác nhận trên giao diện giúp giảm thao tác nhầm, nhưng không phải bằng chứng phê duyệt đáng tin nếu server không thực thi ràng buộc tương ứng.

## 14. Đọc dữ liệu quản trị cũng là đặc quyền

Những endpoint chỉ đọc có thể cung cấp:

- Log chứa dữ liệu khách hàng.
- Cấu hình hệ thống.
- Danh sách principal và quyền.
- Metadata hạ tầng.
- Stack trace, thông tin kết nối hoặc trạng thái nội bộ.
- Bản dump hoặc dữ liệu chẩn đoán có secret.

Do đó, không gộp mọi quyền đọc vào `admin.read` nếu dữ liệu có mức nhạy cảm khác nhau.

Một endpoint health tối thiểu chỉ cần trả trạng thái phục vụ điều phối. Endpoint chẩn đoán chi tiết có thể cần quyền riêng, lọc dữ liệu, giới hạn tải và đường truy cập đặc quyền.

Đối với bản xuất lớn, cần xem xét nơi lưu kết quả, quyền tải, thời hạn tồn tại và khả năng người khác dùng lại đường dẫn. Quyền tạo bản xuất và quyền đọc bản xuất là hai quyết định liên quan nhưng không hoàn toàn giống nhau.

Không trả password, private key hoặc token đầy đủ chỉ để người vận hành kiểm tra “ứng dụng đang nhận đúng secret hay chưa”. Có thể dùng metadata không bí mật và phép thử có giới hạn thay thế.

## 15. Credential và quyền của chính Admin API

Admin API là một workload đặc quyền nên cũng cần được quản trị như service account nhạy cảm.

Cần xác định:

- Principal chạy API và principal của executor.
- Tài nguyên nào mỗi principal được phép tác động.
- Cách lấy credential và điều kiện được sử dụng.
- Chủ sở hữu và người phê duyệt quyền.
- Cách xoay credential, thu hồi và xử lý sự cố.
- Log nào ghi nhận hành động ở hệ thống đích.

Nếu một API làm cả xem trạng thái, restart, sửa dữ liệu và quản lý danh tính, có thể cần tách các bộ thực thi hoặc principal theo ranh giới tác động.

Không phải mọi hệ thống đều cần một service cho từng endpoint. Điều quan trọng là không để lỗi ở một chức năng ít đặc quyền dễ dàng sử dụng credential của chức năng có quyền cao hơn.

Credential ngắn hạn hoặc danh tính workload có thể giảm việc giữ bí mật dài hạn, nhưng không tự sửa một chính sách cho phép quá rộng.

## 16. Audit: nối được từ người yêu cầu đến kết quả

Một bản ghi quản trị hữu ích thường có:

| Nhóm dữ liệu | Nội dung minh họa |
| --- | --- |
| Người yêu cầu | Principal đã xác thực, loại chủ thể, ngữ cảnh phiên cần thiết |
| Hành động | Tên thao tác chuẩn hóa, không chỉ URL |
| Tài nguyên | Định danh ổn định, môi trường, tenant phù hợp |
| Quyền và phê duyệt | Kết quả quyết định, mã tham chiếu, phiên bản chính sách |
| Thực thi | Mã thao tác, principal executor, thời điểm bắt đầu và kết thúc |
| Kết quả | Thành công, từ chối, thất bại, hủy hoặc chưa xác định |
| Liên kết bằng chứng | Mã tương quan với hệ thống đích và hồ sơ thay đổi |

Phân biệt rõ “đã tiếp nhận”, “đã được cho phép”, “đã bắt đầu” và “đã hoàn tất”. Phản hồi HTTP chấp nhận yêu cầu không chứng minh tài nguyên đã thay đổi thành công.

Log yêu cầu và log thực thi nên có mã tương quan, nhưng không dùng mã tương quan làm credential. Người biết mã thao tác vẫn cần quyền để xem kết quả.

Không ghi nguyên body nếu body có dữ liệu nhạy cảm. Có thể lưu bản yêu cầu được kiểm soát ở kho thích hợp và ghi tham chiếu hoặc thông tin đã lọc vào audit.

Đối với thao tác đặc quyền, nên có bằng chứng từ hệ thống đích khi khả dụng. Log do Admin API tự khai không phải lúc nào cũng đủ khi chính API bị xâm nhập.

### Khi hệ thống audit gặp lỗi

Cần định nghĩa trước hành vi:

- Tác vụ nào bắt buộc có bản ghi bền vững trước khi thực hiện.
- Có cơ chế ghi đệm hoặc khôi phục audit được kiểm soát hay không.
- Khi nào phải từ chối hoặc trì hoãn tác vụ.
- Quy trình khẩn cấp nào được phép nếu có.

Không âm thầm tiếp tục mọi thao tác quản trị trong khi mất toàn bộ khả năng ghi nhận bằng chứng.

## 17. Bộ kiểm thử phân quyền

Kiểm thử cần gửi yêu cầu trực tiếp đến API hoặc ranh giới ứng dụng, không chỉ kiểm tra nút giao diện.

| Tình huống | Kết quả mong đợi |
| --- | --- |
| Không có danh tính hợp lệ | Không được thực hiện thao tác |
| Người dùng thông thường gọi endpoint quản trị | Bị từ chối |
| Người có quyền staging chọn tài nguyên production | Bị từ chối |
| Admin tenant A dùng ID của tenant B | Bị từ chối theo ranh giới tenant |
| Có quyền xem trạng thái nhưng yêu cầu restart | Bị từ chối |
| Có quyền restart nhưng yêu cầu sửa cấu hình | Bị từ chối |
| Token cho ứng dụng khác hoặc sai ngữ cảnh | Không được chấp nhận như quyền quản trị hợp lệ |
| Client tự gửi header hoặc trường vai trò quản trị | Không được dùng để tự nâng quyền |
| Truy cập backend để bỏ qua cổng quản trị | Bị chặn hoặc vẫn chịu kiểm soát tương đương |
| Phê duyệt hết hạn hoặc sai tài nguyên | Không thực hiện thao tác |
| Thay nội dung sau phê duyệt | Yêu cầu bị từ chối hoặc cần phê duyệt lại |
| Người không có quyền ghi job giả vào hàng đợi | Không làm executor thực thi |
| Quyền bị thu hồi khi job đang chờ | Xử lý đúng chính sách tại thời điểm thực thi |
| Gửi lại cùng yêu cầu hợp lệ | Không lặp tác động ngoài thiết kế |
| Dùng khóa idempotency của chủ thể khác | Không lộ hoặc chiếm thao tác |
| Thành phần chính sách không xác minh được quyền | Không tự cho phép rộng hơn |
| Audit bắt buộc không thể ghi | Xử lý theo chính sách lỗi đã xác định |
| Xem trạng thái thao tác của người khác | Kiểm tra quyền đọc kết quả trước khi trả dữ liệu |

Thực hiện thêm kiểm thử tích cực để chứng minh người có đúng quyền vẫn hoàn thành nhiệm vụ. Hệ thống từ chối mọi yêu cầu không phải là kết quả vận hành đạt yêu cầu.

Với tác vụ có tác động thật, chọn môi trường thử nghiệm, tài nguyên giả lập hoặc phương án kiểm tra được phê duyệt. Không dùng thử nghiệm bảo mật để tự ý restart production hay sửa dữ liệu thật.

## 18. Triển khai và vận hành

### 18.1. Kiểm kê trước khi siết quyền

Lập danh mục endpoint, phương thức, chức năng, caller, principal thực thi và tài nguyên tác động.

Bao gồm phiên bản API cũ, đường chẩn đoán, công cụ hỗ trợ, endpoint từ framework và các đường gọi nội bộ. Một phiên bản cũ không có trong giao diện vẫn có thể được gọi trực tiếp.

Không đánh dấu endpoint “không sử dụng” chỉ vì một khoảng log ngắn không có yêu cầu. Đối chiếu tác vụ định kỳ và quy trình khôi phục.

### 18.2. Đưa quyền từ rộng về hẹp

Xác định hành động thực sự cần, chia vai trò hoặc quyền theo nhiệm vụ và cung cấp công cụ vận hành thay thế cho shell hoặc credential chung.

Nếu chuyển đổi có giai đoạn ngoại lệ, ghi phạm vi, chủ sở hữu, thời hạn và kế hoạch đóng. Không giữ hai đường truy cập với kiểm soát khác nhau vô thời hạn.

### 18.3. Theo dõi tín hiệu bất thường

Các tín hiệu cần điều tra có thể gồm:

- Sử dụng endpoint nhạy cảm lần đầu bởi một principal.
- Yêu cầu ngoài tài nguyên hoặc môi trường được giao.
- Nhiều lần thử ID tài nguyên khác nhau.
- Phê duyệt được tái sử dụng bất thường.
- Khối lượng thao tác tăng đột biến.
- Job được thực thi nhưng không có yêu cầu hoặc quyết định tương ứng.
- Principal executor thực hiện hành động ngoài danh mục endpoint được phép.
- Thay đổi chính sách, cấu hình hoặc credential của đường quản trị.

Đừng chỉ theo dõi yêu cầu thất bại. Một yêu cầu thành công với phạm vi bất thường có thể quan trọng hơn nhiều lần bị từ chối.

### 18.4. Khi nghi ngờ bị lạm dụng

Xác định caller, thao tác, tài nguyên, thời điểm, principal executor và các job còn chờ. Bảo toàn bằng chứng rồi giới hạn đường sử dụng bị ảnh hưởng theo quy trình ứng phó.

Đánh giá riêng token của người gọi, credential của API, credential executor và phiên ở hệ thống đích. Thu hồi một loại không mặc nhiên thu hồi tất cả loại còn lại.

Các job đã được tiếp nhận cần được xét theo chính sách: hủy, giữ chờ, kiểm tra lại hoặc hoàn tất an toàn. Không bỏ qua hàng đợi khi đã đóng endpoint tiếp nhận.

## 19. Bài tập tình huống

Một ứng dụng cung cấp ba endpoint:

```text
GET  /internal/status
POST /internal/restart
POST /internal/run-maintenance
```

Toàn bộ được bảo vệ bằng một API key dùng chung. Key xuất hiện trong cấu hình của nhiều service. Endpoint maintenance nhận tên host, câu lệnh và trường `approved: true`. Tất cả tác vụ được đưa vào hàng đợi; worker chạy bằng principal quản trị hạ tầng.

### Yêu cầu phân tích

- Phân loại tác động và dữ liệu của từng endpoint.
- Xác định những ranh giới xác thực và phân quyền đang thiếu.
- Đề xuất cách thay API key chung bằng danh tính có thể quy trách nhiệm.
- Thiết kế lại maintenance để phục vụ đúng các tác vụ cần thiết.
- Xác định cách ràng buộc phê duyệt và bảo vệ job.
- Nêu những kiểm thử phải có trước khi triển khai.

### Hướng giải thích

Endpoint status phải được kiểm tra nội dung: trạng thái tối thiểu có thể khác hoàn toàn cấu hình hoặc dữ liệu chẩn đoán chi tiết.

Restart cần nhận một tài nguyên được đăng ký thay vì cho phép tác động host bất kỳ. Quyền phải kiểm tra theo hành động, môi trường và tài nguyên.

Maintenance không nên tin câu lệnh và cờ phê duyệt từ client. Cần thay bằng danh mục tác vụ có đầu vào hẹp, lấy hồ sơ phê duyệt từ nguồn tin cậy và gắn nó với đúng yêu cầu.

Con người sử dụng danh tính cá nhân; service tự động sử dụng danh tính workload riêng. Mỗi caller chỉ có quyền gọi tác vụ cần thiết, không kế thừa toàn bộ quyền của worker.

Hàng đợi cần giới hạn bên được gửi job, bảo vệ nội dung và có kiểm tra tại executor. Principal quản trị hạ tầng cần được thu hẹp hoặc tách theo phạm vi thực thi mà nền tảng hỗ trợ.

Kiểm thử phải bao gồm yêu cầu trái phép trực tiếp, ID ngoài phạm vi, giả header, phê duyệt không khớp, job giả, quyền hết hạn khi job chờ và việc gửi lặp. Đồng thời phải chứng minh tác vụ hợp lệ vẫn chạy và audit nối được toàn bộ chuỗi.

## 20. Tiêu chí hoàn thành

Một admin endpoint được quản trị đúng khi có thể chứng minh:

- Hành động và tài nguyên tác động đã được kiểm kê và phân loại.
- Danh tính của người hoặc workload gọi endpoint được xác thực trong ngữ cảnh phù hợp.
- Phân quyền được thực thi phía server cho đúng hành động, tài nguyên, môi trường và tenant.
- Chức năng có phạm vi hẹp, đầu vào không tự mở rộng thành đặc quyền tùy ý.
- Phê duyệt và quyền tạm thời được ràng buộc, kiểm tra hiệu lực và xử lý khi thu hồi.
- Worker không dùng quyền của nó để thực thi yêu cầu chưa được cho phép.
- Retry, đồng thời và tác vụ hàng loạt không làm vượt phạm vi tác động đã thiết kế.
- Dữ liệu chẩn đoán và credential không bị lộ qua phản hồi hoặc log.
- Bằng chứng nối được từ yêu cầu đến kết quả tại tài nguyên đích.
- Kiểm thử bao phủ cả trường hợp hợp lệ và các đường bỏ qua kiểm soát.

Admin endpoint là nơi ứng dụng biến một yêu cầu thành hành động có đặc quyền. Thiết kế tốt làm rõ ai được yêu cầu, điều gì được thực hiện, phạm vi nào được chấp nhận và bằng chứng nào chứng minh kết quả. Đó là cách đưa least privilege, JIT/JEA và trách nhiệm giải trình vào ngay đường quản trị của ứng dụng.
