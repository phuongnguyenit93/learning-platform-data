# Nguồn đặc tả từ một URL hoặc danh sách tài liệu

Swagger UI cần biết URL của tài liệu OpenAPI trước khi có thể hiển thị endpoint, schema và ví dụ. Với một API, cấu hình thường chỉ cần một URL. Khi hệ thống có nhiều phiên bản, nhiều nhóm API hoặc nhiều dịch vụ độc lập, Swagger UI có thể nhận một danh sách URL để người dùng chọn tài liệu trong thanh điều hướng phía trên.

Trong Spring Boot, springdoc-openapi cung cấp các thuộc tính cấu hình cho cả hai trường hợp. Thuộc tính **springdoc.swagger-ui.url** trỏ đến một tài liệu OpenAPI. Nhóm thuộc tính **springdoc.swagger-ui.urls** khai báo danh sách tài liệu, mỗi mục có tên hiển thị và URL riêng. Hai cách này dựa trên cấu hình chính thức của Swagger UI; cần phân biệt URL của đặc tả với URL cấu hình Swagger UI và URL máy chủ API được khai báo bên trong đặc tả.

## 1. Phân biệt các loại URL

Khi cấu hình Swagger UI, có một số loại URL thường bị nhầm lẫn:

| Thuộc tính | Vai trò | Ví dụ |
| --- | --- | --- |
| **springdoc.swagger-ui.path** | Đường dẫn trang HTML mở giao diện Swagger UI | **/swagger-ui.html** |
| **springdoc.api-docs.path** | Đường dẫn gốc của đặc tả OpenAPI do springdoc sinh | **/v3/api-docs** |
| **springdoc.swagger-ui.configUrl** | URL trả về tài liệu cấu hình cho Swagger UI, gồm nguồn OpenAPI và các tùy chọn giao diện | **/v3/api-docs/swagger-config** |
| **springdoc.swagger-ui.url** | URL của một tài liệu OpenAPI mà giao diện cần tải | **/v3/api-docs** |
| **springdoc.swagger-ui.urls** | Danh sách nhiều tài liệu OpenAPI để người dùng chọn | **/v3/api-docs/orders**, **/v3/api-docs/admin** |
| **servers.url** trong OpenAPI | URL gốc của API dùng cho các request như Try it out | **https://api.example.com** |

Ví dụ, trang giao diện có thể nằm tại **https://docs.example.com/swagger-ui.html**, tải đặc tả từ **https://docs.example.com/openapi/store.yaml**, trong khi các request thực tế được gửi đến server **https://api.example.com** được khai báo trong thuộc tính servers của đặc tả.

**configUrl** không phải URL của file OpenAPI. Với tích hợp springdoc mặc định, configUrl thường là **/v3/api-docs/swagger-config**. Endpoint này trả cấu hình mà springdoc tạo cho Swagger UI, bao gồm URL tài liệu hoặc danh sách nhóm. Chỉ thay configUrl khi muốn dùng một file cấu hình Swagger UI do ứng dụng tự quản lý.

## 2. Dùng một URL đặc tả với springdoc

Nếu giao diện chỉ cần hiển thị một tài liệu, có thể cấu hình URL của file OpenAPI trong application.yml:

~~~yaml
springdoc:
  swagger-ui:
    url: https://docs.example.com/openapi/store.yaml
    disable-swagger-default-url: true
~~~

Thuộc tính **url** có thể trỏ đến:

- Đặc tả JSON do springdoc sinh, ví dụ **/v3/api-docs**.
- Đặc tả YAML do springdoc sinh, ví dụ **/v3/api-docs.yaml**.
- Một file JSON hoặc YAML tĩnh được phục vụ từ ứng dụng.
- Một tài liệu OpenAPI được lưu trên máy chủ tài liệu hoặc CDN khác.

Nếu ứng dụng đã dùng springdoc để sinh tài liệu mặc định tại **/v3/api-docs**, thông thường không cần ghi đè thuộc tính url. Giữ cấu hình mặc định giúp springdoc tự cung cấp nguồn tài liệu phù hợp với ứng dụng và các cấu hình group.

Nếu ứng dụng đã khai báo **GroupedOpenApi** hoặc **springdoc.group-configs**, springdoc có thể đưa các group vào danh sách **urls** trong swagger-config. Khi cấu hình **urls** tồn tại, Swagger UI ưu tiên danh sách đó và bỏ qua **url** đơn. Nếu muốn giao diện chỉ hiển thị một file ngoài trong ứng dụng có nhiều group, hãy khai báo danh sách **urls** với một phần tử duy nhất hoặc quản lý swagger-config riêng.

Ví dụ chỉ định file YAML tĩnh được đóng gói trong Spring Boot:

~~~text
src/
  main/
    resources/
      static/
        openapi/
          store-api.yaml
~~~

Với static resource mapping mặc định, file có thể được truy cập qua **/openapi/store-api.yaml**. Cấu hình:

~~~yaml
springdoc:
  swagger-ui:
    url: /openapi/store-api.yaml
    disable-swagger-default-url: true
~~~

Hãy mở trực tiếp URL của file để xác nhận ứng dụng phục vụ đúng nội dung. Nếu dự án thay đổi static resource mapping hoặc triển khai dưới context path, URL công khai cần được cập nhật tương ứng.

## 3. Cấu hình một URL trong application.properties

Các thuộc tính Swagger UI được springdoc hỗ trợ theo prefix **springdoc.swagger-ui**. Với file application.properties, cấu hình một nguồn đặc tả như sau:

~~~properties
springdoc.swagger-ui.url=https://docs.example.com/openapi/store.yaml
springdoc.swagger-ui.disable-swagger-default-url=true
~~~

Nếu dùng tài liệu được sinh bởi springdoc:

~~~properties
springdoc.swagger-ui.url=/v3/api-docs
~~~

Không đặt **springdoc.swagger-ui.url** thành URL của trang HTML Swagger UI hoặc URL của endpoint swagger-config. Giá trị phải trỏ đến nội dung đặc tả OpenAPI có thể được tải và phân tích.

## 4. Dùng danh sách urls cho nhiều tài liệu

Khi cần cung cấp nhiều đặc tả trong cùng giao diện, dùng thuộc tính **urls**. Mỗi phần tử có hai trường:

- **name**: tên duy nhất hiển thị trong danh sách chọn tài liệu.
- **url**: URL duy nhất trỏ đến đặc tả OpenAPI tương ứng.

Ví dụ cấu hình ba tài liệu:

~~~yaml
springdoc:
  swagger-ui:
    urls:
      - name: Store API v1
        url: /v3/api-docs/store-v1
      - name: Store API v2
        url: /v3/api-docs/store-v2
      - name: Admin API
        url: /v3/api-docs/admin
    urls-primary-name: Store API v2
    disable-swagger-default-url: true
~~~

Swagger UI hiển thị danh sách để người dùng chuyển giữa Store API v1, Store API v2 và Admin API. Khi giao diện tải lần đầu, **urls-primary-name** chọn tài liệu có tên khớp làm tài liệu mặc định. Tên phải trùng chính xác với một phần tử trong danh sách; nếu không khớp, Swagger UI sẽ dùng tài liệu đầu tiên.

Tên và URL trong danh sách phải duy nhất. Không dùng cùng một name cho hai tài liệu hoặc lặp lại cùng một URL dưới các tên khác nhau nếu không có chủ ý rõ ràng. Việc định danh bằng name và URL giúp Topbar plugin phân biệt các mục trong danh sách.

Khi **urls** được cấu hình và Topbar plugin hoạt động, thuộc tính **url** đơn lẻ sẽ bị bỏ qua. Vì vậy, hãy chọn một nguồn cấu hình rõ ràng: một URL cho một tài liệu, hoặc danh sách urls cho nhiều tài liệu.

## 5. Cấu hình danh sách trong application.properties

Có thể khai báo từng phần tử của danh sách bằng chỉ số:

~~~properties
springdoc.swagger-ui.urls[0].name=Store API v1
springdoc.swagger-ui.urls[0].url=/v3/api-docs/store-v1

springdoc.swagger-ui.urls[1].name=Store API v2
springdoc.swagger-ui.urls[1].url=/v3/api-docs/store-v2

springdoc.swagger-ui.urls[2].name=Admin API
springdoc.swagger-ui.urls[2].url=/v3/api-docs/admin

springdoc.swagger-ui.urlsPrimaryName=Store API v2
springdoc.swagger-ui.disable-swagger-default-url=true
~~~

Trong YAML, Spring Boot hỗ trợ dạng danh sách với các phần tử có name và url. Trong properties, các mục được đánh số bắt đầu từ 0. Hãy tránh bỏ chỉ số giữa danh sách hoặc lặp chỉ số vì có thể khiến binding không tạo ra tập phần tử như mong đợi.

Tên thuộc tính trong bảng cấu hình springdoc là **urlsPrimaryName**. Với YAML có thể dùng cách viết kebab-case **urls-primary-name** theo quy tắc relaxed binding của Spring Boot.

## 6. Kết hợp GroupedOpenApi với danh sách tài liệu

Một ứng dụng Spring Boot có thể tạo nhiều đặc tả bằng các bean **GroupedOpenApi**. Mỗi group được truy cập qua URL tài liệu riêng, mặc định có dạng **/v3/api-docs/{groupName}**. Những URL này có thể được đưa vào danh sách urls của Swagger UI.

Ví dụ khai báo nhóm:

~~~java
import org.springdoc.core.models.GroupedOpenApi;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class OpenApiGroupConfiguration {

    @Bean
    public GroupedOpenApi storeV1() {
        return GroupedOpenApi.builder()
            .group("store-v1")
            .pathsToMatch("/api/v1/**")
            .build();
    }

    @Bean
    public GroupedOpenApi storeV2() {
        return GroupedOpenApi.builder()
            .group("store-v2")
            .pathsToMatch("/api/v2/**")
            .build();
    }

    @Bean
    public GroupedOpenApi admin() {
        return GroupedOpenApi.builder()
            .group("admin")
            .pathsToMatch("/api/admin/**")
            .build();
    }
}
~~~

Cấu hình Swagger UI:

~~~yaml
springdoc:
  swagger-ui:
    urls:
      - name: Store API v1
        url: /v3/api-docs/store-v1
      - name: Store API v2
        url: /v3/api-docs/store-v2
      - name: Admin API
        url: /v3/api-docs/admin
    urls-primary-name: Store API v2
~~~

Mỗi group được tạo từ bộ lọc riêng, vì vậy danh sách giao diện phản ánh các tài liệu do ứng dụng cung cấp. Không cần tạo file OpenAPI tĩnh chỉ để liệt kê các group nếu springdoc đã tạo chúng và Swagger UI có thể truy cập endpoint tương ứng.

Khi springdoc đã tự tạo danh sách group trong swagger-config, có thể giữ cấu hình mặc định để Swagger UI hiển thị các group đó. Ví dụ khai báo **urls** tường minh ở trên dành cho trường hợp muốn tự kiểm soát tên hiển thị, URL hoặc trộn tài liệu do ứng dụng sinh với tài liệu từ dịch vụ ngoài. Danh sách **urls** chỉ quyết định tài liệu nào xuất hiện trong giao diện; nó không tạo group và không thay thế bộ lọc path/package của **GroupedOpenApi**.

Nếu thay đổi **springdoc.api-docs.path**, đường dẫn mặc định **/v3/api-docs** sẽ thay đổi. Nếu ứng dụng có **server.servlet.context-path**, URL công khai cũng cần bao gồm context path. Hãy kiểm tra URL group thực tế trên môi trường chạy thay vì sao chép đường dẫn mặc định một cách máy móc.

## 7. Dùng nguồn đặc tả từ nhiều dịch vụ

Danh sách urls cũng có thể trỏ đến các dịch vụ khác nhau, không nhất thiết tất cả tài liệu đều do cùng một ứng dụng Spring Boot sinh ra:

~~~yaml
springdoc:
  swagger-ui:
    urls:
      - name: Identity API
        url: https://identity.example.com/v3/api-docs
      - name: Billing API
        url: https://billing.example.com/openapi.yaml
      - name: Inventory API
        url: https://inventory.example.com/openapi.json
    urls-primary-name: Identity API
~~~

Đây là cách xây dựng một trang tài liệu tổng hợp cho nhiều dịch vụ. Mỗi tài liệu vẫn độc lập: có server, security scheme, schema và version riêng. Swagger UI chỉ cung cấp giao diện chọn và hiển thị; nó không hợp nhất các path của nhiều tài liệu thành một OpenAPI document.

Nếu muốn tạo một đặc tả tổng hợp duy nhất từ nhiều dịch vụ, cần một bước hợp nhất hoặc API gateway/documentation aggregator riêng. Cấu hình **urls** chỉ tạo danh sách lựa chọn giữa các tài liệu.

## 8. Dùng configUrl khi cần quản lý cấu hình Swagger UI riêng

Trong springdoc, giá trị mặc định của **springdoc.swagger-ui.configUrl** là **/v3/api-docs/swagger-config**. Đây là endpoint cấu hình được springdoc tạo tự động. Nó thường trả về các thuộc tính mà Swagger UI cần để tải tài liệu và hiển thị giao diện.

Nếu muốn Swagger UI tải một file cấu hình riêng, có thể đặt configUrl:

~~~yaml
springdoc:
  swagger-ui:
    config-url: /config/swagger-ui-config.json
~~~

File cấu hình có thể chứa một URL:

~~~json
{
  "url": "/openapi/store-api.yaml",
  "deepLinking": true,
  "docExpansion": "none"
}
~~~

Hoặc một danh sách tài liệu:

~~~json
{
  "urls": [
    {
      "name": "Store API v1",
      "url": "/openapi/store-v1.yaml"
    },
    {
      "name": "Store API v2",
      "url": "/openapi/store-v2.yaml"
    }
  ],
  "urls.primaryName": "Store API v2",
  "deepLinking": true
}
~~~

Khi thay configUrl bằng file riêng, ứng dụng chịu trách nhiệm phục vụ file đó và duy trì đầy đủ các thuộc tính Swagger UI cần thiết. Không nhầm file cấu hình này với tài liệu OpenAPI: config JSON có các khóa như url, urls và docExpansion; file OpenAPI có cấu trúc openapi, info, paths và components.

Nếu chỉ muốn đổi nguồn tài liệu, hãy dùng **springdoc.swagger-ui.url** hoặc **springdoc.swagger-ui.urls**. Không cần thay configUrl chỉ để trỏ đến một file OpenAPI.

## 9. Cấu hình Swagger UI độc lập bằng JavaScript

Khi triển khai Swagger UI độc lập, không dùng starter springdoc để phục vụ giao diện, có thể cấu hình trực tiếp trong JavaScript:

~~~javascript
const ui = SwaggerUIBundle({
  dom_id: "#swagger-ui",
  url: "https://api.example.com/v3/api-docs",
  deepLinking: true
});
~~~

Với nhiều tài liệu:

~~~javascript
const ui = SwaggerUIBundle({
  dom_id: "#swagger-ui",
  urls: [
    {
      name: "Store API v1",
      url: "https://api.example.com/v3/api-docs/store-v1"
    },
    {
      name: "Store API v2",
      url: "https://api.example.com/v3/api-docs/store-v2"
    }
  ],
  "urls.primaryName": "Store API v2",
  deepLinking: true
});
~~~

Trong cấu hình JavaScript, **url** nhận một chuỗi URL; **urls** nhận một mảng object gồm name và url. Khi dùng urls, url đơn bị bỏ qua. **urls.primaryName** là một khóa có dấu chấm trong tên thuộc tính cấu hình Swagger UI, không phải một object JavaScript lồng nhau.

Có thể truyền **spec** thay cho URL nếu đã có sẵn một object OpenAPI trong JavaScript. Khi dùng spec, Swagger UI không phân tích tham số url. Đây là trường hợp nhúng trực tiếp đặc tả vào ứng dụng frontend, không phải lựa chọn phù hợp nếu muốn tải file OpenAPI độc lập từ máy chủ.

## 10. Phân biệt url của Swagger UI với servers trong OpenAPI

Một nguồn gây lỗi phổ biến là dùng nhầm URL tải tài liệu với URL gửi request API. Hai thuộc tính này có mục đích khác nhau:

- **springdoc.swagger-ui.url** hoặc từng mục trong **urls** chỉ định nơi tải tài liệu OpenAPI.
- **servers** trong OpenAPI chỉ định server gốc để Swagger UI gửi request khi người dùng bấm Try it out.

Ví dụ tài liệu được tải từ **https://docs.example.com/openapi/store.yaml**, nhưng API thực tế chạy ở **https://api.example.com/store**:

~~~yaml
openapi: 3.1.0
info:
  title: Store API
  version: 1.0.0
servers:
  - url: https://api.example.com/store
paths:
  /orders:
    get:
      summary: Liệt kê đơn hàng
      responses:
        '200':
          description: Danh sách đơn hàng
~~~

Trong trường hợp này, Swagger UI tải file từ host docs, nhưng request thử nghiệm được gửi đến host api. Cần cấu hình CORS cho cả việc tải đặc tả và việc gọi API nếu chúng nằm khác origin.

Nếu servers không được khai báo trong tài liệu, Swagger UI có thể dùng server mặc định theo quy tắc của OpenAPI. Hãy kiểm tra URL được hiển thị trong ô request của Try it out để xác nhận server đang trỏ đúng môi trường.

## 11. CORS, xác thực và quyền truy cập tài liệu

Swagger UI tải tài liệu bằng request từ trình duyệt. Nếu trang giao diện và file OpenAPI có origin khác nhau, máy chủ cung cấp tài liệu cần cho phép CORS từ origin của Swagger UI.

Ví dụ:

- Giao diện: **https://docs.example.com**
- Đặc tả: **https://api.example.com/v3/api-docs**
- API thực tế: **https://service.example.com**

Trong trường hợp này, trình duyệt cần được phép đọc đặc tả từ **api.example.com**. Khi Try it out gửi request đến **service.example.com**, API đó cũng cần CORS phù hợp.

Swagger UI và API cùng host, port, protocol thường không cần cấu hình CORS cho việc tải tài liệu. Nếu nằm khác origin, hãy cấu hình allow-origin, allow-methods và allow-headers phù hợp; không mở wildcard tùy tiện khi dùng credentials.

Nếu tài liệu được bảo vệ bằng đăng nhập, cần bảo đảm trình duyệt có thể truy cập endpoint config và endpoint OpenAPI. Nếu tài liệu ở dịch vụ khác, xác định rõ cơ chế xác thực mà trình duyệt sử dụng. Không nhúng mật khẩu, client secret hoặc bearer token cố định trong file cấu hình công khai hay URL query string.

Việc đưa một tài liệu vào danh sách urls không cấp quyền truy cập tài liệu đó. Endpoint OpenAPI và endpoint API vẫn phải được bảo vệ bằng Spring Security, gateway hoặc cơ chế xác thực của dịch vụ. Ẩn một mục khỏi danh sách cũng không thay thế kiểm soát truy cập.

## 12. Đường dẫn tương đối, context path và reverse proxy

Đường dẫn đặc tả cần được phân giải đúng trong môi trường triển khai. Ví dụ ứng dụng có context path:

~~~properties
server.servlet.context-path=/store
~~~

Khi đó Swagger UI mặc định có thể được truy cập dưới **/store/swagger-ui.html**, còn OpenAPI mặc định dưới **/store/v3/api-docs**. Nếu cấu hình URL tuyệt đối từ gốc domain là **/v3/api-docs**, request có thể bỏ mất prefix **/store**.

Với cùng một ứng dụng, có thể dùng URL tương đối theo context path mà springdoc quản lý hoặc cung cấp URL công khai đầy đủ khi có reverse proxy. Với tài liệu ngoài ứng dụng, URL HTTPS tuyệt đối thường dễ kiểm soát hơn. Khi reverse proxy thay đổi prefix, hãy xác minh URL mà trình duyệt thực sự yêu cầu.

Không dùng **localhost** trong cấu hình được triển khai cho người dùng bên ngoài. Trong trình duyệt của họ, localhost trỏ về máy của chính họ, không phải máy chủ Spring Boot. Tương tự, hostname nội bộ hoặc địa chỉ IP private có thể chỉ truy cập được trong mạng phát triển.

## 13. Ưu tiên cấu hình và query string

Swagger UI hỗ trợ cấu hình từ đối tượng JavaScript, file cấu hình được tải qua configUrl và query string của trang. Theo tài liệu Swagger UI, thứ tự ưu tiên chung từ thấp đến cao là:

1. Đối tượng cấu hình truyền trực tiếp vào SwaggerUIBundle.
2. File cấu hình được tải qua configUrl.
3. Các tham số cấu hình truyền trong query string của URL giao diện.

Tuy nhiên, springdoc đặt **springdoc.swagger-ui.queryConfigEnabled** mặc định là false và tài liệu ghi nhận tính năng này đã bị vô hiệu hóa từ v1.6.0 vì lý do bảo mật. Không bật lại chỉ để người dùng có thể ghi đè URL tài liệu qua query string nếu chưa đánh giá rủi ro. Hãy quản lý nguồn đặc tả bằng application.yml, application.properties hoặc file cấu hình được kiểm soát.

Nếu giao diện hiển thị sai nguồn tài liệu, hãy kiểm tra endpoint **/v3/api-docs/swagger-config** để xem cấu hình mà springdoc trả về, sau đó kiểm tra request tải đặc tả trong tab Network của trình duyệt. Cách này giúp xác định lỗi nằm ở configUrl, danh sách urls, URL tài liệu hay quyền truy cập.

## 14. Kiểm tra nguồn đặc tả

Trước khi công bố Swagger UI, hãy kiểm tra từng URL nguồn độc lập:

~~~bash
curl -i http://localhost:8080/v3/api-docs
curl -i http://localhost:8080/v3/api-docs/store-v1
curl -i http://localhost:8080/v3/api-docs/admin
~~~

Với file YAML:

~~~bash
curl -i http://localhost:8080/v3/api-docs.yaml
~~~

Xác nhận:

- Request trả về status thành công và đúng nội dung JSON hoặc YAML.
- Body có cấu trúc OpenAPI hợp lệ, có trường openapi và info.
- URL được khai báo trong cấu hình trỏ đúng file hoặc group.
- Các name trong urls không trùng nhau và urls-primary-name khớp một name.
- Nếu URL ở origin khác, CORS cho phép trình duyệt đọc tài liệu.
- servers trong tài liệu trỏ đến API thực tế cần thử nghiệm.

Sau đó mở Swagger UI, chọn từng tài liệu trong danh sách và kiểm tra:

1. Tiêu đề, phiên bản và operation thuộc đúng API được chọn.
2. Chuyển đổi giữa các tài liệu không làm hiển thị nhầm đặc tả.
3. Try it out dùng đúng server và path.
4. Không có lỗi CORS, 404, 401 hoặc 403 khi tải config và tài liệu.
5. Tài liệu có thể tải được sau khi triển khai dưới context path hoặc reverse proxy.

## 15. Lỗi thường gặp và cách xử lý

| Biểu hiện | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Swagger UI vẫn hiển thị Petstore hoặc tài liệu mặc định | Chưa cấu hình URL mong muốn hoặc default URL chưa bị tắt | Đặt url/urls và cân nhắc disable-swagger-default-url |
| Cấu hình url không có tác dụng | Đã khai báo urls hoặc spec, khiến url bị bỏ qua | Chỉ dùng url đơn hoặc chuyển nguồn vào danh sách urls |
| Danh sách chọn tài liệu không xuất hiện | urls không được cấu hình hoặc Topbar plugin không hoạt động | Kiểm tra config JSON và preset/plugin của Swagger UI |
| Giao diện mở sai tài liệu mặc định | urls-primary-name không khớp name hoặc không được bind | Dùng đúng tên trong danh sách và kiểm tra swagger-config |
| Tài liệu trả 404 | URL thiếu context path, sai prefix proxy hoặc sai tên group | Mở URL trực tiếp và đối chiếu với đường dẫn công khai |
| Swagger UI báo lỗi parse | URL trả HTML, trang đăng nhập hoặc file không phải OpenAPI | Kiểm tra status, Content-Type và body trong Network |
| Tài liệu từ dịch vụ khác không tải được | CORS, xác thực hoặc TLS chặn trình duyệt | Cấu hình CORS, quyền đọc và chứng chỉ phù hợp |
| Tài liệu tải được nhưng Try it out gọi sai host | Nhầm URL tải đặc tả với servers.url | Sửa servers trong OpenAPI và kiểm tra request preview |
| UI hoạt động trong máy local nhưng lỗi khi deploy | Cấu hình dùng localhost hoặc hostname nội bộ | Dùng URL có thể truy cập từ trình duyệt người dùng |
| Đổi configUrl khiến UI không còn các group | File cấu hình riêng không khai báo urls hoặc url cần thiết | Bổ sung danh sách tài liệu vào config JSON hoặc quay về configUrl mặc định |

## 16. Checklist cấu hình

- [ ] Chọn một URL đơn hay danh sách urls theo số lượng tài liệu cần hiển thị.
- [ ] URL trỏ đến JSON/YAML OpenAPI, không trỏ đến trang HTML Swagger UI.
- [ ] Nếu dùng nhiều tài liệu, mỗi name và URL đều duy nhất.
- [ ] urls-primary-name khớp chính xác một name trong danh sách.
- [ ] Đã phân biệt configUrl với URL của tài liệu.
- [ ] Đã kiểm tra đường dẫn sau context path và reverse proxy.
- [ ] CORS cho phép tải đặc tả và gọi API khi khác origin.
- [ ] servers trong tài liệu trỏ đến API server phù hợp.
- [ ] Không nhúng secret hoặc token cố định vào URL/cấu hình công khai.
- [ ] Đã mở từng tài liệu trong Swagger UI và thử request trong môi trường kiểm thử.

## 17. Tài liệu tham khảo chính thức

- [Swagger UI — Configuration](https://swagger.io/docs/open-source-tools/swagger-ui/usage/configuration/) — tham số url, urls, urls.primaryName, configUrl, spec và thứ tự ưu tiên cấu hình.
- [springdoc-openapi — Configuration Properties](https://springdoc.org/properties.html) — thuộc tính springdoc.swagger-ui.url, configUrl, urls, urlsPrimaryName, disable-swagger-default-url và queryConfigEnabled.
- [springdoc-openapi — Getting Started](https://springdoc.org/getting-started.html) — URL Swagger UI, OpenAPI JSON/YAML và context path trong Spring Boot.
- [springdoc-openapi v2 — Features](https://springdoc.org/v2/features.html) — tích hợp Swagger UI và cách cấu hình các thuộc tính chính thức.
- [Swagger UI — CORS](https://swagger.io/docs/open-source-tools/swagger-ui/usage/cors/) — yêu cầu CORS khi giao diện và tài liệu hoặc API nằm khác origin.

Một URL đơn phù hợp với ứng dụng chỉ công bố một tài liệu. Danh sách urls phù hợp khi cần đưa nhiều phiên bản, nhiều nhóm hoặc nhiều dịch vụ vào cùng giao diện. Hãy giữ riêng URL tải đặc tả, URL cấu hình giao diện và server thực thi API; kiểm tra từng URL từ trình duyệt sẽ giúp Swagger UI hiển thị đúng tài liệu và gửi request đến đúng môi trường.
