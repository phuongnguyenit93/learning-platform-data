# Cấu hình cleanup.policy

Kafka lưu record trong partition dưới dạng log chỉ ghi thêm. Khi một record đã được ghi, broker không sửa trực tiếp record đó; việc dọn dữ liệu được thực hiện nền theo chính sách cleanup của topic. Thuộc tính topic **cleanup.policy** quyết định Kafka giữ log theo thời gian/kích thước, giữ giá trị mới nhất theo key, hay kết hợp cả hai cách.

Chọn đúng cleanup policy là quyết định về ý nghĩa dữ liệu. Topic lưu lịch sử sự kiện cần giữ từng record thường dùng delete. Topic biểu diễn trạng thái mới nhất của từng thực thể thường phù hợp với compact. Một số topic cần vừa giữ trạng thái mới nhất vừa giới hạn tuổi của dữ liệu có thể dùng compact,delete.

## Mục tiêu học tập

Sau bài học, bạn có thể:

- Giải thích mục đích và các giá trị hợp lệ của cleanup.policy.
- Phân biệt delete, compact và compact,delete.
- Mô tả log compaction, key, tombstone và cách Kafka xử lý bản ghi bị xóa.
- Hiểu vì sao compaction chạy bất đồng bộ, không xóa record ngay khi có bản ghi mới.
- Chọn các cấu hình liên quan như retention.ms, retention.bytes, delete.retention.ms và min.compaction.lag.ms.
- Tạo và thay đổi cleanup policy bằng Kafka CLI hoặc Spring Kafka Admin.
- Thiết kế key và partition phù hợp để compaction phản ánh đúng trạng thái nghiệp vụ.
- Kiểm thử, quan sát và xử lý các lỗi cấu hình thường gặp.

## 1. cleanup.policy quyết định log được dọn như thế nào

Mỗi topic có một cấu hình cleanup.policy. Các giá trị chính:

| Giá trị | Cách Kafka dọn log | Trường hợp phù hợp |
|---|---|---|
| delete | Xóa các segment log khi dữ liệu vượt giới hạn retention theo thời gian hoặc dung lượng | Event log, audit log, telemetry có thời hạn lưu |
| compact | Giữ lại giá trị mới nhất theo key trong mỗi partition; các bản ghi cũ hơn cùng key có thể được loại bỏ qua compaction | Topic lưu trạng thái hiện tại, changelog, cache state |
| compact,delete | Vừa compact theo key, vừa áp dụng retention để xóa segment cũ | Topic cần giữ trạng thái gần nhất trong một cửa sổ lưu trữ hữu hạn |

Trong cấu hình topic, hai policy có thể được khai báo dưới dạng danh sách phân tách bằng dấu phẩy. Ví dụ: compact,delete.

Nếu không khai báo riêng ở topic, Kafka sử dụng giá trị mặc định từ broker. Cấu hình broker thường đặt log.cleanup.policy mặc định là delete. Khi vận hành, hãy kiểm tra cấu hình hiệu lực của topic thay vì suy luận từ cấu hình mặc định của một môi trường khác.

Điểm quan trọng: cleanup.policy không quyết định consumer đọc record theo thứ tự nào. Nó quyết định dữ liệu cũ được giữ hay có thể bị loại khỏi log sau khi đã ghi.

## 2. Delete policy: giữ log theo retention

Với delete, Kafka giữ các segment theo giới hạn thời gian hoặc dung lượng. Hai cấu hình thường được dùng là:

- retention.ms: tuổi tối đa của dữ liệu theo chính sách retention.
- retention.bytes: dung lượng log tối đa cho mỗi partition theo chính sách retention.

Khi segment đủ cũ hoặc log vượt ngưỡng dung lượng, Kafka đánh dấu segment phù hợp để xóa. Việc xóa diễn ra theo segment và có độ trễ vận hành; không nên xem retention.ms như một bộ hẹn giờ chính xác cho từng record.

Ví dụ topic lưu sự kiện đơn hàng trong 14 ngày:

~~~properties
cleanup.policy=delete
retention.ms=1209600000
~~~

Ví dụ tạo topic bằng Kafka CLI:

~~~bash
bin/kafka-topics.sh \
  --bootstrap-server localhost:9092 \
  --create \
  --topic order-events \
  --partitions 6 \
  --replication-factor 3 \
  --config cleanup.policy=delete \
  --config retention.ms=1209600000
~~~

Delete phù hợp khi lịch sử record là quan trọng trong thời hạn lưu. Khi segment hết hạn, consumer đọc từ đầu có thể không còn nhìn thấy dữ liệu đã bị xóa. Nếu consumer offline lâu hơn retention, nó có thể gặp offset out of range và cần xử lý theo reset policy hoặc quy trình khôi phục phù hợp.

Retention không thay thế backup. Nếu dữ liệu cần lưu lâu dài để đáp ứng yêu cầu lưu trữ hoặc khôi phục, hãy thiết kế hệ thống lưu trữ riêng thay vì chỉ dựa vào Kafka topic.

## 3. Compact policy: giữ trạng thái mới nhất theo key

Log compaction giữ lại bản ghi mới nhất theo key trong mỗi partition. Kafka không cần giữ mọi lần cập nhật nếu mục tiêu của topic là tái tạo trạng thái hiện tại.

Ví dụ topic customer-state nhận các cập nhật:

~~~text
offset  key       value
------  --------  ------------------
0       customer-1  name=An
1       customer-2  name=Binh
2       customer-1  name=An, city=Hanoi
3       customer-3  name=Chi
4       customer-1  name=An, city=DaNang
5       customer-2  name=Binh, tier=Gold
~~~

Sau khi compaction hoàn tất trên các segment đủ điều kiện, Kafka có thể giữ lại trạng thái mới nhất cho từng key:

~~~text
offset  key         value
------  ----------  -----------------------------
3       customer-3  name=Chi
4       customer-1  name=An, city=DaNang
5       customer-2  name=Binh, tier=Gold
~~~

Đây là hình minh họa kết quả logic. Trong log thực tế, offset không được đánh lại liên tục từ 0 và có thể xuất hiện khoảng trống vì các record cũ đã bị loại bỏ. Kafka giữ nguyên ý nghĩa offset để consumer group có thể tiếp tục đọc theo vị trí đã commit.

### Compaction chỉ áp dụng trong từng partition

Cleaner so sánh key trong phạm vi partition. Kafka không thực hiện một phép gộp key toàn cục trên mọi partition của topic.

Vì vậy:

- Cùng một key cần được định tuyến ổn định vào cùng partition nếu muốn compaction giữ một trạng thái duy nhất cho key đó.
- Producer thường dùng business key, ví dụ customerId hoặc accountId.
- Tăng số partition có thể làm thay đổi phép ánh xạ key sang partition. Các bản ghi cũ và mới của cùng key có thể nằm ở hai partition khác nhau, khiến compaction không loại trùng giữa chúng.
- Nếu producer chỉ gửi record không có key, compaction không thể dùng key để nhận diện trạng thái và các record đó không được compact theo cách giữ giá trị mới nhất.

Ví dụ gửi record có key trong Spring Kafka:

~~~java
kafkaTemplate.send("customer-state", customerId, customerState);
~~~

Nếu key là null, ứng dụng đã bỏ mất định danh mà compaction cần. Hãy xác định key trước khi chọn compact.

### Compaction không xóa record ngay lập tức

Kafka log cleaner chạy nền. Record mới có thể tạm thời cùng tồn tại với các phiên bản cũ. Một segment đang hoạt động (active segment) thường chưa được compact cho đến khi được roll và trở thành segment đủ điều kiện. Việc compaction còn phụ thuộc vào lượng dữ liệu chưa compact và tài nguyên cleaner.

Vì vậy, consumer đọc topic compacted không được giả định rằng tại mọi thời điểm log chỉ có một record cho mỗi key. Trong lúc compaction chưa chạy xong, consumer có thể vẫn đọc được nhiều phiên bản của cùng key.

## 4. Tombstone: biểu diễn thao tác xóa một key

Trong compacted topic, ứng dụng biểu diễn việc xóa trạng thái của một key bằng cách gửi record có key và value null. Record này được gọi là **tombstone**.

Ví dụ:

~~~java
// Xóa trạng thái hiện tại của customer-42 trong compacted topic.
kafkaTemplate.send("customer-state", "customer-42", null);
~~~

Tombstone không có nghĩa Kafka xóa ngay mọi record cũ của key đó. Nó đánh dấu rằng trạng thái hiện tại của key đã bị xóa. Khi cleaner xử lý log, các phiên bản cũ của key có thể bị loại bỏ cùng với tombstone theo vòng đời compaction.

### delete.retention.ms

delete.retention.ms quy định khoảng thời gian tombstone được giữ lại để consumer có cơ hội quan sát thông tin xóa khi đọc lại compacted log. Sau khi tombstone đủ điều kiện hết hạn và cleaner xử lý, tombstone có thể bị loại bỏ.

Cấu hình này đặc biệt quan trọng với consumer dùng compacted topic như changelog để tái tạo state store. Nếu consumer đọc lại từ đầu quá chậm hoặc offline lâu hơn cửa sổ tombstone, nó có thể không nhìn thấy dấu xóa trong khi vẫn đọc dữ liệu cũ theo cách không mong muốn.

Ví dụ:

~~~properties
cleanup.policy=compact
delete.retention.ms=86400000
~~~

Giá trị trên minh họa cửa sổ một ngày. Hãy chọn cửa sổ đủ lớn so với thời gian tối đa mà consumer cần để khởi tạo lại state hoặc bắt kịp log.

Tombstone cũng có thể được dùng trong luồng cập nhật trạng thái. Consumer cần phân biệt value null mang ý nghĩa xóa với một payload JSON hợp lệ có trường dữ liệu rỗng. Deserializer và listener phải giữ được ngữ nghĩa null này.

## 5. compact và compact,delete khác nhau thế nào?

Hai cấu hình đều có compaction, nhưng compact,delete bổ sung giới hạn retention theo thời gian hoặc dung lượng.

| Tiêu chí | compact | compact,delete |
|---|---|---|
| Giữ phiên bản mới nhất theo key | Có | Có |
| Xóa segment theo retention.ms/retention.bytes | Không áp dụng chính sách delete của topic | Có |
| Dữ liệu cũ không còn key mới hơn | Có thể vẫn tồn tại cho đến khi compaction đủ điều kiện | Có thể bị xóa khi segment hết hạn |
| Tombstone | Có, theo delete.retention.ms | Có, đồng thời chịu tác động của retention |
| Mục tiêu điển hình | Changelog/state topic cần tái tạo trạng thái mới nhất | State topic chỉ cần lưu trong một cửa sổ thời gian/dung lượng |

Với compact, Kafka có thể giữ bản ghi mới nhất của key trong log lâu dài, trừ khi topic bị xóa hoặc có thay đổi cấu hình/hoạt động quản trị khác. Với compact,delete, segment cũ vẫn có thể bị xóa theo retention ngay cả khi compaction đã giữ một số trạng thái trong segment đó.

Không nên chọn compact,delete chỉ vì muốn “dọn gọn hơn”. Nếu consumer cần dựng lại đầy đủ trạng thái hiện tại cho tất cả key, hãy bảo đảm retention không xóa mất bản ghi cuối cùng cần thiết trước khi state được snapshot hoặc chuyển sang hệ thống lưu trữ khác.

Ví dụ:

~~~properties
cleanup.policy=compact,delete
retention.ms=2592000000
delete.retention.ms=86400000
~~~

Ví dụ này giữ log trong chính sách retention 30 ngày và dùng cửa sổ tombstone một ngày. Các giá trị thực tế phải dựa trên yêu cầu khôi phục và tốc độ consumer.

## 6. Các cấu hình compaction liên quan

cleanup.policy là công tắc chọn chính sách. Các thuộc tính sau điều khiển thời điểm và cách cleaner làm việc.

| Thuộc tính | Ý nghĩa |
|---|---|
| min.cleanable.dirty.ratio | Tỷ lệ dữ liệu chưa compact tối thiểu để log đủ điều kiện được cleaner chọn theo ngưỡng này |
| min.compaction.lag.ms | Thời gian tối thiểu một record phải tồn tại trước khi có thể được compact |
| max.compaction.lag.ms | Giới hạn độ trễ tối đa mục tiêu trước khi record đủ điều kiện cần được xem xét compact |
| delete.retention.ms | Thời gian giữ tombstone để consumer có cơ hội quan sát thao tác xóa |
| segment.ms | Khoảng thời gian tối đa trước khi log segment được roll theo điều kiện thời gian |
| segment.bytes | Kích thước segment mục tiêu trước khi roll theo dung lượng |

### min.cleanable.dirty.ratio

Cleaner đánh giá phần log chưa compact (dirty log) so với tổng log. Khi tỷ lệ đạt ngưỡng min.cleanable.dirty.ratio, log có thể đủ điều kiện để cleaner xử lý, tùy tải và tài nguyên cleaner.

- Giá trị thấp hơn thường khiến compaction được kích hoạt thường xuyên hơn, tăng I/O và hoạt động cleaner.
- Giá trị cao hơn giảm tần suất cleaner chạy nhưng có thể làm các phiên bản cũ tồn tại lâu hơn.

Không nên xem tỷ lệ này là cam kết rằng compaction bắt đầu đúng lúc tỷ lệ đạt ngưỡng. Cleaner còn phải có tài nguyên và log segment phải đủ điều kiện.

### min.compaction.lag.ms và max.compaction.lag.ms

min.compaction.lag.ms giữ record trong log ít nhất một khoảng thời gian trước khi compaction có thể loại bỏ phiên bản cũ. Cấu hình này hữu ích khi consumer cần một khoảng thời gian để đọc các thay đổi gần nhất.

max.compaction.lag.ms đặt giới hạn độ trễ tối đa mục tiêu để record đủ điều kiện được xem xét compact. Đây không phải thời hạn chính xác đảm bảo cleaner hoàn tất mọi thao tác; tải broker, segment và tài nguyên cleaner vẫn ảnh hưởng thời gian thực tế.

Ví dụ topic cần giữ các thay đổi ít nhất 10 phút trước khi compact:

~~~properties
cleanup.policy=compact
min.compaction.lag.ms=600000
~~~

### Broker log cleaner

Compaction cần log cleaner hoạt động trên broker. Các cấu hình broker liên quan gồm log.cleaner.enable và các tham số điều phối tài nguyên cleaner. Nếu cleaner bị tắt hoặc không có đủ tài nguyên, compacted topic vẫn nhận record nhưng các phiên bản cũ có thể tồn tại lâu hơn dự kiến.

Khi vận hành, kiểm tra cả topic config và broker config. Chỉ đặt cleanup.policy=compact không có nghĩa mọi record cũ lập tức được dọn.

## 7. Cấu hình topic bằng Kafka CLI

Có thể tạo topic với cleanup policy ngay từ đầu:

~~~bash
bin/kafka-topics.sh \
  --bootstrap-server localhost:9092 \
  --create \
  --topic customer-state \
  --partitions 6 \
  --replication-factor 3 \
  --config cleanup.policy=compact \
  --config delete.retention.ms=86400000 \
  --config min.compaction.lag.ms=60000
~~~

Để thay đổi cấu hình topic đã tồn tại, dùng kafka-configs.sh:

~~~bash
bin/kafka-configs.sh \
  --bootstrap-server localhost:9092 \
  --entity-type topics \
  --entity-name customer-state \
  --alter \
  --add-config cleanup.policy=compact
~~~

Kiểm tra cấu hình hiệu lực:

~~~bash
bin/kafka-configs.sh \
  --bootstrap-server localhost:9092 \
  --entity-type topics \
  --entity-name customer-state \
  --describe
~~~

Để chuyển từ compact sang compact,delete:

~~~bash
bin/kafka-configs.sh \
  --bootstrap-server localhost:9092 \
  --entity-type topics \
  --entity-name customer-state \
  --alter \
  --add-config cleanup.policy=compact,delete
~~~

Tên script có thể kết thúc bằng .sh hoặc .bat tùy hệ điều hành và bản phân phối Kafka. Với cụm KRaft hiện đại, dùng bootstrap-server; không cần ZooKeeper argument.

Khi xóa một cấu hình override, dùng --delete-config với đúng tên cấu hình để topic quay về giá trị mặc định từ broker. Hãy xác nhận cấu hình hiện tại trước khi xóa override vì giá trị kế thừa có thể khác giữa các môi trường.

## 8. Khai báo topic bằng Spring Kafka

Spring Kafka có thể tạo topic lúc khởi động thông qua KafkaAdmin và bean NewTopic. Ví dụ:

~~~java
@Configuration
public class TopicConfiguration {

    @Bean
    public NewTopic customerStateTopic() {
        return TopicBuilder.name("customer-state")
                .partitions(6)
                .replicas(3)
                .config(TopicConfig.CLEANUP_POLICY_CONFIG,
                        TopicConfig.CLEANUP_POLICY_COMPACT)
                .config(TopicConfig.DELETE_RETENTION_MS_CONFIG, "86400000")
                .config(TopicConfig.MIN_COMPACTION_LAG_MS_CONFIG, "60000")
                .build();
    }
}
~~~

Ví dụ trên khai báo topic compacted cùng một số cấu hình liên quan. KafkaAdmin cần được cấu hình để kết nối đúng cluster và tài khoản chạy ứng dụng phải có quyền tạo topic.

Một điểm cần phân biệt: bean NewTopic chủ yếu mô tả topic cần tạo. Không nên mặc định rằng thay đổi thuộc tính trong bean sẽ luôn sửa cấu hình của topic đã tồn tại. Với topic hiện hữu, hãy dùng cơ chế alter topic configuration như Kafka CLI hoặc AdminClient theo quy trình quản trị của hệ thống.

Nếu ứng dụng khai báo NewTopic trong nhiều môi trường, hãy đưa partitions, replication factor và cleanup policy vào cấu hình theo môi trường thay vì hard-code các giá trị không phù hợp cho mọi cluster.

## 9. Thiết kế compacted topic cho trạng thái nghiệp vụ

Một compacted topic thường được dùng như changelog của trạng thái hiện tại. Mỗi record mang key xác định thực thể và value chứa trạng thái mới nhất.

Ví dụ:

| Key | Value | Ý nghĩa |
|---|---|---|
| account-100 | balance=500 | Số dư mới nhất của tài khoản |
| account-101 | balance=120 | Số dư mới nhất của tài khoản |
| account-100 | balance=450 | Cập nhật trạng thái mới của account-100 |
| account-101 | null | Xóa trạng thái account-101 |

Các nguyên tắc thiết kế:

1. Dùng key ổn định, duy nhất theo thực thể nghiệp vụ.
2. Gửi snapshot trạng thái đầy đủ nếu consumer cần dựng state độc lập; nếu value chỉ là delta, consumer phải áp dụng toàn bộ chuỗi thay đổi còn lại theo đúng hợp đồng.
3. Gửi tombstone có key khi xóa thực thể.
4. Giữ cùng key trong cùng partition; cân nhắc tác động khi tăng số partition.
5. Đặt delete.retention.ms đủ dài cho consumer khởi tạo lại hoặc bắt kịp dữ liệu.
6. Không dùng compact nếu nghiệp vụ cần giữ từng event trung gian như một lịch sử bất biến.

Compaction không biến Kafka thành database key-value có truy vấn tùy ý. Consumer vẫn đọc log tuần tự theo partition; muốn tra cứu nhanh theo key, ứng dụng có thể dựng state store hoặc dùng hệ thống lưu trữ phù hợp.

## 10. Khi nào không nên dùng compact?

Không nên dùng compact cho topic mà mọi event đều có giá trị lịch sử độc lập.

Ví dụ audit log cần giữ tất cả hành động:

~~~text
UserRegistered
EmailChanged
PasswordReset
RoleGranted
RoleRevoked
~~~

Nếu tất cả record dùng cùng userId làm key và topic compacted, Kafka có thể loại bỏ các event trung gian, chỉ giữ event mới nhất theo key sau compaction. Khi đó audit trail không còn đầy đủ.

Tương tự, event sourcing thường cần giữ toàn bộ event để dựng lại aggregate state. Compaction có thể phá vỡ mục tiêu đó. Hãy dùng delete với retention phù hợp hoặc thiết kế topic lưu snapshot riêng bên cạnh event log.

Một mẫu kiến trúc phổ biến:

- Topic order-events dùng delete để giữ lịch sử event trong thời hạn quy định.
- Topic order-state dùng compact để giữ trạng thái mới nhất của mỗi order.
- Consumer cập nhật order-state từ order-events theo một quy trình có kiểm soát.

Hai topic có mục đích khác nhau, do đó có thể dùng cleanup policy khác nhau.

## 11. Tác động đến consumer và offset

Compaction loại bỏ record cũ nhưng không đánh lại offset của record còn lại. Vì vậy, consumer có thể đọc:

~~~text
offset 10 -> key A, value v3
offset 14 -> key B, value v2
offset 19 -> key C, value v5
~~~

Khoảng trống offset là bình thường trong compacted topic. Không được giả định offset tiếp theo luôn bằng offset hiện tại cộng một, hoặc số offset phản ánh chính xác số record còn tồn tại.

Consumer group commit offset theo vị trí đọc tiếp theo. Sau compaction, consumer khởi tạo lại từ đầu có thể gặp các khoảng trống do record cũ đã bị loại. Điều này không phải mất dữ liệu ngoài chính sách cleanup.

Với compacted topic, consumer nên:

- Chấp nhận offset không liên tục.
- Xử lý nhiều phiên bản của cùng key nếu compaction chưa hoàn tất.
- Xử lý tombstone như thao tác xóa state.
- Không phụ thuộc thứ tự giữa các partition.
- Thiết kế phục hồi state theo chính sách retention và delete.retention.ms.

Compaction không làm thay đổi offset của record còn lại, nên consumer đang hoạt động có thể tiếp tục dùng offset đã commit. Tuy nhiên, consumer offline lâu vẫn phải xét retention, tombstone và khả năng offset cũ đã nằm ngoài log start offset.

## 12. Kiểm thử và quan sát

Có thể kiểm thử compacted topic bằng cách tạo topic có cleanup.policy=compact, gửi nhiều record cùng key, chờ segment được roll và cleaner xử lý, sau đó đọc lại từ đầu để quan sát các phiên bản cũ đã bị loại.

Kịch bản nên bao gồm:

- Gửi nhiều giá trị cho cùng một key và xác nhận trạng thái cuối cùng được giữ sau compaction.
- Gửi các key khác nhau và xác nhận mỗi key có trạng thái mới nhất.
- Gửi tombstone và xác nhận consumer xử lý null value như thao tác xóa.
- Đọc compacted topic trước khi cleaner chạy để xác nhận ứng dụng chịu được nhiều phiên bản của cùng key.
- Khởi tạo lại state consumer và kiểm tra cửa sổ delete.retention.ms.
- Thử compact,delete cùng retention để xác nhận dữ liệu cũ có thể bị xóa theo chính sách.
- Kiểm tra consumer không giả định offset liên tục.

Không nên viết test phụ thuộc vào một thời điểm compaction cố định. Cleaner chạy bất đồng bộ và điều kiện segment/dirty ratio ảnh hưởng thời điểm xử lý. Test tích hợp nên đồng bộ bằng trạng thái quan sát được và có timeout đủ lớn, thay vì dùng sleep ngắn rồi kết luận compaction không hoạt động.

Các chỉ số vận hành hữu ích:

- Log size và số segment của topic/partition.
- Tốc độ ghi và tốc độ I/O của log cleaner.
- Cleaner backlog, thời gian compaction và tài nguyên broker.
- Consumer lag và thời gian khởi tạo state.
- Số tombstone và tuổi tombstone trong quy trình khởi tạo lại consumer.
- Retention và log start offset theo partition.

Nếu topic tăng dung lượng liên tục, hãy kiểm tra cleaner có hoạt động không, dirty ratio có đạt ngưỡng không, segment có được roll không và broker có đủ tài nguyên cleaner không.

## 13. Các lỗi cấu hình thường gặp

**Dùng compact cho audit log.** Compaction loại bỏ các phiên bản cũ của cùng key, làm mất lịch sử event trung gian. Chọn delete nếu cần giữ từng event.

**Gửi record không có key vào compacted topic.** Kafka không có định danh để giữ giá trị mới nhất theo thực thể. Producer phải gửi key ổn định.

**Tưởng tombstone xóa dữ liệu ngay lập tức.** Tombstone được giữ một khoảng thời gian và compaction chạy nền. Consumer phải chấp nhận dữ liệu cũ còn tồn tại trong lúc cleaner chưa xử lý xong.

**Đặt delete.retention.ms quá ngắn.** Consumer khởi tạo lại chậm có thể bỏ lỡ tombstone và dựng sai trạng thái. Chọn thời gian đủ cho cửa sổ phục hồi.

**Tăng partition mà không đánh giá key routing.** Cùng key có thể được ánh xạ sang partition khác sau thay đổi partition count; compaction không hợp nhất key giữa partition.

**Chọn compact,delete nhưng retention quá ngắn.** Segment chứa trạng thái cuối cùng của key có thể bị xóa theo retention, khiến consumer không còn dựng được đầy đủ state.

**Cho rằng NewTopic luôn cập nhật topic đã tồn tại.** Cơ chế tạo topic và thay đổi cấu hình topic hiện hữu cần được quản trị riêng.

## 14. Checklist chọn cleanup policy

- [ ] Topic lưu event history hay trạng thái mới nhất?
- [ ] Nếu dùng compact, mọi record nghiệp vụ có key ổn định không?
- [ ] Cùng key có được định tuyến vào cùng partition không?
- [ ] Consumer có xử lý được tombstone và nhiều phiên bản của cùng key không?
- [ ] delete.retention.ms đủ dài cho thời gian khởi tạo lại state?
- [ ] min.compaction.lag.ms có cần thiết để consumer đọc các thay đổi gần nhất?
- [ ] max.compaction.lag.ms và min.cleanable.dirty.ratio có phù hợp với mục tiêu vận hành?
- [ ] Broker log cleaner đã được bật và có đủ tài nguyên?
- [ ] Nếu dùng compact,delete, retention.ms/retention.bytes có giữ đủ dữ liệu để phục hồi?
- [ ] Đã kiểm thử compaction bất đồng bộ, offset không liên tục và tombstone?

## Kết luận

cleanup.policy quyết định Kafka giữ log theo retention, theo trạng thái mới nhất của key, hay kết hợp cả hai. Delete phù hợp với event history có thời hạn lưu; compact phù hợp với changelog/state topic cần trạng thái mới nhất; compact,delete kết hợp compaction với giới hạn retention. Compaction chạy nền, hoạt động trong từng partition và dựa vào key; tombstone biểu diễn thao tác xóa và cần được giữ đủ lâu để consumer quan sát. Trong Spring Kafka, hãy chọn key và cleanup policy theo mục đích dữ liệu, cấu hình topic rõ ràng, rồi kiểm thử consumer với nhiều phiên bản record, tombstone và offset không liên tục.

