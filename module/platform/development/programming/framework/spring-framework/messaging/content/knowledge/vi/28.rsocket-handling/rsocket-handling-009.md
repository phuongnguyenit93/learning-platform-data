# Thiết lập RSocketStrategies thống nhất giữa requester và responder

## Mục tiêu

RSocket cho phép ứng dụng trao đổi object Java thông qua payload nhị phân. Spring dùng `Encoder` để chuyển object thành payload khi gửi và `Decoder` để khôi phục object khi nhận. `RSocketStrategies` tập hợp các thành phần xử lý đó cùng những cấu hình messaging liên quan, giúp requester và responder tuân theo cùng một hợp đồng dữ liệu.

Bài này trình bày cách thống nhất codec, MIME type, route matcher và metadata. Ví dụ chính dùng Java, Spring Framework 7 và Jackson 3; phần sau nêu cách áp dụng trong Spring Boot và khác biệt với Spring Framework 6.

## 1. RSocketStrategies chịu trách nhiệm những gì?

`RSocketStrategies` là tập hợp cấu hình có thể tái sử dụng cho RSocket. Các thành phần chính gồm:

- **Encoders:** chuyển object Java thành dữ liệu nhị phân để gửi qua kết nối.
- **Decoders:** chuyển dữ liệu nhị phân nhận được thành object Java.
- **MetadataExtractor:** giải mã metadata thành các giá trị mà handler có thể truy cập, chẳng hạn header tùy chỉnh.
- **RouteMatcher:** so khớp route nhận được với các mẫu trong `@MessageMapping`.
- **ReactiveAdapterRegistry:** giúp Spring làm việc với các kiểu reactive được hỗ trợ.

Encoder ở phía gửi phải tương thích với decoder ở phía nhận. Ví dụ, requester gửi `CustomerQuery` thì responder phải có decoder hiểu định dạng và cấu trúc của payload đó. Khi responder trả `CustomerView`, responder cần encoder tương ứng và requester cần decoder tương ứng.

Nếu requester và responder chạy trong cùng một ứng dụng, có thể khai báo một bean `RSocketStrategies` rồi truyền cùng instance cho hai phía. Nếu chạy trong hai tiến trình khác nhau, mỗi tiến trình tạo cấu hình riêng nhưng phải thống nhất hợp đồng: định dạng payload, MIME type, schema DTO, quy tắc tên field và metadata.

### Codec mặc định và codec mở rộng

Các codec cơ bản từ `spring-core` hỗ trợ `String`, `byte[]` và `ByteBuffer`. Muốn trao đổi DTO JSON, CBOR hoặc Protobuf, ứng dụng cần có module và encoder/decoder tương ứng; các codec web phổ biến nằm trong `spring-web`.

Ví dụ bên dưới dùng `JacksonJsonEncoder` và `JacksonJsonDecoder` của Spring Framework 7, tức nhánh tích hợp Jackson 3. Trong ứng dụng Spring Boot, `spring-boot-starter-rsocket` cung cấp các dependency để Boot tự cấu hình codec CBOR và JSON. Nếu tự cấu hình Spring Framework, cần có `spring-web` cùng module Jackson tương thích trên classpath và quản lý phiên bản đồng bộ.

Không nên mặc định rằng mọi object Java đều tự truyền được. Nếu không có encoder phù hợp, quá trình encode request hoặc response sẽ thất bại. Nếu bên nhận không có decoder tương ứng, bên đó không thể khôi phục payload thành kiểu mong đợi.

## 2. Phân biệt Strategies và MIME type

Hai khái niệm này liên quan nhưng có vai trò khác nhau:

- `RSocketStrategies` xác định **có những encoder, decoder và cơ chế xử lý nào**.
- `dataMimeType` xác định **định dạng data payload trên kết nối**. MIME type này được khai báo trong frame `SETUP` và áp dụng cho data payload của các request trên kết nối.
- `metadataMimeType` xác định định dạng metadata của kết nối. Mặc định Spring dùng composite metadata để có thể mang nhiều mục metadata với MIME type riêng.

`RSocketRequester.Builder` cung cấp `dataMimeType(MimeType)` và `metadataMimeType(MimeType)` để cấu hình MIME type trong frame `SETUP`. Nếu không chỉ định data MIME type, Spring suy ra giá trị mặc định từ decoder đầu tiên được cấu hình. Khi ứng dụng có nhiều codec, chỉ định MIME type tường minh giúp hợp đồng dễ đọc và dễ kiểm tra hơn.

Server đọc MIME type từ frame `SETUP`. Nếu client gửi `application/json` thì server phải có decoder tương thích với MIME type đó. Có encoder/decoder đúng class nhưng MIME type không tương thích vẫn có thể gây lỗi encode/decode.

## 3. Tạo cấu hình dùng chung cho requester và responder

Ví dụ sau đăng ký codec JSON với Jackson 3 và dùng `PathPatternRouteMatcher` để so khớp route theo mẫu.

Tạo `RSocketConfiguration.java`:

~~~java
package example.rsocket;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.codec.json.JacksonJsonDecoder;
import org.springframework.http.codec.json.JacksonJsonEncoder;
import org.springframework.messaging.rsocket.RSocketMessageHandler;
import org.springframework.messaging.rsocket.RSocketStrategies;
import org.springframework.web.util.pattern.PathPatternRouteMatcher;

@Configuration
public class RSocketConfiguration {

    @Bean
    RSocketStrategies rSocketStrategies() {
        return RSocketStrategies.builder()
                .encoders(encoders -> encoders.add(new JacksonJsonEncoder()))
                .decoders(decoders -> decoders.add(new JacksonJsonDecoder()))
                .routeMatcher(new PathPatternRouteMatcher())
                .build();
    }

    @Bean
    RSocketMessageHandler rSocketMessageHandler(
            RSocketStrategies strategies) {

        RSocketMessageHandler handler = new RSocketMessageHandler();
        handler.setRSocketStrategies(strategies);
        return handler;
    }
}
~~~

Giải thích:

1. `RSocketStrategies.builder()` tạo builder với các codec cơ bản mặc định.
2. `encoders(...)` bổ sung encoder JSON để serialize DTO.
3. `decoders(...)` bổ sung decoder JSON để deserialize DTO.
4. `routeMatcher(...)` dùng `PathPatternRouteMatcher` từ `spring-web`. Route RSocket vẫn là route messaging, không phải URL HTTP.
5. `RSocketMessageHandler.setRSocketStrategies(...)` áp dụng cùng chiến lược cho responder. Handler nhận encoder/decoder, route matcher và metadata extractor từ đối tượng strategies đó.

Khi tạo requester, truyền cùng bean vào builder:

~~~java
package example.rsocket;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.messaging.rsocket.RSocketRequester;
import org.springframework.messaging.rsocket.RSocketStrategies;
import org.springframework.util.MimeTypeUtils;

@Configuration
public class RSocketClientConfiguration {

    @Bean
    RSocketRequester customerRequester(RSocketStrategies strategies) {
        return RSocketRequester.builder()
                .rsocketStrategies(strategies)
                .dataMimeType(MimeTypeUtils.APPLICATION_JSON)
                .tcp("localhost", 7000);
    }
}
~~~

Requester dùng cùng encoder/decoder đã đăng ký và khai báo data MIME type là `application/json`. Server nhận MIME type này trong frame `SETUP` rồi chọn decoder tương thích.

`tcp("localhost", 7000)` tạo requester cho địa chỉ server. Kết nối không nhất thiết được mở ngay tại dòng này; Spring thiết lập và sử dụng kết nối khi có request đầu tiên.

Cấu hình `RSocketMessageHandler` ở ví dụ này dành cho trường hợp ứng dụng tự quản lý Spring Messaging handler. Nếu Spring Boot đã tự cấu hình handler và server, hãy dùng cách tùy chỉnh của Boot ở phần 6, tránh khai báo thêm handler trùng.

## 4. Dùng DTO ở hai phía

Giả sử requester gửi yêu cầu tìm khách hàng theo mã và responder trả về thông tin khách hàng.

Tạo hai DTO:

~~~java
package example.rsocket;

public record CustomerQuery(String customerId) {
}
~~~

~~~java
package example.rsocket;

public record CustomerView(String customerId, String displayName) {
}
~~~

Responder nhận DTO đã được giải mã và trả về một DTO khác:

~~~java
package example.rsocket;

import org.springframework.messaging.handler.annotation.MessageMapping;
import org.springframework.messaging.handler.annotation.Payload;
import org.springframework.stereotype.Controller;
import reactor.core.publisher.Mono;

@Controller
public class CustomerResponder {

    @MessageMapping("customers.find")
    public Mono<CustomerView> find(
            @Payload CustomerQuery query) {

        CustomerView result =
                new CustomerView(query.customerId(), "Nguyen An");

        return Mono.just(result);
    }
}
~~~

Requester gọi route tương ứng:

~~~java
package example.rsocket;

import org.springframework.messaging.rsocket.RSocketRequester;
import org.springframework.stereotype.Service;
import reactor.core.publisher.Mono;

@Service
public class CustomerClient {

    private final RSocketRequester requester;

    public CustomerClient(RSocketRequester customerRequester) {
        this.requester = customerRequester;
    }

    public Mono<CustomerView> find(String customerId) {
        return requester
                .route("customers.find")
                .data(new CustomerQuery(customerId))
                .retrieveMono(CustomerView.class);
    }
}
~~~

Luồng encode/decode diễn ra như sau:

| Bước | Phía thực hiện | Công việc |
|---|---|---|
| 1 | Requester | Encoder JSON chuyển `CustomerQuery` thành payload |
| 2 | Responder | Decoder JSON đọc payload thành `CustomerQuery` |
| 3 | Responder | Handler xử lý và tạo `CustomerView` |
| 4 | Responder | Encoder JSON chuyển `CustomerView` thành response payload |
| 5 | Requester | Decoder JSON đọc response thành `CustomerView` |

Kết quả của `retrieveMono(CustomerView.class)` là `Mono<CustomerView>`. Requester nhận object sau khi response được giải mã và pipeline được subscribe.

Trong ví dụ, DTO có mặt ở cả hai phía nên có thể đặt chúng trong một module contract dùng chung hoặc duy trì schema tương thích. Nếu hai bên phát triển độc lập, hãy quản lý thay đổi field, kiểu dữ liệu, nullability và phiên bản schema như một API contract.

## 5. Khi requester và responder nằm ở hai ứng dụng riêng

Hai ứng dụng không thể dùng chung một bean Spring qua mạng. Mỗi ứng dụng cần khai báo cấu hình tương đương:

- Cùng data MIME type, ví dụ `application/json`.
- Requester có encoder cho DTO gửi đi và decoder cho response nhận về.
- Responder có decoder cho request nhận vào và encoder cho response gửi ra.
- Cùng quy ước serialize/deserialize, chẳng hạn tên field JSON, enum, ngày giờ và kiểu số.
- Cùng quy ước metadata nếu ứng dụng gửi metadata tùy chỉnh.

Nếu một bên thay đổi cấu trúc DTO mà bên còn lại chưa cập nhật, payload có thể vẫn là JSON hợp lệ nhưng không còn tương thích ở cấp nghiệp vụ. Ưu tiên thay đổi tương thích ngược: thêm field tùy chọn có giá trị mặc định, giữ nguyên ý nghĩa field đang tồn tại và không đổi kiểu dữ liệu một cách âm thầm.

Có thể đóng gói codec và schema DTO thành thư viện nội bộ để tránh hai nhóm tự cấu hình khác nhau. Tuy nhiên, phiên bản thư viện và schema vẫn cần được quản lý đồng bộ.

## 6. Tùy chỉnh trong Spring Boot

Spring Boot tự cấu hình bean `RSocketStrategies`. Với `spring-boot-starter-rsocket`, Boot có thể tự cấu hình codec CBOR và JSON theo dependency trên classpath. Boot cũng tự cấu hình `RSocketMessageHandler` và bean `RSocketRequester.Builder`.

Trong dự án Spring Boot, nếu chỉ cần bổ sung cấu hình, dùng `RSocketStrategiesCustomizer` để tùy chỉnh builder do Boot quản lý. Ví dụ, bổ sung route matcher:

~~~java
package example.rsocket;

import org.springframework.boot.rsocket.messaging.RSocketStrategiesCustomizer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.util.pattern.PathPatternRouteMatcher;

@Configuration
public class RSocketStrategiesConfiguration {

    @Bean
    RSocketStrategiesCustomizer routeMatcherCustomizer() {
        return strategies ->
                strategies.routeMatcher(new PathPatternRouteMatcher());
    }
}
~~~

Requester có thể dùng builder được Boot inject:

~~~java
import org.springframework.messaging.rsocket.RSocketRequester;
import org.springframework.stereotype.Service;
import org.springframework.util.MimeTypeUtils;

@Service
public class CustomerClient {

    private final RSocketRequester requester;

    public CustomerClient(RSocketRequester.Builder builder) {
        this.requester = builder
                .dataMimeType(MimeTypeUtils.APPLICATION_JSON)
                .tcp("localhost", 7000);
    }
}
~~~

Builder của Boot là prototype bean vì nó có trạng thái cấu hình. Mỗi điểm inject sẽ nhận một builder mới. Không nên giữ một builder rồi tái sử dụng để tạo nhiều requester với các cấu hình kết nối khác nhau.

Nếu cần thêm encoder/decoder riêng, có thể bổ sung chúng qua `RSocketStrategiesCustomizer`. Chú ý thứ tự codec: `@Order` của customizer ảnh hưởng thứ tự áp dụng; thứ tự encoder/decoder cũng có thể ảnh hưởng lựa chọn codec khi nhiều codec cùng hỗ trợ một MIME type.

Không nên tạo một bean `RSocketStrategies` hoàn toàn mới chỉ để thêm một codec nếu mục đích là giữ các codec Boot đã tự cấu hình. Việc thay thế bean có thể làm mất cấu hình mặc định mà ứng dụng đang dựa vào.

## 7. Metadata cũng cần được thống nhất

Data và metadata là hai phần riêng trong một RSocket message. Route thường được gửi dưới dạng metadata. Spring hỗ trợ composite metadata và routing metadata mặc định trong `RSocketMessageHandler`.

Nếu ứng dụng truyền metadata tùy chỉnh, ví dụ tenant ID hoặc thông tin tracing, cần cấu hình decoder và `MetadataExtractor` tương ứng. Chỉ đăng ký encoder cho requester là chưa đủ: responder phải hiểu MIME type và giải mã metadata thành header hoặc giá trị mà handler có thể truy cập.

Ví dụ, handler có thể nhận metadata đã được trích xuất bằng `@Header`:

~~~java
@MessageMapping("orders.find")
public Mono<OrderView> find(
        @Payload OrderQuery query,
        @Header("tenantId") String tenantId) {

    return orderService.find(tenantId, query.orderId());
}
~~~

Tên header `tenantId` chỉ có giá trị nếu metadata extractor đã được cấu hình để giải mã mục metadata tương ứng và đưa nó vào map header. Với metadata chuẩn như route, Spring đã có hỗ trợ mặc định; với MIME type tùy chỉnh, cần đăng ký decoder và quy tắc trích xuất ở phía nhận.

Không thay đổi `metadataMimeType` tùy tiện. Nếu chuyển từ composite metadata sang định dạng khác, requester và responder phải cùng hiểu định dạng mới, bao gồm cách biểu diễn route và các metadata khác.

## 8. Lỗi thường gặp và cách kiểm tra

1. **Có DTO nhưng thiếu codec:** lỗi xảy ra khi Spring không tìm thấy encoder hoặc decoder hỗ trợ kiểu object. Kiểm tra dependency và danh sách codec trong strategies.
2. **Hai phía dùng MIME type khác nhau:** requester khai báo JSON nhưng responder không có decoder JSON tương thích. Kiểm tra `dataMimeType` trong SETUP và MIME type mà codec hỗ trợ.
3. **Chỉ cấu hình encoder hoặc chỉ cấu hình decoder:** request có thể gửi được nhưng response không giải mã được, hoặc ngược lại. Xét cả hai chiều request và response.
4. **Tự thay bean Boot và mất codec mặc định:** kiểm tra xem ứng dụng có đang thay thế `RSocketStrategies` do Boot auto-configure hay không. Ưu tiên `RSocketStrategiesCustomizer` nếu chỉ cần mở rộng.
5. **Route không khớp:** kiểm tra route trong `requester.route(...)` với `@MessageMapping` và cấu hình `RouteMatcher`. Route RSocket thường dùng dấu chấm làm dấu phân cách; không coi route như URL HTTP.
6. **Metadata tùy chỉnh không xuất hiện trong handler:** kiểm tra MIME type, decoder và cấu hình `MetadataExtractor`. Encoder ở requester không tự tạo header cho responder.
7. **Thay đổi DTO làm hỏng tương thích:** kiểm tra field bắt buộc, kiểu dữ liệu, enum, ngày giờ và quy tắc xử lý field không biết. Dùng kiểm thử contract giữa hai phiên bản client/server.

Khi debug, xác định lỗi thuộc giai đoạn nào: encode phía gửi, truyền tải/kết nối, route matching, decode phía nhận, xử lý handler hay encode/decode response. Cách phân loại này giúp khoanh vùng đúng cấu hình cần kiểm tra.

## 9. Checklist triển khai

- [ ] Chọn định dạng payload và MIME type rõ ràng, ví dụ JSON với `application/json`.
- [ ] Cả hai phía có encoder và decoder phù hợp với các DTO cần trao đổi.
- [ ] Requester truyền đúng `RSocketStrategies` hoặc dùng cấu hình Boot đã được tùy chỉnh.
- [ ] Responder dùng cùng strategies hoặc một cấu hình tương đương.
- [ ] Route matcher hỗ trợ đúng kiểu route đang sử dụng.
- [ ] Metadata tùy chỉnh có decoder và metadata extractor ở phía nhận.
- [ ] DTO và quy tắc serialize được quản lý như một API contract.
- [ ] Có kiểm thử request/response thực tế giữa requester và responder.

## Tài liệu tham khảo

- [Spring Framework Reference — RSocket, Strategies và Annotated Responders](https://docs.spring.io/spring-framework/reference/rsocket.html)
- [Spring Boot Reference — RSocket auto-configuration và RSocketStrategiesCustomizer](https://docs.spring.io/spring-boot/reference/messaging/rsocket.html)
- [RSocketStrategies — Spring Framework Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/rsocket/RSocketStrategies.html)
- [RSocketMessageHandler — Spring Framework Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/rsocket/annotation/support/RSocketMessageHandler.html)

### Ghi chú phiên bản

Ví dụ codec JSON chính ở trên dùng Spring Framework 7 với Jackson 3: `JacksonJsonEncoder` và `JacksonJsonDecoder`. Với Spring Framework 6 / Spring Boot 3 dùng Jackson 2, các class tương ứng là `Jackson2JsonEncoder` và `Jackson2JsonDecoder`. Không trộn codec Jackson 2 và Jackson 3 trong cùng một cấu hình nếu chưa có chủ đích và dependency tương ứng. Hãy đối chiếu API với phiên bản Spring đang dùng trong dự án.
