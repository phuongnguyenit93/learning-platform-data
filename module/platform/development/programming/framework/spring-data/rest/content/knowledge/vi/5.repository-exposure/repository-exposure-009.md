# ExposureConfiguration giới hạn HTTP method toàn cục hoặc theo kiểu miền

## 1. ExposureConfiguration giải quyết vấn đề gì?

Spring Data REST tự động xuất các Spring Data repository thành REST resource. Từ các phương thức repository, framework xác định những HTTP method nào có thể dùng trên từng loại resource. Trong nhiều ứng dụng, quy tắc mặc định là đủ. Nhưng có trường hợp API cần chính sách chi tiết hơn: chẳng hạn tất cả item resource không được PATCH, trong khi chỉ riêng resource `User` không được tạo mới bằng PUT.

`ExposureConfiguration` là API cấu hình để điều chỉnh tập HTTP method được Spring Data REST hỗ trợ. Có thể đăng ký filter áp dụng toàn cục hoặc giới hạn filter cho một domain type bằng `forDomainType(Class)`. API này được bổ sung từ Spring Data REST 3.1.

Cấu hình này áp dụng cho repository resource do Spring Data REST quản lý. Nó không tự kiểm soát những controller Spring MVC tùy chỉnh nằm ngoài cơ chế export repository.

## 2. Quy tắc HTTP method mặc định

Trước khi thêm filter, Spring Data REST đã xác định method được hỗ trợ dựa trên những thao tác repository có thể thực hiện.

Ví dụ:

- Nếu repository không cung cấp thao tác `delete(…)`, item resource tương ứng sẽ không hỗ trợ HTTP `DELETE`.
- Nếu cần khai báo một repository method chỉ để dùng nội bộ, có thể đánh dấu method đó bằng `@RestResource(exported = false)` để nó không tạo ra HTTP exposure tương ứng.
- Method `save(…)` có thể được dùng cho nhiều thao tác: `POST` trên collection resource và `PUT` hoặc `PATCH` trên item resource. Vì vậy, ẩn `save(…)` bằng `exported = false` có thể loại bỏ nhiều HTTP method cùng lúc.

Khi cần điều chỉnh riêng từng method HTTP mà vẫn giữ repository method cho các thao tác khác, hãy dùng `ExposureConfiguration`.

## 3. Lấy ExposureConfiguration trong cấu hình Spring Data REST

Ứng dụng truy cập đối tượng này thông qua `RepositoryRestConfiguration.getExposureConfiguration()`. Cách phổ biến là đăng ký một bean triển khai `RepositoryRestConfigurer`, rồi thêm các filter trong callback cấu hình.

Ví dụ sau kết hợp một quy tắc toàn cục với hai quy tắc riêng theo domain type:

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.data.rest.core.config.RepositoryRestConfiguration;
import org.springframework.data.rest.core.mapping.ExposureConfiguration;
import org.springframework.data.rest.webmvc.config.RepositoryRestConfigurer;
import org.springframework.http.HttpMethod;
import org.springframework.web.servlet.config.annotation.CorsRegistry;

@Configuration
public class SpringDataRestExposureConfig implements RepositoryRestConfigurer {

    @Override
    public void configureRepositoryRestConfiguration(
            RepositoryRestConfiguration config, CorsRegistry cors) {

        ExposureConfiguration exposure = config.getExposureConfiguration();

        // Quy tắc toàn cục: không cho PATCH trên mọi item resource.
        exposure.disablePatchOnItemResources();

        // Chỉ domain type User không được tạo item mới bằng PUT.
        exposure.forDomainType(User.class)
                .disablePutForCreation();

        // Chỉ item resource của Order không hỗ trợ DELETE.
        exposure.forDomainType(Order.class)
                .withItemExposure((metadata, httpMethods) ->
                        httpMethods.disable(HttpMethod.DELETE));
    }
}
```

Trong ví dụ:

- `disablePatchOnItemResources()` là shortcut toàn cục: áp dụng cho item resource của mọi repository được Spring Data REST export.
- `forDomainType(User.class)` giới hạn filter tiếp theo cho aggregate thuộc domain type `User`.
- `forDomainType(Order.class)` giới hạn filter tiếp theo cho aggregate thuộc domain type `Order`.

`User.class` và `Order.class` là các entity/domain class, không phải repository interface hay chuỗi URL. Bean cấu hình cần được Spring phát hiện, ví dụ thông qua component scanning.

## 4. Ba nhóm resource có thể tùy chỉnh

Spring Data REST phân biệt ba nhóm resource. Mỗi nhóm có một phương thức đăng ký filter riêng:

| API | Phạm vi | Ví dụ mục đích |
|---|---|---|
| `withCollectionExposure(filter)` | Collection resource, ví dụ `/api/users` | Giới hạn method tạo resource qua collection |
| `withItemExposure(filter)` | Item resource, ví dụ `/api/users/42` | Giới hạn method đọc, thay thế, cập nhật hoặc xóa item |
| `withAssociationExposure(filter)` | Association resource, ví dụ liên kết giữa `/api/users/42/roles` | Giới hạn method đọc hoặc thay đổi quan hệ |

Hai filter đầu sử dụng `ExposureConfigurer.AggregateResourceHttpMethodsFilter`; filter association sử dụng `ExposureConfigurer.AssociationResourceHttpMethodsFilter`.

Các filter nhận metadata của resource và một đối tượng `ConfigurableHttpMethods`. Đối tượng này cho phép thay đổi tập method đang được hỗ trợ:

```java
exposure.withCollectionExposure((metadata, httpMethods) ->
        httpMethods.disable(HttpMethod.POST));

exposure.withItemExposure((metadata, httpMethods) ->
        httpMethods.disable(HttpMethod.PATCH, HttpMethod.DELETE));

exposure.withAssociationExposure((metadata, httpMethods) ->
        httpMethods.disable(HttpMethod.PUT));
```

Đây là các ví dụ filter toàn cục vì chúng được đăng ký trực tiếp trên `ExposureConfiguration`. Nếu muốn giới hạn một filter cho một domain type, đăng ký nó qua `forDomainType`:

```java
exposure.forDomainType(User.class)
        .withItemExposure((metadata, httpMethods) ->
                httpMethods.disable(HttpMethod.PATCH));
```

Filter nhận `ConfigurableHttpMethods`, có các thao tác `disable(HttpMethod...)` và `enable(HttpMethod...)`. Nó điều chỉnh tập method của resource dựa trên metadata hiện có; việc thêm một method vào tập exposure không tự tạo ra nghiệp vụ repository còn thiếu.

## 5. Phân biệt các shortcut liên quan đến PUT và PATCH

`ExposureConfiguration` cung cấp ba shortcut thường gặp. Chúng có phạm vi khác nhau:

| Phương thức | Ý nghĩa |
|---|---|
| `disablePutForCreation()` | Không cho dùng HTTP `PUT` để tạo một item resource mới |
| `disablePutOnItemResources()` | Tắt hỗ trợ HTTP `PUT` trên item resource |
| `disablePatchOnItemResources()` | Tắt hỗ trợ HTTP `PATCH` trên item resource |

Ví dụ:

```java
ExposureConfiguration exposure = config.getExposureConfiguration();

exposure.disablePutForCreation();
exposure.disablePutOnItemResources();
exposure.disablePatchOnItemResources();
```

Ba dòng trên đều là quy tắc toàn cục. Lưu ý rằng `disablePutForCreation()` là thao tác hẹp hơn: nó nhắm đến việc tạo item mới bằng PUT. Nếu yêu cầu là tắt PUT trên item resource nói chung, dùng `disablePutOnItemResources()`.

`disablePutForCreation()` cũng có trên `ExposureConfigurer`, nên có thể giới hạn theo domain type:

```java
exposure.forDomainType(User.class)
        .disablePutForCreation();
```

Trong khi đó, `disablePutOnItemResources()` và `disablePatchOnItemResources()` là shortcut của lớp `ExposureConfiguration`. Để áp dụng các quy tắc tương tự cho một domain type riêng, đăng ký filter qua `forDomainType(...).withItemExposure(...)`.

## 6. Ví dụ kết quả theo phạm vi

Giả sử ứng dụng có các endpoint:

- `/api/users` và `/api/users/42`
- `/api/orders` và `/api/orders/7`
- `/api/users/42/roles`

Với cấu hình trong phần 3, có thể đọc chính sách như sau:

| Resource | HTTP method bị giới hạn | Phạm vi |
|---|---|---|
| Mọi item resource, gồm User và Order | `PATCH` | Toàn cục |
| Item resource của User | `PUT` khi tạo mới | Chỉ User |
| Item resource của Order | `DELETE` | Chỉ Order |
| Collection resource | Không có filter bổ sung trong ví dụ | Theo exposure mặc định |
| Association resource | Không có filter bổ sung trong ví dụ | Theo exposure mặc định |

Nếu thêm:

```java
exposure.forDomainType(User.class)
        .withAssociationExposure((metadata, httpMethods) ->
                httpMethods.disable(HttpMethod.PUT));
```

thì filter association chỉ áp dụng cho các association resource thuộc các property do domain type `User` sở hữu. Nó không tự động áp dụng cho association của `Order`.

## 7. Phối hợp với @RestResource, CORS và Spring Security

Ba cơ chế này giải quyết các vấn đề khác nhau:

**`@RestResource(exported = false)`**

Dùng khi muốn ẩn một repository method hoặc resource khỏi HTTP exposure. Cách này hữu ích khi method chỉ phục vụ nội bộ. Nhưng nếu một method như `save(…)` đứng sau nhiều HTTP method, việc ẩn method có thể ảnh hưởng rộng hơn ý định ban đầu. `ExposureConfiguration` cho phép chọn chính xác collection, item hoặc association method cần điều chỉnh.

**CORS**

CORS quyết định trình duyệt từ origin khác có được phép gửi request với HTTP method và header nhất định hay không. CORS không thay thế cấu hình exposure của Spring Data REST. Cho phép `PUT` trong `CorsRegistry` không tự làm xuất hiện một thao tác PUT đã bị tắt trong `ExposureConfiguration`.

**Spring Security**

`ExposureConfiguration` quyết định HTTP method nào được Spring Data REST hỗ trợ trên repository resource. Nó không xác thực người dùng, không phân quyền theo vai trò và không thay thế authorization. Nếu chỉ một số người dùng được phép gọi `DELETE`, hãy dùng Spring Security để kiểm soát người gọi; nếu API không được phép cung cấp `DELETE` cho resource đó, hãy điều chỉnh exposure.

## 8. Cách kiểm tra khi một HTTP method không hoạt động

Khi request nhận kết quả ngoài dự kiến, kiểm tra lần lượt:

1. Xác định URL là collection, item hay association resource.
2. Kiểm tra repository có cung cấp thao tác tương ứng hay không; ví dụ `DELETE` thường cần thao tác xóa phù hợp.
3. Tìm các annotation `@RestResource(exported = false)` trên repository hoặc method liên quan.
4. Xác nhận bean `RepositoryRestConfigurer` đã được Spring phát hiện và callback cấu hình thực sự chạy.
5. Kiểm tra filter được đăng ký toàn cục hay qua đúng `forDomainType(Domain.class)`.
6. Kiểm tra filter đang thay đổi đúng nhóm resource: collection, item hay association.
7. Kiểm tra thêm CORS và Spring Security nếu request đến từ trình duyệt hoặc phụ thuộc quyền của người gọi.

Nên viết integration test cho từng loại resource và method quan trọng. Ví dụ, nếu mục tiêu là chỉ cấm `PATCH` với User, hãy kiểm tra `PATCH /api/users/42` bị từ chối theo chính sách và `PATCH` trên một domain type khác vẫn giữ hành vi dự kiến. Mã trạng thái cuối cùng còn phụ thuộc route, handler và cấu hình bảo mật của ứng dụng, vì vậy cần kiểm tra cả hành vi thực tế thay vì chỉ dựa vào một mã lỗi.

## 9. Ghi nhớ

`ExposureConfiguration` là lớp điều chỉnh HTTP method của Spring Data REST ở ba cấp resource: collection, item và association. Filter đăng ký trực tiếp trên cấu hình áp dụng toàn cục; filter đăng ký qua `forDomainType(Class)` giới hạn vào aggregate và association thuộc domain type tương ứng. Dùng shortcut khi chính sách phổ biến đã có sẵn, và dùng filter lambda khi cần chọn chính xác method cần bật hoặc tắt.

## Tài liệu tham khảo

- [Spring Data REST — Customizing supported HTTP methods](https://docs.spring.io/spring-data/rest/reference/customizing-sdr.html)
- [Javadoc — ExposureConfiguration](https://docs.spring.io/spring-data/rest/reference/api/java/org/springframework/data/rest/core/mapping/ExposureConfiguration.html)
- [Javadoc — ExposureConfigurer](https://docs.spring.io/spring-data/rest/reference/api/java/org/springframework/data/rest/core/mapping/ExposureConfigurer.html)
- [Javadoc — ConfigurableHttpMethods](https://docs.spring.io/spring-data/rest/reference/api/java/org/springframework/data/rest/core/mapping/ConfigurableHttpMethods.html)
- [Javadoc — RepositoryRestConfigurer](https://docs.spring.io/spring-data/rest/reference/api/java/org/springframework/data/rest/webmvc/config/RepositoryRestConfigurer.html)
