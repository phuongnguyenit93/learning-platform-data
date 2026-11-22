# Kiểm thử key, thứ tự, offset và khả năng phát lại

Trong Kafka, một bài kiểm thử luồng sự kiện cần xác nhận nhiều hơn việc producer gửi thành công và consumer nhận được bản tin. Với luồng đơn hàng, chẳng hạn, các sự kiện của cùng một đơn hàng phải đi qua cùng partition để giữ thứ tự; consumer chỉ được xác nhận offset sau khi xử lý thành công; khi cần chạy lại, hệ thống phải đọc lại được dữ liệu còn lưu và không tạo tác dụng phụ trùng lặp.

Bài học này thuộc chương **Kiểm thử** của module **KAFKA**. Nội dung tập trung vào cách kiểm chứng key, thứ tự bản tin, offset của consumer và khả năng phát lại trong một hệ thống event streaming dùng Apache Kafka, Java và Spring Kafka.

Sau bài học, người học có thể:

- Kiểm tra key được định tuyến vào partition phù hợp và hiểu giới hạn của bảo đảm thứ tự.
- Viết integration test xác nhận thứ tự theo offset trong cùng partition.
- Phân biệt vị trí đọc hiện tại với offset đã commit.
- Kiểm tra commit sau xử lý và phát lại bằng seek hoặc consumer group mới.
- Thiết kế test ổn định khi có nhiều partition, retry, consumer group và dữ liệu được giữ theo retention.

## 1. Những bảo đảm cần kiểm thử

Kafka lưu bản tin trong các partition. Mỗi bản tin có thể mang key, value, partition, offset, timestamp và header. Key thường được dùng để chọn partition; offset xác định vị trí bản tin trong một partition.

| Thành phần | Điều cần xác nhận | Giới hạn cần nhớ |
|---|---|---|
| Key | Các bản tin cùng key được định tuyến nhất quán | Kết quả phụ thuộc partitioner, cách serialize key và số partition |
| Partition | Bản tin được ghi vào partition dự kiến | Không nên mặc định hai key khác nhau luôn nằm ở hai partition khác nhau |
| Thứ tự | Bản tin trong cùng partition được đọc theo thứ tự offset | Kafka không tạo một thứ tự tổng thể giữa nhiều partition |
| Offset | Consumer commit đúng vị trí sau khi xử lý | Offset là vị trí trong partition, không phải số thứ tự nghiệp vụ |
| Replay | Consumer có thể đọc lại từ vị trí đã chọn | Chỉ đọc lại được dữ liệu vẫn còn trong log và còn nhìn thấy theo isolation level |

### Key và partition

Với producer dùng partitioner mặc định và bản tin có key, Kafka dùng byte của key đã serialize để chọn partition. Vì vậy, cùng một key thường đi vào cùng partition khi số partition và cấu hình partitioner không đổi. Điều này cho phép consumer xử lý các sự kiện của cùng một thực thể theo thứ tự trong partition đó.

Không nên viết test khẳng định hai key khác nhau phải nằm ở hai partition khác nhau. Hai key khác nhau hoàn toàn có thể được ánh xạ vào cùng partition. Hợp đồng hữu ích hơn là: nhiều bản tin có cùng key phải được định tuyến vào cùng partition trong cùng điều kiện cấu hình.

Kết quả định tuyến cũng có thể thay đổi khi:

- Ứng dụng thay đổi key serializer, khiến byte của key thay đổi.
- Ứng dụng dùng custom partitioner.
- Số partition của topic thay đổi.
- Producer chỉ định partition trực tiếp thay vì để partitioner lựa chọn.

Key null không có byte key để hash như key thông thường; key rỗng vẫn là một giá trị riêng được serialize và có thể được hash. Với key null, partitioner có thể phân phối bản tin theo cơ chế khác, chẳng hạn sticky partitioning. Nếu nghiệp vụ yêu cầu thứ tự theo thực thể, producer cần gửi key ổn định và có ý nghĩa.

Một thay đổi số partition cần được xem là thay đổi hợp đồng định tuyến. Khi số partition tăng, cùng một key có thể được ánh xạ sang partition mới. Các sự kiện cũ và mới của thực thể đó khi ấy có thể nằm ở hai partition khác nhau và được xử lý đồng thời. Nếu thứ tự xuyên suốt của một thực thể là yêu cầu bắt buộc, hãy kiểm soát việc thay đổi partition và kiểm thử chiến lược chuyển đổi trước khi áp dụng.

### Thứ tự

Kafka bảo đảm thứ tự bản ghi trong một partition theo thứ tự chúng được append vào log. Consumer đọc partition đó theo offset tăng dần. Kafka không bảo đảm thứ tự toàn cục giữa các partition, kể cả khi các bản tin có timestamp gần nhau.

Vì vậy, test thứ tự nên tập trung vào đúng phạm vi nghiệp vụ:

- Với luồng đơn hàng, kiểm tra các sự kiện cùng **orderId** có cùng partition và offset tăng dần.
- Với luồng có nhiều partition, không so sánh thứ tự tuyệt đối của các key độc lập.
- Với nhiều producer đồng thời, không giả định thứ tự gửi ở phía ứng dụng là thứ tự broker nhận được nếu không có cơ chế phối hợp.
- Với listener xử lý bất đồng bộ, kiểm tra cả thứ tự hoàn tất tác vụ nghiệp vụ. Thứ tự consumer nhận bản tin không tự động bảo đảm thứ tự các tác dụng phụ trong thread pool.

Nếu producer cần duy trì thứ tự khi retry, hãy cấu hình idempotence phù hợp và kiểm tra các thiết lập liên quan đến số request đang chờ trên một connection. Với Kafka client hiện đại, idempotence có các ràng buộc tương thích về **max.in.flight.requests.per.connection**; nên khai báo cấu hình chủ đích thay vì dựa vào mặc định khác nhau giữa các phiên bản.

### Offset và commit

Offset chỉ có ý nghĩa trong phạm vi một partition. Ví dụ, offset 25 của partition 0 không có quan hệ thứ tự với offset 25 của partition 1.

Cần phân biệt hai khái niệm:

- **Position** là vị trí tiếp theo mà consumer sẽ đọc. Position có thể tiến lên ngay sau khi **poll()** trả bản ghi, trước khi ứng dụng xử lý xong bản ghi đó.
- **Committed offset** là vị trí consumer group đã lưu để tiếp tục ở lần chạy sau. Khi xử lý bản ghi offset 25 xong, consumer thường commit offset 26, tức vị trí tiếp theo cần đọc.

Nếu ứng dụng commit trước khi hoàn tất tác dụng phụ, một lần khởi động lại có thể bỏ qua bản tin chưa được xử lý. Nếu ứng dụng xử lý xong nhưng chưa commit, bản tin có thể được giao lại sau khi consumer khởi động lại. Đây là lý do phổ biến khiến hệ thống at-least-once cần xử lý idempotent.

Offset cũng không phải bộ đếm số lượng bản tin đã xử lý. Topic compacted, bản tin thuộc transaction bị abort hoặc isolation level **read_committed** có thể khiến consumer quan sát các khoảng offset bị bỏ qua. Test nên so sánh vị trí và quan hệ tăng giảm, không nên suy ra số bản tin chỉ bằng phép trừ offset trong mọi loại topic.

## 2. Thiết kế bộ kiểm thử

Tách kiểm thử theo ranh giới để lỗi dễ xác định:

| Loại test | Phạm vi | Ví dụ assertion |
|---|---|---|
| Unit test | Custom partitioner, key serializer, logic tạo event | Key được serialize ổn định; partitioner trả partition hợp lệ |
| Integration test producer | Producer và broker thật hoặc broker nhúng | Metadata trả về có key, partition và offset đúng kỳ vọng |
| Integration test consumer | Consumer group và broker | Bản tin cùng key được đọc theo offset; group commit đúng vị trí |
| Listener test | Spring Kafka container và handler | Xử lý thành công mới acknowledge; lỗi được retry theo cấu hình |
| Replay test | Seek hoặc group offset | Bản tin cũ được đọc lại; xử lý lặp không nhân đôi tác dụng phụ |

Với các hợp đồng liên quan đến partition, offset và commit, hãy dùng integration test có broker. Unit test có thể kiểm tra logic partitioner hoặc serializer nhưng không chứng minh được broker đã ghi và consumer group đã lưu offset như mong đợi.

Để test ổn định:

1. Dùng topic riêng cho test hoặc tạo topic có tên duy nhất cho mỗi lần chạy.
2. Dùng group id riêng cho từng test. Không để test phụ thuộc offset còn sót từ lần chạy trước.
3. Tắt auto commit khi test cần kiểm soát chính xác thời điểm commit.
4. Chờ điều kiện bằng deadline và **poll()** thay vì **Thread.sleep()** với thời gian cố định.
5. Chỉ khẳng định partition cụ thể khi partition là một phần của hợp đồng, ví dụ custom partitioner đã được kiểm thử riêng.
6. Dọn consumer, producer, container và topic test theo vòng đời fixture.

## 3. Integration test với Spring Kafka và Kafka Consumer

Ví dụ dưới đây kiểm tra ba điều trong một topic test có ba partition và đang rỗng: hai bản tin cùng key đi vào cùng partition, offset của bản tin sau lớn hơn bản tin trước, và consumer có thể commit rồi seek về offset cũ để đọc lại.

Giả định test fixture đã khởi chạy broker, tạo một topic riêng cho test và cấu hình **KafkaTemplate<String, String>** dùng String serializer. **bootstrapServers** là địa chỉ broker của fixture. Có thể dùng Testcontainers hoặc Embedded Kafka; cách khởi tạo broker tùy phiên bản thư viện trong dự án.

    import static org.junit.jupiter.api.Assertions.assertEquals;
    import static org.junit.jupiter.api.Assertions.assertNotNull;
    import static org.junit.jupiter.api.Assertions.assertTrue;

    import java.time.Duration;
    import java.util.ArrayList;
    import java.util.List;
    import java.util.Map;
    import java.util.Properties;
    import java.util.Set;
    import java.util.UUID;
    import java.util.concurrent.TimeUnit;

    import org.apache.kafka.clients.consumer.ConsumerConfig;
    import org.apache.kafka.clients.consumer.KafkaConsumer;
    import org.apache.kafka.clients.consumer.OffsetAndMetadata;
    import org.apache.kafka.clients.consumer.ConsumerRecord;
    import org.apache.kafka.common.TopicPartition;
    import org.apache.kafka.common.serialization.StringDeserializer;
    import org.springframework.kafka.core.KafkaTemplate;
    import org.springframework.kafka.support.SendResult;

    void shouldKeepKeyOrderCommitAndReplay(
            KafkaTemplate<String, String> producer,
            String bootstrapServers,
            String topic) throws Exception {

        String key = "order-42";

        SendResult<String, String> sentFirst =
                producer.send(topic, key, "{\"seq\":1}")
                        .get(10, TimeUnit.SECONDS);
        SendResult<String, String> sentSecond =
                producer.send(topic, key, "{\"seq\":2}")
                        .get(10, TimeUnit.SECONDS);

        var firstMetadata = sentFirst.getRecordMetadata();
        var secondMetadata = sentSecond.getRecordMetadata();

        assertEquals(firstMetadata.partition(), secondMetadata.partition());
        assertTrue(firstMetadata.offset() < secondMetadata.offset());

        Properties properties = new Properties();
        properties.put(ConsumerConfig.BOOTSTRAP_SERVERS_CONFIG, bootstrapServers);
        properties.put(ConsumerConfig.GROUP_ID_CONFIG, "test-" + UUID.randomUUID());
        properties.put(ConsumerConfig.KEY_DESERIALIZER_CLASS_CONFIG,
                StringDeserializer.class);
        properties.put(ConsumerConfig.VALUE_DESERIALIZER_CLASS_CONFIG,
                StringDeserializer.class);
        properties.put(ConsumerConfig.AUTO_OFFSET_RESET_CONFIG, "earliest");
        properties.put(ConsumerConfig.ENABLE_AUTO_COMMIT_CONFIG, "false");

        try (KafkaConsumer<String, String> consumer =
                     new KafkaConsumer<>(properties)) {
            consumer.subscribe(List.of(topic));

            List<ConsumerRecord<String, String>> received = new ArrayList<>();
            long deadline = System.nanoTime()
                    + TimeUnit.SECONDS.toNanos(10);

            while (received.size() < 2 && System.nanoTime() < deadline) {
                for (ConsumerRecord<String, String> record
                        : consumer.poll(Duration.ofMillis(200))) {
                    if (key.equals(record.key())) {
                        received.add(record);
                    }
                }
            }

            assertEquals(2, received.size(),
                    "Consumer phải nhận đủ hai bản tin của key đang kiểm tra");

            ConsumerRecord<String, String> firstRead = received.get(0);
            ConsumerRecord<String, String> secondRead = received.get(1);

            assertEquals(firstMetadata.partition(), firstRead.partition());
            assertEquals(firstRead.partition(), secondRead.partition());
            assertEquals(firstMetadata.offset(), firstRead.offset());
            assertTrue(firstRead.offset() < secondRead.offset());

            TopicPartition partition =
                    new TopicPartition(topic, firstRead.partition());
            long nextOffset = secondRead.offset() + 1;

            consumer.commitSync(Map.of(
                    partition, new OffsetAndMetadata(nextOffset)));

            OffsetAndMetadata committed =
                    consumer.committed(Set.of(partition)).get(partition);
            assertNotNull(committed);
            assertEquals(nextOffset, committed.offset());

            consumer.seek(partition, firstRead.offset());

            boolean firstRecordWasReplayed = false;
            long replayDeadline = System.nanoTime()
                    + TimeUnit.SECONDS.toNanos(5);

            while (!firstRecordWasReplayed
                    && System.nanoTime() < replayDeadline) {
                for (ConsumerRecord<String, String> record
                        : consumer.poll(Duration.ofMillis(200))) {
                    if (record.partition() == partition.partition()
                            && record.offset() == firstRead.offset()) {
                        firstRecordWasReplayed = true;
                        break;
                    }
                }
            }

            assertTrue(firstRecordWasReplayed,
                    "Consumer phải đọc lại được bản tin sau khi seek");
        }
    }

Đây là một test tích hợp minh họa. Trong dự án thực tế, đặt phương thức trong test class có fixture quản lý broker và topic. Topic phải mới hoặc rỗng để phép so sánh offset đầu tiên không bị ảnh hưởng bởi dữ liệu từ test khác. Nếu dùng Kafka client cũ chưa có overload **committed(Set<TopicPartition>)**, dùng overload tương ứng với phiên bản client đang được dự án quản lý.

Test trên xác nhận định tuyến và thứ tự ở phía broker, sau đó kiểm tra commit và replay ở phía consumer. Nó chưa chứng minh logic nghiệp vụ của listener là idempotent; phần đó cần một test riêng kiểm tra trạng thái hoặc bản ghi nghiệp vụ sau khi cùng event được xử lý nhiều lần.

## 4. Kiểm thử listener và thời điểm acknowledge

Với Spring Kafka, thời điểm commit phụ thuộc acknowledgment mode của listener container. Nếu dùng manual acknowledgment, handler nên acknowledge sau khi thao tác nghiệp vụ đã thành công:

    @KafkaListener(
            topics = "orders",
            groupId = "order-projection",
            containerFactory = "manualAckFactory")
    public void onOrder(
            ConsumerRecord<String, OrderEvent> record,
            Acknowledgment acknowledgment) {

        projection.apply(record.value());
        acknowledgment.acknowledge();
    }

Trong ví dụ, **manualAckFactory** cần được cấu hình với **AckMode.MANUAL** hoặc **AckMode.MANUAL_IMMEDIATE** theo chủ đích của ứng dụng. Hai chế độ có cách gom và commit acknowledgment khác nhau; test phải phản ánh đúng cấu hình đang chạy.

Một kịch bản integration test hữu ích:

1. Gửi một event có key và event id đã biết.
2. Cho listener xử lý thành công, sau đó kiểm tra offset đã commit theo acknowledgment mode.
3. Gửi event tiếp theo và làm handler phát sinh lỗi trước khi acknowledge.
4. Xác nhận offset không vượt qua event chưa xử lý thành công, theo chính sách error handler và retry đang cấu hình.
5. Khởi động lại container hoặc để retry diễn ra, rồi xác nhận event được giao lại và xử lý đúng.

Không chỉ kiểm tra số lần listener được gọi. Hãy kiểm tra kết quả nghiệp vụ, chẳng hạn số dòng trong bảng projection, trạng thái đơn hàng hoặc một event idempotency đã được ghi nhận. Nếu cùng một event được phát lại, kết quả cuối cùng phải đúng theo hợp đồng nghiệp vụ.

Khi listener chuyển việc sang executor hoặc xử lý song song, cần kiểm tra thứ tự hoàn tất. Consumer có thể đọc tuần tự từ một partition nhưng các tác vụ được gửi sang thread pool vẫn có thể hoàn thành không theo thứ tự. Nếu nghiệp vụ yêu cầu xử lý tuần tự theo key, hãy giữ cơ chế tuần tự hóa ở tầng xử lý và viết test cho chính cơ chế đó.

Retry topic cũng ảnh hưởng đến thứ tự quan sát. Khi một event lỗi được chuyển sang retry topic trong lúc event tiếp theo tiếp tục được xử lý từ topic chính, thứ tự hoàn tất của cùng key có thể thay đổi. Nếu yêu cầu nghiệp vụ bắt buộc event sau phải chờ event trước, cần thiết kế retry và việc tạm dừng partition phù hợp, rồi kiểm thử cả trường hợp lỗi và phục hồi.

## 5. Kiểm thử phát lại

Có hai cách phổ biến để kiểm tra replay:

**Seek trong consumer hiện tại.** Sau khi partition đã được assign, gọi **seek(topicPartition, offset)** để thay đổi position của consumer. Cách này phù hợp để kiểm tra việc đọc lại một đoạn log trong integration test. **seekToBeginning()** cũng chỉ thay đổi position của consumer hiện tại; group offset chỉ được lưu khi consumer commit.

**Dùng consumer group mới hoặc reset group offset.** Một group mới chưa có committed offset sẽ dùng **auto.offset.reset** khi bắt đầu đọc. Đặt giá trị **earliest** để đọc từ đầu phần dữ liệu còn được giữ. Với group đã có committed offset, đổi **auto.offset.reset** sang **earliest** không tự động đưa group về đầu log. Muốn reset group hiện có, cần chủ động thay đổi offset của group; khi dùng công cụ reset offset hoặc AdminClient, hãy bảo đảm group không còn consumer hoạt động theo yêu cầu của thao tác đó.

Khi kiểm thử replay, cần phân biệt:

- **Dữ liệu còn tồn tại:** retention có thể xóa dữ liệu cũ. Topic compacted có thể loại bỏ phiên bản cũ của cùng key, nên không phù hợp nếu bài kiểm thử cần phát lại toàn bộ lịch sử sự kiện.
- **Dữ liệu được phép nhìn thấy:** consumer dùng isolation level **read_committed** không đọc các bản ghi thuộc transaction đã abort.
- **Offset được chọn:** replay từ offset 40 không có nghĩa offset 40 chắc chắn là bản ghi nghiệp vụ thứ 40.
- **Tác dụng phụ:** phát lại là hành vi bình thường của Kafka. Consumer cần idempotency, chẳng hạn lưu event id đã xử lý, dùng khóa duy nhất trong cơ sở dữ liệu hoặc cập nhật trạng thái theo phiên bản.

Một replay test tốt không dừng ở việc xác nhận consumer đọc lại được record. Test nên phát lại cùng event và xác nhận hệ thống không tạo thêm khoản thanh toán, không nhân đôi dòng dữ liệu và không làm trạng thái nghiệp vụ lùi về phiên bản cũ.

## 6. Các tình huống cần có trong test suite

| Tình huống | Kết quả mong đợi |
|---|---|
| Hai event liên tiếp có cùng key | Cùng partition; offset tăng theo thứ tự broker ghi |
| Hai event có key khác nhau | Không áp đặt chúng phải nằm ở hai partition khác nhau |
| Topic có nhiều partition | Chỉ kiểm tra thứ tự trong từng partition hoặc từng key |
| Consumer chưa xử lý xong | Offset chưa được commit vượt qua phần chưa xử lý theo ack mode |
| Consumer xử lý xong rồi dừng | Group tiếp tục từ committed offset |
| Consumer dừng trước commit | Event có thể được giao lại; handler xử lý idempotent |
| Consumer mới với **earliest** | Đọc từ đầu dữ liệu còn được giữ khi group chưa có offset |
| Group đã có offset | **auto.offset.reset** không tự reset offset hợp lệ hiện có |
| Replay một event | Tác dụng phụ nghiệp vụ không bị nhân đôi |
| Listener chạy song song | Thứ tự hoàn tất đáp ứng yêu cầu nghiệp vụ theo key |
| Producer retry | Không tạo bản ghi trùng ngoài hợp đồng và vẫn giữ thứ tự theo cấu hình producer |
| Transaction bị abort | Consumer **read_committed** không nhìn thấy bản ghi thuộc transaction đó |

## 7. Lỗi kiểm thử thường gặp

- **Dùng chung group id giữa nhiều test:** test sau tiếp tục từ offset test trước và có thể không nhận được dữ liệu mong đợi. Hãy tạo group id duy nhất.
- **Bật auto commit trong test offset:** commit có thể xảy ra theo chu kỳ và khiến kết quả phụ thuộc thời gian. Tắt auto commit khi cần kiểm soát commit.
- **Đợi bằng sleep cố định:** thời gian khởi động broker và rebalance thay đổi giữa máy chạy. Dùng poll có deadline và thông báo lỗi rõ ràng khi hết thời gian.
- **Khẳng định thứ tự toàn cục:** các partition độc lập không có một thứ tự tổng thể. So sánh offset chỉ trong cùng partition.
- **Giả định offset liền nhau:** compaction và transaction có thể tạo khoảng trống trong những record consumer quan sát.
- **Chỉ test nhận bản tin:** producer gửi thành công không chứng minh consumer commit đúng hoặc logic nghiệp vụ an toàn khi replay.
- **Không cô lập topic:** dữ liệu cũ làm sai kết quả đọc từ **earliest**. Dùng topic test riêng hoặc dọn dữ liệu bằng fixture phù hợp.
- **Bỏ qua thay đổi số partition:** việc tăng partition có thể thay đổi định tuyến của key. Đưa thay đổi này vào kiểm thử nâng cấp topic nếu thứ tự theo key là yêu cầu.

## 8. Checklist trước khi hoàn thành

- [ ] Key được tạo ổn định và serialize đúng như hợp đồng.
- [ ] Các event cùng key được định tuyến vào cùng partition trong cấu hình đang kiểm thử.
- [ ] Test thứ tự chỉ so sánh bản ghi trong cùng partition.
- [ ] Test bao gồm producer retry và cấu hình idempotence nếu hệ thống sử dụng chúng.
- [ ] Auto commit được tắt trong test cần xác minh thời điểm commit.
- [ ] Offset commit trỏ đến vị trí tiếp theo sau phần đã xử lý thành công.
- [ ] Có test cho trường hợp lỗi trước acknowledgment và giao lại event.
- [ ] Có test seek hoặc consumer group mới để phát lại dữ liệu.
- [ ] Có test xác nhận handler idempotent khi event được xử lý lặp.
- [ ] Topic, group id và dữ liệu được cô lập giữa các lần chạy.
- [ ] Các test bất đồng bộ dùng deadline thay vì sleep cố định.

Khi các kiểm thử này đi qua, nhóm phát triển có bằng chứng rõ ràng hơn về hợp đồng định tuyến, thứ tự theo partition, quản lý offset và khả năng phục hồi bằng replay. Những kiểm thử này nên chạy cùng integration test của producer, consumer và listener trong pipeline CI để phát hiện sớm thay đổi cấu hình hoặc hành vi khi nâng cấp Kafka và Spring Kafka.
