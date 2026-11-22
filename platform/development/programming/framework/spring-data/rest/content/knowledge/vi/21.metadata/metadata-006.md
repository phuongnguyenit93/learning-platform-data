# Bổ sung mô tả tài nguyên, thuộc tính và truy vấn bằng @Description trong Spring Data REST

## Mục tiêu

Sau bài này, bạn có thể:

- Giải thích vai trò của metadata mô tả trong một REST API có hypermedia.
- Dùng @Description để mô tả domain type và các thuộc tính được biểu diễn.
- Cấu hình mô tả cho collection resource và item resource bằng @RepositoryRestResource.
- Mô tả query method được export bằng @RestResource.
- Đọc ALPS metadata để xác nhận các mô tả đã được công bố cho client.
- Phân biệt mô tả metadata với dữ liệu JSON, validation và tài liệu API viết riêng.

## 1. Vì sao cần mô tả metadata?

Spring Data REST tự động xuất bản các repository thành REST resources. Một client có thể theo các liên kết HAL để khám phá collection, item, association và search resource. Tuy nhiên, tên resource hoặc tên thuộc tính chưa chắc giải thích đầy đủ ý nghĩa nghiệp vụ.

Ví dụ, client nhìn thấy resource people và các thuộc tính firstName, lastName, status. Tên gọi giúp nhận diện cấu trúc nhưng chưa trả lời được:

- Collection people chứa những đối tượng nào?
- Item resource đại diện cho một người hay một bản ghi nội bộ?
- Thuộc tính status biểu thị trạng thái nghiệp vụ nào?
- Query by-last-name tìm theo chính xác họ hay tìm gần đúng?
- Query method có tham số nào và kết quả đại diện cho điều gì?

Spring Data REST cung cấp metadata ALPS (Application-Level Profile Semantics) để mô tả các transition và descriptor của resource. Annotation @Description cho phép đưa phần giải thích bằng văn bản vào metadata này.

Mô tả metadata giúp client hiểu contract và khám phá API. Nó không thay đổi dữ liệu được lưu, không tạo endpoint mới, không đổi HTTP method và không tự kiểm tra tính hợp lệ của request.

## 2. @Description là gì?

Annotation cần import:

    import org.springframework.data.rest.core.annotation.Description;

@Description có các đặc điểm:

- Có thể đặt trên type, field hoặc method.
- Được giữ ở runtime để Spring Data REST đọc khi tạo metadata.
- Nhận một value kiểu String, là phần mô tả bằng văn bản.
- Value cũng có thể là key tra cứu trong resource bundle để hỗ trợ quốc tế hóa.

Ví dụ:

    @Description("A person registered in the address book.")
    public class Person {
        // ...
    }

Với thuộc tính:

    @Description("The person's given name.")
    private String firstName;

Mô tả nên giải thích ý nghĩa của resource hoặc property theo ngôn ngữ nghiệp vụ. Tránh lặp lại tên field, viết nội dung quá chung chung hoặc đưa chi tiết triển khai nội bộ không có ích cho client.

## 3. Mô tả domain type và thuộc tính

Giả sử ứng dụng có entity Person với các thuộc tính id, firstName, lastName và status.

    import jakarta.persistence.Entity;
    import jakarta.persistence.Id;

    import org.springframework.data.rest.core.annotation.Description;

    @Entity
    @Description("A person that can be discovered and managed through the people API.")
    public class Person {

        @Id
        @Description("Stable identifier assigned to this person.")
        private Long id;

        @Description("The person's given name.")
        private String firstName;

        @Description("The person's family name.")
        private String lastName;

        @Description("The person's current business status.")
        private String status;

        protected Person() {
        }

        // Constructors and accessors
    }

Mô tả trên type giải thích ý nghĩa tổng thể của representation. Mô tả trên từng field giải thích ý nghĩa của descriptor tương ứng trong representation metadata.

Nếu entity sử dụng property access của JPA, có thể đặt @Description trên getter thay vì field:

    @Description("The person's family name.")
    public String getLastName() {
        return lastName;
    }

Hãy chọn vị trí annotation phù hợp với cách domain model khai báo property. Không cần đặt cùng một mô tả lên cả field và getter nếu chúng đại diện cho cùng một property; việc lặp lại có thể làm cấu hình khó hiểu khi bảo trì.

Mô tả không làm cho một thuộc tính private tự động xuất hiện trong JSON. Việc property có được serialize hay không vẫn phụ thuộc vào mapping, Jackson, projection và cấu hình exposure của Spring Data REST.

## 4. Mô tả collection resource và item resource

Một repository được xuất bản thường có hai loại resource chính:

- Collection resource: đại diện cho tập hợp các Person, ví dụ /people.
- Item resource: đại diện cho một Person cụ thể, ví dụ /people/42.

Dùng @RepositoryRestResource để đặt mô tả riêng cho hai loại resource:

    import org.springframework.data.repository.CrudRepository;
    import org.springframework.data.rest.core.annotation.Description;
    import org.springframework.data.rest.core.annotation.RepositoryRestResource;

    @RepositoryRestResource(
        path = "people",
        collectionResourceRel = "people",
        collectionResourceDescription =
            @Description("The collection of people available through this API."),
        itemResourceRel = "person",
        itemResourceDescription =
            @Description("A single person and the information exposed for that person.")
    )
    public interface PersonRepository
            extends CrudRepository<Person, Long> {
    }

Các thuộc tính cần phân biệt:

| Thuộc tính | Ý nghĩa |
|---|---|
| path | Đường dẫn collection resource được export |
| collectionResourceRel | Tên relation dùng cho liên kết đến collection |
| collectionResourceDescription | Mô tả collection resource |
| itemResourceRel | Tên relation dùng cho liên kết đến một item |
| itemResourceDescription | Mô tả item resource |
| exported | Quyết định repository có được export hay không |

collectionResourceDescription và itemResourceDescription nhận một annotation @Description, không phải một String thông thường. Vì vậy, cú pháp cần có dạng @Description("...") bên trong cấu hình @RepositoryRestResource.

Mô tả collection nên giải thích tập hợp và mục đích sử dụng. Mô tả item nên giải thích một resource đơn lẻ. Không nên dùng cùng một câu chung chung cho cả hai nếu chúng có ý nghĩa khác nhau.

## 5. Mô tả query method được export

Spring Data REST có thể export query method thành query method resource dưới search resource. Ví dụ repository có phương thức findByLastName:

    import java.util.List;

    import org.springframework.data.repository.query.Param;
    import org.springframework.data.rest.core.annotation.Description;
    import org.springframework.data.rest.core.annotation.RestResource;

    public interface PersonRepository
            extends CrudRepository<Person, Long> {

        @RestResource(
            path = "by-last-name",
            rel = "by-last-name",
            description =
                @Description("Find people whose family name matches the supplied name.")
        )
        List<Person> findByLastName(@Param("name") String lastName);
    }

Với collection path là people và query path là by-last-name, query method resource có đường dẫn minh họa:

    GET /people/search/by-last-name?name=Nguyen

Trong ví dụ này:

- path thay đổi phần đường dẫn của query method resource.
- rel xác định relation được dùng khi tạo liên kết.
- description cung cấp mô tả cho query resource trong metadata.
- @Param("name") xác định tên query parameter mà client gửi.

@Description không export query method thay cho Spring Data repository. Query method vẫn phải được Spring Data nhận diện và Spring Data REST cho phép export. Nếu method bị ẩn bằng exported = false hoặc repository không được export, mô tả không thể làm endpoint xuất hiện trở lại.

Mô tả query nên nói rõ điều kiện tìm kiếm và ý nghĩa kết quả. Nếu query tìm theo họ chính xác, hãy ghi rõ “matches the supplied name”; nếu query tìm theo tiền tố hoặc chứa chuỗi, mô tả phải phản ánh đúng hành vi thực tế.

## 6. Metadata ALPS được công bố ở đâu?

Spring Data REST cung cấp ALPS metadata cho repository được export. Client thường tìm được liên kết profile trong HAL response của resource.

Luồng khám phá thường dùng:

1. Gọi GET đến root resource của ứng dụng.
2. Theo liên kết đến collection resource, ví dụ /people.
3. Đọc liên kết profile được trả về.
4. Truy cập profile URI để xem mô tả metadata.
5. Có thể gửi Accept: application/alps+json để yêu cầu biểu diễn ALPS.

Ví dụ:

    curl -i -H "Accept: application/alps+json"       http://localhost:8080/profile/people

ALPS mô tả representation và các transition của repository. Một descriptor có thể chứa doc với value là câu mô tả, format là TEXT. Ví dụ rút gọn:

    {
      "alps": {
        "version": "1.0",
        "descriptor": [
          {
            "id": "person-representation",
            "doc": {
              "value": "A person that can be discovered and managed through the people API.",
              "format": "TEXT"
            },
            "descriptor": [
              {
                "name": "firstName",
                "doc": {
                  "value": "The person's given name.",
                  "format": "TEXT"
                },
                "type": "SEMANTIC"
              }
            ]
          }
        ]
      }
    }

Đây là ví dụ minh họa cấu trúc. Metadata thực tế có thêm descriptor, transition, quan hệ và các thuộc tính được Spring Data REST phát hiện từ domain model và repository.

ALPS khác với response HAL thông thường:

| Nội dung | HAL representation | ALPS metadata |
|---|---|---|
| Mục đích | Trả dữ liệu và liên kết của resource | Mô tả ngữ nghĩa và các transition của API |
| Nội dung chính | Data, _links, embedded resources | Descriptor, doc, type, transition |
| Cách dùng | Client đọc hoặc thao tác với resource | Client khám phá contract và hiểu ý nghĩa resource |
| Mô tả @Description | Không phải một trường nghiệp vụ được thêm vào entity JSON | Có thể xuất hiện trong doc.value của descriptor tương ứng |

Không nên tìm mô tả @Description trong body JSON của entity rồi kết luận annotation không hoạt động. Hãy kiểm tra profile/ALPS metadata của repository.

## 7. Dùng resource bundle cho mô tả đa ngôn ngữ

@Description.value có thể là một key trong resource bundle. Điều này giúp tránh viết cứng nội dung hiển thị trong annotation khi ứng dụng cần nhiều locale.

Ví dụ, domain type có thể dùng một key:

    @Description("person.resource.description")
    public class Person {
        // ...
    }

Có thể cung cấp nội dung trong resource bundle mà ứng dụng cấu hình, ví dụ rest-messages.properties:

    person.resource.description=A person registered in the address book.
    person.firstName.description=The person's given name.
    person.lastName.description=The person's family name.

Spring MVC hỗ trợ locale và resource bundle. Hãy cấu hình đúng MessageSource/resource bundle theo phiên bản và cấu hình ứng dụng, sau đó kiểm tra metadata với locale tương ứng.

Một cách cấu hình khác được tài liệu Spring Data REST mô tả là dùng các key có tiền tố rest.description trong rest-messages.properties:

    rest.description.person=A collection of people
    rest.description.person.id=Identifier used to address a person
    rest.description.person.firstName=The person's given name
    rest.description.person.lastName=The person's family name

Các key này có thể cung cấp mô tả cho representation và các thuộc tính trong ALPS. Nếu dự án đã có resource bundle convention, hãy làm theo convention đó để tránh hai nguồn mô tả trùng lặp.

Chỉ dùng resource bundle khi cần quản lý nội dung ngoài mã nguồn hoặc hỗ trợ nhiều locale. Với một ứng dụng nhỏ và một ngôn ngữ, @Description trực tiếp thường đơn giản hơn.

## 8. Phân biệt @Description với các annotation lân cận

Các annotation trong Spring Data REST có thể xuất hiện cùng nhau nhưng đảm nhiệm vai trò khác nhau:

| Annotation | Vai trò |
|---|---|
| @Description | Giải thích ngữ nghĩa của resource hoặc property |
| @RepositoryRestResource | Cấu hình cách repository được export, collection/item rel và description |
| @RestResource | Cấu hình path, rel, description hoặc trạng thái export của resource gắn với repository/method/field |
| @Param | Đặt tên query parameter cho tham số của query method |
| @Projection | Định nghĩa một representation tùy chỉnh cho domain type |

Ví dụ, @RestResource(path = "by-last-name") đổi path của query resource. @Description bên trong thuộc tính description giải thích query đó làm gì. Hai annotation bổ sung cho nhau nhưng không thay thế nhau.

Tương tự, @Projection chọn các thuộc tính được trả về trong một representation. @Description chỉ giải thích ý nghĩa của resource/property trong metadata; nó không ẩn hoặc thêm field vào projection.

## 9. Kiểm thử mô tả metadata

Không nên chỉ nhìn vào source code rồi kết luận mô tả đã được công bố. Hãy kiểm tra metadata mà ứng dụng thực sự trả về.

### Kiểm tra collection profile

- Khởi động ứng dụng với repository PersonRepository được export.
- Gọi GET /people.
- Xác nhận response có liên kết profile.
- Truy cập profile URI và xác nhận mô tả collection/item xuất hiện trong ALPS tương ứng.

### Kiểm tra property description

- Truy cập profile metadata của people.
- Tìm descriptor person-representation.
- Tìm các descriptor firstName, lastName và status.
- Xác nhận doc.value có nội dung đã khai báo.
- Kiểm tra tên và mô tả khớp property thực tế.

### Kiểm tra query description

- Gọi GET /people/search.
- Xác nhận có liên kết đến query resource by-last-name.
- Gọi GET /people/search/by-last-name?name=Nguyen.
- Kiểm tra query trả kết quả đúng.
- Kiểm tra ALPS metadata của repository có mô tả phù hợp cho query transition/resource.

### Kiểm tra nội dung đa ngôn ngữ

Nếu dùng resource bundle:

- Chạy request với locale mặc định.
- Gửi request với locale khác theo cơ chế locale của ứng dụng.
- Kiểm tra message được phân giải đúng.
- Kiểm tra khi thiếu key có fallback phù hợp, không làm metadata hỏng.

## 10. Lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Không thấy mô tả trong JSON entity | Đang kiểm tra HAL response thay vì ALPS metadata | Theo liên kết profile và đọc ALPS |
| Collection có mô tả nhưng item không có | Chỉ cấu hình collectionResourceDescription | Bổ sung itemResourceDescription |
| Query resource không có mô tả mong muốn | Thiếu description trên @RestResource hoặc query method chưa được export | Kiểm tra annotation, method và metadata |
| Property không có doc.value | Annotation đặt sai field/getter hoặc property không thuộc representation được mô tả | Kiểm tra mapping và vị trí annotation |
| Query path không đổi | Dùng @Description mà chưa cấu hình @RestResource(path = ...) | Đặt path trong @RestResource |
| Client không tìm thấy query resource | Query method không được export hoặc repository không được export | Kiểm tra exported, repository và query method |
| Mô tả hiển thị nguyên key | Resource bundle chưa được cấu hình hoặc key không tồn tại | Kiểm tra MessageSource, tên file và key |
| Mô tả không đúng nghiệp vụ | Nội dung bị sao chép hoặc không khớp hành vi query | Sửa mô tả theo contract thực tế |

## 11. Checklist khi bổ sung @Description

- [ ] Mỗi resource có mô tả rõ ràng về mục đích.
- [ ] Collection resource và item resource có mô tả riêng khi ngữ nghĩa khác nhau.
- [ ] Domain type và các property quan trọng có mô tả phù hợp.
- [ ] Query method mô tả đúng điều kiện tìm kiếm và kết quả.
- [ ] @RestResource vẫn chịu trách nhiệm cấu hình path/rel/export; @Description chỉ cung cấp nội dung mô tả.
- [ ] Không nhầm ALPS metadata với HAL entity representation.
- [ ] Resource bundle được cấu hình đúng nếu dùng key quốc tế hóa.
- [ ] Đã đọc profile metadata để xác nhận nội dung thực tế.
- [ ] Mô tả không chứa thông tin nhạy cảm hoặc chi tiết nội bộ không nên công bố.
- [ ] Mô tả phản ánh đúng contract hiện tại của API.

## Kết luận

@Description bổ sung ngữ nghĩa cho metadata của Spring Data REST. Dùng annotation trên domain type và property để giải thích representation; dùng collectionResourceDescription và itemResourceDescription của @RepositoryRestResource để mô tả hai cấp resource; dùng description của @RestResource để giải thích query resource. Sau khi cấu hình, hãy kiểm tra profile/ALPS metadata để xác nhận client thực sự nhận được nội dung mong muốn.

Mô tả tốt giúp API dễ khám phá và giảm việc client phải suy đoán từ tên field hoặc tên endpoint. Nó là tài liệu metadata của contract, không thay thế validation, projection hay logic xử lý dữ liệu.

## Tài liệu tham khảo

- Spring Data REST — Metadata and ALPS: https://docs.spring.io/spring-data/rest/reference/metadata.html
- Spring Data REST 5.1 API — Description: https://docs.spring.io/spring-data/rest/docs/5.1.x/api/org/springframework/data/rest/core/annotation/Description.html
- Spring Data REST 5.1 API — RepositoryRestResource: https://docs.spring.io/spring-data/rest/reference/api/java/org/springframework/data/rest/core/annotation/RepositoryRestResource.html
- Spring Data REST 5.0 API — RestResource: https://docs.spring.io/spring-data/rest/reference/5.0/api/java/org/springframework/data/rest/core/annotation/RestResource.html
