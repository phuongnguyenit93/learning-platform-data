# MessageHeaderAccessor và quản lý trạng thái có thể thay đổi trong Spring Messaging

## 1. Mục tiêu: thay đổi metadata có kiểm soát

Trong Spring Messaging, một message gồm payload và headers. Payload chứa dữ liệu chính; headers mang metadata như correlation ID, content type, destination, thông tin phiên hoặc dữ liệu phục vụ định tuyến.

Headers thường được xem như dữ liệu bất biến sau khi message được tạo. Cách tiếp cận này giúp message có thể được chuyển qua nhiều handler, channel và thread mà không phải lo một thành phần bất ngờ thay đổi metadata mà thành phần khác đang đọc.

Tuy vậy, trong lúc xây dựng hoặc làm giàu message, ứng dụng đôi khi cần thêm, thay thế hoặc loại bỏ một header. **MessageHeaderAccessor** cung cấp API để thực hiện việc đó theo một vòng đời rõ ràng: tạo accessor, thay đổi metadata, tạo message, sau đó chuyển message đi xử lý.

Sau bài học, bạn cần có thể:

- Phân biệt MessageHeaders với MessageHeaderAccessor.
- Giải thích vì sao headers của message đã phát đi nên được xem là bất biến.
- Tạo message có custom headers và sửa metadata của một message hiện có bằng accessor.
- Dùng accessor chuyên biệt khi làm việc với header của STOMP hoặc Spring messaging.
- Hiểu tác động của trạng thái mutable tới interceptor, nhiều subscriber và xử lý đa luồng.
- Tránh sửa trực tiếp map headers, chia sẻ mutable state hoặc tin cậy metadata do client gửi lên.

## 2. MessageHeaders và MessageHeaderAccessor có vai trò khác nhau

### 2.1 MessageHeaders: phần headers của message

`MessageHeaders` là kiểu dữ liệu chứa metadata gắn với một message. Nó triển khai giao diện Map để đọc theo tên header, ví dụ:

~~~java
Object correlationId = message.getHeaders().get("app.correlationId");
~~~

Các thao tác cập nhật map trực tiếp không phải cách sửa message được hỗ trợ. `MessageHeaders` được thiết kế để cung cấp một góc nhìn chỉ đọc sau khi message được tạo. Ví dụ, gọi `put` hoặc `remove` trực tiếp trên map headers thường dẫn tới `UnsupportedOperationException`.

Thiết kế này có ích vì message có thể được chia sẻ giữa nhiều thành phần. Nếu một subscriber thay đổi header sau khi subscriber khác đã nhận cùng message, kết quả xử lý có thể phụ thuộc vào thứ tự chạy và thời điểm đọc.

Lưu ý: map headers không cho sửa trực tiếp không có nghĩa mọi object nằm trong đó đều bất biến sâu. Nếu header chứa một object mutable, code vẫn có thể thay đổi trạng thái bên trong object đó. Vì vậy, nên ưu tiên metadata có kiểu đơn giản và giá trị bất biến như String, UUID, số, enum hoặc kiểu thời gian bất biến.

### 2.2 MessageHeaderAccessor: công cụ thao tác metadata

`MessageHeaderAccessor` thuộc package `org.springframework.messaging.support`. Nó cung cấp các phương thức để:

- Đọc header theo tên.
- Thiết lập header mới hoặc thay giá trị hiện có.
- Chỉ thiết lập khi header chưa tồn tại.
- Xóa một header.
- Sao chép headers từ map khác.
- Lấy đối tượng `MessageHeaders` để tạo message.
- Lấy accessor mutable từ một message hiện có.

Một số phương thức thường dùng:

| API | Công dụng |
|---|---|
| `getHeader(name)` | Đọc giá trị header |
| `setHeader(name, value)` | Thêm hoặc thay giá trị header |
| `setHeaderIfAbsent(name, value)` | Chỉ thiết lập khi chưa có giá trị |
| `removeHeader(name)` | Loại bỏ header |
| `copyHeaders(map)` | Sao chép headers; giá trị cùng tên có thể bị ghi đè |
| `copyHeadersIfAbsent(map)` | Chỉ sao chép những header chưa có |
| `getMessageHeaders()` | Lấy MessageHeaders để xây dựng message |
| `getMutableAccessor(message)` | Lấy accessor mutable được khởi tạo từ message |

Hãy dùng accessor trong giai đoạn tạo hoặc biến đổi message. Sau khi tạo message mới, chuyển message đó cho channel hoặc handler tiếp theo và xem metadata là dữ liệu đã chốt.

## 3. Tạo message với accessor

Có thể khởi tạo accessor mới, đặt các custom headers rồi tạo message bằng `MessageBuilder.createMessage`.

~~~java
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.messaging.support.MessageHeaderAccessor;

public class HeaderAccessorDemo {

    public static void main(String[] args) {
        MessageHeaderAccessor accessor = new MessageHeaderAccessor();
        accessor.setHeader("app.correlationId", "corr-42");
        accessor.setHeader("app.source", "checkout");

        Message<String> message = MessageBuilder.createMessage(
                "order.created",
                accessor.getMessageHeaders()
        );

        System.out.println(message.getPayload());
        System.out.println(message.getHeaders().get("app.correlationId"));
    }
}
~~~

Kết quả:

~~~text
order.created
corr-42
~~~

Trong ví dụ:

1. Tạo một accessor độc lập.
2. Thêm correlation ID và nguồn phát message.
3. Lấy MessageHeaders từ accessor.
4. Dùng payload và headers để tạo một message hoàn chỉnh.
5. Đọc metadata qua `message.getHeaders()`.

Ví dụ dùng package `spring-messaging` của Spring Framework. Với dự án Spring Boot, hãy để dependency management của phiên bản Boot đang dùng quản lý phiên bản Spring tương thích.

## 4. Lấy accessor mutable từ message hiện có

Một tình huống thường gặp là message đã được tạo nhưng cần thêm metadata trước khi gửi tới bước tiếp theo. Không sửa trực tiếp `message.getHeaders()`. Hãy lấy accessor mutable rồi tạo một message mới.

~~~java
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.messaging.support.MessageHeaderAccessor;

public class EnrichMessageDemo {

    public static void main(String[] args) {
        Message<String> original = MessageBuilder
                .withPayload("order.created")
                .setHeader("app.correlationId", "corr-42")
                .build();

        MessageHeaderAccessor accessor =
                MessageHeaderAccessor.getMutableAccessor(original);

        accessor.setHeader("app.processingAttempt", 1);

        Message<String> enriched = MessageBuilder.createMessage(
                original.getPayload(),
                accessor.getMessageHeaders()
        );

        System.out.println(enriched.getPayload());
        System.out.println(enriched.getHeaders().get("app.correlationId"));
        System.out.println(enriched.getHeaders().get("app.processingAttempt"));
    }
}
~~~

Kết quả:

~~~text
order.created
corr-42
1
~~~

`getMutableAccessor(message)` tạo hoặc cung cấp accessor có thể chỉnh sửa dựa trên headers của message được truyền vào. Accessor giữ lại metadata hiện có để bạn có thể bổ sung hoặc cập nhật có chủ đích.

Trong ví dụ, message mới giữ nguyên payload và correlation ID, đồng thời có thêm processing attempt. Message ban đầu vẫn là đối tượng đầu vào của bước biến đổi. Hãy chuyển message mới tới channel tiếp theo.

Cách làm này thể hiện rõ một nguyên tắc: **biến đổi message bằng cách tạo message kế tiếp với metadata đã được chuẩn bị**, thay vì để nhiều thành phần cùng sửa một message đang được sử dụng.

## 5. Chọn đúng cách cập nhật header

### 5.1 Ghi đè hay chỉ bổ sung

Hai thao tác có ngữ nghĩa khác nhau:

~~~java
accessor.setHeader("app.correlationId", "corr-new");
accessor.setHeaderIfAbsent("app.source", "fallback");
~~~

- `setHeader` thay giá trị hiện tại nếu tên header đã tồn tại.
- `setHeaderIfAbsent` giữ giá trị hiện có và chỉ thêm giá trị khi header chưa được thiết lập.

Điều này quan trọng khi một message đi qua nhiều tầng. Ví dụ, gateway đã tạo correlation ID thì handler phía sau không nên tự ghi đè bằng một ID khác. Trong trường hợp đó, `setHeaderIfAbsent` phù hợp hơn.

Nếu ứng dụng chủ động tạo một message mới và cần đặt lại metadata theo hợp đồng, `setHeader` có thể là lựa chọn đúng.

### 5.2 Xóa và sao chép headers

Dùng `removeHeader` khi một metadata không còn hợp lệ ở bước tiếp theo:

~~~java
accessor.removeHeader("app.internalToken");
~~~

Dùng `copyHeaders` khi cần sao chép một nhóm metadata và chấp nhận ghi đè tên trùng:

~~~java
accessor.copyHeaders(sourceHeaders);
~~~

Dùng `copyHeadersIfAbsent` khi muốn giữ các giá trị đã được thiết lập trước đó:

~~~java
accessor.copyHeadersIfAbsent(defaultHeaders);
~~~

Không nên sao chép toàn bộ headers một cách máy móc qua mọi ranh giới. Một message có thể chứa header nội bộ, header của protocol, thông tin bảo mật hoặc dữ liệu chỉ có ý nghĩa trong một phiên cụ thể. Hãy xác định danh sách metadata thực sự cần được truyền tiếp.

### 5.3 Header hệ thống và custom header

Spring quản lý một số header nền tảng như ID và timestamp. Không nên tùy tiện ghi đè các header hệ thống hoặc dùng tên của framework cho dữ liệu nghiệp vụ riêng.

Đặt quy ước tên cho metadata của ứng dụng, ví dụ:

- `app.correlationId`: liên kết các message trong cùng một luồng nghiệp vụ.
- `app.tenantId`: ngữ cảnh tenant sau khi đã được xác minh.
- `app.source`: thành phần tạo message.
- `app.processingAttempt`: số lần xử lý theo quy ước của ứng dụng.
- `app.schemaVersion`: phiên bản schema của payload nếu hợp đồng yêu cầu.

Tên có namespace giúp tránh va chạm với header do Spring hoặc protocol adapter quản lý. Kiểu dữ liệu và ý nghĩa của mỗi header nên được định nghĩa nhất quán trong hợp đồng ứng dụng.

## 6. Accessor chuyên biệt cho protocol

`MessageHeaderAccessor` là lớp nền tảng. Một số module Spring cung cấp accessor chuyên biệt để thao tác với metadata có cấu trúc riêng của giao thức hoặc loại message.

Ví dụ trong Spring messaging:

- `SimpMessageHeaderAccessor` cung cấp cách truy cập các header liên quan tới mô hình simple messaging, chẳng hạn destination, session và message type.
- `StompHeaderAccessor` cung cấp cách thao tác với header và command của STOMP.
- `NativeMessageHeaderAccessor` hỗ trợ nhóm native headers đến từ protocol hoặc adapter.

Khi xử lý message thuộc một protocol cụ thể, nên dùng accessor tương ứng để đọc và cập nhật metadata theo đúng semantics của protocol. Không nên đoán tên header hoặc tự sửa cấu trúc native header bằng cách thao tác với map chung nếu framework đã có API chuyên biệt.

Có thể lấy accessor chuyên biệt đang gắn với message bằng API dạng:

~~~java
SimpMessageHeaderAccessor accessor =
        MessageHeaderAccessor.getAccessor(
                message,
                SimpMessageHeaderAccessor.class
        );
~~~

Giá trị trả về có thể là `null` nếu message không gắn với accessor thuộc kiểu được yêu cầu. Vì vậy, chỉ dùng API này khi luồng xử lý bảo đảm message đến từ đúng hạ tầng tương ứng, hoặc kiểm tra kết quả trước khi truy cập.

Accessor chuyên biệt không biến mọi message thành message STOMP hay WebSocket. Chỉ dùng nó trong đúng ngữ cảnh tích hợp.

## 7. Mutable state và vòng đời message

### 7.1 Vì sao cần chốt metadata trước khi gửi

Một message có thể đi qua nhiều channel, interceptor và handler. Channel cũng có thể phân phối cùng một message cho nhiều subscriber. Nếu headers còn mutable khi các thành phần bắt đầu xử lý song song, một thành phần có thể nhìn thấy giá trị khác với thành phần khác.

Ví dụ, hai subscriber cùng nhận message. Subscriber thứ nhất thay correlation ID trong một map dùng chung; subscriber thứ hai có thể ghi log hoặc gọi dịch vụ với correlation ID đã bị thay đổi. Kết quả truy vết khi đó không còn đáng tin cậy.

Vì vậy, hãy hoàn thành việc cập nhật metadata trước khi publish message. Sau khi gửi, coi message và các header value của nó là dữ liệu chỉ đọc.

### 7.2 setLeaveMutable và trường hợp nâng cao

`MessageHeaderAccessor` có API `setLeaveMutable(boolean)` để điều khiển việc giữ trạng thái mutable của MessageHeaders được tạo từ accessor. Đây là tùy chọn nâng cao, thường chỉ cần trong những luồng framework hoặc interceptor có chủ đích cần tiếp tục hoàn thiện headers trước khi message được chốt.

Không bật chế độ này theo thói quen. Nếu một message với headers mutable được chia sẻ hoặc chuyển sang xử lý bất đồng bộ trước khi hoàn tất, các thành phần có thể thay đổi cùng một trạng thái. Hãy chỉ dùng khi đã xác định rõ ai được phép cập nhật, cập nhật ở giai đoạn nào và khi nào trạng thái trở thành immutable.

Với code nghiệp vụ thông thường, dùng accessor mutable trong một phạm vi ngắn, tạo message đã hoàn thiện rồi gửi đi là cách dễ hiểu và an toàn hơn.

### 7.3 Payload cũng có thể chứa mutable state

Headers bất biến không làm payload tự động bất biến. Ví dụ, payload là một `ArrayList` hoặc một DTO có setter vẫn có thể bị thay đổi sau khi message đã gửi.

Nếu nhiều handler cùng đọc payload, hãy ưu tiên:

- Java record hoặc DTO bất biến.
- Collection không cho sửa hoặc bản sao phòng vệ.
- Không chia sẻ object mutable giữa các thread nếu không có đồng bộ phù hợp.
- Tạo payload mới khi cần biến đổi dữ liệu.

Quy tắc này áp dụng cho cả payload lẫn object được lưu trong custom header.

## 8. Sử dụng accessor trong ChannelInterceptor

Interceptor là một điểm phù hợp để bổ sung metadata kỹ thuật dùng chung cho một luồng gửi, ví dụ thời điểm tiếp nhận hoặc mã truy vết. Tuy nhiên, interceptor cần tránh chứa quy tắc nghiệp vụ của từng loại message.

Ví dụ minh họa phần xử lý trước khi gửi:

~~~java
import java.time.Instant;

import org.springframework.messaging.Message;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.support.ChannelInterceptor;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.messaging.support.MessageHeaderAccessor;

public class ProcessingMetadataInterceptor implements ChannelInterceptor {

    @Override
    public Message<?> preSend(
            Message<?> message,
            MessageChannel channel) {

        MessageHeaderAccessor accessor =
                MessageHeaderAccessor.getMutableAccessor(message);

        accessor.setHeader("app.acceptedAt", Instant.now());

        return MessageBuilder.createMessage(
                message.getPayload(),
                accessor.getMessageHeaders()
        );
    }
}
~~~

Interceptor lấy accessor mutable từ message, thêm timestamp ở cấp ứng dụng rồi trả về message mới. Timestamp này biểu diễn thời điểm interceptor tiếp nhận message theo đồng hồ của tiến trình hiện tại; nó không nhất thiết là thời điểm message được tạo ở hệ thống nguồn.

Đăng ký interceptor với channel tương ứng bằng cơ chế cấu hình của ứng dụng. Không gắn interceptor toàn cục nếu metadata chỉ có ý nghĩa với một luồng cụ thể.

Nếu cần đo thời gian xử lý, hãy cân nhắc dùng tracing hoặc metrics chuyên dụng. Không biến headers thành nơi lưu mọi số liệu vận hành hoặc log tùy ý.

## 9. Bảo mật và độ tin cậy của metadata

Headers là dữ liệu đi cùng message, không phải bằng chứng rằng giá trị trong đó đáng tin cậy.

Ví dụ, client có thể gửi header `app.tenantId` hoặc `userRole` do chính client tự khai báo. Server không nên dùng các giá trị đó để quyết định quyền truy cập nếu chưa xác minh chúng bằng cơ chế xác thực và phân quyền đáng tin cậy.

Các nguyên tắc cần giữ:

- Xác thực người gửi trước khi tin cậy metadata liên quan tới danh tính.
- Không dùng header do client cung cấp để tự cấp quyền hoặc chọn tenant mà không kiểm tra.
- Chỉ truyền tiếp các header cần thiết; loại bỏ token hoặc metadata nhạy cảm trước khi gửi ra hệ thống khác.
- Không log toàn bộ headers một cách mặc định vì chúng có thể chứa dữ liệu cá nhân hoặc bí mật.
- Giới hạn số lượng, kích thước và kiểu dữ liệu của custom headers.
- Dùng correlation ID cho truy vết, nhưng không coi nó là thông tin xác thực.

Khi message đi qua broker hoặc protocol adapter, hãy xác định header nào được ánh xạ, header nào bị đổi tên và header nào không được bảo toàn. Không giả định mọi metadata nội bộ của Spring sẽ tự động xuất hiện nguyên vẹn ở phía nhận.

## 10. Kiểm thử việc tạo và biến đổi headers

Nên kiểm thử ba nhóm hành vi:

1. **Tạo message:** payload và custom headers có giá trị như mong đợi.
2. **Biến đổi message:** accessor mutable giữ metadata cần thiết, thêm hoặc thay đúng header và không làm thay đổi payload ngoài dự kiến.
3. **Bảo vệ trạng thái:** code đọc headers sau khi tạo message; không phụ thuộc vào việc sửa map trực tiếp.

Ví dụ unit test với JUnit 5:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import org.junit.jupiter.api.Test;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.messaging.support.MessageHeaderAccessor;

class MessageHeaderAccessorTest {

    @Test
    void shouldEnrichMessageWithoutChangingOriginalPayload() {
        Message<String> original = MessageBuilder
                .withPayload("order.created")
                .setHeader("app.correlationId", "corr-42")
                .build();

        MessageHeaderAccessor accessor =
                MessageHeaderAccessor.getMutableAccessor(original);
        accessor.setHeader("app.processingAttempt", 2);

        Message<String> enriched = MessageBuilder.createMessage(
                original.getPayload(),
                accessor.getMessageHeaders()
        );

        assertEquals("order.created", enriched.getPayload());
        assertEquals("corr-42",
                enriched.getHeaders().get("app.correlationId"));
        assertEquals(2,
                enriched.getHeaders().get("app.processingAttempt"));
        assertEquals(null,
                original.getHeaders().get("app.processingAttempt"));
    }

    @Test
    void messageHeadersShouldNotBeModifiedDirectly() {
        Message<String> message = MessageBuilder
                .withPayload("order.created")
                .build();

        assertThrows(UnsupportedOperationException.class,
                () -> message.getHeaders().put("app.source", "checkout"));
    }
}
~~~

Các test trên kiểm tra hành vi tạo và biến đổi message. Nếu dự án dùng accessor chuyên biệt hoặc interceptor, hãy bổ sung test cho đúng protocol và channel đó. Unit test không thay thế integration test với broker khi cần xác minh việc chuyển đổi header qua ranh giới mạng.

## 11. Những lỗi thường gặp

- **Gọi put trực tiếp trên MessageHeaders:** headers của message được thiết kế để đọc; cập nhật map trực tiếp thường bị từ chối.
- **Cho rằng MessageHeaderAccessor làm payload bất biến:** accessor chỉ quản lý headers; object payload vẫn có thể mutable.
- **Thay đổi headers sau khi publish:** tạo race condition khi message được chia sẻ giữa nhiều subscriber hoặc thread.
- **Bật leaveMutable không có lý do:** để lộ trạng thái dùng chung cho các thành phần không nên sửa metadata.
- **Ghi đè correlation ID ở tầng sau:** làm đứt liên kết giữa các message của cùng một nghiệp vụ.
- **Sao chép toàn bộ headers:** có thể làm lộ token, metadata phiên hoặc header nội bộ sang hệ thống khác.
- **Nhầm custom header với header xác thực:** giá trị do client gửi lên phải được xác minh trước khi dùng cho quyết định bảo mật.
- **Dùng sai accessor protocol:** accessor STOMP hoặc Simp chỉ phù hợp khi message thuộc đúng ngữ cảnh tích hợp.
- **Không định nghĩa namespace và kiểu dữ liệu:** các module dễ dùng trùng tên hoặc hiểu khác nhau về cùng một header.
- **Dùng header để chứa object mutable lớn:** tăng rủi ro chia sẻ trạng thái, tốn bộ nhớ và khó tuần tự hóa.

## 12. Checklist khi làm việc với MessageHeaderAccessor

Trước khi chuyển message tới channel hoặc handler tiếp theo, hãy tự kiểm tra:

- Đã phân biệt payload với metadata chưa?
- Có thể đọc headers qua MessageHeaders mà không cần sửa trực tiếp không?
- Nếu cần thay đổi, đã dùng MessageHeaderAccessor hoặc MessageBuilder chưa?
- Có giữ lại correlation ID và metadata hợp lệ từ message gốc không?
- Có tránh ghi đè header đã được tầng trước thiết lập không?
- Có loại bỏ header nội bộ hoặc nhạy cảm trước khi truyền qua ranh giới không?
- Có dùng accessor chuyên biệt khi làm việc với STOMP hoặc simple messaging không?
- Headers đã được chốt trước khi publish hoặc xử lý song song chưa?
- Payload và các object trong headers có tránh chia sẻ mutable state không?
- Unit test đã xác minh cả trường hợp enrichment lẫn việc không sửa trực tiếp headers chưa?

Khi hiểu vòng đời của accessor và message, bạn có thể làm giàu metadata một cách có kiểm soát, giữ được tính nhất quán giữa các handler và tránh những lỗi khó tái hiện do mutable state trong hệ thống messaging.