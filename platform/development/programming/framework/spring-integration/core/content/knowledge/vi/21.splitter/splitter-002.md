# Tách collection payload

## 1. Mục tiêu và ngữ cảnh

Trong module **SPRING_INTEGRATION_CORE**, splitter giúp chuyển một thông điệp chứa nhiều phần tử thành nhiều thông điệp để từng phần tử đi qua các endpoint của luồng tích hợp. Bài này tập trung vào trường hợp payload là collection, chẳng hạn danh sách dòng đơn hàng.

Sau bài học, bạn có thể:

- Thiết kế hợp đồng đầu vào chứa danh sách và hợp đồng đầu ra chứa một phần tử.
- Cấu hình splitter bằng Java DSL, kết hợp transformer và MessageChannel.
- Đọc correlationId, sequenceNumber và sequenceSize để theo dõi các phần tử cùng đợt tách.
- Xử lý danh sách rỗng và phân biệt lỗi từng phần tử với lỗi toàn đợt.
- Viết kiểm thử cho payload, header và hành vi dừng khi gặp lỗi.

Ví dụ dùng Java 17+, Spring Integration 6.5.x và JUnit Jupiter. Nếu dự án dùng Spring Boot, để bộ quản lý dependency của dự án chọn các phiên bản Spring tương thích; ví dụ không yêu cầu tự nâng phiên bản module hiện có. Cú pháp cấu hình splitter trong bài là **splitWith(...)** của Java DSL ở nhánh tài liệu 6.5.

## 2. Một collection trong payload vẫn chỉ là một message

Giả sử producer gửi một Message có payload:

~~~text
[
  OrderLine("L1", "BOOK", 2),
  OrderLine("L2", "PEN", 5),
  OrderLine("L3", "BAG", 1)
]
~~~

Trước splitter, đây là **một message chứa ba đối tượng**. Sau splitter, có ba message, mỗi message mang một OrderLine.

~~~mermaid
flowchart LR
    A["Message chứa List gồm L1, L2, L3"] --> S["Splitter"]
    S --> B["Message chứa L1"]
    S --> C["Message chứa L2"]
    S --> D["Message chứa L3"]
    B --> T["Transformer xử lý một dòng"]
    C --> T
    D --> T
    T --> Q["Queue kết quả"]
~~~

Các mũi tên biểu diễn sự phân rã dữ liệu; chúng chưa nói rằng ba phần tử được xử lý đồng thời.

Có thể phân biệt các cách xử lý cùng đầu vào như sau:

| Cấu hình | Ý nghĩa đối với danh sách ba dòng |
| --- | --- |
| Transformer nhận cả danh sách | Biến đổi danh sách thành một payload kết quả |
| Splitter nhận danh sách | Phát một message cho mỗi dòng |
| Router nhận message chứa danh sách | Chọn đích gửi cho message đó theo điều kiện |
| PublishSubscribeChannel nhận message chứa danh sách | Gửi message đó đến các subscriber; payload vẫn là danh sách |

Nếu transformer trả về một List, endpoint transformer thông thường vẫn tạo một message mang List đó. Để bước tiếp theo nhận từng phần tử, cần đưa kết quả qua splitter.

Trong Java DSL, **split()** không tham số dùng DefaultMessageSplitter. Các cấu hình khác có thể cung cấp hàm tách hoặc biểu thức. Phạm vi bài này là collection đã được tạo sẵn trong bộ nhớ. [Tài liệu Java DSL về Splitters](https://docs.spring.io/spring-integration/reference/6.5/dsl/java-splitters.html).

## 3. Xác định hợp đồng dữ liệu trước khi cấu hình

Với ví dụ đơn hàng, hợp đồng nên được mô tả rõ:

~~~text
Đầu vào:
  Message<List<OrderLine>>
  Header orderId: String
  List không chứa null
  Mỗi phần tử đại diện một dòng có lineId riêng

Đầu ra sau splitter:
  N message, mỗi message có payload OrderLine
  Các message cùng đợt có thông tin correlation/sequence

Đầu ra sau transformer:
  N message, mỗi message có payload LineResult
  Điều kiện: mọi phần tử đều xử lý thành công
~~~

Điều kiện cuối có ý nghĩa thực tế. Danh sách có N phần tử không đồng nghĩa hệ thống chắc chắn tạo được N kết quả nghiệp vụ khi endpoint phía sau có thể ném lỗi.

### 3.1. Collection nào phù hợp?

| Dạng collection | Điều cần quyết định trong ứng dụng |
| --- | --- |
| List | Phù hợp khi thứ tự dòng đầu vào có ý nghĩa |
| LinkedHashSet | Giữ thứ tự duyệt theo cách collection này quản lý, nhưng loại phần tử trùng theo quy tắc của Set |
| HashSet | Không dùng thứ tự duyệt làm thứ tự nghiệp vụ |
| List chứa List | Một lần tách lấy ra từng List con |
| List chứa các kiểu khác nhau | Cần chuẩn hóa hoặc kiểm tra kiểu trước endpoint chỉ nhận OrderLine |

Ví dụ payload là danh sách hai danh sách con, mỗi danh sách con có hai dòng. Một splitter ở mức ngoài tạo **hai message chứa List**, không tự động duyệt đệ quy thành bốn dòng. Nếu nghiệp vụ muốn xử lý từng dòng, hãy làm phẳng dữ liệu có chủ đích hoặc thêm một tầng splitter.

### 3.2. Kiểm tra phần tử null và dữ liệu có thể thay đổi

Message payload thông thường phải khác null; vì vậy một phần tử null không phải cách hợp lệ để biểu diễn “không có dòng”. Hãy loại hoặc từ chối phần tử đó trước khi tạo message con. [API GenericMessage](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/messaging/support/GenericMessage.html).

Với đầu vào do ứng dụng kiểm soát, có thể dùng List.copyOf(lines) để chụp cấu trúc danh sách và từ chối phần tử null. Đây là bản sao nông: nếu một phần tử là đối tượng mutable, nội dung đối tượng đó vẫn có thể thay đổi. Vì vậy ví dụ dùng record chỉ chứa String và int để hợp đồng dữ liệu dễ theo dõi.

Không để producer thêm hoặc xóa phần tử trong cùng danh sách khi splitter đang duyệt. Nếu dữ liệu xuất phát từ request JSON, nên kiểm tra schema, kiểu phần tử và giới hạn số dòng ngay ở ranh giới nhận request.

## 4. Cấu hình hoàn chỉnh: tách danh sách rồi xử lý từng dòng

Trong một dự án đã có Spring Integration Core và Spring Context, đặt cấu hình sau vào **CollectionSplitConfig.java**. Java DSL thuộc Spring Integration Core; ví dụ không cần một thư viện DSL tách riêng.

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.PollableChannel;

@Configuration
@EnableIntegration
public class CollectionSplitConfig {

    public record OrderLine(String lineId, String sku, int quantity) {
    }

    public record LineResult(
            String lineId,
            String sku,
            int quantity,
            String status) {
    }

    @Bean
    public MessageChannel orderLinesInput() {
        return new DirectChannel();
    }

    @Bean
    public PollableChannel processedLines() {
        return new QueueChannel();
    }

    @Bean
    public PollableChannel emptyBatches() {
        return new QueueChannel();
    }

    @Bean
    public IntegrationFlow collectionSplitFlow() {
        return IntegrationFlow.from("orderLinesInput")
                .splitWith(s -> s
                        .applySequence(true)
                        .discardChannel("emptyBatches"))
                .<OrderLine, LineResult>transform(
                        CollectionSplitConfig::processLine)
                .channel("processedLines")
                .get();
    }

    private static LineResult processLine(OrderLine line) {
        if (line.quantity() <= 0) {
            throw new IllegalArgumentException(
                    "Quantity must be positive: " + line.lineId());
        }

        return new LineResult(
                line.lineId(),
                line.sku(),
                line.quantity(),
                "ACCEPTED");
    }
}
~~~

Cấu hình có bốn phần:

1. **orderLinesInput** nhận message chứa danh sách.
2. Splitter tạo các message chứa OrderLine.
3. Transformer kiểm tra quantity và chuyển OrderLine thành LineResult.
4. **processedLines** lưu các message kết quả để consumer hoặc kiểm thử lấy ra.

Kênh **emptyBatches** nhận yêu cầu có kết quả tách rỗng. Đây là nhánh phục vụ hợp đồng “không có dòng”, độc lập với nhánh xử lý lỗi nghiệp vụ.

Các bean IntegrationFlow mô tả luồng bằng các builder của Java DSL; Spring đăng ký các channel và endpoint tương ứng trong application context. [Tài liệu Java DSL](https://docs.spring.io/spring-integration/reference/6.5/dsl.html).

### 4.1. Gửi một danh sách vào luồng

Đoạn dưới là phần thân của một phương thức trong ứng dụng hoặc kiểm thử đã có biến **context** trỏ đến application context chứa cấu hình trên:

~~~java
var input = context.getBean(
        "orderLinesInput",
        org.springframework.messaging.MessageChannel.class);

var results = context.getBean(
        "processedLines",
        org.springframework.messaging.PollableChannel.class);

var lines = java.util.List.of(
        new CollectionSplitConfig.OrderLine("L1", "BOOK", 2),
        new CollectionSplitConfig.OrderLine("L2", "PEN", 5),
        new CollectionSplitConfig.OrderLine("L3", "BAG", 1));

var request = org.springframework.messaging.support.MessageBuilder
        .withPayload(lines)
        .setHeader("orderId", "ORD-100")
        .build();

input.send(request);

for (int i = 0; i < lines.size(); i++) {
    var result = results.receive(1_000);
    if (result == null) {
        throw new IllegalStateException("Missing result at index " + i);
    }
    System.out.println(result.getPayload());
}
~~~

Kết quả payload mong đợi:

~~~text
LineResult[lineId=L1, sku=BOOK, quantity=2, status=ACCEPTED]
LineResult[lineId=L2, sku=PEN, quantity=5, status=ACCEPTED]
LineResult[lineId=L3, sku=BAG, quantity=1, status=ACCEPTED]
~~~

QueueChannel trong ví dụ giúp quan sát đầu ra mà không cần dịch vụ bên ngoài. Khi đưa vào hệ thống thực tế, consumer có thể ghi database hoặc gọi một outbound adapter.

## 5. Đọc metadata của các message sau khi tách

Với cấu hình applySequence(true), cần hiểu ba header:

| Header | Ý nghĩa trong luồng một tầng tách của ví dụ |
| --- | --- |
| correlationId | Liên kết các message con với đợt tách; lấy từ id của message đầu vào splitter |
| sequenceNumber | Vị trí phần tử trong lượt duyệt, bắt đầu từ 1 |
| sequenceSize | Số phần tử của collection được tách |

Ví dụ request có id là UUID **P**, payload gồm ba dòng:

~~~text
Message chứa L1: correlationId=P, sequenceNumber=1, sequenceSize=3
Message chứa L2: correlationId=P, sequenceNumber=2, sequenceSize=3
Message chứa L3: correlationId=P, sequenceNumber=3, sequenceSize=3
~~~

Splitter mặc định bật applySequence; ví dụ vẫn khai báo rõ để người đọc thấy chủ đích cấu hình. Khi tự xây message con bằng MessageBuilder, cần để cơ chế sequence của splitter quản lý nhóm tách. [API AbstractMessageSplitter](https://docs.spring.io/spring-integration/docs/6.5.x/api/org/springframework/integration/splitter/AbstractMessageSplitter.html).

Các hằng tương ứng thuộc IntegrationMessageHeaderAccessor:

~~~java
import org.springframework.integration.IntegrationMessageHeaderAccessor;

Object correlationId = message.getHeaders().get(
        IntegrationMessageHeaderAccessor.CORRELATION_ID);

Integer sequenceNumber = message.getHeaders().get(
        IntegrationMessageHeaderAccessor.SEQUENCE_NUMBER,
        Integer.class);

Integer sequenceSize = message.getHeaders().get(
        IntegrationMessageHeaderAccessor.SEQUENCE_SIZE,
        Integer.class);
~~~

Ở đoạn này, **message** là một message nhận từ kênh kết quả. Dùng hằng giúp tránh gõ sai tên header. [API IntegrationMessageHeaderAccessor](https://docs.spring.io/spring-integration/docs/6.5.x/api/org/springframework/integration/IntegrationMessageHeaderAccessor.html).

Trong ví dụ, header nghiệp vụ orderId được chuyển tiếp qua splitter và transformer. Nên giữ **orderId** và **lineId** làm định danh nghiệp vụ:

- orderId cho biết đơn hàng nào đang được xử lý.
- lineId cho biết dòng nào cần cập nhật hoặc xử lý lại.
- correlationId phục vụ nhóm message trong một lượt tách.

Gửi lại cùng dữ liệu trong một message đầu vào mới có thể tạo correlationId khác. Vì vậy khóa chống xử lý trùng nên dựa trên định danh nghiệp vụ ổn định, chẳng hạn orderId kết hợp lineId và phiên bản yêu cầu.

Nếu endpoint phía sau tự tạo một Message mới rồi bỏ các header cần thiết, việc lần theo nhóm có thể bị đứt. Khi cần trả Message thay vì chỉ trả payload, hãy chủ động bảo toàn metadata phù hợp với hợp đồng của luồng.

## 6. Khi collection nằm trong một đối tượng nghiệp vụ

Payload thực tế thường là **OrderBatch**, không phải List trực tiếp. Một kiểu dữ liệu có thể được khai báo trong ứng dụng như sau:

~~~java
import java.util.List;
import java.util.Objects;

public record OrderBatch(
        String orderId,
        List<CollectionSplitConfig.OrderLine> lines) {

    public OrderBatch {
        Objects.requireNonNull(orderId, "orderId");
        lines = List.copyOf(lines);
    }
}
~~~

Với kiểu này, cần chỉ rõ cách lấy danh sách. Đây là một phương án thay thế đầu vào cho ví dụ trước; nếu áp dụng, khai báo thêm channel **batchInput** và dùng endpoint tương đương:

~~~java
@Bean
public MessageChannel batchInput() {
    return new DirectChannel();
}

@Bean
public IntegrationFlow batchInputFlow() {
    return IntegrationFlow.from("batchInput")
            .enrichHeaders(h -> h.headerExpression(
                    "orderId", "payload.orderId()"))
            .split(OrderBatch.class, OrderBatch::lines)
            .channel("orderLinesIndividual")
            .get();
}
~~~

Trong biến thể này, **orderLinesIndividual** là channel do ứng dụng khai báo để nối tới endpoint nhận **một OrderLine**. Không nối nó vào **orderLinesInput** của ví dụ chính, vì kênh đó có hợp đồng nhận **cả danh sách**.

Việc lấy orderId đưa lên header phải diễn ra trước splitter: sau bước tách, payload là OrderLine, không còn là OrderBatch.

Để nối biến thể này với xử lý nghiệp vụ, có thể chuyển transformer sang một IntegrationFlow riêng bắt đầu từ orderLinesIndividual. Phần lấy danh sách và phần xử lý dòng khi đó có hai hợp đồng rõ ràng.

Một POJO splitter cũng có thể nhận đối tượng nghiệp vụ và trả collection. Nếu cần tạo header khác nhau cho từng dòng, hàm tách có thể trả collection các Message thay vì collection payload. [Mô hình lập trình Splitter](https://docs.spring.io/spring-integration/reference/6.5/splitter.html).

## 7. Collection rỗng và các dạng kết quả đặc biệt

### 7.1. Danh sách rỗng không tạo một message con rỗng

Trong cấu hình chính, gửi List.of() sẽ có kết quả:

~~~text
processedLines: không có message mới
emptyBatches: nhận request ban đầu có payload là danh sách rỗng
~~~

discardChannel nhận **message yêu cầu**, không phải một OrderLine giả và cũng không phải ErrorMessage.

Không cấu hình discardChannel thì kết quả tách rỗng không tạo message đầu ra để tiếp tục luồng. Với hợp đồng yêu cầu phản hồi cho mỗi batch, hãy xác định rõ phản hồi cho batch rỗng ngay từ thiết kế.

### 7.2. Rỗng khác null

Trong một splitter tùy biến, trả collection rỗng nghĩa là không có phần tử để phát. Trả null biểu thị không có kết quả để tiếp tục luồng và không đi qua cơ chế discard của collection rỗng. Chính sách requiresReply, nếu được bật riêng, còn có thể biến việc không có kết quả thành lỗi.

Vì vậy nên dùng collection rỗng khi muốn nói “đã tách hợp lệ nhưng không có dòng”; dùng lỗi kiểm tra đầu vào khi muốn nói “request không hợp lệ”. [Quy tắc kết quả rỗng và null của Splitter](https://docs.spring.io/spring-integration/reference/6.5/splitter.html).

### 7.3. Không đổi List sang Iterator chỉ vì thấy tiện

Ví dụ này biết trước số phần tử nhờ collection. Với Iterator hoặc nguồn duyệt khác không xác định được kích thước, sequenceSize thường là 0, biểu thị kích thước chưa biết. Aggregator dựa vào đủ số lượng phần tử không thể suy luận hoàn tất theo cách của ví dụ List.

Nếu dữ liệu quá lớn để giữ cả collection, cần thiết kế riêng chiến lược streaming, hoàn tất nhóm và đóng tài nguyên. Đây là thay đổi hợp đồng, không chỉ là thay kiểu trả về của một phương thức. [Splitter và Iterator](https://docs.spring.io/spring-integration/reference/6.5/splitter.html).

## 8. Tách dữ liệu, luồng thực thi và thứ tự kết quả

Cấu hình chính dùng DirectChannel ở đầu vào và các kết nối trực tiếp giữa splitter với transformer. Do đó, từng dòng được xử lý trên thread gọi send; QueueChannel cuối luồng chỉ lưu kết quả.

Nếu chuyển message con qua ExecutorChannel, handler phía sau có thể chạy trên thread khác. QueueChannel cũng chỉ trở thành ranh giới xử lý bất đồng bộ khi có consumer/poller lấy message để xử lý. [Các triển khai MessageChannel](https://docs.spring.io/spring-integration/reference/6.5/channel/implementations.html).

Ví dụ ba tác vụ có thời gian khác nhau:

~~~text
L1: 300 ms
L2:  20 ms
L3: 100 ms
~~~

Khi xử lý đồng bộ theo List, consumer quan sát kết quả lần lượt L1, L2, L3. Khi xử lý đồng thời, thứ tự hoàn thành có thể là L2, L3, L1.

Trong cả hai cách, sequenceNumber vẫn mô tả vị trí trong lượt tách. Nó không phải thứ hạng hoàn thành. Nếu đầu ra có yêu cầu giữ thứ tự, ứng dụng cần đưa yêu cầu đó vào thiết kế resequencing hoặc sắp xếp khi tổng hợp.

Không suy ra “đã xử lý hết batch” chỉ từ việc send trả true trong một luồng có ranh giới bất đồng bộ. Nếu bên gọi cần một kết quả cuối cùng cho cả đơn hàng, nên dùng cơ chế tổng hợp kết quả rõ ràng.

## 9. Lỗi ở một phần tử và phạm vi xử lý lại

Thử đầu vào:

~~~text
L1: quantity=2
L2: quantity=0
L3: quantity=1
~~~

Với cấu hình chính, không có transaction bao quanh và không có cơ chế tiếp tục sau lỗi:

1. L1 tạo LineResult và được đưa vào processedLines.
2. Transformer ném lỗi ở L2.
3. Lỗi truyền ngược về lời gọi send.
4. L3 chưa được xử lý trong lần gửi đó.

Hành vi lỗi đồng bộ qua DirectChannel là lỗi có thể truyền về caller. Chỉ đặt header errorChannel không tự chuyển mọi lỗi trên call stack đồng bộ thành ErrorMessage. Với tác vụ bất đồng bộ do framework quản lý, cơ chế xử lý lỗi có thể phát ErrorMessage đến error channel phù hợp. [Xử lý lỗi trong Spring Integration](https://docs.spring.io/spring-integration/reference/6.5/error-handling.html).

Từ tình huống này, người thiết kế luồng cần lựa chọn:

| Yêu cầu nghiệp vụ | Cách thiết kế phù hợp |
| --- | --- |
| Từ chối toàn bộ batch khi có dữ liệu sai | Kiểm tra toàn bộ danh sách trước splitter |
| Thử lại tác vụ tạm thời lỗi trên một dòng | Đặt retry vào endpoint xử lý dòng, xác định tác vụ nào có thể lặp an toàn |
| Thu đủ kết quả thành công hoặc thất bại của mọi dòng | Chuyển lỗi dự kiến thành kết quả nghiệp vụ của dòng và tiếp tục xử lý |
| Gửi lại cả batch sau khi một dòng thất bại | Dùng khóa chống trùng ổn định và quy tắc cập nhật phù hợp |

Ví dụ, nếu L1 đã tạo giao dịch ở một hệ thống bên ngoài, gửi lại toàn bộ danh sách có thể tạo lại tác dụng phụ cho L1. Splitter không tự đảm bảo mỗi dòng chỉ thực hiện đúng một lần.

Nếu chọn chính sách “mỗi dòng luôn có kết quả”, hãy tạo một kiểu kết quả chứa lineId, trạng thái và thông tin lỗi phù hợp. Chỉ chuyển những lỗi nghiệp vụ được dự kiến thành dữ liệu; lỗi hạ tầng cần một chính sách retry hoặc phục hồi riêng.

Không dùng sequenceNumber làm khóa nghiệp vụ duy nhất: thêm một dòng mới vào đầu danh sách sẽ thay đổi số thứ tự của các dòng phía sau.

## 10. Kết hợp filter, router và aggregator sau splitter

Sau bước tách, filter hoặc router nhận **một OrderLine** nên điều kiện nghiệp vụ thường đơn giản hơn. Chẳng hạn, router có thể chọn tuyến xử lý theo sku; filter có thể chặn dòng không thuộc phạm vi xử lý.

Nếu sau đó cần một phản hồi cho cả batch, aggregator có thể nhóm message theo correlationId và chờ đủ sequenceSize. Cơ chế nhóm và điều kiện phát kết quả là hai quyết định riêng của aggregator. [Tài liệu Aggregator](https://docs.spring.io/spring-integration/reference/6.5/aggregator.html).

Với ba dòng ban đầu, filter loại L2 sẽ dẫn đến:

~~~text
Trước filter:
  L1: sequenceNumber=1, sequenceSize=3
  L2: sequenceNumber=2, sequenceSize=3
  L3: sequenceNumber=3, sequenceSize=3

Đến aggregator:
  Chỉ còn L1 và L3
~~~

Ứng dụng phải quyết định thế nào là “đủ” khi số dòng đã thay đổi:

- Lọc collection trước khi tách nếu sequence chỉ cần bao gồm các dòng được chấp nhận.
- Tạo kết quả REJECTED cho dòng bị loại nếu báo cáo cần bao phủ toàn bộ đầu vào.
- Thiết kế release strategy và timeout riêng khi nhóm chỉ cần một tập kết quả phù hợp với điều kiện nghiệp vụ.

Nếu router phân tán các dòng sang nhiều nhánh rồi mỗi nhánh có aggregator riêng, không mặc định rằng mỗi nhánh sẽ nhận đủ số lượng ban đầu.

Gateway trả về một kết quả cho một lời gọi cũng cần hợp đồng rõ: muốn phản hồi cả đơn hàng thì tổng hợp trước khi trả lời. Việc có ba message con không tự biến thành một giá trị trả về chứa ba kết quả.

## 11. Kiểm thử hợp đồng bằng JUnit Jupiter

Đặt lớp sau trong source kiểm thử, cùng package với CollectionSplitConfig. Bộ kiểm thử dùng context riêng cho mỗi test để kết quả trong QueueChannel không lẫn giữa các lần chạy.

~~~java
import java.util.List;

import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.integration.IntegrationMessageHeaderAccessor;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.MessagingException;
import org.springframework.messaging.PollableChannel;
import org.springframework.messaging.support.MessageBuilder;

import static org.junit.jupiter.api.Assertions.*;

class CollectionSplitConfigTest {

    private AnnotationConfigApplicationContext context;
    private MessageChannel input;
    private PollableChannel output;
    private PollableChannel emptyBatches;

    @BeforeEach
    void setUp() {
        context = new AnnotationConfigApplicationContext(
                CollectionSplitConfig.class);
        input = context.getBean("orderLinesInput", MessageChannel.class);
        output = context.getBean("processedLines", PollableChannel.class);
        emptyBatches = context.getBean("emptyBatches", PollableChannel.class);
    }

    @AfterEach
    void tearDown() {
        context.close();
    }

    @Test
    void splitsCollectionAndPreservesGroupMetadata() {
        var lines = List.of(
                new CollectionSplitConfig.OrderLine("L1", "BOOK", 2),
                new CollectionSplitConfig.OrderLine("L2", "PEN", 5),
                new CollectionSplitConfig.OrderLine("L3", "BAG", 1));

        Message<List<CollectionSplitConfig.OrderLine>> request =
                MessageBuilder.withPayload(lines)
                        .setHeader("orderId", "ORD-100")
                        .build();

        assertTrue(input.send(request));

        for (int i = 0; i < lines.size(); i++) {
            Message<?> actual = output.receive(1_000);
            assertNotNull(actual);

            var expected = lines.get(i);
            assertEquals(
                    new CollectionSplitConfig.LineResult(
                            expected.lineId(),
                            expected.sku(),
                            expected.quantity(),
                            "ACCEPTED"),
                    actual.getPayload());

            assertEquals("ORD-100", actual.getHeaders().get("orderId"));
            assertEquals(
                    request.getHeaders().getId(),
                    actual.getHeaders().get(
                            IntegrationMessageHeaderAccessor.CORRELATION_ID));
            assertEquals(
                    Integer.valueOf(i + 1),
                    actual.getHeaders().get(
                            IntegrationMessageHeaderAccessor.SEQUENCE_NUMBER,
                            Integer.class));
            assertEquals(
                    Integer.valueOf(lines.size()),
                    actual.getHeaders().get(
                            IntegrationMessageHeaderAccessor.SEQUENCE_SIZE,
                            Integer.class));
        }

        assertNull(output.receive(0));
        assertNull(emptyBatches.receive(0));
    }

    @Test
    void singletonCollectionStillProducesOneItemMessage() {
        var request = MessageBuilder.withPayload(List.of(
                new CollectionSplitConfig.OrderLine("L1", "BOOK", 2)))
                .build();

        assertTrue(input.send(request));

        Message<?> actual = output.receive(1_000);
        assertNotNull(actual);
        assertInstanceOf(
                CollectionSplitConfig.LineResult.class,
                actual.getPayload());
        assertEquals(
                Integer.valueOf(1),
                actual.getHeaders().get(
                        IntegrationMessageHeaderAccessor.SEQUENCE_NUMBER,
                        Integer.class));
        assertEquals(
                Integer.valueOf(1),
                actual.getHeaders().get(
                        IntegrationMessageHeaderAccessor.SEQUENCE_SIZE,
                        Integer.class));
        assertNull(output.receive(0));
    }

    @Test
    void emptyCollectionRoutesOriginalRequestToDiscardChannel() {
        var request = MessageBuilder.withPayload(
                List.<CollectionSplitConfig.OrderLine>of())
                .setHeader("orderId", "ORD-EMPTY")
                .build();

        assertTrue(input.send(request));

        assertNull(output.receive(0));
        Message<?> discarded = emptyBatches.receive(1_000);
        assertNotNull(discarded);
        assertEquals(request, discarded);
        assertNull(emptyBatches.receive(0));
    }

    @Test
    void synchronousFailureLeavesEarlierOutputAndStopsLaterItems() {
        var request = MessageBuilder.withPayload(List.of(
                new CollectionSplitConfig.OrderLine("L1", "BOOK", 2),
                new CollectionSplitConfig.OrderLine("L2", "PEN", 0),
                new CollectionSplitConfig.OrderLine("L3", "BAG", 1)))
                .build();

        assertThrows(MessagingException.class, () -> input.send(request));

        Message<?> first = output.receive(1_000);
        assertNotNull(first);
        assertEquals(
                new CollectionSplitConfig.LineResult(
                        "L1", "BOOK", 2, "ACCEPTED"),
                first.getPayload());

        assertNull(output.receive(0));
        assertNull(emptyBatches.receive(0));
    }
}
~~~

Các test kiểm tra những điều dễ bị bỏ sót khi chỉ in payload ra console:

| Test | Hợp đồng được kiểm tra |
| --- | --- |
| Danh sách ba dòng | Số lượng, dữ liệu, thứ tự đồng bộ, orderId và metadata nhóm |
| Một dòng | Đầu ra là kết quả của phần tử, sequence bắt đầu từ 1 |
| Danh sách rỗng | Không có kết quả dòng, request gốc đi vào discard channel |
| Dòng thứ hai lỗi | Caller nhận lỗi; kết quả trước lỗi vẫn có trong queue và dòng sau chưa được xử lý |

Các lệnh receive có timeout để test không chờ vô hạn. receive(0) kiểm tra ngay xem còn message trong queue hay không. Cách kiểm tra cuối cùng phù hợp với luồng đồng bộ ở đây; với luồng bất đồng bộ, cần cơ chế chờ hoàn tất có giới hạn thời gian trước khi kết luận không còn kết quả.

Đây là mã kiểm thử để người học đưa vào dự án và chạy. Nội dung bài không thay thế kết quả thực thi kiểm thử trên cấu hình dependency thực tế của dự án.

## 12. Tải lớn và khả năng quan sát

Giả sử một request chứa 10.000 dòng và mỗi dòng gọi một dịch vụ bên ngoài. Sau splitter, ứng dụng có thể thực hiện 10.000 tác vụ, dù producer chỉ gửi một message đầu vào.

Do đó cần đặt giới hạn theo hợp đồng sử dụng:

- Giới hạn số dòng cho một request để bảo vệ thời gian đáp ứng và bộ nhớ.
- Khi tăng số thread xử lý, khống chế số tác vụ đang chạy theo sức chịu tải của hệ thống đích.
- Nếu có queue hữu hạn, xác định hành vi khi đầy và timeout gửi; tránh để upstream chờ vô hạn ngoài chủ đích.
- Đặt retry vào phạm vi tác vụ đã xác định, tính đến việc tác dụng phụ có thể đã xảy ra.
- Nếu cần gửi từng nhóm 100 dòng, thiết kế bước chia nhóm trả về collection các nhóm; splitter không tự chọn kích thước batch.

QueueChannel mặc định trong ví dụ phục vụ bài học trong bộ nhớ; nó không phải nơi lưu bền kết quả khi tiến trình dừng. Với yêu cầu phục hồi sau sự cố, cần chọn message store hoặc hạ tầng chuyển phát phù hợp. [QueueChannel và lưu trữ message](https://docs.spring.io/spring-integration/reference/6.5/channel/implementations.html).

Để lần theo một dòng bị lỗi, log nên có orderId, lineId, correlationId và sequenceNumber. Theo dõi thêm số dòng đầu vào, số dòng thành công, số dòng thất bại và số batch rỗng. Khi một đợt thiếu kết quả, các số liệu này giúp phân biệt dữ liệu bị loại có chủ đích, tác vụ lỗi và tác vụ còn chờ.

## 13. Cách áp dụng vào một luồng mới

Khi đưa collection payload vào hệ thống, thực hiện theo thứ tự:

1. Chốt kiểu payload đầu vào và kiểu phần tử sau splitter.
2. Chọn định danh nghiệp vụ của batch và từng phần tử.
3. Quy định thứ tự có ý nghĩa hay không, cách xử lý null và collection rỗng.
4. Bảo toàn thông tin cấp batch cần dùng sau khi payload trở thành phần tử.
5. Chọn channel theo yêu cầu về thread, bộ đệm và thứ tự kết quả.
6. Đặt chính sách lỗi, retry và chống xử lý trùng vào đúng endpoint nghiệp vụ.
7. Nếu cần phản hồi cả batch, thiết kế điều kiện tổng hợp cho cả thành công, thất bại và dòng bị loại.
8. Kiểm thử số message, payload, metadata, nhánh rỗng và lỗi ở giữa danh sách.

Với hợp đồng đã xác định, splitter làm cầu nối từ dữ liệu dạng danh sách sang các endpoint xử lý một phần tử. Nhờ đó transformer, router và filter có thể làm việc với đơn vị nghiệp vụ nhỏ, còn việc tổng hợp và phục hồi được thiết kế theo yêu cầu của toàn luồng.