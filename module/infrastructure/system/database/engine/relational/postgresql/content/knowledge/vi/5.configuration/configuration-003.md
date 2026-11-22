# Thứ tự ưu tiên giữa cấu hình máy chủ, database, role và phiên trong PostgreSQL

Một hệ thống PostgreSQL có thể phục vụ nhiều ứng dụng trên cùng một instance: ứng dụng bán hàng cần phản hồi nhanh, công cụ báo cáo chạy những câu truy vấn tổng hợp dài, còn tác vụ quản trị cần giới hạn thời gian chờ khóa. Nếu tất cả sử dụng một bộ tham số chung, việc tối ưu cho nhóm này đôi khi lại gây vấn đề cho nhóm khác.

PostgreSQL giải quyết bài toán bằng hệ thống **tham số cấu hình** (*configuration parameters*, thường gọi là **GUC – Grand Unified Configuration**). Một tham số như `work_mem` hay `statement_timeout` có thể được khai báo ở **mức máy chủ**, **database**, **role**, **cặp role–database**, hoặc điều chỉnh trong **phiên làm việc** và **giao dịch**.

Khi nhiều nơi cùng đặt một tham số, câu hỏi quan trọng không phải “nơi nào được cấu hình trước”, mà là **nguồn nào có độ ưu tiên cao hơn, và giá trị nào thực sự đang có hiệu lực trong phiên đang kết nối?**

Bài học này hướng dẫn cách xác định thứ tự ưu tiên, thực hành quan sát bằng `SHOW` và `pg_settings`, giải thích các trường hợp ngoại lệ do quyền hoặc loại tham số, rồi áp dụng vào việc vận hành ứng dụng PostgreSQL.

## 1. Cấu hình PostgreSQL có nhiều phạm vi

Hãy tưởng tượng server phục vụ hai database và nhiều tài khoản:

~~~text
                     PostgreSQL instance
                             |
          postgresql.conf / ALTER SYSTEM / -c
                             |
                +------------+------------+
                |                         |
           Database shopdb          Database reportdb
                |                         |
          Role app_user              Role analyst
                |                         |
           Session A                  Session B
                |
         BEGIN ... SET LOCAL ...
                |
        Câu SQL đang thực thi
~~~

Ví dụ một người quản trị muốn:

- Mọi kết nối mặc định dùng `statement_timeout = '30s'`.
- Riêng database báo cáo cho phép tối đa `'2min'`.
- Tài khoản chạy batch có giá trị `'5min'` dù kết nối đến database nào.
- Khi batch chạy trong database báo cáo, dùng riêng `'90s'` cho cặp tài khoản–database.
- Một transaction đặc biệt chỉ cần giới hạn `'10s'`, rồi tự trở về cấu hình của phiên.

PostgreSQL có cơ chế cho từng trường hợp này mà không cần sửa cấu hình toàn server mỗi lần có một truy vấn khác biệt.

### Một vài tham số thường gặp

| Tham số | Ý nghĩa | Phạm vi thay đổi thông dụng |
| --- | --- | --- |
| `work_mem` | Bộ nhớ tối đa cho một số thao tác sort/hash trước khi cần dùng giải pháp khác; không phải tổng RAM cho cả query | Server, database, role, session/transaction |
| `statement_timeout` | Giới hạn thời gian thực thi câu lệnh theo quy tắc PostgreSQL | Server, database, role, session/transaction |
| `lock_timeout` | Giới hạn thời gian chờ lấy khóa | Server, database, role, session/transaction |
| `search_path` | Thứ tự tìm schema khi tên đối tượng không được chỉ rõ schema | Server, database, role, session/transaction |
| `TimeZone` | Múi giờ dùng để diễn giải/hiển thị một số dữ liệu thời gian | Server, database, role, session/transaction |
| `shared_buffers` | Kích thước bộ nhớ đệm dữ liệu dùng chung của instance | Cấu hình máy chủ; thường cần restart |
| `max_connections` | Giới hạn kết nối tới instance | Cấu hình máy chủ; cần restart |

**Không phải mọi tham số đều điều chỉnh được ở mọi phạm vi.** `work_mem` có thể đặt bằng `SET` trong session, nhưng `shared_buffers` và `max_connections` không thể đổi theo từng session. PostgreSQL phân loại tham số theo **context** và quyền cần thiết; phần sau sẽ giải thích rõ.

## 2. Quy tắc ưu tiên cốt lõi

Đối với một **tham số cho phép đặt ở tất cả các mức liên quan**, có thể ghi nhớ thứ tự từ **mặc định ít cụ thể hơn** tới **giá trị áp dụng riêng hơn**:

~~~text
        Mặc định bên trong PostgreSQL
                    │
                    ▼
       Cấu hình server / cluster
          postgresql.conf, ...
                    │
                    ▼
          ALTER DATABASE ... SET
                    │
                    ▼
            ALTER ROLE ... SET
                    │
                    ▼
     ALTER ROLE ... IN DATABASE ... SET
                    │
                    ▼
       Tùy chọn gửi khi mở kết nối
       (ví dụ options / PGOPTIONS)
                    │
                    ▼
          SET ... trong session
                    │
                    ▼
      SET LOCAL ... trong transaction
       (chỉ trong phạm vi phù hợp)
~~~

Thứ tự này là **mô hình thực hành** cho các tham số có thể được đặt tại các mức trên, không phải khẳng định rằng mọi tham số đều hỗ trợ mọi nguồn. Cấu hình server còn có thứ tự ưu tiên nội bộ giữa các file, tùy chọn dòng lệnh và giá trị ghi bởi `ALTER SYSTEM`.

### Bảng so sánh nguồn cấu hình

| Nguồn | Cú pháp ví dụ | Áp dụng ở đâu? | Khi nào thấy tác dụng? |
| --- | --- | --- | --- |
| Server | `work_mem = '4MB'` trong file cấu hình | Mặc định toàn instance, trừ nơi được ghi đè | Sau khi cấu hình được nạp phù hợp |
| Database | `ALTER DATABASE shopdb SET work_mem = '8MB';` | Phiên mới kết nối tới `shopdb` | Lần kết nối mới |
| Role | `ALTER ROLE app_user SET work_mem = '16MB';` | Phiên mới đăng nhập bằng role `app_user` | Lần đăng nhập mới |
| Role trong database | `ALTER ROLE app_user IN DATABASE shopdb SET work_mem = '24MB';` | Phiên mới đăng nhập bằng `app_user` tới `shopdb` | Lần đăng nhập mới |
| Client startup options | `PGOPTIONS='-c work_mem=28MB'` | Kết nối gửi tùy chọn đó | Khi tạo kết nối |
| Session | `SET work_mem = '32MB';` | Phiên đang chạy lệnh | Sau khi lệnh có hiệu lực; chịu quy tắc transaction |
| Transaction | `SET LOCAL work_mem = '48MB';` | Transaction hiện tại | Cho phần còn lại của transaction, theo các quy tắc phạm vi |

Nếu cả bốn mức **server, database, role và role–database** cùng đặt `work_mem`, phiên đăng nhập bằng `app_user` tới `shopdb` sẽ dùng giá trị role–database `24MB`, trừ khi có nguồn ưu tiên cao hơn hoặc một cơ chế giới hạn riêng.

### Database hay role ưu tiên cao hơn?

Đây là điểm thường dễ nhầm:

~~~sql
ALTER DATABASE shopdb SET work_mem = '8MB';
ALTER ROLE app_user SET work_mem = '16MB';
~~~

Khi `app_user` đăng nhập vào `shopdb` bằng một **kết nối mới**, giá trị role `16MB` có ưu tiên hơn giá trị database `8MB`.

Nếu có thêm:

~~~sql
ALTER ROLE app_user
IN DATABASE shopdb
SET work_mem = '24MB';
~~~

thì **thiết lập dành cho đúng cặp role–database** ưu tiên hơn cả hai thiết lập riêng lẻ.

Quy tắc này giúp người quản trị xây dựng mặc định chung cho database, rồi chuyên biệt hóa theo loại tài khoản sử dụng database đó.

## 3. Cấu hình máy chủ: các file và tùy chọn khởi động

Các tham số chung của PostgreSQL thường nằm trong `postgresql.conf` hoặc các file được include. Bạn có thể xem các đường dẫn hiện tại bằng:

~~~sql
SHOW config_file;
SHOW data_directory;
SHOW hba_file;
~~~

Ví dụ vài dòng trong `postgresql.conf`:

~~~conf
# Giá trị mẫu, không phải cấu hình bắt buộc:
work_mem = '4MB'
statement_timeout = '30s'
log_min_duration_statement = '1s'
~~~

Các giá trị trong file cấu hình thường đóng vai trò **mặc định** cho các phiên, cho tới khi database, role hoặc session ghi đè.

### 3.1. include và include_dir

PostgreSQL cho phép tách cấu hình thành nhiều file:

~~~conf
include = 'common.conf'
include_if_exists = 'optional.conf'
include_dir = 'conf.d'
~~~

Khi cùng một tham số được đặt nhiều lần trong những file được nạp theo thứ tự, giá trị có hiệu lực phụ thuộc **thứ tự xử lý cấu hình**. Với `include_dir`, thứ tự tên file có ý nghĩa. Đừng chỉ tìm một dòng đầu tiên trong `postgresql.conf` rồi kết luận đó là giá trị cuối cùng.

### 3.2. ALTER SYSTEM và postgresql.auto.conf

Quản trị viên có thể dùng:

~~~sql
-- Lệnh minh họa: thay đổi cấu hình toàn instance.
ALTER SYSTEM SET work_mem = '6MB';
~~~

`ALTER SYSTEM` ghi thiết lập vào `postgresql.auto.conf` trong thư mục dữ liệu. Tệp này có thứ tự ưu tiên cao hơn các thiết lập trong `postgresql.conf` thông thường và các include liên quan.

Điểm cần phân biệt:

- `ALTER SYSTEM` **không có nghĩa** đang đổi `work_mem` riêng cho người chạy lệnh.
- Với tham số có thể reload, thay đổi được áp dụng sau khi server nạp lại cấu hình phù hợp.
- Với tham số cần restart, reload chưa đủ.
- `ALTER SYSTEM` là thao tác quản trị, yêu cầu quyền phù hợp và không chạy trong transaction block.

Muốn làm mới cấu hình đối với các tham số reload được, quản trị viên có thể dùng:

~~~sql
SELECT pg_reload_conf();
~~~

Giá trị `true` trả về cho biết yêu cầu gửi tín hiệu reload được thực hiện, **không phải chứng nhận mọi tham số đã được áp dụng thành công**. Cần xem log, `pg_settings` và trạng thái chờ restart để biết kết quả.

Khi muốn bỏ override từ `ALTER SYSTEM`:

~~~sql
ALTER SYSTEM RESET work_mem;
SELECT pg_reload_conf();
~~~

Việc reset trên server không tự xóa các override tại database, role hoặc session. Đây là lý do thường gặp khi file cấu hình được sửa mà một ứng dụng vẫn dùng giá trị khác.

### 3.3. Tùy chọn dòng lệnh của server

Một PostgreSQL server có thể được khởi động với tùy chọn `-c`:

~~~bash
# Minh họa cú pháp khởi động, không chạy nếu server đang hoạt động.
postgres -D /path/to/pgdata -c work_mem=8MB
~~~

Các tham số được đưa vào dòng lệnh khởi động server có độ ưu tiên cao trong **tầng cấu hình máy chủ** so với file. Tuy nhiên, quyền sửa tham số theo database/role/session vẫn phụ thuộc **context** của chính tham số; không thể thay đổi `shared_buffers` bằng `SET LOCAL` chỉ vì biết một thứ tự ưu tiên tổng quát.

Trong hệ thống chạy qua systemd hoặc container, tùy chọn khởi động có thể đến từ unit file, entrypoint hoặc công cụ quản lý cấu hình, không nhất thiết hiển thị trực tiếp tại `postgresql.conf`.

## 4. ALTER DATABASE SET: mặc định dành cho một database

Giả sử database báo cáo cần `statement_timeout` dài hơn mặc định chung:

~~~sql
ALTER DATABASE reportdb
SET statement_timeout = '2min';
~~~

Giá trị này được dùng cho **những phiên mới** kết nối vào `reportdb`, nếu không có thiết lập role, cặp role–database hoặc nguồn ưu tiên cao hơn.

Nó **không**:

- Thay đổi `statement_timeout` cho mọi database khác.
- Ngay lập tức thay đổi phiên đã kết nối từ trước.
- Cấp quyền truy cập bảng hoặc thay đổi role đăng nhập.
- Cho phép thay đổi các tham số thuộc loại chỉ cấu hình khi server khởi động.

Xóa thiết lập mặc định theo database:

~~~sql
ALTER DATABASE reportdb
RESET statement_timeout;
~~~

Sau đó, những phiên mới không còn nhận override tương ứng từ database này, nhưng có thể vẫn nhận giá trị từ role, cặp role–database, server hoặc client startup options.

### Mặc định database không phải transaction của database

`ALTER DATABASE ... SET` thay đổi **cấu hình mặc định cho kết nối tương lai**, không phải chạy một transaction nghiệp vụ trên tất cả bảng của database. Nó không quét các hàng để cập nhật dữ liệu và không đổi toàn bộ session hiện hữu.

Một database có thể có nhiều role với những tham số khác nhau. Khi đó, để xác định giá trị thực tế cần xét **role cụ thể đang đăng nhập**.

## 5. ALTER ROLE SET: mặc định của người đăng nhập

Đặt giá trị theo role:

~~~sql
ALTER ROLE report_reader
SET statement_timeout = '45s';
~~~

Với một phiên **mới đăng nhập** bằng role `report_reader`, thiết lập `45s` có ưu tiên hơn cấu hình riêng của database nếu cả hai cùng quy định tham số đó.

Thu hồi thiết lập:

~~~sql
ALTER ROLE report_reader
RESET statement_timeout;
~~~

Đây là thao tác **reset một tham số mặc định đã gắn cho role**, không phải xóa role và không phải reset tất cả giá trị cấu hình của server.

### Gán role khác với đăng nhập bằng role đó

Một tài khoản `service_user` có thể là thành viên của role `report_reader`, nhưng **thiết lập `ALTER ROLE report_reader SET ...` không tự được kế thừa chỉ vì có quan hệ thành viên role**.

Tương tự, chạy:

~~~sql
SET ROLE report_reader;
~~~

trong một phiên đã đăng nhập bằng role khác làm thay đổi ngữ cảnh quyền theo quy tắc `SET ROLE`; nó **không nạp lại** các mặc định GUC của `report_reader` như thể phiên vừa đăng nhập mới bằng role đó.

Do vậy:

> Khi dựa vào `ALTER ROLE ... SET` để thiết kế tham số vận hành, hãy xác định **role đăng nhập lúc mở kết nối**, không chỉ role hiệu lực sau `SET ROLE`.

Đây là điểm đặc biệt quan trọng trong ứng dụng có connection pool và hệ thống phân quyền theo nhóm role.

## 6. ALTER ROLE IN DATABASE: cấu hình chuyên biệt nhất của cặp role–database

Một tài khoản có thể cần cấu hình khác nhau khi vào hai database:

~~~sql
ALTER ROLE report_reader
IN DATABASE reportdb
SET statement_timeout = '90s';
~~~

Thiết lập này áp dụng khi thỏa **đồng thời**:

1. Phiên mới đăng nhập bằng `report_reader`.
2. Phiên đó kết nối vào `reportdb`.

Nếu `report_reader` kết nối tới `shopdb`, cấu hình của cặp `report_reader/reportdb` **không áp dụng**. Khi ấy, PostgreSQL xét giá trị theo role, database đích khác và server.

Thứ tự trong trường hợp cụ thể:

~~~text
Server:                  statement_timeout = 30s
Database reportdb:       statement_timeout = 2min
Role report_reader:      statement_timeout = 45s
Role + database:         statement_timeout = 90s

Kết nối report_reader → reportdb: 90s
Kết nối report_reader → shopdb:   45s
Kết nối role khác    → reportdb:  2min
Kết nối role khác    → shopdb:    30s (nếu không có override khác)
~~~

Các kết quả giả định rằng không có `PGOPTIONS`, `SET` hoặc tham số nguồn khác có độ ưu tiên cao hơn.

Để bỏ cấu hình của đúng cặp:

~~~sql
ALTER ROLE report_reader
IN DATABASE reportdb
RESET statement_timeout;
~~~

Sau reset, kết nối mới bằng `report_reader` tới `reportdb` sẽ quay về giá trị phù hợp tiếp theo trong chuỗi ưu tiên, ở ví dụ trên là `45s` từ thiết lập role.

## 7. Cấu hình của phiên bằng SET và RESET

Sau khi kết nối thành công, người dùng có thể điều chỉnh một số tham số được phép ở mức session:

~~~sql
SHOW work_mem;

SET work_mem = '32MB';

SHOW work_mem;
~~~

`SET work_mem` thay đổi giá trị của **phiên đang chạy**, không sửa `postgresql.conf`, không thay đổi các phiên khác và không tạo mặc định mới cho những lần đăng nhập sau.

### 7.1. RESET trả về giá trị nào?

~~~sql
RESET work_mem;
SHOW work_mem;
~~~

`RESET work_mem` khôi phục giá trị **mặc định có hiệu lực của phiên** theo những nguồn cấu hình được nạp khi tạo kết nối và các quy tắc liên quan; nó không nhất thiết trả về giá trị biên dịch gốc của PostgreSQL.

Ví dụ:

~~~text
Server = 4MB
Database = 8MB
Role = 16MB
Role+database = 24MB

Kết nối mới ban đầu: 24MB
SET work_mem = '32MB': 32MB
RESET work_mem: 24MB
~~~

Đây là lý do `RESET` không đồng nghĩa với “xóa toàn bộ thiết lập theo database và role”.

### 7.2. RESET ALL

~~~sql
RESET ALL;
~~~

Lệnh này đưa các tham số có thể reset trong phiên về những giá trị mặc định của session theo cơ chế PostgreSQL. Nó không xóa cấu hình trong file, `ALTER DATABASE SET` hay `ALTER ROLE SET`.

### 7.3. SET trong transaction và ROLLBACK

Một chi tiết quan trọng: `SET` thực thi **bên trong một transaction** chịu quy tắc commit/rollback.

~~~sql
SHOW work_mem;         -- Giả sử 24MB.

BEGIN;
SET work_mem = '32MB';
SHOW work_mem;         -- 32MB trong transaction.
ROLLBACK;

SHOW work_mem;         -- Trở lại 24MB.
~~~

Nếu transaction `COMMIT` thay vì `ROLLBACK`, thay đổi `SET` thông thường có thể tiếp tục tồn tại trong session cho tới khi được reset, đặt lại hoặc session kết thúc.

Vì vậy câu “`SET` luôn có hiệu lực đến hết kết nối” là **chưa đủ chính xác**: khi nằm trong một transaction thất bại/rollback, hiệu ứng của nó có thể bị đảo ngược.

## 8. SET LOCAL: ưu tiên trong phạm vi giao dịch

Khi chỉ một transaction cần cấu hình khác, sử dụng `SET LOCAL`:

~~~sql
SHOW work_mem;  -- Ví dụ 24MB.

BEGIN;

SET LOCAL work_mem = '48MB';
SHOW work_mem;  -- 48MB ở phần còn lại của transaction.

-- Truy vấn cần dùng cấu hình này.
SELECT current_setting('work_mem');

COMMIT;

SHOW work_mem;  -- Trở về giá trị có hiệu lực trước SET LOCAL.
~~~

Điểm quan trọng:

- `SET LOCAL` chỉ có hiệu lực trong transaction đang mở và trong phạm vi còn hiệu lực theo quy tắc PostgreSQL.
- Khi transaction kết thúc bằng `COMMIT` hoặc `ROLLBACK`, hiệu ứng `SET LOCAL` biến mất.
- Dùng `SET LOCAL` ngoài transaction block không mang ý nghĩa “đặt cho câu SQL kế tiếp”; PostgreSQL cảnh báo và không tạo một phạm vi transaction kéo dài để giữ giá trị đó.
- Nếu dùng savepoint rồi rollback về savepoint trước lệnh thiết lập, hiệu ứng của lệnh `SET`/`SET LOCAL` tại phần bị rollback cũng có thể được hoàn nguyên.

### Phân biệt SET và SET LOCAL

| Tiêu chí | `SET work_mem = '32MB'` | `SET LOCAL work_mem = '48MB'` |
| --- | --- | --- |
| Phạm vi chính | Session | Transaction hiện tại |
| Có thể dùng ngoài `BEGIN`? | Có | Không hữu ích ngoài transaction block |
| Sau `COMMIT` | Có thể còn hiệu lực trong session | Hết hiệu lực |
| Sau `ROLLBACK` nếu đặt trong transaction | Thay đổi đặt trong transaction bị rollback | Hết hiệu lực |
| Có đổi mặc định database/role? | Không | Không |
| Có tự tác động tới connection khác? | Không | Không |

### Ví dụ ứng dụng: giới hạn một transaction báo cáo

~~~sql
BEGIN;

SET LOCAL statement_timeout = '10s';
SET LOCAL lock_timeout = '2s';

SELECT
    customer_id,
    SUM(total_amount)
FROM sales_orders
GROUP BY customer_id;

COMMIT;
~~~

`sales_orders` là bảng **giả định**. Ví dụ thể hiện cách giới hạn timeout cho **transaction hiện tại**, không thay đổi timeout của các câu truy vấn sau khi transaction kết thúc.

**Lưu ý:** nếu một câu lệnh bị timeout và làm transaction rơi vào trạng thái lỗi, ứng dụng cần `ROLLBACK` hoặc xử lý savepoint phù hợp. `SET LOCAL` không tự biến một transaction thất bại thành transaction thành công.

## 9. Cấu hình từ client khi tạo kết nối

Ngoài cấu hình server, database, role và `SET`, client có thể gửi tùy chọn cấu hình khi khởi tạo kết nối. Với `libpq`/`psql`, môi trường Unix shell có thể dùng `PGOPTIONS`:

~~~bash
PGOPTIONS='-c work_mem=28MB -c statement_timeout=15s' \
  psql -h 127.0.0.1 -U app_user -d shopdb
~~~

Lệnh minh họa giả định account và database tồn tại. Trong kết nối mới:

~~~sql
SHOW work_mem;
SHOW statement_timeout;
~~~

Các tùy chọn client có thể ghi đè giá trị mặc định của database và role đối với tham số **được phép** thiết lập theo cách này. Một `SET` hợp lệ chạy sau khi kết nối vẫn có thể đổi giá trị của phiên.

Không nhầm:

- Biến môi trường `PGOPTIONS` là cách **libpq gửi startup options**, không sửa cấu hình máy chủ.
- Không phải mọi ứng dụng đều dùng libpq; Java JDBC có cơ chế truyền tùy chọn của driver riêng.
- Một tham số cần restart server không thể được thay đổi hợp lệ chỉ bằng startup options của client.
- Khi xem nguồn trong `pg_settings`, giá trị có thể được mô tả là đến từ client/startup packet thay vì từ `ALTER ROLE`.

Trong hệ thống có connection pool, mỗi **kết nối vật lý được tạo mới** mới trải qua bước startup này. Một request HTTP mượn lại connection cũ có thể nhận giá trị session đã thay đổi từ request trước nếu pool không quản lý/reset trạng thái phù hợp.

## 10. Thực hành có thể tái hiện: quan sát từng mức ưu tiên

Phần này dùng tham số `work_mem` vì nó hỗ trợ cấu hình trong phiên. Ví dụ triển khai trên **database thử nghiệm**, bằng tài khoản quản trị được phép tạo role/database và sửa các mặc định tương ứng.

Lưu ý: các giá trị MB ở đây phục vụ việc **quan sát mức ưu tiên**, không phải đề xuất tối ưu `work_mem` trên server sản xuất. `work_mem` có thể được tiêu thụ bởi **nhiều thao tác của mỗi truy vấn, nhiều phiên và parallel workers**; đặt quá cao ở phạm vi rộng có thể làm tăng nguy cơ thiếu RAM.

### Bước 1. Tạo role và database thực hành

Trong phiên quản trị:

~~~sql
CREATE ROLE cfg_student
LOGIN PASSWORD 'REPLACE_WITH_STRONG_LAB_SECRET';

CREATE DATABASE cfg_demo OWNER cfg_student;
~~~

`REPLACE_WITH_STRONG_LAB_SECRET` chỉ là chuỗi giữ chỗ; phải thay bằng mật khẩu riêng phù hợp môi trường. `CREATE DATABASE` cần chạy ngoài transaction block và có thể bị từ chối nếu tài khoản thiếu `CREATEDB` hoặc quyền quản trị tương ứng.

Nếu role hoặc database đã tồn tại, không chạy ghi đè mà chưa xác minh trạng thái. Phần hướng dẫn giả định tên `cfg_student` và `cfg_demo` chưa được sử dụng.

### Bước 2. Đặt giá trị ở mức database

~~~sql
ALTER DATABASE cfg_demo
SET work_mem = '8MB';
~~~

Mở **một kết nối mới** bằng `cfg_student` tới `cfg_demo`:

~~~bash
psql -h 127.0.0.1 -p 5432 -U cfg_student -d cfg_demo
~~~

Trong phiên vừa mở:

~~~sql
SHOW work_mem;
-- Dự kiến 8MB nếu không có override khác.
~~~

Đóng kết nối này trước bước tiếp theo:

~~~text
\q
~~~

### Bước 3. Đặt giá trị ở mức role

Trong phiên quản trị:

~~~sql
ALTER ROLE cfg_student
SET work_mem = '16MB';
~~~

Mở lại `psql` bằng `cfg_student` tới `cfg_demo`:

~~~sql
SHOW work_mem;
-- Dự kiến 16MB: role ghi đè database.
~~~

Vì mức role đã đặt `16MB`, cấu hình `8MB` của database chưa bị xóa nhưng không còn quyết định kết quả cho phiên đăng nhập bằng role này.

Đóng phiên thử trước bước kế tiếp.

### Bước 4. Đặt giá trị dành riêng cho cặp role–database

Trong phiên quản trị:

~~~sql
ALTER ROLE cfg_student
IN DATABASE cfg_demo
SET work_mem = '24MB';
~~~

Mở một kết nối **mới** tới `cfg_demo` bằng `cfg_student`:

~~~sql
SHOW work_mem;
-- Dự kiến 24MB: cặp role–database ưu tiên cao nhất
-- trong ba mức database/role/role–database.
~~~

Nếu cùng role đăng nhập tới một database khác mà không có override riêng, thiết lập `24MB` **không tự áp dụng** cho database kia; khi đó giá trị role `16MB` là ứng viên phù hợp.

### Bước 5. Ghi đè tạm trong phiên

Ngay trong kết nối `cfg_student` vừa mở:

~~~sql
SET work_mem = '32MB';
SHOW work_mem;
-- 32MB

RESET work_mem;
SHOW work_mem;
-- Trở lại 24MB của cặp role–database trong ví dụ.
~~~

`RESET` không xóa các cấu hình do quản trị viên đã đặt. Nó chỉ đưa giá trị session trở về mặc định hiện hành tương ứng.

### Bước 6. Ghi đè trong transaction

~~~sql
SHOW work_mem;
-- 24MB

BEGIN;
SET LOCAL work_mem = '48MB';
SHOW work_mem;
-- 48MB

COMMIT;

SHOW work_mem;
-- 24MB
~~~

Hoặc thử rollback:

~~~sql
BEGIN;
SET work_mem = '32MB';
SHOW work_mem;
-- 32MB

ROLLBACK;
SHOW work_mem;
-- 24MB vì SET nằm trong transaction đã rollback.
~~~

Chuỗi này minh họa rõ ranh giới **mặc định khi đăng nhập**, **ghi đè của session**, và **ghi đè chỉ có hiệu lực trong transaction**.

### Bước 7. Gỡ từng lớp và xem giá trị rơi về đâu

Đóng phiên `cfg_student` hiện có. Trong phiên quản trị:

~~~sql
-- Gỡ cấu hình chuyên biệt nhất:
ALTER ROLE cfg_student
IN DATABASE cfg_demo
RESET work_mem;
~~~

Kết nối mới bằng `cfg_student` tới `cfg_demo` sẽ thấy `16MB` từ role.

Tiếp tục:

~~~sql
ALTER ROLE cfg_student
RESET work_mem;
~~~

Kết nối mới sẽ thấy `8MB` từ database.

Cuối cùng:

~~~sql
ALTER DATABASE cfg_demo
RESET work_mem;
~~~

Kết nối mới không còn ba override này và sẽ lấy giá trị phù hợp từ cấu hình server/nguồn kết nối khác. **Không nên mặc định nó chắc chắn là `4MB`** nếu server thực tế có cấu hình riêng hoặc client truyền `PGOPTIONS`.

**Quan trọng cho toàn bộ thí nghiệm:** sau mỗi lệnh `ALTER DATABASE` hoặc `ALTER ROLE`, phải tạo **kết nối mới** để đánh giá kết quả. Không dựa vào `SHOW work_mem` trong một kết nối được mở trước thay đổi để kết luận lệnh quản trị không có tác dụng.

### Bước 8. Dọn môi trường thực hành khi không còn dùng

Đảm bảo đã đóng tất cả kết nối tới `cfg_demo`. Trong phiên quản trị:

~~~sql
DROP DATABASE cfg_demo;
DROP ROLE cfg_student;
~~~

`DROP DATABASE` không thể chạy trong transaction block và sẽ thất bại nếu còn kết nối tới database đích theo các quy tắc áp dụng. **Không dùng `WITH (FORCE)` hoặc chấm dứt kết nối tùy tiện** chỉ để hoàn thành bài thực hành, vì có thể ảnh hưởng người khác đang sử dụng database.

Chỉ xóa hai đối tượng này nếu chắc chắn chúng được tạo **riêng cho bài lab** và không chứa dữ liệu cần giữ.

## 11. Truy vết giá trị thực tế bằng SHOW, current_setting và pg_settings

Khi ứng dụng báo đang dùng một giá trị khác dự kiến, trước tiên cần quan sát **trong chính session của ứng dụng** hoặc trong một kết nối có cùng user, database và startup options.

### 11.1. SHOW và current_setting

~~~sql
SHOW work_mem;
SHOW statement_timeout;
SHOW search_path;

SELECT
    current_setting('work_mem') AS work_mem,
    current_setting('statement_timeout') AS statement_timeout;
~~~

`SHOW` và `current_setting` cho biết **giá trị đang có hiệu lực trong session**. Chúng không tự cho biết tham số được lấy từ server, database, role hay `SET`.

### 11.2. pg_settings cho biết nguồn và bối cảnh

~~~sql
SELECT
    name,
    setting,
    unit,
    source,
    context,
    sourcefile,
    sourceline,
    pending_restart
FROM pg_settings
WHERE name IN (
    'work_mem',
    'statement_timeout',
    'shared_buffers',
    'max_connections'
)
ORDER BY name;
~~~

Các cột đáng chú ý:

| Cột | Cách hiểu |
| --- | --- |
| `name` | Tên tham số |
| `setting` | Giá trị theo cách PostgreSQL biểu diễn trong view |
| `unit` | Đơn vị gắn với giá trị, nếu có |
| `source` | Nguồn mà giá trị hiện hành được chọn từ đó |
| `context` | Loại phạm vi/thẩm quyền cần thiết để thay đổi tham số |
| `sourcefile`, `sourceline` | File và dòng liên quan khi nguồn là file cấu hình và quyền xem cho phép |
| `pending_restart` | Cho biết cấu hình mới đang chờ restart để có hiệu lực hay không |

`pg_settings` phản ánh giá trị **trong phiên đang truy vấn**, không phải bảng tổng hợp duy nhất cho mọi user. Nếu đang kết nối dưới tài khoản quản trị trong database `postgres`, kết quả `work_mem` có thể khác hẳn phiên của `cfg_student` trong `cfg_demo`.

Một số nguồn có thể được hiển thị là cấu hình file, database, user/role, kết hợp database–user, client, hoặc thiết lập phiên. Cách biểu diễn cụ thể phụ thuộc phiên bản và nguồn được dùng. Không nên chỉ dựa vào một giá trị `source` mà bỏ qua `context`, trạng thái restart và kết nối thực sự.

**Quyền xem file:** `sourcefile` và `sourceline` có thể là `NULL` nếu không có nguồn file phù hợp hoặc tài khoản thiếu quyền xem thông tin cấu hình. Đừng suy ra “file không tồn tại” chỉ từ giá trị `NULL`.

### 11.3. Tham số setting có thể dùng đơn vị riêng

`SHOW work_mem` có thể hiển thị `'24MB'`, trong khi `pg_settings.setting` và `pg_settings.unit` có cách biểu diễn dữ liệu khác, chẳng hạn giá trị số tương ứng với đơn vị `kB`.

Nếu cần chuyển sang MB hoặc so sánh số liệu tự động, nên đọc **cả `setting` và `unit`**, không giả định mọi tham số cùng đơn vị hoặc đã quy về byte.

## 12. Xem những giá trị mặc định đang được gán cho role và database

Giá trị hiện hành trong một phiên không mô tả đầy đủ những cài đặt đang lưu cho **các role/database khác**. Đối với người quản trị, PostgreSQL lưu metadata tương ứng trong catalog `pg_db_role_setting`.

Ví dụ:

~~~sql
SELECT
    s.setdatabase,
    d.datname,
    s.setrole,
    r.rolname,
    s.setconfig
FROM pg_db_role_setting AS s
LEFT JOIN pg_database AS d
    ON d.oid = s.setdatabase
LEFT JOIN pg_roles AS r
    ON r.oid = s.setrole
ORDER BY d.datname NULLS FIRST, r.rolname NULLS FIRST;
~~~

Ý nghĩa thường gặp:

- `setdatabase = 0`: thiết lập không giới hạn ở một database cụ thể.
- `setrole = 0`: thiết lập không giới hạn ở một role cụ thể.
- Cả hai có giá trị OID cụ thể: cấu hình chuyên biệt cho **cặp role–database**.
- `setconfig` chứa danh sách tham số/giá trị đã được lưu cho phạm vi đó.

Tùy quyền truy cập metadata và phiên bản, tài khoản không phải quản trị viên có thể không xem được tất cả thông tin cần thiết. Hơn nữa, catalog này chứa **các override được lưu**, không phải giá trị cuối cùng của một kết nối đang mở sau `PGOPTIONS` hoặc `SET`.

Vì vậy, khi điều tra nên kết hợp:

1. `pg_db_role_setting` để xem thiết lập đã lưu của database/role.
2. `pg_settings` trong phiên cần kiểm tra để xem giá trị và nguồn thực tế.
3. Cấu hình server, log và startup options để xác định phần còn lại.

## 13. Không phải tham số nào cũng thay đổi được ở cùng một mức

Thứ tự ưu tiên chỉ có nghĩa khi tham số **được phép điều chỉnh ở nguồn đó**.

PostgreSQL phân biệt các `context` của GUC. Những nhóm thường gặp:

| `context` | Ý nghĩa thực tế |
| --- | --- |
| `internal` | PostgreSQL xác định nội bộ, người dùng không chỉnh tùy ý |
| `postmaster` | Cần đặt khi khởi động server; thay đổi thường yêu cầu restart |
| `sighup` | Có thể áp dụng sau khi server reload cấu hình |
| `backend` | Được xác định khi backend/session bắt đầu trong phạm vi cho phép |
| `superuser-backend` | Tương tự tham số backend, nhưng có giới hạn quyền cao hơn |
| `superuser` | Yêu cầu quyền nâng cao hoặc quyền `SET` riêng được cấp phù hợp, tùy phiên bản |
| `user` | Người dùng thông thường có thể điều chỉnh trong session hoặc nguồn được phép |

Chẳng hạn:

~~~sql
SELECT
    name,
    context,
    setting,
    source,
    pending_restart
FROM pg_settings
WHERE name IN (
    'work_mem',
    'statement_timeout',
    'shared_buffers',
    'max_connections',
    'log_min_duration_statement'
)
ORDER BY name;
~~~

Ví dụ:

- `work_mem` thường có `context = 'user'`: có thể đặt bằng `SET` nếu hợp lệ.
- `shared_buffers` thường có `context = 'postmaster'`: đổi giá trị yêu cầu restart PostgreSQL.
- `max_connections` cũng là tham số khởi động, không thể đổi cho một session bằng `SET`.
- Một số tham số phục vụ log hoặc bảo mật chỉ người có quyền cao mới được thay đổi.

Đừng suy diễn rằng “session có ưu tiên cao nhất, vì vậy `SET shared_buffers = ...` sẽ thắng cấu hình server”. PostgreSQL sẽ từ chối thao tác không hợp lệ.

### Reload và restart khác nhau

~~~text
Sửa tham số reload được
          |
          v
postgresql.conf / ALTER SYSTEM
          |
          v
pg_reload_conf() hoặc tín hiệu reload
          |
          v
Áp dụng tại thời điểm phù hợp

Sửa tham số postmaster
          |
          v
postgresql.conf / ALTER SYSTEM
          |
          v
Chưa có hiệu lực; pending_restart
          |
          v
Restart instance theo quy trình vận hành
~~~

Việc reload hoặc restart cần được làm có kiểm soát, đặc biệt trên server production. Một giá trị sai có thể khiến PostgreSQL không khởi động hoặc ảnh hưởng tải ứng dụng.

## 14. Một số tình huống xung đột thường gặp

### Tình huống A: “Đã sửa postgresql.conf nhưng SHOW vẫn là giá trị cũ”

Nguyên nhân có thể:

1. Chưa reload hoặc tham số yêu cầu restart.
2. `postgresql.auto.conf` hoặc tùy chọn dòng lệnh server ghi đè file.
3. Database, role hoặc cặp role–database có override.
4. Session đã chạy `SET` hoặc client gửi startup options.
5. Bạn đang kết nối tới **instance khác** hoặc một pooler đang tái sử dụng backend.

Cách chẩn đoán:

~~~sql
SHOW config_file;
SELECT name, setting, source, context, pending_restart
FROM pg_settings
WHERE name = 'work_mem';
~~~

Sau đó kiểm tra kết nối mới bằng đúng role/database và xem metadata cấp database/role.

### Tình huống B: “ALTER ROLE SET rồi mà ứng dụng không đổi”

`ALTER ROLE ... SET` thông thường chỉ được nạp khi **đăng nhập mới**. Ứng dụng đang dùng connection pool có thể tiếp tục tái sử dụng những kết nối vật lý được tạo từ trước.

Giải pháp không phải thay đổi `max_connections` hay khởi động lại cả server ngay lập tức. Trước tiên:

- Kiểm tra role đăng nhập thực tế (`session_user`).
- Mở một kết nối mới độc lập để xác nhận giá trị.
- Nếu ứng dụng dùng pool, lập kế hoạch làm mới kết nối an toàn theo khả năng của pool và SLA.
- Kiểm tra có `SET` hay startup options ghi đè trong ứng dụng không.

### Tình huống C: “Tài khoản thuộc role quản trị nhưng không nhận work_mem của role đó”

`ALTER ROLE role_x SET ...` không tự áp dụng nhờ membership role. Nó áp dụng khi phiên **đăng nhập bằng role_x** theo quy tắc PostgreSQL. `SET ROLE role_x` trong phiên đang có không tự chạy lại các thiết lập cấu hình đăng nhập của role đó.

Nếu muốn mặc định theo một nhóm tài khoản, có thể cần cấu hình trực tiếp cho từng login role hoặc thay đổi thiết kế quản trị, không giả định membership hoạt động như kế thừa mọi biến session.

### Tình huống D: “SET LOCAL xong nhưng truy vấn sau COMMIT không còn giá trị”

Đây là hành vi đúng: `SET LOCAL` tồn tại trong phạm vi transaction. Nếu cần cho toàn session, dùng `SET`; nếu cần cho mọi lần đăng nhập bằng role/database, dùng `ALTER ROLE` / `ALTER DATABASE`.

### Tình huống E: “RESET work_mem mà không về 4MB”

`RESET` trả giá trị mặc định có hiệu lực của session, có thể là `24MB` từ cặp role–database. Muốn loại giá trị ở tầng đó, quản trị viên phải `ALTER ROLE ... IN DATABASE ... RESET`, không chỉ `RESET` trong một kết nối.

### Tình huống F: “Áp dụng statement_timeout cho báo cáo mà lại ảnh hưởng ứng dụng khác”

Nếu đặt `statement_timeout` ở server, nhiều workload cùng chịu tác động trừ nơi được override. Nếu chỉ báo cáo cần timeout khác, đặt theo database/role hoặc transaction cụ thể; đồng thời bảo đảm ứng dụng không dùng chung role rộng và không để trạng thái session rò rỉ giữa các request trong pool.

## 15. Đưa vào ứng dụng: connection pool và quản lý session

Trong ứng dụng Java dùng JDBC/HikariCP, mỗi kết nối vật lý tới PostgreSQL có một **session** với trạng thái cấu hình riêng.

Ví dụ workflow:

~~~text
Ứng dụng mở connection từ pool
        |
        v
Connection đã đăng nhập vào PostgreSQL
        |
        +-- Mặc định server/database/role được nạp lúc tạo kết nối
        |
        +-- Request A: SET search_path = tenant_a
        |              SELECT ...
        |              Trả connection về pool
        |
        +-- Request B mượn lại cùng connection
                       Có thể nhận search_path còn từ A
                       nếu pool/ứng dụng không reset đúng
~~~

Đây là nguy cơ **rò rỉ trạng thái session** giữa các request, không phải rò rỉ dữ liệu do PostgreSQL bỏ qua quyền. Dẫu vậy, nó có thể dẫn tới truy vấn nhầm schema, timeout khác mong muốn hoặc hành vi nghiệp vụ sai.

### Lựa chọn phù hợp cho thay đổi ngắn hạn

Nếu chỉ một transaction cần cấu hình:

~~~sql
BEGIN;
SET LOCAL statement_timeout = '5s';

-- Câu SQL của nghiệp vụ.
SELECT 1;

COMMIT;
~~~

Vì `SET LOCAL` tự hết hiệu lực khi transaction kết thúc, nó thường dễ kiểm soát hơn `SET` kéo dài cả session. Tuy nhiên, ứng dụng vẫn phải **commit hoặc rollback** đúng cách, và pool phải bảo đảm connection không bị trả lại khi transaction chưa kết thúc.

### Chú ý PgBouncer transaction pooling

Với PgBouncer ở chế độ **transaction pooling**, một kết nối client không nhất thiết sử dụng cùng backend PostgreSQL qua nhiều transaction. Do đó:

- Không giả định `SET` cấp session trên một transaction sẽ tiếp tục có hiệu lực ở transaction sau.
- Các tham số chuyên biệt nên được lựa chọn từ thiết kế role/database khi kết nối backend được khởi tạo, hoặc sử dụng `SET LOCAL` trong transaction theo các điều kiện cụ thể.
- Phải hiểu cách pooler quản lý startup parameters, reset query và backend session trước khi dựa vào cấu hình cấp phiên.

Không nên so sánh kết quả `SHOW` qua pooler với một kết nối trực tiếp mà không xác nhận chế độ pooling và cùng role/database.

## 16. Quyền quản trị khi thay đổi cấu hình

Không phải tài khoản ứng dụng nào cũng có quyền sửa mọi mức:

| Thao tác | Quyền cần cân nhắc |
| --- | --- |
| `SET work_mem` | Có thể thực hiện với tham số cho phép người dùng chỉnh |
| `SET log_min_duration_statement` | Có thể đòi hỏi quyền cao hoặc quyền `SET` được cấp riêng phù hợp |
| `ALTER DATABASE ... SET` | Cần có quyền quản trị/ownership và quyền thay đổi tham số tương ứng |
| `ALTER ROLE ... SET` | Cần quyền quản trị role theo quy tắc PostgreSQL và quyền đối với tham số |
| `ALTER SYSTEM SET` | Hành động cấu hình toàn instance, yêu cầu quyền quản trị cao phù hợp |
| Chỉnh `postgresql.conf`, restart server | Cần quyền vận hành ở host/container/managed service |

Quyền cụ thể thay đổi theo phiên bản và tham số; ví dụ PostgreSQL hỗ trợ cơ chế cấp quyền `SET` trên một số parameter. **Không cấp superuser cho ứng dụng chỉ để thay `statement_timeout`**. Hãy dùng phạm vi cấu hình phù hợp hoặc nhờ quản trị viên thiết lập mặc định theo role/database.

### Cấu hình phục vụ bảo mật cũng cần kiểm soát

`search_path` ảnh hưởng cách PostgreSQL tìm đối tượng không được chỉ rõ schema, vì thế có thể tác động tới độ an toàn của các ứng dụng hoặc hàm `SECURITY DEFINER` nếu được thiết kế không cẩn thận. Với SQL có yêu cầu bảo mật cao, nên dùng tên schema rõ ràng hoặc cấu hình `search_path` an toàn theo thiết kế.

Tương tự, timeout quá rộng hoặc `work_mem` quá cao theo role có thể tạo rủi ro tài nguyên. Người dùng có quyền điều chỉnh tham số vẫn phải chịu quy trình kiểm soát cấu hình phù hợp.

## 17. Bài tập thực hành

Các bài tập giả định tham số `work_mem` được phép thay đổi ở mọi mức được nêu, các role/database đã tồn tại và không có startup options hay session override ngoài những điều kiện trong câu hỏi.

**Bài 1.** Server mặc định `work_mem = 4MB`. Database `shopdb` đặt `8MB`, role `app_user` đặt `16MB`. Khi `app_user` tạo kết nối mới tới `shopdb`, giá trị là bao nhiêu?

**Bài 2.** Giữ cấu hình của bài 1, bổ sung `ALTER ROLE app_user IN DATABASE shopdb SET work_mem='24MB'`. Trong kết nối mới bằng đúng role/database, giá trị nào thắng? Nếu `app_user` kết nối tới `otherdb` không có override riêng, giá trị dự kiến là gì?

**Bài 3.** Sau khi kết nối và nhận `24MB` từ cặp role–database, chạy `SET work_mem='32MB'` rồi `RESET work_mem`. Giá trị sau `RESET` sẽ là bao nhiêu? Vì sao không trở về `4MB`?

**Bài 4.** Trong một session đang có `work_mem = 24MB`, chạy:

~~~sql
BEGIN;
SET LOCAL work_mem = '48MB';
SHOW work_mem;
COMMIT;
SHOW work_mem;
~~~

Hai câu `SHOW` trả giá trị nào?

**Bài 5.** Trong session đang có `work_mem = 24MB`, chạy:

~~~sql
BEGIN;
SET work_mem = '32MB';
ROLLBACK;
SHOW work_mem;
~~~

Giá trị sau `ROLLBACK` là bao nhiêu?

**Bài 6.** Quản trị viên chạy `ALTER ROLE analyst SET statement_timeout='90s'` nhưng một connection mở từ hôm trước vẫn hiển thị `30s`. Hãy nêu hai điều cần kiểm tra trước khi kết luận lệnh `ALTER ROLE` thất bại.

**Bài 7.** Một user là thành viên của role `report_reader`. Quản trị viên đặt `ALTER ROLE report_reader SET work_mem='64MB'`. User đăng nhập bằng tài khoản riêng của mình có đương nhiên nhận `64MB` không?

**Bài 8.** Viết truy vấn lấy `name`, `setting`, `source`, `context` và `pending_restart` cho `shared_buffers` và `work_mem`. Trong hai tham số, tham số nào thông thường cần restart để đổi?

**Bài 9.** Một ứng dụng có connection pool và chạy `SET search_path = tenant_a` rồi trả connection về pool. Request khác nhận lại connection nhưng cần `tenant_b`. Vấn đề nào có thể xảy ra? Nên thiết kế thế nào?

**Bài 10.** Phân biệt ba thao tác:

~~~sql
RESET statement_timeout;

ALTER ROLE report_reader RESET statement_timeout;

ALTER ROLE report_reader
IN DATABASE reportdb
RESET statement_timeout;
~~~

Mỗi lệnh thay đổi phạm vi nào?

### Gợi ý đáp án

| Bài | Đáp án cốt lõi |
| --- | --- |
| 1 | `16MB`, vì thiết lập role có ưu tiên hơn database |
| 2 | `24MB` cho `app_user@shopdb`; `16MB` khi vào `otherdb` nếu không có override khác |
| 3 | `24MB`, vì `RESET` khôi phục mặc định session nhận từ cặp role–database |
| 4 | `48MB` trong transaction, `24MB` sau `COMMIT` |
| 5 | `24MB`, vì `SET` trong transaction bị rollback |
| 6 | Mở kết nối mới bằng đúng login role; kiểm tra `pg_settings.source`, các override cặp role–database, `PGOPTIONS` hoặc `SET` |
| 7 | Không; mặc định GUC từ `ALTER ROLE` không tự kế thừa chỉ vì membership hoặc `SET ROLE` |
| 8 | `shared_buffers` thường cần restart; `work_mem` có thể thay đổi trong session |
| 9 | Session có thể còn `search_path` từ request A; reset trạng thái khi trả pool, đặt giá trị đúng cho mỗi request hoặc dùng phạm vi transaction phù hợp |
| 10 | Lần lượt reset trong session hiện hành; xóa mặc định của role; xóa mặc định của cặp role–database |

Ví dụ lời giải **bài 8**:

~~~sql
SELECT
    name,
    setting,
    source,
    context,
    pending_restart
FROM pg_settings
WHERE name IN ('shared_buffers', 'work_mem')
ORDER BY name;
~~~

## 18. Bảng tra cứu nhanh

| Muốn cấu hình | Dùng cách nào? | Điều cần nhớ |
| --- | --- | --- |
| Mặc định toàn server | `postgresql.conf` hoặc `ALTER SYSTEM` | Có thể cần reload hoặc restart |
| Mặc định khi kết nối vào một DB | `ALTER DATABASE db SET param = value` | Áp dụng cho kết nối mới |
| Mặc định khi login bằng một role | `ALTER ROLE role SET param = value` | Ưu tiên hơn database riêng lẻ |
| Mặc định của một cặp role–DB | `ALTER ROLE role IN DATABASE db SET ...` | Chuyên biệt hơn role và database |
| Override khi mở kết nối | Tùy chọn startup/client, ví dụ `PGOPTIONS` | Chỉ với tham số được phép |
| Đổi trong phiên đang chạy | `SET param = value` | Có thể kéo dài tới khi reset/kết thúc session, chịu quy tắc transaction |
| Chỉ đổi trong transaction | `SET LOCAL param = value` | Tự hết hiệu lực sau transaction |
| Xem giá trị hiệu lực | `SHOW param` hoặc `current_setting()` | Đọc trong đúng session |
| Xem nguồn và context | `pg_settings` | Xem `source`, `context`, `pending_restart` |
| Xem override đã lưu theo role/DB | `pg_db_role_setting` | Không thay thế trạng thái thực tế của session |

**Ghi nhớ:** với những tham số cho phép cấu hình ở các mức tương ứng, **server → database → role → cặp role–database → tùy chọn kết nối → session → transaction-local** là thứ tự ưu tiên thực dụng. Nhưng “ưu tiên cao hơn” không vượt qua **quyền thay đổi tham số**, **context yêu cầu reload/restart** hoặc **vòng đời của phiên**. Khi một giá trị có vẻ không đúng, hãy kiểm tra bằng `SHOW` và `pg_settings` trong chính kết nối cần điều tra, rồi lần theo nguồn cấu hình từ cụ thể nhất về mặc định chung.
