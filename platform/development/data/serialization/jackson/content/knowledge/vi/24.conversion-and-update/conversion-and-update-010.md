# Tránh dùng chuyển đổi như một bảo đảm sao chép sâu hoặc kiểm tra nghiệp vụ

Jackson có thể chuyển một giá trị Java sang kiểu khác bằng ObjectMapper.convertValue. API này rất tiện khi cần biến một request DTO thành một model khác, chuyển POJO thành Map, hoặc ánh xạ một cấu trúc trung gian sang DTO. Vì thao tác thường chỉ cần một dòng code, đôi khi người ta dùng nó như cách sao chép object hoặc như một bước xác nhận dữ liệu hợp lệ.

Hai giả định đó đều không an toàn. convertValue là thao tác chuyển đổi theo quy tắc serialize/deserialize của Jackson. Nó tạo representation trung gian bằng token và ánh xạ representation đó sang kiểu đích. Nó không hứa hẹn sao chép sâu toàn bộ object graph, giữ nguyên mọi quan hệ tham chiếu, hoặc thực thi đầy đủ quy tắc nghiệp vụ của ứng dụng.

Muốn sao chép sâu, hãy định nghĩa rõ object nào cần được sao chép, object nào được chia sẻ và cách xử lý vòng tham chiếu. Muốn xác nhận dữ liệu hợp lệ, hãy dùng validation ở đúng tầng: cấu trúc JSON, DTO constraints, domain invariants và quy tắc nghiệp vụ của use case. Việc chuyển đổi có thể là một bước trong quy trình, nhưng không thay thế những trách nhiệm đó.

## 1. convertValue làm gì?

ObjectMapper.convertValue nhận một giá trị nguồn và chuyển nó thành kiểu đích theo metadata Jackson:

```java
UserDto dto = mapper.convertValue(userEntity, UserDto.class);
```

Hoặc chuyển thành map:

```java
Map<String, Object> values = mapper.convertValue(
    userEntity,
    new TypeReference<Map<String, Object>>() {}
);
```

Và chuyển collection với kiểu phần tử cụ thể:

```java
JavaType targetType = mapper.getTypeFactory()
    .constructCollectionType(List.class, UserDto.class);

List<UserDto> users = mapper.convertValue(sourceUsers, targetType);
```

convertValue hữu ích khi cấu trúc nguồn và đích có thể được biểu diễn qua quy tắc Jackson. Nó thường ít tốn chi phí hơn việc tạo JSON string rồi đọc JSON string đó trở lại, vì Jackson dùng một buffer token nội bộ thay vì phải tạo chuỗi JSON văn bản hoàn chỉnh.

### 1.1. Mô hình hoạt động

Về mặt khái niệm, quá trình gần giống:

```text
Source Java value
       |
       v
Jackson serializer
       |
       v
TokenBuffer
       |
       v
Jackson deserializer for target type
       |
       v
Target Java value
```

Điều này có hệ quả quan trọng: kết quả phụ thuộc vào cách Jackson nhìn thấy object nguồn khi serialize và cách nó tạo object đích khi deserialize. Getter, serializer tùy biến, annotation, mix-in, module, naming strategy và cấu hình mapper đều có thể ảnh hưởng representation trung gian.

convertValue không phải một phép gán field trực tiếp giữa hai object. Nó cũng không phải một cơ chế clone tổng quát của Java.

### 1.2. Ví dụ chuyển DTO

```java
public record CreateUserRequest(String username, String email) {}

public record UserProfile(String username, String email) {}

CreateUserRequest request =
    new CreateUserRequest("an", "an@example.test");

UserProfile profile =
    mapper.convertValue(request, UserProfile.class);
```

Trong ví dụ đơn giản này, tên và kiểu property tương thích nên việc chuyển đổi thuận tiện. Nhưng việc tạo được UserProfile chỉ chứng minh Jackson có thể ánh xạ representation của request sang kiểu đích. Nó chưa chứng minh email thuộc về người dùng hiện tại, username chưa bị người khác sử dụng hoặc người gọi được phép tạo tài khoản.

## 2. Vì sao convertValue không phải bảo đảm deep copy?

Sao chép sâu (deep copy) thường có nghĩa là tạo một object graph mới, trong đó các object mutable cần độc lập với graph nguồn. Tuy nhiên, khái niệm này phải được định nghĩa theo domain:

- Có cần tạo bản sao cho mọi object con mutable không?
- Có giữ nguyên quan hệ chia sẻ khi hai property cùng trỏ tới một object không?
- Có giữ vòng tham chiếu không?
- Có sao chép các object bất biến hay chỉ chia sẻ chúng?
- Có sao chép resource như stream, socket, file handle hoặc entity proxy không?
- Có giữ identity, cache, lazy-loading state và trạng thái nội bộ không?

convertValue không đưa ra một hợp đồng tổng quát cho các câu hỏi này. Nó chuyển đổi representation mà Jackson serialize được, sau đó tạo kiểu đích theo deserializer và cấu hình hiện tại.

### 2.1. Field bị bỏ qua có thể biến mất

Ví dụ:

```java
public class User {
    private String username;
    private String passwordHash;
    private String internalNote;

    @JsonIgnore
    public String getPasswordHash() {
        return passwordHash;
    }

    // Other getters and setters
}
```

Khi serialize User, property passwordHash bị loại khỏi representation. Nếu chuyển đổi sang một kiểu có field tương ứng, Jackson cũng không thể phục hồi giá trị đã không được ghi vào buffer.

Các cơ chế khác cũng có thể làm mất dữ liệu:

- JsonIgnore hoặc JsonIgnoreProperties.
- JsonInclude loại null hoặc empty value.
- JsonView khi writer dùng view giới hạn.
- JsonFilter hoặc custom property filter.
- Custom serializer chỉ ghi một phần object.
- Getter không được phát hiện hoặc bị naming strategy đổi tên.
- Property write-only/read-only hoặc cấu hình access khác nhau.

Do đó, một lần chuyển đổi thành công không chứng minh mọi field nguồn đã được sao chép.

### 2.2. Quan hệ tham chiếu có thể thay đổi

Giả sử hai property cùng trỏ tới một object:

```java
Address shared = new Address("Da Nang");

Customer customer = new Customer();
customer.setBillingAddress(shared);
customer.setShippingAddress(shared);
```

Trong graph Java nguồn, hai property có cùng reference. Representation JSON thông thường mô tả giá trị của từng property; nó không tự biểu diễn việc hai property đang trỏ tới cùng một địa chỉ trong heap.

Khi deserialize, Jackson có thể tạo hai instance Address độc lập. Khi đó:

```java
copy.getBillingAddress() != copy.getShippingAddress()
```

dù hai object có cùng dữ liệu. Nếu ứng dụng cần giữ aliasing hoặc object identity, phải cấu hình và kiểm thử cơ chế identity/reference phù hợp, chẳng hạn JsonIdentityInfo trong các graph được hỗ trợ. Không mặc định rằng một phép chuyển đổi thông thường giữ nguyên topology của graph.

### 2.3. Vòng tham chiếu và graph phức tạp

Một graph Java có thể có vòng:

```java
Department department = new Department();
Employee employee = new Employee();

department.setManager(employee);
employee.setDepartment(department);
```

JSON dạng cây không thể biểu diễn vòng tham chiếu trực tiếp nếu không có cơ chế identity/reference. Serializer mặc định có thể báo lỗi về self-reference hoặc recursion; cấu hình identity có thể biểu diễn tham chiếu theo ID. Nếu chuyển đổi không được cấu hình cho graph này, không nên coi convertValue là giải pháp clone.

### 2.4. Kiểu bất biến và tài nguyên ngoài

String, enum, một số kiểu value bất biến hoặc các giá trị được cache có thể được chia sẻ an toàn giữa nhiều object. Ngược lại, resource như InputStream, Socket, EntityManager, lazy proxy, thread hoặc file handle không thể được sao chép đúng nghĩa chỉ bằng cách chuyển representation JSON.

Một custom serializer có thể bỏ qua resource, ghi một ID hoặc ghi metadata thay thế. Target object khi đó không có cùng resource state với nguồn.

## 3. Khi nào convertValue có vẻ giống deep copy?

Với POJO đơn giản chỉ có các field dữ liệu, không có reference phức tạp, serializer mặc định ghi đủ property và target dùng các bean deserializer mặc định, convertValue(source, Source.class) thường tạo một object mới cùng dữ liệu. Các object con thông thường cũng có thể được tạo lại từ token.

Ví dụ:

```java
User source = new User();
source.setUsername("an");
source.setAddress(new Address("Da Nang"));

User copy = mapper.convertValue(source, User.class);
```

Trong một cấu hình thông thường, copy và source có thể là hai instance khác nhau, và Address bên trong cũng có thể là hai instance khác nhau. Điều đó có thể hữu ích cho một số tình huống, nhưng chỉ là kết quả của model và cấu hình cụ thể.

Nếu ứng dụng dựa vào hành vi này, hãy viết test kiểm tra chính những thuộc tính và quan hệ tham chiếu cần được bảo toàn. Đừng suy rộng từ một POJO đơn giản sang mọi loại object trong hệ thống.

### 3.1. Test dữ liệu và test identity là hai việc khác nhau

```java
assertEquals(source.getUsername(), copy.getUsername());
assertNotSame(source, copy);
```

Hai assertion này chỉ xác nhận dữ liệu scalar và root reference. Nếu yêu cầu là deep copy, cần kiểm tra cả object con mutable:

```java
assertNotSame(source.getAddress(), copy.getAddress());

source.getAddress().setCity("Hue");
assertEquals("Da Nang", copy.getAddress().getCity());
```

Nếu hai property phải tiếp tục chia sẻ cùng một object bên trong bản sao, test cả quan hệ đó:

```java
assertSame(copy.getBillingAddress(), copy.getShippingAddress());
```

Một test chỉ kiểm tra equals() không chứng minh object độc lập về reference. Một test chỉ kiểm tra assertNotSame ở root cũng không chứng minh các node con đã được sao chép sâu.

## 4. convertValue không phải kiểm tra nghiệp vụ

Jackson có thể kiểm tra một số điều kiện trong lúc binding:

- JSON có cú pháp hợp lệ.
- Token có thể chuyển sang kiểu Java đích.
- Creator property bắt buộc có mặt theo cấu hình.
- Custom deserializer chấp nhận cấu trúc và giá trị.
- Constructor hoặc factory được gọi trong quá trình tạo object có thể tự bảo vệ invariant.

Những kiểm tra đó không tương đương với validation nghiệp vụ.

Ví dụ, chuyển đổi sau có thể thành công:

```java
CreateTransferRequest request =
    mapper.convertValue(input, CreateTransferRequest.class);
```

Nhưng nó không xác nhận:

- Tài khoản nguồn thuộc về người dùng hiện tại.
- Tài khoản đích đang hoạt động.
- Số dư đủ để thực hiện chuyển tiền.
- Hạn mức ngày chưa bị vượt.
- Loại tiền được phép giữa hai tài khoản.
- Lệnh chưa bị gửi lặp.
- Người gọi có quyền thực hiện thao tác.

Đây là các điều kiện phụ thuộc trạng thái hệ thống, người dùng, dữ liệu lưu trữ hoặc use case. Jackson không tự biết các quy tắc đó.

### 4.1. Annotation validation không tự chạy chỉ vì convertValue

Ví dụ DTO:

```java
public record CreateAccountRequest(
    @NotBlank
    @Size(max = 40)
    String accountName,

    @Email
    String contactEmail
) {}
```

Các annotation Bean Validation mô tả constraint, nhưng lời gọi mapper.convertValue(...) không tự động gọi Validator.validate(...). Việc tạo record thành công không chứng minh các constraint trên đã được kiểm tra.

Trong Spring MVC, @Valid có thể kích hoạt validation ở request boundary khi method/controller được cấu hình phù hợp. Nếu tự gọi convertValue trong service hoặc một job nền, phải gọi validator rõ ràng nếu cần Bean Validation.

### 4.2. Constructor validation có phạm vi khác

Nếu constructor kiểm tra accountName không được blank, lỗi có thể xảy ra ngay khi Jackson tạo target. Đây là bảo vệ invariant của object, và có giá trị ở mọi đường tạo object.

Nhưng constructor thường không thể tự xác nhận số dư, quyền truy cập hoặc trạng thái tài khoản từ database mà không đưa dependency và side effect vào model. Những điều kiện đó thuộc application service/domain service và phải được kiểm tra trong use case.

Không nên đặt truy vấn database, gọi API hoặc thực hiện giao dịch bên ngoài trong constructor chỉ để làm convertValue có vẻ như một bước validation đầy đủ.

## 5. Phân biệt các loại validation

Một pipeline dữ liệu có thể có nhiều lớp kiểm tra:

| Lớp | Câu hỏi được trả lời | Ví dụ |
|---|---|---|
| Parser | JSON có đúng cú pháp và giới hạn tài nguyên không? | Dấu ngoặc, nesting depth, token length |
| Binding | Token có ánh xạ được sang kiểu Java không? | String, integer, enum, required creator |
| DTO validation | Request có thỏa constraint đầu vào không? | NotBlank, Size, Email |
| Domain invariant | Object có thể tồn tại hợp lệ không? | Amount dương, list không rỗng |
| Use-case/business rule | Hành động có được phép ở thời điểm này không? | Đủ số dư, đúng owner, hạn mức |

convertValue chủ yếu thực hiện binding/conversion. Nó có thể gọi constructor hoặc custom deserializer, nhưng không thay thế các lớp validation còn lại.

## 6. Cách dùng convertValue an toàn cho mapping DTO

Nếu hai kiểu có cùng ý nghĩa và cấu trúc tương thích, convertValue có thể giảm code mapping:

```java
public record CustomerInput(String name, String email) {}
public record CustomerView(String name, String email) {}

CustomerView view = mapper.convertValue(input, CustomerView.class);
```

Nên dùng khi:

- Mapping là chuyển đổi cấu trúc đơn giản.
- Quy tắc tên và kiểu property rõ ràng.
- Không cần kiểm tra trạng thái bên ngoài.
- Không cần giữ reference identity.
- Mất field ngoài representation đích là có chủ đích.

Không nên dùng nếu việc mapping cần quy tắc nghiệp vụ, chuẩn hóa phức tạp, tra cứu dữ liệu, quyền truy cập hoặc quyết định có điều kiện theo trạng thái hệ thống.

### 6.1. Dùng TypeReference hoặc JavaType cho generic

Do Java type erasure, nếu target là generic type như Map<String, UserView> hoặc List<UserView>, hãy cung cấp đầy đủ kiểu:

```java
Map<String, UserView> result = mapper.convertValue(
    source,
    new TypeReference<Map<String, UserView>>() {}
);
```

Hoặc:

```java
JavaType mapType = mapper.getTypeFactory()
    .constructMapType(
        Map.class,
        String.class,
        UserView.class
    );

Map<String, UserView> result = mapper.convertValue(source, mapType);
```

Nếu chỉ truyền Map.class hoặc List.class, Jackson không có đủ thông tin tĩnh về kiểu phần tử và có thể tạo các giá trị dạng map/list/scalar tổng quát thay vì kiểu domain mong muốn.

### 6.2. Xử lý lỗi conversion

Nếu source không thể ánh xạ sang target, convertValue thường báo lỗi runtime dạng IllegalArgumentException với nguyên nhân mapping ở bên trong. Hãy chuyển lỗi này thành lỗi input phù hợp ở API boundary, đồng thời giữ nguyên cause cho logging nội bộ.

Không bắt mọi exception rồi trả target rỗng hoặc null. Cách đó biến payload không hợp lệ thành trạng thái có vẻ hợp lệ và làm lỗi khó tìm hơn.

## 7. Những yếu tố cấu hình có thể làm thay đổi kết quả

Vì convertValue đi qua cơ chế serialize và deserialize, kết quả phụ thuộc cấu hình mapper.

### 7.1. Annotation và visibility

JsonProperty, JsonIgnore, JsonAlias, JsonInclude, access mode và visibility rules có thể thay đổi property được ghi hoặc đọc. Source có getter được serialize nhưng target không có setter/creator phù hợp có thể làm field bị bỏ qua hoặc gây lỗi tùy cấu hình.

Không giả định rằng mọi field Java đều được chuyển chỉ vì hai class có field cùng tên. Jackson hoạt động dựa trên property model mà nó phát hiện, không chỉ dựa vào reflection trên field.

### 7.2. Naming strategy

Nếu mapper dùng snake case:

```java
mapper.setPropertyNamingStrategy(
    PropertyNamingStrategies.SNAKE_CASE
);
```

thì displayName có thể được biểu diễn bằng display_name. Mapping phụ thuộc tên property JSON và metadata của source/target. Nếu hai kiểu dùng tên khác nhau, có thể cần JsonProperty, alias hoặc mapper riêng.

### 7.3. Custom serializer và deserializer

Custom serializer có thể chỉ ghi một phần source; custom deserializer có thể tạo target theo quy tắc riêng. Khi convertValue dùng mapper đã đăng ký các component đó, chúng có thể được gọi trong quá trình chuyển đổi.

Điều này có thể hữu ích, nhưng cũng khiến conversion có hành vi ngoài dự đoán nếu serializer/deserializer chứa side effect, đọc trạng thái toàn cục hoặc phụ thuộc context của request. Serializer nên tập trung vào representation; deserializer nên chuyển dữ liệu và kiểm tra cấu trúc/invariant phù hợp, không nên thực hiện thao tác nghiệp vụ bên ngoài.

### 7.4. Filter và view

Nếu writer/filter/view áp dụng trong đường serialize, một số property có thể không xuất hiện trong representation trung gian. Không dùng mapper có filter public để tạo bản sao nội bộ nếu filter đó cố ý loại field.

Khi cần nhiều mục đích, tạo cấu hình mapper/writer tách biệt và đặt tên rõ cho từng use case. Đừng thay đổi cấu hình mapper dùng chung theo từng request.

## 8. Side effect khi chuyển đổi

Mặc dù convertValue thường được dùng như một phép chuyển đổi dữ liệu, nó vẫn có thể gọi code của ứng dụng:

- Getter của source có thể tính toán hoặc thực hiện lazy loading.
- Custom serializer có thể gọi service, ghi log hoặc mutate state nếu được viết không đúng trách nhiệm.
- Constructor/setter của target có thể thay đổi state hoặc ném lỗi.
- Custom deserializer có thể truy cập context hoặc gọi logic phụ.

Ví dụ getter:

```java
public String getDisplayName() {
    auditCounter.increment();
    return firstName + " " + lastName;
}
```

Khi Jackson serialize object, getter có thể được gọi. Nếu conversion được thực hiện nhiều lần trong vòng lặp hoặc trong đường nóng, side effect có thể gây khó hiểu và hiệu năng kém.

Giữ getter, serializer và constructor càng ít side effect càng tốt. Các thao tác như ghi audit, gửi message, cập nhật database hoặc kiểm tra quyền nên được thực hiện rõ ràng ở application service.

## 9. convertValue không phải cách cập nhật hoặc merge object

Một số code dùng convertValue để chuyển patch/request thành entity hiện có:

```java
User updated = mapper.convertValue(request, User.class);
```

Đoạn code này tạo target từ representation của request. Nó không tự hiểu rằng field thiếu có nghĩa giữ giá trị cũ, explicit null có nghĩa xóa, còn empty có nghĩa đặt rỗng. Nếu request chỉ chứa một phần field, các field còn lại có thể trở thành null/default hoặc bị bỏ theo constructor/configuration.

Để cập nhật một object hiện có, hãy định nghĩa rõ semantics của update:

- PUT thường biểu diễn một representation hoàn chỉnh theo contract.
- PATCH thường chỉ biểu diễn các thay đổi được yêu cầu.
- Missing và explicit null cần được phân biệt nếu chúng có ý nghĩa khác nhau.
- Nested object và collection cần chính sách replace, merge hoặc append cụ thể.

Jackson có API update như readerForUpdating/updateValue và annotation JsonMerge cho một số trường hợp merge. Những API đó có semantics riêng theo kiểu property và cấu hình; chúng cũng không tự thực hiện business validation hay bảo đảm deep merge cho mọi object graph. Hãy viết logic update domain tường minh khi hành vi thay đổi dữ liệu quan trọng.

Ví dụ patch DTO:

```java
public record UpdateProfileRequest(
    JsonNullable<String> displayName,
    JsonNullable<String> phone
) {}
```

Một presence wrapper như JsonNullable (từ thư viện OpenAPI/nullable support tương ứng) có thể phân biệt property không được gửi với property được gửi null. Nếu không dùng thư viện, có thể tạo kiểu FieldUpdate<T> riêng với cờ presence.

Sau đó service áp dụng ý nghĩa:

```java
if (request.displayName().isPresent()) {
    profile.changeDisplayName(request.displayName().get());
}

if (request.phone().isPresent()) {
    profile.changePhone(request.phone().orElse(null));
}
```

Ví dụ chỉ minh họa presence semantics; API thực tế phải xác định rõ null được phép hay không và domain method chịu trách nhiệm kiểm tra invariant.

## 10. Khi nào cần deep copy thật sự?

Trước khi viết copy logic, xác định mục tiêu:

| Mục tiêu | Cách phù hợp |
|---|---|
| Tạo DTO response khác shape | Mapper tường minh hoặc convertValue nếu mapping đơn giản |
| Tạo snapshot bất biến | Copy constructor/factory và collection immutable |
| Tách graph mutable khỏi source | Deep-copy logic có chủ đích cho từng kiểu node |
| Nhân bản entity có identity/persistence state | Thiết kế clone domain riêng; không sao chép tùy tiện ID/version/proxy |
| Lưu trữ hoặc truyền dữ liệu | Serialization theo contract; không gọi đó là clone |
| Giữ graph có shared references/cycles | Copy algorithm có identity map hoặc cơ chế reference rõ ràng |

### 10.1. Copy constructor

Với model nhỏ, copy constructor dễ đọc và thể hiện rõ chính sách:

```java
public final class ProfileSnapshot {
    private final String displayName;
    private final AddressSnapshot address;
    private final List<String> tags;

    public ProfileSnapshot(Profile source) {
        this.displayName = source.getDisplayName();
        this.address = source.getAddress() == null
            ? null
            : new AddressSnapshot(source.getAddress());
        this.tags = List.copyOf(source.getTags());
    }
}
```

Ở đây:

- String được chia sẻ vì bất biến.
- Address được sao chép thành kiểu snapshot riêng.
- List được tạo mới và không thể sửa.
- Quy tắc không sao chép entity ID hoặc resource nội bộ có thể được thể hiện rõ trong constructor.

### 10.2. Deep copy graph có identity map

Nếu graph có shared reference hoặc cycle, copy algorithm cần map từ object nguồn sang object bản sao:

```java
IdentityHashMap<Object, Object> copies = new IdentityHashMap<>();
```

Khi gặp một node:

1. Nếu node đã có trong identity map, trả về bản sao đã tạo.
2. Nếu chưa có, tạo object rỗng/khởi tạo phù hợp.
3. Đăng ký source → copy trước khi đi sâu vào các node con.
4. Sao chép các property và collection theo chính sách.

Đăng ký bản sao trước khi đệ quy giúp xử lý cycle. Dùng IdentityHashMap thay vì HashMap khi việc nhận diện phải dựa trên object identity chứ không dựa trên equals().

Không có một thuật toán generic an toàn cho mọi class Java. Mỗi loại node có thể cần chính sách riêng cho immutable values, entity identity, resource, proxy và collection.

### 10.3. Serialization round-trip chỉ phù hợp khi contract cho phép

Một số ứng dụng dùng:

```java
byte[] bytes = mapper.writeValueAsBytes(source);
Target copy = mapper.readValue(bytes, Target.class);
```

Đây là serialize rồi deserialize thực sự. Nó hữu ích khi mục tiêu là tạo representation JSON hoặc kiểm tra tương thích schema. Nhưng nó vẫn chịu các giới hạn của representation: field bị ignore có thể mất, identity có thể thay đổi, vòng tham chiếu cần cấu hình, kiểu resource không thể clone và business validation không tự chạy.

Nếu mục tiêu là clone, hãy dùng copy API được định nghĩa cho model đó. Nếu mục tiêu là kiểm tra contract JSON, hãy test serialize/deserialize round-trip như một test riêng và gọi đúng tên nó.

## 11. Dùng mapper tường minh cho quy tắc chuyển đổi quan trọng

Khi mapping cần đổi tên, chuẩn hóa hoặc tính toán, mapper tường minh giúp code review được:

```java
public final class UserMapper {
    public UserProfile toProfile(User user) {
        return new UserProfile(
            user.getId(),
            normalizeName(user.getFirstName(), user.getLastName()),
            user.getEmail()
        );
    }

    private String normalizeName(String first, String last) {
        return (first + " " + last).trim();
    }
}
```

MapStruct cũng có thể sinh code mapping tĩnh và giảm boilerplate. Tuy vậy, MapStruct hay mapper thủ công vẫn chỉ là mapping; chúng không tự xác nhận mọi quy tắc nghiệp vụ nếu không được thiết kế để gọi validation/domain method.

Đối với mapping quan trọng, nên:

- Viết tên method theo ý nghĩa nghiệp vụ (toPublicProfile, toPaymentCommand).
- Không dùng một mapper tổng quát cho mọi boundary.
- Kiểm soát field nhạy cảm và field bị bỏ.
- Đặt validation ở DTO/domain/use-case layer.
- Test cả field mapping và các trường hợp không hợp lệ.

## 12. Kiểm tra DTO bằng Bean Validation

Ví dụ:

```java
public record CreateTransferRequest(
    @NotBlank
    @Size(max = 34)
    String sourceAccount,

    @NotBlank
    @Size(max = 34)
    String destinationAccount,

    @NotNull
    @DecimalMin("0.01")
    @Digits(integer = 12, fraction = 2)
    BigDecimal amount
) {}
```

Gọi validation một cách tường minh nếu code không chạy trong Spring MVC request pipeline:

```java
Set<ConstraintViolation<CreateTransferRequest>> violations =
    validator.validate(request);

if (!violations.isEmpty()) {
    throw new ConstraintViolationException(violations);
}
```

Bean Validation phù hợp cho điều kiện trên dữ liệu request như blank, length, range, format và class-level relationship. Nó không tự kiểm tra database hoặc quyền truy cập.

Đừng nhầm JsonProperty(required = true) với Bean Validation. required chủ yếu có ý nghĩa metadata cho creator properties trong một số đường databinding; nó không thay thế đầy đủ validation trên mọi mutable field. Nếu cần field bắt buộc, hãy dùng constructor/creator phù hợp và/hoặc validator rõ ràng.

## 13. Kiểm tra quy tắc nghiệp vụ ở use-case layer

Một chuyển khoản có thể có DTO hợp lệ về mặt cấu trúc nhưng không hợp lệ về nghiệp vụ:

```java
public TransferReceipt transfer(
        AuthenticatedUser actor,
        CreateTransferRequest request) {

    validator.validate(request);

    Account source = accountRepository.requireByNumber(request.sourceAccount());
    Account destination =
        accountRepository.requireByNumber(request.destinationAccount());

    authorizationService.requireCanTransfer(actor, source);
    transferPolicy.validateAllowed(source, destination, request.amount());

    source.debit(request.amount());
    destination.credit(request.amount());

    return transferRepository.save(source, destination, request.amount());
}
```

Ví dụ này minh họa thứ tự trách nhiệm:

1. Validate dữ liệu request.
2. Tải domain state cần thiết.
3. Xác thực quyền của actor.
4. Kiểm tra quy tắc use case.
5. Thực hiện domain operation và lưu kết quả trong transaction phù hợp.

convertValue không thể thay thế các bước này vì chúng phụ thuộc actor, database, thời điểm và trạng thái giao dịch.

## 14. Cấu hình mapper riêng cho từng boundary

Một mapper dùng chung có thể chứa:

- Naming strategy.
- Custom serializer/deserializer.
- Mix-in.
- Filter provider/view.
- Module cho date/time, money hoặc domain types.
- Coercion và unknown-property policy.

Nếu dùng cùng mapper để chuyển entity nội bộ thành DTO public, một serializer/filter được cấu hình cho output public có thể làm mất field khi chuyển đổi nội bộ. Ngược lại, mapper nội bộ có thể đưa field không nên có vào DTO public nếu mapping quá rộng.

Hãy tạo cấu hình theo boundary khi cần:

```java
ObjectMapper apiMapper = JsonMapper.builder()
    .addModule(new JavaTimeModule())
    .build();

ObjectMapper internalMapper = JsonMapper.builder()
    .addModule(new JavaTimeModule())
    .addModule(internalModule)
    .build();
```

Đây là ví dụ khái niệm. Không nhất thiết phải có nhiều mapper nếu cấu hình giống nhau; mục tiêu là tránh một cấu hình presentation hoặc security-specific vô tình ảnh hưởng một use case khác.

## 15. Hiệu năng và bộ nhớ

convertValue thường tiết kiệm hơn tạo JSON string trung gian, nhưng vẫn có chi phí serialize và deserialize:

- Getter và serializer của source được thực thi.
- Token được ghi vào buffer.
- Deserializer tạo target và các object con cần thiết.
- Collection/map có thể được cấp phát.
- Custom serializer/deserializer có thể làm tăng CPU hoặc tạo object phụ.

Không dùng convertValue trong vòng lặp lớn nếu mapping tường minh đơn giản hơn và đã được chứng minh hiệu năng tốt hơn. Ngược lại, không tự viết mapper thủ công chỉ dựa trên giả định nhanh hơn; đo bằng workload thực tế.

Với payload hoặc collection rất lớn, ưu tiên streaming hoặc xử lý từng phần tử. Tránh tạo thêm Map<String, Object>/JsonNode toàn bộ chỉ để chuyển đổi nếu đích có thể được đọc trực tiếp.

## 16. Những lỗi thường gặp

| Triệu chứng | Nguyên nhân | Cách xử lý |
|---|---|---|
| Bản sao thiếu field | Serializer, annotation hoặc filter đã loại property | Kiểm tra representation nguồn trước khi deserialize. |
| Object con vẫn dùng chung reference | Giả định conversion luôn deep-copy graph | Xác định copy contract và test identity từng node mutable. |
| Shared reference bị tách thành hai object | JSON tree không giữ aliasing mặc định | Dùng identity/reference metadata hoặc copy algorithm có identity map. |
| Chuyển đổi thành công nhưng request sai nghiệp vụ | Nhầm binding với business validation | Gọi DTO validator và use-case/domain checks riêng. |
| NotBlank không được thực thi | Chỉ gọi convertValue | Gọi Bean Validator hoặc dùng validation pipeline của framework. |
| Field thiếu bị đặt null/default | Dùng conversion cho partial update | Dùng patch DTO có presence semantics và apply update rõ ràng. |
| Mapper public làm mất dữ liệu nội bộ | Filter/view/serializer dùng chung | Tách mapper/writer theo boundary và mục đích. |
| Mapping chạy getter hoặc code phụ không mong muốn | Getter/custom serializer có side effect | Giữ mapping code thuần và tách side effect sang service. |
| Generic collection có phần tử kiểu Map | Chỉ truyền List.class hoặc Map.class | Dùng TypeReference hoặc JavaType đầy đủ. |
| Lỗi conversion bị che giấu | Catch exception rồi trả object rỗng/null | Chuyển lỗi thành validation/mapping error rõ ràng. |

## 17. Kiểm thử conversion đúng mục tiêu

Không có một test duy nhất chứng minh convertValue vừa clone sâu vừa validate nghiệp vụ. Hãy tách test theo contract.

### 17.1. Test mapping field

```java
@Test
void convertsUserToProfile() {
    User source = new User("u-17", "an", "an@example.test");

    UserProfile result = mapper.convertValue(source, UserProfile.class);

    assertEquals("u-17", result.id());
    assertEquals("an", result.username());
    assertEquals("an@example.test", result.email());
}
```

### 17.2. Test field bị loại theo representation

Tạo source có cả public field và internal field. Chạy conversion bằng đúng mapper/filter được sử dụng trong production và xác nhận field bị loại hoặc được giữ theo contract. Test này phát hiện cấu hình mapper làm mất dữ liệu ngoài dự kiến.

### 17.3. Test deep-copy requirements

Nếu use case thật sự cần copy sâu, kiểm tra:

- Root object là instance khác.
- Mỗi nested mutable node cần độc lập là instance khác.
- Thay đổi source không làm thay đổi copy.
- Shared reference cần giữ được topology đã định nghĩa.
- Vòng tham chiếu được giữ hoặc bị từ chối theo policy.
- Immutable value có thể được chia sẻ.

### 17.4. Test validation độc lập

Gọi Bean Validator và domain factory với dữ liệu sai. Xác nhận:

- DTO constraint bị phát hiện.
- Constructor/factory từ chối invariant sai.
- Use case từ chối quyền hoặc trạng thái không hợp lệ.
- convertValue thành công không làm test validation tự động pass.

### 17.5. Test patch semantics

Với PATCH DTO, test riêng:

- Field không được gửi.
- Field được gửi với null.
- Field được gửi với empty string.
- Nested object thiếu một property.
- Collection rỗng và collection null.

Xác nhận update giữ, xóa, thay thế hoặc merge theo contract; không suy ra semantics từ kết quả mặc định của convertValue.

## 18. Quy trình chọn công cụ

1. Nếu cần đổi shape dữ liệu đơn giản giữa hai kiểu Jackson hiểu được, dùng convertValue.
2. Nếu cần generic target, truyền TypeReference hoặc JavaType đầy đủ.
3. Nếu cần clone sâu, định nghĩa graph copy contract và dùng copy constructor/factory hoặc copy algorithm có identity map.
4. Nếu cần tạo snapshot, ưu tiên DTO/value object bất biến và collection immutable.
5. Nếu cần mapping có quy tắc hoặc tính toán, dùng mapper tường minh/MapStruct và viết test cho từng quy tắc.
6. Nếu cần validate request, dùng Bean Validation hoặc custom validation ở boundary.
7. Nếu cần bảo vệ domain invariant, đặt điều kiện trong constructor/factory/domain method.
8. Nếu cần kiểm tra quyền hoặc trạng thái bên ngoài, thực hiện trong use-case/application service.
9. Nếu cần update/patch, định nghĩa rõ missing/null/empty và merge semantics; không dùng conversion như phép merge ngầm.
10. Test mapping, identity, validation, field loss và update behavior như các yêu cầu độc lập.

ObjectMapper.convertValue là công cụ chuyển đổi cấu trúc tiện lợi, không phải hợp đồng sao chép sâu và cũng không phải validator nghiệp vụ. Hãy dùng nó khi representation nguồn và đích tương thích, đồng thời hiểu rõ serializer/deserializer đang tham gia. Khi cần object graph độc lập, hãy định nghĩa chính sách copy cụ thể; khi cần dữ liệu hợp lệ, hãy xác nhận constraint và business rule ở đúng tầng trước khi thực hiện use case.
