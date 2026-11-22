# Cấu hình địa chỉ gốc, URI, query parameter và header

Trong **SPRING_BOOT_INTEGRATION**, một adapter HTTP thường gọi nhiều endpoint của cùng đối tác, ví dụ lấy danh mục, kiểm tra đơn hàng hoặc gửi yêu cầu thanh toán. Dù đã chọn đúng `RestClient`, `WebClient` hay HTTP interface, ứng dụng vẫn có thể gọi **nhầm host**, tạo URI sai khi mã đơn hàng chứa dấu `/`, làm mất query parameter lặp hoặc đưa nhầm Bearer token của đối tác A sang đối tác B. Những lỗi này vừa ảnh hưởng độ tin cậy, vừa có thể thành sự cố bảo mật.

Bài thuộc chương **Lựa chọn HTTP client**, tập trung vào **cấu hình địa chỉ gốc (base URL), URI, query parameter và HTTP header**. Chúng ta sẽ xây URL bằng URI builder thay vì ghép chuỗi, quản lý cấu hình theo môi trường, hiểu encoding/escaping, phân biệt header chung với header theo request và kiểm chứng request thực tế qua các lớp HTTP của Spring Boot. Nội dung kết nối với hợp đồng DTO/JSON, deadline, idempotency, kiểm thử, quan sát và các adapter HTTP trong một luồng tích hợp có database, cache, broker hoặc Spring Integration.

> Các ví dụ hướng tới **Java 17+, Spring Boot 3.x, Spring Framework 6.x**. `RestClient` có từ Spring Framework 6.1 (tương ứng phổ biến với Spring Boot 3.2+); với bản Boot 3.0/3.1 chưa có API này, dùng `RestTemplate` hoặc `WebClient` theo phiên bản thực tế. Chúng ta không giả định mọi server đều diễn giải URI, giá trị query hoặc header theo cùng một hợp đồng.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt **URI, URL, origin, base URL, path, path segment, query string, fragment** và hostname.
2. Cấu hình một `baseUrl` cho HTTP adapter từ `application.yml` hoặc `@ConfigurationProperties` mà không hardcode endpoint trong application service.
3. Dùng `UriBuilder`, `pathSegment` và **URI template variables** để xây path an toàn cho ID có dấu cách, dấu chéo, Unicode và ký tự đặc biệt.
4. Xây query parameter tùy chọn, lặp lại, phân trang, thời gian và filter theo hợp đồng thay vì nối `?`/`&` thủ công.
5. Hiểu **percent-encoding**, `+` so với `%20`, cách tránh encode thiếu hoặc encode hai lần.
6. Phân biệt các header `Accept`, `Content-Type`, `Authorization`, `If-Match`, `Idempotency-Key`, correlation/trace headers và thứ tự áp dụng default/request headers.
7. Sử dụng `RestClient`, `WebClient` và declarative HTTP interface có chủ đích, kèm xác thực, allowlist đích và giới hạn input.
8. Kiểm thử method/path/query/header trên HTTP request thật, quan sát endpoint đã chuẩn hóa mà không rò rỉ token hoặc dữ liệu nhạy cảm.

## 2. Một HTTP URI có những thành phần nào?

Ví dụ request đến một dịch vụ danh mục:

```text
https://catalog.example.org:8443/api/v1/products/PRD-107?lang=vi&tag=java&tag=spring#details
└─┬──┘ └─────────┬────────┘└┬─┘└───────────┬───────────┘└─────────────┬────────────┘└──┬──┘
 scheme       host         port          path                  query            fragment
```

| Thành phần | Ví dụ | Vai trò |
| --- | --- | --- |
| Scheme | `https` | Giao thức cấp URL và yêu cầu bảo mật kết nối. |
| Authority/host/port | `catalog.example.org:8443` | Đích mạng; có thể đi qua DNS, proxy, TLS và load balancer. |
| Origin | `https://catalog.example.org:8443` | Scheme + host + port; hữu ích khi cấu hình client theo đối tác. |
| Base URL | `https://catalog.example.org:8443` hoặc `https://catalog.example.org:8443/api` | Mốc chung để giải quyết relative URI; quy tắc ghép path phải nhất quán. |
| Path | `/api/v1/products/PRD-107` | Đường dẫn tài nguyên. |
| Path segment | `api`, `v1`, `products`, `PRD-107` | Các đơn vị phân cách bởi dấu `/`; một ID động nên được coi là **một segment** nếu contract quy định vậy. |
| Query | `lang=vi&tag=java&tag=spring` | Các tham số, có thể nhiều giá trị cùng tên và có thứ tự khi server yêu cầu. |
| Fragment | `#details` | Dùng phía user-agent để định danh một phần tài nguyên, **không được gửi trong HTTP request-target lên server**. |

**URI không đồng nghĩa với mỗi path:** URI có thể là absolute (`https://...`) hoặc relative (`/api/v1/...`). `baseUrl` giúp các caller dùng một mốc chung; không nên nhầm `baseUrl` với `Host` header. HTTP engine chọn endpoint từ URI và cấu hình kết nối; chỉnh `Host` header tùy tiện không đảm bảo request được gửi tới host mong muốn và có thể gây mâu thuẫn TLS/SNI, proxy hoặc HTTP/2 authority.

### 2.1. Không hardcode URL ở mọi application service

Đây là một anti-pattern:

```java
// Dễ sai host khi chuyển môi trường, khó sửa đồng bộ.
String url = "https://catalog.example.org/api/products/" + productId;
```

Nếu có 20 endpoint, hardcode host/path ở nhiều chỗ làm thay môi trường từ sandbox sang production khó kiểm soát. Tách:

- **Cấu hình**: origin/base URL, TLS, proxy, timeout, credentials theo đối tác.
- **Adapter**: đường dẫn API, URI template, query parameter và header tương ứng hợp đồng.
- **Application service**: thao tác nghiệp vụ như `findProduct` hay `submitOrder`, không tự ghép URL.

Đây là sự tách biệt giữa **định tuyến kết nối** và **ngữ nghĩa nghiệp vụ**. HTTP client còn có connection pool, retry và transaction interactions, nhưng các chủ đề đó không thay thế trách nhiệm xây URL đúng.

## 3. Cấu hình base URL bằng Spring Boot

Spring Boot không có property phổ quát `spring.http.partner.base-url` được tự động hiểu cho từng đối tác. Hãy tạo namespace ứng dụng với `@ConfigurationProperties`.

```yaml
app:
  partners:
    catalog:
      base-url: ${CATALOG_BASE_URL:https://catalog.example.org}
      audience: products-v1
    billing:
      base-url: ${BILLING_BASE_URL:https://billing.example.org}
      audience: payments-v1
```

`audience` chỉ là metadata ứng dụng minh họa; nó không tự được gửi làm header hay cấu hình OAuth. Nếu dùng JWT/OAuth audience thực, phải thiết kế đúng cơ chế cấp token.

Record cấu hình có validation:

```java
import jakarta.validation.constraints.NotNull;
import java.net.URI;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "app.partners.catalog")
public record CatalogApiProperties(
        @NotNull URI baseUrl,
        String audience
) {
    public CatalogApiProperties {
        if (baseUrl != null && (
                !"https".equalsIgnoreCase(baseUrl.getScheme())
                || baseUrl.getHost() == null
                || baseUrl.getRawUserInfo() != null
                || baseUrl.getRawQuery() != null
                || baseUrl.getRawFragment() != null
                || (baseUrl.getRawPath() != null
                    && !baseUrl.getRawPath().isEmpty()
                    && !"/".equals(baseUrl.getRawPath())))) {
            throw new IllegalArgumentException(
                    "catalog base-url must be an HTTPS origin");
        }
    }
}
```

Ở ví dụ này, policy chấp nhận **HTTPS origin** để mọi path nghiệp vụ được xây từ `/v1/...`, tránh quy tắc ghép path khi base có sẵn `/api`. Có thể nới policy cho local development qua profile/test properties riêng, nhưng **không** được dùng một biến do HTTP caller cung cấp để chọn arbitrary host. `@Validated` cần hạ tầng Bean Validation, thường là `spring-boot-starter-validation` khi dự án dùng validation.

Kích hoạt properties bằng `@ConfigurationPropertiesScan` ở ứng dụng hoặc:

```java
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
@EnableConfigurationProperties(CatalogApiProperties.class)
public class CatalogPropertiesConfiguration {}
```

### 3.1. Base URL chung cho nhiều endpoint

| Environment | Cấu hình `base-url` | Endpoint xây từ adapter |
| --- | --- | --- |
| Local test | `https://catalog.test.example.org` | `/v1/products/{id}` |
| Staging | `https://catalog-staging.example.org` | `/v1/products/{id}` |
| Production | `https://catalog.example.org` | `/v1/products/{id}` |

Application service không đổi khi chuyển môi trường. Thay đổi hostname được quản lý bằng cấu hình triển khai; không đưa token vào base URL như `https://user:password@host`, không log credential và không dùng một URL do bên ngoài trả về làm nguồn kết nối thứ hai nếu chưa qua kiểm tra allowlist/SSRF.

### 3.2. Khi base URL có path prefix

Một số đối tác yêu cầu base `https://api.example.org/gateway/catalog`. Khi đó **đường dẫn tương đối, dấu `/` đầu/cuối và cấu hình `UriBuilderFactory`** có thể tác động cách ghép prefix. Không suy từ quy tắc resolve của browser rằng mọi overload Spring đều ghép như nhau.

Chọn **một quy ước**:

1. Cấu hình **chỉ origin** rồi mọi adapter cung cấp full API path như `/gateway/catalog/v1/products/{id}`; hoặc
2. Cho phép prefix trong base và kiểm tra request-target thực bằng integration test với builder/engine đúng version.

Tránh vừa ghi prefix trong base vừa thêm chính prefix đó trong `path(...)`, gây `/gateway/catalog/gateway/catalog/...`. Cũng tránh giả định URI absolute đưa vào client luôn được giữ nguyên base URL — một **absolute URI** có thể bỏ qua base đã cấu hình.

## 4. Xây URI bằng template và `UriBuilder` thay vì nối chuỗi

Ví dụ cần gọi:

```text
GET /v1/products/{productId}
```

`productId` có thể là `PRD-107`, `SKU A&B` hoặc một ID có dấu `/`. Khi nối chuỗi:

```java
// Sai nếu productId chứa /, ?, #, %, space hoặc Unicode đặc biệt.
String path = "/v1/products/" + productId;
```

một dấu `/` trong ID có thể bị hiểu thành **path separator**, `?` có thể mở query, `#` có thể mở fragment. Lựa chọn phù hợp hơn là URI template variable và `pathSegment` theo hợp đồng định danh:

```java
import java.net.URI;
import org.springframework.web.util.DefaultUriBuilderFactory;

public final class CatalogUriExamples {
    private final DefaultUriBuilderFactory factory =
            new DefaultUriBuilderFactory("https://catalog.example.org");

    public CatalogUriExamples() {
        factory.setEncodingMode(
                DefaultUriBuilderFactory.EncodingMode.TEMPLATE_AND_VALUES);
    }

    public URI productUri(String productId) {
        return factory.builder()
                .pathSegment("v1", "products", "{productId}")
                .build(productId);
    }
}
```

Với `TEMPLATE_AND_VALUES`, biến URI được xem là **giá trị dữ liệu cần encode**; khi `productId = "SKU A/B"`, ký tự `/` thuộc ID được biểu diễn như một phần của **segment** thay vì đổi thành hai segment. Đừng tự gọi `URLEncoder.encode(...)` cho path rồi đưa giá trị đã encode vào template; cách đó dễ tạo `%252F` (encode `%2F` thêm lần nữa).

### 4.1. `path(...)` khác `pathSegment(...)`

| Cách làm | Ý định | Rủi ro |
| --- | --- | --- |
| `path("/v1/products/{id}")` | Dùng một path template có separator cố định | Hợp lệ nếu URI variable được encode bằng policy thích hợp. |
| `pathSegment("v1","products","{id}")` | Dựng các segment, ID là **một segment** | Diễn đạt ý định rõ khi ID có dấu `/`; cần kiểm tra backend có chấp nhận `%2F` không. |
| `path("/v1/products/" + id)` | Ghép giá trị động trực tiếp vào cấu trúc path | Có thể đổi ý nghĩa path hoặc tạo URL sai/injection. |
| `URI.create(base + "/v1/products/" + id)` | Tạo URI từ chuỗi đã ghép | Không tự biết đoạn nào là dữ liệu cần escape, dễ lỗi với space, `?` và `#`. |

**Không có cách encoding nào sửa được hợp đồng API sai.** Một số gateway từ chối encoded slash (`%2F`) trong path vì chính sách bảo mật hoặc routing. Nếu đối tác quy định product IDs không được chứa slash, hãy **validate và từ chối ID đó**; nếu IDs có slash hợp lệ, cần test end-to-end qua chính gateway đang dùng.

### 4.2. Không dùng fragment để gửi dữ liệu server

`https://catalog.example.org/v1/products/123#private` không gửi `private` lên server qua HTTP request-target. Nếu cần truyền lựa chọn filter hoặc định danh phụ thuộc server, dùng path/query/header/body theo hợp đồng; đừng kỳ vọng server nhận fragment.

### 4.3. URI variable chứa phần trăm và double encoding

Ba kiểu giá trị khác nhau:

```text
Raw identifier:            A/B
Encoded path segment:      A%2FB
Double-encoded segment:    A%252FB
```

Nếu service nhận raw ID `A/B`, truyền raw ID vào builder **một lần** và để builder encode. Nếu upstream đã gửi `A%2FB` nhưng đó thực sự là **raw ID có dấu phần trăm**, encoding ra `A%252FB` lại là đúng. Điều cần xác định là **kiểu dữ liệu đầu vào** (raw hay pre-encoded) và ownership của encoding, không tự gọi `URLDecoder.decode` rồi encode lại nhiều lớp. Với các giá trị đã được giải mã từ một HTTP request, hãy quy định chúng là **raw business values** trước khi chuyển cho outbound adapter.

## 5. Query parameter: filter, phân trang, danh sách và ký tự đặc biệt

Query string là phần sau dấu `?` trong URI. Nó có thể mang bộ lọc, trang dữ liệu, mã ngôn ngữ, số lượng kết quả và nhiều giá trị cùng tên. Ví dụ:

```text
GET /v1/products?category=book&lang=vi&page=0&size=20&tag=java&tag=spring
```

Một cặp query không giống HTTP header. `category` có thể được định nghĩa trong hợp đồng API là tham số bắt buộc; `tag` có thể có nhiều giá trị. Query cần được **build với từng tên/giá trị** thay vì nối chuỗi `"?category=" + category + "&..."`.

### 5.1. `queryParam` cho giá trị đơn và lặp

```java
import java.net.URI;
import org.springframework.web.util.DefaultUriBuilderFactory;

public final class ProductSearchUris {
    private final DefaultUriBuilderFactory factory;

    public ProductSearchUris(String baseUrl) {
        factory = new DefaultUriBuilderFactory(baseUrl);
        factory.setEncodingMode(
                DefaultUriBuilderFactory.EncodingMode.TEMPLATE_AND_VALUES);
    }

    public URI search(
            String phrase, int page, int size) {

        if (phrase == null || phrase.isBlank()
                || page < 0 || size < 1 || size > 100) {
            throw new IllegalArgumentException("Invalid search arguments");
        }

        return factory.builder()
                .pathSegment("v1", "products")
                .queryParam("q", "{phrase}")
                .queryParam("page", page)
                .queryParam("size", size)
                .build(phrase);
    }

    public URI searchByTags() {
        return factory.builder()
                .pathSegment("v1", "products")
                .queryParam("tag", "java", "spring")
                .build();
    }
}
```

Ý nghĩa `queryParam("tag", "java", "spring")`: một tên **`tag`** xuất hiện nhiều lần; tương ứng dạng query `tag=java&tag=spring` trong nhiều API. Không thay bằng `tag=java,spring` nếu hợp đồng đối tác quy định **repeated parameter**. Cũng không tự suy ngược rằng server hỗ trợ danh sách qua comma chỉ vì một framework có converter cho `List<String>`.

Đối với giá trị động chứa `&`, dấu `?`, dấu bằng hoặc `#`, dùng **URI template variable** như `"{phrase}"` rồi gọi `build(phrase)`. Không gộp giá trị người dùng vào một chuỗi URI template trước khi build:

```java
// Dễ thay đổi ý nghĩa truy vấn khi user nhập &, #, = hoặc ?.
String uri = "/v1/products?q=" + phrase;

// Tách cấu trúc và dữ liệu để encoder xử lý.
builder.path("/v1/products")
       .queryParam("q", "{phrase}")
       .build(phrase);
```

### 5.2. Tham số tùy chọn: khác nhau giữa thiếu, rỗng và literal `null`

Ba request có thể mang nghĩa khác nhau:

```text
GET /v1/products
GET /v1/products?category=
GET /v1/products?category=null
```

| Query | Server có thể hiểu là | Lưu ý |
| --- | --- | --- |
| Không có `category` | Không áp filter category | Thường dùng khi tham số tùy chọn vắng mặt. |
| `category=` | Có filter nhưng giá trị rỗng | Có API xem là invalid; có API xem là danh mục rỗng. |
| `category=null` | Chuỗi ký tự "null" | **Không** mặc định là null của Java/JSON. |
| `category` không có dấu `=` | Flag/presence parameter | Semantics phụ thuộc API; không tự thay bằng `category=true`. |

Hãy xây tùy chọn **có chủ đích**:

```java
import java.net.URI;
import org.springframework.web.util.UriBuilder;
import org.springframework.web.util.DefaultUriBuilderFactory;

public final class OptionalProductUris {
    private final DefaultUriBuilderFactory factory;

    public OptionalProductUris(String baseUrl) {
        factory = new DefaultUriBuilderFactory(baseUrl);
    }

    public URI list(String category, Integer size) {
        UriBuilder builder = factory.builder().path("/v1/products");

        if (category != null && !category.isBlank()) {
            builder.queryParam("category", "{category}");
        }
        if (size != null) {
            if (size < 1 || size > 100) {
                throw new IllegalArgumentException("Invalid size");
            }
            builder.queryParam("size", size);
        }

        return (category != null && !category.isBlank())
                ? builder.build(category)
                : builder.build();
    }
}
```

Ở đây chỉ **bỏ qua** category trống theo contract được giả định. Nếu đối tác phân biệt “filter rỗng” với “filter vắng”, cần biểu diễn cả hai theo mô hình input cụ thể chứ không dùng `String`/`null` tùy tiện.

**Một hạn chế quan trọng của ví dụ:** tên biến URI template `{category}` là một thành phần của query; khi mở rộng các URI template khác trong cùng builder, có thể dùng `Map.of("category", category)` để tránh nhầm thứ tự tham số. Với nhiều field tùy chọn, dùng một map mở rộng rõ ràng hoặc factory method tạo URI sẽ dễ bảo trì hơn việc đặt tên biến theo vị trí.

### 5.3. Cấu trúc query động theo allowlist

Nếu HTTP API nhận `sort`, `fields`, `page` và `size` từ caller, không chuyển nguyên input thành URI của đối tác không kiểm soát. Ví dụ `sort=price,desc` phải phù hợp field được phép:

```java
import java.util.Set;

public final class ProductSortPolicy {
    private static final Set<String> SORT_FIELDS =
            Set.of("name", "price", "createdAt");

    public static String validateSort(String field, boolean descending) {
        if (!SORT_FIELDS.contains(field)) {
            throw new IllegalArgumentException("Unsupported sort field");
        }
        return field + (descending ? ",desc" : ",asc");
    }
}
```

Builder chỉ đảm bảo **URI syntax/encoding**, không đảm bảo người gọi được phép yêu cầu một trường dữ liệu, filter hoặc trang bất kỳ. Phải áp validation cho giá trị nghiệp vụ và giới hạn page size; tránh để một người dùng làm adapter tải hàng triệu rows từ đối tác rồi `collectList()` vào RAM.

### 5.4. Thời gian, số thập phân và locale

Một query `from`/`to` cần có hợp đồng rõ:

```text
GET /v1/orders?from=2026-11-21T00%3A00%3A00Z&to=2026-11-22T00%3A00%3A00Z
```

Ví dụ chuyển `Instant` sang chuỗi ISO-8601 UTC:

```java
import java.net.URI;
import java.time.Instant;
import java.time.format.DateTimeFormatter;
import org.springframework.web.util.UriBuilderFactory;

public URI ordersInWindow(
        UriBuilderFactory factory, Instant from, Instant to) {
    if (from == null || to == null || !from.isBefore(to)) {
        throw new IllegalArgumentException("Invalid time window");
    }
    String fromIso = DateTimeFormatter.ISO_INSTANT.format(from);
    String toIso = DateTimeFormatter.ISO_INSTANT.format(to);

    return factory.builder()
            .path("/v1/orders")
            .queryParam("from", "{from}")
            .queryParam("to", "{to}")
            .build(java.util.Map.of("from", fromIso, "to", toIso));
}
```

Hợp đồng có thể yêu cầu epoch milliseconds, timezone offset, ngày-only hay một format khác; không dùng `Date.toString()` hoặc `Locale` của máy chủ mặc định. Với số tiền, nên dùng `BigDecimal.toPlainString()` khi API yêu cầu decimal text và quy tắc scale/currency đã được định nghĩa, không đi qua `double` rồi chịu rounding không mong muốn.

## 6. Percent-encoding: một sai khác nhỏ có thể làm sai bộ lọc

Trong URI, một số ký tự là **reserved** vì chúng có thể có ý nghĩa cấu trúc (`/`, `?`, `#`, `&`, `=`...). **Percent-encoding** biểu diễn bytes bằng `%HH` khi cần. Nhiều URI builder dùng UTF-8 cho ký tự Unicode; đừng tự coi “mỗi Java char = một byte”.

| Giá trị raw | Khi encode như dữ liệu URI | Điều cần chú ý |
| --- | --- | --- |
| `A B` | Thường `A%20B` trong URI encoding | Không tự thay mọi dấu cách bằng `+` trừ khi contract dùng form encoding. |
| `C++` | `C%2B%2B` nếu dấu `+` cần giữ nghĩa literal trong query value | Nhiều server form-decode `+` thành dấu cách. |
| `A&B` | `A%26B` trong một query value | Nếu nối chuỗi, `&` có thể tạo query param khác. |
| `R&D=1` | `R%26D%3D1` khi cả chuỗi là value | Dấu `=` không phải cặp name/value mới. |
| `A/B` | `A%2FB` khi là **một path segment** và dùng encoding phù hợp | Encoded slash có thể bị proxy/server từ chối hoặc xử lý đặc biệt. |
| `100%` | `100%25` | Encode lại giá trị pre-encoded sai cách có thể tạo `%2525`. |
| `cà phê` | UTF-8 percent encoding trong URI thực | Test qua client và server thực thay vì giả định chỉ từ log Unicode. |

### 6.1. `URLEncoder` dành cho HTML form, không phải mọi URI component

Trong Java:

```java
String encoded = java.net.URLEncoder.encode(
        "C++ basics", java.nio.charset.StandardCharsets.UTF_8);
// Dạng form-style có thể chứa dấu + để biểu diễn space.
```

`URLEncoder` dùng quy ước `application/x-www-form-urlencoded`: **dấu cách thành `+`**. Nếu dùng nó để tự encode một path segment rồi truyền tiếp vào `UriBuilder`, kết quả có thể khác hợp đồng và bị encode hai lần. Dùng URI builder của Spring, đồng thời test giá trị chứa dấu cộng, space, dấu phần trăm và Unicode với phía server thực sự nhận.

### 6.2. Các encoding modes của `DefaultUriBuilderFactory`

Spring hỗ trợ cấu hình `DefaultUriBuilderFactory.EncodingMode`. Những mode chính cần hiểu:

| Mode | Ý định | Khi nào cân nhắc |
| --- | --- | --- |
| `TEMPLATE_AND_VALUES` | Encode URI template và **encode URI variables chặt chẽ** như dữ liệu | Lựa chọn an toàn/thông dụng cho ID, keyword và query value từ ứng dụng. |
| `VALUES_ONLY` | Không pre-encode template như mode trên, nhưng encode variables chặt chẽ | Khi template đã được chuẩn hóa và cần kiểm soát encoding riêng ở template. |
| `URI_COMPONENT` | Mở rộng variables trước, rồi encode các URI components; có thể giữ một số reserved chars hợp lệ ở vị trí đó | Phải hiểu rõ khi value chứa reserved char và semantics backend. |
| `NONE` | Không tự encode | Chỉ phù hợp với dữ liệu/template **đã bảo đảm encoded đúng**, không nên dùng cho input không tin cậy. |

Mặc định cụ thể có thể khác theo lớp/cách cấu hình và phiên bản Spring; khi thiết kế client dùng chung, **đặt encoding mode có chủ đích** để giảm bất ngờ sau upgrade. Không đặt `NONE` toàn cục để “sửa lỗi double encode” nếu upstream đang truyền raw user input. Hãy sửa ranh giới raw/pre-encoded và có test kiểm tra request-target thực.

### 6.3. Tránh hai lần encode khi truyền `URI` đã dựng sẵn

Có khác biệt giữa:

```java
client.get().uri("/v1/products/{id}", rawProductId);
```

và:

```java
URI alreadyBuilt = uriBuilderFactory.builder()
        .pathSegment("v1", "products", "{id}")
        .build(rawProductId);
client.get().uri(alreadyBuilt);
```

Overload nhận **`URI`** thể hiện: “URI đã được dựng, đưa nó tới client”; overload nhận **String template + variables** cho framework cơ hội expand/encode. Tránh lấy chuỗi `alreadyBuilt.toString()` rồi đưa qua một builder thứ hai với kỳ vọng nó không encode lại. Nên có **một thành phần sở hữu encoding** trong outbound adapter và test chính xác từng ký tự có ý nghĩa đối với đối tác.

## 7. Query string không phải một `Map<String,String>` đơn giản

Các vấn đề cần giữ trong hợp đồng:

- Một name có thể xuất hiện nhiều lần: `tag=java&tag=spring`.
- Có khác biệt giữa name không xuất hiện, name không có value và name có value rỗng.
- Server có thể quan tâm tới **thứ tự tham số**, đặc biệt khi tính chữ ký HMAC hoặc canonical request.
- Tên tham số có thể phân biệt chữ hoa/thường theo hợp đồng, mặc dù HTTP header names thì case-insensitive.
- Có API dùng bracket notation như `filter[status]=ACTIVE` hoặc `ids[]=1&ids[]=2`; không mặc định mọi server hỗ trợ.
- Giá trị query có thể chứa Unicode/`+`/`&`, cần encode theo contract thực tế.

**Đừng chuyển query sang một map thường rồi mất nhiều giá trị cùng tên.** Nếu cần đọc/giữ repeated params ở Spring Web, dùng kiểu như `MultiValueMap<String,String>` thay vì `Map<String,String>`. Khi gửi outbound, dùng `queryParam` cho từng giá trị hoặc API hỗ trợ nhiều giá trị thích hợp.

### 7.1. Vì sao chữ ký HMAC dễ hỏng dù URL vẫn mở được?

Một số đối tác yêu cầu chữ ký dựa trên canonical request gồm **path, query, header và body hash**. Nếu bạn ký:

```text
tag=java&tag=spring
```

nhưng một interceptor đảo thứ tự, encode space từ `%20` thành `+` hoặc loại tham số trùng, chữ ký có thể khác dù người dùng nhìn thấy cùng bộ lọc. Cần đọc **đúng specification canonicalization** của đối tác: sort hay giữ nguyên thứ tự, percent-encoding thế nào, ký headers nào, dùng bytes nào, timestamp/window nào.

Một URI builder đơn lẻ **không tự triển khai** HMAC signing. Nếu có cơ chế ký request, hãy xây/canonicalize request trước khi ký, bảo đảm HTTP engine gửi đúng representation đã ký và có test đối chiếu canonical string với fixture chính thức của đối tác.

## 8. `RestClient`: cấu hình URI builder và default headers một lần

`RestClient` của Spring Framework 6.1+ cung cấp fluent synchronous HTTP client. Trong Spring Boot, nên inject `RestClient.Builder` do Boot quản lý để nhận customizers/message converters/observation phù hợp, rồi dựng **một client theo đối tác** khi khởi động, thay vì `RestClient.create()` rải rác trong mỗi request.

### 8.1. Spring bean chứa URI policy

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.web.client.RestClient;
import org.springframework.web.util.DefaultUriBuilderFactory;

@Configuration(proxyBeanMethods = false)
public class CatalogHttpClientConfiguration {

    @Bean
    RestClient catalogRestClient(
            RestClient.Builder bootBuilder,
            CatalogApiProperties properties) {

        var uriFactory = new DefaultUriBuilderFactory(
                properties.baseUrl().toString());
        uriFactory.setEncodingMode(
                DefaultUriBuilderFactory.EncodingMode.TEMPLATE_AND_VALUES);

        return bootBuilder
                .uriBuilderFactory(uriFactory)
                .defaultHeader(
                        HttpHeaders.ACCEPT,
                        MediaType.APPLICATION_JSON_VALUE)
                .build();
    }
}
```

`CatalogApiProperties` là bean đã đăng ký ở phần 3. Ở đây **`uriBuilderFactory(...)` sở hữu cả base URL và quy tắc encoding**; không cần đồng thời gọi `baseUrl(...)` một lần nữa rồi đoán phương thức nào có ưu tiên. `defaultHeader(Accept, application/json)` là policy **tĩnh**, không chứa thông tin người dùng hoặc token có thể đổi.

Nếu dùng nhiều `RestClient` beans:

```java
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.stereotype.Component;
import org.springframework.web.client.RestClient;

@Component
public class CatalogProductAdapter {
    private final RestClient client;
    private final PartnerTokenProvider tokenProvider;

    public CatalogProductAdapter(
            @Qualifier("catalogRestClient") RestClient client,
            PartnerTokenProvider tokenProvider) {
        this.client = client;
        this.tokenProvider = tokenProvider;
    }

    public ProductDto findProduct(
            String productId, String language, String correlationId) {

        if (productId == null || productId.isBlank()) {
            throw new IllegalArgumentException("Missing productId");
        }
        if (!java.util.Set.of("vi", "en").contains(language)) {
            throw new IllegalArgumentException("Unsupported language");
        }

        return client.get()
                .uri(uri -> uri
                        .pathSegment("v1", "products", "{id}")
                        .queryParam("lang", "{lang}")
                        .build(java.util.Map.of(
                                "id", productId,
                                "lang", language)))
                .headers(headers -> {
                    headers.setBearerAuth(
                            tokenProvider.tokenForCatalog());
                    headers.set("X-Correlation-ID", correlationId);
                })
                .retrieve()
                .body(ProductDto.class);
    }
}

public record ProductDto(String id, String name) {}

public interface PartnerTokenProvider {
    String tokenForCatalog();
}
```

Trong project thực, các `public` top-level types đặt vào file Java riêng. `PartnerTokenProvider` là interface **do ứng dụng triển khai**: có thể đọc token ứng dụng hoặc tích hợp OAuth2 Authorized Client theo chính sách. Nó phải trả token **không có tiền tố `Bearer `** để `setBearerAuth` gắn prefix đúng một lần. `correlationId` phải được kiểm tra không null/ký tự điều khiển và lấy từ nguồn trace/edge policy đáng tin cậy; không truyền một header bất kỳ từ HTTP inbound ra đối tác mà thiếu lọc.

**Vì sao `@Qualifier` quan trọng?** Khi có cả `catalogRestClient` và `billingRestClient`, ứng dụng không nên phụ thuộc tên bean mặc định để vô tình tiêm client sai host hoặc sai credential. Chọn bean theo **đối tác và nhiệm vụ** giúp code review thấy rõ request này đi đâu.

### 8.2. Lỗi HTTP status phải được ánh xạ tại adapter

`retrieve().body(...)` có thể ném exception trên phản hồi 4xx/5xx theo xử lý mặc định. Adapter không nên tự trả `null` cho mọi trường hợp:

- `404` khi tìm product có thể là **không tồn tại** theo contract, cần map `ProductNotFoundException`.
- `429` có thể báo **rate limit** kèm `Retry-After`; không retry ngay vô hạn.
- `401/403` thường là vấn đề xác thực/phân quyền; tăng pool hay gửi lại cùng token liên tục không giúp.
- `5xx` và network timeout có thể là lỗi tạm thời; đặt deadline/retry có giới hạn khi thao tác an toàn.
- Body 2xx không đúng schema là **contract error**, không được âm thầm map thành DTO rỗng.

Trong adapter có thể dùng `onStatus(...)` hoặc tầng exception mapping theo API Spring tương ứng. Dù lỗi gì, nên tránh log nguyên response chứa PII/token; giới hạn kích thước body lỗi trước khi ghi log hoặc metric.

## 9. `WebClient`: URI policy tương tự, vòng đời reactive khác

`WebClient` dùng Reactor/Reactive Streams và có `WebClient.Builder` do Boot cấu hình khi có WebFlux tương ứng. Nó vẫn sử dụng các khái niệm **base URL, URI template, query parameter và headers** như `RestClient`.

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.web.reactive.function.client.WebClient;
import org.springframework.web.util.DefaultUriBuilderFactory;

@Configuration(proxyBeanMethods = false)
public class CatalogWebClientConfiguration {

    @Bean
    WebClient catalogWebClient(
            WebClient.Builder bootBuilder,
            CatalogApiProperties properties) {

        var factory = new DefaultUriBuilderFactory(
                properties.baseUrl().toString());
        factory.setEncodingMode(
                DefaultUriBuilderFactory.EncodingMode.TEMPLATE_AND_VALUES);

        return bootBuilder
                .uriBuilderFactory(factory)
                .defaultHeader(
                        HttpHeaders.ACCEPT,
                        MediaType.APPLICATION_JSON_VALUE)
                .build();
    }
}
```

Gọi sản phẩm theo `id` và `lang`:

```java
import java.util.Map;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.stereotype.Component;
import org.springframework.web.reactive.function.client.WebClient;
import reactor.core.publisher.Mono;

@Component
public class ReactiveCatalogProductAdapter {
    private final WebClient client;
    private final PartnerTokenProvider tokens;

    public ReactiveCatalogProductAdapter(
            @Qualifier("catalogWebClient") WebClient client,
            PartnerTokenProvider tokens) {
        this.client = client;
        this.tokens = tokens;
    }

    public Mono<ProductDto> findProduct(
            String id, String lang, String correlationId) {
        if (id == null || id.isBlank()) {
            return Mono.error(new IllegalArgumentException("Missing id"));
        }

        return client.get()
                .uri(uri -> uri
                        .pathSegment("v1", "products", "{id}")
                        .queryParam("lang", "{lang}")
                        .build(Map.of("id", id, "lang", lang)))
                .headers(headers -> {
                    headers.setBearerAuth(tokens.tokenForCatalog());
                    headers.set("X-Correlation-ID", correlationId);
                })
                .retrieve()
                .bodyToMono(ProductDto.class);
    }
}
```

Đây là ví dụ về **URI và header policy**, không phải mẫu OAuth2 token refresh hoàn chỉnh. `tokens.tokenForCatalog()` chạy trong quá trình xây request khi subscriber thực thi; nếu việc cấp token phải gọi HTTP/blocking storage, **không** làm blocking call trên Reactor event loop. Khi dùng OAuth2, ưu tiên cơ chế reactive authorized client/filter của Spring Security OAuth2 phù hợp với version hiện tại.

**Không gọi `subscribe()` tự do rồi trả về “đã xử lý”** trong consumer Kafka/AMQP/Spring Integration: kết quả HTTP có thể thất bại sau khi message đã được ack. Giữ publisher trong lifecycle được quản lý, timeout/deadline và idempotency của tác vụ nghiệp vụ.

### 9.1. Hai client có thể dùng cùng contract nhưng không cùng resource policy

`RestClient` và `WebClient` đều hiểu URI template, nhưng transport/pool và thread model khác nhau. Một ứng dụng dùng `WebClient` trên `Reactor Netty` có event loop và `ConnectionProvider`; `RestClient` có thể dùng Apache HttpClient/JDK engine. **Chọn client theo mô hình caller**, sau đó thống nhất **URI + header contract** bằng adapter/test; không suy rằng cùng cấu hình base URL nghĩa là dùng cùng TCP connection pool.

## 10. Header HTTP: loại nào và đặt ở đâu?

Header là metadata của HTTP message. Tên header về nguyên tắc **case-insensitive**, nhưng giá trị có thể có ngữ nghĩa phức tạp; một số header có thể xuất hiện nhiều lần hoặc mang danh sách. Không coi header là một map text muốn ghi gì cũng được.

| Header | Vai trò thường gặp | Policy khuyến nghị |
| --- | --- | --- |
| `Accept` | Client muốn server trả media type nào | Ví dụ `application/json`; không đồng nghĩa nội dung body gửi đi. |
| `Content-Type` | Media type **body request** khi có body | Ví dụ `application/json` với POST/PUT; không cần tùy tiện gắn lên GET không có body. |
| `Authorization` | Xác thực request, thường Bearer/Basic theo hợp đồng | Lấy theo đối tác/request; **không log** hoặc chia token qua client sai đích. |
| `Accept-Language` | Ngôn ngữ nội dung mong muốn | Theo hợp đồng và danh sách ngôn ngữ cho phép, không auto-trust input. |
| `Idempotency-Key` | Nhận diện một thao tác logic để đối tác xử lý retry an toàn khi hỗ trợ | Giữ **cùng key qua các attempts** của cùng một lệnh. |
| `X-Correlation-ID` / `X-Request-ID` | Liên kết log/trace giữa hệ thống | Quy ước tên/nguồn/format, không dùng như khóa chống trùng nếu semantics khác. |
| `traceparent` / `tracestate` | W3C distributed tracing | Để instrumentation theo chính sách propagate, tránh tự đè header trace. |
| `If-Match` | Điều kiện optimistic concurrency dựa trên ETag | Dùng khi update yêu cầu version tài nguyên. |
| `If-None-Match` | Truy vấn có điều kiện/kiểm tra cache với ETag | Xử lý `304 Not Modified` theo contract. |
| `User-Agent` | Nhận diện client ứng dụng/thư viện | Có thể đặt giá trị ổn định theo ứng dụng, không chứa dữ liệu người dùng. |
| `Cookie` | Trạng thái phiên theo một giao thức | Không tự chuyển cookie người dùng tới API đối tác nếu không có yêu cầu và quyền. |
| `Host` / HTTP/2 `:authority` | Tên authority ở tầng HTTP routing | Để transport xây nhất quán với URI/TLS; tránh tự spoof để đổi đích. |

### 10.1. `Accept` khác `Content-Type`

Request GET trả JSON:

```http
GET /v1/products/PRD-107?lang=vi HTTP/1.1
Host: catalog.example.org
Accept: application/json
```

Request POST gửi JSON và nhận JSON:

```http
POST /v1/orders HTTP/1.1
Host: billing.example.org
Accept: application/json
Content-Type: application/json
Idempotency-Key: pay-req-892

{"orderId":"ORD-892","amount":125000}
```

`Accept: application/json` mô tả **representation mong muốn của response**, `Content-Type: application/json` mô tả **representation của body request**. Nếu server trả `Content-Type: application/problem+json` khi lỗi, client phải đọc/mapping lỗi theo media type/hợp đồng, không giả định mọi JSON response đều là DTO thành công.

### 10.2. Default headers và per-request headers

**Default header** phù hợp với những giá trị ổn định của client/đối tác như `Accept: application/json`. **Per-request header** dành cho token, correlation ID, idempotency key, ETag hoặc tenant context có thể đổi.

Với Spring HTTP API, `defaultHeader(...)` là một **giá trị mặc định** khi request chưa có header tương ứng theo contract của builder. Nhưng hành vi giữa `header(name, value)` (có thể **thêm** giá trị) và `headers(h -> h.set(name, value))` (**đặt/thay**) khác nhau; nếu một header chỉ được phép có **một** giá trị, ưu tiên `set(...)` theo request:

```java
client.get()
        .uri("/v1/products/{id}", productId)
        .headers(h -> {
            h.setAccept(java.util.List.of(
                    org.springframework.http.MediaType.APPLICATION_JSON));
            h.set("X-Correlation-ID", correlationId);
        })
        .retrieve()
        .body(ProductDto.class);
```

Tránh để hai giá trị `Authorization` khác nhau trong một request do vừa có default Bearer token vừa gọi `header("Authorization", ...)` ở adapter khác. Với nhiều token/tenant, **đừng đặt Bearer token động làm một default header toàn cục** trên singleton client rồi cập nhật mỗi lần gọi.

### 10.3. Header có nhiều giá trị và case-insensitivity

Tên header `accept`, `Accept`, `ACCEPT` đều được hiểu như cùng header theo HTTP semantics, dù bộ thư viện có thể giữ cách viết khác trong log. Khi kiểm tra, dùng API `HttpHeaders.getFirst("...")` hoặc `get(...)` theo semantics, không so chuỗi raw header block theo letter case. Một số header cho phép nhiều values theo danh sách, nhưng **không** tự gộp mọi header bằng dấu phẩy, đặc biệt những trường có grammar hoặc security semantics riêng. Kiểm thử header multi-value theo HTTP specification và hợp đồng đối tác.

## 11. Header bảo mật: Bearer, Basic, API key và chứng chỉ

**Xác thực** của outbound request không phải lúc nào cũng là một `Authorization` header. Tùy API đối tác:

- **Bearer token**: thường dùng `Authorization: Bearer <token>`, có thể là access token OAuth2 cần refresh trước khi hết hạn.
- **Basic authentication**: chỉ sử dụng nếu đối tác yêu cầu và kết nối đã được bảo vệ bằng TLS; username/password được encode theo quy tắc, không phải mã hóa bí mật.
- **API key**: có thể nằm trong `X-API-Key` hoặc header riêng theo specification; không tự đổi tên hay nhét key vào query nếu không được phép.
- **mTLS**: danh tính client nằm ở tầng **TLS certificate/handshake**, không phải header có thể thêm vào code Spring.
- **HMAC signing**: cần canonicalize method, path, query, headers, body hash theo hợp đồng; không có một `Authorization` chung áp dụng cho mọi nhà cung cấp.

### 11.1. Bearer token theo mỗi request

```java
String token = tokenProvider.tokenForCatalog();

ProductDto response = catalogRestClient.get()
        .uri(uri -> uri
                .pathSegment("v1", "products", "{id}")
                .build(productId))
        .headers(headers -> headers.setBearerAuth(token))
        .retrieve()
        .body(ProductDto.class);
```

**Không** khởi tạo `RestClient` singleton bằng một token ngắn hạn rồi hy vọng nó tự refresh sau 60 phút. Nếu dùng OAuth2 client credentials, nên dùng cơ chế token management/authorized client tương ứng với Spring Security, cache và refresh có kiểm soát, thay vì đặt `@Value("${PARTNER_TOKEN}")` cố định khi khởi động rồi không bao giờ cập nhật.

### 11.2. Header và URI phải cùng một đối tác

Nguy cơ:

```text
catalogRestClient có Authorization: Bearer catalog-token
caller truyền URI tuyệt đối: https://attacker.example/path
=> request có thể đi khỏi host catalog nhưng vẫn mang credential
```

Base URL **có thể bị override** khi caller dùng URI absolute ở nhiều API Spring. Vì vậy:

1. Không cho HTTP input cung cấp arbitrary outbound URL.
2. Giới hạn đích đến các origin được cấu hình/allowlist; dùng relative paths do adapter kiểm soát.
3. Nếu cần gọi URL hoàn toàn khác qua redirect hoặc presigned URL, dùng **client/credential policy riêng**.
4. Kiểm tra redirect policy ở HTTP transport. Không dựa vào giả định “thư viện chắc chắn không chuyển Authorization khi redirect cross-origin” mà chưa kiểm chứng engine/version.
5. Với mTLS, tách HTTP engine/pool khi certificate/trust policy giữa đối tác khác nhau.

**Không log Bearer token, Basic credentials, API key hoặc chữ ký HMAC** vào request debug log, trace attribute, metric tag hay error body. Query string cũng có thể bị ghi vào server/proxy access log; nếu API có lựa chọn truyền secret trong header thay vì query, nên tuân theo cách an toàn đã được hợp đồng hỗ trợ.

### 11.3. Không chuyển tiếp nguyên các inbound headers

Khi một Spring Boot controller nhận request từ người dùng rồi gọi đối tác:

```java
// NGUY HIỂM: mang toàn bộ inbound headers sang một hệ thống khác.
outbound.headers(h -> h.addAll(inboundHeaders));
```

Việc này có thể làm lộ `Authorization`, `Cookie`, internal debug headers, tenant identifiers chưa xác thực hoặc proxy headers. Hãy xây **allowlist được viết rõ**, ví dụ correlation ID được kiểm tra hợp lệ, ngôn ngữ từ tập giá trị cho phép và một client credential riêng cho đối tác. Nếu hệ thống có distributed tracing auto-instrumentation, dùng chính cơ chế propagate được hỗ trợ thay vì copy thô mọi header.

## 12. Header nghiệp vụ: idempotency, ETag, conditional requests và locale

Một số header ảnh hưởng **tính đúng đắn nghiệp vụ**, không chỉ metadata tiện ích.

### 12.1. `Idempotency-Key` bảo vệ retry cho POST có side effect

Ví dụ tạo thanh toán từ một yêu cầu HTTP:

```java
import java.math.BigDecimal;
import org.springframework.http.MediaType;
import org.springframework.web.client.RestClient;

public record CreatePaymentRequest(
        String orderId,
        BigDecimal amount
) {}

public record PaymentResponse(
        String paymentId,
        String status
) {}

public PaymentResponse createPayment(
        RestClient billing,
        CreatePaymentRequest body,
        String stableOperationId) {

    if (stableOperationId == null || stableOperationId.isBlank()) {
        throw new IllegalArgumentException("Missing operation ID");
    }

    return billing.post()
            .uri("/v1/payments")
            .contentType(MediaType.APPLICATION_JSON)
            .accept(MediaType.APPLICATION_JSON)
            .headers(h -> h.set("Idempotency-Key", stableOperationId))
            .body(body)
            .retrieve()
            .body(PaymentResponse.class);
}
```

Giả sử request được gửi và đối tác đã commit payment, nhưng client timeout trước khi nhận response. Nếu retry với **key mới**, đối tác có thể coi là payment khác. Nếu retry cùng key và **đối tác có hợp đồng hỗ trợ idempotency**, hệ đích có thể trả lại kết quả trước đó hoặc từ chối payload xung đột theo policy.

**Header không tự tạo idempotency.** Phải biết phía đối tác có hỗ trợ hay không, thời hạn lưu idempotency key, phạm vi theo tenant/account, xử lý khi cùng key nhưng body khác và khả năng tra cứu trạng thái sau timeout. Đối với producer ghi DB rồi phát broker event, vẫn cần transactional outbox; đối với consumer nhận redelivery, cần inbox/unique constraint. Không suy từ một header thành exactly-once toàn hệ thống.

### 12.2. ETag và cập nhật có điều kiện

Đối tác trả:

```http
HTTP/1.1 200 OK
Content-Type: application/json
ETag: "order-v7"

{"id":"ORD-89","status":"PENDING"}
```

Khi cập nhật status, caller muốn chỉ sửa nếu version vẫn đúng:

```http
PUT /v1/orders/ORD-89 HTTP/1.1
Host: catalog.example.org
Content-Type: application/json
If-Match: "order-v7"

{"status":"ACCEPTED"}
```

Server có thể trả `412 Precondition Failed` nếu ETag đã đổi. Đây là **optimistic concurrency ở HTTP boundary**, tương tự ý tưởng version ở database nhưng không tự đồng nhất với `@Version` của JPA hoặc Mongo. Client cần đọc lại trạng thái và quyết định thay vì retry PUT mù quáng với cùng ETag cũ.

Với GET, `If-None-Match` có thể tạo phản hồi `304 Not Modified` để client tiếp tục dùng bản cache hiện có. Khi dùng Redis hoặc HTTP cache, cache key/variant và freshness policy phải tính đến URI, query, `Accept`/`Accept-Language` và các `Vary` headers liên quan. Không dùng cache chung cho response có quyền riêng mà không tách identity/tenant thích hợp.

### 12.3. Correlation ID không phải idempotency ID

`X-Correlation-ID` có thể giữ liên kết giữa HTTP inbound, database transaction, outbound HTTP và Kafka event, nhưng một **business operation** có thể được retry nhiều lần hoặc phân thành nhiều messages. Quy ước nên tách:

| Định danh | Ý nghĩa | Khi retry |
| --- | --- | --- |
| Correlation/trace ID | Truy vết một hành trình và các spans/requests | Có thể cùng hoặc thay đổi tùy tracing propagation; không tự là khóa nghiệp vụ. |
| Idempotency key | Một **tác động logic** tại đối tác | Phải ổn định cho những attempt thuộc cùng operation theo hợp đồng. |
| Event ID | Danh tính một sự kiện broker/outbox | Giữ nguyên qua publish lại của cùng event. |
| Order/payment ID | Danh tính đối tượng nghiệp vụ | Có thể có nhiều events và API operations hợp lệ theo ID đó. |

Nếu có W3C Trace Context instrumentation hoạt động qua Spring Boot/Micrometer, không tự viết `traceparent` từ một UUID tùy tiện: trace header có format và semantics riêng. Hãy dùng công cụ tracing/propagator để giữ ngữ cảnh chính xác.

## 13. Interceptor/filter: thêm header thống nhất mà không làm rò rỉ dữ liệu

Khi một đối tác cần `User-Agent` và một header phiên bản client trên mọi request, có thể đặt ở **default headers** ngay khi tạo client. Khi cần logic per-request như tracing hoặc logging có redaction, có thể dùng interceptor/filter.

### 13.1. RestClient interceptor cho metadata không nhạy cảm

```java
import org.springframework.http.client.ClientHttpRequestInterceptor;
import org.springframework.web.client.RestClient;

ClientHttpRequestInterceptor agentHeader = (request, body, execution) -> {
    request.getHeaders().set("X-Client-Name", "order-integration");
    return execution.execute(request, body);
};

RestClient client = bootBuilder
        .requestInterceptor(agentHeader)
        .build();
```

`bootBuilder` là builder do Spring quản lý (ví dụ trong `@Bean` factory), không phải biến toàn cục. Interceptor này đặt header **cố định** và không log request body/token; mọi interceptor cần có chính sách khi exception xảy ra và không được tự retry gây gọi trùng ngoài ý định. Interceptors của Spring Boot có thể đã gắn metrics/tracing; đừng thay toàn bộ builder/request factory mà bỏ qua customizers sẵn có.

### 13.2. WebClient filter dùng cho logging được kiểm soát

```java
import org.springframework.web.reactive.function.client.ExchangeFilterFunction;

ExchangeFilterFunction logOperation = (request, next) -> {
    // Ghi tên operation/host được allowlist, không log URI raw,
    // Authorization, Cookie, query có PII hoặc request body.
    return next.exchange(request);
};

WebClient client = bootBuilder
        .filter(logOperation)
        .build();
```

Ví dụ này chủ ý **không log gì** vì cách thực tế cần logger, redaction rules và đo timing/response ở đúng điểm. Mục tiêu là thể hiện nơi filter chặn/quan sát request; đừng copy nó rồi tin rằng đã có logging/metrics. Với tracing, ưu tiên instrumentation Spring Boot/Micrometer phù hợp, vì tự thêm trace headers bằng filter có thể phá propagation.

### 13.3. Thứ tự header/URI customization và test

Nếu một client có default `Accept`, interceptor, OAuth filter và per-request `Authorization`, thứ tự thực tế có thể ảnh hưởng giá trị cuối cùng. Không suy từ tên method nào “luôn thắng” trong mọi phiên bản Spring/engine. **Test request on-wire** với chính builder/configuration dùng ở production để xác minh:

1. Không có hai Bearer tokens hoặc hai `Idempotency-Key`.
2. Dynamic token đúng đối tác/tenant và không bị gửi khi redirect cross-origin.
3. `Content-Type` và `Accept` đúng với body/response contract.
4. Correlation/trace headers có format đúng, không ghi đè context ngoài ý muốn.
5. URI từ template giữ nguyên base host, path segments và query chính xác.

**Không dùng mutable shared header map** như một biến static được cập nhật theo người dùng rồi đưa vào singleton client. Một request đang chạy có thể đọc header của request khác trong môi trường multi-thread; hãy tạo request headers từ context của chính lời gọi.

## 14. Declarative HTTP interfaces: URI/header contract nằm ngay trên method

Spring Framework cung cấp **HTTP interfaces** để mô tả outbound API qua annotations, sau đó tạo proxy sử dụng `RestClient` hoặc `WebClient` đã được cấu hình. Chúng phù hợp khi đối tác có nhiều endpoint ổn định, nhưng **không thay thế** `baseUrl`, transport, token management hay error handling.

Ví dụ interface dùng synchronous `RestClient`:

```java
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.service.annotation.GetExchange;
import org.springframework.web.service.annotation.HttpExchange;

@HttpExchange(url = "/v1")
public interface CatalogHttpApi {

    @GetExchange("/products/{id}")
    ProductDto getProduct(
            @PathVariable("id") String productId,
            @RequestParam("lang") String language,
            @RequestHeader("X-Correlation-ID") String correlationId);
}
```

Tạo proxy từ client đã chọn:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.web.client.RestClient;
import org.springframework.web.client.support.RestClientAdapter;
import org.springframework.web.service.invoker.HttpServiceProxyFactory;

@Configuration(proxyBeanMethods = false)
public class CatalogProxyConfiguration {

    @Bean
    CatalogHttpApi catalogHttpApi(
            @Qualifier("catalogRestClient") RestClient client) {
        var adapter = RestClientAdapter.create(client);
        return HttpServiceProxyFactory
                .builderFor(adapter)
                .build()
                .createClient(CatalogHttpApi.class);
    }
}
```

Đây là cách diễn đạt method/path/query/header **được khai báo**. `CatalogHttpApi` vẫn đi qua cấu hình `RestClient` (host, URI factory, JSON converter, TLS, timeout, observability) và adapter vẫn phải:

- Validate `productId` và `lang` theo hợp đồng trước khi gọi.
- Gắn `Authorization` từ token manager/interceptor hoặc một lớp adapter có chủ đích.
- Xử lý 404, 429, 5xx, timeout và DTO rỗng/không hợp lệ.
- Kiểm thử **encoded URI** thực, nhất là ID có slash, vì annotations không tự biết quyền truy cập và schema của đối tác.

Nếu tạo proxy bằng `WebClientAdapter`, method có thể trả `Mono<T>`/`Flux<T>` theo khả năng adapter và interface tương ứng. Đừng đổi sang return `Mono` trong interface synchronous vừa được tạo qua `RestClientAdapter` rồi kỳ vọng reactive network I/O tự xuất hiện.

### 14.1. Tránh tạo proxy cho từng request

Proxy HTTP interface, `RestClient` và `WebClient` thường được tạo **một lần** dưới dạng Spring bean và dùng lại. Không nên tạo `HttpServiceProxyFactory` cho mỗi message Kafka hoặc mỗi HTTP inbound request chỉ để đổi `baseUrl` theo input: sẽ làm khó kiểm soát pool, credentials và observability. Nếu có nhiều đối tác hợp lệ, khai báo một registry/bean theo đối tác được cấu hình và allowlist, không chấp nhận arbitrary URL từ caller.

## 15. Bảo mật URL/header: SSRF, redirect, path traversal và injection

URI builder giúp **mã hóa cú pháp**, nhưng **không phải một security boundary đầy đủ**. Nguy cơ chính trong outbound integration là **Server-Side Request Forgery (SSRF)** và việc chuyển tiếp dữ liệu nhạy cảm.

### 15.1. Base URL không phải rào chắn nếu chấp nhận absolute URI

Giả sử ứng dụng muốn luôn gọi catalog:

```java
RestClient catalog = RestClient.builder()
        .baseUrl("https://catalog.example.org")
        .build();
```

Nếu một method sau đó làm:

```java
// KHÔNG làm vậy với URL do HTTP caller cung cấp.
catalog.get().uri(userSuppliedAbsoluteUrl).retrieve().toBodilessEntity();
```

URI absolute có thể **bỏ qua base URL**, dẫn đến request tới một host khác, thậm chí đích nội bộ nếu mạng cho phép. Khi có default Authorization hoặc interceptor gắn token, rủi ro rò rỉ credential tăng lên.

**Chính sách cần có:**

1. Giữ origin/base URL trong cấu hình phía server, không lấy từ query/body người dùng.
2. Nhận **business IDs hoặc filter values** làm dữ liệu, rồi dựng relative path/query bằng template.
3. Nếu có yêu cầu gọi nhiều host, dùng allowlist chính xác về scheme, hostname, port và chính sách TLS; kiểm tra cả redirect destination.
4. Với URL không tin cậy, phải xử lý DNS resolution, private/loopback/link-local IP ranges, DNS rebinding và proxy routing; chỉ kiểm tra substring hostname như `endsWith("example.org")` không đủ.
5. Hạn chế outbound network bằng egress/firewall policy và quyền của workload, không chỉ application regex.

Đối với webhook hoặc presigned download URL của một đối tác tin cậy, có thể cần **client riêng** với redirect/credential policy đặc biệt; vẫn phải validate đích và giới hạn size/timeout. Không đưa token của catalog lên một host thứ ba chỉ vì response của catalog trả `Location`.

### 15.2. Encoded path có thể trở thành path traversal sau khi decode

Một raw ID:

```text
../admin
```

có thể chứa dấu chéo và ký tự traversal. Template/pathSegment giúp encode giá trị như **một segment**, nhưng gateway/backend có thể decode nhiều lần hoặc normalize path theo cách khác. Nếu IDs không được phép chứa `..` hay `/`, **validate đúng định dạng ID** trước khi build URI. Không coi `%2E%2E` hay `%2F` là “đã an toàn tuyệt đối” khi server tiếp tục xử lý path.

**Phương pháp hai lớp:** input validation theo contract và URI builder đúng syntax; cộng thêm server/gateway routing policy và integration tests. Không ghép path từ giá trị chưa tin cậy để chọn file resource hoặc internal admin endpoint.

### 15.3. Header injection và các ký tự điều khiển

Header value không được chứa CR/LF tùy ý; nếu một trace/correlation ID từ HTTP input được chuyển tiếp chưa kiểm tra, attacker có thể tìm cách tạo thêm header hoặc làm sai log trên thư viện yếu. Các HTTP engines hiện đại có validation, nhưng ứng dụng vẫn nên enforce định dạng/độ dài, ví dụ chỉ chấp nhận một request ID đã chuẩn hóa.

**Không tự đặt `Host` hoặc HTTP/2 `:authority` để “né” allowlist hostname**. Transport cần nhất quán giữa đích DNS/TCP, TLS SNI, certificate và HTTP authority; thay header không làm request tự trở thành một đích tin cậy.

### 15.4. Dữ liệu nhạy cảm trong query

Query string thường xuất hiện trong reverse-proxy logs, APM, browser history và hệ thống monitoring. Không nhét password, access token, API key hoặc PII vào query chỉ để dễ debug; dùng header/body theo API contract và HTTPS/TLS. Nếu đối tác bắt buộc dùng query parameter nhạy cảm, phải áp redaction, giới hạn logging/retention và phân quyền tương ứng.

## 16. HTTP outbound adapter trong Spring Integration và các luồng bất đồng bộ

Spring Integration có thể gọi HTTP thông qua outbound gateway/adapter hoặc service activator dùng một `RestClient`/`WebClient` chuyên biệt. Quy tắc base URL, encoding và headers vẫn **giống một HTTP call bình thường**, nhưng còn phải tính đến vòng đời message, error channel và broker ack.

```mermaid
flowchart LR
    A[(Kafka / RabbitMQ)] --> B[Inbound adapter]
    B --> C[Validate event + map DTO]
    C --> D[HTTP outbound call]
    D --> E[Catalog RestClient / WebClient]
    E --> F[URI template + query + headers]
    F --> G[Partner API]
    G --> H[Map result / error]
    H --> I[(DB / outbox / cache)]
```

**Một thiết kế tách lớp dễ kiểm soát:**

- Inbound broker adapter đọc message/event contract và trích `orderId`/correlation ID.
- Application service xác định operation, idempotency key và deadline.
- HTTP adapter tự xây **relative URI** từ ID/filter đã kiểm tra, gắn token của đối tác và headers cần thiết.
- Result/error được trả lại flow để quyết định DB transaction, ack/offset, retry hoặc DLQ.

### 16.1. Không gắn mọi `MessageHeaders` vào HTTP request

Spring Integration `Message<?>` có nhiều headers nội bộ như ID, timestamp, routing hoặc metadata của broker. Chúng không phải mặc nhiên là outbound HTTP headers hợp lệ hoặc được phép tiết lộ.

```java
// Anti-pattern: chuyển toàn bộ MessageHeaders vào HTTP partner.
// httpRequest.headers(h -> h.addAll(message.getHeaders()));
```

Thay vì vậy, tạo **header allowlist** theo contract: ví dụ correlation ID đã normalize, `Idempotency-Key` nghiệp vụ và tenant context đã xác thực nếu đối tác thực sự cần. Không chuyển Kafka headers, broker credentials, Spring internal Message ID hoặc JWT của client inbound như dữ liệu HTTP không kiểm soát.

### 16.2. Deadline và retry khi một message tạo nhiều HTTP calls

Nếu một Kafka message yêu cầu 3 HTTP calls, mỗi call đặt timeout 2 giây có thể làm processing vượt deadline và gây rebalance/ack trễ. Hãy tính **time budget của toàn message** và áp giới hạn cho từng call, đồng thời tránh retry storm.

Ví dụ một consumer nhận `PaymentRequested`:

```text
Message(eventId=evt-55, operationId=pay-55)
  -> HTTP GET /v1/customers/{id}  (catalog token, lang)
  -> HTTP POST /v1/payments       (billing token, stable Idempotency-Key)
  -> DB update + outbox event
  -> ack broker theo chính sách xử lý
```

Không dùng **cùng một HTTP client/token** cho catalog và billing chỉ vì chúng được gọi trong cùng flow. Nếu POST thanh toán timeout sau khi server đã commit, không retry với key mới hoặc cứ trả HTTP status từ client làm bằng chứng chắc chắn. Cần tra cứu theo operation ID và lưu dấu trạng thái bền vững, tránh thừa nhận xử lý thành công trước khi nghiệp vụ thật hoàn tất.

### 16.3. Cache key và URI query phải nhất quán

Một luồng dùng Redis cache cho catalog không nên chỉ cache theo `productId` nếu response phụ thuộc `lang`, `currency`, `Accept`, `Accept-Language`, quyền tenant hoặc API version.

Ví dụ:

```text
catalog:v1:product:PRD-107:lang:vi
catalog:v1:product:PRD-107:lang:en
```

Hai URI khác query có thể trả hai representations khác nhau. Cache key phải phản ánh **những chiều ảnh hưởng đến nội dung/ủy quyền**, không chỉ URL path. HTTP caching có `Vary` và `Cache-Control`; Redis cache ứng dụng phải chủ động thực thi chính sách tương đương nếu cần.

## 17. Kiểm thử URI và headers: kiểm tra request thực sự được gửi

Unit test xây URI có thể bắt lỗi template, nhưng một Spring HTTP adapter còn có default headers, interceptors, OAuth filters và transport có thể thêm/chỉnh metadata. Vì vậy, khi contract quan trọng, cần kiểm tra **wire representation**: method, target path, query, header names/values, media type và body.

### 17.1. Phân loại test cần có

| Test | Công cụ | Bảo đảm cần kiểm tra |
| --- | --- | --- |
| URI builder unit test | `DefaultUriBuilderFactory`, JUnit | Raw ID thành đúng URI, encode một lần, repeated query được giữ. |
| RestClient request test | `MockRestServiceServer` bind với `RestClient.Builder` | Method/URI/header do Spring API tạo theo hợp đồng, không cần network thật. |
| WebClient request test | Mock HTTP server hoặc `ExchangeFunction` giả được kiểm soát | URI, query, dynamic headers và response mapping. |
| Real transport test | WireMock/OkHttp `MockWebServer`, HTTP server thực trên localhost | Request-target, percent encoding, headers qua transport thật, redirect policy. |
| Spring Boot context test | `@SpringBootTest` hoặc slice phù hợp | ConfigurationProperties, builder do Boot quản lý, filters/interceptors/credentials. |
| Contract/E2E test | Partner sandbox/test fixture, flow DB/broker/cache | URI/header theo API version thật; timeout, idempotency, side effect và recovery. |

**`MockRestServiceServer` không chứng minh** TLS, proxy, DNS, connection pooling hoặc redirect behavior của HTTP engine thực. Ngược lại, một HTTP server giả có thể kiểm chứng bytes URI/header ở transport mà không chứng minh business contract ở phía đối tác production.

### 17.2. URI unit test: ID có dấu chéo, dấu cộng, Unicode

Ví dụ:

```java
import static org.junit.jupiter.api.Assertions.assertEquals;
import java.net.URI;
import java.util.Map;
import org.junit.jupiter.api.Test;
import org.springframework.web.util.DefaultUriBuilderFactory;

class CatalogUriTest {
    private final DefaultUriBuilderFactory factory =
            new DefaultUriBuilderFactory("https://catalog.example.org");

    CatalogUriTest() {
        factory.setEncodingMode(
                DefaultUriBuilderFactory.EncodingMode.TEMPLATE_AND_VALUES);
    }

    @Test
    void encodesSlashSpaceAndPlusInsideProductId() {
        URI uri = factory.builder()
                .pathSegment("v1", "products", "{id}")
                .build(Map.of("id", "SKU A/B++"));

        assertEquals(
                "/v1/products/SKU%20A%2FB%2B%2B",
                uri.getRawPath());
    }

    @Test
    void keepsRepeatedQueryParameters() {
        URI uri = factory.builder()
                .path("/v1/products")
                .queryParam("tag", "java", "spring")
                .build();

        assertEquals("tag=java&tag=spring", uri.getRawQuery());
    }

    @Test
    void escapesQueryValueInsteadOfCreatingNewParameter() {
        URI uri = factory.builder()
                .path("/v1/products")
                .queryParam("q", "{term}")
                .build(Map.of("term", "C++ & Spring"));

        assertEquals("q=C%2B%2B%20%26%20Spring",
                uri.getRawQuery());
    }
}
```

Các asserts dùng `getRawPath()` và `getRawQuery()` để thấy percent-encoding thay vì nhận chuỗi đã decode. Với ID tiếng Việt hoặc nhiều byte UTF-8, có thể thêm fixture chính xác và kiểm tra cả logic mà server nhận sau một lần decode; không tự so sánh với `String.toLowerCase()` hay encoder dựa vào locale của máy chạy test.

### 17.3. Network integration test với `MockWebServer`

Giả sử project có JUnit 5, Spring Web và dependency test `com.squareup.okhttp3:mockwebserver` phiên bản tương thích:

```java
import static org.junit.jupiter.api.Assertions.*;

import java.util.Map;
import java.util.concurrent.TimeUnit;
import okhttp3.mockwebserver.MockResponse;
import okhttp3.mockwebserver.MockWebServer;
import okhttp3.mockwebserver.RecordedRequest;
import org.junit.jupiter.api.Test;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.web.client.RestClient;
import org.springframework.web.util.DefaultUriBuilderFactory;

class CatalogRequestWireIT {

    @Test
    void sendsExpectedEncodedPathQueryAndHeaders() throws Exception {
        var server = new MockWebServer();
        server.start();

        try {
            server.enqueue(new MockResponse()
                    .setResponseCode(200)
                    .addHeader("Content-Type", "application/json")
                    .setBody("""
                            {"id":"SKU A/B++","name":"Demo"}
                            """));

            var factory = new DefaultUriBuilderFactory(
                    server.url("/").toString());
            factory.setEncodingMode(
                    DefaultUriBuilderFactory.EncodingMode.TEMPLATE_AND_VALUES);

            var client = RestClient.builder()
                    .uriBuilderFactory(factory)
                    .defaultHeader(HttpHeaders.ACCEPT,
                            MediaType.APPLICATION_JSON_VALUE)
                    .build();

            ProductDto result = client.get()
                    .uri(uri -> uri
                            .pathSegment("v1", "products", "{id}")
                            .queryParam("tag", "java", "spring")
                            .build(Map.of("id", "SKU A/B++")))
                    .headers(h ->
                            h.set("X-Correlation-ID", "corr-123"))
                    .retrieve()
                    .body(ProductDto.class);

            assertNotNull(result);
            assertEquals("SKU A/B++", result.id());

            RecordedRequest request =
                    server.takeRequest(2, TimeUnit.SECONDS);
            assertNotNull(request);
            assertEquals("GET", request.getMethod());
            assertEquals(
                    "/v1/products/SKU%20A%2FB%2B%2B?tag=java&tag=spring",
                    request.getPath());
            assertEquals("application/json",
                    request.getHeader("Accept"));
            assertEquals("corr-123",
                    request.getHeader("X-Correlation-ID"));
            assertNull(request.getHeader("Authorization"));
        } finally {
            server.shutdown();
        }
    }
}
```

Ở test này, `RestClient.builder()` được tạo trực tiếp **để kiểm tra URI/transport có kiểm soát**. Nó không chứng minh Spring Boot đã áp toàn bộ customizers của production. Muốn test đúng application bean, dùng Spring context cùng `CatalogApiProperties` test override tới mock server, rồi inject bean/proxy thực.

Test dùng `http://localhost` do server test phát địa chỉ; đó **không phải** lý do để nới policy `HTTPS origin` ở production. Không dùng MockWebServer URL làm cấu hình production hoặc bỏ hostname verification. Với test đăng ký container/proxy TLS, thiết lập certificate test có chủ đích thay vì tắt verify.

### 17.4. Ma trận trường hợp nên kiểm tra

| Trường hợp | Input/thao tác | Assert quan trọng |
| --- | --- | --- |
| ID thường | `PRD-107` | Path chuẩn, không tự thêm dấu `/` hoặc query. |
| ID có slash | `A/B` | Một encoded segment nếu contract cho phép; gateway không tự routing sai. |
| ID có space/Unicode | `SKU A`, `cà phê` | Encode UTF-8 đúng và server nhận giá trị mong muốn. |
| ID có dấu phần trăm | `100%` | Không encode thiếu hoặc hai lần. |
| Query có dấu cộng | `C++` | Literal plus được giữ, không thành khoảng trắng sau khi decode. |
| Query có `&` hoặc `=` | `R&D=1` | Vẫn là **một giá trị** của một param. |
| Repeated query | `tag=java&tag=spring` | Không bị gộp thành một `Map<String,String>` hoặc comma string. |
| Optional parameter | null, empty, absent | Đúng policy phân biệt thiếu và rỗng. |
| Offset/date | ISO-8601 UTC, epoch hoặc format riêng | Kiểu/độ chính xác được server hiểu, không phụ thuộc locale. |
| Header media type | GET vs POST JSON | `Accept`/`Content-Type` đúng với body/hợp đồng. |
| Token và correlation | Hai caller/two tenants concurrent | Không lẫn headers hoặc credential giữa requests/đối tác. |
| Retry POST | Cùng operation thử lại nhiều lần | `Idempotency-Key` giữ nguyên; payload không bị đổi nghĩa. |
| Conditional update | `If-Match` ETag cũ | Xử lý 412, không ghi đè trạng thái mới. |
| Redirect | 302/307 sang host khác | Không lộ token, policy redirect/allowlist đúng. |
| URI absolute input | Caller cố truyền `http://127.0.0.1/...` | Adapter từ chối hoặc không có đường nào cho URL đó đi tới transport. |
| Base URL có prefix | `https://host/gateway` | Endpoint thật không bị nhân đôi hoặc mất path prefix. |

Với asynchronous tests, dùng deadline cho `server.takeRequest(...)` thay vì sleep tùy tiện. Với WebClient, subscribe bằng `StepVerifier` hoặc framework test tương ứng, rồi kiểm tra request và cancellation/error path; đừng gọi `block()` trên Reactor event-loop chỉ để test đơn giản.

## 18. Chẩn đoán lỗi thường gặp về base URL, URI, query và headers

| Hiện tượng | Nguyên nhân có thể | Cách chẩn đoán và sửa |
| --- | --- | --- |
| Request đến **sai host** dù đã đặt baseUrl | Caller truyền absolute URI hoặc client/proxy cấu hình sai | Ghi tên partner/origin đã allowlist, kiểm tra URI overload và redirects. |
| `404` khi path có dấu `/` trong ID | Path bị tách thành nhiều segment hoặc gateway từ chối encoded slash | Kiểm tra `getRawPath()`/recorded request; dùng `pathSegment` và xác nhận hợp đồng server. |
| Đường dẫn chứa `/api/api/...` | Base URL đã có prefix, adapter thêm lại prefix | Quy định origin-only hoặc base-prefix duy nhất và test URL thật. |
| Đường dẫn mất `/gateway` | Quy tắc ghép base/path khác dự đoán, leading slash bị xử lý theo config | Test request-target với factory Spring version đang chạy. |
| Query `C++` trở thành `C  ` | `+` được server form-decode thành space | Encode literal plus (`%2B`) bằng URI variable đúng mode; test phía nhận. |
| `%252F` xuất hiện thay `%2F` | Encoded value bị đưa qua thêm một lần encode | Quy định raw vs pre-encoded; chỉ một lớp sở hữu encoding. |
| Search theo tên `R&D` thành hai params | Query string bị ghép bằng `&` thủ công | Dùng `queryParam("q", "{q}")` với URI variable. |
| Server không nhận hai tags | `Map<String,String>` làm mất repeated values | Dùng repeated `queryParam`/`MultiValueMap` theo contract. |
| Filter thiếu không được coi là “không lọc” | Client gửi `category=null` hoặc `category=` | Phân biệt absent/empty/null; chỉ thêm param khi có giá trị hợp lệ. |
| Kết quả thay đổi theo múi giờ server | Chuyển `LocalDateTime`/`Date` sang query không rõ timezone | Pin ISO-8601 UTC/offset hoặc epoch theo hợp đồng, test timezone. |
| Trả `415 Unsupported Media Type` | `Content-Type` body sai hoặc converter không serialize được | Kiểm tra request body thực và `Content-Type`, không chỉ `Accept`. |
| Trả `406 Not Acceptable` | `Accept` không tương thích response format server | Đối chiếu media types được API hỗ trợ. |
| Trả `401` sau một thời gian chạy | Singleton client giữ token hết hạn ở default header | Dùng token manager/OAuth client cho mỗi call; xem refresh path. |
| Trả `400` hoặc xác thực thất bại do header lặp | `header()` thêm một giá trị thay vì thay, interceptor thêm lần nữa | Kiểm tra toàn bộ HTTP headers on-wire; dùng `HttpHeaders.set(...)` khi cần single value. |
| Token của A xuất hiện ở request tới B | Reuse client sai qualifier, redirect hoặc absolute URL vượt base | Tách client/credentials, allowlist host, test cross-origin redirect. |
| Chữ ký HMAC sai | Thứ tự/canonicalization query/header hoặc percent encoding khác bên ký | Dùng canonical request fixture chính thức, test bytes được gửi. |
| Cùng payment được tạo hai lần sau timeout | Retry sinh Idempotency-Key mới hoặc đối tác không hỗ trợ semantics đó | Ổn định operation ID, tra cứu kết quả, inbox/outbox khi cần. |
| HTTP cache trả sai ngôn ngữ/tenant | Cache key bỏ `lang`/`Vary`/authorization scope | Cache theo những chiều quyết định representation/identity. |
| Observability có quá nhiều time series | Dùng raw URL có `orderId`/query làm metric label | Dùng URI template/operation name đã chuẩn hóa; ID trong trace/log an toàn. |
| Spring WebClient call không chạy | Publisher chưa được subscribe | Trả `Mono`/`Flux` cho caller quản lý; không fire-and-forget. |

### 18.1. Quy trình khoanh vùng theo từng lớp

Khi nhận một response bất ngờ, hãy phân tích theo thứ tự:

1. **Đích:** request cuối cùng đi tới scheme/host/port nào? Có redirect hay proxy không?
2. **Cấu trúc URI:** base URL được ghép thế nào? `getRawPath()` và query thật là gì?
3. **Encoding:** giá trị business là raw hay pre-encoded? Có `+`, `%`, `&`, slash và Unicode không?
4. **Headers:** `Accept`/`Content-Type`, token, ETag, correlation và idempotency key có đúng/single value không?
5. **Hợp đồng API:** phương thức GET/POST/PUT/PATCH, kiểu DTO, status và cách server diễn giải query/headers.
6. **Transport/policy:** proxy, TLS, redirect, timeout và observability do Boot/custom client cấu hình ra sao?
7. **Tác động nghiệp vụ:** request có thể đã commit ở server dù client timeout? Có cách query/reconcile theo operation ID?

**Không sửa lỗi ở tầng khác.** Tăng connection pool không làm `tag=java,spring` thành hai query params; đổi retry policy không sửa query `C++` bị decode thành dấu cách; thêm `Content-Type` cho GET không chữa được base URL sai.

## 19. Quan sát URI và headers mà không rò rỉ dữ liệu

Spring Boot Actuator/Micrometer có thể cung cấp quan sát HTTP client khi app dùng builder, connector và instrumentation phù hợp. Điều quan trọng là **tag theo operation/template, không theo từng URL raw**.

| Thông tin | Nên ghi/đo | Tránh |
| --- | --- | --- |
| Đối tác | `partner=catalog` / `billing` | Raw hostname nếu chứa tenant/secret hoặc arbitrary host từ input. |
| Operation | `get_product`, `create_payment` | URL có ID thay đổi cho mỗi request. |
| URI pattern | `/v1/products/{id}` | `/v1/products/PRD-107?...` làm metric label. |
| HTTP method | GET, POST, PUT… | Gộp thao tác đọc và ghi gây khó phân loại retry. |
| Status/outcome | 2xx, 4xx, 5xx, timeout, decode error, rejected | Chỉ đo số request được gửi mà bỏ qua rejected-before-send. |
| Latency | Tổng call và từng pha khi transport cho phép | Coi timeout ở client là bằng chứng server chưa xử lý. |
| Retry attempt | Số lần thử, nguyên nhân retry, budget còn lại | Ghi toàn bộ request/response body, credential. |
| Correlation/trace | Trace ID trong hệ tracing đã bảo mật | Token, Cookie, ID cá nhân trong metric tags. |
| Idempotency ID | Có thể đặt trong audit log hạn chế quyền nếu cần | In raw header `Idempotency-Key` trên mọi log/monitoring không kiểm soát. |
| URI encoding errors | Phân loại lỗi template/invalid input | Log trực tiếp query chứa PII hoặc secret. |

### 19.1. Vì sao template là ranh giới của metric cardinality?

Giả sử ứng dụng gọi:

```text
GET /v1/products/PRD-107?lang=vi
GET /v1/products/PRD-108?lang=vi
GET /v1/products/PRD-109?lang=en
```

Nếu meter dùng **full URL** làm tag, mỗi sản phẩm/trang/filter có thể tạo series mới. Nếu tag dùng **`/v1/products/{id}`**, các request được nhóm theo operation để thấy error rate và latency có ý nghĩa. Cần xác minh thực tế HTTP client observations có được bật không; không phải mọi custom request factory/connector tự sinh đủ tags.

Một cách quan sát an toàn là gán **tên operation cố định** trong adapter, ví dụ `catalog.get_product`. Giữ correlation ID trong trace/log có giới hạn quyền, còn URI template trong metric. Đừng đưa `Authorization`, `Cookie`, `X-API-Key` hoặc toàn raw query vào trace attributes.

### 19.2. Kiểm thử instrumentation là một phần của contract vận hành

Với ứng dụng có `RestClient.Builder`/`WebClient.Builder` từ Boot, có thể thêm một integration test gửi request tới MockWebServer rồi kiểm tra metric/observation thực trong test registry. Nếu không có metric:

- Có thể chưa có Actuator/Micrometer dependencies cần thiết.
- Có thể client được dựng trực tiếp bằng `RestClient.create()` và không nhận observation customizer.
- Có thể connector/transport metrics riêng chưa bật hoặc naming khác theo version.
- Có thể instrumentation bị thay thế khi custom builder/filter/request factory.

Không tự ghi các meter cardinality cao chỉ để “bù” một metric còn thiếu. Hãy chọn tập tags cố định, gắn tracing theo chuẩn và giữ policy redaction thống nhất.

## 20. Checklist triển khai base URL, URI, query và header

Trước khi đưa HTTP adapter vào production, hãy xác minh:

1. **Base URL:** lấy từ cấu hình môi trường/secret policy đúng đối tác; scheme/host/port được allowlist, không lấy arbitrary outbound URL từ HTTP caller?
2. **Client ownership:** `RestClient`/`WebClient`/HTTP interface là bean tạo một lần, dùng builder/configuration phù hợp, mỗi đối tác có qualifier/credential riêng?
3. **Path prefix:** nếu base chứa prefix, quy tắc ghép URI đã được thống nhất và test chính xác trong Spring Framework version thực tế?
4. **URI template:** path variables dùng `pathSegment`/template khi cần; không nối `"/orders/" + orderId` trực tiếp từ user input?
5. **Encoding:** raw/pre-encoded có owner rõ; dấu `/`, `+`, `%`, `?`, `#`, Unicode/space đã được test, không double encode?
6. **Query semantics:** repeated parameters, optional/empty/absent, sort/page size, date/time, numeric formatting và canonicalization có theo đúng API contract?
7. **Default headers:** chỉ chứa dữ liệu ổn định, phù hợp mọi request của client; không chứa short-lived token hoặc tenant-specific state?
8. **Per-request headers:** `Authorization`, correlation/trace, `Idempotency-Key`, `If-Match`, `Accept-Language` được sinh đúng nguồn và không trùng?
9. **Media types:** `Accept` cho response và `Content-Type` cho body request được phân biệt; JSON/XML/problem responses được mapping phù hợp?
10. **Security:** SSRF/redirect/cross-origin token forwarding, path traversal sau decode, header injection và query PII đã có policy và tests?
11. **Retry/idempotency:** POST/PATCH có side effect không retry mù quáng; key nghiệp vụ ổn định, có reconciliation/inbox/outbox khi luồng đi qua DB/broker?
12. **Integration:** Spring Integration/Kafka/RabbitMQ chuyển metadata sang HTTP theo allowlist, không copy thô inbound `MessageHeaders`/Authorization?
13. **Caching:** cache key/TTL phản ánh query, ngôn ngữ, quyền và `Vary` dimensions liên quan?
14. **Testing:** unit test URI raw encoding, repeated/optional query, real HTTP request-target, headers, dynamic credentials, redirects, 4xx/5xx và timeout?
15. **Observability:** metric theo template/operation, không gắn raw URL/ID/header nhạy cảm; có correlation và phân loại lỗi đủ khoanh vùng?

**Ghi nhớ:** **Base URL** chọn mốc đích, **URI builder/template** tạo path và query đúng cấu trúc, còn **headers** diễn đạt media type, xác thực, tracing, điều kiện ghi và idempotency. Ba lớp này phải được cấu hình **nhất quán và có chủ sở hữu rõ ràng**: input là dữ liệu chứ không phải cú pháp URL, client credentials không đi theo arbitrary host, và request động không sửa shared state. Với Spring Boot Integration, một URL/header đúng không chỉ giúp HTTP request thành công mà còn là tiền đề của hợp đồng dữ liệu, retry an toàn, cache đúng ngữ cảnh, xử lý thông điệp không trùng và quan sát toàn tuyến từ HTTP đến database, broker và Spring Integration.
