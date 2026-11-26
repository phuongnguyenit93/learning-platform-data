# Fallback representation trong Spring HATEOAS

Khi một API dùng Spring HATEOAS, server thường muốn trả về representation HAL để công bố liên kết và tài nguyên nhúng. Tuy nhiên, một số máy khách cũ chỉ gửi header `Accept: application/json` vì chúng biết JSON nhưng chưa khai báo riêng media type HAL. Spring Boot cung cấp một hành vi fallback tương thích: theo mặc định, request chấp nhận `application/json` vẫn có thể nhận response HAL với `Content-Type: application/hal+json`.

Hành vi này được điều khiển bởi property `spring.hateoas.use-hal-as-default-json-media-type`. Hiểu rõ fallback giúp API hỗ trợ client cũ mà vẫn công bố đúng media type, đồng thời tránh nhầm lẫn giữa HAL JSON và JSON thuần.

## 1. Fallback representation là gì?

Fallback representation là representation server chọn trong một tình huống thương lượng nội dung cụ thể khi máy khách không yêu cầu rõ media type hypermedia mà server ưu tiên. Trong Spring Boot, trường hợp quan trọng là máy khách gửi:

~~~http
GET /orders/42 HTTP/1.1
Accept: application/json
~~~

Nếu fallback HAL đang bật, Spring HATEOAS có thể trả:

~~~http
HTTP/1.1 200 OK
Content-Type: application/hal+json
~~~

Body vẫn là JSON, nhưng có cấu trúc HAL:

~~~json
{
  "id": 42,
  "status": "PAID",
  "_links": {
    "self": {
      "href": "/orders/42"
    },
    "items": {
      "href": "/orders/42/items"
    }
  }
}
~~~

Điểm cần nhớ: server không đổi response thành JSON thuần chỉ vì client ghi `application/json` trong `Accept`. Nó dùng HAL như representation JSON mặc định cho request đó.

Đây là một quy tắc tương thích cụ thể của Spring Boot và Spring HATEOAS. Nó không phải cơ chế chung để chọn bất kỳ media type thay thế nào trong mọi trường hợp.

## 2. Vì sao Spring Boot dùng HAL làm fallback cho application/json?

HAL sử dụng cú pháp JSON, nhưng bổ sung quy ước hypermedia như `_links` và `_embedded`. Nhiều client có thể parse cú pháp JSON mà không cần thay đổi parser, trong khi client hiểu HAL có thể khám phá các quan hệ và điều hướng theo link.

Ví dụ cùng một tài nguyên đơn hàng:

JSON thuần:

~~~json
{
  "id": 42,
  "status": "PAID"
}
~~~

HAL JSON:

~~~json
{
  "id": 42,
  "status": "PAID",
  "_links": {
    "self": {
      "href": "/orders/42"
    }
  }
}
~~~

Việc trả HAL cho client chấp nhận JSON có thể giúp API chuyển dần sang hypermedia mà không yêu cầu tất cả client phải gửi ngay `Accept: application/hal+json`.

Tuy vậy, hai media type không đồng nhất về semantics:

- `application/json` chỉ xác định cú pháp và quy tắc JSON.
- `application/hal+json` xác định representation JSON theo quy ước HAL.
- Client chỉ hiểu JSON có thể đọc các trường dữ liệu, nhưng chưa chắc biết xử lý `_links` hoặc `_embedded`.

Vì vậy, hãy công bố đúng `Content-Type` mà server thực sự trả về. Không nên ghi `application/json` trong response header nếu body được tạo theo hợp đồng HAL.

## 3. Property điều khiển fallback

Spring Boot cung cấp property:

~~~properties
spring.hateoas.use-hal-as-default-json-media-type=true
~~~

Giá trị mặc định là `true`. Khi bật, bộ xử lý HAL có thể phục vụ request chấp nhận `application/json` ngoài media type HAL cụ thể `application/hal+json`.

| Giá trị | Hành vi |
|---|---|
| `true` | Cho phép response HAL được gửi cho request chấp nhận `application/json` |
| `false` | Không dùng `application/json` như media type thay thế cho HAL converter; client cần yêu cầu media type được cấu hình tương ứng |

Property này điều khiển cách Spring HATEOAS xử lý media type ở phía response. Nó không thay đổi kiểu Java của DTO, không tự chuyển đổi entity thành HAL và cũng không quyết định HTTP method của endpoint.

Property này cũng không thay thế điều kiện `produces` trên mapping controller. Nếu endpoint khai báo một `produces` quá hẹp, điều kiện chọn handler có thể loại request trước khi message converter áp dụng fallback. Khi dùng `produces`, hãy bảo đảm nó phù hợp với các media type mà client thực sự gửi và kiểm thử bằng request HTTP.

## 4. Luồng xử lý với fallback đang bật

Giả sử controller trả về `EntityModel<OrderDto>` và representation có link self. Máy khách gửi request:

~~~http
GET /orders/42
Accept: application/json
~~~

Với cấu hình mặc định, kết quả có thể là:

~~~http
HTTP/1.1 200 OK
Content-Type: application/hal+json
~~~

~~~json
{
  "id": 42,
  "status": "PAID",
  "_links": {
    "self": {
      "href": "/orders/42"
    }
  }
}
~~~

Khi client yêu cầu HAL rõ ràng:

~~~http
GET /orders/42
Accept: application/hal+json
~~~

server cũng trả HAL. Khác biệt nằm ở việc request thứ nhất dùng media type JSON tổng quát, còn request thứ hai yêu cầu đúng media type hypermedia.

Bảng dưới đây tóm tắt:

| Request Accept | Fallback bật | Content-Type response mong đợi |
|---|---|---|
| `application/hal+json` | Có | `application/hal+json` |
| `application/json` | Có | `application/hal+json` |
| `application/json` | Tắt | Phụ thuộc representation và converter khác đã cấu hình |
| `application/xml` | Có hoặc tắt | Chỉ thành công nếu endpoint có hỗ trợ XML |

Fallback chỉ áp dụng cho quan hệ giữa `application/json` và HAL. Nó không tự tạo serializer XML, CBOR hoặc media type tùy chỉnh.

## 5. Tắt fallback khi cần content negotiation nghiêm ngặt

Nếu hợp đồng API yêu cầu client phải chỉ rõ media type hypermedia, có thể tắt fallback:

~~~properties
spring.hateoas.use-hal-as-default-json-media-type=false
~~~

Sau đó client cần yêu cầu media type HAL:

~~~http
GET /orders/42
Accept: application/hal+json
~~~

Khi tắt fallback, không nên mặc định rằng mọi `RepresentationModel` sẽ tự động được tuần tự hóa thành JSON thuần nếu client gửi `Accept: application/json`. Representation model có cấu trúc và metadata hypermedia riêng; việc tắt một media type mapping không tự tạo ra một serializer thay thế.

Nếu API muốn hỗ trợ JSON thuần song song với HAL, hãy thiết kế representation và converter cho hai contract một cách tường minh. Ví dụ, một endpoint có thể trả DTO thuần cho `application/json`, còn endpoint hoặc mapping khác trả `EntityModel` cho `application/hal+json`. Cách tổ chức cụ thể phụ thuộc vào kiến trúc và version Spring Boot/Spring HATEOAS.

## 6. Phân biệt fallback HAL với JSON representation riêng

Một lỗi thiết kế thường gặp là nghĩ rằng tắt fallback sẽ tự khôi phục JSON thuần cho tất cả response. Thực tế, property chỉ điều khiển việc HAL converter có nhận `application/json` như một media type thay thế hay không.

| Nhu cầu | Cách thiết kế |
|---|---|
| Client cũ gửi application/json nhưng API vẫn muốn công bố HAL | Giữ fallback mặc định |
| Client phải khai báo rõ HAL | Tắt fallback và yêu cầu application/hal+json |
| API cần cả JSON thuần và HAL | Tạo representation/converter phù hợp cho từng media type |
| API cần media type hypermedia riêng | Đăng ký HypermediaMappingInformation |
| Muốn đăng ký media type alias cho HAL JSON | Cấu hình `HalConfiguration.withMediaType(...)` |
| Chỉ muốn thay đổi cách HAL render link | Cấu hình HalConfiguration |

JSON thuần nên được tạo từ DTO hoặc representation được thiết kế cho contract JSON đó. Đừng dùng việc tắt fallback như một cách ẩn các link khỏi một representation mà server vẫn xây dựng theo mô hình HATEOAS.

## 7. Cấu hình HalConfiguration và HypermediaMappingInformation

Khi thay đổi fallback, Spring Boot khuyến nghị cấu hình Spring HATEOAS phù hợp với media type mà ứng dụng muốn cung cấp. Hai thành phần thường gặp có mục tiêu khác nhau.

### HalConfiguration

`HalConfiguration` có thể đăng ký thêm media type alias cho HAL JSON bằng `withMediaType(...)`. Alias này vẫn dùng cấu trúc HAL; nó không tạo ra JSON thuần hoặc một serializer hoàn toàn khác.

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.hateoas.mediatype.hal.HalConfiguration;
import org.springframework.http.MediaType;

@Configuration
class HalMediaTypeConfiguration {

    @Bean
    HalConfiguration halConfiguration() {
        return new HalConfiguration()
            .withMediaType(
                MediaType.parseMediaType("application/vnd.acme.hal+json")
            );
    }
}
~~~

Sau cấu hình, client có thể yêu cầu media type alias `application/vnd.acme.hal+json` để nhận representation HAL. Cách này hữu ích khi muốn dùng một vendor media type riêng mà vẫn giữ serializer HAL.

Nếu muốn kết hợp alias media type và chính sách render link trong cùng một bean, có thể cấu hình như sau:

~~~java
import org.springframework.hateoas.mediatype.hal.HalConfiguration;
import org.springframework.hateoas.mediatype.hal.HalConfiguration.RenderSingleLinks;
import org.springframework.http.MediaType;

@Bean
HalConfiguration halConfiguration() {
    return new HalConfiguration()
        .withMediaType(
            MediaType.parseMediaType("application/vnd.acme.hal+json")
        )
        .withRenderSingleLinks(RenderSingleLinks.AS_ARRAY);
}
~~~

Ví dụ kết hợp alias media type và chính sách render link. Mặc định HAL thường render một link đơn dưới dạng object; cấu hình trên yêu cầu render relation một link dưới dạng array. `HalConfiguration` không phải bộ chuyển đổi tổng quát từ HAL sang JSON thuần; nó điều chỉnh media type alias và các chính sách biểu diễn HAL.

### HypermediaMappingInformation

Nếu cần đăng ký media type hypermedia riêng, Spring HATEOAS cung cấp SPI `HypermediaMappingInformation`. Implementation mô tả các media type được hỗ trợ và cung cấp cấu hình Jackson tương ứng.

Một cấu hình custom có dạng khái quát:

~~~java
import java.util.List;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.hateoas.config.HypermediaMappingInformation;
import org.springframework.http.MediaType;
import tools.jackson.databind.JacksonModule;

@Configuration
class AcmeHypermediaConfiguration
        implements HypermediaMappingInformation {

    @Override
    public List<MediaType> getMediaTypes() {
        return List.of(
            MediaType.parseMediaType(
                "application/vnd.acme.order+json"
            )
        );
    }

    @Override
    public JacksonModule getJacksonModule() {
        return new AcmeHypermediaJacksonModule();
    }

    @Bean
    AcmeLinkDiscoverer acmeLinkDiscoverer() {
        return new AcmeLinkDiscoverer();
    }
}
~~~

`AcmeHypermediaJacksonModule` và `AcmeLinkDiscoverer` là các implementation do ứng dụng cung cấp. Module chịu trách nhiệm tuần tự hóa/giải tuần tự hóa representation theo định dạng riêng; LinkDiscoverer giúp client-side support tìm link theo relation.

Ví dụ dùng chữ ký API Spring HATEOAS 3.1.x với Jackson 3. Ở các phiên bản Spring HATEOAS 2.x, kiểu Jackson và một số method cấu hình có thể khác; hãy dùng đúng API theo phiên bản dependency của ứng dụng.

Không cần tạo custom media type chỉ để đổi tên `application/hal+json`. Hãy dùng custom SPI khi ứng dụng thực sự có một contract representation khác.

## 8. Vai trò của Spring Boot auto-configuration

Khi dùng Spring Boot với starter Spring HATEOAS phù hợp, auto-configuration đăng ký các thành phần cần thiết để tuần tự hóa representation model và hỗ trợ hypermedia. Nhờ đó, phần lớn ứng dụng không cần tự khai báo `@EnableHypermediaSupport`.

Nếu tự bật `@EnableHypermediaSupport`, ứng dụng chuyển sang kiểm soát cấu hình hypermedia trực tiếp. Spring Boot lưu ý rằng việc này tắt một số tùy chỉnh `JsonMapper` mà auto-configuration đã áp dụng trước đó.

Vì vậy:

- Ưu tiên auto-configuration khi không có nhu cầu tùy chỉnh đặc biệt.
- Chỉ dùng `@EnableHypermediaSupport` khi cần kiểm soát media type hoặc cấu hình hypermedia rõ ràng.
- Không đăng ký trùng các module/converter mà Boot đã tự cấu hình.
- Sau khi thay đổi fallback, kiểm thử lại serialization và content negotiation ở cấp HTTP.

Với Spring WebFlux, `spring-boot-starter-hateoas` là starter dành cho Spring MVC. Ứng dụng WebFlux dùng dependency `spring-hateoas` trực tiếp cùng `spring-boot-starter-webflux` và cần xác minh cấu hình codec phù hợp với stack reactive.

## 9. Fallback representation không phải error representation

Không nên nhầm fallback HAL với representation dùng cho lỗi HTTP.

Fallback HAL giải quyết câu hỏi: khi client chấp nhận `application/json`, server có cho phép trả HAL JSON hay không?

Error representation giải quyết câu hỏi khác: khi request thất bại, server mô tả lỗi theo media type nào? Ví dụ, `application/problem+json` có thể biểu diễn thông tin lỗi theo Problem Details.

Hai cơ chế độc lập:

| Khái niệm | Mục đích |
|---|---|
| HAL fallback cho application/json | Chọn HAL làm response cho request chấp nhận JSON |
| Problem Details | Mô tả lỗi HTTP có cấu trúc |
| Default content type | Chọn media type khi không có lựa chọn cụ thể theo chiến lược negotiation |
| Custom hypermedia mapping | Đăng ký media type và serializer riêng |

Property `spring.hateoas.use-hal-as-default-json-media-type` không cấu hình status code, error handler hoặc Problem Details.

## 10. Kiểm thử fallback bằng MockMvc

Nên kiểm thử header `Accept` và `Content-Type` thực tế thay vì chỉ kiểm tra object Java trả về từ controller.

Khi fallback mặc định đang bật:

~~~java
mockMvc.perform(
        get("/orders/42")
            .accept(MediaType.APPLICATION_JSON)
    )
    .andExpect(status().isOk())
    .andExpect(content().contentTypeCompatibleWith(
        MediaTypes.HAL_JSON
    ))
    .andExpect(jsonPath("$._links.self.href").exists());
~~~

Kiểm tra client yêu cầu HAL tường minh:

~~~java
mockMvc.perform(
        get("/orders/42")
            .accept(MediaTypes.HAL_JSON)
    )
    .andExpect(status().isOk())
    .andExpect(content().contentTypeCompatibleWith(
        MediaTypes.HAL_JSON
    ));
~~~

Khi fallback đã tắt, kiểm thử phải phản ánh contract mà ứng dụng thực sự cấu hình. Nếu endpoint hỗ trợ JSON thuần bằng DTO:

~~~java
mockMvc.perform(
        get("/orders/42/summary")
            .accept(MediaType.APPLICATION_JSON)
    )
    .andExpect(status().isOk())
    .andExpect(content().contentTypeCompatibleWith(
        MediaType.APPLICATION_JSON
    ))
    .andExpect(jsonPath("$.id").value(42))
    .andExpect(jsonPath("$._links").doesNotExist());
~~~

Ví dụ cuối giả định endpoint summary trả DTO thuần và có converter JSON tương ứng. Không áp dụng kỳ vọng này cho endpoint trả EntityModel nếu ứng dụng chưa định nghĩa serializer cho contract JSON thuần.

Các tình huống nên kiểm tra:

- Accept application/json khi fallback bật nhận Content-Type application/hal+json.
- Accept application/hal+json luôn được xử lý theo cấu hình HAL.
- Khi fallback tắt, application/json chỉ thành công nếu có representation/converter phù hợp.
- Response HAL vẫn có _links và _embedded đúng contract.
- Response JSON thuần không vô tình lộ cấu trúc nội bộ của RepresentationModel.
- Custom media type có Content-Type, serializer và link discovery đúng.
- Các response khác nhau theo Accept có chính sách cache phù hợp.

## 11. Lỗi thường gặp

| Lỗi | Hệ quả | Cách xử lý |
|---|---|---|
| Nghĩ application/json luôn đồng nghĩa JSON thuần | Client nhận HAL dù chỉ yêu cầu JSON | Kiểm tra Content-Type response và property fallback |
| Tắt property nhưng không cấu hình representation thay thế | Có thể không tìm thấy converter phù hợp hoặc serialization thất bại | Đăng ký mapping/serializer phù hợp và kiểm thử |
| Dùng HalConfiguration để tạo JSON thuần | Sai mục tiêu cấu hình | Dùng DTO/converter JSON hoặc HypermediaMappingInformation |
| Cho rằng fallback áp dụng cho mọi Accept | Hiểu sai phạm vi property | Property chỉ điều khiển HAL response cho request chấp nhận application/json |
| Trả EntityModel và mong Jackson bỏ link khi fallback tắt | Representation vẫn mang cấu trúc hypermedia | Tạo DTO riêng cho JSON thuần |
| Bật @EnableHypermediaSupport mà không kiểm tra Boot auto-config | Có thể làm mất tùy chỉnh JsonMapper của Boot | Chỉ bật khi cần và kiểm tra lại converter |
| Chỉ kiểm thử status 200 | Không phát hiện sai media type | Kiểm tra cả Content-Type và cấu trúc body |

## 12. Quy trình chọn fallback representation

Khi thiết kế fallback cho API Spring HATEOAS, hãy thực hiện theo trình tự:

1. Xác định client có hiểu HAL hay chỉ gửi Accept application/json.
2. Nếu muốn hỗ trợ client cũ bằng HAL, giữ `spring.hateoas.use-hal-as-default-json-media-type=true`.
3. Nếu muốn content negotiation nghiêm ngặt, đặt property thành false và yêu cầu client gửi media type hypermedia rõ ràng.
4. Nếu cần JSON thuần, tạo DTO/representation và converter riêng cho application/json.
5. Nếu cần media type hypermedia riêng, triển khai HypermediaMappingInformation.
6. Nếu chỉ cần thay đổi cách render HAL, dùng HalConfiguration.
7. Kiểm tra tác động của auto-configuration và @EnableHypermediaSupport.
8. Kiểm thử Accept, Content-Type, body, link và lỗi serialization bằng MockMvc hoặc WebTestClient.

Fallback representation giúp Spring Boot phục vụ HAL cho những client chỉ chấp nhận application/json. Cơ chế này thuận tiện cho tương thích, nhưng không có nghĩa HAL và JSON thuần là cùng một contract. Khi tắt fallback, ứng dụng cần công bố rõ media type và cấu hình serializer phù hợp với từng representation mà API hỗ trợ.

## Tài liệu tham khảo

- [Spring Boot Reference — Spring HATEOAS](https://docs.spring.io/spring-boot/reference/web/spring-hateoas.html)
- [Spring HATEOAS Reference — Media types](https://docs.spring.io/spring-hateoas/docs/current/reference/html/#mediatypes)
- [HypermediaMappingInformation API](https://docs.spring.io/spring-hateoas/docs/current/api/org/springframework/hateoas/config/HypermediaMappingInformation.html)
