# Lỗi serialize

Trong module SPRING_MODULITH_APPLICATION_EVENTS, application event có thể đi qua nhiều ranh giới lưu trữ và truyền tin. Khi một event được lưu vào Event Publication Registry hoặc chuyển thành message để gửi tới hệ thống khác, ứng dụng phải chuyển object thành một dạng dữ liệu có thể lưu hoặc truyền đi. Quá trình này gọi là serialization. Ở chiều ngược lại, hệ thống đọc dữ liệu và dựng lại object bằng deserialization.

Lỗi serialize thường xuất hiện khi payload chứa kiểu dữ liệu mà serializer không hỗ trợ, object có cấu trúc không phù hợp, cấu hình giữa publisher và consumer không thống nhất hoặc schema đã thay đổi. Muốn xử lý đúng, trước hết cần xác định lỗi xảy ra ở ranh giới nào.

## 1. Serialization nằm ở đâu trong luồng application events?

Một event có thể đi qua nhiều chặng, mỗi chặng có serializer hoặc message converter riêng:

~~~mermaid
flowchart LR
    A[Publish application event] --> B[Event Publication Registry]
    B --> C[Externalization listener]
    C --> D[Message converter / serializer]
    D --> E[Broker hoặc hệ thống đích]
    E --> F[Consumer deserializer]
~~~

- **Publication registry:** nếu cấu hình lưu publication bền vững, event cần được biểu diễn thành dữ liệu để lưu cùng thông tin publication. Serializer của tầng lưu trữ chịu trách nhiệm cho ranh giới này.
- **Externalization:** event được chuyển thành message theo hợp đồng tích hợp. Message converter hoặc serializer của integration adapter quyết định payload và header gửi đi.
- **Consumer:** hệ thống nhận giải mã payload theo schema và kiểu dữ liệu mà nó hiểu.

Ba chặng có thể dùng cấu hình hoặc công nghệ khác nhau. Một event lưu được trong registry chưa chắc đã serialize được bằng message converter của broker; message gửi thành công cũng chưa chắc consumer có thể deserialize. Vì vậy, không nên gom mọi lỗi vào một khái niệm chung rồi thay đổi serializer một cách tùy ý.

## 2. Nhận biết lỗi xảy ra ở ranh giới nào

| Dấu hiệu | Ranh giới có thể gặp lỗi | Điều cần kiểm tra đầu tiên |
| --- | --- | --- |
| Publish event thất bại ngay trong transaction hoặc lúc đăng ký publication | Ghi nhận hoặc serialize publication | Kiểu event, serializer lưu trữ, object graph và cấu hình persistence registry |
| Publication đã được ghi nhận nhưng listener externalization lỗi | Chuyển event thành message | Message converter, serializer, header, target và payload |
| Broker nhận message nhưng consumer báo lỗi parse hoặc binding | Deserialization ở consumer | Định dạng thực tế, schema version, tên field, kiểu dữ liệu và cấu hình consumer |
| Chỉ lỗi sau khi deploy phiên bản mới | Tương thích schema giữa các phiên bản | Thay đổi field, kiểu dữ liệu, tên class và chính sách nâng cấp |

Đọc stack trace để tìm lớp phát sinh lỗi đầu tiên và thời điểm nó xảy ra. Ghi nhận event type, event ID, listener hoặc target, serializer/converter đang dùng và correlation ID. Những thông tin này giúp phân biệt lỗi lưu publication với lỗi gửi message hoặc lỗi đọc message.

## 3. Những nguyên nhân thường gặp

**Kiểu dữ liệu không được hỗ trợ.** Serializer không biết cách chuyển một kiểu tùy chỉnh, kiểu thư viện bên ngoài hoặc object đặc thù thành JSON hay định dạng khác. Các kiểu ngày giờ như `Instant`, `LocalDate` và `OffsetDateTime` cần module hỗ trợ tương ứng khi dùng Jackson.

**Entity JPA và object proxy.** Gửi trực tiếp entity có thể kéo theo lazy proxy, collection chưa được tải, quan hệ hai chiều hoặc object graph rất lớn. Khi serializer truy cập property, Hibernate có thể yêu cầu session đã đóng hoặc tạo vòng tham chiếu vô hạn.

**Vòng tham chiếu trong object graph.** Ví dụ `Order` tham chiếu `Customer`, trong khi `Customer` lại chứa danh sách `Order`. Serializer có thể lặp vô hạn hoặc từ chối chu trình tùy cấu hình.

**Đa hình không rõ kiểu.** Field khai báo bằng interface hoặc abstract class có nhiều implementation. Khi deserialize, serializer không biết cần tạo implementation nào nếu hợp đồng không cung cấp type discriminator hoặc quy tắc mapping rõ ràng.

**Payload thay đổi theo thời gian.** Publisher thêm, xóa hoặc đổi kiểu field nhưng consumer vẫn dùng schema cũ. Đổi tên class hoặc package cũng có thể làm hỏng những định dạng lưu trữ phụ thuộc trực tiếp vào tên lớp.

**Cấu hình khác nhau giữa các môi trường.** Ứng dụng phát dùng một ObjectMapper hoặc message converter, còn môi trường test hay consumer dùng cấu hình khác. Một kiểu dữ liệu có thể hoạt động ở máy phát triển nhưng lỗi khi chạy production.

**Payload quá lớn hoặc chứa dữ liệu không cần thiết.** Gửi toàn bộ aggregate, binary data hoặc dữ liệu nhạy cảm làm tăng chi phí serialize, dung lượng registry và kích thước message; broker cũng có thể từ chối message vượt giới hạn.

## 4. Thiết kế event payload dễ serialize

Ưu tiên event payload là một hợp đồng dữ liệu nhỏ, rõ nghĩa và ổn định. Với integration event, thường nên dùng DTO hoặc Java record thay vì gửi entity JPA hay object nội bộ của domain model.

Ví dụ một event có cấu trúc đơn giản:

~~~java
import java.time.Instant;
import java.util.UUID;

public record OrderConfirmedIntegrationEvent(
        UUID eventId,
        UUID orderId,
        Instant occurredAt,
        int schemaVersion) {
}
~~~

Payload này chỉ chứa định danh, thời điểm và phiên bản hợp đồng. Consumer không phải khởi tạo entity hoặc hiểu quan hệ JPA của publisher. `eventId` cũng hỗ trợ consumer nhận biết message được giao lại.

Những nguyên tắc nên áp dụng:

- Chỉ đưa vào payload dữ liệu consumer cần để xử lý.
- Dùng kiểu dữ liệu phổ biến, có biểu diễn ổn định như string, số, boolean, UUID và ngày giờ theo chuẩn đã thống nhất.
- Xác định rõ format cho tiền tệ, thời gian, số thập phân và enum.
- Tránh gửi entity, Hibernate proxy, stream, connection, file handle hoặc object phụ thuộc vào trạng thái runtime.
- Tránh vòng tham chiếu; mô hình hóa quan hệ bằng ID thay vì nhúng cả object graph.
- Có event type và schema version rõ ràng khi hợp đồng được chia sẻ giữa nhiều hệ thống.

Không dùng Java native serialization làm hợp đồng tích hợp lâu dài giữa các dịch vụ độc lập. Định dạng trao đổi như JSON hoặc Avro/Protobuf có schema được quản lý thường giúp việc tương thích và quan sát payload rõ ràng hơn.

## 5. Cấu hình Jackson cho kiểu dữ liệu phổ biến

Nếu ứng dụng dùng Jackson để serialize JSON, cần bảo đảm ObjectMapper có module hỗ trợ các kiểu dữ liệu được payload sử dụng. Ví dụ sau minh họa cấu hình cho Java Time:

~~~java
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.SerializationFeature;
import com.fasterxml.jackson.datatype.jsr310.JavaTimeModule;

ObjectMapper mapper = new ObjectMapper()
        .registerModule(new JavaTimeModule())
        .disable(SerializationFeature.WRITE_DATES_AS_TIMESTAMPS);
~~~

Trong Spring Boot, hãy ưu tiên dùng ObjectMapper đã được cấu hình và quản lý bởi application context. Các starter phù hợp thường tự đăng ký module Jackson trên classpath; nếu ứng dụng tạo ObjectMapper thủ công, cấu hình tự động có thể bị bỏ qua. Tránh tạo một mapper mới ở từng listener vì các mapper có thể khác nhau về module, naming strategy, visibility và chính sách xử lý field lạ.

Ví dụ record phía trên có thể được chuyển thành JSON và đọc lại:

~~~java
String json = mapper.writeValueAsString(event);

OrderConfirmedIntegrationEvent restored = mapper.readValue(
        json, OrderConfirmedIntegrationEvent.class);
~~~

Đây là ví dụ kiểm tra khả năng serialize/deserialize của một kiểu payload với mapper cụ thể. Trong ứng dụng thực tế, hãy kiểm tra bằng chính ObjectMapper hoặc message converter được cấu hình trong runtime, thay vì chỉ kiểm tra một mapper tự tạo không được ứng dụng sử dụng.

Không bật default typing hoặc cơ chế nạp class tùy ý chỉ để xử lý lỗi đa hình. Việc cho phép payload chỉ định class cần khởi tạo có thể mở rộng bề mặt tấn công. Nếu cần đa hình, hãy dùng type discriminator có giới hạn và ánh xạ tới các kiểu được cho phép.

## 6. Tách lỗi serialization khỏi lỗi externalization

Event được đánh dấu để externalize bằng `@Externalized` vẫn cần adapter và message converter tương thích. Annotation mô tả ý định và target logic; nó không quyết định mọi chi tiết encoding cho tất cả broker.

Ví dụ một integration event:

~~~java
import java.time.Instant;
import java.util.UUID;
import org.springframework.modulith.events.Externalized;

@Externalized("orders")
public record OrderConfirmedIntegrationEvent(
        UUID eventId,
        UUID orderId,
        Instant occurredAt,
        int schemaVersion) {
}
~~~

Nếu publication được đăng ký nhưng listener externalization báo lỗi serialize, hãy kiểm tra serializer hoặc converter được adapter dùng để tạo message, bao gồm cấu hình content type và header. Không giả định serializer dùng để lưu publication trong registry cũng chính là serializer của broker.

Nếu broker đã nhận message nhưng consumer không đọc được, hãy lấy một message mẫu đã loại bỏ dữ liệu nhạy cảm và so sánh payload thực tế với schema consumer mong đợi. Kiểm tra encoding, content type, tên field, kiểu dữ liệu và version. Việc gửi thành công chỉ xác nhận chặng gửi; nó không chứng minh payload có thể được consumer giải mã.

## 7. Kiểm thử serialization

Kiểm thử serialization nên được thực hiện ở cấp hợp đồng. Một bài kiểm thử cơ bản có thể serialize event, deserialize lại và so sánh các field quan trọng:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import java.time.Instant;
import java.util.UUID;

import org.junit.jupiter.api.Test;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.SerializationFeature;
import com.fasterxml.jackson.datatype.jsr310.JavaTimeModule;

class OrderEventSerializationTests {

    private final ObjectMapper mapper = configuredObjectMapper();

    @Test
    void roundTripsOrderConfirmedEvent() throws Exception {
        var event = new OrderConfirmedIntegrationEvent(
                UUID.randomUUID(),
                UUID.randomUUID(),
                Instant.parse("2026-01-15T10:30:00Z"),
                1);

        String json = mapper.writeValueAsString(event);
        var restored = mapper.readValue(
                json, OrderConfirmedIntegrationEvent.class);

        assertThat(restored).isEqualTo(event);
    }

    private ObjectMapper configuredObjectMapper() {
        // Trong ứng dụng, ưu tiên inject ObjectMapper đã cấu hình.
        return new ObjectMapper()
                .registerModule(new JavaTimeModule())
                .disable(SerializationFeature.WRITE_DATES_AS_TIMESTAMPS);
    }
}
~~~

Đoạn kiểm thử minh họa round trip cho record; import `SerializationFeature` và `JavaTimeModule` cần được khai báo trong test như ở ví dụ cấu hình. Trong dự án thực tế, nên inject mapper của Spring thay vì dựng mapper riêng trong test để kiểm tra đúng cấu hình đang chạy.

Ngoài round trip, hãy kiểm tra:

1. Payload JSON hoặc binary có đúng format, field và content type đã công bố.
2. Consumer đọc được payload được tạo bởi phiên bản publisher trước đó.
3. Field bổ sung hoặc field tùy chọn được xử lý theo chính sách schema.
4. Enum, thời gian, số thập phân, null và giá trị biên có biểu diễn thống nhất.
5. Payload có kích thước nằm trong giới hạn vận hành của broker và hệ thống lưu trữ.
6. Message converter thực tế của integration adapter hoạt động trong kiểm thử tích hợp.

Với Event Publication Registry, kiểm thử cả đường ghi và đọc lại publication khi dùng persistence bền vững. Mục tiêu là xác minh serializer của registry có thể lưu event và khôi phục event sau khi ứng dụng khởi động lại.

## 8. Tương thích schema khi triển khai nhiều phiên bản

Message có thể nằm trong broker hoặc registry lâu hơn một lần triển khai. Publisher và consumer vì thế có thể chạy các phiên bản khác nhau trong cùng một khoảng thời gian.

Ưu tiên thay đổi tương thích:

- Thêm field mới theo cách consumer cũ có thể bỏ qua hoặc có giá trị mặc định được xác định rõ.
- Giữ nguyên kiểu và ý nghĩa của field hiện có.
- Không tái sử dụng tên field cũ cho ý nghĩa mới.
- Khi cần thay đổi phá vỡ tương thích, công bố schema hoặc event version mới và có kế hoạch chuyển consumer.
- Kiểm thử payload được lưu từ phiên bản cũ bằng code phiên bản mới trước khi nâng cấp production.

Không dựa vào tên class Java làm định danh schema duy nhất cho hợp đồng bên ngoài. Dùng event type và schema version rõ ràng để việc đổi package hoặc refactor nội bộ không làm thay đổi ý nghĩa message.

Nếu dữ liệu publication cũ không còn deserialize được sau khi đổi class hoặc schema, cần có kế hoạch migration hoặc chuyển đổi có kiểm soát. Không xóa publication chưa xử lý chỉ để loại bỏ lỗi đọc dữ liệu; trước hết xác định event đó còn cần xử lý hay có thể được xử lý thủ công theo quy trình nghiệp vụ.

## 9. Quy trình chẩn đoán và khắc phục

Khi gặp lỗi serialize, có thể đi theo trình tự sau:

1. **Xác định chặng lỗi.** Lỗi xuất hiện lúc publish/ghi registry, lúc listener externalize, lúc broker nhận message hay lúc consumer deserialize?
2. **Xác định kiểu event.** Ghi nhận event type, class payload, event ID, listener/target và phiên bản ứng dụng.
3. **Đọc nguyên nhân gốc.** Tìm exception đầu tiên trong stack trace: kiểu không hỗ trợ, proxy chưa tải, vòng tham chiếu, thiếu module, lỗi binding hay schema không tương thích.
4. **Tái hiện bằng payload tối thiểu.** Tạo một event nhỏ với các field liên quan để kiểm tra serializer hoặc converter thực tế.
5. **Sửa hợp đồng hoặc cấu hình tại đúng ranh giới.** Dùng DTO, đăng ký module cần thiết, loại bỏ object graph không cần thiết hoặc triển khai schema tương thích.
6. **Kiểm thử dữ liệu cũ và mới.** Đảm bảo payload đã lưu hoặc message đang tồn tại vẫn có thể được đọc theo kế hoạch chuyển đổi.
7. **Phục hồi publication.** Sau khi sửa nguyên nhân, dùng cơ chế retry/resubmit được hỗ trợ và theo dõi publication đến khi listener hoàn tất.

Phân biệt lỗi cấu hình cố định với lỗi tạm thời. Broker timeout có thể phù hợp với retry có backoff; một kiểu payload không serialize được thường sẽ tiếp tục thất bại cho tới khi code hoặc cấu hình được sửa. Retry vô hạn lỗi deterministic chỉ tạo thêm tải và làm publication tồn đọng.

Trong lúc điều tra, log event ID, event type, target, correlation ID và exception class. Tránh ghi toàn bộ payload, token hoặc dữ liệu cá nhân vào log. Nếu cần lưu message mẫu, hãy loại bỏ hoặc thay thế các giá trị nhạy cảm trước khi chia sẻ.

## 10. Những sai lầm cần tránh

- Gửi trực tiếp entity JPA và để serializer tự duyệt toàn bộ quan hệ.
- Tạo ObjectMapper mới ở nhiều nơi với cấu hình khác nhau.
- Cho rằng registry serializer và broker message converter luôn là một.
- Bật cơ chế deserialize class tùy ý để né lỗi đa hình.
- Thay đổi tên hoặc kiểu field mà không xem xét message cũ còn tồn tại.
- Retry liên tục một lỗi serialization deterministic mà chưa sửa nguyên nhân.
- Xóa publication chưa hoàn tất khi chưa xác định event có thể bị mất nghiệp vụ hay không.
- Ghi toàn bộ payload vào log để chẩn đoán dù payload chứa dữ liệu nhạy cảm.

## Kết luận

Lỗi serialize cần được chẩn đoán theo đúng ranh giới: lưu publication, chuyển event thành message hay đọc message ở consumer. Thiết kế payload nhỏ và ổn định, dùng DTO thay cho entity, cấu hình serializer nhất quán, kiểm thử round trip và quản lý schema theo phiên bản sẽ giảm lỗi khi ứng dụng phát triển. Với Spring Modulith, hãy theo dõi Event Publication Registry và externalization riêng biệt để có thể sửa đúng nguyên nhân, retry có kiểm soát và phục hồi giao sự kiện đáng tin cậy.
