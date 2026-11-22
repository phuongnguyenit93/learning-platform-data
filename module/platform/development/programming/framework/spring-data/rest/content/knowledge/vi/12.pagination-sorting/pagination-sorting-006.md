# Cấu hình kích thước trang mặc định và kích thước tối đa

## Mục tiêu

Spring Data REST phân trang kết quả của collection resource khi repository hỗ trợ `Pageable`. Hai giới hạn quan trọng là:

- **Default page size:** số phần tử server trả về khi client không chỉ định `size`.
- **Maximum page size:** số phần tử tối đa server cho phép trong một trang, kể cả khi client yêu cầu lớn hơn.

Cấu hình hai giá trị này giúp API có hành vi ổn định và tránh để một request tải một tập dữ liệu quá lớn.

## Tham số phân trang

Spring Data REST mặc định dùng các query parameter:

| Tham số | Ý nghĩa | Giá trị mặc định |
| --- | --- | --- |
| `page` | Số thứ tự trang, bắt đầu từ `0` | `0` |
| `size` | Số phần tử yêu cầu trong một trang | Default page size của server |
| `sort` | Thuộc tính và hướng sắp xếp | Không sắp xếp nếu không chỉ định |

Ví dụ lấy trang đầu tiên, mỗi trang có 10 phần tử:

    GET /api/orders?page=0&size=10

Lấy trang thứ hai và sắp xếp theo `createdAt` giảm dần:

    GET /api/orders?page=1&size=10&sort=createdAt,desc

`page=0` là trang đầu tiên; `page=1` là trang thứ hai. Nếu bỏ `page`, server dùng trang đầu tiên. Nếu bỏ `size`, server dùng kích thước trang mặc định đã cấu hình.

## Cấu hình bằng Spring Boot

Trong `application.properties`, đặt hai thuộc tính sau:

    spring.data.rest.default-page-size=25
    spring.data.rest.max-page-size=100

Với cấu hình này:

- Request không có `size` nhận tối đa 25 phần tử trong trang.
- Client có thể yêu cầu kích thước nhỏ hơn, ví dụ `size=10`.
- Nếu client yêu cầu `size=500`, server giới hạn kích thước trang ở mức tối đa 100.

Có thể đặt cùng cấu hình trong `application.yml`:

    spring:
      data:
        rest:
          default-page-size: 25
          max-page-size: 100

Spring Data REST thường có default page size là 20 và max page size là 2000 nếu ứng dụng không thay đổi cấu hình. Hãy đặt giá trị tường minh trong ứng dụng để API không phụ thuộc vào giá trị mặc định của phiên bản framework.

## Cấu hình bằng Java

Nếu ứng dụng quản lý cấu hình Spring Data REST bằng Java, có thể triển khai `RepositoryRestConfigurer` và đặt giá trị trong `RepositoryRestConfiguration`:

    import org.springframework.context.annotation.Configuration;
    import org.springframework.data.rest.webmvc.config.RepositoryRestConfigurer;
    import org.springframework.data.rest.core.config.RepositoryRestConfiguration;
    import org.springframework.web.servlet.config.annotation.CorsRegistry;

    @Configuration
    public class RestConfiguration implements RepositoryRestConfigurer {

        @Override
        public void configureRepositoryRestConfiguration(
                RepositoryRestConfiguration config, CorsRegistry cors) {
            config.setDefaultPageSize(25);
            config.setMaxPageSize(100);
        }
    }

Chọn một nơi quản lý cấu hình để tránh các giá trị bị ghi đè hoặc khó xác định khi khởi động. Nếu dùng nhiều profile Spring Boot, kiểm tra cấu hình của profile đang chạy.

## Điều gì xảy ra khi client yêu cầu vượt giới hạn?

Giả sử server có `max-page-size=100`, client gửi:

    GET /api/orders?page=0&size=500

Server áp dụng giới hạn tối đa 100 phần tử cho trang. Giới hạn này bảo vệ API trước request cố lấy quá nhiều bản ghi trong một lần, nhưng không thay thế việc tối ưu truy vấn hoặc kiểm soát quyền truy cập.

Client nên đọc metadata phân trang trong response thay vì giả định server luôn trả đúng `size` đã gửi. Số phần tử thực tế còn phụ thuộc số bản ghi phù hợp, trang hiện tại và điều kiện lọc.

## Metadata trong response

Collection resource dạng HAL thường trả metadata phân trang trong thuộc tính `page`, ví dụ:

    {
      "_embedded": {
        "orders": [
          { "id": 101 },
          { "id": 102 }
        ]
      },
      "_links": {
        "self": { "href": "http://localhost:8080/api/orders?page=0&size=25" },
        "next": { "href": "http://localhost:8080/api/orders?page=1&size=25" }
      },
      "page": {
        "size": 25,
        "totalElements": 62,
        "totalPages": 3,
        "number": 0
      }
    }

Ý nghĩa các trường:

- `size`: kích thước trang được áp dụng cho response.
- `totalElements`: tổng số phần tử phù hợp với truy vấn.
- `totalPages`: tổng số trang.
- `number`: chỉ số trang hiện tại, bắt đầu từ `0`.

Client nên ưu tiên các liên kết điều hướng (`next`, `prev`, `first`, `last`) mà server trả về. Nếu API đổi base path hoặc tên query parameter, các liên kết này vẫn là nguồn URL đáng tin cậy.

## Đổi tên query parameter

Spring Data REST cho phép tùy chỉnh tên tham số trang, kích thước và sắp xếp. Ví dụ trong `application.properties`:

    spring.data.rest.page-param-name=pageNumber
    spring.data.rest.limit-param-name=pageSize
    spring.data.rest.sort-param-name=orderBy

Khi đó client dùng tên đã cấu hình, ví dụ:

    GET /api/orders?pageNumber=0&pageSize=25&orderBy=createdAt,desc

Chỉ đổi tên parameter khi có yêu cầu tương thích API rõ ràng. Khi đổi, cần cập nhật client và tài liệu API cùng lúc.

## Repository cần hỗ trợ phân trang

Phân trang chỉ hoạt động với repository cung cấp khả năng nhận `Pageable`/`Page`. Với Spring Data JPA, `JpaRepository` cung cấp sẵn khả năng này. Nếu repository chỉ kế thừa một interface CRUD không có phương thức phân trang, collection endpoint có thể không cung cấp hành vi phân trang như mong đợi.

Ví dụ:

    public interface OrderRepository
            extends JpaRepository<Order, Long> {
    }

Spring Data REST có thể dùng các phương thức phân trang của repository để trả collection theo từng trang.

## Kiểm tra cấu hình

1. Khởi động ứng dụng với profile và cấu hình dự kiến.
2. Gọi collection endpoint không có `size`, ví dụ `GET /api/orders`, rồi kiểm tra `page.size` trong response.
3. Gửi request với `size` nhỏ hơn default để xác nhận client có thể chọn trang nhỏ hơn.
4. Gửi request với `size` lớn hơn max, ví dụ `size=500`, rồi kiểm tra kích thước thực tế không vượt quá giới hạn.
5. Điều hướng qua link `next` và xác nhận `page.number` tăng theo từng trang.

Ví dụ với default 25 và max 100:

    GET /api/orders
    GET /api/orders?page=0&size=10
    GET /api/orders?page=0&size=500

## Lưu ý khi chọn giá trị

- Default page size nên đủ nhỏ để response nhanh và không chiếm quá nhiều bộ nhớ, nhưng vẫn đáp ứng số lượng dữ liệu client thường cần.
- Max page size nên dựa trên kích thước response, độ phức tạp truy vấn, tải database và giới hạn tài nguyên của ứng dụng.
- Tăng max page size không làm truy vấn tự nhanh hơn; cân nhắc index, projection, fetch strategy và sắp xếp trên các cột phù hợp.
- Client nên duyệt qua các trang thay vì yêu cầu một trang cực lớn để tải toàn bộ dữ liệu.
- Với tập dữ liệu thay đổi liên tục, các trang offset có thể dịch chuyển giữa các request; nếu cần tính nhất quán mạnh hơn, thiết kế chiến lược truy vấn phù hợp với yêu cầu nghiệp vụ.

Default page size quyết định kích thước khi client không chỉ định; max page size đặt trần cho mọi request. Cấu hình cả hai, sau đó để client dùng metadata và liên kết phân trang từ response để điều hướng.