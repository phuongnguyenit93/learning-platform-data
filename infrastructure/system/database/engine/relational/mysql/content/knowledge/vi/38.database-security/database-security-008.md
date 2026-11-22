# Password policy, khóa tài khoản, hết hạn và luân chuyển mật khẩu

Trong MySQL, bảo vệ tài khoản bằng mật khẩu gồm nhiều lớp phối hợp: kiểm tra chất lượng mật khẩu, ngăn dùng lại mật khẩu cũ, đặt thời hạn sử dụng, khóa đăng nhập sau nhiều lần xác thực thất bại và luân chuyển thông tin xác thực khi cần. Mỗi lớp giải quyết một rủi ro khác nhau. Chỉ bật một chính sách độ phức tạp không thể thay thế việc giới hạn quyền, mã hóa kết nối, quản lý bí mật và theo dõi hoạt động đăng nhập.

Bài học này thuộc module **DATABASE_MYSQL**, tập trung vào quản trị MySQL trong môi trường thực tế: cấu hình có kiểm soát, áp dụng chính sách theo từng loại tài khoản, xác minh trạng thái và xử lý tình huống vận hành. Các ví dụ dùng cú pháp MySQL 8.0. Một số tính năng có mốc phiên bản riêng; hãy kiểm tra phiên bản máy chủ trước khi triển khai.

## 1. Phân biệt các cơ chế quản lý mật khẩu

| Cơ chế | Câu hỏi được giải quyết | Công cụ MySQL |
|---|---|---|
| Độ mạnh mật khẩu | Mật khẩu có đủ dài và khó đoán không? | Thành phần **validate_password** |
| Lịch sử và tái sử dụng | Người dùng có đang quay lại mật khẩu cũ không? | **password_history**, **password_reuse_interval** |
| Mật khẩu hiện tại | Khi đổi mật khẩu, người dùng có phải xác nhận mật khẩu hiện tại không? | **password_require_current** |
| Hết hạn | Mật khẩu cần được thay sau bao lâu? | **default_password_lifetime**, **PASSWORD EXPIRE** |
| Khóa do đăng nhập sai | Tài khoản cần bị khóa sau bao nhiêu lần xác thực thất bại? | **FAILED_LOGIN_ATTEMPTS**, **PASSWORD_LOCK_TIME** |
| Khóa quản trị | Tài khoản có cần bị vô hiệu hóa đăng nhập ngay lập tức không? | **ACCOUNT LOCK**, **ACCOUNT UNLOCK** |
| Luân chuyển | Làm thế nào thay bí mật mà giảm gián đoạn ứng dụng? | **ALTER USER**, cơ chế dual password |

Các cơ chế này không đồng nghĩa với nhau. Mật khẩu hết hạn yêu cầu người dùng đổi mật khẩu; khóa tài khoản ngăn đăng nhập; còn luân chuyển là quy trình thay bí mật và cập nhật các hệ thống đang sử dụng bí mật đó.

### Khác biệt phiên bản cần biết

- Chính sách lịch sử mật khẩu và yêu cầu mật khẩu hiện tại được hỗ trợ trong dòng MySQL 8.0; khả năng cấu hình ở cấp tài khoản phụ thuộc phiên bản cụ thể.
- Dual password được hỗ trợ từ MySQL 8.0.14.
- **FAILED_LOGIN_ATTEMPTS** và **PASSWORD_LOCK_TIME** được hỗ trợ từ MySQL 8.0.19.
- MySQL 8.0 hỗ trợ thành phần **component_validate_password**; các bản cũ hơn có thể sử dụng plugin **validate_password**. Cách cài đặt và quản lý hai dạng này khác nhau.

Trên máy chủ đang chạy, kiểm tra trước:

~~~sql
SELECT VERSION();
SHOW VARIABLES LIKE 'default_password_lifetime';
SHOW VARIABLES LIKE 'password_history';
SHOW VARIABLES LIKE 'password_reuse_interval';
SHOW VARIABLES LIKE 'password_require_current';
SHOW VARIABLES LIKE 'validate_password%';
~~~

Không giả định mọi biến hoặc tùy chọn đều tồn tại trên mọi bản MySQL. Nếu câu lệnh báo biến không tồn tại hoặc cú pháp không được hỗ trợ, đối chiếu tài liệu đúng phiên bản và chính sách nâng cấp của hệ thống.

## 2. Thiết lập yêu cầu về độ mạnh mật khẩu

Thành phần **validate_password** kiểm tra mật khẩu khi tạo tài khoản hoặc đổi mật khẩu. Nó có thể kiểm tra độ dài, chữ hoa, chữ thường, chữ số, ký tự đặc biệt và từ điển. Thành phần này giúp từ chối mật khẩu yếu, nhưng không thể tự bảo đảm mật khẩu là duy nhất giữa các dịch vụ hoặc bí mật chưa từng bị lộ.

Với MySQL 8.0, có thể cài thành phần bằng câu lệnh sau nếu máy chủ chưa cài:

~~~sql
INSTALL COMPONENT 'file://component_validate_password';
~~~

Kiểm tra các thiết lập hiện tại:

~~~sql
SHOW VARIABLES LIKE 'validate_password%';
~~~

Ví dụ cấu hình chính sách mạnh:

~~~sql
SET PERSIST validate_password.policy = 'STRONG';
SET PERSIST validate_password.length = 14;
SET PERSIST validate_password.mixed_case_count = 1;
SET PERSIST validate_password.number_count = 1;
SET PERSIST validate_password.special_char_count = 1;
SET PERSIST validate_password.check_user_name = ON;
~~~

Ý nghĩa của các tham số:

- **validate_password.policy** chọn mức **LOW**, **MEDIUM** hoặc **STRONG**. Mức **STRONG** bổ sung kiểm tra từ điển khi đã cấu hình tệp từ điển.
- **validate_password.length** đặt độ dài tối thiểu.
- **mixed_case_count**, **number_count** và **special_char_count** quy định số lượng tối thiểu của các nhóm ký tự tương ứng.
- **check_user_name** yêu cầu mật khẩu không chứa tên tài khoản theo quy tắc kiểm tra của thành phần.

Các giá trị trên chỉ là ví dụ khởi điểm. Tổ chức cần cân nhắc khả năng tương thích của ứng dụng, phương thức nhập mật khẩu và yêu cầu bảo mật. Một mật khẩu dài, duy nhất, được sinh ngẫu nhiên hoặc một cụm mật khẩu đủ dài thường có giá trị hơn việc ép người dùng thay đổi ký tự theo một mẫu dễ đoán.

**SET GLOBAL** thay đổi giá trị trong thời gian máy chủ đang chạy nhưng không tự lưu cấu hình qua lần khởi động tiếp theo. **SET PERSIST** lưu giá trị để MySQL nạp lại sau khi khởi động. Trong môi trường được quản lý bằng cấu hình hạ tầng, nên thay đổi cấu hình tại nguồn quản lý chuẩn, ghi nhận người phê duyệt và kiểm tra trạng thái sau khi triển khai. Không chạy các câu lệnh thay đổi toàn cục trực tiếp trên production nếu chưa đánh giá tác động.

Nếu dùng bản MySQL cũ với plugin thay vì component, hãy làm theo hướng dẫn cài plugin tương ứng với hệ điều hành và phiên bản. Không cài component và plugin theo hai hướng dẫn trộn lẫn.

## 3. Ngăn tái sử dụng mật khẩu

Nếu người dùng có thể đổi qua lại giữa một vài mật khẩu quen thuộc, chính sách hết hạn sẽ giảm hiệu quả. MySQL cung cấp hai cơ chế để giới hạn việc này:

- Lịch sử mật khẩu: từ chối một số mật khẩu gần nhất đã dùng.
- Khoảng thời gian tái sử dụng: từ chối mật khẩu đã dùng trong một khoảng thời gian nhất định.

Có thể đặt mặc định toàn máy chủ:

~~~sql
SET PERSIST password_history = 5;
SET PERSIST password_reuse_interval = 365;
SET PERSIST password_require_current = ON;
~~~

Ví dụ áp dụng chính sách tường minh cho một tài khoản:

~~~sql
CREATE USER 'analyst'@'10.20.%'
  IDENTIFIED BY 'REPLACE_WITH_A_SECRET'
  PASSWORD HISTORY 5
  PASSWORD REUSE INTERVAL 365 DAY
  PASSWORD REQUIRE CURRENT;
~~~

Tên tài khoản, host và giá trị chính sách phải được điều chỉnh theo hệ thống. Chuỗi mật khẩu trong ví dụ chỉ là chỗ giữ chỗ, không phải mật khẩu để triển khai. Không đưa bí mật thật vào mã nguồn, tài liệu, ticket hoặc lịch sử lệnh dùng chung.

**PASSWORD REQUIRE CURRENT** yêu cầu cung cấp mật khẩu hiện tại khi thay đổi mật khẩu theo cơ chế mà máy khách và máy chủ hỗ trợ. Có thể dùng **PASSWORD REQUIRE CURRENT OPTIONAL** hoặc **PASSWORD REQUIRE CURRENT DEFAULT** để chọn hành vi khác theo nhu cầu. Tùy chọn này cần được kiểm tra với luồng đổi mật khẩu của ứng dụng; một ứng dụng tự động đổi mật khẩu có thể không có ngữ cảnh mật khẩu hiện tại.

Chính sách lịch sử không thay thế việc tạo mật khẩu đủ mạnh. Nó cũng không làm cho một bí mật đã bị lộ trở nên an toàn. Khi nghi ngờ lộ mật khẩu, phải thay ngay và rà soát nơi bí mật đã được lưu hoặc sử dụng.

## 4. Đặt thời hạn mật khẩu

Biến toàn cục **default_password_lifetime** quy định thời hạn mặc định tính theo ngày. Giá trị **0** nghĩa là mật khẩu không tự hết hạn theo mặc định. Ví dụ, đặt mặc định 180 ngày:

~~~sql
SET PERSIST default_password_lifetime = 180;
~~~

Có thể đặt thời hạn riêng khi tạo hoặc sửa tài khoản:

~~~sql
CREATE USER 'report_reader'@'10.20.%'
  IDENTIFIED BY 'REPLACE_WITH_A_SECRET'
  PASSWORD EXPIRE INTERVAL 90 DAY;

ALTER USER 'report_reader'@'10.20.%'
  PASSWORD EXPIRE INTERVAL 90 DAY;
~~~

Ba lựa chọn thường gặp:

~~~sql
-- Theo thời hạn mặc định của máy chủ
ALTER USER 'report_reader'@'10.20.%' PASSWORD EXPIRE DEFAULT;

-- Không tự hết hạn mật khẩu của tài khoản này
ALTER USER 'service_worker'@'10.20.%' PASSWORD EXPIRE NEVER;

-- Đánh dấu mật khẩu hết hạn ngay
ALTER USER 'temporary_user'@'localhost' PASSWORD EXPIRE;
~~~

Tài khoản có **PASSWORD EXPIRE NEVER** không bị thời hạn mặc định của máy chủ chi phối. Vì vậy, khi đặt chính sách toàn cục, cần rà soát các ngoại lệ ở cấp tài khoản. Không nên vô tình đặt **NEVER** cho tài khoản người dùng có quyền cao.

Hết hạn mật khẩu có thể gây gián đoạn nếu tài khoản được dùng bởi ứng dụng, tác vụ nền, connection pool hoặc quy trình sao lưu. Trước khi áp dụng, xác định chủ sở hữu tài khoản, nơi lưu bí mật, quy trình cập nhật và cách kiểm tra kết nối sau khi đổi. Tài khoản dịch vụ cần quy trình luân chuyển có điều phối; đặt một chu kỳ hết hạn ngắn mà không có quy trình cập nhật bí mật thường làm hệ thống ngừng hoạt động.

## 5. Khóa tài khoản sau nhiều lần đăng nhập sai

Từ MySQL 8.0.19, có thể cấu hình số lần xác thực thất bại liên tiếp trước khi tự khóa tài khoản và khoảng thời gian khóa tính theo ngày.

~~~sql
CREATE USER 'app_login'@'10.20.%'
  IDENTIFIED BY 'REPLACE_WITH_A_SECRET'
  FAILED_LOGIN_ATTEMPTS 5
  PASSWORD_LOCK_TIME 1;

ALTER USER 'app_login'@'10.20.%'
  FAILED_LOGIN_ATTEMPTS 5
  PASSWORD_LOCK_TIME 1;
~~~

Trong ví dụ, tài khoản bị khóa sau năm lần đăng nhập sai liên tiếp và thời gian khóa là một ngày. Giá trị **PASSWORD_LOCK_TIME** được tính bằng ngày. Dùng **UNBOUNDED** nếu tài khoản phải được quản trị viên mở khóa thủ công:

~~~sql
ALTER USER 'sensitive_admin'@'10.20.%'
  FAILED_LOGIN_ATTEMPTS 3
  PASSWORD_LOCK_TIME UNBOUNDED;
~~~

Khóa do đăng nhập sai khác với khóa quản trị chủ động. Khi cần ngăn đăng nhập mới ngay lập tức, quản trị viên có thể khóa tài khoản:

~~~sql
ALTER USER 'app_login'@'10.20.%' ACCOUNT LOCK;
~~~

Mở khóa sau khi đã xác minh nguyên nhân:

~~~sql
ALTER USER 'app_login'@'10.20.%' ACCOUNT UNLOCK;
~~~

Khóa tài khoản ngăn các lần xác thực mới. Nó không tự động kết thúc những kết nối đã được thiết lập trước đó. Nếu cần chặn cả phiên đang tồn tại, phải xác định và xử lý các kết nối đó riêng theo quy trình vận hành, đồng thời cân nhắc ảnh hưởng đến giao dịch đang chạy.

Thiết lập ngưỡng quá thấp có thể khiến người dùng hợp lệ bị khóa do nhập sai hoặc khiến kẻ tấn công cố tình gây gián đoạn bằng cách làm tài khoản bị khóa. Chọn ngưỡng và thời gian khóa dựa trên mức độ nhạy cảm của tài khoản, mô hình đăng nhập, khả năng hỗ trợ người dùng và cơ chế cảnh báo. Với tài khoản quản trị quan trọng, cần có quy trình mở khóa khẩn cấp được kiểm soát.

## 6. Luân chuyển mật khẩu an toàn

Luân chuyển mật khẩu là quá trình thay một bí mật đang được sử dụng bằng bí mật mới, cập nhật nơi lưu trữ và xác minh mọi thành phần phụ thuộc. Các tình huống thường cần luân chuyển gồm:

- Bí mật đến kỳ thay theo chính sách nội bộ.
- Nhân sự sở hữu hoặc quản lý bí mật thay đổi vai trò.
- Có dấu hiệu bí mật bị lộ, bị chia sẻ sai nơi hoặc xuất hiện trong log.
- Ứng dụng, môi trường hoặc nhà cung cấp dịch vụ thay đổi.

Với tài khoản người dùng, nên xác thực người yêu cầu và dùng luồng đổi mật khẩu được tổ chức phê duyệt. Với tài khoản dịch vụ, cần phối hợp cập nhật secret manager, cấu hình ứng dụng, connection pool, tác vụ nền và các bản triển khai liên quan.

### Dùng dual password để giảm gián đoạn

Từ MySQL 8.0.14, một tài khoản có thể tạm thời giữ mật khẩu hiện tại và mật khẩu mới. Cách này hữu ích khi cần cập nhật bí mật ở nhiều ứng dụng mà không thể chuyển đồng thời.

**Bước 1: đặt mật khẩu mới và giữ mật khẩu hiện tại**

~~~sql
ALTER USER 'app_login'@'10.20.%'
  IDENTIFIED BY 'NEW_SECRET_FROM_SECRET_MANAGER'
  RETAIN CURRENT PASSWORD;
~~~

**Bước 2: cập nhật secret manager và triển khai ứng dụng**

Đưa bí mật mới vào kho bí mật được phê duyệt, cập nhật cấu hình của các instance ứng dụng, khởi tạo lại hoặc làm mới connection pool theo quy trình, sau đó kiểm tra đăng nhập và truy vấn cần thiết. Theo dõi lỗi xác thực để tìm instance còn dùng bí mật cũ.

**Bước 3: loại bỏ mật khẩu cũ sau khi xác minh**

~~~sql
ALTER USER 'app_login'@'10.20.%' DISCARD OLD PASSWORD;
~~~

Sau lệnh này, mật khẩu cũ không còn được chấp nhận. Chỉ thực hiện khi đã xác minh mọi thành phần phụ thuộc đã chuyển sang mật khẩu mới và có phương án xử lý nếu kiểm tra thất bại.

Dual password là cửa sổ chuyển đổi tạm thời, không phải lý do để giữ nhiều bí mật lâu dài. Giới hạn thời gian chuyển đổi, ghi lại người thực hiện và đóng cửa sổ bằng **DISCARD OLD PASSWORD**.

### Luân chuyển khẩn cấp khi nghi ngờ lộ bí mật

Khi bí mật bị lộ, ưu tiên ngăn truy cập trái phép và thay bí mật càng sớm càng tốt. Tùy mức độ sự cố, có thể khóa tài khoản trước, xác định các phiên đang hoạt động, cập nhật bí mật ở nguồn quản lý, đổi mật khẩu, triển khai cấu hình mới và mở lại tài khoản sau khi xác minh. Nếu cần duy trì dịch vụ, lập kế hoạch chuyển đổi có kiểm soát và rút ngắn tối đa thời gian mật khẩu cũ còn hiệu lực.

Không chỉ đổi mật khẩu rồi kết thúc sự cố. Cần kiểm tra log đăng nhập, địa chỉ nguồn, thời điểm, quyền của tài khoản, các truy vấn bất thường và nơi bí mật có thể đã bị lộ. Nếu tài khoản có quyền quá rộng, thu hẹp quyền theo nguyên tắc đặc quyền tối thiểu.

## 7. Kiểm tra trạng thái và xác minh chính sách

**SHOW CREATE USER** cho biết các thuộc tính tài khoản đang được cấu hình:

~~~sql
SHOW CREATE USER 'app_login'@'10.20.%'\G
~~~

Kết quả có thể chứa thông tin xác thực đã mã hóa hoặc băm và dữ liệu cấu hình nhạy cảm. Chỉ người có thẩm quyền mới được xem; không sao chép nguyên kết quả vào ticket hoặc tài liệu chia sẻ rộng.

Quản trị viên có thể kiểm tra một số trạng thái từ **mysql.user**:

~~~sql
SELECT
  user,
  host,
  account_locked,
  password_expired,
  password_last_changed,
  password_lifetime,
  failed_login_attempts,
  password_lock_time
FROM mysql.user
WHERE user = 'app_login';
~~~

Các cột và quyền đọc có thể khác theo phiên bản và cấu hình. Truy vấn này chỉ phục vụ kiểm tra; không cập nhật trực tiếp bảng hệ thống để thay đổi chính sách. Dùng **CREATE USER**, **ALTER USER** và các câu lệnh quản trị được MySQL hỗ trợ để thay đổi tài khoản.

Sau khi áp dụng chính sách, xác minh bằng một tài khoản thử nghiệm có phạm vi quyền hạn thấp:

1. Tạo tài khoản thử với chính sách dự kiến.
2. Thử tạo hoặc đổi sang mật khẩu yếu để xác nhận kiểm tra độ mạnh hoạt động.
3. Thử tái sử dụng mật khẩu cũ trong môi trường kiểm thử.
4. Kiểm tra hành vi hết hạn và luồng đặt lại mật khẩu.
5. Thử số lần đăng nhập sai trong giới hạn kiểm soát để xác nhận cơ chế khóa.
6. Xác nhận tài khoản bị khóa không thể tạo kết nối mới và có thể được mở khóa đúng quy trình.
7. Với dual password, xác nhận cả hai bí mật hoạt động trong giai đoạn chuyển tiếp, rồi xác nhận mật khẩu cũ bị từ chối sau khi loại bỏ.

Không thử gây khóa tài khoản thật hoặc làm hết hạn tài khoản production chỉ để kiểm tra. Dùng môi trường staging hoặc tài khoản kiểm thử được phê duyệt.

## 8. Xử lý các tình huống thường gặp

### Máy khách báo mật khẩu đã hết hạn

MySQL có thể từ chối các thao tác thông thường và yêu cầu đổi mật khẩu trước khi tiếp tục. Dùng luồng đặt lại mật khẩu đã được phê duyệt. Với MySQL client, tùy phiên bản và cấu hình, tùy chọn **--connect-expired-password** cho phép kết nối trong trạng thái mật khẩu hết hạn để thực hiện đổi mật khẩu. Không tắt chính sách hết hạn trên toàn máy chủ chỉ để xử lý một tài khoản.

### Người dùng hợp lệ bị khóa

Kiểm tra đúng cặp **user** và **host**, xác định nguồn đăng nhập sai, kiểm tra cấu hình ứng dụng và connection pool, sau đó chờ hết thời gian khóa hoặc dùng **ACCOUNT UNLOCK** theo quy trình. Nếu lỗi đến từ một instance ứng dụng vẫn giữ mật khẩu cũ, cần sửa nguồn cấu hình trước khi mở khóa để tránh tài khoản bị khóa lại.

### Mật khẩu mới bị từ chối

Kiểm tra chính sách **validate_password**, độ dài, nhóm ký tự, tên tài khoản và cấu hình từ điển. Nếu mật khẩu bị từ chối do lịch sử hoặc khoảng thời gian tái sử dụng, kiểm tra **password_history** và **password_reuse_interval**. Không hạ chính sách toàn cục một cách vội vàng; xác định chính xác quy tắc gây lỗi và xử lý ở phạm vi nhỏ nhất.

### Ứng dụng mất kết nối sau khi luân chuyển

Kiểm tra secret manager đã cập nhật đúng phiên bản bí mật chưa, tất cả instance đã nạp cấu hình mới chưa, connection pool có còn dùng thông tin xác thực cũ không và tài khoản có bị khóa hoặc hết hạn không. Nếu đang trong giai đoạn dual password và mật khẩu cũ vẫn được giữ, có thể dùng nó để khôi phục tạm thời theo kế hoạch sự cố. Sau khi xử lý, hoàn tất việc loại bỏ mật khẩu cũ.

## 9. Kết hợp chính sách mật khẩu với bảo vệ tài khoản

Chính sách mật khẩu chỉ là một phần của bảo mật MySQL. Một cấu hình vận hành tốt nên kết hợp:

- Mỗi người hoặc ứng dụng có tài khoản riêng; tránh dùng chung tài khoản quản trị.
- Giới hạn host nguồn theo mạng thực sự cần truy cập, thay vì cấp quyền kết nối từ mọi nơi.
- Cấp quyền tối thiểu theo vai trò công việc; không dùng tài khoản ứng dụng có quyền **SUPER** hoặc quyền quản trị rộng nếu không cần.
- Bắt buộc kết nối TLS khi dữ liệu xác thực đi qua mạng không đáng tin cậy; cân nhắc yêu cầu chứng thư phía máy khách cho hệ thống nhạy cảm.
- Lưu mật khẩu trong secret manager, giới hạn người và tiến trình có thể đọc, ghi nhận lịch sử thay đổi và tránh đưa bí mật vào mã nguồn hoặc log.
- Theo dõi đăng nhập thất bại, tài khoản bị khóa, thay đổi tài khoản và các thay đổi chính sách.
- Có quy trình thu hồi hoặc khóa tài khoản ngay khi nhân sự, ứng dụng hoặc tích hợp không còn cần truy cập.
- Kiểm tra backup và khả năng khôi phục theo quy trình; bảo vệ bản sao lưu cùng mức độ với dữ liệu production.

Không phải mọi tài khoản đều cần cùng một chính sách. Tài khoản quản trị cá nhân, tài khoản ứng dụng, tài khoản đọc báo cáo và tài khoản tạm thời có vòng đời và cách xác thực khác nhau. Thiết kế chính sách theo loại tài khoản, xác định chủ sở hữu và rà soát ngoại lệ định kỳ.

## 10. Quy trình triển khai đề xuất

Trước khi thay đổi production, lập danh sách tài khoản, chủ sở hữu, host được phép, ứng dụng phụ thuộc, quyền hiện có, trạng thái hết hạn và phương án khôi phục. Phân loại tài khoản con người, tài khoản dịch vụ, tài khoản quản trị và tài khoản tạm thời.

Tiếp theo, thử cấu hình trên môi trường kiểm thử với đúng phiên bản MySQL. Kiểm tra khả năng tương thích của ứng dụng với hết hạn mật khẩu, xác nhận luồng đặt lại mật khẩu, đo tác động của khóa đăng nhập và diễn tập luân chuyển. Chốt ngưỡng, chu kỳ, ngoại lệ và người có quyền mở khóa.

Khi triển khai, thay đổi theo nhóm nhỏ, ghi lại cấu hình trước và sau, kiểm tra đăng nhập của ứng dụng và theo dõi lỗi xác thực. Có người chịu trách nhiệm xử lý khi tài khoản bị khóa hoặc mật khẩu hết hạn. Sau khi hoàn tất, rà soát các tài khoản ngoại lệ và loại bỏ những ngoại lệ không còn lý do.

Checklist vận hành:

- [ ] Đã xác định phiên bản MySQL và tính năng được hỗ trợ.
- [ ] Đã chọn chính sách độ mạnh phù hợp và thử trên môi trường kiểm thử.
- [ ] Đã cấu hình lịch sử mật khẩu và quy tắc tái sử dụng theo yêu cầu.
- [ ] Đã quyết định thời hạn cho từng loại tài khoản và kiểm tra ngoại lệ.
- [ ] Đã cấu hình khóa đăng nhập sai với ngưỡng và thời gian hợp lý.
- [ ] Đã có người chịu trách nhiệm mở khóa và xử lý sự cố xác thực.
- [ ] Đã có quy trình luân chuyển bí mật cho ứng dụng và connection pool.
- [ ] Đã kiểm tra log, quyền tài khoản, TLS và nơi lưu bí mật.
- [ ] Đã ghi nhận thay đổi và có phương án khôi phục đã được kiểm thử.

## Kết luận

Quản lý mật khẩu MySQL hiệu quả đòi hỏi phối hợp chính sách độ mạnh, lịch sử, hết hạn, khóa đăng nhập và quy trình luân chuyển. Hãy áp dụng theo loại tài khoản, kiểm tra khả năng tương thích của phiên bản, thử trước trên môi trường an toàn và xác minh toàn bộ ứng dụng phụ thuộc sau mỗi thay đổi. Một chính sách chỉ có giá trị khi người dùng và hệ thống có thể tuân thủ mà vẫn duy trì hoạt động ổn định, đồng thời bí mật luôn được lưu trữ và thay thế có kiểm soát.
