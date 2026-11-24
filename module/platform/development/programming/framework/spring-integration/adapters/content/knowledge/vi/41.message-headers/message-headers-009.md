# Header filter để loại dữ liệu nhạy cảm

## Mục tiêu

Sau bài học này, bạn có thể:

- Giải thích vai trò của header filter trong luồng message của Spring Integration.
- Phân biệt việc loại header với việc loại message hoặc làm sạch payload.
- Đặt header filter đúng vị trí trước khi message đi qua ranh giới hệ thống.
- Cấu hình danh sách header cần loại bằng Java DSL.
- Kiểm tra header nhạy cảm đã bị loại và metadata cần thiết vẫn được giữ lại.
- Kết hợp header filter với header mapper, logging và quy tắc bảo vệ dữ liệu.

Trong module **SPRING_INTEGRATION_ADAPTERS**, message đi qua các adapter và gateway để trao đổi với file, SFTP, HTTP, JMS, AMQP, Kafka, cơ sở dữ liệu và các hệ thống khác. Spring Integration message mang payload cùng metadata trong header. Header có thể chứa correlation ID, thông tin định tuyến, định danh tenant hoặc dữ liệu xác thực do flow bổ sung. Khi message được chuyển sang hệ thống ngoài, một header nội bộ có thể vô tình trở thành dữ liệu được gửi qua mạng, ghi vào broker hoặc lưu ở hệ thống đích.

**Header filter** giúp loại những header được chỉ định trước khi message đi tiếp. Đây là một bước làm sạch metadata ở cấp message; nó không thay thế việc bảo vệ payload, transport hay secret store.

## 1. Header của message và dữ liệu nhạy cảm

Một Spring Integration message gồm hai phần:

- **Payload**: dữ liệu chính mà flow xử lý, chẳng hạn một DTO, chuỗi JSON, nội dung file hoặc lệnh nghiệp vụ.
- **Headers**: metadata đi kèm message, chẳng hạn ID, timestamp, correlation ID, reply channel, content type và các header do ứng dụng định nghĩa.

Ví dụ một message nội bộ có thể mang các header:

| Header | Mục đích | Có nên gửi ra ngoài? |
|---|---|---|
| correlationId | Theo dõi một giao dịch qua nhiều bước | Chỉ khi hợp đồng tích hợp cần |
| tenantId | Xác định tenant xử lý | Chỉ khi đối tác được phép biết |
| Authorization | Token xác thực cho một lời gọi HTTP | Chỉ qua cơ chế transport đã được thiết kế; không phát tán sang connector khác |
| X-Api-Key | API key của một đối tác | Không gửi sang đích khác hoặc ghi log |
| sessionToken | Token phiên làm việc | Thường phải loại trước khi chuyển tiếp |
| replyChannel | Tham chiếu channel trả lời trong ứng dụng | Không chuyển ra hệ thống ngoài |
| errorChannel | Tham chiếu channel xử lý lỗi nội bộ | Không chuyển ra hệ thống ngoài |

Không phải mọi header đều là bí mật. Correlation ID có thể hữu ích khi đối soát, trong khi replyChannel là chi tiết thực thi nội bộ. Cần phân loại header theo hợp đồng của từng luồng và theo quyền của hệ thống nhận.

### Ví dụ về rủi ro rò rỉ header

Giả sử một flow nhận yêu cầu từ API nội bộ. Một bước xác thực thêm token vào header để gọi dịch vụ kiểm tra quyền. Sau đó cùng message được gửi sang Kafka để xử lý nghiệp vụ. Nếu adapter hoặc header mapper chuyển tiếp header đó, token có thể xuất hiện trong record Kafka hoặc được một consumer khác đọc.

~~~mermaid
flowchart LR
    A[HTTP inbound] --> B[Message có token]
    B --> C[Kiểm tra quyền]
    C --> D[Header filter]
    D --> E[Kafka outbound]
    E --> F[Consumer nghiệp vụ]
    B -. nếu không lọc .-> G[Token bị phát tán]
~~~

Vị trí lọc cần nằm sau bước đã sử dụng header cho mục đích nội bộ và trước điểm mà message có thể rời khỏi ranh giới tin cậy.

## 2. HeaderFilter hoạt động như thế nào?

Trong Spring Integration, **HeaderFilter** là một transformer loại bỏ những header được chỉ định khỏi message. Java DSL cung cấp thao tác `.headerFilter(...)` để khai báo các tên header cần loại.

Khi transformer chạy:

1. Payload được giữ nguyên.
2. Các header nằm trong danh sách loại bỏ bị xóa khỏi message đầu ra.
3. Những header khác được giữ lại theo hành vi của transformer.
4. Message đã được biến đổi tiếp tục đi tới endpoint hoặc channel kế tiếp.

Spring Message và MessageHeaders có tính bất biến. Việc lọc tạo message đầu ra với bộ header đã thay đổi; không nên thiết kế flow dựa trên giả định rằng message đầu vào bị sửa trực tiếp.

Header filter là transformer, không phải **MessageFilter**:

| Thành phần | Hành vi |
|---|---|
| HeaderFilter | Giữ message và payload, loại những header được chỉ định |
| MessageFilter | Quyết định message có được chuyển tiếp hay bị loại dựa trên điều kiện |
| Payload transformer | Biến đổi payload, ví dụ xóa trường nhạy cảm khỏi DTO hoặc JSON |
| Header enricher | Bổ sung hoặc cập nhật header theo quy tắc của flow |

Nếu mục tiêu là bỏ token khỏi message nhưng vẫn xử lý đơn hàng, dùng HeaderFilter. Nếu mục tiêu là chặn toàn bộ đơn hàng không hợp lệ, dùng MessageFilter hoặc cơ chế xác thực phù hợp. Nếu token nằm trong payload, HeaderFilter không thể loại nó.

## 3. Cấu hình bằng Java DSL

Giả sử một flow nhận message từ channel nội bộ và gửi tiếp đến một dịch vụ đối tác. Các header `Authorization`, `X-Api-Key` và `sessionToken` chỉ được dùng trong những bước nội bộ trước đó, không thuộc hợp đồng message gửi sang đối tác.

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.integration.dsl.IntegrationFlow;

@Configuration
public class PartnerFlowConfiguration {

    @Bean
    IntegrationFlow partnerRequestFlow() {
        return IntegrationFlow.from("partnerRequests")
                .headerFilter(
                        "Authorization",
                        "X-Api-Key",
                        "sessionToken")
                .channel("partnerSanitizedRequests")
                .get();
    }

    @Bean
    QueueChannel partnerSanitizedRequests() {
        return new QueueChannel();
    }
}
~~~

Trong ví dụ này, message đi vào channel `partnerRequests`, qua header filter rồi mới tới `partnerSanitizedRequests`. Các endpoint sau channel này chỉ nhận message đã được loại ba header nêu trên.

Khi tích hợp với adapter outbound, đặt bước lọc trong cùng flow và trước adapter:

~~~java
@Bean
IntegrationFlow publishPartnerEvent(PartnerEventHandler partnerEventHandler) {
    return IntegrationFlow.from("partnerEventRequests")
            .headerFilter(
                    "Authorization",
                    "X-Api-Key",
                    "sessionToken",
                    "internalUserContext")
            .handle(partnerEventHandler)
            .get();
}
~~~

`PartnerEventHandler` đại diện cho endpoint gửi dữ liệu ra hệ thống ngoài trong ví dụ. Trong ứng dụng thực tế, endpoint có thể là HTTP outbound gateway, Kafka outbound adapter, AMQP outbound adapter hoặc một service gateway. Danh sách header phải được xác định theo hợp đồng của endpoint đó.

Không nên đặt header filter quá sớm nếu các bước trước đó vẫn cần token để xác thực hoặc cần metadata để định tuyến. Cũng không nên đặt nó sau adapter outbound: khi adapter đã gửi message, dữ liệu có thể đã rời khỏi ứng dụng.

## 4. Chọn header cần loại

Lập danh sách header dựa trên nguồn tạo, mục đích sử dụng và nơi message sẽ đến. Những header thường cần xem xét gồm:

- Credential: `Authorization`, `X-Api-Key`, `password`, `accessToken`, `refreshToken`.
- Session: `sessionToken`, `sessionId`, `Cookie`, `Set-Cookie`.
- Thông tin nội bộ: `replyChannel`, `errorChannel`, `internalUserContext`, tham chiếu tới security context.
- Dữ liệu cá nhân hoặc định danh: email, số điện thoại, mã khách hàng hoặc tenant ID nếu đối tác không có quyền nhận.
- Header debug: thông tin trace nội bộ, dữ liệu chẩn đoán hoặc giá trị chỉ dùng trong môi trường phát triển.

Tên header trong Spring MessageHeaders là key của map. Dùng đúng tên được tạo trong flow; không tự giả định rằng mọi tên đều được chuẩn hóa chữ hoa/chữ thường. Ví dụ, `Authorization` và `authorization` có thể là hai key khác nhau nếu ứng dụng tạo chúng riêng biệt.

Một cách thực tế là tập trung tên header nhạy cảm thành hằng số để các flow cùng tham chiếu:

~~~java
public final class SensitiveHeaders {

    public static final String AUTHORIZATION = "Authorization";
    public static final String API_KEY = "X-Api-Key";
    public static final String SESSION_TOKEN = "sessionToken";
    public static final String INTERNAL_USER_CONTEXT = "internalUserContext";

    private SensitiveHeaders() {
    }
}
~~~

Khi phiên bản Java DSL đang dùng hỗ trợ truyền danh sách tên qua mảng, có thể tập trung cấu hình danh sách để tránh lặp lại literal ở nhiều flow. Nếu dự án có quy ước tên header riêng, hãy ưu tiên hằng số từ module dùng chung.

Không loại một header chỉ vì tên của nó có vẻ nội bộ. Ví dụ, correlation ID có thể cần được giữ lại để theo dõi request từ hệ thống gửi đến hệ thống nhận. Ngược lại, chỉ giữ correlation ID khi đối tác được phép nhận nó và hợp đồng đã định nghĩa cách sử dụng.

## 5. Kết hợp header filter với header mapper

Khi dùng adapter HTTP, JMS, AMQP hoặc Kafka, message header của Spring Integration có thể được ánh xạ thành header hoặc property của giao thức đích. Cơ chế ánh xạ phụ thuộc adapter và header mapper đang cấu hình.

Header filter và header mapper giải quyết hai phần khác nhau:

- Header filter loại metadata khỏi Spring Message trước khi endpoint tiếp theo xử lý.
- Header mapper quyết định header nào được chuyển đổi sang định dạng của giao thức bên ngoài và cách chuyển đổi.

Vì vậy, một flow có thể cần cả hai lớp kiểm soát. Ví dụ, lọc credential nội bộ trước adapter và cấu hình mapper chỉ chuyển những header được hợp đồng cho phép. Với dữ liệu nhạy cảm, danh sách cho phép (allowlist) ở biên giao thức thường dễ kiểm soát hơn việc vô tình chuyển tiếp mọi header mới xuất hiện trong ứng dụng.

~~~mermaid
flowchart TD
    A[Spring Integration Message] --> B[HeaderFilter]
    B --> C[Header mapper]
    C --> D[HTTP / JMS / AMQP / Kafka]
    D --> E[Hệ thống ngoài]
    F[Quy tắc allowlist] -. cấu hình mapper .-> C
~~~

Ví dụ: một flow Kafka có thể giữ `correlationId` để consumer đối soát, nhưng loại `Authorization`, `X-Api-Key` và `internalUserContext`. Kafka header mapper sau đó chỉ ánh xạ các metadata được hợp đồng cho phép. Nếu chỉ dùng header filter mà mapper vẫn chuyển tiếp mọi header khác, một header nhạy cảm mới được bổ sung trong tương lai có thể bị phát tán.

Với HTTP outbound adapter, cần xem cả các header HTTP đặc biệt như Authorization, Cookie và các header do ứng dụng ánh xạ. Với JMS, xem xét message properties và giới hạn kiểu dữ liệu của provider. Với AMQP và Kafka, xem xét header mapper, kiểu dữ liệu được hỗ trợ và quy tắc serialize. Cách ánh xạ cụ thể phụ thuộc phiên bản Spring Integration và adapter đang sử dụng.

## 6. Header filter không làm sạch payload

Header filter chỉ làm việc với header của Spring Message. Nó không tìm kiếm hoặc xóa dữ liệu trong payload.

Ví dụ, message có payload:

~~~json
{
  "orderId": "ORD-10025",
  "customerEmail": "customer@example.com",
  "accessToken": "secret-value"
}
~~~

Nếu `accessToken` nằm trong JSON payload, gọi `.headerFilter("accessToken")` không thay đổi JSON. Cần dùng payload transformer hoặc thiết kế DTO đầu ra chỉ chứa các trường được phép chia sẻ.

Tương tự, HeaderFilter không tự động:

- Che hoặc xóa dữ liệu trong log đã được ghi trước đó.
- Xóa secret trong object lồng bên trong payload.
- Xóa HTTP header đã được gửi đi trước khi transformer chạy.
- Thu hồi token hoặc credential đã bị lộ.
- Mã hóa dữ liệu còn lại trong message.
- Thay thế việc phân quyền hệ thống nhận.

Với payload nhạy cảm, hãy xác định rõ schema trao đổi, tạo DTO dành riêng cho đối tác hoặc dùng transformer có kiểm soát. Tránh serialize trực tiếp object nội bộ chứa credential, thông tin cá nhân hoặc trường debug.

## 7. Thứ tự xử lý và các header cần giữ

Thứ tự các endpoint quyết định header nào còn tồn tại tại từng thời điểm. Một flow có thể cần token để gọi dịch vụ xác thực, correlation ID để nối log và tenant ID để chọn endpoint. Chỉ sau các bước đó, flow mới loại các header không được phép rời khỏi ứng dụng.

Ví dụ thứ tự xử lý:

~~~mermaid
sequenceDiagram
    participant In as Inbound adapter
    participant Auth as Bước xác thực nội bộ
    participant Route as Router
    participant Filter as HeaderFilter
    participant Out as Outbound adapter

    In->>Auth: Message + token + correlationId
    Auth->>Route: Message đã xác thực
    Route->>Filter: Message theo tuyến đích
    Note over Filter: Loại token và context nội bộ
    Filter->>Out: Payload + header được phép
    Out-->>In: Kết quả theo flow
~~~

Một số nguyên tắc khi quyết định thứ tự:

1. Xác định endpoint nào cần header để xác thực, định tuyến, đối soát hoặc xử lý lỗi.
2. Giữ header trong phạm vi nhỏ nhất và trong thời gian ngắn nhất có thể.
3. Lọc trước điểm ghi log, publish hoặc gửi dữ liệu sang hệ thống ngoài nếu các điểm đó không cần giá trị nhạy cảm.
4. Kiểm tra các nhánh rẽ của flow. Mỗi nhánh có thể đi tới một adapter khác và cần chính sách header riêng.
5. Kiểm tra cả reply flow và error flow; message lỗi có thể mang lại header nhạy cảm của request ban đầu.
6. Không phụ thuộc vào việc một adapter mặc định bỏ qua một header. Hãy xác minh cấu hình mapper của adapter thực tế.

Các header điều khiển của Spring Integration như reply channel hoặc error channel thường phục vụ xử lý nội bộ. Không gửi tham chiếu đối tượng channel qua ranh giới hệ thống. Cần kiểm tra header mapper để bảo đảm những header framework không được ánh xạ ra giao thức ngoài. Header filter có thể bổ sung một lớp bảo vệ rõ ràng khi flow biết chính xác tên header cần loại.

## 8. Kiểm thử header filter

Kiểm thử cần xác nhận cả hai điều: header nhạy cảm đã biến mất và header nghiệp vụ cần thiết vẫn còn.

Một ví dụ kiểm thử theo flow:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

@SpringJUnitConfig(PartnerFlowConfiguration.class)
class PartnerHeaderFilterTests {

    @Autowired
    private MessageChannel partnerRequests;

    @Autowired
    private QueueChannel partnerSanitizedRequests;

    @Test
    void removesSensitiveHeadersAndKeepsCorrelationId() {
        Message<String> request = MessageBuilder
                .withPayload("{\"orderId\":\"ORD-10025\"}")
                .setHeader("Authorization", "Bearer test-token")
                .setHeader("X-Api-Key", "test-api-key")
                .setHeader("sessionToken", "test-session")
                .setHeader("correlationId", "corr-10025")
                .build();

        partnerRequests.send(request);

        Message<?> sanitized = partnerSanitizedRequests.receive(1000);

        assertThat(sanitized).isNotNull();
        assertThat(sanitized.getHeaders())
                .doesNotContainKeys(
                        "Authorization",
                        "X-Api-Key",
                        "sessionToken");
        assertThat(sanitized.getHeaders().get("correlationId"))
                .isEqualTo("corr-10025");
        assertThat(sanitized.getPayload())
                .isEqualTo(request.getPayload());
    }
}
~~~

Ví dụ giả định cấu hình flow đưa đầu ra vào một `QueueChannel` có tên `partnerSanitizedRequests`. Nếu dự án dùng channel bean hoặc tên bean khác, điều chỉnh cấu hình test cho khớp. Test gửi một message có ba header nhạy cảm và correlation ID; message nhận được phải không còn ba header nhạy cảm, nhưng vẫn giữ payload và correlation ID.

Bổ sung các ca kiểm thử phù hợp với hệ thống:

- Header có cách viết hoa/thường khác nhau theo đúng key mà ứng dụng tạo.
- Header nhạy cảm được bổ sung ở một bước trung gian.
- Nhánh retry và error flow không phát tán token.
- Header mapper của adapter chỉ gửi metadata được cho phép.
- Payload chứa trường nhạy cảm được xử lý bởi payload transformer riêng.
- Log và wiretap không ghi lại giá trị bí mật.

Không nên kiểm thử bằng cách chỉ xác nhận flow chạy hết. Hãy kiểm tra trực tiếp tập header ở đầu ra của bước lọc và, khi có thể, kiểm tra message sau khi adapter ánh xạ sang giao thức đích.

## 9. Vận hành và xử lý sự cố

| Hiện tượng | Nguyên nhân cần kiểm tra |
|---|---|
| Header vẫn xuất hiện ở hệ thống nhận | Header filter đặt sau outbound adapter, sai tên key hoặc nhánh flow đi vòng qua bước lọc |
| Header biến mất nhưng request không chạy | Đã loại header mà endpoint nội bộ phía sau vẫn cần để xác thực hoặc định tuyến |
| Token vẫn có trong log | Log hoặc wiretap chạy trước header filter, hoặc logger ghi cả payload |
| Header lạ xuất hiện trên Kafka/AMQP | Header mapper đang ánh xạ thêm metadata mà flow không dự kiến |
| Correlation ID không còn ở hệ thống nhận | Đã lọc nhầm header phục vụ đối soát hoặc mapper không chuyển tiếp header này |
| Secret vẫn tồn tại sau khi lọc | Giá trị nằm trong payload, object lồng nhau hoặc transport header đã được tạo ở bước khác |

Khi điều tra, theo dõi message tại từng channel bằng dữ liệu thử không nhạy cảm. Ghi tên header cần thiết cho chẩn đoán nhưng không ghi giá trị bí mật. Kiểm tra thứ tự transformer, các nhánh flow và cấu hình header mapper của adapter. Nếu phát hiện token đã bị gửi ra ngoài, cần xử lý credential theo quy trình ứng phó của hệ thống, bao gồm thu hồi hoặc xoay vòng token khi cần.

Header filter cũng cần được xem xét khi hợp đồng tích hợp thay đổi. Một header mới có thể chứa thông tin nhạy cảm mà danh sách loại bỏ hiện tại chưa biết. Kết hợp kiểm tra schema, rà soát mapper và kiểm thử biên giao thức trong quy trình thay đổi adapter.

## 10. Checklist trước khi chuyển message qua ranh giới hệ thống

- [ ] Đã xác định header nào chứa credential, session, dữ liệu cá nhân hoặc metadata nội bộ.
- [ ] Header filter chạy sau bước sử dụng header nội bộ và trước adapter outbound.
- [ ] Danh sách tên header khớp chính xác key được tạo trong flow.
- [ ] Correlation ID và metadata nghiệp vụ cần thiết được giữ lại theo hợp đồng.
- [ ] Header mapper của HTTP, JMS, AMQP hoặc Kafka chỉ chuyển tiếp dữ liệu được phép.
- [ ] Reply channel, error channel và các tham chiếu nội bộ không bị phát tán ra ngoài.
- [ ] Payload đã được kiểm tra riêng; không giả định HeaderFilter xóa trường nhạy cảm trong payload.
- [ ] Logging và wiretap không ghi giá trị token hoặc dữ liệu nhạy cảm.
- [ ] Có test xác nhận header nhạy cảm bị loại và header cần thiết được giữ lại.
- [ ] Các nhánh retry, reply và error flow cũng tuân thủ chính sách lọc.

Header filter là một bước nhỏ nhưng có vai trò rõ ràng trong bảo vệ message khi tích hợp nhiều hệ thống. Đặt nó đúng vị trí, xác định chính xác header cần loại và kết hợp với quy tắc ánh xạ ở adapter giúp kiểm soát metadata được phép đi qua ranh giới hệ thống.

