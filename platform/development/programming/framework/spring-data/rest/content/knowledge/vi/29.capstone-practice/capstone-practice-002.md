# Thực hành CRUD và kiểm chứng khác biệt PUT, PATCH, DELETE trong Spring Data REST

## Mục tiêu

Bài thực hành này dùng một repository được Spring Data REST export để tạo, đọc, thay thế, cập nhật một phần và xóa tài nguyên. Mục tiêu là nhìn thấy sự khác nhau ở cả ba lớp:

1. **HTTP contract**: URI, method, request body, media type, header và status code.
2. **Trạng thái dữ liệu**: trường nào được thay đổi, trường nào được giữ, tài nguyên hoặc liên kết nào bị xóa.
3. **Tính đúng đắn khi có nhiều client**: ETag, `If-Match`, xử lý retry và kiểm thử tích hợp.

Spring Data REST tự tạo collection resource và item resource từ Spring Data repository. Vì thế, trước khi gửi request, cần xác định đúng loại URI đang thao tác.

## 1. Chuẩn bị repository và domain

Ví dụ dùng Spring Data JPA. Một repository tối thiểu có thể là:

~~~java
@RepositoryRestResource(path = "products", collectionResourceRel = "products")
public interface ProductRepository extends JpaRepository<Product, Long> {
}
~~~

Entity minh họa:

~~~java
@Entity
public class Product {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false, unique = true)
    private String sku;

    @Column(nullable = false)
    private String name;

    private BigDecimal price;

    @Version
    private Long version;

    protected Product() {
    }

    // Constructor, getters và setters theo nhu cầu của dự án.
}
~~~

Trong ví dụ này:

- Collection resource là `/products`.
- Item resource của sản phẩm có ID `42` là `/products/42`.
- `@Version` của JPA cho phép Spring Data REST dùng version làm ETag để bảo vệ thao tác cập nhật/xóa đồng thời.
- `unique = true` chỉ có tác dụng khi schema thật có unique constraint tương ứng. Trong dự án thực tế, xác nhận migration đã tạo constraint.

Nếu không cần tùy chỉnh đường dẫn, Spring Data REST thường tạo tên collection bằng cách viết thường và số nhiều tên domain type. Hãy khám phá root HAL và dùng các link được trả về thay vì giả định đường dẫn trong client.

## 2. Phân biệt collection resource, item resource và association resource

| Resource | URI ví dụ | Method hỗ trợ mặc định | Ý nghĩa |
| --- | --- | --- | --- |
| Collection | `/products` | GET, POST | Đọc danh sách, tạo entity mới |
| Item | `/products/42` | GET, PUT, PATCH, DELETE | Đọc, thay thế, cập nhật một phần, xóa entity |
| Association | `/products/42/category` | GET, PUT, POST, DELETE tùy quan hệ | Đọc hoặc thay đổi liên kết giữa entity |

Collection resource không nhận PUT, PATCH hoặc DELETE theo mặc định. Các method đó trên collection thường trả `405 Method Not Allowed`. Để thay đổi một entity, dùng item URI.

Spring Data REST chỉ xuất các method mà repository thực sự có và cho phép export. Ví dụ, nếu `save(...)` không có hoặc được đánh dấu `@RestResource(exported = false)`, POST/PUT/PATCH tương ứng sẽ không được cung cấp. Nếu các phương thức `delete(...)` bị ẩn, DELETE cũng không được cung cấp.

## 3. CRUD cơ bản bằng HTTP

Giả sử ứng dụng chạy tại `http://localhost:8080`. Các lệnh dưới đây dùng `application/json` cho request body và `application/hal+json` để yêu cầu representation HAL ở response.

### 3.1. GET — đọc collection và item

Đọc collection:

~~~bash
curl -i -H 'Accept: application/hal+json' 'http://localhost:8080/products?page=0&size=20'
~~~

Nếu repository hỗ trợ phân trang, response có metadata trang và các link điều hướng. Đọc một item:

~~~bash
curl -i -H 'Accept: application/hal+json' 'http://localhost:8080/products/42'
~~~

Response item có các trường của entity và `_links`, ví dụ:

~~~json
{
  "sku": "KB-001",
  "name": "Keyboard",
  "price": 49.90,
  "_links": {
    "self": {
      "href": "http://localhost:8080/products/42"
    },
    "product": {
      "href": "http://localhost:8080/products/42"
    }
  }
}
~~~

Ví dụ trên chỉ minh họa cấu trúc. Các link và trường thực tế phụ thuộc domain model, projection, cấu hình và media type. Client nên theo link `self` từ response khi cần gọi lại tài nguyên.

### 3.2. POST — tạo entity mới qua collection

POST vào collection URI:

~~~bash
curl -i -X POST 'http://localhost:8080/products' -H 'Content-Type: application/json' -H 'Accept: application/hal+json' -d '{"sku":"KB-001","name":"Keyboard","price":49.90}'
~~~

POST tạo một entity mới từ body. Response thành công thường là `201 Created` và có header `Location` trỏ tới item vừa tạo. Nếu có `Accept`, Spring Data REST mặc định có thể trả thêm representation; nếu không, client lấy URI từ `Location` rồi GET item. Cấu hình `RepositoryRestConfiguration.setReturnBodyOnCreate(...)` có thể thay đổi hành vi trả body.

POST phù hợp khi client gửi dữ liệu để collection/resource phía server tạo ra tài nguyên và xác định URI. POST không mặc nhiên idempotent: gửi lặp cùng request có thể tạo nhiều entity nếu ứng dụng không có cơ chế chống trùng hoặc idempotency key.

### 3.3. PUT — thay thế trạng thái item

PUT gửi representation mô tả trạng thái đầy đủ mà client muốn đặt cho item tại URI đã biết:

~~~bash
curl -i -X PUT 'http://localhost:8080/products/42' -H 'Content-Type: application/json' -H 'Accept: application/hal+json' -d '{"sku":"KB-001","name":"Keyboard Pro","price":59.90}'
~~~

Trong Spring Data REST, PUT trên item resource gọi đường lưu `save(...)` và thay thế trạng thái resource theo ngữ nghĩa PUT. Vì vậy, client nên gửi đầy đủ các trường có thể ghi theo hợp đồng của resource. Không nên dùng PUT như một PATCH ngầm bằng cách chỉ gửi một trường rồi giả định mọi trường còn lại luôn được giữ nguyên.

Không gửi ID hoặc version do client tự đặt trong body. ID do URI xác định; version được bảo vệ bằng cơ chế version/ETag. Hãy kiểm thử riêng cách ứng dụng ánh xạ các thuộc tính bị bỏ khỏi body, giá trị null, object lồng nhau và các thuộc tính read-only theo entity/Jackson mapping thực tế.

Với cấu hình mặc định của Spring Data REST, khi request có header `Accept`, PUT update thường trả `200 OK` kèm body. Khi không có `Accept`, response update thường là `204 No Content`. Cấu hình `RepositoryRestConfiguration.setReturnBodyOnUpdate(...)` có thể ép hành vi này.

### 3.4. PATCH — cập nhật một phần item

PATCH gửi một patch document mô tả thay đổi. Ví dụ dùng JSON Merge Patch:

~~~bash
curl -i -X PATCH 'http://localhost:8080/products/42' -H 'Content-Type: application/merge-patch+json' -H 'Accept: application/hal+json' -d '{"name":"Keyboard Pro"}'
~~~

Với JSON Merge Patch theo RFC 7396:

- Thuộc tính không xuất hiện trong patch được giữ nguyên.
- Thuộc tính xuất hiện với giá trị khác null được thêm mới hoặc thay thế.
- Thuộc tính có giá trị `null` mang nghĩa xóa member khỏi JSON representation.
- Object lồng nhau được merge đệ quy.
- Array được thay thế như một giá trị, không merge từng phần tử theo index.

Ví dụ resource hiện tại:

~~~json
{
  "sku": "KB-001",
  "name": "Keyboard",
  "price": 49.90,
  "description": "Mechanical"
}
~~~

Patch:

~~~json
{
  "name": "Keyboard Pro",
  "description": null
}
~~~

Sau khi áp dụng merge patch, tên đổi thành `Keyboard Pro`, thuộc tính `description` bị loại khỏi representation theo semantics của JSON Merge Patch, còn `sku` và `price` được giữ nguyên. Khi ánh xạ vào entity Java, kết quả của việc xóa thuộc tính còn phụ thuộc mapping, nullability và cách domain model biểu diễn trạng thái đó; kiểm thử với entity thật.

Spring Data REST tài liệu hóa các media type PATCH gồm `application/hal+json`, `application/json`, `application/patch+json` và `application/merge-patch+json`. Hãy chọn đúng format mà client và server cùng hiểu. Không suy ra semantics chỉ từ HTTP method PATCH: RFC 5789 định nghĩa PATCH nhận patch document có format được nhận diện bằng media type; mỗi format có quy tắc riêng.

PATCH có thể không idempotent tùy loại patch document. Nếu patch dựa trên một phiên bản dữ liệu đã đọc trước đó, nên gửi `If-Match` để server từ chối patch trên phiên bản đã thay đổi.

### 3.5. DELETE — xóa item resource

Xóa item:

~~~bash
curl -i -X DELETE 'http://localhost:8080/products/42'
~~~

DELETE trên item resource gọi một trong các phương thức repository `delete(T)`, `delete(ID)` hoặc `delete(Iterable)`, tùy phương thức có sẵn. Với cấu hình mặc định, nếu không gửi `Accept`, response thành công thường là `204 No Content`; khi có `Accept`, Spring Data REST có thể trả body cùng `200 OK`. `RepositoryRestConfiguration.setReturnBodyOnDelete(...)` có thể thay đổi hành vi.

DELETE item xóa entity được URI xác định. Việc entity liên quan có bị xóa theo hay không phụ thuộc mapping JPA, cascade, orphan removal và constraint của database. Không giả định DELETE một item sẽ tự động xóa tất cả entity liên quan.

HTTP định nghĩa DELETE là idempotent theo hiệu ứng dự kiến: gửi lại cùng yêu cầu không làm trạng thái tài nguyên trở lại trạng thái khác. Response của lần gọi thứ hai vẫn có thể là `404 Not Found` vì tài nguyên đã bị xóa ở lần đầu; điều đó không làm mất tính idempotent của thao tác.

## 4. PUT, PATCH và DELETE khác nhau ở đâu?

| Tiêu chí | PUT | PATCH | DELETE |
| --- | --- | --- | --- |
| Mục đích | Thay thế trạng thái item | Áp dụng một phần thay đổi | Xóa item |
| URI điển hình | Item URI | Item URI | Item URI |
| Request body | Representation của trạng thái muốn đặt | Patch document theo media type | Thường không cần body |
| Trường không gửi | Không nên dựa vào semantics giữ nguyên; gửi đầy đủ writable state | Thường không thay đổi với JSON Merge Patch | Không áp dụng |
| Idempotency theo HTTP | Có | Không được bảo đảm bởi method | Có |
| Spring Data REST gọi | `save(...)` | `save(...)` | `delete(...)` |
| Bảo vệ cập nhật đồng thời | Có thể dùng `If-Match` | Nên dùng `If-Match` khi patch dựa trên bản đã đọc | Có thể dùng `If-Match` để tránh xóa bản mới hơn |

Điểm cần nhớ:

- PUT là ý định đặt trạng thái resource theo representation gửi lên.
- PATCH là ý định áp dụng một tập thay đổi; media type xác định cách diễn giải patch.
- DELETE là ý định làm resource không còn tồn tại tại URI đó.
- POST collection tạo resource mới; không thay thế PUT/PATCH trên item URI.
- `Content-Type` mô tả định dạng body gửi lên. `Accept` mô tả định dạng response client muốn nhận. Hai header có vai trò khác nhau.

Theo RFC 9110, PUT và DELETE là idempotent. PATCH không được bảo đảm idempotent; một patch cụ thể có thể được thiết kế idempotent, nhưng client phải hiểu semantics của patch document trước khi tự động retry.

## 5. DELETE trên item và DELETE trên association không giống nhau

Spring Data REST tạo association resource cho quan hệ của entity. Ví dụ:

~~~text
/products/42/category
~~~

Các thao tác trên association có semantics riêng:

- GET đọc liên kết.
- PUT gắn URI của resource đích vào association.
- POST chỉ dành cho collection association và thêm phần tử vào collection.
- DELETE bỏ liên kết khỏi association.

Ví dụ gán category cho product:

~~~bash
curl -i -X PUT 'http://localhost:8080/products/42/category' -H 'Content-Type: text/uri-list' --data 'http://localhost:8080/categories/5'
~~~

Ví dụ bỏ liên kết:

~~~bash
curl -i -X DELETE 'http://localhost:8080/products/42/category'
~~~

Các request association dùng `text/uri-list`, chứa URI của resource liên quan, không phải JSON object tùy ý. Với association to-one, PUT chỉ nhận một URI; gửi nhiều URI sẽ bị từ chối. DELETE association unbind quan hệ, không đồng nghĩa xóa category hoặc product. Với collection association, POST thêm một phần tử; PUT có thể thay tập URI đang liên kết theo semantics của association resource.

Hãy theo link association do HAL trả về thay vì tự ghép tên property nếu repository đã tùy chỉnh quan hệ bằng `@RestResource`.

## 6. Status code và cách đọc response

Các status thành công thường gặp:

| Request | Kết quả mặc định thường gặp |
| --- | --- |
| GET collection/item | `200 OK` |
| POST collection tạo mới | `201 Created` và `Location` |
| PUT item cập nhật | `200 OK` nếu response body được bật; nếu không thường `204 No Content` |
| PATCH item cập nhật | `200 OK` nếu response body được bật; nếu không thường `204 No Content` |
| DELETE item | `200 OK` nếu response body được bật; nếu không thường `204 No Content` |

Với PUT/PATCH/DELETE, sự hiện diện của `Accept` quyết định việc trả body khi cấu hình `returnBodyOnUpdate` hoặc `returnBodyOnDelete` là null. Nếu dự án cấu hình rõ `setReturnBodyOnUpdate`, `setReturnBodyOnDelete` hoặc các tùy chọn tương ứng, giá trị cấu hình được ưu tiên.

Các lỗi thường gặp:

| Status | Nguyên nhân cần kiểm tra |
| --- | --- |
| `400 Bad Request` | JSON sai cú pháp, kiểu dữ liệu không hợp lệ, validation thất bại hoặc gửi nhiều URI cho association to-one |
| `401 Unauthorized` / `403 Forbidden` | Chưa xác thực hoặc không có quyền với method/resource |
| `404 Not Found` | Item URI không tồn tại, hoặc link/URI client dùng đã cũ |
| `405 Method Not Allowed` | Dùng PUT/PATCH/DELETE trên collection, hoặc repository/method không được export |
| `409 Conflict` | Vi phạm unique/foreign-key constraint hoặc optimistic locking thất bại ở tầng repository |
| `412 Precondition Failed` | ETag hiện tại không khớp header `If-Match` |
| `415 Unsupported Media Type` | `Content-Type` không được endpoint chấp nhận |

Đây là hướng chẩn đoán phổ biến. Security configuration, validation, exception handler tùy chỉnh và phiên bản Spring Data REST có thể ảnh hưởng response cuối cùng.

### 6.1. Phân biệt 409 và 412

Nếu entity có trường `@Version`, Spring Data REST có thể trả ETag tương ứng với version. GET item để lấy ETag:

~~~http
GET /products/42
ETag: "7"
~~~

Gửi PUT, PATCH hoặc DELETE kèm ETag đã đọc:

~~~bash
curl -i -X PATCH 'http://localhost:8080/products/42' -H 'If-Match: "7"' -H 'Content-Type: application/merge-patch+json' -H 'Accept: application/hal+json' -d '{"name":"New name"}'
~~~

Chỉ thực hiện thao tác nếu ETag hiện tại khớp `If-Match`. Nếu một client khác đã cập nhật tài nguyên, request dùng ETag cũ nhận `412 Precondition Failed`. Đây là kiểm tra HTTP precondition.

Nếu hai transaction cùng sửa dữ liệu và persistence layer phát hiện version không khớp khi lưu, repository có thể ném `OptimisticLockingFailureException`, thường được xử lý như `409 Conflict`. Khi điều tra, xem exception thực tế và header request; đừng gộp hai đường lỗi thành một.

## 7. Kiểm thử CRUD với MockMvc

Dùng integration test để xác nhận cả HTTP contract và trạng thái dữ liệu sau request. Ví dụ dưới đây giả định:

- `ProductRepository` được Spring Data REST export tại `/products`.
- Database test có schema và constraint tương ứng.
- `Product` có các thuộc tính `sku`, `name`, `price`, `version`.
- Cấu hình mặc định cho phép trả body khi request có `Accept`.

Khung test:

~~~java
@SpringBootTest
@AutoConfigureMockMvc
class ProductCrudRestTests {

    @Autowired
    MockMvc mvc;

    @Autowired
    ProductRepository repository;

    @BeforeEach
    void cleanDatabase() {
        repository.deleteAll();
    }

    @Test
    void postCreatesResourceAndReturnsLocation() throws Exception {
        mvc.perform(post("/products")
                .contentType(MediaType.APPLICATION_JSON)
                .accept("application/hal+json")
                .content("""
                    {"sku":"SKU-001","name":"Keyboard","price":49.90}
                    """))
            .andExpect(status().isCreated())
            .andExpect(header().exists("Location"));

        assertThat(repository.findAll()).hasSize(1);
    }

    @Test
    void putReplacesTheItemState() throws Exception {
        Product product = new Product();
        product.setSku("SKU-001");
        product.setName("Keyboard");
        product.setPrice(new BigDecimal("49.90"));
        Product saved = repository.saveAndFlush(product);

        mvc.perform(put("/products/{id}", saved.getId())
                .contentType(MediaType.APPLICATION_JSON)
                .accept("application/hal+json")
                .content("""
                    {"sku":"SKU-001","name":"Keyboard Pro","price":59.90}
                    """))
            .andExpect(status().isOk());

        Product reloaded = repository.findById(saved.getId()).orElseThrow();
        assertThat(reloaded.getName()).isEqualTo("Keyboard Pro");
        assertThat(reloaded.getPrice()).isEqualByComparingTo("59.90");
    }

    @Test
    void patchChangesOnlyTheNamedProperty() throws Exception {
        Product product = new Product();
        product.setSku("SKU-002");
        product.setName("Mouse");
        product.setPrice(new BigDecimal("20.00"));
        Product saved = repository.saveAndFlush(product);

        mvc.perform(patch("/products/{id}", saved.getId())
                .contentType("application/merge-patch+json")
                .accept("application/hal+json")
                .content("""
                    {"name":"Wireless Mouse"}
                    """))
            .andExpect(status().isOk());

        Product reloaded = repository.findById(saved.getId()).orElseThrow();
        assertThat(reloaded.getName()).isEqualTo("Wireless Mouse");
        assertThat(reloaded.getSku()).isEqualTo("SKU-002");
        assertThat(reloaded.getPrice()).isEqualByComparingTo("20.00");
    }

    @Test
    void deleteRemovesTheItem() throws Exception {
        Product product = new Product();
        product.setSku("SKU-003");
        product.setName("Monitor");
        product.setPrice(new BigDecimal("150.00"));
        Product saved = repository.saveAndFlush(product);

        mvc.perform(delete("/products/{id}", saved.getId()))
            .andExpect(status().isNoContent());

        assertThat(repository.existsById(saved.getId())).isFalse();
    }
}
~~~

Các test là mẫu để điều chỉnh theo constructor, getter/setter, database và cấu hình response của dự án. Nếu `Accept` hoặc `RepositoryRestConfiguration` được thay đổi, status/body expectation cần thay đổi tương ứng. Test PATCH cần xác nhận cả trường được sửa và trường không xuất hiện trong patch vẫn giữ nguyên.

### 7.1. Kiểm thử ETag và stale update

Tạo một item có `@Version`, GET item để lấy ETag, sau đó cập nhật qua repository để tăng version. Gửi PATCH bằng ETag cũ:

~~~java
MvcResult firstRead = mvc.perform(get("/products/{id}", id)
        .accept("application/hal+json"))
    .andExpect(status().isOk())
    .andReturn();

String staleEtag = firstRead.getResponse().getHeader("ETag");
assertThat(staleEtag).isNotBlank();

Product latest = repository.findById(id).orElseThrow();
latest.setName("Changed by another client");
repository.saveAndFlush(latest);

mvc.perform(patch("/products/{id}", id)
        .header("If-Match", staleEtag)
        .contentType("application/merge-patch+json")
        .accept("application/hal+json")
        .content("{\"name\":\"Stale client edit\"}"))
    .andExpect(status().isPreconditionFailed());
~~~

Test này kiểm tra precondition HTTP. Dùng database thật hoặc database test tương thích để xác nhận `@Version` được persistence provider xử lý đúng. Không chỉ assert status; hãy xác nhận giá trị mới nhất trong database vẫn còn nguyên sau request bị từ chối.

### 7.2. Kiểm thử method và association

Bổ sung các trường hợp sau nếu API dùng chúng:

- PUT/PATCH/DELETE trên collection URI trả `405`.
- Nếu method repository được đánh dấu `@RestResource(exported = false)`, endpoint tương ứng không được export.
- PUT association với `text/uri-list` gắn đúng resource.
- POST collection association thêm một liên kết.
- DELETE association bỏ liên kết nhưng không xóa entity đích.
- DELETE item xóa entity theo repository và kiểm tra hành vi với foreign key/cascade.
- Payload sai hoặc media type không hỗ trợ trả lỗi phù hợp.

MockMvc chạy đầy đủ luồng Spring MVC qua request/response mock, nhưng không khởi chạy HTTP server thật. Nếu cần kiểm tra proxy, container, serialization hoặc cấu hình mạng thực tế, thêm test end-to-end bằng server đang chạy.

Chạy test theo build của dự án, ví dụ `./mvnw test` hoặc `mvn test`.

## 8. Troubleshooting

**PUT làm mất giá trị mà client không gửi**

- PUT mang nghĩa thay thế trạng thái item. Client cần gửi đầy đủ writable state theo contract.
- Kiểm tra Jackson mapping, constructor, setter, thuộc tính read-only và cách Spring Data REST áp dụng PUT cho entity hiện có.
- Viết test cho trường bị bỏ khỏi body, trường null và object lồng nhau; không suy ra hành vi từ một entity khác.

**PATCH thay đổi nhiều trường hơn dự kiến**

- Kiểm tra `Content-Type`; patch document phải được diễn giải theo đúng format.
- Với JSON Merge Patch, null có nghĩa xóa member và array được thay thế toàn bộ.
- Kiểm tra nested object, association và custom deserializer.
- Nếu client muốn cập nhật một phần tử trong array theo index hoặc thực hiện chuỗi thao tác add/remove/test, cần patch format hỗ trợ các thao tác đó và kiểm tra phiên bản Spring Data REST đang dùng.

**PATCH trả 415**

- Kiểm tra media type server hỗ trợ và giá trị `Content-Type`.
- Không dùng `Accept` thay cho `Content-Type`; `Accept` chỉ mô tả response client muốn nhận.
- Xác nhận request tới đúng item URI và endpoint Spring Data REST.

**PUT/PATCH/DELETE trả 405**

- Xác nhận đang gọi item URI, không phải collection URI.
- Kiểm tra repository có `save(...)` hoặc `delete(...)` tương ứng.
- Kiểm tra `@RestResource(exported = false)`, `@RepositoryRestResource` và cấu hình supported HTTP methods.

**DELETE item không xóa entity liên quan**

- Xác định request gọi item URI hay association URI.
- DELETE association chỉ unbind liên kết.
- Kiểm tra JPA cascade/orphan removal và foreign key constraint nếu kỳ vọng xóa entity liên quan.
- Không bật cascade remove chỉ để làm cho response của một test đơn lẻ khớp mong đợi; xác định lifecycle nghiệp vụ trước.

**Update thành công nhưng không có response body**

- Kiểm tra header `Accept`.
- Kiểm tra `RepositoryRestConfiguration.setReturnBodyOnUpdate(...)` và `setReturnBodyOnDelete(...)`.
- `204 No Content` là response thành công không có body; client không nên cố parse JSON khi status này được trả về.

**Nhận 409 hoặc 412 khi cập nhật**

- 409 thường liên quan constraint database hoặc optimistic locking ở repository.
- 412 thường do ETag hiện tại không khớp `If-Match`.
- GET lại tài nguyên, lấy ETag mới, so sánh thay đổi và chỉ gửi lại sau khi giải quyết conflict.

**Client tự retry tạo nhiều bản ghi**

- POST collection không mặc nhiên idempotent.
- Sau timeout, kiểm tra kết quả bằng business key hoặc cơ chế idempotency key của ứng dụng trước khi gửi lại.
- Với PUT/DELETE, HTTP định nghĩa idempotent về hiệu ứng dự kiến, nhưng response của lần lặp lại có thể khác.
- Không tự động retry PATCH nếu chưa biết patch document có idempotent và có điều kiện phiên bản hay không.

**Lỗi constraint xuất hiện thành 500 hoặc response không ổn định**

- Kiểm tra database constraint có thật trong schema đang chạy.
- Đọc exception class/cause chain và exception handler tùy chỉnh.
- Kiểm tra transaction đã flush tại thời điểm nào; lỗi constraint có thể chỉ xuất hiện khi flush/commit.
- Không trả SQL hoặc stack trace cho client.

## 9. Lưu ý bảo mật cho PUT/PATCH

Spring Data REST xuất CRUD trực tiếp trên domain model, vì vậy method được export phải đi cùng authorization và giới hạn writable properties. Kiểm tra quyền ở cả item resource và association resource. Không coi việc ẩn một nút ở giao diện là kiểm soát truy cập.

Các trường như ID, version, owner, role, trạng thái phê duyệt và audit metadata không nên được client tùy ý ghi. Dùng mapping/authorization phù hợp, kiểm thử request cố tình gửi các trường nhạy cảm và kiểm tra phiên bản Spring Data REST đã vá.

Các security advisory của Spring trong năm 2026 đặc biệt liên quan đến JSON Patch và version:

- CVE-2026-41728 và CVE-2026-41729 liên quan xử lý JSON Patch `application/json-patch+json`, gồm bypass giới hạn read-only trên path lồng nhau và SpEL injection qua Map key. Các bản sửa OSS được công bố gồm Spring Data REST 5.0.6, 4.5.12, 4.4.15, 4.3.17 và 3.7.20.
- CVE-2026-47849 liên quan khả năng sửa `@Id`/`@Version` bằng JSON Patch; CVE-2026-47850 liên quan version của immutable aggregate qua PUT. Các bản sửa tương ứng được công bố gồm 5.1.1, 5.0.7, 4.5.13, 4.4.16 và 3.7.21.

Đối chiếu advisory với nhánh Spring Data REST thực tế trong dependency tree và nâng cấp lên bản đã vá tương ứng. Nếu không cần JSON Patch, không bật hoặc chấp nhận format này một cách tùy tiện. Với bất kỳ format PATCH nào, kiểm thử rằng client không thể sửa ID, version hoặc thuộc tính chỉ dành cho server. Với aggregate immutable, kiểm thử PUT và optimistic locking riêng.

## 10. Checklist hoàn thành bài thực hành

- [ ] GET collection và item trả representation HAL có link đúng.
- [ ] POST collection tạo đúng một entity, trả `201 Created` và `Location`.
- [ ] PUT item thay thế trạng thái theo payload đầy đủ.
- [ ] PATCH item chỉ áp dụng thay đổi theo media type; trường không được patch vẫn đúng.
- [ ] PATCH Merge Patch xử lý null, nested object và array theo quy tắc đã chọn.
- [ ] DELETE item xóa đúng entity và không nhầm với DELETE association.
- [ ] Association PUT/POST/DELETE dùng `text/uri-list` và có semantics đúng.
- [ ] Kiểm tra status/body khi có và không có `Accept`.
- [ ] Kiểm tra `If-Match` và ETag cũ trả `412`.
- [ ] Kiểm tra method bị ẩn trả `405` và payload sai được xử lý phù hợp.
- [ ] Kiểm tra authorization và các trường ID/version/owner/role không bị client sửa.
- [ ] Kiểm tra dependency Spring Data REST đã vá các advisory áp dụng cho nhánh đang dùng.

## 11. Tài liệu chính thức

- [Spring Data REST — Repository resources](https://docs.spring.io/spring-data/rest/reference/repository-resources.html): collection, item, association resources; HTTP methods, media types và status codes mặc định.
- [Spring Data REST — Conditional Operations with Headers](https://docs.spring.io/spring-data/rest/reference/etags-and-other-conditionals.html): `@Version`, ETag, `If-Match`, `If-None-Match`, 412 và 304.
- [Spring Data REST — Getting Started](https://spring.io/guides/gs/accessing-data-rest): ví dụ tạo entity bằng POST, header `Location` và representation HAL.
- [Spring Data REST API — DomainObjectReader](https://docs.spring.io/spring-data/rest/docs/current/api/org/springframework/data/rest/webmvc/json/DomainObjectReader.html): cách framework áp dụng JSON document lên domain object và API xử lý PUT.
- [RFC 9110 — HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110.html): semantics PUT, POST, DELETE và tính idempotent của method.
- [RFC 5789 — PATCH Method for HTTP](https://www.rfc-editor.org/rfc/rfc5789.html): patch document, media type, atomicity và điều kiện cập nhật đồng thời.
- [RFC 7396 — JSON Merge Patch](https://www.rfc-editor.org/rfc/rfc7396.html): semantics của thuộc tính bị bỏ qua, null, object lồng nhau và array.
- [Spring Advisory CVE-2026-41728](https://spring.io/security/cve-2026-41728/): JSON Patch bypass read-only property protection.
- [Spring Advisory CVE-2026-41729](https://spring.io/security/cve-2026-41729/): JSON Patch SpEL injection qua Map key.
- [Spring Advisory CVE-2026-47849](https://spring.io/security/cve-2026-47849/): JSON Patch sửa ID và version.
- [Spring Advisory CVE-2026-47850](https://spring.io/security/cve-2026-47850/): PUT với immutable aggregate và version.

Đối chiếu tài liệu với phiên bản Spring Data REST được Spring Boot BOM quản lý trong dự án. Khi kết quả phụ thuộc `Accept`, media type, entity mapping hoặc exception handler, hãy giữ một integration test thể hiện contract mà client thực sự sử dụng.
