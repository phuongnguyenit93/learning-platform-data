# Emergency access policy

## 1. Mục đích của chính sách truy cập khẩn cấp

Trong quản lý quyền truy cập đặc biệt (Privileged Access Management — PAM), **emergency access policy** là chính sách quy định khi nào, ai và bằng cách nào được sử dụng một tuyến truy cập khẩn cấp để bảo vệ hoặc khôi phục hệ thống quan trọng.

Cơ chế này thường được gọi là **break-glass**. Nó cần phục vụ hai mục tiêu cùng lúc:

- Có thể tiếp cận hệ thống khi quy trình hoặc thành phần truy cập thông thường không còn đáp ứng tình huống.
- Giữ trách nhiệm, phạm vi quyền, thời gian sử dụng và bằng chứng đủ rõ để kiểm soát rủi ro.

Ví dụ, nhà cung cấp danh tính (Identity Provider — IdP) gặp lỗi khiến quản trị viên không thể đăng nhập để khôi phục dịch vụ. Một tuyến dự phòng có thể cần thiết. Nhưng nếu tuyến đó vẫn phụ thuộc hoàn toàn vào chính IdP đang lỗi, chính sách chỉ tồn tại trên giấy.

Truy cập khẩn cấp là một ngoại lệ được thiết kế trước. Tên gọi “khẩn cấp” không tự trao quyền quản trị, không thay thế việc xác minh danh tính và không bảo đảm credential đã được thu hồi sau sử dụng.

Bài học tập trung vào quản trị cơ chế này cho tài khoản quản trị, tài khoản dịch vụ và hạ tầng nhạy cảm. Các giá trị thời gian, mức sự cố và trường cấu hình trong ví dụ đều là giả định thiết kế, cần được điều chỉnh theo môi trường thực tế.

## 2. Khi nào được kích hoạt?

Một tình huống nên được xem xét theo ba câu hỏi:

1. Có tác động hoặc nguy cơ đủ nghiêm trọng để cần hành động ngay không?
2. Tuyến truy cập thông thường có sẵn, đáng tin cậy và đủ nhanh cho hành động đó không?
3. Người kích hoạt có thuộc phạm vi và thẩm quyền đã được chính sách cho phép không?

Chính sách cần định nghĩa điều kiện cụ thể, thay vì để người dùng tự quyết rằng việc của mình “rất gấp”.

| Tình huống | Cách xem xét |
|---|---|
| IdP hoặc thành phần xác thực lỗi, không thể dùng tuyến thông thường để khôi phục dịch vụ trọng yếu | Có thể phù hợp với tuyến khôi phục đã chuẩn bị cho lỗi danh tính |
| Vault hoặc cổng PAM không hoạt động, trong khi cần xử lý sự cố nghiêm trọng | Chỉ dùng phương án dự phòng đã được thiết kế cho thành phần đó |
| Có căn cứ tuyến danh tính thông thường đang bị xâm nhập | Cần đánh giá độ tin cậy của danh tính, thiết bị và kênh điều khiển trước khi chọn tuyến khác |
| Phải cô lập tài nguyên để ngăn tác động lan rộng | Thực hiện theo thẩm quyền ứng phó sự cố và phạm vi cho phép |
| Người duyệt chưa phản hồi nhưng công việc không có tác động khẩn cấp được định nghĩa | Chuyển tuyến hoặc xử lý theo quy trình thông thường |
| Muốn bỏ qua việc ghi phiên, hạn chế lệnh hoặc thủ tục thay đổi | Không phải căn cứ tự thân để sử dụng break-glass |
| Công việc đã được lên lịch nhưng người thực hiện quên xin quyền | Xử lý vấn đề lập kế hoạch; không tự chuyển thành tình huống khẩn cấp |

“Không dùng được tuyến thông thường” có thể do tuyến bị lỗi hoặc không còn đáng tin cậy. Hai nguyên nhân cần cách xử lý khác nhau. Trong tình huống nghi ngờ xâm nhập, một đường kết nối khác chưa chắc an toàn nếu vẫn dùng cùng thiết bị, credential hoặc nguồn xác thực đã bị ảnh hưởng.

Nếu hệ thống quản lý sự cố cũng không hoạt động, chính sách nên cho phép tạo mã sự kiện tạm thời và đối soát sau. Không yêu cầu một phụ thuộc đang lỗi phải hoạt động mới được ghi nhận tình huống khẩn cấp.

## 3. Xác định phạm vi, trách nhiệm và thẩm quyền

Mỗi tuyến khẩn cấp cần được gắn với tài nguyên, loại sự cố và người chịu trách nhiệm.

| Vai trò | Trách nhiệm cần xác định |
|---|---|
| Chủ sở hữu chính sách | Duy trì phạm vi, điều kiện, ngoại lệ, lịch rà soát và diễn tập |
| Chủ sở hữu tài nguyên | Xác định khả năng khôi phục, mức tác động và yêu cầu kỹ thuật của tài nguyên |
| Người chỉ huy hoặc điều phối sự cố | Xác nhận mục tiêu, ưu tiên và phối hợp hành động trong thẩm quyền được giao |
| Người có thẩm quyền cho kích hoạt | Chấp nhận lần sử dụng theo tuyến và điều kiện chính sách |
| Người giữ hoặc phát hành phương tiện truy cập | Quản lý việc lấy credential, thiết bị hoặc vật liệu khôi phục theo cơ chế kiểm soát |
| Người thực hiện | Sử dụng quyền đúng mục tiêu, ghi nhận thao tác và kết thúc truy cập |
| Người ghi nhận hoặc giám sát | Theo dõi mốc thời gian, phạm vi và bằng chứng khi cơ chế tự động không đầy đủ |
| Người rà soát sau sử dụng | Đối chiếu điều kiện kích hoạt, quyền thực tế, thay đổi và kết quả thu hồi |

Một người có thể đảm nhiệm nhiều vai trò nếu chính sách cho phép. Nếu cần hai người độc lập, phải kiểm tra danh tính thực tế; hai tài khoản của cùng một người không tạo ra tính độc lập.

Cần phân biệt:

- **Phê duyệt trước khi sử dụng:** có người ra quyết định cho lần kích hoạt.
- **Kích hoạt theo thẩm quyền được giao trước:** chính sách đã cho một vai trò được tự kích hoạt trong điều kiện cụ thể.
- **Rà soát sau sử dụng:** đánh giá sự kiện đã xảy ra.

Không ghi một lần kích hoạt theo thẩm quyền giao trước thành “được người khác duyệt” nếu điều đó không diễn ra. Rà soát sau cũng không làm phát sinh ngược một quyết định phê duyệt trước.

Nếu thiếu người duyệt, chỉ áp dụng tuyến dự phòng hoặc điều kiện giao quyền trước đã được thiết kế. Người thực hiện không tự bổ sung một ngoại lệ mới trong lúc sử dụng.

## 4. Chọn hình thức truy cập khẩn cấp

### 4.1. Role khẩn cấp qua hệ thống danh tính

Có thể sử dụng role đặc biệt với cơ chế JIT, xác thực và thời hạn riêng. Cách này giúp giữ liên kết với danh tính người dùng và giảm quyền thường trực.

Tuy nhiên, nó chỉ có ích khi các phụ thuộc để kích hoạt role còn hoạt động và đáng tin cậy. Một role bắt buộc đăng nhập qua IdP không phải phương án khôi phục lỗi mất toàn bộ khả năng xác thực của chính IdP đó.

### 4.2. Tài khoản khôi phục độc lập

Một số tài nguyên có thể cần tài khoản hoặc cơ chế xác thực riêng cho tình huống tuyến trung tâm không dùng được.

Cần xác định:

- Tài nguyên nào thực sự cần tuyến độc lập.
- Credential hoặc yếu tố xác thực được bảo vệ ở đâu.
- Ai được tiếp cận và ai theo dõi việc sử dụng.
- Quyền có thể thu hẹp đến mức nào.
- Cách xử lý sau mỗi lần sử dụng.
- Cách kiểm tra tuyến vẫn hoạt động mà không làm lộ credential.

Không mặc định mọi tài khoản khẩn cấp phải luôn bị vô hiệu hóa. Nếu bật lại tài khoản cũng cần một đường quản trị đang lỗi, thiết kế có thể không sử dụng được. Trạng thái sẵn sàng phải phù hợp với cơ chế bảo vệ và mô hình sự cố, được đánh giá rõ thay vì áp dụng một quy tắc hình thức.

### 4.3. Phương tiện khôi phục hoặc credential dự phòng ngoài tuyến thường

Trong một số thiết kế, cần có phương tiện được bảo quản độc lập, chẳng hạn thiết bị xác thực, credential khôi phục hoặc vật liệu phục hồi được phép sử dụng cho một hệ thống cụ thể.

“Dự phòng” không có nghĩa sao chép bí mật ra nhiều nơi không quản lý. Cần có mã kiểm kê, phạm vi sử dụng, kiểm soát tiếp cận, lịch kiểm tra và quy trình cập nhật khi credential thay đổi.

Credential dài hạn được giữ để khôi phục vẫn có rủi ro tồn tại lâu dài. Chính sách phải nêu cơ chế bảo vệ, kiểm tra, thay thế và xử lý sau khi được tiết lộ cho người sử dụng.

### 4.4. Console hoặc kênh quản trị ngoài đường thông thường

Một tuyến console hoặc quản trị ngoài băng có thể hỗ trợ khi đường mạng hoặc cổng truy cập thường bị lỗi. Tuyến đó vẫn có cơ chế xác thực, quyền và phụ thuộc riêng.

Không coi việc có console là có thể bỏ qua yêu cầu xác thực của nền tảng. Cần kiểm tra toàn bộ chuỗi truy cập, bao gồm thiết bị, kết nối, danh tính và khả năng thực thi trên tài nguyên đích.

## 5. Lập bản đồ phụ thuộc trước khi có sự cố

Một tuyến khẩn cấp chỉ đáng tin cậy nếu đã hiểu những thành phần mà nó cần.

| Thành phần bị lỗi hoặc không đáng tin cậy | Câu hỏi cần trả lời | Bằng chứng cần có trước khi công bố tuyến sẵn sàng |
|---|---|---|
| IdP | Có thể xác thực quản trị viên mà không phụ thuộc cùng điểm lỗi không? | Kết quả kiểm tra tuyến thay thế và danh tính đủ điều kiện |
| Vault | Có lấy được phương tiện cần thiết theo cơ chế dự phòng được phép không? | Kiểm kê, kiểm soát tiếp cận và lần kiểm tra gần nhất |
| Proxy hoặc cổng PAM | Có kênh quản trị thay thế đã giới hạn không? | Đường kết nối, quyền tại đích và cách ghi nhận sử dụng |
| Hệ thống giám sát | Có thể ghi bằng chứng ở đâu khi kênh tập trung lỗi? | Cơ chế ghi cục bộ hoặc độc lập và cách chuyển lại sau |
| Hệ thống ticket hoặc liên lạc | Có thể xác nhận sự kiện và người tham gia bằng cách nào? | Phương thức liên lạc và ghi nhận dự phòng |
| Mạng quản trị | Có đường tiếp cận thay thế được quản lý không? | Kết quả kiểm tra kết nối và xác thực đầu cuối |
| Nguồn thời gian | Làm sao xác định hạn cuối và thứ tự thao tác nếu đồng hồ lệch? | Nguồn tham chiếu và cách ghi độ không chắc chắn |

Cần xem cả lỗi đồng thời. Ví dụ, một phương tiện “offline” không giải quyết được lỗi vault nếu người giữ phải đăng nhập qua cùng IdP đang lỗi để tìm hướng dẫn hoặc thông tin liên hệ.

Mức độc lập cần phù hợp với kịch bản. Không thể suy ra một tuyến an toàn chỉ vì khác tên sản phẩm hoặc khác địa chỉ truy cập.

Trong tình huống nghi ngờ xâm nhập, cần có cách xác minh người tham gia và sử dụng thiết bị, kênh điều khiển có độ tin cậy phù hợp. Không làm lộ credential khẩn cấp qua một kênh chưa được xác minh chỉ vì đang có áp lực thời gian.

## 6. Những nội dung tối thiểu của chính sách

Một chính sách nên có các thành phần sau:

1. Mục tiêu và tài nguyên thuộc phạm vi.
2. Điều kiện được kích hoạt và điều kiện không được kích hoạt.
3. Vai trò có thẩm quyền, người thực hiện và yêu cầu độc lập.
4. Tuyến thông thường, tuyến dự phòng và phụ thuộc của từng tuyến.
5. Phạm vi quyền, thời gian sử dụng và cách gia hạn.
6. Yêu cầu xác thực, quản lý credential và giám sát.
7. Phương án khi một thành phần kiểm soát không sẵn sàng.
8. Quy trình kết thúc, thu hồi và xác minh tại đích.
9. Bằng chứng, rà soát sau sử dụng và xử lý sai lệch.
10. Lịch kiểm tra khả năng vận hành và cập nhật.

Đoạn YAML sau là mô hình minh họa, không phải cấu hình chạy trực tiếp:

~~~yaml
emergency_access_policy:
  policy_id: production-recovery
  version: 3
  accountable_team_reference: team-platform-security
  scope:
    environment: production
    resource_set_reference: approved-recovery-targets
  activation:
    requires_qualifying_incident: true
    requires_incident_reference: true
    permitted_routes:
      - independent_recovery_console
      - preapproved_offline_credential_route
    authority_model: route_specific
    record_actual_authorization_method: true
  access:
    minimum_scope_for_recovery: true
    requested_duration_minutes: 30
    automatic_extension: false
    deadline_enforcement_must_be_documented_per_route: true
  credential:
    disclose_only_to_authorized_operator: true
    record_reference_without_secret: true
    post_use_handling_required: true
  evidence:
    use_central_recording_when_available: true
    fallback_record_reference: approved-independent-record
    mark_recording_gaps_explicitly: true
  closure:
    end_emergency_sessions: true
    handle_exposed_credentials: true
    inspect_relevant_access_changes: true
    verify_target_state: true
    independent_review_required: true
~~~

Một cờ như end_emergency_sessions thể hiện yêu cầu của thiết kế. Nó không chứng minh hệ thống đích đã hỗ trợ hoặc thực hiện việc đó. Mỗi tuyến cần mô tả cơ chế thực tế và bằng chứng kiểm tra.

## 7. Tuyên bố sự cố và cho phép kích hoạt

### 7.1. Xác nhận mục tiêu khôi phục

Trước khi lấy quyền, ghi tối thiểu:

- Sự kiện hoặc nguy cơ đang xử lý.
- Vì sao tuyến thông thường không đáp ứng.
- Tài nguyên cần tiếp cận.
- Hành động dự kiến và mức quyền cần thiết.
- Người thực hiện, căn cứ thẩm quyền và phương thức cho phép.
- Hạn kết thúc dự kiến.
- Các kiểm soát bị thiếu và biện pháp bù đã được chính sách cho phép.

Nội dung có thể được ghi bằng cơ chế dự phòng nếu nền tảng trung tâm không sẵn sàng. Sau đó phải nối lại với hồ sơ chính thức, giữ nguyên thời điểm và tác giả ban đầu.

### 7.2. Kiểm tra thẩm quyền và xung đột

Nếu tuyến yêu cầu hai người, cần xác định ai ra quyết định và ai sử dụng quyền. Người làm chứng hoặc giữ phương tiện không tự trở thành approver nếu không có thẩm quyền.

Nếu tuyến cho phép một vai trò kích hoạt theo điều kiện giao trước, cần kiểm tra người đó đúng vai trò và sự kiện đúng điều kiện. Không đổi cách ghi thành phê duyệt hai người cho đủ mẫu.

Khi không xác minh được các điều kiện bắt buộc, không cấp mới theo tuyến đó. Chỉ chuyển sang một tuyến khác nếu tuyến đó đã được phép cho tình huống tương ứng và vẫn đáp ứng điều kiện riêng.

### 7.3. Phạm vi phải đủ cụ thể

“Khôi phục hệ thống” quá rộng để giải thích mọi thao tác. Có thể cần quyền mạnh trong một tình huống thực tế, nhưng phải nêu tài nguyên, mục tiêu và lý do không thể dùng quyền hẹp hơn.

Khi có thể, tách nhiệm vụ: xác minh trạng thái, khôi phục cấu hình, kiểm tra dịch vụ rồi kết thúc. Không mở quyền trên toàn bộ hạ tầng chỉ vì một thành phần cần sửa.

## 8. Kích hoạt, giới hạn thời gian và gia hạn

### 8.1. Ghi nhận lần sử dụng cụ thể

Một lần kích hoạt cần có mã riêng và nối với:

~~~text
incident_reference
policy_version
emergency_route_reference
operator_identity_reference
authorization_basis_reference
target_resources
allowed_scope
activation_time
operational_deadline
credential_or_session_reference
known_control_gaps
~~~

Không ghi giá trị credential vào bản ghi này. Nếu phải sử dụng tài khoản dùng chung, cần ghi đủ thông tin để liên kết người thực hiện với lần lấy credential và phiên liên quan.

### 8.2. Phân biệt hạn vận hành và khả năng tự hết hạn

Với grant JIT hoặc credential tạm thời có cơ chế thực thi phù hợp, có thể áp hạn cuối bằng hệ thống.

Với một mật khẩu khôi phục tĩnh hoặc tài khoản cục bộ, việc ghi “30 phút” trong hồ sơ không làm mật khẩu tự hết hiệu lực. Tuyến đó cần nêu rõ:

- Thành phần nào có thể đóng phiên hoặc chặn thao tác.
- Ai theo dõi hạn cuối khi không có bộ điều khiển tự động.
- Credential được thay đổi hoặc vô hiệu hóa như thế nào.
- Cách kiểm tra bản sao đã tiết lộ không còn dùng được.
- Biện pháp xử lý nếu không thể hoàn tất đúng hạn.

Không báo “đã tự hết hạn” nếu thực tế chỉ có một nhắc việc thủ công. Giới hạn kỹ thuật phải được thể hiện trong đánh giá rủi ro và kế hoạch thu hồi.

### 8.3. Gia hạn là quyết định mới

Nếu chưa khôi phục xong trước hạn, cần ghi mục tiêu còn lại, lý do, phạm vi và người có thẩm quyền cho thời gian bổ sung theo chính sách.

Không để việc phiên vẫn hoạt động tự kéo dài quyền. Không đặt lại toàn bộ thời gian chỉ vì hệ thống điều khiển được khởi động lại hoặc lời gọi kích hoạt được gửi lại.

Giới hạn tổng thời gian và số lần gia hạn nên phù hợp với loại sự cố. Khi không thể thực thi hạn cuối tự động, mỗi lần gia hạn vẫn cần được theo dõi và kiểm chứng, không biến thành một tuyến quản trị thường trực.

## 9. Quy tắc trong thời gian sử dụng

Người thực hiện cần giữ hoạt động trong mục tiêu khôi phục đã được cho phép.

Các yêu cầu thực tế:

- Sử dụng danh tính và thiết bị theo tuyến đã được xác minh.
- Giữ phạm vi tài nguyên và thao tác hẹp nhất có thể đáp ứng nhiệm vụ.
- Ghi nhận các thay đổi quan trọng và lý do.
- Hạn chế tiết lộ hoặc sao chép credential ra ngoài cơ chế đã duyệt.
- Không tạo đường truy cập lâu dài ngoài mục tiêu và thẩm quyền được giao.
- Nếu phải thay đổi cơ chế bảo vệ để khôi phục, ghi điều kiện, phạm vi và cách đưa về trạng thái được chấp nhận.
- Bảo vệ log và bằng chứng, kể cả khi không thể gửi về hệ thống tập trung ngay.
- Báo thay đổi phạm vi hoặc nguy cơ mới cho người điều phối theo quy trình.

JEA — Just-Enough Access — vẫn hữu ích trong khẩn cấp nếu nền tảng hỗ trợ các thao tác cần thiết. Nếu tình huống thực sự cần quyền rộng, cần ghi rõ vì sao và áp dụng kiểm soát thời gian, giám sát, trách nhiệm phù hợp.

Truy cập khẩn cấp không chỉ dành cho con người. Nếu phải sử dụng hoặc thay đổi tài khoản dịch vụ để phục hồi, phải xét các workload phụ thuộc. Đổi credential mà chưa cập nhật dịch vụ có thể tạo thêm sự cố.

Nếu hệ thống ghi phiên không sẵn sàng, không tuyên bố đã có bản ghi phiên đầy đủ. Dùng phương án bù được phép và đánh dấu khoảng trống để người rà soát đánh giá đúng mức bằng chứng.

## 10. Chuyển về tuyến thông thường và kết thúc quyền

Khi tuyến truy cập thông thường hoạt động trở lại, người điều phối cần quyết định thời điểm bàn giao phù hợp. Không tiếp tục dùng break-glass vì thuận tiện.

Tuy nhiên, khôi phục một thành phần không có nghĩa có thể ngắt ngay mọi thao tác đang chạy mà không xét ảnh hưởng. Cần xác định điểm bàn giao, người tiếp nhận và các thay đổi chưa hoàn tất.

Một lần đóng truy cập nên xử lý riêng từng lớp:

| Lớp cần xử lý | Nội dung phải xác minh |
|---|---|
| Khả năng cấp mới | Không tiếp tục tạo grant hoặc lấy credential từ lần kích hoạt đã kết thúc |
| Phiên hiện có | Phiên quản trị đã được kết thúc hoặc giới hạn theo quyết định |
| Credential đã tiết lộ | Được thay thế, vô hiệu hóa hoặc xử lý theo cơ chế có hiệu lực tại nơi xác thực |
| Quyền được cấp thêm | Role, membership hoặc gán quyền tạm thời đã được thu hồi |
| Đường truy cập phát sinh | Các thay đổi cho phép truy cập tiếp đã được xem xét và xử lý |
| Tác vụ đang chạy | Danh tính, quyền và vòng đời được kiểm soát; không giả định đóng phiên sẽ dừng mọi tác vụ |
| Cấu hình hệ thống | Trạng thái sau khôi phục đã được xác nhận |
| Phương tiện dự phòng | Được cập nhật và bảo quản lại để sẵn sàng cho lần cần thiết tiếp theo |

Đổi mật khẩu không tự bảo đảm mọi phiên đã mở bị ngắt. Đóng phiên cũng không làm bản sao mật khẩu mất hiệu lực. Cần kiểm tra hành vi tại từng nền tảng.

Với credential dùng chung cho dịch vụ, việc thay thế phải phối hợp các phụ thuộc. Nếu chưa thể thay ngay, ghi rõ rủi ro còn tồn tại, người chịu trách nhiệm, biện pháp tạm thời và hạn xử lý. Không ghi hoàn tất thu hồi khi thực tế chỉ mới lên kế hoạch.

## 11. Bằng chứng và rà soát sau sử dụng

### 11.1. Cần lưu những gì?

Một hồ sơ đủ để rà soát thường gồm:

- Điều kiện kích hoạt và bằng chứng tuyến thông thường không đáp ứng.
- Phiên bản chính sách và tuyến khẩn cấp đã dùng.
- Người thực hiện, người cho phép hoặc căn cứ giao quyền trước.
- Mốc bắt đầu, hạn dự kiến, các lần gia hạn và thời điểm kết thúc.
- Tài nguyên, quyền và thay đổi thực tế.
- Tham chiếu phiên, credential và log, không chứa giá trị bí mật.
- Những kiểm soát không hoạt động và phương án bù thực tế.
- Kết quả thu hồi, xử lý credential và xác minh trạng thái đích.
- Các tồn tại chưa hoàn tất cùng người tiếp nhận.
- Kết luận rà soát và cải tiến cần thực hiện.

Dữ liệu cần có quyền đọc và thời gian lưu phù hợp. Không đưa toàn bộ thông tin nhạy cảm vào một báo cáo được chia sẻ rộng.

### 11.2. Khi chỉ có bằng chứng cục bộ

Có thể cần thu thập log từ tài nguyên, ghi nhận thao tác hoặc dữ liệu từ một kênh độc lập sau khi kết nối được khôi phục.

Giữ nguyên nguồn, thời điểm thu thập và hạn chế của bằng chứng. Nếu đồng hồ không đồng bộ, ghi rõ độ không chắc chắn khi dựng lại trình tự.

Bản ghi cục bộ do người có quyền quản trị toàn hệ thống kiểm soát có giới hạn về độ tin cậy. Chuyển dữ liệu sang nơi quản lý độc lập khi có thể và đối chiếu nhiều nguồn. Một giá trị băm giúp kiểm tra dữ liệu có thay đổi so với bản đã thu hay không; nó không tự chứng minh dữ liệu trước khi thu chưa từng bị sửa.

### 11.3. Rà soát cần độc lập ở mức phù hợp

Người rà soát cần xem việc kích hoạt có đúng điều kiện, phạm vi có hợp lý và việc đóng quyền có bằng chứng không.

Rà soát không chỉ để xác nhận “đã khôi phục dịch vụ”. Cần tìm quyền còn sót, credential chưa xử lý, khả năng truy cập lâu dài được tạo ra và lỗ hổng của tuyến dự phòng.

Nếu nguồn lực không cho phép rà soát độc lập ngay, giữ trạng thái chờ và giao người có thẩm quyền tiếp nhận. Không để người thực hiện tự đánh dấu đã có đánh giá độc lập.

## 12. Ví dụ xuyên suốt: IdP và cổng PAM không sẵn sàng

Giả định một sự cố làm quản trị viên không thể dùng IdP và cổng PAM để khôi phục dịch vụ quan trọng. Tổ chức đã có tuyến console độc lập, credential khôi phục được bảo quản riêng và quy trình hai người có thẩm quyền cho lần sử dụng này.

Tuyến dùng mật khẩu tĩnh nên hạn vận hành phải được giám sát theo quy trình. Mật khẩu chỉ mất hiệu lực khi được xử lý tại nơi xác thực; việc ghi một hạn cuối không đủ để tự vô hiệu hóa nó.

| Thời điểm | Sự kiện | Bằng chứng hoặc điều kiện cần ghi |
|---|---|---|
| 02:00 | Xác nhận sự cố đủ điều kiện | Mã sự kiện, tác động và lý do không dùng tuyến thường |
| 02:03 | Hoàn tất bước cho phép và lấy phương tiện theo tuyến dự phòng | Danh tính, thẩm quyền, tài nguyên và tham chiếu phương tiện |
| 02:05 | Bắt đầu truy cập console | Người thực hiện, phạm vi và hạn vận hành 02:35 |
| 02:10 | Thực hiện thay đổi khôi phục | Mục đích, thay đổi và bằng chứng có thể thu |
| 02:18 | IdP và cổng PAM hoạt động lại | Kết quả kiểm tra và kế hoạch chuyển tuyến |
| 02:22 | Bàn giao sang tuyến thông thường | Người tiếp nhận, công việc còn lại và trạng thái tài nguyên |
| 02:23 | Kết thúc phiên khẩn cấp | Xác nhận phiên đã kết thúc; chưa coi mật khẩu cũ đã vô hiệu |
| 02:25 | Xử lý credential và cập nhật phương tiện dự phòng | Kết quả tại nơi xác thực và hồ sơ bảo quản mới |
| 02:26 | Xác minh trạng thái sau sử dụng | Quyền, phiên, thay đổi truy cập và các tồn tại |
| Sau sự cố | Rà soát độc lập | Kết luận, khoảng trống bằng chứng và hành động cải tiến |

Nếu không thể xử lý credential lúc 02:25, hồ sơ phải giữ trạng thái chưa hoàn tất ở lớp đó, dù dịch vụ đã ổn định. Người chịu trách nhiệm cần áp dụng biện pháp tạm thời được phép và theo dõi tới khi xác minh xong.

Nếu tuyến console cũng phụ thuộc vào IdP đang lỗi, tình huống không thể hoàn thành theo thiết kế trên. Đây là lỗi phụ thuộc cần được phát hiện qua diễn tập, không phải lý do tự tìm một đường truy cập chưa được phép.

## 13. Kiểm tra và diễn tập khả năng vận hành

Một chính sách tốt cần được kiểm tra bằng các tình huống phản ánh lỗi thực tế. Có thể bắt đầu bằng diễn tập trên giấy và môi trường thử nghiệm, sau đó kiểm tra vận hành theo kế hoạch được phép.

Không gây lỗi IdP, vault, mạng quản trị hoặc dịch vụ sản xuất chỉ để thử khả năng break-glass nếu không có phạm vi và kế hoạch kiểm soát phù hợp.

| Tình huống diễn tập | Kết quả cần chứng minh |
|---|---|
| Không dùng được IdP | Tuyến được thiết kế cho lỗi đó vẫn xác thực được người đủ điều kiện |
| Vault không truy cập được | Phương án dự phòng có thể lấy đúng phương tiện mà không làm lộ bí mật ngoài phạm vi |
| Người duyệt chính vắng mặt | Tuyến dự phòng hoặc điều kiện giao quyền trước hoạt động đúng |
| Người không đủ thẩm quyền yêu cầu lấy credential | Yêu cầu không được chấp nhận chỉ vì gắn nhãn khẩn cấp |
| Hệ thống ghi phiên không hoạt động | Phương án bù có dữ liệu thực tế và ghi rõ phần thiếu |
| Gần hết thời gian nhưng công việc chưa xong | Có quyết định gia hạn hoặc kết thúc đúng tuyến |
| Dịch vụ trung tâm khởi động lại | Không tự mở lại lần kích hoạt hoặc đặt lại toàn bộ hạn cuối |
| Credential đã được sử dụng | Có thể xử lý tại đích và cập nhật phương tiện khôi phục |
| Thay đổi nhân sự hoặc nhóm | Chỉ người còn đủ điều kiện tiếp cận được tuyến |
| Đường thường hoạt động trở lại | Có thể bàn giao và đóng truy cập khẩn cấp có kiểm chứng |

Kiểm tra cả khả năng sử dụng và khả năng đóng. Một tuyến giúp đăng nhập thành công nhưng không quản lý được credential sau sử dụng vẫn còn khoảng trống quan trọng.

Với kiểm tra trên hệ thống thật, chọn cách xác minh phù hợp và được phép. Không thực hiện nhiều lần đăng nhập thất bại hoặc thay đổi credential tùy tiện làm khóa tài khoản khôi phục hay gián đoạn dịch vụ.

## 14. Chỉ số quản trị và cải tiến

Các chỉ số nên phản ánh cả độ sẵn sàng và chất lượng kiểm soát:

- Số tài nguyên cần tuyến khẩn cấp và số đã có tuyến được kiểm chứng.
- Số tuyến quá hạn kiểm tra hoặc có phụ thuộc chưa xác minh.
- Số tài khoản, phương tiện khôi phục chưa có người chịu trách nhiệm hợp lệ.
- Thời gian từ tuyên bố sự cố tới truy cập được theo đúng thẩm quyền.
- Số lần sử dụng theo từng loại tình huống và tuyến.
- Số lần gia hạn, thay đổi phạm vi hoặc dùng ngoại lệ.
- Số lần chưa có đầy đủ bằng chứng bắt buộc.
- Thời gian xử lý credential sau sử dụng và số trường hợp còn tồn đọng.
- Số quyền, phiên hoặc thay đổi truy cập còn sót sau khi tuyên bố đóng.
- Số lần truy cập khẩn cấp được dùng vì vấn đề quy trình thông thường lặp lại.

Cần nêu rõ mẫu số và phạm vi. Ví dụ, có 10 tuyến trong danh mục nhưng chỉ 8 tuyến được kiểm tra đạt trong kỳ thì tỷ lệ đó là 8 / 10 cho danh mục đã biết. Nó không chứng minh mọi tài nguyên quan trọng đều đã có tuyến phù hợp.

Thời gian truy cập ngắn không đủ để kết luận chính sách tốt nếu việc xác thực, phạm vi hoặc thu hồi không đạt. Ngược lại, quy trình quá phức tạp khiến không thể sử dụng trong sự cố cũng cần được sửa.

Nhiều lần break-glass vì chờ phê duyệt công việc định kỳ là dấu hiệu cần xem lại quy trình thường, phạm vi JIT/JEA hoặc năng lực trực. Không nên giải quyết bằng cách bình thường hóa tuyến khẩn cấp.

## 15. Bài thực hành xây dựng một tuyến khẩn cấp

Chọn một dịch vụ giả lập và giả định IdP, vault hoặc cổng PAM có thể lỗi độc lập. Không sử dụng credential thật trong tài liệu bài tập.

### 15.1. Sản phẩm cần tạo

1. Mô tả tình huống đủ điều kiện và những tình huống không đủ điều kiện.
2. Danh sách tài nguyên, tài khoản hoặc phương tiện cần dùng.
3. Sơ đồ phụ thuộc của tuyến thông thường và tuyến khẩn cấp.
4. Bảng vai trò, thẩm quyền, yêu cầu độc lập và tuyến khi thiếu người.
5. Phạm vi quyền, hạn vận hành và cơ chế gia hạn.
6. Cách ghi bằng chứng khi hệ thống trung tâm không hoạt động.
7. Kế hoạch đóng phiên, xử lý credential và xác minh tại đích.
8. Kịch bản diễn tập và tiêu chí kết luận.

### 15.2. Những câu hỏi phải trả lời được

- Nếu IdP lỗi, người thực hiện được xác minh bằng gì?
- Nếu vault lỗi, cách lấy phương tiện có còn phụ thuộc vào vault hay không?
- Nếu dùng mật khẩu tĩnh, điều gì thực sự làm mật khẩu cũ mất hiệu lực?
- Nếu không có bộ điều khiển tự động, ai theo dõi hạn cuối và làm gì khi quá hạn?
- Nếu một người dùng hai tài khoản, hệ thống có nhận ra xung đột không?
- Nếu không có bản ghi phiên, bằng chứng thay thế là gì và còn thiếu gì?
- Nếu đã đóng phiên nhưng còn tác vụ nền hoặc quyền phát sinh, ai xử lý?
- Nếu không thể hoàn tất thu hồi, hồ sơ được giữ mở và nâng cấp thế nào?

### 15.3. Ví dụ đánh giá một thiết kế chưa đạt

Một đội khai báo có tài khoản khẩn cấp, mật khẩu nằm trong vault, hướng dẫn nằm sau IdP, không có phương án dự phòng và chỉ đặt lịch nhắc đổi mật khẩu sau sử dụng.

Thiết kế đó chưa chứng minh được khả năng khôi phục khi IdP hoặc vault lỗi. Lịch nhắc cũng chưa chứng minh credential đã mất hiệu lực.

Hướng cải thiện là xác định kịch bản cần phục vụ, thiết kế phụ thuộc phù hợp, kiểm soát phương tiện dự phòng, ghi rõ giới hạn thời gian thực tế và kiểm chứng quy trình xử lý credential tại đích. Không chỉ thêm một nhãn “break-glass” vào tài khoản.

## 16. Những lỗi chính sách thường gặp

| Lỗi | Hệ quả | Hướng xử lý |
|---|---|---|
| Bất kỳ công việc gấp nào cũng được coi là khẩn cấp | Tuyến dự phòng trở thành cách bỏ qua quy trình | Định nghĩa điều kiện và rà soát nguyên nhân sử dụng |
| Tuyến khẩn cấp phụ thuộc cùng điểm lỗi với tuyến thường | Không thể truy cập khi cần | Lập bản đồ và kiểm tra phụ thuộc theo kịch bản |
| Credential dự phòng được sao chép tự do | Khó biết ai có khả năng sử dụng | Kiểm kê, giới hạn tiếp cận và xử lý sau tiết lộ |
| Có hạn trên giấy nhưng không có cơ chế thực thi | Quyền hoặc credential còn dùng được sau hạn | Nêu đúng giới hạn, trách nhiệm và cách thu hồi tại đích |
| Thiếu người duyệt thì tự cho phép | Thẩm quyền bị mở rộng ngoài chính sách | Chỉ dùng tuyến dự phòng hoặc giao quyền trước hợp lệ |
| Đóng phiên được coi là thu hồi toàn bộ | Credential, quyền và tác vụ có thể còn tồn tại | Xử lý và xác minh từng lớp |
| Ghi đã có log đầy đủ khi hệ thống ghi nhận đang lỗi | Hồ sơ tạo cảm giác kiểm soát sai | Ghi rõ dữ liệu thực tế và khoảng trống |
| Chỉ kiểm tra đăng nhập, không kiểm tra đóng quyền | Khả năng khôi phục có nhưng rủi ro còn kéo dài | Diễn tập cả kích hoạt, bàn giao, thu hồi và cập nhật phương tiện |
| Dịch vụ khôi phục là đóng luôn sự kiện truy cập | Bỏ sót credential, quyền hoặc đánh giá sau sử dụng | Theo dõi các tồn tại tới khi có bằng chứng hoàn tất |

Một chính sách truy cập khẩn cấp có thể vận hành khi người có thẩm quyền tiếp cận được đúng tài nguyên trong tình huống đã định nghĩa, biết rõ quyền và thời gian được sử dụng, rồi kết thúc bằng việc thu hồi có kiểm chứng. Bằng chứng về những gì thực sự đã xảy ra giúp tổ chức cải thiện khả năng phục hồi mà vẫn giữ trách nhiệm đối với quyền đặc biệt.
