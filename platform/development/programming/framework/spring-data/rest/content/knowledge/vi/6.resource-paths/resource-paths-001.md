# Cấu hình base path và phân biệt với servlet context path trong Spring Data REST

## Mục tiêu

Sau bài này, bạn có thể cấu hình tiền tố URL chung cho các REST resource do Spring Data REST tạo ra; phân biệt tiền tố đó với context path của toàn bộ ứng dụng web; ghép các phần đường dẫn để xác định URL thực tế; và xử lý các lỗi thường gặp như gọi thiếu hoặc lặp tiền tố.

## 1. Hai loại đường dẫn phục vụ hai mục đích khác nhau

Spring Data REST và servlet container có thể cùng thêm một phần đường dẫn vào URL, nhưng mỗi phần thuộc một lớp khác nhau:

- **Spring Data REST base path** là tiền tố dành cho API do Spring Data REST quản lý. Nó gom API root, repository resources và các endpoint Spring Data REST dưới một nhánh chung.
- **Servlet context path** là đường dẫn gốc của toàn bộ web application trong servlet container. Nó áp dụng cho mọi request thuộc ứng dụng, bao gồm Spring MVC controllers, Spring Data REST, static resources và các servlet khác trong cùng context.

Ví dụ, ứng dụng có servlet context path là `/shop` và Spring Data REST base path là `/api`. Repository `CustomerRepository` có resource path là `customers`. URL collection đầy đủ sẽ là:

```text
http://localhost:8080/shop/api/customers
```

Trong URL trên:

- `/shop` định vị web application trong servlet container.
- `/api` là tiền tố riêng của Spring Data REST.
- `/customers` là resource path của repository.

Nếu bỏ context path, request Spring Data REST sẽ có dạng `http://localhost:8080/api/customers`. Nếu bỏ base path, repository resource nằm ở `http://localhost:8080/shop/customers`.

## 2. Cấu hình Spring Data REST base path bằng Spring Boot

Trong ứng dụng Spring Boot, dùng thuộc tính `spring.data.rest.base-path` trong `application.properties`:

```properties
spring.data.rest.base-path=/api
```

Sau khi cấu hình, Spring Data REST đặt API root và các repository resource dưới `/api`. Ví dụ:

```java
@RepositoryRestResource(path = "customers")
public interface CustomerRepository
        extends CrudRepository<Customer, Long> {
}
```

Collection resource của repository này được truy cập qua `/api/customers` khi ứng dụng chạy ở context root mặc định.

Có thể dùng một tiền tố có nhiều đoạn, ví dụ:

```properties
spring.data.rest.base-path=/internal/data
```

Khi đó collection resource có path `/internal/data/customers`. Base path là cấu hình chung cho Spring Data REST; `@RepositoryRestResource(path = "customers")` vẫn chỉ định phần path riêng của repository.

Nếu không cấu hình base path, Spring Data REST dùng đường dẫn gốc mặc định của nó. Khi đó repository resource thường được truy cập trực tiếp theo path của repository, ví dụ `/customers`.

## 3. Cấu hình base path bằng Java

Nếu cần cấu hình bằng Java, triển khai `RepositoryRestConfigurer` và gọi `setBasePath` trên `RepositoryRestConfiguration`:

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.data.rest.core.config.RepositoryRestConfiguration;
import org.springframework.data.rest.webmvc.config.RepositoryRestConfigurer;
import org.springframework.web.servlet.config.annotation.CorsRegistry;

@Configuration
public class SpringDataRestConfig implements RepositoryRestConfigurer {

    @Override
    public void configureRepositoryRestConfiguration(
            RepositoryRestConfiguration config,
            CorsRegistry cors) {

        config.setBasePath("/api");
    }
}
```

Cấu hình trên đặt base path của Spring Data REST thành `/api`. Nó có cùng mục đích với thuộc tính Spring Boot `spring.data.rest.base-path=/api`.

Trong một ứng dụng Spring Boot, hãy chọn cách cấu hình phù hợp với quy ước của dự án và tránh khai báo nhiều giá trị base path khác nhau ở nhiều nơi. Nếu ứng dụng có nhiều `RepositoryRestConfigurer`, hãy kiểm tra thứ tự và nội dung cấu hình để xác định giá trị cuối cùng được áp dụng.

## 4. Cấu hình servlet context path

Servlet context path đặt đường dẫn gốc cho toàn bộ web application. Với Spring Boot chạy embedded servlet container, cấu hình bằng `server.servlet.context-path`:

```properties
server.servlet.context-path=/shop
```

Thuộc tính này tác động đến mọi endpoint thuộc ứng dụng, không chỉ Spring Data REST. Ví dụ, nếu ứng dụng có một Spring MVC controller:

```java
@RestController
class HealthController {

    @GetMapping("/health")
    String health() {
        return "ok";
    }
}
```

thì endpoint controller có URL `/shop/health` khi context path là `/shop`.

Nếu đồng thời cấu hình:

```properties
server.servlet.context-path=/shop
spring.data.rest.base-path=/api
```

thì các URL tiêu biểu là:

| Endpoint | URL path |
| --- | --- |
| Spring Data REST API root | `/shop/api` |
| Customer collection resource | `/shop/api/customers` |
| Spring MVC `/health` controller | `/shop/health` |

Bảng này giả định servlet được map ở path mặc định `/` và repository có resource path là `customers`.

Khi deploy ứng dụng vào một servlet container bên ngoài, context root đôi khi được quyết định bởi cấu hình deploy của container hoặc tên ứng dụng được deploy. Trong trường hợp đó, cần kiểm tra context root thực tế của môi trường chạy; thuộc tính Spring Boot `server.servlet.context-path` thường được dùng khi ứng dụng tự chạy với embedded server.

## 5. Ghép các thành phần thành URL thực tế

Với ứng dụng chạy trên servlet mapping mặc định, có thể hình dung URL của một Spring Data REST repository resource theo thứ tự:

```text
scheme://host:port
    + servlet context path
    + Spring Data REST base path
    + repository resource path
```

Ví dụ cấu hình:

```properties
server.port=8080
server.servlet.context-path=/shop
spring.data.rest.base-path=/api
```

và repository:

```java
@RepositoryRestResource(path = "orders")
public interface OrderRepository
        extends CrudRepository<Order, Long> {
}
```

URL collection resource là:

```text
http://localhost:8080/shop/api/orders
```

Nếu chỉ đổi `spring.data.rest.base-path` thành `/data`, URL mới là `http://localhost:8080/shop/data/orders`. Các controller thông thường như `/health` vẫn nằm dưới context path `/shop`, không tự chuyển sang `/data`.

Nếu ứng dụng còn cấu hình servlet mapping path riêng, ví dụ DispatcherServlet được map dưới một prefix khác, prefix đó cũng có thể xuất hiện trong URL. Vì vậy, khi debug một URL thực tế, hãy kiểm tra cả context path và servlet mapping của môi trường đang chạy, bên cạnh base path của Spring Data REST.

## 6. Phân biệt base path với resource path của repository

Ba cấu hình sau đây không thay thế cho nhau:

- `spring.data.rest.base-path=/api`: đặt tiền tố chung cho các endpoint Spring Data REST.
- `@RepositoryRestResource(path = "customers")`: đặt path của một repository cụ thể.
- `server.servlet.context-path=/shop`: đặt context root cho toàn bộ web application.

Ví dụ với cả ba cấu hình, collection resource là `/shop/api/customers`.

Không cần lặp lại base path trong annotation repository. Nếu đã đặt base path là `/api` mà tiếp tục khai báo `@RepositoryRestResource(path = "api/customers")`, kết quả có thể thành đường dẫn lặp như `/api/api/customers` (cộng thêm context path nếu có). Hãy để base path chứa phần chung và repository path chứa phần riêng.

## 7. Cách kiểm tra sau khi cấu hình

Sau khi thay đổi cấu hình, kiểm tra theo các bước sau:

1. Khởi động lại ứng dụng để cấu hình mới được nạp.
2. Xác định host, port và servlet context path của môi trường đang chạy.
3. Gửi request đến API root theo context path và Spring Data REST base path. Với ví dụ trên, đó là `GET /shop/api`.
4. Đọc các link HAL trong response để xác định collection resource mà Spring Data REST công bố.
5. Gọi collection resource, ví dụ `GET /shop/api/customers`.
6. Gọi một controller ngoài Spring Data REST, ví dụ `GET /shop/health`, để xác nhận context path dùng chung cho ứng dụng còn base path chỉ tác động đến API Spring Data REST.

API root HAL hữu ích vì các link trong response cho biết đường dẫn mà server đang công bố. Khi có proxy hoặc gateway đứng trước ứng dụng, hãy kiểm tra cả URL bên ngoài và URL mà request được chuyển tiếp đến ứng dụng.

## 8. Lỗi thường gặp và cách xử lý

**Gọi API thiếu context path**

Nếu `server.servlet.context-path=/shop`, gọi `/api/customers` trực tiếp trên ứng dụng thường dẫn đến 404. Hãy gọi `/shop/api/customers`.

**Gọi API thiếu Spring Data REST base path**

Nếu base path là `/api`, gọi `/shop/customers` sẽ không khớp endpoint Spring Data REST đã cấu hình. Hãy thêm `/api` sau context path.

**Lặp tiền tố trong repository path**

Nếu base path đã là `/api`, không thêm lại `api` vào `@RepositoryRestResource(path = ...)`. Chỉ khai báo phần riêng của repository, ví dụ `customers`.

**Nhầm base path với context path**

Nếu Spring MVC controller cũng cần nằm dưới một prefix, thay đổi context path. Nếu chỉ muốn gom các endpoint Spring Data REST dưới một prefix, thay đổi base path. Chọn sai thuộc tính có thể làm các controller khác đổi URL ngoài dự kiến.

**Đường dẫn bên ngoài khác đường dẫn nội bộ sau reverse proxy**

Proxy hoặc API gateway có thể thêm, bỏ hoặc viết lại prefix trước khi chuyển request đến ứng dụng. Đối chiếu cấu hình rewrite của proxy, forwarded headers và URL thực tế mà ứng dụng nhận được. Không tự thêm một prefix lần thứ hai nếu proxy đã thêm prefix đó.

## Tóm tắt

- `spring.data.rest.base-path` đặt tiền tố chung cho API Spring Data REST.
- `server.servlet.context-path` đặt context root cho toàn bộ web application.
- `@RepositoryRestResource(path = "...")` chỉ đặt path của một repository.
- Khi context path là `/shop`, base path là `/api` và repository path là `customers`, URL collection là `/shop/api/customers`.
- Kiểm tra API root HAL và URL của một controller thông thường để xác định prefix nào đang được áp dụng.

## Tài liệu tham khảo

- [Spring Data REST — Customizing the base URI and repository exposure](https://docs.spring.io/spring-data/rest/reference/customizing-sdr.html)
- [Spring Boot application properties — spring.data.rest.base-path](https://docs.spring.io/spring-boot/appendix/application-properties/index.html#application-properties.data.spring.data.rest.base-path)
- [Spring Boot application properties — server.servlet.context-path](https://docs.spring.io/spring-boot/appendix/application-properties/index.html#application-properties.server.server.servlet.context-path)
- [RepositoryRestConfiguration — API](https://docs.spring.io/spring-data/rest/reference/api/java/org/springframework/data/rest/core/config/RepositoryRestConfiguration.html)
