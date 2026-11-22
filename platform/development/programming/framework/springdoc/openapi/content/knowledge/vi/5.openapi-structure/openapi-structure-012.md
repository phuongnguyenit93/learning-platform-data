# Phân biệt `info.version` với phiên bản OpenAPI và phiên bản route

Trong một dự án Spring Boot dùng `springdoc-openapi`, từ “phiên bản API” có thể chỉ nhiều khái niệm khác nhau. Trường `openapi` ở đầu tài liệu cho biết tài liệu tuân theo phiên bản nào của OpenAPI Specification. Trường `info.version` mô tả phiên bản của tài liệu OpenAPI. Còn phiên bản route là quy ước mà ứng dụng dùng để định tuyến request đến một hợp đồng hoặc cách triển khai API cụ thể, chẳng hạn `/api/v1/orders`.

Ba giá trị này có thể thay đổi độc lập. Nâng phiên bản OpenAPI Specification không tự tạo endpoint `/v2`; đổi `info.version` không tự thay đổi controller; và thêm route `/api/v2` không bắt buộc phải chuyển tài liệu sang OpenAPI 3.1. Hiểu rõ ranh giới này giúp quản lý hợp đồng, sinh client và phát hành API mà không làm các công cụ hoặc người tích hợp hiểu nhầm.

## 1. Ba khái niệm phiên bản có mục đích khác nhau

| Vị trí hoặc khái niệm | Nó mô tả điều gì? | Ví dụ | Thành phần quyết định |
|---|---|---|---|
| `openapi` | Phiên bản của ngôn ngữ/đặc tả OpenAPI dùng để biểu diễn tài liệu | `3.0.3`, `3.1.0` | Phiên bản OpenAPI mà công cụ tạo tài liệu xuất ra |
| `info.version` | Phiên bản của tài liệu OpenAPI | `1.4.0`, `2026.11` | Nhóm phát triển quản lý phiên bản tài liệu |
| Phiên bản route | Phiên bản hợp đồng được chọn khi client gọi API | `/api/v1/orders`, `/api/v2/orders` | Thiết kế routing và triển khai ứng dụng |

Ngoài ba khái niệm trên, dự án còn có phiên bản của ứng dụng, artifact Maven/Gradle, Spring Boot, Springdoc và Swagger UI. Những phiên bản này có thể liên quan đến quá trình build và vận hành, nhưng không thể thay thế cho ba trường hoặc quy ước ở bảng trên.

## 2. Trường `openapi`: phiên bản của OpenAPI Specification

Một tài liệu OpenAPI bắt đầu bằng trường `openapi`, ví dụ:

```yaml
openapi: 3.1.0
info:
  title: Order API
  version: 1.0.0
paths: {}
```

Giá trị `3.1.0` cho biết tài liệu được viết theo OpenAPI Specification phiên bản 3.1.0. Nó xác định cú pháp, cấu trúc object, kiểu dữ liệu và những quy tắc mà validator, parser, Swagger UI hoặc công cụ sinh client cần hiểu.

Các phiên bản đặc tả có thể khác nhau về khả năng biểu diễn schema, cách tham chiếu JSON Schema, từ khóa được hỗ trợ và quy tắc xử lý tài liệu. Vì vậy, công cụ đọc tài liệu phải tương thích với phiên bản đặc tả được khai báo.

`openapi` không phải phiên bản phát hành của dịch vụ. Ví dụ, một nhóm có thể nâng tài liệu từ OpenAPI 3.0.3 lên 3.1.0 để sử dụng khả năng mới của đặc tả, trong khi các route `/api/v1/...` và hành vi API vẫn giữ nguyên. Ngược lại, một nhóm có thể phát hành `/api/v2/...` mà vẫn dùng OpenAPI 3.0.3 nếu các schema và tính năng được sử dụng tương thích với 3.0.3.

Trong ứng dụng dùng Springdoc, phiên bản đặc tả được xuất ra bởi phiên bản thư viện và cấu hình tương ứng. Không nên sửa thủ công trường `openapi` trong JSON/YAML đầu ra để cố gắng đổi phiên bản. Nếu cần một phiên bản đặc tả khác, hãy kiểm tra khả năng hỗ trợ của dòng Springdoc đang dùng, cấu hình chính thức của phiên bản đó và khả năng tương thích của các công cụ tiếp nhận.

## 3. Trường `info.version`: phiên bản của tài liệu OpenAPI

`info.version` là trường bắt buộc trong Info Object. Theo định nghĩa của OpenAPI, nó biểu thị phiên bản của tài liệu OpenAPI và khác với phiên bản OpenAPI Specification cũng như phiên bản triển khai API.

Ví dụ:

```yaml
openapi: 3.1.0
info:
  title: Order API
  version: 2026.11
  description: Tài liệu hợp đồng cho dịch vụ đơn hàng.
paths: {}
```

Ở đây:

- `openapi: 3.1.0` nói rằng tài liệu dùng cú pháp OpenAPI Specification 3.1.0.
- `info.version: 2026.11` là phiên bản của tài liệu OpenAPI đang được công bố.
- Không có thông tin nào ở hai trường này tự khai báo ứng dụng phải định tuyến request đến `/api/v1` hay `/api/v2`.

Trong thực tế, nhiều nhóm quy ước `info.version` trùng với phiên bản phát hành API, ví dụ `1.2.0`. Đây là quy ước quản lý hữu ích vì người đọc tài liệu dễ liên hệ tài liệu với release tương ứng. Tuy nhiên, đặc tả không buộc giá trị này phải bằng phiên bản route hoặc phiên bản binary đang chạy.

Một tài liệu có thể được cập nhật phần mô tả, ví dụ, contact hoặc schema annotation mà không làm thay đổi hành vi API. Nhóm có thể tăng phiên bản tài liệu để ghi nhận lần cập nhật đó, hoặc giữ nguyên `info.version` nếu chính sách chỉ tăng khi hợp đồng API thay đổi. Điều quan trọng là phải định nghĩa quy tắc nhất quán và công bố cách hiểu cho người dùng tài liệu.

### Thiết lập `info.version` bằng Springdoc

Có thể khai báo thông tin tài liệu bằng annotation:

```java
import io.swagger.v3.oas.annotations.OpenAPIDefinition;
import io.swagger.v3.oas.annotations.info.Info;
import org.springframework.context.annotation.Configuration;

@Configuration
@OpenAPIDefinition(
    info = @Info(
        title = "Order API",
        version = "1.4.0",
        description = "API quản lý đơn hàng"
    )
)
class OpenApiMetadataConfiguration {
}
```

Hoặc khai báo bean mô hình OpenAPI:

```java
import io.swagger.v3.oas.models.OpenAPI;
import io.swagger.v3.oas.models.info.Info;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class OpenApiConfiguration {

    @Bean
    OpenAPI orderApi() {
        return new OpenAPI()
            .info(new Info()
                .title("Order API")
                .version("1.4.0")
                .description("API quản lý đơn hàng"));
    }
}
```

Hai cách trên đều bổ sung metadata cấp tài liệu. Chọn cách phù hợp với cấu trúc dự án và tránh khai báo hai nguồn `Info` cạnh tranh nhau. Có thể quản lý giá trị version trong build metadata hoặc cấu hình ứng dụng để giảm việc sửa chuỗi ở nhiều nơi, nhưng cần bảo đảm giá trị được đóng gói vào tài liệu là phiên bản phát hành đã xác định.

## 4. Phiên bản route: cách ứng dụng chọn hợp đồng API

Phiên bản route quyết định client đang gọi biến thể API nào. Đây là một phần của thiết kế HTTP và routing. Nó có thể được biểu diễn theo nhiều cách, phổ biến nhất là đưa version vào URL path.

Ví dụ hai route:

```java
@RestController
class OrderV1Controller {

    @GetMapping("/api/v1/orders/{id}")
    OrderV1Response getOrder(@PathVariable Long id) {
        // Xử lý theo hợp đồng v1
        return orderService.getV1(id);
    }
}

@RestController
class OrderV2Controller {

    @GetMapping("/api/v2/orders/{id}")
    OrderV2Response getOrder(@PathVariable Long id) {
        // Xử lý theo hợp đồng v2
        return orderService.getV2(id);
    }
}
```

Ứng dụng có thể duy trì hai route trong giai đoạn chuyển đổi để client cũ tiếp tục hoạt động trong khi client mới chuyển sang v2. Controller có thể dùng chung service hoặc domain model nội bộ, nhưng DTO và cách ánh xạ response cần phản ánh đúng hợp đồng của từng phiên bản.

### Các chiến lược versioning thường gặp

| Chiến lược | Ví dụ request | Cách Spring có thể định tuyến | Điểm cần cân nhắc |
|---|---|---|---|
| URI/path versioning | `/api/v1/orders` | `@RequestMapping("/api/v1/orders")` | Dễ nhìn, dễ cache và dễ phân biệt trong log |
| Header versioning | `X-API-Version: 2` | Mapping theo `headers` hoặc logic định tuyến tùy chỉnh | URL không đổi nhưng client phải gửi header đúng |
| Media type versioning | `Accept: application/vnd.example.order-v2+json` | Mapping theo `produces` hoặc content negotiation | Thể hiện phiên bản qua biểu diễn nội dung, cần quy ước media type rõ |

Ví dụ mapping theo header:

```java
@RestController
@RequestMapping("/api/orders")
class VersionedOrderController {

    @GetMapping(value = "/{id}", headers = "X-API-Version=1")
    OrderV1Response getV1(@PathVariable Long id) {
        return orderService.getV1(id);
    }

    @GetMapping(value = "/{id}", headers = "X-API-Version=2")
    OrderV2Response getV2(@PathVariable Long id) {
        return orderService.getV2(id);
    }
}
```

Ví dụ này minh họa điều kiện mapping của Spring MVC. Trong hệ thống thực tế, cần xác định rõ hành vi khi client thiếu header, gửi version không hỗ trợ hoặc gửi nhiều giá trị xung đột. Nên trả lỗi có cấu trúc và mô tả quy tắc trong tài liệu API.

Không có một chiến lược phù hợp cho mọi hệ thống. URI versioning thường dễ quan sát và triển khai; header hoặc media type versioning có thể phù hợp với quy ước tích hợp đã có. Điều quan trọng là version được chọn phải có quy tắc rõ, được kiểm thử và được phản ánh trong hợp đồng OpenAPI.

## 5. Mối quan hệ giữa `servers`, `paths` và route version

Trong OpenAPI, `servers` mô tả URL gốc mà client dùng để gọi API; `paths` mô tả các đường dẫn tương đối từ server URL đó. Nếu version được đặt trong path, nó thường nằm trong `paths`.

Ví dụ:

```yaml
openapi: 3.1.0
info:
  title: Order API
  version: 2.0.0
servers:
  - url: https://api.example.com
paths:
  /api/v2/orders/{id}:
    get:
      summary: Lấy đơn hàng theo mã
      parameters:
        - name: id
          in: path
          required: true
          schema:
            type: integer
            format: int64
      responses:
        '200':
          description: Tìm thấy đơn hàng
```

Trong ví dụ, `https://api.example.com` là server URL và `/api/v2/orders/{id}` là path. Client ghép hai phần để tạo URL request. `info.version: 2.0.0` là phiên bản tài liệu; route version là `v2` trong path.

Không nên đặt `/api/v2` đồng thời trong `servers.url` và trong `paths` nếu không có chủ đích, vì client có thể ghép thành `/api/v2/api/v2/...`. Khi ứng dụng chạy sau reverse proxy hoặc context path, hãy kiểm tra giá trị server URL và path được sinh ra có khớp URL công khai hay không.

Với header versioning, `paths` có thể giữ nguyên nhưng operation cần khai báo header parameter hoặc media type tương ứng để client biết cách chọn hợp đồng. Tài liệu cần mô tả đầy đủ điều kiện định tuyến, nếu không client chỉ thấy cùng một URL và không biết cách yêu cầu phiên bản mong muốn.

## 6. Một route version có thể có nhiều lần cập nhật tài liệu

Không phải mỗi lần tài liệu được cập nhật đều cần tạo route version mới. Ví dụ API v1 có thể bổ sung mô tả, ví dụ, response lỗi đã tồn tại hoặc làm rõ format của một field mà không thay đổi hành vi tương thích. Khi đó, nhóm có thể phát hành bản tài liệu mới nhưng tiếp tục phục vụ route `/api/v1`.

Ngược lại, một thay đổi phá vỡ tương thích thường cần một chiến lược chuyển phiên bản API được công bố rõ ràng. Ví dụ:

- API v1 trả `customerName` dưới dạng chuỗi; v2 đổi thành object `customer` có nhiều thuộc tính.
- API v1 chấp nhận một trường bắt buộc; v2 đổi quy tắc validation theo cách khiến request cũ không còn hợp lệ.
- API v1 trả mã trạng thái hoặc cấu trúc lỗi mà client đang phụ thuộc; v2 thay đổi cách phản hồi.
- API v1 có ý nghĩa của một tham số; v2 đổi đơn vị hoặc cách diễn giải giá trị đó.

Những thay đổi như vậy cần phân tích ảnh hưởng client. Có thể triển khai song song hai route hoặc dùng chiến lược versioning đã chọn để client chuyển đổi theo lộ trình. Việc chỉ tăng `info.version` không làm request cũ được định tuyến sang implementation mới và cũng không tự bảo vệ tương thích.

## 7. Quản lý nhiều route version bằng tài liệu nhóm

Springdoc có thể tạo nhiều tài liệu OpenAPI bằng `GroupedOpenApi`. Group giúp chia tài liệu theo phạm vi endpoint, package hoặc các điều kiện lọc khác. Ví dụ:

```java
import org.springdoc.core.models.GroupedOpenApi;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class ApiVersionDocumentation {

    @Bean
    GroupedOpenApi orderV1Docs() {
        return GroupedOpenApi.builder()
            .group("orders-v1")
            .pathsToMatch("/api/v1/**")
            .build();
    }

    @Bean
    GroupedOpenApi orderV2Docs() {
        return GroupedOpenApi.builder()
            .group("orders-v2")
            .pathsToMatch("/api/v2/**")
            .build();
    }
}
```

Các endpoint tài liệu nhóm thường có dạng:

```text
/v3/api-docs/orders-v1
/v3/api-docs/orders-v2
```

Có thể cấu hình Swagger UI để chọn tài liệu:

```yaml
springdoc:
  swagger-ui:
    urls:
      - name: Orders API v1
        url: /v3/api-docs/orders-v1
      - name: Orders API v2
        url: /v3/api-docs/orders-v2
    urls-primary-name: Orders API v2
```

Group name chỉ đặt tên cho tài liệu được tạo; nó không tự tạo route tương ứng và không thay đổi mapping của controller. Ví dụ, khai báo group `orders-v2` không làm endpoint `/api/v2/orders` xuất hiện nếu ứng dụng chưa có controller hoặc handler phù hợp.

Nếu tài liệu của mỗi group cần `info.version` khác nhau, hãy cấu hình metadata theo group bằng cơ chế customizer phù hợp với phiên bản Springdoc đang sử dụng. Không giả định tên group tự động được sao chép vào `info.version` hoặc Springdoc tự suy ra API release version từ đoạn `/v2` trong URL.

## 8. Quy ước đặt giá trị `info.version`

OpenAPI định nghĩa `info.version` là một chuỗi. Nhóm phát triển có thể dùng Semantic Versioning, lịch phát hành hoặc một quy ước nội bộ khác. Nếu chọn SemVer, cần nói rõ version đang áp dụng cho tài liệu, cho API contract hay cho release API theo quy ước của tổ chức.

Một cách quản lý thường gặp là đồng bộ `info.version` với phiên bản hợp đồng API được công bố:

| Giá trị | Cách hiểu theo quy ước của nhóm | Ví dụ |
|---|---|---|
| `1.0.0` | Bản hợp đồng đầu tiên được phát hành | API v1 ra mắt |
| `1.1.0` | Bổ sung khả năng tương thích ngược | Thêm endpoint hoặc field tùy chọn |
| `1.1.1` | Sửa lỗi hoặc làm rõ tài liệu mà không đổi hợp đồng theo chính sách nhóm | Sửa ví dụ hoặc mô tả sai |
| `2.0.0` | Có thay đổi phá vỡ tương thích | Phát hành hợp đồng mới cần client điều chỉnh |

Đây là quy ước minh họa, không phải yêu cầu của OpenAPI. Nếu tổ chức cần theo dõi riêng phiên bản tài liệu và phiên bản API, có thể đặt `info.version` theo revision tài liệu và ghi phiên bản API trong `description`, extension như `x-api-version`, hoặc metadata được thống nhất khác. Khi làm vậy, hãy giữ cách thể hiện rõ ràng để người dùng không hiểu nhầm.

Không dùng phiên bản của Springdoc làm `info.version` một cách máy móc. Ví dụ `springdoc-openapi` phiên bản `2.x` là phiên bản thư viện sinh tài liệu; nó không có nghĩa dịch vụ Order API đang ở phiên bản `2.x`.

## 9. Tình huống thay đổi ba phiên bản độc lập

| Tình huống | `openapi` | `info.version` | Route | Ý nghĩa |
|---|---|---|---|---|
| Cập nhật thư viện/cách biểu diễn tài liệu | `3.0.3` → `3.1.0` | Có thể giữ `1.4.0` | Giữ `/api/v1` | Nâng phiên bản đặc tả; API vẫn giữ hợp đồng cũ |
| Sửa nội dung tài liệu | Giữ `3.1.0` | `1.4.0` → `1.4.1` theo quy ước | Giữ `/api/v1` | Có revision tài liệu mới; routing không đổi |
| Phát hành route API mới | Có thể giữ `3.1.0` | Ví dụ `2.0.0` | Thêm `/api/v2` | Có hợp đồng route mới; đặc tả vẫn dùng cùng phiên bản OpenAPI |
| Nâng cả đặc tả và hợp đồng | `3.0.3` → `3.1.0` | `1.4.0` → `2.0.0` | `/api/v1` và `/api/v2` cùng tồn tại | Thay đổi đồng thời hai trục tài liệu và hợp đồng API |

Điểm quan trọng là phải ghi nhận lý do cho từng thay đổi. Một commit thay đổi `openapi` có thể chỉ nhằm sử dụng schema dialect mới; một commit thay đổi route có thể nhằm hỗ trợ client mới; một commit thay đổi `info.version` có thể chỉ là revision tài liệu. Review nên kiểm tra từng mục theo đúng tác động của nó.

## 10. Kiểm tra tài liệu và route có nhất quán không

Khi phát hành một phiên bản API, nên kiểm tra ba lớp riêng:

1. **Đặc tả:** trường `openapi` có phiên bản mà validator và công cụ của nhóm hỗ trợ; cấu trúc tài liệu hợp lệ.
2. **Metadata:** `info.version` theo đúng quy ước của nhóm, có thể đối chiếu với release note hoặc artifact phát hành.
3. **Routing:** route thực sự tồn tại, request được định tuyến đúng implementation và tài liệu mô tả đúng path, header hoặc media type dùng để chọn version.

Ví dụ kiểm tra endpoint thực tế:

```bash
curl -i http://localhost:8080/api/v1/orders/42
curl -i http://localhost:8080/api/v2/orders/42
```

Nếu dùng header versioning:

```bash
curl -i -H "X-API-Version: 1" http://localhost:8080/api/orders/42
curl -i -H "X-API-Version: 2" http://localhost:8080/api/orders/42
```

Sau đó lấy tài liệu tương ứng:

```bash
curl http://localhost:8080/v3/api-docs/orders-v1
curl http://localhost:8080/v3/api-docs/orders-v2
```

Không nên chỉ kiểm tra JSON có trường `info.version` đúng rồi kết luận route đã được triển khai. Cũng không nên chỉ gọi route thành công rồi kết luận tài liệu phản ánh đúng request và response. Cần đối chiếu cả hai phía.

## 11. Các lỗi hiểu nhầm thường gặp

| Hiểu nhầm | Thực tế |
|---|---|
| `openapi: 3.1.0` có nghĩa API đang ở v3.1 | Đây là phiên bản OpenAPI Specification |
| `info.version: 2.0.0` tự tạo route `/v2` | Đây là metadata của tài liệu; route phải được triển khai riêng |
| Đổi `/api/v1` thành `/api/v2` thì Springdoc tự tăng `info.version` | Springdoc không nên được xem là cơ chế quản lý API release version tự động |
| Tên group `v2` tương đương route v2 | Group chỉ lọc và đặt tên tài liệu; controller phải cung cấp route |
| Nâng Springdoc từ `2.x` lên `3.x` là nâng API của ứng dụng | Đây là phiên bản thư viện; cần đánh giá riêng ảnh hưởng lên đặc tả và runtime |
| `info.version` luôn phải bằng version trong URL | Đây có thể là quy ước của dự án, không phải yêu cầu bắt buộc của OpenAPI |

## 12. Checklist quản lý phiên bản

- [ ] Phân biệt trường `openapi` với `info.version` trong tài liệu.
- [ ] Quy định rõ `info.version` đại diện revision tài liệu hay được đồng bộ với phiên bản hợp đồng API.
- [ ] Chọn chiến lược route versioning: URI, header hoặc media type.
- [ ] Controller và mapping thực sự triển khai từng phiên bản route được công bố.
- [ ] `servers` và `paths` ghép thành URL đúng trong môi trường triển khai.
- [ ] Tài liệu nhóm được lọc đúng endpoint và không nhầm group name với route version.
- [ ] Swagger UI cung cấp đúng tài liệu cho từng phiên bản API cần hỗ trợ.
- [ ] Validator và công cụ sinh client tương thích với phiên bản OpenAPI trong tài liệu.
- [ ] Thay đổi phá vỡ tương thích có kế hoạch phát hành, chuyển đổi và ngừng hỗ trợ rõ ràng.
- [ ] Kiểm thử cả endpoint thực tế lẫn tài liệu OpenAPI được xuất ra.

Khi quản lý đúng ba trục phiên bản, nhóm có thể nâng cấp định dạng đặc tả, cập nhật revision tài liệu và phát hành route API mới theo các kế hoạch riêng. `openapi` cho công cụ biết cách đọc tài liệu, `info.version` giúp nhận diện phiên bản tài liệu được công bố, còn route version quyết định request được xử lý theo hợp đồng nào. Springdoc giúp mô tả các route đã triển khai; quy trình phát hành của nhóm chịu trách nhiệm giữ metadata, tài liệu và hành vi API nhất quán.
