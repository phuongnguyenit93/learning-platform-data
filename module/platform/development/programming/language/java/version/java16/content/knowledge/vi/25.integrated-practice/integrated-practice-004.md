# Refactor lớp DTO thành record và kiểm tra hợp đồng API hiện có

## 1. Bối cảnh và mục tiêu thực hành

DTO (Data Transfer Object) mang dữ liệu giữa các tầng ứng dụng hoặc giữa ứng dụng và client API. Một DTO đơn giản thường có field, constructor, getter và setter. Cách viết này quen thuộc nhưng tạo nhiều mã lặp và cho phép trạng thái object thay đổi sau khi tạo.

Java record, được hoàn thiện trong Java 16 qua JEP 395, là một dạng class dành cho dữ liệu. Compiler tự tạo canonical constructor, accessor cho từng component, `equals()`, `hashCode()` và `toString()`. Record phù hợp với DTO có trạng thái được xác định khi khởi tạo và không cần thay đổi sau đó.

Refactor DTO class thành record có thể giảm mã lặp và làm rõ hợp đồng dữ liệu. Tuy nhiên, thay đổi này ảnh hưởng đến cách code Java tạo và đọc object, cách thư viện serialize dữ liệu, cách so sánh object và khả năng tương thích với consumer hiện tại.

Bài thực hành sử dụng DTO khách hàng để đi qua quy trình:

1. Khảo sát DTO class và các nơi đang sử dụng.
2. Ghi lại hợp đồng Java và JSON hiện tại.
3. Thiết kế record component và constructor.
4. Chuyển mapper/controller sang cách tạo record.
5. Kiểm tra tính bất biến và value semantics.
6. Chạy contract test để xác nhận API vẫn giữ hành vi đã công bố.
7. Quyết định cách phát hành nếu thay đổi không tương thích.

Record là một loại class trong Java, không phải annotation hay thư viện ngoài.

## 2. Khảo sát DTO hiện tại trước khi refactor

Giả sử ứng dụng có DTO mutable:

~~~java
import java.util.List;

public class CustomerDto {
    private String id;
    private String displayName;
    private String email;
    private List<String> roles;

    public CustomerDto() {
    }

    public String getId() {
        return id;
    }

    public void setId(String id) {
        this.id = id;
    }

    public String getDisplayName() {
        return displayName;
    }

    public void setDisplayName(String displayName) {
        this.displayName = displayName;
    }

    public String getEmail() {
        return email;
    }

    public void setEmail(String email) {
        this.email = email;
    }

    public List<String> getRoles() {
        return roles;
    }

    public void setRoles(List<String> roles) {
        this.roles = roles;
    }
}
~~~

Một nơi tạo DTO có thể viết:

~~~java
CustomerDto dto = new CustomerDto();
dto.setId(customer.id());
dto.setDisplayName(customer.displayName());
dto.setEmail(customer.email());
dto.setRoles(customer.roles());
~~~

Cách viết này có một số đặc điểm cần ghi nhận:

- Object được tạo trước khi có đủ dữ liệu.
- Consumer có thể gọi setter theo thứ tự bất kỳ.
- Object có thể tồn tại ở trạng thái thiếu field giữa các lần gọi setter.
- `roles` có thể trỏ tới một list mà caller khác tiếp tục thay đổi.
- Nếu class không override `equals()` và `hashCode()`, hai DTO chứa cùng dữ liệu vẫn không được xem là bằng nhau theo giá trị.
- Constructor không thể bảo đảm mọi instance đều thỏa các bất biến dữ liệu.

Trước khi thay đổi, hãy tìm tất cả nơi gọi constructor, getter, setter, reflection, serializer, mapper và test. Một DTO có vẻ chỉ được dùng trong controller vẫn có thể được framework khởi tạo hoặc đọc qua JavaBeans conventions.

### Bảng khảo sát

| Khu vực | Câu hỏi cần trả lời |
| --- | --- |
| Constructor | Consumer có dùng constructor không tham số không? |
| Getter | Consumer gọi `getId()` hay accessor khác? |
| Setter | Có nơi nào cập nhật DTO sau khi tạo không? |
| Reflection | Framework có tìm property theo JavaBeans convention không? |
| JSON | Field name, kiểu dữ liệu, nullability và format hiện tại là gì? |
| Equality | DTO có được dùng làm key trong Map/Set hoặc so sánh trong test không? |
| Collection | Ai sở hữu list/map bên trong DTO? |
| Validation | Quy tắc dữ liệu đang được kiểm tra ở đâu? |

Không nên bắt đầu refactor trước khi có câu trả lời cho các câu hỏi này. Chúng xác định record có phù hợp với vai trò hiện tại của DTO hay không.

## 3. Ghi lại hợp đồng API hiện tại

Giả sử endpoint hiện trả về:

~~~json
{
  "id": "C-100",
  "displayName": "An Nguyen",
  "email": "an@example.test",
  "roles": ["USER", "REPORT_VIEWER"]
}
~~~

Đây là hợp đồng mà client có thể sử dụng. Khi refactor, cần giữ các đặc điểm đã công bố trừ khi có quyết định thay đổi API rõ ràng.

Hãy ghi lại tối thiểu:

- Tên field JSON và kiểu dữ liệu.
- Field nào bắt buộc, field nào có thể null.
- Field nào có thể bị lược bỏ khỏi response.
- Quy tắc định dạng ngày giờ, số, enum và identifier.
- Cấu trúc lồng nhau và các giá trị biên mà client cần xử lý.
- Hành vi khi dữ liệu không hợp lệ.
- HTTP status, content type và header liên quan.
- Các method Java mà consumer bên ngoài gọi trực tiếp nếu DTO là public API của thư viện.

JSON object không có khái niệm constructor Java. Việc thay class bằng record không tự động bảo đảm JSON contract giữ nguyên. Kết quả phụ thuộc serializer, cấu hình naming strategy, annotation và phiên bản framework đang chạy.

### Tạo contract fixture

Lưu một JSON mẫu đại diện cho response hiện tại trong test resources, ví dụ `customer-response.json`. Fixture nên chứa dữ liệu thực tế như list rỗng, field tùy chọn, Unicode và giá trị biên.

Không chỉ kiểm tra một object đơn giản toàn chuỗi không dấu. Các trường hợp biên thường làm lộ khác biệt giữa class và record.

## 4. Thiết kế record component

Record khai báo dữ liệu qua danh sách component:

~~~java
import java.util.List;

public record CustomerDto(
    String id,
    String displayName,
    String email,
    List<String> roles
) {
}
~~~

Compiler cung cấp:

| Thành phần | Kết quả được tạo |
| --- | --- |
| `CustomerDto(String, String, String, List<String>)` | Canonical constructor. |
| `id()` | Accessor cho component `id`. |
| `displayName()` | Accessor cho component `displayName`. |
| `email()` | Accessor cho component `email`. |
| `roles()` | Accessor cho component `roles`. |
| `equals()` | So sánh theo component. |
| `hashCode()` | Tính hash từ component. |
| `toString()` | Biểu diễn record và component. |

Các component tạo thành state description của record. Field tương ứng là `private final` và record class là `final`. Record không thể khai báo thêm instance field độc lập ngoài các component, nhưng vẫn có thể khai báo static field, static method, constructor overload và instance method.

Record có thể implement interface, nhưng không thể kế thừa một class tùy ý. Mọi record đều kế thừa `java.lang.Record`.

Accessor có tên theo component, ví dụ `id()`, chứ không tự tạo JavaBean getter `getId()`. Đây là khác biệt quan trọng khi thay DTO class hiện có.

## 5. Thêm validation vào canonical constructor

Nếu DTO class trước đây cho phép trạng thái thiếu dữ liệu, record nên xác định rõ hợp đồng nào cần được bảo vệ ngay lúc khởi tạo.

Có thể dùng compact canonical constructor:

~~~java
import java.util.List;
import java.util.Objects;

public record CustomerDto(
    String id,
    String displayName,
    String email,
    List<String> roles
) {
    public CustomerDto {
        id = Objects.requireNonNull(id, "id").strip();
        displayName = Objects.requireNonNull(
            displayName, "displayName"
        ).strip();
        email = Objects.requireNonNull(email, "email").strip();
        roles = List.copyOf(
            Objects.requireNonNull(roles, "roles")
        );

        if (id.isBlank()) {
            throw new IllegalArgumentException("id must not be blank");
        }

        if (displayName.isBlank()) {
            throw new IllegalArgumentException(
                "displayName must not be blank"
            );
        }

        if (email.isBlank()) {
            throw new IllegalArgumentException("email must not be blank");
        }
    }
}
~~~

Trong compact constructor, các tham số component có thể được kiểm tra hoặc chuẩn hóa. Sau khi phần thân constructor chạy xong, compiler gán giá trị cuối cùng của các tham số vào component fields.

Ví dụ, `strip()` chuẩn hóa khoảng trắng ở đầu và cuối. `List.copyOf()` tạo list không thể sửa đổi và từ chối list null hoặc phần tử null.

### Chọn validation theo hợp đồng

Không nên tự đặt mọi field thành bắt buộc chỉ vì record có constructor. Hãy căn cứ vào API contract:

- Nếu `email` có thể null theo hợp đồng cũ, không thêm `requireNonNull()` cho field đó.
- Nếu `roles` có thể vắng mặt, xác định rõ có chuyển thành list rỗng hay giữ null.
- Nếu identifier có quy tắc định dạng, xác thực quy tắc đã được công bố.
- Nếu cần chuẩn hóa dữ liệu, bảo đảm việc chuẩn hóa không làm thay đổi ý nghĩa đối với client.

Validation trong constructor bảo vệ mọi đường tạo record. Validation ở controller hoặc request boundary vẫn cần thiết để chuyển lỗi đầu vào thành phản hồi phù hợp, thay vì để exception nội bộ trở thành lỗi server không có kiểm soát.

## 6. Hiểu đúng tính bất biến của record

Record có component fields `final`, nhưng điều đó không đồng nghĩa toàn bộ object graph tự động bất biến.

Ví dụ:

~~~java
public record CustomerDto(String id, List<String> roles) {
}
~~~

Field `roles` là final, nhưng list mà nó trỏ tới có thể mutable. Nếu caller giữ cùng list và sửa list sau khi tạo DTO, dữ liệu quan sát qua record cũng thay đổi.

Dùng defensive copy:

~~~java
import java.util.List;
import java.util.Objects;

public record CustomerDto(String id, List<String> roles) {
    public CustomerDto {
        id = Objects.requireNonNull(id, "id");
        roles = List.copyOf(
            Objects.requireNonNull(roles, "roles")
        );
    }
}
~~~

`List.copyOf()` tạo một list không thể sửa đổi. Nó không tạo deep copy cho từng phần tử. Nếu phần tử là object mutable, object bên trong vẫn có thể thay đổi.

Với collection lồng nhau hoặc object mutable, cần quyết định rõ ownership:

- Dùng immutable value object cho phần tử.
- Tạo defensive copy ở từng tầng cần bảo vệ.
- Không đưa entity hoặc object mutable vào DTO nếu client không cần quyền thay đổi.
- Không trả về mảng mutable mà không sao chép cả khi nhận và khi trả accessor.

### Kiểm tra defensive copy

~~~java
List<String> sourceRoles = new ArrayList<>(List.of("USER"));

CustomerDto dto = new CustomerDto("C-100", sourceRoles);
sourceRoles.add("ADMIN");

System.out.println(dto.roles()); // [USER]
~~~

Caller cũng không thể thêm phần tử trực tiếp:

~~~java
dto.roles().add("ADMIN"); // UnsupportedOperationException
~~~

Tính bất biến này giúp DTO dễ chia sẻ giữa các tầng, giảm rủi ro thay đổi dữ liệu ngoài dự kiến và làm rõ ownership của collection.

## 7. Chuyển mapper và consumer sang record

Sau khi có record, thay cách tạo object bằng canonical constructor:

~~~java
public final class CustomerMapper {
    private CustomerMapper() {
    }

    public static CustomerDto toDto(Customer customer) {
        return new CustomerDto(
            customer.id(),
            customer.displayName(),
            customer.email(),
            customer.roles()
        );
    }
}
~~~

Consumer đọc component qua accessor:

~~~java
CustomerDto dto = CustomerMapper.toDto(customer);

String id = dto.id();
String name = dto.displayName();
List<String> roles = dto.roles();
~~~

Nếu code cũ gọi `getId()`, có hai lựa chọn:

1. Cập nhật consumer sang `id()` nếu đây là thay đổi nội bộ và có thể build lại toàn bộ consumer.
2. Giữ method `getId()` như method bổ sung trên record nếu cần duy trì một phần source/binary API.

Ví dụ:

~~~java
public record CustomerDto(String id, String displayName) {
    public String getId() {
        return id;
    }

    public String getDisplayName() {
        return displayName;
    }
}
~~~

Record cho phép khai báo method instance bổ sung. Tuy nhiên, getter tương thích không khôi phục setter, constructor không tham số hay khả năng mutate DTO. Nếu serializer introspect cả record accessor và JavaBean getter, hãy xác minh nó vẫn tạo đúng một property JSON như hợp đồng yêu cầu.

Không nên giữ getter theo thói quen nếu mọi consumer đã chuyển sang record accessor. Chỉ duy trì method tương thích khi có consumer thực sự cần nó.

## 8. Kiểm tra những thay đổi về Java API

Chuyển class thành record có thể ảnh hưởng đến consumer Java theo nhiều cách:

| Hợp đồng cũ | Sau khi chuyển thành record | Hành động cần làm |
| --- | --- | --- |
| `new CustomerDto()` | Không còn constructor không tham số tự sinh. | Chuyển sang canonical constructor hoặc factory. |
| `setId(...)` | Record không có setter cho component. | Tạo record mới với dữ liệu đã cập nhật. |
| `getId()` | Record tự sinh `id()`. | Cập nhật caller hoặc giữ method getter có chủ đích. |
| Kế thừa DTO class | Record là final và chỉ kế thừa `java.lang.Record`. | Dùng interface hoặc composition nếu cần đa hình. |
| Identity equality mặc định | Record có value-based `equals()`/`hashCode()`. | Kiểm tra logic so sánh và collection. |
| Reflection theo JavaBeans | Framework có thể tìm getter/setter theo quy ước cũ. | Xác minh framework hỗ trợ record. |

### Thay setter bằng cách tạo record mới

Với class mutable, code có thể viết:

~~~java
dto.setDisplayName("An Nguyen");
~~~

Với record, tạo instance mới:

~~~java
CustomerDto updated = new CustomerDto(
    dto.id(),
    "An Nguyen",
    dto.email(),
    dto.roles()
);
~~~

Có thể thêm method tiện ích nếu thao tác này phổ biến:

~~~java
public CustomerDto withDisplayName(String newDisplayName) {
    return new CustomerDto(id, newDisplayName, email, roles);
}
~~~

Method `withDisplayName()` không phải tính năng tự sinh của record. Đây là method do ứng dụng định nghĩa và phải tạo record mới.

### Kiểm tra equals và hashCode

Record dùng value semantics: hai record cùng kiểu và các component bằng nhau sẽ được xem là bằng nhau.

~~~java
CustomerDto first = new CustomerDto(
    "C-100", "An Nguyen", "an@example.test", List.of("USER")
);

CustomerDto second = new CustomerDto(
    "C-100", "An Nguyen", "an@example.test", List.of("USER")
);

System.out.println(first.equals(second)); // true
~~~

Nếu DTO class cũ dùng identity equality, hành vi này thay đổi. Kiểm tra các nơi dùng DTO trong `HashMap`, `HashSet`, cache hoặc test. Hai object trước đây được xem là khác nhau có thể trở thành cùng key theo giá trị.

`toString()` cũng thay đổi sang dạng biểu diễn record. Không dùng `toString()` làm định dạng log/API ổn định, và tránh đưa secret hoặc dữ liệu nhạy cảm vào component vì record-generated `toString()` có thể hiển thị giá trị component.

## 9. Kiểm tra hợp đồng JSON và serializer

Một serializer phải biết cách đọc record components và gọi canonical constructor khi deserialize. Khả năng này phụ thuộc thư viện, phiên bản và cấu hình thực tế.

Jackson bổ sung hỗ trợ record từ dòng 2.12. Với ứng dụng hiện tại, hãy dùng một phiên bản Jackson còn được duy trì và kiểm tra bằng đúng cấu hình mapper đang chạy trong production; không lấy việc một phiên bản cũ từng hỗ trợ record làm lý do giữ dependency đã hết hỗ trợ.

Trước khi chuyển DTO:

1. Kiểm tra phiên bản serializer đang được ứng dụng sử dụng.
2. Xác nhận phiên bản đó hỗ trợ record trên JDK mục tiêu.
3. Kiểm tra naming strategy và annotation đang áp dụng.
4. Kiểm tra cả serialization và deserialization.
5. Chạy test bằng chính cấu hình mapper của production.

Không suy luận rằng mọi framework Java đều hỗ trợ record giống nhau chỉ vì compiler hỗ trợ record.

### Giữ tên JSON khi tên component khác wire contract

Giả sử API cũ dùng field `customer_id`, nhưng code Java muốn dùng component `id`. Với Jackson, có thể khai báo mapping trên record component:

~~~java
import com.fasterxml.jackson.annotation.JsonProperty;
import java.util.List;

public record CustomerDto(
    @JsonProperty("customer_id") String id,
    String displayName,
    String email,
    List<String> roles
) {
}
~~~

Đây là ví dụ dành cho Jackson. Với thư viện khác, dùng annotation hoặc cấu hình tương ứng của thư viện đó. Không thêm annotation của một serializer nếu ứng dụng không dùng serializer ấy.

### Kiểm tra round-trip

Ví dụ test với Jackson `ObjectMapper` đã được cấu hình như ứng dụng:

~~~java
@Test
void jsonContractRemainsStable() throws Exception {
    CustomerDto dto = new CustomerDto(
        "C-100",
        "An Nguyen",
        "an@example.test",
        List.of("USER", "REPORT_VIEWER")
    );

    String serialized = objectMapper.writeValueAsString(dto);
    JsonNode json = objectMapper.readTree(serialized);

    assertEquals("C-100", json.get("id").asText());
    assertEquals("An Nguyen", json.get("displayName").asText());
    assertEquals("an@example.test", json.get("email").asText());
    assertEquals(2, json.get("roles").size());

    CustomerDto restored =
        objectMapper.readValue(serialized, CustomerDto.class);

    assertEquals(dto, restored);
}
~~~

Round-trip test hữu ích nhưng chưa đủ. Nếu client phụ thuộc chính xác tên field, kiểu JSON, nullability hoặc field bị lược bỏ, hãy kiểm tra các đặc điểm đó trực tiếp.

Không chỉ assert object sau deserialize bằng object ban đầu. Serializer có thể serialize và deserialize cùng một sai lệch nên round-trip vẫn pass dù wire contract đã thay đổi.

## 10. Kiểm tra null, missing field và default value

Class mutable thường có thể được tạo không tham số rồi chỉ set một phần field. Record thường yêu cầu truyền giá trị cho tất cả component qua canonical constructor.

Điều này làm rõ trạng thái dữ liệu, nhưng có thể thay đổi cách deserialize JSON thiếu field.

Ví dụ, API có thể nhận:

~~~json
{
  "id": "C-100",
  "displayName": "An Nguyen"
}
~~~

Trong khi `email` và `roles` bị thiếu. Hãy xác định hợp đồng hiện tại quy định:

- Field thiếu được xem là null.
- Field thiếu được thay bằng default value.
- Field thiếu là lỗi validation.
- Field null khác với field không xuất hiện.

Đừng tự động thay null bằng list rỗng hoặc chuỗi rỗng nếu client đang phân biệt hai trạng thái đó.

Nếu component là primitive như `int` hoặc `boolean`, giá trị mặc định của kiểu primitive có thể làm mất khả năng phân biệt null với zero/false. Nếu hợp đồng cần trạng thái chưa cung cấp, cân nhắc kiểu wrapper hoặc mô hình biểu diễn phù hợp.

Với field optional, có thể dùng component nullable hoặc một kiểu dữ liệu thể hiện rõ trạng thái. Điều quan trọng là giữ nguyên semantics đã công bố.

## 11. Kiểm tra annotation và validation framework

Framework validation có thể đặt annotation trên field, getter, constructor parameter hoặc record component. Record component có thể truyền annotation tới các thành phần tương ứng tùy `@Target` của annotation và quy tắc áp dụng annotation của Java.

Ví dụ với Bean Validation:

~~~java
public record CreateCustomerRequest(
    @NotBlank String displayName,
    @Email String email
) {
}
~~~

Đây là ví dụ minh họa. Để hoạt động đúng, ứng dụng cần dùng phiên bản validation provider/framework hỗ trợ record component và cấu hình validation cho request boundary.

Cần kiểm tra:

- Annotation được đặt ở vị trí framework thực sự đọc.
- Constructor validation và Bean Validation không mâu thuẫn.
- Lỗi validation được chuyển thành response theo hợp đồng hiện có.
- Field optional không bị đánh dấu bắt buộc ngoài ý muốn.
- Nested object và collection được validate theo đúng cascade rules.

Không coi annotation trên record component là bảo đảm framework cũ sẽ tự nhận diện. Hãy kiểm tra bằng test tích hợp với đúng phiên bản dependency.

## 12. Xác định record có phù hợp với DTO này không

Record phù hợp khi:

- DTO chủ yếu mang dữ liệu.
- Các giá trị được xác định tại thời điểm tạo object.
- Không cần setter hoặc lifecycle mutation.
- Value equality phù hợp với semantics của dữ liệu.
- Framework serializer, mapper và validation hỗ trợ record.
- API có thể chấp nhận constructor/accessor mới hoặc có lớp adapter giữ tương thích.

Nên giữ class thông thường khi:

- Consumer cần setter hoặc trạng thái thay đổi theo lifecycle.
- Framework bắt buộc no-arg constructor và JavaBean property mutation nhưng chưa hỗ trợ record.
- DTO cần kế thừa một class cụ thể.
- Equality phải dựa trên identity hoặc quy tắc tùy chỉnh phức tạp.
- Public API phải giữ tương thích với constructor và setter cũ.
- Dữ liệu có quy trình khởi tạo nhiều bước mà record constructor không diễn tả rõ.

Record là lựa chọn tốt cho immutable DTO, request/response model và projection khi framework hỗ trợ. Không nên thay mọi class có tên `Dto` thành record mà không xem xét semantics.

Đặc biệt, DTO dùng ở biên API thường khác entity được quản lý bởi ORM. Không mặc định dùng record làm JPA entity; hãy tuân theo yêu cầu lifecycle, constructor, proxy và mutability của persistence framework.

## 13. Kiểm tra source compatibility và binary compatibility

Nếu DTO chỉ dùng trong một ứng dụng được build đồng thời, việc cập nhật mọi call site và build lại thường đủ để phát hiện phần lớn lỗi source compatibility.

Nếu DTO nằm trong thư viện hoặc module được consumer biên dịch độc lập sử dụng, cần đánh giá public API kỹ hơn.

Các điểm có thể phá vỡ tương thích:

- Constructor không tham số bị loại bỏ.
- Setter biến mất.
- Getter đổi tên thành record accessor.
- Lớp trở thành final.
- Superclass thay đổi thành `java.lang.Record`.
- Consumer dựa vào JavaBeans introspection.
- Reflection hoặc serialization phụ thuộc class shape.
- `equals()` và `hashCode()` đổi từ identity sang value semantics.

Giữ lại getter có thể bảo toàn một số method signature, nhưng không khôi phục toàn bộ contract của class cũ. Không tuyên bố binary compatibility chỉ vì code consumer có thể gọi được một getter.

Với thư viện public, cân nhắc:

1. Tạo DTO record mới với tên hoặc package/version rõ ràng.
2. Giữ DTO class cũ trong một giai đoạn chuyển tiếp.
3. Viết mapper giữa DTO cũ và record mới.
4. Đánh dấu API cũ deprecated theo chính sách phát hành nếu phù hợp.
5. Chỉ loại bỏ DTO cũ ở major release có thông báo migration.

## 14. Bài thực hành tích hợp từ mapper đến endpoint

Giả sử domain model cung cấp dữ liệu:

~~~java
import java.util.List;

public interface Customer {
    String id();
    String displayName();
    String email();
    List<String> roles();
}
~~~

Tạo record DTO:

~~~java
import java.util.List;
import java.util.Objects;

public record CustomerDto(
    String id,
    String displayName,
    String email,
    List<String> roles
) {
    public CustomerDto {
        id = Objects.requireNonNull(id, "id").strip();
        displayName = Objects.requireNonNull(
            displayName, "displayName"
        ).strip();
        email = Objects.requireNonNull(email, "email").strip();
        roles = List.copyOf(
            Objects.requireNonNull(roles, "roles")
        );

        if (id.isBlank() || displayName.isBlank() || email.isBlank()) {
            throw new IllegalArgumentException(
                "Customer fields must not be blank"
            );
        }
    }
}
~~~

Mapper:

~~~java
public final class CustomerMapper {
    private CustomerMapper() {
    }

    public static CustomerDto toDto(Customer customer) {
        return new CustomerDto(
            customer.id(),
            customer.displayName(),
            customer.email(),
            customer.roles()
        );
    }
}
~~~

Service:

~~~java
public final class CustomerService {
    private final CustomerRepository repository;

    public CustomerService(CustomerRepository repository) {
        this.repository = repository;
    }

    public CustomerDto findCustomer(String id) {
        Customer customer = repository.findById(id);
        return CustomerMapper.toDto(customer);
    }
}
~~~

Controller hoặc HTTP adapter trả DTO:

~~~java
public CustomerDto getCustomer(String id) {
    return customerService.findCustomer(id);
}
~~~

Đoạn controller trên là minh họa độc lập với framework. Với framework HTTP thực tế, cần xác nhận serializer của framework hỗ trợ record và giữ đúng JSON contract.

### Kiểm tra mapping

~~~java
@Test
void mapperCopiesDomainDataIntoRecord() {
    Customer customer = customerFixture();

    CustomerDto dto = CustomerMapper.toDto(customer);

    assertEquals(customer.id(), dto.id());
    assertEquals(customer.displayName(), dto.displayName());
    assertEquals(customer.email(), dto.email());
    assertEquals(customer.roles(), dto.roles());
}
~~~

Test mapping giúp phát hiện việc đảo component, bỏ sót field hoặc chuẩn hóa sai dữ liệu.

## 15. Bộ kiểm thử cần có sau refactor

Một refactor DTO hoàn chỉnh nên có nhiều lớp kiểm thử:

| Loại test | Điều cần xác nhận |
| --- | --- |
| Constructor test | Nullability, validation, normalization và quy tắc biên. |
| Immutability test | Collection không bị thay đổi qua reference bên ngoài hoặc accessor. |
| Value semantics test | `equals()` và `hashCode()` phù hợp với hợp đồng mới. |
| Mapper test | Domain data được ánh xạ đúng vào component. |
| JSON serialization test | Tên field, kiểu dữ liệu, null và format không đổi. |
| JSON deserialization test | Serializer gọi được constructor và tạo object hợp lệ. |
| HTTP contract test | Status, header, content type, schema và response body không đổi ngoài dự kiến. |
| Consumer test | Các client nội bộ hoặc thư viện sử dụng DTO vẫn biên dịch và chạy. |

### Test tính bất biến

~~~java
@Test
void rolesAreDefensivelyCopied() {
    List<String> source = new ArrayList<>(List.of("USER"));

    CustomerDto dto = new CustomerDto(
        "C-100", "An Nguyen", "an@example.test", source
    );

    source.add("ADMIN");

    assertEquals(List.of("USER"), dto.roles());
    assertThrows(
        UnsupportedOperationException.class,
        () -> dto.roles().add("ADMIN")
    );
}
~~~

### Test value semantics

~~~java
@Test
void recordsUseComponentValueEquality() {
    CustomerDto first = new CustomerDto(
        "C-100", "An Nguyen", "an@example.test", List.of("USER")
    );
    CustomerDto second = new CustomerDto(
        "C-100", "An Nguyen", "an@example.test", List.of("USER")
    );

    assertEquals(first, second);
    assertEquals(first.hashCode(), second.hashCode());
}
~~~

Nếu semantics mới không phù hợp với consumer cũ, đây là tín hiệu cần giữ class hoặc thay đổi cách thiết kế thay vì cố ép record vào vai trò không phù hợp.

## 16. Quy trình refactor an toàn

Có thể chia việc chuyển DTO thành các bước nhỏ để dễ review:

1. **Tìm usage:** tìm constructor, getter, setter, reflection, serializer, mapper và test.
2. **Chụp contract hiện tại:** lưu JSON fixture và kiểm tra API Java công khai.
3. **Chọn component:** xác định tên, thứ tự, kiểu, nullability và semantics của từng component.
4. **Thiết kế constructor:** thêm validation và defensive copy theo đúng contract.
5. **Cập nhật mapper:** thay khởi tạo rời rạc bằng canonical constructor.
6. **Cập nhật consumer nội bộ:** chuyển getter sang accessor và loại setter usage.
7. **Kiểm tra framework:** xác nhận serializer, validation, mapper và dependency injection hỗ trợ record.
8. **Viết regression/contract test:** so sánh JSON và hành vi endpoint trước/sau.
9. **Build toàn bộ consumer:** tìm lỗi source compatibility và binary compatibility phù hợp phạm vi sản phẩm.
10. **Đánh giá phát hành:** nếu DTO là public API, chọn versioning hoặc adapter khi có breaking change.
11. **Theo dõi sau phát hành:** kiểm tra log serialization, validation error và lỗi client integration.

Không xóa DTO class cũ trước khi đã xác định mọi consumer được chuyển đổi hoặc có adapter tương thích.

## 17. Lỗi thường gặp và cách khắc phục

1. **Chuyển class thành record chỉ bằng cách bỏ getter/setter:** kiểm tra constructor, accessor, reflection và serializer.
2. **Giữ list mutable bên trong record:** dùng defensive copy phù hợp như `List.copyOf()`.
3. **Cho rằng record bất biến sâu:** component có thể tham chiếu object mutable; kiểm tra cả object graph.
4. **Đổi null thành empty collection:** chỉ làm nếu API contract quy định như vậy.
5. **Quên getter JavaBeans:** record accessor là `id()`, không tự có `getId()`.
6. **Giả định mọi serializer đều hỗ trợ record:** xác minh phiên bản và cấu hình framework thực tế.
7. **Chỉ test round-trip JSON:** kiểm tra độc lập tên field, kiểu dữ liệu, nullability và schema.
8. **Bỏ qua value equality:** kiểm tra cache, Map, Set và logic so sánh DTO.
9. **Dùng record cho object cần setter/lifecycle mutation:** giữ class nếu semantics cần thay đổi trạng thái.
10. **Cho rằng giữ getter là đủ tương thích:** constructor, setter, superclass, finality và reflection contract vẫn có thể thay đổi.
11. **Đưa secret vào record component:** `toString()` tự sinh có thể hiển thị component value; tránh lưu secret hoặc kiểm soát logging.
12. **Không build lại consumer:** compile và test tất cả module sử dụng DTO trong phạm vi có thể kiểm soát.
13. **Đổi component name mà quên JSON mapping:** giữ wire name bằng cấu hình/annotation phù hợp và contract test.
14. **Thay đổi public DTO mà không versioning:** dùng adapter hoặc phát hành breaking change theo chính sách API.

## 18. Bài tập thực hành

1. Tạo DTO class có no-arg constructor, getter và setter cho `id`, `name`, `email`.
2. Ghi lại constructor, getter, setter và JSON contract đang được consumer sử dụng.
3. Chuyển DTO thành `CustomerDto` record với canonical constructor.
4. Thêm validation cho identifier và display name theo quy tắc đã thống nhất.
5. Dùng `List.copyOf()` để bảo vệ collection component.
6. Chuyển mapper từ setter-based construction sang canonical constructor.
7. Chuyển consumer từ `getId()` sang `id()`.
8. Thêm getter tương thích và kiểm tra serializer có tạo JSON field trùng hay không.
9. Viết test cho null, blank string, list null và list chứa null.
10. Viết test chứng minh list nguồn thay đổi không làm record thay đổi.
11. Viết JSON contract test cho field name, type, nullability và round-trip.
12. Kiểm tra `equals()`/`hashCode()` trong `HashSet` và `HashMap`.
13. Thử dùng record với serializer hiện có của dự án và ghi lại phiên bản hỗ trợ.
14. Đánh giá DTO có phải public API không; nếu có, thiết kế adapter hoặc version mới.
15. Viết báo cáo refactor nêu các API Java đã đổi, contract JSON đã giữ và test đã chạy.

## Ghi nhớ

Record phù hợp với DTO mang dữ liệu có state được xác định khi khởi tạo. Java tự tạo canonical constructor, accessor theo tên component, `equals()`, `hashCode()` và `toString()`. Khi refactor, cần kiểm tra cả Java API lẫn wire contract: constructor không tham số, setter, getter JavaBeans, tên JSON, nullability, serializer support và equality semantics đều có thể thay đổi. Component fields là final nhưng object graph không tự động immutable; dùng defensive copy cho collection mutable và xác định rõ ownership. Test constructor, mapper, JSON serialization/deserialization, HTTP contract và consumer trước khi phát hành. Với public API có breaking change, cân nhắc adapter hoặc version mới thay vì âm thầm đổi class thành record.

**Tài liệu tham khảo chính thức:**

- [JEP 395 – Records](https://openjdk.org/jeps/395)
- [Java Language Specification – Record Classes](https://docs.oracle.com/javase/specs/jls/se16/html/jls-8.html#jls-8.10)
- [Java API – java.lang.Record](https://docs.oracle.com/en/java/javase/16/docs/api/java.base/java/lang/Record.html)
- [Java API – List.copyOf](https://docs.oracle.com/en/java/javase/16/docs/api/java.base/java/util/List.html#copyOf(java.util.Collection))
- [Jackson – Java 16 Record Support](https://github.com/FasterXML/jackson-databind/issues/2709)
