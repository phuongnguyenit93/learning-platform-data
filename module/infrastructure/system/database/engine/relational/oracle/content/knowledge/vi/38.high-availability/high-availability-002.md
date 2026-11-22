# Tổng quan RAC, instance dùng chung database và Cache Fusion

Oracle Real Application Clusters (RAC) cho phép nhiều Oracle Database instance chạy trên nhiều máy chủ và cùng truy cập một database. Mỗi instance có bộ nhớ SGA, các background process và redo thread riêng, nhưng các instance cùng làm việc trên một tập database files dùng chung. Nhờ kiến trúc này, ứng dụng có thể phân phối kết nối và workload giữa nhiều node, đồng thời tiếp tục phục vụ khi một instance hoặc node gặp sự cố, tùy cấu hình và mức độ dự phòng của hệ thống.

Điểm cốt lõi của RAC là **nhiều instance, một database**. RAC không tạo ra nhiều bản sao database độc lập để đồng bộ sau đó. Các instance cùng quản lý một database logic và phối hợp để bảo đảm tính nhất quán khi nhiều node đọc hoặc sửa cùng block dữ liệu.

Sự phối hợp đó được thực hiện qua các dịch vụ cluster và cơ chế truyền block giữa các instance, nổi bật là **Cache Fusion**. Cache Fusion cho phép một instance nhận block dữ liệu cần thiết trực tiếp từ buffer cache của instance khác qua interconnect, thay vì luôn phải đọc lại block từ storage. Cơ chế này là nền tảng để nhiều instance cùng truy cập dữ liệu một cách nhất quán.

## 1. Database, instance và node là ba khái niệm khác nhau

Trong Oracle RAC, cần phân biệt ba thành phần:

- **Database:** tập hợp các physical files và metadata tạo nên một database, chẳng hạn datafiles, control files, online redo log files và các thành phần liên quan.
- **Instance:** các vùng bộ nhớ và background process dùng để quản lý, truy cập database. Một instance có SGA, process, thread redo và trạng thái hoạt động riêng.
- **Node:** máy chủ vật lý hoặc máy ảo tham gia cluster và chạy một instance.

Ở hệ thống single-instance thông thường, một instance quản lý một database tại một thời điểm. Trong RAC, nhiều instance trên nhiều node cùng mở và truy cập một database.

```text
             Ứng dụng / Clients
                    |
             SCAN / Listeners
                    |
          +---------+---------+
          |                   |
     Node 1                Node 2
   +-----------+         +-----------+
   | Instance 1|         | Instance 2|
   | SGA       |         | SGA       |
   | Processes |         | Processes |
   | Redo T1   |         | Redo T2   |
   +-----+-----+         +-----+-----+
          |                     |
          +------ Interconnect -+
                    |
             Shared Storage
       +---------------------------+
       | Datafiles                 |
       | Control files             |
       | Online redo log files     |
       | SPFILE / other files      |
       +---------------------------+
```

Sơ đồ trên là mô hình khái niệm. Mỗi node có instance và bộ nhớ riêng; các instance phối hợp qua interconnect và truy cập cùng database files trên shared storage. RAC còn cần các thành phần clusterware, voting files, OCR và các dịch vụ mạng để quản lý membership, tài nguyên và kết nối.

### 1.1. Một database có thể có nhiều instance

Ví dụ database có tên `SALESDB` chạy trên hai node:

| Thành phần | Node 1 | Node 2 |
|---|---|---|
| Database | `SALESDB` | `SALESDB` |
| Instance | `salesdb1` | `salesdb2` |
| SGA | Riêng | Riêng |
| Background processes | Riêng | Riêng |
| Redo thread | Thread 1 | Thread 2 |
| Datafiles | Cùng tập file | Cùng tập file |
| Online redo logs | Các group thuộc thread 1 | Các group thuộc thread 2 |

Tên instance thường được cấu hình qua `INSTANCE_NAME`; tên database là `DB_NAME`. Trong RAC, các instance có thể có instance name khác nhau nhưng cùng thuộc một database. Cấu hình cụ thể còn phụ thuộc `DB_UNIQUE_NAME`, môi trường CDB/PDB và cách triển khai.

### 1.2. Shared database không có nghĩa shared memory

Các instance không dùng chung một SGA. Mỗi instance có buffer cache, shared pool, large pool, redo buffer và các vùng bộ nhớ khác riêng. Một block đang nằm trong buffer cache của instance 1 không tự động xuất hiện trong buffer cache của instance 2.

Khi instance 2 cần block mà instance 1 đang giữ phiên bản phù hợp, RAC có thể truyền block qua interconnect bằng Cache Fusion. Vì vậy, cần phân biệt:

- Shared storage: các instance truy cập cùng database files.
- Private instance memory: mỗi instance có SGA và process riêng.
- Global coordination: các instance trao đổi thông tin để xác định block đang ở đâu, ai có quyền sửa và phiên bản nào có thể được sử dụng.

Chính sự phối hợp giữa cache riêng và dữ liệu lưu trữ chung làm RAC khác với mô hình một instance đơn giản.

## 2. Vì sao cần Oracle RAC?

RAC thường được triển khai để đáp ứng yêu cầu về khả năng sẵn sàng, phân phối workload hoặc mở rộng năng lực xử lý theo chiều ngang.

### 2.1. High availability

Nếu một instance hoặc node ngừng hoạt động, các instance còn lại có thể tiếp tục phục vụ database. Dịch vụ ứng dụng được cấu hình để chuyển kết nối mới sang instance còn hoạt động. Các session đang chạy trên node gặp sự cố có thể bị ngắt; ứng dụng cần cơ chế reconnect và retry phù hợp.

RAC không đảm bảo mọi transaction đang chạy đều tiếp tục nguyên trạng khi node bị lỗi. Transaction chưa commit trên instance bị mất thường cần được rollback hoặc phục hồi theo cơ chế database. Application Continuity, Transparent Application Failover (TAF) hoặc các cơ chế client/service phù hợp có thể giảm ảnh hưởng đối với một số loại workload, nhưng cần cấu hình và kiểm thử theo hành vi ứng dụng.

### 2.2. Scalability

Nhiều instance có thể cùng xử lý workload. Khi thêm node, hệ thống có thể tăng tổng năng lực CPU và khả năng phục vụ kết nối nếu workload có thể phân phối hiệu quả.

Tuy nhiên, thêm node không đảm bảo hiệu năng tăng tuyến tính. Nếu nhiều instance thường xuyên sửa cùng một block, Cache Fusion và global coordination có thể tạo chi phí lớn. Workload có contention trên cùng index leaf block, sequence hot spot hoặc bảng tập trung có thể mở rộng kém khi tăng số instance.

### 2.3. Workload distribution

Services giúp phân loại workload và điều phối kết nối đến các instance thích hợp. Ví dụ:

- `OLTP_SERVICE`: ưu tiên workload giao dịch ngắn, có thể chạy trên các instance OLTP.
- `REPORT_SERVICE`: định tuyến báo cáo đến nhóm instance được chỉ định, nếu kiến trúc và tài nguyên cho phép.
- `BATCH_SERVICE`: chỉ chạy batch trên một tập instance hoặc theo lịch để tránh cạnh tranh với giao dịch trực tuyến.

Service placement, preferred/available instances và policy của service cần được thiết kế cùng ứng dụng. Không nên giả định mọi service tự động cân bằng hoàn hảo hoặc mọi kết nối luôn được chuyển sang node ít tải nhất.

## 3. Thành phần kiến trúc của RAC

### 3.1. Oracle Grid Infrastructure và Clusterware

Oracle Grid Infrastructure cung cấp nền tảng cluster để quản lý các node và tài nguyên. Thành phần Clusterware giám sát trạng thái node, network, storage và các tài nguyên database/service; điều phối khởi động, dừng và failover theo cấu hình.

Các khái niệm thường gặp:

| Thành phần | Vai trò |
|---|---|
| Cluster membership | Xác định node nào đang là thành viên hợp lệ của cluster |
| Oracle Clusterware | Quản lý tài nguyên cluster như database, instance, listener, service và VIP |
| Voting files | Hỗ trợ quyết định membership/quorum và tránh nhiều nhóm node cùng tự nhận là cluster hợp lệ |
| OCR (Oracle Cluster Registry) | Lưu cấu hình tài nguyên và thông tin cluster được Clusterware quản lý |
| Cluster interconnect | Network riêng hoặc network được cấu hình cho trao đổi nội bộ cluster, bao gồm Cache Fusion traffic |
| Node VIP | Địa chỉ IP ảo của node, hỗ trợ chuyển kết nối khi node gặp sự cố |
| SCAN | Single Client Access Name, điểm truy cập thống nhất cho client RAC |

Voting files và OCR có vai trò khác nhau. Voting files tham gia vào membership/quorum; OCR lưu cấu hình cluster. Chúng không thay thế datafiles, control files hoặc redo logs của database.

### 3.2. Shared storage

Các instance RAC phải truy cập được tập database files chung. Shared storage có thể được cung cấp qua SAN, NAS hoặc Oracle Automatic Storage Management (ASM) tùy kiến trúc hỗ trợ.

ASM là volume manager và file system chuyên dụng cho Oracle Database. ASM disk group có thể chứa datafiles, control files, online redo logs, archive logs và các file liên quan. ASM có thể phân phối và mirror dữ liệu theo redundancy configuration.

Shared storage không có nghĩa các instance cùng ghi tùy ý vào một data block mà không phối hợp. Việc cấp quyền truy cập block và bảo đảm tính nhất quán được điều phối bởi RAC. Storage và interconnect đều cần thiết; một shared disk nhanh nhưng interconnect kém vẫn có thể làm RAC chậm khi Cache Fusion traffic cao.

### 3.3. Interconnect

Interconnect là đường truyền mạng nội bộ giữa các node. Nó mang thông tin điều phối cluster và dữ liệu block được truyền giữa các instance. Với workload có nhiều cross-instance access, độ trễ và băng thông của interconnect ảnh hưởng trực tiếp đến hiệu năng.

Thiết kế interconnect cần quan tâm:

- Băng thông đủ cho peak Cache Fusion traffic.
- Độ trễ thấp và ổn định.
- Không bị nghẽn bởi traffic ứng dụng hoặc backup không được kiểm soát.
- Redundancy và khả năng phát hiện lỗi network.
- Cấu hình MTU, bonding, VLAN và routing đúng theo hướng dẫn Oracle và hệ điều hành.

Không nên chỉ kiểm tra tốc độ link danh nghĩa. Hãy đo latency, packet loss, throughput và các thống kê RAC liên quan trong workload thật.

### 3.4. Redo thread và undo

Mỗi RAC instance có redo thread riêng. Khi instance thực hiện thay đổi dữ liệu, redo được ghi vào online redo log groups của thread đó. Tất cả thread thuộc cùng database và cần được cấu hình để đáp ứng recovery và archiving.

Mỗi instance cũng sử dụng undo tablespace phù hợp cho hoạt động transaction của mình. Các transaction của instance được nhận diện trong database và có thể được instance khác truy cập thông tin khi cần phục hồi hoặc phối hợp.

Không nên nhầm redo thread với database riêng. Các thread đều thuộc một database; archive log và recovery phải xem xét các thread liên quan.

## 4. Cách client kết nối tới RAC

Client thường kết nối thông qua service name thay vì gắn cứng vào một instance cụ thể. Oracle RAC cung cấp SCAN và listeners để tìm instance phù hợp phục vụ service.

### 4.1. SCAN và SCAN listener

SCAN là tên truy cập thống nhất cho cluster. DNS hoặc cấu hình mạng phân giải SCAN name thành một hoặc nhiều SCAN VIP. Client gửi yêu cầu kết nối tới SCAN listener; listener chuyển hướng client đến local listener của node có instance đang cung cấp service.

Mô hình đơn giản:

```text
Client
  |
  | connect to sales-scan.example.com:1521 / service SALES_APP
  v
SCAN VIP / SCAN Listener
  |
  +----> Node 1 local listener ----> salesdb1
  |
  +----> Node 2 local listener ----> salesdb2
```

SCAN giúp client dùng một tên kết nối ổn định khi số node hoặc service placement thay đổi. Nó không phải database và cũng không phải một load balancer xử lý mọi câu SQL. SCAN listener chủ yếu hỗ trợ định tuyến kết nối; phân phối session và workload còn phụ thuộc service configuration và load balancing policy.

### 4.2. Service là đơn vị kết nối logic

Service biểu diễn một workload hoặc nhóm ứng dụng. Database có thể có nhiều service với placement, goal và policy khác nhau.

Ví dụ kiểm tra service trong database:

```sql
SELECT name,
       network_name,
       goal,
       clb_goal
FROM dba_services
ORDER BY name;
```

View và cột có thể khác theo phiên bản hoặc quyền truy cập. Trong môi trường RAC, có thể dùng `GV$ACTIVE_SERVICES` để xem service đang hoạt động trên instance nào:

```sql
SELECT inst_id,
       name,
       network_name
FROM gv$active_services
ORDER BY name, inst_id;
```

Một service có thể được cấu hình chạy trên preferred instances và failover sang available instances. Với policy-managed database, server pool có thể được dùng để xác định nơi service chạy. Chi tiết cấu hình được quản lý qua SRVCTL hoặc công cụ quản trị phù hợp của phiên bản.

### 4.3. Client-side load balancing và runtime load balancing

Hai khái niệm cần phân biệt:

- **Connection load balancing:** phân phối các kết nối mới giữa các instance cung cấp service.
- **Runtime connection load balancing:** cung cấp thông tin để client có khả năng hỗ trợ chọn instance dựa trên tình trạng workload/service.

Kết nối mới được phân phối không đồng nghĩa một câu SQL đang chạy sẽ được chuyển sang node khác. Session đã gắn với một instance trong suốt vòng đời kết nối, trừ khi có cơ chế failover/replay phù hợp.

### 4.4. Ví dụ cấu hình kết nối

Một client có thể dùng connect descriptor với service name:

```text
salesdb_high =
  (DESCRIPTION =
    (ADDRESS =
      (PROTOCOL = TCP)
      (HOST = sales-scan.example.com)
      (PORT = 1521)
    )
    (CONNECT_DATA =
      (SERVICE_NAME = sales_app.example.com)
    )
  )
```

Trong JDBC, ứng dụng thường dùng service name trong URL dạng:

```text
jdbc:oracle:thin:@//sales-scan.example.com:1521/sales_app.example.com
```

Ứng dụng nên kết nối bằng service đã được DBA công bố, không hard-code `INSTANCE_NAME` nếu mục tiêu là workload có khả năng phân phối/failover trong RAC.

## 5. Global Cache và Global Enqueue Services

Nhiều instance cùng truy cập dữ liệu nên Oracle cần cơ chế theo dõi trạng thái block và lock trên toàn cluster. Hai dịch vụ quan trọng là Global Cache Service (GCS) và Global Enqueue Service (GES).

### 5.1. Global Cache Service (GCS)

GCS phối hợp quản lý trạng thái và vị trí các block trong các buffer cache của instance. Khi một instance cần block, GCS giúp xác định block có thể lấy từ cache nào, trạng thái hiện tại ra sao và cần chuyển giao quyền truy cập thế nào.

GCS liên quan đến các khái niệm như:

- Global resource directory: thông tin điều phối về resource/block trong cluster.
- Block ownership/mastership: instance chịu trách nhiệm điều phối resource tương ứng.
- Block mode: trạng thái truy cập hiện tại, chẳng hạn shared hoặc exclusive.
- Current/consistent block: phiên bản block phù hợp cho thao tác đọc hoặc sửa.

GCS không đơn giản là một process duy nhất hay một bảng metadata trên disk. Nó là một dịch vụ phân tán phối hợp giữa các instance.

### 5.2. Global Enqueue Service (GES)

GES quản lý các global enqueue/resource cần điều phối giữa instance. Nó xử lý các loại lock và tài nguyên đồng bộ ở phạm vi cluster, bao gồm nhiều loại resource không chỉ là buffer block.

GCS tập trung vào cache/block coordination; GES tập trung vào global enqueue coordination. Trong thực tế hai dịch vụ tương tác để giữ nhất quán và điều phối hoạt động database.

### 5.3. Global Resource Directory (GRD)

Global Resource Directory lưu thông tin điều phối về các resource mà RAC cần quản lý. Mỗi resource có master instance chịu trách nhiệm điều phối thông tin liên quan. Master có thể thay đổi theo trạng thái cluster hoặc cơ chế quản lý resource.

Khi một instance yêu cầu block, nó không cần quét tất cả cache của mọi node. Cơ chế quản lý global resource giúp định vị nơi có bản sao phù hợp và thực hiện chuyển giao theo protocol.

## 6. Cache Fusion là gì?

Cache Fusion là cơ chế cho phép các instance RAC truyền block dữ liệu trực tiếp giữa các buffer cache qua interconnect. Nó giúp một instance nhận block từ instance khác khi block đang được cache ở đó, giảm nhu cầu đọc lại block từ disk trong nhiều trường hợp.

Ví dụ, instance 1 đã đọc block chứa các dòng `ORDERS`. Sau đó session trên instance 2 cần đọc hoặc cập nhật cùng block. Instance 2 yêu cầu quyền truy cập phù hợp thông qua cơ chế global cache. Nếu instance 1 đang giữ block, Oracle có thể chuyển block qua interconnect theo trạng thái cần thiết.

```text
       Instance 1                         Instance 2
  +-------------------+              +-------------------+
  | Buffer Cache      |              | Buffer Cache      |
  | Block B (current) |              | Request Block B   |
  +---------+---------+              +---------+---------+
            |                                  |
            +----------- Interconnect --------+
                       Cache Fusion
                              |
                    GCS coordinates access
```

Cache Fusion không phải replication bất đồng bộ giữa hai database. Nó là cơ chế chuyển block giữa các cache của những instance cùng mở một database, với sự điều phối của GCS/GES và quy tắc nhất quán của Oracle.

## 7. Các trạng thái block và cách block được chuyển

Để hiểu Cache Fusion, cần phân biệt một số khái niệm trạng thái block.

### 7.1. Consistent Read (CR) block

Một consistent read block là phiên bản block được dựng để đáp ứng read consistency tại một SCN phù hợp. Oracle có thể dùng undo để tạo phiên bản nhất quán của block cho truy vấn.

Một query có thể đọc block theo consistent read mà không cần chặn transaction đang thay đổi dữ liệu. Nếu cache của instance khác có block phù hợp, block hoặc dữ liệu cần thiết có thể được chuyển qua Cache Fusion; nếu cần phiên bản cũ hơn, Oracle có thể áp dụng undo theo cơ chế consistent read.

CR block không nhất thiết là bản sao vật lý giống hệt current block ở thời điểm hiện tại. Nó đại diện cho phiên bản dữ liệu nhất quán với snapshot mà query cần.

### 7.2. Current block

Current block là phiên bản hiện hành của block trong cache, dùng cho các hoạt động cần trạng thái hiện tại và thay đổi dữ liệu. Một block chỉ có một current version hợp lệ tại một thời điểm logic, nhưng có thể tồn tại các CR copies trên các instance khác nhau.

Khi một transaction cần sửa block, Oracle phải cấp quyền truy cập exclusive phù hợp. Nếu instance khác đang giữ quyền hoặc bản sao, RAC phối hợp thu hồi/chuyển giao trạng thái theo protocol.

### 7.3. Shared và exclusive mode

Ở mức khái niệm:

- Shared mode cho phép nhiều instance giữ bản sao phù hợp để đọc.
- Exclusive mode cho phép một instance có quyền sửa block theo quy tắc cache coherency.

Tên mode và trạng thái cụ thể được Oracle quản lý nội bộ. Người vận hành thường quan sát các wait event hoặc thống kê global cache thay vì tự điều khiển block mode.

### 7.4. Một luồng đọc block qua Cache Fusion

Giả sử session trên instance 2 cần đọc block mà instance 1 đang giữ:

1. Instance 2 phát hiện block chưa có trong local buffer cache.
2. Instance 2 yêu cầu block qua cơ chế global cache.
3. GCS xác định trạng thái resource và instance đang giữ block phù hợp.
4. Instance 1 có thể gửi block qua interconnect cho instance 2.
5. Instance 2 nhận block vào buffer cache và tiếp tục truy vấn.

Đây là mô tả khái niệm; protocol thực tế có nhiều trạng thái và trường hợp tối ưu khác nhau. Không phải mọi cache miss đều tạo cùng một loại wait hoặc cùng một đường truyền.

### 7.5. Một luồng ghi block từ instance khác

Giả sử instance 1 đang giữ block ở trạng thái shared và instance 2 muốn cập nhật dòng trong block:

1. Instance 2 yêu cầu quyền exclusive phù hợp.
2. GCS/GES điều phối việc chuyển trạng thái và thu hồi các bản sao không còn phù hợp.
3. Instance đang giữ block có thể gửi block hiện tại hoặc thực hiện hành động được protocol yêu cầu.
4. Instance 2 nhận quyền và block cần thiết để thực hiện thay đổi.
5. Redo cho thay đổi được tạo và ghi theo redo thread của instance 2.
6. Các instance khác sẽ nhận biết trạng thái mới thông qua cơ chế cache coherency.

Block không được cập nhật độc lập trên hai node rồi hợp nhất sau. RAC điều phối quyền truy cập trước khi sửa để tránh các bản sao xung đột.

## 8. Cache Fusion và disk I/O

Cache Fusion có thể giảm physical I/O khi block cần thiết đã nằm trong buffer cache của instance khác. Tuy nhiên, truyền block qua interconnect vẫn có chi phí latency và CPU. Một block lấy từ remote cache không miễn phí.

Có thể hình dung các tình huống:

| Tình huống | Đường lấy dữ liệu khái quát | Chi phí cần xem |
|---|---|---|
| Block có trong local cache | Đọc từ local buffer cache | CPU và memory access |
| Block không có local nhưng có ở remote cache | Cache Fusion qua interconnect | Interconnect latency, global cache coordination |
| Block không có bản sao cache phù hợp | Đọc từ storage vào cache | Storage I/O và cache management |
| Block cần quyền sửa đang được instance khác giữ | Global coordination và chuyển block/quyền | Global cache waits, interconnect và contention |

Vì vậy, khi thấy physical reads thấp, không thể kết luận RAC không có chi phí truy cập dữ liệu. Một workload có thể có nhiều global cache waits dù không đọc nhiều từ disk.

## 9. Global Cache waits và chẩn đoán hiệu năng

Khi RAC phải chờ block hoặc quyền truy cập từ instance khác, session có thể ghi nhận global cache wait events. Tên wait event thay đổi theo phiên bản và tình huống, nhưng thường gặp các nhóm như:

- `gc cr request`: chờ consistent-read block từ global cache.
- `gc current request`: chờ current block hoặc quyền truy cập current phù hợp.
- `gc cr block 2-way` / `gc cr block 3-way`: các dạng truyền consistent-read block.
- `gc current block 2-way` / `gc current block 3-way`: các dạng truyền current block.
- `gc buffer busy acquire` và `gc buffer busy release`: chờ liên quan đến buffer/global cache contention trong một số tình huống.

Tên cụ thể, ý nghĩa chi tiết và các biến thể phụ thuộc phiên bản Oracle. Không nên chẩn đoán chỉ bằng tên event; cần kết hợp thời gian chờ, số lần chờ, object/block liên quan, instance nguồn/đích và execution plan.

### 9.1. Xem global cache wait trong session

Ví dụ xem wait event của session hiện tại:

```sql
SELECT event,
       total_waits,
       time_waited_micro
FROM v$session_event
WHERE sid = SYS_CONTEXT('USERENV', 'SID')
  AND event LIKE 'gc%'
ORDER BY time_waited_micro DESC;
```

Với RAC, `GV$` view cho phép quan sát nhiều instance:

```sql
SELECT inst_id,
       event,
       total_waits,
       time_waited_micro
FROM gv$system_event
WHERE event LIKE 'gc%'
ORDER BY time_waited_micro DESC;
```

Các bộ đếm system event thường là số liệu tích lũy từ lúc instance khởi động. Muốn đánh giá một khoảng thời gian, nên lấy hai snapshot và tính delta; cần lưu ý restart hoặc reset counters.

### 9.2. Xem thống kê cache transfer

Có thể xem các thống kê global cache trong `GV$SYSSTAT`:

```sql
SELECT inst_id,
       name,
       value
FROM gv$sysstat
WHERE LOWER(name) LIKE '%gc%'
ORDER BY inst_id, name;
```

Tên statistic có thể khác theo phiên bản. Truy vấn trên giúp khám phá các counter hiện có; hãy chọn đúng counter và tính delta trước khi kết luận.

### 9.3. Xem block contention theo object

Các view như `GV$SESSION`, `GV$SESSION_WAIT`, `GV$ACTIVE_SESSION_HISTORY` (nếu có quyền và tính năng phù hợp) và các báo cáo AWR có thể giúp liên hệ wait event với SQL, object và block. Một số view hoặc dữ liệu lịch sử cần quyền quản trị và có thể liên quan đến tính năng được cấp phép riêng; tuân theo chính sách của tổ chức.

Ví dụ xem session đang chờ:

```sql
SELECT inst_id,
       sid,
       serial#,
       username,
       event,
       wait_class,
       seconds_in_wait,
       sql_id,
       blocking_instance,
       blocking_session
FROM gv$session
WHERE wait_class <> 'Idle'
ORDER BY seconds_in_wait DESC;
```

Để xác định object/block cụ thể, cần bổ sung thông tin row wait như `ROW_WAIT_OBJ#`, `ROW_WAIT_FILE#`, `ROW_WAIT_BLOCK#` khi phù hợp và ánh xạ object ID qua data dictionary. Không phải mọi global cache wait đều cung cấp row-wait information hữu ích.

### 9.4. Phân biệt cache transfer bình thường với contention

RAC cần truyền block giữa các instance; một số global cache waits là hoạt động bình thường. Chỉ số wait count cao chưa đủ để kết luận có vấn đề. Cần xem:

- Tổng thời gian chờ và tỷ lệ so với DB time.
- Wait trung bình và phân bố latency.
- SQL nào tạo ra traffic.
- Block hoặc object nào bị truy cập nhiều từ nhiều instance.
- DML có tập trung vào cùng block hoặc index leaf không.
- Interconnect có latency, packet loss hoặc băng thông bất thường không.
- Có thể thay đổi service placement hoặc workload affinity để giảm cross-instance traffic không.

## 10. Affinity, locality và giảm block ping

Một vấn đề hiệu năng thường gặp trong RAC là cùng một block được nhiều instance luân phiên yêu cầu quyền sửa. Việc chuyển block qua lại có thể tạo global cache traffic và wait. Hiện tượng này thường được gọi là block pinging hoặc block contention tùy ngữ cảnh.

Ví dụ, hai service trên hai node cùng cập nhật một nhóm dòng tập trung trong bảng `COUNTERS`. Nếu nhiều session trên cả hai instance liên tục sửa cùng block, quyền current có thể phải chuyển qua lại giữa node.

Các hướng giảm chi phí:

- **Workload affinity:** định tuyến các giao dịch thường truy cập cùng nhóm dữ liệu về cùng instance/service khi phù hợp.
- **Partitioning:** chia dữ liệu để các workload khác nhau chủ yếu chạm vào partition/block khác nhau.
- **Giảm hot block:** thiết kế lại index hoặc cách ghi để tránh nhiều session cùng cập nhật một block tập trung.
- **Batching:** gom các thay đổi nhỏ thành batch hợp lý để giảm số lần điều phối và round-trip.
- **Sequence cache:** dùng cache phù hợp để giảm hoạt động quản lý sequence; không bật `ORDER` nếu nghiệp vụ không cần thứ tự toàn cluster.
- **Tối ưu SQL:** giảm số lần truy cập cùng block và thời gian giữ transaction.

### 10.1. Index hot block

Một index có key tăng tuần tự có thể khiến nhiều session insert cùng đi tới vùng leaf block cuối index. Trong RAC, nếu insert diễn ra đồng thời trên nhiều instance, block nóng có thể được chuyển giữa các node.

Giải pháp phụ thuộc loại index, phiên bản và workload. Có thể cân nhắc reverse key index cho một số pattern equality lookup, hash partitioned index hoặc các kỹ thuật khác khi phù hợp. Reverse key index không phù hợp với mọi range scan; partitioning và thiết kế index cần được đánh giá trên truy vấn thực tế.

### 10.2. Sequence trong RAC

Sequence là đối tượng dùng để sinh giá trị số, thường dùng làm khóa. Trong RAC, sequence có thể được cache để giảm chi phí phối hợp và truy cập dictionary.

Ví dụ:

```sql
CREATE SEQUENCE order_id_seq
    START WITH 1
    INCREMENT BY 1
    CACHE 1000
    NOORDER;
```

`CACHE` giúp mỗi instance giữ trước một nhóm giá trị để giảm chi phí lấy giá trị mới. Khi instance lỗi hoặc restart, các giá trị đã cache nhưng chưa dùng có thể bị mất, tạo khoảng trống trong sequence. Sequence không bảo đảm không có gap.

`ORDER` yêu cầu giá trị được cấp theo thứ tự request toàn cục theo quy tắc sequence, nhưng có thể tăng coordination overhead. Với phần lớn khóa surrogate, chỉ cần giá trị duy nhất chứ không cần thứ tự thời gian tuyệt đối; `NOORDER` thường phù hợp hơn. Nếu nghiệp vụ cần thứ tự giao dịch, hãy dùng timestamp/commit metadata hoặc cơ chế nghiệp vụ rõ ràng thay vì giả định sequence là thứ tự commit.

## 11. RAC và tính nhất quán transaction

Các instance cùng truy cập một database nên Oracle phải duy trì read consistency và transaction isolation trên toàn cluster.

### 11.1. Redo và undo vẫn hoạt động theo transaction

Khi session thay đổi dữ liệu trên instance 1, Oracle tạo undo để có thể rollback hoặc dựng consistent read, đồng thời tạo redo để phục hồi thay đổi. Redo được ghi vào thread của instance thực hiện thay đổi.

Instance khác đọc dữ liệu đã commit theo SCN và cơ chế consistent read. Nếu block hiện tại ở remote cache, Cache Fusion có thể cung cấp block; nếu cần phiên bản cũ hơn, Oracle có thể dựng CR version từ undo.

### 11.2. Commit và redo durability

Khi transaction commit, Oracle phải bảo đảm redo cần thiết được ghi bền vững theo quy tắc commit trước khi báo thành công. RAC không làm thay đổi nguyên tắc transaction durability. Mỗi instance có redo thread riêng nhưng cùng database quản lý tất cả thread.

### 11.3. Instance recovery

Nếu một instance lỗi, các instance còn lại phát hiện membership change và database thực hiện instance recovery cho redo/undo của instance lỗi theo cơ chế Oracle. Recovery có thể bao gồm roll forward các thay đổi đã ghi redo và rollback các transaction chưa commit bằng undo.

Các instance còn sống có thể tiếp tục phục vụ khi recovery và dịch vụ được điều phối phù hợp. Thời gian phục hồi phụ thuộc lượng redo, trạng thái cache, cấu hình cluster và workload. RAC không loại bỏ nhu cầu backup, media recovery hoặc Data Guard.

## 12. Xử lý node/instance failure và dịch vụ ứng dụng

RAC cung cấp nền tảng high availability, nhưng trải nghiệm ứng dụng phụ thuộc cách service và client được cấu hình.

### 12.1. Khi một node bị lỗi

Một luồng xử lý tổng quát:

1. Clusterware phát hiện node hoặc instance không còn hoạt động.
2. Cluster membership được cập nhật; các node còn lại xác định trạng thái thành viên hợp lệ.
3. Resource và service được chuyển hoặc khởi động trên instance còn hoạt động theo policy.
4. Database thực hiện recovery cần thiết cho transaction của instance lỗi.
5. Client có thể reconnect qua SCAN/service; session cũ có thể cần được tạo lại.

Nếu interconnect bị phân vùng mạng, cluster cần tránh tình huống nhiều nhóm node cùng hoạt động như các cluster độc lập trên cùng shared storage. Cơ chế membership/quorum và fencing giúp bảo vệ tính toàn vẹn. Cấu hình voting files, network redundancy và storage fencing phải được vận hành theo hướng dẫn Oracle.

### 12.2. TAF và Application Continuity

Các cơ chế client có thể giảm thời gian gián đoạn:

- **Transparent Application Failover (TAF):** hỗ trợ failover session cho một số loại kết nối và trạng thái truy vấn. Khả năng tiếp tục fetch hoặc khôi phục session phụ thuộc loại câu lệnh và cấu hình.
- **Application Continuity:** có thể replay một số request sau lỗi nếu ứng dụng, driver, service và database được cấu hình phù hợp.
- **Fast Application Notification (FAN):** thông báo thay đổi trạng thái service/instance để client pool phản ứng nhanh.
- **Fast Connection Failover (FCF):** giúp connection pool tương thích nhận FAN và loại bỏ kết nối lỗi.

Không nên tuyên bố rằng RAC tự động làm mọi request chạy lại an toàn. Ứng dụng phải xử lý transaction boundary, idempotency, side effects và lỗi không xác định kết quả commit. Gửi email, gọi API bên ngoài hoặc ghi file không tự động được replay an toàn.

### 12.3. Kiểm thử failover

Một bài kiểm thử failover cần xác nhận:

- Kết nối mới có thể tới service trên node còn sống.
- Connection pool loại bỏ kết nối hỏng và tạo kết nối mới.
- Transaction đang chạy trên instance lỗi có kết quả đúng theo quy tắc rollback/recovery.
- Retry không tạo giao dịch trùng.
- Thời gian phục hồi nằm trong mục tiêu RTO của hệ thống.
- Dữ liệu đã commit vẫn bền vững theo mục tiêu RPO.
- Alert, monitoring và runbook nhận biết được node/service failure.

## 13. RAC khác Data Guard và các mô hình HA khác như thế nào?

RAC và Data Guard giải quyết những vấn đề khác nhau, dù có thể được kết hợp trong cùng kiến trúc.

| Tiêu chí | Oracle RAC | Oracle Data Guard |
|---|---|---|
| Mục tiêu chính | Nhiều instance cùng truy cập một database để HA và scale workload | Duy trì database standby để bảo vệ và phục hồi sau sự cố site/database |
| Storage | Các instance dùng chung database files | Primary và standby có database files riêng ở các site/storage khác nhau |
| Instance | Nhiều instance mở cùng database | Primary và standby có vai trò database riêng; standby có thể mount hoặc open theo chế độ hỗ trợ |
| Đồng bộ dữ liệu | Cache Fusion và redo/transaction coordination trong cùng database | Redo transport và apply từ primary sang standby |
| Lỗi node | Instance khác trong cluster có thể tiếp tục phục vụ | Standby có thể được chuyển thành primary khi failover/switchover phù hợp |
| Bảo vệ lỗi site | Không tự giải quyết toàn bộ mất site hoặc shared storage | Có thể bảo vệ trước lỗi site tùy thiết kế và khoảng cách |

RAC bảo vệ trước một số loại lỗi instance/node và giúp phân phối workload trong một cluster. Data Guard bảo vệ trước lỗi database/site và cung cấp bản standby. Một hệ thống yêu cầu cả HA cục bộ lẫn DR có thể dùng RAC ở primary site kết hợp Data Guard tới site dự phòng.

## 14. Các view và lệnh thường dùng để quan sát RAC

### 14.1. Xem instance đang hoạt động

```sql
SELECT inst_id,
       instance_name,
       host_name,
       status,
       database_status,
       startup_time
FROM gv$instance
ORDER BY inst_id;
```

`GV$INSTANCE` tổng hợp thông tin instance từ các node mà database có thể quan sát. `V$INSTANCE` chỉ phản ánh instance hiện tại của session.

### 14.2. Xem database và thread

```sql
SELECT dbid,
       name,
       db_unique_name,
       open_mode,
       database_role
FROM v$database;
```

```sql
SELECT thread#,
       status,
       enabled,
       groups
FROM v$thread
ORDER BY thread#;
```

Các cột có thể khác theo phiên bản; kiểm tra data dictionary khi viết script dùng lâu dài.

### 14.3. Xem session theo instance

```sql
SELECT inst_id,
       username,
       service_name,
       status,
       COUNT(*) AS session_count
FROM gv$session
WHERE type = 'USER'
GROUP BY inst_id, username, service_name, status
ORDER BY inst_id, username, service_name;
```

Truy vấn này giúp xem session đang phân bố trên các instance như thế nào. Số session không đồng nghĩa mức tải CPU hoặc DB time; cần xem thêm active sessions, wait events và service workload.

### 14.4. Xem các thống kê liên quan Cache Fusion

```sql
SELECT inst_id,
       event,
       total_waits,
       time_waited_micro
FROM gv$system_event
WHERE event LIKE 'gc%'
ORDER BY inst_id, time_waited_micro DESC;
```

Để điều tra đúng khoảng thời gian, lấy snapshot trước và sau, rồi tính delta. Không so sánh tổng counter của hai instance có uptime khác nhau mà không chuẩn hóa theo thời gian hoặc workload.

### 14.5. Xem interconnect và cluster resource

Một số thông tin về cluster network và resource có thể được quan sát qua dynamic performance views, Clusterware utilities và hệ điều hành. Các lệnh `crsctl`, `srvctl`, `olsnodes` và `asmcmd` thường được dùng trong quản trị Grid Infrastructure/ASM; cú pháp cụ thể phụ thuộc phiên bản và quyền OS/grid owner.

Ví dụ các lệnh kiểm tra ở mức khái niệm:

```text
olsnodes -n
crsctl stat res -t
srvctl status database -db SALESDB
srvctl status service -db SALESDB
```

Chỉ chạy lệnh quản trị theo runbook và quyền được cấp. Không dùng các lệnh start/stop hoặc thay đổi resource trong môi trường production khi chưa theo quy trình change control.

## 15. Các nguyên nhân làm RAC chậm dù có nhiều node

Thêm instance không giải quyết được mọi điểm nghẽn. Một số nguyên nhân thường gặp:

### 15.1. Block pinging và hot block

Nhiều instance liên tục yêu cầu quyền sửa cùng block. Điều này tạo chuyển giao current block, tăng global cache waits và interconnect traffic. Cần tìm object/index/segment và pattern DML gây tập trung.

### 15.2. Workload không có locality

Các session trên nhiều node cùng truy cập cùng dữ liệu nóng, trong khi workload có thể được phân nhóm theo tenant, customer hoặc service. Định tuyến workload để giữ locality có thể giảm cross-instance block transfer.

### 15.3. Interconnect latency hoặc nghẽn

Cache Fusion phụ thuộc interconnect. Network chậm, packet loss, congestion hoặc cấu hình sai có thể làm global cache waits tăng dù storage hoạt động tốt.

### 15.4. Hot index leaf block

Index tăng tuần tự có thể tập trung insert vào một số leaf block. Trong RAC, nhiều instance ghi vào cùng vùng index có thể tạo contention. Cần xem index design, sequence cache, reverse key/hash partitioning và workload trước khi chọn giải pháp.

### 15.5. SQL và execution plan không phù hợp

Một SQL xử lý quá nhiều dòng, join sai thứ tự hoặc lặp lookup quá nhiều lần vẫn chậm trên RAC. Tối ưu SQL, statistics và index vẫn quan trọng; RAC không thay thế công việc tuning ở cấp câu lệnh.

### 15.6. Service placement không hợp lý

Nếu mọi service đều hoạt động trên mọi node dù workload có affinity, các giao dịch có thể làm tăng cross-instance traffic. Phân nhóm service và connection pool theo workload có thể giúp cải thiện locality, nhưng cần tránh làm một node quá tải.

### 15.7. Shared storage hoặc CPU đã bão hòa

RAC không tự tăng băng thông storage hoặc CPU vô hạn. Nếu shared storage là bottleneck, thêm instance có thể làm mức cạnh tranh tăng lên. Cần đánh giá cả CPU, I/O, interconnect và global cache.

## 16. Nguyên tắc thiết kế và vận hành RAC

Một hệ thống RAC ổn định cần thiết kế đồng bộ từ cluster đến ứng dụng:

1. **Thiết kế node và cluster:** bảo đảm node, voting files, OCR, network và storage redundancy theo kiến trúc được hỗ trợ.
2. **Thiết kế shared storage:** chọn ASM/storage phù hợp, có đường truy cập dự phòng và giám sát latency.
3. **Thiết kế interconnect:** băng thông và latency phù hợp với mức Cache Fusion traffic dự kiến.
4. **Thiết kế service:** phân loại workload, xác định preferred/available instance và policy kết nối.
5. **Thiết kế connection pool:** dùng service name, hỗ trợ FAN/FCF hoặc cơ chế driver phù hợp và kiểm soát reconnect.
6. **Thiết kế transaction:** transaction ngắn, retry có idempotency, không giữ lock khi gọi dịch vụ ngoài lâu.
7. **Thiết kế data locality:** hạn chế nhiều instance sửa cùng block nếu workload có thể phân vùng/định tuyến.
8. **Thiết kế sequence/index:** cân nhắc cache, hot block và index strategy cho insert đồng thời.
9. **Giám sát toàn cluster:** xem theo `INST_ID`, service, SQL, wait class, global cache và interconnect.
10. **Kiểm thử failure:** kiểm tra node loss, network interruption, service failover và hành vi transaction/application.

## 17. Bài thực hành: theo dõi một ứng dụng trên hai instance

Giả sử database `SALESDB` có hai instance `salesdb1` và `salesdb2`. Ứng dụng kết nối qua service `sales_app`.

### Bước 1: Xác nhận cả hai instance

```sql
SELECT inst_id,
       instance_name,
       host_name,
       status
FROM gv$instance
ORDER BY inst_id;
```

### Bước 2: Kiểm tra service đang chạy ở đâu

```sql
SELECT inst_id,
       name,
       network_name
FROM gv$active_services
WHERE name = 'sales_app'
   OR network_name LIKE '%sales_app%'
ORDER BY inst_id;
```

### Bước 3: Kiểm tra kết nối của ứng dụng

```sql
SELECT inst_id,
       service_name,
       COUNT(*) AS sessions
FROM gv$session
WHERE type = 'USER'
GROUP BY inst_id, service_name
ORDER BY inst_id, service_name;
```

### Bước 4: Quan sát global cache waits

```sql
SELECT inst_id,
       event,
       total_waits,
       time_waited_micro
FROM gv$system_event
WHERE event LIKE 'gc%'
ORDER BY inst_id, time_waited_micro DESC;
```

### Bước 5: Thực hiện workload đại diện

Chạy các giao dịch cùng loại trên cả hai instance, ghi lại SQL ID, service, wait event, logical reads và elapsed time. So sánh khi workload được phân tán và khi được định tuyến có affinity phù hợp. Không tạo tải thử nghiệm trên production nếu chưa có kế hoạch và giới hạn an toàn.

### Bước 6: Đánh giá

- Session có được phân phối như mong đợi không?
- Global cache wait có tăng khi hai instance cùng sửa một tập dữ liệu nóng không?
- Interconnect có latency hoặc throughput bất thường không?
- SQL có tạo nhiều block access hoặc index hot spot không?
- Service placement có thể cải thiện locality mà không làm node mất cân bằng không?

## 18. Những nhầm lẫn cần tránh

| Nhầm lẫn | Cách hiểu đúng |
|---|---|
| RAC là nhiều database đồng bộ với nhau | RAC là nhiều instance cùng mở một database |
| Các instance dùng chung SGA | Mỗi instance có SGA và process riêng |
| Cache Fusion là disk replication | Cache Fusion truyền block giữa buffer cache qua interconnect |
| Có shared storage là đủ để chạy RAC | Cần Grid Infrastructure, cluster membership, interconnect và cơ chế global coordination |
| RAC bảo đảm session không bao giờ bị ngắt | Session trên node lỗi có thể mất; reconnect/replay phụ thuộc client/service và ứng dụng |
| Thêm node luôn tăng hiệu năng tuyến tính | Global cache traffic, hot block, CPU và storage có thể giới hạn scalability |
| Ít physical read nghĩa là RAC không có bottleneck | Global cache waits có thể cao dù disk I/O thấp |
| SCAN là load balancer cho từng SQL statement | SCAN hỗ trợ định tuyến kết nối; session vẫn gắn với instance đã kết nối |
| Sequence trong RAC luôn tăng theo thứ tự commit | Sequence đảm bảo giá trị theo quy tắc sequence, không bảo đảm thứ tự commit và có thể có gap |
| RAC thay thế Data Guard | RAC xử lý HA/scale trong cluster; Data Guard cung cấp standby/DR ở database/site khác |
| Mọi `gc%` wait đều là lỗi | Cần xem latency, tổng thời gian, SQL, object và workload trước khi kết luận |

Oracle RAC kết hợp nhiều instance với một database dùng chung để tăng khả năng sẵn sàng và phân phối workload. Mỗi instance có bộ nhớ và process riêng, còn các instance phối hợp qua Clusterware, GCS/GES và interconnect. Cache Fusion truyền block giữa buffer cache để duy trì tính nhất quán mà không phải luôn đọc lại từ storage. Hiệu năng RAC phụ thuộc không chỉ vào số node mà còn vào locality của dữ liệu, thiết kế service, SQL, index, interconnect và cách ứng dụng xử lý kết nối khi có sự cố.
