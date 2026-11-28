# Policy condition theo thời gian trong PAM

## 1. Điều kiện theo thời gian là gì?

**Policy condition theo thời gian** là điều kiện ủy quyền sử dụng thời điểm, khoảng thời gian hoặc độ mới của một dữ kiện để quyết định một hành động có được phép hay không.

Trong PAM, cùng một người, target và role có thể được phép lúc này nhưng không được phép lúc khác. Ví dụ, một kỹ sư chỉ được mở phiên chẩn đoán production trong cửa sổ hỗ trợ đã duyệt; một quyền mở phiên chỉ dùng được trong vài phút; hoặc một thao tác nhạy cảm yêu cầu bằng chứng MFA đủ mới.

Thời gian là một chiều của quyết định, cần kết hợp với:

- Danh tính và entitlement còn hợp lệ.
- Target, account và tác vụ được cấp.
- Phê duyệt và phân tách nhiệm vụ.
- Điều kiện thiết bị, đường truy cập và credential.
- Quyền hiệu lực tại đích.
- Giám sát, kết thúc phiên và bằng chứng thu hồi.

Một lịch truy cập đúng không tự làm quyền quản trị rộng trở thành least privilege. Một token có hạn dùng cũng không tự bảo đảm phiên tại đích kết thúc cùng lúc.

## 2. Không gộp mọi thời hạn thành một giá trị

Một yêu cầu PAM có thể liên quan nhiều khái niệm thời gian:

| Khái niệm | Câu hỏi | Phạm vi thường cần định nghĩa |
|---|---|---|
| Thời hạn quan hệ hoặc entitlement | Chủ thể còn đủ điều kiện nhận quyền không? | Đánh giá cấp quyền và các sự kiện thay đổi |
| Cửa sổ phê duyệt | Quyết định được dùng hoặc công việc được thực hiện khi nào? | Phải phân biệt hai ý nghĩa này |
| Khoảng cấp grant | Khi nào hệ thống được tạo grant? | Bước cấp |
| Hạn quyền mở phiên | Khi nào được tiêu thụ quyền để mở phiên? | Bước mở |
| Cửa sổ công việc | Hoạt động được phép diễn ra trong khoảng nào? | Có thể áp dụng suốt phiên |
| Thời lượng tuyệt đối | Một phiên tồn tại tối đa bao lâu? | Từ mốc bắt đầu đã xác định |
| Idle timeout | Không hoạt động bao lâu thì xử lý? | Theo định nghĩa hoạt động của nền tảng |
| Độ mới xác thực | Bằng chứng MFA được chấp nhận cũ đến đâu? | Mở phiên hoặc thao tác cần step-up |
| Hạn credential hoặc chứng thư | Khi nào credential được bên xác minh chấp nhận? | Xác thực và cơ chế thu hồi tương ứng |
| Hạn token hoặc cookie | Đối tượng kỹ thuật còn dùng được không? | Theo semantics của hệ thống nhận |

Ví dụ, bằng chứng MFA phải mới trong 5 phút lúc mở phiên không mặc nhiên có nghĩa phiên chỉ được chạy 5 phút. Ngược lại, session được phép 30 phút không làm một phê duyệt đã hết hạn trở lại hợp lệ.

Mỗi trường cần có ý nghĩa, mốc tính, điểm kiểm tra và hành vi hết hạn rõ ràng.

## 3. Xác định thời điểm đánh giá

### 3.1. Khi tạo yêu cầu và cấp grant

Ở bước tạo yêu cầu, hệ thống có thể kiểm tra cửa sổ được đề nghị có hợp lệ không. Đây là kiểm tra dữ liệu và policy ban đầu.

Khi cấp grant, cần đánh giá lại các điều kiện liên quan. Một yêu cầu hợp lệ lúc gửi chưa chắc còn hợp lệ khi người duyệt hoàn tất hoặc khi grant được tạo.

Ví dụ, quan hệ hỗ trợ của vendor có thể đã kết thúc trong thời gian yêu cầu chờ xử lý.

### 3.2. Khi mở phiên

Gateway hoặc điểm thực thi cần kiểm tra quyền mở phiên còn dùng được, đúng target và đúng thời điểm theo policy.

Cần định nghĩa “mở phiên” là sự kiện nào:

- Nhận yêu cầu từ client.
- Chấp nhận và tiêu thụ quyền mở.
- Bắt đầu xác thực tới target.
- Xác nhận kết nối tại đích.

Các mốc này có thể cách nhau do hàng đợi, lấy credential, mạng hoặc xác thực. Không dùng thời điểm client nhấn nút để chứng minh một mốc khác đã đạt trước hạn.

Nếu policy yêu cầu kết nối được xác nhận trước một deadline, kiến trúc phải có cách kiểm tra và xử lý phần đang mở dở. Nếu chỉ ràng buộc thời điểm tiêu thụ quyền, cần ghi đúng ý nghĩa đó.

### 3.3. Trong phiên và khi thực hiện tác vụ

Một số điều kiện chỉ áp dụng tại bước mở. Điều kiện khác phải duy trì trong suốt hoạt động, chẳng hạn kết thúc phiên không muộn hơn cuối cửa sổ công việc.

Thao tác nhạy cảm có thể cần đánh giá riêng nếu nền tảng hỗ trợ. Không tuyên bố kiểm tra thời gian cho từng lệnh chỉ từ một kiểm tra trước khi mở shell.

### 3.4. Khi reconnect, resume hoặc gia hạn

Kết nối lại không nhất thiết là một phiên nghiệp vụ mới. Nó có thể quay lại shell hoặc desktop đang tồn tại.

Cần xác định điều kiện nào kiểm tra lại và deadline nào được giữ. Không tự đặt lại bộ đếm thời lượng tuyệt đối chỉ vì TCP reconnect hoặc người dùng mở lại tab.

Gia hạn là thay đổi phạm vi thời gian và cần đi qua workflow tương ứng.

## 4. Biểu diễn khoảng thời gian một cách rõ ràng

### 4.1. Dùng quy ước ranh giới nhất quán

Một quy ước hữu ích là khoảng nửa mở:

~~~text
[start, end)

Được phép khi:
start <= now < end
~~~

Theo quy ước này:

- Đúng thời điểm start: đã vào cửa sổ.
- Ngay trước end: còn trong cửa sổ.
- Đúng thời điểm end: đã hết cửa sổ.

Quy ước phải nhất quán giữa policy engine, gateway, giao diện và log. Nếu một nơi dùng end bao gồm còn nơi khác loại trừ, người dùng có thể nhận kết quả khó giải thích ở ranh giới.

Độ phân giải thời gian cũng cần rõ. Dữ liệu chỉ lưu tới giây không thể chứng minh chính xác một hành động ở cấp mili giây.

### 4.2. Biểu diễn thời điểm cụ thể

Ví dụ một khoảng công việc giả định:

~~~text
start = 2026-12-03T21:00:00+07:00
end   = 2026-12-03T22:00:00+07:00
~~~

Dấu +07:00 chỉ offset của thời điểm đó. Khi xử lý, cần parse thành thời điểm theo cơ chế phù hợp, không so sánh các chuỗi hiển thị với offset khác nhau như thể chúng có cùng thứ tự thời gian.

Có thể lưu thời điểm chuẩn hóa và hiển thị theo múi giờ công việc. Cần giữ được thông tin đủ để đối chiếu ý định gốc của người phê duyệt.

### 4.3. Kiểm tra dữ liệu đầu vào

Không chấp nhận một cửa sổ mà:

- Thiếu múi giờ hoặc quy tắc diễn giải cần thiết.
- End không sau start.
- Vượt giới hạn tối đa theo policy.
- Nằm ngoài quan hệ, nhiệm vụ hoặc cửa sổ cấp quyền được phép.
- Có định dạng không được xử lý rõ.
- Được client tự thay đổi sau khi đã phê duyệt.

Một giá trị bị thiếu không nên mặc định thành vô hạn nếu policy không cho phép.

## 5. Múi giờ, lịch lặp lại và cửa sổ qua ngày

### 5.1. Chọn múi giờ có thẩm quyền

Một lịch “từ 09:00 đến 17:00” chưa đủ. Cần biết đó là giờ của đội vận hành, target, hợp đồng hay người yêu cầu.

Không để múi giờ trình duyệt quyết định quyền truy cập nếu policy dùng múi giờ khác. Người dùng đổi thiết lập máy không được tự thay cửa sổ được phép.

Với lịch theo giờ địa phương lặp lại, thường cần định danh vùng thời gian và quy tắc lịch. Với một khoảng thời gian tuyệt đối đã chốt, cần lưu các thời điểm cụ thể có thể đối chiếu.

### 5.2. Lịch lặp lại khác khoảng tuyệt đối

Một policy “ngày làm việc, 09:00–17:00 theo vùng thời gian của đội” phải giải quyết:

- Ngày trong tuần.
- Ngày nghỉ hoặc lịch ngoại lệ nếu có.
- Múi giờ áp dụng.
- Thay đổi quy tắc thời gian của vùng.
- Tập target và chủ thể được áp dụng.

Không dùng cron hoặc một job tạo rule như bằng chứng duy nhất rằng mọi hành động ngoài giờ bị chặn. Điểm thực thi vẫn cần kiểm tra policy hoặc trạng thái có thẩm quyền.

### 5.3. Cửa sổ qua nửa đêm

Một cửa sổ 22:00–02:00 thường cần được hiểu là kết thúc vào ngày tiếp theo. Nếu chỉ so “giờ hiện tại lớn hơn 22 và nhỏ hơn 02” thì logic sẽ sai.

Cần xây khoảng cụ thể theo ngày neo của cửa sổ:

~~~text
Ngày neo D:
  start = D lúc 22:00
  end   = D+1 lúc 02:00
~~~

Quy tắc ngày trong tuần cần nói rõ áp dụng theo ngày neo nào. Phần sau nửa đêm thuộc cửa sổ bắt đầu trước đó, không tự biến thành một lịch mới.

### 5.4. Vùng có thay đổi giờ theo mùa

Ở vùng có thay đổi offset theo mùa, một giờ địa phương có thể không tồn tại hoặc xuất hiện hai lần tại thời điểm chuyển đổi.

Policy cần xác định cách xử lý trường hợp mơ hồ hoặc không tồn tại, đồng thời kiểm chứng thư viện và nền tảng thực tế. Không giả định mọi ngày địa phương luôn có đúng 24 giờ.

Quy tắc vùng thời gian và cách mở rộng lịch cần được quản lý. Khi rule hoặc dữ liệu vùng thay đổi, phải đánh giá ảnh hưởng tới cửa sổ tương lai thay vì âm thầm đổi phạm vi đã duyệt.

## 6. Kết hợp nhiều điều kiện theo thời gian

### 6.1. Chỉ kết hợp các giới hạn có cùng ý nghĩa

Nếu một hành động cần đồng thời nằm trong nhiều khoảng, khoảng hợp lệ là phần giao của chúng.

Với những khoảng cùng áp dụng cho việc mở phiên:

~~~text
S = max(các thời điểm bắt đầu áp dụng cho mở phiên)
E = min(các thời điểm kết thúc áp dụng cho mở phiên)

Có thể mở khi:
S <= now < E

Nếu S >= E:
không tồn tại khoảng hợp lệ.
~~~

Các điều kiện không phải thời gian vẫn phải đạt.

Không đưa một giới hạn chỉ kiểm tra tại bước mở vào công thức kết thúc phiên đang chạy mà chưa có policy cho phép. Ví dụ, hạn tiêu thụ quyền mở không tự là deadline của phiên đã mở hợp lệ.

### 6.2. Thời lượng phiên và deadline tuyệt đối

Giả sử policy yêu cầu phiên không vượt cửa sổ công việc và grant có một mốc kết thúc hoạt động riêng:

~~~text
session_deadline =
  min(
    session_start + max_session_duration,
    work_window_end,
    grant_active_until
  )
~~~

Chỉ đưa vào công thức những giới hạn thực sự áp dụng trong lúc phiên hoạt động. Nếu một loại grant không có semantics grant_active_until như trên, không tự suy ra từ một trường hết hạn khác.

Nếu deadline không sau mốc bắt đầu hợp lệ, không mở phiên rồi lập tức coi đó là một phiên được cấp bình thường.

### 6.3. Idle timeout là giới hạn khác

Idle timeout thường phụ thuộc một mốc hoạt động được định nghĩa:

~~~text
idle_deadline = last_qualifying_activity + max_idle_duration
~~~

Cần xác định “hoạt động” gồm input của người dùng, output từ target, keepalive hay loại sự kiện nào. Tùy nền tảng, các loại đó có thể được xử lý khác nhau.

Một luồng output liên tục không nhất thiết thể hiện người dùng đang hiện diện. Ngược lại, một tác vụ dài ít output có thể vẫn hợp lệ. Policy cần cân nhắc công việc và khả năng quan sát thay vì mặc định một bộ đếm phù hợp mọi giao thức.

Dù có hoạt động, giới hạn tuyệt đối vẫn phải được áp dụng nếu policy yêu cầu.

## 7. Ví dụ phân biệt hạn mở với hạn chạy phiên

Giả sử một policy minh họa có:

~~~text
Cửa sổ công việc:       [21:00, 22:00)
Khoảng dùng quyền mở:  [21:10, 21:20)
Thời lượng phiên tối đa: 30 phút
MFA khi mở: không cũ hơn 5 phút
Múi giờ hiển thị: UTC+07:00
~~~

Trong ví dụ này, “khoảng dùng quyền mở” chỉ ràng buộc mốc mở được policy xác định; nó không trực tiếp là hạn kết thúc phiên.

### 7.1. Mở lúc 21:19:30

Nếu mọi điều kiện khác đạt và mốc mở được xác nhận lúc 21:19:30:

~~~text
Giới hạn theo thời lượng: 21:49:30
Giới hạn cửa sổ:         22:00:00
Deadline của phiên:      21:49:30
~~~

Đến 21:20, quyền mở không còn được dùng cho một lần mở mới. Phiên đã mở hợp lệ không tự phải kết thúc lúc đó theo semantics của ví dụ.

Nếu yêu cầu nghiệp vụ muốn mọi phiên đều dừng lúc 21:20, policy phải biểu diễn một giới hạn hoạt động tương ứng.

### 7.2. Yêu cầu mở đúng 21:20:00

Với quy ước khoảng nửa mở, yêu cầu không còn nằm trong khoảng dùng quyền mở. Việc credential còn hạn hoặc cửa sổ công việc chưa kết thúc không làm quyền mở hết hạn trở lại hợp lệ.

Nếu xử lý kết nối kéo dài qua ranh giới, cần áp dụng đúng mốc kiểm tra đã định, không lấy giờ client gửi để thay cho giờ gateway xác nhận.

### 7.3. Một yêu cầu khác được duyệt mở lúc 21:50

Giả sử có một quyền mở khác hợp lệ cho thời điểm đó:

~~~text
Giới hạn theo thời lượng: 22:20
Giới hạn cửa sổ:         22:00
Deadline của phiên:      22:00
~~~

Phiên chỉ có thể hoạt động tới cuối cửa sổ. Không cấp trọn 30 phút rồi kéo dài ngoài phạm vi công việc đã duyệt.

Đây là tình huống thay thế với quyền mở khác, không phải tái sử dụng một quyền một lần đã được tiêu thụ trước đó.

## 8. Kiến trúc quyết định và thực thi

~~~mermaid
flowchart LR
    U["Yêu cầu có danh tính, target và action"] --> P["Điểm đánh giá policy"]
    T["Nguồn thời gian được quản lý"] --> P
    A["Entitlement, phê duyệt và lịch"] --> P
    P --> G["Grant hoặc quyền mở có phạm vi"]
    G --> E["Gateway hoặc điểm thực thi"]
    T --> E
    E --> R["Target và quyền hiệu lực"]
    E --> L["Bằng chứng phiên và hết hạn"]
    R --> L
    S["Timer và cơ chế đối chiếu"] --> E
~~~

Các vai trò có thể nằm trong nhiều thành phần:

- **Điểm đánh giá policy** xác định điều kiện và kết quả tại một thời điểm.
- **Grant hoặc quyền mở** mang phạm vi đã được cấp.
- **Điểm thực thi** kiểm tra quyền và áp dụng hành động.
- **Timer** hỗ trợ xử lý đúng deadline.
- **Cơ chế đối chiếu** phát hiện phần đã trễ hoặc bỏ lỡ.
- **Target** thực thi quyền và có thể có vòng đời phiên riêng.

Một job đến giờ xóa grant là cơ chế hỗ trợ, không nên là hàng rào duy nhất cho việc ngăn dùng grant quá hạn. Nếu job bị chậm, điểm thực thi vẫn cần hiểu thời hạn theo thiết kế.

Tương tự, token có trường thời hạn không giúp ích nếu bên nhận không kiểm tra hoặc dùng semantics không đúng.

## 9. Nguồn thời gian và độ lệch đồng hồ

### 9.1. Không tin thời gian do client tự khai

Client có thể gửi thời điểm yêu cầu để hỗ trợ giao diện và đối chiếu, nhưng quyền phải được quyết định bằng nguồn thời gian có thẩm quyền theo kiến trúc.

Người dùng đổi đồng hồ laptop không được tự làm token hoặc grant hợp lệ lâu hơn.

### 9.2. Quản lý chênh lệch giữa các thành phần

Policy engine, gateway, nguồn xác thực và target có thể dùng các đồng hồ khác nhau. Cần quản lý đồng bộ, đo lệch và xác định hành vi khi không tin cậy thời gian.

Nếu cho phép một mức lệch, phải hiểu nó tác động tới cả ranh giới bắt đầu và kết thúc. Không âm thầm cộng thêm khoảng “ân hạn” vào mọi deadline.

Với cửa sổ nghiêm ngặt, việc mở rộng ranh giới có thể trái mục tiêu. Có thể cần một cách xử lý bảo thủ hoặc từ chối trong tình huống không xác minh được, theo policy đã xác định.

### 9.3. Thời điểm lịch và đo khoảng thời gian

Thời điểm tuyệt đối cần để phối hợp cửa sổ giữa hệ thống. Đồng hồ đơn điệu có thể hỗ trợ đo thời lượng trong một tiến trình mà không bị một số thay đổi của đồng hồ lịch làm sai bộ đếm.

Tuy nhiên, giá trị đơn điệu của một tiến trình không tự dùng được trên node khác hoặc sau restart. Cần thiết kế cách khôi phục deadline bền vững và đối chiếu với thời gian được quản lý.

Không để chỉnh lùi đồng hồ hoặc failover vô tình kéo dài một phiên vô hạn.

## 10. Grant, token và credential

### 10.1. Gắn thời gian với đúng phạm vi

Quyền mở phiên cần ràng buộc các dữ kiện liên quan, chẳng hạn:

~~~text
Chủ thể
Target và account hoặc role
Action được cấp
Thời điểm bắt đầu và hết hiệu lực
Số lần sử dụng nếu có
Yêu cầu hoặc phê duyệt liên quan
Phiên bản policy hoặc điều kiện cần đối chiếu
~~~

Bên nhận cần xác minh tính hợp lệ theo cơ chế của hệ thống. Client không được tự đổi timestamp hoặc target để mở rộng quyền.

### 10.2. Hạn token khác hạn phiên

Token hết hạn có thể ngăn yêu cầu mới nếu bên nhận kiểm tra đúng. Phiên đã hình thành có thể có trạng thái và deadline riêng.

Nếu mục tiêu là dừng phiên tại một thời điểm, phải có cơ chế áp dụng deadline đó ở lớp phiên hoặc target phù hợp. Không chỉ gắn thời hạn vào token rồi suy ra mọi hoạt động đã dừng.

### 10.3. Hạn credential khác hạn grant

Một grant PAM hết hạn chưa làm mật khẩu tĩnh tự đổi. Một chứng thư SSH hết hạn thường ảnh hưởng xác thực mới theo kiểm tra của server, không tự bảo đảm shell hiện hữu bị kết thúc.

Nếu người dùng đã nhận secret, việc hết checkout không tự lấy lại bản sao. Cần xử lý vòng đời credential, nơi chấp nhận và đường dùng ngoài PAM theo thiết kế.

Thời gian ngắn có thể giảm thời gian phơi lộ của một khả năng truy cập, nhưng không thay kiểm soát phạm vi hoặc kế hoạch thu hồi.

## 11. Policy minh họa

~~~yaml
# Mã giả mô tả ý định, không phải cấu hình của một sản phẩm.
policy:
  id: production-diagnostics-time-example
  subject_group: approved-diagnostics-engineers
  target_group: approved-production-targets
  action: open_privileged_session

  work_window:
    start_inclusive: "2026-12-03T21:00:00+07:00"
    end_exclusive: "2026-12-03T22:00:00+07:00"
    applies_while_session_active: true

  launch_window:
    start_inclusive: "2026-12-03T21:10:00+07:00"
    end_exclusive: "2026-12-03T21:20:00+07:00"
    evaluation_event: verified_session_open
    permitted_uses: 1

  authentication:
    max_evidence_age_at_open_seconds: 300
    accepted_profile: verified_privileged_profile

  session:
    max_duration_seconds: 1800
    reset_absolute_duration_on_resume: false
    check_current_policy_on_resume: true
    deadline_action: terminate_under_supported_design

  evidence:
    record_time_source_and_decision: true
    record_deadline_and_action_results: true
~~~

Các con số chỉ là ví dụ. Tên verified_session_open cần được ánh xạ thành một sự kiện cụ thể mà hệ thống thực sự xác nhận được.

Nếu sản phẩm chỉ kiểm tra khi nhận yêu cầu, không thể tuyên bố đã thực thi điều kiện “xác nhận mở trước hạn” mà không có thiết kế bổ sung. Nếu khả năng kết thúc phiên ở đích có giới hạn, cần ghi đúng phạm vi của deadline_action.

Các điều kiện danh tính, quyền, phê duyệt, target và credential vẫn cần được đánh giá ngoài phần thời gian trong ví dụ.

## 12. Gia hạn và thay đổi policy

### 12.1. Gia hạn là thay đổi phạm vi

Một người dùng đang làm việc có thể cần thêm thời gian, nhưng yêu cầu đó phải được đánh giá theo workflow đã định.

Cần xác định:

- Ai được đề nghị và ai có thẩm quyền chấp thuận.
- Có thay target, role hoặc loại tác vụ không.
- Điều kiện MFA và phê duyệt có cần cập nhật không.
- Deadline mới áp dụng cho phiên nào.
- Việc gia hạn đã được thực thi và ghi nhận chưa.

Không để client gửi keepalive hoặc reconnect trở thành cách gia hạn ngầm.

### 12.2. Không sửa lịch sử phê duyệt

Nếu thời gian đã được phê duyệt thay đổi, cần lưu phiên bản hoặc lịch sử tương đương. Người kiểm tra phải biết cửa sổ nào được cấp ban đầu và ai cho phép thay đổi.

Không sửa một timestamp cũ rồi làm mất dấu việc phiên đã từng vượt phạm vi trước khi được gia hạn.

### 12.3. Policy chặt hơn hoặc rộng hơn

Khi policy thay đổi, cần có quy tắc cho grant đã phát hành và phiên đang mở.

Một thay đổi mở rộng không nên tự kéo dài mọi grant cũ nếu không có cơ chế cho phép. Một thay đổi thu hẹp cũng không tự tác động tức thời tới mọi target nếu chưa có luồng thực thi.

Cần xác định thời điểm có hiệu lực, điểm kiểm tra lại, độ trễ và cách xử lý phần chưa xác nhận.

### 12.4. Đồng thời giữa hết hạn và gia hạn

Nếu timer đang kết thúc phiên trong lúc một quyết định gia hạn được xử lý, cần cơ chế giữ trạng thái nhất quán.

Có thể cần phiên bản grant hoặc cập nhật có điều kiện theo khả năng hệ thống. Một callback cũ không được tự đóng phiên bằng deadline đã được thay hợp lệ; ngược lại, một phản hồi gia hạn đến muộn không tự mở lại phiên đã thu hồi theo một quyết định khác.

Không dùng cách “lần ghi cuối thắng” nếu nó bỏ qua thẩm quyền hoặc trạng thái hiện tại.

## 13. Cửa sổ cấm, ngoại lệ và tình huống khẩn cấp

Lịch cho phép có thể giao với thời gian cấm thay đổi, bảo trì khác hoặc một lệnh hạn chế đang hiệu lực.

Policy cần định nghĩa cách kết hợp. Ví dụ, một tổ chức có thể quy định cửa sổ cấm chặn hoạt động thường lệ, còn ngoại lệ cần thẩm quyền và phạm vi riêng. Không mặc định mọi policy engine đều có cùng thứ tự ưu tiên.

Một ngoại lệ theo thời gian cần có:

- Lý do và công việc.
- Chủ thể và target.
- Role hoặc tác vụ.
- Thời điểm bắt đầu và kết thúc.
- Người có thẩm quyền.
- Các điều kiện bổ sung và bằng chứng.
- Cách đóng quyền sau sử dụng.

Nếu dùng break-glass, ghi đúng đây là một luồng khẩn cấp theo policy. Không sửa lịch thông thường để mọi hoạt động cùng được mở rộng, rồi quên khôi phục.

Hết thời gian ngoại lệ cần có cả kiểm tra tại điểm sử dụng và xử lý phần quyền đã cấp, tùy semantics của hệ thống.

## 14. Thực thi hết hạn trong hệ thống phân tán

### 14.1. Timer có thể chậm hoặc bị mất

Restart, failover, hàng đợi hoặc gián đoạn mạng có thể làm một tác vụ hết hạn xử lý muộn.

Cần có khả năng khôi phục deadline đã lưu và đối chiếu các phiên quá hạn. Không tính lại “30 phút từ bây giờ” sau restart cho một phiên đã chạy từ trước.

Điểm cấp và mở phiên cũng cần kiểm tra thời hạn để một scheduler chậm không tiếp tục cho phép quyền mới trái policy.

### 14.2. Hết hạn khi control plane mất kết nối

Gateway hoặc target có thể còn hoạt động khi control plane không tới được. Cần xác định:

- Deadline và điều kiện nào đã được chuyển tới điểm thực thi.
- Điểm đó có thể tự áp dụng không.
- Có được mở phiên mới từ dữ liệu đã cache không.
- Trạng thái revoke được tiếp nhận thế nào sau khi kết nối lại.
- Bằng chứng được giữ và chuyển tiếp ra sao.

Không mặc định mọi phiên đều dừng hoặc mọi phiên đều được tiếp tục vô hạn.

### 14.3. Kết quả hết hạn theo từng lớp

Một báo cáo có thể phân biệt:

~~~text
Grant: hết hiệu lực, không cấp yêu cầu mới.
Quyền mở phiên: không còn sử dụng được.
Gateway: đã chặn tương tác và thực hiện kết thúc.
Target: đã xác nhận logoff hoặc còn chờ xác nhận.
Tác vụ nền: trạng thái riêng theo phạm vi quan sát.
Credential: xử lý theo vòng đời tương ứng.
~~~

Đóng một luồng mạng không đảo ngược thay đổi đã xảy ra. Nó cũng có thể chưa dừng một tác vụ đã tách khỏi phiên.

Nếu mục tiêu cần kết thúc ở đích, phải có cách thực thi và xác nhận phù hợp. Khi chưa có, ghi PENDING hoặc UNKNOWN thay vì gộp vào PASS.

## 15. Bằng chứng và xử lý sự cố thời gian

Mỗi quyết định quan trọng nên có thể đối chiếu:

- Thời điểm đánh giá và nguồn thời gian.
- Múi giờ hoặc cách chuẩn hóa.
- Policy và phiên bản áp dụng.
- Các khoảng hoặc deadline liên quan.
- Chủ thể, target và action.
- Kết quả cùng lý do.
- Deadline thực tế của grant hoặc phiên.
- Hành động hết hạn và thời điểm được xác nhận.
- Thay đổi, gia hạn và phần còn chưa rõ.

Không cần lưu secret hoặc token đầy đủ để chứng minh điều kiện thời gian. Dùng ID có thể liên kết các nguồn dữ liệu trong phạm vi được kiểm soát.

Khi có tranh chấp “người dùng vào trước giờ hết hạn”, cần phân biệt thời điểm nhấn nút, nhận yêu cầu, tiêu thụ quyền, xác thực tới target và xác nhận mở. Đối chiếu đúng mốc mà policy quy định.

Nếu clock hoặc timezone bị cấu hình sai, không chỉ sửa giờ rồi bỏ lịch sử. Cần đánh giá quyết định nào có thể bị ảnh hưởng, giữ dữ liệu cần thiết và xác định phần phải xử lý lại.

## 16. Kiểm chứng các ranh giới và tình huống lỗi

| Tình huống | Kết quả cần xác nhận |
|---|---|
| Ngay trước start | Không dùng quyền nếu chưa tới mốc cho phép |
| Đúng start | Được đánh giá trong cửa sổ theo quy ước |
| Ngay trước end | Được đánh giá theo mốc và độ phân giải đã định |
| Đúng end | Không còn trong khoảng nửa mở |
| Client đổi đồng hồ hoặc múi giờ | Không thay quyền theo nguồn thời gian có thẩm quyền |
| Cùng thời điểm hiển thị bằng offset khác | Kết quả nhất quán sau chuẩn hóa |
| Cửa sổ qua nửa đêm | Đúng ngày neo và ngày kết thúc |
| Giờ địa phương mơ hồ hoặc không tồn tại | Hành vi theo policy và thư viện được kiểm chứng |
| Yêu cầu chờ xử lý qua deadline | Không dùng giờ gửi thay mốc đánh giá thực tế |
| MFA cũ nhưng token mới | Kiểm tra đúng độ mới xác thực |
| Hạn mở đã qua nhưng phiên mở hợp lệ còn thời lượng | Xử lý đúng semantics của hai giới hạn |
| Mở muộn gần cuối cửa sổ | Không vượt deadline hoạt động |
| Reconnect hoặc failover | Không tự đặt lại giới hạn tuyệt đối |
| Scheduler xử lý chậm | Không tiếp tục cấp mới trái thời hạn |
| Restart giữa phiên | Khôi phục deadline cũ, không cấp thêm thời gian ngầm |
| Gia hạn đồng thời timer hết hạn | Kết quả nhất quán theo phiên bản và thẩm quyền |
| Credential hết hạn nhưng phiên còn hoạt động | Không suy rằng đã dừng mọi hoạt động |
| Kết thúc gateway nhưng target chưa rõ | Giữ trạng thái riêng cho phần chưa xác nhận |

Các kiểm chứng cần dùng thời gian, identity và tài nguyên trong phạm vi được phép. Có thể dùng mô phỏng hoặc môi trường thử nghiệm để kiểm tra ranh giới; không chỉnh đồng hồ production chỉ để tái hiện một trường hợp.

Chỉ số có thể theo dõi gồm quyết định ngoài cửa sổ, độ trễ từ deadline tới kết quả thực thi, phiên bị kéo dài sau reconnect, grant quá hạn còn được dùng và hành động hết hạn còn chờ xác nhận.

Số grant có timestamp không đủ để chứng minh policy hiệu quả. Cần kiểm chứng hành vi tại điểm sử dụng và kết quả khi hết thời gian.

## 17. Bài tập áp dụng

Một vendor được phê duyệt công việc từ 22:00 đến 02:00 hôm sau. Quyền mở phiên chỉ dùng trong 10 phút đầu; phiên tối đa 60 phút. Hệ thống chỉ kiểm tra thời gian lúc gửi yêu cầu. Khi reconnect, gateway đặt lại bộ đếm 60 phút. Một job chạy định kỳ xóa grant hết hạn nhưng không theo dõi phiên tại target.

Hãy xác định:

1. Múi giờ và ngày neo cần được ghi thế nào?
2. Hạn mở, cửa sổ công việc và thời lượng phiên có ý nghĩa khác nhau ra sao?
3. Một yêu cầu chờ lâu nên được đánh giá lại tại mốc nào?
4. Reconnect có được đặt lại deadline không?
5. Nếu phiên bắt đầu gần 02:00, thời điểm kết thúc phải tính thế nào?
6. Xóa grant đã và chưa chứng minh điều gì?
7. Cần cơ chế nào khi scheduler, gateway hoặc control plane gián đoạn?
8. Bằng chứng nào giúp đối chiếu một quyết định tại ranh giới hết hạn?

Một thiết kế có thể kiểm tra được phải nêu rõ khoảng thời gian, mốc đánh giá, nguồn thời gian, lớp thực thi và kết quả hết hạn. Khi các khái niệm này được tách rõ, policy mới giới hạn đúng cả khả năng nhận quyền và thời gian sử dụng đặc quyền theo ý định.
