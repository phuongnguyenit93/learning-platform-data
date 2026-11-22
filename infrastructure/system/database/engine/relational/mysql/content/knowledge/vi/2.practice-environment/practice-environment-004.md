# File cấu hình, cổng, socket và thư mục dữ liệu

Trong module **DATABASE_MYSQL**, người học làm chủ MySQL từ thiết kế bảng, kiểu dữ liệu, khóa và truy vấn SQL đến index, transaction, kiểm soát đồng thời, đọc kế hoạch thực thi, tối ưu truy vấn, phân quyền, sao lưu và vận hành. Trước khi thực hành các nội dung đó, cần hiểu MySQL Server lấy cấu hình ở đâu, nhận kết nối qua cổng hoặc socket nào và lưu dữ liệu tại thư mục nào. Đây là những thông tin quyết định ứng dụng có kết nối đúng máy chủ hay không, máy chủ có khởi động được không và dữ liệu có được bảo vệ khi vận hành hay không.

## 1. Bức tranh tổng thể

MySQL thường có một tiến trình máy chủ là `mysqld` và một hoặc nhiều chương trình khách như `mysql`. Máy chủ đọc cấu hình khi khởi động, mở các điểm nhận kết nối và truy cập thư mục dữ liệu. Chương trình khách cũng có thể đọc file cấu hình riêng để biết cách kết nối.

| Thành phần | Vai trò | Ví dụ |
|---|---|---|
| File cấu hình máy chủ | Thiết lập cách `mysqld` hoạt động | `port`, `bind-address`, `socket`, `datadir` |
| Cổng TCP | Nhận kết nối qua mạng IP | `3306` |
| Socket cục bộ | Nhận kết nối giữa các tiến trình trên cùng máy Unix/Linux | `/run/mysqld/mysqld.sock` |
| Thư mục dữ liệu | Lưu các file dữ liệu và metadata của instance | `/var/lib/mysql` |
| File cấu hình client | Thiết lập mặc định cho chương trình khách | `[client]`, `[mysql]` |

Cổng TCP, socket và thư mục dữ liệu là ba cấu hình khác nhau. Đổi cổng không tự đổi socket; đổi socket không chuyển dữ liệu; đổi `datadir` cũng không làm ứng dụng tự biết địa chỉ kết nối mới. Khi vận hành nhiều instance MySQL trên cùng máy, mỗi instance phải có cấu hình riêng và các tài nguyên như cổng, socket, PID file và thư mục dữ liệu không được xung đột.

## 2. File cấu hình MySQL

### 2.1. Những vị trí thường gặp

Tên và vị trí file cấu hình phụ thuộc hệ điều hành, cách cài đặt và cách đóng gói MySQL. Một số vị trí phổ biến:

| Môi trường | Vị trí thường gặp |
|---|---|
| Debian/Ubuntu | `/etc/mysql/my.cnf`; file cấu hình máy chủ thường nằm trong `/etc/mysql/mysql.conf.d/` |
| RHEL/Oracle Linux và một số bản phân phối tương tự | `/etc/my.cnf`; file bổ sung có thể nằm trong `/etc/my.cnf.d/` |
| Windows cài bằng MySQL Installer | Thường là `C:\ProgramData\MySQL\MySQL Server 8.0\my.ini`; phiên bản và đường dẫn cài đặt có thể khác |
| macOS hoặc bản cài thủ công | Phụ thuộc gói cài đặt và cách biên dịch MySQL |

Không nên đoán file cấu hình chỉ từ hệ điều hành. Hãy hỏi chính chương trình MySQL về danh sách file và nhóm tùy chọn mà nó đọc:

```bash
mysqld --verbose --help
mysql --verbose --help
```

Ở phần đầu kết quả, tìm dòng cho biết các file tùy chọn được đọc theo thứ tự. Lệnh thứ nhất kiểm tra cách máy chủ tìm cấu hình; lệnh thứ hai kiểm tra cách client tìm cấu hình. Trên Windows, chạy các lệnh từ thư mục chứa chương trình hoặc dùng tên file thực thi tương ứng, chẳng hạn `mysqld.exe`.

Để xem các tùy chọn được đọc từ option files:

```bash
mysqld --print-defaults
my_print_defaults mysqld
mysql --print-defaults
```

Kết quả có thể chứa thông tin nhạy cảm nếu ai đó đã ghi bí mật vào file cấu hình; không đăng nguyên kết quả lên nơi công khai. Các lệnh này giúp kiểm tra option files, nhưng không thay thế việc xác minh giá trị máy chủ đang chạy.

### 2.2. Nhóm tùy chọn và cú pháp

File cấu hình MySQL dùng các nhóm đặt trong dấu ngoặc vuông. Máy chủ đọc nhóm dành cho máy chủ, còn chương trình khách đọc nhóm dành cho client:

- `[mysqld]`: tùy chọn áp dụng cho MySQL Server.
- `[client]`: tùy chọn chung cho các chương trình khách MySQL.
- `[mysql]`: tùy chọn riêng cho chương trình dòng lệnh `mysql`.

Ví dụ cấu hình tối giản trên Linux:

```ini
[mysqld]
port=3306
bind-address=127.0.0.1
socket=/run/mysqld/mysqld.sock
datadir=/var/lib/mysql

[client]
port=3306
socket=/run/mysqld/mysqld.sock
```

Trong ví dụ này, máy chủ nhận TCP trên cổng 3306 và địa chỉ loopback, đồng thời tạo socket tại đường dẫn chỉ định. Client có thể dùng cùng cổng và socket làm mặc định. Các đường dẫn chỉ là ví dụ: phải dùng đường dẫn thực tế của máy đang cấu hình, bảo đảm thư mục cha tồn tại và tài khoản chạy MySQL có quyền phù hợp.

Tên tùy chọn thường có thể viết bằng dấu gạch ngang hoặc dấu gạch dưới, ví dụ `bind-address` và `bind_address`. Dòng bắt đầu bằng `#` hoặc `;` có thể dùng làm chú thích. Tùy chọn phải nằm trong đúng nhóm; đặt `datadir` trong `[client]` không cấu hình được thư mục dữ liệu của máy chủ.

Một file cấu hình có thể nạp file khác bằng `!include` hoặc nạp một thư mục bằng `!includedir`. Vì vậy, thay đổi ở file chính có thể bị một file được đọc sau ghi đè. Hãy kiểm tra thứ tự đọc thực tế và các file được include trước khi kết luận giá trị nào có hiệu lực.

Các tùy chọn truyền trực tiếp trên dòng lệnh có thể ghi đè giá trị trong file cấu hình. MySQL 8.0 còn hỗ trợ các biến được lưu bằng `SET PERSIST`; giá trị này được lưu trong `mysqld-auto.cnf` tại thư mục dữ liệu và được nạp khi khởi động. Khi giá trị thực tế khác file vừa sửa, hãy kiểm tra cả tham số khởi chạy và các biến đã persist. Có thể xem các biến persist bằng:

```sql
SELECT VARIABLE_NAME, VARIABLE_VALUE
FROM performance_schema.persisted_variables;
```

Nếu cần buộc một chương trình đọc một file cụ thể, có thể dùng `--defaults-file`; tùy chọn này phải đứng ngay sau tên chương trình, trước các tùy chọn khác:

```bash
mysql --defaults-file=/path/to/client.cnf --protocol=TCP
```

## 3. Cổng TCP và địa chỉ bind

### 3.1. Cổng dùng để làm gì?

MySQL Server thường dùng TCP port **3306** cho kết nối SQL thông thường. Đây là giá trị mặc định phổ biến, không phải cam kết rằng mọi instance đều dùng cổng này. MySQL X Protocol thường dùng cổng **33060** khi plugin X Protocol được bật; cổng này phục vụ giao thức riêng và không thay thế cổng SQL cổ điển 3306.

Client phải kết nối đúng địa chỉ IP hoặc tên máy, đúng cổng và đúng giao thức. Ví dụ kết nối qua TCP đến máy chủ trên cùng máy:

```bash
mysql --protocol=TCP --host=127.0.0.1 --port=3306 --user=app_user --password
```

Tùy chọn `--password` ở dạng này yêu cầu client hỏi mật khẩu tương tác; không đặt mật khẩu trực tiếp trong câu lệnh vì lịch sử shell và danh sách tiến trình có thể làm lộ bí mật. Khi kết nối máy chủ từ xa, thay `127.0.0.1` bằng địa chỉ hoặc tên DNS của máy chủ.

### 3.2. Địa chỉ bind quyết định máy nào được nhận kết nối

Tùy chọn `bind-address` xác định địa chỉ mạng mà máy chủ lắng nghe:

- `127.0.0.1`: chỉ nhận kết nối IPv4 từ chính máy đó.
- Một địa chỉ IP riêng cụ thể: chỉ lắng nghe trên giao diện mạng tương ứng.
- `0.0.0.0`: lắng nghe trên mọi giao diện IPv4; cần kiểm soát bằng firewall và chính sách mạng.

Nếu máy chủ chỉ phục vụ ứng dụng chạy cùng máy, bind vào loopback thường là lựa chọn giới hạn phạm vi tốt. Nếu cần kết nối từ máy khác, phải chọn giao diện phù hợp, mở firewall đúng nguồn và cổng, đồng thời cấu hình tài khoản MySQL với quyền tối thiểu. Không nên công khai cổng MySQL ra Internet chỉ để tiện kết nối.

Nếu tùy chọn `skip-networking` được bật, máy chủ không nhận kết nối TCP; khi đó client TCP sẽ không kết nối được dù socket cục bộ vẫn có thể hoạt động. Cũng cần phân biệt firewall chặn kết nối với máy chủ không lắng nghe: hai nguyên nhân này có cách xử lý khác nhau.

## 4. Socket cục bộ

Trên Linux và Unix, Unix domain socket cho phép các tiến trình trên cùng máy giao tiếp qua một file socket. Kết nối này không đi qua TCP/IP và không cần mở cổng mạng. Đường dẫn socket thường được cấu hình bằng biến `socket` trong nhóm `[mysqld]`.

Client cũng cần biết đường dẫn socket tương ứng. Ví dụ:

```ini
[mysqld]
socket=/run/mysqld/mysqld.sock

[client]
socket=/run/mysqld/mysqld.sock
```

Nếu máy chủ tạo socket ở một đường dẫn nhưng client tìm ở đường dẫn khác, client có thể báo không kết nối được dù dịch vụ đang chạy. Kiểm tra giá trị phía máy chủ:

```sql
SHOW GLOBAL VARIABLES LIKE 'socket';
```

Và thử kết nối bằng đường dẫn tường minh:

```bash
mysql --protocol=SOCKET --socket=/run/mysqld/mysqld.sock --user=app_user --password
```

Trên Unix, kết nối đến `localhost` thường chọn Unix socket, trong khi `127.0.0.1` chọn TCP. Khi cần chẩn đoán chính xác, hãy chỉ định `--protocol=SOCKET` hoặc `--protocol=TCP` thay vì dựa vào giá trị mặc định. Trên Windows, cơ chế cục bộ có thể là named pipe hoặc shared memory nếu được bật; Unix domain socket và đường dẫn kiểu Linux không áp dụng trực tiếp.

Quyền truy cập socket phụ thuộc quyền trên file socket và thư mục cha. Nếu client không có quyền truy cập, cần kiểm tra user/group và cấu hình dịch vụ. Không xóa file socket tùy tiện khi chưa xác nhận trạng thái tiến trình máy chủ; file có thể đang được sử dụng hoặc được dịch vụ quản lý.

## 5. Thư mục dữ liệu (datadir)

Biến `datadir` chỉ thư mục gốc mà một instance MySQL dùng để lưu dữ liệu. Thư mục này có thể chứa thư mục của các database, metadata hệ thống, file tablespace, redo log, undo log và những file khác tùy phiên bản cùng cấu hình storage engine. Binary log và một số loại log có thể được đặt ở đường dẫn riêng, vì vậy không nên mặc định mọi log đều nằm trong `datadir`.

Xem đường dẫn đang được máy chủ sử dụng:

```sql
SHOW GLOBAL VARIABLES LIKE 'datadir';
-- Hoặc truy vấn cùng các cấu hình môi trường khác:
SELECT @@global.port,
       @@global.bind_address,
       @@global.socket,
       @@global.datadir;
```

Thư mục dữ liệu thuộc về tiến trình máy chủ. Tài khoản hệ điều hành chạy `mysqld` cần quyền đọc, ghi và đi qua các thư mục cha cần thiết. Trên Linux có thể còn phải điều chỉnh chính sách SELinux hoặc AppArmor khi chuyển dữ liệu sang vị trí mới. Không giải quyết lỗi quyền bằng cách cấp quyền ghi rộng cho tất cả người dùng.

### 5.1. Thay đổi datadir an toàn

Đổi `datadir` là thao tác ảnh hưởng trực tiếp đến dữ liệu và quá trình khởi động. Quy trình tổng quát:

1. Xác định chính xác instance, phiên bản MySQL, đường dẫn dữ liệu hiện tại và tài khoản hệ điều hành chạy dịch vụ.
2. Tạo bản sao lưu có thể khôi phục; kiểm tra bản sao lưu trước khi chuyển đổi.
3. Dừng MySQL một cách sạch sẽ và xác nhận tiến trình đã dừng hoàn toàn.
4. Chuẩn bị thư mục đích, sao chép hoặc khôi phục dữ liệu bằng phương pháp phù hợp, giữ đúng chủ sở hữu, quyền truy cập và metadata cần thiết.
5. Cập nhật `datadir` trong cấu hình đúng của instance; kiểm tra thêm các đường dẫn liên quan như log, socket và PID file nếu chúng phụ thuộc vị trí cũ.
6. Khởi động dịch vụ, đọc error log và xác minh các biến hệ thống cùng dữ liệu ứng dụng.
7. Chỉ xóa dữ liệu cũ sau khi đã xác nhận bản mới hoạt động và bản sao lưu vẫn có thể khôi phục.

Không sao chép file dữ liệu đang được `mysqld` sử dụng bằng thao tác copy thông thường. Không chạy bước khởi tạo trên một thư mục đã chứa dữ liệu cần giữ. Với khác biệt phiên bản hoặc định dạng lưu trữ, backup/restore bằng công cụ MySQL thường an toàn và dễ kiểm soát hơn việc di chuyển file thô.

Khi tạo một instance hoàn toàn mới, thư mục dữ liệu phải được khởi tạo theo hướng dẫn của phiên bản và gói cài đặt đang dùng. `mysqld --initialize` tạo dữ liệu hệ thống ban đầu và sinh mật khẩu tạm cho tài khoản root; mật khẩu này được ghi vào error log. `--initialize-insecure` tạo tài khoản root không có mật khẩu ban đầu và chỉ phù hợp với môi trường lab cô lập cần được bảo vệ ngay sau đó. Không dùng các lệnh khởi tạo trên thư mục dữ liệu hiện có.

## 6. Áp dụng và xác minh cấu hình

Một thay đổi cấu hình chỉ được xem là hoàn tất sau khi xác nhận máy chủ khởi động với giá trị mong muốn và client kết nối theo đúng đường dẫn.

1. **Nhận diện đúng instance.** Xác định binary, file cấu hình, service name và thư mục dữ liệu. Nếu có nhiều instance, không dựa vào tên dịch vụ mặc định.
2. **Sao lưu file cấu hình.** Lưu bản gốc trước khi sửa để có thể khôi phục khi cấu hình mới khiến dịch vụ không khởi động.
3. **Sửa đúng nhóm.** Đặt tùy chọn máy chủ trong `[mysqld]`, tùy chọn chung client trong `[client]`. Kiểm tra file include và các tùy chọn dòng lệnh của service.
4. **Kiểm tra trước khi áp dụng.** Dùng `mysqld --print-defaults` hoặc `my_print_defaults mysqld` để rà soát option files; dùng cú pháp kiểm tra cấu hình được hỗ trợ bởi phiên bản đang cài nếu có.
5. **Khởi động lại đúng dịch vụ khi cần.** Trên Linux, tên dịch vụ thường là `mysql` hoặc `mysqld`; xác định tên thực tế trước khi restart. Ví dụ khi dịch vụ tên `mysql`:

   ```bash
   sudo systemctl restart mysql
   sudo systemctl status mysql
   sudo journalctl -u mysql -n 100 --no-pager
   ```

   Trên Windows, có thể tìm dịch vụ bằng `Get-Service *mysql*`, sau đó kiểm tra đúng tên dịch vụ trước khi khởi động lại.

6. **Xác minh từ bên trong MySQL.** Sau khi kết nối được, chạy:

   ```sql
   SELECT @@global.port AS tcp_port,
          @@global.bind_address AS bind_address,
          @@global.socket AS socket_path,
          @@global.datadir AS data_directory,
          @@global.skip_networking AS skip_networking;
   ```

7. **Xác minh ở hệ điều hành.** Trên Linux, dùng `ss -ltnp` để xem cổng TCP đang lắng nghe và `ss -lxnp` để xem Unix socket. Trên Windows, dùng `Get-NetTCPConnection -LocalPort 3306 -State Listen` với đúng cổng đang cấu hình. Kết quả hệ điều hành giúp phân biệt máy chủ chưa lắng nghe với lỗi từ client hoặc firewall.

Đường dẫn error log có thể lấy bằng `SHOW GLOBAL VARIABLES LIKE 'log_error';`. Nếu dịch vụ không khởi động, đọc log này hoặc log của service trước khi sửa tiếp; thông báo thường chỉ ra option không hợp lệ, file cấu hình sai cú pháp, cổng bị chiếm hoặc thư mục dữ liệu không truy cập được.

## 7. Bài thực hành: xác định đường kết nối và vị trí dữ liệu

Thực hiện trên instance phát triển hoặc môi trường lab mà bạn được phép truy cập.

**Bước 1 — Tìm cấu hình.** Chạy `mysqld --verbose --help` và ghi lại danh sách file máy chủ đọc. Mở file phù hợp, xác định nhóm `[mysqld]`, các file include và các giá trị liên quan đến `port`, `bind-address`, `socket`, `datadir`.

**Bước 2 — Đọc cấu hình hiệu lực.** Chạy `my_print_defaults mysqld` và so sánh với file bạn vừa đọc. Nếu có khác biệt, kiểm tra thứ tự file, file include và tham số khởi chạy.

**Bước 3 — Đọc giá trị runtime.** Kết nối bằng tài khoản được cấp và chạy:

```sql
SELECT @@hostname AS server_name,
       @@port AS tcp_port,
       @@bind_address AS bind_address,
       @@socket AS socket_path,
       @@datadir AS data_directory;
```

Ghi lại kết quả. Đây là giá trị máy chủ đang sử dụng, hữu ích hơn việc chỉ nhìn một file cấu hình chưa chắc đã được nạp.

**Bước 4 — Thử kết nối TCP.** Dùng địa chỉ loopback và cổng vừa xác định:

```bash
mysql --protocol=TCP --host=127.0.0.1 --port=3306 --user=app_user --password
```

Thay cổng bằng giá trị thực tế nếu instance không dùng 3306. Nếu cần thử socket trên Linux, dùng:

```bash
mysql --protocol=SOCKET --socket=/run/mysqld/mysqld.sock --user=app_user --password
```

Thay đường dẫn bằng giá trị `@@socket` đã đọc. So sánh hai lần kết nối và xác định lần nào dùng TCP, lần nào dùng socket.

**Bước 5 — Đối chiếu hệ điều hành.** Kiểm tra cổng và socket bằng công cụ phù hợp với hệ điều hành. Xác nhận đường dẫn `datadir` tồn tại và tài khoản dịch vụ có quyền truy cập. Không di chuyển hoặc chỉnh sửa file dữ liệu trong bài thực hành này.

**Kết quả cần đạt:** bạn giải thích được client đang kết nối qua TCP hay socket, máy chủ lắng nghe trên địa chỉ/cổng nào, file cấu hình nào cung cấp các tùy chọn và dữ liệu của instance nằm ở đâu.

## 8. Lỗi thường gặp và cách khoanh vùng

| Triệu chứng | Nguyên nhân có thể | Hướng kiểm tra |
|---|---|---|
| Client báo không kết nối được tới `127.0.0.1:3306` | Dịch vụ dừng, cổng khác, bind sai địa chỉ, `skip-networking` hoặc firewall | Kiểm tra service, `@@port`, `@@bind_address`, `@@skip_networking` và trạng thái lắng nghe TCP |
| Client báo không tìm thấy hoặc không kết nối được socket | Client dùng sai đường dẫn, socket chưa được tạo, quyền thư mục/file không phù hợp | Đọc `@@socket`, kiểm tra `ss -lxnp`, quyền truy cập và error log |
| Báo `Address already in use` khi khởi động | Một tiến trình khác đã chiếm cổng hoặc socket | Xác định tiến trình đang lắng nghe; chọn tài nguyên riêng cho instance hoặc dừng dịch vụ xung đột đúng cách |
| Báo `Access denied` | Kết nối đã tới MySQL nhưng xác thực hoặc quyền tài khoản không phù hợp | Kiểm tra user, host được phép, phương thức xác thực và grants; không đổi cổng để xử lý lỗi quyền |
| MySQL không khởi động sau khi sửa file | Sai tên tùy chọn, đặt nhầm nhóm, đường dẫn không tồn tại, quyền truy cập sai hoặc cấu hình xung đột | Đọc error log, kiểm tra file được nạp và khôi phục bản cấu hình trước nếu cần |
| MySQL không đọc được dữ liệu ở datadir mới | Sai chủ sở hữu/quyền, chính sách bảo mật hệ điều hành hoặc dữ liệu chưa được chuyển đúng | Kiểm tra tài khoản dịch vụ, quyền thư mục, SELinux/AppArmor và quy trình backup/restore |

Hãy phân loại lỗi theo tầng: lỗi định tuyến hoặc firewall xảy ra trước khi tới máy chủ; lỗi cổng/socket là vấn đề đường kết nối; `Access denied` là vấn đề xác thực hoặc quyền sau khi kết nối đã tới MySQL; lỗi datadir thường thể hiện ở lúc khởi động hoặc khi truy cập file dữ liệu.

## 9. Nguyên tắc vận hành an toàn

- Giới hạn `bind-address` vào giao diện cần thiết; chỉ mở firewall cho nguồn tin cậy và cổng thực sự sử dụng.
- Dùng tài khoản MySQL riêng cho ứng dụng với quyền tối thiểu; không dùng tài khoản quản trị để kết nối thường ngày.
- Không ghi mật khẩu rõ trong file cấu hình hoặc dòng lệnh. Bảo vệ file cấu hình và bản sao lưu vì chúng có thể chứa thông tin nhạy cảm.
- Bảo đảm chỉ tài khoản dịch vụ MySQL và quản trị viên được phép truy cập thư mục dữ liệu.
- Với nhiều instance, cấp riêng `datadir`, cổng TCP, socket và PID file cho từng instance.
- Trước khi thay đổi đường dẫn dữ liệu hoặc cấu hình kết nối của ứng dụng, lập kế hoạch khôi phục và kiểm tra lại kết nối từ ứng dụng sau khi áp dụng.

Nắm được file cấu hình, cổng, socket và `datadir` giúp bạn xác định chính xác MySQL instance đang chạy ở đâu, ứng dụng đang đi vào bằng đường nào và dữ liệu được lưu ở vị trí nào. Đây là nền tảng để thực hành truy vấn, index, transaction, phân quyền, sao lưu và xử lý sự cố trên một môi trường MySQL có thể kiểm soát.
