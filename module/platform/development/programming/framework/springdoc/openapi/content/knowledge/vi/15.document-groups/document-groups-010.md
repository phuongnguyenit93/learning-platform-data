# Chồng lấn nhóm, operation bị thiếu và cách kiểm tra phạm vi

Khi một ứng dụng Spring Boot xuất bản nhiều tài liệu OpenAPI bằng springdoc-openapi, một endpoint có thể xuất hiện trong nhiều nhóm hoặc không xuất hiện trong nhóm nào. Đây thường là kết quả của các bộ lọc phạm vi, chẳng hạn **pathsToMatch**, **pathsToExclude**, **packagesToScan** và **packagesToExclude**. Hiểu cách các bộ lọc kết hợp giúp tránh hai lỗi phổ biến: nghĩ rằng endpoint bị mất khỏi ứng dụng trong khi nó chỉ bị loại khỏi một tài liệu, hoặc vô tình đưa endpoint nội bộ vào tài liệu dành cho client bên ngoài.

Mỗi **GroupedOpenApi** tạo một tài liệu OpenAPI riêng. Các nhóm có thể cố ý chồng lấn: cùng một operation có thể được công bố trong tài liệu tổng quan và tài liệu chuyên biệt của miền nghiệp vụ. Việc xuất hiện trong nhiều tài liệu không tạo thêm route và cũng không làm thay đổi quyền truy cập runtime.

Bài này giải thích cách các bộ lọc bao gồm và loại trừ hoạt động, cách thiết kế nhóm có chồng lấn có chủ đích, cách truy tìm operation bị thiếu và cách kiểm tra từng tài liệu JSON/YAML.

## 1. Một operation có thể thuộc nhiều nhóm

Giả sử ứng dụng có các endpoint:

| Operation | Controller | Mục đích |
|---|---|---|
| GET /api/books | BookController | Liệt kê sách |
| GET /api/books/{bookId} | BookController | Xem một sách |
| POST /api/books | BookController | Tạo sách |
| GET /api/orders | OrderController | Liệt kê đơn hàng |
| POST /api/orders | OrderController | Tạo đơn hàng |
| GET /api/internal/health | InternalController | Kiểm tra nội bộ |

Có thể muốn tạo hai tài liệu:

- **public-api**: mọi endpoint công khai dưới /api, ngoại trừ phần internal.
- **orders**: chỉ endpoint quản lý đơn hàng.

Trong thiết kế này, GET /api/orders và POST /api/orders xuất hiện trong cả hai tài liệu. Đây là chồng lấn có chủ đích, không phải lỗi trùng route.

~~~mermaid
flowchart TD
    A["Các Spring MVC handler"] --> B["Bộ lọc của nhóm public-api"]
    A --> C["Bộ lọc của nhóm orders"]
    B --> D["Tài liệu /v3/api-docs/public-api"]
    C --> E["Tài liệu /v3/api-docs/orders"]
    F["GET/POST /api/orders"] --> B
    F --> C
    G["GET /api/internal/health"] --> H["Bị loại khỏi public-api"]
    G --> I["Không khớp nhóm orders"]
~~~

Một nhóm là một **ảnh chụp hợp đồng API theo phạm vi**. Nhóm không phải module Spring riêng, không đăng ký lại controller và không tạo endpoint HTTP mới cho nghiệp vụ.

## 2. Các bộ lọc của GroupedOpenApi

Các bộ lọc thường dùng:

| Bộ lọc | Tác dụng |
|---|---|
| **pathsToMatch** | Chỉ giữ operation có path khớp ít nhất một pattern được khai báo |
| **pathsToExclude** | Loại operation có path khớp pattern loại trừ |
| **packagesToScan** | Chỉ giữ handler thuộc package được chọn |
| **packagesToExclude** | Loại handler thuộc package bị loại trừ |

Ví dụ cấu hình:

~~~java
@Configuration
public class OpenApiGroups {

    @Bean
    GroupedOpenApi publicApi() {
        return GroupedOpenApi.builder()
            .group("public-api")
            .pathsToMatch("/api/**")
            .pathsToExclude("/api/internal/**")
            .build();
    }

    @Bean
    GroupedOpenApi ordersApi() {
        return GroupedOpenApi.builder()
            .group("orders")
            .packagesToScan("com.example.app.orders")
            .pathsToMatch("/api/**")
            .build();
    }
}
~~~

Trong ví dụ:

- public-api nhận các path thuộc /api/** rồi loại phần /api/internal/**.
- orders nhận handler thuộc package orders và có path thuộc /api/**.
- Nếu một handler của package orders có path /api/orders, nó có thể thuộc cả hai nhóm.

### Cách các bộ lọc kết hợp

Với cấu hình có cả path và package, nên hiểu điều kiện theo hai tầng:

1. Trong cùng một danh sách pattern, operation chỉ cần khớp **một** pattern để thỏa bộ lọc đó.
2. Khi nhóm khai báo cả bộ lọc path và package, operation phải thỏa các điều kiện bao gồm tương ứng; các điều kiện loại trừ sẽ loại operation nếu nó khớp tiêu chí bị loại.

Ví dụ, một nhóm khai báo:

~~~java
GroupedOpenApi.builder()
    .group("catalog")
    .pathsToMatch("/api/**")
    .packagesToScan("com.example.app.catalog")
    .pathsToExclude("/api/catalog/internal/**")
    .build();
~~~

Một handler cần thuộc package được chọn và có path khớp /api/**. Sau đó, nếu path khớp /api/catalog/internal/** thì handler bị loại khỏi nhóm.

Đừng coi danh sách pathsToMatch và packagesToScan là hai danh sách thay thế nhau. Khi khai báo cả hai, chúng cùng giới hạn phạm vi. Nếu kết quả rỗng ngoài dự kiến, hãy thử kiểm tra riêng path filter và package filter để tìm điều kiện đang loại operation.

Bảng quyết định đơn giản:

| Path khớp include | Package khớp include | Khớp exclusion | Kết quả |
|---|---|---|---|
| Có | Có | Không | Được đưa vào group |
| Không | Có | Không | Bị loại |
| Có | Không | Không | Bị loại |
| Có | Có | Có | Bị loại |

> Quy tắc so khớp cụ thể và bộ lọc bổ sung có thể thay đổi theo phiên bản springdoc/Spring. Hãy xác minh bằng endpoint tài liệu thực tế của phiên bản dự án đang dùng, nhất là khi dùng pattern phức tạp hoặc package lồng nhau.

## 3. Chồng lấn nhóm bằng path pattern

Một cách đơn giản để tạo nhóm chồng lấn là dùng các path pattern có phạm vi bao hàm nhau:

~~~java
@Bean
GroupedOpenApi allPublicEndpoints() {
    return GroupedOpenApi.builder()
        .group("public-api")
        .pathsToMatch("/api/**")
        .pathsToExclude("/api/internal/**")
        .build();
}

@Bean
GroupedOpenApi bookEndpoints() {
    return GroupedOpenApi.builder()
        .group("books")
        .pathsToMatch("/api/books/**")
        .build();
}

@Bean
GroupedOpenApi orderEndpoints() {
    return GroupedOpenApi.builder()
        .group("orders")
        .pathsToMatch("/api/orders/**")
        .build();
}
~~~

Các endpoint sách thuộc public-api và books. Các endpoint đơn hàng thuộc public-api và orders. Đây là cách phù hợp khi tài liệu tổng quan phục vụ người tích hợp chung, còn tài liệu chuyên biệt phục vụ nhóm phát triển hoặc khách hàng của một miền.

### Đặt tên group ổn định

Tên group được dùng trong URL tài liệu, ví dụ:

- /v3/api-docs/public-api
- /v3/api-docs/books
- /v3/api-docs/orders

Hãy dùng tên ngắn, duy nhất và ổn định. Đổi group name có thể làm thay đổi URL mà Swagger UI, cổng API, pipeline kiểm thử hoặc công cụ client đang tham chiếu.

Tên group không phải tên tag. **Group** quyết định operation nào nằm trong một tài liệu; **tag** phân loại operation bên trong tài liệu đó. Một group orders vẫn có thể chứa các tag Orders, Payments và Customers nếu các operation đó cùng thuộc phạm vi tài liệu.

## 4. Chồng lấn nhóm bằng package filter

Package filter hữu ích khi cấu trúc mã nguồn phản ánh ranh giới miền nghiệp vụ:

~~~text
com.example.app
  books
    BookController
  orders
    OrderController
  payments
    PaymentController
  internal
    InternalController
~~~

Có thể tạo tài liệu theo package:

~~~java
@Bean
GroupedOpenApi bookApi() {
    return GroupedOpenApi.builder()
        .group("books")
        .packagesToScan("com.example.app.books")
        .build();
}

@Bean
GroupedOpenApi commerceApi() {
    return GroupedOpenApi.builder()
        .group("commerce")
        .packagesToScan(
            "com.example.app.orders",
            "com.example.app.payments"
        )
        .build();
}
~~~

Nếu một package được đưa vào nhiều group, handler của package đó có thể xuất hiện ở nhiều tài liệu. Ví dụ, group commerce và group orders đều có thể quét package orders.

### Package scan không phải component scan

**packagesToScan** của GroupedOpenApi lọc các handler khi tạo tài liệu. Nó không làm Spring đăng ký controller và không thay đổi component scan của ứng dụng.

Nếu controller không được Spring tạo thành bean, thêm package đó vào packagesToScan không làm endpoint xuất hiện. Trước tiên phải xác nhận controller thực sự được đăng ký và có request mapping.

### Kiểm tra package thực tế của controller

Một lỗi thường gặp là dùng package cha hoặc package con không đúng với package khai báo của class. Khi nghi ngờ:

1. Mở khai báo package trong file controller.
2. Đối chiếu với packagesToScan và packagesToExclude.
3. Kiểm tra nhóm có đồng thời đặt pathsToMatch hay không.
4. Lấy tài liệu nhóm và tìm path cụ thể.

Không suy luận package từ tên folder trên ổ đĩa; package Java được xác định bởi khai báo package trong source và cấu trúc class đã biên dịch.

Package filter thường được áp dụng theo package name của handler và có thể bao gồm các package con. Tránh đặt package có tiền tố dễ gây nhập nhằng; ví dụ package tên **orders** và **ordersArchive** có thể khó phân biệt nếu cơ chế so khớp của phiên bản đang dùng dựa trên prefix. Khi package boundary quan trọng, chọn package namespace rõ ràng và xác minh operation thực tế trong từng group.

## 5. Loại trừ luôn được kiểm tra cùng với điều kiện bao gồm

Loại trừ hữu ích khi một nhóm rộng cần bỏ qua một số route hoặc package:

~~~java
@Bean
GroupedOpenApi partnerApi() {
    return GroupedOpenApi.builder()
        .group("partner-api")
        .pathsToMatch("/api/**")
        .pathsToExclude(
            "/api/internal/**",
            "/api/admin/**"
        )
        .packagesToExclude(
            "com.example.app.internal",
            "com.example.app.admin"
        )
        .build();
}
~~~

Trong ví dụ, nhóm partner-api chỉ nhận các handler thuộc phạm vi path /api/**, sau đó loại các path hoặc package được chỉ định. Các tiêu chí loại trừ nên được xem như ranh giới bảo vệ tài liệu: nếu handler khớp một tiêu chí loại trừ, nó không thuộc group này.

### Cẩn thận với path quá rộng

Pattern **/** có thể bao phủ gần như toàn bộ route mà springdoc nhìn thấy. Nếu dùng nó làm điều kiện bao gồm, hãy thêm loại trừ rõ ràng cho các path không dành cho tài liệu đó.

Ví dụ:

~~~java
GroupedOpenApi.builder()
    .group("external")
    .pathsToMatch("/**")
    .pathsToExclude(
        "/internal/**",
        "/actuator/**",
        "/admin/**"
    )
    .build();
~~~

Đối với tài liệu công khai, nên ưu tiên allowlist theo prefix rõ ràng như /api/public/** hoặc package API được chọn. Danh sách loại trừ có thể bị quên cập nhật khi một endpoint nội bộ mới được thêm vào.

## 6. Cấu hình group bằng application.yml

Ngoài Java bean, springdoc hỗ trợ khai báo group qua cấu hình Spring Boot. Ví dụ:

~~~yaml
springdoc:
  group-configs:
    - group: public-api
      paths-to-match:
        - /api/**
      paths-to-exclude:
        - /api/internal/**
        - /api/admin/**
    - group: orders
      packages-to-scan:
        - com.example.app.orders
      paths-to-match:
        - /api/**
    - group: books
      paths-to-match:
        - /api/books/**
~~~

Mỗi phần tử trong group-configs tạo một nhóm tài liệu với tên riêng. Có thể dùng package filter, path filter hoặc kết hợp chúng để xác định phạm vi.

Khi dùng cấu hình properties:

- Dùng group name duy nhất.
- Kiểm tra YAML indentation và tên property theo phiên bản springdoc.
- Tránh định nghĩa cùng một group ở cả Java bean và properties nếu không có chủ đích.
- Nếu có cấu hình toàn cục như springdoc.paths-to-match hoặc springdoc.packages-to-scan, kiểm tra tác động của chúng lên phạm vi tài liệu cùng với cấu hình group.

Không nên giả định rằng cấu hình toàn cục và cấu hình từng group tự triệt tiêu nhau. Khi nhiều tầng filter cùng tồn tại, kiểm tra endpoint JSON là cách xác nhận đáng tin cậy nhất.

## 7. Operation bị thiếu: xác định nó bị loại ở đâu

Khi một operation không xuất hiện trong tài liệu, hãy tìm theo thứ tự sau.

### Bước 1: Xác nhận endpoint tồn tại trong Spring MVC

Kiểm tra:

- Controller có được component scan tạo bean không?
- Method có @GetMapping, @PostMapping, @RequestMapping hoặc mapping tương ứng không?
- Profile, conditional bean hoặc cấu hình triển khai có làm controller không được tạo không?
- Endpoint có bị mapping khác xung đột hoặc không đăng ký không?

Nếu ứng dụng có Spring Boot Actuator và endpoint mappings đã được expose, **/actuator/mappings** có thể giúp kiểm tra mapping runtime. Chỉ dùng endpoint này trong môi trường và cấu hình cho phép; nó không phải endpoint OpenAPI.

### Bước 2: Kiểm tra bộ lọc của đúng group

Đối chiếu package controller với packagesToScan và packagesToExclude. Sau đó đối chiếu path với pathsToMatch và pathsToExclude.

Nếu group dùng cả package lẫn path, kiểm tra từng điều kiện. Một handler đúng package nhưng path không khớp vẫn có thể bị loại; tương tự handler đúng path nhưng nằm ngoài package được chọn.

### Bước 3: Kiểm tra annotation ẩn

Các annotation sau có thể loại operation khỏi tài liệu:

~~~java
@Hidden
@RestController
public class InternalController {
    // Các operation của controller có thể bị ẩn khỏi OpenAPI
}
~~~

Hoặc ẩn một method:

~~~java
@Operation(hidden = true)
@GetMapping("/api/internal/diagnostics")
public DiagnosticsResponse diagnostics() {
    // ...
    return null;
}
~~~

Hãy tìm cả annotation trên class và method. Nếu controller dùng functional endpoint, kiểm tra cấu hình router và metadata tương ứng của springdoc.

### Bước 4: Kiểm tra filter toàn cục và customizer

Ngoài filter của group, ứng dụng có thể có:

- Cấu hình toàn cục springdoc.paths-to-match, springdoc.paths-to-exclude, springdoc.packages-to-scan hoặc springdoc.packages-to-exclude.
- Customizer thay đổi danh sách path/operation sau bước lọc. Cần phân biệt **OpenApiCustomizer** cho tài liệu mặc định, **GlobalOpenApiCustomizer** cho tài liệu mặc định và các group, và customizer gắn trực tiếp vào **GroupedOpenApi** cho group tương ứng.
- Cấu hình ẩn operation hoặc controller.
- Cấu hình group chỉ được kích hoạt ở một profile hoặc một application context nhất định.

Một customizer có thể loại path khỏi tài liệu sau khi filter ban đầu đã chọn operation. Vì vậy, nếu path vượt qua bộ lọc nhưng vẫn không có trong JSON cuối, hãy kiểm tra các customizer và cấu hình OpenAPI.

### Bước 5: Kiểm tra đúng URL tài liệu

Đừng chỉ mở /v3/api-docs rồi kết luận một group không có operation. Hãy truy vấn đúng group:

~~~bash
curl -i http://localhost:8080/v3/api-docs/orders
curl -i http://localhost:8080/v3/api-docs/books
curl -i http://localhost:8080/v3/api-docs/public-api
~~~

Nếu cấu hình hỗ trợ YAML:

~~~bash
curl -i http://localhost:8080/v3/api-docs/orders.yaml
~~~

Nếu endpoint tài liệu đã được đổi bằng springdoc.api-docs.path hoặc group được cấu hình theo cách khác, dùng URL tương ứng của ứng dụng.

## 8. Phân biệt operation không có trong tài liệu với endpoint không tồn tại

Đây là hai kết luận khác nhau:

| Quan sát | Có thể kết luận |
|---|---|
| Endpoint trả 200 khi gọi trực tiếp nhưng không có trong group A | Runtime route tồn tại; group A không công bố operation đó |
| Endpoint có trong group B nhưng không có trong group A | Group B bao gồm operation; group A loại hoặc không chọn operation |
| Endpoint không có trong bất kỳ tài liệu nào và gọi trực tiếp trả 404 | Có thể mapping chưa đăng ký, nhưng cần kiểm tra profile, context và base path |
| /v3/api-docs/orders trả 401/403 | Có thể tài liệu bị bảo vệ; chưa thể kết luận operation bị filter |
| /v3/api-docs/orders trả 404 | Có thể group name/URL sai hoặc group không được đăng ký |
| Tài liệu có path nhưng thiếu một HTTP method | Có thể method bị ẩn, filter/customizer hoặc mapping của method khác nhau |

Đặc biệt, nếu request tới /v3/api-docs/{group} bị 401 hoặc 403, đó là vấn đề truy cập tài liệu. Nó khác với việc server trả tài liệu thành công nhưng JSON không chứa operation mong đợi.

## 9. Bộ lọc tài liệu không phải bảo mật runtime

Loại một endpoint khỏi OpenAPI không chặn client gọi endpoint đó. Ví dụ:

~~~java
@Bean
GroupedOpenApi publicApi() {
    return GroupedOpenApi.builder()
        .group("public-api")
        .pathsToMatch("/api/**")
        .pathsToExclude("/api/admin/**")
        .build();
}
~~~

Cấu hình trên chỉ loại /api/admin/** khỏi tài liệu public-api. Nếu Spring MVC vẫn đăng ký endpoint và Spring Security vẫn cho phép người gọi, client có thể gọi route đó.

Muốn bảo vệ endpoint, cần cấu hình Spring Security, authorization tại service/controller hoặc cơ chế bảo vệ phù hợp. Muốn bảo vệ tài liệu OpenAPI, cấu hình quyền truy cập tới /v3/api-docs và Swagger UI. Không dùng pathsToExclude như một biện pháp phân quyền.

Tương tự, việc một operation xuất hiện trong public-api không có nghĩa mọi người dùng đều có quyền gọi operation đó. Tài liệu và quyền truy cập là hai hợp đồng khác nhau.

## 10. Kiểm tra phạm vi từng group bằng jq

Sau khi ứng dụng chạy, lấy danh sách path trong từng tài liệu:

~~~bash
curl -s http://localhost:8080/v3/api-docs/public-api \
  | jq -r '.paths | keys[]'

curl -s http://localhost:8080/v3/api-docs/orders \
  | jq -r '.paths | keys[]'
~~~

Để xem method và path:

~~~bash
curl -s http://localhost:8080/v3/api-docs/orders \
  | jq -r '
      .paths
      | to_entries[]
      | .key as $path
      | .value
      | to_entries[]
      | select(
          .key == "get" or
          .key == "post" or
          .key == "put" or
          .key == "patch" or
          .key == "delete" or
          .key == "head" or
          .key == "options" or
          .key == "trace"
        )
      | "\(.key | ascii_upcase) \($path)"
    '
~~~

Để xác nhận một operation cụ thể:

~~~bash
curl -s http://localhost:8080/v3/api-docs/orders \
  | jq '.paths["/api/orders"].get'
~~~

Nếu kết quả là null, operation không có trong tài liệu orders tại URL đó. Tiếp tục kiểm tra tài liệu public-api hoặc nhóm khác để xác định operation có được công bố ở nơi khác hay không.

### So sánh hai nhóm

Có thể tải hai tài liệu về file tạm rồi so sánh danh sách path/method bằng jq hoặc script kiểm thử. Khi so sánh, hãy so sánh cả method chứ không chỉ path: một path có thể có GET trong nhóm A nhưng chỉ có POST trong nhóm B.

Đối với API lớn, nên duy trì danh sách operation mong đợi cho từng group. Danh sách này giúp phát hiện:

- Operation mới vô tình lọt vào tài liệu bên ngoài.
- Operation công khai bị mất sau khi đổi package hoặc path.
- Nhóm chuyên biệt nhận quá nhiều endpoint.
- Hai nhóm không còn chồng lấn như thiết kế ban đầu.

## 11. Kiểm thử group bằng MockMvc

Có thể kiểm tra endpoint tài liệu trong integration test:

~~~java
@SpringBootTest
@AutoConfigureMockMvc
class OpenApiGroupTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void ordersDocumentContainsOrderOperations() throws Exception {
        mockMvc.perform(get("/v3/api-docs/orders"))
            .andExpect(status().isOk())
            .andExpect(jsonPath(
                "$['paths']['/api/orders']['get']"
            ).exists())
            .andExpect(jsonPath(
                "$['paths']['/api/orders']['post']"
            ).exists());
    }

    @Test
    void publicDocumentDoesNotExposeInternalPath() throws Exception {
        mockMvc.perform(get("/v3/api-docs/public-api"))
            .andExpect(status().isOk())
            .andExpect(jsonPath(
                "$['paths']['/api/internal/health']"
            ).doesNotExist());
    }
}
~~~

Ví dụ trên kiểm tra tài liệu được sinh ra. Nên bổ sung test gọi endpoint runtime để xác nhận route và quyền truy cập hoạt động đúng theo yêu cầu. Hai test có mục tiêu khác nhau:

- Test tài liệu kiểm tra operation nào được công bố trong group.
- Test runtime kiểm tra request thật được xử lý và authorization được áp dụng.

Nếu dự án bảo vệ /v3/api-docs bằng Spring Security, test cần dùng principal hoặc cấu hình test phù hợp để truy cập tài liệu. Không diễn giải lỗi 401/403 thành lỗi filter group.

## 12. Lập ma trận phạm vi group trước khi cấu hình

Trước khi tạo nhiều GroupedOpenApi, lập ma trận operation giúp nhìn rõ chồng lấn và loại trừ:

| Operation | public-api | books | orders | internal |
|---|---:|---:|---:|---:|
| GET /api/books | Có | Có | Không | Không |
| POST /api/books | Có | Có | Không | Không |
| GET /api/orders | Có | Không | Có | Không |
| POST /api/orders | Có | Không | Có | Không |
| GET /api/internal/health | Không | Không | Không | Có |

Ma trận này là tiêu chí kiểm thử. Sau khi thay đổi path, package hoặc group, đối chiếu tài liệu thực tế với ma trận để phát hiện operation bị thiếu hoặc xuất hiện sai nhóm.

Một số nguyên tắc hữu ích:

- Mỗi group cần có mục đích và đối tượng sử dụng rõ ràng.
- Chồng lấn chỉ nên xuất hiện khi operation thực sự cần có trong nhiều tài liệu.
- Dùng allowlist path/package rõ ràng cho tài liệu dành cho đối tác hoặc khách hàng.
- Đặt group name ổn định vì URL tài liệu có thể được hệ thống khác tham chiếu.
- Tránh cấu hình quá nhiều group có cùng filter; chúng làm tăng số tài liệu nhưng không tăng giá trị phân loại.
- Khi một operation bị thiếu, xác minh runtime mapping trước rồi mới kiểm tra từng tầng filter.

## 13. Checklist điều tra operation bị thiếu hoặc lọt nhóm

**Khi operation bị thiếu:**

- [ ] Đã xác nhận controller là Spring bean.
- [ ] Đã xác nhận method có request mapping hợp lệ.
- [ ] Đã gọi đúng URL tài liệu của group.
- [ ] Path khớp ít nhất một pathsToMatch nếu filter này được cấu hình.
- [ ] Package khớp packagesToScan nếu filter này được cấu hình.
- [ ] Path không khớp pathsToExclude.
- [ ] Package không khớp packagesToExclude.
- [ ] Controller/method không bị @Hidden hoặc @Operation(hidden = true).
- [ ] Đã kiểm tra global filters, customizer và profile cấu hình.
- [ ] Đã phân biệt lỗi truy cập tài liệu 401/403 với operation không có trong JSON.

**Khi operation xuất hiện trong nhóm không mong muốn:**

- [ ] Kiểm tra path pattern bao phủ route.
- [ ] Kiểm tra package scan có bao gồm package của controller.
- [ ] Kiểm tra group có dùng filter toàn cục hay không.
- [ ] Bổ sung path/package exclusion phù hợp.
- [ ] Xem operation có được cố ý chia sẻ giữa tài liệu tổng quan và tài liệu chuyên biệt không.
- [ ] Kiểm tra JSON sau thay đổi và xác nhận operation không bị loại khỏi group cần giữ.

## Kết luận

Một operation có thể xuất hiện trong nhiều GroupedOpenApi nếu nó thỏa bộ lọc của từng nhóm. **pathsToMatch** và **packagesToScan** xác định phạm vi bao gồm; **pathsToExclude** và **packagesToExclude** loại các handler không phù hợp. Operation bị thiếu cần được kiểm tra từ Spring MVC mapping, package/path filter, annotation ẩn, cấu hình toàn cục, customizer đến URL tài liệu của đúng group. Hãy dùng JSON tại **/v3/api-docs/{group}**, jq, ma trận phạm vi và test MockMvc để xác nhận từng nhóm. Bộ lọc tài liệu chỉ quyết định nội dung OpenAPI; bảo mật endpoint và bảo mật tài liệu vẫn cần cấu hình riêng.
