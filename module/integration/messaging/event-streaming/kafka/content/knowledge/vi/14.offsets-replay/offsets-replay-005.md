# Reset offset bằng công cụ quản trị: xem trước rồi thực thi

## Mục tiêu

Kafka lưu committed offset riêng cho từng consumer group và từng topic-partition. Khi cần phát lại dữ liệu, bỏ qua backlog cũ hoặc khôi phục một nhóm sau sự cố, quản trị viên có thể thay đổi các committed offset bằng `kafka-consumer-groups.sh`.

Reset offset là thao tác thay đổi điểm bắt đầu đọc của consumer group. Nó không xóa record trong topic và cũng không tự xử lý lại dữ liệu. Khi consumer chạy lại với cùng `group.id`, nó sẽ tiếp tục từ offset mới. Vì vậy, chọn sai offset có thể khiến ứng dụng đọc lại dữ liệu và tạo side effect trùng, hoặc bỏ qua dữ liệu chưa xử lý.

Bài học này hướng dẫn quy trình an toàn: dừng consumer, kiểm tra trạng thái và offset hiện tại, chạy `--dry-run` để xem kế hoạch, sau đó mới dùng `--execute`. Bạn cũng sẽ học cách export offset để lưu kế hoạch rollback.

Sau bài học, bạn có thể:

- Giải thích reset offset thay đổi committed position như thế nào.
- Dùng `--dry-run` để xem trước offset mới theo từng partition.
- Chọn `--to-earliest`, `--to-latest`, `--shift-by`, `--to-offset`, `--to-datetime` hoặc `--by-duration`.
- Giới hạn phạm vi reset theo topic hoặc partition.
- Export/import offset bằng CSV để sao lưu và phục hồi.
- Xác minh kết quả sau `--execute` và tránh mất dữ liệu hoặc xử lý trùng ngoài ý muốn.

## 1. Reset offset tác động đến điều gì?

Mỗi consumer group lưu một committed offset cho từng topic-partition. Đây là vị trí tiếp theo consumer sẽ đọc khi khôi phục group. Ví dụ:

| Topic-partition | Committed offset hiện tại | Ý nghĩa |
|---|---:|---|
| `orders-0` | 120 | Consumer sẽ bắt đầu từ offset 120 |
| `orders-1` | 85 | Consumer sẽ bắt đầu từ offset 85 |
| `orders-2` | 240 | Consumer sẽ bắt đầu từ offset 240 |

Nếu reset `orders-0` từ 120 về 100, consumer sẽ đọc lại các record từ vị trí 100 còn được giữ trong log. Nếu reset từ 120 lên 150, consumer bỏ qua vùng offset trước 150.

```mermaid
flowchart LR
    A[Committed offset hiện tại: 120] --> B[Admin chạy --dry-run]
    B --> C[Xem NEW-OFFSET: 100]
    C --> D[Admin xác nhận kế hoạch]
    D --> E[Chạy --execute]
    E --> F[Committed offset mới: 100]
    F --> G[Consumer khởi động lại và đọc từ 100]
```

Reset offset chỉ cập nhật vị trí của group trong metadata Kafka. Record vẫn nằm trong topic theo retention/compaction hiện hành. Reset về offset cũ không thể khôi phục record đã bị retention xóa hoặc dữ liệu đã bị compact khỏi log.

## 2. Điều kiện trước khi reset

Kafka yêu cầu consumer instances của group phải inactive khi dùng `--reset-offsets`. Công cụ kiểm tra group state; group đang có member hoạt động sẽ không được reset theo quy trình này.

Trước khi thao tác:

1. Xác nhận đúng cluster, môi trường và `group.id`.
2. Dừng tất cả consumer instance của group: service, container, Kubernetes deployment, scheduled job hoặc tiến trình chạy thủ công.
3. Chờ group không còn member hoạt động. Kiểm tra state bằng `--describe --state` và member bằng `--describe --members`.
4. Ghi lại committed offset, log start/end offset và lag hiện tại.
5. Thống nhất mục tiêu nghiệp vụ: phát lại từ đầu, phát lại một khoảng thời gian, bỏ backlog hay quay về offset cụ thể.
6. Export offset hiện tại để có thể khôi phục nếu kế hoạch reset không đúng.

Ví dụ kiểm tra group:

```bash
bin/kafka-consumer-groups.sh \
  --bootstrap-server localhost:9092 \
  --describe --group order-processor --state

bin/kafka-consumer-groups.sh \
  --bootstrap-server localhost:9092 \
  --describe --group order-processor --members

bin/kafka-consumer-groups.sh \
  --bootstrap-server localhost:9092 \
  --describe --group order-processor
```

Group thường cần ở trạng thái `Empty` hoặc `Dead` và không có member hoạt động. Nếu consumer vẫn đang chạy, hãy dừng đúng tiến trình trước khi tiếp tục; không cố reset đồng thời với consumer đang đọc/commit offset.

Nếu cluster dùng SASL/SSL, thêm `--command-config client.properties` vào các lệnh. File này phải chứa cấu hình kết nối và xác thực được AdminClient sử dụng.

## 3. Cú pháp cơ bản: preview trước, execute sau

Mẫu lệnh:

```bash
bin/kafka-consumer-groups.sh \
  --bootstrap-server localhost:9092 \
  --reset-offsets \
  --group order-processor \
  --topic commerce.orders.events.v1 \
  --to-earliest \
  --dry-run
```

`--dry-run` chỉ tính và hiển thị kế hoạch, không thay đổi committed offsets. Đây là chế độ mặc định của Kafka 4.1 nếu không chỉ định `--execute`, nhưng nên ghi rõ `--dry-run` trong lệnh để tránh hiểu nhầm khi đọc script hoặc lịch sử thao tác.

Khi đã kiểm tra bảng `NEW-OFFSET` và xác nhận đúng topic/partition, chạy lại cùng kế hoạch với `--execute`:

```bash
bin/kafka-consumer-groups.sh \
  --bootstrap-server localhost:9092 \
  --reset-offsets \
  --group order-processor \
  --topic commerce.orders.events.v1 \
  --to-earliest \
  --execute
```

Không dùng đồng thời `--dry-run` và `--execute`. `--execute` là bước ghi thay đổi thật vào committed offsets của group.

Với cluster bảo mật:

```bash
bin/kafka-consumer-groups.sh \
  --bootstrap-server kafka.example.com:9093 \
  --command-config client.properties \
  --reset-offsets --group order-processor \
  --topic commerce.orders.events.v1 \
  --to-earliest --dry-run
```

Ví dụ trên dùng Bash trên Linux/macOS. Trên Windows, dùng `bin\windows\kafka-consumer-groups.bat` với cùng tham số. Lệnh reset chỉ hỗ trợ một consumer group mỗi lần.

## 4. Chọn phạm vi topic và partition

Reset cần có phạm vi xác định:

| Tùy chọn | Phạm vi |
|---|---|
| `--topic topic-name` | Các partition của topic được chỉ định |
| `--all-topics` | Các topic mà consumer group đang có assignment/offset liên quan; không phải tất cả topic trên cluster |
| `--topic topic-name:0,1` | Một số phiên bản hỗ trợ chỉ định partition cụ thể trong topic |

Ví dụ chỉ reset một topic:

```bash
bin/kafka-consumer-groups.sh \
  --bootstrap-server localhost:9092 \
  --reset-offsets --group order-processor \
  --topic commerce.orders.events.v1 \
  --to-earliest --dry-run
```

Ví dụ chỉ reset partition 0 và 2 của topic `orders` trên Kafka CLI hỗ trợ cú pháp partition scope:

```bash
bin/kafka-consumer-groups.sh \
  --bootstrap-server localhost:9092 \
  --reset-offsets --group order-processor \
  --topic orders:0,2 \
  --to-latest --dry-run
```

Nếu dùng nhiều topic, có thể lặp tùy chọn `--topic` theo khả năng của phiên bản CLI. Luôn xem output preview để xác nhận đúng tập partition. Nếu muốn đặt offset khác nhau cho từng partition, dùng `--from-file` thay vì một chiến lược chung cho toàn scope.

## 5. Các chiến lược reset offset

Mỗi lần reset chỉ chọn một chiến lược. Dưới đây là các lựa chọn phổ biến của `kafka-consumer-groups.sh`.

### 5.1. `--to-earliest`: đọc từ đầu log còn được giữ

Đặt offset về vị trí sớm nhất còn tồn tại trong từng partition:

```bash
bin/kafka-consumer-groups.sh \
  --bootstrap-server localhost:9092 \
  --reset-offsets --group order-processor \
  --topic orders --to-earliest --dry-run
```

`earliest` không nhất thiết là offset 0. Nếu retention đã xóa các segment cũ hoặc compaction đã loại bỏ record, vị trí sớm nhất có thể lớn hơn 0. Consumer sẽ đọc lại phần dữ liệu còn lại từ log start offset.

Chọn cách này khi cần phát lại toàn bộ dữ liệu hiện còn trong topic. Kiểm tra side effect downstream trước khi thực thi vì các đơn hàng/giao dịch đã xử lý có thể được gửi lại.

### 5.2. `--to-latest`: bỏ qua backlog hiện tại

Đặt offset đến log end offset của mỗi partition:

```bash
bin/kafka-consumer-groups.sh \
  --bootstrap-server localhost:9092 \
  --reset-offsets --group order-processor \
  --topic orders --to-latest --dry-run
```

Khi consumer khởi động lại, nó đọc các record được append sau vị trí reset. Các record đang tồn tại trước thời điểm reset sẽ bị bỏ qua đối với group này.

Chỉ dùng khi nghiệp vụ chấp nhận bỏ backlog cũ, ví dụ bỏ qua dữ liệu thử nghiệm hoặc chuyển group sang xử lý dữ liệu mới. Không dùng `latest` để “sửa lag” nếu các record đang chờ vẫn cần được xử lý.

### 5.3. `--shift-by`: dịch chuyển từ committed offset hiện tại

Giá trị dương đưa offset tiến lên; giá trị âm đưa offset lùi lại:

```bash
# Phát lại khoảng 100 offset trước vị trí hiện tại
bin/kafka-consumer-groups.sh \
  --bootstrap-server localhost:9092 \
  --reset-offsets --group order-processor \
  --topic orders --shift-by -100 --dry-run

# Bỏ qua 50 offset tiếp theo
bin/kafka-consumer-groups.sh \
  --bootstrap-server localhost:9092 \
  --reset-offsets --group order-processor \
  --topic orders --shift-by 50 --dry-run
```

`shift-by` tính từ committed offset hiện tại của từng partition. Nếu kết quả nằm ngoài phạm vi offset còn hợp lệ, Kafka điều chỉnh về phạm vi log khả dụng. Luôn kiểm tra `NEW-OFFSET` vì offset có thể bị giới hạn ở log start hoặc log end.

Offset không đảm bảo liên tục, đặc biệt với topic compacted hoặc transactional. Vì vậy, dịch `-100` là lùi 100 đơn vị offset, không nhất thiết tương đương đúng 100 record nghiệp vụ.

### 5.4. `--to-offset`: đặt offset cụ thể

Đặt tất cả partition trong scope về cùng một offset số:

```bash
bin/kafka-consumer-groups.sh \
  --bootstrap-server localhost:9092 \
  --reset-offsets --group order-processor \
  --topic orders --to-offset 5000 --dry-run
```

`--to-offset` hữu ích khi có offset mục tiêu đã xác định từ log, incident hoặc kế hoạch replay. Giá trị được áp dụng cho từng partition trong scope; nếu mỗi partition cần một offset khác nhau, hãy tạo CSV và dùng `--from-file`.

Consumer position là offset tiếp theo cần đọc. Nếu partition không có record đúng tại offset yêu cầu do khoảng trống, consumer sẽ đọc record kế tiếp có offset phù hợp. Kiểm tra offset mục tiêu có nằm trong log start/end hiện tại không.

### 5.5. `--to-datetime`: quay về thời điểm cụ thể

Chọn offset tương ứng với timestamp:

```bash
bin/kafka-consumer-groups.sh \
  --bootstrap-server localhost:9092 \
  --reset-offsets --group order-processor \
  --topic orders \
  --to-datetime 2026-11-20T09:00:00.000 \
  --dry-run
```

Định dạng theo tài liệu Kafka là `YYYY-MM-DDThh:mm:ss.sss`. Kafka tra cứu offset theo timestamp của record, vì vậy kết quả phụ thuộc timestamp type và timestamp do producer/broker ghi vào record. Nếu topic dùng `CreateTime`, timestamp có thể do producer cung cấp; nếu dùng `LogAppendTime`, timestamp phản ánh thời điểm broker append.

Với timestamp hợp lệ, Kafka tra cứu vị trí record đầu tiên có timestamp lớn hơn hoặc bằng mốc yêu cầu. Chuỗi thời gian trong cú pháp CLI không mang phần offset timezone riêng. Hãy thống nhất timezone giữa người vận hành, máy chạy CLI và timestamp của dữ liệu; kiểm tra kết quả preview trước khi execute. Không suy ra rằng offset này luôn trùng với thời điểm nghiệp vụ nếu payload có trường `occurredAt` riêng.

### 5.6. `--by-duration`: quay lại một khoảng thời gian từ hiện tại

Chọn vị trí tương ứng với thời điểm hiện tại trừ đi duration:

```bash
# Bắt đầu đọc lại khoảng 2 giờ gần nhất
bin/kafka-consumer-groups.sh \
  --bootstrap-server localhost:9092 \
  --reset-offsets --group order-processor \
  --topic orders --by-duration PT2H --dry-run
```

Duration dùng định dạng ISO-8601, ví dụ:

| Duration | Ý nghĩa |
|---|---|
| `PT15M` | 15 phút |
| `PT2H` | 2 giờ |
| `P1D` | 1 ngày |
| `P2DT3H` | 2 ngày 3 giờ |

Đây là thời lượng tính từ thời điểm chạy lệnh, không phải khoảng thời gian cố định theo lịch. Khi cần một mốc tuyệt đối, dùng `--to-datetime`.

### 5.7. `--to-current`: giữ committed offset hiện có

`--to-current` chọn committed offset hiện tại của group. Với partition chưa có committed offset, công cụ dùng log end offset làm điểm bắt đầu. Tùy chọn này hữu ích khi export/sao lưu vị trí hiện tại hoặc muốn tạo kế hoạch offset nhất quán cho scope.

```bash
bin/kafka-consumer-groups.sh \
  --bootstrap-server localhost:9092 \
  --reset-offsets --group order-processor \
  --all-topics --to-current --dry-run
```

Nếu mục đích là sao lưu, thêm `--export` và chuyển output ra file như phần 7. Đừng nhầm `--to-current` với `--to-latest`: partition đã có committed offset sẽ giữ vị trí hiện tại, không nhảy tới cuối log.

## 6. Đọc kết quả dry-run

Preview thường hiển thị group, topic, partition và offset mới:

```text
GROUP            TOPIC   PARTITION  NEW-OFFSET
order-processor  orders  0          100
order-processor  orders  1          85
order-processor  orders  2          240
```

Trước khi execute, kiểm tra:

- Đúng `GROUP` và đúng cluster/môi trường.
- Đúng `TOPIC` và toàn bộ partition cần reset.
- `NEW-OFFSET` đúng mục tiêu của từng partition.
- Offset không nằm ngoài vùng dữ liệu còn được giữ.
- Tác động replay/skip đã được owner nghiệp vụ chấp thuận.
- Consumer instances vẫn đang dừng và không có automation tự khởi động lại chúng.

Nếu kết quả không đúng, sửa scope hoặc chiến lược rồi chạy `--dry-run` lại. Không chuyển sang `--execute` chỉ vì lệnh preview đã chạy thành công.

## 7. Export offset hiện tại và dùng CSV

Export cho phép lưu kế hoạch offset ra CSV. Đây là cách đơn giản để chụp lại committed offsets trước khi reset và chuẩn bị rollback.

### 7.1. Export offset hiện tại

```bash
bin/kafka-consumer-groups.sh \
  --bootstrap-server localhost:9092 \
  --reset-offsets --group order-processor \
  --all-topics --to-current --dry-run --export \
  > order-processor-before-reset.csv
```

Với một group, file CSV có các cột theo thứ tự `topic,partition,offset`, ví dụ:

```csv
orders,0,120
orders,1,85
orders,2,240
payments,0,90
```

File export không cần thêm dòng header. Giữ file này cùng ticket/change record và không ghi đè trước khi reset hoàn tất.

### 7.2. Preview reset từ file

`--from-file` lấy offset riêng cho từng topic-partition trong CSV, nên không cần `--topic` hoặc `--all-topics`:

```bash
bin/kafka-consumer-groups.sh \
  --bootstrap-server localhost:9092 \
  --reset-offsets --group order-processor \
  --from-file order-processor-reset-plan.csv \
  --dry-run
```

Kiểm tra `NEW-OFFSET` cho từng dòng rồi mới thực thi:

```bash
bin/kafka-consumer-groups.sh \
  --bootstrap-server localhost:9092 \
  --reset-offsets --group order-processor \
  --from-file order-processor-reset-plan.csv \
  --execute
```

Với một group, CSV dùng ba cột `topic,partition,offset`. Nếu tự tạo file, không thêm header và không thay đổi thứ tự cột. Dùng file export từ chính Kafka CLI giúp tránh lỗi định dạng.

## 8. Thực thi và xác minh sau reset

Sau khi preview được duyệt, chạy đúng cùng scope/strategy với `--execute`. Ví dụ phát lại dữ liệu trong hai giờ gần nhất:

```bash
bin/kafka-consumer-groups.sh \
  --bootstrap-server localhost:9092 \
  --reset-offsets --group order-processor \
  --topic orders --by-duration PT2H --execute
```

Sau khi lệnh hoàn tất:

1. Chạy `--describe --group order-processor` để đọc committed offset mới.
2. So sánh `CURRENT-OFFSET` với `NEW-OFFSET` trong preview.
3. Xác nhận group vẫn không có consumer ngoài ý muốn.
4. Khởi động lại consumer với đúng `group.id`.
5. Theo dõi log ứng dụng, consumer lag, tốc độ xử lý và lỗi downstream.
6. Xác minh các record được replay hoặc bỏ qua đúng như kế hoạch nghiệp vụ.

Ví dụ kiểm tra:

```bash
bin/kafka-consumer-groups.sh \
  --bootstrap-server localhost:9092 \
  --describe --group order-processor
```

Reset offset không tự tạo bản sao dữ liệu và cũng không rollback side effect đã xảy ra. Nếu consumer đã gửi email, tạo hóa đơn hoặc cập nhật database trước đó, replay có thể lặp lại hành động đó. Hãy dùng event ID, unique constraint, inbox/dedup hoặc idempotency key ở hệ thống downstream.

## 9. Rollback khi reset không đúng

Nếu đã export offset trước khi thay đổi, có thể khôi phục vị trí ban đầu bằng `--from-file`:

```bash
# Xem trước rollback
bin/kafka-consumer-groups.sh \
  --bootstrap-server localhost:9092 \
  --reset-offsets --group order-processor \
  --from-file order-processor-before-reset.csv \
  --dry-run

# Thực hiện rollback sau khi xác nhận preview
bin/kafka-consumer-groups.sh \
  --bootstrap-server localhost:9092 \
  --reset-offsets --group order-processor \
  --from-file order-processor-before-reset.csv \
  --execute
```

Rollback chỉ khôi phục committed offsets. Nó không hoàn tác các record đã được consumer xử lý trong khoảng replay và không xóa side effect trùng đã ghi ở database hoặc hệ thống ngoài. Những side effect đó cần được xử lý theo quy trình nghiệp vụ riêng.

## 10. Các nhầm lẫn và rủi ro thường gặp

| Nhầm lẫn/rủi ro | Cách hiểu đúng |
|---|---|
| Reset offset xóa record trong topic | Reset chỉ thay đổi committed position của group; retention/compaction vẫn quản lý dữ liệu |
| `earliest` luôn là offset 0 | Đó là log start offset còn được giữ; dữ liệu cũ có thể đã bị retention xóa |
| `latest` là cách nhanh để giảm lag an toàn | Nó bỏ qua backlog hiện tại đối với group; chỉ dùng khi nghiệp vụ chấp nhận bỏ dữ liệu |
| `shift-by -100` phát lại đúng 100 event | Nó lùi 100 đơn vị offset; offset không nhất thiết liên tục |
| `to-datetime` luôn là thời điểm nghiệp vụ | Nó dựa vào timestamp metadata của Kafka record, có thể khác `occurredAt` trong payload |
| `auto.offset.reset` sẽ ghi đè offset vừa reset | Khi committed offset hợp lệ đã tồn tại, `auto.offset.reset` không được dùng để thay thế nó |
| Chạy reset khi consumer vẫn hoạt động | Công cụ yêu cầu group inactive; dừng toàn bộ instance trước khi reset |
| Preview thành công nghĩa là đã thay đổi offset | `--dry-run` không ghi thay đổi; phải dùng `--execute` |
| Rollback CSV hoàn tác cả nghiệp vụ | CSV chỉ phục hồi committed offsets, không đảo ngược side effect downstream |

### 10.1. Reset offset cho Kafka Streams

Kafka Streams quản lý cả input offsets, internal topics và local state stores theo `application.id`. Reset riêng consumer group offsets có thể làm lệch input position với state store hoặc changelog đã tồn tại. Khi cần reset toàn bộ Kafka Streams application, dùng `kafka-streams-application-reset` theo hướng dẫn của Kafka Streams, đồng thời xử lý local state directory và internal topics theo quy trình phù hợp. Không coi `kafka-consumer-groups.sh --reset-offsets` là công cụ reset đầy đủ cho một Streams application.

## 11. Runbook quản trị offset

Một quy trình thay đổi có thể review và audit:

1. **Xác định mục tiêu:** ghi rõ group, topic/partition, offset đích và lý do replay/skip.
2. **Dừng consumer:** scale deployment về 0 hoặc dừng service/job; xác nhận không còn member.
3. **Ghi nhận hiện trạng:** lưu group state, committed offsets, log start/end offsets và lag.
4. **Backup:** export offset hiện tại ra CSV, đặt tên có môi trường và thời điểm.
5. **Preview:** chạy `--dry-run`; kiểm tra từng partition và phạm vi thay đổi.
6. **Review:** xác nhận tác động replay/skip với owner dữ liệu và downstream.
7. **Execute:** chạy đúng lệnh đã preview với `--execute`.
8. **Verify:** describe group, đối chiếu committed offsets và khởi động consumer.
9. **Monitor:** theo dõi lag, duplicate, lỗi nghiệp vụ và tốc độ catch-up.
10. **Rollback/escalate:** nếu vị trí không đúng, dùng CSV backup để khôi phục offset; xử lý side effect riêng nếu đã phát sinh.

Không reset đồng thời nhiều group bằng một lệnh. Kafka CLI reset từng consumer group một lần; ghi nhận riêng kế hoạch và CSV cho mỗi group.

## 12. Bài thực hành và tự kiểm tra

### Thực hành A — Reset về earliest bằng dry-run

1. Tạo topic `offset-reset-lab` với hai partition và gửi một số record.
2. Chạy consumer group `offset-reset-demo`, xử lý một phần dữ liệu và commit offsets.
3. Dừng tất cả consumer instance.
4. Chạy `--describe --state`, `--members` và `--describe` để ghi lại hiện trạng.
5. Export offset hiện tại bằng `--to-current --dry-run --export`.
6. Chạy reset `--to-earliest --dry-run`; ghi lại `NEW-OFFSET` của từng partition.
7. Chỉ sau khi kiểm tra, chạy lại lệnh với `--execute`.
8. Describe group lần nữa và xác nhận committed offsets đã thay đổi.
9. Khởi động consumer và quan sát dữ liệu được đọc lại.

### Thực hành B — Replay một khoảng thời gian

1. Tạo record có timestamp và gửi liên tục trong vài phút.
2. Dừng consumer group.
3. Dùng `--to-datetime` để preview offset từ một mốc cụ thể.
4. So sánh với `--by-duration PT2M`.
5. Chọn một kế hoạch, execute và xác minh committed offset.
6. Giải thích vì sao kết quả có thể khác nếu topic dùng `LogAppendTime` thay vì `CreateTime`.

### Thực hành C — Khôi phục offset từ CSV

1. Export offset group hiện tại.
2. Tạo một CSV thử nghiệm với offset khác nhau cho hai partition.
3. Chạy `--from-file --dry-run` và kiểm tra từng partition.
4. Execute kế hoạch trong lab.
5. Dùng CSV backup ban đầu để preview rồi rollback.
6. Xác nhận committed offsets trở về giá trị trước thử nghiệm.

### Câu hỏi tự kiểm tra

1. Vì sao consumer group phải inactive trước khi reset offset?
2. `--dry-run` khác `--execute` như thế nào?
3. `--all-topics` áp dụng cho tất cả topic trên cluster hay topic group đang sử dụng?
4. `--to-earliest` có bảo đảm bắt đầu từ offset 0 không?
5. `--to-latest` gây tác động gì với backlog hiện tại?
6. `--shift-by -100` có luôn phát lại đúng 100 record không?
7. `--to-datetime` phụ thuộc timestamp nào của Kafka record?
8. Khi nào nên dùng `--from-file` thay vì `--to-offset`?
9. CSV export cho một group có thứ tự cột nào?
10. Rollback offset có hoàn tác side effect đã xảy ra trong lúc replay không?
11. Vì sao reset offset thông thường chưa đủ để reset một Kafka Streams application?

## Kết luận

Reset offset là thao tác quản trị committed position của consumer group. Quy trình an toàn cần dừng consumer, ghi nhận hiện trạng, export offset, xem trước bằng `--dry-run`, xác nhận từng partition rồi mới thực thi bằng `--execute`. Chọn chiến lược theo mục tiêu replay hoặc skip, xác minh committed offsets sau thao tác và theo dõi downstream để phát hiện duplicate hoặc dữ liệu bị bỏ qua. CSV backup hỗ trợ khôi phục vị trí đọc, nhưng không thay thế cơ chế rollback nghiệp vụ.

## Tài liệu tham khảo

- [Apache Kafka 4.1 — Basic Kafka Operations: Managing Consumer Groups and Resetting Offsets](https://kafka.apache.org/41/operations/basic-kafka-operations/)
- [Apache Kafka — ConsumerGroupCommandOptions source](https://apache.googlesource.com/kafka/+/34d365fd8a8e387e2650e3d9e492403d6bca9064/tools/src/main/java/org/apache/kafka/tools/consumer/group/ConsumerGroupCommandOptions.java)
- [Apache Kafka — ConsumerGroupCommand implementation and CSV reset plan](https://apache.googlesource.com/kafka/+/b6183a41342c765daec9c88f9d2723a221131960/tools/src/main/java/org/apache/kafka/tools/consumer/group/ConsumerGroupCommand.java)
- [Apache Kafka 4.1 — Consumer configuration: auto.offset.reset](https://kafka.apache.org/41/configuration/consumer-configs/)
