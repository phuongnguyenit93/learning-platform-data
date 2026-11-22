# Phân biệt application/hal+json và application/json theo cấu hình Spring Data REST

## Mục tiêu

Sau bài này, bạn có thể phân biệt JSON thông thường với HAL JSON; hiểu cách Spring Data REST thương lượng media type qua HTTP headers; cấu hình media type mặc định; và điều khiển việc một request yêu cầu `application/json` nhận HAL hay legacy Spring Data representation.

## 1. JSON và HAL JSON khác nhau ở đâu?

`application/json` là media type tổng quát cho dữ liệu JSON. Nó cho biết nội dung được truyền theo cú pháp JSON, nhưng bản thân media type này không quy định cấu trúc hypermedia hoặc cách client khám phá các resource liên quan.

`application/hal+json` là media type dành cho HAL (Hypertext Application Language), một định dạng hypermedia dựa trên JSON. HAL bổ sung quy ước để biểu diễn liên kết và resource được nhúng trong tài liệu:

- `_links` chứa các liên kết như `self`, `profile` hoặc liên kết đến resource liên quan.
- `_embedded` chứa các resource khác được nhúng trong representation, ví dụ danh sách customer trong collection.
- Các relation name mô tả ý nghĩa của liên kết, giúp client khám phá API qua link thay vì phải tự ghép mọi URL.

Ví dụ HAL rút gọn:

```json
{
  "_links": {
    "self": { "href": "http://localhost:8080/customers" },
    "profile": { "href": "http://localhost:8080/profile/customers" }
  },
  "_embedded": {
    "customers": [
      {
        "name": "Ada",
        "_links": {
          "self": { "href": "http://localhost:8080/customers/1" }
        }
      }
    ]
  }
}
```

Đây vẫn là JSON hợp lệ, nhưng có cấu trúc HAL và thông tin điều hướng. Một JSON representation thông thường có thể chứa các thuộc tính domain như `id`, `name`, `email` mà không có `_links` hoặc `_embedded`. Vì vậy, hai media type đều dùng cú pháp JSON nhưng không đồng nghĩa về hợp đồng representation.

## 2. Spring Data REST hỗ trợ cả hai media type

Các repository resources của Spring Data REST hỗ trợ `application/hal+json` và `application/json` cho nhiều thao tác như đọc collection, đọc item, tạo và cập nhật resource. Với HAL, response có các link hypermedia để client khám phá API. Với JSON thông thường, representation không nhất thiết mang các điều khiển hypermedia của HAL.

Spring Data REST dùng content negotiation để chọn representation dựa trên request headers và cấu hình. Cần phân biệt hai header:

- **`Accept`** do client gửi để cho server biết client muốn nhận response theo media type nào.
- **`Content-Type`** mô tả media type của body mà client gửi lên server, thường gặp ở các request `POST`, `PUT` hoặc `PATCH`.

Ví dụ client yêu cầu HAL:

```http
GET /customers HTTP/1.1
Host: localhost:8080
Accept: application/hal+json
```

Client yêu cầu JSON tổng quát:

```http
GET /customers HTTP/1.1
Host: localhost:8080
Accept: application/json
```

Với request tạo customer, `Content-Type` mô tả body gửi lên, còn `Accept` mô tả response mong muốn:

```http
POST /customers HTTP/1.1
Content-Type: application/json
Accept: application/hal+json

{"name":"Ada"}
```

Trong ví dụ này, body gửi lên là JSON thông thường; client muốn server trả representation HAL sau khi tạo resource. Nếu endpoint và cấu hình cho phép, hai lựa chọn này có thể khác nhau trong cùng một request.

## 3. Hành vi mặc định khi client gửi Accept: application/json

Spring Data REST có cấu hình `useHalAsDefaultJsonMediaType`. Giá trị mặc định của cấu hình này là `true`.

Khi giá trị là `true`, request gửi `Accept: application/json` vẫn được phục vụ bằng HAL như representation JSON mặc định. Response thường có `Content-Type: application/hal+json` và body chứa cấu trúc HAL.

Khi giá trị là `false`, request gửi `Accept: application/json` nhận legacy Spring Data representation thay vì HAL. Đây là lựa chọn tương thích khi client cũ mong đợi dạng JSON trước đây và không xử lý các cấu trúc hypermedia của HAL.

Có thể hình dung kết quả như sau:

| Accept của client | `useHalAsDefaultJsonMediaType=true` | `useHalAsDefaultJsonMediaType=false` |
| --- | --- | --- |
| `application/hal+json` | HAL JSON | HAL JSON |
| `application/json` | HAL được dùng làm representation JSON mặc định | Legacy Spring Data JSON |
| Không gửi `Accept` | Dùng default media type đã cấu hình | Dùng default media type đã cấu hình |

Cấu hình này chỉ điều khiển cách Spring Data REST xử lý yêu cầu `application/json` theo quy ước mặc định. Nếu client yêu cầu rõ `application/hal+json`, đó là yêu cầu trực tiếp đối với HAL.

## 4. Cấu hình bằng Spring Boot properties

Có hai thuộc tính cần phân biệt:

- `spring.data.rest.default-media-type` xác định media type mặc định khi request không chỉ định media type phù hợp.
- `spring.hateoas.use-hal-as-default-json-media-type` quyết định liệu request chấp nhận `application/json` có được phục vụ bằng HAL hay không. Mặc định là `true`.

Để ưu tiên HAL cho API Spring Data REST:

```properties
spring.data.rest.default-media-type=application/hal+json
spring.hateoas.use-hal-as-default-json-media-type=true
```

Với cấu hình này, request không gửi `Accept` dùng HAL làm media type mặc định; request `Accept: application/json` cũng được phục vụ bằng HAL theo thiết lập mặc định.

Nếu cần giữ legacy JSON cho các client gửi `Accept: application/json`:

```properties
spring.data.rest.default-media-type=application/json
spring.hateoas.use-hal-as-default-json-media-type=false
```

Khi đó request không chỉ định `Accept` dùng JSON làm media type mặc định; request `Accept: application/json` được xử lý theo legacy Spring Data representation. Client cần HAL vẫn có thể yêu cầu rõ `Accept: application/hal+json`.

Tên property `spring.hateoas.use-hal-as-default-json-media-type` thuộc cấu hình Spring HATEOAS trong Spring Boot. Hãy dùng property có trong phiên bản Spring Boot/Spring Data REST của dự án; với ứng dụng không dùng Spring Boot hoặc cần cấu hình trực tiếp, có thể dùng API Java ở phần tiếp theo.

## 5. Cấu hình bằng RepositoryRestConfigurer

Trong cấu hình Java, dùng `RepositoryRestConfiguration`:

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.data.rest.core.config.RepositoryRestConfiguration;
import org.springframework.data.rest.webmvc.config.RepositoryRestConfigurer;
import org.springframework.http.MediaType;
import org.springframework.web.servlet.config.annotation.CorsRegistry;

@Configuration
public class RestConfiguration implements RepositoryRestConfigurer {

    @Override
    public void configureRepositoryRestConfiguration(
            RepositoryRestConfiguration config,
            CorsRegistry cors) {

        config.setDefaultMediaType(MediaType.parseMediaType(
                "application/hal+json"));
        config.useHalAsDefaultJsonMediaType(true);
    }
}
```

Để dùng legacy Spring Data representation khi client gửi `application/json`, đổi cấu hình thành:

```java
config.setDefaultMediaType(MediaType.APPLICATION_JSON);
config.useHalAsDefaultJsonMediaType(false);
```

Hai phương thức có vai trò riêng:

- `setDefaultMediaType(...)` chọn media type dự phòng khi request không chỉ định media type.
- `useHalAsDefaultJsonMediaType(...)` điều khiển việc `application/json` có được ánh xạ sang HAL hay không.

Đừng nhầm hai cấu hình này với việc bật hoặc tắt Spring Data REST, thay đổi repository path, hay thay đổi nội dung domain object được lưu trong database.

## 6. Kiểm tra response thực tế bằng curl

Có thể kiểm tra cùng một endpoint bằng hai giá trị `Accept`. Thêm `-i` để xem cả status line và response headers:

```bash
curl -i -H "Accept: application/hal+json" \
  http://localhost:8080/customers
```

```bash
curl -i -H "Accept: application/json" \
  http://localhost:8080/customers
```

Đọc header `Content-Type` trong response để xác định server đã chọn representation nào. Với HAL, body thường có `_links` và có thể có `_embedded`. Với legacy JSON, body được render theo representation JSON truyền thống của Spring Data REST.

Nếu muốn kiểm tra trường hợp không gửi `Accept`, gọi endpoint mà không thêm header này:

```bash
curl -i http://localhost:8080/customers
```

Kết quả sẽ phụ thuộc vào `spring.data.rest.default-media-type` hoặc `RepositoryRestConfiguration.setDefaultMediaType(...)`.

## 7. Lỗi thường gặp

**Client gửi Accept: application/json nhưng vẫn nhận HAL**

Đây là hành vi mặc định khi `useHalAsDefaultJsonMediaType=true`. Kiểm tra `spring.hateoas.use-hal-as-default-json-media-type` hoặc cấu hình `RepositoryRestConfiguration.useHalAsDefaultJsonMediaType(false)` nếu client cần legacy representation.

**Client muốn HAL nhưng response không có link**

Gửi rõ `Accept: application/hal+json`, sau đó kiểm tra response `Content-Type`. Nếu body vẫn không đúng kỳ vọng, kiểm tra cấu hình converter, phiên bản Spring HATEOAS và việc endpoint có phải resource do Spring Data REST quản lý hay không.

**Nhầm Content-Type với Accept**

Đặt `Content-Type: application/json` chỉ mô tả body request. Nó không yêu cầu response phải là JSON. Muốn yêu cầu response, đặt `Accept` tương ứng.

**Nhận 406 Not Acceptable**

Server không tìm được representation phù hợp với `Accept` mà client yêu cầu. Kiểm tra media type được hỗ trợ bởi endpoint, header `Accept` và cấu hình mặc định.

**Nhận 415 Unsupported Media Type**

Media type của body request không được endpoint chấp nhận. Kiểm tra `Content-Type` và tài liệu endpoint. Một số endpoint association có thể yêu cầu media type chuyên biệt như `text/uri-list`; không phải mọi request body đều dùng `application/json`.

## 8. Chọn representation theo nhu cầu client

- Ưu tiên **`application/hal+json`** khi client cần khám phá API qua các link, theo dõi relation và giảm phụ thuộc vào URL được hard-code.
- Dùng **`application/json` với HAL mặc định** khi client gửi media type JSON tổng quát nhưng ứng dụng vẫn muốn giữ hypermedia.
- Chỉ chuyển **`useHalAsDefaultJsonMediaType=false`** khi có yêu cầu tương thích rõ ràng với client đang phụ thuộc legacy Spring Data representation.
- Đặt **default media type** để request không có `Accept` nhận được representation dự kiến; vẫn hướng dẫn client gửi `Accept` rõ ràng để hợp đồng API dễ hiểu.

Thay đổi từ legacy JSON sang HAL có thể ảnh hưởng đến client đang đọc trực tiếp cấu trúc response. Trước khi đổi cấu hình, hãy kiểm tra cách client deserialize response và có đang dựa vào tên trường hoặc cấu trúc JSON cũ hay không.

## Tóm tắt

- `application/json` là JSON tổng quát; `application/hal+json` là JSON theo quy ước hypermedia HAL.
- `Accept` chọn representation của response; `Content-Type` mô tả body request.
- `useHalAsDefaultJsonMediaType` mặc định là `true`: request `Accept: application/json` được phục vụ bằng HAL.
- Đặt giá trị này thành `false` để request `application/json` nhận legacy Spring Data representation.
- `spring.data.rest.default-media-type` hoặc `setDefaultMediaType(...)` chỉ định media type mặc định khi client không gửi yêu cầu cụ thể.

## Tài liệu tham khảo

- [Spring Data REST — Repository resources and supported media types](https://docs.spring.io/spring-data/rest/reference/repository-resources.html)
- [RepositoryRestConfiguration — API](https://docs.spring.io/spring-data/rest/reference/api/java/org/springframework/data/rest/core/config/RepositoryRestConfiguration.html)
- [Spring Boot — Common application properties](https://docs.spring.io/spring-boot/appendix/application-properties/)
- [Spring HATEOAS — Spring Boot](https://docs.spring.io/spring-boot/reference/web/spring-hateoas.html)
