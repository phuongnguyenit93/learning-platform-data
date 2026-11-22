# Phân biệt SID, SERVICE_NAME và tên kết nối TNS trong Oracle Database

Khi tạo kết nối trong SQL Developer, SQLcl, SQL*Plus, DBeaver hoặc ứng dụng Java, bạn thường gặp các ô **SID**, **Service name** và **TNS name**. Chúng có vẻ giống nhau vì đều xuất hiện trong thông tin kết nối Oracle, nhưng thực chất chỉ đến **ba cấp khác nhau**: một *instance*, một *dịch vụ cơ sở dữ liệu* và một *tên dùng để tra cứu cấu hình kết nối ở phía client*.

Nhầm lẫn ba khái niệm này là nguyên nhân phổ biến của những lỗi như `ORA-12505`, `ORA-12514` hoặc `ORA-12154`. Bài học giúp bạn hiểu đường đi của kết nối Oracle Net, chọn đúng loại định danh và tự chẩn đoán sự cố thay vì thử ngẫu nhiên nhiều tên.

Sau bài học, bạn có thể:

- Giải thích SID khác `SERVICE_NAME` ở cấp instance, database, container database (CDB) và pluggable database (PDB).
- Hiểu tên TNS trong `tnsnames.ora` là alias phía client và biết nó trỏ đến host, port, service hoặc SID như thế nào.
- Viết và đọc chuỗi kết nối dạng Easy Connect, TNS alias và dạng SID cũ.
- Chọn đúng kiểu kết nối trong SQL Developer và JDBC Thin.
- Kiểm tra tên thực tế trên server, nhận biết loại lỗi và sửa đúng lớp bị sai.

> Trong tài liệu này, từ **TNS alias** chỉ *net service name/alias* được định nghĩa bởi cơ chế local naming, thường là một mục trong `tnsnames.ora`. TNS là tên lịch sử gắn với hệ thống mạng Oracle; nó không đồng nghĩa với một SID hay service của database.

## 1. Một kết nối Oracle đi qua những thành phần nào?

Xét một máy cá nhân có SQL Developer và một Oracle Database Free đang mở cổng `1521`:

```text
SQL Developer / SQL*Plus / ứng dụng Java
        │
        │  Connect identifier:
        │    //127.0.0.1:1521/FREEPDB1
        │          hoặc ORACLE_LAB (TNS alias)
        ▼
Oracle Net phía client
        │  Phân giải thành địa chỉ + CONNECT_DATA
        ▼
127.0.0.1:1521 ──TCP──► Oracle Listener
                              │
                              │ tìm service được yêu cầu: FREEPDB1
                              ▼
                      Instance Oracle đang phục vụ
                              │
                              ▼
                         PDB FREEPDB1
```

Ở ví dụ trên:

- `127.0.0.1` là **host**, không phải SID hoặc service.
- `1521` là **cổng TCP của listener**; cổng có thể đổi theo cấu hình.
- `FREEPDB1` là **service name** dùng để truy cập PDB trong cấu hình Oracle Database Free thường gặp; phải kiểm tra tên thực tế ở môi trường của bạn.
- `ORACLE_LAB` là **alias tự đặt trên máy client**, nếu bạn đã khai báo nó trong cấu hình TNS.
- SID là tên của **instance** đã đăng ký với listener; SID có thể không xuất hiện trong chuỗi kết nối bằng service.

**Listener không kiểm tra mật khẩu thay cho database.** Nó tiếp nhận kết nối mạng và chuyển đến instance/handler phù hợp dựa trên thông tin dịch vụ hoặc SID. Việc xác thực người dùng và quyền trên schema diễn ra ở phía database.

## 2. SID: định danh một Oracle instance

### 2.1. Instance khác database

Trong Oracle, cần phân biệt:

| Khái niệm | Bản chất | Ví dụ minh họa |
| --- | --- | --- |
| **Database** | Tập dữ liệu và các tệp vật lý như datafiles, control files, redo logs | Một cơ sở dữ liệu Oracle lưu dữ liệu bán hàng |
| **Instance** | Các cấu trúc bộ nhớ (như SGA) và tiến trình nền dùng để truy cập, quản lý database | Instance `ORCL1` |
| **SID** (*System Identifier*) | Tên định danh của instance Oracle trên một host | `ORCL1` |
| **DB_NAME** | Tên database được cấu hình ở cấp database | `ORCL` |

Trong mô hình đơn instance, tên database và SID đôi khi được đặt **giống nhau** nên người học dễ tưởng chúng là một khái niệm. Sự trùng tên đó chỉ là quyết định cấu hình. **DB_NAME không phải định nghĩa của SID.**

Ví dụ trên một server có:

```text
Database: ORCL
     ▲
     │ được mở và quản lý bởi
Instance: ORCL1
SID: ORCL1
```

Thông tin SID đặc biệt hữu ích cho vận hành instance: tiến trình hệ điều hành, cấu hình local database, phân biệt nhiều instance cùng chạy trên một máy, hoặc các bài quản trị cần chỉ định instance.

Trên Oracle Linux, biến môi trường `ORACLE_SID` thường được dùng bởi một số tiện ích/quy trình quản trị **kết nối cục bộ** để chọn instance:

```bash
export ORACLE_SID=ORCL1
sqlplus / as sysdba
```

Ví dụ này chỉ có ý nghĩa khi tài khoản OS và cơ chế xác thực cục bộ được cấu hình phù hợp trên máy database. **Đặt `ORACLE_SID` trên laptop client không tự tạo kết nối TCP đến một server từ xa.**

### 2.2. SID trong môi trường nhiều instance

Với Oracle Real Application Clusters (RAC), một database có thể được truy cập qua nhiều instance:

```text
                Database SALES
                  /         \
            Instance 1    Instance 2
            SID SALES1    SID SALES2
```

Trong kiến trúc này, SID gắn với **một instance cụ thể**, còn client ứng dụng thường nên kết nối bằng **service** được quản lý trên cluster. Service có thể được cung cấp bởi một hoặc nhiều instance tùy cấu hình; điều này cho phép quản lý workload, định tuyến và khả năng chịu lỗi mà ứng dụng không phải gắn vào một SID cố định.

Không suy ra rằng vì database có tên `SALES` thì SID luôn là `SALES`. Một server hoặc cluster có thể có cách đặt tên hoàn toàn khác.

## 3. SERVICE_NAME: tên dịch vụ mà client yêu cầu

### 3.1. Service là điểm truy cập logic

**Database service** là một điểm truy cập có tên do Oracle Database cung cấp và listener biết cách chuyển kết nối đến những instance/handler phục vụ service đó.

Ví dụ:

```text
Client A ── SERVICE_NAME=SALES_APP ──┐
                                     ├──► Oracle Database / PDB phù hợp
Client B ── SERVICE_NAME=SALES_REPORT ┘
```

Hai service có thể dẫn tới cùng một database nhưng dùng cho các nhóm công việc khác nhau. Trong hệ thống nhiều instance, một service có thể được cấu hình chạy trên các instance theo chính sách của hệ thống. Các tính năng như cân bằng tải hoặc failover còn phụ thuộc cấu hình listener, RAC/Data Guard, client và driver; **chỉ ghi tên service không tự bảo đảm tính sẵn sàng cao**.

Service name thường có dạng tên ngắn hoặc tên gồm domain, ví dụ `FREEPDB1`, `sales_app.example.com`. Hãy dùng **tên service đúng như server công bố**; đừng tự thêm hay bỏ domain dựa trên suy đoán.

### 3.2. Vì sao PDB nên được truy cập qua service?

Oracle Multitenant chia một **CDB** thành CDB root và các **PDB**. Một instance phục vụ CDB có thể cung cấp nhiều service để client đi vào các PDB tương ứng:

```text
                   Instance: SID=FREE (ví dụ)
                              │
                CDB và các container
                  /                    \
           CDB$ROOT                  PDB: FREEPDB1
          service riêng             service: FREEPDB1
                                       ▲
                                       │
                     Ứng dụng: //host:1521/FREEPDB1
```

Ví dụ minh họa SID `FREE` phụ thuộc vào phiên bản và cách khởi tạo; **không dùng tên SID giả định để thay cho việc tra cứu thực tế**. Điểm cần nhớ là nhiều service/PDB có thể được phục vụ qua cùng một instance. Dùng SID chỉ chỉ định instance, không phải cách thông thường để chọn chính xác một PDB.

Trong ứng dụng mới, nhất là khi truy cập PDB, **ưu tiên `SERVICE_NAME`**. Nếu tài liệu cài đặt chỉ cung cấp host, port, service, bạn không cần tự tìm SID để kết nối.

### 3.3. Listener biết service bằng cách nào?

Oracle instance đăng ký thông tin dịch vụ và handler với listener thông qua cơ chế đăng ký động (ở các phiên bản hiện đại có tiến trình nền **LREG**). Tùy cấu hình có thể còn những cách đăng ký tĩnh. Khi client yêu cầu `SERVICE_NAME=FREEPDB1`, listener cần biết một handler phù hợp cho service đó.

Vì vậy, ba trạng thái sau là **khác nhau**:

1. Server/VM/container đang chạy.
2. TCP listener đang lắng nghe ở `1521`.
3. Service `FREEPDB1` đã được đăng ký và database/PDB thực sự sẵn sàng cho phiên đăng nhập.

Lớp 1 và 2 hoạt động chưa bảo đảm lớp 3 đã sẵn sàng. Ví dụ, listener có thể chạy trước khi PDB mở.

## 4. Tên kết nối TNS: tên tra cứu ở phía client

Giả sử máy chủ Oracle có:

```text
Host: 192.0.2.10       (địa chỉ minh họa)
Port: 1521
Service name: SALES_APP
```

Thay vì nhập ba giá trị trên mỗi lần đăng nhập, bạn có thể tạo alias `SALES_LAB` trong tệp **`tnsnames.ora`** ở phía client:

```text
SALES_LAB =
  (DESCRIPTION =
    (ADDRESS =
      (PROTOCOL = TCP)
      (HOST = 192.0.2.10)
      (PORT = 1521)
    )
    (CONNECT_DATA =
      (SERVICE_NAME = SALES_APP)
    )
  )
```

Khi gõ `sqlplus app_user@SALES_LAB`, Oracle Net client sẽ cố **phân giải** `SALES_LAB` thành mô tả kết nối ở trên. Alias `SALES_LAB` chỉ là một tên do người cấu hình client đặt, **không phải tên instance, database hay service trên server**.

Bạn hoàn toàn có thể đặt alias `ORACLE_THUC_HANH` hoặc `DB_REPORT` trỏ đến cùng `SALES_APP`; đồng thời một alias có thể được sửa để trỏ đến endpoint khác. Điều quan trọng là khách hàng phải đọc được đúng cấu hình và endpoint mới thực sự cung cấp service.

### 4.1. Alias nằm ở đâu?

Thông thường, local naming dùng:

- **`tnsnames.ora`**: định nghĩa alias và connect descriptor.
- **`sqlnet.ora`** (tùy chọn): quy định hành vi Oracle Net client, ví dụ thứ tự các phương thức phân giải tên.
- **`TNS_ADMIN`**: biến môi trường hoặc thuộc tính cấu hình giúp chỉ thư mục chứa các tệp mạng Oracle khi không dùng đường dẫn mặc định của client.

Ví dụ nội dung một `sqlnet.ora` đơn giản:

```text
NAMES.DIRECTORY_PATH = (TNSNAMES, EZCONNECT)
```

Điều này cho phép client thử phương thức tra cứu trong `tnsnames.ora` và phương thức Easy Connect theo thứ tự cấu hình. Các môi trường thực tế có thể dùng thêm phương thức khác như directory naming; khả năng phân giải và thứ tự thực tế phụ thuộc phiên bản/cấu hình client.

Một số vị trí thường gặp cho tệp Oracle Net bao gồm `$ORACLE_HOME/network/admin`, thư mục `network/admin` của Instant Client, hoặc thư mục được chỉ ra bởi `TNS_ADMIN`. **Đừng giả định mọi công cụ trên cùng máy đọc cùng một `tnsnames.ora`**: SQL Developer, Instant Client, JDBC và các Oracle Home khác nhau có thể có cấu hình đường dẫn riêng.

Ví dụ đặt thư mục tệp TNS cho **phiên PowerShell hiện tại**:

```powershell
$env:TNS_ADMIN = 'C:\oracle\network\admin'
```

Trên Linux/macOS:

```bash
export TNS_ADMIN="$HOME/oracle-network/admin"
```

Hai ví dụ chỉ **đặt biến môi trường**; bạn phải tự bảo đảm thư mục và `tnsnames.ora` tồn tại, đồng thời ứng dụng được chạy trong môi trường nhận biến đó. Một ứng dụng đã mở trước khi thay đổi biến có thể cần khởi động lại.

### 4.2. TNS alias có nhất thiết dùng SERVICE_NAME?

Không. Về mặt cú pháp, connect descriptor cũng có thể yêu cầu SID:

```text
LEGACY_ORCL =
  (DESCRIPTION =
    (ADDRESS = (PROTOCOL = TCP)(HOST = db.example.com)(PORT = 1521))
    (CONNECT_DATA = (SID = ORCL1))
  )
```

Đây là **alias TNS chứa SID**. Trong khi đó, ví dụ `SALES_LAB` ở trên là **alias TNS chứa SERVICE_NAME**. Từ “TNS” cho biết cách client tìm cấu hình kết nối, **không cho biết listener sẽ nhận SID hay service**.

Với kết nối ứng dụng hiện đại, cách dùng `(SERVICE_NAME=...)` trong alias thường là lựa chọn thích hợp hơn; cấu hình `(SID=...)` có thể còn xuất hiện trong hệ thống cũ hoặc quy trình quản trị riêng.

### 4.3. Tên hiển thị kết nối trong SQL Developer có phải TNS alias?

Không nhất thiết. SQL Developer có trường **Connection Name** để bạn đặt nhãn hiển thị trong danh sách kết nối, chẳng hạn “Oracle bài tập”. Nhãn này **không bắt buộc tồn tại trong `tnsnames.ora`**.

Khi chọn **Connection Type = Basic**, bạn nhập trực tiếp hostname, port và service/SID. Khi chọn **Connection Type = TNS** (nếu phiên bản/cấu hình client hỗ trợ), bạn chọn một **Network Alias** đã được client phân giải. Việc hai trường cùng có chữ “name” không làm chúng trở thành cùng một dữ liệu.

## 5. Bảng so sánh SID, SERVICE_NAME và TNS alias

| Tiêu chí | SID | SERVICE_NAME | TNS alias / net service name |
| --- | --- | --- | --- |
| Đại diện cho | Một **Oracle instance** | Một **dịch vụ database** để client truy cập | Một **tên tra cứu cấu hình Oracle Net** ở phía client |
| Nơi thường được xác lập | Cấu hình và môi trường instance trên server | Cấu hình service database, PDB hoặc chính sách quản lý service | `tnsnames.ora` / phương thức naming phù hợp |
| Ví dụ | `ORCL1` | `SALES_APP` hoặc `FREEPDB1` | `SALES_LAB` |
| Có phải host/port? | Không | Không | Không; alias có thể *chứa tham chiếu* đến host/port |
| Có thể trùng tên với nhau không? | Có, do cách đặt tên | Có | Có, nhưng trùng chữ không đồng nghĩa trùng bản chất |
| Dùng cho nhiều PDB | Không trực tiếp chọn PDB theo cách chuẩn | Có thể chọn service gắn với PDB phù hợp | Có, nếu alias trỏ tới service của PDB |
| Môi trường RAC | Chỉ một instance cụ thể | Có thể đại diện workload trên một hoặc nhiều instance | Có thể chứa địa chỉ và service phục vụ RAC |
| Dùng trong kết nối ứng dụng mới | Thường tránh nếu không có lý do riêng | **Ưu tiên** | Hữu ích khi muốn quản lý endpoint bằng tên ngắn |
| Khi gặp lỗi tên | Listener không biết SID: thường `ORA-12505` | Listener không biết service: thường `ORA-12514` | Không phân giải được connect identifier: thường `ORA-12154` |

Một quy tắc ghi nhớ:

> **SID trả lời “instance nào?”, SERVICE_NAME trả lời “dịch vụ database nào?”, còn TNS alias trả lời “client sẽ tìm thông số kết nối dưới tên nào?”.**

## 6. Ba cách tạo kết nối đến cùng Oracle Database

Giả sử một môi trường thực hành Oracle Database Free có listener trên host `127.0.0.1:1521`, service của PDB là `FREEPDB1`, và bạn đã có user `LAB_USER` trong PDB. Các thông số này chỉ là ví dụ; cần thay bằng cấu hình thực tế của bạn.

### 6.1. Kết nối trực tiếp bằng SERVICE_NAME (khuyên dùng)

Trong SQL Developer chọn **Basic**:

| Trường | Giá trị |
| --- | --- |
| Connection Name | `Oracle Local - PDB` (chỉ là nhãn UI) |
| Username | `LAB_USER` |
| Password | Mật khẩu của `LAB_USER` |
| Hostname | `127.0.0.1` |
| Port | `1521` |
| Connection selector | **Service name** |
| Service name | `FREEPDB1` |

Trong SQL*Plus hoặc SQLcl có hỗ trợ Easy Connect, gõ:

```bash
sqlplus LAB_USER@//127.0.0.1:1521/FREEPDB1
```

Sau đó nhập mật khẩu tại prompt của công cụ.

Dạng `//host:port/service_name` là **Easy Connect**: client có thể tự dựng connect descriptor từ host, port và service mà không cần alias trong `tnsnames.ora`, miễn client cho phép phương thức đặt tên này.

Với JDBC Thin (Java):

```properties
spring.datasource.url=jdbc:oracle:thin:@//127.0.0.1:1521/FREEPDB1
spring.datasource.username=LAB_USER
# Đưa mật khẩu qua cơ chế cấu hình/secret an toàn, không commit giá trị thật.
```

Trong JDBC, phần sau `@//` chỉ rõ host, port và **service name**, không phải SID. Cú pháp này phù hợp với nhiều cấu hình Oracle JDBC hiện đại.

### 6.2. Kết nối qua TNS alias

Giả sử client có `tnsnames.ora`:

```text
ORACLE_LAB =
  (DESCRIPTION =
    (ADDRESS = (PROTOCOL = TCP)(HOST = 127.0.0.1)(PORT = 1521))
    (CONNECT_DATA = (SERVICE_NAME = FREEPDB1))
  )
```

Khi đó dùng:

```bash
sqlplus LAB_USER@ORACLE_LAB
```

Tại SQL Developer, nếu công cụ đọc được `tnsnames.ora`, chọn **TNS** rồi chọn alias `ORACLE_LAB`. Kết nối này vẫn đến **cùng service `FREEPDB1`**; alias chỉ giúp gom thông số kết nối và tái sử dụng tên.

Trong ứng dụng JDBC Thin, việc dùng TNS alias cũng có thể thực hiện được nếu driver có cấu hình Oracle Net/TNS tương ứng; hãy bảo đảm driver và tiến trình Java thực sự biết đường dẫn `tnsnames.ora`. Đối với ví dụ nhỏ hoặc container cục bộ, URL Easy Connect thường đơn giản hơn.

### 6.3. Kết nối bằng SID (cách cũ hoặc trường hợp đặc biệt)

Một số công cụ cho phép bạn chọn **SID** thay vì **Service name**. Ví dụ nếu listener đăng ký một instance có SID `ORCL1`, connect descriptor có thể là:

```text
(DESCRIPTION =
  (ADDRESS = (PROTOCOL = TCP)(HOST = db.example.com)(PORT = 1521))
  (CONNECT_DATA = (SID = ORCL1))
)
```

Một dạng URL JDBC Thin truyền thống là:

```text
jdbc:oracle:thin:@db.example.com:1521:ORCL1
```

Dạng `host:port:SID` trên **khác** dạng `@//host:port/service_name` và không nên hoán đổi ký tự `:` với `/` tùy ý. Lựa chọn SID chỉ phù hợp khi server hỗ trợ kết nối theo SID và bạn có chủ đích truy cập instance đó. Đối với PDB, hãy sử dụng service name mà database cung cấp.

### 6.4. Ba chuỗi nhìn giống nhau nhưng khác mục đích

```text
//127.0.0.1:1521/FREEPDB1       -> Easy Connect tới SERVICE_NAME=FREEPDB1
ORACLE_LAB                      -> Alias, client phải phân giải ra descriptor
(CONNECT_DATA=(SID=ORCL1))      -> Yêu cầu SID của instance ORCL1
```

Trường hợp hiển thị của SQL Developer:

```text
Connection Name: "Local Oracle"
Connection Type: Basic
Host: 127.0.0.1
Port: 1521
Service name: FREEPDB1
```

Ở đây “Local Oracle” **chỉ là nhãn hiển thị**. Không có TNS alias nào bắt buộc mang tên đó.

## 7. Tìm tên đúng trên môi trường Oracle đang chạy

### 7.1. Kiểm tra từ phía client: đang kết nối vào đâu?

Sau khi đăng nhập thành công, người dùng thông thường có thể thử truy vấn sau:

```sql
SELECT
    USER AS login_user,
    SYS_CONTEXT('USERENV', 'DB_NAME')       AS database_name,
    SYS_CONTEXT('USERENV', 'INSTANCE_NAME') AS instance_name,
    SYS_CONTEXT('USERENV', 'SERVICE_NAME')  AS session_service,
    SYS_CONTEXT('USERENV', 'CON_NAME')      AS container_name
FROM dual;
```

Ý nghĩa các cột:

- `DATABASE_NAME`: database đang phục vụ phiên làm việc.
- `INSTANCE_NAME`: instance đang xử lý phiên hiện tại.
- `SESSION_SERVICE`: service gắn với phiên.
- `CONTAINER_NAME`: container/PDB hiện tại; đặc biệt quan trọng để kiểm tra có vào đúng PDB hay không.

Trong SQL*Plus, `SHOW CON_NAME` cũng giúp xem container hiện tại nếu công cụ và phiên đăng nhập hỗ trợ. Những giá trị trên là **thông tin sau khi đã kết nối**; chúng không cho biết client trước đó đã sử dụng Easy Connect hay alias TNS nào.

### 7.2. Kiểm tra từ phía quản trị server

Khi có tài khoản và quyền phù hợp để xem các dynamic performance views, người quản trị có thể chạy:

```sql
SELECT instance_name, host_name, status
FROM v$instance;

SELECT name, network_name, pdb
FROM v$services
ORDER BY name;

SELECT name, open_mode
FROM v$pdbs
ORDER BY name;
```

Không mặc định rằng `LAB_USER` có quyền đọc các view `V$`. Trong bài học kết nối, hãy dùng tài khoản quản trị chỉ khi cần chẩn đoán dịch vụ; không cấp quyền `DBA` cho user ứng dụng để tránh lỗi truy vấn này.

Từ terminal ngay trên máy database, nếu có các tiện ích Oracle tương ứng:

```bash
lsnrctl status
lsnrctl services
```

`lsnrctl status` cho biết listener, endpoint và phần tóm tắt service. `lsnrctl services` cung cấp thêm thông tin service/instance/handler mà listener hiện biết. Nếu service bạn nhập không xuất hiện, hãy kiểm tra PDB có mở hay chưa, cấu hình service và đăng ký service với listener.

**Lưu ý:** Một service không xuất hiện tại listener đang kiểm tra không có nghĩa toàn bộ database không có service đó: có thể bạn đang xem nhầm listener, port, node hoặc cấu hình mạng.

### 7.3. Kiểm tra alias và đường dẫn `tnsnames.ora`

Nếu client Oracle Net có công cụ `tnsping`, có thể chạy:

```bash
tnsping ORACLE_LAB
```

`tnsping` hữu ích để xem alias có được phân giải ra connect descriptor và listener có thể được tiếp cận hay không. **`tnsping` thành công không chứng minh user đăng nhập thành công, PDB mở, quyền truy cập đúng hoặc service đang sẵn sàng tạo session.** Hãy dùng một lần đăng nhập thật bằng `sqlplus`/SQL Developer để xác nhận.

Khi alias không được nhận ra, kiểm tra:

1. Tệp `tnsnames.ora` nằm trong thư mục mà **đúng tiến trình client** sử dụng.
2. Biến `TNS_ADMIN` và cấu hình Oracle Home/Instant Client có trỏ đúng thư mục không.
3. Tên alias ở đầu mục có khớp tên bạn nhập và cú pháp ngoặc trong descriptor có đầy đủ không.
4. Cấu hình `NAMES.DIRECTORY_PATH` có cho phép phương thức `TNSNAMES` không.
5. Trong descriptor, host, port và service/SID có đúng với server thực không.

## 8. Phân biệt các lỗi Oracle Net thường gặp

Thông báo `ORA-` là **dấu hiệu để xác định lớp lỗi**, không phải lời khuyên đổi ngẫu nhiên từ SID sang service.

| Lỗi/triệu chứng | Lớp liên quan | Nguyên nhân thường gặp | Bước xác minh |
| --- | --- | --- | --- |
| `ORA-12154: TNS:could not resolve the connect identifier specified` | Phân giải tên ở client | Alias sai, không tìm thấy `tnsnames.ora`, cấu hình naming không phù hợp | Kiểm tra `TNS_ADMIN`, alias và `tnsping` nếu có. |
| `ORA-12541: TNS:no listener` | Kết nối TCP/listener | Sai host/port, listener chưa chạy hoặc endpoint không truy cập được | Kiểm tra TCP tới host:port và `lsnrctl status`. |
| `ORA-12514: listener does not currently know of service requested` | Service phía listener | `SERVICE_NAME` không đúng/không đăng ký, PDB chưa mở | Xem `lsnrctl services`, service thật và trạng thái PDB. |
| `ORA-12505: listener does not currently know of SID given` | SID phía listener | Chọn SID sai hoặc listener không biết instance theo SID yêu cầu | Kiểm tra SID thực và cấu hình listener; xem có nên đổi sang service name. |
| `ORA-01017: invalid username/password` | Xác thực database | Sai user/mật khẩu, đăng nhập sai PDB/service hoặc chính sách xác thực | Xác nhận account, service/PDB và thông tin đăng nhập bằng phương thức an toàn. |
| `ORA-28000: account is locked` | Trạng thái tài khoản | User bị khóa | Nhờ tài khoản quản trị kiểm tra/mở khóa theo chính sách. |
| Kết nối được nhưng không thấy bảng | PDB/schema | Vào sai PDB, sai user/schema hoặc thiếu quyền truy cập đối tượng | Query `USER`, `CON_NAME`, schema owner và quyền. |

Mô hình xử lý theo thứ tự:

```text
Không kết nối được
       │
       ▼
Client có phân giải được connect identifier?
       ├── Không → TNS alias / tnsnames.ora / TNS_ADMIN
       └── Có
             │
             ▼
       Tới được TCP listener?
             ├── Không → host, port, firewall, Docker/VM forwarding
             └── Có
                   │
                   ▼
             Listener biết service hoặc SID?
                   ├── Không → service name / SID / đăng ký / trạng thái PDB
                   └── Có
                         │
                         ▼
                   Đăng nhập và truy vấn đúng PDB?
                         ├── Không → credentials, account, PDB, quyền
                         └── Có → Kết nối hoạt động
```

Điểm quan trọng: Nếu lỗi `ORA-12154`, đổi **mật khẩu** không giúp phân giải alias. Nếu lỗi `ORA-12514`, thay `TNS_ADMIN` cũng không làm listener tự biết một service chưa đăng ký, trừ khi alias trước đó trỏ sai service. Hãy khoanh đúng vị trí sự cố.

## 9. Tình huống thực tế giúp nhận biết đúng định danh

### Tình huống A — Oracle chạy trên máy học

Bạn được cung cấp `localhost`, cổng `1521`, service `FREEPDB1`. Trong SQL Developer hãy chọn **Basic → Service name → FREEPDB1** hoặc dùng `//localhost:1521/FREEPDB1`. Không cần hỏi thêm SID chỉ để chạy SQL trên PDB.

### Tình huống B — Đồng nghiệp chỉ đưa một tên `FINANCE_UAT`

Nếu đây là TNS alias, client của bạn cần có cấu hình phân giải `FINANCE_UAT` (chẳng hạn một mục trong `tnsnames.ora`) hoặc một phương thức naming tương ứng. Một tên alias đứng riêng **không cho biết** host/port/service thực tế và không mặc định dùng được trên máy khác.

### Tình huống C — Hai máy khác nhau dùng alias `REPORTING`

Máy A có thể cấu hình `REPORTING` trỏ đến UAT, máy B trỏ đến production. Vì alias là cấu hình phía client, **cùng tên alias không bảo đảm cùng môi trường đích**. Trước thao tác ghi/xóa dữ liệu quan trọng, hãy kiểm tra kết nối thực tế và cơ sở dữ liệu/PDB đang đăng nhập.

### Tình huống D — Một database có nhiều service

Service `SALES_OLTP` và `SALES_REPORT` có thể cùng phục vụ một database/PDB nhưng được cấu hình để dùng các instance hoặc chính sách workload khác nhau. Kết nối qua một SID cố định có thể bỏ qua các lợi ích định tuyến theo service mà quản trị viên đã thiết kế.

### Tình huống E — Chuyển từ một instance sang RAC

Trong môi trường một instance, người ta từng kết nối trực tiếp tới SID `SALES1`. Khi chuyển sang RAC có `SALES1` và `SALES2`, ứng dụng dùng service `SALES_APP` sẽ phù hợp hơn để quản lý endpoint ở cấp workload. Tính năng failover thực tế vẫn cần listener/service/driver và chính sách cluster được cấu hình đúng.

## 10. Bài thực hành: Hai cách gọi cùng một PDB

**Điều kiện:** Có Oracle listener lắng nghe ở `127.0.0.1:1521`, service `FREEPDB1` đã đăng ký, PDB mở và có tài khoản đăng nhập hợp lệ. Nếu cổng host khác `1521`, thay bằng cổng host thật. Thực hành này chỉ đọc metadata, không cần quyền quản trị hệ thống.

**Bước 1 — Kết nối trực tiếp**

```bash
sqlplus LAB_USER@//127.0.0.1:1521/FREEPDB1
```

Nhập mật khẩu khi công cụ hỏi. Sau khi có `SQL>`, chạy:

```sql
SELECT USER AS connected_user,
       SYS_CONTEXT('USERENV', 'SERVICE_NAME') AS used_service,
       SYS_CONTEXT('USERENV', 'CON_NAME') AS connected_container
FROM dual;
```

Ghi lại user, service và container thực tế. Thoát bằng `EXIT`.

**Bước 2 — Định nghĩa alias `ORACLE_PDB_LAB`**

Trong thư mục mạng Oracle mà client thực sự đọc, thêm hoặc tạo mục sau trong `tnsnames.ora`:

```text
ORACLE_PDB_LAB =
  (DESCRIPTION =
    (ADDRESS = (PROTOCOL = TCP)(HOST = 127.0.0.1)(PORT = 1521))
    (CONNECT_DATA = (SERVICE_NAME = FREEPDB1))
  )
```

Nếu máy đang có nhiều client, hãy đặt và kiểm tra `TNS_ADMIN` cho đúng tiến trình chạy SQL*Plus/SQLcl. Tệp `tnsnames.ora` không được chứa mật khẩu đăng nhập.

**Bước 3 — Kết nối bằng alias**

```bash
tnsping ORACLE_PDB_LAB
sqlplus LAB_USER@ORACLE_PDB_LAB
```

Lệnh `tnsping` là bước quan sát tùy chọn; nếu client không có tiện ích đó, thử kết nối thật bằng SQL*Plus/SQL Developer. Chạy lại câu `SELECT` ở bước 1 và đối chiếu kết quả. Hai phương thức đặt tên khác nhau có thể dẫn tới **cùng một service/PDB**, cho dù tên `ORACLE_PDB_LAB` không xuất hiện ở server.

**Bước 4 — Thử phân biệt alias và service**

Không thay đổi database. Hãy tưởng tượng đặt tên alias mới `MY_DB` nhưng giữ nguyên `(SERVICE_NAME=FREEPDB1)`. Như vậy client vẫn kết nối đến cùng service. Ngược lại, chỉ đổi `(SERVICE_NAME=KHONG_TON_TAI)` trong alias sẽ làm client yêu cầu một service khác; nếu listener không biết tên đó, kết nối thường thất bại ở lớp service với `ORA-12514`.

Sau bài thực hành, bạn phải giải thích được vì sao đổi **tên alias** không yêu cầu đổi tên instance hoặc PDB và vì sao đổi **SERVICE_NAME trong descriptor** là thay đổi đích kết nối thực sự.

## 11. Lưu ý bảo mật và vận hành

- Ưu tiên **SERVICE_NAME** cho kết nối ứng dụng, đặc biệt khi làm việc với PDB hoặc cụm RAC.
- Không nhúng mật khẩu vào ví dụ chuỗi kết nối hoặc đưa mật khẩu thật vào file version control; nhập từ prompt hoặc dùng cơ chế lưu secret phù hợp.
- `tnsnames.ora` thường chứa thông tin **đích kết nối**, không phải kho lưu mật khẩu. Việc có alias không tự cho phép ai đó đăng nhập.
- Cấu hình TCP listener chỉ trên giao diện mạng cần dùng; trong lab Docker cục bộ có thể chỉ publish `127.0.0.1:1521`. Không công khai listener ra Internet vì tiện thử kết nối.
- Khi kết nối qua mạng không tin cậy hoặc theo yêu cầu tổ chức, cân nhắc **TCPS/TLS** và cấu hình Oracle Net/driver/wallet thích hợp; SID, service và TNS alias vẫn là các khái niệm định danh khác nhau.
- Khi chuyển UAT/production, kiểm tra host, port và service **bên trong alias**; nhãn kết nối quen thuộc không đủ để xác nhận bạn đang truy cập môi trường nào.
- Đối với hệ thống nhiều Oracle Home, ghi rõ đường dẫn mạng Oracle của từng công cụ. Một lỗi alias hoạt động ở SQL*Plus nhưng không hoạt động ở SQL Developer thường liên quan **cấu hình client khác nhau**, không nhất thiết là lỗi database.

## 12. Tổng kết bằng cách đọc một mô tả kết nối

Cho khai báo:

```text
PAYMENTS_UAT =
  (DESCRIPTION =
    (ADDRESS = (PROTOCOL = TCP)(HOST = db-uat.example.com)(PORT = 1521))
    (CONNECT_DATA = (SERVICE_NAME = PAYMENTS_PDB))
  )
```

Đọc theo thứ tự:

1. `PAYMENTS_UAT` là **TNS alias** mà client có thể gọi.
2. `db-uat.example.com:1521` là **địa chỉ Oracle listener** mà alias chỉ đến.
3. `PAYMENTS_PDB` là **SERVICE_NAME** mà client yêu cầu listener tìm.
4. **SID không xuất hiện** trong khai báo này và không cần đoán SID để đăng nhập.
5. Khi kết nối thành công, có thể xem instance đang phục vụ và PDB đang truy cập bằng các giá trị `SYS_CONTEXT` phù hợp.

Nếu được hỏi nên nhập gì ở trường **SID** khi có chuỗi trên, câu trả lời là: **không chọn SID; chọn Service name `PAYMENTS_PDB` hoặc TNS alias `PAYMENTS_UAT`**. Hiểu ranh giới giữa instance, service và alias giúp bạn kết nối Oracle chính xác, làm việc đúng PDB và chẩn đoán sự cố ngay tại lớp cần sửa.
