# Lỗi message converter khi thay cấu hình mặc định của Spring

Khi thay đổi danh sách HttpMessageConverter mặc định của Spring MVC, ứng dụng có thể vẫn khởi động và controller đơn giản vẫn chạy, nhưng OpenAPI endpoint hoặc Swagger UI lại lỗi. Triệu chứng thường thấy là Swagger UI báo không thể render definition, request /v3/api-docs trả HTTP 500, hoặc log có thông báo không tìm được converter để ghi response.

Nguyên nhân thường nằm ở danh sách converter đã bị thay thế hoặc sắp xếp không phù hợp. springdoc cần các converter thích hợp để trả tài liệu OpenAPI và cấu hình Swagger UI. FAQ của springdoc nêu rõ: khi override converter mặc định do Spring đăng ký, cần có ByteArrayHttpMessageConverter và converter JSON tương ứng; thứ tự đăng ký cũng quan trọng.

Với Spring Boot 3 và Spring Framework 6, converter JSON thường là MappingJackson2HttpMessageConverter. Với Spring Boot 4 và Spring Framework 7, stack mặc định chuyển sang Jackson 3 và JacksonJsonHttpMessageConverter. Hãy dùng đúng lớp theo phiên bản dependency của ứng dụng.

## 1. HttpMessageConverter làm nhiệm vụ gì?

Trong Spring MVC, HttpMessageConverter đọc request body thành đối tượng Java và ghi đối tượng Java thành HTTP response body. Spring chọn converter dựa trên kiểu dữ liệu, media type và danh sách converter đã đăng ký.

Ví dụ:

| HTTP trao đổi | Converter thường tham gia |
| --- | --- |
| JSON request thành DTO | Jackson JSON converter |
| DTO thành JSON response | Jackson JSON converter |
| Byte array thành response | ByteArrayHttpMessageConverter |
| String thành text response | StringHttpMessageConverter |
| Form URL encoded | FormHttpMessageConverter |
| Multipart upload | AllEncompassingFormHttpMessageConverter và converter cho từng part |
| Resource hoặc file response | ResourceHttpMessageConverter |

Spring Boot tự cấu hình một danh sách converter phù hợp với dependency trên classpath. Nếu ứng dụng có Jackson, các object thường được đọc/ghi dưới dạng JSON. Nếu có module XML phù hợp, ứng dụng có thể hỗ trợ XML. String mặc định được ghi bằng UTF-8.

Converter không phải là Converter<S,T> dùng để chuyển đổi giá trị trong @PathVariable hoặc @RequestParam. HttpMessageConverter xử lý body HTTP; Converter, Formatter và ConversionService xử lý chuyển đổi giá trị binding.

## 2. Spring chọn converter theo Content-Type và Accept

Hai header cần phân biệt:

- Content-Type: định dạng của body request mà client gửi lên. Spring dùng nó để chọn converter đọc request.
- Accept: định dạng response mà client chấp nhận. Spring dùng nó cùng kiểu trả về và produces để chọn converter ghi response.

Ví dụ client gửi JSON và muốn nhận JSON:

~~~http
POST /api/orders HTTP/1.1
Content-Type: application/json
Accept: application/json

{"customerId":"C-100"}
~~~

Controller nhận DTO và trả DTO:

~~~java
@PostMapping(
    path = "/api/orders",
    consumes = MediaType.APPLICATION_JSON_VALUE,
    produces = MediaType.APPLICATION_JSON_VALUE
)
public OrderResponse create(@RequestBody CreateOrderRequest request) {
    return orderService.create(request);
}
~~~

Spring cần converter có thể đọc CreateOrderRequest từ application/json và converter có thể ghi OrderResponse thành application/json. Nếu không có converter phù hợp, request hoặc response sẽ thất bại dù method controller được gọi đúng.

/v3/api-docs cũng là HTTP endpoint. springdoc tạo OpenAPI model rồi Spring MVC phải ghi model đó thành response body. Vì vậy, cấu hình converter của ứng dụng ảnh hưởng trực tiếp đến việc Swagger UI tải được đặc tả.

## 3. Dấu hiệu lỗi converter làm hỏng springdoc

Các triệu chứng thường gặp:

| Triệu chứng | Điều cần kiểm tra |
| --- | --- |
| Swagger UI hiện “Unable to render definition” | Network request đến /v3/api-docs và /v3/api-docs/swagger-config |
| /v3/api-docs trả 500 | Log HttpMessageNotWritableException, No converter for ... hoặc lỗi serialize |
| /v3/api-docs trả JSON nhưng Swagger UI không tải được | Kiểm tra swagger-config, Content-Type, response body và URL được cấu hình |
| API nhận JSON trả 415 | Không có converter đọc Content-Type của request hoặc consumes không khớp |
| API trả 406 | Không có converter ghi response theo Accept/produces |
| Response lỗi chỉ xuất hiện sau khi thêm converter riêng | Converter mới có thể nhận media type quá rộng hoặc đứng sai thứ tự |
| File/byte response bị lỗi sau khi thay converter | Kiểm tra ByteArrayHttpMessageConverter và ResourceHttpMessageConverter |

Một lỗi điển hình trong log:

~~~text
HttpMessageNotWritableException:
No converter for [class ...] with preset Content-Type 'application/json'
~~~

Thông báo này có nghĩa Spring không tìm thấy converter có thể ghi kiểu dữ liệu đang trả về với content type đã chọn. Không nên chỉ sửa controller hoặc annotation OpenAPI trước khi kiểm tra danh sách converter.

## 4. Vì sao thay converter mặc định có thể làm Swagger UI hỏng?

Trong Spring MVC, configureMessageConverters là hook để cấu hình danh sách converter. Khi ứng dụng tự thêm converter vào danh sách này, hành vi mặc định có thể bị thay đổi. Nếu danh sách mới chỉ có converter JSON, các converter khác như byte array, string, resource hoặc form có thể không còn được đăng ký theo cách trước đó.

springdoc FAQ có một trường hợp cụ thể: Swagger UI không thể render definition khi ứng dụng override HttpMessageConverter mặc định do Spring đăng ký. Hướng dẫn của springdoc yêu cầu đăng ký cả:

- ByteArrayHttpMessageConverter
- MappingJackson2HttpMessageConverter với ObjectMapper phù hợp

Ví dụ theo hướng dẫn springdoc dành cho stack Jackson 2:

~~~java
converters.add(new ByteArrayHttpMessageConverter());
converters.add(new MappingJackson2HttpMessageConverter(jacksonBuilder.build()));
~~~

Hai converter phục vụ hai kiểu body khác nhau. ByteArrayHttpMessageConverter đọc/ghi byte[]; Jackson converter đọc/ghi object JSON. Nếu thay danh sách converter mà bỏ một trong hai, một số response của springdoc có thể không được ghi đúng.

Thứ tự cũng quan trọng. Spring thử các converter theo thứ tự đăng ký và chọn converter phù hợp đầu tiên. Một converter custom hỗ trợ */* hoặc nhiều media type rộng có thể nhận response trước converter chuyên biệt. Khi thêm converter, hãy kiểm tra canRead, canWrite, supportedMediaTypes và vị trí của nó trong danh sách.

## 5. Phân biệt configureMessageConverters và extendMessageConverters

Hai method có mục tiêu khác nhau:

| Method | Ý nghĩa | Khi nào dùng |
| --- | --- | --- |
| configureMessageConverters | Tự cấu hình danh sách converter | Khi chủ động thay thế toàn bộ danh sách và chịu trách nhiệm đăng ký đầy đủ converter cần thiết |
| extendMessageConverters | Sửa hoặc bổ sung sau khi danh sách đã được tạo | Khi chỉ muốn thêm converter hoặc điều chỉnh converter mặc định |

Trong Spring Framework, configureMessageConverters nhận danh sách ban đầu rỗng. Nếu thêm converter tại đây, việc đăng ký converter mặc định của Spring Framework có thể bị tắt. extendMessageConverters được gọi sau khi danh sách đã được cấu hình và là điểm phù hợp hơn để bổ sung converter mà vẫn giữ các converter mặc định.

Trong Spring Boot, auto-configuration còn đóng góp các converter bean và converter mặc định. Tuy nhiên, đừng dựa vào khác biệt nội bộ giữa các phiên bản để thay toàn bộ danh sách một cách vô tình. Với nhu cầu thông thường, ưu tiên cơ chế bổ sung của Spring Boot hoặc extendMessageConverters.

## 6. Cách sửa ưu tiên: giữ cấu hình MVC mặc định và mở rộng converter

Nếu chỉ cần thêm một converter cho định dạng riêng, hãy dùng extendMessageConverters:

~~~java
import java.util.List;

import org.springframework.context.annotation.Configuration;
import org.springframework.http.converter.HttpMessageConverter;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

@Configuration
class WebConfiguration implements WebMvcConfigurer {

    @Override
    public void extendMessageConverters(
            List<HttpMessageConverter<?>> converters) {
        converters.add(0, new VendorDocumentHttpMessageConverter());
    }
}
~~~

VendorDocumentHttpMessageConverter là converter riêng của ứng dụng. Đặt nó ở vị trí đầu chỉ khi nó có media type hẹp và không chiếm các loại nội dung mà converter khác xử lý. Nếu converter hỗ trợ */*, không nên đặt trước converter JSON hoặc byte array mà không kiểm tra tác động.

Khi chỉ muốn sửa ObjectMapper của JSON converter hiện có, có thể tìm converter Jackson đã được đăng ký và cấu hình nó thay vì tạo một danh sách hoàn toàn mới:

~~~java
import java.util.List;

import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.converter.HttpMessageConverter;
import org.springframework.http.converter.json.MappingJackson2HttpMessageConverter;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

@Configuration
class JacksonMvcConfiguration implements WebMvcConfigurer {

    private final ObjectMapper objectMapper;

    JacksonMvcConfiguration(ObjectMapper objectMapper) {
        this.objectMapper = objectMapper;
    }

    @Override
    public void extendMessageConverters(
            List<HttpMessageConverter<?>> converters) {
        for (HttpMessageConverter<?> converter : converters) {
            if (converter instanceof MappingJackson2HttpMessageConverter jackson) {
                jackson.setObjectMapper(objectMapper);
            }
        }
    }
}
~~~

Ví dụ này dành cho Spring Boot 3 / Spring Framework 6 với Jackson 2. Danh sách converter mặc định vẫn được Spring Boot tạo trước; code chỉ thay ObjectMapper của converter Jackson hiện có.

Nếu ứng dụng có nhiều Jackson converter cho media type khác nhau, chỉ thay những converter thực sự cần dùng chung mapper. Đừng giả định chỉ có đúng một converter nếu ứng dụng hỗ trợ JSON, XML hoặc vendor media type.

## 7. Bảo đảm ByteArrayHttpMessageConverter có mặt

Khi tự kiểm soát danh sách converter, kiểm tra sự hiện diện của byte-array converter. Ví dụ dưới đây dành cho Spring MVC với Jackson 2:

~~~java
import java.util.List;

import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.converter.ByteArrayHttpMessageConverter;
import org.springframework.http.converter.HttpMessageConverter;
import org.springframework.http.converter.json.MappingJackson2HttpMessageConverter;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

@Configuration
class OpenApiConverterConfiguration implements WebMvcConfigurer {

    private final ObjectMapper objectMapper;

    OpenApiConverterConfiguration(ObjectMapper objectMapper) {
        this.objectMapper = objectMapper;
    }

    @Override
    public void extendMessageConverters(
            List<HttpMessageConverter<?>> converters) {
        boolean hasByteArray = false;
        boolean hasJacksonJson = false;

        for (HttpMessageConverter<?> converter : converters) {
            if (converter instanceof ByteArrayHttpMessageConverter) {
                hasByteArray = true;
            }
            if (converter instanceof MappingJackson2HttpMessageConverter jackson) {
                jackson.setObjectMapper(objectMapper);
                hasJacksonJson = true;
            }
        }

        if (!hasByteArray) {
            converters.add(0, new ByteArrayHttpMessageConverter());
        }

        if (!hasJacksonJson) {
            converters.add(new MappingJackson2HttpMessageConverter(objectMapper));
        }
    }
}
~~~

Đây là cách kiểm tra/bổ sung cho danh sách đã được Spring MVC cấu hình. Nó không thay thế toàn bộ converter khác. Nếu danh sách ban đầu rỗng vì ứng dụng chủ động tắt auto-configuration, chỉ thêm hai converter trên có thể chưa đủ cho toàn bộ controller; cần khôi phục cấu hình MVC phù hợp hoặc đăng ký đầy đủ converter cần thiết.

Đừng thêm converter trùng lặp một cách máy móc. Trước tiên hãy kiểm tra danh sách hiện tại, sau đó chỉ bổ sung khi thiếu. Converter trùng có thể làm lựa chọn phụ thuộc thứ tự và gây khó hiểu khi debug.

## 8. Nếu dùng configureMessageConverters để thay toàn bộ danh sách

Chỉ dùng cách này khi ứng dụng chủ động quản lý toàn bộ danh sách converter. Ví dụ tối thiểu cho một ứng dụng Spring MVC có yêu cầu rất cụ thể:

~~~java
import java.nio.charset.StandardCharsets;
import java.util.List;

import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.converter.ByteArrayHttpMessageConverter;
import org.springframework.http.converter.HttpMessageConverter;
import org.springframework.http.converter.ResourceHttpMessageConverter;
import org.springframework.http.converter.StringHttpMessageConverter;
import org.springframework.http.converter.json.MappingJackson2HttpMessageConverter;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

@Configuration
class CompleteMvcConverterConfiguration implements WebMvcConfigurer {

    private final ObjectMapper objectMapper;

    CompleteMvcConverterConfiguration(ObjectMapper objectMapper) {
        this.objectMapper = objectMapper;
    }

    @Override
    public void configureMessageConverters(
            List<HttpMessageConverter<?>> converters) {
        converters.add(new ByteArrayHttpMessageConverter());
        converters.add(new StringHttpMessageConverter(StandardCharsets.UTF_8));
        converters.add(new ResourceHttpMessageConverter());
        converters.add(new MappingJackson2HttpMessageConverter(objectMapper));
    }
}
~~~

Đây chỉ là ví dụ rút gọn, không phải danh sách đầy đủ cho mọi ứng dụng. Tùy nhu cầu còn có form, multipart, XML, source, feed hoặc converter cho định dạng riêng. Nếu thay thế danh sách, bạn phải chịu trách nhiệm cho mọi request/response mà ứng dụng cần hỗ trợ, kể cả các endpoint springdoc và Swagger UI.

Nếu mục tiêu chỉ là thêm một converter, không nên dùng configureMessageConverters theo cách này. Dùng extendMessageConverters hoặc cơ chế HttpMessageConverters của đúng phiên bản Spring Boot.

## 9. Dùng HttpMessageConverters trong Spring Boot 3

Spring Boot 3.x có class org.springframework.boot.autoconfigure.http.HttpMessageConverters. Cơ chế này cho phép đóng góp converter bổ sung trong khi giữ các converter mặc định:

~~~java
import org.springframework.boot.autoconfigure.http.HttpMessageConverters;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.converter.HttpMessageConverter;

@Configuration(proxyBeanMethods = false)
class BootHttpConvertersConfiguration {

    @Bean
    HttpMessageConverters customConverters() {
        HttpMessageConverter<?> custom =
            new VendorDocumentHttpMessageConverter();
        return new HttpMessageConverters(custom);
    }
}
~~~

Trong Spring Boot 3.5, constructor nhận converter bổ sung sẽ đặt converter custom cạnh converter mặc định tương ứng hoặc trước danh sách khi không tìm thấy loại tương ứng. Có thể kế thừa HttpMessageConverters và override postProcessConverters nếu cần tinh chỉnh thứ tự hoặc loại bỏ converter mặc định.

Không tạo bean HttpMessageConverters với cờ addDefaultConverters=false nếu chưa có lý do rõ ràng và chưa tự đăng ký đầy đủ converter cần thiết. Làm vậy có thể tái tạo đúng lỗi khiến OpenAPI endpoint không ghi được response.

## 10. Tùy chỉnh Jackson mà không thay toàn bộ converter

Nếu nhu cầu chỉ là format ngày, inclusion hoặc module Jackson, hãy cấu hình builder/mapper theo cơ chế của Spring Boot thay vì tự tạo danh sách converter mới.

Ví dụ với Spring Boot 3 và Jackson 2:

~~~java
import com.fasterxml.jackson.annotation.JsonInclude;
import org.springframework.boot.autoconfigure.jackson.Jackson2ObjectMapperBuilderCustomizer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class JacksonConfiguration {

    @Bean
    Jackson2ObjectMapperBuilderCustomizer jacksonCustomizer() {
        return builder -> builder.serializationInclusion(
            JsonInclude.Include.NON_NULL
        );
    }
}
~~~

Jackson2ObjectMapperBuilderCustomizer điều chỉnh builder mà Spring Boot dùng để tạo mapper. Các converter JSON tiếp tục sử dụng mapper được cấu hình theo cơ chế Boot. Sau khi đổi serialization rule, vẫn cần kiểm tra response API và OpenAPI document vì cùng mapper có thể ảnh hưởng nhiều endpoint.

Không tạo một ObjectMapper mới với cấu hình thiếu module chỉ để giải quyết lỗi converter. Mapper tùy chỉnh có thể làm mất hỗ trợ Java Time, Kotlin, Optional, parameter names hoặc các serializer mà ứng dụng đang dựa vào.

## 11. Lưu ý Spring Boot 4 và Jackson 3

Spring Boot 4 chuyển sang Jackson 3 làm JSON stack mặc định. Vì vậy, ví dụ dùng MappingJackson2HttpMessageConverter và Jackson2ObjectMapperBuilderCustomizer thuộc thế hệ Jackson 2; không sao chép nguyên xi vào ứng dụng Boot 4.

Trong Spring Boot 4, converter JSON mặc định là JacksonJsonHttpMessageConverter, sử dụng tools.jackson.databind.json.JsonMapper. Spring Boot cung cấp ServerHttpMessageConvertersCustomizer để tùy chỉnh converter phía server.

Ví dụ thay JSON converter trong Boot 4:

~~~java
import org.springframework.boot.http.converter.autoconfigure.ServerHttpMessageConvertersCustomizer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.converter.json.JacksonJsonHttpMessageConverter;
import tools.jackson.databind.json.JsonMapper;

@Configuration(proxyBeanMethods = false)
class Boot4JsonConverterConfiguration {

    @Bean
    ServerHttpMessageConvertersCustomizer serverJsonCustomizer() {
        JsonMapper jsonMapper = JsonMapper.builder().build();
        return builder -> builder.withJsonConverter(
            new JacksonJsonHttpMessageConverter(jsonMapper)
        );
    }
}
~~~

Nếu cần thêm converter byte array trong Boot 4, dùng cùng builder:

~~~java
return builder
    .addCustomConverter(new ByteArrayHttpMessageConverter())
    .withJsonConverter(new JacksonJsonHttpMessageConverter(jsonMapper));
~~~

API builder và package có thể thay đổi theo minor version; hãy đối chiếu Spring Boot reference của đúng version đang dùng. FAQ springdoc hiện có ví dụ MappingJackson2HttpMessageConverter cho trường hợp Jackson 2, nhưng không nên áp dụng lớp Jackson 2 vào Boot 4 nếu ứng dụng đã chuyển sang Jackson 3.

Quy tắc chọn dependency:

| Spring Boot | Spring Framework | springdoc-openapi | JSON converter mặc định thường gặp |
| --- | --- | --- | --- |
| 2.x | 5.x | springdoc 1.x | MappingJackson2HttpMessageConverter |
| 3.x | 6.x | springdoc 2.x | MappingJackson2HttpMessageConverter |
| 4.x | 7.x | springdoc 3.x | JacksonJsonHttpMessageConverter |

Đây là định hướng theo major version. Kiểm tra compatibility matrix chính thức trước khi nâng cấp hoặc chọn version cụ thể.

## 12. Không thêm @EnableWebMvc chỉ để sửa converter

Trong Spring Boot, @EnableWebMvc báo rằng ứng dụng muốn tự kiểm soát cấu hình Spring MVC. Khi thêm annotation này, bạn có thể làm mất một số auto-configuration của Boot như static resources, WebJars và các tích hợp MVC mặc định.

Nếu chỉ muốn thêm interceptor, formatter, resource handler hoặc converter, hãy khai báo WebMvcConfigurer mà không gắn @EnableWebMvc:

~~~java
@Configuration
class WebConfiguration implements WebMvcConfigurer {
    // Chỉ override hook cần thiết.
}
~~~

Chỉ dùng @EnableWebMvc khi chủ đích tiếp quản cấu hình MVC và đã tự cấu hình đầy đủ những thành phần cần thiết. Việc thêm annotation này để sửa lỗi Swagger UI có thể tạo thêm vấn đề ở static resource, welcome page hoặc các endpoint khác.

## 13. Kiểm tra thứ tự converter và media type

Spring duyệt danh sách converter theo thứ tự. Converter đứng trước có thể được chọn trước nếu nó hỗ trợ Java type và media type của response. Khi client gửi Accept: */*, nhiều converter có thể cùng phù hợp, nên thứ tự càng quan trọng.

Một converter custom nên khai báo media type hẹp:

~~~java
public VendorDocumentHttpMessageConverter() {
    setSupportedMediaTypes(
        List.of(MediaType.valueOf("application/vnd.example.document+json"))
    );
}
~~~

Không khai báo MediaType.ALL nếu converter chỉ xử lý một định dạng cụ thể. Nếu converter cần hỗ trợ nhiều media type, hãy xác định rõ loại Java mà nó đọc/ghi và kiểm tra thứ tự so với Jackson, byte array, string và resource converters.

Sau khi thay thứ tự, thử cả request JSON thông thường và endpoint OpenAPI. Đừng chỉ thử một controller trả DTO đơn giản vì nó có thể không đi qua cùng nhánh xử lý như byte array hoặc swagger-config.

## 14. Phân biệt lỗi converter với lỗi content negotiation

Các status HTTP gợi ý hướng điều tra:

| Status/lỗi | Ý nghĩa thường gặp | Kiểm tra |
| --- | --- | --- |
| 400 / HttpMessageNotReadableException | Converter đã đọc request nhưng body không hợp lệ hoặc không deserialize được | JSON syntax, DTO type, Jackson module |
| 406 / HttpMediaTypeNotAcceptableException | Không ghi được response theo Accept hoặc produces | Supported media types, converter canWrite |
| 415 / HttpMediaTypeNotSupportedException | Không đọc được request Content-Type | Converter canRead, consumes, request header |
| 500 / HttpMessageNotWritableException | Không serialize/ghi được response | Converter cho kiểu trả về, mapper và content type |
| Swagger UI không render | Tài liệu hoặc swagger-config không tải được/không phải OpenAPI JSON hợp lệ | Network response, HTTP status, Content-Type và body |

Không phải mọi lỗi Swagger UI đều do converter. Nếu /v3/api-docs trả 401/403, hãy kiểm tra Spring Security. Nếu trả 404, kiểm tra springdoc.api-docs.path, context path hoặc việc bật/tắt springdoc. Nếu trả 200 nhưng body là trang HTML login, vấn đề nằm ở security redirect hoặc proxy chứ không phải JSON converter.

## 15. Kiểm tra endpoint OpenAPI bằng curl

Đầu tiên kiểm tra JSON endpoint trực tiếp:

~~~bash
curl -i \
  -H "Accept: application/json" \
  http://localhost:8080/v3/api-docs
~~~

Response thành công phải có status 200 và body JSON chứa field openapi, info, paths theo document được sinh.

Kiểm tra swagger-config:

~~~bash
curl -i \
  -H "Accept: application/json" \
  http://localhost:8080/v3/api-docs/swagger-config
~~~

Nếu Swagger UI mở được trang HTML nhưng không render API, kiểm tra hai request này trong tab Network của trình duyệt. Phân biệt file JavaScript/CSS tĩnh với endpoint cấu hình và OpenAPI động.

Kiểm tra YAML nếu ứng dụng bật endpoint YAML:

~~~bash
curl -i \
  -H "Accept: application/yaml" \
  http://localhost:8080/v3/api-docs.yaml
~~~

Nếu JSON hoạt động nhưng YAML lỗi, kiểm tra cấu hình và hỗ trợ YAML riêng; đừng kết luận mọi converter JSON đều bị hỏng.

## 16. Kiểm tra danh sách converter trong ứng dụng

Có thể log loại converter, thứ tự và media type được hỗ trợ trong extendMessageConverters:

~~~java
@Override
public void extendMessageConverters(
        List<HttpMessageConverter<?>> converters) {
    for (int index = 0; index < converters.size(); index++) {
        HttpMessageConverter<?> converter = converters.get(index);
        log.info(
            "HTTP converter [{}]: {} supports {}",
            index,
            converter.getClass().getName(),
            converter.getSupportedMediaTypes()
        );
    }
}
~~~

Ví dụ trên cần có logger của ứng dụng. Dùng log ở môi trường phát triển hoặc khi điều tra sự cố; tránh log quá nhiều trong production nếu danh sách không thay đổi.

Danh sách cần được rà soát theo mục tiêu:

- Có converter ghi JSON cho OpenAPI document.
- Có ByteArrayHttpMessageConverter khi springdoc FAQ yêu cầu cho cấu hình override.
- Có converter cho các kiểu response mà API thực tế đang trả.
- Media type và thứ tự không khiến converter rộng chiếm response của converter chuyên biệt.
- Không có converter custom làm thay đổi Content-Type ngoài ý muốn.

## 17. Kiểm thử OpenAPI endpoint bằng MockMvc

Sau khi sửa converter, thêm integration test để phát hiện lỗi tái xuất hiện. Test endpoint OpenAPI trực tiếp:

~~~java
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest
@AutoConfigureMockMvc
class OpenApiMessageConverterTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void writesOpenApiDocumentAsJson() throws Exception {
        mockMvc.perform(get("/v3/api-docs")
                .accept(MediaType.APPLICATION_JSON))
            .andExpect(status().isOk())
            .andExpect(content().contentTypeCompatibleWith(
                MediaType.APPLICATION_JSON
            ))
            .andExpect(jsonPath("$.openapi").exists())
            .andExpect(jsonPath("$.paths").isMap());
    }

    @Test
    void writesSwaggerConfigurationAsJson() throws Exception {
        mockMvc.perform(get("/v3/api-docs/swagger-config")
                .accept(MediaType.APPLICATION_JSON))
            .andExpect(status().isOk())
            .andExpect(content().contentTypeCompatibleWith(
                MediaType.APPLICATION_JSON
            ));
    }
}
~~~

Nếu ứng dụng có custom API docs path hoặc context path, thay URL test theo cấu hình thực tế. Nếu Spring Security bảo vệ tài liệu, thêm authentication hoặc cấu hình test security phù hợp; không tắt bảo mật production chỉ để test qua.

Test này kiểm tra cả nội dung JSON và swagger-config. Nếu chỉ kiểm tra controller nghiệp vụ, lỗi converter ở springdoc có thể không bị phát hiện.

## 18. Kiểm thử converter cho byte array và API thông thường

Ngoài OpenAPI endpoint, nên kiểm tra một endpoint trả file/byte array nếu ứng dụng có loại response đó:

~~~java
@GetMapping(
    path = "/api/reports/{id}/download",
    produces = MediaType.APPLICATION_OCTET_STREAM_VALUE
)
public ResponseEntity<byte[]> download(@PathVariable UUID id) {
    byte[] content = reportService.load(id);
    return ResponseEntity.ok()
        .contentType(MediaType.APPLICATION_OCTET_STREAM)
        .body(content);
}
~~~

Test:

~~~java
mockMvc.perform(get("/api/reports/{id}/download", reportId)
        .accept(MediaType.APPLICATION_OCTET_STREAM))
    .andExpect(status().isOk())
    .andExpect(content().contentTypeCompatibleWith(
        MediaType.APPLICATION_OCTET_STREAM
    ));
~~~

Nếu không có endpoint file trong ứng dụng, không cần tạo endpoint giả chỉ để thử. Có thể kiểm tra sự hiện diện của ByteArrayHttpMessageConverter trong danh sách converter và kiểm thử swagger-config/OpenAPI endpoint.

## 19. Khi dùng Spring WebFlux

HttpMessageConverter thuộc Spring MVC/Servlet stack. Spring WebFlux dùng hệ thống codec với HttpMessageReader và HttpMessageWriter, cấu hình qua WebFluxConfigurer#configureHttpMessageCodecs hoặc CodecConfigurer.

Vì vậy, không áp dụng trực tiếp WebMvcConfigurer, extendMessageConverters hoặc MappingJackson2HttpMessageConverter cho ứng dụng WebFlux. Hãy kiểm tra stack của starter:

| Stack | Cơ chế chuyển đổi |
| --- | --- |
| Spring MVC | HttpMessageConverter |
| Spring WebFlux | HttpMessageReader / HttpMessageWriter, codec |

Nếu dự án dùng springdoc-openapi-starter-webflux-*, hãy chẩn đoán codec JSON và cấu hình WebFlux tương ứng. Không thêm @EnableWebMvc hoặc converter MVC vào ứng dụng WebFlux để xử lý lỗi.

## 20. Quy trình chẩn đoán từng bước

1. Gọi trực tiếp /v3/api-docs với Accept: application/json và ghi lại status, Content-Type, body.
2. Gọi /v3/api-docs/swagger-config để xác định lỗi nằm ở tài liệu hay cấu hình Swagger UI.
3. Đọc log server và tìm HttpMessageNotWritableException, No converter for, HttpMediaTypeNotAcceptableException hoặc lỗi Jackson.
4. Kiểm tra stack đang dùng là Spring MVC hay WebFlux.
5. Kiểm tra Spring Boot, Spring Framework, springdoc và Jackson major version.
6. Tìm configureMessageConverters, @EnableWebMvc, bean HttpMessageConverters và các converter bean custom.
7. Log thứ tự converter, class và supported media types.
8. Bảo đảm converter JSON và ByteArrayHttpMessageConverter có mặt nếu dùng MVC và đang override danh sách như trường hợp trong springdoc FAQ.
9. Chuyển phần bổ sung converter sang extendMessageConverters hoặc cơ chế customizer của Spring Boot tương ứng.
10. Kiểm tra lại Swagger UI, JSON/YAML endpoint và các API trả DTO, String, Resource hoặc byte array.

## 21. Những cấu hình dễ gây lỗi

**Chỉ thêm Jackson converter vào configureMessageConverters.** Danh sách tự cấu hình có thể bỏ các converter mặc định. Bổ sung byte array và các converter ứng dụng cần, hoặc chuyển sang extendMessageConverters.

**Thiếu ByteArrayHttpMessageConverter.** springdoc FAQ yêu cầu converter này khi override converter mặc định. Kiểm tra và đăng ký nó trong MVC stack.

**Dùng MappingJackson2HttpMessageConverter trong Spring Boot 4.** Đây là converter Jackson 2. Boot 4 dùng Jackson 3; chọn JacksonJsonHttpMessageConverter và API customizer của Boot 4.

**Đặt converter custom hỗ trợ */* ở đầu danh sách.** Converter có thể nhận response mà converter chuyên biệt nên xử lý. Thu hẹp supported media types và kiểm tra thứ tự.

**Tạo ObjectMapper mới thiếu module.** DTO Java Time, Optional hoặc Kotlin có thể không serialize đúng. Tùy chỉnh mapper do Boot quản lý hoặc đăng ký đầy đủ module cần thiết.

**Thêm @EnableWebMvc chỉ để sửa converter.** Điều này tiếp quản MVC configuration và có thể làm mất nhiều auto-configuration khác. Dùng WebMvcConfigurer không có @EnableWebMvc nếu chỉ cần mở rộng.

**Chỉ kiểm tra Swagger UI HTML.** Trang HTML có thể tải được trong khi /v3/api-docs hoặc swagger-config lỗi. Kiểm tra các request API docs trực tiếp.

**Nhầm lỗi 401/403 với lỗi converter.** Security có thể chặn endpoint trước khi converter ghi response. Kiểm tra status và filter chain.

**Nhầm lỗi 404 với lỗi serialize.** Xác minh springdoc.api-docs.path, context path và springdoc.api-docs.enabled.

**Chỉ test endpoint JSON nghiệp vụ.** Thêm test cho /v3/api-docs và /v3/api-docs/swagger-config để phát hiện lỗi riêng của springdoc.

## 22. Checklist khôi phục message converter

- [ ] Xác nhận ứng dụng dùng Spring MVC hay WebFlux.
- [ ] Ghi đúng Spring Boot, Spring Framework, springdoc và Jackson version.
- [ ] Kiểm tra request /v3/api-docs trực tiếp.
- [ ] Kiểm tra /v3/api-docs/swagger-config.
- [ ] Đọc log để xác định lỗi đọc request hay ghi response.
- [ ] Kiểm tra configureMessageConverters có thay danh sách mặc định hay không.
- [ ] Ưu tiên extendMessageConverters khi chỉ cần bổ sung/chỉnh converter.
- [ ] Đảm bảo JSON converter đúng major version.
- [ ] Đảm bảo ByteArrayHttpMessageConverter có mặt trong MVC override scenario theo hướng dẫn springdoc.
- [ ] Kiểm tra thứ tự và supportedMediaTypes.
- [ ] Không dùng @EnableWebMvc nếu không có chủ đích tiếp quản toàn bộ MVC.
- [ ] Tùy chỉnh ObjectMapper/JsonMapper qua cơ chế phù hợp với Spring Boot.
- [ ] Kiểm tra JSON, YAML, swagger-config và API trả file/string/resource.
- [ ] Thêm MockMvc integration test để ngăn lỗi quay lại.

## 23. Kết luận

Lỗi message converter khi thay cấu hình mặc định thường xuất hiện vì danh sách converter bị thay thế, thiếu converter byte array hoặc JSON converter không phù hợp với phiên bản Spring/Jackson. Với Spring MVC, hãy ưu tiên giữ converter mặc định và dùng extendMessageConverters để bổ sung hoặc chỉnh sửa. Khi thực sự override danh sách, bảo đảm ByteArrayHttpMessageConverter và JSON converter cần thiết vẫn có mặt, đồng thời kiểm tra thứ tự. Với Boot 3 dùng Jackson 2 converter; với Boot 4 dùng Jackson 3 converter và cơ chế customizer tương ứng. Cuối cùng, test trực tiếp /v3/api-docs và /v3/api-docs/swagger-config để xác nhận springdoc hoạt động sau mọi thay đổi MVC.

## 24. Nguồn tham khảo

- [springdoc-openapi FAQ — Swagger UI unable to render definition when overriding HttpMessageConverter](https://springdoc.org/faq.html): yêu cầu ByteArrayHttpMessageConverter, Jackson converter và lưu ý thứ tự khi override converter mặc định.
- [Spring Framework 6.2 — Message Converters](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-config/message-converters.html): khác biệt configureMessageConverters và extendMessageConverters, converter selection và ví dụ Jackson 2.
- [Spring Boot 3.5 — Servlet Web Applications](https://docs.spring.io/spring-boot/3.5/reference/web/servlet.html): MVC auto-configuration, HttpMessageConverters và cách bổ sung converter trong Boot 3.
- [Spring Boot 3.5 — HttpMessageConverters API](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/autoconfigure/http/HttpMessageConverters.html): constructor, default converters và postProcessConverters.
- [Spring Boot 4 — Servlet Web Applications](https://docs.spring.io/spring-boot/reference/web/servlet.html): Jackson 3, JacksonJsonHttpMessageConverter và ServerHttpMessageConvertersCustomizer.
- [Spring Framework — HTTP Message Conversion](https://docs.spring.io/spring-framework/reference/web/webmvc/message-converters.html): các converter theo media type như String, byte array, form, resource và Jackson.
- [springdoc-openapi FAQ — Spring Boot compatibility matrix](https://springdoc.org/faq.html): đối chiếu major version springdoc với Spring Boot.
