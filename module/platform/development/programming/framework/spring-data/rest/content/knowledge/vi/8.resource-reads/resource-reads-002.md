# GET tập hợp và phương thức findAll được sử dụng

## Mục tiêu

Trong Spring Data REST, collection resource là endpoint đại diện cho tập hợp entity do một repository quản lý. Gửi HTTP GET đến collection resource để đọc danh sách entity. Spring Data REST thực hiện thao tác này bằng phương thức \`findAll(…)\` mà repository cung cấp.

Ví dụ, một repository quản lý Customer có thể tạo collection resource:

    GET /customers

Nếu repository hỗ trợ phân trang, response chỉ chứa một trang kết quả và có thêm link điều hướng cùng metadata trang. Nếu repository chỉ có phương thức đọc toàn bộ, response có thể chứa toàn bộ entity mà phương thức đó trả về.

Khi phân tích một request GET collection, cần xác định:

1. Collection URL nào được export?
2. Repository có những overload \`findAll\` nào?
3. Framework chọn overload nào để thực thi?
4. Các tham số \`page\`, \`size\`, \`sort\` có được repository hỗ trợ không?
5. Response có dữ liệu, link và metadata trang như thế nào?

## 1. Collection resource và HTTP GET

Spring Data REST tạo collection resource từ repository được export. Theo mặc định, path dựa trên tên domain class sau khi chuyển thành chữ thường và số nhiều. Ví dụ, domain type Customer thường được công bố tại \`/customers\`.

Có thể tùy chỉnh path và relation bằng \`@RepositoryRestResource\`:

    @RepositoryRestResource(
        path = "customers",
        collectionResourceRel = "customers"
    )
    public interface CustomerRepository
            extends CrudRepository<Customer, Long> {
    }

Trong đó:

- \`path\` xác định URL của collection.
- \`collectionResourceRel\` xác định tên relation trong HAL \`_links\`.
- Item resource nằm dưới collection, ví dụ \`/customers/{id}\`.

Path và relation là hai khái niệm riêng. Client nên bắt đầu từ root resource và theo link HAL để lấy URL thực tế, thay vì tự suy luận đường dẫn từ tên interface.

### 1.1. GET đọc collection

Request:

    curl -H "Accept: application/hal+json" \
      "http://localhost:8080/customers"

GET trả về các entity mà repository cung cấp thông qua phương thức \`findAll(…)\`. Nếu repository hỗ trợ phân trang, Spring Data REST thêm link phân trang khi cần và metadata mô tả trang hiện tại.

Collection resource hỗ trợ:

| HTTP method | Ý nghĩa |
|---|---|
| GET | Đọc entity trong collection |
| HEAD | Kiểm tra collection resource có khả dụng |
| POST | Tạo entity mới từ request body |

Các HTTP method khác trên collection thường trả \`405 Method Not Allowed\`.

GET collection khác GET item:

- \`GET /customers\` đọc một tập hợp, dùng \`findAll(…)\`.
- \`GET /customers/1001\` đọc một entity theo ID, dùng \`findById(…)\`.

GET collection cũng khác query method resource, ví dụ \`GET /customers/search/by-status?status=ACTIVE\`, vốn gọi một query method riêng.

### 1.2. Media type và response

GET collection hỗ trợ các media type phổ biến:

- \`application/hal+json\`: representation HAL JSON, có link hypermedia.
- \`application/json\`: representation JSON.

Với HAL, response phân trang thường có các phần:

- \`_links\`: link \`self\`, \`next\`, \`prev\` khi phù hợp và các link liên quan.
- \`_embedded\`: danh sách entity trong trang hiện tại.
- \`page\`: metadata về kích thước trang, tổng số entity, tổng số trang và chỉ số trang hiện tại.

Ví dụ rút gọn:

    {
      "_links": {
        "self": {
          "href": "http://localhost:8080/customers?page=0&size=2"
        },
        "next": {
          "href": "http://localhost:8080/customers?page=1&size=2"
        }
      },
      "_embedded": {
        "customers": [
          { "id": 1001, "name": "An" },
          { "id": 1002, "name": "Binh" }
        ]
      },
      "page": {
        "size": 2,
        "totalElements": 5,
        "totalPages": 3,
        "number": 0
      }
    }

Đây là ví dụ minh họa. Relation name, URL, property và nội dung entity phụ thuộc domain type cùng cấu hình của ứng dụng. Với trang đầu tiên sẽ không có link \`prev\`; với trang cuối cùng sẽ không có link \`next\`.

## 2. Thứ tự chọn phương thức findAll

Spring Data REST chọn phương thức đọc collection theo thứ tự ưu tiên giảm dần sau đây:

1. \`findAll(Pageable)\`
2. \`findAll(Sort)\`
3. \`findAll()\`

Framework dùng phương thức đầu tiên có sẵn và được phép export. Đây là thứ tự quan trọng khi repository cung cấp nhiều overload.

### 2.1. findAll(Pageable)

Chữ ký thường gặp:

    Page<Customer> findAll(Pageable pageable);

Đây là lựa chọn ưu tiên cao nhất. \`Pageable\` chứa:

- Số trang cần đọc.
- Kích thước trang.
- Thông tin sắp xếp.

Spring Data REST tạo \`Pageable\` từ các query parameter của request rồi chuyển nó vào repository. Kết quả \`Page<Customer>\` cung cấp nội dung trang cùng thông tin tổng số entity và tổng số trang.

Ví dụ request:

    GET /customers?page=1&size=10&sort=name,asc

Với \`page=1\`, \`size=10\`, repository được yêu cầu đọc trang thứ hai gồm tối đa 10 entity, sắp xếp theo \`name\` tăng dần.

Đây thường là lựa chọn phù hợp nhất với collection có thể tăng lớn, vì database chỉ cần trả về phạm vi kết quả của trang được yêu cầu thay vì tải toàn bộ collection về ứng dụng.

### 2.2. findAll(Sort)

Chữ ký thường gặp:

    Iterable<Customer> findAll(Sort sort);

Đây là lựa chọn thứ hai khi repository không có overload \`findAll(Pageable)\` nhưng có \`findAll(Sort)\`.

Phương thức này hỗ trợ sắp xếp kết quả. Nó không nhận page number hoặc page size, nên bản thân nó không thể giới hạn kết quả theo một trang như \`findAll(Pageable)\`.

Khi RepositoryInvoker được gọi với một \`Pageable\`, nếu không có phương thức nhận \`Pageable\`, nó có thể lấy phần \`Sort\` từ \`Pageable\` và gọi \`findAll(Sort)\`. Việc đó giữ thông tin sắp xếp, nhưng phương thức \`Sort\` không thực hiện được giới hạn theo trang.

### 2.3. findAll()

Chữ ký phổ biến trong CrudRepository:

    Iterable<Customer> findAll();

Đây là lựa chọn cuối cùng khi repository không có phương thức nhận \`Pageable\` hoặc \`Sort\`.

Phương thức này trả về tất cả entity mà repository cung cấp. Nó không nhận thông tin phân trang hay sắp xếp, vì vậy không thể thực hiện page/size/sort ở tầng phương thức repository.

Với collection lớn, việc tải toàn bộ dữ liệu có thể tốn bộ nhớ, thời gian và tài nguyên database. Nếu cần API collection có khả năng mở rộng, hãy bổ sung hỗ trợ \`Pageable\` hoặc \`Sort\` phù hợp với yêu cầu.

### 2.4. Bảng so sánh

| Phương thức | Ưu tiên | Phân trang | Sắp xếp | Dữ liệu trả về |
|---|---:|---|---|---|
| \`findAll(Pageable)\` | 1 | Có | Có, qua Pageable | Một Page |
| \`findAll(Sort)\` | 2 | Không | Có | Các entity đã sắp xếp |
| \`findAll()\` | 3 | Không | Không | Toàn bộ entity |

Thứ tự này là quy tắc lựa chọn phương thức của Spring Data REST. Nó không có nghĩa framework luôn gọi cả ba phương thức. Trong một request, phương thức có mức ưu tiên cao nhất đang khả dụng sẽ được chọn.

## 3. Khai báo repository có phân trang

Trong Spring Data hiện đại, \`PagingAndSortingRepository\` cung cấp các phương thức phân trang và sắp xếp. Từ Spring Data 3.x, interface này không còn kế thừa \`CrudRepository\`; nếu repository cần cả thao tác CRUD và phân trang, hãy kế thừa cả hai interface:

    public interface CustomerRepository
            extends CrudRepository<Customer, Long>,
                    PagingAndSortingRepository<Customer, Long> {
    }

Khi đó repository có các phương thức CRUD và phương thức:

    Page<Customer> findAll(Pageable pageable);
    Iterable<Customer> findAll(Sort sort);

Nếu muốn các phương thức CRUD trả về \`List\` ở những trường hợp phù hợp, Spring Data cũng có \`ListCrudRepository\`. Kiểu trả về cụ thể phụ thuộc interface mà dự án chọn và phiên bản Spring Data đang dùng.

### 3.1. Domain type minh họa

    @Entity
    public class Customer {

        @Id
        @GeneratedValue
        private Long id;

        private String name;
        private String status;

        // constructors, getters and setters
    }

Repository:

    @RepositoryRestResource(path = "customers")
    public interface CustomerRepository
            extends CrudRepository<Customer, Long>,
                    PagingAndSortingRepository<Customer, Long> {
    }

Spring Data REST có thể export collection tại \`/customers\`. GET collection sử dụng \`findAll(Pageable)\` vì phương thức này có mức ưu tiên cao nhất và repository cung cấp nó.

## 4. Các query parameter của GET collection

Nếu repository hỗ trợ phân trang, Spring Data REST nhận các tham số sau.

### 4.1. page

\`page\` là chỉ số trang, bắt đầu từ 0. Mặc định là trang 0.

    GET /customers?page=0
    GET /customers?page=1

Trang 0 là trang đầu tiên; trang 1 là trang thứ hai.

### 4.2. size

\`size\` là số entity tối đa được yêu cầu trong một trang. Mặc định của Spring Data REST là 20.

    GET /customers?size=5

Ứng dụng có thể cấu hình page size mặc định và giới hạn page size tối đa bằng \`RepositoryRestConfiguration\`. Vì vậy, giá trị client yêu cầu có thể bị giới hạn theo cấu hình server.

Ví dụ cấu hình:

    @Component
    public class RestConfiguration implements RepositoryRestConfigurer {

        @Override
        public void configureRepositoryRestConfiguration(
                RepositoryRestConfiguration config,
                CorsRegistry cors) {

            config.setDefaultPageSize(25);
            config.setMaxPageSize(100);
        }
    }

Không nên cho phép client yêu cầu page size quá lớn nếu endpoint truy cập dữ liệu nhiều hoặc có chi phí truy vấn cao.

### 4.3. sort

\`sort\` xác định property dùng để sắp xếp và chiều sắp xếp:

    GET /customers?sort=name,asc
    GET /customers?sort=name,desc

- \`asc\`: tăng dần.
- \`desc\`: giảm dần.

Có thể sắp xếp theo nhiều property bằng cách gửi nhiều tham số \`sort\`:

    GET /customers?sort=status,asc&sort=name,desc

Có thể sử dụng property lồng nhau theo property path nếu store và mapping hỗ trợ, ví dụ:

    GET /customers?sort=address.city,asc

Việc sort theo association có link tới một top-level resource không được hỗ trợ theo cách sort property thông thường. Property đưa vào sort phải hợp lệ với domain model và khả năng truy vấn của store.

### 4.4. Kết hợp phân trang và sắp xếp

Ví dụ đầy đủ:

    curl -H "Accept: application/hal+json" \
      "http://localhost:8080/customers?page=0&size=5&sort=status,asc&sort=name,desc"

Request này yêu cầu trang đầu tiên, tối đa năm entity, sắp xếp status tăng dần rồi name giảm dần.

Khi đọc link \`self\`, \`next\` hoặc \`prev\` trong response, hãy dùng các link server cung cấp để tiếp tục điều hướng. Không cần tự ghép lại URL nếu response đã có link phù hợp.

## 5. Response phân trang và chi phí truy vấn

### 5.1. Page metadata

Một \`Page\` thường cho biết:

- \`size\`: số entity tối đa trong một trang.
- \`number\`: chỉ số trang hiện tại.
- \`totalElements\`: tổng số entity phù hợp.
- \`totalPages\`: tổng số trang.

Để tính tổng số entity và số trang, implementation có thể phải thực hiện thêm count query. Với bảng lớn hoặc query phức tạp, count query có thể tốn kém.

Nếu ứng dụng chỉ cần biết còn trang kế tiếp hay không mà không cần tổng số trang, Spring Data query method có thể dùng \`Slice\`. Tuy nhiên, collection GET tiêu chuẩn sử dụng cơ chế \`findAll(Pageable)\` của repository; kiểu kết quả và metadata thực tế phụ thuộc contract của repository cùng phiên bản Spring Data.

### 5.2. Vì sao không nên tải toàn bộ collection?

Nếu dùng \`findAll()\` trên một bảng lớn, repository có thể phải đọc toàn bộ entity trước khi trả response. Điều này có thể gây:

- Tăng bộ nhớ heap của ứng dụng.
- Tăng thời gian phản hồi.
- Tăng tải database và network.
- Response JSON lớn, khó xử lý ở client.
- Khó kiểm soát khi số lượng entity tăng.

Với collection có dữ liệu tăng theo thời gian, nên thiết kế repository có hỗ trợ \`Pageable\`, đặt giới hạn page size hợp lý và dùng sort ổn định.

### 5.3. Sort ổn định khi phân trang

Khi sort theo một property không duy nhất, nhiều entity có thể có cùng giá trị. Nếu dữ liệu thay đổi giữa các request, thứ tự kết quả có thể thay đổi và client có thể gặp bản ghi lặp hoặc bị bỏ qua khi đi qua các trang.

Có thể thêm một property duy nhất làm tiêu chí cuối cùng, ví dụ ID:

    GET /customers?sort=status,asc&sort=id,asc&page=0&size=20

Sort ổn định giúp thứ tự phân trang dễ dự đoán hơn. Nó không thay thế cơ chế snapshot hoặc cursor pagination khi hệ thống cần bảo đảm nhất quán cao dưới tải ghi liên tục.

## 6. Kiểm soát việc export findAll

Các phương thức repository có thể được ẩn khỏi REST API bằng \`@RestResource(exported = false)\`.

Ví dụ, ẩn phương thức phân trang:

    public interface CustomerRepository
            extends CrudRepository<Customer, Long>,
                    PagingAndSortingRepository<Customer, Long> {

        @Override
        @RestResource(exported = false)
        Page<Customer> findAll(Pageable pageable);
    }

Nếu tất cả phương thức \`findAll(…)\` được hỗ trợ đều bị ẩn hoặc không tồn tại, GET collection có thể trả:

    405 Method Not Allowed

Đây là dấu hiệu collection resource không có phương thức đọc collection được export. Hãy kiểm tra:

- Repository có kế thừa interface cung cấp \`findAll\` không?
- Phương thức nào có mặt: \`findAll(Pageable)\`, \`findAll(Sort)\`, \`findAll()\`?
- Phương thức có bị đánh dấu \`@RestResource(exported = false)\` không?
- Có cấu hình exposure nào của ứng dụng làm thay đổi khả năng export không?

Ẩn một phương thức \`findAll\` không đồng nghĩa xóa phương thức khỏi Java interface hoặc database. Nó chỉ thay đổi API mà Spring Data REST công bố.

## 7. Kiểm tra phương thức thực sự được gọi

Để xác nhận GET collection đang dùng overload nào, hãy đối chiếu contract repository và kết quả HTTP.

### Bước 1 — Xem repository interface

Tìm các chữ ký:

    Page<T> findAll(Pageable pageable);
    Iterable<T> findAll(Sort sort);
    Iterable<T> findAll();

Ghi nhận phương thức được kế thừa từ interface nào và phương thức nào đã bị override.

### Bước 2 — Gửi request có page, size và sort

Ví dụ:

    GET /customers?page=1&size=3&sort=name,asc

Nếu repository có \`findAll(Pageable)\`, đây là phương thức được ưu tiên. Response phân trang sẽ thể hiện nội dung trang, link điều hướng và metadata trang.

### Bước 3 — Đối chiếu SQL hoặc log repository

Nếu dùng Spring Data JPA, bật log phù hợp trong môi trường phát triển để quan sát câu SQL. Một truy vấn có giới hạn kết quả và offset thường cho thấy repository đang thực thi phân trang ở database.

Với \`Page\`, có thể xuất hiện thêm count query để tính tổng số entity. Không nên kết luận chỉ từ một câu SQL; hãy đối chiếu cả method signature, request parameter và response.

### Bước 4 — Kiểm tra trường hợp fallback

Nếu không có \`findAll(Pageable)\`, kiểm tra xem repository có \`findAll(Sort)\` hay chỉ có \`findAll()\`.

- Có \`findAll(Sort)\`: phương thức sort được dùng nếu Pageable overload không tồn tại.
- Chỉ có \`findAll()\`: phương thức không tham số được dùng.
- Không có phương thức đọc nào được export: GET collection có thể trả 405.

### Bước 5 — Kiểm tra link HAL

Đọc \`_links.self\`, \`_links.next\` và \`_links.prev\` để xác nhận URL phân trang server công bố. Nếu collection có query methods, response cũng có thể chứa link \`search\`; đó là resource riêng cho các query method.

## 8. Các lỗi thường gặp

| Hiện tượng | Nguyên nhân cần kiểm tra |
|---|---|
| GET collection trả 405 | Không có \`findAll(…)\` phù hợp hoặc các method đã bị ẩn |
| Request có page nhưng trả nhiều entity | Repository không có \`findAll(Pageable)\`, chỉ có fallback không phân trang |
| Tham số sort không có tác dụng | Repository không có overload hỗ trợ Sort hoặc property sort không hợp lệ |
| Trang đầu không có prev | Hành vi bình thường của trang đầu |
| Trang cuối không có next | Hành vi bình thường của trang cuối |
| Tổng số trang lớn hoặc chậm | Count query có chi phí cao |
| Dữ liệu trùng hoặc thiếu giữa các trang | Sort không ổn định hoặc dữ liệu thay đổi giữa các request |
| URL collection không đúng dự kiến | Kiểm tra domain type, \`@RepositoryRestResource(path = "...")\` và base path |
| Collection rỗng | Có thể không có entity phù hợp; kiểm tra dữ liệu và repository thực tế |

## 9. Checklist

1. Tìm link collection trong root HAL resource.
2. Xác định domain type và collection path của repository.
3. Kiểm tra repository có \`findAll(Pageable)\`, \`findAll(Sort)\` và/hoặc \`findAll()\`.
4. Áp dụng thứ tự ưu tiên: Pageable, rồi Sort, cuối cùng là phương thức không tham số.
5. Kiểm tra method có được export hay bị ẩn bằng \`@RestResource(exported = false)\`.
6. Gửi GET với \`page\`, \`size\`, \`sort\` nếu repository hỗ trợ.
7. Đọc \`_embedded\`, \`_links\` và \`page\` trong response.
8. Đối chiếu SQL/log để xác nhận phân trang và count query.
9. Kiểm tra sort ổn định nếu client đi qua nhiều trang.
10. Nếu GET trả 405, xác nhận phương thức findAll nào còn được export.

## Tài liệu tham khảo

- [Spring Data REST — Repository resources](https://docs.spring.io/spring-data/rest/reference/repository-resources.html)
- [Spring Data REST — Paging and sorting](https://docs.spring.io/spring-data/rest/reference/paging-and-sorting.html)
- [Spring Data Core — RepositoryInvoker API](https://docs.spring.io/spring-data/rest/reference/data-commons/api/java/org/springframework/data/repository/support/RepositoryInvoker.html)
- [Spring Data Core — PagingAndSortingRepository API](https://docs.spring.io/spring-data/rest/reference/data-commons/api/java/org/springframework/data/repository/PagingAndSortingRepository.html)
- [Spring Data Commons — Query methods and Pageable](https://docs.spring.io/spring-data/commons/reference/repositories/query-methods-details.html)
