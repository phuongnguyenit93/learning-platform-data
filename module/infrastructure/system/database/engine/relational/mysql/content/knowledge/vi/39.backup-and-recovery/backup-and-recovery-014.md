# Sao lưu cấu hình, tài khoản, chứng thư và khóa mã hóa

## Mục tiêu

Một bản sao lưu MySQL chỉ có thể phục hồi đầy đủ khi bạn giữ được cả dữ liệu lẫn những thành phần cần để máy chủ khởi động, xác thực người dùng, thiết lập kết nối bảo mật và giải mã dữ liệu. Tệp cấu hình, định nghĩa tài khoản, chứng thư TLS và khóa mã hóa thường nằm ngoài luồng sao lưu bảng dữ liệu; nếu bỏ sót chúng, quá trình khôi phục có thể dừng ngay cả khi các tệp dữ liệu vẫn còn nguyên.

Bài học này thuộc module **DATABASE_MYSQL**, bao quát thiết kế bảng, kiểu dữ liệu, khóa, SQL, index, transaction, kiểm soát đồng thời, tối ưu truy vấn và vận hành cơ sở dữ liệu quan hệ. Trong phạm vi sao lưu và phục hồi, nội dung tập trung vào việc nhận diện, bảo vệ, lập phiên bản và khôi phục các thành phần cấu hình và bảo mật đi kèm MySQL.

Sau bài học, bạn có thể:

- Lập danh mục các tệp cấu hình, thiết lập runtime và thành phần mở rộng cần lưu giữ.
- Xuất và phục hồi định nghĩa account, quyền, role và cấu hình role mặc định.
- Sao lưu chứng thư, chuỗi CA, khóa riêng và thông tin xác thực TLS một cách an toàn.
- Xác định keyring hoặc dịch vụ KMS/HSM đang bảo vệ dữ liệu được mã hóa và xây dựng quy trình phục hồi tương ứng.
- Thực hiện kiểm tra phục hồi để xác nhận máy chủ khởi động, ứng dụng đăng nhập và dữ liệu mã hóa có thể đọc được.

## 1. Nhìn bản sao lưu như một tập hợp thành phần

Dữ liệu trong schema chỉ là một phần của trạng thái hệ thống. Một bản phục hồi có thể cần những nhóm thông tin sau:

| Nhóm | Ví dụ thành phần | Mục đích khi phục hồi |
|---|---|---|
| Cấu hình máy chủ | `my.cnf`, `my.ini`, thư mục include, tham số khởi động, cấu hình service | Khởi động MySQL với đúng đường dẫn, cổng, chế độ và hành vi mong muốn |
| Thiết lập lưu bền | `mysqld-auto.cnf` do `SET PERSIST` quản lý | Khôi phục các biến hệ thống đã được lưu bền qua lần khởi động |
| Tài khoản và quyền | Account `user`/`host`, plugin xác thực, role, grants, default role | Cho phép DBA, ứng dụng và công cụ vận hành đăng nhập đúng quyền |
| Chứng thư và TLS | Chứng thư máy chủ, khóa riêng, CA, chứng thư client, CRL nếu sử dụng | Thiết lập kết nối mã hóa và xác thực chứng thư |
| Khóa mã hóa | Dữ liệu keyring, cấu hình component/plugin, định danh và quyền truy cập KMS/HSM | Mở tablespace, redo log hoặc dữ liệu được mã hóa |
| Thông tin vận hành | Phiên bản MySQL, plugin/component, đường dẫn, chủ sở hữu file, ACL, sơ đồ triển khai | Tái tạo môi trường tương thích và đúng quyền truy cập |

Hãy xác định rõ phạm vi mỗi bộ sao lưu. Bản dump dữ liệu không mặc nhiên chứa cấu hình hệ điều hành, khóa riêng, keyring hoặc thông tin truy cập KMS. Ngược lại, bản sao thư mục cấu hình cũng không thay thế bản sao lưu dữ liệu và log cần cho mục tiêu phục hồi.

## 2. Lập danh mục cấu hình MySQL

MySQL có thể đọc cấu hình từ nhiều option file, thư mục được include, tham số dòng lệnh và cấu hình của dịch vụ khởi động. Vị trí cụ thể tùy hệ điều hành, gói cài đặt và cách triển khai. Vì vậy, đừng chỉ sao chép một tệp `my.cnf` hoặc `my.ini` mà chưa xác nhận máy chủ thực sự đọc những nguồn nào.

Trước khi sao lưu, ghi nhận phiên bản và các biến quan trọng:

```sql
SELECT VERSION() AS mysql_version;

SHOW GLOBAL VARIABLES
WHERE Variable_name IN (
  'basedir', 'datadir', 'port', 'socket', 'pid_file',
  'log_error', 'log_bin', 'relay_log', 'server_id',
  'lower_case_table_names', 'character_set_server',
  'collation_server', 'sql_mode', 'time_zone',
  'tls_version', 'ssl_ca', 'ssl_cert', 'ssl_key'
);

SHOW PLUGINS;

-- MySQL 8.0: inspect registered components when this table is available
SELECT component_urn FROM mysql.component;
```

Các biến trên là ví dụ để bắt đầu kiểm kê; hãy bổ sung biến liên quan đến replication, binary log, InnoDB, mã hóa, audit, xác thực và plugin đang dùng. `SHOW PLUGINS` liệt kê plugin; component cần được kiểm kê riêng theo phiên bản, chẳng hạn qua `mysql.component` trên MySQL 8.0. Giá trị của biến có thể nhạy cảm hoặc tiết lộ cấu trúc nội bộ, vì vậy cần giới hạn quyền truy cập bản xuất.

Ở phía máy chủ, xác định:

- Tất cả option file và thư mục được include, kể cả file được quản lý bởi công cụ cấu hình.
- Các tham số dòng lệnh và cấu hình của systemd, Windows Service, container hoặc hệ thống điều phối.
- Tài khoản hệ điều hành chạy `mysqld`, quyền đọc/ghi thư mục dữ liệu, log, chứng thư và keyring.
- Cấu hình plugin/component, thư viện đi kèm và các biến môi trường cần để khởi động.
- Những thay đổi runtime được lưu bền bằng `SET PERSIST`.

Tiện ích `my_print_defaults` có thể giúp xem các tùy chọn lấy từ option file, còn `mysqld --verbose --help` có thể cung cấp thông tin về tùy chọn và nguồn mặc định tùy phiên bản. Kết quả của các lệnh này có thể chứa mật khẩu hoặc thông tin nhạy cảm; chỉ lưu trong vùng hạn chế truy cập và không dán nguyên văn vào ticket hay log công khai.

### Lưu ý về `mysqld-auto.cnf`

Khi dùng `SET PERSIST`, MySQL ghi giá trị biến hệ thống vào tệp `mysqld-auto.cnf` trong thư mục dữ liệu. Tệp này tham gia vào cấu hình khi máy chủ khởi động. Hãy đưa nó vào danh mục bảo vệ và lưu lại cùng mốc thời gian của bản sao lưu dữ liệu tương ứng.

Không sửa trực tiếp `mysqld-auto.cnf` khi máy chủ đang quản lý nó. Dùng `SET PERSIST`, `SET PERSIST_ONLY` hoặc `RESET PERSIST` theo nhu cầu và phiên bản MySQL. Khi phục hồi sang môi trường khác, rà soát từng giá trị trước khi áp dụng vì đường dẫn, thiết bị, cổng và giới hạn tài nguyên có thể khác.

## 3. Sao lưu tài khoản, role và quyền

Trong MySQL, account được nhận diện theo cặp tên người dùng và host, ví dụ `'orders_app'@'10.20.30.15'`. Bản ghi tài khoản có thể bao gồm plugin xác thực, trạng thái khóa, chính sách mật khẩu, yêu cầu TLS, giới hạn tài nguyên và các thuộc tính khác. Quyền có thể được cấp trực tiếp hoặc thông qua role; role còn có thể được cấu hình làm role mặc định khi đăng nhập.

Đối với từng account và role cần giữ lại, xuất định nghĩa và grants bằng các lệnh quản trị:

```sql
SHOW CREATE USER 'orders_app'@'10.20.30.15';
SHOW GRANTS FOR 'orders_app'@'10.20.30.15';

SHOW CREATE USER 'orders_report'@'10.20.30.25';
SHOW GRANTS FOR 'orders_report'@'10.20.30.25';
```

`SHOW CREATE USER` cung cấp câu lệnh tái tạo account và các thuộc tính xác thực mà người thực hiện có quyền xem. `SHOW GRANTS` thể hiện quyền trực tiếp và các role đã được cấp. Thực hiện tương tự cho account quản trị, account dịch vụ, role và các account nội bộ do ứng dụng hoặc công cụ vận hành yêu cầu.

Với role, ghi lại cả quyền trong role, quan hệ role được cấp cho account và role mặc định. Ví dụ:

```sql
CREATE ROLE 'orders_readonly';
GRANT SELECT ON orders.* TO 'orders_readonly';
GRANT 'orders_readonly' TO 'analyst'@'10.20.30.25';
SET DEFAULT ROLE 'orders_readonly' TO 'analyst'@'10.20.30.25';
```

Trong quá trình xuất, hãy lưu lại các lệnh tạo role, cấp role và đặt role mặc định cùng với grants của chúng. Nếu một account nhận nhiều role hoặc role được lồng theo cấu hình, phải ghi nhận đầy đủ quan hệ đó để tránh phục hồi thiếu quyền.

Định nghĩa account và grants là dữ liệu nhạy cảm. Đầu ra `SHOW CREATE USER` có thể chứa thông tin xác thực dạng hash hoặc thuộc tính plugin; bảo vệ tệp xuất như một secret, mã hóa khi lưu và giới hạn người có thể đọc. Không gửi nội dung này vào Git công khai, email không bảo vệ hoặc log CI/CD.

### Chọn phương pháp xuất phù hợp

Có thể dùng tiện ích xuất account được hỗ trợ bởi đúng phiên bản MySQL hoặc xuất các câu lệnh `SHOW CREATE USER` và `SHOW GRANTS` theo danh mục account. Trước khi chọn công cụ, kiểm tra tài liệu phiên bản đang chạy và xác nhận công cụ có giữ được role, dynamic privilege, default role, thuộc tính xác thực và các yêu cầu TLS hay không.

Không sao chép thô các tệp hoặc bảng hệ thống quyền từ một data directory sang máy chủ có phiên bản khác. Cấu trúc dữ liệu từ điển và grant table thay đổi theo phiên bản; hãy dùng cơ chế quản trị và nâng cấp được MySQL hỗ trợ. Cũng không nên phục hồi một cách mù quáng các account đã nghỉ việc hoặc secret đã bị thu hồi.

## 4. Sao lưu chứng thư và cấu hình TLS

MySQL có thể dùng TLS để mã hóa kết nối client/server và, tùy cấu hình, xác thực chứng thư của client. Một bộ TLS thường gồm:

- Chứng thư máy chủ và khóa riêng tương ứng.
- Chứng thư CA hoặc chuỗi CA mà client dùng để xác minh máy chủ.
- Chứng thư client và khóa riêng nếu bật xác thực client certificate.
- CRL hoặc cấu hình kiểm tra thu hồi chứng thư nếu môi trường sử dụng.
- Thông tin đường dẫn, định dạng, mật khẩu bảo vệ khóa (nếu có), chủ sở hữu và quyền truy cập file.

Các biến như `ssl_ca`, `ssl_cert`, `ssl_key` và `tls_version` giúp xác định cấu hình đang hoạt động. Có thể kiểm tra bằng:

```sql
SHOW GLOBAL VARIABLES LIKE 'ssl_%';
SHOW GLOBAL VARIABLES LIKE 'tls_version';
```

Sao lưu chứng thư cùng chuỗi CA cần thiết và khóa riêng trong vùng lưu trữ được mã hóa, có kiểm soát truy cập chặt chẽ. Bản sao phải giữ được quyền file phù hợp với tài khoản hệ điều hành chạy MySQL. Một khóa riêng bị lộ có thể làm suy yếu khả năng xác thực của toàn bộ hệ thống, vì vậy không đặt khóa trong thư mục chia sẻ rộng hoặc kho mã nguồn.

Nếu có OpenSSL, có thể kiểm tra thông tin thời hạn và chủ thể của chứng thư:

```bash
openssl x509 -in server-cert.pem -noout -subject -issuer -dates
```

Lệnh trên chỉ đọc thông tin chứng thư công khai; không dùng lệnh hiển thị nội dung khóa riêng để kiểm tra. Ghi nhận ngày hết hạn và lập lịch gia hạn trước khi chứng thư hết hiệu lực. Khi thay chứng thư, kiểm tra SAN/hostname, chuỗi CA, phiên bản TLS mà client hỗ trợ và khả năng khởi động lại MySQL.

### Phục hồi TLS

Trước khi khởi động MySQL, đặt các file chứng thư và khóa vào đúng vị trí, khôi phục chủ sở hữu và quyền truy cập, rồi kiểm tra đường dẫn trong cấu hình. Sau khi máy chủ hoạt động, xác minh kết nối TLS từ một client thực tế và kiểm tra account có yêu cầu SSL/X509 theo thiết kế.

Không giả định rằng chứng thư cũ luôn còn hợp lệ sau khi phục hồi. Chứng thư có thể đã hết hạn, bị thu hồi hoặc không còn phù hợp với hostname mới. Nếu thay đổi tên máy chủ, địa chỉ hoặc CA, cần phát hành và phân phối chứng thư mới theo quy trình quản lý vòng đời.

## 5. Bảo vệ keyring và khóa mã hóa dữ liệu

Nếu MySQL dùng mã hóa tablespace, redo log, undo log hoặc binary log, máy chủ cần truy cập được khóa tương ứng. Trong nhiều cấu hình, MySQL sử dụng keyring component hoặc plugin để quản lý khóa; môi trường khác có thể tích hợp với KMS hoặc HSM bên ngoài.

Hãy kiểm kê ít nhất:

- Tên và phiên bản keyring component/plugin hoặc cơ chế KMS/HSM đang dùng.
- File cấu hình để nạp component/plugin và vị trí dữ liệu keyring.
- Quyền truy cập file, danh tính dịch vụ và các tham số cần để kết nối KMS/HSM.
- Key identifier, phiên bản khóa, chính sách truy cập và quy trình xoay vòng.
- Các tính năng mã hóa đang bật và những đối tượng phụ thuộc vào khóa.

Điểm quan trọng là **bản sao dữ liệu mã hóa và bản sao khóa phải thuộc cùng một kế hoạch phục hồi**. Nếu có tablespace được mã hóa mà keyring bị mất, MySQL có thể không giải mã được dữ liệu dù các file tablespace vẫn còn. Nếu dùng KMS/HSM, giữ lại thông tin định danh khóa và quyền truy cập cần thiết để máy chủ phục hồi có thể yêu cầu giải mã.

Không tự ý sao chép, sửa hoặc thay thế file keyring khi máy chủ đang hoạt động. Cách tạo bản sao nhất quán phụ thuộc component/plugin và phiên bản; hãy dùng quy trình backup được tài liệu của cơ chế đó hỗ trợ. Có thể cần cửa sổ bảo trì, thao tác đồng bộ hoặc cơ chế backup riêng. Luôn thử phục hồi bản keyring trong môi trường cô lập trước khi dựa vào nó trong sự cố thật.

### Phân biệt khóa MySQL và khóa mã hóa bản sao lưu

Khóa trong keyring MySQL bảo vệ dữ liệu do MySQL mã hóa. Khóa dùng để mã hóa file dump, snapshot, archive hoặc bản sao lưu ở tầng lưu trữ có thể là một khóa khác. Ghi rõ mỗi khóa bảo vệ lớp nào, được quản lý ở đâu và ai có quyền khôi phục.

Giữ bản sao khóa hoặc khả năng truy cập KMS độc lập với nơi lưu bản sao dữ liệu. Nếu bản sao lưu và khóa giải mã cùng nằm trong một tài khoản hoặc một vùng lưu trữ có thể bị xóa cùng lúc, một sự cố duy nhất có thể làm mất cả hai. Với KMS/HSM, bảo vệ danh tính dịch vụ, chính sách IAM, thông tin xác thực và quy trình khôi phục quyền truy cập.

## 6. Tổ chức và bảo vệ bộ sao lưu

Phân loại dữ liệu trước khi lưu:

| Loại dữ liệu | Ví dụ | Biện pháp bảo vệ đề xuất |
|---|---|---|
| Cấu hình thông thường | Tham số InnoDB, cổng, đường dẫn, chế độ SQL | Kiểm soát phiên bản trong kho riêng tư; rà soát secret trước khi commit |
| Cấu hình nhạy cảm | Mật khẩu client, token, thông tin truy cập dịch vụ ngoài | Secret manager hoặc kho bí mật chuyên dụng |
| Account và grants | Định nghĩa user, role, authentication metadata | Mã hóa, quyền đọc hạn chế, audit truy cập |
| Chứng thư công khai | CA certificate, server certificate | Lưu cùng metadata thời hạn và chuỗi tin cậy |
| Khóa riêng và keyring | Private key, keyring data, khóa xuất từ hệ thống được phép | Kho bảo mật riêng, mã hóa và kiểm soát truy cập nghiêm ngặt |
| Metadata KMS/HSM | Key ID, policy, danh tính dịch vụ, hướng dẫn khôi phục | Lưu tài liệu vận hành an toàn và kiểm tra quyền truy cập định kỳ |

Mỗi bộ sao lưu nên có mã định danh, thời điểm tạo, phiên bản MySQL, máy nguồn, phạm vi account/configuration, phiên bản chứng thư, key identifier và checksum phù hợp. Ghi lại mối liên hệ với bản sao dữ liệu và binary log cần dùng để phục hồi đến thời điểm mong muốn.

Áp dụng nguyên tắc tách quyền: người có thể đọc bản sao dữ liệu không nhất thiết được đọc private key hoặc secret quản trị. Dùng mã hóa khi truyền và khi lưu, giới hạn thời gian lưu giữ, ghi log truy cập và có bản sao ngoại tuyến hoặc vùng lưu trữ độc lập cho kịch bản ransomware.

## 7. Quy trình phục hồi theo thứ tự phụ thuộc

Phục hồi các thành phần theo thứ tự giúp tránh khởi động máy chủ khi thiếu khóa hoặc chứng thư cần thiết:

1. **Chuẩn bị môi trường:** cài đúng phiên bản MySQL tương thích, plugin/component, thư viện và gói hệ điều hành. Ghi nhận khác biệt giữa máy nguồn và máy đích.
2. **Khôi phục danh tính và quyền hệ điều hành:** tạo tài khoản dịch vụ, thư mục, chủ sở hữu và ACL cho data directory, log, chứng thư và keyring.
3. **Khôi phục cấu hình:** áp dụng option file, cấu hình service và tham số khởi động; rà soát đường dẫn, cổng, biến hệ thống và các giá trị `SET PERSIST`.
4. **Khôi phục cơ chế khóa:** cấu hình keyring hoặc quyền truy cập KMS/HSM trước khi MySQL mở dữ liệu được mã hóa.
5. **Khôi phục TLS:** đặt CA, chứng thư và khóa riêng đúng vị trí; xác minh quyền file và hostname.
6. **Khởi động và kiểm tra máy chủ:** xem error log, trạng thái plugin/component, biến TLS, trạng thái mã hóa và khả năng đọc dữ liệu.
7. **Phục hồi dữ liệu:** nạp bản sao lưu và áp dụng binary log nếu mục tiêu là phục hồi đến một thời điểm cụ thể.
8. **Phục hồi account và quyền:** tạo lại account/role, grants và default role bằng các câu lệnh đã xuất; kiểm tra quyền bằng account thực tế.
9. **Kiểm tra ứng dụng:** thử kết nối TLS, xác thực, truy vấn cần thiết và thao tác ghi trong môi trường thử nghiệm trước khi mở traffic.

Nếu phục hồi sang một máy chủ mới, không sao chép danh tính máy chủ cũ một cách máy móc. Đặc biệt, xem xét `auto.cnf` chứa `server_uuid`; các instance độc lập hoặc replica cần định danh phù hợp và duy nhất. Làm theo quy trình clone/replication của phiên bản MySQL đang dùng.

Không mở traffic ứng dụng ngay sau khi tiến trình `mysqld` báo đã chạy. Máy chủ cần vượt qua kiểm tra log, plugin, TLS, keyring, quyền và dữ liệu trước khi được đưa lại vào dịch vụ.

## 8. Kiểm tra sau phục hồi

Phục hồi chỉ được xem là đạt khi các chức năng cần thiết hoạt động. Dùng checklist kiểm tra:

- [ ] Phiên bản MySQL và plugin/component tương thích với kế hoạch phục hồi.
- [ ] MySQL khởi động không có lỗi cấu hình, lỗi quyền file hoặc lỗi nạp component.
- [ ] Các biến hệ thống quan trọng có giá trị mong đợi; các giá trị được lưu bền đã được rà soát.
- [ ] Keyring/KMS/HSM sẵn sàng và có thể mở dữ liệu được mã hóa.
- [ ] Chứng thư còn hạn, hostname và chuỗi CA hợp lệ; client kết nối bằng TLS thành công.
- [ ] Account, plugin xác thực, role, grants và default role đã được khôi phục.
- [ ] `CURRENT_USER()` trả về account dự kiến khi đăng nhập; `SHOW GRANTS` khớp với quyền đã thiết kế.
- [ ] Ứng dụng đọc/ghi được đúng đối tượng và các thao tác vượt quyền bị từ chối.
- [ ] Backup mới có thể được tạo từ máy đã phục hồi và được lưu ở vị trí độc lập.

Ghi lại thời gian thực tế cho từng bước và so sánh với RTO. Xác định điểm dữ liệu phục hồi cuối cùng và so sánh với RPO. Một lần phục hồi thành công giúp kiểm chứng quy trình, nhưng cần lặp lại định kỳ và sau những thay đổi lớn về phiên bản, chứng thư, plugin, keyring hoặc KMS.

## 9. Những lỗi thường gặp

- **Chỉ sao lưu schema và bảng:** máy chủ có dữ liệu nhưng thiếu cấu hình, account, chứng thư hoặc khóa để vận hành. Duy trì danh mục thành phần ngoài dữ liệu.
- **Bỏ qua option file được include:** một phần cấu hình quan trọng không được khôi phục. Kiểm kê nguồn cấu hình thực tế và tham số service.
- **Không lưu `mysqld-auto.cnf`:** các biến đặt bằng `SET PERSIST` bị mất hoặc khác với máy nguồn. Đưa tệp này vào kế hoạch và rà soát khi phục hồi.
- **Xuất account nhưng quên role mặc định:** người dùng đăng nhập được nhưng thiếu quyền mong đợi. Ghi nhận grants, quan hệ role và default role.
- **Chép thô system schema giữa các phiên bản:** cấu trúc grant table hoặc data dictionary không tương thích. Dùng phương pháp di chuyển account được hỗ trợ.
- **Mất khóa riêng hoặc keyring:** dữ liệu mã hóa không thể giải mã. Kiểm tra phục hồi khóa cùng bản sao dữ liệu.
- **Lưu backup và khóa giải mã cùng nơi:** một sự cố có thể làm mất cả dữ liệu lẫn khả năng phục hồi. Tách miền lưu trữ và quyền truy cập.
- **Không giữ quyền file:** MySQL không đọc được chứng thư hoặc keyring sau khi phục hồi. Khôi phục chủ sở hữu và ACL.
- **Không theo dõi hạn chứng thư:** máy chủ hoặc client ngừng kết nối khi chứng thư hết hạn. Lập lịch kiểm tra và gia hạn.
- **Không kiểm tra quyền KMS/HSM:** file cấu hình còn nhưng máy chủ phục hồi không có danh tính hoặc chính sách để lấy khóa. Thử nghiệm truy cập bằng danh tính thực tế.

## 10. Bài tập thực hành

Trên một môi trường MySQL thử nghiệm, hãy lập bộ hồ sơ phục hồi cho một schema ứng dụng giả định:

1. Ghi lại phiên bản MySQL, các biến cấu hình liên quan, plugin/component và các nguồn option file.
2. Tạo hai account ứng dụng với quyền khác nhau, một role dùng chung và một role mặc định; xuất `SHOW CREATE USER` cùng `SHOW GRANTS`.
3. Ghi lại đường dẫn TLS, CA, chứng thư máy chủ, thời hạn chứng thư và quyền file. Không đưa khóa riêng vào báo cáo thực hành.
4. Nếu môi trường có mã hóa InnoDB, xác định keyring/KMS/HSM, quy trình tạo bản sao được hỗ trợ và quyền cần để phục hồi.
5. Lưu metadata và các bản sao cần thiết trong vùng lưu trữ thử nghiệm có kiểm soát truy cập; ghi checksum và thời điểm.
6. Dựng một máy MySQL thử nghiệm mới, phục hồi cấu hình, cơ chế khóa, TLS, dữ liệu và account theo đúng thứ tự.
7. Kiểm tra kết nối, `CURRENT_USER()`, `SHOW GRANTS`, đọc dữ liệu mã hóa và một thao tác ứng dụng hợp lệ.

**Tiêu chí hoàn thành:** có thể tái tạo cấu hình, account và kết nối TLS; dữ liệu mã hóa đọc được; account nhận đúng quyền; và nhóm vận hành có thể chỉ ra vị trí an toàn của từng bản sao cũng như quy trình khôi phục chúng.

## Kết luận

Để phục hồi MySQL đáng tin cậy, hãy quản lý cấu hình, account, chứng thư và khóa mã hóa như những thành phần bắt buộc của kế hoạch sao lưu. Ghi nhận đầy đủ phiên bản và phụ thuộc, bảo vệ secret bằng quyền truy cập phù hợp, dùng cơ chế xuất/backup được hỗ trợ và kiểm tra phục hồi định kỳ. Khi máy chủ có thể khởi động, giải mã dữ liệu, xác thực đúng người dùng và phục vụ ứng dụng qua TLS, bạn mới có bằng chứng rằng bộ sao lưu đã đáp ứng mục tiêu vận hành.
