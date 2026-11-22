# Cài đặt và khởi tạo database bằng công cụ phù hợp với bản Oracle

> **Chủ đề:** Database Engine Relational Oracle  
> **Chương:** Môi trường thực hành  
> **Đích đến:** Cài đặt một Oracle Database có thể kết nối, xác định đúng container/PDB, tạo schema riêng và chạy được một truy vấn SQL đầu tiên.

## 1. Phân biệt cài đặt phần mềm và khởi tạo database

Trong Oracle, **cài đặt Oracle Database** và **tạo một database** là hai việc liên quan nhưng không đồng nghĩa:

1. **Cài đặt phần mềm máy chủ (database software):** đưa các chương trình, thư viện và công cụ Oracle vào máy. Thư mục cài đặt thường được gọi là `ORACLE_HOME`.
2. **Khởi tạo database:** tạo các tệp dữ liệu, control file, redo log, cấu hình instance, tài khoản quản trị và dịch vụ kết nối.
3. **Khởi động và mở database:** cho instance chạy, mở database và PDB để chấp nhận truy vấn.
4. **Tạo schema thực hành:** tạo người dùng riêng có quyền vừa đủ để làm bài, thay vì dùng `SYS`/`SYSTEM` cho mọi thao tác.

Từ Oracle Database 12c, kiến trúc **multitenant** sử dụng:

- **CDB (Container Database):** cơ sở dữ liệu chứa tầng quản trị chung, có root container `CDB$ROOT`.
- **PDB (Pluggable Database):** cơ sở dữ liệu có thể cắm vào CDB, là nơi thường đặt schema, bảng và dữ liệu ứng dụng.
- **Instance:** tập hợp tiến trình và bộ nhớ phục vụ database; `SID` xác định instance tại máy chủ.
- **Listener:** tiến trình nhận kết nối mạng, thông thường lắng nghe cổng TCP `1521`.
- **Service name:** tên dịch vụ mà client dùng để truy cập đúng database/PDB; khác với `SID`.

Ví dụ cài đặt mặc định Oracle AI Database 26ai Free:

```text
Máy tính / máy ảo / container
└── Oracle Database instance: SID = FREE
    └── CDB: FREE
        ├── CDB$ROOT        ← quản trị CDB
        ├── PDB$SEED        ← khuôn mẫu hệ thống, không lưu dữ liệu bài tập
        └── FREEPDB1        ← tạo user, bảng và dữ liệu thực hành tại đây

Client ── TCP localhost:1521 ── Listener ── service FREEPDB1
```

**Hệ quả quan trọng:** Kết nối vào service `FREE` thường đưa bạn đến `CDB$ROOT`, còn `FREEPDB1` đưa bạn đến PDB thực hành. Tạo tài khoản ứng dụng nhầm trong root dễ gặp lỗi `ORA-65096`.

## 2. Chọn công cụ dựa trên phiên bản và môi trường

| Trường hợp | Công cụ cài đặt/khởi tạo phù hợp | Database/PDB mặc định hoặc cần xác định |
|---|---|---|
| **Oracle AI Database 26ai Free** (học tập, phát triển) | Trình cài Windows; gói RPM + script `oracle-free-26ai configure` trên Linux; hoặc container Docker/Podman | `FREE` / `FREEPDB1` |
| **Oracle Database 23ai Free** | Trình cài theo hệ điều hành, RPM + `oracle-free-23ai configure` hoặc container tương ứng | `FREE` / `FREEPDB1` |
| **Oracle Database 21c XE**, **18c XE** | Bộ cài XE và công cụ cấu hình đi kèm; theo hướng dẫn đúng bản | `XE` / `XEPDB1` |
| **Oracle Database 19c**, 21c, 23ai/26ai bản Enterprise/Standard | Oracle Universal Installer (hoặc gói triển khai được tài liệu hỗ trợ), sau đó **Database Configuration Assistant (DBCA)** để tạo CDB/PDB | Tên tự chọn, ví dụ `ORCL` / `ORCLPDB1` |
| **Database ở máy chủ khác hoặc Oracle Cloud** | Không cần cài database server trên laptop; chỉ cần SQL Developer, SQLcl, SQL*Plus hoặc JDBC client và thông tin truy cập | Dùng **service name thực tế** do quản trị viên cung cấp |

`SQL Developer` là công cụ đồ họa để kết nối và chạy SQL; `SQLcl` và `SQL*Plus` là công cụ dòng lệnh. Chúng **không thay thế bộ cài server hay DBCA**. Ngược lại, DBCA chủ yếu dùng để tạo/quản trị database; DBCA không phải công cụ viết SQL thường ngày.

> **Lựa chọn khuyến nghị cho bài lab mới:** Oracle AI Database **26ai Free** trên Docker/Podman nếu máy đã có môi trường container; hoặc cài bản **26ai Free** trực tiếp trên Windows/Oracle Linux được hỗ trợ. Nếu môn học hoặc dự án quy định 19c/21c, hãy giữ đúng phiên bản đó và dùng bộ công cụ của chính phiên bản đó. Đừng thay tên `XE` bằng `FREE` một cách máy móc.

### Điều kiện cần chuẩn bị

- Kiểm tra **hệ điều hành, kiến trúc CPU, RAM, dung lượng lưu trữ và quyền quản trị** theo tài liệu cho đúng phiên bản. Oracle AI Database 26ai Free có giới hạn tài nguyên/khả năng sử dụng của bản Free; máy phải có thêm tài nguyên cho chính hệ điều hành và công cụ học tập.
- Tải bộ cài từ [Oracle AI Database Free](https://www.oracle.com/database/free/) và đối chiếu tài liệu [Oracle Database 26ai — Install](https://docs.oracle.com/en/database/oracle/oracle-database/26/install.html). Không dùng một tệp RPM/installer của hệ điều hành hoặc kiến trúc khác.
- Kiểm tra cổng `1521` (hoặc chọn cổng host khác), đủ chỗ cho **tệp dữ liệu** và **nhật ký**, mạng ổn định khi tải image/bộ cài.
- Chuẩn bị mật khẩu mạnh, riêng cho bài lab. Các ví dụ sử dụng tài khoản quản trị chỉ khi cấu hình; công việc SQL hằng ngày sẽ dùng `LAB_ORACLE`.
- Nếu máy đã có bản XE/Free, dịch vụ Oracle hoặc dữ liệu cũ, **sao lưu trước** và kiểm tra xung đột `SID`, cổng, tên dịch vụ. Không cài đè hay xóa bản cũ chỉ để chạy ví dụ.

## 3. Cách A — Chạy Oracle AI Database 26ai Free bằng Docker

Đường đi này phù hợp với Windows có Docker Desktop, Linux có Docker Engine hoặc macOS có môi trường container tương thích. Ví dụ lệnh bên dưới dùng **Bash** (Linux, macOS hoặc WSL). Với Podman, thay `docker` bằng `podman` khi môi trường hỗ trợ cú pháp tương ứng.

### 3.1. Tạo volume và chạy image chính thức

Kiểm tra Docker đang hoạt động:

```bash
docker version
```

Đặt mật khẩu quản trị vào biến môi trường mà không gõ trực tiếp vào dòng lệnh `docker run`:

```bash
read -r -s -p "Mat khau moi cho SYS/SYSTEM/PDBADMIN: " ORACLE_PWD
echo
export ORACLE_PWD
```

Sau đó chạy:

```bash
docker volume create oracle-free-data
docker pull container-registry.oracle.com/database/free:latest

docker run -d \
  --name oracle-free \
  -p 127.0.0.1:1521:1521 \
  -e ORACLE_PWD \
  -v oracle-free-data:/opt/oracle/oradata \
  container-registry.oracle.com/database/free:latest

unset ORACLE_PWD
```

Ý nghĩa:

- `--name oracle-free`: tên container dùng trong các lệnh tiếp theo.
- `-p 127.0.0.1:1521:1521`: ánh xạ cổng 1521 về **localhost của máy host**, hạn chế truy cập từ mạng ngoài.
- `-e ORACLE_PWD`: chuyển biến môi trường đã đặt cho quá trình khởi tạo; mật khẩu sẽ được thiết lập cho các tài khoản quản trị mặc định. Với môi trường dùng lâu dài, ưu tiên cơ chế **secret** của runtime thay cho biến môi trường.
- `-v oracle-free-data:/opt/oracle/oradata`: giữ dữ liệu trong named volume khi container dừng hoặc được tạo lại đúng cách.
- `:latest`: lấy image Free hiện hành; dùng **tag phiên bản cụ thể** nếu khóa phiên bản để tái hiện môi trường hoặc làm bài theo giáo trình cũ.

**Lần chạy đầu** sẽ tạo database và có thể cần một khoảng thời gian tùy máy. Theo dõi log:

```bash
docker logs -f oracle-free
```

Khi thấy thông báo đại ý `DATABASE IS READY TO USE!`, database đã sẵn sàng. Thoát chế độ theo dõi log bằng `Ctrl+C`; việc này không dừng database.

> Nếu cổng host 1521 đang được dùng, đổi tham số thành `-p 127.0.0.1:1522:1521` và dùng cổng **1522** trong mọi cấu hình kết nối từ host. Cổng bên trong container vẫn là 1521.

### 3.2. Đăng nhập thử vào PDB

Có thể dùng SQL*Plus đã có sẵn trong container:

```bash
docker exec -it oracle-free sqlplus system@//localhost:1521/FREEPDB1
```

Nhập mật khẩu `SYSTEM` đã đặt khi tạo container; không gắn mật khẩu trực tiếp vào connect string lưu trong lịch sử shell. Trong dấu nhắc `SQL>`, chạy:

```sql
SHOW CON_NAME;

SELECT SYS_CONTEXT('USERENV', 'CON_NAME') AS current_pdb
FROM dual;

EXIT;
```

Kết quả của `SHOW CON_NAME` hoặc `CURRENT_PDB` phải là `FREEPDB1`. Nếu không, xem lại **service name** đã kết nối.

### 3.3. Dừng và chạy lại

```bash
docker stop oracle-free
docker start oracle-free
docker ps --filter name=oracle-free
```

Việc dừng container không xóa named volume. **Không xóa volume** nếu cần giữ dữ liệu. Nếu cần dùng từ client trên host, kết nối `localhost:1521/FREEPDB1`.

## 4. Cách B — Cài trực tiếp Oracle AI Database 26ai Free trên Windows

Đây là đường đi phù hợp khi muốn server Oracle chạy như một dịch vụ Windows.

1. Đọc [Hướng dẫn cài 26ai Free cho Windows](https://docs.oracle.com/en/database/oracle/oracle-database/26/xeinw/). Kiểm tra hệ điều hành 64-bit và quyền **Administrator**; xem các biến `ORACLE_HOME`, `TNS_ADMIN` và những bản Oracle đã cài trước đó để tránh xung đột.
2. Tải gói **Oracle AI Database 26ai Free for Windows** từ trang chính thức, giải nén và chạy `setup.exe` bằng tài khoản có quyền quản trị.
3. Thực hiện các bước trong wizard: chọn thư mục cài, xác nhận điều kiện cài và đặt mật khẩu quản trị theo yêu cầu. Dùng thư mục được wizard đề xuất hoặc vị trí có quyền truy cập đáp ứng yêu cầu của Oracle.
4. Chờ trình cài hoàn tất. Với bản Free này, quá trình thiết lập sẽ tạo sẵn CDB `FREE`, PDB `FREEPDB1` và listener theo cấu hình mặc định. Ghi lại thông tin kết nối hiển thị ở màn hình hoàn tất.
5. Mở `services.msc`, kiểm tra dịch vụ **`OracleServiceFREE`**. Dịch vụ listener có tên theo Oracle Home, ví dụ dạng `OracleOraDB26Home<n>TNSListener`; số `<n>` thay đổi theo máy.
6. Dùng SQL Developer hoặc SQL*Plus kết nối tới `localhost:1521/FREEPDB1` bằng `SYSTEM`, rồi chuyển sang tài khoản riêng cho bài thực hành ở mục 7.

Nếu database ở trạng thái dừng, mở `services.msc` để khởi động `OracleServiceFREE` và listener tương ứng. Với database khởi chạy nhưng PDB chưa mở, sử dụng câu lệnh `ALTER PLUGGABLE DATABASE` ở mục 8.

**Lưu ý:** Trình cài **Free** tự tạo database mặc định; không chạy DBCA tạo thêm một database chỉ vì thấy có công cụ DBCA trên hệ thống.

## 5. Cách C — Cài trực tiếp 26ai Free trên Oracle Linux

Ví dụ này dành cho **Oracle Linux 9 x86-64** sử dụng Bash và `dnf`. Các bản Oracle Linux/RHEL, hệ điều hành và kiến trúc khác phải dùng đúng RPM/preinstall theo hướng dẫn phiên bản tương ứng.

### 5.1. Cài phần mềm

Trên Oracle Linux có kho RPM thích hợp:

```bash
sudo dnf install -y oracle-ai-database-preinstall-26ai
```

Tải **RPM Oracle AI Database Free 26ai cho Oracle Linux 9 x86-64** từ trang Oracle, đặt trong thư mục hiện tại rồi cài:

```bash
sudo dnf install -y ./oracle-ai-database-free-26ai-*.el9.x86_64.rpm
```

Tên tệp có phần phiên bản cụ thể thay đổi theo bản phát hành. Trước khi cài, xác nhận chỉ có **một RPM phù hợp** khớp với mẫu trên. Với RHEL, cách cài gói preinstall có thể khác Oracle Linux.

### 5.2. Khởi tạo database sau khi cài RPM

Xem trước cấu hình khởi tạo:

```bash
sudo cat /etc/sysconfig/oracle-free-26ai.conf
```

Chạy **script cấu hình của đúng phiên bản**:

```bash
sudo /etc/init.d/oracle-free-26ai configure
```

Script hỏi mật khẩu quản trị và tạo:

- CDB/`SID`: `FREE`.
- PDB: `FREEPDB1`.
- Listener: mặc định cổng `1521`.

Kiểm tra/trợ giúp vận hành:

```bash
sudo /etc/init.d/oracle-free-26ai status
sudo systemctl start oracle-free-26ai
sudo systemctl enable oracle-free-26ai
```

`start` khởi động dịch vụ; `enable` thiết lập khởi động theo hệ điều hành. Khi cần dừng có chủ đích, dùng `sudo systemctl stop oracle-free-26ai`.

### 5.3. Thiết lập môi trường và kết nối quản trị cục bộ

Chuyển sang người dùng hệ điều hành `oracle`, rồi thiết lập Oracle Home:

```bash
sudo su - oracle
export ORACLE_SID=FREE
export ORACLE_HOME=/opt/oracle/product/26ai/dbhomeFree
export ORAENV_ASK=NO
. "$ORACLE_HOME/bin/oraenv"
sqlplus / as sysdba
```

`sqlplus / as sysdba` dựa trên xác thực hệ điều hành tại server; nó thường kết nối vào `CDB$ROOT`. **Không** dùng cú pháp này như kết nối thông thường từ laptop đến database ở máy khác.

Trong SQL*Plus:

```sql
SELECT name, open_mode FROM v$pdbs;
SHOW CON_NAME;
EXIT;
```

Nếu học trên Oracle **23ai Free**, thay đường dẫn, RPM và script bằng tên **`23ai`** tương ứng, ví dụ `/etc/init.d/oracle-free-23ai configure`. Không trộn RPM 23ai với script 26ai.

## 6. Cách D — Oracle Database 19c/21c Enterprise hoặc Standard với DBCA

Với bản máy chủ Oracle cài qua **Oracle Universal Installer (OUI)**, việc cài các tệp chương trình và tạo database có thể tách thành hai giai đoạn. DBCA là công cụ thích hợp để tạo database theo từng bước.

1. Chuẩn bị máy chủ đúng ma trận hỗ trợ hệ điều hành/phần cứng và quyền cài. Cài Oracle Database software theo bộ cài chính thức, chọn chế độ chỉ cài phần mềm nếu muốn tạo database về sau.
2. Mở **Database Configuration Assistant** (ví dụ chạy `dbca` từ Oracle Home trên môi trường có giao diện), chọn **Create a database**.
3. Chọn cấu hình **Typical** hoặc **Advanced**. Với bài học về Oracle multitenant, nên tạo **CDB chứa ít nhất một PDB**, nếu lựa chọn đó có trong bản/cấu hình đang dùng.
4. Chọn tên toàn cục và `SID`, ví dụ `ORCL`; đặt tên PDB rõ ràng, ví dụ `ORCLPDB1`. Cấu hình nơi lưu datafile, bộ ký tự (thường `AL32UTF8` cho bài lab mới), bộ nhớ và listener phù hợp.
5. Đặt mật khẩu quản trị, kiểm tra trang **Summary**, chọn **Create database**, chờ kết quả từ DBCA. Ghi lại `SID`, tên PDB, cổng listener và đường dẫn log được thông báo.
6. Dùng SQL*Plus/SQL Developer đăng nhập vào service của **PDB đã tạo**, chẳng hạn `localhost:1521/ORCLPDB1`, rồi tạo schema bài tập.

Trong DBCA, các tên `ORCL` và `ORCLPDB1` chỉ là **ví dụ**, không phải tên cố định của Oracle 19c. Cấu hình thật có thể khác. Bản quyền và quyền sử dụng của Enterprise/Standard phải phù hợp với môi trường triển khai.

**Riêng XE 18c/21c:** bộ cài Express Edition thường khởi tạo sẵn `XE`/`XEPDB1`. Dùng tài liệu XE đúng phiên bản, kết nối theo service `XEPDB1` để làm bài; không tự giả định chúng có service `FREEPDB1`.

## 7. Tạo schema riêng để thực hành

Sau khi cài đặt thành công, tạo người dùng riêng trong **PDB**. Ví dụ dưới đây giả định service `FREEPDB1` của 26ai/23ai Free và truy cập từ máy có database hoặc client Oracle.

Đầu tiên đăng nhập bằng tài khoản quản trị `SYSTEM`:

```bash
sqlplus system@//localhost:1521/FREEPDB1
```

Nếu client chạy ngoài máy chủ, thay `localhost` bằng tên/IP của máy chủ; nếu cổng host đổi thành 1522, thay số cổng tương ứng. Nhập mật khẩu tại prompt.

Xác nhận đã ở PDB đúng:

```sql
SHOW CON_NAME;
```

Chỉ tiếp tục khi kết quả là `FREEPDB1` (hoặc PDB thực tế mà bạn được giao). Tạo user và cấp quyền tối thiểu:

```sql
CREATE USER LAB_ORACLE
  IDENTIFIED BY "ThayBangMatKhauManh_2026"
  DEFAULT TABLESPACE USERS
  QUOTA 100M ON USERS;

GRANT CREATE SESSION, CREATE TABLE TO LAB_ORACLE;
```

**Phải thay mật khẩu minh họa** bằng mật khẩu riêng. Chạy lệnh tạo user trên PDB do bạn kiểm soát; với server của lớp học, xác nhận bạn được phép tạo user trước. Nếu tablespace bài tập không mang tên `USERS`, chọn tablespace được quản trị viên cấp cho bạn. Không cấp `DBA` hoặc `SYSDBA` cho user lab.

Thoát rồi đăng nhập bằng tài khoản vừa tạo:

```bash
sqlplus lab_oracle@//localhost:1521/FREEPDB1
```

Chạy thử bộ lệnh:

```sql
SELECT USER AS current_user FROM dual;

SELECT SYS_CONTEXT('USERENV', 'CON_NAME') AS current_pdb
FROM dual;

CREATE TABLE bai_hoc (
    id       NUMBER GENERATED BY DEFAULT ON NULL AS IDENTITY PRIMARY KEY,
    ten      VARCHAR2(100 CHAR) NOT NULL,
    ngay_tao DATE DEFAULT SYSDATE NOT NULL
);

INSERT INTO bai_hoc (ten) VALUES ('Oracle Database lab');
COMMIT;

SELECT id, ten, ngay_tao
FROM bai_hoc
ORDER BY id;
```

Nếu nhận được một bản ghi vừa chèn, bạn đã xác minh được **kết nối PDB → xác thực user → quyền tạo bảng → ghi và đọc dữ liệu**.

> `CREATE USER` tạo một **schema trong PDB hiện có**; nó không tạo một Oracle database/CDB mới. Đây là phân biệt quan trọng trong bài "khởi tạo database".

## 8. Kết nối bằng SQL Developer, SQLcl, SQL*Plus và JDBC

Một database server có thể được truy cập từ nhiều công cụ client. Với Oracle 26ai Free khởi tạo theo mặc định, thông số cho **schema `LAB_ORACLE`**:

| Thuộc tính | Giá trị minh họa | Ghi chú |
|---|---|---|
| Username | `LAB_ORACLE` | User vừa tạo tại `FREEPDB1` |
| Password | Mật khẩu đã đặt cho `LAB_ORACLE` | Không dùng mật khẩu `SYS`/`SYSTEM` |
| Hostname | `localhost` | Nếu client cùng máy host; từ máy khác dùng địa chỉ máy chủ thực |
| Port | `1521` | Hoặc `1522` nếu ánh xạ container như ví dụ |
| Connection type | `Basic` trong SQL Developer | Kết nối trực tiếp qua host/port |
| Connection identifier | **Service name: `FREEPDB1`** | Không chọn SID `FREE` thay cho service PDB |
| Role | `Default` | User bài thực hành không dùng `SYSDBA` |

Trong **SQL Developer**, tạo *New Database Connection*, điền các trường trên, bấm **Test** rồi **Connect**. Nếu kết nối máy chủ chạy trong Docker từ laptop, dùng địa chỉ/cổng **đã ánh xạ ở host**.

Trong **SQLcl**:

```bash
sql lab_oracle@localhost:1521/FREEPDB1
```

Trong **SQL*Plus**:

```bash
sqlplus lab_oracle@//localhost:1521/FREEPDB1
```

Trong ứng dụng **Java JDBC Thin**, service-style URL thường là:

```text
jdbc:oracle:thin:@//localhost:1521/FREEPDB1
```

Ví dụ thiết lập Java:

```java
String url = "jdbc:oracle:thin:@//localhost:1521/FREEPDB1";
String username = "LAB_ORACLE";
// Lấy password từ cấu hình bảo mật/biến môi trường, không hard-code trong source.
String password = System.getenv("ORACLE_LAB_PASSWORD");

try (java.sql.Connection conn =
         java.sql.DriverManager.getConnection(url, username, password);
     java.sql.PreparedStatement ps =
         conn.prepareStatement("SELECT COUNT(*) FROM bai_hoc");
     java.sql.ResultSet rs = ps.executeQuery()) {
    if (rs.next()) {
        System.out.println("So bai hoc: " + rs.getInt(1));
    }
}
```

Ứng dụng cần Oracle JDBC driver phù hợp với phiên bản Java và máy chủ. Nếu service là `XEPDB1` hoặc `ORCLPDB1`, sửa **service name** trong tất cả kết nối trên.

## 9. Xác minh trạng thái database sau khi khởi tạo

Đăng nhập bằng tài khoản có quyền quản trị phù hợp trên server, chẳng hạn `sqlplus / as sysdba` của người dùng OS `oracle` trên Linux. Kiểm tra:

```sql
SELECT instance_name, status FROM v$instance;

SELECT name, open_mode FROM v$database;

SELECT name, open_mode FROM v$pdbs;

SHOW CON_NAME;
```

Cần hiểu kết quả:

- `v$instance.status` thường là `OPEN` khi instance/database hoạt động bình thường.
- `v$database.open_mode` là `READ WRITE` cho database đang mở ghi/đọc.
- PDB thực hành phải có `OPEN_MODE = READ WRITE`; `PDB$SEED` thường là `READ ONLY`.
- Khi kiểm tra quyền/schema, quay lại kết nối **LAB_ORACLE vào đúng PDB** và chạy `SELECT USER FROM dual;`.

Nếu PDB cần mở sau khi khởi động lại, ở `CDB$ROOT` với quyền `SYSDBA`:

```sql
ALTER PLUGGABLE DATABASE FREEPDB1 OPEN;
ALTER PLUGGABLE DATABASE FREEPDB1 SAVE STATE;
```

Chỉ chạy lệnh `OPEN` khi PDB đang đóng (ví dụ `MOUNTED`); khi PDB đã mở thì không cần mở thêm. `SAVE STATE` lưu trạng thái mở để PDB tự mở ở những lần khởi động CDB tiếp theo, trên phiên bản hỗ trợ. Thay `FREEPDB1` bằng tên PDB thực tế nếu dùng phiên bản khác.

Kiểm tra listener trên máy chủ:

```bash
lsnrctl status
```

Với Docker, xem thêm `docker ps` và `docker logs oracle-free`. Trạng thái container "running" chỉ khẳng định process đang chạy; **chưa đủ** chứng minh PDB đã mở và sẵn sàng nhận kết nối.

## 10. Lỗi thường gặp và cách xác định nguyên nhân

| Triệu chứng | Nguyên nhân cần kiểm tra | Hướng xử lý |
|---|---|---|
| Không kết nối được, `ORA-12541` | Listener không chạy; host/port sai; cổng host không ánh xạ | Kiểm tra `lsnrctl status`, `docker ps`, dịch vụ Oracle và cổng thực tế |
| `ORA-12514` | Service `FREEPDB1`/`XEPDB1` sai, chưa đăng ký hoặc PDB chưa mở | Kiểm tra `lsnrctl status`, `SELECT name, open_mode FROM v$pdbs`; mở PDB khi cần |
| `ORA-01017` | Sai username/password, nhầm CDB/PDB, nhầm môi trường | Dùng đúng service, nhập lại thông tin và xác nhận user tồn tại trong PDB |
| `ORA-65096` khi `CREATE USER` | Đang tạo local user ở `CDB$ROOT` | Kết nối service PDB trước khi chạy `CREATE USER` |
| `ORA-01950` khi tạo/chèn bảng | User chưa có quota trên tablespace | Cấp quota phù hợp trong PDB, ví dụ `ALTER USER LAB_ORACLE QUOTA 100M ON USERS` |
| `ORA-01031` | User thiếu quyền thực hiện thao tác | Cấp đúng quyền cần thiết, tránh cấp `DBA` cho mục đích học |
| Docker báo `port is already allocated` | Host port 1521 bị chiếm | Đổi host port, ví dụ `127.0.0.1:1522:1521`; sửa cấu hình client |
| SQL Developer test thất bại nhưng SQL*Plus cục bộ chạy | Khác máy, mạng/firewall, service name hoặc client cấu hình SID | Kiểm tra địa chỉ host, ánh xạ port, chính sách mạng và **Service name** |
| Container khởi động lại mất dữ liệu | Đã tạo container không có volume ổn định hoặc kết nối nhầm container | Kiểm tra volume gắn với `/opt/oracle/oradata` và tên container trước khi thao tác |

**Nguyên tắc chẩn đoán:** Kiểm tra theo thứ tự **server/container chạy → listener chạy → service đăng ký → PDB mở → username/password → quyền trên schema**. Thứ tự này giúp tránh sửa quyền SQL khi lỗi gốc là kết nối mạng.

## 11. Đầu ra mong đợi của bài thực hành

Khi kết thúc, người học phải có thể mô tả và tự chứng minh các điểm sau:

1. Ghi rõ **phiên bản/edition Oracle**, hệ điều hành, cách cài (Docker, Windows installer, Linux RPM hoặc DBCA), tên **SID/CDB/PDB**, hostname và port.
2. Kết nối bằng **service của PDB**, không nhầm root CDB; xác minh bằng `SHOW CON_NAME`.
3. Tạo `LAB_ORACLE` trong PDB với quyền `CREATE SESSION`, `CREATE TABLE` và quota giới hạn.
4. Tạo bảng `BAI_HOC`, chèn một dòng, `COMMIT` và truy vấn đọc thành công.
5. Biết khởi động/dừng database theo công cụ tương ứng và xác định vị trí xem log khi kết nối lỗi.

Kết quả này là môi trường nền để học tiếp bảng, khóa, ràng buộc, JOIN, transaction, index, optimizer và quản trị Oracle cơ bản.

## Tài liệu chính thức nên đối chiếu

- [Oracle AI Database 26ai Free — tải và bắt đầu](https://www.oracle.com/database/free/get-started/)
- [Oracle AI Database 26ai Free — hướng dẫn Linux](https://docs.oracle.com/en/database/oracle/oracle-database/26/xeinl/)
- [Oracle AI Database 26ai Free — hướng dẫn Windows](https://docs.oracle.com/en/database/oracle/oracle-database/26/xeinw/)
- [Oracle AI Database Free — kết nối bằng service FREE/FREEPDB1](https://docs.oracle.com/en/database/oracle/oracle-database/26/xeinl/connecting-to-oracle-ai-database-free.html)
- [Oracle Database 19c — tạo database bằng DBCA](https://docs.oracle.com/en/database/oracle/oracle-database/19/admqs/installing-oracle-database-creating-database.html)
- [Oracle Database Free — container image trên Oracle Container Registry](https://container-registry.oracle.com/)

Các tên script, dịch vụ Windows, đường dẫn `ORACLE_HOME` và phiên bản image/RPM phụ thuộc **bản Oracle và hệ điều hành**. Khi tài liệu của phiên bản bạn cài khác ví dụ trong bài, hãy ưu tiên hướng dẫn của chính phiên bản đó.

