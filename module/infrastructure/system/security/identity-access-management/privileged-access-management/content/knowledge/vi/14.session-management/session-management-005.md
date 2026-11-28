# Idle timeout trong quản lý phiên đặc quyền

## 1. Idle timeout là gì?

Trong quản lý truy cập đặc quyền (Privileged Access Management — PAM), **idle timeout** là giới hạn thời gian một phiên được phép không có loại hoạt động được chính sách công nhận trước khi hệ thống áp dụng hành động kiểm soát.

Hành động đó có thể là khóa tương tác, yêu cầu xác thực lại, ngắt kết nối hoặc kết thúc phiên trong phạm vi mà nền tảng hỗ trợ. Cần định nghĩa rõ hành động, không chỉ cấu hình một số phút.

Ví dụ, một quản trị viên mở phiên qua gateway rồi rời máy. Nếu phiên còn hoạt động không giới hạn, người tiếp cận được môi trường client có thể tiếp tục sử dụng quyền đã cấp. Idle timeout giúp giảm khoảng phơi lộ của phiên bị bỏ quên.

Tuy nhiên, cơ chế này có giới hạn:

- Không chứng minh người dùng đã rời máy chỉ vì không có input.
- Không ngăn một chủ thể đang chủ động tương tác duy trì phiên.
- Không tự thu hồi mọi credential, grant hoặc đường truy cập khác.
- Không bảo đảm tác vụ đã được gửi tới đích ngừng chạy.

Giá trị của idle timeout nằm ở định nghĩa hoạt động, nơi thực thi, hành động khi hết hạn và bằng chứng kết quả.

## 2. Phân biệt những giới hạn thời gian liên quan

| Giới hạn | Bắt đầu hoặc được tính theo | Mục đích |
|---|---|---|
| Idle timeout | Lần hoạt động hợp lệ gần nhất | Xử lý phiên không có tương tác được công nhận |
| Absolute session lifetime | Mốc bắt đầu hoặc mốc giới hạn tuyệt đối | Không để phiên kéo dài vô hạn nhờ liên tục hoạt động |
| Cửa sổ phê duyệt | Quyết định cho phép công việc | Giới hạn lúc và khoảng truy cập được duyệt |
| Thời hạn grant JIT | Vòng đời quyền tạm | Giới hạn quyền được gán |
| Credential hoặc token TTL | Cơ chế xác thực tương ứng | Giới hạn hiệu lực credential theo khả năng đích |
| Network timeout | Trạng thái kết nối hoặc luồng mạng | Phát hiện hoặc xử lý kết nối không đáp ứng |
| Lock-screen timeout | Hoạt động tại môi trường người dùng | Khóa giao diện theo cơ chế của môi trường |
| Checkout duration | Lượt cấp hoặc sử dụng credential tại PAM | Điều phối quyền sử dụng credential |

Một keepalive có thể giúp kết nối mạng tồn tại nhưng không nhất thiết là hoạt động người dùng. Một token còn hiệu lực cũng không tự cho phép mở lại phiên đã hết cửa sổ phê duyệt.

Đổi mật khẩu không mặc định kết thúc phiên đã xác thực. Ngược lại, ngắt phiên không làm người dùng quên mật khẩu đã biết.

Khi thiết kế PAM, cần biết những giới hạn nào áp dụng đồng thời và lớp nào thực thi từng giới hạn.

## 3. Một người dùng có thể có nhiều lớp phiên

### 3.1. Các lớp thường gặp

~~~text
Phiên đăng nhập vào giao diện PAM
  → yêu cầu truy cập và quyết định
  → phiên tại gateway
  → kết nối tới hệ thống đích
  → phiên đăng nhập hoặc tiến trình tại đích.
~~~

Ngoài ra có thể có phiên SSO, cookie, token bàn giao, kênh WebSocket hoặc kết nối API. Không phải mọi lớp có cùng vòng đời hay cùng khái niệm idle.

### 3.2. Hết hạn ở một lớp không tự hết hạn ở lớp khác

| Sự kiện | Điều có thể đã xảy ra | Điều cần xác minh thêm |
|---|---|---|
| Giao diện PAM tự đăng xuất | Phiên web không còn được dùng như trước | Phiên gateway đã mở có bị ảnh hưởng không |
| Client đóng cửa sổ | Client ngừng tương tác qua cửa sổ đó | Gateway và đích đã nhận kết thúc chưa |
| Gateway đóng kênh tới client | Một đường truyền đã bị chặn hoặc ngắt | Kết nối tới đích và phiên đích còn không |
| Đích khóa giao diện | Tương tác theo giao diện bị khóa | Phiên, quyền và tác vụ nền còn tồn tại không |
| Token bàn giao hết hạn | Không dùng token đó theo điều kiện cũ | Phiên được mở trước đó còn hoạt động không |
| Grant JIT được gỡ | Quan hệ cấp quyền thay đổi | Token hoặc phiên đã có quyền còn tiếp diễn không |

Một thông báo “session ended” cần nói rõ phạm vi mà hệ thống thực sự xác nhận.

### 3.3. Xác định đơn vị áp dụng

Idle timeout có thể áp dụng theo từng phiên, từng kênh hoặc một tập phiên theo thiết kế.

Nếu người dùng tương tác ở phiên A, không nên mặc định mọi phiên B và C cũng được làm mới. Một trang dashboard liên tục polling không nên tự giữ mọi phiên đặc quyền sống nếu policy không cho phép điều đó.

Phạm vi timer phải được định nghĩa rõ trong policy và bằng chứng.

## 4. Kiến trúc tham chiếu và nơi thực thi

~~~mermaid
flowchart LR
    U["Người dùng"] -->|Tương tác theo giao thức| C["Client hoặc trình duyệt"]
    C --> G["Gateway PAM"]
    P["Policy phiên và quyết định truy cập"] --> G
    G -->|Kênh quản trị| T["Hệ thống đích"]
    G --> S["Trạng thái phiên và deadline"]
    G -->|Sự kiện an toàn| A["Audit và giám sát"]
    S --> E["Điều phối hết hạn"]
    E -->|Chặn, khóa hoặc kết thúc theo policy| G
    E -.->|Hành động tại đích nếu được hỗ trợ| T
    T --> A
~~~

Sơ đồ là mô hình logic, không phải yêu cầu mỗi khối là một máy chủ riêng.

### 4.1. Timer trên client chưa đủ

Client có thể bị đóng, mất kết nối hoặc không thực hiện mã giao diện. Người dùng hoặc phần mềm cũng có thể thay đổi dữ liệu do client gửi.

Cần một điểm thực thi có thẩm quyền phù hợp với kiến trúc. Client có thể hiển thị cảnh báo và hỗ trợ trải nghiệm, nhưng không nên là nơi duy nhất quyết định phiên còn được phép hoạt động.

### 4.2. Gateway cần áp dụng quyết định thực tế

Nếu policy đã xác định phiên hết hạn, hệ thống phải xử lý việc nhận input, tiếp tục kênh hoặc kết thúc theo thiết kế.

Không chỉ đổi màu giao diện rồi để các kênh tương tác tiếp tục không giới hạn.

Một tác vụ cleanup chạy chậm có thể làm hành động kết thúc hoàn tất sau deadline. Phải phân biệt lúc quyết định hết hạn, lúc chặn hoạt động mới và lúc có bằng chứng kết thúc.

### 4.3. Cơ chế native tại đích là một lớp riêng

Hệ thống đích có thể có idle timeout của chính nó. Đây là một lớp bổ sung, nhưng ngữ nghĩa hoạt động và hành động có thể khác gateway.

Không mặc định các timer có cùng định nghĩa hoặc một giá trị nhỏ nhất đơn giản đủ mô tả toàn bộ hành vi. Cần xem từng lớp đo gì và làm gì.

## 5. Thế nào là hoạt động được công nhận?

### 5.1. Không có một định nghĩa chung cho mọi giao thức

Một policy có thể công nhận input tương tác được gateway tiếp nhận, một thao tác ứng dụng đã xác thực hoặc loại sự kiện khác mà nền tảng quan sát được.

Cần định nghĩa cụ thể:

- Sự kiện nào được tính.
- Nguồn sự kiện và cách ràng buộc với phiên.
- Thời điểm sự kiện được chấp nhận.
- Sự kiện nào bị loại trừ.
- Cách xử lý khi không xác định được chất lượng dữ liệu.

### 5.2. Bảng sự kiện minh họa

| Sự kiện | Cách xem xét trong policy |
|---|---|
| Input tương tác hợp lệ vào phiên | Có thể đặt lại timer nếu policy chọn loại này |
| Hoạt động chuột hoặc bàn phím được giao thức hỗ trợ | Cần định nghĩa rõ loại và nơi quan sát |
| Output liên tục từ tác vụ | Có thể là hoạt động hệ thống, chưa chứng minh người dùng hiện diện |
| Transport keepalive | Thường phục vụ duy trì kênh; không tự là tương tác người dùng |
| Heartbeat của agent | Cho biết liveness của thành phần, không tự làm mới idle |
| Ghi hình hoặc xuất recording | Hoạt động quan sát, không phải input của chủ thể phiên |
| Polling dashboard | Thuộc giao diện hoặc dịch vụ giám sát, không tự là hoạt động phiên đích |
| Mở một phiên khác | Chưa chứng minh phiên đang xét có tương tác |
| Thao tác đọc màn hình không tạo input | Có thể không quan sát được bằng cơ chế input |

Bảng nêu các điểm phải quyết định, không mô tả mặc định của một sản phẩm cụ thể.

### 5.3. “Hoạt động hợp lệ” không chứng minh con người hiện diện

Một sự kiện có thể đến từ phần mềm hoặc tự động hóa trên client. Gateway tiếp nhận input theo giao thức chưa đủ để chứng minh một người đang làm việc có chủ đích.

Idle timeout không phải phép kiểm tra sự hiện diện tuyệt đối. Cần phối hợp với giới hạn thời gian tuyệt đối, đánh giá quyền, xác thực lại và các lớp giám sát phù hợp.

### 5.4. Sự kiện phải thuộc đúng phiên

Không nhận một giá trị last_active do client tùy ý khai báo rồi dùng làm thẩm quyền kéo dài phiên.

Cần ràng buộc sự kiện với session ID, danh tính, kênh và trạng thái hiện tại. Input tới sau khi phiên đã hết hạn không được tự biến thành quyền mở lại nếu policy yêu cầu tái xác thực.

## 6. Chọn policy theo rủi ro và công việc

Một policy cần gồm nhiều hơn idle_duration:

~~~text
Loại chủ thể và role
  → target và môi trường
  → giao thức hoặc đường truy cập
  → định nghĩa activity
  → khoảng idle
  → cảnh báo
  → hành động khi hết hạn
  → điều kiện resume
  → giới hạn tuyệt đối
  → bằng chứng và xử lý lỗi.
~~~

### 6.1. Các loại công việc có đặc điểm khác nhau

Một phiên quản trị production, phiên chẩn đoán chỉ đọc và tác vụ tự động hóa không nhất thiết cần cùng policy.

Cần xem ảnh hưởng khi một phiên bị bỏ quên, quyền hiệu lực, khả năng kết thúc an toàn và cách công việc thực tế tạo tương tác.

Không chọn một con số duy nhất cho toàn bộ hạ tầng mà chưa hiểu ngữ nghĩa và ảnh hưởng.

### 6.2. Giá trị thời gian là quyết định của thiết kế

Ví dụ trong bài có thể dùng khoảng idle 10 phút và cảnh báo trước một phút để minh họa tính deadline. Đây không phải khuyến nghị mặc định cho mọi tổ chức.

Giá trị thật cần được xác định theo nhu cầu, khả năng nền tảng và chính sách đang áp dụng.

### 6.3. Idle timeout không thay least privilege

Một phiên tồn tại ngắn nhưng toàn quyền vẫn có thể gây tác động lớn. Role và năng lực tại đích cần được giới hạn đúng nhu cầu.

JIT giới hạn thời gian cấp quyền hoặc truy cập; JEA giới hạn hành động. Idle timeout hỗ trợ quản lý vòng đời phiên nhưng không tự tạo cả hai loại giới hạn đó.

## 7. Tính deadline và xử lý ranh giới

### 7.1. Mô hình thời gian tham chiếu

~~~text
idle_deadline = last_accepted_activity + idle_window

effective_deadline = mốc sớm nhất trong:
  idle_deadline
  absolute_session_deadline
  approved_access_window_end
  các giới hạn thời gian bắt buộc khác của thiết kế.
~~~

Công thức là mô hình logic khi các mốc đó áp dụng cho cùng quyền tiếp tục phiên. Những giới hạn ở hệ thống khác vẫn cần cơ chế thực thi tương ứng.

### 7.2. Nguồn thời gian và đo thời lượng

Cần dùng nguồn thời gian có thẩm quyền cho quyết định. Không để client tự gia hạn bằng việc gửi timestamp trong tương lai.

Trong một tiến trình, cơ chế đo thời lượng phù hợp có thể tránh ảnh hưởng từ việc đồng hồ lịch bị điều chỉnh. Log vẫn cần thời điểm có thể tương quan.

Tuy nhiên, mốc monotonic cục bộ không thể tùy tiện mang sang máy khác sau failover. Trạng thái bền vững và cách tính lại phải được thiết kế cho môi trường phân tán.

### 7.3. Input ở sát deadline

Cần quy định thứ tự xử lý và ranh giới. Một mô hình có thể coi thời điểm bằng hoặc sau deadline là đã hết hạn.

Nếu sự kiện được tiếp nhận trước deadline và đáp ứng policy, timer có thể được đặt lại. Nếu phiên đã hết hạn, sự kiện đến muộn không tự mở lại quyền.

Không để hai thành phần xử lý khác nhau khiến cùng một input vừa gia hạn vừa kết thúc phiên mà không có quy tắc thống nhất.

### 7.4. Không đặt lại giới hạn tuyệt đối theo mọi input

Input hợp lệ có thể làm mới idle_deadline, nhưng không nên tự kéo dài absolute_session_deadline hoặc cửa sổ phê duyệt.

Nếu cần gia hạn thẩm quyền truy cập, phải có cơ chế và quyết định tương ứng. Không dùng timer idle để né giới hạn của quyền tạm.

## 8. Cảnh báo trước khi hết hạn

### 8.1. Cảnh báo hỗ trợ người dùng, không thay việc thực thi

Một cảnh báo có thể cho biết:

~~~text
Phiên sẽ kết thúc sau khoảng một phút nếu không có tương tác
được chính sách công nhận. Nếu cần tiếp tục, hãy thực hiện
bước xác nhận hoặc xác thực theo yêu cầu.
~~~

Nội dung cần phản ánh đúng hành động thật. Nếu policy chỉ khóa tương tác rồi yêu cầu xác thực lại, không nên nói mọi tác vụ tại đích sẽ bị dừng.

Nếu cảnh báo không hiển thị vì client mất kết nối, điểm thực thi vẫn cần xử lý deadline theo policy.

### 8.2. Cách tính thời điểm cảnh báo

Một mô hình có thể dùng:

~~~text
warning_at = effective_deadline - warning_lead_time
~~~

Cấu hình phải hợp lệ cho loại phiên. Nếu có nhiều giới hạn cùng áp dụng, cảnh báo nên phản ánh giới hạn thực sự sẽ tới trước.

Không hiển thị một bộ đếm ước lượng trên client như thể đó là nguồn thời gian có thẩm quyền. Quyết định cuối cùng vẫn thuộc điểm thực thi.

### 8.3. Nút tiếp tục không phải quyền gia hạn vô hạn

Cần quy định thao tác xác nhận có được tính là activity không, có yêu cầu step-up không và chỉ áp dụng trước hay sau deadline.

Một thao tác trước deadline có thể làm mới idle nếu policy cho phép. Nó không tự kéo dài cửa sổ phê duyệt hay giới hạn tuyệt đối.

Sau khi hết hạn, cần đi theo luồng resume hoặc mở phiên mới, không chỉ đặt last_activity về thời điểm hiện tại.

### 8.4. Trải nghiệm phải khớp trạng thái

Nếu hệ thống đang gửi yêu cầu kết thúc và chưa có xác nhận từ đích, có thể hiển thị trạng thái đang kết thúc trong phạm vi người dùng được phép xem.

Không báo đã kết thúc hoàn toàn khi chỉ mới gửi yêu cầu. Cũng không cho người dùng tiếp tục nhập qua một giao diện tưởng đã khóa nhưng kênh dữ liệu vẫn mở.

## 9. Khóa, ngắt kết nối và kết thúc khác nhau

| Hành động | Tác dụng có thể có | Điều không tự được bảo đảm |
|---|---|---|
| Khóa giao diện client | Ngăn tương tác qua giao diện đó | Kênh khác hoặc phiên tại đích đã kết thúc |
| Chặn input tại gateway | Không chuyển thêm tương tác theo đường bị chặn | Tiến trình đã chạy tại đích dừng |
| Yêu cầu xác thực lại | Kiểm tra lại điều kiện chủ thể | Quyền hoặc phiên cũ tự bị thu hồi |
| Ngắt kết nối | Đóng một hoặc nhiều kênh truyền | Phiên đăng nhập tại đích đã bị logoff |
| Kết thúc phiên tại đích | Xử lý phiên cụ thể bằng cơ chế đích | Không còn tiến trình hoặc quyền ngoài phạm vi phiên đó |
| Thu hồi grant hoặc credential | Thay đổi quyền hoặc khả năng xác thực | Mọi phiên đã có quyền đều mất hiệu lực ngay |

Hành vi chính xác phụ thuộc nền tảng và giao thức. Runbook cần xác minh thay vì dựa vào tên nút trong giao diện.

### 9.1. Các trạng thái nên tách

Một mô hình logic:

~~~text
ACTIVE
  → WARNING
  → EXPIRED_BY_POLICY
  → INTERACTION_BLOCKED
  → TERMINATION_REQUESTED
  → TERMINATED_FOR_CONFIRMED_SCOPE.
~~~

Một nhánh khác có thể là:

~~~text
EXPIRED_BY_POLICY
  → LOCKED_OR_SUSPENDED_FOR_INTERACTION
  → REAUTHENTICATION_REQUIRED
  → tiếp tục nếu được phép, hoặc kết thúc.
~~~

Các nhãn chỉ minh họa. Không phải mọi hệ thống có tất cả trạng thái hoặc cùng thứ tự.

### 9.2. Expired là quyết định, terminated là kết quả thực thi

Khi deadline tới, hệ thống có thể đã chặn input mới nhưng vẫn đang đóng kết nối hoặc chờ xác nhận từ đích.

Cần ghi riêng thời điểm quyết định và các kết quả. Nếu một bước lỗi, giữ trạng thái pending hoặc unknown phù hợp.

Không dùng thời điểm gửi API làm thời điểm chắc chắn phiên đích đã chấm dứt.

### 9.3. Cleanup có thể cần nhiều lớp

Có thể cần đóng kênh client, kênh tới đích, phiên liên quan và xử lý grant hoặc checkout theo policy.

Idle timeout của một phiên không mặc định rotation mọi credential hoặc thu hồi toàn bộ quyền của tài khoản. Nếu có yêu cầu này, cần tác vụ và bằng chứng riêng.

## 10. Mở lại hoặc tiếp tục phiên sau timeout

### 10.1. Không để reconnect tự cấp lại quyền

Một client kết nối lại có thể mang session ID, cookie hoặc token từ trước. Những dữ liệu đó không tự chứng minh chủ thể vẫn đủ điều kiện.

Cần kiểm tra trạng thái phiên, deadline, danh tính, quyền hiện tại và điều kiện truy cập. Phiên đã hết hạn không được tự trở lại ACTIVE chỉ vì network phục hồi.

### 10.2. Xác thực lại và ủy quyền lại

Luồng resume có thể cần:

- Xác minh danh tính theo mức yêu cầu.
- Kiểm tra tài khoản còn hoạt động.
- Kiểm tra role, target và quyết định phê duyệt.
- Kiểm tra thời hạn tuyệt đối hoặc grant liên quan.
- Kiểm tra điều kiện thiết bị hoặc đường truy cập nếu policy yêu cầu.
- Ghi sự kiện resume và phiên bản policy.

Không suy ra từ việc xác thực lại thành công rằng mọi quyền cũ đều còn hợp lệ.

### 10.3. Khôi phục cùng phiên hay mở phiên mới

Một nền tảng có thể hỗ trợ tiếp tục một phiên còn tồn tại; nền tảng khác yêu cầu kết nối mới.

Cần chỉ ra điều gì xảy ra với trạng thái đích, bản ghi phiên, credential và giới hạn thời gian. Không tự đặt lại tuổi phiên về không nếu điều đó làm vượt giới hạn tuyệt đối đã được phê duyệt.

### 10.4. Tách bước xác nhận khỏi kênh điều khiển đích

Nếu phiên đang bị khóa, các thao tác trong luồng resume không nên bị chuyển nhầm thành lệnh hoặc input tới đích.

Chỉ mở lại tương tác sau khi các điều kiện đã đạt. Bằng chứng cần cho biết ai mở lại, theo policy nào và trong giới hạn nào.

## 11. Tác vụ dài, output liên tục và người dùng đọc màn hình

### 11.1. Không có input chưa chắc không có công việc

Một quản trị viên có thể chờ truy vấn, theo dõi log hoặc đọc tài liệu trong khi phiên mở. Một tác vụ có thể liên tục xuất dữ liệu mà không cần thêm input.

Nếu policy dựa vào input, những tình huống đó vẫn có thể chạm idle deadline. Đây là hành vi cần được dự đoán và truyền đạt, không phải lỗi có thể giải quyết bằng tự động tắt timeout.

### 11.2. Output không mặc định là bằng chứng hiện diện

Nếu mọi output đều đặt lại timer, một tiến trình nền có thể giữ phiên tồn tại rất lâu dù không còn người giám sát.

Policy cần chọn ngữ nghĩa phù hợp. Không đổi từ input-based sang any-traffic chỉ để tránh một tình huống mà chưa đánh giá ảnh hưởng.

### 11.3. Kết thúc kết nối không bảo đảm dừng tác vụ

Tác vụ có thể tiếp tục tại đích sau khi client hoặc gateway ngắt. Hành vi phụ thuộc cơ chế chạy và nền tảng.

Cần phân biệt mục tiêu chặn sử dụng phiên với mục tiêu hủy một công việc. Nếu cần hủy công việc, phải có cơ chế, thẩm quyền và bằng chứng tương ứng.

Không báo một truy vấn, tiến trình hoặc job đã bị dừng chỉ từ log đóng socket.

### 11.4. Thiết kế đường cho tác vụ không tương tác

Công việc tự động hóa dài hạn có thể phù hợp hơn với một workload có danh tính riêng, quyền theo tác vụ, vòng đời và giám sát được quản lý.

Không dùng một phiên quản trị mở liên tục như danh tính dịch vụ ngầm. Ngược lại, không áp dụng máy móc quy tắc bàn phím/chuột cho mọi connection pool của ứng dụng.

Nếu có ngoại lệ cho một loại công việc, cần phạm vi, owner, thời hạn và điều kiện kết thúc rõ.

## 12. Nhiều gateway, failover và khởi động lại

### 12.1. Trạng thái phiên cần có nguồn có thẩm quyền

Khi nhiều instance có thể xử lý phiên, cần xác định ai sở hữu trạng thái, ai cập nhật last_activity và ai có quyền áp dụng timeout.

Một timer chỉ nằm trong bộ nhớ một instance có thể bị mất khi tiến trình dừng. Nhiều instance cũng có thể gửi thao tác kết thúc trùng nếu không phối hợp.

Cơ chế phối hợp cần phù hợp kiến trúc và phạm vi thực thi.

### 12.2. Không tính heartbeat thành activity của người dùng

Heartbeat có thể cần để biết gateway còn sống hoặc còn giữ quyền xử lý phiên. Nó không tự chứng minh chủ thể có tương tác.

Nếu hệ thống liên tục cập nhật last_activity từ heartbeat, idle timeout có thể không bao giờ tới dù phiên bị bỏ quên.

Cần tách liveness của thành phần khỏi activity của phiên.

### 12.3. Giữ deadline qua failover

Gateway mới cần khôi phục hoặc xác định được trạng thái thời gian theo cơ chế tin cậy. Không tự bắt đầu một cửa sổ idle mới chỉ vì instance vừa nhận phiên.

Không thể sao chép một mốc monotonic cục bộ sang máy khác rồi giả định có cùng ý nghĩa. Thiết kế có thể cần thời điểm bền vững, trạng thái tham chiếu và quy tắc xử lý sai lệch hoặc downtime.

Nếu không đủ bằng chứng để tiếp tục, cần hành vi hạn chế hoặc yêu cầu xác minh lại theo policy, thay vì mặc định làm mới phiên.

### 12.4. Timer cũ và activity mới

Một tác vụ timeout được xếp hàng trước đó có thể chạy sau khi input hợp lệ đã làm mới deadline.

Trước khi kết thúc, phải kiểm tra trạng thái và generation hiện tại. Không kết thúc chỉ dựa trên một deadline cũ trong thông điệp.

Ngược lại, một instance cũ không nên tiếp tục nhận input sau khi quyền xử lý của nó đã hết hiệu lực. Các giới hạn phối hợp phải được thực thi tại điểm liên quan, không chỉ ghi trong metadata.

## 13. Policy minh họa và giả mã điều phối

Các cấu trúc sau là mô hình logic, không phải cú pháp của một sản phẩm cụ thể.

### 13.1. Policy

~~~yaml
session_timeout_policy:
  policy_id: production-interactive-session
  subject_scope: approved-human-operators
  target_scope: approved-production-targets
  session_scope: individual-gateway-session

  idle:
    window: 10m
    activity_basis: accepted-session-interactive-input
    exclude:
      - transport-keepalive
      - gateway-heartbeat
      - recording-output
      - dashboard-polling

  warning:
    lead_time: 1m
    client_notification: enabled

  limits:
    absolute_lifetime: 30m
    approved_window_must_remain_valid: true

  expiry:
    action_reference: block-input-and-end-defined-session
    record_target_confirmation_separately: true

  resume:
    policy_reference: reauthenticate-and-reauthorize
~~~

Các giá trị 10 phút, một phút và 30 phút chỉ phục vụ ví dụ. Trường policy không tự tạo ra khả năng chặn input hoặc kết thúc phiên nếu nền tảng không hỗ trợ.

### 13.2. Xử lý input

~~~text
on_input_event(session_id, event):
    session, policy = load_current_authoritative_state(session_id)
    now = obtain_time_under_valid_clock_policy()

    if session does not permit interaction:
        return BLOCKED_OR_RESUME_REQUIRED

    if now >= effective_deadline(session, policy):
        mark_expired_and_block_new_interaction(session)
        schedule_defined_expiry_action(session)
        return EXPIRED

    verify_event_subject_channel_and_scope(event, session)
    verify_interaction_is_permitted(event, session)

    if qualifies_as_activity(event, policy):
        update_activity_with_current_generation_check(session, now)

    relay_only_permitted_interaction(event)
~~~

Giả mã yêu cầu cơ chế phối hợp đủ để xử lý trạng thái đồng thời. Một lần đọc rồi ghi không có điều kiện không tự bảo đảm đúng trong nhiều instance.

### 13.3. Xử lý deadline

~~~text
on_timeout_candidate(session_id, observed_generation):
    session, policy = load_current_authoritative_state(session_id)
    now = obtain_time_under_valid_clock_policy()

    if session is already closed:
        return

    if now < effective_deadline(session, policy):
        reschedule_using_current_state()
        return

    atomically_record_expiry_and_enforce_local_interaction_policy()
    execute_supported_expiry_actions_with_tracking_reference()
    record_each_result_and_pending_scope()
~~~

Thao tác nguyên tử trong sổ trạng thái không làm mọi hành động tới đích trở thành một giao dịch nguyên tử. Kết quả tại gateway và tại đích vẫn cần được theo dõi riêng.

## 14. Thay đổi policy và xử lý lỗi vận hành

### 14.1. Policy mới có áp dụng phiên đang mở không?

Cần quy định phiên dùng snapshot policy lúc mở hay nhận cập nhật trong quá trình hoạt động.

Nếu rút ngắn timeout cho phiên đang mở, phải biết deadline được tính lại thế nào. Nếu kéo dài, không được tự vượt cửa sổ phê duyệt hoặc giới hạn quyền khác.

Ghi policy version, thời điểm áp dụng và ảnh hưởng. Không thay cấu hình rồi để các instance tự diễn giải khác nhau.

### 14.2. Không quan sát được activity

Mất telemetry hoặc kênh input không đồng nghĩa chắc chắn người dùng đã idle, nhưng cũng không chứng minh họ đang hoạt động.

Cần chính sách cho dữ liệu thiếu và khả năng tiếp tục trong giới hạn. Không tự đặt last_activity bằng thời điểm hiện tại mỗi lần có lỗi quan sát.

### 14.3. Không thực thi được hành động tại đích

Có thể gateway đã chặn input nhưng không gọi được cơ chế logoff hoặc đóng phiên đích.

Giữ trạng thái xử lý còn tồn tại, retry theo giới hạn và chuyển cấp theo phạm vi. Không báo hoàn tất kết thúc chỉ vì tác vụ đã được đưa vào hàng đợi.

### 14.4. Nguồn trạng thái hoặc audit gặp lỗi

Cần xác định điều kiện cho phép tiếp tục tương tác, ghi bền vững và khả năng khôi phục tác vụ sau lỗi.

Không cho mọi phiên hoạt động vô thời hạn chỉ vì không truy cập được kho trạng thái. Hành vi phải được quyết định trước và phù hợp mức rủi ro.

Đường khẩn cấp, nếu có, cần kiểm soát và vòng đời riêng; không phải một cờ bỏ idle timeout cho toàn bộ hạ tầng.

## 15. Audit và bằng chứng timeout

### 15.1. Những sự kiện cần phân biệt

Có thể cần ghi theo khả năng hệ thống:

- Phiên được mở, với chủ thể, target và policy version.
- Mốc activity hợp lệ hoặc thông tin tổng hợp cần thiết.
- Deadline và nguyên nhân thay đổi deadline.
- Cảnh báo được tạo và tình trạng bàn giao theo khả năng.
- Quyết định hết hạn.
- Thời điểm chặn tương tác.
- Yêu cầu ngắt hoặc kết thúc.
- Kết quả tại gateway và xác nhận tại đích.
- Resume, xác thực lại và quyết định quyền.
- Lỗi, phần chưa xác minh và chuyển cấp.

Không phải mọi input đều cần được sao chép vào log timeout. Bằng chứng thời gian thường có thể dùng metadata về loại sự kiện, session và thời điểm.

### 15.2. Sự kiện minh họa

~~~json
{
  "event_type": "session_idle_expiry_applied",
  "session_id": "session-081",
  "subject_id": "operator-017",
  "target_id": "production-target-042",
  "policy_version": "session-policy-v7",
  "timeout_reason": "idle",
  "activity_basis": "accepted-session-interactive-input",
  "idle_elapsed_seconds": 600,
  "local_input_state": "blocked",
  "target_termination_state": "pending",
  "action_reference": "termination-081",
  "evidence_reference": "evidence-081"
}
~~~

Đây là dữ liệu giả định. Bản ghi thực tế cần thời điểm có thể tương quan, nguồn ghi và phạm vi phù hợp.

Sự kiện này chứng minh hệ thống đã ghi nhận áp dụng hết hạn và chặn input theo phạm vi. Nó chưa chứng minh target_termination_state đã hoàn tất.

### 15.3. Liên kết với request, grant và recording

Một phiên đặc quyền có thể liên quan tới phê duyệt, checkout, credential version và recording.

Cần giữ định danh để biết timeout đã ảnh hưởng phiên nào và những đối tượng vòng đời nào cần xử lý tiếp. Không tự gộp mọi phiên của cùng tài khoản thành một phiên duy nhất.

Recording tiếp tục ghi output không nên làm mới idle nếu policy loại trừ loại hoạt động đó. Hoạt động của hệ thống ghi hình cần được tách khỏi hoạt động của chủ thể.

### 15.4. Bảo vệ nội dung audit

Không ghi password, token hoặc raw input nhạy cảm vào sự kiện timeout chỉ để biết có activity.

Log về phiên cũng có thể chứa tên tài khoản, đích hoặc thông tin hạ tầng nhạy cảm. Quyền xem, sửa, xuất và thời hạn lưu cần theo yêu cầu của tổ chức.

Lịch sử không nên bị sửa để biến một hành động kết thúc lỗi thành thành công. Kết quả xử lý sau đó cần được ghi bằng sự kiện có thời điểm tương ứng.

## 16. Tình huống xuyên suốt: phiên chẩn đoán production

### 16.1. Policy của tình huống

Một quản trị viên mở phiên chẩn đoán qua gateway. Policy giả định:

- Tính activity theo input tương tác hợp lệ của phiên.
- Không tính transport keepalive và output từ đích.
- Idle window là 10 phút.
- Cảnh báo trước một phút.
- Giới hạn tuyệt đối là 30 phút từ lúc mở.
- Khi hết hạn, chặn input rồi thực hiện kết thúc theo phạm vi hỗ trợ.
- Xác nhận tại đích được ghi riêng.

Các mốc chỉ minh họa, không phải cấu hình chung cho mọi tổ chức.

### 16.2. Dòng thời gian

Các thời điểm trong bảng dùng cùng múi giờ của tình huống.

| Mốc | Sự kiện | Deadline và ý nghĩa |
|---|---|---|
| 09:00 | Phiên bắt đầu | Idle ban đầu tới 09:10; giới hạn tuyệt đối 09:30 |
| 09:03 | Input hợp lệ được chấp nhận | Idle deadline chuyển tới 09:13 |
| Sau 09:03 | Kênh gửi keepalive định kỳ | Không đặt lại idle theo policy này |
| Đến 09:11 | Tác vụ tiếp tục xuất output | Không tự chứng minh chủ thể đang tương tác |
| 09:12 | Cảnh báo trước deadline hiện tại | Người dùng được thông báo nếu client nhận được |
| 09:12:30 | Input hợp lệ mới được chấp nhận | Idle deadline chuyển tới 09:22:30 |
| 09:21:30 | Cảnh báo cho deadline mới | Không tự gia hạn phiên |
| 09:22:30 | Không có thêm activity hợp lệ | Hết hạn idle và chặn input theo policy |
| Sau đó | Hành động kết thúc được thực thi | Ghi riêng kết quả gateway và đích |

Nếu người dùng liên tục tương tác tới sau đó, giới hạn tuyệt đối 09:30 vẫn phải được xử lý. Activity không tự kéo dài mốc này.

### 16.3. Input đến sau deadline

Giả sử một input tới lúc 09:22:31. Theo mô hình ranh giới đã chọn, nó không được tự làm mới phiên.

Người dùng phải đi qua luồng được phép như xác thực và ủy quyền lại, hoặc mở phiên mới. Hệ thống không chỉ đặt last_activity=09:22:31 rồi tiếp tục.

### 16.4. Trạng thái sau quyết định hết hạn

Giả sử gateway chặn input tại deadline nhưng nhận xác nhận kết thúc phiên đích vài giây sau.

Báo cáo cần giữ hai mốc riêng. Trong khoảng đó, có thể nói tương tác mới qua gateway đã bị chặn; chưa được nói phiên đích đã chấm dứt nếu chưa có bằng chứng.

Nếu một tác vụ ở đích tiếp tục tồn tại, phải mô tả theo khả năng quan sát. Không suy ra mọi công việc đã dừng từ việc phiên tương tác kết thúc.

### 16.5. Tình huống người dùng chỉ đọc màn hình

Một người đang đọc output có thể không tạo input trong thời gian dài. Với policy này, phiên vẫn có thể hết hạn.

Cần cảnh báo và thiết kế công việc phù hợp. Không bổ sung script tạo input giả hoặc tính mọi output là activity như một cách né policy.

Nếu nhu cầu thực tế đòi hỏi một đường khác, phải thay thiết kế hoặc ngoại lệ theo phạm vi được quản trị, không âm thầm vô hiệu hóa giới hạn.

## 17. Idle timeout trong ứng phó sự cố

### 17.1. Không chờ idle khi có quyết định thu hồi

Nếu có bằng chứng tài khoản hoặc client bị xâm phạm, một chủ thể chủ động có thể tiếp tục gửi input và tránh idle timeout.

Thu hồi trong tình huống đó cần hành động theo quyết định sự cố: chặn truy cập mới, chặn hoặc kết thúc phiên, xử lý credential và grant liên quan theo phạm vi.

Không chờ đủ idle window mới bắt đầu xử lý một phiên đã được xác định cần thu hồi.

### 17.2. Timeout là một tín hiệu, không tự chứng minh xâm nhập

Nhiều phiên hết hạn có thể phản ánh công việc đọc output, vấn đề trải nghiệm hoặc cách policy nhận diện activity.

Cần xem bối cảnh trước khi diễn giải. Không gọi mọi timeout là hành vi đáng ngờ hoặc mọi phiên không timeout là an toàn.

### 17.3. Kiểm tra phần quyền còn tồn tại

Sau khi kết thúc phiên, có thể còn:

- Credential đã được xuất.
- Grant hoặc role thường trực.
- Token khác còn hiệu lực.
- Phiên ngoài gateway.
- Tác vụ hoặc thay đổi bền vững ở đích.

Idle timeout chỉ xử lý phạm vi đã thiết kế. Những lớp khác cần quy trình và bằng chứng riêng nếu mục tiêu là thu hồi rộng hơn.

### 17.4. Bảo toàn bằng chứng khi can thiệp

Cần biết chủ thể nào yêu cầu kết thúc, hệ thống đã chặn gì, kết quả tại đích và phần chưa xác minh.

Không xóa session record để làm một phiên không còn xuất hiện trên dashboard. Điều đó có thể làm mất khả năng điều tra trong khi phiên hoặc tác vụ vẫn tồn tại.

## 18. Các tình huống cần kiểm chứng

| Tình huống | Kết quả cần quan sát |
|---|---|
| Không có activity hợp lệ | Phiên đạt deadline và hành động đúng policy |
| Chỉ có keepalive | Không đặt lại timer nếu policy loại trừ |
| Output liên tục | Hành vi đúng định nghĩa activity đã chọn |
| Polling dashboard | Không vô tình làm mới phiên đích |
| Input trước deadline | Làm mới idle theo policy, giữ giới hạn tuyệt đối |
| Input tại hoặc sau ranh giới hết hạn | Không tự khôi phục phiên trái quy tắc |
| Timer cũ chạy sau activity mới | Đọc lại trạng thái, không kết thúc sai từ deadline cũ |
| Cảnh báo không tới client | Thực thi deadline vẫn theo thiết kế |
| Một người có nhiều phiên | Activity không giữ nhầm những phiên khác |
| Client mất kết nối rồi nối lại | Không tự đặt lại deadline hoặc bỏ kiểm tra quyền |
| Tài khoản mất quyền trước resume | Không tiếp tục chỉ nhờ cookie hoặc xác thực lại |
| Gateway failover hoặc khởi động lại | Giữ đúng ngữ nghĩa thời gian và trạng thái |
| Đồng hồ hoặc telemetry không tin cậy | Đi theo policy dữ liệu thiếu, không tự làm mới |
| Hành động tại đích lỗi | Giữ pending, retry có giới hạn và bằng chứng |
| Tác vụ dài vẫn chạy sau ngắt | Báo đúng phạm vi, không khẳng định đã hủy công việc |
| Policy thay đổi khi phiên đang mở | Hành vi theo quy tắc đã thống nhất và có lịch sử |

### 18.1. Quan sát ở đúng lớp

Cần kiểm tra cả giao diện, gateway và điểm thực thi trong phạm vi. Một bộ đếm trên màn hình chạy đúng không chứng minh backend đang chặn input đúng lúc.

Một API báo nhận yêu cầu logoff cũng chưa chắc chứng minh phiên đã kết thúc. Phải hiểu ngữ nghĩa phản hồi.

### 18.2. Kiểm chứng không gây ảnh hưởng ngoài kế hoạch

Có thể chọn môi trường, tài khoản và tác vụ đại diện phù hợp. Không cần chạy một tác vụ production quan trọng rồi cắt phiên bất ngờ để chứng minh timeout.

Mục tiêu là xác minh cơ chế thực tế, giới hạn và khả năng phục hồi trong phạm vi được phép.

### 18.3. Giữ rõ phần chưa kiểm tra

Nếu chưa diễn tập failover hoặc chưa có khả năng xác nhận tại một loại đích, báo giới hạn đó cùng owner và kế hoạch xử lý.

Không gộp NOT_TESTED hoặc UNKNOWN thành PASS trong báo cáo tổng.

## 19. Chỉ số và quản lý policy lâu dài

### 19.1. Chỉ số có ý nghĩa

Có thể theo dõi:

- Phiên có policy timeout rõ theo loại và môi trường.
- Phiên hết hạn theo idle, giới hạn tuyệt đối hoặc nguyên nhân khác.
- Độ trễ từ deadline tới chặn input.
- Độ trễ từ quyết định kết thúc tới xác nhận ở từng lớp.
- Hành động kết thúc còn pending hoặc không xác định.
- Resume bị từ chối do hết quyền hoặc hết cửa sổ.
- Trường hợp failover làm mất hoặc thay đổi deadline.
- Ngoại lệ và thời gian tồn tại của ngoại lệ.
- Sai lệch giữa định nghĩa activity và hành vi quan sát.

Không dùng số phiên bị đóng nhiều làm mục tiêu duy nhất. Một policy gây gián đoạn không cần thiết không tự chứng minh kiểm soát tốt hơn.

### 19.2. Mẫu số và phạm vi

Tỷ lệ áp dụng trong tập phiên đã quản lý không chứng minh mọi đường quản trị đều đi qua kiểm soát.

Cần biết còn API, console, tài khoản hoặc đường trực tiếp nào nằm ngoài gateway. Phạm vi đó phải có biện pháp và trách nhiệm phù hợp.

### 19.3. Bảo vệ quyền sửa policy

Một người đổi idle window, loại activity hoặc hành động khi hết hạn có thể kéo dài khả năng dùng đặc quyền.

Cần kiểm soát và ghi lịch sử những thay đổi này như thay đổi có ảnh hưởng tới quyền. Đặc biệt, chuyển sang tính mọi heartbeat là activity có thể làm mất tác dụng của timeout mà không cần đặt thời gian thành vô hạn.

### 19.4. Rà soát khi thay đổi hệ thống

Thay client, giao thức, gateway hoặc cơ chế HA có thể làm ngữ nghĩa input và thời gian khác đi.

Cần xác minh lại những giả định liên quan. Một bộ kiểm chứng cũ không tự chứng minh phiên bản triển khai mới vẫn hoạt động giống trước.

## 20. Lỗi thường gặp và bài tập áp dụng

### 20.1. Lỗi thường gặp

| Lỗi | Hậu quả | Cách xử lý |
|---|---|---|
| Chỉ có timer trên trình duyệt | Backend có thể tiếp tục nhận tương tác | Thực thi tại điểm có thẩm quyền |
| Mọi lưu lượng đều là activity | Keepalive hoặc output giữ phiên mãi | Định nghĩa activity theo mục tiêu |
| Tương tác ở dashboard làm mới mọi phiên | Phiên bị bỏ quên vẫn được giữ | Ràng buộc đúng session scope |
| Đặt lại idle khi reconnect | Client có thể kéo dài phiên qua nối lại | Khôi phục deadline và đánh giá lại điều kiện |
| Không có giới hạn tuyệt đối | Input liên tục duy trì phiên rất lâu | Quản lý cả thời gian tuyệt đối và thẩm quyền |
| Cảnh báo được coi là thực thi | Phiên không bị chặn khi UI lỗi | Tách cảnh báo và hành động backend |
| Đóng socket là coi đã logoff đích | Phiên hoặc tác vụ có thể còn | Xác minh tại lớp liên quan |
| Timer cũ kết thúc phiên vừa hoạt động | Gián đoạn sai thời điểm | Kiểm tra trạng thái và generation hiện tại |
| Heartbeat HA cập nhật last_activity | Idle không bao giờ tới | Tách liveness và activity |
| Failover tự cấp cửa sổ mới | Vượt thời hạn đã định | Thiết kế trạng thái bền vững và thời gian |
| Resume chỉ cần token cũ | Tiếp tục quyền không còn hợp lệ | Xác thực và ủy quyền theo điều kiện hiện tại |
| Ghi raw keystroke vào log timeout | Lộ dữ liệu nhạy cảm | Ghi metadata cần thiết |
| Tắt timeout vì có tác vụ dài | Tạo ngoại lệ thường trực | Thiết kế đường công việc và ngoại lệ có giới hạn |
| Báo terminated khi mới gửi yêu cầu | Báo quá mức bằng chứng | Tách quyết định, yêu cầu và xác nhận |
| Chờ idle để xử lý phiên đã bị thu hồi | Chủ thể có thể tiếp tục tương tác | Thực hiện thu hồi theo quyết định sự cố |

### 20.2. Bài tập

Một hệ thống PAM cấu hình idle timeout trên giao diện web. Dashboard polling mỗi khoảng ngắn cập nhật last_activity cho toàn bộ phiên của người dùng. Một phiên CLI đang xuất log liên tục. Khi trình duyệt đóng, gateway chỉ ngắt kênh tới client và báo session terminated. Sau failover, gateway mới đặt timer lại từ đầu.

Hãy phân tích:

1. Những lớp phiên nào đang bị gộp?
2. Polling và output có nên làm mới timer theo mục tiêu xử lý phiên bị bỏ quên không?
3. Báo session terminated đã đủ bằng chứng chưa?
4. Vì sao failover có thể kéo dài truy cập?
5. Cần ràng buộc activity và deadline như thế nào?
6. Những tình huống nào cần kiểm chứng trước khi nghiệm thu?

Hướng phân tích:

- Phiên web, gateway, kết nối và phiên tại đích có vòng đời riêng.
- Policy phải định nghĩa event hợp lệ; polling giao diện và output không tự chứng minh người dùng hiện diện.
- Ngắt một kênh chưa chứng minh logoff đích hoặc dừng tác vụ.
- Bắt đầu lại timer có thể cấp thêm thời gian ngoài policy.
- Cần activity thuộc đúng phiên, nguồn thời gian có thẩm quyền, giới hạn tuyệt đối và trạng thái qua failover.
- Cần kiểm chứng không activity, keepalive, output, ranh giới input, resume, nhiều phiên, lỗi kết thúc và failover.

## 21. Các điểm cần nắm

Idle timeout là một cơ chế quản lý vòng đời phiên dựa trên loại hoạt động đã được định nghĩa. Nó chỉ có hiệu lực khi có điểm thực thi, deadline đáng tin cậy và hành động rõ ràng.

Activity, keepalive, liveness và output là những khái niệm khác nhau. Hết hạn policy, chặn input, ngắt kết nối và kết thúc phiên tại đích cũng là những kết quả khác nhau.

Khi đánh giá một thiết kế, hãy theo phiên từ lúc mở, qua hoạt động, cảnh báo, deadline, resume hoặc kết thúc. Mỗi bước cần có phạm vi, trách nhiệm và bằng chứng tương ứng; không suy rộng từ một lớp sang toàn bộ hệ thống.
