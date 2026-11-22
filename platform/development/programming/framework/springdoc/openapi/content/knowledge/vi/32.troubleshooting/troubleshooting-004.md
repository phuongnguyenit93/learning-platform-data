# Đặc tả OpenAPI rỗng do điều kiện quét hoặc bộ lọc nhóm

Khi mở `/v3/api-docs` hoặc tài liệu của một group mà nhận được JSON hợp lệ nhưng `paths` rỗng, springdoc-openapi thường đã chạy được nhưng không tìm thấy endpoint phù hợp với phạm vi quét hiện tại. Nguyên nhân hay gặp là controller chưa được Spring đăng ký, cấu hình quét package hoặc URL quá hẹp, bộ lọc của `GroupedOpenApi` loại hết endpoint, hoặc controller/phương thức bị ẩn bằng annotation.

Hãy kiểm tra JSON do API docs trả về trước, sau đó lần lượt xác minh mapping của Spring, điều kiện quét toàn cục và bộ lọc của từng group. Cách làm này giúp xác định chính xác tầng đang loại endpoint thay vì thay đổi nhiều cấu hình cùng lúc.

## 1. Phân biệt đặc tả rỗng với lỗi truy cập tài liệu

Swagger UI không hiển thị endpoint chưa đủ để kết luận đặc tả rỗng. Trước tiên gọi trực tiếp API docs và kiểm tra mã HTTP cùng nội dung JSON.

| Biểu hiện | Ý nghĩa cần kiểm tra |
| --- | --- |
| HTTP `200`, có `openapi` nhưng `paths` là `{}` | Tài liệu được tạo nhưng không có endpoint nào vượt qua các điều kiện quét hoặc lọc. |
| HTTP `404` tại `/v3/api-docs` | Kiểm tra starter, đường dẫn API docs, cấu hình `springdoc.api-docs.enabled` và context path. Đây không phải bằng chứng rằng bộ lọc trả về đặc tả rỗng. |
| HTTP `401` hoặc `403` | Request tới tài liệu bị bảo vệ bởi Spring Security hoặc gateway. Xử lý quyền truy cập trước khi phân tích nội dung đặc tả. |
| `/v3/api-docs` có endpoint nhưng `/v3/api-docs/{group}` rỗng | Tập trung vào cấu hình của group tương ứng và các điều kiện toàn cục đang áp dụng. |
| JSON có endpoint nhưng Swagger UI trống hoặc báo lỗi | Kiểm tra URL JSON mà UI đang tải, cấu hình UI, lỗi mạng và quyền truy cập của trình duyệt. |

Ví dụ kiểm tra tài liệu mặc định:

```bash
curl -i http://localhost:8080/v3/api-docs
curl -sS http://localhost:8080/v3/api-docs \
  | jq '{openapi, pathCount: ((.paths // {}) | length), paths: ((.paths // {}) | keys)}'
```

Với group tên `public`, kiểm tra riêng endpoint tương ứng:

```bash
curl -i http://localhost:8080/v3/api-docs/public
curl -sS http://localhost:8080/v3/api-docs/public \
  | jq '{openapi, pathCount: ((.paths // {}) | length), paths: ((.paths // {}) | keys)}'
```

Nếu không có `jq`, mở JSON và tìm thuộc tính `paths`. Một tài liệu có `paths: {}` khác với trường hợp endpoint không tồn tại hoặc request không được phép truy cập.

## 2. Hiểu những điều kiện quyết định endpoint được đưa vào tài liệu

springdoc-openapi lấy thông tin từ các handler mà ứng dụng Spring đã đăng ký. Một phương thức Java chỉ được viết trong project chưa đủ để xuất hiện trong OpenAPI: controller phải được tạo thành bean, phương thức phải có mapping HTTP được Spring nhận diện và endpoint phải vượt qua các điều kiện lọc.

Các lớp điều kiện thường gặp gồm:

1. **Điều kiện đăng ký bean:** controller phải nằm trong phạm vi component scan hoặc được khai báo bean theo cấu hình phù hợp. `@Profile`, `@ConditionalOnProperty` và các điều kiện tạo bean khác có thể khiến controller không tồn tại trong môi trường đang chạy.
2. **Điều kiện package:** `springdoc.packages-to-scan` hoặc `packagesToScan(...)` giới hạn package được đưa vào tài liệu. Package cần đối chiếu là package của controller, không phải package của service mà controller gọi.
3. **Điều kiện path:** `springdoc.paths-to-match` hoặc `pathsToMatch(...)` chỉ nhận các mapping khớp pattern đã cấu hình. Pattern sai tiền tố hoặc sai cấu trúc có thể loại toàn bộ endpoint.
4. **Điều kiện loại trừ:** `packages-to-exclude`, `paths-to-exclude`, `packagesToExclude(...)` và `pathsToExclude(...)` có thể loại endpoint vốn đã khớp điều kiện bao gồm.
5. **Điều kiện ẩn:** `@Hidden` trên controller hoặc `@Operation(hidden = true)` trên phương thức có thể làm endpoint không xuất hiện trong đặc tả.
6. **Điều kiện riêng của group:** mỗi bean `GroupedOpenApi` có thể giới hạn package và path khác nhau. Một endpoint có mặt trong group này nhưng vắng ở group khác có thể là kết quả đúng của cấu hình group.

Khi đồng thời cấu hình package và path, hãy kiểm tra cả hai điều kiện. Ví dụ controller thuộc `com.acme.orders.api` nhưng mapping là `/v1/orders`; cấu hình package đúng mà `paths-to-match` chỉ nhận `/admin/**` vẫn không đưa controller đó vào tài liệu.

## 3. Xác minh controller đã được Spring đăng ký

Trước khi sửa cấu hình springdoc, xác minh ứng dụng thực sự có mapping HTTP tương ứng. Một controller thông thường có dạng:

```java
package com.acme.orders.api;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/v1/orders")
public class OrderController {

    @GetMapping
    public String listOrders() {
        return "orders";
    }
}
```

Kiểm tra các điểm sau:

- Lớp có `@RestController`, hoặc có `@Controller` kết hợp với `@ResponseBody` ở lớp/phương thức khi cần trả dữ liệu trực tiếp.
- Phương thức có annotation mapping như `@GetMapping`, `@PostMapping` hoặc `@RequestMapping`.
- Package của controller nằm trong phạm vi component scan. Theo mặc định, `@SpringBootApplication` quét package chứa lớp ứng dụng và các package con; controller nằm ở package ngang hàng hoặc ngoài cây đó cần cấu hình scan phù hợp.
- Profile và điều kiện tạo bean đang hoạt động trong môi trường hiện tại cho phép controller được đăng ký.
- Không có annotation ẩn được đặt ở cấp lớp hoặc phương thức một cách ngoài ý muốn.

Có thể xem log khởi động của Spring MVC để tìm các mapping đã đăng ký. Nếu mapping không tồn tại trong ứng dụng, cần sửa component scan, điều kiện tạo bean hoặc khai báo controller trước. springdoc không thể tạo operation cho handler mà Spring không nhận diện.

## 4. Kiểm tra bộ lọc package và path toàn cục

Các thuộc tính trong cấu hình Spring Boot có thể giới hạn toàn bộ API docs. Ví dụ:

```yaml
springdoc:
  api-docs:
    enabled: true
  packages-to-scan: com.acme.orders.api
  paths-to-match: /v1/**
```

Với cấu hình trên, controller cần thuộc package được chọn và mapping cần khớp `/v1/**`. Nếu controller thực tế nằm trong `com.acme.billing.api` hoặc mapping bắt đầu bằng `/api/v1/`, điều kiện tương ứng sẽ không khớp.

Đối chiếu cấu hình với mapping thực tế, sau đó nới đúng điều kiện bị sai. Ví dụ, nếu API nằm dưới `/api/v1/orders`, có thể điều chỉnh thành:

```yaml
springdoc:
  packages-to-scan: com.acme.orders.api
  paths-to-match: /api/v1/**
```

Nếu ứng dụng có nhiều package API, khai báo đầy đủ các package cần tài liệu theo cú pháp thuộc tính mà phiên bản springdoc đang sử dụng. Không thêm package rộng hơn chỉ để làm JSON có nội dung, vì thao tác đó có thể vô tình đưa API nội bộ vào tài liệu công khai.

Đồng thời rà soát các điều kiện loại trừ. Một cấu hình `packages-to-exclude` hoặc `paths-to-exclude` quá rộng có thể loại đúng package/path mà điều kiện bao gồm vừa chọn. Khi điều tra, tạm thời bỏ từng điều kiện loại trừ trong môi trường phát triển để xác định tác động; sau khi tìm được nguyên nhân, khôi phục danh sách loại trừ chính xác.

## 5. Kiểm tra cấu hình của GroupedOpenApi

`GroupedOpenApi` tạo tài liệu riêng theo tên group. Ví dụ:

```java
import org.springdoc.core.models.GroupedOpenApi;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class OpenApiGroupsConfig {

    @Bean
    GroupedOpenApi publicApi() {
        return GroupedOpenApi.builder()
                .group("public")
                .packagesToScan("com.acme.publicapi")
                .pathsToMatch("/api/public/**")
                .build();
    }
}
```

Với ví dụ này, tài liệu của group được truy cập tại `/v3/api-docs/public`. Nếu controller nằm ở `com.acme.orders.api` hoặc mapping thực tế là `/v1/orders/**`, group `public` không nhận controller đó. Hãy kiểm tra đồng thời tên group, package, path và các điều kiện loại trừ của chính bean này.

Một số tình huống thường gây nhầm lẫn:

- Đọc `/v3/api-docs` trong khi cần kiểm tra `/v3/api-docs/public`, hoặc ngược lại.
- Swagger UI đang chọn group khác với group vừa cấu hình.
- Tên group trong URL không trùng với giá trị `.group("...")`.
- Group có cả `packagesToScan(...)` và `pathsToMatch(...)`, nhưng chỉ một trong hai điều kiện được đối chiếu.
- Nhiều bean group có bộ lọc gần giống nhau; endpoint thuộc group khác nên không xuất hiện trong group đang xem.
- Bộ lọc toàn cục và bộ lọc group cùng giới hạn phạm vi. Kiểm tra tất cả cấu hình đang có hiệu lực thay vì giả định bộ lọc ở một nơi sẽ ghi đè nơi còn lại.

Để khoanh vùng, so sánh `paths` của tài liệu mặc định với `paths` của từng group. Nếu endpoint có trong tài liệu mặc định nhưng vắng ở một group, hãy tập trung vào bộ lọc group. Nếu mọi tài liệu đều rỗng, kiểm tra component scan, controller mapping và các điều kiện toàn cục trước.

## 6. Kiểm tra profile và cấu hình thực tế khi chạy

File `application.yml` có thể không phải nguồn cấu hình cuối cùng. Spring Boot có thể nạp thêm `application-{profile}.yml`, biến môi trường, tham số dòng lệnh hoặc cấu hình từ nền tảng triển khai. Một cấu hình đúng ở máy cá nhân vẫn có thể bị ghi đè ở môi trường kiểm thử hoặc production.

Khi kiểm tra, hãy xác định:

- Profile đang hoạt động, chẳng hạn `dev`, `test` hoặc `prod`.
- Giá trị hiệu lực của `springdoc.packages-to-scan`, `springdoc.paths-to-match` và các thuộc tính loại trừ.
- Các bean `GroupedOpenApi` được tạo trong profile hiện tại và tên group tương ứng.
- `springdoc.api-docs.enabled` có đang bật hay không.
- Ứng dụng có dùng `server.servlet.context-path` hoặc tiền tố triển khai khiến URL gọi tài liệu khác với URL dự kiến hay không.

Phân biệt hai thuộc tính: `springdoc.api-docs.enabled` điều khiển API docs; `springdoc.swagger-ui.enabled` điều khiển giao diện Swagger UI. Tắt UI không đồng nghĩa JSON API docs bị tắt. Vì vậy, khi UI không mở được, hãy gọi trực tiếp endpoint JSON để xác định lớp gặp lỗi.

Không công khai endpoint quản lý cấu hình hoặc log nhạy cảm chỉ để điều tra. Trong môi trường dùng chung, có thể kiểm tra giá trị cấu hình qua log khởi động có kiểm soát hoặc debugger nội bộ, rồi gỡ thông tin chẩn đoán sau khi hoàn tất.

## 7. Quy trình khoanh vùng theo thứ tự

Thực hiện từng bước và gọi lại API docs sau mỗi thay đổi:

1. Gọi `/v3/api-docs`, ghi nhận mã HTTP và kiểm tra `paths`.
2. Nếu đang điều tra group, gọi đúng `/v3/api-docs/{group}` và xác nhận tên group.
3. Xác minh controller có bean và mapping HTTP trong ứng dụng đang chạy.
4. Đối chiếu package của controller với `packages-to-scan` và các điều kiện loại trừ.
5. Đối chiếu mapping thực tế với `paths-to-match` và `paths-to-exclude`.
6. Kiểm tra `@Hidden`, `@Operation(hidden = true)` và các điều kiện tạo bean theo profile.
7. So sánh cấu hình mặc định với từng `GroupedOpenApi`, đồng thời kiểm tra cấu hình profile/biến môi trường.
8. Sau khi sửa, gọi lại endpoint JSON và xác nhận các path dự kiến đã xuất hiện. Mở Swagger UI sau cùng để kiểm tra trải nghiệm hiển thị.

Ví dụ, nếu `/v3/api-docs` có `/v1/orders` nhưng `/v3/api-docs/public` không có, controller và mapping đã được Spring nhận diện. Lúc này nên sửa bộ lọc của group `public`, chẳng hạn đổi `pathsToMatch("/api/public/**")` thành pattern khớp với mapping thực tế, thay vì thay đổi component scan của toàn ứng dụng.

## 8. Kiểm thử để tránh tái diễn

Nên kiểm tra nội dung của tài liệu trong integration test, không chỉ kiểm tra endpoint trả HTTP `200`. Ví dụ với Spring MVC, MockMvc và Jackson:

```java
MvcResult result = mockMvc.perform(get("/v3/api-docs/public"))
        .andExpect(status().isOk())
        .andReturn();

JsonNode document = objectMapper.readTree(
        result.getResponse().getContentAsString());
JsonNode paths = document.path("paths");

assertThat(paths.size()).isGreaterThan(0);
assertThat(paths.has("/api/public/orders")).isTrue();
```

Điều chỉnh đường dẫn mong đợi theo mapping thật của ứng dụng. Với nhiều group, tạo kiểm thử riêng cho từng group và xác nhận ít nhất một endpoint đại diện thuộc phạm vi của group đó. Nếu group có trách nhiệm loại API nội bộ, cũng nên kiểm tra endpoint nội bộ không xuất hiện trong tài liệu công khai.

Khi thay đổi package controller, URL mapping, profile hoặc cấu hình group, chạy lại integration test API docs trong profile tương ứng. Nhờ đó, thay đổi bộ lọc vô tình làm rỗng tài liệu sẽ được phát hiện ngay trong CI.

## 9. Những lỗi cấu hình thường gặp

| Cấu hình hoặc thay đổi | Vì sao tài liệu có thể rỗng | Cách xử lý |
| --- | --- | --- |
| `packages-to-scan` trỏ tới package service | Controller ở package khác nên không được chọn. | Dùng package chứa controller thực tế. |
| `paths-to-match` là `/admin/**` nhưng mapping là `/api/**` | Không có mapping nào khớp pattern. | Sửa pattern theo URL mapping đã đăng ký. |
| `packagesToScan` đúng nhưng `pathsToMatch` sai | Endpoint không thỏa toàn bộ điều kiện group đang khai báo. | Đối chiếu cả package và path. |
| `paths-to-exclude` bao phủ toàn bộ path được chọn | Các endpoint bị loại sau khi chọn. | Thu hẹp hoặc bỏ pattern loại trừ không cần thiết. |
| Controller nằm ngoài component scan | Spring không tạo handler cho controller. | Điều chỉnh vị trí lớp ứng dụng hoặc component scan. |
| Đặt `@Hidden` trên controller dùng chung | Toàn bộ operation của controller bị ẩn khỏi tài liệu. | Chỉ ẩn đúng controller/phương thức thực sự không muốn công bố. |
| UI trỏ tới group sai | JSON của group đang chọn có thể rỗng dù group khác có endpoint. | Kiểm tra URL JSON và tên group đang chọn. |

Không nên xóa toàn bộ bộ lọc trong production như một cách sửa lâu dài. Bộ lọc thường thể hiện ranh giới giữa API công khai và API nội bộ; cần sửa điều kiện cụ thể và kiểm thử lại phạm vi được công bố.

## Kết luận

Đặc tả có `paths` rỗng thường là dấu hiệu không có handler nào vượt qua chuỗi điều kiện đăng ký và lọc. Hãy bắt đầu từ JSON API docs, xác nhận mapping Spring, rồi kiểm tra package, path, annotation ẩn và cấu hình riêng của group. Khi integration test xác nhận đúng endpoint xuất hiện trong từng group, cấu hình springdoc-openapi sẽ ổn định hơn qua các lần thay đổi controller và môi trường triển khai.
