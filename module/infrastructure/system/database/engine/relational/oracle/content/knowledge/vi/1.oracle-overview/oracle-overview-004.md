# Bản đồ thuật ngữ Oracle: database, instance, service, schema, CDB và PDB

Khi bắt đầu làm việc với Oracle Database, ta rất dễ nghe các câu như “kết nối vào database”, “restart instance”, “tạo schema”, “mở PDB” hoặc “đổi service”. Những câu này mô tả **những thành phần khác nhau** của cùng một hệ thống. Nhầm lẫn chúng có thể dẫn đến kết nối sai môi trường, cấp quyền nhầm chỗ, hoặc xử lý sự cố không đúng nguyên nhân.

Bài học này đặt sáu thuật ngữ quan trọng lên cùng một bản đồ: **database**, **instance**, **service**, **schema**, **CDB** và **PDB**. Mục tiêu là hiểu mỗi thuật ngữ trả lời câu hỏi nào, chúng liên hệ với nhau ra sao, và cách nhận diện chúng khi kết nối hoặc chạy SQL.

## 1. Bức tranh tổng thể

Trong ngữ cảnh kiến trúc Oracle, có thể đặt các khái niệm vào ba lớp:

1. **Lưu trữ và vận hành:** *database* là tập hợp dữ liệu và các tệp phục vụ việc lưu trữ, còn *instance* là bộ nhớ cùng các tiến trình vận hành database.
2. **Kết nối và đối tượng:** *service* là tên logic để ứng dụng truy cập một workload/database hoặc một PDB; *schema* là không gian tên các đối tượng do một user sở hữu.
3. **Tổ chức đa tenant:** *CDB* (Container Database) là database chứa các container; *PDB* (Pluggable Database) là một container có dữ liệu, schema và môi trường ứng dụng riêng bên trong CDB.

| Thuật ngữ | Câu hỏi mà nó trả lời | Ví dụ minh họa | Không nên đồng nhất với |
|---|---|---|---|
| **Database** | Dữ liệu Oracle thực sự nằm ở đâu, được tổ chức và duy trì như thế nào? | Database `CORPDB` với datafile, control file và redo log | Instance đang chạy |
| **Instance** | Thành phần nào đang sử dụng bộ nhớ và các tiến trình để mở, truy cập database? | Instance `corp1` | Toàn bộ database hoặc PDB |
| **Service** | Ứng dụng gọi tên nào để được đưa đến đúng dịch vụ dữ liệu? | `sales_rw.example.com` | SID, tên schema hoặc tên PDB |
| **Schema** | Bảng, view, sequence, package… thuộc về chủ sở hữu nào? | Schema `SALES_APP`, chứa `ORDERS` | Một database hoặc PDB riêng |
| **CDB** | Database này tổ chức nhiều container/PDB như thế nào? | CDB `CORPDB` | Một schema |
| **PDB** | Ứng dụng đang hoạt động trong đơn vị dữ liệu logic nào của CDB? | PDB `SALES_PDB` | Một instance riêng hoặc một schema |

> **Quy tắc định hướng:** “Tôi kết nối bằng tên gì?” thường là câu hỏi về **service**; “Tôi đang ở vùng dữ liệu nào?” là về **PDB**; “Tôi đang dùng bảng của ai?” là về **schema**; “Máy chủ nào đang xử lý truy vấn?” là về **instance**.

## 2. Database: tập hợp dữ liệu bền vững

Theo nghĩa kiến trúc, **Oracle database** là tập hợp các tệp vật lý lưu dữ liệu và thông tin cần thiết để quản lý, khôi phục dữ liệu. Các thành phần tiêu biểu:

- **Datafile:** lưu nội dung bảng, chỉ mục và các đối tượng cần lưu trữ khác thông qua các tablespace.
- **Control file:** chứa thông tin nhận diện và cấu trúc database, các tệp dữ liệu, checkpoint cùng thông tin phục vụ quản lý và phục hồi.
- **Online redo log:** ghi lại thông tin thay đổi để phục vụ phục hồi khi cần.

Database là phần **bền vững**: một instance có thể dừng, nhưng các tệp database vẫn tồn tại trên hệ thống lưu trữ. Khi khởi động lại, một instance có thể mở database từ những tệp đó.

Trong lời nói hằng ngày, “Oracle Database” đôi khi chỉ cả sản phẩm/hệ thống gồm database, instance và dịch vụ. Khi đọc sơ đồ kiến trúc hoặc phân tích lỗi, cần tách nghĩa vật lý của **database** khỏi **instance**.

### Database và tablespace khác nhau thế nào?

Một **tablespace** là đơn vị tổ chức lưu trữ logic bên trong database, được hiện thực bởi một hoặc nhiều datafile. **Schema** tổ chức đối tượng theo *chủ sở hữu*; **tablespace** tổ chức phần lưu trữ theo *vị trí/cấu trúc lưu trữ*. Một schema có thể có đối tượng nằm ở nhiều tablespace; một tablespace có thể chứa đối tượng thuộc nhiều schema.

## 3. Instance: bộ nhớ và các tiến trình chạy database

**Oracle instance** chủ yếu gồm:

- **SGA (System Global Area):** vùng bộ nhớ dùng chung, chẳng hạn database buffer cache và shared pool.
- **Background processes:** các tiến trình nền phục vụ ghi dữ liệu, ghi redo, khôi phục, giám sát và điều phối hoạt động, chẳng hạn DBWn, LGWR và CKPT.

Các **server process** xử lý yêu cầu SQL của phiên làm việc tương tác với instance; chúng thường được mô tả riêng, không phải thành phần định nghĩa cốt lõi của instance.

Có thể hình dung:

~~~text
Tệp database trên bộ lưu trữ
    ├── Datafiles
    ├── Control files
    └── Redo logs
             ▲
             │ mở và truy cập
             │
Instance đang chạy
    ├── SGA (bộ nhớ dùng chung)
    └── Background processes
~~~

Một số điểm quan trọng:

- **Single-instance:** thông thường một instance đang chạy mở một database.
- **Oracle RAC (Real Application Clusters):** nhiều instance trên các máy/nút khác nhau có thể đồng thời mở **cùng một database**. Mỗi instance có SGA và tiến trình của riêng mình; chúng cùng phối hợp truy cập dữ liệu.
- **SID (System Identifier):** nhận diện một instance trong ngữ cảnh cấu hình/kết nối kiểu SID. Trong RAC, mỗi instance có SID riêng. SID **không phải service name**.
- **Trạng thái khởi động:** quá trình thường đi qua `NOMOUNT` (instance đã khởi động), `MOUNT` (gắn control file), rồi `OPEN` (database mở cho hoạt động tương ứng). Vì vậy “instance đã chạy” chưa chắc nghĩa là người dùng có thể truy vấn dữ liệu.

Ví dụ, một CDB tên `CORPDB` có thể được mở bởi instance `corp1`. Nếu triển khai RAC, cùng CDB/database đó còn có thể được mở bởi instance `corp2`. Ta có **một database, nhiều instance**.

## 4. CDB và PDB: cách Oracle tổ chức nhiều môi trường dữ liệu

Kiến trúc **multitenant** của Oracle sử dụng hai cấp:

- **CDB (Container Database):** một Oracle database có cấu trúc chứa các container, bao gồm root và các PDB. CDB có cấu trúc database chung và được vận hành bởi một hoặc nhiều instance.
- **PDB (Pluggable Database):** một database logic bên trong CDB, có các schema, đối tượng ứng dụng, dữ liệu và phần metadata riêng. Ứng dụng thường kết nối đến **PDB** thích hợp thông qua service.

Ví dụ về một CDB:

~~~text
Oracle CDB: CORPDB
│
├── CDB$ROOT                  Container gốc, metadata và quản trị chung
├── PDB$SEED                  Mẫu chỉ đọc để tạo PDB mới
│
├── SALES_PDB                 PDB dành cho hệ thống bán hàng
│   ├── schema SALES_APP
│   ├── schema REPORT_APP
│   └── bảng, view, package, dữ liệu...
│
└── HR_PDB                    PDB dành cho nhân sự
    ├── schema HR_APP
    └── bảng, view, package, dữ liệu...

Instance corp1
    └── SGA và background processes vận hành CDB trên
~~~

### Các container có vai trò gì?

| Container | Vai trò | Thực hành thường gặp |
|---|---|---|
| `CDB$ROOT` | Root quản lý thông tin, thành phần và người dùng chung của CDB | DBA cấu hình, quản trị CDB; tránh đặt bảng ứng dụng thông thường tại root |
| `PDB$SEED` | Mẫu hệ thống để tạo PDB mới | Không dùng như PDB ứng dụng và không chỉnh sửa tùy tiện |
| User PDB, ví dụ `SALES_PDB` | Chứa dữ liệu và các schema của ứng dụng | Tạo user local, bảng, view; kết nối ứng dụng và thực thi nghiệp vụ |

Một PDB có thể có **nhiều schema**. Các PDB khác nhau có thể cùng xuất hiện schema tên `APP_USER`, nhưng đó là các tài khoản/schema trong **những container khác nhau**, với đối tượng và quyền riêng. PDB có thể được mở/đóng, sao chép, hoặc di chuyển theo các khả năng quản trị của Oracle, trong khi các PDB trong cùng CDB chia sẻ cơ sở hạ tầng instance/database chung.

**PDB không tương đương một server hay một instance riêng.** Tách biệt theo PDB là tách biệt ở mức tổ chức dữ liệu và quản trị logic; tài nguyên vật lý vẫn có thể được chia sẻ, và mức cách ly tài nguyên phụ thuộc vào cấu hình hệ thống.

### Có phải Oracle database nào cũng có PDB?

Không nhất thiết. Một số hệ thống Oracle kế thừa vận hành theo kiến trúc **non-CDB**, tức không có PDB. Các khái niệm database, instance, service và schema vẫn tồn tại. Với môi trường multitenant, cần thêm hai cấp CDB/PDB để biết chính xác ứng dụng đang làm việc trong container nào.

## 5. Schema: không gian tên các đối tượng do user sở hữu

Trong Oracle, **schema** là tập hợp các đối tượng database thuộc về một **database user**: bảng, view, index, sequence, procedure, function, package, trigger và các đối tượng khác. User và schema có **cùng tên** trong container tương ứng; người dùng có thể đăng nhập là user, còn các đối tượng được tham chiếu bằng tên schema.

Ví dụ, trong `SALES_PDB`:

~~~sql
-- Bảng ORDERS thuộc schema SALES_APP.
SELECT order_id, status
FROM sales_app.orders;
~~~

Ở đây:

- `SALES_PDB` là **PDB** mà phiên SQL đang kết nối tới.
- `SALES_APP` là **schema** sở hữu bảng.
- `ORDERS` là **đối tượng** thuộc schema đó.
- User đang thực thi `SELECT` có thể là `SALES_APP` hoặc user khác được cấp quyền phù hợp.

Oracle không dùng schema như một cơ sở dữ liệu con độc lập theo nghĩa PDB. Một schema **không** có instance riêng, listener riêng hay vòng đời mở/đóng riêng. Một PDB có thể chứa nhiều schema; schema không thay thế ranh giới PDB.

### User đăng nhập, schema sở hữu và quyền truy cập

Nếu đăng nhập dưới user `REPORT_USER`, truy vấn không nhất thiết chỉ đọc đối tượng của `REPORT_USER`. Khi được cấp quyền, user này có thể truy vấn `SALES_APP.ORDERS`. Việc truy cập phụ thuộc vào **privilege/role** thích hợp, không phụ thuộc vào việc hai schema “cùng database” hay “cùng PDB” là đủ.

Câu lệnh:

~~~sql
ALTER SESSION SET CURRENT_SCHEMA = SALES_APP;

-- Có thể viết tên bảng không kèm tiền tố schema,
-- nếu user đăng nhập thật sự có quyền SELECT trên bảng.
SELECT order_id, status
FROM orders;
~~~

`CURRENT_SCHEMA` chỉ đổi schema mặc định dùng để **phân giải tên đối tượng**. Nó **không đổi** `SESSION_USER` (danh tính đăng nhập) và **không tự cấp thêm quyền**.

## 6. Service: tên logic mà ứng dụng dùng để kết nối

**Database service** là tên logic đại diện cho dịch vụ truy cập dữ liệu hoặc một workload. Ứng dụng thường gửi thông tin **host + port + service name** để Oracle đưa kết nối đến đúng nơi.

Trong môi trường multitenant, một service có thể được **gắn với một PDB cụ thể**. PDB có thể có nhiều service phục vụ các ứng dụng hoặc workload khác nhau. Trong RAC, một service có thể được cung cấp bởi một hoặc nhiều instance để hỗ trợ định tuyến, cân bằng tải và tính sẵn sàng. Vì thế **service không có quan hệ một-một bắt buộc với instance**.

Ví dụ chuỗi kết nối JDBC Thin:

~~~text
jdbc:oracle:thin:@//db.example.internal:1521/sales_rw.example.com
~~~

Các phần trong chuỗi kết nối:

| Thành phần | Ý nghĩa |
|---|---|
| `db.example.internal` | Host hoặc địa chỉ nơi client liên hệ |
| `1521` | Cổng listener (cổng ví dụ thường dùng, có thể khác) |
| `sales_rw.example.com` | **Service name** được yêu cầu |
| `SALES_PDB` | PDB mà service này được cấu hình phục vụ, **không nhất thiết xuất hiện trong chuỗi** |
| `SALES_APP` | User/schema dùng sau đó để xác thực và truy cập đối tượng |

Luồng kết nối đơn giản:

~~~text
Ứng dụng
   |
   | host:port / service_name
   v
Oracle Net Listener
   |
   | tìm service và chuyển yêu cầu kết nối
   v
Instance / server process
   |
   | session được gắn với container của service
   v
PDB: SALES_PDB
   |
   | đăng nhập USER, kiểm tra quyền, chạy SQL
   v
Schema SALES_APP, REPORT_APP, ...
~~~

**Listener không phải service**: listener là thành phần mạng nhận yêu cầu kết nối; service là tên logic mà listener/Oracle dùng để nhận diện đích và workload. **Service không phải user/schema**: chọn đúng service mới giúp đến đúng PDB, còn user/password và quyền mới xác định truy cập được đối tượng nào.

### Service name và SID

Một nhầm lẫn phổ biến là điền tên SID vào ô `SERVICE_NAME`, hoặc ngược lại:

- **SID:** nhận diện một **instance**, ví dụ `corp1`.
- **SERVICE_NAME:** nhận diện **dịch vụ logic**, ví dụ `sales_rw.example.com`.

Đối với ứng dụng hiện đại, đặc biệt khi dùng PDB hoặc RAC, **kết nối theo service name** thường là lựa chọn phù hợp. Định dạng `host:port:SID` là kiểu kết nối SID cũ và không thay thế ngữ nghĩa service.

## 7. Ghép sáu thuật ngữ vào một tình huống cụ thể

Giả sử một tổ chức chạy Oracle như sau:

~~~text
                                      ┌───────────────────────┐
                                      │ Client: ứng dụng Sales │
                                      └───────────┬───────────┘
                                                  │
                             //dbhost:1521/sales_rw.example.com
                                                  │
                                                  ▼
                                          Listener / service
                                                  │
                                                  ▼
                      CDB / DATABASE: CORPDB
              ┌──────────────────────────────────────────────┐
              │ Instance corp1: SGA + background processes   │
              │                                              │
              │ CDB$ROOT          PDB$SEED                   │
              │                                              │
              │ ┌───────────────┐      ┌───────────────────┐ │
              │ │ SALES_PDB     │      │ HR_PDB            │ │
              │ │ Schema        │      │ Schema            │ │
              │ │ SALES_APP     │      │ HR_APP            │ │
              │ │ ORDERS        │      │ EMPLOYEES         │ │
              │ └───────────────┘      └───────────────────┘ │
              └──────────────────────────────────────────────┘
                      Database files trên storage
~~~

Đây là các tên và chức năng tương ứng:

| Tình huống | Đáp án |
|---|---|
| Database vật lý nào chứa dữ liệu? | `CORPDB` |
| Instance nào đang xử lý? | `corp1` (có thể có thêm instance khác nếu RAC) |
| Ứng dụng Sales yêu cầu service nào? | `sales_rw.example.com` |
| Service Sales dẫn đến PDB nào? | `SALES_PDB` theo cấu hình ví dụ |
| Bảng nghiệp vụ thuộc schema nào? | `SALES_APP` |
| PDB Sales và HR nằm trong cấu trúc nào? | Cùng **CDB** `CORPDB` |

Nếu ứng dụng HR kết nối bằng một service gắn với `HR_PDB`, nó sẽ ở **container khác**, dù có thể dùng chung host, listener, instance và database vật lý với Sales.

> **Phân biệt tên với quan hệ:** service có thể mang cùng tên với PDB mặc định, nhưng điều đó không làm chúng thành cùng một đối tượng. Để biết service dẫn đến PDB nào, phải xem cấu hình hoặc kiểm tra container thực tế của phiên đăng nhập.

## 8. Tự nhận diện trong phiên Oracle bằng SQL

Đoạn SQL dưới đây hữu ích nhất khi bạn **đã đăng nhập** và muốn biết đang ở database/PDB/service/schema nào. Các hàm `SYS_CONTEXT` không yêu cầu tra các view quản trị.

~~~sql
SELECT
    SYS_CONTEXT('USERENV', 'DB_NAME')        AS database_name,
    SYS_CONTEXT('USERENV', 'INSTANCE_NAME')  AS instance_name,
    SYS_CONTEXT('USERENV', 'CON_NAME')       AS container_name,
    SYS_CONTEXT('USERENV', 'SERVICE_NAME')   AS service_name,
    SYS_CONTEXT('USERENV', 'SESSION_USER')   AS session_user,
    SYS_CONTEXT('USERENV', 'CURRENT_SCHEMA') AS current_schema
FROM dual;
~~~

Giả sử trả về:

~~~text
DATABASE_NAME  INSTANCE_NAME  CONTAINER_NAME  SERVICE_NAME          SESSION_USER  CURRENT_SCHEMA
-------------  -------------  --------------  --------------------  ------------  --------------
CORPDB         corp1          SALES_PDB       sales_rw.example.com  REPORT_USER   REPORT_USER
~~~

Ta biết phiên này đang ở **PDB `SALES_PDB`** trong database **`CORPDB`**, sử dụng service **`sales_rw.example.com`**, chạy qua instance **`corp1`** và đăng nhập dưới user **`REPORT_USER`**. Việc xem `SALES_APP.ORDERS` có được phép hay không còn tùy quyền của `REPORT_USER`.

### Kiểm tra cấu trúc CDB/PDB (cần quyền phù hợp)

Các truy vấn dưới đây chủ yếu dùng cho người quản trị hoặc tài khoản đã được cấp quyền xem dynamic performance views. Tùy quyền và container hiện tại, kết quả có thể bị giới hạn.

~~~sql
-- Database đang mở có phải là CDB không?
SELECT name, cdb, open_mode
FROM v$database;

-- Instance hiện tại
SELECT instance_name, host_name, status
FROM v$instance;

-- Các container trong CDB, bao gồm root, seed và PDB
SELECT con_id, name, open_mode
FROM v$containers
ORDER BY con_id;

-- Các service đang được Oracle ghi nhận và PDB liên quan
SELECT name, network_name, pdb
FROM v$services
ORDER BY name;
~~~

Trong SQL*Plus hoặc SQLcl, lệnh `SHOW CON_NAME` là một cách ngắn để xem container hiện tại; đây là lệnh của **client**, không phải câu lệnh SQL chuẩn.

### Kiểm tra đối tượng thuộc schema nào

~~~sql
-- Các đối tượng mà phiên hiện tại được phép nhìn thấy
-- với owner là SALES_APP
SELECT owner, object_name, object_type
FROM all_objects
WHERE owner = 'SALES_APP'
  AND object_name = 'ORDERS';
~~~

`ALL_OBJECTS` cho biết các đối tượng mà user hiện tại có thể nhìn thấy trong ngữ cảnh container kết nối. Không tìm thấy dòng nào **chưa đủ** để kết luận bảng không tồn tại trong toàn bộ CDB: bạn có thể đang ở PDB khác, sai tên, hoặc thiếu quyền thấy đối tượng.

## 9. Nhận diện sự cố theo đúng lớp khái niệm

Khi ứng dụng gặp lỗi, hãy xác định **lớp nào** đang có vấn đề trước khi thay đổi cấu hình:

| Hiện tượng | Nên kiểm tra trước | Vì sao |
|---|---|---|
| Client báo không nhận diện được service yêu cầu, ví dụ `ORA-12514` | Service name, listener, trạng thái mở của PDB, đăng ký service | Listener có thể chưa biết service cần tìm hoặc PDB/service chưa sẵn sàng |
| Kết nối đến được Oracle nhưng ứng dụng thấy dữ liệu “sai môi trường” | `CON_NAME`, `SERVICE_NAME`, chuỗi kết nối | Có thể service dẫn đến PDB khác |
| User đăng nhập được nhưng gặp `ORA-00942` khi truy vấn bảng | Schema owner, tên đối tượng, quyền truy cập, PDB hiện tại | Bảng có thể nằm ở schema/PDB khác hoặc không có quyền |
| Tạo user ứng dụng trong CDB root bị lỗi quy tắc tên common user, ví dụ `ORA-65096` | Container hiện tại và mục đích tạo local/common user | Tạo **local user** ứng dụng thường thực hiện trong PDB |
| “Restart instance” nhưng file dữ liệu vẫn còn | Trạng thái instance và database | Instance là quá trình chạy; database nằm trên storage |
| Ứng dụng dùng SID thay cho service name và không vào đúng PDB | Kiểu chuỗi kết nối và đích cấu hình | SID định danh instance; service chọn workload/PDB |

Ví dụ điều tra vấn đề “đăng nhập được nhưng không thấy bảng `ORDERS`”: trước hết chạy truy vấn `SYS_CONTEXT` ở trên để xác nhận **PDB**, tiếp đến kiểm tra **schema** sở hữu bảng, sau cùng kiểm tra **quyền** của user hiện tại. Việc kết nối đúng host hoặc đúng instance vẫn chưa đảm bảo đến đúng PDB/schema.

## 10. Những cách hiểu sai cần tránh

1. **“Mỗi PDB có một instance riêng.”** Sai. Các PDB trong CDB thường dùng chung instance; trong RAC, CDB có thể được mở bởi nhiều instance.
2. **“Schema chính là database.”** Sai trong ngữ cảnh Oracle. Schema là tập hợp đối tượng thuộc user trong một container; PDB là đơn vị dữ liệu logic lớn hơn, chứa nhiều schema.
3. **“Service name luôn trùng tên PDB.”** Không bắt buộc. Một PDB có thể có nhiều service; service có thể mang tên do quản trị viên chọn.
4. **“Đã kết nối vào CORPDB thì chắc chắn đang ở SALES_PDB.”** Sai. Tên database thường là tên CDB; cần kiểm tra `CON_NAME`.
5. **“Đổi CURRENT_SCHEMA là đăng nhập bằng user khác.”** Sai. Nó đổi cách phân giải tên đối tượng, không đổi danh tính và quyền.
6. **“Listener, instance, service đều là một.”** Sai. Listener nhận kết nối mạng; service xác định đích logic; instance cung cấp bộ nhớ và tiến trình xử lý.
7. **“CDB và PDB là hai database vật lý hoàn toàn độc lập.”** Sai. PDB có dữ liệu/metadata riêng nhưng nằm trong cấu trúc CDB, có thành phần hạ tầng chung.

## 11. Bài tập tự kiểm tra

**Tình huống A.** Hai ứng dụng cùng truy cập `db.example.internal:1521`. Ứng dụng A dùng service `sales_app` và được đưa đến `SALES_PDB`; ứng dụng B dùng `hr_app` và được đưa đến `HR_PDB`. Chúng có nhất thiết ở hai database vật lý hay hai instance khác nhau không?

**Đáp án:** Không. Chúng có thể cùng CDB và cùng instance, nhưng ở hai PDB riêng nhờ service phù hợp.

**Tình huống B.** Trong `SALES_PDB`, user `REPORT_USER` truy vấn `SALES_APP.ORDERS` thành công. Bảng thuộc schema nào? Ai là user của phiên?

**Đáp án:** Bảng thuộc schema `SALES_APP`; user đăng nhập là `REPORT_USER`. Thành công vì phiên có quyền truy cập phù hợp.

**Tình huống C.** DBA dừng instance `corp1`, sau đó khởi động lại và mở database `CORPDB`. Những datafile của `SALES_PDB` có tự nhiên biến mất khi instance dừng không?

**Đáp án:** Không. Datafile là phần lưu trữ bền vững; dừng instance chỉ dừng bộ nhớ/tiến trình và khả năng phục vụ tương ứng. Việc PDB có sẵn sàng truy cập sau khởi động còn phụ thuộc trạng thái mở và service.

**Tình huống D.** Một phiên chạy `ALTER SESSION SET CURRENT_SCHEMA = SALES_APP`. Có thể kết luận rằng phiên đã chuyển PDB hoặc được nâng quyền thành `SALES_APP` không?

**Đáp án:** Không. PDB và user đăng nhập giữ nguyên; chỉ schema mặc định để giải tên đối tượng thay đổi.

## Ghi nhớ qua một câu chuyện kết nối

Ứng dụng gửi yêu cầu đến **listener** theo **service name**. Service được cấu hình phục vụ một **PDB** (hoặc database trong hệ non-CDB); PDB là một phần của **CDB/database**. Một **instance** với bộ nhớ và các tiến trình thực thi công việc trên database đó. Sau khi xác thực bằng **user**, các truy vấn thao tác với đối tượng thuộc một hoặc nhiều **schema** mà user được phép sử dụng.

Hãy luôn trả lời riêng sáu câu: **database nào, instance nào, service nào, PDB nào, user/schema nào, và quyền nào**. Đây là bản đồ nền tảng để đọc kiến trúc Oracle, cấu hình kết nối và phân tích lỗi chính xác.
