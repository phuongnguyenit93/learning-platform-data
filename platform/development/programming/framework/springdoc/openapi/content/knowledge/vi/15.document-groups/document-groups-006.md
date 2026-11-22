# Khai báo nhóm bằng bean hoặc thuộc tính group-configs

## 1. Vì sao cần chia tài liệu OpenAPI thành nhóm?

Một ứng dụng Spring Boot có thể cung cấp nhiều nhóm endpoint: API công khai cho khách hàng, API quản trị, API nội bộ giữa các dịch vụ và API dành cho đối tác. Nếu tất cả endpoint xuất hiện trong một tài liệu OpenAPI, người đọc phải lọc thủ công phần liên quan và có thể nhìn thấy những operation không thuộc phạm vi tích hợp của họ.

Springdoc OpenAPI hỗ trợ **document groups** để tạo nhiều tài liệu OpenAPI từ cùng một ứng dụng. Mỗi nhóm chọn một tập operation theo các điều kiện như đường dẫn hoặc package chứa controller. Tài liệu của từng nhóm có thể được mở riêng bằng URL và hiển thị trong Swagger UI.

Có hai cách khai báo thường dùng:

- **GroupedOpenApi bean**: cấu hình nhóm bằng Java, phù hợp khi muốn dùng code, điều kiện hoặc customizer.
- **springdoc.group-configs**: khai báo nhóm trong application.yml hoặc application.properties, phù hợp với bộ lọc tĩnh và cấu hình tập trung.

Cả hai cách đều tạo các nhóm tài liệu cho Springdoc. Chọn một cách phù hợp với cấu trúc dự án, đặt tên nhóm ổn định và kiểm tra endpoint tài liệu sau khi ứng dụng khởi động.

## 2. GroupedOpenApi và nguyên tắc chọn operation

Một nhóm tài liệu được định danh bằng tên group. Group có thể giới hạn operation theo:

- **pathsToMatch**: chọn các đường dẫn API phù hợp với mẫu.
- **pathsToExclude**: loại các đường dẫn không muốn đưa vào nhóm.
- **packagesToScan**: chỉ xét controller trong các package được chỉ định.
- **packagesToExclude**: loại controller thuộc package nhất định.
- Các điều kiện bổ sung theo media type hoặc header nếu phiên bản Springdoc đang dùng hỗ trợ.

Ví dụ, nhóm public chỉ lấy endpoint dưới đường dẫn /api/public:

~~~java
@Bean
GroupedOpenApi publicApi() {
    return GroupedOpenApi.builder()
        .group("public")
        .pathsToMatch("/api/public/**")
        .build();
}
~~~

Nhóm admin có thể được chọn theo path và package:

~~~java
@Bean
GroupedOpenApi adminApi() {
    return GroupedOpenApi.builder()
        .group("admin")
        .packagesToScan("com.example.shop.api.admin")
        .pathsToMatch("/api/admin/**")
        .build();
}
~~~

Tên group là định danh dùng khi truy cập tài liệu. Nên dùng tên ngắn, ổn định, không chứa khoảng trắng và thể hiện phạm vi nghiệp vụ. Ví dụ public, admin, partner hoặc internal.

Khi kết hợp nhiều bộ lọc, hãy xem chúng như các điều kiện giới hạn tập operation và xác minh kết quả trong tài liệu được sinh ra. Đừng dựa vào tên package hoặc tên group để kết luận endpoint đã được đưa vào đúng nhóm.

## 3. Khai báo GroupedOpenApi bằng bean

GroupedOpenApi là một bean do Spring quản lý. Springdoc phát hiện các bean này và tạo một OpenAPI document riêng cho từng group.

Ví dụ cấu hình hai nhóm:

~~~java
@Configuration
public class OpenApiGroupConfiguration {

    @Bean
    public GroupedOpenApi publicApi() {
        return GroupedOpenApi.builder()
            .group("public")
            .pathsToMatch("/api/public/**")
            .build();
    }

    @Bean
    public GroupedOpenApi adminApi() {
        return GroupedOpenApi.builder()
            .group("admin")
            .pathsToMatch("/api/admin/**")
            .build();
    }
}
~~~

Với Springdoc 2.x, GroupedOpenApi nằm trong package org.springdoc.core.models. Ở dòng Springdoc 1.x, package có thể khác. Hãy dùng import tương ứng với phiên bản dependency trong dự án thay vì sao chép import giữa các major version.

Mỗi bean nên có tên group duy nhất. Nếu hai bean cùng dùng một group name, việc đăng ký và định tuyến tài liệu có thể xung đột hoặc tạo kết quả không như mong muốn.

Một cấu hình nhóm rõ ràng nên thể hiện:

- Phạm vi endpoint được chọn.
- Package controller tương ứng nếu dùng package filter.
- Các path cần loại trừ.
- Customizer riêng nếu tài liệu nhóm cần metadata khác.
- Quy tắc kiểm tra để bảo đảm endpoint không bị thiếu hoặc xuất hiện nhầm.

## 4. Lọc theo package bằng packagesToScan

Khi controller được tổ chức theo package nghiệp vụ, có thể chọn nhóm bằng packagesToScan:

~~~java
@Bean
public GroupedOpenApi orderApi() {
    return GroupedOpenApi.builder()
        .group("orders")
        .packagesToScan(
            "com.example.shop.api.orders",
            "com.example.shop.api.ordertracking"
        )
        .build();
}
~~~

Cấu hình này chọn controller thuộc các package đã khai báo. Nó hữu ích khi cấu trúc source code phản ánh rõ ranh giới API.

Tuy nhiên, package Java là chi tiết tổ chức mã nguồn. Một lần refactor đổi package có thể làm tài liệu nhóm mất operation dù URL API không đổi. Vì vậy:

- Giữ package filter đồng bộ với cấu trúc controller.
- Thêm test kiểm tra các operation quan trọng trong từng group.
- Không xem package name là ranh giới bảo mật.
- Dùng path filter bổ sung khi cần bảo đảm nhóm chỉ chứa một vùng URL cụ thể.

Nếu controller trong cùng package chứa cả endpoint public và internal, chỉ dùng packagesToScan có thể đưa cả hai vào cùng nhóm. Khi đó nên tách package, kết hợp pathsToMatch/pathsToExclude hoặc dùng quy tắc lọc phù hợp hơn.

## 5. Lọc theo path bằng pathsToMatch và pathsToExclude

Path filter phù hợp khi ranh giới nhóm được xác định bằng URL API.

Ví dụ:

~~~java
@Bean
public GroupedOpenApi catalogApi() {
    return GroupedOpenApi.builder()
        .group("catalog")
        .pathsToMatch("/api/products/**", "/api/categories/**")
        .pathsToExclude("/api/products/internal/**")
        .build();
}
~~~

Trong ví dụ:

- Nhóm chọn các operation dưới /api/products và /api/categories.
- Những operation dưới /api/products/internal bị loại khỏi nhóm.

Các pattern thường được viết theo cú pháp path matching mà Springdoc sử dụng. Hãy kiểm tra kết quả thực tế khi dùng wildcard, path variable hoặc base path do ứng dụng cấu hình.

Path được so khớp với đường dẫn operation trong OpenAPI. Nếu ứng dụng có context path hoặc servlet path riêng, cần xác minh đường dẫn xuất hiện trong tài liệu và cách Springdoc áp dụng filter ở phiên bản đang dùng.

Không nên chỉ chọn một path prefix rộng như /api/** nếu cùng prefix chứa API nội bộ, quản trị hoặc endpoint thử nghiệm. Dùng include và exclude rõ ràng để hạn chế việc công bố nhầm operation.

## 6. Khai báo nhóm bằng springdoc.group-configs trong YAML

Nếu nhóm chỉ cần bộ lọc tĩnh, có thể khai báo trong application.yml:

~~~yaml
springdoc:
  group-configs:
    - group: public
      paths-to-match:
        - /api/public/**
    - group: admin
      packages-to-scan:
        - com.example.shop.api.admin
      paths-to-match:
        - /api/admin/**
    - group: partner
      paths-to-match:
        - /api/partner/**
      paths-to-exclude:
        - /api/partner/internal/**
~~~

Mỗi phần tử trong group-configs mô tả một group. Trường group là định danh của nhóm; các trường packages-to-scan, paths-to-match và paths-to-exclude xác định operation thuộc tài liệu đó.

Có thể dùng danh sách nhiều package hoặc nhiều path pattern. Ví dụ một nhóm partner có thể lấy các đường dẫn /api/partner/v1/** và /api/partner/v2/** nếu chúng cùng thuộc một hợp đồng tài liệu.

Cấu hình trong YAML phù hợp khi:

- Nhóm chỉ dựa trên package/path.
- Muốn thay đổi phạm vi tài liệu theo profile hoặc môi trường.
- Muốn quản lý cấu hình gần với các thuộc tính Spring Boot khác.
- Không cần viết logic Java để tạo group.

Tên thuộc tính và các bộ lọc được hỗ trợ có thể khác theo phiên bản Springdoc. Đối chiếu cấu hình của đúng phiên bản dependency trước khi dùng thêm thuộc tính ngoài các ví dụ cơ bản.

## 7. Khai báo nhóm bằng application.properties

Cùng cấu hình có thể viết bằng application.properties:

~~~properties
springdoc.group-configs[0].group=public
springdoc.group-configs[0].paths-to-match[0]=/api/public/**

springdoc.group-configs[1].group=admin
springdoc.group-configs[1].packages-to-scan[0]=com.example.shop.api.admin
springdoc.group-configs[1].paths-to-match[0]=/api/admin/**

springdoc.group-configs[2].group=partner
springdoc.group-configs[2].paths-to-match[0]=/api/partner/**
springdoc.group-configs[2].paths-to-exclude[0]=/api/partner/internal/**
~~~

Chỉ số trong group-configs xác định phần tử của danh sách; chỉ số ở paths-to-match hoặc packages-to-scan xác định phần tử của danh sách pattern.

Khi cấu hình nhiều group, cần bảo đảm chỉ số không bị trùng hoặc bỏ sót ngoài ý muốn. Nếu dùng YAML, cấu trúc danh sách thường dễ đọc hơn; nếu dự án chuẩn hóa cấu hình bằng properties, có thể giữ cùng quy ước chỉ số.

Không nên đồng thời khai báo cùng một group ở cả GroupedOpenApi bean và group-configs nếu không có chủ đích rõ ràng. Hai nguồn cấu hình có thể tạo nhóm trùng hoặc làm người bảo trì khó xác định cấu hình nào đang có hiệu lực. Chọn một nguồn quản lý chính cho mỗi group.

## 8. Kết hợp nhiều điều kiện lọc

Một group có thể cần vừa giới hạn package vừa giới hạn path:

~~~java
@Bean
public GroupedOpenApi customerApi() {
    return GroupedOpenApi.builder()
        .group("customers")
        .packagesToScan("com.example.shop.api.customer")
        .pathsToMatch("/api/customers/**")
        .pathsToExclude("/api/customers/internal/**")
        .build();
}
~~~

Cách kết hợp này hữu ích khi package có nhiều controller hoặc path prefix được chia sẻ bởi nhiều module. Nó giúp nhóm tài liệu phản ánh cả tổ chức mã nguồn và hợp đồng URL.

Cần xác minh semantics của các filter trong phiên bản Springdoc đang dùng. Trong thực tế, một operation phải vượt qua các điều kiện lọc áp dụng để xuất hiện. Nếu nhóm rỗng hoặc thiếu endpoint, hãy kiểm tra riêng package, path và exclude pattern thay vì mở rộng tất cả filter cùng lúc.

Có thể lập bảng kỳ vọng trước khi cấu hình:

| Group | Package dự kiến | Path dự kiến | Path loại trừ |
|---|---|---|---|
| public | api.public | /api/public/** | /api/public/internal/** |
| admin | api.admin | /api/admin/** | Không có |
| partner | api.partner | /api/partner/** | /api/partner/internal/** |

Bảng này trở thành cơ sở để viết test kiểm tra mỗi group có đúng operation.

## 9. Tùy biến metadata riêng cho từng group

Mỗi group là một OpenAPI document độc lập. Có thể cần title, description hoặc metadata khác nhau cho public, admin và partner.

Với GroupedOpenApi builder, có thể thêm OpenApiCustomizer cho nhóm:

~~~java
@Bean
public GroupedOpenApi partnerApi() {
    return GroupedOpenApi.builder()
        .group("partner")
        .pathsToMatch("/api/partner/**")
        .addOpenApiCustomizer(openApi ->
            openApi.info(new Info()
                .title("Partner API")
                .description("API dành cho đối tác tích hợp")
                .version("1.0.0")
            )
        )
        .build();
}
~~~

OpenApiCustomizer cho phép chỉnh OpenAPI model trước khi document được trả về. Trong ví dụ, metadata Info của group partner được đặt riêng.

Các customizer có thể được dùng để bổ sung tag, server, extension hoặc metadata khác nếu cần. Tuy nhiên, nên giữ cấu hình dễ dự đoán: một customizer có phạm vi group rõ ràng và không vô tình ghi đè nội dung của nhóm khác.

Nếu ứng dụng có nhiều nhóm và dùng chung một số metadata, có thể tái sử dụng hàm tạo Info hoặc helper cấu hình. Hãy xác minh API customizer của phiên bản Springdoc đang dùng, vì package và cách đăng ký có thể khác giữa các major version.

## 10. Endpoint tài liệu của từng group

Khi một group tên public được khai báo, Springdoc cung cấp tài liệu riêng cho group đó. Với endpoint mặc định:

| Tài liệu | URL thường dùng |
|---|---|
| OpenAPI JSON mặc định | /v3/api-docs |
| OpenAPI YAML mặc định | /v3/api-docs.yaml |
| OpenAPI JSON của group public | /v3/api-docs/public |
| OpenAPI YAML của group public | /v3/api-docs/public.yaml |
| OpenAPI JSON của group admin | /v3/api-docs/admin |
| OpenAPI YAML của group admin | /v3/api-docs/admin.yaml |

Các URL trên giả định không thay đổi springdoc.api-docs.path và không có context path bổ sung. Nếu ứng dụng cấu hình endpoint tài liệu riêng, đường dẫn group sẽ dựa trên cấu hình đó.

Ví dụ tải tài liệu public:

~~~http
GET /v3/api-docs/public
~~~

Tải tài liệu YAML của admin:

~~~http
GET /v3/api-docs/admin.yaml
~~~

Hãy mở từng URL và kiểm tra paths bên trong. Chỉ thấy HTTP 200 không chứng minh group chứa đúng endpoint; tài liệu có thể hợp lệ nhưng rỗng hoặc thiếu operation do filter sai.

## 11. Hiển thị các group trong Swagger UI

Swagger UI có thể hiển thị danh sách các tài liệu nhóm để người dùng chọn. Springdoc cung cấp cấu hình Swagger UI và endpoint swagger-config để giao diện biết những tài liệu nào có sẵn.

Theo cấu hình mặc định, UI thường được mở tại:

~~~text
/swagger-ui.html
~~~

hoặc đường dẫn UI đã được tùy chỉnh trong springdoc.swagger-ui.path.

Khi có nhiều GroupedOpenApi, kiểm tra:

- Swagger UI có hiển thị tên từng group hay không.
- Chọn group có tải đúng URL /v3/api-docs/{group} không.
- Operation trong giao diện khớp với JSON/YAML của group.
- Server URL và security scheme đúng cho tài liệu đang xem.
- Không có group trùng tên hoặc tài liệu cũ bị cache.

Có thể truy cập endpoint cấu hình Swagger UI, thường là /v3/api-docs/swagger-config, để kiểm tra danh sách URL mà giao diện sử dụng. Nếu UI không hiện group, kiểm tra endpoint swagger-config và các thuộc tính springdoc.swagger-ui liên quan.

Swagger UI chỉ là giao diện đọc và thử API. Nó không quyết định operation thuộc group nào; việc chọn operation được thực hiện khi Springdoc tạo từng document.

## 12. Phân biệt group tài liệu với API version

Group và version giải quyết hai vấn đề khác nhau:

- **Group** chia tài liệu theo phạm vi, đối tượng hoặc miền nghiệp vụ.
- **API version** biểu thị phiên bản hợp đồng, thường được thể hiện trong path, header hoặc media type theo chính sách của ứng dụng.

Ví dụ một ứng dụng có thể có:

| Group | Paths | Mục đích |
|---|---|---|
| public-v1 | /api/v1/public/** | API công khai phiên bản 1 |
| public-v2 | /api/v2/public/** | API công khai phiên bản 2 |
| admin | /api/admin/** | API quản trị |
| partner | /api/partner/** | API tích hợp đối tác |

Tên group có thể chứa dấu hiệu phiên bản để người đọc dễ nhận biết, nhưng việc đặt tên group không tự tạo route versioning hoặc thay đổi hành vi controller.

Nếu API dùng version trong URL, controller mapping phải thực sự có path tương ứng. Nếu dùng header hoặc media type versioning, cần bảo đảm cơ chế định tuyến và tài liệu OpenAPI phản ánh chính xác cách client gửi request.

## 13. Group không phải ranh giới bảo mật

Một lỗi thiết kế nghiêm trọng là cho rằng endpoint không xuất hiện trong group public thì endpoint đó đã được bảo vệ. Group chỉ lọc nội dung tài liệu OpenAPI; nó không chặn request HTTP.

Ví dụ, loại /api/admin/** khỏi group public không ngăn client gọi endpoint admin. Quyền truy cập phải được thực thi bằng Spring Security, authorization rule, method security hoặc cơ chế bảo vệ ở gateway.

Cũng cần bảo vệ chính endpoint tài liệu nếu OpenAPI document chứa thông tin nội bộ. Có thể cấu hình Spring Security để giới hạn quyền truy cập /v3/api-docs/** và Swagger UI trong môi trường cần thiết. Cấu hình bảo mật phải được kiểm tra riêng cho cả tài liệu mặc định và tài liệu theo group.

Không dùng paths-to-exclude để thay thế authorization. Một endpoint bị ẩn khỏi Swagger UI vẫn có thể được gọi nếu ứng dụng cho phép.

## 14. Các lỗi thường gặp khi cấu hình group

| Hiện tượng | Nguyên nhân cần kiểm tra |
|---|---|
| Group không xuất hiện | Bean không được Spring scan hoặc group-configs sai cấu trúc |
| Group xuất hiện nhưng không có operation | paths-to-match hoặc packages-to-scan không khớp |
| Endpoint bị thiếu | paths-to-exclude hoặc packages-to-exclude loại nhầm |
| Endpoint xuất hiện ở nhiều group | Filter giữa các group chồng lấn |
| Hai tài liệu dùng cùng group name | Tên group bị trùng giữa bean và cấu hình |
| Swagger UI không có danh sách group | swagger-config không trả URL group hoặc UI đang dùng cấu hình khác |
| URL tài liệu group trả 404 | Sai group name, sai api-docs path hoặc context path |
| JSON đúng nhưng YAML không truy cập được | Đường dẫn suffix hoặc cấu hình xuất YAML không khớp phiên bản |
| Metadata Info của group không đúng | Customizer không áp dụng hoặc customizer khác ghi đè |
| API nội bộ xuất hiện trong tài liệu public | Filter quá rộng hoặc controller dùng chung package/path |
| Ẩn group nhưng endpoint vẫn gọi được | Group chỉ tác động tài liệu, chưa có security rule |

Khi xử lý, hãy kiểm tra theo thứ tự: bean/configuration có được nạp không, group name, package filter, path filter, endpoint JSON của group, rồi Swagger UI. Cách này giúp xác định lỗi nằm ở đăng ký group, chọn operation hay hiển thị giao diện.

## 15. Kiểm thử nội dung của từng group

Không nên chỉ kiểm tra rằng URL tài liệu trả 200. Cần xác minh tập operation đúng với phạm vi đã định.

Một cách đơn giản là tải OpenAPI JSON và kiểm tra các path quan trọng:

~~~java
mockMvc.perform(get("/v3/api-docs/public"))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$.paths['/api/public/products']").exists())
    .andExpect(jsonPath("$.paths['/api/admin/users']").doesNotExist());
~~~

Test trên minh họa việc kiểm tra một path phải có và một path không được xuất hiện. Tên path cần thay bằng mapping thực tế của ứng dụng.

Với mỗi group, nên có danh sách kỳ vọng:

- Các path bắt buộc phải xuất hiện.
- Các path không được xuất hiện.
- Các operation HTTP cần có.
- Các schema và security scheme quan trọng.
- Title, version và server URL của document.

Nếu dùng package scan, test giúp phát hiện refactor package khiến group rỗng. Nếu dùng path pattern, test giúp phát hiện endpoint mới vô tình lọt vào tài liệu public.

Có thể so sánh OpenAPI document của từng group trong CI để nhận diện thay đổi hợp đồng trước khi phát hành.

## 16. Chọn bean hay group-configs?

Hai cách cấu hình phục vụ cùng mục tiêu nhưng phù hợp với nhu cầu khác nhau:

| Tiêu chí | GroupedOpenApi bean | springdoc.group-configs |
|---|---|---|
| Khai báo | Java configuration | application.yml/properties |
| Bộ lọc package/path | Có | Có, tùy thuộc thuộc tính phiên bản |
| Logic tạo nhóm động | Linh hoạt hơn | Không phù hợp với logic động |
| OpenApiCustomizer riêng | Có thể gắn trực tiếp qua builder | Cần cấu hình Java bổ sung nếu cần logic tùy biến |
| Quản lý theo profile | Có thể dùng Spring bean/profile | Thuận tiện với cấu hình Spring Boot |
| Phù hợp | Nhóm cần customizer hoặc điều kiện bằng code | Nhóm tĩnh, cấu hình đơn giản |

Nếu chỉ cần chia theo path hoặc package, group-configs thường dễ đọc và dễ quản lý. Nếu cần customizer, method filter hoặc logic tạo nhóm bằng code, GroupedOpenApi bean linh hoạt hơn.

Không cần dùng đồng thời hai cách cho cùng một nhóm. Nếu một dự án dùng cả hai, hãy phân chia ownership rõ: ví dụ group-configs cho các nhóm tĩnh, bean cho một nhóm đặc biệt có customizer. Sau đó kiểm tra không có group name trùng lặp.

## 17. Quy trình triển khai nhóm tài liệu

Một quy trình thực tế:

1. Xác định đối tượng đọc tài liệu: public, admin, partner hay internal.
2. Chọn ranh giới group theo path hoặc package.
3. Đặt tên group duy nhất, ổn định và dễ hiểu.
4. Chọn GroupedOpenApi bean hoặc springdoc.group-configs.
5. Khai báo include/exclude rõ ràng.
6. Thêm OpenApiCustomizer riêng nếu cần metadata khác nhau.
7. Khởi động ứng dụng và tải từng endpoint /v3/api-docs/{group}.
8. Kiểm tra Swagger UI và swagger-config.
9. Viết test xác nhận path phải có và path không được có.
10. Kiểm tra security của endpoint tài liệu và endpoint nghiệp vụ.
11. Đưa kiểm tra OpenAPI group vào CI để phát hiện thay đổi ngoài ý muốn.

Khi thêm endpoint mới, cần xác định nó thuộc group nào. Nếu không có quy tắc rõ ràng, endpoint có thể bị thiếu trong tài liệu hoặc xuất hiện trong group không phù hợp.

## 18. Nguyên tắc duy trì document groups

Khi dùng Springdoc để tạo nhiều tài liệu OpenAPI, hãy giữ các nguyên tắc:

1. Dùng group name duy nhất cho mỗi tài liệu.
2. Chọn filter path/package phản ánh đúng ranh giới API.
3. Kết hợp include và exclude một cách có chủ đích.
4. Chọn bean khi cần Java logic hoặc customizer; chọn group-configs cho cấu hình tĩnh.
5. Không khai báo cùng group ở nhiều nguồn cấu hình nếu không có quy ước rõ.
6. Kiểm tra endpoint JSON/YAML riêng của từng group.
7. Kiểm tra Swagger UI và swagger-config.
8. Không xem group là cơ chế bảo mật hoặc API versioning.
9. Kiểm thử path phải có và path không được có.
10. Duy trì tài liệu và security rule cùng thay đổi khi mở rộng API.

GroupedOpenApi bean và springdoc.group-configs giúp tạo các OpenAPI document riêng từ một ứng dụng Spring Boot. Khi ranh giới nhóm, tên group và bộ lọc được thiết kế rõ ràng, mỗi đối tượng tích hợp có thể đọc đúng phần API liên quan. Kiểm tra JSON/YAML của từng group và bảo vệ endpoint tài liệu giúp việc phân phối hợp đồng API dễ kiểm soát hơn.

