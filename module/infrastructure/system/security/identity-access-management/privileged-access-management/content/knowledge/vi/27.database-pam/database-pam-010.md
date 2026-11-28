# Database break-glass

## Mục tiêu bài học

Sau bài học này, bạn có thể:

- Xác định khi nào cần kích hoạt truy cập database khẩn cấp.
- Thiết kế đường truy cập dự phòng có thể sử dụng khi một thành phần bình thường bị lỗi.
- Giới hạn danh tính, quyền, đích và thời gian trong một lần break-glass.
- Bảo vệ credential và bằng chứng trong điều kiện vận hành suy giảm.
- Đóng quyền, xử lý phiên tồn dư và xác minh trạng thái dữ liệu sau sự kiện.

## 1. Database break-glass là gì?

**Database break-glass** là cơ chế truy cập đặc quyền khẩn cấp đã được chuẩn bị để xử lý một tình huống không thể giải quyết kịp bằng đường vận hành thông thường.

Ví dụ, hệ thống danh tính doanh nghiệp lỗi trong khi database sản xuất có một phiên gây nghẽn nghiêm trọng. Đội trực cần một đường được phép để chẩn đoán và thực hiện tác vụ khôi phục cụ thể.

Break-glass không đồng nghĩa tài khoản luôn có mọi quyền, mật khẩu chia sẻ cho cả đội hoặc bỏ toàn bộ kiểm soát. Nó là một quy trình ngoại lệ với:

- Điều kiện kích hoạt.
- Người có thẩm quyền và người thực hiện.
- Đích, hành động và giới hạn.
- Cách cấp hoặc lấy credential.
- Bằng chứng tối thiểu.
- Điểm kết thúc và xác minh.
- Rà soát sau sự kiện.

### 1.1. Kết quả mong muốn

Một lần sử dụng thành công không chỉ là “đã vào được database”. Cần đạt được cả ba kết quả:

1. Xử lý hoặc giảm tác động của sự cố.
2. Duy trì khả năng biết ai đã làm gì và vì sao.
3. Đóng các khả năng đặc quyền tạm thời và xử lý hậu quả còn lại.

Nếu dịch vụ phục hồi nhưng tài khoản khẩn cấp vẫn mở ngoài kế hoạch, công việc PAM chưa hoàn tất.

### 1.2. Bài học không phải runbook khôi phục cho mọi engine

Các ví dụ kỹ thuật sử dụng PostgreSQL 18 để làm rõ một số khác biệt về role và phiên. Việc khôi phục xác thực, dừng phiên hoặc sửa dữ liệu phải theo engine, phiên bản, mô hình hosting và quy trình được tổ chức chấp nhận.

Không có một lệnh break-glass chung an toàn cho mọi database.

## 2. Khi nào nên kích hoạt?

Một tình huống phù hợp thường có cả nhu cầu khẩn cấp và bằng chứng rằng đường thông thường không đáp ứng.

| Tình huống | Câu hỏi trước khi kích hoạt |
|---|---|
| SSO hoặc IdP lỗi | Database còn hoạt động và có đường xác thực độc lập được chuẩn bị không? |
| Gateway hoặc PAM chính lỗi | Đường dự phòng có nằm trong phạm vi được phê duyệt không? |
| Người quản trị thông thường bị khóa quyền | Có đúng là thiếu quyền quản trị hay do mạng, chứng chỉ hoặc trạng thái dịch vụ? |
| Cần xử lý phiên gây gián đoạn | Đã xác định đúng phiên và hậu quả của việc dừng chưa? |
| Nghi credential quản trị bị chiếm | Đường khẩn cấp còn đáng tin cậy không? |
| Cần sửa trạng thái dữ liệu khẩn cấp | Có kế hoạch, điều kiện và cách xác minh hoặc phục hồi không? |
| Control plane hoặc database không khả dụng | Truy cập SQL có giải quyết được hay phải xử lý lớp hạ tầng trước? |

### 2.1. Khẩn cấp cần tiêu chí, không chỉ cảm giác

Tổ chức nên xác định trước mức ảnh hưởng, thời gian phản ứng và người có thể tuyên bố tình huống khẩn cấp.

Ví dụ tiêu chí nội bộ có thể là gián đoạn chức năng trọng yếu, nguy cơ mất dữ liệu hoặc một cuộc tấn công đang diễn ra. Các tiêu chí đó cần phù hợp hệ thống thực tế; không có ngưỡng thời gian cố định dùng cho mọi tổ chức.

### 2.2. Những nhu cầu không tự trở thành break-glass

- Một tác vụ thường kỳ chưa được xin quyền.
- Muốn tránh quy trình thay đổi.
- Không muốn chờ người phụ trách trong khi chưa có tác động khẩn cấp.
- Cần đọc thêm dữ liệu để điều tra thông thường.
- Công cụ tiện dụng bị lỗi nhưng còn đường vận hành hợp lệ khác.

Nếu break-glass trở thành cách làm hằng ngày, cần sửa thiết kế quyền hoặc quy trình bình thường.

## 3. Phân biệt các lớp đặc quyền

Database có thể phụ thuộc vào nhiều lớp quản trị:

| Lớp | Khả năng điển hình | Không nên suy ra |
|---|---|---|
| Danh tính tổ chức | Xác thực người và cấp nhóm | Tự có quyền SQL trong mọi database |
| PAM hoặc gateway | Cấp phiên, bảo quản credential, ghi nhận yêu cầu | Tự kiểm soát mọi đường kết nối trực tiếp |
| Danh tính database | Kết nối và thực hiện quyền SQL được cấp | Tự có quyền sửa hệ điều hành hoặc dịch vụ cloud |
| Hệ điều hành hoặc nền tảng container | Quản lý tiến trình, tệp hoặc runtime theo quyền | Tự khôi phục được mọi dữ liệu hoặc khóa |
| Control plane cloud | Quản lý dịch vụ database theo chức năng nhà cung cấp | Tương đương superuser đầy đủ bên trong engine |
| Hệ thống khóa và sao lưu | Bảo vệ hoặc phục hồi dữ liệu theo thiết kế | Có thể bỏ qua mọi yêu cầu về khóa hoặc tính nhất quán |

Một database quản lý bởi nhà cung cấp có thể giới hạn những thao tác mà tài khoản quản trị được làm. Không lấy runbook của database tự quản trị để áp dụng nguyên trạng cho dịch vụ được quản lý.

### 3.1. Chọn đúng lớp để khắc phục

Nếu database hết dung lượng hoặc control plane đang lỗi, việc có mật khẩu quản trị SQL chưa chắc giải quyết được. Nếu nguyên nhân là một truy vấn giữ lock, thay đổi cấu hình mạng có thể không phải tác vụ cần thiết.

Cần xác định giả thuyết nguyên nhân và hành động tương ứng trước khi mở quyền mạnh.

## 4. Chuẩn bị đường dự phòng theo tình huống lỗi

### 4.1. Vẽ mối phụ thuộc

Một ví dụ phân tích:

~~~text
Người trực
  │
  ├── Thiết bị quản trị
  ├── Kênh phê duyệt và liên hệ
  ├── Nơi giữ credential / cơ chế cấp phiên
  ├── Yếu tố xác thực bổ sung
  ├── Mạng, DNS và chứng chỉ
  └── Database hoặc control plane đích
             │
             └── Nguồn audit và nơi giữ bằng chứng
~~~

Với từng nhánh, hỏi điều gì xảy ra nếu thành phần đó lỗi hoặc bị xâm nhập.

### 4.2. Tránh vòng phụ thuộc

Ví dụ, mật khẩu khẩn cấp nằm trong vault mà việc truy cập vault chỉ dùng chính IdP đang lỗi. Đường dự phòng tồn tại trên giấy nhưng không dùng được trong kịch bản cần thiết.

Một ví dụ khác là khóa giải mã bản dự phòng chỉ lấy được từ cùng account cloud đang bị khóa quyền. Cần thiết kế phương án theo rủi ro cụ thể, không chỉ chuẩn bị thêm một bản mật khẩu.

### 4.3. Độc lập vừa đủ và vẫn được kiểm soát

Không nhất thiết mỗi thành phần phải có một bản sao hoàn toàn tách biệt. Cần xác định những lỗi mà phương án dự phòng phải chịu được và kiểm thử chúng.

Một đường độc lập nhưng không ai giám sát, dùng credential cũ hoặc mở cho toàn mạng có thể tạo rủi ro lớn hơn mục tiêu khôi phục ban đầu.

### 4.4. Phân biệt lỗi và xâm nhập

Khi IdP chỉ gián đoạn kỹ thuật, có thể dùng thiết bị và danh tính khác đã được chuẩn bị.

Nếu nghi IdP, vault hoặc máy quản trị bị chiếm, phải đánh giá độ tin cậy của credential và mọi phiên cấp từ chúng. Không tự chuyển sang một đường khác có cùng nguồn bị nghi xâm nhập.

## 5. Các mô hình truy cập khẩn cấp

### 5.1. Danh tính khẩn cấp được chuẩn bị trước

Một principal riêng tồn tại trước sự cố, có quyền được xác định và cơ chế bảo vệ credential.

Ưu điểm là có thể giảm phụ thuộc vào khả năng tạo principal trong lúc lỗi. Rủi ro là credential hoặc quyền tồn tại lâu nếu không được quản lý.

Cần xác định đường đăng nhập nào luôn khả dụng, đường nào được mở theo quyết định và ai có thể thay đổi trạng thái đó.

### 5.2. Cấp danh tính hoặc quyền tạm thời

Một hệ thống độc lập có thể tạo hoặc kích hoạt quyền khi có yêu cầu khẩn cấp hợp lệ.

Mô hình này giảm một số đặc quyền thường trực nhưng phụ thuộc khả năng hoạt động của bên cấp. Nếu chính quyền cần để kích hoạt nằm sau thành phần đang lỗi, phương án chưa đáp ứng kịch bản.

### 5.3. Khôi phục thông qua nền tảng hoặc nhà cung cấp

Một số tình huống cần đường quản trị ở lớp nền tảng hoặc quy trình hỗ trợ chính thức.

Đó là một đường đặc quyền riêng, cần owner, kênh xác minh, giới hạn và bằng chứng. Không nên chỉ ghi “liên hệ hỗ trợ” mà không chuẩn bị ai được liên hệ và cách chứng minh quyền sở hữu.

### 5.4. Không chọn mô hình theo khẩu hiệu

“Không có tài khoản thường trực” hoặc “luôn có tài khoản dự phòng” đều chưa đủ để quyết định. Cần so sánh khả năng phục hồi, phạm vi quyền và những đường có thể bị lạm dụng.

Một hệ thống có thể kết hợp nhiều mô hình cho những kịch bản khác nhau.

## 6. Giới hạn quyền trước sự cố

### 6.1. Không mặc định cấp superuser

Nhiệm vụ xem tình trạng, xử lý một phiên hoặc khôi phục một quyền cụ thể có thể cần các tập quyền khác nhau.

Tạo các năng lực có phạm vi rõ khi engine cho phép:

- Quan sát và chẩn đoán.
- Xử lý phiên đã được xác minh.
- Sửa một nhóm cấu hình.
- Khôi phục quyền truy cập.
- Sửa dữ liệu theo kế hoạch riêng.
- Quản trị cấp cao chỉ cho những nhiệm vụ thật sự cần.

Một principal có quyền quản lý role và quyền đọc toàn dữ liệu cùng lúc cần mức kiểm soát mạnh hơn một principal chẩn đoán hẹp.

### 6.2. Quyền hẹp phải được kiểm tra hiệu lực

Không chỉ nhìn grant trực tiếp. Cần rà soát membership, khả năng chuyển role, ownership, routine đặc quyền và quyền được cấp qua đường khác.

Một role có tên emergency-readonly không tự bảo đảm chỉ đọc nếu còn được phép gọi routine làm thay đổi dữ liệu.

### 6.3. Trạng thái LOGIN và hạn mật khẩu không phải cùng một thứ

Trong PostgreSQL, LOGIN/NOLOGIN kiểm soát khả năng dùng role làm danh tính đăng nhập ban đầu. VALID UNTIL là thời hạn của mật khẩu, không phải thời hạn tổng thể của role và không áp dụng như nhau cho cách xác thực không dùng mật khẩu. [PostgreSQL 18: CREATE ROLE](https://www.postgresql.org/docs/18/sql-createrole.html).

Hệ quả thiết kế là không dùng một thuộc tính mật khẩu để tuyên bố toàn bộ truy cập khẩn cấp sẽ tự kết thúc đúng giờ.

Đồng thời, nếu chọn khóa đăng nhập lúc không dùng, cần biết ai và bằng đường nào có thể mở nó khi chính đường quản trị thông thường đang lỗi.

## 7. Bảo quản credential và yếu tố khôi phục

### 7.1. Credential dự phòng vẫn cần vòng đời

Bản kiểm kê nên có:

- Principal và đích mà credential mở được.
- Owner vận hành và owner bảo mật.
- Nơi bảo quản.
- Người được yêu cầu, phê duyệt và lấy credential.
- Cách cấp hoặc thay giá trị.
- Lần kiểm tra khả dụng gần nhất.
- Những bản sao hoặc bản dự phòng được phép.
- Phương án khi nơi bảo quản không hoạt động.

Không ghi giá trị bí mật vào bảng kiểm kê.

### 7.2. Phân tách trách nhiệm thực tế

Với credential có hậu quả cao, có thể yêu cầu nhiều người phối hợp để mở quyền. Nhưng cần xét mọi đường khôi phục.

Nếu một người quản trị vault, email khôi phục, thiết bị xác thực và danh sách người phê duyệt, việc tách hai nút trên giao diện chưa tạo kiểm soát độc lập.

### 7.3. Không tạo bản sao khẩn cấp ngoài kiểm soát

Mật khẩu trong chat riêng, tài liệu cá nhân hoặc ảnh chụp màn hình có thể trở thành đường truy cập lâu dài không được giám sát.

Bản dự phòng được phép cần có vị trí, quyền truy cập, cách kiểm tra và cách thay sau khi sử dụng hoặc có nguy cơ bị lộ.

### 7.4. Không giả định MFA nằm ngay tại database

MFA có thể được thực thi tại một lớp truy cập trước database hoặc qua cơ chế xác thực mà hệ thống hỗ trợ. Cần kiểm tra đường kết nối trực tiếp có chịu cùng kiểm soát không.

Một đường khẩn cấp không qua gateway có thể có mô hình xác thực khác. Sự khác biệt này phải được đánh giá và phê duyệt trong thiết kế, không bị bỏ qua trong lúc sự cố.

## 8. Trách nhiệm khi kích hoạt

Một lần break-glass cần những trách nhiệm rõ ràng, dù tổ chức có thể gộp một số vai trò theo mức rủi ro.

| Trách nhiệm | Nội dung |
|---|---|
| Chỉ huy hoặc điều phối sự cố | Xác định ưu tiên, nhu cầu và phạm vi khẩn cấp |
| Người có thẩm quyền mở quyền | Kiểm tra điều kiện kích hoạt và giới hạn |
| Người thực hiện | Dùng quyền đúng mục đích và cập nhật kết quả |
| Người quan sát hoặc xác minh | Đối chiếu thao tác và trạng thái cuối |
| Owner database | Đánh giá tác động dữ liệu và vận hành |
| Owner PAM/bảo mật | Theo dõi cấp quyền, credential và thu hồi |

### 8.1. Chuẩn bị khi người duyệt chính không sẵn sàng

Quy trình nên định nghĩa trước người thay thế hoặc quyền kích hoạt khẩn cấp trong điều kiện cụ thể.

Rà soát sau sự kiện có thể bổ sung kiểm soát, nhưng không thay thế toàn bộ thẩm quyền trước hoặc trong lúc mở quyền. Không để người thực hiện tự tạo ra một ngoại lệ không giới hạn chỉ vì người duyệt chính vắng mặt.

### 8.2. Gia hạn là một quyết định mới

Khi chưa hoàn tất trong cửa sổ, cần đánh giá lại phạm vi, lý do và thời gian. Không âm thầm giữ principal hoạt động tới ca trực tiếp theo.

Nếu bàn giao người thực hiện, cập nhật liên kết danh tính và những credential đã được tiết lộ.

## 9. Runbook kích hoạt

### Bước 1: Xác nhận sự cố và nhu cầu

Ghi mã sự cố, tác động, đường thông thường đang lỗi và nhiệm vụ cần thực hiện. Xác định database có còn phục vụ được loại truy cập dự kiến không.

### Bước 2: Chọn đường đáng tin cậy

Đối chiếu với kịch bản đã chuẩn bị. Kiểm tra thiết bị, nguồn credential, mạng và cơ chế xác thực.

Nếu có dấu hiệu xâm nhập, đánh giá lại độ tin cậy trước khi cung cấp credential mạnh.

### Bước 3: Chốt phạm vi

Nêu instance hoặc cluster, database, môi trường, principal và hành động được phép.

Tên host hoặc nhãn môi trường đơn lẻ có thể gây nhầm. Dùng những định danh và dấu hiệu xác minh ổn định phù hợp nền tảng.

### Bước 4: Ghi thẩm quyền và thời hạn

Ghi người mở quyền, người thực hiện, cửa sổ, giới hạn và điều kiện dừng. Thông báo đúng người nhận theo kế hoạch.

### Bước 5: Chuẩn bị bằng chứng tối thiểu

Xác định log nào còn hoạt động, nơi lưu và cách ghi diễn biến khi một nguồn bị lỗi. Bảo vệ bằng chứng khỏi chính đường đặc quyền đang được sử dụng khi có thể.

### Bước 6: Cấp hoặc lấy truy cập

Thực hiện qua đường đã thiết kế. Liên kết lần cấp với danh tính cá nhân và mã sự cố.

Không đưa credential vào ticket, tham số dòng lệnh dễ bị thu thập hoặc bản ghi màn hình.

### Bước 7: Kiểm tra đích và quyền

Xác nhận đúng database, vai trò hiệu lực và phạm vi. Thực hiện kiểm tra không gây thay đổi trước khi làm tác vụ hậu quả cao.

### Bước 8: Thao tác, xác minh và cập nhật

Ghi rõ kết quả từng bước, điều kiện thay đổi và quyết định tiếp theo. Khi không chắc kết quả, đối soát trước khi retry.

### Bước 9: Chuyển sang quy trình đóng

Ngay khi nhu cầu khẩn cấp kết thúc, xử lý quyền, phiên, credential và trạng thái dữ liệu. Không chờ hoàn tất toàn bộ báo cáo sự cố mới bắt đầu đóng khả năng truy cập.

## 10. Mẫu kế hoạch một lần sử dụng

Ví dụ sau là mô hình tài liệu nội bộ, không phải cấu hình của một sản phẩm:

~~~yaml
request_id: INC-LAB-042
purpose: Diagnose and stop one verified blocking query
target:
  environment: training
  database_cluster: payments-lab-cluster
  database: payments_lab
access:
  identity_path: approved-emergency-path
  window_minutes: 30
  allowed_actions:
    - inspect_session_metadata
    - cancel_verified_query
  excluded_actions:
    - bulk_data_export
    - unrestricted_dml
    - schema_change
    - role_delegation
verification:
  - confirm_target_and_execution_identity
  - record_approved_session_identifiers
  - verify_service_health_after_action
closure:
  - stop_new_emergency_access
  - reconcile_existing_sessions
  - restore_credential_and_network_posture
  - review_changes_and_remaining_exceptions
~~~

Các tên và thời hạn chỉ mang tính minh họa. Việc ghi allowed_actions trong tài liệu không tự làm database từ chối hành động khác; cần cơ chế thực thi và giám sát tương ứng.

## 11. Ví dụ quan sát phiên trong PostgreSQL

Các câu SQL dưới đây chỉ minh họa truy vấn chẩn đoán được phép. Bài học không kết nối database thật hoặc thực thi lệnh quản trị.

### 11.1. Kiểm tra ngữ cảnh kết nối

~~~sql
SELECT
    session_user,
    current_user,
    current_database(),
    inet_server_addr(),
    inet_server_port(),
    pg_backend_pid();
~~~

Cần đối chiếu kết quả với định danh hệ thống được quản lý. Địa chỉ có thể không đủ để xác định tài nguyên cloud hoặc môi trường phía sau proxy.

Nếu ngữ cảnh không khớp kế hoạch, dừng và xác minh thay vì tiếp tục chỉ vì kết nối đã thành công.

### 11.2. Quan sát metadata của danh tính khẩn cấp

~~~sql
SELECT
    pid,
    backend_start,
    usename,
    datname,
    application_name,
    client_addr,
    state,
    xact_start,
    wait_event_type,
    wait_event
FROM pg_stat_activity
WHERE usename = 'bg_example_operator'
ORDER BY backend_start;
~~~

Tên role là ví dụ. Quyền và độ đầy đủ thông tin quan sát phụ thuộc danh tính thực hiện. pg_stat_activity là nguồn quan sát hoạt động hiện tại, không phải bản lưu lịch sử kiểm toán đầy đủ. [PostgreSQL 18: pg_stat_activity](https://www.postgresql.org/docs/18/monitoring-stats.html#MONITORING-PG-STAT-ACTIVITY-VIEW).

Ví dụ không xuất toàn bộ query text vì nó có thể chứa dữ liệu hoặc tham số nhạy cảm.

### 11.3. Không dùng một PID cũ làm bằng chứng duy nhất

Trước hành động trên phiên, đối chiếu lại thời điểm khởi tạo, người đăng nhập, database và trạng thái liên quan. Một định danh tiến trình có thể không đủ để nhận diện cùng một phiên qua thời gian.

application_name hữu ích cho tương quan nhưng không tự là chứng cứ danh tính cá nhân đáng tin cậy.

### 11.4. Cancel khác terminate

Trong PostgreSQL, pg_cancel_backend nhằm hủy query hiện tại; pg_terminate_backend nhằm kết thúc session. Các hàm có điều kiện quyền riêng. Với terminate không chờ timeout dương, giá trị trả về có thể chỉ phản ánh việc gửi tín hiệu, nên cần xác minh trạng thái sau đó. [Server Signaling Functions](https://www.postgresql.org/docs/18/functions-admin.html#FUNCTIONS-ADMIN-SIGNAL).

Không thay cancel bằng terminate một cách máy móc. Cần đánh giá transaction, lock, retry ứng dụng và tác động dịch vụ.

Bài không đưa lệnh kết thúc hàng loạt phiên. Việc xử lý phải nhắm đúng đối tượng đã được xác minh.

## 12. Thực thi có giới hạn trong lúc sự cố

### 12.1. Ưu tiên hành động giải quyết nguyên nhân đã xác định

Nếu mục tiêu là xử lý một query gây nghẽn, không dùng khoảng quyền đó để sửa role, chạy migration hoặc xuất dữ liệu “cho tiện điều tra”.

Mỗi thay đổi ngoài kế hoạch cần được đánh giá và ghi nhận theo thẩm quyền khẩn cấp đã định nghĩa.

### 12.2. DML và DDL cần kế hoạch riêng

Sửa hoặc xóa dữ liệu có thể cần xác nhận đối tượng, điều kiện trạng thái, transaction và kiểm tra hậu quả. Thay đổi cấu trúc có thể tạo lock hoặc ảnh hưởng ứng dụng.

Không kết luận thao tác an toàn chỉ vì được thực hiện bởi DBA. Quyền kỹ thuật và tính đúng đắn của thay đổi là hai vấn đề khác nhau.

### 12.3. Không lấy tắt kiểm soát làm phản xạ mặc định

Thay đổi xác thực hoặc hàng rào mạng có thể mở một phạm vi lớn hơn công việc cần làm.

Trong PostgreSQL, cấu hình pg_hba.conf tham gia chọn phương thức xác thực theo connection và quy tắc khớp. Thứ tự rule có ý nghĩa. [The pg_hba.conf File](https://www.postgresql.org/docs/18/auth-pg-hba-conf.html).

Nếu runbook thật sự cần đổi một kiểm soát, phải có phạm vi hẹp, bằng chứng cấu hình trước/sau, phương án phục hồi và kiểm tra đường không được phép. Không mở xác thực rộng như một bước mặc định của break-glass.

### 12.4. Timeout là kết quả chưa rõ cho tới khi đối soát

Một thao tác có thể đã hoàn tất nhưng client không nhận được phản hồi. Chạy lại có thể gây tác động lần hai.

Cần đối chiếu trạng thái database, mã tác vụ và dữ liệu liên quan trước khi quyết định retry. Với thay đổi có tác động bên ngoài, phải đối soát cả bên nhận.

## 13. Khi hệ thống audit hoặc PAM bị suy giảm

### 13.1. Chuẩn bị chế độ vận hành suy giảm

Runbook cần xác định trước:

- Điều gì còn được thực hiện khi nguồn audit chính lỗi.
- Những hành động phải dừng vì không đủ khả năng xác minh.
- Bằng chứng thay thế được thu thập ở đâu.
- Ai có thẩm quyền chấp nhận mức quan sát còn lại.
- Khi nào phải chuyển cấp hoặc dừng.

Đây là quyết định thiết kế theo rủi ro, không phải lựa chọn tự phát của người đang cầm credential.

### 13.2. Bằng chứng thay thế cần được bảo vệ

Có thể cần nhật ký thao tác được ký xác nhận, người quan sát độc lập hoặc nguồn log nền tảng còn hoạt động. Phải bảo vệ quyền đọc/ghi và liên kết với sự kiện.

Không ghi credential hoặc toàn bộ dữ liệu khách hàng vào bản ghi tạm.

### 13.3. Log câu lệnh có thể chứa bí mật

PostgreSQL có nhiều tùy chọn về điểm nhận và nội dung log. Cần cấu hình, kiểm tra độ bao phủ và bảo vệ dữ liệu được ghi. [Error Reporting and Logging](https://www.postgresql.org/docs/18/runtime-config-logging.html).

Ghi mọi statement không tự tạo bằng chứng hoàn hảo và có thể làm lộ literal hoặc tham số. Một hình ảnh màn hình cũng không chứng minh không có hoạt động qua connection khác.

### 13.4. Không che lấp khoảng trống

Nếu một khoảng hoạt động không có đủ bằng chứng, báo cáo phải nêu rõ thời gian, phạm vi và các nguồn còn lại. Không dựng lại nhật ký như thể nó được thu thập trực tiếp tại thời điểm đó.

Có thể phân biệt bản ghi trực tiếp, hồi dựng từ nhiều nguồn và lời tường trình sau sự kiện.

## 14. Quy trình đóng quyền khẩn cấp

Việc đóng cần được điều phối theo khả năng của hệ thống, tránh tự khóa đường khôi phục trước khi có phương án kết thúc.

### Bước 1: Xác nhận không còn nhu cầu đặc quyền

Owner sự cố và owner database xác định công việc nào đã hoàn tất, phần nào còn chạy và ai tiếp tục theo dõi.

### Bước 2: Ngăn cấp hoặc sử dụng mới ngoài kế hoạch

Đóng yêu cầu hoặc khả năng kích hoạt mới, xử lý quyền và đường mạng tạm thời theo thiết kế.

Đóng checkout trong vault không làm người đã biết mật khẩu tự mất kiến thức về mật khẩu đó.

### Bước 3: Kiểm kê phiên và transaction

Xác định connection liên quan, quyền hiệu lực và transaction còn mở hoặc chưa rõ kết quả.

Không tự kết thúc mọi connection chung một database. Chọn đối tượng và hành động theo tác động đã đánh giá.

### Bước 4: Xử lý quyền và phiên hiện có

Thu hồi grant, membership hoặc khả năng đặc biệt đúng phạm vi. Kết thúc hoặc bàn giao những phiên cần thiết theo runbook.

Không suy rằng NOLOGIN, hết hạn mật khẩu hoặc đổi credential tự đóng mọi session đã xác thực trước đó.

### Bước 5: Xử lý credential đã được tiết lộ

Nếu một bí mật dài hạn đã được cung cấp cho người dùng hoặc có nguy cơ lộ, thay và xác minh theo chính sách. Đánh giá bản sao ở công cụ, profile và nơi lưu tạm.

Credential tạm thời cần được đóng hoặc theo dõi tới trạng thái hết hiệu lực có thể chứng minh. Không chỉ xóa giá trị khỏi giao diện PAM.

### Bước 6: Phục hồi cấu hình bảo vệ

Đối chiếu cấu hình mạng, xác thực, logging, role và các ngoại lệ với trạng thái mong muốn. Kiểm tra automation không tạo lại đường truy cập đã đóng.

### Bước 7: Đối soát dữ liệu và hậu quả

Thu hồi không hoàn tác DML đã commit, role đã cấp cho người khác hoặc dữ liệu đã xuất. Mỗi hậu quả cần có kết quả hoặc owner xử lý.

### Bước 8: Xác minh độc lập và đóng hồ sơ

Người xác minh đối chiếu kế hoạch với hoạt động thực tế, ghi phần chưa rõ và chỉ đóng khi đáp ứng tiêu chí đã đặt ra.

## 15. Tiêu chí kết thúc có thể kiểm chứng

| Tiêu chí | Bằng chứng phù hợp |
|---|---|
| Nhu cầu khẩn cấp đã kết thúc | Xác nhận và trạng thái công việc |
| Không cấp lại ngoài thẩm quyền | Trạng thái hệ thống cấp và phép kiểm tra được phép |
| Quyền tạm thời đã xử lý | Grant, membership, thuộc tính và kết quả kiểm tra |
| Phiên còn lại có trạng thái rõ | Metadata phiên và kết quả xử lý |
| Credential đã được xử lý | ID phiên bản, kết quả thay hoặc hết hiệu lực |
| Cấu hình bảo vệ đã phục hồi | Chênh lệch cấu hình và kiểm thử đường truy cập |
| Không bỏ quên quyền phát sinh | Đối soát danh tính, grant và tác vụ được tạo |
| Trạng thái dữ liệu đã xác minh | Kiểm tra kết quả hoặc kế hoạch xử lý ngoại lệ |
| Bằng chứng được bảo vệ | Nơi lưu, quyền truy cập và thông tin nguồn |
| Ngoại lệ được quản lý | Owner, lý do và hạn xử lý |

Không cần đưa giá trị credential vào hồ sơ để chứng minh các điều kiện này.

## 16. Tình huống: SSO lỗi và dịch vụ bị nghẽn

Một ứng dụng thanh toán bị tăng độ trễ. Đội trực xác định có dấu hiệu chờ khóa trong database, nhưng SSO không hoạt động nên không mở được đường quản trị bình thường.

### 16.1. Quyết định kích hoạt

Người điều phối xác nhận tác động và kích hoạt một đường khẩn cấp đã được diễn tập. Phạm vi ban đầu là quan sát metadata và xử lý một query đã được xác minh, không sửa dữ liệu hoặc quản lý role.

Credential được lấy qua cơ chế dự phòng còn đáng tin cậy, có liên kết cá nhân và thông báo cho người quan sát.

### 16.2. Xác minh trước tác động

Người thực hiện kiểm tra đúng cluster và database, xác nhận danh tính hiệu lực, đối chiếu phiên nghi gây chặn và tác động dự kiến.

Nếu dữ kiện không chứng minh query đó là nguyên nhân, cần tiếp tục chẩn đoán hoặc chuyển cấp; không kết thúc phiên chỉ vì nó có thời gian chạy dài.

### 16.3. Thực hiện và kiểm tra sau đó

Áp dụng hành động phù hợp với quyền đã duyệt. Kiểm tra trạng thái phiên, transaction, lock và sức khỏe ứng dụng sau thay đổi.

Nếu có retry hoặc kết quả chưa rõ, ghi nhận và đối soát. Không xem một phản hồi boolean từ công cụ quản trị là bằng chứng duy nhất rằng dịch vụ đã phục hồi.

### 16.4. Đóng quyền

Khi đường quản trị bình thường phục hồi và không còn nhiệm vụ khẩn cấp, ngăn cấp mới, xử lý session, thay credential nếu đã tiết lộ và kiểm tra cấu hình tạm.

Một báo cáo phù hợp có thể là:

> Đã xử lý query được xác minh và xác nhận độ trễ giảm. Quyền khẩn cấp đã được đóng theo kế hoạch, các connection liên quan đã có trạng thái rõ. Credential dài hạn đã được thay và kiểm tra. Hồ sơ còn mở để rà soát nguyên nhân SSO và bổ sung một nguồn bằng chứng bị gián đoạn.

Không ghi “mọi truy cập đã bị thu hồi” nếu còn một lớp chưa xác minh.

## 17. Diễn tập và kiểm tra định kỳ

### 17.1. Kiểm tra theo kịch bản lỗi

Không chỉ kiểm tra mật khẩu đăng nhập được. Cần diễn tập:

- IdP không khả dụng.
- PAM hoặc vault chính lỗi.
- Người duyệt chính vắng mặt.
- Mạng hoặc DNS quản trị có sự cố.
- Credential hoặc yếu tố xác thực dự phòng không dùng được.
- Nghi thiết bị quản trị bị chiếm.
- Nguồn audit chính gián đoạn.
- Mất phản hồi khi thực hiện thao tác.
- Không thể đóng một session theo cách dự kiến.
- Automation tạo lại một quyền đã thu hồi.

### 17.2. Dùng môi trường và dữ liệu phù hợp

Thử tác vụ hậu quả cao trong môi trường mô phỏng hoặc theo kế hoạch được phê duyệt. Không dùng credential sản xuất trong tài liệu hướng dẫn hoặc ghi hình công khai.

Kiểm thử cũng cần thu hồi và xử lý bí mật sau khi dùng.

### 17.3. Đo cả khả năng mở và khả năng đóng

Các chỉ số hữu ích gồm:

- Thời gian tiếp cận đường khẩn cấp.
- Thời gian xác định đúng đích và quyền.
- Tỷ lệ lần diễn tập có đủ bằng chứng.
- Thời gian ngăn cấp mới và xử lý phiên.
- Số credential hoặc ngoại lệ quá hạn.
- Số quyền phát sinh không có kế hoạch.
- Thời gian hoàn thành rà soát sau sự kiện.

Một đường mở rất nhanh nhưng không đóng được không đáp ứng đầy đủ mục tiêu PAM.

## 18. Những lỗi thường gặp

| Lỗi | Hệ quả | Cách cải thiện |
|---|---|---|
| Chỉ giữ một mật khẩu mạnh | Bỏ sót đường mạng, IdP và khôi phục | Vẽ và kiểm thử mối phụ thuộc |
| Vault dự phòng vẫn cần cùng IdP đang lỗi | Không dùng được khi cần | Thiết kế theo kịch bản lỗi |
| Cấp superuser cho mọi nhiệm vụ | Tăng hậu quả sai sót | Chuẩn bị năng lực theo nhiệm vụ |
| Chia sẻ credential cho cả ca trực | Khó quy trách nhiệm và thu hồi | Liên kết cá nhân và kiểm soát tiết lộ |
| Ghi secret trong ticket | Tạo nguồn lộ lâu dài | Chỉ lưu metadata cần thiết |
| Coi MFA gateway bao phủ đường trực tiếp | Bỏ sót khác biệt xác thực | Kiểm tra mọi đường kết nối |
| Dùng hết hạn mật khẩu làm thời hạn quyền | Có thể còn role hoặc session | Tách các vòng đời |
| Tắt xác thực rộng để vào nhanh | Mở thêm bề mặt tấn công | Dùng đường đã chuẩn bị và phạm vi hẹp |
| Dừng mọi phiên đang chạy lâu | Gây gián đoạn hoặc rollback ngoài ý muốn | Xác minh đúng đối tượng và tác động |
| Coi gửi tín hiệu là xử lý xong | Bỏ sót trạng thái thực | Kiểm tra sau thao tác |
| Đóng yêu cầu PAM nhưng giữ session | Còn khả năng đặc quyền | Đối soát phiên và quyền |
| Đổi mật khẩu rồi bỏ qua dữ liệu đã sửa | Thiếu xử lý hậu quả | Kiểm tra commit và trạng thái cuối |
| Không có nguồn audit thay thế | Mất khả năng giải thích hoạt động | Chuẩn bị vận hành suy giảm |
| Chỉ rà soát khi có sự cố thật | Runbook và credential có thể lỗi thời | Diễn tập và cập nhật owner |

## 19. Thực hành

### Bài tập 1: Kiểm tra vòng phụ thuộc

Credential khẩn cấp nằm trong vault chỉ mở bằng SSO. SSO lại phụ thuộc dịch vụ đang có database cần khôi phục.

Hãy vẽ vòng phụ thuộc, xác định kịch bản không đáp ứng và đề xuất một đường dự phòng có kiểm soát. Nêu cách kiểm thử và bảo vệ đường đó.

### Bài tập 2: Chia quyền theo nhiệm vụ

Đội trực cần quan sát phiên và xử lý một query gây chặn. Họ không cần đọc toàn dữ liệu hoặc quản lý role.

Hãy lập phạm vi năng lực và bằng chứng cần có. Giải thích vì sao dùng tài khoản quản trị toàn quyền làm mặc định khó đáp ứng least privilege.

### Bài tập 3: Mật khẩu hết hạn nhưng session còn mở

Một principal dùng xác thực mật khẩu có thời hạn đã hết, nhưng connection khẩn cấp được mở trước đó vẫn cần được đánh giá.

Hãy phân biệt xác thực mới, quyền của role, session và transaction. Thiết kế quy trình đóng mà không dựa vào một thuộc tính thời hạn duy nhất.

### Bài tập 4: Audit chính lỗi

Trong một lần break-glass, nguồn log tập trung không hoạt động nhưng có log nền tảng và người quan sát.

Hãy xác định hành động còn được phép theo chính sách giả định, bằng chứng thay thế và cách báo cáo khoảng trống. Không đưa credential hoặc dữ liệu khách hàng vào biên bản.

### Bài tập 5: Kết quả thao tác chưa rõ

Công cụ báo đã gửi yêu cầu kết thúc phiên, nhưng ứng dụng chưa phục hồi và có transaction cần đối soát.

Hãy viết các bước xác minh trước khi làm tiếp. Phân biệt thành công gửi yêu cầu, session thực sự kết thúc và nguyên nhân dịch vụ đã được xử lý.

## 20. Điểm cần ghi nhớ

Database break-glass là một năng lực khôi phục được chuẩn bị và kiểm soát, không chỉ là một tài khoản mạnh. Nó phải hoạt động trong kịch bản cần thiết, giới hạn đúng nhiệm vụ và bảo vệ được danh tính lẫn bằng chứng.

Một lần sử dụng chỉ hoàn tất khi đã xử lý nhu cầu khẩn cấp, quyền và phiên liên quan có trạng thái rõ, credential được quản lý lại và hậu quả dữ liệu được đối soát. Khả năng đóng và chứng minh kết thúc quan trọng như khả năng mở truy cập.
