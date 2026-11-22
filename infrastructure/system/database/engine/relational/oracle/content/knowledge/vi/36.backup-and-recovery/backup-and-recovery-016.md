# Sao lưu khóa mã hóa, lưu bản sao ngoài máy chủ và chứng minh khả năng khôi phục

Một chiến lược backup chỉ có giá trị khi tổ chức có thể khôi phục database trong tình huống cần thiết. Với Oracle Database sử dụng Transparent Data Encryption (TDE), việc có đủ datafile, control file và archived redo log vẫn chưa đủ: DBA còn phải bảo vệ keystore chứa các khóa mã hóa cần để đọc dữ liệu. Nếu database backup được lưu an toàn nhưng keystore hoặc mật khẩu mở keystore bị mất, dữ liệu đã mã hóa có thể không khôi phục được.

Vì vậy, quy trình sao lưu và phục hồi cần quản lý đồng thời ba nhóm tài sản: **backup database**, **khóa và thông tin xác thực mã hóa**, và **bằng chứng diễn tập khôi phục**. Bản sao cần được đưa ra khỏi máy chủ hoặc failure domain nguồn; quyền truy cập và credential phải được tách biệt; cuối cùng, tổ chức phải thường xuyên khôi phục thử trên môi trường cô lập để chứng minh bản sao dùng được.

## 1. Bức tranh tổng thể của khả năng khôi phục

### 1.1. Một bản backup đầy đủ cần những gì?

Để phục hồi database đến một thời điểm xác định, DBA thường cần kết hợp:

- **Datafile backup:** bản sao các datafile chứa dữ liệu và metadata của database.
- **Control file:** chứa thông tin cấu trúc database và metadata cần thiết cho hoạt động RMAN, gồm thông tin về datafile, redo log và backup.
- **SPFILE hoặc PFILE:** chứa tham số khởi tạo instance, chẳng hạn memory, control file, audit, archive và vị trí keystore.
- **Archived redo log:** cho phép áp dụng các thay đổi sau thời điểm backup và hỗ trợ point-in-time recovery.
- **RMAN repository/catalog:** lưu metadata về backup. Metadata có thể nằm trong control file hoặc recovery catalog riêng.
- **TDE keystore và lịch sử khóa:** cho phép Oracle giải mã các tablespace, cột hoặc backup được mã hóa.
- **Thông tin hạ tầng và vận hành:** Oracle Home, phiên bản/patch, cấu hình mạng, password, secret, cấu hình media manager và quy trình mở keystore.

Không phải mọi tình huống đều cần khôi phục tất cả các thành phần theo cùng một cách. Tuy nhiên, khi thiết kế kế hoạch, cần liệt kê chúng và chỉ rõ nơi lưu, người sở hữu, cách khôi phục và cách xác minh.

### 1.2. Vì sao phải lưu khóa mã hóa cùng chiến lược backup?

TDE mã hóa dữ liệu khi lưu trữ. Database giữ các khóa mã hóa dữ liệu (table key hoặc column key tùy tính năng) được bảo vệ bởi TDE master encryption key trong keystore. Khi đọc dữ liệu, Oracle cần truy cập đúng khóa để giải mã.

Điều này tạo ra quan hệ phụ thuộc:

```text
Database backup / encrypted backup piece
                 |
                 v
       TDE master encryption key
                 |
                 v
          TDE keystore
                 |
                 v
       Keystore password / custody
```

Nếu backup database còn nguyên nhưng keystore bị mất, hỏng hoặc không mở được, quá trình phục hồi dữ liệu mã hóa có thể thất bại. Nếu chỉ giữ khóa hiện tại mà bỏ mất các khóa cũ, bản backup được tạo trước một lần rotate key cũng có thể không giải mã được.

Do đó, cần sao lưu keystore sau khi tạo hoặc thay đổi khóa, giữ lại lịch sử khóa cần thiết và kiểm tra việc mở keystore trong diễn tập phục hồi.

## 2. Hiểu TDE keystore và vòng đời khóa

### 2.1. Các thành phần chính

| Thành phần | Vai trò |
|---|---|
| TDE master encryption key | Khóa gốc dùng để bảo vệ các khóa mã hóa dữ liệu. |
| Tablespace encryption key | Khóa dùng để mã hóa dữ liệu trong tablespace được mã hóa. |
| Column encryption key | Khóa dùng cho cột được mã hóa bằng TDE column encryption. |
| Keystore / wallet | Nơi lưu master key và thông tin cần thiết để Oracle sử dụng khóa. |
| Keystore password | Bí mật dùng để mở hoặc quản lý password-based keystore. |
| Auto-login keystore | Cho phép Oracle mở keystore tự động trong cấu hình tương ứng; không thay thế bản sao password-based keystore an toàn. |

TDE có thể được cấu hình bằng software keystore, external keystore hoặc key management service tùy phiên bản và kiến trúc. Quy trình backup/restore cần phù hợp loại keystore thực tế. Với external key manager, ngoài database backup còn phải có kế hoạch khôi phục dịch vụ quản lý khóa, danh tính máy chủ, chứng thư, kết nối và quyền truy cập key manager.

### 2.2. Các file thường gặp của software keystore

Trong cấu hình software keystore, hai file thường được nhắc đến là:

- `ewallet.p12`: password-based keystore, được bảo vệ bằng mật khẩu.
- `cwallet.sso`: auto-login keystore, cho phép mở tự động theo cấu hình.

Đường dẫn thực tế phụ thuộc cấu hình `WALLET_ROOT`, `TDE_CONFIGURATION`, tham số wallet cũ hoặc vị trí được cấu hình trong `sqlnet.ora`. Không nên mặc định mọi hệ thống đều đặt wallet ở cùng một thư mục.

`ewallet.p12` là bản cần bảo vệ và sao lưu có kiểm soát. `cwallet.sso` thuận tiện cho khởi động tự động nhưng không nên là bản duy nhất được lưu giữ. Với local auto-login keystore, file có thể gắn với máy chủ đã tạo; bản sao đó có thể không dùng được khi chuyển sang host khác. Khi thiết kế disaster recovery, phải bảo đảm có password-based keystore, mật khẩu và hướng dẫn mở trên máy phục hồi.

### 2.3. Xác định trạng thái keystore

Trên database hỗ trợ TDE, có thể kiểm tra:

```sql
SELECT
    wrl_type,
    wrl_parameter,
    status,
    wallet_type,
    wallet_order,
    keystore_mode
FROM v$encryption_wallet;
```

Các cột cho biết loại keystore, vị trí, trạng thái mở/đóng, loại wallet và chế độ keystore. Cột có sẵn có thể khác theo phiên bản Oracle và cấu hình multitenant; hãy kiểm tra data dictionary của hệ thống đang vận hành.

Một số giá trị trạng thái thường gặp:

| STATUS | Ý nghĩa khái quát |
|---|---|
| `OPEN` | Keystore đang mở và có thể được sử dụng. |
| `CLOSED` | Keystore đã đóng. |
| `NOT_AVAILABLE` | Oracle không truy cập được keystore tại vị trí hoặc dịch vụ được cấu hình. |
| `OPEN_NO_MASTER_KEY` | Keystore mở nhưng container hoặc database chưa có master key phù hợp. |

Trong CDB/PDB, có thể có nhiều dòng hoặc trạng thái khác nhau theo container và keystore mode. Hãy xác định container hiện tại và phạm vi key store trước khi kết luận.

### 2.4. Theo dõi các khóa TDE

Có thể xem metadata khóa bằng view `V$ENCRYPTION_KEYS`:

```sql
SELECT
    key_id,
    tag,
    creation_time,
    activation_time,
    key_use,
    keystore_type,
    origin
FROM v$encryption_keys
ORDER BY creation_time;
```

View này cung cấp thông tin về các khóa được database ghi nhận. Khả năng đọc và một số cột phụ thuộc quyền và phiên bản. Không truy vấn hoặc ghi xuất material bí mật vào log; metadata khóa không thay thế cho bản sao keystore thực tế.

Khi rotate master key, Oracle tạo khóa mới và giữ thông tin các khóa cũ cần thiết để đọc dữ liệu đã mã hóa trước đó. Không xóa hoặc thay thế keystore bằng một bản cũ hơn chỉ vì file đó có vẻ hợp lệ. Bản cũ có thể không chứa master key được tạo sau thời điểm backup.

## 3. Sao lưu TDE keystore

### 3.1. Khi nào cần backup keystore?

Tạo bản sao keystore trước hoặc ngay sau những thay đổi quan trọng, theo quy trình quản trị khóa:

- Sau khi tạo TDE master key lần đầu.
- Sau khi rotate hoặc activate master key.
- Sau khi import hoặc migrate khóa.
- Sau khi thay đổi keystore password.
- Sau khi thay đổi kiến trúc wallet, chuyển host hoặc chuyển loại key manager.
- Theo lịch backup định kỳ đã được phê duyệt.

Một bản keystore backup phải tương ứng với thời điểm và trạng thái khóa có thể cần để phục hồi các database backup liên quan. Cần ghi nhận timestamp, database/PDB, loại keystore, key rotation và vị trí bản sao.

### 3.2. Backup password-based keystore bằng DBMS

Oracle cung cấp câu lệnh `ADMINISTER KEY MANAGEMENT BACKUP KEYSTORE` để tạo bản backup keystore. Ví dụ:

```sql
ADMINISTER KEY MANAGEMENT BACKUP KEYSTORE
    USING 'before_monthly_rotation'
    IDENTIFIED BY "<keystore_password>";
```

`USING` đặt nhãn cho bản backup; mật khẩu phải là mật khẩu keystore thực tế được cung cấp qua quy trình bí mật an toàn. Đây là placeholder, không phải mật khẩu có thể dùng. Cú pháp có thể có thêm tùy chọn như `FORCE KEYSTORE` hoặc `CONTAINER` tùy phiên bản và chế độ CDB/PDB. Hãy xác nhận bằng tài liệu đúng phiên bản và quyền quản trị trước khi thực thi.

Oracle tạo bản sao keystore trong vị trí wallet theo cơ chế của phiên bản. Sau lệnh, DBA cần xác định chính xác file được tạo, kiểm tra kích thước/thời điểm, rồi sao chép file đó vào vùng lưu trữ backup được bảo vệ. Không coi việc câu lệnh trả về thành công là bằng chứng bản sao off-host đã được tạo.

### 3.3. Backup trước và sau khi rotate key

Một quy trình thay đổi khóa có thể gồm:

1. Ghi nhận database, PDB, keystore mode, trạng thái wallet và các khóa hiện tại.
2. Tạo backup keystore và chuyển bản sao ra kho lưu trữ bảo mật.
3. Thực hiện thao tác rotate/activate key theo chính sách.
4. Xác nhận khóa mới được tạo và keystore vẫn mở đúng.
5. Tạo thêm backup keystore sau thay đổi.
6. Kiểm tra hai bản backup có thể truy cập, có metadata và được liên kết với thời điểm thay đổi.

Không xóa các bản keystore cũ theo lịch tùy tiện. Chúng có thể cần cho backup database được tạo trước lần rotate. Retention khóa phải bao phủ toàn bộ thời gian còn lưu giữ backup được mã hóa bằng những khóa đó.

### 3.4. Bảo vệ mật khẩu keystore

Mất file keystore là một vấn đề; mất mật khẩu mở keystore cũng có thể khiến file không dùng được. Mật khẩu cần được quản lý tách khỏi file backup:

- Lưu trong enterprise secret manager hoặc hệ thống quản lý bí mật được phê duyệt.
- Giới hạn người có quyền đọc, ghi và khôi phục secret.
- Bật audit cho thao tác truy cập secret và yêu cầu phê duyệt khi truy xuất khẩn cấp.
- Có cơ chế break-glass được kiểm soát để phục hồi khi người quản lý chính không sẵn sàng.
- Kiểm tra quy trình lấy secret trong diễn tập DR, không chỉ kiểm tra file tồn tại.
- Không ghi mật khẩu vào shell history, script, ticket, email hoặc log.

Không lưu mật khẩu keystore trong cùng thư mục hoặc cùng quyền truy cập với bản backup keystore. Tách biệt này giúp giảm rủi ro khi một tài khoản hoặc một vùng lưu trữ bị xâm phạm.

### 3.5. Auto-login wallet và khả năng phục hồi sang host khác

Auto-login wallet giúp database mở keystore tự động theo cấu hình. Tuy nhiên, file auto-login không thay thế password-based keystore và quy trình quản lý mật khẩu.

- Giữ bản backup password-based keystore có mật khẩu được quản lý an toàn.
- Nếu dùng local auto-login wallet, hiểu rằng file có thể được ràng buộc với host đã tạo và không sử dụng được khi chuyển sang máy DR.
- Khi cần tự động mở wallet trên host mới, tạo hoặc cấu hình auto-login wallet theo hướng dẫn Oracle sau khi đã khôi phục password-based keystore trên host đích.
- Không chia sẻ file `cwallet.sso` rộng rãi; auto-login có thể làm giảm bước xác thực tương tác và cần được bảo vệ như một credential.

## 4. Lưu bản sao ngoài máy chủ

### 4.1. Vì sao cần off-host backup?

Backup đặt trên cùng máy chủ hoặc cùng storage với database không bảo vệ được trước nhiều tình huống: lỗi thiết bị, ransomware, xóa nhầm, lỗi cấu hình, mất trung tâm dữ liệu hoặc tài khoản quản trị bị chiếm quyền. Off-host backup đưa bản sao sang một failure domain khác để database nguồn và backup không cùng chịu một sự cố.

Một bản sao được coi là off-host có thể nằm ở:

- Hệ thống backup chuyên dụng tại trung tâm dữ liệu khác.
- Object storage hoặc cloud backup account riêng.
- Media manager/SBT library có lưu trữ ngoài host.
- Storage replication sang site DR độc lập.
- Kho offline hoặc immutable theo chính sách tổ chức.

Một thư mục NFS gắn vào máy chủ database có thể nằm ngoài ổ đĩa local nhưng vẫn chưa chắc độc lập về failure domain. Hãy xác định storage, tài khoản quản trị, mạng, site và cơ chế xóa của nơi lưu trữ.

### 4.2. Nguyên tắc 3-2-1 và bản sao bất biến

Một cách thiết kế phổ biến là quy tắc 3-2-1:

- Có ít nhất ba bản sao dữ liệu tính cả bản production.
- Lưu trên ít nhất hai loại phương tiện hoặc hệ thống lưu trữ độc lập.
- Có ít nhất một bản sao off-site.

Với rủi ro ransomware hoặc tài khoản quản trị bị chiếm quyền, nên bổ sung bản sao immutable hoặc offline. Immutable backup ngăn thay đổi/xóa trong thời gian retention được cấu hình; quyền quản trị kho backup cần tách khỏi quyền DBA trên database nguồn.

3-2-1 là nguyên tắc thiết kế, không phải bằng chứng tự động rằng có thể phục hồi. Mỗi bản sao cần có checksum hoặc cơ chế kiểm tra toàn vẹn, metadata, thời gian lưu, quyền truy cập và quy trình restore đã được thử.

### 4.3. Những thành phần nên lưu ngoài máy chủ

| Thành phần | Mục đích |
|---|---|
| RMAN backup pieces | Khôi phục datafile và database. |
| Archived redo logs | Recovery đến thời điểm cần thiết. |
| Control file và SPFILE | Dựng lại cấu trúc và cấu hình instance. |
| Recovery catalog backup/export nếu có | Khôi phục metadata RMAN độc lập với control file nguồn. |
| TDE keystore backup | Giải mã dữ liệu và backup được mã hóa. |
| Keystore password và secret liên quan | Mở keystore và truy cập backup. Lưu trong hệ thống bí mật riêng. |
| Cấu hình RMAN/media manager | Kết nối lại kho backup và đọc backup piece. |
| Thông tin Oracle Home/patch và cấu hình DR | Dựng môi trường tương thích để restore. |
| Tài liệu vận hành | Trình tự phục hồi, người liên hệ, quyền và tiêu chí xác nhận. |

Không nhất thiết mọi thành phần phải nằm trong cùng một kho. Keystore và mật khẩu nên có cơ chế bảo vệ riêng, đồng thời vẫn có quy trình truy cập khẩn cấp đủ nhanh để đáp ứng RTO.

### 4.4. Tách biệt quyền và thông tin xác thực

Thiết kế off-host backup cần tách biệt các quyền sau:

- DBA có thể tạo backup nhưng không có quyền xóa mọi bản sao immutable.
- Tài khoản backup service có thể ghi backup nhưng không được quyền đọc dữ liệu ứng dụng ngoài nhiệm vụ.
- Quản trị storage có thể quản lý dung lượng nhưng không tự động có quyền lấy keystore password.
- Người khôi phục có thể được cấp quyền đọc bản sao và lấy secret theo quy trình break-glass.
- Audit ghi nhận ai tạo, sao chép, xóa, khôi phục hoặc truy xuất secret.

Nếu database admin và backup admin dùng chung một tài khoản có quyền xóa bản sao, ransomware chiếm được tài khoản đó có thể phá cả production lẫn backup. Phân tách quyền làm giảm phạm vi ảnh hưởng của một credential bị lộ.

## 5. Sao lưu database bằng RMAN

### 5.1. Kiểm tra chế độ archive log

Point-in-time recovery thường dựa trên archived redo log. Kiểm tra chế độ archive:

```sql
ARCHIVE LOG LIST;
```

Hoặc truy vấn:

```sql
SELECT log_mode
FROM v$database;
```

Nếu database chạy `NOARCHIVELOG`, khả năng khôi phục thường bị giới hạn vào các bản backup nhất quán phù hợp và không có cùng khả năng phục hồi đến thời điểm tùy chọn như database ở `ARCHIVELOG`. Việc chuyển chế độ archive là thay đổi vận hành cần lập kế hoạch và thực hiện theo tài liệu Oracle.

### 5.2. Bật control file autobackup

Trong RMAN, có thể bật tự động backup control file và SPFILE:

```text
RMAN> CONFIGURE CONTROLFILE AUTOBACKUP ON;
```

Điều này giúp RMAN tạo autobackup control file sau các thao tác backup phù hợp. Nếu dùng SPFILE, autobackup control file có thể chứa SPFILE. Cần xác nhận cấu hình, format và vị trí autobackup để biết cách tìm chúng khi restore.

### 5.3. Backup database và archived redo log

Ví dụ một lệnh RMAN tạo backup database cùng archived redo log:

```text
RMAN> BACKUP DATABASE PLUS ARCHIVELOG;
```

Lệnh này là ví dụ cơ bản; chiến lược thực tế có thể bổ sung backup level 0/1, compression, encryption, tag, channel và retention phù hợp. Khi dùng media manager/SBT, cần cấu hình channel và credential của plugin theo tài liệu sản phẩm.

Nếu cần backup riêng control file hoặc SPFILE theo lịch rõ ràng:

```text
RMAN> BACKUP CURRENT CONTROLFILE;
RMAN> BACKUP SPFILE;
```

Nếu đã bật control file autobackup, cần hiểu các bản sao được tạo tự động và tránh tạo cấu hình trùng lặp không cần thiết. Quan trọng là bản backup và metadata có thể tìm được khi mất control file hiện tại.

### 5.4. Backup piece phải được chuyển ra failure domain khác

Tạo backup trong một thư mục local chưa hoàn thành yêu cầu off-host. Cần cấu hình RMAN ghi trực tiếp tới media manager/object storage hoặc có bước chuyển bản backup đã hoàn tất sang kho độc lập.

Ví dụ về luồng:

```text
Oracle Database
      |
      v
    RMAN
      |
      v
Backup piece / archived log
      |
      v
Backup gateway / media manager
      |
      v
Remote vault / object storage
      |
      v
Immutable retention + separate admin
```

Nếu dùng quy trình copy file sau khi RMAN hoàn tất, hãy kiểm tra lệnh RMAN đã đóng backup piece, tính toàn vẹn của bản sao, kích thước, checksum và quyền truy cập trước khi đánh dấu thành công. Không sao chép một backup piece đang được ghi dở rồi coi đó là bản backup hoàn chỉnh.

### 5.5. Mã hóa backup RMAN

RMAN hỗ trợ mã hóa backup set. Có thể dùng transparent encryption dựa trên TDE keystore, password encryption hoặc dual-mode tùy phiên bản và yêu cầu. Transparent mode thuận tiện khi keystore có sẵn; password mode có thể giúp khôi phục trong một số tình huống không có keystore nhưng tạo thêm một bí mật cần quản lý.

Với transparent encryption, khả năng restore phụ thuộc vào TDE keystore và các master key liên quan. Với password encryption, mất mật khẩu backup có thể khiến backup không đọc được. Vì vậy, phải lưu credential tương ứng trong secret manager và thử phục hồi bằng đúng cơ chế mã hóa đã dùng.

Ví dụ minh họa trong RMAN cho chế độ mã hóa bằng mật khẩu:

```text
RMAN> SET ENCRYPTION ON IDENTIFIED BY "<backup_password>" ONLY;
RMAN> BACKUP DATABASE PLUS ARCHIVELOG;
```

Placeholder `<backup_password>` phải được thay bằng bí mật được quản lý an toàn. Cú pháp và phạm vi của `SET ENCRYPTION` phụ thuộc phiên bản RMAN và cấu hình; không đưa mật khẩu thật vào script hoặc log. Nếu dùng transparent encryption, xác nhận keystore đã mở và có khóa phù hợp trước khi backup.

Không nhầm việc database dùng TDE với việc mọi backup piece đều được mã hóa theo cùng một cơ chế. Hãy kiểm tra cấu hình RMAN và loại tablespace, xác nhận chính sách mã hóa thực tế, sau đó thử restore trên môi trường độc lập.

## 6. Bảo vệ TDE khi database nằm trong CDB/PDB hoặc dùng external key manager

### 6.1. Unified và isolated keystore trong multitenant

Trong CDB, TDE có thể dùng united keystore hoặc isolated keystore tùy cấu hình và phiên bản. Với united mode, các PDB dùng chung keystore của CDB theo cơ chế Oracle. Với isolated mode, PDB có keystore riêng. Việc restore CDB hoặc một PDB có thể cần đúng tập keystore và master key của container liên quan.

Kiểm tra `KEYSTORE_MODE` và trạng thái wallet trong `V$ENCRYPTION_WALLET`. Khi lập kế hoạch, lập danh sách:

- CDB root keystore.
- PDB keystore nếu PDB dùng isolated mode.
- Các PDB đã được unplug/plug hoặc clone sang nơi khác.
- Key history và backup keystore tương ứng với thời điểm backup dữ liệu.

Không giả định chỉ cần một file wallet cho mọi PDB. Hãy thử restore đúng kiến trúc CDB/PDB và phiên bản sẽ dùng trong DR.

### 6.2. External keystore hoặc Key Management Service

Nếu TDE dùng Oracle Key Vault hoặc một key management service khác, file `ewallet.p12` có thể không phải nơi duy nhất hoặc nơi chính giữ khóa. Kế hoạch DR cần bao gồm:

- Backup và phục hồi dịch vụ key manager theo hướng dẫn nhà cung cấp.
- Bảo vệ metadata, key identifier và phiên bản khóa.
- Bảo đảm host DR có thể xác thực với key manager bằng credential hoặc certificate phù hợp.
- Mở firewall/network và cấu hình kết nối cần thiết.
- Xác nhận quyền truy cập khóa cũ còn hiệu lực.
- Diễn tập khôi phục khi site chính hoặc key manager chính không sẵn sàng.

Một bản database backup ở site DR không hữu ích nếu site đó không thể liên hệ key manager hoặc không thể lấy đúng key version. Vì vậy, dịch vụ quản lý khóa phải nằm trong cùng kế hoạch liên tục kinh doanh và có dependency được ghi nhận.

## 7. Chứng minh backup có thể khôi phục

### 7.1. Backup thành công không đồng nghĩa restore thành công

Một job backup có exit code thành công chỉ chứng minh công cụ đã hoàn thành thao tác theo điều kiện của nó. Nó chưa chứng minh:

- Backup piece còn đọc được sau khi chuyển ra off-host.
- Control file, SPFILE và archived log đủ để dựng database.
- TDE keystore và mật khẩu mở được trên host khác.
- Các master key cần thiết vẫn tồn tại.
- Database có thể recover đến thời điểm mong muốn.
- Ứng dụng có thể kết nối và đọc dữ liệu sau restore.
- Thời gian khôi phục đáp ứng RTO và dữ liệu mất nằm trong RPO.

Chỉ có thể chứng minh khả năng khôi phục bằng cách kiểm tra backup và thực hiện restore/recovery thực tế trong môi trường được kiểm soát.

### 7.2. Phân biệt các mức kiểm tra

| Mức kiểm tra | Ví dụ | Bằng chứng nhận được |
|---|---|---|
| Job status | RMAN job hoàn tất thành công. | Công việc backup đã chạy xong. |
| Backup metadata | `LIST BACKUP`, `CROSSCHECK BACKUP`. | RMAN nhận diện backup và trạng thái repository. |
| Physical validation | `RESTORE DATABASE VALIDATE` hoặc `VALIDATE BACKUPSET`. | Backup có thể được đọc/kiểm tra theo phạm vi lệnh. |
| Restore rehearsal | Restore datafile/database vào môi trường cô lập. | Chứng minh có thể dựng lại database từ bản sao. |
| Recovery rehearsal | Apply archived redo log đến thời điểm mục tiêu. | Chứng minh chuỗi backup và log đủ cho recovery mục tiêu. |
| Application validation | Mở database, kiểm tra object, dữ liệu và ứng dụng. | Chứng minh kết quả có thể sử dụng được. |

Các mức kiểm tra bổ sung cho nhau. `CROSSCHECK` chỉ đối chiếu trạng thái file theo repository và storage; nó không thay thế việc đọc và restore backup. `RESTORE ... VALIDATE` cũng không thay thế một buổi diễn tập recovery toàn diện.

### 7.3. Kiểm tra backup bằng RMAN

Một số lệnh kiểm tra thường dùng:

```text
RMAN> LIST BACKUP SUMMARY;
RMAN> CROSSCHECK BACKUP;
RMAN> RESTORE DATABASE PREVIEW;
RMAN> RESTORE DATABASE VALIDATE;
```

- `LIST BACKUP SUMMARY` liệt kê tổng quan các backup mà repository biết.
- `CROSSCHECK BACKUP` đối chiếu metadata với sự tồn tại của backup trên thiết bị lưu trữ.
- `RESTORE DATABASE PREVIEW` hiển thị các backup mà RMAN dự kiến dùng cho restore.
- `RESTORE DATABASE VALIDATE` kiểm tra khả năng đọc các backup cần thiết mà không ghi đè datafile đích.

Có thể kiểm tra tính hợp lệ của backup set cụ thể bằng `VALIDATE BACKUPSET`. Cú pháp và phạm vi lệnh phải được xác nhận theo phiên bản RMAN. Nếu backup nằm trong SBT/cloud, cần kiểm tra credential, channel và kết nối tới media manager trong môi trường test.

### 7.4. Diễn tập restore trong môi trường cô lập

Một buổi diễn tập có giá trị nên khôi phục vào máy chủ hoặc vùng DR riêng, không ghi đè database production. Môi trường thử nghiệm cần có:

- Oracle Home và patch tương thích.
- Storage đủ dung lượng cho datafile, redo, temp và recovery.
- Backup piece, control file/SPFILE và archived redo log lấy từ kho off-host.
- TDE keystore/password hoặc kết nối key manager.
- Network tách biệt để ứng dụng thử nghiệm không gửi giao dịch tới hệ thống production.
- Quyền truy cập và secret được cấp theo quy trình DR.

Một trình tự tổng quát:

1. Chọn một recovery point và xác định backup cùng archived log cần thiết.
2. Lấy backup, control file, SPFILE và keystore từ kho off-host.
3. Dựng instance đích với cấu hình phù hợp, `DB_UNIQUE_NAME` và đường dẫn riêng.
4. Khôi phục password-based keystore, mở keystore và xác nhận master key có thể truy cập.
5. Khôi phục control file và mount database theo quy trình RMAN.
6. Restore datafile và recover bằng archived redo log đến thời điểm mục tiêu.
7. Mở database theo loại recovery đã thực hiện; nếu incomplete recovery yêu cầu `OPEN RESETLOGS`, thực hiện đúng quy trình Oracle cho tình huống đó.
8. Kiểm tra trạng thái tablespace, datafile, object, invalid object và dữ liệu ứng dụng.
9. Ghi lại thời gian từng bước, lỗi phát sinh, lượng dữ liệu phục hồi và thời điểm dữ liệu cuối cùng.
10. Xóa hoặc cô lập môi trường diễn tập theo quy trình sau khi đã lưu bằng chứng.

Không chạy các lệnh restore/open trực tiếp trên production để thử nghiệm. Lệnh cụ thể phụ thuộc loại restore, trạng thái control file, CDB/PDB, backup encryption và recovery target; hãy sử dụng runbook đã được kiểm chứng cho phiên bản thực tế.

### 7.5. Xác nhận TDE sau restore

Sau khi khôi phục keystore, xác nhận trạng thái:

```sql
SELECT
    wrl_type,
    wrl_parameter,
    status,
    wallet_type,
    keystore_mode
FROM v$encryption_wallet;
```

Với password-based keystore, DBA có thể mở keystore bằng câu lệnh phù hợp với phiên bản và container:

```sql
ADMINISTER KEY MANAGEMENT SET KEYSTORE OPEN
    IDENTIFIED BY "<keystore_password>";
```

Không đặt mật khẩu thật trong script được lưu hoặc chia sẻ. Với CDB/PDB, có thể cần chỉ định container hoặc mở keystore trong container tương ứng. Hãy tham khảo cú pháp theo chế độ united/isolated và xác nhận từng PDB cần phục hồi.

Sau khi wallet mở, thực hiện truy vấn đọc các bảng/tablespace đã mã hóa để chứng minh Oracle giải mã được dữ liệu. Chỉ nhìn thấy `STATUS = OPEN` chưa đủ để chứng minh tất cả master key lịch sử cần thiết đều sẵn sàng; cần kiểm tra dữ liệu đã mã hóa từ các thời kỳ khác nhau trong bài diễn tập.

### 7.6. Kiểm tra dữ liệu và ứng dụng

Database mở thành công vẫn chưa chứng minh ứng dụng hoạt động đúng. Nên có các kiểm tra phù hợp với hệ thống:

- `V$DATABASE.OPEN_MODE`, trạng thái instance và trạng thái PDB.
- Datafile, tablespace và archived log không có lỗi cần xử lý.
- Các schema quan trọng tồn tại; object invalid được ghi nhận và xử lý.
- Số lượng bản ghi, tổng tiền hoặc checksum ở các bảng nghiệp vụ quan trọng khớp với kỳ vọng tại recovery point.
- Có thể đọc dữ liệu trong tablespace được TDE bảo vệ.
- Ứng dụng thử nghiệm kết nối tới service DR, chạy truy vấn và transaction thử nghiệm đã được phê duyệt.
- Job, scheduler, database link, external directory, wallet và dependency bên ngoài được kiểm tra theo phạm vi diễn tập.

Không nên chỉ so sánh tổng số dòng. Một bảng có thể có cùng số dòng nhưng mất các giao dịch mới nhất hoặc sai quan hệ. Chọn các kiểm tra nghiệp vụ phản ánh dữ liệu quan trọng và thời điểm khôi phục.

## 8. Chứng minh RPO và RTO

### 8.1. RPO là gì?

Recovery Point Objective (RPO) là lượng dữ liệu tối đa mà tổ chức chấp nhận mất khi có sự cố, thường được biểu diễn bằng thời gian. Ví dụ RPO 15 phút nghĩa là recovery point phải nằm trong khoảng không quá 15 phút trước thời điểm gián đoạn theo cách đo đã thống nhất.

RPO phụ thuộc tần suất backup, tốc độ chuyển archived redo log, độ trễ replication và khả năng truy cập các log cần thiết. Backup database mỗi đêm không thể tự chứng minh RPO 15 phút nếu archived redo log không được lưu và chuyển ra ngoài thường xuyên.

### 8.2. RTO là gì?

Recovery Time Objective (RTO) là khoảng thời gian mục tiêu để đưa dịch vụ trở lại trạng thái sử dụng được sau sự cố. RTO không chỉ là thời gian RMAN restore datafile; còn có thời gian cấp hạ tầng, lấy backup, khôi phục keystore, recover redo, mở database, xác nhận dữ liệu và khởi động ứng dụng.

### 8.3. Ghi nhận bằng chứng trong buổi diễn tập

Một báo cáo DR drill nên ghi:

| Chỉ số | Cách ghi nhận |
|---|---|
| Thời điểm sự cố giả lập | Timestamp bắt đầu diễn tập và recovery target. |
| Backup được chọn | Tag, piece, thời điểm backup, vị trí off-host và trạng thái validation. |
| Keystore | Vị trí, loại, bản backup, key history và kết quả mở trên host đích. |
| Recovery point thực tế | Thời điểm redo cuối cùng được áp dụng hoặc dữ liệu cuối cùng có thể xác nhận. |
| RPO thực tế | Chênh lệch giữa thời điểm sự cố giả lập và recovery point. |
| RTO thực tế | Thời gian từ khi bắt đầu phục hồi đến khi dịch vụ vượt qua kiểm tra sẵn sàng. |
| Kiểm tra dữ liệu | Kết quả truy vấn, checksum, số liệu nghiệp vụ và object cần thiết. |
| Vấn đề phát sinh | Thiếu quyền, thiếu key, backup chậm, log thiếu, lỗi cấu hình hoặc bước thủ công. |
| Hành động cải thiện | Người phụ trách, hạn hoàn thành và cách kiểm chứng lại. |

Ví dụ: sự cố giả lập bắt đầu lúc 10:00, database được phục hồi tới 09:52 và ứng dụng sẵn sàng lúc 10:48. RPO thực tế là 8 phút; RTO thực tế là 48 phút. Nếu mục tiêu của tổ chức là RPO 15 phút và RTO 60 phút, lần diễn tập này đáp ứng hai mục tiêu theo các mốc đã đo. Các số liệu chỉ có ý nghĩa nếu đồng hồ, timezone và định nghĩa “dịch vụ sẵn sàng” được thống nhất.

### 8.4. Tần suất diễn tập

Tần suất phụ thuộc mức độ quan trọng của hệ thống, tốc độ thay đổi, yêu cầu pháp lý và RPO/RTO. Có thể tổ chức:

- Kiểm tra RMAN backup và trạng thái off-host tự động mỗi ngày.
- Kiểm tra restore validate định kỳ và sau thay đổi lớn của cấu hình backup.
- Diễn tập restore/recovery đầy đủ theo quý hoặc theo chu kỳ được phê duyệt.
- Diễn tập riêng tình huống mất host, mất site, mất control file, mất keystore hoặc không truy cập được key manager.
- Diễn tập lại sau khi rotate TDE key, thay đổi mật khẩu keystore, chuyển storage hoặc nâng cấp Oracle.

Lịch cụ thể phải đủ để phát hiện sớm việc backup hỏng, key không còn truy cập hoặc quy trình đã lỗi thời. Một lần diễn tập thành công từ nhiều tháng trước không chứng minh backup mới nhất vẫn có thể khôi phục.

## 9. Lỗi thường gặp và cách giảm rủi ro

| Lỗi | Hậu quả | Cách phòng tránh |
|---|---|---|
| Chỉ backup datafile mà quên keystore | Không giải mã được dữ liệu TDE sau restore. | Đưa keystore và secret vào kế hoạch backup/DR. |
| Chỉ lưu `cwallet.sso` | Có thể không mở được trên host khác hoặc thiếu bản password-based cần thiết. | Giữ `ewallet.p12`, mật khẩu và quy trình tạo auto-login trên host đích. |
| Rotate key nhưng không backup keystore mới | Backup database mới cần khóa không có trong bản keystore off-host. | Backup keystore sau mỗi thay đổi khóa và kiểm tra bản sao. |
| Xóa keystore cũ khi vẫn còn backup cũ | Không thể giải mã dữ liệu được bảo vệ bởi key lịch sử. | Giữ key history theo vòng đời backup. |
| Lưu backup trên cùng storage hoặc cùng credential | Một sự cố có thể phá cả production và backup. | Dùng failure domain, tài khoản và immutable retention độc lập. |
| Chỉ kiểm tra job status | Backup có thể thiếu log, không đọc được hoặc không restore được. | Kết hợp validate, restore drill và application validation. |
| Quên archived redo log | Không thể recovery tới thời điểm yêu cầu. | Backup và chuyển archived log theo lịch phù hợp với RPO. |
| Mất mật khẩu backup hoặc keystore | File còn nhưng không giải mã/mở được. | Lưu secret trong hệ thống độc lập, có break-glass và audit. |
| Chỉ diễn tập trên cùng host | Không chứng minh có thể khôi phục khi mất host/site. | Restore sang host hoặc failure domain khác. |
| Không kiểm tra PDB isolated keystore | PDB restore có thể thiếu key riêng. | Kiểm kê keystore theo CDB/PDB và diễn tập đúng chế độ. |
| Không đo RPO/RTO | Không biết khả năng phục hồi có đáp ứng mục tiêu nghiệp vụ. | Ghi timestamp và kết quả từng bước trong mỗi drill. |

## 10. Runbook mẫu cho backup và restore drill

### 10.1. Trước khi backup

1. Xác nhận database, instance, container và `ARCHIVELOG` mode.
2. Xác nhận RMAN repository, channel, destination và dung lượng.
3. Kiểm tra TDE wallet đang mở, loại keystore và vị trí cấu hình.
4. Xác nhận backup keystore gần nhất có sau lần rotate key mới nhất.
5. Kiểm tra secret manager có mật khẩu và quyền truy cập khẩn cấp.
6. Kiểm tra kho off-host, immutable policy và retention.

### 10.2. Trong và sau backup

1. Chạy RMAN backup database và archived redo log theo lịch.
2. Đảm bảo control file và SPFILE được backup hoặc autobackup.
3. Chuyển backup piece sang kho off-host độc lập.
4. Xác minh file, checksum hoặc cơ chế integrity của storage.
5. Sao lưu keystore sau thay đổi khóa và chuyển bản sao sang kho bảo mật.
6. Ghi metadata: database, DBID, DB_UNIQUE_NAME, thời gian, tag, backup piece, archived log range và key backup.
7. Ghi nhận job status và cảnh báo nếu bất kỳ thành phần bắt buộc nào thiếu.

### 10.3. Trong buổi restore drill

1. Chọn backup off-host và recovery point cần chứng minh.
2. Cấp host/VM và storage thử nghiệm trong mạng cô lập.
3. Lấy keystore và secret qua quy trình DR; mở keystore trên host đích.
4. Khôi phục control file/SPFILE, datafile và archived redo log bằng runbook đã phê duyệt.
5. Mở database theo đúng loại recovery và xác nhận TDE data đọc được.
6. Chạy kiểm tra dữ liệu, object và ứng dụng.
7. Ghi RPO/RTO thực tế, lỗi phát sinh và bằng chứng.
8. Thu hồi quyền, dọn môi trường thử nghiệm và lưu báo cáo theo chính sách.

### 10.4. Bằng chứng cần lưu

- RMAN log và danh sách backup piece được dùng.
- Kết quả `LIST BACKUP`, `CROSSCHECK` và `RESTORE ... VALIDATE`.
- Bản ghi kiểm tra keystore, key history và kết quả mở wallet trên host đích.
- Timestamp bắt đầu, các mốc restore/recover, thời điểm mở database và thời điểm ứng dụng sẵn sàng.
- Kết quả kiểm tra dữ liệu và ứng dụng.
- RPO/RTO thực tế, người tham gia, phê duyệt và hành động khắc phục.

Không lưu mật khẩu hoặc private key vào báo cáo. Chỉ ghi ID tham chiếu secret, vị trí lưu được bảo vệ và người có quyền truy xuất.

## Kết luận

Backup Oracle có TDE phải bảo vệ cả database backup lẫn keystore, master key history và mật khẩu cần để sử dụng chúng. Bản sao database và archived redo log cần được lưu ở failure domain khác, có quyền quản trị tách biệt và retention chống xóa ngoài ý muốn. Kiểm tra job status hoặc metadata chỉ là bước đầu; bằng chứng mạnh nhất là restore và recover thực tế trên môi trường cô lập, mở được dữ liệu TDE, xác nhận ứng dụng và đo được RPO/RTO. Khi những hoạt động này được ghi thành runbook và diễn tập định kỳ, tổ chức mới có cơ sở chứng minh khả năng phục hồi khi máy chủ hoặc site chính gặp sự cố.
