# PersistentEntityResourceAssembler cho biểu diễn entity nhất quán

## Mục tiêu

Sau bài này, bạn có thể:

- Giải thích PersistentEntityResourceAssembler tạo ra kiểu resource nào và vì sao Spring Data REST cung cấp nó.
- Dùng assembler trong một custom controller để trả entity theo định dạng hypermedia thống nhất với repository endpoint.
- Phân biệt việc chuyển entity thành representation với việc truy vấn hoặc lưu entity.
- Biết khi nào nên dùng assembler, khi nào nên dùng EntityModel/DTO và khi nào cần bổ sung link nghiệp vụ.
- Kiểm tra response để phát hiện trường hợp custom endpoint làm mất metadata hoặc HAL links.

## 1. Vấn đề khi tự viết endpoint

Spring Data REST tự xuất bản các repository thành REST resources. Một item endpoint như GET /people/42 thường trả về representation có dữ liệu entity cùng các hypermedia links, chẳng hạn self và các association links.

Trong thực tế, ứng dụng thường cần custom endpoint để bổ sung nghiệp vụ: trả về một góc nhìn tổng hợp, chạy một truy vấn đặc biệt, hoặc thực hiện bước xử lý trước khi trả kết quả. Nếu controller chỉ trả trực tiếp entity hoặc tự tạo JSON, response có thể không còn nhất quán với resource do Spring Data REST tạo:

- Thiếu self link hoặc các association links mà client đang dùng để khám phá API.
- Không đi theo metadata và mapping mà Spring Data REST đã cấu hình cho entity.
- Khác cách biểu diễn của repository endpoint, khiến client phải xử lý hai dạng response cho cùng một loại entity.
- Dễ tạo URL bằng cách ghép chuỗi, rồi sai khi base path hoặc resource path thay đổi.

PersistentEntityResourceAssembler giải quyết phần chuyển entity thành representation theo cơ chế resource của Spring Data REST. Custom controller vẫn tự quyết định truy vấn và nghiệp vụ; assembler đảm nhiệm việc đóng gói entity thành resource.

## 2. PersistentEntityResourceAssembler là gì?

PersistentEntityResourceAssembler thuộc package org.springframework.data.rest.webmvc. Đây là một RepresentationModelAssembler<Object, PersistentEntityResource>, nghĩa là nó nhận một domain object và tạo ra PersistentEntityResource.

Phương thức thường dùng là:

~~~java
PersistentEntityResource resource = assembler.toModel(person);
~~~

PersistentEntityResource là một lớp con của Spring HATEOAS EntityModel<Object>. Ngoài nội dung entity và links, nó còn giữ PersistentEntity metadata tương ứng với entity được biểu diễn. Metadata này cho phép Spring Data REST xử lý representation theo mô hình persistent entity của nó.

Assembler được xây dựng dựa trên các thành phần hạ tầng như:

- PersistentEntities: tra cứu metadata của các persistent entity.
- Projector: xử lý cơ chế projection khi tạo representation.
- Associations: cung cấp thông tin về association và cách biểu diễn chúng.
- SelfLinkProvider: cung cấp self link cho entity.

Bạn không cần tự tạo các dependency này hoặc tự gọi constructor trong controller thông thường. Spring Data REST cung cấp assembler phù hợp cho request thông qua cơ chế phân giải tham số của controller.

Hãy phân biệt rõ ba trách nhiệm:

| Thành phần | Trách nhiệm |
|---|---|
| Repository | Tìm, tạo, cập nhật hoặc xóa entity theo nghiệp vụ dữ liệu |
| Controller/service | Điều phối request, kiểm tra quyền, áp dụng nghiệp vụ và quyết định response |
| PersistentEntityResourceAssembler | Chuyển entity đã có thành PersistentEntityResource theo metadata và cơ chế biểu diễn của Spring Data REST |

Gọi assembler không tự chạy repository query, không gọi save và không ghi dữ liệu xuống database. Nó chỉ tạo representation từ object mà bạn truyền vào.

## 3. Dùng assembler trong Repository REST Controller

Để custom handler tham gia vào không gian endpoint của Spring Data REST, dùng @RepositoryRestController. Annotation này giúp controller dùng API base path và các thiết lập Spring Data REST như message converters, exception handling và cấu hình liên quan.

Ví dụ, giả sử ứng dụng có entity Person và repository:

~~~java
@Entity
public class Person {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    private String firstName;
    private String lastName;

    protected Person() {
    }

    public Person(String firstName, String lastName) {
        this.firstName = firstName;
        this.lastName = lastName;
    }

    public Long getId() {
        return id;
    }

    public String getFirstName() {
        return firstName;
    }

    public String getLastName() {
        return lastName;
    }
}
~~~

~~~java
public interface PersonRepository
        extends JpaRepository<Person, Long> {
}
~~~

Ta muốn tạo một endpoint custom để trả về một Person sau khi áp dụng thêm logic nghiệp vụ:

~~~java
@RepositoryRestController
public class PersonDetailsController {

    private final PersonRepository personRepository;

    public PersonDetailsController(PersonRepository personRepository) {
        this.personRepository = personRepository;
    }

    @GetMapping("/people/{id}/details")
    public ResponseEntity<PersistentEntityResource> getDetails(
            @PathVariable Long id,
            PersistentEntityResourceAssembler assembler) {

        return personRepository.findById(id)
                .map(person -> {
                    // Thực hiện kiểm tra hoặc xử lý nghiệp vụ tại đây.
                    PersistentEntityResource resource =
                            assembler.toModel(person);

                    return ResponseEntity.ok(resource);
                })
                .orElseGet(() -> ResponseEntity.notFound().build());
    }
}
~~~

Các điểm cần hiểu:

1. Controller nhận PersonRepository qua constructor injection để truy vấn entity.
2. PersistentEntityResourceAssembler được khai báo trực tiếp như một method parameter. Spring Data REST đăng ký argument resolver để cung cấp assembler cho handler method.
3. findById(id) chịu trách nhiệm tìm entity. Nếu không tồn tại, controller trả 404 Not Found.
4. assembler.toModel(person) tạo PersistentEntityResource từ entity đã tìm được.
5. ResponseEntity.ok(resource) trả resource qua cơ chế message conversion đang được Spring Data REST cấu hình.

Đường dẫn custom được viết tương đối với API base path. Ví dụ, nếu base path là /api, endpoint đầy đủ sẽ có dạng /api/people/{id}/details. Đường dẫn thực tế còn phụ thuộc cấu hình của ứng dụng và mapping repository.

## 4. Response có gì khác khi dùng assembler?

Response dưới đây chỉ minh họa cấu trúc có thể gặp; relation name, URI và các property thực tế phụ thuộc entity mapping, repository configuration, projection và cấu hình serialization của ứng dụng.

~~~json
{
  "id": 42,
  "firstName": "An",
  "lastName": "Nguyen",
  "_links": {
    "self": {
      "href": "http://localhost:8080/api/people/42"
    }
  }
}
~~~

Với entity có association được Spring Data REST xuất bản, representation còn có thể chứa các links tương ứng với association đó. Client có thể dùng self link để quay lại item resource và dùng association link để khám phá resource liên quan.

Assembler giúp custom endpoint sử dụng cùng cơ chế biểu diễn entity của Spring Data REST. Tuy nhiên, không nên xem mọi response đều có một bộ link cố định. Links nào xuất hiện phụ thuộc metadata, association exposure, mapping, quyền truy cập và cấu hình của ứng dụng.

Điều này đặc biệt hữu ích khi custom endpoint trả về chính entity mà repository endpoint đang quản lý. Client có thể tiếp tục sử dụng cách điều hướng hypermedia quen thuộc thay vì phải học một cấu trúc response hoàn toàn khác.

## 5. toModel và toFullResource

PersistentEntityResourceAssembler cung cấp hai phương thức đáng chú ý:

- toModel(instance): phương thức chuẩn của RepresentationModelAssembler, tạo PersistentEntityResource cho object được truyền vào.
- toFullResource(instance): tạo PersistentEntityResource biểu diễn full object bằng Projector bên trong assembler.

Trong phần lớn custom handler, bắt đầu với toModel. Chỉ chọn toFullResource khi yêu cầu response thực sự cần biểu diễn đầy đủ object theo semantics của API và bạn đã kiểm tra ảnh hưởng tới projection, serialization và dữ liệu được phép công khai.

Đừng dùng toFullResource như một cách bỏ qua kiểm soát dữ liệu. Projection và serialization configuration có thể ảnh hưởng trực tiếp tới những field client nhìn thấy. Hãy kiểm tra response thực tế bằng request tương ứng.

## 6. Xử lý collection

Assembler cũng triển khai RepresentationModelAssembler, nên có thể dùng khả năng tạo collection model được kế thừa từ Spring HATEOAS.

Ví dụ:

~~~java
@GetMapping("/people/active")
public ResponseEntity<CollectionModel<PersistentEntityResource>> getActivePeople(
        PersistentEntityResourceAssembler assembler) {

    List<Person> people = personRepository.findByActiveTrue();

    CollectionModel<PersistentEntityResource> resources =
            assembler.toCollectionModel(people);

    return ResponseEntity.ok(resources);
}
~~~

Ví dụ trên giả định repository có phương thức findByActiveTrue phù hợp với entity. Nếu phương thức chưa tồn tại, hãy khai báo nó trong repository hoặc thay bằng truy vấn thực tế của ứng dụng.

Điểm quan trọng là mỗi entity trong collection đều được chuyển thành PersistentEntityResource thông qua cùng assembler. Cách làm này giúp representation của từng item nhất quán với cách biểu diễn entity đơn lẻ.

Với collection có phân trang, sắp xếp hoặc metadata riêng, cần chọn cách tạo collection response phù hợp với contract của endpoint. Không nên tự bỏ page metadata hoặc pagination links nếu client cần chúng.

## 7. Bổ sung link cho nghiệp vụ custom

Assembler tập trung vào representation của persistent entity và các links do Spring Data REST quản lý. Nó không tự biết mọi hành động nghiệp vụ mà ứng dụng định nghĩa.

Ví dụ, endpoint có thể cần thêm link để xem lịch sử giao dịch của một Person. Bạn có thể thêm link sau khi assembler tạo resource:

~~~java
PersistentEntityResource resource = assembler.toModel(person);

resource.add(
    linkTo(methodOn(PersonDetailsController.class)
        .getHistory(person.getId()))
        .withRel("history")
);

return ResponseEntity.ok(resource);
~~~

Đoạn code giả định controller có method getHistory(Long id) và đã khai báo mapping tương ứng. Cần bổ sung import của Spring HATEOAS:

~~~java
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;
~~~

Link history là link nghiệp vụ do ứng dụng thêm vào. Nó không tự xuất hiện chỉ vì assembler nhận được entity.

Nếu cần thêm hoặc biến đổi links một cách tập trung cho mọi response của một loại entity, hãy cân nhắc extension point như ResourceProcessor. Nếu chỉ cần bổ sung link cho một custom handler cụ thể, thêm link vào representation tại controller có thể dễ hiểu hơn.

## 8. Khi nào nên dùng PersistentEntityResourceAssembler?

| Nhu cầu | Cách phù hợp |
|---|---|
| Custom endpoint trả một entity do Spring Data REST quản lý | PersistentEntityResourceAssembler.toModel |
| Custom endpoint trả nhiều entity cùng kiểu resource | assembler.toCollectionModel |
| Response là DTO có cấu trúc riêng, không phải representation của persistent entity | EntityModel<YourDto> hoặc DTO thông thường |
| Cần tự thiết kế toàn bộ links và representation | Spring HATEOAS RepresentationModel/EntityModel và assembler riêng |
| Muốn thêm link nghiệp vụ vào entity resource | Tạo resource bằng assembler rồi thêm link |
| Muốn bổ sung link/metadata tập trung cho nhiều response | Cân nhắc ResourceProcessor |

Không nên dùng PersistentEntityResourceAssembler chỉ vì controller có một object Java. Nó phù hợp khi object thuộc mô hình persistent entity mà Spring Data REST quản lý và bạn muốn giữ contract hypermedia của Spring Data REST.

Nếu API cần schema công khai khác với entity nội bộ, hãy tạo DTO. Không nên để cấu trúc database quyết định toàn bộ API contract chỉ vì assembler có thể chuyển entity thành resource.

## 9. Những lỗi thường gặp

- **Trả trực tiếp entity:** response có thể thiếu resource links hoặc không dùng đúng cơ chế biểu diễn của Spring Data REST. Dùng assembler khi endpoint cần trả persistent entity resource.
- **Tự khởi tạo assembler bằng constructor:** constructor yêu cầu nhiều dependency nội bộ như PersistentEntities, Projector, Associations và SelfLinkProvider. Hãy nhận assembler do framework cung cấp trong handler method.
- **Dùng @RestController cho endpoint thuộc Spring Data REST:** controller chuẩn có thể nằm ngoài phạm vi xử lý của Spring Data REST, dẫn đến khác base path, message converters và exception handling. Dùng @RepositoryRestController cho handler thuộc không gian repository.
- **Nghĩ assembler tự lưu entity:** assembler chỉ tạo representation. Muốn thay đổi dữ liệu, phải thực hiện nghiệp vụ và gọi repository/service thích hợp.
- **Cho rằng mọi custom action sẽ tự có link:** assembler không tự suy ra các hành động nghiệp vụ riêng. Hãy thêm link bằng Spring HATEOAS hoặc dùng ResourceProcessor khi phù hợp.
- **Dùng assembler để thay thế DTO:** PersistentEntityResource vẫn biểu diễn persistent entity. Nếu cần ẩn hoặc đổi cấu trúc field, hãy thiết kế projection hoặc DTO phù hợp.
- **Bỏ qua kiểm soát dữ liệu:** assembler không thay thế authorization. Phải kiểm tra quyền truy cập ở controller/service và xác nhận các field được serialization công khai là an toàn.
- **Giả định response có link cố định:** self link, association links và relation name phụ thuộc cấu hình thực tế. Hãy kiểm tra response từ ứng dụng.

## 10. Cách kiểm tra custom endpoint

Khi kiểm tra endpoint dùng PersistentEntityResourceAssembler, hãy xác minh cả dữ liệu lẫn hypermedia:

1. Gửi GET tới custom endpoint với Accept: application/hal+json.
2. Kiểm tra status code, Content-Type và các property dự kiến.
3. Kiểm tra self link có URI trỏ tới item resource đúng hay không.
4. Với entity có association được xuất bản, kiểm tra relation links có phù hợp cấu hình hay không.
5. Kiểm tra base path khi ứng dụng bật spring.data.rest.base-path.
6. Kiểm tra request có projection parameter nếu endpoint hỗ trợ projection.
7. Kiểm tra trường hợp entity không tồn tại và xác nhận controller trả 404.
8. Kiểm tra authorization và đảm bảo dữ liệu nhạy cảm không xuất hiện ngoài ý muốn.

Không chỉ kiểm tra JSON có chứa field id. Mục đích của assembler là tạo một resource nhất quán, nên test cần xác nhận links và contract hypermedia mà client thực sự sử dụng.

## 11. Bài tập tự kiểm tra

Một custom handler tìm thấy Person có id = 42. Bạn cần trả entity đó cùng resource links theo cơ chế Spring Data REST.

**Câu 1.** Phương thức nào của PersistentEntityResourceAssembler thường được gọi để tạo representation?

**Câu 2.** Vì sao nên nhận assembler như method parameter thay vì tự gọi constructor?

**Câu 3.** Repository trả Optional.empty() thì controller nên trả kết quả nào?

**Câu 4.** Assembler có gọi save() hoặc ghi entity xuống database không?

**Câu 5.** Nếu cần thêm link history trỏ tới một custom action, assembler có tự tạo link đó không?

**Đáp án:**

1. Gọi assembler.toModel(person).
2. Spring Data REST cung cấp assembler đã được cấu hình với metadata, projector, association handling và self-link provider của hệ thống.
3. Trả 404 Not Found.
4. Không. Assembler chỉ chuyển object thành representation.
5. Không. Controller hoặc ResourceProcessor phải bổ sung link nghiệp vụ bằng Spring HATEOAS.

## 12. Ghi nhớ

- PersistentEntityResourceAssembler là RepresentationModelAssembler chuyên tạo PersistentEntityResource từ domain object.
- PersistentEntityResource kế thừa EntityModel và giữ PersistentEntity metadata.
- Nhận assembler như tham số của handler method trong custom @RepositoryRestController.
- Dùng toModel cho representation thông thường; cân nhắc toFullResource khi thật sự cần full object.
- Assembler không truy vấn, lưu hay thay đổi entity.
- Dùng EntityModel/DTO khi API cần contract riêng; thêm link nghiệp vụ bằng Spring HATEOAS hoặc ResourceProcessor.
- Kiểm tra status, media type, self link, association links, projection và authorization bằng response thực tế.

## Tài liệu tham khảo

- Spring Data REST API — PersistentEntityResourceAssembler: https://www.springframework.org/spring-data/rest/reference/api/java/org/springframework/data/rest/webmvc/PersistentEntityResourceAssembler.html
- Spring Data REST API — PersistentEntityResource: https://docs.spring.io/spring-data/rest/reference/api/java/org/springframework/data/rest/webmvc/PersistentEntityResource.html
- Spring Data REST Reference — Overriding Spring Data REST Response Handlers: https://www.springframework.org/spring-data/rest/reference/5.0/customizing/overriding-sdr-response-handlers.html
