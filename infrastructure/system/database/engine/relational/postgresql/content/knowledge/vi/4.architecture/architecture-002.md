# Tiến trình điều phối, tiến trình phục vụ kết nối và tiến trình nền trong PostgreSQL

Khi ứng dụng mở một kết nối đến PostgreSQL và chạy `SELECT`, ai nhận kết nối đó? Ai phân tích SQL, đọc trang dữ liệu, giữ khóa và trả kết quả? Nếu không có câu truy vấn nào từ người dùng, tại sao PostgreSQL vẫn có các tiến trình đang hoạt động? Hiểu ba nhóm **tiến trình điều phối**, **tiến trình phục vụ kết nối** và **tiến trình nền** là nền tảng để giải thích cấu trúc PostgreSQL, giới hạn kết nối, công việc ghi đĩa, bảo trì dữ liệu và xử lý sự cố.

Trong mô hình truyền thống của PostgreSQL, server hoạt động theo **kiến trúc nhiều tiến trình** (*multi-process architecture*). Một tiến trình chính chấp nhận kết nối và quản lý vòng đời các tiến trình con. Mỗi kết nối client thông thường được phục vụ bởi một **backend process** riêng. Bên cạnh đó là các tiến trình nền chuyên trách checkpoint, ghi WAL, vacuum, sao chép và những nhiệm vụ khác. Các tiến trình này cùng tiếp cận những vùng **bộ nhớ chia sẻ** và phối hợp thông qua những cơ chế đồng bộ nội bộ.

Bài học tập trung vào PostgreSQL hiện đại, đặc biệt các nhánh phiên bản 15–17 và những khái niệm kiến trúc vẫn được sử dụng rộng rãi. Danh sách tiến trình, tên hiển thị và một số cơ chế thống kê có thể thay đổi theo phiên bản hoặc cấu hình; hãy dùng những truy vấn quan sát bên dưới để xác định tình trạng thực tế trên server đang học.

## 1. Bức tranh tổng thể: một PostgreSQL server có những thành phần nào?

Một instance PostgreSQL có thể được mô tả bằng sơ đồ sau:

~~~mermaid
flowchart TD
    C1["Ứng dụng Java / JDBC"] -->|TCP hoặc Unix socket| PM["Tiến trình chính postgres<br/>postmaster / supervisor"]
    C2["psql"] -->|TCP hoặc Unix socket| PM

    PM --> B1["Client backend A<br/>phục vụ JDBC"]
    PM --> B2["Client backend B<br/>phục vụ psql"]
    PM --> BG["Các tiến trình nền"]

    B1 <--> SH["Shared memory<br/>shared_buffers, lock tables, WAL buffers..."]
    B2 <--> SH
    BG <--> SH

    BG --> CK["Checkpointer"]
    BG --> BW["Background writer"]
    BG --> WW["WAL writer"]
    BG --> AV["Autovacuum launcher / workers"]
    BG --> RP["Replication / archive / workers khác"]

    SH --> D["Data files và WAL files<br/>trong hệ lưu trữ"]
~~~

Sơ đồ nhằm trình bày **vai trò và đường phối hợp**, không phải trình tự gọi hàm thật của từng câu SQL. Chẳng hạn, một backend có thể trực tiếp thực hiện công việc đọc/ghi cần thiết, không phải mọi thao tác vào file đều phải đi qua checkpointer hoặc background writer.

Ba nhóm cần phân biệt ngay:

| Nhóm | Vai trò chính | Ví dụ quan sát |
| --- | --- | --- |
| **Tiến trình điều phối** | Khởi tạo dịch vụ, tiếp nhận kết nối, tạo và giám sát tiến trình con, xử lý các sự kiện vòng đời server | Tiến trình chính `postgres`, thường được gọi lịch sử là *postmaster* |
| **Tiến trình phục vụ kết nối** | Xử lý yêu cầu của một phiên client: xác thực ngữ cảnh phiên, parse/plan/execute SQL, quản lý transaction và gửi kết quả | `client backend` của `psql` hoặc ứng dụng |
| **Tiến trình nền** | Thực hiện công việc nội bộ, bảo trì, ghi đĩa, recovery, replication hoặc những tác vụ không gắn trực tiếp một phiên client | `checkpointer`, `background writer`, `walwriter`, `autovacuum worker`, `walsender`, `walreceiver` |

Điểm quan trọng: **backend cũng là một tiến trình của PostgreSQL**, không phải một chương trình riêng do JDBC tạo ra trên máy ứng dụng. Backend chạy ở phía server và phục vụ một connection cụ thể. Còn tiến trình nền có thể hoạt động dù không có ứng dụng nào đang gửi truy vấn.

## 2. PostgreSQL dùng tiến trình, không phải một thread cho mỗi kết nối

Trên nhiều hệ điều hành, tiến trình của PostgreSQL có thể xuất hiện trong danh sách của hệ điều hành với tên `postgres`. Người quản trị thấy nhiều dòng `postgres` không nhất thiết là nhiều máy chủ độc lập. Chúng thường là các tiến trình con của **cùng một instance** đang phục vụ những chức năng khác nhau.

Ví dụ một cây tiến trình khái niệm trên hệ thống kiểu Unix:

~~~text
postgres (main server / postmaster)
├── postgres: checkpointer
├── postgres: background writer
├── postgres: walwriter
├── postgres: autovacuum launcher
├── postgres: logical replication launcher
├── postgres: appdb app_user 10.0.0.21 idle
├── postgres: appdb app_user 10.0.0.22 SELECT
└── postgres: appdb reporting_user 10.0.0.30 idle
~~~

Đây là danh sách **minh họa**, không phải kết quả bắt buộc từ một phiên bản PostgreSQL. Một số tiến trình có thể không tồn tại khi tính năng tương ứng chưa bật; một số khác chỉ xuất hiện khi có việc cần làm. Tên tiến trình hiển thị khác nhau theo hệ điều hành và công cụ quan sát.

Trên hệ Unix-like, PostgreSQL thường dùng cơ chế tạo tiến trình con phù hợp với nền tảng, ví dụ `fork`. Trên Windows, cách tạo tiến trình con khác về kỹ thuật hệ điều hành, nhưng về mặt kiến trúc người dùng vẫn quan sát nhiều **process** có vai trò khác nhau. Vì thế không nên mô tả kiến trúc PostgreSQL chỉ bằng câu “server tạo các thread như một số hệ quản trị khác”.

### 2.1. Một connection thường đi cùng một backend

Khi ứng dụng mở một connection thông thường:

1. Client kết nối đến địa chỉ/cổng PostgreSQL.
2. Tiến trình chính tiếp nhận yêu cầu và sắp xếp tạo tiến trình con phục vụ phiên.
3. Backend thực hiện các bước của giao thức và xác thực cần thiết, thiết lập trạng thái phiên.
4. Backend nhận các câu SQL và thực hiện chúng trong cùng phiên đó.
5. Backend trả kết quả về client.
6. Khi connection kết thúc, backend phiên tương ứng được giải phóng.

Một câu `SELECT` rồi một câu `UPDATE` gửi **trên cùng connection** thường dùng **cùng backend**; PostgreSQL không tạo một tiến trình mới cho mỗi câu SQL. Ngược lại, hai connection đồng thời từ cùng ứng dụng thường có hai client backend khác nhau.

Sơ đồ:

~~~text
Ứng dụng Java                       PostgreSQL server
---------------------------------------------------------------
Connection A ---------------------> Backend PID 12001
    SELECT ...                           |
    BEGIN                                | cùng phiên
    UPDATE ...                           |
    COMMIT                               |

Connection B ---------------------> Backend PID 12002
    SELECT ...                       phiên khác
~~~

Các PID chỉ là số ví dụ. Trong môi trường có **connection proxy/pooler** ở giữa, không nhất thiết mỗi kết nối ứng dụng đều ánh xạ một-một với kết nối server tại mọi thời điểm; phần kết nối được giải thích kỹ hơn ở mục 11.

### 2.2. Backend không sở hữu bản sao toàn bộ database

Dù backend là các process tách biệt, chúng không tải một bản sao riêng của tất cả các bảng vào bộ nhớ. Backend sử dụng chung một số tài nguyên của instance, ví dụ:

- **Shared buffers:** bộ đệm các trang bảng/chỉ mục đang được dùng.
- **WAL buffers:** vùng nhớ hỗ trợ việc tạo các bản ghi write-ahead log.
- **Thông tin lock và transaction:** cho phép các process điều phối truy cập đồng thời.
- **Một số cấu trúc điều phối, thống kê và đồng bộ nội bộ**.

Mỗi backend cũng có **bộ nhớ riêng** cho trạng thái phiên, cây kế hoạch, bộ nhớ thực thi các toán tử và những cấu trúc cục bộ khác. Hai kiểu bộ nhớ này khác nhau, nên giới hạn số connection liên quan trực tiếp đến khả năng kiểm soát RAM.

## 3. Tiến trình chính: postmaster điều phối vòng đời server

Trong tài liệu và lịch sử PostgreSQL, tiến trình chính thường được gọi là **postmaster**. Trên nhiều hệ thống, chương trình thực thi có tên `postgres` và các chức năng máy chủ được khởi động qua lệnh `pg_ctl`, service manager hoặc hạ tầng managed database.

Vai trò khái quát của tiến trình chính:

1. Khởi tạo và quản lý vòng đời instance.
2. Thiết lập các cơ chế chia sẻ tài nguyên và các cấu trúc cần cho server.
3. Lắng nghe kết nối từ client qua TCP hoặc Unix-domain socket tùy cấu hình.
4. Tạo/khởi động tiến trình phục vụ kết nối và các tiến trình nền cần thiết.
5. Theo dõi tiến trình con, tiếp nhận tín hiệu dừng/reload và điều phối shutdown.
6. Tham gia xử lý sự kiện bất thường của server, ví dụ một tiến trình backend bị crash theo cách gây ảnh hưởng đến tính nhất quán của bộ nhớ chia sẻ.

### 3.1. Tiến trình chính không tự thực thi mọi SELECT

Một nhầm lẫn thường gặp là “postmaster nhận câu SQL rồi tự chạy các lệnh”. Trong đường xử lý thông thường, backend của phiên sẽ phân tích, lập kế hoạch, thực thi và trả kết quả. Tiến trình chính chủ yếu làm nhiệm vụ **supervisor/điều phối**, không xử lý thay mọi truy vấn ứng dụng.

Điều này giải thích tại sao khi có 100 kết nối tới một PostgreSQL instance, người quản trị có thể thấy nhiều backend nhưng vẫn chỉ có **một tiến trình chính** của instance đó.

### 3.2. Khi một backend có sự cố

Không phải mọi lỗi SQL đều khiến backend chết. Ví dụ một lệnh vi phạm `UNIQUE` thường chỉ trả lỗi cho phiên; PostgreSQL có thể đặt transaction đang mở vào trạng thái aborted và yêu cầu `ROLLBACK`, nhưng connection và backend vẫn tồn tại.

Ngược lại, nếu một backend bị crash nghiêm trọng và PostgreSQL nghi ngờ trạng thái bộ nhớ chia sẻ không còn an toàn, tiến trình điều phối có thể yêu cầu các backend khác thoát, khởi tạo lại cơ chế nội bộ và thực hiện recovery trước khi cho kết nối hoạt động bình thường. Đây là một tình huống nghiêm trọng hơn rất nhiều so với lỗi cú pháp SQL thông thường.

Không nên coi việc “một câu lệnh báo lỗi” và “một process PostgreSQL chết” là cùng loại sự cố.

### 3.3. Khởi động, reload và restart khác nhau

| Thao tác | Ý nghĩa | Lưu ý |
| --- | --- | --- |
| **Reload configuration** | Yêu cầu PostgreSQL nạp lại các tham số hỗ trợ reload và thông tin cấu hình tương ứng | Không phải mọi tham số đều có hiệu lực sau reload |
| **Restart** | Dừng và chạy lại server theo quy trình quản trị | Gây gián đoạn các phiên và giao dịch đang hoạt động |
| **Shutdown có kiểm soát** | Kết thúc dịch vụ theo mode dừng thích hợp | Tác động với connection đang mở phụ thuộc cách dừng |
| **Crash recovery** | Đọc trạng thái lưu trữ/WAL để phục hồi sau sự cố | Không tương đương chỉ reload file cấu hình |

Một câu SQL quản trị để yêu cầu reload cấu hình, khi tài khoản có quyền phù hợp:

~~~sql
SELECT pg_reload_conf();
~~~

Hàm trả về việc gửi tín hiệu reload thành công hay không; **không chứng minh tất cả cấu hình đều đã hợp lệ hoặc được áp dụng**. Một số thông số đòi restart. Có thể xem metadata qua `pg_settings` và log server để kiểm tra chính xác.

## 4. Backend process: nơi phiên SQL được phục vụ

Một client backend xử lý những phần chính của vòng đời truy vấn:

~~~mermaid
flowchart TD
    A["Client gửi SQL"] --> B["Backend nhận thông điệp"]
    B --> C["Parse / analyze / rewrite"]
    C --> D["Planner chọn kế hoạch"]
    D --> E["Executor thực thi"]
    E --> F["Truy cập shared buffers, index, heap và locks"]
    F --> G["Đọc/ghi dữ liệu; WAL nếu cần"]
    G --> H["Trả rows, command tag hoặc lỗi"]
    H --> I["Backend chờ lệnh tiếp theo của cùng phiên"]
~~~

Các thành phần trên là mô hình đơn giản; một prepared statement có thể làm một số bước vào các thời điểm khác nhau, và lệnh quản trị hay utility command không nhất thiết đi đúng chuỗi giống `SELECT`.

### 4.1. Backend quản lý trạng thái phiên

Một connection PostgreSQL có thể giữ:

- Transaction hiện tại và mức cô lập.
- Cấu hình trong phiên như `search_path` hoặc `statement_timeout`.
- Prepared statements và một số đối tượng gắn với session.
- Temporary tables, nếu phiên đã tạo.
- Trạng thái cursor, transaction-level hoặc session-level advisory locks khi có.

Ví dụ trên một connection:

~~~sql
SET application_name = 'lesson_55_psql';
SET search_path = public;

SELECT
    pg_backend_pid() AS my_backend_pid,
    current_database() AS my_database,
    current_user AS my_role,
    current_setting('application_name') AS app_name;
~~~

`pg_backend_pid()` trả PID của backend đang phục vụ chính connection hiện tại. Khi chạy hai phiên `psql` riêng, thường sẽ nhận hai PID khác nhau.

### 4.2. Một transaction có thể chứa nhiều statement

~~~sql
BEGIN;

SELECT txid_current() AS current_xid;

-- Các câu lệnh đọc/ghi tiếp theo ở cùng connection
-- tham gia transaction hiện tại cho đến COMMIT hoặc ROLLBACK.

ROLLBACK;
~~~

`txid_current()` có thể gán/đòi transaction ID và không cần thiết cho mọi thao tác đọc; chỉ sử dụng trong lab khi muốn quan sát ngữ nghĩa transaction. Một số phiên bản PostgreSQL mới còn có các hàm transaction ID theo kiểu dữ liệu mới; không nên dựa vào giá trị ID để xác định backend hoặc session.

Phân biệt rõ:

- **Connection/session:** kéo dài từ khi client đăng nhập đến khi ngắt kết nối, có thể chứa nhiều transaction.
- **Transaction:** bắt đầu bởi `BEGIN` hoặc ngầm định theo autocommit, kết thúc bằng `COMMIT`/`ROLLBACK`.
- **Statement:** một câu SQL cụ thể trong transaction.
- **Backend process:** process phục vụ connection, có thể xử lý nhiều statement và transaction suốt vòng đời phiên.

Một request HTTP có thể dùng một connection lấy từ pool để chạy nhiều SQL; sau request, connection có thể được trả về pool **chứ chưa đóng**, vì vậy backend server vẫn có thể tồn tại và ở trạng thái `idle`.

### 4.3. Vì sao một backend có thể chờ mà vẫn chiếm tài nguyên?

Trong `pg_stat_activity`, backend có thể có các trạng thái:

| `state` | Diễn giải |
| --- | --- |
| `active` | Backend đang thực thi truy vấn |
| `idle` | Không thực thi truy vấn hiện tại, đang đợi lệnh tiếp theo |
| `idle in transaction` | Transaction vẫn mở nhưng không có câu SQL nào đang chạy |
| `idle in transaction (aborted)` | Transaction mở đã gặp lỗi, cần kết thúc bằng rollback |
| `fastpath function call` hoặc trạng thái khác | Phụ thuộc chức năng/phiên bản đang dùng |

**`idle` không đồng nghĩa connection không tốn tài nguyên**: backend vẫn có bộ nhớ và slot kết nối. **`idle in transaction` đáng chú ý hơn** vì phiên có thể giữ lock, snapshot hoặc ngăn công việc dọn dẹp những phiên bản hàng cũ cần thiết cho MVCC. Vì vậy, ứng dụng không nên mở transaction rồi gọi HTTP tới dịch vụ khác hoặc chờ thao tác người dùng mà không có giới hạn thời gian.

## 5. Bộ nhớ chia sẻ và cơ chế phối hợp giữa tiến trình

Kiến trúc nhiều tiến trình đòi hỏi một cách trao đổi dữ liệu. PostgreSQL sử dụng **shared memory** và những primitive đồng bộ phù hợp để backend và background process làm việc trên cùng cấu trúc.

~~~text
                  Shared memory của một instance
  +----------------------------------------------------+
  | shared_buffers: cache page của heap và index      |
  | WAL buffers: bản ghi WAL trước khi được ghi       |
  | lock structures: thông tin đồng bộ truy cập       |
  | thông tin transaction / trạng thái nội bộ khác    |
  +----------------------------------------------------+
       ^                 ^                   ^
       |                 |                   |
   Backend A         Backend B         Background process
  (private RAM)     (private RAM)        (private RAM)
~~~

### 5.1. Shared buffers

`shared_buffers` là cấu hình xác định quy mô bộ nhớ đệm trang chung của PostgreSQL. Một backend có thể cần đọc trang bảng từ storage; nếu trang đã có trong bộ đệm, nó có thể dùng bản trang đó. Nếu trang bị sửa, bản trong cache trở thành **dirty buffer** cho đến khi được ghi về file dữ liệu.

~~~sql
SHOW shared_buffers;
~~~

Không nhầm `shared_buffers` với tổng RAM mà PostgreSQL sử dụng. Hệ thống còn có **bộ nhớ riêng của backend**, cache của hệ điều hành, bộ nhớ cho parallel workers, maintenance và những thành phần khác.

### 5.2. Bộ nhớ riêng của backend

Một truy vấn `ORDER BY` hay `GROUP BY` có thể dùng bộ nhớ cho sort/hash. Tham số `work_mem` là ngưỡng liên quan đến **một thao tác** sort/hash, chứ không phải một hạn mức RAM cố định cho toàn server hoặc một connection.

~~~sql
SHOW work_mem;
SHOW maintenance_work_mem;
~~~

Một truy vấn phức tạp có thể có nhiều operator sử dụng bộ nhớ, và nhiều backend có thể chạy đồng thời. Nếu mỗi backend có nhiều phép sort/hash, tổng tiêu thụ RAM có thể lớn hơn đáng kể so với một giá trị `work_mem` đơn lẻ. Cấu hình `hash_mem_multiplier` còn tác động đến giới hạn của các thao tác hash trong những phiên bản hỗ trợ.

Đó là lý do không thể chọn `max_connections = 1000` và `work_mem = 100MB` rồi kết luận chỉ cần vài trăm MB RAM. Cần xét đồng thời **số process, số operator và mức tải thực tế**.

### 5.3. Lock và MVCC

Backend phối hợp qua hệ thống khóa và cơ chế **MVCC**. MVCC cho phép nhiều truy vấn đọc các phiên bản dữ liệu nhất quán mà không nhất thiết chặn mọi giao dịch ghi. Nhưng các transaction ghi vẫn có thể tranh chấp row lock hoặc những loại lock khác.

Vì vậy:

- Hai backend có thể cùng chạy `SELECT` mà không gây chặn nhau trong nhiều tình huống thông thường.
- Hai backend cùng cập nhật một dòng có thể phải chờ nhau.
- DDL có thể cần lock mạnh hơn và ảnh hưởng các phiên khác.
- Transaction mở lâu có thể kéo dài tuổi snapshot và khiến VACUUM chưa dọn được những phiên bản cũ.

Khi điều tra, phải phân biệt **backend đang chạy chậm vì CPU/I/O** với **backend đang chờ lock hoặc chờ client**. Hai trường hợp cần cách giải quyết khác nhau.

## 6. Tiến trình ghi dữ liệu nền: background writer, checkpointer và WAL writer

Ba tiến trình này dễ bị nhầm vì đều có chữ “write”, nhưng vai trò của chúng khác nhau.

| Tiến trình | Trách nhiệm điển hình | Không nên hiểu sai |
| --- | --- | --- |
| **Background writer (bgwriter)** | Chủ động ghi một số dirty buffer để tăng khả năng tái sử dụng buffer và giảm áp lực ghi phát sinh ngay lúc backend cần trang | Không phải tiến trình duy nhất ghi trang dữ liệu |
| **Checkpointer** | Điều phối checkpoint và việc ghi/đồng bộ các trang cần thiết ở mốc phục hồi | Không phải một lần ghi toàn bộ database từ đầu |
| **WAL writer (walwriter)** | Ghi dữ liệu từ WAL buffers ra tệp WAL theo cơ chế nền | Không có nghĩa mọi `COMMIT` chỉ chờ một mình WAL writer |

### 6.1. WAL và quan hệ với durability

**WAL (*Write-Ahead Log*)** giúp PostgreSQL phục hồi những thay đổi sau sự cố. Nguyên tắc write-ahead yêu cầu thông tin WAL tương ứng được ghi bền vững theo quy tắc phù hợp **trước khi** các trang dữ liệu đã thay đổi được phép ghi về storage theo cách có thể cần recovery.

Sơ đồ đơn giản:

~~~text
Client: UPDATE ...
    |
    v
Backend thay đổi trang trong shared_buffers
    |
    +--> tạo WAL records, đưa vào WAL buffers
    |
    +--> COMMIT theo chính sách durability
              |
              v
      WAL được ghi/flush theo yêu cầu

Về sau:
    bgwriter / checkpointer / backend
        ghi dirty data pages về data files
~~~

Thứ tự và cơ chế flush cụ thể phụ thuộc cấu hình như `synchronous_commit` và cách PostgreSQL phối hợp giữa backend và WAL writer. Với cài đặt mặc định phù hợp độ bền, việc một transaction đã `COMMIT` thành công **không đòi** tất cả trang dữ liệu của transaction đó phải được ghi ngay xuống file bảng; WAL cho phép phục hồi khi xảy ra crash.

Không nên suy luận “sau COMMIT, dữ liệu chỉ ở RAM cho đến checkpoint”. Với cấu hình bền vững thông thường, PostgreSQL đã thực hiện những đảm bảo cần thiết về WAL; dữ liệu bảng có thể được flush muộn hơn.

### 6.2. Background writer: giảm cú sốc khi backend cần buffer trống

Buffer pool có giới hạn; một số buffer có thể chứa trang bị sửa. Nếu một backend cần dùng lại buffer cũ mà buffer đó còn dirty, nó có thể phải làm công việc ghi/đợi phù hợp. Background writer giúp ghi trước một phần các dirty buffer để chúng dễ được tái sử dụng hơn.

Tuy nhiên, nếu số lượng ghi rất lớn, các backend vẫn có thể trực tiếp ghi dữ liệu khi cần. Bgwriter không phải “hàng đợi ghi duy nhất” mà mọi thao tác SQL phải chờ.

Truy vấn cấu hình liên quan:

~~~sql
SHOW bgwriter_delay;
SHOW bgwriter_lru_maxpages;
~~~

Các tham số quyết định một phần cách background writer làm việc; đừng chỉnh chúng chỉ dựa vào một lần thấy I/O cao. Cần nhìn tổng thể workload, checkpoint và thiết bị lưu trữ.

### 6.3. Checkpointer và checkpoint

Checkpoint giúp giới hạn lượng WAL phải replay khi phục hồi và là mốc quan trọng trong quản lý ghi bền vững. Checkpointer điều phối việc ghi và đồng bộ những trang dữ liệu cần thiết theo checkpoint.

Các tham số thường gặp:

~~~sql
SHOW checkpoint_timeout;
SHOW max_wal_size;
SHOW checkpoint_completion_target;
~~~

Giá trị `max_wal_size` là ngưỡng mục tiêu/soft limit liên quan đến chính sách checkpoint và WAL, **không phải mức trần tuyệt đối không thể vượt** trong mọi tình huống. Thời điểm checkpoint còn phụ thuộc các điều kiện vận hành khác.

Không phải cứ giảm `checkpoint_timeout` là server an toàn hơn: checkpoint quá thường xuyên có thể tăng I/O và số WAL do full-page writes; checkpoint quá thưa cũng có đánh đổi về thời gian phục hồi và dung lượng WAL. Việc tuning cần theo dữ liệu đo và mục tiêu RTO.

### 6.4. WAL writer và hành vi commit

WAL writer làm công việc nền đối với WAL buffers. Dưới workload có nhiều transaction, nó có thể giúp giảm việc từng backend phải làm các thao tác ghi nhỏ liên tục. Nhưng khi transaction cần đảm bảo commit, **backend có thể trực tiếp đảm bảo việc flush WAL cần thiết** thay vì luôn đợi một chu trình riêng của WAL writer.

Điều này giải thích một nghịch lý tưởng tượng: “Server có WAL writer, tại sao một câu `COMMIT` vẫn có thể chậm?” Vì độ trễ commit còn chịu ảnh hưởng của flush storage, đồng bộ WAL, cạnh tranh I/O, synchronous replication và cấu hình durability.

## 7. Autovacuum: tiến trình nền giữ MVCC và thống kê khỏe mạnh

PostgreSQL dùng MVCC để giữ các phiên bản hàng theo thời gian. Khi `UPDATE` tạo phiên bản mới hoặc `DELETE` đánh dấu phiên bản cũ không còn hiện hành, các phiên bản cũ không thể được loại bỏ ngay nếu những transaction khác vẫn cần nhìn thấy chúng.

**Autovacuum** tự động thực hiện công việc bảo trì tương ứng. Kiến trúc khái quát:

~~~mermaid
flowchart TD
    L["Autovacuum launcher"] --> W1["Autovacuum worker 1"]
    L --> W2["Autovacuum worker 2"]
    W1 --> T1["VACUUM / ANALYZE bảng A"]
    W2 --> T2["VACUUM / ANALYZE bảng B"]
    T1 --> S["Thu hồi không gian tái sử dụng,<br/>duy trì thông tin MVCC"]
    T2 --> S
~~~

- **Autovacuum launcher** theo dõi và sắp xếp thời điểm khởi chạy worker.
- **Autovacuum workers** thực hiện công việc cụ thể trên bảng phù hợp: vacuum và/hoặc analyze.
- **VACUUM** giúp loại bỏ các phiên bản hàng không còn cần thiết và xử lý những nhu cầu bảo trì liên quan, bao gồm chống nguy cơ transaction ID wraparound.
- **ANALYZE** cập nhật thống kê phân bố dữ liệu cho query planner.

Autovacuum không phải một câu SQL do ứng dụng gửi, nên người học có thể thấy các process này hoạt động dù không có request HTTP nào đến server.

### 7.1. Quan sát autovacuum

~~~sql
SHOW autovacuum;
SHOW autovacuum_max_workers;

SELECT
    schemaname,
    relname,
    n_live_tup,
    n_dead_tup,
    last_autovacuum,
    last_autoanalyze
FROM pg_stat_user_tables
ORDER BY n_dead_tup DESC
LIMIT 20;
~~~

`n_live_tup` và `n_dead_tup` là **ước tính thống kê**, không phải số đếm chính xác. `last_autovacuum`/`last_autoanalyze` phản ánh thông tin đã được ghi nhận trong hệ thống thống kê. Nếu một database chỉ có vài dòng, có thể không thấy worker chạy đúng thời điểm người học quan sát.

### 7.2. Tại sao không nên tắt autovacuum?

Tắt autovacuum để giảm I/O có thể khiến bảng phình to do phiên bản hàng cũ, thống kê chậm cập nhật và tăng nguy cơ liên quan transaction ID wraparound. Trong vận hành nghiêm túc, cách làm đúng là **theo dõi và cấu hình bảo trì theo workload**, không vô hiệu hóa cơ chế chỉ vì xuất hiện trong danh sách process.

`VACUUM FULL` khác `VACUUM` thông thường: nó có thể viết lại bảng để thu hồi dung lượng vật lý nhưng thường yêu cầu lock mạnh và không phải một phần “vacuum nền liên tục” đơn giản. Không dùng `VACUUM FULL` làm giải pháp mặc định cho mọi bảng lớn.

## 8. Những tiến trình nền khác: WAL archive, recovery và replication

Danh sách tiến trình PostgreSQL thay đổi theo vai trò instance. Một primary độc lập có ít thành phần replication hơn một primary có nhiều standby hoặc một instance đang subscribe logical replication.

### 8.1. WAL archiver

Khi bật WAL archiving với cấu hình phù hợp, **archiver** hỗ trợ đưa các WAL segment đã sẵn sàng ra vị trí lưu trữ dài hạn. Điều này quan trọng cho **point-in-time recovery (PITR)** khi kết hợp cùng base backup phù hợp.

~~~sql
SHOW archive_mode;
SHOW archive_command;

SELECT
    archived_count,
    failed_count,
    last_archived_wal,
    last_archived_time,
    last_failed_wal,
    last_failed_time
FROM pg_stat_archiver;
~~~

Không nên coi việc archiver xuất hiện trong danh sách process là bằng chứng **backup hoàn chỉnh**. Archiving cần hoạt động thành công, chuỗi WAL phải đủ, base backup phải phù hợp và quy trình restore cần được kiểm thử.

Lưu ý: `archive_command` có thể chứa đường dẫn và cấu hình vận hành; tránh đưa nội dung nhạy cảm từ đó vào log hoặc tài liệu công khai.

### 8.2. Startup process và phục hồi WAL

Khi PostgreSQL khởi động sau một lần dừng bất thường hoặc một instance đang ở chế độ **standby/recovery**, các công việc recovery có thể cần replay WAL để đưa dữ liệu về trạng thái nhất quán.

**Startup process** có vai trò quan trọng trong việc áp dụng WAL trong giai đoạn recovery. Trên standby, quá trình replay WAL là thành phần chính giúp bản sao theo kịp primary. Tên và trạng thái tiến trình cụ thể tùy giai đoạn khởi động/phiên bản.

~~~sql
SELECT pg_is_in_recovery() AS is_standby_or_recovering;
~~~

Nếu `pg_is_in_recovery() = TRUE`, server đang trong trạng thái recovery, thường thấy ở standby đang replay WAL. Nếu `FALSE`, server không ở recovery mode tại thời điểm truy vấn. Tuy nhiên, một phép kiểm tra này **không đủ xác định toàn bộ topology và ai đang giữ quyền ghi của ứng dụng**; còn phải xem cấu hình và cơ chế điều phối failover.

### 8.3. WAL sender và WAL receiver

Với **physical streaming replication**, primary có thể có **WAL sender processes (walsender)** gửi dữ liệu WAL tới standby. Ở phía standby có **WAL receiver (walreceiver)** nhận dòng WAL, sau đó startup/recovery áp dụng WAL theo tiến độ.

~~~mermaid
flowchart LR
    A["Primary PostgreSQL"] --> WS["WAL sender"]
    WS -->|"Streaming WAL"| WR["WAL receiver trên standby"]
    WR --> RL["WAL cục bộ"]
    RL --> ST["Startup / recovery"]
    ST --> SD["Data files của standby"]
~~~

Quan sát phía primary:

~~~sql
SELECT
    pid,
    application_name,
    client_addr,
    state,
    sync_state,
    sent_lsn,
    write_lsn,
    flush_lsn,
    replay_lsn
FROM pg_stat_replication;
~~~

Quan sát phía standby:

~~~sql
SELECT
    pid,
    status,
    receive_start_lsn,
    written_lsn,
    flushed_lsn,
    latest_end_lsn,
    latest_end_time
FROM pg_stat_wal_receiver;
~~~

Trên một server không có replication, kết quả có thể **không có dòng**; điều đó không chứng minh PostgreSQL bị hỏng. Tùy phiên bản, một số cột trạng thái của `pg_stat_wal_receiver` có thể khác nhau; khi chạy trên server cụ thể, xem `\d+ pg_stat_wal_receiver` trong `psql` để xác định tập cột thực tế trước khi dùng trong dashboard.

### 8.4. Logical replication launcher và apply workers

Logical replication sao chép thay đổi ở mức logic, khác với việc standby phát lại nguyên luồng WAL vật lý của toàn instance. Một instance dùng **subscription** có thể có **logical replication launcher** và **apply workers** để tiếp nhận, thực thi thay đổi đã được giải mã từ phía publisher.

Không phải mọi instance có logical replication launcher đều đang có subscription hoạt động, và không phải mọi backend replication là client backend thông thường. Các tiến trình logical replication cần được tính vào ngân sách background workers và số lượng kết nối phù hợp với cấu hình.

### 8.5. Các background workers do extension tạo

PostgreSQL cho phép một số extension hoặc chức năng hệ thống tạo **background workers**. Tùy extension được cài, có thể thấy tiến trình xử lý lịch trình, bảo trì hoặc các nhiệm vụ nội bộ khác.

Không nên thấy một process có tên lạ rồi tự kết luận đó là mã độc hoặc lỗi PostgreSQL; trước tiên cần xác minh extension, file cấu hình, role/ownership và tài liệu chức năng. Ngược lại, cũng không nên cho phép tùy ý extension có thể chạy code nền trên production mà không qua quy trình bảo mật.

## 9. Parallel workers: tiến trình hỗ trợ một truy vấn lớn

Không phải mọi tiến trình được tạo thêm đều là một connection từ ứng dụng hoặc một dịch vụ bảo trì. Với **parallel query**, PostgreSQL có thể khởi chạy những **parallel workers** giúp xử lý một phần kế hoạch truy vấn.

Ví dụ:

~~~text
Client Connection
      |
      v
Leader backend PID 22001
      |
      +--> Parallel worker PID 22011
      +--> Parallel worker PID 22012
      |
      +--> Gather / Gather Merge
      |
      v
Kết quả trả về cùng connection client
~~~

Trong mô hình này, client vẫn có **một connection**, nhưng server có thể dùng thêm một hoặc nhiều worker phục vụ quá trình thực thi. Vì vậy câu “mỗi connection có một backend” không có nghĩa mọi truy vấn chỉ có thể sử dụng duy nhất một process để tính toán.

Một kế hoạch parallel có thể có node `Gather` hoặc `Gather Merge` và số worker được dự kiến/khởi chạy:

~~~sql
EXPLAIN
SELECT COUNT(*)
FROM large_events;
~~~

Ví dụ giả định bảng `large_events` đã tồn tại và có lượng dữ liệu phù hợp; đây **không phải** câu có thể chạy trên một database mới trống. PostgreSQL không đảm bảo mọi truy vấn `COUNT(*)` sẽ chạy song song. Planner dựa vào chi phí, điều kiện của query, kích thước bảng, `max_parallel_workers_per_gather`, ngân sách worker và những hạn chế khác.

Một số biến thường gặp:

~~~sql
SHOW max_parallel_workers_per_gather;
SHOW max_parallel_workers;
SHOW max_worker_processes;
~~~

Các thông số này không phải “số thread cho mỗi connection”. Worker được phân bổ theo kế hoạch và khả năng thực tế; kế hoạch dự kiến có thể không nhận đủ worker nếu server đang bận hoặc đạt giới hạn tài nguyên.

### 9.1. Vì sao parallel query không luôn nhanh hơn?

Việc khởi tạo và điều phối worker có chi phí, cần trao đổi dữ liệu về leader và có thể tạo tranh chấp I/O/CPU. Với bảng nhỏ, một process quét dữ liệu có thể nhanh hơn tạo cả một nhóm worker. Khi nhiều query đồng thời cố dùng nhiều worker, tổng tải máy chủ có thể vượt năng lực CPU/storage.

Hãy nhìn `EXPLAIN (ANALYZE, BUFFERS)` trên môi trường thử nghiệm có dữ liệu đại diện nếu muốn đánh giá tác động thật; lệnh `EXPLAIN ANALYZE` **thực thi** truy vấn và có thể tiêu thụ tài nguyên đáng kể.

## 10. Quan sát tiến trình bằng pg_stat_activity

`pg_stat_activity` là một trong những system view hữu ích nhất để quan sát các tiến trình đang hoạt động ở PostgreSQL. Nó có thể chứa client backend cùng một số background/auxiliary processes, kèm các trường như `pid`, `backend_type`, `state` và `wait_event`.

### 10.1. Liệt kê các loại backend hiện có

~~~sql
SELECT
    backend_type,
    COUNT(*) AS process_count
FROM pg_stat_activity
GROUP BY backend_type
ORDER BY backend_type;
~~~

Kết quả minh họa:

~~~text
backend_type                 process_count
------------------------------------------------
autovacuum launcher          1
background writer            1
checkpointer                 1
client backend               4
logical replication launcher 1
walwriter                    1
~~~

**Không coi danh sách này là bắt buộc.** Các phiên bản và cấu hình khác nhau có thể cho kết quả khác, và một số tiến trình không xuất hiện trong view giống các process ứng dụng. Tiến trình chính `postmaster` không nhất thiết được liệt kê như một dòng `client backend`.

### 10.2. Xem phiên client, query và trạng thái chờ

~~~sql
SELECT
    pid,
    backend_type,
    datname,
    usename,
    application_name,
    client_addr,
    state,
    wait_event_type,
    wait_event,
    now() - backend_start AS backend_age,
    now() - xact_start AS transaction_age,
    LEFT(query, 100) AS query_preview
FROM pg_stat_activity
WHERE backend_type = 'client backend'
ORDER BY backend_start;
~~~

Các trường:

| Trường | Ý nghĩa |
| --- | --- |
| `pid` | PID của backend process trong hệ điều hành |
| `backend_type` | Loại tiến trình, ví dụ `client backend` |
| `datname` / `usename` | Database và role liên quan |
| `application_name` | Nhãn do client/cấu hình đặt để tiện quan sát |
| `client_addr` | Địa chỉ IP client nếu có; có thể `NULL` với Unix socket |
| `state` | Trạng thái thực thi/đợi lệnh của client backend |
| `wait_event_type` / `wait_event` | Nhóm và loại sự kiện backend đang chờ |
| `backend_start` | Thời điểm backend bắt đầu |
| `xact_start` | Thời điểm transaction hiện tại bắt đầu, có thể `NULL` |
| `query` | Câu SQL hiện tại hoặc câu gần nhất tùy trạng thái |

Khi transaction không mở, biểu thức `now() - xact_start` trả `NULL`. Một backend `idle` có thể hiển thị **câu truy vấn cuối** trong trường `query`; không được suy luận nó vẫn đang thực thi câu đó.

Quyền truy cập có thể giới hạn thông tin về phiên khác. Một số trường có thể bị che nếu role không được cấp quyền theo dõi phù hợp; quyền như `pg_read_all_stats` nên được quản trị cấp có chủ đích, không cấp rộng chỉ để làm ví dụ.

### 10.3. Truy vấn phát hiện idle in transaction

~~~sql
SELECT
    pid,
    usename,
    application_name,
    state,
    now() - xact_start AS transaction_age,
    wait_event_type,
    wait_event
FROM pg_stat_activity
WHERE state LIKE 'idle in transaction%'
ORDER BY xact_start NULLS LAST;
~~~

Nếu một phiên mở transaction hàng giờ rồi đứng yên, cần kiểm tra logic ứng dụng, timeout, locks và ảnh hưởng MVCC. **Không tự động kết thúc mọi phiên idle in transaction trên production**: việc hủy/đóng connection có thể rollback công việc hợp lệ và ảnh hưởng người dùng.

### 10.4. Phân biệt backend đang chờ lock với chờ client

Một backend có `wait_event_type = 'Lock'` có thể đang chờ một lock PostgreSQL:

~~~sql
SELECT
    a.pid,
    a.usename,
    a.application_name,
    a.state,
    a.wait_event_type,
    a.wait_event,
    pg_blocking_pids(a.pid) AS blocking_pids,
    LEFT(a.query, 120) AS query_preview
FROM pg_stat_activity AS a
WHERE a.wait_event_type = 'Lock'
ORDER BY a.pid;
~~~

`pg_blocking_pids(pid)` giúp tìm những process đang chặn PID được hỏi. Nó có giới hạn theo quyền và bối cảnh khóa. Một backend đang đợi client gửi lệnh sẽ có loại chờ khác, thường thuộc nhóm `Client`; điều đó không đồng nghĩa database đang bị khóa dữ liệu.

### 10.5. Tham chiếu PID tới câu lệnh chính mình

~~~sql
SELECT
    pg_backend_pid() AS current_pid,
    pg_postmaster_start_time() AS server_started_at,
    current_database() AS current_database,
    current_setting('application_name') AS application_name;
~~~

`pg_postmaster_start_time()` cho biết thời điểm khởi động của server chính hiện tại; nó **không** phải PID của tiến trình điều phối. `pg_backend_pid()` là PID của connection đang thực hiện câu SQL.

## 11. Connection pool và PgBouncer: nhìn từ góc độ tiến trình

Vì PostgreSQL dùng backend process cho connection, một ứng dụng có hàng nghìn client đồng thời không nhất thiết nên tạo hàng nghìn **kết nối vật lý** trực tiếp đến PostgreSQL. Việc mở connection có chi phí tạo process, khởi tạo trạng thái phiên, phân bổ bộ nhớ; quá nhiều kết nối còn gây cạnh tranh CPU, cache và tài nguyên quản trị.

Ví dụ:

~~~text
30 instance ứng dụng
  x 20 connection trong mỗi pool
  = tối đa 600 backend connection dự kiến
    nếu tất cả pool đều mở đầy và dùng trực tiếp PostgreSQL
~~~

Con số 600 là phép tính cấu hình **tiềm năng**, không có nghĩa luôn có đúng 600 backend đang chạy SQL. Một số connection có thể idle; số đang được mở thực tế phụ thuộc hành vi của pool.

### 11.1. Connection pool ở ứng dụng

Hệ thống Java thường dùng `DataSource` và pool như HikariCP. Pool giữ các connection tái sử dụng giữa nhiều request HTTP. Một connection trả về pool có thể vẫn được duy trì trong PostgreSQL:

~~~mermaid
flowchart LR
    R1["HTTP request 1"] --> POOL["Application connection pool"]
    R2["HTTP request 2"] --> POOL
    R3["HTTP request 3"] --> POOL
    POOL --> A["PostgreSQL backend A"]
    POOL --> B["PostgreSQL backend B"]
~~~

Khi thiết kế pool, phải xem cả:

- `max_connections` của PostgreSQL và số slot dành cho kết nối quản trị/đặc biệt.
- Tổng số instance ứng dụng, không chỉ cấu hình của một instance.
- Chi phí RAM cho từng backend và các query chạy đồng thời.
- Thời gian transaction, query timeout và connection acquisition timeout.
- Khả năng server đáp ứng thực tế, tránh chỉ tăng pool size khi query chậm.

~~~sql
SHOW max_connections;
SHOW superuser_reserved_connections;
~~~

Trong những phiên bản mới có thể có thêm các tham số liên quan connection reserve; cần đọc cấu hình theo phiên bản. Một số background/replication workers được quản lý bằng giới hạn riêng nên **không nên cộng tất cả process trong hệ điều hành rồi so một-một với `max_connections`**.

### 11.2. PgBouncer và giới hạn ngữ nghĩa phiên

`PgBouncer` là một connection pooler ngoài PostgreSQL. Nó có thể nhận nhiều client connection rồi dùng một tập server connections nhỏ hơn. Trong **transaction pooling**, một client có thể được ánh xạ sang backend PostgreSQL khác ở transaction tiếp theo.

~~~text
Client X --transaction 1--> PgBouncer --> Backend 10
Client X --transaction 2--> PgBouncer --> Backend 12
~~~

Điều này hữu ích cho ứng dụng có nhiều kết nối ngắn, nhưng **không được giả định trạng thái session luôn tồn tại qua các transaction**. Những tính năng như temporary tables sống qua transaction, session-level advisory locks, session settings, server-side prepared statements và một số cursor có thể cần được thiết kế riêng hoặc phụ thuộc mức hỗ trợ của PgBouncer/driver.

Nếu ứng dụng cần một backend cố định trong toàn phiên, **session pooling** có hành vi phù hợp hơn ở khía cạnh giữ connection, nhưng hiệu quả chia sẻ backend và mức tiêu thụ tài nguyên khác với transaction pooling.

Không chỉ thêm PgBouncer rồi coi như mọi vấn đề performance được giải quyết. Pooler giảm chi phí quản lý connection trong một số workload; nó **không làm một truy vấn nặng trở nên nhẹ hơn**, không thay thế index, vacuum hoặc điều chỉnh SQL.

## 12. Thực hành quan sát hai phiên kết nối và tiến trình nền

Phần này chỉ dùng những truy vấn đọc/thực hành an toàn trên **database lab riêng**. Cần có quyền kết nối PostgreSQL và công cụ `psql` hoặc một SQL client tương đương.

### Bài thực hành 1 — Hai connection, hai PID

**Phiên A**, kết nối qua `psql`:

~~~sql
SET application_name = 'lesson55_A';

SELECT
    pg_backend_pid() AS pid_a,
    current_database() AS db_a,
    current_user AS user_a;
~~~

**Phiên B**, mở một connection khác:

~~~sql
SET application_name = 'lesson55_B';

SELECT
    pg_backend_pid() AS pid_b,
    current_database() AS db_b,
    current_user AS user_b;
~~~

Sau đó ở một trong hai phiên:

~~~sql
SELECT
    pid,
    application_name,
    backend_type,
    state
FROM pg_stat_activity
WHERE application_name IN ('lesson55_A', 'lesson55_B')
ORDER BY application_name;
~~~

Kỳ vọng **hai PID khác nhau** và `backend_type = 'client backend'`. Nếu một công cụ SQL tự động đóng/reconnect mỗi statement, PID có thể đổi khi thực hiện truy vấn khác; cần phân biệt hành vi công cụ với hành vi của PostgreSQL.

### Bài thực hành 2 — Nhìn một backend đang chạy

Trong **phiên A**:

~~~sql
SELECT pg_sleep(15);
~~~

Trong khoảng lệnh đang thực thi, ở **phiên B**:

~~~sql
SELECT
    pid,
    application_name,
    state,
    wait_event_type,
    wait_event
FROM pg_stat_activity
WHERE application_name = 'lesson55_A';
~~~

Trên nhiều bản PostgreSQL, có thể thấy `state = 'active'` cùng wait event biểu thị đang chờ trong `pg_sleep`. **Active** nghĩa là statement còn trong quá trình thực thi, không nhất thiết đang tiêu tốn CPU trong mọi khoảnh khắc.

Nếu truy vấn quá nhanh kết thúc trước khi kịp quan sát, lặp lại trong lab với thời lượng phù hợp. Không dùng một câu sleep dài trên production chỉ để tạo ví dụ.

### Bài thực hành 3 — Quan sát idle in transaction

Trong **phiên A**:

~~~sql
BEGIN;

SELECT 1 AS still_in_transaction;

-- Để nguyên phiên ở prompt, chưa COMMIT/ROLLBACK.
~~~

Trong **phiên B**:

~~~sql
SELECT
    pid,
    application_name,
    state,
    now() - xact_start AS transaction_age
FROM pg_stat_activity
WHERE application_name = 'lesson55_A';
~~~

Kỳ vọng thấy trạng thái `idle in transaction` sau khi câu `SELECT 1` đã kết thúc nhưng transaction vẫn còn mở. Quay lại phiên A và dọn:

~~~sql
ROLLBACK;
~~~

Nếu quan sát lại, phiên A thường chuyển về `idle`. Với client có chế độ tự động transaction hoặc pooling khác nhau, trạng thái hiển thị có thể cần giải thích theo hành vi của công cụ.

### Bài thực hành 4 — Quan sát background types

~~~sql
SELECT backend_type, COUNT(*) AS cnt
FROM pg_stat_activity
GROUP BY backend_type
ORDER BY cnt DESC, backend_type;
~~~

Hãy chỉ ra các loại có thể xuất hiện như `checkpointer`, `background writer`, `walwriter` và `autovacuum launcher`. Nếu không thấy `autovacuum worker` hoặc `parallel worker` thì cũng có thể bình thường: đó là các worker thường chỉ được tạo khi có công việc phù hợp.

### Bài thực hành 5 — Quan sát workload replication nếu có

Nếu server lab đã cấu hình physical replication:

~~~sql
-- Chạy trên primary:
SELECT
    application_name,
    state,
    sync_state
FROM pg_stat_replication;
~~~

Trên instance standalone, truy vấn thường trả 0 dòng. Không cần thiết phải dựng thêm replica chỉ để học cấu trúc cơ bản; bài tập này dành cho môi trường đã có sẵn topology thử nghiệm.

## 13. Chẩn đoán theo triệu chứng: process nào đáng quan tâm?

| Triệu chứng | Process hoặc view cần xem | Câu hỏi điều tra |
| --- | --- | --- |
| Ứng dụng không lấy được connection | Client backends, `pg_stat_activity`, pool, `max_connections` | Quá nhiều phiên idle hay active? Pool có bị rò connection không? |
| Truy vấn đột ngột chậm | Backend đang active, `EXPLAIN`, wait events | Chờ CPU, I/O, lock hay đang thực thi kế hoạch kém? |
| Nhiều phiên `idle in transaction` | Client backends và `xact_start` | Có code mở transaction rồi không commit/rollback đúng lúc? |
| Table bloat tăng nhanh | Autovacuum workers, `pg_stat_user_tables` | Có nhiều UPDATE/DELETE, transaction lâu, vacuum không theo kịp? |
| Ghi đĩa tạo các đợt I/O lớn | Checkpointer, bgwriter, backend writes, storage metrics | Checkpoint quá thường xuyên, workload tăng hay thiết bị chậm? |
| Độ trễ commit lớn | WAL writer, WAL flush, synchronous replication và storage | Chậm do flush WAL, mạng standby hay tranh chấp? |
| WAL archive không cập nhật | Archiver, `pg_stat_archiver`, log | Archive command lỗi, thiếu quyền, đầy dung lượng? |
| Replica theo kịp chậm | WAL sender/receiver, recovery process và replication views | Mạng chậm, WAL receiver, replay hay resource bottleneck? |
| Một truy vấn dùng CPU trên nhiều core | Leader backend và parallel workers | Kế hoạch song song có thật sự hiệu quả không? |
| PostgreSQL restart sau sự cố | Main process, log startup/recovery | Backend crash, lỗi memory/storage hay hệ điều hành? |

Nguyên tắc chẩn đoán: **đừng chỉ nhìn số process**. Cần kết hợp loại process, trạng thái, thời gian chờ, số transaction đang mở, I/O và log để hiểu tình huống thực.

### 13.1. Nhiều tiến trình postgres chưa chắc là rò rỉ

Một server có 200 client connection cùng các tiến trình nền có thể hiển thị hơn 200 process `postgres`. Nếu `max_connections` và pool được thiết kế cho workload đó, điều này chưa tự chứng minh có lỗi. Ngược lại, 20 connection nhưng có nhiều transaction giữ lock hàng giờ vẫn có thể gây sự cố nghiêm trọng.

### 13.2. Không tự ý kill process PostgreSQL ở hệ điều hành

Khi một backend chạy truy vấn nặng, người quản trị có thể cân nhắc dùng các hàm PostgreSQL thay vì gửi tín hiệu cưỡng bức ở OS. Ví dụ:

~~~sql
-- Chỉ minh họa, không chạy khi chưa xác minh PID và quyền:
SELECT pg_cancel_backend(<pid>);
~~~

Trong ví dụ trên, `<pid>` là chỗ giữ chỗ **không phải SQL hợp lệ** cho đến khi được thay bằng một PID số đã xác minh. `pg_cancel_backend` yêu cầu hủy **truy vấn hiện tại** của backend; `pg_terminate_backend` có phạm vi mạnh hơn là kết thúc **session**, có thể rollback transaction của session đó. Quyền gọi các hàm này bị giới hạn và tác động đến người dùng thật.

**Không gửi `kill -9`/TerminateProcess bừa bãi vào tiến trình PostgreSQL trên production.** Một lỗi process có thể kích hoạt các cơ chế bảo vệ và recovery phức tạp hơn việc hủy truy vấn có kiểm soát.

## 14. Những nhầm lẫn kiến trúc thường gặp

| Nhầm lẫn | Sự thật |
| --- | --- |
| “Một PostgreSQL instance chỉ có một process” | Có process chính, các client backend và các background/auxiliary processes |
| “Mỗi SQL statement tạo một process mới” | Một backend thường phục vụ nhiều statement của cùng connection |
| “Một connection luôn là một process ở ứng dụng” | Backend process chạy ở **server**; phía client là connection giao thức |
| “Thêm 500 connection là tăng hiệu năng” | Nhiều backend tăng overhead và cạnh tranh; cần pool size phù hợp |
| “Mỗi backend có một bản sao shared_buffers” | `shared_buffers` là bộ nhớ chia sẻ của instance |
| “Có WAL writer thì backend không bao giờ ghi WAL” | Backend có thể tham gia ghi/flush WAL khi cần bảo đảm commit |
| “Checkpoint là lúc mọi transaction mới được commit” | Commit dựa vào quy tắc durability/WAL; checkpoint là mốc quản trị ghi và recovery |
| “Bgwriter là process duy nhất viết trang dữ liệu” | Checkpointer và backend cũng có thể ghi trang dữ liệu |
| “Autovacuum chạy tức là database đang gặp lỗi” | Đây là công việc bảo trì thông thường, cần cho MVCC và thống kê |
| “Tắt autovacuum để server nhẹ hơn luôn an toàn” | Có thể gây bloat và rủi ro transaction ID wraparound |
| “Replica cần một client backend thông thường cho mỗi transaction” | Streaming replication có WAL sender/receiver và recovery processes chuyên trách |
| “Parallel workers là thêm kết nối từ ứng dụng” | Chúng hỗ trợ xử lý một query phía server, không phải client session độc lập |
| “`active` nghĩa là đang dùng 100% CPU” | Backend có thể active nhưng đang đợi lock, I/O hoặc timer |
| “`idle` nghĩa là không tốn tài nguyên” | Connection idle vẫn giữ backend và tài nguyên phiên |
| “`idle in transaction` vô hại như idle” | Có thể giữ lock/snapshot và ảnh hưởng VACUUM |
| “Xem được `pg_stat_activity` nghĩa là thấy mọi chi tiết mọi process” | Visibility phụ thuộc quyền, loại process và phiên bản |

## 15. Bài tập vận dụng

### Bài 1 — Suy ra số client backend

Một ứng dụng có 4 instance. Mỗi instance cấu hình pool tối đa 15 connection trực tiếp đến PostgreSQL. Hãy tính số backend từ ứng dụng này khi **mọi pool đều mở đầy**, chưa tính admin connection và thành phần nền.

**Đáp án gợi ý:** 4 × 15 = **60 client backends** tiềm năng. Đây không phải số truy vấn chạy song song chắc chắn và cũng chưa phải tổng số process PostgreSQL.

### Bài 2 — Phân biệt các mốc ghi dữ liệu

Một câu `UPDATE` đã `COMMIT` thành công, nhưng trang dữ liệu của bảng vẫn dirty trong `shared_buffers`. Có phải transaction chưa bền vững không?

**Gợi ý:** không kết luận như vậy. Với cấu hình durability thông thường, WAL được ghi/flush theo quy tắc commit trước khi cần flush trang data file. Trang dữ liệu có thể được checkpointer/bgwriter/backend ghi về file sau đó; crash recovery dùng WAL khi cần.

### Bài 3 — Tại sao có 10 dòng `postgres` khi chỉ mở 2 psql?

Hãy xác định process chính, hai client backends và các tiến trình như checkpointer, bgwriter, walwriter, autovacuum launcher từ output của hệ điều hành hoặc `pg_stat_activity`.

**Gợi ý:** nhiều process không đồng nghĩa nhiều kết nối user. Một số background processes hoạt động độc lập và tên hiển thị phụ thuộc phiên bản.

### Bài 4 — Tại sao nhiều idle in transaction khiến table bloat tăng?

Giả sử transaction A mở snapshot rồi để idle rất lâu; các transaction B liên tục cập nhật hàng. Hãy giải thích cơ chế MVCC và vì sao VACUUM có thể chưa dọn được những phiên bản hàng cũ mà transaction A vẫn có thể cần thấy.

**Gợi ý:** phân biệt `idle` không có transaction với `idle in transaction` giữ transaction mở; điều tra `xact_start` và logic ứng dụng.

### Bài 5 — Kiểm tra backend hiện tại

Mở hai connection `psql` độc lập và chạy:

~~~sql
SELECT pg_backend_pid(), current_database(), current_user;
~~~

So sánh PID. Ở một phiên, chạy `SELECT pg_sleep(10)`; ở phiên còn lại đọc `pg_stat_activity`. Giải thích vì sao `state` có thể là `active` nhưng `wait_event` cho thấy backend đang đợi.

### Bài 6 — Chọn process để điều tra theo tình huống

| Tình huống | Nhóm process đáng xem đầu tiên |
| --- | --- |
| WAL không archive thành công | Archiver và `pg_stat_archiver` |
| Standby bị replay lag | WAL receiver, startup/recovery và metrics replication |
| Query `COUNT(*)` lớn dùng `Gather` | Leader backend và parallel workers |
| Nhiều deadlocks | Các client backends, locks và transaction boundaries |
| Truy vấn chờ connection pool | Client backends, pool và giới hạn kết nối |
| Bảng có nhiều dead tuples lâu không giảm | Autovacuum và long-running transactions |

### Bài 7 — Thiết kế connection pool

Một server có tài nguyên đủ cho số lượng truy vấn đang chạy hữu ích tương đối hạn chế, nhưng ứng dụng có hàng nghìn request ngắn. Hãy giải thích:

1. Vì sao mở hàng nghìn connection PostgreSQL trực tiếp có thể không tốt?
2. Connection pool ở ứng dụng giảm chi phí nào?
3. PgBouncer transaction pooling khác session pooling ở khả năng giữ trạng thái phiên thế nào?
4. Vì sao cần kiểm tra prepared statements, temporary tables và session settings trước khi thay đổi chế độ pooling?

### Bài 8 — Đọc một bảng trạng thái

Giả sử `pg_stat_activity` báo:

~~~text
PID    backend_type     state                  wait_event_type
3010   client backend   active                 Lock
3011   client backend   idle in transaction    Client
3012   client backend   idle                   Client
3013   background writer (null)                (null)
~~~

Hãy nêu:

- PID 3010 có thể đang chờ điều gì?
- Tại sao PID 3011 đáng điều tra hơn một kết nối idle thông thường?
- Có thể gọi `pg_cancel_backend(3013)` như thể background writer là truy vấn người dùng không?
- Chỉ dựa vào bảng này có đủ căn cứ để terminate PID 3011 không?

**Gợi ý:** cần xác định nguyên nhân khóa, tuổi transaction, nguồn ứng dụng và quyền/tác động trước khi can thiệp. Background writer không phải session SQL người dùng. Không được tự hủy process nền.

## 16. Tổng kết

Trong PostgreSQL, **tiến trình chính/postmaster** điều phối khởi động, kết nối và vòng đời server. **Client backend** phục vụ một connection, xử lý các statement và transaction, sử dụng bộ nhớ riêng đồng thời phối hợp qua shared memory. **Các tiến trình nền** đảm nhận những nhiệm vụ dài hạn và độc lập hơn: background writer giảm áp lực buffer, checkpointer quản lý checkpoint, WAL writer hỗ trợ ghi nhật ký, autovacuum giữ dữ liệu MVCC và thống kê, còn các tiến trình replication/recovery phục vụ sao chép và phục hồi.

Những thành phần này phối hợp thay vì tồn tại tách biệt hoàn toàn. Khi đọc một câu SQL, backend có thể sử dụng shared buffers và chờ lock; khi `COMMIT`, WAL và cấu hình durability quyết định những đảm bảo cần thiết; sau đó các process ghi nền tiếp tục làm việc. Với truy vấn lớn, PostgreSQL có thể dùng parallel workers; với ứng dụng nhiều kết nối, connection pool giúp kiểm soát số backend.

Hiểu đúng **ai nhận kết nối, ai chạy truy vấn và ai bảo trì hệ thống** giúp người phát triển tránh những quyết định sai như tăng connection vô hạn, tắt autovacuum hoặc kill nhầm tiến trình. Đây cũng là nền tảng để sử dụng `pg_stat_activity`, `EXPLAIN` và các system views nhằm quan sát, giải thích và vận hành PostgreSQL có kiểm soát.
