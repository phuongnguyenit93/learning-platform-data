# Khám phá các projection được công bố qua metadata

Spring Data REST cho phép một resource được biểu diễn theo nhiều góc nhìn. Một projection có thể chỉ trả về một tập thuộc tính cần thiết, đưa một quan hệ vào response hoặc tạo ra thuộc tính dẫn xuất. Khi API có nhiều projection, client cần biết những lựa chọn nào đang được công bố và cách yêu cầu từng lựa chọn.

Spring Data REST cung cấp metadata theo chuẩn Application-Level Profile Semantics (ALPS). Client có thể đi theo các hypermedia link để lấy metadata của repository, đọc các projection được liệt kê trong thao tác GET và dùng tên projection đó trên query parameter. Cách làm này giúp client khám phá API từ những link mà server công bố thay vì phải đoán tên projection.

## 1. Projection là gì?

Projection là một cách định nghĩa representation của domain object. Thay vì luôn trả về toàn bộ góc nhìn mặc định, server có thể cung cấp một projection phù hợp với nhu cầu của client.

Ví dụ, một resource Person có các thuộc tính firstName, lastName và address. Một màn hình danh sách chỉ cần tên người dùng, không cần địa chỉ. Projection có thể giới hạn representation còn firstName và lastName.

Một projection thường được khai báo bằng interface Java và annotation @Projection:

~~~java
import org.springframework.data.rest.core.config.Projection;

@Projection(name = "noAddresses", types = { Person.class })
public interface NoAddresses {

    String getFirstName();

    String getLastName();
}
~~~

Trong ví dụ:

- @Projection đánh dấu interface là projection được Spring Data REST nhận diện.
- name là tên công khai mà client sử dụng khi yêu cầu projection.
- types xác định domain type mà projection áp dụng.
- Các getter định nghĩa dữ liệu được đưa vào representation.

Tên interface là NoAddresses, còn tên projection công khai là noAddresses. Client phải dùng giá trị của thuộc tính name trong annotation, không tự suy ra từ tên interface.

Projection cũng có thể thêm dữ liệu dẫn xuất bằng @Value và SpEL, hoặc hiển thị một quan hệ lồng bên trong representation. Vì vậy, metadata không chỉ cho biết projection tồn tại mà còn mô tả các thuộc tính mà projection khai báo.

## 2. ALPS metadata trong Spring Data REST

ALPS là viết tắt của Application-Level Profile Semantics. Đây là định dạng metadata nhỏ gọn dùng để mô tả ngữ nghĩa của một ứng dụng REST, bao gồm các thuộc tính của representation và các thao tác REST mà tài nguyên hỗ trợ.

Spring Data REST cung cấp một ALPS document cho mỗi repository được export. Metadata mô tả các REST transition và các thuộc tính của repository. Khi có projection, các lựa chọn đó cũng được công bố trong metadata.

Cần phân biệt hai media type:

| Media type | Nội dung |
|---|---|
| application/hal+json | Representation HAL chứa dữ liệu resource và các hypermedia link |
| application/alps+json | ALPS metadata mô tả thuộc tính, thao tác và các lựa chọn projection |

HAL giúp client tìm đường đi trong API. ALPS mô tả ngữ nghĩa của các tài nguyên và thao tác mà client có thể sử dụng. Một response HAL có thể chứa link profile dẫn đến ALPS document.

## 3. Khám phá metadata từ root resource

Bắt đầu bằng cách gọi root endpoint của ứng dụng Spring Data REST:

~~~http
GET / HTTP/1.1
Host: localhost:8080
Accept: application/hal+json
~~~

Ví dụ response:

~~~json
{
  "_links": {
    "persons": {
      "href": "http://localhost:8080/persons"
    },
    "addresses": {
      "href": "http://localhost:8080/addresses"
    },
    "profile": {
      "href": "http://localhost:8080/profile"
    }
  }
}
~~~

Link profile là điểm bắt đầu để khám phá metadata. Client nên đọc giá trị href từ response thực tế, vì base path, host và các đường dẫn repository có thể khác nhau giữa các môi trường.

Dùng curl để đọc root resource:

~~~bash
curl -i -H "Accept: application/hal+json" http://localhost:8080/
~~~

Root resource chỉ công bố một profile link chung. Nó không trực tiếp chứa metadata chi tiết cho tất cả repository. Hãy đi tiếp theo href của link profile.

## 4. Liệt kê profile của từng repository

Gọi profile endpoint:

~~~http
GET /profile HTTP/1.1
Host: localhost:8080
Accept: application/hal+json
~~~

Ví dụ response:

~~~json
{
  "_links": {
    "self": {
      "href": "http://localhost:8080/profile"
    },
    "persons": {
      "href": "http://localhost:8080/profile/persons"
    },
    "addresses": {
      "href": "http://localhost:8080/profile/addresses"
    }
  }
}
~~~

Mỗi link trong response này dẫn đến metadata của một repository. Trong ví dụ, profile của repository persons nằm ở /profile/persons. Profile của addresses nằm ở /profile/addresses.

Đường dẫn /profile/{repository} trong ví dụ được sinh từ repository resource mà ứng dụng export. Khi viết client dùng chung cho nhiều ứng dụng, hãy theo href mà /profile trả về thay vì hardcode tên repository hoặc tự ghép URL.

Lệnh đọc danh sách profile:

~~~bash
curl -i -H "Accept: application/hal+json" http://localhost:8080/profile
~~~

Lưu ý: /profile là một tài nguyên điều hướng đến metadata của từng repository. Nó chưa phải ALPS document mô tả các thuộc tính và projection cụ thể.

## 5. Đọc ALPS document của repository

Theo link persons từ response /profile để lấy metadata:

~~~http
GET /profile/persons HTTP/1.1
Host: localhost:8080
Accept: application/alps+json
~~~

Ví dụ dùng curl:

~~~bash
curl -i -H "Accept: application/alps+json" http://localhost:8080/profile/persons
~~~

ALPS document có cấu trúc descriptors. Một phần của document có thể giống như sau:

~~~json
{
  "version": "1.0",
  "descriptors": [
    {
      "id": "person-representation",
      "descriptors": [
        { "name": "firstName", "type": "SEMANTIC" },
        { "name": "lastName", "type": "SEMANTIC" },
        { "name": "id", "type": "SEMANTIC" },
        { "name": "address", "type": "SAFE" }
      ]
    },
    {
      "id": "get-persons",
      "name": "persons",
      "type": "SAFE",
      "rt": "#person-representation",
      "descriptors": [
        {
          "name": "projection",
          "type": "SEMANTIC",
          "descriptors": [
            {
              "name": "inlineAddress",
              "type": "SEMANTIC",
              "descriptors": [
                { "name": "address", "type": "SEMANTIC" },
                { "name": "firstName", "type": "SEMANTIC" },
                { "name": "lastName", "type": "SEMANTIC" }
              ]
            },
            {
              "name": "noAddresses",
              "type": "SEMANTIC",
              "descriptors": [
                { "name": "firstName", "type": "SEMANTIC" },
                { "name": "lastName", "type": "SEMANTIC" }
              ]
            }
          ]
        }
      ]
    }
  ]
}
~~~

Đây là đoạn minh họa rút gọn. Metadata thực tế có thể có thêm descriptors cho create, update, delete, item resource, collection resource và các thuộc tính khác.

Đọc các thành phần chính:

- version cho biết phiên bản cấu trúc ALPS.
- person-representation mô tả các thuộc tính của representation mặc định.
- get-persons mô tả thao tác GET trên collection persons.
- type = SAFE biểu thị một transition an toàn, chẳng hạn GET.
- rt tham chiếu đến resource type được mô tả bởi descriptor person-representation.
- descriptors bên trong get-persons chứa các tùy chọn cho thao tác GET.
- projection là descriptor biểu thị query option dùng để chọn projection.
- Các descriptor lồng bên trong projection là những projection name được công bố.
- Các descriptor con của từng projection cho biết các thuộc tính mà projection đó cung cấp.

Trong ví dụ, client tìm thấy hai projection là inlineAddress và noAddresses. Projection noAddresses cung cấp firstName và lastName; inlineAddress cung cấp thêm address.

## 6. Nhận diện projection trong ALPS

Khi phân tích ALPS, đừng chỉ tìm chuỗi tên projection ở bất kỳ vị trí nào. Hãy xác định thao tác GET tương ứng, rồi tìm descriptor tên projection nằm bên trong thao tác đó.

Một cấu trúc khái quát:

~~~text
descriptors
  └── get-persons
       └── descriptors
            └── projection
                 ├── inlineAddress
                 │    ├── address
                 │    ├── firstName
                 │    └── lastName
                 └── noAddresses
                      ├── firstName
                      └── lastName
~~~

Có thể đọc metadata theo thứ tự sau:

1. Tìm operation descriptor có id là get-persons nếu đang khám phá collection resource.
2. Tìm descriptor con có name là projection.
3. Lấy danh sách projection từ projection.descriptors.
4. Đọc name của mỗi projection để lấy giá trị query parameter.
5. Đọc descriptors bên trong mỗi projection để hiểu các thuộc tính mà representation cung cấp.

Metadata của item resource có thể chứa operation get-person. ALPS có thể công bố projection trong GET collection và GET item. Khi cần projection cho một loại resource cụ thể, hãy kiểm tra operation phù hợp với endpoint mà client chuẩn bị gọi.

Các type thường gặp trong ALPS:

| Type | Ý nghĩa |
|---|---|
| SEMANTIC | Thành phần dữ liệu hoặc trạng thái trong representation |
| SAFE | Transition an toàn, thường là GET hoặc HEAD |
| IDEMPOTENT | Transition làm thay đổi trạng thái nhưng có tính idempotent, ví dụ PUT hoặc DELETE |
| UNSAFE | Transition không idempotent, thường là POST |

Type giúp client hiểu loại transition. Nó không thay thế việc đọc tài liệu nghiệp vụ hoặc kiểm tra quyền truy cập thực tế.

## 7. Yêu cầu projection sau khi khám phá

Sau khi đọc metadata và tìm thấy projection noAddresses, client có thể thêm query parameter projection vào URI của resource.

Đối với một item resource:

~~~http
GET /persons/1?projection=noAddresses HTTP/1.1
Host: localhost:8080
Accept: application/hal+json
~~~

Đối với collection resource:

~~~http
GET /persons?projection=noAddresses HTTP/1.1
Host: localhost:8080
Accept: application/hal+json
~~~

Có thể thử bằng curl:

~~~bash
curl -i -H "Accept: application/hal+json" "http://localhost:8080/persons/1?projection=noAddresses"
~~~

Tên noAddresses phải khớp với name trong @Projection. Tên này không phải tên interface NoAddresses.

Khi resource có projection được công bố, self link có thể là URI template:

~~~json
{
  "_links": {
    "self": {
      "href": "http://localhost:8080/persons/1{?projection}",
      "templated": true
    }
  }
}
~~~

Biểu thức {?projection} cho biết URI có thể nhận query parameter projection. Client hypermedia có thể dùng URI template này để mở rộng link, thay vì tự nối chuỗi tùy tiện.

Nếu client yêu cầu một projection không được công bố hoặc không được đăng ký cho resource đó, server có thể không xử lý được lựa chọn này. Hãy kiểm tra ALPS document, tên trong annotation và cấu hình đăng ký projection trước khi kết luận endpoint bị lỗi.

## 8. Đăng ký projection để metadata có thể công bố

Một projection chỉ xuất hiện trong metadata khi Spring Data REST nhận diện và đăng ký nó.

Có hai cách phổ biến:

**Cách 1: đặt interface cùng package hoặc sub-package của domain type**

Spring Data REST tự tìm interface có @Projection nằm trong cùng package với entity hoặc một package con. Ví dụ:

~~~text
com.example.people
  ├── Person.java
  ├── PersonRepository.java
  └── projection
       └── NoAddresses.java
~~~

Nếu Person nằm trong com.example.people, interface NoAddresses nằm trong com.example.people.projection là một vị trí có thể được phát hiện.

**Cách 2: đăng ký thủ công**

Có thể đăng ký projection bằng ProjectionConfiguration của RepositoryRestConfiguration:

~~~java
@Configuration
public class RestConfiguration implements RepositoryRestConfigurer {

    @Override
    public void configureRepositoryRestConfiguration(
            RepositoryRestConfiguration config,
            CorsRegistry cors) {

        config.getProjectionConfiguration()
            .addProjection(NoAddresses.class);
    }
}
~~~

Interface vẫn phải có annotation @Projection. Đăng ký thủ công hữu ích khi projection không nằm trong package mà cơ chế tìm kiếm mặc định quét.

Nếu projection không xuất hiện trong ALPS:

- Xác nhận interface có @Projection.
- Xác nhận name và types đúng với domain type.
- Kiểm tra interface nằm trong cùng package hoặc sub-package của entity, hoặc đã được đăng ký thủ công.
- Kiểm tra repository tương ứng có được export hay không.
- Khởi động lại ứng dụng sau khi thay đổi cấu hình và đọc lại metadata từ server đang chạy.
- Đảm bảo client đang truy cập đúng môi trường và đúng repository profile link.

## 9. ALPS và JSON Schema khác nhau như thế nào?

Spring Data REST cung cấp nhiều dạng metadata. ALPS tập trung vào ngữ nghĩa resource, REST transition và các lựa chọn projection. JSON Schema tập trung vào cấu trúc dữ liệu, kiểu thuộc tính và các ràng buộc có thể dùng cho validation.

Có thể yêu cầu JSON Schema từ profile link của repository bằng header:

~~~http
GET /profile/persons HTTP/1.1
Host: localhost:8080
Accept: application/schema+json
~~~

Ví dụ:

~~~bash
curl -i -H "Accept: application/schema+json" http://localhost:8080/profile/persons
~~~

Không nên nhầm JSON Schema với ALPS:

- Muốn khám phá thao tác GET và các projection name, đọc ALPS.
- Muốn xem kiểu dữ liệu và cấu trúc thuộc tính, đọc JSON Schema.
- Muốn tìm đường dẫn resource và metadata, đọc các hypermedia link trong HAL response.

Cùng một profile href có thể phục vụ các representation metadata khác nhau tùy Accept header. Do đó, hãy đặt đúng media type theo thông tin client cần.

## 10. Projection và excerpt projection

Projection được yêu cầu rõ ràng bằng query parameter projection. Client có thể chọn một representation cho request cụ thể.

Excerpt projection là một projection được cấu hình làm representation mặc định khi Spring Data REST nhúng resource vào collection hoặc resource liên quan. Nó thường được cấu hình trên repository bằng excerptProjection của @RepositoryRestResource.

Ví dụ:

~~~java
@RepositoryRestResource(excerptProjection = NoAddresses.class)
public interface PersonRepository extends CrudRepository<Person, Long> {
}
~~~

Excerpt projection được dùng cho các resource được nhúng trong collection hoặc quan hệ. Nó không tự động được áp dụng cho item resource khi client GET trực tiếp một người; muốn áp dụng projection cho item resource, client phải yêu cầu rõ ràng.

Việc phân biệt này giúp tránh nhầm lẫn khi một collection response có các thuộc tính khác với response khi GET một item.

## 11. Giới hạn và lưu ý bảo mật khi dùng metadata

ALPS là mô tả về API được công bố, không phải bản sao của dữ liệu runtime. Metadata cho biết projection và các thuộc tính được mô tả, nhưng không bảo đảm mọi request đều được phép thực hiện. Authentication, authorization, validation và business rule vẫn do server kiểm soát.

Đặc biệt, projection có thể đưa một thuộc tính vào response ngay cả khi thuộc tính đó được đánh dấu @JsonIgnore trong entity. Vì vậy, không được coi @JsonIgnore là hàng rào bảo mật duy nhất nếu ứng dụng còn sử dụng projection.

Khi thiết kế projection:

- Không tạo getter trả về password, token, secret hoặc dữ liệu nội bộ nhạy cảm.
- Xem xét từng thuộc tính được đưa vào projection, kể cả thuộc tính lồng và thuộc tính dẫn xuất bằng SpEL.
- Kiểm tra quyền truy cập ở server; không dựa vào việc client không nhìn thấy một projection trong giao diện.
- Chỉ công bố projection thực sự cần cho consumer.
- Đọc lại ALPS sau khi thay đổi projection để xác nhận metadata phản ánh đúng lựa chọn đã đăng ký.

Metadata cũng có thể thay đổi khi repository, domain model hoặc cấu hình REST thay đổi. Client nên khám phá link và metadata từ server thay vì đóng đinh danh sách projection trong mã nguồn khi API có khả năng mở rộng.

## 12. Quy trình khám phá projection dành cho client

Một client có thể triển khai quy trình tổng quát sau:

1. Gọi root resource với Accept: application/hal+json.
2. Đọc _links.profile và theo href.
3. Đọc /profile để lấy link metadata cho repository cần sử dụng.
4. Gọi repository profile với Accept: application/alps+json.
5. Tìm GET operation phù hợp với collection hoặc item resource.
6. Tìm descriptor projection bên trong operation đó.
7. Đọc tên projection và các descriptor thuộc tính lồng bên trong.
8. Theo self link hoặc resource link rồi mở rộng query parameter projection bằng đúng tên đã công bố.
9. Đọc response HAL và xử lý representation nhận được.
10. Nếu cần kiểu dữ liệu và cấu trúc schema, yêu cầu JSON Schema riêng bằng Accept: application/schema+json.

Quy trình này giúp client tự khám phá các lựa chọn representation từ metadata của server, giảm phụ thuộc vào cấu hình cứng và hỗ trợ API hypermedia.

## 13. Checklist thực hành

- [ ] Root response có link profile.
- [ ] Đã theo href của profile thay vì tự đoán URL.
- [ ] /profile có link đến metadata của repository cần dùng.
- [ ] Đã yêu cầu ALPS bằng application/alps+json.
- [ ] Đã tìm đúng GET operation của collection hoặc item.
- [ ] Đã tìm descriptor projection và các descriptor con.
- [ ] Đã lấy projection name từ metadata.
- [ ] Query parameter projection dùng đúng giá trị @Projection(name = ...).
- [ ] Đã kiểm tra response thực tế của projection.
- [ ] Đã rà soát projection không làm lộ dữ liệu nhạy cảm.

## 14. Kết luận

Spring Data REST công bố projection trong ALPS metadata của từng repository. Client bắt đầu từ profile link ở root, đi đến profile của repository, đọc descriptor projection bên trong GET operation và lấy tên projection được liệt kê. Sau đó client dùng tên này trong query parameter projection để nhận representation mong muốn.

Cần nhớ ba điểm: HAL cung cấp đường dẫn khám phá, ALPS mô tả các lựa chọn projection và JSON Schema mô tả cấu trúc dữ liệu. Metadata giúp client hiểu API, còn server vẫn chịu trách nhiệm kiểm tra quyền truy cập và bảo vệ dữ liệu nhạy cảm.

## Tài liệu tham khảo

- [Spring Data REST Reference — Metadata](https://docs.spring.io/spring-data/rest/reference/metadata.html): profile link, ALPS descriptors, projection metadata và JSON Schema.
- [Spring Data REST Reference — Projections and Excerpts](https://docs.spring.io/spring-data/rest/reference/projections-excerpts.html): khai báo @Projection, query parameter projection, cách đăng ký và lưu ý bảo mật.
- [RFC 6906 — The 'profile' Link Relation Type](https://www.rfc-editor.org/rfc/rfc6906): ý nghĩa của profile link relation.
- [ALPS Specification](https://alps.io/spec/): cấu trúc và ngữ nghĩa của Application-Level Profile Semantics.
