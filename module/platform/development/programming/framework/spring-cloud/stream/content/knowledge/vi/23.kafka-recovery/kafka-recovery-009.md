# Reset offset để phục hồi và đánh giá phạm vi ảnh hưởng

Kafka lưu tiến độ tiêu thụ riêng cho từng consumer group và từng partition. Khi consumer xử lý sai dữ liệu, bỏ lỡ một khoảng sự kiện hoặc cần dựng lại projection, đội vận hành có thể reset committed offset để group đọc lại từ một vị trí đã chọn. Ngược lại, khi muốn bỏ qua một đoạn dữ liệu đã biết là không cần xử lý, có thể đưa offset tiến về phía trước.

Reset offset là thao tác thay đổi tiến độ tiêu thụ của group, không sửa hoặc xóa record trong topic. Vì vậy, phạm vi ảnh hưởng phụ thuộc vào group, topic và partition được chọn. Reset lùi có thể làm message được xử lý lại và lặp tác dụng phụ; reset tiến có thể khiến message chưa được xử lý bị bỏ qua. Trong ứng dụng Spring Cloud Stream, mọi instance cùng dùng một group sẽ cùng chịu ảnh hưởng của thay đổi offset đó.

Bài học này hướng dẫn cách kiểm tra trạng thái group, lập kế hoạch reset, dùng Kafka CLI ở chế độ dry-run, đánh giá ảnh hưởng của từng lựa chọn offset và phục hồi an toàn trong môi trường Spring Cloud Stream.

## Mục tiêu học tập

Sau bài học, bạn có thể:

- Giải thích committed offset và phạm vi của một consumer group.
- Xác định chính xác group, topic và partition cần phục hồi.
- Đọc current offset, log end offset, log start offset và consumer lag.
- Phân biệt reset lùi để replay với reset tiến để bỏ qua dữ liệu.
- Dùng `kafka-consumer-groups.sh` để mô phỏng và thực thi reset.
- Chọn `earliest`, `latest`, offset cụ thể, `shift-by` hoặc timestamp phù hợp.
- Đánh giá tác động tới mọi instance Spring Cloud Stream cùng group.
- Lập kế hoạch snapshot, rollback, idempotency và theo dõi sau reset.
- Phân biệt reset offset của consumer thông thường với khôi phục trạng thái Kafka Streams.

## 1. Offset được lưu theo group và partition

Kafka ghi record trong từng partition với offset tăng dần. Consumer group lưu committed offset độc lập cho mỗi partition mà group tiêu thụ. Ví dụ, group `order-processor` có thể đã commit:

| Topic | Partition | Committed offset | Log end offset | Lag minh họa |
|---|---:|---:|---:|---:|
| orders | 0 | 120 | 150 | 30 |
| orders | 1 | 95 | 110 | 15 |
| orders | 2 | 210 | 210 | 0 |

Committed offset thường biểu thị vị trí tiếp theo consumer sẽ đọc. Nếu committed offset của partition 0 là 120, consumer tiếp tục từ record có offset 120 nếu record đó vẫn còn trong log. Khi reset về 80, consumer có thể đọc lại từ offset 80 tới phần dữ liệu mới hơn. Khi reset tới 140, consumer bỏ qua các record từ 120 đến 139 theo tiến độ mới của group.

Một topic có nhiều group thì mỗi group có tiến độ riêng. Reset group `order-processor` không thay đổi committed offset của group `order-audit`. Trong cùng một group, tất cả instance đang chia nhau partition chịu ảnh hưởng của committed offset mới sau lần assignment/khởi động tiếp theo.

~~~mermaid
flowchart TD
    T["Kafka topic: orders"] --> P0["Partition 0"]
    T --> P1["Partition 1"]
    T --> P2["Partition 2"]
    P0 --> G1["Group: order-processor<br/>offset 120"]
    P1 --> G1
    P2 --> G1
    P0 --> G2["Group: order-audit<br/>offset độc lập"]
    P1 --> G2
    P2 --> G2
~~~

Reset offset không đổi dữ liệu trong topic, không thay đổi offset của group khác và không tự xóa DLQ. Nó chỉ thay đổi vị trí mà group được yêu cầu tiếp tục tiêu thụ.

## 2. Khi nào nên reset offset?

Các tình huống thường gặp:

- Consumer có lỗi logic và đã ghi trạng thái sai; cần chạy lại một khoảng sự kiện sau khi sửa lỗi.
- Projection hoặc read model cần dựng lại từ dữ liệu nguồn còn lưu.
- Một đoạn record được xác nhận là không hợp lệ và có quyết định nghiệp vụ bỏ qua.
- Consumer group bị đưa tới offset quá xa về phía trước do cấu hình hoặc thao tác nhầm.
- Cần replay một khoảng thời gian để đối soát dữ liệu.
- Cần đồng bộ lại tiến độ group sau khi thay đổi quy trình xử lý.

Trước khi reset, cần trả lời ba câu hỏi:

1. **Mục tiêu là gì?** Đọc lại để sửa trạng thái, hay bỏ qua dữ liệu?
2. **Phạm vi nào cần thay đổi?** Một partition, một topic hay toàn bộ topic của group?
3. **Tác dụng phụ nào có thể lặp hoặc bị bỏ qua?** Ghi database, gửi email, phát lệnh thanh toán hoặc cập nhật dịch vụ ngoài?

Không reset chỉ vì consumer lag tăng. Lag có thể do tốc độ xử lý thấp, số partition ít, dịch vụ phụ thuộc chậm hoặc consumer không hoạt động. Reset offset không khắc phục nguyên nhân throughput; reset tiến còn có thể làm mất công việc đang chờ xử lý.

## 3. Đánh giá phạm vi ảnh hưởng trước khi thao tác

Một lệnh reset cần xác định chính xác:

- Kafka cluster và bootstrap servers.
- Consumer group ID.
- Topic đích.
- Partition cụ thể hoặc toàn bộ partition của topic.
- Vị trí offset mới.
- Các instance đang chạy group đó.
- Các hệ thống downstream có thể nhận lại message.

Trong Spring Cloud Stream, group được khai báo ở input binding:

~~~yaml
spring:
  cloud:
    function:
      definition: processOrder
    stream:
      bindings:
        processOrder-in-0:
          destination: orders
          group: order-processor
~~~

Các replica của cùng ứng dụng dùng group `order-processor` tham gia cùng consumer group. Reset group này ảnh hưởng tới tiến độ tiêu thụ của tất cả replica, không chỉ một pod hoặc một instance.

Nếu có nhiều binding cùng dùng group hoặc một ứng dụng khác cũng dùng group ID đó, chúng có thể cùng tham gia tiến độ tiêu thụ tương ứng. Kiểm tra cấu hình triển khai và thành viên group trước khi thực thi.

### Kiểm tra trạng thái group

Liệt kê group:

~~~bash
kafka-consumer-groups.sh \
  --bootstrap-server kafka-1:9092 \
  --list
~~~

Xem offset và lag:

~~~bash
kafka-consumer-groups.sh \
  --bootstrap-server kafka-1:9092 \
  --describe \
  --group order-processor
~~~

Xem trạng thái group và thành viên (tùy phiên bản Kafka CLI):

~~~bash
kafka-consumer-groups.sh \
  --bootstrap-server kafka-1:9092 \
  --describe \
  --group order-processor \
  --state
~~~

~~~bash
kafka-consumer-groups.sh \
  --bootstrap-server kafka-1:9092 \
  --describe \
  --group order-processor \
  --members \
  --verbose
~~~

Đọc kết quả để xác nhận group đang ổn định hay đang rebalance, partition nào được gán cho member nào và lag nằm ở đâu. Tên cờ có thể khác giữa các bản phân phối hoặc phiên bản; kiểm tra `kafka-consumer-groups.sh --help` trên đúng Kafka CLI đang vận hành.

## 4. Dừng consumer trước khi reset

Kafka CLI yêu cầu group không có consumer active khi reset offset. Nếu group vẫn có member, lệnh reset thường bị từ chối hoặc có thể xung đột với tiến độ tiêu thụ đang chạy. Vì vậy, hãy:

1. Dừng tất cả replica của ứng dụng dùng group cần reset.
2. Tạm dừng autoscaler hoặc controller có thể tự tạo lại pod.
3. Dừng các job, worker hoặc ứng dụng khác dùng cùng group ID.
4. Chờ group không còn member active.
5. Kiểm tra lại trạng thái group và offset.
6. Thực hiện dry-run, xem kết quả rồi mới execute.

Không chỉ scale một deployment xuống 0 nếu còn một ứng dụng khác dùng cùng group. Cũng cần kiểm tra các tiến trình chạy theo lịch hoặc consumer chạy ngoài Kubernetes.

Sau khi reset xong, chỉ khởi động lại consumer khi đã xác nhận offset mới và phạm vi thay đổi đúng với kế hoạch.

## 5. Snapshot committed offset trước khi thay đổi

Trước thao tác có ảnh hưởng production, hãy lưu lại offset hiện tại để có thể khôi phục tiến độ nếu reset sai. Kafka CLI hỗ trợ xuất offset group ra file trong quy trình reset.

Ví dụ xuất offset để lưu snapshot:

~~~bash
kafka-consumer-groups.sh \
  --bootstrap-server kafka-1:9092 \
  --group order-processor \
  --topic orders \
  --reset-offsets \
  --to-current \
  --dry-run \
  --export > order-processor-offsets.csv
~~~

Ví dụ trên chuyển dữ liệu export từ stdout vào file `order-processor-offsets.csv`. Tùy phiên bản Kafka, cách kết hợp `--export` với `--dry-run` có thể khác. Hãy kiểm tra phần trợ giúp của CLI đang cài đặt và xác nhận file được tạo, có đủ group, topic, partition và offset. Không coi một dòng lệnh đã chạy là snapshot hợp lệ nếu chưa kiểm tra file thực tế.

Một file offset snapshot cần được bảo vệ như dữ liệu vận hành. Ghi lại:
- Cluster và thời điểm export.
- Group ID.
- Topic/partition.
- Committed offset trước reset.
- Người hoặc quy trình thực hiện.
- Mục tiêu và lý do reset.

Không sửa thủ công file export mà không xác minh định dạng. Nếu dùng file để import/khôi phục offset, giữ nguyên cấu trúc mà CLI yêu cầu.

## 6. Luôn dry-run trước khi execute

Kafka CLI hỗ trợ `--reset-offsets` với chế độ mô phỏng và chế độ thực thi. Nếu không dùng `--execute`, lệnh reset thông thường hiển thị các offset dự kiến thay đổi mà không ghi thay đổi vào group. Dùng `--dry-run` để thể hiện rõ ý định mô phỏng.

Ví dụ xem tác động nếu reset toàn bộ partition của topic về earliest:

~~~bash
kafka-consumer-groups.sh \
  --bootstrap-server kafka-1:9092 \
  --group order-processor \
  --topic orders \
  --reset-offsets \
  --to-earliest \
  --dry-run
~~~

Đọc kết quả cho từng partition:
- Offset hiện tại.
- Offset đề xuất sau reset.
- Partition có bị thay đổi hay không.
- Partition nào không còn dữ liệu hoặc có trạng thái bất thường.

Chỉ khi kết quả đúng với phạm vi đã duyệt mới chạy lại lệnh với `--execute`:

~~~bash
kafka-consumer-groups.sh \
  --bootstrap-server kafka-1:9092 \
  --group order-processor \
  --topic orders \
  --reset-offsets \
  --to-earliest \
  --execute
~~~

Không bỏ qua dry-run vì lệnh reset có thể thay đổi nhiều partition cùng lúc. Nếu kết quả dry-run không đúng, dừng lại, kiểm tra group, topic, partition và tùy chọn reset trước khi tiếp tục.

## 7. Chọn vị trí mới: earliest, latest và offset cụ thể

Kafka CLI hỗ trợ nhiều chiến lược đặt offset. Mỗi chiến lược có phạm vi ảnh hưởng khác nhau.

| Tùy chọn | Vị trí đích | Trường hợp dùng |
|---|---|---|
| `--to-earliest` | Offset sớm nhất còn được giữ trong mỗi partition được chọn | Dựng lại dữ liệu từ phần log còn lưu |
| `--to-latest` | Vị trí cuối log hiện tại | Bỏ qua backlog và chỉ nhận dữ liệu mới |
| `--to-offset N` | Offset N trong partition được chọn | Bắt đầu lại từ mốc đã xác định |
| `--shift-by N` | Dịch committed offset hiện tại thêm N | Lùi hoặc tiến một khoảng tương đối |
| `--to-datetime` | Vị trí tương ứng timestamp | Replay từ một thời điểm |
| `--by-duration` | Vị trí theo khoảng thời gian tính lùi từ hiện tại | Replay một cửa sổ thời gian |
| `--to-current` | Giữ vị trí hiện tại | Xuất/đối chiếu offset mà không thay đổi tiến độ |

### Reset về earliest

~~~bash
kafka-consumer-groups.sh \
  --bootstrap-server kafka-1:9092 \
  --group order-rebuild \
  --topic orders \
  --reset-offsets \
  --to-earliest \
  --dry-run
~~~

`earliest` là offset nhỏ nhất còn có thể đọc trong log, không nhất thiết là 0. Nếu retention đã xóa dữ liệu cũ, reset không thể khôi phục những record đó.

### Reset về latest

~~~bash
kafka-consumer-groups.sh \
  --bootstrap-server kafka-1:9092 \
  --group live-monitor \
  --topic system-events \
  --reset-offsets \
  --to-latest \
  --dry-run
~~~

`latest` đưa vị trí đọc tới cuối log hiện tại. Group sẽ bỏ qua backlog đang tồn tại tại thời điểm reset và nhận record mới được ghi sau đó. Chỉ dùng khi quyết định bỏ qua dữ liệu cũ đã được chấp thuận.

### Reset tới offset cụ thể

~~~bash
kafka-consumer-groups.sh \
  --bootstrap-server kafka-1:9092 \
  --group order-processor \
  --topic orders:1 \
  --reset-offsets \
  --to-offset 500 \
  --dry-run
~~~

Ví dụ nhắm partition 1 của topic `orders`. Offset 500 là vị trí consumer sẽ bắt đầu đọc tiếp theo nếu offset đó hợp lệ trong partition. Kiểm tra log start/end offset trước khi chọn; offset ngoài phạm vi có thể bị từ chối hoặc chịu chính sách out-of-range khi consumer khởi động.

Cú pháp chỉ định topic/partition và khả năng dùng `--to-offset` có thể phụ thuộc phiên bản CLI. Luôn kiểm tra kết quả dry-run cho từng partition.

## 8. Dịch chuyển offset bằng shift-by

`--shift-by` thay đổi offset hiện tại theo một số lượng tương đối:

- Giá trị âm: dịch lùi, đọc lại record đã xử lý trước đó.
- Giá trị dương: dịch tiến, bỏ qua một số record chưa xử lý.
- Giá trị 0: không thay đổi vị trí.

Ví dụ lùi 100 record trên mỗi partition được chọn:

~~~bash
kafka-consumer-groups.sh \
  --bootstrap-server kafka-1:9092 \
  --group order-processor \
  --topic orders \
  --reset-offsets \
  --shift-by -100 \
  --dry-run
~~~

Ví dụ tiến 20 record:

~~~bash
kafka-consumer-groups.sh \
  --bootstrap-server kafka-1:9092 \
  --group order-processor \
  --topic orders \
  --reset-offsets \
  --shift-by 20 \
  --dry-run
~~~

Shift-by được tính theo committed offset của từng partition, không phải một dải offset liên tục toàn topic. Với partition có tốc độ ghi khác nhau, cùng một shift có thể đại diện khoảng thời gian khác nhau.

Offset kết quả phải nằm trong phạm vi dữ liệu còn đọc được. Kiểm tra kết quả mô phỏng để phát hiện offset bị giới hạn ở log start hoặc vượt quá log end. Không tự tính offset mới rồi giả định mọi partition có cùng tiến độ.

## 9. Reset theo timestamp hoặc khoảng thời gian

Khi biết thời điểm sự cố, có thể reset offset theo timestamp thay vì đoán một số offset.

Ví dụ bắt đầu đọc từ một mốc thời gian:

~~~bash
kafka-consumer-groups.sh \
  --bootstrap-server kafka-1:9092 \
  --group order-processor \
  --topic orders \
  --reset-offsets \
  --to-datetime 2026-11-20T09:30:00.000 \
  --dry-run
~~~

Hoặc đọc lại dữ liệu trong khoảng 2 giờ gần nhất:

~~~bash
kafka-consumer-groups.sh \
  --bootstrap-server kafka-1:9092 \
  --group order-processor \
  --topic orders \
  --reset-offsets \
  --by-duration PT2H \
  --dry-run
~~~

Kafka tìm offset theo timestamp của record và metadata index của partition. Nếu partition không có record tương ứng hoặc timestamp nằm ngoài dữ liệu được giữ, kết quả có thể khác mong đợi. Kiểm tra offset dự kiến cho từng partition trước khi execute.

Cần phân biệt:
- Thời điểm nghiệp vụ trong payload, chẳng hạn `occurredAt`.
- Timestamp Kafka record.
- Thời điểm consumer nhận hoặc xử lý message.

`--to-datetime` dựa trên timestamp của Kafka record, không đọc trường thời gian nghiệp vụ trong payload. Nếu producer dùng timestamp không đồng nhất hoặc dữ liệu được backfill, replay theo timestamp có thể không tương ứng chính xác với thời điểm nghiệp vụ.

## 10. Giới hạn phạm vi bằng topic và partition

Lệnh reset có thể nhắm:
- Một topic cụ thể.
- Một partition cụ thể của topic.
- Nhiều topic được liệt kê.
- Tất cả topic mà group đã tiêu thụ, nếu dùng tùy chọn tương ứng của CLI.

Ưu tiên chỉ định topic và partition cần phục hồi. Không dùng `--all-topics` nếu sự cố chỉ liên quan một topic. Một group có thể tiêu thụ nhiều topic; reset toàn bộ group có thể làm các luồng nghiệp vụ khác đọc lại hoặc bỏ qua dữ liệu ngoài phạm vi sự cố.

Ví dụ chỉ reset partition 2:

~~~bash
kafka-consumer-groups.sh \
  --bootstrap-server kafka-1:9092 \
  --group order-processor \
  --topic orders:2 \
  --reset-offsets \
  --to-earliest \
  --dry-run
~~~

Nếu một topic có nhiều partition và chỉ một partition bị lỗi, reset riêng partition đó giúp giảm phạm vi replay. Tuy nhiên, nếu nghiệp vụ yêu cầu thứ tự toàn aggregate và khóa có thể nằm ở nhiều partition, cần kiểm tra quan hệ giữa partition và dữ liệu trước khi reset một phần.

## 11. Ảnh hưởng khi reset lùi: duplicate và side effect

Reset lùi khiến consumer đọc lại record đã có thể từng xử lý thành công. Điều này có thể tạo:
- Bản ghi database trùng.
- Email hoặc thông báo được gửi lại.
- Lệnh thanh toán hoặc hoàn tiền bị thực hiện nhiều lần.
- Sự kiện downstream bị phát lại.
- Counter hoặc số liệu tăng hai lần.
- Projection bị áp dụng lại event cũ.

Trước khi reset lùi:
1. Xác minh consumer có idempotent hay không.
2. Kiểm tra inbox/deduplication key theo event ID.
3. Kiểm tra API ngoài có hỗ trợ idempotency key.
4. Xác định side effect nào cần tạm dừng hoặc chạy ở chế độ replay.
5. Xác định event version và thứ tự aggregate.
6. Chạy thử trên group riêng hoặc môi trường staging nếu có thể.
7. Đặt giới hạn tốc độ để replay không gây quá tải downstream.

Không dựa vào Kafka producer idempotence để ngăn consumer xử lý trùng. Producer idempotence bảo vệ một số trường hợp retry gửi trong producer session; nó không tự ngăn consumer thực hiện side effect lần nữa khi group đọc lại record.

## 12. Ảnh hưởng khi reset tiến: bỏ qua dữ liệu

Reset tiến có thể khiến consumer không bao giờ đọc lại những record nằm giữa committed offset cũ và offset mới. Đây là thao tác có nguy cơ mất xử lý ở cấp ứng dụng, dù record vẫn còn trong Kafka topic.

Trước khi reset tiến:
- Xác minh record trong khoảng bị bỏ qua không cần xử lý.
- Đối chiếu trạng thái nghiệp vụ hoặc báo cáo bù.
- Kiểm tra có consumer group khác giữ dữ liệu để đối soát không.
- Lưu snapshot offset cũ.
- Ghi lại lý do, khoảng offset và người phê duyệt.
- Chuẩn bị quy trình bù dữ liệu nếu quyết định bỏ qua bị sai.

Ví dụ committed offset là 100, reset tới 150. Consumer tiếp tục từ 150; record 100 đến 149 sẽ không được group xử lý qua luồng bình thường. Việc record còn tồn tại trong topic không có nghĩa consumer tự quay lại đọc chúng.

## 13. Kế hoạch reset an toàn trong Spring Cloud Stream

Một quy trình production có thể chia thành các giai đoạn:

### Giai đoạn A: chuẩn bị

1. Xác định input binding và group ID thực tế.
2. Xác định Kafka cluster và topic.
3. Đọc offset/lag theo partition.
4. Kiểm tra các member trong group.
5. Dừng tất cả consumer instance và ngăn autoscaler tạo lại.
6. Export/snapshot committed offsets.
7. Xác định vị trí mới và phạm vi topic/partition.
8. Đánh giá duplicate hoặc skipped records.

### Giai đoạn B: mô phỏng

1. Chạy `--reset-offsets` với lựa chọn dự kiến và `--dry-run`.
2. Đọc toàn bộ kết quả từng partition.
3. So sánh offset cũ và mới.
4. Tính khoảng record sẽ replay hoặc bị bỏ qua.
5. Kiểm tra log start/end offset và retention.
6. Lưu kết quả dry-run cùng change record.

### Giai đoạn C: thực thi

1. Xác nhận group không có consumer active.
2. Chạy lại chính xác lệnh đã dry-run với `--execute`.
3. Đọc kết quả CLI và xác minh committed offset mới.
4. Không khởi động consumer nếu offset hoặc phạm vi không đúng.

### Giai đoạn D: khởi động và quan sát

1. Khởi động một instance trước nếu quy trình triển khai cho phép.
2. Kiểm tra log group assignment và vị trí đọc thực tế.
3. Theo dõi consumer lag, throughput và error rate.
4. Theo dõi duplicate suppression, DLQ và side effect.
5. Mở rộng các instance còn lại khi luồng ổn định.
6. Đối chiếu kết quả nghiệp vụ và đóng change record.

Trong Spring Cloud Stream, `startOffset` không phải công cụ reset thường xuyên cho một group đã có committed offset. Khi offset đã tồn tại, binder thường tiếp tục từ offset đó. Reset vận hành bằng Kafka CLI có phạm vi rõ ràng hơn và cần được phối hợp với trạng thái các consumer.

## 14. Rollback khi reset sai

Reset offset có thể được đảo lại bằng cách reset group về offset snapshot đã lưu, miễn là dữ liệu tương ứng còn tồn tại và group đang không hoạt động. Tuy nhiên, rollback tiến độ không tự đảo ngược side effect đã xảy ra.

Ví dụ, reset lùi làm consumer gửi lại email. Đưa offset trở lại giá trị cũ không thể thu hồi email đã gửi. Reset tiến khiến group bỏ qua thanh toán, đưa offset lùi lại có thể cho phép xử lý lại record nhưng chỉ an toàn nếu nghiệp vụ có cơ chế chống trùng.

Một kế hoạch rollback cần:
- Snapshot offset trước thay đổi.
- Lệnh hoặc file import khôi phục đã được kiểm tra.
- Quy trình dừng consumer trước rollback.
- Đánh giá side effect phát sinh trong khoảng reset.
- Đối soát trạng thái nghiệp vụ sau rollback.
- Ghi nhận offset cuối cùng và kết quả.

Nếu dùng file offset export để khôi phục, xác minh định dạng `--from-file` theo đúng phiên bản Kafka CLI. Chạy dry-run với file trước, kiểm tra từng partition rồi mới execute. Không dùng file snapshot từ cluster hoặc group khác.

Ví dụ mô phỏng khôi phục từ file snapshot:

~~~bash
kafka-consumer-groups.sh \
  --bootstrap-server kafka-1:9092 \
  --group order-processor \
  --reset-offsets \
  --from-file order-processor-offsets.csv \
  --dry-run
~~~

Chỉ chạy lại với `--execute` sau khi xác nhận group, topic, partition và offset trong file đều đúng.

## 15. Reset offset khác với khôi phục Kafka Streams state

Kafka Streams binder duy trì state store và changelog topic để phục hồi trạng thái ứng dụng. Reset committed offset của input consumer group bằng `kafka-consumer-groups.sh` không tự xóa hoặc tái tạo state store.

Nếu chỉ reset input offsets nhưng giữ state store cũ, ứng dụng có thể áp dụng lại record lên trạng thái đã chứa kết quả của lần xử lý trước. Kết quả có thể sai hoặc tạo duplicate trong state/output.

Với Kafka Streams:
- Xác định application ID và các input topics.
- Kiểm tra state store, changelog và output topics.
- Dừng ứng dụng trước thao tác reset.
- Dùng quy trình reset application của Kafka Streams phù hợp phiên bản khi cần dựng lại state.
- Xác định có xóa/rebuild local state và internal topics hay không.
- Không xóa changelog hoặc internal topic thủ công khi chưa hiểu tác động.
- Kiểm thử phục hồi state trên môi trường riêng trước khi thực hiện production.

Kafka Streams application reset là quy trình rộng hơn reset offset consumer thông thường. Hãy dùng công cụ và hướng dẫn dành riêng cho Kafka Streams thay vì chỉ chạy lệnh reset group.

## 16. Kiểm thử reset offset

Kiểm thử nên dùng Kafka broker riêng hoặc Testcontainers, với topic và group có thể tạo/xóa an toàn.

### Kiểm thử dry-run

1. Tạo topic có nhiều partition và ghi record mẫu.
2. Chạy consumer group để tạo committed offsets.
3. Dừng consumer.
4. Chạy reset về earliest với dry-run.
5. Xác minh CLI hiển thị offset dự kiến nhưng committed offset không đổi.
6. Chạy reset về latest với dry-run và so sánh phạm vi bỏ qua.

### Kiểm thử execute

1. Chạy lệnh reset đã được xác minh với execute.
2. Đọc lại group offsets bằng `--describe`.
3. Khởi động consumer.
4. Xác minh record được đọc từ vị trí mới.
5. Kiểm tra side effect và duplicate suppression.

### Kiểm thử partition scope

- Reset một partition và xác minh partition khác giữ nguyên offset.
- Reset một topic trong group có nhiều topic và xác minh topic còn lại không đổi.
- Thử group mới và group đã có committed offset.
- Thử offset gần log start và log end.
- Thử timestamp không có record tương ứng.

### Kiểm thử lỗi vận hành

- Thử reset khi group còn active và xác minh CLI từ chối.
- Thử offset nằm ngoài phạm vi.
- Thử snapshot/export và khôi phục từ file.
- Mô phỏng consumer khởi động lại trong lúc quy trình reset đang được điều phối; xác minh autoscaler hoặc supervisor không khởi động lại consumer quá sớm.

## 17. Lệnh tham khảo: kiểm tra và reset

Các ví dụ dưới đây dùng Kafka CLI trên môi trường minh họa. Thay bootstrap server, group, topic và partition theo môi trường thực tế; chạy `--help` để xác nhận tùy chọn có trong phiên bản cài đặt.

Xem group:

~~~bash
kafka-consumer-groups.sh \
  --bootstrap-server kafka-1:9092 \
  --describe \
  --group order-processor
~~~

Mô phỏng reset một topic về earliest:

~~~bash
kafka-consumer-groups.sh \
  --bootstrap-server kafka-1:9092 \
  --group order-processor \
  --topic orders \
  --reset-offsets \
  --to-earliest \
  --dry-run
~~~

Thực thi sau khi đã duyệt kết quả:

~~~bash
kafka-consumer-groups.sh \
  --bootstrap-server kafka-1:9092 \
  --group order-processor \
  --topic orders \
  --reset-offsets \
  --to-earliest \
  --execute
~~~

Mô phỏng reset partition cụ thể về offset đã xác định:

~~~bash
kafka-consumer-groups.sh \
  --bootstrap-server kafka-1:9092 \
  --group order-processor \
  --topic orders:1 \
  --reset-offsets \
  --to-offset 500 \
  --dry-run
~~~

Xác minh offset sau thay đổi:

~~~bash
kafka-consumer-groups.sh \
  --bootstrap-server kafka-1:9092 \
  --describe \
  --group order-processor
~~~

Kết quả CLI cần được lưu cùng change record. Không chỉ lưu câu lệnh đã chạy; lưu cả kết quả dry-run, kết quả execute và offset sau reset.

## 18. Lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Reset bị từ chối | Group vẫn có consumer active | Dừng tất cả member và xác minh group inactive |
| Offset không thay đổi | Chỉ chạy dry-run hoặc sai group/topic | Kiểm tra kết quả và dùng execute sau phê duyệt |
| Nhiều partition bị reset ngoài dự kiến | Dùng phạm vi topic/group quá rộng | Chỉ định topic và partition cần thiết |
| Consumer đọc lại dữ liệu cũ | Reset lùi hoặc chọn earliest | Kiểm tra idempotency và side effect |
| Consumer bỏ qua dữ liệu | Reset tiến hoặc latest | Đối soát khoảng offset bị bỏ qua |
| Offset mới nằm ngoài log | Chọn offset trước log start hoặc sau log end | Kiểm tra log start/end và chạy dry-run |
| Consumer lag tăng mạnh sau reset | Replay lượng lớn record | Giới hạn tốc độ, scale theo năng lực downstream |
| Consumer tự chạy lại khi đang reset | Autoscaler hoặc deployment controller | Tạm dừng controller và xác minh không còn member |
| Rollback offset nhưng dữ liệu vẫn trùng | Side effect đã xảy ra trong lần replay | Dùng inbox/idempotency và đối soát nghiệp vụ |
| Kafka Streams state sai sau reset | Chỉ reset input offset, giữ state store cũ | Dùng quy trình reset application/state riêng |

## 19. Bài thực hành: phục hồi group order-processor

Giả sử consumer `order-processor` phát hiện logic xử lý sai từ một mốc offset đã xác định. Hãy lập kế hoạch replay:

1. Xác định Kafka cluster, topic `orders` và group `order-processor`.
2. Kiểm tra trạng thái group, member, committed offset, log start/end offset và lag.
3. Dừng mọi instance dùng group và tạm dừng autoscaler.
4. Lưu snapshot committed offsets của các partition.
5. Xác định partition và mốc offset đầu tiên cần đọc lại.
6. Chạy reset `--dry-run` cho đúng partition.
7. Tính số record sẽ đọc lại và đánh giá side effect.
8. Xác nhận consumer có inbox/idempotency key theo event ID.
9. Thực thi reset sau khi kết quả dry-run đã được duyệt.
10. Xác minh committed offset mới bằng `--describe`.
11. Khởi động một instance và quan sát record đầu tiên được đọc.
12. Theo dõi lag, throughput, duplicate suppression, DLQ và trạng thái nghiệp vụ.
13. Nếu offset sai, dừng consumer và khôi phục từ snapshot bằng dry-run rồi execute.
14. Ghi lại kết quả replay và đóng change record.

Bảng nghiệm thu:

| Hạng mục | Kết quả cần xác nhận |
|---|---|
| Group scope | Đúng group ID và tất cả member đã dừng |
| Topic/partition | Chỉ đúng phạm vi cần phục hồi |
| Snapshot | Offset trước reset được lưu và kiểm tra |
| Dry-run | Offset dự kiến được xem xét cho từng partition |
| Execute | Chỉ chạy sau khi phạm vi được duyệt |
| Offset verification | Committed offset sau reset đúng mục tiêu |
| Idempotency | Replay không lặp side effect ngoài dự kiến |
| Backlog | Lag và tốc độ xử lý nằm trong ngưỡng |
| Rollback | Có thể khôi phục offset từ snapshot |
| Kafka Streams | State store/changelog được xử lý theo quy trình riêng |

## Kết luận

Reset offset là thao tác thay đổi tiến độ của một consumer group trên các partition được chọn. Reset lùi phục hồi bằng cách đọc lại record nhưng có thể lặp tác dụng phụ; reset tiến bỏ qua record trong khoảng bị dịch chuyển. Nó không sửa dữ liệu trong topic và không thay đổi tiến độ của group khác.

Với Spring Cloud Stream, xác định đúng group từ input binding, dừng toàn bộ instance cùng group, snapshot offset, chạy dry-run và chỉ execute sau khi đánh giá phạm vi từng partition. Theo dõi offset/lag sau khi khởi động lại, bảo vệ nghiệp vụ bằng idempotency và chuẩn bị rollback. Nếu ứng dụng dùng Kafka Streams, reset input offset phải đi cùng kế hoạch khôi phục state store và changelog.

## Tài liệu tham khảo

- [Apache Kafka – Consumer Group CLI](https://kafka.apache.org/documentation/#basic_ops_consumer_group)
- [Apache Kafka – Consumer Configs](https://kafka.apache.org/documentation/#consumerconfigs)
- [Spring Cloud Stream – Kafka Binder](https://docs.spring.io/spring-cloud-stream/reference/kafka/kafka-binder/index.html)
- [Kafka Streams – Application Reset Tool](https://kafka.apache.org/documentation/streams/developer-guide/app-reset-tool.html)

