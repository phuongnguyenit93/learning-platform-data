# SYSDBA, SYSOPER và các quyền quản trị chuyên biệt trong Oracle

Oracle Database có các quyền quản trị đặc biệt để cho phép một số tài khoản thực hiện thao tác ở cấp instance, database, backup, Data Guard, encryption key hoặc Oracle ASM. Hai quyền thường gặp nhất là **SYSDBA** và **SYSOPER**. Chúng không phải role thông thường như DBA; đây là các administrative privileges được dùng khi kết nối tới database, ví dụ `CONNECT / AS SYSDBA` hoặc `CONNECT backup_user@service AS SYSBACKUP`.

SYSDBA cho phép thực hiện gần như toàn bộ công việc quản trị database, bao gồm startup/shutdown, mount/open, recovery và truy cập đặc quyền vào data dictionary. SYSOPER có phạm vi hẹp hơn, tập trung vào một số thao tác vận hành instance như startup/shutdown, mount/open database và một số thao tác quản trị giới hạn. Các quyền chuyên biệt như SYSBACKUP, SYSDG, SYSKM, SYSASM và SYSRAC hỗ trợ phân tách nhiệm vụ: người làm backup không nhất thiết phải có toàn quyền SYSDBA, người quản lý Data Guard không cần quyền quản lý mọi dữ liệu ứng dụng, và người quản lý ASM không cần dùng quyền database administrator.

Phân tách quyền giúp giảm phạm vi thiệt hại khi tài khoản bị lộ, giới hạn thao tác ngoài nhiệm vụ và tạo dấu vết kiểm toán rõ ràng. Việc cấp quyền phải đi cùng cách xác thực phù hợp: OS authentication cho kết nối cục bộ, password file authentication cho kết nối quản trị từ xa, kiểm soát thành viên OS groups và audit các phiên đặc quyền.

Bài học thuộc chủ đề **Bảo mật** của *Database Engine Relational Oracle*. Nội dung tập trung vào:

- Administrative privileges khác role và system privileges thông thường như thế nào.
- Phạm vi và use case của SYSDBA, SYSOPER.
- SYSBACKUP, SYSDG, SYSKM, SYSASM và SYSRAC.
- OS authentication, password file và tham số REMOTE_LOGIN_PASSWORDFILE.
- Cấp/thu hồi quyền, kiểm tra V$PWFILE_USERS và quản lý tài khoản.
- Kết nối SQL*Plus/SQLcl và thao tác startup/shutdown.
- Least privilege, separation of duties, auditing và vận hành an toàn.
- Lỗi thường gặp và bài thực hành kiểm tra quyền trong môi trường lab.

## 1. Administrative privilege là gì?

Administrative privilege là quyền đặc biệt cho phép kết nối và thực hiện thao tác quản trị database/instance vượt ngoài phạm vi quyền SQL thông thường. Oracle hỗ trợ các quyền như:

| Quyền | Mục đích chính |
| --- | --- |
| SYSDBA | Quản trị database toàn diện, bao gồm startup/shutdown, mount/open, recovery và thao tác đặc quyền. |
| SYSOPER | Vận hành instance/database với tập thao tác giới hạn. |
| SYSBACKUP | Backup và recovery database theo phạm vi chuyên biệt. |
| SYSDG | Quản trị Oracle Data Guard. |
| SYSKM | Quản lý encryption key/keystore, đặc biệt cho Transparent Data Encryption. |
| SYSASM | Quản trị Oracle ASM instance và disk groups. |
| SYSRAC | Thực hiện các thao tác quản trị chuyên biệt cho Oracle RAC. |

Tên và khả năng cụ thể của một số privilege có thể khác theo Oracle release, architecture và công cụ. Hãy đối chiếu tài liệu của phiên bản đang vận hành trước khi cấp hoặc dùng trong production.

### Không nhầm administrative privilege với role DBA

`DBA` là một database role chứa nhiều system privileges và quyền quản trị thông thường. Role này không tương đương SYSDBA:

- Người có role DBA vẫn không mặc nhiên có quyền kết nối `AS SYSDBA`.
- Role DBA không thay thế các thao tác startup/shutdown hoặc recovery yêu cầu administrative privilege.
- SYSDBA có ngữ nghĩa đặc biệt khi kết nối và thực thi; nó không chỉ là một tập grant thông thường.
- Quyền SYSDBA/SYSOPER và các quyền quản trị chuyên biệt được quản lý qua cơ chế administrative authentication/password file hoặc OS authentication, không nên chỉ tìm trong DBA_SYS_PRIVS như một system privilege thông thường.

### SYS là schema, SYSDBA là privilege

`SYS` là schema/user quản trị đặc biệt sở hữu data dictionary và các đối tượng lõi. `SYSDBA` là administrative privilege cho phép kết nối với quyền quản trị tương ứng. Hai khái niệm liên quan nhưng không đồng nghĩa.

Khi kết nối `AS SYSDBA`, Oracle thực hiện phiên quản trị với danh tính SYS theo semantics của SYSDBA. Vì vậy, câu lệnh DDL/DML chạy trong phiên này có thể tác động trực tiếp tới dictionary và object hệ thống. Không dùng SYSDBA để chạy ứng dụng hoặc thao tác dữ liệu nghiệp vụ hằng ngày.

## 2. SYSDBA: quyền quản trị database toàn diện

SYSDBA là quyền cao nhất trong nhóm administrative privileges dành cho database instance. Tài khoản có SYSDBA có thể thực hiện các thao tác quản trị rộng, chẳng hạn:

- STARTUP và SHUTDOWN instance.
- MOUNT, OPEN, CLOSE database.
- Thực hiện media recovery và các thao tác phục hồi.
- Tạo, sửa hoặc quản lý các thành phần database ở cấp quản trị.
- Truy cập các đối tượng dictionary với quyền đặc biệt.
- Quản lý người dùng và cấp quyền quản trị.
- Thực hiện các thao tác bảo trì cần đặc quyền SYSDBA.

SYSDBA có quyền rất rộng; một lỗi hoặc câu lệnh sai trong phiên này có thể ảnh hưởng toàn database. Chỉ cấp cho DBA/nhóm vận hành thực sự cần và có quy trình kiểm soát.

### Kết nối cục bộ bằng OS authentication

Trên máy database server, người dùng thuộc OS group được ánh xạ tới OSDBA có thể kết nối mà không nhập username/password database:

~~~sql
sqlplus / as sysdba
~~~

Hoặc trong SQL*Plus đang mở:

~~~sql
CONNECT / AS SYSDBA
~~~

Quyền này dựa trên danh tính OS của tiến trình client và group membership tại máy chủ. Người dùng có thể kết nối SYSDBA mà không cần password file password nếu OS authentication được cấu hình cho host đó.

### Kết nối từ xa bằng password file authentication

Kết nối quản trị qua Oracle Net thường cần password file authentication:

~~~sql
sqlplus admin_dba@prod_service as sysdba
~~~

SQL*Plus sẽ hỏi mật khẩu nếu chưa được cung cấp qua cơ chế an toàn. Tránh ghi password trực tiếp trên command line, script plain text, shell history hoặc log.

Tài khoản phải được cấp SYSDBA và password file/remote authentication phải được cấu hình phù hợp. Kết nối từ xa qua SYSDBA cần bảo vệ network, listener, password file và secret như credential có quyền cao nhất.

### Xác nhận phiên quản trị

~~~sql
SHOW USER;

SELECT sys_context('USERENV', 'SESSION_USER') AS session_user,
       sys_context('USERENV', 'CURRENT_USER') AS current_user,
       sys_context('USERENV', 'ISDBA') AS isdba
FROM dual;
~~~

`ISDBA` có thể giúp xác nhận session đang dùng quyền SYSDBA theo phiên bản. Không dựa vào một biến duy nhất để kiểm toán; cần kết hợp audit trail và thông tin kết nối.

## 3. SYSOPER: quyền vận hành giới hạn

SYSOPER dành cho nhiệm vụ vận hành instance/database nhưng không cần toàn quyền SYSDBA. Quyền này cho phép một số thao tác như:

- STARTUP và SHUTDOWN.
- MOUNT database và OPEN database.
- ALTER DATABASE ở các phạm vi vận hành được cho phép, chẳng hạn một số thao tác backup/archive.
- Bật restricted session trong phạm vi privilege hỗ trợ.

SYSOPER không cho phép người vận hành tự do đọc/sửa dữ liệu ứng dụng hoặc thực hiện mọi tác vụ quản trị như SYSDBA. Phạm vi thao tác chính xác cần đối chiếu privilege table của Oracle release đang dùng.

### Kết nối bằng SYSOPER

~~~sql
sqlplus ops_user@prod_service as sysoper
~~~

Hoặc kết nối cục bộ nếu OS group tương ứng đã được cấu hình:

~~~sql
sqlplus / as sysoper
~~~

### Ví dụ thao tác vận hành

~~~sql
SHUTDOWN IMMEDIATE;
~~~

~~~sql
STARTUP MOUNT;
~~~

~~~sql
ALTER DATABASE OPEN;
~~~

Các lệnh này chỉ chạy khi database/instance đang ở trạng thái phù hợp. SYSOPER có thể thực hiện một số thao tác vận hành nhưng không thay thế DBA cho recovery phức tạp, thay đổi cấu trúc hoặc truy cập dữ liệu đặc quyền.

### SYSOPER không phải quyền đọc dữ liệu ứng dụng

Tài khoản có SYSOPER không nên được cấp thêm quyền đọc các bảng nghiệp vụ chỉ để theo dõi ứng dụng. Hãy dùng tài khoản monitoring với SELECT privilege tối thiểu trên view cần thiết. Việc vận hành instance và việc truy vấn dữ liệu nghiệp vụ là hai nhiệm vụ khác nhau.

## 4. So sánh SYSDBA và SYSOPER

| Tiêu chí | SYSDBA | SYSOPER |
| --- | --- | --- |
| Mức quyền | Toàn diện, đặc quyền cao nhất cho database administration | Giới hạn cho một số tác vụ vận hành |
| Startup/shutdown | Có | Có |
| Mount/open database | Có | Có, trong phạm vi cho phép |
| Recovery | Có quyền thực hiện các thao tác recovery quản trị | Không có toàn bộ quyền recovery của SYSDBA |
| Truy cập dictionary/data | Có quyền đặc biệt rộng | Không được cấp quyền đọc/sửa dữ liệu tùy ý |
| Quản trị user/privilege | Có | Không phải mục đích của SYSOPER |
| Phù hợp | DBA, database recovery, cấu hình và quản trị tổng thể | Operator thực hiện startup/shutdown và tác vụ vận hành giới hạn |
| Rủi ro khi credential bị lộ | Rất cao | Thấp hơn SYSDBA nhưng vẫn có thể gây gián đoạn database |

### Chọn SYSOPER hay SYSDBA?

Nếu nhiệm vụ chỉ cần khởi động/dừng instance, mount/open database hoặc thao tác vận hành giới hạn, đánh giá SYSOPER trước. Nếu cần recovery, thay đổi cấu hình database, quản lý user/privilege hoặc thao tác toàn diện, DBA được ủy quyền mới dùng SYSDBA.

Không cấp SYSDBA chỉ vì một script cũ yêu cầu quyền này. Hãy xác định chính xác câu lệnh cần chạy và chọn administrative privilege nhỏ nhất đáp ứng yêu cầu.

## 5. SYSBACKUP: phân tách nhiệm vụ backup và recovery

SYSBACKUP được giới thiệu để người vận hành backup/recovery thực hiện công việc bằng RMAN và các API liên quan mà không cần toàn bộ quyền SYSDBA. Đây là một phần của mô hình separation of duties.

### Use case

- Kết nối RMAN để thực hiện backup database.
- Thực hiện các thao tác restore/recover theo phạm vi privilege.
- Quản lý một số thao tác backup/recovery mà không cấp quyền quản trị toàn diện.

### Cấp quyền

~~~sql
GRANT SYSBACKUP TO backup_operator;
~~~

Kết nối:

~~~sql
CONNECT backup_operator@prod_service AS SYSBACKUP
~~~

RMAN có thể dùng administrative connection tương ứng:

~~~text
rman target backup_operator@prod_service
~~~

Khi công cụ yêu cầu administrative privilege, sử dụng đúng cơ chế xác thực và cú pháp được hỗ trợ trong môi trường. Không ghi password vào script hoặc command line.

### SYSBACKUP không thay thế quy trình backup

Có SYSBACKUP không tự bảo đảm backup có thể restore. Vẫn cần:

- Chính sách retention và backup schedule.
- Backup control file, SPFILE và archived redo theo yêu cầu recovery.
- Kiểm tra backup pieces, catalog/control file metadata.
- Test restore/recover trên môi trường độc lập.
- Bảo vệ quyền truy cập backup storage và encryption keys.

### SYSBACKUP và SYSDBA

SYSBACKUP giảm quyền so với SYSDBA cho người chỉ làm backup/recovery. Nếu công việc cụ thể yêu cầu thao tác ngoài phạm vi SYSBACKUP, hãy xác định và phê duyệt quyền bổ sung riêng; không mặc định nâng lên SYSDBA.

## 6. SYSDG: quản trị Data Guard

SYSDG là administrative privilege chuyên biệt cho các thao tác Oracle Data Guard. Nó hỗ trợ người vận hành quản lý môi trường primary/standby, broker và các thao tác liên quan mà không cần cấp toàn bộ SYSDBA.

### Use case

- Thực hiện các thao tác quản trị Data Guard qua SQL*Plus hoặc công cụ tương ứng.
- Quản lý một số trạng thái database primary/standby.
- Thực hiện công việc liên quan Data Guard Broker theo quyền được hỗ trợ.

### Cấp quyền và kết nối

~~~sql
GRANT SYSDG TO dataguard_operator;
~~~

~~~sql
CONNECT dataguard_operator@prod_service AS SYSDG
~~~

### Lưu ý

SYSDG không phải quyền quản trị toàn bộ database. Nó không thay thế SYSDBA cho mọi hoạt động database, cũng không thay thế tài khoản quản trị OS/Clusterware. Người vận hành cần tuân thủ quy trình switchover/failover, kiểm tra apply lag, transport lag, role transition và bảo đảm có kế hoạch quay lui.

## 7. SYSKM: quản lý encryption key và keystore

SYSKM là administrative privilege dành cho các thao tác quản lý key/keystore, đặc biệt liên quan Transparent Data Encryption (TDE). Việc tách quyền này giúp người quản lý khóa thực hiện nhiệm vụ mà không nhất thiết có toàn quyền DBA trên dữ liệu.

### Use case

- Quản lý TDE keystore/wallet.
- Thực hiện thao tác key management được Oracle hỗ trợ.
- Hỗ trợ các quy trình mở/đóng keystore, backup hoặc rotate master encryption key theo phiên bản/cấu hình.

### Cấp quyền và kết nối

~~~sql
GRANT SYSKM TO key_operator;
~~~

~~~sql
CONNECT key_operator@prod_service AS SYSKM
~~~

### Bảo vệ SYSKM

Credential SYSKM và keystore password có thể quyết định khả năng giải mã dữ liệu. Không đặt chúng trong cùng secret store hoặc cùng nhóm người có quyền với backup nếu mô hình separation of duties yêu cầu độc lập. Backup keystore và kiểm tra restore/recovery là phần bắt buộc của quy trình TDE.

SYSKM không có nghĩa là người vận hành có thể đọc mọi dữ liệu plaintext. Quyền key management và quyền truy cập bảng/dữ liệu là hai lớp khác nhau; cần tuân theo privilege model của Oracle release.

## 8. SYSASM: quản trị Oracle ASM

SYSASM là administrative privilege dành cho Oracle Automatic Storage Management (ASM). ASM quản lý disk groups và storage được database sử dụng. SYSASM dùng để kết nối với ASM instance và thực hiện các thao tác quản trị storage.

### Use case

- Tạo, mount, dismount hoặc drop ASM disk groups.
- Quản lý ASM disks, failure groups và thuộc tính disk group.
- Giám sát và vận hành ASM instance.
- Thực hiện các thao tác storage quản trị theo quyền được hỗ trợ.

### Kết nối ASM

~~~sql
sqlplus / as sysasm
~~~

Hoặc dùng tài khoản password file được cấp SYSASM theo cấu hình:

~~~sql
CONNECT asm_operator@asm_service AS SYSASM
~~~

### SYSASM khác SYSDBA

SYSASM quản trị ASM instance và storage; SYSDBA quản trị database instance. Hai phạm vi có liên quan nhưng không đồng nhất. Trong kiến trúc tách biệt, không cấp SYSASM cho DBA ứng dụng nếu họ không cần quản lý ASM; không dùng SYSDBA để thay thế quy trình quản trị ASM chuyên biệt.

### OS groups cho ASM

Trên Unix/Linux, installation có thể dùng các group như OSASM (thường được đặt tên asmadmin), OSDBA và OSOPER. Tên group thực tế phụ thuộc cấu hình cài đặt và Oracle Grid Infrastructure. Không tự giả định tên group; xác nhận trong cấu hình host và tài liệu cài đặt.

## 9. SYSRAC: quyền quản trị chuyên biệt cho RAC

SYSRAC là administrative privilege phục vụ một số tác vụ quản trị Oracle Real Application Clusters và các tiện ích/agent liên quan. Nó hỗ trợ phân tách quyền cho hoạt động RAC mà không cần cấp toàn bộ SYSDBA.

### Use case

- Các tác vụ quản trị RAC được Oracle hỗ trợ với SYSRAC.
- Hoạt động của Clusterware/agent hoặc công cụ quản trị cần privilege chuyên biệt.
- Một số thao tác liên quan RAC instance/node/service theo phiên bản.

### Cấp quyền và kết nối

~~~sql
GRANT SYSRAC TO rac_operator;
~~~

~~~sql
CONNECT rac_operator@prod_service AS SYSRAC
~~~

Phạm vi chính xác của SYSRAC phụ thuộc Oracle release và công cụ sử dụng. Đây không phải quyền thay thế SYSDBA cho database administration, cũng không tự cấp quyền OS để quản lý Grid Infrastructure. Clusterware/ASM vẫn có các lớp quyền và tài khoản OS riêng.

## 10. Bảng so sánh các quyền quản trị chuyên biệt

| Privilege | Phạm vi | Nhóm công việc nên giao |
| --- | --- | --- |
| SYSDBA | Database/instance toàn diện | DBA cấp cao, recovery và quản trị tổng thể |
| SYSOPER | Vận hành database giới hạn | Operator startup/shutdown, mount/open |
| SYSBACKUP | Backup/recovery | Backup operator, RMAN |
| SYSDG | Data Guard | Data Guard operator |
| SYSKM | Encryption key/keystore | Key management officer |
| SYSASM | ASM storage/instance | ASM administrator |
| SYSRAC | RAC-specific operations | RAC/Clusterware operations theo quyền được hỗ trợ |

### Separation of duties

Một mô hình phân tách có thể gồm:

- DBA quản trị database và cấp quyền SYSDBA khi cần.
- Operator thực hiện startup/shutdown bằng SYSOPER.
- Backup team dùng SYSBACKUP.
- Data Guard team dùng SYSDG.
- Key management team dùng SYSKM.
- Storage/ASM team dùng SYSASM.
- RAC operations dùng SYSRAC và các quyền OS/Clusterware cần thiết.

Mô hình cụ thể phụ thuộc quy mô, kiến trúc và chính sách tổ chức. Một người có thể giữ nhiều vai trò trong môi trường nhỏ, nhưng mỗi quyền phải được cấp theo nhiệm vụ và được audit.

## 11. Xác thực OS và OS groups

Oracle hỗ trợ operating system authentication cho administrative connection trên host database. Người dùng OS thuộc group quản trị phù hợp có thể kết nối bằng cú pháp slash mà không cần nhập database username/password:

~~~sql
sqlplus / as sysdba
sqlplus / as sysoper
sqlplus / as sysasm
~~~

Oracle installer/configuration ánh xạ các OS groups tới administrative privileges. Trên Unix/Linux, các tên thường gặp gồm:

| OS group category | Privilege thường tương ứng |
| --- | --- |
| OSDBA (thường có tên dba) | SYSDBA |
| OSOPER (thường có tên oper) | SYSOPER |
| OSBACKUPDBA (thường có tên backupdba) | SYSBACKUP |
| OSDGDBA (thường có tên dgdba) | SYSDG |
| OSKMDBA (thường có tên kmdba) | SYSKM |
| OSRACDBA (thường có tên racdba) | SYSRAC |
| OSASM (thường có tên asmadmin) | SYSASM |

Tên group thực tế phụ thuộc installation owner, Oracle Grid Infrastructure, Oracle Home và nền tảng. Trên Windows, Oracle dùng các local groups có tên theo dạng ORA_DBA, ORA_OPER và các group tương ứng theo home/role. Không áp dụng bảng tên Linux một cách máy móc cho Windows.

### Vì sao OS group rất nhạy cảm?

Thành viên OSDBA thường có thể lấy quyền SYSDBA cục bộ. Nếu một tài khoản OS thông thường được thêm nhầm vào group này, người đó có thể quản trị database mà không cần biết password database. Vì vậy:

- Giới hạn membership OSDBA/OSOPER và các group chuyên biệt.
- Không thêm user ứng dụng, developer hoặc tài khoản CI/CD vào OSDBA chỉ để chạy một lệnh.
- Rà soát group membership định kỳ và khi nhân sự thay đổi.
- Bảo vệ quyền truy cập host, sudo, SSH và tài khoản Oracle software owner.
- Tách tài khoản người vận hành khỏi tài khoản chạy ứng dụng.

### Kiểm tra OS group

Trên Linux/Unix, DBA/administrator có thể kiểm tra group membership bằng công cụ OS như id hoặc getent. Trên Windows, kiểm tra Local Users and Groups hoặc công cụ quản trị domain. Các thao tác này nằm ngoài SQL và phải tuân thủ quyền quản trị host.

### OS authentication không phải password file authentication

OS authentication xác thực qua user/group của host database. Password file authentication xác thực tài khoản database được cấp administrative privilege qua password file, thường dùng cho kết nối từ xa. Hai cơ chế có thể cùng tồn tại nhưng cần được cấu hình và bảo vệ riêng.

## 12. Password file authentication

Password file là file đặc biệt Oracle dùng để xác thực các tài khoản được cấp administrative privileges khi kết nối quản trị qua Oracle Net. Nó cho phép một tài khoản database được xác thực để kết nối AS SYSDBA, SYSOPER hoặc các privilege chuyên biệt tùy phiên bản.

### Khi nào cần password file?

- DBA kết nối từ máy quản trị từ xa qua service/listener.
- RMAN hoặc công cụ quản trị kết nối tới database từ host khác.
- RAC instances cần dùng password file chung theo cấu hình.
- Cần quản lý tài khoản quản trị riêng thay vì dựa vào OS account trên host database.

### REMOTE_LOGIN_PASSWORDFILE

Tham số initialization parameter REMOTE_LOGIN_PASSWORDFILE điều khiển việc sử dụng password file. Các giá trị phổ biến:

| Giá trị | Ý nghĩa khái quát |
| --- | --- |
| NONE | Không sử dụng password file authentication cho administrative connection. |
| EXCLUSIVE | Password file dành cho một database; hỗ trợ quản lý các administrative users được cấp quyền. |
| SHARED | Password file có thể được chia sẻ theo các giới hạn của Oracle; khả năng quản lý user/admin privilege bị hạn chế hơn EXCLUSIVE. |

Kiểm tra:

~~~sql
SHOW PARAMETER remote_login_passwordfile;

SELECT name, value, isdefault, issys_modifiable
FROM v$parameter
WHERE name = 'remote_login_passwordfile';
~~~

Giá trị mặc định và khả năng thay đổi phụ thuộc release/platform. Một số cấu hình cần restart instance để thay đổi có hiệu lực; xem tài liệu phiên bản trước khi sửa.

### Tạo password file

Oracle cung cấp tiện ích orapwd để tạo password file. Cú pháp tùy phiên bản và cách triển khai (filesystem hoặc ASM):

~~~text
orapwd file=orapwORCL password=<secure-password> entries=20
~~~

Đây là cú pháp minh họa; không đặt password thật trong shell history hoặc log. Với Oracle RAC/ASM và các phiên bản mới, password file có thể được quản lý trong ASM và dùng bởi nhiều instance. Dùng công cụ/cấu hình được Oracle hỗ trợ cho môi trường thực tế thay vì tự copy file thủ công khi cluster đang chạy.

### Bảo vệ password file

- Hạn chế quyền OS đọc/ghi file.
- Không đưa file vào source control hoặc image ứng dụng.
- Dùng secret management và rotation theo chính sách.
- Giám sát thay đổi administrative privilege và password file.
- Đồng bộ file theo quy trình được hỗ trợ trong RAC/Data Guard.
- Không chia sẻ credential SYSDBA giữa nhiều người nếu có thể cấp account riêng.

### Password file và user được cấp privilege

Khi cấp SYSDBA/SYSOPER hoặc privilege chuyên biệt cho một database user, Oracle ghi nhận thông tin quản trị tương ứng trong password file khi cấu hình cho phép. V$PWFILE_USERS là view quan trọng để kiểm tra những user được cấp quyền administrative.

## 13. Cấp và thu hồi administrative privileges

Administrative privileges được cấp cho database user bằng GRANT và thu hồi bằng REVOKE. Các thao tác này cần người thực hiện có quyền quản trị thích hợp, thường là kết nối SYSDBA.

### Tạo user quản trị riêng

~~~sql
CREATE USER ops_user IDENTIFIED BY "<secret-managed-password>";
GRANT SYSOPER TO ops_user;
~~~

Tùy release và authentication setup, cấp administrative privilege có thể yêu cầu user tồn tại và password file ở chế độ phù hợp. Không cấp role DBA kèm theo nếu nhiệm vụ chỉ cần SYSOPER.

### Cấp SYSDBA

~~~sql
GRANT SYSDBA TO dba_operator;
~~~

### Cấp quyền chuyên biệt

~~~sql
GRANT SYSBACKUP TO backup_operator;
GRANT SYSDG TO dataguard_operator;
GRANT SYSKM TO key_operator;
GRANT SYSRAC TO rac_operator;
~~~

SYSASM thường được quản lý trong ngữ cảnh ASM instance và cấu hình password file/OS group của ASM. Cấp quyền cho đúng user và đúng instance; không chạy lệnh ở database instance chỉ vì cú pháp trông tương tự.

### Thu hồi quyền

~~~sql
REVOKE SYSDBA FROM dba_operator;
REVOKE SYSOPER FROM ops_user;
REVOKE SYSBACKUP FROM backup_operator;
REVOKE SYSDG FROM dataguard_operator;
REVOKE SYSKM FROM key_operator;
REVOKE SYSRAC FROM rac_operator;
~~~

Sau khi revoke, kiểm tra lại V$PWFILE_USERS và xác nhận user không còn administrative privilege. Nếu credential đã bị lộ, ngoài revoke cần rotation password, rà soát OS group, active sessions và audit records.

### Không dùng tài khoản SYS làm tài khoản cá nhân

SYS là account hệ thống dùng cho công việc đặc quyền. Không đổi password/chia sẻ SYS cho nhiều DBA nếu mô hình có thể dùng account quản trị riêng. Account cá nhân giúp audit biết ai đã thực hiện thao tác và có thể thu hồi một người mà không ảnh hưởng người khác.

## 14. Kiểm tra administrative privileges trong database

V$PWFILE_USERS là view chính để xem những user được cấp administrative privileges qua password file. Quyền truy cập view có thể cần catalog privileges hoặc quyền SELECT phù hợp.

~~~sql
SELECT *
FROM v$pwfile_users
ORDER BY username;
~~~

Các cột thường gặp bao gồm USERNAME, SYSDBA, SYSOPER, SYSASM, SYSBACKUP, SYSDG, SYSKM và CON_ID. Cột cụ thể phụ thuộc Oracle release; dùng DESC V$PWFILE_USERS trước khi viết truy vấn giám sát cố định.

Ví dụ kiểm tra các quyền phổ biến nếu phiên bản có các cột này:

~~~sql
SELECT username,
       sysdba,
       sysoper,
       sysasm,
       sysbackup,
       sysdg,
       syskm
FROM v$pwfile_users
ORDER BY username;
~~~

### So sánh với DBA_SYS_PRIVS

~~~sql
SELECT grantee, privilege, admin_option
FROM dba_sys_privs
WHERE grantee IN ('OPS_USER', 'DBA_OPERATOR');
~~~

DBA_SYS_PRIVS liệt kê system privileges thông thường. Không dựa riêng vào view này để kiểm tra SYSDBA/SYSOPER; administrative privileges được quản lý theo cơ chế password file/OS authentication và được thể hiện trong V$PWFILE_USERS.

### Xem role DBA

~~~sql
SELECT grantee, granted_role, admin_option
FROM dba_role_privs
WHERE granted_role = 'DBA'
ORDER BY grantee;
~~~

Truy vấn này giúp phân biệt user có role DBA với user có administrative privilege. Hai danh sách có thể không trùng nhau.

### Xem cấu hình password file

~~~sql
SELECT name, value
FROM v$parameter
WHERE name = 'remote_login_passwordfile';
~~~

### Kiểm tra container

Trong môi trường multitenant:

~~~sql
SHOW CON_NAME;

SELECT sys_context('USERENV', 'CON_NAME') AS container_name,
       sys_context('USERENV', 'SESSION_USER') AS session_user,
       sys_context('USERENV', 'ISDBA') AS isdba
FROM dual;
~~~

Administrative privilege, user common/local và service kết nối có thể có phạm vi container khác nhau. Khi thao tác trong CDB/PDB, xác nhận đang ở đúng container/service và quyền được cấp ở đúng scope. Không giả định một grant trong root tự động có nghĩa mọi user local ở PDB đều có cùng quyền.

## 15. Audit administrative connections và thao tác SYS

Phiên SYSDBA/SYSOPER và các administrative connections cần được audit vì chúng có thể thay đổi trạng thái database hoặc truy cập dữ liệu nhạy cảm.

### AUDIT_SYS_OPERATIONS

Tham số AUDIT_SYS_OPERATIONS điều khiển việc audit các thao tác của user có administrative privilege như SYSDBA/SYSOPER theo cơ chế audit của Oracle release. Kiểm tra:

~~~sql
SHOW PARAMETER audit_sys_operations;

SELECT name, value
FROM v$parameter
WHERE name = 'audit_sys_operations';
~~~

Trong nhiều cấu hình, các bản ghi audit cho thao tác đặc quyền được ghi vào OS audit destination. Vị trí và cách lưu phụ thuộc nền tảng, AUDIT_TRAIL, unified auditing và cấu hình database. Hãy kiểm tra tài liệu đúng release và chính sách audit của tổ chức.

### Unified Auditing

Các phiên bản Oracle hỗ trợ Unified Auditing cung cấp audit policies và unified audit trail. DBA cần xác định policy nào ghi nhận administrative actions, login/logout, privilege use và thay đổi quyền. Cú pháp audit policy và hành vi SYS operations có thể phụ thuộc release/mode.

Có thể truy vấn trail khi được cấp quyền:

~~~sql
SELECT event_timestamp,
       dbusername,
       action_name,
       object_schema,
       object_name,
       return_code,
       unified_audit_policies
FROM unified_audit_trail
ORDER BY event_timestamp DESC;
~~~

View và các cột có thể khác theo release; dùng DESC UNIFIED_AUDIT_TRAIL. Giới hạn quyền đọc audit trail cho nhóm kiểm toán được ủy quyền.

### Audit thay đổi privilege

Theo dõi:

- GRANT/REVOKE SYSDBA, SYSOPER và các quyền chuyên biệt.
- Thay đổi password file hoặc cấu hình remote login.
- Thay đổi membership của OS groups.
- Đăng nhập quản trị từ xa và từ host lạ.
- Startup/shutdown, mount/open, recovery, role transition và ASM operations.
- Thay đổi audit policy, keystore hoặc backup destination.

Audit trong database không ghi nhận đầy đủ thay đổi group membership trên OS. Cần tích hợp log hệ điều hành, IAM, PAM hoặc hệ thống quản trị truy cập tương ứng.

### Audit phải được bảo vệ

Tài khoản có SYSDBA có thể thay đổi nhiều thành phần database; vì vậy audit trail phải được chuyển/giữ ở nơi mà cùng người vận hành không thể tùy tiện sửa hoặc xóa. Dùng quyền tách biệt cho audit review và log retention.

## 16. Quy trình vận hành an toàn

Trước một thao tác đặc quyền:

1. Xác định chính xác nhiệm vụ: startup/shutdown, backup, Data Guard, key management, ASM hay RAC.
2. Chọn administrative privilege nhỏ nhất phù hợp.
3. Dùng account cá nhân hoặc account vận hành riêng, không chia sẻ SYS.
4. Xác thực qua OS group hoặc password file đã được quản lý.
5. Xác nhận database, service, instance và container đúng mục tiêu.
6. Kiểm tra trạng thái hiện tại và tác động của lệnh.
7. Thực hiện trong change window/quy trình được phê duyệt nếu là production.
8. Ghi lại command, thời gian, operator, SQLCODE và kết quả.
9. Xác nhận database/service trở lại trạng thái mong muốn.
10. Đóng session và thu hồi quyền tạm thời nếu được cấp cho một nhiệm vụ ngắn hạn.

### Tách tài khoản theo nhiệm vụ

Một user backup không cần role DBA; một operator không cần quyền đọc bảng ứng dụng; một key manager không cần sửa dữ liệu nghiệp vụ. Nếu cần nhiều nhiệm vụ, cấp nhiều privilege có chủ đích và audit việc sử dụng từng quyền.

### Credential management

- Không lưu password trong script plain text.
- Dùng wallet/secure external password store hoặc secret manager theo chuẩn tổ chức.
- Không gửi password qua chat, ticket hoặc command line.
- Rotation password file theo quy trình hỗ trợ và kiểm tra mọi client/instance phụ thuộc.
- Bảo vệ file password và wallet ở OS/ASM.
- Dùng TLS/network controls cho remote administrative connections.
- Giới hạn listener exposure và chỉ cho phép host quản trị cần thiết.

### Quyền tạm thời

Nếu một engineer cần SYSDBA trong thời gian triển khai, cấp theo thời hạn/quy trình, ghi nhận người phê duyệt và thu hồi sau khi hoàn tất. Việc xóa quyền cần được xác nhận ở V$PWFILE_USERS và hệ thống IAM/OS group.

## 17. Thao tác vận hành thường gặp

Các ví dụ sau minh họa cú pháp. Thực hiện lệnh startup/shutdown hoặc mount/open chỉ trên instance được phép bảo trì, có change plan và xác nhận phụ thuộc ứng dụng.

### Shutdown

~~~sql
SHUTDOWN IMMEDIATE;
~~~

IMMEDIATE chặn phiên đăng nhập mới, chấm dứt session hiện tại theo quy trình Oracle, rollback transaction chưa commit và đóng database/instance. Đây là thao tác gián đoạn dịch vụ; không dùng trong lab trên database dùng chung.

### Startup ở NOMOUNT

~~~sql
STARTUP NOMOUNT;
~~~

NOMOUNT khởi động instance và đọc initialization parameters, nhưng chưa mount control file hoặc open datafiles.

### Mount database

~~~sql
ALTER DATABASE MOUNT;
~~~

MOUNT mở control file và gắn database vào instance; datafiles chưa được mở cho hoạt động thông thường.

### Open database

~~~sql
ALTER DATABASE OPEN;
~~~

OPEN đưa database vào trạng thái hoạt động bình thường theo role/mode hiện tại. Trong một số recovery scenario, cần các bước recovery trước khi open.

### Restricted session

Restricted session giới hạn đăng nhập cho user có privilege phù hợp. Cú pháp và privilege cần dùng phụ thuộc trạng thái database và phiên bản:

~~~sql
ALTER SYSTEM ENABLE RESTRICTED SESSION;
ALTER SYSTEM DISABLE RESTRICTED SESSION;
~~~

Không coi restricted session là cơ chế thay thế firewall, account lock hoặc maintenance window. Các phiên đã kết nối có thể vẫn tồn tại; xác định rõ session nào được phép hoạt động.

### RMAN với SYSBACKUP

Ví dụ kết nối target bằng tài khoản được cấp SYSBACKUP:

~~~text
rman target backup_operator@prod_service
~~~

RMAN có thể yêu cầu password hoặc Oracle Secure External Password Store. Dùng đúng privilege và authentication setup của phiên bản. Không dùng SYSDBA nếu tác vụ backup có thể hoàn thành bằng SYSBACKUP.

### Data Guard và ASM

Các công cụ như DGMGRL và SQL*Plus có thể dùng administrative privilege tương ứng cho Data Guard/ASM operations. Cú pháp cụ thể phụ thuộc tool và release. Không thực hiện lệnh ASM trên database service hoặc ngược lại; xác nhận service/instance trước khi thao tác.

## 18. CDB/PDB và phạm vi quyền

Trong kiến trúc multitenant, cần phân biệt CDB root, application root và PDB. Administrative connection có thể được thiết lập tới service của CDB hoặc PDB; user và quyền có thể mang scope common/local.

### Xác nhận container trước khi thao tác

~~~sql
SHOW CON_NAME;

SELECT name, cdb
FROM v$database;

SELECT sys_context('USERENV', 'CON_NAME') AS con_name,
       sys_context('USERENV', 'CON_ID') AS con_id
FROM dual;
~~~

### Common user và local user

- Common user được định nghĩa trong root và có thể tồn tại trong các container theo quy tắc common user.
- Local user chỉ tồn tại trong một PDB.
- Các administrative privileges có quy tắc grant/container scope riêng; cú pháp CONTAINER=CURRENT/ALL và đối tượng được phép cấp phụ thuộc release.
- Kết nối tới service khác có thể đưa session vào container khác dù username giống nhau.

Không copy lệnh GRANT SYSDBA/SYSBACKUP từ CDB root sang PDB mà chưa kiểm tra Oracle documentation cho đúng release. Xác nhận user type, container hiện tại, password file và service mà công cụ sẽ sử dụng.

### PDB lifecycle khác instance lifecycle

STARTUP/SHUTDOWN điều khiển instance/database container, còn việc mở/đóng PDB dùng ALTER PLUGGABLE DATABASE:

~~~sql
ALTER PLUGGABLE DATABASE salespdb OPEN;
ALTER PLUGGABLE DATABASE salespdb CLOSE IMMEDIATE;
~~~

Các thao tác PDB cần privilege và trạng thái CDB phù hợp. Không nhầm quyền quản trị instance với quyền quản trị một PDB hoặc quyền quản lý user trong PDB.

## 19. Lỗi thường gặp khi kết nối quản trị

| Lỗi/triệu chứng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| ORA-01017 invalid username/password | Credential sai, user chưa được thêm đúng vào password file hoặc xác thực không đúng service | Kiểm tra account, password file, privilege và service đích. |
| ORA-01031 insufficient privileges | Thiếu administrative privilege, OS group không đúng hoặc stored/tool context không đủ quyền | Xác nhận AS privilege, OS group, V$PWFILE_USERS và quyền hiệu lực. |
| ORA-28009 connection as SYS should be as SYSDBA or SYSOPER | Đang kết nối SYS mà không chỉ định administrative privilege phù hợp | Dùng CONNECT / AS SYSDBA hoặc kết nối tài khoản quản trị theo privilege đã cấp. |
| ORA-01994 GRANT failed: password file missing or disabled | Password file không tồn tại/không được bật hoặc REMOTE_LOGIN_PASSWORDFILE không phù hợp | Kiểm tra password file, tham số và cấu hình theo release. |
| ORA-01031 khi chạy lệnh quản trị với SYSOPER | Lệnh vượt phạm vi SYSOPER | Dùng privilege chuyên biệt đúng nhiệm vụ hoặc chuyển DBA được ủy quyền. |
| ORA-12514/ORA-12505 | Listener không nhận diện service/SID được yêu cầu | Kiểm tra connect descriptor, service registration và listener. |
| Kết nối / AS SYSDBA bị từ chối trên host | User OS không thuộc group OSDBA/OSASM phù hợp hoặc môi trường Oracle Home sai | Kiểm tra OS group, ORACLE_HOME, ORACLE_SID và cấu hình authentication. |
| Kết nối từ xa SYSDBA thất bại dù local thành công | Password file auth/network configuration chưa đúng | Kiểm tra REMOTE_LOGIN_PASSWORDFILE, password file, grants và listener/service. |
| User không xuất hiện trong V$PWFILE_USERS | Chưa được cấp admin privilege hoặc password file chưa đồng bộ | Cấp đúng privilege bằng account quản trị và xác nhận file trên instance/cluster. |
| SYSBACKUP không chạy được một lệnh SYSDBA | Tác vụ vượt quyền backup/recovery chuyên biệt | Xác định quyền tối thiểu cần thiết; không nâng SYSDBA theo thói quen. |
| ASM connection thất bại | Dùng database service thay vì ASM instance hoặc thiếu OSASM/SYSASM | Kết nối đúng ASM instance và xác nhận group/password file. |
| Admin session vào nhầm PDB | Dùng service hoặc container sai | Kiểm tra SHOW CON_NAME, CON_ID và service name trước thao tác. |

### Checklist chẩn đoán

1. Đang kết nối local hay remote?
2. Dùng OS authentication hay password file authentication?
3. User có đúng administrative privilege không?
4. OS group membership có đúng không?
5. REMOTE_LOGIN_PASSWORDFILE có cho phép password file authentication không?
6. Password file có đúng path, quyền OS và đúng instance/database không?
7. Listener/service có trỏ đúng CDB/PDB/ASM instance không?
8. Lệnh có nằm trong phạm vi privilege không?
9. Phiên bản Oracle có hỗ trợ privilege/cú pháp đó không?
10. Audit trail có ghi nhận lý do từ chối hoặc thay đổi không?

## 20. Bài thực hành: tạo và kiểm tra tài khoản SYSOPER

Bài lab cần một Oracle database riêng cho học tập và một DBA được ủy quyền để cấp quyền. Không thực hiện shutdown/startup trên database dùng chung hoặc production.

### Bước 1: xác nhận cấu hình

Kết nối bằng SYSDBA trong lab:

~~~sql
SHOW USER;
SHOW PARAMETER remote_login_passwordfile;

SELECT name, value
FROM v$parameter
WHERE name = 'remote_login_passwordfile';
~~~

Xác nhận password file authentication phù hợp nếu sẽ thử remote connection. Với local OS authentication, kiểm tra group mapping ở host.

### Bước 2: tạo tài khoản operator thử nghiệm

~~~sql
CREATE USER lab_operator IDENTIFIED BY "<password-from-secret-manager>";
GRANT SYSOPER TO lab_operator;
~~~

Đây là tài khoản lab; thay placeholder bằng secret được quản lý an toàn. Không dùng password ví dụ hoặc password thật trong script lưu trữ.

### Bước 3: kiểm tra password-file privilege

~~~sql
SELECT *
FROM v$pwfile_users
WHERE username = 'LAB_OPERATOR';
~~~

Nếu view không hiển thị user, kiểm tra quyền đã cấp, password file mode và cấu hình database. Một số release có cột khác nhau; dùng DESC để xem cấu trúc.

### Bước 4: kết nối bằng SYSOPER

Từ SQL*Plus/SQLcl:

~~~text
sqlplus lab_operator@lab_service as sysoper
~~~

Nhập password qua prompt hoặc cơ chế secure external password store. Xác nhận kết nối thành công:

~~~sql
SELECT sys_context('USERENV', 'ISDBA') AS isdba
FROM dual;
~~~

ISDBA phản ánh SYSDBA status; nó không phải phép kiểm tra duy nhất cho SYSOPER. Dùng kết quả kết nối và V$PWFILE_USERS để xác nhận privilege.

### Bước 5: hiểu giới hạn

Trong lab cô lập, thử một thao tác vận hành được hỗ trợ cho SYSOPER theo tài liệu release. Không chạy SHUTDOWN/STARTUP nếu instance còn phục vụ người khác. Thử truy vấn dữ liệu ứng dụng mà user không được grant riêng để quan sát giới hạn quyền; kết quả chính xác có thể là thiếu object privilege hoặc không truy cập được schema.

### Bước 6: thu hồi quyền

Kết nối lại bằng tài khoản quản trị được ủy quyền:

~~~sql
REVOKE SYSOPER FROM lab_operator;
DROP USER lab_operator;
~~~

Xác nhận user không còn trong V$PWFILE_USERS. DROP USER chỉ dùng sau khi chắc chắn đây là account lab và không sở hữu object cần giữ.

### Bước 7: mở rộng lab với SYSBACKUP

Trong môi trường lab riêng, có thể tạo account thứ hai và cấp SYSBACKUP:

~~~sql
CREATE USER lab_backup IDENTIFIED BY "<password-from-secret-manager>";
GRANT SYSBACKUP TO lab_backup;
~~~

Kiểm tra V$PWFILE_USERS và kết nối bằng AS SYSBACKUP. Thử các thao tác RMAN phù hợp trên database lab, sau đó revoke và drop account. Không cần cấp SYSDBA cho người học để làm bài backup.

## 21. Câu hỏi tự kiểm tra

1. **SYSDBA là gì?** Administrative privilege cho phép quản trị database/instance với phạm vi đặc quyền rộng nhất.
2. **SYSOPER khác SYSDBA thế nào?** SYSOPER chỉ cho phép một tập thao tác vận hành giới hạn; SYSDBA có toàn quyền quản trị database.
3. **SYSDBA có phải role DBA không?** Không; SYSDBA là administrative privilege, DBA là database role.
4. **SYS là gì?** Schema/user đặc biệt sở hữu data dictionary và các đối tượng hệ thống.
5. **Kết nối AS SYSDBA có ngữ nghĩa gì?** Phiên được kết nối với quyền SYSDBA và hoạt động trong ngữ cảnh SYS theo Oracle semantics.
6. **OS authentication là gì?** Xác thực administrative connection dựa trên user/group của host database.
7. **Password file dùng để làm gì?** Xác thực tài khoản có administrative privilege, đặc biệt cho remote admin connection.
8. **REMOTE_LOGIN_PASSWORDFILE điều khiển gì?** Việc database sử dụng password file authentication.
9. **V$PWFILE_USERS dùng để làm gì?** Xem các user và administrative privileges được ghi nhận trong password file.
10. **DBA_SYS_PRIVS có đủ để kiểm tra SYSDBA không?** Không; cần kiểm tra V$PWFILE_USERS và OS authentication configuration.
11. **SYSBACKUP phù hợp với ai?** Người thực hiện backup/recovery theo phạm vi privilege chuyên biệt.
12. **SYSDG dùng cho việc gì?** Các thao tác Oracle Data Guard.
13. **SYSKM dùng cho việc gì?** Quản lý encryption key/keystore.
14. **SYSASM dùng cho việc gì?** Quản trị ASM instance và disk groups.
15. **SYSRAC dùng cho việc gì?** Một số tác vụ quản trị chuyên biệt Oracle RAC.
16. **Vì sao không cấp SYSDBA cho backup operator?** SYSBACKUP có thể đáp ứng nhiệm vụ với phạm vi quyền nhỏ hơn.
17. **Vì sao không chia sẻ user SYS?** Khó quy trách nhiệm cá nhân và thu hồi quyền theo người.
18. **OSDBA membership có nhạy cảm không?** Có; thành viên thường có thể xác thực SYSDBA cục bộ.
19. **SYSOPER có quyền đọc mọi bảng ứng dụng không?** Không; quyền vận hành không đồng nghĩa quyền truy cập dữ liệu tùy ý.
20. **Trong CDB/PDB cần xác nhận gì?** Container/service, common/local user và scope của privilege.
21. **Tại sao phải audit administrative operations?** Vì chúng có thể thay đổi database state, quyền và dữ liệu nhạy cảm.
22. **Nếu SYSOPER gặp lệnh ngoài phạm vi thì xử lý thế nào?** Xác định privilege tối thiểu cần thiết và chuyển cho operator/DBA phù hợp; không tự động nâng SYSDBA.
23. **Password file cần được bảo vệ ra sao?** Giới hạn quyền OS, quản lý secret/rotation, không đưa vào source control và đồng bộ theo quy trình.

SYSDBA và SYSOPER là administrative privileges, không phải role thông thường. SYSDBA dành cho quản trị database toàn diện; SYSOPER giới hạn ở các tác vụ vận hành. SYSBACKUP, SYSDG, SYSKM, SYSASM và SYSRAC phân tách quyền theo backup, Data Guard, encryption key, ASM và RAC. Hãy xác thực qua OS groups hoặc password file được bảo vệ, kiểm tra quyền bằng V$PWFILE_USERS, audit mọi phiên đặc quyền và cấp đúng privilege nhỏ nhất cho từng nhiệm vụ. Trong môi trường CDB/PDB hoặc RAC, luôn xác nhận đúng container, service, instance và scope trước khi chạy lệnh quản trị.
