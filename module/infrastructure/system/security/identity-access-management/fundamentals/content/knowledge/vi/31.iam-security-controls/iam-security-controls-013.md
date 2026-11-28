# Secure default

## 1. Secure default là gì?

**Secure default** là nguyên tắc thiết kế để trạng thái mặc định của hệ thống bảo vệ danh tính, quyền và dữ liệu mà không đòi hỏi người vận hành phải tự phát hiện rồi bật từng biện pháp bảo vệ thiết yếu.

Trong IAM, điều đó thể hiện qua những lựa chọn như:

- Tài khoản mới không tự có đặc quyền quản trị.
- Tài nguyên mới không tự trở thành công khai.
- Request không khớp một quy tắc cho phép phù hợp không được truy cập tài nguyên được bảo vệ.
- Thiếu cấu hình xác thực quan trọng không làm ứng dụng tự chuyển sang chế độ bỏ xác thực.
- Một kết nối danh tính chưa được phê duyệt không được tự tạo membership.
- Token và credential không tự có phạm vi toàn hệ thống hoặc hiệu lực vô thời hạn.

Ví dụ, một nhóm tạo tenant mới trên nền tảng quản lý tài liệu. Nếu họ chưa cấu hình chia sẻ ra bên ngoài, tài liệu của tenant phải được giữ trong phạm vi được bảo vệ. Không nên yêu cầu họ tìm một tùy chọn “tắt public access” sau khi dữ liệu đã được đưa lên.

Secure default không có nghĩa mọi chức năng đều bị khóa vĩnh viễn. Nó làm cho việc mở rộng quyền hoặc chia sẻ dữ liệu trở thành một hành động rõ ràng, có thẩm quyền và có phạm vi, thay vì hệ quả của việc bỏ trống một trường hoặc chưa đọc tài liệu cấu hình.

## 2. Phân biệt với các nguyên tắc liên quan

| Nguyên tắc | Nội dung chính | Ví dụ |
|---|---|---|
| Secure default | Trạng thái ban đầu và giá trị được chọn sẵn bảo vệ hệ thống | Tài liệu mới ở trạng thái private |
| Default deny | Không cho phép khi không có căn cứ cấp quyền phù hợp | Route chưa được cấp policy không tự được mở |
| Fail secure | Lỗi không làm mất ranh giới bảo vệ | Timeout phân quyền không trở thành ALLOW |
| Least privilege | Quyền được cấp không vượt nhu cầu hợp lệ | Workload báo cáo không có quyền quản lý thành viên |
| Secure configuration | Cấu hình đang chạy đáp ứng yêu cầu bảo vệ | Nguồn danh tính, policy và credential được cấu hình đúng |

Các nguyên tắc hỗ trợ nhau nhưng không thay thế nhau. Một hệ thống có default deny vẫn có thể cấp quá rộng qua role mặc định. Một ứng dụng có cấu hình an toàn trong môi trường hiện tại vẫn có thể có default nguy hiểm cho lần triển khai tiếp theo.

Tương tự, “mặc định an toàn” là thuộc tính của thiết kế và trải nghiệm cấu hình, không phải nhãn bảo đảm mọi triển khai đều an toàn. Việc vận hành có thể cố ý ghi đè một mặc định; những thay đổi đó vẫn cần được giới hạn và theo dõi.

## 3. Mặc định an toàn trong quyết định quyền

Một quyết định truy cập cần có căn cứ về chủ thể, hành động, tài nguyên và điều kiện liên quan. Nếu các điều kiện bắt buộc chưa được chứng minh, không nên đoán một giá trị có lợi cho việc cấp quyền.

Ví dụ:

```text
Không có membership          -> không suy ra thành viên ACTIVE.
Không có role quản trị       -> không suy ra ADMIN.
Không phân giải được tenant  -> không chọn tenant đầu tiên trong danh sách.
Không tìm thấy policy        -> không mở endpoint cho mọi người.
Thiếu thuộc tính bắt buộc    -> không coi điều kiện đã đạt.
```

Điểm quan trọng là phân biệt “không có dữ liệu”, “dữ liệu không hợp lệ” và “dữ liệu xác nhận được phép”. Cả ba không được bị gom thành cùng một nhánh ALLOW.

Một mẫu khái niệm:

```text
authorize(request):
    identity = verifyIdentityWhenRequired(request)
    target = resolveTargetFromTrustedSources(request)

    if target is invalid:
        rejectWithoutProtectedData()

    inputs = collectRequiredPolicyInputs(identity, target)

    if requiredInputsAreMissingOrInvalid(inputs):
        rejectOrReportEvaluationFailure()

    decision = evaluatePolicy(inputs)

    if decision is not a valid ALLOW:
        rejectOrReportEvaluationFailure()

    if requiredRestrictionsCannotBeEnforced(decision):
        rejectWithoutProtectedData()

    executeOnlyTheAuthorizedOperation(target, decision)
```

Đây là pseudocode về trách nhiệm. Nó không quy định một mã lỗi HTTP chung hoặc bắt mọi tài nguyên công khai phải có tài khoản. Quyền truy cập công khai cũng cần được xác định rõ bằng policy cho đúng hành động và tài nguyên, thay vì phát sinh vì một nhánh kiểm tra bị thiếu.

## 4. Tài khoản, membership và role mặc định

### 4.1. Tài khoản mới

Tạo tài khoản chỉ thiết lập một danh tính hoặc hồ sơ trong hệ thống. Nó không mặc nhiên chứng minh người đăng ký thuộc một doanh nghiệp hoặc đủ quyền quản trị tenant.

Một thiết kế cần định nghĩa rõ:

- Điều kiện kích hoạt tài khoản.
- Quyền cơ bản nào phục vụ chính tài khoản đó.
- Điều kiện gia nhập tenant.
- Ai có thẩm quyền cấp role.
- Những hành động cần xác minh bổ sung.

Nếu người dùng có thể tự sửa hồ sơ, tập trường được phép sửa không được bao gồm role quản trị chỉ vì role nằm trong cùng entity.

### 4.2. Membership mới

Một lời mời chưa được chấp nhận không nên tự tạo quyền truy cập đầy đủ. Tùy mô hình, invitation có thể tồn tại riêng hoặc membership ở trạng thái chờ cho tới khi hoàn tất các điều kiện.

Khi một user chưa có membership trong tenant đang yêu cầu, không gán một role mặc định của tenant để “giúp họ vào được ứng dụng”.

Nếu sản phẩm hỗ trợ người dùng tự tạo tenant, quyền của người tạo tenant có thể là một phần hợp lệ của workflow. Nhưng quyền đó cần được cấp có chủ đích sau khi kiểm tra điều kiện tạo, gắn với đúng tenant và không biến thành quyền quản trị toàn nền tảng.

### 4.3. Nhóm và kế thừa

Role mặc định của một nhóm lớn có thể trở thành nguồn quyền rất rộng. Cần đánh giá cả quyền trực tiếp, role kế thừa và mapping từ nguồn bên ngoài.

Không tự ánh xạ một nhóm có tên “Administrators” trong mọi nguồn danh tính thành role quản trị nền tảng. Mapping cần được cấu hình bởi bên có thẩm quyền, gắn với đúng kết nối và đúng tenant.

Những trạng thái như null, chuỗi rỗng hoặc giá trị enum không biết cần được xử lý rõ. Không chuyển chúng thành role mạnh hơn hoặc trạng thái ACTIVE để tránh lỗi tương thích.

## 5. Secure default cho tài nguyên và chia sẻ dữ liệu

Mặc định an toàn cần xuất hiện ở các tài nguyên được tạo mới, không chỉ ở trang cài đặt hệ thống.

| Đối tượng | Mặc định minh họa phù hợp | Hành động cần chủ động cấp phép |
|---|---|---|
| Tài liệu mới | Private hoặc theo phạm vi kế thừa đã được kiểm tra | Chia sẻ ra ngoài phạm vi ban đầu |
| Báo cáo xuất | Chỉ bên được cấp quyền tải | Tạo liên kết chia sẻ cho bên khác |
| Tenant mới | Cách ly với tenant khác | Cấp quyền hỗ trợ hoặc tích hợp có phạm vi |
| API key mới | Phạm vi tối thiểu được chọn rõ | Thêm hành động hoặc tài nguyên |
| Service account mới | Chưa có grant ngoài workflow cấp quyền | Gán role vận hành phù hợp |
| Endpoint mới | Nằm trong cơ chế bảo vệ mặc định | Công khai theo policy cụ thể |

Private không có nghĩa “mọi người đã đăng nhập đều được đọc”. Cần xác định rõ chủ thể hoặc nhóm nào được cấp quyền trong phạm vi đó.

Nếu tài nguyên kế thừa quyền từ project hoặc thư mục, ứng dụng cần kiểm tra việc tạo trong nơi đó và hiểu đúng tập quyền kế thừa. Một tùy chọn có tên “default visibility” không tự bảo đảm quyền thực tế là hẹp.

Việc mở rộng chia sẻ nên làm rõ ai được truy cập, hành động gì được phép và giới hạn hiệu lực nếu có. Không tự chọn “anyone with the link” chỉ vì client không gửi trường visibility.

Dữ liệu nhạy cảm cũng không nên xuất hiện mặc định trong log, thông báo lỗi, trang debug hoặc response serialize từ entity. Cần chủ động chọn thông tin được phép công bố theo mục đích.

## 6. Cấu hình thiếu hoặc không hợp lệ

### 6.1. Thiếu cấu hình không đồng nghĩa tắt bảo vệ

Một mẫu nguy hiểm:

```text
nếu không tìm thấy cấu hình authentication:
    bỏ qua xác thực
```

Nếu một file không được mount, một biến môi trường bị đặt sai tên hoặc một secret chưa được cấp, ứng dụng có thể vô tình mở dữ liệu ra ngoài.

Với cấu hình thiết yếu để bảo vệ tài nguyên, có thể cần từ chối khởi động phần chức năng được bảo vệ hoặc giữ nó chưa sẵn sàng cho tới khi cấu hình hợp lệ. Đường kiểm tra sức khỏe phục vụ vận hành, nếu có, cần có phạm vi riêng và không tiết lộ dữ liệu hoặc secret.

Không để service nhận request nghiệp vụ trong khoảng trống trước khi policy và thành phần xác thực cần thiết được nạp xong.

### 6.2. Kiểm tra kiểu và giá trị

Một cấu hình cần phân biệt:

- Không có key.
- Giá trị rỗng.
- Sai kiểu.
- Giá trị ngoài tập được hỗ trợ.
- Giá trị hợp lệ được chọn có chủ đích.

Không dùng cách ép kiểu mơ hồ để quyết định bật hoặc tắt xác thực. Ví dụ, một chuỗi chứa chữ “false” không nên được diễn giải tùy tiện như một cờ bảo mật; schema phải xác định kiểu và parser phải kiểm tra nó.

Danh sách nguồn danh tính được chấp nhận bị rỗng cũng không nên tự mang nghĩa “chấp nhận mọi nguồn”. Ý nghĩa rỗng phải được định nghĩa rõ và kiểm tra trong môi trường đích.

### 6.3. Cấu hình có hiệu lực mới là điều cần đánh giá

Giá trị trong file mẫu có thể bị ghi đè bởi biến môi trường, cấu hình runtime hoặc một nguồn phân phối khác. Cần biết thứ tự ưu tiên và giá trị có hiệu lực cuối cùng.

Có thể hiển thị các trạng thái bảo mật không chứa secret cho người vận hành được phép, như chế độ enforcement, phiên bản policy hoặc tập nguồn đã cấu hình. Không in toàn bộ credential để chứng minh rằng cấu hình đã được đọc.

### 6.4. Nạp lại cấu hình

Khi cập nhật policy, cần tránh một khoảng thời gian hệ thống đã xóa bản cũ nhưng chưa xác nhận bản mới.

Có thể kiểm tra cấu hình mới rồi thay thế nguyên tử. Nếu giữ bản hợp lệ trước đó khi cập nhật lỗi, cần có chính sách về hiệu lực, độ mới và xử lý thu hồi; không coi “bản tốt gần nhất” là quyền tồn tại vô hạn.

## 7. Xác thực, token và phiên mặc định

Secure default ở lớp xác thực có thể bao gồm:

- Không có tài khoản quản trị với mật khẩu chung được biết trước.
- Credential được phát hành riêng và có cách quản lý vòng đời.
- Chỉ chấp nhận nguồn danh tính và loại credential đã cấu hình.
- Kiểm tra tính toàn vẹn, hiệu lực và đích sử dụng phù hợp.
- Không tự hạ xuống một cơ chế yếu hơn khi luồng chính lỗi.
- Có giới hạn vòng đời phiên hoặc credential theo thiết kế.
- Quy trình khôi phục tài khoản được bảo vệ tương xứng với tác động.

Một access token không nên mặc định mang mọi scope hoặc được chấp nhận bởi mọi API. Token có hiệu lực về chữ ký vẫn cần khớp mục đích và phạm vi sử dụng.

Trong ứng dụng web, cookie phiên cần có các thuộc tính bảo vệ phù hợp với kiến trúc trình duyệt và cách triển khai. Không để mặc định thuận tiện cho môi trường thử nghiệm trở thành cấu hình production, chẳng hạn truyền phiên qua đường không được bảo vệ hoặc mở rộng phạm vi cookie không cần thiết.

Độ dài phiên và thời hạn token cần dựa trên mô hình rủi ro, khả năng thu hồi và nhu cầu sử dụng. Không có một con số mặc định phù hợp cho mọi loại người dùng, workload và hành động.

### Khởi tạo quản trị viên đầu tiên

Hệ thống có thể cần một bước bootstrap có quyền cao. Thiết kế an toàn cần làm rõ:

- Ai được phép thực hiện thiết lập.
- Bằng chứng hoặc credential bootstrap được cấp qua kênh nào.
- Phạm vi và thời hạn của khả năng bootstrap.
- Cách ngăn hai yêu cầu cạnh tranh tạo quản trị viên ngoài ý muốn.
- Cách đóng luồng thiết lập sau khi hoàn tất.
- Cách ghi nhận kết quả mà không lộ secret.

Không mặc định người đăng ký công khai đầu tiên trở thành quản trị viên chỉ vì bảng user đang rỗng. Việc xác định “chưa thiết lập” phải gắn với một quy trình có thẩm quyền, không chỉ một điều kiện đếm bản ghi.

## 8. Kết nối danh tính, SSO và provisioning

Một kết nối bên ngoài có thể xác thực người dùng hoặc cung cấp thuộc tính, nhưng hệ thống vẫn cần quyết định nguồn nào có thẩm quyền với tenant và role.

Các mặc định cần tránh:

| Mặc định nguy hiểm | Hướng xử lý |
|---|---|
| Nguồn phát hành lạ được chấp nhận khi chưa có allowlist | Chỉ chấp nhận nguồn đã được cấu hình và xác minh |
| Email giống tên miền công ty tự tạo ADMIN | Gia nhập và cấp role theo workflow được phê duyệt |
| SSO thành công tự tạo membership ở mọi tenant | Ràng buộc với đúng kết nối và chính sách tenant |
| Cùng chuỗi email tự gộp tài khoản | Liên kết danh tính bằng bằng chứng và quy tắc đã xác định |
| Nhóm chưa được mapping nhận role mạnh mặc định | Không cấp đặc quyền khi chưa có mapping hợp lệ |
| Lỗi SSO chuyển sang tài khoản quản trị cục bộ dùng chung | Có quy trình phục hồi riêng, không hạ cấp tự động |
| Provisioning tái kích hoạt mọi membership đã bị loại bỏ | Xác định thẩm quyền tái cấp và trạng thái chặn |

Just-in-time provisioning có thể là một lựa chọn hợp lệ, nhưng việc bật nó phải đi cùng điều kiện gia nhập, phạm vi tenant và role ban đầu. Không coi JIT là cơ chế chấp nhận mọi danh tính mà nhà cung cấp bên ngoài trả về.

Một tenant bị khóa hoặc đang offboarding không được hồi sinh chỉ vì đồng bộ nhận thêm thuộc tính. Trạng thái vòng đời cần tiếp tục là điều kiện thực thi tại các luồng cấp quyền.

## 9. Lỗi runtime không tạo ra quyền mới

Fail secure là phần quan trọng để mặc định an toàn không biến mất khi có lỗi.

Một mẫu cần tránh:

```text
try:
    return policy.evaluate(request)
catch:
    return ALLOW
```

Nếu PDP timeout, không lấy được membership hoặc không phân giải được resource, hệ thống cần xử lý lỗi mà vẫn giữ ranh giới dữ liệu.

Cần phân biệt một kết quả DENY hợp lệ với lỗi không thể đánh giá. Cách phản hồi và giám sát có thể khác nhau, nhưng cả hai đều không tự cấp quyền cho thao tác được bảo vệ.

Một số trường hợp:

| Sự cố | Hành vi bảo vệ cần giữ |
|---|---|
| Không xác minh được credential | Không tạo identity context đã xác thực |
| Membership không tra cứu được | Không đoán ACTIVE cho hành động cần membership |
| Policy không có quy tắc phù hợp | Không tự cho phép |
| PDP trả giới hạn mà PEP không hiểu | Không bỏ qua giới hạn bắt buộc rồi thực hiện |
| Tenant không xác định | Không chọn tenant mặc định tùy ý |
| Cache hết hiệu lực | Không giữ ALLOW vô hạn |
| Hệ thống thu hồi lỗi | Không tuyên bố quyền đã mất hiệu lực khi chưa có bằng chứng |

Hệ thống có thể thiết kế chế độ hoạt động suy giảm, như đánh giá bằng policy cục bộ đã được xác thực trong một giới hạn thời gian. Chế độ đó cần có phạm vi và điều kiện rõ ràng. Nó không phải một nhánh tiện lợi mở mọi request khi dịch vụ phụ thuộc gặp sự cố.

Mục tiêu vận hành là bảo đảm các chức năng được phép vẫn hoạt động bằng kiến trúc sẵn sàng phù hợp, thay vì bỏ kiểm soát quyền để đạt uptime.

## 10. Ví dụ cấu hình minh họa

Đoạn YAML sau là schema giả định để mô tả lựa chọn thiết kế. Nó không phải cấu hình của một framework hoặc sản phẩm có thể áp dụng trực tiếp.

```yaml
authentication:
  required_for_protected_routes: true
  accepted_identity_sources:
    - approved-company-login

authorization:
  unmatched_request: DENY
  evaluation_failure: REJECT_PROTECTED_OPERATION
  unknown_required_restriction: REJECT_PROTECTED_OPERATION

membership:
  self_registration_grants_tenant_access: false
  initial_status_for_approval_workflow: PENDING

resources:
  initial_visibility: PRIVATE
  external_sharing_requires_permission: true

credentials:
  unrestricted_scope_by_default: false
  explicit_lifetime_required: true

audit:
  include_credentials: false

runtime:
  allow_insecure_development_overrides_in_production: false
```

Điểm cần hiểu không nằm ở tên key mà ở hành vi thực tế:

- Parser phải kiểm tra schema và kiểu.
- Khóa không được hỗ trợ không nên bị bỏ qua âm thầm nếu làm người vận hành tưởng kiểm soát đã bật.
- Service phải thực sự sử dụng các lựa chọn trong quyết định và enforcement.
- Các nguồn ghi đè không được vô tình làm mất ràng buộc production.
- Phải có kiểm tra hành vi, không chỉ đọc thấy một file cấu hình có vẻ an toàn.

Trạng thái PENDING trong ví dụ thuộc một workflow cần phê duyệt. Một sản phẩm có workflow gia nhập khác có thể chọn biểu diễn khác, nhưng vẫn phải chứng minh căn cứ cấp quyền. Không sao chép một giá trị enum mà bỏ qua mô hình nghiệp vụ.

## 11. Ngoại lệ, môi trường thử nghiệm và thay đổi mặc định

### 11.1. Ngoại lệ phải là một quyết định có phạm vi

Nếu cần mở một tài nguyên công khai hoặc cấp quyền tạm thời, hãy làm rõ:

- Đối tượng và hành động được mở.
- Ai được phê duyệt.
- Lý do và thời hạn.
- Những điều kiện vẫn phải được áp dụng.
- Cách thu hồi và bằng chứng kết quả.

Một ngoại lệ cho một tài liệu không nên trở thành cờ `skipAuthorization` áp dụng cho cả tenant hoặc toàn ứng dụng.

Người có quyền sửa ngoại lệ thực chất có khả năng thay đổi ranh giới truy cập. Quyền này cần được bảo vệ và audit tương ứng.

### 11.2. Development không được tự biến thành production

Môi trường phát triển có thể dùng nguồn danh tính giả hoặc dữ liệu mẫu. Những khả năng này cần được tách rõ, không được kích hoạt chỉ vì production thiếu một cấu hình.

Không nên có logic “không thấy secret thì dùng credential mẫu”. Với một phần chức năng được bảo vệ, thiếu secret quan trọng phải được thể hiện thành trạng thái lỗi thiết lập, không thành một deployment dễ truy cập hơn.

Tài liệu ví dụ và template cũng ảnh hưởng tới mặc định thực tế vì chúng thường được sao chép. Không để template tạo ADMIN hàng loạt hoặc khuyến nghị wildcard chỉ để thao tác demo chạy nhanh.

### 11.3. Thay đổi mặc định trên hệ thống hiện có

Một phiên bản mới chuyển mặc định từ public sang private có thể ảnh hưởng dữ liệu và workflow hiện tại. Cần phân biệt:

- Giá trị áp dụng cho tài nguyên tạo mới.
- Giá trị hiện có đã được người có thẩm quyền chọn.
- Trường cũ bị thiếu do schema trước chưa có.
- Dữ liệu không hợp lệ.

Không tự suy diễn mọi giá trị thiếu trong dữ liệu cũ đều mang cùng ý nghĩa. Cần có kế hoạch migration, phạm vi kiểm chứng và cách xử lý ngoại lệ. Mục tiêu an toàn không phải lý do để âm thầm sửa các quyết định đã được phê duyệt mà chưa đánh giá tác động.

Khi triển khai cấu hình mới, cần kiểm tra các phiên bản service có hiểu cùng schema và cùng nghĩa mặc định không. Một PEP cũ bỏ qua field mới có thể làm kiểm soát tưởng đã bật nhưng chưa được thực thi.

## 12. Các tình huống cần kiểm chứng

Một thiết kế secure default cần được kiểm tra cả khi người vận hành không điền gì thêm và khi hệ thống gặp dữ liệu hoặc lỗi bất thường.

| Tình huống | Kết quả mong đợi |
|---|---|
| Tạo user mới | Không tự có đặc quyền ngoài workflow được phép |
| Tạo tài liệu mà không gửi visibility | Áp dụng phạm vi bảo vệ mặc định đã định nghĩa |
| Tạo endpoint mới chưa có policy cho phép | Không tự công khai tài nguyên được bảo vệ |
| Thiếu cấu hình xác thực production | Không chuyển sang bỏ xác thực |
| Allowlist nguồn danh tính rỗng | Không tự chấp nhận mọi nguồn |
| Gửi role hoặc trạng thái không biết | Không nâng quyền bằng fallback |
| PDP timeout | Không tự tạo ALLOW |
| Membership bị thu hồi nhưng token còn hạn | Tuân theo cơ chế hiệu lực và thu hồi đã thiết kế |
| Nạp policy mới không hợp lệ | Không tạo khoảng trống bỏ enforcement |
| Client yêu cầu chia sẻ ra ngoài tenant | Cần permission và phạm vi thích hợp |
| Có override phát triển trong production | Bị chặn hoặc phát hiện theo cơ chế kiểm soát đã thiết kế |
| Provisioning gửi dữ liệu vào tenant đã khóa | Không tự tái kích hoạt quyền |
| Bootstrap đã hoàn tất | Không tiếp tục cấp quản trị qua luồng thiết lập |
| Log lỗi chứa credential đầu vào | Không ghi credential vào log |

Các chỉ dấu vận hành hữu ích gồm cấu hình ghi đè làm giảm bảo vệ, tài nguyên công khai, grant mặc định quá rộng, endpoint thiếu policy và lỗi nạp cấu hình. Thông tin quan sát cần đủ để phát hiện sai lệch nhưng không làm lộ secret.

Secure default giúp hệ thống giữ được ranh giới bảo vệ ngay từ khi tài khoản, tài nguyên hoặc deployment được tạo. Giá trị của nguyên tắc này nằm ở hành vi thực thi: thiếu cấu hình không mở quyền, lỗi không làm mất bảo vệ, và việc mở rộng truy cập luôn là một quyết định rõ ràng có phạm vi.
