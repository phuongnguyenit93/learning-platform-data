# Kiểm thử tương thích schema

Trong Kafka, producer và consumer thường được triển khai ở những thời điểm khác nhau. Một producer mới có thể gửi event trong khi một số instance consumer vẫn đang chạy phiên bản cũ. Ngoài ra, event đã ghi vào topic có thể được đọc lại sau nhiều giờ hoặc nhiều ngày khi consumer khởi động lại, đổi consumer group hay xử lý lại dữ liệu.

Vì vậy, thay đổi một DTO hoặc cấu trúc JSON không chỉ là thay đổi nội bộ của ứng dụng. Đó là thay đổi hợp đồng dữ liệu giữa các dịch vụ. Kiểm thử tương thích schema giúp xác định phiên bản producer và consumer nào có thể trao đổi dữ liệu an toàn trước khi thay đổi được triển khai.

Trong Spring Kafka, `KafkaTemplate` chuyển object thành byte thông qua serializer; `@KafkaListener` nhận byte và chuyển thành object thông qua deserializer. Kafka broker lưu và chuyển tiếp record, nhưng bản thân broker không hiểu ý nghĩa các field trong payload. Tính tương thích phải được bảo đảm bởi serializer, deserializer, schema hoặc Schema Registry nếu hệ thống sử dụng, và các bài kiểm thử của ứng dụng.

## 1. Schema là hợp đồng của event

Giả sử một dịch vụ phát event `OrderCreated` với payload:

```json
{
  "orderId": "DH-001",
  "amount": 125000
}
```

Producer có thể biểu diễn event này bằng một class Java:

```java
import java.math.BigDecimal;

public record OrderCreated(
    String orderId,
    BigDecimal amount
) {}
```

Consumer cũng có thể có DTO riêng để đọc cùng event. Hai dịch vụ không nhất thiết dùng chung một thư viện Java, nhưng phải thống nhất tên field, kiểu dữ liệu, ý nghĩa và quy tắc xử lý khi field vắng mặt hoặc có giá trị `null`.

Một schema hữu ích cần trả lời được các câu hỏi sau:

- Field nào bắt buộc phải có? Field nào được phép vắng mặt?
- Nếu một field mới chưa xuất hiện trong event cũ, consumer mới lấy giá trị mặc định ở đâu?
- Consumer cũ xử lý thế nào khi gặp field mới?
- Một field có thể đổi kiểu, đổi tên hoặc đổi ý nghĩa hay không?
- Consumer có thể đọc lại event được tạo bởi những phiên bản schema nào?

Điểm cuối đặc biệt quan trọng với Kafka. Một lần thay đổi producer không chỉ ảnh hưởng đến record được gửi từ thời điểm triển khai. Consumer mới còn có thể đọc các record cũ đang nằm trong thời gian lưu giữ của topic.

## 2. Ba hướng tương thích cần phân biệt

Khi nói về tương thích schema, cần xác định **schema ghi** và **schema đọc**. Schema ghi mô tả payload do producer tạo ra; schema đọc mô tả cấu trúc mà consumer dùng để giải mã payload đó.

| Loại tương thích | Câu hỏi cần kiểm tra | Tình huống triển khai |
|---|---|---|
| Backward compatibility | Consumer dùng schema mới có đọc được dữ liệu được ghi bằng schema cũ không? | Triển khai consumer mới trước, producer cũ vẫn đang gửi event. |
| Forward compatibility | Consumer dùng schema cũ có đọc được dữ liệu được ghi bằng schema mới không? | Producer mới bắt đầu gửi event trong khi consumer cũ vẫn còn chạy. |
| Full compatibility | Cả consumer mới đọc dữ liệu cũ và consumer cũ đọc dữ liệu mới có hoạt động không? | Producer và consumer được nâng cấp theo các thời điểm khác nhau. |

Ví dụ, phiên bản 1 có hai field `orderId` và `amount`; phiên bản 2 thêm `currency`. Nếu consumer mới tự đặt giá trị mặc định khi `currency` chưa tồn tại, nó có thể đọc event cũ. Nếu consumer cũ bỏ qua field không nhận biết, nó có thể đọc event mới. Khi cả hai điều kiện đều được kiểm chứng, thay đổi có thể đáp ứng full compatibility đối với hai phiên bản đó.

Các hệ thống dùng Schema Registry thường cấu hình mức tương thích như `BACKWARD`, `FORWARD` hoặc `FULL`. Một số registry còn có chế độ transitive, ví dụ `BACKWARD_TRANSITIVE`, để so schema mới với toàn bộ các phiên bản trước thay vì chỉ so với phiên bản gần nhất. Cần đọc đúng quy ước của registry đang dùng vì tên chế độ và phạm vi kiểm tra phụ thuộc sản phẩm, cấu hình.

## 3. Đánh giá tác động của thay đổi schema

Không nên kết luận một thay đổi an toàn chỉ vì code vẫn biên dịch hoặc JSON vẫn hợp lệ. Hãy xét riêng khả năng đọc của consumer cũ và consumer mới.

| Thay đổi | Rủi ro tương thích | Điều cần kiểm thử |
|---|---|---|
| Thêm field tùy chọn có giá trị mặc định | Thường an toàn hơn vì consumer mới có cách xử lý event cũ; consumer cũ vẫn có thể lỗi nếu từ chối field lạ. | Consumer mới đọc payload cũ; consumer cũ đọc payload mới. |
| Thêm field bắt buộc, không có mặc định | Consumer mới có thể không đọc được event cũ vì field chưa tồn tại. | Giải mã event cũ bằng consumer mới và kiểm tra validation. |
| Xóa field | Consumer cũ có thể không đọc được event mới nếu vẫn yêu cầu field đó. Consumer mới cũng cần xử lý field còn xuất hiện trong dữ liệu cũ. | Đọc payload của cả hai phiên bản theo cả hai hướng. |
| Đổi tên field | Thường tương đương xóa field cũ và thêm field mới; dữ liệu cũ có thể không được ánh xạ sang tên mới. | Kiểm tra alias, mapping hoặc bước chuyển đổi dữ liệu. |
| Đổi kiểu dữ liệu | Có thể làm serializer hoặc deserializer thất bại, hoặc chuyển đổi sai giá trị. | Kiểm tra giá trị biên, giá trị lớn và dữ liệu lịch sử. |
| Thêm giá trị vào enum | Consumer cũ có thể không biết cách xử lý giá trị mới. | Gửi giá trị enum mới đến từng phiên bản consumer đang được hỗ trợ. |
| Đổi ý nghĩa field nhưng giữ nguyên kiểu | Kiểm tra schema cấu trúc có thể vẫn thành công dù nghiệp vụ đọc sai dữ liệu. | Kiểm tra quy tắc nghiệp vụ và ý nghĩa của giá trị. |

Các kết luận trong bảng phụ thuộc định dạng và cấu hình. Chẳng hạn, JSON không tự quy định consumer phải bỏ qua field lạ; Jackson có thể được cấu hình để từ chối field không biết. Với Avro, việc thêm field thường cần giá trị mặc định để reader schema mới đọc được dữ liệu cũ. Với Protobuf, số field đã dùng không được tái sử dụng sau khi xóa.

Một nguyên tắc thực tế là thiết kế consumer có khả năng chịu được thay đổi có kiểm soát: xử lý rõ field vắng mặt, field `null`, field lạ và enum chưa biết. Tuy nhiên, chỉ bỏ qua field lạ không thay thế được kiểm tra nghiệp vụ. Nếu field mới làm thay đổi cách tính tiền hoặc trạng thái đơn hàng, consumer cũ có thể giải mã thành công nhưng vẫn xử lý sai.

## 4. Xây dựng ma trận kiểm thử producer và consumer

Trước khi viết test, liệt kê các phiên bản schema còn có thể xuất hiện trong dữ liệu và các phiên bản consumer có thể chạy đồng thời. Một ma trận cơ bản gồm:

| Dữ liệu được tạo bởi | Consumer được kiểm thử | Mục tiêu |
|---|---|---|
| Producer cũ | Consumer mới | Kiểm tra backward compatibility. |
| Producer mới | Consumer cũ | Kiểm tra forward compatibility. |
| Producer mới | Consumer mới | Kiểm tra hợp đồng của phiên bản hiện tại. |
| Payload lịch sử đã lưu | Consumer mới | Kiểm tra khả năng replay dữ liệu trong Kafka. |

Nếu topic đã tồn tại qua nhiều lần nâng cấp, hãy giữ payload đại diện của các phiên bản cũ làm fixture trong `src/test/resources`. Fixture phải là byte hoặc nội dung event thực tế đã được phát hành, không nên tạo lại tất cả bằng DTO mới vì cách đó có thể vô tình làm mất khác biệt của schema cũ.

Ma trận cần phản ánh cách triển khai thật. Khi rolling deployment, các instance consumer cũ và mới có thể cùng tồn tại trong một consumer group. Mỗi partition được gán cho một instance tại một thời điểm, nên event mới có thể đến instance cũ trong lúc quá trình nâng cấp chưa hoàn tất. Khi replay, consumer mới có thể gặp event từ nhiều phiên bản producer. Hãy kiểm thử các trường hợp này thay vì chỉ kiểm tra cặp DTO mới nhất.

## 5. Ví dụ kiểm thử tương thích JSON bằng Jackson

Ví dụ sau mô phỏng hai phiên bản event. Consumer phiên bản 1 bỏ qua field chưa biết. Consumer phiên bản 2 cung cấp giá trị mặc định cho `currency` khi đọc payload cũ.

```java
import com.fasterxml.jackson.databind.DeserializationFeature;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.json.JsonMapper;
import org.junit.jupiter.api.Test;

import java.math.BigDecimal;

import static org.junit.jupiter.api.Assertions.assertEquals;

record OrderCreatedV1(String orderId, BigDecimal amount) {}

record OrderCreatedV2(
    String orderId,
    BigDecimal amount,
    String currency
) {
    OrderCreatedV2 {
        if (currency == null || currency.isBlank()) {
            currency = "VND";
        }
    }
}

class OrderSchemaCompatibilityTest {

    // Cấu hình minh họa: consumer chấp nhận field JSON chưa biết.
    // Trong ứng dụng thật, test phải dùng cấu hình ObjectMapper giống production.
    private final ObjectMapper mapper = JsonMapper.builder()
        .disable(DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES)
        .build();

    @Test
    void oldConsumerCanReadPayloadFromNewProducer() throws Exception {
        OrderCreatedV2 event = new OrderCreatedV2(
            "DH-001",
            new BigDecimal("125000"),
            "VND"
        );

        byte[] payload = mapper.writeValueAsBytes(event);
        OrderCreatedV1 decoded = mapper.readValue(payload, OrderCreatedV1.class);

        assertEquals("DH-001", decoded.orderId());
        assertEquals(new BigDecimal("125000"), decoded.amount());
    }

    @Test
    void newConsumerCanReadPayloadFromOldProducer() throws Exception {
        String oldPayload = """
            {
              "orderId": "DH-001",
              "amount": 125000
            }
            """;

        OrderCreatedV2 decoded = mapper.readValue(oldPayload, OrderCreatedV2.class);

        assertEquals("DH-001", decoded.orderId());
        assertEquals("VND", decoded.currency());
    }
}
```

Test thứ nhất chứng minh consumer cũ đọc được payload có thêm field `currency` khi cấu hình Jackson cho phép bỏ qua field lạ. Nếu ứng dụng production bật `FAIL_ON_UNKNOWN_PROPERTIES`, test phải phản ánh cấu hình đó; khi ấy test sẽ phát hiện thay đổi chưa tương thích thay vì âm thầm giả định rằng field lạ được bỏ qua.

Test thứ hai kiểm tra consumer mới đọc payload không có `currency`. Compact constructor của record đặt giá trị mặc định khi Jackson truyền `null` cho field bị thiếu. Nếu nghiệp vụ phân biệt rõ field vắng mặt và field có giá trị `null`, cần thêm test cho cả hai payload và xử lý chúng theo quy tắc đã công bố.

Đây là kiểm thử hợp đồng payload ở mức Jackson. Nó chưa chứng minh toàn bộ cấu hình Spring Kafka hoạt động đúng. Trong ứng dụng thực, nên dùng `ObjectMapper` bean và cấu hình serializer/deserializer đang chạy trong production. Nếu `JsonSerializer` hoặc `JsonDeserializer` sử dụng type header, trusted packages hay type mapping, cần kiểm tra cả các thiết lập đó.

## 6. Kiểm thử với định dạng và công cụ schema thực tế

Chiến lược test phải khớp với định dạng event mà ứng dụng đang gửi.

| Định dạng | Các điểm cần kiểm tra |
|---|---|
| JSON | Field bắt buộc, field tùy chọn, giá trị `null`, field lạ, kiểu dữ liệu và cấu hình Jackson khi deserialize. Nếu có JSON Schema, kiểm tra payload với schema của từng phiên bản. |
| Avro | Writer schema và reader schema, default của field mới, union có `null`, alias khi đổi tên field và khả năng đọc các phiên bản schema cũ. |
| Protobuf | Field number, wire type, giá trị mặc định, cách xử lý enum mới; không tái sử dụng field number hoặc tên đã xóa. |

Nếu hệ thống dùng Schema Registry, thêm bước kiểm tra compatibility vào CI trước khi đăng ký hoặc phát hành schema mới. Bước này phát hiện sớm các thay đổi cấu trúc bị registry từ chối. Cần chọn đúng chế độ tương thích theo chiến lược rollout và cân nhắc chế độ transitive khi consumer mới phải đọc được toàn bộ dữ liệu còn lưu từ các phiên bản trước.

Kiểm tra của registry vẫn chưa đủ. Nó không thể xác nhận mọi quy tắc nghiệp vụ, cấu hình Jackson riêng của từng consumer hay việc code có xử lý đúng giá trị mới hay không. Vì vậy, nên kết hợp ba lớp:

1. **Kiểm tra schema:** xác thực schema mới và quy tắc tương thích của registry.
2. **Kiểm thử hợp đồng:** dùng payload fixture của producer cũ và mới để kiểm tra từng consumer.
3. **Kiểm thử tích hợp Spring Kafka:** dùng broker nhúng hoặc môi trường test để gửi record qua `KafkaTemplate`, sau đó xác nhận `@KafkaListener` nhận và xử lý được payload bằng serializer/deserializer thật.

Kiểm thử tích hợp nên xác minh cả key, value và header nếu ứng dụng dựa vào chúng. Với consumer bất đồng bộ, hãy chờ điều kiện nhận event bằng cơ chế đồng bộ của test thay vì dùng thời gian chờ cố định quá ngắn. Nếu test có retry hoặc dead-letter topic, xác minh event không tương thích được chuyển đến đúng luồng lỗi theo cấu hình ứng dụng.

## 7. Đưa kiểm thử vào quy trình thay đổi event

Một quy trình phù hợp cho mỗi thay đổi schema có thể thực hiện theo thứ tự sau:

1. **Mô tả thay đổi:** ghi rõ field được thêm, xóa, đổi tên, đổi kiểu hoặc đổi ý nghĩa; xác định giá trị mặc định và quy tắc xử lý `null`.
2. **Chọn hướng tương thích:** xác định cần backward, forward hay full compatibility dựa trên thứ tự nâng cấp producer và consumer.
3. **Kiểm tra schema:** chạy validator hoặc kiểm tra compatibility với Schema Registry nếu có.
4. **Chạy ma trận payload:** đọc fixture cũ bằng consumer mới, đọc payload mới bằng consumer cũ và kiểm tra payload của phiên bản hiện tại.
5. **Chạy kiểm thử tích hợp:** xác nhận cấu hình Kafka thực tế, bao gồm serializer, deserializer, type header và listener.
6. **Xác định cách rollout:** với thay đổi backward-compatible, thường có thể nâng cấp consumer trước rồi mới nâng cấp producer. Với thay đổi forward-compatible, producer mới có thể được triển khai trước nếu consumer cũ đã được kiểm chứng đọc được payload mới. Với full compatibility, hai phía có nhiều linh hoạt hơn nhưng vẫn cần giữ khả năng đọc dữ liệu lịch sử.

Không xóa fixture cũ chỉ vì producer hiện tại đã ngừng phát schema đó. Nếu record vẫn có thể tồn tại trong thời gian retention, được lưu trữ ngoài Kafka hoặc được phát lại từ hệ thống khác, consumer mới vẫn cần xử lý chúng hoặc có một quy trình chuyển đổi dữ liệu rõ ràng.

## 8. Những lỗi thường gặp khi kiểm thử

**Chỉ kiểm tra producer serialize thành công.** Việc tạo được JSON hoặc Avro bytes không chứng minh consumer cũ có thể đọc payload đó. Hãy kiểm tra cả chiều đọc của từng phiên bản consumer.

**Dùng DTO mới để tạo fixture cho dữ liệu cũ.** Fixture như vậy không còn đại diện cho payload lịch sử. Hãy lưu mẫu payload thực tế theo phiên bản hoặc lấy từ bộ dữ liệu kiểm thử đã được kiểm soát.

**Dùng ObjectMapper riêng trong test.** Nếu test tự cấu hình bỏ qua field lạ trong khi production lại từ chối, kết quả test không phản ánh hành vi thật. Hãy dùng bean cấu hình thực tế trong kiểm thử tích hợp hoặc đồng bộ cấu hình test với production.

**Chỉ kiểm tra field có tồn tại.** Cần kiểm tra thêm `null`, field vắng mặt, chuỗi rỗng, giá trị enum mới, số nằm ngoài phạm vi dự kiến và thay đổi ý nghĩa nghiệp vụ.

**Chỉ kiểm tra phiên bản liền trước.** Consumer mới có thể phải đọc lại event được tạo từ nhiều lần phát hành trước đó. Dùng fixture của các phiên bản còn nằm trong thời gian lưu giữ hoặc còn được hỗ trợ.

**Coi registry chấp nhận là bảo đảm tuyệt đối.** Registry kiểm tra các quy tắc schema mà nó hỗ trợ. Test ứng dụng vẫn phải xác minh serializer/deserializer, mapping DTO và hành vi nghiệp vụ.

## 9. Checklist trước khi phát hành schema mới

- [ ] Đã xác định schema ghi và schema đọc của các phiên bản liên quan.
- [ ] Đã chọn rõ backward, forward hay full compatibility.
- [ ] Field mới có quy tắc xử lý khi vắng mặt và khi nhận `null`.
- [ ] Consumer cũ và mới đã được kiểm thử với payload của nhau.
- [ ] Payload lịch sử còn có thể được replay đã có fixture kiểm thử.
- [ ] Cấu hình serializer/deserializer trong test khớp với Spring Kafka production.
- [ ] Schema Registry hoặc validator đã chấp nhận schema mới nếu hệ thống sử dụng.
- [ ] Các thay đổi về ý nghĩa nghiệp vụ đã được kiểm tra ngoài phép so sánh cấu trúc schema.
- [ ] Thứ tự rollout và khả năng rollback đã được xác định.

Kiểm thử tương thích schema là một phần của hợp đồng event trong hệ thống Kafka. Khi kiểm tra cả dữ liệu mới, dữ liệu cũ, consumer đang chạy và luồng replay, nhóm có thể thay đổi event theo từng bước mà vẫn giữ cho các dịch vụ Spring Kafka trao đổi dữ liệu đúng trong suốt quá trình nâng cấp.
