# Đọc cấu trúc tổng quát lồng nhiều cấp

Trong nhiều hệ thống, JSON không có một cấu trúc cố định chỉ gồm vài property đơn giản. Một tài liệu có thể chứa object bên trong object, array chứa object, object chứa array, hoặc nhiều lớp collection lồng nhau. Có khi ứng dụng chỉ biết một phần schema; có khi cần đọc payload động từ API đối tác, cấu hình hoặc message queue.

Jackson hỗ trợ các tình huống đó bằng nhiều cách: ánh xạ vào DTO/record có kiểu rõ ràng, dùng các kiểu generic như Map và List, giữ thông tin kiểu bằng TypeReference hoặc JavaType, hoặc đọc cây JSON bằng JsonNode.

Bài học này tập trung vào việc đọc **cấu trúc tổng quát lồng nhiều cấp**: cách mô tả kiểu đích, cách giữ generic type ở runtime, cách truy cập dữ liệu sâu và cách chọn giữa mô hình tổng quát với mô hình có kiểu cụ thể.

## 1. Nhận diện cấu trúc lồng nhiều cấp

Xét một tài liệu JSON mô tả các phòng ban, thành viên, kỹ năng và metadata:

```json
{
  "organization": "Northwind",
  "departments": [
    {
      "name": "Engineering",
      "members": [
        {
          "id": 101,
          "name": "An",
          "skills": ["Java", "Spring"]
        },
        {
          "id": 102,
          "name": "Binh",
          "skills": ["SQL", "Docker"]
        }
      ],
      "budgets": {
        "2025": 120000,
        "2026": 145000
      }
    },
    {
      "name": "Support",
      "members": [],
      "budgets": {}
    }
  ],
  "metadata": {
    "source": "directory-service",
    "tags": ["internal", "active"],
    "flags": {
      "verified": true,
      "archived": false
    }
  }
}
```

Cấu trúc trên có nhiều lớp:

- Root là object.
- `departments` là array.
- Mỗi phần tử của `departments` là object.
- `members` là array object nằm trong từng department.
- `skills` là array string nằm trong từng member.
- `budgets` là object chứa các number.
- `metadata` là object chứa cả scalar, array và object lồng nhau.

Để đọc đúng tài liệu, cần mô tả chính xác từng lớp. Chỉ khai báo root là `Map` hoặc `Object` không có nghĩa là chương trình tự biết kiểu cụ thể của tất cả phần tử con.

### 1.1. Bản đồ kiểu dữ liệu

Có thể biểu diễn một phần cấu trúc bằng các kiểu Java như sau:

| Vị trí JSON | Kiểu Java có thể dùng |
| --- | --- |
| Root object | `Map<String, Object>` hoặc DTO |
| `departments` | `List<Map<String, Object>>` hoặc `List<DepartmentDto>` |
| `members` | `List<Map<String, Object>>` hoặc `List<MemberDto>` |
| `skills` | `List<String>` |
| `budgets` | `Map<String, Integer>` hoặc `Map<String, BigDecimal>` |
| `metadata.flags` | `Map<String, Boolean>` |
| `metadata.tags` | `List<String>` |

Mỗi lớp collection cần giữ thông tin kiểu phần tử. Ví dụ, `List` không cho biết phần tử là object, string hay number. `Map` cũng cần biết kiểu key và value nếu muốn ánh xạ có kiểu rõ ràng.

## 2. Đọc cấu trúc tổng quát vào Map và List

Khi schema thay đổi hoặc ứng dụng chỉ cần một phần dữ liệu, có thể dùng cấu trúc tổng quát:

- JSON object → `Map`.
- JSON array → `List`.
- JSON string → `String`.
- JSON boolean → `Boolean`.
- JSON number → một kiểu số phù hợp.
- JSON null → Java `null`.

Đây là cơ chế **untyped deserialization** của Jackson. Kiểu Java con được chọn dựa trên token JSON và cấu hình của mapper, thay vì dựa trên DTO khai báo trước.

### 2.1. Đọc root object thành Map

Dùng `TypeReference` để khai báo kiểu generic:

```java
ObjectMapper mapper = new ObjectMapper();

Map<String, Object> document = mapper.readValue(
    json,
    new TypeReference<Map<String, Object>>() {}
);
```

Root object được ánh xạ thành Map. Property `organization` có thể là String; `departments` là List; `metadata` là Map lồng nhau.

Có thể lấy dữ liệu ở cấp đầu:

```java
String organization = (String) document.get("organization");

Object rawDepartments = document.get("departments");
Object rawMetadata = document.get("metadata");
```

Vì value có kiểu `Object`, việc ép kiểu cần dựa trên schema hoặc kiểm tra kiểu thực tế. Không nên ép kiểu một cách mù quáng nếu JSON đến từ nguồn không đáng tin cậy hoặc schema có thể thay đổi.

### 2.2. Truy cập array object bên trong Map

Với cấu trúc đã biết, có thể kiểm tra và ép kiểu:

```java
Object rawDepartments = document.get("departments");

if (rawDepartments instanceof List<?> departments) {
    for (Object rawDepartment : departments) {
        if (!(rawDepartment instanceof Map<?, ?> department)) {
            throw new IllegalArgumentException(
                "Each department must be a JSON object"
            );
        }

        Object rawName = department.get("name");
        Object rawMembers = department.get("members");

        System.out.println(rawName);
        System.out.println(rawMembers);
    }
}
```

Dùng wildcard `?` ở bước kiểm tra giúp compiler không giả định key/value đã có kiểu cụ thể. Sau khi kiểm tra, chương trình mới đọc và xác thực từng giá trị.

Đối với JSON object được đọc vào Map, key mặc định là String vì tên property trong JSON object luôn là chuỗi. Value có thể là scalar, Map, List hoặc null.

### 2.3. Truy cập nhiều cấp

Ví dụ lấy danh sách kỹ năng của thành viên đầu tiên trong phòng ban đầu tiên:

```java
List<?> departments = (List<?>) document.get("departments");

Map<?, ?> firstDepartment = (Map<?, ?>) departments.get(0);

List<?> members = (List<?>) firstDepartment.get("members");

Map<?, ?> firstMember = (Map<?, ?>) members.get(0);

List<?> skills = (List<?>) firstMember.get("skills");
```

Đoạn code minh họa đường đi qua các lớp, nhưng mỗi cast đều giả định payload có đúng cấu trúc và không rỗng. Trong ứng dụng thật, hãy kiểm tra:

- Property có tồn tại không?
- Giá trị có phải null không?
- Giá trị có đúng loại Map/List không?
- Array/List có phần tử ở chỉ số cần truy cập không?
- Phần tử có đúng shape mong đợi không?

Một chuỗi cast dài dễ gây `NullPointerException` hoặc `ClassCastException` khi schema thay đổi. Khi phải duyệt dữ liệu động nhiều cấp, hãy cân nhắc helper method có kiểm tra kiểu, hoặc dùng JsonNode.

## 3. Giữ generic type bằng TypeReference

Java sử dụng **type erasure**: thông tin generic của nhiều kiểu như `List<MemberDto>` bị xóa khỏi đối tượng Class ở runtime. Vì vậy, `List.class` không thể truyền cho Jackson thông tin rằng phần tử bên trong là `MemberDto`.

`TypeReference<T>` giải quyết vấn đề bằng cách giữ thông tin kiểu generic trong một anonymous subclass.

### 3.1. Generic lồng nhau một cấp

Ví dụ JSON là array các product:

```json
[
  {"id": 1, "name": "Keyboard"},
  {"id": 2, "name": "Mouse"}
]
```

Khai báo:

```java
public record ProductDto(long id, String name) {}

List<ProductDto> products = mapper.readValue(
    json,
    new TypeReference<List<ProductDto>>() {}
);
```

Jackson nhận được cả kiểu collection lẫn kiểu phần tử. Mỗi object trong array được tạo thành một `ProductDto`.

### 3.2. Generic lồng nhiều cấp

Có thể khai báo trực tiếp những cấu trúc phức tạp:

```java
Map<String, List<ProductDto>> productsByCategory =
    mapper.readValue(
        json,
        new TypeReference<Map<String, List<ProductDto>>>() {}
    );
```

Hoặc:

```java
List<Map<String, List<Integer>>> scores =
    mapper.readValue(
        json,
        new TypeReference<List<Map<String, List<Integer>>>>() {}
    );
```

Đọc cách diễn giải kiểu từ trong ra ngoài:

- `Integer` là kiểu phần tử trong List sâu nhất.
- `List<Integer>` là value của Map.
- `Map<String, List<Integer>>` là phần tử của List ngoài cùng.

Cách đặt tên biến và xuống dòng rõ ràng giúp tránh nhầm thứ tự các generic khi cấu trúc có ba hoặc bốn cấp.

### 3.3. Ánh xạ cấu trúc ví dụ thành Map tổng quát

Với tài liệu organization ở đầu bài, có thể đọc toàn bộ thành:

```java
Map<String, Object> document = mapper.readValue(
    json,
    new TypeReference<Map<String, Object>>() {}
);
```

Sau đó, các phần tử bên trong vẫn là kiểu untyped. Nếu cần đọc đúng kiểu lồng nhau, có thể mô tả toàn bộ cấu trúc bằng DTO hoặc dùng generic cụ thể cho các phần đã biết.

Ví dụ chỉ lấy phần budgets với kiểu rõ ràng:

```java
Map<String, Integer> budgets = mapper.readValue(
    budgetsJson,
    new TypeReference<Map<String, Integer>>() {}
);
```

Nếu giá trị ngân sách có phần thập phân hoặc cần chính xác cao, đổi value type thành `BigDecimal`.

### 3.4. Generic wrapper chứa kiểu generic khác

API thường bọc dữ liệu trong một response envelope:

```java
public record ApiResponse<T>(
    boolean success,
    T data,
    String message
) {}
```

Nếu `data` là một danh sách product, kiểu đầy đủ là `ApiResponse<List<ProductDto>>`:

```java
ApiResponse<List<ProductDto>> response = mapper.readValue(
    json,
    new TypeReference<ApiResponse<List<ProductDto>>>() {}
);
```

Không nên truyền `ApiResponse.class` rồi cast `data` sang List sau đó. Khi type parameter bị mất, Jackson phải dùng kiểu untyped cho phần data.

Đây là một trong những trường hợp TypeReference hữu ích nhất: generic wrapper, generic data và collection lồng nhau có thể được mô tả trong một kiểu đầy đủ.

## 4. Dựng kiểu lồng nhau bằng JavaType

`TypeReference` tiện khi kiểu đích được biết tại thời điểm viết code. Khi kiểu cần được tạo động từ các class hoặc tham số cấu hình, hãy dùng `JavaType` và `TypeFactory`.

### 4.1. Tạo collection type

```java
TypeFactory typeFactory = mapper.getTypeFactory();

JavaType productListType = typeFactory.constructCollectionType(
    List.class,
    ProductDto.class
);
```

Sau đó truyền JavaType vào `readValue`:

```java
List<ProductDto> products = mapper.readValue(json, productListType);
```

### 4.2. Tạo Map chứa List

Ví dụ kiểu cần đọc là `Map<String, List<ProductDto>>`:

```java
JavaType productListType = typeFactory.constructCollectionType(
    List.class,
    ProductDto.class
);

JavaType productsByCategoryType = typeFactory.constructMapType(
    Map.class,
    typeFactory.constructType(String.class),
    productListType
);

Map<String, List<ProductDto>> result =
    mapper.readValue(json, productsByCategoryType);
```

`constructMapType` nhận kiểu key và value dưới dạng JavaType, nên có thể ghép các type đã tạo ở bước trước.

### 4.3. Tạo generic wrapper

Với `ApiResponse<T>`, có thể tạo kiểu tham số hóa:

```java
JavaType productListType = typeFactory.constructCollectionType(
    List.class,
    ProductDto.class
);

JavaType responseType = typeFactory.constructParametricType(
    ApiResponse.class,
    productListType
);

ApiResponse<?> response = mapper.readValue(json, responseType);
```

Khi cần kiểu tường minh ở compile time, TypeReference dễ đọc hơn. JavaType phù hợp khi kiểu được xác định tại runtime, ví dụ framework nhận một class và cần bọc nó trong List hoặc ApiResponse.

### 4.4. So sánh TypeReference và JavaType

| Tiêu chí | TypeReference | JavaType |
| --- | --- | --- |
| Cách khai báo | Anonymous subclass giữ generic signature | Tạo bằng TypeFactory |
| Kiểu lồng nhau viết trực tiếp | Rất thuận tiện | Cần ghép từng type |
| Xây dựng kiểu động | Hạn chế hơn | Phù hợp |
| Dùng trong code ứng dụng | Rõ ràng khi kiểu đã biết | Tốt cho helper/framework tổng quát |
| Giữ generic | Có | Có |

Không cần chuyển mọi khai báo sang JavaType. Chọn cách diễn đạt rõ nhất cho tình huống: kiểu cố định thì TypeReference thường ngắn gọn; kiểu động thì JavaType linh hoạt hơn.

## 5. Dùng DTO lồng nhau khi schema đã ổn định

Map tổng quát hữu ích với dữ liệu động, nhưng không phải lúc nào cũng là lựa chọn tốt nhất. Nếu schema đã biết và được kiểm soát, DTO/record lồng nhau giúp code an toàn kiểu hơn.

Với JSON organization ở đầu bài, có thể mô hình hóa:

```java
public record MemberDto(
    long id,
    String name,
    List<String> skills
) {}

public record DepartmentDto(
    String name,
    List<MemberDto> members,
    Map<String, BigDecimal> budgets
) {}

public record MetadataDto(
    String source,
    List<String> tags,
    Map<String, Boolean> flags
) {}

public record OrganizationDto(
    String organization,
    List<DepartmentDto> departments,
    MetadataDto metadata
) {}
```

Đọc:

```java
OrganizationDto organization = mapper.readValue(
    json,
    OrganizationDto.class
);
```

Jackson đi theo cấu trúc DTO từ root xuống các component lồng nhau. Mỗi cấp có kiểu cụ thể, vì vậy compiler và IDE hỗ trợ tốt hơn khi truy cập:

```java
String firstDepartmentName =
    organization.departments().get(0).name();

String firstMemberName =
    organization.departments()
        .get(0)
        .members()
        .get(0)
        .name();
```

Đoạn truy cập vẫn cần kiểm tra List rỗng hoặc null nếu hợp đồng cho phép các trường hợp đó. Kiểu tường minh không tự bảo đảm payload đã hợp lệ về nghiệp vụ.

### 5.1. Khi nào dùng DTO, khi nào dùng Map?

| Tình huống | Lựa chọn phù hợp |
| --- | --- |
| Schema ổn định, ứng dụng sở hữu hợp đồng | DTO/record |
| Cần truy cập nhiều property sâu với kiểu rõ ràng | DTO/record lồng nhau |
| Một phần payload động, một phần đã biết | DTO kết hợp Map hoặc JsonNode |
| Cấu hình do người dùng mở rộng tùy ý | Map hoặc JsonNode |
| Chỉ cần đọc vài nhánh trong payload không ổn định | JsonNode |
| Xử lý dữ liệu lớn theo từng token | Streaming API |

Một mô hình kết hợp thường hợp lý:

```java
public record PartnerMessage(
    String eventType,
    String eventId,
    JsonNode payload,
    Map<String, Object> metadata
) {}
```

Các field envelope được định kiểu rõ ràng, còn payload giữ dạng tree để xử lý theo event type.

## 6. Đọc cấu trúc động bằng JsonNode

`JsonNode` là lựa chọn tốt khi schema chưa biết đầy đủ hoặc cần kiểm tra dữ liệu ở nhiều cấp trước khi quyết định cách bind.

### 6.1. Đọc cây JSON

```java
JsonNode root = mapper.readTree(json);
```

Với JSON object, root là ObjectNode; với array, root là ArrayNode. Các giá trị bên trong được biểu diễn bằng node tương ứng.

Có thể đi sâu bằng `path`:

```java
JsonNode firstSkill = root
    .path("departments")
    .path(0)
    .path("members")
    .path(0)
    .path("skills")
    .path(0);

String skill = firstSkill.asText(null);
```

`path` trả về MissingNode khi đường dẫn không tồn tại, nhờ đó chuỗi truy cập không lập tức phát sinh NullPointerException. Tuy vậy, phải kiểm tra MissingNode và NullNode nếu hai tình huống mang ý nghĩa khác nhau.

### 6.2. Phân biệt missing và null ở mọi cấp

Giả sử JSON có thể có hoặc không có metadata:

```json
{
  "metadata": null
}
```

Và một payload khác không có property metadata:

```json
{}
```

Có thể phân biệt:

```java
JsonNode metadata = root.path("metadata");

if (metadata.isMissingNode()) {
    // Property không xuất hiện trong JSON.
} else if (metadata.isNull()) {
    // Property xuất hiện nhưng có giá trị null.
} else if (metadata.isObject()) {
    // Property là object.
}
```

Không nên chỉ gọi `asText`, `asInt` hoặc `asBoolean` rồi coi giá trị mặc định là bằng chứng property hợp lệ. Các method chuyển đổi có thể trả về giá trị mặc định khi node không phù hợp.

### 6.3. Duyệt object và array tổng quát

Duyệt các field của object:

```java
JsonNode metadata = root.path("metadata");

if (metadata.isObject()) {
    Iterator<Map.Entry<String, JsonNode>> fields =
        metadata.fields();

    while (fields.hasNext()) {
        Map.Entry<String, JsonNode> field = fields.next();

        String fieldName = field.getKey();
        JsonNode fieldValue = field.getValue();

        System.out.println(fieldName + ": " + fieldValue);
    }
}
```

Duyệt phần tử array:

```java
JsonNode departments = root.path("departments");

if (departments.isArray()) {
    for (JsonNode department : departments) {
        String name = department.path("name").asText(null);
        System.out.println(name);
    }
}
```

Tree model cho phép kiểm tra kiểu node ở từng cấp trước khi truy cập sâu. Điều này đặc biệt hữu ích khi dữ liệu có thể bị thiếu, null hoặc có cấu trúc thay đổi giữa các phiên bản.

### 6.4. Dùng JSON Pointer để truy cập sâu

Khi đã biết đường dẫn, có thể dùng JSON Pointer:

```java
JsonNode node = root.at("/departments/0/members/1/name");
```

Pointer bắt đầu bằng dấu slash. Mỗi đoạn là tên property hoặc chỉ số array. Một số ký tự trong tên property cần escape:

- `~1` biểu diễn dấu slash `/`.
- `~0` biểu diễn dấu ngã `~`.

Nếu đường dẫn không tồn tại, `at` trả về MissingNode. Hãy kiểm tra `isMissingNode()` trước khi chuyển node sang kiểu Java.

## 7. Chuyển đổi giữa tree, Map và DTO

Một quy trình phổ biến là đọc dữ liệu tổng quát trước, sau đó chuyển một nhánh đã nhận diện sang DTO.

### 7.1. Tree node sang DTO

```java
JsonNode departmentNode = root.path("departments").path(0);

if (departmentNode.isObject()) {
    DepartmentDto department = mapper.treeToValue(
        departmentNode,
        DepartmentDto.class
    );
}
```

`treeToValue` chuyển một node thành kiểu Java cụ thể. Hãy kiểm tra root shape trước để tránh bind một array hoặc scalar vào DTO không phù hợp.

### 7.2. Map sang DTO

```java
Map<String, Object> rawData = mapper.readValue(
    json,
    new TypeReference<Map<String, Object>>() {}
);

OrganizationDto organization = mapper.convertValue(
    rawData,
    OrganizationDto.class
);
```

`convertValue` hữu ích khi dữ liệu đã nằm trong bộ nhớ và cần chuyển sang kiểu đích. Nó dùng cơ chế databind, không yêu cầu ứng dụng tự serialize ra JSON text rồi đọc lại.

Tuy nhiên, `convertValue` không thay thế validation. Nếu cấu trúc Map có kiểu sai hoặc thiếu field bắt buộc, thao tác vẫn có thể thất bại hoặc tạo giá trị mặc định tùy kiểu và cấu hình.

### 7.3. DTO sang tree hoặc Map

Chiều ngược lại:

```java
JsonNode tree = mapper.valueToTree(organization);

Map<String, Object> generic = mapper.convertValue(
    organization,
    new TypeReference<Map<String, Object>>() {}
);
```

Dùng `valueToTree` khi muốn thao tác trên JSON tree. Dùng `convertValue` khi cần một biểu diễn Java tổng quát như Map/List.

## 8. Kiểu số và key trong cấu trúc tổng quát

Khi đọc vào `Object`, Map hoặc List không định kiểu, Jackson phải chọn kiểu Java cho các scalar.

### 8.1. Kiểu số mặc định

Thông thường, số nguyên được ánh xạ vào kiểu nhỏ nhất có thể chứa giá trị, như Integer, Long hoặc BigInteger; số thập phân thường được ánh xạ thành Double.

Nếu cần kiểm soát, có thể dùng các feature:

```java
ObjectMapper mapper = JsonMapper.builder()
    .enable(DeserializationFeature.USE_BIG_DECIMAL_FOR_FLOATS)
    .enable(DeserializationFeature.USE_BIG_INTEGER_FOR_INTS)
    .build();
```

- `USE_BIG_DECIMAL_FOR_FLOATS` yêu cầu dùng BigDecimal cho floating-point number trong ngữ cảnh untyped.
- `USE_BIG_INTEGER_FOR_INTS` yêu cầu dùng BigInteger cho integer trong ngữ cảnh untyped.

Các feature này ảnh hưởng đến cách biểu diễn số khi Jackson chưa có kiểu đích cụ thể. Nếu DTO khai báo property là Long hoặc BigDecimal, kiểu property vẫn là căn cứ chính để mapping.

Với dữ liệu tiền tệ hoặc số có độ chính xác cao, nên khai báo kiểu cụ thể thay vì phụ thuộc kiểu số mặc định của Map.

### 8.2. Key của JSON object

Tên property trong JSON object luôn là chuỗi. Vì vậy, khi đọc vào `Map<String, Object>`, key là String.

Ví dụ:

```json
{
  "101": "An",
  "102": "Binh"
}
```

Có thể yêu cầu Jackson ánh xạ key sang kiểu khác:

```java
Map<Long, String> usersById = mapper.readValue(
    json,
    new TypeReference<Map<Long, String>>() {}
);
```

Jackson dùng key deserializer để chuyển tên property dạng text thành kiểu key được khai báo. Nếu key không thể chuyển sang kiểu đích, mapping sẽ thất bại.

Với key là object phức tạp hoặc quy tắc biểu diễn đặc biệt, cần custom key serializer/deserializer hoặc đổi JSON thành array các entry:

```json
[
  {"key": {"region": "VN", "type": "USER"}, "value": "active"}
]
```

JSON object không phải cấu trúc phù hợp để biểu diễn key có nhiều thuộc tính nếu không có một quy ước chuyển đổi rõ ràng.

## 9. Đọc cấu trúc lồng nhau từ InputStream và ghi ra OutputStream

Với file hoặc HTTP body lớn, có thể đọc từ InputStream thay vì nạp toàn bộ thành String:

```java
try (InputStream input = Files.newInputStream(path)) {
    Map<String, Object> document = mapper.readValue(
        input,
        new TypeReference<Map<String, Object>>() {}
    );
}
```

Ghi trực tiếp ra OutputStream:

```java
try (OutputStream output = Files.newOutputStream(path)) {
    mapper.writeValue(output, document);
}
```

Dùng stream tránh phải tạo thêm một chuỗi JSON lớn trong ứng dụng. Tuy nhiên, nếu đọc thành Map/List hoặc DTO toàn bộ, cấu trúc đối tượng vẫn được giữ trong bộ nhớ. InputStream không tự biến data binding thành streaming token processing.

Nếu cần xử lý tài liệu rất lớn mà không giữ toàn bộ object graph, hãy cân nhắc JsonParser/JsonGenerator và xử lý từng phần tử một. Chọn cách đọc dựa trên kích thước dữ liệu, khả năng truy cập ngẫu nhiên và yêu cầu xử lý.

## 10. Những lỗi thường gặp với cấu trúc lồng nhiều cấp

| Hiện tượng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Lấy phần tử sâu bị ClassCastException | Cast nhầm Map, List hoặc kiểu scalar | Kiểm tra kiểu từng cấp trước khi cast |
| NullPointerException khi truy cập property | Property thiếu hoặc có giá trị null | Phân biệt missing/null và kiểm tra trước khi dùng |
| Phần tử array thành Map thay vì DTO | Dùng raw List hoặc Object | Khai báo TypeReference/JavaType đầy đủ |
| Generic wrapper có data thành Map/List untyped | Chỉ truyền ApiResponse.class | Truyền ApiResponse<T> đầy đủ bằng TypeReference hoặc JavaType |
| Number không đúng kiểu mong đợi | Untyped mapping chọn kiểu số theo mặc định | Khai báo kiểu cụ thể hoặc bật feature số phù hợp |
| Map key không chuyển được | Tên property không parse được sang kiểu key | Kiểm tra key type hoặc cung cấp key deserializer |
| Node truy cập sâu trả về giá trị mặc định | Dùng asText/asInt mà không kiểm tra node | Kiểm tra isMissingNode/isNull và loại node |
| Payload có schema mới gây lỗi | DTO chặt không có field mới hoặc không cho unknown | Quyết định rõ bỏ qua unknown hay cập nhật DTO |
| JSON rất lớn gây áp lực bộ nhớ | Bind toàn bộ thành Map/List/DTO graph | Dùng streaming để xử lý từng phần |

Khi debug, xác định chính xác đường dẫn property gây lỗi. Nếu exception có path reference, dùng nó để tìm cấp object/array nơi kiểu dữ liệu không khớp. Đừng chỉ nhìn dòng cuối của stack trace rồi sửa bằng cách cast sang Object.

## 11. Quy trình chọn mô hình đọc dữ liệu

Có thể dùng quy trình sau:

1. **Schema cố định và được ứng dụng sở hữu?** Dùng DTO/record lồng nhau.
2. **Schema tổng quát nhưng kiểu generic đã biết?** Dùng TypeReference hoặc JavaType.
3. **Schema có phần động và cần kiểm tra nhiều cấp?** Dùng JsonNode.
4. **Chỉ cần dữ liệu tổng quát dạng Map/List?** Dùng Map<String, Object> hoặc Object với kiểm tra kiểu rõ ràng.
5. **Kiểu cần xây dựng tại runtime?** Dùng TypeFactory để tạo JavaType.
6. **Dữ liệu lớn và cần xử lý tuần tự?** Dùng streaming parser/generator hoặc MappingIterator phù hợp.

Đừng chọn Map chỉ vì JSON có nhiều cấp. Nếu schema đã ổn định, DTO lồng nhau giúp giảm ép kiểu, làm rõ hợp đồng và phát hiện lỗi sớm hơn.

## 12. Bài thực hành tổng hợp

Dùng JSON organization ở đầu bài để thực hành:

1. Đọc toàn bộ tài liệu thành Map<String, Object>.
2. Truy cập departments và members, kiểm tra kiểu từng cấp trước khi cast.
3. Đọc riêng departments thành List<DepartmentDto> bằng TypeReference.
4. Khai báo OrganizationDto, DepartmentDto và MemberDto dạng record rồi bind toàn bộ JSON.
5. Tạo kiểu Map<String, List<MemberDto>> bằng TypeReference.
6. Tạo cùng kiểu bằng JavaType và TypeFactory.
7. Đọc root thành JsonNode; kiểm tra object, array, null và field bị thiếu.
8. Dùng JSON Pointer để lấy kỹ năng của thành viên thứ hai.
9. Chuyển một department node thành DepartmentDto bằng treeToValue.
10. Thử một key không chuyển được sang Long trong Map<Long, String>.
11. Thử số nguyên lớn và số thập phân với các feature untyped number.
12. Ghi kết quả ra OutputStream và so sánh với writeValueAsString.

Bài thực hành hoàn thành khi có thể giải thích cách Jackson biểu diễn từng cấp JSON, chỉ ra generic type của từng collection và chọn được mô hình phù hợp giữa DTO, Map/List, JsonNode và streaming.

## 13. Nguyên tắc ghi nhớ

- Cấu trúc JSON lồng nhau cần kiểu Java mô tả đúng từng cấp object, array và scalar.
- Map/List tổng quát dùng Object cho value/phần tử khi chưa biết schema, vì vậy cần kiểm tra kiểu trước khi cast.
- TypeReference giữ generic signature ở runtime cho kiểu lồng nhau đã biết.
- JavaType và TypeFactory phù hợp khi cần dựng kiểu generic động.
- DTO/record lồng nhau là lựa chọn rõ ràng khi schema ổn định.
- JsonNode hỗ trợ duyệt, kiểm tra và chuyển đổi cấu trúc động nhiều cấp.
- MissingNode khác NullNode; property không có khác property có giá trị null.
- Untyped number và Map key chịu quy tắc chuyển đổi riêng; khai báo kiểu cụ thể khi cần chính xác.
- Đọc từ InputStream không đồng nghĩa với xử lý streaming token nếu vẫn bind toàn bộ object graph.
- Với dữ liệu rất lớn, cân nhắc parser/generator hoặc iterator để xử lý tuần tự.

Khi đọc cấu trúc tổng quát lồng nhiều cấp, hãy mô tả kiểu từ trong ra ngoài, giữ đầy đủ generic type và kiểm tra từng cấp trước khi truy cập hoặc chuyển đổi dữ liệu.
