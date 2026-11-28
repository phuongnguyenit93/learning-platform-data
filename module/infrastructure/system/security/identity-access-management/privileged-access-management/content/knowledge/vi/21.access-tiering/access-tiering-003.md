# Tier 2 workstation identity — Danh tính trong lớp quản trị máy trạm Tier 2

## 1. Hiểu phạm vi Tier 2 trước khi cấp quyền

Trong một mô hình phân tầng quản trị thường gặp:

- **Tier 0** bao gồm các thành phần và quyền có thể kiểm soát danh tính hoặc nền tảng tin cậy.
- **Tier 1** bao gồm các hệ thống máy chủ, nền tảng và ứng dụng theo phạm vi tổ chức xác định.
- **Tier 2** bao gồm máy trạm người dùng và công việc hỗ trợ, quản trị các endpoint thuộc lớp đó.

Đây là mô hình khái niệm để thiết kế ranh giới tin cậy. Không phải mọi tổ chức hay nền tảng đều dùng cùng số tầng hoặc cùng cách phân loại. Trong bài học này, Tier 0 có mức tác động tới nền tảng tin cậy cao hơn Tier 2; số lớn hơn không có nghĩa quyền cao hơn.

**Tier 2 workstation identity** cần được xem ở nhiều lớp:

1. Danh tính thiết bị của máy trạm.
2. Danh tính cá nhân dùng cho công việc thường ngày.
3. Danh tính quản trị dùng để hỗ trợ máy trạm.
4. Danh tính kỹ thuật của agent, dịch vụ hoặc công cụ quản lý endpoint.
5. Tài khoản cục bộ trên từng máy.

Nếu gộp các lớp này, tổ chức dễ nhầm rằng “máy đã được đăng ký” đồng nghĩa “người đang dùng máy được quản trị”, hoặc “quản trị viên máy trạm” đồng nghĩa “được quản trị máy chủ và danh tính”.

Trong PAM, mục tiêu là cho đội hỗ trợ làm đúng công việc trên máy trạm được giao, đồng thời ngăn credential và quyền vượt qua ranh giới phân tầng ngoài ý muốn.

## 2. Phân biệt các loại danh tính

### 2.1. Danh tính thiết bị

Danh tính thiết bị biểu diễn một endpoint trong hệ thống quản lý hoặc hạ tầng danh tính. Tùy kiến trúc, nó có thể gắn với đối tượng máy, khóa, chứng thư hoặc cơ chế đăng ký thiết bị.

Danh tính này có thể hỗ trợ xác định:

- Thiết bị nào đang kết nối.
- Nó có thuộc phạm vi quản lý không.
- Khóa hoặc bằng chứng thiết bị có hợp lệ không.
- Trạng thái và phân loại thiết bị theo nguồn có thẩm quyền.

Nó không tự xác nhận người đang thao tác là ai hoặc người đó có quyền gì.

Tên máy hoặc một header tự khai không phải bằng chứng đủ về danh tính thiết bị.

### 2.2. Danh tính người dùng thường ngày

Người dùng dùng danh tính này để đọc email, sử dụng ứng dụng và làm công việc nghiệp vụ.

Tài khoản thường ngày không nên mặc nhiên có quyền quản trị cục bộ rộng hoặc quyền quản trị hạ tầng chỉ vì người sở hữu cũng làm công việc kỹ thuật.

Một người có thể được phân công nhiều trách nhiệm, nhưng cần tách cách sử dụng và quyền tương ứng. Danh tính thường ngày có phiên trên máy trạm tiếp xúc với nội dung từ nhiều nguồn, nên việc gắn thêm quyền đặc biệt cao làm tăng hậu quả khi máy bị ảnh hưởng.

### 2.3. Danh tính quản trị Tier 2

Đây là danh tính được dùng cho các tác vụ hỗ trợ máy trạm trong phạm vi cụ thể.

Ví dụ:

- Xem trạng thái endpoint được giao.
- Triển khai một gói phần mềm đã được phê duyệt.
- Chạy tác vụ sửa chữa được đóng gói.
- Quản lý một số cấu hình của máy trạm.
- Lấy credential cục bộ của một máy theo quy trình PAM.
- Thực hiện một số thao tác khôi phục cho người dùng thường theo ủy quyền.

Quyền quản trị Tier 2 không tự bao gồm quyền trên máy chủ, CA, IdP, PAM hoặc tài khoản quản trị Tier 0/Tier 1.

### 2.4. Danh tính của agent hoặc dịch vụ quản lý endpoint

Một agent có thể chạy với quyền cao trên máy trạm để cập nhật, kiểm kê hoặc hỗ trợ. Danh tính của agent khác với người hỗ trợ.

Cần xác định:

- Agent xác thực tới dịch vụ điều khiển như thế nào.
- Dịch vụ điều khiển được phép gửi loại tác vụ nào.
- Ai được tạo, duyệt hoặc thay đổi tác vụ.
- Phạm vi thiết bị của từng người vận hành.
- Credential và token của agent được giới hạn ra sao.

Nếu một nền tảng có thể chạy mã trên mọi PAW và hệ thống nhạy cảm, nền tảng đó có khả năng điều khiển lớn hơn một công cụ hỗ trợ endpoint thông thường. Phải phân loại theo khả năng thực tế.

### 2.5. Tài khoản quản trị cục bộ

Tài khoản cục bộ tồn tại trên từng máy, không đồng nghĩa với tài khoản hỗ trợ trong directory.

Nếu nhiều máy dùng cùng một mật khẩu quản trị cục bộ, việc lộ một bí mật có thể ảnh hưởng nhiều endpoint. Cần quản lý credential riêng theo thiết bị, quyền truy xuất và vòng đời phù hợp.

| Loại danh tính | Đại diện cho | Không tự chứng minh |
|---|---|---|
| Thiết bị | Endpoint đã được đăng ký theo cơ chế | Người dùng đủ quyền quản trị |
| Người dùng thường | Cá nhân làm công việc hằng ngày | Quyền quản trị máy trạm hoặc máy chủ |
| Quản trị Tier 2 | Người thực hiện công việc hỗ trợ được giao | Quyền quản trị các tầng khác |
| Agent hoặc workload | Thành phần kỹ thuật | Thẩm quyền tùy ý của người gửi tác vụ |
| Tài khoản cục bộ | Chủ thể trên một máy | Danh tính cá nhân thực sự sử dụng nếu có dùng chung |

## 3. Ranh giới quan trọng: Tier 2 không phải nơi để dùng danh tính quyền cao hơn

### 3.1. Vì sao đăng nhập chéo tầng gây rủi ro?

Máy trạm người dùng có thể tiếp xúc với trình duyệt, tài liệu, ứng dụng và thiết bị ngoại vi. Khi tài khoản quản trị có phạm vi cao hơn đăng nhập vào endpoint đó, tùy cơ chế đăng nhập, máy có thể tiếp xúc với credential, token, phiên hoặc khả năng sử dụng danh tính.

Ngay cả khi không lấy được mật khẩu, một bên kiểm soát endpoint có thể tìm cách điều khiển phiên hoặc lợi dụng khả năng xác thực còn tồn tại.

Vì vậy, không nên dùng tài khoản quản trị danh tính hoặc máy chủ để thực hiện việc hỗ trợ thông thường trên máy trạm.

### 3.2. Tách danh tính theo nhiệm vụ

Một người có thể có các danh tính minh họa:

~~~text
lan.work          → công việc thường ngày
lan.support.t2    → hỗ trợ máy trạm thuộc phạm vi
lan.ops.t1        → quản trị máy chủ được giao
lan.identity.t0   → công việc quản trị danh tính được giao
~~~

Tên tài khoản chỉ giúp nhận diện. Ranh giới thực sự cần:

- Phân quyền hiệu lực.
- Giới hạn nơi đăng nhập hoặc sử dụng.
- Kiểm soát đường quản trị.
- Quản lý credential và phiên.
- Quy định môi trường nguồn.
- Giám sát và thu hồi.

Đổi tên tài khoản thành hậu tố t2 không làm quyền của nó tự giảm.

### 3.3. Không có kế thừa tự động giữa các tầng

Một tài khoản quản trị tầng nhạy cảm hơn không nên tự được dùng cho mọi tầng thấp hơn chỉ vì có quyền mạnh.

Khi cùng một người cần hỗ trợ máy trạm, họ dùng danh tính và đường hỗ trợ phù hợp với công việc đó. Điều này giúp tránh đưa danh tính có phạm vi cao vào môi trường có thể bị ảnh hưởng.

Ngược lại, tài khoản Tier 2 không được tự nâng lên Tier 1 hoặc Tier 0 vì người sở hữu có trách nhiệm khác trong tổ chức.

### 3.4. Máy trạm quản trị không tự thuộc Tier 2

PAW là một máy trạm về hình thức, nhưng có thể được dùng để quản trị nền tảng danh tính hoặc hệ thống quan trọng.

Nếu đội Tier 2 có quyền điều khiển một PAW đang giữ phiên Tier 0, họ có thể có đường tác động tới quyền cao hơn. Vì vậy cần phân loại theo chức năng và quan hệ điều khiển, không chỉ theo loại thiết bị.

Công cụ quản lý endpoint, nhóm thiết bị và quyền hỗ trợ phải loại trừ hoặc xử lý riêng các máy quản trị nhạy cảm theo mô hình của tổ chức.

## 4. Thiết kế quyền cho danh tính hỗ trợ Tier 2

### 4.1. Bắt đầu từ các tác vụ cụ thể

Không phải mọi việc hỗ trợ đều cần full local administrator.

Ví dụ:

| Nhu cầu | Cách biểu diễn quyền có thể phù hợp |
|---|---|
| Xem tình trạng máy | Đọc thông tin trạng thái được phép |
| Cài ứng dụng chuẩn | Chạy tác vụ triển khai gói đã được quản trị |
| Sửa một dịch vụ endpoint | Action có tham số và tài nguyên giới hạn |
| Hỗ trợ phiên người dùng | Quyền điều khiển hoặc quan sát theo quy trình phù hợp |
| Xem mật khẩu quản trị cục bộ | Checkout cho đúng thiết bị, có thời hạn và bằng chứng |
| Khôi phục tài khoản thường | Action được ủy quyền, loại trừ danh tính đặc quyền |

Các action phải được thực thi ở backend hoặc hệ thống đích. Một lời nhắc “chỉ dùng quyền admin để sửa lỗi” không tạo ra giới hạn kỹ thuật.

### 4.2. Giới hạn theo tập thiết bị

Quyền cần gắn với tập endpoint được giao, chẳng hạn theo đơn vị, địa điểm hoặc chức năng.

Cần giữ đúng quan hệ:

~~~text
Danh tính A được chạy action X trên tập thiết bị R
~~~

Không hợp nhất riêng các action và các thiết bị từ nhiều grant rồi tạo ra mọi kết hợp rộng hơn.

Nếu phạm vi dựa vào group hoặc nhãn, phải kiểm soát ai được thay đổi membership hoặc nhãn. Người hỗ trợ không nên tự đưa một PAW nhạy cảm vào nhóm endpoint mình quản lý.

### 4.3. JIT cho các quyền cần cao hơn

Khi cần quyền quản trị cục bộ rộng, có thể cấp theo JIT nếu nền tảng hỗ trợ:

1. Người hỗ trợ tạo yêu cầu cho thiết bị và công việc cụ thể.
2. Chủ thể có thẩm quyền phê duyệt nếu cần.
3. PAM kiểm tra xác thực, thiết bị nguồn và cửa sổ.
4. Quyền hoặc credential được cung cấp có giới hạn.
5. Hoạt động được ghi nhận.
6. Quyền, phiên và credential được xử lý khi kết thúc.

Phải phân biệt “đủ điều kiện yêu cầu” với “đang có quyền”. Một người thuộc nhóm hỗ trợ không nhất thiết cần quyền thường trực trên mọi endpoint.

### 4.4. Hạn chế quyền tự mở rộng

Các khả năng sau cần được xem xét riêng:

- Thêm chính mình vào nhóm quản trị.
- Thay đổi phạm vi thiết bị.
- Sửa policy cấp quyền.
- Triển khai script tùy ý tới mọi endpoint.
- Đọc credential của toàn bộ máy.
- Thay đổi nguồn hoặc cấu hình quản lý PAW.
- Vô hiệu hóa ghi log hoặc bảo vệ endpoint.

Chúng có thể làm mất ranh giới của các action hỗ trợ còn lại.

## 5. Ủy quyền khôi phục danh tính người dùng

### 5.1. Password reset là một quyền có tác động lớn

Đội hỗ trợ thường cần xử lý tài khoản người dùng. Tuy nhiên, quyền reset mật khẩu hoặc đăng ký lại MFA có thể dẫn tới kiểm soát danh tính đó.

Cần giới hạn:

- Loại tài khoản được xử lý.
- Tập người dùng thuộc phạm vi.
- Các action được phép.
- Quy trình xác minh người yêu cầu.
- Các tài khoản và vai trò phải loại trừ.
- Yêu cầu phê duyệt hoặc độc lập khi cần.

Không chỉ bảo vệ một nhóm có tên administrator. Danh tính nhạy cảm có thể có quyền qua group lồng nhau, role đám mây, ủy quyền hoặc hệ thống khác.

### 5.2. Không để hỗ trợ Tier 2 quản lý authenticator của danh tính tầng cao

Nếu một tài khoản hỗ trợ Tier 2 có thể thay yếu tố MFA hoặc reset mật khẩu của quản trị viên nền tảng tin cậy, nó có thể trở thành đường vượt tầng.

Cần đánh giá quyền hiệu lực và các luồng khôi phục, không chỉ role trên giao diện chính.

Ví dụ, loại trừ tài khoản Tier 0 ở form reset chưa đủ nếu cùng tài khoản hỗ trợ có thể gọi API khác thực hiện thao tác đó.

### 5.3. Danh tính thường ngày cũng có thể nhạy cảm

Một tài khoản không mang hậu tố admin vẫn có thể:

- Sở hữu ứng dụng.
- Quản lý pipeline.
- Giữ token triển khai.
- Có quyền cấp cho workload.
- Được truy cập dữ liệu quan trọng.

Vì vậy, phân loại cần dựa vào quyền thực tế và quan hệ điều khiển. Nhãn “người dùng thường” không thay thế việc kiểm tra các khả năng có thể dẫn tới đặc quyền.

## 6. Quản lý danh tính thiết bị và tài khoản cục bộ

### 6.1. Enrollment và nguồn có thẩm quyền

Danh tính thiết bị cần được tạo qua quy trình đăng ký được quản trị. Cần biết:

- Ai được đưa thiết bị vào quản lý.
- Ai được gán phân loại hoặc nhóm.
- Khóa, chứng thư hoặc bí mật thiết bị được cấp thế nào.
- Thiết bị gắn với chủ sở hữu và trạng thái vòng đời nào.
- Điều kiện để được nhận chính sách hỗ trợ Tier 2.

Không dùng tên máy do người dùng tự nhập làm căn cứ duy nhất. Một thiết bị mang tên giống máy đã được quản lý không tự có cùng danh tính.

### 6.2. Danh tính thiết bị không phải entitlement quản trị

Chứng minh một máy thuộc tổ chức có thể là điều kiện để truy cập. Nó không tự cho người dùng quyền quản trị máy khác hoặc gọi API đặc quyền.

Một quyết định vẫn cần kết hợp:

~~~text
Danh tính người dùng hoặc workload
    + danh tính và trạng thái thiết bị khi cần
    + action
    + tài nguyên
    + điều kiện và thời gian
~~~

Thiết bị được quản lý nhưng người dùng không đủ quyền thì vẫn phải bị từ chối.

### 6.3. Credential quản trị cục bộ theo thiết bị

Nếu cần tài khoản quản trị cục bộ, nên quản lý bí mật riêng theo endpoint và kiểm soát việc truy xuất.

Cần xác định:

- Ai được lấy credential của máy nào.
- Có phê duyệt hoặc lý do nào bắt buộc.
- Credential được dùng qua PAM hay được tiết lộ.
- Khi nào cần đổi hoặc thu hồi.
- Cách cập nhật trạng thái vault và đích.
- Cách phát hiện việc lấy nhiều credential bất thường.

Một quyền xem mật khẩu cục bộ của toàn bộ tổ chức có phạm vi lớn hơn nhiều so với hỗ trợ một thiết bị.

### 6.4. Đổi mật khẩu không tự đóng mọi phiên

Nếu credential đã được dùng để mở phiên, đổi mật khẩu có thể không chấm dứt phiên đó. Cần kiểm tra vòng đời phiên và token của hệ thống đích.

Khi kết thúc công việc hoặc có sự cố, phải xác minh các lớp liên quan thay vì chỉ thấy trạng thái “đã rotate” trong vault.

### 6.5. Reimage, thay thiết bị và loại bỏ

Khi xây dựng lại hoặc thay máy, cần xử lý danh tính cũ theo quy trình:

- Vô hiệu hóa hoặc loại bỏ credential không còn dùng.
- Cấp danh tính phù hợp cho thiết bị mới.
- Tránh sao chép cùng private key hoặc bí mật thiết bị qua ảnh triển khai.
- Cập nhật inventory, chủ sở hữu và phạm vi quản lý.
- Bảo vệ hoặc xử lý dữ liệu theo vòng đời.
- Giữ bằng chứng cần thiết trước khi xóa.

Một máy mới cùng tên không nên âm thầm được coi là chính thiết bị cũ chỉ dựa vào chuỗi tên.

## 7. Đường hỗ trợ qua PAM

### 7.1. Nguồn quản trị phải được chấp nhận

Tài khoản Tier 2 cần được dùng từ môi trường nguồn phù hợp với chính sách hỗ trợ, chẳng hạn một PAW hoặc môi trường quản trị được quản lý.

Không kết luận mọi máy trạm Tier 2 đều đủ tin cậy để giữ credential quản trị của toàn bộ tập endpoint.

Mức bảo vệ của môi trường nguồn phải tương xứng với quyền được sử dụng. Đường quản lý chính môi trường đó cũng cần được xem xét.

### 7.2. Luồng tham chiếu

~~~mermaid
flowchart TD
    A[Người hỗ trợ dùng danh tính Tier 2 riêng] --> B[Xác thực và kiểm tra môi trường nguồn]
    B --> C[Chọn endpoint và action hỗ trợ]
    C --> D[Phân giải danh tính, phân loại và phạm vi tài nguyên]
    D --> E{Đúng phạm vi Tier 2 và đủ điều kiện?}
    E -- Không --> F[Từ chối hoặc chuyển tuyến đúng thẩm quyền]
    E -- Có --> G[Kiểm tra phê duyệt và cửa sổ]
    G --> H[Cấp tác vụ, phiên hoặc credential có giới hạn]
    H --> I[Ghi hoạt động và kết quả]
    I --> J[Kết thúc, thu hồi và xác minh]
~~~

### 7.3. Không đưa danh tính tầng cao vào endpoint để sửa lỗi

Khi gặp tác vụ ngoài phạm vi, người hỗ trợ cần chuyển tuyến hoặc tạo yêu cầu phù hợp. Không đăng nhập bằng tài khoản Tier 0 hoặc Tier 1 trên máy người dùng chỉ để vượt một lỗi quyền.

Nếu công cụ hỗ trợ có cơ chế môi giới xác thực hoặc giảm phơi nhiễm credential, vẫn phải kiểm tra hành vi thực tế. Không suy ra rằng mọi hình thức remote support đều không để lại token hoặc khả năng sử dụng danh tính trên đích.

### 7.4. Giới hạn tác vụ và đường dữ liệu

Phiên hỗ trợ có thể cần kiểm soát clipboard, truyền file, drive redirection hoặc khả năng nhận credential. Các điều kiện này phải phù hợp công việc và khả năng thực thi.

Nếu chỉ cần chạy một tác vụ định sẵn, không nhất thiết cấp một desktop hoặc shell toàn quyền.

Ngược lại, nếu đã cấp một phiên toàn quyền, cần mô tả đúng mức quyền đó. Ghi log không tự biến phiên thành JEA.

## 8. Cấu hình chính sách minh họa

Mô hình dưới đây chỉ diễn tả ý định, không phải cú pháp của một nền tảng cụ thể:

~~~yaml
tier2_support_policy:
  subject_class: "tier2-support-identity"

  source:
    approved_support_environment_required: true
    trusted_recent_device_state_required: true
    suitable_mfa_required: true

  targets:
    classification: "managed-user-workstations"
    assigned_scope_required: true
    privileged_admin_workstations_excluded: true

  capabilities:
    prefer_scoped_support_actions: true
    broad_local_admin_requires_separate_activation: true
    higher_tier_administration_allowed: false

  identity_recovery:
    delegated_standard_users_only: true
    privileged_identities_excluded: true
    verification_process_required: true

  local_credentials:
    unique_per_device_management: true
    scoped_checkout_required: true
    disclosed_secret_lifecycle_managed: true

  lifecycle:
    approved_window_if_required: true
    enforce_expiry: true
    verify_revocation: true

  governance:
    protect_scope_and_classification_changes: true
    record_operator_and_target_identity: true
~~~

Các ràng buộc như privileged_identities_excluded phải được thực thi trên quyền hiệu lực và mọi đường liên quan. Một bộ lọc trên giao diện không đủ.

Mã giả:

~~~text
authorize_tier2_support(connection, request):
    operator = get_authenticated_operator(connection)
    require(operator.identity_class == TIER2_SUPPORT)
    require(operator.is_active)

    source = get_trusted_source_context(connection)
    require(source.is_approved_for_tier2_support)
    require(source.meets_required_current_state)

    target = resolve_managed_target(request.target_id)
    require(target.is_in_assigned_tier2_scope(operator))
    require(not target.is_protected_administrative_endpoint)

    action = resolve_known_support_action(request.action)
    require(operator.has_matching_action_resource_grant(action, target))
    require(action.parameters_are_within_allowed_scope)

    require(required_approval_is_current)
    require(access_window_is_open)
    require(authentication_assurance_is_sufficient)

    issue_bounded_support_operation(operator, action, target)
~~~

Đoạn mã mô tả logic, chưa bao gồm mọi yêu cầu triển khai. Các phân loại và quyền phải đến từ nguồn có thẩm quyền; client không được tự đặt một cờ tier2 để được cấp quyền.

## 9. Những đường vượt tầng thường bị bỏ sót

### 9.1. Nhóm lồng nhau và quyền ngoài directory chính

Một tài khoản Tier 2 có thể gián tiếp thuộc nhóm rộng hoặc có role trong một nền tảng khác.

Cần kiểm tra quyền hiệu lực, bao gồm:

- Membership trực tiếp và gián tiếp.
- Role ứng dụng hoặc đám mây.
- Quyền reset, thay MFA hoặc cấp credential.
- Quyền sửa automation.
- Quyền quản lý thiết bị và tác vụ triển khai.
- Quyền thay nhãn hoặc phân loại tài nguyên.

Một báo cáo chỉ kiểm tra nhóm có tên quen thuộc có thể bỏ sót quan hệ kiểm soát quan trọng.

### 9.2. Nền tảng quản lý endpoint bao phủ PAW

Nếu một người hỗ trợ có thể đẩy script tới PAW của quản trị viên danh tính, quyền đó có thể tác động tới Tier 0.

Cần tách phạm vi, role, nguồn quản lý hoặc cơ chế kiểm soát phù hợp. Không chỉ đặt PAW vào một nhóm có tên khác nếu người Tier 2 vẫn sửa được membership của nhóm.

### 9.3. Tài khoản người dùng có phiên đặc quyền trên máy thường

Tách tài khoản không có ích đầy đủ nếu danh tính tầng cao vẫn được dùng trên máy thường.

Cần kiểm tra nơi credential, token và phiên thực sự xuất hiện. Hành vi đăng nhập phải phù hợp với phân tầng đã thiết kế.

### 9.4. Công cụ chẩn đoán và điều khiển từ xa

Quyền thu thập dữ liệu, điều khiển màn hình hoặc chạy tác vụ có thể tạo ảnh hưởng lớn. Phải phân loại theo khả năng thực tế, không chỉ tên “read-only support”.

Ví dụ, quyền xem màn hình có thể tiếp xúc với dữ liệu nhạy cảm; quyền chạy công cụ chẩn đoán tùy ý có thể rộng hơn đọc trạng thái.

### 9.5. Credential dùng lại trên nhiều máy

Một credential dùng chung tạo quan hệ tin cậy giữa các endpoint. Khi một máy bị ảnh hưởng, phạm vi tác động có thể lan sang máy khác.

Quản lý bí mật riêng, tác vụ có giới hạn và kiểm soát đường sử dụng giúp giảm rủi ro, nhưng vẫn cần kiểm tra quyền của tài khoản và khả năng truy cập thực tế.

## 10. Bằng chứng và vòng đời danh tính Tier 2

### 10.1. Ghi nhận đúng chủ thể

Một phiên hỗ trợ cần liên kết được:

~~~text
Người được phân công hỗ trợ
    → danh tính Tier 2 đã xác thực
    → môi trường nguồn
    → request và phê duyệt
    → endpoint và danh tính thiết bị
    → action hoặc phiên đích
    → tài khoản kỹ thuật nếu có
    → kết quả và thu hồi
~~~

Nếu dùng tài khoản cục bộ chung cho một máy, cần biết cá nhân nào đã lấy và sử dụng. Không ghi như thể hệ thống đích đã trực tiếp xác thực danh tính cá nhân nếu thực tế chỉ thấy tài khoản kỹ thuật.

### 10.2. Sự kiện cần quan sát

Ví dụ:

- Danh tính Tier 0/Tier 1 xuất hiện trên endpoint Tier 2 ngoài chính sách.
- Danh tính hỗ trợ Tier 2 cố dùng quyền trên tài nguyên khác tầng.
- Lấy credential cục bộ của nhiều máy ngoài công việc dự kiến.
- Thay đổi nhóm thiết bị hoặc phạm vi hỗ trợ.
- Reset hoặc thay MFA cho một danh tính được bảo vệ.
- Triển khai tác vụ tới PAW nhạy cảm.
- Quyền JIT không được thu hồi hoàn tất.
- Đăng nhập bằng danh tính đã ngừng phân công.

Không ghi mật khẩu, token hoặc private key vào log. Bằng chứng phải đủ đối chiếu mà không tạo thêm kho bí mật.

### 10.3. Thay đổi nhiệm vụ và nghỉ việc

Khi người hỗ trợ chuyển nhóm hoặc ngừng công việc:

- Thu hồi eligibility và grant không còn phù hợp.
- Xử lý phê duyệt hoặc yêu cầu đang chờ.
- Hủy phiên và token theo chính sách.
- Xem credential đã được tiết lộ.
- Thu hồi quyền trong các nền tảng liên quan.
- Cập nhật người chịu trách nhiệm và ủy quyền.

Khóa một tài khoản ở directory không tự bảo đảm mọi phiên hoặc credential trên đích đã hết hiệu lực.

### 10.4. Rà soát định kỳ

Rà soát nên kiểm tra quyền thực tế và mẫu sử dụng:

- Ai còn cần hỗ trợ tập máy nào?
- Quyền nào có thể thu hẹp thành action?
- Có quyền rộng được cấp tạm nhưng chưa hết không?
- Có endpoint nào bị phân loại sai?
- Có công cụ quản lý nào tạo đường tới tầng cao hơn?
- Có phiên của danh tính tầng cao trên máy thường không?

Không chỉ xác nhận một danh sách tài khoản còn tồn tại.

## 11. Xử lý khi một danh tính hoặc endpoint Tier 2 bị ảnh hưởng

### 11.1. Xác định phạm vi tác động

Một sự cố Tier 2 không nên bị xem nhẹ chỉ vì tên tầng. Máy trạm có thể giữ dữ liệu, token và phiên ứng dụng quan trọng.

Cần xác định:

- Danh tính người dùng và hỗ trợ nào đã xuất hiện.
- Credential hoặc token nào có thể bị sử dụng.
- Tài khoản cục bộ có dùng chung không.
- Endpoint nào đã được quản trị.
- Có quyền trên nền tảng khác không.
- Có dấu hiệu sử dụng danh tính tầng cao trên máy không.
- Có thay đổi group, policy hoặc tác vụ quản lý endpoint không.

### 11.2. Khoanh vùng và thu hồi

Theo quy trình ứng phó, có thể cần cô lập endpoint, chặn danh tính, thu hồi phiên hoặc quyền, xử lý credential và giữ bằng chứng.

Nếu có nghi ngờ về credential tầng cao đã xuất hiện trên máy, phạm vi điều tra phải mở rộng tương ứng. Không chỉ đổi mật khẩu cục bộ rồi kết luận ranh giới tầng chưa bị ảnh hưởng.

### 11.3. Khôi phục từ môi trường đáng tin cậy

Việc xử lý danh tính và quyền nên được điều phối từ một môi trường còn đủ tin cậy.

Có thể cần xây dựng lại máy, cấp lại danh tính thiết bị và xác minh baseline. Nếu nguồn quản lý hoặc triển khai bị ảnh hưởng, phải giải quyết nguồn đó trước khi coi thiết bị xây dựng lại là đáng tin.

Sau khôi phục, kiểm tra cả đường hỗ trợ, quyền hiệu lực và các phiên còn tồn tại.

## 12. Tình huống: helpdesk cần sửa máy người dùng

Một nhân viên gặp lỗi ứng dụng trên laptop được quản lý. Người hỗ trợ có:

~~~text
Danh tính thường: minh.work
Danh tính hỗ trợ: minh.support.t2
Phạm vi: endpoint của đơn vị được giao
Action: đọc trạng thái và triển khai gói sửa chữa chuẩn
~~~

Quy trình:

1. Người hỗ trợ dùng môi trường nguồn được phê duyệt.
2. Đăng nhập bằng minh.support.t2 và xác thực phù hợp.
3. Chọn endpoint theo định danh từ inventory, không chỉ tên do người gọi cung cấp.
4. PAM kiểm tra phạm vi thiết bị, action và điều kiện.
5. Tác vụ sửa chữa chạy bằng cơ chế được quản lý.
6. Danh tính người khởi tạo và danh tính thực thi được liên kết.
7. Kết quả được ghi nhận và quyền tạm thời kết thúc.

Nếu cần local administrator, người hỗ trợ tạo yêu cầu bổ sung theo chính sách. Nếu endpoint thực tế là PAW quản trị danh tính bị phân loại sai, luồng Tier 2 phải bị chặn và chuyển đến tuyến phù hợp.

Người hỗ trợ không dùng một tài khoản quản trị Tier 0 để vượt lỗi. Cũng không được reset MFA của người quản trị Tier 0 dưới danh nghĩa “khôi phục người dùng”.

Tình huống này cho thấy ranh giới nằm ở quyền và đối tượng thực tế, không chỉ ở việc dùng một tài khoản khác tên.

## 13. Kiểm chứng trước khi áp dụng

Kiểm thử cần bao phủ danh tính, phạm vi, đường truy cập và vòng đời.

| Ca kiểm thử | Kết quả cần đạt |
|---|---|
| Tài khoản thường yêu cầu action hỗ trợ | Không tự có quyền của danh tính Tier 2 |
| Thiết bị hợp lệ nhưng người dùng không đủ quyền | Bị từ chối |
| Client tự khai tên hoặc tầng thiết bị | Không thay thế được nguồn phân loại đáng tin cậy |
| Danh tính Tier 2 chọn endpoint ngoài phạm vi | Bị chặn |
| Có action trên máy A và action khác trên máy B | Không tạo ra mọi tổ hợp quyền mới |
| Danh tính Tier 2 yêu cầu quản trị máy chủ hoặc IdP | Không được cấp ngoài thẩm quyền |
| Danh tính tầng cao cố đăng nhập endpoint Tier 2 | Bị chặn hoặc phát hiện đúng chính sách đã thiết kế |
| PAW nhạy cảm xuất hiện trong nhóm máy thường | Được phát hiện và không âm thầm mở quyền hỗ trợ |
| Người hỗ trợ sửa membership để mở rộng phạm vi | Không tự cấp quyền ngoài quy trình |
| Reset hoặc thay MFA của danh tính được bảo vệ | Bị chặn trên cả giao diện và các đường liên quan |
| Lấy mật khẩu cục bộ của máy không được giao | Bị từ chối |
| JIT hết hạn khi phiên còn mở | Quyền và phiên được xử lý theo cơ chế công bố |
| Đổi mật khẩu cục bộ sau sử dụng | Xác minh cả credential mới và phiên cũ liên quan |
| Reimage hoặc thay thiết bị | Không giữ lại danh tính, khóa hoặc quyền cũ ngoài ý định |
| Nhân sự chuyển nhiệm vụ | Quyền hiệu lực và các nền tảng liên quan được cập nhật |
| Endpoint bị nghi xâm nhập | Có thể khoanh vùng, thu hồi và giữ bằng chứng |
| Kiểm tra log | Có liên kết người, thiết bị, request và đích; không lộ bí mật |

Quản lý danh tính Tier 2 giúp đội hỗ trợ làm việc trên máy trạm mà không kéo quyền quản trị cao hơn vào cùng môi trường. Ranh giới đó cần được thể hiện bằng quyền hiệu lực, nơi sử dụng danh tính, phạm vi thiết bị, cơ chế PAM và quy trình thu hồi có thể kiểm chứng.
