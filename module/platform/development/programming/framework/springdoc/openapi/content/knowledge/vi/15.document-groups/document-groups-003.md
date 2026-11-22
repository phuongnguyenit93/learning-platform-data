# Lọc theo pathsToMatch và pathsToExclude

Trong một ứng dụng Spring Boot, các controller có thể phục vụ nhiều nhóm người dùng và nhiều mục đích: API công khai cho khách hàng, API quản trị, endpoint nội bộ cho dịch vụ khác hoặc endpoint phục vụ vận hành. Khi springdoc-openapi tạo tài liệu OpenAPI, không phải lúc nào nhóm cũng muốn đưa mọi endpoint vào cùng một đặc tả. Có thể dùng bộ lọc đường dẫn để chọn các endpoint cần công bố và loại các nhánh không thuộc phạm vi của tài liệu.

Hai thuộc tính chính là **pathsToMatch** và **pathsToExclude**. Thuộc tính thứ nhất xác định những đường dẫn được đưa vào; thuộc tính thứ hai loại các đường dẫn không muốn xuất hiện. Chúng có thể được cấu hình ở phạm vi toàn ứng dụng, theo từng nhóm tài liệu bằng **GroupedOpenApi**, hoặc qua cấu hình **springdoc.group-configs** trong application.yml.

## 1. Phân biệt lọc đường dẫn và lọc package

springdoc-openapi có thể giới hạn tài liệu theo đường dẫn endpoint hoặc theo package chứa controller:

| Cấu hình | Mục đích | Ví dụ |
| --- | --- | --- |
| **pathsToMatch** | Chọn các đường dẫn endpoint được đưa vào tài liệu | `/api/public/**` |
| **pathsToExclude** | Loại các đường dẫn khỏi tài liệu | `/api/internal/**` |
| **packagesToScan** | Chỉ quét controller thuộc package được chỉ định | **com.example.orders.api** |
| **packagesToExclude** | Bỏ qua controller thuộc package được chỉ định | **com.example.internal.web** |

Lọc theo path phù hợp khi cấu trúc URL thể hiện rõ phạm vi API, chẳng hạn `/api/v1/**`, `/api/admin/**` và `/internal/**`. Lọc theo package hữu ích khi controller được tổ chức theo module hoặc miền nghiệp vụ, dù URL không có prefix riêng.

Một nhóm có thể kết hợp cả path và package. Ví dụ, nhóm chỉ nhận endpoint dưới `/api/v1/**` và controller thuộc **com.example.orders.api** sẽ được giới hạn bởi cả hai điều kiện. Cách kết hợp này hữu ích khi ứng dụng có nhiều controller dùng chung prefix URL hoặc nhiều module cùng chứa endpoint có cấu trúc tương tự.

## 2. Hiểu pathsToMatch và pathsToExclude

**pathsToMatch** nhận một hoặc nhiều mẫu đường dẫn. Khi khai báo, nhóm tài liệu chỉ lấy những endpoint khớp với các mẫu được chọn. **pathsToExclude** nhận danh sách mẫu cần loại ra khỏi kết quả.

Ví dụ, API công khai có các đường dẫn:

| Endpoint | Mục đích |
| --- | --- |
| **/api/orders** | Tạo hoặc liệt kê đơn hàng |
| **/api/orders/{id}** | Xem chi tiết đơn hàng |
| **/api/catalog/products** | Danh sách sản phẩm |
| **/api/internal/reconciliation** | Đối soát nội bộ |
| **/api/admin/users** | Quản lý người dùng quản trị |

Nếu tài liệu dành cho client bên ngoài chỉ cần đơn hàng và catalog, có thể chọn nhánh `/api/**` rồi loại `/api/internal/**` và `/api/admin/**`. Các mẫu include có thể liệt kê nhiều nhánh; các mẫu exclude dùng để bỏ những nhánh không thuộc phạm vi.

Một số mẫu thường gặp:

| Mẫu | Ý nghĩa sử dụng |
| --- | --- |
| `/api/v1/**` | Chọn các endpoint thuộc nhánh API phiên bản 1 |
| `/api/orders/**` | Chọn endpoint trong nhánh orders |
| `/api/internal/**` | Nhận diện nhánh nội bộ để loại khỏi tài liệu công khai |
| `/api/admin/**` | Nhận diện nhánh quản trị |
| **/api/health** | Chọn hoặc loại một đường dẫn cụ thể |
| **/api/orders/{id}** | Đường dẫn có biến path theo mapping của controller |

Các ví dụ dùng wildcard theo quy ước path matching của hệ sinh thái Spring. Mẫu `/**` thường được dùng để bao quát một nhánh và các đường dẫn con. Không xem chuỗi pattern là regular expression. Khi dùng cú pháp phức tạp hoặc nâng cấp Spring Framework, hãy xác minh kết quả vì Spring MVC có các cơ chế matching như PathPattern và AntPathMatcher với khác biệt theo phiên bản.

Đường dẫn trong bộ lọc là path của mapping controller, ví dụ **/api/orders/{id}**. Không đưa scheme, hostname hoặc query string vào pattern. Nếu ứng dụng chạy sau context path hoặc reverse proxy, hãy kiểm tra endpoint OpenAPI được sinh để xác nhận path mà springdoc đang dùng cho việc lọc.

## 3. Lọc toàn bộ tài liệu bằng application.yml

Nếu muốn áp dụng cùng một phạm vi cho tài liệu mặc định của ứng dụng, có thể cấu hình hai thuộc tính ở cấp **springdoc**:

~~~yaml
springdoc:
  paths-to-match:
    - /api/**
  paths-to-exclude:
    - /api/internal/**
    - /api/admin/**
~~~

Trong ví dụ, springdoc chỉ đưa các endpoint thuộc nhánh `/api/**` vào tài liệu mặc định, sau đó loại nhánh nội bộ và quản trị. Cách cấu hình này phù hợp khi ứng dụng chỉ có một tài liệu hoặc khi toàn bộ tài liệu đều dùng chung quy tắc lọc.

Có thể khai báo nhiều path pattern trong danh sách YAML. Nếu dùng file properties, các danh sách có thể khai báo dưới dạng chuỗi phân tách bằng dấu phẩy theo tài liệu cấu hình springdoc:

~~~properties
springdoc.paths-to-match=/api/**,/catalog/**
springdoc.paths-to-exclude=/api/internal/**,/catalog/private/**
~~~

Tên thuộc tính dạng kebab-case như **paths-to-match** và **paths-to-exclude** là cách viết nên dùng trong application.yml và application.properties. Tài liệu FAQ cũ cũng có ví dụ dạng camelCase **pathsToMatch**; khi viết cấu hình mới, hãy dùng tên chuẩn trong bảng Configuration Properties của phiên bản springdoc đang triển khai.

Lưu ý: cấu hình toàn cục ảnh hưởng đến phạm vi tài liệu được sinh ở cấp ứng dụng. Nếu mỗi nhóm cần một tập endpoint khác nhau, hãy đặt bộ lọc trên từng nhóm thay vì áp dụng một quy tắc toàn cục quá hẹp rồi cố mở rộng lại ở nhóm riêng.

## 4. Lọc riêng từng nhóm bằng GroupedOpenApi

Khi một ứng dụng có nhiều tài liệu, cách rõ ràng là khai báo từng **GroupedOpenApi** với tên nhóm riêng, mẫu include và mẫu exclude tương ứng.

Ví dụ dưới đây tạo tài liệu cho API công khai:

~~~java
import org.springdoc.core.models.GroupedOpenApi;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class OpenApiGroupConfiguration {

    @Bean
    public GroupedOpenApi publicApi() {
        return GroupedOpenApi.builder()
            .group("public")
            .pathsToMatch("/api/**")
            .pathsToExclude(
                "/api/internal/**",
                "/api/admin/**"
            )
            .build();
    }
}
~~~

Trong cấu hình này:

- **group("public")** đặt tên nhóm tài liệu là public.
- **pathsToMatch("/api/**")** chọn các endpoint trong nhánh API.
- **pathsToExclude(...)** loại nhánh nội bộ và quản trị khỏi nhóm.

Đặc tả của nhóm được cung cấp mặc định tại:

~~~text
http://localhost:8080/v3/api-docs/public
~~~

Tên nhóm phải duy nhất trong ứng dụng. Nếu đã đổi **springdoc.api-docs.path**, endpoint nhóm sẽ dùng base path mới thay cho **/v3/api-docs**.

Có thể khai báo nhiều nhóm với phạm vi khác nhau:

~~~java
@Bean
public GroupedOpenApi customerApi() {
    return GroupedOpenApi.builder()
        .group("customer")
        .pathsToMatch(
            "/api/orders/**",
            "/api/catalog/**"
        )
        .pathsToExclude("/api/orders/internal/**")
        .build();
}

@Bean
public GroupedOpenApi adminApi() {
    return GroupedOpenApi.builder()
        .group("admin")
        .pathsToMatch("/api/admin/**")
        .build();
}
~~~

Nhóm customer chứa API đơn hàng và catalog, còn nhóm admin chứa các endpoint quản trị. Một endpoint có thể xuất hiện trong nhiều nhóm nếu các mẫu của nhiều nhóm cùng chọn nó. Việc một endpoint xuất hiện trong một nhóm không tự động loại endpoint đó khỏi nhóm khác.

Với springdoc-openapi v2 dùng Spring Boot 3, import **GroupedOpenApi** thường là **org.springdoc.core.models.GroupedOpenApi**. Dòng springdoc 1.x có package khác; khi làm việc với dự án cũ, hãy đối chiếu import theo phiên bản đang dùng.

## 5. Khai báo nhóm và bộ lọc trong application.yml

Không bắt buộc phải tạo bean **GroupedOpenApi** nếu muốn khai báo nhóm bằng cấu hình Spring Boot. springdoc hỗ trợ danh sách **springdoc.group-configs**:

~~~yaml
springdoc:
  group-configs:
    - group: customer
      display-name: Customer API
      paths-to-match:
        - /api/orders/**
        - /api/catalog/**
      paths-to-exclude:
        - /api/orders/internal/**

    - group: admin
      display-name: Admin API
      paths-to-match:
        - /api/admin/**

    - group: partner
      display-name: Partner API
      paths-to-match:
        - /partner/**
      paths-to-exclude:
        - /partner/internal/**
~~~

Mỗi phần tử trong **group-configs** định nghĩa một nhóm:

- **group** là tên định danh duy nhất và được dùng trong URL tài liệu.
- **display-name** là tên hiển thị trong danh sách nhóm của Swagger UI khi cấu hình giao diện sử dụng các nhóm.
- **paths-to-match** chọn các nhánh endpoint cho nhóm.
- **paths-to-exclude** loại các nhánh không muốn đưa vào nhóm.

Với cấu hình trên, các URL tài liệu mặc định là:

~~~text
/v3/api-docs/customer
/v3/api-docs/admin
/v3/api-docs/partner
~~~

Có thể thêm **packages-to-scan** hoặc **packages-to-exclude** trong từng nhóm nếu muốn kết hợp lọc theo package. Không cần khai báo bean cùng một nhóm lần nữa nếu đã định nghĩa nhóm bằng **springdoc.group-configs**; nên chọn một nguồn cấu hình cho mỗi nhóm để tránh khó xác định nhóm nào đang được đăng ký.

## 6. Kết hợp lọc path với package

Path thể hiện cấu trúc URL, còn package thể hiện vị trí controller trong mã nguồn. Ví dụ, dự án có thể đặt controller đơn hàng ở **com.example.order.api** và controller catalog ở **com.example.catalog.api**, trong khi cả hai đều dùng prefix `/api/v1/**`.

Có thể giới hạn nhóm theo cả hai điều kiện:

~~~java
@Bean
public GroupedOpenApi orderV1Api() {
    return GroupedOpenApi.builder()
        .group("order-v1")
        .packagesToScan("com.example.order.api")
        .pathsToMatch("/api/v1/**")
        .pathsToExclude("/api/v1/orders/internal/**")
        .build();
}
~~~

Nhóm chỉ lấy controller trong package order và endpoint khớp nhánh `/api/v1/**`. Nhánh nội bộ tiếp tục bị loại bằng **pathsToExclude**. Cách này giảm khả năng một controller mới ở module khác vô tình xuất hiện trong tài liệu chỉ vì URL của nó dùng chung prefix.

Nếu controller được di chuyển package nhưng URL không đổi, bộ lọc package có thể làm endpoint biến mất khỏi nhóm. Ngược lại, nếu URL thay đổi nhưng package giữ nguyên, bộ lọc path có thể không còn khớp. Khi thay đổi cấu trúc mã nguồn hoặc API, hãy kiểm tra cả hai điều kiện.

## 7. Chọn giữa bộ lọc path và @Hidden

Không phải mọi trường hợp đều cần pattern. Nếu chỉ cần ẩn một controller hoặc một operation cụ thể, annotation **@Hidden** hoặc thuộc tính ẩn của annotation operation có thể dễ đọc hơn:

~~~java
import io.swagger.v3.oas.annotations.Hidden;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class InternalDiagnosticsController {

    @Hidden
    @GetMapping("/api/internal/diagnostics")
    public String diagnostics() {
        return "internal";
    }
}
~~~

So sánh:

| Cách làm | Phù hợp khi |
| --- | --- |
| **pathsToMatch / pathsToExclude** | Cần quản lý hàng loạt endpoint theo cấu trúc URL hoặc nhóm API |
| **packagesToScan / packagesToExclude** | Ranh giới module được thể hiện bằng package |
| **@Hidden** | Chỉ một controller hoặc operation cần ẩn khỏi tài liệu |

Lọc path là cách quản lý phạm vi ở cấp nhóm. **@Hidden** thể hiện chủ ý ngay tại mã nguồn của endpoint. Có thể phối hợp chúng nếu dự án cần, nhưng nên giữ quy tắc dễ giải thích để người bảo trì biết vì sao endpoint xuất hiện hoặc biến mất.

## 8. Lọc path không phải là bảo mật endpoint

Đây là điểm cần phân biệt rõ: **pathsToExclude** chỉ điều khiển nội dung đặc tả OpenAPI được sinh. Nó không chặn HTTP request đến endpoint, không thay thế Spring Security, không ẩn endpoint khỏi người đã biết URL và không bảo vệ dữ liệu.

Ví dụ, loại `/api/admin/**` khỏi tài liệu customer không có nghĩa người dùng customer không thể gọi endpoint admin. Quyền truy cập vẫn phải được kiểm tra ở runtime bằng Spring Security, authorization rule, kiểm tra quyền trong service hoặc cơ chế bảo vệ tương ứng.

Tương tự, ẩn Swagger UI hoặc không đưa một path vào OpenAPI không phải biện pháp bảo mật. Nếu tài liệu chứa endpoint nội bộ, cần bảo vệ cả endpoint tài liệu **/v3/api-docs** và các URL group theo chính sách truy cập. Bộ lọc chỉ giúp tạo đúng tài liệu cho từng đối tượng tiêu thụ.

## 9. Kiểm tra kết quả lọc trong OpenAPI JSON

Sau khi cấu hình, hãy xác minh trực tiếp đặc tả của từng nhóm. Không chỉ dựa vào việc ứng dụng khởi động thành công hoặc Swagger UI hiển thị tên nhóm.

Với nhóm customer:

~~~bash
curl -s http://localhost:8080/v3/api-docs/customer
~~~

Với nhóm admin:

~~~bash
curl -s http://localhost:8080/v3/api-docs/admin
~~~

Trong response JSON, kiểm tra khóa **paths**:

- Endpoint được include phải xuất hiện.
- Endpoint khớp exclude không được xuất hiện.
- Endpoint thuộc nhóm khác không được xuất hiện nếu không có mẫu include phù hợp.
- Nếu nhiều method dùng cùng path, hãy xác nhận các operation mong đợi vẫn có mặt.

Nếu máy có **jq**, có thể liệt kê các path:

~~~bash
curl -s http://localhost:8080/v3/api-docs/customer | jq -r '.paths | keys[]'
~~~

Đối chiếu danh sách kết quả với mapping trong controller. Nếu có context path, reverse proxy hoặc base path tùy chỉnh, dùng URL thực tế mà môi trường triển khai công bố.

Một quy trình kiểm thử tích hợp nên có endpoint đại diện cho từng trường hợp:

| Endpoint kiểm thử | Kết quả mong đợi trong nhóm customer |
| --- | --- |
| **/api/orders** | Có |
| **/api/catalog/products** | Có |
| **/api/orders/internal/reconcile** | Không |
| **/api/admin/users** | Không |
| **/internal/metrics** | Không |

Nên tự động hóa việc kiểm tra tập path quan trọng khi build hoặc trong CI. Nếu hợp đồng API thay đổi, bài kiểm thử sẽ phát hiện endpoint bị thêm hoặc bị loại ngoài dự kiến.

## 10. Lỗi thường gặp và cách xử lý

| Biểu hiện | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Nhóm không có endpoint nào | Mẫu include không khớp path mapping hoặc cấu hình package quá hẹp | Kiểm tra path đầy đủ từ class-level và method-level mapping; nới mẫu include có chủ đích |
| Endpoint nội bộ vẫn xuất hiện | Mẫu exclude không khớp đúng prefix hoặc thiếu nhánh path thực tế | Mở **/v3/api-docs/{group}** và so sánh chính xác path trong **paths** |
| Endpoint cần thiết bị loại | Một mẫu exclude rộng đang bao phủ cả nhánh hợp lệ | Thu hẹp exclude hoặc tách endpoint theo cấu trúc path rõ hơn |
| Nhóm có endpoint từ package không mong muốn | Chỉ lọc path trong khi nhiều module dùng chung prefix | Kết hợp **packagesToScan** với **pathsToMatch** |
| Đã đổi YAML nhưng output chưa đổi | Ứng dụng chưa reload hoặc tài liệu được cache | Khởi động lại ứng dụng trong môi trường phát triển và kiểm tra lại endpoint docs |
| Nhóm không xuất hiện trong Swagger UI | Nhóm chưa được đăng ký hoặc UI chưa được cấu hình để liệt kê group | Kiểm tra **/v3/api-docs/{group}** trước, sau đó kiểm tra cấu hình Swagger UI |
| Một path có nhiều operation nhưng chỉ muốn ẩn một method | Bộ lọc path tác động theo đường dẫn, không phải lựa chọn method riêng | Dùng **@Hidden**/metadata operation hoặc cấu trúc endpoint khác |
| Nghĩ rằng exclude đã bảo vệ endpoint | Nhầm lọc tài liệu với authorization runtime | Cấu hình Spring Security và kiểm thử quyền truy cập HTTP riêng |

## 11. Quy trình thiết kế bộ lọc cho dự án

Khi bắt đầu tổ chức tài liệu cho nhiều nhóm API, có thể làm theo trình tự:

1. Liệt kê các endpoint thực tế từ mapping controller hoặc từ **/v3/api-docs**.
2. Phân loại endpoint theo đối tượng tiêu thụ: public, partner, admin, internal hoặc actuator.
3. Xác định prefix path có thể đại diện cho từng nhóm; nếu path dùng chung, xác định package controller tương ứng.
4. Chọn phạm vi cấu hình: toàn ứng dụng bằng **springdoc.paths-to-match**/**springdoc.paths-to-exclude**, hoặc từng nhóm bằng **GroupedOpenApi**/**springdoc.group-configs**.
5. Đặt include cho nhánh cần công bố và exclude cho nhánh cần loại khỏi nhóm.
6. Tạo nhóm có tên duy nhất, kiểm tra endpoint tài liệu **/v3/api-docs/{group}**.
7. Viết kiểm thử xác nhận một số path phải có và một số path phải vắng mặt.
8. Kiểm tra bảo mật runtime độc lập với tài liệu OpenAPI.

Không nên bắt đầu bằng một mẫu include quá rộng rồi chỉ thêm exclude theo từng lỗi phát hiện. Khi có danh sách endpoint rõ ràng, hãy chọn các nhánh cần công bố trước, sau đó thêm ngoại lệ có lý do cụ thể. Cách này giúp bộ lọc dễ bảo trì khi dự án thêm controller hoặc phiên bản API mới.

## 12. Checklist trước khi công bố nhóm tài liệu

- [ ] Tên nhóm duy nhất và có ý nghĩa với người tiêu thụ.
- [ ] **pathsToMatch** bao gồm đúng các nhánh API dự kiến.
- [ ] **pathsToExclude** loại đúng endpoint nội bộ hoặc ngoài phạm vi.
- [ ] Nếu cần, **packagesToScan** và **packagesToExclude** đã được kết hợp đúng.
- [ ] Không dùng domain, query string hoặc context path sai trong pattern.
- [ ] Đã kiểm tra JSON tại **/v3/api-docs/{group}**.
- [ ] Endpoint cần có xuất hiện và endpoint cần loại không xuất hiện.
- [ ] Đã kiểm thử endpoint runtime và Spring Security độc lập.
- [ ] Các nhóm không vô tình công bố cùng một endpoint ngoài chủ ý.
- [ ] CI có kiểm tra tập path quan trọng nếu tài liệu là hợp đồng phát hành.

## 13. Tài liệu tham khảo chính thức

- [springdoc-openapi Configuration Properties](https://springdoc.org/properties.html) — **springdoc.paths-to-match**, **springdoc.paths-to-exclude** và các thuộc tính lọc theo từng group.
- [springdoc-openapi FAQ v2](https://springdoc.org/v2/faq.html) — tạo nhiều OpenAPI definition bằng **GroupedOpenApi**, kết hợp path và package, URL tài liệu theo tên group.
- [springdoc-openapi Features v2](https://springdoc.org/v2/features.html) — chọn REST controller bằng cấu hình package hoặc path và annotation **@Hidden**.
- [Spring Framework — Path Matching](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-servlet/handlermapping-path.html) — cơ chế path matching trong Spring MVC, **PathPatternParser** và **AntPathMatcher**.
- [Spring Framework — Mapping Requests](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-requestmapping.html) — mẫu URL và cách khai báo mapping cho controller.

**pathsToMatch** và **pathsToExclude** giúp mỗi đặc tả OpenAPI chỉ chứa các endpoint thuộc phạm vi mong muốn. Khi kết hợp bộ lọc path với package, nhóm tài liệu rõ ràng và kiểm tra output JSON trong CI, springdoc-openapi có thể cung cấp tài liệu riêng cho khách hàng, đối tác và nhóm vận hành mà vẫn giữ một ứng dụng Spring Boot.
