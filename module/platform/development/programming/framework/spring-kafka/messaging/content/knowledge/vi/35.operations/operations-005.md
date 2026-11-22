# Tính và diễn giải consumer lag

Consumer lag cho biết consumer group đang chậm bao nhiêu so với dữ liệu hiện có trong Kafka. Đây là tín hiệu vận hành quan trọng để phát hiện consumer xử lý không kịp tốc độ producer, một partition bị nghẽn, consumer liên tục rebalance hoặc downstream đang quá tải.

Không nên chỉ nhìn một con số lag tổng. Cần hiểu offset nào đang được dùng để tính, xem lag theo từng partition, so sánh tốc độ record đi vào và đi ra, đồng thời theo dõi tuổi của record cũ nhất chưa xử lý. Một group có lag lớn nhưng đang giảm nhanh có thể khỏe hơn group có lag nhỏ nhưng tăng liên tục.

## 1. Consumer lag là gì?

Kafka lưu record theo thứ tự trong từng partition và gán offset tăng dần. Consumer group đọc các partition được assign và lưu committed offset để ghi nhận vị trí đã xử lý đến đâu. Consumer lag mô tả khoảng cách giữa vị trí consumer và phần cuối dữ liệu có thể đọc trong partition.

Lag thường được biểu diễn theo offset hoặc số record ước tính. Ví dụ, nếu committed offset của một partition là `120` và end offset là `150`, khoảng cách offset là `30`. Consumer group còn khoảng cách 30 offset trước cuối log của partition đó.

Lag cần được tính riêng cho từng partition trước khi tổng hợp theo topic hoặc group. Consumer group có thể xử lý tốt hầu hết partition nhưng bị chậm ở một partition do key nóng, dữ liệu bất thường hoặc lỗi nghiệp vụ lặp lại.

## 2. Các loại offset cần phân biệt

Để đọc lag chính xác, cần phân biệt ba vị trí:

- **Committed offset:** offset tiếp theo mà consumer group đã xác nhận sẽ đọc. Đây là vị trí đã được lưu bền vững cho group.
- **Consumer position:** offset tiếp theo mà consumer hiện tại sẽ nhận khi poll tiếp. Position có thể tiến xa hơn committed offset vì record đã được poll hoặc xử lý nhưng chưa commit.
- **Log end offset (LEO):** offset tiếp theo mà broker sẽ gán cho record mới trong partition. Đây là cuối log theo góc nhìn leader, không đồng nghĩa mọi record đã được replicate hoặc mọi record đã hiển thị với `read_committed`.

Với cách tính offset phổ biến:

\[
\text{Committed lag} = \text{LEO} - \text{Committed offset}
\]

\[
\text{Fetch lag} = \text{Readable end offset} - \text{Consumer position}
\]

Committed lag cho biết khoảng cách từ offset đã commit tới cuối log. Fetch lag gần với lượng dữ liệu consumer còn phải poll theo position hiện tại. Hai giá trị có thể khác nhau đáng kể khi consumer đang xử lý record nhưng chưa commit offset.

Kafka dùng offset theo quy ước vị trí tiếp theo sẽ đọc. Vì vậy, nếu committed offset là `120`, record offset `119` là record cuối cùng đã được xác nhận theo vị trí đó. Không nên trừ hoặc cộng thêm một đơn vị theo cách hiểu offset là số thứ tự của record cuối đã xử lý.

## 3. Ví dụ tính lag theo partition

Giả sử partition `orders-0` có các vị trí sau:

| Đại lượng | Offset |
| --- | ---: |
| Committed offset | 12.300 |
| Consumer position | 12.380 |
| Log end offset | 12.450 |

Khi đó:

- Committed lag = `12.450 - 12.300 = 150` offset.
- Fetch lag = `12.450 - 12.380 = 70` offset, nếu readable end tương ứng với LEO trong trường hợp này.
- Khoảng cách giữa position và committed offset là `80`, phản ánh phần consumer đã tiến qua nhưng chưa được commit.

Nếu consumer tiếp tục xử lý và commit, committed offset sẽ tiến gần end offset. Nếu listener bị chậm hoặc không commit, committed lag có thể vẫn cao dù consumer đã poll được nhiều record.

| Partition | Committed offset | End offset | Lag |
| --- | ---: | ---: | ---: |
| orders-0 | 12.300 | 12.450 | 150 |
| orders-1 | 8.900 | 8.920 | 20 |
| orders-2 | 5.100 | 5.100 | 0 |
| **Tổng** |  |  | **170** |

Tổng lag là tổng các khoảng cách offset của từng partition. Nó hữu ích để theo dõi xu hướng chung, nhưng có thể che khuất partition bị nghẽn. Trong ví dụ, `orders-0` chiếm phần lớn lag và cần được điều tra riêng.

## 4. Offset distance không luôn bằng số record thực tế

Phép trừ end offset và committed offset thường được gọi là số record lag, nhưng chính xác hơn đó là khoảng cách offset. Hai khái niệm có thể khác nhau:

- Topic compacted có thể xóa record cũ nhưng vẫn giữ các offset phía sau, tạo khoảng trống trong dãy offset.
- Transaction bị abort có thể để lại offset không hiển thị cho consumer `read_committed`.
- Control record và các cơ chế nội bộ của Kafka có thể làm khoảng cách offset khác số record nghiệp vụ mà listener nhận được.
- Một số exporter báo lag theo offset distance, trong khi metric của consumer có thể dựa trên position và dữ liệu có thể đọc.

Vì vậy, lag `1.000` không nhất thiết có nghĩa listener sẽ nhận đúng 1.000 record nghiệp vụ. Hãy xem đây là chỉ số khoảng cách tiến độ và kết hợp với record rate, timestamp và trạng thái consumer.

## 5. High watermark và Last Stable Offset

Ngoài LEO, Kafka còn có hai mốc quan trọng khi phân tích lag:

- **High watermark (HW):** mốc cuối của dữ liệu đã được replicate đủ theo điều kiện Kafka để consumer thông thường có thể đọc. HW thường thấp hơn hoặc bằng LEO.
- **Last Stable Offset (LSO):** mốc giới hạn dữ liệu mà consumer dùng `isolation.level=read_committed` có thể đọc khi có transaction chưa hoàn tất. LSO có thể thấp hơn HW nếu partition đang có transaction mở.

Ví dụ, LEO là `500`, HW là `490`, còn LSO là `470` do có transaction chưa kết thúc bắt đầu tại vùng offset đó. Consumer `read_committed` chưa thể đọc qua LSO cho đến khi transaction liên quan được commit hoặc abort. Nếu dashboard tính lag từ LEO, nó có thể hiển thị khoảng cách lớn hơn phần dữ liệu hiện có thể đọc ngay.

Khi dùng Kafka transaction hoặc EOS, cần biết công cụ đang tính lag dựa trên LEO, HW hay LSO. Không nên kết luận consumer bị chậm chỉ từ chênh lệch với LEO nếu transaction đang mở và LSO chưa tiến lên.

## 6. Xem consumer lag bằng kafka-consumer-groups

Công cụ `kafka-consumer-groups` là cách nhanh để xem offset đã commit, end offset và lag theo group. Trên Windows, có thể chạy script `.bat` trong thư mục Kafka:

```powershell
.\bin\windows\kafka-consumer-groups.bat `
  --bootstrap-server localhost:9092 `
  --describe `
  --group orders-service
```

Kết quả thường có các cột như:

| Cột | Ý nghĩa |
| --- | --- |
| `TOPIC` | Topic mà group đang đọc |
| `PARTITION` | Partition cụ thể |
| `CURRENT-OFFSET` | Committed offset của group |
| `LOG-END-OFFSET` | End offset mà công cụ dùng để so sánh |
| `LAG` | Khoảng cách giữa end offset và committed offset |
| `CONSUMER-ID` | Consumer đang được assign partition |
| `HOST` | Host của consumer |
| `CLIENT-ID` | Client ID của consumer |

Để xem trạng thái group và thành viên, có thể dùng:

```powershell
.\bin\windows\kafka-consumer-groups.bat `
  --bootstrap-server localhost:9092 `
  --describe `
  --group orders-service `
  --state

.\bin\windows\kafka-consumer-groups.bat `
  --bootstrap-server localhost:9092 `
  --describe `
  --group orders-service `
  --members `
  --verbose
```

Tên cột và tùy chọn có thể khác theo phiên bản Kafka CLI. Nếu `CURRENT-OFFSET` chưa có, group có thể chưa commit offset cho partition đó; hãy kiểm tra trạng thái group và `auto.offset.reset` trước khi diễn giải lag.

## 7. Theo dõi lag bằng consumer metrics

Kafka Java consumer cung cấp các metric hữu ích để phân tích tốc độ và tiến độ. Tên metric có thể thay đổi theo phiên bản client và cách expose qua JMX/Micrometer, nhưng các nhóm chỉ số thường cần theo dõi gồm:

| Metric | Ý nghĩa vận hành |
| --- | --- |
| `records-lag-max` | Lag lớn nhất trong các partition được consumer theo dõi theo định nghĩa metric client |
| `records-consumed-rate` | Tốc độ consumer nhận record |
| `bytes-consumed-rate` | Tốc độ dữ liệu consumer nhận, theo byte/giây |
| `fetch-rate` | Tốc độ các fetch request |
| `fetch-latency-avg` | Độ trễ trung bình của fetch request |
| `commit-rate` | Tần suất commit offset |
| `commit-latency-avg` | Độ trễ trung bình của commit |
| `assigned-partitions` | Số partition được assign cho consumer |
| `poll-idle-ratio-avg` | Tỷ lệ thời gian consumer không bận xử lý poll theo định nghĩa client |
| `heartbeat-rate` | Tốc độ gửi heartbeat trong consumer group |

`records-lag-max` là metric theo góc nhìn consumer và không nhất thiết bằng committed lag lấy từ group offsets. Hãy đặt tên dashboard rõ ràng để phân biệt metric lag theo consumer position với lag tính từ committed offset.

Trong Spring Kafka, có thể đưa Kafka client metrics vào JMX hoặc Micrometer tùy cách cấu hình ứng dụng. Với Spring Boot Actuator và Micrometer, hãy kiểm tra metric thực tế được expose trong endpoint metrics và Prometheus scrape; không giả định mọi metric Kafka đều tự động có cùng tên trong mọi phiên bản.

## 8. Phân biệt lag theo record và lag theo thời gian

Lag theo offset cho biết khoảng cách tiến độ. Lag theo thời gian cho biết record cũ nhất chưa xử lý đã chờ bao lâu. Hai chỉ số bổ sung cho nhau:

- **Offset lag:** khoảng cách offset giữa end và vị trí consumer/committed offset.
- **Time lag / record age:** tuổi của record cũ nhất mà consumer chưa xử lý, tính từ timestamp phù hợp.

Ví dụ, lag 10.000 record có thể không đáng lo nếu consumer xử lý 50.000 record/giây và backlog đang giảm. Ngược lại, lag 50 record có thể vi phạm SLA nếu record cũ nhất đã chờ 20 phút trong một luồng yêu cầu xử lý trong 30 giây.

Khi tính time lag, cần biết timestamp đang dùng là `CreateTime` do producer cung cấp hay `LogAppendTime` do broker gán. `CreateTime` có thể bị ảnh hưởng bởi đồng hồ producer; event time trong payload còn có thể cũ hơn thời điểm record được publish. Hãy chọn một mốc timestamp nhất quán với SLA nghiệp vụ.

## 9. Đọc xu hướng lag thay vì một ảnh chụp

Lag thay đổi theo chênh lệch giữa tốc độ dữ liệu đến và tốc độ xử lý:

\[
\Delta \text{lag} \approx (\text{incoming rate} - \text{processing rate}) \times \Delta t
\]

Đây là mô hình xấp xỉ trong một khoảng thời gian, giả định partition assignment và offset không bị reset. Nếu producer ghi nhanh hơn consumer xử lý, lag tăng. Nếu consumer xử lý nhanh hơn lượng record mới, lag giảm.

| Diễn biến | Cách diễn giải ban đầu |
| --- | --- |
| Lag thấp và ổn định | Consumer theo kịp tải hiện tại |
| Lag tăng đều | Tốc độ xử lý thấp hơn tốc độ record đến |
| Lag tăng đột ngột rồi giảm | Có burst traffic hoặc consumer tạm gián đoạn rồi bắt kịp |
| Lag cao nhưng giảm đều | Consumer đang xử lý backlog; theo dõi thời gian dự kiến để bắt kịp |
| Lag chỉ cao ở một partition | Có thể có key nóng, phân phối key lệch hoặc record gây xử lý chậm |
| Lag tăng ở tất cả partition | Có thể thiếu năng lực consumer, downstream chậm hoặc broker/network gặp vấn đề |
| Lag bằng 0 nhưng SLA vẫn trễ | Có thể metric không phản ánh time lag, commit quá sớm hoặc timestamp/offset được diễn giải sai |

Không cảnh báo chỉ dựa trên một lần scrape. Hãy dùng cửa sổ thời gian, tốc độ tăng lag và tuổi record để phân biệt burst ngắn với sự cố kéo dài.

## 10. Các nguyên nhân phổ biến khiến lag tăng

### Consumer xử lý chậm

Listener gọi database, REST service hoặc xử lý CPU nặng. Nếu thời gian xử lý mỗi record tăng, consumer throughput giảm. Đo thời gian listener, độ trễ downstream và số record xử lý mỗi giây trước khi tăng concurrency.

### Consumer group thiếu consumer hoặc partition

Một group chỉ có thể xử lý song song tối đa theo số partition được assign. Tăng concurrency vượt số partition không tạo thêm mức song song hữu ích. Nếu cần thêm năng lực, kiểm tra partition count, consumer count, key distribution và giới hạn downstream.

### Rebalance lặp lại

Consumer xử lý lâu hơn `max.poll.interval.ms`, mất heartbeat hoặc liên tục restart có thể khiến group rebalance. Trong thời gian rebalance, việc xử lý bị gián đoạn và lag tăng. Theo dõi rebalance rate, heartbeat, poll interval và log container.

### Record lỗi bị retry liên tục

Một poison record hoặc dịch vụ phụ thuộc lỗi có thể khiến consumer mất thời gian retry. Với blocking retry, record lỗi có thể chặn các record phía sau trong partition. Với retry topic, cần theo dõi lag riêng ở các retry topic và DLT.

### Backpressure hoặc partition đang pause

Ứng dụng có thể chủ động pause consumer khi queue downstream đầy. Khi pause, consumer không nhận thêm record từ partition đã pause nên lag tăng là hành vi dự kiến. Cần theo dõi thời lượng pause, queue depth và điều kiện resume.

### Offset không được commit

Listener có thể xử lý record nhưng không acknowledge theo `AckMode` hoặc transaction bị abort. Consumer position tiến lên nhưng committed offset đứng yên, làm committed lag vẫn cao. Kiểm tra commit rate, commit latency, exception và acknowledgment flow.

## 11. Phân tích lag theo partition và key

Tổng lag của group có thể che khuất một partition nóng. Hãy sắp xếp partition theo lag giảm dần và kiểm tra:

- Partition có lag cao có nhận phần lớn traffic hay không.
- Key nào chiếm nhiều record hoặc có xử lý lâu bất thường.
- Một record cụ thể có gây retry hoặc block listener không.
- Partition có đang pause hoặc không có consumer được assign không.
- Số consumer và số partition có phù hợp với concurrency mong muốn không.

Kafka bảo đảm thứ tự trong một partition. Nếu một key liên tục được map vào partition có xử lý chậm, tăng consumer count không thể chia nhỏ thứ tự của key đó. Có thể cần xem lại partition key, thiết kế tác vụ, hoặc tách workload theo loại sự kiện nếu nghiệp vụ cho phép.

## 12. Lag và nguy cơ retention

Kafka retention không chờ consumer xử lý xong mới xóa record. Topic có thể xóa segment theo `retention.ms` hoặc `retention.bytes` ngay cả khi consumer group còn lag. Nếu record chưa được consumer đọc đã hết retention, consumer có thể không còn khả năng đọc lại dữ liệu đó.

Hãy so sánh tuổi của record cũ nhất chưa xử lý với thời gian retention thực tế của topic. Khi backlog tăng kéo dài:

1. Ước lượng thời gian để consumer bắt kịp dựa trên incoming rate và processing rate.
2. So sánh thời gian đó với phần retention còn lại của record cũ nhất.
3. Nếu có nguy cơ hết retention, tăng năng lực xử lý hoặc điều chỉnh retention theo quy trình vận hành đã đánh giá dung lượng broker.
4. Nếu dữ liệu đã hết retention, xác định nguồn replay/backup phù hợp; không giả định Kafka có thể phục hồi record đã bị xóa.

Với topic compacted, dữ liệu cũ có thể bị compact theo key dù retention time chưa hết. Khi tính backlog cho topic compacted, offset distance càng không thể xem là số lượng record nghiệp vụ chính xác.

## 13. Cách xử lý khi lag cao

Một quy trình điều tra có thể thực hiện theo thứ tự:

1. Xác định đúng `group.id`, topic và partition bị lag; kiểm tra group đang `Stable`, `PreparingRebalance`, `Empty` hay trạng thái khác.
2. Xem lag theo partition và xác định lag tập trung hay phân tán.
3. So sánh producer rate với consumer record rate để biết backlog đang tăng hay giảm.
4. Kiểm tra consumer assignment, số consumer đang hoạt động, rebalance và heartbeat.
5. Kiểm tra thời gian xử lý listener, downstream latency, retry, DLT và queue backpressure.
6. Kiểm tra commit rate/latency, AckMode và transaction nếu position tiến nhưng committed offset không tiến.
7. Kiểm tra broker/network, request latency, fetch rate và quota nếu consumer không lấy được dữ liệu đủ nhanh.
8. Ước lượng thời gian bắt kịp và so sánh với retention/SLA.
9. Chọn hành động phù hợp: sửa lỗi downstream, giảm thời gian listener, tăng consumer trong giới hạn partition, tối ưu batch, hoặc bổ sung partition sau khi đánh giá ordering và key distribution.

Không reset offset chỉ để làm dashboard lag về 0. Reset có thể bỏ qua dữ liệu chưa xử lý hoặc khiến dữ liệu được xử lý lại. Chỉ thay đổi offset theo quy trình được phê duyệt, có kiểm tra group, partition, vị trí đích và tác động nghiệp vụ.

## 14. Thiết kế dashboard và cảnh báo

Dashboard vận hành nên có ít nhất:

- Tổng lag theo consumer group và topic.
- Lag lớn nhất theo partition và danh sách partition top N.
- Lag theo thời gian và tốc độ tăng/giảm.
- Tuổi record cũ nhất chưa xử lý.
- Producer incoming rate và consumer processing rate.
- Consumer count, assigned partitions, rebalance rate và heartbeat.
- Listener processing time, retry count, DLT rate và pause duration.
- Broker request/fetch latency và network throughput khi cần điều tra sâu.

Đặt cảnh báo theo SLA thay vì một ngưỡng cố định cho mọi topic. Ví dụ, luồng cập nhật trạng thái đơn hàng có thể yêu cầu time lag dưới vài chục giây, trong khi luồng phân tích batch có thể chấp nhận backlog nhiều phút. Nên kết hợp điều kiện lag vượt ngưỡng trong một khoảng thời gian và tuổi record vượt SLA để giảm cảnh báo giả.

## 15. Checklist vận hành

- [ ] Đã xác định lag đang đo từ committed offset hay consumer position.
- [ ] Đã hiểu end offset được dùng là LEO, HW hay readable end/LSO.
- [ ] Theo dõi lag riêng cho từng partition, không chỉ tổng group.
- [ ] Kết hợp offset lag với time lag/record age.
- [ ] So sánh incoming rate và processing rate để biết backlog tăng hay giảm.
- [ ] Theo dõi consumer count, assigned partitions, heartbeat và rebalance.
- [ ] Kiểm tra retry, DLT, pause/backpressure và commit flow khi lag tăng.
- [ ] So sánh thời gian bắt kịp với retention của topic.
- [ ] Có dashboard và alert theo SLA của từng luồng sự kiện.
- [ ] Không reset offset chỉ để xóa lag khỏi dashboard.

Consumer lag là chỉ báo về tiến độ đọc của consumer group, không phải một con số độc lập đủ để kết luận hệ thống khỏe hay lỗi. Diễn giải đúng committed offset, consumer position và end offset; xem lag theo partition và theo thời gian; sau đó đối chiếu với throughput, rebalance, retry và retention. Cách nhìn này giúp xác định consumer đang thực sự thiếu năng lực, chỉ đang xử lý một burst hợp lệ hay bị chặn bởi một lỗi vận hành cụ thể.
