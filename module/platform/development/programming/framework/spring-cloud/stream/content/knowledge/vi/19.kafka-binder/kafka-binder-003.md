# Cấp phát topic và kiểm soát `autoCreateTopics`, `autoAddPartitions`

Kafka Binder cần một topic để nối output hoặc input binding với Kafka. Khi binding được khởi tạo, binder kiểm tra topic đích và số partition cần thiết. Tùy cấu hình, binder có thể tạo topic chưa tồn tại hoặc tăng số partition của topic hiện có. Hai thuộc tính quan trọng điều khiển hành vi này là `autoCreateTopics` và `autoAddPartitions`.

Trong môi trường phát triển, tự động tạo và mở rộng topic giúp khởi chạy ứng dụng nhanh. Trong production, việc cấp phát topic thường cần được quản lý tập trung để kiểm soát replication factor, retention, dung lượng, quyền truy cập và kế hoạch mở rộng. Hiểu rõ hai thuộc tính giúp tránh tình trạng ứng dụng tự tạo tài nguyên ngoài ý muốn hoặc khởi động thất bại vì topic chưa đủ partition.

## 1. Topic là tài nguyên mà binding sử dụng

Trong Spring Cloud Stream, thuộc tính `destination` của binding Kafka thường ánh xạ tới tên topic Kafka. Producer gửi record vào topic; consumer đọc record từ topic thông qua consumer group và offset.

```yaml
spring:
  cloud:
    function:
      definition: publishOrder;processOrder
    stream:
      bindings:
        publishOrder-out-0:
          destination: orders.created
          content-type: application/json
        processOrder-in-0:
          destination: orders.created
          group: inventory-service
          content-type: application/json
```

Trong ví dụ, cả hai binding dùng cùng destination `orders.created`. Producer và consumer group cùng làm việc trên một topic. Group không tạo một topic riêng; nó có trạng thái offset độc lập để các instance trong cùng group chia nhau partition.

Topic cần được tạo trước hoặc được binder cấp phát khi binding khởi tạo. Việc tạo topic gồm tên topic, số partition và replication factor. Các cấu hình retention, cleanup policy, compression, quota và ACL là những quyết định vận hành riêng; không nên xem hai thuộc tính tự động dưới đây là cơ chế quản trị toàn bộ topic.

## 2. `autoCreateTopics`: tạo topic khi chưa tồn tại

`spring.cloud.stream.kafka.binder.autoCreateTopics` điều khiển việc Kafka Binder tự tạo topic khi destination chưa tồn tại. Mặc định thuộc tính này là `true` trong cấu hình Kafka Binder thông dụng.

- Khi `true`, binder có thể dùng Kafka AdminClient để tạo topic còn thiếu trong lúc provision binding, nếu tài khoản kết nối có đủ quyền quản trị cần thiết.
- Khi `false`, binder không chủ động tạo topic. Topic phải được tạo trước bằng công cụ quản trị hoặc hạ tầng dưới dạng mã (Infrastructure as Code); nếu topic chưa tồn tại, quá trình provision binding có thể thất bại.
- Thuộc tính này áp dụng cho việc provision topic của binder. Nó không phải cùng một cấu hình với `auto.create.topics.enable` ở phía broker.

Ví dụ cấu hình cho môi trường phát triển:

```yaml
spring:
  cloud:
    stream:
      kafka:
        binder:
          auto-create-topics: true
```

Với cấu hình trên, khi ứng dụng tạo binding đến `orders.created`, binder có thể tạo topic nếu chưa có. Nếu broker không cho phép user tạo topic, ứng dụng vẫn có thể gặp lỗi authorization dù `auto-create-topics` đang bật.

### 2.1. Phân biệt với `auto.create.topics.enable` của Kafka broker

Kafka broker có cấu hình riêng `auto.create.topics.enable`, điều khiển việc broker tự tạo topic khi client truy cập một topic chưa tồn tại theo những đường truy cập có thể kích hoạt implicit creation. Đây là thiết lập ở cấp broker.

Hai cấu hình có phạm vi khác nhau:

| Cấu hình | Nơi đặt | Vai trò |
|---|---|---|
| `spring.cloud.stream.kafka.binder.autoCreateTopics` | Ứng dụng Spring Cloud Stream | Cho phép binder chủ động provision topic bằng AdminClient |
| `auto.create.topics.enable` | Kafka broker | Cho phép hoặc ngăn cơ chế broker tự tạo topic ngầm khi client yêu cầu metadata/đọc/ghi vào topic chưa có |

Tắt implicit topic creation ở broker không đồng nghĩa cấm AdminClient tạo topic một cách tường minh. Ngược lại, tắt `autoCreateTopics` ở binder không tự thay đổi cấu hình broker. Trong môi trường được quản trị chặt, thường tắt implicit creation ở broker và tắt provision tự động ở ứng dụng; pipeline triển khai sẽ tạo topic trước khi deploy producer/consumer.

## 3. `autoAddPartitions`: tăng partition cho topic đã tồn tại

`spring.cloud.stream.kafka.binder.autoAddPartitions` điều khiển việc binder tự tăng số partition khi topic hiện có ít partition hơn số lượng cần thiết theo cấu hình binding/binder. Mặc định thuộc tính này thường là `true`.

Ví dụ, topic `orders.created` hiện có 2 partition nhưng cấu hình producer yêu cầu 6 partition. Nếu `autoAddPartitions` bật và user có quyền thay đổi topic, binder có thể yêu cầu Kafka tăng số partition lên 6 khi provision binding.

```yaml
spring:
  cloud:
    stream:
      kafka:
        binder:
          auto-add-partitions: true
      bindings:
        publishOrder-out-0:
          destination: orders.created
          producer:
            partition-count: 6
```

`partition-count` ở producer là số partition mong muốn/được yêu cầu cho destination trong quá trình provision. Số partition thực tế của topic là thông tin do Kafka quản lý. Nếu topic đã có số partition lớn hơn, binder không cần giảm số partition xuống theo giá trị cấu hình nhỏ hơn.

Khi `autoAddPartitions` là `false`, binder không tự mở rộng topic. Nếu topic hiện có không đáp ứng số partition cần thiết, binding có thể không được provision thành công. Khi đó, quản trị viên cần mở rộng topic trước bằng quy trình quản trị đã phê duyệt, hoặc điều chỉnh cấu hình ứng dụng để phù hợp với topic hiện có.

### 3.1. Số partition cần thiết đến từ đâu?

Số partition mà binder yêu cầu có thể chịu ảnh hưởng bởi cấu hình ở cấp binder và binding. Các thuộc tính thường cần xem cùng nhau gồm:

| Thuộc tính | Phạm vi | Ý nghĩa |
|---|---|---|
| `spring.cloud.stream.kafka.binder.min-partition-count` | Kafka Binder | Số partition tối thiểu mà binder yêu cầu cho topic được provision |
| `spring.cloud.stream.bindings.<binding>.producer.partition-count` | Producer binding | Số partition mong muốn cho destination của producer |
| `spring.cloud.stream.bindings.<binding>.consumer.concurrency` | Consumer binding | Số consumer thread trong một instance; ảnh hưởng khả năng tiêu thụ song song của instance |
| `spring.cloud.stream.instance-count` | Ứng dụng | Số instance được khai báo khi binder cần tính năng lực tiêu thụ của consumer partitioned |

Giá trị yêu cầu cuối cùng phụ thuộc loại binding, cấu hình partitioning và phiên bản binder. Với consumer được partition theo instance, cần tính cả `instance-count` và `concurrency` khi lập kế hoạch số partition. Đừng chỉ nhìn `partition-count` của producer hoặc chỉ nhìn số pod đang chạy rồi kết luận topic đã đủ.

Ví dụ một consumer service chạy 3 instance, mỗi instance có concurrency 2, có thể cần tối đa 6 consumer slot để xử lý song song trong cùng group. Topic có ít hơn 6 partition sẽ khiến một số slot không có partition để nhận. Tăng partition chỉ có ích khi có đủ năng lực downstream và cách phân vùng dữ liệu phù hợp.

## 4. Kết hợp hai thuộc tính

Hai thuộc tính kiểm soát hai tình huống khác nhau:

| `autoCreateTopics` | `autoAddPartitions` | Hành vi cần dự kiến |
|---|---|---|
| `true` | `true` | Binder có thể tạo topic còn thiếu và tăng partition cho topic đã tồn tại khi cần |
| `true` | `false` | Binder có thể tạo topic mới theo số partition được yêu cầu, nhưng không tự mở rộng topic đã tồn tại không đủ partition |
| `false` | `true` | Topic phải tồn tại; binder có thể tăng partition nếu topic hiện tại chưa đủ và user có quyền thay đổi |
| `false` | `false` | Topic và số partition cần thiết phải được chuẩn bị trước; binder không tự tạo hoặc mở rộng |

Khi `autoCreateTopics` tắt mà topic chưa tồn tại, `autoAddPartitions` không thể thay thế việc tạo topic. Ngược lại, nếu topic đã tồn tại, việc tắt tạo mới không nhất thiết ngăn binder mở rộng partition khi `autoAddPartitions` vẫn bật.

## 5. Ví dụ cấu hình theo môi trường

### 5.1. Môi trường phát triển cục bộ

Trong môi trường local, cho phép binder tự tạo topic và tăng partition giúp người học tập trung vào code producer/consumer:

```yaml
spring:
  cloud:
    stream:
      kafka:
        binder:
          brokers: localhost:9092
          auto-create-topics: true
          auto-add-partitions: true
          min-partition-count: 1
          replication-factor: 1
      bindings:
        publishOrder-out-0:
          destination: orders.created
          producer:
            partition-count: 3
        processOrder-in-0:
          destination: orders.created
          group: inventory-local
          consumer:
            concurrency: 3
```

Replication factor bằng 1 phù hợp với Kafka một node để học tập; nó không cung cấp khả năng chịu lỗi. Topic local có thể được tạo khi binding khởi tạo, và binder có thể tăng partition nếu topic tồn tại với số partition thấp hơn yêu cầu.

### 5.2. Môi trường production có provisioning tập trung

Trong production, thường nên để pipeline hoặc nhóm nền tảng tạo topic trước. Ứng dụng chỉ kết nối tới tài nguyên đã được cấp phát:

```yaml
spring:
  cloud:
    stream:
      kafka:
        binder:
          auto-create-topics: false
          auto-add-partitions: false
      bindings:
        publishOrder-out-0:
          destination: orders.created
          producer:
            partition-count: 12
        processOrder-in-0:
          destination: orders.created
          group: inventory-service
          consumer:
            concurrency: 4
```

Trước khi deploy cấu hình này, topic `orders.created` phải tồn tại với số partition phù hợp (ít nhất 12 theo yêu cầu producer trong ví dụ) và replication factor, retention, cleanup policy cùng ACL theo tiêu chuẩn nền tảng. Nếu topic thiếu hoặc không đủ partition, binding có thể không khởi tạo được. Ứng dụng không tự sửa cấu hình topic trong môi trường này.

Có thể tách các giá trị theo Spring profile, ví dụ `application-local.yml` và `application-prod.yml`. Hãy kiểm tra profile đang hoạt động trong log startup để tránh vô tình chạy production với cấu hình local cho phép tạo tài nguyên.

## 6. Cấp phát topic trước bằng công cụ Kafka

Khi tắt tự động tạo và mở rộng, pipeline quản trị cần cấp phát topic trước. Ví dụ dùng `kafka-topics.sh`:

```bash
kafka-topics.sh \
  --bootstrap-server kafka-1:9092 \
  --create \
  --topic orders.created \
  --partitions 12 \
  --replication-factor 3
```

Replication factor 3 yêu cầu cụm có đủ broker phù hợp. Điều chỉnh số broker, rack awareness và chính sách replication theo nền tảng thực tế; không sao chép giá trị này vào cluster nhỏ hơn.

Kiểm tra topic sau khi tạo:

```bash
kafka-topics.sh \
  --bootstrap-server kafka-1:9092 \
  --describe \
  --topic orders.created
```

Kết quả mô tả topic cho biết partition count, leader, replica và ISR. Hãy xác nhận đúng cluster, đúng topic và số partition trước khi deploy ứng dụng.

Nếu cần tăng partition cho topic đã tồn tại, dùng lệnh alter:

```bash
kafka-topics.sh \
  --bootstrap-server kafka-1:9092 \
  --alter \
  --topic orders.created \
  --partitions 18
```

Số partition mới phải lớn hơn số hiện tại. Kafka không hỗ trợ giảm partition của một topic đã tồn tại bằng thao tác alter thông thường. Muốn giảm, cần lập kế hoạch tạo topic mới và di chuyển dữ liệu/producer/consumer theo quy trình migration.

## 7. Tác động khi tăng partition

Tăng partition không chỉ là thay đổi dung lượng. Nó thay đổi mức song song, phân bố dữ liệu và có thể ảnh hưởng thứ tự xử lý.

### 7.1. Mức song song của consumer group

Trong một consumer group Kafka, mỗi partition tại một thời điểm được gán cho tối đa một consumer member trong group. Nếu group có nhiều consumer hơn số partition, một số consumer sẽ không nhận partition. Thêm partition có thể tăng khả năng song song, nhưng chỉ khi ứng dụng, database và dịch vụ phụ thuộc xử lý được tải tăng thêm.

Ví dụ topic có 4 partition và group có 8 consumer instance: tối đa 4 consumer có partition được gán tại một thời điểm. Nếu mở rộng topic lên 8 partition, group có thể phân công cho cả 8 consumer, tùy cấu hình và trạng thái group.

### 7.2. Thứ tự theo key có thể thay đổi sau khi mở rộng

Kafka bảo đảm thứ tự trong phạm vi một partition, không phải trên toàn topic. Với partitioner mặc định, key thường được băm để chọn partition dựa trên số partition hiện tại. Khi tăng số partition, cùng một key có thể được ánh xạ sang partition khác cho các record mới. Các record cũ của key đó vẫn nằm ở partition cũ.

Điều này có thể làm các record cũ và mới của cùng một key được xử lý bởi consumer khác nhau, dẫn tới quan sát không còn theo thứ tự toàn cục như trước. Nếu nghiệp vụ yêu cầu thứ tự nghiêm ngặt theo `orderId`, hãy đánh giá việc tăng partition như một thay đổi kiến trúc; có thể cần chiến lược partitioning ổn định, versioned routing hoặc migration sang topic mới.

### 7.3. Chi phí tài nguyên và quản trị

Nhiều partition hơn làm tăng số log segment, metadata, file handle, chi phí leader election, rebalance và công việc quản trị. Consumer group cũng phải phân công lại partition khi số partition thay đổi. Không đặt partition count quá cao chỉ để “dự phòng” mà không có ước lượng throughput, kích thước record, retention và số consumer.

## 8. Quyền cấp phát và lỗi thường gặp

Binder có thể kết nối broker thành công nhưng vẫn không được phép tạo hoặc thay đổi topic. Tài khoản runtime cần các quyền phù hợp với thao tác provision. Mô hình ACL khác nhau theo phiên bản Kafka và cách nền tảng quản trị quyền; nên cấp quyền tối thiểu cho đúng topic/prefix và đúng môi trường.

| Triệu chứng | Nguyên nhân có thể | Hướng kiểm tra |
|---|---|---|
| Binding lỗi vì topic không tồn tại | `autoCreateTopics=false` và topic chưa được cấp phát; hoặc user không có quyền tạo | Kiểm tra topic trên cluster và quyền AdminClient |
| Topic không tự tăng partition | `autoAddPartitions=false`, số partition yêu cầu không vượt cấu hình hiện tại hoặc thiếu quyền alter | So sánh partition thực tế với yêu cầu; kiểm tra quyền và log provisioner |
| Ứng dụng local tạo topic với 1 partition ngoài dự kiến | Cấu hình `partition-count`/`min-partition-count` không được nạp hoặc profile sai | Kiểm tra effective configuration và `kafka-topics --describe` |
| Topic được tạo nhưng replication factor thấp | Giá trị replication factor khi tạo chưa phù hợp hoặc cluster không đủ broker | Kiểm tra replication factor và số broker; điều chỉnh quy trình provisioning |
| Startup thất bại với authorization exception | Runtime principal thiếu quyền describe/create/alter cần thiết | Kiểm tra ACL và principal thực tế của ứng dụng |
| Tăng partition làm thay đổi thứ tự theo key | Hash partitioning phụ thuộc số partition | Đánh giá yêu cầu ordering và kế hoạch migration |
| Broker tự tạo topic ngoài dự kiến | `auto.create.topics.enable` đang bật | Kiểm tra cấu hình broker và quy trình quản trị cluster |

Các exception cụ thể có thể gồm lỗi authorization, lỗi topic metadata hoặc lỗi tạo partition; tên và nguyên nhân gốc phụ thuộc Kafka client, broker và phiên bản binder. Hãy đọc log startup đầy đủ, đặc biệt phần cause từ AdminClient/provisioner.

## 9. Dynamic destination và StreamBridge

`StreamBridge` có thể gửi tới destination được xác định lúc runtime và binder có thể tạo binding động khi gửi lần đầu. Nếu dynamic destination không được kiểm soát, ứng dụng có thể vô tình tạo nhiều topic theo dữ liệu đầu vào, chẳng hạn tên khách hàng hoặc request ID.

Với destination động:

- Dùng allowlist hoặc quy tắc đặt tên giới hạn số lượng destination hợp lệ.
- Xác định rõ ai được phép tạo topic và topic nào phải được provision trước.
- Cân nhắc tắt `autoCreateTopics` trong production để binding động không tự tạo topic ngoài kế hoạch.
- Theo dõi số binding/topic động và có quy trình dọn tài nguyên sau khi xác nhận không còn dữ liệu cần giữ.
- Không dùng dữ liệu người dùng trực tiếp làm tên topic nếu chưa kiểm tra ký tự, độ dài và quyền truy cập.

Dynamic binding không làm mất các quy tắc cấp phát topic. Nó chỉ thay đổi thời điểm binder phát hiện destination và provision binding.

## 10. Kiểm thử hành vi cấp phát

Kiểm thử nên bao gồm các trạng thái topic khác nhau:

1. Topic chưa tồn tại và `autoCreateTopics=true`: xác nhận binder tạo topic với số partition và replication factor dự kiến.
2. Topic chưa tồn tại và `autoCreateTopics=false`: xác nhận startup/binding báo lỗi rõ ràng, không tạo topic ngoài ý muốn.
3. Topic hiện có ít partition hơn yêu cầu và `autoAddPartitions=true`: xác nhận topic được mở rộng.
4. Topic hiện có ít partition hơn yêu cầu và `autoAddPartitions=false`: xác nhận binding không âm thầm hoạt động với cấu hình thiếu partition.
5. User không có quyền create/alter: xác nhận lỗi authorization được nhận diện và log có thông tin hữu ích.
6. Topic đã có nhiều partition hơn cấu hình: xác nhận binder không cố giảm partition.
7. Tăng partition khi có record cùng key: kiểm tra lại thứ tự và phân phối record.
8. Dynamic destination ngoài allowlist: xác nhận ứng dụng từ chối trước khi tạo binding/topic.

Test Binder phù hợp để kiểm tra logic function và một số binding trong JVM, nhưng không thay thế Kafka thật cho việc tạo topic, ACL, partition count, replication factor và AdminClient. Những hành vi provisioning phải được kiểm thử bằng broker tích hợp hoặc môi trường Kafka kiểm thử có quyền tương đương production.

## 11. Quy trình lựa chọn cấu hình

| Môi trường | `autoCreateTopics` | `autoAddPartitions` | Cách quản lý phù hợp |
|---|---:|---:|---|
| Máy cá nhân | `true` | `true` | Cho binder tạo tài nguyên phục vụ học tập và thử nghiệm |
| Integration test cô lập | Tùy fixture | Tùy fixture | Tạo topic tường minh trong test setup nếu cần xác nhận provisioning |
| Staging | Thường `false` | Thường `false` hoặc theo chính sách nền tảng | Provision bằng pipeline để gần production |
| Production | Thường `false` | Thường `false` | Quản trị topic tập trung, review partition/replication/retention/ACL trước deploy |

Không có một giá trị bắt buộc cho mọi hệ thống. Nếu nền tảng cho phép binder provision topic, cần giới hạn quyền và kiểm soát cấu hình. Nếu topic được quản trị tập trung, tắt hai tính năng tự động để ứng dụng chỉ sử dụng tài nguyên đã được cấp phát.

## 12. Danh sách kiểm tra trước khi triển khai

- [ ] Mỗi binding có `destination` rõ ràng và topic tồn tại hoặc được phép tạo.
- [ ] Đã chọn `autoCreateTopics` theo chính sách của môi trường.
- [ ] Đã chọn `autoAddPartitions` theo quy trình quản trị partition.
- [ ] Đã kiểm tra `minPartitionCount`, producer `partitionCount`, consumer `concurrency` và `instance-count` khi cần.
- [ ] Topic có partition count đủ cho mức song song mong muốn.
- [ ] Replication factor, retention, cleanup policy, compression và ACL được quản lý riêng.
- [ ] Runtime principal chỉ có quyền create/alter/describe cần thiết.
- [ ] Đã kiểm tra `auto.create.topics.enable` ở cấp broker và phân biệt với thuộc tính binder.
- [ ] Đã đánh giá tác động ordering theo key trước khi tăng partition.
- [ ] Dynamic destination có allowlist và giới hạn số lượng.
- [ ] Có integration test với Kafka thật cho topic provisioning và quyền truy cập.
- [ ] Log startup và metric cho biết topic/partition provisioning có thành công.

`autoCreateTopics` quyết định binder có chủ động tạo topic chưa tồn tại hay không; `autoAddPartitions` quyết định binder có tự mở rộng partition của topic hiện có khi cần hay không. Hai thuộc tính này giúp việc phát triển thuận tiện, nhưng trong production cần cân nhắc quyền quản trị, replication, retention, khả năng song song và thứ tự theo key. Quản lý topic có chủ đích giúp ứng dụng khởi động nhất quán và tránh thay đổi tài nguyên Kafka ngoài kế hoạch.
