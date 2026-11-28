# Không dùng identity tier cao ở tier thấp

## 1. Nguyên tắc cần bảo vệ

Trong mô hình phân tầng quản trị, một danh tính có quyền kiểm soát hệ thống nhạy cảm không nên được sử dụng trên môi trường có mức tin cậy thấp hơn.

Lý do không chỉ là người quản trị có thể thao tác nhầm. Khi một danh tính đặc quyền được dùng trên một endpoint, tùy cơ chế xác thực, endpoint hoặc thành phần trung gian có thể tiếp xúc với credential, token, phiên hay khả năng sử dụng danh tính đó.

Nếu môi trường này bị kiểm soát, ảnh hưởng có thể vượt xa tài nguyên mà người quản trị đang sửa.

Ví dụ:

- Tài khoản quản trị danh tính được dùng để đăng nhập một máy chủ ứng dụng thông thường.
- Tài khoản quản trị máy chủ được dùng để sửa lỗi trên laptop người dùng.
- Credential của tài khoản kiểm soát PAM được đưa vào một script chạy trên máy hỗ trợ.
- Phiên đám mây có quyền cao được mở trong trình duyệt dùng cho công việc thường ngày.

Trong PAM, mục tiêu của nguyên tắc là giữ ranh giới giữa các vùng quản trị: cấp đúng danh tính, đúng quyền và đúng đường truy cập cho từng nhiệm vụ, thay vì mang một danh tính quyền cao đi khắp hệ thống.

Bài học sử dụng một mô hình minh họa quen thuộc:

| Tầng | Phạm vi minh họa |
|---|---|
| Tier 0 | Danh tính và các thành phần có thể kiểm soát nền tảng tin cậy |
| Tier 1 | Máy chủ, nền tảng và ứng dụng theo phân loại của tổ chức |
| Tier 2 | Máy trạm người dùng và công việc hỗ trợ endpoint |

Trong mô hình này, Tier 0 nhạy cảm hơn Tier 2; số lớn hơn không có nghĩa quyền cao hơn. Các tổ chức có thể có mô hình khác hoặc nhiều vùng độc lập. Cần dùng ranh giới tin cậy đã được xác định, không áp dụng một phép so sánh số một cách máy móc.

## 2. Vì sao dùng identity quyền cao trên môi trường thấp hơn nguy hiểm?

### 2.1. Danh tính có phạm vi lớn hơn nhiệm vụ

Giả sử người vận hành cần restart một dịch vụ trên máy chủ ứng dụng. Nếu họ dùng tài khoản có quyền thay đổi hệ thống danh tính, khả năng của tài khoản vượt xa công việc.

Một sự cố trên máy chủ đó có thể trở thành sự cố của danh tính có phạm vi toàn tổ chức. Người quản trị chỉ định làm một việc nhỏ không giới hạn được những gì tài khoản bị lạm dụng có thể làm.

Least privilege cần áp dụng cả vào **danh tính được chọn**, không chỉ vào ý định của người dùng.

### 2.2. Không phải chỉ mật khẩu mới đáng bảo vệ

Các đối tượng có thể bị phơi nhiễm hoặc lạm dụng gồm:

| Đối tượng | Rủi ro cần xem xét |
|---|---|
| Mật khẩu hoặc bí mật dùng lại | Có thể được dùng ở tài nguyên khác trong phạm vi tài khoản |
| Private key hoặc quyền sử dụng khóa | Có thể hỗ trợ xác thực trái phép theo khả năng cơ chế |
| Ticket hoặc token | Có thể cho phép gọi dịch vụ mà không nhập lại mật khẩu |
| Cookie phiên | Có thể duy trì một phiên ứng dụng còn hiệu lực |
| Phiên quản trị đang mở | Có thể bị điều khiển hoặc sử dụng để thực hiện hành động |
| Credential đã checkout | Có thể tồn tại ngoài đường kiểm soát của PAM |
| File cấu hình, lịch sử và log | Có thể giữ lại bí mật hoặc thông tin hỗ trợ sử dụng quyền |

Mức phơi nhiễm cụ thể phụ thuộc giao thức và cấu hình. Không nên khẳng định mọi kiểu đăng nhập đều gửi cùng một loại bí mật tới đích. Nhưng cũng không được suy ra rằng không gửi mật khẩu đồng nghĩa không có rủi ro phiên hoặc token.

### 2.3. MFA không giải quyết mọi rủi ro sau đăng nhập

MFA bảo vệ bước xác thực theo cơ chế được lựa chọn. Sau khi phiên đã được tạo, endpoint bị ảnh hưởng có thể tìm cách tác động tới phiên hoặc hành động của người dùng.

Một khóa được bảo vệ bằng phần cứng có thể khó bị lấy ra, nhưng môi trường điều khiển vẫn có thể bị lạm dụng để yêu cầu sử dụng khóa hoặc thực hiện hành động qua phiên.

Do đó, “tài khoản có MFA” không phải lý do đủ để cho phép dùng tài khoản đó trên mọi endpoint.

### 2.4. Phơi nhiễm có thể tồn tại sau khi người dùng rời đi

Đăng xuất không bảo đảm mọi token, cache hoặc quyền đã phát sinh đều biến mất. Một số đối tượng có vòng đời riêng và cần cơ chế thu hồi tương ứng.

Nếu đã dùng danh tính quyền cao trên môi trường không phù hợp, chỉ đóng cửa sổ kết nối không đủ cơ sở để kết luận rủi ro đã hết.

## 3. Tier là quan hệ kiểm soát, không chỉ là loại tài sản

### 3.1. Phân loại theo khả năng ảnh hưởng

Một hệ thống có thể không mang tên “identity” nhưng vẫn kiểm soát thành phần Tier 0.

Ví dụ:

- Nền tảng có thể thay đổi máy ảo chạy dịch vụ danh tính.
- Hệ thống sao lưu có thể khôi phục hoặc thay thế thành phần tin cậy.
- Nền tảng triển khai có thể đẩy mã tới PAW quản trị danh tính.
- Công cụ quản lý có thể sửa policy hoặc credential của PAM.
- Hệ thống quản lý khóa hoặc phát hành chứng thư có thể tạo danh tính được tin cậy.

Phải đánh giá các quan hệ đó khi phân tầng. Không coi một máy là Tier 1 chỉ vì nó là máy chủ thông thường nếu quyền trên nó có thể điều khiển nền tảng Tier 0.

### 3.2. Một PAW không tự thuộc Tier 2

PAW là máy trạm về hình thức, nhưng mức tin cậy phụ thuộc công việc quản trị nó phục vụ và ai có thể điều khiển nó.

Nếu một tài khoản hỗ trợ Tier 2 có thể điều khiển PAW dùng cho Tier 0, ranh giới đã có một đường vượt tầng.

Cần xem cả:

- Người có quyền quản trị cục bộ.
- Nền tảng quản lý thiết bị.
- Quyền điều khiển từ xa.
- Kho phần mềm và script.
- Nguồn cấu hình.
- Cơ chế cập nhật và phục hồi.

### 3.3. Không đồng nhất kết nối mạng với đăng nhập đặc quyền

Nguyên tắc phân tầng không có nghĩa cấm mọi gói tin hoặc mọi luồng dữ liệu giữa các tầng.

DNS, thời gian, thu thập log hoặc các dịch vụ khác có thể có luồng cần thiết. Phải đánh giá quyền và dữ liệu của từng luồng, đặc biệt khả năng cấp lệnh, thay đổi cấu hình hoặc sử dụng credential.

Điều cần ngăn trong bài học là việc đưa danh tính và khả năng quản trị vượt ranh giới tin cậy ngoài chính sách, không phải áp dụng một khẩu hiệu thay cho thiết kế hệ thống.

## 4. Tách danh tính theo nhiệm vụ và nơi sử dụng

### 4.1. Một người có thể có nhiều danh tính quản trị

Ví dụ:

~~~text
ha.work             → công việc thường ngày
ha.support.t2       → hỗ trợ máy trạm trong phạm vi
ha.server.t1        → quản trị máy chủ được giao
ha.identity.t0      → quản trị nền tảng danh tính được giao
~~~

Các tên chỉ minh họa. Để có ranh giới thực tế cần:

- Grant và role khác nhau.
- Phạm vi tài nguyên rõ ràng.
- Giới hạn nơi sử dụng.
- Chính sách xác thực phù hợp.
- Quản lý phiên và credential.
- Nguồn quản trị được chấp nhận.
- Giám sát và thu hồi.

Chỉ thêm hậu tố vào tên mà giữ nguyên quyền và cách sử dụng không tạo ra phân tầng.

### 4.2. Không dùng identity tầng cao để làm việc tầng thấp vì tiện

Một người đủ thẩm quyền trên nhiều tầng vẫn chọn danh tính phù hợp cho từng công việc.

Nếu cần sửa laptop, dùng đường hỗ trợ và danh tính Tier 2 được giao. Nếu cần sửa máy chủ ứng dụng, dùng danh tính và đường Tier 1 tương ứng.

Không nên dùng danh tính Tier 0 cho tất cả công việc chỉ vì tài khoản đó “chắc chắn đủ quyền”.

### 4.3. Cùng một principal với role khác nhau cần được đánh giá kỹ

Trong một số kiến trúc, một principal có nhiều role hoặc quyền đủ điều kiện kích hoạt. Việc chọn một role ít quyền hơn cho một phiên chưa tự giải quyết mọi rủi ro đối với principal có khả năng nhận quyền cao hơn.

Cần đánh giá:

- Principal còn quyền hoặc eligibility nào khác.
- Token được phát hành có scope gì.
- Có thể kích hoạt thêm quyền từ cùng phiên không.
- Yếu tố và đường khôi phục nào điều khiển principal.
- Credential bị lộ có thể được dùng lại ở đâu.
- Các ràng buộc có thực thi độc lập không.

Trong mô hình yêu cầu tách danh tính theo tầng, một nhãn role trong giao diện không tự tương đương với các danh tính đã được cách ly.

### 4.4. Bảo vệ yếu tố và đường khôi phục

Không dùng lại mật khẩu giữa các danh tính khác tầng. Nếu một bí mật bị lộ ở tầng thấp, nó không nên mở ra tài khoản tầng cao.

Với authenticator phần cứng có thể chứa nhiều credential, cần đánh giá cách sử dụng, chính sách xác minh và rủi ro chung; không mặc nhiên kết luận cùng một thiết bị vật lý luôn phá vỡ hoặc luôn đáp ứng phân tầng.

Đường reset mật khẩu, thay MFA hoặc khôi phục tài khoản tầng cao cũng phải được bảo vệ. Nếu người quản trị tầng thấp có thể chiếm lại tài khoản tầng cao qua hỗ trợ, việc tách tài khoản ở luồng đăng nhập chính chưa đủ.

## 5. Xác định nguồn, danh tính, đích và action cùng lúc

Một quyết định truy cập nên xét đầy đủ:

~~~text
Môi trường nguồn
    + danh tính sử dụng
    + action
    + tài nguyên đích
    + phương thức truy cập
    + điều kiện và thời gian
~~~

Chỉ kiểm tra danh tính hoặc chỉ kiểm tra thiết bị là chưa đủ.

### 5.1. Ma trận minh họa

| Nguồn | Danh tính | Đích và công việc | Hướng quyết định |
|---|---|---|---|
| PAW được chấp nhận cho quản trị danh tính | Tier 0 | Hệ thống danh tính thuộc phạm vi | Có thể cho phép khi đủ mọi điều kiện |
| PAW được chấp nhận cho quản trị danh tính | Tier 0 | Sửa máy chủ ứng dụng thông thường | Dùng danh tính và tuyến phù hợp công việc, không mang identity Tier 0 sang |
| Môi trường quản trị máy chủ được chấp nhận | Tier 1 | Máy chủ được giao | Có thể cho phép trong phạm vi |
| Laptop công việc thường ngày | Tier 1 | Mở phiên quản trị máy chủ | Không tự được phép chỉ vì tài khoản đủ quyền |
| Môi trường hỗ trợ được chấp nhận | Tier 2 | Máy trạm người dùng thuộc phạm vi | Có thể cho phép action hỗ trợ được giao |
| Môi trường hỗ trợ | Tier 2 | Reset yếu tố của tài khoản Tier 0 | Từ chối ngoài thẩm quyền |

“Có thể cho phép” không phải quyền mặc định. Vẫn cần MFA, entitlement, phê duyệt, cửa sổ và các điều kiện khác theo chính sách.

### 5.2. Nguồn tin cậy cao không làm mọi danh tính và tác vụ phù hợp

Một PAW quan trọng không nên trở thành nơi thực hiện mọi công việc ít tin cậy hơn chỉ vì máy được bảo vệ tốt.

Nội dung từ hệ thống tầng thấp, công cụ và dữ liệu nhận về vẫn có thể tạo rủi ro cho môi trường nguồn. Cần giới hạn tập tác vụ, công cụ và luồng dữ liệu theo mục đích của PAW.

### 5.3. Thiếu phân loại không được tự hiểu là an toàn

Nếu chưa biết tài nguyên thuộc vùng nào hoặc ai kiểm soát nguồn, cần xác minh trước khi cấp quyền nhạy cảm.

Không đưa tài nguyên mới vào phạm vi rộng chỉ vì chưa có nhãn hoặc vì tên của nó giống một máy đã được chấp nhận.

## 6. Thực thi ranh giới trên nhiều lớp

### 6.1. Quyền hiệu lực

Cần loại bỏ các grant làm tài khoản tầng cao có thể được dùng rộng ngoài phạm vi hoặc tài khoản tầng thấp có thể điều khiển tài nguyên tầng cao.

Kiểm tra:

- Nhóm trực tiếp và lồng nhau.
- Role trong các nền tảng khác.
- Quyền ủy quyền.
- Quyền reset hoặc phát hành credential.
- Quyền sửa policy, script và automation.
- Quyền thay phạm vi thiết bị hoặc phân loại.

Một chính sách đăng nhập có thể giảm phơi nhiễm, nhưng không thay thế việc sửa quyền sai.

### 6.2. Giới hạn kiểu sử dụng danh tính

Một hệ thống có thể có nhiều cách sử dụng tài khoản:

- Đăng nhập tương tác.
- Remote desktop.
- Truy cập mạng.
- Chạy dịch vụ.
- Tác vụ theo lịch.
- API hoặc công cụ quản trị.
- Luồng môi giới qua PAM.

Chặn một loại không tự chặn các loại còn lại. Cần ánh xạ chính sách sang các cơ chế mà hệ điều hành, ứng dụng và nền tảng danh tính thực sự hỗ trợ.

Không chỉ thử một giao diện rồi kết luận tài khoản đã bị chặn ở mọi đường.

### 6.3. Mạng và nguồn quản trị

Giới hạn đường tới tài nguyên đặc quyền giúp giảm bề mặt truy cập. Tuy nhiên, địa chỉ IP hoặc vị trí mạng không tự chứng minh danh tính và trạng thái endpoint.

Cần phối hợp nguồn quản trị được chấp nhận, xác thực, quyền và phương thức kết nối. Không tin một header client tự khai rằng thiết bị thuộc tầng được phép.

### 6.4. Hệ thống đích vẫn cần thực thi

Nếu portal từ chối nhưng tài khoản vẫn đăng nhập trực tiếp được, ranh giới chưa bao phủ đường trực tiếp đó.

Các kiểm soát cần phù hợp ở IdP, PAM, gateway, hệ điều hành hoặc ứng dụng đích. Phải biết điểm nào chịu trách nhiệm chặn điều gì.

### 6.5. Chính sách thay đổi và phiên hiện hữu

Khi loại bỏ quyền hoặc đổi phân loại, cần xử lý phiên và token đã tồn tại. Không giả định cập nhật một group làm mọi phiên cũ mất hiệu lực ngay.

Phải xác định cơ chế thu hồi, thời hạn, độ trễ và cách xác minh kết quả trên điểm thực thi.

## 7. Thiết kế PAM để không làm cầu nối sai tầng

### 7.1. Chọn đúng danh tính đích

Khi người dùng mở yêu cầu, PAM cần cấp action hoặc credential phù hợp tài nguyên đích.

Ví dụ, restart một dịch vụ Tier 1 nên dùng một khả năng giới hạn hoặc tài khoản kỹ thuật đủ quyền trên dịch vụ đó. Không dùng credential quản trị danh tính Tier 0 làm credential chung cho mọi máy.

Không đưa danh tính quyền cao xuống đích chỉ vì PAM giữ bí mật và người dùng không nhìn thấy. Hệ thống đích vẫn tiếp xúc với một hình thức xác thực hoặc phiên có phạm vi cần đánh giá.

### 7.2. Tách người thao tác với tài khoản kỹ thuật nhưng giữ quy trách nhiệm

Một phiên có thể gồm:

~~~text
Danh tính cá nhân phù hợp nhiệm vụ
    → request và phê duyệt
    → entitlement theo action hoặc role
    → tài khoản kỹ thuật phù hợp đích
    → phiên hoặc tác vụ thực tế
~~~

Cần giữ liên kết này để biết ai làm gì mà không buộc phải dùng cùng một tài khoản cá nhân có quyền rộng trên mọi tầng.

Nếu hệ thống đích chỉ thấy tài khoản kỹ thuật, không ghi như thể nó đã trực tiếp xác thực người dùng cá nhân.

### 7.3. Bảo vệ gateway và thành phần giữ credential

Một gateway có thể mở phiên hoặc dùng credential tầng cao là một thành phần nhạy cảm.

Nếu một nhóm quản trị tầng thấp có thể thay mã, cấu hình hoặc đọc bí mật của gateway đó, họ có thể tác động tới khả năng quản trị tầng cao.

Tách gateway theo tầng có thể hỗ trợ, nhưng không đủ nếu cùng một nền tảng quản lý yếu vẫn điều khiển mọi gateway. Phải đánh giá cả nguồn cập nhật, backup, automation và quyền cấu hình.

### 7.4. Portal dùng chung không xóa ranh giới nhiệm vụ

Một portal có thể phục vụ nhiều vùng quản trị. Cần kiểm tra role, principal, yêu cầu và credential theo từng tác vụ, không mặc định một lần đăng nhập bằng danh tính quyền cao bao phủ mọi công việc thấp hơn.

Cách tổ chức cụ thể phụ thuộc kiến trúc, nhưng mục tiêu phải giữ được: không dùng danh tính quyền cao như tài khoản làm việc chung và không đưa credential của nó tới đích ngoài phạm vi.

### 7.5. Credential checkout cần được giới hạn

Nếu cho xem hoặc sao chép credential, khả năng kiểm soát đường sử dụng giảm đi. Cần xác định người dùng có thể dùng bí mật đó từ đâu và trên tài nguyên nào.

Ưu tiên phiên hoặc tác vụ được môi giới khi phù hợp. Nếu phải tiết lộ, cần quản lý thời gian, mục đích, việc đổi hoặc thu hồi và bằng chứng sử dụng.

## 8. Automation cũng phải tuân thủ ranh giới

### 8.1. Không dùng tài khoản quản trị con người trong script tầng thấp

Một script chạy trên máy hỗ trợ không nên giữ credential của quản trị viên nền tảng danh tính để gọi một thao tác.

Cần dùng danh tính workload riêng với:

- Action cụ thể.
- Tài nguyên cụ thể.
- Credential hoặc token có vòng đời phù hợp.
- Điều kiện phát hành và sử dụng.
- Khả năng thu hồi.
- Bằng chứng người hoặc quy trình đã tạo tác vụ.

Chỉ đổi tài khoản thành tên service không làm quyền trở nên an toàn.

### 8.2. Tách khả năng gọi tác vụ với khả năng sửa tác vụ

Một người có thể được phép yêu cầu một tác vụ khôi phục đã đóng gói nhưng không được sửa mã của tác vụ đó.

Nếu người gọi có thể thay script chạy dưới danh tính tầng cao, giới hạn ở màn hình yêu cầu sẽ mất ý nghĩa.

Cần quản trị nguồn mã, runner, tham số và triển khai theo mức tác động thực tế.

### 8.3. Xác minh luồng được ủy quyền

Một dịch vụ trung gian có quyền cao không nên làm mọi điều theo dữ liệu người gọi gửi. Nó phải kiểm tra danh tính khởi tạo, action, đích và điều kiện.

Luồng automation giữa các vùng có thể được thiết kế có kiểm soát, nhưng không phải ngoại lệ mặc định cho việc dùng lại credential quyền cao.

## 9. Chính sách và logic minh họa

Cấu hình sau chỉ diễn tả ý định, không phải cú pháp của một sản phẩm:

~~~yaml
administrative_identity_boundary:
  model: "explicit-trust-zones"

  identities:
    separate_by_administrative_purpose: true
    high_tier_identity_is_not_general_support_identity: true
    shared_password_across_tiers_allowed: false

  access_decision:
    validate_source_identity_action_and_target: true
    use_authoritative_resource_classification: true
    unknown_required_classification: "deny-and-review"
    high_tier_identity_on_lower_trust_target: "deny"

  enforcement:
    cover_applicable_logon_and_api_paths: true
    direct_access_must_not_bypass_pam_policy: true
    protect_existing_session_revocation: true

  pam:
    target_credential_must_match_task_scope: true
    protect_gateways_that_handle_high_tier_access: true
    prevent_low_tier_operators_from_reconfiguring_high_tier_routes: true

  exceptions:
    require_authority_scope_and_expiry: true
    automatic_fallback_on_failure: false

  evidence:
    record_source_identity_target_and_method: true
    exclude_reusable_secrets: true
~~~

Mã giả:

~~~text
authorize_administrative_access(connection, request):
    actor = authenticated_principal(connection)
    source = trusted_source_context(connection)
    target = resolve_authoritative_target(request.target_id)
    action = resolve_known_action(request.action)

    require(actor.is_active)
    require(source.is_approved_for_this_administrative_purpose)
    require(target.classification_is_known)

    relationship = evaluate_trust_boundary(
        actor.administrative_scope,
        source,
        target,
        request.access_method
    )

    if relationship.exposes_higher_tier_identity_to_lower_trust:
        deny("IDENTITY_BOUNDARY_VIOLATION")

    require(actor.has_matching_action_resource_entitlement)
    require(current_approval_if_needed)
    require(access_window_is_open)
    require(authentication_assurance_is_sufficient)

    target_identity = select_scoped_execution_identity(action, target)
    require(target_identity.matches_the_approved_task)

    return bounded_access_decision(actor, target_identity, action, target)
~~~

Logic cần dựa trên quan hệ đã quản trị, không chỉ so sánh hai số tier do client gửi. Quyết định phải được ràng buộc với thao tác thực tế và kiểm tra lại khi các điều kiện thay đổi.

~~~mermaid
flowchart TD
    A[Yêu cầu quản trị] --> B[Xác định nguồn, danh tính, action và đích]
    B --> C[Tra phân loại và quan hệ tin cậy có thẩm quyền]
    C --> D{Làm phơi nhiễm identity tầng cao ở vùng thấp hơn?}
    D -- Có --> E[Từ chối và chuyển sang danh tính hoặc tuyến đúng nhiệm vụ]
    D -- Không --> F[Kiểm tra entitlement, phê duyệt, xác thực và thời gian]
    F --> G{Đủ điều kiện?}
    G -- Không --> H[Từ chối và ghi lý do]
    G -- Có --> I[Cấp phiên hoặc tác vụ có giới hạn]
    I --> J[Giám sát, kết thúc và xác minh thu hồi]
~~~

## 10. Ngoại lệ và break-glass

### 10.1. Sự cố không tự xóa ranh giới

Một lỗi xác thực, một tài khoản thiếu quyền hoặc áp lực thời gian không tự cho phép dùng tài khoản mạnh nhất trên môi trường thấp hơn.

Cần có tuyến khẩn cấp được chuẩn bị, xác định danh tính, tài nguyên, action, phương thức, thời hạn và thẩm quyền kích hoạt.

Ưu tiên giữ phạm vi phù hợp với công việc, ngay cả khi quy trình phê duyệt thông thường không khả dụng.

### 10.2. Ngoại lệ có rủi ro phải được gọi đúng tên

Nếu một tình huống bắt buộc tạo phơi nhiễm ngoài mô hình, cần ghi rõ:

- Vì sao tuyến an toàn hơn không dùng được.
- Danh tính và tài nguyên nào liên quan.
- Rủi ro và biện pháp giảm thiểu.
- Người có thẩm quyền.
- Khoảng thời gian.
- Kế hoạch kết thúc và xử lý credential, phiên.
- Hậu kiểm và biện pháp tránh lặp lại.

Không coi một ngoại lệ đã được ghi nhận là chứng minh rủi ro không còn. Phải thực hiện các bước kết thúc tương ứng.

### 10.3. Không tạo lịch sử giả

Phê duyệt hoặc hậu kiểm sau sự cố cần ghi đúng thời điểm và cơ sở thẩm quyền. Không ghi lùi ngày để làm như đã có phê duyệt thường trước khi sử dụng.

Break-glass dùng lặp lại cho công việc có thể dự kiến là dấu hiệu cần cải thiện đường vận hành, không phải lý do biến ngoại lệ thành quyền thường trực.

## 11. Phát hiện và xử lý việc dùng sai tầng

### 11.1. Bằng chứng cần liên kết

Cần quan sát được:

- Danh tính và phạm vi quản trị của nó.
- Thiết bị hoặc môi trường nguồn.
- Tài nguyên đích và phiên bản phân loại.
- Kiểu đăng nhập hoặc phương thức truy cập.
- Action và quyền đã dùng.
- Request, phê duyệt và cửa sổ.
- Tài khoản kỹ thuật trên đích nếu có.
- Kết quả, phiên và trạng thái thu hồi.

Không chỉ tìm tên tài khoản có hậu tố t0. Một tài khoản không có tên đặc biệt vẫn có thể có quyền quản trị nền tảng tin cậy.

### 11.2. Tín hiệu đáng điều tra

Ví dụ:

- Danh tính Tier 0 xuất hiện trên máy chủ không thuộc phạm vi.
- Tài khoản quản trị máy chủ được dùng trên laptop người dùng.
- Credential tầng cao được checkout từ một môi trường nguồn không phù hợp.
- Một công cụ hỗ trợ có quyền sửa PAW nhạy cảm.
- Một script tầng thấp gọi tác vụ bằng credential quản trị rộng.
- Nhiều phiên khác tầng tồn tại trong cùng môi trường không được chấp nhận.
- Chính sách phân loại hoặc tuyến PAM đổi ngay trước lần truy cập.

Một sự kiện đăng nhập không tự chứng minh đã lộ mọi bí mật. Nó cho thấy cần xác định bằng chứng và phạm vi phơi nhiễm thực tế.

### 11.3. Khi đã có phơi nhiễm

Theo quy trình ứng phó, có thể cần:

1. Dừng việc sử dụng sai và bảo vệ bằng chứng.
2. Chuyển điều phối sang môi trường còn đáng tin cậy.
3. Xác định credential, token và phiên có thể bị ảnh hưởng.
4. Thu hồi quyền hoặc phiên liên quan theo khả năng thực thi.
5. Thay hoặc vô hiệu hóa bí mật khi cần.
6. Kiểm tra hành động đã xảy ra trên tài nguyên khác.
7. Xử lý endpoint và nguyên nhân tạo đường vượt tầng.
8. Xác minh khôi phục trước khi sử dụng lại.

Đổi mật khẩu không tự bảo đảm token hoặc phiên cũ đã hết hiệu lực. Cần kiểm tra từng lớp liên quan.

Không mặc định xóa máy ngay nếu việc đó làm mất bằng chứng cần thiết; phối hợp giữa khoanh vùng, điều tra và khôi phục theo quy trình.

## 12. Tình huống: quản trị viên máy chủ hỗ trợ một laptop

Một người đồng thời làm vận hành máy chủ và hỗ trợ endpoint. Họ có tài khoản quản trị Tier 1 và danh tính hỗ trợ Tier 2.

Laptop người dùng gặp lỗi ứng dụng. Tài khoản hỗ trợ thiếu một action sửa chữa, còn tài khoản Tier 1 có quyền rộng hơn.

Cách xử lý không phù hợp là đăng nhập tài khoản Tier 1 trên laptop để vượt lỗi. Phạm vi công việc là Tier 2, nhưng danh tính bị đưa vào máy có khả năng tác động tới nhiều máy chủ.

Một quy trình phù hợp hơn:

1. Xác minh đúng laptop và phạm vi hỗ trợ.
2. Dùng danh tính Tier 2 từ môi trường được chấp nhận.
3. Yêu cầu action bổ sung hoặc quyền cục bộ JIT đúng thiết bị nếu cần.
4. Nhận quyết định có thẩm quyền theo chính sách.
5. Thực hiện qua đường PAM hoặc tác vụ được quản lý.
6. Ghi kết quả và kết thúc quyền.
7. Giữ tài khoản Tier 1 trong môi trường và công việc quản trị máy chủ.

Nếu laptop là PAW của quản trị viên danh tính, tài nguyên cần được phân loại lại hoặc chuyển đúng tuyến. Không tiếp tục luồng Tier 2 chỉ vì inventory đang ghi “workstation”.

Nếu người vận hành đã dùng tài khoản Tier 1 trước khi phát hiện, hồ sơ cần ghi sự kiện thực tế và đánh giá phơi nhiễm. Không chỉ đổi nhãn request rồi coi như ranh giới chưa bị vi phạm.

## 13. Triển khai và kiểm chứng

Trước khi áp dụng chặn rộng, cần lập bản đồ danh tính, quyền hiệu lực, tài nguyên và đường sử dụng. Những tài khoản dịch vụ hoặc automation đang dùng sai có thể tạo phụ thuộc cần xử lý.

Một lộ trình thực tế có thể gồm quan sát, sửa quyền và đường làm việc, thử trên phạm vi đại diện, rồi mở rộng. Phải chuẩn bị tuyến khôi phục phù hợp để tránh mất đường quản trị hợp lệ.

| Ca kiểm thử | Kết quả cần đạt |
|---|---|
| Identity Tier 0 tới máy chủ ứng dụng ngoài phạm vi | Bị chặn theo chính sách |
| Identity Tier 1 tới máy trạm người dùng | Không được dùng như tài khoản hỗ trợ |
| Người có nhiều danh tính chọn sai tài khoản | Được chặn hoặc hướng về tuyến đúng nhiệm vụ |
| Nguồn không được quản lý tự khai là PAW | Không được tin như bằng chứng |
| Tài nguyên thiếu phân loại | Không tự được cấp quyền nhạy cảm |
| PAW nhạy cảm bị gắn nhãn máy thường | Được phát hiện qua quan hệ điều khiển và kiểm soát phân loại |
| Tài khoản có quyền qua group lồng nhau | Được đánh giá theo quyền hiệu lực |
| Đường tương tác bị chặn nhưng API hoặc tác vụ khác còn mở | Các đường liên quan được kiểm tra và xử lý |
| PAM chọn credential quá mạnh cho tác vụ thấp | Không thực hiện ngoài phạm vi đã thiết kế |
| Người tầng thấp sửa gateway hoặc runner tầng cao | Bị chặn bởi ranh giới quản trị |
| Một script dùng credential người quản trị rộng | Được phát hiện và chuyển sang danh tính workload phù hợp |
| Role hoặc classification thay đổi khi phiên đang mở | Có xử lý phiên và quyền theo cơ chế đã công bố |
| Reset mật khẩu hoặc MFA của identity tầng cao | Không thuộc quyền hỗ trợ tầng thấp ngoài thẩm quyền |
| Ngoại lệ hết hạn | Không tiếp tục mở quyền theo ngoại lệ cũ |
| Thu hồi credential sau phơi nhiễm | Xác minh cả token, phiên và quyền liên quan |
| Log được kiểm tra | Có nguồn, principal, đích và phương thức; không lộ bí mật |
| Đường khẩn cấp được diễn tập | Dùng được và không trở thành đường quản trị thường ngày |

Nguyên tắc không dùng identity tier cao ở tier thấp bảo vệ phạm vi ảnh hưởng của danh tính, không chỉ trật tự đặt tên tài khoản. Ranh giới có hiệu lực khi danh tính, môi trường nguồn, tài nguyên, action và đường thực thi đều phù hợp nhiệm vụ, đồng thời mọi phơi nhiễm hoặc ngoại lệ được xử lý đến khi quyền thực tế đã được kiểm soát.
