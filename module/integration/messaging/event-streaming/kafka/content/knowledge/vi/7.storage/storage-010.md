# Segment roll, log cleaner và tác động đến dung lượng

## Mục tiêu bài học

Kafka lưu dữ liệu của mỗi partition dưới dạng một log được chia thành nhiều segment. Broker ghi record vào segment đang hoạt động; khi segment đạt ngưỡng kích thước hoặc thời gian, Kafka đóng segment đó và tạo segment mới. Việc chuyển segment được gọi là *segment roll*. Các segment đã đóng sau đó có thể được xử lý bởi retention hoặc log cleaner tùy chính sách của topic.

Segment roll, retention và log cleaner có liên hệ trực tiếp đến dung lượng đĩa, số lượng file, độ trễ dọn dữ liệu và tải I/O của broker. Bài học này giải thích vòng đời segment, cách log cleaner compact dữ liệu theo key, cách chọn cấu hình và cách ước lượng dung lượng để tránh broker hết đĩa.

Sau bài học, người học có thể:

- Mô tả cấu trúc log directory, partition và segment.
- Giải thích điều kiện roll theo kích thước, thời gian và jitter.
- Phân biệt segment roll, retention delete và log compaction.
- Giải thích cách log cleaner chọn log, loại record cũ và xử lý tombstone.
- Đánh giá tác động của kích thước segment và chính sách cleanup đến dung lượng.
- Ước lượng storage theo ingest rate, retention, replication factor và headroom.
- Kiểm tra cấu hình topic, log directory và dấu hiệu cleaner không theo kịp.

## 1. Cấu trúc lưu trữ của một partition

Topic là đơn vị logic mà producer và consumer sử dụng. Bên trong topic, mỗi partition là một log độc lập được lưu trên broker đang giữ replica của partition đó. Một partition không được lưu trong một file duy nhất; log được chia thành nhiều segment để Kafka có thể ghi, đọc, compact và xóa dữ liệu theo từng phần.

Ví dụ một partition có các segment:

~~~mermaid
flowchart LR
    subgraph LOG[Topic orders - Partition 0]
        S0[Segment base offset 0]
        S1[Segment base offset 120]
        S2[Active segment base offset 245]
        S0 --> S1 --> S2
    end
    S0 --- I0[Log index]
    S1 --- I1[Log index]
    S2 --- I2[Log index]
~~~

Mỗi segment có một base offset, thường được thể hiện trong tên file. Segment chứa record batch theo thứ tự offset. Segment cuối cùng đang nhận record mới được gọi là *active segment*. Các segment trước đó đã đóng và có thể trở thành ứng viên cho retention hoặc compaction.

### 1.1. Các file thường thấy

Trong log directory của Kafka, một partition có thể có các file như:

| File | Vai trò |
|---|---|
| «00000000000000000000.log» | Record batch được lưu trong segment có base offset tương ứng |
| «00000000000000000000.index» | Offset index thưa, giúp tìm vị trí byte gần offset cần đọc |
| «00000000000000000000.timeindex» | Timestamp index, hỗ trợ tìm record theo thời gian |
| «00000000000000000000.txnindex» | Transaction index, dùng cho thông tin transaction/aborted transaction khi cần |

Không phải mọi segment đều có đủ mọi loại file phụ trợ trong mọi thời điểm. Kafka có thể tạo hoặc mở rộng index khi log hoạt động. Index là dữ liệu phụ trợ để định vị nhanh, không phải bản sao nội dung record.

Ví dụ cấu trúc thư mục:

~~~text
/var/lib/kafka/data/
  orders-0/
    00000000000000000000.log
    00000000000000000000.index
    00000000000000000000.timeindex
    00000000000000000120.log
    00000000000000000120.index
    00000000000000000120.timeindex
    00000000000000000245.log
    00000000000000000245.index
    00000000000000000245.timeindex
~~~

Tên thư mục «orders-0» minh họa partition 0 của topic «orders». Cấu trúc thực tế còn có thể chứa checkpoint, metadata và các file khác do phiên bản Kafka quản lý. Không chỉnh sửa hoặc xóa trực tiếp các file này khi broker đang chạy.

### 1.2. Vì sao Kafka chia log thành segment?

Segment giúp Kafka quản lý log lớn theo từng đơn vị hữu hạn:

- Broker ghi nối tiếp vào active segment, giảm việc phải cập nhật file cũ.
- Index theo segment giúp định vị record mà không phải quét toàn bộ partition.
- Retention có thể xóa các segment cũ đủ điều kiện thay vì xóa từng record.
- Log cleaner có thể compact các segment đã đóng trong khi active segment tiếp tục nhận ghi.
- Việc roll giới hạn kích thước file và tạo ranh giới quản lý rõ ràng.

Segment không phải một partition mới. Một partition vẫn giữ một dãy offset liên tục theo logic của log, dù dữ liệu vật lý nằm trong nhiều segment.

## 2. Segment roll hoạt động như thế nào?

Segment roll là quá trình đóng active segment và tạo segment mới. Roll không đồng nghĩa với xóa dữ liệu. Các record trong segment vừa đóng vẫn còn trên đĩa và có thể tiếp tục được consumer đọc theo offset.

~~~mermaid
flowchart TD
    A[Producer gửi record] --> B[Broker append vào active segment]
    B --> C{Đạt điều kiện roll?}
    C -->|Chưa| B
    C -->|Rồi| D[Đóng segment hiện tại]
    D --> E[Tạo active segment mới]
    E --> F[Segment cũ chờ cleanup policy]
    F --> G{cleanup.policy}
    G -->|delete| H[Retention xóa segment đủ điều kiện]
    G -->|compact| I[Log cleaner compact segment]
    G -->|compact,delete| J[Cleaner và retention cùng áp dụng]
~~~

### 2.1. Roll theo kích thước

«segment.bytes» là cấu hình topic xác định kích thước segment mục tiêu. Khi segment đạt ngưỡng, Kafka roll sang segment mới. Nếu topic không đặt override, broker dùng giá trị mặc định «log.segment.bytes».

Ví dụ cấu hình topic:

~~~properties
segment.bytes=268435456
~~~

Giá trị trên tương đương 256 MiB. Đây là ngưỡng roll, không phải cam kết rằng mọi file segment sẽ có kích thước chính xác bằng 256 MiB. Việc append theo record batch, kích thước record và thời điểm kiểm tra điều kiện roll có thể khiến kích thước thực tế chênh lệch.

Segment nhỏ tạo nhiều file và index hơn. Segment lớn giảm số lượng file nhưng làm đơn vị retention/compaction lớn hơn và có thể khiến dữ liệu cũ chờ lâu hơn mới trở thành segment đã đóng.

### 2.2. Roll theo thời gian

«segment.ms» đặt khoảng thời gian tối đa mà Kafka cho phép một segment tiếp tục hoạt động trước khi roll theo điều kiện thời gian. Broker có cấu hình mặc định «log.roll.ms»; cấu hình topic có thể override bằng «segment.ms».

Ví dụ:

~~~properties
segment.ms=3600000
~~~

Giá trị này tương đương một giờ. Điều kiện thời gian hữu ích với topic có tốc độ ghi thấp: nếu chỉ dựa vào kích thước, active segment có thể mở rất lâu và các segment trước đó ít có cơ hội được đóng để cleanup.

Điều kiện roll được đánh giá trong quá trình log nhận hoạt động. Không nên hiểu «segment.ms» là bộ hẹn giờ đảm bảo file mới được tạo chính xác vào đúng mili giây khi hết hạn, đặc biệt khi topic không có record mới.

### 2.3. Segment jitter

«segment.jitter.ms» cho phép thêm độ lệch ngẫu nhiên vào thời gian roll. Ở cấp broker có cấu hình «log.roll.jitter.ms».

Jitter giúp tránh tình huống nhiều partition được tạo cùng lúc và cùng thời điểm roll, dẫn đến tải I/O dồn cục bộ trên broker. Điều này hữu ích khi broker có nhiều partition với nhịp ghi tương tự nhau.

### 2.4. Cấu hình topic và broker

Các cấu hình phổ biến:

| Cấu hình topic | Cấu hình broker mặc định | Ý nghĩa |
|---|---|---|
| «segment.bytes» | «log.segment.bytes» | Ngưỡng kích thước segment |
| «segment.ms» | «log.roll.ms» | Ngưỡng thời gian roll |
| «segment.jitter.ms» | «log.roll.jitter.ms» | Độ lệch ngẫu nhiên thời gian roll |

Khi debug, hãy xem cấu hình hiệu lực của topic thay vì chỉ đọc «server.properties». Giá trị ở cấp topic có thể ghi đè giá trị mặc định của broker.

## 3. Segment roll tác động đến dung lượng ra sao?

Segment roll tự nó không làm giảm dung lượng log. Nó chỉ đóng file hiện tại và mở file mới. Dung lượng chỉ giảm khi một cleanup policy thực sự loại bỏ dữ liệu và hệ thống file thu hồi các block tương ứng.

Roll ảnh hưởng gián tiếp đến dung lượng và vận hành theo các cách:

- Tạo thêm segment file và index file, làm tăng số file và metadata filesystem.
- Tạo ranh giới để retention có thể xóa segment cũ.
- Tạo segment đã đóng để log cleaner có thể xử lý.
- Segment quá nhỏ làm tăng số lượng index, file handle và công việc scan.
- Segment quá lớn có thể làm cleanup theo lô thô hơn và tăng lượng dữ liệu phải xử lý trong một lần.

### 3.1. Segment nhỏ và segment lớn

| Tiêu chí | Segment nhỏ | Segment lớn |
|---|---|---|
| Số lượng file | Nhiều | Ít |
| Số index và metadata file | Tăng | Giảm tương đối |
| Tần suất roll | Cao hơn | Thấp hơn |
| Độ hạt retention | Nhỏ hơn | Lớn hơn |
| Đơn vị công việc cleaner | Nhỏ hơn, nhiều segment | Lớn hơn, ít segment |
| Khả năng tạo I/O dồn cục bộ | Có thể tăng do nhiều lần roll | Có thể tăng khi một segment lớn cần xử lý |

Không có một kích thước segment tốt cho mọi topic. Topic có throughput cao, topic ít record và compacted topic có đặc tính khác nhau. Hãy chọn ngưỡng theo lưu lượng, retention, số partition, năng lực disk và khả năng xử lý cleanup.

### 3.2. Retention xóa theo segment

Với «cleanup.policy=delete», Kafka xóa các segment cũ khi chúng đủ điều kiện theo «retention.ms» hoặc «retention.bytes». Kafka không thường xuyên cắt bỏ từng record cũ nằm giữa một segment đang còn hiệu lực.

Hệ quả là:

- Record đã quá tuổi retention có thể vẫn còn cho đến khi segment chứa nó đủ điều kiện xóa.
- Một segment có record mới hơn ở cuối có thể tiếp tục được giữ dù một số record đầu segment đã cũ.
- Segment roll ảnh hưởng đến độ hạt và thời điểm dữ liệu trở thành ứng viên xóa.
- «retention.bytes» được áp dụng theo log của từng partition, không phải một giới hạn tổng duy nhất cho toàn topic.

Vì vậy, retention là chính sách lưu trữ theo segment và không nên xem như cam kết xóa chính xác từng record ngay khi hết hạn.

## 4. Log cleaner và log compaction

Log cleaner là tiến trình nền trên broker dùng để compact các log có «cleanup.policy=compact». Compaction giữ lại phiên bản mới nhất của record theo key trong vùng log đã được xử lý, từ đó giảm dữ liệu lặp và hỗ trợ khôi phục trạng thái hiện tại.

Ví dụ topic «account-state» nhận:

| Offset | Key | Value |
|---:|---|---|
| 0 | «account-1» | «balance=100» |
| 1 | «account-2» | «balance=50» |
| 2 | «account-1» | «balance=130» |
| 3 | «account-1» | «balance=120» |

Sau compaction, Kafka có thể loại bỏ các phiên bản cũ của «account-1» và giữ lại phiên bản mới nhất «balance=120», cùng phiên bản mới nhất của «account-2».

~~~mermaid
flowchart LR
    subgraph BEFORE[Log trước compaction]
        A0["0: account-1 = 100"]
        A1["1: account-2 = 50"]
        A2["2: account-1 = 130"]
        A3["3: account-1 = 120"]
        A0 --> A1 --> A2 --> A3
    end
    subgraph AFTER[Record còn lại sau compaction]
        B1["1: account-2 = 50"]
        B3["3: account-1 = 120"]
        B1 --> B3
    end
    BEFORE -->|Cleaner| AFTER
~~~

Compaction không biến Kafka thành một bảng key-value thông thường. Log vẫn giữ offset gốc của record còn lại; sau khi loại record cũ, offset có thể có khoảng trống. Consumer vẫn đọc theo offset của partition.

### 4.1. Cleaner xử lý log như thế nào?

Quy trình tổng quát:

1. Cleaner tìm các partition có «cleanup.policy=compact» và vùng log đủ điều kiện xử lý.
2. Cleaner xác định ranh giới giữa vùng đã clean và vùng dirty.
3. Cleaner xây dựng offset map từ key đến offset mới nhất trong vùng cần compact.
4. Cleaner đọc các segment đã đóng, bỏ record cũ có key đã có phiên bản mới hơn.
5. Cleaner ghi các segment đã compact ra file thay thế.
6. Khi segment mới sẵn sàng, Kafka thay thế segment cũ và cập nhật trạng thái checkpoint.

Active segment đang nhận record mới thường không được compact như segment đã đóng. Vì vậy segment roll là điều kiện quan trọng để cleaner có thêm dữ liệu có thể xử lý.

Cleaner hoạt động nền và không nhất thiết compact ngay sau mỗi lần producer ghi một key mới. Có độ trễ giữa lúc record được ghi và lúc phiên bản cũ được loại bỏ.

### 4.2. Dirty ratio

«min.cleanable.dirty.ratio» điều khiển tỷ lệ vùng log chưa được compact so với phần log được xem xét trước khi cleaner coi log là đủ điều kiện. Giá trị thấp làm cleaner có thể chạy thường xuyên hơn, giảm thời gian dữ liệu trùng tồn tại nhưng tăng I/O và CPU. Giá trị cao giảm tần suất cleanup nhưng có thể khiến nhiều phiên bản cũ nằm trên đĩa lâu hơn.

Ví dụ cấu hình topic:

~~~properties
cleanup.policy=compact
min.cleanable.dirty.ratio=0.3
~~~

Giá trị 0.3 chỉ là ví dụ để thảo luận, không phải giá trị tối ưu chung. Khi chọn, cần quan sát tốc độ ghi, số lượng key, dung lượng dirty log và tài nguyên cleaner.

### 4.3. Compaction lag

Hai cấu hình liên quan đến thời gian:

- «min.compaction.lag.ms»: khoảng thời gian tối thiểu record phải tồn tại trước khi có thể bị compact. Nó hữu ích khi consumer cần một khoảng thời gian để quan sát mọi phiên bản mới.
- «max.compaction.lag.ms»: giới hạn thời gian mà record chưa được compact có thể chờ trước khi trở thành ứng viên cleanup theo cơ chế cấu hình.

Các giá trị này không biến cleaner thành tác vụ thời gian thực. Cleaner vẫn cần tài nguyên và thời gian để đọc, lập offset map, ghi lại segment. Nếu cleaner bị quá tải, dữ liệu cũ có thể tồn tại lâu hơn dự kiến.

### 4.4. Tombstone

Trong compacted topic, record có key và value «null» được gọi là tombstone. Tombstone biểu thị rằng key đó đã bị xóa logic.

Ví dụ:

~~~text
offset=10 key=account-7 value=balance=100
offset=25 key=account-7 value=null
~~~

Sau khi compaction xử lý vùng log, phiên bản value cũ của «account-7» có thể bị loại bỏ. Tombstone được giữ trong khoảng thời gian theo «delete.retention.ms» để consumer có cơ hội nhìn thấy tín hiệu xóa; sau thời gian này, tombstone cũng có thể bị cleaner loại bỏ.

Điều này có ý nghĩa với ứng dụng dựng lại state từ compacted topic: consumer cần có cơ hội đọc tombstone trong cửa sổ lưu giữ. Không dùng null key để biểu diễn xóa; tombstone cần key xác định và value null.

### 4.5. Record nào được giữ lại?

- Với cùng một key, cleaner giữ phiên bản mới nhất trong vùng đã compact.
- Record không có key không thể được khử trùng lặp theo key như record có key.
- Record có key khác nhau đều có thể được giữ lại.
- Tombstone được giữ tạm thời theo «delete.retention.ms», sau đó có thể bị loại bỏ.
- Offset của record còn lại không bị đánh số lại sau compaction.

Compaction phù hợp cho topic biểu diễn trạng thái mới nhất như cấu hình, trạng thái tài khoản hoặc bảng tra cứu. Nếu cần giữ toàn bộ lịch sử nghiệp vụ để audit hoặc replay mọi thay đổi, hãy chọn retention delete phù hợp hoặc một thiết kế lưu trữ lịch sử riêng.

## 5. Phân biệt delete, compact và compact,delete

«cleanup.policy» quyết định Kafka xử lý dữ liệu cũ như thế nào:

| Chính sách | Hành vi | Trường hợp phù hợp |
|---|---|---|
| «delete» | Xóa segment đủ điều kiện theo retention time/size | Event history cần giữ trong một khoảng thời gian |
| «compact» | Giữ phiên bản mới nhất theo key trong log đã compact | Topic biểu diễn trạng thái hiện tại |
| «compact,delete» | Vừa compact theo key vừa áp dụng giới hạn retention | State topic cần giới hạn tuổi dữ liệu |

Ví dụ topic «orders» cần lưu lịch sử sự kiện bảy ngày có thể dùng «delete». Topic «account-state» cần giữ trạng thái mới nhất theo account key có thể dùng «compact». Không chọn «compact» cho event history nếu nghiệp vụ yêu cầu mọi phiên bản phải còn nguyên.

## 6. Cấu hình segment và cleaner

### 6.1. Cấu hình ở cấp topic

Ví dụ tạo topic compacted với segment nhỏ hơn để dễ quan sát trong lab:

~~~bash
kafka-topics.sh --bootstrap-server localhost:9092 \
  --create --topic account-state \
  --partitions 3 --replication-factor 1 \
  --config cleanup.policy=compact \
  --config segment.bytes=10485760 \
  --config segment.ms=60000 \
  --config min.cleanable.dirty.ratio=0.3 \
  --config delete.retention.ms=86400000
~~~

Trong ví dụ:

- «segment.bytes=10485760» tương đương 10 MiB.
- «segment.ms=60000» đặt ngưỡng thời gian roll một phút.
- «min.cleanable.dirty.ratio=0.3» là ngưỡng dirty ratio minh họa.
- «delete.retention.ms=86400000» là một ngày lưu tombstone.
- «replication-factor=1» chỉ phù hợp cho lab một broker, không có bản sao dự phòng.

Kích thước nhỏ và thời gian roll ngắn giúp quan sát nhiều segment nhanh hơn, nhưng không phải cấu hình khuyến nghị cho production.

### 6.2. Cấu hình ở cấp broker

Một số broker setting thường được quản trị viên quan tâm:

~~~properties
# Segment mặc định nếu topic không override.
log.segment.bytes=1073741824
log.roll.ms=604800000
log.roll.jitter.ms=0

# Chu kỳ kiểm tra retention.
log.retention.check.interval.ms=300000

# Cleaner cho compacted topics.
log.cleaner.enable=true
log.cleaner.threads=1
log.cleaner.dedupe.buffer.size=134217728
~~~

Các giá trị trên là ví dụ cấu hình minh họa; hãy đối chiếu default và giới hạn của đúng phiên bản Kafka trước khi áp dụng. Không cần đặt mọi thuộc tính trong mọi cụm. Topic config có thể override một số mặc định broker như segment size hoặc segment time.

«log.cleaner.threads» điều khiển số luồng cleaner. Tăng số thread có thể tăng khả năng xử lý đồng thời nhưng cũng làm tăng cạnh tranh CPU, RAM và disk I/O. «log.cleaner.dedupe.buffer.size» là bộ nhớ dùng cho cấu trúc map phục vụ khử trùng lặp key; nếu dữ liệu có rất nhiều key duy nhất, buffer không đủ có thể làm giảm hiệu quả xử lý mỗi lượt.

### 6.3. Xem cấu hình hiệu lực của topic

~~~bash
kafka-configs.sh --bootstrap-server localhost:9092 \
  --entity-type topics --entity-name account-state --describe
~~~

Đọc cả cấu hình topic và cấu hình broker để hiểu giá trị nào đang áp dụng. Nếu topic có override «segment.bytes», thay đổi «log.segment.bytes» ở broker sẽ không thay đổi ngưỡng của topic đó.

## 7. Ước lượng dung lượng lưu trữ

Dung lượng cần thiết phụ thuộc vào tốc độ dữ liệu vào, thời gian lưu, replication factor, compression, phân bố partition, index và khoảng trống cần thiết cho cleanup.

### 7.1. Công thức ước lượng ban đầu

Gọi:

- «R»: tốc độ dữ liệu ghi vào sau compression, tính bằng byte/giây.
- «T»: thời gian retention, tính bằng giây.
- «RF»: replication factor.
- «H»: hệ số headroom cho index, metadata, cleaner workspace và dao động tải.

Ước lượng dung lượng toàn cluster cho topic dùng delete retention:

\[
Storage \approx R \times T \times RF \times (1 + H)
\]

Ví dụ topic ghi trung bình 2 MiB/s, giữ bảy ngày, replication factor bằng ba và dự trù headroom 25%:

\[
2 \times 1024^2 \times 604800 \times 3 \times 1.25
\]

Kết quả là ước lượng dung lượng toàn cluster cho topic đó. Khi chia dung lượng cho từng broker, phải xét replica placement, số partition, các broker đang giữ leader/follower và mức phân bố thực tế; không mặc định mọi broker có dung lượng sử dụng bằng nhau.

Đây là công thức sizing ban đầu. Với nhiều topic, hãy tính từng topic rồi cộng lại, đồng thời cộng thêm internal topic, metadata, log khác và dung lượng dành cho vận hành.

### 7.2. Replication làm tăng dung lượng vật lý

Nếu một partition có replication factor bằng ba, dữ liệu của partition đó được lưu trên ba broker. Dung lượng vật lý của cluster vì thế lớn hơn dung lượng logical của topic. Tăng replication factor cải thiện khả năng chịu lỗi nhưng tăng disk usage và replication traffic.

### 7.3. Compacted topic có mô hình dung lượng khác

Với «cleanup.policy=compact», dung lượng ổn định phụ thuộc nhiều vào số key duy nhất và kích thước phiên bản mới nhất của mỗi key, cộng với:

- Các phiên bản cũ đang chờ cleaner xử lý.
- Tombstone còn trong thời gian lưu giữ.
- Active segment chưa đóng.
- Segment đang được cleaner tạo lại và khoảng trống cần cho quá trình thay thế.
- Index và metadata của từng segment.

Không sizing compacted topic chỉ bằng số key hiện tại. Trong thời gian cleaner chưa theo kịp, log có thể lớn hơn nhiều so với tập trạng thái cuối cùng.

### 7.4. Cleaner cần khoảng trống đĩa

Khi compaction, Kafka đọc segment cũ và ghi segment đã compact trước khi thay thế file cũ. Trong giai đoạn chuyển đổi, cả dữ liệu cũ lẫn dữ liệu mới có thể cùng chiếm dung lượng. Nếu disk gần đầy, cleaner có thể không có đủ chỗ để hoàn tất công việc, khiến dữ liệu cũ tiếp tục tích tụ.

Vì vậy, headroom phải tính cả peak storage trong lúc cleaner làm việc, không chỉ dung lượng ổn định sau cleanup. Tránh đặt ngưỡng cảnh báo disk quá sát 100%.

## 8. Số lượng segment và chi phí vận hành

Một ước lượng thô về số segment:

\[
SegmentCount \approx \frac{RetainedBytesPerPartition}{segment.bytes}
\]

Đây chỉ là ước lượng vì segment cuối có thể chưa đầy, segment có thể roll theo thời gian và compaction/retention làm thay đổi số segment.

Khi có nhiều partition, số segment và index file tăng theo tổng số partition trên broker. Quá nhiều segment có thể làm tăng:

- Số file cần mở và quản lý.
- Metadata filesystem và chi phí directory scan.
- Số index file và chi phí cache.
- Công việc kiểm tra retention và lập lịch cleaner.
- Thời gian khởi động, phục hồi và kiểm tra log directory trong một số tình huống.

Ngược lại, segment quá lớn làm chậm khả năng cleanup theo từng phần và có thể làm tăng peak disk usage trong lúc compact. Cần cân bằng giữa số file, kích thước cleanup unit và đặc tính workload.

## 9. Quan sát storage và cleaner bằng công cụ

### 9.1. Kiểm tra topic và partition

~~~bash
kafka-topics.sh --bootstrap-server localhost:9092 \
  --describe --topic account-state
~~~

Lệnh cho biết partition, leader, replica và ISR. Nó không hiển thị trực tiếp kích thước từng segment, nhưng giúp xác định partition được đặt trên broker nào.

### 9.2. Kiểm tra log directory của broker

~~~bash
kafka-log-dirs.sh --bootstrap-server localhost:9092 \
  --describe --broker-list 0
~~~

Thay broker ID theo cụm thực tế. Kết quả có thể cung cấp log directory, topic-partition và kích thước log trên broker. Đối chiếu với số liệu filesystem để tìm broker hoặc volume đang tăng dung lượng nhanh.

### 9.3. Kiểm tra cấu hình cleanup

~~~bash
kafka-configs.sh --bootstrap-server localhost:9092 \
  --entity-type topics --entity-name account-state --describe
~~~

Kiểm tra «cleanup.policy», «segment.bytes», «segment.ms», «min.cleanable.dirty.ratio», «min.compaction.lag.ms», «max.compaction.lag.ms», «delete.retention.ms» và retention settings có liên quan.

### 9.4. Theo dõi metric

Kết hợp JMX/exporter và hệ thống monitoring để theo dõi:

- Disk usage và tốc độ tăng dung lượng theo broker/log directory.
- Số partition, số segment và số file trong log directory.
- Log cleaner backlog hoặc mức độ dirty log còn chờ cleanup.
- Cleaner I/O, thời gian xử lý và mức sử dụng buffer.
- CPU, heap, garbage collection và disk latency của broker.
- Under-replicated partition và replica lag để phân biệt cleanup issue với replication issue.

Tên metric cụ thể thay đổi theo phiên bản và cách export JMX. Hãy lấy metric từ broker đang chạy, xác nhận MBean/metric mapping trước khi viết alert cố định.

## 10. Chẩn đoán sự cố thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra và xử lý |
|---|---|---|
| Disk tăng liên tục ở topic delete | Retention dài, segment chưa đủ điều kiện xóa, retention check chậm hoặc ingest tăng | Kiểm tra «retention.ms», «retention.bytes», segment roll và log directory |
| Compacted topic lớn hơn dự kiến | Cleaner backlog, dirty ratio cao, key cardinality lớn hoặc tombstone còn hạn | Kiểm tra cleaner metrics, compaction lag, dirty log và phân bố key |
| Cleaner dùng nhiều CPU/I/O | Quá nhiều log cần compact, nhiều key duy nhất hoặc cleaner thread hoạt động mạnh | Theo dõi backlog và disk latency; điều chỉnh thread/buffer/throttle dựa trên benchmark |
| Cleaner không giải phóng dung lượng | Active segment chưa đóng, cleaner chưa xử lý đến vùng dirty hoặc topic không bật compact | Kiểm tra «cleanup.policy», segment roll và trạng thái cleaner |
| Số lượng file rất lớn | Segment quá nhỏ, quá nhiều partition hoặc retention dài | Đánh giá «segment.bytes», «segment.ms», partition count và filesystem |
| Broker hết đĩa trong lúc compaction | Không còn headroom cho segment thay thế | Khôi phục dung lượng an toàn, giảm tải ghi nếu cần và kiểm tra cleaner; không xóa thủ công file log |
| Tombstone biến mất trước khi ứng dụng thấy | Consumer không đọc trong cửa sổ «delete.retention.ms» hoặc group lag quá lớn | Điều chỉnh retention tombstone và đảm bảo consumer catch up trong thời gian yêu cầu |
| Retention xóa chậm hơn mong đợi | Segment chưa roll hoặc cleanup check chưa đến chu kỳ | Kiểm tra segment age, traffic mới và «log.retention.check.interval.ms» |

Không xóa trực tiếp «.log», «.index» hoặc «.timeindex» để lấy dung lượng. Xóa file thủ công có thể làm hỏng log và metadata mà broker đang quản lý. Hãy dùng retention, reassignment hoặc quy trình vận hành được hỗ trợ.

## 11. Quy trình chọn cấu hình trong thực tế

Khi thiết kế topic mới, thực hiện theo trình tự:

1. **Xác định loại dữ liệu:** event history hay state theo key. Chọn «delete», «compact» hoặc «compact,delete» theo yêu cầu đọc lại.
2. **Ước lượng ingest:** đo bytes/giây sau compression và tốc độ tăng trong giờ cao điểm.
3. **Chọn retention:** xác định thời gian lưu và giới hạn dung lượng theo partition.
4. **Chọn segment:** cân bằng «segment.bytes» và «segment.ms» với tốc độ ghi, số partition và cleanup latency.
5. **Chọn compaction settings:** nếu dùng compact, đánh giá dirty ratio, min/max compaction lag, tombstone retention và số key duy nhất.
6. **Tính replication:** nhân dung lượng logical với replication factor và phân bổ theo broker.
7. **Dành headroom:** tính index, cleaner workspace, rebalance/reassignment và tăng trưởng đột biến.
8. **Đo trong staging:** tạo tải gần thực tế, quan sát segment roll, cleaner throughput, disk usage và consumer lag.
9. **Thiết lập cảnh báo:** cảnh báo sớm theo disk utilization, tốc độ tăng, cleaner backlog và replication health.

Không có một bộ cấu hình segment/cleaner phù hợp cho mọi topic. Hãy cấu hình theo đặc tính từng luồng dữ liệu và kiểm tra tác động trên broker thật trước khi mở rộng.

## 12. Bài tập thực hành và câu hỏi tự kiểm tra

### Bài tập 1: Quan sát segment roll

1. Tạo topic «segment-lab» với một partition và replication factor bằng một.
2. Đặt «segment.bytes» nhỏ, ví dụ 1 MiB, trong môi trường lab.
3. Gửi đủ record để log vượt nhiều lần ngưỡng segment.
4. Dùng «kafka-log-dirs.sh» và filesystem để quan sát kích thước log directory.
5. Giải thích vì sao segment roll không làm dung lượng giảm ngay.

### Bài tập 2: Quan sát log cleaner

1. Tạo topic «state-lab» với «cleanup.policy=compact».
2. Gửi nhiều phiên bản value cho cùng một tập key.
3. Dùng key có độ phân tán khác nhau để so sánh số record còn lại sau compaction.
4. Quan sát cleaner metrics và disk usage trong lúc cleaner chạy.
5. Giải thích vì sao dung lượng không giảm ngay khi producer ghi phiên bản mới.

### Bài tập 3: So sánh delete và compact

1. Tạo «events-lab» với «cleanup.policy=delete» và retention ngắn.
2. Tạo «state-lab» với «cleanup.policy=compact».
3. Gửi dữ liệu tương đương vào hai topic.
4. Theo dõi số segment và dung lượng qua nhiều chu kỳ roll/cleanup.
5. So sánh record nào còn lại và vì sao hai topic có dung lượng khác nhau.

### Câu hỏi tự kiểm tra

1. Segment khác partition ở điểm nào?
2. Segment roll có trực tiếp xóa dữ liệu không?
3. Vì sao segment đã đóng quan trọng với retention và log cleaner?
4. «segment.bytes» và «segment.ms» điều khiển hai điều kiện roll nào?
5. «min.cleanable.dirty.ratio» ảnh hưởng thế nào đến cleaner I/O và dung lượng?
6. Tombstone có vai trò gì trong compacted topic?
7. Vì sao cleaner cần disk headroom trong lúc ghi segment thay thế?
8. Replication factor ảnh hưởng thế nào đến dung lượng vật lý toàn cluster?
9. Tại sao «retention.bytes» cần được đánh giá theo từng partition?
10. Khi disk tăng liên tục, cần kiểm tra những chỉ số nào trước khi thay đổi cấu hình?

Khi hiểu segment roll là ranh giới vật lý của log, retention là cơ chế xóa segment theo chính sách và log cleaner là cơ chế compact theo key, người vận hành có thể dự báo dung lượng, kiểm soát I/O cleanup và tránh để broker cạn storage.
