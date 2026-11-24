# TTL key và metadata

Trong một luồng Spring Integration dùng Redis, không phải dữ liệu nào cũng có cùng vòng đời. Dấu chống xử lý trùng thường chỉ cần tồn tại trong một khoảng thời gian; checkpoint đồng bộ có thể phải tồn tại qua nhiều lần khởi động lại. Chọn đúng TTL (time to live) và cách lưu metadata giúp luồng xử lý chịu được retry, restart và message đến lặp mà không làm mất trạng thái cần thiết.

Bài này đặt TTL và metadata trong bối cảnh Redis adapter: message đi vào flow qua inbound adapter, được định tuyến bằng `MessageChannel`, rồi handler đọc hoặc cập nhật trạng thái Redis. Cùng nguyên tắc đó có thể áp dụng khi một flow phối hợp Redis với file, SFTP, HTTP, JMS, AMQP, Kafka hoặc cơ sở dữ liệu: giữ hợp đồng message ổn định và xác định rõ trạng thái nào cần tồn tại bao lâu.

## 1. Phân biệt TTL và metadata

**TTL** là thời gian một Redis key còn hiệu lực. Khi hết hạn, Redis loại key khỏi không gian dữ liệu. TTL phù hợp với dữ liệu tạm thời như:

- Dấu nhận diện event đã được tiếp nhận để chặn bản gửi lặp trong một cửa sổ thời gian.
- Trạng thái xử lý tạm thời hoặc lease của một công việc.
- Cache kết quả tra cứu, token ngắn hạn hoặc thông tin phiên làm việc.

**Metadata** là dữ liệu mô tả tiến độ hoặc ngữ cảnh của một luồng tích hợp, thường nhỏ hơn payload. Ví dụ: offset cuối cùng đã xử lý, mã bản ghi cuối cùng, ETag của tài nguyên HTTP, tên file đã nhập hoặc watermark của lần đồng bộ gần nhất. Metadata thường cần tồn tại sau khi ứng dụng restart để flow tiếp tục từ vị trí phù hợp.

Hai khái niệm có thể cùng được lưu trong Redis nhưng phục vụ hai mục đích khác nhau. Đừng đặt TTL ngắn cho checkpoint chỉ vì dữ liệu đó được lưu trong Redis. Ngược lại, cũng không nên giữ vô thời hạn mọi dấu chống trùng nếu nghiệp vụ chỉ yêu cầu một cửa sổ chống lặp hữu hạn.

| Dữ liệu | Vòng đời thường gặp | Câu hỏi cần trả lời |
| --- | --- | --- |
| Idempotency key | Có TTL | Trong bao lâu một event đến lại vẫn phải được xem là trùng? |
| Processing lease | TTL ngắn, có thể gia hạn | Worker được giữ quyền xử lý tối đa bao lâu? |
| Checkpoint / offset | Thường không TTL | Khi restart, flow phải tiếp tục từ đâu? |
| ETag hoặc cache metadata | Có TTL hoặc được thay thế khi nguồn đổi | Bao lâu thì cần kiểm tra lại nguồn? |

## 2. TTL hoạt động ở cấp Redis key

Redis lưu thời hạn hết hạn trên key. Có thể đặt TTL ngay khi tạo key:

```redis
SET si:orders:dedup:event-8421 1 NX EX 86400
TTL si:orders:dedup:event-8421
```

`NX` chỉ tạo key khi key chưa tồn tại; `EX 86400` đặt thời hạn 86.400 giây. Cách kết hợp này hữu ích cho thao tác claim một idempotency key trong một cửa sổ 24 giờ. `TTL` trả về số giây còn lại; giá trị `-2` nghĩa là key không tồn tại, còn `-1` nghĩa là key tồn tại nhưng không có thời hạn hết hạn.

Một số điểm cần nhớ:

- `SET` lại key mà không chỉ định TTL thường làm mất TTL cũ. Nếu cần giữ thời hạn cũ, phải dùng cách cập nhật có chủ đích và kiểm tra hỗ trợ của phiên bản Redis/client đang dùng.
- TTL thuộc về key. Nếu nhiều mục metadata được gom vào một Redis hash, đặt TTL cho hash sẽ ảnh hưởng toàn bộ hash, không tạo thời hạn riêng cho từng field.
- TTL là cơ chế hết hạn dữ liệu, không phải bộ lập lịch chính xác. Không dùng thời điểm key hết hạn để kích hoạt một nghiệp vụ cần chạy đúng vào một thời điểm cụ thể.
- Redis có thể xóa key khi truy cập hoặc qua quá trình quét hết hạn nền. Ứng dụng không nên phụ thuộc vào một thời điểm xóa chính xác đến mili giây.

Chọn TTL theo cửa sổ nghiệp vụ. Với idempotency key, TTL cần bao phủ thời gian message có thể được gửi lại, retry và replay thủ công. TTL quá ngắn làm event cũ được xử lý lần nữa; TTL quá dài làm Redis giữ nhiều key không còn giá trị. Nếu nghiệp vụ yêu cầu chống trùng lâu dài, hãy lưu ràng buộc idempotency bền vững trong cơ sở dữ liệu thay vì dựa duy nhất vào key có TTL.

## 3. Lưu metadata bằng Spring Integration

Spring Integration định nghĩa abstraction `MetadataStore` cho thao tác đọc, ghi và xóa các cặp key/value metadata. `RedisMetadataStore` là một implementation dùng Redis, phù hợp khi nhiều lần chạy của ứng dụng cần chia sẻ trạng thái tiến độ.

Ví dụ khai báo bean:

```java
@Bean
MetadataStore integrationMetadataStore(RedisConnectionFactory connectionFactory) {
    return new RedisMetadataStore(connectionFactory);
}
```

Một flow đồng bộ đơn nguồn có thể lưu mã bản ghi cuối cùng đã xử lý:

```java
String checkpointKey = "erp:orders:last-id";

String lastId = metadataStore.get(checkpointKey);
// Đọc nguồn từ sau lastId, xử lý thành công một batch rồi mới tiến checkpoint.
String nextId = batch.lastSuccessfullyProcessedId();

if (lastId == null) {
    metadataStore.putIfAbsent(checkpointKey, nextId);
} else if (!metadataStore.replace(checkpointKey, lastId, nextId)) {
    throw new IllegalStateException("Checkpoint đã được cập nhật bởi luồng khác");
}
```

`putIfAbsent` hữu ích khi khởi tạo trạng thái; `replace` hỗ trợ cập nhật có điều kiện theo giá trị cũ. Nếu có nhiều consumer cùng cập nhật một checkpoint, cần xử lý trường hợp cập nhật thất bại bằng cách đọc lại và áp dụng chiến lược đồng bộ phù hợp. Nếu chỉ có một consumer sở hữu nguồn dữ liệu, vẫn nên ghi rõ giả định một writer trong thiết kế.

`MetadataStore` mô tả hợp đồng lưu metadata, không truyền TTL trong các thao tác `get`, `put` hoặc `replace`. Vì vậy, không nên mặc định mọi metadata entry có thể được đặt TTL riêng chỉ bằng cách dùng abstraction này. Nếu cần TTL cho từng mục, có thể dùng các Redis key riêng qua `StringRedisTemplate`/`RedisTemplate`, hoặc xây dựng implementation `MetadataStore` có chính sách hết hạn rõ ràng. Tránh sửa trực tiếp key nội bộ của `RedisMetadataStore`; cấu trúc lưu trữ đó là chi tiết của implementation.

## 4. Tạo key có TTL từ một handler

Với dữ liệu tạm thời, `StringRedisTemplate` cho phép đặt giá trị và TTL trong cùng một thao tác. Ví dụ sau tạo dấu chống trùng trong 48 giờ:

```java
@Component
class OrderIdempotencyKeys {

    private final StringRedisTemplate redis;

    OrderIdempotencyKeys(StringRedisTemplate redis) {
        this.redis = redis;
    }

    boolean claim(String eventId) {
        String key = "si:orders:dedup:" + eventId;
        Boolean created = redis.opsForValue().setIfAbsent(
                key,
                "1",
                Duration.ofHours(48));
        return Boolean.TRUE.equals(created);
    }
}
```

`setIfAbsent` với thời hạn thực hiện thao tác tạo key có điều kiện một cách nguyên tử ở Redis. Chỉ một consumer trong số các consumer cạnh tranh cùng `eventId` nhận được `true`; consumer còn lại xem đó là event đã được claim. Đoạn code giả định `eventId` là mã nghiệp vụ ổn định do nguồn gửi cung cấp. Không dùng `MessageHeaders.ID` làm idempotency key vì ID của message có thể thay đổi khi message được tạo lại.

Một inbound flow có thể nhận message từ Redis queue rồi chuyển vào channel xử lý:

```java
@Bean
IntegrationFlow ordersFromRedis(RedisConnectionFactory connectionFactory) {
    return IntegrationFlow
            .from(new RedisQueueInboundChannelAdapter(connectionFactory, "orders:in"))
            .channel("orders.input")
            .get();
}
```

Flow trên minh họa ranh giới nhận message. Handler phía sau channel có thể lấy `eventId`, kiểm tra idempotency key và cập nhật metadata sau khi xử lý. Cấu hình serializer/deserializer của adapter phải khớp với hợp đồng payload mà producer gửi; không giả định payload đã là một Java object nếu hai đầu chưa thống nhất định dạng.

**Lưu ý về thứ tự ghi dấu:** nếu tạo dấu chống trùng trước khi gọi nghiệp vụ, rồi handler lỗi, lần retry có thể bị bỏ qua dù nghiệp vụ chưa hoàn tất. Nếu chỉ ghi dấu sau nghiệp vụ, hai consumer đồng thời hoặc crash giữa hai thao tác có thể gây xử lý lặp. Redis key có TTL tự nó không tạo ra bảo đảm exactly-once cho một side effect bên ngoài Redis. Với cập nhật quan trọng trong cơ sở dữ liệu, hãy dùng khóa duy nhất theo event ID, transaction/outbox hoặc một cơ chế idempotent ở tầng nghiệp vụ. Nếu dùng key làm lease, cần có token sở hữu và thao tác gia hạn/giải phóng có kiểm tra token để worker cũ không xóa lease của worker mới.

## 5. Thiết kế namespace và chính sách vòng đời

Đặt tên key theo ứng dụng, môi trường, luồng và mục đích để dễ tìm kiếm, giám sát và dọn dẹp:

```text
si:{environment}:{flow}:{purpose}:{business-id}

si:prod:orders:dedup:event-8421
si:prod:erp:checkpoint:last-order-id
si:prod:catalog:etag:products
```

Các thành phần trong tên key nên ổn định và có quy ước chung. Không đưa mật khẩu, token, dữ liệu cá nhân hoặc toàn bộ payload vào tên key. Nếu business ID có thể chứa ký tự phân tách, chuẩn hóa hoặc encode trước khi ghép key.

Trước khi chọn TTL, hãy trả lời các câu hỏi sau:

1. Nguồn có thể gửi lại message trong bao lâu, kể cả retry và replay thủ công?
2. Một worker có thể xử lý lâu hơn TTL hay không? Nếu có, lease cần được gia hạn thế nào?
3. Metadata có phải sống qua lần deploy, restart hoặc chuyển consumer không?
4. Khi Redis mất kết nối, flow phải dừng và retry, chuyển message sang error channel, hay chấp nhận xử lý với rủi ro trùng?
5. Ai chịu trách nhiệm xóa trạng thái cũ và giới hạn dung lượng Redis?

Một checkpoint chỉ được cập nhật sau khi batch tương ứng đã xử lý thành công. Nếu ghi checkpoint trước side effect, sự cố giữa hai bước có thể khiến lần chạy sau bỏ qua dữ liệu chưa xử lý. Nếu ghi sau side effect, cần bảo đảm việc chạy lại batch là an toàn hoặc có idempotency ở tầng nghiệp vụ.

## 6. Lỗi thường gặp và cách xử lý

| Tình huống | Hậu quả | Cách xử lý |
| --- | --- | --- |
| TTL ngắn hơn cửa sổ retry/replay | Event cũ được xử lý lại sau khi key hết hạn | Tính TTL theo chính sách retry và thời gian replay thực tế |
| Checkpoint bị đặt TTL ngắn | Flow restart và đọc lại từ vị trí cũ hoặc mất mốc tiến độ | Giữ checkpoint bền vững; chỉ đặt TTL khi có quy trình khôi phục rõ ràng |
| Ghi lại key bằng `SET` không TTL | TTL cũ bị loại bỏ, key tồn tại lâu hơn dự kiến | Đặt TTL trong cùng thao tác ghi hoặc chủ động kiểm tra TTL sau cập nhật |
| Nhiều luồng cùng cập nhật checkpoint | Một luồng ghi đè tiến độ của luồng khác | Dùng `replace` có điều kiện, phân vùng checkpoint hoặc bảo đảm một writer |
| Redis không truy cập được | Không thể kiểm tra idempotency hoặc lưu tiến độ | Chọn chính sách fail-fast/retry hoặc fail-open có đánh giá rõ rủi ro; phát lỗi vào error flow phù hợp |
| Dấu được ghi trước side effect rồi handler lỗi | Retry bị nhận nhầm là message đã hoàn tất | Dùng trạng thái claim/complete có kiểm soát hoặc idempotency bền vững ở hệ thống đích |

Không coi việc Redis trả lời thành công là bằng chứng nghiệp vụ đã hoàn tất. Log nên có `eventId`, tên flow, trạng thái xử lý và checkpoint liên quan; tránh log giá trị nhạy cảm. Metric hữu ích gồm số key được tạo, số message bị nhận diện trùng, số lần retry, lỗi Redis và độ trễ xử lý. Khi điều tra, dùng `TTL`/`PTTL` trên key cụ thể để kiểm tra thời hạn còn lại.

## 7. Kiểm tra hành vi trước khi đưa flow vào vận hành

Với một flow có idempotency key và checkpoint, hãy kiểm tra ít nhất các trường hợp sau:

- Gửi cùng một `eventId` hai lần trong TTL và xác nhận lần gửi sau đi theo nhánh duplicate.
- Gửi lại sau khi TTL hết hạn và xác nhận chính sách cho phép xử lý lại hoạt động như thiết kế.
- Khởi động lại ứng dụng và xác nhận checkpoint vẫn còn, flow tiếp tục từ vị trí đã commit.
- Chạy hai consumer đồng thời với cùng một `eventId` để xác nhận thao tác claim không cấp quyền cho cả hai.
- Làm Redis tạm thời không truy cập được và xác nhận retry/error flow thực hiện đúng chính sách đã chọn.
- Làm handler lỗi sau khi claim key để xác nhận cơ chế phục hồi không bỏ mất nghiệp vụ.

TTL và metadata là hai phần của hợp đồng vận hành của adapter. Khi thiết kế rõ key nào tạm thời, key nào là tiến độ bền vững, ai được cập nhật và điều gì xảy ra khi Redis lỗi, flow Spring Integration sẽ dễ phục hồi và dễ quan sát hơn.
