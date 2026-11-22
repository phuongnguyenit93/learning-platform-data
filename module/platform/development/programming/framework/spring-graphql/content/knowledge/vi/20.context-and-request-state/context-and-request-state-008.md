# Locale và timezone

Trong Spring for GraphQL, **Locale** và **timezone** là hai phần quan trọng của request state khi API cần trả thông báo, ngày giờ hoặc nội dung phù hợp với người dùng. Locale quyết định quy tắc ngôn ngữ và định dạng văn hóa; timezone xác định cách chuyển một thời điểm thành giờ địa phương.

Hai giá trị này thường được lấy từ HTTP request hoặc tùy chọn đã lưu trong hồ sơ người dùng, sau đó đưa vào **GraphQLContext** để các resolver trong cùng lần thực thi có thể sử dụng. Bài học trình bày cách phân biệt Locale với ZoneId, đọc header Accept-Language, nhận timezone preference, thiết lập context bằng WebGraphQlInterceptor, truy cập trong resolver và kiểm thử hành vi theo từng request.

## 1. Phân biệt Locale và timezone

Locale và timezone có liên quan khi hiển thị dữ liệu, nhưng chúng biểu diễn hai khái niệm khác nhau.

**Locale** mô tả ngôn ngữ và quy ước văn hóa được dùng khi trình bày dữ liệu, ví dụ:

- Ngôn ngữ hiển thị thông báo.
- Cách viết ngày, tháng và năm.
- Dấu phân cách hàng nghìn và phần thập phân.
- Quy tắc số nhiều hoặc định dạng văn bản.
- Cách sắp xếp và so sánh chuỗi theo ngôn ngữ.

Java biểu diễn locale bằng java.util.Locale, ví dụ vi-VN, en-US hoặc ja-JP.

**Timezone** xác định giờ địa phương tương ứng với một thời điểm, bao gồm quy tắc chênh lệch UTC và thay đổi giờ mùa hè nếu khu vực có áp dụng. Java biểu diễn timezone bằng java.time.ZoneId, ví dụ Asia/Ho_Chi_Minh, Europe/Paris hoặc America/Los_Angeles.

Một người có thể dùng locale vi-VN nhưng đang ở America/Los_Angeles. Locale không tự xác định timezone.

| Khái niệm | Java type | Ví dụ | Ảnh hưởng |
| --- | --- | --- | --- |
| Ngôn ngữ và quy ước trình bày | Locale | vi-VN | Văn bản, ngày tháng, số và định dạng văn hóa. |
| Múi giờ | ZoneId | Asia/Ho_Chi_Minh | Giờ địa phương và quy tắc DST. |
| Thời điểm tuyệt đối | Instant | 2026-11-20T04:00:00Z | Một thời điểm duy nhất trên timeline UTC. |

Không nên suy ra timezone chỉ từ Locale hoặc quốc gia trong locale. Một quốc gia có thể có nhiều múi giờ, và người dùng có thể chọn ngôn ngữ khác với nơi họ đang sống.

## 2. Locale và timezone là request preference

Một GraphQL operation có thể trả về nhiều object và nhiều field. Nếu toàn bộ response cần dùng cùng ngôn ngữ và timezone, các giá trị đó phù hợp với request context.

Ví dụ client gửi HTTP request:

~~~http
POST /graphql
Accept: application/json
Accept-Language: vi-VN, en;q=0.8
X-Time-Zone: Asia/Ho_Chi_Minh
Content-Type: application/json
~~~

Trong đó:

- Accept-Language là HTTP header tiêu chuẩn để client nêu các ngôn ngữ ưu tiên.
- X-Time-Zone là header do ứng dụng tự quy ước để truyền timezone preference; đây không phải header timezone bắt buộc của HTTP.
- Server cần kiểm tra các giá trị trước khi sử dụng.
- Nếu thiếu hoặc không hỗ trợ, server áp dụng fallback policy đã công bố.

Timezone cũng có thể đến từ hồ sơ người dùng đã xác thực. Ứng dụng nên định nghĩa thứ tự ưu tiên rõ ràng, ví dụ: preference hợp lệ của người dùng, sau đó là header được chấp nhận, cuối cùng là UTC. Ví dụ trong bài dùng header để minh họa việc đưa preference vào request state.

Không cần thêm locale và timezone thành argument của mọi field GraphQL nếu chúng áp dụng chung cho toàn request. Nếu một field thực sự cần cho phép client chọn cách hiển thị riêng, có thể thiết kế argument tường minh cho field đó.

## 3. Vì sao đưa preference vào GraphQLContext?

GraphQLContext là nơi lưu dữ liệu context dùng chung trong một lần GraphQL execution. Resolver có thể đọc context để biết locale, timezone, principal hoặc thông tin request khác đã được server xác định.

Luồng xử lý tổng quát:

~~~mermaid
flowchart TD
    A["HTTP GraphQL request"] --> B["Đọc Accept-Language"]
    A --> C["Đọc timezone preference"]
    B --> D["Validate và chọn Locale"]
    C --> E["Validate và chọn ZoneId"]
    D --> F["WebGraphQlInterceptor"]
    E --> F
    F --> G["GraphQLContext của execution"]
    G --> H["Query / Schema / Batch resolver"]
    H --> I["Localized response"]
~~~

GraphQLContext giúp các resolver nhận cùng một bộ preference mà không phải truyền chúng qua từng argument trong schema.

Các lợi ích chính:

- Dữ liệu được gắn với lần thực thi GraphQL hiện tại.
- Nhiều resolver có thể đọc cùng một giá trị.
- Resolver bất đồng bộ không cần dựa vào thread-local để tìm preference.
- Không làm thay đổi schema SDL hoặc operation của client.
- Dễ kiểm thử các request có header khác nhau.

GraphQLContext không phải nơi lưu trạng thái toàn cục của ứng dụng. Không đặt Locale hoặc ZoneId của một request vào field mutable của singleton bean, vì request đồng thời có thể ghi đè dữ liệu của nhau.

## 4. Lấy Locale từ Accept-Language

Header Accept-Language có thể chứa một hoặc nhiều ngôn ngữ, kèm trọng số ưu tiên q.

Ví dụ:

~~~http
Accept-Language: vi-VN, en-US;q=0.9, ja-JP;q=0.7
~~~

Server không nên chỉ lấy chuỗi đầu tiên rồi dùng trực tiếp. Cần so khớp với danh sách locale mà ứng dụng thực sự hỗ trợ.

Java cung cấp Locale.LanguageRange.parse để phân tích danh sách ưu tiên và Locale.lookup để tìm locale phù hợp trong danh sách hỗ trợ.

~~~java
import java.util.List;
import java.util.Locale;
import org.springframework.stereotype.Component;

@Component
public class RequestLocaleResolver {

    private static final Locale DEFAULT_LOCALE =
            Locale.forLanguageTag("vi-VN");

    private static final List<Locale> SUPPORTED_LOCALES = List.of(
            Locale.forLanguageTag("vi-VN"),
            Locale.forLanguageTag("en-US"),
            Locale.forLanguageTag("ja-JP")
    );

    public Locale resolve(String acceptLanguage) {
        if (acceptLanguage == null || acceptLanguage.isBlank()) {
            return DEFAULT_LOCALE;
        }

        try {
            List<Locale.LanguageRange> ranges =
                    Locale.LanguageRange.parse(acceptLanguage);

            Locale match = Locale.lookup(ranges, SUPPORTED_LOCALES);
            return match != null ? match : DEFAULT_LOCALE;
        }
        catch (IllegalArgumentException exception) {
            return DEFAULT_LOCALE;
        }
    }
}
~~~

Ví dụ này:

- Chỉ trả về locale nằm trong SUPPORTED_LOCALES.
- Tôn trọng thứ tự ưu tiên và trọng số trong header.
- Dùng vi-VN nếu header thiếu, không hợp lệ hoặc không có ngôn ngữ được hỗ trợ.
- Không tạo locale tùy ý từ mọi chuỗi client gửi.

Fallback cần nhất quán giữa các endpoint. Nếu ứng dụng có locale mặc định khác, hãy thay đổi DEFAULT_LOCALE theo chính sách sản phẩm.

### Locale tag và cách chuẩn hóa

Nên dùng BCP 47 language tag như vi-VN, en-US, fr-FR. Java có thể chuyển chuỗi thành Locale:

~~~java
Locale locale = Locale.forLanguageTag("vi-VN");
~~~

Tránh tự tách chuỗi theo dấu gạch ngang để tạo language/country, vì language tag có thể chứa script, region và extension. Dùng API chuẩn của Java và danh sách locale được hỗ trợ.

## 5. Lấy timezone preference và kiểm tra ZoneId

HTTP không cung cấp một header timezone phổ quát mà mọi ứng dụng bắt buộc phải dùng. Một ứng dụng có thể quy ước header riêng như X-Time-Zone, hoặc lấy timezone từ hồ sơ người dùng.

Nên ưu tiên tên vùng IANA như:

- Asia/Ho_Chi_Minh
- Europe/London
- America/New_York
- Australia/Sydney

Các tên vùng chứa quy tắc thay đổi UTC offset theo lịch sử và chính sách của khu vực. Chỉ lưu offset cố định như +07:00 sẽ không thể biểu diễn quy tắc DST của một khu vực khác.

Java có thể kiểm tra timezone bằng ZoneId.of:

~~~java
import java.time.DateTimeException;
import java.time.ZoneId;
import org.springframework.stereotype.Component;

@Component
public class TimeZoneResolver {

    private static final ZoneId DEFAULT_ZONE = ZoneId.of("UTC");

    public ZoneId resolve(String timeZoneHeader) {
        if (timeZoneHeader == null || timeZoneHeader.isBlank()) {
            return DEFAULT_ZONE;
        }

        try {
            return ZoneId.of(timeZoneHeader);
        }
        catch (DateTimeException exception) {
            return DEFAULT_ZONE;
        }
    }
}
~~~

Ví dụ dùng UTC làm fallback để dữ liệu máy đọc được có một mốc thống nhất. Ứng dụng hướng tới một khu vực cụ thể có thể chọn default khác, miễn là quy tắc được công bố.

Nếu sản phẩm chỉ chấp nhận IANA region ID, có thể kiểm tra thêm ZoneId.getAvailableZoneIds() hoặc dùng allowlist riêng. Nếu cho phép offset như +07:00, hãy xác định rõ đó là lựa chọn được hỗ trợ.

Không dùng TimeZone.getDefault() hoặc timezone mặc định của máy chủ làm preference của người dùng. Kết quả có thể thay đổi theo môi trường triển khai.

## 6. Đưa Locale và ZoneId vào GraphQLContext

Với HTTP transport, WebGraphQlInterceptor là điểm thích hợp để đọc request header và bổ sung dữ liệu vào ExecutionInput.

Ví dụ interceptor:

~~~java
package com.example.catalog.graphql;

import java.time.ZoneId;
import java.util.Locale;

import org.springframework.graphql.server.WebGraphQlInterceptor;
import org.springframework.graphql.server.WebGraphQlRequest;
import org.springframework.graphql.server.WebGraphQlResponse;
import org.springframework.http.HttpHeaders;
import org.springframework.stereotype.Component;

import reactor.core.publisher.Mono;

@Component
public class RequestPreferencesInterceptor
        implements WebGraphQlInterceptor {

    private final RequestLocaleResolver localeResolver;
    private final TimeZoneResolver timeZoneResolver;

    public RequestPreferencesInterceptor(
            RequestLocaleResolver localeResolver,
            TimeZoneResolver timeZoneResolver) {
        this.localeResolver = localeResolver;
        this.timeZoneResolver = timeZoneResolver;
    }

    @Override
    public Mono<WebGraphQlResponse> intercept(
            WebGraphQlRequest request,
            Chain chain) {

        String acceptLanguage =
                request.getHeaders().getFirst(HttpHeaders.ACCEPT_LANGUAGE);

        String timeZoneHeader =
                request.getHeaders().getFirst("X-Time-Zone");

        Locale locale = localeResolver.resolve(acceptLanguage);
        ZoneId zoneId = timeZoneResolver.resolve(timeZoneHeader);

        request.configureExecutionInput((executionInput, builder) ->
                builder.graphQLContext(contextBuilder -> {
                    contextBuilder.put("requestLocale", locale);
                    contextBuilder.put("requestZoneId", zoneId);
                }).build()
        );

        return chain.next(request);
    }
}
~~~

Interceptor thực hiện các việc:

1. Đọc Accept-Language và header timezone.
2. Gọi resolver để kiểm tra và chọn giá trị hợp lệ.
3. Đưa Locale và ZoneId vào GraphQLContext của execution.
4. Chuyển request tiếp cho GraphQL engine.

WebGraphQlInterceptor được Spring for GraphQL tích hợp với HTTP transport. Đăng ký interceptor thành Spring bean để framework áp dụng cho request. Nếu ứng dụng dùng WebSocket, cần thiết kế cách nhận preference theo cơ chế interceptor/connection initialization của WebSocket; không mặc định rằng HTTP interceptor sẽ xử lý mọi message trên WebSocket.

Các key requestLocale và requestZoneId là tên do ứng dụng quy ước. Hãy dùng hằng số hoặc một class key tập trung nếu nhiều component cùng đọc chúng, để tránh sai chính tả.

## 7. Đọc request state trong resolver bằng @ContextValue

Spring for GraphQL cung cấp @ContextValue để lấy giá trị từ GraphQLContext vào tham số method.

Ví dụ schema:

~~~graphql
scalar DateTime

type Query {
    events: [Event!]!
}

type Event {
    id: ID!
    startsAt: DateTime!
    startsAtLabel: String!
}
~~~

Ở đây DateTime là custom scalar cần được đăng ký riêng; nó đại diện thời điểm theo hợp đồng máy đọc được. Field startsAtLabel là chuỗi hiển thị theo locale và timezone của request.

Java model:

~~~java
import java.time.Instant;

public record Event(
        String id,
        Instant startsAt
) {
}
~~~

Resolver:

~~~java
import java.time.ZoneId;
import java.time.format.DateTimeFormatter;
import java.time.format.FormatStyle;
import java.util.Locale;

import org.springframework.graphql.data.method.annotation.ContextValue;
import org.springframework.graphql.data.method.annotation.SchemaMapping;
import org.springframework.stereotype.Controller;

@Controller
public class EventController {

    @SchemaMapping(typeName = "Event", field = "startsAtLabel")
    public String startsAtLabel(
            Event event,
            @ContextValue("requestLocale") Locale locale,
            @ContextValue("requestZoneId") ZoneId zoneId) {

        DateTimeFormatter formatter =
                DateTimeFormatter.ofLocalizedDateTime(FormatStyle.MEDIUM)
                        .withLocale(locale)
                        .withZone(zoneId);

        return formatter.format(event.startsAt());
    }
}
~~~

@ContextValue lấy object đã được interceptor đặt vào GraphQLContext. Resolver không cần đọc lại HTTP header hoặc tự phân tích locale/timezone.

Nếu key có thể không tồn tại, có thể cấu hình tham số context là không bắt buộc theo API annotation của phiên bản đang dùng, hoặc dùng DataFetchingEnvironment để đọc context và áp dụng fallback rõ ràng. Trong ví dụ này, interceptor luôn đặt cả hai key nên resolver có thể yêu cầu chúng.

### Đọc trực tiếp qua DataFetchingEnvironment

Khi resolver cần truy cập nhiều giá trị context hoặc muốn kiểm tra key tồn tại, có thể dùng DataFetchingEnvironment:

~~~java
import graphql.schema.DataFetchingEnvironment;
import java.time.ZoneId;
import java.time.format.DateTimeFormatter;
import java.time.format.FormatStyle;
import java.util.Locale;

@SchemaMapping(typeName = "Event", field = "startsAtLabel")
public String startsAtLabel(
        Event event,
        DataFetchingEnvironment environment) {

    Locale locale =
            environment.getGraphQlContext().get("requestLocale");

    ZoneId zoneId =
            environment.getGraphQlContext().get("requestZoneId");

    return DateTimeFormatter.ofLocalizedDateTime(FormatStyle.MEDIUM)
            .withLocale(locale)
            .withZone(zoneId)
            .format(event.startsAt());
}
~~~

Hai cách có mục đích tương tự. @ContextValue phù hợp khi method chỉ cần một vài giá trị đã biết; DataFetchingEnvironment hữu ích khi cần đọc context động hoặc thêm metadata của lần thực thi.

## 8. Dùng Locale để định dạng văn bản và số

Locale không chỉ ảnh hưởng ngày tháng. Java có các formatter theo locale cho số và tiền tệ.

Định dạng số:

~~~java
import java.text.NumberFormat;

NumberFormat numberFormat = NumberFormat.getNumberInstance(locale);
String formattedCount = numberFormat.format(1234567.89);
~~~

Định dạng tiền:

~~~java
import java.text.NumberFormat;
import java.util.Currency;

NumberFormat currencyFormat =
        NumberFormat.getCurrencyInstance(locale);

currencyFormat.setCurrency(Currency.getInstance("VND"));
String formattedPrice = currencyFormat.format(amount);
~~~

Không nên suy ra currency chỉ từ Locale. Locale en-US không có nghĩa mọi giá trị tiền phải là USD; currency là dữ liệu nghiệp vụ riêng. Hãy lấy loại tiền từ sản phẩm, giao dịch hoặc cấu hình nghiệp vụ rồi dùng Locale để định dạng.

Đối với thông báo dịch, có thể dùng Spring MessageSource:

~~~java
String message = messageSource.getMessage(
        "event.notFound",
        new Object[] { eventId },
        locale
);
~~~

Resource bundle có thể chứa các bản dịch như messages_vi.properties, messages_en.properties và messages_ja.properties. Locale được lấy từ request context giúp cùng một service trả thông báo theo ngôn ngữ client đã chọn.

Không tự ghép chuỗi thông báo bằng các mảnh tiếng Anh hoặc tiếng Việt trong resolver. Đặt thông điệp vào resource bundle giúp dịch thuật và bảo trì tập trung hơn.

## 9. Dùng ZoneId để chuyển đổi thời điểm

Nên lưu và truyền thời điểm tuyệt đối bằng Instant hoặc kiểu có offset rõ ràng. Chỉ chuyển sang giờ địa phương khi trình bày cho người dùng.

Ví dụ:

~~~java
Instant startsAt = Instant.parse("2026-11-20T04:00:00Z");

ZonedDateTime localDateTime = startsAt.atZone(
        ZoneId.of("Asia/Ho_Chi_Minh")
);
~~~

Instant biểu diễn một thời điểm trên timeline UTC. ZoneId áp dụng quy tắc của khu vực để tính giờ địa phương.

Với DateTimeFormatter, có thể format trực tiếp Instant bằng withZone:

~~~java
DateTimeFormatter formatter =
        DateTimeFormatter.ofLocalizedDateTime(FormatStyle.MEDIUM)
                .withLocale(Locale.forLanguageTag("vi-VN"))
                .withZone(ZoneId.of("Asia/Ho_Chi_Minh"));

String label = formatter.format(startsAt);
~~~

Không nên lưu giờ địa phương dạng LocalDateTime mà không lưu timezone hoặc offset nếu dữ liệu đại diện cho một sự kiện xảy ra tại thời điểm cụ thể. Khi đổi múi giờ hoặc xử lý DST, giờ địa phương có thể không xác định duy nhất một instant.

Đối với lịch hẹn được tạo theo giờ địa phương, cần lưu cả quy tắc timezone phù hợp với nghiệp vụ, ví dụ LocalDateTime cùng ZoneId, rồi xác định chính xác cách xử lý khoảng thời gian bị nhảy hoặc lặp khi DST thay đổi.

## 10. Giữ dữ liệu API ổn định, tách khỏi chuỗi hiển thị

Không nên thay đổi giá trị máy đọc được theo locale nếu client cần dùng nó để lưu, so sánh hoặc tính toán.

Ví dụ schema:

~~~graphql
scalar DateTime

type Event {
    id: ID!
    startsAt: DateTime!
    startsAtLabel: String!
}
~~~

- startsAt trả thời điểm theo định dạng chuẩn của custom scalar, ví dụ ISO-8601 UTC.
- startsAtLabel trả chuỗi trình bày theo locale và timezone của request.

Client có thể dùng startsAt để sắp xếp, lưu hoặc đồng bộ dữ liệu. UI có thể dùng startsAtLabel để hiển thị cho người dùng.

Nếu chỉ có một field startsAt nhưng server thay đổi nội dung string theo timezone và locale, client khó so sánh và cache kết quả. Tách hai mục đích giúp API rõ ràng hơn.

Locale/timezone có thể làm response khác nhau dù GraphQL document và variables giống nhau. Nếu response được cache ở HTTP gateway hoặc CDN, cache key cần xét các preference ảnh hưởng response. Với HTTP caching, cân nhắc Vary: Accept-Language, X-Time-Zone nếu những header này làm thay đổi representation.

## 11. Request scope và an toàn khi thực thi bất đồng bộ

GraphQL có thể phân giải nhiều field song song. Resolver có thể chạy trên các thread khác nhau hoặc tiếp tục qua future/reactive pipeline.

Không nên dựa hoàn toàn vào ThreadLocal hoặc LocaleContextHolder để truyền request preference qua mọi bước bất đồng bộ. Thread xử lý có thể thay đổi, trong khi context tường minh được gắn với GraphQL execution và có thể được resolver đọc trực tiếp.

Một số nguyên tắc:

- Đặt Locale và ZoneId vào GraphQLContext ở đầu request.
- Xem các giá trị này là immutable preference trong suốt execution.
- Không ghi preference của request vào field của singleton controller/service.
- Không dùng static mutable variable để giữ locale/timezone hiện tại.
- Với batch loader, sử dụng context của execution khi cần; không giữ context trong biến dùng chung.
- Nếu một resolver cần preference khác cho một field cụ thể, truyền nó qua argument hoặc thiết kế rõ local context thay vì sửa request context chung.

GraphQLContext phù hợp cho dữ liệu request-wide. Nếu dữ liệu chỉ có ý nghĩa trong một nhánh của selection tree, có thể cân nhắc local context của GraphQL Java thay vì đưa mọi thứ vào context toàn request.

## 12. Locale/timezone và DataLoader

DataLoader có cache theo key trong phạm vi request. Nếu batch loader trả về dữ liệu đã được format theo locale hoặc timezone, cần bảo đảm các preference đó không thay đổi giữa các lần gọi cùng DataLoader trong request.

Thông thường, locale và timezone được cố định ở GraphQLContext cho toàn execution, vì vậy chúng có thể được đọc trong batch loader qua batch environment/context.

Nếu kết quả batch phụ thuộc vào một tham số có thể thay đổi theo từng lần gọi field, tham số đó cần được đưa vào key tổng hợp hoặc cơ chế context phù hợp. Ví dụ, cùng một Event ID nhưng client yêu cầu format ở hai timezone khác nhau thì không thể cache chung một chuỗi đã format chỉ bằng Event ID.

Tốt hơn, batch loader nên trả dữ liệu miền chuẩn như Instant, còn resolver format theo locale/timezone. Cách này giảm nguy cơ cache chuỗi trình bày sai ngữ cảnh.

## 13. Kiểm thử locale và timezone theo request

Cần kiểm thử cả phần chọn preference và phần GraphQL context.

### Kiểm thử RequestLocaleResolver

~~~java
@Test
void choosesFirstSupportedLocaleFromAcceptLanguage() {
    RequestLocaleResolver resolver = new RequestLocaleResolver();

    Locale locale = resolver.resolve("vi-VN, en-US;q=0.8");

    assertThat(locale).isEqualTo(Locale.forLanguageTag("vi-VN"));
}
~~~

Các trường hợp khác:

- Header không có.
- Header rỗng.
- Header sai cú pháp.
- Locale không nằm trong danh sách hỗ trợ.
- Nhiều locale với trọng số q khác nhau.
- Wildcard *.

### Kiểm thử TimeZoneResolver

~~~java
@Test
void fallsBackToUtcForInvalidTimeZone() {
    TimeZoneResolver resolver = new TimeZoneResolver();

    ZoneId zoneId = resolver.resolve("Invalid/Zone");

    assertThat(zoneId).isEqualTo(ZoneId.of("UTC"));
}
~~~

Nên kiểm thử thêm timezone hợp lệ, giá trị trống và vùng có DST để bảo đảm resolver dùng ZoneId thay vì hardcode offset.

### Kiểm thử GraphQL qua HTTP

Dùng WebTestClient hoặc HttpGraphQlTester để gửi request với header khác nhau:

~~~http
Accept-Language: vi-VN
X-Time-Zone: Asia/Ho_Chi_Minh
~~~

Sau đó gửi request thứ hai:

~~~http
Accept-Language: en-US
X-Time-Zone: America/Los_Angeles
~~~

Cùng một GraphQL document có thể trả startsAtLabel khác nhau, trong khi startsAt vẫn giữ giá trị ISO-8601 chuẩn. Kiểm thử như vậy xác nhận interceptor đặt context riêng cho từng request và không rò preference giữa các lần thực thi.

Cũng nên kiểm tra resolver/service không được gọi nếu request bị từ chối theo chính sách header, hoặc fallback được áp dụng đúng nếu ứng dụng chọn chính sách fallback.

## 14. Các lỗi thường gặp

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- |
| Response luôn dùng ngôn ngữ mặc định | Không đọc Accept-Language, hoặc locale client không nằm trong danh sách hỗ trợ. | Kiểm tra interceptor, danh sách locale và fallback. |
| Locale không đúng ưu tiên | Chỉ lấy phần đầu header hoặc bỏ qua trọng số q. | Dùng Locale.LanguageRange.parse và Locale.lookup. |
| Timezone không hợp lệ gây lỗi resolver | Dùng trực tiếp chuỗi client gửi cho ZoneId.of. | Validate và áp dụng fallback hoặc trả request error theo policy. |
| Giờ hiển thị lệch so với người dùng | Dùng timezone máy chủ hoặc offset cố định. | Dùng ZoneId theo preference và format từ Instant. |
| Locale bị dùng nhầm làm timezone | Giả định ngôn ngữ/quốc gia xác định duy nhất múi giờ. | Lưu Locale và ZoneId thành hai giá trị riêng. |
| Resolver bất đồng bộ dùng sai preference | Dựa vào thread-local không được truyền sang thread khác. | Đọc từ GraphQLContext tường minh. |
| Request đồng thời ảnh hưởng lẫn nhau | Lưu preference trong field mutable của singleton. | Đặt dữ liệu trong context theo request. |
| Client không thể so sánh timestamp | Server trả chuỗi ngày giờ đã localize ở field máy đọc được. | Trả Instant/DateTime chuẩn và field label riêng. |
| Cache trả sai định dạng | Cache key không xét header làm thay đổi response. | Thêm preference vào cache key hoặc cấu hình Vary phù hợp. |
| Currency không đúng locale | Suy ra currency từ Locale. | Lấy currency từ dữ liệu nghiệp vụ, dùng Locale chỉ để format. |

## 15. Quy trình triển khai Locale và timezone

Khi bổ sung request preference cho GraphQL API, có thể làm theo trình tự:

1. Xác định response nào cần bản địa hóa.
2. Quy định Locale và timezone lấy từ header, hồ sơ người dùng hay cả hai.
3. Chọn danh sách Locale được hỗ trợ và fallback.
4. Chọn quy ước timezone, ưu tiên IANA ZoneId và xác định fallback.
5. Viết resolver riêng để parse và validate từng preference.
6. Đăng ký WebGraphQlInterceptor để đưa giá trị vào GraphQLContext.
7. Dùng @ContextValue hoặc DataFetchingEnvironment trong resolver.
8. Dùng Locale cho message/number/date formatting.
9. Dùng ZoneId để chuyển Instant thành giờ địa phương.
10. Giữ field thời gian máy đọc được theo định dạng chuẩn; tách field hiển thị nếu cần.
11. Kiểm tra async resolver, DataLoader và request isolation.
12. Kiểm thử nhiều header, fallback, timezone không hợp lệ và cache behavior.

## 16. Những điểm cần ghi nhớ

- Locale điều khiển ngôn ngữ và quy tắc định dạng văn hóa; ZoneId điều khiển giờ địa phương và quy tắc DST.
- Accept-Language là header tiêu chuẩn; header timezone như X-Time-Zone là quy ước của ứng dụng.
- Chỉ chấp nhận Locale được hỗ trợ và kiểm tra timezone trước khi sử dụng.
- Dùng WebGraphQlInterceptor để đưa preference vào GraphQLContext của HTTP execution.
- Dùng @ContextValue hoặc DataFetchingEnvironment để đọc context trong resolver.
- GraphQLContext là request state; không lưu preference trong singleton mutable field hoặc static variable.
- Lưu thời điểm bằng Instant/UTC; chỉ chuyển sang ZoneId khi trình bày.
- Không suy ra currency từ Locale và không suy ra timezone từ ngôn ngữ.
- Tách timestamp chuẩn khỏi chuỗi hiển thị đã localize.
- Cache response cần xét Locale/timezone nếu các giá trị này làm thay đổi representation.

Locale và timezone giúp GraphQL API trình bày dữ liệu phù hợp với từng người dùng mà không làm thay đổi hợp đồng dữ liệu cốt lõi. Khi xác thực preference ở đầu request, lưu chúng trong GraphQLContext và sử dụng tường minh trong resolver, ứng dụng Spring for GraphQL có thể xử lý bản địa hóa nhất quán ngay cả khi các field được thực thi bất đồng bộ.

