# JDBC store và tiêu chí lựa chọn so với file journal

> **Chương:** Lưu trữ Artemis  
> **Module:** `INTEGRATION_MESSAGING_MESSAGE_BROKER_ACTIVEMQ` — thực hành ActiveMQ Artemis trong hệ thống Java/JMS giao tiếp bất đồng bộ.  
> **Trọng tâm:** Cơ chế lưu message bền vững của Artemis bằng **file journal** hoặc **JDBC store**, cấu hình `broker.xml` và tiêu chí chọn giải pháp trên cơ sở yêu cầu hiệu năng, khôi phục, vận hành và HA.

## 1. Tình huống cần quyết định

Một dịch vụ đơn hàng nhận message `PaymentConfirmed` và đưa lệnh `PrepareShipment` vào queue. Hệ thống cần bảo đảm:

- Message đã được producer gửi với chế độ **persistent** và transaction gửi đã commit không bị mất một cách dễ dàng khi broker restart.
- Consumer chỉ ACK/commit sau khi nghiệp vụ hoàn tất; nếu consumer mất kết nối trước ACK, message vẫn có cơ hội được giao lại.
- Khi broker gặp sự cố, nhóm vận hành biết **dữ liệu bền vững đang nằm ở đâu**, sao lưu như thế nào và khôi phục bằng quy trình nào.
- Độ trễ `send/commit` vẫn nằm trong SLO dưới tải thực tế, ngay cả khi hệ thống có paging hoặc message lớn.

Artemis hỗ trợ hai hướng persistence chính:

1. **File journal**: lưu bindings, message và các cấu trúc persistence trên hệ thống tệp, với message journal tối ưu cho kiểu ghi tuần tự; đây là hướng mặc định/thông dụng trên broker Artemis.
2. **JDBC store**: dùng một cơ sở dữ liệu quan hệ thông qua JDBC để ghi các thành phần persistence được hỗ trợ, thay cho cấu hình file store tương ứng.

Bài không đề xuất mặc định “database đáng tin cậy hơn file” hoặc “file luôn nhanh hơn database”. **Cả hai chỉ đáng tin cậy khi cấu hình durability, hạ tầng, backup, HA và kiểm thử failure mode phù hợp.**

### Bản đồ đường đi của một message

~~~mermaid
flowchart TD
    P[Java JMS Producer] -->|PERSISTENT + send + commit| B[Artemis broker]
    B --> R[Route vào queue bền vững]
    R --> S{Store đã cấu hình}
    S -->|file store| J[Bindings + message journal / file areas]
    S -->|database-store| DB[(JDBC relational database)]
    J --> C[Consumer]
    DB --> C
    C -->|JMS commit / ACK| A[Cập nhật trạng thái đã xử lý]
~~~

**Điểm quan trọng:** Store chỉ quyết định **nơi và cách broker lưu dữ liệu**, không biến các thao tác **DB nghiệp vụ**, **HTTP side effect** và **JMS transaction** thành một giao dịch nguyên tử duy nhất. Persistent message cũng không đồng nghĩa consumer sẽ không bao giờ nhận lại: redelivery là một phần của thiết kế đáng tin cậy.

## 2. File journal đang lưu cái gì?

Trong một Artemis broker dùng file store, các dữ liệu persistence quan trọng thường được đặt ở các vùng riêng:

| Nhóm dữ liệu | Cấu hình thư mục phổ biến | Chức năng |
|---|---|---|
| **Bindings** | `bindings-directory` (thường `data/bindings`) | Thông tin định nghĩa queue/address binding và metadata cần khôi phục |
| **Message journal** | `journal-directory` (thường `data/journal`) | Bản ghi thêm/xóa/cập nhật message và các transaction liên quan |
| **Large messages** | `large-messages-directory` (thường `data/large-messages`) | Nội dung message lớn được xử lý theo đường lưu riêng |
| **Paging** | `paging-directory` (thường `data/paging`) | Dữ liệu message chuyển sang paging khi chính sách address-full kích hoạt |

Không nên tưởng tượng mọi payload và mọi trạng thái đều nằm trong **một** file journal duy nhất. Việc sao lưu chỉ thư mục `data/journal` trong khi quên bindings, large messages hoặc paging có thể tạo một bản phục hồi không đầy đủ. Tên thư mục chính xác phụ thuộc cấu hình của instance.

### 2.1. Vì sao journal thường có lợi cho broker?

Message broker thường ghi rất nhiều message nhỏ, ACK/commit và cập nhật trạng thái liên tục. File journal được thiết kế theo mô hình **append/update records**, giúp hạn chế kiểu ghi ngẫu nhiên từng row như một workload RDBMS thông thường. Artemis có các loại journal I/O, điển hình:

- **NIO**: thực hiện I/O file qua Java NIO, thích hợp khi không có native async I/O phù hợp.
- **ASYNCIO**: dùng native asynchronous I/O trên môi trường được hỗ trợ, đặc biệt khi cấu hình Linux/thiết bị lưu trữ đáp ứng yêu cầu.
- **MAPPED**: một tùy chọn journal I/O theo phiên bản và nền tảng, có cơ chế memory-mapped file.

Không phải môi trường nào cũng có thể sử dụng `ASYNCIO`. Broker có thể có cách xử lý/fallback tùy bản phát hành; phải kiểm tra **startup log** xem I/O implementation nào được dùng thật, không chỉ dựa trên giá trị yêu cầu trong XML.

Một đoạn cấu hình file journal để đối chiếu, đặt **trong thẻ `<core>` hiện có của `broker.xml`**, là:

~~~xml
<!-- Ví dụ hướng file journal; chỉ dùng trên instance file-store. -->
<journal-type>NIO</journal-type>
<bindings-directory>data/bindings</bindings-directory>
<journal-directory>data/journal</journal-directory>
<large-messages-directory>data/large-messages</large-messages-directory>
<paging-directory>data/paging</paging-directory>
<journal-sync-transactional>true</journal-sync-transactional>
<journal-sync-non-transactional>true</journal-sync-non-transactional>
~~~

Các thẻ trên là **mảnh cấu hình**, không phải file hoàn chỉnh. Thư mục thực tế được tính theo broker instance/configuration; xác nhận đường dẫn dữ liệu đã được resolve trong runtime. Khi dùng file journal, đặt dữ liệu trên volume bền vững, có đủ IOPS, độ trễ flush thấp và chính sách backup/restore phù hợp.

### 2.2. Durability là chuỗi điều kiện, không chỉ là flag persistent

Để một command quan trọng được phục hồi qua broker restart, tối thiểu cần xem đồng thời:

1. Producer gửi với `DeliveryMode.PERSISTENT`.
2. Broker có `persistence-enabled=true` và store cấu hình hợp lệ.
3. Queue/subscription cần tồn tại bền vững theo mô hình routing; ví dụ một durable anycast queue hoặc durable topic subscription đã được tạo.
4. Producer nhận được kết quả transaction `commit`/acknowledgment theo đúng ranh giới tin cậy của hệ thống.
5. Storage và phương thức đồng bộ dữ liệu đáp ứng yêu cầu về crash durability; nguồn điện, hệ thống tệp, volume, database WAL và replication không được coi là “luôn an toàn” nếu không kiểm thử.

Message có thể hết TTL, bị chuyển DLQ/expiry, bị consumer ACK, bị purge hoặc mất do thảm họa hạ tầng nằm ngoài khả năng cấu hình. **Persistent không có nghĩa giữ vô hạn** và **queue durable không làm non-persistent message trở nên persistent**.

## 3. JDBC store hoạt động ra sao?

Thay vì lưu phần persistence chính bằng các thư mục file journal, Artemis có thể chọn **database store**. Broker sử dụng JDBC driver để ghi dữ liệu vào các bảng trong RDBMS được cấu hình. Cơ chế này không biến message thành “một hàng JSON trong bảng nghiệp vụ” do ứng dụng tự quản lý; **schema của các bảng là cấu trúc nội bộ của Artemis**.

### 3.1. Các bảng liên quan

Với cấu hình database store, tài liệu Artemis cho phép đặt tên các bảng dùng cho nhiều phần persistence:

| Tham số `database-store` | Vai trò |
|---|---|
| `bindings-table-name` | Lưu binding metadata cần cho broker |
| `message-table-name` | Lưu nội dung/trạng thái journal message |
| `large-message-table-name` | Lưu dữ liệu large messages theo JDBC implementation |
| `page-store-table-name` | Dữ liệu phục vụ paging theo cơ chế JDBC store |
| `node-manager-store-table-name` | Dữ liệu node-manager/lock dùng trong một số chế độ HA/shared-store |

Một số phiên bản có cách triển khai, giới hạn kiểu SQL và quy tắc khởi tạo bảng khác nhau. **Không coi tên bảng hoặc schema là API công khai để trực tiếp INSERT/UPDATE/DELETE message.** Dùng JMS, broker management hoặc công cụ chính thức của Artemis để thao tác queue; dùng SQL chủ yếu để quan sát sức khỏe/tài nguyên DB theo runbook đã kiểm chứng.

### 3.2. Điều gì thay đổi khi chuyển từ file sang JDBC?

~~~mermaid
flowchart LR
    subgraph FILE[File store]
      F1[Broker Artemis] --> F2[(Journal / Bindings / Paging / Large message files)]
    end
    subgraph JDBC[JDBC store]
      J1[Broker Artemis] --> J2[JDBC driver]
      J2 --> J3[(Database tables + WAL/redo log)]
    end
~~~

Bản thân RDBMS cũng cần cơ chế durability vật lý: **WAL/redo log, fsync, checkpoint, backup, replication hoặc storage subsystem**. Vì vậy chọn JDBC store không “loại bỏ journal” theo nghĩa hạ tầng; nó **chuyển trách nhiệm ghi bền vững** sang transaction log và storage engine của database.

Hệ quả vận hành:

- Mỗi thao tác persistence của broker có thêm **driver, SQL transaction, kết nối và đôi khi network round-trip**.
- Database có thể chia sẻ nền tảng giám sát/backup do tổ chức đã có, nhưng broker phụ thuộc vào **khả năng sẵn sàng và độ trễ của database**.
- Một lần database mất kết nối, hết connection, deadlock hoặc storage đầy có thể tác động trực tiếp đến send/commit/ACK của broker.
- Nếu bật replication của database, cần biết replication **synchronous** hay **asynchronous** để đánh giá mất dữ liệu khi failover; “DB có replica” không đồng nghĩa RPO bằng 0.

## 4. Cấu hình database-store trên Artemis

### 4.1. Điều kiện cho bài lab PostgreSQL

Ví dụ sau dùng PostgreSQL có sẵn tại `127.0.0.1:5432`. Đây là **môi trường thử nghiệm cục bộ**, không phải mẫu chứa secret cho production.

Điều kiện:

- Phiên bản Artemis bạn triển khai **hỗ trợ JDBC store và dialect PostgreSQL/JDBC driver tương ứng**. Kiểm tra tài liệu của **đúng phiên bản** trước khi quyết định production.
- Broker có thể nạp class `org.postgresql.Driver` từ **classpath do startup script nạp**. Chỉ thêm PostgreSQL JDBC jar vào thư mục `lib` thích hợp của distribution/instance theo tài liệu cài đặt; không giả định nó đã có sẵn.
- Database và tài khoản có quyền tạo/ghi/đọc các bảng Artemis cần thiết.
- Broker instance dùng JDBC **không** đồng thời trỏ cùng bộ bảng đến một broker độc lập khác; ngoại lệ phải dùng cơ chế HA/shared-store được Artemis hỗ trợ và cấu hình đúng.

Ví dụ tạo DB bằng `psql` với tài khoản quản trị ở máy lab:

~~~sql
-- Chỉ thực hành trên PostgreSQL lab, không dùng mật khẩu thật.
CREATE ROLE artemis_lab LOGIN PASSWORD 'dev-only-password';
CREATE DATABASE artemis_lab OWNER artemis_lab;
~~~

Các lệnh này thường cần chạy riêng ở kết nối quản trị, vì PostgreSQL không cho phép `CREATE DATABASE` bên trong một transaction block. Nếu role/database đã tồn tại, không tạo trùng. Cần đặt schema, quyền truy cập và TLS của DB phù hợp với tổ chức khi dùng production.

### 4.2. Mảnh cấu hình broker.xml

Trong `ARTEMIS_INSTANCE/etc/broker.xml`, ở dưới `<core>` hiện có, cấu hình **một** store:

~~~xml
<!-- Ví dụ PostgreSQL cục bộ; KHÔNG dùng secret literal này ở production. -->
<store>
    <database-store>
        <jdbc-connection-url>jdbc:postgresql://127.0.0.1:5432/artemis_lab?user=artemis_lab&amp;password=dev-only-password</jdbc-connection-url>
        <jdbc-driver-class-name>org.postgresql.Driver</jdbc-driver-class-name>

        <bindings-table-name>ART_BINDINGS</bindings-table-name>
        <message-table-name>ART_MESSAGES</message-table-name>
        <large-message-table-name>ART_LARGE_MESSAGES</large-message-table-name>
        <page-store-table-name>ART_PAGE_STORE</page-store-table-name>
        <node-manager-store-table-name>ART_NODE_MANAGER</node-manager-store-table-name>
    </database-store>
</store>
~~~

**Giải thích chính xác vị trí và giới hạn:**

- `<store><database-store>...</database-store></store>` thuộc cấu hình **Core broker**, không đặt trong `<addresses>`, `<address-settings>` hoặc `<acceptors>`.
- `jdbc-connection-url` là URL JDBC mà **broker sử dụng để truy cập DB**; không phải URL mà Java JMS producer/consumer dùng để kết nối Artemis.
- `jdbc-driver-class-name` phải hiện diện trong classpath của broker và khớp JAR driver.
- Các tên bảng phải **được xác nhận phù hợp với giới hạn identifier của database** và không đụng các bảng của broker khác.
- Ký tự `&` trong URL XML phải escape thành `&amp;`. Nếu sao chép `&password=...` trực tiếp trong XML attribute/element không hợp lệ có thể làm broker không parse được cấu hình.
- Chuỗi password literal chỉ nhằm làm rõ việc truyền URL **trong lab**. Production nên cấp bí mật bằng secret manager, cấu hình externalized/property expansion hoặc datasource hỗ trợ của đúng phiên bản, cùng TLS và quyền DB tối thiểu.
- Không dùng đồng thời hai phần tử `<store>`. File-store mặc định và database-store là **hai lựa chọn**, không phải hai backend tự động replicate cho nhau.

Cấu hình trên là một mẫu thực hành có phụ thuộc môi trường: bạn cần chuẩn bị PostgreSQL, driver, tài khoản và quyền. Khi Artemis khởi động, **xem log khởi tạo JDBC store, lỗi connect/schema và số bảng được tạo**; không chỉ suy từ việc broker process vẫn chạy.

### 4.3. Các tham số JDBC nâng cao cần hiểu trước khi chỉnh

Artemis còn có các thiết lập JDBC store cho **đồng bộ journal**, **thời gian giữ/renew database lock** và một số giới hạn batch/page tùy phiên bản. Ví dụ các tên thường gặp trong tài liệu:

- `jdbc-journal-sync-period`: khoảng đồng bộ theo cơ chế JDBC journal của broker.
- `jdbc-lock-renew-period`: chu kỳ gia hạn lock/lease khi cơ chế node manager tương ứng sử dụng.
- `jdbc-lock-expiration`: ngưỡng hết hạn của lock trong cơ chế HA dùng DB.
- `jdbc-max-page-size-bytes` và các giới hạn theo dialect/driver nếu phiên bản hỗ trợ.

**Không đặt các tham số này tùy tiện chỉ để tăng tốc.** Với journal sync, phải hiểu quan hệ giữa send/commit response và crash-consistency; với lock period/expiration, phải tính tới stop-the-world GC, network latency và database stall. Một khóa hết hạn sai có thể khiến hai broker tin rằng mình có quyền active trong tình huống lỗi nghiêm trọng.

Ví dụ **minh họa vị trí**, không nên paste nếu chưa đối chiếu tài liệu của đúng bản Artemis:

~~~xml
<store>
  <database-store>
    <!-- ... jdbc-connection-url, driver, tên bảng ... -->
    <jdbc-journal-sync-period>5</jdbc-journal-sync-period>
  </database-store>
</store>
~~~

Giá trị cấu hình và đơn vị thời gian phải được xác minh qua tài liệu phiên bản. Đặc biệt, không tuyên bố rằng đặt giá trị cực nhỏ tự động cho độ bền tuyệt đối; vẫn phụ thuộc database commit, WAL/fsync và hạ tầng lưu trữ.

### 4.4. Địa chỉ và queue để kiểm chứng

Trong cùng `broker.xml`, bên trong section `<addresses>` hiện có, thêm một anycast queue chỉ dành cho lab:

~~~xml
<address name="lab.storage.orders">
    <anycast>
        <queue name="lab.storage.orders">
            <durable>true</durable>
        </queue>
    </anycast>
</address>
~~~

Đây là mảnh cấu hình riêng với phần store. `<durable>true</durable>` tạo queue bền vững, còn cách lưu message do **store cấp broker** quyết định. Đừng hiểu `durable queue` là một chỉ thị chọn riêng file journal hay JDBC. Cả producer và consumer Java vẫn sử dụng cùng JMS queue `lab.storage.orders`, bất kể backend là file hay JDBC.

## 5. So sánh JDBC store với file journal theo tiêu chí quyết định

| Tiêu chí | File journal | JDBC store | Kết luận sử dụng |
|---|---|---|---|
| **Đường ghi** | Broker ghi journal và các file persistence trên volume | Broker đi qua JDBC/RDBMS, database tự ghi WAL/storage | File thường có đường I/O ít tầng hơn; vẫn cần benchmark thực tế |
| **Độ trễ commit** | Phụ thuộc I/O journal, sync, volume/fsync | Phụ thuộc driver, network, DB transaction/WAL/lock | Đo **p95/p99 commit**, không chỉ throughput trung bình |
| **Throughput** | Thường là lựa chọn tối ưu cho workload broker nhiều message nhỏ | Có thể thấp hơn vì SQL/DB overhead hoặc contention | Với lưu lượng cao, bắt đầu bằng file journal rồi thử JDBC dưới tải tương đương |
| **Độ bền** | Volume và cấu hình sync/journal quyết định | RDBMS transaction, WAL/fsync, HA/replication quyết định | Không có lựa chọn nào mặc định RPO=0 dưới mọi lỗi |
| **HA** | Có thể dùng các chính sách HA/replication/shared-store phù hợp | Có thể dùng DB shared-store/node manager nếu phiên bản/mode hỗ trợ | JDBC không tự biến hai broker thành HA; cần chính sách, lock, fencing |
| **Backup/restore** | Phải nhất quán nhiều thư mục journal/bindings/paging/large messages | Dùng snapshot/backup nhất quán của **toàn bộ DB bảng broker** | JDBC hữu ích khi tổ chức đã vận hành backup/PITR RDBMS tốt |
| **Khả năng quan sát** | Broker metrics, journal I/O, disk, queue metrics | Broker metrics **cộng** DB query/locks/WAL/connections | JDBC có nhiều điểm giám sát hơn, không phải lúc nào đơn giản hơn |
| **Chi phí vận hành** | Volume bền vững, IOPS, snapshot và restore broker | Cần DB cluster, driver, schema, tài khoản, TLS, connection limits | Chọn theo năng lực đội ngũ và chi phí tổng thể |
| **Phụ thuộc sự cố** | Disk/volume lỗi có thể làm broker chậm hoặc dừng | DB/network lỗi ảnh hưởng trực tiếp việc broker persist | RDBMS shared có thể tạo fault domain rộng hơn |
| **Large message/paging** | Thư mục file chuyên biệt | Bảng/cơ chế JDBC theo phiên bản | Phải benchmark payload lớn và paging; không chỉ test message nhỏ |
| **Triển khai tách biệt** | Tách volume theo instance/HA policy | Tách database hoặc bộ bảng theo instance/HA policy | Không cho hai broker độc lập ghi chung một store |
| **Khả năng chuyển đổi** | Không tự “đọc” bảng JDBC | Không tự “import” journal file cũ | Muốn migration cần quy trình có kiểm soát, không chỉ đổi XML |

### 5.1. Quy tắc lựa chọn thực dụng

**Ưu tiên file journal khi:**

- Bạn cần throughput cao và commit latency thấp cho nhiều message nhỏ.
- Có disk/volume bền vững, có thể theo dõi fsync và provisioning IOPS.
- Có thể triển khai HA/replication phù hợp với Artemis mà không yêu cầu dùng chung DB.
- Đội vận hành đã có phương án backup/restore volume nhất quán và kiểm thử phục hồi.
- Không có lý do quản trị dữ liệu bắt buộc phải lưu dữ liệu broker vào RDBMS.

**Đánh giá JDBC store khi:**

- Hạ tầng yêu cầu quản trị dữ liệu qua RDBMS có backup, audit, PITR và vận hành trưởng thành.
- Quy mô throughput/latency phù hợp với ngân sách tài nguyên của DB.
- Cơ chế HA/shared-store mà bạn đang chọn **được Artemis hỗ trợ** với JDBC driver/DB/version hiện hành.
- Bạn sẵn sàng chịu phụ thuộc DB/network, có timeout, monitoring và runbook xử lý lỗi DB.
- Việc tập trung vận hành database có lợi hơn chi phí overhead của SQL và JDBC.

**Không nên chọn JDBC chỉ vì muốn dùng SQL xem hoặc sửa message.** Artemis không thiết kế bảng journal làm một giao diện truy vấn sự kiện nghiệp vụ. Nếu doanh nghiệp cần phân tích lịch sử, audit hoặc replay theo thời gian, hãy phát/lưu sự kiện vào một hệ thống event store/analytics được thiết kế cho mục tiêu đó, thay vì truy vấn trực tiếp bảng nội bộ broker.

## 6. HA: một database dùng chung có tự tạo failover an toàn không?

**Không.** Có một PostgreSQL cluster sẵn sàng cao chỉ giải quyết phần **database availability**. Broker còn cần:

1. Một chính sách HA hợp lệ của Artemis cho phiên bản đang chạy, ví dụ cơ chế shared-store hoặc replication tương ứng.
2. Quy tắc **ai được quyền active** và cách standby tiếp quản, kèm giới hạn quyền ghi store.
3. Cơ chế **node manager/lease/lock** nếu dùng shared store, với thông số thời hạn và giám sát phù hợp.
4. Kết nối client có thể failover/reconnect đúng cách, timeout được xác định.
5. Kiểm tra split-brain/fencing khi broker mất mạng tới DB nhưng còn giao tiếp với các hệ thống khác.

~~~mermaid
flowchart TB
    C[Producer / Consumer clients] --> A[Broker active]
    B[Broker standby] -.->|HA policy / lease| A
    A --> DB[(JDBC shared store)]
    B -.->|Chỉ tiếp quản khi hợp lệ| DB
    DB --> W[DB WAL + storage + replication]
~~~

**Không dùng cùng JDBC URL và cùng bộ bảng cho hai live broker độc lập** rồi mong hệ thống tự chia tải an toàn. Nếu cả hai cùng ghi store mà không có HA coordination phù hợp, có thể gây lỗi nghiêm trọng về lock và trạng thái message. Nếu cần phân tải ngang, dùng cơ chế clustering/routing được hỗ trợ, thường với **store độc lập cho từng live broker**; đó là bài toán khác với một shared-store HA pair.

### 6.1. RPO và RTO phải đo riêng

- **RPO (Recovery Point Objective):** mức mất dữ liệu tối đa được phép. DB async replica có thể mất những transaction chưa kịp replicate khi primary DB lỗi; file journal cũng phụ thuộc flush/storage/HA.
- **RTO (Recovery Time Objective):** thời gian broker sẵn sàng trở lại. Bao gồm failover DB, phát hiện broker lỗi, lấy lock/lease, đọc lại store, dựng queue và reconnect client.

RDBMS có backup mỗi 5 phút không đồng nghĩa broker có RPO 0. Hệ thống dùng DB synchronous replication cũng cần đo latency và xem đánh đổi availability/performance. Chỉ đánh giá “JDBC giúp HA hơn” nếu **bài thử failover end-to-end** chứng minh điều đó.

## 7. Lab kiểm chứng lưu message qua restart

Mục tiêu là dùng **cùng chương trình JMS** với hai kiểu store để tách bạch semantics của API và backend persistence. Chạy trên **hai instance lab riêng** hoặc hai lượt chạy có dữ liệu được chuẩn bị lại rõ ràng. **Không dùng chung thư mục store, và không thay JDBC vào một instance đang có journal data cần giữ.**

### 7.1. Chuẩn bị Java

Ví dụ dùng Java 17, `jakarta.jms.*` và Artemis Jakarta client tương thích với broker. POM rút gọn:

~~~xml
<properties>
    <maven.compiler.release>17</maven.compiler.release>
    <artemis.version>2.33.0</artemis.version>
</properties>

<dependencies>
    <dependency>
        <groupId>org.apache.activemq</groupId>
        <artifactId>artemis-jakarta-client</artifactId>
        <version>${artemis.version}</version>
    </dependency>
</dependencies>
~~~

Phiên bản trên chỉ là ví dụ để pin dependency; kiểm tra hỗ trợ của broker, JDK và client trong môi trường bạn sử dụng. Biến môi trường `ARTEMIS_USER` và `ARTEMIS_PASSWORD` là tài khoản **JMS broker**, độc lập với tài khoản **PostgreSQL JDBC store** của broker.

### 7.2. Chương trình gửi và nhận, có transaction

Mã sau có ba mode:

- `send <runId>`: gửi 5 message persistent, chứa property `runId` và `seq`, rồi commit một lần.
- `receive <runId>`: nhận và xác nhận 5 message trong session transacted; in `eventId` và `JMSXDeliveryCount`.
- `rollback-one <runId>`: nhận một message nhưng rollback, để thấy nó **vẫn còn** cho lần nhận khác. Mode này **không phải phép thử crash durability**, chỉ xác minh semantics của ACK.

~~~java
import jakarta.jms.DeliveryMode;
import jakarta.jms.JMSConsumer;
import jakarta.jms.JMSContext;
import jakarta.jms.Message;
import jakarta.jms.Queue;
import jakarta.jms.TextMessage;
import org.apache.activemq.artemis.jms.client.ActiveMQConnectionFactory;

public final class StoragePersistenceLab {
    private static final String URL = "tcp://127.0.0.1:61616";
    private static final String QUEUE_NAME = "lab.storage.orders";

    public static void main(String[] args) throws Exception {
        if (args.length != 2 ||
                !(args[0].equals("send")
                    || args[0].equals("receive")
                    || args[0].equals("rollback-one"))) {
            System.out.println(
                "StoragePersistenceLab send|receive|rollback-one <runId>");
            return;
        }

        String runId = args[1];
        if (!runId.matches("[A-Za-z0-9_-]{1,60}")) {
            throw new IllegalArgumentException(
                "runId chỉ gồm chữ, số, _ và -");
        }

        String user = env("ARTEMIS_USER");
        String password = env("ARTEMIS_PASSWORD");
        ActiveMQConnectionFactory factory =
            new ActiveMQConnectionFactory(URL);

        try (JMSContext ctx = factory.createContext(
                user, password, JMSContext.SESSION_TRANSACTED)) {

            Queue queue = ctx.createQueue(QUEUE_NAME);
            switch (args[0]) {
                case "send" -> send(ctx, queue, runId);
                case "receive" -> receive(ctx, queue, runId, false);
                case "rollback-one" -> receive(ctx, queue, runId, true);
                default -> throw new AssertionError();
            }
        }
    }

    private static void send(
            JMSContext ctx, Queue queue, String runId) throws Exception {
        var producer = ctx.createProducer()
            .setDeliveryMode(DeliveryMode.PERSISTENT);

        try {
            for (int seq = 1; seq <= 5; seq++) {
                String eventId = runId + ":" + seq;
                TextMessage message = ctx.createTextMessage(
                    "{\"eventId\":\"" + eventId
                    + "\",\"seq\":" + seq + "}");
                message.setStringProperty("runId", runId);
                message.setStringProperty("eventId", eventId);
                message.setIntProperty("seq", seq);
                producer.send(queue, message);
                System.out.println("SENT " + eventId);
            }
            ctx.commit();
            System.out.println("SEND_COMMITTED " + runId);
        } catch (Exception failure) {
            ctx.rollback();
            throw failure;
        }
    }

    private static void receive(
            JMSContext ctx, Queue queue, String runId, boolean rollbackOne)
            throws Exception {

        // Chỉ lấy đúng lô thử nghiệm để tránh tiêu thụ nhầm dữ liệu cũ.
        String selector = "runId = '" + runId + "'";
        JMSConsumer consumer = ctx.createConsumer(queue, selector);

        try {
            int count = 0;
            int limit = rollbackOne ? 1 : 5;

            while (count < limit) {
                Message message = consumer.receive(5000);
                if (message == null) {
                    System.out.println(
                        "TIMEOUT sau " + count + " messages");
                    break;
                }

                if (!(message instanceof TextMessage text)) {
                    ctx.rollback();
                    throw new IllegalArgumentException(
                        "Lab chỉ đọc TextMessage");
                }

                int deliveryCount = message.propertyExists(
                    "JMSXDeliveryCount")
                    ? message.getIntProperty("JMSXDeliveryCount") : -1;

                System.out.printf(
                    "RECEIVED id=%s seq=%d deliveryCount=%d body=%s%n",
                    text.getStringProperty("eventId"),
                    text.getIntProperty("seq"),
                    deliveryCount,
                    text.getText());

                if (rollbackOne) {
                    ctx.rollback();
                    System.out.println("ROLLED_BACK: message chưa được ACK");
                    return;
                }

                // Production: thực hiện side effect idempotent trước commit.
                ctx.commit();
                count++;
            }
            System.out.println("RECEIVE_COMMITTED count=" + count);
        } finally {
            consumer.close();
        }
    }

    private static String env(String key) {
        String value = System.getenv(key);
        if (value == null || value.isBlank()) {
            throw new IllegalStateException("Thiếu biến " + key);
        }
        return value;
    }
}
~~~

Code chủ đích dùng một queue **anycast** đã cấu hình và không có consumer cạnh tranh. `runId` cần thay cho mỗi vòng lab mới, ví dụ `FILE01` và `JDBC01`; đừng gửi lặp cùng `runId` rồi nhầm thành cùng năm message gốc. Mỗi mode `receive` sẽ ACK/commit thông điệp được chọn; vì vậy muốn kiểm chứng lưu qua restart, **đừng chạy receive trước khi restart**.

### 7.3. Quy trình cho file journal

1. Tạo hoặc dùng **instance lab file-store** độc lập, với dữ liệu mới và queue `lab.storage.orders`. Xác minh `persistence-enabled=true`.
2. Khởi động broker, kiểm tra log đang dùng journal I/O nào và xác nhận queue rỗng.
3. Chạy `StoragePersistenceLab send FILE01`, đợi log `SEND_COMMITTED FILE01`.
4. Kiểm tra queue count khoảng 5; không có consumer đang xử lý.
5. **Dừng broker sạch** bằng script hoặc cơ chế quản trị của instance, giữ nguyên toàn bộ thư mục `data`; khởi động lại.
6. Chạy `StoragePersistenceLab receive FILE01` và kỳ vọng năm event được đọc, sau commit queue count về 0.

Kết quả chứng minh **đường khôi phục sau clean restart** cho một lô message persistent. Nó **chưa đủ** chứng minh RPO khi mất điện đột ngột, disk không fsync, kernel crash hoặc sự cố nhiều node; các tình huống đó cần failure injection riêng và bảo vệ dữ liệu lab.

### 7.4. Quy trình cho JDBC store

1. Tạo **instance lab khác** với cùng queue logic nhưng cấu hình `database-store` ở mục 4, dùng DB/bộ bảng riêng.
2. Khởi động PostgreSQL trước, xác minh broker load được JDBC driver và kết nối DB thành công.
3. Khởi động Artemis instance JDBC; kiểm tra bảng cấu hình được tạo/nạp đúng và queue `lab.storage.orders` xuất hiện trong console.
4. Chạy `StoragePersistenceLab send JDBC01`, đợi `SEND_COMMITTED JDBC01`; kiểm tra queue count = 5 nếu không có consumer khác.
5. Dừng **chỉ tiến trình Artemis** theo cách sạch, **không dừng PostgreSQL và không xóa bảng**; khởi động broker lại.
6. Chạy `StoragePersistenceLab receive JDBC01`. Năm event cần đọc được và ACK/commit; queue giảm về 0.

**Cảnh báo môi trường:** URL Java trong code là `tcp://127.0.0.1:61616`. Khi dùng hai instance, chạy lần lượt từng instance trên cổng đó **hoặc** đổi URL phù hợp với cổng của instance đang test; không khởi động hai broker cùng bind một cổng.

### 7.5. Bảng kiểm chứng

| Tiêu chí | File journal lab | JDBC store lab |
|---|---|---|
| Lệnh send commit thành công | `SEND_COMMITTED FILE01` | `SEND_COMMITTED JDBC01` |
| Có 5 message trước restart | Kiểm tra broker queue count | Kiểm tra broker queue count |
| Dữ liệu vẫn còn sau clean restart | Kỳ vọng có | Kỳ vọng có |
| Nhận và commit 5 message | Kỳ vọng có | Kỳ vọng có |
| Thử `rollback-one` (ở lô mới) | Message được broker giao lại theo policy | Cùng semantics JMS |
| Dấu hiệu persistence hạ tầng | Journal/bindings/paging/large message files | Bảng broker trong DB + transaction/WAL |
| Khi backend lưu trữ unavailable | Volume/journal I/O lỗi | DB/connection/WAL lỗi |
| Bằng chứng production durability | Cần crash/restore/HA tests | Cần crash/DB failover/restore/HA tests |

**Không dùng nội dung trực tiếp của các file journal hoặc SQL rows làm tiêu chí xác minh nghiệp vụ.** Queue count qua broker management và message được client đọc đúng `eventId` sau restart là bằng chứng ở lớp ứng dụng; backup/restore test là bằng chứng ở lớp vận hành.

## 8. Benchmark so sánh có ý nghĩa

Đừng đo một lần `send 5` rồi kết luận store nào nhanh. Một phép đo có thể tái lập cần:

1. **Cùng phiên bản Artemis**, JDK, client, JMS message type, queue setup và security cho hai cấu hình.
2. **Cùng hardware quota** có tính tới nguồn lực RDBMS: CPU, RAM, disk, network, IOPS, WAL volume, connection limits.
3. Nhiều kịch bản payload: ví dụ **1 KiB**, **32 KiB**, **1 MiB** (và large-message threshold thực tế), cả single queue và nhiều queue.
4. Producer persistent, xác định rõ ACK/commit mode: mỗi message commit hay batch 100; không so một bên transacted với một bên fire-and-forget.
5. Đo **p50/p95/p99 latency** cho send/commit, throughput ổn định, queue end-to-end latency, backlog growth, CPU, memory, disk/WAL I/O và lỗi.
6. Test **DB/network interruption** với JDBC, **storage stall/fsync latency** với file, và cùng thời gian thử dưới tải.
7. Chạy đủ lâu qua một chu kỳ checkpoint, journal rotation/compaction và nếu cần cả paging. Ghi warm-up và loại kết quả chưa ổn định.

### Ví dụ bảng số liệu minh họa *chỉ để học cách đọc*

| Chỉ số (giả định, không phải benchmark thực) | File journal | JDBC store |
|---|---:|---:|
| P95 commit latency | 4 ms | 12 ms |
| P99 commit latency | 15 ms | 75 ms |
| Throughput ổn định | 8.000 msg/s | 4.500 msg/s |
| RTO sau restart | 8 s | 12 s |

Các con số trên **hoàn toàn giả định**, không được trích dẫn làm tiêu chí chọn product. Một PostgreSQL cục bộ có NVMe hoặc storage mạnh có thể cho kết quả khác DB từ xa có synchronous replicas. Quan trọng là **SLO thực tế** và chi phí vận hành của đội ngũ, không phải một benchmark không có thông tin môi trường.

### 8.1. Các biến gây sai lệch phổ biến

- File journal trên local NVMe, JDBC dùng DB ở mạng khác vùng → so sánh không cân bằng.
- JDBC dùng DB chung với workload OLTP nên đo cả lock/SQL contention từ ứng dụng khác.
- Một bên bật fsync/synchronous commit, bên kia giảm durability để tăng benchmark.
- Test 1 KiB message nhưng production có message lớn, paging và heavy consumer ACK.
- Chỉ đo `producer.send()` mà không tính thời điểm transaction commit.
- Bật auto-create queue khác nhau, khác số consumer, khác prefetch/consumer window, khác TTL/DLQ.
- Chạy benchmark lúc backup, checkpoint hoặc DB failover nhưng không ghi nhận.

**Kết luận benchmark:** Khi xem hiệu năng, phải đo đúng điểm đảm bảo mà nghiệp vụ sử dụng — thường là **transaction commit đã được broker xác nhận** — và giữ durability tương đương trước khi so sánh.

## 9. Backup, restore và migration: giới hạn thực tế

### 9.1. File journal: sao lưu cần nhất quán nhiều khu vực

Trong file-store, queue metadata và message data có thể trải ở các thư mục riêng. Sao chép từng thư mục khi broker vẫn đang ghi không đảm bảo một **snapshot nhất quán về thời điểm**. Phương án đơn giản cho lab là dừng broker sạch trước khi sao lưu; production có thể dùng cơ chế snapshot nhất quán/backup được tài liệu Artemis và storage provider hỗ trợ.

Khi restore, khôi phục **toàn bộ tập dữ liệu cần thiết**, đúng phiên bản và đường dẫn, sau đó khởi động broker và kiểm chứng queue/messages/transaction states.

### 9.2. JDBC store: dùng backup DB nhưng phải phục hồi toàn bộ trạng thái broker

Với JDBC, dùng cơ chế **transactionally consistent backup/PITR** của PostgreSQL hoặc RDBMS tương ứng. Một bản sao chỉ của bảng message mà thiếu bindings, page store, large messages hoặc node manager state có thể không tạo được broker hợp lệ.

Đặc biệt:

- Quản lý **retention và point-in-time**: restore DB về quá khứ có thể đưa message đã ACK trở lại hoặc làm mất những message đã commit sau thời điểm restore. Consumer phải idempotent.
- Giữ thông tin schema, version, driver, identity và cấu hình broker khớp với DB restore.
- Không “dọn DLQ” hoặc “xóa message” bằng thao tác `DELETE FROM ART_MESSAGES` thủ công.
- Không xem việc DB backup thành công là đủ: cần **drill restore thực tế** rồi chạy client kiểm tra message theo eventId.
- RDBMS backup có thể có cơ chế encryption, access control và audit tốt, nhưng cũng tạo bề mặt quyền truy cập nhạy cảm mới.

### 9.3. Đổi `file journal → JDBC` không tự di chuyển backlog

Đây là sai lầm có thể làm hệ thống tưởng rằng đã “mất” message:

~~~text
Lúc đầu:
  file store đang có 20.000 message chưa ACK

Operator sửa broker.xml:
  <store><database-store>...</database-store></store>

Khởi động lại broker:
  JDBC store là store khác.
  Các message cũ KHÔNG tự động được import từ file journal.
~~~

**Không chuyển đổi store backend bằng cách đổi một thẻ XML trên production instance đang còn dữ liệu.** Tùy nhu cầu, thực hiện một quy trình migration có kiểm soát:

1. Lập inventory queue, durable subscriptions, DLQ/expiry, backlog, schema, TTL, message ID và quyền.
2. Dừng producer hoặc điều phối cutover, ghi checkpoint/eventId.
3. Đưa backlog ra khỏi store cũ bằng consumer/bridge/export–import **được phiên bản hỗ trợ**, sau đó publish sang store mới với xác nhận và idempotency.
4. Khi cần giữ ordering, dừng hoặc chia cutover theo từng luồng/aggregate; không chạy hai đường phân phối gây duplicate ngoài ý định.
5. Kiểm tra số message đầu/cuối theo queue, eventId/hash, ACK, DLQ, durable subscriptions và transaction.
6. Giữ backup và kế hoạch rollback rõ ràng; chỉ xóa store cũ sau khi có bằng chứng nghiệm thu.

**Nguy cơ:** Publish lại bằng message mới thường tạo `JMSMessageID` khác; TTL, priority, selectors, delivery count, delayed messages và header đặc thù provider cũng cần migration plan, không thể suy “copy body là đủ”.

## 10. Quan sát vận hành và các triệu chứng lỗi

| Hiện tượng | File journal cần kiểm tra | JDBC store cần kiểm tra |
|---|---|---|
| Broker startup lỗi | Quyền thư mục, journal file lock, corruption, thiếu disk | DB có chạy? driver class có load? URL/auth/TLS/schema grants đúng? |
| `send/commit` chậm | Fsync, journal sync, disk latency, compaction, paging | Network RTT, connection/transaction latency, locks, WAL fsync/checkpoint |
| Throughput giảm khi payload lớn | Large message dir, paging, disk throughput | BLOB handling, page-store table, DB I/O và driver limit |
| Backlog tăng dần | Producer rate > consumer ACK, paging volume | Tương tự và DB table/WAL growth |
| Broker mất kết nối store | Disk/volume unavailable | DB failover, connection reset, credential rotation, pool starvation |
| Disk đầy | Journal/paging/large message volume | DB data/WAL volume, tablespace, temp files |
| Failover chậm | Journal recovery/HA policy, volume attach | DB/HA lock, recovery, connection setup, replication lag |
| Message không còn sau migration | Có thể đang nhìn vào JDBC store mới | Không import từ file-store cũ |
| Backup restore không dùng được | Snapshot thiếu bindings/paging/large messages | DB backup thiếu bảng/schema hoặc không nhất quán |
| Client thấy duplicate sau restore | ACK state bị khôi phục về quá khứ | DB PITR phục hồi message từng ACK sau điểm restore |

### Những chỉ số nên có

**Broker:**

- Queue count/ready/delivering, enqueue/dequeue/ACK rate, oldest message age.
- Redelivery, expiry, DLQ, transaction rollback, paging active.
- P95/P99 send/commit latency và tỉ lệ lỗi/timeout.
- Thời gian broker startup, recovery và HA takeover.

**File store:**

- IOPS, disk throughput, fsync latency, volume fullness.
- Journal file count/size và paging/large message utilization.
- Lỗi filesystem, permissions, I/O timeout, snapshot age.

**JDBC:**

- DB connectivity và thời gian connect/execute/commit.
- Active connections, lock wait, deadlocks, statement latency.
- WAL generation, checkpoint/sync latency, tablespace growth, replication lag.
- Tuổi backup/PITR, restore drill và thời gian failover DB.

Hãy dùng **eventId** xuyên các tầng để đối chiếu, không dùng tên bảng SQL hay địa chỉ file journal làm khóa nghiệp vụ. Lưu log broker/DB có giới hạn và tránh đưa plaintext credentials hoặc payload nhạy cảm vào diagnostics.

## 11. Bài tập và tình huống ra quyết định

### Bài 1 — Chọn store theo SLO

Một hệ thống cần 20.000 persistent messages/giây, commit p99 dưới 15 ms. Đội ngũ có local NVMe và đã triển khai Artemis replication HA nhưng không có DBA chuyên trách. Bạn chọn baseline store nào để benchmark trước? Hãy giải thích bằng tiêu chí commit latency, IOPS, recovery và chi phí vận hành.

**Hướng phân tích:** Bắt đầu với file journal (với loại I/O phù hợp hạ tầng), benchmark đúng SLO. Không chọn JDBC chỉ vì tổ chức có PostgreSQL; cần dữ liệu chứng minh DB đáp ứng p99/throughput/HA.

### Bài 2 — Yêu cầu DB governance

Một ngân hàng yêu cầu toàn bộ dữ liệu middleware nằm trong RDBMS đã được quản trị với backup, mã hóa, PITR và RBAC, lưu lượng message trung bình. Khi nào JDBC store đáng đánh giá? Những test DB failover, transaction durability, driver compatibility và restore nào bắt buộc?

**Hướng phân tích:** JDBC có thể giảm độ phức tạp governance nếu đã có nền tảng DB tốt, nhưng phải tính DB license/ops, WAL/replication, network dependency và SLO thực tế.

### Bài 3 — “Chuyển store” làm queue biến mất

Sau khi đổi từ file journal sang JDBC, console chỉ hiện queue mới trống; trước đó file store có 3.500 message. Có chắc message đã bị xóa không? Quy trình khôi phục/migrate nào cần thực hiện?

**Hướng phân tích:** Store cũ không được JDBC tự đọc; **không xóa dữ liệu cũ**, dừng các thao tác có rủi ro rồi xác nhận backend/instance, restore config cũ nếu phù hợp, xuất/đẩy backlog theo quy trình an toàn.

### Bài 4 — Độ bền và transaction

Producer gọi `JMSProducer.send()` rồi tiến trình chết **trước khi** `JMSContext.commit()`. Bạn có thể khẳng định message persistent đã được broker commit không? Nếu client timeout ở **đúng thời điểm commit**, kết quả khác nhau ra sao?

**Hướng phân tích:** Gửi trong transacted context chưa commit không đủ để xác nhận; timeout đúng lúc commit có thể tạo trạng thái chưa xác định ở phía client, phải dùng idempotency/outbox.

### Bài 5 — Phục hồi DB về hôm qua

DBA restore database store bằng PITR đến 23:00 hôm trước. Một số event đã ACK từ 23:00 đến 01:00 nay xuất hiện lại. Đây có phải bug của Artemis? Ứng dụng bảo vệ side effect thế nào?

**Hướng phân tích:** Restore đưa durable state về điểm cũ có thể làm message đã ACK sau điểm đó xuất hiện lại, hoặc làm mất message commit sau điểm đó; cần RPO/runbook/idempotency.

### Bài 6 — Hai broker trỏ chung PostgreSQL

Đội vận hành khởi động hai Artemis brokers active độc lập trên hai máy, cùng JDBC URL và cùng bảng `ART_MESSAGES`, hy vọng nhân đôi throughput. Điều gì sai? Phân biệt shared-store HA với clustering có store riêng.

**Hướng phân tích:** Cùng store không đồng nghĩa cluster active/active; cần chính sách HA/lease đúng hoặc mỗi live broker dùng store độc lập và routing/cluster hợp lệ.

### Tiêu chí hoàn thành bài học

Người học cần tự giải thích và chứng minh được:

- File journal và JDBC store lưu những nhóm dữ liệu persistence nào.
- Cách bật `database-store` tại đúng vị trí trong `broker.xml`, kèm JDBC driver/database hợp lệ.
- Vì sao queue durable + persistent message + broker sync/DB durability + commit mới tạo một chuỗi đảm bảo có ý nghĩa.
- Quy trình xác minh năm message sống qua restart ở **cả hai backend**, không nhầm với crash test.
- Những tiêu chí có thể đo để chọn store: SLO, HA, backup/restore, DB dependency, I/O và vận hành.
- Vì sao **đổi store không phải migration**, DB backup không phải HA broker và JDBC tables không phải business API.

## 12. Kết luận và tài liệu đối chiếu

**File journal** là baseline phù hợp với nhiều workload Artemis vì đường ghi tối ưu cho messaging và ít phụ thuộc hạ tầng ngoài broker. **JDBC store** đáng đánh giá khi nền tảng DB, yêu cầu quản trị và khả năng HA/backup tạo ra lợi ích vận hành thực tế, đồng thời p95/p99, throughput và failover vẫn đạt SLO. Không có giải pháp nào miễn nhiễm với crash, restore về quá khứ, backend outage hoặc duplicate do consumer chưa ACK.

Khi ra quyết định, hãy theo thứ tự: **xác định ngữ nghĩa durability cần giữ → kiểm chứng broker/client/version → cấu hình đúng một store → test persistent send/commit và restart → đo lỗi/latency dưới tải → diễn tập backup/restore và failover → chốt RPO/RTO và runbook**.

**Tài liệu chính thức để đối chiếu theo phiên bản:**

- [Apache ActiveMQ Artemis — Persistence](https://artemis.apache.org/components/artemis/documentation/latest/persistence.html): file journal, JDBC database store và các tham số liên quan.
- [Apache ActiveMQ Artemis — Address Model](https://artemis.apache.org/components/artemis/documentation/latest/address-model.html): address, anycast queue, routing và storage semantics.
- [Apache ActiveMQ Artemis — High Availability](https://artemis.apache.org/components/artemis/documentation/latest/ha.html): chính sách HA, replication/shared-store và ranh giới takeover.
- [Apache ActiveMQ Artemis — Paging](https://artemis.apache.org/components/artemis/documentation/latest/paging.html): tác động của address-full policy và paging.
- [Apache ActiveMQ Artemis — Large Messages](https://artemis.apache.org/components/artemis/documentation/latest/large-messages.html): xử lý và lưu payload lớn.

> **Kết quả cần nhớ:** Chọn JDBC hay file journal là quyết định về **đường bền vững và failure domain của broker**, không phải thay đổi API JMS. Code producer/consumer vẫn gửi, nhận, commit và rollback như trước; điều phải chứng minh bằng đo đạc là dữ liệu và nghiệp vụ được phục hồi đúng khi hệ thống thực tế xảy ra lỗi.
