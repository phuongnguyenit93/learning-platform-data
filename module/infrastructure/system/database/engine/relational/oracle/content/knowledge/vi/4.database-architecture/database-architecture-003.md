# Tiến trình người dùng, server process và background process trong kiến trúc Oracle Database

Khi ứng dụng gửi một câu lệnh SQL đến Oracle Database, không phải chương trình ứng dụng tự mở và đọc trực tiếp tệp dữ liệu. Thay vào đó, **user process** gửi yêu cầu; **server process** của Oracle tiếp nhận và thực thi yêu cầu; **background processes** duy trì những công việc chung như ghi redo, ghi các khối dữ liệu đã thay đổi, checkpoint, giám sát và phục hồi.

Phân biệt đúng ba loại tiến trình này giúp giải thích vì sao một thao tác `COMMIT` có thể hoàn tất trước khi dữ liệu được ghi vào datafile, tại sao hàng nghìn phiên kết nối không nhất thiết có hàng nghìn server process, và vì sao tiến trình nền dừng có thể ảnh hưởng đến cả instance.

Bài học xét kiến trúc Oracle Database quan hệ (đặc biệt mô hình phổ biến trên Linux/Unix). Tên tiến trình, số lượng tiến trình và cách chúng hiển thị ở hệ điều hành có thể khác theo phiên bản, cấu hình, Oracle RAC, multitenant và chế độ chạy bằng OS thread.

## 1. Đặt ba loại tiến trình vào bức tranh kiến trúc

Một **Oracle Database** có hai phần khái niệm quan trọng:

- **Database**: các tệp vật lý lưu dữ liệu và thông tin để phục hồi, gồm datafiles, control files, online redo log files; ngoài ra còn có tempfile và các tệp liên quan tùy cấu hình.
- **Database instance**: **System Global Area (SGA)** và các **background processes** phục vụ việc quản lý, truy cập, ghi và phục hồi database.

Khi một ứng dụng làm việc với Oracle, các **user processes** và **server processes** tham gia ở phía trên instance để xử lý các yêu cầu SQL. Trong một hệ thống Oracle RAC, nhiều instance có thể truy cập cùng một database; mỗi instance có SGA và nhóm background process riêng.

### 1.1. Sơ đồ kiến trúc tổng quan

```text
             MÁY CLIENT / MÁY ỨNG DỤNG
        +--------------------------------+
        |  User process                  |
        |  SQL*Plus / SQLcl / JDBC app   |
        +----------------+---------------+
                         |
                         | SQL request / result
                         | Oracle Net hoặc kết nối cục bộ
                         v
             MÁY CHỦ ORACLE DATABASE
        +--------------------------------+
        |  Server process                |
        |  - nhận yêu cầu                |
        |  - parse / execute / fetch     |
        |  - sử dụng PGA riêng           |
        +----------------+---------------+
                         |
                         v
        +--------------------------------+
        | ORACLE INSTANCE                |
        |                                |
        |  SGA:                          |
        |  - Shared Pool                 |
        |  - Database Buffer Cache       |
        |  - Redo Log Buffer             |
        |                                |
        |  Background processes:         |
        |  DBWn, LGWR, CKPT, PMON,       |
        |  SMON, LREG, ARCn, ...         |
        +---------+--------------+-------+
                  |              |
                  v              v
              Datafiles      Online redo
              Control files  Archive logs
```

Sơ đồ mô tả vai trò, không có nghĩa mỗi user process luôn có một server process riêng. Điều đó phụ thuộc vào mô hình **dedicated server**, **shared server** hoặc **Database Resident Connection Pooling (DRCP)**.

### 1.2. Bảng so sánh nhanh

| Tiêu chí | User process | Server process | Background process |
| --- | --- | --- | --- |
| Nơi chạy thường gặp | Máy client hoặc máy ứng dụng; cũng có thể ở database server | Trên máy chủ Oracle Database | Trong môi trường Oracle instance |
| Do ai tạo/quản lý? | Hệ điều hành và chương trình client | Hạ tầng Oracle khi xử lý kết nối, tùy mô hình server | Oracle khởi tạo/quản lý cho các tác vụ của instance |
| Vai trò chính | Gửi lệnh SQL, nhận kết quả | Thực thi yêu cầu từ phiên client | Làm công việc chung, nền tảng và bảo trì |
| Có đại diện cho một user database cố định? | Không nhất thiết: một ứng dụng có thể mở nhiều session | Dedicated thường phục vụ một kết nối; shared/pooled có thể phục vụ nhiều session lần lượt | Không: thực hiện công việc chung của instance |
| Bộ nhớ chính | Bộ nhớ của client/process ứng dụng | **PGA** riêng, đồng thời truy cập **SGA** | PGA riêng và quyền truy cập SGA cần thiết |
| Ví dụ | `sqlplus`, ứng dụng Java | Dedicated server process, shared server process | `LGWR`, `DBW0`, `CKPT`, `PMON` |

**Điểm cốt lõi:** ba loại tiến trình là ba vai trò trong xử lý. Một **database user**, một **database session** và một **OS process** là các khái niệm khác nhau.

## 2. User process: phía phát sinh yêu cầu

### 2.1. User process là gì?

**User process** là tiến trình thực thi ứng dụng phía client để tương tác với Oracle Database. Khi người dùng mở SQL*Plus và chạy `SELECT ...`, chương trình SQL*Plus là một ví dụ dễ hình dung. Với ứng dụng Java, tiến trình JVM chạy dịch vụ có thể đóng vai trò user process và gửi SQL qua JDBC.

Các trách nhiệm thường gặp:

1. Thu thập thao tác người dùng hoặc logic nghiệp vụ.
2. Kết nối đến Oracle thông qua driver/client library.
3. Gửi SQL statement, bind variables, dữ liệu nhập và yêu cầu giao dịch.
4. Nhận dòng kết quả, thông báo lỗi hoặc trạng thái thực thi.
5. Hiển thị dữ liệu, xử lý tiếp hoặc gửi phản hồi đến một lớp ứng dụng khác.

User process **không tự đọc datafile, không tự ghi redo log của instance** và không trực tiếp thực thi SQL engine bên trong Oracle server. Việc thực hiện SQL được chuyển sang server process và các thành phần database.

### 2.2. Một ứng dụng có thể tạo nhiều session

Ví dụ dịch vụ Java nhận 200 yêu cầu HTTP đồng thời. Dịch vụ này có thể:

- chạy trong **một JVM process**;
- duy trì **một connection pool** với 20 kết nối Oracle;
- sử dụng mỗi kết nối để giao tiếp với một hoặc nhiều database session theo cơ chế client/pooling đang áp dụng.

Do đó, **200 HTTP requests ≠ 200 user processes ≠ 200 Oracle sessions ≠ 200 server processes**.

Số lượng kết nối đồng thời thực tế được quyết định bởi cấu hình connection pool, workload, mô hình Oracle server và các giới hạn tài nguyên.

### 2.3. Client ở xa hay cùng máy?

User process có thể chạy:

- **Từ xa**, ví dụ Java backend trên máy ứng dụng kết nối tới `db01.example.com:1521` qua Oracle Net.
- **Cục bộ**, ví dụ SQL*Plus chạy trên chính database server và kết nối trực tiếp đến instance.

Vị trí client chỉ quyết định đường giao tiếp. Dù ở cùng máy, chương trình SQL*Plus vẫn là **user process**, còn server process của Oracle vẫn đảm nhiệm phần xử lý trong database.

## 3. Server process: phía thực hiện yêu cầu SQL

### 3.1. Server process làm những gì?

**Server process** là tiến trình Oracle phục vụ yêu cầu từ client. Những công việc chính gồm:

- Tiếp nhận yêu cầu từ user process qua kết nối được thiết lập.
- Kiểm tra ngữ cảnh phiên, quyền và trạng thái giao dịch.
- **Parse SQL**: kiểm tra cú pháp/ngữ nghĩa và tìm hoặc tạo cách thực thi phù hợp (cùng các cấu trúc liên quan trong shared pool).
- **Execute**: thực hiện phương án thực thi, truy cập các block trong database buffer cache hoặc đọc block cần thiết từ datafile theo cơ chế của Oracle.
- Thực hiện thao tác DML, quản lý thay đổi trong buffer cache, undo và redo.
- **Fetch** và gửi dòng kết quả về cho client, hoặc trả trạng thái/sai lỗi của câu lệnh.

Server process không phải là database user: nó **thực thi dưới ngữ cảnh session và đặc quyền của database user**. Trong mô hình shared server, cùng một tiến trình server có thể phục vụ lần lượt các yêu cầu thuộc nhiều phiên khác nhau.

### 3.2. Server process sử dụng PGA và SGA thế nào?

- **Program Global Area (PGA)**: vùng bộ nhớ riêng của một tiến trình Oracle; chứa các vùng làm việc và trạng thái cần thiết, ví dụ cho sort/hash operation tùy kế hoạch thực thi. Các tiến trình khác không truy cập PGA như một vùng chia sẻ chung.
- **SGA**: vùng bộ nhớ chung của instance; server process truy cập các thành phần như **shared pool**, **database buffer cache** và **redo log buffer**.

Một ví dụ đọc dữ liệu:

```text
Server process
   |
   +-- Tìm SQL/cursor trong Shared Pool
   |
   +-- Tìm block cần đọc trong Database Buffer Cache
   |      |
   |      +-- Có block: đọc từ cache
   |      |
   |      +-- Chưa có: thực hiện I/O thích hợp để lấy block
   |
   +-- Xử lý điều kiện lọc, biểu thức, sắp xếp...
   |
   +-- Trả các dòng kết quả về user process
```

Không phải tất cả dữ liệu truy vấn đều phải đi qua buffer cache theo cùng cách. Oracle có thể dùng các chiến lược truy xuất như **direct path read**, parallel execution và các cơ chế tối ưu khác. Mục tiêu của sơ đồ là phân biệt vai trò, không giới hạn mọi execution plan vào một đường I/O duy nhất.

### 3.3. Dedicated server: một tiến trình phục vụ một kết nối

Ở mô hình **dedicated server**, một client connection thường có **một dedicated server process** phục vụ các yêu cầu liên tiếp trong thời gian kết nối tồn tại.

```text
User process A  <------>  Dedicated server A  ---+
                                                |
User process B  <------>  Dedicated server B  ---+--> SGA / Database
                                                |
User process C  <------>  Dedicated server C  ---+
```

Ưu điểm là đường xử lý dễ hiểu, phù hợp nhiều workload và các thao tác yêu cầu một server process phục vụ session liên tục. Đổi lại, nếu có rất nhiều kết nối mở và không hoạt động, lượng tài nguyên dành cho server processes có thể tăng đáng kể.

Thông thường, một kết nối chuyên dụng dùng một dedicated server process trong Oracle; nhưng số user process, số connection, số session và số OS process không phải lúc nào cũng khớp một-một trong mọi driver hoặc cơ chế pooling.

### 3.4. Shared server: nhiều session chia sẻ một nhóm server process

Ở mô hình **shared server** (còn gọi là Multi-Threaded Server trong một số tài liệu cũ), Oracle dùng **dispatcher processes** và **shared server processes**.

```text
Client A ----\
Client B -----+----> Dispatcher(s)
Client C ----/           |
                         v
                 Request queue trong SGA
                         |
                  +------+------+
                  |             |
            Shared server S0  Shared server S1
                  |             |
                  +------+------+
                         |
                 Response / dispatcher
                         |
                       Client
```

Một shared server xử lý một yêu cầu của session, sau đó có thể phục vụ yêu cầu từ session khác. Mô hình này thích hợp khi có nhiều session đồng thời nhưng không phải session nào cũng thường xuyên hoạt động. Để duy trì trạng thái session khi yêu cầu được xử lý bởi các server khác nhau, **UGA (User Global Area)** nằm trong bộ nhớ chia sẻ của instance, thường ở **large pool** nếu được cấu hình và có thể ở **shared pool** theo cấu hình.

Không nên kết luận shared server luôn nhanh hơn dedicated. Shared server có chi phí dispatcher/queue và cần cân nhắc loại workload, mức đồng thời, các yêu cầu tương thích của tính năng và sizing bộ nhớ.

### 3.5. Database Resident Connection Pooling (DRCP)

**DRCP** là một cơ chế pooling phía Oracle Database để các client/connection có thể dùng lại nhóm server processes cư trú trong database theo chính sách pool. Đây là lựa chọn hữu ích với nhiều kết nối có thời gian sử dụng ngắn hoặc ứng dụng dùng pooling tương thích DRCP.

Cần tách ba khái niệm:

- **Application connection pool**: chương trình giữ và tái sử dụng kết nối từ phía ứng dụng (ví dụ HikariCP trong Java).
- **Shared server**: nhiều session được phục vụ qua dispatchers và nhóm shared servers.
- **DRCP**: pool các server processes bên database, được client hỗ trợ/cấu hình phù hợp.

Chúng giải quyết bài toán tương đồng về tài nguyên kết nối, nhưng cơ chế và các yêu cầu cấu hình khác nhau. Không gọi mọi dạng “pool” là shared server.

## 4. Background process: tiến trình nền của instance

**Background processes** của Oracle thực hiện các công việc mà nếu để mỗi server process đảm nhiệm độc lập sẽ khó bảo đảm tính nhất quán, khả năng phục hồi hoặc hiệu năng của toàn instance.

Một số tiến trình thường chạy liên tục; một số chỉ xuất hiện khi bật tính năng hoặc có workload tương ứng. Danh sách chính xác thay đổi theo release và cấu hình.

### 4.1. Các background process cốt lõi

| Tiến trình | Tên đầy đủ / vai trò | Công việc chính | Điều dễ nhầm |
| --- | --- | --- | --- |
| **DBWn**, thường có `DBW0` | Database Writer | Ghi **dirty buffers** từ database buffer cache xuống **datafiles**. Có thể có nhiều database writers. | Không phải tiến trình xác nhận mọi lần `COMMIT`. |
| **LGWR** | Log Writer | Ghi dữ liệu **redo** từ redo log buffer vào **online redo log files**, đặc biệt khi cần bảo đảm commit. | LGWR không phải tiến trình ghi các data block trực tiếp xuống datafile. |
| **CKPT** | Checkpoint | Phối hợp/checkpoint signaling; cập nhật thông tin checkpoint trong **control file** và header datafiles. | CKPT **không** tự ghi mọi dirty data block; DBWn đảm nhiệm việc đó. |
| **SMON** | System Monitor | Thực hiện/phối hợp những tác vụ phục hồi và dọn dẹp ở mức instance, bao gồm công việc liên quan instance recovery. | Không phải là server process thay user chạy câu SQL. |
| **PMON** | Process Monitor | Theo dõi các tiến trình Oracle và hỗ trợ cleanup khi user/server process thất bại; có thể phối hợp với cleanup helpers tùy release. | Không được coi là công cụ sửa mọi lỗi ứng dụng. |

**Tên DBWn:** chữ `n` biểu thị số thứ tự của database writer; ở hệ thống thực tế có thể thấy `DBW0`, `DBW1`... Tài liệu đôi khi dùng tên tổng quát **DBWR**. Chúng cùng nói về chức năng ghi buffer dữ liệu.

### 4.2. Các background process thường gặp khác

| Tiến trình | Vai trò | Khi nào cần quan tâm? |
| --- | --- | --- |
| **ARCn** / `ARC0`, `ARC1` | Archiver, sao chép các online redo log đã đầy/cần lưu trữ thành archived redo logs theo cơ chế archive. | Backup/recovery, ARCHIVELOG mode, Data Guard. |
| **LREG** | Listener Registration: đăng ký thông tin dịch vụ/instance với listener. | Khi service chưa được listener nhận diện hoặc lỗi kết nối Oracle Net. |
| **MMON**, **MMNL** | Thu thập/điều phối dữ liệu quản lý hiệu năng và một số công việc monitor. | Vận hành, chẩn đoán hiệu năng, tính năng quản lý được cấp phép phù hợp. |
| **RECO** | Recoverer, xử lý các tình huống giao dịch phân tán còn treo. | Distributed transaction hoặc sử dụng database link trong giao dịch liên quan. |
| **CJQ0**, **Jnnn** | Job coordinator và job slaves. | Khi chạy scheduler jobs và tác vụ nền. |
| **QMNC** và tiến trình liên quan | Các chức năng điều phối hàng đợi trong các cấu hình thích hợp. | Khi dùng các cơ chế queue/Advanced Queuing liên quan. |

Không phải hệ thống nào cũng có tất cả những tiến trình trên. Ví dụ, **ARCn** và quy trình archive phụ thuộc cấu hình database; các tiến trình cho Data Guard, RAC, parallel query, ASM hoặc các tính năng khác có vai trò riêng.

Một số tiến trình có tên bắt đầu bằng `P...` là **parallel execution server processes** được Oracle tạo để thực hiện SQL song song. Chúng là worker thực thi tác vụ SQL; không nên tự động coi chúng giống `LGWR` hoặc `DBWn` chỉ vì thấy ở danh sách process hệ điều hành.

### 4.3. Vì sao cần nhiều tiến trình nền?

Oracle chia công việc theo vai trò để tránh mỗi client phải tự quyết định thời điểm ghi log, checkpoint hay phục hồi:

- **LGWR** tối ưu việc ghi redo, có thể gom yêu cầu commit của nhiều transaction (group commit).
- **DBWn** quản lý việc ghi dirty buffers theo các điều kiện của buffer cache/checkpoint, không khóa mỗi transaction đến lúc datafile được ghi.
- **CKPT** điều phối việc xác định tiến độ checkpoint và ghi nhận thông tin checkpoint phù hợp.
- **SMON/PMON** giúp hệ thống xử lý các tình huống cần khôi phục hoặc cleanup ngay cả khi user process đã biến mất.
- **LREG** cho phép listener nắm được dịch vụ mà instance quảng bá.

Cơ chế này giúp phân định **đường thực thi câu SQL** và **công việc cần thiết để instance tồn tại ổn định**.

## 5. Diễn biến của một câu lệnh SELECT

Giả sử ứng dụng Java gọi:

```sql
SELECT employee_id, full_name
FROM   employees
WHERE  department_id = :dept_id;
```

Luồng xử lý đơn giản hóa:

1. **User process:** ứng dụng bind giá trị cho `:dept_id` và gửi câu SQL qua JDBC.
2. **Thiết lập đường kết nối:** Oracle Net và listener tham gia đưa client đến service và server process thích hợp. Trong đường kết nối thông thường, **listener không phải tiến trình thực thi SQL** và không nằm trong đường xử lý mọi câu SQL sau khi kết nối đã được thiết lập.
3. **Server process:** nhận yêu cầu, parse hoặc tái sử dụng cursor, kiểm tra quyền trên bảng, xác định cách truy cập dữ liệu.
4. **SGA / storage:** server process dùng shared pool, database buffer cache hoặc đường đọc phù hợp để lấy dữ liệu.
5. **Server process:** xử lý lọc, biểu thức, phép join hoặc sort nếu có; gửi các dòng kết quả cho client qua một hoặc nhiều lần fetch.
6. **User process:** đọc các dòng kết quả và chuyển thành đối tượng Java/hiển thị trên giao diện.

```text
JDBC application  -->  server process  -->  shared pool / dữ liệu
      ^                    |
      +------ rows --------+
```

Câu lệnh `SELECT` thông thường **không cần LGWR ghi commit record cho chính thao tác đọc**. Background processes vẫn hoạt động cho toàn instance và có thể phục vụ nhiều tác vụ khác tại cùng thời điểm.

## 6. Diễn biến của UPDATE và COMMIT: LGWR khác DBWn ở đâu?

Xét một giao dịch đơn giản:

```sql
UPDATE accounts
SET    balance = balance - 100
WHERE  account_id = 101;

UPDATE accounts
SET    balance = balance + 100
WHERE  account_id = 202;

COMMIT;
```

Giả định các bảng tồn tại và câu lệnh thành công, bản chất xử lý như sau:

### 6.1. Trong lúc thực hiện UPDATE

**User process** gửi câu SQL. **Server process** kiểm tra quyền, tìm dòng dữ liệu và cập nhật các database buffers liên quan; đồng thời Oracle tạo thông tin **undo** để hỗ trợ rollback và nhất quán đọc, cũng như **redo** cho những thay đổi cần phục hồi.

Redo được tạo trong ngữ cảnh xử lý giao dịch và được đặt vào **redo log buffer** trong SGA; các thay đổi của dữ liệu được quản lý trong các buffer liên quan. Việc tạo redo/undo không có nghĩa các datafiles đã được ghi ngay tại thời điểm `UPDATE` chạy.

### 6.2. Khi thực hiện COMMIT

Theo chế độ commit đồng bộ thông thường, Oracle ghi commit record và **LGWR bảo đảm redo cần thiết đã được ghi tới online redo logs** trước khi trả trạng thái commit thành công. Đây là một phần quan trọng của **durability**.

**DBWn có thể ghi dirty data buffers trước hoặc sau thời điểm commit**, tùy hoạt động buffer cache, checkpoint và tài nguyên. Oracle bảo đảm nguyên tắc **write-ahead logging**: redo liên quan cần được bảo vệ phù hợp trước khi dirty data block được ghi xuống datafile.

Vì vậy:

> **`COMMIT` thành công không có nghĩa toàn bộ data block đã được DBWn ghi vào datafile.** Với commit đồng bộ thông thường, khả năng phục hồi dựa trên redo đã được LGWR ghi bền vững.

Có những chế độ commit bất đồng bộ/`NOWAIT` được Oracle hỗ trợ trong một số tình huống; các chế độ đó có đặc tính durability khác. Bài học sử dụng hành vi commit đồng bộ mặc định làm mô hình chính.

### 6.3. Một dòng thời gian minh họa

```text
Thời điểm  User process / Server process       Background process / I/O
---------  ----------------------------------  ---------------------------------------
T1         Gửi UPDATE                           --
T2         Sửa buffer, tạo undo và redo         --
T3         Gửi COMMIT                           LGWR ghi redo và commit record
T4         Nhận "Commit complete"               Redo đã bền vững theo commit thông thường
T5         Đọc dữ liệu mới ở transaction khác    DBWn có thể ghi dirty buffers về datafile
T6         --                                   CKPT cập nhật thông tin checkpoint
```

Các bước nền có thể chồng lấn nhau; biểu đồ không quy định thứ tự thời gian bắt buộc giữa mọi lần DBWn ghi buffer và mỗi câu SQL. Tác dụng chính là phân biệt **ghi redo** với **ghi datafile**.

## 7. Khi một tiến trình gặp sự cố, điều gì xảy ra?

### 7.1. User process hoặc dedicated server process bị ngắt

Giả sử người dùng đóng ứng dụng đột ngột hoặc kết nối mạng mất. Database session có thể vẫn còn một thời gian cho đến khi Oracle phát hiện ngắt kết nối hoặc lỗi tiến trình.

Theo cơ chế quản lý phiên, Oracle có thể:

- phát hiện session/connection không còn hợp lệ;
- thu hồi các tài nguyên và lock liên quan theo quy tắc;
- rollback giao dịch chưa commit;
- dọn dẹp phiên và tiến trình, với sự tham gia của các thành phần monitor/cleanup thích hợp.

Không nên dựa vào việc đóng cửa sổ terminal để bảo đảm một transaction đã `COMMIT` hoặc đã `ROLLBACK`. Trạng thái giao dịch phụ thuộc việc câu lệnh tương ứng có thực sự hoàn tất hay chưa.

### 7.2. Instance bị crash

Khi instance dừng bất thường, phần dữ liệu mới nhất có thể đã tồn tại trong redo logs nhưng chưa được DBWn ghi đầy đủ vào datafiles. Khi instance được khởi động lại, Oracle sử dụng các thông tin trong redo/undo và metadata checkpoint để tiến hành **instance recovery**.

Có thể hình dung:

```text
Trước crash:
  Online redo log:  [thay đổi đã ghi bền vững]
  Datafiles:        [có thể chưa chứa toàn bộ thay đổi mới]

Khởi động lại:
  Đọc thông tin checkpoint / redo cần thiết
      |
      +-- Roll forward các thay đổi từ redo
      |
      +-- Roll back các giao dịch chưa commit
      |
      +-- Khôi phục database về trạng thái nhất quán
```

Oracle quản lý việc phục hồi này bằng cơ chế instance recovery, với sự tham gia của các tiến trình phù hợp như SMON và các recovery workers tùy cấu hình. Đây cũng là một lý do quyết định **COMMIT** của transaction không cần chờ tất cả datafiles được cập nhật ngay lập tức.

### 7.3. Background process thiết yếu bị lỗi

Các tiến trình như LGWR và DBWn giữ vai trò thiết yếu đối với hoạt động an toàn của instance. Nếu một tiến trình nền quan trọng thất bại hoặc không thể tiếp tục làm việc, Oracle có thể chấm dứt instance để bảo vệ tính nhất quán. Điều đó khác với việc một user process đơn lẻ mất kết nối.

Không nên kết luận “thấy tiến trình không hoạt động trong ảnh chụp `top` nghĩa là nó hỏng”: nhiều tiến trình nền bình thường chủ yếu chờ sự kiện cho đến khi có việc cần làm.

## 8. Session, connection, process và thread: không thể dùng thay thế

Những khái niệm này liên quan nhưng khác nhau:

| Khái niệm | Mô tả | Ví dụ |
| --- | --- | --- |
| **Connection** | Kênh giao tiếp vật lý/logical giữa client và database service. | Một kết nối TCP từ ứng dụng đến Oracle. |
| **Session** | Trạng thái đăng nhập và làm việc trong Oracle: user, quyền, transaction, NLS/context, v.v. | Một dòng ứng với phiên trong `V$SESSION`. |
| **User process** | Tiến trình ứng dụng phía client. | JVM, SQL*Plus. |
| **Server process** | Oracle process phục vụ câu SQL của session. | Dedicated server hoặc shared server. |
| **Background process** | Tiến trình đảm nhiệm nhiệm vụ chung của Oracle instance. | LGWR, DBW0. |
| **OS thread** | Đơn vị thực thi của hệ điều hành; Oracle có thể sử dụng nhiều thread trong một OS process tùy platform/cấu hình. | Một process host nhiều Oracle threads. |

Trong mô hình dedicated đơn giản, một session gắn với một dedicated server process. Trong shared server hoặc DRCP, mối quan hệ không còn một-một theo cách đó.

Trên một số nền tảng/cấu hình, Oracle có thể chạy các tác vụ dưới dạng **thread** (ví dụ khi dùng cơ chế threaded execution). Vì vậy, khi nhìn vào Task Manager, `ps` hoặc `top`, không nên đồng nhất số **OS PIDs** với số **Oracle sessions** hoặc số tiến trình logic mà Oracle báo cáo.

### 8.1. Active, inactive và đang chờ

Trong `V$SESSION`:

- `STATUS='ACTIVE'` cho biết session đang thực hiện một database call, nhưng không nhất thiết đang tiêu thụ CPU; nó có thể đang **WAITING** vì I/O, lock hay sự kiện khác.
- `STATUS='INACTIVE'` thường là session đã kết nối nhưng hiện không có database call đang chạy.
- Một server process có thể tồn tại hoặc chờ trong khi client đang suy nghĩ/không gửi câu lệnh mới.

Không thể xác định “tiến trình hỏng” chỉ dựa vào nhãn `ACTIVE`, `INACTIVE` hoặc thời điểm CPU thấp. Cần đánh giá đồng thời thời gian chờ, sự kiện, tiến độ thực thi và workload.

## 9. Thực hành quan sát bằng các dynamic performance views

Các ví dụ sau là lệnh **đọc dữ liệu**. Tài khoản cần có quyền phù hợp với các `V$` views; nếu không đủ quyền có thể gặp `ORA-00942` hoặc lỗi quyền truy cập. Không cấp đặc quyền quản trị rộng chỉ để thử một câu truy vấn.

### 9.1. Kiểm tra instance

```sql
SELECT instance_name,
       host_name,
       status
FROM   v$instance;
```

Dòng trả về xác định instance hiện tại. Một CDB với nhiều PDB có thể sử dụng chung instance đó; tên instance không phải tên của từng PDB.

### 9.2. Quan sát session và server process liên quan

```sql
SELECT s.sid,
       s.serial#,
       s.username,
       s.status,
       s.server,
       s.machine,
       s.program AS client_program,
       s.process AS client_os_process,
       p.spid    AS oracle_os_process,
       p.pname   AS oracle_process_name
FROM   v$session s
LEFT JOIN v$process p
       ON p.addr = s.paddr
WHERE  s.type = 'USER'
AND    s.username IS NOT NULL
ORDER  BY s.sid;
```

Các cột đáng chú ý:

- `SID` và `SERIAL#`: cùng tham gia định danh session tại thời điểm truy vấn.
- `USERNAME`: database user của session; khác với tên tiến trình hệ điều hành.
- `SERVER`: kiểu server phục vụ session; các giá trị có thể gặp gồm `DEDICATED`, `SHARED`, `POOLED`, tùy cấu hình.
- `MACHINE` và `CLIENT_PROGRAM`: thông tin client mà Oracle thu nhận/báo cáo.
- `CLIENT_OS_PROCESS`: định danh process phía client mà session cung cấp.
- `ORACLE_OS_PROCESS`: ID process hệ điều hành phía Oracle qua `V$PROCESS.SPID`.

**Lưu ý:** với shared server/pooled server, mối liên hệ giữa session và một Oracle server process có thể thay đổi theo thời điểm xử lý. Trên cấu hình threaded execution, `SPID` có thể không đủ để nhận diện duy nhất đơn vị thực thi; Oracle còn cung cấp những trường như `STID`/`SOSID` tùy phiên bản và nền tảng. Tham khảo mô tả cột ở release đang sử dụng.

### 9.3. Xem các tiến trình Oracle và tiến trình nền đang hiện diện

```sql
SELECT spid,
       pname,
       program
FROM   v$process
WHERE  pname IS NOT NULL
ORDER  BY pname;
```

`PNAME` giúp nhận diện nhiều background processes có tên như `PMON`, `SMON`, `LGWR`, `DBW0`, `CKPT`, `LREG`. Tên và lượng tiến trình thực tế khác nhau giữa các hệ thống.

Có thể xem mô tả tiến trình từ một view chuyên dụng:

```sql
SELECT name,
       description
FROM   v$bgprocess
WHERE  name IN ('PMON', 'SMON', 'DBW0', 'LGWR', 'CKPT', 'LREG', 'ARC0')
ORDER  BY name;
```

`V$BGPROCESS` chứa thông tin/định nghĩa background processes; một dòng tên xuất hiện không nên được coi là bằng chứng duy nhất rằng tiến trình đó đang hoạt động bình thường. Để kiểm tra tiến trình sống hoặc lỗi, kết hợp `V$PROCESS`, trạng thái instance, alert log và công cụ OS.

### 9.4. Theo dõi giới hạn session/process

```sql
SELECT resource_name,
       current_utilization,
       max_utilization,
       limit_value
FROM   v$resource_limit
WHERE  resource_name IN ('processes', 'sessions')
ORDER  BY resource_name;
```

Mục đích:

- `CURRENT_UTILIZATION`: tài nguyên hiện dùng tại thời điểm quan sát.
- `MAX_UTILIZATION`: đỉnh đã ghi nhận trong vòng đời thống kê tương ứng.
- `LIMIT_VALUE`: mức giới hạn được Oracle báo cáo cho resource.

Nếu số kết nối ứng dụng tăng quá nhanh, các giá trị này giúp xác định giới hạn tài nguyên. Không đặt lại tham số `PROCESSES` hoặc `SESSIONS` tùy tiện trước khi hiểu nguyên nhân connection leak, pooling và tác động bộ nhớ.

### 9.5. Một cách quan sát session đang kết nối

Mở **hai cửa sổ SQL*Plus** bằng tài khoản thực hành đã được cấp quyền.

Cửa sổ A:

```sql
SELECT sys_context('USERENV', 'SID')         AS my_sid,
       sys_context('USERENV', 'SESSION_USER') AS my_user
FROM   dual;
```

Cửa sổ B (bằng tài khoản được phép đọc `V$SESSION`):

```sql
SELECT sid,
       serial#,
       username,
       status,
       server,
       program
FROM   v$session
WHERE  sid = :sid_from_window_a;
```

Với cửa sổ B, thay bind variable `:sid_from_window_a` bằng giá trị SID thực từ cửa sổ A theo cách nhập phù hợp với công cụ. Thử quan sát khi A đang chạy truy vấn và khi A rảnh để thấy thay đổi trạng thái phiên. Cần thận trọng: truy vấn chạy quá nhanh sẽ không dễ bắt được trạng thái `ACTIVE` bằng một lần polling.

## 10. Mối liên hệ với listener, RAC và CDB/PDB

### 10.1. Listener không phải server process thực thi SQL

**Oracle Net Listener** thường giúp client tìm và thiết lập đường kết nối đến database service/server thích hợp. Listener có thể phối hợp với các tiến trình liên quan tùy dedicated/shared, RAC và phương thức kết nối.

Sau khi kết nối được thiết lập theo cách thông thường, **server process** mới là đơn vị xử lý SQL. Listener không thay thế server process để parse `SELECT` hay ghi dữ liệu cho transaction.

Trong kiến trúc shared server, **dispatchers** đóng vai trò nhận/chuyển các yêu cầu client và đưa chúng vào hàng đợi cho shared servers. Dispatcher là tiến trình thuộc cơ chế Oracle shared server, khác listener và khác worker server process.

### 10.2. Oracle RAC

Với **Real Application Clusters (RAC)**, nhiều **instances** có thể cùng mở/truy cập một database:

```text
        Oracle RAC — một database dùng chung
        +-------------------------------+
        |          Database             |
        |  Datafiles / Control / Redo   |
        +---------------+---------------+
                        ^
                +-------+-------+
                |               |
          Instance 1         Instance 2
          SGA riêng          SGA riêng
          LGWR/DBWn/...      LGWR/DBWn/...
          Server processes   Server processes
```

Mỗi instance có nhóm background processes và bộ nhớ riêng để xử lý workload. Trong RAC, Oracle còn có các tiến trình phục vụ phối hợp cache, lock và tài nguyên giữa các instances.

Để quan sát các phiên/tiến trình theo toàn cụm, người quản trị có thể dùng các **`GV$` views**, ví dụ `GV$SESSION` và `GV$PROCESS`, có thêm `INST_ID` để phân biệt instance.

### 10.3. Oracle Multitenant: CDB và PDB

Trong mô hình **CDB/PDB**, một instance CDB phục vụ nhiều **pluggable databases (PDBs)**:

- Một PDB **không mặc nhiên có toàn bộ một nhóm LGWR, DBWn, PMON, SGA độc lập** như một instance riêng.
- Client thường kết nối tới PDB qua **database service** của PDB.
- Server process thực hiện SQL dưới ngữ cảnh container/session thích hợp.
- Các background processes thuộc instance thực hiện công việc cần thiết cho dữ liệu của các container.

Có những kiến trúc triển khai hoặc tính năng multitenant chuyên biệt với hành vi tiến trình khác; khi phân tích hệ thống thực phải đối chiếu version và cấu hình. Với mô hình học cơ bản, **PDB là container logic của database, không phải một instance độc lập**.

## 11. Cách đọc các hiện tượng hiệu năng và vận hành

| Hiện tượng | Có thể liên quan đến | Cần xác minh trước khi kết luận |
| --- | --- | --- |
| Rất nhiều kết nối mở nhưng ít SQL đang chạy | Connection pool, dedicated processes, idle sessions | Số `V$SESSION`, `V$PROCESS`, trạng thái session, cách pool được cấu hình |
| Ứng dụng báo đạt giới hạn process/session | Số server processes, connection leak hoặc cấu hình giới hạn | `V$RESOURCE_LIMIT`, `PROCESSES`, `SESSIONS`, pool, DRCP/shared server |
| `COMMIT` mất nhiều thời gian | Hoạt động ghi redo của LGWR và storage liên quan, cạnh tranh hoặc nguyên nhân khác | Event/wait thích hợp, redo I/O, workload cùng thời điểm |
| Có nhiều dirty buffers | Workload DML, tốc độ ghi DBWn, checkpoint pressure | Chỉ số buffer cache, storage I/O và các chỉ số chẩn đoán phù hợp |
| Listener chạy nhưng client không vào được service | Đăng ký service, trạng thái database/PDB hoặc chính sách mạng | `LREG`, listener services, tên service, log |
| Application process bị ngắt nhưng còn session trong database | Thời điểm phát hiện disconnect, timeout, cleanup | Trạng thái session, timeout/client heartbeat, lịch sử lỗi |
| Oracle server bận CPU nhưng client ít thao tác | SQL đang chạy, parallel execution, background workloads | `V$SESSION`, tiến trình Oracle, SQL ID, job, wait/event |

Không nên quy mọi lần `COMMIT` chậm về DBWn hoặc mọi lần truy vấn chậm về LGWR. Câu SQL có thể chờ CPU, I/O, lock, network, parse, latch, log sync và nhiều điều kiện khác. Cần phân biệt server process đang **làm việc**, **chờ sự kiện** hay **được điều phối**.

### 11.1. Khi nào cân nhắc shared server hoặc DRCP?

Cân nhắc khi ứng dụng có **nhiều kết nối đồng thời**, phần lớn ít hoạt động, làm tăng server process và tài nguyên. Cần đo workload, thử nghiệm tính tương thích ứng dụng/driver và theo dõi các hàng đợi/độ trễ tương ứng.

Một ứng dụng có 20 kết nối được tái sử dụng hiệu quả trong application pool không nhất thiết có lợi khi đổi ngay sang shared server. Đổi mô hình kết nối phải dựa trên **nghẽn tài nguyên đã quan sát** thay vì số lượng user tổng thể.

### 11.2. Vì sao user process không nên thao tác datafiles?

Các tệp database thuộc cơ chế quản lý của Oracle; các tiến trình nội bộ duy trì đồng bộ redo/undo, khóa, cache và checkpoint. Một ứng dụng không nên ghi trực tiếp vào datafiles như ghi một tệp văn bản: điều đó bỏ qua các cơ chế bảo đảm tính nhất quán và phục hồi của cơ sở dữ liệu.

## 12. Các hiểu nhầm phổ biến

**Hiểu nhầm 1: “Một user trong database là một OS process.”**  
Không đúng. Một database user có thể có nhiều session; một application process có thể dùng nhiều connections; một server process có thể phục vụ nhiều session theo thời gian ở shared/pooled mode.

**Hiểu nhầm 2: “DBWn ghi datafile ngay khi người dùng nhấn COMMIT.”**  
Không đúng. LGWR là thành phần then chốt cho ghi redo khi commit đồng bộ. DBWn ghi dirty buffers vào datafile theo hoạt động của database buffer cache/checkpoint.

**Hiểu nhầm 3: “CKPT làm công việc ghi dirty buffers.”**  
Không đúng. CKPT điều phối checkpoint và cập nhật thông tin checkpoint; DBWn đảm nhiệm việc ghi các data buffers từ cache xuống datafiles.

**Hiểu nhầm 4: “Listener thực thi câu SQL.”**  
Không đúng. Listener chủ yếu phục vụ thiết lập/định tuyến kết nối. SQL được server process xử lý với SGA và các thành phần Oracle khác.

**Hiểu nhầm 5: “Background process chỉ chạy khi có client đăng nhập.”**  
Không đúng. Các tiến trình nền là thành phần của instance và nhiều tiến trình tiếp tục làm việc ngay cả khi không có session ứng dụng nào hoạt động.

**Hiểu nhầm 6: “Session INACTIVE nghĩa là đã ngắt kết nối.”**  
Không đúng. Thông thường đây là một session còn kết nối nhưng không đang thực hiện database call.

**Hiểu nhầm 7: “Mỗi PDB có một LGWR riêng.”**  
Không đúng trong kiến trúc CDB/PDB thông thường. Các PDB chia sẻ instance và nhiều thành phần instance, bao gồm nhóm background processes.

## 13. Bài tập tự kiểm tra

### Tình huống 1: Ứng dụng Java

Một dịch vụ Java có một tiến trình JVM, dùng connection pool tối đa 30 connections. Khi có 200 HTTP requests, nhóm phát triển cho rằng chắc chắn có 200 dedicated server processes trên Oracle. Nhận định đó có chắc đúng không?

**Gợi ý:** Không. HTTP request không đồng nhất Oracle connection/session/process; connection pool có thể giới hạn số connections mà ứng dụng mở, và mô hình dedicated/shared/DRCP còn quyết định cách server process được phân bổ.

### Tình huống 2: COMMIT và datafile

Một transaction `UPDATE` rồi `COMMIT` thành công. DBA quan sát datafile chưa chứa toàn bộ dirty blocks mới tại thời điểm đó. Có phải transaction đã không an toàn?

**Gợi ý:** Chưa đủ cơ sở kết luận. Với commit đồng bộ thông thường, redo được LGWR ghi bền vững để phục hồi; DBWn có thể ghi dirty buffers về datafile sau đó.

### Tình huống 3: Phân vai tiến trình

Hãy gán vai trò cho các thao tác:

1. JDBC gửi `SELECT`.
2. Oracle parse SQL, kiểm tra quyền, chạy execution plan.
3. Ghi redo ra online redo log.
4. Ghi dirty buffers ra datafiles.
5. Cập nhật thông tin checkpoint.
6. Quản lý một số công việc phục hồi sau instance failure.

**Đáp án:** (1) user process; (2) server process; (3) LGWR; (4) DBWn; (5) CKPT; (6) cơ chế instance recovery, trong đó SMON và các tiến trình phục hồi thích hợp đóng vai trò.

### Tình huống 4: Shared server

Một hệ thống có 4.000 sessions, phần lớn không hoạt động, và sử dụng shared server. Có thể suy ra đang có 4.000 shared server OS processes không?

**Gợi ý:** Không. Các sessions chia sẻ một nhóm shared server processes, với dispatcher và queue phục vụ phân phối yêu cầu. Kích thước thực tế của nhóm phụ thuộc cấu hình và mức tải.

### Tình huống 5: Quan sát dữ liệu

Trong `V$SESSION`, một session có `STATUS='ACTIVE'`, nhưng CPU của process không tăng. Điều đó có chắc bất thường không?

**Gợi ý:** Không. Session có thể đang chờ I/O, lock, network hoặc sự kiện khác. Cần xem sự kiện chờ và ngữ cảnh workload để đánh giá.

## 14. Tài liệu Oracle để tìm hiểu thêm

- [Oracle Database Concepts](https://docs.oracle.com/en/database/oracle/oracle-database/19/cncpt/): kiến trúc database/instance, memory, process và background processes.
- [Oracle Database Reference](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/): định nghĩa `V$SESSION`, `V$PROCESS`, `V$BGPROCESS`, `V$RESOURCE_LIMIT` và các tham số liên quan.
- [Oracle Database Administrator's Guide](https://docs.oracle.com/en/database/oracle/oracle-database/19/admin/): quản trị instance, cấu hình server, khả năng phục hồi và vận hành.
- [Oracle Database Net Services Administrator's Guide](https://docs.oracle.com/en/database/oracle/oracle-database/19/netag/): listener, service, dedicated/shared server connections.
- [Oracle Database Performance Tuning Guide](https://docs.oracle.com/en/database/oracle/oracle-database/19/tgsql/): SQL execution và các khía cạnh hiệu năng liên quan.
- [Oracle Database JDBC Developer's Guide](https://docs.oracle.com/en/database/oracle/oracle-database/19/jjdbc/): Java client, drivers, connections và các cơ chế tương tác với Oracle.

Khi phân tích một yêu cầu SQL, hãy lần theo: **user process phát yêu cầu → server process thực thi với PGA/SGA → background processes duy trì redo, datafile, checkpoint và instance → kết quả trả về client**. Phân biệt rõ luồng xử lý này sẽ giúp đọc trạng thái hệ thống, giải thích giao dịch và tìm đúng lớp nguyên nhân khi phát sinh sự cố.
