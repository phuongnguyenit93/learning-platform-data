# Managed Service for Apache Flink và xử lý stream có trạng thái

Amazon Managed Service for Apache Flink là dịch vụ được quản lý để xây dựng và vận hành ứng dụng xử lý dữ liệu streaming bằng Apache Flink. Dịch vụ phù hợp khi dữ liệu đến liên tục và ứng dụng cần tính toán theo thời gian, kết hợp sự kiện, gom nhóm theo khóa, xử lý cửa sổ, phát hiện mẫu hoặc duy trì trạng thái giữa các sự kiện. Các ví dụ điển hình gồm phát hiện gian lận giao dịch, tính số liệu sản phẩm theo phút, giám sát thiết bị IoT, phân tích clickstream và làm giàu dữ liệu trước khi ghi vào hệ thống downstream.

Điểm khác biệt quan trọng của xử lý stream có trạng thái là ứng dụng không chỉ xử lý từng record độc lập. Nó có thể nhớ số lần giao dịch của một tài khoản, tổng doanh thu của một cửa sổ thời gian, trạng thái phiên người dùng hoặc kết quả đã tích lũy từ nhiều partition. Khi task bị lỗi, state phải được khôi phục nhất quán với vị trí đọc của nguồn và trạng thái ghi của sink. Apache Flink cung cấp state, checkpoint, event time và cơ chế phục hồi; Managed Service for Apache Flink quản lý hạ tầng chạy, tích hợp AWS, giám sát và các thao tác vận hành ứng dụng.

Bài học tập trung vào mô hình stateful stream processing, DataStream API và Table API/SQL, key/window/time semantics, checkpoint và snapshot, exactly-once, scaling, connector, triển khai và vận hành trên AWS.

## 1. Mục tiêu học tập

Sau bài học, người học có thể:

- Giải thích vai trò của Apache Flink trong kiến trúc streaming và phân biệt xử lý stateless với stateful.
- Phân biệt source, transformation/operator, keyed state, operator state, window, sink và runtime task.
- Chọn processing time, ingestion time hoặc event time; hiểu watermark, late event và idle partition.
- Thiết kế state theo key, TTL, window và serialization phù hợp với yêu cầu nghiệp vụ.
- Phân biệt checkpoint, savepoint, application snapshot, system snapshot và enhanced snapshot.
- Thiết kế phục hồi sau lỗi và hiểu điều kiện để đạt exactly-once ở cấp ứng dụng và end-to-end.
- Chọn DataStream API, Table API hoặc SQL cho workload.
- Kết nối Kinesis Data Streams, Amazon MSK, Amazon S3, Data Firehose và các sink được hỗ trợ.
- Cấu hình parallelism, maxParallelism, ParallelismPerKPU và autoscaling.
- Triển khai ứng dụng Java/Python/SQL, quản lý IAM, VPC, logging, metrics và chi phí.
- Điều tra backpressure, checkpoint failure, lag, state growth và lỗi tương thích snapshot.

## 2. Managed Service for Apache Flink là gì?

Amazon Managed Service for Apache Flink trước đây có tên Amazon Kinesis Data Analytics for Apache Flink. Dịch vụ cho phép phát triển và chạy ứng dụng Apache Flink mà không phải tự quản lý cụm compute, task manager, job manager hoặc hạ tầng lưu trữ checkpoint. Ứng dụng có thể được viết bằng Java, Scala, Python hoặc SQL tùy API/runtime và connector tương thích.

Apache Flink là engine xử lý luồng phân tán. Một job gồm đồ thị các operator liên kết với nhau. Các operator xử lý record song song trên nhiều task, trao đổi dữ liệu qua network shuffle và có thể duy trì state. Runtime điều phối task, checkpoint và khôi phục khi lỗi.

Managed Service for Apache Flink quản lý vòng đời ứng dụng và tài nguyên chạy. Người phát triển vẫn chịu trách nhiệm thiết kế logic, schema, key, state, watermark, connector, sink semantics, cấu hình capacity, quyền IAM, kiểm thử và vận hành nghiệp vụ.

### 2.1 Thành phần của một ứng dụng

| Thành phần | Vai trò |
|---|---|
| Source | Đọc sự kiện từ Kinesis Data Streams, Amazon MSK/Kafka hoặc nguồn được connector hỗ trợ |
| Deserialization | Chuyển byte/message thành record có schema và kiểu dữ liệu |
| Transformation | Filter, map, flatMap, join, aggregate, enrich hoặc route record |
| Keyed state | Lưu trạng thái riêng cho từng key, ví dụ tổng giao dịch theo account |
| Operator state | Lưu trạng thái gắn với một operator/subtask, ví dụ offset hoặc danh sách partition được quản lý |
| Window | Gom record theo thời gian hoặc số lượng để tính kết quả |
| Timer | Kích hoạt xử lý tại event time hoặc processing time |
| Sink | Ghi kết quả sang Kinesis, Kafka/MSK, S3, Firehose hoặc hệ thống được hỗ trợ |
| Checkpoint coordinator | Điều phối checkpoint để lưu nhất quán state và vị trí xử lý |
| Runtime | Lập lịch task, phân phối parallelism, phục hồi và thực thi job |

### 2.2 Kiến trúc tổng quát

    Producers / Applications / IoT Devices
                    |
                    v
             Kinesis Data Streams
                    |
                    v
        Managed Service for Apache Flink
          +----------------------------+
          | Source and deserializer    |
          | Timestamp and watermark    |
          | KeyBy / Window / Join      |
          | Keyed state and timers     |
          | Checkpoint / recovery      |
          | Aggregation and enrichment |
          +----------------------------+
             |             |        |
             v             v        v
          Kinesis         MSK      S3 / Firehose
             |             |        |
             +-------------+--------+
                           |
                           v
                Lakehouse / Analytics
                Alerts / Applications

Một kiến trúc thực tế còn có IAM execution role, CloudWatch Logs, CloudWatch metrics, S3 chứa application package, KMS key, VPC/subnet/security group và quy trình deployment. Nguồn và đích được tính phí riêng với Managed Service for Apache Flink.

### 2.3 Khi nào nên dùng Flink?

Flink phù hợp khi ứng dụng cần:

- Tính toán liên tục trên dữ liệu không ngừng tăng.
- Duy trì state giữa các sự kiện.
- Window aggregation theo event time.
- Join nhiều stream hoặc enrich với dữ liệu tham chiếu.
- Xử lý out-of-order event và watermark.
- Phục hồi từ checkpoint mà không phải đọc lại toàn bộ lịch sử.
- Độ trễ thấp với throughput cao và logic xử lý phức tạp.

Nếu chỉ cần chuyển record đơn giản từ stream sang S3, không có state hoặc window phức tạp, có thể xem xét Amazon Data Firehose hoặc các dịch vụ tích hợp khác. Nếu workload chủ yếu là truy vấn SQL streaming, Table API/SQL hoặc dịch vụ analytics SQL chuyên dụng có thể giảm lượng code. Chọn engine theo yêu cầu state, event time, latency, khả năng kiểm soát và năng lực vận hành.

## 3. Stateful và stateless stream processing

### 3.1 Stateless processing

Stateless operator xử lý record hiện tại mà không cần nhớ kết quả của record trước. Ví dụ:

- Chuẩn hóa tên trường.
- Lọc giao dịch có amount nhỏ hơn ngưỡng.
- Chuyển JSON thành Avro/Protobuf.
- Thêm một hằng số hoặc đổi định dạng timestamp.

Với cùng input, operator có thể tính output độc lập. Nếu task restart, thường chỉ cần đọc lại input từ vị trí phù hợp; không phải phục hồi state nghiệp vụ tích lũy.

### 3.2 Stateful processing

Stateful operator lưu dữ liệu qua nhiều record. Ví dụ:

- Tổng số giao dịch theo tài khoản trong 10 phút.
- Số lần đăng nhập thất bại trong một cửa sổ trượt.
- Trạng thái phiên người dùng đến khi không còn hoạt động.
- Số lượng hàng tồn theo SKU.
- Kết quả join một stream giao dịch với dữ liệu tham chiếu đã nạp.

Giả sử stream nhận các giao dịch:

| Thời điểm | Account | Amount |
|---|---|---:|
| 10:00:01 | A100 | 40 |
| 10:00:03 | B200 | 25 |
| 10:00:05 | A100 | 70 |
| 10:00:08 | A100 | 20 |
| 10:00:09 | B200 | 30 |

Sau khi group theo account, state có thể là:

| Account key | Running total |
|---|---:|
| A100 | 130 |
| B200 | 55 |

Khi record tiếp theo của A100 đến, operator cập nhật state A100 mà không phải quét lại toàn bộ stream. State có thể tồn tại hàng giờ, nhiều ngày hoặc lâu hơn tùy TTL và yêu cầu nghiệp vụ.

### 3.3 Keyed state và operator state

**Keyed state** được phân vùng theo key sau phép chia stream bằng keyBy. Mỗi key có state riêng. Ví dụ:

    transactions
      -> keyBy(accountId)
      -> ValueState(totalAmount)
      -> fraud rule

Keyed state phù hợp với counter, aggregate, trạng thái phiên, timer và rule theo từng entity. Khi rescale, Flink phân phối lại key group giữa các parallel subtasks.

**Operator state** gắn với operator instance/subtask thay vì một business key cụ thể. Nó hữu ích cho trạng thái cần phân phối lại giữa subtask, ví dụ metadata partition hoặc trạng thái nguồn tùy connector. Operator state có thể dùng union redistribution hoặc list redistribution theo cách triển khai.

Không chọn operator state để thay thế keyed state nếu logic cần cách ly trạng thái theo customer/account. State đúng loại giúp rescale và phục hồi chính xác.

### 3.4 State backend và kích thước state

Managed Service for Apache Flink dùng RocksDB làm embedded key/value store cho state trong môi trường runtime theo tài liệu dịch vụ. State đang hoạt động có thể nằm trên local storage; checkpoint/snapshot được lưu bền vững để phục hồi khi máy/task bị mất.

Kích thước state ảnh hưởng:

- Thời gian checkpoint và restore.
- Dung lượng running application storage.
- Thời gian rescale.
- I/O và memory pressure.
- Khả năng hoàn tất checkpoint trong timeout.

Đừng lưu toàn bộ payload không cần thiết trong state. Chỉ giữ thông tin phục vụ quyết định tiếp theo, đặt TTL khi dữ liệu hết giá trị, dùng serializer hiệu quả và tránh object graph quá lớn.

### 3.5 State TTL

State TTL cho phép dữ liệu state tự hết hạn theo thời gian. Ví dụ trạng thái phiên người dùng có thể hết hạn sau 30 phút không hoạt động. TTL giúp giới hạn state growth nhưng cần chọn theo semantics:

- TTL bắt đầu khi tạo state hay khi cập nhật state?
- Đọc state có làm gia hạn TTL không?
- Dữ liệu hết hạn có thể được dọn ngay hay chỉ dọn dần?
- Khi restore từ checkpoint, TTL timestamp có tiếp tục đúng ý nghĩa không?
- TTL có làm mất dữ liệu cần cho late event hoặc audit không?

TTL không thay thế retention của stream hoặc database. Nếu cần replay/audit, giữ dữ liệu gốc ở data lake hoặc source retention phù hợp.

## 4. Event time, processing time và watermark

### 4.1 Ba khái niệm thời gian

| Time characteristic | Ý nghĩa | Ví dụ |
|---|---|---|
| Processing time | Thời gian máy thực thi operator xử lý record | Record được xử lý lúc 10:05:10 |
| Ingestion time | Thời gian record đi vào hệ thống Flink | Record được Flink nhận lúc 10:05:08 |
| Event time | Thời điểm sự kiện thực sự xảy ra tại producer | Giao dịch xảy ra lúc 10:04:55 |

Processing time dễ dùng và phản ánh thời điểm hệ thống xử lý, nhưng kết quả phụ thuộc tốc độ xử lý, retry và backlog. Event time phản ánh thời gian nghiệp vụ của sự kiện, phù hợp với analytics cần kết quả đúng theo lúc sự kiện xảy ra.

Ví dụ điện thoại mất mạng 5 phút rồi gửi batch event. Processing time sẽ xếp các event vào thời điểm batch được nhận; event time vẫn có thể đặt chúng vào các cửa sổ lúc chúng thực sự xảy ra.

### 4.2 Watermark là gì?

Watermark là tín hiệu cho biết stream processor có thể tin rằng các event có timestamp nhỏ hơn một mốc thời gian đã được xử lý, trong giới hạn out-of-order được cấu hình. Watermark giúp Flink quyết định khi nào đóng window và phát kết quả.

Ví dụ dùng event time và cho phép trễ tối đa 30 giây:

    Watermark = max(event timestamp observed) - 30 seconds

Nếu event mới nhất có timestamp 10:05:00, watermark xấp xỉ 10:04:30. Window kết thúc 10:04:00 có thể được đóng khi watermark đi qua mốc kết thúc theo semantics của window.

Watermark không phải timestamp của record và cũng không phải cam kết không còn event đến trễ. Một event cũ hơn watermark vẫn có thể xuất hiện do producer delay, retry hoặc source partition bị đọc không đồng đều.

### 4.3 Out-of-order event và allowed lateness

Giả sử cửa sổ 1 phút kết thúc lúc 10:05:00. Một giao dịch có event time 10:04:58 đến lúc 10:05:20. Nếu watermark đã vượt 10:05:00, event này là late event đối với window.

Có một số chiến lược:

- Cho phép out-of-order trong một khoảng bằng watermark delay.
- Cho phép allowed lateness để cập nhật window đã phát kết quả trong một khoảng bổ sung.
- Gửi late event vào side output để xử lý riêng.
- Dùng cơ chế correction/retraction ở downstream nếu nghiệp vụ cần điều chỉnh kết quả.
- Loại bỏ event quá trễ nếu không còn giá trị.

Chọn chiến lược theo SLA. Dashboard realtime có thể chấp nhận kết quả sơ bộ và correction; đối soát tài chính có thể cần late-event path và quy trình chốt kỳ.

### 4.4 Idle shard/partition

Watermark downstream thường bị chi phối bởi input chậm nhất. Nếu một source subtask đọc nhiều shard/partition và một shard không có dữ liệu, watermark từ shard idle có thể không tiến lên, khiến event-time window không đóng.

Có thể dùng watermark strategy với idleness timeout để loại subtask idle khỏi phép tính watermark. Ví dụ ý tưởng trong Java DataStream API:

    WatermarkStrategy.<Event>forBoundedOutOfOrderness(Duration.ofSeconds(30))
        .withIdleness(Duration.ofMinutes(1));

Idleness giải quyết việc partition không phát record, nhưng không làm cho event time của dữ liệu cũ tiến lên. Cần hiểu semantics của source connector và kiểm tra late event sau khi shard hoạt động trở lại.

### 4.5 Chọn time semantics

| Yêu cầu | Gợi ý |
|---|---|
| Đếm số record xử lý trong 1 phút theo máy | Processing time |
| Tổng giao dịch theo phút xảy ra thực tế | Event time |
| SLA dựa trên lúc hệ thống nhận dữ liệu | Ingestion time hoặc timestamp do source gán |
| Nhiều producer có clock lệch | Chuẩn hóa timestamp, giới hạn out-of-order và kiểm tra clock skew |
| Source có shard idle | Watermark idleness và late-event policy |

## 5. Window và phép tính theo thời gian

### 5.1 Tumbling window

Tumbling window chia stream thành các khoảng không chồng lấn, ví dụ mỗi phút hoặc mỗi giờ. Mỗi event thuộc một window theo timestamp.

Ví dụ tổng amount theo account trong mỗi phút:

    event stream
      -> keyBy(accountId)
      -> tumbling event-time window(1 minute)
      -> sum(amount)

### 5.2 Sliding window

Sliding window có kích thước và bước trượt. Ví dụ cửa sổ 10 phút, cập nhật mỗi phút. Một event có thể thuộc nhiều window. Loại này phù hợp với rolling average, moving count hoặc phát hiện hành vi gần đây.

### 5.3 Session window

Session window nhóm các event gần nhau theo thời gian hoạt động của một key. Nếu khoảng im lặng vượt gap, session kết thúc. Dùng cho phiên người dùng, thiết bị IoT hoặc tương tác khách hàng.

### 5.4 Count window và global window

Count window dựa trên số lượng record thay vì thời gian. Global window gom tất cả record vào một window và cần trigger để phát kết quả. Dùng khi logic nghiệp vụ yêu cầu theo batch count hoặc custom trigger; nếu không, window time-based thường dễ giải thích hơn.

### 5.5 Window lifecycle

Window không chỉ có kích thước. Cần xác định:

- Timestamp dùng để gán event vào window.
- Watermark và allowed lateness.
- Trigger khi nào phát kết quả.
- Accumulation mode hoặc cách xử lý update/retraction.
- Cleanup state sau khi window hết hạn.
- Late event đi đâu.

Window quá dài hoặc allowed lateness quá rộng có thể làm state tăng đáng kể. Window ngắn có thể giảm latency nhưng tăng số lần emit và overhead sink.

## 6. DataStream API và stateful operator

### 6.1 DataStream pipeline

DataStream API cho phép mô tả pipeline bằng source, transformation và sink. Một luồng điển hình:

    Source
      -> Deserialize
      -> Assign timestamps and watermarks
      -> Filter invalid records
      -> KeyBy business key
      -> Stateful process / window
      -> Enrich or route
      -> Sink

Các phép biến đổi phổ biến:

| Operator | Mục đích |
|---|---|
| map | Một input tạo một output |
| flatMap | Một input tạo 0..n output |
| filter | Giữ record thỏa điều kiện |
| keyBy | Chia record theo key để dùng keyed state |
| union | Hợp nhất nhiều stream cùng kiểu |
| connect/coProcess | Kết hợp hai stream và xử lý hai input |
| window | Gom record theo thời gian/số lượng |
| process | Logic tùy chỉnh, state và timer |
| side output | Phát record phụ như late event hoặc invalid data |

### 6.2 Ví dụ keyed state

Ví dụ sau minh họa ý tưởng dùng keyed state để đếm số giao dịch của từng tài khoản. Phần import, schema Event và cấu hình source/sink được lược bỏ để tập trung vào state:

    DataStream<Event> events = ...;

    DataStream<Event> keyed = events
        .keyBy(Event::accountId);

    DataStream<AccountCount> counts = keyed
        .process(new KeyedProcessFunction<String, Event, AccountCount>() {
            private transient ValueState<Long> countState;

            @Override
            public void open(Configuration parameters) {
                ValueStateDescriptor<Long> descriptor =
                    new ValueStateDescriptor<>("transaction-count", Long.class);
                countState = getRuntimeContext().getState(descriptor);
            }

            @Override
            public void processElement(
                Event event,
                Context context,
                Collector<AccountCount> out) throws Exception {
                Long current = countState.value();
                long next = (current == null ? 0L : current) + 1L;
                countState.update(next);
                out.collect(new AccountCount(event.accountId(), next));
            }
        });

KeyBy phải được thực hiện trước khi sử dụng keyed state. Nếu quên keyBy hoặc chọn key không ổn định, state có thể không phản ánh đúng entity. Không dùng accountId null hoặc giá trị mặc định chung cho nhiều record vì chúng sẽ dồn vào một key nóng.

### 6.3 Timer và stateful rule

Timer cho phép operator thực hiện logic tại event time hoặc processing time. Ví dụ:

- Tạo cảnh báo nếu tài khoản không xác nhận giao dịch trong 30 giây.
- Đóng phiên khi không có event mới.
- Gửi kết quả tổng hợp khi window kết thúc.
- Xóa state tạm sau khi quá hạn.

Timer được gắn với key và cần được checkpoint cùng state. Nếu đăng ký quá nhiều timer hoặc không xóa timer không còn cần thiết, state và checkpoint có thể tăng mạnh.

### 6.4 Serialization và schema evolution

State cần được serialize để checkpoint và restore. Kiểu dữ liệu tùy chỉnh phải có serializer ổn định. Việc thay đổi class, field, type, serializer hoặc key có thể làm state cũ không tương thích.

Thực hành tốt:

- Dùng schema có version.
- Giữ kiểu state rõ ràng và ổn định.
- Kiểm tra serialization trong local integration test.
- Tránh thay đổi tên operator nếu cần map state từ savepoint.
- Dùng operator UID ổn định trong DataStream job khi quản lý state qua code update.
- Kiểm thử restore từ snapshot thật trước khi triển khai thay đổi lớn.

## 7. Table API và SQL

Table API/SQL phù hợp với phép tính relational như filter, projection, join, aggregation và window. Nó giảm lượng code Java cho workload có schema/table rõ ràng.

### 7.1 Streaming table

Table có thể đại diện cho stream append-only hoặc changelog stream. Một truy vấn SQL có thể nhận record mới liên tục và phát kết quả cập nhật. Khi join, aggregate hoặc dùng window, runtime vẫn có state phía dưới.

### 7.2 Event-time window bằng SQL

Ví dụ khái niệm:

    CREATE TABLE transactions (
      account_id STRING,
      amount DECIMAL(18, 2),
      event_time TIMESTAMP(3),
      WATERMARK FOR event_time AS event_time - INTERVAL '30' SECOND
    );

    SELECT
      window_start,
      window_end,
      account_id,
      SUM(amount) AS total_amount
    FROM TABLE(
      TUMBLE(
        TABLE transactions,
        DESCRIPTOR(event_time),
        INTERVAL '1' MINUTE
      )
    )
    GROUP BY window_start, window_end, account_id;

Đây là ví dụ minh họa SQL event-time window; phần connector WITH, catalog, serialization và sink phải được cấu hình theo connector/runtime version đang dùng. Không sao chép nguyên schema trên vào production nếu timestamp hoặc watermark của nguồn khác.

### 7.3 Chọn API

| Nhu cầu | API phù hợp |
|---|---|
| Filter/map/aggregate đơn giản với schema rõ | SQL hoặc Table API |
| Keyed state tùy chỉnh, timer, side output | DataStream API |
| Join/aggregation dạng relational | Table API/SQL |
| Kết hợp logic custom và SQL | DataStream + Table API |
| Window và event-time semantics cần kiểm soát | Cả hai, tùy độ phức tạp |

SQL không loại bỏ yêu cầu thiết kế state. Một câu query có GROUP BY hoặc JOIN trên stream vẫn cần state, retention, watermark và checkpoint.

## 8. Checkpoint, savepoint và snapshot

### 8.1 Vì sao cần checkpoint?

Checkpoint là ảnh nhất quán của trạng thái job tại một điểm xử lý. Nó giúp Flink phục hồi state của operator và vị trí đọc source sau khi job/task gặp lỗi. Khi checkpoint thành công, ứng dụng có thể khôi phục và tiếp tục mà không cần xử lý lại toàn bộ lịch sử.

Với Managed Service for Apache Flink, checkpointing được khuyến nghị bật. Cấu hình mặc định trong service guide có checkpoint enabled, interval 60 giây và minimum pause 5 giây khi dùng default configuration. Giá trị thực tế cần kiểm tra theo runtime và cấu hình application.

### 8.2 Checkpoint barrier

Flink chèn checkpoint barrier vào stream. Barrier đi qua các operator để tạo một snapshot nhất quán giữa state và input position. Với operator có nhiều input, checkpoint alignment đảm bảo các input được snapshot tại cùng một logical point.

Nếu một input chậm, barrier phải chờ; checkpoint duration có thể tăng. Unaligned checkpoint có thể giảm alignment time trong một số workload nhưng có trade-off về state/checkpoint size và phải được xác minh theo hỗ trợ của service/runtime.

### 8.3 Checkpoint và savepoint khác nhau

| Khái niệm | Mục đích | Vòng đời |
|---|---|---|
| Checkpoint | Tự động phục hồi khi job lỗi | Runtime tạo theo interval; service quản lý |
| Savepoint | Điểm lưu state có chủ đích cho update, migration hoặc thao tác quản trị | Người vận hành/ứng dụng chủ động tạo và quản lý |
| Application snapshot (legacy) | Snapshot do Managed Service for Apache Flink quản lý, gắn với application | Chỉ application tạo nó có thể restore |
| Enhanced snapshot | Snapshot là AWS resource có ARN riêng, tồn tại độc lập với application | Có thể restore vào application enhanced snapshot mode cùng account/Region; có thể export/import S3 |
| System snapshot | Snapshot service tạo khi update/stop/scale theo snapshot mode | Dùng để bảo toàn state qua thao tác quản trị |

Trong tài liệu AWS, mỗi snapshot là một Apache Flink savepoint. Tuy nhiên, checkpoint tự động và snapshot/savepoint có mục tiêu, cách quản lý và retention khác nhau; không nên dùng tên thay thế cho nhau.

### 8.4 Legacy snapshot và enhanced snapshot

Managed Service for Apache Flink hỗ trợ hai snapshot mode:

- Application snapshots (legacy): snapshot thuộc application tạo ra và chỉ application đó restore được.
- Enhanced snapshots: mỗi snapshot có ARN độc lập, tồn tại sau khi application bị xóa; có thể restore vào application khác ở enhanced snapshot mode trong cùng account và Region, hoặc export/import qua S3.

Enhanced snapshots yêu cầu Apache Flink 1.20 trở lên. Application mới mặc định vẫn có thể ở legacy mode; muốn dùng enhanced mode phải chọn khi tạo hoặc upgrade application. Một application chỉ dùng một mode tại một thời điểm.

Khi xóa application, legacy snapshots của application bị xóa theo, nhưng enhanced snapshots vẫn tồn tại và tiếp tục phát sinh storage charge cho đến khi xóa snapshot riêng. Đây là điểm cần đưa vào quy trình cleanup và ngân sách.

### 8.5 System snapshot và exactly-once khi update

Khi snapshots được bật, Managed Service for Apache Flink có thể tạo system snapshot trong các thao tác như update, stop và một số thao tác thay đổi cấu hình. Tùy snapshot mode, hành vi khi scale/VPC/logging change có thể khác.

Nếu snapshots được cấu hình và application restore configuration trỏ đúng snapshot, dịch vụ có thể giữ semantics exactly-once trong quá trình update hoặc service-related scaling/maintenance. Force stop không tạo system snapshot; nó có thể gây mất hoặc xử lý trùng dữ liệu. Chỉ dùng force stop khi có runbook và chấp nhận hậu quả.

Với enhanced snapshot mode, AWS khuyến nghị tạo enhanced snapshot trước mỗi code release và chờ snapshot đạt trạng thái READY trước khi update. Hãy giữ snapshot đủ lâu để rollback theo chính sách, sau đó xóa snapshot cũ đã hết nhu cầu.

### 8.6 Tần suất snapshot

Snapshot nhiều lần trong ngày giúp khôi phục gần thời điểm lỗi hơn, nhưng làm tăng:

- Storage cost.
- Tài nguyên CPU/I/O trong quá trình snapshot.
- Checkpoint/snapshot duration.
- Rủi ro snapshot chồng lấn nếu state quá lớn.

Chọn tần suất theo RPO, business criticality, state size và thời gian restore. Không đặt snapshot interval quá ngắn nếu checkpoint chưa kịp hoàn tất hoặc application đang có backpressure.

### 8.7 Snapshot compatibility

Snapshot có thể không tương thích với code mới nếu thay đổi operator topology, operator UID, key type, serializer, state schema hoặc maxParallelism. Trước khi release:

1. Tạo snapshot từ version đang chạy.
2. Deploy code mới vào môi trường test.
3. Restore snapshot vào code mới.
4. Kiểm tra operator state mapping và dữ liệu state.
5. Chạy tiếp với dữ liệu đại diện và xác minh sink output.
6. Chỉ rollout production sau khi có rollback plan.

Nếu state không còn tương thích, có thể cần state migration, schema evolution, hoặc chủ động bỏ state cũ theo quyết định nghiệp vụ. Không dùng tùy chọn skip restore để che giấu lỗi tương thích nếu state đó chứa dữ liệu quan trọng.

## 9. Exactly-once và các giới hạn thực tế

### 9.1 Processing guarantee

Ba thuật ngữ thường gặp:

- **At-most-once:** record có thể mất nhưng không xử lý lặp.
- **At-least-once:** record không bị mất trong điều kiện phục hồi phù hợp nhưng có thể được xử lý nhiều lần.
- **Exactly-once:** mỗi hiệu ứng logic được phản ánh đúng một lần trong phạm vi guarantee của hệ thống.

Flink checkpointing giúp phục hồi state và source position. Tuy nhiên, exactly-once end-to-end còn phụ thuộc source connector, sink connector, transaction protocol và khả năng idempotency của đích.

### 9.2 Source, state và sink phải nhất quán

Giả sử Flink đọc transaction từ Kinesis, cập nhật state rồi ghi kết quả sang Kafka:

1. Source ghi nhận vị trí đọc trong checkpoint.
2. Operator state được snapshot cùng checkpoint.
3. Sink cần phối hợp commit để output không bị nhân đôi khi restore.
4. Khi lỗi, Flink khôi phục source position và state từ checkpoint.
5. Sink hoàn tất hoặc rollback transaction tương ứng.

Nếu sink chỉ ghi record trực tiếp mà không có transaction/idempotency, restart có thể phát lại output đã ghi trước khi checkpoint hoàn tất. Do đó, không khẳng định mọi sink mặc định exactly-once.

### 9.3 Transactional sink

Kafka connector hỗ trợ exactly-once semantics trong các cấu hình phù hợp, thường dùng transaction và yêu cầu cấu hình checkpointing. S3 FileSink có cơ chế commit file dựa trên checkpoint/committer. Kinesis sink và các connector khác có guarantee, giới hạn và cách cấu hình riêng.

Với API/database sink không hỗ trợ transaction chung với checkpoint, có thể dùng idempotent write, unique event ID, upsert theo key hoặc deduplication ở downstream.

### 9.4 Idempotency

Một thao tác idempotent cho cùng kết quả khi được thực hiện lặp. Ví dụ ghi trạng thái đơn hàng bằng upsert theo order_id và version có thể tránh tạo hai bản ghi do retry.

Đối với payment/fraud workflow:

- Dùng event_id duy nhất.
- Ghi trạng thái theo version/sequence.
- Dùng conditional write hoặc transaction ở downstream.
- Tách side effect không thể rollback khỏi pipeline chính.
- Đưa event lỗi vào DLQ/quarantine.

Exactly-once trong Flink không tự động bảo đảm email, SMS, webhook hoặc lệnh thanh toán chỉ phát một lần nếu hệ thống nhận không có cơ chế idempotency.

## 10. Kết nối nguồn và đích

### 10.1 Kinesis Data Streams source

Kinesis Data Streams là nguồn phổ biến cho Managed Service for Apache Flink. Kinesis source connector đọc record từ shard và chuyển thành DataStream. Cần cấu hình stream name/ARN, Region, initial position, credentials/role và connector version tương thích với Flink runtime.

Initial position thường là LATEST hoặc TRIM_HORIZON tùy connector. LATEST đọc record mới theo cấu hình; TRIM_HORIZON bắt đầu từ record còn lưu sớm nhất. Chọn sai initial position có thể bỏ qua lịch sử hoặc làm ứng dụng đọc lại backlog lớn.

Enhanced Fan-Out (EFO) cung cấp consumer throughput riêng cho consumer được đăng ký. Standard consumer chia sẻ read throughput của shard. EFO có thể hữu ích khi nhiều ứng dụng đọc cùng stream hoặc cần độ trễ ổn định; nó có chi phí riêng và cần đánh giá số consumer.

### 10.2 Amazon MSK/Kafka source

Kafka connector đọc topic/partition và offset. Cần xác định:

- Bootstrap brokers và authentication.
- Topic, consumer group và starting offsets.
- Partition assignment và parallelism.
- TLS/SASL/IAM authentication theo cluster.
- VPC networking, security group và DNS.
- Event timestamp và watermark strategy.

Nếu source partition bị idle hoặc partition skew, event-time watermark có thể chậm. Theo dõi lag theo partition và source subtask.

### 10.3 Sink

Các sink phổ biến:

| Sink | Use case | Điểm cần chú ý |
|---|---|---|
| Kinesis Data Streams | Chuyển kết quả sang stream khác hoặc downstream consumer | Partition key, shard capacity, throttling và connector guarantee |
| Amazon MSK/Kafka | Event bus, microservices, data integration | Transactional sink, topic partition, authentication |
| Amazon S3 | Data lake, archive, analytics | File rolling, checkpoint commit, partitioning và small files |
| Amazon Data Firehose | Delivery managed đến S3, Redshift, OpenSearch hoặc destination hỗ trợ | Buffering, retry, transformation và service cost |
| JDBC/database | Upsert hoặc serving table | Connection pool, batch, transaction và idempotency |

### 10.4 Connector compatibility

Connector version phải tương thích với Flink runtime version và Java dependencies. Không copy một connector JAR từ phiên bản Flink khác chỉ vì package name giống nhau. Kiểm tra matrix connector của AWS cho runtime đang chọn, đặc biệt khi upgrade từ Flink 1.x sang 2.x.

Một lưu ý khi nâng cấp Kinesis connector: FlinkKinesisConsumer và KinesisStreamsSource không có state compatibility. Migration phải có kế hoạch offset/state riêng, không giả định snapshot cũ restore trực tiếp sang source connector mới.

### 10.5 Source retention và replay

Checkpoint không thay thế retention của source. Nếu application downtime lâu hơn retention của Kinesis/MSK, source có thể không còn dữ liệu để replay. Hãy thiết kế retention đủ dài cho RTO, backfill và incident recovery. Với Kinesis, retention có giới hạn theo cấu hình stream; MSK phụ thuộc log retention và disk capacity.

## 11. Scaling, parallelism và KPU

### 11.1 Parallelism

Parallelism là số subtask chạy song song cho operator/job. Nhiều partition hoặc key giúp phân phối workload; parallelism quá thấp có thể tạo bottleneck, còn quá cao có thể tăng overhead, network shuffle và checkpoint cost.

Trong Managed Service for Apache Flink:

- Parallelism là số task song song của ứng dụng.
- ParallelismPerKPU là số task slots có thể schedule trên mỗi KPU.
- Số KPU cần thiết liên quan đến Parallelism chia cho ParallelismPerKPU.

ParallelismPerKPU mặc định là 1 và có thể tăng đến 8 theo tài liệu scaling. Tăng giá trị có thể tận dụng KPU tốt hơn với workload có blocking I/O, nhưng không tự tăng throughput nếu bottleneck là CPU, source partition hoặc sink.

### 11.2 Operator parallelism

Mỗi operator có thể override parallelism. Tăng application parallelism mà giữ một operator quan trọng ở parallelism thấp vẫn có thể tạo bottleneck. Ví dụ source có 16 subtasks nhưng enrichment operator chỉ 1 subtask, tất cả record vẫn phải qua một điểm tuần tự.

Kiểm tra:

- Source parallelism so với số shard/partition.
- Key distribution và hot key.
- Operator busy/backpressure.
- Sink throughput và transaction commit.
- Serialization, network shuffle và state size.

### 11.3 maxParallelism

maxParallelism là giới hạn parallelism mà job có thể đạt khi giữ state. Keyed state được phân thành key groups; khi rescale, key groups được phân phối lại giữa subtasks.

Nếu không cấu hình rõ, default maxParallelism có thể là 128 khi ứng dụng bắt đầu với parallelism không vượt 128. Nếu muốn scale lớn hơn, phải đặt maxParallelism phù hợp từ đầu.

Thay đổi maxParallelism của application hiện có làm snapshot cũ không còn tương thích để restore theo quy tắc AWS. Đây là quyết định kiến trúc quan trọng; hãy chọn giới hạn dự kiến trước khi production.

### 11.4 Autoscaling

Managed Service for Apache Flink autoscaling dựa trên CPU utilization. Theo tài liệu hiện hành, nếu CPU trên 75% trong 15 phút và autoscaling bật, dịch vụ có thể tăng parallelism/capacity. Autoscaling không tự phản ứng với mọi metric như heap memory utilization, source lag hoặc backpressure.

Nếu bottleneck là memory, skew, I/O hoặc sink, tăng KPU tự động có thể không giải quyết được. Cần kiểm tra operator parallelism, key distribution, memory, checkpoint duration và downstream capacity.

### 11.5 Kinesis Processing Unit

Một KPU gồm 1 vCPU compute và 4 GB memory. Dịch vụ dùng KPU để biểu diễn capacity xử lý. Mỗi Apache Flink application còn bị tính thêm một KPU cho orchestration theo pricing model hiện hành.

KPU không thể quy đổi trực tiếp từ records/second mà không benchmark. Throughput phụ thuộc:

- Record size và schema complexity.
- Số operator và transformation.
- State size, key cardinality và window.
- Serialization/compression.
- Source/sink latency và I/O.
- Machine learning hoặc cryptographic computation.
- Parallelism và data skew.

Hãy chạy load test bằng dữ liệu có kích thước và phân phối gần production. Theo dõi CPU, heap, backpressure, checkpoint và source lag để xác định capacity.

## 12. Triển khai ứng dụng

### 12.1 Quy trình Java DataStream

Một quy trình triển khai phổ biến:

1. Tạo Kinesis Data Streams/MSK source và destination.
2. Tạo S3 bucket chứa application package.
3. Phát triển Java application với Flink API và connector tương thích.
4. Test local bằng dữ liệu đại diện.
5. Build fat JAR chứa application và dependency cần thiết.
6. Upload JAR lên S3.
7. Tạo Managed Service for Apache Flink application và chọn runtime version.
8. Cấp service execution role.
9. Cấu hình checkpoint/snapshot, parallelism, environment properties, logging và VPC.
10. Start application, theo dõi trạng thái và CloudWatch metrics.
11. Gửi test record và xác minh sink output.

AWS getting-started tutorial sử dụng JDK 11 và Maven cho ví dụ DataStream Java; runtime/SDK version hiện hành có thể hỗ trợ hoặc yêu cầu phiên bản khác. Luôn đối chiếu runtime version đang chọn với Developer Guide và connector compatibility matrix.

### 12.2 Fat JAR và dependency

Ứng dụng phải được đóng gói cùng dependency cần thiết trong fat JAR/uber JAR. Cần tránh:

- Đóng gói nhầm Flink runtime dependency mà service đã cung cấp.
- Trùng phiên bản Jackson/Netty/connector.
- Shade service loader metadata sai.
- Thiếu connector hoặc serializer lúc chạy.
- JAR vượt giới hạn kích thước hỗ trợ.

Build và chạy local với đúng dependency/runtime profile trước khi upload.

### 12.3 Cấu hình application

Application cần:

- Application name và runtime environment.
- Code package S3 location/version.
- Service execution role ARN.
- Environment properties.
- Parallelism configuration.
- Checkpointing và snapshot configuration.
- VPC configuration nếu cần truy cập resource private.
- CloudWatch logging options.

Nếu tạo application bằng console, một số dependent resource như IAM role và CloudWatch log stream có thể được tạo cho bạn. Nếu dùng CLI/API, người vận hành phải tạo và cấp quyền các resource liên quan.

### 12.4 Java code deployment

Ví dụ lệnh build và upload mang tính minh họa:

    mvn clean package
    aws s3 cp target/stream-job.jar s3://my-flink-artifacts/releases/stream-job-1.0.0.jar

Sau khi upload, tạo application bằng console, CloudFormation hoặc AWS CLI/API. Nên dùng object versioning hoặc tên artifact bất biến để biết chính xác binary đang chạy.

Không ghi access key vào source code hoặc environment properties. Dùng IAM execution role và policy theo least privilege.

## 13. Bảo mật và network

### 13.1 Service execution role

Managed Service for Apache Flink assume service execution role để truy cập AWS resource. Role cần:

- Trust policy cho service principal tương ứng theo tài liệu AWS.
- Quyền đọc source stream/topic.
- Quyền ghi sink.
- Quyền đọc application package từ S3.
- Quyền ghi CloudWatch Logs.
- Quyền dùng KMS nếu stream, bucket hoặc secret được mã hóa bằng customer managed key.
- Quyền network/VPC integration theo cấu hình.

Tách role theo application và môi trường. Không cấp quyền administrator để giải quyết nhanh AccessDenied.

### 13.2 VPC access

Nếu source/sink nằm trong private subnet, cấu hình VPC, subnet và security group cho application. Kiểm tra route, DNS, NAT hoặc VPC endpoint, security group ingress/egress và NACL.

Managed Service for Apache Flink chạy trong hạ tầng AWS quản lý; việc gắn VPC configuration không đồng nghĩa application có thể truy cập mọi resource private. Phải kiểm tra connectivity thực tế và IAM permission riêng.

### 13.3 Encryption và secrets

Sử dụng TLS cho kết nối Kafka/MSK, database và endpoint hỗ trợ. Dùng KMS cho encryption at rest theo resource policy. Credential bên ngoài nên lưu trong AWS Secrets Manager hoặc cơ chế được hỗ trợ; không ghi password vào JAR, source code hoặc log.

Nếu thay đổi KMS key policy, kiểm tra application role và service principal có quyền decrypt/encrypt cần thiết. Một key bị disable hoặc policy bị sửa có thể làm application không đọc source/sink hoặc không phục hồi state.

### 13.4 Data privacy

Stateful stream có thể giữ PII, payment metadata hoặc hành vi người dùng trong state và snapshot. Hãy:

- Giảm dữ liệu nhạy cảm được lưu trong state.
- Đặt TTL và retention phù hợp.
- Hạn chế quyền xem snapshot/log.
- Mã hóa dữ liệu và bảo vệ bucket.
- Không ghi payload đầy đủ vào debug log.
- Xây dựng quy trình xóa dữ liệu theo yêu cầu pháp lý nếu state chứa thông tin định danh.

## 14. Monitoring và vận hành

### 14.1 Metrics quan trọng

Theo dõi CloudWatch metrics của application và Flink:

| Metric | Ý nghĩa | Dấu hiệu cần điều tra |
|---|---|---|
| CPU utilization | Mức sử dụng compute | Cao kéo dài, gần saturation |
| heapMemoryUtilization | Mức sử dụng JVM heap | Tăng liên tục, gần giới hạn |
| backPressuredTimeMsPerSecond | Thời gian task bị backpressure | Tăng ở operator hoặc downstream |
| busyTimeMsPerSecond | Thời gian task bận | Cao nhưng output thấp |
| idleTimeMsPerSecond | Thời gian task idle | Có thể thiếu input hoặc bottleneck upstream |
| lastCheckpointDuration | Thời gian checkpoint gần nhất | Tăng dần, gần timeout |
| lastCheckpointSize | Kích thước checkpoint | Tăng bất thường do state growth |
| numRecordsIn/Out | Throughput record | Input tăng nhưng output giảm |
| currentInputWatermark | Watermark hiện tại | Đứng yên do idle partition hoặc event-time issue |
| downtime | Thời gian ứng dụng gián đoạn | Tăng khi restart hoặc failure |

Metric names và dimensions phụ thuộc runtime/monitoring level. Bật mức monitoring phù hợp; mức Debug hoặc Parallelism quá chi tiết có thể tạo log/metric overhead và làm tăng backpressure.

### 14.2 Backpressure

Backpressure xảy ra khi operator downstream không tiêu thụ kịp output từ upstream. Nguồn có thể bị chậm lại vì buffer đầy.

Nguyên nhân phổ biến:

- Sink ghi chậm hoặc throttling.
- Operator xử lý CPU-intensive.
- Key skew khiến một subtask nhận quá nhiều record.
- Serialization/deserialization nặng.
- Network shuffle hoặc external I/O chậm.
- Logging quá nhiều, đặc biệt log mỗi record.

Cách điều tra:

1. Xác định operator/subtask có backpressure cao.
2. So sánh busy, idle, input và output rate.
3. Kiểm tra sink latency/throttle.
4. Kiểm tra key distribution và hot key.
5. Xem CPU, heap, GC và checkpoint duration.
6. Tối ưu logic hoặc sink trước khi chỉ tăng parallelism.

### 14.3 Checkpoint failure

Checkpoint có thể fail do:

- State quá lớn hoặc checkpoint duration vượt timeout.
- Backpressure khiến barrier không đến kịp.
- Sink/source permission hoặc network lỗi.
- Serializer/schema không tương thích.
- Snapshot quota hoặc storage issue.
- Operator không được provision đủ.

Kiểm tra lastCheckpointDuration, lastCheckpointSize, checkpoint alignment/start delay và log. Nếu checkpoint không thành công, khả năng phục hồi có thể lùi về checkpoint thành công gần nhất, làm tăng replay và data lag.

### 14.4 Logging

Application log cần tập trung vào lifecycle, warning, error, state migration, connector exception và business event quan trọng. Không ghi một log entry cho mỗi record ở throughput cao. Log quá nhiều có thể tạo bottleneck, tăng CloudWatch ingestion cost và gây backpressure.

Khi log không xuất hiện, kiểm tra execution role có quyền PutLogEvents, DescribeLogGroups và DescribeLogStreams; kiểm tra application đang chạy và CloudWatch log stream được cấu hình đúng.

### 14.5 Alarm và runbook

Đặt CloudWatch alarm cho:

- Application downtime hoặc status không RUNNING.
- CPU utilization cao kéo dài.
- Backpressure cao.
- Checkpoint duration gần timeout hoặc checkpoint failure.
- Source lag tăng.
- Watermark đứng yên.
- Sink error/throttle.
- State/checkpoint size tăng nhanh.

Mỗi alarm cần owner, severity, dashboard và runbook. Không dùng CPU đơn lẻ để quyết định application khỏe; một application có CPU thấp nhưng source lag tăng có thể đang bị nghẽn ở connector hoặc sink.

## 15. Troubleshooting tình huống thường gặp

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| Application không start | JAR lỗi, dependency conflict, IAM role thiếu quyền, runtime không tương thích | Đọc application error, kiểm tra artifact và execution role |
| Không đọc được Kinesis | Stream ARN/Region sai, IAM deny, initial position hoặc connector config sai | Kiểm tra source config, role và stream status |
| Không kết nối được MSK | Security group, subnet, DNS, TLS/SASL hoặc bootstrap broker | Kiểm tra VPC route và authentication |
| Watermark không tiến | Idle shard, event timestamp lỗi, source subtask bị chậm | Dùng idleness, kiểm tra timestamp và source lag |
| Window không phát kết quả | Watermark chưa vượt end time, late event hoặc trigger sai | Kiểm tra watermark và allowed lateness |
| State tăng liên tục | Key cardinality cao, TTL thiếu, window quá dài, timer không cleanup | Giới hạn state, TTL và timer |
| Checkpoint thất bại | Backpressure, state lớn, timeout, sink/source issue | Kiểm tra checkpoint metrics và operator bottleneck |
| CPU thấp nhưng lag cao | Sink I/O, hot key, source partition hoặc memory bottleneck | Kiểm tra backpressure, heap, parallelism và partition |
| Application update bị treo | Snapshot fail, state incompatibility, code/package lỗi | Xem status, snapshot và rollback option |
| Restore snapshot thất bại | Flink version, operator UID, serializer, maxParallelism không tương thích | Test restore trước release, migration state có kế hoạch |
| Output bị trùng | Sink không transactional/idempotent hoặc force stop | Dùng transaction, event ID và deduplication |
| Output bị thiếu | Checkpoint/snapshot không đúng, source retention hết, sink commit lỗi | Kiểm tra source position, restore point và sink transaction |

Nếu application ở trạng thái transient như STARTING, UPDATING, STOPPING hoặc AUTOSCALING quá lâu, đọc troubleshooting guide trước khi force stop. Force stop có thể làm mất hoặc lặp dữ liệu. Với ứng dụng có snapshot, rollback về version trước có thể khôi phục từ snapshot thành công gần nhất.

## 16. Chi phí Managed Service for Apache Flink

### 16.1 KPU-hour

Chi phí compute dựa trên số KPU và thời gian application chạy. Một KPU gồm 1 vCPU và 4 GB RAM. Dịch vụ tính thêm một KPU mỗi application cho orchestration đối với Apache Flink application.

Managed Service for Apache Flink hiện tính theo giây ở Region được hỗ trợ, với mức tối thiểu 10 phút cho mỗi lần application start. Vì vậy, một job chạy 2 phút vẫn có thể bị tính mức tối thiểu 10 phút cho lần start đó. Kiểm tra pricing page theo Region trước khi dự toán.

### 16.2 Running application storage

Dịch vụ tính phí running application storage dùng cho stateful processing. AWS pricing guidance nêu allocation theo KPU và đơn giá GB-month; application đang chạy có mức tối thiểu storage theo FAQ. Khi ước tính, không bỏ qua storage chỉ vì state nhỏ hoặc stream đang idle.

### 16.3 Durable backup storage

Durable application backups/snapshots tùy chọn được tính theo GB-month. Enhanced snapshots tồn tại sau khi application bị xóa, nên phải có retention/cleanup policy. Import/export snapshot có quy tắc giá riêng theo tài liệu pricing hiện hành.

### 16.4 Chi phí dịch vụ phụ thuộc

Managed Service for Apache Flink không bao gồm chi phí của source và sink:

- Kinesis Data Streams shard/on-demand throughput và data retrieval.
- MSK broker, storage, network và data transfer.
- S3 storage, request và lifecycle.
- Data Firehose ingestion/delivery.
- CloudWatch Logs và metrics.
- VPC NAT Gateway, endpoint và data transfer.
- KMS, Secrets Manager và các dịch vụ downstream.

### 16.5 Tối ưu chi phí

- Chọn parallelism/KPU theo benchmark thay vì provision dư.
- Dùng autoscaling khi workload biến động và logic phù hợp.
- Không giữ Studio notebook ở interactive mode khi không phát triển.
- Dừng application batch sau khi hoàn thành, lưu ý minimum 10 phút mỗi start.
- Giảm state size và TTL đúng nghiệp vụ.
- Giữ snapshot theo RPO/rollback policy, xóa enhanced snapshot đã hết nhu cầu.
- Tránh debug logging trong production.
- Tối ưu source/sink batching và network path.
- Theo dõi cost theo application, Region và workload.

## 17. Thiết kế tham khảo: phát hiện gian lận giao dịch

### 17.1 Yêu cầu

Một hệ thống thanh toán nhận giao dịch từ nhiều kênh. Mỗi record có transaction_id, account_id, amount, merchant_id, event_time và device_id. Hệ thống muốn cảnh báo khi một account có quá nhiều giao dịch hoặc tổng amount vượt ngưỡng trong cửa sổ 5 phút.

### 17.2 Pipeline

    Payment producers
          |
    Kinesis Data Streams
          |
    Managed Service for Apache Flink
          |
    Parse + validate schema
          |
    Assign event time + watermark
          |
    keyBy(account_id)
          |
    5-minute event-time window
          |
    Count + sum + velocity rules
          |
      +---+----------------+
      |                    |
      v                    v
    Fraud alerts        Aggregated metrics
      |                    |
    EventBridge/SNS      S3 / MSK

### 17.3 State design

State theo account_id có thể giữ:

- Số giao dịch trong window.
- Tổng amount.
- Số merchant khác nhau.
- Số device khác nhau.
- Timestamp giao dịch gần nhất.

Không lưu toàn bộ raw transaction nếu chỉ cần aggregate. Nếu cần audit, lưu raw event riêng vào S3/Kinesis archive.

### 17.4 Fault tolerance

Checkpoint lưu keyed state và source progress. Snapshot trước deployment cho phép rollback code. Sink alert nên có transaction hoặc idempotency key theo transaction_id/rule_id để tránh gửi cảnh báo trùng sau restart.

### 17.5 Scale và hot key

Account có volume cao có thể trở thành hot key. Tăng parallelism toàn ứng dụng không tách được cùng một key nếu logic cần tuần tự hóa state của key đó. Có thể dùng two-stage aggregation, salting hoặc partition strategy nếu nghiệp vụ cho phép, sau đó merge kết quả.

### 17.6 Late event

Watermark delay 30 giây và allowed lateness 2 phút là một ví dụ cấu hình ban đầu. Cần benchmark và đánh giá false positive/false negative. Giao dịch đến quá trễ có thể đi side output để đối soát thay vì bị loại im lặng.

## 18. Lab: xử lý stream có trạng thái với Kinesis

### Mục tiêu

Tạo một ứng dụng Flink đọc giao dịch từ Kinesis, đếm theo account, ghi kết quả sang stream đích và quan sát checkpoint/recovery.

### Chuẩn bị

- AWS account và Region lab.
- Kinesis Data Streams input/output.
- S3 bucket lưu JAR.
- Java JDK và Maven phù hợp với runtime được chọn.
- IAM execution role có quyền source, sink, S3 artifact và CloudWatch Logs.
- AWS CLI hoặc console.

### Bước 1: Tạo stream

Tạo hai stream, ví dụ input-transactions và output-account-count. Chọn capacity phù hợp với lab và Region. Không dùng dữ liệu thanh toán thật.

### Bước 2: Viết ứng dụng

1. Tạo Maven project với Flink runtime và Kinesis connector tương thích.
2. Định nghĩa Event schema có account_id, transaction_id và event_time.
3. Tạo Kinesis source.
4. Parse record và loại dữ liệu sai.
5. Gán timestamp/watermark.
6. keyBy(account_id).
7. Dùng ValueState hoặc window aggregate để đếm.
8. Ghi kết quả sang Kinesis sink.
9. Bật checkpointing và log lifecycle/error.

### Bước 3: Test local

1. Chạy ứng dụng trong IDE hoặc local runner.
2. Gửi nhiều record có account_id lặp lại.
3. Xác nhận counter tăng theo từng account.
4. Gửi record out-of-order và quan sát watermark/window.
5. Kiểm tra sink output.

### Bước 4: Deploy

1. Build fat JAR.
2. Upload JAR lên S3.
3. Tạo Managed Service for Apache Flink application.
4. Chọn runtime và service execution role.
5. Cấu hình source/sink properties.
6. Bật checkpointing và snapshot theo yêu cầu.
7. Start application và quan sát CloudWatch metrics.

### Bước 5: Kiểm thử phục hồi

Trong môi trường lab:

1. Gửi dữ liệu và ghi nhận output.
2. Chờ checkpoint thành công.
3. Thực hiện một lần restart/stop theo quy trình có snapshot.
4. Start lại và kiểm tra state/counter.
5. So sánh output để phát hiện mất hoặc trùng record.
6. Tạo snapshot trước khi thử thay đổi code.

Không force stop application có state cần giữ nếu chưa chấp nhận rủi ro mất/trùng dữ liệu.

### Bước 6: Kiểm tra vận hành

- Quan sát CPU, heap, input/output records và backpressure.
- Xem lastCheckpointDuration và lastCheckpointSize.
- Kiểm tra source lag và sink throughput.
- Thử tăng parallelism trong lab.
- Kiểm tra application vẫn restore được từ snapshot sau thay đổi.

### Bước 7: Dọn lab

Stop/delete application theo quy trình. Xóa enhanced snapshots không còn cần thiết. Xóa stream, S3 artifact và log group theo chính sách lab. Kiểm tra Kinesis, S3 và CloudWatch không còn tài nguyên tính phí ngoài dự kiến.

## 19. Câu hỏi tự kiểm tra

**Câu 1.** Stateful stream processing khác stateless ở đâu?

**Đáp án:** Stateful operator giữ state qua nhiều record, ví dụ counter theo account; stateless operator xử lý từng record độc lập.

**Câu 2.** Khi nào dùng keyed state?

**Đáp án:** Khi cần state riêng cho từng business key như account_id, customer_id hoặc device_id sau keyBy.

**Câu 3.** Operator state khác keyed state thế nào?

**Đáp án:** Operator state gắn với operator/subtask; keyed state được phân vùng theo key và tự phân phối qua key groups khi rescale.

**Câu 4.** Watermark dùng để làm gì?

**Đáp án:** Báo tiến độ event time để window/operator quyết định khi nào có thể xử lý hoặc đóng dữ liệu theo thời gian.

**Câu 5.** Vì sao idle shard có thể làm window không đóng?

**Đáp án:** Watermark downstream có thể bị giữ bởi input subtask không phát watermark mới; idleness giúp loại subtask idle khỏi phép tính.

**Câu 6.** Checkpoint khác savepoint thế nào?

**Đáp án:** Checkpoint phục vụ fault recovery tự động; savepoint/snapshot được tạo có chủ đích để update, migration hoặc quản trị.

**Câu 7.** Enhanced snapshot khác legacy snapshot thế nào?

**Đáp án:** Enhanced snapshot có ARN riêng và tồn tại độc lập với application; legacy snapshot gắn với application tạo ra.

**Câu 8.** Enhanced snapshots yêu cầu runtime Flink tối thiểu nào?

**Đáp án:** Apache Flink 1.20 trở lên theo tài liệu AWS hiện hành.

**Câu 9.** Checkpointing có tự đảm bảo exactly-once end-to-end không?

**Đáp án:** Không. Source, sink, transaction và idempotency phải phối hợp để bảo đảm output không mất hoặc trùng.

**Câu 10.** Vì sao force stop có rủi ro?

**Đáp án:** Force stop không tạo system snapshot; restart có thể mất hoặc xử lý trùng dữ liệu.

**Câu 11.** maxParallelism ảnh hưởng điều gì?

**Đáp án:** Giới hạn parallelism có thể đạt khi giữ state; thay đổi maxParallelism có thể làm snapshot cũ không restore được.

**Câu 12.** Autoscaling của Managed Service for Apache Flink dựa trên metric nào?

**Đáp án:** CPU utilization; theo tài liệu hiện hành, CPU trên 75% trong 15 phút có thể kích hoạt scale khi autoscaling bật.

**Câu 13.** Vì sao tăng KPU không luôn giải quyết backpressure?

**Đáp án:** Bottleneck có thể nằm ở sink, hot key, memory, network hoặc operator parallelism; autoscaling không phản ứng với mọi metric.

**Câu 14.** Một KPU gồm những tài nguyên nào?

**Đáp án:** 1 vCPU compute và 4 GB memory.

**Câu 15.** Vì sao connector version phải khớp Flink runtime?

**Đáp án:** API/serializer/runtime dependency có thể khác; connector không tương thích có thể làm application không build hoặc không start.

**Câu 16.** Event-time window xử lý late event như thế nào?

**Đáp án:** Theo watermark, allowed lateness, side output hoặc correction policy do ứng dụng cấu hình.

**Câu 17.** Vì sao không log mọi record trong production?

**Đáp án:** Log volume có thể tạo bottleneck, tăng CloudWatch cost và gây backpressure.

**Câu 18.** Khi application bị lag nhưng CPU thấp, nên kiểm tra gì?

**Đáp án:** Source partition, sink throughput, backpressure, memory, hot key và network/I/O.

**Câu 19.** Enhanced snapshot có tự bị xóa khi delete application không?

**Đáp án:** Không. Enhanced snapshot tồn tại độc lập và phải xóa riêng khi hết nhu cầu.

**Câu 20.** Những khoản nào ngoài KPU cần tính khi dự toán?

**Đáp án:** Orchestration KPU, running application storage, durable backup storage, source/sink, Kinesis/MSK, S3, CloudWatch, VPC và data transfer.

## 20. Checklist production readiness

- [ ] Chọn DataStream API hoặc Table API/SQL theo logic nghiệp vụ.
- [ ] Source/sink connector tương thích runtime.
- [ ] Event schema có version và xử lý dữ liệu lỗi.
- [ ] Key phân phối hợp lý, không có hot key không kiểm soát.
- [ ] State size, TTL và timer lifecycle được thiết kế.
- [ ] Event time, watermark, idleness và late-event policy rõ ràng.
- [ ] Checkpointing bật và interval/timeout phù hợp.
- [ ] Snapshot mode, retention và rollback procedure được phê duyệt.
- [ ] Enhanced snapshot compatibility đã được test nếu sử dụng.
- [ ] Exactly-once end-to-end được xác minh với source/sink thực tế.
- [ ] Idempotency key hoặc deduplication cho external side effect.
- [ ] Parallelism, maxParallelism và ParallelismPerKPU được chọn trước production.
- [ ] Autoscaling được test với CPU và non-CPU bottleneck.
- [ ] IAM execution role theo least privilege.
- [ ] VPC, security group, route, DNS và KMS policy đã được kiểm tra.
- [ ] CloudWatch logs/metrics/alarms có owner và runbook.
- [ ] Backpressure, checkpoint failure, source lag và sink throttle có quy trình xử lý.
- [ ] RPO/RTO và source retention đủ cho replay/recovery.
- [ ] KPU, orchestration, running storage, snapshots và source/sink cost được dự toán.
- [ ] Enhanced snapshots cũ được dọn theo retention policy.

## 21. Tài liệu tham khảo chính thức

1. [Amazon Managed Service for Apache Flink Documentation](https://docs.aws.amazon.com/managed-flink/) — tổng quan dịch vụ, API và Developer Guide.
2. [Get started with the DataStream API](https://docs.aws.amazon.com/managed-flink/latest/java/getting-started.html) — ứng dụng Java, Maven và môi trường phát triển.
3. [Get started with Table API and SQL](https://docs.aws.amazon.com/managed-flink/latest/java/gs-table.html) — SQL/Table API.
4. [Add streaming data sources](https://docs.aws.amazon.com/managed-flink/latest/java/how-sources.html) — Kinesis và MSK source.
5. [Write data using sinks](https://docs.aws.amazon.com/managed-flink/latest/java/how-sinks.html) — Kinesis, Kafka/MSK, S3 và Firehose sink.
6. [Implement fault tolerance](https://docs.aws.amazon.com/managed-flink/latest/java/how-fault.html) — checkpoint và fault recovery.
7. [Manage application backups using snapshots](https://docs.aws.amazon.com/managed-flink/latest/java/how-snapshots.html) — legacy/enhanced snapshot và system snapshot.
8. [How enhanced snapshots work](https://docs.aws.amazon.com/managed-flink/latest/java/snapshots-how-it-works.html) — snapshot mode và lifecycle.
9. [Implement application scaling](https://docs.aws.amazon.com/managed-flink/latest/java/how-scaling.html) — parallelism, maxParallelism và autoscaling.
10. [Review application resources](https://docs.aws.amazon.com/managed-flink/latest/java/how-resources.html) — KPU và task slots.
11. [Track events using the DataStream API](https://docs.aws.amazon.com/managed-flink/latest/java/how-time.html) — processing/ingestion/event time.
12. [Maintain best practices](https://docs.aws.amazon.com/managed-flink/latest/java/best-practices.html) — checkpoint, watermark và hiệu năng.
13. [Troubleshoot performance issues](https://docs.aws.amazon.com/managed-flink/latest/java/performance-troubleshooting.html) — CPU, parallelism, logging và backpressure.
14. [Troubleshoot checkpoint issues](https://docs.aws.amazon.com/managed-flink/latest/java/troubleshooting-checkpoints.html) — checkpoint stages và failure.
15. [Set up application logging](https://docs.aws.amazon.com/managed-flink/latest/java/cloudwatch-logs.html) — CloudWatch Logs và IAM permissions.
16. [Managed Service for Apache Flink pricing](https://aws.amazon.com/managed-service-apache-flink/pricing/) — KPU, running storage và durable backups.
17. [Managed Service for Apache Flink FAQs](https://aws.amazon.com/managed-service-apache-flink/faqs/) — minimum usage, KPU và billing.
18. [Use Flink connectors](https://docs.aws.amazon.com/managed-flink/latest/java/how-flink-connectors.html) — connector/runtime compatibility.

---

**Kết luận:** Stateful stream processing cần phối hợp đúng giữa key, state, event time, watermark, checkpoint và sink semantics. Managed Service for Apache Flink giảm gánh nặng quản lý runtime, nhưng độ tin cậy vẫn phụ thuộc vào thiết kế state, tương thích snapshot, parallelism, connector, IAM và quy trình vận hành. Hãy kiểm thử phục hồi và exactly-once bằng workload thực trước khi đưa ứng dụng streaming quan trọng vào production.
