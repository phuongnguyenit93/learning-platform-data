# Điều khiển tên thuộc tính bằng @JsonProperty và quy tắc đặt tên

## Mục tiêu

Trong Java, tên thuộc tính thường dùng camelCase, còn JSON API có thể cần snake_case, kebab-case hoặc một tên công khai khác. Jackson cho phép kiểm soát tên trường JSON bằng annotation `@JsonProperty` và quy tắc đặt tên thuộc tính (property naming strategy).

Ví dụ, Java model có property `firstName` nhưng API cần JSON:

    {
      "first_name": "An"
    }

Có hai cách chính:

- Dùng `@JsonProperty("first_name")` khi một property cần tên JSON cụ thể.
- Dùng naming strategy như `SNAKE_CASE` khi muốn chuyển đổi nhất quán nhiều property.

Trong Spring Data REST, Jackson cũng tham gia serialize và deserialize domain object trong representation HTTP. Vì vậy, tên JSON có thể khác tên Java, nhưng URL resource, relation HAL và tên cột database là các khái niệm riêng.

## 1. Phân biệt tên Java, tên JSON và tên database

Một property có thể có nhiều tên ở các lớp khác nhau:

| Lớp | Ví dụ | Được điều khiển bởi |
|---|---|---|
| Java property | firstName | Tên field, getter/setter hoặc record component |
| JSON property | first_name | Jackson annotation hoặc naming strategy |
| Database column | first_name | JPA mapping như @Column |
| REST resource path | /people/1001 | Spring Data REST repository mapping |
| HAL relation | people | Spring Data REST relation configuration |

Đổi tên JSON bằng `@JsonProperty` không tự động đổi tên field Java, tên cột database, collection URL hoặc HAL relation.

Ví dụ:

    @Entity
    public class Person {

        @Id
        private Long id;

        @Column(name = "first_name")
        @JsonProperty("first_name")
        private String firstName;
    }

Ở đây:

- Java dùng `firstName`.
- JSON dùng `first_name`.
- Database column cũng là `first_name` vì có `@Column`.
- Hai annotation có nhiệm vụ riêng; nếu bỏ `@Column`, Jackson vẫn có thể xuất JSON key `first_name`, nhưng tên cột database không nhất thiết đổi theo.

## 2. Đổi tên một property bằng @JsonProperty

`@JsonProperty` thuộc Jackson annotations:

    import com.fasterxml.jackson.annotation.JsonProperty;

Có thể đặt annotation trên field, getter, setter hoặc tham số constructor/creator tùy cách Jackson truy cập object.

### 2.1. Đặt annotation trên field

    public class Person {

        @JsonProperty("first_name")
        private String firstName;

        @JsonProperty("last_name")
        private String lastName;
    }

Khi serialize, Jackson dùng các tên được chỉ định:

    {
      "first_name": "An",
      "last_name": "Nguyen"
    }

Khi deserialize, Jackson cũng có thể đọc các key đó để gán giá trị vào property tương ứng, theo access mode và cấu hình của class.

### 2.2. Đặt annotation trên getter

Nếu ứng dụng dùng getter làm điểm truy cập JSON:

    public class Person {

        private String firstName;

        @JsonProperty("first_name")
        public String getFirstName() {
            return firstName;
        }

        public void setFirstName(String firstName) {
            this.firstName = firstName;
        }
    }

Tên công khai của property trong JSON là `first_name`. Jackson có thể ghép getter và setter thành cùng một logical property.

### 2.3. Đặt annotation trên setter

Có thể dùng annotation trên setter để xác định tên input JSON:

    public class Person {

        private String firstName;

        public String getFirstName() {
            return firstName;
        }

        @JsonProperty("first_name")
        public void setFirstName(String firstName) {
            this.firstName = firstName;
        }
    }

Khi annotation được đặt ở nhiều vị trí của cùng một logical property, hãy dùng cùng một tên JSON và tránh tạo các khai báo mâu thuẫn. Jackson có quy tắc hợp nhất metadata từ field, getter, setter và creator; kết quả cụ thể còn phụ thuộc visibility và cấu hình ObjectMapper.

### 2.4. Đặt tên tham số constructor hoặc creator

Với immutable object, có thể khai báo JSON name trên creator parameter:

    public class Person {

        private final String firstName;

        @JsonCreator
        public Person(
                @JsonProperty("first_name") String firstName) {
            this.firstName = firstName;
        }

        public String getFirstName() {
            return firstName;
        }
    }

Cách này giúp Jackson biết JSON key nào được dùng để tạo object. Với Java records và các kiểu immutable khác, cách nhận diện constructor/component còn phụ thuộc phiên bản Jackson và cấu hình module đang dùng.

## 3. Các access mode của @JsonProperty

`@JsonProperty` có thuộc tính `access` để kiểm soát chiều đọc và ghi JSON.

| Access mode | Serialize object thành JSON | Deserialize JSON thành object |
|---|---|---|
| AUTO | Theo quy tắc mặc định của Jackson | Theo quy tắc mặc định của Jackson |
| READ_ONLY | Có thể xuất property | Không nhận giá trị input cho property |
| WRITE_ONLY | Không xuất property | Có thể nhận giá trị input |
| READ_WRITE | Đọc và ghi theo cả hai chiều | Đọc và ghi theo cả hai chiều |

Ví dụ chỉ cho phép nhận mật khẩu khi tạo request, không trả mật khẩu trong response:

    public class RegistrationRequest {

        private String username;

        @JsonProperty(
            value = "password",
            access = JsonProperty.Access.WRITE_ONLY
        )
        private String password;
    }

Ví dụ chỉ xuất một giá trị do server quản lý:

    public class PersonResponse {

        @JsonProperty(
            value = "internal_code",
            access = JsonProperty.Access.READ_ONLY
        )
        private String internalCode;
    }

Không dùng WRITE_ONLY như cơ chế bảo vệ dữ liệu hoàn chỉnh. Vẫn cần kiểm soát authorization, logging, validation và cách lưu trữ dữ liệu nhạy cảm.

## 4. Dùng naming strategy cho toàn bộ model

Nếu nhiều property đều cần chuyển từ camelCase sang snake_case, không cần gắn `@JsonProperty` cho từng field. Dùng `PropertyNamingStrategies` của Jackson:

    import com.fasterxml.jackson.databind.PropertyNamingStrategies;
    import com.fasterxml.jackson.databind.annotation.JsonNaming;

    @JsonNaming(PropertyNamingStrategies.SnakeCaseStrategy.class)
    public class Person {

        private String firstName;
        private String lastName;
        private Instant createdAt;
    }

JSON minh họa:

    {
      "first_name": "An",
      "last_name": "Nguyen",
      "created_at": "2026-11-11T10:00:00Z"
    }

`@JsonNaming` áp dụng naming strategy cho class được đánh dấu. Các class khác không tự động bị đổi tên chỉ vì một class dùng annotation này.

### 4.1. Những naming strategy thường dùng

Jackson cung cấp các strategy phổ biến:

| Strategy | Java property | JSON name minh họa |
|---|---|---|
| LOWER_CAMEL_CASE | firstName | firstName |
| SNAKE_CASE | firstName | first_name |
| KEBAB_CASE | firstName | first-name |
| UPPER_CAMEL_CASE | firstName | FirstName |
| LOWER_CASE | firstName | firstname |
| UPPER_SNAKE_CASE | firstName | FIRST_NAME |

Kết quả thực tế với tên viết tắt, chữ số hoặc acronym có thể phụ thuộc thuật toán của Jackson. Hãy kiểm thử các tên đặc biệt như `URLValue`, `userID` hoặc `address2Line` nếu chúng xuất hiện trong model.

### 4.2. Áp dụng strategy cho từng class

Có thể dùng strategy khác nhau cho từng DTO:

    @JsonNaming(PropertyNamingStrategies.SnakeCaseStrategy.class)
    public class PersonResponse {
        private String firstName;
        private String createdAt;
    }

    @JsonNaming(PropertyNamingStrategies.LowerCamelCaseStrategy.class)
    public class LegacyResponse {
        private String firstName;
        private String createdAt;
    }

Cách này hữu ích khi một API phải duy trì nhiều contract JSON khác nhau. Tuy nhiên, nên giữ naming convention nhất quán trong cùng một representation để client dễ sử dụng.

## 5. Cấu hình naming strategy toàn ứng dụng

Nếu toàn bộ API cần một quy tắc chung, có thể cấu hình ObjectMapper hoặc cấu hình Jackson do Spring Boot quản lý.

### 5.1. Spring Boot application property

Với Spring Boot dùng Jackson 2, có thể đặt trong application.properties:

    spring.jackson.property-naming-strategy=SNAKE_CASE

Hoặc YAML:

    spring:
      jackson:
        property-naming-strategy: SNAKE_CASE

Cấu hình này áp dụng cho ObjectMapper mà Spring Boot cấu hình tự động. Nó có thể ảnh hưởng tới nhiều endpoint và DTO trong ứng dụng, vì vậy cần kiểm tra các API đang dùng tên JSON cũ trước khi bật toàn cục.

Tên class strategy đầy đủ cũng có thể được dùng nếu cấu hình cần tham chiếu trực tiếp implementation mà ứng dụng cung cấp.

### 5.2. Cấu hình ObjectMapper trực tiếp

Nếu ứng dụng tự quản lý ObjectMapper, có thể đặt strategy:

    ObjectMapper mapper = new ObjectMapper();
    mapper.setPropertyNamingStrategy(
        PropertyNamingStrategies.SNAKE_CASE
    );

Cần lưu ý Spring Data REST dùng Jackson converter được cấu hình trong Spring MVC. Tạo một ObjectMapper riêng rồi không đăng ký vào HTTP message converter sẽ không thay đổi JSON response của Spring Data REST.

### 5.3. Tùy chỉnh Jackson builder trong Spring Boot

Có thể tùy chỉnh builder mà Spring Boot dùng để tạo ObjectMapper:

    @Configuration
    public class JacksonConfiguration {

        @Bean
        Jackson2ObjectMapperBuilderCustomizer namingCustomizer() {
            return builder ->
                builder.propertyNamingStrategy(
                    PropertyNamingStrategies.SNAKE_CASE
                );
        }
    }

Cách này phù hợp khi muốn bổ sung cấu hình vào ObjectMapper do Boot quản lý. API builder và tên integration có thể thay đổi giữa các thế hệ Spring Boot/Jackson; dùng kiểu tương ứng với dependency version của dự án.

Không nên khai báo một ObjectMapper bean mới nếu chỉ cần đổi một thuộc tính mà chưa hiểu các auto-configuration khác đang được áp dụng. Một bean tự tạo có thể làm thay đổi module, serializer, deserializer hoặc converter mặc định.

## 6. Ưu tiên giữa @JsonProperty và naming strategy

Naming strategy là quy tắc mặc định để chuyển tên property. `@JsonProperty` cung cấp tên JSON tường minh cho một property.

Ví dụ:

    @JsonNaming(PropertyNamingStrategies.SnakeCaseStrategy.class)
    public class Person {

        private String firstName;

        @JsonProperty("displayName")
        private String publicName;
    }

Representation minh họa:

    {
      "first_name": "An",
      "displayName": "An Nguyen"
    }

Property `firstName` theo naming strategy chung. Property `publicName` dùng tên tường minh `displayName` được khai báo bằng annotation.

Nên dùng:

- Naming strategy khi nhiều property tuân theo một quy tắc thống nhất.
- @JsonProperty khi tên công khai cần giữ nguyên, khác convention hoặc là một phần của contract API.
- @JsonAlias khi muốn nhận thêm tên input cũ trong giai đoạn tương thích mà không đổi tên output.

Ví dụ alias cho input cũ:

    public class Person {

        @JsonProperty("first_name")
        @JsonAlias("firstName")
        private String firstName;
    }

Khi deserialize, API có thể nhận cả `first_name` và alias `firstName`; khi serialize, tên property công khai vẫn là `first_name`. Hãy xác định rõ alias nào cần hỗ trợ và trong bao lâu để tránh duy trì nhiều contract không cần thiết.

## 7. @JsonProperty và Spring Data REST

Spring Data REST dùng Spring MVC message converters và Jackson để tạo representation JSON cho domain object. Vì vậy, naming strategy và property annotation có thể thay đổi tên các field trong body của resource.

Ví dụ repository:

    @RepositoryRestResource(path = "people")
    public interface PersonRepository
            extends JpaRepository<Person, Long> {
    }

Domain type:

    @Entity
    @JsonNaming(PropertyNamingStrategies.SnakeCaseStrategy.class)
    public class Person {

        @Id
        private Long id;

        private String firstName;
        private String lastName;
    }

Request đọc item:

    GET /people/1001
    Accept: application/hal+json

Phần entity được nhúng trong response có thể dùng `first_name` và `last_name`, trong khi URL vẫn là `/people/1001`.

Cần phân biệt các phần của HAL:

- `_links` chứa link hypermedia.
- `_embedded` chứa representation của resource liên quan hoặc collection.
- Các field của entity nằm trong representation do Jackson serialize.
- Tên relation như `people` được Spring Data REST cấu hình riêng.

Các key HAL được framework định nghĩa có contract riêng. Đừng giả định thay naming strategy sẽ đổi tên `_links`, `_embedded`, relation hoặc URL. Hãy kiểm tra response HAL thực tế của phiên bản Spring Data REST đang dùng.

### 7.1. Tác động tới request body ghi dữ liệu

POST, PUT và PATCH gửi JSON body để Jackson deserialize thành object hoặc representation tương ứng. Nếu server chuyển sang snake_case, client cần gửi key đúng contract:

    {
      "first_name": "An",
      "last_name": "Nguyen"
    }

Nếu client vẫn gửi `firstName`, property có thể không được bind theo cấu hình hiện tại, trừ khi API có alias hoặc cấu hình tương thích.

Trước khi đổi naming strategy toàn cục, cần kiểm tra cả response và request body. Một thay đổi chỉ nhìn thấy ở response vẫn có thể làm hỏng client đang POST/PUT/PATCH theo tên cũ.

### 7.2. Projection và DTO

Projection hoặc DTO có thể định nghĩa một representation riêng. Annotation trên DTO/projection và naming strategy của ObjectMapper có thể ảnh hưởng cách field được serialize.

Nếu API dùng projection, excerpt hoặc custom controller, hãy kiểm tra đúng representation mà endpoint trả về. Không suy luận rằng mọi endpoint đều dùng cùng một class hoặc cùng một tập property.

## 8. Những lưu ý khi đổi tên JSON

### 8.1. Không đổi contract mà không kiểm tra client

Tên JSON là một phần của API contract. Đổi `firstName` thành `first_name` có thể làm client cũ không đọc được response hoặc không gửi đúng request.

Nếu cần chuyển đổi convention:

1. Liệt kê endpoint và client đang sử dụng field cũ.
2. Xác định thời gian tương thích cần thiết.
3. Có thể dùng alias để nhận input cũ trong thời gian chuyển tiếp.
4. Cập nhật tài liệu và schema API.
5. Kiểm thử serialize và deserialize trước khi phát hành.

### 8.2. Tránh property name trùng nhau

Hai Java property khác nhau không nên cùng được ánh xạ tới một JSON name. Ví dụ:

    @JsonProperty("name")
    private String firstName;

    @JsonProperty("name")
    private String lastName;

Cấu hình này tạo xung đột logical property và có thể khiến Jackson báo lỗi hoặc xử lý không như mong đợi. Hãy bảo đảm mỗi JSON property có một nguồn dữ liệu rõ ràng.

### 8.3. Field, getter và setter phải nhất quán

Nếu field, getter và setter khai báo tên khác nhau, Jackson có thể hợp nhất chúng theo visibility và annotation introspection. Tránh gắn nhiều annotation mâu thuẫn trên cùng logical property.

Nếu cần tên khác nhau cho input và output, cân nhắc custom serializer/deserializer hoặc DTO riêng thay vì tạo metadata khó hiểu trên entity.

### 8.4. Không dùng @JsonProperty để kiểm soát quyền truy cập

Đổi tên hoặc ẩn một field trong JSON không phải là authorization. Nếu client không được phép đọc hoặc sửa property, hãy dùng DTO, access mode phù hợp, validation và security rule ở tầng ứng dụng.

## 9. Kiểm thử serialize và deserialize

Nên kiểm tra cả hai chiều vì tên property ảnh hưởng response lẫn request.

### 9.1. Unit test với ObjectMapper

Ví dụ:

    ObjectMapper mapper = new ObjectMapper();

    Person person = new Person();
    person.setFirstName("An");

    String json = mapper.writeValueAsString(person);

    assertThat(json).contains(""first_name":"An"");

    Person restored = mapper.readValue(
        "{"first_name":"An"}",
        Person.class
    );

    assertThat(restored.getFirstName()).isEqualTo("An");

Nếu dùng Spring Boot customizer hoặc module, nên inject ObjectMapper thực tế từ application context để test đúng cấu hình runtime.

### 9.2. Integration test Spring Data REST

Dùng MockMvc hoặc test HTTP để xác nhận representation thật:

    mockMvc.perform(get("/people/1001")
            .accept(MediaTypes.HAL_JSON))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$._embedded").doesNotExist());

Với item representation, kiểm tra trực tiếp JSON key của entity theo response shape thực tế. Ví dụ:

    mockMvc.perform(get("/people/1001")
            .accept(MediaTypes.HAL_JSON))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.first_name").value("An"));

Đường dẫn JSONPath phụ thuộc item representation và media type. Hãy dùng response thực tế để chọn JSONPath đúng; ví dụ trên minh họa field ở root.

### 9.3. Bộ trường hợp cần kiểm tra

- Serialize property có @JsonProperty.
- Deserialize cùng JSON name.
- Naming strategy áp dụng cho class hoặc toàn ObjectMapper.
- Explicit @JsonProperty khi có naming strategy.
- @JsonAlias cho tên input cũ nếu có.
- READ_ONLY và WRITE_ONLY.
- Getter/setter hoặc constructor/record binding.
- POST/PUT/PATCH qua Spring Data REST.
- HAL links và embedded entity fields.
- Các client đang dùng JSON contract cũ.

## 10. Checklist lựa chọn cách đặt tên

1. Xác định JSON contract cần dùng camelCase, snake_case hay convention khác.
2. Dùng @JsonProperty cho property có tên công khai đặc biệt.
3. Dùng @JsonNaming khi chỉ một class cần convention riêng.
4. Dùng Spring Boot Jackson configuration khi toàn ứng dụng cần cùng naming strategy.
5. Dùng @JsonAlias để hỗ trợ input cũ trong thời gian chuyển đổi.
6. Dùng access mode hoặc DTO để kiểm soát field được đọc/ghi.
7. Phân biệt JSON property với Java property, database column, REST path và HAL relation.
8. Kiểm thử cả serialize lẫn deserialize.
9. Kiểm thử response HAL và các request POST/PUT/PATCH.
10. Kiểm tra client hiện có trước khi đổi API contract.

## Tài liệu tham khảo

- [Jackson Annotations — JsonProperty](https://javadoc.io/doc/com.fasterxml.jackson.core/jackson-annotations/latest/com/fasterxml/jackson/annotation/JsonProperty.html)
- [Jackson Annotations — JsonAlias](https://javadoc.io/doc/com.fasterxml.jackson.core/jackson-annotations/latest/com/fasterxml/jackson/annotation/JsonAlias.html)
- [Jackson Databind — PropertyNamingStrategies](https://javadoc.io/doc/com.fasterxml.jackson.core/jackson-databind/latest/com/fasterxml/jackson/databind/PropertyNamingStrategies.html)
- [Jackson Databind — JsonNaming](https://javadoc.io/doc/com.fasterxml.jackson.core/jackson-databind/latest/com/fasterxml/jackson/databind/annotation/JsonNaming.html)
- [Spring Boot — Customize the Jackson ObjectMapper](https://docs.spring.io/spring-boot/reference/features/json.html)
- [Spring Data REST — Configuring the REST representation](https://docs.spring.io/spring-data/rest/reference/representations.html)
