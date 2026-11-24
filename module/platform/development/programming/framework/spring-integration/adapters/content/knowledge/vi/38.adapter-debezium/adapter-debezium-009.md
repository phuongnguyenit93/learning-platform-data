# Đảm bảo thứ tự theo partition trong Debezium và Spring Integration

## 1. Bài toán: nhận đủ sự kiện nhưng áp dụng sai thứ tự

Trong module **SPRING_INTEGRATION_ADAPTERS**, các hệ thống bên ngoài được kết nối bằng inbound/outbound adapter, gateway, poller và `MessageChannel`. Một luồng phổ biến dùng **Debezium** đọc thay đổi từ transaction log của database nguồn, phát CDC event vào Kafka, rồi **Spring Integration Kafka inbound adapter** chuyển message cho transformer, router và service activator cập nhật hệ thống đích.

Giả sử đơn hàng `orders.id = 42` thay đổi theo thứ tự:

~~~text
T1: status = NEW
T2: status = PAID
T3: status = SHIPPED
~~~

Database đã commit theo trình tự `T1 → T2 → T3`. Nếu chương trình nhận đủ ba sự kiện nhưng xử lý song song và ghi `SHIPPED` trước `PAID`, projection cuối cùng có thể **lùi từ SHIPPED về PAID**. Hệ thống lúc đó không bị mất record, nhưng **kết quả vẫn sai**.

**Thứ tự theo partition** là một bảo đảm quan trọng của Kafka: các record nằm trong **cùng một topic-partition** có thứ tự xác định bởi offset trong log partition. Tuy vậy, bảo đảm đó chỉ giúp được một phần. Để hệ thống đích xử lý đúng, cần hiểu toàn tuyến **database log → Debezium → Kafka partition → consumer → Spring Integration MessageChannel → transaction của sink**.

Sau bài này, bạn sẽ:

1. Phân biệt thứ tự transaction nguồn, thứ tự record Kafka và thứ tự xử lý thực tế tại sink.
2. Hiểu vai trò của **Kafka record key**, partitioner và offset đối với tính tuần tự của một đối tượng nghiệp vụ.
3. Thiết kế consumer group, listener concurrency và MessageChannel tránh đảo thứ tự ngoài ý muốn.
4. Giải thích tác động của snapshot, đa bảng, đa partition, retry, DLT, replay và thay đổi primary key.
5. Chọn chiến lược xử lý khi cần thứ tự theo khóa, theo partition hoặc thứ tự toàn cục.

## 2. Bảo đảm chính xác của Kafka: một log có thứ tự cho từng partition

Một Kafka **topic** có thể có nhiều **partition**. Trong mỗi partition, broker lưu các record thành một dãy có offset tăng dần:

~~~mermaid
flowchart LR
    D[Debezium source] --> P0[(Topic orders · partition 0<br/>offset 15 → 16 → 17)]
    D --> P1[(Topic orders · partition 1<br/>offset 28 → 29 → 30)]
    D --> P2[(Topic orders · partition 2<br/>offset 7 → 8 → 9)]
    P0 --> C0[Consumer A]
    P1 --> C1[Consumer B]
    P2 --> C2[Consumer B]
~~~

**Kafka có thứ tự bên trong mỗi partition, không có một offset hay thứ tự toàn cục giữa các partition**. Offset `30` của partition 1 không có ý nghĩa là “sau” offset `17` của partition 0 trong thời gian nghiệp vụ.

Ví dụ trong cùng một topic:

| Partition | Offset | Record | Ý nghĩa |
|---:|---:|---|---|
| 1 | 28 | `order=42, status=NEW` | Trạng thái đầu |
| 1 | 29 | `order=42, status=PAID` | Cập nhật tiếp |
| 1 | 30 | `order=42, status=SHIPPED` | Cập nhật mới nhất |
| 0 | 15 | `order=99, status=NEW` | Đơn hàng khác |

Theo log partition 1, có thể chắc chắn thứ tự **28 → 29 → 30**. Không thể kết luận record partition 0 offset 15 xảy ra trước, xen giữa hay sau ba record đó nếu chỉ nhìn offset Kafka.

### Ba loại thứ tự thường bị nhầm

| Loại thứ tự | Ai quản lý? | Bảo đảm thực tế |
|---|---|---|
| **Thứ tự giao dịch/đổi dữ liệu nguồn** | Database và cơ chế CDC | Log nguồn định vị thay đổi; thứ tự trong hoặc giữa transaction phụ thuộc database, connector |
| **Thứ tự record trong Kafka partition** | Kafka broker/producer | Record append vào cùng partition có offset tăng và consumer đọc theo thứ tự log |
| **Thứ tự xử lý/commit ở ứng dụng đích** | Listener container, Spring Integration, worker, database sink | Chỉ đúng nếu thiết kế xử lý, ack và concurrency giữ được quan hệ mong muốn |

Vì vậy, “Kafka đảm bảo ordering” **không có nghĩa** mặc định service activator xử lý xong từng bản ghi theo thứ tự nguồn.

## 3. Record key quyết định khả năng gom thay đổi cùng đối tượng

Debezium thường dùng **primary key của hàng** làm Kafka record key đối với bảng có khóa chính (hành vi cụ thể tùy connector và cấu hình). Ví dụ:

~~~sql
CREATE TABLE sales.orders (
    id BIGINT PRIMARY KEY,
    status VARCHAR(24) NOT NULL,
    updated_at TIMESTAMP NOT NULL
);
~~~

Hai lần cập nhật cùng `id=42` có key logic giống nhau:

~~~text
Event E1:
  key   = {"id":42}
  value = {"op":"u", "after":{"id":42,"status":"PAID"}, ...}

Event E2:
  key   = {"id":42}
  value = {"op":"u", "after":{"id":42,"status":"SHIPPED"}, ...}
~~~

Với **partitioner xác định và không đổi**, các key có cùng bytes sau serialization thường được định tuyến về **cùng partition** của cùng topic. Nếu Debezium gửi E1 rồi E2 theo thứ tự vào partition đó, Kafka lưu E1 trước E2.

Điều kiện phải kiểm tra:

- **Key ổn định:** các sự kiện của cùng đối tượng có cùng giá trị key và cùng cách serialize (bao gồm kiểu dữ liệu và định dạng key).
- **Topic ổn định:** nếu SMT đổi tên topic hoặc router phân tách một khóa sang nhiều topic, thứ tự không còn một trục chung.
- **Partitioner ổn định:** quy tắc chọn partition, số partition của topic và explicit partition (nếu có) không thay đổi giữa các event cần giữ thứ tự.
- **Producer source đúng thứ tự:** luồng CDC và pipeline không chủ động đảo thứ tự khi phát record. Kafka chỉ bảo vệ thứ tự **append thực tế** trong partition.
- **Sink xử lý đúng:** không đưa hai event cùng khóa vào worker độc lập rồi ghi đích theo thời điểm worker hoàn tất.

**Không suy ra thứ tự chỉ từ key:** Kafka key là điều kiện định tuyến phổ biến, nhưng các ứng dụng có thể dùng custom partitioner, key=null, key SMT hoặc gửi partition tường minh.

### Khóa tổng hợp, khóa thiếu và thay đổi khóa

Nếu bảng có primary key (`order_id`, `line_no`), một Kafka key có thể chứa **cả hai** field; định danh nghiệp vụ không nhất thiết là một số nguyên.

Nếu bảng **không có primary key**, một số connector có thể phát null key hoặc dùng lựa chọn khóa khác khi được cấu hình. Khi key=null, không nên mặc định các update thuộc cùng một hàng sẽ được đưa tới cùng partition hoặc có thể dùng compaction/upsert an toàn.

**Đổi primary key** có thể tạo chuỗi logic **delete ở khóa cũ** và **create ở khóa mới** (tùy connector), kèm tombstone. Hai khóa cũ/mới có thể nằm ở **hai partition khác nhau**. Không được mặc định ứng dụng quan sát các record đó theo cùng thứ tự toàn cục; cần quy trình chuyển khóa và xử lý xóa/upsert độc lập, idempotent.

## 4. Phân biệt source log position và Kafka offset

Debezium đọc thay đổi từ nguồn theo cơ chế database:

- MySQL: binary log; metadata có thể gồm `file`, `pos`, `row` và `gtid`.
- PostgreSQL: WAL qua logical decoding; metadata có thể gồm `lsn` và transaction information.
- Database khác có hệ thống vị trí riêng.

Trong Kafka, mỗi record được ghi vào một **topic-partition-offset**. Hai loại vị trí này **không quy đổi trực tiếp**:

~~~text
MySQL source change: mysql-bin.000031 : 47280
    -> Debezium
    -> Kafka topic orders-cdc.sales.orders, partition 2, offset 518
~~~

Source offset cho phép **connector** tiếp tục đọc sau restart; consumer group offset cho phép **Spring Kafka consumer** tiếp tục đọc Kafka. Source offset còn có thể lưu trạng thái snapshot và những dữ liệu bổ sung ngoài một log position.

Một transaction nguồn có thể sinh nhiều CDC record, cho nhiều hàng/bảng. Chúng có thể đi vào **nhiều topic/partition**. Không thể lấy một Kafka offset làm chỉ số thứ tự chung của transaction; cũng không thể đơn giản so sánh `ts_ms` của từng event để tạo “thứ tự tuyệt đối”, vì timestamp có thể trùng nhau, khác nguồn hoặc không phản ánh thời điểm commit mong muốn.

## 5. Từ binlog/WAL tới partition: các giới hạn quan trọng

### 5.1. Thứ tự đọc nguồn không đồng nhất thứ tự mọi topic

Một transaction có thể thay đổi đồng thời:

~~~sql
BEGIN;
UPDATE sales.orders SET status = 'PAID' WHERE id = 42;
INSERT INTO sales.payments (id, order_id, amount)
VALUES (9001, 42, 125000);
COMMIT;
~~~

Debezium có thể phát một row CDC event vào `orders-cdc.sales.orders` và một event khác vào `orders-cdc.sales.payments`. Mỗi topic có offset riêng; ngay cả khi connector quan sát transaction nguồn theo thứ tự nhất định, **hai consumer độc lập không tự cam kết thời điểm xử lý event orders/payments**.

Khi một nghiệp vụ cần áp dụng **nguyên tử** thay đổi liên quan nhiều bảng, có thể:

1. Thiết kế một **transactional outbox** ở database nguồn để phát một sự kiện nghiệp vụ tổng hợp.
2. Sử dụng transaction metadata của Debezium (nếu connector hỗ trợ và đã bật) để nhận diện nhóm/thứ tự sự kiện và tự xây bộ hợp nhất có checkpoint.
3. Thiết kế sink đối soát hoặc chờ đủ điều kiện trước khi công bố trạng thái.

Không giải quyết yêu cầu “commit cùng lúc đa bảng” bằng cách chỉ tăng số partition hay số consumer.

### 5.2. Transaction metadata giúp gì?

Một số Debezium connector có thể bổ sung `transaction` metadata khi bật chức năng tương ứng, ví dụ:

~~~json
{
  "op": "u",
  "after": {"id": 42, "status": "PAID"},
  "transaction": {
    "id": "tx-illustrative",
    "total_order": 3,
    "data_collection_order": 2
  }
}
~~~

Ví dụ **rút gọn** trên không phải payload chuẩn cho mọi connector. Các trường thứ tự trong transaction có thể hỗ trợ phân tích/reconstruct một nhóm sự kiện theo contract cụ thể. Nhưng Kafka/Spring Integration **không tự chờ tất cả partition và tự dựng transaction nguồn** chỉ vì có `transaction.total_order`. Muốn dựa vào metadata này, ứng dụng phải có bộ đệm, biết điểm hoàn tất, trạng thái bền vững và phương án xử lý thiếu event.

### 5.3. Snapshot và streaming có thể đan xen

Initial snapshot thường phát `op="r"` cho hàng hiện có rồi chuyển sang streaming theo ranh giới log phù hợp. Incremental snapshot có thể phát các `r` theo chunk **khi streaming vẫn chạy**. Do đó không nên giả định **mọi `r` luôn nằm trước mọi `u`** trên toàn bộ topic.

Debezium có cơ chế snapshot window/collision handling để phối hợp dữ liệu đọc lại với thay đổi từ log theo connector và phiên bản. Tuy vậy, nếu ứng dụng tự đẩy dữ liệu snapshot/streaming vào những channel hoặc worker khác nhau và cho chúng ghi đích bất đồng bộ, vẫn có thể tạo thứ tự commit sai.

Ví dụ một bản chụp cũ `status=NEW` hoàn tất xử lý **sau** event streaming `status=PAID` có thể ghi đè projection trở về `NEW`. Khi xây dựng projection, cần định nghĩa rõ chiến lược snapshot và cập nhật theo phiên bản hoặc thứ tự nguồn/partition đáng tin cậy.

## 6. Consumer group: partition được giao cho ai?

Trong một Kafka **consumer group**, tại một thời điểm thông thường **một partition chỉ được gán cho một consumer member hoạt động** trong group đó. Một consumer có thể sở hữu **nhiều partition**, và nhiều consumer trong group giúp xử lý song song **giữa các partition**.

Ví dụ:

| Topic partitions | Consumer members | Kết quả thường gặp |
|---|---:|---|
| 3 | 1 | Một consumer đọc cả ba partition |
| 3 | 2 | Partition được chia cho hai consumer |
| 3 | 3 | Mỗi consumer thường nhận một partition |
| 3 | 6 | Chỉ tối đa ba member có assignment topic này; thành viên dư có thể idle |

Sơ đồ chỉ xét **một topic với ba partition**; assignment thực tế còn tùy các topic đã subscribe, assignor, instance và consumer group.

### Rebalance có phá thứ tự không?

Khi consumer join/leave, Kafka rebalance có thể chuyển partition từ member A sang member B. Thứ tự record trong log **không đổi**. Tuy nhiên, ứng dụng có thể làm sai nếu:

- A đã đẩy offset 101 tới một worker bất đồng bộ, nhưng worker chưa ghi đích.
- Rebalance xảy ra và B bắt đầu xử lý từ offset đã commit.
- A vẫn có một tác vụ cũ đang chạy và ghi dữ liệu **sau** khi B đã áp dụng record mới hơn.

Để tránh “zombie processing”, cần quản lý **in-flight work**, hủy/drain tác vụ khi revoke partition, và dùng fencing/version hoặc transactional strategy phù hợp. Chỉ dựa vào số member trong group không đủ để đảm bảo trạng thái đích.

## 7. Spring Integration: MessageChannel quyết định thứ tự xử lý thực tế

Kafka inbound adapter nhận record rồi đưa vào Spring Integration flow. **Loại channel** và handler concurrency ảnh hưởng rất lớn tới kết quả.

| Thành phần / cấu hình | Ảnh hưởng tới ordering |
|---|---|
| `DirectChannel` với handler đồng bộ | Caller xử lý message trên luồng gọi; thuận lợi để hoàn tất việc ghi đích trước khi tiếp tục record khác trên cùng consumer thread |
| `ExecutorChannel` | Giao message cho thread pool; record offset sau có thể xử lý xong trước offset trước |
| `QueueChannel` + nhiều poller/worker | Message có thể được lấy ra theo thứ tự queue nhưng thời điểm **commit nghiệp vụ** có thể đảo |
| `PublishSubscribeChannel` không đồng bộ | Nhiều subscriber/worker có thể hoàn tất khác nhau; cần hợp đồng riêng để xác nhận mọi nhánh |
| Transformer/router/service activator | Nếu gọi async hoặc đẩy sang executor nội bộ, có thể phá thứ tự dù channel bên ngoài đồng bộ |
| Outbound Kafka/JMS/HTTP adapter | Thứ tự hoàn tất ở đích còn phụ thuộc broker/service ngoài, retry và callback |
| Kafka listener concurrency | Hỗ trợ song song giữa partition; cần kiểm chứng cách listener container quản lý partition và lỗi |

Một mô hình đơn giản khi **ưu tiên đúng thứ tự trên từng partition**:

~~~mermaid
flowchart LR
    K[(Kafka partition p)] --> C[Listener thread<br/>đọc offset n rồi n+1]
    C --> D[DirectChannel]
    D --> T[Transformer đồng bộ]
    T --> H[Service activator đồng bộ]
    H --> DB[(Projection transaction)]
    DB --> A[Ack/commit theo cấu hình]
~~~

Trong mô hình này, handler nên **chờ transaction đích hoàn tất** rồi mới trả về. Nếu chuyển sang xử lý bất đồng bộ giữa đường, cần cơ chế giữ thứ tự/ack tương ứng, không được giả định việc `send()` trả về nghĩa là sink đã commit.

### 7.1. Ví dụ ý tưởng cấu hình

Các thành phần sau minh họa **hợp đồng**, không phải toàn bộ Spring Boot/Kafka configuration có thể chạy độc lập:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.messaging.MessageChannel;

@Configuration
public class CdcChannels {
    @Bean
    MessageChannel orderedCdcChannel() {
        return new DirectChannel();
    }
}
~~~

Spring Integration Kafka inbound adapter có thể được nối tới `orderedCdcChannel`. Phía nhận cần cấu hình serializer/deserializer, converter, error handling, Kafka container và transaction phù hợp; đoạn trên mới thiết lập **một channel đồng bộ**.

Nếu cần throughput cao, nên thử tăng **số partition** và số consumer phù hợp rồi đo lag, thay vì lập tức đặt `ExecutorChannel` nhiều thread đẩy từng record của **cùng partition** đi xử lý không kiểm soát. Vẫn phải đánh giá tải nguồn, thứ tự theo key và khả năng thay đổi partition mapping.

### 7.2. Concurrency = 1 có đủ không?

`concurrency=1` thường làm một listener container xử lý record trên một consumer thread, nhưng không phải lời hứa end-to-end nếu:

- Ứng dụng chạy nhiều instance/group khác nhau cùng ghi một projection.
- Handler phát asynchronous task và trả về sớm.
- Record được chuyển đến một work queue rồi nhiều worker cùng cập nhật cùng key.
- Rebalance còn tác vụ cũ, replay/DLT hoặc nhiều topic nhập cùng một bảng.

Ngược lại, **concurrency > 1** không tự động làm sai thứ tự theo partition nếu listener container assign các partition độc lập và toàn bộ processing của mỗi partition vẫn tuần tự. Cần phân biệt **song song giữa partition** (thường an toàn khi các key độc lập) và **song song bên trong một partition** (cần điều phối).

## 8. Commit offset phải gắn với hoàn thành xử lý

Kafka consumer group lưu **committed offset** để biết lần sau bắt đầu đọc từ đâu. Thông thường, giá trị commit cho một partition biểu diễn **offset của record tiếp theo cần xử lý**, chẳng hạn đã xử lý đến offset 101 thì vị trí commit có thể là 102.

Quan hệ an toàn điển hình:

~~~text
Poll record 100
  -> parse
  -> validate
  -> write projection (transaction commit)
  -> mark record 100 handled
Poll/process record 101
  -> ...
Commit consumer offset theo ack mode và khoảng xử lý an toàn
~~~

Nếu ghi dữ liệu đích xong nhưng **chưa commit Kafka offset**, sau crash có thể nhận lại record. Đây là tình huống at-least-once: handler cần idempotency.

Nếu commit Kafka offset **trước khi** transaction đích an toàn, sau crash có thể bỏ qua record ở group hiện tại dù projection chưa cập nhật.

### 8.1. Offset không thể “nhảy” qua record chưa xong

Giả sử partition 2 có record `100, 101, 102`, ba worker xử lý song song:

| Offset | Trạng thái | Có thể commit vị trí 103 chưa? |
|---:|---|---|
| 100 | Đã ghi đích | Chưa nếu 101 hoặc 102 chưa xong |
| 101 | Đang retry | **Chưa** |
| 102 | Đã ghi đích | **Chưa** nếu 101 vẫn chưa giải quyết |

Commit 103 sẽ báo với consumer group rằng mọi record trước vị trí đó không cần đọc lại theo checkpoint, gây nguy cơ mất xử lý record 101 khi restart.

Nếu cần worker song song trong một partition, thiết kế phải giữ **frontier các offset hoàn tất liên tiếp**, chỉ xác nhận tới vị trí ngay sau dãy đã hoàn tất an toàn; đồng thời cần xác định trạng thái của các tác vụ đang chạy khi rebalance và lỗi. Mô hình này phức tạp hơn xử lý tuần tự, nên chỉ dùng khi có nhu cầu throughput rõ ràng.

### 8.2. Một channel bền vững có thay thế DB transaction không?

Nếu inbound adapter đưa message vào queue bền vững và xác nhận thành công sau khi queue đã lưu an toàn, có thể xem đây là **điểm bàn giao có kiểm soát**, rồi queue xử lý tiếp với checkpoint riêng. Tuy nhiên phải làm rõ:

- Queue có bền vững qua restart không?
- Key và partition/offset được giữ để phát lại đúng thứ tự không?
- Có thể một message vào queue thành công nhưng DB đích chưa cập nhật không?
- Có cơ chế retry, dedupe, fencing và DLQ cho luồng queue không?

Không nên commit Kafka offset chỉ vì message được đẩy tới một **in-memory queue**; khi tiến trình chết, message chưa xử lý có thể biến mất.

## 9. Retry, DLT và sự kiện đến muộn phá thứ tự thế nào?

Một lỗi thường gặp:

~~~text
offset 201: order=42, status=PAID      -> lỗi mapping -> đưa DLT
offset 202: order=42, status=SHIPPED   -> áp dụng thành công
... nhiều phút sau ...
redrive 201 -> UPSERT status=PAID      -> projection bị lùi
~~~

Gửi record lỗi đến **Dead Letter Topic (DLT)** giúp consumer có thể đi tiếp theo policy, nhưng **không bảo đảm chuỗi business state vẫn được áp dụng đúng**.

Các lựa chọn tùy mục tiêu:

1. **Giữ chặt thứ tự:** retry có giới hạn, sau đó dừng partition/key nếu record chưa thể được xử lý an toàn; sửa lỗi rồi tiếp tục từ chính record đó.
2. **Cho phép cô lập lỗi:** xuất DLT và tiến tiếp, nhưng sink phải biết cách nhận record cũ mà không ghi đè trạng thái mới; cần theo dõi và đối soát khoảng thiếu.
3. **Phiên bản hóa state:** chỉ nhận event mới hơn theo một thứ tự/version đáng tin cậy, gồm cả delete marker để ngăn event cũ tạo lại hàng đã xóa.
4. **Khôi phục lại trạng thái hiện tại:** nếu projection chỉ cần state cuối, có thể đọc lại từ nguồn hoặc chạy reconciliation theo chính sách thay vì áp dụng vô điều kiện một delta cũ.

**Timestamp không phải giải pháp tổng quát:** `ts_ms` có thể trùng, lệch đồng hồ, thuộc snapshot hoặc chỉ phản ánh thời điểm connector xử lý. Một version/ordering key đáng tin cậy phải có scope và quy tắc so sánh phù hợp connector, nguồn và business key. Cũng không thể so sánh offset từ hai partition khác nhau như một version toàn cục.

### Xóa và tombstone

Debezium delete event thường có `op="d"` với `after=null`; một **Kafka tombstone** là record cùng key nhưng value ở mức Kafka bằng `null`, có thể được phát để hỗ trợ compaction.

~~~text
offset 300: key={"id":42}, value={...,"op":"d","after":null}
offset 301: key={"id":42}, value=null  (nếu tombstone được bật)
~~~

Nếu một update cũ được replay sau DELETE, upsert vô điều kiện có thể **tái tạo một hàng đã xóa**. Trường hợp này có thể cần lưu **tombstone/version marker** trong projection để biết một event cũ không được phép hồi sinh state, hoặc xử lý chuỗi theo thứ tự và kiểm soát replay. Không coi Kafka compaction là cơ chế tự động bảo vệ thứ tự commit của database đích.

## 10. Điều gì xảy ra khi tăng số partition hoặc đổi partitioner?

Giả sử Kafka topic hiện có 4 partition và hash của key `{"id":42}` đưa nó vào partition 1. Sau này đội vận hành tăng topic lên 8 partition. **Partition mapping có thể đổi**, nên các event mới của `id=42` có thể tới một partition khác trong khi event cũ vẫn nằm ở partition trước.

~~~text
Trước thay đổi:
  partition 1: order=42, PAID

Sau thay đổi:
  partition 5: order=42, SHIPPED

Hai partition được đọc độc lập
  -> SHIPPED có thể được commit đích trước PAID
~~~

Chuyển đổi key serializer, SMT, route topic, thay producer partitioning strategy hoặc thêm custom partitioner cũng có thể tạo hiệu ứng tương tự.

**Lưu ý thiết kế:**

- Chọn số partition dựa trên throughput dự kiến và yêu cầu thứ tự.
- Nếu cần giữ thứ tự dài hạn theo key, xem thay đổi partition count là một **migration dữ liệu/định tuyến**, không chỉ thay đổi thông số hiệu năng.
- Có thể cân nhắc topic mới với kế hoạch chuyển đổi, ngừng ghi vào tuyến cũ, drain backlog, đối soát, rồi chuyển producer/consumer có kiểm soát.
- Đảm bảo nhiều pipeline cũ/mới không cùng ghi vào projection mà thiếu version/fencing.

Thêm partition không nhất thiết gây sai lệch với mọi record/key, nhưng **không thể bảo đảm invariant cùng key → cùng partition qua các giai đoạn thay đổi** nếu không có kế hoạch kiểm chứng.

## 11. Ba yêu cầu ordering và kiến trúc phù hợp

| Yêu cầu | Thiết kế tham khảo | Chi phí/giới hạn |
|---|---|---|
| **Thứ tự của từng bản ghi (`orderId`)** | Stable Kafka key, mapping partition ổn định, xử lý tuần tự theo partition hoặc per-key sequencer, idempotent sink | Scale được giữa các key; key nóng có thể thành nút nghẽn |
| **Thứ tự theo một nhóm nghiệp vụ (`customerId`)** | Chọn key theo customer hoặc dùng topic sự kiện nghiệp vụ/outbox; xử lý tuần tự trong group | Nhiều order của một customer dồn cùng partition; thay đổi key và fan-out cần cân nhắc |
| **Một thứ tự toàn cục cho toàn bộ sự kiện** | Một partition hoặc bộ điều phối/đánh số thứ tự toàn cục có trạng thái bền vững | Hạn chế throughput; CDC đa bảng/nhiều nguồn không tự cung cấp total order toàn cục |

Muốn thứ tự toàn cục thực sự trên **nhiều database nguồn**, cần một nguồn thứ tự chung hoặc giao thức phối hợp. Kafka offset không tạo được quan hệ tổng thứ tự giữa các partition, và transaction ID của từng database không phải ID so sánh toàn cục.

### 11.1. Khi nào dùng transactional outbox?

Nếu yêu cầu nghiệp vụ là “khi thanh toán thành công, xuất một event `OrderPaid` sau khi bảng đơn hàng và payment được cập nhật cùng transaction”, một **outbox table** được ghi trong cùng transaction nguồn có thể giúp phát một record nghiệp vụ có key `orderId`, thay vì consumer tự hợp nhất nhiều row CDC topic.

Debezium có thể thu nhận row thay đổi trong bảng outbox; một SMT/routing strategy phù hợp đưa event vào topic nghiệp vụ. Outbox cải thiện **ranh giới ý nghĩa** và lựa chọn key, nhưng vẫn cần quản lý partition count, retry và idempotency ở downstream.

### 11.2. Khi nào cần per-key sequencer?

Per-key sequencer hoặc actor/mailbox có thể cho phép các khóa khác nhau xử lý song song trong khi từng key vẫn xử lý lần lượt. Tuy vậy, nếu một Kafka partition được chia thành nhiều worker, cơ chế ack/commit Kafka cần biết **offset liên tiếp nào đã xử lý xong**, và khi thay member/instance phải chống các worker cũ ghi muộn. Đây là bài toán điều phối có trạng thái, không thể đạt chỉ bằng `ConcurrentHashMap<key, Lock>` trong một JVM khi chạy nhiều instance.

## 12. Ví dụ handler an toàn hơn với idempotency và thứ tự

Giả sử một projection PostgreSQL `reporting.orders` nhận Kafka CDC của `sales.orders`. Các event đến **từ một topic-partition ổn định**, xử lý tuần tự theo key; ứng dụng cần chống việc consumer phát lại cùng record sau crash.

**Cách tiếp cận đơn giản** là UPSERT idempotent cho cùng state:

~~~sql
INSERT INTO reporting.orders (id, status)
VALUES (42, 'PAID')
ON CONFLICT (id)
DO UPDATE SET status = EXCLUDED.status;
~~~

Lệnh này chịu được việc nhận lặp lại đúng event `PAID`, nhưng **không đủ** khi một event `PAID` cũ được phát lại **sau** `SHIPPED`.

Nếu luồng đích cần nhận event đến muộn, có thể duy trì trường `source_version` với quy tắc thứ tự đã được **chứng minh hợp lệ trong phạm vi một bản ghi**. Ví dụ **giả mã**:

~~~text
onCdcRecord(event, kafkaRecord):
    key = validatedBusinessKey(event, kafkaRecord)
    version = trustworthyVersionForThisSourceAndKey(event)

    transaction:
        current = selectProjectionStateForUpdate(key)

        if current exists and version <= current.lastAppliedVersion:
            return ALREADY_HANDLED_OR_STALE

        if event.op in ["r", "c", "u"]:
            saveProjectionAndVersion(key, event.after, version)
        else if event.op == "d":
            saveDeleteMarkerAndVersion(key, version)
        else:
            failWithContext(event)

    acknowledgeAfterTransactionOrDurableRecovery()
~~~

Điểm cần thận trọng:

- **`trustworthyVersionForThisSourceAndKey` là giao thức do kiến trúc lựa chọn**, không phải API sẵn có. Một `lsn` hoặc binlog `pos` đơn lẻ có thể không đủ phân biệt từng hàng/transaction; không so sánh qua các cluster, connector hoặc partition độc lập.
- Với snapshot, version phải phản ánh ranh giới/chính sách snapshot thực tế; không lấy thời điểm consumer nhận event làm thứ tự nguồn.
- So sánh version và ghi dữ liệu đích phải **nguyên tử** để hai worker không cùng vượt điều kiện.
- Delete marker phải được giữ đủ lâu để một event cũ không tạo lại bản ghi đã xóa.
- Nếu chỉ cần xử lý tuần tự theo một partition không đổi, version chủ yếu là biện pháp bảo vệ bổ sung khi có replay, DLT hoặc thay đổi topology.

### 12.1. Có thể dùng Kafka offset làm version không?

**Có thể trong phạm vi hẹp**, nếu tất cả update của một projection key luôn thuộc **một topic-partition cố định** và hệ thống kiểm soát được mọi đường replay. Khi đó cặp (`topic`, `partition`, `offset`) phân biệt vị trí record trên Kafka; offset tăng trong partition.

Nhưng điều này **không đúng nếu** key chuyển sang partition khác, record xuất từ hai topic, nguồn có hai producer độc lập, ứng dụng redrive ra topic mới, hoặc cùng source event bị Debezium phát lại dưới **Kafka offset mới**. Một source event cũ có Kafka offset mới hơn sau phát lại có thể đánh lừa cơ chế “offset lớn nhất là version nghiệp vụ mới nhất”.

Không tạo một cơ chế last-write-wins dựa duy nhất vào Kafka offset nếu những trường hợp này có thể xảy ra.

## 13. Ví dụ lỗi thường gặp

| Triệu chứng | Nguyên nhân khả dĩ | Cách kiểm tra/khắc phục |
|---|---|---|
| Đơn hàng bị lùi trạng thái sau khi tăng throughput | `ExecutorChannel`/worker pool xử lý hai event cùng key song song | Kiểm tra thời điểm bắt đầu/kết thúc handler, chọn DirectChannel hoặc per-key sequencing |
| Chỉ sai sau khi tăng Kafka partitions | Mapping key → partition thay đổi | Đối chiếu partition của cùng key trước/sau thay đổi, lập kế hoạch migration |
| Đúng khi chạy một instance, sai khi scale | Tác vụ async cũ vẫn ghi sau rebalance; nhiều group ghi cùng sink | Kiểm tra assignments, in-flight tasks, fencing, idempotent transaction |
| Sai sau khi redrive DLT | Event cũ được áp dụng sau event mới | Dedupe/version, khóa partition, reconciliation; giữ delete marker |
| Một update payment đến trước update order | Hai bảng/topic/partition độc lập | Dùng outbox hoặc coordinator/transaction metadata nếu cần hợp nhất |
| Offset group tăng nhưng projection thiếu update | Ack trước khi ghi đích, error handler nuốt exception, queue không bền vững | Kiểm tra transaction boundary, listener error handling, điểm giao nhận/commit |
| Một bảng thiếu primary key cho dữ liệu phân tán | Key null hoặc key không ổn định | Thêm identity đáng tin cậy hoặc thay contract capture |
| Snapshot ghi đè update mới | Xử lý `r` và `u` trên nhánh async không có quy tắc thứ tự | Kiểm tra incremental snapshot, per-key sequencing và version |
| Consumer lag một partition cao nhưng partition khác rảnh | Key nóng hoặc record lỗi khiến partition bị chặn | Quan sát lag theo partition; cân nhắc lại partition key/cách xử lý poison pill |

## 14. Thực hành: đọc offset và dự đoán kết quả

Hệ thống Debezium MySQL xuất thay đổi bảng `sales.orders` vào topic Kafka `orders-cdc.sales.orders` có **3 partition**. Spring Integration dùng Kafka inbound adapter và ghi projection theo `id`.

Giả sử các record sau đã được append:

| Topic-partition | Offset | Key | `after.status` |
|---|---:|---|---|
| P1 | 100 | `{"id":42}` | NEW |
| P1 | 101 | `{"id":42}` | PAID |
| P1 | 102 | `{"id":42}` | SHIPPED |
| P2 | 77 | `{"id":99}` | NEW |

Sau đó, ứng dụng chuyển từ `DirectChannel` đồng bộ sang `ExecutorChannel` có 8 worker. Worker xử lý offset 102 nhanh hơn worker offset 101.

**Câu hỏi:**

1. Kafka có vi phạm thứ tự log trong partition P1 không?
2. Vì sao projection của đơn 42 vẫn có thể kết thúc ở `PAID`?
3. Nếu offset 101 còn đang chạy nhưng offset 102 đã ghi đích, consumer có nên commit vị trí 103 không?
4. Nếu lỗi offset 101 bị chuyển vào DLT, cần làm gì trước khi redrive khi offset 102 đã thành công?
5. Khi tăng topic từ 3 lên 6 partition, điều gì cần xác minh để giữ thứ tự cho đơn 42?
6. Nếu event cho `orders.id=42` và `payments.order_id=42` nằm ở hai topic khác nhau, có thể so sánh trực tiếp offset của chúng để xác định thứ tự nghiệp vụ không?

<details>
<summary>Gợi ý lời giải</summary>

1. **Không.** Kafka vẫn lưu P1:100 → 101 → 102. Ứng dụng thay đổi cách xử lý nên thời điểm commit DB khác thứ tự Kafka.
2. Worker 102 lưu `SHIPPED` trước; worker 101 ghi `PAID` sau, ghi đè trạng thái mới. Cần xử lý tuần tự theo partition/key hoặc sử dụng version đáng tin cậy.
3. **Không**, nếu 101 chưa được xử lý hoặc recovery bền vững. Commit 103 làm vị trí nhóm nhảy qua 101, gây nguy cơ mất xử lý sau crash.
4. Xem record 101 có còn cần áp dụng không, bảo vệ projection trước event cũ; dùng version/dedupe/reconciliation hoặc chặn key đến khi khôi phục đúng thứ tự.
5. Kiểm tra hash/partitioner, serialized key, mapping trước/sau tăng partition, backlog và kế hoạch drain/migration. Cùng key có thể rơi vào partition mới.
6. **Không.** Kafka offset chỉ so sánh trong một partition cụ thể. Nếu cần hợp nhất transaction, dùng cơ chế phối hợp hoặc sự kiện nghiệp vụ/outbox rõ ràng.

</details>

### Bài tập thiết kế

Một hệ thống cần cập nhật bảng `account_balance` từ CDC, với yêu cầu **không được cộng/trừ số dư hai lần**, đồng thời phục hồi được sau khi consumer restart. Hãy đề xuất:

- Key để chọn partition nếu mỗi tài khoản được xử lý độc lập.
- Channel và concurrency phù hợp trong Spring Integration.
- Cơ chế idempotency, transaction, offset acknowledgment và xử lý event lặp.
- Hành vi nếu event cũ được redrive từ DLT sau một update mới.

Gợi ý: với nghiệp vụ tài chính, nên cân nhắc xử lý **sự kiện có ID duy nhất và transaction outbox** hoặc đồng bộ state tuyệt đối có version đáng tin cậy, thay vì biến mỗi row update thành một lệnh “cộng số dư” không idempotent.

## 15. Checklist khi triển khai CDC cần giữ thứ tự

- [ ] Xác định **scope ordering**: theo hàng, theo customer/account, theo transaction hay toàn cục.
- [ ] Kiểm tra Debezium Kafka key, schema/key converter, SMT, topic routing và partitioner thực tế.
- [ ] Đảm bảo key ổn định được route tới cùng partition trong giai đoạn cần giữ thứ tự.
- [ ] Hiểu Kafka offset theo **topic-partition**; không so sánh offset khác partition như một global sequence.
- [ ] Kiểm tra nguồn MySQL/PostgreSQL, snapshot mode, log position và transaction metadata nếu dùng.
- [ ] Xác định tác động của initial/incremental snapshot tới những event `r` và event streaming `u/c/d`.
- [ ] Thiết kế Spring Integration channel, listener concurrency, worker/async handoff cho đúng yêu cầu ordering.
- [ ] Xác nhận ack/commit chỉ xảy ra sau transaction đích hoặc bước recovery bền vững theo policy.
- [ ] Khi xử lý song song một partition, không commit vượt offset đang xử lý hoặc chưa recovery an toàn.
- [ ] Dùng idempotency/version đúng scope; kiểm thử replay, delete/tombstone và stale event.
- [ ] Có quy trình xử lý poison pill/DLT mà không âm thầm phá thứ tự theo khóa.
- [ ] Đánh giá lại yêu cầu ordering khi tăng partition count, đổi partitioner, thay key hoặc chuyển topic.
- [ ] Theo dõi consumer lag **theo partition**, rebalance, thời gian xử lý per-key và độ trễ ghi đích.
- [ ] Diễn tập restart/rebalance khi còn in-flight message và xác minh projection không lùi trạng thái.

**Ghi nhớ:** Kafka bảo đảm **thứ tự record trong từng partition**. Debezium mang đến dòng thay đổi từ transaction log; record key và chiến lược partitioning quyết định những thay đổi nào có thể chia sẻ thứ tự đó. Trong **Spring Integration**, thứ tự chỉ trở thành đúng đắn ở hệ thống đích khi xử lý đồng bộ hoặc điều phối rõ ràng, commit sau khi hoàn thành an toàn, và có idempotency/khả năng phục hồi cho retry, replay, DLT cùng những lần thay đổi topology.
