# Quan sát consumer group và offset bằng công cụ dòng lệnh

Kafka cung cấp công cụ dòng lệnh để kiểm tra consumer group đang hoạt động, thành viên nào đang sở hữu partition và consumer đã commit đến offset nào. Lệnh quan trọng nhất là `kafka-consumer-groups`. Kết quả `--describe` giúp đối chiếu offset đã commit với log end offset để ước lượng consumer lag.

Trong bài thực hành này, bạn tạo một topic, chạy console consumer với một group ID, gửi một số sự kiện rồi quan sát trạng thái group và offset từ terminal. Các ví dụ dùng broker tại `localhost:9092` và topic `orders`; hãy thay địa chỉ broker, tên topic và group ID theo môi trường của bạn.

## 1. Chuẩn bị môi trường

Bạn cần có:

- Một Kafka cluster đang chạy và có thể kết nối bằng địa chỉ bootstrap server.
- Kafka command-line tools cùng phiên bản tương thích với môi trường đang sử dụng.
- Quyền đọc metadata và consumer group. Các lệnh xem group cần truy cập broker và group coordinator; cluster bảo mật có thể yêu cầu file cấu hình client.
- Ba cửa sổ terminal để chạy consumer, producer và lệnh quan sát.

Các ví dụ dưới đây dùng Kafka local một broker, vì vậy replication factor của topic là 1. Với cluster có nhiều broker, hãy chọn replication factor không vượt quá số broker đang hoạt động.

Tên script tùy hệ điều hành:

| Hệ điều hành | Script |
|---|---|
| Linux/macOS | `bin/kafka-topics.sh`, `bin/kafka-console-producer.sh`, `bin/kafka-console-consumer.sh`, `bin/kafka-consumer-groups.sh` |
| Windows | `bin\windows\kafka-topics.bat`, `bin\windows\kafka-console-producer.bat`, `bin\windows\kafka-console-consumer.bat`, `bin\windows\kafka-consumer-groups.bat` |

Các lệnh trong phần thực hành dùng tên script Linux/macOS để dễ đọc. Trên Windows PowerShell, chạy script tương ứng trong `bin\windows`, ví dụ:

```powershell
.\bin\windows\kafka-consumer-groups.bat --bootstrap-server localhost:9092 --list
```

Nếu cluster dùng TLS hoặc SASL, tạo file cấu hình client theo hướng dẫn quản trị của cluster rồi truyền `--command-config client.properties` cho lệnh quản trị. Không đưa mật khẩu hoặc secret trực tiếp vào lịch sử terminal hay tài liệu dùng chung.

## 2. Tạo topic và kiểm tra topic

Tạo topic có ba partition để quan sát cách group phân phối partition:

```bash
bin/kafka-topics.sh --bootstrap-server localhost:9092 \
  --create --topic orders --partitions 3 --replication-factor 1
```

Xác nhận topic đã tồn tại và xem partition:

```bash
bin/kafka-topics.sh --bootstrap-server localhost:9092 \
  --describe --topic orders
```

Kết quả thường có thông tin partition, leader, replica và ISR. Trong bài này, phần cần quan tâm là topic có ba partition. Mỗi partition là một log độc lập và có dãy offset riêng bắt đầu từ offset của log hiện có; không có một offset toàn cục duy nhất cho cả topic.

Nếu topic đã tồn tại, không cần tạo lại. Hãy dùng topic thử nghiệm riêng nếu bạn không chắc dữ liệu hiện tại có thể được dùng cho bài thực hành.

## 3. Khởi chạy consumer thuộc một group

Mở terminal thứ nhất và chạy console consumer:

```bash
bin/kafka-console-consumer.sh --bootstrap-server localhost:9092 \
  --topic orders \
  --group orders-observer-lab \
  --consumer-property auto.offset.reset=earliest \
  --consumer-property enable.auto.commit=true \
  --consumer-property auto.commit.interval.ms=1000 \
  --property print.partition=true \
  --property print.offset=true
```

Ý nghĩa các tham số:

- `--group orders-observer-lab`: consumer tham gia group có ID này. Group ID là khóa để Kafka lưu và truy xuất offset đã commit của consumer group.
- `auto.offset.reset=earliest`: nếu group chưa có offset hợp lệ, consumer bắt đầu từ offset sớm nhất còn tồn tại. Cấu hình này không tua một group đã có offset commit về đầu topic.
- `enable.auto.commit=true`: Kafka client tự động commit vị trí đọc theo chu kỳ.
- `auto.commit.interval.ms=1000`: đặt chu kỳ auto commit là một giây cho bài thực hành.
- `print.partition=true` và `print.offset=true`: hiển thị partition và offset của bản ghi được console consumer in ra.

Giữ terminal này mở. Consumer sẽ tham gia group và nhận assignment sau quá trình group coordination. Với group mới, offset có thể chưa xuất hiện ngay trong kết quả mô tả cho đến khi client đã đọc và commit.

> Auto commit phù hợp để quan sát trong lab. Với ứng dụng nghiệp vụ, cần chọn chiến lược commit dựa trên thời điểm xử lý hoàn tất. Auto commit có thể ghi nhận vị trí đọc trước khi tác vụ bên ngoài đã được lưu bền vững.

## 4. Gửi sự kiện vào topic

Mở terminal thứ hai và chạy console producer:

```bash
bin/kafka-console-producer.sh --bootstrap-server localhost:9092 \
  --topic orders
```

Nhập một số dòng, mỗi dòng là một bản ghi:

```text
order-1001
order-1002
order-1003
order-1004
order-1005
order-1006
```

Quan sát terminal consumer. Mỗi dòng được in kèm partition và offset, ví dụ:

```text
Partition:2    Offset:0    order-1001
Partition:0    Offset:0    order-1002
Partition:1    Offset:0    order-1003
```

Đây là ví dụ minh họa; partition được chọn phụ thuộc partitioner và trạng thái batch của producer. Không giả định các bản ghi sẽ được chia đều cho ba partition. Offset tăng độc lập trong từng partition, vì vậy có thể thấy nhiều partition cùng có bản ghi offset 0.

## 5. Liệt kê consumer group

Mở terminal thứ ba. Liệt kê các group mà cluster đang biết:

```bash
bin/kafka-consumer-groups.sh --bootstrap-server localhost:9092 --list
```

Nếu consumer đã tham gia group, bạn sẽ thấy `orders-observer-lab` trong danh sách. Một số group chỉ xuất hiện sau khi có metadata hoặc offset được lưu, tùy trạng thái group và phiên bản Kafka.

Lệnh này chỉ liệt kê ID. Để xem partition, offset và lag, dùng `--describe`.

## 6. Xem offset đã commit và consumer lag

Chạy:

```bash
bin/kafka-consumer-groups.sh --bootstrap-server localhost:9092 \
  --describe --group orders-observer-lab
```

Một kết quả minh họa:

```text
GROUP               TOPIC   PARTITION  CURRENT-OFFSET  LOG-END-OFFSET  LAG
orders-observer-lab orders  0          2               5               3
orders-observer-lab orders  1          3               3               0
orders-observer-lab orders  2          1               4               3
```

Các cột chính:

| Cột | Ý nghĩa |
|---|---|
| `GROUP` | ID của consumer group |
| `TOPIC` | Topic mà group đang đọc |
| `PARTITION` | Partition cụ thể của topic |
| `CURRENT-OFFSET` | Offset đã commit của group, tức vị trí tiếp tục đọc |
| `LOG-END-OFFSET` | Vị trí cuối của log tại thời điểm truy vấn, tức offset kế tiếp sau dữ liệu hiện có trong log |
| `LAG` | Chênh lệch giữa log end offset và committed offset |

Trong ví dụ, partition 0 có committed offset 2 và log end offset 5, nên lag là 3. Consumer group đã commit vị trí 2 và còn khoảng ba offset phía sau vị trí đó trong log. Partition 1 có lag bằng 0 tại thời điểm truy vấn. Partition 2 còn lag 3.

Offset commit là vị trí kế tiếp cần đọc, không phải offset của bản ghi cuối cùng đã xử lý. Ví dụ, committed offset bằng 5 thường có nghĩa consumer sẽ tiếp tục từ offset 5; với quá trình đọc tuần tự, bản ghi cuối cùng trước đó là offset 4.

Nếu `CURRENT-OFFSET` hoặc `LAG` hiển thị dấu gạch ngang (`-`), group chưa có committed offset cho partition đó hoặc broker chưa có giá trị offset để báo cáo. Hãy kiểm tra consumer đã đọc bản ghi và đã commit chưa. `auto.offset.reset` chỉ quyết định vị trí bắt đầu khi không có offset hợp lệ; bản thân cấu hình này không commit offset.

Lag là chỉ số chênh lệch hữu ích để theo dõi tiến độ, nhưng không phải lúc nào cũng bằng chính xác số bản ghi mà ứng dụng có thể xử lý ngay. Log compaction, giao dịch chưa được commit, isolation level và thay đổi log trong lúc truy vấn có thể ảnh hưởng cách diễn giải. Khi điều tra production, đối chiếu lag với tốc độ xử lý, thời gian xử lý và metric của ứng dụng.

## 7. Xem trạng thái group

Trong khi console consumer vẫn chạy, xem trạng thái group:

```bash
bin/kafka-consumer-groups.sh --bootstrap-server localhost:9092 \
  --describe --group orders-observer-lab --state
```

Kết quả thường thể hiện coordinator, assignment strategy, state và số thành viên. Tên cột chi tiết có thể thay đổi theo phiên bản Kafka và group protocol.

Một số trạng thái thường gặp:

| Trạng thái | Cách hiểu |
|---|---|
| `Stable` | Group đã ổn định và các thành viên đã nhận assignment |
| `PreparingRebalance` | Group đang chuẩn bị phân phối lại partition |
| `CompletingRebalance` | Group đang hoàn tất quá trình rebalance |
| `Empty` | Không còn consumer đang hoạt động trong group; offset đã commit có thể vẫn được lưu |
| `Dead` | Metadata của group đã bị loại bỏ |
| `Unknown` | Broker hoặc công cụ không xác định được trạng thái cụ thể |

Trạng thái rebalance trong thời gian ngắn có thể là bình thường khi consumer tham gia hoặc rời group. Nếu group liên tục chuyển trạng thái và không ổn định, hãy kiểm tra consumer restart, heartbeat, thời gian xử lý, timeout và lỗi kết nối.

Dừng console consumer bằng Ctrl+C rồi chạy lại lệnh `--state`. Group thường chuyển sang `Empty` sau khi broker nhận biết thành viên đã rời. Offset đã commit vẫn có thể được giữ lại để lần chạy sau tiếp tục.

## 8. Xem thành viên và partition assignment

Khi consumer đang chạy, dùng:

```bash
bin/kafka-consumer-groups.sh --bootstrap-server localhost:9092 \
  --describe --group orders-observer-lab --members --verbose
```

Lệnh này hiển thị các thành viên, client ID, host, số partition được gán và assignment chi tiết. Một consumer có thể sở hữu nhiều partition. Trong cùng một group, mỗi partition được gán cho tối đa một consumer tại một thời điểm; các group khác vẫn có thể đọc cùng partition độc lập.

Để quan sát việc chia tải:

1. Giữ consumer đầu tiên chạy.
2. Mở terminal khác và khởi chạy thêm một console consumer với cùng topic và cùng group ID.
3. Chạy lại lệnh `--members --verbose`.
4. Quan sát số thành viên và danh sách partition được gán cho từng thành viên.
5. Dừng một consumer rồi quan sát group rebalance và assignment mới.

Ví dụ lệnh cho consumer thứ hai:

```bash
bin/kafka-console-consumer.sh --bootstrap-server localhost:9092 \
  --topic orders \
  --group orders-observer-lab \
  --consumer-property auto.offset.reset=earliest \
  --consumer-property enable.auto.commit=true \
  --consumer-property auto.commit.interval.ms=1000 \
  --property print.partition=true \
  --property print.offset=true
```

Cả hai consumer phải dùng cùng group ID để chia sẻ partition. Nếu dùng group ID khác, chúng tạo thành hai group độc lập và mỗi group có vị trí đọc riêng.

Nếu số consumer nhiều hơn số partition, một số consumer sẽ không nhận partition nào. Tăng số consumer vượt số partition không làm tăng mức song song đọc của topic đó trong group.

## 9. Theo dõi offset khi consumer dừng và khởi động lại

Thực hiện thí nghiệm sau để thấy sự khác nhau giữa offset đã commit và log end offset:

1. Khi consumer đang chạy, gửi thêm vài bản ghi từ producer.
2. Chờ consumer in các bản ghi và chờ lâu hơn chu kỳ auto commit đã cấu hình.
3. Dừng consumer bằng Ctrl+C.
4. Chạy `--describe --group orders-observer-lab` để ghi lại committed offset và lag.
5. Khởi động lại consumer với cùng group ID.
6. Quan sát consumer tiếp tục từ vị trí đã commit thay vì tự động đọc lại toàn bộ topic.

Nếu consumer được khởi động lại trước khi có lần commit phù hợp, một số bản ghi có thể được đọc lại. Đây là lý do ứng dụng cần hiểu rõ commit timing và thiết kế thao tác xử lý có tính idempotent.

Thử đổi group ID thành `orders-observer-second` rồi chạy consumer mới. Nếu group mới chưa có offset, `auto.offset.reset=earliest` cho phép nó đọc từ offset sớm nhất còn tồn tại. Hai group có thể đọc cùng một dữ liệu mà không ảnh hưởng committed offset của nhau.

## 10. Xem trước thao tác reset offset

Kafka CLI có thể đề xuất vị trí offset mới cho group. Đây là thao tác quản trị có thể khiến consumer đọc lại hoặc bỏ qua dữ liệu. Trước tiên, dừng tất cả consumer thuộc group cần reset; lệnh reset yêu cầu group không có thành viên hoạt động.

Xem trước việc đưa offset của topic về đầu log:

```bash
bin/kafka-consumer-groups.sh --bootstrap-server localhost:9092 \
  --group orders-observer-lab \
  --topic orders \
  --reset-offsets --to-earliest --dry-run
```

`--dry-run` chỉ hiển thị các offset dự kiến, không áp dụng thay đổi. Đọc kỹ kết quả theo từng partition và xác nhận topic/group đích trước khi thực hiện. Nếu có chủ đích cho consumer đọc lại dữ liệu từ đầu log, mới chạy lại lệnh với `--execute`:

```bash
bin/kafka-consumer-groups.sh --bootstrap-server localhost:9092 \
  --group orders-observer-lab \
  --topic orders \
  --reset-offsets --to-earliest --execute
```

Sau khi reset, khi consumer thuộc group khởi động lại, nó có thể đọc lại các bản ghi từ vị trí mới. `to-earliest` là đầu log hiện còn được lưu, không nhất thiết là offset 0 nếu dữ liệu cũ đã bị retention xóa. Không chạy `--execute` trên group production chỉ để thử nghiệm; reset offset có thể làm phát sinh xử lý lại hoặc bỏ qua dữ liệu theo vị trí mới.

Một số tùy chọn reset thường dùng:

| Tùy chọn | Vị trí mới |
|---|---|
| `--to-earliest` | Offset sớm nhất còn tồn tại |
| `--to-latest` | Cuối log tại thời điểm reset |
| `--to-offset N` | Offset cụ thể N |
| `--shift-by N` | Dịch chuyển vị trí hiện tại thêm N |
| `--to-datetime YYYY-MM-DDTHH:mm:SS.sss` | Offset tương ứng với thời điểm chỉ định |
| `--by-duration PT1H` | Dịch vị trí về trước theo khoảng thời gian ISO-8601 |

Luôn bắt đầu bằng `--dry-run`, kiểm tra từng partition rồi mới cân nhắc `--execute`.

## 11. Một số tình huống chẩn đoán thường gặp

| Quan sát | Nguyên nhân có thể | Việc nên kiểm tra |
|---|---|---|
| Group không xuất hiện trong `--list` | Consumer chưa tham gia, group chưa có metadata hoặc đang dùng sai cluster | Bootstrap server, group ID, trạng thái tiến trình consumer |
| `CURRENT-OFFSET` là `-` | Chưa có offset commit cho partition | Consumer đã đọc chưa, auto commit có bật không, commit có lỗi không |
| Lag tăng liên tục | Producer ghi nhanh hơn consumer xử lý hoặc consumer bị nghẽn | Tốc độ vào/ra, thời gian xử lý, số partition, lỗi gọi dịch vụ ngoài |
| State liên tục rebalance | Consumer restart, mất kết nối hoặc không poll đúng hạn | Log consumer, heartbeat, `max.poll.interval.ms`, `session.timeout.ms` |
| Một số consumer có 0 partition | Số consumer lớn hơn số partition hoặc assignment hiện tại không chia đều | Số partition và output `--members --verbose` |
| Consumer khởi động lại đọc lại dữ liệu | Lần xử lý trước chưa commit offset tương ứng | Commit timing, auto commit, lỗi commit và tính idempotent |
| Consumer không đọc lại từ đầu dù đặt `earliest` | Group đã có committed offset hợp lệ | Group ID, offset hiện tại; reset offset chỉ khi có chủ đích |

Để xem mọi group và offset trong cluster, có thể dùng:

```bash
bin/kafka-consumer-groups.sh --bootstrap-server localhost:9092 \
  --describe --all-groups
```

Lệnh này hữu ích khi kiểm tra tổng quan, nhưng trên cluster lớn có thể trả về nhiều dữ liệu. Nên lọc theo group ID khi điều tra một ứng dụng cụ thể. Với cluster bảo mật, thêm `--command-config client.properties` vào các lệnh quản trị tương ứng.

## 12. Hoàn thành bài thực hành

Bạn đã hoàn thành khi có thể thực hiện và giải thích được các điểm sau:

- Liệt kê group bằng `--list`.
- Xem committed offset, log end offset và lag bằng `--describe --group`.
- Phân biệt committed offset với offset của bản ghi vừa được in ra.
- Xem trạng thái group bằng `--state`.
- Xem consumer member và partition assignment bằng `--members --verbose`.
- Giải thích vì sao group mới có thể bắt đầu từ earliest, còn group đã có offset thì tiếp tục từ committed offset.
- Dùng `--reset-offsets --dry-run` để xem trước thay đổi và hiểu tác động của `--execute`.

Các lệnh quan sát này là bước đầu để vận hành Kafka. Khi lag tăng hoặc group rebalance bất thường, hãy kết hợp kết quả CLI với log ứng dụng, metric consumer và thời gian xử lý thực tế để xác định nguyên nhân.

