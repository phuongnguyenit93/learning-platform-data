# Đặc điểm ổ đĩa, độ trễ I/O và yêu cầu lưu trữ bền vững

## 1. Vì sao thiết kế lưu trữ ảnh hưởng trực tiếp đến Neo4j?

Neo4j lưu property graph trên các file của database: node, relationship, property, index và thông tin giao dịch. Các câu Cypher như `MATCH`, mở rộng đường đi, `MERGE`, cập nhật property hay nhập dữ liệu từ CSV có thể tạo ra các đặc điểm I/O rất khác nhau.

Một ổ đĩa có thể quảng cáo tốc độ **3 GB/s** khi đọc tuần tự nhưng lại xử lý chậm các lượt đọc ngẫu nhiên kích thước nhỏ hoặc có **độ trễ ghi đồng bộ ở p99** rất cao. Khi đó ứng dụng có thể gặp:

- Truy vấn đồ thị chạy nhanh khi dữ liệu đã ở **page cache**, nhưng chậm ở lần truy cập các trang chưa được nạp.
- Giao dịch ghi chờ đĩa xác nhận thao tác với **transaction log**, dù CPU và RAM còn dư.
- Độ trễ tăng từng đợt lúc checkpoint ghi các trang bẩn về store hoặc khi storage bị giới hạn IOPS.
- Hệ thống hoạt động bình thường nhiều ngày nhưng mất dữ liệu khi dùng volume tạm, bộ nhớ đệm ghi không bền vững hoặc quy trình backup không phù hợp.

Trong chương **Cấu hình tài nguyên** của mô-đun `DATABASE_ENGINE_GRAPH_NEO4J`, bài này tập trung vào **đặc điểm ổ đĩa, độ trễ I/O và yêu cầu lưu trữ bền vững**, đặt trong bối cảnh truy vấn quan hệ, index/constraint, nhập dữ liệu, Neo4j Java Driver và Spring Data Neo4j.

Sau bài học, bạn sẽ có khả năng:

1. Giải thích Neo4j sử dụng đĩa thế nào ở đường **đọc**, **ghi**, **transaction log**, **checkpoint** và **khôi phục**.
2. Phân biệt thông lượng MB/s, IOPS, latency p50/p95/p99 và mức độ bão hòa hàng đợi I/O.
3. Chọn và đánh giá HDD, SSD, NVMe, local disk và network block storage bằng workload phù hợp.
4. Hiểu tại sao page cache tăng hiệu năng đọc **không thay thế yêu cầu durable storage**.
5. Tính dung lượng dự phòng, thiết kế backup/restore, nhận diện rủi ro mất dữ liệu và hết đĩa.
6. Đo hiệu năng với fixture Cypher có đáp án và quy trình benchmark không gây tác động ngoài môi trường test.

> **Phạm vi phiên bản:** Ví dụ hướng đến Neo4j 5 trở lên. Tên cài đặt, tính sẵn có của metrics, lệnh backup và chế độ Enterprise/Community thay đổi theo phiên bản, edition và nền tảng managed. Không suy ra cấu hình production từ số liệu demo.

## 2. Neo4j lưu những gì trên ổ đĩa?

| Nhóm dữ liệu | Tác dụng | Đặc điểm I/O thường thấy |
|---|---|---|
| **Graph store** | Các record node, relationship, property và cấu trúc liên quan | Truy cập ngẫu nhiên khi graph traversal/property lookup; ghi các trang đã thay đổi |
| **Index files** | Hỗ trợ tìm node/relationship theo property, full-text, vector và các dạng index khác | Lookup, cập nhật khi ghi, có thể có pattern I/O riêng theo index |
| **Transaction logs** | Ghi nhận thay đổi giao dịch để phục hồi và quản lý tiến độ commit | Ghi bổ sung (*append*) theo thứ tự; chi phí flush/độ bền đặc biệt quan trọng |
| **Checkpoint / store write-back** | Đưa những thay đổi đã ghi log xuống các file database | Những đợt ghi trang bẩn có thể cạnh tranh I/O với truy vấn |
| **Log vận hành** | Query log, debug, security và các thông tin vận hành khác | Ghi liên tục, tốc độ phụ thuộc cấu hình logging |
| **Backup, dump, snapshot** | Bản sao phục hồi dữ liệu khi xảy ra sự cố | Đọc nhiều file và ghi ra điểm lưu trữ khác, có thể gây tải lớn |
| **Tệp tạm / tác vụ quản trị** | Import, restore, index population, tạo archive | Có thể tăng dung lượng và I/O đột biến |

**Không được coi chỉ riêng graph store là toàn bộ dung lượng cần cấp.** Transaction logs, index, backup, tệp tạm, tốc độ tăng trưởng và dung lượng dự phòng đều ảnh hưởng đến quyết định chọn ổ đĩa/volume.

Một **vector index** hoặc index công nghệ đặc biệt có thể có yêu cầu native memory và I/O khác với store thông thường. Mô hình sizing phải xem cả những tính năng thật sự đang sử dụng, không chỉ tổng số node và relationship.

## 3. Đường đọc, đường ghi và đường phục hồi

~~~mermaid
flowchart TD
    A["Cypher qua Browser / Java Driver / SDN"] --> B["Neo4j query runtime"]
    B --> C{"Đọc trang có sẵn trong Neo4j page cache?"}
    C -->|Hit| D["Đọc trang trong RAM"]
    C -->|Miss| E["Tìm/nạp trang từ storage stack"]
    E --> F["OS filesystem cache / block device"]
    F --> D
    B --> G["Transaction ghi"]
    G --> H["Transaction log: ghi và làm bền theo giao thức commit"]
    G --> I["Thay đổi các trang store/index"]
    I --> J["Dirty pages trong cache"]
    J --> K["Checkpoint / write-back xuống file database"]
    H --> L["Recovery: đọc log hợp lệ khi khởi động lại"]
    K --> L
~~~

Sơ đồ chỉ mô tả nguyên lý. Nó **không** có nghĩa một giao dịch ghi phải chờ tất cả các trang store được checkpoint mới được báo commit. Transaction log hỗ trợ khôi phục các thay đổi đã commit ngay cả khi một số trang store chưa kịp ghi về file.

### 3.1. Đọc đồ thị: vì sao I/O ngẫu nhiên quan trọng?

Một câu truy vấn như:

~~~cypher
MATCH (u:User {userId: $id})-[:BOUGHT]->(o:Order)
RETURN o.orderId, o.createdAt
ORDER BY o.createdAt DESC
LIMIT 10;
~~~

có thể phải lần theo record quan hệ, truy cập node đích và đọc property/index ở các vị trí lưu trữ không liền nhau. Khi working set không nằm đủ trong page cache, thao tác đọc **ngẫu nhiên với độ trễ thấp** có thể quan trọng hơn tốc độ đọc tuần tự công bố của ổ đĩa.

Tuy nhiên, không phải mọi traversal đều đọc vật lý từ SSD: Neo4j page cache và bộ nhớ đệm tầng OS có thể đã giữ nhiều trang. **DB Hits** trong `PROFILE` là hoạt động truy cập logic, không phải số lệnh đọc đĩa thực tế.

### 3.2. Ghi đồ thị: transaction log và index cũng tốn I/O

Một câu `MERGE` có thể cần:

1. Tra cứu node/relationship theo index hoặc quét một phần graph.
2. Kiểm tra constraint và khóa để bảo đảm tính đúng.
3. Ghi lại thay đổi giao dịch qua transaction log.
4. Cập nhật các cấu trúc trong store/page cache và index.
5. Đưa dữ liệu về file store theo cơ chế ghi nền/checkpoint phù hợp.

Vì thế, workload ghi vừa có **đọc ngẫu nhiên** (tìm ID) vừa có **ghi log** và **ghi các trang store/index**. Gộp nhiều thao tác vào một transaction có thể giảm overhead commit, nhưng transaction quá lớn lại tăng memory, thời gian giữ khóa, độ trễ và chi phí khi retry.

### 3.3. Tốc độ log không đồng nghĩa tốc độ backup

Ghi transaction log, checkpoint, copy store và backup có đường đi I/O khác nhau. Một ổ lưu trữ có tốc độ append tốt không bảo đảm backup hàng trăm GiB nhanh; backup còn chịu ảnh hưởng của đọc dữ liệu, network, nén, checksum và thiết bị đích.

## 4. So sánh các loại ổ đĩa và dịch vụ lưu trữ

| Loại | Đặc điểm nổi bật | Điều phải kiểm tra trước khi dùng |
|---|---|---|
| **HDD** | Giá/GiB thuận lợi, có thể phù hợp lưu trữ tuần tự/lưu trữ lạnh; seek cơ học làm I/O ngẫu nhiên chậm | Latency random read/write, cạnh tranh khi nhiều transaction, rebuild và recovery |
| **SATA/SAS SSD** | Latency ngẫu nhiên thường thấp hơn HDD nhiều lần | Độ bền ghi, steady-state write, controller/cache và hiệu năng khi gần đầy |
| **NVMe SSD** | Hỗ trợ nhiều queue và IOPS/latency tốt khi hệ thống tận dụng được | Độ bền khi mất điện, thermal throttling, write amplification, QoS ở p99 |
| **Network block volume** | Có thể hỗ trợ mở rộng dung lượng/snapshot/khả năng quản lý thuận tiện | IOPS/throughput cấp phát, giới hạn burst, latency mạng, jitter và giới hạn VM |
| **Local ephemeral disk** | Có thể rất nhanh, phục vụ một số tác vụ tạm hoặc kiến trúc có phục hồi rõ ràng | Dữ liệu có thể mất khi thay host/instance; không tự đáp ứng durability |
| **Object storage** | Phù hợp backup/archive và lưu trữ đối tượng | Không mặc định là filesystem block để chạy trực tiếp graph store đang hoạt động |

Đây là **đặc tính điển hình**, không phải bảng xếp hạng tuyệt đối. Một NVMe cấu hình yếu, đầy dung lượng hoặc dùng write cache không có nguồn điện bảo vệ có thể kém phù hợp hơn một volume có độ trễ ổn định và bảo đảm bền vững rõ ràng.

**Không chọn ổ đĩa dựa duy nhất vào số “up to 7.000 MB/s”.** Neo4j cần hiệu năng trong workload thực tế: kích thước I/O, tỷ lệ đọc/ghi, mức song song, tỉ lệ hit cache, lượng transaction ghi bền và các đợt checkpoint.

## 5. Năm chỉ số I/O cần phân biệt

### 5.1. IOPS

**IOPS** (*Input/Output Operations Per Second*) là số thao tác I/O trong một giây. Nếu mỗi thao tác 4 KiB thì 10.000 IOPS xấp xỉ 39 MiB/s; nếu mỗi thao tác 256 KiB thì cùng 10.000 IOPS tương đương gần 2,44 GiB/s. Đây là ví dụ số học, không phải tốc độ Neo4j được đo.

Công thức:

\[
\text{Throughput (MiB/s)}
=\frac{\text{IOPS}\times\text{bytes/I/O}}{1024^2}
\]

Do đó, một con số IOPS không mô tả đầy đủ năng lực đĩa nếu không biết **kích thước yêu cầu**, tỷ lệ đọc/ghi và độ trễ.

### 5.2. Throughput

**Throughput** (MiB/s hoặc MB/s, cần nêu rõ đơn vị) đo khối lượng dữ liệu truyền mỗi giây. Nó hữu ích khi import, backup, restore, scan lớn hoặc ghi log nhiều, nhưng **không thay thế** latency cho những truy vấn có yêu cầu I/O ngẫu nhiên nhỏ.

### 5.3. Latency p50, p95 và p99

Giả sử một volume có các số liệu **minh họa**:

| Chỉ số | Giá trị minh họa |
|---|---:|
| Read latency p50 | 0,7 ms |
| Read latency p95 | 3 ms |
| Read latency p99 | 25 ms |
| Durable write latency p50 | 1,5 ms |
| Durable write latency p99 | 80 ms |

Không được diễn giải “p99 = 80 ms” thành “mọi giao dịch đều mất 80 ms”. Nó cho biết khoảng 99% phép đo có độ trễ **không lớn hơn** 80 ms trong tập mẫu đó, còn một số ít có thể chậm hơn. Độ trễ đuôi cao có thể làm **p95/p99 của API** tăng mạnh nếu transaction phải chờ các thao tác ghi bền.

Một số hệ thống có độ trễ trung bình thấp nhưng đôi khi bị throttle, garbage collection trong firmware SSD hoặc nghẽn mạng dẫn tới p99 lớn. Vì vậy, hãy yêu cầu cả **phân bố latency**, không chỉ average.

### 5.4. Queue depth và độ bão hòa

Một storage stack có thể có nhiều yêu cầu đang chờ xử lý. Khi đẩy concurrency cao, throughput ban đầu tăng, nhưng đến một ngưỡng:

- IOPS/MBps không tăng tương ứng.
- Queue depth, await time và p95/p99 tăng.
- Neo4j/Driver phải chờ I/O dù CPU chưa sử dụng hết.

Điều đó là dấu hiệu bão hòa, nhưng không thể kết luận chỉ từ queue depth nếu không biết loại thiết bị và workload. Một NVMe có khả năng xử lý nhiều queue khác HDD.

### 5.5. Độ bền ghi được xác nhận

**Ack latency của write** quan trọng với giao dịch: khi server xác nhận commit, storage stack phải tôn trọng những cam kết về flush và ổn định dữ liệu theo giao thức Neo4j. Thiết bị nhận lệnh ghi nhanh rồi chỉ để trong cache dễ mất dữ liệu khi tắt nguồn **không tương đương** ổ có cơ chế bảo vệ nguồn hoặc cache bền vững.

Độ bền dữ liệu không thể suy ra chỉ từ IOPS; phải kiểm tra cả **flush semantics, filesystem, controller, nguồn điện, volume policy và thử nghiệm khôi phục**.

## 6. Transaction log, nguyên tắc write-ahead và độ bền dữ liệu

Neo4j sử dụng **transaction log** để ghi lại các thay đổi giao dịch, hỗ trợ recovery sau sự cố và một số cơ chế sao lưu/replication phù hợp edition/topology. Nguyên tắc ở mức khái niệm là thay đổi đã commit phải có thông tin đủ bền vững trong log trước khi cần dựa vào việc các trang store đã được ghi hoàn toàn.

### 6.1. Commit không phải “toàn bộ graph store đã fsync xong”

Một ví dụ:

1. Giao dịch T1 tạo node `(:Payment {paymentId:'P100'})`.
2. Neo4j thực thi các kiểm tra/ghi cần thiết và sử dụng transaction log.
3. Ứng dụng nhận kết quả commit thành công.
4. Các trang store/index thay đổi có thể được ghi xuống file theo lịch checkpoint/write-back sau đó.

Nếu process dừng đột ngột giữa bước 3 và bước 4, hệ thống có thể cần dùng transaction log để khôi phục. Neo4j quản lý quá trình này; **không** được xóa/di chuyển transaction logs thủ công chỉ vì các file store đã có dữ liệu.

### 6.2. fsync, flush và cache của bộ điều khiển

Các khái niệm cần phân biệt:

- **Buffered write:** dữ liệu có thể mới vào cache ở kernel/controller và chưa tới nơi lưu trữ bền.
- **Flush/fsync semantics:** yêu cầu tầng lưu trữ làm bền dữ liệu theo giao thức được hệ điều hành và filesystem hỗ trợ.
- **Volatile write cache:** bộ nhớ đệm có thể mất nội dung nếu mất điện.
- **Power-loss protection (PLP):** cơ chế phần cứng giúp bảo vệ dữ liệu chưa kịp ghi vào non-volatile media; khả năng thực tế tùy thiết bị.

Yêu cầu vận hành là storage và filesystem **honor** lệnh đồng bộ/ghi bền mà Neo4j dựa vào. Không dùng các chế độ gắn filesystem hoặc cấu hình controller cố tình bỏ qua flush để đổi lấy benchmark đẹp mà không đánh giá hậu quả mất dữ liệu.

> **Thận trọng:** Neo4j cung cấp các bảo đảm ACID khi chạy trên hạ tầng hoạt động theo các giả định lưu trữ được hỗ trợ. Một thiết bị, kernel, filesystem hoặc dịch vụ block volume báo “đã ghi” không trung thực có thể phá vỡ những giả định ấy. Lời hứa durability của phần mềm không thay thế xác minh durability của hạ tầng.

### 6.3. Tx log retention và rotation

Transaction logs tăng khi có ghi. Chúng được rotate và giữ theo chính sách của Neo4j/version, có thể liên quan đến backup và recovery.

- **Retention quá ngắn** có thể gây khó khăn cho một số quy trình incremental backup, tùy phiên bản/công cụ.
- **Retention quá dài** có thể khiến đĩa đầy khi workload ghi lớn.
- **Xóa log bằng tay** có thể làm hỏng khả năng khôi phục; không dùng lệnh `rm` trên transaction logs đang hoạt động.
- **Ghi dồn trong thời gian dài** khiến cần giám sát tốc độ tăng log, thay vì chỉ xem dung lượng database sau một ngày.

Chỉ thay đổi chính sách khi đã hiểu quy trình backup/recovery, khả năng của edition và chi phí dung lượng; kiểm tra tên setting chính xác theo bản Neo4j.

## 7. Checkpoint: vì sao có những đợt ghi lớn?

Page cache giữ các trang của graph/index để phục vụ query. Các trang được chỉnh sửa trở thành **dirty pages**; Neo4j có cơ chế ghi chúng về file store và checkpoint để xác lập trạng thái phục hồi.

~~~mermaid
sequenceDiagram
    participant App as Java Driver
    participant DB as Neo4j
    participant Log as Transaction log
    participant Store as Store/index files
    App->>DB: executeWrite(...)
    DB->>Log: Ghi thông tin transaction
    Log-->>DB: Ghi bền theo giao thức
    DB-->>App: Commit thành công
    Note over DB,Store: Trang store có thể còn bẩn trong cache
    DB->>Store: Background write / checkpoint
    Note over DB,Log: Recovery có thể cần replay log sau checkpoint
~~~

**Checkpoint không phải backup.** Nó giúp giới hạn công việc phục hồi sau crash và đồng bộ trạng thái store, nhưng không cung cấp bản sao độc lập nếu ổ đĩa bị mất hay dữ liệu bị xóa nhầm.

| Tình huống | Điều có thể quan sát |
|---|---|
| Nhiều giao dịch cập nhật property liên tục | Transaction log ghi mạnh, trang store/index bị đánh dấu bẩn |
| Checkpoint xảy ra trên storage đã sát ngưỡng | Latency p95/p99 tăng, queue depth và write I/O cùng tăng |
| Dừng đột ngột | Startup có thể phải kiểm tra/replay log; thời gian recovery tùy lượng việc |
| Sắp hết dung lượng vì log/backup | Có thể lỗi ghi hoặc database không còn phục vụ bình thường |

Không nên mặc định “checkpoint càng thường xuyên càng tốt”. Chạy quá thường xuyên có thể tăng tải ghi, trong khi checkpoint quá thưa có thể làm tăng công việc recovery và yêu cầu không gian log. Đây là quyết định cần đo trên workload thật và đối chiếu hướng dẫn phiên bản.

## 8. Neo4j page cache khác với thiết bị lưu trữ bền vững

**Neo4j page cache** là bộ nhớ phục vụ trang dữ liệu/index thường dùng. Nó giúp giảm phải nạp trang từ storage, nhưng **không thay thế** transaction log, checkpoint hay backup.

| Thành phần | Tác dụng | Mất điện/restart thì sao? |
|---|---|---|
| **Heap JVM** | Đối tượng Java, trạng thái truy vấn, một phần bộ nhớ giao dịch | Nội dung runtime mất khi process dừng |
| **Neo4j page cache** | Giữ trang store/index trong RAM | Trang cache trong RAM mất; dữ liệu đã durable cần có trên storage/log |
| **OS filesystem cache** | Giữ một phần trang tệp ở kernel | Có thể biến mất khi OS restart; không là backup |
| **Persistent block storage** | Lưu file database/log lâu dài | Phải bảo đảm flush, tính toàn vẹn và tính khả dụng theo yêu cầu |
| **Backup ở vùng độc lập** | Phục hồi trước mất cả volume hoặc xóa nhầm | Cần thử restore, kiểm soát quyền và retention |

Khi đọc query bằng `PROFILE`, bạn có thể gặp:

- `DB Hits`: truy cập logic; không phải số lần hệ điều hành đọc đĩa.
- `Page Cache Hits/Misses`: mức độ các trang có sẵn trong cache nếu edition/runtime hỗ trợ.
- `Memory (Bytes)`: bộ nhớ trung gian của operator; không tương đương page cache size.

**Một page cache hit ratio cao không bảo đảm ghi nhanh**: transaction log flush và các đợt write-back vẫn có thể bị storage chậm. Ngược lại, tỉ lệ miss cao nhưng latency vẫn ổn có thể phản ánh storage đủ tốt hoặc truy vấn không nhạy cảm với I/O ở điều kiện đó. Phải dùng cả metrics ứng dụng và hệ điều hành.

## 9. Lưu trữ bền vững trong Docker, Kubernetes và cloud

### 9.1. Container không làm dữ liệu tự bền vững

Nếu Neo4j ghi database vào layer tạm của container, dữ liệu có thể biến mất khi container bị thay thế. Trên Docker, cần mount persistent volume đúng thư mục dữ liệu/log theo hướng dẫn Neo4j của image/version.

Ví dụ **mang tính mô hình**:

~~~yaml
services:
  neo4j:
    image: neo4j:5
    volumes:
      - neo4j-data:/data
      - neo4j-logs:/logs

volumes:
  neo4j-data:
  neo4j-logs:
~~~

File trên không phải cấu hình production hoàn chỉnh: chưa có TLS, secrets, giới hạn RAM, auth, health checks và backup. Trước khi áp dụng phải kiểm tra version image và quyền sở hữu của volume.

Trong Kubernetes, volume phải có `PersistentVolumeClaim`/StorageClass phù hợp; **đừng** mặc định `emptyDir` bền vững sau khi pod được chuyển sang node khác. Đồng thời cần kiểm tra filesystem, access mode, khả năng attach/detach, vùng khả dụng và hành vi khi node mất.

### 9.2. Persistent volume cũng không đồng nghĩa backup

Một cloud block volume có thể giữ dữ liệu qua restart VM nhưng vẫn không chống được:

- Xóa nhầm database hoặc tài khoản có quyền cao ghi đè.
- Lỗi ứng dụng tạo hàng triệu thay đổi sai.
- Mất volume hoặc sự cố vùng cloud ngoài phạm vi SLA đã cam kết.
- Thao tác snapshot không phù hợp khiến bản sao thiếu tính nhất quán có thể khôi phục.

Vì thế, phải có bản sao được hỗ trợ, vùng lỗi độc lập, kiểm thử restore và chính sách retention rõ ràng.

### 9.3. Tránh “tối ưu” bằng ổ tạm cho transaction log

Di chuyển transaction log vào ổ tạm rất nhanh nhưng dễ mất khi node thay thế **có thể làm phá vỡ khả năng recovery** nếu không có cơ chế lưu trữ/replication được thiết kế và kiểm chứng riêng. Việc tách log khỏi store để giảm cạnh tranh I/O chỉ hợp lý khi **cả hai** đạt yêu cầu bền vững và có quy trình khôi phục nhất quán.

## 10. Chọn layout lưu trữ theo mục tiêu

Một thiết kế vận hành thường cần phân loại:

- **Data/graph/index:** cần volume có độ trễ đọc ngẫu nhiên và IOPS phù hợp; đủ khả năng mở rộng store.
- **Transaction logs:** cần write latency ổn định, flush bền vững và dung lượng theo tốc độ ghi/retention.
- **Operational logs:** tách chính sách quay vòng khỏi transaction logs; không để debug log làm đầy volume data.
- **Backup/archive:** ưu tiên vị trí khác failure domain, retention, kiểm soát quyền; không để bản backup duy nhất cạnh database.
- **Temporary/import:** đủ chỗ cho pipeline nhập/dump/restore và các thao tác quản trị có đột biến.

Tách các thư mục ra **nhiều filesystem/volume** có thể giúp quản lý dung lượng và cách ly I/O, nhưng **không tự cải thiện latency** nếu tất cả volume vẫn chia sẻ cùng một thiết bị hoặc chung quota cloud. Đồng thời, việc tách store và transaction logs đòi hỏi kế hoạch backup/snapshot nhận biết tính nhất quán của cả hai phần.

**Nguyên tắc:** khả năng **khôi phục nhất quán** ưu tiên hơn một sơ đồ chia partition trông có vẻ tối ưu.

## 11. Tính dung lượng và không gian dự phòng

Nhu cầu lưu trữ không chỉ là `database size`. Một công thức planning đơn giản:

\[
C_{\text{provisioned}}
\geq (C_{\text{store}} + C_{\text{indexes}} +
C_{\text{txlogs}} + C_{\text{temp}})\times(1+h)
\]

Trong đó `h` là hệ số dự phòng được tổ chức lựa chọn theo tốc độ tăng trưởng, thời gian cần để mở rộng volume và rủi ro burst workload.

**Ví dụ hoàn toàn giả định:**

| Hạng mục | Dung lượng |
|---|---:|
| Graph store | 120 GiB |
| Index | 30 GiB |
| Transaction logs cần giữ theo policy | 20 GiB |
| Import/temp/index population dự kiến | 10 GiB |
| Tổng cơ sở | **180 GiB** |
| Dự phòng minh họa 40% | **72 GiB** |
| Mức cấp phát tính toán | **252 GiB** |

**252 GiB không phải cấu hình khuyến nghị cố định**. Với workload khác, index có thể lớn hơn graph store; import offline có thể cần thêm dung lượng, và backup lưu chung filesystem cần được cộng vào công thức. Ngoài ra cần xem quota của volume, hiệu năng khi gần đầy và chi phí mở rộng.

### Theo dõi dung lượng theo thời gian

| Chỉ số | Câu hỏi cần trả lời |
|---|---|
| Used / free bytes / % | Còn đủ chỗ cho ghi và tăng trưởng không? |
| Tốc độ tăng GiB/ngày | Khi nào đạt ngưỡng cảnh báo hoặc hết quota? |
| Tx log bytes/day và retention | Nếu ghi tăng gấp ba, đĩa log có đủ không? |
| Index size theo loại | Mở rộng text/full-text/vector index gây biến động gì? |
| Dung lượng tạm khi backup/restore/import | Có vượt giới hạn khi chạy công việc theo lịch không? |
| Thời gian mở rộng filesystem/volume | Cần cảnh báo sớm trước bao lâu? |

Không chờ đến khi volume đạt 99% mới xử lý. Ngưỡng cảnh báo phải xét **headroom cho các đợt ghi nhanh**, chứ không chỉ dung lượng trung bình một ngày.

## 12. Kiểm tra cấu hình Neo4j mà không thay đổi hệ thống

Nếu account và edition cho phép, truy vấn **chỉ đọc**:

~~~cypher
SHOW SETTINGS
YIELD name, value
WHERE name IN [
  'server.directories.data',
  'server.directories.transaction.logs.root',
  'server.directories.logs',
  'server.memory.pagecache.size',
  'server.memory.heap.max_size'
]
RETURN name, value
ORDER BY name;
~~~

Giá trị và việc hiển thị một số setting phụ thuộc phiên bản, cách triển khai và quyền quản trị. Neo4j chạy trong container hoặc dịch vụ managed có thể sử dụng đường dẫn/volume thực bên dưới khác với cách biểu diễn trong UI.

Lấy mô tả các database đang hoạt động (nếu có quyền):

~~~cypher
SHOW DATABASES
YIELD name, currentStatus
RETURN name, currentStatus
ORDER BY name;
~~~

Các lệnh trên **không đo tốc độ ổ đĩa**; chúng chỉ xác minh cấu hình và trạng thái. Để đánh giá latency cần metrics hệ điều hành, cloud block storage, query log, page cache, transaction và Java Driver.

### Ví dụ cấu hình tham khảo

~~~properties
# neo4j.conf — chỉ là ví dụ cho một môi trường giả định.
# Không áp dụng nếu chưa biết RAM, store và giới hạn container.
server.memory.heap.initial_size=4G
server.memory.heap.max_size=4G
server.memory.pagecache.size=8G
~~~

**Không** cộng `heap` + `page cache` thành toàn bộ RAM rồi quên OS/native index memory và filesystem buffers. Việc tăng page cache có thể giảm miss của query đọc nhưng lại lấy RAM khỏi OS/những nhu cầu khác; xem tài liệu ước lượng và metrics thực tế trước khi thay.

Trên máy có quyền vận hành, tiện ích:

~~~text
neo4j-admin server memory-recommendation
~~~

có thể giúp đưa ra điểm xuất phát cho phân bổ bộ nhớ; nó **không** tự chọn ổ đĩa hoặc kiểm chứng durability.

## 13. Fixture có đáp án: đọc và duyệt đồ thị ở mức nhỏ

Dùng riêng database thực hành, không xóa dữ liệu production. Dataset này giúp kiểm chứng câu Cypher **đúng** trước khi đo latency; quy mô 1.000 node không đủ để chứng minh hiệu năng SSD/volume.

### 13.1. Reset riêng fixture

~~~cypher
DROP CONSTRAINT qa003_storage_id IF EXISTS;
~~~

~~~cypher
MATCH (n:QA003Storage)
DETACH DELETE n;
~~~

### 13.2. Tạo ID duy nhất và 1.000 node

~~~cypher
CREATE CONSTRAINT qa003_storage_id IF NOT EXISTS
FOR (n:QA003Storage)
REQUIRE n.id IS UNIQUE;
~~~

~~~cypher
UNWIND range(1, 1000) AS i
CREATE (:QA003Storage {
  id: i,
  bucket: i % 10,
  score: i % 10,
  payload: 'sample-' + toString(i)
});
~~~

Tạo đường liên kết tuyến tính có hướng:

~~~cypher
UNWIND range(1, 999) AS i
MATCH (a:QA003Storage {id:i})
MATCH (b:QA003Storage {id:i + 1})
CREATE (a)-[:QA003_NEXT]->(b);
~~~

Các phần sau có thể quan sát **NodeIndexSeek**, mở rộng quan hệ và đọc thuộc tính. Planner tùy phiên bản/tập dữ liệu vẫn có quyền chọn operator khác; không ép một plan cố định.

### 13.3. Kiểm tra kết quả để loại lỗi dữ liệu

~~~cypher
MATCH (n:QA003Storage)
RETURN
  count(n) AS totalNodes,
  sum(n.id) AS sumIds,
  sum(n.score) AS sumScores,
  count(DISTINCT n.bucket) AS buckets;
~~~

| totalNodes | sumIds | sumScores | buckets |
|---:|---:|---:|---:|
| **1.000** | **500.500** | **4.500** | **10** |

Giải thích: `1 + 2 + ... + 1000 = 500500`; giá trị `score = i mod 10` từ 0 đến 9 lặp 100 lần nên `100 × (0+1+...+9) = 4500`.

~~~cypher
MATCH ()-[r:QA003_NEXT]->()
RETURN count(r) AS totalRelationships;
~~~

**Đáp án:** `totalRelationships = 999`.

Kiểm chứng traversal ba bước:

~~~cypher
MATCH (start:QA003Storage {id:1})
      -[:QA003_NEXT*1..3]->(dest:QA003Storage)
RETURN DISTINCT dest.id AS reached
ORDER BY reached;
~~~

**Đáp án:** ba record `2`, `3`, `4`. Đúng số bước và hướng quan hệ quan trọng hơn thời gian chạy của fixture nhỏ.

## 14. Đo truy vấn đọc: page cache và I/O

### 14.1. EXPLAIN không chạy truy vấn

~~~cypher
EXPLAIN
MATCH (n:QA003Storage)
RETURN sum(n.score) AS totalScore;
~~~

`EXPLAIN` cung cấp kế hoạch dự kiến, không nạp đầy đủ tập dữ liệu của câu query như lúc chạy; không dùng nó làm số đo I/O thực tế.

### 14.2. PROFILE thực sự chạy truy vấn

~~~cypher
PROFILE
MATCH (n:QA003Storage)
RETURN sum(n.score) AS totalScore;
~~~

**Đáp án:** `totalScore = 4500`. Xem `Rows`, `DB Hits` và, khi runtime/edition hỗ trợ, `Page Cache Hits/Misses`. Thử chạy lặp lại cùng truy vấn, ghi kết quả.

~~~cypher
PROFILE
MATCH (start:QA003Storage {id:1})
      -[:QA003_NEXT*1..3]->(dest:QA003Storage)
RETURN count(DISTINCT dest) AS reached;
~~~

**Đáp án:** `reached = 3`.

### 14.3. Bảng ghi đo thay vì suy đoán

| Run | Điều kiện | DB Hits | Page cache hits | Page cache misses | Latency client |
|---|---|---:|---:|---:|---:|
| 1 | Lần đầu quan sát | *(đo)* | *(nếu có)* | *(nếu có)* | *(đo)* |
| 2 | Cùng query sau warmup | *(đo)* | *(nếu có)* | *(nếu có)* | *(đo)* |
| 3..N | Steady-state | *(đo)* | *(nếu có)* | *(nếu có)* | *(đo)* |

Không điền số liệu tự tưởng tượng vào cột **đo**. Nếu `DB Hits` gần như không đổi và misses giảm khi lặp lại, page cache là một lời giải thích hợp lý cho thay đổi latency. Nếu không có chỉ số page cache theo query, dùng metrics hệ thống **trong cửa sổ tải đã cô lập**, không gán toàn bộ số liệu của DBMS nhiều người dùng cho một request.

**Cẩn trọng với cold/warm:** vừa `CREATE` dữ liệu xong thì các trang có thể đã nóng. Restart Neo4j cũng không bảo đảm “disk cold”, do filesystem cache của OS và cơ chế page cache warmup. Không xóa cache của OS hoặc restart production để tạo benchmark.

### 14.4. Không suy throughput ổ đĩa từ PROFILE DB Hits

`DB Hits` đo công việc logic của Neo4j query runtime. Cùng 10.000 DB Hits có thể được phục vụ chủ yếu từ RAM trong một lượt chạy và gây nhiều page cache misses trong lượt khác. Số lệnh đọc vật lý còn phụ thuộc layout file, OS cache, đọc trước, index và thiết bị lưu trữ.

Muốn biết block-device latency/IOPS, lấy metrics từ **OS/storage provider**, không biến `DB Hits` thành IOPS bằng một hệ số tùy ý.

## 15. Đo đường ghi và thời gian commit qua Java Driver

Mục tiêu là đo **thời gian ứng dụng chờ giao dịch được commit**, đồng thời biết giới hạn của phép đo.

Một câu ghi nhỏ trên fixture:

~~~cypher
UNWIND range(1, 100) AS i
MATCH (n:QA003Storage {id:i})
SET n.benchMarker = 'sample-run-001';
~~~

Sau lệnh, đúng 100 node có `benchMarker = 'sample-run-001'`; tổng số node vẫn 1.000. Đây **không** phải phép đo độ bền vật lý độc lập: server và client còn phải xử lý Cypher, index lookup, mạng và transaction management.

Ví dụ Java Driver 5.x, có một `Driver` đã khởi tạo:

~~~java
import java.util.UUID;
import java.util.concurrent.TimeUnit;
import org.neo4j.driver.Driver;
import org.neo4j.driver.Session;
import org.neo4j.driver.SessionConfig;
import org.neo4j.driver.Values;

public static void measureCommit(
        Driver driver, String database) {

    // Marker khác nhau giữa các lần đo để có thay đổi thực.
    String marker = UUID.randomUUID().toString();

    try (Session session = driver.session(
            SessionConfig.forDatabase(database))) {

        long start = System.nanoTime();
        session.executeWrite(tx -> {
            tx.run("""
                UNWIND range(1, 100) AS i
                MATCH (n:QA003Storage {id:i})
                SET n.benchMarker = $marker
                """, Values.parameters("marker", marker))
                .consume();
            return null;
        });

        long elapsed = System.nanoTime() - start;
        System.out.printf("Commit round trip: %.3f ms%n",
            elapsed / 1_000_000.0);
    }
}
~~~

**Khoảng đo này bao gồm** Driver, mạng, truyền tham số, chọn kết nối, lookup index, cập nhật store/index và transaction commit. Nó **không tách riêng fsync của ổ đĩa**. Với `executeWrite`, callback có thể được retry khi gặp lỗi transient; thời gian đo có thể gồm nhiều lượt thử. Marker được tạo **trước** callback giúp nội dung cập nhật ổn định khi retry.

Nên ghi thêm từ môi trường test:

- Latency p50/p95/p99 của **managed transaction** ở client, số retries và error rate.
- Tốc độ giao dịch thành công/s, thay vì chỉ số dòng được gửi.
- Disk write latency, write IOPS, bytes/s, queue depth và thời điểm checkpoint.
- CPU/GC, page cache misses, locks; tốc độ ghi có thể bị giới hạn bởi các tầng này chứ không nhất thiết storage.
- Mức tăng dung lượng transaction logs và thời gian recovery trong thử nghiệm có kiểm soát.

### Không so sánh lệch workload

Hai query sau **không tương đương**:

~~~cypher
CREATE (:QA003Storage {id:999999});
~~~

~~~cypher
MERGE (n:QA003Storage {id:999999})
SET n.benchMarker = 'x';
~~~

`CREATE` không phải `MERGE` theo khóa unique; một lượt có thể tạo node mới, lượt tiếp theo chỉ match và update. Không thể kết luận chênh lệch thời gian hoàn toàn do ổ đĩa khi số DB Hits, index lookup và lượng ghi khác nhau. Trước mọi benchmark thực tế phải khôi phục cùng điều kiện dữ liệu.

## 16. Theo dõi I/O từ Neo4j và tầng hạ tầng

### 16.1. Những chỉ số phải thu thập cùng lúc

| Tầng | Metrics hữu ích | Diễn giải đúng |
|---|---|---|
| **Ứng dụng Java/SDN** | p50/p95/p99 query/commit, retries, error rate, pool wait | Latency client có cả network/mapping, không chỉ server |
| **Neo4j query** | `PROFILE` Rows/DB Hits, plan index/scan | Xem chi phí truy cập graph logic |
| **Neo4j page cache** | Hits, misses, hit ratio, usage ratio, faults | Chỉ ra mức nóng của dữ liệu/index |
| **Neo4j transactions/checkpoints** | Throughput giao dịch, checkpoint duration/occurrences, log activity | Xem hoạt động ghi và các đợt write-back |
| **CPU/heap/GC** | CPU saturation, memory, GC pause, transaction memory | Chậm có thể do CPU/GC trước khi tới storage |
| **OS/block device** | Read/write IOPS, MiB/s, await latency, queue depth, utilization | Xác nhận đường I/O thực sự bị nghẽn |
| **Cloud volume** | Provisioned IOPS/throughput, burst credits, throttling, errors | Một instance có thể chạm quota mà ổ vật lý chưa đầy |
| **Filesystem** | Free bytes/inodes, lỗi I/O, journal và mount status | Hết đĩa hoặc filesystem read-only có thể chặn ghi |

Tùy Neo4j edition, metrics và tracing chi tiết có thể cần cấu hình bổ sung. Không giả định tất cả counters đều hiển thị trong `PROFILE`.

### 16.2. Công cụ hệ điều hành tham khảo

Trên Linux do nhóm quản trị vận hành, các lệnh **chỉ đọc** thường hữu ích:

~~~bash
# Xem tên thiết bị, dung lượng và mountpoint.
lsblk -o NAME,SIZE,TYPE,ROTA,MOUNTPOINT

# Xem dung lượng filesystem.
df -h

# Khi đã cài sysstat: thống kê thiết bị mỗi giây.
iostat -xz 1
~~~

`iostat` không tự tách I/O của Neo4j khỏi I/O của các process khác; cần đối chiếu mountpoint, thiết bị và mức tải. Trên NVMe hoặc storage ảo hóa, `%util` gần 100% **không luôn** có nghĩa đã đạt trần thiết bị; cần thêm queue depth, await, IOPS và throughput.

Trong Kubernetes/cloud, ghép thêm metrics của **PVC**, StorageClass, VM quota, disk IOPS limit và provider throttling. Nếu không có quyền hệ điều hành (Aura/managed service), sử dụng dashboard được nhà cung cấp hỗ trợ và ghi rõ giới hạn quan sát.

## 17. Bảng phân biệt nút thắt: storage, cache hay Cypher?

| Triệu chứng | Giả thuyết hợp lý | Phép đối chứng |
|---|---|---|
| Lần đầu đọc chậm, lần sau nhanh; DB Hits gần không đổi | Page cache chưa nóng ở lần đầu | Ghi page cache misses/hits và kiểm soát điều kiện warmup |
| Nhiều page cache misses, random read latency cao | Working set vượt cache hoặc storage đọc ngẫu nhiên chậm | Đo cache usage/miss, OS read IOPS, cấu trúc query/index |
| DB Hits rất cao kể cả khi cache nóng | Plan đang quét/mở rộng nhiều dữ liệu | `EXPLAIN`/`PROFILE`; xem index, cardinality, filter |
| Giao dịch ghi p99 cao, disk flush latency cũng tăng | Log/volume durable write là ứng viên | So thời điểm commit chậm với storage latency, checkpoint và throttling |
| p99 tăng theo từng đợt, checkpoint activity trùng thời gian | Checkpoint/write-back cạnh tranh I/O | Đo checkpoint duration, write bytes, queue depth theo timeline |
| CPU bão hòa, storage I/O còn dư | Neo4j xử lý query/constraint/GC nặng | Tối ưu Cypher, batch, index và concurrency |
| Pool wait tăng nhưng server ít I/O | Kết nối/transaction bị giữ lâu hoặc network | Kiểm tra Driver pool, result consumption và network RTT |
| Cloud volume gần trần IOPS/burst credit cạn | Quota storage tầng cloud | Xem metric nhà cung cấp, cấp IOPS phù hợp hoặc đổi volume |
| Đĩa log gần đầy, store tăng ít | Log retention/ghi quá nhiều | Kiểm tra chính sách và dung lượng log; không xóa file bằng tay |
| Container restart thì mất dữ liệu | Volume không persistent hoặc mount sai | Kiểm tra PVC/volume, restore test và failure domain |
| Backup có file nhưng restore không thành công | Snapshot/backup thiếu nhất quán hoặc thiếu thành phần | Dùng công cụ được hỗ trợ và diễn tập restore độc lập |

Một bài toán có thể có **nhiều nút thắt**. Ví dụ thiếu index làm `MERGE` tốn thêm đọc ngẫu nhiên, sau đó disk write chậm ở thời điểm commit. Giải pháp có thể gồm **constraint/index đúng + ổ đĩa có latency ổn định**, chứ không nhất thiết chỉ tăng RAM hoặc mua NVMe.

## 18. Backup, restore, RPO và RTO: bền vững đến đâu là đủ?

### 18.1. Phân biệt khả năng phục hồi

- **Durability của transaction:** mục tiêu là dữ liệu đã commit không bị mất trong các loại lỗi mà nền tảng/phần mềm cam kết hỗ trợ.
- **Backup:** bản sao độc lập để phục hồi khi dữ liệu bị xóa/hỏng, cả volume mất hoặc thao tác con người sai.
- **HA/replication:** tăng khả năng tiếp tục dịch vụ khi một server lỗi; **không thay thế backup** vì lỗi logic/xóa nhầm có thể được nhân bản.
- **RPO (Recovery Point Objective):** tổ chức chấp nhận mất tối đa bao nhiêu dữ liệu tính theo thời gian.
- **RTO (Recovery Time Objective):** thời gian mục tiêu để dịch vụ có thể hoạt động trở lại sau sự cố.

Ví dụ một dịch vụ yêu cầu **RPO ≤ 5 phút** và **RTO ≤ 30 phút**: backup một lần mỗi ngày **không đủ** để tự đáp ứng RPO đó; cần thiết kế backup/log/replication phù hợp và thử nghiệm phục hồi. Không được chỉ ghi SLA trên tài liệu mà không diễn tập.

### 18.2. Neo4j backup và dump khác gì?

| Phương án | Đặc điểm | Khi nào phù hợp |
|---|---|---|
| **Online database backup** | Công cụ backup được Neo4j hỗ trợ có thể sao lưu khi database hoạt động trong edition/version thích hợp | Workload production cần backup theo lịch, ít gián đoạn |
| **Offline dump** | Tạo archive khi database tương ứng không hoạt động theo yêu cầu công cụ | Sao chép/phục hồi/test/di chuyển trong cửa sổ bảo trì |
| **Storage snapshot có phối hợp** | Snapshot tại tầng storage nhưng cần bảo đảm nhất quán store + log theo quy trình được Neo4j hỗ trợ | Hạ tầng có cơ chế quiesce/snapshot nhất quán và diễn tập restore |
| **Sao chép thư mục data lúc database đang ghi** | Có thể thu được tập file không đồng bộ trạng thái | **Không dùng như backup production** |

Dùng lệnh `neo4j-admin database backup` hoặc `neo4j-admin database dump` theo **cú pháp/version và edition đang chạy**. Đừng thực thi ví dụ từ phiên bản khác rồi mặc định backup có thể restore. Với cluster, phải xem hướng dẫn backup đúng topology và database được chọn.

### 18.3. Kiểm tra restore quan trọng hơn “backup job xanh”

Một quy trình tối thiểu:

1. Lưu backup ở **vùng lỗi/identity tách biệt** khỏi Neo4j production.
2. Kiểm soát quyền đọc/xóa bản backup và encryption at rest/in transit.
3. Định kỳ restore vào **một môi trường độc lập** bằng version/tool được hỗ trợ.
4. Chạy truy vấn đối soát số node, relationship, constraint/index và vài nghiệp vụ đại diện.
5. Đo **thời gian thật** từ khi bắt đầu restore đến khi ứng dụng đọc/ghi được để kiểm tra RTO.
6. Ghi restore point thực tế và phạm vi dữ liệu không khôi phục được để kiểm tra RPO.
7. Thử thêm tình huống lỗi: backup thiếu, volume đầy, secret/KMS không khả dụng, schema/version không tương thích.

Không dùng tính năng `DETACH DELETE`, lệnh drop database hoặc ngắt nguồn trên production để mô phỏng sự cố. Thực hiện các diễn tập lỗi ở staging/DR lab được phê duyệt.

## 19. Checklist lựa chọn ổ đĩa cho Neo4j

Trước khi duyệt một thiết kế lưu trữ, hãy xác nhận:

- [ ] Loại workload chính: OLTP ghi, traversal ngẫu nhiên, full scan, import hay analytics?
- [ ] Đã đo IOPS, MiB/s, p50/p95/p99 ở **mixed workload** gần thực tế?
- [ ] Có quy định về flush/fsync durability, cache controller, PLP và filesystem được hỗ trợ?
- [ ] Store, index, transaction logs, temp và backup đều có dung lượng/headroom?
- [ ] Storage volume có persistence qua restart/replace pod/VM theo thiết kế?
- [ ] Có cảnh báo free bytes, tăng trưởng log, queue depth, write latency và throttle?
- [ ] Có chế độ backup/restore được hỗ trợ với phiên bản/edition Neo4j đang dùng?
- [ ] Backup được giữ ở vùng lỗi khác và đã **diễn tập restore**?
- [ ] Có mục tiêu RPO/RTO và đã chứng minh bằng thử nghiệm?
- [ ] Các cấu hình page cache/heap không chiếm hết RAM dùng cho OS/native index?
- [ ] Không tăng concurrency ghi vượt mức làm throughput chững mà p99 tăng?
- [ ] Có kế hoạch xử lý disk-full, I/O errors, read-only filesystem và volume expansion?
- [ ] Mọi thay đổi cấu hình/volume được thử ở staging và có phương án rollback?

## 20. Bài tập có đáp án

### Bài 1 — MB/s hay IOPS?

Một ổ đạt thông lượng đọc tuần tự 2 GiB/s nhưng có random read latency p99 cao. Truy vấn Neo4j có nhiều bước traversal và page cache misses đang chậm. Có thể kết luận ổ đủ nhanh không?

**Đáp án:** Không. Throughput tuần tự không đại diện cho truy cập random nhỏ. Cần đo random IOPS/latency p95-p99, page cache misses và `DB Hits` của truy vấn.

### Bài 2 — Tính dung lượng

Graph store 120 GiB, index 30 GiB, tx logs 20 GiB, dữ liệu tạm 10 GiB. Nếu chọn dự phòng 40% trên tổng cơ sở, mức tính toán là bao nhiêu?

**Đáp án:** Tổng cơ sở `120+30+20+10=180 GiB`; dự phòng `72 GiB`; mức cấp phát minh họa **252 GiB**. Chưa kể backup lưu cùng volume hay tăng trưởng bất thường.

### Bài 3 — Lần chạy nóng và disk reads

Hai lượt `PROFILE` cùng query có `DB Hits` bằng nhau, nhưng lượt sau page cache misses giảm mạnh. Điều gì có thể thay đổi?

**Đáp án:** Công việc logic tương đương nhưng các trang cần dùng đã có trong page cache. Đó là lý do hợp lý để latency đọc giảm; không kết luận chính xác bao nhiêu ms là disk I/O nếu chưa đo ở tầng storage.

### Bài 4 — Commit đã trả về nhưng trang store chưa checkpoint

Một transaction commit thành công nhưng server chưa kịp checkpoint mọi dirty page. Điều đó tự động đồng nghĩa dữ liệu không durable không?

**Đáp án:** Không. Neo4j dùng transaction log để duy trì khả năng recovery; việc checkpoint store không cần trùng thời điểm với commit. Durability vẫn phụ thuộc storage tuân thủ cam kết ghi bền/flush.

### Bài 5 — Kubernetes emptyDir

Neo4j chạy bằng pod có dữ liệu ở `emptyDir`. Khi pod chuyển sang node khác, có thể coi dữ liệu vẫn an toàn chỉ vì service tự khởi động lại không?

**Đáp án:** Không. `emptyDir` là lưu trữ theo vòng đời pod, không thay thế persistent volume. Phải dùng PVC/StorageClass và quy trình backup/restore phù hợp.

### Bài 6 — Hai chỉ số trái chiều

Neo4j có page cache hit ratio 99,8%, nhưng commit p99 = 200 ms vào lúc storage write latency tăng và checkpoint đang diễn ra. Nên tăng page cache ngay không?

**Đáp án:** Chưa. Hit ratio đã cao; cần phân tích durable write latency, checkpoint/write-back, storage throttling và transaction log. Tăng page cache không giải quyết trực tiếp đường flush ghi.

### Bài 7 — HA có thay backup?

Hệ thống chạy cluster 3 server. Một DBA xóa nhầm graph bằng Cypher có quyền cao và việc xóa được replicate. Có thể dùng HA replication để tự phục hồi dữ liệu cũ không?

**Đáp án:** Không. Replication có thể truyền cả thao tác sai. Cần backup có điểm phục hồi và diễn tập restore tách khỏi dữ liệu đang vận hành.

### Bài 8 — Đọc đáp án fixture

Fixture ở mục 13 có `1000` node, `999` quan hệ `QA003_NEXT`, `score = id mod 10`. `sum(score)` bằng bao nhiêu và từ id=1 đi theo 1–3 quan hệ tới ID nào?

**Đáp án:** `sum(score) = 4500`, tập ID tới được là **{2,3,4}**. Nếu khác đáp án, phải sửa/kiểm tra dữ liệu trước khi dùng fixture để đo I/O.

### Bài 9 — Đĩa chưa đầy nhưng p99 tăng

Một cloud volume còn 40% dung lượng trống nhưng IOPS provisioned đã chạm trần, hàng đợi tăng. Lý do nào phù hợp hơn: thiếu dung lượng hay thiếu performance quota?

**Đáp án:** Trước mắt là **performance quota/IOPS**, không phải hết dung lượng. Có thể cần tối ưu query/batch/cache hoặc thay đổi loại và mức cấp IOPS của volume; phải đối chiếu thêm metrics toàn hệ thống.

### Bài 10 — Snapshot live có chắc nhất quán?

Một script sao chép file graph store khi Neo4j vẫn ghi, nhưng không sao lưu/đồng bộ transaction logs theo quy trình được hỗ trợ. Có được xem là backup kiểm chứng không?

**Đáp án:** Không. Bản sao có thể không nhất quán; dùng công cụ backup Neo4j đúng edition/version hoặc snapshot được phối hợp và thử restore thành công.

## 21. Dọn dữ liệu thực hành

Chỉ trong **database test** có fixture `QA003Storage`, không áp dụng trên graph sản xuất:

~~~cypher
MATCH (n:QA003Storage)
DETACH DELETE n;
~~~

~~~cypher
DROP CONSTRAINT qa003_storage_id IF EXISTS;
~~~

Kiểm tra:

~~~cypher
MATCH (n:QA003Storage)
RETURN count(n) AS remaining;
~~~

**Đáp án:** `remaining = 0`. Các property benchmark ghi thêm trên 100 node cũng được xóa cùng node. Nếu test đã tạo thêm node bằng ví dụ `CREATE/ MERGE`, chúng cũng mang label fixture và sẽ bị dọn. Không chạy trên database chia sẻ những label demo với dữ liệu thật.

## 22. Tài liệu tham khảo và nguyên tắc cuối cùng

- [Neo4j Operations Manual — Disks, RAM and other tips](https://neo4j.com/docs/operations-manual/current/performance/disks-ram-and-other-tips/): đặc điểm lưu trữ, bộ nhớ và tối ưu hệ thống.
- [Neo4j Operations Manual — Memory configuration](https://neo4j.com/docs/operations-manual/current/performance/memory-configuration/): phân bổ heap, page cache và OS/native memory.
- [Neo4j Operations Manual — Configuration settings](https://neo4j.com/docs/operations-manual/current/configuration/configuration-settings/): tên setting và đường dẫn data/transaction logs theo phiên bản.
- [Neo4j Operations Manual — Monitoring metrics reference](https://neo4j.com/docs/operations-manual/current/monitoring/metrics/reference/): page cache, checkpoint, transactions và các nhóm metrics hữu ích.
- [Neo4j Operations Manual — Backup and restore](https://neo4j.com/docs/operations-manual/current/backup-restore/): backup online, dump, restore và kiểm tra phù hợp edition/version.
- [Neo4j Operations Manual — Docker](https://neo4j.com/docs/operations-manual/current/docker/): container, volumes, cấu hình và quyền file.
- [Neo4j Cypher Manual — Execution plans](https://neo4j.com/docs/cypher-manual/current/planning-and-tuning/execution-plans/): `EXPLAIN`/`PROFILE`, `DB Hits`, page cache và memory.
- [Neo4j Java Driver Manual — Performance](https://neo4j.com/docs/java-manual/current/performance/): đo transaction, reuse Driver, batching và kết quả client.

**Ghi nhớ:** Không chọn ổ đĩa cho Neo4j chỉ dựa trên MB/s tối đa. Hãy đo **random I/O, durable write latency p95/p99, mức sử dụng page cache, transaction log và checkpoint** cùng khối lượng graph thực tế. Dữ liệu đã commit cần storage tôn trọng nguyên tắc ghi bền; còn **backup có thể restore** mới bảo vệ trước mất volume, xóa nhầm hoặc lỗi vận hành. Hiệu năng tốt và khả năng khôi phục là **hai mục tiêu phải được kiểm chứng độc lập**.
