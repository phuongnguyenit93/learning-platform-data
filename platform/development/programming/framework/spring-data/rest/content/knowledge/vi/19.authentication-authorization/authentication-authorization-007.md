# Phân quyền đọc, tạo, sửa, xóa và thao tác liên kết

## Mục tiêu

Sau bài này, bạn có thể:

- Phân biệt quyền đọc, tạo, sửa và xóa tài nguyên trong Spring Data REST.
- Ánh xạ từng HTTP method vào quyền tương ứng.
- Bảo vệ các endpoint quan hệ (association resources) khi thêm, thay thế hoặc gỡ liên kết giữa hai tài nguyên.
- Kết hợp luật theo URL/HTTP method với kiểm tra quyền ở repository hoặc service.
- Kiểm tra cả quyền thao tác lẫn quyền sở hữu dữ liệu, tránh để người dùng sửa hoặc xóa tài nguyên của người khác.

## 1. Phân quyền diễn ra ở đâu?

Spring Data REST tự động xuất bản các repository thành REST endpoint. Ví dụ, repository `PersonRepository` có thể tạo collection endpoint `/people`, endpoint tài nguyên `/people/{id}` và các endpoint quan hệ như `/people/{id}/addresses`.

Việc endpoint được xuất bản không có nghĩa mọi người dùng đều được phép gọi nó. Cần tách hai câu hỏi:

- **Authentication (xác thực):** người gọi là ai?
- **Authorization (phân quyền):** người đó được phép thực hiện thao tác nào trên tài nguyên nào?

Spring Security thường là lớp kiểm soát chính cho các request đi vào ứng dụng. Có thể áp dụng luật theo HTTP method và đường dẫn trong `SecurityFilterChain`. Khi cần kiểm tra sâu hơn, chẳng hạn chỉ chủ sở hữu mới được sửa một bản ghi, có thể bổ sung method security ở repository hoặc service.

Một chính sách đầy đủ thường có nhiều lớp:

1. Request có được phép dùng HTTP method đó trên endpoint này không?
2. Người dùng có authority cần thiết không?
3. Người dùng có quyền trên bản ghi hoặc tài nguyên liên quan cụ thể không?
4. Repository có thực sự xuất bản thao tác đó không?

## 2. Ánh xạ CRUD vào HTTP method

Với một collection endpoint `/people`, các thao tác phổ biến được ánh xạ như sau:

| Nghiệp vụ | HTTP method | Endpoint ví dụ | Quyền thường dùng |
|---|---|---|---|
| Đọc danh sách | `GET` | `/people` | `people:read` |
| Đọc chi tiết | `GET` | `/people/42` | `people:read` |
| Tạo mới | `POST` | `/people` | `people:create` |
| Thay thế/cập nhật | `PUT` | `/people/42` | `people:update` |
| Cập nhật một phần | `PATCH` | `/people/42` | `people:update` |
| Xóa | `DELETE` | `/people/42` | `people:delete` |

Đây là cách đặt tên authority minh họa. Ứng dụng có thể dùng tên khác, nhưng cần thống nhất giữa nơi cấp authority và nơi kiểm tra authority.

Một vài điểm cần phân biệt:

- `GET` thường chỉ đọc dữ liệu. Nếu người dùng được xem danh sách nhưng không được xem một số bản ghi, chỉ kiểm tra quyền ở cấp endpoint là chưa đủ; cần lọc dữ liệu theo người dùng hoặc kiểm tra quyền trên từng tài nguyên.
- `POST` trên collection thường tạo tài nguyên mới.
- `PUT` thường thay thế trạng thái tài nguyên; `PATCH` thường cập nhật một phần.
- `DELETE` trên endpoint tài nguyên thường xóa tài nguyên đó.
- Các thao tác trên endpoint quan hệ cũng có thể dùng `POST`, `PUT` hoặc `DELETE`, nhưng ý nghĩa là thay đổi liên kết chứ không nhất thiết tạo/xóa bản ghi đích.

Spring Data REST chỉ xử lý những method mà repository và cấu hình exposure cho phép. Một HTTP method bị tắt ở tầng exposure sẽ không trở thành khả dụng chỉ vì người dùng có authority tương ứng.

## 3. Bảo vệ endpoint theo HTTP method bằng Spring Security

Ví dụ dưới đây minh họa chính sách cho tài nguyên `people`. Các authority như `people:read`, `people:create` là chuỗi quyền mà ứng dụng phải cấp cho người dùng hoặc token.

~~~java
@Configuration
public class SecurityConfig {

    @Bean
    SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                // Đọc collection, tài nguyên và association resource.
                .requestMatchers(HttpMethod.GET, "/people", "/people/**")
                    .hasAuthority("people:read")

                // Quyền thay đổi liên kết: đặt trước các luật CRUD tổng quát.
                .requestMatchers(HttpMethod.POST, "/people/*/addresses")
                    .hasAuthority("people:link")
                .requestMatchers(HttpMethod.PUT, "/people/*/address")
                    .hasAuthority("people:link")
                .requestMatchers(
                    HttpMethod.DELETE,
                    "/people/*/addresses/**",
                    "/people/*/address"
                ).hasAuthority("people:unlink")

                // CRUD trên chính tài nguyên Person.
                .requestMatchers(HttpMethod.POST, "/people")
                    .hasAuthority("people:create")
                .requestMatchers(HttpMethod.PUT, "/people/**")
                    .hasAuthority("people:update")
                .requestMatchers(HttpMethod.PATCH, "/people/**")
                    .hasAuthority("people:update")
                .requestMatchers(HttpMethod.DELETE, "/people/**")
                    .hasAuthority("people:delete")

                .anyRequest().denyAll()
            )
            .build();
    }
}
~~~

Trong ví dụ:

- Người có `people:read` được đọc tài nguyên.
- Người có `people:create` được tạo `Person`.
- Người có `people:update` được sửa `Person`.
- Người có `people:delete` được xóa `Person`.
- Người có `people:link` được thêm hoặc đặt liên kết địa chỉ.
- Người có `people:unlink` được gỡ liên kết địa chỉ.

Các luật association được đặt trước luật CRUD tổng quát để request thay đổi liên kết nhận đúng authority riêng. Nếu đặt một luật tổng quát khớp trước, request có thể bị áp dụng quyền rộng hơn dự kiến.

Đường dẫn `/people/*/addresses` và `/people/*/address` chỉ là ví dụ. Hãy thay chúng bằng đường dẫn association thực tế được Spring Data REST xuất bản trong ứng dụng. Tên đường dẫn thường phụ thuộc vào tên resource và association `rel`; association collection và association đơn có thể có cấu trúc khác nhau.

`hasAuthority("people:read")` so sánh đúng chuỗi authority. Nếu dùng `hasRole("ADMIN")`, Spring Security mặc định kiểm tra authority `ROLE_ADMIN`. Không trộn hai quy ước mà không hiểu cách authority được cấp.

Luật `anyRequest().denyAll()` là lựa chọn mặc định chặt chẽ cho ví dụ có danh sách endpoint được cho phép rõ ràng. Trong ứng dụng thực tế, cần bổ sung các endpoint hợp lệ khác như login, health check hoặc tài nguyên công khai theo chính sách của hệ thống.

## 4. Phân quyền trên association resource

Spring Data REST có thể xuất bản một association thành endpoint riêng. Ví dụ, một `Person` có nhiều `Address`:

- `GET /people/42/addresses`: đọc các địa chỉ đang liên kết với người số 42.
- `POST /people/42/addresses`: thêm một địa chỉ vào association collection.
- `DELETE /people/42/addresses/9`: gỡ địa chỉ số 9 khỏi association của người số 42.

Với association đơn, ví dụ một người có một địa chỉ chính:

- `GET /people/42/address`: đọc địa chỉ đang được liên kết.
- `PUT /people/42/address`: đặt hoặc thay thế địa chỉ được liên kết.
- `DELETE /people/42/address`: gỡ liên kết hiện tại nếu association hỗ trợ thao tác này.

Một request thêm địa chỉ vào association collection có thể có dạng:

~~~http
POST /people/42/addresses
Content-Type: text/uri-list

http://localhost:8080/addresses/9
~~~

Request trên gửi URI của tài nguyên đích. Nó yêu cầu Spring Data REST thêm liên kết giữa `Person` số 42 và `Address` số 9. Ý nghĩa chính là **liên kết hai tài nguyên**, không phải tạo mới bản ghi `Address` số 9.

Để thay địa chỉ chính của một người, request có thể là:

~~~http
PUT /people/42/address
Content-Type: text/uri-list

http://localhost:8080/addresses/12
~~~

Để gỡ một phần tử khỏi association collection:

~~~http
DELETE /people/42/addresses/9
~~~

Khi thiết kế quyền, nên quyết định riêng các câu hỏi sau:

- Ai được xem các liên kết?
- Ai được thêm liên kết?
- Ai được thay thế liên kết đơn?
- Ai được gỡ liên kết?
- Người dùng có được liên kết tới mọi tài nguyên đích hay chỉ tài nguyên mà họ được phép truy cập?

Một người có quyền sửa thông tin `Person` chưa chắc đã được quyền thay đổi quan hệ địa chỉ. Tương tự, có quyền xóa một liên kết không đồng nghĩa có quyền xóa bản ghi `Address` được liên kết. Hãy xác định rõ ranh giới giữa xóa quan hệ và xóa tài nguyên.

## 5. Bổ sung method security ở repository hoặc service

Luật theo URL và HTTP method giúp phân biệt `POST`, `PUT`, `PATCH`, `DELETE`. Với những điều kiện gắn với dữ liệu cụ thể, có thể bật method security:

~~~java
@Configuration
@EnableMethodSecurity
public class MethodSecurityConfig {
}
~~~

Sau đó có thể bảo vệ repository method bằng `@PreAuthorize`:

~~~java
@RepositoryRestResource
public interface PersonRepository extends JpaRepository<Person, Long> {

    @Override
    @PreAuthorize("hasAuthority('people:read')")
    Page<Person> findAll(Pageable pageable);

    @Override
    @PreAuthorize("@personAccess.canSave(authentication, #p0)")
    <S extends Person> S save(S entity);

    @Override
    @PreAuthorize("@personAccess.canDelete(authentication, #p0)")
    void deleteById(Long id);
}
~~~

`personAccess` là bean do ứng dụng tự triển khai. `canSave` có thể phân biệt tạo mới và cập nhật dựa trên ID của entity: entity chưa có ID cần quyền tạo; entity đã tồn tại cần quyền cập nhật và kiểm tra chủ sở hữu. `canDelete` kiểm tra quyền xóa và quyền trên bản ghi cụ thể. Các kiểm tra này bổ sung cho request matcher; request vẫn phải vượt qua cả hai lớp.

Không nên giả định mọi phương thức nội bộ mà framework gọi đều đi qua một service tùy ý của ứng dụng. Khi dùng Spring Data REST, hãy đặt kiểm tra tại điểm thực sự được gọi trong luồng repository, hoặc dùng custom repository method/event handler phù hợp với thiết kế. Một số luồng cập nhật/xóa có thể cần đọc bản ghi trước khi thực hiện; hãy thiết kế quyền đọc nội bộ phù hợp và kiểm thử request thực tế để tránh vô tình chặn thao tác hợp lệ.

## 6. Kiểm tra quyền trên từng tài nguyên

Quyền `people:update` chỉ trả lời câu hỏi người dùng có quyền sửa loại tài nguyên `Person` hay không. Nó chưa chứng minh người đó được sửa mọi `Person`.

Ví dụ, hệ thống có thể áp dụng quy tắc:

- Người dùng chỉ sửa được `Person` do mình sở hữu.
- Quản trị viên sửa được mọi `Person`.
- Người dùng chỉ được liên kết địa chỉ mà họ có quyền đọc hoặc quản lý.

Có thể dùng một bean kiểm tra quyền trong biểu thức `@PreAuthorize`:

~~~java
@PreAuthorize(
    "hasAuthority('people:update') and " +
    "@personAccess.canUpdate(authentication, #personId)"
)
public Person updatePerson(Long personId, UpdatePersonCommand command) {
    // Tải bản ghi hiện có, áp dụng thay đổi hợp lệ và lưu.
}
~~~

Đây là ví dụ cho một service operation do ứng dụng gọi. Nếu REST endpoint được Spring Data REST xuất bản trực tiếp từ repository, hãy đặt cùng quy tắc ở repository method hoặc cơ chế mở rộng phù hợp; annotation trên một service không tự bảo vệ repository mà không đi qua service đó.

Bean kiểm tra quyền cần xác định bản ghi đã lưu, người sở hữu và quyền của principal hiện tại. Với thao tác cập nhật, không nên tin trường `owner` do client gửi lên: client có thể sửa payload để tự nhận quyền sở hữu. Hãy đối chiếu với dữ liệu đã lưu và áp dụng chính sách thay đổi owner riêng.

Tương tự, trước khi thêm association, cần kiểm tra cả hai phía:

1. Người dùng được phép thay đổi association của tài nguyên nguồn.
2. Tài nguyên đích tồn tại và người dùng được phép liên kết tới nó.
3. Việc liên kết không vi phạm quy tắc nghiệp vụ, chẳng hạn địa chỉ thuộc tenant khác.

Nếu cần giới hạn dữ liệu trả về, ưu tiên truy vấn đã được scope theo principal/tenant. Chỉ lọc kết quả sau khi truy vấn có thể làm sai số lượng và metadata phân trang, đồng thời có nguy cơ để lộ thông tin qua `totalElements` hoặc các liên kết điều hướng.

## 7. Tắt method không đồng nghĩa với phân quyền

Spring Data REST có cấu hình exposure để giới hạn HTTP method được xuất bản cho repository hoặc association. Đây là cơ chế kiểm soát bề mặt API:

- Nếu hệ thống không cho phép xóa qua REST, có thể tắt việc xuất bản thao tác `DELETE`.
- Nếu thao tác vẫn được xuất bản, Spring Security quyết định người gọi nào được phép thực hiện.
- Tắt method không thay thế việc kiểm tra quyền ở service hoặc ở các đường gọi khác trong ứng dụng.

Nói cách khác, exposure trả lời “API có cung cấp thao tác này không?”, còn authorization trả lời “người gọi hiện tại có được gọi thao tác này không?”. Hai lớp có mục đích khác nhau và có thể dùng đồng thời.

## 8. Những điểm cần kiểm tra khi triển khai

- **Thứ tự matcher:** luật association cụ thể phải đứng trước luật CRUD rộng hơn nếu chúng có thể cùng khớp.
- **HTTP method:** kiểm tra riêng `GET`, `POST`, `PUT`, `PATCH` và `DELETE`; không dùng một quyền ghi chung nếu nghiệp vụ yêu cầu tách biệt.
- **Đường dẫn thật:** xác nhận endpoint collection, item và association từ các liên kết HAL hoặc tài liệu API của ứng dụng.
- **Quyền tài nguyên:** kiểm tra ownership, tenant và quyền đối với tài nguyên đích; không chỉ dựa vào role chung.
- **Association:** xác nhận thao tác thêm/gỡ liên kết không vô tình tạo hoặc xóa bản ghi đích.
- **CSRF:** nếu ứng dụng xác thực bằng session/cookie từ trình duyệt, giữ bảo vệ CSRF cho request thay đổi trạng thái. Với API stateless dùng bearer token, cấu hình CSRF theo mô hình xác thực và rủi ro thực tế; không tắt chỉ vì endpoint là REST.
- **Phản hồi lỗi:** request chưa xác thực thường nhận `401 Unauthorized`; người dùng đã xác thực nhưng thiếu quyền thường nhận `403 Forbidden`. Không để response lỗi tiết lộ dữ liệu nhạy cảm.

Một ma trận kiểm thử tối thiểu nên có người chỉ đọc, người tạo/cập nhật, người được phép xóa và người không có quyền. Thử cả tài nguyên chính lẫn association resource, với cả trường hợp truy cập dữ liệu thuộc người dùng khác.

## 9. Bài tập tự kiểm tra

Một hệ thống có các quyền `people:read`, `people:create`, `people:update`, `people:delete`, `people:link` và `people:unlink`.

1. Người dùng chỉ có `people:read` gọi `POST /people`. Kết quả mong đợi là gì?
2. Người dùng có `people:update` gọi `DELETE /people/42`. Có được phép không?
3. Người dùng có quyền sửa `Person` nhưng không có `people:link` gọi `POST /people/42/addresses`. Có được thêm liên kết không?
4. `DELETE /people/42/addresses/9` có nhất thiết xóa bản ghi `Address` số 9 không?
5. Vì sao cần kiểm tra quyền trên tài nguyên đích trước khi tạo liên kết?

**Đáp án:**

1. Bị từ chối vì thiếu `people:create`.
2. Bị từ chối nếu chính sách xóa yêu cầu `people:delete`.
3. Bị từ chối vì thao tác association có quyền riêng.
4. Không. Đây là thao tác gỡ liên kết; việc xóa bản ghi đích là nghiệp vụ khác.
5. Để ngăn người dùng tạo liên kết tới dữ liệu ngoài phạm vi được phép, chẳng hạn tài nguyên thuộc tenant khác.

## Ghi nhớ

- Dùng HTTP method để phân biệt quyền đọc, tạo, sửa và xóa.
- Association resource cần chính sách riêng cho đọc, thêm, thay thế và gỡ liên kết.
- Dùng Spring Security request matcher cho luật theo method/URL và method security cho điều kiện gắn với repository, service hoặc dữ liệu cụ thể.
- Kiểm tra quyền trên cả tài nguyên nguồn và tài nguyên đích khi thay đổi liên kết.
- Exposure quyết định thao tác có được xuất bản; authorization quyết định ai được gọi thao tác đó.

Tham khảo:

- [Spring Data REST — Security](https://docs.spring.io/spring-data/rest/reference/security.html)
- [Spring Data REST — Association Resources](https://docs.spring.io/spring-data/rest/reference/associations.html)
- [Spring Security — Authorize HTTP Requests](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html)
- [Spring Security — Method Security](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html)
