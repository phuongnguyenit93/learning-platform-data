# Khóa identity khi bất thường trong PAM

## 1. Mục tiêu của việc khóa identity

Trong hệ thống quản lý truy cập đặc quyền, **khóa identity khi bất thường** là áp dụng một trạng thái hạn chế đối với danh tính khi có tín hiệu rủi ro cần ngăn chặn hoặc điều tra. Phạm vi có thể là không cho mở phiên PAM mới, không cho kích hoạt quyền đặc biệt hoặc vô hiệu khả năng xác thực ở nguồn danh tính.

Khóa là một biện pháp kiểm soát truy cập. Nó không tự chứng minh đã có xâm nhập và cũng không tự thu hồi mọi khả năng sử dụng quyền đã tồn tại.

Ví dụ, tài khoản quản trị của An xuất hiện một phiên từ môi trường không được nhận diện, kèm yêu cầu tới target ngoài công việc dự kiến. Tổ chức có thể chặn cấp phiên mới để giới hạn rủi ro trong khi xác minh. Nhưng phiên đã mở, token đã phát hành, SSH key và tác vụ tại đích vẫn cần được xem xét riêng.

Một thiết kế đạt mục tiêu cần trả lời:

- Tín hiệu nào đủ để áp dụng hành động nào?
- Identity nào thực sự bị ảnh hưởng?
- Khóa ở lớp nào, trong phạm vi nào?
- Những quyền, credential và phiên nào còn có thể sử dụng?
- Ai có thẩm quyền xử lý và mở lại?
- Bằng chứng nào xác nhận kết quả, phần nào còn chưa biết?

Mục tiêu là giảm khả năng sử dụng đặc quyền trái phép, giữ hoạt động cần thiết trong phạm vi đã thiết kế và bảo toàn khả năng điều tra.

## 2. Phân biệt các loại khóa và thu hồi

Từ “khóa tài khoản” thường được dùng cho nhiều hành động khác nhau. Cần ghi rõ lớp thực thi.

| Hành động | Kết quả trực tiếp dự kiến | Không tự chứng minh |
|---|---|---|
| Giới hạn tần suất đăng nhập | Giảm số yêu cầu được xử lý | Người có phiên hợp lệ đã mất quyền |
| Khóa do đăng nhập sai | Ngăn một số lần xác thực mới theo cấu hình | Tài khoản thật sự bị chiếm |
| Hạn chế ở PAM | Không cấp một số quyền hoặc phiên PAM mới | Đường SSH, API hoặc console ngoài PAM đã bị chặn |
| Vô hiệu tại IdP hoặc directory | Ngừng xác thực hoặc phát hành mới theo khả năng nguồn | Mọi ứng dụng đã thu hồi phiên cũ |
| Thu hồi entitlement hoặc grant | Gỡ điều kiện cấp quyền tương ứng | Token hoặc phiên đã được cấp đều hết hiệu lực ngay |
| Vô hiệu token hoặc cookie | Giảm khả năng dùng đối tượng đó theo semantics hệ thống | Mọi token, cookie và ứng dụng khác đã xử lý xong |
| Kết thúc phiên gateway | Ngừng tương tác qua phiên đó theo khả năng | Tác vụ nền ở đích đã dừng |
| Thu hồi credential | Ngăn sử dụng credential theo cơ chế và thời điểm áp dụng | Phiên đã xác thực bằng credential đó tự đóng |
| Khóa tài khoản tại target | Hạn chế account ở đích theo nền tảng | Không ảnh hưởng consumer dùng chung hoặc không còn đường khác |

Một lệnh được API chấp nhận chưa phải bằng chứng rằng trạng thái mong muốn đã được thực thi ở mọi điểm liên quan.

Trong báo cáo, nên ghi “đã chặn cấp mới tại PAM” hoặc “đã xác nhận phiên gateway kết thúc”, thay vì một câu chung “đã khóa toàn bộ truy cập” khi chưa đủ bằng chứng.

## 3. Xác định đúng identity và phạm vi liên quan

### 3.1. Dùng định danh ổn định

Tên hiển thị và email có thể thay đổi hoặc trùng nhau. Quyết định cần gắn với định danh theo cơ chế của hệ thống, bao gồm nguồn phát hành hoặc miền quản lý phù hợp.

Một người có thể có:

- Tài khoản làm việc hằng ngày.
- Tài khoản quản trị riêng.
- Tài khoản khách hoặc vendor.
- Các phiên và grant ở nhiều ứng dụng.
- Khóa hoặc chứng thư được cấp cho công việc đặc quyền.

Một tài khoản tại target cũng có thể được nhiều phiên PAM sử dụng. Không tự coi mọi đối tượng cùng tên hoặc cùng email là cùng một identity cần khóa.

### 3.2. Mapping người dùng với tài khoản kỹ thuật

Giả sử An đăng nhập PAM bằng danh tính riêng, còn gateway dùng tài khoản kỹ thuật diagnostics để vào máy chủ. Khi có rủi ro gắn với An, hệ thống cần biết các phiên và grant nào thuộc An.

Khóa account diagnostics ở target có thể ảnh hưởng người dùng khác hoặc automation nếu account được dùng chung. Biện pháp đó có thể cần thiết trong một tình huống cụ thể, nhưng phải được lựa chọn với phạm vi và tác động được hiểu rõ.

Khả năng liên kết danh tính con người, request, grant, account và session giúp tổ chức thực hiện hạn chế chính xác hơn.

### 3.3. Tách người dùng và workload

Workload có thể có token, chứng thư, service account hoặc danh tính nền tảng với vòng đời khác tài khoản con người.

Một cảnh báo trên workload cần xét dependency và khả năng ảnh hưởng dịch vụ. Không áp dụng máy móc quy trình “gọi người dùng xác minh rồi reset MFA” cho một tiến trình tự động.

Ngược lại, không dùng lý do tài khoản có consumer để miễn mọi biện pháp kiểm soát. Cần có phương án giới hạn và phục hồi phù hợp với loại identity đó.

## 4. Những tín hiệu bất thường cần đánh giá

### 4.1. Tín hiệu xác thực

Có thể gồm:

- Nhiều lần đăng nhập thất bại theo mẫu bất thường.
- Yêu cầu MFA lặp lại mà người dùng không nhận ra.
- Xác thực từ môi trường hoặc thiết bị không phù hợp policy.
- Thay authenticator hoặc phục hồi tài khoản ngoài quy trình dự kiến.
- Dùng phương thức fallback không đáp ứng yêu cầu của phiên.
- Dấu hiệu một token hoặc session artifact được sử dụng ngoài ngữ cảnh được phép.

Những tín hiệu này có độ chắc chắn khác nhau. Không phải mọi lần xác thực thất bại đều là bằng chứng người dùng đã mất tài khoản.

### 4.2. Tín hiệu đặc quyền

Các ví dụ khác gồm:

- Xin hoặc sử dụng quyền tới target không liên quan công việc.
- Tăng quyền hoặc thêm credential ngoài thay đổi đã duyệt.
- Xuất secret trái phạm vi được cấp.
- Mở nhiều phiên khác thường theo hồ sơ sử dụng.
- Sửa policy PAM, nguồn khóa hoặc hệ thống lưu bằng chứng không đúng thẩm quyền.
- Duy trì truy cập sau khi hết nhiệm vụ, hợp đồng hoặc cửa sổ.
- Hoạt động tại đích không tương ứng role và tác vụ đã cấp.

Cần đối chiếu với lịch bảo trì, sự cố, failover, automation và công việc hợp lệ. Một thao tác ít gặp có thể có lý do chính đáng, nhưng lý do đó cần được xác minh.

### 4.3. Tín hiệu mạng và vị trí

Địa chỉ IP, vị trí suy ra hoặc thời gian di chuyển có thể hỗ trợ đánh giá. Tuy nhiên, VPN, NAT, mạng di động, proxy, thay đổi đường ra và dữ liệu định vị không chính xác có thể tạo tín hiệu gây hiểu nhầm.

Không dùng một địa chỉ mới như bằng chứng duy nhất rằng tài khoản đã bị chiếm. Cũng không coi địa chỉ quen thuộc là bảo đảm an toàn nếu host hoặc phiên tại đó đã bị ảnh hưởng.

### 4.4. Chất lượng và độ mới của tín hiệu

Mỗi tín hiệu cần có nguồn, thời điểm và phạm vi tin cậy. Phân biệt:

- Thời điểm sự kiện xảy ra.
- Thời điểm hệ thống nhận được.
- Thời điểm đánh giá và hành động.
- Phần dữ liệu bị thiếu hoặc chưa xác minh.

Một sự kiện đến muộn không nên bị hiểu như một hành vi mới mà không xem ngữ cảnh. Khi nguồn log gián đoạn, “không có cảnh báo mới” không tự đồng nghĩa với “rủi ro đã hết”.

## 5. Chọn hành động theo độ chắc chắn và tác động

Không phải bất thường nào cũng cần vô hiệu toàn bộ tài khoản. Một policy có thể dùng nhiều mức phản ứng:

| Tình huống minh họa | Hành động có thể được thiết kế | Điều cần cân nhắc |
|---|---|---|
| Tín hiệu yếu, chưa đủ dữ liệu | Tăng quan sát hoặc yêu cầu xác minh bổ sung | Không gắn nhãn đã xâm nhập |
| Bằng chứng xác thực chưa đủ cho tác vụ | Yêu cầu step-up hoặc từ chối tác vụ đó | Step-up không thay entitlement |
| Lạm dụng tần suất từ một nguồn | Giới hạn theo nguồn hoặc luồng phù hợp | Tránh tạo cách khóa người khác quá dễ |
| Rủi ro liên quan một phiên cụ thể | Ngừng hoặc cách ly phiên trong thẩm quyền | Cần theo dõi trạng thái ở đích |
| Rủi ro đối với danh tính đặc quyền | Chặn cấp mới và xử lý grant, token, phiên liên quan | Phạm vi có thể vượt một ứng dụng |
| Nghi ngờ credential bị lộ | Thu hồi hoặc thay credential theo kế hoạch ứng phó | Xét mọi nguồn chấp nhận và consumer |
| Nguồn danh tính bị ảnh hưởng | Đánh giá lại việc tiếp nhận bằng chứng từ nguồn đó | Không chỉ reset một mật khẩu người dùng |

Bảng mô tả các lựa chọn thiết kế, không quy định một thang phản ứng dùng chung cho mọi tổ chức.

Cần cân nhắc đồng thời:

1. Mức độ chắc chắn của tín hiệu.
2. Tác động nếu tiếp tục cho phép truy cập.
3. Tác động khi khóa nhầm hoặc khóa quá rộng.
4. Khả năng quan sát và khôi phục.
5. Thẩm quyền đã được giao cho hệ thống hoặc người xử lý.

Với hành vi có độ tin cậy cao và tác động lớn, quy trình có thể cho phép hạn chế ngay trong phạm vi đã ủy quyền. Phần đánh giá tiếp theo không được dùng làm lý do tự động kéo dài mọi quyền nguy hiểm khi biện pháp ứng phó đã được xác định.

## 6. Tránh biến khóa tài khoản thành công cụ từ chối dịch vụ

Một cơ chế khóa chỉ dựa trên số lần đăng nhập sai có thể bị lợi dụng để gây gián đoạn cho chủ tài khoản. Tài khoản đặc quyền và tài khoản dùng chung càng cần xem xét ảnh hưởng.

Các lựa chọn theo khả năng nền tảng có thể gồm:

- Giới hạn tần suất theo nguồn, thiết bị hoặc luồng trước khi mở rộng phạm vi.
- Phân biệt lỗi mật khẩu, lỗi tích hợp và tín hiệu chiếm phiên.
- Áp dụng trì hoãn hoặc thử thách phù hợp.
- Sử dụng nhiều tín hiệu để quyết định khóa rộng.
- Có đường báo cáo và phục hồi cho người dùng hợp lệ.
- Giám sát chính các mẫu kích hoạt khóa lặp lại.

Không vì nguy cơ khóa nhầm mà bỏ mọi khóa tự động. Mục tiêu là lựa chọn điều kiện và phạm vi có thể giải thích, có dữ liệu kiểm chứng và có người chịu trách nhiệm.

Một lỗi cấu hình khiến workload liên tục xác thực bằng credential cũ cũng có thể tạo hàng loạt thất bại. Cần tìm consumer đó, không chỉ mở khóa rồi để lỗi tiếp tục tái diễn.

## 7. Vòng đời một quyết định hạn chế

Một mô hình logic minh họa:

~~~mermaid
stateDiagram-v2
    [*] --> NORMAL
    NORMAL --> RESTRICTED: Tín hiệu cần hạn chế
    RESTRICTED --> LOCKED: Đánh giá yêu cầu khóa rộng hơn
    RESTRICTED --> RECOVERY_PENDING: Hoàn thành xác minh ban đầu
    LOCKED --> RECOVERY_PENDING: Đủ điều kiện xem xét phục hồi
    RECOVERY_PENDING --> MONITORED: Phục hồi có phạm vi
    MONITORED --> NORMAL: Đạt tiêu chí đóng
    RECOVERY_PENDING --> LOCKED: Điều kiện chưa đạt
    MONITORED --> LOCKED: Rủi ro mới
~~~

Đây là trạng thái quản lý quyết định, không phải yêu cầu mọi sản phẩm có đúng những nhãn này.

Cần phân biệt trạng thái mong muốn với trạng thái thực tế ở các thành phần. Identity có thể đang ở trạng thái LOCKED của vụ việc, trong khi:

- PAM đã chặn cấp mới.
- IdP đã nhận yêu cầu vô hiệu.
- Một ứng dụng vẫn còn phiên.
- Gateway đã ngắt kênh.
- Target còn kết quả chưa xác nhận.

Không gộp các kết quả đó thành một cờ thành công duy nhất.

Quyết định nên có ID, lý do, owner, phạm vi, thời điểm, điều kiện đánh giá lại và các hành động liên quan. Nếu có thời hạn tự đánh giá lại, hết thời hạn không tự chứng minh identity an toàn để mở lại.

## 8. Luồng xử lý từ cảnh báo tới thực thi

### 8.1. Tiếp nhận và chuẩn hóa

Xác minh cảnh báo đến từ nguồn phù hợp và đủ dữ liệu để nhận diện đối tượng. Không để một trường không được kiểm chứng trong thông báo quyết định tùy ý identity hoặc target sẽ bị vô hiệu.

Giữ nguyên tham chiếu tới sự kiện gốc và ghi cách hệ thống suy ra phạm vi. Nếu định danh không rõ, không khóa một tài khoản chỉ vì tên hiển thị giống nhau.

### 8.2. Đánh giá và ghi quyết định

Đối chiếu policy, độ chắc chắn, quyền đang có và tác động dự kiến. Xác định hành động tự động đã được ủy quyền hay cần người có thẩm quyền quyết định.

Ghi quyết định trước hoặc cùng cơ chế thực thi phù hợp để có thể đối chiếu. Không tạo ra trạng thái mà hệ thống đã khóa một đối tượng nhưng không biết cảnh báo hay người nào chịu trách nhiệm.

### 8.3. Thực thi theo lớp

Một trình tự logic cho rủi ro của một người dùng đặc quyền có thể là:

~~~text
1. Chặn cấp quyền và mở phiên mới trong phạm vi PAM.
2. Vô hiệu các quyền mở phiên chưa dùng và grant liên quan.
3. Xử lý nguồn danh tính, token và cookie theo khả năng từng hệ thống.
4. Xử lý các phiên gateway thuộc chủ thể.
5. Xác minh hoặc xử lý phiên, tài khoản và tác vụ tại đích.
6. Đánh giá credential, khóa hoặc chứng thư có thể còn dùng ngoài luồng.
7. Thu thập kết quả, retry có kiểm soát và giao phần chưa hoàn tất.
~~~

Đây không phải thứ tự bắt buộc cho mọi sự cố. Một số hành động có thể cần phối hợp hoặc ưu tiên khác để đạt mục tiêu và hạn chế tác động.

Điểm quan trọng là không dừng ở bước 1 rồi tuyên bố tất cả các lớp đã được thu hồi.

### 8.4. Xác minh sau hành động

Cần kiểm tra kết quả theo semantics của thành phần:

- Trạng thái cấp mới đã thay đổi chưa?
- Grant nào đã được gỡ?
- Token nào đã được xử lý và hệ thống nào còn dùng cache?
- Phiên nào đã dừng, phiên nào chỉ bị disconnect?
- Credential nào còn có thể xác thực mới?
- Có đường SSH, API hoặc console ngoài PAM không?

Nếu không nhận được xác nhận, ghi PENDING hoặc UNKNOWN theo mô hình vận hành. Một timeout không tự là thành công hay thất bại chắc chắn.

## 9. Xử lý retry, sự kiện trùng và thay đổi đồng thời

### 9.1. Tránh thao tác trùng ngoài ý định

Một cảnh báo có thể được gửi lại; một lệnh thực thi có thể hoàn thành nhưng phản hồi bị mất. Cần định danh và đối chiếu để retry không tạo thêm tác động ngoài phạm vi.

Ví dụ, retry một hành động ngừng cấp mới khác với liên tục tạo các đợt rotation credential. Mỗi loại hành động cần semantics riêng.

Không tính cùng một sự kiện được truyền qua nhiều nguồn thành nhiều bằng chứng độc lập nếu thực tế chúng có cùng nguồn gốc.

### 9.2. Không để mở khóa ghi đè hạn chế mới hơn

Giả sử quy trình phục hồi đang mở lại identity thì một cảnh báo mới yêu cầu tiếp tục khóa. Nếu áp dụng cách “lần cập nhật cuối thắng”, kết quả có thể trái policy.

Cần dùng cơ chế phù hợp như phiên bản quyết định, điều kiện cập nhật hoặc đối chiếu các vụ việc đang mở. Một yêu cầu mở lại phải xác minh không còn điều kiện chặn có hiệu lực trong phạm vi cần xét.

Nếu có nhiều nguồn tạo hạn chế, cần biết ai có quyền gỡ hạn chế nào. Đóng một vụ việc không tự xóa lệnh giữ của một vụ việc khác.

### 9.3. Giữ khác biệt giữa hết hạn và đã an toàn

Một hạn chế tự động có thể có TTL để buộc đánh giá lại, nhưng không nên làm mất một lệnh giữ thủ công hoặc một sự cố chưa xử lý chỉ vì bộ đếm hết thời gian.

Tương tự, retry thất bại không nên tự đưa identity về trạng thái bình thường. Cần owner và cơ chế xử lý phần chưa xác nhận.

## 10. Policy minh họa

~~~yaml
# Mã giả mô tả ý định, không phải cấu hình để triển khai trực tiếp.
decision:
  case_id: PAM-IDENTITY-EXAMPLE-018
  subject_ref: trusted-source-and-stable-subject-id
  scope: privileged_access_for_this_subject
  reason: correlated_session_and_privilege_anomalies
  policy_version: identity-containment-example-v2

containment:
  block_new_pam_grants: true
  invalidate_unused_launch_permissions: true
  review_active_sessions: true
  apply_session_actions_within_authority: true
  assess_identity_provider_actions: true
  assess_credentials_and_direct_paths: true

evidence:
  link_source_events: true
  record_action_results_separately: true
  preserve_unknown_states: true
  do_not_log_raw_secrets: true

recovery:
  require_verified_subject: true
  require_remediation_evidence: true
  require_authorized_release: true
  check_other_active_holds: true
  restore_only_approved_entitlements: true
  review_after_restore: true
~~~

Các trường trên không chứng minh hệ thống có đủ khả năng. Triển khai phải ánh xạ từng hành động tới thành phần, thẩm quyền và cách xác nhận kết quả.

Ví dụ, một connector chỉ có quyền chặn grant PAM chưa thể vô hiệu tài khoản tại IdP. Nếu cần thêm hành động, phải có luồng thực hiện phù hợp thay vì ghi nhận thành công cho một thao tác không được hỗ trợ.

## 11. Credential, token và phiên có vòng đời riêng

### 11.1. Token và cookie

Một token hoặc cookie có thể tiếp tục dùng cho tới khi hết hiệu lực hoặc tới khi bên xác minh thực sự xử lý việc thu hồi, tùy kiến trúc.

Cần hiểu cách từng ứng dụng xử lý trạng thái tài khoản, cache, introspection hoặc cơ chế thu hồi được hỗ trợ. Không mặc định việc vô hiệu tại IdP lập tức được mọi ứng dụng nhận biết.

Một đối tượng có thời hạn ngắn giúp giới hạn một số rủi ro, nhưng không tự giải quyết phiên dài hạn hoặc token khác đã phát hành.

### 11.2. SSH key và chứng thư

Khóa người dùng trong PAM không tự gỡ public key đã được cài trực tiếp trên target. Cần biết nguồn chấp nhận key và phạm vi phân phối.

Chứng thư hết hạn hoặc bị thu hồi có thể ngăn xác thực mới theo kiểm tra tại server. Phiên SSH đang chạy cần được xử lý riêng nếu mục tiêu yêu cầu dừng truy cập ngay.

### 11.3. Mật khẩu và secret dùng chung

Nếu secret bị lộ, rotation có thể cần thiết nhưng phải xét các consumer và nơi sử dụng. Tài khoản hoặc credential dùng chung với dịch vụ làm tăng độ khó của việc cô lập theo người dùng.

Không ghi nhận “đã xử lý credential của An” chỉ vì đã đổi một mật khẩu, khi An từng có khả năng lấy khóa, token hoặc secret khác chưa được kiểm kê.

### 11.4. Tác vụ tại đích

Một lệnh đã khởi chạy có thể tiếp tục sau khi gateway ngắt. Một thay đổi cấu hình đã hoàn tất không bị đảo ngược bởi việc khóa identity.

Phạm vi ứng phó có thể cần đánh giá tác vụ nền, thay đổi đã tạo, tài khoản mới và cơ chế duy trì truy cập. Các hành động đó cần có thẩm quyền, bằng chứng và owner phù hợp.

## 12. Ví dụ xuyên suốt: bất thường trên identity quản trị

### 12.1. Bối cảnh

An có tài khoản làm việc hằng ngày và một identity quản trị riêng để sử dụng PAM. Khi làm nhiệm vụ, gateway dùng tài khoản kỹ thuật để mở phiên tới máy chủ.

Hệ thống nhận nhiều tín hiệu liên quan identity quản trị: một phiên mới từ môi trường chưa được xác minh, yêu cầu tới target ngoài nhiệm vụ và một hành động đặc quyền không khớp yêu cầu đã duyệt.

Các tín hiệu được liên kết theo định danh và thời gian. Chúng tạo căn cứ cho quy trình hạn chế, nhưng chưa tự xác định ai thực hiện hoặc nguyên nhân cuối cùng.

### 12.2. Hạn chế ban đầu

Theo thẩm quyền đã giao, hệ thống:

- Chặn cấp phiên mới cho identity quản trị đó tại PAM.
- Vô hiệu quyền mở phiên chưa dùng.
- Xác định các grant và phiên có liên quan.
- Tạo vụ việc với bằng chứng nguồn.
- Chuyển các hành động cần người xử lý tới đúng owner.

Không tự khóa mọi tài khoản cùng tên hoặc tài khoản làm việc hằng ngày nếu chưa xác định phạm vi và policy tương ứng.

### 12.3. Xử lý phiên và tài khoản đích

Một phiên gateway được kết thúc thành công; một phiên khác còn đang chờ xác nhận tại target.

Tài khoản kỹ thuật tại đích có thể được dùng bởi luồng khác. Nhóm xử lý đánh giá khả năng ngừng phiên thuộc An, khóa account hoặc xử lý credential theo tác động thực tế. Không tự coi mọi consumer của account là độc hại.

Nhóm cũng kiểm tra xem có SSH key hoặc đường quản trị trực tiếp ngoài gateway thuộc phạm vi cần xử lý không.

### 12.4. Xác minh với người dùng

An được liên hệ qua một kênh và quy trình xác minh phù hợp. Không chỉ gửi thông báo vào chính phiên hoặc thiết bị đang bị nghi ảnh hưởng rồi coi phản hồi là đủ.

Nếu endpoint có dấu hiệu bị kiểm soát, việc đổi mật khẩu từ endpoint đó có thể chưa giải quyết nguyên nhân. Cần phối hợp đánh giá thiết bị và các bằng chứng liên quan.

### 12.5. Kết quả từng lớp

Hồ sơ có thể ghi:

~~~text
PAM cấp mới: BLOCKED, đã xác nhận.
Quyền mở phiên chưa dùng: INVALIDATED, đã đối chiếu.
Grant tạm: REVOKED trong phạm vi đã kiểm kê.
Gateway session A: TERMINATED, đã xác nhận.
Target session B: PENDING_CONFIRMATION.
Nguồn danh tính: hành động theo quyết định của owner, có kết quả riêng.
Credential và đường trực tiếp: đang đánh giá phạm vi.
Khôi phục identity: NOT_AUTHORIZED_YET.
~~~

Đây là báo cáo trung thực hơn một cờ “identity đã khóa hoàn toàn” khi còn các phần chưa xác nhận.

## 13. Điều kiện mở lại identity

### 13.1. Xác minh chủ thể

Cần xác định đúng người hoặc đúng workload theo quy trình phù hợp. Không yêu cầu người dùng cung cấp OTP, recovery code hoặc private key cho người xử lý.

Với vendor, cần phối hợp người bảo trợ và phía quản lý danh tính. Với workload, cần xác định owner dịch vụ, nguồn thực thi và cấu hình credential.

### 13.2. Hiểu nguyên nhân và xử lý phần ảnh hưởng

Tùy tình huống, có thể cần:

- Xử lý endpoint hoặc nguồn thực thi bị ảnh hưởng.
- Thay hoặc thu hồi credential liên quan.
- Rà soát authenticator được thêm mới.
- Kiểm tra token, cookie và phiên cũ.
- Xác minh các thay đổi quyền hoặc account đã tạo.
- Khắc phục consumer gây xác thực sai lặp lại.
- Đối chiếu đường truy cập trực tiếp và nguồn khóa.
- Ghi rõ phần chưa kết luận và mức rủi ro còn lại.

Không phải mọi trường hợp đều cần tất cả hành động. Tiêu chí cần dựa trên nguyên nhân, bằng chứng và policy, không phải một danh sách thao tác máy móc.

### 13.3. Có thẩm quyền mở lại

Người xử lý kỹ thuật không mặc nhiên có quyền chấp nhận mọi rủi ro tồn dư. Quyết định mở lại cần đúng vai trò và phạm vi.

Trước khi thực thi, kiểm tra các hạn chế còn hiệu lực và vụ việc khác. Một chủ tài khoản yêu cầu mở lại không tự thay sự chấp thuận cần thiết.

### 13.4. Khôi phục quyền tối thiểu

Mở lại khả năng xác thực không có nghĩa khôi phục nguyên trạng mọi entitlement, key và ngoại lệ trước sự cố.

Có thể cần:

1. Khôi phục danh tính hoặc phương thức xác thực phù hợp.
2. Chỉ cấp lại entitlement còn có nhu cầu và được phê duyệt.
3. Yêu cầu xác thực mới theo policy.
4. Dùng JIT cho công việc tiếp theo.
5. Kiểm tra một luồng đại diện trong phạm vi an toàn.
6. Theo dõi điều kiện sau phục hồi trước khi đóng vụ việc.

Không phục hồi một key đã thu hồi do bị lộ chỉ để đăng nhập nhanh hơn.

## 14. Identity quan trọng và truy cập khẩn cấp

Một tài khoản có thể là đường quản trị cần thiết trong sự cố. Vì vậy, thiết kế cần có phương án phục hồi và break-glass trước khi sự cố xảy ra.

Đường khẩn cấp cần xác định:

- Ai có quyền sử dụng.
- Từ môi trường nào.
- Tới những target và tác vụ nào.
- Credential được bảo vệ và lấy ra ra sao.
- Thời hạn, bằng chứng và hậu kiểm.
- Cách đóng quyền tạm và xử lý sau sử dụng.

Nếu một identity thường lệ bị nghi ảnh hưởng, không nên tự chuyển mọi người sang một tài khoản khẩn cấp dùng chung không có quy trách nhiệm.

Với workload quan trọng, có thể cần cơ chế cô lập consumer, thay credential hoặc chuyển hoạt động sang nguồn thực thi khác theo thiết kế. Đây là vấn đề của kiến trúc dịch vụ và ứng phó, không chỉ một nút khóa tài khoản.

Ngoại lệ cần được ghi đúng với owner và thời hạn. Không đánh dấu một hành động ứng phó đã đạt nếu thực tế phải chấp nhận một giới hạn chưa giải quyết.

## 15. Bằng chứng và thông báo

### 15.1. Hồ sơ cần giữ được điều gì?

Một hồ sơ có thể đối chiếu nên chứa:

~~~text
ID vụ việc và policy áp dụng.
Identity ổn định và phạm vi bị ảnh hưởng.
Các tín hiệu nguồn cùng thời điểm liên quan.
Căn cứ, người hoặc cơ chế ra quyết định.
Hành động được yêu cầu ở từng thành phần.
Kết quả, thời điểm xác nhận và nguồn bằng chứng.
Các phần pending, failed hoặc unknown.
Thay đổi credential, quyền và phiên có liên quan.
Quyết định phục hồi, người có thẩm quyền và điều kiện.
Kết quả kiểm tra sau phục hồi.
~~~

Không ghi mật khẩu, OTP, private key hoặc token đầy đủ để làm bằng chứng. Có thể dùng định danh sự kiện và đối tượng được kiểm soát để liên kết các nguồn.

Bằng chứng cần được bảo vệ khỏi sửa đổi hoặc xóa trái thẩm quyền theo mô hình lưu trữ của tổ chức. Khóa identity không phải lý do xóa lịch sử của người đó.

### 15.2. Thông báo đúng đối tượng

Người dùng cần biết cách báo cáo và khôi phục theo phạm vi phù hợp. Owner hệ thống cần biết tác động tới phiên hoặc consumer. Nhóm ứng phó cần thông tin đủ để xử lý.

Không đưa chi tiết điều tra nhạy cảm vào mọi thông báo. Cũng không chỉ dựa vào một kênh có thể đã bị chiếm để xác nhận danh tính và mở lại.

Thời điểm thông báo và nội dung cần phù hợp tình huống. Chúng phải được xác định trong quy trình thay vì do từng connector tự suy đoán.

## 16. Kiểm chứng quy trình

| Tình huống | Kết quả cần quan sát |
|---|---|
| Nhiều lỗi xác thực do một consumer cấu hình sai | Có khả năng xác định consumer và tránh mở khóa lặp vô ích |
| Một nguồn cố tình tạo nhiều lần sai cho người khác | Đánh giá được nguy cơ gây khóa nhầm và phạm vi phản ứng |
| Cảnh báo có tên hiển thị trùng nhau | Không khóa sai identity chỉ từ tên |
| Chặn cấp mới tại PAM | Không còn grant hoặc phiên mới qua luồng đó |
| Phiên cũ còn hoạt động | Có hành động và kết quả riêng, không suy từ trạng thái account |
| Thu hồi token trong một ứng dụng | Không tự ghi các ứng dụng khác đã hoàn tất |
| Key được cài trực tiếp trên target | Được nhận diện trong phạm vi xử lý credential |
| Hành động API timeout | Có đối chiếu trạng thái, retry và owner cho phần chưa rõ |
| Cùng cảnh báo được gửi lại | Không tạo tác động trùng ngoài ý định |
| Mở lại đồng thời có cảnh báo mới | Không ghi đè hạn chế còn hiệu lực trái policy |
| Hạn chế có TTL hết hạn | Không tự bỏ lệnh giữ khác hoặc coi sự cố đã xử lý |
| Credential dùng chung với dịch vụ | Tác động được đánh giá và kết quả phân biệt theo consumer |
| Người giả mạo yêu cầu mở khóa | Không vượt quy trình xác minh và thẩm quyền |
| Phục hồi thành công | Chỉ quyền còn hợp lệ được cấp lại và có kiểm tra |
| Còn kết quả tại đích chưa biết | Báo UNKNOWN hoặc PENDING, không gộp vào PASS |

Kiểm chứng cần dùng identity và tài nguyên trong phạm vi được phép, ưu tiên tình huống có thể quan sát mà không gây gián đoạn không cần thiết. Không vô hiệu một account production dùng chung chỉ để hoàn thành bảng thử nghiệm.

Các chỉ số có thể theo dõi gồm thời gian từ tín hiệu tới quyết định, tới chặn cấp mới và tới kết thúc phiên; số phần còn chưa xác nhận; khóa nhầm; mở lại sai; và số đường truy cập không nằm trong phạm vi thực thi.

Không chỉ đo tốc độ khóa. Một hệ thống khóa rất nhanh nhưng sai identity hoặc không thu hồi các phiên liên quan vẫn không đạt mục tiêu.

## 17. Bài tập áp dụng

Một tổ chức tự khóa tài khoản PAM sau nhiều lần đăng nhập sai. Người dùng vẫn giữ một phiên web quản trị, một phiên SSH và một key đã cài trực tiếp trên máy chủ. Đội vận hành chỉ kiểm tra cờ disabled ở PAM, rồi báo đã thu hồi toàn bộ đặc quyền. Sau một khoảng chờ, hệ thống tự mở khóa mà không kiểm tra vụ việc và credential.

Hãy phân tích:

1. Những lớp nào đã bị hạn chế và lớp nào chưa có bằng chứng?
2. Các lần đăng nhập sai có đủ để kết luận identity bị chiếm không?
3. Có thể có nguyên nhân hợp lệ hoặc hành vi gây khóa nhầm nào?
4. Cần dùng định danh và mapping nào để tìm đúng phiên, key và tài khoản đích?
5. Những hành động nào có thể ảnh hưởng consumer hoặc người dùng khác?
6. Điều kiện nào cần đạt trước khi mở lại?
7. Làm thế nào ngăn một thao tác phục hồi cũ ghi đè cảnh báo mới?
8. Báo cáo kết quả nên diễn đạt thế nào khi một phiên tại đích chưa được xác nhận?

Một phương án đạt mục tiêu cần chỉ rõ căn cứ quyết định, phạm vi hạn chế, lớp thực thi và bằng chứng. Khóa identity là điểm khởi đầu của một chuỗi xử lý có kiểm soát; kết quả phải được xác nhận theo từng khả năng truy cập thực tế.
