# Reset ứng dụng Streams và hậu quả đối với dữ liệu, trạng thái

Reset một Kafka Streams application có thể khiến dữ liệu đầu vào được đọc lại, state store được dựng lại và output được ghi thêm lần nữa. Vì vậy, reset là một thao tác thay đổi trạng thái xử lý trên nhiều nơi: Kafka input topics, consumer offsets, internal topics, state directory cục bộ và các hệ thống downstream.

Không có một lệnh duy nhất xóa sạch mọi dấu vết của ứng dụng. Kafka Streams cung cấp công cụ reset offset và internal topics; local state trên từng máy phải được xử lý riêng; output topics và side effect bên ngoài cần kế hoạch riêng.

Bài học này phân biệt restart thông thường, xóa local state, reset toàn bộ ứng dụng và đổi application ID. Sau đó, bài hướng dẫn chọn công cụ đúng theo rebalance protocol, đánh giá hậu quả đối với dữ liệu và thực hiện reset có kiểm soát.

## 1. Reset Kafka Streams thực sự có nghĩa gì?

Kafka Streams application được nhận diện bằng application ID. Giá trị này được dùng làm consumer group ID, prefix của internal topics và thư mục con trong state directory. Tất cả instance của cùng một logical application phải dùng chung application ID.

Một ứng dụng stateful thường sử dụng các tài nguyên sau:

- **Input topics:** chứa event đầu vào mà topology đọc.
- **Output topics:** chứa kết quả mà topology phát ra.
- **Intermediate topics:** topic người dùng dùng làm điểm trung gian giữa các phần pipeline, nếu có.
- **Internal topics:** changelog topics lưu thay đổi của state store và repartition topics dùng để phân vùng lại dữ liệu.
- **Committed offsets:** vị trí xử lý đã xác nhận cho input partitions.
- **Local state directory:** state store trên disk của từng instance, thường dùng RocksDB hoặc store implementation khác.
- **External systems:** database, HTTP API, object storage hoặc dịch vụ khác mà processor có thể gọi.

~~~mermaid
flowchart TB
    A["Input topics"] --> B["Kafka Streams application"]
    B --> C["Local state stores"]
    C <--> D["Changelog topics"]
    B --> E["Repartition topics"]
    E --> B
    B --> F["Output topics"]
    F --> G["Downstream applications"]
    B --> H["External side effects"]
    I["Committed input offsets"] --> B
~~~

Reset có thể tác động đến một số tài nguyên trong sơ đồ nhưng không tự động xóa tất cả. Trước khi chạy lệnh, phải xác định chính xác muốn thay đổi offset, state store, internal topics hay cả output.

## 2. Phân biệt restart, local cleanup và full reset

Các thao tác dưới đây có hậu quả khác nhau.

| Thao tác | Input offsets | Internal topics | Local state | Output topics |
|---|---|---|---|---|
| Restart process bình thường | Giữ nguyên | Giữ nguyên | Giữ lại và tiếp tục dùng | Giữ nguyên |
| KafkaStreams.cleanUp() | Không reset | Giữ nguyên | Xóa local state của application | Giữ nguyên |
| Application Reset Tool kiểu classic | Reset input offsets theo lựa chọn và xóa internal topics | Xóa | Không tự xóa | Không xóa |
| Streams Groups CLI | Reset input offsets; có thể xóa internal topics khi được chỉ định | Tùy chọn | Không tự xóa | Không xóa |
| Đổi application.id | Tạo group/resource namespace mới | Topic cũ còn tồn tại; app mới tạo topic riêng | Dùng thư mục state riêng | Giữ nguyên |
| Xóa output topic thủ công | Không thay đổi | Không thay đổi | Không thay đổi | Topic được chọn bị xóa |

### 2.1. Restart thông thường

Khi process dừng rồi khởi động lại với cùng application ID:

- Kafka Streams đọc committed offsets hiện có.
- Internal changelog và repartition topics vẫn tồn tại.
- Local state store có thể được tái sử dụng.
- Nếu local state không còn hoặc task được giao sang máy khác, state có thể được phục hồi từ changelog.
- Output tiếp tục được ghi theo processing flow.

Restart không phải reset. Đây là thao tác vận hành thường ngày khi deploy bản vá hoặc khởi động lại process.

### 2.2. Chỉ xóa local state

KafkaStreams.cleanUp() xóa local state store trong state directory của application. Nó không reset committed input offsets và không xóa changelog topics trên broker.

Khi application chạy lại, state store có thể được restore từ changelog. Vì vậy, xóa local state thường làm tăng thời gian khởi động và state restoration, nhưng không có nghĩa toàn bộ input topic được đọc lại từ đầu.

### 2.3. Reset toàn bộ trạng thái xử lý

Một full reset thường cần phối hợp nhiều bước:

1. Dừng tất cả application instances.
2. Reset input offsets đến vị trí mong muốn.
3. Xóa internal topics chứa state/repartition theo kế hoạch.
4. Xóa local state directory trên tất cả máy hoặc volume đã chạy instance.
5. Quyết định cách xử lý output topics và downstream consumers.
6. Khởi động lại application và theo dõi quá trình rebuild.

Nếu bỏ sót local state, application có thể dùng dữ liệu cục bộ cũ. Nếu xóa internal topics nhưng giữ input offsets ở vị trí hiện tại, state store sẽ được dựng lại chỉ từ các event mới sau vị trí đó, dẫn đến trạng thái không đầy đủ.

## 3. application.id liên kết những tài nguyên nào?

Ví dụ:

~~~properties
application.id=orders-enrichment-v1
bootstrap.servers=kafka-1:9092,kafka-2:9092
state.dir=/var/lib/kafka-streams
~~~

Với cấu hình trên, application ID được dùng làm:

- Consumer group ID để phối hợp xử lý.
- Prefix cho client IDs mặc định.
- Prefix cho tên internal topics.
- Tên thư mục con dưới state.dir.

Các tài nguyên được tách biệt theo application ID. Nếu đổi ID thành orders-enrichment-v2, Kafka Streams xem đây là một logical application khác.

Điều đó không xóa tài nguyên cũ. Internal topics có prefix orders-enrichment-v1 vẫn có thể nằm trên broker, output topic cũ vẫn tồn tại và state directory cũ có thể còn trên disk.

Khi đổi application ID, ứng dụng mới chưa có committed offsets. Kafka Streams mặc định dùng auto.offset.reset=earliest cho consumer nội bộ. Nếu input data vẫn còn, ứng dụng mới có thể đọc lại từ earliest available offset và phát lại kết quả. Đây là nguyên nhân phổ biến tạo output trùng sau khi đổi ID.

Chỉ đổi application ID khi muốn tạo một logical application riêng hoặc cần tách biệt state/topology theo một kế hoạch migration rõ ràng. Đừng dùng đổi ID như một lệnh reset đơn giản.

## 4. Hậu quả đối với input topics và offsets

Input topic chứa lịch sử event mà Streams application dùng để xây dựng kết quả và state.

### 4.1. Reset về earliest

Reset offset về earliest khiến application đọc lại từ offset sớm nhất còn tồn tại của mỗi partition.

Earliest available offset không nhất thiết bằng 0. Nếu retention đã xóa segment cũ, hoặc compaction đã loại bỏ phiên bản cũ của key, dữ liệu lịch sử có thể không còn đầy đủ.

Ví dụ:

| Partition | Offset đầu tiên từng có | Earliest hiện tại | Latest |
|---|---:|---:|---:|
| 0 | 0 | 120 | 950 |
| 1 | 0 | 85 | 1.120 |
| 2 | 0 | 210 | 870 |

Reset về earliest sẽ bắt đầu từ 120, 85 và 210 tương ứng. Không thể dựng lại state cần event trước các offset này nếu không có bản lưu khác.

### 4.2. Reset về latest

Reset về latest khiến application bỏ qua backlog hiện có và bắt đầu nhận record mới được ghi sau thời điểm reset.

Cách này hữu ích khi cố ý bỏ lịch sử và chỉ xử lý event mới, nhưng có thể làm mất kết quả cần thiết cho aggregate hoặc bảng trạng thái. Nếu state store được tạo mới nhưng input offset ở cuối topic, state sẽ chỉ phản ánh event đến sau reset.

### 4.3. Reset theo timestamp hoặc offset cụ thể

Có thể chọn vị trí bắt đầu bằng:

- Earliest available offset.
- Latest offset.
- Một offset cụ thể.
- Timestamp cụ thể.
- Một khoảng thời gian tính từ hiện tại.
- Dịch offset hiện tại lên hoặc xuống.
- File CSV chứa offset theo partition.

Chỉ chọn một chiến lược offset trong một lần reset. Trước khi áp dụng, kiểm tra từng partition để bảo đảm không có partition bắt đầu quá muộn hoặc quá sớm so với yêu cầu nghiệp vụ.

### 4.4. Retention và compaction giới hạn khả năng replay

Reset offset không khôi phục dữ liệu đã bị Kafka xóa.

Với topic retention theo thời gian/kích thước, event cũ có thể đã bị xóa. Với topic compacted, nhiều phiên bản cũ của cùng key có thể đã được loại bỏ; dữ liệu còn lại thường đại diện trạng thái mới nhất theo key, không phải toàn bộ lịch sử thay đổi.

Nếu cần dựng lại một kết quả lịch sử chính xác, phải xác nhận input topic còn đủ dữ liệu hoặc có nguồn snapshot/backup khác.

## 5. Hậu quả đối với internal topics và state store

Kafka Streams có thể tạo các internal topics như:

- Changelog topic: lưu thay đổi state store.
- Repartition topic: phân vùng lại record theo key cần thiết cho phép group/join.
- Các internal resources khác theo topology và phiên bản runtime.

### 5.1. Xóa changelog topic

Changelog topic là nguồn để phục hồi local state store. Nếu xóa changelog, state backup trên broker mất đi.

Nếu input offsets được reset về vị trí phù hợp và input history còn đủ, Kafka Streams có thể dựng lại state bằng cách xử lý lại event. Nếu offsets không được reset, state mới có thể chỉ phản ánh phần dữ liệu đến sau vị trí hiện tại.

### 5.2. Xóa repartition topic

Repartition topic là dữ liệu trung gian do topology tạo ra. Sau khi xóa, Streams cần tạo lại và tái xử lý pipeline theo topology. Không xóa topic này trong khi application đang chạy.

Nếu topic trung gian do người dùng quản lý hoặc có consumer ngoài ứng dụng đọc, cần xử lý riêng và xác nhận ảnh hưởng trước khi xóa.

### 5.3. Internal topics không phải output topics

Internal topics phục vụ runtime và state của Streams. Output topics là contract dữ liệu mà downstream consumers có thể đang sử dụng.

Không được xóa output topics chỉ vì muốn reset internal state. Output có thể là lịch sử nghiệp vụ, dữ liệu phục vụ audit hoặc nguồn cho nhiều consumer khác.

## 6. Hậu quả đối với output và downstream

Đây là phần dễ bị bỏ sót nhất khi reset.

Application Reset Tool không xóa output topics. Nếu reset input offset về earliest, application có thể phát lại các output đã từng được ghi.

Ví dụ:

| Lần chạy | Input | Output |
|---|---|---|
| Lần đầu | OrderCreated tại offset 10 | OrderEnriched được ghi |
| Reset | Input offset trở về earliest | Output cũ vẫn còn |
| Chạy lại | OrderCreated được đọc lại | OrderEnriched mới được ghi thêm |

Downstream consumer có thể đọc output cũ một lần và sau đó nhận thêm output replay. Exactly-once trong Kafka transaction không tự loại bỏ duplicate được tạo bởi một lần replay có chủ đích ở thời điểm khác.

### 6.1. Ba chiến lược với output

| Chiến lược | Khi phù hợp | Việc cần làm |
|---|---|---|
| Giữ output topic và chấp nhận replay | Output là event log, downstream có idempotency | Giữ event ID ổn định và deduplicate |
| Tạo output topic version mới | Cần xây dựng lại kết quả nhưng không muốn trộn với lịch sử cũ | Ghi sang topic v2, kiểm tra kết quả rồi chuyển downstream |
| Xóa và tạo lại output topic | Môi trường lab hoặc có kế hoạch migration được phê duyệt | Dừng/điều phối downstream, kiểm tra retention/ACL và offset group |

Không xóa output topic nếu chưa kiểm kê tất cả downstream consumers. Việc xóa topic có thể làm mất dữ liệu lịch sử, phá vỡ offset đã lưu và ảnh hưởng các ứng dụng khác.

### 6.2. Downstream offsets không tự reset

Reset một Streams application không reset consumer groups của các ứng dụng downstream.

Nếu downstream đã đọc output đến offset 500, việc upstream replay và ghi thêm record tại offset 501 trở đi sẽ khiến downstream tiếp tục nhận chúng. Nếu mục tiêu là dựng lại toàn bộ downstream state, cần có kế hoạch reset riêng cho downstream group và output dataset.

## 7. Hậu quả đối với external side effects

Exactly-once processing của Kafka Streams bảo đảm atomicity giữa input offsets, output records và state store trong phạm vi Kafka transaction mà Streams quản lý.

Nó không hoàn tác các thao tác đã thực hiện ở hệ thống ngoài Kafka.

Ví dụ processor gọi API để gửi email hoặc cập nhật database:

1. Event được đọc và API đã thực hiện side effect.
2. Application bị dừng trước khi Kafka commit hoàn tất.
3. Sau reset, event được xử lý lại.
4. API có thể nhận yêu cầu lần thứ hai.

Do đó, reset có thể tạo side effect trùng dù application dùng exactly_once_v2.

Các biện pháp cần có:

- Dùng event ID ổn định làm idempotency key.
- Lưu processed-event ID trong database với unique constraint.
- Dùng inbox/outbox pattern khi cần phối hợp database và Kafka.
- Phân biệt replay để dựng lại state với hành động nghiệp vụ cần thực hiện lại.
- Nếu side effect không thể lặp an toàn, chạy chế độ replay chỉ ghi output nội bộ hoặc tắt side effect theo một cơ chế được kiểm soát.

Không dựa vào Kafka transaction để bảo đảm một REST API hoặc database bên ngoài chỉ được gọi đúng một lần.

## 8. Hậu quả đối với windowed state và event time

State store có thể chứa aggregate theo cửa sổ thời gian, session hoặc trạng thái theo key.

Khi reset và replay:

- Event cũ có thể được xử lý lại theo timestamp ban đầu.
- Window aggregate có thể được phát ra lại.
- Grace period và retention của window store vẫn ảnh hưởng event nào được chấp nhận.
- Event-time result có thể khác nếu timestamp extractor hoặc topology đã thay đổi.
- Nếu input history không còn đủ, window state lịch sử không thể được dựng lại chính xác.

Ví dụ ứng dụng tính doanh thu theo ngày. Reset từ earliest available offset chỉ dựng lại tổng doanh thu từ phần event còn tồn. Nếu các event của tháng trước đã hết retention, kết quả tháng trước sẽ thiếu.

Nếu topology mới đổi cách trích timestamp hoặc quy tắc window, replay cùng input có thể tạo ra kết quả khác. Đây là một lần rebuild dữ liệu theo logic mới, không đơn thuần là khởi động lại.

## 9. Các công cụ reset theo rebalance protocol

Kafka 4.4 có hai cách quản lý reset tùy group protocol.

| Rebalance protocol | Công cụ |
|---|---|
| Classic protocol | kafka-streams-application-reset.sh |
| Streams Rebalance Protocol, cấu hình group.protocol=streams | kafka-streams-groups.sh |

Streams Rebalance Protocol được hỗ trợ từ Kafka 4.2. Với protocol mới, dùng Streams Groups CLI. Không dùng classic reset tool cho một Streams group theo protocol mới.

Trước mọi thao tác thay đổi offset hoặc xóa internal topics:

1. Dừng tất cả instance của application.
2. Xác nhận group không còn member hoạt động.
3. Xác định chính xác application ID và input topics.
4. Chạy dry-run để xem phạm vi thay đổi.
5. Kiểm tra output/downstream và local state.
6. Chỉ execute khi kết quả preview đúng.

## 10. Reset với classic rebalance protocol

Với ứng dụng dùng classic protocol, chạy script kafka-streams-application-reset.sh trong thư mục Kafka distribution.

Ví dụ preview reset input topics về earliest:

~~~bash
bin/kafka-streams-application-reset.sh \
  --application-id orders-enrichment-v1 \
  --bootstrap-server localhost:9092 \
  --input-topics orders,payments \
  --to-earliest \
  --dry-run
~~~

Nếu preview đúng, áp dụng:

~~~bash
bin/kafka-streams-application-reset.sh \
  --application-id orders-enrichment-v1 \
  --bootstrap-server localhost:9092 \
  --input-topics orders,payments \
  --to-earliest \
  --execute
~~~

Một số lựa chọn offset:

~~~bash
# Reset đến latest
bin/kafka-streams-application-reset.sh \
  --application-id orders-enrichment-v1 \
  --bootstrap-server localhost:9092 \
  --input-topics orders,payments \
  --to-latest \
  --dry-run

# Reset đến timestamp
bin/kafka-streams-application-reset.sh \
  --application-id orders-enrichment-v1 \
  --bootstrap-server localhost:9092 \
  --input-topics orders,payments \
  --to-datetime 2026-11-01T00:00:00.000 \
  --dry-run

# Dịch offset lùi 500 record
bin/kafka-streams-application-reset.sh \
  --application-id orders-enrichment-v1 \
  --bootstrap-server localhost:9092 \
  --input-topics orders \
  --shift-by -500 \
  --dry-run
~~~

Các tham số trên chỉ minh họa cú pháp. Hãy kiểm tra help của đúng Kafka distribution và xác nhận timestamp/offset có tồn tại trong từng partition.

### 10.1. Tool classic làm gì?

Theo tài liệu Kafka 4.4, application reset tool:

- Reset committed offsets của các input topics theo vị trí được chọn; nếu không chọn vị trí, mặc định là earliest.
- Xóa internal topics thuộc application.
- Không xóa output topics.
- Không xóa local state directory trên các máy chạy instance.

Không truyền nhầm topic của ứng dụng khác. Một application ID sai hoặc input topic list sai có thể ảnh hưởng consumer group và topic không thuộc ứng dụng mục tiêu.

### 10.2. Reset internal state nhưng không replay input

Nếu muốn tạo internal state mới nhưng không đọc lại input lịch sử, không truyền tùy chọn input topics cho reset tool. Khi đó, cần hiểu rõ hậu quả: state store bị xóa nhưng input offsets không được đưa về đầu.

Ứng dụng chỉ xử lý event đến sau offset hiện tại. Các aggregate hoặc bảng trạng thái phụ thuộc lịch sử có thể bắt đầu từ trạng thái rỗng và thiếu dữ liệu cũ.

Đây chỉ là lựa chọn phù hợp khi nghiệp vụ chấp nhận khởi tạo trạng thái mới từ các event tương lai hoặc có nguồn snapshot để nạp lại state.

## 11. Reset với Streams Rebalance Protocol

Với Kafka 4.2 trở lên và ứng dụng dùng group.protocol=streams, dùng kafka-streams-groups.sh.

Preview reset toàn bộ input topics về earliest:

~~~bash
bin/kafka-streams-groups.sh \
  --bootstrap-server localhost:9092 \
  --group orders-enrichment-v1 \
  --reset-offsets \
  --all-input-topics \
  --to-earliest \
  --dry-run
~~~

Áp dụng sau khi đã kiểm tra preview:

~~~bash
bin/kafka-streams-groups.sh \
  --bootstrap-server localhost:9092 \
  --group orders-enrichment-v1 \
  --reset-offsets \
  --all-input-topics \
  --to-earliest \
  --execute
~~~

Có thể chọn một input topic:

~~~bash
bin/kafka-streams-groups.sh \
  --bootstrap-server localhost:9092 \
  --group orders-enrichment-v1 \
  --reset-offsets \
  --input-topic orders \
  --to-earliest \
  --dry-run
~~~

Trước tiên, preview phạm vi offset bằng lệnh reset không kèm tùy chọn xóa internal topics. Khi đã xác nhận đúng và thực sự muốn rebuild state từ input, thực thi reset cùng tùy chọn xóa internal topics:

~~~bash
bin/kafka-streams-groups.sh \
  --bootstrap-server localhost:9092 \
  --group orders-enrichment-v1 \
  --reset-offsets \
  --all-input-topics \
  --to-earliest \
  --delete-all-internal-topics \
  --execute
~~~

Tùy chọn xóa internal topics chỉ nên xuất hiện trong lệnh execute sau khi đã kiểm tra preview offset. Việc xóa các topic này loại bỏ state backing topics và buộc application dựng lại state.

### 11.1. Xóa Streams group

Streams Groups CLI có thể xóa metadata phía broker của group. Có thể chỉ xóa metadata hoặc chọn xóa thêm internal topics.

Ví dụ xóa group và internal topics:

~~~bash
bin/kafka-streams-groups.sh \
  --bootstrap-server localhost:9092 \
  --delete \
  --group orders-enrichment-v1 \
  --delete-all-internal-topics
~~~

Thao tác này có tác động rộng hơn reset offset. Chỉ dùng khi muốn xóa broker-side Streams metadata và state backing topics của application. Output topics vẫn cần được quản lý riêng.

### 11.2. Kiểm tra group trước và sau reset

Xem trạng thái group:

~~~bash
bin/kafka-streams-groups.sh \
  --bootstrap-server localhost:9092 \
  --describe \
  --group orders-enrichment-v1 \
  --state \
  --verbose
~~~

Xem input offsets và lag:

~~~bash
bin/kafka-streams-groups.sh \
  --bootstrap-server localhost:9092 \
  --describe \
  --group orders-enrichment-v1 \
  --offsets
~~~

Xác nhận group đã inactive/empty trước khi reset và kiểm tra lại offset sau khi ứng dụng chạy lại.

## 12. Xóa local state directory

Application reset tool không xóa local state trên các máy hoặc container đã chạy application. Phải xử lý từng local state directory.

### 12.1. Dùng KafkaStreams.cleanUp()

API cleanUp() xóa local state của application. Chỉ gọi khi KafkaStreams instance chưa start hoặc đã close.

Ví dụ gọi trước start trong môi trường kiểm thử:

~~~java
KafkaStreams streams = new KafkaStreams(topology, props);

streams.cleanUp();
streams.start();
~~~

Nếu instance đã chạy, hãy đóng trước:

~~~java
streams.close(Duration.ofSeconds(30));
streams.cleanUp();
~~~

Không gọi cleanUp() trong khi stream threads đang xử lý record.

### 12.2. Hành vi cleanUp() trong Kafka 4.4

Từ Kafka 4.4, cleanUp() có thể giữ lại application state directory nếu bên trong chỉ còn các file metadata hợp lệ như:

- kafka-streams-process-metadata
- .lock

Điều đó không có nghĩa local state store chưa được xóa. Kafka giữ metadata này để duy trì process identity và quản lý lock.

Nếu cần full local reset bao gồm metadata, hãy đóng KafkaStreams instance rồi xóa thủ công thư mục application bên dưới state.dir.

### 12.3. Xóa local state trên mọi instance

Ví dụ state.dir:

~~~properties
state.dir=/var/lib/kafka-streams
application.id=orders-enrichment-v1
~~~

Thư mục application thường nằm tại:

~~~text
/var/lib/kafka-streams/orders-enrichment-v1
~~~

Nếu không cấu hình state.dir, Kafka Streams dùng thư mục dưới java.io.tmpdir, theo dạng kafka-streams/<application.id>. Hãy kiểm tra giá trị state.dir thực tế của service thay vì giả định mọi host đều dùng cùng một đường dẫn.

Nếu application từng chạy trên 3 host hoặc 3 persistent volumes, phải kiểm tra cả 3 nơi. Xóa state ở một host không xóa state ở host khác.

Trong Kubernetes:

- Với emptyDir, local state thường mất khi pod bị xóa.
- Với persistent volume, dữ liệu có thể vẫn tồn tại sau khi pod thay thế.
- Mỗi replica phải có vùng local state riêng.
- Không để hai process cùng sử dụng một state directory.
- Chỉ xóa volume sau khi xác định đúng application ID và pod đã dừng.

Không xóa toàn bộ state.dir nếu thư mục đó chứa state của nhiều Kafka Streams application khác.

## 13. Đổi application.id có phải là reset không?

Đổi application ID tạo một logical application mới, không phải thao tác cleanup application cũ.

Ví dụ:

~~~properties
# Trước
application.id=orders-enrichment-v1

# Sau
application.id=orders-enrichment-v2
~~~

Hậu quả:

- Consumer group mới được tạo.
- Internal topics mới được tạo theo prefix mới.
- Local state nằm trong thư mục khác.
- Không sử dụng committed offsets của application ID cũ.
- Kafka Streams mặc định bắt đầu từ earliest khi group mới chưa có offset.
- Output topics cũ không bị xóa.
- Internal topics cũ và local state cũ có thể còn tồn tại.

Nếu v2 ghi vào cùng output topic với v1, downstream có thể nhận dữ liệu replay hoặc dữ liệu được tính lại từ đầu. Nếu muốn chạy song song để so sánh, nên dùng output topic version mới và consumer group downstream riêng.

Khi migration hoàn tất, cần có kế hoạch thu hồi tài nguyên của application cũ sau khi đã xác nhận không còn consumer hoặc operator phụ thuộc chúng.

## 14. Reset và exactly-once semantics

Exactly-once v2 bảo đảm input offsets, output records và state updates của một processing transaction được commit nguyên tử trong Kafka.

Nó không ngăn việc cùng input được xử lý lại sau một reset có chủ đích.

Ví dụ:

1. Lần chạy đầu ghi output cho order-100.
2. Application reset về earliest.
3. Input order-100 được đọc lại.
4. Application ghi output mới cho order-100.
5. Output topic có thể chứa hai lần biểu diễn kết quả.

Hai output không phải lỗi transaction. Chúng đến từ hai lần chạy hợp lệ của application.

Nếu downstream không muốn xử lý lặp, cần event ID ổn định, deduplication hoặc output topic version mới. Với database/API ngoài Kafka, cần idempotency riêng.

## 15. Reset khi thay đổi topology hoặc sửa bug

Reset thường được cân nhắc trong các trường hợp:

- Bug trong aggregation khiến state store sai.
- Thay đổi logic join hoặc grouping key.
- Thay đổi Serde hoặc schema làm state cũ không còn đọc được.
- Thay đổi timestamp extractor hoặc window logic.
- Cần tái tạo kết quả từ lịch sử event.
- Thay đổi cấu trúc topology làm task/state mapping không còn phù hợp.

Không phải mọi thay đổi code đều cần reset. Nếu thay đổi chỉ ở phần xử lý stateless và tương thích với state hiện có, có thể rolling deploy theo kế hoạch.

Nếu thay đổi state schema hoặc topology không tương thích, có thể cần application ID mới để cô lập state mới. Tuy nhiên, phải đánh giá replay input, output duplication, internal topic cleanup và thời gian rebuild.

Khi nâng Kafka Streams version, đọc upgrade guide trước. Một số bản nâng cấp có thể thay đổi task ID hoặc state store mapping và tự restore state từ changelog; điều đó không đồng nghĩa cần reset toàn bộ application.

## 16. Runbook reset an toàn

Một runbook đầy đủ nên được thực hiện theo thứ tự sau.

### Bước 1: Xác định mục tiêu

Trả lời rõ:

- Có cần đọc lại toàn bộ input không?
- Có cần dựng lại state store không?
- Có cần xóa internal topics không?
- Output topic sẽ giữ, version mới hay xóa?
- Downstream consumers có cần reset không?
- External side effects có thể được gọi lại không?

Không bắt đầu bằng lệnh reset trước khi trả lời các câu hỏi này.

### Bước 2: Kiểm kê tài nguyên

Ghi lại:

- application.id và group.protocol.
- Input, output và intermediate topics.
- Internal changelog/repartition topics.
- Committed offsets theo partition.
- Local state.dir trên từng instance.
- Consumer groups downstream.
- Database/API có thể nhận side effect.

Lưu cấu hình topic, offset snapshot và thông tin incident để đối soát.

### Bước 3: Dừng application

Dừng tất cả instance và đợi shutdown hoàn tất. Xác nhận group đã empty/inactive bằng CLI phù hợp.

Không chạy reset khi còn instance đang xử lý. Nếu có member cũ chưa hết session timeout, chỉ cân nhắc force removal sau khi đã xác nhận toàn bộ process thực sự dừng.

### Bước 4: Preview reset

Chọn công cụ theo group protocol. Chạy dry-run và kiểm tra:

- Đúng application ID.
- Đúng input topics.
- Đúng partition/offset/timestamp.
- Đúng internal topics dự kiến xóa.
- Không tác động group/topic khác.

Nếu bất kỳ mục nào sai, dừng và sửa tham số.

### Bước 5: Xử lý local state

Xóa local state của đúng application trên tất cả host hoặc volume. Nếu cần full reset Kafka 4.4, đóng instance rồi xóa cả application directory còn metadata.

### Bước 6: Xử lý output và downstream

Chọn chiến lược giữ output, output version mới hoặc xóa/recreate theo kế hoạch. Xác định downstream sẽ tiếp tục từ offset cũ hay đọc lại.

Nếu replay có thể tạo side effect trùng, bật deduplication hoặc chạy một chế độ rebuild không gọi side effect.

### Bước 7: Execute và khởi động lại

Thực thi reset sau khi preview pass. Khởi động một instance canary trước nếu có thể, theo dõi state restoration và output. Sau đó mới mở rộng đủ số instance.

### Bước 8: Đối soát

Kiểm tra:

- Input offsets bắt đầu đúng vị trí.
- Internal topics được tạo lại.
- State store restore/rebuild thành công.
- Output count và business aggregate đúng.
- Downstream không bị duplicate ngoài dự kiến.
- External side effects không bị thực hiện lặp ngoài policy.
- Consumer lag và processing latency ổn định.

## 17. Metrics và dấu hiệu cần theo dõi sau reset

| Chỉ số | Ý nghĩa |
|---|---|
| Input consumer lag | Khối lượng dữ liệu còn phải replay |
| Records consumed rate | Tốc độ xử lý input |
| State restoration duration | Thời gian phục hồi local state từ changelog |
| Changelog restore lag | Mức độ còn phải đọc để phục hồi state |
| Rebalance count/duration | Số lần và thời gian phân phối lại task |
| Output records rate | Tốc độ ghi kết quả sau reset |
| Transaction abort/commit | Tình trạng xử lý Kafka transaction |
| Processing exception count | Lỗi phát sinh trong quá trình replay |
| External API/database error | Side effect ngoài Kafka bị lỗi hoặc bị gọi lặp |
| Disk usage | Dung lượng local state/RocksDB và internal topics |

Nếu reset từ earliest, consumer lag có thể tăng rất lớn. Cần kiểm tra capacity broker, disk, network và downstream trước khi cho application chạy hết tốc độ.

## 18. Lab: quan sát hậu quả của ba kiểu reset

Mục tiêu: phân biệt restart bình thường, local cleanup và full reset.

### Bước 1: Tạo input topic

Tạo topic orders với 3 partition. Gửi một số event có key order ID.

### Bước 2: Tạo topology stateful

Xây dựng topology đọc orders, group theo customer ID, aggregate tổng số đơn và ghi kết quả sang customer-order-counts.

### Bước 3: Chạy application

Đặt application.id=orders-count-lab. Chờ application xử lý input và tạo state store/changelog. Ghi lại input offsets, state value và output records.

### Bước 4: Restart bình thường

Dừng process và khởi động lại cùng application ID, cùng state directory. Xác nhận input offsets được giữ và application tiếp tục xử lý event mới.

### Bước 5: Xóa local state

Dừng application. Gọi cleanUp() hoặc xóa đúng local application directory. Giữ nguyên input offsets và internal changelog topics. Khởi động lại và quan sát state restoration từ changelog.

### Bước 6: Full reset

Dừng mọi instance. Chạy reset tool theo group protocol, preview offset reset về earliest và internal topic cleanup. Xóa local state trên các máy đã chạy application.

### Bước 7: Quan sát output

Khởi động lại và xác nhận input được đọc lại, state được dựng lại và output có thể được ghi thêm. So sánh output trước/sau reset.

### Bước 8: Thử downstream

Tạo một consumer group đọc customer-order-counts. Xác nhận group downstream không tự reset khi upstream reset và có thể nhận thêm các output replay.

### Bước 9: Thử đổi application.id

Chạy ứng dụng với application ID mới và quan sát group/internal topics mới. Kiểm tra dữ liệu input được đọc theo auto.offset.reset và output topic cũ vẫn còn.

### Bước 10: Ghi kết quả

Ghi lại từng thao tác đã thực hiện, offsets trước/sau, internal topics, local state, output records và trạng thái downstream.

## 19. Những sai lầm thường gặp

| Sai lầm | Hậu quả | Cách phòng tránh |
|---|---|---|
| Nghĩ restart là reset | State và offsets cũ vẫn được dùng | Phân biệt lifecycle với reset |
| Chỉ xóa local state | State được restore lại từ changelog | Reset đúng cả broker-side state khi cần |
| Chỉ xóa internal topics | Local state cũ có thể còn trên disk | Xử lý state directory trên mọi instance |
| Reset input nhưng giữ output | Output replay có thể bị downstream xử lý trùng | Dùng dedupe hoặc output version mới |
| Đổi application.id để reset | Tạo group/internal topics mới, tài nguyên cũ còn tồn tại | Quản lý vòng đời cả ID cũ và mới |
| Reset khi instance còn chạy | Group rebalance hoặc application state không hợp lệ | Dừng toàn bộ instance và xác nhận group empty |
| Không chạy dry-run | Có thể reset nhầm topic hoặc group | Preview trước khi execute |
| Reset về earliest nhưng input đã hết retention | Không dựng lại được toàn bộ state lịch sử | Kiểm tra earliest offset và backup |
| Xóa state nhưng giữ input offset cuối | State mới không phản ánh lịch sử | Đồng bộ offset với chiến lược rebuild |
| Tin EOS ngăn duplicate sau replay | Output và side effect vẫn có thể lặp giữa hai lần chạy | Idempotency và deduplication |
| Xóa toàn bộ state.dir dùng chung | Mất state của application khác | Chỉ xóa thư mục đúng application ID |
| Dùng classic reset tool cho Streams protocol | Công cụ không quản lý đúng loại group | Chọn Streams Groups CLI khi group.protocol=streams |

## 20. Checklist trước khi reset production

- [ ] Xác định mục tiêu reset và phạm vi dữ liệu cần xử lý lại.
- [ ] Ghi nhận application.id và group.protocol.
- [ ] Kiểm kê input, output, intermediate và internal topics.
- [ ] Lưu offset snapshot theo partition.
- [ ] Kiểm tra retention và earliest available offset của input.
- [ ] Kiểm kê local state directory trên mọi instance/volume.
- [ ] Kiểm kê downstream consumer groups và external side effects.
- [ ] Dừng toàn bộ application instances.
- [ ] Xác nhận group empty/inactive.
- [ ] Chọn đúng reset tool theo rebalance protocol.
- [ ] Chạy dry-run và xác minh toàn bộ topic/offset scope.
- [ ] Có kế hoạch output replay, deduplication hoặc output version mới.
- [ ] Xóa local state đúng application trên tất cả host.
- [ ] Chỉ xóa internal topics khi thật sự muốn rebuild state.
- [ ] Không xóa output topics khi chưa điều phối downstream.
- [ ] Khởi động canary và theo dõi restore/lag/output.
- [ ] Đối soát state và business results sau reset.
- [ ] Lưu audit record và kết quả reset.

## 21. Tài liệu tham khảo

- [Apache Kafka 4.4 – Application Reset Tool](https://kafka.apache.org/44/streams/developer-guide/app-reset-tool/)
- [Apache Kafka 4.4 – Kafka Streams Groups Tool](https://kafka.apache.org/44/streams/developer-guide/kafka-streams-group-sh/)
- [Apache Kafka 4.4 – Streams Rebalance Protocol](https://kafka.apache.org/44/streams/developer-guide/streams-rebalance-protocol/)
- [Apache Kafka 4.4 – Configuring a Streams Application](https://kafka.apache.org/44/streams/developer-guide/config-streams/)
- [Apache Kafka 4.4 – KafkaStreams Javadoc](https://kafka.apache.org/44/javadoc/org/apache/kafka/streams/KafkaStreams.html)
- [Apache Kafka 4.4 – Upgrade Guide](https://kafka.apache.org/44/streams/upgrade-guide/)

Reset Kafka Streams là thao tác đồng bộ giữa input offsets, internal topics, local state và output/downstream. Hãy dừng toàn bộ instance, xác định group protocol, preview thay đổi, xử lý local state trên mọi máy và chuẩn bị cách đối soát output trước khi chạy lại. Chỉ khi hiểu rõ dữ liệu nào được đọc lại, state nào được dựng lại và side effect nào có thể lặp, mới có thể reset ứng dụng an toàn trong production.
