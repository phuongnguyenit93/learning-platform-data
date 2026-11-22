# Tùy chỉnh URI định danh bằng EntityLookup và withEntityLookup trong Spring Data REST

## Mục tiêu

Mặc định, Spring Data REST tạo URI tài nguyên đơn từ đường dẫn collection cộng với khóa định danh của entity trong datastore. Ví dụ, một `User` có khóa chính `id = 42` thường được truy cập tại:

~~~text
GET /api/users/42
~~~

Trong nhiều hệ thống, khóa chính chỉ có ý nghĩa nội bộ. API có thể muốn định danh tài nguyên bằng một giá trị nghiệp vụ ổn định và duy nhất, chẳng hạn `username`, `slug`, mã nhân viên hoặc mã khách hàng. Spring Data REST hỗ trợ việc này thông qua `EntityLookup`.

`EntityLookup` cho Spring Data REST biết hai chiều ánh xạ:

1. Lấy định danh công khai từ một entity để tạo URI và self link.
2. Tìm lại entity khi client gửi yêu cầu tới URI chứa định danh công khai đó.

Có thể đăng ký ánh xạ bằng API cấu hình `RepositoryRestConfiguration.withEntityLookup()`, hoặc tự cung cấp một bean triển khai `EntityLookup` (thường kế thừa `EntityLookupSupport`).

## 1. Hiểu định danh URI và khóa chính

Giả sử bảng User có dữ liệu:

| id (khóa chính) | username | fullName |
| ---: | --- | --- |
| 42 | an.nguyen | An Nguyen |
| 57 | binh.tran | Binh Tran |

Nếu không tùy chỉnh, Spring Data REST tạo item URI theo khóa chính:

- `/api/users/42`
- `/api/users/57`

Sau khi ánh xạ theo username, URI có thể là:

- `/api/users/an.nguyen`
- `/api/users/binh.tran`

Đây là thay đổi cách định danh tài nguyên trong REST API. Nó **không đổi khóa chính trong database**, không sửa quan hệ JPA và không thay thế `@Id`. Repository vẫn có thể dùng `Long` làm kiểu khóa chính cho các thao tác nội bộ.

Giá trị dùng làm URI phải xác định duy nhất một entity trong phạm vi repository, ổn định trong suốt thời gian client có thể lưu hoặc chia sẻ URI, và phù hợp để đặt trong một path segment.

## 2. Chuẩn bị entity và repository

Ví dụ dùng `username` làm định danh công khai:

~~~java
@Entity
public class User {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false, unique = true, updatable = false)
    private String username;

    private String fullName;

    protected User() {
    }

    public String getUsername() {
        return username;
    }

    public String getFullName() {
        return fullName;
    }
}
~~~

`unique = true` bảo đảm database không cho hai bản ghi dùng chung username. `updatable = false` là một lựa chọn để giữ URI ổn định sau khi tạo; nếu nghiệp vụ cho phép đổi username, cần thiết kế rõ việc di chuyển URI và xử lý các client đang giữ link cũ.

Repository cần có phương thức tìm entity bằng chính giá trị sẽ xuất hiện trong URI:

~~~java
public interface UserRepository extends JpaRepository<User, Long> {

    Optional<User> findByUsername(String username);
}
~~~

Phương thức `findByUsername` có thể chỉ được dùng nội bộ bởi cơ chế lookup. Không bắt buộc phải xuất nó thành một search endpoint riêng.

## 3. Cách khuyến nghị: đăng ký bằng withEntityLookup()

Với Java hiện đại, cách ngắn gọn nhất là dùng method reference. Đăng ký một `RepositoryRestConfigurer` bean:

~~~java
@Configuration
public class UserRestConfiguration {

    @Bean
    RepositoryRestConfigurer userEntityLookup() {
        return RepositoryRestConfigurer.withConfig(config -> {
            config.withEntityLookup()
                    .forRepository(UserRepository.class)
                    .withIdMapping(User::getUsername)
                    .withLookup(UserRepository::findByUsername);
        });
    }
}
~~~

Các import chính:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.rest.webmvc.config.RepositoryRestConfigurer;
~~~

Chuỗi cấu hình có ba phần:

- `withEntityLookup()`: lấy registrar để khai báo cách định danh và tìm entity.
- `forRepository(UserRepository.class)`: giới hạn ánh xạ cho repository User.
- `withIdMapping(User::getUsername)`: ánh xạ từ entity sang giá trị định danh công khai.
- `withLookup(UserRepository::findByUsername)`: ánh xạ ngược từ giá trị trên URI sang entity.

Trong ví dụ, `User::getUsername` trả về `String`; `UserRepository::findByUsername` nhận `String` và trả về `Optional<User>`. Kiểu dữ liệu đầu ra của mapping và kiểu tham số lookup cần tương thích với nhau.

Nếu dự án dùng phiên bản Spring Data REST có phương thức cấu hình một tham số, có thể viết class triển khai `RepositoryRestConfigurer` và override phương thức tương ứng. Với API 5.1.x, có thể dùng `RepositoryRestConfigurer.withConfig(Consumer<RepositoryRestConfiguration>)` như ví dụ trên để tránh phụ thuộc vào chữ ký callback có thêm `CorsRegistry`.

## 4. Vai trò của EntityLookup

`org.springframework.data.rest.core.support.EntityLookup<T>` là SPI (Service Provider Interface) mô tả cách Spring Data REST nhận diện một domain type và tra cứu entity theo định danh được yêu cầu.

Hai thao tác cốt lõi:

| Phương thức | Hướng ánh xạ | Trách nhiệm |
| --- | --- | --- |
| `getResourceIdentifier(T entity)` | Entity → URI identifier | Trả về giá trị được dùng trong item URI và self link. |
| `lookupEntity(Object id)` | URI identifier → Entity | Tìm entity tương ứng với giá trị client gửi trong URL. |

API hiện đại còn có `getLookupProperty()` để cung cấp tên thuộc tính dùng cho lookup khi có thể xác định. Nếu trả về `Optional.empty()`, Spring Data REST giả định thuộc tính định danh cũng là thuộc tính dùng để lookup.

Có thể kế thừa `EntityLookupSupport<T>` thay vì tự triển khai toàn bộ plugin contract. Lớp cơ sở suy ra domain type được hỗ trợ từ tham số generic `T`, nên không phải tự viết logic `supports(Class<?>)`.

## 5. Đăng ký EntityLookup dưới dạng Spring bean

Nếu cần logic ánh xạ phức tạp hơn method reference, có thể tạo một bean riêng:

~~~java
@Component
public class UserEntityLookup extends EntityLookupSupport<User> {

    private final UserRepository repository;

    public UserEntityLookup(UserRepository repository) {
        this.repository = repository;
    }

    @Override
    public Object getResourceIdentifier(User entity) {
        return entity.getUsername();
    }

    @Override
    public Optional<User> lookupEntity(Object id) {
        return repository.findByUsername(String.valueOf(id));
    }

    @Override
    public Optional<String> getLookupProperty() {
        return Optional.of("username");
    }
}
~~~

Các import chính:

~~~java
import java.util.Optional;

import org.springframework.stereotype.Component;
import org.springframework.data.rest.core.support.EntityLookupSupport;
~~~

Khi component scan phát hiện bean này, Spring Data REST có thể sử dụng nó cho domain type `User`. `EntityLookupSupport<User>` cho biết bean áp dụng cho User.

Trong ví dụ:

- `getResourceIdentifier` trả về username để xây dựng URI.
- `lookupEntity` gọi repository để tìm User bằng username.
- `getLookupProperty` khai báo thuộc tính tra cứu là `username`.

Chữ ký phương thức có thể khác ở các phiên bản Spring Data REST cũ. Với API 5.1.x, Javadoc khai báo `getResourceIdentifier(T)` trả về `Object` và `lookupEntity(Object)` trả về `Optional<T>`. Khi làm việc trên dự án cụ thể, luôn kiểm tra Javadoc theo phiên bản dependency đang dùng.

Chọn một cách cấu hình cho mỗi domain type: registrar qua `withEntityLookup()` hoặc bean `EntityLookup`. Tránh khai báo nhiều lookup cạnh tranh cho cùng một loại entity vì sẽ làm việc xác định mapping trở nên khó hiểu.

## 6. Luồng xử lý khi tạo và đọc URI

Giả sử User có `id = 42`, `username = "an.nguyen"`.

<escape>
Entity trong repository
        |
        | getResourceIdentifier(user)
        v
"an.nguyen"
        |
        v
/api/users/an.nguyen
</escape>

Khi client gọi `GET /api/users/an.nguyen`, Spring Data REST lấy phần định danh `an.nguyen`, gọi lookup tương ứng và nhận lại entity User. Cả hai chiều phải dùng cùng một quy tắc:

~~~text
User -> username -> URI path
URI path -> username -> UserRepository.findByUsername(...)
~~~

Nếu hai chiều không nhất quán, API có thể tạo self link mà chính nó không đọc lại được. Ví dụ, nếu `getResourceIdentifier` trả về username viết thường nhưng lookup so sánh phân biệt hoa thường với giá trị chuẩn hóa khác, request có thể không tìm thấy entity.

## 7. Kết quả trên REST API

Giả sử base path là `/api` và repository được xuất tại `/users`.

Đọc collection:

~~~http
GET /api/users
Accept: application/hal+json
~~~

Phản hồi HAL có thể chứa các item self link theo username:

~~~json
{
  "_embedded": {
    "users": [
      {
        "username": "an.nguyen",
        "fullName": "An Nguyen",
        "_links": {
          "self": {
            "href": "http://localhost:8080/api/users/an.nguyen"
          }
        }
      }
    ]
  },
  "_links": {
    "self": {
      "href": "http://localhost:8080/api/users"
    }
  }
}
~~~

Đọc một item bằng định danh mới:

~~~http
GET /api/users/an.nguyen
Accept: application/hal+json
~~~

Spring Data REST dùng `findByUsername("an.nguyen")` để lấy entity. Nếu không có username tương ứng, request item sẽ không tìm thấy tài nguyên và trả về phản hồi lỗi tương ứng (thông thường là HTTP 404).

Các link tới User được Spring Data REST tạo từ entity đó cũng có thể sử dụng định danh mới. Vì vậy, client nên theo `_links.self` và các hypermedia link trả về thay vì giữ quy tắc tự ghép URI dựa trên khóa chính số.

## 8. Phạm vi tác động và những điều không thay đổi

`EntityLookup` tập trung vào định danh của **item resource** cho repository được cấu hình.

| Thành phần | Có thay đổi không? | Giải thích |
| --- | --- | --- |
| URI item, ví dụ `/users/{id}` | Có | Phần định danh được thay bằng giá trị từ `getResourceIdentifier` hoặc `withIdMapping`. |
| Self link trong HAL | Có | Link item được tạo bằng định danh tùy chỉnh. |
| Cách tìm item theo URL | Có | Lookup dùng định danh URI để tìm entity. |
| Khóa chính database (`@Id`) | Không | Entity vẫn giữ khóa chính và repository vẫn dùng kiểu ID ban đầu. |
| Đường dẫn collection (`/users`) | Không | Dùng `@RepositoryRestResource(path = ...)` để đổi collection path. |
| Tên relation trong HAL | Không | Dùng cấu hình resource mapping hoặc `@RestResource` cho relation. |
| Việc expose trường ID trong JSON | Không trực tiếp | `exposeIdsFor(...)` là cấu hình riêng để hiển thị ID như một property. |

Không nhầm `EntityLookup` với `BackendIdConverter`. `EntityLookup` thay đổi giá trị định danh tài nguyên thông qua repository và thuộc tính nghiệp vụ. `BackendIdConverter` phục vụ các trường hợp cần tùy chỉnh cách chuyển đổi backend ID sang dạng URI và ngược lại, thường gắn với kiểu ID/datastore đặc thù.

## 9. Lựa chọn định danh công khai

Một thuộc tính phù hợp làm URI identifier nên đáp ứng các điều kiện sau:

1. **Duy nhất:** database nên có unique constraint hoặc cơ chế tương đương để tránh hai entity cùng định danh.
2. **Ổn định:** nếu username hoặc slug thay đổi, URI cũ có thể không còn truy cập được. Cân nhắc mã công khai bất biến nếu client cần lưu URI lâu dài.
3. **Không nhạy cảm:** không dùng email cá nhân, số điện thoại, mã nội bộ bí mật hoặc dữ liệu có thể tiết lộ thông tin người dùng.
4. **An toàn với URL:** tránh dấu gạch chéo `/` và các ký tự cần xử lý đặc biệt trong path segment. Nếu cần giá trị tự do, hãy encode đúng chuẩn hoặc dùng public identifier có định dạng URL-safe.
5. **Có quy tắc chuẩn hóa:** xác định rõ chữ hoa/chữ thường, khoảng trắng, Unicode và cách so sánh ở cả lúc tạo lẫn lúc lookup.

Không nên dùng tên hiển thị (`fullName`) làm định danh nếu tên có thể trùng hoặc thay đổi. Một `slug` duy nhất, username bất biến hoặc UUID công khai thường phù hợp hơn.

## 10. Kiểm thử mapping

Nên kiểm thử cả chiều tạo URI và chiều tra cứu. Ví dụ với Spring MVC Test:

~~~java
mockMvc.perform(get("/api/users/an.nguyen")
        .accept(MediaTypes.HAL_JSON))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$.username").value("an.nguyen"))
    .andExpect(jsonPath("$._links.self.href")
            .value(containsString("/api/users/an.nguyen")));
~~~

Kiểm tra thêm collection để xác nhận self link của từng item dùng định danh mới:

~~~java
mockMvc.perform(get("/api/users")
        .accept(MediaTypes.HAL_JSON))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$._embedded.users[0]._links.self.href")
            .value(containsString("/api/users/")));
~~~

Với một định danh không tồn tại:

~~~java
mockMvc.perform(get("/api/users/unknown-user")
        .accept(MediaTypes.HAL_JSON))
    .andExpect(status().isNotFound());
~~~

Các trường hợp cần kiểm tra trong ứng dụng:

- GET item bằng username trả đúng entity.
- Collection HAL tạo self link theo username.
- Định danh không tồn tại trả về 404.
- Hai entity không thể có cùng định danh.
- Các association link tới User vẫn dẫn tới URI hợp lệ.
- Các thao tác PUT/PATCH/DELETE trên item vẫn hoạt động với URI mới.
- Base path và reverse proxy không làm sai link được tạo.
- Nếu identifier có thay đổi, hành vi với URI cũ được xác định và kiểm thử.

## 11. Lỗi thường gặp

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- |
| GET bằng username trả 404 | `findByUsername` không tìm thấy, dữ liệu chưa được chuẩn hóa hoặc mapping hai chiều không khớp | Kiểm tra giá trị trong database và logic lookup. |
| Self link vẫn chứa số ID | Bean/configurer không được scan hoặc mapping đăng ký sai repository | Kiểm tra component scan, configurer bean và `forRepository`. |
| Hai entity tạo ra cùng URI | Giá trị định danh không unique | Tạo unique constraint và chọn khóa nghiệp vụ duy nhất. |
| URI bị lỗi khi có ký tự đặc biệt | Identifier không phù hợp path segment hoặc client không encode đúng | Dùng identifier URL-safe và kiểm tra URL encoding. |
| Một số endpoint hoạt động, endpoint khác không | Mapping chỉ áp dụng cho repository/domain type đã đăng ký | Xác định repository nào cần lookup riêng và đăng ký tương ứng. |
| Client cũ không tìm thấy item | Client vẫn dùng URI dựa trên khóa chính cũ | Có kế hoạch chuyển đổi API, cập nhật client hoặc cung cấp cơ chế tương thích. |

## 12. Tài liệu tham khảo

- [Spring Data REST — Customizing Spring Data REST](https://docs.spring.io/spring-data/rest/reference/customizing-sdr.html): mục “Customizing Item Resource URIs”, ví dụ `withEntityLookup()`, `withIdMapping` và `withLookup`.
- [Spring Data REST 5.1.2 API — EntityLookup](https://docs.spring.io/spring-data/rest/reference/api/java/org/springframework/data/rest/core/support/EntityLookup.html): hợp đồng SPI để ánh xạ entity sang định danh và lookup ngược.
- [Spring Data REST 5.1.x API — EntityLookupSupport](https://docs.spring.io/spring-data/rest/docs/5.1.x/api/org/springframework/data/rest/core/support/EntityLookupSupport.html): lớp cơ sở tự xác định domain type từ generic.
- [Spring Data REST 5.1.2 API — EntityLookupRegistrar](https://docs.spring.io/spring-data/rest/reference/api/java/org/springframework/data/rest/core/config/EntityLookupRegistrar.html): API đăng ký lookup theo repository.
- [Spring Data REST 5.1.2 API — RepositoryRestConfigurer](https://docs.spring.io/spring-data/rest/reference/api/java/org/springframework/data/rest/webmvc/config/RepositoryRestConfigurer.html): extension point cấu hình Spring Data REST.
