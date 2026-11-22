# Service của PDB và định tuyến kết nối ứng dụng trong Oracle

Khi làm việc với Oracle Database theo kiến trúc **multitenant**, ứng dụng thường không kết nối trực tiếp bằng tên instance hay một thư mục chứa datafile. Ứng dụng yêu cầu kết nối đến **service**; Oracle Net sử dụng service này để tìm nơi có thể phục vụ kết nối và đưa phiên làm việc vào **PDB** phù hợp. Nếu cấu hình sai service, chương trình có thể kết nối nhầm container, nhìn thấy schema khác hoặc báo lỗi dù database và listener vẫn đang chạy.

Bài học giải thích mối quan hệ giữa **CDB**, **PDB**, **service**, **listener**, **instance** và **client**; cách định tuyến kết nối từ Java/JDBC; cách tạo, khởi động, kiểm tra service; cùng phương pháp chẩn đoán khi một service không truy cập được.

## 1. Từ CDB đến PDB: ứng dụng thật sự kết nối vào đâu?

Trong kiến trúc Oracle multitenant:

- **CDB (Container Database)** là database chứa root, seed và các PDB. CDB được mở và vận hành bởi một hoặc nhiều Oracle instance.
- **CDB$ROOT** là container gốc phục vụ thông tin và quản trị chung. Đây thường không phải đích truy cập nghiệp vụ của ứng dụng.
- **PDB$SEED** là template dùng để tạo PDB; không phải đích truy cập ứng dụng thông thường.
- **PDB (Pluggable Database)** là container logic có schema, đối tượng và dữ liệu ứng dụng. Một CDB có thể có nhiều PDB.
- **Schema/user** là chủ sở hữu đối tượng và danh tính truy cập trong container; nhiều user/schema có thể cùng tồn tại trong một PDB.
- **Service** là tên logic mà client yêu cầu để được đưa đến dịch vụ dữ liệu, thường gắn với một PDB cụ thể.

Ví dụ:

~~~text
                           CDB: CORPDB
                    ┌──────────────────────────┐
                    │ CDB$ROOT                 │
                    │ PDB$SEED                 │
                    │                          │
                    │ ┌──────────────────────┐ │
                    │ │ SALES_PDB            │ │
                    │ │ SALES_APP, REPORT_APP│ │
                    │ │ ORDERS, CUSTOMERS... │ │
                    │ └──────────────────────┘ │
                    │                          │
                    │ ┌──────────────────────┐ │
                    │ │ HR_PDB               │ │
                    │ │ HR_APP, EMPLOYEES... │ │
                    │ └──────────────────────┘ │
                    └──────────────────────────┘
                             ▲          ▲
                             │          │
          sales_app.example.com          hr_app.example.com
                (service)                     (service)
                             ▲          ▲
                             └────┬─────┘
                                  │
                   Client / Listener / Instance
~~~

Ở ví dụ này, hai ứng dụng có thể sử dụng **cùng một host và port**, nhưng yêu cầu **service name khác nhau** để được kết nối tới hai PDB. Khi client đã vào `SALES_PDB`, user `SALES_APP` hay `REPORT_APP` quyết định danh tính và các quyền có sẵn; service không tự biến hai user thành một.

> **Câu hỏi định hướng:** *Kết nối vào service nào?* giúp xác định đích logic. *Session thực tế ở PDB nào?* giúp xác nhận vị trí dữ liệu. *Đăng nhập bằng user nào?* giúp xác định schema mặc định và quyền. Đây là ba câu hỏi riêng biệt.

## 2. Service là gì và có quan hệ thế nào với PDB?

**Database service** là một tên logic do Oracle cung cấp để client kết nối tới workload hoặc dịch vụ dữ liệu. Trong CDB, service ứng dụng thường được **gắn với một PDB**; các kết nối thông qua service đó được thiết lập trong container đích.

Các quan hệ cơ bản:

| Cặp khái niệm | Quan hệ đúng | Ví dụ |
|---|---|---|
| **CDB – PDB** | Một CDB chứa nhiều PDB | `CORPDB` chứa `SALES_PDB` và `HR_PDB` |
| **PDB – service** | Một PDB có thể có **nhiều service** | `SALES_PDB` phục vụ `sales_app.example.com` và `sales_report.example.com` |
| **Service – instance** | Một service có thể được cung cấp bởi một hoặc nhiều instance, tùy triển khai | Trong RAC, service Sales chạy trên các instance được quản lý |
| **Service – listener** | Listener nhận yêu cầu Oracle Net và xác định handler cho service đã được đăng ký | Listener biết `sales_app.example.com` có thể được phục vụ ở đâu |
| **Service – schema** | Service chọn đích kết nối; schema/user là danh tính và đối tượng bên trong PDB | `sales_app.example.com` dẫn tới `SALES_PDB`, user `SALES_APP` đăng nhập |
| **Service – SID** | Service là đích logic; SID nhận diện instance | `sales_app.example.com` khác `corp1` |

Một **service không phải bản sao dữ liệu**. Hai service cùng dẫn đến `SALES_PDB` không mặc nhiên tạo hai bộ dữ liệu, hai transaction log hoặc hai schema riêng. Ta có thể chia service theo ứng dụng hoặc lớp workload, nhưng việc cách ly quyền phải dựa vào **user, role, privilege**, và các cơ chế kiểm soát thích hợp.

### Tên service có nhất thiết trùng tên PDB?

**Không.** Khi tạo PDB, Oracle thường cung cấp một **default service** gắn với PDB; tên mặc định này thường dựa trên tên PDB và cách định danh domain của database. Nhưng quản trị viên có thể tạo **service dành riêng cho ứng dụng** với network name như `sales_app.example.com`.

Chẳng hạn:

~~~text
PDB: SALES_PDB
    ├── Default PDB service (phục vụ kết nối cơ bản)
    ├── sales_app.example.com       ── Ứng dụng giao dịch
    ├── sales_report.example.com    ── Ứng dụng báo cáo
    └── sales_batch.example.com     ── Job chạy theo lô
~~~

Ba service trên có thể dẫn đến **cùng SALES_PDB**. Việc đặt tên service với hậu tố `_ro`, `_rw` hoặc `_batch` chỉ là cách mô tả mục đích: tên `_ro` **không tự biến PDB thành read-only**. Nếu cần hạn chế cập nhật, phải cấu hình quyền phù hợp hoặc triển khai workload trên đích/role đáp ứng chính sách đó.

## 3. Luồng định tuyến kết nối từ ứng dụng đến PDB

Giả sử một ứng dụng Java sử dụng:

~~~text
jdbc:oracle:thin:@//db.example.internal:1521/sales_app.example.com
~~~

Luồng xử lý thường được hiểu theo các bước:

1. **Client phân giải địa chỉ** `db.example.internal` qua DNS hoặc cấu hình mạng, sau đó tạo kết nối Oracle Net tới host và port `1521`.
2. **Listener tiếp nhận yêu cầu** với connect data, trong đó có `SERVICE_NAME=sales_app.example.com`. Listener là tiến trình lắng nghe kết nối, **không phải** PDB hay chính service.
3. **Service đã được đăng ký với listener** cùng thông tin instance/handler có thể phục vụ. Listener chọn cách chuyển hoặc bàn giao yêu cầu tới tiến trình/phía instance thích hợp.
4. **Oracle server tạo session** cho yêu cầu kết nối, gắn session với container tương ứng với service, trong ví dụ là `SALES_PDB`.
5. **Oracle xác thực user** và thiết lập ngữ cảnh session. Kể từ đó SQL được phân giải trong PDB, schema và quyền của session.
6. **Connection pool giữ các kết nối đã mở** để ứng dụng tái sử dụng; service được yêu cầu khi tạo kết nối vật lý mới, không phải mỗi câu SQL riêng lẻ.

~~~text
Ứng dụng Java
    |
    | Oracle JDBC URL
    | db.example.internal:1521 / sales_app.example.com
    v
DNS / Oracle Net connect descriptor
    |
    v
Oracle Listener :1521
    |  yêu cầu SERVICE_NAME
    |  tìm handler đã đăng ký
    v
Instance/server process phục vụ service
    |
    v
CDB CORPDB
    |
    └── PDB SALES_PDB
         |
         ├── Xác thực SALES_APP
         ├── Áp quyền của SALES_APP
         └── Truy vấn SALES_APP.ORDERS
~~~

Đây là sơ đồ **logic** cho một lần kết nối. Trong Oracle RAC hoặc một cấu hình cân bằng tải, listener có thể chuyển hướng client sang listener/instance khác; cách kết nối thực tế tùy driver và thiết kế Oracle Net. Phân giải tên service giúp chọn đích logic, trong khi chọn instance/handler là bước định tuyến vật lý.

### Vai trò của listener và cơ chế đăng ký service

Listener biết những service nào có thể nhận kết nối thông qua **service registration**. Trên hệ thống Oracle hiện đại, tiến trình đăng ký như **LREG** cung cấp thông tin service/instance tới listener; cấu hình `LOCAL_LISTENER` và trong môi trường RAC có thể có `REMOTE_LISTENER` liên quan đến nơi đăng ký.

Điều quan trọng:

- **Listener đang chạy** chưa chắc **service đang được listener biết đến**.
- **Instance đang chạy** chưa chắc **PDB đã mở**.
- **PDB mở** chưa chắc **service tùy chỉnh đã được start**.
- **Service được đăng ký** chưa chắc **user/password đúng** hoặc ứng dụng có quyền vào schema.

Vì thế khi có lỗi kết nối, hãy kiểm tra từng mắt xích, thay vì chỉ thử restart toàn bộ database.

## 4. SERVICE_NAME, SID, PDB name, DB_NAME và TNS alias

Những tên sau thường xuất hiện cùng lúc nhưng có vai trò khác nhau:

| Tên | Đại diện cho | Dùng ở đâu? |
|---|---|---|
| **`DB_NAME`** | Tên database theo cấu hình Oracle | Nhận diện database/CDB ở mức quản trị |
| **`INSTANCE_NAME` / SID** | Instance Oracle đang chạy | Quản trị instance, một số kiểu kết nối cũ |
| **`PDB name`** | Tên container logic | Quản trị PDB, kiểm tra `CON_NAME` |
| **`SERVICE_NAME`** | Đích logic client yêu cầu | JDBC URL, Oracle Net connect descriptor |
| **TNS alias** | Tên bí danh phía client cho một connect descriptor | `tnsnames.ora` hoặc cấu hình Oracle Net |
| **Schema/user** | Danh tính hoặc chủ sở hữu đối tượng | Login và câu SQL, ví dụ `SALES_APP.ORDERS` |

Ví dụ các giá trị hoàn toàn có thể khác nhau:

~~~text
DB_NAME       = CORPDB
INSTANCE_NAME = corp1
PDB_NAME      = SALES_PDB
SERVICE_NAME  = sales_app.example.com
TNS_ALIAS     = SALES_PROD
SESSION_USER  = SALES_APP
~~~

Trong một ứng dụng cần chọn **PDB**, hãy ưu tiên kết nối theo **service name** thích hợp. Một chuỗi kiểu `host:port:SID` nhắm vào instance, không mô tả rõ PDB cần đến; nó đặc biệt dễ gây nhầm lẫn trong môi trường CDB/PDB hoặc RAC.

### Easy Connect, TNS alias và connect descriptor

Ba cách sau có thể biểu diễn cùng đích logic:

**Easy Connect / JDBC Thin URL:**

~~~text
//db.example.internal:1521/sales_app.example.com

jdbc:oracle:thin:@//db.example.internal:1521/sales_app.example.com
~~~

**Một entry trong `tnsnames.ora` trên máy client:**

~~~text
SALES_PROD =
  (DESCRIPTION =
    (ADDRESS = (PROTOCOL = TCP)
               (HOST = db.example.internal)
               (PORT = 1521))
    (CONNECT_DATA =
      (SERVICE_NAME = sales_app.example.com)))
~~~

**Client dùng alias khi cấu hình Oracle Net phù hợp:**

~~~text
sqlplus SALES_APP@SALES_PROD
~~~

SQL*Plus sẽ hỏi mật khẩu nếu không ghi ngay trong command line. `SALES_PROD` chỉ là **alias client**, không nhất thiết là service đã đăng ký trên database. Entry alias có thể trỏ tới nhiều host hoặc có cấu hình retry/timeout, nhưng `SERVICE_NAME` trong descriptor mới chỉ ra service Oracle Net cần tìm.

## 5. Default PDB service và application service

Sau khi một PDB được tạo, Oracle thường có service mặc định đi cùng tên PDB để kết nối cơ bản. Tuy nhiên, với ứng dụng tồn tại lâu dài, **service riêng theo ứng dụng hoặc workload** thường dễ quản lý hơn.

| Tiêu chí | Default PDB service | Service dành riêng cho ứng dụng |
|---|---|---|
| Mục đích | Đảm bảo PDB có điểm kết nối cơ bản | Định danh app/workload độc lập với tên PDB |
| Tên | Thường gắn với tên PDB | Do kiến trúc/DBA đặt theo quy ước |
| Vòng đời | Liên quan đến PDB và chế độ mở | Cần quản lý trạng thái start/stop và cấu hình phù hợp |
| Khả năng cấu hình workload/HA | Giới hạn hơn tùy nền tảng/cơ chế | Phù hợp hơn để quản lý qua công cụ hỗ trợ như SRVCTL trong RAC |
| Thay đổi bên dưới | App có thể phụ thuộc vào tên PDB | Tên ứng dụng giữ ổn định hơn khi cấu trúc triển khai thay đổi có kiểm soát |

Lý do dùng application service:

- **Tách cấu hình ứng dụng khỏi tên vật lý** của database/instance.
- **Điều khiển nơi workload chạy** trong các cấu hình có nhiều instance.
- **Chủ động vận hành:** có thể dừng service của một ứng dụng khi bảo trì mà không đồng nghĩa dừng toàn bộ CDB.
- **Phân loại kết nối** để vận hành và theo dõi; trong môi trường hỗ trợ, service còn được dùng cùng các tính năng availability và workload management.

Ứng dụng cần service name ổn định trong cấu hình. Nếu ngày mai hệ thống chuyển sang instance khác hoặc cấu trúc host thay đổi, DBA có thể điều chỉnh phía Oracle Net/service và danh sách địa chỉ, giảm việc phải sửa tên SID trong mã Java.

## 6. Tạo và vận hành service trong môi trường single-instance

Ví dụ minh họa CDB `CORPDB` chứa `SALES_PDB`, cần tạo service:

~~~text
Service nội bộ:   sales_app_svc
Network name:     sales_app.example.com
PDB đích:         SALES_PDB
~~~

**Điều kiện:** bạn có quyền quản trị cần thiết, PDB tồn tại và có thể mở. Cú pháp/khả năng của `DBMS_SERVICE` phụ thuộc phiên bản và loại môi trường; nếu database được quản lý bởi Oracle Restart/RAC/Clusterware, nên quản lý service bằng công cụ tương ứng thay vì tự tạo service cạnh tranh bằng các API khác.

### Bước 1 — kiểm tra PDB trước khi cấu hình

Từ một session quản trị ở CDB root:

~~~sql
SHOW CON_NAME

SELECT name, open_mode
FROM v$pdbs
WHERE name = 'SALES_PDB';
~~~

Nếu PDB chưa mở, khi đã xác định phù hợp với quy trình vận hành:

~~~sql
ALTER PLUGGABLE DATABASE SALES_PDB OPEN READ WRITE;
~~~

Trong môi trường muốn giữ trạng thái mở PDB qua khởi động lại CDB, có thể cấu hình saved state:

~~~sql
ALTER PLUGGABLE DATABASE SALES_PDB SAVE STATE;
~~~

`SAVE STATE` lưu trạng thái mở mong muốn của PDB cho các lần khởi động tương ứng; nó **không đồng nghĩa** bảo đảm mọi service tự start theo mọi kiểu triển khai. Service vẫn phải được quản lý với chính sách khởi động thích hợp.

### Bước 2 — chuyển vào đúng PDB

~~~sql
ALTER SESSION SET CONTAINER = SALES_PDB;

SELECT SYS_CONTEXT('USERENV', 'CON_NAME') AS current_container
FROM dual;
~~~

Kết quả kỳ vọng là `SALES_PDB`. Tạo service trong **đúng ngữ cảnh PDB** giúp tránh cấu hình một service không thuộc container mong muốn.

### Bước 3 — tạo và start application service

Trong môi trường single-instance không dùng công cụ Clusterware quản lý service, một ví dụ là:

~~~sql
BEGIN
  DBMS_SERVICE.CREATE_SERVICE(
    service_name => 'sales_app_svc',
    network_name => 'sales_app.example.com'
  );
END;
/

BEGIN
  DBMS_SERVICE.START_SERVICE(
    service_name => 'sales_app_svc'
  );
END;
/
~~~

Ở đây:

- `service_name` là tên quản trị nội bộ của service khi gọi package.
- `network_name` là tên có thể được Oracle Net client yêu cầu.
- Vì ví dụ đang chạy **trong `SALES_PDB`**, service được tạo cho PDB đó theo ngữ cảnh và cơ chế được phiên bản hỗ trợ.
- `START_SERVICE` làm service khả dụng tại runtime; tạo metadata thôi chưa chắc service đã sẵn sàng nhận kết nối.

Nếu service đã có sẵn, không chạy lại `CREATE_SERVICE` mù quáng. Nên kiểm tra service hiện có, trạng thái đăng ký và chính sách quản lý trước khi thay đổi.

### Bước 4 — xác nhận đăng ký với listener

Trên máy Oracle server, từ hệ điều hành và khi dùng listener mặc định:

~~~bash
lsnrctl status
lsnrctl services
~~~

`lsnrctl services` cung cấp thông tin những service/instance/handler mà listener đang biết. Nếu hệ thống dùng listener không mặc định hoặc cấu hình RAC/SCAN, phải quan sát **listener liên quan đến endpoint client** đang dùng, không chỉ một listener ngẫu nhiên trên host.

Môi trường image Docker/VM thường có tên listener và cổng khác mặc định; kiểm tra theo cấu hình thực tế. Có thể có độ trễ ngắn giữa lúc service khởi động và lúc listener nhận thông tin đăng ký. Nếu service không xuất hiện, kiểm tra trạng thái PDB, service và việc đăng ký listener.

### Bước 5 — kiểm tra từ một phiên client thật

Đăng nhập bằng user **đã tồn tại trong `SALES_PDB`**:

~~~bash
sqlplus SALES_APP@//db.example.internal:1521/sales_app.example.com
~~~

SQL*Plus sẽ yêu cầu mật khẩu. Sau khi đăng nhập, chạy truy vấn kiểm tra container/service ở phần tiếp theo.

### Dừng service khi bảo trì

Trong môi trường quản lý service qua `DBMS_SERVICE`, có thể sử dụng package để dừng service:

~~~sql
BEGIN
  DBMS_SERVICE.STOP_SERVICE(
    service_name => 'sales_app_svc'
  );
END;
/
~~~

Hành động dừng service ảnh hưởng tới **khả năng nhận kết nối mới** qua service đó; cách xử lý các session đang tồn tại phụ thuộc phương thức vận hành và công cụ quản lý. Không mặc định `STOP_SERVICE` là cách chấm dứt ngay mọi transaction của ứng dụng. Khi bảo trì, cần phối hợp connection pool, ngừng nhận traffic, chờ các giao dịch và dùng đúng cơ chế drain/service relocation nếu nền tảng hỗ trợ.

## 7. Quản lý service khi dùng Oracle RAC hoặc Oracle Restart

Trong **Oracle RAC**, nhiều instance có thể mở cùng một CDB/database. Một PDB có thể được ứng dụng truy cập qua service chạy trên một hoặc nhiều instance. Để quản lý lifecycle, vị trí chạy, chính sách tự khởi động và HA, Oracle sử dụng **Oracle Clusterware/SRVCTL** trong môi trường phù hợp.

~~~text
                      Application
                          |
                          v
                   SCAN / Oracle Net
                          |
                    Service: SALES_APP
                          |
             +------------+------------+
             |                         |
             v                         v
        Instance corp1            Instance corp2
             |                         |
             +------------+------------+
                          |
                     CDB CORPDB
                          |
                     SALES_PDB
~~~

Ở đây, hai instance có thể phục vụ **cùng một PDB** trên **cùng bộ dữ liệu của CDB**. Không phải có hai bản `SALES_PDB` độc lập chỉ vì có hai instance.

Ví dụ minh họa lệnh quản trị RAC:

~~~bash
# Ví dụ mô tả - thay DB_UNIQUE_NAME/instance theo cấu hình thật.
srvctl add service -db CORPDB -service sales_app -pdb SALES_PDB -preferred corp1,corp2

srvctl start service -db CORPDB -service sales_app

srvctl status service -db CORPDB -service sales_app
~~~

Tùy phiên bản Oracle, chính sách service, chế độ quản lý database và RAC topology, tùy chọn `srvctl` có thể khác; thực tế DBA phải dùng cú pháp chính thức phù hợp triển khai. Ví dụ tập trung vào ý tưởng: **service gắn với PDB và được Clusterware quản lý trên các instance**.

### SCAN, listener và service trong RAC

**SCAN (Single Client Access Name)** là điểm truy cập ổn định cho RAC; client kết nối theo SCAN name/port, sau đó listener đưa yêu cầu tới instance đang cung cấp service. Service có thể di chuyển giữa các instance trong phạm vi cấu hình. Vì vậy:

- **Không hard-code SID của một node** làm đích duy nhất nếu ứng dụng cần khả năng chuyển hướng khi node đó không còn phục vụ.
- **Không coi SCAN là service**: SCAN là tên/địa chỉ mạng; service mới định danh workload.
- **Không coi service là IP cố định**: một service có thể được phục vụ bởi nhiều instance hoặc thay đổi vị trí.

Các tính năng như **FAN**, **Fast Connection Failover**, **Application Continuity**, **Transaction Guard** hoặc kết nối có cơ chế cân bằng tải có thể hỗ trợ tính sẵn sàng tùy phiên bản, loại driver/connection pool và cấu hình service. Chỉ đặt tên service không tự kích hoạt đầy đủ các cơ chế đó; ứng dụng cần cấu hình client và kiểm thử hành vi khi sự cố xảy ra.

## 8. Cấu hình Oracle JDBC cho ứng dụng Java

Với JDBC Thin, dạng Easy Connect phổ biến là:

~~~text
jdbc:oracle:thin:@//host:port/service_name
~~~

Ví dụ:

~~~text
jdbc:oracle:thin:@//db.example.internal:1521/sales_app.example.com
~~~

Khi mã Java chạy trên máy host, hostname là máy mà client có thể truy cập. Khi ứng dụng và Oracle chạy trong **hai container cùng mạng Docker Compose**, hostname có thể là **tên service Compose**, ví dụ `db`; `localhost` bên trong container Java **không phải** container Oracle:

~~~text
Java chạy trên host:       jdbc:oracle:thin:@//localhost:1521/SALES_PDB
Java trong mạng Compose:   jdbc:oracle:thin:@//db:1521/SALES_PDB
Môi trường doanh nghiệp:  jdbc:oracle:thin:@//db.example.internal:1521/sales_app.example.com
~~~

Ba ví dụ sử dụng những network endpoint khác nhau. `SALES_PDB` trong hai ví dụ lab là tên service **chỉ khi** Oracle đã cung cấp/đăng ký service đó; phải xác nhận tên thực tế thay vì suy đoán mọi hệ thống đều dùng đúng chữ đó.

### JDBC thuần với `DriverManager`

~~~java
import java.sql.Connection;
import java.sql.DriverManager;
import java.sql.ResultSet;
import java.sql.Statement;

public class OraclePdbServiceDemo {
    public static void main(String[] args) throws Exception {
        String url =
            "jdbc:oracle:thin:@//db.example.internal:1521/sales_app.example.com";
        String user = System.getenv("DB_USER");
        String password = System.getenv("DB_PASSWORD");

        try (Connection connection =
                 DriverManager.getConnection(url, user, password);
             Statement statement = connection.createStatement();
             ResultSet result = statement.executeQuery(
                 "SELECT " +
                 "SYS_CONTEXT('USERENV', 'CON_NAME') AS pdb_name, " +
                 "SYS_CONTEXT('USERENV', 'SERVICE_NAME') AS service_name, " +
                 "SYS_CONTEXT('USERENV', 'INSTANCE_NAME') AS instance_name " +
                 "FROM dual")) {

            if (result.next()) {
                System.out.println("PDB      = " + result.getString("PDB_NAME"));
                System.out.println("Service  = " + result.getString("SERVICE_NAME"));
                System.out.println("Instance = " + result.getString("INSTANCE_NAME"));
            }
        }
    }
}
~~~

Ví dụ giả định đã có Oracle JDBC driver tương thích trên classpath và đã đặt biến môi trường cho user/mật khẩu. Không đưa mật khẩu vào JDBC URL hay mã nguồn commit lên repository.

### Cấu hình trong Spring Boot

~~~properties
spring.datasource.url=jdbc:oracle:thin:@//db.example.internal:1521/sales_app.example.com
spring.datasource.username=${DB_USER}
spring.datasource.password=${DB_PASSWORD}
spring.datasource.driver-class-name=oracle.jdbc.OracleDriver
~~~

Đây là ví dụ cấu hình `application.properties`. Trong triển khai thật, cần cung cấp `DB_USER` và `DB_PASSWORD` qua secret manager hoặc cơ chế biến môi trường phù hợp. Ứng dụng phải dùng đúng driver và pool tương thích với phiên bản Oracle.

Nếu kết nối đã được tạo trong pool, thay URL/service trong config **chưa chắc** đổi đích của các kết nối vật lý đang sống. Phải thiết kế quy trình làm mới pool/rolling deployment, kết hợp xác minh service mới được đăng ký và có khả năng nhận kết nối.

## 9. Kiểm tra service, PDB và instance bằng SQL

### 9.1. Kiểm tra từ bất cứ session đăng nhập được

~~~sql
SELECT
  SYS_CONTEXT('USERENV', 'DB_NAME')       AS database_name,
  SYS_CONTEXT('USERENV', 'INSTANCE_NAME') AS instance_name,
  SYS_CONTEXT('USERENV', 'CON_NAME')      AS container_name,
  SYS_CONTEXT('USERENV', 'SERVICE_NAME')  AS service_name,
  SYS_CONTEXT('USERENV', 'SESSION_USER')  AS session_user,
  SYS_CONTEXT('USERENV', 'CURRENT_SCHEMA') AS current_schema
FROM dual;
~~~

Ví dụ kết quả:

~~~text
DATABASE_NAME INSTANCE_NAME CONTAINER_NAME SERVICE_NAME           SESSION_USER CURRENT_SCHEMA
------------- ------------- -------------- ---------------------- ------------ --------------
CORPDB        corp1         SALES_PDB      sales_app.example.com  SALES_APP    SALES_APP
~~~

Đây là bằng chứng trực tiếp rằng **session hiện tại** đang ở `SALES_PDB`, được thiết lập qua service tương ứng, chạy trên instance `corp1` và đăng nhập bằng user `SALES_APP`. Khi kiểm tra sự cố “kết nối được nhưng dữ liệu sai”, truy vấn này thường hữu ích hơn việc chỉ nhìn URL trong file cấu hình.

### 9.2. Xem PDB và trạng thái mở (cần quyền phù hợp)

Từ CDB root với quyền quản trị:

~~~sql
SELECT con_id, name, open_mode, restricted
FROM v$pdbs
ORDER BY con_id;
~~~

Nếu `SALES_PDB` đang ở `MOUNTED` hoặc chưa sẵn sàng, việc listener biết tên service không bảo đảm ứng dụng sẽ đăng nhập thành công. Để PDB tự mở theo trạng thái đã lưu trong những lần khởi động sau, DBA có thể xem xét `SAVE STATE` như phần quản trị ở trên.

### 9.3. Xem service được cấu hình và đang hoạt động

Ví dụ từ session có quyền đọc các dynamic performance views:

~~~sql
SELECT name, network_name, pdb
FROM v$services
ORDER BY name;
~~~

~~~sql
SELECT name, network_name, pdb
FROM v$active_services
ORDER BY name;
~~~

`V$SERVICES` thể hiện thông tin service; `V$ACTIVE_SERVICES` cho biết những service đang active theo phạm vi instance/view. Tùy container, quyền và phiên bản, tập dòng hiển thị có thể khác. Trong RAC, có thể cần các view dạng `GV$` và trạng thái Clusterware để hiểu service chạy ở những instance nào.

Không nên kết luận service khả dụng với **client bên ngoài** chỉ vì một query trong database trả về tên. Còn phải kiểm tra nó đã được listener ở endpoint tương ứng đăng ký, DNS/mạng hoạt động và client xác thực thành công.

### 9.4. Kiểm tra từ hệ điều hành

~~~bash
lsnrctl status
lsnrctl services
~~~

Hai lệnh này chạy tại máy/container có công cụ Oracle Net, không phải câu lệnh SQL. Chúng giúp xác nhận listener thực sự nhìn thấy service và handler. Trong RAC có thể phải kiểm tra đúng SCAN listener hoặc node listener; trong Docker cần lưu ý mapping host port.

## 10. Quy trình chẩn đoán khi ứng dụng không kết nối được

Giả sử Java cấu hình `jdbc:oracle:thin:@//db.example.internal:1521/sales_app.example.com` và báo lỗi. Hãy đi theo thứ tự từ mạng tới service, PDB và quyền:

~~~text
Ứng dụng không kết nối được
          |
          v
Host/port có tới listener?
     | không                  | có
     v                        v
DNS, network, firewall       Listener có đăng ký service?
                                | không            | có
                                v                  v
                           Service đã start?     PDB đã OPEN?
                           PDB có mở?               | không       | có
                           LREG/registration?       v             v
                                                 Mở PDB       User/password,
                                                               privilege,
                                                               connection pool
~~~

| Lỗi hoặc hiện tượng | Khả năng thường gặp | Kiểm tra trước |
|---|---|---|
| `ORA-12541: TNS:no listener` | Không đến được listener ở host/port yêu cầu | DNS, host, port, firewall, listener có chạy không |
| `ORA-12514` | Listener không biết service được yêu cầu | Kiểm tra `SERVICE_NAME`, `lsnrctl services`, service đang active và PDB open |
| `ORA-12505` | Yêu cầu SID không được listener nhận diện | Chuỗi kết nối dùng SID hay service; chuyển sang service name phù hợp |
| `ORA-12516` | Listener không tìm được handler phù hợp/sẵn sàng | Tài nguyên instance, session/process limits, trạng thái handler/service |
| `ORA-01017` | Thông tin xác thực bị từ chối | Username/password, container đích, user có tồn tại tại PDB không |
| `ORA-01033` hoặc thông báo database đang khởi động/đóng | Database/PDB chưa sẵn sàng phục vụ | Open mode, log khởi động, trạng thái service |
| Kết nối thành công nhưng `ORA-00942` khi truy vấn bảng | Sai PDB/schema hoặc thiếu quyền | `CON_NAME`, `CURRENT_SCHEMA`, tên chủ sở hữu bảng, grant |
| Đúng URL nhưng vào instance khác | Service có thể chạy trên nhiều instance hoặc được di chuyển | `INSTANCE_NAME`, chính sách RAC, listener/SCAN |
| Thay service nhưng pool vẫn kết nối đích cũ | Connection pool tái sử dụng session vật lý đã mở | Chuyển đổi có kế hoạch, refresh/drain pool, kiểm tra session mới |

### Ví dụ điều tra lỗi `ORA-12514`

1. Đọc URL và xác định chính xác `SERVICE_NAME` mà ứng dụng đang yêu cầu, chẳng hạn `sales_app.example.com`.
2. Ở đúng endpoint listener, dùng `lsnrctl services` để xem service đó có được đăng ký không.
3. Nếu không có, trong database kiểm tra `V$ACTIVE_SERVICES` và trạng thái `SALES_PDB`; service tùy chỉnh có thể chưa được start.
4. Kiểm tra cơ chế registration listener và các tham số liên quan nếu service active nhưng không xuất hiện trên listener.
5. Sau khi listener biết service và PDB mở, thử kết nối **mới** từ client rồi đọc `SYS_CONTEXT` để xác nhận PDB thật.

Tránh khắc phục bằng cách thay ngẫu nhiên `SERVICE_NAME` thành `SID` hoặc tên CDB. Làm vậy có thể chuyển sang kết nối khác mà không giải quyết việc service ứng dụng được đăng ký đúng.

### Ví dụ “kết nối được nhưng sai dữ liệu”

Trong một CDB, `HR_PDB` và `SALES_PDB` có thể đều chứa bảng `EMPLOYEES` hoặc user cùng tên. Nếu URL trỏ nhầm service, câu SQL vẫn có thể chạy nhưng đọc bộ dữ liệu khác. Hãy kiểm tra:

~~~sql
SELECT
  SYS_CONTEXT('USERENV', 'CON_NAME') AS pdb,
  SYS_CONTEXT('USERENV', 'SERVICE_NAME') AS service,
  SYS_CONTEXT('USERENV', 'SESSION_USER') AS login_user
FROM dual;
~~~

Khi `PDB` và `SERVICE` đã đúng, mới kiểm tra schema owner và quyền đối tượng. **Cùng host, cùng port hoặc cùng CDB chưa đủ để xác nhận đúng PDB.**

## 11. Service và tính sẵn sàng: định tuyến có nghĩa gì với ứng dụng?

Service tạo ra **điểm tên logic** cho workload, giúp tách cách ứng dụng gọi database khỏi danh tính vật lý của một instance. Tuy vậy, khả năng failover không xuất hiện tự động chỉ vì URL có service name.

### Trường hợp một instance

Nếu CDB chạy trên một instance và instance dừng, service không còn nơi phục vụ cho tới khi instance/database/PDB hoạt động trở lại. Có service không biến single-instance thành hệ thống HA.

### Trường hợp RAC nhiều instance

Một service có thể được quản lý trên nhiều instance hoặc được chuyển tới instance còn khả dụng theo chính sách. Connection pool/driver có thể cần cấu hình phù hợp để **nhận thông tin thay đổi** và tái tạo kết nối. Những transaction đang chạy dở phải tuân theo semantics của driver, database và tính năng HA được cấu hình; không thể mặc định mọi SQL đang chạy sẽ tiếp tục liền mạch.

### Read-write và read-only

Việc đặt service `sales_rw` và `sales_ro` có thể phục vụ mục đích kiến trúc, nhưng **tên gọi không áp dụng read-only**. Để có đích đọc riêng, DBA phải thiết kế môi trường và quyền thích hợp (ví dụ PDB mở read-only trong những ngữ cảnh được hỗ trợ, hoặc giải pháp reporting/standby phù hợp). Những chính sách đó phải được phối hợp với kết nối, transaction và dữ liệu cần nhất quán.

### Quản lý timeout và retry ở client

Ứng dụng nên có giới hạn thời gian tạo kết nối và chính sách retry hợp lý ở tầng Oracle Net/connection pool. Retry quá nhanh hoặc không giới hạn có thể gây bão kết nối khi database mới hồi phục. Timeout và retry không sửa được service name sai, user sai hoặc PDB đóng; phải phân biệt lỗi cấu hình với sự cố tạm thời.

## 12. Bài lab: hai PDB, hai service và một ứng dụng

Giả sử có:

~~~text
CDB: CORPDB
  ├── SALES_PDB
  │     service: sales_app.example.com
  │     local user: SALES_APP
  └── HR_PDB
        service: hr_app.example.com
        local user: HR_APP

Listener endpoint: db.example.internal:1521
~~~

Các service và user được giả định đã được DBA tạo đúng cách. Người học không cần tạo lại CDB chỉ để quan sát routing.

### Bước 1 — thử kết nối Sales

~~~bash
sqlplus SALES_APP@//db.example.internal:1521/sales_app.example.com
~~~

Sau khi nhập mật khẩu:

~~~sql
SELECT
  SYS_CONTEXT('USERENV', 'CON_NAME') AS pdb_name,
  SYS_CONTEXT('USERENV', 'SERVICE_NAME') AS service_name,
  SYS_CONTEXT('USERENV', 'SESSION_USER') AS session_user
FROM dual;
~~~

Kỳ vọng tương ứng:

~~~text
PDB_NAME   SERVICE_NAME           SESSION_USER
---------- ---------------------- ------------
SALES_PDB  sales_app.example.com  SALES_APP
~~~

### Bước 2 — thử kết nối HR

~~~bash
sqlplus HR_APP@//db.example.internal:1521/hr_app.example.com
~~~

Chạy cùng SQL `SYS_CONTEXT`:

~~~text
PDB_NAME SERVICE_NAME         SESSION_USER
-------- -------------------- ------------
HR_PDB   hr_app.example.com   HR_APP
~~~

Host/port không đổi; **service** thay đổi, nên PDB đích khác. User đăng nhập cũng thay đổi phù hợp với tài khoản local của từng PDB.

### Bước 3 — nếu có thêm một service trên SALES_PDB

Giả sử DBA tạo `sales_report.example.com` cùng gắn với `SALES_PDB`. Kết nối vào service mới bằng user được cấp quyền thích hợp, rồi kiểm tra `CON_NAME`:

~~~text
SERVICE_NAME               CON_NAME
-------------------------- ---------
sales_app.example.com      SALES_PDB
sales_report.example.com   SALES_PDB
~~~

Hai service cùng một PDB nhưng có thể được quản trị như hai workload khác nhau. **Không** suy ra `sales_report` chỉ đọc chỉ vì tên service; hãy thử bằng quyền truy cập và policy được cấu hình, không dùng thao tác ghi tùy ý trên dữ liệu quan trọng.

### Bước 4 — gắn vào ứng dụng Java

Đặt URL JDBC vào biến cấu hình của ứng dụng. Sau khi tạo kết nối, chạy SQL đọc `CON_NAME` và `SERVICE_NAME` như ở phần JDBC. Nếu thay service trong cấu hình, làm mới connection pool để kiểm tra kết nối vật lý mới thực sự dùng service vừa chọn.

### Bước 5 — quan sát tác động khi PDB đóng (chỉ trong lab được phép)

DBA có thể dừng nhận kết nối của PDB/service trong môi trường thử nghiệm và dùng client tạo **kết nối mới** để quan sát lỗi. Sau đó DBA mở lại PDB và start/register service theo quy trình môi trường. Khi thao tác, phải hiểu rằng các kết nối cũ, transaction đang mở và khả năng nhận kết nối mới có thể có hành vi khác nhau. Không đóng PDB dùng chung chỉ để thực hành.

## 13. Những nhầm lẫn phổ biến

1. **“Service chính là PDB.”** Không. Service là tên logic phục vụ kết nối; PDB là container chứa schema và dữ liệu. Một PDB có thể có nhiều service.
2. **“Một service bắt buộc bằng tên PDB.”** Không. Default service thường liên quan tên PDB, còn application service có thể mang tên riêng.
3. **“SID và SERVICE_NAME thay thế cho nhau.”** Không. SID định danh instance; service định danh workload/đích logic, đặc biệt quan trọng với PDB và RAC.
4. **“Đến đúng listener là chắc chắn vào đúng PDB.”** Không. Listener có thể biết nhiều service; client phải yêu cầu đúng service.
5. **“PDB mở là mọi application service tự hoạt động.”** Không thể mặc định. Cần kiểm tra trạng thái start/registration của service và chính sách quản lý thực tế.
6. **“Chỉ cần đổi service URL là kết nối pool hiện có lập tức chuyển PDB.”** Không. Kết nối vật lý đã mở vẫn giữ session của nó; phải quản lý pool/connection lifecycle.
7. **“Service tên read_only tự chặn lệnh UPDATE.”** Không. Phải dựa vào trạng thái database/standby, quyền và chính sách thực sự.
8. **“Service tự bảo đảm failover cho mọi transaction.”** Không. Kết quả phụ thuộc HA architecture, driver, pool và các tính năng availability được bật.
9. **“Lỗi ORA-12514 chỉ do username/password sai.”** Không. Nó thường báo listener không nhận diện service đã yêu cầu; lỗi xác thực thuộc bước khác.
10. **“Kết nối thành công chứng minh đã ở đúng môi trường.”** Không. Luôn kiểm tra `CON_NAME` và `SERVICE_NAME` khi có nghi vấn nhầm PDB.

## 14. Câu hỏi tự kiểm tra

**Câu 1.** Hai ứng dụng dùng cùng host và port `db.example.internal:1521`, nhưng service khác nhau. Chúng có thể kết nối vào hai PDB khác nhau không?

**Đáp án:** Có. Listener chọn đích theo service được đăng ký; hai service có thể gắn với hai PDB khác nhau trong cùng CDB.

**Câu 2.** `SALES_PDB` có service `sales_app.example.com` và `sales_report.example.com`. Chúng có nhất thiết chứa hai bộ dữ liệu độc lập không?

**Đáp án:** Không. Nếu cả hai service gắn cùng `SALES_PDB`, chúng phục vụ cùng container dữ liệu; quyền và cấu hình workload có thể khác.

**Câu 3.** Client nhận `ORA-12514` khi kết nối service `sales_app.example.com`. Có nên thay chuỗi kết nối thành `:corp1` (SID) ngay không?

**Đáp án:** Không. Trước tiên kiểm tra service name, trạng thái service, PDB và đăng ký listener; SID chỉ là một định danh instance, không thay thế ngữ nghĩa service/PDB.

**Câu 4.** DBA đã mở `SALES_PDB` nhưng chưa start application service được tạo riêng. Ứng dụng có chắc kết nối được qua service đó không?

**Đáp án:** Không. PDB mở và service active/được đăng ký là các điều kiện khác nhau. Kiểm tra `V$ACTIVE_SERVICES` và listener tương ứng.

**Câu 5.** Service đang được phục vụ bởi instance `corp2` thay vì `corp1` trong RAC. Ứng dụng có cần sửa tên PDB trong SQL không?

**Đáp án:** Không. Service vẫn định danh workload/PDB; instance vật lý có thể thay đổi theo cấu hình. Client/connection pool phải hỗ trợ kết nối lại theo đúng chính sách HA.

**Câu 6.** Một kết nối JDBC tới service Sales được trả về từ pool và chạy `SELECT` trong nhiều phút. DBA đổi mapping service cho kết nối **mới**. Session đang chạy có tự chuyển PDB không?

**Đáp án:** Không. Session đã kết nối giữ ngữ cảnh container hiện tại. Thay đổi service ảnh hưởng tới quá trình thiết lập kết nối theo cấu hình mới; cần quản lý session cũ và thời điểm drain/refresh pool.

## 15. Ghi nhớ bằng sơ đồ cuối

~~~text
             ỨNG DỤNG / CONNECTION POOL
                        |
                        | host + port + SERVICE_NAME
                        v
                  ORACLE NET / LISTENER
                        |
                        | service registration
                        v
                INSTANCE / SERVER PROCESS
                        |
                        | session được gắn với PDB của service
                        v
                      CDB
                        |
                        v
                       PDB
                        |
                        | user + password + privileges
                        v
                   SCHEMA / DATA
~~~

Để định tuyến kết nối Oracle chính xác, hãy **dùng service name dành cho ứng dụng**, xác nhận service **được đăng ký và đang active**, kiểm tra **PDB đã mở**, và khi đăng nhập thành công đọc `SYS_CONTEXT('USERENV', 'CON_NAME')` cùng `SERVICE_NAME` để xác minh đích thực tế. Khi triển khai RAC hoặc pool JDBC, service còn là điểm trung tâm để tổ chức workload và chuyển hướng kết nối, nhưng các chính sách failover, bảo mật và quản lý connection lifecycle vẫn cần được cấu hình riêng.
