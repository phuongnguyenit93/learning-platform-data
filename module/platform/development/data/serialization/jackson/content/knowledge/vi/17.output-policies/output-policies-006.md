# Lọc thuộc tính động bằng JsonFilter

Một API thường cần trả cùng một đối tượng Java cho nhiều nhóm người dùng hoặc nhiều mục đích khác nhau. Ví dụ, trang danh sách người dùng chỉ cần mã và tên; trang chi tiết cần thêm email và trạng thái; một endpoint nội bộ có thể cần metadata kỹ thuật. Nếu tạo một DTO riêng cho mọi tổ hợp field, số lượng model và mapping có thể tăng nhanh. Nếu thay đổi POJO theo từng request, cấu hình serialize có thể ảnh hưởng lẫn nhau giữa các request.

Jackson có cơ chế property filter để chọn thuộc tính khi serialize. Annotation JsonFilter đánh dấu kiểu hoặc property cần được lọc; FilterProvider cung cấp filter có ID tương ứng; SimpleBeanPropertyFilter hỗ trợ các chính sách include/exclude phổ biến. Khi cần filter thay đổi theo request, có thể tạo ObjectWriter riêng cho lần ghi đó hoặc dùng MappingJacksonValue trong Spring MVC.

JsonFilter là công cụ điều khiển representation đầu ra. Nó không thay thế phân quyền, không lọc dữ liệu khi deserialize và không nên là lớp bảo vệ duy nhất cho thông tin nhạy cảm. Hãy hiểu rõ phạm vi filter, cách gắn filter ID và cách cấu hình writer để mỗi response nhận đúng tập thuộc tính.

## 1. Khi nào cần lọc thuộc tính động?

Giả sử model có nhiều thuộc tính:

```java
public class User {
    private String id;
    private String username;
    private String displayName;
    private String email;
    private boolean active;
    private String internalNote;

    // Constructors, getters and setters
}
```

Các response có thể cần tập field khác nhau:

| Ngữ cảnh | Thuộc tính cần trả |
|---|---|
| Danh sách công khai | id, displayName |
| Trang hồ sơ | id, username, displayName, email |
| Bảng quản trị | Các field quản trị được phép hiển thị |
| Log hoặc event rút gọn | Một tập field nhỏ, không chứa nội dung riêng tư |

Có thể viết nhiều DTO, dùng JsonView, hoặc dùng filter. JsonFilter phù hợp khi tập thuộc tính cần serialize được quyết định động ở thời điểm ghi JSON, chẳng hạn theo endpoint, lựa chọn field của client hoặc một chế độ response.

Nếu mỗi representation có cấu trúc và quy tắc nghiệp vụ khác nhau, DTO riêng vẫn thường rõ ràng hơn. Filter hữu ích khi cùng một object có nhiều biến thể trình bày và các biến thể chủ yếu khác nhau ở việc giữ/bỏ property.

## 2. Ba thành phần của JsonFilter

Một cấu hình cơ bản có ba phần:

1. JsonFilter("filter-id") gắn ID filter vào bean.
2. FilterProvider ánh xạ ID đó tới một PropertyFilter.
3. ObjectWriter hoặc cơ chế ghi JSON nhận FilterProvider.

Ví dụ:

```java
import com.fasterxml.jackson.annotation.JsonFilter;

@JsonFilter("userFields")
public class User {
    private String id;
    private String username;
    private String email;
    private boolean active;

    // Getters and setters
}
```

Khi serialize, Jackson thấy bean có filter ID là userFields. Filter provider phải có filter với đúng ID đó:

```java
FilterProvider filters = new SimpleFilterProvider()
    .addFilter(
        "userFields",
        SimpleBeanPropertyFilter.filterOutAllExcept("id", "username")
    );

String json = mapper.writer(filters).writeValueAsString(user);
```

Output chỉ chứa id và username:

```json
{
  "id": "u-17",
  "username": "an"
}
```

Tên filter trong annotation và tên được đăng ký trong provider phải khớp chính xác. Nếu không, Jackson không tìm được filter tương ứng và có thể ném lỗi khi serialize.

## 3. Dùng SimpleBeanPropertyFilter để include hoặc exclude

Jackson cung cấp SimpleBeanPropertyFilter để xây dựng filter theo tên property mà không cần tự viết logic token.

### 3.1. Chỉ giữ một danh sách field cho phép

filterOutAllExcept(...) giữ lại các property được liệt kê và bỏ những property còn lại:

```java
PropertyFilter publicFields =
    SimpleBeanPropertyFilter.filterOutAllExcept(
        "id",
        "displayName"
    );
```

Đây là kiểu allowlist. Khi model được bổ sung field mới, field đó không tự xuất hiện trong response cho đến khi được thêm vào danh sách cho phép. Với response công khai, allowlist thường dễ kiểm soát hơn denylist.

### 3.2. Loại một danh sách field

serializeAllExcept(...) giữ các property khác và loại những property được liệt kê:

```java
PropertyFilter withoutPrivateFields =
    SimpleBeanPropertyFilter.serializeAllExcept(
        "passwordHash",
        "internalNote"
    );
```

Đây là kiểu denylist. Khi model có field nhạy cảm mới, field đó có thể được serialize nếu không được thêm vào danh sách loại trừ. Vì vậy, denylist cần quy trình cập nhật và kiểm tra cẩn thận.

### 3.3. Đăng ký filter

```java
FilterProvider provider = new SimpleFilterProvider()
    .addFilter("userFields", publicFields);

String json = mapper.writer(provider).writeValueAsString(user);
```

Có thể dùng Set<String> để tạo danh sách từ cấu hình:

```java
Set<String> allowed = Set.of("id", "displayName", "active");

PropertyFilter filter =
    SimpleBeanPropertyFilter.filterOutAllExcept(allowed);
```

SimpleBeanPropertyFilter làm việc với property mà Jackson đã phát hiện cho bean. Tên trong allowlist/denylist là tên property JSON sau khi áp dụng naming strategy và các annotation đổi tên, không nhất thiết trùng tên field Java. Nếu dùng JsonProperty("user_name"), filter thường cần tham chiếu tên property được Jackson nhận diện là user_name.

## 4. Serialize cùng một object theo nhiều filter

Một lợi ích của filter là không cần sửa object trước khi serialize. Có thể tạo nhiều writer với chính sách khác nhau:

```java
FilterProvider summaryFilters = new SimpleFilterProvider()
    .addFilter(
        "userFields",
        SimpleBeanPropertyFilter.filterOutAllExcept("id", "displayName")
    );

FilterProvider detailFilters = new SimpleFilterProvider()
    .addFilter(
        "userFields",
        SimpleBeanPropertyFilter.filterOutAllExcept(
            "id", "username", "displayName", "email", "active"
        )
    );

ObjectWriter summaryWriter = mapper.writer(summaryFilters);
ObjectWriter detailWriter = mapper.writer(detailFilters);

String summaryJson = summaryWriter.writeValueAsString(user);
String detailJson = detailWriter.writeValueAsString(user);
```

Hai lần ghi dùng cùng object nhưng có representation khác nhau. Filter không xóa field khỏi object Java; gọi writer thứ hai vẫn có thể ghi field mà writer đầu đã loại.

ObjectWriter là đối tượng cấu hình ghi bất biến và có thể tái sử dụng sau khi tạo. Đây là cách phù hợp để giữ cấu hình theo từng representation mà không thay đổi ObjectMapper dùng chung.

## 5. Cấu hình động theo request

Trong API, client hoặc controller có thể chọn một chế độ hiển thị. Không nên thay đổi filter provider trên mapper toàn cục theo từng request. Nhiều request chạy đồng thời có thể dùng nhầm cấu hình của nhau nếu shared mapper bị mutate.

Thay vào đó, tạo provider/writer mới cho từng lần ghi hoặc dùng một tập writer cố định đã được tạo trước.

Ví dụ service nhận tập field đã được kiểm tra:

```java
public String serializeUser(
        ObjectMapper mapper,
        User user,
        Set<String> allowedFields) throws JsonProcessingException {

    PropertyFilter filter =
        SimpleBeanPropertyFilter.filterOutAllExcept(allowedFields);

    FilterProvider provider = new SimpleFilterProvider()
        .addFilter("userFields", filter);

    ObjectWriter writer = mapper.writer(provider);
    return writer.writeValueAsString(user);
}
```

Đầu vào allowedFields ở đây phải được xác thực trước khi truyền vào service. Không nên để client tự chọn tùy ý mọi property của domain object, bởi một tên field nhạy cảm có thể bị yêu cầu trực tiếp.

### 5.1. Dùng profile thay vì cho client tự chọn tên property

Một thiết kế an toàn hơn là client chọn profile có giới hạn:

```java
public enum UserRepresentation {
    SUMMARY,
    DETAIL,
    ADMIN
}
```

Service ánh xạ profile sang allowlist được định nghĩa phía server:

```java
private static final Map<UserRepresentation, Set<String>> FIELDS =
    Map.of(
        UserRepresentation.SUMMARY,
        Set.of("id", "displayName"),
        UserRepresentation.DETAIL,
        Set.of("id", "username", "displayName", "email", "active"),
        UserRepresentation.ADMIN,
        Set.of("id", "username", "displayName", "email", "active")
    );
```

Ví dụ chỉ minh họa cấu trúc. Trong hệ thống thật, profile ADMIN phải được kiểm tra quyền ở service/controller trước khi chọn filter. Nếu người gọi không có quyền, không được chọn profile quản trị chỉ vì client yêu cầu.

### 5.2. Kiểm tra field name không tồn tại

Allowlist có thể chứa tên không phải property của bean. Filter đơn giản sẽ không tự báo rằng client yêu cầu một field không tồn tại; field đó chỉ không xuất hiện trong output. Nếu API muốn trả lỗi cho field name sai, hãy kiểm tra danh sách yêu cầu với metadata/schema được server quản lý trước khi serialize.

Không nên dùng reflection tùy tiện trên toàn bộ object graph để xác định field có thể đọc. Jackson có thể dùng getter, mix-in, naming strategy, JsonProperty, virtual property hoặc custom serializer. Nếu cần xác thực danh sách field, hãy dùng metadata Jackson phù hợp hoặc giới hạn lựa chọn vào các profile tĩnh.

## 6. Filter cho nested object

Filter gắn với một bean type. Nếu object chứa bean lồng, property của object cha và property của bean con là hai cấp khác nhau.

Ví dụ:

```java
@JsonFilter("userFields")
public class User {
    private String id;
    private String displayName;
    private Address address;
    // Getters and setters
}

@JsonFilter("addressFields")
public class Address {
    private String city;
    private String street;
    private String postalCode;
    // Getters and setters
}
```

Provider có thể đăng ký filter cho cả hai ID:

```java
FilterProvider filters = new SimpleFilterProvider()
    .addFilter(
        "userFields",
        SimpleBeanPropertyFilter.filterOutAllExcept(
            "id", "displayName", "address"
        )
    )
    .addFilter(
        "addressFields",
        SimpleBeanPropertyFilter.filterOutAllExcept("city")
    );

String json = mapper.writer(filters).writeValueAsString(user);
```

Kết quả có thể chứa address nhưng chỉ giữ city bên trong:

```json
{
  "id": "u-17",
  "displayName": "An",
  "address": {
    "city": "Ho Chi Minh City"
  }
}
```

Nếu filter của bean cha loại address, toàn bộ property đó bị bỏ; filter của bean con không còn cơ hội chạy cho property này. Nếu giữ address, serializer của bean con sẽ dùng filter ID riêng nếu kiểu con được gắn JsonFilter.

Một object graph có thể chứa nhiều loại bean. Mỗi kiểu có filter ID riêng cần được đăng ký trong provider được dùng cho lần serialize đó. Khi thiếu filter ID, output có thể thất bại thay vì tự động bỏ qua.

## 7. Xử lý filter ID không được đăng ký

SimpleFilterProvider mặc định có thể báo lỗi khi serializer yêu cầu filter ID không tồn tại. Đây thường là hành vi tốt trong môi trường strict vì giúp phát hiện cấu hình thiếu.

Ví dụ:

```java
FilterProvider filters = new SimpleFilterProvider()
    .addFilter(
        "userFields",
        SimpleBeanPropertyFilter.filterOutAllExcept("id")
    )
    .setFailOnUnknownId(false);
```

setFailOnUnknownId(false) cho phép provider không báo lỗi khi gặp ID không biết và dùng hành vi fallback của provider. Cần cân nhắc kỹ trước khi bật: nếu bean có JsonFilter("addressFields") nhưng provider quên đăng ký filter đó, việc fallback có thể khiến dữ liệu được ghi theo cách không như mong muốn.

Trong API cần kiểm soát output, nên đăng ký đầy đủ filter ID và giữ fail-fast. Chỉ dùng fallback khi có chủ đích rõ ràng, đã biết filter nào có thể thiếu và output mặc định nào được chấp nhận.

## 8. Dùng mix-in khi không thể sửa class nguồn

Không phải lúc nào cũng có thể thêm JsonFilter vào model. Class có thể thuộc thư viện bên ngoài hoặc được chia sẻ với module không muốn phụ thuộc Jackson annotation.

Có thể dùng mix-in:

```java
@JsonFilter("externalUserFields")
abstract class ExternalUserMixIn {
}

ObjectMapper mapper = new ObjectMapper();
mapper.addMixIn(ExternalUser.class, ExternalUserMixIn.class);
```

Sau đó đăng ký filter ID externalUserFields trong FilterProvider như bình thường. Mix-in cho phép bổ sung metadata Jackson mà không sửa class gốc.

Hãy đăng ký mix-in khi cấu hình mapper, trước khi mapper được sử dụng đồng thời. Không mutate cấu hình mapper giữa các request.

## 9. Custom PropertyFilter cho quy tắc phức tạp

SimpleBeanPropertyFilter phù hợp khi quyết định chỉ dựa vào tên property. Nếu cần quy tắc khác, có thể triển khai PropertyFilter.

Ví dụ filter tự viết có thể kiểm tra property writer:

```java
public final class ConditionalUserFilter extends SimpleBeanPropertyFilter {
    private final Set<String> allowed;

    public ConditionalUserFilter(Set<String> allowed) {
        this.allowed = Set.copyOf(allowed);
    }

    @Override
    public void serializeAsField(
            Object pojo,
            JsonGenerator gen,
            SerializerProvider provider,
            PropertyWriter writer) throws Exception {

        if (allowed.contains(writer.getName())) {
            writer.serializeAsField(pojo, gen, provider);
        } else if (!gen.canOmitFields()) {
            writer.serializeAsOmittedField(pojo, gen, provider);
        }
    }
}
```

Đăng ký:

```java
FilterProvider filters = new SimpleFilterProvider()
    .addFilter(
        "userFields",
        new ConditionalUserFilter(Set.of("id", "displayName"))
    );
```

Đây là ví dụ cơ bản của filter theo tên. PropertyFilter còn có đường xử lý property dạng element để hỗ trợ các cấu trúc serializer đặc biệt; khi triển khai custom filter thực tế, cần tuân thủ đầy đủ contract của Jackson version đang dùng. Đặc biệt, không gọi serializer của property hai lần và không tự ghi token field/value nếu đã ủy quyền cho PropertyWriter.

Filter custom có thể nhận thêm context qua constructor, nhưng context nên là dữ liệu bất biến của một lần serialize. Tránh giữ request mutable trong singleton filter dùng chung giữa các thread.

## 10. JsonFilter khác JsonView như thế nào?

Jackson có cả JsonView và JsonFilter. Hai cơ chế đều có thể tạo nhiều representation, nhưng cách lựa chọn khác nhau.

| Tiêu chí | JsonView | JsonFilter |
|---|---|---|
| Cách xác định field | Gắn view class vào property | Filter quyết định theo property name hoặc logic custom |
| Lựa chọn lúc serialize | Chọn view class | Chọn FilterProvider |
| Phù hợp | Một số view tương đối cố định | Field selection động theo request/profile |
| Cấu hình | Annotation trên property/class và writer view | JsonFilter cùng filter ID/provider |
| Tính linh hoạt | Tốt cho các nhóm view định nghĩa trước | Tốt cho allowlist/denylist hoặc rule động |

Nếu API chỉ có hai representation ổn định như PublicView và InternalView, JsonView có thể dễ hiểu hơn. Nếu client có thể yêu cầu tập field trong một allowlist giới hạn, hoặc server cần filter theo profile động, JsonFilter thường phù hợp hơn.

Không nên dùng filter chỉ để thay thế DTO trong mọi trường hợp. Khi mỗi representation có validation, tên field, nested structure hoặc semantics khác nhau, DTO riêng làm rõ hợp đồng hơn.

## 11. Tích hợp với Spring MVC bằng MappingJacksonValue

Trong Spring MVC, có thể gắn filter cho một response bằng MappingJacksonValue. Cách này hữu ích khi controller muốn trả cùng object nhưng chọn filter theo endpoint hoặc quyền đã kiểm tra.

Ví dụ:

```java
@GetMapping("/users/{id}/summary")
public MappingJacksonValue getSummary(@PathVariable String id) {
    User user = userService.findById(id);

    FilterProvider filters = new SimpleFilterProvider()
        .addFilter(
            "userFields",
            SimpleBeanPropertyFilter.filterOutAllExcept(
                "id", "displayName"
            )
        );

    MappingJacksonValue response = new MappingJacksonValue(user);
    response.setFilters(filters);
    return response;
}
```

Spring MVC dùng Jackson message converter để serialize wrapper này và áp dụng filter provider cho response. Cần bảo đảm application đang dùng Jackson converter tương thích và mapper có module/cấu hình cần thiết.

Với profile cần quyền quản trị, kiểm tra authorization trước khi tạo filter:

```java
if (!authorizationService.canViewPrivateUserFields(currentUser)) {
    throw new AccessDeniedException("Not allowed to view private fields");
}
```

Sau khi quyền được xác nhận, controller/service mới chọn representation có email hoặc field nội bộ phù hợp. Filter chỉ quyết định cách ghi JSON; nó không chứng minh người gọi có quyền xem dữ liệu.

## 12. Filter áp dụng ở đâu và không áp dụng ở đâu?

Property filter điều khiển property của bean được Jackson serialize. Cần phân biệt:

- Filter của bean cha có thể loại cả property nested như address.
- Filter của bean con điều khiển property bên trong address, nếu bean con cũng có filter tương ứng.
- Một property có kiểu Map thường được xem là một property của bean cha; filter tên property có thể giữ/bỏ cả map.
- Filter bean không tự động biến thành quy tắc lọc từng key trong Map.
- Filter không phải cơ chế lọc từng phần tử scalar trong List hoặc array.
- Filter không điều khiển deserialize JSON thành Java object.

Ví dụ nếu muốn giữ property metadata nhưng chỉ xuất một số key của map, SimpleBeanPropertyFilter ở bean cha không đủ để lọc key bên trong map. Hãy tạo map output đã được lọc, dùng custom serializer cho kiểu map phù hợp hoặc thiết kế DTO representation riêng.

Tương tự, nếu List chứa các object có JsonFilter, mỗi object con có thể được filter theo type của nó. Nếu List chứa String/number, không có bean property bên trong để lọc.

## 13. Kết hợp JsonFilter với JsonInclude và naming strategy

JsonFilter quyết định property có được đưa vào output theo filter hay không. JsonInclude điều khiển việc bỏ giá trị theo điều kiện như null/empty. Hai cơ chế có thể cùng tác động đến một property:

```java
@JsonFilter("profileFields")
public class Profile {
    private String id;

    @JsonInclude(JsonInclude.Include.NON_NULL)
    private String nickname;
}
```

Nếu filter cho phép nickname nhưng giá trị là null và inclusion là NON_NULL, property vẫn có thể bị bỏ do inclusion policy. Nếu filter loại nickname, property bị bỏ dù giá trị khác null.

Naming strategy và JsonProperty cũng ảnh hưởng tên property mà filter nhìn thấy. Ví dụ:

```java
public class Account {
    @JsonProperty("account_id")
    private String id;
}
```

Khi filter theo tên JSON, dùng account_id thay vì giả định tên Java id. Nên có test xác nhận tên filter trong output khi DTO sử dụng snake_case, alias hoặc custom naming strategy.

## 14. Bảo mật khi dùng filter

Lọc field không đồng nghĩa phân quyền. Một số nguyên tắc quan trọng:

1. Không để client tự chọn bất kỳ property nào của entity/domain model.
2. Xác thực quyền trước khi chọn filter profile.
3. Ưu tiên allowlist cho response công khai.
4. Không serialize secret rồi hy vọng filter luôn được cấu hình đúng ở mọi endpoint.
5. Tách DTO cho dữ liệu nhạy cảm hoặc representation có semantics khác nhau.
6. Test rằng field nhạy cảm không xuất hiện trong từng response profile.
7. Không dùng setFailOnUnknownId(false) như cách che giấu cấu hình filter bị thiếu.
8. Không mutate shared mapper/provider theo request.

Ví dụ, nếu User chứa password hash, access token hoặc internal note, cách an toàn hơn là không đưa những giá trị đó vào DTO công khai. Filter có thể là lớp chọn presentation bổ sung, nhưng không nên là hàng rào duy nhất chống lộ dữ liệu.

## 15. Kiểm thử filter

Nên kiểm tra JSON thực tế thay vì chỉ kiểm tra object Java hoặc số lượng property.

### 15.1. Test allowlist

```java
@Test
void writesOnlyAllowedUserFields() throws Exception {
    User user = new User();
    user.setId("u-17");
    user.setUsername("an");
    user.setEmail("an@example.test");
    user.setActive(true);

    FilterProvider filters = new SimpleFilterProvider()
        .addFilter(
            "userFields",
            SimpleBeanPropertyFilter.filterOutAllExcept("id", "username")
        );

    String json = mapper.writer(filters).writeValueAsString(user);
    JsonNode tree = mapper.readTree(json);

    assertEquals("u-17", tree.path("id").asText());
    assertEquals("an", tree.path("username").asText());
    assertFalse(tree.has("email"));
    assertFalse(tree.has("active"));
}
```

### 15.2. Test hai writer không ảnh hưởng lẫn nhau

Tạo summary writer và detail writer, serialize cùng một object theo cả hai thứ tự gọi. Xác nhận summary luôn chỉ có field summary và detail luôn có field detail. Test này phát hiện lỗi nếu ứng dụng vô tình mutate cấu hình dùng chung.

### 15.3. Test nested filter

Tạo User có Address. Xác nhận:

- Filter cha loại address thì toàn bộ property address biến mất.
- Filter cha giữ address và filter con chỉ cho phép city thì các field khác của address không xuất hiện.
- Provider thiếu filter ID cho bean con tạo đúng hành vi lỗi/fallback đã chọn.

### 15.4. Test naming strategy

Nếu ứng dụng dùng SNAKE_CASE hoặc JsonProperty, xác nhận filter sử dụng đúng tên property JSON. Test này tránh tình trạng allowlist dùng tên field Java nên field mong muốn không xuất hiện.

### 15.5. Test quyền truy cập riêng với filter

Test controller/service để xác nhận người dùng không có quyền không thể chọn profile chứa field riêng tư. Test serialization chỉ chứng minh filter hoạt động; test authorization chứng minh người gọi được phép nhận representation đó.

## 16. Ví dụ hoàn chỉnh: profile summary và detail

Model:

```java
@JsonFilter("customerFields")
public class Customer {
    private String id;
    private String name;
    private String email;
    private String phone;
    private String internalCode;

    // Getters and setters
}
```

Factory tạo writer theo profile:

```java
public final class CustomerWriters {
    private final ObjectMapper mapper;

    public CustomerWriters(ObjectMapper mapper) {
        this.mapper = mapper;
    }

    public ObjectWriter summary() {
        return writerFor(Set.of("id", "name"));
    }

    public ObjectWriter detail() {
        return writerFor(Set.of("id", "name", "email", "phone"));
    }

    private ObjectWriter writerFor(Set<String> fields) {
        PropertyFilter filter =
            SimpleBeanPropertyFilter.filterOutAllExcept(fields);

        FilterProvider provider = new SimpleFilterProvider()
            .addFilter("customerFields", filter);

        return mapper.writer(provider);
    }
}
```

Sử dụng:

```java
CustomerWriters writers = new CustomerWriters(mapper);

String summaryJson = writers.summary().writeValueAsString(customer);
String detailJson = writers.detail().writeValueAsString(customer);
```

internalCode không có trong bất kỳ allowlist nào nên không xuất hiện. Nếu cần profile quản trị có field này, hãy thêm một phương thức writer riêng và chỉ gọi sau khi authorization thành công. Trong hệ thống thực tế, có thể cache writer cho một số profile cố định thay vì tạo mới mỗi lần; không chia sẻ một provider đang bị thay đổi giữa các thread.

## 17. Những lỗi thường gặp

| Triệu chứng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| Serialize báo không tìm thấy filter ID | ID trong JsonFilter không có trong provider | Đăng ký filter đúng ID cho mọi bean được serialize. |
| Field không xuất hiện dù có trong allowlist | Dùng tên field Java thay vì tên property JSON | Kiểm tra JsonProperty và naming strategy. |
| Request này ảnh hưởng response request khác | Mutate shared mapper/provider theo request | Tạo provider/writer riêng hoặc dùng writer bất biến. |
| Field nested không bị lọc | Chỉ gắn filter cho bean cha | Gắn filter ID và đăng ký filter cho bean con. |
| Map vẫn có mọi key | Filter chỉ chọn property map ở cấp bean | Lọc map riêng hoặc dùng custom serializer/DTO. |
| Field nhạy cảm bị lộ khi filter thiếu | Dựa vào denylist hoặc fallback không kiểm soát | Dùng allowlist, DTO và authorization. |
| Filter không ảnh hưởng deserialize | Filter là cơ chế serialization | Dùng annotation/deserializer/validation cho chiều đọc. |
| Profile mới không hoạt động | Chưa đăng ký filter hoặc chưa cập nhật allowlist | Kiểm tra mapping profile và filter provider. |

## 18. Quy trình triển khai

1. Xác định các representation cần có và field được phép ở từng representation.
2. Đánh dấu bean bằng JsonFilter với ID ổn định; nếu không sửa được class, dùng mix-in.
3. Tạo FilterProvider chứa filter cho từng ID xuất hiện trong object graph.
4. Dùng allowlist với filterOutAllExcept khi muốn chọn field được phép; dùng serializeAllExcept khi cần loại một số field đã biết.
5. Tạo ObjectWriter riêng cho profile/request; không thay đổi mapper dùng chung trong lúc phục vụ request.
6. Với nested bean, đăng ký filter riêng cho từng kiểu cần lọc.
7. Nếu cần lọc Map key hoặc dữ liệu lồng đặc biệt, dùng logic riêng thay vì kỳ vọng bean filter xử lý mọi cấp.
8. Kiểm tra quyền trước khi chọn profile có dữ liệu riêng tư.
9. Test JSON output, nested filter, filter ID thiếu, naming strategy và hai writer chạy độc lập.
10. Tài liệu hóa profile và các field public để client biết representation nào ổn định.

JsonFilter giúp Jackson chọn property linh hoạt ở thời điểm serialize. Khi kết hợp đúng filter ID, provider và writer riêng, cùng một object có thể tạo nhiều response mà không cần thay đổi dữ liệu gốc. Hãy giữ chính sách lọc ở phạm vi rõ ràng, ưu tiên allowlist cho dữ liệu công khai và dùng DTO/authorization cho ranh giới bảo mật; như vậy việc thay đổi representation sẽ dễ kiểm soát hơn khi API phát triển.
