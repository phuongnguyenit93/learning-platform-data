# Deserialize resource model

Khi một client nhận response HAL từ REST API, Jackson phải chuyển JSON thành một đối tượng Java có thể sử dụng được. Nếu client chỉ đọc payload thành DTO, các thuộc tính nghiệp vụ có thể được giữ lại nhưng những thành phần hypermedia như _links và _embedded sẽ không còn được biểu diễn thành các kiểu Spring HATEOAS. **Deserialize resource model** là quá trình đọc representation thành các model như EntityModel<T>, CollectionModel<T> hoặc PagedModel<T>, đồng thời giữ lại content và links.

Spring HATEOAS bổ sung cấu hình Jackson và các message converter/decoder phù hợp với media type hypermedia. Khi client yêu cầu application/hal+json, module HAL giúp chuyển cấu trúc _links thành Link và cấu trúc _embedded thành content của collection hoặc model lồng nhau. Client có thể đọc dữ liệu, kiểm tra relation và theo link mà không cần tự phân tích JSON bằng chuỗi hoặc map.

Trong module SPRING_HATEOAS, deserialization là phần quan trọng của vòng đời representation: server tạo model có links, serialize thành media type hypermedia, client nhận response và deserialize lại thành resource model có kiểu. Bài học này tập trung vào cách đọc HAL resource, xử lý generic type, cấu hình WebClient và RestTemplate, dùng Traverson, kiểm thử deserialization và xử lý các lỗi thường gặp.

Sau bài học, bạn có thể:

- Giải thích vì sao deserialize HAL thành DTO thuần có thể làm mất hypermedia links.
- Phân biệt EntityModel<T>, CollectionModel<T> và PagedModel<T> khi đọc response.
- Hiểu cách Jackson và module HAL chuyển _links và _embedded.
- Tránh mất generic type do Java type erasure bằng TypeReferences hoặc ParameterizedTypeReference.
- Cấu hình WebClient, RestTemplate và WebTestClient để đọc hypermedia.
- Dùng Traverson để theo relation và deserialize tài nguyên đích.
- Thiết kế DTO phù hợp với content được nhúng.
- Kiểm thử dữ liệu, links và collection bằng Spring test tools.

## Deserialize resource model là gì?

Serialization chuyển một object Java thành JSON hoặc một representation khác. Deserialization làm chiều ngược lại: đọc body và tạo object Java từ nội dung đó.

Với JSON thông thường, client có thể đọc body thành DTO:

~~~json
{
  "id": 42,
  "orderNumber": "ORD-0042",
  "status": "PAID"
}
~~~

~~~java
OrderResponse order = objectMapper.readValue(json, OrderResponse.class);
~~~

Nếu response là HAL, body còn có các thành phần hypermedia:

~~~json
{
  "id": 42,
  "orderNumber": "ORD-0042",
  "status": "PAID",
  "_links": {
    "self": {
      "href": "https://api.example.com/orders/42"
    },
    "invoice": {
      "href": "https://api.example.com/orders/42/invoice"
    }
  }
}
~~~

Đọc trực tiếp thành OrderResponse chỉ lấy các thuộc tính nghiệp vụ mà DTO ánh xạ. Các link không trở thành đối tượng Link trong DTO. Nếu client cần khám phá hành động tiếp theo hoặc đi đến tài nguyên liên quan, nên deserialize thành EntityModel<OrderResponse>.

~~~java
EntityModel<OrderResponse> orderModel = ...;

OrderResponse content = orderModel.getContent();
Link self = orderModel.getRequiredLink("self");
Optional<Link> invoice = orderModel.getLink("invoice");
~~~

Resource model giữ hai phần có vai trò khác nhau:

- **Content** chứa dữ liệu nghiệp vụ mà client cần đọc.
- **Links** chứa các quan hệ và URI để client điều hướng.

Deserialization không tự gửi request theo các link. Nó chỉ đọc link thành dữ liệu Link; client quyết định khi nào cần theo relation.

## Cấu trúc HAL được Jackson chuyển đổi như thế nào?

HAL JSON sử dụng _links để biểu diễn link và _embedded để biểu diễn tài nguyên được nhúng. Spring HATEOAS cung cấp Jackson module và cấu hình media type để ánh xạ những cấu trúc này vào representation models.

### Đọc _links thành Links

Ví dụ response:

~~~json
{
  "id": 42,
  "status": "PAID",
  "_links": {
    "self": {
      "href": "/orders/42"
    },
    "customer": {
      "href": "/customers/7"
    }
  }
}
~~~

Khi deserialize thành EntityModel<OrderResponse>, Spring HATEOAS giữ content trong getContent() và chuyển relation cùng href thành các Link trong model:

~~~java
OrderResponse order = model.getContent();
String selfHref = model.getRequiredLink("self").getHref();
String customerHref = model.getRequiredLink("customer").getHref();
~~~

Link có thể chứa thêm metadata như title, type, hreflang, name, profile hoặc deprecation tùy representation và cấu hình. Client không nên tự giả định chỉ có href.

### Đọc _embedded thành collection content

Một HAL collection thường có dạng:

~~~json
{
  "_embedded": {
    "orders": [
      {
        "id": 42,
        "status": "PAID",
        "_links": {
          "self": { "href": "/orders/42" }
        }
      },
      {
        "id": 43,
        "status": "DRAFT",
        "_links": {
          "self": { "href": "/orders/43" }
        }
      }
    ]
  },
  "_links": {
    "self": { "href": "/orders" }
  }
}
~~~

Khi đọc thành CollectionModel<EntityModel<OrderResponse>>, client nhận collection content gồm các item models. Mỗi item giữ content và self link riêng; collection giữ link ở cấp ngoài:

~~~java
CollectionModel<EntityModel<OrderResponse>> collection = ...;

Link collectionSelf = collection.getRequiredLink("self");

for (EntityModel<OrderResponse> item : collection.getContent()) {
    OrderResponse content = item.getContent();
    Link itemSelf = item.getRequiredLink("self");
}
~~~

Relation orders trong _embedded cho biết nhóm tài nguyên được nhúng. Nó không nhất thiết trở thành tên một field Java trên CollectionModel; content được truy cập thông qua getContent().

### Đọc collection có phân trang

Response phân trang có thể bổ sung metadata page và các link như next, prev, first, last. Dùng PagedModel<T> khi client cần giữ cả content, metadata page và links điều hướng.

~~~java
PagedModel<EntityModel<OrderResponse>> page = ...;

int pageNumber = page.getMetadata().getNumber();
long totalElements = page.getMetadata().getTotalElements();
Link next = page.getLink("next").orElse(null);
~~~

Tên metadata và link có thể thay đổi theo cấu hình media type hoặc pagination strategy. Hãy theo links mà server trả về thay vì tự ghép URL trang kế tiếp.

## Chọn đúng kiểu resource model

Spring HATEOAS cung cấp các wrapper tương ứng với hình dạng tài nguyên:

| Kiểu Java | Khi dùng | Phần dữ liệu |
| --- | --- | --- |
| EntityModel<T> | Một tài nguyên đơn | Một content object T và links |
| CollectionModel<T> | Một collection | Nhiều content item và links cấp collection |
| PagedModel<T> | Một collection phân trang | Content, metadata page và links |
| RepresentationModel<T> | Model tùy chỉnh có links | Các thuộc tính do lớp con khai báo và links |

Nếu endpoint trả một order đơn, chọn EntityModel<OrderResponse>. Nếu endpoint trả danh sách các order, chọn CollectionModel<EntityModel<OrderResponse>> khi từng item có links. Nếu endpoint trả một trang, chọn PagedModel<EntityModel<OrderResponse>>.

Không nên deserialize mọi response vào EntityModel<T>. Một collection HAL có _embedded không có cùng cấu trúc với một item representation; chọn sai wrapper có thể dẫn đến content rỗng hoặc lỗi mapping.

## Generic type và Java type erasure

Java xóa thông tin generic ở runtime trong nhiều tình huống. Khi truyền EntityModel.class cho một deserializer, kiểu T bên trong không còn được xác định. Jackson có thể đọc content thành LinkedHashMap thay vì OrderResponse.

Ví dụ dễ mất kiểu:

~~~java
EntityModel model = objectMapper.readValue(json, EntityModel.class);
Object content = model.getContent();
// content có thể là LinkedHashMap, không phải OrderResponse.
~~~

Để giữ kiểu generic, cung cấp một ParameterizedTypeReference hoặc TypeReference chứa đầy đủ kiểu lồng.

### Dùng TypeReferences của Spring HATEOAS

Spring HATEOAS cung cấp các lớp tiện ích trong org.springframework.hateoas.server.core.TypeReferences:

- EntityModelType<T> đại diện cho EntityModel<T>.
- CollectionModelType<T> đại diện cho CollectionModel<T>.
- PagedModelType<T> đại diện cho PagedModel<T>.

Ví dụ:

~~~java
import org.springframework.hateoas.EntityModel;
import org.springframework.hateoas.server.core.TypeReferences;

var orderType = new TypeReferences.EntityModelType<OrderResponse>() {};
~~~

Với collection item có links:

~~~java
var ordersType =
    new TypeReferences.CollectionModelType<EntityModel<OrderResponse>>() {};
~~~

Các lớp này kế thừa ParameterizedTypeReference, vì vậy có thể truyền trực tiếp vào những API client nhận generic type reference.

### Dùng ParameterizedTypeReference trực tiếp

Nếu không dùng helper của Spring HATEOAS, Spring Framework cung cấp ParameterizedTypeReference:

~~~java
import org.springframework.core.ParameterizedTypeReference;
import org.springframework.hateoas.EntityModel;

ParameterizedTypeReference<EntityModel<OrderResponse>> orderType =
    new ParameterizedTypeReference<>() {};
~~~

Với collection:

~~~java
ParameterizedTypeReference<CollectionModel<EntityModel<OrderResponse>>> ordersType =
    new ParameterizedTypeReference<>() {};
~~~

Cả hai cách đều giữ thông tin generic để decoder biết kiểu content cần tạo.

## Cấu hình hypermedia deserialization

Jackson mặc định biết cách đọc JSON cơ bản, nhưng không tự hiểu mọi semantics của HAL. Spring HATEOAS cung cấp module và message converter/decoder để chuyển các kiểu representation model cùng links.

### Bật hỗ trợ HAL trong ApplicationContext

Với ứng dụng Spring MVC hoặc WebFlux cấu hình thủ công, có thể bật hỗ trợ HAL:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.hateoas.config.EnableHypermediaSupport;
import org.springframework.hateoas.config.EnableHypermediaSupport.HypermediaType;

@Configuration
@EnableHypermediaSupport(type = HypermediaType.HAL)
class HypermediaConfiguration {
}
~~~

EnableHypermediaSupport đăng ký hạ tầng Spring HATEOAS và các Jackson module cần thiết cho media type được chọn. Nó cũng có thể đăng ký LinkDiscoverer và các bean hỗ trợ hypermedia trong application context.

Trong ứng dụng Spring Boot dùng starter Spring HATEOAS, cấu hình tự động có thể cung cấp nhiều thành phần này. Nếu ứng dụng có cấu hình MVC/WebFlux tùy chỉnh, hãy xác nhận hypermedia support đã được kích hoạt cho đúng web stack.

Lưu ý: EnableHypermediaSupport cấu hình hạ tầng Spring. Nó không tự động cấu hình mọi ObjectMapper được tạo thủ công bằng new ObjectMapper() ở ngoài application context.

### Vì sao không nên tự tạo ObjectMapper mặc định?

Ví dụ:

Một mapper được tạo độc lập bằng constructor mặc định, chẳng hạn ObjectMapper mới, không tự có cấu hình HAL của application context. Lệnh đọc JSON vào EntityModel<OrderResponse> chỉ có thể hoạt động đầy đủ nếu mapper đã đăng ký các module và cấu hình phù hợp cho HAL cùng các kiểu representation model. Một mapper Jackson thuần có thể đọc cú pháp JSON nhưng không nhất thiết chuyển _links thành Link hoặc xử lý _embedded theo relation.

Trong ứng dụng Spring, ưu tiên sử dụng message converter/decoder đã được Spring HATEOAS cấu hình. Nếu bắt buộc phải tạo mapper độc lập, hãy đăng ký module HAL và handler/configuration tương ứng với đúng phiên bản Spring HATEOAS và Jackson đang dùng. API module và package có thể khác giữa các thế hệ Jackson; không sao chép một tên module từ ví dụ phiên bản khác mà không đối chiếu dependency hiện tại.

## Deserialize bằng WebClient

WebClient là lựa chọn phổ biến khi client gọi dịch vụ từ ứng dụng reactive hoặc muốn dùng API fluent. Spring HATEOAS cung cấp HypermediaWebClientConfigurer để đăng ký encoder và decoder cho media type hypermedia.

### Cấu hình WebClient

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.hateoas.config.HypermediaWebClientConfigurer;
import org.springframework.web.reactive.function.client.WebClient;

@Configuration
class ClientConfiguration {

    @Bean
    WebClient orderWebClient(HypermediaWebClientConfigurer configurer) {
        return configurer
            .registerHypermediaTypes(WebClient.builder())
            .baseUrl("https://api.example.com")
            .build();
    }
}
~~~

Configurer đăng ký các encoder và decoder cần thiết trên WebClient.Builder. Điều này giúp client xử lý các media type hypermedia mà Spring HATEOAS hỗ trợ.

### Đọc một EntityModel

~~~java
import org.springframework.hateoas.EntityModel;
import org.springframework.hateoas.MediaTypes;
import org.springframework.hateoas.server.core.TypeReferences;
import reactor.core.publisher.Mono;

Mono<EntityModel<OrderResponse>> findOrder(Long id) {
    return orderWebClient.get()
        .uri("/orders/{id}", id)
        .accept(MediaTypes.HAL_JSON)
        .retrieve()
        .bodyToMono(new TypeReferences.EntityModelType<OrderResponse>() {});
}
~~~

Decoder dùng type reference để tạo EntityModel<OrderResponse>. Khi subscribe, client nhận model có content kiểu OrderResponse và links kiểu Spring HATEOAS.

### Đọc một CollectionModel

~~~java
Mono<CollectionModel<EntityModel<OrderResponse>>> findOrders() {
    return orderWebClient.get()
        .uri("/orders")
        .accept(MediaTypes.HAL_JSON)
        .retrieve()
        .bodyToMono(
            new TypeReferences.CollectionModelType<EntityModel<OrderResponse>>() {});
}
~~~

Kiểu generic lồng nhau nói rõ mỗi embedded item là một EntityModel<OrderResponse>. Nếu API chỉ nhúng DTO không có links, kiểu phần tử có thể là OrderResponse; hãy chọn kiểu khớp với representation thực tế.

### Đọc PagedModel

~~~java
Mono<PagedModel<EntityModel<OrderResponse>>> findOrderPage(int page, int size) {
    return orderWebClient.get()
        .uri(builder -> builder.path("/orders")
            .queryParam("page", page)
            .queryParam("size", size)
            .build())
        .accept(MediaTypes.HAL_JSON)
        .retrieve()
        .bodyToMono(
            new TypeReferences.PagedModelType<EntityModel<OrderResponse>>() {});
}
~~~

Sau khi nhận page, client có thể đọc metadata và tìm link next. Nếu cần duyệt trang tiếp theo, hãy theo href của link next thay vì tự tính giá trị page.

## Deserialize bằng RestTemplate

Với ứng dụng đồng bộ, có thể cấu hình RestTemplate bằng HypermediaRestTemplateConfigurer. Configurer chèn các message converter hypermedia vào danh sách converter của client.

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.hateoas.config.HypermediaRestTemplateConfigurer;
import org.springframework.web.client.RestTemplate;

@Configuration
class RestClientConfiguration {

    @Bean
    RestTemplate hypermediaRestTemplate(
            HypermediaRestTemplateConfigurer configurer) {
        return configurer.registerHypermediaTypes(new RestTemplate());
    }
}
~~~

Dùng ParameterizedTypeReference để đọc resource:

~~~java
import java.util.List;

import org.springframework.core.ParameterizedTypeReference;
import org.springframework.http.HttpEntity;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpMethod;
import org.springframework.hateoas.EntityModel;
import org.springframework.hateoas.MediaTypes;
import org.springframework.http.ResponseEntity;

ParameterizedTypeReference<EntityModel<OrderResponse>> type =
    new ParameterizedTypeReference<>() {};

HttpHeaders headers = new HttpHeaders();
headers.setAccept(List.of(MediaTypes.HAL_JSON));

ResponseEntity<EntityModel<OrderResponse>> response =
    restTemplate.exchange(
        "https://api.example.com/orders/42",
        HttpMethod.GET,
        new HttpEntity<>(headers),
        type);

EntityModel<OrderResponse> model = response.getBody();
~~~

Không dùng EntityModel.class trong overload generic nếu cần content có kiểu cụ thể. Dùng type reference để tránh LinkedHashMap ở getContent().

## Deserialize bằng Traverson

Traverson là API client của Spring HATEOAS để đi theo các link relation. Nó có thể đọc representation HAL, tìm relation, theo link và deserialize tài nguyên cuối cùng thành kiểu được yêu cầu.

~~~java
import java.net.URI;

import org.springframework.hateoas.EntityModel;
import org.springframework.hateoas.MediaTypes;
import org.springframework.hateoas.client.Traverson;
import org.springframework.hateoas.server.core.TypeReferences;

Traverson traverson = new Traverson(
    URI.create("https://api.example.com/"),
    MediaTypes.HAL_JSON);

EntityModel<OrderResponse> order = traverson
    .follow("orders")
    .follow("$._embedded.orders[0]._links.self.href")
    .toObject(new TypeReferences.EntityModelType<OrderResponse>() {});
~~~

Ví dụ minh họa việc bắt đầu từ entry point, theo relation orders, chọn self link của item đầu tiên và đọc item thành EntityModel<OrderResponse>. JSONPath trong bước follow phụ thuộc cấu trúc HAL thực tế. Trong ứng dụng, nên xử lý trường hợp collection rỗng trước khi cố truy cập phần tử đầu tiên.

Traverson hữu ích khi client muốn khám phá API qua relation thay vì hard-code URI. Nó vẫn cần media type phù hợp và kiểu generic chính xác ở bước toObject.

## Kiểm thử deserialization bằng WebTestClient

Khi kiểm thử ứng dụng WebFlux hoặc controller hypermedia, có thể dùng HypermediaWebTestClientConfigurer để đăng ký hỗ trợ hypermedia cho WebTestClient.

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.hateoas.EntityModel;
import org.springframework.hateoas.MediaTypes;
import org.springframework.hateoas.config.HypermediaWebTestClientConfigurer;
import org.springframework.hateoas.server.core.TypeReferences;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest
@AutoConfigureWebTestClient
class OrderHypermediaClientTest {

    @Autowired
    WebTestClient.Builder builder;

    @Autowired
    HypermediaWebTestClientConfigurer configurer;

    @Test
    void deserializesOrderResource() {
        WebTestClient client = builder.apply(configurer).build();

        client.get()
            .uri("/orders/42")
            .accept(MediaTypes.HAL_JSON)
            .exchange()
            .expectStatus().isOk()
            .expectBody(
                new TypeReferences.EntityModelType<OrderResponse>() {})
            .consumeWith(result -> {
                EntityModel<OrderResponse> model = result.getResponseBody();

                assertThat(model).isNotNull();
                assertThat(model.getContent().id()).isEqualTo(42L);
                assertThat(model.getRequiredLink("self").getHref())
                    .endsWith("/orders/42");
            });
    }
}
~~~

Ví dụ giả định ứng dụng đã cấu hình HAL, endpoint /orders/42 trả một representation HAL và test có AssertJ. Với Spring Boot, builder được auto-configure; apply(configurer) bổ sung hỗ trợ hypermedia cho client test.

Nếu dùng MockMvc để kiểm thử controller phía server, có thể kiểm tra JSONPath trên response. Tuy nhiên, để kiểm tra thật sự quá trình Jackson deserialize thành EntityModel hoặc CollectionModel, cần một client có hypermedia decoder được cấu hình hoặc một test trực tiếp với mapper đã đăng ký module HAL.

## Xử lý các kiểu model tùy chỉnh

Ứng dụng có thể tạo model riêng kế thừa RepresentationModel:

~~~java
public class OrderModel extends RepresentationModel<OrderModel> {

    private Long id;
    private String status;

    public OrderModel() {
    }

    public Long getId() {
        return id;
    }

    public void setId(Long id) {
        this.id = id;
    }

    public String getStatus() {
        return status;
    }

    public void setStatus(String status) {
        this.status = status;
    }
}
~~~

Nếu response JSON chứa các thuộc tính tương ứng và _links, mapper hypermedia có thể tạo OrderModel cùng links. Với lớp model chỉ có constructor tham số, hãy cung cấp constructor hoặc creator mà Jackson hỗ trợ, chẳng hạn JsonCreator và JsonProperty theo cấu hình Jackson của ứng dụng.

~~~java
import com.fasterxml.jackson.annotation.JsonCreator;
import com.fasterxml.jackson.annotation.JsonProperty;
import org.springframework.hateoas.RepresentationModel;

public class OrderModel extends RepresentationModel<OrderModel> {

    private final Long id;
    private final String status;

    @JsonCreator
    public OrderModel(
            @JsonProperty("id") Long id,
            @JsonProperty("status") String status) {
        this.id = id;
        this.status = status;
    }

    public Long getId() {
        return id;
    }

    public String getStatus() {
        return status;
    }
}
~~~

Ví dụ annotation dùng package Jackson 2 (com.fasterxml.jackson). Với nền tảng chuyển sang Jackson 3, package annotation và API mapper tương ứng có thể thay đổi. Hãy dùng đúng Jackson major version được Spring Framework/Spring Boot của ứng dụng quản lý.

Khi không cần kiểu model tùy chỉnh, EntityModel<OrderResponse> thường đơn giản hơn. Nó tách DTO content khỏi links và giảm số lượng lớp cần duy trì.

## Nhiều embedded relations trong cùng một representation

Một HAL resource có thể nhúng nhiều relation:

~~~json
{
  "_embedded": {
    "items": [
      {
        "id": 101,
        "sku": "KB-001"
      }
    ],
    "customer": {
      "id": 7,
      "name": "Nguyễn An"
    }
  },
  "_links": {
    "self": { "href": "/orders/42" }
  }
}
~~~

Đây là một representation cha có cả collection items và một customer. Không thể giả định toàn bộ _embedded sẽ ánh xạ thành một CollectionModel<T> duy nhất nếu client cần giữ cả hai relation với kiểu khác nhau.

Trong trường hợp đó, hãy định nghĩa một representation model có thuộc tính cho từng quan hệ được nhúng, dùng kiểu DTO phù hợp, hoặc đọc cây JSON bằng JsonNode rồi chuyển từng nhánh theo hợp đồng. Các relation có thể khác cardinality và kiểu dữ liệu.

Ví dụ:

~~~java
public class OrderDetails {
    private List<OrderItemResponse> items;
    private CustomerResponse customer;

    // Getters and setters
}
~~~

Đối với model phức hợp có links ở cấp cha, bọc content trong EntityModel<OrderDetails>. Cần cấu hình HAL mapper để nó ánh xạ embedded relation vào thuộc tính content theo cấu trúc và annotation mà phiên bản thư viện hỗ trợ; hãy xác minh bằng test response thực tế.

## Các lỗi thường gặp khi deserialize resource model

### Content trở thành LinkedHashMap

Nguyên nhân thường là client dùng raw class như EntityModel.class hoặc CollectionModel.class nên Jackson không nhận được generic type cụ thể.

Cách xử lý:

- Dùng TypeReferences.EntityModelType<T>.
- Dùng TypeReferences.CollectionModelType<T>.
- Dùng ParameterizedTypeReference khi API client hỗ trợ.

### Links không được deserialize

Nguyên nhân có thể là mapper hoặc message converter không có module hypermedia phù hợp, hoặc response không được đọc dưới media type tương ứng.

Kiểm tra:

- Response có Content-Type: application/hal+json không?
- Client có gửi Accept: application/hal+json không?
- HypermediaWebClientConfigurer hoặc HypermediaRestTemplateConfigurer đã được áp dụng chưa?
- Mapper độc lập có module HAL đúng phiên bản không?

### Collection content rỗng hoặc sai kiểu

Kiểm tra response có đúng _embedded relation và kiểu phần tử có khớp với JSON không. Ví dụ CollectionModel<OrderResponse> không tương đương với CollectionModel<EntityModel<OrderResponse>> nếu từng item có _links riêng và client cần giữ chúng.

### Không tìm thấy relation

getRequiredLink("invoice") sẽ lỗi nếu representation không có relation đó. Nếu link là tùy chọn, dùng getLink("invoice") và xử lý Optional:

~~~java
model.getLink("invoice").ifPresent(link -> {
    // Follow or store the link when available.
});
~~~

Không phải mọi tài nguyên đều phải có mọi relation. Links có thể phụ thuộc trạng thái, quyền truy cập hoặc dữ liệu hiện tại.

### JSON không khớp DTO

Jackson có thể báo lỗi khi kiểu dữ liệu không tương thích, constructor không thể gọi, hoặc property bắt buộc không có. Hãy kiểm tra:

- Tên property và kiểu dữ liệu trong JSON.
- Constructor, getter/setter hoặc JsonCreator.
- Kiểu ngày giờ và module Jackson tương ứng.
- Quy tắc xử lý unknown properties.
- Version schema của API mà client đang gọi.

### Nhầm deserialize với follow link

Deserialize chỉ chuyển body hiện tại thành object. Nó không tự tải các URI trong _links. Muốn lấy tài nguyên liên quan, dùng WebClient, RestTemplate hoặc Traverson để thực hiện request theo link.

## Ranh giới giữa resource model và domain entity

Không nên deserialize trực tiếp response từ dịch vụ bên ngoài vào JPA entity đang được quản lý bởi persistence context. HAL representation là hợp đồng HTTP; domain entity có thể chứa trạng thái, quan hệ hai chiều, khóa nội bộ và quy tắc bất biến riêng.

Ưu tiên DTO:

~~~java
public record OrderResponse(
    Long id,
    String orderNumber,
    String status
) {}
~~~

Đọc vào EntityModel<OrderResponse>, sau đó chuyển content sang domain model qua service hoặc mapper. Links giữ vai trò điều hướng ở tầng client/integration; chúng không nên trở thành quan hệ JPA hoặc dữ liệu persistence một cách mặc định.

Đối với dữ liệu đầu vào, luôn xác thực và kiểm tra quyền ở server. Một link có trong representation không chứng minh người dùng có quyền gọi nó; một resource model deserialize thành công cũng không chứng minh dữ liệu đáng tin cậy.

## Checklist kiểm thử

Khi kiểm thử deserialize resource model, hãy xác minh:

1. Client yêu cầu đúng media type hypermedia.
2. Response có Content-Type phù hợp, ví dụ application/hal+json.
3. Content được chuyển thành đúng DTO hoặc model tùy chỉnh.
4. Generic type được giữ đúng, không bị thay bằng LinkedHashMap.
5. _links được chuyển thành Link và giữ đúng relation/href.
6. _embedded được chuyển thành đúng collection content.
7. Collection có phân trang giữ được metadata và links điều hướng.
8. Link tùy chọn được xử lý an toàn khi vắng mặt.
9. Collection rỗng và relation embedded rỗng được xử lý đúng.
10. Unknown fields hoặc relation mới không làm client hỏng ngoài dự kiến.
11. Mapper và decoder sử dụng đúng major version Jackson.
12. Deserialize không tự gọi link hoặc làm thay đổi domain state.

## Những sai lầm thường gặp

**Deserialize HAL thành DTO thuần rồi mong vẫn có links.** DTO chỉ giữ các thuộc tính được ánh xạ. Dùng EntityModel<T> hoặc model kế thừa RepresentationModel khi cần hypermedia.

**Dùng raw EntityModel.class.** Java type erasure khiến content có thể trở thành LinkedHashMap. Dùng TypeReferences hoặc ParameterizedTypeReference.

**Dùng ObjectMapper mặc định cho HAL.** Mapper không có module hypermedia sẽ không xử lý đúng cấu trúc links/embedded. Dùng converter đã cấu hình hoặc đăng ký module HAL phù hợp.

**Nhầm collection với item resource.** Chọn EntityModel, CollectionModel hoặc PagedModel theo hình dạng response.

**Nghĩ deserialize sẽ tự theo link.** Links chỉ được đọc thành dữ liệu. Dùng client hoặc Traverson để gửi request tiếp theo.

**Deserialize trực tiếp vào JPA entity.** Tách DTO khỏi domain entity để tránh gắn hợp đồng HTTP với persistence model.

**Giả định mọi relation đều luôn tồn tại.** Relation có thể tùy trạng thái hoặc quyền. Dùng getLink khi link không bắt buộc.

**Dùng API Jackson không khớp phiên bản.** Cấu hình module và package có thể thay đổi giữa Jackson 2 và Jackson 3; dùng dependency được Spring quản lý và đối chiếu tài liệu đúng phiên bản.

## Kết luận

Deserialize resource model giúp client chuyển HAL representation thành các kiểu Spring HATEOAS mà vẫn giữ content và hypermedia links. EntityModel<T> phù hợp với một tài nguyên, CollectionModel<T> phù hợp với collection và PagedModel<T> phù hợp với collection phân trang. Jackson cần module hypermedia và client cần message converter/decoder phù hợp để hiểu _links cùng _embedded.

Hãy giữ generic type bằng TypeReferences hoặc ParameterizedTypeReference, cấu hình WebClient/RestTemplate bằng các hypermedia configurer, và dùng Traverson khi cần đi theo relation. Deserialize chỉ đọc representation hiện tại; nó không tự follow link, không xác thực quyền và không thay thế bước chuyển DTO thành domain model. Kiểm thử cả content, relation, href, collection và media type để bảo đảm client hiểu đúng hợp đồng hypermedia.

Tài liệu tham khảo:

- Spring HATEOAS Reference — Client-side support: https://docs.spring.io/spring-hateoas/docs/current/reference/html/#client-side
- Spring HATEOAS Reference — Configuring WebClient instances: https://docs.spring.io/spring-hateoas/docs/current/reference/html/#webclient
- Spring HATEOAS API — TypeReferences: https://docs.spring.io/spring-hateoas/docs/current/api/org/springframework/hateoas/server/core/TypeReferences.html
- Spring HATEOAS API — HypermediaWebClientConfigurer: https://docs.spring.io/spring-hateoas/docs/current/api/org/springframework/hateoas/config/HypermediaWebClientConfigurer.html
- Spring HATEOAS API — HypermediaRestTemplateConfigurer: https://docs.spring.io/spring-hateoas/docs/current/api/org/springframework/hateoas/config/HypermediaRestTemplateConfigurer.html
