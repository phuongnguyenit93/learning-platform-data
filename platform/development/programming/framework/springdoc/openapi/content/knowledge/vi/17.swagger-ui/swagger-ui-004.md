# Chọn nhóm mặc định và tổ chức danh sách nhóm

Khi một ứng dụng Spring Boot công bố nhiều tài liệu OpenAPI, Swagger UI cần cho người dùng biết tài liệu nào đang được xem và cách chuyển sang tài liệu khác. springdoc-openapi có thể tạo nhiều tài liệu bằng **GroupedOpenApi**; Swagger UI hiển thị danh sách các tài liệu đó để người dùng chọn. Khi có nhiều lựa chọn, ta nên xác định tài liệu mặc định và sắp xếp danh sách theo cách dễ hiểu.

Hai cấu hình thường gặp là **url** khi giao diện chỉ dùng một tài liệu và **urls** khi giao diện cần một danh sách tài liệu. Với nhiều tài liệu, thuộc tính **urls-primary-name** chọn tên tài liệu được mở ban đầu. Danh sách này là danh sách đặc tả OpenAPI; nó khác với tag và operation bên trong từng đặc tả.

## 1. GroupedOpenApi tạo tài liệu riêng cho từng nhóm

Mỗi bean **GroupedOpenApi** xác định một phạm vi endpoint và một tên group. Ví dụ:

~~~java
@Configuration
public class OpenApiGroupConfiguration {

    @Bean
    GroupedOpenApi publicApi() {
        return GroupedOpenApi.builder()
            .group("public-api")
            .pathsToMatch("/api/**")
            .pathsToExclude("/api/internal/**")
            .build();
    }

    @Bean
    GroupedOpenApi adminApi() {
        return GroupedOpenApi.builder()
            .group("admin-api")
            .pathsToMatch("/api/admin/**")
            .build();
    }

    @Bean
    GroupedOpenApi partnerApi() {
        return GroupedOpenApi.builder()
            .group("partner-api")
            .packagesToScan("com.example.app.partner")
            .build();
    }
}
~~~

springdoc tạo tài liệu riêng cho từng group. Với đường dẫn mặc định, có thể truy cập:

| Group | OpenAPI JSON |
|---|---|
| Tài liệu mặc định | /v3/api-docs |
| public-api | /v3/api-docs/public-api |
| admin-api | /v3/api-docs/admin-api |
| partner-api | /v3/api-docs/partner-api |

Tên group được dùng trong URL tài liệu. Hãy chọn tên ngắn, dễ nhận biết và ổn định vì Swagger UI, cổng API, pipeline kiểm tra hợp đồng hoặc công cụ sinh SDK có thể tham chiếu các URL này.

**Group** quyết định operation nào thuộc một tài liệu. **Tag** tổ chức operation bên trong tài liệu đó. Ví dụ, group public-api có thể chứa tag Books, Orders và Payments; group admin-api có thể chứa tag Users và Audit. Không dùng tag để thay thế group khi mục tiêu là tạo các tài liệu OpenAPI riêng.

## 2. Chọn một tài liệu mặc định bằng url

Nếu Swagger UI chỉ cần hiển thị một tài liệu, cấu hình **springdoc.swagger-ui.url**:

~~~yaml
springdoc:
  swagger-ui:
    url: /v3/api-docs/public-api
~~~

Hoặc trong application.properties:

~~~properties
springdoc.swagger-ui.url=/v3/api-docs/public-api
~~~

Khi mở Swagger UI, giao diện tải tài liệu ở URL đã chỉ định. Cách này phù hợp khi ứng dụng chỉ muốn cung cấp một tài liệu cho môi trường hoặc nhóm người dùng cụ thể.

Nếu muốn dùng tài liệu mặc định do springdoc tạo ra, có thể trỏ tới /v3/api-docs hoặc để springdoc sử dụng cấu hình mặc định. Không cần khai báo một URL riêng nếu tài liệu mặc định đã đáp ứng mục đích.

**url** là một URL tài liệu đơn. Khi cần dropdown cho nhiều tài liệu, hãy dùng cấu hình **urls**.

## 3. Hiển thị nhiều tài liệu bằng urls

Swagger UI hỗ trợ một danh sách URL đặc tả. springdoc cho phép cấu hình danh sách này bằng **springdoc.swagger-ui.urls**.

Ví dụ application.yml:

~~~yaml
springdoc:
  swagger-ui:
    urls:
      - name: Public API
        url: /v3/api-docs/public-api
      - name: Admin API
        url: /v3/api-docs/admin-api
      - name: Partner API
        url: /v3/api-docs/partner-api
~~~

Hoặc application.properties:

~~~properties
springdoc.swagger-ui.urls[0].name=Public API
springdoc.swagger-ui.urls[0].url=/v3/api-docs/public-api
springdoc.swagger-ui.urls[1].name=Admin API
springdoc.swagger-ui.urls[1].url=/v3/api-docs/admin-api
springdoc.swagger-ui.urls[2].name=Partner API
springdoc.swagger-ui.urls[2].url=/v3/api-docs/partner-api
~~~

Swagger UI sẽ có bộ chọn tài liệu. Tên trong **name** là nhãn người dùng nhìn thấy; **url** là địa chỉ Swagger UI tải đặc tả. Hai trường cần nhất quán với tên group và endpoint thực tế.

Trong cấu hình trên:

- Người dùng chọn **Public API** để tải /v3/api-docs/public-api.
- Người dùng chọn **Admin API** để tải /v3/api-docs/admin-api.
- Người dùng chọn **Partner API** để tải /v3/api-docs/partner-api.

Danh sách urls có thể tham chiếu tài liệu trong cùng ứng dụng hoặc tài liệu từ máy chủ khác. Nếu dùng URL khác origin, trình duyệt cần truy cập được máy chủ đó và máy chủ phải cho phép CORS phù hợp.

## 4. Chọn nhóm được mở đầu tiên bằng urls-primary-name

Khi có nhiều URL, **springdoc.swagger-ui.urls-primary-name** chỉ định tên tài liệu được chọn khi Swagger UI khởi động:

~~~yaml
springdoc:
  swagger-ui:
    urls:
      - name: Public API
        url: /v3/api-docs/public-api
      - name: Admin API
        url: /v3/api-docs/admin-api
      - name: Partner API
        url: /v3/api-docs/partner-api
    urls-primary-name: Public API
~~~

Trong application.properties:

~~~properties
springdoc.swagger-ui.urls[0].name=Public API
springdoc.swagger-ui.urls[0].url=/v3/api-docs/public-api
springdoc.swagger-ui.urls[1].name=Admin API
springdoc.swagger-ui.urls[1].url=/v3/api-docs/admin-api
springdoc.swagger-ui.urls[2].name=Partner API
springdoc.swagger-ui.urls[2].url=/v3/api-docs/partner-api
springdoc.swagger-ui.urls-primary-name=Public API
~~~

Giá trị **urls-primary-name** phải khớp chính xác với một giá trị **name** trong danh sách urls. Tên này là nhãn của tài liệu trong dropdown, không nhất thiết giống group name, nhưng dùng cùng tên thường giúp cấu hình dễ đọc.

Nếu đổi tên Public API thành External API trong danh sách, cần đổi urls-primary-name theo. Nếu tên mặc định không khớp bất kỳ mục nào, Swagger UI có thể quay về lựa chọn đầu tiên hoặc hành vi mặc định của phiên bản đang dùng; không nên dựa vào fallback đó trong môi trường triển khai.

### Phân biệt urls-primary-name với group name

Giả sử GroupedOpenApi được khai báo:

~~~java
@Bean
GroupedOpenApi publicApi() {
    return GroupedOpenApi.builder()
        .group("public-api")
        .pathsToMatch("/api/**")
        .build();
}
~~~

Tên group là public-api, nên URL JSON là /v3/api-docs/public-api. Trong Swagger UI, mục hiển thị có thể đặt tên Public API; khi đó:

- **group("public-api")** xác định group của springdoc.
- **url: /v3/api-docs/public-api** trỏ tới tài liệu của group.
- **name: Public API** đặt nhãn trong bộ chọn.
- **urls-primary-name: Public API** chọn nhãn đó làm tài liệu mặc định.

Không đặt urls-primary-name thành URL hoặc group name nếu name trong danh sách là một nhãn khác.

## 5. Tổ chức thứ tự các nhóm trong dropdown

Khi tự khai báo **springdoc.swagger-ui.urls**, thứ tự phần tử trong danh sách là thứ tự cấu hình mà Swagger UI nhận được. Có thể đặt tài liệu thường dùng lên trước:

~~~yaml
springdoc:
  swagger-ui:
    urls:
      - name: Public API
        url: /v3/api-docs/public-api
      - name: Partner API
        url: /v3/api-docs/partner-api
      - name: Admin API
        url: /v3/api-docs/admin-api
    urls-primary-name: Public API
~~~

Một thứ tự dễ dùng thường là:

1. Tài liệu dành cho phần lớn người tích hợp.
2. Tài liệu chuyên biệt theo miền hoặc đối tác.
3. Tài liệu quản trị hoặc nội bộ dành cho người dùng có quyền.

Đây là quy ước tổ chức giao diện, không phải cơ chế phân quyền. Nếu danh sách urls được khai báo thủ công, người duy trì phải cập nhật nó khi thêm, đổi tên hoặc xóa group.

### Đặt tên nhãn dễ nhận biết

Nên chọn nhãn mô tả đối tượng sử dụng hoặc phạm vi:

| Nên dùng | Tránh dùng |
|---|---|
| Public API | Group 1 |
| Partner API | Docs B |
| Administration API | Other |
| Billing API | API mới |

Tên hiển thị có thể chứa khoảng trắng và chữ hoa để dễ đọc. Tên group trong GroupedOpenApi nên ổn định, đơn giản và phù hợp với URL. Có thể dùng nhãn đẹp hơn trong urls.name mà không phải đổi URL group.

## 6. Tự động phát hiện group hay khai báo urls tường minh?

Khi đăng ký nhiều bean GroupedOpenApi, springdoc có thể đưa các group vào cấu hình Swagger UI được sinh ra. Cách này giảm việc phải lặp lại URL của từng group. Với ứng dụng có yêu cầu điều khiển danh sách hoặc nhãn hiển thị cụ thể, có thể khai báo springdoc.swagger-ui.urls tường minh.

| Cách tổ chức | Phù hợp khi | Cần lưu ý |
|---|---|---|
| Dùng các bean GroupedOpenApi | Các group được tạo và quản lý hoàn toàn trong ứng dụng | Kiểm tra /v3/api-docs/swagger-config để biết danh sách mà UI thực sự nhận |
| Khai báo swagger-ui.urls | Cần chọn chính xác tài liệu, URL hoặc nhãn trong dropdown | Phải đồng bộ thủ công với group và URL đang tồn tại |
| Kết hợp group nội bộ và URL ngoài | UI cần tổng hợp tài liệu từ nhiều dịch vụ | Kiểm tra CORS, HTTPS, khả năng truy cập và vòng đời URL ngoài |

Không nên khai báo cùng một tài liệu lặp lại trong nhiều mục urls. Nếu tự cấu hình danh sách, hãy bảo đảm mỗi name duy nhất và mỗi URL trỏ tới một tài liệu hợp lệ.

Nếu một group mới được thêm nhưng không xuất hiện trong dropdown, hãy kiểm tra cấu hình Swagger UI và endpoint swagger-config. Đừng chỉ kiểm tra bean GroupedOpenApi vì group tồn tại không có nghĩa một danh sách URL tự quản lý đã được cập nhật.

## 7. Dùng URL tương đối và cấu hình sau reverse proxy

Trong cùng một ứng dụng, nên dùng URL tương đối:

~~~yaml
springdoc:
  swagger-ui:
    urls:
      - name: Public API
        url: /v3/api-docs/public-api
      - name: Orders API
        url: /v3/api-docs/orders
~~~

URL tương đối giúp tài liệu hoạt động khi ứng dụng được triển khai ở host hoặc domain khác. Nếu ứng dụng chạy dưới context path, reverse proxy hoặc prefix như /service-a, cần xác nhận URL được trình duyệt yêu cầu thực tế có prefix đúng.

Nếu URL tài liệu nằm ở máy chủ khác:

~~~yaml
springdoc:
  swagger-ui:
    urls:
      - name: Catalog API
        url: https://api.example.test/catalog/v3/api-docs
      - name: Orders API
        url: https://api.example.test/orders/v3/api-docs
    urls-primary-name: Catalog API
~~~

Trình duyệt tải trực tiếp tài liệu từ các URL này. Cần HTTPS trong môi trường thật, CORS phù hợp nếu khác origin và quyền truy cập tài liệu đúng với người dùng. Không đưa token hoặc thông tin xác thực vào query string của URL tài liệu.

## 8. Tùy chỉnh cách hiển thị bên trong mỗi tài liệu

Danh sách group và cách sắp xếp operation là hai lớp khác nhau. **urls** tổ chức danh sách tài liệu; các thuộc tính khác của Swagger UI tổ chức nội dung bên trong tài liệu đang chọn.

Ví dụ:

~~~yaml
springdoc:
  swagger-ui:
    doc-expansion: none
    tags-sorter: alpha
    operations-sorter: method
    filter: true
~~~

Các thuộc tính:

| Thuộc tính | Tác dụng |
|---|---|
| **doc-expansion** | Cách mở rộng tag và operation khi tải tài liệu: none, list hoặc full |
| **tags-sorter** | Sắp xếp tag trong tài liệu |
| **operations-sorter** | Sắp xếp operation bên trong tag |
| **filter** | Hiển thị bộ lọc tìm kiếm operation |

Các thuộc tính này không thay đổi group mặc định và không sắp xếp danh sách urls. Ví dụ tags-sorter: alpha sắp xếp các tag trong tài liệu đang mở; nó không thay đổi thứ tự Public API, Admin API và Partner API trong dropdown.

## 9. Không nhầm default document với URL mặc định của Swagger UI

Swagger UI cần biết tài liệu hoặc cấu hình tài liệu nào để tải. Một số thuộc tính liên quan:

| Thuộc tính | Vai trò |
|---|---|
| **springdoc.swagger-ui.url** | Một URL tài liệu đơn |
| **springdoc.swagger-ui.urls** | Danh sách URL tài liệu |
| **springdoc.swagger-ui.urls-primary-name** | Tên mục trong danh sách được chọn đầu tiên |
| **springdoc.swagger-ui.config-url** | URL trả cấu hình Swagger UI, thường là endpoint swagger-config do springdoc cung cấp |
| **springdoc.swagger-ui.disable-swagger-default-url** | Tắt URL Petstore mặc định của Swagger UI khi không muốn giao diện dùng tài liệu mẫu |

Trong cấu hình nhiều group của springdoc, endpoint cấu hình thường là /v3/api-docs/swagger-config. Chỉ thay config-url khi có lý do cụ thể, chẳng hạn cấu hình được phục vụ qua một URL tùy chỉnh hoặc reverse proxy. config-url không phải URL của OpenAPI JSON và cũng không phải giá trị của urls-primary-name.

Nếu UI mở tài liệu mẫu Petstore ngoài ý muốn, kiểm tra URL/URLs và cân nhắc:

~~~yaml
springdoc:
  swagger-ui:
    disable-swagger-default-url: true
~~~

Điều này giúp tránh nhầm tài liệu demo mặc định với API của ứng dụng.

## 10. Ví dụ cấu hình hoàn chỉnh

Giả sử ứng dụng có ba GroupedOpenApi:

~~~java
@Configuration
public class ApiDocumentationConfiguration {

    @Bean
    GroupedOpenApi publicApi() {
        return GroupedOpenApi.builder()
            .group("public-api")
            .pathsToMatch("/api/**")
            .pathsToExclude("/api/admin/**")
            .build();
    }

    @Bean
    GroupedOpenApi ordersApi() {
        return GroupedOpenApi.builder()
            .group("orders")
            .pathsToMatch("/api/orders/**")
            .build();
    }

    @Bean
    GroupedOpenApi adminApi() {
        return GroupedOpenApi.builder()
            .group("admin-api")
            .pathsToMatch("/api/admin/**")
            .build();
    }
}
~~~

Cấu hình application.yml:

~~~yaml
springdoc:
  swagger-ui:
    urls:
      - name: Public API
        url: /v3/api-docs/public-api
      - name: Orders API
        url: /v3/api-docs/orders
      - name: Administration API
        url: /v3/api-docs/admin-api
    urls-primary-name: Public API
    disable-swagger-default-url: true
    doc-expansion: none
    tags-sorter: alpha
    operations-sorter: method
    filter: true
~~~

Kết quả mong muốn:

- Swagger UI mở tài liệu **Public API** khi người dùng truy cập lần đầu.
- Dropdown hiển thị Public API, Orders API và Administration API.
- Người dùng có thể đổi tài liệu mà không phải mở URL Swagger UI khác.
- Trong từng tài liệu, tag được sắp xếp theo alphabet, operation được sắp xếp theo method và các nhóm nội dung thu gọn lúc đầu.
- Swagger UI không dùng URL Petstore mặc định.

Nếu thay đổi tên group trong Java, cần cập nhật URL tương ứng trong application.yml. Nếu đổi nhãn name, cần cập nhật urls-primary-name khi mục đó đang là tài liệu mặc định.

## 11. Kiểm tra Swagger UI nhận đúng danh sách nhóm

Đừng chỉ nhìn cấu hình source. Hãy kiểm tra endpoint swagger-config mà Swagger UI thực sự tải:

~~~bash
curl -i http://localhost:8080/v3/api-docs/swagger-config
~~~

Endpoint này trả cấu hình dùng để khởi tạo Swagger UI. Kiểm tra danh sách URL, tên hiển thị và lựa chọn chính theo cấu hình mà phiên bản springdoc đang xuất ra.

Kiểm tra từng tài liệu:

~~~bash
curl -i http://localhost:8080/v3/api-docs/public-api
curl -i http://localhost:8080/v3/api-docs/orders
curl -i http://localhost:8080/v3/api-docs/admin-api
~~~

Nếu đã đổi đường dẫn API docs hoặc ứng dụng chạy dưới context path, thay URL cho phù hợp. Mỗi URL cần trả về OpenAPI JSON hợp lệ.

Có thể dùng jq để xem các path của một group:

~~~bash
curl -s http://localhost:8080/v3/api-docs/orders \
  | jq -r '.paths | keys[]'
~~~

Sau đó mở Swagger UI và xác nhận:

1. Dropdown hiển thị đúng các nhãn và thứ tự mong muốn.
2. Tài liệu mặc định được chọn đúng khi tải giao diện.
3. Chọn từng mục sẽ tải đúng endpoint tương ứng.
4. Tag và operation bên trong tài liệu được sắp xếp đúng.
5. Không có URL trùng, URL 404 hoặc tài liệu mẫu ngoài ý muốn.

## 12. Lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Dropdown không xuất hiện | Chỉ cấu hình một url, hoặc swagger-config không có danh sách urls | Kiểm tra urls và /v3/api-docs/swagger-config |
| Nhóm mặc định không đúng | urls-primary-name không khớp name | Đồng bộ tên chính xác |
| Một mục trong dropdown trả 404 | URL không khớp group name hoặc API docs path đã đổi | Gọi trực tiếp URL và sửa cấu hình |
| Group mới không xuất hiện | Danh sách urls khai báo thủ công chưa cập nhật | Thêm mục mới hoặc dùng cơ chế phát hiện group phù hợp |
| Dropdown có mục trùng | Cùng tài liệu được thêm nhiều lần | Loại mục trùng và giữ name duy nhất |
| Thứ tự dropdown không như mong đợi | Thứ tự trong danh sách urls chưa đúng hoặc cấu hình tự động khác dự kiến | Khai báo danh sách tường minh và kiểm tra swagger-config |
| tags-sorter không đổi thứ tự group | Đang nhầm sorter tag với thứ tự danh sách tài liệu | Sắp xếp danh sách urls |
| Swagger UI mở Petstore | Chưa tắt URL demo mặc định hoặc cấu hình URL chưa được áp dụng | Kiểm tra url, urls và disable-swagger-default-url |
| Tài liệu ngoài không tải được | CORS, HTTPS, DNS hoặc quyền truy cập | Kiểm tra network request từ trình duyệt và cấu hình máy chủ |
| Chạy sau reverse proxy bị 404 | URL tương đối thiếu context path hoặc proxy prefix | Kiểm tra URL thực tế và cấu hình forwarded headers/proxy |
| Nhóm có trong JSON nhưng người dùng không truy cập được | API docs endpoint bị Spring Security bảo vệ | Cấp quyền truy cập tài liệu theo chính sách triển khai |

## 13. Phân biệt lựa chọn tài liệu với quyền truy cập

Việc đưa một tài liệu vào urls chỉ làm nó xuất hiện trong bộ chọn Swagger UI. Việc đặt một group làm primary chỉ quyết định tài liệu được mở đầu tiên. Hai cấu hình này không cấp quyền truy cập cho người dùng.

Nếu tài liệu admin chỉ dành cho quản trị viên:

- Bảo vệ endpoint /v3/api-docs/admin-api bằng Spring Security hoặc cơ chế truy cập phù hợp.
- Bảo vệ Swagger UI nếu cần.
- Xác nhận người dùng không có quyền không thể tải JSON/YAML trực tiếp.
- Không dựa vào việc ẩn mục dropdown hoặc không đặt nó làm primary để bảo vệ tài liệu.

Tương tự, một endpoint bị loại khỏi tài liệu không tự động bị chặn ở runtime. Group và UI là cách tổ chức hợp đồng được công bố; authorization phải được thực hiện ở tầng bảo mật của ứng dụng.

## 14. Checklist tổ chức danh sách nhóm

- [ ] Mỗi GroupedOpenApi có tên duy nhất và ổn định.
- [ ] Mỗi group trả về OpenAPI JSON hợp lệ tại URL dự kiến.
- [ ] Danh sách urls chỉ chứa tài liệu cần hiển thị cho giao diện này.
- [ ] Mỗi mục có name duy nhất, dễ hiểu và URL đúng.
- [ ] urls-primary-name khớp chính xác một name trong danh sách.
- [ ] Thứ tự urls phù hợp với người dùng chính của Swagger UI.
- [ ] url đơn và urls nhiều tài liệu không bị cấu hình chồng chéo ngoài ý muốn.
- [ ] tags-sorter, operations-sorter và doc-expansion chỉ dùng cho nội dung bên trong tài liệu.
- [ ] /v3/api-docs/swagger-config phản ánh cấu hình mong muốn.
- [ ] Từng URL group đã được gọi thử và không trả 404.
- [ ] Tài liệu nội bộ được bảo vệ bằng quyền runtime thích hợp.
- [ ] Danh sách được cập nhật khi thêm, đổi tên hoặc xóa group.

## Kết luận

**GroupedOpenApi** tạo tài liệu OpenAPI theo phạm vi; **springdoc.swagger-ui.urls** cung cấp danh sách tài liệu trong dropdown; **urls-primary-name** chọn nhãn tài liệu được mở đầu tiên. Với một tài liệu, dùng **springdoc.swagger-ui.url**. Thứ tự phần tử trong danh sách urls điều khiển thứ tự lựa chọn, còn tags-sorter và operations-sorter chỉ tổ chức nội dung bên trong tài liệu đang mở. Hãy giữ group name, URL và nhãn đồng bộ, kiểm tra /v3/api-docs/swagger-config cùng từng endpoint JSON, và bảo vệ tài liệu nội bộ bằng cơ chế bảo mật runtime riêng.
