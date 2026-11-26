# Dọn dữ liệu sau test

Kiểm thử tích hợp với message broker thường tạo ra nhiều tài nguyên nằm ngoài transaction của test: topic, queue, exchange, consumer group, offset, message, dead-letter queue, schema và dữ liệu phụ trợ trong database. Nếu không dọn đúng cách, dữ liệu của lần chạy trước có thể ảnh hưởng lần chạy sau, làm test chập chờn hoặc khiến môi trường test tích lũy tài nguyên không cần thiết.

Dọn dữ liệu sau test là một phần của thiết kế test broker. Mỗi test cần biết tài nguyên nào do nó tạo, thời điểm consumer đã xử lý xong, cách xóa an toàn và cách bảo đảm một test không xóa dữ liệu của test khác. Với Spring Modulith, cần chú ý thêm application event có thể được xử lý sau commit, publication registry có trạng thái riêng và listener bất đồng bộ có thể vẫn đang chạy khi phương thức test kết thúc.

## 1. Vì sao cần cleanup sau test?

Một test gửi `OrderPlaced` vào Kafka có thể tạo ra các tác động sau:

- Record được ghi vào topic.
- Consumer group đọc record và commit offset.
- Listener cập nhật database hoặc projection.
- Listener phát event tiếp theo vào topic khác.
- Lỗi xử lý có thể đưa record sang retry topic hoặc dead-letter topic (DLT).
- Schema Registry có thể lưu schema version mới.
- Event Publication Registry có thể ghi trạng thái publication của listener nội bộ.

Transaction rollback của test chỉ có thể rollback những thay đổi thuộc transaction database đó. Nó không tự xóa record đã gửi tới broker, không xóa offset đã commit và không hoàn tác lời gọi HTTP tới hệ thống ngoài. Listener chạy sau commit còn có thể dùng transaction riêng, độc lập với transaction test.

Nếu dữ liệu không được cô lập hoặc cleanup, các vấn đề thường gặp gồm:

- Test sau đọc lại message cũ và nhận kết quả sai.
- Consumer group giữ offset từ lần chạy trước khiến test bỏ qua record cần kiểm tra.
- DLT chứa message lỗi cũ làm test hiện tại thất bại ngoài dự kiến.
- Queue/exchange/topic dùng chung bị xóa trong khi test khác vẫn đang chạy.
- Consumer vẫn xử lý bất đồng bộ sau khi cleanup đã xóa dữ liệu, tạo ra trạng thái không xác định.
- Broker container hoặc database test tích lũy tài nguyên qua nhiều lần chạy.

Cleanup đáng tin cậy bắt đầu từ việc xác định ownership của tài nguyên và hoàn tất công việc bất đồng bộ trước khi xóa chúng.

## 2. Lập danh sách tài nguyên do test sở hữu

Trước khi viết `@AfterEach`, hãy liệt kê tài nguyên test tạo ra và cách xóa tương ứng. Không phải mọi test đều cần xóa toàn bộ broker hoặc database.

| Tài nguyên | Ví dụ | Cách cleanup thường dùng |
| --- | --- | --- |
| Topic | `it-orders-<test-id>` | Xóa topic do test tạo hoặc hủy broker/container dùng riêng. |
| Queue | `it-order-events-<test-id>` | Purge message hoặc xóa queue riêng sau khi consumer dừng. |
| Exchange và binding | Exchange test và binding tới queue | Xóa binding/exchange nếu test sở hữu chúng. |
| Consumer group | `it-inventory-<test-id>` | Dùng group ID riêng; xóa group khi không còn member hoạt động nếu cần. |
| Offset | Offset theo group và partition | Xóa cùng group test hoặc tạo group mới cho lần chạy mới. |
| Retry/DLT | `it-orders-retry-<test-id>` | Dọn cùng topic/queue gốc hoặc giữ lại khi test đang xác minh DLT. |
| Schema | Subject và version test | Dùng subject riêng; xóa theo chính sách registry nếu được phép. |
| Database test data | Order, projection, inbox/outbox | Xóa theo schema/test ID hoặc rollback transaction phù hợp. |
| Container | Kafka/RabbitMQ Testcontainer | Để lifecycle quản lý dừng và xóa container. |

Một tài nguyên chỉ nên được cleanup bởi test hoặc fixture đã tạo và sở hữu nó. Nếu topic, queue hoặc schema được nhiều test dùng chung, cần một lifecycle chung do suite quản lý; từng test không được tự ý xóa tài nguyên đó.

## 3. Ưu tiên tài nguyên riêng cho mỗi test

Chiến lược dễ cô lập nhất là tạo tên tài nguyên có namespace riêng theo test hoặc test class. Ví dụ:

```text
it-orders-<run-id>-<test-id>
it-inventory-<run-id>-<test-id>
it-orders-dlt-<run-id>-<test-id>
```

Consumer group cũng cần ID riêng. Nếu nhiều test dùng cùng một group ID, offset commit từ test trước có thể làm test sau bắt đầu ở vị trí khác. Một group ID mới giúp broker quản lý tiến độ đọc độc lập.

Có thể tạo ID từ tên test kết hợp UUID hoặc một ID của lần chạy CI. Tên phải tuân theo giới hạn ký tự và độ dài của broker. Không dùng dữ liệu người dùng hoặc thông tin bí mật làm tên tài nguyên.

Lợi ích của namespace riêng:

- Test có thể chạy song song mà không đọc hoặc xóa message của nhau.
- Cleanup chỉ tác động tới tài nguyên thuộc test hiện tại.
- Khi test thất bại, operator dễ tìm topic/queue còn sót lại theo prefix.
- Không cần purge một topic dùng chung rồi hy vọng consumer khác không bị ảnh hưởng.

Nếu chi phí tạo topic/queue riêng quá cao, có thể dùng một broker dùng chung nhưng phải phân vùng dữ liệu theo key, group ID, schema subject và quy ước cleanup rõ ràng. Khi đó cần test isolation mạnh hơn vì một thao tác cleanup sai có thể ảnh hưởng nhiều test.

## 4. Dọn dữ liệu Kafka

Với Kafka, dữ liệu test thường nằm trong topic và tiến độ đọc được lưu theo consumer group. Xóa message theo từng record không phải lúc nào cũng là cách cleanup phù hợp. Với integration test, tạo topic riêng cho test rồi xóa topic sau khi consumer đã dừng thường đơn giản và rõ ownership hơn.

Một quy trình cleanup Kafka có thể gồm:

1. Chờ listener đã xử lý xong record cần kiểm tra.
2. Dừng hoặc đóng consumer/listener container thuộc test.
3. Đóng producer hoặc client không còn được sử dụng.
4. Xóa consumer group riêng nếu broker cho phép và group không còn member hoạt động.
5. Xóa topic test, retry topic và DLT do test tạo.
6. Chờ thao tác quản trị hoàn tất và metadata broker ổn định trước khi test khác dùng lại tên tài nguyên.

Ví dụ xóa topic bằng Kafka `AdminClient`:

```java
import java.time.Duration;
import java.util.List;
import java.util.concurrent.TimeUnit;

import org.apache.kafka.clients.admin.AdminClient;

void deleteTestTopic(AdminClient admin, String topicName) throws Exception {
    admin.deleteTopics(List.of(topicName))
            .all()
            .get(10, TimeUnit.SECONDS);
}
```

Đây là ví dụ minh họa. Trong test thực tế, `AdminClient` cần được đóng đúng lifecycle và topic phải là topic do test sở hữu. Thời gian chờ cần phù hợp với broker và môi trường CI; timeout hữu hạn giúp test báo lỗi rõ khi broker không hoàn tất thao tác.

Xóa consumer group cần chú ý group không còn consumer member hoạt động. Nếu listener container chưa dừng, broker có thể từ chối xóa group hoặc group được tạo lại khi consumer kết nối. Hãy dừng container trước, sau đó mới xóa group nếu cần. Khi mỗi test dùng group ID mới, thường không cần tái sử dụng offset cũ.

### Xóa topic hay chỉ reset offset?

Hai thao tác có ý nghĩa khác nhau:

- Xóa topic loại bỏ tài nguyên chứa record và metadata của topic theo cơ chế broker.
- Reset offset thay đổi vị trí consumer group đọc tiếp; nó không xóa record.

Không reset offset của group dùng chung để “làm sạch test”. Thao tác đó có thể làm thay đổi tiến độ consumer của ứng dụng hoặc test khác. Nếu cần kiểm tra replay, hãy tạo group riêng và đặt offset theo kịch bản test.

## 5. Dọn queue, exchange và binding của RabbitMQ

Với RabbitMQ, test thường tạo exchange, queue và binding. Message nằm trong queue; consumer ack message sẽ loại message khỏi queue theo semantics của broker. Nếu test cần xác minh message còn trong queue hoặc kiểm tra dead-letter routing, không purge trước khi assertion hoàn tất.

Một thứ tự cleanup phổ biến:

1. Dừng consumer và chờ các delivery đang xử lý hoàn tất hoặc được trả lại theo chính sách test.
2. Xóa binding do test tạo.
3. Xóa queue test, bao gồm queue retry/DLQ riêng nếu có.
4. Xóa exchange riêng do test tạo sau khi không còn binding phụ thuộc.
5. Đóng connection/channel được test sở hữu.

Nếu chỉ cần xóa message nhưng giữ queue, có thể purge queue test sau khi assertion. Purge xóa message đang chờ trong queue; nó không thay thế việc dừng consumer đang hoạt động và không thể thu hồi message mà consumer đã nhận.

Không purge queue dùng chung với ứng dụng hoặc test khác. Với queue có tên được tạo tự động, hãy lưu lại tên thực tế để cleanup đúng queue. Queue exclusive hoặc auto-delete có thể được broker xóa khi connection/channel sở hữu đóng; cần hiểu ownership trước khi thêm lệnh delete thủ công.

## 6. Dọn retry topic và dead-letter queue

Retry topic và DLT thường chứa message có giá trị chẩn đoán. Không nên xóa chúng trước khi test xác minh nội dung, header, số lần retry hoặc nguyên nhân thất bại.

Với test xác minh dead-letter routing:

1. Gửi message gây lỗi có định danh riêng.
2. Chờ consumer xử lý và chuyển message sang DLT.
3. Đọc DLT và xác minh payload/header/error metadata.
4. Dừng consumer liên quan.
5. Cleanup topic/queue retry và DLT riêng của test.

Nếu test thất bại trước assertion, vẫn cần cleanup tài nguyên test trong `finally` hoặc callback lifecycle. Tuy nhiên, khi cần giữ bằng chứng để debug, có thể cấu hình chế độ giữ tài nguyên khi test fail trong môi trường local/CI có kiểm soát. Cần có TTL hoặc job dọn rác cho các tài nguyên được giữ lại.

Không dùng DLT production làm nơi thử nghiệm cleanup. Test phải dùng broker/container hoặc namespace test riêng.

## 7. Dọn database và Event Publication Registry

Broker cleanup không xóa dữ liệu trong database. Một listener có thể đã tạo projection, inbox record, audit row hoặc dữ liệu nghiệp vụ. Nếu test dùng database chung cho nhiều test, cần cleanup đúng các bản ghi do test tạo.

Các lựa chọn phổ biến:

- Transaction rollback cho dữ liệu đồng bộ nằm trong cùng transaction test.
- Xóa theo ID test hoặc business key riêng.
- Dùng schema/database riêng cho mỗi test class hoặc suite.
- Dùng database Testcontainer riêng và để container lifecycle xóa toàn bộ dữ liệu sau suite.

Với Spring Modulith, listener `@ApplicationModuleListener` chạy sau commit và trong transaction riêng. Transaction của listener không nhất thiết thuộc transaction test. Vì vậy, rollback transaction test không đảm bảo xóa dữ liệu listener đã commit. Hãy chờ listener hoàn tất rồi cleanup dữ liệu do listener tạo theo ID test.

Event Publication Registry theo dõi publication tới transactional listener. Không xóa trực tiếp bảng nội bộ của registry bằng SQL để dọn test hoặc đánh dấu publication hoàn tất. Nếu test cần xác minh registry, dùng API công khai hoặc cấu hình database/schema riêng để lifecycle của database dọn toàn bộ. Không biến cleanup thành thao tác sửa trạng thái framework bằng tay.

Nếu test dùng relational registry, dữ liệu publication có thể nằm trong cùng database nhưng có vòng đời do framework quản lý. Hãy phân biệt bảng nghiệp vụ của test với bảng hạ tầng của registry và chỉ cleanup theo cách được hỗ trợ.

## 8. Dọn schema và subject trong Schema Registry

Nếu test broker dùng Avro, Protobuf hoặc JSON Schema cùng Schema Registry, test có thể đăng ký subject và version. Subject dùng chung có thể ảnh hưởng compatibility check của test khác hoặc để lại schema rác.

Các nguyên tắc:

- Dùng subject riêng cho test nếu registry hỗ trợ quy ước subject theo topic hoặc tên subject tùy chỉnh.
- Không đăng ký schema test vào subject production.
- Chỉ xóa subject do test sở hữu và theo đúng quyền/API của registry.
- Hiểu soft delete, hard delete và compatibility policy trước khi xóa version.
- Không xóa schema dùng chung trong khi test khác hoặc ứng dụng còn tham chiếu.

Một số registry yêu cầu xóa subject theo hai bước hoặc có chính sách hạn chế hard delete. Vì vậy, cleanup cần dùng API quản trị chính thức của registry thay vì thao tác trực tiếp vào database nội bộ.

Nếu không cần kiểm thử hành vi xóa schema, có thể dùng subject namespace riêng và để registry test/container bị hủy sau suite. Cách này giảm nguy cơ xóa nhầm schema dùng chung.

## 9. Dùng Testcontainers để quản lý vòng đời broker

Testcontainers giúp khởi chạy broker trong container phục vụ integration test và dừng container theo lifecycle của test suite. Khi mỗi suite có broker riêng, cleanup toàn bộ dữ liệu broker thường đơn giản hơn việc xóa từng topic sau mỗi test.

Ví dụ khởi tạo Kafka container:

```java
import org.junit.jupiter.api.AfterAll;
import org.junit.jupiter.api.BeforeAll;
import org.testcontainers.kafka.KafkaContainer;
import org.testcontainers.utility.DockerImageName;

class BrokerIntegrationTests {

    static KafkaContainer kafka = new KafkaContainer(
            DockerImageName.parse("apache/kafka-native:latest"));

    @BeforeAll
    static void startBroker() {
        kafka.start();
    }

    @AfterAll
    static void stopBroker() {
        kafka.stop();
    }
}
```

Ví dụ minh họa lifecycle; image, class Testcontainers và cách khai báo container cần khớp phiên bản dependency của dự án. Trong dự án dùng `@Container` với JUnit 5 extension hoặc container bean được quản lý bởi Spring, để extension/context chịu trách nhiệm start/stop. Không vừa để extension tự quản lý vừa gọi stop thủ công nếu điều đó làm lifecycle khó dự đoán.

Container dùng chung ở cấp class/suite tiết kiệm thời gian khởi động, nhưng các test vẫn cần topic, queue và group ID riêng nếu chạy song song. Dừng container chỉ nên diễn ra sau khi tất cả test sử dụng broker đã hoàn tất.

Tránh dùng container reuse giữa các lần chạy CI nếu không có chiến lược cleanup và namespace rõ ràng. Reuse có thể giữ message, offset và schema từ lần chạy trước, khiến kết quả không còn độc lập.

## 10. Cleanup theo JUnit lifecycle

JUnit cung cấp `@AfterEach` và `@AfterAll` để cleanup theo phạm vi test hoặc class. Hãy đặt cleanup ở đúng cấp ownership:

- `@AfterEach`: tài nguyên riêng của một test method.
- `@AfterAll`: tài nguyên dùng chung cho toàn bộ test class.
- Testcontainers/JUnit extension: container được quản lý theo lifecycle đã cấu hình.
- Suite-level fixture: broker hoặc schema registry dùng chung cho nhiều class.

Ví dụ cấu trúc:

```java
class OrderBrokerTests {

    private String topicName;
    private String groupId;

    @BeforeEach
    void createTestResources() {
        topicName = TestResourceNames.topicForCurrentTest();
        groupId = TestResourceNames.groupForCurrentTest();
        // Tạo topic và cấu hình consumer group riêng.
    }

    @AfterEach
    void cleanTestResources() throws Exception {
        // Dừng listener/consumer trước.
        // Đóng producer/admin client do test sở hữu.
        // Xóa group và topic test sau khi không còn consumer hoạt động.
    }
}
```

Đây là skeleton minh họa, không phải implementation đầy đủ cho mọi broker. Cleanup cần chạy cả khi assertion thất bại. JUnit vẫn gọi lifecycle callback khi test method ném assertion error, nhưng bản thân cleanup cũng có thể lỗi; hãy ghi nhận lỗi cleanup mà không che mất nguyên nhân thất bại ban đầu.

Nếu cleanup gồm nhiều thao tác, dùng `try/finally` hoặc helper có thứ tự rõ ràng để một bước lỗi không khiến các bước độc lập còn lại bị bỏ qua. Không bắt exception rồi bỏ qua hoàn toàn; cần log tài nguyên nào chưa được xóa để suite hoặc job dọn rác xử lý.

## 11. Chờ consumer hoàn tất trước khi cleanup

Đây là nguyên tắc quan trọng nhất với event bất đồng bộ: không dọn topic, queue hoặc database trong khi listener vẫn có thể đang xử lý message của test.

Trình tự đúng về mặt lifecycle:

1. Gửi event/message.
2. Chờ điều kiện xử lý mong đợi bằng assertion hoặc probe có timeout.
3. Xác minh kết quả trong database, output topic hoặc DLT.
4. Dừng listener container/consumer thuộc test.
5. Cleanup dữ liệu database và broker.

Không dùng `Thread.sleep` cố định để đoán consumer đã xử lý xong. Dùng Awaitility, latch, future hoặc cơ chế chờ của framework để chờ điều kiện cụ thể với timeout hữu hạn.

Ví dụ với Awaitility:

```java
import static org.awaitility.Awaitility.await;

import java.time.Duration;

await()
        .atMost(Duration.ofSeconds(10))
        .untilAsserted(() ->
                assertThat(orderProjection.findById(orderId)).isPresent());
```

Đoạn code minh họa chờ projection được cập nhật. Điều kiện cần phù hợp với test; nếu projection có thể tồn tại từ dữ liệu cũ, hãy kiểm tra event ID hoặc version của chính test hiện tại. Sau khi xác nhận hoàn tất, mới dừng consumer và cleanup.

## 12. Chạy test song song mà không xóa nhầm dữ liệu

Test song song làm lộ các vấn đề ownership. Hai test dùng cùng topic hoặc queue có thể đọc message của nhau; một test xóa queue trong khi test kia đang dùng sẽ gây lỗi khó tái hiện.

Để hỗ trợ parallel execution:

- Dùng namespace riêng theo test ID cho topic, queue, exchange và DLT.
- Dùng consumer group ID riêng cho từng test.
- Dùng business ID/event ID duy nhất cho mỗi test.
- Không dùng một static cleanup job xóa mọi tài nguyên theo prefix quá rộng khi test khác còn chạy.
- Chia database schema hoặc dùng test ID trong dữ liệu để cleanup chính xác.
- Chỉ dừng broker/container ở cấp suite sau khi mọi test phụ thuộc đã kết thúc.

Nếu không thể tạo tài nguyên riêng, có thể tắt parallel execution cho nhóm test dùng tài nguyên chia sẻ. Đây là một quyết định rõ ràng hơn việc để test tranh chấp rồi thêm delay để tránh lỗi.

## 13. Cleanup khi test thất bại hoặc tiến trình bị dừng

`@AfterEach` không thể bảo đảm chạy trong mọi trường hợp, chẳng hạn JVM bị kill, máy CI mất điện hoặc container runtime dừng đột ngột. Vì vậy, môi trường test dùng broker lâu dài cần cơ chế dọn tài nguyên mồ côi.

Một cách làm an toàn:

- Gắn prefix test rõ ràng và metadata về run ID.
- Đặt TTL/retention cho tài nguyên test nếu broker hỗ trợ.
- Tạo job cleanup chỉ xóa tài nguyên thuộc namespace test đã hết hạn.
- Lưu log khi tạo tài nguyên để có thể truy vết ownership.
- Dùng broker/container ephemeral cho CI khi có thể.
- Có chế độ giữ tài nguyên khi test thất bại để debug local, nhưng không bật mặc định trên môi trường dùng chung.

Job dọn rác cần kiểm tra tuổi tài nguyên, run ID và trạng thái suite trước khi xóa. Không dùng quy tắc như “xóa mọi topic bắt đầu bằng `it-`” trên broker dùng chung nếu các suite khác vẫn đang chạy.

## 14. Phân biệt cleanup dữ liệu và reset môi trường

Cleanup từng test và reset toàn bộ broker là hai phạm vi khác nhau:

| Phạm vi | Ví dụ | Thời điểm phù hợp |
| --- | --- | --- |
| Per-test cleanup | Xóa topic/queue/group riêng của test. | Sau mỗi test method. |
| Per-class cleanup | Xóa tài nguyên dùng chung trong một test class. | Sau khi tất cả test method trong class kết thúc. |
| Per-suite cleanup | Dừng broker/schema registry container. | Sau khi toàn bộ suite dùng hạ tầng kết thúc. |
| Environment reset | Xóa namespace test hoặc tái tạo broker test. | Trước/sau một pipeline độc lập hoặc môi trường test riêng. |

Không reset broker dùng chung sau từng test nếu test khác đang chạy. Cũng không nên giữ mọi tài nguyên tới cuối suite nếu chúng chiếm dung lượng lớn và có thể xóa an toàn sau mỗi test.

## 15. Những sai lầm thường gặp

- Nghĩ transaction rollback sẽ xóa message đã gửi vào broker.
- Dùng chung topic hoặc consumer group giữa nhiều test mà không cô lập offset.
- Purge queue trước khi assertion kiểm tra message hoặc DLT.
- Xóa topic khi consumer vẫn đang chạy.
- Xóa group khi member vẫn còn hoạt động.
- Dùng `@AfterEach` để dừng container dùng chung cho cả suite.
- Xóa schema subject dùng chung hoặc thao tác trực tiếp database nội bộ của Schema Registry.
- Xóa trực tiếp bảng Event Publication Registry bằng SQL.
- Dùng `Thread.sleep` để chờ consumer rồi cleanup.
- Dùng job cleanup xóa prefix quá rộng trên broker dùng chung.
- Bỏ qua lỗi cleanup khiến tài nguyên mồ côi tích lũy qua nhiều lần chạy.
- Giả định `@DirtiesContext` tự xóa topic, queue hoặc record của broker.

`@DirtiesContext` làm Spring test context bị loại khỏi cache và đóng theo lifecycle của Spring. Nó không tự động xóa tài nguyên đã tạo ở broker bên ngoài context, trừ khi chính bean/container được quản lý có lifecycle cleanup tương ứng.

## 16. Checklist dọn dữ liệu sau test

- [ ] Đã liệt kê tài nguyên broker/database/schema do test tạo và xác định owner.
- [ ] Topic, queue, exchange, group ID và DLT có namespace riêng khi cần chạy song song.
- [ ] Đã chờ consumer/listener xử lý xong trước khi cleanup.
- [ ] Đã xác minh message, offset, DLT hoặc projection trước khi xóa dữ liệu cần assertion.
- [ ] Consumer/listener container được dừng trước khi xóa group hoặc queue.
- [ ] Producer, AdminClient, channel và connection do test tạo được đóng đúng lifecycle.
- [ ] Topic/queue/group chỉ bị xóa nếu test sở hữu chúng.
- [ ] Schema Registry subject được cleanup qua API chính thức và đúng ownership.
- [ ] Dữ liệu listener commit trong database được cleanup riêng; không dựa vào rollback transaction test.
- [ ] Không sửa/xóa trực tiếp bảng nội bộ của Event Publication Registry.
- [ ] Cleanup chạy khi test thất bại và báo rõ tài nguyên chưa dọn được.
- [ ] Có cơ chế xử lý tài nguyên mồ côi nếu tiến trình bị dừng đột ngột.
- [ ] Broker/container dùng chung chỉ được dừng ở cấp suite sau khi mọi test hoàn tất.

Dọn dữ liệu sau test giúp mỗi lần kiểm thử bắt đầu từ trạng thái có thể dự đoán và không làm ảnh hưởng các test khác. Khi tài nguyên được cô lập theo ownership, consumer được chờ hoàn tất trước cleanup và broker/database được dọn theo đúng lifecycle, các bài kiểm thử Spring Modulith tích hợp broker sẽ ổn định hơn và dễ điều tra khi thất bại.
