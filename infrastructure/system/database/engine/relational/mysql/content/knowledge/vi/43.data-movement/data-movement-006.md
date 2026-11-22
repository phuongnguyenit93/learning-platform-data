# SELECT INTO OUTFILE, quyền FILE và secure_file_priv

MySQL có thể xuất kết quả truy vấn trực tiếp thành một tệp trên máy chủ database bằng câu lệnh SELECT INTO OUTFILE. Cơ chế này hữu ích khi cần tạo bản xuất logic có định dạng rõ ràng để chuyển dữ liệu sang hệ thống khác. Tuy nhiên, tệp được ghi trên filesystem của máy chủ MySQL, không phải máy tính đang chạy SQL client. Vì vậy, quyền FILE, cấu hình secure_file_priv và quyền ghi của tài khoản hệ điều hành chạy MySQL đều phải được kiểm tra.

Bài học thuộc module **DATABASE_MYSQL**, tập trung vào nhập xuất và di chuyển dữ liệu: tạo tệp CSV hoặc TSV, kiểm soát phạm vi dữ liệu được xuất, cấu hình thư mục an toàn, phân quyền tối thiểu và xử lý lỗi khi ghi tệp. Các ví dụ dùng MySQL 8.0.

## 1. SELECT INTO OUTFILE hoạt động như thế nào?

SELECT INTO OUTFILE thực thi truy vấn trên MySQL Server rồi ghi các hàng kết quả thành một tệp trên filesystem mà tiến trình mysqld có thể truy cập.

Luồng xử lý:

1. Client gửi câu lệnh SELECT INTO OUTFILE đến MySQL Server.
2. Server kiểm tra quyền SELECT trên các đối tượng được truy vấn và quyền FILE của tài khoản.
3. Server kiểm tra chính sách secure_file_priv.
4. Hệ điều hành kiểm tra tài khoản dịch vụ MySQL có quyền tạo tệp trong thư mục đích hay không.
5. MySQL ghi các hàng truy vấn theo quy tắc phân tách trường, bao ngoặc, escape và xuống dòng đã cấu hình.

Điểm cần nhớ: đường dẫn trong INTO OUTFILE được hiểu trên máy chủ database. Nếu client kết nối từ máy tính cá nhân đến một server từ xa, tệp vẫn được tạo trên server. Muốn có tệp trên máy client, cần tải tệp qua kênh truyền được bảo vệ hoặc dùng một công cụ xuất dữ liệu ghi file tại phía client.

### Cú pháp tổng quát

~~~sql
SELECT select_list
INTO OUTFILE 'file_name'
  [CHARACTER SET charset_name]
  [FIELDS
    [TERMINATED BY 'string']
    [[OPTIONALLY] ENCLOSED BY 'char']
    [ESCAPED BY 'char']
  ]
  [LINES
    [STARTING BY 'string']
    [TERMINATED BY 'string']
  ]
FROM table_name
WHERE condition;
~~~

Các tùy chọn định dạng:

- **CHARACTER SET** chọn character set dùng để ghi dữ liệu ra tệp.
- **FIELDS TERMINATED BY** đặt ký tự phân cách giữa các cột.
- **ENCLOSED BY** bao giá trị trường bằng một ký tự, ví dụ dấu nháy kép.
- **OPTIONALLY ENCLOSED BY** chỉ bao các trường kiểu chuỗi, thay vì bao mọi giá trị.
- **ESCAPED BY** xác định ký tự dùng để escape ký tự đặc biệt và giá trị NULL.
- **LINES TERMINATED BY** đặt ký tự kết thúc mỗi hàng.
- **LINES STARTING BY** thêm chuỗi ở đầu mỗi hàng, thường không cần cho CSV.

Nếu không chỉ định các tùy chọn, MySQL sử dụng định dạng mặc định với tab phân cách trường, ký tự xuống dòng phân cách hàng và dấu gạch chéo ngược để escape. Đối với tích hợp hệ thống, nên khai báo định dạng tường minh để tránh phụ thuộc mặc định.

## 2. Quyền FILE và quyền SELECT

Để xuất bằng SELECT INTO OUTFILE, tài khoản cần:

- Quyền SELECT trên bảng hoặc view được truy vấn.
- Quyền toàn cục FILE để MySQL cho phép đọc/ghi file trên máy chủ theo các cơ chế được hỗ trợ.
- Quyền của tài khoản hệ điều hành chạy mysqld để tạo tệp trong thư mục đích.
- Đường dẫn nằm trong phạm vi secure_file_priv nếu biến này giới hạn thư mục.

Kiểm tra quyền hiện tại:

~~~sql
SHOW GRANTS FOR CURRENT_USER();
~~~

Quyền FILE là quyền toàn cục, không thể giới hạn chỉ cho một schema hoặc một bảng. Ví dụ cấp quyền:

~~~sql
GRANT FILE ON *.* TO 'data_exporter'@'10.20.%';
~~~

Khi không còn nhu cầu:

~~~sql
REVOKE FILE ON *.* FROM 'data_exporter'@'10.20.%';
~~~

Không cấp FILE cho tài khoản ứng dụng thông thường hoặc tài khoản dùng chung. Quyền này có phạm vi rộng: tùy cấu hình và quyền filesystem, tài khoản có thể đọc hoặc ghi file mà tiến trình MySQL được phép truy cập. Vì vậy, hãy tạo tài khoản xuất dữ liệu riêng, giới hạn host, cấp SELECT đúng phạm vi và thu hồi FILE sau khi công việc hoàn tất nếu chỉ cần dùng tạm thời.

Quyền FILE không tự cấp quyền SELECT. Ngược lại, có SELECT trên bảng cũng không đủ để chạy INTO OUTFILE nếu thiếu FILE.

## 3. secure_file_priv kiểm soát thư mục ra sao?

Biến hệ thống **secure_file_priv** giới hạn các thao tác nhập/xuất file phía server, bao gồm SELECT INTO OUTFILE, LOAD DATA INFILE và LOAD_FILE().

Kiểm tra:

~~~sql
SHOW VARIABLES LIKE 'secure_file_priv';
~~~

Ba trạng thái có ý nghĩa khác nhau:

| Giá trị | Hành vi |
|---|---|
| Đường dẫn thư mục, ví dụ /var/lib/mysql-files/ | Các thao tác file bị giới hạn trong thư mục được chỉ định |
| Chuỗi rỗng | Không áp dụng giới hạn thư mục từ secure_file_priv; phạm vi còn phụ thuộc quyền filesystem |
| NULL | Vô hiệu hóa các thao tác nhập/xuất file được kiểm soát bởi biến này |

Trên nhiều gói cài đặt, MySQL được cấu hình một thư mục xuất/nhập riêng. Giá trị thực tế phụ thuộc hệ điều hành, gói cài đặt và cấu hình máy chủ; luôn truy vấn trên instance thay vì đoán đường dẫn.

### Cấu hình thư mục an toàn

Ví dụ trong tệp cấu hình MySQL:

~~~ini
[mysqld]
secure_file_priv=/var/lib/mysql-files
~~~

Thư mục phải tồn tại và tài khoản hệ điều hành chạy MySQL phải có quyền ghi phù hợp. Không cấp quyền ghi rộng cho mọi người dùng. Trên hệ thống Linux, quản trị viên có thể đặt chủ sở hữu và quyền thư mục theo tài khoản dịch vụ MySQL, ví dụ:

~~~bash
sudo install -d -o mysql -g mysql -m 750 /var/lib/mysql-files
~~~

Tên tài khoản dịch vụ có thể khác theo bản phân phối. Xác minh tài khoản thực tế trước khi thay đổi quyền filesystem.

**secure_file_priv** là biến chỉ đọc trong lúc máy chủ hoạt động và được thiết lập khi MySQL khởi động. Sau khi sửa tệp cấu hình, cần khởi động lại MySQL theo quy trình bảo trì của hệ thống rồi xác minh lại giá trị. Không thể dùng SET GLOBAL để đổi biến này trong một session đang chạy.

Không đặt secure_file_priv thành chuỗi rỗng trên production nếu không có lý do vận hành đã được đánh giá. Giới hạn một thư mục riêng giúp thu hẹp phạm vi file mà câu lệnh SQL có thể truy cập.

## 4. Xuất dữ liệu dạng TSV

TSV dùng tab để phân cách các trường. Đây là định dạng đơn giản, phù hợp khi hệ thống đích có thể đọc tab-delimited text.

~~~sql
SELECT
  order_id,
  customer_id,
  created_at,
  total_amount
INTO OUTFILE '/var/lib/mysql-files/orders.tsv'
CHARACTER SET utf8mb4
FIELDS TERMINATED BY '\t'
LINES TERMINATED BY '\n'
FROM sales.orders
WHERE created_at >= '2026-01-01';
~~~

Trong ví dụ:

- Chỉ xuất bốn cột cần thiết, tránh lấy toàn bộ dữ liệu bằng SELECT *.
- Dữ liệu được ghi theo UTF-8/utf8mb4.
- Tab phân cách cột.
- Ký tự escape mặc định của MySQL được dùng cho tab, xuống dòng, backslash và các giá trị đặc biệt.
- Mỗi hàng kết thúc bằng LF.

Nếu hệ thống nhận tệp yêu cầu CRLF, có thể đặt **LINES TERMINATED BY '\r\n'**. Hãy thống nhất quy tắc xuống dòng với hệ thống nhận dữ liệu.

## 5. Xuất CSV

CSV thường dùng dấu phẩy phân cách cột và dấu nháy kép bao các giá trị văn bản. Ví dụ:

~~~sql
SELECT
  order_id,
  customer_name,
  created_at,
  total_amount
INTO OUTFILE '/var/lib/mysql-files/orders.csv'
CHARACTER SET utf8mb4
FIELDS TERMINATED BY ','
OPTIONALLY ENCLOSED BY '"'
LINES TERMINATED BY '\n'
FROM sales.orders
WHERE created_at >= '2026-01-01';
~~~

**OPTIONALLY ENCLOSED BY** bao các trường chuỗi bằng dấu nháy kép. Ký tự escape mặc định là backslash. Dữ liệu có dấu phẩy, dấu nháy, backslash hoặc ký tự xuống dòng cần được escape theo đúng quy tắc xuất của MySQL.

Định dạng CSV không có một cách xử lý NULL thống nhất giữa mọi công cụ. Với ký tự escape khác rỗng, MySQL ghi NULL dưới dạng ký hiệu backslash-N. Ứng dụng nhận tệp cần phân biệt NULL với chuỗi rỗng. Nếu hệ thống đích yêu cầu quy tắc CSV riêng, hãy kiểm tra bằng dữ liệu mẫu có NULL, chuỗi rỗng, dấu phẩy, dấu nháy và ký tự xuống dòng trước khi xuất toàn bộ.

SELECT INTO OUTFILE không tự thêm dòng tiêu đề tên cột. Nếu hệ thống nhận yêu cầu header, hãy thêm dòng tiêu đề bằng bước xử lý ở phía client hoặc thiết kế truy vấn xuất có dòng đầu riêng, rồi xác minh kiểu dữ liệu và thứ tự cột trước khi dùng.

Ví dụ dữ liệu thử nên bao gồm:

| Giá trị nguồn | Nội dung cần kiểm tra |
|---|---|
| NULL | Nhận diện NULL theo quy tắc escape |
| Chuỗi rỗng | Không bị hiểu nhầm thành NULL |
| Nguyen, An | Dấu phẩy nằm trong trường chuỗi |
| Anh nói "xin chào" | Dấu nháy kép trong nội dung |
| Dòng 1 và dòng 2 | Ký tự xuống dòng trong một trường |
| Tiếng Việt có dấu | Character set được đọc đúng |

Đối với trao đổi dữ liệu nghiêm ngặt theo RFC 4180 hoặc yêu cầu của một nền tảng cụ thể, cần xác nhận parser phía nhận tương thích với cách escape của MySQL. Có thể cần chuyển đổi định dạng bằng công cụ ở phía client sau khi xuất.

## 6. Kiểm soát dữ liệu trước khi xuất

SELECT INTO OUTFILE có thể tạo bản sao dữ liệu nhạy cảm trên filesystem của database server. Trước khi chạy, xác định rõ mục đích và phạm vi dữ liệu cần cung cấp.

### Chọn cột và lọc hàng

Không nên xuất tất cả cột theo thói quen. Viết danh sách cột tường minh, lọc theo thời gian hoặc trạng thái và chỉ lấy các bản ghi thuộc phạm vi công việc.

~~~sql
SELECT
  customer_id,
  email,
  created_at
INTO OUTFILE '/var/lib/mysql-files/customer-contact.csv'
CHARACTER SET utf8mb4
FIELDS TERMINATED BY ','
OPTIONALLY ENCLOSED BY '"'
LINES TERMINATED BY '\n'
FROM crm.customers
WHERE marketing_consent = 1
  AND status = 'active';
~~~

Nếu không cần email thật, hãy xuất mã khách hàng hoặc dữ liệu đã được che/mã hóa theo chính sách. Không xuất mật khẩu, token, thông tin thanh toán hoặc dữ liệu cá nhân vượt quá mục đích xử lý.

### Dùng view hoặc truy vấn có quyền hạn rõ ràng

Có thể tạo view chỉ chứa các trường được phép xuất và cấp SELECT trên view cho tài khoản xuất dữ liệu. Cách này giúp tách quyền truy cập dữ liệu khỏi quyền truy vấn toàn bộ bảng nguồn. Tuy nhiên, quyền FILE vẫn là quyền toàn cục và phải được kiểm soát riêng.

### Bảo vệ tệp sau khi xuất

- Giới hạn quyền đọc thư mục và tệp cho tài khoản dịch vụ hoặc nhóm vận hành cần thiết.
- Không lưu tệp lâu hơn thời gian nghiệp vụ yêu cầu.
- Mã hóa khi lưu trữ và khi chuyển qua mạng.
- Ghi nhận người yêu cầu, câu truy vấn/phạm vi, thời gian và vị trí tệp.
- Xóa bản tạm theo quy trình có kiểm soát sau khi xác nhận bên nhận đã nhận đủ dữ liệu.
- Tránh ghi đường dẫn chứa thông tin nhạy cảm vào log ứng dụng công khai.

## 7. Tệp phải chưa tồn tại

MySQL không ghi đè một tệp đã tồn tại bằng SELECT INTO OUTFILE. Nếu tệp đích đã có, lệnh thường trả lỗi:

~~~text
ERROR 1086 (HY000): File ... already exists
~~~

Hãy dùng tên file mới cho mỗi lần xuất, ví dụ gắn ngày giờ hoặc mã lần chạy. Không xóa file cũ tự động trước khi xác nhận file đó không còn được quy trình khác sử dụng.

Ví dụ tên tệp theo ngày có thể được tạo bởi ứng dụng hoặc quy trình điều phối, rồi truyền thành literal an toàn trong câu SQL. Không nối chuỗi đường dẫn trực tiếp từ input người dùng mà không kiểm tra; tránh cho phép người gọi tùy ý chọn đường dẫn trên server.

SELECT INTO OUTFILE không tạo thư mục cha. Thư mục phải tồn tại trước, nằm trong secure_file_priv và có quyền ghi phù hợp.

## 8. Phân biệt OUTFILE, DUMPFILE và xuất ở phía client

| Cách xuất | Nơi tạo tệp | Định dạng | Khi nên dùng |
|---|---|---|---|
| SELECT INTO OUTFILE | Máy chủ MySQL | Các hàng dạng văn bản có delimiter/escape | Xuất tập dữ liệu có định dạng TSV/CSV từ server |
| SELECT INTO DUMPFILE | Máy chủ MySQL | Dữ liệu nhị phân thô của một hàng | Xuất một giá trị nhị phân hoặc một hàng theo cách không thêm delimiter |
| Xuất ở phía client | Máy chạy ứng dụng hoặc SQL client | Phụ thuộc công cụ | Cần ghi file trực tiếp trên máy client hoặc không muốn cấp FILE |

**SELECT INTO DUMPFILE** chỉ ghi một hàng và không thêm định dạng phân cách trường/hàng. Nó không phải lựa chọn thay thế cho CSV nhiều hàng.

Nếu cần tệp trên máy client, có thể dùng ứng dụng, thư viện database hoặc công cụ xuất dữ liệu chạy tại client. Ví dụ, MySQL Shell có tiện ích export table phù hợp cho một số luồng xuất. Cần kiểm tra đường dẫn đầu ra của công cụ đó vì file thường được ghi trên máy đang chạy Shell, khác với OUTFILE.

Xuất ở phía client có thể tránh cấp quyền FILE cho user database, nhưng ứng dụng vẫn cần quyền SELECT và phải bảo vệ file đầu ra tương tự.

## 9. Kết hợp OUTFILE với LOAD DATA INFILE

Một quy trình di chuyển dữ liệu dạng text thường có hai bước:

1. Xuất dữ liệu từ nguồn bằng SELECT INTO OUTFILE.
2. Chuyển tệp sang máy chủ đích qua kênh an toàn và nạp bằng LOAD DATA INFILE hoặc công cụ tương thích.

Ví dụ nạp TSV:

~~~sql
LOAD DATA INFILE '/var/lib/mysql-files/orders.tsv'
INTO TABLE sales.orders_import
CHARACTER SET utf8mb4
FIELDS TERMINATED BY '\t'
LINES TERMINATED BY '\n'
(order_id, customer_id, created_at, total_amount);
~~~

Định dạng của LOAD DATA phải khớp với cách SELECT INTO OUTFILE đã ghi. Nếu dùng cùng một thư mục trên cùng server, vẫn cần bảo đảm file được chuyển vào đúng vị trí và có quyền đọc.

Phân biệt:

- **LOAD DATA INFILE** đọc file trên máy chủ MySQL.
- **LOAD DATA LOCAL INFILE** đọc file từ máy client gửi lên server; tính năng LOCAL cần được bật và cho phép ở cả client lẫn server theo cấu hình.

Không bật LOCAL INFILE rộng rãi chỉ để tiện nhập một file. Kiểm soát nguồn file, client được phép kết nối và quyền của tài khoản nạp dữ liệu.

Khi nạp dữ liệu vào bảng đích, nên dùng bảng staging, kiểm tra kiểu dữ liệu và số dòng, xác thực ràng buộc rồi mới hợp nhất vào bảng nghiệp vụ. Không nạp trực tiếp vào bảng production nếu chưa có kế hoạch xử lý dữ liệu lỗi, trùng khóa và rollback.

## 10. Các lỗi thường gặp và cách xử lý

### Server từ chối do secure_file_priv

Lỗi có thể xuất hiện khi đường dẫn nằm ngoài thư mục được cho phép hoặc secure_file_priv đang là NULL. Kiểm tra:

~~~sql
SHOW VARIABLES LIKE 'secure_file_priv';
~~~

Chọn một đường dẫn nằm trong thư mục được cấu hình. Nếu chính sách cần thay đổi, cập nhật cấu hình máy chủ và khởi động lại theo quy trình. Không tìm cách né giới hạn bằng đường dẫn khác hoặc thay đổi quyền hệ điều hành không được phê duyệt.

### Thiếu quyền FILE

Kiểm tra:

~~~sql
SHOW GRANTS FOR CURRENT_USER();
~~~

Nếu tài khoản được phép thực hiện xuất dữ liệu, cấp FILE tạm thời theo quy trình phê duyệt và thu hồi khi hoàn tất. Đồng thời xác nhận tài khoản có SELECT trên các bảng cần xuất.

### Không có quyền ghi file

MySQL có thể báo không tạo được file dù tài khoản SQL có FILE. Kiểm tra thư mục có tồn tại không, tài khoản hệ điều hành chạy mysqld có quyền ghi không, dung lượng đĩa còn đủ không và hệ thống kiểm soát truy cập như SELinux hoặc AppArmor có chặn không.

### Tệp đã tồn tại

Chọn một tên file mới hoặc xử lý file cũ theo quy trình lưu trữ. MySQL không ghi đè file đã có bằng INTO OUTFILE.

### File được tạo nhưng nội dung sai định dạng

Kiểm tra character set, delimiter, enclosure, escape, quy tắc NULL và ký tự kết thúc dòng. Xuất một tập dữ liệu nhỏ có đủ trường hợp đặc biệt, sau đó mở bằng parser của hệ thống nhận để xác minh.

### Tệp quá lớn hoặc truy vấn chạy lâu

Giảm phạm vi bằng bộ lọc, chia theo khoảng khóa hoặc thời gian, kiểm tra execution plan và chọn index phù hợp. Theo dõi I/O, dung lượng đĩa và tải của server. Nếu cần xuất khối lượng lớn định kỳ, cân nhắc job batch hoặc công cụ export có khả năng resume và giới hạn tải.

## 11. Quy trình xuất dữ liệu an toàn

Trước khi chạy:

1. Xác nhận người yêu cầu, mục đích, bảng và cột cần xuất.
2. Kiểm tra dữ liệu nhạy cảm và yêu cầu masking.
3. Kiểm tra FILE, SELECT và secure_file_priv.
4. Xác nhận thư mục tồn tại, quyền filesystem và dung lượng đĩa.
5. Chạy thử truy vấn với giới hạn hàng và kiểm tra định dạng.
6. Xác định tên file mới và người nhận.

Trong khi chạy:

- Theo dõi thời gian truy vấn, số hàng, tải I/O và dung lượng tệp.
- Tránh xuất đồng thời nhiều tập dữ liệu lớn trên máy chủ đang chịu tải cao.
- Ghi nhận thông tin lần chạy và lỗi nếu có.

Sau khi chạy:

- Kiểm tra file tồn tại, kích thước hợp lý và có thể đọc được.
- Đếm số hàng trong tệp bằng parser phù hợp, không chỉ đếm số dòng nếu trường có thể chứa newline.
- So sánh số bản ghi với truy vấn nguồn trong cùng phạm vi.
- Kiểm tra encoding, NULL, dấu phân cách và các trường đặc biệt.
- Chuyển file qua kênh được bảo vệ, xác nhận bên nhận đã nhận đủ.
- Thu hồi FILE nếu là quyền cấp tạm và dọn bản sao theo retention.

## 12. Checklist

- [ ] Đã xác định tệp được tạo trên máy chủ hay máy client.
- [ ] Đã kiểm tra secure_file_priv và chọn đúng thư mục.
- [ ] Tài khoản có SELECT trên dữ liệu và FILE theo đúng nhu cầu.
- [ ] Tài khoản hệ điều hành chạy mysqld có quyền ghi vào thư mục.
- [ ] Tệp đích chưa tồn tại và thư mục cha đã được tạo.
- [ ] Đã chọn cột, lọc hàng và loại bỏ dữ liệu không cần thiết.
- [ ] Đã xác định character set, delimiter, enclosure, escape và line ending.
- [ ] Đã kiểm thử NULL, chuỗi rỗng, dấu phẩy, dấu nháy và newline.
- [ ] Đã kiểm tra dung lượng, hiệu năng và tải server.
- [ ] Tệp được bảo vệ khi lưu và truyền; quyền tạm đã được thu hồi.

## Kết luận

SELECT INTO OUTFILE là cách xuất dữ liệu trực tiếp từ MySQL Server ra một tệp có định dạng kiểm soát được. Để dùng an toàn, cần phối hợp quyền SELECT, quyền toàn cục FILE, giới hạn thư mục secure_file_priv và quyền filesystem của tiến trình mysqld. Hãy chỉ xuất các cột và hàng cần thiết, kiểm thử định dạng với dữ liệu đặc biệt, bảo vệ tệp sau khi tạo và xác minh kết quả trước khi chuyển sang hệ thống khác.
