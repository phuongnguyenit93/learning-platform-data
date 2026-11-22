# Lọc theo packagesToScan và packagesToExclude

Trong một ứng dụng Spring Boot, controller thường được chia theo miền nghiệp vụ hoặc lớp chức năng: khách hàng, đơn hàng, thanh toán, quản trị và tích hợp nội bộ. Khi ứng dụng có nhiều nhóm API, một tài liệu OpenAPI duy nhất có thể chứa quá nhiều endpoint hoặc làm lộ những operation không dành cho người tích hợp bên ngoài. **springdoc-openapi** cho phép lọc controller theo package bằng **packagesToScan** và **packagesToExclude**, từ đó tạo các tài liệu OpenAPI có phạm vi rõ ràng.

Hai thuộc tính này có thể được cấu hình ở phạm vi toàn cục hoặc riêng cho từng nhóm tài liệu:

- **springdoc.packages-to-scan** chọn các package cần quét cho tài liệu mặc định.
- **springdoc.packages-to-exclude** loại các package khỏi phạm vi quét toàn cục.
- **springdoc.group-configs[n].packages-to-scan** và **packages-to-exclude** cấu hình phạm vi package của một group khai báo trong application configuration.
- **GroupedOpenApi.Builder.packagesToScan(...)** và **packagesToExclude(...)** cấu hình package bằng Java.

Lọc package chỉ quyết định controller nào được đưa vào tài liệu. Nó không đăng ký bean, thay đổi URL, ngăn client gọi endpoint hoặc thay thế Spring Security.

## 1. Vì sao cần lọc theo package?

Giả sử một ứng dụng bán hàng có cấu trúc package:

~~~text
com.example.shop
├── api
│   ├── customer
│   │   ├── CustomerController.java
│   │   └── AddressController.java
│   ├── order
│   │   └── OrderController.java
│   └── admin
│       └── AdminOrderController.java
├── internal
│   ├── health
│   │   └── InternalHealthController.java
│   └── integration
│       └── PartnerCallbackController.java
└── application
    └── ...
~~~

Các controller trên có thể thuộc những nhóm người dùng tài liệu khác nhau:

- Đối tác tích hợp chỉ cần API khách hàng và đơn hàng.
- Nhóm quản trị cần thêm các endpoint quản lý.
- Endpoint nội bộ không nên xuất hiện trong tài liệu công khai.

Nếu để springdoc quét toàn bộ controller, tài liệu mặc định có thể chứa cả endpoint nội bộ. Lọc theo package giúp tạo phạm vi ban đầu theo cách tổ chức mã nguồn.

Lọc package đặc biệt hữu ích khi package phản ánh ranh giới module ổn định. Nếu cấu trúc package không phản ánh ranh giới API, cân nhắc dùng **pathsToMatch** và **pathsToExclude** theo URL hoặc kết hợp cả hai bộ lọc.

## 2. Phân biệt packagesToScan và packagesToExclude

**packagesToScan** xác định các package được đưa vào phạm vi quét. **packagesToExclude** loại những package không được công bố trong tài liệu.

| Thuộc tính | Mục đích | Ví dụ |
| --- | --- | --- |
| **packagesToScan** | Chọn package chứa controller cần mô tả | **com.example.shop.api.customer** |
| **packagesToExclude** | Loại package khỏi tài liệu | **com.example.shop.api.admin** |

Có thể hình dung phạm vi được chọn như sau:

1. Bắt đầu từ các controller mà Springdoc có thể nhận diện.
2. Giữ controller thuộc package được chọn bởi **packagesToScan**; nếu không giới hạn danh sách include, phạm vi mặc định có thể bao phủ toàn bộ package.
3. Loại controller thuộc package được chỉ định trong **packagesToExclude**.
4. Nếu group còn cấu hình bộ lọc URL như **pathsToMatch** hoặc **pathsToExclude**, áp dụng thêm các điều kiện path của group.

Khi package xuất hiện trong cả danh sách include và exclude, hãy thiết kế cấu hình sao cho ý định không mơ hồ và xác minh kết quả ở phiên bản springdoc đang dùng. Cách dễ bảo trì là chọn một package cha làm phạm vi include rồi loại các package con không công bố.

Tài liệu thuộc tính springdoc v2 ghi nhận:

- **springdoc.packages-to-scan** có mặc định là dấu sao (*).
- **springdoc.packages-to-exclude** mặc định không có danh sách loại trừ.
- Các thuộc tính tương ứng cũng có trong từng phần tử **springdoc.group-configs**.

Vì vậy, nếu không cấu hình lọc package, tài liệu mặc định thường quét tất cả package controller được springdoc nhận diện.

## 3. Lọc package cho tài liệu mặc định

Có thể cấu hình trực tiếp trong **application.yml**:

~~~yaml
springdoc:
  packages-to-scan:
    - com.example.shop.api.customer
    - com.example.shop.api.order
  packages-to-exclude:
    - com.example.shop.api.admin
    - com.example.shop.internal
~~~

Hoặc dùng **application.properties**:

~~~properties
springdoc.packages-to-scan=com.example.shop.api.customer,com.example.shop.api.order
springdoc.packages-to-exclude=com.example.shop.api.admin,com.example.shop.internal
~~~

Trong ví dụ, tài liệu OpenAPI mặc định chỉ tập trung vào controller thuộc các package khách hàng và đơn hàng, đồng thời loại các package quản trị và nội bộ.

Endpoint tài liệu mặc định thường là:

~~~text
GET /v3/api-docs
~~~

Nếu ứng dụng đã đổi **springdoc.api-docs.path** hoặc có context path, sử dụng URL tương ứng với cấu hình đó.

Các thuộc tính toàn cục phù hợp khi ứng dụng chỉ cần một phạm vi tài liệu mặc định hoặc khi mọi tài liệu đều cần cùng một giới hạn nền. Nếu mỗi nhóm API có phạm vi khác nhau, nên cấu hình package ở từng group.

## 4. Lọc package riêng cho từng document group bằng application.yml

Springdoc cho phép khai báo nhiều group trong **springdoc.group-configs**. Không cần tạo bean **GroupedOpenApi** khi dùng cách khai báo này.

Ví dụ tạo hai tài liệu riêng cho khách hàng và quản trị:

~~~yaml
springdoc:
  group-configs:
    - group: customer-api
      display-name: Customer API
      packages-to-scan:
        - com.example.shop.api.customer
        - com.example.shop.api.order
      packages-to-exclude:
        - com.example.shop.api.customer.internal

    - group: admin-api
      display-name: Admin API
      packages-to-scan:
        - com.example.shop.api.admin
      packages-to-exclude:
        - com.example.shop.api.admin.maintenance
~~~

Kết quả là hai tài liệu có phạm vi package khác nhau:

| Group | Package được chọn | Package bị loại |
| --- | --- | --- |
| **customer-api** | **api.customer**, **api.order** | **api.customer.internal** |
| **admin-api** | **api.admin** | **api.admin.maintenance** |

Theo bảng thuộc tính springdoc v2, **packages-to-scan** của từng group cũng có mặc định là dấu sao (*), còn **packages-to-exclude** mặc định rỗng. Vì vậy, nếu một group không khai báo phạm vi package, group đó có thể chứa controller từ toàn bộ ứng dụng theo các bộ lọc còn lại. Hãy khai báo include rõ ràng cho từng group khi muốn tạo tài liệu có phạm vi hẹp.

Theo cấu hình mặc định, tài liệu từng group có thể được truy cập tại:

~~~text
GET /v3/api-docs/customer-api
GET /v3/api-docs/admin-api
~~~

Tên group được dùng trong URL, vì vậy nên đặt tên ngắn gọn, ổn định và duy nhất. **display-name** phục vụ tên hiển thị trong một số giao diện tích hợp; nó không thay thế định danh **group**.

Có thể khai báo group bằng cú pháp properties tương đương:

~~~properties
springdoc.group-configs[0].group=customer-api
springdoc.group-configs[0].display-name=Customer API
springdoc.group-configs[0].packages-to-scan=com.example.shop.api.customer,com.example.shop.api.order
springdoc.group-configs[0].packages-to-exclude=com.example.shop.api.customer.internal

springdoc.group-configs[1].group=admin-api
springdoc.group-configs[1].display-name=Admin API
springdoc.group-configs[1].packages-to-scan=com.example.shop.api.admin
springdoc.group-configs[1].packages-to-exclude=com.example.shop.api.admin.maintenance
~~~

Khi dùng group config trong file cấu hình, không cần đồng thời tạo bean **GroupedOpenApi** cho cùng một group. Tránh khai báo hai nguồn cấu hình trùng tên khiến việc xác định phạm vi tài liệu khó kiểm soát.

## 5. Lọc package bằng GroupedOpenApi trong Java

Nếu muốn cấu hình group bằng Java, tạo bean **GroupedOpenApi** và truyền danh sách package vào builder:

~~~java
import org.springdoc.core.models.GroupedOpenApi;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class OpenApiGroupConfiguration {

    @Bean
    GroupedOpenApi customerApi() {
        return GroupedOpenApi.builder()
            .group("customer-api")
            .packagesToScan(
                "com.example.shop.api.customer",
                "com.example.shop.api.order"
            )
            .packagesToExclude(
                "com.example.shop.api.customer.internal"
            )
            .build();
    }

    @Bean
    GroupedOpenApi adminApi() {
        return GroupedOpenApi.builder()
            .group("admin-api")
            .packagesToScan("com.example.shop.api.admin")
            .packagesToExclude(
                "com.example.shop.api.admin.maintenance"
            )
            .build();
    }
}
~~~

Trong springdoc v2, **GroupedOpenApi** thuộc package **org.springdoc.core.models**. Với springdoc v1, package Java của lớp này khác; hãy dùng import phù hợp với major version của dự án. Các phương thức builder thường dùng gồm:

- **group(...)**: đặt tên group.
- **packagesToScan(...)**: chọn package.
- **packagesToExclude(...)**: loại package.
- **pathsToMatch(...)**: chọn URL path.
- **pathsToExclude(...)**: loại URL path.
- **build()**: tạo cấu hình group.

Nếu ứng dụng cần điều kiện lọc động hoặc cấu hình được xây dựng từ profile, có thể tạo bean theo cấu hình Spring. Dù chọn application.yml hay Java config, nên giữ một nguồn cấu hình rõ ràng cho mỗi group.

## 6. Kết hợp package filter với path filter

Package và path giải quyết hai câu hỏi khác nhau:

- Package filter: controller được khai báo trong vùng mã nguồn nào?
- Path filter: endpoint có URL bắt đầu hoặc khớp với mẫu nào?

Springdoc hỗ trợ kết hợp cả hai. Ví dụ, chỉ đưa controller thuộc package khách hàng vào tài liệu và chỉ lấy endpoint dưới **/api/v1/**:

~~~java
@Bean
GroupedOpenApi customerV1Api() {
    return GroupedOpenApi.builder()
        .group("customer-v1")
        .packagesToScan("com.example.shop.api.customer")
        .pathsToMatch("/api/v1/**")
        .pathsToExclude("/api/v1/internal/**")
        .build();
}
~~~

Hoặc trong YAML:

~~~yaml
springdoc:
  group-configs:
    - group: customer-v1
      packages-to-scan:
        - com.example.shop.api.customer
      paths-to-match:
        - /api/v1/**
      paths-to-exclude:
        - /api/v1/internal/**
~~~

Một controller phải nằm trong phạm vi package đã chọn và có path phù hợp với điều kiện URL thì operation mới thuộc group. Nếu một controller nằm đúng package nhưng URL không khớp **paths-to-match**, operation đó sẽ không được đưa vào group. Ngược lại, path đúng nhưng controller nằm ngoài package đã chọn cũng không được đưa vào.

Không dùng tên URL như **/api/customer/** làm giá trị **packagesToScan**. Đó là mẫu path, cần đặt vào **pathsToMatch**. Package là tên namespace Java, ví dụ **com.example.shop.api.customer**.

## 7. Hiểu đúng ranh giới package được lọc

Package filter tập trung vào controller và handler mà springdoc thu thập. Nó không có nghĩa tất cả class nằm ngoài package được chọn đều biến mất khỏi OpenAPI.

Ví dụ:

~~~java
package com.example.shop.api.customer;

@RestController
class CustomerController {

    @GetMapping("/api/customers/{id}")
    CustomerView find(@PathVariable String id) {
        return customerService.find(id);
    }
}
~~~

DTO có thể nằm ở package dùng chung:

~~~java
package com.example.shop.contract.customer;

public record CustomerView(
    String id,
    String displayName
) {}
~~~

Khi controller được chọn vào group, schema của **CustomerView** vẫn cần xuất hiện nếu operation tham chiếu đến kiểu này. Package filter không phải bộ lọc độc lập để xóa mọi schema theo package của DTO.

Tương tự, việc loại package controller khỏi tài liệu không xóa bean Spring và không thay đổi component scan của ứng dụng. Controller vẫn có thể được đăng ký và endpoint vẫn có thể gọi được nếu Spring MVC/WebFlux và bảo mật cho phép.

## 8. Quy tắc tổ chức package để lọc dễ bảo trì

Một cấu trúc package tốt giúp cấu hình tài liệu rõ ràng:

~~~text
com.example.shop.api
├── public
│   ├── customer
│   ├── order
│   └── catalog
├── partner
│   ├── fulfillment
│   └── payment
├── admin
└── internal
    ├── health
    └── maintenance
~~~

Cấu hình có thể chọn package cha **com.example.shop.api.public** hoặc từng package con. Nếu chọn package cha, hãy xác minh các package con không mong muốn có bị đưa vào theo quy tắc lọc của phiên bản springdoc đang dùng hay không; dùng **packagesToExclude** để loại rõ các vùng không công bố.

Các nguyên tắc nên áp dụng:

1. Đặt controller theo miền API hoặc audience, không gom mọi controller vào một package lớn không có ranh giới.
2. Đặt controller nội bộ ở package riêng để dễ loại khỏi tài liệu.
3. Dùng tên package đầy đủ, đúng chữ hoa/chữ thường.
4. Không phụ thuộc vào wildcard package nếu hành vi đó không được phiên bản thư viện xác nhận.
5. Dùng package filter cho ranh giới mã nguồn và path filter cho ranh giới URL.
6. Giữ package cấu hình đồng bộ khi chuyển controller sang package khác.

Nếu một controller chứa nhiều endpoint cho nhiều audience khác nhau, package filter không thể tách từng method trong cùng lớp theo package. Khi đó dùng path filter, tách controller hoặc dùng customizer phù hợp.

## 9. Ví dụ phân chia tài liệu theo miền nghiệp vụ

Một ứng dụng có ba miền API:

| Miền | Package | Group |
| --- | --- | --- |
| Khách hàng | **com.example.shop.api.customer** | **customer-api** |
| Đơn hàng | **com.example.shop.api.order** | **order-api** |
| Đối tác vận chuyển | **com.example.shop.api.partner.shipping** | **shipping-partner-api** |

Có thể cấu hình trong application.yml:

~~~yaml
springdoc:
  group-configs:
    - group: customer-api
      display-name: Customer API
      packages-to-scan:
        - com.example.shop.api.customer

    - group: order-api
      display-name: Order API
      packages-to-scan:
        - com.example.shop.api.order

    - group: shipping-partner-api
      display-name: Shipping Partner API
      packages-to-scan:
        - com.example.shop.api.partner.shipping
      packages-to-exclude:
        - com.example.shop.api.partner.shipping.internal
~~~

Mỗi group tạo một tài liệu độc lập:

~~~text
/v3/api-docs/customer-api
/v3/api-docs/order-api
/v3/api-docs/shipping-partner-api
~~~

Điều này giúp nhóm tích hợp tải đúng hợp đồng họ cần. Tuy nhiên, nếu một operation cần xuất hiện trong nhiều tài liệu, có thể chọn cùng package trong nhiều group hoặc thiết kế phạm vi group dựa trên cả package và path. Việc một controller xuất hiện trong nhiều tài liệu không có nghĩa endpoint runtime được tạo thành nhiều bản.

## 10. Kiểm tra kết quả lọc package

Sau khi cấu hình, khởi động lại ứng dụng để Spring nạp cấu hình mới. Lấy tài liệu mặc định và từng group:

~~~bash
curl -sS http://localhost:8080/v3/api-docs -o default-openapi.json
curl -sS http://localhost:8080/v3/api-docs/customer-api -o customer-openapi.json
curl -sS http://localhost:8080/v3/api-docs/admin-api -o admin-openapi.json
~~~

Liệt kê các path trong mỗi tài liệu:

~~~bash
jq -r '.paths | keys[]' customer-openapi.json
jq -r '.paths | keys[]' admin-openapi.json
~~~

Kiểm tra nhanh số lượng operation:

~~~bash
jq '[.paths[] | to_entries[]] | length' customer-openapi.json
~~~

Đối chiếu kết quả:

- Group khách hàng chỉ chứa các path thuộc controller trong package khách hàng và các package được chọn thêm.
- Group quản trị không chứa controller thuộc package bị loại.
- DTO dùng chung vẫn có schema nếu operation trong group tham chiếu đến DTO đó.
- Một endpoint có thể xuất hiện ở nhiều group nếu cấu hình include của các group cùng chọn controller đó.
- Tài liệu mặc định và tài liệu group có phạm vi riêng; kiểm tra đúng URL trước khi kết luận cấu hình không có hiệu lực.

Nếu dùng context path, reverse proxy hoặc đã đổi **springdoc.api-docs.path**, hãy điều chỉnh URL truy cập. Nếu endpoint trả 404, kiểm tra tên group, cấu hình API docs và quyền truy cập vào tài liệu.

## 11. Kiểm thử tự động ranh giới của từng group

Có thể dùng MockMvc để kiểm tra endpoint tài liệu của group và xác nhận path được chọn hoặc bị loại:

~~~java
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class OpenApiGroupPackageFilterTest {

    @Autowired
    MockMvc mockMvc;

    @Autowired
    ObjectMapper objectMapper;

    @Test
    void customerGroupContainsOnlyExpectedOperations() throws Exception {
        MvcResult result = mockMvc.perform(get("/v3/api-docs/customer-api"))
            .andExpect(status().isOk())
            .andReturn();

        JsonNode openApi = objectMapper.readTree(
            result.getResponse().getContentAsString()
        );
        JsonNode paths = openApi.path("paths");

        assertThat(paths.has("/api/customers/{id}")).isTrue();
        assertThat(paths.has("/api/admin/users")).isFalse();
    }
}
~~~

Các path trong assertion là ví dụ theo API giả định; thay bằng path thực tế của ứng dụng. Kiểm thử nên bao gồm ít nhất một endpoint được chọn, một endpoint bị loại bởi package và một endpoint bị loại bởi path nếu group dùng cả hai loại filter.

Nếu cùng controller được dùng trong nhiều group, viết assertion theo hợp đồng của từng group thay vì giả định mỗi controller chỉ xuất hiện ở một tài liệu.

## 12. Những lỗi thường gặp

**Dùng URL path làm package.** **packagesToScan** nhận tên package Java, không nhận **/api/**. Dùng **pathsToMatch** cho URL.

**Dùng package của DTO thay cho package của controller.** Bộ lọc nhằm chọn controller/handler được mô tả. DTO được tham chiếu từ operation vẫn có thể được tạo schema dù nằm ở package khác.

**Package bị loại vẫn xuất hiện trong tài liệu.** Kiểm tra package thực tế của lớp controller được Spring đăng ký, giá trị cấu hình có đúng chính tả không và group đang truy cập có phải group đã cấu hình hay không.

**Group không có operation.** Kiểm tra **packages-to-scan**, **packages-to-exclude**, **paths-to-match**, **paths-to-exclude** có đang loại toàn bộ controller hay không. Kiểm tra controller có được Spring nhận diện là REST endpoint không.

**Cấu hình toàn cục không thay đổi group như mong muốn.** Nếu mỗi group có phạm vi riêng, khai báo package trực tiếp trong **springdoc.group-configs[n]** hoặc builder của **GroupedOpenApi**.

**Khai báo group trùng ở YAML và Java.** Chọn một cách khai báo cho mỗi group, đặt tên duy nhất và tránh tạo nhiều nguồn cấu hình cùng phạm vi.

**Ẩn tài liệu nhưng nghĩ endpoint đã bị khóa.** Package filter chỉ ảnh hưởng OpenAPI. Dùng Spring Security, gateway hoặc cơ chế phân quyền để bảo vệ endpoint thực tế.

**Controller được chuyển package nhưng tài liệu không cập nhật như dự kiến.** Đồng bộ lại package include/exclude, khởi động lại ứng dụng và kiểm tra đúng endpoint tài liệu.

## 13. Checklist cấu hình packagesToScan và packagesToExclude

- [ ] Xác định package thực tế chứa controller cần công bố.
- [ ] Chọn package cần quét bằng **packagesToScan**.
- [ ] Loại package không công bố bằng **packagesToExclude**.
- [ ] Dùng cấu hình toàn cục cho tài liệu mặc định hoặc cấu hình riêng cho từng group.
- [ ] Chọn application.yml, application.properties hoặc **GroupedOpenApi** làm nguồn cấu hình rõ ràng.
- [ ] Dùng **pathsToMatch**/**pathsToExclude** khi cần lọc theo URL.
- [ ] Đặt tên group duy nhất và ổn định.
- [ ] Không xem package filter là cơ chế bảo mật endpoint.
- [ ] Kiểm tra **/v3/api-docs** và **/v3/api-docs/{group}** sau khi thay đổi.
- [ ] Viết kiểm thử xác nhận operation được chọn và bị loại.

## 14. Kết luận

**packagesToScan** và **packagesToExclude** giúp chia tài liệu OpenAPI theo cấu trúc package của controller. Có thể áp dụng bộ lọc cho tài liệu mặc định, cấu hình riêng trong **springdoc.group-configs** hoặc dùng builder của **GroupedOpenApi**. Khi cần giới hạn đồng thời theo mã nguồn và URL, kết hợp package filter với path filter. Cuối cùng, xác minh các endpoint **/v3/api-docs** của từng group để bảo đảm tài liệu phản ánh đúng phạm vi API mà nhóm người dùng cần tích hợp.

## 15. Nguồn tham khảo

- [Springdoc OpenAPI v2 — Core Properties Reference](https://springdoc.org/v2/core-properties.html): mặc định và ý nghĩa của **springdoc.packages-to-scan**, **springdoc.packages-to-exclude** cùng các thuộc tính package theo group.
- [Springdoc OpenAPI v2 — FAQ](https://springdoc.org/v2/faq.html): tạo nhiều OpenAPI definitions bằng package và path, sử dụng **GroupedOpenApi** hoặc **springdoc.group-configs**.
- [Springdoc OpenAPI v2 — Documentation](https://springdoc.org/v2/): cấu hình springdoc cho các ứng dụng Spring Boot 3.
