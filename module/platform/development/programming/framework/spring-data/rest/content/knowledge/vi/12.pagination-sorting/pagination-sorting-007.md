# Tùy chỉnh tên tham số phân trang và sắp xếp trong Spring Data REST

## Mục tiêu

Spring Data REST mặc định dùng các query parameter **page**, **size** và **sort** để phân trang và sắp xếp dữ liệu của repository. Bạn có thể đổi tên các tham số này để thống nhất với quy ước API của hệ thống hoặc tránh xung đột với những tham số khác.

Sau bài này, bạn có thể:

- Nhận biết ý nghĩa của ba tham số phân trang và sắp xếp mặc định.
- Đổi tên chúng bằng cấu hình Spring Boot hoặc Java configuration.
- Gửi request với tên tham số mới.
- Hiểu ảnh hưởng của thay đổi đối với client và các liên kết phân trang HAL.

## 1. Các tham số mặc định

Khi Spring Data REST xuất bản collection resource của một repository, endpoint thường hỗ trợ:

| Tham số mặc định | Ý nghĩa | Ví dụ |
|---|---|---|
| **page** | Chỉ số trang, bắt đầu từ 0 | **page=0** là trang đầu |
| **size** | Số phần tử tối đa trên một trang | **size=20** |
| **sort** | Thuộc tính và chiều sắp xếp | **sort=lastName,asc** |

Ví dụ request:

~~~http
GET /people?page=0&size=20&sort=lastName,asc
Accept: application/hal+json
~~~

Request trên lấy trang đầu tiên, tối đa 20 phần tử và sắp xếp theo **lastName** tăng dần.

Có thể sắp xếp theo nhiều thuộc tính bằng cách lặp lại tham số **sort**:

~~~http
GET /people?page=0&size=20&sort=lastName,asc&sort=firstName,desc
~~~

Trong ví dụ này, **lastName** là tiêu chí sắp xếp chính; nếu nhiều bản ghi có cùng last name, **firstName** được dùng làm tiêu chí tiếp theo.

## 2. Đổi tên bằng application.yml

Với ứng dụng Spring Boot, có thể khai báo tên tham số trong cấu hình **spring.data.rest**:

~~~yaml
spring:
  data:
    rest:
      page-param-name: pageIndex
      limit-param-name: pageSize
      sort-param-name: orderBy
~~~

Ba thuộc tính cấu hình tương ứng là:

- **page-param-name**: tên query parameter thay cho **page**.
- **limit-param-name**: tên query parameter thay cho **size**.
- **sort-param-name**: tên query parameter thay cho **sort**.

Sau khi cấu hình, request có thể viết như sau:

~~~http
GET /people?pageIndex=0&pageSize=20&orderBy=lastName,asc
Accept: application/hal+json
~~~

Sắp xếp theo nhiều thuộc tính:

~~~http
GET /people?pageIndex=0&pageSize=20&orderBy=lastName,asc&orderBy=firstName,desc
Accept: application/hal+json
~~~

Tên tham số mới chỉ thay thế tên query parameter. Cách diễn giải giá trị vẫn giữ nguyên: chỉ số trang bắt đầu từ 0, page size xác định số phần tử trên trang, và giá trị sort chứa tên thuộc tính cùng chiều sắp xếp.

## 3. Đổi tên bằng RepositoryRestConfigurer

Nếu muốn cấu hình bằng Java, triển khai **RepositoryRestConfigurer** và đặt tên tham số trên **RepositoryRestConfiguration**:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.data.rest.core.config.RepositoryRestConfiguration;
import org.springframework.data.rest.webmvc.config.RepositoryRestConfigurer;
import org.springframework.web.servlet.config.annotation.CorsRegistry;

@Configuration
public class SpringDataRestConfig
        implements RepositoryRestConfigurer {

    @Override
    public void configureRepositoryRestConfiguration(
            RepositoryRestConfiguration config,
            CorsRegistry cors) {

        config.setPageParamName("pageIndex");
        config.setLimitParamName("pageSize");
        config.setSortParamName("orderBy");
    }
}
~~~

Các method cấu hình có ý nghĩa:

- **setPageParamName(...)** đổi tên tham số chọn trang.
- **setLimitParamName(...)** đổi tên tham số giới hạn số phần tử trên trang.
- **setSortParamName(...)** đổi tên tham số sắp xếp.

Đặt class cấu hình trong package được Spring Boot component scan. Khi ứng dụng khởi động, Spring Data REST sử dụng các giá trị này khi xử lý request tới repository resources.

Chọn một nơi làm nguồn cấu hình thống nhất cho ba tên tham số. Nếu khai báo cùng một thiết lập ở cả YAML và Java configuration, hãy kiểm tra cấu hình cuối cùng của ứng dụng để tránh khó xác định giá trị nào đang được áp dụng.

## 4. Phân trang và sắp xếp sau khi đổi tên

Giả sử repository **PersonRepository** được Spring Data REST xuất bản tại **/people** và cấu hình dùng **pageIndex**, **pageSize**, **orderBy**.

Lấy trang thứ hai với 10 bản ghi:

~~~http
GET /people?pageIndex=1&pageSize=10
Accept: application/hal+json
~~~

Vì chỉ số trang bắt đầu từ 0, **pageIndex=1** là trang thứ hai.

Sắp xếp tăng dần theo họ:

~~~http
GET /people?orderBy=lastName,asc
Accept: application/hal+json
~~~

Sắp xếp giảm dần theo họ và tăng dần theo tên:

~~~http
GET /people?orderBy=lastName,desc&orderBy=firstName,asc
Accept: application/hal+json
~~~

Kết hợp phân trang và sắp xếp:

~~~http
GET /people?pageIndex=1&pageSize=10&orderBy=lastName,asc&orderBy=firstName,desc
Accept: application/hal+json
~~~

Spring Data REST vẫn xử lý request theo cơ chế phân trang và sắp xếp của Spring Data. Bạn chỉ thay tên các query parameter mà client gửi lên.

## 5. Liên kết phân trang trong HAL

Khi response được trả về dưới dạng HAL, Spring Data REST có thể cung cấp các liên kết như **self**, **first**, **prev**, **next** và **last** trong phần **_links**.

Ví dụ minh họa:

~~~json
{
  "_links": {
    "self": {
      "href": "http://localhost:8080/people?pageIndex=1&pageSize=10"
    },
    "first": {
      "href": "http://localhost:8080/people?pageIndex=0&pageSize=10"
    },
    "prev": {
      "href": "http://localhost:8080/people?pageIndex=0&pageSize=10"
    },
    "next": {
      "href": "http://localhost:8080/people?pageIndex=2&pageSize=10"
    }
  },
  "page": {
    "size": 10,
    "totalElements": 35,
    "totalPages": 4,
    "number": 1
  }
}
~~~

Đây là response minh họa; các link và metadata thực tế phụ thuộc vào trang hiện tại, số bản ghi và cấu hình repository.

Client nên theo các URL do server trả về trong **_links** để chuyển trang. Không nên tự giả định tên tham số hoặc tự ghép URL, vì server có thể thay đổi base path, tên tham số hay cách xuất bản resource.

## 6. Phạm vi ảnh hưởng và những điểm cần lưu ý

- **Áp dụng cho API Spring Data REST:** các tên cấu hình thuộc Repository REST configuration và được dùng khi xử lý phân trang, sắp xếp trên repository resources được xuất bản.
- **Không đổi tên field trong response:** đổi **page-param-name** không làm đổi cấu trúc metadata phân trang trong response HAL, ví dụ **page.number** và **page.size**.
- **Không đổi tên thuộc tính entity:** **orderBy=lastName,asc** vẫn tham chiếu tới thuộc tính **lastName** của domain object. Tên query parameter và tên thuộc tính được sắp xếp là hai khái niệm khác nhau.
- **Không đổi cấu trúc request body:** các thiết lập này chỉ liên quan tới query parameter, không thay đổi JSON representation dùng để tạo hoặc cập nhật entity.
- **Cập nhật client cùng lúc:** frontend, mobile app, script và tài liệu API đang gửi **page**, **size**, **sort** cần chuyển sang tên mới. Request cũ có thể không còn được xử lý theo cách mong muốn.
- **Phân biệt với controller MVC tự viết:** các controller dùng Spring MVC và **Pageable** có thể được xử lý bởi cơ chế argument resolver riêng. Đừng mặc định cấu hình Repository REST tự động đổi tên tham số cho mọi endpoint trong ứng dụng.
- **Phân biệt tên tham số với giới hạn phân trang:** đổi **limit-param-name** chỉ đổi tên query parameter nhận page size. Cấu hình **default-page-size** và **max-page-size** điều khiển kích thước mặc định và giới hạn tối đa, không đổi tên tham số.

## 7. Kiểm tra sau khi cấu hình

Có thể xác nhận cấu hình bằng một lượt kiểm tra API:

1. Khởi động ứng dụng và kiểm tra repository resource vẫn được xuất bản.
2. Gửi request với tên tham số mới, ví dụ **/people?pageIndex=0&pageSize=5&orderBy=lastName,asc**.
3. Kiểm tra response chứa số phần tử phù hợp và thứ tự theo thuộc tính đã chọn.
4. Đọc các link **first**, **prev**, **next**, **last** trong HAL và xác nhận URL sử dụng tên tham số đã cấu hình.
5. Gửi thử request với tên mặc định cũ để phát hiện client hoặc tài liệu còn chưa được cập nhật.

Nếu request mới không có tác dụng, kiểm tra chính tả tên thuộc tính YAML, class **RepositoryRestConfigurer** có được Spring quản lý hay không, và request có đang gọi đúng repository resource của Spring Data REST hay không.

## Ghi nhớ

Spring Data REST mặc định dùng **page**, **size**, **sort**. Để đổi tên, cấu hình **page-param-name**, **limit-param-name**, **sort-param-name** trong **spring.data.rest**, hoặc gọi lần lượt **setPageParamName**, **setLimitParamName**, **setSortParamName** trong **RepositoryRestConfigurer**. Sau khi đổi, cập nhật client và ưu tiên theo các liên kết phân trang HAL do server cung cấp.