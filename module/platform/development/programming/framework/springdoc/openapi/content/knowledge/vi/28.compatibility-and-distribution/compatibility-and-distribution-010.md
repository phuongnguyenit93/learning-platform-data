# Phân biệt liệt kê nhiều đặc tả với hợp nhất các đặc tả thành một

Khi một hệ thống có nhiều nhóm API hoặc nhiều microservice, Swagger UI có thể hiển thị nhiều tài liệu OpenAPI để người dùng chọn. Việc hiển thị nhiều tài liệu trong một giao diện **không làm chúng trở thành một đặc tả duy nhất**. Nếu cần một hợp đồng tổng hợp cho API Gateway, cần chạy bước merge để tạo ra một OpenAPI document mới.

Với Spring Boot và springdoc-openapi, có ba cách tổ chức thường gặp:

1. **Tách nhóm trong một ứng dụng** bằng GroupedOpenApi: mỗi nhóm sinh một OpenAPI document riêng.
2. **Liệt kê nhiều document trong Swagger UI** bằng springdoc.swagger-ui.urls: người dùng chọn một tài liệu để xem; các document vẫn độc lập.
3. **Hợp nhất document** bằng công cụ OpenAPI merge: các paths, components và thông tin tương ứng được kết hợp thành một OpenAPI document mới.

Chọn đúng cách giúp giữ ranh giới API rõ ràng, tránh tạo một tài liệu khổng lồ không có chủ đích hoặc nhầm rằng một dropdown trong Swagger UI đã tạo API Gateway contract.

## 1. Ba khái niệm và kết quả khác nhau

| Cách làm | Đầu vào | Kết quả | Khi phù hợp |
|---|---|---|---|
| GroupedOpenApi | Controller, DTO và configuration trong một Spring Boot application | Nhiều tài liệu OpenAPI riêng, mỗi tài liệu có group name và URL riêng | Monolith có public/admin/internal API hoặc nhiều bounded context. |
| Swagger UI urls | Nhiều URL OpenAPI độc lập, có thể cùng ứng dụng hoặc từ nhiều service | Một Swagger UI có danh sách chọn tài liệu | Developer portal muốn duyệt API của nhiều service. |
| Merge OpenAPI | Nhiều OpenAPI JSON/YAML | Một OpenAPI document tổng hợp | Gateway hoặc facade công bố một hợp đồng API thống nhất. |

Điểm mấu chốt:

- Grouping quyết định operation nào thuộc tài liệu nào.
- Listing quyết định Swagger UI cho người dùng chọn tài liệu nào.
- Merging tạo ra một tài liệu mới chứa các operation được kết hợp.

## 2. Tách nhiều tài liệu bằng GroupedOpenApi

GroupedOpenApi cho phép chia API theo package scan, path matching hoặc kết hợp cả hai. Mỗi group phải có tên riêng. Springdoc sinh tài liệu mặc định theo URL:

    /v3/api-docs/{groupName}

Ví dụ ứng dụng Catalog có API quản lý sản phẩm và API quản trị:

~~~java
import org.springdoc.core.models.GroupedOpenApi;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class OpenApiGroupConfiguration {

    @Bean
    GroupedOpenApi catalogApi() {
        return GroupedOpenApi.builder()
                .group("catalog")
                .pathsToMatch("/api/catalog/**")
                .build();
    }

    @Bean
    GroupedOpenApi catalogAdminApi() {
        return GroupedOpenApi.builder()
                .group("catalog-admin")
                .pathsToMatch("/api/admin/catalog/**")
                .build();
    }
}
~~~

Ứng dụng cung cấp hai tài liệu độc lập:

| Group | URL |
|---|---|
| catalog | /v3/api-docs/catalog |
| catalog-admin | /v3/api-docs/catalog-admin |

Group catalog không tự động chứa các operation của catalog-admin. Nếu một path thỏa điều kiện của hai group, operation đó có thể xuất hiện trong cả hai document. Đây là kết quả của hai bộ lọc độc lập, không phải merge.

### 2.1. Chia nhóm bằng package

Nếu package phản ánh ranh giới module, có thể dùng packagesToScan:

~~~java
@Bean
GroupedOpenApi billingApi() {
    return GroupedOpenApi.builder()
            .group("billing")
            .packagesToScan("com.example.billing.api")
            .build();
}
~~~

Có thể kết hợp package và path:

~~~java
@Bean
GroupedOpenApi partnerApi() {
    return GroupedOpenApi.builder()
            .group("partner")
            .packagesToScan(
                    "com.example.catalog.api",
                    "com.example.billing.api"
            )
            .pathsToMatch("/partner/**")
            .build();
}
~~~

Điều kiện package và path giúp kiểm soát phạm vi operation của từng tài liệu. Chọn quy tắc dựa trên cấu trúc API mà nhóm muốn công bố, không chỉ dựa vào cấu trúc thư mục Java.

### 2.2. Khai báo group trong application.yml

Với cấu hình đơn giản, có thể dùng springdoc.group-configs:

~~~yaml
springdoc:
  group-configs:
    - group: catalog
      paths-to-match:
        - /api/catalog/**
    - group: billing
      packages-to-scan:
        - com.example.billing.api
~~~

Tên property tương ứng trong tài liệu springdoc gồm springdoc.group-configs[0].group, packages-to-scan, paths-to-match và paths-to-exclude. Với điều kiện phức tạp hơn, customizer hoặc bean GroupedOpenApi cho phép cấu hình bằng Java.

### 2.3. Group không thay thế security boundary

Một group tên internal không tự bảo vệ tài liệu. Endpoint /v3/api-docs/internal vẫn phải được bảo vệ bằng Spring Security hoặc network policy phù hợp. Tương tự, Swagger UI ẩn một tài liệu khỏi dropdown không có nghĩa URL tài liệu đã bị vô hiệu hóa.

Hãy phân biệt:

- Group filter: operation nào được đưa vào tài liệu.
- Swagger UI listing: tài liệu nào được hiển thị để chọn.
- Authorization: ai được phép tải tài liệu hoặc gọi API.

## 3. Liệt kê nhiều tài liệu trong một Swagger UI

Springdoc hỗ trợ property springdoc.swagger-ui.urls. Mỗi entry gồm name và url; Swagger UI dùng Topbar plugin để người dùng chọn một API definition.

Ví dụ ứng dụng có hai group:

~~~yaml
springdoc:
  swagger-ui:
    urls:
      - name: Catalog API
        url: /v3/api-docs/catalog
      - name: Billing API
        url: /v3/api-docs/billing
    urls-primary-name: Catalog API
~~~

Khi mở /swagger-ui.html, người dùng có thể chọn Catalog API hoặc Billing API. urls-primary-name xác định tài liệu được mở mặc định. Tên và URL trong danh sách cần duy nhất.

### 3.1. Liệt kê tài liệu từ nhiều microservice

Swagger UI có thể lấy tài liệu từ service khác:

~~~yaml
springdoc:
  swagger-ui:
    urls:
      - name: Catalog
        url: https://catalog.example.com/v3/api-docs
      - name: Billing
        url: https://billing.example.com/v3/api-docs
      - name: Identity
        url: https://identity.example.com/v3/api-docs
    urls-primary-name: Catalog
~~~

Trong trường hợp này, Swagger UI là điểm truy cập chung để duyệt các API. Mỗi lần người dùng chọn một entry, UI tải document tương ứng và hiển thị operation của document đó. urls không chép các paths vào nhau và không tạo components chung.

Nếu Swagger UI và các service nằm khác origin, trình duyệt cần tải được tài liệu qua CORS. Cấu hình CORS trên service cung cấp OpenAPI phải cho phép origin của Swagger UI. Nếu tài liệu cần authentication, cấu hình quyền truy cập và credential cho từng nguồn.

### 3.2. urls và url có ưu tiên khác nhau

Swagger UI hỗ trợ:

- springdoc.swagger-ui.url: một OpenAPI file tùy chỉnh.
- springdoc.swagger-ui.urls: danh sách nhiều OpenAPI definitions.
- springdoc.swagger-ui.urls-primary-name: tên tài liệu được chọn mặc định trong danh sách.

Khi urls được cấu hình, property url bị bỏ qua. Không khai báo cả hai với kỳ vọng Swagger UI sẽ tự hợp nhất chúng.

### 3.3. Liệt kê nhiều tài liệu không tạo server URL chung

Mỗi document vẫn giữ servers, security schemes và API version của chính nó. Khi người dùng chọn Catalog, Try it out dùng server URL trong Catalog document; khi chọn Billing, UI dùng server URL của Billing document.

Điều này phù hợp với portal liệt kê nhiều service độc lập. Nếu mục tiêu là mọi operation được gọi qua một hostname/path của API Gateway, cần thiết kế một hợp đồng gateway và có thể phải merge hoặc tạo một document facade riêng.

## 4. Hợp nhất nhiều OpenAPI document thành một

Merge là bước xử lý các tài liệu đầu vào và tạo một tài liệu OpenAPI mới. Ví dụ ba service công bố:

- catalog.yaml
- billing.yaml
- identity.yaml

Một API Gateway muốn công bố chung:

https://api.example.com/platform

Khi đó, kết quả merge có thể chứa các paths:

~~~yaml
paths:
  /catalog/products:
    get:
      operationId: listProducts
  /billing/invoices:
    get:
      operationId: listInvoices
  /identity/users/me:
    get:
      operationId: getCurrentUser
~~~

Đây là một OpenAPI document có một paths object tổng hợp. Người tiêu thụ có thể tải một file để khám phá tất cả operation của facade.

**Merge đặc tả không triển khai routing.** API Gateway vẫn phải định tuyến /catalog/** tới Catalog service, /billing/** tới Billing service và /identity/** tới Identity service. Nếu path trong OpenAPI không khớp gateway, tài liệu hợp nhất sẽ mô tả một API không tồn tại trên runtime.

## 5. Dùng openapi-merge-cli

Một công cụ dành cho bước merge là openapi-merge-cli. Công cụ nhận nhiều OpenAPI 3.0, 3.1 hoặc 3.2 document, áp dụng quy tắc kết hợp và ghi ra một file mới. Các input phải cùng major.minor OpenAPI version.

Cài đặt như development dependency:

~~~bash
npm install --save-dev openapi-merge-cli
~~~

Tạo file cấu hình openapi-merge.yaml:

~~~yaml
inputs:
  - inputFile: ./specs/gateway.yaml
  - inputFile: ./specs/catalog.yaml
    pathModification:
      stripStart: /api
      prepend: /catalog
    dispute:
      prefix: Catalog
  - inputFile: ./specs/billing.yaml
    pathModification:
      stripStart: /api
      prepend: /billing
    dispute:
      prefix: Billing
  - inputFile: ./specs/identity.yaml
    pathModification:
      stripStart: /api
      prepend: /identity
    dispute:
      prefix: Identity

output: ./dist/platform-api.yaml
serversStrategy: first
securitySchemesStrategy: merge
resolveExternalReferences: true
inputRoot: ./specs
outputRoot: ./dist
~~~

File gateway.yaml đứng đầu danh sách là document nền cho facade. Ví dụ:

~~~yaml
openapi: 3.1.0
info:
  title: Platform API
  version: 1.0.0
servers:
  - url: https://api.example.com/platform
    description: Public API Gateway
paths: {}
~~~

Document nền cung cấp info và servers cho kết quả. Các document service theo sau đóng góp paths, operations và components.

Chạy:

~~~bash
npx openapi-merge-cli --config openapi-merge.yaml
~~~

Ý nghĩa cấu hình:

- inputs: thứ tự và danh sách document đầu vào.
- info và servers: mặc định lấy từ input đầu tiên; vì vậy gateway.yaml được đặt đầu tiên để định nghĩa metadata và public server của facade.
- pathModification: stripStart loại prefix /api của service rồi prepend thêm prefix theo service để khớp route gateway.
- dispute.prefix: tạo tên riêng khi component trùng tên nhưng có định nghĩa khác nhau.
- output: đường dẫn document kết quả.
- serversStrategy: first: giữ servers từ input đầu tiên; đặt gateway contract làm input đầu tiên nếu đây là chủ đích.
- securitySchemesStrategy: merge: kết hợp các security scheme theo chiến lược của tool.
- resolveExternalReferences: cho phép theo các $ref sang file khác để đưa component cần thiết vào kết quả.
- inputRoot và outputRoot: giới hạn phạm vi file được đọc và file kết quả được ghi.

openapi-merge-cli cũng có lệnh init để tạo cấu hình mẫu:

~~~bash
npx openapi-merge-cli init
~~~

Lệnh merge đọc file cấu hình và tạo output. Hãy commit cấu hình merge cùng pipeline để kết quả có thể tái tạo.

## 6. Những xung đột cần xử lý khi merge

Hai document độc lập có thể hợp lệ nhưng khi kết hợp lại có xung đột. Merge tool cần phát hiện hoặc áp dụng quy tắc rõ ràng.

### 6.1. Trùng path và HTTP method

Giả sử hai service đều có:

GET /health

Nếu merge nguyên trạng, một path/method có thể bị trùng. Có thể:

- Thêm prefix theo service, ví dụ /catalog/health và /billing/health.
- Chọn operation thuộc gateway facade và loại operation còn lại.
- Dùng quy tắc merge khi cùng path nhưng các HTTP methods không trùng và các path-level fields tương thích.

openapi-merge-cli có duplicatePathHandling với các lựa chọn như error, skip-later, prefer-later và merge-operations. Mặc định nên để xung đột làm merge thất bại để nhóm review. skip-later hoặc prefer-later có thể làm mất operation nếu dùng mà không kiểm tra.

### 6.2. Trùng component name

Hai service có thể cùng khai báo ErrorResponse nhưng schema khác nhau. Không nên giả định chúng giống nhau chỉ vì tên trùng.

Một chiến lược an toàn là đổi tên component theo service:

- CatalogErrorResponse
- BillingErrorResponse
- IdentityErrorResponse

Merge tool có thể deduplicate component có cấu trúc giống nhau và áp dụng prefix/suffix cho component name bị xung đột. Khi đổi tên, mọi $ref trỏ tới component đó phải được cập nhật. Kiểm tra output để chắc chắn không còn reference hỏng.

### 6.3. Trùng operationId

operationId nên duy nhất trong một OpenAPI document. Nếu hai service cùng khai báo getById, client generator có thể tạo method trùng tên hoặc thất bại.

Đặt operationId có namespace hoặc ngữ cảnh:

- catalogGetProductById
- billingGetInvoiceById
- identityGetUserById

Không chỉ đổi path rồi giữ operationId trùng. Hãy kiểm tra tính duy nhất sau khi merge.

### 6.4. $ref nội bộ và cross-document

Một component có thể tham chiếu:

~~~yaml
$ref: "#/components/schemas/Product"
~~~

Đây là local reference trong cùng document. Khi merge nhiều file, tool cần giữ hoặc viết lại $ref tới vị trí component mới.

Một input cũng có thể tham chiếu file ngoài:

~~~yaml
$ref: "../common/errors.yaml#/components/schemas/ApiProblem"
~~~

Nếu file tham chiếu nằm trong danh sách inputs, merge tool có thể rewrite reference tới component đã nhập vào document tổng hợp. Nếu file không được khai báo, resolveExternalReferences có thể yêu cầu tool tải file và lấy component được tham chiếu.

Không bật resolve external references với input không tin cậy. Việc theo $ref có thể mở rộng tập file hoặc URL mà tool đọc. Giữ inputRoot để giới hạn file local được đọc và chỉ xử lý nguồn spec đã được review.

## 7. Servers và Security khi hợp nhất

### 7.1. Chọn servers của API Gateway

Mỗi microservice có thể công bố server riêng:

~~~yaml
servers:
  - url: https://catalog.internal.example.com
~~~

~~~yaml
servers:
  - url: https://billing.internal.example.com
~~~

Nhưng document tổng hợp cho gateway có thể cần:

~~~yaml
servers:
  - url: https://api.example.com/platform
    description: Public API Gateway
~~~

Vì vậy, merge strategy mặc định giữ servers từ input đầu tiên là một quyết định quan trọng. Hãy đặt gateway-level document đầu tiên hoặc cấu hình strategy để giữ/ghép servers theo yêu cầu. Không ghép tất cả server URL một cách máy móc nếu client chỉ nên gọi qua gateway.

### 7.2. Security schemes có thể trùng tên nhưng khác ý nghĩa

Ví dụ cả Catalog và Billing đều dùng scheme tên bearerAuth, nhưng một service yêu cầu audience khác hoặc một service dùng API key riêng. Nếu định nghĩa scheme khác nhau, không nên ghi đè im lặng.

Hãy:

1. Kiểm tra từng components.securitySchemes.
2. Chuẩn hóa tên scheme khi chúng thật sự có cùng semantics.
3. Đổi tên scheme theo service nếu cấu hình khác nhau.
4. Kiểm tra security ở root và operation sau khi merge.
5. Xác minh API Gateway thực thi cùng chính sách được mô tả.

Merge security scheme không tự tạo authentication, token exchange hay authorization trên gateway.

## 8. Thông tin info và version của document tổng hợp

Mỗi service có thể có:

~~~yaml
info:
  title: Catalog API
  version: 2.1.0
~~~

~~~yaml
info:
  title: Billing API
  version: 4.0.0
~~~

Một merged document chỉ có một info object. Không thể giữ nguyên hai info.title và hai info.version ở cùng cấp như thể document vẫn là hai file.

Đối với gateway facade, chọn metadata đại diện:

~~~yaml
info:
  title: Platform API
  version: 1.0.0
  description: Hợp đồng tổng hợp cho các API được công bố qua Platform Gateway.
~~~

info.version của merged document nên biểu diễn phiên bản API contract facade. Phiên bản của từng service cần được lưu trong release metadata, API catalog, hoặc vendor extension được quy ước thống nhất. Không lấy version của một service rồi mặc định đó là version của toàn bộ platform.

Các input cũng cần cùng OpenAPI major.minor version theo yêu cầu của công cụ merge. Đây là phiên bản ngôn ngữ đặc tả, độc lập với info.version của từng API.

## 9. Khi nào chọn list, khi nào chọn merge?

| Nhu cầu | Cách phù hợp | Lý do |
|---|---|---|
| Monolith có API public và admin | GroupedOpenApi | Mỗi audience có document riêng và path filter riêng. |
| Developer portal cho nhiều microservice độc lập | Swagger UI urls | Dễ chọn từng service; không cần tạo một contract facade. |
| API Gateway công bố một surface thống nhất | Merge OpenAPI | Một document phản ánh các paths mà gateway thực sự expose. |
| Một service muốn cung cấp cả JSON và YAML | Springdoc endpoints | Cùng một document có hai định dạng xuất. |
| Muốn gộp $ref bên ngoài trong một document gốc | Bundling tool | Đây là xử lý reference trong một root spec, không phải ghép nhiều API độc lập. |

Nếu chỉ cần một giao diện chung để xem API, không cần merge. Nếu consumer cần một contract duy nhất để generate SDK hoặc validate gateway, Swagger UI dropdown không đáp ứng mục tiêu đó.

## 10. Kiểm tra kết quả sau khi group, list hoặc merge

### 10.1. Kiểm tra từng group

Gọi endpoint của từng group:

~~~bash
curl -fsS http://localhost:8080/v3/api-docs/catalog \
  -o build/openapi/catalog.json

curl -fsS http://localhost:8080/v3/api-docs/billing \
  -o build/openapi/billing.json
~~~

Kiểm tra paths mỗi file chỉ có operation thuộc group. Nếu có overlap có chủ đích, ghi lại lý do và bảo đảm không lộ endpoint internal.

### 10.2. Kiểm tra Swagger UI configuration

Swagger UI lấy cấu hình tại /v3/api-docs/swagger-config. Khi dùng nhiều URL, kiểm tra cấu hình có:

- Tất cả name và url mong muốn.
- Tên và URL không trùng.
- urlsPrimaryName trỏ tới một entry có thật.
- URL external có thể truy cập từ browser.
- CORS và authentication của các service nguồn được cấu hình phù hợp.

Swagger UI config chỉ chứa danh sách URL; không dùng nó làm bằng chứng rằng paths đã được merge.

### 10.3. Validate merged document

Sau khi merge, chạy validator/linter trên output:

~~~bash
openapi-generator-cli validate \
  -i dist/platform-api.yaml \
  --recommend
~~~

Ngoài validate syntax, cần kiểm tra:

- Mỗi path và method xuất hiện đúng một lần.
- operationId không trùng.
- Mọi $ref đều resolve được.
- Component collision đã được xử lý.
- servers phản ánh gateway URL.
- Security schemes và requirements không bị mất.
- Tất cả input có cùng OpenAPI major.minor version.
- Các path đã rewrite khớp route thật của gateway.

### 10.4. Contract test qua gateway

Một merged document có thể hợp lệ về cú pháp nhưng sai với runtime. Hãy chạy test gọi gateway thật:

- /catalog/products đi tới Catalog service.
- /billing/invoices đi tới Billing service.
- Header authentication được gateway chuyển tiếp đúng.
- Response status, media type và schema khớp merged document.
- Error response từ từng service không bị gateway biến đổi ngoài mô tả.

Nếu gateway rewrite status, header hoặc error payload, merged contract cần mô tả behavior bên ngoài mà consumer thực sự nhìn thấy.

## 11. Những lỗi thường gặp

- **Nhầm GroupedOpenApi với merge**: mỗi group vẫn là một document riêng.
- **Nhầm Swagger UI urls với merge**: Topbar chỉ cho chọn một document để xem.
- **Dùng springdoc.swagger-ui.url cùng urls**: url bị bỏ qua khi urls được cấu hình.
- **Tên hoặc URL trong urls bị trùng**: Swagger UI cần các identifier duy nhất.
- **Không bật CORS cho spec external**: browser không tải được tài liệu từ service khác origin.
- **Cho rằng group name bảo vệ tài liệu**: cần Spring Security/network policy.
- **Merge path trùng nhưng bỏ qua warning**: operation có thể bị mất hoặc bị thay thế.
- **Trùng component name nhưng schema khác nhau**: $ref có thể trỏ sai nếu không rename và rewrite.
- **Trùng operationId**: SDK generator có thể tạo method trùng hoặc thất bại.
- **Giữ server URL nội bộ trong merged spec**: client bị hướng tới host không thể truy cập.
- **Gộp security schemes không kiểm tra**: requirement có thể đổi nghĩa hoặc tham chiếu sai.
- **Gộp info.version của một service làm version toàn platform**: metadata facade không phản ánh release tổng hợp.
- **Trộn OpenAPI 3.0 và 3.1**: tool merge có thể từ chối do khác major.minor.
- **Bật resolve external refs với nguồn không tin cậy**: tool có thể đọc file hoặc URL ngoài phạm vi mong muốn.
- **Cho rằng merge tạo gateway routing**: vẫn phải cấu hình và kiểm thử runtime gateway.
- **Chỉ validate cú pháp**: spec có thể hợp lệ nhưng sai path hoặc server behavior thực tế.

## 12. Quy trình phân phối tài liệu cho hệ thống nhiều service

1. **Phân loại API**: monolith group, microservice độc lập hay gateway facade.
2. **Chọn topology tài liệu**: một document, nhiều group, danh sách UI hay merged spec.
3. **Xuất tài liệu từng service**: lấy JSON/YAML từ springdoc và lưu artifact có version.
4. **Chuẩn hóa OpenAPI version**: các input merge cần cùng major.minor.
5. **Chuẩn hóa path và server**: xác định gateway prefix và public server URL.
6. **Xử lý component/security collisions**: đặt tên, merge hoặc fail để review.
7. **Tạo merged document**: chạy merge tool với config được quản lý trong source control.
8. **Validate và lint**: kiểm tra $ref, operationId, paths, components, servers và security.
9. **Test runtime**: gọi API qua gateway để đối chiếu merged contract.
10. **Publish**: phát hành spec tổng hợp cùng release metadata của các service nguồn.

## 13. Checklist review

- [ ] Đã xác định mục tiêu là chia group, liệt kê tài liệu hay merge thật sự.
- [ ] Mỗi GroupedOpenApi có group name duy nhất.
- [ ] Group path/package filters phản ánh đúng audience.
- [ ] Tài liệu nội bộ được bảo vệ bằng security policy.
- [ ] Swagger UI urls có name và URL duy nhất.
- [ ] urlsPrimaryName trỏ tới một document có thật.
- [ ] CORS cho external spec đã được cấu hình.
- [ ] Nếu merge, các input có cùng OpenAPI major.minor version.
- [ ] Path collision có chính sách rõ ràng và không làm mất operation.
- [ ] Component collision được rename/deduplicate có kiểm soát.
- [ ] Mọi $ref resolve được sau merge.
- [ ] operationId duy nhất trong merged document.
- [ ] servers và path khớp public gateway.
- [ ] Security schemes và requirements vẫn đúng semantics.
- [ ] info.version đại diện cho facade contract, không nhầm version service.
- [ ] Merged document được validate, diff và lưu thành artifact.
- [ ] Gateway contract được kiểm thử với request/response runtime thật.

## 14. Tài liệu tham khảo

- [springdoc-openapi – Multiple OpenAPI definitions and GroupedOpenApi](https://springdoc.org/index.html#how-can-i-define-multiple-openapi-definitions-in-one-spring-boot-project)
- [springdoc-openapi – Configuration properties](https://springdoc.org/properties.html)
- [springdoc-openapi – Aggregating external OpenAPI endpoints](https://springdoc.org/index.html#how-can-i-aggregate-external-endpoints-exposing-openapi-3-spec-inside-one-single-application)
- [Swagger UI – Configuration: url and urls](https://swagger.io/docs/open-source-tools/swagger-ui/usage/configuration/)
- [openapi-merge-cli – Getting started and configuration](https://github.com/robertmassaioli/openapi-merge/blob/main/packages/openapi-merge-cli/README.md)
- [openapi-merge – Merging behaviour and conflict handling](https://robertmassaioli.github.io/openapi-merge/library/merging-behaviour)
- [openapi-merge – CLI configuration reference](https://robertmassaioli.github.io/openapi-merge/cli/configuration)
- [OpenAPI Specification](https://spec.openapis.org/oas/)

Liệt kê nhiều tài liệu giúp người dùng chọn và xem từng API độc lập; merge tạo một contract tổng hợp mới. Hãy dùng GroupedOpenApi để phân chia tài liệu trong ứng dụng, swagger-ui.urls để làm catalog nhiều service, và merge tool khi cần một document cho gateway hoặc SDK. Trước khi phân phối merged spec, xử lý path/component/operationId conflicts, $ref, servers và security rồi kiểm thử nó với routing HTTP thật.
