# Pagination trong client

Khi một REST API trả về collection lớn, server thường chia dữ liệu thành nhiều trang. Client cần đọc trang hiện tại, hiển thị dữ liệu và chuyển tới trang kế tiếp hoặc quay lại trang trước. Với Spring HATEOAS, response phân trang có thể được biểu diễn bằng HAL và chứa các link điều hướng như **first**, **prev**, **self**, **next** và **last**.

Nguyên tắc quan trọng ở phía client là điều hướng theo link mà server công bố. Client không nên tự ghép query parameter page, size hoặc sort để đoán URL trang tiếp theo. Server có thể đổi cách đánh số trang, giới hạn kích thước, thêm filter, dùng cursor hoặc thay cấu trúc route; link hypermedia giúp client tiếp tục làm việc mà không phải biết các chi tiết đó.

## Một trang dữ liệu trong HAL

Spring HATEOAS dùng **PagedModel** để biểu diễn một trang collection. Khi serialize thành HAL JSON, response thường có ba phần:

- **_embedded** chứa các phần tử của trang hiện tại.
- **_links** chứa các link điều hướng tới collection hoặc các trang liên quan.
- **page** chứa metadata như kích thước trang, số phần tử tổng cộng, số trang và chỉ số trang hiện tại.

Ví dụ response của API đơn hàng:

~~~json
{
  "_embedded": {
    "orders": [
      {
        "id": "ORD-101",
        "status": "PENDING",
        "_links": {
          "self": {
            "href": "https://api.example.com/orders/ORD-101"
          }
        }
      },
      {
        "id": "ORD-102",
        "status": "PAID",
        "_links": {
          "self": {
            "href": "https://api.example.com/orders/ORD-102"
          }
        }
      }
    ]
  },
  "_links": {
    "first": {
      "href": "https://api.example.com/orders?page=0&size=2"
    },
    "prev": {
      "href": "https://api.example.com/orders?page=0&size=2"
    },
    "self": {
      "href": "https://api.example.com/orders?page=1&size=2"
    },
    "next": {
      "href": "https://api.example.com/orders?page=2&size=2"
    },
    "last": {
      "href": "https://api.example.com/orders?page=4&size=2"
    }
  },
  "page": {
    "size": 2,
    "totalElements": 10,
    "totalPages": 5,
    "number": 1
  }
}
~~~

Ví dụ giả định trang hiện tại là trang thứ hai theo cách đếm dành cho người dùng, tương ứng chỉ số 1 trong metadata Spring Data mặc định. Server có thể không trả tất cả relation trong mọi response. Ví dụ, trang đầu thường không có prev; trang cuối thường không có next. first và last cũng có thể được cấu hình để chỉ xuất hiện khi có prev/next.

## Link điều hướng và metadata có vai trò khác nhau

Metadata giúp client hiển thị thông tin về trang hiện tại. Link cho biết client có thể đi đâu tiếp theo.

| Thành phần | Ý nghĩa | Cách client sử dụng |
| --- | --- | --- |
| page.size | Kích thước trang được trả về | Hiển thị hoặc ghi nhận số phần tử tối đa mỗi trang |
| page.totalElements | Tổng số phần tử mà server báo cáo | Hiển thị tổng số kết quả nếu có |
| page.totalPages | Tổng số trang theo metadata | Hiển thị số trang hoặc thanh tiến trình |
| page.number | Chỉ số trang hiện tại | Hiển thị vị trí trang |
| _links.first | Trang đầu | Điều hướng về đầu collection |
| _links.prev | Trang trước | Quay lại trang liền trước |
| _links.self | Trang hiện tại | Tải lại đúng view hiện tại |
| _links.next | Trang tiếp theo | Tiếp tục đọc dữ liệu |
| _links.last | Trang cuối | Điều hướng tới cuối collection |

Với Spring Data, page number mặc định bắt đầu từ 0. Giao diện có thể hiển thị trang đầu là 1 bằng cách cộng 1 khi trình bày, nhưng không nên tự dùng con số hiển thị đó để tạo URL. Cấu hình server có thể thay đổi cách phân giải tham số pageable; link do server tạo phản ánh cấu hình thực tế.

Không suy ra rằng có trang tiếp theo chỉ vì page.number nhỏ hơn page.totalPages - 1. Hãy kiểm tra sự hiện diện của relation next. Tương tự, không tự tạo link prev bằng cách trừ 1 vào page number; hãy dùng link prev nếu server công bố.

## Quy trình điều hướng phía client

Một client đọc toàn bộ collection theo trang thường thực hiện các bước:

1. Gửi GET tới entry point hoặc URI collection ban đầu với Accept phù hợp, ví dụ application/hal+json.
2. Đọc các phần tử trong _embedded và xử lý dữ liệu của trang hiện tại.
3. Tìm relation next trong _links.
4. Nếu next tồn tại, gửi GET tới href của link đó và xử lý trang mới.
5. Lặp lại cho tới khi response không còn link next.

Nếu client chỉ cần một trang, có thể dừng ngay sau bước 2. Nếu người dùng bấm nút Next, client chỉ cần theo link next của trang đang hiển thị. Nút Previous tương tự sử dụng link prev.

~~~text
GET collection entry point
          |
          v
    Đọc trang hiện tại
          |
          v
    Xử lý các phần tử
          |
          v
    Có link rel=next?
       /       \
     Có         Không
      |           |
      v           v
  GET href     Kết thúc
  của next
      |
      +------> Đọc trang mới
~~~

Điều kiện dừng là không có link next. Client không cần biết tổng số trang, không cần đoán trang cuối và không cần dựa vào việc trang hiện tại có ít phần tử hơn page.size.

## Vì sao không tự tạo page và size?

Giả sử client nhận trang đầu tại /orders?page=0&size=20. Nếu client tự tăng page lên 1 để tạo trang kế tiếp, nó đang phụ thuộc vào nhiều giả định:

- API dùng tên query parameter page và size.
- Chỉ số trang bắt đầu từ 0.
- Server dùng offset pagination.
- Kích thước trang được giữ nguyên.
- Các filter và sort hiện tại phải được sao chép chính xác.
- URI không có prefix, version hoặc cursor riêng.

Các giả định này có thể sai khi API thay đổi. Link next có thể chứa query parameter bổ sung, token cursor, đường dẫn mới hoặc host khác. Theo link giúp client tôn trọng hợp đồng mà server công bố.

Metadata vẫn hữu ích để hiển thị trạng thái, nhưng không phải nguồn để tự dựng URI. Nếu API dùng cursor pagination, metadata có thể không có totalPages; client vẫn tiếp tục được bằng link next.

## Đọc PagedModel bằng RestTemplate

Spring HATEOAS cung cấp **HypermediaRestTemplateConfigurer** để đăng ký message converter hỗ trợ media type hypermedia. Khi đã cấu hình, RestTemplate có thể deserialize HAL response thành PagedModel và giữ lại các link.

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.hateoas.config.HypermediaRestTemplateConfigurer;
import org.springframework.web.client.RestTemplate;

@Configuration
class ClientConfiguration {

    @Bean
    RestTemplate hypermediaRestTemplate(
            HypermediaRestTemplateConfigurer configurer) {
        return configurer.registerHypermediaTypes(new RestTemplate());
    }
}
~~~

Nếu dùng Spring Boot, tài liệu Spring Boot khuyến nghị tạo RestTemplate qua RestTemplateBuilder. Có thể đăng ký converter hypermedia bằng RestTemplateCustomizer thay vì tự quản lý một RestTemplate dùng chung:

~~~java
import org.springframework.boot.web.client.RestTemplateCustomizer;
import org.springframework.context.annotation.Bean;
import org.springframework.hateoas.config.HypermediaRestTemplateConfigurer;
import org.springframework.web.client.RestTemplate;

@Bean
RestTemplateCustomizer hypermediaRestTemplateCustomizer(
        HypermediaRestTemplateConfigurer configurer) {
    return restTemplate -> configurer.registerHypermediaTypes(restTemplate);
}
~~~

Ví dụ cấu hình trên dành cho ứng dụng Spring Boot. Nếu tự cấu hình Spring không dùng Boot, có thể dùng bean RestTemplate ở ví dụ trước. Trong cả hai trường hợp, hãy bảo đảm client dùng đúng instance đã được đăng ký hypermedia converter.

Để đọc generic collection, dùng TypeReferences.PagedModelType. Kiểu này giữ thông tin kiểu phần tử khi Java runtime bị type erasure:

~~~java
import org.springframework.hateoas.EntityModel;
import org.springframework.hateoas.server.core.TypeReferences;

private static final TypeReferences.PagedModelType<EntityModel<OrderRepresentation>>
    ORDER_PAGE_TYPE = new TypeReferences.PagedModelType<>() {};
~~~

OrderRepresentation là DTO phía client dùng để đọc phần dữ liệu của một đơn hàng. Ví dụ:

~~~java
public record OrderRepresentation(String id, String status) {}
~~~

Trong ứng dụng thực tế, DTO này cần khớp với những trường client quan tâm trong representation.

## Tải một trang và theo link next

Ví dụ client tải lần lượt tất cả các trang đơn hàng:

~~~java
import java.net.URI;
import java.util.ArrayList;
import java.util.HashSet;
import java.util.List;
import java.util.Objects;
import java.util.Set;

import org.springframework.hateoas.EntityModel;
import org.springframework.hateoas.Link;
import org.springframework.hateoas.MediaTypes;
import org.springframework.hateoas.PagedModel;
import org.springframework.hateoas.server.core.TypeReferences;
import org.springframework.http.HttpEntity;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpMethod;
import org.springframework.http.ResponseEntity;
import org.springframework.web.client.RestTemplate;

class OrderPageClient {

    private static final TypeReferences.PagedModelType<EntityModel<OrderRepresentation>>
        PAGE_TYPE = new TypeReferences.PagedModelType<>() {};

    private final RestTemplate restTemplate;

    OrderPageClient(RestTemplate restTemplate) {
        this.restTemplate = restTemplate;
    }

    List<OrderRepresentation> readAll(URI firstPageUri) {
        List<OrderRepresentation> result = new ArrayList<>();
        Set<URI> visited = new HashSet<>();
        URI currentUri = firstPageUri;
        int pagesRead = 0;
        int maxPages = 10_000;

        HttpHeaders headers = new HttpHeaders();
        headers.setAccept(List.of(MediaTypes.HAL_JSON));
        HttpEntity<Void> request = new HttpEntity<>(headers);

        while (currentUri != null) {
            if (++pagesRead > maxPages) {
                throw new IllegalStateException(
                    "Pagination exceeded the configured page limit");
            }

            if (!visited.add(currentUri)) {
                throw new IllegalStateException(
                    "Pagination returned a previously visited URI: " + currentUri);
            }

            ResponseEntity<PagedModel<EntityModel<OrderRepresentation>>> response =
                restTemplate.exchange(
                    currentUri,
                    HttpMethod.GET,
                    request,
                    PAGE_TYPE
                );

            PagedModel<EntityModel<OrderRepresentation>> page =
                Objects.requireNonNull(response.getBody());

            for (EntityModel<OrderRepresentation> item : page.getContent()) {
                result.add(Objects.requireNonNull(item.getContent()));
            }

            URI pageUri = currentUri;
            currentUri = page.getNextLink()
                .map(Link::getHref)
                .map(URI::create)
                .map(pageUri::resolve)
                .orElse(null);

            if (currentUri != null) {
                assertSameOrigin(pageUri, currentUri);
            }
        }

        return result;
    }

    private static void assertSameOrigin(URI current, URI next) {
        boolean sameOrigin =
            Objects.equals(current.getScheme(), next.getScheme())
            && Objects.equals(current.getHost(), next.getHost())
            && effectivePort(current) == effectivePort(next);

        if (!sameOrigin) {
            throw new SecurityException(
                "Pagination link points to an untrusted origin: " + next);
        }
    }

    private static int effectivePort(URI uri) {
        if (uri.getPort() != -1) {
            return uri.getPort();
        }
        return "https".equalsIgnoreCase(uri.getScheme()) ? 443 : 80;
    }
}
~~~

Đoạn code dùng link next từ PagedModel. Link có thể chứa URI tuyệt đối hoặc tương đối; pageUri.resolve(...) biến URI tương đối thành URI có thể gọi được dựa trên trang hiện tại. Set visited giúp phát hiện server vô tình tạo vòng lặp link khiến client tải mãi một trang. Giới hạn maxPages bảo vệ tiến trình đồng bộ khỏi một chuỗi link quá dài. Hàm assertSameOrigin là chính sách ví dụ để tránh gửi lại cùng credential sang host khác; nếu API được thiết kế để chuyển sang nhiều origin, hãy thay bằng allowlist và cơ chế xác thực riêng cho từng origin.

Ví dụ lược bỏ phần xác thực, timeout và xử lý lỗi để tập trung vào luồng phân trang. Nếu API yêu cầu bearer token, client có thể thêm Authorization vào HttpHeaders. Khi theo link, chỉ chuyển thông tin xác thực tới origin được tin cậy; không gửi token cho host khác một cách tự động.

Nếu client chỉ tải một trang, không cần vòng lặp. Gọi một lần exchange(...), xử lý page.getContent() và sử dụng getNextLink() hoặc getPreviousLink() khi người dùng yêu cầu điều hướng.

## Dùng Traverson để khám phá relation

**Traverson** là API client-side của Spring HATEOAS để đi theo các link relation. Nó nhận URI entry point và media type, sau đó tìm relation cần theo trong representation:

~~~java
import java.net.URI;

import org.springframework.hateoas.MediaTypes;
import org.springframework.hateoas.PagedModel;
import org.springframework.hateoas.EntityModel;
import org.springframework.hateoas.client.Traverson;
import org.springframework.hateoas.server.core.TypeReferences;

Traverson traverson = new Traverson(
    URI.create("https://api.example.com/"),
    MediaTypes.HAL_JSON
);

TypeReferences.PagedModelType<EntityModel<OrderRepresentation>> pageType =
    new TypeReferences.PagedModelType<>() {};

PagedModel<EntityModel<OrderRepresentation>> firstPage =
    traverson.follow("orders").toObject(pageType);
~~~

Traverson gọi entry point, phát hiện relation orders và tải representation collection. Client có thể xử lý firstPage.getContent() rồi đọc firstPage.getNextLink(). Traverson cũng hỗ trợ follow nhiều relation liên tiếp, tùy chỉnh header và mở rộng URI template parameter. Với vòng lặp nhiều trang, client có thể lấy next link từ PagedModel hiện tại rồi tải href đó bằng HTTP client đã cấu hình hypermedia.

Không nhầm việc follow một chuỗi relation với việc tự động tải toàn bộ trang. Mỗi lần chuyển relation là một lần gọi HTTP để khám phá resource tiếp theo. Client vẫn cần quyết định khi nào tiếp tục, khi nào dừng và xử lý dữ liệu trang ra sao.

## Dùng WebClient trong ứng dụng reactive

Với client reactive, Spring HATEOAS cung cấp HypermediaWebClientConfigurer để đăng ký decoder và encoder cho các hypermedia media type:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.hateoas.config.HypermediaWebClientConfigurer;
import org.springframework.web.reactive.function.client.WebClient;

@Configuration
class ReactiveClientConfiguration {

    @Bean
    WebClient hypermediaWebClient(HypermediaWebClientConfigurer configurer) {
        return configurer.registerHypermediaTypes(WebClient.builder()).build();
    }
}
~~~

Sau khi cấu hình, client có thể tải một trang thành PagedModel trong Mono:

~~~java
import java.net.URI;

import org.springframework.hateoas.EntityModel;
import org.springframework.hateoas.MediaTypes;
import org.springframework.hateoas.PagedModel;
import org.springframework.hateoas.server.core.TypeReferences;
import org.springframework.web.reactive.function.client.WebClient;
import reactor.core.publisher.Mono;

class ReactiveOrderPageClient {

    private static final TypeReferences.PagedModelType<EntityModel<OrderRepresentation>>
        PAGE_TYPE = new TypeReferences.PagedModelType<>() {};

    private final WebClient webClient;

    ReactiveOrderPageClient(WebClient webClient) {
        this.webClient = webClient;
    }

    Mono<PagedModel<EntityModel<OrderRepresentation>>> loadPage(URI pageUri) {
        return webClient.get()
            .uri(pageUri)
            .accept(MediaTypes.HAL_JSON)
            .retrieve()
            .bodyToMono(PAGE_TYPE);
    }
}
~~~

Khi Mono phát ra PagedModel, client xử lý getContent() và đọc getNextLink() giống cách làm với RestTemplate. Hãy resolve URI tương đối theo URI của trang hiện tại trước khi gọi loadPage cho trang tiếp theo. Có thể kết hợp các lần tải bằng toán tử Reactor, nhưng cần giữ cả URI hiện tại và page model trong luồng để resolve link chính xác.

## Điều hướng trang trước và trang đầu/cuối

Khi người dùng quay lại trang trước, đọc link previous từ PagedModel:

~~~java
import java.net.URI;

import org.springframework.hateoas.Link;

URI previousPageUri = page.getPreviousLink()
    .map(Link::getHref)
    .map(URI::create)
    .map(currentPageUri::resolve)
    .orElse(null);
~~~

Đoạn code giả định currentPageUri là URI của trang đang hiển thị.

Trong API HAL, relation thường được serialize dưới tên prev; API Java của PagedModel cung cấp phương thức getPreviousLink(). Tương tự, client có thể tìm first hoặc last trong danh sách links nếu server công bố chúng:

~~~java
import org.springframework.hateoas.IanaLinkRelations;

page.getLink(IanaLinkRelations.FIRST);
page.getLink(IanaLinkRelations.LAST);
~~~

first và last không phải lúc nào cũng có mặt. PagedResourcesAssembler có cấu hình force first/last relation; mặc định chúng chỉ xuất hiện cùng với prev/next. Client nên kiểm tra link trước khi bật nút tương ứng.

Nếu server không công bố prev ở trang đầu hoặc next ở trang cuối, client nên vô hiệu hóa nút điều hướng tương ứng. Không tự tạo link dựa trên metadata.

## Hiển thị metadata cho người dùng

Client có thể dùng page metadata để hiển thị thông tin:

~~~java
PagedModel.PageMetadata metadata = page.getMetadata();

if (metadata != null) {
    long currentPageForDisplay = metadata.getNumber() + 1;
    long totalPages = metadata.getTotalPages();
    long totalElements = metadata.getTotalElements();
    long pageSize = metadata.getSize();
}
~~~

Trong ví dụ, số trang được cộng 1 chỉ để hiển thị cho người dùng. URI tiếp theo vẫn lấy từ link next. Metadata có thể không tồn tại trong một số representation hoặc loại collection khác; client cần kiểm tra null trước khi sử dụng.

Tổng số phần tử và tổng số trang có thể tốn chi phí tính toán ở server. Một API có thể chọn dạng slice hoặc cursor để chỉ công bố next/prev mà không cung cấp tổng số. Giao diện khi đó có thể hiển thị nút Next/Previous thay vì số trang cuối.

## Giữ filter và sort khi chuyển trang

Khi người dùng lọc đơn hàng theo trạng thái và sắp xếp theo ngày tạo, server có thể trả link next đã chứa đầy đủ tham số:

~~~json
{
  "_links": {
    "self": {
      "href": "https://api.example.com/orders?status=PENDING&sort=createdAt,desc&page=0&size=20"
    },
    "next": {
      "href": "https://api.example.com/orders?status=PENDING&sort=createdAt,desc&page=1&size=20"
    }
  }
}
~~~

Client không cần tự sao chép status, sort, page hoặc size. Theo href next sẽ giữ các điều kiện mà server đưa vào link. Điều này đặc biệt quan trọng khi có nhiều filter, tham số lặp, encoding hoặc tên tham số tùy chỉnh.

Khi người dùng thay đổi filter hoặc sort, client nên bắt đầu lại từ link collection/search phù hợp với tiêu chí mới. Không tiếp tục theo next link của bộ lọc cũ vì link đó đại diện cho một truy vấn khác.

## Offset pagination và cursor pagination

Client không nên giả định mọi API dùng số trang:

| Kiểu phân trang | Link next có thể chứa | Điều client cần làm |
| --- | --- | --- |
| Page/offset | page, size, sort và filter | Theo href mà server trả |
| Cursor/keyset | cursor hoặc token tiếp tục | Giữ nguyên token trong link |
| Slice | next/prev nhưng không nhất thiết có tổng số | Dừng khi không còn next |
| Phân trang tùy chỉnh | URI hoặc query parameter riêng | Xem link là nguồn điều hướng |

Với cursor pagination, token thường là dữ liệu opaque. Client không nên giải mã, sửa hoặc tự tạo token. Server chịu trách nhiệm tạo token tiếp tục và cung cấp URI tương ứng.

Offset pagination có thể gặp hiện tượng phần tử bị lặp hoặc bỏ sót khi dữ liệu thay đổi giữa các request. Ví dụ, một đơn hàng mới được chèn vào đầu danh sách sau khi client đã đọc trang đầu, làm vị trí các phần tử phía sau dịch chuyển. Nếu API cần duyệt dữ liệu ổn định trong thời gian dài, server có thể dùng cursor/keyset pagination hoặc snapshot semantics.

Ngay cả khi server dùng cursor, client vẫn theo next link theo cùng một thuật toán. Đây là lợi ích của việc điều hướng theo hypermedia.

## Xử lý lỗi và trạng thái dữ liệu thay đổi

Một link next được trả ở thời điểm trước có thể không còn sử dụng được khi client gửi request sau đó. Dữ liệu có thể đã thay đổi, quyền có thể bị thu hồi hoặc cursor có thể hết hạn.

Các trường hợp client cần xử lý:

- **401 Unauthorized:** token hết hạn hoặc thiếu xác thực; làm mới thông tin xác thực theo chính sách rồi thử lại có giới hạn.
- **403 Forbidden:** người dùng không còn quyền; dừng điều hướng và hiển thị trạng thái phù hợp.
- **404 Not Found hoặc 410 Gone:** trang/cursor không còn hợp lệ; tải lại collection entry point nếu nghiệp vụ cho phép.
- **429 Too Many Requests:** tôn trọng Retry-After nếu server gửi và giới hạn tốc độ gọi.
- **5xx:** có thể retry GET với backoff và giới hạn số lần thử.
- **Link next bị lặp:** phát hiện URI đã truy cập và dừng để tránh vòng lặp vô hạn.

GET là phương thức an toàn và idempotent theo ngữ nghĩa HTTP, nên có thể retry trong những điều kiện phù hợp. Tuy nhiên, retry phải có giới hạn và cần tôn trọng rate limit của server.

Không giả định totalElements hoặc totalPages luôn bất biến trong suốt quá trình duyệt. Nếu dữ liệu thay đổi, metadata của trang sau có thể khác metadata của trang trước. Với giao diện, hãy cập nhật theo response mới nhất thay vì giữ một tổng số cũ như sự thật tuyệt đối.

## Bảo mật khi theo link

Client thường gửi cookie hoặc bearer token khi gọi API. Khi server trả link tuyệt đối tới một origin khác, không nên tự động chuyển tiếp credential sang host mới. Hãy xác định origin được tin cậy hoặc dùng cơ chế xác thực riêng cho từng dịch vụ.

Nếu API nằm sau reverse proxy, link có thể dùng host công khai hoặc URI tương đối. Client nên xử lý cả hai dạng bằng cách resolve URI tương đối theo URI của response hiện tại. Không nối chuỗi URL thủ công vì dễ sai khi có context path hoặc encoding.

Client cũng nên đặt timeout, giới hạn số trang tối đa cho một lần đồng bộ và giới hạn tổng dữ liệu cần tải. Một API có thể có hàng triệu phần tử; việc theo next liên tục không đồng nghĩa client nên tải toàn bộ trong một request nghiệp vụ.

## Kiểm thử client pagination

Kiểm thử nên xác nhận client thực sự theo link next mà server trả về. Một test dùng MockRestServiceServer có thể chuẩn bị hai response HAL:

~~~java
import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.method;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.requestTo;
import static org.springframework.test.web.client.response.MockRestResponseCreators.withSuccess;

import java.net.URI;
import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.http.HttpMethod;
import org.springframework.hateoas.MediaTypes;
import org.springframework.test.web.client.MockRestServiceServer;

@Test
void followsNextLinkUntilThereIsNoNextPage() {
    MockRestServiceServer server =
        MockRestServiceServer.bindTo(restTemplate).build();

    server.expect(requestTo("https://api.example.com/orders"))
        .andExpect(method(HttpMethod.GET))
        .andRespond(withSuccess(FIRST_PAGE_HAL, MediaTypes.HAL_JSON));

    server.expect(requestTo("https://api.example.com/orders?cursor=next-abc"))
        .andExpect(method(HttpMethod.GET))
        .andRespond(withSuccess(LAST_PAGE_HAL, MediaTypes.HAL_JSON));

    List<OrderRepresentation> orders =
        client.readAll(URI.create("https://api.example.com/orders"));

    assertThat(orders).hasSize(4);
    server.verify();
}
~~~

FIRST_PAGE_HAL là fixture HAL có hai đơn hàng và link next trỏ tới URI cursor ở trên. LAST_PAGE_HAL có hai đơn hàng nhưng không có relation next. Test xác nhận client thực hiện đúng hai request và dừng sau trang cuối. Các fixture cần có cấu trúc _embedded.orders và _links phù hợp với DTO/model mà client deserialize.

Đoạn test là phần thân của một test class; restTemplate và client phải dùng cùng một RestTemplate đã cấu hình hypermedia converter. FIRST_PAGE_HAL và LAST_PAGE_HAL là các hằng String chứa response HAL của hai trang.

Ngoài test luồng thành công, nên kiểm thử:

- Trang đầu không có prev.
- Trang cuối không có next.
- Collection rỗng không làm client lặp vô hạn.
- Link tương đối được resolve đúng theo URI trang hiện tại.
- Filter và sort được giữ nguyên trong next href.
- Link next lặp lại URI đã truy cập sẽ làm client dừng hoặc báo lỗi.
- HTTP 401, 403, 404, 429 và 5xx được xử lý theo chính sách retry.
- Client không gửi credential tới origin ngoài danh sách tin cậy.

Nếu dùng WebClient trong ứng dụng reactive, Spring HATEOAS cung cấp HypermediaWebClientConfigurer để đăng ký encoder/decoder cho các hypermedia media type. Khi test WebTestClient, cũng cần áp dụng HypermediaWebTestClientConfigurer để deserialize representation model.

## Những lỗi thường gặp

- **Tự tăng page:** client tự tạo page + 1 và phụ thuộc cấu trúc query của server.
- **Dùng totalPages để dừng:** metadata có thể không có hoặc không phản ánh link điều hướng thực tế; hãy dừng khi thiếu next.
- **Giả định first/last luôn có:** server có thể chỉ công bố prev/next tùy trạng thái và cấu hình.
- **Bỏ query filter:** client tự tạo URI mới và làm mất điều kiện lọc/sắp xếp.
- **Không resolve URI tương đối:** link hợp lệ nhưng client không tạo được URI tuyệt đối để gửi request.
- **Lặp trang vô hạn:** client không phát hiện server trả lại URI đã truy cập.
- **Nhầm page number hiển thị với page index:** giao diện đếm từ 1 trong khi Spring Data mặc định đếm từ 0.
- **Chuyển token xác thực sang host khác:** có thể làm lộ credential.
- **Giả định dữ liệu không đổi:** offset pagination có thể lặp hoặc bỏ sót phần tử khi collection biến động.
- **Deserialize collection bằng raw List:** client mất metadata và links của PagedModel.

Pagination phía client trong Spring HATEOAS dựa trên việc đọc representation, xử lý các phần tử hiện tại và theo relation next/prev do server công bố. Dùng PagedModel để đọc metadata và link, RestTemplate hoặc WebClient đã cấu hình hypermedia để tải trang, và Traverson để khám phá relation từ entry point. Khi client không tự dựng URL và dừng theo sự hiện diện của link next, nó có thể làm việc với nhiều chiến lược phân trang mà không phụ thuộc vào chi tiết triển khai phía server.

## Tài liệu tham khảo

- [Spring HATEOAS – Client-side Support và Traverson](https://docs.spring.io/spring-hateoas/docs/current/reference/html/#client-side)
- [Spring HATEOAS API – PagedModel](https://docs.spring.io/spring-hateoas/docs/current/api/org/springframework/hateoas/PagedModel.html)
- [Spring HATEOAS API – Traverson](https://docs.spring.io/spring-hateoas/docs/current/api/org/springframework/hateoas/client/Traverson.html)
- [Spring HATEOAS API – HypermediaRestTemplateConfigurer](https://docs.spring.io/spring-hateoas/docs/current/api/org/springframework/hateoas/config/HypermediaRestTemplateConfigurer.html)
- [Spring HATEOAS API – TypeReferences.PagedModelType](https://docs.spring.io/spring-hateoas/docs/current/api/org/springframework/hateoas/server/core/TypeReferences.PagedModelType.html)
- [Spring Data Commons – PagedResourcesAssembler](https://docs.spring.io/spring-data/commons/docs/current/api/org/springframework/data/web/PagedResourcesAssembler.html)
