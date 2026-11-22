# `GroupedOpenApi` và định danh nhóm duy nhất

Một ứng dụng Spring Boot có thể cung cấp nhiều nhóm API với mục đích khác nhau. Ví dụ, nhóm `stores` dành cho nghiệp vụ cửa hàng, nhóm `users` dành cho người dùng và nhóm `admin` dành cho quản trị. Mỗi nhóm cần một tài liệu OpenAPI riêng để người đọc chỉ thấy những operation liên quan đến phạm vi của họ.

`springdoc-openapi` hỗ trợ việc này bằng `GroupedOpenApi`. Mỗi bean `GroupedOpenApi` định nghĩa một nhóm tài liệu thông qua một định danh nhóm và các điều kiện lọc endpoint. Springdoc tạo một OpenAPI document cho từng nhóm, thường truy cập được qua `/v3/api-docs/{group}`. Định danh nhóm phải duy nhất trong ứng dụng vì nó được dùng để phân biệt tài liệu và tạo đường dẫn truy cập.

## 1. Nhóm tài liệu giải quyết vấn đề gì?

Khi ứng dụng có nhiều controller, một tài liệu chứa toàn bộ endpoint có thể trở nên dài và khó sử dụng. Nhóm tài liệu giúp chia đặc tả theo domain, phiên bản, đối tượng sử dụng hoặc phạm vi triển khai.

Ví dụ một hệ thống thương mại điện tử có các controller:

| Phạm vi | Package ví dụ | Path ví dụ | Nhóm tài liệu |
| --- | --- | --- | --- |
| Cửa hàng | `com.example.api.store` | `/api/stores/**` | `stores` |
| Người dùng | `com.example.api.user` | `/api/users/**` | `users` |
| Quản trị | `com.example.api.admin` | `/api/admin/**` | `admin` |

Mỗi nhóm có thể được tải riêng để tạo client SDK, review hợp đồng, xuất tài liệu hoặc cung cấp cho một đội phát triển. Các controller vẫn chạy trong cùng ứng dụng Spring Boot; việc chia nhóm chỉ tổ chức tài liệu được sinh ra.

Một nhóm tài liệu không phải một ứng dụng riêng, không tạo thêm route runtime và không tự áp dụng quyền truy cập. Endpoint vẫn được Spring MVC đăng ký theo mapping của controller. Spring Security hoặc cơ chế bảo mật khác tiếp tục quyết định ai được gọi endpoint.

## 2. `GroupedOpenApi` là gì?

`GroupedOpenApi` là cấu hình của springdoc để tạo một OpenAPI document từ một tập endpoint được chọn. Thông thường, ta khai báo mỗi nhóm bằng một bean trong class `@Configuration`:

```java
@Configuration
class OpenApiGroupConfiguration {

    @Bean
    GroupedOpenApi storesApi() {
        return GroupedOpenApi.builder()
            .group("stores")
            .pathsToMatch("/api/stores/**")
            .build();
    }

    @Bean
    GroupedOpenApi usersApi() {
        return GroupedOpenApi.builder()
            .group("users")
            .pathsToMatch("/api/users/**")
            .build();
    }

    @Bean
    GroupedOpenApi adminApi() {
        return GroupedOpenApi.builder()
            .group("admin")
            .pathsToMatch("/api/admin/**")
            .build();
    }
}
```

Trong ví dụ:

- `GroupedOpenApi.builder()` tạo builder cho một nhóm tài liệu.
- `group("stores")` đặt định danh của nhóm.
- `pathsToMatch(...)` chọn các API path thuộc nhóm.
- `build()` hoàn tất cấu hình để Spring đăng ký bean.

Springdoc phát hiện các bean `GroupedOpenApi` trong application context và tạo tài liệu tương ứng. Không cần tạo một controller mới cho mỗi nhóm.

## 3. Định danh nhóm phải duy nhất

Định danh truyền vào `.group("...")` là khóa nhận diện của tài liệu. Mỗi nhóm trong cùng ứng dụng cần một giá trị riêng:

```java
@Bean
GroupedOpenApi publicApi() {
    return GroupedOpenApi.builder()
        .group("public-v1")
        .pathsToMatch("/api/v1/public/**")
        .build();
}

@Bean
GroupedOpenApi adminApi() {
    return GroupedOpenApi.builder()
        .group("admin-v1")
        .pathsToMatch("/api/v1/admin/**")
        .build();
}
```

Hai nhóm trên có định danh khác nhau nên có endpoint tài liệu riêng. Nếu hai bean cùng khai báo `group("public")`, chúng đang tranh cùng một định danh. Không nên dựa vào thứ tự khởi tạo bean hoặc cơ chế ghi đè để quyết định tài liệu cuối cùng; hãy sửa cấu hình để mỗi nhóm có một tên duy nhất.

Một số quy ước đặt tên hữu ích:

- Dùng chữ thường và dấu gạch ngang, ví dụ `store-v1`, `admin-v1`.
- Đặt tên ngắn, phản ánh domain hoặc phiên bản.
- Giữ tên ổn định vì client, pipeline và liên kết tài liệu có thể tham chiếu trực tiếp đến nó.
- Không dùng tên bean Java làm định danh thay cho `.group(...)`; hai giá trị này có mục đích khác nhau.
- Khi tạo nhóm mới, kiểm tra toàn bộ cấu hình `GroupedOpenApi` để tránh trùng tên.

Định danh nhóm cũng không phải `info.title` trong OpenAPI. `group` định tuyến đến document; `info.title` là tiêu đề mô tả API bên trong document. Có thể có nhóm `stores-v1` nhưng `info.title` là `Store Management API`.

## 4. Chọn endpoint theo URL path

`pathsToMatch` nhận một hoặc nhiều pattern để chọn API path đưa vào tài liệu:

```java
@Bean
GroupedOpenApi catalogApi() {
    return GroupedOpenApi.builder()
        .group("catalog")
        .pathsToMatch("/api/products/**", "/api/categories/**")
        .build();
}
```

Nhóm `catalog` bao gồm các operation có path khớp với một trong các pattern đã khai báo. Cách lọc theo path phù hợp khi cấu trúc URL đã phản ánh domain hoặc phiên bản API.

Có thể loại trừ một path con khỏi nhóm bằng `pathsToExclude`:

```java
@Bean
GroupedOpenApi publicCatalogApi() {
    return GroupedOpenApi.builder()
        .group("public-catalog")
        .pathsToMatch("/api/**")
        .pathsToExclude("/api/internal/**", "/api/admin/**")
        .build();
}
```

Trong ví dụ, nhóm lấy các path thuộc `/api/**` rồi loại các path nội bộ và quản trị. Dùng exclude khi nhiều endpoint cùng nằm trong một vùng URL nhưng một số endpoint không thuộc tài liệu cần công bố.

Pattern được đánh giá trên API path mà springdoc phát hiện. Nếu ứng dụng có context path, servlet path hoặc cấu hình reverse proxy, cần xác minh path xuất hiện trong `/v3/api-docs` và điều chỉnh pattern theo đúng path của operation trong đặc tả.

## 5. Chọn endpoint theo package controller

Nếu package Java đã chia theo domain, có thể dùng `packagesToScan`:

```java
@Bean
GroupedOpenApi userApi() {
    return GroupedOpenApi.builder()
        .group("users")
        .packagesToScan("com.example.api.user")
        .build();
}
```

Springdoc đưa vào nhóm các controller thuộc package được chỉ định. Có thể chỉ định nhiều package:

```java
@Bean
GroupedOpenApi accountApi() {
    return GroupedOpenApi.builder()
        .group("accounts")
        .packagesToScan(
            "com.example.api.account",
            "com.example.api.profile"
        )
        .build();
}
```

Để loại một package khỏi nhóm, dùng `packagesToExclude`:

```java
@Bean
GroupedOpenApi externalApi() {
    return GroupedOpenApi.builder()
        .group("external")
        .packagesToScan("com.example.api")
        .packagesToExclude("com.example.api.internal")
        .build();
}
```

Lọc theo package phù hợp khi cấu trúc mã nguồn được tổ chức rõ theo domain. Lọc theo path phù hợp khi quy ước URL là ranh giới chính. Có thể kết hợp hai loại điều kiện nếu cần giới hạn cả package controller lẫn path operation.

## 6. Kết hợp package và path trong cùng nhóm

Một nhóm có thể sử dụng cả `packagesToScan` và `pathsToMatch`:

```java
@Bean
GroupedOpenApi storeV1Api() {
    return GroupedOpenApi.builder()
        .group("store-v1")
        .packagesToScan("com.example.api.store")
        .pathsToMatch("/api/v1/**")
        .pathsToExclude("/api/v1/store/internal/**")
        .build();
}
```

Cấu hình này giới hạn tài liệu vào controller thuộc package store và các operation có path phù hợp, đồng thời loại path nội bộ. Khi kết hợp nhiều bộ lọc, hãy nghĩ đến chúng như các điều kiện thu hẹp phạm vi. Nếu một endpoint không xuất hiện, kiểm tra cả package khai báo của controller lẫn path thực tế của mapping.

Các builder filter khác có thể được dùng để lọc theo media type hoặc header khi phù hợp với phiên bản springdoc đang sử dụng, chẳng hạn `producesToMatch`, `consumesToMatch` và `headersToMatch`. Chỉ thêm filter khi có yêu cầu rõ ràng; nhiều điều kiện lọc đồng thời khiến việc chẩn đoán endpoint bị loại khỏi nhóm khó hơn.

## 7. Một endpoint có thể xuất hiện trong nhiều nhóm

Các nhóm là những tài liệu độc lập được tạo từ cùng ứng dụng. Nếu điều kiện lọc của nhiều nhóm cùng khớp một operation, operation đó có thể xuất hiện trong nhiều document.

Ví dụ endpoint tra cứu cửa hàng có thể thuộc nhóm `stores` và nhóm `public-v1`:

```java
@Bean
GroupedOpenApi storesApi() {
    return GroupedOpenApi.builder()
        .group("stores")
        .pathsToMatch("/api/stores/**")
        .build();
}

@Bean
GroupedOpenApi publicV1Api() {
    return GroupedOpenApi.builder()
        .group("public-v1")
        .pathsToMatch("/api/v1/public/**", "/api/stores/**")
        .build();
}
```

Điều này không đăng ký endpoint hai lần và cũng không tạo hai phiên bản controller. Nó chỉ đưa cùng operation vào hai tài liệu để phục vụ hai nhóm người đọc khác nhau.

Nếu không muốn một endpoint xuất hiện ở nhiều tài liệu, hãy thiết kế path/package filter không chồng lấn hoặc dùng exclude. Nếu việc xuất hiện ở nhiều nhóm là chủ ý, cần giữ schema và mô tả nhất quán giữa các nhóm.

## 8. Định nghĩa nhóm bằng `application.yml`

Ngoài bean Java, springdoc cho phép khai báo nhóm động trong cấu hình Spring Boot bằng `springdoc.group-configs`. Khi dùng cách này, không cần tạo thêm bean `GroupedOpenApi` cho chính các nhóm đã khai báo trong danh sách:

```yaml
springdoc:
  group-configs:
    - group: stores
      paths-to-match:
        - /api/stores/**
    - group: users
      packages-to-scan:
        - com.example.api.user
    - group: admin
      paths-to-match:
        - /api/admin/**
      packages-to-scan:
        - com.example.api.admin
```

Mỗi phần tử có một `group` duy nhất và các điều kiện lọc tương ứng. Cấu hình YAML phù hợp khi nhóm chỉ cần khai báo tĩnh theo môi trường hoặc được quản lý tập trung trong file cấu hình.

Không nên khai báo cùng một nhóm vừa bằng `springdoc.group-configs` vừa bằng bean `GroupedOpenApi` nếu không có chủ đích rõ ràng. Hãy chọn một cách quản lý cho mỗi nhóm để tránh cấu hình trùng lặp hoặc xung đột định danh.

## 9. Đường dẫn tài liệu của từng nhóm

Với group id là `stores`, endpoint tài liệu mặc định thường là:

```text
/v3/api-docs/stores
```

Với group id là `users`:

```text
/v3/api-docs/users
```

Đặc tả YAML có thể được lấy qua endpoint có hậu tố `.yaml`, ví dụ:

```text
/v3/api-docs/stores.yaml
/v3/api-docs/users.yaml
```

Nếu ứng dụng cấu hình context path, các URL này được đặt dưới context path đó. Nếu thay đổi `springdoc.api-docs.path`, base path của endpoint tài liệu cũng thay đổi; group id vẫn được thêm vào để xác định document tương ứng.

Swagger UI có thể hiển thị các nhóm được phát hiện trong danh sách chọn tài liệu. Người dùng chọn `stores`, `users` hoặc `admin` để mở đặc tả tương ứng. Có thể kiểm tra trực tiếp JSON/YAML độc lập với giao diện bằng cách gọi URL của nhóm.

## 10. Phân biệt group id với metadata OpenAPI

Mỗi nhóm có thể chia sẻ metadata chung hoặc có metadata riêng. Các trường `info.title`, `info.version`, `info.description` mô tả nội dung API trong document; chúng không thay thế group id.

Ví dụ hai document có thể dùng tên nhóm và metadata như sau:

| Group id | `info.title` | `info.version` |
| --- | --- | --- |
| `store-v1` | `Store API` | `1.0` |
| `admin-v1` | `Admin API` | `1.0` |

Một `OpenAPI` bean có thể cung cấp metadata hoặc component dùng chung cho các nhóm. Nếu cần tùy chỉnh metadata riêng cho một nhóm, có thể gắn customizer vào cấu hình `GroupedOpenApi` tương ứng. Hãy xác định rõ thành phần nào dùng chung toàn ứng dụng và thành phần nào chỉ thuộc một document.

## 11. Nhóm tài liệu không phải ranh giới bảo mật

Một hiểu nhầm nguy hiểm là cho rằng endpoint không xuất hiện trong nhóm public thì người dùng public không thể gọi endpoint đó. Group filter chỉ quyết định operation nào được đưa vào OpenAPI document.

Ví dụ:

- `pathsToExclude("/api/admin/**")` chỉ loại path quản trị khỏi tài liệu nhóm public.
- Nó không chặn request HTTP đến `/api/admin/**`.
- Nó không yêu cầu token, không kiểm tra role và không tạo rule trong Spring Security.

Nếu endpoint quản trị cần hạn chế truy cập, cấu hình xác thực và phân quyền ở runtime. Có thể bảo vệ riêng các endpoint tài liệu như `/v3/api-docs/**` và Swagger UI bằng Spring Security nếu chính sách triển khai yêu cầu. Việc công bố hay ẩn tài liệu phải được xem là quyết định phân phối thông tin; bảo vệ API vẫn là trách nhiệm của lớp bảo mật.

## 12. Kiểm tra các nhóm sau khi cấu hình

Sau khi thêm hoặc thay đổi `GroupedOpenApi`, nên xác minh từng nhóm độc lập:

1. Khởi động ứng dụng và kiểm tra log để bảo đảm các bean cấu hình nhóm được tạo.
2. Gọi `/v3/api-docs/{group}` cho từng group id và xác nhận trả về OpenAPI document.
3. Tìm `paths` trong document và xác nhận chỉ có operation thuộc phạm vi dự kiến.
4. Kiểm tra `components.schemas`, response, security scheme và các `$ref` cần thiết vẫn có mặt.
5. Thử endpoint nằm ngoài path/package filter để xác nhận nó không xuất hiện trong nhóm.
6. Kiểm tra một endpoint có chủ ý xuất hiện ở nhiều nhóm để xác nhận hành vi overlap.
7. Mở Swagger UI và xác nhận danh sách nhóm có tên dễ hiểu, mỗi lựa chọn mở đúng document.
8. Gọi endpoint runtime trực tiếp để xác nhận group filter không bị nhầm với rule truy cập.

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| `/v3/api-docs/{group}` trả lỗi không tìm thấy | Group id không tồn tại hoặc bean/config chưa được nạp | Kiểm tra `.group(...)`, `springdoc.group-configs` và application context. |
| Hai nhóm dùng chung tài liệu hoặc có kết quả bất thường | Định danh nhóm bị trùng | Đặt group id duy nhất cho từng `GroupedOpenApi`. |
| Nhóm không có operation | `pathsToMatch` hoặc `packagesToScan` không khớp controller | Kiểm tra path mapping và package thực tế; nới filter từng bước. |
| Operation nội bộ vẫn xuất hiện trong nhóm public | Thiếu `pathsToExclude` hoặc `packagesToExclude` | Bổ sung điều kiện loại trừ và kiểm tra document sau khi sinh. |
| Operation xuất hiện ở hai nhóm | Bộ lọc của hai nhóm giao nhau | Xác định đây là chủ ý hay điều kiện lọc bị chồng lấn. |
| Swagger UI không có lựa chọn nhóm | Nhóm chưa được đăng ký, UI bị tắt hoặc cấu hình URL tùy chỉnh chưa đúng | Gọi trực tiếp group docs và kiểm tra cấu hình Swagger UI. |
| Endpoint bị ẩn khỏi tài liệu nhưng vẫn gọi được | Group filter chỉ tác động đến tài liệu | Cấu hình Spring Security hoặc cơ chế bảo vệ runtime. |
| Metadata riêng của nhóm bị giống nhau | Chỉ khai báo `OpenAPI` bean toàn cục | Dùng customizer riêng cho nhóm cần metadata khác. |

## 13. Nguyên tắc áp dụng

- Tạo một `GroupedOpenApi` cho mỗi tài liệu cần công bố riêng.
- Đặt `.group(...)` bằng định danh duy nhất, ổn định và dễ đọc.
- Chọn `pathsToMatch` khi ranh giới nằm ở URL; chọn `packagesToScan` khi ranh giới nằm ở cấu trúc controller.
- Dùng `pathsToExclude` và `packagesToExclude` để loại endpoint ngoài phạm vi.
- Chỉ kết hợp nhiều filter khi hiểu rõ phạm vi giao nhau của chúng.
- Có thể khai báo nhóm bằng bean Java hoặc `springdoc.group-configs`; tránh quản lý trùng một nhóm bằng cả hai cách.
- Dùng URL `/v3/api-docs/{group}` để kiểm tra từng document và Swagger UI để điều hướng giữa các nhóm.
- Không dùng việc ẩn operation khỏi tài liệu làm cơ chế bảo mật endpoint.
- Kiểm tra group id, path, package và schema trong từng tài liệu sau mỗi thay đổi.

`GroupedOpenApi` giúp một ứng dụng Spring Boot phát hành nhiều OpenAPI document theo những phạm vi khác nhau. Group id duy nhất tạo đường dẫn và nhận diện ổn định cho từng tài liệu; path/package filters quyết định operation nào xuất hiện trong nhóm. Khi thiết kế nhóm rõ ràng và kiểm tra từng document, đội phát triển có thể phân phối tài liệu gọn hơn mà vẫn giữ một ứng dụng và một hệ thống endpoint nhất quán.

## Tài liệu tham khảo

- [Springdoc OpenAPI FAQ – Multiple OpenAPI Definitions and GroupedOpenApi](https://springdoc.org/faq.html)
- [Springdoc OpenAPI v2 FAQ – Groups for Spring Boot 3](https://springdoc.org/v2/faq.html)
- [Springdoc OpenAPI – tài liệu chính thức](https://springdoc.org/)
