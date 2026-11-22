# Mục tiêu chia hợp đồng theo miền nghiệp vụ hoặc đối tượng sử dụng

Khi một ứng dụng Spring Boot có nhiều controller, nhiều miền nghiệp vụ hoặc nhiều nhóm người tích hợp, một tài liệu OpenAPI duy nhất có thể trở nên quá lớn và khó tìm. Người dùng chỉ cần API đơn hàng có thể phải cuộn qua hàng trăm operation về thanh toán, quản trị và vận hành. Một số endpoint còn dành riêng cho đối tác hoặc hệ thống nội bộ, không phù hợp để xuất hiện trong tài liệu công khai.

springdoc-openapi hỗ trợ chia một ứng dụng thành nhiều tài liệu OpenAPI bằng GroupedOpenApi. Mỗi nhóm là một hợp đồng được sinh từ tập controller hoặc path đã chọn, có thể có thông tin mô tả và tùy biến riêng. Việc chia nhóm giúp tài liệu đúng đối tượng, dễ điều hướng và dễ quản lý vòng đời hơn.

## 1. Vì sao cần chia tài liệu OpenAPI?

Chia nhóm hữu ích khi có một hoặc nhiều nhu cầu sau:

- Tách các miền nghiệp vụ như catalog, orders, billing và identity để người đọc chỉ thấy operation liên quan.
- Cung cấp hợp đồng riêng cho từng đối tượng tích hợp như public client, đối tác và đội vận hành nội bộ.
- Phân biệt API theo phiên bản hoặc giai đoạn phát hành khi hợp đồng thực sự khác nhau.
- Giảm độ phức tạp của tài liệu, giúp tìm endpoint và kiểm tra thay đổi dễ hơn.
- Áp dụng metadata, mô tả, tag hoặc quy trình phát hành riêng cho từng hợp đồng.
- Kiểm soát tài liệu nào được công bố trên developer portal hoặc cung cấp cho một nhóm người dùng.

Ví dụ một hệ thống thương mại điện tử có thể có:

| Nhóm tài liệu | Đối tượng sử dụng | Nội dung |
| --- | --- | --- |
| public-api | Ứng dụng web/mobile và khách hàng tích hợp | Xem sản phẩm, tạo đơn, theo dõi đơn |
| partner-api | Đối tác vận chuyển hoặc bán hàng | Tra cứu đơn được phân quyền, cập nhật trạng thái giao nhận |
| admin-api | Nhân viên quản trị | Quản lý danh mục, hoàn tiền, cấu hình hệ thống |
| internal-api | Dịch vụ nội bộ | Đồng bộ dữ liệu và tác vụ vận hành |

Đây là cách tổ chức hợp đồng tài liệu. Quyền truy cập thực tế của từng endpoint vẫn do Spring Security, gateway và chính sách ứng dụng quyết định.

## 2. Nhóm tài liệu khác gì tag và package?

Ba cơ chế này có vai trò khác nhau:

| Cơ chế | Phạm vi | Mục đích |
| --- | --- | --- |
| GroupedOpenApi | Toàn bộ tài liệu OpenAPI được sinh | Chọn tập operation tạo thành một hợp đồng riêng |
| Tag | Bên trong một tài liệu | Gom operation theo chủ đề để dễ điều hướng |
| Java package | Cấu trúc mã nguồn | Tổ chức controller và thành phần Java |

Ví dụ, nhóm public-api có thể chứa các tag Products, Orders và Accounts. Tag Products tiếp tục gom các operation xem, tìm kiếm và lọc sản phẩm. Một package có thể chứa nhiều controller; một group có thể lấy controller từ nhiều package nếu chúng cùng thuộc một hợp đồng.

Không cần tạo group chỉ vì có một controller hoặc một tag mới. Group nên đại diện cho ranh giới hợp đồng có ý nghĩa với người tiêu thụ API.

## 3. Xác định ranh giới nhóm theo miền nghiệp vụ

Chia theo miền nghiệp vụ phù hợp khi các phần của hệ thống có chức năng và mô hình dữ liệu tương đối độc lập.

Ví dụ:

- Catalog: sản phẩm, danh mục, thuộc tính và tồn kho hiển thị.
- Orders: giỏ hàng, đơn hàng, trạng thái và lịch sử đặt hàng.
- Billing: thanh toán, hóa đơn và hoàn tiền.
- Identity: tài khoản, hồ sơ và quyền truy cập.

Một cách triển khai là tổ chức controller theo package:

~~~text
com.example.shop.api
  catalog
    ProductController.java
    CategoryController.java
  orders
    OrderController.java
    CartController.java
  billing
    PaymentController.java
    InvoiceController.java
~~~

Khi các package phản ánh đúng ranh giới nghiệp vụ, có thể tạo một group cho từng miền. Cách này giúp nhóm tài liệu ít phụ thuộc vào tên path, nhưng đòi hỏi package không bị trộn lẫn giữa các miền.

Nếu controller được tổ chức theo lớp kỹ thuật thay vì miền, chẳng hạn tất cả controller nằm trong một package, có thể dùng pathsToMatch và pathsToExclude để chọn operation theo URL. Trong thực tế có thể kết hợp lọc package và path để làm rõ ranh giới.

## 4. Xác định ranh giới theo đối tượng sử dụng

Một miền nghiệp vụ có thể phục vụ nhiều nhóm người dùng với các mức quyền và nhu cầu khác nhau. Khi đó, tách tài liệu theo audience có thể hữu ích hơn chia thuần theo package.

Ví dụ:

| Đối tượng | Nhu cầu tài liệu | Operation phù hợp |
| --- | --- | --- |
| Public client | Tích hợp các luồng cơ bản | Xem sản phẩm, tạo đơn, đọc trạng thái |
| Partner | Tích hợp luồng phối hợp với đối tác | Nhận đơn được giao, xác nhận giao hàng, gửi mã đối soát |
| Administrator | Quản trị dữ liệu và cấu hình | Tạo danh mục, khóa tài khoản, điều chỉnh trạng thái |
| Internal service | Giao tiếp giữa các dịch vụ | Đồng bộ, xử lý sự kiện, truy vấn nội bộ |

Không nên chỉ dựa vào tên vai trò để đưa endpoint vào group. Hãy xác định tập operation mà đối tượng đó được phép biết và cần sử dụng. Một endpoint có thể xuất hiện trong nhiều group nếu nhiều đối tượng cùng cần hợp đồng đó; điều này không cấp thêm quyền gọi endpoint.

## 5. Khai báo GroupedOpenApi bằng Java configuration

Với springdoc-openapi 2.x và 3.x, GroupedOpenApi nằm trong package org.springdoc.core.models. Có thể tạo bean cho từng nhóm:

~~~java
import org.springdoc.core.models.GroupedOpenApi;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class OpenApiGroupsConfig {

    @Bean
    GroupedOpenApi publicApi() {
        return GroupedOpenApi.builder()
            .group("public-api")
            .packagesToScan(
                "com.example.shop.api.catalog",
                "com.example.shop.api.orders"
            )
            .pathsToMatch("/api/public/**")
            .build();
    }

    @Bean
    GroupedOpenApi partnerApi() {
        return GroupedOpenApi.builder()
            .group("partner-api")
            .packagesToScan("com.example.shop.api.partner")
            .pathsToMatch("/api/partner/**")
            .build();
    }

    @Bean
    GroupedOpenApi adminApi() {
        return GroupedOpenApi.builder()
            .group("admin-api")
            .packagesToScan("com.example.shop.api.admin")
            .pathsToMatch("/api/admin/**")
            .build();
    }
}
~~~

Mỗi bean tạo một tài liệu riêng. Tên group là định danh được dùng trong URL lấy tài liệu, vì vậy nên chọn tên ổn định, dễ đọc, không chứa khoảng trắng hoặc ký tự cần URL encode.

Với springdoc 1.x, package của GroupedOpenApi khác với các dòng mới hơn. Dự án cũ thường dùng org.springdoc.core.GroupedOpenApi. Hãy dùng import tương ứng với phiên bản dependency đang cài, không sao chép import giữa các major version mà chưa kiểm tra.

## 6. Lọc bằng package và path

GroupedOpenApi hỗ trợ các bộ lọc phổ biến:

| Bộ lọc | Tác dụng |
| --- | --- |
| packagesToScan | Chỉ lấy controller thuộc các package được chỉ định |
| packagesToExclude | Loại controller thuộc các package chỉ định |
| pathsToMatch | Chỉ lấy các path phù hợp mẫu |
| pathsToExclude | Loại các path phù hợp mẫu |

Ví dụ chỉ công bố endpoint catalog công khai, đồng thời bỏ các endpoint thử nghiệm:

~~~java
@Bean
GroupedOpenApi catalogPublicApi() {
    return GroupedOpenApi.builder()
        .group("catalog-public")
        .packagesToScan("com.example.shop.api.catalog")
        .pathsToMatch("/api/catalog/**")
        .pathsToExclude(
            "/api/catalog/internal/**",
            "/api/catalog/debug/**"
        )
        .build();
}
~~~

Khi khai báo nhiều bộ lọc, hãy xem chúng như các điều kiện thu hẹp tập operation: controller phải thuộc phạm vi package được chọn và path phải phù hợp bộ lọc. Quy tắc khớp cuối cùng còn phụ thuộc cấu hình và phiên bản; luôn xác minh nội dung thực tế của tài liệu nhóm.

Path pattern nên dựa trên URL mapping mà Spring công bố, không dựa vào tên method Java. Nếu controller có context path hoặc prefix ở tầng triển khai, kiểm tra path trong OpenAPI để chọn đúng mẫu. Các bộ lọc tài liệu không đổi URL runtime của controller.

## 7. Tách tài liệu bằng nhiều GroupedOpenApi

Có thể tạo nhiều group theo miền:

~~~java
@Bean
GroupedOpenApi ordersApi() {
    return GroupedOpenApi.builder()
        .group("orders")
        .packagesToScan("com.example.shop.api.orders")
        .build();
}

@Bean
GroupedOpenApi billingApi() {
    return GroupedOpenApi.builder()
        .group("billing")
        .packagesToScan("com.example.shop.api.billing")
        .build();
}
~~~

Hoặc tạo nhóm theo audience:

~~~java
@Bean
GroupedOpenApi publicApi() {
    return GroupedOpenApi.builder()
        .group("public")
        .pathsToMatch("/api/catalog/**", "/api/orders/**")
        .pathsToExclude("/api/orders/{orderId}/internal/**")
        .build();
}

@Bean
GroupedOpenApi operationsApi() {
    return GroupedOpenApi.builder()
        .group("operations")
        .pathsToMatch("/api/**/admin/**", "/api/operations/**")
        .build();
}
~~~

Các ví dụ path chỉ minh họa quy tắc chọn operation. Trước khi dùng, hãy đối chiếu với mapping thật của controller và tránh để một mẫu rộng vô tình kéo endpoint nội bộ vào tài liệu công khai.

Một controller có thể xuất hiện trong nhiều group nếu thỏa bộ lọc của các group đó. Ngược lại, controller không thỏa bộ lọc nào vẫn có thể xuất hiện trong tài liệu mặc định nếu cấu hình ứng dụng tiếp tục cung cấp default OpenAPI document.

## 8. URL của tài liệu từng nhóm

Với đường dẫn mặc định, springdoc thường cung cấp:

| URL | Nội dung |
| --- | --- |
| /v3/api-docs | Tài liệu OpenAPI mặc định của ứng dụng |
| /v3/api-docs/public-api | Tài liệu của group public-api |
| /v3/api-docs/partner-api | Tài liệu của group partner-api |
| /v3/api-docs/admin-api | Tài liệu của group admin-api |
| /swagger-ui.html | Điểm vào Swagger UI |

Nếu đã thay springdoc.api-docs.path, URL của default document và các group sẽ thay đổi theo prefix đó. Hãy kiểm tra cấu hình ứng dụng thay vì mặc định luôn dùng /v3/api-docs.

Swagger UI có thể hiển thị danh sách các group được đăng ký để người dùng chọn tài liệu cần xem. Danh sách này được cung cấp qua cấu hình Swagger UI do springdoc sinh. Nếu không thấy group, kiểm tra bean GroupedOpenApi có được Spring khởi tạo, tên group có duy nhất và endpoint cấu hình Swagger UI có trả danh sách đúng hay không.

Có thể lấy từng tài liệu bằng curl:

~~~bash
curl -sS http://localhost:8080/v3/api-docs/public-api
curl -sS http://localhost:8080/v3/api-docs/partner-api
curl -sS http://localhost:8080/v3/api-docs/admin-api
~~~

Nếu ứng dụng có context path, reverse proxy hoặc API gateway, thêm prefix công khai tương ứng vào URL.

## 9. Tùy biến thông tin riêng cho từng group

Mỗi tài liệu nhóm có thể cần title, version hoặc description riêng. Có thể dùng OpenApiCustomizer gắn trực tiếp vào GroupedOpenApi:

~~~java
import io.swagger.v3.oas.models.info.Info;
import org.springdoc.core.models.GroupedOpenApi;
import org.springframework.context.annotation.Bean;

@Bean
GroupedOpenApi billingApi() {
    return GroupedOpenApi.builder()
        .group("billing")
        .packagesToScan("com.example.shop.api.billing")
        .addOpenApiCustomizer(openApi ->
            openApi.info(new Info()
                .title("Billing API")
                .version("v1")
                .description("Hợp đồng API dành cho nghiệp vụ thanh toán.")
            )
        )
        .build();
}
~~~

Customizer gắn trên builder giúp điều chỉnh tài liệu của group tương ứng. Đây là nơi phù hợp để thay metadata hoặc bổ sung thông tin chỉ áp dụng cho một hợp đồng.

Nếu cần một tùy biến áp dụng cho mọi tài liệu, có thể dùng cơ chế global customizer phù hợp với phiên bản springdoc. Cần phân biệt customizer toàn cục với customizer riêng từng group để tránh ghi đè metadata của nhóm khác.

## 10. Group không thay thế bảo mật endpoint

Đây là điểm cần đặc biệt lưu ý khi tạo public-api và internal-api. Việc một endpoint không xuất hiện trong tài liệu không có nghĩa endpoint đó đã bị vô hiệu hóa hoặc được bảo vệ.

Ví dụ:

- pathsToExclude chỉ loại operation khỏi tài liệu được sinh.
- packagesToScan chỉ giới hạn controller được đưa vào hợp đồng nhóm.
- Người dùng vẫn có thể gọi URL endpoint nếu ứng dụng và gateway cho phép.
- Tài liệu OpenAPI cũng có thể tiết lộ tên path, schema hoặc quy trình nội bộ nếu được công bố không đúng đối tượng.

Vì vậy, hãy kết hợp:

1. GroupedOpenApi để tạo đúng hợp đồng cho từng audience.
2. Spring Security để xác thực và phân quyền endpoint.
3. Gateway hoặc reverse proxy để kiểm soát truy cập mạng nếu cần.
4. Security scheme trong OpenAPI để mô tả cách client xác thực.
5. Quyền truy cập riêng cho endpoint tài liệu nếu hợp đồng không công khai.

Không dùng việc ẩn endpoint khỏi Swagger UI làm biện pháp bảo mật. Hãy kiểm thử request trực tiếp tới endpoint nội bộ bằng danh tính không có quyền để xác nhận server trả 401 hoặc 403 theo chính sách.

## 11. Chia nhóm theo phiên bản API

Có thể tạo group cho các phiên bản API nếu ứng dụng thực sự phục vụ nhiều hợp đồng khác nhau, ví dụ /api/v1/** và /api/v2/**:

~~~java
@Bean
GroupedOpenApi apiV1() {
    return GroupedOpenApi.builder()
        .group("api-v1")
        .pathsToMatch("/api/v1/**")
        .build();
}

@Bean
GroupedOpenApi apiV2() {
    return GroupedOpenApi.builder()
        .group("api-v2")
        .pathsToMatch("/api/v2/**")
        .build();
}
~~~

Tên group api-v1 và api-v2 chỉ định danh hai tài liệu. Nó không tự tạo versioning cho endpoint và không thay đổi route. Ứng dụng phải triển khai mapping/versioning thực tế, quản lý tương thích và có chính sách deprecation riêng.

Nếu API dùng header version hoặc media type version thay vì version trong path, có thể cần bộ lọc hoặc customizer phù hợp để tách hợp đồng. Hãy xác minh mỗi group chỉ chứa operation của phiên bản dự kiến và schema không bị trộn giữa các phiên bản.

## 12. Khi nào không nên chia group?

Không nên chia quá nhỏ nếu các nhóm chỉ khác nhau về cách sắp xếp hoặc tag. Quá nhiều tài liệu khiến người dùng khó biết nên mở tài liệu nào và làm tăng chi phí duy trì.

Giữ một tài liệu và dùng tag khi:

- API có cùng đối tượng người dùng và cùng chính sách truy cập.
- Các operation chỉ cần phân loại theo chủ đề.
- Không có khác biệt về hợp đồng, vòng đời hoặc quyền công bố.
- Người tích hợp thường xuyên cần nhìn toàn bộ API trong một luồng công việc.

Tạo group riêng khi có khác biệt thực sự về miền, audience, phiên bản, metadata, quyền công bố hoặc quy trình phát hành. Ranh giới tốt là ranh giới mà người tiêu thụ hiểu ngay vì sao có một tài liệu riêng.

## 13. Kiểm tra nội dung từng group

Sau khi cấu hình các bean, kiểm tra từng endpoint OpenAPI:

~~~bash
# Tài liệu nhóm public
curl -sS http://localhost:8080/v3/api-docs/public-api

# Tài liệu nhóm partner
curl -sS http://localhost:8080/v3/api-docs/partner-api

# Tài liệu nhóm admin
curl -sS http://localhost:8080/v3/api-docs/admin-api
~~~

Đối chiếu mỗi tài liệu:

1. Title, version và description có đúng đối tượng sử dụng không?
2. Paths có chứa đúng các operation dự kiến không?
3. Có endpoint nội bộ hoặc endpoint thử nghiệm xuất hiện nhầm không?
4. Các schema, parameter, request body và response có đầy đủ không?
5. Security scheme và security requirement có phù hợp với nhóm không?
6. Các $ref có trỏ tới component tồn tại trong chính tài liệu nhóm không?
7. Swagger UI có hiển thị các nhóm và mở đúng tài liệu không?
8. Endpoint runtime có thực sự được bảo vệ độc lập với việc ẩn/hiện tài liệu không?

Có thể viết integration test tải OpenAPI của từng group và kiểm tra tập path quan trọng. Điều này giúp phát hiện việc một controller mới vô tình lọt vào tài liệu public hoặc một endpoint bị loại khỏi tài liệu partner sau khi đổi package/path.

Ví dụ kiểm tra nội dung bằng jq:

~~~bash
curl -sS http://localhost:8080/v3/api-docs/public-api \
  | jq -r '.paths | keys[]'
~~~

Nếu không có jq, có thể tải JSON vào test và kiểm tra object paths bằng thư viện JSON của dự án.

## 14. Lỗi thường gặp

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- |
| Group không xuất hiện trong Swagger UI | Bean không được component scan hoặc tên group cấu hình sai | Kiểm tra @Configuration, bean và endpoint swagger-config |
| Group không có operation | packagesToScan hoặc pathsToMatch không khớp controller/path thực tế | Kiểm tra package và path trong default document |
| Endpoint nội bộ xuất hiện trong public-api | Mẫu path quá rộng hoặc package dùng chung | Thu hẹp bộ lọc và kiểm thử danh sách path |
| Một operation xuất hiện trong nhiều group | Bộ lọc các group giao nhau | Xác định việc trùng là chủ ý hay cần loại trừ |
| Đổi tên group làm URL cũ lỗi | Group name là một phần URL tài liệu | Quản lý tên group như một contract endpoint |
| Tài liệu bị 401/403 | Security matcher chặn endpoint docs | Cấu hình quyền truy cập tài liệu theo audience |
| Endpoint bị ẩn nhưng vẫn gọi được | Group chỉ lọc tài liệu, không khóa endpoint | Bảo vệ route bằng Spring Security/gateway |
| Group dùng sai title/version | Metadata mặc định hoặc customizer ghi đè | Tùy biến riêng và kiểm tra từng tài liệu sinh ra |

## 15. Quy trình thiết kế nhóm tài liệu

Khi chia một ứng dụng thành nhiều hợp đồng OpenAPI:

1. Liệt kê miền nghiệp vụ, đối tượng sử dụng và phiên bản API đang phục vụ.
2. Xác định ai cần đọc từng hợp đồng và operation nào thuộc phạm vi đó.
3. Chọn ranh giới dựa trên package, path hoặc kết hợp cả hai.
4. Đặt tên group ổn định, dễ hiểu và duy nhất.
5. Khai báo từng GroupedOpenApi bean, bộ lọc và metadata riêng nếu cần.
6. Kiểm tra URL tài liệu của từng group và danh sách operation được sinh.
7. Cấu hình Spring Security/gateway độc lập với bộ lọc tài liệu.
8. Thêm kiểm thử để bảo vệ ranh giới group khi controller hoặc path thay đổi.

Chia tài liệu theo miền nghiệp vụ hoặc audience giúp mỗi nhóm người tích hợp có một hợp đồng vừa đủ và dễ dùng. Khi ranh giới được xác định rõ, GroupedOpenApi giúp sinh các tài liệu riêng từ cùng một ứng dụng mà vẫn giữ một nguồn mã controller thống nhất.

## Tài liệu tham khảo

- [springdoc-openapi – Multiple OpenAPI Definitions / GroupedOpenApi](https://springdoc.org/)
- [springdoc-openapi – FAQ and Configuration Properties](https://springdoc.org/faq.html)
- [OpenAPI Specification – OpenAPI Object](https://spec.openapis.org/oas/latest.html#openapi-object)
- [Spring Boot Reference – Auto-configuration and component scanning](https://docs.spring.io/spring-boot/reference/using/auto-configuration.html)
- [Spring Security – Authorization](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html)
