# Kiểm thử generic, record và mô hình bất biến

Jackson có thể serialize và deserialize nhiều kiểu Java khác nhau, nhưng generic, record và immutable model đặt ra những yêu cầu riêng cho quá trình binding. Generic type có thể bị mất thông tin khi chỉ truyền raw Class do Java type erasure; record không có setter và được tạo qua canonical constructor; immutable POJO thường dùng constructor hoặc builder thay vì cách khởi tạo rồi gán field.

Một test chỉ gọi writeValueAsString() rồi readValue() chưa đủ để chứng minh các mô hình này hoạt động đúng. Cần xác nhận Jackson hiểu đúng kiểu tham số generic, tạo đúng kiểu phần tử trong collection lồng nhau, ánh xạ tên component của record, gọi đúng constructor, giữ invariant và xử lý null/missing theo hợp đồng.

Bài học này tập trung vào cách thiết kế test có ý nghĩa cho ba nhóm mô hình đó. Các ví dụ dùng JUnit 5 và Jackson Databind; cấu hình mapper phải tương ứng với ứng dụng thực tế.

## 1. Vì sao generic cần được kiểm thử riêng?

Java generic cung cấp type safety ở thời điểm biên dịch. Nhưng do type erasure, thông tin tham số kiểu thường không còn tồn tại đầy đủ trong một đối tượng Class ở runtime.

Ví dụ:

~~~java
public class ApiResponse<T> {
    private boolean success;
    private T data;
    private List<String> errors;

    public ApiResponse() {
    }

    public boolean isSuccess() {
        return success;
    }

    public void setSuccess(boolean success) {
        this.success = success;
    }

    public T getData() {
        return data;
    }

    public void setData(T data) {
        this.data = data;
    }

    public List<String> getErrors() {
        return errors;
    }

    public void setErrors(List<String> errors) {
        this.errors = errors;
    }
}
~~~

Khi đọc JSON bằng:

~~~java
ApiResponse response =
    mapper.readValue(json, ApiResponse.class);
~~~

Jackson chỉ nhận ApiResponse.class. Nó không biết T phải là UserDto, OrderDto hay một kiểu cụ thể khác. Property data thường được bind thành kiểu untyped như LinkedHashMap, List hoặc scalar phù hợp với JSON.

Vì vậy, test generic phải truyền đầy đủ kiểu đích cho Jackson.

## 2. TypeReference cho generic đã biết tại thời điểm viết code

Jackson cung cấp TypeReference để giữ thông tin generic thông qua một anonymous subclass.

Ví dụ đọc ApiResponse<UserDto>:

~~~java
ApiResponse<UserDto> response = mapper.readValue(
    json,
    new TypeReference<ApiResponse<UserDto>>() {}
);
~~~

Đối với collection:

~~~java
List<UserDto> users = mapper.readValue(
    json,
    new TypeReference<List<UserDto>>() {}
);
~~~

Với generic lồng nhau:

~~~java
ApiResponse<List<UserDto>> response = mapper.readValue(
    json,
    new TypeReference<ApiResponse<List<UserDto>>>() {}
);
~~~

TypeReference giúp Jackson nhận được cấu trúc kiểu đầy đủ thay vì chỉ raw class.

### 2.1. Test generic container có phần tử đúng kiểu

Giả sử UserDto:

~~~java
public record UserDto(long id, String name) {}
~~~

JSON fixture:

~~~json
{
  "success": true,
  "data": {
    "id": 42,
    "name": "An"
  },
  "errors": []
}
~~~

Test:

~~~java
@Test
void readsGenericResponseWithConcretePayloadType() throws Exception {
    String json = """
        {
          "success": true,
          "data": {
            "id": 42,
            "name": "An"
          },
          "errors": []
        }
        """;

    ApiResponse<UserDto> response = mapper.readValue(
        json,
        new TypeReference<ApiResponse<UserDto>>() {}
    );

    assertTrue(response.isSuccess());
    assertInstanceOf(UserDto.class, response.getData());
    assertEquals(42L, response.getData().id());
    assertEquals("An", response.getData().name());
}
~~~

Assert instance type có ích vì nó phát hiện lỗi phổ biến: data được bind thành Map thay vì UserDto. Sau đó assert field để xác nhận semantics.

### 2.2. Test generic lồng collection

JSON:

~~~json
{
  "success": true,
  "data": [
    {"id": 1, "name": "An"},
    {"id": 2, "name": "Binh"}
  ],
  "errors": []
}
~~~

Test:

~~~java
@Test
void readsGenericResponseContainingList() throws Exception {
    ApiResponse<List<UserDto>> response = mapper.readValue(
        json,
        new TypeReference<ApiResponse<List<UserDto>>>() {}
    );

    assertEquals(2, response.getData().size());
    assertInstanceOf(UserDto.class, response.getData().get(0));
    assertEquals("Binh", response.getData().get(1).name());
}
~~~

Test cần đi sâu đến phần tử trong collection. Chỉ kiểm tra data không null hoặc size bằng 2 chưa chứng minh generic element type được giữ đúng.

### 2.3. Test Map lồng generic

Một payload có thể chứa Map với value là collection:

~~~java
Map<String, List<UserDto>> groups = mapper.readValue(
    json,
    new TypeReference<Map<String, List<UserDto>>>() {}
);
~~~

Hoặc generic wrapper chứa Map:

~~~java
ApiResponse<Map<String, UserDto>> response = mapper.readValue(
    json,
    new TypeReference<ApiResponse<Map<String, UserDto>>>() {}
);
~~~

Khi test, hãy assert cả key, số lượng phần tử và kiểu value. Điều này giúp phát hiện trường hợp Jackson bind thành Map<String, Object> lồng nhau thay vì kiểu cụ thể đã mong đợi.

## 3. Giới hạn của TypeReference trong generic method

TypeReference hoạt động tốt khi kiểu cụ thể được ghi trực tiếp tại nơi tạo anonymous subclass:

~~~java
new TypeReference<ApiResponse<UserDto>>() {}
~~~

Nhưng nếu tạo TypeReference bên trong một generic method:

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

T là type variable của method. Type erasure có nghĩa runtime không tự biết T đang là UserDto hay OrderDto. TypeReference này không tự giải quyết được kiểu cụ thể chỉ vì caller khai báo biến nhận là ApiResponse<UserDto>.

Đối với helper generic, hãy truyền Class<T> hoặc JavaType từ caller để tạo target type chính xác.

## 4. JavaType và TypeFactory cho kiểu generic động

Khi kiểu đích chỉ được biết lúc runtime, dùng TypeFactory để xây dựng JavaType.

Ví dụ:

~~~java
JavaType responseType = mapper.getTypeFactory()
    .constructParametricType(ApiResponse.class, UserDto.class);

ApiResponse<UserDto> response =
    mapper.readValue(json, responseType);
~~~

JavaType biểu diễn cấu trúc kiểu mà Jackson dùng trong databind. Nó có thể mô tả generic lồng nhau, collection, map và kiểu tham số phức tạp.

### 4.1. Helper generic nhận Class<T>

~~~java
static <T> ApiResponse<T> readResponse(
        ObjectMapper mapper,
        String json,
        Class<T> payloadClass) throws IOException {

    JavaType responseType = mapper.getTypeFactory()
        .constructParametricType(ApiResponse.class, payloadClass);

    return mapper.readValue(json, responseType);
}
~~~

Caller:

~~~java
ApiResponse<UserDto> response =
    readResponse(mapper, json, UserDto.class);
~~~

Helper này có thông tin runtime cần thiết để dựng ApiResponse<UserDto>.

### 4.2. Helper generic nhận JavaType

Class<T> không đủ để mô tả mọi kiểu. Ví dụ payload type là List<UserDto> hoặc Map<String, UserDto>. Khi đó, nhận JavaType:

~~~java
static <T> ApiResponse<T> readResponse(
        ObjectMapper mapper,
        String json,
        JavaType payloadType) throws IOException {

    JavaType responseType = mapper.getTypeFactory()
        .constructParametricType(ApiResponse.class, payloadType);

    return mapper.readValue(json, responseType);
}
~~~

Tạo kiểu List<UserDto>:

~~~java
JavaType userListType = mapper.getTypeFactory()
    .constructCollectionType(List.class, UserDto.class);

ApiResponse<List<UserDto>> response =
    readResponse(mapper, json, userListType);
~~~

Tạo kiểu Map<String, UserDto>:

~~~java
JavaType userMapType = mapper.getTypeFactory()
    .constructMapType(
        Map.class,
        String.class,
        UserDto.class
    );
~~~

JavaType giúp tránh phải viết một helper riêng cho từng tổ hợp generic.

### 4.3. Dùng constructParametricType cho generic lồng nhau

Có thể kết hợp JavaType:

~~~java
TypeFactory typeFactory = mapper.getTypeFactory();

JavaType userType = typeFactory.constructType(UserDto.class);

JavaType userListType = typeFactory.constructCollectionType(
    List.class,
    userType
);

JavaType responseType = typeFactory.constructParametricType(
    ApiResponse.class,
    userListType
);
~~~

Cách xây dựng từng tầng giúp code rõ ràng khi kiểu có nhiều cấp. Nếu generic type đã biết cố định trong source, TypeReference thường ngắn gọn hơn.

## 5. Test raw type để phát hiện mất generic

Một test hữu ích là chứng minh vì sao không nên dùng raw class:

~~~java
@Test
void rawResponseClassDoesNotPreservePayloadType() throws Exception {
    ApiResponse response = mapper.readValue(
        json,
        ApiResponse.class
    );

    assertInstanceOf(Map.class, response.getData());
}
~~~

Test này mô tả hành vi untyped của cấu hình ví dụ. Với payload scalar hoặc array, kiểu runtime của data sẽ khác. Mục tiêu là nhận ra rằng raw ApiResponse.class không giữ UserDto.

Trong code production, tránh ép cast:

~~~java
UserDto user = (UserDto) response.getData();
~~~

Cast có thể chỉ thất bại ở runtime hoặc che giấu việc binding sai. Hãy cung cấp JavaType hoặc TypeReference đầy đủ từ đầu.

## 6. Serialization của generic type

Serialization thường có thể nhìn thấy runtime value của property, nhưng generic root type vẫn có thể quan trọng, đặc biệt khi dùng polymorphic type metadata, custom serializer hoặc declared type-specific configuration.

Ví dụ tạo writer theo JavaType:

~~~java
JavaType responseType = mapper.getTypeFactory()
    .constructParametricType(ApiResponse.class, UserDto.class);

ObjectWriter writer = mapper.writerFor(responseType);

String json = writer.writeValueAsString(response);
~~~

Hoặc dùng TypeReference khi kiểu đã biết:

~~~java
ObjectWriter writer = mapper.writerFor(
    new TypeReference<ApiResponse<UserDto>>() {}
);
~~~

Test serialization nên kiểm tra:

- Property name theo contract.
- Payload data có đúng shape.
- Collection được ghi thành array.
- Null/missing/inclusion theo cấu hình.
- Type discriminator nếu có polymorphism.
- Custom serializer có nhận đúng declared type không.

Đừng chỉ assert JSON không rỗng. Parse lại thành JsonNode rồi so sánh với fixture hoặc assert các property quan trọng.

## 7. Generic record

Record có thể khai báo type parameter giống class thông thường:

~~~java
public record ApiResult<T>(
    boolean success,
    T data,
    List<String> errors
) {}
~~~

Jackson có thể deserialize record generic nếu target type đầy đủ:

~~~java
ApiResult<UserDto> result = mapper.readValue(
    json,
    new TypeReference<ApiResult<UserDto>>() {}
);
~~~

Với list:

~~~java
ApiResult<List<UserDto>> result = mapper.readValue(
    json,
    new TypeReference<ApiResult<List<UserDto>>>() {}
);
~~~

Record không làm mất vấn đề type erasure. TypeReference hoặc JavaType vẫn cần thiết khi đọc generic record.

### 7.1. Test generic record

~~~java
@Test
void readsGenericRecordWithConcreteType() throws Exception {
    ApiResult<UserDto> result = mapper.readValue(
        """
        {
          "success": true,
          "data": {"id": 7, "name": "Lan"},
          "errors": []
        }
        """,
        new TypeReference<ApiResult<UserDto>>() {}
    );

    assertTrue(result.success());
    assertEquals(7L, result.data().id());
    assertEquals("Lan", result.data().name());
}
~~~

Record cung cấp accessor theo tên component, ví dụ data() thay vì getData(). Test nên dùng đúng accessor và kiểm tra kiểu phần tử thực tế.

## 8. Jackson hỗ trợ record từ phiên bản nào?

Jackson Databind hỗ trợ Java record từ dòng 2.12. Record yêu cầu Java runtime/compiler hỗ trợ record; record trở thành tính năng ổn định từ Java 16. Các phiên bản Java sớm hơn có thể đã có preview support, nhưng không nên lấy preview behavior làm baseline cho ứng dụng mới.

Khi dự án dùng record:

- Kiểm tra phiên bản jackson-databind.
- Kiểm tra Java source/target/release level.
- Đồng bộ jackson-core, annotations và databind.
- Kiểm tra module bổ sung như JavaTimeModule.
- Chạy test trên đúng JDK và dependency set production.

Nếu dùng Jackson cũ hơn khả năng hỗ trợ record, hãy nâng cấp lên version phù hợp hoặc dùng immutable POJO với @JsonCreator. Không giả định record sẽ hoạt động giống nhau với mọi version Jackson.

## 9. Binding record qua canonical constructor

Record là immutable theo cấu trúc: component được khai báo trong header, field được tạo final và không có setter thông thường.

Ví dụ:

~~~java
public record UserRecord(
    long id,
    String name,
    boolean active
) {}
~~~

Jackson tạo record qua canonical constructor:

~~~java
new UserRecord(id, name, active)
~~~

Không cần constructor mặc định hoặc setter. Jackson đọc tên component và giá trị tương ứng rồi gọi constructor.

Test:

~~~java
@Test
void deserializesRecordThroughCanonicalConstructor() throws Exception {
    UserRecord user = mapper.readValue(
        """
        {
          "id": 10,
          "name": "An",
          "active": true
        }
        """,
        UserRecord.class
    );

    assertEquals(10L, user.id());
    assertEquals("An", user.name());
    assertTrue(user.active());
}
~~~

Nếu record có compact constructor hoặc canonical constructor tùy chỉnh, logic validation/normalization trong constructor cũng được thực thi khi Jackson tạo object.

### 9.1. Record component và JSON property name

Có thể dùng @JsonProperty trên component:

~~~java
public record UserRecord(
    @JsonProperty("user_id") long id,
    @JsonProperty("display_name") String name,
    boolean active
) {}
~~~

JSON:

~~~json
{
  "user_id": 10,
  "display_name": "An",
  "active": true
}
~~~

Test cả chiều ghi và chiều đọc để bảo vệ tên contract:

~~~java
@Test
void usesExplicitRecordPropertyNames() throws Exception {
    UserRecord user = new UserRecord(10L, "An", true);

    JsonNode json = mapper.readTree(
        mapper.writeValueAsString(user)
    );

    assertTrue(json.has("user_id"));
    assertTrue(json.has("display_name"));
    assertFalse(json.has("id"));
}
~~~

Nếu mapper có naming strategy, cần test tên cuối cùng khi annotation và strategy cùng áp dụng.

### 9.2. Khi nào cần @JsonCreator?

Với record tiêu chuẩn và Jackson version hỗ trợ record, canonical constructor thường được nhận diện tự động. Không cần thêm @JsonCreator chỉ để record deserialize được.

@JsonCreator có thể cần khi có nhiều constructor/factory hoặc muốn chọn creator cụ thể. Khi dùng creator property-based, khai báo tên property rõ ràng bằng @JsonProperty nếu Jackson không thể suy luận chắc chắn.

Không thêm annotation dư thừa nếu canonical record mapping đã rõ; giữ mô hình đơn giản giúp tránh cấu hình creator mâu thuẫn.

## 10. Compact constructor và invariant của record

Record có thể xác thực dữ liệu ngay trong compact constructor:

~~~java
public record PageRequest(int page, int size) {
    public PageRequest {
        if (page < 0) {
            throw new IllegalArgumentException("page must be non-negative");
        }
        if (size < 1 || size > 200) {
            throw new IllegalArgumentException("size must be between 1 and 200");
        }
    }
}
~~~

Jackson gọi canonical constructor khi deserialize. Vì vậy, payload có page hoặc size không hợp lệ có thể khiến quá trình binding thất bại. Jackson thường bọc lỗi khởi tạo trong exception thuộc nhóm ValueInstantiationException/JsonMappingException.

Test hợp lệ:

~~~java
@Test
void createsPageRequestWithValidValues() throws Exception {
    PageRequest request = mapper.readValue(
        "{\"page\":0,\"size\":20}",
        PageRequest.class
    );

    assertEquals(0, request.page());
    assertEquals(20, request.size());
}
~~~

Test không hợp lệ:

~~~java
@Test
void rejectsInvalidPageRequest() {
    assertThrows(JsonMappingException.class, () ->
        mapper.readValue(
            "{\"page\":-1,\"size\":20}",
            PageRequest.class
        )
    );
}
~~~

Nếu muốn phân biệt lỗi JSON binding với lỗi validation nghiệp vụ, cân nhắc không ném exception nghiệp vụ quá phức tạp trong constructor. Constructor nên bảo vệ invariant cơ bản của value object; validation phụ thuộc database, user permission hoặc trạng thái hệ thống nên nằm ở service/domain layer.

## 11. Null và missing trong record

Record component có thể là reference type hoặc primitive:

~~~java
public record UserInput(
    String nickname,
    Integer age,
    boolean active
) {}
~~~

Với reference component, JSON null có thể trở thành Java null. Với primitive component, null không thể được lưu trực tiếp; Jackson có thể dùng default primitive hoặc từ chối tùy cấu hình.

Có thể bật:

~~~java
ObjectMapper strictMapper = JsonMapper.builder()
    .enable(DeserializationFeature.FAIL_ON_NULL_FOR_PRIMITIVES)
    .build();
~~~

Test null primitive:

~~~java
@Test
void rejectsNullForPrimitiveRecordComponentWhenStrict() {
    assertThrows(JsonProcessingException.class, () ->
        strictMapper.readValue(
            """
            {"nickname": null, "age": 20, "active": null}
            """,
            UserInput.class
        )
    );
}
~~~

Missing component và explicit null cũng cần được xem xét riêng. Nếu component reference không xuất hiện, giá trị được truyền vào constructor có thể là null hoặc default theo creator binding. Nếu nghiệp vụ cần phân biệt hai trạng thái, dùng wrapper/presence model hoặc custom deserializer thay vì giả định record tự giữ được sự khác biệt.

### 11.1. Required property và primitive

Nếu component bắt buộc, có thể dùng @JsonProperty(required = true) trong các trường hợp creator-based binding phù hợp, nhưng cần kiểm thử đúng version và cấu hình. Không coi annotation này là thay thế cho validation mọi trường hợp.

Một lựa chọn khác là kiểm tra trong compact constructor:

~~~java
public record CreateUser(String name) {
    public CreateUser {
        Objects.requireNonNull(name, "name is required");
    }
}
~~~

Test payload thiếu name và payload name null để xác nhận lỗi được phát hiện theo mong đợi.

## 12. Record generic lồng nhau

Một record có thể chứa generic record hoặc collection:

~~~java
public record Page<T>(
    List<T> items,
    int page,
    int size,
    long totalElements
) {}
~~~

~~~java
public record ApiResult<T>(
    boolean success,
    T data
) {}
~~~

Đọc ApiResult<Page<UserRecord>>:

~~~java
ApiResult<Page<UserRecord>> result = mapper.readValue(
    json,
    new TypeReference<ApiResult<Page<UserRecord>>>() {}
);
~~~

Test cần kiểm tra:

~~~java
assertEquals(2, result.data().items().size());
assertInstanceOf(UserRecord.class, result.data().items().get(0));
assertEquals("An", result.data().items().get(0).name());
~~~

Kết hợp generic và record làm rõ hai vấn đề độc lập: record cần constructor binding đúng; generic cần type information đầy đủ. Test nên kiểm tra cả hai thay vì chỉ assert object root đã được tạo.

## 13. Immutable POJO với final fields

Không phải dự án nào cũng dùng record. Có thể cần class bất biến vì:

- Hỗ trợ Java version chưa có record.
- Cần inheritance hoặc API class hiện hữu.
- Cần custom construction.
- Cần tương thích thư viện hoặc framework.
- Cần kiểm soát cách tạo object.

Ví dụ:

~~~java
public final class Money {

    private final BigDecimal amount;
    private final String currency;

    @JsonCreator(mode = JsonCreator.Mode.PROPERTIES)
    public Money(
        @JsonProperty("amount") BigDecimal amount,
        @JsonProperty("currency") String currency
    ) {
        this.amount = Objects.requireNonNull(amount);
        this.currency = Objects.requireNonNull(currency);

        if (amount.signum() < 0) {
            throw new IllegalArgumentException("amount must be non-negative");
        }
        if (currency.isBlank()) {
            throw new IllegalArgumentException("currency is required");
        }
    }

    public BigDecimal getAmount() {
        return amount;
    }

    public String getCurrency() {
        return currency;
    }
}
~~~

Không có setter. Jackson gọi constructor được đánh dấu @JsonCreator và gán giá trị thông qua các tham số có tên @JsonProperty.

### 13.1. Vì sao cần @JsonCreator và @JsonProperty?

Với immutable class có nhiều constructor hoặc không có default constructor, Jackson cần biết constructor/factory nào dùng để tạo object và JSON property nào ánh xạ vào từng tham số.

@JsonCreator(mode = PROPERTIES) nói rằng các tham số constructor được bind theo tên property. @JsonProperty cung cấp tên tường minh.

Không dựa vào tên tham số Java nếu build không bảo đảm metadata parameter names hoặc mapper không được cấu hình module phù hợp. Annotation rõ ràng làm contract ổn định hơn.

### 13.2. Test constructor binding

~~~java
@Test
void deserializesImmutablePojoThroughCreator() throws Exception {
    Money money = mapper.readValue(
        """
        {
          "amount": 125.50,
          "currency": "VND"
        }
        """,
        Money.class
    );

    assertEquals(new BigDecimal("125.50"), money.getAmount());
    assertEquals("VND", money.getCurrency());
}
~~~

Test không chỉ xác nhận JSON đọc được mà còn xác nhận constructor tạo ra state đúng.

### 13.3. Test invariant của immutable class

~~~java
@Test
void rejectsNegativeMoneyAmount() {
    assertThrows(JsonMappingException.class, () ->
        mapper.readValue(
            """
            {"amount": -1, "currency": "VND"}
            """,
            Money.class
        )
    );
}
~~~

Nếu constructor ném IllegalArgumentException, Jackson thường bọc nó trong lỗi mapping. Khi cần kiểm tra cause cụ thể, xem root cause nhưng tránh phụ thuộc message nội bộ không ổn định.

## 14. Constructor parameter names và ParameterNamesModule

Một số ứng dụng muốn dùng tên tham số constructor thay cho @JsonProperty ở mọi tham số. Jackson có thể sử dụng metadata parameter names khi class được biên dịch với thông tin tên tham số và cấu hình/module tương ứng.

Ví dụ module:

~~~java
ObjectMapper mapper = JsonMapper.builder()
    .addModule(new ParameterNamesModule())
    .build();
~~~

Build cũng cần giữ parameter name metadata, thường bằng compiler option -parameters cho Java compiler. Chi tiết cấu hình phụ thuộc Maven/Gradle và toolchain.

Dù có thể giảm annotation, việc dựa vào tên tham số làm mapping phụ thuộc build configuration. Với contract public hoặc immutable model quan trọng, @JsonProperty tường minh thường dễ review và ít bất ngờ hơn.

Test phải chạy trên artifact được biên dịch bằng đúng cấu hình production. Test chạy trong IDE với metadata khác có thể che giấu lỗi xảy ra sau khi đóng gói.

## 15. Immutable model dùng builder

Một số class bất biến có builder thay vì constructor dài. Jackson có thể deserialize qua builder với @JsonDeserialize và @JsonPOJOBuilder.

Ví dụ:

~~~java
@JsonDeserialize(builder = ServerConfig.Builder.class)
public final class ServerConfig {

    private final String host;
    private final int port;

    private ServerConfig(Builder builder) {
        this.host = Objects.requireNonNull(builder.host);
        this.port = builder.port;
    }

    public String getHost() {
        return host;
    }

    public int getPort() {
        return port;
    }

    @JsonPOJOBuilder(withPrefix = "")
    public static class Builder {
        private String host;
        private int port;

        public Builder host(String host) {
            this.host = host;
            return this;
        }

        public Builder port(int port) {
            this.port = port;
            return this;
        }

        public ServerConfig build() {
            if (port < 1 || port > 65535) {
                throw new IllegalArgumentException("Invalid port");
            }
            return new ServerConfig(this);
        }
    }
}
~~~

@JsonDeserialize(builder = ...) chỉ định builder dùng cho quá trình đọc. @JsonPOJOBuilder(withPrefix = "") nói rằng method builder tên host() và port() tương ứng property host và port, thay vì mặc định tìm method có prefix with.

Nếu builder dùng withHost()/withPort(), cấu hình prefix phù hợp hoặc giữ convention mặc định.

### 15.1. Test builder-based deserialization

~~~java
@Test
void deserializesImmutableModelThroughBuilder() throws Exception {
    ServerConfig config = mapper.readValue(
        """
        {"host":"localhost","port":8080}
        """,
        ServerConfig.class
    );

    assertEquals("localhost", config.getHost());
    assertEquals(8080, config.getPort());
}
~~~

Test lỗi:

~~~java
@Test
void rejectsInvalidBuilderState() {
    assertThrows(JsonMappingException.class, () ->
        mapper.readValue(
            """
            {"host":"localhost","port":70000}
            """,
            ServerConfig.class
        )
    );
}
~~~

Kiểm tra cả builder method mapping, default value, required field và validation ở build(). Nếu builder tự gán default cho field bị thiếu, test cần xác nhận đó là semantics mong muốn.

## 16. Bảo vệ collection trong immutable model

Final reference không đồng nghĩa collection bất biến. Ví dụ:

~~~java
private final List<String> roles;
~~~

Reference roles không thể trỏ sang List khác sau khi constructor kết thúc, nhưng List bên trong vẫn có thể thay đổi nếu caller giữ reference mutable.

Constructor nên tạo defensive copy:

~~~java
public UserPermissions(List<String> roles) {
    this.roles = List.copyOf(roles);
}
~~~

Record cũng cần lưu ý điều này:

~~~java
public record UserPermissions(List<String> roles) {
    public UserPermissions {
        roles = List.copyOf(roles);
    }
}
~~~

List.copyOf() tạo collection không thể sửa qua reference trả về và từ chối null collection/element theo contract của API. Nếu null hoặc null element được phép, cần chính sách copy phù hợp.

Test:

~~~java
@Test
void immutableModelDefensivelyCopiesList() {
    List<String> source = new ArrayList<>(List.of("READ"));

    UserPermissions permissions = new UserPermissions(source);
    source.add("ADMIN");

    assertEquals(List.of("READ"), permissions.roles());
    assertThrows(
        UnsupportedOperationException.class,
        () -> permissions.roles().add("WRITE")
    );
}
~~~

Test này là kiểm thử tính bất biến của model Java, bổ sung cho test Jackson. Deserialize thành công không tự chứng minh collection đã được defensive copy.

## 17. Generic immutable class

Generic type có thể kết hợp với immutable constructor:

~~~java
public final class Result<T> {

    private final T value;
    private final String requestId;

    @JsonCreator(mode = JsonCreator.Mode.PROPERTIES)
    public Result(
        @JsonProperty("value") T value,
        @JsonProperty("requestId") String requestId
    ) {
        this.value = value;
        this.requestId = requestId;
    }

    public T getValue() {
        return value;
    }

    public String getRequestId() {
        return requestId;
    }
}
~~~

Khi deserialize, phải cung cấp kiểu tham số:

~~~java
Result<UserDto> result = mapper.readValue(
    json,
    new TypeReference<Result<UserDto>>() {}
);
~~~

Nếu dùng Result.class, T có thể trở thành Object và object value có thể được bind thành Map.

Test generic immutable model nên xác nhận cả constructor binding và concrete payload type:

~~~java
@Test
void readsGenericImmutableResult() throws Exception {
    Result<UserDto> result = mapper.readValue(
        """
        {
          "requestId": "req-1",
          "value": {"id": 9, "name": "Mai"}
        }
        """,
        new TypeReference<Result<UserDto>>() {}
    );

    assertInstanceOf(UserDto.class, result.getValue());
    assertEquals(9L, result.getValue().id());
}
~~~

## 18. @JsonProperty, @JsonAlias và naming strategy

Generic, record và immutable model vẫn chịu ảnh hưởng của quy tắc tên property.

Ví dụ:

~~~java
public record CustomerRecord(
    @JsonProperty("customer_id") long id,
    @JsonAlias("displayName") String name
) {}
~~~

@JsonProperty xác định tên chính được dùng trong mapping. @JsonAlias cho phép nhận thêm tên cũ khi deserialize; alias không nhất thiết được dùng khi serialize.

Nếu mapper dùng SNAKE_CASE, hãy kiểm tra tên cuối cùng. Không giả định annotation, alias và global naming strategy luôn kết hợp theo cách trực giác.

Test cả payload mới và legacy:

~~~java
@Test
void acceptsLegacyAliasAndWritesCanonicalName() throws Exception {
    CustomerRecord customer = mapper.readValue(
        """
        {"customer_id": 1, "displayName": "An"}
        """,
        CustomerRecord.class
    );

    JsonNode output = mapper.readTree(
        mapper.writeValueAsString(customer)
    );

    assertTrue(output.has("customer_id"));
    assertTrue(output.has("name"));
    assertFalse(output.has("displayName"));
}
~~~

Tên mong đợi trong test phải khớp cấu hình mapper thực tế. Nếu dùng naming strategy, điều chỉnh expected contract theo tên cuối cùng đã công bố.

## 19. Generic type và polymorphism

Generic container có thể chứa base type hoặc interface:

~~~java
public interface DomainEvent {}

public record UserCreated(String userId) implements DomainEvent {}
public record UserDeleted(String userId, String reason) implements DomainEvent {}
~~~

Một container:

~~~java
public record EventBatch<T>(
    String batchId,
    List<T> events
) {}
~~~

Nếu T là DomainEvent, consumer cần type metadata hoặc một cách lựa chọn subtype rõ ràng. Có thể dùng logical type id với @JsonTypeInfo trên base type và khai báo subtype allowlist.

~~~java
@JsonTypeInfo(
    use = JsonTypeInfo.Id.NAME,
    include = JsonTypeInfo.As.PROPERTY,
    property = "eventType"
)
@JsonSubTypes({
    @JsonSubTypes.Type(value = UserCreated.class, name = "user-created"),
    @JsonSubTypes.Type(value = UserDeleted.class, name = "user-deleted")
})
public interface DomainEvent {}
~~~

Test:

~~~java
EventBatch<DomainEvent> batch = mapper.readValue(
    json,
    new TypeReference<EventBatch<DomainEvent>>() {}
);
~~~

Assert từng subtype:

~~~java
assertInstanceOf(UserCreated.class, batch.events().get(0));
assertInstanceOf(UserDeleted.class, batch.events().get(1));
~~~

Generic type information cho biết collection chứa DomainEvent; polymorphic metadata cho biết mỗi phần tử cụ thể là subtype nào. Hai cơ chế bổ sung cho nhau.

Không bật default typing rộng chỉ để giải quyết generic polymorphism. Ưu tiên logical type id và subtype được phép rõ ràng, nhất là với input không tin cậy.

## 20. Optional và generic wrapper

Nếu model dùng Optional<T>, Jackson cần module JDK 8:

~~~java
ObjectMapper mapper = JsonMapper.builder()
    .addModule(new Jdk8Module())
    .build();
~~~

Ví dụ:

~~~java
public record UserPreferences(Optional<String> nickname) {}
~~~

Test cần xác định semantics của Optional.empty(), Optional.of(value), field missing và explicit null. Tùy inclusion/deserialization configuration, các trường hợp này có thể được biểu diễn khác nhau.

Với generic Optional trực tiếp:

~~~java
Optional<UserDto> user = mapper.readValue(
    json,
    new TypeReference<Optional<UserDto>>() {}
);
~~~

Hãy dùng module tương thích với Jackson version và test bằng mapper production. Không giả định Optional tự hoạt động giống String nullable khi chưa đăng ký module.

## 21. Test serialization và deserialization độc lập

Một round-trip test:

~~~java
T source = sample();

String json = mapper.writeValueAsString(source);

T restored = mapper.readValue(json, targetType);

assertEquals(source, restored);
~~~

có thể phát hiện lỗi cơ bản, nhưng chưa đủ. Serializer và deserializer có thể cùng sai theo một cách nhất quán.

Nên có các test riêng:

1. Serialize model thành JSON và so với fixture hợp đồng.
2. Deserialize fixture JSON độc lập thành model và assert giá trị.
3. Test invalid payload và invariant.
4. Test generic type được resolve đúng.
5. Test model immutable không bị thay đổi ngoài ý muốn.

Fixture độc lập nên được lưu trong src/test/resources và không được tạo tự động từ DTO đang kiểm tra mỗi lần test chạy.

## 22. So sánh JsonNode để kiểm tra JSON contract

Không nên so sánh JSON String nguyên văn nếu whitespace và thứ tự object property không thuộc hợp đồng:

~~~java
assertEquals(expectedJson, actualJson);
~~~

Thay vào đó, parse cả hai:

~~~java
JsonNode expected = mapper.readTree(expectedJson);
JsonNode actual = mapper.readTree(actualJson);

assertEquals(expected, actual);
~~~

Object property order không cần giống nhau; array element order vẫn có ý nghĩa. Với decimal, JsonNode numeric equality và BigDecimal scale cần được cân nhắc theo contract. Nếu scale là yêu cầu, assert decimalValue().scale() riêng.

Ví dụ:

~~~java
assertEquals(
    new BigDecimal("12.50"),
    actual.path("amount").decimalValue()
);
assertEquals(2, actual.path("amount").decimalValue().scale());
~~~

Nếu chỉ quan tâm giá trị số, dùng compareTo() thay vì equals() của BigDecimal:

~~~java
assertEquals(
    0,
    actual.path("amount").decimalValue()
        .compareTo(new BigDecimal("12.5"))
);
~~~

## 23. Test generic collection và map bằng JavaType

Khi kiểu được tạo động, test helper TypeFactory riêng:

~~~java
@Test
void readsDynamicGenericType() throws Exception {
    JavaType listType = mapper.getTypeFactory()
        .constructCollectionType(List.class, UserDto.class);

    JavaType responseType = mapper.getTypeFactory()
        .constructParametricType(ApiResponse.class, listType);

    ApiResponse<List<UserDto>> response =
        mapper.readValue(json, responseType);

    assertEquals(2, response.getData().size());
    assertInstanceOf(UserDto.class, response.getData().get(0));
}
~~~

Với Map:

~~~java
JavaType mapType = mapper.getTypeFactory()
    .constructMapType(Map.class, String.class, UserDto.class);
~~~

Khi test helper nhận JavaType, cần xác nhận caller truyền đúng kiểu nested. Nếu helper chỉ nhận Class<T>, nó không thể tự suy ra mọi cấu trúc generic lồng nhau.

## 24. Test unknown properties và version compatibility

Generic, record và immutable model có thể phản ứng khác nhau với property không biết tùy mapper configuration và annotation.

Nếu mapper strict, payload có field mới có thể fail. Nếu mapper tolerant, field đó có thể bị bỏ qua. Nếu dùng extension map hoặc @JsonAnySetter, có thể giữ field động.

Test rõ chính sách:

~~~java
@Test
void rejectsUnknownFieldWhenStrict() {
    assertThrows(JsonProcessingException.class, () ->
        strictMapper.readValue(
            """
            {"id": 1, "name": "An", "newField": true}
            """,
            UserRecord.class
        )
    );
}
~~~

Với model cần backward compatibility, có thể dùng @JsonIgnoreProperties(ignoreUnknown = true) hoặc mapper riêng. Đừng tắt strict globally chỉ để một DTO tolerant hơn.

## 25. Test null, missing và constructor invariants

Các trường hợp nên có fixture/test riêng:

| Trường hợp | Điều cần xác nhận |
|---|---|
| Field có giá trị | Constructor nhận đúng giá trị |
| Field missing | Default hoặc lỗi theo contract |
| Field explicit null | Null được chấp nhận hay từ chối |
| Primitive null | Fail hoặc default theo cấu hình |
| Collection null | Null, empty hay từ chối |
| Collection rỗng | Giữ empty collection |
| Generic payload null | T có thể null theo contract không |
| Constructor invariant fail | Binding trả lỗi rõ ràng |
| Builder field missing | Builder default có đúng không |

Đừng để constructor tự đặt default không được tài liệu hóa. Ví dụ missing size được đổi thành 20 có thể hữu ích, nhưng consumer phải biết đây là default hợp đồng.

## 26. Test record và immutable model qua nhiều mapper configuration

Ứng dụng có thể có nhiều mapper:

- JSON mapper cho REST.
- CBOR/Smile mapper cho message.
- YAMLMapper cho file cấu hình.
- Mapper strict cho input bên ngoài.
- Mapper tolerant cho payload legacy.

Record và immutable model cần được test với đúng mapper sẽ dùng. Cùng một DTO có thể có kết quả khác nếu mapper thiếu JavaTimeModule, Jdk8Module hoặc naming strategy khác nhau.

Không cần nhân bản toàn bộ test cho mọi mapper nếu contract giống nhau và factory configuration dùng chung. Nhưng mọi mapper production có behavior khác nhau cần có test bảo vệ khác biệt đó.

## 27. Test lỗi constructor và builder

Jackson thường bọc exception do constructor/builder ném ra trong JsonMappingException hoặc subtype. Test nên xác nhận payload bị từ chối:

~~~java
@Test
void rejectsInvalidImmutableObject() {
    assertThrows(JsonMappingException.class, () ->
        mapper.readValue(
            """
            {"amount": -10, "currency": "VND"}
            """,
            Money.class
        )
    );
}
~~~

Nếu cần kiểm tra root cause:

~~~java
JsonMappingException exception = assertThrows(
    JsonMappingException.class,
    () -> mapper.readValue(json, Money.class)
);

assertNotNull(exception.getCause());
~~~

Không assert toàn bộ exception message nếu không cần; message có thể thay đổi giữa các phiên bản. Ở tầng API, chuyển lỗi thành mã và field path ổn định.

## 28. Bộ test mẫu cho generic, record và immutable class

Một test suite có thể chia theo trách nhiệm:

~~~text
src/test/java/
  GenericBindingTest.java
  GenericSerializationTest.java
  RecordBindingTest.java
  ImmutableCreatorTest.java
  ImmutableBuilderTest.java
  GenericRecordTest.java
  ContractFixtureTest.java
  MapperConfigurationTest.java

src/test/resources/
  contracts/
    api-response-user.json
    api-response-user-list.json
    page-of-users.json
    immutable-money.json
    invalid-money-negative.json
    record-missing-required-field.json
~~~

Các test nên tập trung:

- GenericBindingTest: TypeReference, JavaType, raw type failure mode.
- GenericSerializationTest: writer type và JSON shape.
- RecordBindingTest: canonical constructor, component naming, null/missing.
- ImmutableCreatorTest: @JsonCreator và @JsonProperty.
- ImmutableBuilderTest: @JsonDeserialize và @JsonPOJOBuilder.
- GenericRecordTest: generic type lồng trong record.
- ContractFixtureTest: fixture độc lập.
- MapperConfigurationTest: module, naming strategy, coercion và unknown property.

Không nhất thiết phải tạo đúng từng class test như trên. Chia theo domain và quy mô dự án, nhưng giữ được mục tiêu test rõ ràng.

## 29. Những lỗi thường gặp

| Lỗi | Nguyên nhân | Cách xử lý |
|---|---|---|
| Generic payload thành LinkedHashMap | Dùng raw ApiResponse.class | Dùng TypeReference hoặc JavaType |
| Generic helper không biết T | Type erasure trong generic method | Truyền Class<T> hoặc JavaType |
| Collection element thành Map | Không cung cấp generic element type | Dùng TypeReference<List<T>> hoặc constructCollectionType |
| Generic record bind sai | Chỉ truyền raw record class | Cung cấp type parameter đầy đủ |
| Record không deserialize | Jackson quá cũ hoặc Java baseline không phù hợp | Dùng Jackson hỗ trợ record và kiểm tra JDK |
| Record component sai tên | Annotation/naming strategy không khớp | Dùng @JsonProperty và test JSON |
| Record primitive null thành 0 | Null primitive policy | Dùng wrapper hoặc FAIL_ON_NULL_FOR_PRIMITIVES |
| Immutable POJO không tạo được | Không có creator/default constructor phù hợp | Dùng @JsonCreator và @JsonProperty |
| Constructor parameter không nhận đúng tên | Thiếu metadata hoặc annotation | Khai báo @JsonProperty tường minh |
| Builder không nhận property | Prefix không khớp | Cấu hình @JsonPOJOBuilder(withPrefix = ...) |
| Final List vẫn bị sửa | Chỉ final reference, không defensive copy | List.copyOf() hoặc copy phù hợp |
| Round-trip pass nhưng contract sai | Hai chiều dùng cùng giả định | Test fixture độc lập và JsonNode |
| BigDecimal test sai do scale | equals() phân biệt scale | Xác định contract và dùng compareTo() nếu cần |
| Optional không bind | Thiếu Jdk8Module hoặc cấu hình | Đăng ký module tương thích |
| Polymorphic generic bị lỗi | Thiếu discriminator/subtype mapping | Logical type id và subtype allowlist |
| Test chạy khác production | Mapper test không cùng cấu hình | Dùng mapper factory production |

## 30. Quy trình kiểm thử generic, record và immutable model

1. Xác định model là generic class, generic record, record thường hay immutable POJO.
2. Xác định target type đầy đủ, bao gồm mọi generic parameter lồng nhau.
3. Dùng TypeReference khi kiểu cụ thể đã biết trong source.
4. Dùng JavaType/TypeFactory khi kiểu được tạo tại runtime.
5. Không dùng raw Class cho generic container nếu cần payload type cụ thể.
6. Kiểm tra record support theo Jackson version và Java baseline.
7. Kiểm tra canonical constructor, compact constructor và component annotation.
8. Dùng @JsonCreator/@JsonProperty cho immutable POJO cần property-based construction.
9. Dùng @JsonDeserialize/@JsonPOJOBuilder cho builder-based model.
10. Defensive-copy collection trong model bất biến.
11. Test serialization và deserialization riêng bằng fixture độc lập.
12. Test null, missing, empty, unknown field và constructor invariant.
13. Test generic element runtime type, không chỉ root object.
14. Test mapper configuration production và module bổ sung.
15. Chạy compatibility test khi nâng Jackson hoặc thay đổi DTO/annotation.

## 31. Nguyên tắc nên giữ

- Type erasure khiến raw Class không đủ để mô tả generic target.
- Dùng TypeReference cho generic type đã biết tại compile time.
- Dùng JavaType/TypeFactory khi generic type được dựng động.
- Truyền kiểu payload vào generic helper; không kỳ vọng T tự được khôi phục trong runtime.
- Kiểm tra kiểu thực tế của phần tử trong List/Map lồng nhau.
- Generic record vẫn cần type information đầy đủ.
- Jackson Databind hỗ trợ record từ dòng 2.12; xác nhận JDK và dependency thực tế.
- Record được tạo qua canonical constructor, không cần setter.
- Dùng compact constructor để bảo vệ invariant cơ bản.
- Dùng @JsonCreator(mode = PROPERTIES) và @JsonProperty cho immutable POJO.
- Dùng builder annotation khi model được tạo qua builder.
- Final reference không tự làm collection bất biến; tạo defensive copy.
- Phân biệt missing, explicit null và empty.
- Dùng mapper đã cấu hình như production.
- Test fixture độc lập, JSON shape, constructor behavior và generic type.
- Round-trip là test bổ sung, không thay thế test sender/receiver riêng.

Kiểm thử generic, record và mô hình bất biến cần chứng minh Jackson giữ đúng thông tin kiểu và tạo object theo đúng cơ chế của model. TypeReference/JavaType bảo vệ generic type; record test bảo vệ canonical constructor và component mapping; immutable POJO test bảo vệ creator hoặc builder cùng invariant. Khi kiểm tra thêm null/missing, collection mutability, naming strategy và fixture JSON độc lập, test suite sẽ phát hiện được những lỗi binding mà một round-trip đơn giản thường bỏ sót.

