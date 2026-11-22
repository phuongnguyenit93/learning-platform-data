# ObjectMapper của Spring Data REST và cơ chế ánh xạ entity–liên kết

## 1. Mục tiêu

Spring Data REST dùng Jackson để đọc và ghi JSON, đồng thời bổ sung cơ chế hypermedia để biểu diễn entity và association dưới dạng tài nguyên REST. Hai phần này liên quan chặt chẽ nhưng có trách nhiệm khác nhau:

- **Jackson ObjectMapper** chuyển đổi giữa JSON và object Java: đọc thuộc tính, chuyển kiểu dữ liệu, định dạng ngày giờ, áp dụng serializer/deserializer và các Jackson annotation.
- **Spring Data REST** dùng metadata của repository và persistent entity để tạo resource, collection, association và các HAL link. Association trong response có thể được biểu diễn bằng rel và href thay vì lồng toàn bộ object Java.

Vì vậy, JSON representation của một entity được quyết định bởi cả mapping của Jackson và quy tắc resource/hypermedia của Spring Data REST. Khi tùy chỉnh, cần xác định muốn thay đổi cách một giá trị được serialize hay muốn thay đổi cách API công bố một quan hệ.

## 2. ObjectMapper làm gì?

Jackson ObjectMapper là thành phần trung tâm để serialize object thành JSON và deserialize JSON thành object. Trong một ứng dụng Spring, ObjectMapper thường được cấu hình với các module hỗ trợ kiểu dữ liệu, naming strategy và các quy tắc định dạng.

Ví dụ entity:

    @Entity
    public class Customer {

        @Id
        @GeneratedValue
        private Long id;

        private String fullName;

        private LocalDate registeredOn;

        private BigDecimal creditLimit;

        // getters and setters
    }

Khi một Customer được trả về dưới dạng JSON, Jackson chuyển các giá trị Java thành JSON tương ứng. Một representation minh họa:

    {
      "fullName": "An Nguyen",
      "registeredOn": "2026-11-11",
      "creditLimit": 2500000
    }

Đây chỉ là JSON phần dữ liệu của entity. Spring Data REST có thể bọc dữ liệu đó trong resource representation và bổ sung HAL links như _links.self, link tới profile hoặc link tới association.

ObjectMapper cũng xử lý JSON request body khi client gửi POST, PUT hoặc PATCH. Việc JSON có thể chuyển thành object Java không tự quyết định một repository method có được export, association có được công bố hay caller có quyền truy cập hay không.

## 3. HAL và cơ chế ánh xạ entity thành liên kết

Giả sử Customer có association tới Address:

    @Entity
    public class Customer {

        @Id
        @GeneratedValue
        private Long id;

        private String fullName;

        @ManyToOne
        private Address address;
    }

    @Entity
    public class Address {

        @Id
        @GeneratedValue
        private Long id;

        private String street;
        private String city;
    }

Khi Spring Data REST export association, response Customer có thể có dạng:

    {
      "fullName": "An Nguyen",
      "_links": {
        "self": {
          "href": "http://localhost:8080/customers/42"
        },
        "address": {
          "href": "http://localhost:8080/customers/42/address"
        }
      }
    }

Thay vì serialize toàn bộ Address lồng vào Customer, API công bố một link có relation address. Client theo href của link đó để đọc association resource.

Với HAL, hai cấu trúc quan trọng là:

- _links: các quan hệ hypermedia và URI tương ứng.
- _embedded: các resource được nhúng trong representation, thường dùng trong collection response.

Ví dụ collection:

    {
      "_links": {
        "self": {
          "href": "http://localhost:8080/customers"
        }
      },
      "_embedded": {
        "customers": [
          {
            "fullName": "An Nguyen",
            "_links": {
              "self": {
                "href": "http://localhost:8080/customers/42"
              },
              "address": {
                "href": "http://localhost:8080/customers/42/address"
              }
            }
          }
        ]
      }
    }

Tên relation và path thực tế phụ thuộc cấu hình repository và association. Client nên đọc rel/href do server trả về thay vì suy ra URL từ tên class hoặc ID.

## 4. Spring Data REST bổ sung mapping cho persistent entity

Spring Data REST đăng ký các thành phần Jackson và resource assembly để hiểu metadata của persistent entity. Trong các phiên bản hiện hành, module Jackson chuyên biệt thường được biết đến với tên `PersistentEntityJackson2Module`.

Module và resource infrastructure này phối hợp với metadata như:

- Entity type và persistent properties.
- Association giữa các persistent entity.
- Repository nào được export.
- Collection resource rel và item resource rel.
- Association path và rel được công bố trong HAL.

Nhờ đó, Spring Data REST có thể tạo representation có link cho association và resolve các tài nguyên theo repository metadata.

Không nên tự thay thế ObjectMapper mặc định của Spring Data REST bằng một ObjectMapper mới được tạo độc lập. Làm vậy có thể làm mất các module, mixin, serializer hoặc cấu hình mà framework đã đăng ký để tạo HAL và xử lý persistent entity.

Nếu cần tùy chỉnh JSON, hãy dùng extension point của Spring Data REST để bổ sung cấu hình lên ObjectMapper mà framework đang sử dụng.

## 5. Tùy chỉnh ObjectMapper bằng RepositoryRestConfigurer

Có thể triển khai RepositoryRestConfigurer và override callback configureJacksonObjectMapper:

    import com.fasterxml.jackson.annotation.JsonInclude;
    import com.fasterxml.jackson.databind.ObjectMapper;
    import org.springframework.context.annotation.Configuration;
    import org.springframework.data.rest.webmvc.config.RepositoryRestConfigurer;

    @Configuration
    public class RepositoryRestConfig
            implements RepositoryRestConfigurer {

        @Override
        public void configureJacksonObjectMapper(
                ObjectMapper objectMapper) {

            objectMapper.setSerializationInclusion(
                JsonInclude.Include.NON_NULL
            );
        }
    }

Ví dụ trên yêu cầu Jackson bỏ qua các thuộc tính có giá trị null khi serialize. Hãy kiểm tra output thực tế vì thay đổi inclusion policy có thể ảnh hưởng tới contract JSON của nhiều resource.

Có thể cấu hình thêm naming strategy, date format hoặc serializer cho kiểu dữ liệu cụ thể. Chỉ nên thay đổi những quy tắc mà API thật sự cần; một thay đổi global có thể ảnh hưởng mọi repository resource được phục vụ bởi ObjectMapper này.

Chữ ký callback và API cấu hình cần đối chiếu với phiên bản Spring Data REST mà project đang dùng. Không copy cấu hình từ một phiên bản khác nếu dependency hiện tại không cung cấp cùng extension point.

## 6. Dùng Jackson annotation cho thuộc tính

Jackson annotation có thể điều khiển cách một thuộc tính xuất hiện trong JSON.

Ví dụ đổi tên thuộc tính:

    public class Customer {

        @JsonProperty("displayName")
        private String fullName;
    }

JSON có thể dùng key displayName thay cho tên Java fullName.

Có thể định dạng ngày:

    public class Customer {

        @JsonFormat(
            shape = JsonFormat.Shape.STRING,
            pattern = "yyyy-MM-dd"
        )
        private LocalDate registeredOn;
    }

Có thể đánh dấu một thuộc tính không được serialize/deserialize theo cách Jackson thông thường:

    @JsonIgnore
    private String internalNote;

Các annotation này tác động tới mapping JSON. Chúng không thay thế cấu hình export repository hoặc association. Đặc biệt, khi annotation đặt trên association property, hãy kiểm tra HAL output thực tế để xác nhận link mong muốn vẫn được công bố theo cấu hình của ứng dụng.

Không nên dùng @JsonIgnore như cơ chế authorization. Ẩn một thuộc tính khỏi JSON không bảo vệ endpoint hoặc dữ liệu ở các API khác.

## 7. Thêm serializer cho kiểu dữ liệu riêng

Khi cần định dạng một value object, có thể đăng ký serializer qua Jackson module. Ví dụ kiểu Money:

    public class Money {

        private final BigDecimal amount;
        private final String currency;

        public Money(BigDecimal amount, String currency) {
            this.amount = amount;
            this.currency = currency;
        }

        public BigDecimal getAmount() {
            return amount;
        }

        public String getCurrency() {
            return currency;
        }
    }

Serializer:

    public class MoneySerializer
            extends JsonSerializer<Money> {

        @Override
        public void serialize(
                Money value,
                JsonGenerator generator,
                SerializerProvider serializers)
                throws IOException {

            generator.writeStartObject();
            generator.writeNumberField(
                "amount",
                value.getAmount()
            );
            generator.writeStringField(
                "currency",
                value.getCurrency()
            );
            generator.writeEndObject();
        }
    }

Đăng ký module trong callback:

    @Override
    public void configureJacksonObjectMapper(
            ObjectMapper objectMapper) {

        SimpleModule module = new SimpleModule();
        module.addSerializer(
            Money.class,
            new MoneySerializer()
        );

        objectMapper.registerModule(module);
    }

Cần các import Jackson tương ứng cho JsonSerializer, JsonGenerator, SerializerProvider, SimpleModule và IOException.

Ví dụ này chỉ thay đổi cách kiểu Money được chuyển thành JSON. Nó không thay đổi cách Spring Data REST tạo link cho Customer hoặc Address.

Khi thêm serializer/deserializer, nên giới hạn vào value type hoặc một kiểu cụ thể. Việc đăng ký serializer tùy chỉnh cho toàn bộ aggregate root như Customer có thể bỏ qua đường xử lý persistent entity và làm HAL links không được tạo như mong đợi.

## 8. Phân biệt mapping JSON với mapping association

Hai việc sau thường bị nhầm lẫn:

**Mapping một thuộc tính JSON**

Ví dụ fullName được đổi tên thành displayName, hoặc LocalDate được serialize theo mẫu yyyy-MM-dd. Đây là trách nhiệm của Jackson annotation, serializer hoặc deserializer.

**Mapping association thành link**

Ví dụ thuộc tính Customer.address được export thành HAL relation address với một href. Đây là trách nhiệm của Spring Data REST dựa trên persistent association metadata và cấu hình resource.

Có thể tùy chỉnh association rel/path bằng @RestResource:

    @ManyToOne
    @RestResource(
        path = "billing-address",
        rel = "billingAddress"
    )
    private Address address;

Trong ví dụ, Java property vẫn là address, trong khi HAL relation là billingAddress và association path là billing-address.

Không dùng Jackson @JsonProperty để thay thế @RestResource(rel = ...) khi mục tiêu là đổi tên association link. Hai annotation điều khiển hai phần khác nhau của representation.

## 9. Gửi dữ liệu JSON và cập nhật association

Khi tạo hoặc cập nhật entity, JSON body thường mang các thuộc tính dữ liệu của entity:

    POST /customers
    Content-Type: application/json
    Accept: application/hal+json

    {
      "fullName": "An Nguyen",
      "registeredOn": "2026-11-11"
    }

Jackson đọc JSON và chuyển các trường thành giá trị Java theo mapping đã cấu hình. Spring Data REST tiếp tục xử lý request thông qua repository và các quy tắc persistence.

Association được export thường có endpoint riêng. Một cách phổ biến để gắn tài nguyên đã tồn tại vào association là gửi URI của tài nguyên liên quan tới association link bằng media type text/uri-list.

Ví dụ minh họa gắn Address vào Customer:

    PUT /customers/42/address
    Content-Type: text/uri-list

    http://localhost:8080/addresses/7

Với association tập hợp, việc thêm một liên kết thường dùng POST tới association resource:

    POST /customers/42/orders
    Content-Type: text/uri-list

    http://localhost:8080/orders/1001

Các URL trên chỉ minh họa theo path đã chọn; trong ứng dụng thực tế, hãy dùng href association và item link được server công bố. Cách thao tác cụ thể còn phụ thuộc loại association và cấu hình Spring Data REST.

Không giả định rằng gửi nguyên một JSON object Address lồng vào Customer luôn là cách chuẩn để liên kết hai resource đã tồn tại. Khi làm việc với association resource, hãy theo hypermedia link và dùng request format mà endpoint association hỗ trợ.

## 10. Cấu hình repository và association resource

@RepositoryRestResource tùy chỉnh cách repository được công bố:

    @RepositoryRestResource(
        collectionResourceRel = "customers",
        path = "customers"
    )
    public interface CustomerRepository
            extends JpaRepository<Customer, Long> {
    }

@RestResource tùy chỉnh association hoặc query method:

    @ManyToOne
    @RestResource(
        rel = "billingAddress",
        path = "billing-address"
    )
    private Address address;

Các cấu hình này ảnh hưởng tới relation/path trong resource. Chúng khác với Jackson naming strategy, @JsonProperty hoặc serializer.

Nếu repository hoặc association không được export, link tương ứng có thể không xuất hiện. Kiểm tra exported, repository detection strategy và cấu hình REST trước khi kết luận ObjectMapper đang serialize sai.

## 11. Đọc và kiểm tra JSON/HAL response

Có thể kiểm tra API root hoặc resource bằng curl:

    curl -i \
      -H "Accept: application/hal+json" \
      http://localhost:8080/customers/42

Kiểm tra:

1. Status code và Content-Type.
2. Các thuộc tính JSON có tên và định dạng như mong đợi không.
3. _links.self có trỏ tới resource hiện tại không.
4. Association rel có xuất hiện trong _links không.
5. Href của association có thể được gọi và trả đúng loại resource không.
6. Nếu là collection, _embedded và metadata phân trang có đúng không.

Ví dụ khi cần xem association:

    curl -i \
      -H "Accept: application/hal+json" \
      http://localhost:8080/customers/42/address

Đây là URL minh họa. Nên lấy href từ HAL response để kiểm tra, thay vì tự ghép đường dẫn.

Khi JSON field đúng nhưng link bị thiếu, hãy kiểm tra association export và persistent metadata. Khi link đúng nhưng một giá trị JSON có định dạng sai, kiểm tra ObjectMapper, Jackson module và annotation của kiểu dữ liệu đó.

## 12. Lỗi thường gặp

**Tạo ObjectMapper mới và thay thế mapper của Spring Data REST**

Mapper mới có thể thiếu module hoặc cấu hình mà framework cần để serialize persistent entity và HAL. Hãy dùng callback configureJacksonObjectMapper để bổ sung cấu hình lên mapper hiện có.

**Dùng @JsonProperty để đổi association rel**

@JsonProperty đổi tên JSON property; @RestResource(rel = ...) điều khiển tên relation của association. Chọn annotation theo phần representation muốn thay đổi.

**Custom serializer làm mất HAL links**

Serializer cho aggregate root có thể ghi đè đường xử lý resource của Spring Data REST. Giới hạn serializer ở value type hoặc kiểu cụ thể và kiểm tra _links sau khi cấu hình.

**Nhầm JSON nested object với association resource**

Một entity lồng trong JSON không tự động có nghĩa Spring Data REST sẽ tạo association link hoặc liên kết tới resource đã tồn tại. Với association export, dùng link và request format phù hợp của association endpoint.

**Dùng annotation để bảo vệ dữ liệu**

JsonIgnore hoặc việc không serialize một field không thay thế authentication và authorization. Bảo vệ endpoint và thao tác repository bằng cấu hình security.

**Thay đổi global mà không kiểm tra contract**

Một chính sách null inclusion, naming strategy hoặc date format toàn cục có thể thay đổi JSON của nhiều resource. Kiểm tra các response liên quan sau khi cấu hình.

## 13. Bài tập thực hành

Với Customer có fullName, registeredOn và association Address:

1. Gọi GET Customer resource với Accept: application/hal+json.
2. Xác định các thuộc tính JSON và link association trong _links.
3. Thêm @JsonProperty cho một thuộc tính và quan sát key JSON thay đổi.
4. Thêm @JsonFormat cho LocalDate và quan sát định dạng ngày.
5. Dùng RepositoryRestConfigurer.configureJacksonObjectMapper để áp dụng một chính sách serialization.
6. Tùy chỉnh association bằng @RestResource(rel = ..., path = ...).
7. So sánh tác động của Jackson annotation với association metadata.
8. Gọi association href và xác nhận response là resource liên quan.
9. Nếu đăng ký custom serializer cho một value object, xác nhận HAL links của Customer vẫn có mặt.

Câu hỏi tự kiểm tra:

- ObjectMapper chịu trách nhiệm cho những bước chuyển đổi nào?
- Vì sao Spring Data REST cần metadata của persistent entity để tạo association link?
- @JsonProperty và @RestResource(rel = ...) khác nhau thế nào?
- Vì sao nên bổ sung module vào ObjectMapper hiện có thay vì thay thế mapper mặc định?
- Khi nào nên dùng custom serializer cho value object?
- Vì sao association đã export thường được thao tác qua association resource?

## 14. Ghi nhớ

- Jackson ObjectMapper đọc và ghi JSON, xử lý kiểu dữ liệu, format và custom serializer/deserializer.
- Spring Data REST dùng persistent entity metadata và hypermedia infrastructure để tạo resource và association links.
- HAL thường biểu diễn link trong _links và resource nhúng trong _embedded.
- RepositoryRestConfigurer.configureJacksonObjectMapper là extension point để tùy chỉnh ObjectMapper của Spring Data REST.
- @JsonProperty và @JsonFormat tác động tới JSON property; @RestResource tác động tới association/query resource rel và path.
- Tránh thay thế mapper mặc định hoặc override serializer aggregate root nếu không hiểu tác động tới HAL.
- Dùng association href và request format phù hợp để liên kết resource.
- JSON mapping không thay thế repository export configuration hoặc authorization.

## Tài liệu tham khảo

- Spring Data REST Reference — Configuring Jackson ObjectMapper: https://docs.spring.io/spring-data/rest/reference/
- Spring Data REST Reference — Association resources: https://docs.spring.io/spring-data/rest/reference/
- Spring Data REST API — RepositoryRestConfigurer: https://docs.spring.io/spring-data/rest/reference/api/java/org/springframework/data/rest/webmvc/config/RepositoryRestConfigurer.html
- Jackson Databind documentation: https://github.com/FasterXML/jackson-databind
