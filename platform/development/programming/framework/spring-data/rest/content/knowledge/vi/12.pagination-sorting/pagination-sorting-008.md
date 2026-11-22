# Sắp xếp tăng, giảm và nhiều thuộc tính bằng sort

## Mục tiêu

Spring Data REST cho phép client sắp xếp kết quả collection bằng query parameter `sort`. Client có thể chọn property, chiều tăng hoặc giảm, và kết hợp nhiều tiêu chí sắp xếp trong cùng một request.

Ví dụ:

    GET /customers?sort=lastName,asc

Request này đọc collection customers và sắp xếp theo lastName tăng dần. Nếu cần sắp xếp theo nhiều thuộc tính, gửi nhiều tham số sort:

    GET /customers?sort=status,asc&sort=lastName,asc&sort=firstName,desc

Các tiêu chí được áp dụng theo thứ tự xuất hiện: status trước, sau đó lastName, cuối cùng firstName. Tiêu chí sau chỉ quyết định thứ tự giữa những bản ghi có giá trị bằng nhau ở các tiêu chí trước.

## 1. Cấu trúc tham số sort

Một tham số sort có dạng:

    sort=<property>,<direction>

Trong đó:

- property là tên thuộc tính của domain type hoặc property path được store hỗ trợ.
- direction là chiều sắp xếp: asc hoặc desc.
- Dấu phẩy phân cách tên property và direction.

Ví dụ:

    GET /customers?sort=lastName,asc
    GET /customers?sort=createdAt,desc

Nếu direction bị bỏ qua, Spring Data mặc định dùng ASC:

    GET /customers?sort=lastName

Có thể ghi rõ chiều để request dễ đọc và tránh phụ thuộc vào mặc định:

    GET /customers?sort=lastName,asc

Tên property phải khớp với property path trong domain model, không nhất thiết là tên cột trong database. Với JPA, nếu entity có property lastName được ánh xạ tới cột customer_last_name, tham số sort vẫn dùng lastName.

## 2. Sắp xếp tăng dần và giảm dần

### 2.1. ASC — tăng dần

Dùng asc để sắp xếp từ nhỏ đến lớn hoặc theo thứ tự từ điển tăng dần tùy kiểu dữ liệu:

    GET /customers?sort=lastName,asc

Một số ví dụ:

- Số: 10, 20, 30.
- Ngày giờ: thời điểm cũ đến thời điểm mới.
- Chuỗi: thứ tự so sánh phụ thuộc collation và database.

### 2.2. DESC — giảm dần

Dùng desc để đảo chiều sắp xếp:

    GET /customers?sort=createdAt,desc

Một số ví dụ:

- Số: 30, 20, 10.
- Ngày giờ: thời điểm mới đến thời điểm cũ.
- Chuỗi: thứ tự so sánh giảm dần theo collation của store.

Chiều sort áp dụng cho từng property riêng. Khi có nhiều tiêu chí, mỗi tiêu chí có thể dùng chiều khác nhau.

### 2.3. So sánh hai chiều

| Request | Kết quả |
|---|---|
| sort=price,asc | Giá thấp trước, cao sau |
| sort=price,desc | Giá cao trước, thấp sau |
| sort=createdAt,asc | Bản ghi cũ trước |
| sort=createdAt,desc | Bản ghi mới trước |
| sort=name,asc | Tên theo thứ tự tăng dần |
| sort=name,desc | Tên theo thứ tự giảm dần |

Thứ tự chuỗi và cách xử lý giá trị null phụ thuộc database, collation và cấu hình store. Nếu API cần quy tắc cụ thể cho chữ hoa/chữ thường hoặc null, hãy xác định và kiểm thử hành vi của database đang dùng.

## 3. Sắp xếp theo nhiều thuộc tính

Để sắp xếp theo nhiều thuộc tính, gửi lặp lại query parameter sort. Mỗi tham số mô tả một tiêu chí độc lập.

Ví dụ:

    GET /customers?sort=status,asc&sort=lastName,asc&sort=firstName,asc

Database áp dụng thứ tự:

1. status tăng dần.
2. Nếu hai customer có cùng status, so sánh lastName tăng dần.
3. Nếu status và lastName đều bằng nhau, so sánh firstName tăng dần.

Có thể trộn ASC và DESC:

    GET /orders?sort=status,asc&sort=createdAt,desc&sort=total,desc

Request này sắp xếp status tăng dần; trong mỗi nhóm status, đơn hàng mới hơn đứng trước; nếu thời điểm tạo bằng nhau thì tổng tiền giảm dần.

### 3.1. Thứ tự tham số có ý nghĩa

Hai request sau có thể cho kết quả khác nhau:

    GET /customers?sort=status,asc&sort=createdAt,desc

    GET /customers?sort=createdAt,desc&sort=status,asc

Request đầu ưu tiên status. Request thứ hai ưu tiên createdAt. Tiêu chí đầu tiên có trọng số thứ tự cao nhất; các tiêu chí sau chỉ phân định khi các tiêu chí đứng trước bằng nhau.

Không nên ghép nhiều property vào một chuỗi tùy ý như:

    sort=status,asc,lastName,desc

Hãy gửi mỗi tiêu chí bằng một tham số sort riêng để Spring Data phân tích đúng cấu trúc.

### 3.2. Thêm ID làm tiêu chí cuối để có thứ tự ổn định

Nếu các bản ghi có thể bằng nhau trên tất cả thuộc tính sort, thứ tự giữa chúng có thể không ổn định. Điều này gây khó khăn khi client đọc nhiều trang trong lúc dữ liệu thay đổi.

Có thể thêm một khóa duy nhất làm tiêu chí cuối:

    GET /customers?sort=status,asc&sort=lastName,asc&sort=id,asc&page=0&size=20

ID giúp phân định thứ tự giữa các bản ghi có cùng status và lastName. Cách này làm thứ tự kết quả dễ dự đoán hơn khi phân trang.

Sort ổn định không tạo ra snapshot của dữ liệu. Nếu bản ghi được thêm, xóa hoặc cập nhật trong lúc client chuyển trang, nội dung các trang vẫn có thể thay đổi. Với yêu cầu nhất quán cao dưới tải ghi liên tục, cần cân nhắc snapshot hoặc cursor-based pagination ở tầng API phù hợp.

## 4. Sort kết hợp với phân trang

Spring Data REST nhận sort cùng các tham số phân trang:

- page: chỉ số trang, bắt đầu từ 0.
- size: số phần tử tối đa trong một trang.
- sort: một hoặc nhiều tiêu chí sắp xếp.

Ví dụ:

    GET /customers?page=0&size=10&sort=lastName,asc&sort=firstName,asc

Request lấy trang đầu gồm tối đa 10 customer, sắp xếp theo lastName rồi firstName.

Ví dụ đọc trang tiếp theo:

    GET /customers?page=1&size=10&sort=lastName,asc&sort=firstName,asc

Khi dùng HAL, response có thể chứa các link self, next và prev. Nên theo link do server trả về để điều hướng, vì link đó phản ánh URL và tham số phân trang thực tế.

Một request collection có sort nhưng repository không hỗ trợ phương thức đọc nhận Sort hoặc Pageable có thể không áp dụng được thứ tự như mong đợi. Hãy kiểm tra các overload repository và cách Spring Data REST chọn phương thức collection.

## 5. Khai báo repository hỗ trợ Sort

Spring Data cung cấp PagingAndSortingRepository với các phương thức nhận Sort và Pageable.

Từ Spring Data 3.x, PagingAndSortingRepository không còn kế thừa CrudRepository. Nếu cần cả CRUD và paging/sorting, khai báo cả hai interface:

    public interface CustomerRepository
            extends CrudRepository<Customer, Long>,
                    PagingAndSortingRepository<Customer, Long> {
    }

Nếu dự án dùng JpaRepository, interface này đã cung cấp các khả năng CRUD, paging và sorting cần thiết:

    public interface CustomerRepository
            extends JpaRepository<Customer, Long> {
    }

Spring Data REST có thể dùng các phương thức repository tương ứng để đọc collection và áp dụng thứ tự được tạo từ query parameter sort.

### 5.1. Ví dụ domain type

    @Entity
    public class Customer {

        @Id
        @GeneratedValue
        private Long id;

        private String firstName;
        private String lastName;
        private String status;
        private Instant createdAt;
    }

Repository:

    @RepositoryRestResource(path = "customers")
    public interface CustomerRepository
            extends JpaRepository<Customer, Long> {
    }

Các request hợp lệ theo property của ví dụ:

    GET /customers?sort=lastName,asc
    GET /customers?sort=createdAt,desc
    GET /customers?sort=status,asc&sort=createdAt,desc&sort=id,asc

Dùng tên property Java trong domain model. Không dùng tên bảng hoặc tên cột SQL trừ khi chúng cũng chính là property path được ánh xạ.

## 6. Dùng Sort trong code Java

Nếu cần tạo sort trong service hoặc repository call, có thể dùng các factory method của Spring Data:

    Sort sort = Sort.by("lastName").ascending();

Hoặc khai báo nhiều tiêu chí:

    Sort sort = Sort.by(
        Sort.Order.asc("status"),
        Sort.Order.asc("lastName"),
        Sort.Order.desc("createdAt"),
        Sort.Order.asc("id")
    );

Dùng với repository:

    List<Customer> customers = customerRepository.findAll(sort);

Nếu cần phân trang cùng sort:

    Pageable pageable = PageRequest.of(
        0,
        20,
        Sort.by(
            Sort.Order.asc("status"),
            Sort.Order.desc("createdAt"),
            Sort.Order.asc("id")
        )
    );

    Page<Customer> page = customerRepository.findAll(pageable);

Đối với collection REST, Spring Data REST tự tạo Sort hoặc Pageable từ query parameter. Các ví dụ Java ở đây giúp hiểu cùng một cấu trúc được biểu diễn khi gọi repository trực tiếp trong ứng dụng.

## 7. Property path và sắp xếp thuộc tính lồng nhau

Spring Data hỗ trợ property path trong Sort nếu store và mapping có thể xử lý đường dẫn đó.

Ví dụ Customer có quan hệ tới Address:

    @Entity
    public class Customer {

        @ManyToOne
        private Address address;
    }

    @Entity
    public class Address {
        private String city;
    }

Có thể thử sort theo property path:

    GET /customers?sort=address.city,asc

Điều kiện:

- address phải là property hợp lệ của Customer.
- city phải là property hợp lệ của Address.
- Persistence store phải hỗ trợ tạo truy vấn theo property path đó.
- Mapping và association phải cho phép truy vấn tương ứng.

Không phải mọi association hoặc property path đều có thể sắp xếp trong mọi store. Nếu request trả lỗi, kiểm tra mapping và log truy vấn của persistence provider.

## 8. Giới hạn và kiểm soát sort

### 8.1. Property không tồn tại

Nếu client gửi tên property không có trong domain model, ví dụ:

    GET /customers?sort=unknownField,asc

Spring Data có thể báo lỗi khi tạo hoặc thực thi truy vấn. Kiểm tra tên property Java, chữ hoa/chữ thường và property path thay vì dùng tên cột database.

### 8.2. Property không phù hợp với kiểu dữ liệu

Một property có kiểu phức tạp hoặc association không được store hỗ trợ có thể không dùng được làm tiêu chí sort. Chỉ cung cấp các property mà persistence provider có thể chuyển thành biểu thức ORDER BY hợp lệ.

### 8.3. Quy tắc sort theo nghiệp vụ

Một API có thể cần giới hạn các trường mà client được phép sort. Ví dụ, màn hình danh sách Customer chỉ cho phép sort theo:

- lastName
- createdAt
- status

Nếu cần allowlist hoặc quy tắc sort theo role, hãy áp dụng ở tầng API/service hoặc custom controller phù hợp. Không xem tên property do client gửi là một quy tắc nghiệp vụ đáng tin cậy.

### 8.4. Null và collation

Cách đặt null ở đầu hay cuối và cách so sánh chuỗi có thể khác nhau giữa database. Một số database có cú pháp NULLS FIRST hoặc NULLS LAST; khả năng dùng trực tiếp phụ thuộc Spring Data version và store.

Nếu kết quả cần nhất quán giữa nhiều môi trường database, hãy xác định quy tắc null/collation rõ ràng và kiểm thử trên database thực tế.

## 9. Đọc response và xác nhận thứ tự

Khi GET collection trả HAL JSON, đọc:

- _embedded: các entity của trang hiện tại.
- _links.self: URL của request hiện tại.
- _links.next và _links.prev: link phân trang khi có.
- page: metadata của trang.

Ví dụ response rút gọn:

    {
      "_links": {
        "self": {
          "href": "http://localhost:8080/customers?sort=lastName,asc&sort=id,asc"
        }
      },
      "_embedded": {
        "customers": [
          { "id": 101, "lastName": "An" },
          { "id": 108, "lastName": "Binh" },
          { "id": 115, "lastName": "Binh" }
        ]
      }
    }

Đây chỉ là response minh họa. Relation name và các property trong entity phụ thuộc domain type cùng cấu hình.

Để xác nhận sort hoạt động:

1. Tạo dữ liệu kiểm thử có giá trị property khác nhau và có trường hợp trùng nhau.
2. Gửi GET với một tiêu chí sort.
3. So sánh thứ tự property trong response với chiều yêu cầu.
4. Gửi request với nhiều tiêu chí để kiểm tra tie-breaker.
5. Kết hợp page/size và kiểm tra các link điều hướng.
6. Kiểm tra SQL hoặc query log nếu cần xác nhận ORDER BY được đẩy xuống database.

## 10. Ví dụ thực hành

Giả sử Customer có các thuộc tính status, lastName, firstName và createdAt.

| Yêu cầu | Request |
|---|---|
| Tên họ tăng dần | GET /customers?sort=lastName,asc |
| Ngày tạo mới nhất trước | GET /customers?sort=createdAt,desc |
| Status tăng dần, tên họ tăng dần | GET /customers?sort=status,asc&sort=lastName,asc |
| Status tăng dần, ngày tạo mới nhất trước | GET /customers?sort=status,asc&sort=createdAt,desc |
| Tên họ, tên, rồi ID tăng dần | GET /customers?sort=lastName,asc&sort=firstName,asc&sort=id,asc |
| Trang 2, 20 phần tử, sort nhiều tiêu chí | GET /customers?page=1&size=20&sort=status,asc&sort=createdAt,desc&sort=id,asc |

Các request giả định collection path là /customers và các property tồn tại trong domain model.

## 11. Lỗi thường gặp

| Hiện tượng | Nguyên nhân cần kiểm tra |
|---|---|
| Kết quả không theo thứ tự mong muốn | Sai tên property hoặc direction |
| Chỉ một tiêu chí được áp dụng | Client đã gửi nhiều sort parameter đúng cách chưa |
| Thứ tự giữa bản ghi trùng không ổn định | Thiếu tiêu chí tie-breaker duy nhất như ID |
| Sort hoạt động nhưng page thay đổi khó đoán | Dữ liệu thay đổi giữa các request hoặc sort chưa ổn định |
| Request trả lỗi property path | Kiểm tra tên property và association mapping |
| Chuỗi có thứ tự khác kỳ vọng | Kiểm tra database collation và phân biệt hoa/thường |
| Null đứng ở vị trí khác nhau giữa môi trường | Kiểm tra quy tắc null ordering của database |
| Tham số sort bị bỏ qua | Kiểm tra repository có hỗ trợ Sort/Pageable và collection method có được export không |

## 12. Checklist

1. Xác định collection URL từ HAL root resource.
2. Kiểm tra repository hỗ trợ Sort hoặc Pageable.
3. Dùng tên property Java đúng với domain model.
4. Chọn asc hoặc desc cho từng tiêu chí.
5. Gửi mỗi tiêu chí bằng một query parameter sort riêng.
6. Đặt tiêu chí quan trọng nhất trước.
7. Thêm ID hoặc property duy nhất làm tie-breaker khi phân trang.
8. Kết hợp page và size nếu cần phân trang.
9. Theo các link HAL để điều hướng giữa các trang.
10. Kiểm tra property path, null ordering và collation trên store thực tế.

## Tài liệu tham khảo

- [Spring Data REST — Paging and sorting](https://docs.spring.io/spring-data/rest/reference/paging-and-sorting.html)
- [Spring Data REST — Repository resources](https://docs.spring.io/spring-data/rest/reference/repository-resources.html)
- [Spring Data Commons — Sorting query results](https://docs.spring.io/spring-data/commons/reference/repositories/query-methods-details.html)
- [Spring Data Commons — Sort API](https://docs.spring.io/spring-data/commons/docs/current/api/org/springframework/data/domain/Sort.html)
- [Spring Data Commons — Pageable API](https://docs.spring.io/spring-data/commons/docs/current/api/org/springframework/data/domain/Pageable.html)
- [Spring Data JPA — Query methods](https://docs.spring.io/spring-data/jpa/reference/repositories/query-methods-details.html)
