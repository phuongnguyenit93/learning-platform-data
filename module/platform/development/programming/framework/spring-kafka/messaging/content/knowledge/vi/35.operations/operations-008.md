# Replay record từ offset cũ

## 1. Replay record là gì?

Kafka lưu record theo thứ tự trong từng partition. Consumer group duy trì committed offset cho từng cặp topic-partition. Khi cần xử lý lại dữ liệu cũ, có thể đưa vị trí đọc của consumer group về một offset trước đó rồi khởi động consumer để đọc lại record từ vị trí mới.

Thao tác này thường được gọi là replay hoặc rewind offset. Nó thay đổi vị trí đọc của consumer group, không xóa record khỏi Kafka và cũng không tự hoàn tác side effect mà lần xử lý trước đã tạo ra.

Ví dụ, consumer group `orders-projection` đã đọc topic `orders` đến offset 900. Sau khi phát hiện một lỗi logic đã ảnh hưởng đến dữ liệu từ offset 850, nhóm vận hành có thể dừng toàn bộ consumer của group, reset partition tương ứng về offset 850 rồi khởi động lại ứng dụng.

~~~mermaid
flowchart LR
    A["Topic orders, partition 0"] --> B["Offsets 840 ... 849"]
    B --> C["Offset 850: bắt đầu replay"]
    C --> D["Offsets 850 ... 899 được đọc lại"]
    D --> E["Offset 900: vị trí cũ"]
    F["Consumer group orders-projection"] --> G["Committed offset được reset về 850"]
    G --> C
~~~

Replay là thao tác vận hành có ảnh hưởng trực tiếp đến dữ liệu đầu ra. Trước khi thực hiện, cần xác định chính xác group, topic, partition, offset bắt đầu, phạm vi dữ liệu và cách ứng dụng xử lý record trùng.

## 2. Hiểu đúng ý nghĩa của offset

Offset là vị trí của record trong một partition, bắt đầu từ 0 và tăng theo log. Offset không phải số thứ tự toàn cục của topic; mỗi partition có dãy offset riêng.

Một committed offset của consumer group biểu thị vị trí đọc kế tiếp mà consumer sẽ tiếp tục sử dụng. Ví dụ:

| Committed offset | Ý nghĩa |
|---:|---|
| 100 | Consumer sẽ đọc từ vị trí 100 trở đi |
| 250 | Các vị trí trước 250 đã được xác nhận theo chính sách commit; lần đọc tiếp theo bắt đầu từ 250 |
| 900 | Consumer sẽ tiếp tục từ 900 |

Nếu reset committed offset về 850, consumer sẽ bắt đầu đọc từ vị trí 850 nếu record đó còn khả dụng. Không reset về 849 chỉ vì muốn đọc record có offset 850; giá trị offset đã là vị trí bắt đầu đọc.

Offset có thể có khoảng trống. Log compaction có thể loại bỏ record cũ nhưng giữ lại offset của record còn tồn tại; transaction bị abort cũng có thể tạo khoảng offset mà consumer dùng isolation level `read_committed` không trả về. Vì vậy, không giả định mọi số nguyên offset đều tương ứng với một record có thể đọc.

## 3. Khi nào cần replay?

Một số tình huống vận hành thường cần replay:

- Lỗi ứng dụng khiến một nhóm record được xử lý sai.
- Projection hoặc read model cần được tính toán lại sau khi sửa logic.
- Dữ liệu đầu vào được bổ sung hoặc sửa đổi và cần chạy lại quy trình downstream.
- Consumer đã commit offset quá sớm do cấu hình hoặc lỗi xử lý.
- Cần tái tạo dữ liệu trong môi trường kiểm thử hoặc môi trường phục hồi.
- Một nhóm consumer mới cần đọc lại lịch sử đang còn trong retention.

Không nên replay chỉ để thử một thay đổi nhỏ trên consumer production. Với thử nghiệm logic, tạo consumer group riêng và dùng database/schema đích riêng sẽ giảm ảnh hưởng tới luồng đang chạy.

## 4. Phân biệt replay cùng group và replay bằng group mới

Có hai chiến lược phổ biến:

| Chiến lược | Cách làm | Ảnh hưởng |
|---|---|---|
| Reset offset của group hiện tại | Đưa committed offset của group đang dùng về vị trí cũ | Consumer hiện tại đọc lại record; side effect có thể lặp |
| Tạo group mới | Dùng group ID mới và chọn vị trí bắt đầu đọc | Group cũ không đổi; có thể chạy song song để kiểm tra hoặc rebuild |

Dùng group hiện tại khi cần khôi phục chính luồng xử lý đang vận hành và đã có kế hoạch xử lý record trùng.

Dùng group mới khi cần:

- So sánh kết quả của phiên bản consumer mới với phiên bản hiện tại.
- Rebuild projection vào bảng hoặc database riêng.
- Chạy kiểm thử lịch sử mà không thay đổi offset production.
- Tạo một subscriber độc lập cần nhận toàn bộ dữ liệu còn lưu.

Nếu group mới không có committed offset, consumer sẽ dùng `auto.offset.reset`. Với `earliest`, consumer bắt đầu từ đầu log còn giữ; với `latest`, consumer bắt đầu ở cuối log tại thời điểm xác định offset ban đầu. Đừng mặc định group mới luôn đọc từ đầu.

## 5. Các điều kiện cần có trước khi reset offset

Kafka yêu cầu consumer group không còn member hoạt động khi reset offset bằng công cụ quản trị thông thường. Cần dừng tất cả instance đang dùng cùng group ID.

Trước khi thực hiện:

1. Xác định chính xác `group.id` của ứng dụng.
2. Liệt kê các topic và partition mà group đang đọc.
3. Ghi lại committed offset hiện tại để có thể khôi phục vị trí.
4. Kiểm tra log start offset và log end offset của từng partition.
5. Xác định offset đích và lý do chọn offset đó.
6. Dừng toàn bộ instance consumer thuộc group.
7. Xác minh group không còn member hoạt động.
8. Chạy dry-run và review kết quả trước khi execute.

Chỉ pause listener container thường chưa đủ. Consumer vẫn có thể còn là member của group. Hãy stop container hoặc dừng toàn bộ ứng dụng/replica, sau đó kiểm tra group state và member list.

Nếu một deployment khác vô tình dùng cùng group ID, nó cũng phải được dừng. Reset khi consumer vẫn hoạt động có thể thất bại hoặc bị consumer commit lại offset cũ sau khi reset.

## 6. Kiểm tra consumer group trước khi replay

Dùng Kafka consumer groups CLI để xem trạng thái group:

~~~bash
kafka-consumer-groups.sh \
  --bootstrap-server broker.example.com:9092 \
  --command-config client.properties \
  --describe \
  --group orders-projection
~~~

Kết quả thường hiển thị topic, partition, current offset, log end offset và lag. Các cột này giúp xác định vị trí hiện tại và lượng record còn chờ.

Để kiểm tra log start offset và log end offset trực tiếp, các bản Kafka có script `kafka-get-offsets.sh` có thể dùng:

~~~bash
kafka-get-offsets.sh \
  --bootstrap-server broker.example.com:9092 \
  --command-config client.properties \
  --topic orders \
  --time -2

kafka-get-offsets.sh \
  --bootstrap-server broker.example.com:9092 \
  --command-config client.properties \
  --topic orders \
  --time -1
~~~

`--time -2` yêu cầu earliest offset còn trong log; `--time -1` yêu cầu latest offset. Script có thể khác tên hoặc chưa được đóng gói ở một số phiên bản Kafka; khi đó dùng công cụ offset tương ứng của bản phân phối đang chạy.

Xem member và assignment:

~~~bash
kafka-consumer-groups.sh \
  --bootstrap-server broker.example.com:9092 \
  --command-config client.properties \
  --group orders-projection \
  --describe \
  --members \
  --verbose
~~~

Xem trạng thái group nếu phiên bản CLI hỗ trợ:

~~~bash
kafka-consumer-groups.sh \
  --bootstrap-server broker.example.com:9092 \
  --command-config client.properties \
  --group orders-projection \
  --state
~~~

Trước khi reset, xác minh group không còn member hoạt động và trạng thái cho phép thực hiện thao tác. Tên cột và trạng thái cụ thể có thể khác theo phiên bản Kafka. Nếu group còn member, tìm đúng deployment/pod đang chạy rồi dừng nó theo quy trình vận hành.

Không chỉ dựa vào một lệnh describe chạy trước đó. Hãy kiểm tra lại ngay trước reset để tránh một instance tự khởi động lại giữa quy trình.

## 7. Sao lưu committed offset hiện tại

Trước khi thay đổi offset, lưu lại vị trí hiện tại của group. Kafka consumer groups CLI có tùy chọn export offset trong chế độ reset:

~~~bash
kafka-consumer-groups.sh \
  --bootstrap-server broker.example.com:9092 \
  --command-config client.properties \
  --group orders-projection \
  --reset-offsets \
  --all-topics \
  --export > orders-projection-offsets-before.csv
~~~

File export là dữ liệu vận hành quan trọng. Lưu nó ở nơi có quyền truy cập hạn chế, gắn với change ticket hoặc mã lần replay và giữ theo chính sách audit.

Có thể chỉ export topic cần replay thay vì toàn bộ topic của group, nhưng phải bảo đảm bản sao lưu đủ phạm vi cần khôi phục. Kiểm tra file export có các partition và offset mong đợi trước khi tiếp tục.

Không sửa tay file export để ước lượng offset cũ. Nếu cần khôi phục, dùng file gốc đã lưu và kiểm tra dry-run trước khi execute.

## 8. Xác định offset đích

Offset đích phải được chọn theo bằng chứng: offset record gây lỗi, offset bắt đầu của một phiên bản logic sai hoặc thời điểm dữ liệu cần xử lý lại.

Một số cách chọn vị trí:

| Tùy chọn | Ý nghĩa |
|---|---|
| `--to-offset N` | Đặt vị trí đọc về offset N |
| `--to-earliest` | Đưa về log start offset còn giữ |
| `--to-latest` | Đưa về log end offset, bỏ qua backlog hiện tại |
| `--to-datetime` | Chọn vị trí dựa trên timestamp của record |
| `--by-duration PT2H` | Lùi theo khoảng thời gian so với thời điểm hiện tại |
| `--shift-by -N` | Dịch vị trí hiện tại lùi N offset |
| `--from-file file.csv` | Đặt offset theo file export đã chuẩn bị |

`--to-earliest` không khôi phục record đã bị retention xóa hoặc compaction loại bỏ. Nó chỉ đưa consumer về vị trí sớm nhất hiện còn trong log.

`--to-latest` không phải cách replay dữ liệu cũ; nó đưa consumer đến cuối log và có thể bỏ qua các record đang chờ.

`--to-datetime` dựa trên timestamp của Kafka record. Kết quả phụ thuộc timestamp type và timestamp thực tế được lưu trong log. Nếu producer dùng `CreateTime`, timestamp do producer cung cấp có thể lệch đồng hồ; nếu topic dùng `LogAppendTime`, broker gán timestamp khi append. Kiểm tra timezone và timestamp type trước khi dùng.

`--shift-by -N` tương đối với vị trí hiện tại. Cách này thuận tiện khi muốn lùi một khoảng cố định, nhưng dễ sai nếu offset đã thay đổi hoặc partition có log start khác nhau. Với replay có phạm vi rõ ràng, offset tuyệt đối thường dễ review hơn.

## 9. Replay một partition từ offset cụ thể

Giả sử chỉ partition 0 của topic `orders` cần được xử lý lại từ offset 850. Trước tiên chạy dry-run:

~~~bash
kafka-consumer-groups.sh \
  --bootstrap-server broker.example.com:9092 \
  --command-config client.properties \
  --group orders-projection \
  --topic orders:0 \
  --reset-offsets \
  --to-offset 850 \
  --dry-run
~~~

Dry-run hiển thị các offset dự kiến thay đổi mà chưa ghi thay đổi vào group. Kiểm tra:

- Đúng group ID.
- Đúng topic và partition.
- Offset hiện tại khớp với bản sao lưu.
- Offset đích đúng bằng vị trí bắt đầu mong muốn.
- Offset đích nằm trong phạm vi log còn khả dụng.
- Không có partition ngoài phạm vi bị thay đổi.

Khi kết quả đã được review và consumer group đã dừng hoàn toàn, thực hiện:

~~~bash
kafka-consumer-groups.sh \
  --bootstrap-server broker.example.com:9092 \
  --command-config client.properties \
  --group orders-projection \
  --topic orders:0 \
  --reset-offsets \
  --to-offset 850 \
  --execute
~~~

Sau khi execute, chạy lại describe để xác minh committed offset mới. Chỉ khởi động consumer sau khi vị trí mới đã được xác nhận.

## 10. Replay nhiều partition hoặc cả topic

Nếu cần replay mọi partition của một topic từ log start offset:

~~~bash
kafka-consumer-groups.sh \
  --bootstrap-server broker.example.com:9092 \
  --command-config client.properties \
  --group orders-projection \
  --topic orders \
  --reset-offsets \
  --to-earliest \
  --dry-run
~~~

Sau khi review, chạy lại với `--execute`.

Nếu mỗi partition cần offset khác nhau, có thể reset theo từng partition hoặc dùng file offset được chuẩn bị chính xác. Không giả định cùng một offset đích phù hợp với tất cả partition vì tốc độ ghi, retention và phạm vi dữ liệu của chúng có thể khác nhau.

Nếu cần replay toàn bộ topic mà group đang subscribe, có thể dùng `--all-topics`. Đây là phạm vi rộng và dễ làm xử lý lặp ngoài dự kiến; chỉ sử dụng khi đã xác minh toàn bộ topic trong group cần được replay.

## 11. Replay theo thời gian

Khi chỉ biết thời điểm sự cố, có thể chọn vị trí dựa trên timestamp:

~~~bash
kafka-consumer-groups.sh \
  --bootstrap-server broker.example.com:9092 \
  --command-config client.properties \
  --group orders-projection \
  --topic orders \
  --reset-offsets \
  --to-datetime 2026-11-16T08:30:00.000 \
  --dry-run
~~~

Thời gian ví dụ cần được thay bằng thời điểm đã chuẩn hóa, tốt nhất là UTC. Công cụ tìm offset tương ứng với timestamp của record trong từng partition; partition không có record tại hoặc sau mốc thời gian có thể được đặt ở vị trí cuối log theo hành vi công cụ.

Với khoảng thời gian tương đối, có thể dùng:

~~~bash
kafka-consumer-groups.sh \
  --bootstrap-server broker.example.com:9092 \
  --command-config client.properties \
  --group orders-projection \
  --topic orders \
  --reset-offsets \
  --by-duration PT2H \
  --dry-run
~~~

`PT2H` biểu thị hai giờ theo ISO-8601 duration. Kiểm tra kết quả dry-run của từng partition; đừng coi timestamp là offset chính xác tuyệt đối. Nếu sự cố bắt đầu giữa một loạt record có timestamp gần nhau, có thể cần đọc metadata và xác định offset cụ thể trước khi reset.

## 12. Dịch offset tương đối

Nếu committed offset hiện tại của partition là 900 và cần replay khoảng 50 offset gần nhất, có thể thử `--shift-by -50`:

~~~bash
kafka-consumer-groups.sh \
  --bootstrap-server broker.example.com:9092 \
  --command-config client.properties \
  --group orders-projection \
  --topic orders:0 \
  --reset-offsets \
  --shift-by -50 \
  --dry-run
~~~

Kết quả dự kiến là vị trí đọc lùi 50 offset so với committed offset hiện tại. Dry-run phải được kiểm tra để bảo đảm offset mới không nằm ngoài log start/end và đúng phạm vi cần xử lý.

Nếu offset hiện tại đã thay đổi, cùng một lệnh shift-by sẽ tạo ra kết quả khác. Không lưu lệnh tương đối làm runbook cố định mà không ghi rõ trạng thái group trước khi chạy.

## 13. Khôi phục offset từ bản sao lưu

Nếu replay gây ra vấn đề và cần đưa group về vị trí trước đó, dùng file export đã lưu:

~~~bash
kafka-consumer-groups.sh \
  --bootstrap-server broker.example.com:9092 \
  --command-config client.properties \
  --group orders-projection \
  --reset-offsets \
  --from-file orders-projection-offsets-before.csv \
  --dry-run
~~~

Review toàn bộ partition trong kết quả. Sau khi xác minh, execute:

~~~bash
kafka-consumer-groups.sh \
  --bootstrap-server broker.example.com:9092 \
  --command-config client.properties \
  --group orders-projection \
  --reset-offsets \
  --from-file orders-projection-offsets-before.csv \
  --execute
~~~

Khôi phục offset chỉ thay đổi vị trí đọc tiếp theo. Nó không xóa các side effect đã xảy ra trong lúc replay. Nếu consumer đã ghi thêm dữ liệu vào database hoặc gọi API bên ngoài, cần quy trình bù trừ hoặc rebuild dữ liệu đầu ra tương ứng.

## 14. Quy trình replay an toàn trong production

Một quy trình có thể dùng làm runbook:

~~~mermaid
flowchart TD
    A["Xác định sự cố và phạm vi"] --> B["Chọn group/topic/partition/offset"]
    B --> C["Sao lưu committed offsets"]
    C --> D["Dừng tất cả consumer của group"]
    D --> E["Xác minh group không còn member"]
    E --> F["Chạy reset --dry-run"]
    F --> G{"Kết quả đúng?"}
    G -->|Không| H["Hủy và điều tra"]
    G -->|Có| I["Review thay đổi"]
    I --> J["Chạy reset --execute"]
    J --> K["Describe xác minh offset mới"]
    K --> L["Khởi động consumer"]
    L --> M["Theo dõi lag, throughput và output"]
    M --> N["Đối soát kết quả replay"]
~~~

Các bước vận hành chi tiết:

1. Mở change record, ghi lý do replay và người chịu trách nhiệm.
2. Xác định record hoặc thời điểm bắt đầu bị ảnh hưởng.
3. Kiểm tra retention, compaction và log start offset.
4. Export offset hiện tại.
5. Dừng mọi instance thuộc consumer group.
6. Xác nhận không còn member hoạt động.
7. Chạy reset dry-run và lưu output.
8. Review topic, partition và offset mới.
9. Execute reset.
10. Describe group để xác nhận committed offset.
11. Khởi động consumer theo từng bước nếu cần giới hạn tải.
12. Theo dõi lag, tốc độ xử lý, lỗi, duplicate và dữ liệu đầu ra.
13. Đối soát kết quả rồi đóng change record.

Nếu replay phạm vi lớn, có thể chia thành từng partition hoặc từng cửa sổ dữ liệu để giảm tải và dễ kiểm soát.

## 15. Ngăn side effect bị nhân đôi

Replay khiến record cũ được xử lý lại. Kafka không tự biết nghiệp vụ đã thực hiện side effect đó trước đây hay chưa.

Ví dụ listener:

~~~java
@KafkaListener(
    topics = "orders",
    groupId = "orders-projection"
)
public void handle(OrderCreatedEvent event) {
    orderProjectionRepository.apply(event);
}
~~~

Nếu `apply()` cộng tiền vào tổng doanh thu mỗi lần được gọi, replay có thể cộng lần thứ hai. Thiết kế idempotent bằng event ID hoặc business key:

~~~java
@Transactional
public void apply(OrderCreatedEvent event) {
    boolean firstDelivery = processedEventRepository
        .insertIfAbsent(event.eventId());

    if (!firstDelivery) {
        return;
    }

    orderProjectionRepository.upsert(
        event.orderId(),
        event.status()
    );
}
~~~

Ví dụ trên cần bảo đảm insert event ID và cập nhật projection nằm trong cùng database transaction. Tạo unique constraint trên event ID để hai consumer đồng thời cũng không xử lý cùng event hai lần.

Các chiến lược khác:

- Upsert trạng thái thay vì cộng dồn một cách mù quáng.
- Lưu bảng processed event với unique key.
- Dùng idempotency key khi gọi API bên ngoài.
- Dùng transactional outbox cho side effect phát tiếp sự kiện.
- Có quy trình bù trừ khi side effect không thể idempotent.

Kafka transaction có thể phối hợp output Kafka và offset trong phạm vi Kafka. Nó không tự rollback database, email, thanh toán hoặc HTTP request khi record được replay.

## 16. Replay để rebuild projection

Nếu mục tiêu là tính lại toàn bộ read model sau khi sửa code, reset group production hiện tại có thể không phải lựa chọn tốt. Một chiến lược ít rủi ro hơn là rebuild vào projection mới:

1. Tạo bảng hoặc database đích mới.
2. Tạo consumer group mới, ví dụ `orders-projection-v2-rebuild`.
3. Chọn offset bắt đầu và cấu hình `auto.offset.reset` phù hợp.
4. Chạy consumer mới để đọc lịch sử còn giữ.
5. Kiểm tra số record, trạng thái và invariant nghiệp vụ.
6. Đối soát dữ liệu giữa projection cũ và mới.
7. Chuyển read traffic sang projection mới khi đạt điều kiện.
8. Giữ projection cũ trong thời gian rollback đã định.

Cách này cho phép so sánh hai kết quả và rollback traffic mà không phải reset group đang phục vụ production. Cần xử lý dữ liệu mới phát sinh trong lúc rebuild, chẳng hạn replay đến một high-water mark rồi bắt kịp phần đuôi trước khi cutover.

## 17. Giới hạn do retention, compaction và transaction

Replay chỉ có thể đọc dữ liệu còn trong Kafka log.

**Retention:** record cũ hơn thời hạn hoặc dung lượng retention có thể đã bị xóa. `--to-earliest` chỉ đưa consumer đến log start offset hiện tại, không phục hồi dữ liệu đã mất.

**Log compaction:** Kafka có thể giữ bản ghi mới nhất theo key và loại bỏ bản ghi cũ. Nếu cần dựng lại mọi trạng thái lịch sử, topic compacted có thể không còn toàn bộ event. Tombstone cũng có thể bị xóa sau thời gian cấu hình.

**Transactional records:** consumer dùng `isolation.level=read_committed` chỉ thấy record thuộc transaction đã commit. Record thuộc transaction bị abort không được trả về như dữ liệu hợp lệ, và open transaction có thể làm giới hạn đọc dừng ở last stable offset.

**Timestamp:** `CreateTime` phụ thuộc đồng hồ producer; `LogAppendTime` do broker gán. Replay theo thời gian phải hiểu timestamp type của topic.

Trước khi replay lịch sử dài, xác minh retention, compaction, log start/end offset, timestamp và isolation level. Nếu dữ liệu không còn trong Kafka, cần nguồn archive hoặc bản sao lưu phù hợp.

## 18. Replay từ trong ứng dụng Spring Kafka

Với vận hành một lần, reset consumer group bằng Kafka CLI thường dễ review và audit. Trong một số luồng ứng dụng, có thể cần seek consumer tới offset cụ thể.

Spring Kafka hỗ trợ `ConsumerSeekAware` để listener nhận callback khi partition được assign và thực hiện seek. Ví dụ minh họa:

~~~java
import java.util.Map;

import org.apache.kafka.common.TopicPartition;
import org.springframework.kafka.listener.ConsumerSeekAware;
import org.springframework.kafka.annotation.KafkaListener;

public class ReplayAwareListener implements ConsumerSeekAware {

    @Override
    public void onPartitionsAssigned(
            Map<TopicPartition, Long> assignments,
            ConsumerSeekCallback callback) {

        assignments.forEach((partition, position) -> {
            if (partition.topic().equals("orders")
                    && partition.partition() == 0) {
                callback.seek("orders", 0, 850L);
            }
        });
    }

    @KafkaListener(
        topics = "orders",
        groupId = "orders-projection-replay"
    )
    public void handle(String payload) {
        process(payload);
    }

    private void process(String payload) {
        // Xử lý nghiệp vụ.
    }
}
~~~

Đây là ví dụ minh họa ý tưởng seek khi partition được assign. Trong ứng dụng thật, listener container cần quản lý callback đúng lifecycle; offset seek phải được giới hạn theo partition, điều kiện replay và trạng thái của consumer. Không hard-code offset trong listener production vì mỗi lần rebalance có thể gọi lại callback.

Seek thay đổi vị trí đọc hiện tại của consumer. Nếu muốn vị trí đó tồn tại sau restart, cần commit offset theo chính sách phù hợp. Khi nhiều instance cùng group, chỉ consumer đang sở hữu partition mới có thể seek partition đó.

Không gọi `Consumer.seek()` tùy tiện từ thread nghiệp vụ bên ngoài consumer thread. Hãy dùng API seek của Spring Kafka như `ConsumerSeekCallback`, `ConsumerSeekAware` hoặc cơ chế container được hỗ trợ.

## 19. Kiểm thử replay trước production

Có thể kiểm thử quy trình trên topic test và consumer group riêng:

1. Tạo topic có một vài partition.
2. Gửi record có key và event ID xác định.
3. Chạy consumer group test để xử lý và commit offset.
4. Dừng consumer group.
5. Export committed offset.
6. Dry-run reset về offset cũ.
7. Execute reset.
8. Khởi động lại consumer.
9. Xác minh record được giao lại.
10. Xác minh idempotency ngăn side effect bị lặp.
11. Thử khôi phục offset từ file export.

Test cũng nên bao gồm các trường hợp:

- Offset đích nhỏ hơn log start offset.
- Offset đích lớn hơn log end offset.
- Partition không có record tại timestamp đã chọn.
- Group còn member đang hoạt động.
- Topic bị compact và không còn record lịch sử.
- Consumer dùng `read_committed` khi topic có transaction.
- Replay nhiều partition với offset khác nhau.
- Ứng dụng restart trong lúc replay.

Dùng Embedded Kafka hoặc Testcontainers cho kiểm thử integration. Với ACL, TLS và SASL, broker test phải được bật đúng cơ chế bảo mật; broker mặc định không chứng minh được quyền reset offset trên production.

## 20. Theo dõi trong và sau replay

Trong thời gian replay, theo dõi:

| Chỉ số | Ý nghĩa |
|---|---|
| Current/committed offset | Vị trí consumer group đã xác nhận |
| Log end offset | Vị trí cuối log của partition |
| Consumer lag | Số offset còn phải bắt kịp theo cách tính của Kafka |
| Records consumed rate | Tốc độ đọc record |
| Processing latency | Thời gian xử lý mỗi record |
| Error/retry/DLT rate | Lỗi phát sinh khi replay |
| Duplicate/idempotency count | Số record bị nhận diện đã xử lý |
| Database/API load | Tác động của replay tới dependency |

Lag có thể tăng hoặc giảm tùy tốc độ producer tiếp tục ghi và tốc độ replay. Replay một partition có thể tạo tải tập trung lên một consumer; replay nhiều partition cùng lúc có thể gây tải lớn lên database hoặc API downstream.

Nếu dependency bắt đầu quá tải, dừng hoặc giảm concurrency theo runbook. Không tự tăng concurrency vượt số partition hữu ích hoặc khả năng chịu tải của downstream.

## 21. Bảo mật và quyền quản trị

Reset offset là thao tác quản trị consumer group. Dùng principal vận hành có quyền tối thiểu cần thiết cho group và topic liên quan.

- Không dùng superuser cho tác vụ replay thông thường.
- Dùng `--command-config` để truyền TLS/SASL config từ file được bảo vệ.
- Không ghi password hoặc JAAS string trực tiếp vào command history.
- Lưu file export và dry-run output trong nơi có quyền truy cập phù hợp.
- Ghi audit: group, topic, partition, offset cũ, offset mới, thời gian và người thực hiện.
- Chỉ dừng đúng consumer group cần replay; không ảnh hưởng group khác trên cùng topic.

Trong môi trường Windows, Kafka distribution thường cung cấp script `kafka-consumer-groups.bat` tương ứng. Cú pháp option giống nhau; thay tên script và cách redirect file theo shell đang dùng.

## 22. Lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
|---|---|---|
| Reset bị từ chối vì group đang active | Còn consumer member | Dừng tất cả instance và xác minh group state |
| Replay không thấy record cũ | Offset đích thấp hơn log start hoặc record đã bị retention xóa | Kiểm tra log start offset và archive |
| Consumer đọc lại quá nhiều dữ liệu | Dùng `--to-earliest` hoặc group mới không đúng phạm vi | Chọn offset cụ thể và kiểm tra dry-run |
| Consumer bỏ qua backlog | Dùng `--to-latest` ngoài ý muốn | Reset về offset mong muốn trước khi start |
| Reset xong offset lại nhảy | Consumer cũ vẫn chạy hoặc ứng dụng commit ngay sau restart | Dừng toàn bộ member, kiểm tra lại group trước/sau reset |
| Kết quả replay khác dự kiến | Timestamp type, timezone hoặc compaction | Kiểm tra timestamp và retention/cleanup policy |
| Database có dữ liệu trùng | Side effect không idempotent | Dùng event ID, unique constraint hoặc upsert |
| Replay làm downstream quá tải | Tốc độ đọc vượt năng lực dependency | Giới hạn concurrency/rate và chia phạm vi replay |
| Không khôi phục được trạng thái cũ | Không export offset trước khi reset | Luôn sao lưu committed offset trước thay đổi |

## 23. Checklist replay record từ offset cũ

- [ ] Xác định consumer group chính xác.
- [ ] Xác định topic, partition và offset bắt đầu.
- [ ] Kiểm tra log start/end offset và retention.
- [ ] Kiểm tra compaction, timestamp type và isolation level.
- [ ] Export committed offset hiện tại.
- [ ] Dừng tất cả consumer thuộc group.
- [ ] Xác minh group không còn member hoạt động.
- [ ] Chạy `--reset-offsets --dry-run`.
- [ ] Review từng partition và offset dự kiến.
- [ ] Chỉ dùng `--execute` sau khi kết quả được xác nhận.
- [ ] Describe lại group để xác minh offset mới.
- [ ] Khởi động consumer và theo dõi lag, lỗi, throughput.
- [ ] Bảo vệ side effect bằng idempotency/deduplication.
- [ ] Đối soát dữ liệu đầu ra sau replay.
- [ ] Lưu audit và file offset backup.
- [ ] Có kế hoạch khôi phục offset và bù trừ side effect nếu cần.

Replay record từ offset cũ là cách hữu ích để sửa sai hoặc tái tạo projection, nhưng nó thay đổi vị trí đọc của consumer group và khiến nghiệp vụ được thực hiện lại. Hãy dừng group, sao lưu offset, kiểm tra phạm vi log, chạy dry-run, execute có kiểm soát rồi đối soát đầu ra. Khi consumer idempotent và dependency được bảo vệ khỏi tải đột biến, việc replay trong Spring Kafka sẽ dễ dự đoán và an toàn hơn.
