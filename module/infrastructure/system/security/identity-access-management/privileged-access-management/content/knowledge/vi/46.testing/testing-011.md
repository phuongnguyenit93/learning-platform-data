# Test PAM bypass

## 1. Mục tiêu của bài học

Kiểm thử PAM bypass là kiểm tra xem một chủ thể có thể đạt quyền đặc biệt trên tài nguyên mà không thỏa các điều kiện kiểm soát đã quy định hay không. Các điều kiện đó có thể gồm xác thực mạnh, phê duyệt, cấp quyền đúng thời hạn, giới hạn tác vụ, đi qua điểm trung gian được quản lý và tạo bằng chứng truy vết.

Một cổng PAM đăng nhập thành công chưa chứng minh hệ thống chống được bypass. Một cổng PAM từ chối cũng chưa chứng minh tài nguyên đích an toàn: cùng tài khoản đó có thể còn quyền trực tiếp qua mạng quản trị, API, console, khóa SSH hoặc vai trò kế thừa.

Sau bài này, người học có thể:

- Chuyển yêu cầu kiểm soát PAM thành các bất biến có thể kiểm thử.
- Lập ma trận người dùng, workload, tài nguyên, giao thức và trạng thái cấp quyền.
- Thiết kế kiểm thử đường đi trực tiếp, quyền thường trực, credential cũ và phiên tồn tại sau thu hồi.
- Phân biệt bằng chứng kết nối với bằng chứng sử dụng quyền đặc biệt.
- Ghi nhận kết quả có thể tái hiện, gắn phát hiện với nguyên nhân và kiểm thử hồi quy.

Trong phạm vi module quản lý truy cập đặc quyền, mục tiêu là kiểm tra toàn chuỗi kiểm kê quyền, least privilege, JIT/JEA, vault, luân chuyển credential và giám sát phiên. Các ví dụ bên dưới là thiết kế phòng lab; tên tài nguyên, tài khoản và giá trị thời gian đều là dữ liệu minh họa.

## 2. Xác định đúng điều gì bị đi vòng

### 2.1. Một quyền truy cập gồm nhiều quyết định

Có thể mô tả một yêu cầu bằng bộ giá trị:

~~~text
Q = (
  initiator,
  effective_principal,
  target,
  action,
  channel,
  source,
  time,
  approval,
  grant,
  credential_or_token,
  device_or_workload_context
)
~~~

Trong đó:

- `initiator` là người hoặc workload khởi tạo yêu cầu.
- `effective_principal` là danh tính thực sự được tài nguyên đích dùng để cấp quyền.
- `grant` là lần cấp quyền cụ thể, không chỉ là tư cách thành viên nhóm.
- `channel` có thể là phiên proxy, API, kết nối trực tiếp hoặc console.
- `action` là thao tác thực tế trên tài nguyên, không chỉ hành động mở giao diện.

Một kỹ sư có thể khởi tạo phiên PAM dưới danh tính cá nhân, còn đích nhận tài khoản quản trị dùng chung. Bằng chứng phải nối được hai danh tính đó với cùng một phiên. Chỉ ghi tên tài khoản quản trị ở đích sẽ không đủ quy trách nhiệm cho người khởi tạo.

### 2.2. Các dạng bypass cần tách biệt

| Dạng | Điều kiện bị bỏ qua | Ví dụ kiểm thử |
| --- | --- | --- |
| Đường truy cập | Tuyến truy cập hoặc điểm thực thi bắt buộc | Quản trị trực tiếp từ máy người dùng dù chính sách yêu cầu qua proxy |
| Xác thực | Mức xác thực hoặc ngữ cảnh danh tính | Kênh quản trị phụ chấp nhận danh tính không đáp ứng yêu cầu của tác vụ |
| Phê duyệt | Phê duyệt hợp lệ cho đúng đối tượng và thời gian | Approval của máy A được dùng cho máy B |
| Cấp quyền | Giới hạn JIT, vai trò hoặc phạm vi tài nguyên | Quyền quản trị thường trực còn tồn tại ngoài thời hạn JIT |
| Giới hạn tác vụ | Tập thao tác được phép theo JEA | Vai trò chỉ xem trạng thái nhưng thực hiện được thay đổi cấu hình |
| Vòng đời | Hết hạn, thu hồi, rotation hoặc offboarding | Phiên tiếp tục có quyền vượt thời hạn thu hồi đã cam kết |
| Truy vết | Gắn người thực hiện với hành động và bằng chứng | Thao tác quản trị thành công qua kênh không được ghi nhận theo yêu cầu |

Một lần thử có thể phát hiện nhiều dạng cùng lúc. Ví dụ, kết nối trực tiếp dùng khóa cũ có thể vừa đi vòng proxy vừa tránh ghi hình phiên. Nên ghi riêng từng điều kiện vi phạm để không che khuất nguyên nhân.

### 2.3. Không gọi mọi đường khác proxy là bypass

Một workload có thể được phép lấy credential ngắn hạn qua API mà không qua phiên tương tác. Tài khoản break-glass có thể được phép dùng console trong sự cố. Những tuyến này chỉ là bypass khi vi phạm chính sách áp dụng cho chính chúng.

Mỗi đường truy cập phải được xếp vào một trong ba nhóm:

1. Tuyến được phép với các điều kiện kiểm soát cụ thể.
2. Tuyến ngoại lệ được phê duyệt với chủ sở hữu, thời hạn và kiểm soát bù.
3. Tuyến không được phép.

Nếu chưa xác định được chính sách, kết quả phù hợp là `POLICY_UNDEFINED`, chưa phải kết luận kỹ thuật rằng hệ thống đạt hay không đạt.

## 3. Mô hình đường đi và bất biến bảo mật

### 3.1. Xem hệ thống như tập hợp đường tới quyền đặc biệt

~~~mermaid
flowchart LR
    U[Người quản trị] --> G[Cổng xác thực và phê duyệt]
    G --> P[Proxy PAM]
    P --> T[Tài nguyên đích]
    U -. Đường trực tiếp cần kiểm thử .-> T
    W[Workload CI/CD] --> B[Broker danh tính workload]
    B --> T
    E[Danh tính khẩn cấp] --> C[Console khôi phục]
    C --> T
    T --> A[Audit tại đích]
    P --> R[Bằng chứng phiên]
    A --> S[Tương quan giám sát]
    R --> S
~~~

Sơ đồ chỉ là mô hình tham khảo. Hệ thống thực có thể dùng agent tại đích, credential injection hoặc cơ chế cấp quyền khác.

Với mỗi đường từ chủ thể tới hành động đặc quyền, hãy xác định điểm nào có khả năng thực sự từ chối yêu cầu. Cổng yêu cầu approval không phải điểm chặn hiệu quả nếu tài nguyên vẫn chấp nhận cùng quyền qua kênh khác mà không kiểm tra điều kiện tương đương.

NIST SP 800-207 nêu rằng vị trí mạng hoặc quyền sở hữu tài sản không tự tạo ra sự tin cậy. Khi thiết kế bài kiểm thử PAM, nguyên tắc này dẫn đến việc kiểm tra cả đường đi từ vùng mạng nội bộ đã được xem là tin cậy. [Nguồn: NIST SP 800-207](https://csrc.nist.gov/pubs/sp/800/207/final).

### 3.2. Viết bất biến trước khi viết test case

Bất biến là điều kiện phải luôn đúng trong phạm vi chính sách. Ví dụ:

~~~text
INV-01:
Người dùng tương tác chỉ thực hiện tác vụ quản trị trên app-lab-01
khi có grant đúng tài nguyên, đúng action và còn hiệu lực.

INV-02:
Kết nối trực tiếp từ workstation-lab không được tạo phiên quản trị
trên app-lab-01.

INV-03:
Sau khi thu hồi grant, yêu cầu đặc quyền mới phải bị từ chối
trong tối đa 30 giây theo hợp đồng kiểm thử của lab.

INV-04:
Phiên đang mở phải mất khả năng thực hiện tác vụ đặc quyền
trong tối đa 60 giây sau khi thu hồi theo hợp đồng của lab.

INV-05:
Mọi tác vụ quản trị được phép đều có bằng chứng nối
initiator -> grant hoặc ngoại lệ -> effective_principal -> target -> action.
~~~

Các giá trị 30 và 60 giây là ví dụ về yêu cầu đã thống nhất cho lab, không phải cam kết chung của sản phẩm PAM.

Nên tách yêu cầu đối với kết nối mới, yêu cầu mới trong phiên cũ và tiến trình đã chạy. Ba đối tượng này có vòng đời khác nhau; chặn đăng nhập mới không tự chứng minh đã thu hồi mọi khả năng đang tồn tại.

## 4. Chuẩn bị một bài kiểm thử có thể kết luận

### 4.1. Chốt phạm vi và trạng thái ban đầu

Đối với từng tài nguyên, ghi rõ chủ sở hữu, môi trường, giao thức quản trị, cổng dịch vụ, danh tính thử, tác vụ chứng minh quyền, thời gian thực hiện và người có quyền dừng thử nghiệm.

Phạm vi phải bao gồm các đường quản trị thay thế có liên quan: địa chỉ quản trị riêng, console máy ảo, API nhà cung cấp, cơ chế truy cập qua agent hoặc đường quản trị database. Không tự suy rằng đường chưa có trong CMDB là đường không tồn tại.

Trước khi thử, lưu các thông tin cần đối chiếu:

- Phiên bản chính sách và tập quyền hiệu lực của danh tính.
- Membership trực tiếp và kế thừa liên quan.
- Trạng thái grant, approval và ngoại lệ.
- Quy tắc mạng hoặc điểm chặn dự kiến trên đúng đường đi.
- Credential version hoặc fingerprint công khai dùng cho thử nghiệm.
- Trạng thái đồng bộ thời gian và nơi thu audit.
- Cơ chế hoàn nguyên fixture của lab.

Dữ liệu này giúp phân biệt lỗi cấu hình thật với việc bài thử sử dụng nhầm tài khoản, sai cổng hoặc fixture chưa sẵn sàng.

### 4.2. Dùng tác vụ chứng minh quyền tối thiểu

Đường thử nên kết thúc bằng một tác vụ ít tác động nhưng chỉ danh tính có quyền quản trị tương ứng mới thực hiện được. Ví dụ trong lab, dựng một API quản trị chỉ đọc trạng thái cấu hình thử và gắn quyền rõ ràng cho endpoint đó.

Không mặc định lệnh đọc danh tính, mở TCP, truy cập trang đăng nhập hoặc đọc một tệp công khai là bằng chứng có quyền quản trị. Tác vụ chứng minh phải được đối chiếu với mô hình quyền của chính tài nguyên.

Một fixture tốt có:

~~~text
probe_id: admin-config-read
target: app-lab-01
operation: đọc thuộc tính quản trị của cấu hình lab
allowed_role: lab-config-admin
expected_standard_user: DENY
expected_admin_user: ALLOW
side_effects: NONE
cleanup: không cần thay đổi trạng thái nghiệp vụ
~~~

Nếu không có tác vụ đọc nào phân biệt được quyền cần thử, có thể dùng thay đổi nhỏ trên đối tượng lab riêng với before/after và hoàn nguyên đã kiểm chứng. Không dùng dữ liệu nghiệp vụ làm vật chứng.

### 4.3. Kiểm tra đường hợp lệ làm đối chứng

Trước khi diễn giải kết quả từ chối, phải biết dịch vụ đích, danh tính và probe đang hoạt động. Chạy đường hợp lệ với grant hợp lệ và đối chứng dương tương ứng.

Nếu cả đường hợp lệ lẫn đường bị cấm đều thất bại vì máy đích tắt, bài thử không chứng minh được kiểm soát chống bypass. Đánh dấu `INCONCLUSIVE`, lưu nguyên nhân và thực hiện lại sau khi fixture sẵn sàng.

## 5. Ma trận kiểm thử tối thiểu

Bảng dưới đây là điểm khởi đầu; cần điều chỉnh theo các tuyến thật của hệ thống.

| ID | Chủ thể và trạng thái | Đường thử | Kỳ vọng chính |
| --- | --- | --- | --- |
| BP-01 | Người dùng hợp lệ, chưa có grant | Proxy PAM | Tác vụ quản trị bị từ chối |
| BP-02 | Người dùng có grant đúng phạm vi | Proxy PAM | Tác vụ đã cấp được phép và có bằng chứng |
| BP-03 | Người dùng có credential thử còn hợp lệ | Trực tiếp từ workstation | Bị chặn theo chính sách bắt buộc qua proxy |
| BP-04 | Người dùng có approval cho tài nguyên A | Yêu cầu quyền trên B | Bị từ chối vì sai phạm vi |
| BP-05 | Người dùng có grant chỉ đọc | Kênh tương tác hoặc API | Tác vụ thay đổi vượt phạm vi bị từ chối |
| BP-06 | Người dùng đã hết hạn JIT | Kết nối mới | Không tạo được quyền quản trị mới |
| BP-07 | Người dùng đang có phiên khi bị thu hồi | Phiên cũ | Mất khả năng đặc quyền trong thời hạn đã quy định |
| BP-08 | Credential cũ sau rotation hoàn tất | Xác thực mới tại đích | Credential cũ bị từ chối |
| BP-09 | Khóa hoặc certificate ngoài inventory | Đường quản trị phụ | Không được dùng để đạt quyền ngoài chính sách |
| BP-10 | Workload đúng và sai ngữ cảnh | API cấp secret hoặc token | Chỉ ngữ cảnh và scope hợp lệ được cấp |
| BP-11 | Người dùng thông thường | Luồng break-glass | Không sử dụng được ngoại lệ khẩn cấp |
| BP-12 | Broker, recorder hoặc kết nối audit bị lỗi | Tuyến liên quan | Hành vi đúng chính sách suy giảm đã thống nhất |
| BP-13 | Danh tính đã offboard | Proxy, API và đường trực tiếp | Không còn đường đạt quyền trong phạm vi thử |
| BP-14 | Thao tác được phép | Đường quản trị hợp lệ | Bằng chứng đầy đủ và tương quan được |

Ma trận phải chỉ ra điểm chặn dự kiến. BP-03 có thể bị chặn bởi firewall, agent hoặc cơ chế xác thực tại đích; không ép mọi kiến trúc phải tạo cùng một mã lỗi.

Tránh lấy tổng số test case làm đại diện cho độ bao phủ. Một giao thức bị bỏ sót có thể tạo ra đường bypass dù hàng chục bài thử khác đều đạt.

## 6. Kiểm thử kết nối trực tiếp và kênh quản trị thay thế

### 6.1. Quy trình kiểm tra một tuyến trực tiếp

Giả sử chính sách của app-lab-01 yêu cầu người dùng quản trị tương tác qua proxy PAM:

1. Xác nhận nguồn thử là workstation-lab đã định danh và nằm trong phạm vi.
2. Chọn đúng endpoint quản trị đã kiểm kê.
3. Kiểm tra khả năng thiết lập kết nối dịch vụ để biết mức reachability.
4. Nếu kết nối đến được và hợp đồng thử cho phép, thực hiện một lần xác thực bằng credential lab đã cấp.
5. Nếu xác thực thành công, chạy đúng probe quản trị tối thiểu.
6. Đối chiếu sự kiện tại điểm chặn, tại đích và tại PAM.
7. Kết thúc phiên thử và xác nhận không để lại quyền hoặc kết nối ngoài kế hoạch.

Không quét rộng hoặc đoán credential để thay thế kiểm kê đường đi. Bài kiểm thử này cần một điều kiện đã biết và kết quả có thể giải thích.

### 6.2. Diễn giải theo từng lớp

| Quan sát | Có thể kết luận | Chưa thể kết luận |
| --- | --- | --- |
| TCP kết nối được | Dịch vụ có thể tiếp cận từ nguồn thử | Có quyền quản trị hoặc bypass thành công |
| Xác thực bị từ chối | Credential hoặc điều kiện xác thực không được chấp nhận trong lần thử | Tất cả credential và đường truy cập khác đều an toàn |
| Xác thực thành công, probe bị từ chối | Có phiên nhưng chưa đạt quyền của probe | Mọi tác vụ đặc quyền khác đều bị chặn |
| Probe quản trị thành công trên tuyến bị cấm | Có vi phạm bất biến được thử nếu fixture và scope đúng | Mức độ ảnh hưởng toàn hệ thống |
| Timeout, không có log tại điểm chặn | Chưa đủ dữ liệu để xác định nguyên nhân | Firewall đã chặn đúng chính sách |
| Có log deny ở điểm chặn và đối chứng dương đạt | Có bằng chứng cho kiểm soát tại tuyến đã thử | Các tuyến chưa thử cũng đạt |

Một timeout có thể do định tuyến, dịch vụ dừng hoặc mất kết nối tạm thời. Vì vậy, bằng chứng từ chối chủ động tại điểm chặn mạnh hơn việc chỉ quan sát client không nhận phản hồi.

### 6.3. Đừng bỏ sót mặt phẳng quản trị khác

Một máy chủ có thể bảo vệ tốt phiên hệ điều hành nhưng vẫn cho phép người quản trị máy ảo thao tác qua console hoặc thay cấu hình khởi động. Một database có thể chỉ cho truy cập mạng qua PAM nhưng tài khoản quản trị nền tảng lại có khả năng thay quyền truy cập.

Với mỗi kênh, hỏi: chủ thể này có thể tác động đến quyền trên tài nguyên bằng cách nào, và điều kiện kiểm soát nào áp dụng? Chỉ thử các tác vụ đã được cấp trong môi trường thử; phát hiện khả năng tác động gián tiếp có thể đủ để mở phát hiện thiết kế mà không cần thực hiện thao tác phá hủy.

## 7. Kiểm thử JIT, phê duyệt và thu hồi

### 7.1. Approval phải gắn với đối tượng cụ thể

Một approval cần được kiểm tra theo chủ thể, tài nguyên, tập hành động và thời hạn. Chỉ kiểm tra trường `approved=true` là không đủ.

Từ một yêu cầu hợp lệ, thay đổi từng chiều trong lab:

- Đổi tài nguyên nhưng giữ approval ID.
- Đổi tác vụ từ đọc sang thay đổi.
- Dùng lại approval của danh tính thử khác.
- Gửi yêu cầu sau khi approval hết hạn hoặc đã bị hủy.
- Thử cấp quyền lần nữa nếu approval được quy định chỉ dùng một lần.

Mỗi test chỉ thay một yếu tố để có thể gắn kết quả với đúng ràng buộc. Việc có cho dùng lại approval hay không phải lấy từ chính sách, không tự giả định mọi approval đều một lần.

### 7.2. Kiểm tra quyền hiệu lực, không chỉ trạng thái hiển thị

Trạng thái cổng PAM có thể đã chuyển sang hết hạn trong khi nhóm quản trị tại đích chưa được cập nhật. Hãy ghi cả sự kiện hết hạn và khả năng thực hiện probe.

Cần phân biệt:

~~~text
eligible_role:
  Có khả năng yêu cầu kích hoạt quyền.

active_grant:
  Đã được cấp quyền trong một phạm vi và thời hạn cụ thể.

effective_privilege:
  Tài nguyên thực sự chấp nhận quyền tại thời điểm thử.
~~~

Người dùng không có active grant vẫn có thể còn quyền qua một nhóm khác, vai trò kế thừa hoặc tài khoản cục bộ. Đó là lý do kiểm thử phải đối chiếu cả quyền hiệu lực tại đích.

### 7.3. Thiết kế timeline thu hồi

Ví dụ lab quy định yêu cầu mới mất quyền trong 30 giây và phiên hiện hữu mất quyền trong 60 giây:

~~~text
t0       Cấp grant G-017 cho probe admin-config-read.
t1       Tạo phiên S-031 và xác nhận probe thành công.
t2       Gửi yêu cầu thu hồi G-017.
t2_ack   Nhận xác nhận thu hồi theo mốc bắt đầu được hợp đồng quy định.
t3       Thử yêu cầu mới qua kết nối mới.
t4       Thử probe trong phiên S-031.
t5       Tiếp tục lấy mẫu trong giới hạn số lần và thời gian đã định.
t_end    Dừng lấy mẫu, đóng phiên thử và đối chiếu audit.
~~~

Phải xác định rõ đồng hồ SLO bắt đầu ở `t2` hay `t2_ack`. Không chọn lại mốc sau khi thấy kết quả.

Lưu thời điểm từng probe, sai số đồng hồ, thời gian chờ phản hồi và khoảng lấy mẫu. Nếu probe thành công ở giây 25 và bị từ chối ở giây 35, chỉ biết chuyển trạng thái nằm trong khoảng đó; chưa đủ chứng minh đạt giới hạn 30 giây. Cần tần suất lấy mẫu phù hợp với yêu cầu kết luận.

Nếu vẫn có quyền sau mốc cho phép, ghi phát hiện thu hồi chậm hoặc không đầy đủ. Nếu chỉ có giao diện còn mở nhưng mọi thao tác đã mất quyền đúng hạn, không coi giao diện mở là bằng chứng bypass.

## 8. Kiểm thử giới hạn tác vụ và truy cập nối tiếp

### 8.1. JEA phải được kiểm tra bằng thao tác ngoài phạm vi

Với vai trò chỉ được xem tình trạng dịch vụ lab, thiết kế cặp kiểm thử:

~~~text
Action A: xem trạng thái dịch vụ lab      -> ALLOW
Action B: thay cấu hình dịch vụ lab      -> DENY
Action C: quản trị tài nguyên khác       -> DENY
~~~

Action B phải đi qua đúng đường thực thi mà người dùng có thể sử dụng, không chỉ kiểm tra nút trên giao diện. Nếu có API hỗ trợ cùng hành động, phải kiểm tra quyền ở API.

OWASP khuyến nghị từ chối mặc định và kiểm tra quyền trên từng request. Áp dụng cho bài thử PAM, cần xác nhận đường gọi tác vụ cũng thực thi giới hạn quyền, kể cả khi người dùng đã đăng nhập vào portal. [Nguồn: OWASP Authorization Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html).

### 8.2. Phiên được kiểm soát không được tự mở rộng phạm vi

Nếu chính sách chỉ cấp quyền tới máy A, xem xét khả năng phiên trên A tiếp tục truy cập máy B, tạo kênh chuyển tiếp hoặc gọi API quản trị bằng danh tính của máy A.

Bài thử trong lab chỉ cần chứng minh một tài nguyên B đã chuẩn bị có thể hoặc không thể tiếp cận và chạy probe theo phạm vi. Không cần dùng chuỗi khai thác để chứng minh rằng một tài khoản dịch vụ trên A đã được cấp quá nhiều quyền trên B.

Phân biệt hai vấn đề:

- Người dùng sử dụng quyền vượt phạm vi của grant ban đầu.
- Workload trên A có quyền hợp lệ tới B nhưng chính sách chưa xác định người dùng tương tác có được sử dụng quyền đó hay không.

Trường hợp thứ hai cần làm rõ mô hình ủy quyền trước khi chốt phát hiện. Dù vậy, việc thiếu khả năng quy trách nhiệm người dùng khi sử dụng danh tính workload vẫn có thể là thiếu sót truy vết cần ghi riêng.

### 8.3. Quan sát và ngăn chặn là hai kết quả khác nhau

Một hành động ngoài phạm vi bị ghi hình đầy đủ nhưng vẫn thực hiện được không đạt bất biến yêu cầu ngăn chặn. Ngược lại, một hành động đã bị chặn nhưng thiếu cảnh báo có thể đạt kiểm soát quyền và không đạt yêu cầu giám sát.

Luôn ghi riêng:

~~~text
authorization_result: ALLOW | DENY | UNKNOWN
operation_result: SUCCESS | FAILURE | UNKNOWN
recording_result: COMPLETE | PARTIAL | MISSING | NOT_REQUIRED
detection_result: ALERTED | NOT_ALERTED | NOT_REQUIRED | UNKNOWN
~~~

Không dùng sự có mặt của một lớp để thay cho bằng chứng ở lớp khác.

## 9. Kiểm thử vault, rotation và credential ngoài quản lý

### 9.1. Rotation cần được xác minh ở tài nguyên sử dụng

Một job rotation thành công trên dashboard chưa đủ. Cần biết credential mới đã có hiệu lực tại đích, credential cũ bị từ chối cho lần xác thực mới và các consumer hợp lệ vẫn hoạt động.

Kịch bản minh họa:

1. Dùng credential phiên bản C1 của tài khoản lab xác nhận đường thử hoạt động.
2. Chạy rotation theo quy trình lab để chuyển sang C2.
3. Chờ trạng thái hoàn tất và thời hạn hội tụ đã quy định.
4. Thử xác thực mới bằng C1 trên từng tuyến liên quan.
5. Thử đường hợp lệ bằng C2 qua cơ chế được quản lý.
6. Đối chiếu kết quả ở vault, đích và các bản sao hoặc node trong phạm vi.

Dùng phiên bản hoặc fingerprint trong báo cáo. Không ghi giá trị secret, private key hoặc token thật vào evidence.

### 9.2. Đổi credential không đồng nghĩa đóng mọi phiên

Một phiên đã xác thực, một token đã phát hành hoặc một kết nối được tái sử dụng có thể có vòng đời riêng. Bài thử phải kiểm tra theo hợp đồng của cơ chế đang dùng:

| Đối tượng | Điều cần chứng minh |
| --- | --- |
| Password cũ | Không tạo được lần xác thực mới sau mốc yêu cầu |
| SSH key hoặc certificate cũ | Không còn được chấp nhận ở các đích thuộc phạm vi |
| Token cũ | Hết khả năng sử dụng theo expiry hoặc cơ chế thu hồi đã cam kết |
| Phiên đang mở | Mất khả năng đặc quyền theo chính sách kết thúc phiên |
| Connection pool | Không giữ khả năng vượt giới hạn vòng đời đã quy định |
| Consumer hợp lệ | Chuyển sang credential mới theo yêu cầu vận hành |

Không suy rằng mọi loại token đều được thu hồi tức thời hoặc việc đổi password sẽ làm mất hiệu lực mọi phiên. Nếu yêu cầu thu hồi nhanh hơn khả năng thiết kế, đó là khoảng cách cần ghi rõ.

### 9.3. Khóa và tài khoản ngoài inventory là đường thử riêng

Tài khoản được vault quản lý vẫn có thể tồn tại một phương thức xác thực khác không do vault quản lý. Trong lab, dùng khóa thử có fingerprint đã biết hoặc tài khoản phụ đã được chủ tài nguyên xác nhận để kiểm tra chính sách.

Phát hiện cần trả lời: credential này được cấp từ đâu, ai là chủ sở hữu, còn hiệu lực ở đích nào, có thuộc ngoại lệ không, và điểm nào phải ngăn nó tạo quyền ngoài chính sách.

Việc vault không biết một khóa là tín hiệu thiếu kiểm kê; chỉ khi khóa thực sự tạo quyền trái chính sách mới có bằng chứng cho đường bypass tương ứng.

## 10. Kiểm thử workload, API và ngữ cảnh môi trường

### 10.1. Danh tính workload có điều kiện riêng

Workload không nhất thiết thực hiện MFA tương tác. Nó có thể được kiểm soát bằng quan hệ tin cậy, định danh workload, môi trường chạy, scope và thời hạn credential.

Ví dụ một pipeline lab chỉ được phép nhận credential triển khai staging:

~~~yaml
workload_policy_example:
  workload: deploy-staging-lab
  trusted_issuer: issuer-lab
  expected_subject: pipeline-staging-lab
  intended_audience: secret-broker-lab
  allowed_environment: staging
  allowed_target: app-staging-lab
  allowed_action: deploy
  credential_lifetime_seconds: 300
~~~

Đây là mô hình để mô tả bài thử, không phải cú pháp cấu hình có thể áp dụng trực tiếp cho một sản phẩm.

Tạo các ca âm với subject khác, audience khác, môi trường khác hoặc tài nguyên production giả lập. Chỉ đổi một thuộc tính mỗi lần và quan sát broker cùng tài nguyên đích.

### 10.2. Chặn cấp secret và chặn dùng secret là hai kiểm soát

Broker có thể từ chối cấp credential production cho pipeline staging, nhưng credential cũ còn trong biến môi trường vẫn có thể dùng trực tiếp. Vì vậy cần thử cả:

- Quyết định cấp credential hoặc token mới.
- Khả năng sử dụng vật chứng lab đã tồn tại.
- Quyền thực tế mà credential đó mang tại tài nguyên.
- Vòng đời sau khi workload bị vô hiệu hóa hoặc thay chính sách.

Không lấy kết quả broker từ chối để kết luận tất cả credential đã phát hành đều mất hiệu lực.

### 10.3. API phải thực thi quyền độc lập với giao diện

Ẩn nút truy cập hoặc giới hạn danh sách tài nguyên trên UI không đủ nếu backend vẫn chấp nhận thao tác ngoài phạm vi. Dùng client kiểm thử được định danh trong lab để gọi đúng endpoint đã được cấp phép thử, với danh tính ít quyền.

Kiểm tra quyền theo đối tượng và tác vụ, bao gồm yêu cầu dùng resource ID của tài nguyên khác trong tập fixture. Không cần khám phá tài nguyên ngoài scope hoặc thử dữ liệu của người dùng thật.

## 11. Kiểm thử break-glass và trạng thái suy giảm

### 11.1. Break-glass là ngoại lệ cần có hợp đồng rõ

Một tuyến break-glass được phê duyệt nên có danh tính được quản lý, điều kiện kích hoạt, quyền giới hạn phù hợp, chủ sở hữu và cơ chế bằng chứng.

Bài kiểm thử cần chứng minh:

1. Người dùng bình thường không thể dùng danh tính hoặc cơ chế khẩn cấp.
2. Luồng khẩn cấp hợp lệ hoạt động trong đúng tình huống đã quy định.
3. Tác vụ được ghi nhận và cảnh báo theo yêu cầu của ngoại lệ.
4. Sau khi kết thúc, phiên, credential và quyền tạm được xử lý theo quy trình.
5. Không còn trạng thái khẩn cấp kéo dài ngoài thời hạn phê duyệt.

Một ngoại lệ hoạt động đúng hợp đồng không được tính là bypass. Ngoại lệ không có chủ sở hữu hoặc thời hạn rõ cần được ghi thành thiếu sót quản trị, thay vì tùy ý coi là đường hợp lệ.

### 11.2. Thử lỗi có kiểm soát theo từng thành phần

Các thành phần nên được xem xét gồm dịch vụ quyết định chính sách, vault, proxy, recorder, agent, kênh audit và đường đồng bộ trạng thái.

Trong lab, mô phỏng lỗi một thành phần mỗi lượt, ví dụ cô lập recorder khỏi phiên thử theo cơ chế kiểm soát lỗi của môi trường. Không cần tắt hạ tầng dùng chung để kiểm tra một phiên.

Trước thử phải xác định:

~~~text
new_sessions_when_recorder_unavailable: DENY
existing_sessions_when_recorder_unavailable: TERMINATE_WITHIN_60_SECONDS
emergency_route: SEPARATE_APPROVED_WORKFLOW
required_evidence: local_event + central_alert
~~~

Các giá trị trên chỉ là một hợp đồng mẫu. Hệ thống khác có thể chọn buffer audit cục bộ hoặc chế độ suy giảm khác, nhưng phải biết giới hạn, thời hạn và bằng chứng cần đạt.

### 11.3. Phân loại đúng kết quả khi có lỗi

Nếu chính sách yêu cầu chặn phiên mới mà hệ thống vẫn cho quản trị bình thường khi recorder lỗi, đó là vi phạm. Nếu chính sách cho phép phiên được phê duyệt tiếp tục với buffer cục bộ, bài thử phải xác nhận buffer đầy đủ, không mất sự kiện và được gửi bù theo yêu cầu.

Nếu hệ thống từ chối toàn bộ truy cập, kiểm soát bảo mật có thể đạt nhưng yêu cầu sẵn sàng có thể không đạt. Hai kết quả phải được báo riêng; không gọi việc dịch vụ tắt là bằng chứng mọi điều kiện PAM đều được thực thi.

## 12. Thu thập bằng chứng và thiết kế oracle kiểm thử

### 12.1. Ba nguồn bằng chứng nên được đối chiếu

Client cho biết người thử đã yêu cầu gì và nhận phản hồi nào. Điểm kiểm soát cho biết quyết định chính sách và rule được áp dụng. Tài nguyên đích cho biết danh tính và hành động có thực sự xảy ra hay không.

Khi cần ghi hình hoặc transcript, bổ sung bằng chứng phiên. Khi cần phát hiện, bổ sung cảnh báo giám sát. Không giả định log PAM luôn chứa đầy đủ sự kiện của một đường đã đi vòng PAM.

Một bản ghi thử tối thiểu có thể như sau:

~~~yaml
test_result_example:
  test_id: BP-03
  run_id: pam-bypass-lab-017
  policy_version: lab-policy-12
  initiator: engineer-lab-01
  effective_principal: admin-lab-01
  source: workstation-lab
  target: app-lab-01
  channel: direct-management
  probe_id: admin-config-read
  grant_id: null
  expected:
    privileged_operation: DENY
    enforcement_point: target-agent-or-network-rule
  observed:
    connectivity: REACHABLE
    authentication: ACCEPTED
    privileged_operation: SUCCESS
    target_event_id: target-event-019
    pam_session_id: null
  result: FAIL
  violated_invariant: INV-02
  evidence:
    - client-transcript-redacted
    - target-audit-event-019
    - policy-snapshot-lab-12
~~~

`pam_session_id: null` không tự chứng minh bypass; trong ví dụ, kết luận dựa vào tuyến bị cấm và probe đặc quyền đã thành công.

### 12.2. Oracle là quy tắc quyết định kết quả

Không dùng quy tắc đơn giản như “client báo lỗi thì PASS”. Có thể mô tả oracle cho một bài thử ngăn chặn như sau:

~~~text
Nếu điều kiện đầu vào hoặc đối chứng không hợp lệ:
    INCONCLUSIVE

Nếu probe đặc quyền thành công và trái chính sách:
    FAIL

Nếu từ chối được xác nhận tại điểm kiểm soát dự kiến,
đối chứng hợp lệ và không có dấu hiệu probe thành công:
    PASS cho kiểm soát ngăn chặn đã thử

Nếu tác vụ bị từ chối nhưng thiếu bằng chứng để xác định nguyên nhân:
    INCONCLUSIVE cho kết luận ngăn chặn

Nếu bằng chứng audit bắt buộc bị thiếu:
    Ghi thêm FAIL cho yêu cầu audit;
    giữ riêng kết quả thực thi quyền nếu có đủ dữ liệu.
~~~

Nếu có xác nhận đáng tin cậy rằng probe đã thành công trái chính sách, thiếu log phụ không làm phát hiện đó biến thành `INCONCLUSIVE`. Cần giữ nguyên phát hiện và ghi thêm khoảng trống bằng chứng.

### 12.3. Tương quan và bảo toàn bằng chứng

Lưu thời gian UTC có độ chính xác phù hợp, run ID, danh tính, tài nguyên, action, grant hoặc exception ID, decision ID và session ID nếu có. Nguồn nào không hỗ trợ một trường thì ghi rõ hạn chế và cách đối chiếu thay thế.

Hash hỗ trợ kiểm tra tệp bằng chứng có thay đổi sau khi thu thập; nó không tự chứng minh nội dung log đúng hoặc nguồn log đáng tin. Cần giữ cả nguồn, thời điểm thu, quyền truy cập kho bằng chứng và chuỗi bàn giao.

Khử secret và dữ liệu nhạy cảm khỏi transcript trước khi chia sẻ. Với credential, lưu version hoặc fingerprint phù hợp; với token, lưu thuộc tính không bí mật cần cho kết luận, không sao chép bearer token vào báo cáo.

## 13. Case study: cổng PAM đạt nhưng đường trực tiếp còn quyền

### 13.1. Bối cảnh

Một nhóm vận hành quản trị app-lab-01 qua proxy PAM. Approval và MFA hoạt động đúng trên cổng. Chính sách yêu cầu mọi thao tác quản trị tương tác đi qua proxy; ngoại lệ console chỉ dành cho nhóm khẩn cấp riêng.

Tài khoản engineer-lab-01 không có active grant. Một khóa lab trước đây vẫn còn được chấp nhận cho tài khoản admin-lab-01 tại máy đích. Workstation thử cũng còn đường mạng tới dịch vụ quản trị của máy đó.

### 13.2. Thực hiện và quan sát

| Bước | Kết quả quan sát | Ý nghĩa |
| --- | --- | --- |
| Yêu cầu qua proxy khi chưa có grant | Bị từ chối, có decision ID | Cổng thực thi kiểm tra grant cho đường này |
| Đối chứng qua proxy với grant hợp lệ | Probe thành công, có audit và phiên | Probe cùng dịch vụ đích hoạt động |
| Trở lại trạng thái không có grant | Quyền trên cổng đã hết hiệu lực | Điều kiện đầu vào của ca âm được xác nhận |
| Truy cập trực tiếp bằng khóa lab cũ | Xác thực thành công | Phương thức xác thực ngoài vòng quản lý còn hiệu lực |
| Chạy probe quản trị tối thiểu | Đích ghi SUCCESS | Có quyền thực tế trên tuyến bị cấm |
| Đối chiếu phiên PAM | Không có phiên tương ứng | Tuyến trực tiếp không được proxy ghi nhận |
| Đối chiếu inventory và ngoại lệ | Khóa không thuộc ngoại lệ hợp lệ | Không có căn cứ coi tuyến này là đường được phép |

### 13.3. Kết luận phát hiện

Phát hiện chính là tác vụ quản trị thành công ngoài tuyến bắt buộc, vi phạm INV-02. Những yếu tố góp phần gồm đường mạng trực tiếp còn mở, khóa còn hiệu lực và thiếu ràng buộc tại đích đối với tuyến truy cập.

Cổng PAM không phải nơi duy nhất cần sửa. Nhóm phụ trách cần xác định điểm chặn phù hợp với kiến trúc, xử lý khóa cũ và cập nhật quản lý vòng đời credential. Nếu chỉ sửa giao diện hoặc cảnh báo ở portal, đường trực tiếp có thể vẫn tồn tại.

Sau khắc phục, thực hiện lại chính tuyến cũ, các đường quản trị tương đương trong scope và đối chứng hợp lệ. Khóa cũ phải không còn đạt quyền; đường được cấp qua PAM vẫn phải hoạt động và tạo đủ bằng chứng.

## 14. Đưa phát hiện vào xử lý và kiểm thử hồi quy

### 14.1. Một phát hiện cần đủ để tái hiện

Báo cáo nên gồm:

- Bất biến và điều khoản chính sách bị vi phạm.
- Chủ thể, quyền ban đầu, tài nguyên, đường truy cập và điều kiện cần.
- Các bước tối thiểu để tái hiện trên fixture được phép.
- Kết quả kỳ vọng, kết quả thực tế và tác vụ chứng minh quyền.
- Bằng chứng tương quan giữa client, điểm kiểm soát và đích.
- Phạm vi ảnh hưởng đã xác minh và phần chưa kiểm tra.
- Chủ sở hữu khắc phục, kiểm soát bù tạm thời và tiêu chí đóng.

Không nâng phạm vi ảnh hưởng từ một máy lab thành toàn bộ hệ thống nếu chưa có bằng chứng. Có thể ghi giả thuyết cần xác minh khi nhiều tài nguyên dùng chung policy.

### 14.2. Đánh giá mức độ theo hậu quả thực

Các yếu tố cần xem xét là quyền thực sự đạt được, độ nhạy cảm của tài nguyên, điều kiện tiên quyết, số tuyến hoặc đích có thể bị ảnh hưởng, khả năng phát hiện và thời gian quyền tồn tại.

Một tuyến trực tiếp chỉ cho phép đọc trạng thái lab khác với tuyến cho phép quản trị dữ liệu production. Tuy nhiên, thiếu recording không tự làm một đường truy cập có quyền thấp thành mức cao; cần trình bày riêng hậu quả đối với truy vết và yêu cầu vận hành.

### 14.3. Bộ hồi quy cần giữ cả ca âm lẫn ca dương

Sau thay đổi firewall, nâng cấp PAM, thay identity provider, đổi vai trò hoặc thêm giao thức quản trị, chạy lại các bài có quan hệ với thay đổi.

Bộ hồi quy nên bao gồm:

~~~text
1. Tuyến hợp lệ + grant hợp lệ             -> ALLOW
2. Tuyến hợp lệ + không có grant           -> DENY
3. Tuyến trực tiếp bị cấm                  -> DENY quyền quản trị
4. Grant sai tài nguyên hoặc action        -> DENY
5. Grant hết hạn hoặc bị thu hồi           -> DENY trong giới hạn yêu cầu
6. Credential cũ sau rotation              -> DENY xác thực mới theo hợp đồng
7. Ngoại lệ khẩn cấp hợp lệ                -> ALLOW đúng phạm vi + đủ bằng chứng
8. Danh tính thông thường dùng ngoại lệ    -> DENY
~~~

Chỉ chạy các bài âm có thể bỏ sót trường hợp hệ thống chặn tất cả do lỗi dịch vụ. Chỉ chạy bài dương lại bỏ sót đường đi vòng. Hai nhóm cùng nhau mới giúp diễn giải kết quả.

## 15. Tự động hóa ở mức phù hợp

Có thể tự động hóa việc nạp ma trận, chuẩn bị fixture, gọi probe, thu response, nối event ID và đánh giá oracle. Script phải dùng danh tính thử riêng, giới hạn số lần, timeout và cơ chế dọn phiên đã tạo.

Mô hình xử lý tham khảo:

~~~text
for each test_case in approved_lab_matrix:
    validate_scope(test_case)
    verify_fixture_and_positive_control(test_case)
    record_baseline_identity_and_policy(test_case)

    observation = execute_bounded_probe(test_case)
    target_evidence = collect_target_observation(test_case)
    control_evidence = collect_enforcement_observation(test_case)

    result = evaluate(
        expected_policy,
        observation,
        target_evidence,
        control_evidence,
        timing_uncertainty
    )

    close_test_sessions()
    restore_test_fixture_if_changed()
    persist_redacted_result(result)
~~~

Đây là giả mã tổ chức kiểm thử, không phải công cụ vượt PAM. Không để hàm `evaluate` coi việc không thu được log là bằng chứng tác vụ không xảy ra. Nếu thu evidence bất đồng bộ, ghi rõ thời gian chờ hợp lệ trước khi phân loại thiếu dữ liệu.

Trong báo cáo tự động, nên lưu kết quả theo từng chiều quyền, audit, phát hiện và sẵn sàng. Không gộp tất cả thành một cờ xanh duy nhất khi vẫn có yêu cầu bắt buộc chưa được xác nhận.

## 16. Những sai lầm dễ dẫn tới kết luận sai

| Sai lầm | Vì sao kết luận yếu | Cách sửa |
| --- | --- | --- |
| Chỉ kiểm tra cổng PAM | Không bao phủ đường tới tài nguyên | Kiểm kê và thử từng tuyến quản trị liên quan |
| Dùng TCP reachable làm bằng chứng bypass | Chưa chứng minh xác thực hoặc quyền | Chạy probe phân biệt quyền trong scope |
| Thấy timeout là đánh dấu PASS | Có thể do lỗi fixture | Đối chiếu log điểm chặn và đối chứng |
| Kiểm tra quyền trên UI | Backend có thể có đường thực thi riêng | Thử API hoặc kênh thực tế |
| Coi rotation là thu hồi mọi phiên | Các đối tượng có vòng đời riêng | Tách credential, token, session và pool |
| Bỏ qua quyền kế thừa | Quyền thường trực có thể nằm ngoài grant | Kiểm tra quyền hiệu lực tại đích |
| Coi mọi break-glass là bypass | Ngoại lệ có thể đã được phê duyệt | Đối chiếu hợp đồng ngoại lệ |
| Dùng tỷ lệ PASS chung để đóng phát hiện | Một đường trọng yếu vẫn có thể mở | Yêu cầu đạt từng bất biến bắt buộc |
| Coi có recording là đã ngăn chặn | Quan sát không thay thế thực thi quyền | Báo riêng authorization và evidence |
| Dùng probe mà user thường cũng chạy được | Không phân biệt được quyền quản trị | Kiểm chứng fixture bằng hai vai trò |
| Kết luận tức thời từ dữ liệu lấy mẫu thưa | Không biết thời điểm thu hồi chính xác | Ghi khoảng bất định và lấy mẫu phù hợp |
| Bỏ qua cleanup | Phiên hoặc quyền thử có thể tồn tại lâu hơn dự kiến | Xác nhận kết thúc và khôi phục fixture |

## 17. Bài thực hành và câu hỏi tự kiểm tra

### 17.1. Bài thực hành

Dựng một tài nguyên lab có probe chỉ đọc dành cho vai trò quản trị, một đường qua PAM và một đường trực tiếp. Chuẩn bị người dùng thường, người dùng có thể nhận JIT, workload staging và một danh tính khẩn cấp riêng.

Viết trước bốn bất biến: tuyến bắt buộc, phạm vi grant, thời hạn thu hồi và yêu cầu bằng chứng. Sau đó thiết kế tối thiểu các ca cho trạng thái chưa cấp quyền, đang có quyền, hết hạn, thu hồi giữa phiên và credential đã rotation.

Với mỗi ca, nộp một bản ghi gồm input, expected, observed, kết quả theo từng chiều, event ID và giới hạn kết luận. Nếu fixture không hoạt động, ghi `INCONCLUSIVE` cùng bước cần làm lại.

Bài thực hành hoàn thành khi có thể trả lời bằng bằng chứng:

- Tuyến nào thực sự cho phép tác vụ quản trị?
- Quyết định cho phép hoặc từ chối được thực thi ở đâu?
- Quyền còn tồn tại bao lâu sau thu hồi và sai số đo là bao nhiêu?
- Có nối được người khởi tạo với danh tính hiệu lực và hành động tại đích không?
- Các phiên, quyền và đối tượng thử đã được xử lý sau khi kết thúc chưa?

### 17.2. Câu hỏi tự kiểm tra

**Một client bị từ chối ở portal nhưng đăng nhập trực tiếp được. Đã đủ kết luận PAM bypass chưa?**

Cần xác nhận tuyến trực tiếp có bị cấm theo chính sách và đăng nhập đó có thực hiện được quyền đang kiểm thử hay không. Nếu chính sách cấm chính việc tạo phiên ngoài PAM, xác thực trực tiếp đã là bằng chứng cho vi phạm đó; nếu bất biến nói về tác vụ quản trị, cần thêm probe phù hợp.

**Vì sao không dùng việc không có session ID PAM làm bằng chứng duy nhất?**

Một số đường workload hoặc ngoại lệ hợp lệ có thể không tạo loại session ID đó. Cần đối chiếu chính sách và hành động tại đích.

**Sau rotation, password cũ không đăng nhập mới được nhưng phiên cũ vẫn hoạt động. Kết quả là gì?**

Kiểm soát credential cũ có thể đạt. Kết quả về phiên phụ thuộc yêu cầu vòng đời phiên; nếu vượt thời hạn thu hồi đã quy định thì mở phát hiện riêng.

**Tài nguyên không trả lời và log PAM không có gì. Đánh dấu thế nào?**

Chưa đủ bằng chứng xác định điểm chặn. Kiểm tra đối chứng, trạng thái dịch vụ, định tuyến và telemetry; nếu vẫn thiếu dữ liệu thì ghi `INCONCLUSIVE`.

**Đường quản trị bị chặn nhưng không có cảnh báo bắt buộc. Có thể chốt đạt toàn bộ không?**

Không. Ghi kết quả ngăn chặn theo bằng chứng hiện có và kết quả không đạt đối với yêu cầu cảnh báo.

## 18. Tiêu chí hoàn tất kiểm thử

Một đợt kiểm thử PAM bypass có thể được nghiệm thu khi các tuyến quản trị trọng yếu trong phạm vi đã được kiểm tra, ca dương xác nhận fixture hoạt động, các ca âm có kết luận đủ bằng chứng và mọi ngoại lệ đều được đối chiếu với chính sách.

Các phát hiện chưa sửa phải có chủ sở hữu và cách xử lý rủi ro được ghi nhận theo quy trình của tổ chức. Không gán PASS cho ca chưa chạy hoặc chưa đủ dữ liệu; không xem một ngoại lệ chưa được phê duyệt là đường hợp lệ chỉ vì hệ thống hiện đang cho phép.

Giá trị của bài kiểm thử nằm ở việc chứng minh ranh giới quyền thực sự được thực thi tại tài nguyên, trên từng đường đi và trong suốt vòng đời truy cập. Portal, vault, JIT, JEA và giám sát phiên chỉ tạo thành kiểm soát hiệu quả khi các điều kiện đó không thể bị bỏ qua qua một tuyến khác nằm trong phạm vi chính sách.
