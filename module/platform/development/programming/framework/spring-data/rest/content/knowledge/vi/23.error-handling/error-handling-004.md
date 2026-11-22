# HTTP 405 Method Not Allowed và header Allow khi HTTP method bị vô hiệu hóa trong Spring Data REST

## 1. Ý nghĩa của 405 và header Allow

Theo RFC 9110 §15.5.6, `405 Method Not Allowed` xuất hiện khi server nhận biết HTTP method trong request nhưng resource đích không hỗ trợ method đó. Khi trả về 405, origin server **MUST** gửi header response `Allow` chứa danh sách method hiện được resource hỗ trợ. Ví dụ:

```http
HTTP/1.1 405 Method Not Allowed
Allow: GET, HEAD, PUT, DELETE
Content-Type: application/json
```

Ví dụ trên chỉ minh họa định dạng; giá trị thực tế phụ thuộc resource, repository và cấu hình đang chạy. Nếu PATCH đã bị tắt trên item resource thì PATCH không được xuất hiện trong danh sách Allow của resource đó.

`Allow` là thông tin theo từng resource, không phải danh sách method chung của toàn ứng dụng. Danh sách có thể thay đổi theo cấu hình hoặc trạng thái hiện tại. RFC 9110 §10.2.1 cũng quy định giá trị Allow rỗng biểu thị resource hiện không cho phép method nào.

Phân biệt các trạng thái thường gặp:

| Status | Ý nghĩa khi chẩn đoán |
| --- | --- |
| `405` | Method đã được nhận biết nhưng không được resource đích hỗ trợ. Kiểm tra URI, loại resource, repository method và ExposureConfiguration. |
| `501` | Server không nhận biết hoặc không triển khai method được gửi. |
| `404` | Không tìm thấy resource/route, hoặc resource được cấu hình không export. |
| `401` / `403` | Request bị chặn bởi xác thực hoặc phân quyền; đây không phải bằng chứng method đã bị tắt trong Spring Data REST. |
| `400` / `415` | Request body hoặc media type có vấn đề; kiểm tra payload và Content-Type sau khi xác nhận method được hỗ trợ. |

## 2. Method mặc định theo loại resource

Spring Data REST tạo collection resource và item resource từ repository. Ví dụ `OrderRepository extends CrudRepository<Order, Long>` thường cung cấp `/orders` và `/orders/{id}`. Method được expose phụ thuộc các method CRUD mà repository có và cho phép export.

| Resource | Method thường hỗ trợ | Hành vi |
| --- | --- | --- |
| Collection `/orders` | `GET`, `HEAD`, `POST` | GET liệt kê; POST tạo entity. Các method khác thường trả 405. |
| Item `/orders/{id}` | `GET`, `HEAD`, `PUT`, `PATCH`, `DELETE` | GET đọc; PUT thay thế; PATCH cập nhật một phần; DELETE xóa entity. |
| Association `/orders/{id}/customer` | `GET`, `PUT`, `POST`, `DELETE` | PUT gắn association; POST chỉ áp dụng cho collection association; DELETE gỡ liên kết khi association cho phép. |
| Search `/orders/search` và query resource | `GET`, `HEAD` | Resource chỉ đọc, cung cấp và thực thi các query method đã export. |

Không suy luận method chỉ từ tên repository. Hãy xác định đúng loại resource trước khi so sánh header Allow. Ví dụ, DELETE trên `/orders/42` có thể hợp lệ nhưng DELETE trên collection `/orders` vẫn trả 405 theo thiết kế.

### Repository method nào quyết định HTTP method?

Các ánh xạ quan trọng trong tài liệu Spring Data REST:

- `findAll(...)` cung cấp GET/HEAD cho collection resource.
- `findById(...)` cung cấp GET/HEAD cho item resource.
- `save(...)` được dùng cho POST trên collection và PUT/PATCH trên item.
- Các method `delete(...)` phù hợp cung cấp DELETE trên item.

Nếu repository không khai báo method cần thiết, hoặc method được đánh dấu `@RestResource(exported = false)`, HTTP method tương ứng sẽ không được expose. Một repository kế thừa `CrudRepository` thường có đủ CRUD method mặc định. Với repository chỉ kế thừa `Repository` và tự khai báo một phần method, exposure sẽ theo đúng những method được khai báo.

Cẩn thận với `save(...)`: ẩn method này bằng `@RestResource(exported = false)` có thể đồng thời làm mất POST collection và PUT/PATCH item. Nếu yêu cầu chỉ tắt một HTTP verb, nên dùng ExposureConfiguration để giới hạn chính xác phạm vi.

## 3. Tắt method bằng ExposureConfiguration

Từ Spring Data REST 3.1, `RepositoryRestConfiguration.getExposureConfiguration()` cung cấp API lambda để lọc HTTP method ở phạm vi toàn cục hoặc theo domain type. Ví dụ dưới đây tắt PATCH trên tất cả item resource:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.rest.webmvc.config.RepositoryRestConfigurer;
import org.springframework.http.HttpMethod;

@Configuration
public class RestMethodExposureConfiguration {

    @Bean
    RepositoryRestConfigurer repositoryRestConfigurer() {
        return RepositoryRestConfigurer.withConfig(config ->
            config.getExposureConfiguration()
                .withItemExposure((metadata, methods) ->
                    methods.disable(HttpMethod.PATCH)));
    }
}
```

Một số lựa chọn khác:

```java
// Tắt DELETE chỉ trên item resource của Order.
config.getExposureConfiguration()
    .forDomainType(Order.class)
    .withItemExposure((metadata, methods) ->
        methods.disable(HttpMethod.DELETE));

// Tắt POST trên mọi collection resource.
config.getExposureConfiguration()
    .withCollectionExposure((metadata, methods) ->
        methods.disable(HttpMethod.POST));

// Tắt PUT trên mọi item resource.
config.getExposureConfiguration().disablePutOnItemResources();

// Tắt PATCH trên mọi item resource.
config.getExposureConfiguration().disablePatchOnItemResources();

// Ngăn PUT tạo item mới cho riêng domain type User.
config.getExposureConfiguration()
    .forDomainType(User.class)
    .disablePutForCreation();
```

Phân biệt `disablePutForCreation()` với `disablePutOnItemResources()`: lựa chọn đầu ngăn tạo item mới bằng PUT; lựa chọn sau tắt PUT trên item resource. `withCollectionExposure` chỉ lọc method của collection; `withItemExposure` chỉ lọc method của item; `withAssociationExposure` dùng cho association resource.

Nếu chỉ muốn ẩn một repository method, có thể override method kế thừa và đặt `@RestResource(exported = false)` lên method đó. Hãy kiểm tra tất cả overload/biến thể CRUD mà phiên bản Spring Data đang dùng có thể gọi. Đặc biệt, `save(...)` có thể điều khiển nhiều HTTP verb như đã nêu ở trên. `@RepositoryRestResource(exported = false)` ở cấp repository sẽ ẩn cả repository resource, thường dẫn đến tình huống route không được export thay vì chỉ tắt một method.

Ví dụ cấu hình trên dùng `RepositoryRestConfigurer.withConfig(Consumer)`, có từ Spring Data REST 3.1. Nếu override trực tiếp `configureRepositoryRestConfiguration(config, cors)`, chữ ký có tham số `CorsRegistry` được hỗ trợ từ 3.4. Hãy đối chiếu Javadoc đúng phiên bản Spring Data REST trong dependency của dự án; không sao chép chữ ký từ tài liệu mới hơn vào ứng dụng cũ mà chưa kiểm tra.

## 4. Đọc và diễn giải Allow

Gọi đúng URL với đúng method và xem toàn bộ response header:

```bash
curl -i -X PATCH http://localhost:8080/orders/42 -H "Content-Type: application/merge-patch+json" -d '{"status":"SHIPPED"}'
```

Nếu PATCH bị tắt trên item resource, kết quả mong đợi là status 405 và header Allow không chứa PATCH. Ví dụ header có thể là:

```http
Allow: GET, HEAD, PUT, DELETE
```

Giá trị cụ thể phụ thuộc cấu hình thực tế. Hãy dùng `curl -i` thay vì chỉ đọc response body vì header Allow là phần bằng chứng quan trọng của lỗi.

Có thể kiểm tra một method được phép bằng request tương ứng, ví dụ:

```bash
curl -i http://localhost:8080/orders/42
curl -i http://localhost:8080/orders
```

GET item chỉ trả 200 nếu item tồn tại và GET được expose. GET collection kiểm tra collection route. Đối với collection, POST mới là thao tác tạo entity; PUT/PATCH/DELETE không tự động hợp lệ chỉ vì các method đó được hỗ trợ trên item resource.

### Allow không phải Access-Control-Allow-Methods

Hai header phục vụ hai mục đích khác nhau:

- `Allow` mô tả HTTP method mà resource đích hỗ trợ; RFC 9110 yêu cầu header này trong response 405.
- `Access-Control-Allow-Methods` thuộc CORS, cho biết method được chấp nhận trong ngữ cảnh request cross-origin từ trình duyệt.

Cấu hình CORS bằng `@CrossOrigin` hoặc `CorsRegistry.allowedMethods(...)` không tự bật route PUT/PATCH/DELETE của Spring Data REST. Ngược lại, route có thể hỗ trợ PATCH nhưng trình duyệt vẫn chặn request vì preflight CORS không cho phép PATCH.

Để xem preflight, gửi request OPTIONS có Origin và Access-Control-Request-Method:

```bash
curl -i -X OPTIONS http://localhost:8080/orders/42 -H "Origin: http://localhost:3000" -H "Access-Control-Request-Method: PATCH"
```

Đọc `Access-Control-Allow-Methods` và các header CORS của response này. Sau đó vẫn phải gọi PATCH thật để xác nhận method được expose. Preflight thành công không chứng minh endpoint có hỗ trợ method đó.

## 5. Quy trình xử lý lỗi 405

1. **Ghi nhận response nguyên vẹn.** Dùng `curl -i` hoặc Network tab để lưu status, URL, method, Allow, Content-Type và response body.
2. **Xác nhận đúng URL.** Phân biệt collection, item, association, search resource và query resource. Kiểm tra base path, path tùy chỉnh bằng `@RepositoryRestResource`, ID và tên association.
3. **Đối chiếu method với loại resource.** Ví dụ POST dùng trên collection; PUT/PATCH/DELETE dùng trên item. Search resource chỉ đọc. Association có quy tắc riêng.
4. **Kiểm tra repository.** Xác nhận repository có method backing tương ứng; kiểm tra method có `@RestResource(exported = false)) hay không. Kiểm tra cả cấu hình expose repository và `RepositoryDetectionStrategy` nếu route không xuất hiện.
5. **Kiểm tra cấu hình exposure.** Tìm các bean `RepositoryRestConfigurer`, `ExposureConfiguration`, `withCollectionExposure`, `withItemExposure`, `withAssociationExposure`, `forDomainType`, `disablePutOnItemResources()` và `disablePatchOnItemResources()`.
6. **Tách vấn đề CORS khỏi exposure.** Nếu chỉ trình duyệt thất bại, kiểm tra request OPTIONS và `Access-Control-Allow-Methods`. Dùng curl từ cùng môi trường để xác nhận endpoint có thực sự trả 405 hay không.
7. **Xác định lớp tạo response.** Nếu 405 không có Allow, kiểm tra reverse proxy/API gateway, servlet filter, Spring Security và custom exception handler. Theo RFC 9110, origin server phải tạo Allow trong response 405; một lớp trung gian có thể làm thay đổi response trước khi tới client.
8. **Kiểm tra lại sau khi sửa.** Gửi lại method bị tắt và ít nhất một method vẫn được phép; xác nhận cả status lẫn Allow. Không chỉ dựa vào response body hoặc một request OPTIONS.

Một số dấu hiệu thường gặp:

- `Allow` không có PATCH: cấu hình hiện tại không quảng bá PATCH cho resource đó; 405 khi gọi PATCH là phù hợp.
- `Allow` có PATCH nhưng request PATCH vẫn trả 405: xác minh URL, host, proxy, cấu hình đang deploy và response có đến từ cùng origin hay không.
- 405 không có Allow: xác định response được tạo ở ứng dụng hay gateway/filter; kiểm tra custom exception handling và header có bị loại bỏ không.
- Chỉ trình duyệt lỗi nhưng curl thành công: ưu tiên kiểm tra CORS preflight, origin, credentials và Access-Control-Allow-Methods.
- 404 thay vì 405: kiểm tra repository/resource có được export, base path và route có đúng không.
- 401/403: kiểm tra authentication/authorization trước khi thay đổi exposure.

## 6. Kiểm thử tích hợp

Nên kiểm tra cả hành vi từ client và header được quảng bá. Với Spring Boot, có thể dùng `@SpringBootTest` + `@AutoConfigureMockMvc`; chuẩn bị một entity tồn tại bằng fixture của dự án rồi thay `orderId` bằng ID đó:

```java
mockMvc.perform(patch("/orders/{id}", orderId)
        .contentType("application/merge-patch+json")
        .content("{\"status\":\"SHIPPED\"}"))
    .andExpect(status().isMethodNotAllowed())
    .andExpect(header().exists("Allow"))
    .andExpect(header().string("Allow",
        not(containsString("PATCH"))));
```

Đoạn test trên giả định PATCH đã bị tắt bằng ExposureConfiguration và fixture đã tạo `orderId`. Import các matcher `not` và `containsString` từ Hamcrest. Không hard-code toàn bộ giá trị Allow nếu ứng dụng có thể thay đổi các method hợp lệ khác; hãy khẳng định header tồn tại, method bị tắt vắng mặt và các method cần giữ vẫn được hỗ trợ.

Bổ sung test cho một method hợp lệ, ví dụ:

```java
mockMvc.perform(get("/orders/{id}", orderId))
    .andExpect(status().isOk());
```

Checklist kiểm thử:

- PATCH trên item resource trả 405 khi đã disable.
- Response 405 có header Allow và Allow không chứa PATCH.
- GET item vẫn thành công nếu vẫn được expose và fixture tồn tại.
- GET/POST trên collection được kiểm tra riêng; không suy luận từ kết quả item resource.
- Nếu dùng `@RestResource(exported = false)`, kiểm tra tất cả HTTP verb được backing method đó phục vụ.
- Nếu client chạy trên browser, kiểm tra CORS preflight riêng với Origin và Access-Control-Request-Method.
- Chạy lại integration test sau khi thay đổi Spring Data REST hoặc Spring Data release train.

## 7. Tài liệu chính thức

- [RFC 9110 §15.5.6 — 405 Method Not Allowed](https://www.rfc-editor.org/rfc/rfc9110.html#section-15.5.6)
- [RFC 9110 §10.2.1 — Allow](https://www.rfc-editor.org/rfc/rfc9110.html#section-10.2.1)
- [Spring Data REST — Repository resources](https://docs.spring.io/spring-data/rest/reference/repository-resources.html)
- [Spring Data REST — Customizing supported HTTP methods](https://docs.spring.io/spring-data/rest/reference/customizing-sdr.html)
- [Spring Data REST API — ExposureConfiguration](https://docs.spring.io/spring-data/rest/docs/current/api/org/springframework/data/rest/core/mapping/ExposureConfiguration.html)
- [Spring Data REST API — RepositoryRestConfigurer](https://docs.spring.io/spring-data/rest/docs/current/api/org/springframework/data/rest/webmvc/config/RepositoryRestConfigurer.html)
- [Spring Data REST — Configuring CORS](https://docs.spring.io/spring-data/rest/reference/customizing/configuring-cors.html)
- [Spring Data REST API — ConfigurableHttpMethods](https://docs.spring.io/spring-data/rest/docs/current/api/org/springframework/data/rest/core/mapping/ConfigurableHttpMethods.html)
