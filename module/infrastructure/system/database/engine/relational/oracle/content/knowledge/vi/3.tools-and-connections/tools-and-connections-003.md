# Listener, đăng ký dịch vụ và luồng thiết lập kết nối Oracle Net

## 1. Bức tranh tổng thể

Khi một ứng dụng Java, SQL*Plus hoặc công cụ quản trị kết nối đến Oracle Database qua mạng, nó không đơn giản "mở cổng 1521 rồi truy vấn SQL". **Oracle Net Services** phải giải quyết ba việc khác nhau:

1. **Định vị đích**: tên kết nối mà client nhập được chuyển thành địa chỉ mạng và tên dịch vụ cơ sở dữ liệu (*database service*).
2. **Tìm nơi phục vụ**: một **Oracle Net Listener** tại địa chỉ đó nhận yêu cầu, tra thông tin dịch vụ và chọn *service handler* phù hợp.
3. **Thiết lập phiên làm việc**: kết nối được bàn giao hoặc chuyển hướng đến tiến trình phục vụ của database; sau đó xác thực, tạo session và trao đổi SQL.

Ở phía database, tiến trình nền **LREG (Listener Registration)** thông báo cho listener rằng instance nào đang cung cấp những dịch vụ nào và các handler có thể nhận kết nối. Vì vậy, dù listener đang chạy, một dịch vụ vẫn có thể chưa được đăng ký hoặc chưa sẵn sàng.

```text
MÁY CLIENT                                       MÁY DATABASE
──────────                                       ────────────
Ứng dụng / SQL*Plus / JDBC
  │
  ├─ "ORDER_APP" (alias trong tnsnames.ora)
  │         hoặc
  └─ "//db01.example.com:1521/orders_rw.example.com" (Easy Connect)
            │
            ▼
    Oracle Net naming resolution
    -> host, port, protocol, SERVICE_NAME
            │
            │ TCP/TCPS tới endpoint
            └──────────────────────────────────► Listener :1521
                                                   ▲
                                                   │ service registration
                                              LREG │
                                                   │
                                            Oracle instance
                                           (dịch vụ + handler)
                                                   │
                                        chọn handler cho service
                                                   │
                  ┌────────────────────────────────┘
                  ▼
    Bàn giao / redirect đến dedicated server
    hoặc dispatcher của shared server
                  │
                  ▼
    Xác thực và thiết lập database session
                  │
                  ▼
    Client ↔ server process / dispatcher ↔ Database
          (SQL, kết quả; listener không xử lý từng truy vấn)
```

**Điểm cốt lõi:** Listener là điểm tiếp nhận và phân phối **yêu cầu kết nối ban đầu**. Sau bước thiết lập kết nối, lưu lượng phiên cơ sở dữ liệu thường đi trực tiếp giữa client và tiến trình/dispatcher được chọn; listener không phải một proxy bắt buộc cho mọi câu SQL.

> Các ví dụ dùng Oracle Database 19c làm mốc khái niệm và cú pháp phổ biến. Cấu hình thực tế có thể khác ở 21c, 23ai/26ai, Oracle RAC, Exadata, Oracle Cloud và các phiên bản client. Tên host/service bên dưới là giả định, không phải tài nguyên có sẵn để kết nối.

## 2. Phân biệt đúng các thực thể

| Thuật ngữ | Là gì? | Ví dụ | Không nên nhầm với |
| --- | --- | --- | --- |
| **Database** | Cấu trúc dữ liệu vật lý và logic mà Oracle quản lý | `ORCLCDB` | Instance hoặc service |
| **Instance** | SGA và các background process dùng để truy cập database | `orcl1`, `orcl2` | CDB/PDB hoặc service |
| **SID** | Định danh một Oracle instance, đặc biệt trong kết nối cục bộ và cấu hình legacy | `orcl1` | Tên service ứng dụng |
| **CDB** | Container database có thể chứa nhiều PDB | `ORCLCDB` | Một PDB |
| **PDB** | Pluggable database trong một CDB | `ORDERPDB` | Listener hoặc một instance riêng |
| **Database service** | Tên logic đại diện cho workload/điểm truy cập database; có thể gắn với PDB, nhiều instance và chính sách HA | `orders_rw.example.com` | SID và alias client |
| **Net service name / alias** | Tên tùy ý ở phía client dùng để tra *connect descriptor* | `ORDER_APP` | Tên database service thực |
| **Listener** | Tiến trình chờ kết nối tại một hoặc nhiều endpoint mạng | `LISTENER` trên `db01:1521` | Database server process |
| **Service handler** | Tiến trình/địa chỉ xử lý kết nối cho service: dedicated server hoặc dispatcher | `DEDICATED`, `D000` | Listener |
| **Connect descriptor** | Cấu trúc chỉ định `ADDRESS` và `CONNECT_DATA` | `(DESCRIPTION=...)` | Chỉ một hostname |

Một instance có thể đăng ký **nhiều service**, và một service trong môi trường RAC có thể được cung cấp bởi **nhiều instance**. Mối quan hệ đó là lý do ứng dụng nên kết nối theo service phục vụ workload, thay vì ghim vào một SID của node cụ thể.

### 2.1. Vì sao `SERVICE_NAME` quan trọng hơn `SID` cho ứng dụng?

Trong một CDB, kết nối đến **service có thuộc tính PDB** sẽ dẫn vào PDB tương ứng. Với RAC, một service có thể tự chuyển vị trí hoạt động giữa các instance theo chính sách của Clusterware. Cả hai trường hợp đều không thể mô tả đầy đủ bằng một `SID` cố định.

Ví dụ:

```text
SERVICE_NAME = orders_rw.example.com   ← ứng dụng cần truy cập workload ORDER
INSTANCE     = orcl1                   ← instance hiện đang phục vụ
PDB          = ORDERPDB                ← container chứa schema ứng dụng
CLIENT ALIAS = ORDER_APP               ← tên do nhóm ứng dụng chọn trong tnsnames.ora
```

Đừng dựa vào việc `ORACLE_SID=orcl1` trên máy chủ để xác định `SERVICE_NAME` mà ứng dụng từ xa phải dùng. `ORACLE_SID` thường chọn instance cho kết nối cục bộ kiểu *bequeath*, không phải tên dịch vụ trong descriptor mạng.

## 3. Oracle Net Listener thực sự làm gì?

Listener là một tiến trình có thể chạy độc lập với instance, nhận yêu cầu tại địa chỉ giao thức (*protocol endpoint*) như TCP hoặc TCPS. Một listener có thể tiếp nhận yêu cầu cho nhiều database/service; ngược lại, một instance có thể đăng ký với nhiều listener theo cấu hình.

Khi nhận một yêu cầu có `SERVICE_NAME`, listener cần biết:

- Service đó đã đăng ký hoặc được cấu hình tĩnh chưa?
- Instance nào hiện cung cấp service?
- Handler nào đang nhận kết nối: dedicated server hoặc shared server dispatcher?
- Handler có còn sẵn sàng, có bị hạn chế kết nối hay đang quá tải không?
- Trong môi trường cluster, có cần chuyển tiếp hoặc redirect đến node khác không?

Listener có thể **bàn giao socket**, **tạo tiến trình dedicated server**, hoặc **trả địa chỉ khác để client kết nối lại**. Cơ chế cụ thể phụ thuộc OS, giao thức và loại handler. Vì thế, không nên khẳng định rằng trong mọi lần kết nối Oracle listener đều "proxy" dữ liệu hoặc luôn tạo ra đúng một kết nối TCP duy nhất.

### 3.1. Dedicated server

Mỗi kết nối client được phục vụ bởi một *dedicated server process* tương ứng; phù hợp nhiều ứng dụng truyền thống, nhưng cần tài nguyên tiến trình/session đủ cho số kết nối đồng thời.

```text
Client A ─► Listener ─► Dedicated server A ─► Instance
Client B ─► Listener ─► Dedicated server B ─► Instance
```

Client có thể yêu cầu rõ trong descriptor:

```text
(CONNECT_DATA=
  (SERVICE_NAME=orders_rw.example.com)
  (SERVER=DEDICATED)
)
```

### 3.2. Shared server

Khi database được cấu hình shared server, **dispatcher** tiếp nhận giao tiếp mạng từ nhiều client và chuyển request vào các hàng đợi để *shared server processes* xử lý. Listener đăng ký và chọn dispatcher cho service. Cấu hình này khác hoàn toàn với việc ứng dụng có **JDBC connection pool**: connection pool tái sử dụng session/kết nối phía ứng dụng, còn shared server thay đổi kiến trúc tiến trình phía Oracle.

```text
Client A ──┐
Client B ──┼──► Dispatcher D000 ─► Queue ─► Shared servers ─► Instance
Client C ──┘
```

Trong descriptor có thể yêu cầu `(SERVER=SHARED)` nếu hệ thống đã cấu hình dispatcher phù hợp. Ngoài dedicated/shared, Oracle còn có **Database Resident Connection Pooling (DRCP)** với loại server `POOLED`; không nên coi ba cơ chế là một.

## 4. Dynamic service registration: LREG thông báo gì cho listener?

Trên các phiên bản Oracle hiện đại, **LREG** là tiến trình nền chịu trách nhiệm đăng ký dịch vụ động. Tài liệu đời cũ thường gắn việc đăng ký với **PMON**; khi đọc tài liệu 19c trở lên nên dùng tên tiến trình **LREG**.

Trong đăng ký động, LREG gửi cho listener các thông tin như:

- Tên dịch vụ (*service name*, có thể gồm domain mạng).
- Tên instance đang cung cấp dịch vụ.
- Những handler đã sẵn sàng, địa chỉ dispatcher và loại server.
- Trạng thái và thông tin tải phục vụ định tuyến/load balancing.

Listener sử dụng thông tin này để lập danh sách service/instance/handler. **Không cần khai báo thủ công mọi dịch vụ trong `listener.ora`** khi đăng ký động hoạt động đúng.

```text
Oracle instance startup / service start / thay đổi trạng thái
                         │
                         ▼
                  LREG phát hiện
                         │
                         ▼
    LOCAL_LISTENER / REMOTE_LISTENER xác định đích đăng ký
                         │
                         ▼
              Listener nhận thông tin
                         │
                         ▼
        lsnrctl services hiển thị service
        và handler READY/BLOCKED/...
                         │
                         ▼
          Client có thể tìm đúng service
```

### 4.1. `LOCAL_LISTENER`

`LOCAL_LISTENER` xác định địa chỉ listener cục bộ mà instance sẽ đăng ký. Với cấu hình thông thường tại TCP port **1521**, Oracle có cơ chế xác định listener mặc định; giá trị tham số rỗng không nhất thiết là lỗi.

Nếu listener lắng nghe tại **port 1522** hoặc một endpoint khác mặc định, DBA cần bảo đảm `LOCAL_LISTENER` trỏ đúng endpoint và tên alias (nếu dùng) được giải được **từ máy database**, không chỉ từ máy client.

Ví dụ mang tính minh họa:

```sql
-- Đọc cấu hình hiện tại, không thay đổi hệ thống.
SELECT name, value
FROM   v$parameter
WHERE  name IN ('local_listener', 'remote_listener')
ORDER BY name;
```

Nếu cấu hình listener tùy chỉnh trên host `db01.example.com:1522`, DBA có thể đặt `LOCAL_LISTENER` bằng địa chỉ Oracle Net tương ứng trong quy trình quản trị có kiểm soát. Chỉ thay tham số khi thực sự xác định sai endpoint; **không sửa `SERVICE_NAMES` như cách khắc phục mặc định**.

### 4.2. `REMOTE_LISTENER`

`REMOTE_LISTENER` xác định những listener ở xa cần nhận thông tin đăng ký, thường gặp trong Oracle RAC khi service được đăng ký với **SCAN listener**. Trong hệ thống do Oracle Clusterware quản lý, các tham số/listener thường được cấu hình tự động; không sửa tay theo ví dụ single-instance nếu chưa kiểm tra topology.

### 4.3. Tại sao listener chạy nhưng vẫn chưa thấy service?

Nếu listener khởi động **sau** instance, quá trình đăng ký động có thể chậm đến lần LREG discovery kế tiếp. Tài liệu Oracle 19c mô tả chu kỳ khám phá mặc định khoảng **60 giây**; DBA có thể chủ động kích hoạt đăng ký lại:

```sql
-- Lệnh quản trị; yêu cầu quyền phù hợp.
-- Chỉ thực hiện sau khi đã xác định listener và service hoạt động đúng.
ALTER SYSTEM REGISTER;
```

Lệnh trên bảo LREG đăng ký lại ngay; nó **không tạo service chưa tồn tại**, **không mở PDB đang đóng**, **không sửa DNS/firewall** và **không thay thế việc khởi động listener**. Nếu listener không nhận được gói đăng ký do endpoint hoặc chính sách đăng ký sai, chạy lại lệnh nhiều lần không giải quyết gốc lỗi.

## 5. Dynamic registration và static registration khác nhau thế nào?

| | **Dynamic** | **Static** |
| --- | --- | --- |
| Nguồn thông tin | Instance/service qua LREG | Khai báo `SID_LIST_<listener_name>` trong `listener.ora` |
| Hiểu trạng thái hoạt động | Có thông tin registration và handler | Có thể không biết trạng thái thật của instance |
| Kết quả `lsnrctl services` điển hình | `READY`, `BLOCKED`, v.v. | `UNKNOWN` nếu chỉ có cấu hình tĩnh |
| Thay đổi khi start/stop service | Tự cập nhật theo registration | Không tự phản ánh đầy đủ trạng thái động |
| Trường hợp nên dùng | Kết nối ứng dụng thông thường | Tình huống đặc biệt cần biết SID trước khi instance hoạt động, ví dụ một số thao tác Data Guard Broker hoặc external procedure |

Ví dụ cấu trúc khai báo tĩnh, **chỉ để nhận diện**, không phải cấu hình nên chép nguyên vào môi trường thực tế:

```ini
# listener.ora — minh họa static SID list cho tình huống quản trị đặc biệt
SID_LIST_LISTENER =
  (SID_LIST =
    (SID_DESC =
      (GLOBAL_DBNAME = orcl_admin.example.com)
      (ORACLE_HOME = /u01/app/oracle/product/19c/dbhome_1)
      (SID_NAME = orcl1)
    )
  )
```

Đường dẫn `ORACLE_HOME`, `SID_NAME` và tên tĩnh phải đúng với máy thật. Không thêm `SID_LIST` chỉ để "chữa" mọi lỗi `ORA-12514`; nếu service cần dùng đang phải được LREG đăng ký, sửa sai cấu hình ở tầng đúng thay vì tạo một alias tĩnh che mất vấn đề. Trạng thái `UNKNOWN` có nghĩa listener không biết trạng thái runtime từ static entry, **không tự động đồng nghĩa instance đã hỏng**.

## 6. Client tìm endpoint bằng cách nào?

Trước khi gửi kết nối, client cần chuyển một *connect identifier* thành *connect descriptor*. Hai cách thường gặp là **Easy Connect** và **local naming (`tnsnames.ora`)**.

### 6.1. Easy Connect

Cú pháp phổ biến:

```text
//host[:port]/service_name
```

Ví dụ với SQL*Plus:

```bash
# Client hỏi password qua prompt; không nhúng mật khẩu vào command line.
sqlplus -L app_user@//db01.example.com:1521/orders_rw.example.com
```

Ví dụ JDBC Thin:

```properties
spring.datasource.url=jdbc:oracle:thin:@//db01.example.com:1521/orders_rw.example.com
spring.datasource.username=app_user
# Password lấy từ secret manager hoặc cơ chế quản lý bí mật của môi trường.
```

Trong cả hai ví dụ, `db01.example.com:1521` là địa chỉ **listener**, còn `orders_rw.example.com` là **database service**. Không dùng tên listener (`LISTENER`) thay cho service. Easy Connect Plus và cú pháp client đời mới hỗ trợ thêm endpoint, tham số bảo mật, retry và load balancing; hãy kiểm tra cú pháp đúng với Oracle Client/JDBC driver đang triển khai.

### 6.2. `tnsnames.ora`: alias phía client

```ini
# tnsnames.ora trên máy client hoặc nơi TNS_ADMIN chỉ tới
ORDER_APP =
  (DESCRIPTION =
    (ADDRESS = (PROTOCOL = TCP)(HOST = db01.example.com)(PORT = 1521))
    (CONNECT_DATA =
      (SERVICE_NAME = orders_rw.example.com)
      (SERVER = DEDICATED)
    )
  )
```

Client sử dụng:

```bash
sqlplus -L app_user@ORDER_APP
```

Hệ thống giải `ORDER_APP` thành descriptor rồi mới tìm địa chỉ mạng. `ORDER_APP` là tên **do bên client đặt**, có thể khác `orders_rw.example.com`. Việc sửa alias trên laptop không đồng nghĩa listener hay service database đã đổi tên.

### 6.3. `sqlnet.ora` và `TNS_ADMIN`

`sqlnet.ora` cấu hình hành vi Oracle Net, trong đó có các phương thức tìm tên và thứ tự tra cứu:

```ini
# sqlnet.ora — ví dụ thứ tự phân giải tên ở client
NAMES.DIRECTORY_PATH = (TNSNAMES, EZCONNECT)
```

Thư mục cấu hình phụ thuộc cách cài Oracle Client, Oracle Home, Instant Client, ứng dụng, biến môi trường **`TNS_ADMIN`** và từng driver. Nếu `tnsping ORDER_APP` tìm sai descriptor, cần xác định client **đang đọc đúng file nào**; không nên giả định một file `tnsnames.ora` duy nhất cho tất cả công cụ trên máy. Một số ứng dụng JDBC Thin sử dụng URL Easy Connect mà không cần `tnsnames.ora`.

### 6.4. Vì sao port và tên service thuộc hai tầng khác nhau?

```text
db01.example.com:1521               → DNS + TCP + Listener endpoint
orders_rw.example.com                → Oracle Net database service
app_user                             → Oracle database account
ORDERPDB                             → Container nhận session
```

**TCP mở thành công** chỉ chứng minh có endpoint trả lời tại cổng đó; nó chưa chứng minh service đã được đăng ký, có handler sẵn sàng, user được xác thực hay PDB đã mở.

## 7. Một cấu hình single-instance điển hình

Giả sử có:

- Máy database: `db01.example.com`.
- Listener: `LISTENER`, TCP port `1521`.
- CDB: `ORCLCDB`, instance: `orcl1`.
- PDB: `ORDERPDB`.
- Dịch vụ ứng dụng do DBA quản lý: `orders_rw.example.com`, gắn với `ORDERPDB`.
- Client kết nối bằng alias `ORDER_APP` hoặc Easy Connect.

### 7.1. Phía listener

Một cấu hình listener TCP tối giản có dạng:

```ini
# listener.ora trên máy database — ví dụ minh họa
LISTENER =
  (DESCRIPTION_LIST =
    (DESCRIPTION =
      (ADDRESS = (PROTOCOL = TCP)(HOST = db01.example.com)(PORT = 1521))
    )
  )
```

Listener có thể do công cụ cài đặt tạo/cấu hình tự động. **Không bắt buộc thêm `SID_LIST_LISTENER`** cho database service ứng dụng thông thường vì LREG đăng ký động. Nếu database chạy sau NAT/container/VM, địa chỉ listener công bố cho client cũng phải được định tuyến phù hợp. Không nên chép nguyên host, port hoặc đường dẫn từ ví dụ mà không kiểm tra mạng thật.

### 7.2. Phía database service

Oracle tự tạo một service mặc định cho PDB, nhưng tài liệu **Oracle 19c Multitenant Administrator's Guide** khuyến nghị ứng dụng dùng **user-defined service** để có thể quản lý thuộc tính riêng và chính sách vận hành, thay vì gắn chặt vào default PDB service.

Với database do **Oracle Restart/Clusterware** quản lý, dùng **SRVCTL** để tạo, cấu hình, khởi động và đặt chính sách dịch vụ. Với single-instance không do Clusterware quản lý, DBA có thể dùng **`DBMS_SERVICE`**. Trong Oracle 19c, việc người dùng trực tiếp quản lý service bằng tham số **`SERVICE_NAMES` đã được đánh dấu deprecated**; không dùng nó như con đường mặc định để tạo service mới.

Một số lệnh **đọc** khi dùng Oracle Restart/Clusterware (thay `db_unique_name` bằng giá trị thật):

```bash
srvctl config service -db db_unique_name
srvctl status service -db db_unique_name
```

Việc tạo/bật/tắt/di chuyển service bằng SRVCTL/DBMS_SERVICE là thay đổi hoạt động của database, cần quy trình DBA phù hợp. Nếu `ORDERPDB` đang đóng hoặc service chưa được start, listener có thể không hiển thị service có thể dùng dù listener vẫn sống.

### 7.3. Xác minh từ listener

Trên máy có Oracle Net Listener Control và đúng Oracle Home:

```bash
lsnrctl status LISTENER
lsnrctl services LISTENER
```

`STATUS` cho biết listener đang dùng file cấu hình nào, các endpoint nào đang mở và danh sách service tổng quan. `SERVICES` hiển thị chi tiết instance/handler, thích hợp để kiểm tra service thực sự đã được đăng ký hay chưa.

Đầu ra minh họa (rút gọn, không phải bản chụp hệ thống thật):

```text
Service "orders_rw.example.com" has 1 instance(s).
  Instance "orcl1", status READY, has 1 handler(s) for this service...
    Handler(s):
      "DEDICATED" established:0 refused:0 state:ready
```

| Trạng thái | Cách đọc |
| --- | --- |
| `READY` | Instance/handler có thể nhận kết nối tại thời điểm listener báo cáo |
| `BLOCKED` | Tạm thời không nhận kết nối mới, cần kiểm tra trạng thái database và tài nguyên |
| `RESTRICTED` | Instance bị giới hạn kết nối theo trạng thái restricted |
| `UNKNOWN` | Entry đăng ký tĩnh; listener không nắm được trạng thái runtime từ registration động |
| Không thấy service | Cần kiểm tra tên, trạng thái PDB/service, LREG, endpoint đăng ký hoặc listener bạn đang hỏi |

`lsnrctl status` trả về thành công **không đảm bảo** mọi service trong đó đều có thể kết nối. Hãy đọc `services` và thử một kết nối ứng dụng hợp lệ.

## 8. Luồng thiết lập kết nối từng bước

Giả sử ứng dụng thực hiện:

```text
jdbc:oracle:thin:@//db01.example.com:1521/orders_rw.example.com
```

**Bước 1 — Phân giải connect identifier.** Oracle JDBC Thin đọc Easy Connect, rút ra giao thức TCP, host `db01.example.com`, port `1521`, service `orders_rw.example.com`. Với alias, client cần tra `tnsnames.ora` hoặc phương thức naming đã cấu hình trước.

**Bước 2 — DNS và đường truyền.** Client phân giải host thành IP, mở kết nối TCP (hoặc thiết lập TLS cho TCPS) tới listener. Nếu DNS, firewall, route hay NAT sai, yêu cầu có thể không đến được listener.

**Bước 3 — Listener nhận connect data.** Listener đọc `SERVICE_NAME` (và các thuộc tính như kiểu server, tên instance nếu có), tra bảng đã được đăng ký bởi LREG và chọn instance/handler phù hợp.

**Bước 4 — Handoff hoặc redirect.** Tùy kiến trúc, listener khởi tạo/bàn giao kết nối tới dedicated server, giao cho dispatcher, hoặc cung cấp địa chỉ để client kết nối tới handler khác. Nếu không có service hay handler sẵn sàng, client nhận lỗi Oracle Net ở giai đoạn này.

**Bước 5 — Xác thực và tạo session.** Server process trao đổi với client, xác thực tài khoản bằng cơ chế đã cấu hình, kiểm tra quyền truy cập và hoàn tất session. Lỗi `ORA-01017` thường thuộc bước xác thực, tức là khác lớp nguyên nhân với `ORA-12514`.

**Bước 6 — Truy vấn SQL.** Ứng dụng gửi SQL và đọc kết quả qua session; listener quay lại chờ các kết nối mới. Nếu dùng connection pool, ứng dụng có thể mượn session đã mở trước đó nên **không phải mỗi câu SQL đều đi lại qua cả sáu bước**.

**Bước 7 — Giải phóng.** Khi kết nối đóng, server process/dispatcher và tài nguyên liên quan xử lý theo loại handler; connection pool có thể giữ các kết nối còn hợp lệ để tái sử dụng.

### Thử từ client và xác nhận container thực tế

```bash
# Chỉ kiểm tra đường phân giải và phản hồi Oracle Net; không đăng nhập DB.
tnsping ORDER_APP

# Đăng nhập bằng tài khoản đã được cấp, mật khẩu nhập tại prompt.
sqlplus -L app_user@ORDER_APP
```

Sau khi đăng nhập thành công:

```sql
SELECT SYS_CONTEXT('USERENV', 'SERVICE_NAME')  AS service_name,
       SYS_CONTEXT('USERENV', 'CON_NAME')      AS container_name,
       SYS_CONTEXT('USERENV', 'INSTANCE_NAME') AS instance_name
FROM   dual;
```

Kết quả giúp xác minh **client thực sự đang ở service/container/instance nào**. Điều này đặc biệt hữu ích khi có nhiều PDB hoặc khi service được chuyển sang instance khác trong RAC. `tnsping` thành công chỉ kiểm tra một phần Oracle Net; nó **không xác thực user và không chứng minh PDB/service cụ thể có thể nhận session**.

## 9. Oracle RAC: SCAN và hai lớp listener

Trong Oracle Real Application Clusters, ứng dụng không nên mã hóa hostname của một node riêng lẻ nếu mục tiêu là service có failover và cân bằng kết nối. **SCAN (Single Client Access Name)** cung cấp một điểm tên DNS ổn định để client tìm cluster; SCAN listener tiếp nhận kết nối ban đầu rồi chuyển đến local listener của node có instance đang phục vụ service.

```text
                         +------------------------+
Client ─► DNS: scan.example.com ─► SCAN listener  +──────────────┐
                         +------------------------+              │
                 chọn instance có service, xét tải/policy       │ redirect
                                                                 ▼
                    ┌───────────────────────────────┬───────────────────────────────┐
                    │ Node 1                        │ Node 2                        │
                    │ Local Listener :1521          │ Local Listener :1521          │
                    │ Instance orcl1                │ Instance orcl2                │
                    └───────────────────────────────┴───────────────────────────────┘
```

Luồng phổ biến: client phân giải SCAN → đến một SCAN listener → SCAN listener xác định instance có service phù hợp → trả địa chỉ local listener trên node đó → client liên hệ node/handler để hoàn thành kết nối.

```text
# JDBC Thin qua service của RAC — minh họa
jdbc:oracle:thin:@//scan.example.com:1521/orders_rw.example.com
```

Các điểm thường phải kiểm tra khi có lỗi RAC:

- SCAN name phân giải đúng địa chỉ và client đến được SCAN listener không?
- Service do Clusterware quản lý có **online** trên ít nhất một instance không?
- `REMOTE_LISTENER`/registration với SCAN listener có đúng theo cấu hình Clusterware không?
- Client có thể kết nối đến **địa chỉ local listener được redirect** hay chỉ đến được SCAN VIP? Đây là nguyên nhân hay gặp khi mạng/firewall phân đoạn.
- Driver và connection pool có được cấu hình cho failover, retry, timeout và các thông báo dịch vụ theo yêu cầu SLA không? Việc dùng SCAN/service **không tự bảo đảm** mọi transaction đang chạy sẽ tiếp tục liền mạch sau sự cố.

**Không áp dụng các lệnh chỉnh listener cho single-instance vào hệ thống Clusterware/RAC một cách tùy tiện.** Trong RAC, listener, SCAN và service thường có vòng đời do Grid Infrastructure và SRVCTL quản lý.

## 10. Cấu hình mạng và bảo mật liên quan

### 10.1. TCP so với TCPS

- **TCP**: vận chuyển kết nối Oracle Net qua TCP. Listener TCP thường dùng port `1521` nhưng có thể cấu hình port khác.
- **TCPS**: Oracle Net qua TLS, liên quan certificate, wallet/trust store và cấu hình client/server. Mở cổng TCP thành công **không chứng minh** đã cấu hình TLS đúng.

Ví dụ descriptor có cấu trúc `(PROTOCOL=TCPS)` nhưng chỉ thay `TCP` thành `TCPS` trong URL không đủ; cần certificate, chain tin cậy, chính sách xác minh tên và cách cấu hình wallet tương ứng với phiên bản/client.

### 10.2. Listener nhận kết nối và đăng ký qua mạng

Nên giới hạn các endpoint được công bố, kiểm soát firewall, quyền vận hành listener và chính sách cho phép instance đăng ký vào listener. Ở hệ thống nhiều node, chính sách bảo vệ *service registration* có thể ảnh hưởng việc LREG đăng ký từ xa; cần dùng tài liệu `VALID_NODE_CHECKING_REGISTRATION_...` và các cơ chế tương ứng **đúng phiên bản**, thay vì mở vô điều kiện mọi nguồn đăng ký khi gặp `ORA-12514`.

Không đưa password vào command line, commit `tnsnames.ora` kèm thông tin bí mật hoặc tắt xác minh TLS để "thử cho qua". `tnsnames.ora` thường chỉ chứa địa chỉ và tên dịch vụ, không cần password.

### 10.3. NAT, container, VPN và firewall

Đường mạng client → listener **có thể khác** đường client → server process/dispatcher sau redirect. Trong Docker, máy ảo, VPN hoặc multi-homed host, kiểm tra:

1. Hostname trong connect descriptor có được client phân giải đúng?
2. Cổng TCP/TCPS thực tế có được publish/forward và firewalled đúng?
3. Listener hoặc dispatcher có trả về một địa chỉ private/container mà client không định tuyến tới được?
4. Trong RAC, các địa chỉ VIP, SCAN VIP và local listener có reachable từ vùng mạng của ứng dụng?

Tùy triển khai, cần thiết kế network routing, listener endpoint và kết nối được hỗ trợ bởi sản phẩm/container; không mặc định rằng chỉ mở port `1521` là đủ cho mọi tình huống redirect.

## 11. Quy trình chẩn đoán từ ngoài vào trong

Khi một client báo không vào được Oracle, hãy đi theo thứ tự lớp mạng → listener → registration → service handler → database authentication.

### 11.1. Bước A: kiểm tra đúng connect string

Ghi lại **nguyên văn host, port, protocol, service name**, phiên bản driver và phương thức naming đang dùng; không yêu cầu user gửi password. Nếu có alias, kiểm tra nó giải thành descriptor nào ở **đúng môi trường ứng dụng** (IDE, container, app server có thể khác terminal cá nhân).

```bash
# Khi dùng alias trong TNSNAMES, kiểm tra phương thức phân giải ở client.
tnsping ORDER_APP
```

Với Easy Connect, so sánh hostname/service với thông tin được DBA công bố. Kiểm tra DNS và đường TCP bằng công cụ mạng phù hợp hệ điều hành (`nslookup`, `Test-NetConnection` trên Windows, `nc -vz` trên Linux nếu có). Các phép thử mạng này chỉ cho biết khả năng đến endpoint, không thay thế đăng nhập Oracle.

### 11.2. Bước B: kiểm tra listener đang lắng nghe ở đâu

```bash
lsnrctl status LISTENER
lsnrctl services LISTENER
```

Đọc **Listening Endpoints Summary** để xác định host/port/protocol; đọc **Services Summary** và phần handler để biết service đã hiện diện, instance có `READY` không. Nếu máy có nhiều Oracle Home/listener, phải chỉ rõ tên listener và dùng đúng công cụ của home đang quản lý instance.

### 11.3. Bước C: kiểm tra service và PDB từ database

Các truy vấn sau chỉ đọc metadata; chạy từ tài khoản quản trị có quyền thích hợp:

```sql
-- Được đăng ký/định nghĩa ở database theo metadata view.
SELECT name, network_name, pdb, con_id
FROM   v$services
ORDER BY name;

-- Dịch vụ đang hoạt động ở instance hiện tại.
SELECT name, con_id
FROM   v$active_services
ORDER BY name;

-- Kiểm tra trạng thái mở các PDB khi truy vấn từ CDB root.
SELECT con_id, name, open_mode
FROM   v$pdbs
ORDER BY con_id;

-- Các đích listener mà instance được cấu hình đăng ký.
SELECT name, value
FROM   v$parameter
WHERE  name IN ('local_listener', 'remote_listener', 'service_names')
ORDER BY name;
```

Lưu ý: `V$SERVICES` và `V$ACTIVE_SERVICES` phản ánh khía cạnh khác nhau của metadata/trạng thái dịch vụ; chúng **không phải bản sao tức thời** của `lsnrctl services`. Trong RAC, cần xem **từng instance** (ví dụ thông qua `GV$...` thích hợp) và chính sách dịch vụ của Clusterware. `SERVICE_NAMES` chỉ nên kiểm tra để hiểu hệ thống legacy, không chủ động sửa vì đây là tham số đã deprecated cho customer use từ 19c.

### 11.4. Bước D: xác định registration có bị lệch không

Nếu database và service đang hoạt động mà listener không biết service:

1. Xác định listener cần đăng ký thực tế (host/port/protocol).
2. Đối chiếu `LOCAL_LISTENER`, `REMOTE_LISTENER` với địa chỉ đó, bao gồm tên alias và DNS resolve **trên database host**.
3. Xem listener có chặn registration theo chính sách mạng không.
4. Với listener vừa khởi động lại, chờ chu kỳ LREG hoặc quản trị viên dùng `ALTER SYSTEM REGISTER` sau khi xác minh điều kiện.
5. Đọc listener log, database alert log/trace theo thời điểm lỗi nếu vẫn không khớp.

Nếu PDB/service đóng, phải xử lý trạng thái PDB/service theo quy trình DBA trước; `ALTER SYSTEM REGISTER` không thể làm một service chưa chạy trở thành sẵn sàng.

### 11.5. Bước E: thử xác thực ở cuối đường

Khi listener và service có handler `READY`, thử đăng nhập với tài khoản hợp lệ. Nếu nhận `ORA-01017`, `ORA-28000`, `ORA-01045` hay lỗi quyền phiên, bước mạng/định tuyến đã tiến xa hơn giai đoạn `ORA-12514`; lúc đó kiểm tra credential, account status, `CREATE SESSION` và chính sách database, không chỉ sửa listener.

Lệnh trên database server như `sqlplus / as sysdba` có thể dùng **kết nối cục bộ không qua listener**. Nó chứng minh database có thể truy cập cục bộ, **không chứng minh Oracle Net remote đã cấu hình thành công**.

## 12. Bảng lỗi phổ biến: dấu hiệu và tầng cần kiểm tra

| Mã lỗi / hiện tượng | Khả năng liên quan | Hướng kiểm tra đầu tiên |
| --- | --- | --- |
| `ORA-12154` | Client không phân giải được connect identifier | `tnsnames.ora`, `TNS_ADMIN`, `NAMES.DIRECTORY_PATH`, cú pháp alias hoặc Easy Connect |
| `ORA-12541` / `TNS-12541` | Không tìm thấy listener tại endpoint yêu cầu | Host/port đúng chưa, process listener có chạy, firewall/route và protocol |
| `ORA-12514` | Listener hoạt động nhưng không biết service trong request | Tên `SERVICE_NAME`, `lsnrctl services`, service/PDB, LREG registration |
| `ORA-12505` | Listener không biết SID được request | Descriptor dùng `(SID=...)` cũ/sai, tên instance hoặc static registration; ưu tiên service đúng |
| `ORA-12516` / `ORA-12520` | Không tìm được handler phù hợp, hoặc handler không sẵn sàng | Dedicated/shared handler, tải, giới hạn `PROCESSES`/`SESSIONS`, trạng thái instance |
| `ORA-12528` | Listener thấy instance đang chặn kết nối mới | Instance/PDB đang khởi động, trạng thái restricted/blocking |
| `ORA-01017` | Sai thông tin đăng nhập hoặc cơ chế xác thực | User/password, tên PDB, proxy/external auth, chính sách account |
| `ORA-28000` | Tài khoản bị khóa | Account status và chính sách bảo mật; thao tác DBA có thẩm quyền |
| JDBC `IO Error`, `ORA-17002` | Lỗi I/O có nhiều nguyên nhân | Lấy nguyên nhân gốc trong exception chain, DNS, port, TLS, timeout, redirect |
| `tnsping` OK nhưng login fail | Naming/endpoint phản hồi, các tầng sau chưa chắc OK | Service registration, handler, xác thực, trạng thái PDB |

**Tránh sửa theo mã lỗi một cách máy móc.** Ví dụ, `ORA-12514` sau khi listener restart có thể chỉ do LREG chưa kịp đăng ký; cùng lỗi đó ở hệ thống lâu ngày có thể do client gọi sai service, PDB đóng, hoặc đăng ký đến listener khác. Giữ timestamp, listener address và connection identifier (nếu lỗi cung cấp) để tra log chính xác.

## 13. Ba tình huống thực tế

### Tình huống 1 — Listener `READY` nhưng gọi nhầm service

Client cấu hình:

```text
//db01.example.com:1521/ORCLCDB
```

Trong khi `lsnrctl services` chỉ có service `orders_rw.example.com` (ứng dụng cần vào `ORDERPDB`). TCP 1521 mở và listener sống, nhưng client có thể nhận `ORA-12514` cho tên `ORCLCDB` nếu tên đó chưa được đăng ký. Cách xử lý đúng: lấy **service name do DBA công bố cho ứng dụng**, cập nhật descriptor; không tạo static SID tùy tiện để giữ một connection string sai.

### Tình huống 2 — Listener chuyển sang port 1522, database vẫn đăng ký port 1521

DBA đã đổi listener endpoint thành `db01:1522`. Client cũng sửa URL sang `:1522`, nhưng `lsnrctl services` của listener mới không thấy service. Nếu instance tiếp tục đăng ký vào địa chỉ mặc định cũ, phải sửa cấu hình `LOCAL_LISTENER` theo endpoint mới (hoặc alias của nó), xác minh resolution **trên database server**, rồi đăng ký lại. Chỉ sửa `tnsnames.ora` phía client không làm LREG biết port mới.

### Tình huống 3 — SQL*Plus local vào được, ứng dụng từ xa không vào được

Trên server, `sqlplus / as sysdba` truy cập thành công, nhưng ứng dụng nhận `ORA-12541`. Kết nối `/ as sysdba` cục bộ có thể **không qua listener**, nên không bác bỏ được khả năng listener chưa chạy, sai port hay firewall chặn. Bắt đầu với host/port/protocol từ chính máy client và `lsnrctl status` trên máy server.

### Tình huống 4 — RAC kết nối đến SCAN được nhưng fail sau redirect

Client đến SCAN VIP và SCAN listener bình thường; listener chọn `orcl2` và chuyển client đến local listener của node 2. Nếu vùng mạng client không truy cập được node VIP đó, quá trình hoàn tất kết nối có thể thất bại. Kiểm tra **đường mạng sau redirect**, cùng trạng thái local listener/service trên node 2; không kết luận chỉ dựa vào phép thử TCP tới SCAN.

## 14. Thực hành tự kiểm tra (không thay đổi cấu hình)

Giả sử có quyền truy cập một database lab, thực hiện lần lượt:

1. Ghi chính xác chuỗi kết nối mà SQL*Plus/JDBC sử dụng; xác định đâu là host/port, alias và service.
2. Đọc `lsnrctl status` và `lsnrctl services` để xác định endpoint, tên service, instance và handler.
3. Dùng truy vấn chỉ đọc vào `V$SERVICES`, `V$ACTIVE_SERVICES`, `V$PDBS` (nếu là CDB) và `V$PARAMETER`.
4. Kết nối bằng **service thực** qua Easy Connect hoặc alias; sau login dùng `SYS_CONTEXT` xác nhận service/container/instance.
5. Tự giải thích vì sao `tnsping` thành công nhưng `ORA-12514` vẫn có thể xuất hiện và vì sao `sqlplus / as sysdba` không chứng minh listener hoạt động.

**Câu hỏi suy luận:**

**A.** `lsnrctl status` hiển thị `LISTENER` đang lắng nghe `:1521`, nhưng `lsnrctl services` không có `inventory_rw.example.com`. Client nên lập tức thay đổi password không?

**B.** `lsnrctl services` hiển thị một instance `status UNKNOWN`. Chắc chắn database đã shutdown không?

**C.** Sau restart listener, service biến mất khỏi output trong vài chục giây rồi xuất hiện. Thành phần nào có thể giải thích hiện tượng?

**D.** Ứng dụng dùng Oracle RAC nhưng connection string trỏ cố định đến `node01` và SID `orcl1`. Nhược điểm vận hành là gì?

<details>
<summary>Gợi ý đáp án</summary>

**A.** Không. `ORA-12514`/service chưa đăng ký xảy ra trước giai đoạn xác thực; trước hết kiểm tra service name, PDB/service đang hoạt động và LREG.

**B.** Không. `UNKNOWN` thường xuất hiện ở static registration, nơi listener không biết trạng thái runtime thực tế.

**C.** LREG đăng ký động theo chu kỳ. Có thể chờ chu kỳ tiếp theo hoặc DBA chủ động `ALTER SYSTEM REGISTER` nếu cần.

**D.** Ứng dụng phụ thuộc một node/instance cụ thể, giảm khả năng dùng SCAN, chuyển dịch service, routing theo tải và chính sách HA; nên thiết kế theo service và SCAN phù hợp.

</details>

## 15. Các nguyên tắc cần giữ khi vận hành

- **Service là hợp đồng logic** giữa workload và database; ưu tiên service do DBA quản lý cho ứng dụng, nhất là với PDB và RAC.
- **Listener chỉ là tầng định tuyến kết nối đầu tiên**; kiểm tra service/handler và xác thực trước khi kết luận kết nối hoàn chỉnh.
- **LREG đăng ký động**, với `LOCAL_LISTENER` và `REMOTE_LISTENER` quyết định các listener nhận thông tin, không bắt buộc `SID_LIST` cho mọi service.
- **Một listener chạy chưa chắc một service sẵn sàng**; `lsnrctl services` có ý nghĩa hơn kiểm tra port đơn thuần.
- **Client alias, service name, SID và hostname khác nhau**; phải kiểm tra từng lớp khi chẩn đoán.
- **RAC/Clusterware có quy trình quản lý riêng**; tôn trọng SCAN, local listener, SRVCTL và chính sách service của hệ thống.
- **Kết nối local không thay thế kiểm tra remote**; `tnsping` cũng không thay thế truy vấn/xác thực thực tế.

## 16. Tài liệu Oracle chính thức để đọc thêm

1. [Oracle Database 19c Net Services Administrator's Guide — Identifying and Accessing the Database](https://docs.oracle.com/en/database/oracle/oracle-database/19/netag/identifying-and-accessing-database.html): service name, listener, handler, dedicated/shared server và kết nối thực tế.
2. [Oracle Database 19c — Configuring and Administering Oracle Net Listener](https://docs.oracle.com/en/database/oracle/oracle-database/19/netag/configuring-and-administering-oracle-net-listener.html): cấu hình listener, LREG, `lsnrctl STATUS/SERVICES`, trạng thái handler và static registration.
3. [Oracle Database 19c RAC Installation Guide — Database Initialization Parameters for Service Registration](https://docs.oracle.com/en/database/oracle/oracle-database/19/rilin/database-initialization-parameters-for-database-service-registration.html): `LOCAL_LISTENER`, `REMOTE_LISTENER`, LREG và `ALTER SYSTEM REGISTER`.
4. [Oracle Database 19c — Configuring Naming Methods](https://docs.oracle.com/en/database/oracle/oracle-database/19/netag/configuring-naming-methods.html): Easy Connect, `tnsnames.ora`, `sqlnet.ora` và thứ tự tra cứu.
5. [Oracle Database 19c — Managing Services for PDBs](https://docs.oracle.com/en/database/oracle/oracle-database/19/multi/administering-pdbs-with-sql-plus.html): service mặc định và user-defined service, `PDB` property, SRVCTL/DBMS_SERVICE.
6. [Oracle Database 19c — Creating Database Services](https://docs.oracle.com/en/database/oracle/oracle-database/19/admin/creating-and-configuring-an-oracle-database.html): phương pháp quản lý service và lưu ý `SERVICE_NAMES` deprecated.
7. [Oracle Database 19c RAC — Connecting Using SCANs](https://docs.oracle.com/en/database/oracle/oracle-database/19/riwin/about-connecting-to-an-oracle-rac-database-using-scans.html): tuyến SCAN listener → local listener và định tuyến dịch vụ RAC.
8. [Oracle Database 19c — Troubleshooting Oracle Net Services](https://docs.oracle.com/en/database/oracle/oracle-database/19/netag/troubleshooting-oracle-net-services.html) và [Oracle Error Help — ORA-12514](https://docs.oracle.com/en/error-help/db/ora-12514/): nguyên nhân lỗi theo từng tầng.

**Tư duy cần nhớ:** định danh client **→** naming resolution **→** listener endpoint **→** LREG-registered service **→** handler **→** authentication/session. Khi có lỗi, xác định nó dừng ở mắt xích nào và kiểm tra bằng chứng ở đúng tầng đó.
