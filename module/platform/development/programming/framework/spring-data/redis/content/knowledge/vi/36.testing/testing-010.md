# Kiểm thử consumer group, acknowledgment và bản ghi đang chờ

**Redis Streams** có thể lưu thông điệp để consumer đọc về sau và hỗ trợ **consumer group** phân chia công việc giữa nhiều worker. Trong **Spring Data Redis**, điều này thường được triển khai qua `StreamOperations`, `StreamMessageListenerContainer` hoặc `StreamReceiver`. Tuy nhiên, việc ứng dụng đọc được một event không chứng minh event đã được xử lý thành công: Redis còn phải theo dõi những event **đã giao nhưng chưa xác nhận** trong **Pending Entries List (PEL)**.

Khi kiểm thử, không nên chỉ chứng minh “đã gửi một event, listener nhận một event”. Cần kiểm tra đủ các tình huống có ý nghĩa vận hành:

- Event mới được phân phối theo consumer group như thế nào?
- Khi nào `XACK` làm một event rời PEL?
- Worker dừng hoặc crash **trước ACK** thì event ở đâu?
- Worker mới có thể claim và xử lý lại event cũ không?
- Nếu side effect đã commit nhưng ACK chưa kịp gửi, làm sao tránh xử lý trùng?
- Nếu stream bị trim hoặc group được tạo sai offset, bản ghi còn có thể phục hồi không?
- Các API Spring Data Redis phản ánh trạng thái Redis ra sao?

Bài học này xây dựng mô hình test từ **Redis CLI** tới **JUnit + Testcontainers + Spring Data Redis**, kèm các ca lỗi và cách tổ chức bài kiểm thử không phụ thuộc vào thời gian chờ ngẫu nhiên.

## 1. Phân biệt ba trạng thái trước khi viết test

Một message trong Redis Streams có ít nhất ba cột mốc:

1. **Đã lưu**: `XADD` thành công và entry có stream ID.
2. **Đã phân phối**: `XREADGROUP` giao entry cho một consumer; Redis theo dõi entry chưa ACK trong PEL của group.
3. **Đã xử lý**: code nghiệp vụ đã hoàn tất side effect và ứng dụng gọi `XACK` theo chính sách.

```text
Producer                        Redis Stream                  Consumer
   |                                 |                            |
   | --- XADD event ---------------->|                            |
   |                                 | lưu entry ID 100-0          |
   |                                 |                            |
   |                                 |<---- XREADGROUP ... > ------|
   |                                 |----- event 100-0 ---------->|
   |                                 |                            |
   |                                 | PEL chứa 100-0             |
   |                                 |                            | xử lý nghiệp vụ
   |                                 |                            | commit thành công
   |                                 |<------- XACK 100-0 ---------|
   |                                 |                            |
   |                                 | PEL không còn 100-0        |
```

Điểm quan trọng: **`XACK` không xóa payload khỏi stream.** Nó loại entry khỏi danh sách pending của **một group**. Việc xóa payload là vấn đề riêng liên quan `XDEL`, `XTRIM`, retention hoặc quản lý stream.

### Bảng trạng thái cần xác minh

| Trạng thái | Entry còn trong stream | Entry trong PEL của group | Consumer xử lý nghiệp vụ |
|---|---|---|---|
| Vừa `XADD`, chưa được group đọc | Có | Chưa | Chưa |
| Được `XREADGROUP` trả về, chưa ACK | Có | Có | Chưa chắc |
| Handler lỗi, không ACK | Có nếu chưa bị xóa/trim | Có | Thất bại hoặc chưa rõ |
| Handler thành công, chưa kịp ACK | Có | Có | Có thể đã thành công |
| Đã `XACK` | Có nếu chưa bị xóa/trim | Không | Ứng dụng tuyên bố đã xong |
| Payload bị `XDEL`/trim khi còn pending | Không | Có thể còn dấu vết pending | Không thể tự khôi phục payload đã bị xóa |

Do đó, assertion chỉ kiểm tra listener được gọi là **chưa đủ**. Cần kiểm tra cả PEL, số ACK thực tế và side effect ở kho dữ liệu nghiệp vụ.

## 2. Các lệnh Redis Streams dùng trong kiểm thử

| Lệnh | Vai trò | Điều nên kiểm tra |
|---|---|---|
| `XADD` | Thêm entry vào stream | ID mới, payload và thứ tự |
| `XGROUP CREATE` | Tạo group từ một offset | Bắt đầu từ lịch sử hay chỉ nhận event mới |
| `XREADGROUP` | Đọc dưới danh nghĩa consumer trong group | Event được giao, consumer nhận và pending |
| `XACK` | Xác nhận entry đã xử lý | Số entry được ACK và PEL thay đổi |
| `XPENDING` | Xem tổng quan/chi tiết PEL | Số pending, owner, idle time, delivery count |
| `XCLAIM` | Chuyển pending cụ thể sang consumer khác | Ownership thay đổi, payload được nhận lại |
| `XAUTOCLAIM` | Duyệt và claim những pending đủ idle | Scan cursor, batch claim và xử lý lại |
| `XINFO GROUPS` | Xem thông tin các group | Consumers, last-delivered ID, pending, lag khi có |
| `XINFO CONSUMERS` | Xem thông tin consumer | Pending theo consumer và trạng thái idle |
| `XRANGE` | Kiểm tra entry còn trong stream | Payload vẫn tồn tại sau ACK |
| `XLEN` | Độ dài stream hiện tại | Không nhầm với số pending |
| `XTRIM`/`XDEL` | Dọn entry | Điều gì xảy ra khi payload biến mất |
| `XGROUP DESTROY` | Xóa group | Dọn trạng thái group test, không xóa stream |

Hai cú pháp cực kỳ quan trọng:

```text
XREADGROUP ... STREAMS stream:key >
    -> Nhận các message MỚI chưa được phân phối theo group.

XREADGROUP ... STREAMS stream:key 0
    -> Đọc lại lịch sử PENDING thuộc chính consumer đó theo quy tắc group.
```

Không coi `>` là “đọc lại mọi event chưa được xử lý”. Nó không tự quét PEL của consumer vừa chết.

## 3. Tạo group ở offset 0 và $: hai bài test khác nhau

Redis cho phép tạo consumer group với vị trí bắt đầu phù hợp.

### Đọc cả lịch sử đang có

```bash
redis-cli XADD stream:test:orders '*' eventId e-1 type CREATED
redis-cli XADD stream:test:orders '*' eventId e-2 type PAID

redis-cli XGROUP CREATE stream:test:orders group-from-start 0
redis-cli XREADGROUP GROUP group-from-start worker-a \
    COUNT 10 STREAMS stream:test:orders '>'
```

Với group tạo từ `0`, những entry có sẵn trong stream có thể được phân phối khi đọc event mới của group. Đây là thiết kế phù hợp khi consumer cần xử lý lại lịch sử còn lưu.

### Chỉ nhận entry phát sinh sau khi tạo group

```bash
redis-cli XGROUP CREATE stream:test:orders group-from-now '$'

redis-cli XADD stream:test:orders '*' eventId e-3 type SHIPPED

redis-cli XREADGROUP GROUP group-from-now worker-b \
    COUNT 10 STREAMS stream:test:orders '>'
```

Group tạo từ `$` bắt đầu theo vị trí cuối tại thời điểm tạo group. Những entry đã tồn tại trước đó **không được nhận như event mới** trong luồng `>` của group này.

**Test cần tuyên bố group được tạo từ đâu.** Nếu test mong nhận event cũ nhưng khởi tạo group bằng `$`, nó có thể thất bại không phải vì consumer handler lỗi mà vì offset sai.

Lưu ý về tên: `0` thường được Redis hiểu như mốc đầu stream; `0-0` là dạng ID đầy đủ, đều thường được dùng để bắt đầu từ lịch sử.

## 4. Kiểm thử thủ công: phân phối, pending và ACK

Dùng một Redis **dành riêng cho test** và tên stream/group không xung đột. Không chạy các lệnh xóa dữ liệu trên Redis dùng chung hoặc production.

### 4.1. Khởi tạo stream và group mới

```bash
redis-cli DEL stream:test:payments
redis-cli XADD stream:test:payments '*' eventId pay-1 type AUTHORIZED
redis-cli XADD stream:test:payments '*' eventId pay-2 type CAPTURED
redis-cli XADD stream:test:payments '*' eventId pay-3 type SETTLED

redis-cli XGROUP CREATE stream:test:payments payment-workers 0
```

Redis trả stream ID thực tế dạng `<milliseconds>-<sequence>`. Hãy dùng ID thực nhận ở bước sau, không chép một ID ví dụ vào môi trường thật.

### 4.2. Consumer A đọc hai event

```bash
redis-cli XREADGROUP GROUP payment-workers worker-a \
    COUNT 2 STREAMS stream:test:payments '>'
```

Kết quả mong đợi:

- Tối đa hai entry chưa được group phân phối được trả về.
- Cả hai được ghi nhận là pending của group.
- Owner là `worker-a`.
- Event thứ ba vẫn chưa được phân phối.

Kiểm tra:

```bash
redis-cli XPENDING stream:test:payments payment-workers
redis-cli XPENDING stream:test:payments payment-workers - + 10
redis-cli XINFO GROUPS stream:test:payments
```

Ví dụ ý nghĩa: pending count bằng 2, không phải 3, vì `pay-3` vẫn chưa giao cho worker.

### 4.3. ACK đúng một event

Thay `<ID-cua-pay-1>` bằng stream ID thực tế:

```text
XACK stream:test:payments payment-workers <ID-cua-pay-1>
```

Kỳ vọng:

- `XACK` trả số `1` khi entry đang pending trong group được xác nhận.
- Pending count giảm từ 2 còn 1.
- `pay-2` còn pending, vẫn thuộc `worker-a`.
- Payload của `pay-1` vẫn có thể có trong stream, vì ACK không phải XDEL.

Kiểm tra payload còn tồn tại:

```bash
redis-cli XRANGE stream:test:payments - +
```

Nếu ACK lại cùng ID:

```text
XACK stream:test:payments payment-workers <ID-cua-pay-1>
```

Thường nhận số `0` vì entry không còn pending trong group. **Không lấy `0` của lần ACK thứ hai làm bằng chứng handler chưa từng xử lý thành công**; trạng thái group có thể đã được xác nhận bởi lần ACK trước.

### 4.4. Consumer B nhận sự kiện mới

```bash
redis-cli XREADGROUP GROUP payment-workers worker-b \
    COUNT 10 STREAMS stream:test:payments '>'
```

Khi `pay-1` và `pay-2` đã được giao cho A, B dùng `>` thường chỉ nhận `pay-3`. Event `pay-2` chưa ACK **không được tự giao lại cho B**. Đây là một assertion cốt lõi để phân biệt group delivery và recovery.

## 5. Kiểm thử crash trước ACK

Một test thực tế có thể không cần giết JVM: chỉ cần **đọc event, giả lập handler lỗi rồi không gọi ACK**. Redis lúc đó sẽ giữ pending cho phép quan sát và phục hồi.

```text
T0: XADD event e-10
T1: worker-a XREADGROUP e-10
T2: e-10 nằm trong PEL, owner worker-a
T3: handler ném exception hoặc worker dừng
T4: Không XACK
T5: worker-b đọc ... >, không nhận lại e-10
T6: worker-b XCLAIM/XAUTOCLAIM e-10
T7: worker-b xử lý, XACK
```

Test cần xác minh **hai điều đối lập**:

1. Chỉ dùng `XREADGROUP ... >` không làm e-10 tự quay lại.
2. Recovery qua claim có thể chuyển quyền xử lý e-10 khi đủ điều kiện và payload còn lưu.

### 5.1. Đọc pending của cùng consumer

Nếu worker A kết nối lại bằng **cùng consumer name**, có thể đọc pending của chính A:

```bash
redis-cli XREADGROUP GROUP payment-workers worker-a \
    COUNT 10 STREAMS stream:test:payments 0
```

Đây không phải là cơ chế lấy pending đang thuộc B. Khi một instance được triển khai với consumer name khác, cần đường claim.

### 5.2. Nhận lại pending bằng XCLAIM

Nếu biết ID của `pay-2`, worker B có thể thử:

```text
XCLAIM stream:test:payments payment-workers worker-b 0 <ID-cua-pay-2>
```

`0` là ngưỡng idle time tối thiểu theo millisecond để test claim ngay; **không nên dùng ngưỡng 0 trong production** vì có thể cướp message của worker A đang xử lý hợp lệ.

Sau claim, kiểm tra:

```bash
redis-cli XPENDING stream:test:payments payment-workers - + 10
redis-cli XINFO CONSUMERS stream:test:payments payment-workers
```

Kỳ vọng owner của event được claim chuyển sang `worker-b`; pending count của toàn group không tự giảm vì **claim không phải ACK**.

Sau khi B xử lý thành công, gọi `XACK` đúng ID để xóa pending.

### 5.3. Nhận lại pending bằng XAUTOCLAIM

Khi không biết trước ID cần claim, Redis hỗ trợ quét PEL qua `XAUTOCLAIM`:

```bash
redis-cli XAUTOCLAIM stream:test:payments payment-workers worker-b \
    0 0-0 COUNT 10
```

Trong test có thể dùng min idle bằng 0 để không phụ thuộc `sleep`. Kết quả bao gồm cursor tiếp theo và các entry được claim; các phiên bản Redis còn có thể trả thông tin về ID không còn payload.

Trong production, dùng min idle phản ánh thời gian xử lý/lease hợp lệ, ví dụ:

```bash
redis-cli XAUTOCLAIM stream:orders:v1 order-workers worker-b \
    60000 0-0 COUNT 100
```

Ngưỡng 60.000 ms chỉ minh họa. Phải tiếp tục từ cursor do Redis trả về nếu còn phạm vi chưa quét và hiểu rằng scan cursor không đồng nghĩa toàn bộ PEL đã được xử lý thành công.

## 6. Test nhiều consumer trong cùng group và nhiều group

### 6.1. Hai consumer cùng một group chia việc

```text
Stream: [e1, e2, e3, e4]

Consumer group: order-workers
    worker-a -> e1, e2
    worker-b -> e3, e4
```

Một message mới được phân phối cho **một consumer trong group** trong cơ chế worker distribution thông thường. Không thiết kế test với kỳ vọng mỗi worker trong cùng group đều nhận toàn bộ event.

Nếu hai consumer đồng thời gọi `XREADGROUP ... >`, thứ tự phân phối chịu scheduling và thời điểm request; test chỉ nên kiểm tra **tổng hợp event được giao và không mất**, không hardcode “A chắc chắn nhận e1, B chắc chắn nhận e2” khi không cố tình điều phối thứ tự.

### 6.2. Hai group độc lập nhận cùng sự kiện

```text
Stream: [e1, e2]

Group A: billing-workers       -> xử lý e1, e2
Group B: notification-workers  -> xử lý e1, e2
```

Mỗi group có tiến độ và PEL riêng. `XACK` e1 trong group A **không ACK e1 trong group B**.

Bài test cần xác nhận:

- Cùng một event có thể được mỗi group nhận riêng.
- `XPENDING` có trạng thái riêng theo group.
- ACK của group A không làm pending của group B giảm.
- Retention phải tính tới group chậm nhất nếu cả hai cần replay.

### 6.3. ACK nhầm group

Nếu một ID đang pending trong `billing-workers` nhưng test gửi:

```text
XACK stream:test:payments notification-workers <ID-cua-e1>
```

thì không được coi như ACK thành công trong `billing-workers`. Redis quản lý PEL **theo từng group**, không theo stream ID đơn thuần.

Kiểm tra group/name là một cách phát hiện bug khi ứng dụng có nhiều loại event trên cùng stream hoặc dùng biến cấu hình sai.

## 7. Thiết kế test độc lập và xác định

Những bài test về thời gian, concurrency và Redis rất dễ thành **flaky test** nếu chỉ dùng `Thread.sleep(1000)` rồi hy vọng worker đã đọc xong. Nên thiết kế để mỗi test kiểm soát rõ tiền đề và quan sát.

### 7.1. Cô lập dữ liệu theo test

Có thể dùng khóa stream độc lập:

```text
stream:test:orders:<test-id>
group:test:orders:<test-id>
```

Hoặc mỗi test chạy trên một Redis container riêng. Với JUnit test song song, tên stream và consumer group cố định có thể khiến các test giẫm vào PEL của nhau.

Nếu dùng chung một Redis test instance:

- Tạo stream/group có namespace riêng cho mỗi test.
- Chỉ xóa đúng khóa của test khi setup/cleanup.
- Đừng dùng `FLUSHALL` trên Redis có thể bị test khác hoặc dịch vụ khác dùng chung.
- Tránh để background listener của test trước tiếp tục chạy và nhận event của test sau.

### 7.2. Không dùng thời gian chờ vô hạn

Lệnh:

```text
XREADGROUP ... BLOCK 0 ...
```

có thể chờ vô hạn đến khi có event. Trong integration test, nên chọn deadline rõ, ví dụ block 100–500 ms, rồi dùng assertion cụ thể.

Khi test waiting behavior, tốt hơn dùng `CountDownLatch`, future với timeout, hoặc cơ chế điều phối tương tự để chắc chắn listener đã bắt đầu trước khi phát event.

### 7.3. Không dùng Redis clock theo phỏng đoán

PEL có idle time tính từ thời điểm giao/claim; test chạy trên CI có thể chậm hoặc nhanh khác nhau. Nếu muốn test **khả năng claim** chứ không test chính xác thời gian idle, đặt min idle bằng `0` trong môi trường test kiểm soát. Nếu muốn test **không claim trước ngưỡng**, dùng thời gian và cửa sổ hợp lý, không dựa vào khoảng vài millisecond có nguy cơ flaky.

### 7.4. Không cố định stream ID

ID do Redis tạo phụ thuộc thời gian và sequence. Test nên lấy `RecordId` từ `XADD` rồi dùng ID đó để ACK/claim. Không hardcode ID như `1780000000000-0` trừ khi bài test chủ động tạo message ID hợp lệ cụ thể và hiểu điều kiện của Redis.

## 8. Môi trường test Spring Boot với Redis thật

Đối với test consumer group, mock `RedisTemplate` thường không đủ để chứng minh PEL, claim và group offset hoạt động đúng. **Testcontainers** giúp chạy Redis thật trong môi trường test có khả năng tái tạo.

Ví dụ dependency Gradle:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-data-redis'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.testcontainers:junit-jupiter'
    testImplementation 'org.testcontainers:testcontainers'
}
```

Phiên bản dependency nên theo BOM/dependency management của dự án. Redis container phải dùng version phù hợp với lệnh được test: `XAUTOCLAIM` yêu cầu Redis có hỗ trợ lệnh đó, trong khi `XREADGROUP`/`XACK` có sớm hơn.

Đối với Spring Boot, một cách tạo môi trường test:

```java
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.testcontainers.containers.GenericContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
import org.testcontainers.utility.DockerImageName;

@Testcontainers
@SpringBootTest
class RedisStreamIntegrationTest {

    @Container
    static final GenericContainer<?> REDIS =
            new GenericContainer<>(
                    DockerImageName.parse("redis:7.4-alpine"))
                    .withExposedPorts(6379);

    @DynamicPropertySource
    static void redisProperties(DynamicPropertyRegistry registry) {
        registry.add(
                "spring.data.redis.host",
                REDIS::getHost);
        registry.add(
                "spring.data.redis.port",
                () -> REDIS.getMappedPort(6379));
    }

    // Các @Test được xây ở phần tiếp theo.
}
```

Trong một dự án thật, class test cần chạy cùng một Spring Boot application/test configuration có `StringRedisTemplate` hoặc `RedisTemplate` được khởi tạo. Ví dụ là cấu trúc integration-test minh họa, không phải yêu cầu khởi động Redis thủ công trong production.

**Không chạy test trực tiếp trên Redis production.** Các ca thử `DEL`, `XGROUP CREATE`, `XCLAIM` hoặc `XTRIM` có thay đổi trạng thái và có thể ảnh hưởng các consumer thật.

## 9. Test JUnit: XADD, XREADGROUP, PEL và ACK

Ta triển khai một bài test theo ngữ nghĩa Spring Data Redis. Với `StringRedisTemplate`, thao tác Stream thường được truy cập qua `opsForStream()`.

### 9.1. Chuẩn bị một stream riêng cho test

```java
import java.util.Map;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.data.redis.connection.stream.ReadOffset;
import org.springframework.data.redis.connection.stream.RecordId;
import org.springframework.data.redis.core.StringRedisTemplate;

class StreamTestSupport {

    @Autowired
    StringRedisTemplate redis;

    String streamKey;

    void setUpStream(String testId) {
        streamKey = "stream:test:orders:" + testId;
        redis.delete(streamKey);
    }

    RecordId append(String eventId) {
        return redis.opsForStream().add(
                streamKey,
                Map.of(
                        "eventId", eventId,
                        "type", "ORDER_CHANGED"));
    }

    void createGroupFromStart(String group) {
        // Stream cần tồn tại: gọi append(...) trước khi tạo group.
        redis.opsForStream().createGroup(
                streamKey,
                ReadOffset.from("0-0"),
                group);
    }
}
```

Trong test bên dưới, để tránh bị xung đột khi chạy song song, sử dụng stream name sinh theo `UUID`. Đây là ví dụ một test method hoàn chỉnh; nếu tách helper, giữ thứ tự append rồi tạo group.

### 9.2. Test tổng số pending thay đổi khi ACK

```java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;

import java.util.List;
import java.util.Map;
import java.util.UUID;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.data.redis.connection.stream.Consumer;
import org.springframework.data.redis.connection.stream.MapRecord;
import org.springframework.data.redis.connection.stream.PendingMessagesSummary;
import org.springframework.data.redis.connection.stream.ReadOffset;
import org.springframework.data.redis.connection.stream.RecordId;
import org.springframework.data.redis.connection.stream.StreamOffset;
import org.springframework.data.redis.core.StreamReadOptions;
import org.springframework.data.redis.core.StringRedisTemplate;

class StreamGroupContractTests {

    @Autowired
    StringRedisTemplate redis;

    @Test
    void deliveredEntriesStayPendingUntilAck() {
        String stream = "stream:test:orders:" + UUID.randomUUID();
        String group = "group-a";

        RecordId first = redis.opsForStream().add(
                stream, Map.of("eventId", "evt-1"));
        RecordId second = redis.opsForStream().add(
                stream, Map.of("eventId", "evt-2"));

        redis.opsForStream().createGroup(
                stream, ReadOffset.from("0-0"), group);

        List<MapRecord<String, Object, Object>> records =
                redis.opsForStream().read(
                        Consumer.from(group, "worker-a"),
                        StreamReadOptions.empty().count(10),
                        StreamOffset.create(
                                stream, ReadOffset.lastConsumed()));

        assertNotNull(records);
        assertEquals(2, records.size());

        PendingMessagesSummary before =
                redis.opsForStream().pending(stream, group);
        assertEquals(2L, before.getTotalPendingMessages());

        Long acknowledged = redis.opsForStream()
                .acknowledge(stream, group, first);
        assertEquals(1L, acknowledged);

        PendingMessagesSummary after =
                redis.opsForStream().pending(stream, group);
        assertEquals(1L, after.getTotalPendingMessages());

        // XACK lần hai không ACK lại một pending đã xong.
        Long repeated = redis.opsForStream()
                .acknowledge(stream, group, first);
        assertEquals(0L, repeated);

        // Message thứ hai vẫn ở PEL.
        redis.opsForStream().acknowledge(stream, group, second);
        assertEquals(
                0L,
                redis.opsForStream()
                        .pending(stream, group)
                        .getTotalPendingMessages());
    }
}
```

Cần đặt class này trong context Spring Boot test có Redis container và `StringRedisTemplate` được autowire; có thể hợp nhất các ví dụ test vào `RedisStreamIntegrationTest` ở mục trước.

**Kiểm tra này xác nhận contract hạ tầng về pending/ACK**, không tự chứng minh business handler đã commit. Phần tiếp theo bổ sung mô phỏng crash và side effect.

### 9.3. Tách hai loại assertion

- **Infrastructure assertion**: `XPENDING` giảm, `XACK` trả 1 rồi 0.
- **Business assertion**: side effect ở database đã được commit **trước** khi ACK; retry không làm thay đổi kết quả lần hai.

Nếu chỉ kiểm tra hạ tầng, ứng dụng vẫn có thể ACK quá sớm. Nếu chỉ kiểm tra database, consumer group vẫn có thể giữ pending hàng giờ.

## 10. Test claim và recovery trong Java

Spring Data Redis có đường `claim(...)` tương ứng với Redis `XCLAIM` trong những phiên bản hỗ trợ. Ví dụ minh họa cách chuyển một pending cụ thể sang consumer khác:

```java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;

import java.time.Duration;
import java.util.List;
import java.util.Map;
import java.util.UUID;

import org.junit.jupiter.api.Test;
import org.springframework.data.redis.connection.stream.Consumer;
import org.springframework.data.redis.connection.stream.MapRecord;
import org.springframework.data.redis.connection.stream.ReadOffset;
import org.springframework.data.redis.connection.stream.RecordId;
import org.springframework.data.redis.connection.stream.StreamOffset;
import org.springframework.data.redis.core.StreamReadOptions;

@Test
void anotherConsumerCanClaimUnackedEntry() {
    String stream = "stream:test:orders:" + UUID.randomUUID();
    String group = "order-workers";

    RecordId id = redis.opsForStream().add(
            stream, Map.of("eventId", "evt-unacked"));
    redis.opsForStream().createGroup(
            stream, ReadOffset.from("0-0"), group);

    List<MapRecord<String, Object, Object>> delivered =
            redis.opsForStream().read(
                    Consumer.from(group, "worker-a"),
                    StreamReadOptions.empty().count(1),
                    StreamOffset.create(
                            stream, ReadOffset.lastConsumed()));

    assertNotNull(delivered);
    assertEquals(1, delivered.size());

    // Mô phỏng worker-a crash: KHÔNG gọi XACK.
    assertEquals(
            1L,
            redis.opsForStream().pending(
                    stream, group).getTotalPendingMessages());

    List<MapRecord<String, Object, Object>> claimed =
            redis.opsForStream().claim(
                    stream,
                    group,
                    "worker-b",
                    Duration.ZERO,  // Chỉ dùng trong test kiểm soát.
                    id);

    assertEquals(1, claimed.size());
    assertEquals(id, claimed.get(0).getId());

    // Claim không tự ACK.
    assertEquals(
            1L,
            redis.opsForStream().pending(
                    stream, group).getTotalPendingMessages());

    // Giả định worker-b xử lý business thành công.
    Long acked = redis.opsForStream()
            .acknowledge(stream, group, id);
    assertEquals(1L, acked);
}
```

Bài test này diễn tả hợp đồng của `claim`; chữ ký và kiểu generic trong code cần tương ứng với phiên bản Spring Data Redis dự án. Với Redis/driver version dùng `XAUTOCLAIM`, cũng nên có integration test riêng cho scan cursor và min-idle threshold.

Lưu ý: `Duration.ZERO` chỉ dùng để **bỏ chờ không cần thiết trong test**. Trong môi trường thật, claim ngay có thể khiến hai worker xử lý cùng message vì owner cũ chưa chết mà chỉ đang bận.

### Vì sao claim không làm pending count giảm?

PEL vẫn theo dõi event chưa ACK. `XCLAIM` chủ yếu đổi owner/idle bookkeeping; sau claim, vẫn cần handler xử lý và `XACK`. Nếu test chỉ thấy pending count vẫn là 1 rồi kết luận claim thất bại, đó là sai về ngữ nghĩa.

Hãy kiểm tra owner qua `XPENDING` chi tiết hoặc `XINFO CONSUMERS`, đồng thời xem ID trong kết quả claim.

## 11. Test không tự redeliver khi chỉ đọc message mới

Một bug phổ biến:

```text
worker-a đọc e1
worker-a crash trước ACK
worker-b liên tục XREADGROUP ... >
worker-b không thấy e1
```

Đây là hành vi bình thường: message e1 đang pending ở consumer A.

Một test nên xác minh:

1. Worker A nhận e1 và không ACK.
2. Worker B đọc `>` và không thấy e1 như “message mới”.
3. PEL vẫn có e1.
4. Worker B dùng `XCLAIM`/`XAUTOCLAIM`, nhận lại e1.
5. B ACK e1 sau xử lý.

Không nên dùng `BLOCK 0` để chứng minh bước 2: test sẽ chờ vô hạn. Dùng poll không block hoặc block trong thời gian ngắn và assertion kết quả rỗng:

```java
List<MapRecord<String, Object, Object>> next =
        redis.opsForStream().read(
                Consumer.from(group, "worker-b"),
                StreamReadOptions.empty().count(10),
                StreamOffset.create(
                        stream, ReadOffset.lastConsumed()));

boolean nothingNew = next == null || next.isEmpty();
// Có thể assert nothingNew == true khi không có event mới.
```

Đối với caller đọc stream ngoài nhóm, semantics offset khác; đừng áp test `XREADGROUP` cho `XREAD` thông thường.

## 12. Test ACK sau commit, không phải sau khi nhận

Một consumer nghiệp vụ thường có luồng:

```text
XREADGROUP
    |
    v
Validate payload
    |
    v
Bắt đầu transaction DB
    |
    v
Thực hiện side effect
    |
    v
Commit DB thành công
    |
    v
XACK Redis
```

Nếu ACK được gọi **trước** khi side effect thực sự commit, crash có thể làm event mất khỏi PEL, dù nghiệp vụ chưa hoàn tất.

### 12.1. Mẫu consumer đồng bộ

```java
import java.util.List;

import org.springframework.data.redis.connection.stream.Consumer;
import org.springframework.data.redis.connection.stream.MapRecord;
import org.springframework.data.redis.connection.stream.ReadOffset;
import org.springframework.data.redis.connection.stream.StreamOffset;
import org.springframework.data.redis.core.StreamReadOptions;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

@Service
public class OrderStreamWorker {

    private final StringRedisTemplate redis;
    private final OrderEventHandler handler;

    public OrderStreamWorker(
            StringRedisTemplate redis,
            OrderEventHandler handler) {
        this.redis = redis;
        this.handler = handler;
    }

    public int pollAndProcess(
            String stream, String group, String consumerName) {

        List<MapRecord<String, Object, Object>> batch =
                redis.opsForStream().read(
                        Consumer.from(group, consumerName),
                        StreamReadOptions.empty().count(10),
                        StreamOffset.create(
                                stream, ReadOffset.lastConsumed()));

        if (batch == null || batch.isEmpty()) {
            return 0;
        }

        int acknowledged = 0;

        for (MapRecord<String, Object, Object> record : batch) {
            // Handler phải báo thành công sau khi side effect commit.
            handler.handle(record.getValue());

            Long count = redis.opsForStream()
                    .acknowledge(stream, group, record.getId());

            if (Long.valueOf(1L).equals(count)) {
                acknowledged++;
            }
        }

        return acknowledged;
    }
}
```

Interface:

```java
import java.util.Map;

public interface OrderEventHandler {
    void handle(Map<Object, Object> payload);
}
```

Khi handler ném exception, lệnh ACK của record đó không được gọi. Nhưng lưu ý một batch có thể đã được Redis giao **toàn bộ** trước khi vòng `for` bắt đầu; nếu handler lỗi ở phần tử thứ hai, các phần tử phía sau batch đã được giao cũng sẽ còn pending. Vì vậy recovery phải xử lý toàn bộ pending, không chỉ record gây exception.

### 12.2. Assertion với handler thất bại

Có thể dùng handler giả lập exception:

```java
OrderEventHandler failingHandler = payload -> {
    throw new IllegalStateException("DB unavailable");
};
```

Sau khi gọi `pollAndProcess(...)`, test kỳ vọng:

- Exception được truyền ra theo hợp đồng.
- Event đã được giao nhưng chưa ACK vẫn nằm trong PEL.
- Không có logic `finally` tự ACK bất kể xử lý thành công hay không.
- Khi retry với handler hoạt động, event được xử lý qua recovery và ACK.

**Không đủ nếu chỉ assert method ném exception.** Phải kiểm tra PEL và việc business side effect chưa được đánh dấu thành công.

## 13. Test crash sau commit nhưng trước ACK

Đây là tình huống nền tảng của delivery kiểu **at-least-once**.

```text
Worker A:
    XREADGROUP e1
    DB INSERT/UPDATE thành công
    DB COMMIT thành công
    process crash trước XACK e1

Worker B:
    reclaim e1
    chạy lại business handler
```

Nếu business handler chỉ tăng một bộ đếm:

```sql
UPDATE summary SET paid_count = paid_count + 1;
```

thì e1 có thể làm tăng `paid_count` hai lần. Redis không biết transaction database đã commit; việc giữ e1 trong PEL là đúng về mặt Redis.

### 13.1. Thiết kế idempotency để test

Một event có ID nghiệp vụ riêng:

```json
{
  "eventId": "evt-001",
  "orderId": "order-42",
  "type": "ORDER_PAID",
  "version": 3
}
```

Handler thực hiện trong **cùng database transaction**:

1. Kiểm tra `eventId` đã ghi nhận chưa.
2. Nếu chưa, áp dụng side effect.
3. Ghi `eventId` vào bảng `processed_events` với ràng buộc unique.
4. Commit transaction.
5. Sau đó ACK Redis.

Mẫu schema:

```sql
CREATE TABLE processed_events (
    consumer_name VARCHAR(100) NOT NULL,
    event_id VARCHAR(100) NOT NULL,
    processed_at TIMESTAMP NOT NULL,
    PRIMARY KEY (consumer_name, event_id)
);
```

Tùy SQL dialect, dùng thao tác insert-if-absent hoặc xử lý unique violation đúng cách. Không thực hiện `SELECT exists` rồi `INSERT` ở hai transaction độc lập mà cho rằng đã chống được hai consumer cạnh tranh.

### 13.2. Các assertion cần có

Bài test crash-after-commit có thể kiểm tra:

| Bước | Business state | PEL |
|---|---|---|
| Worker A nhận e1 | Chưa đổi | Có e1 |
| Handler A commit thành công | Đã đổi một lần | Vẫn có e1 |
| A crash trước ACK | Vẫn đúng | Vẫn có e1 |
| B claim e1 | Vẫn đúng | Vẫn có e1, owner B |
| Handler B nhận lại e1 | Không tạo side effect lần hai | Vẫn có e1 |
| B ACK thành công | Vẫn đúng | Không còn e1 |

Mục tiêu không phải “handler B không được gọi”. Hệ thống at-least-once **có thể gọi lại**; điều cần đảm bảo là **tác dụng nghiệp vụ không bị áp dụng trùng**.

## 14. Test nhiều event, ACK từng phần và thứ tự xử lý

Giả sử một batch có ba message:

```text
e1 -> xử lý thành công -> XACK e1
e2 -> xử lý thất bại   -> KHÔNG ACK
e3 -> chưa xử lý       -> đã được XREADGROUP giao
```

PEL sau đó có thể còn e2 và e3. Trạng thái group và PEL phản ánh cả những entry **đã giao nhưng handler chưa chạy**, không chỉ những entry handler báo lỗi.

Bài test nên xác minh:

- ACK e1 trả `1` và e1 rời PEL.
- e2 vẫn pending.
- e3 vẫn pending nếu đã có trong batch được giao.
- Đọc event mới bằng `>` không lấy lại e2/e3.
- Recovery lấy e2/e3, có thể xử lý với chiến lược theo thứ tự/phiên bản phù hợp.

Nếu nghiệp vụ yêu cầu thứ tự tuyệt đối cho cùng đơn hàng, xử lý e3 trước e2 có thể sai, dù Redis cho phép claim và ACK không theo thứ tự. **Độ tin cậy delivery** và **thứ tự side effect** là hai yêu cầu riêng.

### 14.1. ACK không liên tục là hợp lệ về mặt PEL

Có thể có:

```text
e1 pending
e2 ACK
e3 pending
e4 ACK
```

Không cần giả định ACK phải đi từ ID thấp tới ID cao. Nhưng nếu ứng dụng dùng một **checkpoint riêng** ngoài group, nó không được nâng checkpoint vượt qua những event chưa hoàn tất theo cách gây mất dữ liệu khi replay.

Redis consumer group giữ PEL nên không nên tự “sửa lag” bằng cách chỉnh group offset sang cuối chỉ để biểu đồ đẹp.

## 15. Test shutdown/restart và recovery theo consumer name

Hai trường hợp khác nhau:

### Worker restart với cùng tên

```text
worker-a nhận e1 và e2
worker-a crash
worker-a khởi động lại cùng consumer name
```

Có thể đọc pending của chính worker-a bằng `XREADGROUP ... 0`, sau đó xử lý lại rồi ACK. Bài test phải kiểm tra rằng code startup **thực sự duyệt pending**, không chỉ bật vòng poll `>`.

### Worker mới mang tên khác

```text
worker-a nhận e1 và e2 rồi chết
worker-b thay thế
```

Worker-b không tự sở hữu pending của worker-a. Cần dùng `XCLAIM`/`XAUTOCLAIM` sau khi đạt ngưỡng idle.

Đối với ứng dụng deploy nhiều replica, consumer name nên phù hợp cơ chế ownership. Tất cả instance cùng dùng một consumer name có thể làm việc chẩn đoán pending, liveness và ownership khó hơn, dù Redis cho phép lệnh gọi tên như vậy.

### Test shutdown có kiểm soát

Một shutdown đáng tin cậy:

```text
Đánh dấu worker draining
          |
          v
Ngừng nhận batch mới
          |
          v
Đợi in-flight tới deadline
          |
      +---+---+
      |       |
     Xong   Chưa xong
      |       |
      v       v
     ACK    Để pending
      |       |
      +---+---+
          |
          v
      Dừng worker
```

Test nên mô phỏng tình huống timeout shutdown và chứng minh message chưa hoàn tất không bị ACK. Không giả định container `stop()` tự bảo đảm drain và ACK ở tầng nghiệp vụ.

## 16. Test XAUTOCLAIM với cursor và ngưỡng idle

`XAUTOCLAIM` hỗ trợ scan PEL để chuyển các entry có idle time vượt ngưỡng sang consumer khác.

```text
XAUTOCLAIM stream group new-consumer min-idle start COUNT N
```

Trả về thông thường gồm:

- Cursor để tiếp tục duyệt.
- Những entry đã được claim.
- Ở các phiên bản Redis phù hợp, thông tin các ID không còn entry để lấy payload.

Bài test không nên chỉ gọi một lần rồi kết luận “đã khôi phục hết mọi message”. Đối với PEL lớn, cần lặp theo cursor và hiểu rằng một cursor cuối vòng không đồng nghĩa tất cả entry đã xử lý/ACK.

### 16.1. Test “không claim trước ngưỡng”

Giả sử worker A đang xử lý một tác vụ kéo dài 5 giây. Nếu worker B claim sau 100 ms, cả hai có thể xử lý trùng. Test có thể đặt min idle cao và chứng minh lệnh không claim những event mới nhận.

Nhưng để tránh flaky test:

- Không chỉ `sleep(50)` rồi kỳ vọng Redis đồng hồ chính xác tuyệt đối.
- Dùng ngưỡng đủ rộng cho bài kiểm thử và deadline ổn định.
- Tách riêng test claim ngay bằng min idle 0 với test chính sách lease/idle.
- Dùng liveness/workflow marker nếu kiến trúc cần biết một worker đang còn xử lý hợp lệ.

### 16.2. Test “claim rồi ACK”

Kỳ vọng:

```text
Before claim:
    pending owner = worker-a
    pending count = 1

After claim:
    pending owner = worker-b
    pending count = 1

After XACK:
    pending count = 0
```

Đây là cấu trúc assertion chuẩn hơn việc mong pending count giảm ngay khi claim.

## 17. Test retention: entry bị xóa/trim khi vẫn pending

Redis Streams giữ entry theo retention hiện tại, không phải vô hạn. Một group có PEL **không buộc Redis giữ payload mãi**.

Ví dụ trên một stream test riêng:

```bash
redis-cli XADD stream:test:retention '*' eventId e-old
redis-cli XGROUP CREATE stream:test:retention retention-workers 0
redis-cli XREADGROUP GROUP retention-workers worker-a \
    COUNT 1 STREAMS stream:test:retention '>'
```

Giả sử nhận được ID `id-old` và chưa ACK. Sau đó xóa entry bằng lệnh test có kiểm soát:

```text
XDEL stream:test:retention <id-old>
```

Bài test tiếp tục kiểm tra:

- `XRANGE` không còn payload e-old.
- PEL và lệnh recovery phản ánh entry bị xóa theo ngữ nghĩa của phiên bản Redis.
- Worker không thể tái tạo payload chỉ từ PEL.
- Cơ chế giám sát báo rằng một pending event đã mất nội dung cần xử lý.

Với `XTRIM`, tác động tương tự có thể xảy ra khi stream giữ số entry tối đa thấp hơn lượng dữ liệu được producer ghi trong thời gian consumer pause.

### 17.1. Retention phải gắn với nhóm chậm nhất

Giả sử có:

```text
Group billing:
    xử lý nhanh, pending nhỏ

Group analytics:
    offline hai giờ, backlog lớn
```

Nếu stream được trim chỉ dựa vào tiến độ của billing, analytics có thể mất event cần đọc. Đừng test retention với một group duy nhất rồi kết luận mọi group đều an toàn.

Các bài test cần mô phỏng **consumer chậm hoặc offline** đủ lâu theo chính sách và xác nhận payload còn tồn tại, hoặc xác nhận hệ thống báo lỗi rõ khi vượt khả năng giữ.

## 18. Test lỗi kết nối và timeout: không tự ACK theo suy đoán

Có thể có các trường hợp:

```text
1. Redis XREADGROUP thành công, client nhận event.
2. Business handler commit thành công.
3. Client gửi XACK.
4. Mất kết nối trước khi nhận reply.
```

Ở bước 4, client có thể không biết chắc `XACK` đã chạy hay chưa. Không nên chỉ bắt timeout rồi coi event “đã ACK thành công”, cũng không nên đánh dấu business failure nếu side effect đã commit.

Test này nên xác minh logic:

- Trạng thái business được quản lý độc lập, có idempotency.
- Nếu ACK đã chạy, PEL không còn entry; ACK lặp thường trả 0.
- Nếu ACK chưa chạy, PEL còn entry; recovery sẽ xử lý lại, handler idempotent.
- Ứng dụng không dựa vào ACK response như một distributed transaction bao gồm cả database.

Trong Redis, `XACK` là thao tác giảm pending, không tạo side effect nghiệp vụ như trừ tiền. Việc retry ACK theo đúng stream/group/ID thường có thể chấp nhận được, nhưng **không dùng kết quả số 0 của ACK lặp để kết luận business chưa từng xử lý**.

### Test Redis outage cần cách ly hạ tầng

Dùng Testcontainers/toxiproxy hoặc môi trường integration có thể ngắt kết nối theo kịch bản. Không tắt Redis production để tạo lỗi. Khi ngắt kết nối:

1. Bảo đảm worker không ACK trước khi handler commit.
2. Xác định request/worker có timeout giới hạn, không treo vô hạn.
3. Quan sát exception riêng, không lẫn với “stream rỗng”.
4. Khôi phục Redis rồi thực hiện pending recovery.
5. Xác nhận không mất business event và không tạo tác dụng phụ trùng.

## 19. Test reactive StreamReceiver và demand

Spring Data Redis có API reactive cho Redis Streams, có thể tạo `Flux` qua `StreamReceiver`. Reactive demand chỉ kiểm soát số phần tử downstream muốn nhận; **nó không tự chứng minh dữ liệu đã được ACK sau side effect**.

### 19.1. Mono/Flux completion không đồng nghĩa ACK

Một listener reactive có thể nhận một record:

```java
receiver.receive(
        Consumer.from(group, consumerName),
        StreamOffset.create(
                stream, ReadOffset.lastConsumed()))
    .concatMap(record ->
        processBusiness(record)
            .then(acknowledge(record)));
```

Trong đó `processBusiness` và `acknowledge` là các hàm ứng dụng minh họa. Cần chọn API receiver và offset phù hợp với phiên bản Spring Data Redis thực tế.

Assertion cần có:

- Đã xử lý nghiệp vụ trước khi ACK.
- Nếu `processBusiness` lỗi, ACK không được gọi cho entry đó.
- Khi cancel subscription giữa chừng, entry chưa ACK còn có thể phục hồi.
- Không dùng biến thể auto-ACK nếu yêu cầu là “business commit trước ACK” mà không hiểu thời điểm auto-ACK trong phiên bản đang dùng.

### 19.2. ReadOffset.latest() có thể bỏ message giữa các lần poll

Khi downstream demand bằng 0, receiver có thể tạm dừng polling. Nếu resume bằng `ReadOffset.latest()`, những entry được thêm trong khoảng không poll có thể bị bỏ qua khỏi dòng nhận.

Test:

```text
T0: Consumer đang nhận event e1.
T1: Downstream dừng yêu cầu thêm.
T2: Producer XADD e2 và e3.
T3: Downstream yêu cầu tiếp.
T4: Kiểm tra e2/e3 có được nhận theo offset đang dùng.
```

Với workload yêu cầu không bỏ sót event, nên kiểm thử `ReadOffset.lastConsumed()` với consumer group, cùng đường xử lý pending, thay vì mặc định latest.

Lưu ý: `ReadOffset.lastConsumed()` ở đường new messages không tự phục hồi những entry đã giao nhưng chưa ACK. Vì vậy bài test reactive vẫn cần ca PEL recovery riêng.

## 20. Test concurrency: nhiều consumer và không ACK sớm

Một integration test concurrency có thể dùng hai worker, mỗi worker đọc batch nhỏ, và một `CountDownLatch` để điều phối thời điểm:

```text
Main test:
    XADD e1..e20
    tạo group ở 0
    cho phép worker A và B bắt đầu cùng lúc
    đợi tổng 20 event được xử lý hoặc timeout

Worker A/B:
    XREADGROUP COUNT n
    handler xử lý
    XACK sau commit
```

Các assertion nên là:

- Tổng số **event ID độc nhất** được xử lý thành công là 20.
- Không bỏ sót event còn lưu cần xử lý.
- Sau khi hệ thống quiescent, PEL của group bằng 0.
- Nếu giả lập crash/recovery, có thể có **attempt** trùng nhưng chỉ một **business effect** cho mỗi event ID.
- Không tự yêu cầu mỗi worker xử lý chính xác 10 event; Redis phân phối phụ thuộc scheduling.

Nếu test dùng `HashSet` trong nhiều thread, phải dùng cấu trúc concurrent hoặc bảo vệ bằng synchronization; race trong chính test harness có thể tạo kết quả sai.

### Tại sao không assert “handler chỉ gọi đúng một lần”?

Redis Streams với consumer group và recovery giúp tổ chức at-least-once delivery. Nếu worker crash sau business commit nhưng trước ACK, event có thể được xử lý lại. Một assertion “handler tuyệt đối chỉ chạy một lần” không phù hợp với mục tiêu thiết kế này.

Thay vào đó:

```text
handler attempts >= 1
business effects == 1
event cuối cùng được ACK == true
```

Và phải xác định thời hạn test, không đợi vô hạn nếu một worker thất bại.

## 21. Test message ordering và consumer group

Trong Redis Streams, stream IDs có thứ tự. Nhưng **thứ tự entry trong log** không đồng nghĩa **thứ tự side effect hoàn tất** khi nhiều worker chạy song song.

Ví dụ:

```text
Stream:
    e1: ORDER_CREATED
    e2: ORDER_PAID
    e3: ORDER_CANCELLED

Consumer group:
    worker-a nhận e1, chậm
    worker-b nhận e2, nhanh
    worker-c nhận e3, nhanh
```

Nếu handler áp dụng trạng thái bằng cách ghi đè không kiểm tra version, database có thể bị cập nhật sai thứ tự.

Test cần xét một trong các chiến lược:

- Chỉ một consumer xử lý tuần tự những event của cùng aggregate.
- Chia partition/consumer theo `orderId` để giữ thứ tự per-aggregate.
- Kiểm tra `version` trước khi cập nhật projection; bỏ qua event cũ.
- Dùng trạng thái/chuyển tiếp hợp lệ của domain thay vì tin thứ tự kết thúc request.
- Khi recovery pending, đảm bảo event cũ không ghi đè kết quả của event mới.

Không cần bắt Redis đảm bảo mọi worker xử lý đúng thứ tự tuyệt đối nếu kiến trúc đã xác định side effect có thể xử lý song song và dùng version để kiểm soát.

## 22. Test poison message và retry policy

Một message có payload không hợp lệ có thể khiến handler lỗi mãi mãi.

```text
XREADGROUP e-bad
    |
    v
Handler deserialize fail
    |
    v
Không ACK
    |
    v
PEL giữ e-bad
    |
    v
Recovery claim -> lỗi tiếp
```

Các test cần kiểm tra:

1. Message lỗi không bị ACK ngay khi handler ném exception.
2. Retry có backoff hoặc min idle, không tạo vòng xử lý nóng vô hạn.
3. Delivery count/attempt count được giới hạn theo chính sách ứng dụng.
4. Khi vượt ngưỡng, hệ thống ghi **dead-letter record** vào một nơi bền.
5. Chỉ sau khi hoàn thành chính sách dead-letter mới ACK source event theo quy trình đã chọn.
6. Redis PEL không giữ poison message vô hạn mà không có cảnh báo.
7. Việc redrive từ DLQ có idempotency và authorization phù hợp.

### Ví dụ mục tiêu

```text
event e-bad:
    attempt 1 -> invalid payload
    attempt 2 -> invalid payload
    attempt 3 -> invalid payload
    -> XADD dlq:orders ...
    -> XACK source e-bad
```

Lưu ý ghi DLQ và ACK source là hai thao tác khác nhau; nếu crash giữa chúng có thể có DLQ duplicate khi retry. Test nên kiểm tra cùng `eventId` không tạo nhiều side effect không mong muốn.

## 23. Test trim, delete và chính sách lưu trữ

Để kiểm thử retention đúng, cần phân biệt:

- **Sự kiện chưa giao**: còn trong stream hay đã bị trim?
- **Sự kiện đã giao, chưa ACK**: payload còn để recovery hay đã bị xóa?
- **Sự kiện đã ACK**: entry còn trong stream để các group khác đọc không?
- **Nhiều consumer group**: group chậm nhất có còn đủ lịch sử?

Một test với `MAXLEN`:

```bash
redis-cli XADD stream:test:bounded MAXLEN ~ 1000 '*' eventId e-1
```

Dấu `~` là trim xấp xỉ để tối ưu hiệu năng. Với integration test cần chính xác số entry, có thể dùng lệnh/cấu hình phù hợp với chính sách trim **exact** hoặc chủ động `XDEL` một ID cụ thể để mô phỏng payload mất.

Nếu dùng approximate trim rồi assert `XLEN == 1000` tuyệt đối, bài test có thể flaky hoặc sai ngay từ kỳ vọng.

## 24. Test nhóm consumer được tạo lại hoặc offset bị chỉnh sai

Một số hệ thống có script triển khai thực hiện:

```bash
redis-cli XGROUP CREATE stream:orders:v1 order-workers '$' MKSTREAM
```

rồi bắt đầu đọc `>`. Nếu stream đã có lịch sử mà group bắt buộc phải xử lý, các sự kiện đó có thể bị bỏ qua.

Các kịch bản cần test:

- Group mới bắt đầu từ `0` đọc được lịch sử còn lưu.
- Group mới bắt đầu từ `$` chỉ nhận sự kiện phát sinh sau mốc đó.
- Restart một group đang tồn tại **không tạo lại từ đầu** vô tình.
- Khi group đã tồn tại, thao tác tạo group có thể trả `BUSYGROUP`; khởi tạo idempotent cần xử lý có mục đích.
- Không xóa/recreate group trên mỗi startup chỉ để tránh `BUSYGROUP`: thao tác đó có thể làm mất PEL và tiến độ phân phối.
- Không dùng `XGROUP SETID` để chỉnh lag mà chưa có kế hoạch về pending/duplicate/skip.

**Group lifecycle là trạng thái bền của hệ thống**, không phải setup tạm thời cần reset ở mọi deploy.

## 25. Test pending ownership và thông tin vận hành

Redis có nhiều lệnh quan sát:

```bash
redis-cli XINFO STREAM stream:orders:v1
redis-cli XINFO GROUPS stream:orders:v1
redis-cli XINFO CONSUMERS stream:orders:v1 order-workers
redis-cli XPENDING stream:orders:v1 order-workers
redis-cli XPENDING stream:orders:v1 order-workers - + 100
```

Trong một test có hai consumer A và B, có thể xác nhận:

- Event e1 đang pending thuộc A sau XREADGROUP.
- Claim e1 sang B làm owner thay đổi.
- Delivery count/idle time thay đổi theo quy tắc Redis.
- Tổng pending không giảm do claim.
- XACK sau xử lý làm pending giảm.
- Khi một consumer không còn hoạt động, các pending cũ vẫn có thể được tìm và reclaim.

Không nhầm **group lag bằng 0** với **không có pending**. Group có thể đã phân phối đến cuối stream, nhưng hàng nghìn event vẫn chưa ACK.

### Metric nên tách rõ

| Metric | Ý nghĩa |
|---|---|
| `stream_append_total` | Số event producer ghi vào Redis |
| `stream_delivered_total` | Số event đã được group phân phối |
| `stream_ack_success_total` | Số event ACK thành công |
| `stream_pending_count` | Số event đã giao, chưa ACK |
| `stream_pending_oldest_age` | Tuổi pending lớn nhất |
| `stream_claim_total` | Số lần reclaim event |
| `stream_handler_attempt_total` | Số lần handler được gọi, bao gồm retry |
| `stream_business_success_total` | Số business effect thực sự hoàn tất |
| `stream_duplicate_event_total` | Số event ID đã được xử lý trước đó |
| `stream_dlq_total` | Số message chuyển DLQ |
| `stream_recovery_lag` | Độ trễ phục hồi pending sau lỗi |
| `stream_trimmed_pending_total` | Pending không còn payload (nếu quan sát được) |

Không dùng `eventId` như một metric label cho mọi sự kiện vì cardinality có thể bùng nổ. Dùng tên stream/group, loại event và mã lỗi; chi tiết event ID chỉ ghi vào tracing/log đã kiểm soát.

## 26. Những lỗi thường gặp khi kiểm thử

| Sai lầm trong test hoặc code | Hậu quả | Cách sửa |
|---|---|---|
| Chỉ assert listener nhận message | Không chứng minh ACK/recovery | Assert PEL và business effect |
| Nhận event rồi ACK trước handler | Crash làm mất khả năng retry | ACK sau commit |
| Expect worker B đọc pending A bằng `>` | Test sai ngữ nghĩa Redis | Dùng claim/recovery |
| Tạo group bằng `$` rồi kỳ vọng đọc lịch sử | Có thể không nhận event cũ | Tạo từ `0` khi cần lịch sử |
| Dùng consumer name cố định khi test song song | PEL và ownership bị can nhiễu | Cô lập stream/group/consumer |
| Dùng `Thread.sleep` rất ngắn để đợi event | Flaky test | Latch/future/deadline rõ |
| Test claim ngay bằng min idle production dài | Test chậm và không ổn định | Dùng `Duration.ZERO` khi test contract claim |
| Dùng min idle 0 trong production | Hai worker có thể cùng xử lý | Ngưỡng idle/lease phù hợp |
| Assert sau `XCLAIM` pending count bằng 0 | Hiểu nhầm claim thành ACK | Assert owner thay đổi, pending giữ nguyên |
| Đọc `XREADGROUP ... >` sau restart rồi bỏ PEL | Pending cũ bị mắc kẹt | Recovery startup/periodic |
| Không xử lý cursor `XAUTOCLAIM` | Bỏ sót pending ở batch sau | Lặp theo cursor, có giới hạn |
| Giả định ACK xóa payload | Test retention sai | Phân biệt `XACK` và `XDEL` |
| Trim payload nhưng kỳ vọng claim phục hồi | Dữ liệu đã bị xóa không thể tạo lại | Retention đủ và cảnh báo |
| Assert mọi worker xử lý chia đều | Scheduling không đảm bảo điều đó | Assert tổng ID độc nhất và invariant |
| Assert handler chỉ chạy đúng một lần sau crash | Trái mục tiêu at-least-once | Assert effect đúng một lần |
| Không đóng listener/subscription giữa test | Test sau nhận nhầm event | Quản lý lifecycle và cleanup |
| Chỉ mock Redis khi test PEL | Không phản ánh server semantics | Integration test với Redis thật |
| Dùng Redis production cho test trim/claim | Có thể phá dữ liệu thật | Testcontainers/Redis chuyên dụng |

## 27. Quy trình kiểm thử đề xuất

```text
Bắt đầu: Cần xác minh consumer group
                     |
                     v
           Tạo stream test riêng
                     |
                     v
             XADD event có eventId
                     |
                     v
       Tạo group ở offset có chủ đích
                     |
                     v
           XREADGROUP ... >
                     |
              +------+------+
              |             |
          Handler OK     Handler lỗi/crash
              |             |
              v             v
       Commit side effect  Không ACK
              |             |
              v             v
             XACK       Kiểm tra XPENDING
              |             |
              v             v
        PEL giảm       Same-consumer replay
                          hoặc XCLAIM/
                           XAUTOCLAIM
                                |
                                v
                         Idempotent handler
                                |
                                v
                               XACK
                                |
                                v
                      Assert business state
                       và pending = 0
                                |
                                v
                   Thử retention, failover,
                   nhiều group và concurrency
```

Nên xây các lớp test theo độ phức tạp tăng dần:

1. **Unit test** cho mapping payload, idempotency policy, quy tắc ACK-after-success trong code ứng dụng; có thể mock handler và gateway.
2. **Integration test Redis thật** cho `XADD`, group offset, `XREADGROUP`, `XPENDING`, `XACK`, `XCLAIM` và `XAUTOCLAIM`.
3. **Integration test với database thật** cho transaction nghiệp vụ và dedup event ID.
4. **Failure/chaos test** cho crash trước ACK, crash sau commit, Redis disconnect, failover, retention và nhiều replica.

Test không nhất thiết phải là một kịch bản end-to-end duy nhất quá dài. Những test nhỏ độc lập giúp xác định lỗi nằm ở protocol, API, business handler hay hạ tầng.

## 28. Tình huống tổng hợp: xử lý ORDER_PAID

Giả sử ứng dụng dùng:

```text
Stream: stream:orders:v1
Group:  billing-projections
Consumers: billing-a, billing-b
```

Mỗi event `ORDER_PAID` cập nhật bảng thống kê, và database có bảng `processed_events` để đảm bảo không cộng doanh thu hai lần.

### Kịch bản 1: thành công bình thường

```text
XADD e1
billing-a XREADGROUP e1
DB commit side effect và processed_events(e1)
billing-a XACK e1
XPENDING == 0
```

Assertions:

- `processed_events` chứa e1 đúng một lần.
- Tổng doanh thu tăng đúng theo e1.
- PEL không còn e1.
- Entry e1 vẫn có thể nằm trong stream cho đến khi retention xóa.

### Kịch bản 2: DB thất bại trước commit

```text
XADD e2
billing-a XREADGROUP e2
DB rollback/handler lỗi
KHÔNG XACK
billing-b claim e2 sau idle phù hợp
DB commit e2
billing-b XACK e2
```

Assertions:

- Trước claim, e2 còn pending.
- Sau claim, owner chuyển sang B, pending vẫn còn.
- Sau commit và ACK, pending giảm.
- Business effect e2 xảy ra đúng một lần.

### Kịch bản 3: crash sau commit nhưng trước ACK

```text
XADD e3
billing-a XREADGROUP e3
DB commit e3
Crash trước XACK
billing-b claim e3
Handler B phát hiện e3 đã xử lý
B không cộng doanh thu lần hai
B XACK e3
```

Assertions:

- Handler có thể được thử lại.
- Bảng nghiệp vụ không tăng hai lần.
- PEL cuối cùng về 0.
- Không dùng sự kiện “replay” làm lý do tạo email/hóa đơn lặp nếu những side effect đó cũng cần idempotency.

### Kịch bản 4: offline quá thời gian retention

```text
billing-a/b ngừng đọc
producer tiếp tục XADD
stream bị trim theo MAXLEN
consumer quay lại
```

Assertions:

- Hệ thống phát hiện có khoảng message cần xử lý nhưng payload không còn.
- Không báo “đã xử lý đủ” chỉ vì group lag giảm.
- Có quy trình khôi phục từ event log/kho authoritative khác nếu yêu cầu nghiệp vụ không được mất dữ liệu.
- Chính sách retention phải được tăng hoặc kiến trúc lưu trữ thay đổi nếu trường hợp này không được chấp nhận.

## 29. Các tiêu chí hoàn thành kiểm thử consumer group

Một hệ thống dùng Redis Streams để xử lý sự kiện quan trọng nên chứng minh được các bất biến sau:

1. **Event mới có thể được đọc** từ vị trí group được tạo đúng theo thiết kế.
2. **Đọc không đồng nghĩa xử lý xong:** entry được giao phải nằm trong PEL cho tới ACK.
3. **ACK chỉ sau thành công** theo ranh giới commit được định nghĩa.
4. **ACK lặp không tạo xử lý trùng**, và kết quả 0 được hiểu đúng.
5. **Crash trước ACK có thể phục hồi** từ pending còn payload.
6. **Worker mới không chỉ đọc `>` mà còn claim pending cũ**.
7. **Claim không được nhầm là ACK**, ownership và pending được kiểm tra riêng.
8. **Crash sau commit trước ACK không tạo double side effect** nhờ idempotency.
9. **Nhiều group có tiến độ riêng** và không chia sẻ ACK.
10. **Retention đủ dài** cho offline, retry và recovery theo tải cao điểm.
11. **Test có cô lập và deadline**, không dựa vào lệnh chờ vô hạn hoặc thứ tự scheduling may rủi.
12. **Metrics tách delivered, processed, ACK và pending**, tránh suy luận từ một chỉ số lag duy nhất.

## 30. Kết luận

**Kiểm thử consumer group, acknowledgment và bản ghi đang chờ** trong Spring Data Redis phải kiểm tra cả **trạng thái Redis** lẫn **kết quả nghiệp vụ**. `XREADGROUP` tạo ra trách nhiệm xử lý, `XPENDING` cho thấy trách nhiệm chưa hoàn thành, `XCLAIM`/`XAUTOCLAIM` cho phép chuyển trách nhiệm sau lỗi, còn `XACK` xác nhận hoàn tất theo group — nhưng không xóa dữ liệu khỏi stream và cũng không tự commit transaction database.

Một bộ test đáng tin cậy phải cố tình tạo những khoảng sự cố quan trọng: **đọc rồi crash, xử lý thất bại, commit rồi crash trước ACK, consumer mới claim pending và stream bị trim khi còn backlog**. Đồng thời, test phải chứng minh idempotency ở tầng nghiệp vụ: sự kiện có thể được gửi lại, nhưng tác dụng không được lặp ngoài ý muốn.

**Nguyên tắc cốt lõi:** Đừng chỉ hỏi “consumer đã nhận được bao nhiêu message?”. Hãy hỏi **“message nào đã được giao, message nào đang pending, message nào đã được commit thành công, và điều gì xảy ra với từng message khi worker biến mất?”** Khi các câu hỏi đó được kiểm chứng bằng Redis thật và assertion nghiệp vụ rõ ràng, hệ thống mới có cơ sở để vận hành Redis Streams consumer group an toàn.

