# Lưu trữ phân tầng và yêu cầu thành phần lưu trữ từ xa

Kafka lưu record theo log phân vùng trên đĩa của broker. Cách này rất hiệu quả cho luồng dữ liệu mới: producer ghi nối tiếp vào log, consumer thường đọc các offset gần cuối và hệ điều hành có thể phục vụ nhiều lần đọc từ page cache. Tuy nhiên, nếu cần giữ dữ liệu trong nhiều tháng, toàn bộ log trên đĩa broker sẽ làm tăng chi phí ổ đĩa, quy mô cụm và thời gian phục hồi khi broker phải thay thế hoặc cân bằng lại partition.

**Tiered storage** chia dữ liệu Kafka thành hai tầng: local tier trên broker để phục vụ dữ liệu mới và remote tier trên hệ thống lưu trữ bên ngoài để giữ các log segment cũ hơn. Consumer vẫn dùng Kafka protocol và offset như trước; broker quyết định đọc dữ liệu từ tầng nào.

Bài học này giải thích kiến trúc hai tầng, vòng đời segment, metadata của remote storage, yêu cầu đối với backend, cấu hình Kafka 4.4 và các tình huống vận hành cần kiểm soát.

## 1. Vì sao cần lưu trữ phân tầng?

Trong nhiều hệ thống, phần lớn consumer đọc dữ liệu mới theo kiểu streaming. Các lần đọc này thường truy cập phần cuối của partition và có thể tận dụng page cache của hệ điều hành. Dữ liệu cũ được đọc ít thường xuyên hơn, chủ yếu phục vụ backfill, điều tra, chạy lại pipeline hoặc phục hồi ứng dụng.

Nếu giữ toàn bộ dữ liệu trong local disk của broker, thời gian retention càng dài thì dung lượng ổ đĩa cần thiết càng lớn. Muốn tăng dung lượng local thường phải bổ sung broker hoặc disk, kéo theo CPU, RAM, network và chi phí vận hành.

Tiered storage cho phép tách nhu cầu lưu trữ dài hạn khỏi tài nguyên local của broker:

- Giữ dữ liệu mới trên local disk để duy trì đường đọc/ghi có độ trễ thấp.
- Chuyển các log segment đã hoàn tất sang remote storage.
- Giữ metadata và index để broker tìm đúng offset trong segment từ xa.
- Cho consumer đọc dữ liệu cũ thông qua cùng Kafka API và offset.

Tiered storage hữu ích khi cần retention dài, có nhiều dữ liệu lịch sử nhưng tỷ lệ truy cập dữ liệu cũ thấp. Nó cũng có thể giảm lượng dữ liệu local phải sao chép khi broker được thay thế hoặc cluster rebalance.

Tiered storage giữ dữ liệu trong Kafka lâu hơn và cho consumer tiếp tục đọc qua Kafka API; nó không thay thế các pipeline ETL, xử lý batch hoặc kho phân tích chuyên dụng mà hệ thống vẫn cần.

## 2. Hai tầng lưu trữ trong Kafka

| Tầng | Nơi lưu | Dữ liệu thường nằm ở đây | Đặc điểm |
|---|---|---|---|
| **Local tier** | Disk và page cache của broker | Active segment và các segment mới | Phục vụ tail read, ghi mới và replication local; thường có latency thấp |
| **Remote tier** | Hệ thống lưu trữ bên ngoài như S3, HDFS hoặc dịch vụ tương thích | Các segment đã hoàn tất và metadata/index đi kèm | Phù hợp retention dài và đọc lịch sử; phụ thuộc network và backend |

Một partition có thể hình dung như sau:

~~~text
Offset thấp                                              Offset cao
     |                                                       |
     v                                                       v
+--------------------------+-------------------------------+
|       Remote tier        |          Local tier           |
|  Segment 0  Segment 1    |  Segment 2   Segment 3 ACTIVE |
+--------------------------+-------------------------------+
          ^                              ^
          |                              |
   Đọc lịch sử/backfill            Đọc/ghi dữ liệu mới
~~~

Khi một local log segment được roll và trở thành segment không còn active, Remote Log Manager có thể sao chép segment cùng các index và trạng thái phụ trợ lên remote storage. Sau khi bản sao từ xa được xác nhận thành công và segment đủ điều kiện theo local retention, bản local mới được phép xóa.

Điểm quan trọng là Kafka không đẩy từng record đang ghi vào remote storage. Đơn vị được chuyển là **log segment đã hoàn tất**, vì vậy kích thước segment, tốc độ roll và thời điểm upload ảnh hưởng đến độ trễ trước khi dữ liệu xuất hiện ở remote tier.

## 3. Các thành phần tham gia tiered storage

Kafka 4.4 cung cấp framework và các interface cho tiered storage. Phần triển khai backend lưu trữ từ xa phải được cung cấp riêng.

### 3.1. Remote Log Manager

Remote Log Manager (RLM) là thành phần nội bộ của broker điều phối vòng đời remote log segment. Nó:

- Theo dõi segment nào đã roll và đủ điều kiện upload.
- Gọi storage manager để copy segment và index sang remote tier.
- Ghi nhận metadata của segment từ xa.
- Phục vụ fetch request cần đọc dữ liệu cũ từ remote tier.
- Xử lý việc xóa segment từ xa khi retention hết hạn hoặc topic được xóa.
- Duy trì cache index để giảm số lần phải tải index từ remote storage.

RLM là thành phần nội bộ của Kafka, không phải API mà ứng dụng producer hoặc consumer gọi trực tiếp.

### 3.2. RemoteStorageManager (RSM)

`RemoteStorageManager` là interface mà plugin phải triển khai để quản lý dữ liệu segment từ xa và index tương ứng. Các thao tác trong vòng đời bao gồm lưu/copy segment, đọc segment hoặc một phần dữ liệu, đọc index và xóa dữ liệu từ xa.

Kafka Apache **không cung cấp sẵn một implementation production cho S3 hoặc HDFS**. Cần chọn plugin tương thích với phiên bản Kafka đang chạy hoặc tự triển khai interface này. Plugin và các thư viện phụ thuộc được nạp qua class name và class path cấu hình ở broker.

`LocalTieredStorage` trong test fixtures của Apache Kafka chỉ mô phỏng remote storage bằng một thư mục local để kiểm thử tích hợp. Nó hữu ích cho lab nhưng không phải backend object storage phân tán để triển khai production.

### 3.3. RemoteLogMetadataManager (RLMM)

`RemoteLogMetadataManager` quản lý metadata của remote log segment với yêu cầu ngữ nghĩa nhất quán mạnh. Metadata có thể bao gồm:

- Topic ID và partition.
- Remote log segment ID.
- Offset đầu/cuối của segment.
- Leader epoch và trạng thái segment.
- Thông tin cần thiết để tìm segment và các index tương ứng.
- Trạng thái copy hoặc delete trong vòng đời segment.

Implementation mặc định của Kafka lưu metadata trong internal topic `__remote_log_metadata` bằng `TopicBasedRemoteLogMetadataManager`. Có thể thay bằng implementation khác nếu hệ thống có một kho metadata riêng đáp ứng yêu cầu nhất quán.

Không nên xem object listing trong S3 hoặc thư mục remote là nguồn metadata duy nhất. Kafka tách metadata quản lý segment khỏi storage chứa bytes của segment để bảo đảm việc tìm kiếm, cập nhật và xóa segment có trạng thái nhất quán.

### 3.4. Mối quan hệ giữa các thành phần

~~~mermaid
flowchart TD
    B["Kafka Broker"] --> RLM["Remote Log Manager"]
    RLM --> RSM["RemoteStorageManager plugin"]
    RLM --> RLMM["RemoteLogMetadataManager"]
    RSM --> RS["Remote storage: S3 / HDFS / compatible store"]
    RLMM --> MT["Internal topic __remote_log_metadata"]
    RLM --> IC["Remote index cache on broker disk"]
    C["Consumer Fetch request"] --> B
    B -->|Offset nằm local| LD["Local log segment"]
    B -->|Offset nằm remote| RLM
    RLM -->|Tìm segment bằng metadata/index| RS
    RS --> RLM
    RLM --> B
    B --> C
~~~

RSM chịu trách nhiệm bytes và index trong remote storage. RLMM giữ metadata có tính nhất quán mạnh để broker xác định segment nào tồn tại và ở đâu. RLM kết nối hai phần này với log, fetch và retention của Kafka.

## 4. Vòng đời của một log segment

Một segment thường đi qua các giai đoạn sau:

1. **Active:** broker ghi record mới vào segment hiện tại. Segment này chưa được upload vì vẫn có thể tiếp tục thay đổi.
2. **Rolled:** khi đạt điều kiện roll theo `segment.bytes`, `segment.ms` hoặc điều kiện liên quan, Kafka đóng segment và mở segment mới.
3. **Upload eligible:** segment cũ đã không còn active và đáp ứng điều kiện thời gian/kích thước để copy.
4. **Copying:** RLM gọi RSM để chuyển log segment cùng index và trạng thái phụ trợ sang remote storage.
5. **Remote metadata published:** sau khi copy thành công, metadata của remote segment được công bố qua RLMM.
6. **Local deletion eligible:** khi local retention cho phép và segment đã được copy thành công, bản local có thể được xóa.
7. **Remote expiration:** khi overall retention hết hạn hoặc topic/partition bị xóa theo chính sách, RLM yêu cầu RSM xóa remote segment và RLMM cập nhật metadata tương ứng.

~~~mermaid
stateDiagram-v2
    [*] --> Active
    Active --> Rolled: Segment roll
    Rolled --> Eligible: Đạt điều kiện upload
    Eligible --> Copying: RLM gọi RSM
    Copying --> Published: Copy thành công và metadata được ghi
    Copying --> Eligible: Lỗi tạm thời / retry
    Published --> LocalDeleted: Đạt local retention
    LocalDeleted --> RemoteExpired: Hết overall retention
    Published --> RemoteExpired: Remote retention hết hạn
    RemoteExpired --> [*]
~~~

Kafka không xóa bản local chỉ vì đã hết local retention nếu việc upload remote chưa hoàn tất. Điều này tránh tạo khoảng trống dữ liệu khi remote backend lỗi hoặc copy chưa thành công. Vì thế, nếu backend bị gián đoạn lâu, local disk có thể tiếp tục giữ segment cũ và tiến gần đến ngưỡng đầy.

Khi upload segment, Kafka cần lưu cả các index và trạng thái phụ trợ tương ứng, không chỉ file log bytes. Các thành phần có thể gồm offset index, time index, transaction index, leader epoch cache và producer ID snapshot. Chúng hỗ trợ định vị offset, xử lý transaction và duy trì tính nhất quán khi replica bắt kịp hoặc leader thay đổi.

## 5. Local retention và overall retention

Tiered storage có hai nhóm retention với ý nghĩa khác nhau.

| Cấu hình topic | Ý nghĩa |
|---|---|
| `local.retention.ms` | Thời gian tối đa giữ bản local trước khi segment đủ điều kiện xóa khỏi local tier |
| `local.retention.bytes` | Giới hạn dung lượng local log cho mỗi partition trước khi segment đủ điều kiện xóa khỏi local tier |
| `retention.ms` | Thời gian lưu dữ liệu tổng thể; khi hết hạn, dữ liệu remote cũng đủ điều kiện xóa |
| `retention.bytes` | Giới hạn dung lượng log tổng thể cho mỗi partition |

`local.retention.ms` và `local.retention.bytes` có giá trị mặc định `-2`, nghĩa là kế thừa giá trị tương ứng từ `retention.ms` và `retention.bytes`. Giá trị hiệu lực của local retention phải nhỏ hơn hoặc bằng overall retention.

`retention.bytes` được áp dụng ở cấp partition. Muốn ước lượng dung lượng của cả topic, cần tính đến số partition và replication ở local tier. Remote storage có cơ chế lưu trữ riêng do backend cung cấp; không nên mặc định rằng dung lượng remote bằng local dung lượng nhân với replication factor của Kafka.

Ví dụ, topic cần giữ dữ liệu tổng thể 30 ngày nhưng chỉ giữ bản local 6 giờ:

~~~properties
remote.storage.enable=true
local.retention.ms=21600000
retention.ms=2592000000
local.retention.bytes=-1
retention.bytes=-1
~~~

Trong ví dụ này:

- Bản local có thể được xóa khi đã đủ 6 giờ và segment đã upload thành công.
- Bản remote được giữ theo overall retention 30 ngày.
- `-1` nghĩa là không giới hạn theo kích thước; retention theo thời gian vẫn áp dụng.
- Các segment mới vẫn có thể tồn tại lâu hơn local retention nếu chưa roll hoặc chưa upload xong.

Đừng đặt local retention quá ngắn chỉ để giảm disk usage. Cần đủ dung lượng local cho segment active, upload backlog, consumer đọc dữ liệu mới, replica catch-up và thời gian backend gián đoạn có thể chấp nhận.

### 5.1. Delay upload

Mặc định, segment không còn active được upload khi đủ điều kiện, giúp remote tier cập nhật sớm. Điều này có thể khiến một khoảng dữ liệu còn nằm đồng thời trên cả local và remote, làm tăng chi phí remote.

Kafka có thể trì hoãn upload bằng:

- Topic config `remote.copy.lag.ms` và `remote.copy.lag.bytes`.
- Broker config `log.remote.copy.lag.ms` và `log.remote.copy.lag.bytes`.

Hai điều kiện thời gian và kích thước được xét theo kiểu OR: segment đủ điều kiện khi một trong hai điều kiện được thỏa mãn. Giá trị `0` khiến upload đủ điều kiện ngay khi segment không còn active; giá trị `-1` cho phép kế thừa điều kiện local retention tương ứng.

Ví dụ topic có local retention 3 ngày nhưng muốn chỉ upload sau khi segment đã cũ ít nhất một ngày:

~~~properties
local.retention.ms=259200000
retention.ms=604800000
remote.copy.lag.ms=86400000
remote.copy.lag.bytes=-1
~~~

Cần tính cả thời gian upload và local disk headroom. Delay upload càng dài thì remote tier càng thiếu dữ liệu mới và local disk càng phải giữ dữ liệu lâu.

## 6. Yêu cầu đối với remote storage backend

Remote storage không chỉ là một nơi có thể ghi file. Backend phải đáp ứng hợp đồng lưu trữ mà RSM sử dụng và phù hợp với tải của Kafka.

### 6.1. API và tính nhất quán

Backend hoặc plugin phải hỗ trợ các thao tác cần thiết trong vòng đời segment:

- Tạo/lưu segment và các index liên quan.
- Đọc segment theo ID hoặc byte range cần thiết cho fetch.
- Đọc các index và metadata phụ trợ.
- Xóa segment, index và object phụ trợ khi Kafka yêu cầu.
- Xử lý retry, timeout và thao tác lặp lại mà không tạo ra trạng thái không nhất quán.

Remote log metadata manager cần semantics nhất quán mạnh. Backend lưu bytes nên bảo đảm object đã upload hoàn chỉnh trước khi metadata được công bố để consumer hoặc broker khác có thể tìm thấy segment. Cần hiểu rõ semantics read-after-write, delete và retry của dịch vụ lưu trữ hoặc plugin đang dùng.

### 6.2. Khả năng truy cập từ tất cả broker

Mỗi broker có thể trở thành leader hoặc follower của nhiều partition. Vì vậy, mọi broker cần truy cập được cùng remote storage namespace theo đúng quyền hạn:

- Cùng endpoint, bucket/container và quy tắc định danh object.
- DNS, routing và firewall cho phép kết nối từ mọi broker.
- TLS cho dữ liệu truyền qua mạng.
- Credential hoặc workload identity được cấp tự động, có thể xoay vòng.
- Quyền đọc, ghi và xóa được giới hạn theo yêu cầu của plugin.
- Không phụ thuộc vào một mount local chỉ tồn tại trên một broker.

Không đặt credential dài hạn trực tiếp trong file cấu hình nếu môi trường có secret manager hoặc workload identity. Không bật public access cho bucket chỉ để broker có thể đọc object.

### 6.3. Độ bền và dung lượng

Remote tier thường chứa dữ liệu lịch sử dài hạn, vì vậy cần xác định:

- Durability và redundancy của backend.
- Chính sách versioning, backup hoặc disaster recovery nếu nghiệp vụ yêu cầu.
- Giới hạn object size, request rate và throughput.
- Khả năng phục vụ nhiều broker đọc cùng lúc.
- Chi phí dung lượng, request, egress và retrieval.
- Chính sách lifecycle không xóa object trước khi Kafka hết retention.

Không dùng lifecycle rule độc lập để xóa segment chỉ dựa trên tuổi object nếu Kafka vẫn có thể tham chiếu đến nó. Việc hết hạn và xóa remote segment cần phối hợp với Kafka RLM/RLMM để metadata và bytes không lệch nhau.

### 6.4. Hiệu năng đọc và ghi

Cần đo hai đường tải riêng:

- **Copy path:** broker upload segment từ local disk lên remote storage. Nếu tốc độ copy thấp hơn tốc độ segment trở nên eligible, upload backlog tăng và local disk không giải phóng kịp.
- **Fetch path:** broker đọc segment/index từ remote storage để phục vụ consumer. Độ trễ phụ thuộc network, backend, cache hit, số request đồng thời và kích thước dữ liệu.

Backend cần chịu được tải đồng thời từ nhiều broker và partition. Theo dõi latency p95/p99, lỗi request, throttling, throughput, retry và số lượng request đang chờ. Một backend có throughput cao nhưng latency tail lớn vẫn có thể làm consumer đọc lịch sử chậm.

## 7. Metadata topic và yêu cầu nhất quán

Với implementation mặc định `TopicBasedRemoteLogMetadataManager`, Kafka dùng internal topic `__remote_log_metadata` để lưu metadata remote segment.

Một số cấu hình mặc định trong Kafka 4.4:

| Cấu hình RLMM | Mặc định | Vai trò |
|---|---:|---|
| `remote.log.metadata.topic.num.partitions` | 50 | Số partition của internal metadata topic |
| `remote.log.metadata.topic.replication.factor` | 3 | Replication factor của metadata topic |
| `remote.log.metadata.topic.min.isr` | 2 | Số replica tối thiểu phải xác nhận ghi metadata |
| `remote.log.metadata.topic.retention.ms` | -1 | Không giới hạn thời gian theo mặc định |
| `remote.log.metadata.consume.wait.ms` | 120.000 ms | Thời gian chờ local consumer nhận metadata event |

Các thuộc tính dành cho implementation mặc định được truyền qua prefix `remote.log.metadata.manager.impl.prefix`, mặc định là `rlmm.config.`. Ví dụ:

~~~properties
remote.log.metadata.manager.class.name=org.apache.kafka.server.log.remote.metadata.storage.TopicBasedRemoteLogMetadataManager
remote.log.metadata.manager.listener.name=INTERNAL

rlmm.config.remote.log.metadata.topic.replication.factor=3
rlmm.config.remote.log.metadata.topic.min.isr=2
rlmm.config.remote.log.metadata.topic.num.partitions=50
rlmm.config.remote.log.metadata.topic.retention.ms=-1
~~~

`remote.log.metadata.manager.listener.name` phải chỉ ra listener mà các client nội bộ của implementation mặc định dùng để kết nối broker. Giá trị `INTERNAL` chỉ là ví dụ; listener thực tế phải tồn tại và được cấu hình trong cluster.

Metadata topic có vai trò quan trọng với khả năng đọc remote segment. Retention của nó phải dài hơn retention lớn nhất của mọi topic bật tiered storage để tránh xóa metadata trong khi remote segment vẫn còn hiệu lực.

Trong cluster production, không hạ replication factor hoặc `min.isr` chỉ để vượt qua lỗi cấu hình. Với lab một broker, có thể cần đặt RF và min ISR bằng 1; cấu hình đó không đại diện cho khả năng chịu lỗi production.

## 8. Cấu hình broker và bật tiered storage cho topic

Tiered storage bị tắt mặc định. Muốn sử dụng cần bật ở broker và cấu hình implementation RSM.

### 8.1. Cấu hình broker

Ví dụ `server.properties` cho Kafka 4.4:

~~~properties
# Bật dịch vụ tiered storage trên broker
remote.log.storage.system.enable=true

# Implementation do nhà cung cấp plugin cung cấp
remote.log.storage.manager.class.name=com.example.kafka.storage.S3RemoteStorageManager
remote.log.storage.manager.class.path=/opt/kafka/plugins/s3-remote-storage-plugin.jar

# Prefix dành cho cấu hình của plugin RSM
remote.log.storage.manager.impl.prefix=rsm.config.

# Cấu hình ví dụ cho plugin; tên property phụ thuộc implementation
rsm.config.bucket=kafka-remote-logs
rsm.config.region=ap-southeast-1
rsm.config.endpoint=https://object-storage.example.internal
rsm.config.path.style.access=true
~~~

Tên class, class path và các thuộc tính `rsm.config.*` ở trên là placeholder để minh họa. Thay bằng tài liệu của plugin cụ thể. Apache Kafka không có class `S3RemoteStorageManager` mặc định và không thể bật tiered storage production chỉ bằng cách đặt bucket name.

Với implementation mặc định của metadata manager, cấu hình listener và các thuộc tính `rlmm.config.*` như phần trước cũng phải được khai báo.

### 8.2. Bật cho topic

Sau khi tất cả broker có plugin và cấu hình cần thiết, bật tiered storage cho topic:

~~~bash
bin/kafka-topics.sh --create \
  --topic orders-history \
  --bootstrap-server localhost:9092 \
  --partitions 12 \
  --replication-factor 3 \
  --config remote.storage.enable=true \
  --config local.retention.ms=21600000 \
  --config retention.ms=2592000000
~~~

Với topic đã tồn tại, có thể thay đổi cấu hình bằng:

~~~bash
bin/kafka-configs.sh --bootstrap-server localhost:9092 \
  --alter --entity-type topics --entity-name orders-history \
  --add-config remote.storage.enable=true,local.retention.ms=21600000,retention.ms=2592000000
~~~

Kiểm tra cấu hình:

~~~bash
bin/kafka-configs.sh --bootstrap-server localhost:9092 \
  --describe --entity-type topics --entity-name orders-history
~~~

Broker bật remote storage ở cấp cluster nhưng topic vẫn phải opt-in bằng `remote.storage.enable=true`. Giá trị mặc định ở topic là `false`.

## 9. Đường đọc dữ liệu local và remote

Khi consumer gửi Fetch request cho một offset:

1. Broker xác định offset nằm trong local log hay đã chuyển sang remote tier.
2. Nếu offset còn ở local tier, broker đọc local segment theo đường xử lý Kafka thông thường.
3. Nếu offset nằm trong remote tier, broker tra metadata và index để xác định remote segment cùng vị trí cần đọc.
4. Remote reader gọi RSM lấy dữ liệu từ backend.
5. Broker trả record cho consumer theo Kafka protocol.

Remote index có thể được tải về và giữ trong cache local để tránh phải đọc index từ remote storage nhiều lần. Kafka 4.4 có các cấu hình đáng chú ý:

| Cấu hình broker | Mặc định | Vai trò |
|---|---:|---|
| `remote.log.index.file.cache.total.size.bytes` | 1 GiB | Dung lượng cache local dành cho remote index |
| `remote.log.reader.threads` | 10 | Số thread phục vụ remote log read |
| `remote.log.reader.max.pending.tasks` | 100 | Số tác vụ đọc remote tối đa chờ trong queue |
| `remote.fetch.max.wait.ms` | 500 ms | Thời gian tối đa broker chờ remote fetch partition hoàn tất |
| `remote.log.manager.task.interval.ms` | 30.000 ms | Chu kỳ chạy các tác vụ copy và cleanup |

Nếu queue remote reader đầy, fetch request có thể nhận lỗi. Nếu backend chậm, consumer đọc lịch sử có thể tăng latency dù consumer đọc tail data vẫn hoạt động tốt. Cần theo dõi cache hit/miss, số tác vụ chờ, thời gian fetch và lỗi từ remote storage.

## 10. Ảnh hưởng đến replication và phục hồi broker

Tiered storage không loại bỏ replication của Kafka. Các replica local vẫn cần duy trì trạng thái partition, ISR, leader epoch và các quy tắc consistency hiện có.

Khi segment cũ đã được lưu ở remote tier, follower không cần giữ toàn bộ lịch sử đó trên local disk. Follower vẫn phải duy trì trạng thái phụ trợ cần thiết để theo kịp leader và xử lý log truncation hoặc leader change. Khi follower bị offline lâu, quá trình bắt kịp có thể cần tham chiếu remote metadata và trạng thái của remote segment trước khi tiếp tục fetch phần local còn lại.

Điều này có thể giảm lượng dữ liệu phải lưu trên từng broker và lượng dữ liệu local cần copy khi broker thay thế. Tuy nhiên, phục hồi vẫn phụ thuộc remote backend và metadata manager. Nếu backend không truy cập được, các thao tác cần dữ liệu lịch sử từ remote có thể bị trì hoãn.

Không xem remote storage là bản backup duy nhất của toàn cluster. Cần có chiến lược backup/DR, bảo vệ metadata topic, bảo vệ cấu hình plugin và kiểm thử khả năng khôi phục theo yêu cầu RPO/RTO.

## 11. Sự cố thường gặp và cách xử lý

| Triệu chứng | Nguyên nhân có thể | Hướng kiểm tra |
|---|---|---|
| Broker không khởi động khi bật tiered storage | Thiếu RSM class, sai class path hoặc plugin không tương thích | Kiểm tra class name, JAR, dependency và log khởi tạo plugin |
| Topic không upload segment | Topic chưa bật `remote.storage.enable`, segment chưa roll hoặc chưa đủ điều kiện upload | Kiểm tra topic config, segment roll, local retention và copy lag |
| Local disk không giảm dù đã bật tiered storage | Upload backlog, backend lỗi hoặc segment chưa được xác nhận remote metadata | Kiểm tra copy task, RSM error, RLMM và dung lượng local |
| Consumer đọc offset cũ bị chậm hoặc lỗi | Remote backend latency, throttling, index cache miss hoặc reader queue đầy | Kiểm tra remote fetch latency, request rate, cache và reader threads |
| Follower catch-up kéo dài | Local retention ngắn, follower offline lâu hoặc remote metadata chưa đồng bộ | Kiểm tra replica lag, remote segment metadata và truy cập backend |
| Broker khởi động nhưng tiered topic gây lỗi | Metadata topic không sẵn sàng hoặc listener/ACL sai | Kiểm tra `__remote_log_metadata`, RF, min ISR, listener và quyền truy cập |
| Remote object bị thiếu | Lifecycle rule xóa ngoài Kafka hoặc plugin delete/copy không nhất quán | Kiểm tra audit log, bucket lifecycle, object key và metadata |
| Remote storage đầy hoặc chi phí tăng | Overall retention dài, upload delay hoặc không có cleanup hiệu quả | Kiểm tra retention, remote expiration, object count và dung lượng |

Nếu remote backend tạm thời không khả dụng, dữ liệu còn trong local tier có thể tiếp tục được phục vụ theo khả năng hiện có. Các fetch cần remote segment và các tác vụ copy/cleanup bị ảnh hưởng. Khi upload không hoàn tất, Kafka giữ segment local để tránh xóa dữ liệu chưa được lưu từ xa. Nếu sự cố kéo dài, local disk có thể đầy và gây ảnh hưởng đến producer.

## 12. Các giới hạn cần biết trong Kafka 4.4

Theo tài liệu Apache Kafka 4.4:

- Tiered storage **không hỗ trợ compacted topics**.
- Tiered storage **không hỗ trợ JBOD**.
- Phải xử lý các topic đang bật tiered storage trước khi tắt tính năng ở cấp broker.
- Các thao tác Admin liên quan tiered storage chỉ được hỗ trợ với client từ phiên bản 3.0 trở lên.
- Topic cũ thiếu producer snapshot file (có thể gặp với topic được tạo trước Kafka 2.8.0) không được hỗ trợ trong tiered storage.

Vì vậy, cần kiểm tra topic cleanup policy và lịch sử topic trước khi bật. Không chuyển một topic đang dùng `cleanup.policy=compact` sang tiered storage và không dựa vào JBOD khi thiết kế remote tier.

Nếu muốn dừng copy mới nhưng giữ remote log ở chế độ chỉ đọc, Kafka hỗ trợ `remote.log.copy.disable=true` cùng `remote.storage.enable=true`. Khi đó cần đặt `local.retention.ms` và `local.retention.bytes` bằng các giá trị `retention.ms` và `retention.bytes` tương ứng, hoặc đặt cả hai local retention thành `-2`. Local retention sẽ không còn được áp dụng như trước; cấu hình sai có thể khiến local disk đầy.

Nếu muốn tắt tiered storage và xóa remote log của topic, cần chủ động dùng `remote.log.delete.on.disable=true` cùng thao tác disable ở cấp topic. Đây là thao tác có thể xóa dữ liệu remote; hãy xác minh chính sách retention, consumer và yêu cầu replay trước khi thực hiện.

Chỉ tắt `remote.log.storage.system.enable` ở broker sau khi các topic đang dùng tiered storage đã được xử lý hoặc xóa theo quy trình. Kafka có thể từ chối khởi động nếu broker bị tắt tiered storage trong khi vẫn còn topic yêu cầu remote storage.

## 13. Quy trình triển khai và kiểm thử

1. **Xác định use case:** retention cần bao lâu, tỷ lệ đọc dữ liệu cũ, mục tiêu latency và chi phí local/remote.
2. **Chọn backend và plugin:** xác minh plugin hỗ trợ đúng Kafka release, API, authentication, region/endpoint và khả năng vận hành.
3. **Thiết kế metadata:** chọn RLMM, bảo đảm internal topic có replication factor, min ISR, listener và retention phù hợp.
4. **Thiết kế local retention:** giữ đủ hot data cho tail reads, replication catch-up và khoảng thời gian backend có thể gián đoạn.
5. **Bật broker feature:** cấu hình RSM, RLMM, class path, credentials và network trên tất cả broker liên quan.
6. **Bật thử trên topic chuyên biệt:** chọn topic không compacted, dùng segment nhỏ trong môi trường test để dễ tạo segment đã roll.
7. **Kiểm thử upload:** gửi record đủ để segment roll, xác nhận object log và index xuất hiện ở remote backend, metadata được publish.
8. **Kiểm thử đọc:** đọc offset còn local và offset đã remote bằng console consumer hoặc ứng dụng consumer thông thường.
9. **Kiểm thử retention:** xác nhận local segment chỉ bị xóa sau khi copy thành công và remote segment chỉ bị xóa khi overall retention hết hạn.
10. **Kiểm thử lỗi:** ngắt quyền truy cập backend, gây timeout, khởi động lại broker, follower catch-up và khôi phục backend.
11. **Đo tải:** kiểm tra copy throughput, remote fetch latency, index cache, queue, network, disk và chi phí object storage.
12. **Triển khai theo giai đoạn:** bật cho một nhóm topic trước, quan sát ổn định rồi mới mở rộng.

### Checklist trước production

- [ ] Broker Kafka và plugin RSM/RLMM có phiên bản tương thích.
- [ ] Tất cả broker cần thiết truy cập được cùng remote storage namespace.
- [ ] Remote backend có quyền đọc/ghi/xóa, TLS và credential rotation.
- [ ] RSM xử lý được segment, index, retry và delete.
- [ ] RLMM cung cấp metadata với semantics nhất quán mạnh.
- [ ] Internal topic `__remote_log_metadata` có RF, min ISR, listener và retention phù hợp.
- [ ] Topic bật tiered storage không dùng compact cleanup policy.
- [ ] `local.retention.*` không vượt `retention.*`.
- [ ] Local disk đủ chỗ cho active segment và upload backlog khi remote storage gián đoạn.
- [ ] Object lifecycle bên ngoài không xóa segment sớm hơn Kafka retention.
- [ ] Đã thử đọc offset local và remote bằng consumer hiện tại.
- [ ] Đã thử follower catch-up, broker restart và remote backend outage.
- [ ] Có cảnh báo cho upload lag, remote fetch latency, error rate, queue và disk usage.
- [ ] Có quy trình tắt tiered storage và xóa remote data được phê duyệt, kiểm thử.

## 14. Tài liệu tham khảo

- [Apache Kafka 4.4 – Tiered Storage Operations](https://kafka.apache.org/44/operations/tiered-storage/)
- [Apache Kafka 4.4 – Tiered Storage Configs](https://kafka.apache.org/44/configuration/tiered-storage-configs/)
- [Apache Kafka – KIP-405: Kafka Tiered Storage](https://cwiki.apache.org/confluence/display/KAFKA/KIP-405%3A+Kafka+Tiered+Storage)
- [Apache Kafka – Tiered Storage GA Release Notes](https://cwiki.apache.org/confluence/display/KAFKA/Kafka+Tiered+Storage+GA+Release+Notes)

Tiered storage giúp Kafka giữ dữ liệu dài hạn mà không buộc toàn bộ log phải nằm trên local disk của broker. Để vận hành an toàn, cần coi remote storage, remote metadata, local retention và replication là các phần của cùng một vòng đời segment; thiếu một trong các phần này có thể khiến dữ liệu cũ không đọc được hoặc local disk không được giải phóng đúng lúc.
