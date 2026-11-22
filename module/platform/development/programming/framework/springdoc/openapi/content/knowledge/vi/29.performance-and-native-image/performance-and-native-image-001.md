# Phạm vi quét và ảnh hưởng đến số handler, schema phải xử lý

springdoc-openapi đọc các handler mà Spring MVC hoặc WebFlux đã đăng ký, sau đó xây dựng OpenAPI operation từ mapping, annotation, tham số, request body, response và kiểu dữ liệu liên quan. Khi ứng dụng có nhiều controller, endpoint nội bộ, phiên bản API hoặc DTO dùng chung, phạm vi quét rộng có thể làm tài liệu lớn hơn và tăng thời gian tạo OpenAPI.

Kiểm soát phạm vi quét giúp tài liệu chỉ chứa API cần công bố, giảm số operation và đồ thị schema mà springdoc phải xử lý cho từng document. Việc này đặc biệt hữu ích khi có nhiều document group hoặc khi chạy ứng dụng dưới GraalVM Native Image. Tuy nhiên, cần phân biệt lọc tài liệu với component scanning của Spring: lọc springdoc không tự ngăn Spring tạo bean hoặc khởi tạo dependency.

Bài này giải thích cách chọn package và path, ẩn operation, tổ chức document group, hiểu tác động của schema graph và đo thời gian tạo tài liệu. Các ví dụ dùng cấu hình springdoc hiện đại; kiểm tra tên property và API builder theo major version đang dùng.

## 1. Springdoc phải xử lý những gì?

Để tạo OpenAPI document, springdoc cần tìm các request mapping mà Spring đã đăng ký và biến chúng thành operation. Với mỗi operation, thư viện còn phải phân tích metadata và các kiểu dữ liệu liên quan.

Luồng xử lý khái quát:

~~~mermaid
flowchart TD
    A[Spring MVC / WebFlux handler mappings] --> B[Chọn handler theo package và path]
    B --> C[Tạo operation và parameter]
    C --> D[Phân tích request body và response]
    D --> E[Khám phá DTO, enum và schema tham chiếu]
    E --> F[Áp dụng annotation và customizer]
    F --> G[Tuần tự hóa OpenAPI JSON/YAML]
~~~

Các nhóm dữ liệu chính:

- **Handler mapping:** controller method, HTTP method, path, consumes, produces và các điều kiện mapping.
- **Operation metadata:** summary, description, operationId, tag, security requirement và response.
- **Parameter:** path, query, header và cookie parameter.
- **Request/response model:** DTO, record, generic wrapper, collection, map và kiểu trả về.
- **Schema graph:** các model được tham chiếu trực tiếp và gián tiếp qua property lồng nhau.
- **OpenAPI components:** schema dùng chung, security scheme, response/parameter tái sử dụng và metadata do customizer bổ sung.

Vì vậy, chi phí không chỉ phụ thuộc số controller. Một controller có ít endpoint nhưng dùng DTO lồng sâu, generic phức tạp hoặc nhiều nhánh đa hình vẫn có thể tạo ra schema graph lớn.

## 2. Phân biệt component scanning của Spring với operation scanning của springdoc

Hai loại scan có mục đích khác nhau:

| Cơ chế | Mục đích | Ảnh hưởng chính |
|---|---|---|
| Spring component scanning | Tìm và đăng ký bean như controller, service, repository, configuration | Application context, dependency injection và quá trình khởi động |
| Spring MVC/WebFlux handler mapping | Đăng ký các route/handler có thể nhận request | Tập endpoint thực tế của ứng dụng |
| Springdoc package/path filtering | Chọn handler nào được đưa vào OpenAPI document | Số operation và schema cần xử lý cho tài liệu đó |

`springdoc.packages-to-scan` và `springdoc.paths-to-match` lọc operation được mô tả. Chúng không thay thế `@ComponentScan`, không tự tắt controller bean và không bảo đảm dependency của controller bị loại khỏi application context.

Ví dụ, nếu controller quản trị vẫn được Spring tạo bean nhưng bị loại khỏi OpenAPI bằng path filter, endpoint đó vẫn có thể hoạt động qua HTTP. Lọc tài liệu không phải cơ chế bảo mật hoặc tắt endpoint.

Không thu hẹp `@ComponentScan` chỉ để giảm số operation trong Swagger UI. Việc đó có thể khiến service, repository, security configuration hoặc các bean cần thiết biến mất, làm ứng dụng không khởi động hoặc thay đổi hành vi runtime.

## 3. Lọc theo package bằng springdoc.packages-to-scan

Khi các controller được tổ chức theo package, có thể giới hạn package mà springdoc đưa vào tài liệu mặc định:

~~~yaml
springdoc:
  packages-to-scan:
    - com.example.catalog.api
    - com.example.catalog.partner
~~~

Trong ví dụ, springdoc chỉ đưa các handler thuộc hai package được chọn vào document áp dụng cấu hình này. Các DTO nằm ở package khác vẫn có thể xuất hiện trong `components.schemas` nếu được request hoặc response của operation được chọn tham chiếu.

Điểm này rất quan trọng: `packages-to-scan` lọc package của handler, không phải danh sách package DTO độc lập. Không cần chuyển tất cả model vào cùng package với controller để chúng được đưa vào schema.

Nên chọn package đủ cụ thể:
- `com.example.catalog.api` nếu toàn bộ package chứa API cần công bố.
- `com.example.catalog.publicapi` nếu đã tách rõ API public.
- Tránh chọn package gốc quá rộng như `com.example` nếu bên dưới có admin, internal, actuator hoặc adapter không thuộc hợp đồng công khai.

Nếu controller nằm trong package con, kiểm tra quy tắc package matching của phiên bản springdoc đang dùng và xác nhận bằng OpenAPI output. Đừng giả định một package cha luôn bao gồm mọi package con theo cùng cách giữa các phiên bản.

## 4. Lọc theo path bằng springdoc.paths-to-match

Package phù hợp không phải lúc nào cũng phản ánh ranh giới API. Một package có thể chứa cả endpoint public và internal. Khi đó, có thể lọc theo URL path:

~~~yaml
springdoc:
  paths-to-match:
    - /api/**
    - /partner/**
~~~

Ví dụ trên chỉ chọn các path thuộc hai prefix. Có thể kết hợp package và path để thu hẹp thêm:

~~~yaml
springdoc:
  packages-to-scan:
    - com.example.catalog
  paths-to-match:
    - /api/**
~~~

Một operation cần thỏa điều kiện lọc tương ứng mới được đưa vào document. Hãy kiểm tra path thực tế sau khi áp dụng context path, WebFlux base path hoặc cấu hình proxy; path được springdoc nhìn thấy là mapping của ứng dụng, không nhất thiết giống public URL đầy đủ bên ngoài proxy.

Các pattern thường dùng:

| Pattern | Ý nghĩa minh họa |
|---|---|
| `/api/**` | Path dưới prefix `/api` |
| `/api/v1/**` | Chỉ API v1 |
| `/partner/**` | Nhóm endpoint đối tác |
| `/api/orders/*` | Một segment sau `/api/orders` theo quy tắc path matcher |

Cú pháp và semantics matching cụ thể phụ thuộc Spring Framework/springdoc version. Nếu pattern không khớp, document có thể trống dù controller vẫn hoạt động. Hãy mở `/v3/api-docs` và kiểm tra `paths` sau mỗi lần đổi filter.

## 5. Loại trừ package và path

Khi phần lớn API cần công bố nhưng có một số khu vực cần loại bỏ, có thể dùng `packages-to-exclude` hoặc `paths-to-exclude`:

~~~yaml
springdoc:
  packages-to-scan:
    - com.example.catalog
  packages-to-exclude:
    - com.example.catalog.internal
  paths-to-exclude:
    - /api/internal/**
    - /api/debug/**
~~~

Dùng package exclusion khi controller nội bộ được tổ chức riêng. Dùng path exclusion khi muốn loại một route prefix bất kể package chứa handler.

Có thể kết hợp include và exclude để tài liệu rõ ràng hơn. Sau khi cấu hình, luôn kiểm tra các endpoint biên:
- Endpoint public nằm trong package cha có bị loại nhầm không?
- Endpoint admin có cùng package nhưng path khác có bị đưa vào không?
- Một route có nhiều mapping path có còn operation mong muốn không?
- Có document group khác cần giữ endpoint đã bị loại khỏi document mặc định không?

Không xem `paths-to-exclude` như authorization rule. Client vẫn có thể gọi endpoint nếu route runtime và security policy cho phép, kể cả khi endpoint không xuất hiện trong OpenAPI document.

## 6. Ẩn một controller hoặc operation cụ thể

Nếu chỉ cần ẩn một số endpoint riêng lẻ, có thể dùng annotation thay vì tạo thêm filter toàn cục.

Ẩn cả controller:

~~~java
import io.swagger.v3.oas.annotations.Hidden;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@Hidden
@RestController
@RequestMapping("/internal/diagnostics")
class DiagnosticsController {
    // Các endpoint không công bố trong OpenAPI
}
~~~

Ẩn một method:

~~~java
import io.swagger.v3.oas.annotations.Operation;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
class OrderController {

    @Operation(hidden = true)
    @GetMapping("/api/orders/reindex")
    void reindex() {
        // Tác vụ nội bộ
    }
}
~~~

Dùng `@Hidden` khi muốn loại resource hoặc handler khỏi tài liệu. Dùng `@Operation(hidden = true)` khi đã khai báo operation và muốn ẩn operation đó.

Ẩn operation chỉ ảnh hưởng đến tài liệu. Endpoint vẫn có thể tồn tại và cần được bảo vệ bằng Spring Security, gateway hoặc kiểm tra quyền trong ứng dụng. Không dùng annotation ẩn như một biện pháp bảo mật.

## 7. GroupedOpenApi để tạo document theo phạm vi

Một ứng dụng có thể công bố nhiều nhóm tài liệu, ví dụ public API, partner API và internal API. Mỗi group có thể có package/path filter riêng.

~~~java
import org.springdoc.core.models.GroupedOpenApi;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class OpenApiGroupsConfiguration {

    @Bean
    GroupedOpenApi publicApi() {
        return GroupedOpenApi.builder()
            .group("public")
            .packagesToScan("com.example.catalog.publicapi")
            .pathsToMatch("/api/public/**")
            .build();
    }

    @Bean
    GroupedOpenApi partnerApi() {
        return GroupedOpenApi.builder()
            .group("partner")
            .packagesToScan("com.example.catalog.partner")
            .pathsToMatch("/partner/**")
            .build();
    }
}
~~~

Với cấu hình group mặc định của springdoc, document thường được truy cập theo dạng:

~~~text
/v3/api-docs/public
/v3/api-docs/partner
~~~

Tên group trở thành một phần của endpoint tài liệu. Kiểm tra path thực tế nếu `springdoc.api-docs.path` đã được tùy chỉnh.

Group giúp phân phối tài liệu theo đối tượng tiêu thụ và giới hạn số operation trong mỗi document. Tuy nhiên, mỗi group là một document cần tạo và duy trì. Quá nhiều group hoặc các group chồng lấn lớn có thể làm tăng tổng thời gian xử lý, bộ nhớ cache và dung lượng tài liệu.

Nên tạo group theo ranh giới có ý nghĩa:
- Đối tượng tiêu thụ khác nhau, ví dụ public và partner.
- Miền nghiệp vụ độc lập.
- API version có lifecycle khác nhau.
- Chính sách công bố và bảo mật tài liệu khác nhau.

Không tạo một group cho từng controller hoặc từng operation nếu không có nhu cầu phân phối thực tế.

## 8. Tránh group chồng lấn ngoài ý muốn

Hai group có thể cùng bao gồm một operation nếu package/path filter của chúng giao nhau. Điều này không nhất thiết sai, nhưng cần chủ đích.

Ví dụ:
- Group `public` chọn `/api/**`.
- Group `orders` chọn `/api/orders/**`.

Các operation đơn hàng có thể xuất hiện trong cả hai document. Nếu mỗi document được tải và validate riêng, chi phí tạo/duy trì schema có thể lặp lại.

Hãy lập bảng ranh giới group trước khi tạo cấu hình:

| Group | Package | Path | Đối tượng |
|---|---|---|---|
| public | `com.example.api.publicapi` | `/api/public/**` | Ứng dụng bên ngoài |
| partner | `com.example.api.partner` | `/partner/**` | Đối tác tích hợp |
| internal | `com.example.api.internal` | `/internal/**` | Đội vận hành |

Nếu group nội bộ không được công bố ra ngoài, bảo vệ endpoint document của group đó bằng security policy riêng. Việc đặt tên `internal` hoặc ẩn group khỏi dropdown Swagger UI không tự bảo vệ JSON document.

## 9. Số handler ảnh hưởng đến số operation như thế nào?

Mỗi handler mapping được đưa vào document có thể tạo một hoặc nhiều operation tùy mapping. Ví dụ một method có thể hỗ trợ nhiều HTTP method hoặc nhiều path mapping.

Không nên dùng số controller class làm đại diện cho kích thước tài liệu. Các chỉ số cần phân biệt:

- **Controller count:** số lớp controller.
- **Handler count:** số method/handler được Spring đăng ký.
- **Path count:** số path trong `paths`.
- **Operation count:** tổng số HTTP method operation dưới các path.
- **Schema count:** số component schema được tạo.
- **Document count:** số OpenAPI document/group cần sinh.

Một controller có 30 method mapping có thể tạo nhiều operation hơn 10 controller nhỏ. Ngược lại, nhiều controller có thể chỉ cung cấp một số endpoint rất ít được chọn bởi filter.

Ví dụ một path có hai operation:

~~~yaml
paths:
  /api/orders:
    get:
      operationId: listOrders
      responses:
        "200":
          description: OK
    post:
      operationId: createOrder
      responses:
        "201":
          description: Created
~~~

Path count ở đây là 1, nhưng operation count là 2. Khi đo quy mô tài liệu, hãy đếm operation riêng với path.

## 10. Số schema phụ thuộc vào đồ thị kiểu dữ liệu

Schema được khám phá từ request/response type và các kiểu được tham chiếu bên trong chúng. Đồ thị có thể mở rộng theo quan hệ property:

~~~text
CreateOrderRequest
  ├── CustomerReference
  ├── List<OrderLine>
  │     └── ProductReference
  └── ShippingAddress

OrderResponse
  ├── OrderStatus
  ├── List<OrderLineResponse>
  └── Money
~~~

Một operation có thể kéo theo nhiều schema component. Một DTO dùng chung bởi nhiều operation thường được tham chiếu lại thay vì tạo một component độc lập cho mỗi lần dùng, nhưng schema inline, generic specialization hoặc annotation khác nhau có thể làm output phức tạp hơn.

Các yếu tố làm schema graph lớn hoặc khó xử lý:
- DTO lồng sâu nhiều cấp.
- Nhiều generic wrapper hoặc collection lồng nhau.
- Polymorphism với `oneOf`, `allOf`, discriminator và nhiều subtype.
- Enum lớn hoặc model có nhiều property.
- Jackson mixin, naming strategy và custom serializer.
- Annotation `@Schema` hoặc customizer tạo schema bổ sung.
- Recursive model có tham chiếu vòng.

Vì vậy, giảm số operation thường giảm schema được khám phá, nhưng không theo tỷ lệ cố định. Một endpoint trả về model đồ thị lớn có thể tốn công xử lý hơn nhiều endpoint trả về scalar đơn giản.

## 11. Schema được tham chiếu vẫn cần có dù package DTO nằm ngoài vùng scan

Giả sử controller nằm trong `com.example.catalog.api`, còn DTO ở `com.example.catalog.contract`:

~~~java
package com.example.catalog.api;

import com.example.catalog.contract.OrderResponse;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;

@RestController
class OrderController {

    @GetMapping("/api/orders/{id}")
    OrderResponse getOrder(@PathVariable String id) {
        // ...
        return null;
    }
}
~~~

~~~java
package com.example.catalog.contract;

public record OrderResponse(
    String id,
    String status,
    CustomerSummary customer
) {
}

record CustomerSummary(String customerId, String displayName) {
}
~~~

Nếu handler được chọn, springdoc vẫn cần mô tả `OrderResponse` và các kiểu được tham chiếu trong đó. Không cần thêm package DTO vào `packages-to-scan` chỉ để schema xuất hiện. Làm vậy có thể khiến springdoc coi package model như vùng handler scan dù package đó không chứa API mapping.

Nếu schema thiếu, hãy kiểm tra kiểu method/request body, Jackson visibility, annotation và customizer trước khi mở rộng package filter.

## 12. Ảnh hưởng của số group và cache tài liệu

Mỗi group có thể có tập operation và schema khác nhau. Khi có nhiều group:
- Thời gian tạo document đầu tiên có thể tăng.
- Schema dùng chung có thể được phân tích hoặc tuần tự hóa trong nhiều document.
- Tổng dung lượng JSON/YAML tăng.
- Cache của từng document có thể giữ thêm dữ liệu trong bộ nhớ.
- Swagger UI có thể cần tải document tương ứng khi người dùng đổi group.

Springdoc có cơ chế cache OpenAPI document trong các cấu hình thông thường. Thuộc tính `springdoc.cache.disabled` có thể tắt cache ở các phiên bản hỗ trợ; chỉ tắt khi thực sự cần tài liệu thay đổi theo request hoặc có lý do kiểm thử cụ thể. Tắt cache có thể khiến việc tạo document lặp lại tốn CPU hơn.

Cache giúp giảm chi phí ở các lần đọc lặp lại, nhưng không xóa chi phí tạo document ban đầu. Nếu cần tối ưu lần truy cập đầu, hãy giảm phạm vi handler/schema, kiểm tra customizer và đo thời gian cold generation.

Nếu customizer tạo nội dung phụ thuộc user, tenant hoặc header request, không giả định cache OpenAPI mặc định tự phân biệt mọi biến thể. Tài liệu OpenAPI thường nên ổn định theo application/group; nội dung phụ thuộc người gọi cần thiết kế riêng và kiểm tra rủi ro lộ dữ liệu giữa các request.

## 13. Đo thời gian tạo OpenAPI trước và sau khi lọc

Đo riêng ba giai đoạn:
1. Thời gian khởi động Spring Boot.
2. Thời gian request OpenAPI đầu tiên sau khi ứng dụng khởi động.
3. Thời gian request lặp lại khi document đã được cache.

Dùng cùng máy, profile, JVM, dữ liệu cấu hình và phiên bản dependency khi so sánh. Chạy nhiều lần và ghi median hoặc p95 thay vì kết luận từ một lần đo.

Ví dụ đo request đầu tiên sau khi restart:

~~~bash
curl -sS -o /dev/null \
  -w 'first OpenAPI request: %{time_total}s\n' \
  http://localhost:8080/v3/api-docs
~~~

Gọi lặp lại để đo warm request:

~~~bash
for i in 1 2 3 4 5; do
  curl -sS -o /dev/null \
    -w 'warm OpenAPI request: %{time_total}s\n' \
    http://localhost:8080/v3/api-docs
done
~~~

Nếu bật cache, warm request thường nhanh hơn cold request. Nếu không, hãy xác nhận phiên bản springdoc và cấu hình cache trước khi so sánh.

Không đo qua proxy ở một lần và gọi trực tiếp backend ở lần khác. Network latency, TLS handshake, authentication và gateway có thể làm sai lệch kết quả. Nếu cần đo thời gian xử lý server chính xác, kết hợp log/metric phía ứng dụng với thời gian HTTP client.

## 14. Đếm path, operation và schema trong OpenAPI JSON

Sau khi tải document:

~~~bash
curl -fsS http://localhost:8080/v3/api-docs -o openapi.json
~~~

Có thể dùng `jq` để lấy số liệu cơ bản:

~~~bash
jq '{
  openapi: .openapi,
  pathCount: (.paths | length),
  operationCount: ([
    .paths[] | to_entries[]
    | select(
        .key == "get" or .key == "put" or .key == "post" or
        .key == "delete" or .key == "options" or .key == "head" or
        .key == "patch" or .key == "trace"
      )
  ] | length),
  schemaCount: (.components.schemas // {} | length)
}' openapi.json
~~~

Số liệu giúp so sánh trước/sau khi thay đổi filter:
- Path count giảm nhưng operation count có thể giảm khác tỷ lệ.
- Schema count giảm khi một số model không còn được tham chiếu.
- Schema count không giảm nhiều nếu nhiều operation cùng dùng DTO chung.
- Document group có thể có số liệu riêng.

Đây là chỉ số quy mô, không phải benchmark đầy đủ. Một schema phức tạp có thể tốn công xử lý hơn nhiều schema đơn giản; kích thước file và thời gian serialization cũng cần được xem xét.

## 15. Cấu hình lọc cho default document và group riêng

Nếu chỉ cần một tài liệu, dùng properties có thể đủ:

~~~yaml
springdoc:
  packages-to-scan:
    - com.example.catalog.api
  paths-to-match:
    - /api/**
  packages-to-exclude:
    - com.example.catalog.api.internal
  paths-to-exclude:
    - /api/internal/**
~~~

Nếu có nhiều nhóm với phạm vi riêng, khai báo `GroupedOpenApi` để mỗi group có filter rõ ràng:

~~~java
@Bean
GroupedOpenApi orderApi() {
    return GroupedOpenApi.builder()
        .group("orders")
        .packagesToScan("com.example.catalog.orders")
        .pathsToMatch("/api/orders/**")
        .pathsToExclude("/api/orders/internal/**")
        .build();
}
~~~

Không nên cấu hình include/exclude toàn cục quá hẹp rồi kỳ vọng group riêng tự động khôi phục mọi endpoint đã bị loại. Hãy kiểm tra cách version springdoc đang dùng kết hợp cấu hình global và group-specific filters. Mở endpoint document của từng group và xác nhận path thực tế.

Nếu dùng custom `OpenAPI` bean, `OpenApiCustomizer` hoặc `GlobalOpenApiCustomizer`, hãy kiểm tra chúng không thêm operation/schema ngoài phạm vi dự kiến. Filter scan không nhất thiết loại bỏ các component mà customizer chủ động thêm.

## 16. Phạm vi quét và GraalVM Native Image

Native Image biên dịch ứng dụng thành executable native bằng phân tích AOT và đóng gói các thành phần cần thiết. Những thao tác dựa trên reflection, resource lookup hoặc classpath discovery cần được hỗ trợ bởi metadata/hints phù hợp.

Thu hẹp operation scan có thể:
- Giảm số operation và schema mà springdoc tạo cho document.
- Giảm kích thước OpenAPI JSON được tạo và phân phối.
- Tránh xử lý những model chỉ thuộc nhóm API không cần công bố trong document đó.
- Làm rõ tập DTO cần kiểm tra reflection/serialization trong native executable.

Nhưng filter springdoc không tự loại controller bean khỏi Spring AOT, không tự sinh toàn bộ reflection hint và không bảo đảm native image nhỏ hơn theo một tỷ lệ cố định. Nếu controller vẫn được component scan, các class và dependency của nó vẫn có thể được đưa vào application context/native image.

Với DTO dùng cho request/response, Spring cung cấp annotation như `@RegisterReflectionForBinding` để đăng ký reflection hints cho binding khi cần:

~~~java
import org.springframework.aot.hint.annotation.RegisterReflectionForBinding;
import org.springframework.context.annotation.Configuration;

@Configuration
@RegisterReflectionForBinding({
    CreateOrderRequest.class,
    OrderResponse.class
})
class ApiReflectionConfiguration {
}
~~~

Đây là ví dụ cho model cần binding/reflection trong native runtime. Không coi annotation này là giải pháp chung cho mọi reflection mà springdoc, Jackson hoặc thư viện khác có thể sử dụng. Chỉ bổ sung hint sau khi kiểm tra native build output và lỗi runtime cụ thể; kiểm thử bằng executable native thực tế.

Nếu tài liệu chỉ cần phân phối cho client, một lựa chọn khác là export OpenAPI JSON/YAML trong CI bằng JVM profile kiểm thử rồi publish artifact tĩnh. Khi đó, runtime native application không nhất thiết phải cung cấp Swagger UI hoặc sinh tài liệu động trong production. Tuy nhiên, nếu yêu cầu sản phẩm cần `/v3/api-docs` trên native executable, phải kiểm tra endpoint đó trong native test.

## 17. Checklist tối ưu phạm vi quét

- [ ] Phân biệt component scanning của Spring với filter operation của springdoc.
- [ ] Xác định package chứa controller/handler cần công bố.
- [ ] Dùng `springdoc.packages-to-scan` khi ranh giới package rõ.
- [ ] Dùng `springdoc.paths-to-match` khi ranh giới API thể hiện qua path.
- [ ] Dùng `packages-to-exclude` hoặc `paths-to-exclude` cho vùng không công bố.
- [ ] Dùng `@Hidden` hoặc `@Operation(hidden = true)` cho trường hợp riêng lẻ.
- [ ] Không coi ẩn operation là bảo vệ endpoint.
- [ ] Giữ DTO được tham chiếu dù nằm ngoài package handler scan.
- [ ] Tạo `GroupedOpenApi` theo đối tượng tiêu thụ hoặc miền nghiệp vụ.
- [ ] Tránh group chồng lấn và group quá nhỏ nếu không có nhu cầu.
- [ ] Kiểm tra customizer không thêm operation/schema ngoài ý muốn.
- [ ] Đếm path, operation và schema trước/sau khi lọc.
- [ ] Đo cold generation riêng với warm cached request.
- [ ] Đo cùng môi trường và cấu hình để so sánh có ý nghĩa.
- [ ] Với native image, kiểm tra AOT/reflection hints và chạy executable thật.
- [ ] Xác nhận `/v3/api-docs` hoặc endpoint group chứa đúng tập operation cần công bố.

## Tài liệu tham khảo

- [springdoc-openapi – Properties](https://springdoc.org/properties.html): các thuộc tính lọc package/path, cache và cấu hình OpenAPI.
- [springdoc-openapi – GroupedOpenApi](https://springdoc.org/#springdoc-openapi-core): cấu hình nhiều document group.
- [Spring Framework – Classpath Scanning](https://docs.spring.io/spring-framework/reference/core/beans/classpath-scanning.html): cơ chế tìm bean và component scanning.
- [Spring Boot – AOT Processing](https://docs.spring.io/spring-boot/reference/packaging/aot.html): xử lý AOT cho ứng dụng Spring Boot.
- [Spring Boot – GraalVM Native Images](https://docs.spring.io/spring-boot/reference/packaging/native-image/index.html): xây dựng và kiểm tra native executable.
- [Spring Framework – Runtime Hints](https://docs.spring.io/spring-framework/reference/core/aot.html): reflection, resource và proxy hints cho AOT/native image.
- [OpenAPI Specification](https://spec.openapis.org/oas/latest.html): cấu trúc paths, operations và components của OpenAPI.
