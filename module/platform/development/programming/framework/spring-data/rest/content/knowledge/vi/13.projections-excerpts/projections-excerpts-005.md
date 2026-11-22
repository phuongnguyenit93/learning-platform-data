# Projection lồng nhau và thay đổi cách hiển thị quan hệ trong Spring Data REST

## 1. Projection lồng nhau giải quyết vấn đề gì?

Spring Data REST xuất tài nguyên từ repository theo dạng HAL. Một entity có thuộc tính quan hệ có thể được biểu diễn khác nhau tùy việc entity liên quan có repository riêng hay không:

- Nếu `Person` có thuộc tính `address` và `Address` có repository riêng, tài nguyên Person mặc định thường cung cấp liên kết `_links.address` để client điều hướng đến `/people/{id}/address`.
- Nếu `Address` không có repository riêng, các trường của Address có thể được nhúng trực tiếp trong representation của Person.
- Projection cho phép chọn tập thuộc tính trả về và thay đổi cách quan hệ xuất hiện trong representation. Một projection có getter cho quan hệ có thể đưa dữ liệu quan hệ vào inline; client vẫn có thể nhận liên kết quan hệ để điều hướng.

Projection là lớp trình bày dữ liệu cho REST response. Nó không thay đổi mapping quan hệ JPA, không tạo thêm repository hay endpoint, và không tự thay đổi dữ liệu đã lưu. Dùng projection khi mỗi client hoặc màn hình cần một góc nhìn khác nhau trên cùng aggregate.

Ví dụ domain model:

```java
@Entity
public class Person {
    @Id
    @GeneratedValue
    private Long id;

    private String firstName;
    private String lastName;

    @OneToOne
    private Address address;

    // getters/setters
}

@Entity
public class Address {
    @Id
    @GeneratedValue
    private Long id;

    private String street;
    private String city;
    private String country;

    // getters/setters
}
```

Repository được Spring Data REST export:

```java
public interface PersonRepository extends CrudRepository<Person, Long> {
}

public interface AddressRepository extends CrudRepository<Address, Long> {
}
```

Khi có repository cho Address, response mặc định của `GET /people/1` có thể chứa dữ liệu Person và link đến Address:

```json
{
  "firstName": "Frodo",
  "lastName": "Baggins",
  "_links": {
    "self": { "href": "http://localhost:8080/people/1" },
    "address": { "href": "http://localhost:8080/people/1/address" }
  }
}
```

Client cần thêm một GET đến link `address` nếu muốn hiển thị địa chỉ. Nếu nhiều màn hình luôn cần thành phố và quốc gia, projection lồng nhau có thể đưa đúng các trường đó vào response Person.

## 2. Định nghĩa projection cho quan hệ lồng nhau

Spring Data REST sử dụng interface được đánh dấu `@Projection`. Các getter xác định thuộc tính được xuất. Với quan hệ lồng nhau, kiểu trả về của getter có thể là một projection interface khác. Spring Data Commons hỗ trợ projection đệ quy: thuộc tính quan hệ được lấy từ đối tượng đích rồi bọc trong projection proxy tương ứng.

Ví dụ sau chỉ đưa `city` và `country` của Address vào Person, bỏ `street`:

```java
import org.springframework.data.rest.core.config.Projection;

@Projection(name = "addressSummary", types = Address.class)
public interface AddressSummary {
    String getCity();
    String getCountry();
}

@Projection(name = "personWithAddress", types = Person.class)
public interface PersonWithAddress {
    String getFirstName();
    String getLastName();

    AddressSummary getAddress();
}
```

Đặt các projection interface trong cùng package với domain type tương ứng hoặc một sub-package để Spring Data REST tự phát hiện. Trong ví dụ trên, `AddressSummary` cần nằm trong package được quét cho Address và `PersonWithAddress` trong package được quét cho Person. Nếu bố trí package khác, có thể đăng ký projection thủ công bằng `RepositoryRestConfiguration.getProjectionConfiguration().addProjection(...)`. Projection interface phải có `@Projection`.

Tên dùng trong URL là giá trị `name` của annotation, không phải tên Java interface. Ví dụ:

```http
GET /people/1?projection=personWithAddress
```

Representation có thể có dạng:

```json
{
  "firstName": "Frodo",
  "lastName": "Baggins",
  "address": {
    "city": "Hobbiton",
    "country": "The Shire"
  },
  "_links": {
    "self": { "href": "http://localhost:8080/people/1{?projection}" },
    "address": { "href": "http://localhost:8080/people/1/address" }
  }
}
```

Các điểm cần nhớ:

- `AddressSummary getAddress()` chọn projection cho đối tượng Address ở cấp lồng nhau; không cần tạo endpoint mới.
- Các getter không khai báo trong projection sẽ không được xuất trong phần dữ liệu của projection đó.
- Link `_links.address` vẫn hữu ích để client điều hướng tới tài nguyên Address độc lập. Dữ liệu inline và link có thể cùng tồn tại.
- Nếu quan hệ là collection, có thể khai báo getter trả về collection các projection phù hợp với phần tử quan hệ, rồi kiểm tra representation thực tế bằng integration test.
- Tên projection là hợp đồng API. Đổi tên có thể làm client đang gọi `?projection=...` bị lỗi.

## 3. Chọn projection cho từng request

Khi có nhiều representation, có thể khai báo nhiều projection cho cùng một domain type:

```java
@Projection(name = "personNames", types = Person.class)
public interface PersonNames {
    String getFirstName();
    String getLastName();
}

@Projection(name = "personWithAddress", types = Person.class)
public interface PersonWithAddress {
    String getFirstName();
    String getLastName();
    AddressSummary getAddress();
}
```

Client chọn representation mong muốn bằng query parameter:

```bash
# Chỉ lấy tên
curl -i "http://localhost:8080/people/1?projection=personNames"

# Lấy tên cùng phần địa chỉ được chọn lọc
curl -i "http://localhost:8080/people/1?projection=personWithAddress"
```

Giá trị query parameter phải khớp chính xác với `@Projection(name = "...")`. Nếu không truyền `projection`, Spring Data REST dùng representation mặc định, trừ khi resource collection có excerpt projection được cấu hình.

Projection có thể được tìm trong ALPS metadata. Theo link `profile` ở root resource, xem tài liệu ALPS của resource, ví dụ `/alps/people`. Descriptor của transition GET liệt kê tên projection và các thuộc tính mà projection xuất ra. Đây là cách hữu ích để client khám phá representation được hỗ trợ mà không phải đoán tên.

## 4. Dùng excerptProjection để thay đổi mặc định của collection

Excerpt là projection tự động áp dụng khi item resource được nhúng vào collection hoặc related resource. Có thể đặt excerpt mặc định trên repository:

```java
import org.springframework.data.rest.core.annotation.RepositoryRestResource;

@RepositoryRestResource(excerptProjection = PersonWithAddress.class)
public interface PersonRepository extends CrudRepository<Person, Long> {
}
```

Với cấu hình này, các phần tử Person trong response collection như `GET /people` có thể mang phần Address inline theo projection đã chọn. Link đến Address vẫn có thể được giữ lại trong `_links`.

Cần phân biệt hai cách áp dụng:

| Cách | Phạm vi |
| --- | --- |
| `?projection=personWithAddress` | Chọn projection tường minh cho request resource, chẳng hạn GET một item. |
| `excerptProjection = PersonWithAddress.class` | Chọn excerpt mặc định khi Person được nhúng trong collection hoặc related resource. |

Excerpt projection **không tự động áp dụng cho GET một item resource**. Vì vậy, nếu `GET /people` hiển thị Address inline nhưng `GET /people/1` chỉ có link Address, đó là hành vi dự kiến. Muốn áp dụng projection trên item, gửi `GET /people/1?projection=personWithAddress`.

Thêm excerpt projection vào repository có thể thay đổi response mặc định mà client hiện hữu đang sử dụng. Trước khi triển khai, kiểm tra các client phụ thuộc vào cấu trúc JSON cũ và coi thay đổi này là thay đổi hợp đồng API.

## 5. Tùy biến dữ liệu quan hệ và dữ liệu tính toán

Projection interface chỉ khai báo getter cho các trường cần xuất. Có thể kết hợp getter thông thường với getter quan hệ lồng nhau:

```java
@Projection(name = "personCard", types = Person.class)
public interface PersonCard {
    String getFirstName();
    String getLastName();
    AddressSummary getAddress();
}
```

Nếu cần trường ảo được tính từ nhiều thuộc tính, Spring Data hỗ trợ `@Value` với SpEL:

```java
@Projection(name = "personLabel", types = Person.class)
public interface PersonLabel {
    @Value("#{target.firstName + ' ' + target.lastName}")
    String getDisplayName();
}
```

Projection dùng `@Value` là open projection vì expression có thể truy cập các thuộc tính của target. Spring Data không thể tối ưu truy vấn dựa trên một tập thuộc tính cố định như với closed projection. Với phép tính đơn giản chỉ dựa trên các getter khác của projection, có thể dùng default method:

```java
@Projection(name = "personLabel", types = Person.class)
public interface PersonLabel {
    String getFirstName();
    String getLastName();

    default String getDisplayName() {
        return getFirstName() + " " + getLastName();
    }
}
```

Đối với trường hợp chỉ cần chọn một số thuộc tính có sẵn, ưu tiên closed projection với getter khớp property của aggregate. DTO/class-based projection của Spring Data Commons không hỗ trợ nested projection; khi cần định hình sâu quan hệ bằng proxy, dùng interface-based projection.

## 6. Những giới hạn và lưu ý khi thay đổi cách hiển thị quan hệ

**Projection không đồng nghĩa với fetch plan.** Việc một getter quan hệ xuất hiện trong projection có thể khiến ứng dụng truy cập association khi serialize. Với JPA, hãy xem xét lazy loading, số lượng SQL và nguy cơ N+1 khi trả về collection lớn. Closed projection có thể giúp Spring Data tối ưu một số truy vấn tùy store module; không giả định mọi association đều được fetch trong một câu SQL. Đo query count và kiểm tra kế hoạch tải dữ liệu với store đang dùng.

**Không dùng projection làm cơ chế bảo mật duy nhất.** Spring Data REST cảnh báo projection có thể đưa cả thuộc tính bị `@JsonIgnore` ra response nếu projection khai báo getter tương ứng. Vì vậy, rà soát mọi projection được export, đặc biệt các trường như password, token, secret, thông tin cá nhân hoặc thuộc tính nội bộ. Quyền truy cập phải được bảo vệ bằng thiết kế domain, serialization và authorization phù hợp; không cho rằng `@JsonIgnore` luôn che được dữ liệu khỏi mọi projection.

**Giữ link khi client cần điều hướng.** Đưa dữ liệu quan hệ inline không có nghĩa phải bỏ liên kết HAL. Link cho phép client truy cập tài nguyên liên quan độc lập, trong khi phần inline giúp giảm số request cho dữ liệu thường dùng.

**Kiểm tra null và cardinality.** Quan hệ có thể null hoặc là collection rỗng. Test cả trường hợp có quan hệ, không có quan hệ, và nhiều phần tử. Đừng giả định mọi entity đều có Address.

**Không nhầm projection với thay đổi mapping.** Nếu cần đổi cardinality, cascade, owning side, foreign key hoặc cách lưu quan hệ, phải sửa domain mapping và migration phù hợp. Projection chỉ điều khiển representation REST.

## 7. Quy trình xử lý khi nested projection không hoạt động

1. **Kiểm tra URL và tên projection.** Gọi đúng resource và dùng giá trị `name` trong `@Projection`, ví dụ `?projection=personWithAddress`; tên interface Java không quyết định query parameter.
2. **Kiểm tra phát hiện projection.** Xác nhận interface có `@Projection`, đúng `types`, nằm trong cùng package với entity hoặc sub-package, hoặc đã được đăng ký thủ công qua `ProjectionConfiguration`.
3. **Kiểm tra getter và kiểu trả về.** Tên getter phải khớp property của domain object. Với nested projection, kiểu trả về phải là interface projection dành cho kiểu quan hệ tương ứng. Kiểm tra chính tả `getAddress()`, kiểu Address và getter con như `getCity()`.
4. **Kiểm tra repository và association.** Xác nhận resource đúng đã export, quan hệ được mapping đúng và association có dữ liệu. Nếu Address có repository riêng, representation mặc định thường là link; nếu không có repository, dữ liệu có thể đã được nhúng mặc định.
5. **Phân biệt item projection và excerpt.** Nếu chỉ cấu hình `excerptProjection`, hãy kiểm tra response collection hoặc related resource. Với item GET, thêm query parameter `projection`.
6. **Đọc HAL response.** Kiểm tra dữ liệu inline ở property quan hệ và link trong `_links`. Không chỉ kiểm tra response body bằng cách tìm một chuỗi bất kỳ; dùng JSON path cụ thể.
7. **Kiểm tra lazy loading và serialization.** Nếu getter quan hệ gây lỗi hoặc query quá nhiều, kiểm tra transaction, fetch strategy, SQL log và dữ liệu null. Không khắc phục N+1 chỉ bằng cách thêm nhiều getter vào projection.
8. **Kiểm tra thay đổi tương thích.** Nếu vừa thêm `excerptProjection`, so sánh response collection trước và sau, đồng thời kiểm tra client tiêu thụ API.

Các triệu chứng thường gặp:

| Triệu chứng | Nguyên nhân cần kiểm tra |
| --- | --- |
| `?projection=...` không nhận tên | Dùng sai giá trị `name`, thiếu `@Projection`, sai package scan hoặc chưa đăng ký thủ công. |
| Address vẫn chỉ là link | Request chưa chọn projection, getter quan hệ không có trong projection, hoặc kiểu trả về không phải nested projection phù hợp. |
| Collection có Address inline nhưng item GET không có | Đang dùng excerpt projection; đây là khác biệt được thiết kế. Chọn projection tường minh trên item. |
| Address không xuất hiện hoặc null | Quan hệ chưa được gán, dữ liệu không có, getter không khớp property hoặc mapping chưa đúng. |
| Response có quá nhiều trường nhạy cảm | Rà soát getter projection; projection có thể làm lộ cả trường được đánh dấu `@JsonIgnore`. |
| Collection lớn chạy nhiều SQL | Kiểm tra lazy loading, N+1 và fetch plan; không mặc định nested projection tối ưu truy vấn. |
| Client bị lỗi sau khi thêm excerpt | Representation mặc định của collection đã thay đổi; kiểm tra tương thích hợp đồng API. |

## 8. Kiểm thử tích hợp bằng MockMvc

Nên kiểm tra cả dữ liệu lồng nhau và link HAL. Ví dụ dưới đây giả định ứng dụng đã cấu hình `PersonWithAddress`, có fixture Person với Address, và endpoint là `/people`:

```java
@SpringBootTest
@AutoConfigureMockMvc
class PersonProjectionIntegrationTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void rendersOnlySelectedNestedAddressFields() throws Exception {
        long personId = /* ID của fixture Person đã lưu */;

        mockMvc.perform(get("/people/{id}", personId)
                .param("projection", "personWithAddress"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.firstName").value("Frodo"))
            .andExpect(jsonPath("$.address.city").value("Hobbiton"))
            .andExpect(jsonPath("$.address.country").value("The Shire"))
            .andExpect(jsonPath("$.address.street").doesNotExist())
            .andExpect(jsonPath("$._links.address.href").exists());
    }
}
```

Test collection excerpt riêng biệt:

```java
@Test
void appliesExcerptProjectionToCollectionEntries() throws Exception {
    mockMvc.perform(get("/people"))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$._embedded.people[0].address.city")
            .value("Hobbiton"));
}
```

Nếu cần xác nhận excerpt không tự áp dụng lên item resource, test GET item không có query parameter và so sánh với GET item có `?projection=personWithAddress`. Chuẩn bị fixture có dữ liệu xác định; không phụ thuộc vào ID cố định của database test.

Checklist kiểm thử trước khi đưa lên môi trường:

- Projection được chọn bằng đúng tên `@Projection(name = ...)`.
- Trường ở entity cha được xuất đúng.
- Nested projection chỉ xuất các trường quan hệ đã khai báo.
- Link quan hệ trong `_links` vẫn tồn tại nếu client cần điều hướng.
- Collection sử dụng excerpt đúng như cấu hình.
- Item GET chỉ dùng excerpt khi có cơ chế áp dụng tường minh; kiểm tra query parameter projection.
- Trường hợp quan hệ null, collection rỗng và nhiều phần tử được kiểm tra.
- Không có dữ liệu nhạy cảm ngoài ý muốn.
- Đo SQL/query count khi serialize nested association để phát hiện N+1.
- Kiểm tra response collection hiện hữu để phát hiện breaking change do excerpt mặc định.

## 9. Tài liệu chính thức

- [Spring Data REST — Projections and Excerpts](https://docs.spring.io/spring-data/rest/reference/projections-excerpts.html): cách khai báo `@Projection`, chọn projection bằng query parameter, discovery, excerpt và inline association.
- [Spring Data Commons — Projections](https://docs.spring.io/spring-data/rest/reference/data-commons/repositories/projections.html): interface-based, recursive/nested, closed/open và DTO projections.
- [Spring Data REST API — @Projection](https://docs.spring.io/spring-data/rest/docs/current/api/org/springframework/data/rest/core/config/Projection.html): annotation, tên projection và kiểu domain được gắn.
- [Spring Data REST API — @RepositoryRestResource](https://docs.spring.io/spring-data/rest/reference/api/java/org/springframework/data/rest/core/annotation/RepositoryRestResource.html): thuộc tính `excerptProjection` của repository resource.
- [Spring Data REST — Metadata and ALPS](https://docs.spring.io/spring-data/rest/reference/metadata.html): khám phá projection và descriptor qua profile/ALPS.
