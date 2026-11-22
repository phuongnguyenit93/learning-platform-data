# LOCAL INFILE, FILE privilege, secure_file_priv và bề mặt truy cập file

Trong module **DATABASE_MYSQL**, phần **Bảo mật** cần xem thao tác nhập và xuất tệp là một phần của bề mặt tấn công của máy chủ cơ sở dữ liệu. Một câu lệnh nạp CSV có thể đọc tệp từ máy chạy ứng dụng hoặc từ máy chủ MySQL; hai cách này có quyền, đường dẫn và rủi ro khác nhau. Nếu nhầm lẫn chúng, ta có thể cấp quyền đọc tệp máy chủ cho tài khoản ứng dụng hoặc vô tình cho phép một máy chủ không đáng tin yêu cầu máy khách gửi tệp cục bộ.

Bài học này tập trung vào ba cơ chế: **LOCAL INFILE**, quyền toàn cục **FILE**, và biến cấu hình **secure_file_priv**. Chúng liên quan trực tiếp đến phân quyền, kiểm soát dữ liệu nhập, bảo vệ máy chủ và vận hành MySQL an toàn.

Trong phạm vi module, chủ đề này bổ sung cho việc làm chủ thiết kế bảng, kiểu dữ liệu, khóa, truy vấn SQL, index, transaction và kiểm soát đồng thời; nó cũng liên quan đến đọc kế hoạch thực thi, tối ưu truy vấn, phân quyền, sao lưu và xử lý sự cố vận hành cơ sở dữ liệu quan hệ.

## 1. Mục tiêu và mô hình truy cập tệp

Sau bài học, bạn có thể:

- Phân biệt LOAD DATA INFILE và LOAD DATA LOCAL INFILE theo nơi đọc tệp.
- Xác định khi nào cần quyền FILE và khi nào không cần.
- Giải thích tác dụng của secure_file_priv và local_infile.
- Cấu hình nhập dữ liệu có kiểm soát, cấp quyền tối thiểu và kiểm tra kết quả.
- Điều tra lỗi đường dẫn, quyền hệ điều hành và cấu hình liên quan đến thao tác tệp.

Hãy luôn xác định ba câu hỏi trước khi viết SQL:

1. Tệp nằm trên máy chạy chương trình khách hay trên máy chủ MySQL?
2. Tiến trình nào thực sự mở tệp: chương trình khách hay tiến trình mysqld?
3. Tài khoản MySQL và tài khoản hệ điều hành nào cần quyền để thao tác đó thành công?

MySQL có hai luồng nhập tệp chính:

| Câu lệnh | Nơi đọc tệp | Ai truy cập hệ thống tệp? | Quyền MySQL đặc trưng |
|---|---|---|---|
| LOAD DATA INFILE | Máy chủ MySQL | Tiến trình mysqld | FILE và INSERT trên bảng đích |
| LOAD DATA LOCAL INFILE | Máy chạy chương trình khách | Chương trình khách hoặc thư viện kết nối | INSERT trên bảng đích; không cần FILE |

Từ LOCAL là khác biệt cốt lõi. Với LOCAL, máy khách mở tệp rồi truyền nội dung qua kết nối MySQL; máy chủ không tự mở đường dẫn đó trên đĩa của máy khách. Nếu ứng dụng chạy trong container hoặc trên máy chủ ứng dụng, đường dẫn LOCAL phải tồn tại và đọc được trong môi trường chạy ứng dụng ấy, không nhất thiết tồn tại trên máy tính của người dùng.

## 2. LOAD DATA LOCAL INFILE

### 2.1. Cách hoạt động

Ví dụ, ứng dụng nhập tệp orders.csv từ máy chạy ứng dụng vào bảng staging:

~~~sql
LOAD DATA LOCAL INFILE '/data/inbox/orders.csv'
INTO TABLE stg_orders
CHARACTER SET utf8mb4
FIELDS TERMINATED BY ','
OPTIONALLY ENCLOSED BY '"'
LINES TERMINATED BY '\n'
IGNORE 1 LINES
(order_id, customer_id, amount, created_at);
~~~

Trong ví dụ này:

- Đường dẫn /data/inbox/orders.csv được phân giải trên máy chạy MySQL client hoặc tiến trình ứng dụng sử dụng thư viện kết nối.
- Máy khách đọc tệp và gửi dữ liệu cho máy chủ qua kết nối.
- Máy chủ cần quyền INSERT trên bảng stg_orders.
- Quyền FILE không cần thiết cho thao tác LOCAL.
- secure_file_priv kiểm soát thao tác tệp phía máy chủ, vì vậy không giới hạn đường dẫn tệp cục bộ mà máy khách mở trong luồng LOCAL.

Cấu hình FIELDS và LINES phải khớp định dạng tệp thực tế. Ví dụ trên giả định CSV dùng dấu phẩy, dấu ngoặc kép bao quanh trường và xuống dòng LF. Nếu tệp đến từ Windows, dòng có thể kết thúc bằng CRLF. Nếu trường có dấu ngoặc kép hoặc ký tự escape bên trong, cần chọn ESCAPED BY phù hợp với cách hệ thống tạo tệp và thử với dữ liệu đại diện trước khi nhập hàng loạt.

### 2.2. Điều kiện bật LOCAL

LOCAL INFILE thường cần được cho phép ở cả phía máy chủ và phía máy khách:

- Trên máy chủ, biến toàn cục local_infile phải bật.
- Trên máy khách, chương trình mysql hoặc thư viện kết nối phải cho phép nạp tệp LOCAL.
- Tài khoản MySQL phải có quyền cần thiết trên bảng đích, thường là INSERT.

Kiểm tra phía máy chủ:

~~~sql
SHOW GLOBAL VARIABLES LIKE 'local_infile';
~~~

Với chương trình dòng lệnh MySQL, có thể bật hỗ trợ ở lúc kết nối bằng tùy chọn:

~~~bash
mysql --local-infile=1 -u batch_loader -p shop
~~~

Tùy chọn của thư viện kết nối phụ thuộc driver và phiên bản. Ví dụ, MySQL Connector/J có thuộc tính kết nối allowLoadLocalInfile. Hãy kiểm tra tài liệu đúng phiên bản driver đang triển khai và chỉ bật tính năng trong kết nối chuyên dùng cho tác vụ nhập dữ liệu.

Nếu hệ thống không cần nhập tệp từ máy khách, nên tắt local_infile ở máy chủ và tắt khả năng tương ứng ở các client. Khi cần bật tạm thời, hãy giới hạn thời gian, tài khoản, nguồn kết nối và quy trình vận hành; sau khi hoàn tất, khôi phục cấu hình an toàn đã chọn.

### 2.3. Rủi ro riêng của LOCAL

Khi LOCAL được bật, giao thức cho phép máy chủ yêu cầu máy khách gửi một tệp cục bộ. Vì vậy, một máy chủ MySQL độc hại hoặc bị chiếm quyền có thể cố yêu cầu chương trình khách gửi những tệp mà tiến trình khách có quyền đọc. Rủi ro phụ thuộc vào quyền của tài khoản hệ điều hành chạy ứng dụng và cách driver kiểm soát yêu cầu LOCAL.

Các biện pháp giảm thiểu:

- Chỉ kết nối LOCAL tới máy chủ đáng tin cậy; xác minh danh tính máy chủ và dùng TLS với kiểm tra chứng thư phù hợp.
- Chỉ bật LOCAL trong client và kết nối thực sự cần nhập tệp.
- Chạy ứng dụng bằng tài khoản hệ điều hành có quyền đọc tối thiểu; không chạy ứng dụng nhập liệu với quyền quản trị.
- Đặt tệp đầu vào trong thư mục staging riêng, giới hạn quyền truy cập và không chứa khóa bí mật, tệp cấu hình hay dữ liệu nhạy cảm khác.
- Không để người dùng tùy ý cung cấp đường dẫn tệp. Ứng dụng nên chọn tệp từ vùng cho phép, tạo tên tệp an toàn và kiểm tra nguồn dữ liệu trước khi nhập.
- Dùng tài khoản MySQL riêng cho tác vụ nhập và chỉ cấp quyền trên schema hoặc bảng cần thiết.

TLS bảo vệ đường truyền và xác thực máy chủ theo cấu hình chứng thư, nhưng không biến một máy chủ độc hại thành máy chủ đáng tin cậy. Quyết định bật LOCAL vẫn phải dựa trên mức độ tin cậy của đầu cuối kết nối.

## 3. LOAD DATA INFILE phía máy chủ

Khi bỏ từ khóa LOCAL, tiến trình mysqld đọc tệp trên máy chủ cơ sở dữ liệu:

~~~sql
LOAD DATA INFILE '/var/lib/mysql-files/orders.csv'
INTO TABLE stg_orders
CHARACTER SET utf8mb4
FIELDS TERMINATED BY ','
OPTIONALLY ENCLOSED BY '"'
LINES TERMINATED BY '\n'
IGNORE 1 LINES
(order_id, customer_id, amount, created_at);
~~~

Với luồng này:

1. Đường dẫn phải tồn tại trên máy chủ MySQL.
2. Tài khoản hệ điều hành chạy mysqld phải có quyền đọc tệp và truy cập các thư mục cha.
3. Tài khoản MySQL thực thi câu lệnh phải có quyền FILE ở phạm vi toàn cục.
4. Tài khoản MySQL phải có quyền INSERT trên bảng đích.
5. Đường dẫn phải thỏa mãn giới hạn của secure_file_priv nếu biến này được cấu hình để giới hạn thư mục.

Quyền FILE không thay thế quyền của hệ điều hành. Một tài khoản MySQL có FILE vẫn không đọc được tệp mà tiến trình mysqld không được phép đọc. Ngược lại, quyền đọc của hệ điều hành cũng không đủ nếu tài khoản MySQL thiếu FILE hoặc đường dẫn bị secure_file_priv chặn.

Chọn LOAD DATA INFILE khi tệp đã được chuyển an toàn đến máy chủ và tổ chức vận hành muốn máy chủ đọc tệp từ một thư mục staging được kiểm soát. Nếu tệp chỉ tồn tại trên máy chạy ứng dụng, dùng LOCAL khi chính sách bảo mật cho phép.

## 4. Quyền toàn cục FILE

### 4.1. FILE cho phép những gì?

FILE là quyền toàn cục cho phép tài khoản MySQL thực hiện một số thao tác đọc hoặc ghi tệp trên máy chủ, tiêu biểu gồm:

- LOAD DATA INFILE: đọc tệp phía máy chủ để nạp vào bảng.
- SELECT ... INTO OUTFILE: ghi kết quả truy vấn thành tệp trên máy chủ.
- SELECT ... INTO DUMPFILE: ghi một hàng kết quả dưới dạng dữ liệu thô vào tệp.
- LOAD_FILE(): đọc nội dung tệp phía máy chủ và trả về dưới dạng giá trị.

FILE có phạm vi toàn cục, không thể giới hạn riêng cho một bảng bằng cách cấp FILE trên một schema. Vì vậy, cấp quyền này cho tài khoản ứng dụng thông thường có thể mở rộng đáng kể khả năng truy cập hệ thống tệp của tiến trình MySQL.

Ví dụ xuất dữ liệu:

~~~sql
SELECT order_id, customer_id, amount
INTO OUTFILE '/var/lib/mysql-files/orders-export.csv'
FIELDS TERMINATED BY ','
OPTIONALLY ENCLOSED BY '"'
LINES TERMINATED BY '\n'
FROM orders
WHERE created_at >= '2026-01-01';
~~~

Câu lệnh cần quyền SELECT thích hợp trên dữ liệu và quyền FILE. Tệp được tạo trên máy chủ bởi tiến trình mysqld. MySQL không ghi đè một tệp đã tồn tại tại đường dẫn đích; hãy dùng tên tệp mới hoặc quy trình xoay vòng tệp có kiểm soát.

SELECT ... INTO DUMPFILE cũng ghi tệp phía máy chủ, nhưng tạo dữ liệu của một hàng mà không thêm định dạng phân tách trường hoặc dòng. Cần đặc biệt thận trọng khi dùng nó để xuất dữ liệu nhị phân.

Ví dụ LOAD_FILE():

~~~sql
SELECT LOAD_FILE('/var/lib/mysql-files/notice.txt');
~~~

LOAD_FILE() chỉ đọc được tệp nếu các điều kiện về quyền FILE, quyền đọc của hệ điều hành, giới hạn secure_file_priv và giới hạn kích thước liên quan đều thỏa mãn. Nếu không đọc được, hàm có thể trả về NULL. Không dùng hàm này như một cơ chế đọc tệp tùy ý từ ứng dụng.

### 4.2. Cấp và thu hồi FILE

Chỉ cấp FILE cho tài khoản vận hành chuyên biệt khi một quy trình đã được đánh giá cần thao tác tệp phía máy chủ:

~~~sql
GRANT FILE ON *.* TO 'file_exporter'@'localhost';
~~~

Nếu tài khoản xuất dữ liệu cần đọc bảng orders, cấp thêm quyền đọc đúng phạm vi:

~~~sql
GRANT SELECT ON shop.orders TO 'file_exporter'@'localhost';
~~~

Đối với nhập dữ liệu phía máy chủ, tài khoản còn cần quyền INSERT trên bảng đích:

~~~sql
GRANT INSERT ON shop.stg_orders TO 'file_importer'@'localhost';
GRANT FILE ON *.* TO 'file_importer'@'localhost';
~~~

Thu hồi FILE khi tác vụ không còn cần quyền này:

~~~sql
REVOKE FILE ON *.* FROM 'file_exporter'@'localhost';
~~~

Kiểm tra quyền đã cấp:

~~~sql
SHOW GRANTS FOR 'file_exporter'@'localhost';
SHOW GRANTS FOR CURRENT_USER();
~~~

Một tài khoản chỉ dùng LOAD DATA LOCAL INFILE thường chỉ cần quyền thao tác trên bảng đích; không cấp FILE cho tài khoản đó. Hãy tránh gộp quyền nhập dữ liệu, xuất dữ liệu và quyền quản trị vào cùng một tài khoản dùng lâu dài.

## 5. secure_file_priv

### 5.1. Ý nghĩa và các trạng thái

secure_file_priv giới hạn hoặc vô hiệu hóa một số thao tác nhập, xuất tệp phía máy chủ. Có thể kiểm tra giá trị hiện tại bằng:

~~~sql
SHOW GLOBAL VARIABLES LIKE 'secure_file_priv';
~~~

Các trạng thái thường gặp:

| Giá trị | Ý nghĩa |
|---|---|
| Đường dẫn thư mục, ví dụ /var/lib/mysql-files | Giới hạn thao tác tệp phía máy chủ vào thư mục được cấu hình |
| Chuỗi rỗng | Không áp dụng giới hạn thư mục từ biến này; bề mặt truy cập tệp rộng hơn |
| NULL | Vô hiệu hóa các thao tác nhập và xuất tệp phía máy chủ chịu sự kiểm soát của biến |

Không nên chọn chuỗi rỗng chỉ để làm cho một câu lệnh đang lỗi chạy được. Cấu hình thư mục riêng thường dễ kiểm soát và kiểm toán hơn. Giá trị mặc định có thể khác nhau theo nền tảng và cách cài đặt, vì vậy hãy đọc giá trị thực tế trên máy chủ thay vì giả định.

secure_file_priv là biến cấu hình chỉ đọc trong lúc máy chủ đang chạy; thay đổi giá trị cần điều chỉnh cấu hình khởi động của MySQL và khởi động lại theo quy trình vận hành. Ví dụ trong tệp cấu hình máy chủ:

~~~ini
[mysqld]
secure_file_priv=/var/lib/mysql-files
local_infile=OFF
~~~

Ví dụ này giới hạn thao tác tệp phía máy chủ vào thư mục riêng và tắt LOCAL ở phía máy chủ. Nếu một quy trình nghiệp vụ cần LOCAL, hãy đánh giá và cấu hình local_infile riêng theo chính sách đã duyệt; không bật chỉ để khắc phục tạm thời mà không xem xét rủi ro.

### 5.2. secure_file_priv không thay thế quyền hệ điều hành

Đặt secure_file_priv thành một thư mục không tự động cấp quyền đọc hoặc ghi cho mysqld. Quản trị viên hệ điều hành cần:

- Tạo thư mục trước khi MySQL khởi động với cấu hình đó.
- Cấp quyền sở hữu và quyền truy cập phù hợp cho tài khoản chạy mysqld.
- Giới hạn người dùng và tiến trình khác có thể ghi vào thư mục.
- Không đặt tệp bí mật, tệp thực thi hoặc dữ liệu không liên quan vào thư mục staging.
- Kiểm tra cơ chế bảo vệ bổ sung như AppArmor hoặc SELinux nếu hệ điều hành sử dụng chúng.

Không nên cho người dùng không tin cậy quyền ghi vào thư mục mà mysqld được phép đọc. Nếu họ có thể thay thế tệp trong thư mục staging, họ có thể tác động đến dữ liệu được nhập hoặc nội dung mà quy trình xuất sử dụng.

### 5.3. Phạm vi của biến

secure_file_priv kiểm soát các thao tác tệp phía máy chủ như LOAD DATA INFILE, SELECT ... INTO OUTFILE, SELECT ... INTO DUMPFILE và LOAD_FILE(). Nó không phải cơ chế giới hạn đường dẫn mà client mở khi dùng LOAD DATA LOCAL INFILE. Để kiểm soát LOCAL, cần quản lý local_infile ở máy chủ, cấu hình của client hoặc driver, danh tính máy chủ và quyền hệ điều hành của tiến trình client.

Do đó, một cấu hình secure_file_priv chặt chẽ vẫn cần chính sách riêng cho LOCAL. Tương tự, tắt LOCAL không tự động thu hồi FILE hoặc vô hiệu hóa SELECT ... INTO OUTFILE nếu các điều kiện phía máy chủ vẫn cho phép.

## 6. Quy trình nhập dữ liệu an toàn

Một quy trình nhập CSV có thể chia thành các bước sau:

1. **Tiếp nhận tệp:** nhận tệp qua kênh được kiểm soát, giới hạn kích thước, định dạng, mã hóa và nguồn gửi.
2. **Đưa vào vùng staging:** dùng thư mục riêng. Nếu nhập bằng LOCAL, thư mục nằm trên máy chạy client; nếu dùng INFILE, thư mục nằm trên máy chủ MySQL.
3. **Chọn tài khoản:** tài khoản nhập chỉ có quyền INSERT cần thiết trên bảng staging. Chỉ cấp FILE nếu chọn luồng INFILE phía máy chủ.
4. **Kiểm tra cấu hình:** xác minh local_infile, secure_file_priv, quyền thư mục và khả năng đọc của tiến trình tương ứng.
5. **Nạp vào bảng staging:** chỉ định rõ CHARACTER SET, dấu phân cách, ký tự bao trường, kiểu kết thúc dòng, dòng tiêu đề và danh sách cột.
6. **Kiểm tra dữ liệu:** kiểm tra số hàng, giá trị NULL, kiểu dữ liệu, khóa trùng, phạm vi số và cảnh báo chuyển đổi.
7. **Đưa vào bảng chính:** dùng câu lệnh có kiểm soát, kiểm tra ràng buộc và ghi nhận kết quả nghiệp vụ.
8. **Dọn dẹp:** xóa tệp staging theo chính sách lưu giữ, thu hồi quyền tạm thời và tắt tính năng chỉ được bật cho tác vụ.

Ví dụ kiểm tra ngay sau khi nạp:

~~~sql
SHOW WARNINGS;
SELECT ROW_COUNT() AS affected_rows;
~~~

Chạy SHOW WARNINGS ngay sau LOAD DATA để đọc cảnh báo của lần nhập; sau đó ghi nhận ROW_COUNT() để theo dõi số hàng bị tác động. Với dữ liệu quan trọng, hãy so sánh số hàng đầu vào, số hàng nạp thành công và số hàng bị loại hoặc chuyển đổi. Không coi việc câu lệnh kết thúc mà không báo lỗi là bằng chứng duy nhất cho thấy dữ liệu đúng.

Bảng staging giúp tách việc tiếp nhận dữ liệu khỏi bảng nghiệp vụ. Có thể kiểm tra bản ghi lỗi, chuẩn hóa định dạng, phát hiện khóa trùng và đối chiếu tổng trước khi ghi vào bảng chính. Hãy dùng bảng InnoDB nếu cần các bảo đảm giao dịch của InnoDB trong các bước xử lý tiếp theo; không giả định mọi hệ thống tệp, bảng và bước nhập đều có thể được hoàn tác như nhau.

## 7. Ma trận lựa chọn và cấu hình bảo mật

| Nhu cầu | Cách tiếp cận | Quyền/cấu hình chính | Kiểm soát cần có |
|---|---|---|---|
| Tệp nằm trên máy chạy ứng dụng | LOAD DATA LOCAL INFILE | local_infile ở máy chủ và client; INSERT trên bảng | Chỉ kết nối máy chủ tin cậy, giới hạn thư mục và quyền của tiến trình client |
| Tệp nằm trên máy chủ DB | LOAD DATA INFILE | FILE toàn cục và INSERT trên bảng | secure_file_priv, quyền đọc của mysqld, thư mục staging riêng |
| Xuất truy vấn thành tệp máy chủ | SELECT ... INTO OUTFILE | FILE toàn cục và SELECT trên dữ liệu | secure_file_priv, quyền ghi của mysqld, kiểm soát nơi nhận tệp |
| Đọc nội dung tệp máy chủ trong SQL | LOAD_FILE() | FILE toàn cục | Hạn chế sử dụng, kiểm soát thư mục và quyền hệ điều hành |
| Ứng dụng không có nhu cầu nhập LOCAL | Tắt LOCAL | local_infile=OFF và client không cho phép LOCAL | Rà soát driver và cấu hình kết nối |

Một cấu hình cơ sở thường phù hợp với hệ thống ứng dụng không cần đọc tệp từ máy khách:

- Giữ local_infile ở trạng thái OFF.
- Đặt secure_file_priv vào một thư mục riêng nếu quy trình máy chủ cần nhập hoặc xuất tệp.
- Không cấp FILE cho tài khoản ứng dụng thông thường.
- Dùng tài khoản chuyên biệt, thời hạn ngắn cho tác vụ cần FILE.
- Giới hạn quyền hệ điều hành đối với thư mục được MySQL sử dụng.
- Ghi nhận người thực hiện, thời điểm, nguồn tệp, số hàng và kết quả nhập.

Nếu tổ chức cần LOCAL, hãy ghi rõ lý do nghiệp vụ, máy chủ đích được tin cậy, client/driver được phép, thư mục được phép đọc và thời điểm bật/tắt. Kiểm tra cấu hình trên môi trường tương đương trước khi triển khai.

## 8. Xử lý sự cố thường gặp

| Triệu chứng | Nguyên nhân có thể | Hướng kiểm tra |
|---|---|---|
| LOCAL bị từ chối hoặc client báo không hỗ trợ | local_infile tắt ở máy chủ hoặc client; driver không cho phép LOCAL | Kiểm tra biến phía máy chủ và tùy chọn của đúng client/driver |
| LOAD DATA INFILE báo không có quyền | Thiếu FILE, thiếu INSERT hoặc thiếu quyền hệ điều hành | Kiểm tra SHOW GRANTS và quyền của tài khoản chạy mysqld |
| Đường dẫn không tìm thấy | Đường dẫn được hiểu trên sai máy; sai đường dẫn hoặc sai thư mục làm việc | Xác định luồng có LOCAL hay không và kiểm tra trên đúng máy |
| secure_file_priv chặn thao tác | Tệp nằm ngoài thư mục được phép hoặc biến đang là NULL | Đọc giá trị biến và kiểm tra đường dẫn; thay đổi cấu hình theo quy trình khởi động |
| Máy chủ không đọc/ghi được dù MySQL đã cấp quyền | Quyền thư mục, quyền tệp, AppArmor hoặc SELinux chặn | Kiểm tra quyền hệ điều hành và nhật ký bảo mật |
| Nạp được nhưng dữ liệu sai cột hoặc sai ký tự | Sai dấu phân cách, mã hóa, ký tự bao trường hoặc kiểu xuống dòng | Kiểm tra vài dòng mẫu và cấu hình FIELDS, LINES, CHARACTER SET |
| Một số hàng bị bỏ qua hoặc chuyển đổi | Dữ liệu không khớp kiểu, khóa trùng, tùy chọn IGNORE hoặc chế độ SQL | Đọc SHOW WARNINGS, đối chiếu dữ liệu nguồn và quy tắc bảng |

Khi điều tra, thu thập tối thiểu: câu lệnh đã chạy (đã loại bỏ bí mật), phiên bản MySQL và driver, giá trị local_infile và secure_file_priv, kết quả SHOW GRANTS, đường dẫn đã dùng, máy mà đường dẫn thuộc về, cùng quyền hệ điều hành của tiến trình liên quan. Không khắc phục bằng cách cấp FILE cho tài khoản rộng hơn hoặc đặt secure_file_priv thành chuỗi rỗng trước khi xác định nguyên nhân.

Nếu phát hiện tài khoản không cần thiết đang có FILE, hãy rà soát phạm vi sử dụng, thu hồi quyền, kiểm tra nhật ký phù hợp và xác minh các thư mục MySQL có thể truy cập. Nếu LOCAL không còn cần thiết, tắt tính năng ở máy chủ và client theo cấu hình triển khai.

## 9. Tự kiểm tra

**Tình huống 1:** Một ứng dụng chạy trên máy chủ ứng dụng cần nhập tệp CSV nằm trong thư mục riêng của ứng dụng vào MySQL từ xa. Tài khoản nhập chỉ cần thêm dữ liệu vào bảng staging. Cách tiếp cận phù hợp là gì?

**Gợi ý:** Cân nhắc LOAD DATA LOCAL INFILE. Đường dẫn phải đọc được bởi tiến trình ứng dụng; cần cho phép LOCAL ở cả máy chủ và client, đồng thời tài khoản có INSERT trên bảng. Không cần cấp FILE chỉ vì dùng LOCAL.

**Tình huống 2:** Quản trị viên muốn MySQL đọc tệp từ /var/lib/mysql-files trên chính máy chủ DB. Những lớp kiểm soát nào phải cùng thỏa mãn?

**Gợi ý:** Câu lệnh LOAD DATA INFILE cần FILE và INSERT; secure_file_priv phải cho phép thư mục; tiến trình mysqld phải có quyền đọc tệp và thư mục cha.

**Tình huống 3:** Máy chủ có secure_file_priv trỏ đến thư mục riêng nhưng ứng dụng vẫn dùng LOCAL để đọc tệp từ máy chạy ứng dụng. Biến này có giới hạn đường dẫn LOCAL không?

**Gợi ý:** Không. secure_file_priv kiểm soát thao tác tệp phía máy chủ. LOCAL cần được quản lý qua local_infile, cấu hình client/driver, danh tính máy chủ và quyền của tiến trình client.

**Tình huống 4:** Một tài khoản ứng dụng có FILE dù chỉ chạy SELECT, INSERT và UPDATE trên schema nghiệp vụ. Nên xử lý thế nào?

**Gợi ý:** Xác minh ứng dụng có thật sự cần thao tác tệp phía máy chủ hay không. Nếu không, thu hồi FILE. Cấp FILE là quyền toàn cục nên không nên dùng như quyền tiện ích cho tài khoản ứng dụng.

## 10. Điểm cần ghi nhớ

- LOCAL đọc tệp từ máy chạy client; INFILE không có LOCAL đọc tệp từ máy chủ MySQL.
- LOAD DATA LOCAL INFILE không yêu cầu quyền FILE, nhưng cần cho phép LOCAL ở cả client và máy chủ, cùng quyền ghi vào bảng đích.
- FILE là quyền toàn cục, mở khả năng đọc hoặc ghi tệp phía máy chủ thông qua các câu lệnh được hỗ trợ.
- secure_file_priv giới hạn hoặc vô hiệu hóa thao tác tệp phía máy chủ; nó không thay thế quyền hệ điều hành và không giới hạn đường dẫn LOCAL.
- Tắt LOCAL khi không sử dụng, tránh cấp FILE cho tài khoản ứng dụng và dùng thư mục staging riêng với quyền tối thiểu.
- Luôn kiểm tra cảnh báo, số hàng, định dạng tệp và kết quả nghiệp vụ sau khi nhập.
