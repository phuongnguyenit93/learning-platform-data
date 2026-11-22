# Đọc metadata repository, kiểu miền và phương thức CRUD khả dụng

## Mục tiêu

Spring Data REST tạo REST API từ các Spring Data repository. Khi ứng dụng khởi động, framework phát hiện repository được phép export, đọc metadata của repository và kiểu miền, rồi ánh xạ những phương thức phù hợp thành các tài nguyên và thao tác HTTP.

Để xác định API nào thực sự tồn tại, cần trả lời bốn câu hỏi:

1. Repository nào được Spring Data REST phát hiện và export?
2. Repository quản lý domain type nào và kiểu khóa chính nào?
3. Repository có những phương thức đọc, ghi, xóa và truy vấn nào; phương thức nào bị ẩn?
4. Các thao tác đó được công bố qua collection resource, item resource, search resource hay association resource nào?

Metadata giúp khám phá hợp đồng REST ở runtime. Nó không có nghĩa mọi phương thức Java trong repository đều trở thành một URL riêng.

## 1. Repository metadata và domain type

Một repository Spring Data khai báo kiểu miền và kiểu ID qua hai tham số generic. Ví dụ:

    public interface PersonRepository extends CrudRepository<Person, Long> {
    }

Trong ví dụ này:

- Repository interface là PersonRepository.
- Domain type là Person: kiểu đối tượng mà repository lưu trữ và truy xuất.
- ID type là Long: kiểu định danh của một Person.
- CrudRepository cung cấp nhóm thao tác CRUD nền tảng mà Spring Data REST có thể ánh xạ thành các thao tác HTTP.

Spring Data Commons biểu diễn thông tin này qua metadata của repository. Hai thông tin quan trọng nhất khi đọc metadata là domain type và ID type. Domain type cho biết cấu trúc đối tượng mà API biểu diễn; ID type cho biết kiểu giá trị được dùng trong URI của từng item.

Metadata của persistent entity còn giúp framework nhận diện thuộc tính, trường định danh và quan hệ giữa các entity. Khi trả dữ liệu, Spring Data REST có thể biểu diễn quan hệ bằng các hypermedia link thay vì luôn nhúng toàn bộ đối tượng liên quan vào JSON.

Không nên nhầm ba khái niệm sau:

- Repository interface mô tả cách truy cập dữ liệu.
- Domain type mô tả đối tượng nghiệp vụ được quản lý.
- REST resource là biểu diễn HTTP mà Spring Data REST tạo ra từ repository và domain type.

Tên repository không nhất thiết quyết định URL. Mặc định, collection path được tạo từ tên đơn giản của domain class sau khi chuyển thành chữ thường và số nhiều. Ví dụ Person thường được export thành /people, còn Order thành /orders. Có thể thay đổi tên quan hệ và đường dẫn bằng annotation.

## 2. Luồng xử lý khi ứng dụng khởi động

### Bước 1 — Phát hiện repository được export

Spring Data REST tìm các Spring Data repository trong application context. Quy tắc phát hiện được điều khiển bởi RepositoryDetectionStrategy.

Các chiến lược thường gặp:

| Chiến lược | Repository được chọn |
|---|---|
| DEFAULT | Repository public hoặc repository được đánh dấu bằng @RepositoryRestResource, miễn là không bị đặt exported = false |
| ALL | Tất cả Spring Data repository, không phụ thuộc visibility hoặc annotation |
| VISIBILITY | Chỉ repository public |
| ANNOTATED | Chỉ repository có @RepositoryRestResource và không bị exported = false |

Mặc định, repository package-private không tự động được export theo cách một public repository được export. Cấu hình ứng dụng có thể thay đổi quy tắc phát hiện này.

Có thể tắt export toàn bộ repository bằng:

    @RepositoryRestResource(exported = false)
    public interface InternalPersonRepository extends CrudRepository<Person, Long> {
    }

### Bước 2 — Đọc metadata và xác định kiểu miền

Sau khi chọn repository, framework xác định:

- Interface repository và các interface cha mà nó kế thừa.
- Domain type, ví dụ Person.
- ID type, ví dụ Long.
- Các phương thức repository có sẵn.
- Metadata của persistent entity, gồm thuộc tính và association có thể được biểu diễn trong REST resource.

Với PersonRepository extends CrudRepository<Person, Long>, framework biết collection chứa Person và URI của item cần một ID kiểu Long.

### Bước 3 — Tạo resource mapping

Từ domain type và cấu hình repository, Spring Data REST xác định collection resource, item resource và các resource liên quan.

Ví dụ:

- Collection resource: /people
- Item resource: /people/{id}
- Search resource: /people/search
- Association resource: /people/{id}/{association}

Tên collection và relation có thể được tùy chỉnh:

    @RepositoryRestResource(
        path = "people",
        collectionResourceRel = "people"
    )
    public interface PersonRepository extends CrudRepository<Person, Long> {
    }

Nếu không khai báo path, framework sử dụng quy tắc tên mặc định dựa trên domain type. Vì vậy, khi kiểm tra URL, hãy dựa vào link HAL được trả về thay vì đoán đường dẫn từ tên interface.

### Bước 4 — Xác định phương thức CRUD có thể công bố

Spring Data REST xem xét các phương thức mà repository cung cấp và ánh xạ chúng vào các thao tác REST tương ứng. Repository kế thừa CrudRepository thường có đủ phương thức nền tảng để công bố CRUD.

Một thao tác HTTP có thể không xuất hiện nếu phương thức nền tảng tương ứng không tồn tại hoặc đã bị tắt bằng exported = false. Ví dụ, nếu repository không cung cấp phương thức xóa được Spring Data REST hỗ trợ, item resource sẽ không công bố DELETE.

### Bước 5 — Xử lý request và tạo response

Khi client gửi request, Spring Data REST chọn resource mapping phù hợp, gọi phương thức repository tương ứng, sau đó chuyển kết quả thành representation HTTP. Mặc định, response sử dụng HAL JSON và chứa các link trong thuộc tính _links.

Client có thể dùng các link này để đi từ root đến collection, từ collection đến item, search hoặc profile metadata. Đây là cơ chế hypermedia discovery của Spring Data REST.

## 3. Ánh xạ phương thức CRUD sang HTTP

Bảng sau mô tả các ánh xạ resource phổ biến. Việc một thao tác có thực sự được bật hay không vẫn phụ thuộc vào phương thức repository, annotation và cấu hình exposure.

| Resource | HTTP | Phương thức repository thường được dùng | Ý nghĩa |
|---|---|---|---|
| Collection /people | GET | findAll(Pageable), findAll(Sort), findAll() | Đọc danh sách entity |
| Collection /people | POST | save(entity) | Tạo entity mới |
| Item /people/{id} | GET | findById(id) | Đọc một entity |
| Item /people/{id} | PUT | save(entity) | Thay thế trạng thái entity |
| Item /people/{id} | PATCH | save(entity) | Cập nhật một phần entity |
| Item /people/{id} | DELETE | Phương thức delete tương ứng | Xóa entity |
| Search /people/search | GET | Các query method được export | Liệt kê link đến truy vấn |
| Query resource | GET | Query method tương ứng | Thực thi truy vấn |
| Association resource | GET, PUT, POST, DELETE | Ánh xạ association | Đọc hoặc thay đổi liên kết giữa entity |

### Đọc collection

GET trên collection gọi phương thức findAll phù hợp. Nếu repository hỗ trợ phân trang hoặc sắp xếp, Spring Data REST ưu tiên các biến thể theo thứ tự:

1. findAll(Pageable)
2. findAll(Sort)
3. findAll()

Các tham số phân trang thường dùng:

- page: số trang, bắt đầu từ 0.
- size: số phần tử trên mỗi trang.
- sort: thuộc tính và chiều sắp xếp, ví dụ sort=lastName,asc.

### Tạo entity

POST trên collection dùng phương thức save để lưu entity mới. Request body chứa dữ liệu đầu vào theo representation mà endpoint hỗ trợ. Khi tạo thành công, response thường trả 201 Created; link của entity mới có thể được cung cấp qua header Location.

### Đọc và cập nhật item

GET trên /people/{id} dùng phương thức tìm theo ID, thường là findById.

PUT thay thế trạng thái của resource bằng dữ liệu gửi lên. PATCH chỉ cập nhật một phần trạng thái. Cả hai thường được xử lý thông qua phương thức save của repository.

### Xóa item

DELETE trên /people/{id} xóa entity tương ứng. Spring Data REST dùng phương thức delete phù hợp mà repository cung cấp. Tên chữ ký cụ thể có thể khác theo phiên bản Spring Data; hãy kiểm tra interface thực tế và tài liệu của phiên bản dự án đang sử dụng.

### Truy vấn tùy chỉnh

Các query method như findByLastName có thể được công bố dưới search resource. Chúng là endpoint đọc dữ liệu và thường hỗ trợ GET. Search resource trả về các link đến từng query method; client theo link để gọi truy vấn.

## 4. Khám phá metadata qua HTTP

Không cần đoán tên repository hoặc tự ghép mọi URL. Hãy bắt đầu từ root endpoint của ứng dụng.

### 4.1 Đọc root HAL resource

Gửi GET đến root URL:

    curl -H "Accept: application/hal+json" http://localhost:8080/

Response minh họa:

    {
      "_links": {
        "people": {
          "href": "http://localhost:8080/people"
        },
        "profile": {
          "href": "http://localhost:8080/profile"
        }
      }
    }

Mỗi key trong _links là một relation. href là URL thực tế của resource. Trong ứng dụng cụ thể, relation và URL có thể khác do cấu hình; hãy dùng link trả về làm nguồn chuẩn.

### 4.2 Đọc danh sách profile

Theo href của link profile từ root resource. Profile index chứa link metadata cho từng repository được export.

Ví dụ với cấu hình mặc định:

    curl http://localhost:8080/profile

Response có thể chứa các link như /profile/people và /profile/orders. Nếu ứng dụng tùy chỉnh profile path, hãy theo href mà root resource cung cấp.

### 4.3 Đọc ALPS metadata của repository

Theo link profile của repository, ví dụ:

    curl -H "Accept: application/alps+json" \
      http://localhost:8080/profile/people

ALPS mô tả hai nhóm thông tin chính:

- Các thuộc tính trong representation của domain resource, chẳng hạn firstName, lastName, id hoặc association.
- Các thao tác REST mà resource công bố, chẳng hạn tạo collection, đọc collection, đọc item, cập nhật item và xóa item.

Một descriptor có thể chứa id, name, type, rt và các descriptor con. Trong đó:

| Trường | Ý nghĩa |
|---|---|
| id | Tên định danh của descriptor hoặc thao tác |
| name | Relation hoặc tên trường được mô tả |
| type = SEMANTIC | Thành phần dữ liệu trong representation |
| type = SAFE | Chuyển trạng thái an toàn, thường tương ứng GET hoặc HEAD |
| type = IDEMPOTENT | Thao tác thay đổi có tính idempotent, thường tương ứng PUT hoặc DELETE |
| type = UNSAFE | Thao tác thay đổi không idempotent, thường tương ứng POST |
| rt | Resource type mà thao tác trả về hoặc tham chiếu |

Ví dụ, descriptor person-representation có thể liệt kê firstName và lastName. Descriptor create-people có thể mô tả thao tác tạo trên collection people và trỏ tới person-representation qua rt.

ALPS giúp client hiểu các chuyển trạng thái REST có sẵn và những trường dữ liệu liên quan. Nếu có projection, metadata cũng có thể liệt kê các projection hợp lệ cùng những thuộc tính mà projection đó trả về.

### 4.4 Đọc JSON Schema

Spring Data REST cũng có thể cung cấp JSON Schema cho profile của repository. Gửi cùng URL profile với Accept header:

    curl -H "Accept: application/schema+json" \
      http://localhost:8080/profile/people

JSON Schema mô tả cấu trúc dữ liệu theo cách máy có thể đọc, ví dụ:

- Tên domain type.
- Các property và kiểu dữ liệu.
- Trường chỉ đọc hoặc có thể ghi.
- Thuộc tính quan hệ được biểu diễn dưới dạng URI.

ALPS hữu ích để hiểu thao tác và ngữ nghĩa REST; JSON Schema hữu ích để hiểu hình dạng dữ liệu và kiểu property.

## 5. Ví dụ hoàn chỉnh với PersonRepository

Repository có thể khai báo như sau:

    @RepositoryRestResource(
        path = "people",
        collectionResourceRel = "people"
    )
    public interface PersonRepository extends CrudRepository<Person, Long> {

        @RestResource(path = "by-last-name", rel = "byLastName")
        List<Person> findByLastName(@Param("lastName") String lastName);
    }

Domain type minh họa:

    @Entity
    public class Person {
        @Id
        @GeneratedValue
        private Long id;

        private String firstName;
        private String lastName;
    }

Luồng khám phá API:

1. GET root URL để tìm link people và profile.
2. Theo link people để đọc collection.
3. Theo link profile của people để đọc ALPS hoặc JSON Schema.
4. Theo link search trong collection để xem các query method được công bố.
5. Gọi query resource bằng GET với tham số lastName.

Ví dụ request:

    curl http://localhost:8080/people
    curl http://localhost:8080/people/search
    curl "http://localhost:8080/people/search/by-last-name?lastName=Nguyen"
    curl http://localhost:8080/people/1

Các thao tác ghi phổ biến:

    curl -X POST http://localhost:8080/people \
      -H "Content-Type: application/json" \
      -d '{"firstName":"An","lastName":"Nguyen"}'

    curl -X PATCH http://localhost:8080/people/1 \
      -H "Content-Type: application/merge-patch+json" \
      -d '{"lastName":"Tran"}'

    curl -X DELETE http://localhost:8080/people/1

Các ví dụ giả định ứng dụng chạy tại localhost:8080 và các thao tác tương ứng đã được export. Payload và media type cần khớp với domain model, cấu hình serialization và phiên bản Spring Data REST của dự án.

## 6. Kiểm soát repository và phương thức được export

Có thể điều chỉnh exposure ở nhiều cấp:

- @RepositoryRestResource(exported = false): không export repository.
- @RestResource(exported = false): không công bố query method, CRUD method hoặc association tương ứng.
- @RepositoryRestResource(path = "...", collectionResourceRel = "..."): đổi collection path và relation.
- @RestResource(path = "...", rel = "..."): đổi path và relation của query method hoặc association.
- RepositoryDetectionStrategy: thay đổi quy tắc chọn repository.
- RepositoryRestConfiguration và RepositoryRestConfigurer: cấu hình exposure ở cấp ứng dụng, domain type hoặc resource.

Một phương thức Java vẫn có thể tồn tại để phục vụ logic nội bộ dù không được công bố qua HTTP. Đặc biệt, save thường được dùng cho POST trên collection và PUT/PATCH trên item. Nếu chỉ muốn tắt một trong các HTTP method đó, cấu hình exposure theo resource có thể phù hợp hơn việc ẩn toàn bộ save method.

Ví dụ tắt PATCH cho item resource:

    @Component
    public class RestConfiguration implements RepositoryRestConfigurer {

        @Override
        public void configureRepositoryRestConfiguration(
                RepositoryRestConfiguration config) {

            config.getExposureConfiguration()
                .withItemExposure((metadata, methods) ->
                    methods.disable(HttpMethod.PATCH));
        }
    }

## 7. Cách kiểm tra khi endpoint không xuất hiện

| Hiện tượng | Điều cần kiểm tra |
|---|---|
| Root không có link repository | Repository có được phát hiện không; visibility, RepositoryDetectionStrategy và exported |
| URL collection khác dự kiến | Domain type, path trong @RepositoryRestResource và base path của ứng dụng |
| Collection không hỗ trợ GET | Repository có phương thức findAll phù hợp và phương thức đó có được export không |
| Collection không hỗ trợ POST | Repository có save và save có bị ẩn không |
| Item không hỗ trợ GET | Repository có findById phù hợp và có bị ẩn không |
| Item không hỗ trợ PUT/PATCH | save có được export không; ExposureConfiguration có tắt method không |
| Item không hỗ trợ DELETE | Repository có phương thức delete phù hợp và method có bị ẩn không |
| Không có link search | Repository có query method được export không |
| Property không xuất hiện như mong đợi | ALPS, JSON Schema, projection và quy tắc serialization của domain type |

HTTP 405 Method Not Allowed thường cho biết resource tồn tại nhưng HTTP method đang yêu cầu không được hỗ trợ. Hãy đối chiếu method với repository interface, annotation và cấu hình exposure trước khi sửa URL.

Metadata là công cụ khám phá API, không phải bản mô tả đầy đủ mọi quy tắc nghiệp vụ hoặc quyền truy cập. Kết quả thực tế còn chịu ảnh hưởng của validation, serialization, projection, security và cấu hình ứng dụng. Hãy kiểm tra response thực tế khi xác nhận hành vi của endpoint.

## 8. Checklist đọc metadata theo đúng thứ tự

1. Gửi GET đến root URL và ghi nhận các relation trong _links.
2. Theo link collection để xác định URL và relation thực tế.
3. Theo link profile để tìm metadata của đúng repository.
4. Đọc ALPS để biết field và thao tác REST được công bố.
5. Đọc JSON Schema nếu cần kiểu dữ liệu và cấu trúc property.
6. Mở repository interface để xác định domain type, ID type, CRUD methods và query methods.
7. Kiểm tra @RepositoryRestResource, @RestResource và RepositoryRestConfiguration để giải thích các method bị ẩn hoặc đổi tên.
8. Thử request GET/POST/PUT/PATCH/DELETE tương ứng và kiểm tra status code, link, response body.

Thứ tự này giúp đối chiếu ba lớp thông tin: metadata Java của repository, metadata REST được công bố và hành vi HTTP thực tế.

## Tài liệu tham khảo

- [Spring Data REST — Metadata](https://docs.spring.io/spring-data/rest/reference/metadata.html)
- [Spring Data REST — Repository resources](https://docs.spring.io/spring-data/rest/reference/repository-resources.html)
- [Spring Data REST — Customizing Spring Data REST](https://docs.spring.io/spring-data/rest/reference/customizing-sdr.html)
- [Spring Data REST — Project overview](https://spring.io/projects/spring-data-rest)
