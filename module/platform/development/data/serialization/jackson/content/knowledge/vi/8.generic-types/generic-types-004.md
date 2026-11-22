# Xây dựng kiểu động cho List, Map và kiểu bao

Trong Java, một biến có thể mang kiểu tổng quát như List<User>, Map<String, User> hoặc ApiResponse<List<User>>. Khi Jackson đọc JSON, nó cần biết không chỉ kiểu lớp bên ngoài mà còn kiểu phần tử, kiểu key/value và các tham số generic bên trong.

Vấn đề nằm ở type erasure của Java: tại runtime, thông tin generic thường không còn đầy đủ nếu chỉ truyền một Class<?>. Vì vậy, nếu gọi readValue với List.class, Jackson biết kết quả là một List nhưng không biết mỗi phần tử phải là User, Order hay một kiểu khác.

Jackson cung cấp hai cách chính để giữ và xây dựng thông tin kiểu tổng quát:

- **TypeReference<T>:** khai báo trực tiếp một kiểu generic cụ thể bằng anonymous subclass.
- **JavaType và TypeFactory:** xây dựng kiểu động từ các Class hoặc JavaType có sẵn, phù hợp khi kiểu đích chỉ được biết tại runtime.

Khi hiểu hai cách này, có thể xử lý chính xác List, Map, kiểu lồng nhau và các wrapper generic mà không phải ép kiểu thủ công từ Map hoặc LinkedHashMap.

## 1. Vì sao Class<?> chưa đủ cho kiểu tổng quát?

Java không cho phép lấy class literal của một kiểu có tham số generic:

~~~java
List<User>.class;                 // Không hợp lệ
Map<String, User>.class;          // Không hợp lệ
ApiResponse<User>.class;          // Không hợp lệ
~~~

Chỉ có thể lấy class của kiểu raw:

~~~java
List.class;
Map.class;
ApiResponse.class;
~~~

Khi truyền List.class cho Jackson:

~~~java
List<?> users = mapper.readValue(json, List.class);
~~~

Jackson tạo một danh sách, nhưng không biết phần tử phải là User. Với JSON object, phần tử thường được ánh xạ thành Map, thường là LinkedHashMap; JSON array thành List; các giá trị scalar thành kiểu số, chuỗi hoặc boolean tương ứng.

Ví dụ JSON:

~~~json
[
  {
    "id": 1,
    "name": "An"
  },
  {
    "id": 2,
    "name": "Binh"
  }
]
~~~

Nếu đọc bằng List.class, kết quả có thể có cấu trúc như:

~~~text
ArrayList
  ├── LinkedHashMap
  │     ├── id   -> Integer
  │     └── name -> String
  └── LinkedHashMap
        ├── id   -> Integer
        └── name -> String
~~~

Điều này gây bất tiện khi code mong muốn nhận List<User>:

- Không có bảo đảm kiểu tại compile time cho phần tử.
- Phải ép kiểu thủ công hoặc convert từng Map.
- Lỗi kiểu có thể xuất hiện muộn khi truy cập dữ liệu.
- Annotation, constructor và custom deserializer của User không được áp dụng như khi đọc trực tiếp User.

Giải pháp là cung cấp cho Jackson đầy đủ cấu trúc generic của kiểu đích.

## 2. TypeReference: khai báo kiểu generic cụ thể

TypeReference thuộc package com.fasterxml.jackson.core.type. Nó giữ thông tin generic thông qua anonymous subclass, cho phép Jackson lấy lại kiểu tổng quát từ metadata của lớp con.

Ví dụ đọc List<User>:

~~~java
import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;

import java.util.List;

ObjectMapper mapper = new ObjectMapper();

List<User> users = mapper.readValue(
    json,
    new TypeReference<List<User>>() {}
);
~~~

Cặp dấu ngoặc nhọn tạo một anonymous subclass. Generic signature của lớp con giữ lại List<User>, nhờ đó Jackson biết kiểu phần tử cần tạo.

Đây là cách ngắn gọn khi kiểu generic đã biết tại thời điểm viết code.

### 2.1. Đọc List<T>

Ví dụ:

~~~java
public record User(Long id, String name) {}

List<User> users = mapper.readValue(
    json,
    new TypeReference<List<User>>() {}
);
~~~

Jackson tạo từng User theo creator hoặc cơ chế binding phù hợp của class. Các annotation, constructor và module hỗ trợ kiểu dữ liệu của User đều có thể được áp dụng.

Có thể dùng cùng cách cho các kiểu collection khác:

~~~java
Set<User> userSet = mapper.readValue(
    json,
    new TypeReference<Set<User>>() {}
);

LinkedList<User> userList = mapper.readValue(
    json,
    new TypeReference<LinkedList<User>>() {}
);
~~~

Tuy nhiên, chỉ nên chọn kiểu collection cụ thể khi hợp đồng hoặc code thực sự cần nó. Với phần lớn API, khai báo List<User> hoặc Set<User> là đủ.

### 2.2. Đọc Map<K, V>

Map cũng cần giữ cả kiểu key và value:

~~~java
Map<String, User> usersById = mapper.readValue(
    json,
    new TypeReference<Map<String, User>>() {}
);
~~~

JSON:

~~~json
{
  "u-01": {
    "id": 1,
    "name": "An"
  },
  "u-02": {
    "id": 2,
    "name": "Binh"
  }
}
~~~

Jackson biết mỗi value phải được tạo thành User. Nếu dùng Map.class, value object có thể chỉ là LinkedHashMap.

JSON object luôn có tên property dạng chuỗi. Khi ánh xạ sang Map có key không phải String, Jackson cần chuyển tên property sang kiểu key đích. Ví dụ Map<Integer, User> có thể hoạt động nếu key có thể chuyển đổi thành Integer; nếu key là value object riêng, có thể cần key deserializer.

### 2.3. Đọc kiểu lồng nhau

TypeReference cũng biểu diễn được generic lồng nhiều cấp:

~~~java
Map<String, List<User>> groupedUsers = mapper.readValue(
    json,
    new TypeReference<Map<String, List<User>>>() {}
);
~~~

JSON tương ứng:

~~~json
{
  "engineering": [
    {
      "id": 1,
      "name": "An"
    }
  ],
  "design": [
    {
      "id": 2,
      "name": "Binh"
    }
  ]
}
~~~

Jackson tạo Map<String, List<User>> với cấu trúc đầy đủ. Không cần đọc thành Map<String, List<LinkedHashMap>> rồi chuyển từng phần tử.

Các kiểu khác cũng có thể lồng nhau:

~~~java
List<Map<String, User>> records = mapper.readValue(
    json,
    new TypeReference<List<Map<String, User>>>() {}
);
~~~

~~~java
Map<String, Map<String, List<User>>> nested = mapper.readValue(
    json,
    new TypeReference<Map<String, Map<String, List<User>>>>() {}
);
~~~

Dù TypeReference biểu diễn được cấu trúc phức tạp, không nên lạm dụng kiểu generic quá sâu trong API công khai. Nếu kiểu lồng nhau khó đọc, hãy định nghĩa DTO hoặc wrapper có tên rõ ràng.

## 3. TypeReference không tự biết kiểu T ở runtime

Một điểm quan trọng: TypeReference giữ được kiểu đã được khai báo cụ thể trong anonymous subclass, nhưng không thể khôi phục một type parameter đã bị Java erasure xóa.

Ví dụ method generic:

~~~java
public <T> List<T> readList(String json) throws IOException {
    return mapper.readValue(
        json,
        new TypeReference<List<T>>() {}
    );
}
~~~

Method này trông có vẻ tổng quát, nhưng T ở đây vẫn là type variable. Khi method chạy, TypeReference không tự biết caller muốn T là User hay Order.

Cách đúng là truyền thông tin kiểu vào method:

~~~java
public <T> List<T> readList(
    String json,
    Class<T> elementType
) throws IOException {

    JavaType listType = mapper.getTypeFactory()
        .constructCollectionType(List.class, elementType);

    return mapper.readValue(json, listType);
}
~~~

Caller:

~~~java
List<User> users = readList(json, User.class);
List<Order> orders = readList(json, Order.class);
~~~

Nếu T itself là một kiểu generic, Class<T> vẫn không đủ. Khi đó hãy truyền JavaType hoặc TypeReference vào method.

## 4. JavaType: xây dựng kiểu động bằng TypeFactory

JavaType thuộc package com.fasterxml.jackson.databind. Nó là mô tả kiểu mà Jackson có thể sử dụng trong serialization/deserialization, bao gồm các tham số generic.

TypeFactory là thành phần tạo JavaType. Thông thường, lấy factory từ mapper đang dùng:

~~~java
TypeFactory typeFactory = mapper.getTypeFactory();
~~~

Một số phương thức thường dùng:

| Phương thức | Mục đích |
|---|---|
| constructType(Class<?>) | Tạo JavaType từ class thông thường |
| constructType(Type) | Tạo JavaType từ java.lang.reflect.Type |
| constructCollectionType(...) | Tạo kiểu Collection với kiểu phần tử |
| constructMapType(...) | Tạo kiểu Map với key và value |
| constructParametricType(...) | Tạo kiểu generic với các tham số kiểu |
| constructArrayType(...) | Tạo kiểu array |
| constructCollectionLikeType(...) | Tạo kiểu giống collection không nhất thiết implement Collection |
| constructMapLikeType(...) | Tạo kiểu giống map không nhất thiết implement Map |

### 4.1. Xây dựng List<User>

~~~java
JavaType userListType = mapper.getTypeFactory()
    .constructCollectionType(List.class, User.class);

List<User> users = mapper.readValue(json, userListType);
~~~

JavaType giữ thông tin rằng collection là List và phần tử là User.

### 4.2. Xây dựng Map<String, User>

~~~java
JavaType userMapType = mapper.getTypeFactory()
    .constructMapType(
        Map.class,
        String.class,
        User.class
    );

Map<String, User> usersById = mapper.readValue(
    json,
    userMapType
);
~~~

Có thể thay String.class bằng một kiểu key khác nếu JSON property name có thể được chuyển đổi sang kiểu đó hoặc đã có key deserializer phù hợp.

### 4.3. Xây dựng kiểu generic lồng nhau

Giả sử JSON có kiểu:

~~~java
Map<String, List<User>>
~~~

Có thể xây dựng từ trong ra ngoài:

~~~java
TypeFactory typeFactory = mapper.getTypeFactory();

JavaType userListType = typeFactory.constructCollectionType(
    List.class,
    User.class
);

JavaType groupedUserType = typeFactory.constructMapType(
    Map.class,
    String.class,
    userListType
);

Map<String, List<User>> result = mapper.readValue(
    json,
    groupedUserType
);
~~~

Điểm quan trọng là tham số value của Map được truyền bằng JavaType, không chỉ bằng Class. Vì vậy, value có thể là một kiểu generic khác như List<User>.

### 4.4. Dùng constructParametricType cho wrapper

Giả sử ứng dụng có wrapper:

~~~java
public record ApiResponse<T>(
    boolean success,
    T data,
    String message
) {}
~~~

Đọc ApiResponse<User>:

~~~java
JavaType responseType = mapper.getTypeFactory()
    .constructParametricType(ApiResponse.class, User.class);

ApiResponse<User> response = mapper.readValue(
    json,
    responseType
);
~~~

Đọc ApiResponse<List<User>>:

~~~java
JavaType userListType = mapper.getTypeFactory()
    .constructCollectionType(List.class, User.class);

JavaType responseType = mapper.getTypeFactory()
    .constructParametricType(ApiResponse.class, userListType);

ApiResponse<List<User>> response = mapper.readValue(
    json,
    responseType
);
~~~

JSON:

~~~json
{
  "success": true,
  "data": [
    {
      "id": 1,
      "name": "An"
    },
    {
      "id": 2,
      "name": "Binh"
    }
  ],
  "message": "OK"
}
~~~

Jackson biết data là List<User>, không phải List<LinkedHashMap>. Cấu trúc wrapper có thể lồng nhiều cấp mà không cần định nghĩa một class mới cho từng tổ hợp.

## 5. Xây dựng helper tổng quát cho List, Map và wrapper

Khi ứng dụng có nhiều nơi cần đọc kiểu generic được xác định ở runtime, nên tập trung logic tạo JavaType vào helper.

### 5.1. Helper đọc collection

~~~java
public final class JsonTypeReader {

    private final ObjectMapper mapper;

    public JsonTypeReader(ObjectMapper mapper) {
        this.mapper = mapper;
    }

    public <T> List<T> readList(
        String json,
        Class<T> elementType
    ) throws JsonProcessingException {

        JavaType type = mapper.getTypeFactory()
            .constructCollectionType(List.class, elementType);

        return mapper.readValue(json, type);
    }
}
~~~

Caller không cần biết cách Jackson xây dựng JavaType:

~~~java
List<User> users = reader.readList(json, User.class);
~~~

### 5.2. Helper đọc Map

~~~java
public <K, V> Map<K, V> readMap(
    String json,
    Class<K> keyType,
    Class<V> valueType
) throws JsonProcessingException {

    JavaType type = mapper.getTypeFactory()
        .constructMapType(Map.class, keyType, valueType);

    return mapper.readValue(json, type);
}
~~~

Cách này phù hợp khi cả key và value đều là class cụ thể.

Nếu value là List<User>, hãy nhận JavaType thay vì Class<V>:

~~~java
public <V> Map<String, V> readStringMap(
    String json,
    JavaType valueType
) throws JsonProcessingException {

    JavaType mapType = mapper.getTypeFactory()
        .constructMapType(Map.class, String.class, valueType);

    return mapper.readValue(json, mapType);
}
~~~

Caller:

~~~java
JavaType userListType = mapper.getTypeFactory()
    .constructCollectionType(List.class, User.class);

Map<String, List<User>> grouped =
    readStringMap(json, userListType);
~~~

### 5.3. Helper đọc wrapper generic

~~~java
public <T> ApiResponse<T> readResponse(
    String json,
    JavaType dataType
) throws JsonProcessingException {

    JavaType responseType = mapper.getTypeFactory()
        .constructParametricType(ApiResponse.class, dataType);

    return mapper.readValue(json, responseType);
}
~~~

Caller có thể truyền User.class đã chuyển thành JavaType, List<User> hoặc Map<String, User>. Helper không phải định nghĩa một method riêng cho từng kiểu data.

Nếu muốn hỗ trợ mọi wrapper generic, có thể nhận Class<?> wrapperType và JavaType... parameterTypes, sau đó gọi constructParametricType. Cần kiểm tra số tham số kiểu đúng với khai báo generic của wrapper; nếu truyền sai, lỗi có thể xuất hiện khi Jackson tạo kiểu hoặc deserialize.

## 6. Chọn TypeReference hay JavaType?

Hai cách đều đúng, nhưng phù hợp với những hoàn cảnh khác nhau.

| Tiêu chí | TypeReference | JavaType |
|---|---|---|
| Kiểu generic biết trước khi viết code | Rất thuận tiện | Dài hơn một chút |
| Kiểu phần tử được truyền vào runtime | Không tự giải quyết type variable | Phù hợp |
| Xây dựng kiểu lồng nhiều cấp từ cấu hình | Có thể khó biểu diễn | Rõ ràng và linh hoạt |
| Helper generic tái sử dụng | Cần truyền Type/JavaType nếu T động | Phù hợp |
| Khả năng đọc code | Ngắn với kiểu cố định | Dễ kiểm soát từng tầng kiểu |
| Tái sử dụng mô tả kiểu | Có thể tạo TypeReference tại chỗ | JavaType có thể lưu và tái sử dụng |

Quy tắc thực tế:

- Dùng TypeReference khi kiểu đích cụ thể đã biết, ví dụ List<User> hoặc Map<String, Order>.
- Dùng JavaType khi kiểu đích được lắp ghép từ Class, JavaType hoặc metadata tại runtime.
- Không dùng raw List.class/Map.class nếu cần phần tử có kiểu cụ thể.
- Nếu JSON có cấu trúc chưa biết trước và cần duyệt linh hoạt, cân nhắc JsonNode thay vì cố ép thành một kiểu generic quá rộng.

## 7. convertValue cũng cần thông tin kiểu generic

ObjectMapper.convertValue() chuyển đổi object đang có trong bộ nhớ sang kiểu đích. Nó hữu ích khi dữ liệu nguồn là Map, JsonNode hoặc một DTO khác và muốn ánh xạ sang kiểu Java.

Ví dụ:

~~~java
Map<String, Object> raw = Map.of(
    "id", 10,
    "name", "An"
);

User user = mapper.convertValue(raw, User.class);
~~~

Nếu kiểu đích là List<User>, hãy cung cấp TypeReference hoặc JavaType:

~~~java
List<User> users = mapper.convertValue(
    rawList,
    new TypeReference<List<User>>() {}
);
~~~

Hoặc:

~~~java
JavaType listType = mapper.getTypeFactory()
    .constructCollectionType(List.class, User.class);

List<User> users = mapper.convertValue(rawList, listType);
~~~

convertValue không phải lúc nào cũng tương đương việc serialize thành JSON string rồi parse lại. Jackson thực hiện chuyển đổi qua cơ chế token nội bộ và có thể phát sinh lỗi mapping nếu dữ liệu không phù hợp với kiểu đích.

Không nên dùng convertValue để che giấu một hợp đồng dữ liệu không rõ ràng. Nếu nguồn và đích là hai mô hình nghiệp vụ khác nhau, hãy cân nhắc MapStruct hoặc mapping thủ công để thể hiện rõ quy tắc chuyển đổi.

## 8. Kiểu động khi serialize JSON

TypeReference và JavaType thường được nhắc đến khi deserialize, nhưng kiểu tổng quát cũng có thể quan trọng khi serialize.

Ví dụ ghi wrapper generic:

~~~java
ApiResponse<List<User>> response =
    new ApiResponse<>(true, users, "OK");

JavaType responseType = mapper.getTypeFactory()
    .constructParametricType(
        ApiResponse.class,
        mapper.getTypeFactory().constructCollectionType(
            List.class,
            User.class
        )
    );

String json = mapper.writerFor(responseType)
    .writeValueAsString(response);
~~~

Với trường hợp serialize đơn giản, Jackson thường có thể suy ra kiểu từ object runtime và serialize bình thường. Tuy nhiên, writerFor(JavaType) hữu ích khi cần chỉ rõ root type, áp dụng root type serializer, static typing hoặc giữ thông tin generic cho các cấu hình polymorphic.

Không nên bật static typing hoặc default typing chỉ để giải quyết vấn đề generic. Hãy xác định chính xác lý do cần khai báo root type.

## 9. Xử lý JSON động bằng Map<String, Object> hay JsonNode?

Khi cấu trúc JSON không cố định, có hai lựa chọn phổ biến.

### 9.1. Map<String, Object>

~~~java
Map<String, Object> payload = mapper.readValue(
    json,
    new TypeReference<Map<String, Object>>() {}
);
~~~

Cách này phù hợp khi JSON là object và ứng dụng cần thao tác dữ liệu như một map Java. Object lồng nhau thường trở thành Map, array thành List.

Nhược điểm là kiểu giá trị không còn rõ ràng. Một field có thể là Integer, Long, Double, Boolean, String, List hoặc Map tùy dữ liệu và cấu hình mapper. Code phải kiểm tra kiểu trước khi ép kiểu.

### 9.2. JsonNode

~~~java
JsonNode root = mapper.readTree(json);

String eventType = root.path("eventType").asText(null);
JsonNode dataNode = root.path("data");

if (eventType == null || dataNode.isMissingNode()) {
    throw new IllegalArgumentException("Invalid event payload");
}
~~~

JsonNode phù hợp khi cần duyệt cây JSON, kiểm tra field tồn tại, phân nhánh theo event type hoặc chỉ trích xuất một vài thuộc tính.

Nếu sau khi xác định loại event đã biết kiểu đích, có thể chuyển node sang DTO:

~~~java
WebhookEvent event = mapper.treeToValue(dataNode, WebhookEvent.class);
~~~

Không nên dùng Map<String, Object> hoặc JsonNode cho mọi request chỉ vì chúng linh hoạt. Khi schema ổn định, DTO generic có kiểu rõ ràng dễ bảo trì và an toàn hơn.

## 10. Kiểm soát độ chính xác của kiểu số trong dữ liệu động

Khi đọc JSON vào Object hoặc Map<String, Object>, Jackson phải chọn kiểu Java cho các số mà không có target type cụ thể. Tùy cấu hình và giá trị, số nguyên có thể thành Integer hoặc Long; số thực thường thành Double.

Nếu dữ liệu tài chính hoặc số rất lớn cần giữ chính xác, hãy cân nhắc BigDecimal/BigInteger hoặc cấu hình tương ứng:

~~~java
ObjectMapper mapper = JsonMapper.builder()
    .enable(DeserializationFeature.USE_BIG_DECIMAL_FOR_FLOATS)
    .enable(DeserializationFeature.USE_BIG_INTEGER_FOR_INTS)
    .build();
~~~

Cấu hình này ảnh hưởng các giá trị không có kiểu đích cụ thể được ánh xạ vào Object. Nếu DTO khai báo BigDecimal, hãy dùng kiểu đó trực tiếp thay vì dựa vào Map động.

Không dùng double để lưu số tiền hoặc giá trị cần độ chính xác thập phân tuyệt đối. Việc chọn kiểu số là một phần của hợp đồng dữ liệu.

## 11. Lỗi thường gặp khi xây dựng kiểu động

| Triệu chứng | Nguyên nhân | Cách xử lý |
|---|---|---|
| List chứa LinkedHashMap thay vì DTO | Đọc bằng List.class | Dùng TypeReference<List<T>> hoặc JavaType |
| Map value là LinkedHashMap | Chỉ truyền Map.class | Khai báo key/value type |
| Generic helper trả về object không đúng kiểu | TypeReference<List<T>> không biết T runtime | Truyền Class<T> hoặc JavaType vào helper |
| Wrapper.data thành Map/List không có kiểu | Chỉ truyền Wrapper.class | Dùng constructParametricType |
| Ép kiểu gây ClassCastException | Type erasure che giấu kiểu phần tử | Deserialize với kiểu generic đầy đủ |
| Nested collection bị sai kiểu | Chỉ mô tả lớp ngoài cùng | Xây dựng JavaType từ trong ra ngoài |
| Map key không parse được | JSON property name không chuyển được sang key type | Dùng key type phù hợp hoặc custom key deserializer |
| convertValue tạo dữ liệu sai | Kiểu đích thiếu generic type hoặc dữ liệu nguồn không tương thích | Truyền JavaType/TypeReference và kiểm tra lỗi mapping |
| Số trong Map bị mất độ chính xác | Dùng kiểu số floating-point không phù hợp | Dùng BigDecimal/BigInteger và cấu hình phù hợp |

Khi gặp lỗi, hãy kiểm tra kiểu đích mà Jackson thực sự nhận được. Nếu log hoặc debugger chỉ cho thấy List.class hoặc Map.class, rất có thể thông tin generic đã bị mất trước khi gọi Jackson.

## 12. Kiểm thử kiểu generic

Nên có test cho từng cấu trúc generic quan trọng.

Ví dụ test List<User>:

~~~java
@Test
void shouldReadTypedUserList() throws Exception {
    String json = """
        [
          {"id": 1, "name": "An"},
          {"id": 2, "name": "Binh"}
        ]
        """;

    List<User> users = mapper.readValue(
        json,
        new TypeReference<List<User>>() {}
    );

    assertEquals(2, users.size());
    assertEquals("An", users.get(0).name());
}
~~~

Test wrapper:

~~~java
@Test
void shouldReadApiResponseWithTypedList() throws Exception {
    String json = """
        {
          "success": true,
          "data": [
            {"id": 1, "name": "An"}
          ],
          "message": "OK"
        }
        """;

    JavaType userListType = mapper.getTypeFactory()
        .constructCollectionType(List.class, User.class);

    JavaType responseType = mapper.getTypeFactory()
        .constructParametricType(ApiResponse.class, userListType);

    ApiResponse<List<User>> response =
        mapper.readValue(json, responseType);

    assertTrue(response.success());
    assertEquals("An", response.data().get(0).name());
}
~~~

Ngoài trường hợp thành công, cần test:

- List rỗng và Map rỗng.
- Giá trị null trong collection hoặc map.
- Field generic bị thiếu trong wrapper.
- Kiểu phần tử sai so với JSON.
- Map key không hợp lệ.
- Số lớn hoặc số thập phân cần giữ chính xác.
- Cấu trúc lồng nhau sâu hơn một cấp.
- JSON không hợp lệ hoặc bị cắt giữa chừng.

Test nên xác nhận kiểu runtime của phần tử, không chỉ xác nhận số lượng phần tử. Nếu List có hai LinkedHashMap, test size vẫn qua nhưng hợp đồng kiểu dữ liệu đã sai.

## 13. Quy trình chọn cách biểu diễn kiểu

~~~text
Xác định kiểu JSON mong muốn
           |
           v
Kiểu generic cố định trong code?
       /          \
     Có            Không
      |              |
      v              v
TypeReference    Có Class/JavaType
                  tại runtime?
                  /       \
                Có         Không
                 |           |
                 v           v
             JavaType    JsonNode hoặc
             TypeFactory  Map động
                 |
                 v
          readValue / readerFor
                 |
                 v
          Kiểm thử kiểu phần tử
~~~

Nếu kiểu đã biết, TypeReference thường dễ đọc. Nếu kiểu đến từ tham số method hoặc cấu hình runtime, JavaType phù hợp hơn. Nếu schema hoàn toàn không biết trước, JsonNode cho phép kiểm tra cấu trúc trước khi chuyển thành DTO.

## 14. Kết luận

Jackson cần biết đầy đủ kiểu đích khi xử lý List, Map và wrapper generic. Class raw như List.class chỉ cung cấp kiểu container, không giữ kiểu phần tử. TypeReference phù hợp với kiểu generic cụ thể đã biết trong code; JavaType và TypeFactory phù hợp khi phải xây dựng kiểu từ các tham số runtime hoặc lồng nhiều cấp.

Hãy truyền thông tin kiểu từ caller vào helper generic, xây dựng JavaType từ trong ra ngoài và tránh ép kiểu từ LinkedHashMap. Với JSON động, chọn Map<String, Object> hoặc JsonNode theo cách ứng dụng cần thao tác dữ liệu. Khi cần độ chính xác số, xác định rõ BigDecimal/BigInteger thay vì để kiểu Object quyết định ngoài ý muốn.

Một kiểu generic được mô tả đầy đủ giúp Jackson tạo đúng DTO ở mọi cấp, giữ được lợi ích của hệ thống type-safe và giảm lỗi chỉ xuất hiện khi ứng dụng truy cập phần tử ở runtime.

