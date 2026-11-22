# Cấu hình `returnBodyOnCreate`, `returnBodyOnUpdate` và ảnh hưởng của `Accept`

Spring Data REST tự động xuất bản các Spring Data repository thành REST resource. Khi client tạo entity bằng `POST` hoặc cập nhật entity đã tồn tại, server có thể trả representation của entity trong response body. Hai cấu hình `returnBodyOnCreate` và `returnBodyOnUpdate` quyết định response có chứa representation đó hay không.

## 1. Hai cấu hình điều khiển thao tác nào?

| Cấu hình | Thao tác | Ý nghĩa |
|---|---|---|
| `returnBodyOnCreate` | Tạo resource, thường qua `POST` trên collection resource | Quyết định có trả representation của entity vừa tạo hay không |
| `returnBodyOnUpdate` | Cập nhật resource đã tồn tại, thường qua `PUT` | Quyết định có trả representation sau cập nhật hay không |

Hai tùy chọn độc lập. Có thể bật body cho thao tác tạo nhưng tắt body cho thao tác cập nhật, hoặc ngược lại. Chúng chỉ điều khiển response body; không bật/tắt repository endpoint, không thay đổi cách lưu dữ liệu và không quyết định entity được tạo hay cập nhật thành công hay không. Response của thao tác xóa có cấu hình riêng là `returnBodyOnDelete`.

Trong API Java, cần phân biệt setter cấu hình với phương thức đánh giá quyết định theo request:

- `setReturnBodyOnCreate(Boolean)` và `setReturnBodyOnUpdate(Boolean)` thiết lập chính sách.
- `returnBodyOnCreate(String acceptHeader)` và `returnBodyOnUpdate(String acceptHeader)` đánh giá có trả body cho request dựa trên chính sách cùng giá trị `Accept`.

## 2. Ý nghĩa của ba giá trị Boolean

Các setter nhận `Boolean` (kiểu wrapper), nên có ba trạng thái:

| Giá trị | Kết quả |
|---|---|
| `true` | Luôn yêu cầu trả representation trong response body |
| `false` | Không trả representation trong response body |
| `null` | Để Spring Data REST quyết định dựa trên sự hiện diện của header `Accept` |

Khi không khai báo hai thuộc tính này, cấu hình mặc định giữ hành vi dựa trên `Accept`: request có header `Accept` thì Spring Data REST có thể trả body; request không có header `Accept` thì không render body. Đây là lý do cùng một endpoint có thể trả body với một HTTP client nhưng không có body với client khác.

Bảng dưới đây áp dụng riêng cho từng thao tác tạo hoặc cập nhật. Giả sử media type mà client yêu cầu được server hỗ trợ:

| Giá trị cấu hình | Request có `Accept` | Request không có `Accept` |
|---|---|---|
| `null` | Có body | Không có body |
| `true` | Có body | Có body |
| `false` | Không có body | Không có body |

## 3. Cấu hình bằng Spring Boot

Có thể khai báo trực tiếp trong `application.yml`:

~~~yaml
spring:
  data:
    rest:
      return-body-on-create: true
      return-body-on-update: true
~~~

Ví dụ trên yêu cầu trả representation cho cả thao tác tạo và cập nhật. Nếu chỉ muốn trả body khi tạo, đặt `return-body-on-create: true` và đặt `return-body-on-update: false`. Nếu muốn giữ quyết định phụ thuộc vào `Accept`, hãy bỏ thuộc tính tương ứng khỏi cấu hình thay vì đặt `false`.

Các khóa property tương ứng là:

- `spring.data.rest.return-body-on-create`
- `spring.data.rest.return-body-on-update`

Spring Boot bind các khóa này vào cấu hình Spring Data REST. Có thể đặt chúng trong file cấu hình theo profile, ví dụ `application-dev.yml` hoặc `application-prod.yml`, để từng môi trường có chính sách response phù hợp.

## 4. Cấu hình bằng Java với RepositoryRestConfigurer

Khi cần cấu hình bằng Java, đăng ký một bean `RepositoryRestConfigurer`:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.rest.webmvc.config.RepositoryRestConfigurer;

@Configuration
class SpringDataRestConfiguration {

    @Bean
    RepositoryRestConfigurer repositoryRestConfigurer() {
        return RepositoryRestConfigurer.withConfig(config -> {
            config.setReturnBodyOnCreate(true);
            config.setReturnBodyOnUpdate(true);
        });
    }
}
~~~

Đổi từng giá trị thành `false` nếu muốn bỏ response body cho thao tác tương ứng. Nếu hai thao tác cần cùng một chính sách, có thể dùng phương thức tiện ích:

~~~java
config.setReturnBodyForPutAndPost(true);
~~~

Phương thức tiện ích này thiết lập chính sách trả body cho cả `POST` và `PUT`. Dùng hai setter riêng khi cần kiểm soát độc lập thao tác tạo và cập nhật.

## 5. Header Accept ảnh hưởng như thế nào?

Hai header HTTP sau có mục đích khác nhau:

- `Content-Type` mô tả định dạng dữ liệu client gửi lên server, ví dụ `application/json`.
- `Accept` mô tả định dạng response mà client có thể nhận, ví dụ `application/hal+json`.

Khi chính sách body là `null`, sự hiện diện của `Accept` là tín hiệu để Spring Data REST quyết định có render representation hay không. Nếu đã đặt rõ `true` hoặc `false`, chính sách đó quyết định việc có body; `Accept` vẫn tham gia content negotiation để chọn media type của response.

Ví dụ:

~~~http
POST /items
Content-Type: application/json
Accept: application/hal+json
~~~

Client gửi JSON để tạo entity và yêu cầu nhận response dạng HAL JSON. Nếu cấu hình `returnBodyOnCreate` là `null` hoặc `true`, response có thể chứa representation của resource vừa tạo. Nếu cấu hình là `false`, body bị tắt dù request có `Accept`.

Chỉ gửi `Content-Type: application/json` không đồng nghĩa với việc client đã yêu cầu response body. Ngược lại, một số HTTP client tự thêm `Accept: */*` dù người dùng không cấu hình header này trong giao diện. Vì vậy, khi kiểm tra hành vi mặc định, cần xem header thực tế trên request được gửi đi.

Nếu `Accept` yêu cầu media type mà server không thể tạo, content negotiation có thể thất bại (thường là HTTP `406 Not Acceptable`). Trường hợp đó khác với việc cấu hình chủ động tắt response body.

## 6. Thử nghiệm bằng curl

Các đường dẫn `/items`, `/items/42` và các trường JSON dưới đây chỉ là ví dụ. Hãy thay bằng resource path do repository của ứng dụng xuất bản và các thuộc tính thực tế của entity.

**Tạo entity và yêu cầu representation:**

~~~bash
curl -i -X POST "http://localhost:8080/items" -H "Content-Type: application/json" -H "Accept: application/hal+json" -d '{"name":"Keyboard","status":"ACTIVE"}'
~~~

**Tạo entity nhưng bỏ header Accept:**

~~~bash
curl -i -X POST "http://localhost:8080/items" -H "Content-Type: application/json" -H "Accept:" -d '{"name":"Keyboard","status":"ACTIVE"}'
~~~

Trong curl, `-H "Accept:"` dùng để loại bỏ header `Accept` mặc định. Khi hai thuộc tính cấu hình vẫn là `null`, hai request trên giúp quan sát sự khác biệt về response body.

**Cập nhật entity và yêu cầu representation:**

~~~bash
curl -i -X PUT "http://localhost:8080/items/42" -H "Content-Type: application/json" -H "Accept: application/hal+json" -d '{"name":"Keyboard Pro","status":"ACTIVE"}'
~~~

Đối chiếu response của các request với ba trạng thái cấu hình `null`, `true` và `false`. Khi body được trả về, representation có thể chứa các liên kết HAL như `_links`, tùy media type và cấu hình serialization của ứng dụng.

## 7. Đọc response và xử lý tình huống không có body

Không nên kết luận thao tác thất bại chỉ vì response body rỗng. Với thao tác tạo, Spring Data REST thường trả header `Location` chứa URI của resource mới. Client có thể dùng URI đó để gửi `GET` và lấy representation. Với thao tác cập nhật, client có thể `GET` URI của resource vừa cập nhật nếu cần dữ liệu mới nhất.

Khi kỳ vọng có body nhưng không nhận được, kiểm tra theo thứ tự:

1. Giá trị hiệu lực của `spring.data.rest.return-body-on-create` hoặc `spring.data.rest.return-body-on-update` trong profile đang chạy.
2. HTTP method thực tế là thao tác tạo hay cập nhật; hai chính sách không thay thế nhau.
3. Header `Accept` thực tế trên request, kể cả header do Postman, browser hoặc HTTP library tự thêm.
4. Media type trong `Accept` có được server hỗ trợ hay không.
5. Response có bị gateway, proxy hoặc client wrapper loại bỏ body hay không.

Nếu body bị tắt có chủ đích, hãy kiểm tra status và header `Location` (đối với thao tác tạo), sau đó gọi `GET` resource khi cần representation. Body response cũng có thể tuân theo projection, Jackson mapping và định dạng HAL; không nên giả định nó luôn là JSON phẳng chỉ gồm các field của entity.

## 8. Chọn chính sách phù hợp

- **Client cần dữ liệu ngay sau khi tạo:** bật `returnBodyOnCreate`; client gửi `Accept` với media type server hỗ trợ và có thể dùng representation trả về để cập nhật giao diện.
- **Client cần dữ liệu sau khi cập nhật:** bật `returnBodyOnUpdate` nếu muốn tránh một request `GET` tiếp theo.
- **Muốn response gọn nhẹ:** đặt `false` cho thao tác không cần representation; client chỉ gọi `GET` khi cần đọc lại dữ liệu.
- **Muốn hành vi theo từng client:** giữ giá trị `null`, sau đó chủ động gửi hoặc bỏ `Accept` tùy nhu cầu của client. Cần lưu ý các thư viện HTTP có thể tự gửi `Accept: */*`.

## Tài liệu tham khảo

- [Spring Data REST — RepositoryRestConfiguration API](https://docs.spring.io/spring-data/rest/docs/4.4.x/api/org/springframework/data/rest/core/config/RepositoryRestConfiguration.html): setter, phương thức quyết định theo `Accept` và chính sách chung cho `POST`/`PUT`.
- [Spring Data REST — RepositoryRestConfigurer API](https://docs.spring.io/spring-data/rest/docs/4.3.5/api/org/springframework/data/rest/webmvc/config/RepositoryRestConfigurer.html): đăng ký cấu hình Java và `withConfig`.
- [Spring Boot 3.3 — Common Application Properties](https://docs.spring.io/spring-boot/3.3/appendix/application-properties/): các khóa `spring.data.rest.return-body-on-create` và `spring.data.rest.return-body-on-update`.
- [Spring Guide — Accessing JPA Data with REST](https://spring.io/guides/gs/accessing-data-rest): ví dụ response `POST`, header `Location` và các tùy chọn trả representation.
