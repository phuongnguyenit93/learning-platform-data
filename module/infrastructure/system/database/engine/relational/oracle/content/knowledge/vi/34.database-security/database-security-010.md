# TDE, keystore, sao lưu khóa và điều kiện tính năng/giấy phép

Transparent Data Encryption (TDE) là cơ chế mã hóa dữ liệu khi lưu trữ (data at rest) của Oracle Database. TDE mã hóa dữ liệu trong datafile để người lấy được file vật lý, bản sao lưu hoặc thiết bị lưu trữ không thể đọc nội dung nếu không có khóa phù hợp. Ứng dụng vẫn truy vấn dữ liệu bằng SQL như bình thường; database tự giải mã khi người dùng được phép truy cập dữ liệu.

TDE chỉ có ý nghĩa khi quản lý khóa đúng cách. Database có thể chứa datafile được mã hóa nhưng vẫn không khôi phục được nếu keystore mất, hỏng hoặc không có master key cần thiết. Vì vậy, thiết kế TDE phải bao gồm cả:

- Phạm vi dữ liệu cần mã hóa.
- Loại TDE: column encryption hay tablespace encryption.
- Keystore/wallet và vị trí lưu.
- Master encryption key và vòng đời của khóa.
- Mở/đóng keystore, auto-login và quản lý mật khẩu.
- Sao lưu khóa, phục hồi và kiểm thử restore.
- Đồng bộ khóa giữa primary/standby, RAC node và PDB.
- Kiểm tra edition, feature và điều kiện license.

TDE là một lớp bảo vệ dữ liệu lưu trữ, không thay thế kiểm soát truy cập, mã hóa network, quản lý secret, audit hoặc backup policy.

## 1. TDE giải quyết vấn đề gì?

Nếu database lưu dữ liệu nhạy cảm dưới dạng plaintext trên thiết bị lưu trữ, người có quyền đọc trực tiếp datafile hoặc bản sao file có thể tìm cách truy xuất dữ liệu ngoài đường truy cập SQL thông thường.

TDE mã hóa dữ liệu ở tầng database storage:

~~~text
Ứng dụng
   |
   | SQL: SELECT / INSERT / UPDATE
   v
Oracle Database
   |
   | Mã hóa/giải mã trong database
   v
Datafile trên disk: dữ liệu đã mã hóa
   |
   v
Storage / backup media
~~~

Khi một session hợp lệ đọc dữ liệu, Oracle giải mã trong database và trả kết quả theo quyền truy cập SQL của session. Khi ghi, database mã hóa dữ liệu trước khi ghi xuống storage theo cơ chế TDE.

### 1.1 Những rủi ro TDE giúp giảm

- Kẻ tấn công lấy được bản sao datafile nhưng không có keystore/key.
- Thiết bị lưu trữ hoặc media bị thất lạc.
- File database bị sao chép trái phép ở tầng OS/storage.
- Bản backup chứa dữ liệu của tablespace được mã hóa, khi backup được xử lý đúng theo cơ chế và cấu hình tương ứng.

### 1.2 Những rủi ro TDE không tự giải quyết

- Người dùng có quyền SELECT dữ liệu nhạy cảm vẫn có thể đọc plaintext qua SQL.
- Tài khoản ứng dụng bị chiếm quyền vẫn có thể truy vấn dữ liệu mà tài khoản đó được phép đọc.
- SQL injection vẫn có thể lấy dữ liệu đã giải mã qua database.
- TDE không tự mã hóa dữ liệu trên đường truyền; cần TLS/Oracle Net encryption theo chính sách.
- TDE không ngăn người dùng hợp lệ xuất dữ liệu ra CSV, log, report hoặc hệ thống khác.
- TDE không thay thế Data Masking, Data Redaction, VPD, auditing hoặc phân quyền.
- TDE không bảo vệ nếu attacker đồng thời có quyền truy cập database và keystore cần thiết.

TDE chủ yếu bảo vệ dữ liệu lưu trữ khỏi truy cập trái phép ở tầng file/media. Hãy xác định đúng threat model trước khi triển khai.

## 2. Các khái niệm khóa trong TDE

TDE dùng mô hình khóa phân cấp. Cách diễn đạt chi tiết có thể khác giữa column encryption và tablespace encryption, nhưng các khái niệm chính gồm:

- **TDE master encryption key:** khóa chính được quản lý trong keystore.
- **Data encryption key / table key / tablespace key:** khóa dùng mã hóa dữ liệu thực tế hoặc khóa dữ liệu.
- **Keystore:** nơi Oracle lưu master key và metadata khóa.
- **Wallet:** tên thường dùng cho software keystore; có thể ở dạng PKCS#12 và các file auto-login.

Mô hình khái quát:

~~~text
Password-protected keystore
       |
       +-- TDE master key
                |
                +-- bảo vệ khóa dữ liệu của column encryption
                |
                +-- bảo vệ khóa tablespace encryption
                         |
                         v
                  Encrypted data blocks
~~~

Master key không phải khóa duy nhất trực tiếp mã hóa mọi byte trong mọi datafile. Nó tham gia bảo vệ các khóa dữ liệu. Cách phân cấp này cho phép xoay master key mà không nhất thiết phải mã hóa lại toàn bộ datafile từ đầu.

### 2.1 Mất keystore có thể đồng nghĩa mất khả năng giải mã

Nếu datafile còn nguyên nhưng keystore chứa master key bị mất hoặc không thể mở, Oracle có thể không giải mã được dữ liệu TDE. Backup database mà không backup keystore tương ứng là quy trình phục hồi chưa đầy đủ.

### 2.2 Giữ lịch sử khóa

Khi xoay master key, khóa cũ thường vẫn cần để giải mã dữ liệu hoặc backup được tạo trước đó. Không xóa key version cũ chỉ vì key mới đã active.

Chỉ xem xét dọn khóa cũ khi:

- Đã biết rõ dữ liệu nào còn tham chiếu khóa đó.
- Các backup/archived backup cần giữ đã hết retention hoặc được chuyển đổi theo quy trình đã kiểm chứng.
- Đã có backup keystore đầy đủ.
- Đã kiểm thử restore và recovery.
- Được DBA/security owner phê duyệt.

## 3. Column encryption và tablespace encryption

Oracle TDE có hai cách triển khai chính: mã hóa từng cột hoặc mã hóa toàn bộ tablespace.

### 3.1 TDE column encryption

Column encryption mã hóa các cột được chỉ định trong table. Ví dụ dữ liệu định danh:

~~~sql
CREATE TABLE employees_secure (
    employee_id NUMBER PRIMARY KEY,
    employee_name VARCHAR2(100),
    national_id VARCHAR2(30) ENCRYPT
);
~~~

Chỉ cột NATIONAL_ID được chỉ định ENCRYPT trong ví dụ. Các cột khác không tự động được mã hóa bằng column encryption.

Ưu điểm:

- Có thể giới hạn phạm vi mã hóa ở một số cột nhạy cảm.
- Hữu ích khi chỉ một phần dữ liệu trong table cần bảo vệ.
- Có thể áp dụng mà không cần chuyển toàn bộ tablespace sang encrypted tablespace.

Điểm cần cân nhắc:

- Có giới hạn kiểu dữ liệu và thao tác được hỗ trợ.
- Index, constraint, truy vấn equality và SALT có các quy tắc riêng.
- Các bản sao dữ liệu ở tầng ứng dụng, export hoặc log vẫn cần bảo vệ riêng.
- Quản lý cột và schema có thể phức tạp khi số cột nhạy cảm lớn.

### 3.2 TDE tablespace encryption

Tablespace encryption mã hóa dữ liệu trong tablespace. Các segment được lưu trong tablespace đó được bảo vệ ở tầng tablespace, bao gồm nhiều loại dữ liệu mà column encryption không áp dụng trực tiếp.

Ví dụ tạo encrypted tablespace:

~~~sql
CREATE TABLESPACE secure_ts
DATAFILE '/u02/oradata/ORCL/secure_ts01.dbf'
SIZE 500M
ENCRYPTION USING 'AES256'
DEFAULT STORAGE (ENCRYPT);
~~~

Ví dụ minh họa cú pháp; tên file, storage, algorithm và khả năng sử dụng phải phù hợp phiên bản/edition và tiêu chuẩn nội bộ.

Ưu điểm:

- Bảo vệ mọi segment nằm trong tablespace được mã hóa.
- Phù hợp khi một ứng dụng/schema có nhiều dữ liệu nhạy cảm.
- Giảm việc phải gắn ENCRYPT cho từng cột.
- Có thể bao phủ LOB segment khi LOB được lưu trong encrypted tablespace.

Điểm cần cân nhắc:

- Phải quản lý tablespace placement và migration.
- Có thể có chi phí CPU/I/O tùy workload và nền tảng.
- Việc chuyển tablespace hiện hữu sang encryption cần kế hoạch dung lượng, thời gian và kiểm tra hỗ trợ.

### 3.3 So sánh

| Tiêu chí | Column encryption | Tablespace encryption |
|---|---|---|
| Phạm vi | Cột được chọn | Dữ liệu trong tablespace |
| Cấu hình | Khai báo ở cột | Khai báo ở tablespace |
| LOB | Có giới hạn hỗ trợ; không giả định mọi LOB column được mã hóa trực tiếp | Có thể được bảo vệ nếu segment nằm trong encrypted tablespace |
| Index | Có các giới hạn liên quan SALT và loại index | Index segment được bảo vệ nếu nằm trong encrypted tablespace |
| Quản trị | Theo từng cột/table | Theo tablespace và placement |
| Phù hợp | Một số trường dữ liệu nhạy cảm | Một vùng lưu trữ hoặc workload cần mã hóa rộng |

Chọn phương án theo kiến trúc lưu trữ, loại dữ liệu, query pattern, yêu cầu tuân thủ và phiên bản Oracle.

## 4. Thuật toán mã hóa

Oracle TDE hỗ trợ các thuật toán AES với độ dài khóa khác nhau tùy phiên bản và loại TDE:

- AES128.
- AES192.
- AES256.

Ví dụ tablespace dùng AES256:

~~~sql
CREATE TABLESPACE secure_ts
DATAFILE '/u02/oradata/ORCL/secure_ts01.dbf'
SIZE 500M
ENCRYPTION USING 'AES256'
DEFAULT STORAGE (ENCRYPT);
~~~

Với column encryption, có thể chỉ định thuật toán theo cú pháp được phiên bản hỗ trợ; nếu không chỉ định, Oracle dùng mặc định của tính năng/phiên bản.

Không chọn thuật toán chỉ theo suy nghĩ “số bit lớn nhất luôn tốt nhất”. Hãy cân nhắc:

- Chuẩn bảo mật của tổ chức.
- Hỗ trợ của phiên bản và nền tảng.
- Hiệu năng CPU và khả năng tăng tốc phần cứng.
- Khả năng tương thích giữa primary, standby và môi trường restore.
- Điều kiện license.

Không tự giả định mặc định thuật toán giống nhau ở mọi phiên bản hoặc mọi kiểu mã hóa.

## 5. SALT trong column encryption

Column encryption có thể dùng SALT để làm cho cùng một plaintext không nhất thiết tạo cùng ciphertext ở các hàng khác nhau.

Ví dụ:

~~~sql
CREATE TABLE customer_identity (
    customer_id NUMBER PRIMARY KEY,
    national_id VARCHAR2(30) ENCRYPT
);
~~~

Theo cấu hình mặc định của column encryption, Oracle có thể áp dụng SALT. SALT làm tăng khả năng chống phân tích mẫu lặp, nhưng ảnh hưởng một số thao tác index/equality.

### 5.1 NO SALT

Trong một số trường hợp cần index trên cột được mã hóa, Oracle cho phép khai báo NO SALT:

~~~sql
CREATE TABLE customer_identity (
    customer_id NUMBER PRIMARY KEY,
    national_id VARCHAR2(30) ENCRYPT NO SALT
);
~~~

NO SALT tạo tính chất mã hóa xác định hơn đối với cùng plaintext và có thể làm lộ mẫu giá trị lặp. Điều này là một trade-off bảo mật; không dùng chỉ để làm index hoạt động mà không đánh giá rủi ro.

### 5.2 Không tự giả định mọi phép toán đều được hỗ trợ

Các thao tác trên encrypted column phụ thuộc kiểu dữ liệu, thuật toán, SALT, index và phiên bản. Trước khi thiết kế truy vấn, kiểm tra tài liệu TDE của release đang dùng đối với:

- Equality predicate.
- Range predicate.
- Join.
- ORDER BY/GROUP BY.
- Index creation.
- Function-based index.
- Constraint.
- Export/import.

## 6. Keystore (wallet) là gì?

Keystore là nơi Oracle lưu TDE master encryption keys. Với software keystore, Oracle thường sử dụng định dạng PKCS#12.

Các file thường gặp:

- ewallet.p12: password-protected keystore.
- cwallet.sso: auto-login keystore.

Đường dẫn thực tế phụ thuộc cấu hình WALLET_ROOT hoặc cấu hình wallet theo phiên bản.

### 6.1 Password-protected keystore

Keystore được bảo vệ bằng mật khẩu. Khi cần mở, người vận hành phải cung cấp mật khẩu theo cơ chế quản trị.

Ưu điểm:

- Có kiểm soát mở keystore bằng secret.
- Phù hợp quy trình yêu cầu thao tác thủ công hoặc tích hợp secret management.
- Có thể dùng làm nguồn tạo auto-login keystore.

Nhược điểm:

- Cần quản lý mật khẩu và quy trình mở sau restart.
- Nếu không có người/secret service mở keystore, database có thể không truy cập được dữ liệu mã hóa sau restart.

### 6.2 Auto-login keystore

Auto-login keystore cho phép database mở keystore mà không cần nhập password tương tác trong một số ngữ cảnh khởi động.

File thường là cwallet.sso. Nó giúp vận hành tự động, nhưng file này cũng là secret quan trọng:

- Bảo vệ bằng filesystem permissions.
- Không để trong source control.
- Không đưa vào container image dùng chung.
- Không gửi qua email/chat.
- Chỉ sao chép qua kênh bảo mật.

Auto-login không có nghĩa keystore không còn nhạy cảm. Người có quyền truy cập file auto-login và môi trường phù hợp có thể có khả năng sử dụng khóa.

### 6.3 Local auto-login keystore

Local auto-login keystore được ràng buộc với máy chủ nơi nó được tạo theo cơ chế Oracle. Đây có thể là lựa chọn cho môi trường cần hạn chế việc sao chép auto-login file sang máy khác.

Khi chuyển host, clone hoặc phục hồi server, cần tạo/khôi phục keystore theo hướng dẫn đúng phiên bản; không giả định local auto-login file có thể dùng ở mọi host.

### 6.4 Password wallet và auto-login wallet phải được quản lý cùng nhau

Auto-login file thường được tạo từ password-protected keystore. Giữ bản backup an toàn của password wallet và master keys. Không chỉ giữ cwallet.sso rồi xóa bản gốc ewallet.p12.

## 7. Cấu hình WALLET_ROOT và TDE_CONFIGURATION

Với các phiên bản Oracle hỗ trợ cấu hình hiện đại, WALLET_ROOT xác định thư mục gốc chứa wallet/keystore. TDE_CONFIGURATION chỉ định kiểu cấu hình keystore.

Ví dụ:

~~~sql
ALTER SYSTEM SET WALLET_ROOT =
    '/u01/app/oracle/admin/ORCL/wallet'
    SCOPE = SPFILE;
~~~

WALLET_ROOT là tham số tĩnh trong các cấu hình phổ biến, do đó có thể cần restart instance để nhận giá trị mới.

Sau khi cấu hình WALLET_ROOT và khởi động lại:

~~~sql
ALTER SYSTEM SET TDE_CONFIGURATION =
    'KEYSTORE_CONFIGURATION=FILE'
    SCOPE = BOTH;
~~~

Đây là ví dụ cho software file keystore. Cú pháp, tham số và yêu cầu restart phụ thuộc phiên bản Oracle và loại keystore (FILE/OKV hoặc cấu hình khác được hỗ trợ).

### 7.1 Vị trí keystore theo WALLET_ROOT

Trong các cấu hình phổ biến, Oracle sử dụng thư mục con liên quan TDE dưới WALLET_ROOT để lưu keystore. Không tự đoán path khi triển khai; xác nhận bằng V$ENCRYPTION_WALLET và tài liệu phiên bản.

### 7.2 Phiên bản cũ dùng sqlnet.ora

Các bản Oracle cũ có thể cấu hình wallet location bằng tham số ENCRYPTION_WALLET_LOCATION trong sqlnet.ora. Không trộn hai cách cấu hình mà không hiểu thứ tự ưu tiên và quy tắc migration.

Khi nâng cấp database, cần rà soát:

- Phiên bản nguồn/đích.
- WALLET_ROOT đã được cấu hình chưa.
- TDE_CONFIGURATION có giá trị gì.
- sqlnet.ora còn cấu hình wallet cũ không.
- Wallet thực tế đang được instance mở từ đường dẫn nào.

## 8. Tạo password-protected keystore

Ví dụ tạo software keystore:

~~~sql
ADMINISTER KEY MANAGEMENT CREATE KEYSTORE
    '/u01/app/oracle/admin/ORCL/wallet/tde'
    IDENTIFIED BY "StrongKeystorePassword";
~~~

Mật khẩu trong ví dụ chỉ là placeholder. Không sử dụng nguyên văn trong production và không ghi secret thật vào script lưu trong repository.

Mật khẩu keystore nên được:

- Sinh ngẫu nhiên theo policy.
- Lưu trong secret manager/password vault được phê duyệt.
- Cấp quyền theo vai trò.
- Có quy trình rotation và emergency access.
- Không hard-code trong file cấu hình ứng dụng.

### 8.1 Mở keystore

~~~sql
ADMINISTER KEY MANAGEMENT SET KEYSTORE OPEN
    IDENTIFIED BY "StrongKeystorePassword";
~~~

Trong môi trường multitenant, phạm vi CONTAINER phải được xác định rõ. Không mở hoặc thay đổi keystore của tất cả PDB nếu chỉ cần thao tác trong một container.

### 8.2 Kiểm tra trạng thái

~~~sql
SELECT con_id,
       wrl_type,
       wrl_parameter,
       status,
       wallet_type,
       keystore_mode,
       fully_backed_up
FROM v$encryption_wallet
ORDER BY con_id;
~~~

Các trường thường dùng:

- WRL_TYPE: loại vị trí keystore.
- WRL_PARAMETER: đường dẫn/tham số wallet.
- STATUS: trạng thái keystore.
- WALLET_TYPE: PASSWORD, AUTOLOGIN hoặc loại tương ứng.
- KEYSTORE_MODE: UNITED hoặc ISOLATED trong multitenant.
- FULLY_BACKED_UP: trạng thái backup theo metadata mà Oracle báo cáo.

Các cột có thể khác theo release. Kiểm tra view metadata trước khi dùng trên phiên bản cũ.

Trạng thái thường gặp có thể gồm OPEN, CLOSED, OPEN_NO_MASTER_KEY, OPEN_UNKNOWN_MASTER_KEY_STATUS hoặc NOT_AVAILABLE tùy phiên bản và ngữ cảnh. Hãy tra ý nghĩa chính xác theo release.

## 9. Tạo và kích hoạt TDE master key

Sau khi keystore đã được tạo và mở, cần thiết lập master key để TDE sử dụng.

Ví dụ:

~~~sql
ADMINISTER KEY MANAGEMENT SET KEY
    IDENTIFIED BY "StrongKeystorePassword"
    WITH BACKUP USING 'initial_tde_master_key';
~~~

Lệnh SET KEY tạo/đặt master key hiện hành theo cơ chế TDE và yêu cầu backup keystore trong ví dụ. Backup identifier giúp nhận diện bản backup được tạo.

### 9.1 Kiểm tra key metadata

~~~sql
SELECT con_id,
       key_id,
       tag,
       creation_time,
       activation_time,
       creator,
       user_name
FROM v$encryption_keys
ORDER BY activation_time DESC;
~~~

View và cột khả dụng phụ thuộc phiên bản/quyền. Không hiển thị hoặc chia sẻ nội dung secret; metadata key ID không phải bản thân master key.

### 9.2 Key ID không phải key material

KEY_ID là định danh khóa. Không thể khôi phục master key chỉ từ KEY_ID. Phải giữ keystore và backup tương ứng.

### 9.3 Không tự tạo master key liên tục

SET KEY là thao tác vòng đời khóa, không phải câu lệnh kiểm tra trạng thái. Chỉ thực hiện khi tạo mới, rotate hoặc theo quy trình quản trị đã phê duyệt. Mỗi lần thay đổi cần ghi nhận, backup và đồng bộ tới các môi trường phụ thuộc.

## 10. Tạo auto-login keystore

Sau khi có password-protected keystore, có thể tạo auto-login keystore:

~~~sql
ADMINISTER KEY MANAGEMENT CREATE AUTO_LOGIN KEYSTORE
    FROM KEYSTORE
    '/u01/app/oracle/admin/ORCL/wallet/tde'
    IDENTIFIED BY "StrongKeystorePassword";
~~~

Oracle tạo file auto-login tương ứng trong vị trí keystore theo quy tắc của phiên bản.

### 10.1 Tạo local auto-login

Trong môi trường hỗ trợ:

~~~sql
ADMINISTER KEY MANAGEMENT CREATE LOCAL AUTO_LOGIN KEYSTORE
    FROM KEYSTORE
    '/u01/app/oracle/admin/ORCL/wallet/tde'
    IDENTIFIED BY "StrongKeystorePassword";
~~~

Local auto-login có ràng buộc host. Xác nhận hỗ trợ và hành vi khi copy/restore trên release đang chạy.

### 10.2 Auto-login không thay thế password backup

Khi cần:

- Khôi phục trên host mới.
- Mở keystore thủ công.
- Thay đổi password.
- Import/export key.
- Tạo auto-login lại.

password-protected keystore và password gốc có thể cần thiết. Hãy backup cả keystore gốc và các artifact cần thiết theo quy trình.

## 11. Đóng keystore và khởi động lại database

Đóng keystore:

~~~sql
ADMINISTER KEY MANAGEMENT SET KEYSTORE CLOSE
    IDENTIFIED BY "StrongKeystorePassword";
~~~

Trong một số ngữ cảnh có thể đóng mà không cung cấp password hoặc dùng cú pháp khác theo loại wallet; tuân theo tài liệu release.

Nếu database đang dùng encrypted tablespace/column, đóng keystore có thể làm các thao tác cần giải mã thất bại hoặc khiến dữ liệu TDE không truy cập được cho tới khi keystore mở lại.

### 11.1 Sau restart

Kiểm tra:

1. Instance mở đúng keystore path.
2. Wallet status là trạng thái mong đợi.
3. Master key có sẵn.
4. PDB cần thiết đã mở keystore.
5. Query tới encrypted object hoạt động.
6. Standby/RAC node có cùng key material cần thiết.

Không chỉ kiểm tra database OPEN. Database có thể OPEN trong khi keystore chưa OPEN hoặc chưa có master key phù hợp.

## 12. Xoay vòng master key

Key rotation là việc tạo master key mới và chuyển key hiện hành sang version mới theo quy trình Oracle. Khóa cũ thường được giữ lại để giải mã dữ liệu/backup đã được bảo vệ bằng version cũ.

Ví dụ:

~~~sql
ADMINISTER KEY MANAGEMENT SET KEY
    IDENTIFIED BY "StrongKeystorePassword"
    WITH BACKUP USING 'rotate_tde_key_2026';
~~~

Đây là dạng lệnh thường dùng để đặt/rotate master key và tạo backup. Cú pháp cụ thể có thể khác theo ngữ cảnh CDB/PDB hoặc release.

### 12.1 Rotation không đồng nghĩa mã hóa lại toàn bộ datafile

Trong mô hình khóa phân cấp, master key bảo vệ khóa dữ liệu. Việc đổi master key thường cập nhật lớp bảo vệ khóa dữ liệu thay vì đọc và mã hóa lại mọi block datafile như một full rewrite. Tuy nhiên, tác động và quy trình phụ thuộc loại TDE, thao tác rekey và phiên bản.

### 12.2 Khi nào cần rotation?

- Theo lịch rotation của tổ chức.
- Sau sự cố nghi ngờ lộ master key hoặc keystore password.
- Sau thay đổi nhân sự/quyền quản trị quan trọng.
- Khi chính sách bảo mật yêu cầu.
- Khi chuyển đổi kiến trúc keystore.

Rotation không xóa nhu cầu bảo vệ các key version cũ.

### 12.3 Backup ngay sau rotation

Mỗi lần đổi key cần:

1. Xác nhận keystore mở đúng.
2. Thực hiện rotation trong cửa sổ được phê duyệt.
3. Tạo backup keystore.
4. Sao chép backup tới nơi lưu trữ an toàn khác.
5. Đồng bộ tới standby/RAC/PDB cần thiết.
6. Ghi nhận key ID, tag, thời gian và người thực hiện.
7. Kiểm thử khả năng mở keystore và truy cập dữ liệu.

## 13. Backup keystore và master key

Backup database và backup keystore là hai phần khác nhau của kế hoạch bảo vệ dữ liệu. Một backup database có thể không đủ để phục hồi dữ liệu TDE nếu thiếu key material tương ứng.

### 13.1 Tạo backup bằng ADMINISTER KEY MANAGEMENT

Ví dụ:

~~~sql
ADMINISTER KEY MANAGEMENT BACKUP KEYSTORE
    USING 'before_maintenance'
    IDENTIFIED BY "StrongKeystorePassword";
~~~

Lệnh backup tạo bản backup keystore theo cơ chế Oracle. Cú pháp có thể có thêm lựa chọn TO file_name hoặc khác theo release. Xác nhận file backup được tạo ở đâu và quyền truy cập filesystem.

### 13.2 WITH BACKUP khi tạo/rotate key

Khi SET KEY, dùng WITH BACKUP để yêu cầu Oracle tạo backup keystore:

~~~sql
ADMINISTER KEY MANAGEMENT SET KEY
    IDENTIFIED BY "StrongKeystorePassword"
    WITH BACKUP USING 'before_key_change';
~~~

Không coi backup tự động này là bản backup duy nhất. Cần đưa artifact ra kho backup an toàn, tách biệt với host/database.

### 13.3 Backup ra ngoài host

Quy trình backup nên:

- Sao chép password-protected keystore.
- Giữ auto-login artifact nếu kiến trúc cần và chính sách cho phép.
- Lưu password/secret trong secret manager riêng.
- Mã hóa đường truyền và nơi lưu backup.
- Giới hạn quyền đọc.
- Có bản off-host/offline hoặc immutable theo chính sách.
- Có checksum và manifest nhận diện phiên bản.
- Kiểm tra khả năng restore định kỳ.

Không đặt bản backup duy nhất trong cùng filesystem với datafile. Nếu host/storage mất, cả database và key có thể cùng mất.

### 13.4 Backup keystore sau mỗi lần thay đổi khóa

Những thay đổi sau cần được ghi nhận và backup:

- Tạo master key đầu tiên.
- Rotate master key.
- Import key từ hệ thống khác.
- Thay đổi password keystore.
- Thay đổi cấu hình keystore.
- Tạo/đổi auto-login wallet.

Backup phải được gắn với thời điểm và database/PDB/keystore tương ứng.

## 14. Phục hồi database TDE khi restore

Một kịch bản restore database được mã hóa cần cả:

- Backup database/datafile/control file/redo phù hợp.
- Keystore chứa master key cần thiết.
- Password hoặc cơ chế mở keystore.
- Cấu hình wallet path/TDE_CONFIGURATION.
- Quyền truy cập filesystem.
- Môi trường Oracle tương thích.

Quy trình khái quát:

~~~text
Chuẩn bị host/database
       |
       v
Khôi phục keystore đúng bản
       |
       v
Đặt quyền file và cấu hình wallet
       |
       v
Mở keystore
       |
       v
Restore/recover database
       |
       v
Kiểm tra encrypted tablespace/column
       |
       v
Kiểm thử truy vấn và ứng dụng
~~~

Thứ tự chi tiết phụ thuộc trạng thái database và loại restore. Có trường hợp cần mở keystore trước khi mount/open hoặc trước thao tác đọc datafile mã hóa. Làm theo runbook đã kiểm thử cho phiên bản và kiến trúc thực tế.

### 14.1 Backup cũ cần key cũ

Nếu backup được tạo trước một lần rotation, cần bảo đảm keystore hiện tại vẫn giữ các key version cần thiết để giải mã dữ liệu từ backup đó.

Không xóa key cũ chỉ vì database hiện tại query thành công. Backup cũ có thể cần phục hồi trong tương lai.

### 14.2 Restore test là bắt buộc

Một backup file tồn tại không chứng minh backup có thể phục hồi. Hãy diễn tập:

1. Dùng môi trường tách biệt.
2. Khôi phục database backup.
3. Khôi phục đúng keystore/password.
4. Mở keystore.
5. Recover database.
6. Truy vấn bảng/cột đã mã hóa.
7. Xác nhận ứng dụng đọc được dữ liệu.
8. Ghi thời gian phục hồi và các bước thủ công.

Không thực hiện diễn tập phá hủy trên production.

## 15. Export/import encryption keys

Trong một số tình huống migration, clone, PDB move hoặc khôi phục giữa môi trường, cần export/import encryption keys theo quy trình Oracle.

Ví dụ khung export:

~~~sql
ADMINISTER KEY MANAGEMENT EXPORT ENCRYPTION KEYS
    WITH SECRET "TransferSecret"
    TO '/secure/transfer/tde_keys.exp'
    IDENTIFIED BY "StrongKeystorePassword";
~~~

Ví dụ khung import:

~~~sql
ADMINISTER KEY MANAGEMENT IMPORT ENCRYPTION KEYS
    WITH SECRET "TransferSecret"
    FROM '/secure/transfer/tde_keys.exp'
    IDENTIFIED BY "StrongKeystorePassword"
    WITH BACKUP;
~~~

Đây là ví dụ minh họa cú pháp thường gặp. Tùy release, container và keystore mode, có thể cần chỉ định thêm phạm vi hoặc điều kiện khác. Hãy kiểm tra Oracle SQL Language Reference cho đúng phiên bản trước khi thực hiện.

### 15.1 Export file là tài liệu nhạy cảm

File export key không phải file cấu hình bình thường. Cần:

- Bảo vệ TransferSecret riêng biệt.
- Giới hạn quyền đọc file.
- Dùng kênh chuyển an toàn.
- Kiểm tra checksum.
- Xóa bản tạm theo retention policy.
- Không commit vào Git.
- Ghi nhận nguồn, đích và người thực hiện.

### 15.2 Import không thay thế backup

Sau khi import, cần backup keystore đích và kiểm tra key metadata. Không xóa file export hoặc keystore nguồn trước khi migration được xác nhận và có bản backup phục hồi.

## 16. Multitenant: CDB, PDB và keystore mode

Trong Oracle Multitenant, CDB chứa root container và các pluggable database (PDB). TDE keystore có thể được quản lý theo chế độ:

- UNITED: các PDB dùng keystore chung do CDB quản lý.
- ISOLATED: PDB có keystore riêng theo cấu hình được hỗ trợ.

Giá trị thực tế có thể xem trong V$ENCRYPTION_WALLET.KEYSTORE_MODE ở phiên bản có cột này.

### 16.1 United mode

Trong united mode, root quản lý keystore chung cho các PDB. Việc mở keystore và set key có thể áp dụng theo container scope.

Ví dụ thao tác trong CDB:

~~~sql
ADMINISTER KEY MANAGEMENT SET KEYSTORE OPEN
    IDENTIFIED BY "StrongKeystorePassword"
    CONTAINER = ALL;
~~~

Phạm vi CONTAINER=ALL cần được dùng có chủ đích. Trong một số tình huống, chỉ thao tác CONTAINER=CURRENT là phù hợp. Kết nối đúng container trước khi thực hiện.

### 16.2 Isolated mode

Trong isolated mode, PDB có keystore riêng. Điều này giúp tách biệt quản trị khóa giữa các PDB, nhưng tăng trách nhiệm:

- Mỗi PDB phải có keystore và master key phù hợp.
- Backup/restore phải gắn đúng PDB và key material.
- PDB unplug/plug cần xử lý keystore theo quy trình.
- DBA phải theo dõi trạng thái wallet của từng container.

### 16.3 Kiểm tra trạng thái theo container

~~~sql
SELECT con_id,
       status,
       wallet_type,
       keystore_mode,
       fully_backed_up,
       wrl_parameter
FROM v$encryption_wallet
ORDER BY con_id;
~~~

Không kết luận TDE đã sẵn sàng cho mọi PDB chỉ vì wallet của CDB$ROOT đang OPEN.

### 16.4 PDB unplug/plug và clone

Khi di chuyển hoặc clone PDB có encrypted data, phải bảo đảm đích có các master key cần thiết. Với isolated keystore, cần export/import hoặc chuyển keystore theo đúng quy trình. Với united mode, phải xác nhận key của PDB có sẵn trong keystore chung và phạm vi container tương thích.

Không chỉ copy datafile của PDB rồi giả định có thể mở ở database đích.

## 17. RAC và Data Guard

### 17.1 Oracle RAC

Các instance trong RAC cần truy cập cùng key material tương ứng với database. Keystore path và artifact phải được triển khai đồng bộ trên các node theo kiến trúc lưu trữ được chọn.

Kiểm tra:

- Mỗi instance thấy đúng keystore.
- Wallet status trên từng instance.
- Auto-login file hoạt động theo host policy.
- Sau rotation, key mới đã được chia sẻ/đồng bộ.
- Restart từng instance không làm mất khả năng mở wallet.

### 17.2 Data Guard standby

Standby cần key material tương ứng để đọc/áp dụng dữ liệu được mã hóa. Sau khi tạo hoặc rotate master key trên primary, phải đồng bộ keystore tới standby theo quy trình được hỗ trợ và kiểm tra trạng thái.

Nếu standby không có key mới:

- Redo apply hoặc thao tác truy cập dữ liệu mã hóa có thể gặp lỗi.
- Switchover/failover có thể không hoạt động như mong muốn.
- Khôi phục backup ở standby có thể thất bại.

### 17.3 Runbook sau rotation

Một checklist đồng bộ:

1. Rotate key trên primary theo cửa sổ đã duyệt.
2. Backup keystore mới.
3. Chuyển keystore/key material qua kênh bảo mật.
4. Cập nhật tất cả standby và RAC nodes liên quan.
5. Mở keystore ở các môi trường cần thiết.
6. Kiểm tra V$ENCRYPTION_WALLET và key metadata.
7. Xác nhận redo apply và query test.
8. Cập nhật inventory/backup manifest.

Không thực hiện switchover/failover nếu chưa xác nhận key readiness ở đích.

## 18. TDE và RMAN backup

TDE và RMAN backup encryption là hai khái niệm liên quan nhưng không đồng nhất.

### 18.1 TDE bảo vệ dữ liệu database at-rest

TDE column/tablespace encryption mã hóa dữ liệu trong database storage. Với tablespace encryption, dữ liệu trong encrypted tablespace được lưu mã hóa trên disk.

### 18.2 RMAN backup encryption là cấu hình riêng

RMAN có các chế độ backup encryption riêng, chẳng hạn transparent, password hoặc dual mode theo phiên bản. RMAN backup encryption có thể mã hóa backup set theo cấu hình và key/secret tương ứng.

Không suy luận rằng mọi loại backup, export hoặc copy file đều tự động được bảo vệ chỉ vì database có TDE.

### 18.3 Backup datafile và backup set

Tính chất mã hóa của backup phụ thuộc:

- Loại TDE (column/tablespace).
- Loại backup (image copy hay backup set).
- RMAN encryption configuration.
- Phiên bản và tùy chọn.
- Cách dữ liệu được xử lý trong backup pipeline.

Hãy kiểm tra tài liệu RMAN/TDE cho release đang dùng và kiểm thử bằng restore. Với dữ liệu nhạy cảm, có thể cần thêm RMAN backup encryption hoặc storage-level encryption theo chính sách.

### 18.4 Backup keystore riêng

Dù RMAN backup đã được mã hóa, keystore vẫn là thành phần cần quản lý riêng. Nếu backup được mã hóa bằng TDE master key hoặc RMAN transparent mode dựa vào wallet, cần key/keystore phù hợp để restore.

## 19. TDE không thay thế mã hóa network

TDE bảo vệ dữ liệu khi lưu trên storage. Khi client kết nối tới database, dữ liệu trả về qua network cần cơ chế bảo vệ riêng.

Các hướng có thể dùng:

- TLS với Oracle Net.
- Oracle Native Network Encryption nếu được cấu hình và hỗ trợ.
- VPN hoặc private network như lớp bổ sung.

Không coi TDE là giải pháp mã hóa toàn bộ đường truyền. Cần cấu hình và kiểm thử TLS/network encryption độc lập.

## 20. TDE và Data Pump/export

Data Pump export tạo dump file chứa dữ liệu logic. Dữ liệu trong dump có thể ở dạng đã giải mã theo cách export xử lý, do đó không được giả định dump file luôn được mã hóa chỉ vì bảng nguồn nằm trong encrypted tablespace.

Khi xuất dữ liệu nhạy cảm:

- Xác định dump file được ghi ở đâu.
- Bảo vệ DIRECTORY object và OS permissions.
- Dùng tùy chọn mã hóa Data Pump phù hợp nếu có quyền và license.
- Bảo vệ encryption password.
- Mã hóa storage/transport.
- Đặt retention và xóa file tạm an toàn.

Kiểm tra điều kiện tính năng Data Pump encryption và licensing theo phiên bản/edition. Không dùng quyền truy cập Data Pump để bỏ qua chính sách phân loại dữ liệu.

## 21. TDE và dữ liệu tạm, redo, undo, LOB

TDE column encryption và tablespace encryption có phạm vi khác nhau. Cần xem dữ liệu được ghi vào segment nào:

- Table segment.
- Index segment.
- LOB segment.
- Undo.
- Temporary tablespace.
- Redo/archive log.
- Export/dump.

Encrypted tablespace bảo vệ các segment trong tablespace đó theo cơ chế TDE tablespace. Nhưng dữ liệu được sao chép sang tablespace khác, dump file hoặc log bên ngoài phải được đánh giá riêng.

Không giả định mọi bản sao dữ liệu phát sinh trong hệ thống tự động được mã hóa giống nhau. Xây dựng data flow inventory và kiểm thử từng đường đi.

## 22. Giám sát trạng thái TDE

### 22.1 Keystore status

~~~sql
SELECT con_id,
       status,
       wallet_type,
       keystore_mode,
       fully_backed_up,
       wrl_type,
       wrl_parameter
FROM v$encryption_wallet;
~~~

### 22.2 Các key đang được database biết

~~~sql
SELECT con_id,
       key_id,
       tag,
       creation_time,
       activation_time
FROM v$encryption_keys
ORDER BY con_id, activation_time DESC;
~~~

### 22.3 Column encryption metadata

~~~sql
SELECT owner,
       table_name,
       column_name,
       encryption_alg,
       salt
FROM dba_encrypted_columns
ORDER BY owner, table_name, column_name;
~~~

### 22.4 Tablespace encryption metadata

~~~sql
SELECT tablespace_name,
       encrypted
FROM dba_tablespaces
ORDER BY tablespace_name;
~~~

Tùy phiên bản, có thể dùng thêm V$ENCRYPTED_TABLESPACES để xem trạng thái mã hóa và thuật toán. Kiểm tra dictionary view có sẵn trong release.

### 22.5 Các kiểm tra vận hành

- Keystore có OPEN ở container cần thiết?
- Master key đã active?
- FULLY_BACKED_UP có phản ánh trạng thái backup mong muốn?
- Backup keystore đã được sao chép off-host?
- Các standby/RAC nodes đã có key version mới?
- Auto-login wallet có quyền filesystem đúng?
- Có cảnh báo keystore closed hoặc key unavailable?

FULLY_BACKED_UP là metadata hữu ích nhưng không chứng minh bản backup off-host có thể restore. Phải kiểm thử recovery thực tế.

## 23. Điều kiện tính năng và giấy phép

TDE là tính năng có điều kiện về edition, version, platform và license. Với triển khai Oracle Database on-premises, TDE thường thuộc Oracle Advanced Security Option (ASO). Không được suy luận rằng có thể chạy lệnh TDE hoặc view báo trạng thái TDE nghĩa là tổ chức đã có quyền license.

### 23.1 Những gì cần xác nhận

Trước khi bật TDE, DBA/license owner cần xác nhận:

1. Oracle Database version và release update.
2. Edition và deployment type.
3. Nền tảng (on-premises, engineered system, cloud service).
4. Advanced Security Option có nằm trong hợp đồng/quyền sử dụng không.
5. Tính năng TDE cụ thể được phép dùng trong môi trường đó.
6. Các điều kiện bổ sung của cloud service hoặc license metric.
7. Quyền sử dụng cho môi trường DR, test, development và standby.

### 23.2 On-premises

Trong nhiều mô hình Oracle Database Enterprise Edition on-premises, TDE là thành phần của Advanced Security Option. Việc có Enterprise Edition không tự động chứng minh ASO đã được license.

Kiểm tra tài liệu Oracle Licensing Information cho đúng phiên bản và hợp đồng của tổ chức. Điều khoản có thể thay đổi theo release và chương trình license.

### 23.3 Cloud service

Một số Oracle Cloud Database services có thể bao gồm quyền sử dụng các tính năng bảo mật trong dịch vụ hoặc có điều kiện thương mại riêng. Không áp dụng máy móc kết luận licensing on-premises cho dịch vụ cloud.

Đọc service description, order document và điều khoản cloud cụ thể. Không giả định mọi dịch vụ Oracle Cloud có quyền giống nhau.

### 23.4 Edition và tính khả dụng kỹ thuật

Một số tính năng có thể:

- Không khả dụng trong edition nhất định.
- Có giới hạn theo platform.
- Cần cấu hình bổ sung.
- Thay đổi giữa các release.

Hãy xác nhận feature support bằng tài liệu phiên bản. Tránh dựa vào một blog cũ hoặc câu lệnh chạy thành công trên môi trường khác.

### 23.5 View và tham số không xác nhận license

Các cách sau không phải bằng chứng đủ để kết luận đã được license:

- Query V$OPTION và thấy một option TRUE.
- Thấy V$ENCRYPTION_WALLET.
- Tạo được keystore.
- SQL ADMINISTER KEY MANAGEMENT chạy thành công.
- Tính năng có trong binary/edition.

Khả năng kỹ thuật và quyền sử dụng theo hợp đồng là hai vấn đề khác nhau. License owner/Oracle account team cần xác nhận điều kiện áp dụng.

## 24. Phân biệt TDE với các tính năng bảo mật khác

| Tính năng | Mục tiêu chính | Có thay thế TDE không? |
|---|---|---|
| TDE | Mã hóa dữ liệu database at-rest | Là lớp mã hóa at-rest |
| TLS/Oracle Net encryption | Bảo vệ dữ liệu trên đường truyền | Không |
| RMAN backup encryption | Mã hóa backup set theo cấu hình RMAN | Không; bổ sung |
| Storage encryption | Mã hóa block/device ở tầng storage | Không hoàn toàn; khác lớp quản lý |
| Data Redaction | Che dữ liệu khi truy vấn theo policy | Không |
| Data Masking | Thay dữ liệu nhạy cảm trong môi trường non-production | Không |
| VPD/Row-Level Security | Giới hạn hàng người dùng được xem | Không |
| Database Vault | Kiểm soát quyền truy cập đặc quyền theo policy | Không |
| Auditing | Ghi nhận hoạt động | Không |

Một kiến trúc bảo mật tốt có thể dùng nhiều lớp. TDE bảo vệ data at-rest nhưng vẫn cần authorization, auditing, network encryption, backup security và quản lý secret.

## 25. Hiệu năng và vận hành

TDE có thể tạo overhead CPU và ảnh hưởng I/O tùy loại encryption, phần cứng, workload và khả năng tăng tốc mã hóa.

Trước khi triển khai rộng:

- Benchmark OLTP read/write.
- Benchmark batch và analytic workload.
- Đo CPU, latency và throughput.
- Đo thời gian backup/restore.
- Kiểm tra index/query trên encrypted columns.
- Đo tác động khi database không có hardware crypto acceleration.
- Kiểm tra các workload LOB và TEMP.

Không dùng kết quả benchmark trên một bảng nhỏ để kết luận cho toàn bộ database.

### 25.1 Tablespace migration

Chuyển tablespace hiện hữu sang encryption có thể cần thao tác online/offline tùy phiên bản và loại chuyển đổi. Một số release hỗ trợ cú pháp ALTER TABLESPACE ENCRYPTION ONLINE; release khác có giới hạn khác.

Không chạy lệnh migration trên production trước khi:

- Xác nhận syntax và tính năng đúng release.
- Đo dung lượng datafile và TEMP.
- Có backup/recovery point.
- Xác định thời gian và locking.
- Kiểm tra standby và replication.
- Có rollback/recovery plan.

### 25.2 Column encryption migration

Thêm hoặc chuyển cột sang ENCRYPT có thể yêu cầu rewrite/DDL operation và ảnh hưởng index/constraint. Kiểm tra table size, datatype, SALT, dependent objects và ứng dụng trước khi thay đổi.

## 26. Kế hoạch xử lý sự cố keystore

### 26.1 Wallet CLOSED

Triệu chứng có thể gồm lỗi khi truy cập encrypted data hoặc khi thao tác yêu cầu master key.

Điều tra:

1. Kiểm tra V$ENCRYPTION_WALLET.
2. Xác định đúng container và instance.
3. Xác nhận đường dẫn keystore.
4. Xác nhận password/auto-login file.
5. Mở keystore theo quy trình được phê duyệt.
6. Thử query dữ liệu mã hóa.

Không tạo master key mới chỉ để xử lý wallet CLOSED.

### 26.2 OPEN_NO_MASTER_KEY

Keystore có thể đang mở nhưng chưa có master key được kích hoạt cho container hoặc database context hiện tại.

Kiểm tra:

- Có set key trước đó chưa?
- Đang ở CDB root hay PDB?
- Có đang dùng united/isolated mode đúng không?
- Keystore có phải bản đúng của database?
- Key có được import đầy đủ không?

Không tạo key mới tùy tiện nếu database đã có dữ liệu mã hóa bằng key cũ.

### 26.3 Keystore path sai hoặc file không đọc được

Kiểm tra:

- WALLET_ROOT.
- TDE_CONFIGURATION.
- WRL_PARAMETER.
- OS permissions/ownership.
- Mount point/network filesystem.
- File ewallet.p12/cwallet.sso có tồn tại và không bị hỏng.

Không chmod 777 wallet directory. Cấp quyền tối thiểu cho Oracle software owner và nhóm vận hành phù hợp.

### 26.4 Master key không có ở standby

Kiểm tra key ID/version ở primary và standby, backup keystore mới nhất và quá trình đồng bộ. Không chỉ copy một file tùy tiện nếu có nhiều keystore/PDB hoặc nhiều key version.

## 27. Quy trình triển khai TDE có kiểm soát

Một quy trình production:

1. Phân loại dữ liệu và xác định threat model.
2. Chọn column encryption hay tablespace encryption.
3. Xác nhận version, edition, platform và license.
4. Thiết kế WALLET_ROOT/TDE_CONFIGURATION.
5. Chọn password keystore, auto-login hoặc isolated keystore theo yêu cầu.
6. Tạo keystore và mở đúng container.
7. Tạo master key và backup ngay.
8. Tạo encrypted tablespace hoặc mã hóa cột.
9. Kiểm tra metadata và query thực tế.
10. Đồng bộ keystore tới RAC/standby/PDB liên quan.
11. Kiểm thử restart, backup/restore và disaster recovery.
12. Đưa backup key ra off-host và lưu secret riêng.
13. Theo dõi wallet status, key lifecycle và backup status.
14. Ghi runbook rotation/recovery và phân quyền.

## 28. Ví dụ runbook: tạo TDE tablespace mới

Các bước sau là ví dụ trong môi trường lab, không phải script chạy nguyên xi cho mọi database.

### Bước 1: Xác nhận cấu hình

~~~sql
SHOW PARAMETER wallet_root
SHOW PARAMETER tde_configuration
~~~

### Bước 2: Tạo keystore nếu chưa có

~~~sql
ADMINISTER KEY MANAGEMENT CREATE KEYSTORE
    '/u01/app/oracle/admin/ORCL/wallet/tde'
    IDENTIFIED BY "StrongKeystorePassword";
~~~

### Bước 3: Mở keystore

~~~sql
ADMINISTER KEY MANAGEMENT SET KEYSTORE OPEN
    IDENTIFIED BY "StrongKeystorePassword";
~~~

### Bước 4: Set master key và backup

~~~sql
ADMINISTER KEY MANAGEMENT SET KEY
    IDENTIFIED BY "StrongKeystorePassword"
    WITH BACKUP USING 'initial_key';
~~~

### Bước 5: Kiểm tra wallet/key

~~~sql
SELECT status, wallet_type, fully_backed_up
FROM v$encryption_wallet;

SELECT key_id, tag, activation_time
FROM v$encryption_keys
ORDER BY activation_time DESC;
~~~

### Bước 6: Tạo encrypted tablespace

~~~sql
CREATE TABLESPACE secure_ts
DATAFILE '/u02/oradata/ORCL/secure_ts01.dbf'
SIZE 500M
ENCRYPTION USING 'AES256'
DEFAULT STORAGE (ENCRYPT);
~~~

### Bước 7: Tạo table và kiểm tra

~~~sql
CREATE TABLE secure_ts_test (
    id NUMBER PRIMARY KEY,
    secret_value VARCHAR2(100)
)
TABLESPACE secure_ts;

INSERT INTO secure_ts_test VALUES (1, 'sample');
COMMIT;

SELECT * FROM secure_ts_test;
~~~

### Bước 8: Backup keystore off-host

DBA tạo backup theo package, xác định file được tạo, sao chép qua kênh an toàn và kiểm tra checksum. Lưu password trong secret manager riêng.

### Bước 9: Restore rehearsal

Khôi phục database và keystore vào môi trường lab, mở wallet, query SECURE_TS_TEST và ghi nhận kết quả.

## 29. Bài thực hành tự kiểm tra

Các bài tập chỉ chạy trên database lab hoặc môi trường đã được DBA phê duyệt.

### Bài 1 — Xem wallet status

Query V$ENCRYPTION_WALLET. Ghi WRL_PARAMETER, STATUS, WALLET_TYPE, KEYSTORE_MODE và FULLY_BACKED_UP.

### Bài 2 — Tạo password keystore

Trong database lab, tạo software keystore bằng ADMINISTER KEY MANAGEMENT. Xác nhận file được tạo và quyền filesystem.

### Bài 3 — Set master key

Mở keystore, tạo master key với WITH BACKUP. Xem V$ENCRYPTION_KEYS và ghi key ID/tag.

### Bài 4 — Auto-login wallet

Tạo auto-login keystore trong lab. Restart instance theo runbook và xác nhận wallet status. Sau đó kiểm tra quy trình mở password wallet độc lập.

### Bài 5 — Column encryption

Tạo table có một cột ENCRYPT. Thêm dữ liệu thử, query metadata DBA_ENCRYPTED_COLUMNS và kiểm tra SQL access.

### Bài 6 — SALT và NO SALT

Tạo hai bảng thử nghiệm với column encryption có SALT và NO SALT. Kiểm tra index/query support theo release và ghi nhận trade-off.

### Bài 7 — Tablespace encryption

Tạo encrypted tablespace AES256, tạo table và kiểm tra DBA_TABLESPACES/V$ENCRYPTED_TABLESPACES.

### Bài 8 — Key rotation

Trong lab, tạo key version mới với WITH BACKUP. Kiểm tra key metadata và xác nhận dữ liệu cũ vẫn đọc được.

### Bài 9 — Backup keystore

Backup keystore, sao chép ra nơi lưu trữ an toàn và kiểm tra checksum. Không lưu secret trong cùng thư mục.

### Bài 10 — Restore test

Khôi phục bản database lab cùng keystore vào host/instance tách biệt. Xác nhận query encrypted table hoạt động.

### Bài 11 — Multitenant

Kiểm tra KEYSTORE_MODE trong CDB/PDB. So sánh UNITED và ISOLATED theo tài liệu phiên bản, không thay đổi mode trên môi trường thật.

### Bài 12 — Licensing review

Lập bảng version, edition, deployment type, TDE feature, Advanced Security entitlement và người phê duyệt. Đối chiếu order document/licensing manual trước khi bật TDE production.

## 30. Checklist production

**Thiết kế**

- Dữ liệu và threat model đã được xác định?
- Chọn column hay tablespace encryption có lý do?
- Đã xác định LOB, index, TEMP, undo, redo, export và backup nằm ở đâu?
- Algorithm phù hợp policy và version?

**Keystore**

- WALLET_ROOT/TDE_CONFIGURATION đúng?
- Password keystore được lưu trong secret manager?
- Auto-login có thực sự cần?
- Filesystem permissions đủ chặt?
- CDB/PDB keystore mode đã xác định?

**Khóa**

- Master key đã active?
- Key ID/version được inventory?
- Rotation có backup?
- Key cũ được giữ theo retention?
- Standby/RAC/PDB có đủ key?

**Backup/restore**

- Backup keystore sau mỗi lần thay đổi?
- Có bản off-host/offline?
- Password được lưu riêng?
- Backup database và key backup được liên kết theo thời gian?
- Đã diễn tập restore database + keystore?

**Licensing**

- Version/edition/platform đã xác nhận?
- Advanced Security Option hoặc entitlement cloud đã được license owner xác nhận?
- Tính năng cụ thể có trong quyền sử dụng?
- DR/test/dev có điều kiện riêng?
- Không dùng V$OPTION hay khả năng chạy lệnh làm bằng chứng license?

**Vận hành**

- Có giám sát wallet status?
- Có cảnh báo wallet CLOSED/key unavailable?
- Có runbook sau restart?
- Có runbook rotation/recovery?
- Có kiểm tra Data Guard/RAC sau rotation?
- Trace/log/export có bảo vệ dữ liệu nhạy cảm?

## 31. Ghi nhớ

| Khái niệm | Điều cần nhớ |
|---|---|
| TDE | Mã hóa dữ liệu database at-rest |
| Column encryption | Mã hóa các cột được chọn |
| Tablespace encryption | Mã hóa dữ liệu trong tablespace |
| Master key | Khóa chính được quản lý trong keystore |
| Data encryption key | Khóa bảo vệ dữ liệu thực tế |
| Keystore/wallet | Nơi lưu TDE master key và metadata |
| ewallet.p12 | Password-protected keystore thường gặp |
| cwallet.sso | Auto-login keystore thường gặp |
| WALLET_ROOT | Thư mục gốc wallet theo cấu hình hiện đại |
| TDE_CONFIGURATION | Cấu hình loại keystore |
| V$ENCRYPTION_WALLET | Trạng thái và vị trí keystore |
| V$ENCRYPTION_KEYS | Metadata các master key |
| WITH BACKUP | Yêu cầu backup keystore khi thay đổi key trong lệnh phù hợp |
| Key rotation | Kích hoạt master key version mới; giữ key cũ theo retention |
| UNITED | PDB dùng keystore chung do CDB quản lý |
| ISOLATED | PDB có keystore riêng theo cấu hình |
| RMAN encryption | Cơ chế mã hóa backup riêng, cần đánh giá cùng TDE |
| Network encryption | Bảo vệ dữ liệu trên đường truyền, độc lập với TDE |
| Advanced Security Option | Gói license thường gắn với TDE on-premises |
| License entitlement | Phải xác nhận theo version, edition, platform và hợp đồng |

TDE chỉ bảo vệ dữ liệu lưu trữ khi keystore và master key được quản lý đúng. Hãy chọn phạm vi mã hóa phù hợp, giữ password-protected keystore và backup khóa an toàn, đồng bộ key tới standby/RAC/PDB, đồng thời kiểm thử restore thực tế. Tách biệt TDE với RMAN backup encryption và network encryption. Cuối cùng, xác nhận edition, deployment và quyền Advanced Security hoặc entitlement cloud với license owner trước khi bật tính năng; việc database hỗ trợ lệnh không tự chứng minh tổ chức có quyền sử dụng.
