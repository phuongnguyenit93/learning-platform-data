# Quản lý nhiều bộ chính sách JSON trong cùng ứng dụng

Một ứng dụng có thể trao đổi JSON với nhiều nhóm hệ thống, và mỗi nhóm có hợp đồng dữ liệu khác nhau. API công khai có thể dùng camelCase và chỉ trả các trường được phép công bố; một đối tác cũ lại yêu cầu snake_case; dữ liệu lưu trữ nội bộ có thể cần giữ đầy đủ thông tin; một webhook bên ngoài có thể cần chính sách đọc linh hoạt để chấp nhận field mới.

Nếu mọi luồng đều dùng một cấu hình JSON duy nhất, các yêu cầu này dễ xung đột. Thay đổi cách đặt tên field cho một đối tác có thể làm thay đổi API công khai. Bỏ qua field lạ để tương thích webhook có thể khiến lỗi dữ liệu nội bộ bị che khuất. Một serializer phục vụ database cũng có thể vô tình để lộ thuộc tính không nên xuất hiện trong response.

Cách tổ chức phù hợp là xác định **các bộ chính sách JSON theo hợp đồng và ranh giới sử dụng**, rồi gắn từng chính sách vào đúng ObjectMapper, ObjectReader/ObjectWriter hoặc HTTP codec. Mỗi chính sách cần có tên, mục đích, cấu hình và test riêng.

## 1. Vì sao một ứng dụng cần nhiều chính sách JSON?

ObjectMapper không chỉ quyết định cách chuyển object thành JSON. Nó còn quyết định cách đọc JSON, xử lý field không biết, field null, tên thuộc tính, ngày giờ, enum, polymorphic type, custom serializer và nhiều quy tắc khác.

Những quy tắc đó có thể khác nhau giữa các ranh giới dữ liệu.

Ví dụ một ứng dụng thương mại điện tử:

| Ranh giới | Nhu cầu JSON | Chính sách có thể áp dụng |
|---|---|---|
| API công khai | Hợp đồng ổn định, chỉ xuất field được công bố | DTO riêng, camelCase, format ngày giờ thống nhất |
| API đối tác | Tương thích với hợp đồng cũ | snake_case, quy tắc null và unknown field theo hợp đồng |
| Webhook đầu vào | Chấp nhận field mới từ nhà cung cấp | Đọc linh hoạt có kiểm soát, kiểm tra nghiệp vụ sau parse |
| Lưu snapshot nội bộ | Giữ dữ liệu cần khôi phục đầy đủ | Schema nội bộ được version hóa, không dùng DTO công khai |
| Audit/event log | Biểu diễn dữ liệu nhất quán để truy vết | Format thời gian, enum và kiểu nghiệp vụ cố định |
| Tích hợp hệ thống cũ | Tương thích format lịch sử | Custom serializer/deserializer hoặc DTO adapter riêng |

Một chính sách JSON nên trả lời được các câu hỏi:

- Dữ liệu thuộc hợp đồng nào?
- Ai là producer và consumer?
- Đây là dữ liệu đầu vào hay đầu ra?
- Field nào được phép xuất hiện?
- Field thiếu, null hoặc không biết được xử lý ra sao?
- Tên field và format ngày giờ được quy định thế nào?
- Kiểu dữ liệu đặc biệt nào cần module hoặc serializer riêng?
- Phiên bản hợp đồng được kiểm thử ở đâu?

Khi trả lời được các câu hỏi này, việc quyết định có cần mapper riêng hay chỉ cần reader/writer riêng sẽ rõ ràng hơn.

## 2. Phân biệt ObjectMapper, ObjectReader và ObjectWriter

Jackson cung cấp nhiều cấp cấu hình. Không phải mọi khác biệt về JSON đều cần tạo thêm một ObjectMapper.

| Thành phần | Vai trò | Khi nên dùng |
|---|---|---|
| ObjectMapper | Cấu hình tổng thể cho serialization và deserialization | Một bộ chính sách có nhiều quy tắc chung |
| ObjectReader | Cấu hình đọc JSON, gắn với kiểu đích và các tùy chọn đọc | Nhiều cách đọc cho cùng mapper |
| ObjectWriter | Cấu hình ghi JSON, gắn với kiểu nguồn và các tùy chọn ghi | Nhiều cách xuất JSON cho cùng mapper |
| JsonFactory | Thành phần cấp thấp tạo parser/generator | Cần kiểm soát quá trình đọc/ghi token hoặc factory |
| Module | Bổ sung serializer, deserializer và hỗ trợ kiểu dữ liệu | Kiểu dữ liệu hoặc định dạng cần hỗ trợ thêm |

### 2.1. Dùng một ObjectMapper với nhiều ObjectReader/ObjectWriter

Nếu các luồng có chung module, naming strategy và phần lớn cấu hình, nhưng khác một vài feature khi đọc hoặc ghi, hãy cân nhắc ObjectReader/ObjectWriter.

Ví dụ ứng dụng có một mapper chuẩn, nhưng cần một writer chỉ định dạng JSON đẹp khi xuất file:

~~~java
ObjectMapper mapper = createApplicationMapper();

ObjectWriter compactWriter =
    mapper.writerFor(OrderResponse.class);

ObjectWriter prettyWriter =
    mapper.writerFor(OrderResponse.class)
        .with(SerializationFeature.INDENT_OUTPUT);

String compactJson = compactWriter.writeValueAsString(response);
String prettyJson = prettyWriter.writeValueAsString(response);
~~~

Hai writer dùng cùng mapper nền nhưng có cấu hình ghi riêng. Không cần tạo hai ObjectMapper chỉ để bật hoặc tắt INDENT_OUTPUT.

Tương tự, ObjectReader có thể đặt feature đọc riêng:

~~~java
ObjectReader strictReader = mapper.readerFor(PartnerRequest.class)
    .with(DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES);

ObjectReader compatibleReader = mapper.readerFor(PartnerRequest.class)
    .without(DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES);
~~~

Cách này phù hợp khi hai chế độ đọc có cùng module, cùng cách đặt tên field và cùng quy tắc kiểu dữ liệu, chỉ khác cách xử lý field không biết.

ObjectReader và ObjectWriter là đối tượng cấu hình bất biến theo cách sử dụng thông thường: gọi with/without tạo cấu hình reader/writer mới. Có thể tạo trước và tái sử dụng, giúp ý định của từng luồng được thể hiện rõ trong code.

### 2.2. Dùng nhiều ObjectMapper khi hợp đồng thực sự khác nhau

Nên tạo mapper riêng khi các luồng có bộ quy tắc khác nhau đáng kể, chẳng hạn:

- Một đối tác dùng snake_case, hệ thống nội bộ dùng camelCase.
- Một hợp đồng yêu cầu format ngày giờ khác.
- Một luồng cần custom serializer cho kiểu tiền tệ, luồng khác dùng biểu diễn chuẩn.
- Một ranh giới cần chính sách đọc field lạ khác hẳn.
- Một hệ thống cũ cần mix-in hoặc quy tắc tương thích riêng.
- Một ranh giới tin cậy khác yêu cầu cấu hình polymorphic type và allowlist khác nhau.

Ví dụ:

~~~text
                     Application
                          |
              +-----------+-----------+
              |           |           |
              v           v           v
        Public API    Partner API   Internal Store
              |           |           |
              v           v           v
        publicMapper partnerMapper internalMapper
              |           |           |
              v           v           v
        Public DTO   Partner DTO   Storage Model
~~~

Mỗi mapper nên được đặt tên theo hợp đồng hoặc ranh giới sử dụng, chẳng hạn publicApiMapper, partnerApiMapper, webhookMapper, internalSnapshotMapper. Tên kiểu defaultMapper2 hoặc specialMapper khó cho người đọc biết mapper phục vụ ai.

Không nên tạo mapper mới cho từng request. Mapper là thành phần cấu hình lâu dài của ứng dụng, được tạo lúc khởi động và tái sử dụng sau khi cấu hình hoàn tất.

## 3. Thiết kế chính sách trước khi viết cấu hình

Một bộ chính sách nên có phạm vi rõ ràng. Có thể mô tả bằng bảng trước khi triển khai:

| Thuộc tính chính sách | Public API | Partner API | Webhook inbound |
|---|---|---|---|
| Kiểu DTO | Public request/response | Partner request/response | Event DTO |
| Naming | camelCase | snake_case | Theo payload nhà cung cấp |
| Unknown field | Theo hợp đồng công khai | Theo phiên bản đối tác | Có thể bỏ qua field chưa biết |
| Null output | Theo hợp đồng | Theo hợp đồng cũ | Không áp dụng cho chiều đọc |
| Date/time | ISO-8601 đã thống nhất | Format đối tác yêu cầu | Parse theo format nhà cung cấp |
| Enum lạ | Xử lý theo contract | Adapter tương thích nếu cần | Chuyển thành lỗi hoặc trạng thái unknown có kiểm soát |
| Custom type | Kiểu công khai | Kiểu adapter đối tác | Kiểu event riêng |
| Security | DTO công khai, không bật typing rộng | Allowlist kiểu cần thiết | Không tin cậy input |

Bảng này không phải cấu hình Jackson. Nó là tài liệu thiết kế hợp đồng, giúp quyết định thuộc tính nào cần đặt trong mapper và thuộc tính nào thuộc DTO hoặc tầng nghiệp vụ.

### 3.1. Tách chính sách đọc và ghi khi cần

Đầu vào và đầu ra thường có yêu cầu khác nhau.

Ví dụ:

- Webhook inbound có thể bỏ qua field chưa biết để nhà cung cấp bổ sung field mà consumer chưa sử dụng.
- API response outbound cần kiểm soát chặt field được xuất ra.
- Snapshot nội bộ cần đọc được nhiều phiên bản dữ liệu cũ.
- Event producer cần ghi đúng schema mà consumer đang chờ.

Không nên giả định một cặp feature đọc/ghi phải giống nhau chỉ vì chúng cùng thuộc một ObjectMapper. Có thể dùng reader/writer riêng hoặc mapper riêng cho từng hướng nếu cấu hình khác biệt lớn.

### 3.2. Tách DTO theo hợp đồng

Nhiều khác biệt không nên giải quyết bằng cách tăng số lượng mapper. Nếu public API và database model có field khác nhau, hãy dùng DTO hoặc storage model riêng.

Ví dụ:

~~~java
public record UserPublicResponse(
    String id,
    String displayName
) {}

public record UserStorageDocument(
    String id,
    String displayName,
    String email,
    String passwordHash,
    String internalStatus
) {}
~~~

Public response không có passwordHash và internalStatus. Vì vậy, mapper không cần cố gắng loại trừ những field nhạy cảm khỏi một Entity lớn để tạo API response.

DTO giúp hợp đồng được thể hiện trong kiểu Java. Mapper chịu trách nhiệm format và chuyển đổi JSON của kiểu đó.

## 4. Tạo nhiều ObjectMapper trong ứng dụng Java

Với Jackson 2.x, có thể dùng JsonMapper builder để tạo mapper và đăng ký module. Ví dụ dưới đây tạo một mapper nội bộ và một mapper cho đối tác.

~~~java
import com.fasterxml.jackson.annotation.JsonInclude;
import com.fasterxml.jackson.databind.DeserializationFeature;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.PropertyNamingStrategies;
import com.fasterxml.jackson.databind.json.JsonMapper;
import com.fasterxml.jackson.datatype.jdk8.Jdk8Module;
import com.fasterxml.jackson.datatype.jsr310.JavaTimeModule;

public final class JsonPolicies {

    private JsonPolicies() {
    }

    public static ObjectMapper createInternalMapper() {
        return JsonMapper.builder()
            .addModule(new JavaTimeModule())
            .addModule(new Jdk8Module())
            .build();
    }

    public static ObjectMapper createPartnerMapper(
        ObjectMapper internalMapper
    ) {
        ObjectMapper mapper = internalMapper.copy();

        mapper.setPropertyNamingStrategy(
            PropertyNamingStrategies.SNAKE_CASE
        );
        mapper.configure(
            DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES,
            false
        );
        mapper.setSerializationInclusion(JsonInclude.Include.NON_NULL);

        return mapper;
    }
}
~~~

Mapper đối tác được tạo từ bản sao của mapper nội bộ, nên kế thừa các module và cấu hình nền đã có. Sau đó, nó bổ sung quy tắc riêng về tên thuộc tính, field không biết và giá trị null.

Trong ví dụ, đối tác cho phép bỏ qua field không biết. Đây là một quyết định theo hợp đồng, không phải giá trị mặc định nên áp dụng cho mọi API. Nếu đối tác yêu cầu phát hiện payload sai schema, hãy giữ chế độ strict và trả lỗi tích hợp rõ ràng.

### 4.1. Khi nào dùng copy()?

ObjectMapper.copy() tạo một mapper độc lập có cấu hình ban đầu dựa trên mapper nguồn. Cách này hữu ích khi hai chính sách có phần lớn module và cấu hình giống nhau.

Nên dùng copy() khi:

- Hai mapper có chung cách xử lý JavaTime, Optional và kiểu dữ liệu chung.
- Chỉ một số feature hoặc naming strategy khác nhau.
- Muốn giữ module đã đăng ký mà không lặp lại danh sách module.

Nên tạo mapper từ đầu khi hai ranh giới có bộ module, factory hoặc quy tắc bảo mật khác nhau đáng kể. Việc tạo mapper riêng cần được xem như một quyết định về hợp đồng, không phải cách sửa nhanh cho mọi lỗi serialization.

copy() không nên được gọi cho từng request. Hãy tạo các mapper chính lúc ứng dụng khởi động, cấu hình xong rồi chia sẻ chúng.

### 4.2. Tránh sửa mapper sau khi đã đưa vào sử dụng

ObjectMapper được thiết kế để dùng đồng thời sau khi cấu hình hoàn tất. Vì vậy, hãy đăng ký module, naming strategy, feature, mix-in và serializer trước khi mapper được chia sẻ cho các luồng xử lý.

Không nên viết:

~~~java
public String serialize(Object value, ObjectMapper mapper) throws Exception {
    mapper.setPropertyNamingStrategy(
        PropertyNamingStrategies.SNAKE_CASE
    );
    return mapper.writeValueAsString(value);
}
~~~

Nếu một request đổi naming strategy của mapper dùng chung, request khác có thể nhận cấu hình ngoài ý muốn. Hãy tạo reader/writer riêng hoặc dùng mapper riêng cho hợp đồng đó.

## 5. Cấu hình nhiều mapper trong Spring Boot

Trong ứng dụng Spring Boot, ObjectMapper thường được framework cấu hình để sử dụng với HTTP message converter. Khi có nhiều mapper, cần phân biệt hai việc:

1. Đăng ký nhiều bean ObjectMapper để service hoặc adapter có thể inject đúng chính sách.
2. Cấu hình đúng HTTP converter hoặc codec để request thực sự được đọc/ghi bằng mapper mong muốn.

Chỉ khai báo hai bean ObjectMapper không tự động làm Spring MVC chọn mapper theo từng endpoint.

### 5.1. Khai báo mapper bean có tên rõ ràng

Ví dụ:

~~~java
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.PropertyNamingStrategies;
import com.fasterxml.jackson.databind.DeserializationFeature;
import com.fasterxml.jackson.databind.json.JsonMapper;
import com.fasterxml.jackson.datatype.jsr310.JavaTimeModule;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Primary;

@Configuration
public class JsonMapperConfiguration {

    @Bean("defaultJsonMapper")
    @Primary
    public ObjectMapper defaultJsonMapper() {
        return JsonMapper.builder()
            .addModule(new JavaTimeModule())
            .build();
    }

    @Bean("partnerJsonMapper")
    public ObjectMapper partnerJsonMapper(
        @Qualifier("defaultJsonMapper") ObjectMapper defaultMapper
    ) {
        ObjectMapper mapper = defaultMapper.copy();

        mapper.setPropertyNamingStrategy(
            PropertyNamingStrategies.SNAKE_CASE
        );
        mapper.configure(
            DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES,
            false
        );

        return mapper;
    }
}
~~~

Bean defaultJsonMapper được đánh dấu Primary để làm lựa chọn mặc định khi một thành phần inject ObjectMapper mà không chỉ rõ qualifier. Các thành phần cần chính sách đối tác phải chỉ rõ partnerJsonMapper.

Ví dụ inject vào adapter:

~~~java
import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.stereotype.Component;

@Component
public class PartnerPayloadAdapter {

    private final ObjectMapper mapper;

    public PartnerPayloadAdapter(
        @Qualifier("partnerJsonMapper") ObjectMapper mapper
    ) {
        this.mapper = mapper;
    }

    public PartnerRequest parse(String json) throws Exception {
        return mapper.readValue(json, PartnerRequest.class);
    }
}
~~~

Qualifier làm rõ hợp đồng mà adapter đang sử dụng. Nếu thiếu qualifier trong ứng dụng có nhiều bean cùng kiểu, Spring có thể báo lỗi không xác định được bean hoặc inject nhầm bean Primary.

### 5.2. Gắn mapper riêng vào HTTP converter

Spring MVC dùng HttpMessageConverter để chuyển request/response body. MappingJackson2HttpMessageConverter có thể được tạo với ObjectMapper cụ thể.

Một cách rõ ràng để chọn chính sách theo media type là dùng vendor media type:

~~~java
import java.util.List;

import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.MediaType;
import org.springframework.http.converter.HttpMessageConverter;
import org.springframework.http.converter.json.MappingJackson2HttpMessageConverter;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

@Configuration
public class PartnerJsonHttpConfiguration
        implements WebMvcConfigurer {

    private final ObjectMapper partnerJsonMapper;

    public PartnerJsonHttpConfiguration(
        @Qualifier("partnerJsonMapper") ObjectMapper partnerJsonMapper
    ) {
        this.partnerJsonMapper = partnerJsonMapper;
    }

    @Override
    public void extendMessageConverters(
        List<HttpMessageConverter<?>> converters
    ) {
        MappingJackson2HttpMessageConverter converter =
            new MappingJackson2HttpMessageConverter(partnerJsonMapper);

        converter.setSupportedMediaTypes(List.of(
            MediaType.valueOf("application/vnd.example.partner+json")
        ));

        converters.add(0, converter);
    }
}
~~~

Endpoint đối tác có thể khai báo:

~~~java
@PostMapping(
    path = "/partner/orders",
    consumes = "application/vnd.example.partner+json",
    produces = "application/vnd.example.partner+json"
)
public PartnerResponse receive(
    @RequestBody PartnerRequest request
) {
    return partnerService.process(request);
}
~~~

Converter được ưu tiên chỉ hỗ trợ vendor media type của đối tác. Request/response dùng media type đó sẽ được xử lý bằng partnerJsonMapper; các endpoint dùng application/json tiếp tục đi theo converter phù hợp với chính sách mặc định.

Media type là một phần của hợp đồng HTTP. Nếu cả hai converter cùng nhận application/json, thứ tự converter có thể ảnh hưởng đến mapper được chọn. Không nên thêm converter hỗ trợ mọi JSON rồi kỳ vọng Spring tự suy ra endpoint nào cần chính sách nào.

### 5.3. Nếu cùng media type nhưng khác endpoint

Một số hệ thống không thể thay đổi media type vì hợp đồng bên ngoài đã cố định application/json. Khi đó, có thể cân nhắc:

- Dùng DTO riêng và @JsonView hoặc @JsonFilter nếu khác biệt chỉ nằm ở tập field được xuất.
- Dùng converter/argument resolver tùy chỉnh có điều kiện theo endpoint.
- Đưa việc parse/serialize qua adapter rõ ràng trong controller hoặc tầng tích hợp.
- Tách service boundary hoặc ứng dụng con nếu hai chính sách thực sự là hai giao thức khác nhau.

Không nên dựa vào thứ tự converter toàn cục để đoán route. Nếu cùng một content type và cùng kiểu DTO nhưng cần hai format khác nhau, cần có một tín hiệu chọn chính sách rõ ràng và được kiểm thử.

## 6. Dùng nhiều mapper cho WebClient và tích hợp outbound

Một ứng dụng có thể gọi nhiều hệ thống đối tác. Mỗi WebClient có thể được cấu hình codec riêng, dùng mapper tương ứng với hợp đồng của hệ thống đích.

Ví dụ với Spring WebFlux:

~~~java
import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.codec.json.Jackson2JsonDecoder;
import org.springframework.http.codec.json.Jackson2JsonEncoder;
import org.springframework.web.reactive.function.client.ExchangeStrategies;
import org.springframework.web.reactive.function.client.WebClient;

@Configuration
public class PartnerWebClientConfiguration {

    @Bean
    public WebClient partnerWebClient(
        @Qualifier("partnerJsonMapper") ObjectMapper partnerMapper
    ) {
        ExchangeStrategies strategies = ExchangeStrategies.builder()
            .codecs(codecs -> {
                codecs.defaultCodecs().jackson2JsonEncoder(
                    new Jackson2JsonEncoder(partnerMapper)
                );
                codecs.defaultCodecs().jackson2JsonDecoder(
                    new Jackson2JsonDecoder(partnerMapper)
                );
            })
            .build();

        return WebClient.builder()
            .baseUrl("https://partner.example")
            .exchangeStrategies(strategies)
            .build();
    }
}
~~~

Đây là cấu hình minh họa; base URL phải lấy từ cấu hình môi trường của ứng dụng. WebClient này dùng mapper đối tác cho cả chiều ghi request và đọc response. Một WebClient khác có thể dùng mapper nội bộ hoặc mapper của nhà cung cấp khác.

Không nên dùng một WebClient toàn cục cho mọi đối tác nếu mỗi đối tác có naming strategy, date format hoặc custom serializer khác nhau. Đặt tên bean theo đối tác hoặc hợp đồng giúp việc inject và kiểm thử rõ ràng.

## 7. Chọn mức cấu hình phù hợp

Không phải mọi khác biệt cần một mapper riêng. Có thể dùng cây quyết định sau:

~~~text
Hai luồng JSON có cùng hợp đồng và module?
                  |
             +----+----+
             |         |
            Có        Không
             |         |
             v         v
     Khác biệt chỉ ở   Tạo mapper riêng
     feature đọc/ghi?  theo hợp đồng
             |
        +----+----+
        |         |
       Có        Không
        |         |
        v         v
   ObjectReader/  Xem xét mapper
   ObjectWriter   riêng hoặc DTO
~~~

### 7.1. Chỉ khác format output

Nếu chỉ khác pretty-print, root type hoặc một feature ghi, dùng ObjectWriter.

~~~java
ObjectWriter auditWriter = mapper
    .writerFor(AuditEvent.class)
    .with(SerializationFeature.INDENT_OUTPUT);
~~~

### 7.2. Chỉ khác chế độ đọc

Nếu chỉ khác việc chấp nhận field không biết, dùng ObjectReader.

~~~java
ObjectReader tolerantReader = mapper
    .readerFor(WebhookEvent.class)
    .without(DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES);
~~~

### 7.3. Khác naming strategy hoặc module

Nếu một hợp đồng dùng snake_case, một hợp đồng dùng camelCase, hoặc cần serializer/deserializer khác nhau, mapper riêng thường dễ hiểu hơn.

### 7.4. Khác tập field được công bố

Nếu cùng một object có các view dữ liệu khác nhau, hãy ưu tiên DTO riêng cho API quan trọng. @JsonView hoặc @JsonFilter có thể phù hợp với một số trường hợp, nhưng phải có test xác nhận field nào được xuất. Đừng dùng mapper riêng như cách che giấu field nhạy cảm trong một Entity không được thiết kế cho response.

## 8. Bảo mật và ranh giới tin cậy

Nhiều mapper không tự động làm ứng dụng an toàn hơn. Mỗi chính sách phải phản ánh ranh giới tin cậy.

### 8.1. Không dùng mapper permissive cho mọi luồng

Webhook có thể cần bỏ qua field chưa biết để tương thích khi nhà cung cấp thêm thuộc tính. Điều đó không có nghĩa request nội bộ cũng nên bỏ qua field lạ.

Ví dụ, nếu API nội bộ nhận sai tên field do client gửi nhầm, chế độ strict có thể giúp phát hiện lỗi sớm. Nếu mapper bỏ qua mọi field lạ, request có thể được xử lý với giá trị mặc định mà không ai nhận ra.

Hãy chọn FAIL_ON_UNKNOWN_PROPERTIES theo hợp đồng và test trường hợp field lạ.

### 8.2. Không bật polymorphic typing rộng cho input bên ngoài

Polymorphic deserialization có thể hữu ích khi hợp đồng có nhiều subtype rõ ràng. Tuy nhiên, không bật default typing rộng cho dữ liệu từ HTTP, webhook, file upload hoặc message broker không tin cậy.

Nếu cần subtype, hãy định nghĩa allowlist bằng annotation hoặc cấu hình subtype cụ thể, kiểm tra kiểu được phép và test payload không hợp lệ. Một mapper riêng cho đối tác nên có ranh giới kiểu dữ liệu rõ ràng.

### 8.3. Không dùng serializer để che giấu dữ liệu nhạy cảm

Không nên serialize Entity có passwordHash, accessToken, internalNote rồi kỳ vọng một custom serializer toàn cục sẽ luôn loại bỏ đúng field. Hãy dùng DTO chỉ chứa field được phép công bố.

Mapper và view/filter có thể hỗ trợ biểu diễn, nhưng ranh giới dữ liệu an toàn nên bắt đầu từ kiểu dữ liệu được truyền ra ngoài.

### 8.4. Không chia sẻ custom module có trạng thái mutable

Module và serializer thường được chia sẻ giữa nhiều mapper. Tránh giữ trạng thái thay đổi theo request bên trong serializer/deserializer. Nếu cần context theo từng lần xử lý, dùng SerializerProvider/DeserializationContext, ContextAttributes hoặc một adapter rõ ràng, không lưu dữ liệu request vào field của serializer dùng chung.

## 9. Kiểm thử từng chính sách JSON

Mỗi mapper hoặc reader/writer quan trọng nên có test thể hiện hợp đồng. Không chỉ test rằng JSON parse thành công; cần xác nhận field, naming, null, ngày giờ và hành vi với input không mong đợi.

### 9.1. Test naming strategy riêng

~~~java
@Test
void partnerMapperUsesSnakeCase() throws Exception {
    ObjectMapper mapper = createPartnerMapper(createInternalMapper());

    PartnerRequest request = new PartnerRequest("CUS-10", "new");

    String json = mapper.writeValueAsString(request);

    assertTrue(json.contains("\"customer_id\""));
    assertFalse(json.contains("\"customerId\""));
}
~~~

Test này xác nhận chính sách đối tác thực sự xuất snake_case. Nếu chỉ test mapper được tạo thành công, sẽ không phát hiện trường hợp converter đang dùng mapper khác.

### 9.2. Test field không biết theo từng hợp đồng

~~~java
@Test
void webhookReaderAcceptsUnknownFields() throws Exception {
    ObjectReader reader = mapper
        .readerFor(WebhookEvent.class)
        .without(DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES);

    WebhookEvent event = reader.readValue("""
        {
          "eventId": "EVT-1",
          "newProviderField": "future-value"
        }
        """);

    assertEquals("EVT-1", event.eventId());
}
~~~

Trong khi đó, test cho API nội bộ có thể xác nhận field lạ bị từ chối. Hai test thể hiện hai chính sách khác nhau một cách có chủ đích.

### 9.3. Test converter hoặc client tích hợp

Với Spring MVC, nên dùng MockMvc để gửi request có Content-Type cụ thể và kiểm tra JSON trả về. Với WebClient, có thể dùng mock HTTP server hoặc ExchangeFunction giả lập để xác nhận request body và response body được chuyển đổi đúng.

Các test tích hợp giúp phát hiện lỗi thường gặp: mapper bean đúng nhưng converter/codec vẫn dùng mapper mặc định.

### 9.4. Test tương thích theo phiên bản hợp đồng

Nếu API đã được sử dụng bởi client bên ngoài, hãy lưu một số JSON mẫu đại diện cho phiên bản hợp đồng đã phát hành. Khi thay mapper, module hoặc serializer, chạy lại test để xác nhận không thay đổi field hoặc format ngoài dự kiến.

## 10. Những lỗi thiết kế thường gặp

| Lỗi | Hậu quả | Cách tổ chức phù hợp |
|---|---|---|
| Một ObjectMapper bị thay đổi feature theo từng request | Request khác có thể chịu cấu hình ngoài ý muốn | Dùng reader/writer hoặc mapper riêng |
| Tạo mapper mới ở mỗi controller/service | Cấu hình phân tán, khó đồng nhất và tốn chi phí khởi tạo | Đăng ký mapper thành bean dùng chung |
| Nhiều bean ObjectMapper nhưng inject không có Qualifier | Ambiguous dependency hoặc chọn nhầm Primary | Đặt tên bean và dùng Qualifier rõ ràng |
| Thêm converter hỗ trợ mọi application/json | Converter có thể bắt request ngoài dự kiến | Dùng media type riêng hoặc điều kiện chọn rõ ràng |
| Dùng mapper đối tác để đọc dữ liệu nội bộ | Chính sách permissive hoặc naming có thể che lỗi | Tách mapper theo ranh giới |
| Dùng Entity cho nhiều hợp đồng JSON | Field nội bộ và quan hệ ORM bị lộ | Dùng DTO/storage model riêng |
| Dùng một custom serializer có trạng thái theo request | Lỗi race condition và dữ liệu chéo request | Serializer stateless, context theo lần xử lý |
| Tạo quá nhiều mapper cho khác biệt nhỏ | Cấu hình và test khó bảo trì | Dùng ObjectReader/ObjectWriter khi phù hợp |

## 11. Quy trình thêm một chính sách JSON mới

Khi tích hợp một hệ thống mới, có thể làm theo quy trình:

1. **Xác định hợp đồng:** lấy payload mẫu, media type, tên field, date/time format và quy tắc null/unknown field.
2. **Tạo DTO riêng:** mô hình hóa đúng dữ liệu đầu vào/đầu ra của hệ thống đó.
3. **So sánh chính sách hiện có:** xác định có thể dùng mapper hiện tại với reader/writer hay cần mapper riêng.
4. **Khai báo mapper bean:** đặt tên theo hợp đồng, cấu hình module và feature một lần khi khởi động.
5. **Gắn vào adapter:** dùng Qualifier, HTTP converter hoặc WebClient codec phù hợp.
6. **Viết contract test:** xác nhận JSON thực tế và hành vi với dữ liệu không hợp lệ.
7. **Kiểm tra dependency graph:** bảo đảm các module Jackson tương thích và không có version override ngoài ý muốn.
8. **Theo dõi thay đổi hợp đồng:** khi đối tác nâng version, cập nhật DTO và test theo version được hỗ trợ.

Không nên thêm mapper mới trước khi biết hợp đồng khác nhau ở điểm nào. Việc tạo mapper là kết quả của thiết kế policy, không phải bước đầu tiên.

## 12. Ví dụ tổng hợp: API công khai và đối tác cùng dùng JSON

Giả sử ứng dụng có hai endpoint:

- API công khai dùng camelCase, chỉ trả PublicOrderResponse.
- API đối tác dùng snake_case, chấp nhận field chưa biết và dùng PartnerOrderRequest.

Có thể tổ chức:

~~~text
src/main/java
└── integration
    ├── json
    │   ├── JsonMapperConfiguration.java
    │   ├── PartnerJsonHttpConfiguration.java
    │   └── PartnerWebClientConfiguration.java
    ├── publicapi
    │   ├── PublicOrderController.java
    │   └── PublicOrderResponse.java
    └── partner
        ├── PartnerOrderController.java
        ├── PartnerOrderRequest.java
        ├── PartnerOrderResponse.java
        └── PartnerPayloadAdapter.java
~~~

Mapper được tạo một lần:

~~~java
@Bean("publicApiMapper")
@Primary
ObjectMapper publicApiMapper() {
    return JsonMapper.builder()
        .addModule(new JavaTimeModule())
        .build();
}

@Bean("partnerApiMapper")
ObjectMapper partnerApiMapper(
    @Qualifier("publicApiMapper") ObjectMapper publicMapper
) {
    ObjectMapper mapper = publicMapper.copy();
    mapper.setPropertyNamingStrategy(PropertyNamingStrategies.SNAKE_CASE);
    mapper.configure(
        DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES,
        false
    );
    return mapper;
}
~~~

Controller công khai nhận và trả DTO công khai. Controller đối tác được gắn với converter có media type của đối tác hoặc dùng adapter để parse payload bằng partnerApiMapper. Adapter outbound dùng WebClient riêng với mapper tương ứng.

Khi đối tác thay đổi format, chỉ chính sách và test của đối tác cần được xem xét. Hợp đồng công khai vẫn có mapper, DTO và test riêng, nên thay đổi không lan sang API khác.

## 13. Checklist trước khi đưa mapper mới vào ứng dụng

- [ ] Đã xác định hợp đồng và chủ sở hữu của JSON.
- [ ] Đã phân biệt chiều đọc và chiều ghi.
- [ ] Đã xác định khác biệt có thể xử lý bằng ObjectReader/ObjectWriter hay cần mapper riêng.
- [ ] DTO không mang theo field nội bộ ngoài hợp đồng.
- [ ] Mapper có tên bean rõ ràng và được inject bằng Qualifier.
- [ ] Module và dependency phiên bản tương thích.
- [ ] Mapper được cấu hình hoàn tất trước khi dùng đồng thời.
- [ ] HTTP converter hoặc client codec thực sự dùng mapper đã chọn.
- [ ] Không bật polymorphic typing rộng cho input không tin cậy.
- [ ] Có test naming, null, unknown field, date/time và payload lỗi.
- [ ] Có test tích hợp chứng minh đúng converter/codec được chọn.
- [ ] Có test bảo vệ JSON của các hợp đồng đã phát hành.

Một ứng dụng có thể có nhiều bộ chính sách JSON mà vẫn dễ bảo trì nếu mỗi bộ được đặt tên, giới hạn theo hợp đồng và kiểm thử riêng. Hãy dùng ObjectReader/ObjectWriter cho những khác biệt nhỏ trong cùng một chính sách; dùng ObjectMapper riêng khi naming, module, format hoặc ranh giới tin cậy khác nhau đáng kể. Spring MVC và WebClient cần được gắn rõ mapper tương ứng, vì sự tồn tại của bean ObjectMapper chưa đủ để quyết định converter nào sẽ xử lý request.


