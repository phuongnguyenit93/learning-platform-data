# Ánh xạ DTO bất biến có generic và đối tượng lồng nhau

Trong một ứng dụng Java, DTO thường có nhiều lớp lồng nhau: response chứa page, page chứa danh sách item, mỗi item lại chứa địa chỉ, thông tin người dùng hoặc metadata. Khi các DTO cần bất biến, chúng không có setter và thường được tạo qua constructor, record hoặc builder. Khi một lớp còn có generic type như ApiResponse<T>, Page<T> hoặc Envelope<T>, Jackson cần biết kiểu tham số thực tế để deserialize đúng object ở mọi cấp.

Ba yêu cầu phải được giải quyết cùng lúc:

1. Jackson phải biết đầy đủ kiểu đích, bao gồm generic parameter và các kiểu lồng nhau.
2. Jackson phải biết cách tạo object bất biến qua canonical constructor, property-based creator hoặc builder.
3. Model phải bảo vệ invariant và collection state sau khi được tạo.

Nếu chỉ truyền raw class cho một generic wrapper, phần payload có thể trở thành LinkedHashMap thay vì DTO mong muốn. Nếu constructor không được mô tả rõ, Jackson có thể không tìm được creator hoặc ánh xạ sai tham số. Nếu chỉ dùng final field mà không defensive-copy collection, object vẫn có thể bị thay đổi từ bên ngoài.

Bài học này trình bày cách thiết kế và ánh xạ DTO bất biến có generic và object lồng nhau bằng Jackson Databind, từ kiểu đơn giản đến các cấu trúc nhiều tầng, đồng thời chỉ ra cách kiểm thử hợp đồng dữ liệu độc lập với implementation.

## 1. Mô hình dữ liệu lồng nhau và generic

Một response API thực tế thường có dạng:

~~~json
{
  "requestId": "req-100",
  "success": true,
  "data": {
    "page": 1,
    "size": 20,
    "totalElements": 2,
    "items": [
      {
        "id": 101,
        "name": "An",
        "address": {
          "street": "12 Nguyen Trai",
          "city": "Ho Chi Minh City"
        }
      },
      {
        "id": 102,
        "name": "Binh",
        "address": {
          "street": "8 Le Loi",
          "city": "Da Nang"
        }
      }
    ]
  }
}
~~~

Cấu trúc này có nhiều tầng:

~~~text
ApiResponse<Page<UserDto>>
    |
    +-- requestId: String
    +-- success: boolean
    +-- data: Page<UserDto>
                 |
                 +-- page: int
                 +-- size: int
                 +-- totalElements: long
                 +-- items: List<UserDto>
                               |
                               +-- id: long
                               +-- name: String
                               +-- address: AddressDto
~~~

Các class có thể được định nghĩa như sau:

~~~java
public record AddressDto(
    String street,
    String city
) {}

public record UserDto(
    long id,
    String name,
    AddressDto address
) {}

public record Page<T>(
    int page,
    int size,
    long totalElements,
    List<T> items
) {}

public record ApiResponse<T>(
    String requestId,
    boolean success,
    T data
) {}
~~~

Ở đây Page<T> và ApiResponse<T> là generic; UserDto và AddressDto là các object lồng nhau. Jackson có thể bind cấu trúc này nếu nhận được target type đầy đủ.

## 2. Vì sao raw Class không đủ cho generic?

Java dùng type erasure. Ở runtime, một Class object như ApiResponse.class không giữ đầy đủ thông tin rằng T là UserDto hay Page<UserDto>.

Đoạn sau không mô tả được kiểu payload cụ thể:

~~~java
ApiResponse response = mapper.readValue(
    json,
    ApiResponse.class
);
~~~

Jackson chỉ biết đang đọc ApiResponse. Với property data có kiểu T, nếu không có type parameter cụ thể, Jackson thường xử lý nó như Object. Object bên trong JSON có thể trở thành LinkedHashMap, array thành List và scalar thành các kiểu Java tương ứng.

Hậu quả:

- response.data() không phải UserDto hoặc Page<UserDto>.
- Phải ép kiểu thủ công ở runtime.
- Generic lồng nhau có thể chứa Map/List không có element type cụ thể.
- Lỗi sai kiểu chỉ xuất hiện khi code truy cập sâu vào payload.
- Type safety ở compile time không còn phản ánh dữ liệu thực tế.

Không nên giải quyết bằng cast:

~~~java
UserDto user = (UserDto) response.data();
~~~

Cast không cung cấp type information cho Jackson và có thể ném ClassCastException. Cần truyền target type đầy đủ ngay tại thời điểm deserialize.

## 3. TypeReference cho generic type đã biết

Jackson cung cấp TypeReference để giữ thông tin generic thông qua anonymous subclass.

Ví dụ:

~~~java
ApiResponse<UserDto> response = mapper.readValue(
    json,
    new TypeReference<ApiResponse<UserDto>>() {}
);
~~~

Với cấu trúc lồng nhau:

~~~java
ApiResponse<Page<UserDto>> response = mapper.readValue(
    json,
    new TypeReference<ApiResponse<Page<UserDto>>>() {}
);
~~~

Jackson nhận được cấu trúc kiểu:

~~~text
ApiResponse
    T = Page<UserDto>
            T = UserDto
~~~

Nó có thể bind:

- ApiResponse.requestId thành String.
- ApiResponse.success thành boolean.
- ApiResponse.data thành Page<UserDto>.
- Page.items thành List<UserDto>.
- Mỗi phần tử thành UserDto.
- UserDto.address thành AddressDto.

### 3.1. Test phần tử ở tầng sâu nhất

Không chỉ assert response hoặc data khác null. Hãy kiểm tra phần tử trong collection và object lồng nhau:

~~~java
@Test
void readsNestedGenericResponse() throws Exception {
    ApiResponse<Page<UserDto>> response = mapper.readValue(
        json,
        new TypeReference<ApiResponse<Page<UserDto>>>() {}
    );

    assertTrue(response.success());
    assertEquals("req-100", response.requestId());

    Page<UserDto> page = response.data();

    assertEquals(2, page.items().size());
    assertInstanceOf(UserDto.class, page.items().get(0));
    assertEquals(101L, page.items().get(0).id());
    assertEquals("An", page.items().get(0).name());
    assertEquals(
        "Ho Chi Minh City",
        page.items().get(0).address().city()
    );
}
~~~

Test này xác nhận generic type đã được giải quyết đúng ở cấp Page, List, UserDto và AddressDto.

### 3.2. Generic nhiều cấp không làm thay đổi cách khai báo

Các kiểu như:

~~~java
ApiResponse<List<UserDto>>
ApiResponse<Map<String, UserDto>>
ApiResponse<Page<List<UserDto>>>
Map<String, List<ApiResponse<UserDto>>>
~~~

đều có thể được biểu diễn bằng TypeReference khi kiểu cụ thể được biết tại compile time.

Hãy viết target type theo cấu trúc dữ liệu thực tế. Không rút gọn thành raw ApiResponse hoặc Map chỉ để code ngắn hơn.

## 4. JavaType và TypeFactory cho kiểu được tạo động

TypeReference thuận tiện khi kiểu cụ thể đã biết trong source. Nhưng một số ứng dụng chọn DTO theo cấu hình, endpoint, event type hoặc schema version tại runtime.

Khi đó dùng JavaType và TypeFactory:

~~~java
TypeFactory types = mapper.getTypeFactory();

JavaType userType = types.constructType(UserDto.class);

JavaType userListType = types.constructCollectionType(
    List.class,
    userType
);

JavaType pageType = types.constructParametricType(
    Page.class,
    userListType
);

JavaType responseType = types.constructParametricType(
    ApiResponse.class,
    pageType
);

ApiResponse<Page<List<UserDto>>> response =
    mapper.readValue(json, responseType);
~~~

JavaType là mô tả kiểu mà Jackson dùng trong databind. Nó hỗ trợ:

- Generic parameter.
- Collection element type.
- Map key/value type.
- Generic type lồng nhau.
- Kiểu được lựa chọn ở runtime.

### 4.1. Helper nhận JavaType thay vì Class

Một helper chỉ nhận Class<T> không thể mô tả mọi generic lồng nhau. Nếu API cần hỗ trợ các payload phức tạp, nhận JavaType:

~~~java
static <T> T read(
        ObjectMapper mapper,
        String json,
        JavaType targetType) throws JsonProcessingException {

    return mapper.readValue(json, targetType);
}
~~~

Caller tự tạo type:

~~~java
JavaType targetType = mapper.getTypeFactory()
    .constructParametricType(
        ApiResponse.class,
        mapper.getTypeFactory().constructType(UserDto.class)
    );

ApiResponse<UserDto> result = read(mapper, json, targetType);
~~~

Helper này giữ nguyên cấu trúc kiểu do caller cung cấp. Nó không phải tự đoán generic parameter từ biến nhận kết quả.

### 4.2. Helper với TypeReference

Nếu caller có thể truyền TypeReference:

~~~java
static <T> T read(
        ObjectMapper mapper,
        String json,
        TypeReference<T> type) throws JsonProcessingException {

    return mapper.readValue(json, type);
}
~~~

Sử dụng:

~~~java
ApiResponse<Page<UserDto>> response = read(
    mapper,
    json,
    new TypeReference<ApiResponse<Page<UserDto>>>() {}
);
~~~

Đây là cách gọn cho code statically typed.

### 4.3. Không tạo TypeReference<T> bên trong generic method rồi kỳ vọng T được giữ

Đoạn sau không giải quyết được type erasure:

~~~java
static <T> ApiResponse<T> readResponse(
        ObjectMapper mapper,
        String json) throws IOException {

    return mapper.readValue(
        json,
        new TypeReference<ApiResponse<T>>() {}
    );
}
~~~

T là type variable của method. Runtime không tự biết caller đang muốn UserDto, OrderDto hay Page<UserDto>.

Truyền Class<T>, TypeReference<T> hoặc JavaType từ caller. Với nested generic, JavaType thường linh hoạt nhất.

## 5. Ánh xạ immutable record có object lồng nhau

Record là một cách tự nhiên để khai báo DTO bất biến:

~~~java
public record AddressDto(
    String street,
    String city
) {}

public record UserDto(
    long id,
    String name,
    AddressDto address
) {}
~~~

Record không có setter thông thường. Jackson tạo record qua canonical constructor, sử dụng các component được khai báo trong record header.

Với Jackson Databind từ dòng hỗ trợ record (2.12 trở lên) và JDK hỗ trợ record, có thể deserialize trực tiếp:

~~~java
UserDto user = mapper.readValue(json, UserDto.class);
~~~

Nếu object con cũng là record, Jackson tiếp tục gọi canonical constructor của AddressDto.

### 5.1. Test nested record

~~~java
@Test
void readsImmutableRecordWithNestedRecord() throws Exception {
    UserDto user = mapper.readValue(
        """
        {
          "id": 101,
          "name": "An",
          "address": {
            "street": "12 Nguyen Trai",
            "city": "Ho Chi Minh City"
          }
        }
        """,
        UserDto.class
    );

    assertEquals(101L, user.id());
    assertEquals("An", user.name());
    assertEquals("12 Nguyen Trai", user.address().street());
    assertEquals("Ho Chi Minh City", user.address().city());
}
~~~

Nếu address là object nhưng DTO khai báo AddressDto, Jackson cần bind object con trước khi gọi constructor UserDto. Nếu JSON shape không khớp, lỗi thường xuất hiện ở path của property address.

### 5.2. Đổi tên JSON property

Dùng @JsonProperty khi wire name khác tên component Java:

~~~java
public record UserDto(
    @JsonProperty("user_id") long id,
    @JsonProperty("display_name") String name,
    AddressDto address
) {}
~~~

JSON:

~~~json
{
  "user_id": 101,
  "display_name": "An",
  "address": {
    "street": "12 Nguyen Trai",
    "city": "Ho Chi Minh City"
  }
}
~~~

Hãy kiểm tra cả chiều serialize và deserialize. Global naming strategy có thể ảnh hưởng tên property nếu contract không khai báo tường minh.

## 6. Immutable POJO qua property-based creator

Nếu không dùng record, một class bất biến có thể dùng final field và constructor được đánh dấu @JsonCreator.

~~~java
public final class AddressDto {

    private final String street;
    private final String city;

    @JsonCreator(mode = JsonCreator.Mode.PROPERTIES)
    public AddressDto(
        @JsonProperty("street") String street,
        @JsonProperty("city") String city
    ) {
        this.street = Objects.requireNonNull(street);
        this.city = Objects.requireNonNull(city);
    }

    public String getStreet() {
        return street;
    }

    public String getCity() {
        return city;
    }
}
~~~

Jackson đọc property rồi gọi constructor. Không cần setter hoặc constructor không tham số.

### 6.1. Immutable object lồng nhau

~~~java
public final class UserDto {

    private final long id;
    private final String name;
    private final AddressDto address;

    @JsonCreator(mode = JsonCreator.Mode.PROPERTIES)
    public UserDto(
        @JsonProperty("id") long id,
        @JsonProperty("name") String name,
        @JsonProperty("address") AddressDto address
    ) {
        this.id = id;
        this.name = Objects.requireNonNull(name);
        this.address = Objects.requireNonNull(address);
    }

    public long getId() {
        return id;
    }

    public String getName() {
        return name;
    }

    public AddressDto getAddress() {
        return address;
    }
}
~~~

Jackson deserialize AddressDto trước hoặc trong quá trình giải quyết tham số creator, sau đó truyền object con vào constructor UserDto.

### 6.2. Vì sao nên dùng @JsonProperty tường minh?

Jackson cần biết tham số constructor nào tương ứng với JSON property nào. Tên tham số Java không phải lúc nào cũng có sẵn trong bytecode hoặc được bật qua compiler option.

Dùng @JsonProperty tường minh giúp mapping ổn định hơn giữa build tool, compiler và môi trường triển khai.

ParameterNamesModule có thể hỗ trợ lấy parameter name metadata trong những trường hợp phù hợp, nhưng không nên dựa vào nó nếu contract quan trọng mà build không đảm bảo metadata.

## 7. Kết hợp generic wrapper với immutable constructor

Một generic wrapper bất biến:

~~~java
public final class ApiResponse<T> {

    private final String requestId;
    private final boolean success;
    private final T data;

    @JsonCreator(mode = JsonCreator.Mode.PROPERTIES)
    public ApiResponse(
        @JsonProperty("requestId") String requestId,
        @JsonProperty("success") boolean success,
        @JsonProperty("data") T data
    ) {
        this.requestId = Objects.requireNonNull(requestId);
        this.success = success;
        this.data = data;
    }

    public String getRequestId() {
        return requestId;
    }

    public boolean isSuccess() {
        return success;
    }

    public T getData() {
        return data;
    }
}
~~~

Deserialize phải truyền generic type:

~~~java
ApiResponse<Page<UserDto>> response = mapper.readValue(
    json,
    new TypeReference<ApiResponse<Page<UserDto>>>() {}
);
~~~

Hai phần giải quyết hai vấn đề khác nhau:

- @JsonCreator và @JsonProperty cho Jackson cách tạo immutable ApiResponse.
- TypeReference cho Jackson biết T là Page<UserDto>.

Nếu chỉ có creator đúng mà truyền raw ApiResponse.class, data vẫn có thể thành Map. Nếu chỉ có TypeReference mà Jackson không tìm được creator, immutable class vẫn không được tạo.

## 8. Generic superclass và kế thừa

Một số model dùng generic base class:

~~~java
public abstract class BaseEnvelope<T> {

    private final String messageId;
    private final T payload;

    @JsonCreator(mode = JsonCreator.Mode.PROPERTIES)
    protected BaseEnvelope(
        @JsonProperty("messageId") String messageId,
        @JsonProperty("payload") T payload
    ) {
        this.messageId = messageId;
        this.payload = payload;
    }

    public String getMessageId() {
        return messageId;
    }

    public T getPayload() {
        return payload;
    }
}
~~~

Subclass có thể cố định type parameter:

~~~java
public final class UserEnvelope extends BaseEnvelope<UserDto> {

    @JsonCreator(mode = JsonCreator.Mode.PROPERTIES)
    public UserEnvelope(
        @JsonProperty("messageId") String messageId,
        @JsonProperty("payload") UserDto payload
    ) {
        super(messageId, payload);
    }
}
~~~

Khi subclass cố định T, Jackson có thể suy ra payload type từ subclass metadata trong các trường hợp thông thường. Tuy nhiên, với base type generic được dùng trực tiếp, vẫn phải truyền JavaType/TypeReference đầy đủ.

Đừng khai báo hai creator không cần thiết nếu một creator đã đủ. Với inheritance phức tạp, test riêng constructor, property visibility và type resolution của đúng version Jackson.

## 9. Immutable collection trong DTO lồng nhau

Một record có final component không tự bảo đảm collection bên trong bất biến:

~~~java
public record TeamDto(
    String name,
    List<UserDto> members
) {}
~~~

List được truyền vào vẫn có thể bị caller sửa sau khi record được tạo. Để bảo vệ state, defensive-copy trong compact constructor:

~~~java
public record TeamDto(
    String name,
    List<UserDto> members
) {
    public TeamDto {
        name = Objects.requireNonNull(name);
        members = List.copyOf(members);
    }
}
~~~

Với immutable POJO:

~~~java
public final class TeamDto {

    private final String name;
    private final List<UserDto> members;

    @JsonCreator(mode = JsonCreator.Mode.PROPERTIES)
    public TeamDto(
        @JsonProperty("name") String name,
        @JsonProperty("members") List<UserDto> members
    ) {
        this.name = Objects.requireNonNull(name);
        this.members = List.copyOf(members);
    }

    public String getName() {
        return name;
    }

    public List<UserDto> getMembers() {
        return members;
    }
}
~~~

List.copyOf() tạo list không thể sửa qua reference được trả về và từ chối null collection hoặc null element. Nếu hợp đồng cho phép null, cần xử lý rõ trước khi copy hoặc dùng một chính sách khác.

### 9.1. Kiểm thử defensive copy

~~~java
@Test
void immutableDtoDefensivelyCopiesNestedCollection() {
    List<UserDto> source = new ArrayList<>(
        List.of(sampleUser())
    );

    TeamDto team = new TeamDto("Engineering", source);

    source.clear();

    assertEquals(1, team.members().size());
    assertThrows(
        UnsupportedOperationException.class,
        () -> team.members().clear()
    );
}
~~~

Đây là test tính bất biến của model Java, không chỉ là test Jackson. Nó bảo vệ object sau khi deserialize và sau khi được truyền qua các layer khác.

## 10. Collection generic lồng nhau

DTO có thể chứa nhiều collection:

~~~java
public record DepartmentDto(
    String name,
    List<TeamDto> teams
) {}

public record OrganizationDto(
    String organizationId,
    Map<String, DepartmentDto> departments
) {}
~~~

Khi đọc OrganizationDto, Jackson biết kiểu Map value là DepartmentDto từ declaration của field, không cần TypeReference ở root vì root class đã khai báo generic field cụ thể.

Nhưng nếu root chính là một generic collection hoặc wrapper, cần truyền kiểu đích đầy đủ:

~~~java
List<OrganizationDto> organizations = mapper.readValue(
    json,
    new TypeReference<List<OrganizationDto>>() {}
);
~~~

### 10.1. Collection lồng nhiều cấp

Ví dụ:

~~~java
public record CatalogDto(
    Map<String, List<ProductDto>> categories
) {}
~~~

Nếu CatalogDto là root class, field generic được khai báo rõ nên Jackson có thể resolve type. Nếu root là Map<String, List<ProductDto>>, dùng TypeReference:

~~~java
Map<String, List<ProductDto>> catalog = mapper.readValue(
    json,
    new TypeReference<Map<String, List<ProductDto>>>() {}
);
~~~

Test phải kiểm tra value type và element type, không chỉ kiểm tra key tồn tại.

## 11. Map key và generic value trong object lồng nhau

JSON object key luôn là string. Khi bind vào Map, Jackson chuyển key theo key deserializer của target type.

Ví dụ:

~~~java
public record PriceBook(
    Map<String, BigDecimal> prices
) {}
~~~

Nếu Map key là enum:

~~~java
public enum Region {
    NORTH,
    CENTRAL,
    SOUTH
}

public record RegionalPrices(
    Map<Region, BigDecimal> prices
) {}
~~~

JSON:

~~~json
{
  "prices": {
    "NORTH": 100.50,
    "SOUTH": 95.00
  }
}
~~~

Jackson cần chuyển text key thành Region. Key không hợp lệ có thể gây mapping exception. Test cả key hợp lệ và không hợp lệ.

Nếu key là kiểu phức tạp không thể biểu diễn tự nhiên bằng JSON property name, hãy dùng array of entries hoặc DTO có field key/value thay vì ép một object phức tạp thành Map key.

## 12. Builder cho immutable DTO lồng nhau

Một số immutable class dùng builder thay vì constructor property-based. Jackson hỗ trợ thông qua @JsonDeserialize và @JsonPOJOBuilder.

Ví dụ:

~~~java
@JsonDeserialize(builder = UserDto.Builder.class)
public final class UserDto {

    private final long id;
    private final String name;
    private final AddressDto address;

    private UserDto(Builder builder) {
        this.id = builder.id;
        this.name = Objects.requireNonNull(builder.name);
        this.address = Objects.requireNonNull(builder.address);
    }

    public long getId() {
        return id;
    }

    public String getName() {
        return name;
    }

    public AddressDto getAddress() {
        return address;
    }

    @JsonPOJOBuilder(withPrefix = "")
    public static class Builder {
        private long id;
        private String name;
        private AddressDto address;

        public Builder id(long id) {
            this.id = id;
            return this;
        }

        public Builder name(String name) {
            this.name = name;
            return this;
        }

        public Builder address(AddressDto address) {
            this.address = address;
            return this;
        }

        public UserDto build() {
            return new UserDto(this);
        }
    }
}
~~~

Jackson gọi builder methods rồi gọi build(). Nested AddressDto được deserialize thành object trước khi truyền vào builder.

Nếu builder dùng withId(), withName() thì prefix phải khớp cấu hình @JsonPOJOBuilder. Mặc định Jackson thường kỳ vọng prefix with; ví dụ trên dùng withPrefix = "" để nhận tên method trực tiếp.

### 12.1. Builder cho generic immutable class

Generic builder có thể phức tạp hơn vì type parameter phải được giữ qua builder type và annotation. Khi thiết kế, cần bảo đảm builder và target type có cùng generic semantics.

Ví dụ minh họa:

~~~java
@JsonDeserialize(builder = Box.Builder.class)
public final class Box<T> {

    private final T value;

    private Box(Builder<T> builder) {
        this.value = builder.value;
    }

    public T getValue() {
        return value;
    }

    @JsonPOJOBuilder(withPrefix = "")
    public static class Builder<T> {
        private T value;

        public Builder<T> value(T value) {
            this.value = value;
            return this;
        }

        public Box<T> build() {
            return new Box<>(this);
        }
    }
}
~~~

Đọc:

~~~java
Box<UserDto> box = mapper.readValue(
    json,
    new TypeReference<Box<UserDto>>() {}
);
~~~

Với generic builder lồng nhau, hãy test đúng Jackson version và signature builder. Nếu annotation builder class không giữ được type parameter theo cách mong muốn, có thể cần custom deserializer hoặc creator-based immutable class đơn giản hơn.

## 13. Null, missing và default trong immutable model

Constructor-based binding phải truyền một giá trị cho từng tham số creator. Vì vậy, cần định nghĩa rõ behavior khi JSON thiếu property hoặc gửi null.

Ví dụ:

~~~java
public record SearchRequest(
    String query,
    Integer page,
    List<String> tags
) {}
~~~

Các input khác nhau:

~~~json
{"query": "jackson"}
~~~

~~~json
{"query": "jackson", "page": null}
~~~

~~~json
{"query": "jackson", "page": 0, "tags": []}
~~~

Ý nghĩa:

| Trạng thái | Khả năng trong Java |
|---|---|
| page missing | null hoặc creator default theo cấu hình |
| page explicit null | null với Integer |
| page = 0 | Integer có giá trị 0 |
| tags missing | Có thể null |
| tags = null | Null |
| tags = [] | Collection rỗng |

Nếu muốn default page = 1 khi missing, hãy thể hiện rõ trong constructor/builder hoặc tầng mapping. Không giả định Jackson tự áp default domain mong muốn.

### 13.1. Primitive hay wrapper?

Primitive int/boolean không thể giữ null. Wrapper Integer/Boolean có thể.

Với request DTO cần phân biệt missing/null/zero, wrapper thường phù hợp hơn. Nếu field bắt buộc, validate sau binding hoặc kiểm tra trong constructor.

Có thể bật FAIL_ON_NULL_FOR_PRIMITIVES để từ chối explicit null cho primitive. Nhưng feature này không tự giải quyết mọi trường hợp missing property; creator property requiredness cần được kiểm tra riêng.

### 13.2. Required creator property

Có thể dùng @JsonProperty(required = true) cho creator parameter trong các tình huống phù hợp:

~~~java
public record CreateUserRequest(
    @JsonProperty(value = "name", required = true)
    String name
) {}
~~~

Hãy kiểm thử behavior trên đúng Jackson version. Annotation required không thay thế validation đầy đủ và không nên được coi là cách duy nhất để bảo vệ invariant.

Một cách khác là kiểm tra trong compact constructor:

~~~java
public record CreateUserRequest(String name) {
    public CreateUserRequest {
        name = Objects.requireNonNull(name, "name is required");
        if (name.isBlank()) {
            throw new IllegalArgumentException("name must not be blank");
        }
    }
}
~~~

## 14. Validation của nested immutable DTO

Jackson chịu trách nhiệm parse và bind. Nó không tự thực hiện mọi business validation.

Có thể đặt constraint trên field/component:

~~~java
public record AddressDto(
    @NotBlank String street,
    @NotBlank String city
) {}

public record UserDto(
    @Positive long id,
    @NotBlank String name,
    @NotNull @Valid AddressDto address
) {}
~~~

@Valid cho phép validation đi sâu vào object con. Với collection:

~~~java
public record TeamDto(
    @NotBlank String name,
    @NotEmpty List<@Valid UserDto> members
) {}
~~~

Bean Validation cần được kích hoạt trong application flow, ví dụ qua @Valid trong Spring controller hoặc Validator được gọi rõ ràng. Jackson deserialize thành công không có nghĩa constraints đã chạy.

### 14.1. Phân biệt ba lớp lỗi

| Lớp | Ví dụ | Cách xử lý |
|---|---|---|
| Parse/binding | JSON sai cú pháp, string vào number | JsonProcessingException / mapping error |
| Model invariant | Constructor từ chối amount âm | Creator/instantiation error |
| Validation/business | City không được hỗ trợ, user không có quyền | Bean Validation hoặc service/domain rule |

Không bắt mọi lỗi rồi thay bằng DTO mặc định. Cần giữ nguyên lý do để API trả lỗi phù hợp.

## 15. Nested polymorphic object

Một object lồng nhau có thể là interface hoặc abstract class:

~~~java
public interface PaymentMethod {}

public record CardPayment(
    String lastFourDigits
) implements PaymentMethod {}

public record BankTransfer(
    String bankCode,
    String accountReference
) implements PaymentMethod {}
~~~

DTO:

~~~java
public record PaymentDto(
    String paymentId,
    PaymentMethod method
) {}
~~~

Jackson cần biết subtype cụ thể. Có thể khai báo logical type id:

~~~java
@JsonTypeInfo(
    use = JsonTypeInfo.Id.NAME,
    include = JsonTypeInfo.As.PROPERTY,
    property = "kind"
)
@JsonSubTypes({
    @JsonSubTypes.Type(value = CardPayment.class, name = "card"),
    @JsonSubTypes.Type(value = BankTransfer.class, name = "bank-transfer")
})
public interface PaymentMethod {}
~~~

JSON:

~~~json
{
  "paymentId": "pay-1",
  "method": {
    "kind": "card",
    "lastFourDigits": "1234"
  }
}
~~~

Generic wrapper có thể chứa object polymorphic:

~~~java
ApiResponse<PaymentDto> response = mapper.readValue(
    json,
    new TypeReference<ApiResponse<PaymentDto>>() {}
);
~~~

Generic type cho biết wrapper chứa PaymentDto; discriminator cho biết method là CardPayment hay BankTransfer.

Không dùng default typing rộng để giải quyết nested polymorphism từ input không tin cậy. Ưu tiên logical type id và subtype allowlist.

## 16. Generic inheritance và type variable resolution

Một số class dùng base generic:

~~~java
public abstract class PayloadHolder<T> {
    private final T payload;

    protected PayloadHolder(T payload) {
        this.payload = payload;
    }

    public T getPayload() {
        return payload;
    }
}
~~~

Subclass cố định kiểu:

~~~java
public final class UserPayloadHolder
        extends PayloadHolder<UserDto> {

    @JsonCreator
    public UserPayloadHolder(
        @JsonProperty("payload") UserDto payload
    ) {
        super(payload);
    }
}
~~~

Khi dùng subclass cụ thể, Jackson có thêm thông tin generic từ superclass signature. Nhưng nếu target là PayloadHolder.class, type variable T vẫn không xác định.

Với generic inheritance phức tạp, hãy:

- Cung cấp JavaType đầy đủ.
- Kiểm tra creator ở superclass/subclass.
- Tránh khai báo cùng một property ở nhiều tầng.
- Test raw base type và concrete subclass.
- Assert runtime type của payload.
- Kiểm tra behavior khi thay đổi generic hierarchy.

## 17. Annotation và naming strategy trong nested DTO

Một mapper có thể dùng SNAKE_CASE trong khi Java component dùng camelCase:

~~~java
ObjectMapper mapper = JsonMapper.builder()
    .propertyNamingStrategy(PropertyNamingStrategies.SNAKE_CASE)
    .build();
~~~

DTO:

~~~java
public record UserDto(
    long userId,
    String displayName,
    AddressDto primaryAddress
) {}
~~~

JSON dự kiến:

~~~json
{
  "user_id": 101,
  "display_name": "An",
  "primary_address": {
    "street": "12 Nguyen Trai",
    "city": "Ho Chi Minh City"
  }
}
~~~

Naming strategy áp dụng cho nested object theo mapper configuration. Nếu một property cần tên đặc biệt, có thể dùng @JsonProperty.

Test fixture phải phản ánh wire names thực tế, không chỉ tên component Java.

## 18. Serialization của generic và immutable DTO

Serialization thường lấy runtime value của property, nhưng declared type vẫn có thể ảnh hưởng đến polymorphic metadata, custom serializer và type-specific configuration.

Có thể tạo writer theo generic JavaType:

~~~java
JavaType responseType = mapper.getTypeFactory()
    .constructParametricType(ApiResponse.class, UserDto.class);

ObjectWriter writer = mapper.writerFor(responseType);

String json = writer.writeValueAsString(response);
~~~

Với nested generic:

~~~java
JavaType pageType = mapper.getTypeFactory()
    .constructParametricType(Page.class, UserDto.class);

JavaType responseType = mapper.getTypeFactory()
    .constructParametricType(ApiResponse.class, pageType);

ObjectWriter writer = mapper.writerFor(responseType);
~~~

Test serialization cần kiểm tra:

- Tên property ở mọi cấp.
- Object con được serialize đúng shape.
- Collection thành array.
- Generic payload không bị serialize thành dạng ngoài ý muốn.
- Null/missing inclusion policy.
- Type discriminator nếu có.
- BigDecimal/date/time formatting nếu contract có yêu cầu.

Đừng chỉ kiểm tra chuỗi JSON không rỗng. Parse output thành JsonNode và so sánh với fixture độc lập.

## 19. Dùng ObjectReader và ObjectWriter cho generic DTO

Có thể tạo reader/writer một lần theo JavaType:

~~~java
JavaType targetType = mapper.getTypeFactory()
    .constructParametricType(
        ApiResponse.class,
        mapper.getTypeFactory().constructType(UserDto.class)
    );

ObjectReader reader = mapper.readerFor(targetType);
ObjectWriter writer = mapper.writerFor(targetType);
~~~

Sau đó tái sử dụng:

~~~java
ApiResponse<UserDto> response = reader.readValue(json);
String output = writer.writeValueAsString(response);
~~~

Reader/Writer giữ target/source type và operation configuration. Chúng không thay thế mapper riêng nếu cần module hoặc JsonFactory khác.

Với mapper dùng chung trong Spring, tạo reader/writer sau khi mapper được cấu hình xong và không mutate mapper sau khi bắt đầu phục vụ request.

## 20. Kiểm thử contract bằng fixture độc lập

Round-trip:

~~~java
T source = sample();
String json = mapper.writeValueAsString(source);
T restored = mapper.readValue(json, targetType);
assertEquals(source, restored);
~~~

là test hữu ích nhưng không đủ. Serializer và deserializer có thể cùng mắc một giả định sai mà vẫn round-trip thành công.

Nên có ít nhất hai hướng kiểm thử độc lập:

1. Deserialize fixture JSON đã được review thành DTO và assert object graph.
2. Serialize DTO thành JSON rồi so sánh với fixture contract.

Ví dụ fixture:

~~~json
{
  "requestId": "req-100",
  "success": true,
  "data": {
    "page": 1,
    "size": 20,
    "totalElements": 1,
    "items": [
      {
        "id": 101,
        "name": "An",
        "address": {
          "street": "12 Nguyen Trai",
          "city": "Ho Chi Minh City"
        }
      }
    ]
  }
}
~~~

Test đọc:

~~~java
@Test
void readsPublishedNestedGenericFixture() throws Exception {
    ApiResponse<Page<UserDto>> response = mapper.readValue(
        readFixture("contracts/api-response-page-user.json"),
        new TypeReference<ApiResponse<Page<UserDto>>>() {}
    );

    assertEquals(101L, response.data().items().get(0).id());
    assertEquals(
        "Ho Chi Minh City",
        response.data().items().get(0).address().city()
    );
}
~~~

Fixture không nên được generate trong lúc test từ chính DTO đang được kiểm tra. Giữ JSON độc lập để thay đổi DTO không tự động thay đổi expected contract.

## 21. So sánh JsonNode thay vì JSON String nguyên văn

JSON object không phụ thuộc thứ tự property hoặc whitespace. So sánh String nguyên văn có thể fail dù cấu trúc và giá trị giống nhau.

Thay vào đó:

~~~java
JsonNode expected = mapper.readTree(expectedJson);
JsonNode actual = mapper.readTree(actualJson);

assertEquals(expected, actual);
~~~

JsonNode equality kiểm tra cấu trúc và giá trị. Với array, thứ tự phần tử vẫn có ý nghĩa.

Nếu BigDecimal scale là một phần contract, assert riêng:

~~~java
BigDecimal amount = actual
    .path("data")
    .path("total")
    .decimalValue();

assertEquals(new BigDecimal("125.50"), amount);
assertEquals(2, amount.scale());
~~~

Nếu chỉ quan tâm giá trị số mà không quan tâm scale, dùng compareTo():

~~~java
assertEquals(0, amount.compareTo(new BigDecimal("125.5")));
~~~

## 22. Test null, missing, empty và default lồng nhau

Một bộ fixture nên phân biệt:

| JSON | Điều cần kiểm tra |
|---|---|
| Không có address | Constructor có nhận null/default không? |
| address: null | Có bị từ chối hay chấp nhận? |
| address: {} | Object rỗng có tạo được không? |
| address.street: null | Component nested có invariant gì? |
| items không xuất hiện | Collection default là gì? |
| items: null | Có chấp nhận null collection? |
| items: [] | Collection rỗng có hợp lệ? |
| data: null | Generic payload có nullable không? |

Với immutable DTO, constructor thường là nơi thích hợp để bảo vệ invariant cơ bản. Tuy nhiên, default cho field optional cần được định nghĩa rõ và test riêng.

Không tự động đổi missing collection thành empty list nếu contract cần phân biệt hai trạng thái. Nếu model luôn yêu cầu collection non-null, có thể chuẩn hóa trong constructor nhưng phải ghi rõ semantics.

## 23. Test sai kiểu và lỗi ở object lồng nhau

Payload có thể đúng root shape nhưng sai kiểu ở sâu bên trong:

~~~json
{
  "data": {
    "items": [
      {
        "id": "not-a-number",
        "address": {
          "city": 123
        }
      }
    ]
  }
}
~~~

Test cần xác nhận mapper từ chối các property sai kiểu theo coercion policy.

Các lỗi nên có fixture:

- String vào long.
- Decimal vào integer.
- Object vào String.
- Array vào object.
- Nested object thiếu property bắt buộc.
- Generic element sai shape.
- Unknown discriminator.
- Collection chứa null element nếu không cho phép.
- Constructor invariant thất bại.
- Builder build() từ chối state không hợp lệ.

Không assert toàn bộ message nội bộ của Jackson nếu không cần. Hãy kiểm tra exception category hoặc map lỗi sang application error ổn định.

## 24. Test immutable state sau deserialize

Sau khi deserialize, test object không thể bị thay đổi ngoài ý muốn:

~~~java
@Test
void deserializedTeamKeepsImmutableMembers() throws Exception {
    TeamDto team = mapper.readValue(
        """
        {
          "name": "Engineering",
          "members": [
            {"id": 1, "name": "An", "address": {
              "street": "12 Nguyen Trai",
              "city": "Ho Chi Minh City"
            }}
          ]
        }
        """,
        TeamDto.class
    );

    assertThrows(
        UnsupportedOperationException.class,
        () -> team.members().clear()
    );
}
~~~

Nếu constructor chỉ gán trực tiếp mutable list được Jackson tạo, test có thể phát hiện collection chưa được bọc/copy đúng theo thiết kế.

Immutability cần xem xét cả object graph. Một record bất biến có thể chứa List mutable, Map mutable hoặc nested object mutable. Chỉ final field không làm toàn bộ graph bất biến.

## 25. Custom deserializer cho generic immutable type

Thông thường TypeReference/JavaType và creator là đủ. Chỉ dùng custom deserializer khi mapping có semantics đặc biệt mà annotation/creator không diễn đạt được.

Ví dụ một generic wrapper nhận JSON có hai dạng legacy khác nhau, hoặc cần chuyển một representation phức tạp thành immutable value object. Custom deserializer phải lấy contextual JavaType đúng và không được hard-code payload class nếu wrapper cần generic.

Với generic deserializer, cần chú ý:

- Contextualization theo BeanProperty.
- JavaType của target.
- Type parameter lồng nhau.
- Cache và thread-safety của deserializer.
- Không giữ parser hoặc request state trong field.
- Test nhiều payload type trên cùng mapper.
- Test nested generic type và null handling.

Không viết custom deserializer chỉ để tránh truyền TypeReference. Custom code làm tăng độ phức tạp và dễ làm mất type information nếu xử lý không đúng.

## 26. Spring integration cho immutable generic DTO

Trong Spring MVC, Jackson HttpMessageConverter có thể deserialize request body trực tiếp vào generic controller parameter khi framework giữ được generic method/parameter metadata.

Ví dụ:

~~~java
@PostMapping("/users/import")
ApiResponse<Page<UserDto>> importUsers(
        @RequestBody ApiResponse<Page<UserDto>> request) {
    return service.importUsers(request);
}
~~~

Framework thường sử dụng generic type metadata của method parameter để tạo JavaType phù hợp. Nhưng nếu code tự đọc body bằng ObjectMapper và chỉ truyền ApiResponse.class, generic payload sẽ bị mất.

Ví dụ cần tránh:

~~~java
ApiResponse response =
    objectMapper.readValue(body, ApiResponse.class);
~~~

Nếu tự xử lý body, hãy tạo JavaType hoặc dùng TypeReference đầy đủ.

### 26.1. Test qua HTTP adapter

Unit test mapper không xác nhận Spring converter đang dùng đúng mapper. Có thể dùng MockMvc/WebTestClient để gửi fixture JSON tới endpoint và kiểm tra request được bind thành nested immutable DTO.

Test cần xác nhận:

- Content-Type.
- Generic type ở controller parameter.
- Naming strategy.
- JavaTimeModule hoặc module bổ sung.
- Error response khi nested property sai kiểu.
- Validation sau binding.
- Unknown property/coercion policy.

## 27. Những lỗi thường gặp

| Lỗi | Nguyên nhân | Cách xử lý |
|---|---|---|
| Generic payload thành LinkedHashMap | Dùng raw Class | TypeReference hoặc JavaType |
| Generic lồng nhau bị mất kiểu | Chỉ khai báo outer generic | Truyền full nested type |
| TypeReference<T> trong generic helper không resolve T | Type erasure | Nhận Class/TypeReference/JavaType từ caller |
| Record không deserialize | Jackson version hoặc JDK không phù hợp | Kiểm tra record support và runtime |
| Immutable POJO không có creator | Không default constructor/setter | @JsonCreator và @JsonProperty |
| Constructor parameter bind sai | Thiếu property name metadata | @JsonProperty tường minh |
| Nested object thành Map | Generic/target type không đầy đủ | Khai báo nested DTO và full JavaType |
| Collection trong DTO vẫn mutable | Chỉ dùng final reference | Defensive copy |
| Missing và null bị nhầm | Model chỉ giữ nullable field | Presence model hoặc validation rõ |
| Primitive null thành default | Primitive không chứa null | Wrapper hoặc strict primitive null policy |
| Builder không nhận property | Prefix không khớp | Cấu hình @JsonPOJOBuilder |
| Polymorphic subtype không resolve | Thiếu discriminator/allowlist | Logical type id và subtype mapping |
| Round-trip pass nhưng contract sai | Hai chiều dùng cùng giả định | Fixture độc lập hai chiều |
| Test chỉ kiểm tra root object | Không phát hiện nested type sai | Assert sâu đến collection element |
| Mapper test khác Spring mapper | Khác module/configuration | Dùng mapper production và adapter test |
| Custom deserializer làm mất generic | Không dùng contextual JavaType | Lấy target JavaType và test nhiều type |

## 28. Quy trình thiết kế và kiểm thử

1. Vẽ object graph từ root đến nested DTO.
2. Đánh dấu class nào generic và type parameter của từng tầng.
3. Chọn record, constructor creator hoặc builder cho từng immutable type.
4. Dùng @JsonProperty rõ ràng cho creator parameter và component có wire name riêng.
5. Dùng TypeReference khi generic type đã biết tại compile time.
6. Dùng JavaType/TypeFactory khi type được tạo động.
7. Không dùng raw Class cho generic root nếu cần payload type cụ thể.
8. Defensive-copy List/Set/Map trong immutable model.
9. Quy định missing, null, empty và default cho mọi component quan trọng.
10. Đặt validation ở constructor, Bean Validation hoặc domain layer đúng trách nhiệm.
11. Dùng logical discriminator và subtype allowlist nếu có polymorphism.
12. Tạo fixture JSON độc lập với DTO implementation.
13. Test deserialize và serialize riêng.
14. Assert kiểu runtime của nested generic element và object con.
15. Test invalid shape, constructor invariant và collection mutability.
16. Test mapper/converter thực tế trong Spring.
17. Chạy lại contract tests khi thay Jackson version, annotation hoặc DTO hierarchy.

## 29. Nguyên tắc nên giữ

- Generic type cần thông tin đầy đủ ở runtime; raw Class thường không đủ.
- Dùng TypeReference cho kiểu lồng nhau đã biết tại compile time.
- Dùng JavaType/TypeFactory cho kiểu động.
- Generic helper phải nhận type information từ caller.
- DTO nested nên có kiểu cụ thể thay vì Map/Object nếu schema đã biết.
- Record được tạo qua canonical constructor.
- Immutable POJO dùng @JsonCreator và @JsonProperty khi cần property-based construction.
- Builder phải khai báo đúng @JsonDeserialize và @JsonPOJOBuilder.
- Generic wrapper cần cả creator đúng lẫn target generic type đầy đủ.
- Final collection reference không tự làm collection immutable; hãy defensive-copy.
- Phân biệt missing, explicit null, empty và default.
- Kiểm tra invariant ở nơi phù hợp, không nhầm binding với business validation.
- Dùng logical subtype id và allowlist cho nested polymorphism.
- Test sâu đến phần tử collection và object lồng nhau.
- Dùng fixture độc lập, không chỉ round-trip.
- Kiểm tra mapper production và Spring adapter thực tế.

Ánh xạ DTO bất biến có generic và đối tượng lồng nhau đòi hỏi Jackson phải biết đầy đủ type graph và cách tạo từng object. TypeReference hoặc JavaType bảo vệ generic parameter; record, @JsonCreator hoặc builder mô tả construction; defensive copy và validation bảo vệ state sau khi tạo. Khi test độc lập cả JSON contract, nested type, null/missing, constructor invariant và collection mutability, ứng dụng có thể dùng các DTO immutable phức tạp mà vẫn giữ được type safety và behavior ổn định.

