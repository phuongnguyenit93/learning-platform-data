# Đối chiếu RAC, Data Guard và Active Data Guard với edition và giấy phép Oracle

Oracle RAC, Oracle Data Guard và Oracle Active Data Guard đều hỗ trợ tính sẵn sàng cao, nhưng giải quyết các bài toán khác nhau. RAC cho nhiều instance cùng truy cập một database dùng chung để duy trì dịch vụ khi một instance/node gặp sự cố. Data Guard duy trì một hoặc nhiều standby database riêng, nhận và áp dụng redo từ primary để phục hồi khi site hoặc database chính gặp sự cố. Active Data Guard bổ sung khả năng mở physical standby cho truy vấn read-only trong khi Redo Apply vẫn tiếp tục chạy, nhờ đó vừa bảo vệ DR vừa có thể offload một số workload đọc.

Các công nghệ này không thay thế hoàn toàn cho nhau. RAC không bảo vệ đầy đủ trước lỗi storage/site hoặc thao tác logic sai được ghi vào cùng database; Data Guard có thể cung cấp bản sao ở failure domain khác. Active Data Guard thêm khả năng truy vấn standby nhưng có yêu cầu license riêng. Một kiến trúc có thể kết hợp RAC ở primary với Data Guard/Active Data Guard ở site dự phòng.

Khi lựa chọn, cần trả lời ba câu hỏi riêng:

1. **Failure domain nào cần bảo vệ?** Instance, node, storage, database, site hay lỗi logic?
2. **Workload nào cần phục vụ?** Giao dịch đọc/ghi, truy vấn read-only trên standby, reporting hay disaster recovery?
3. **Edition và entitlement nào bao phủ triển khai?** Oracle Database edition, RAC option, Active Data Guard option, metric Processor/Named User Plus, standby/failover rights và hợp đồng cụ thể.

Không kết luận rằng một tính năng được hỗ trợ kỹ thuật đồng nghĩa tổ chức đã có quyền sử dụng thương mại. Quyền sử dụng phụ thuộc phiên bản, edition, option, license metric, phần cứng, số node/server, môi trường standby và các tài liệu đặt hàng/hợp đồng đang có hiệu lực. Trước khi triển khai production, đối chiếu Oracle Licensing Information User Manual của đúng release, Oracle price list/contract và xác nhận với License Management/Oracle khi có điểm chưa rõ.

Bài học thuộc chủ đề **Sẵn sàng cao** của *Database Engine Relational Oracle*. Nội dung tập trung vào:

- Kiến trúc và failure domain của RAC, Data Guard, Active Data Guard.
- So sánh HA, DR, RPO/RTO, read scaling và giới hạn từng giải pháp.
- Basic Data Guard so với Active Data Guard real-time query.
- Edition và option: Enterprise Edition, Standard Edition 2, RAC option, Active Data Guard option.
- License metric Processor và Named User Plus.
- Quyền sử dụng standby, failover, RAC node và DR site.
- Kịch bản kết hợp RAC + Data Guard.
- Ma trận lựa chọn theo yêu cầu nghiệp vụ.
- Kiểm tra entitlement, giám sát, diễn tập và lỗi triển khai thường gặp.

## 1. Phân biệt HA, DR và read scaling

### High Availability (HA)

High Availability hướng tới giảm thời gian dịch vụ không thể sử dụng khi một thành phần lỗi. Thiết kế HA có thể dùng redundancy, cluster, failover, connection retry và monitoring để chuyển workload sang thành phần còn hoạt động.

Ví dụ:

- Một Oracle instance bị crash nhưng instance khác vẫn phục vụ cùng database.
- Node database bị lỗi, service chuyển sang node còn lại.
- Session được reconnect/replay theo khả năng của application/driver.

HA không có nghĩa mọi transaction đang chạy đều được tiếp tục nguyên trạng. Session có thể mất, transaction chưa commit có thể rollback, client phải retry và cần bảo đảm idempotency.

### Disaster Recovery (DR)

DR hướng tới phục hồi dịch vụ sau sự cố lớn như mất site, storage, database hoặc lỗi làm primary không thể tiếp tục hoạt động. DR thường cần bản sao dữ liệu ở failure domain khác, quy trình failover, DNS/service routing và kế hoạch đưa hệ thống về trạng thái bình thường.

Các câu hỏi chính:

- Standby có nhận đủ redo đến đâu?
- RPO có thể là zero hay chấp nhận mất một khoảng dữ liệu?
- Failover tự động hay cần quyết định thủ công?
- RTO gồm phát hiện lỗi, quyết định failover, mount/open và chuyển kết nối mất bao lâu?
- Có khả năng failback/switchover về site chính không?

### Read scaling

Read scaling phân phối workload đọc sang nhiều tài nguyên để giảm tải primary hoặc tăng năng lực truy vấn. RAC có thể phục vụ workload trên nhiều instance cùng database; Active Data Guard có thể offload truy vấn read-only sang physical standby trong khi apply redo tiếp tục.

Read scaling cần xét tính nhất quán và độ trễ dữ liệu. Một báo cáo chạy trên standby có thể đọc dữ liệu trễ hơn primary nếu apply lag khác zero. Không dùng read-only standby cho nghiệp vụ yêu cầu đọc-after-write tức thì nếu chưa có cơ chế bảo đảm phù hợp.

### RPO và RTO

- **RPO (Recovery Point Objective):** lượng dữ liệu tối đa tổ chức chấp nhận mất, thường biểu diễn bằng thời gian hoặc điểm dữ liệu.
- **RTO (Recovery Time Objective):** thời gian tối đa để khôi phục dịch vụ sau sự cố.

RAC thường giảm downtime do lỗi instance/node trong cùng cluster, với database files vẫn sẵn sàng trên shared storage. Data Guard bảo vệ trước failure domain rộng hơn bằng standby database. Active Data Guard bổ sung truy vấn standby trong trạng thái apply.

RPO/RTO thực tế phụ thuộc kiến trúc, transport mode, apply lag, automation, detection, application reconnect và diễn tập. Không có sản phẩm nào tự bảo đảm RPO/RTO chỉ bằng việc cài đặt.

## 2. Oracle RAC là gì?

Oracle Real Application Clusters (RAC) cho phép nhiều database instances trên các node khác nhau cùng truy cập một database dùng chung. Các instance có buffer cache riêng nhưng chia sẻ datafiles, control files và online redo theo kiến trúc cluster/storage được hỗ trợ.

### Kiến trúc khái quát

~~~text
             Applications / Services
                /             \
               /               \
        RAC Node 1            RAC Node 2
        Instance 1            Instance 2
        SGA / Buffer Cache    SGA / Buffer Cache
               \               /
                \             /
             Shared Database Storage
       Datafiles / Control Files / Redo / ASM
~~~

Oracle Clusterware quản lý cluster resources, membership, voting/OCR và database services theo cấu hình. ASM thường được dùng để quản lý storage nhưng kiến trúc cụ thể có thể khác theo môi trường.

### RAC bảo vệ điều gì?

- Instance failure: instance còn lại có thể tiếp tục phục vụ service theo cấu hình.
- Node failure: workload có thể được chuyển sang node còn hoạt động.
- Bảo trì node: một số thao tác có thể thực hiện rolling nếu kiến trúc/phiên bản hỗ trợ.
- Scale-out: nhiều instance có thể tăng năng lực xử lý workload phù hợp.

### RAC không tự bảo vệ điều gì?

- Mất toàn bộ shared storage hoặc failure domain dùng chung.
- Hỏng dữ liệu logic do DELETE/UPDATE sai được commit vào database dùng chung.
- Corruption được lan truyền qua cùng database hoặc storage.
- Mất toàn bộ site nếu không có bản sao ở site khác.
- Application không xử lý session loss, transaction rollback hoặc retry.

RAC là một database với nhiều instance, không phải hai database độc lập. Vì vậy, thay đổi dữ liệu trên instance này được nhìn thấy qua database chung trên instance khác.

### Services và client failover

RAC dùng database services để phân phối kết nối. Application cần kết nối bằng service name và driver/configuration hỗ trợ failover/reconnect phù hợp. Các khả năng như Fast Application Notification (FAN), Fast Connection Failover (FCF), Application Continuity hoặc Transparent Application Continuity phụ thuộc driver, edition/option và cấu hình; không giả định chúng tự hoạt động chỉ vì đã cài RAC.

### RAC và transaction

Khi một node lỗi:

- Session gắn với node đó có thể bị ngắt.
- Transaction chưa commit có thể cần rollback/recovery.
- Instance còn lại có thể thực hiện cache recovery/instance recovery theo kiến trúc.
- Client phải reconnect/retry theo cơ chế ứng dụng.

RAC cải thiện availability nhưng không bảo đảm mọi request không bị gián đoạn.

## 3. Oracle Data Guard là gì?

Oracle Data Guard duy trì một hoặc nhiều standby databases để bảo vệ primary database. Primary gửi redo tới standby; standby nhận redo và có thể áp dụng redo để đồng bộ dữ liệu.

### Kiến trúc cơ bản

~~~text
          Primary Database
             LGWR/ARCH
                 |
           Redo Transport
                 |
        Network / WAN / Site link
                 |
           Standby Database
        Standby Redo Logs (SRL)
                 |
             Redo Apply
                 |
          Standby Datafiles
~~~

### Physical standby

Physical standby duy trì bản sao block-level của primary thông qua redo apply. Cấu trúc vật lý của datafiles về cơ bản tương ứng với primary. Đây là lựa chọn phổ biến cho DR và là nền tảng để dùng Active Data Guard real-time query.

### Logical standby

Logical standby áp dụng SQL tương đương từ redo thay vì duy trì bản sao block-level giống hệt. Nó có thể cho phép một số khác biệt cấu trúc và workload trên standby, nhưng có giới hạn datatype/object và yêu cầu kiểm thử tương thích. Không phải mọi schema/object đều được hỗ trợ như nhau.

### Snapshot standby

Snapshot standby chuyển physical standby thành database có thể đọc/ghi tạm thời cho kiểm thử. Trong thời gian đó redo apply bị dừng; khi chuyển lại physical standby, các thay đổi local bị loại bỏ và redo được apply tiếp theo quy trình. Snapshot standby không phải nơi chạy production write workload lâu dài.

### Redo transport và apply

- Redo transport gửi redo từ primary tới standby.
- Standby redo logs (SRL) nhận redo khi cấu hình phù hợp.
- Redo Apply áp dụng redo lên physical standby.
- Archive log và transport/apply services duy trì chuỗi đồng bộ.

Theo dõi transport lag và apply lag để biết standby đang trễ bao nhiêu. Một standby tồn tại nhưng không nhận/apply redo đúng cách không đáp ứng DR objective.

### Switchover và failover

- **Switchover:** chuyển role có kế hoạch, thường không mất dữ liệu nếu điều kiện đồng bộ đáp ứng.
- **Failover:** chuyển standby thành primary khi primary không thể tiếp tục; có thể mất dữ liệu tùy protection mode/redo đã nhận.
- **Reinstate:** đưa primary cũ trở lại thành standby nếu điều kiện và công cụ hỗ trợ.

Data Guard Broker có thể đơn giản hóa quản lý configuration, switchover/failover và monitoring. Fast-Start Failover (FSFO) có thể tự động failover theo điều kiện observer/broker; vẫn cần thiết kế quorum, observer placement, thresholds và fencing để tránh split-brain.

## 4. Active Data Guard là gì?

Active Data Guard là option mở rộng Data Guard. Khả năng thường được nhắc đến nhiều nhất là **real-time query**: mở physical standby ở chế độ read-only trong khi Redo Apply vẫn chạy. Nhờ vậy, standby vừa tiếp tục đồng bộ redo vừa phục vụ một số truy vấn đọc/reporting.

### Basic Data Guard và Active Data Guard

| Khả năng | Data Guard cơ bản | Active Data Guard |
| --- | --- | --- |
| Physical standby nhận redo | Có | Có |
| Redo Apply trên standby | Có | Có |
| Mở physical standby read-only trong lúc apply vẫn hoạt động | Không phải khả năng real-time query được cấp trong Data Guard cơ bản | Có, với Active Data Guard real-time query |
| Dừng apply rồi mở read-only để kiểm tra | Có thể theo quy trình, nhưng apply phải dừng | Có; đồng thời có thể hỗ trợ read-only query trong khi apply tiếp tục |
| Offload reporting gần real-time | Giới hạn do apply phải dừng khi mở read-only theo cách cơ bản | Có, tùy apply lag, workload và cấu hình |

Điểm phân biệt quan trọng là trạng thái đồng thời. Với Data Guard cơ bản, physical standby có thể được mở read-only trong một số quy trình nhưng Redo Apply không tiếp tục đồng thời theo mô hình Active Data Guard. Active Data Guard cho phép read-only query khi apply vẫn chạy.

### Real-time query

Physical standby có thể phục vụ truy vấn read-only trong lúc nhận và apply redo. Query nhìn thấy dữ liệu theo read-consistency của standby; nếu apply lag khác zero, kết quả có thể trễ so với primary.

Ứng dụng cần biết:

- Query chạy trên standby hay primary.
- Standby apply lag và transport lag hiện tại.
- Có chấp nhận eventual/near-real-time data không.
- Có yêu cầu read-after-write ngay sau transaction primary không.
- Query có gây cạnh tranh CPU/I/O với redo apply không.

### Một số khả năng khác của Active Data Guard

Active Data Guard option có thể bao gồm các khả năng nâng cao khác tùy phiên bản, chẳng hạn automatic block repair, Far Sync và một số tính năng bảo vệ/availability liên quan. Không suy rộng danh sách từ một release sang release khác; kiểm tra Oracle Licensing Information User Manual và tài liệu feature matrix đúng phiên bản.

### Active Data Guard không phải RAC

Active Data Guard read-only query chạy trên một standby database riêng, thường ở site hoặc failure domain khác. Nó không biến standby thành instance thứ hai cùng ghi một database như RAC. Standby physical database vẫn áp dụng redo theo cơ chế Data Guard và có giới hạn về thao tác ghi.

## 5. Data Guard protection modes và RPO

Data Guard có các protection modes xác định cách primary chờ redo được chuyển tới standby. Chọn mode là quyết định giữa data protection, latency và khả năng tiếp tục giao dịch khi standby/network gặp sự cố.

| Protection mode | Redo transport điển hình | Mục tiêu | Trade-off |
| --- | --- | --- | --- |
| Maximum Protection | Synchronous transport với xác nhận ghi redo theo cấu hình bảo vệ | Không mất dữ liệu đã commit trong điều kiện cấu hình bảo vệ được duy trì | Nếu không còn standby đồng bộ đáp ứng, primary có thể dừng để tránh mất dữ liệu |
| Maximum Availability | Synchronous transport; primary tiếp tục hoạt động khi điều kiện standby tạm thời không đáp ứng theo cơ chế mode | Zero data loss khi standby đồng bộ sẵn sàng; ưu tiên availability khi standby mất kết nối | Có thể chuyển sang chế độ ít bảo vệ hơn khi lỗi, tùy trạng thái |
| Maximum Performance | Thường dùng asynchronous transport | Ưu tiên hiệu năng primary; RPO phụ thuộc redo chưa truyền | Có thể mất redo chưa tới standby khi primary/site mất đột ngột |

Tên transport attributes, SYNC/ASYNC, AFFIRM/NOAFFIRM và hành vi cụ thể phụ thuộc cấu hình/version. Cần thiết kế đúng theo Oracle documentation và test failure scenarios.

### SYNC và ASYNC

- SYNC yêu cầu primary chờ phản hồi từ standby theo chế độ cấu hình trước khi hoàn tất một số commit path; có thể tăng transaction latency theo network/storage latency.
- ASYNC gửi redo bất đồng bộ, giảm ảnh hưởng latency trên primary nhưng có thể có redo gap nếu primary mất trước khi redo được chuyển.

Không chỉ nhìn protection mode trong V$DATABASE. Cần kiểm tra transport destination attributes, standby redo logs, network, apply process và protection level thực tế.

### Kiểm tra protection mode và level

~~~sql
SELECT protection_mode,
       protection_level,
       database_role,
       switchover_status
FROM v$database;
~~~

PROTECTION_MODE là mode được cấu hình; PROTECTION_LEVEL phản ánh mức bảo vệ đang đạt được tại thời điểm quan sát. Hai giá trị có thể khác nhau nếu standby/destination không đáp ứng.

### Transport lag và apply lag

~~~sql
SELECT name, value, unit, time_computed, datum_time
FROM v$dataguard_stats
WHERE name IN ('transport lag', 'apply lag', 'apply finish time');
~~~

Lag cần được theo dõi liên tục, không chỉ khi diễn tập. Một giá trị lag nhỏ tại một thời điểm không bảo đảm standby luôn đạt RPO.

## 6. So sánh RAC, Data Guard và Active Data Guard

| Tiêu chí | RAC | Data Guard cơ bản | Active Data Guard |
| --- | --- | --- | --- |
| Kiến trúc | Nhiều instance cùng một database | Primary và standby database riêng | Primary và physical standby riêng |
| Failure domain | Instance/node trong cluster | Database/site/storage theo kiến trúc standby | Tương tự Data Guard |
| Storage | Thường shared storage/ASM cho database | Storage độc lập cho standby | Storage độc lập cho standby |
| Primary read/write | Có trên các instance theo cấu hình | Có ở primary | Có ở primary |
| Standby read-only khi redo apply đang chạy | Không áp dụng | Không theo real-time query option | Có |
| Bảo vệ mất site | Không tự cung cấp | Có nếu standby ở site khác | Có nếu standby ở site khác |
| Offload reporting | Có thể phân phối workload giữa instances, nhưng cùng database | Standby read-only theo giới hạn apply pause | Có thể offload read-only gần real-time |
| RPO | Không có redo transport sang database riêng; crash recovery dùng database chung | Phụ thuộc sync/async và redo gap | Phụ thuộc Data Guard transport/apply như Data Guard |
| RTO | Thường nhanh cho instance/node failover nếu cluster còn khỏe | Phụ thuộc detection, role transition, mount/open và app reconnect | Tương tự Data Guard |
| Lỗi logic được commit | Lan tới database chung | Redo cũng có thể truyền sang standby; cần chiến lược bảo vệ logic/restore point | Tương tự Data Guard |
| License chính | RAC option hoặc quyền SE2 theo giới hạn phiên bản | Enterprise Edition Data Guard entitlement theo release | Enterprise Edition + Active Data Guard option theo entitlement |

### Kết luận theo failure domain

- Cần tiếp tục phục vụ khi một instance/node lỗi trong cùng site: RAC phù hợp.
- Cần standby độc lập để phục hồi khi primary/site lỗi: Data Guard phù hợp.
- Cần chạy báo cáo trên physical standby trong khi apply vẫn tiếp tục: Active Data Guard phù hợp nếu có license option.
- Cần cả HA cục bộ và DR site: kết hợp RAC ở primary/standby với Data Guard.

### Cùng tồn tại trong một kiến trúc

~~~text
       Primary Site                         DR Site
   +------------------+                +------------------+
   | RAC Node 1       |                | RAC Node 3       |
   | RAC Node 2       | -- Redo -----> | RAC Node 4       |
   | Primary Database |                | Physical Standby |
   +------------------+                +------------------+
        |                                      |
   App Services                         Read-only reports
                                        (Active DG option)
~~~

RAC bảo vệ node/instance trong từng site; Data Guard bảo vệ giữa các database/site; Active Data Guard cho phép workload đọc trên standby trong lúc redo apply. Mỗi lớp cần license, hạ tầng, monitoring và quy trình riêng.

## 7. Edition và option: cần phân biệt những lớp nào?

Oracle Database software có edition, options và management packs. Chúng là các lớp entitlement khác nhau:

- **Edition** xác định bộ tính năng nền tảng của database product, ví dụ Standard Edition 2 hoặc Enterprise Edition.
- **Database option** là tính năng bổ sung được cấp license riêng trên edition hỗ trợ, ví dụ Oracle RAC option hoặc Active Data Guard option.
- **Management pack** là nhóm công cụ quản trị/giám sát có entitlement riêng, ví dụ Diagnostics Pack và Tuning Pack.
- **License metric** xác định cách tính số license phải mua, ví dụ Processor hoặc Named User Plus.
- **Contract/order documents** xác định quyền sử dụng cụ thể của tổ chức, discount, metric, số lượng, site và các điều khoản đặc biệt.

Một feature có thể xuất hiện trong software binary hoặc dictionary views nhưng điều đó không chứng minh tổ chức đã có entitlement để sử dụng. Ngược lại, edition/option được mua phải được triển khai đúng version và điều kiện hợp đồng.

## 8. Enterprise Edition, Standard Edition 2 và RAC

### Enterprise Edition (EE)

Enterprise Edition là nền tảng cho các kiến trúc HA/DR nâng cao. Tuy nhiên, không nên hiểu rằng mua EE mặc nhiên bao gồm mọi option:

- Oracle RAC cho Enterprise Edition là option có license riêng theo Oracle licensing model.
- Active Data Guard là option có license riêng.
- Basic Data Guard có entitlement gắn với Enterprise Edition theo licensing documentation của các release phổ biến; vẫn phải xác nhận release và contract.
- Một số tính năng khác như Partitioning, Advanced Compression, Diagnostics Pack, Tuning Pack hoặc các option khác cũng có entitlement riêng.

### Standard Edition 2 (SE2)

SE2 có giới hạn kỹ thuật và licensing khác EE. Trong các release SE2 phổ biến (đặc biệt 12.1.0.2/12.2/18c/19c), Oracle RAC được bao gồm trong SE2 nhưng có giới hạn về số socket/CPU threads và số node của cluster. Quy định chi tiết thay đổi theo release/platform và cần kiểm tra Licensing Information User Manual tương ứng.

Một số giới hạn thường gặp trong tài liệu SE2 của các release trước đây:

- Tối đa hai CPU sockets trên mỗi server theo định nghĩa Oracle.
- Giới hạn CPU threads mà mỗi database instance có thể sử dụng.
- RAC cluster giới hạn số node (thường tối đa hai node trong các release được đề cập).

Không lấy con số của một release làm quy tắc chung cho release mới. Cần kiểm tra tài liệu license đúng phiên bản và cấu hình máy chủ.

### Data Guard với SE2

Không giả định SE2 có cùng entitlement Data Guard như Enterprise Edition. Oracle Data Guard feature availability/entitlement gắn với Enterprise Edition trong các licensing guides phổ biến; Standard Edition 2 không nên được xem là có quyền dùng Data Guard chỉ vì có thể triển khai một số cơ chế replication khác.

Nếu cần DR với SE2, đánh giá các giải pháp được Oracle hỗ trợ và cấp phép cho đúng release, chẳng hạn backup/restore, storage replication hoặc công nghệ replication riêng có entitlement phù hợp. Không gọi một bản sao storage là Data Guard nếu không chạy Data Guard feature.

### Kiểm tra edition từ database

~~~sql
SELECT banner
FROM v$version;

SELECT parameter, value
FROM v$option
WHERE parameter IN ('Real Application Clusters');
~~~

V$OPTION cho biết một số option có được enable trong binary/configuration, nhưng không xác nhận license đã mua. Edition cũng cần được đối chiếu qua banner, registry/inventory và contract. Không dùng V$OPTION như bằng chứng pháp lý về entitlement.

## 9. Oracle RAC option và license metric

### RAC trên Enterprise Edition

Oracle RAC option thường cần được cấp phép trên các server/processor nơi RAC được cài đặt hoặc sử dụng theo licensing rules. Khi cluster có nhiều node, không chỉ tính node đang nhận workload ở thời điểm kiểm tra; cần xem phạm vi cài đặt, cấu hình failover và quyền trong hợp đồng.

### RAC trong SE2

RAC có thể nằm trong quyền SE2 với giới hạn cụ thể của release. Nếu vượt giới hạn socket/thread/node hoặc dùng tính năng không được SE2 hỗ trợ, có thể cần chuyển edition/kiến trúc và license khác. Không suy luận rằng mọi RAC cluster hai node đều hợp lệ chỉ vì số node đúng; còn giới hạn phần cứng và version.

### Processor metric

Processor metric thường dựa trên số processor cores theo định nghĩa Oracle và Core Factor Table, cộng với quy tắc tối thiểu/điều kiện của hợp đồng. Cách tính có thể khác giữa kiến trúc chip, platform và contract.

Ví dụ công thức khái quát thường được dùng khi tính Processor license:

\[
\text{Processor licenses}
=
\text{Cores} \times \text{Core Factor}
\]

Đây chỉ là mô hình minh họa. Phải áp dụng Core Factor Table hiện hành và các điều khoản cụ thể; không tự dùng một hệ số mặc định.

### Named User Plus (NUP)

NUP tính theo số người dùng/thiết bị được phép truy cập software theo định nghĩa hợp đồng, có minimums theo Processor và các quy tắc riêng. Với connection pool, application account hoặc user gián tiếp, không mặc định số database accounts bằng số NUP. Cần xác định mọi người dùng/thiết bị truy cập trực tiếp hoặc gián tiếp theo licensing rules.

### License RAC ở đâu?

RAC có thể làm tăng license footprint vì option phải được cấp phép cho các server/processor nằm trong phạm vi sử dụng option. Trong cluster, đánh giá tất cả node nơi RAC option được cài/enable/used theo quy tắc hợp đồng, không chỉ node primary hoặc node đang chạy service.

## 10. Data Guard cơ bản và Active Data Guard option

### Basic Data Guard

Basic Data Guard được cung cấp trong Enterprise Edition theo licensing documentation của nhiều release, không phải một option trả phí riêng như Active Data Guard. Tuy nhiên, entitlement cho standby server, failover use, số standby, hardware và cách vận hành vẫn phải đọc trong license agreement/order documents.

Không nên diễn giải câu “Data Guard included with EE” thành “mọi standby server và mọi tính năng standby đều miễn phí”. Database software trên standby, failover rights, usage restrictions và các option khác có thể chịu điều kiện license riêng.

### Active Data Guard option

Active Data Guard là option có license riêng bên cạnh Enterprise Edition. Khi sử dụng các tính năng thuộc option, đặc biệt real-time query trên physical standby trong lúc Redo Apply vẫn hoạt động, phải có entitlement phù hợp.

Tùy release, Active Data Guard option có thể bao gồm các khả năng bổ sung như automatic block repair, Far Sync và các feature được liệt kê trong Licensing Information User Manual. Danh sách feature và điều kiện cấp phép cần được xác nhận theo version.

### License ở primary và standby

Không tự giả định chỉ cần mua Active Data Guard cho standby hoặc chỉ cho primary. Việc cấp license option phụ thuộc cách feature được triển khai/sử dụng, các server chạy database/option, metric và điều khoản Oracle áp dụng cho standby/DR. Kiểm tra chính xác license guide và hợp đồng của tổ chức trước khi chốt số lượng.

### Read-only standby không tự động đồng nghĩa Active Data Guard

Có thể mở physical standby read-only trong một số quy trình Data Guard cơ bản khi Redo Apply dừng. Hành vi này khác real-time query trong khi apply vẫn chạy. Chỉ vì standby mở READ ONLY không đủ để kết luận đã dùng Active Data Guard; trạng thái apply và feature thực tế mới là yếu tố cần xét.

## 11. Standby, failover và quyền sử dụng license

Standby licensing là phần dễ hiểu nhầm nhất. Có nhiều tình huống:

- Physical standby nhận/apply redo liên tục.
- Standby chỉ dùng cho DR và không phục vụ workload đọc.
- Standby được mở read-only để báo cáo.
- Standby được dùng cho backup hoặc testing.
- Standby được kích hoạt thành primary khi failover.
- Primary cũ được reinstated thành standby.
- Một cluster có nhiều node/instance ở cả hai site.

Mỗi tình huống có thể tác động tới license requirement khác nhau.

### Failover rule không phải quyền miễn phí chung

Oracle có các chính sách failover server trong một số license agreements/guides, thường được diễn giải theo giới hạn số ngày failover trong năm và số failover nodes. Điều kiện chính xác phụ thuộc tài liệu và hợp đồng áp dụng; không được tự suy ra mọi Data Guard standby đều được chạy không license.

### Active Data Guard và standby usage

Khi standby chạy real-time query, reporting hoặc feature thuộc Active Data Guard, cần kiểm tra option license cho các server liên quan. Đừng dựa vào lập luận rằng standby “chỉ là DR” nếu trên thực tế đang phục vụ workload đọc hoặc chạy tính năng option.

### Backup trên standby

Việc offload RMAN backup sang standby có thể có quyền/điều kiện khác với việc chạy Active Data Guard real-time query. Không suy ra backup offload đồng nghĩa phải có hoặc không cần Active Data Guard option. Kiểm tra đúng feature matrix và license guide của release.

### Test và development

Standby dùng cho testing, QA, UAT hoặc reporting có thể không còn chỉ là passive failover environment. Xác định mục đích sử dụng, thời lượng, user access, option enabled và license metric. Các quyền disaster recovery không tự động bao phủ mọi môi trường test.

## 12. Tính license footprint cho kiến trúc HA/DR

Để tính entitlement, cần lập inventory theo từng database/server/site. Không chỉ đếm số database instances.

### Thông tin cần thu thập

- Oracle Database release, edition và patch level.
- Oracle Home, option installed/used và database services.
- Hostname, physical/virtual server, CPU sockets, cores và Core Factor.
- Processor hoặc NUP metric trong contract.
- Số node RAC và instance trên mỗi node.
- Primary/standby role và nơi đặt standby.
- Active Data Guard real-time query, Far Sync hoặc feature option khác có sử dụng không.
- Backup/reporting/testing workload chạy ở standby.
- Failover policy, số ngày sử dụng standby và điều khoản DR.
- Các option/management packs khác được bật hoặc sử dụng.

### Bảng inventory minh họa

| Site | Server | Role | Edition | RAC | Data Guard | Active DG usage | Metric/quantity |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Primary | db01 | Primary node 1 | EE | RAC | Primary | Không | Theo contract |
| Primary | db02 | Primary node 2 | EE | RAC | Primary | Không | Theo contract |
| DR | db03 | Physical standby | EE | RAC/Single | Standby | Read-only query | Theo contract |
| DR | db04 | Physical standby node 2 | EE | RAC/Single | Standby | Read-only query | Theo contract |

Đây chỉ là form inventory; không phải kết luận server nào cần bao nhiêu license. Điền metric, option usage và failover rights theo hợp đồng.

### Processor metric và Core Factor

Nếu contract dùng Processor metric, cần tính số core thuộc phạm vi Oracle software theo quy tắc Oracle và áp dụng Core Factor Table phù hợp. Các yếu tố cần xác minh:

- CPU model và số core/socket.
- Hyper-threading có được tính như core không theo metric hiện hành.
- Virtualization/hard partitioning policy và cách Oracle công nhận partition.
- Core Factor Table version.
- Minimums và điều khoản đặc biệt.
- Node standby/failover có được miễn/giảm trong điều kiện cụ thể không.

Không dùng số vCPU của VM làm con số license cuối cùng nếu chưa xác nhận Oracle partitioning policy. Soft partitioning thường không tự giới hạn license footprint theo cách nhiều tổ chức mong muốn.

### Named User Plus

Với NUP, inventory cần xác định người dùng và thiết bị được phép truy cập, kể cả truy cập gián tiếp qua ứng dụng, middleware, batch hoặc service account theo quy tắc NUP. NUP có minimums theo Processor và không thể chỉ đếm số user trong DBA_USERS.

### Option license gắn với server/processor

Option như RAC hoặc Active Data Guard có thể yêu cầu entitlement riêng theo server/processor nơi option được cài đặt hoặc sử dụng. Không giả định mua EE ở primary đã tự động cấp RAC/Active DG ở mọi server trong DR site.

### Virtualization, cloud và engineered systems

Quy tắc license trên VMware, Hyper-V, cloud IaaS, OCI, Exadata và các engineered systems có thể khác nhau. Đặc biệt, phạm vi host/cluster mà Oracle xem là có thể chạy software ảnh hưởng cách tính Processor. Dùng Oracle licensing policy đúng môi trường và contract; không lấy cách tính của bare metal áp vào VM/cloud.

## 13. Kiểm tra kỹ thuật không thay thế kiểm tra license

DBA có thể kiểm tra database đang chạy edition/option nào và feature nào đang được sử dụng. Những truy vấn này giúp inventory kỹ thuật, nhưng không xác nhận entitlement thương mại.

### Kiểm tra phiên bản và edition

~~~sql
SELECT banner
FROM v$version;

SELECT product, version, status
FROM product_component_version;
~~~

### Kiểm tra option enablement

~~~sql
SELECT parameter, value
FROM v$option
ORDER BY parameter;
~~~

V$OPTION chỉ cho biết option được enable trong binary/configuration theo cách view thể hiện. Một option có thể enabled nhưng không có license, hoặc license đã mua nhưng feature không được enable ở database hiện tại.

### Kiểm tra RAC runtime

~~~sql
SELECT instance_name,
       host_name,
       thread#,
       status,
       parallel
FROM gv$instance
ORDER BY inst_id;

SELECT name, value
FROM v$parameter
WHERE name IN ('cluster_database', 'cluster_database_instances');
~~~

Trong RAC, GV$ views cung cấp thông tin từ các instances trong cluster nếu query có thể truy cập chúng.

### Kiểm tra Data Guard role và mode

~~~sql
SELECT name,
       db_unique_name,
       database_role,
       open_mode,
       protection_mode,
       protection_level,
       switchover_status
FROM v$database;
~~~

### Kiểm tra Data Guard lag

~~~sql
SELECT name, value, unit, time_computed, datum_time
FROM v$dataguard_stats
ORDER BY name;
~~~

### Kiểm tra database open mode trên standby

~~~sql
SELECT database_role, open_mode
FROM v$database;

SELECT process, status, thread#, sequence#
FROM v$managed_standby;
~~~

V$MANAGED_STANDBY đã deprecated trong một số release mới; dùng V$DATAGUARD_PROCESS theo tài liệu release khi phù hợp. Trạng thái READ ONLY WITH APPLY là dấu hiệu kỹ thuật của Active Data Guard real-time query, nhưng việc license vẫn phải được xác minh riêng.

### Kiểm tra feature usage

DBA_FEATURE_USAGE_STATISTICS hoặc các view feature usage có thể hỗ trợ inventory một số tính năng. Tuy nhiên, số liệu feature usage không phải hợp đồng license, có thể ghi nhận theo cơ chế/độ trễ của Oracle và không phải bằng chứng đầy đủ cho mọi feature. Dùng kết hợp audit, configuration, workload và contract review.

## 14. Kiến trúc kết hợp RAC và Data Guard

Một hệ thống yêu cầu cả local HA và site DR có thể triển khai RAC ở primary site và RAC hoặc single-instance standby ở DR site.

### RAC primary + single-instance physical standby

Ưu điểm:

- Primary có HA giữa các RAC nodes.
- DR site có database độc lập.
- Chi phí RAC option có thể chỉ tập trung ở primary cluster nếu standby không chạy RAC, tùy license requirements.

Trade-off:

- DR failover có thể có capacity thấp hơn primary.
- Khi failover, cần kiểm tra services, instance resources và connection routing.
- License standby và option vẫn phải được xác nhận theo hợp đồng.

### RAC primary + RAC standby

Ưu điểm:

- Cả primary và DR site có khả năng HA nội bộ.
- Có thể giữ cấu hình gần tương đương cho failover.
- Có thể phân phối workload/read workload nếu có Active Data Guard.

Trade-off:

- Hạ tầng, storage, network, Clusterware và vận hành phức tạp hơn.
- RAC option/SE2 restrictions và Active Data Guard option cần đánh giá trên cả hai site.
- Diễn tập role transition, services và node failure phức tạp hơn.

### Single-instance primary + RAC standby

Có thể dùng khi DR cần năng lực/availability khác primary, nhưng không mặc định là lựa chọn tối ưu. Cần đánh giá khả năng chuyển role, parameter compatibility, redo transport, services và licensing của RAC ở standby.

### Data Guard với nhiều standby

Data Guard có thể duy trì nhiều standby theo kiến trúc và release hỗ trợ. Mỗi standby có mục đích riêng: DR, reporting, regional recovery hoặc test. Nhiều standby làm tăng network/storage/monitoring và có thể ảnh hưởng license footprint; không giả định standby thứ hai miễn phí.

## 15. Quyết định chọn công nghệ theo yêu cầu

| Yêu cầu | Giải pháp cần xem xét | Vì sao |
| --- | --- | --- |
| Một node/instance lỗi nhưng database storage vẫn hoạt động | RAC | Nhiều instance cùng database có thể tiếp tục phục vụ. |
| Mất toàn site hoặc shared storage | Data Guard | Standby database độc lập ở failure domain khác. |
| Reporting trên standby trong khi apply redo tiếp tục | Active Data Guard | Real-time query trên physical standby. |
| Tăng read capacity trong cùng site với cùng database | RAC/service distribution hoặc cache/reporting tier | Workload được phân phối nhưng vẫn dùng database chung. |
| Tăng read capacity ở DR site | Active Data Guard | Offload read-only queries sang standby. |
| Zero-data-loss DR | Data Guard Maximum Protection/Maximum Availability với SYNC và hạ tầng phù hợp | Có thể bảo vệ commit theo điều kiện cấu hình, latency và availability. |
| RPO vài giây/phút có thể chấp nhận | Data Guard ASYNC có monitoring/lag policy | Giảm latency primary, chấp nhận redo gap trong một số sự cố. |
| Chỉ cần backup/restore và RTO dài hơn | RMAN + backup strategy | Có thể đủ nếu không cần standby database liên tục. |
| Bảo vệ trước lỗi logic/accidental delete | Backup, Flashback, restore point, logical protection và DR controls | RAC/Data Guard có thể truyền thay đổi sai sang standby. |

### Ma trận câu hỏi thiết kế

Trước khi quyết định, yêu cầu kiến trúc sư/DBA trả lời:

1. Lỗi instance hay node có phải failure chính cần bảo vệ?
2. Shared storage/site có thể mất đồng thời không?
3. RPO là zero hay chấp nhận mất redo chưa truyền?
4. RTO tính từ lúc phát hiện hay từ lúc quyết định failover?
5. Standby có cần mở read-only khi apply đang chạy?
6. Query có thể chấp nhận apply lag bao nhiêu?
7. Primary và standby có cần cùng số node/capacity?
8. Ứng dụng có hỗ trợ reconnect, retry và idempotency?
9. Có đủ license cho edition, RAC/Active DG option, metric và node?
10. Có đội ngũ diễn tập switchover/failover và restore định kỳ?

## 16. Checklist rà soát license trước production

Trước khi mua, mở rộng cluster, bật Active Data Guard hoặc đưa standby vào phục vụ reporting, lập một hồ sơ entitlement.

### Bước 1: xác định release và edition

- Ghi chính xác Oracle Database release, release update và platform.
- Xác định Standard Edition 2 hay Enterprise Edition.
- Xác định Oracle Home, Grid Infrastructure và database home liên quan.
- Đối chiếu giới hạn kỹ thuật của edition trong licensing guide đúng release.

### Bước 2: liệt kê feature thực tế

- RAC instances/nodes và RAC services.
- Data Guard primary/standby configurations.
- Physical, logical hoặc snapshot standby.
- Active Data Guard real-time query.
- Far Sync, automatic block repair hoặc feature option khác.
- Diagnostics/Tuning Packs và các option khác được sử dụng.
- Backup, reporting, test và batch workload trên standby.

### Bước 3: lập inventory server và metric

Ghi host, CPU model, socket, core, VM/hypervisor, cloud/engineered system, Oracle Home, node role và Processor/NUP metric. Nếu dùng virtualization, lưu tài liệu phân vùng CPU và Oracle partitioning policy áp dụng.

### Bước 4: đọc tài liệu license

Đối chiếu tối thiểu:

- Oracle Database Licensing Information User Manual của đúng release.
- Oracle Database Licensing Guide/price list hiện hành.
- Core Factor Table hiện hành nếu dùng Processor metric.
- Ordering document, license certificate, contract và amendments của tổ chức.
- Điều khoản standby, failover, disaster recovery, test/development và cloud.

Tên tài liệu và cách diễn đạt có thể thay đổi theo release. Dùng bản chính thức tương ứng với phần mềm đang chạy và ngày mua.

### Bước 5: lập mapping feature-to-entitlement

| Feature/usage | Edition nền tảng | Option/entitlement cần xác nhận |
| --- | --- | --- |
| RAC trên EE | Enterprise Edition | Oracle RAC option |
| RAC trên SE2 | Standard Edition 2 | Quyền RAC theo SE2 release và giới hạn phần cứng/node |
| Basic Data Guard | Enterprise Edition theo các licensing guides phổ biến | Xác nhận Data Guard và standby/failover terms trong contract |
| Active Data Guard real-time query | Enterprise Edition | Active Data Guard option |
| ASM/Clusterware | Theo Oracle Grid Infrastructure/database architecture | Quyền sử dụng và điều kiện sản phẩm tương ứng |
| AWR/ASH/SQL Tuning Advisor/Real-Time SQL Monitoring | Edition hỗ trợ | Diagnostics Pack/Tuning Pack nếu feature thuộc pack |

Bảng là hướng dẫn định hướng, không phải license quote. Các feature có thể thay đổi entitlement theo release hoặc contract.

### Bước 6: xác nhận standby/failover rights

Đặt câu hỏi cụ thể:

- Standby được dùng thụ động hay chạy read-only workload?
- Có apply redo liên tục trong khi query không?
- Có dùng standby để backup không?
- Có chạy RAC trên standby không?
- Failover được phép bao nhiêu lần/ngày theo điều khoản nào?
- Sau failover, primary cũ có được dùng làm standby và trong bao lâu?
- Có quyền dùng môi trường test/QA clone không?

Yêu cầu License Management hoặc Oracle xác nhận bằng văn bản nếu điều khoản không rõ.

### Bước 7: lưu bằng chứng

Lưu inventory, query output, architecture diagram, license guide version, contract reference, approval và ngày review. Khi thêm node hoặc bật feature, cập nhật hồ sơ trước production rollout.

## 17. Vận hành và giám sát RAC/Data Guard

License chỉ là một phần. Một kiến trúc HA/DR cần vận hành và kiểm thử để chứng minh RPO/RTO.

### RAC monitoring

Theo dõi:

- Clusterware node membership và resource status.
- Database instances và services.
- Interconnect latency/packet loss.
- Cache fusion traffic và global cache waits.
- ASM disk groups, rebalance và storage health.
- Node eviction, instance recovery và service relocation.
- Application reconnect, transaction retry và connection pool.

Ví dụ:

~~~sql
SELECT inst_id, instance_name, host_name, status
FROM gv$instance
ORDER BY inst_id;

SELECT inst_id, name, open_mode, database_role
FROM gv$database
ORDER BY inst_id;
~~~

Các thông tin cluster chi tiết thường cần Grid Infrastructure tools/views như CRSCTL/SRVCTL và ASM views. Dùng đúng Oracle Home và quyền OS.

### Data Guard monitoring

Theo dõi:

- Transport lag và apply lag.
- Redo transport destination status/errors.
- Standby redo log availability.
- Managed recovery process.
- Archive gap và sequence gap.
- Broker configuration/status.
- Protection mode và protection level.
- Observer status nếu dùng FSFO.

Ví dụ:

~~~sql
SELECT name, value, unit, time_computed, datum_time
FROM v$dataguard_stats
WHERE name IN ('transport lag', 'apply lag');

SELECT dest_id, status, error, destination
FROM v$archive_dest_status
ORDER BY dest_id;
~~~

Một số view/cột có thể thay đổi theo release và database role. Với Data Guard Broker, dùng DGMGRL SHOW CONFIGURATION, SHOW DATABASE VERBOSE và VALIDATE DATABASE theo phiên bản.

### Active Data Guard monitoring

Ngoài các metric Data Guard, theo dõi:

- Standby open mode có phải READ ONLY WITH APPLY không.
- Query workload và resource usage trên standby.
- Apply lag trong giờ reporting.
- Query consistency/lag tolerance của ứng dụng.
- Resource Manager plan và giới hạn reporting workload.
- Licensing/feature usage theo entitlement.

### Diễn tập

Diễn tập định kỳ:

- Node/instance failure trong RAC.
- Service relocation và application reconnect.
- Data Guard switchover có kế hoạch.
- Failover khi primary site mất.
- Reinstate primary cũ.
- Mất network/redo transport.
- Apply lag vượt ngưỡng.
- Standby read-only workload gây ảnh hưởng apply.

Ghi RTO/RPO đo được, không chỉ RTO/RPO mục tiêu trên tài liệu.

## 18. Các tình huống thiết kế mẫu

### Ứng dụng OLTP nội bộ, cần HA trong một site

Nếu yêu cầu chủ yếu là tiếp tục phục vụ khi một node/instance lỗi và storage/site vẫn hoạt động, RAC có thể đáp ứng. Cần database edition/option phù hợp, cluster network/storage, services và client failover. Nếu cần DR site, bổ sung Data Guard.

### Hệ thống thanh toán, cần DR với RPO rất thấp

Đánh giá Data Guard synchronous transport và protection mode phù hợp. Đo network round-trip và standby redo write latency. Maximum Protection có thể dừng primary khi không còn standby đáp ứng; Maximum Availability có behavior khác khi standby mất. Chọn theo yêu cầu availability và data loss tolerance, rồi diễn tập.

### Hệ thống báo cáo nặng trên standby

Nếu cần báo cáo trong khi redo apply tiếp tục, đánh giá Active Data Guard. Kiểm tra query có read-only phù hợp, apply lag, workload contention và license option. Nếu chỉ cần báo cáo theo batch và có thể dừng apply trong cửa sổ riêng, Data Guard cơ bản có thể đủ theo quy trình.

### Hệ thống nhỏ dùng SE2

Nếu cần RAC, xác minh giới hạn SE2 của đúng release và server hardware. Nếu yêu cầu Data Guard/Active Data Guard vượt entitlement SE2, cân nhắc EE và option cần thiết hoặc một giải pháp DR khác được cấp phép. Không thiết kế kiến trúc vượt giới hạn edition rồi mới kiểm tra license sau.

### Hai site, vừa HA vừa DR

RAC tại primary và Data Guard sang DR là mẫu phổ biến. Có thể dùng RAC ở standby nếu cần capacity/HA tương đương. Active Data Guard được cân nhắc khi standby cần phục vụ read-only workload trong lúc apply. Mỗi node/site/option phải nằm trong license inventory.

## 19. Những hiểu lầm thường gặp

| Hiểu lầm | Thực tế |
| --- | --- |
| RAC và Data Guard là hai cách gọi cho cluster | RAC nhiều instance cùng một database; Data Guard có primary và standby databases riêng. |
| RAC bảo vệ khi mất toàn site | RAC không tự tạo database copy ở site khác. |
| Data Guard luôn zero data loss | RPO phụ thuộc SYNC/ASYNC, protection mode, network và trạng thái standby. |
| Data Guard cơ bản cho phép query khi apply đang chạy | Real-time query trên physical standby trong khi Redo Apply tiếp tục là khả năng Active Data Guard. |
| Active Data Guard chỉ là mở standby READ ONLY | Điểm phân biệt là read-only query đồng thời với apply; open read-only khi apply dừng là trường hợp khác. |
| Mua Enterprise Edition là có RAC | RAC option cho EE thường cần license riêng. |
| SE2 có thể dùng mọi cấu hình RAC | SE2 RAC có giới hạn theo release về socket, CPU thread và node. |
| Data Guard standby luôn miễn phí license | Standby/failover rights có điều kiện; Active Data Guard option và workload trên standby cần kiểm tra riêng. |
| V$OPTION=TRUE chứng minh đã mua option | V$OPTION chỉ là trạng thái kỹ thuật, không phải bằng chứng entitlement. |
| Có thể dùng standby để reporting vì nó là DR | Reporting có thể làm thay đổi licensing/option requirements và mục đích sử dụng. |
| RAC xử lý được lỗi DELETE nhầm | Thay đổi logic được commit có thể lan tới mọi RAC instance và standby qua redo. |
| Failover không mất transaction | Session/transaction đang chạy có thể bị ngắt; ứng dụng phải xử lý retry và idempotency. |
| Một standby đủ cho mọi mục tiêu DR | Cần xét failure domain, RTO/RPO, backup độc lập và khả năng mất đồng thời primary/standby. |

## 20. Bài thực hành: lập ma trận kiến trúc và license

Bài lab không yêu cầu cài RAC/Data Guard hoặc bật option có license. Mục tiêu là lập inventory từ một kiến trúc giả định và xác định tài liệu cần đối chiếu trước khi triển khai.

### Bước 1: mô tả yêu cầu

Giả sử ứng dụng cần:

- HA khi một database node lỗi.
- DR ở site thứ hai.
- RPO mục tiêu dưới 5 giây.
- RTO mục tiêu dưới 15 phút.
- Báo cáo có thể trễ dữ liệu tối đa 30 giây.
- Primary có workload OLTP đọc/ghi; standby có reporting read-only.

### Bước 2: vẽ kiến trúc

~~~text
Primary Site                         DR Site
-------------                        --------
RAC Node A                           Standby Node C
RAC Node B  ---- Redo Transport ---> Physical Standby
Primary DB                           Redo Apply
Application services                 Read-only reporting
                                     (evaluate Active DG)
~~~

### Bước 3: chọn công nghệ

- RAC xử lý lỗi node/instance tại primary site.
- Data Guard cung cấp standby độc lập ở DR site.
- Nếu reporting phải chạy trong khi apply vẫn hoạt động, đánh giá Active Data Guard option.
- Nếu reporting có thể chấp nhận apply pause/batch window, đánh giá Data Guard cơ bản và lịch vận hành.

### Bước 4: ghi các giả định cần kiểm chứng

| Giả định | Cách xác minh |
| --- | --- |
| Edition hỗ trợ cấu hình RAC dự kiến | Licensing guide đúng release và hardware inventory |
| RAC option đã được mua | Contract/order documents và license inventory |
| Data Guard được hỗ trợ/cấp quyền | Edition matrix và contract |
| Active Data Guard option cần thiết | Xác định real-time query/apply behavior và feature list |
| Standby/failover server có quyền sử dụng | Điều khoản standby/failover và số ngày/usage |
| Processor/NUP đủ | CPU/socket/core/virtualization hoặc user/device inventory |
| RPO < 5 giây đạt được | Transport/apply test trong tải đại diện |
| RTO < 15 phút đạt được | Failover drill đo end-to-end |
| Reporting lag < 30 giây | Apply lag monitor và query test |

### Bước 5: thu thập dữ liệu kỹ thuật

Trên database hiện có, dùng các truy vấn phù hợp:

~~~sql
SELECT banner FROM v$version;

SELECT parameter, value
FROM v$option
WHERE parameter = 'Real Application Clusters';

SELECT name, db_unique_name, database_role,
       open_mode, protection_mode, protection_level
FROM v$database;

SELECT name, value, unit
FROM v$dataguard_stats
WHERE name IN ('transport lag', 'apply lag');
~~~

Đây là inventory kỹ thuật; lưu kết quả cùng host/CPU inventory và license documents.

### Bước 6: lập bảng entitlement

Điền theo contract:

| Server/node | Edition | RAC option | Active DG option | Metric | Entitled quantity | Evidence |
| --- | --- | --- | --- | --- | --- | --- |
| Primary A | ... | ... | ... | ... | ... | ... |
| Primary B | ... | ... | ... | ... | ... | ... |
| DR C | ... | ... | ... | ... | ... | ... |

Không tự điền quantity bằng số CPU nếu chưa áp dụng Core Factor/virtualization rules.

### Bước 7: đưa ra quyết định

Viết quyết định có điều kiện:

- Kiến trúc nào đáp ứng failure domains?
- Cần option nào theo feature được sử dụng?
- Cần mua/điều chỉnh license nào?
- Điều khoản standby/failover nào cần xác nhận?
- Các giả định nào phải kiểm thử trước production?
- RPO/RTO thực tế sau diễn tập là bao nhiêu?

## 21. Câu hỏi tự kiểm tra

1. **RAC giải quyết vấn đề gì?** HA/scale-out ở cấp instance/node khi nhiều instance cùng truy cập một database.
2. **Data Guard giải quyết vấn đề gì?** DR/availability bằng primary và standby database riêng, đồng bộ qua redo.
3. **Active Data Guard khác Data Guard cơ bản ở điểm nào?** Real-time query trên physical standby trong khi Redo Apply vẫn chạy.
4. **RAC có thay thế backup không?** Không; RAC không bảo vệ khỏi lỗi logic, corruption hoặc mất toàn bộ storage.
5. **Data Guard có luôn zero data loss không?** Không; phụ thuộc transport mode, protection mode, network và redo đã nhận.
6. **RPO là gì?** Mức dữ liệu tối đa có thể mất theo mục tiêu recovery.
7. **RTO là gì?** Thời gian tối đa để khôi phục dịch vụ.
8. **Physical standby là gì?** Bản sao standby áp dụng redo ở mức physical blocks.
9. **Logical standby khác physical standby thế nào?** Áp dụng SQL tương đương và có thể có cấu trúc khác trong giới hạn hỗ trợ.
10. **Snapshot standby có tiếp tục apply redo không?** Không trong giai đoạn snapshot standby; apply tiếp tục sau khi chuyển lại physical standby theo quy trình.
11. **Basic Data Guard có real-time query đồng thời apply không?** Không theo entitlement Data Guard cơ bản; đó là khả năng Active Data Guard.
12. **RAC trên EE có option license riêng không?** Có, RAC option thường được cấp phép riêng.
13. **SE2 có bao gồm RAC không?** Các release SE2 phổ biến có quyền RAC với giới hạn cụ thể; phải kiểm tra release và hardware.
14. **SE2 có mặc nhiên bao gồm Data Guard không?** Không nên giả định; Data Guard entitlement gắn với EE trong licensing guides phổ biến.
15. **Active Data Guard có cần license riêng không?** Có, đây là option riêng trên nền Enterprise Edition theo entitlement.
16. **V$OPTION=TRUE có chứng minh đã mua license không?** Không.
17. **Standby có luôn được miễn license không?** Không; phải kiểm tra standby/failover terms, workload và option usage.
18. **Processor metric tính thế nào?** Theo core/socket và Core Factor Table/contract áp dụng.
19. **NUP có thể chỉ đếm database users không?** Không; cần tính người dùng/thiết bị truy cập theo quy tắc NUP, kể cả truy cập gián tiếp.
20. **RAC và Data Guard có thể kết hợp không?** Có; RAC cung cấp HA trong site, Data Guard cung cấp DR giữa sites.
21. **Active Data Guard có thể offload reporting không?** Có, với read-only queries trên physical standby khi apply tiếp tục và license phù hợp.
22. **Read-after-write trên standby có luôn tức thời không?** Không; cần xem apply lag và cơ chế đảm bảo consistency.
23. **AWR/ASH/SQL Monitor có luôn được bao gồm trong EE không?** Không; Diagnostics/Tuning Pack có entitlement riêng theo feature/release.
24. **Điều gì chứng minh entitlement?** License contract/order documents và licensing policy chính thức, không phải chỉ output SQL.
25. **Vì sao phải diễn tập failover?** Để đo RTO/RPO thực tế và xác minh ứng dụng, network, services, redo và nhân sự vận hành.

RAC, Data Guard và Active Data Guard giải quyết các nhu cầu khác nhau. RAC duy trì dịch vụ khi instance/node lỗi trong cùng database; Data Guard duy trì standby độc lập cho DR; Active Data Guard bổ sung real-time read-only query trong khi redo apply tiếp tục. Lựa chọn đúng phải bắt đầu từ failure domain, RPO/RTO và workload, sau đó đối chiếu edition, option, metric và quyền standby/failover trong tài liệu Oracle cùng hợp đồng của tổ chức. Kiểm tra kỹ thuật bằng V$ views chỉ giúp lập inventory; nó không thay thế xác nhận license. Kết hợp RAC với Data Guard khi cần cả local HA và site DR, và diễn tập định kỳ để chứng minh kiến trúc thực sự đạt mục tiêu.
