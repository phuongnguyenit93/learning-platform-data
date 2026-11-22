# Tách cách nhìn dữ liệu bằng JsonView

Một lớp Java có thể được dùng ở nhiều ngữ cảnh API nhưng mỗi ngữ cảnh chỉ nên hiển thị một tập thuộc tính nhất định. Ví dụ, màn hình công khai chỉ cần mã và tên người dùng; màn hình nội bộ cần thêm email; màn hình quản trị có thể cần thêm trạng thái kiểm tra. Nếu tạo một DTO riêng cho từng ngữ cảnh, số lớp dữ liệu có thể tăng nhanh và các thuộc tính chung bị lặp lại.

Jackson cung cấp @JsonView để mô tả các cách nhìn khác nhau trên cùng một mô hình Java. Ứng dụng khai báo các view marker, gắn thuộc tính vào một hoặc nhiều view, rồi chọn view khi đọc hoặc ghi JSON. Nhờ vậy, cùng một đối tượng có thể được tuần tự hóa theo nhiều hợp đồng đầu ra khác nhau.

JsonView là cơ chế lọc thuộc tính trong quá trình databinding. Nó không tạo bản sao đối tượng, không thay đổi trạng thái Java và cũng không tự động trở thành cơ chế phân quyền. Phần còn lại của bài tập trung vào cách định nghĩa view, chọn view cho từng thao tác và kiểm soát các trường hợp dễ gây nhầm lẫn.

## 1. JsonView giải quyết vấn đề gì?

Giả sử ứng dụng có mô hình người dùng:

~~~java
public class User {
    private Long id;
    private String displayName;
    private String email;
    private String internalNote;

    // Constructor, getter và setter
}
~~~

Các ngữ cảnh có thể cần dữ liệu khác nhau:

| Ngữ cảnh | Thuộc tính cần dùng |
|---|---|
| Trang công khai | id, displayName |
| Khu vực nội bộ | id, displayName, email |
| Công cụ quản trị | id, displayName, email, internalNote |

Nếu luôn ghi toàn bộ User, API công khai có nguy cơ trả các thuộc tính nội bộ. Nếu tạo PublicUser, InternalUser và AdminUser riêng, ứng dụng phải duy trì nhiều lớp có cấu trúc gần giống nhau.

Với JsonView, ta có thể gắn mỗi thuộc tính vào view phù hợp và chọn view lúc serialize:

~~~java
String json = mapper
    .writerWithView(Views.Public.class)
    .writeValueAsString(user);
~~~

Jackson chỉ ghi các thuộc tính được phép xuất hiện trong view đang hoạt động, theo chính sách view inclusion của mapper.

## 2. Khai báo view marker

View thường là interface hoặc class rỗng, chỉ dùng làm nhãn. Chúng không chứa dữ liệu và không cần tạo instance.

~~~java
public final class Views {
    private Views() {
    }

    public interface Public {
    }

    public interface Internal extends Public {
    }

    public interface Admin extends Internal {
    }
}
~~~

Trong ví dụ, view được tổ chức theo quan hệ kế thừa:

~~~text
Public
  ▲
  │ extends
Internal
  ▲
  │ extends
Admin
~~~

Internal mở rộng Public, còn Admin mở rộng Internal. Vì vậy, view nội bộ bao gồm các thuộc tính dành cho Public và các thuộc tính dành riêng cho Internal; view Admin bao gồm cả hai nhóm trước và nhóm Admin.

Kế thừa view giúp biểu diễn quan hệ "view rộng hơn bao gồm các thuộc tính của view nền". Nếu các view hoàn toàn độc lập, có thể khai báo các interface không kế thừa nhau.

## 3. Gắn thuộc tính vào view bằng JsonView

JsonView nhận một hoặc nhiều lớp view. Có thể đặt annotation trên field, getter, setter hoặc thành phần creator phù hợp. Ví dụ dưới đây gắn annotation trên field:

~~~java
import com.fasterxml.jackson.annotation.JsonView;

public class User {
    @JsonView(Views.Public.class)
    private Long id;

    @JsonView(Views.Public.class)
    private String displayName;

    @JsonView(Views.Internal.class)
    private String email;

    @JsonView(Views.Admin.class)
    private String internalNote;

    public User() {
    }

    public User(Long id, String displayName, String email,
                String internalNote) {
        this.id = id;
        this.displayName = displayName;
        this.email = email;
        this.internalNote = internalNote;
    }

    public Long getId() {
        return id;
    }

    public String getDisplayName() {
        return displayName;
    }

    public String getEmail() {
        return email;
    }

    public String getInternalNote() {
        return internalNote;
    }

    public void setId(Long id) {
        this.id = id;
    }

    public void setDisplayName(String displayName) {
        this.displayName = displayName;
    }

    public void setEmail(String email) {
        this.email = email;
    }

    public void setInternalNote(String internalNote) {
        this.internalNote = internalNote;
    }
}
~~~

Jackson hợp nhất thông tin thuộc tính được phát hiện từ field, getter, setter và các thành phần liên quan thành property logic. Để tránh cấu hình khó hiểu, nên đặt annotation nhất quán và không gán các view mâu thuẫn trên những thành phần khác nhau của cùng property.

Với view đã khai báo:

- id và displayName thuộc Public.
- email thuộc Internal.
- internalNote thuộc Admin.

Do Internal kế thừa Public, khi chọn Internal, Jackson cũng thấy id và displayName. Khi chọn Admin, Jackson thấy cả ba nhóm.

## 4. Chọn view khi tuần tự hóa bằng ObjectWriter

ObjectMapper tạo ObjectWriter có view bằng writerWithView(Class<?>). Writer này giữ cấu hình cho thao tác ghi và có thể được dùng nhiều lần:

~~~java
ObjectMapper mapper = new ObjectMapper();

User user = new User(
    12L,
    "Mai Nguyen",
    "mai@example.com",
    "Tài khoản cần kiểm tra"
);

String publicJson = mapper
    .writerWithView(Views.Public.class)
    .writeValueAsString(user);

String internalJson = mapper
    .writerWithView(Views.Internal.class)
    .writeValueAsString(user);

String adminJson = mapper
    .writerWithView(Views.Admin.class)
    .writeValueAsString(user);
~~~

Với cấu hình view inclusion nghiêm ngặt, kết quả có thể hình dung như sau:

~~~json
{
  "id": 12,
  "displayName": "Mai Nguyen"
}
~~~

Đây là kết quả của Public view.

~~~json
{
  "id": 12,
  "displayName": "Mai Nguyen",
  "email": "mai@example.com"
}
~~~

Đây là kết quả của Internal view.

~~~json
{
  "id": 12,
  "displayName": "Mai Nguyen",
  "email": "mai@example.com",
  "internalNote": "Tài khoản cần kiểm tra"
}
~~~

Đây là kết quả của Admin view.

Các đoạn JSON minh họa tập thuộc tính được chọn. Thứ tự thuộc tính thực tế phụ thuộc thứ tự phát hiện property và cấu hình serialization; client không nên dựa vào thứ tự field trong object JSON.

## 5. Chọn view khi giải tuần tự hóa bằng ObjectReader

JsonView cũng có thể giới hạn các thuộc tính được nhận khi đọc JSON. Dùng readerWithView(Class<?>) để tạo reader có view:

~~~java
ObjectReader publicReader = mapper
    .readerWithView(Views.Public.class)
    .forType(User.class);

User user = publicReader.readValue(json);
~~~

Ví dụ JSON đầu vào:

~~~json
{
  "id": 12,
  "displayName": "Mai Nguyen",
  "email": "mai@example.com",
  "internalNote": "private"
}
~~~

Nếu active view là Public và cấu hình view inclusion nghiêm ngặt, các thuộc tính chỉ thuộc Internal hoặc Admin sẽ không được gán qua view đó. Các thuộc tính được đánh dấu Public vẫn được đọc.

Có thể dùng view khác cho các luồng nhập:

~~~java
User publicInput = mapper
    .readerWithView(Views.Public.class)
    .forType(User.class)
    .readValue(json);

User internalInput = mapper
    .readerWithView(Views.Internal.class)
    .forType(User.class)
    .readValue(json);
~~~

Điều này hữu ích khi một loại dữ liệu được dùng cho nhiều loại request nhưng mỗi luồng chỉ được phép cập nhật một nhóm thuộc tính. Tuy nhiên, cần nhớ rằng view điều khiển databinding; quy tắc ai được phép cập nhật dữ liệu vẫn phải được xác định ở tầng xác thực và phân quyền của ứng dụng.

## 6. View khi không có active view

JsonView chỉ có tác dụng lọc khi thao tác databinding có một active view. Nếu gọi writeValueAsString() trực tiếp mà không chọn view, Jackson thông thường ghi các thuộc tính như một lần serialize bình thường; annotation không tự động làm ẩn trường.

~~~java
String json = mapper.writeValueAsString(user);
~~~

Lời gọi trên không tương đương với:

~~~java
String json = mapper
    .writerWithView(Views.Public.class)
    .writeValueAsString(user);
~~~

Đây là điểm cần đặc biệt chú ý khi cùng một lớp được trả về từ nhiều endpoint. Nếu endpoint công khai quên chọn view, các thuộc tính có thể xuất hiện theo cách serialize mặc định.

## 7. DEFAULT_VIEW_INCLUSION

Một thuộc tính không có JsonView có thể được đưa vào tất cả view đang hoạt động hoặc bị loại khỏi các view đó, tùy cấu hình MapperFeature.DEFAULT_VIEW_INCLUSION.

Trong cấu hình Jackson Databind độc lập, feature này thường được bật mặc định. Khi bật, các property không khai báo view vẫn được coi là thuộc mọi view. Khi tắt, property không có annotation view sẽ không được đưa vào thao tác có active view.

Có thể cấu hình:

~~~java
ObjectMapper mapper = JsonMapper.builder()
    .disable(MapperFeature.DEFAULT_VIEW_INCLUSION)
    .build();
~~~

Hoặc với mapper đã tạo:

~~~java
mapper.disable(MapperFeature.DEFAULT_VIEW_INCLUSION);
~~~

Ví dụ thêm một thuộc tính không gắn view:

~~~java
public class User {
    @JsonView(Views.Public.class)
    private Long id;

    private String legacyCode;
}
~~~

Khi ghi với Public view:

- Nếu DEFAULT_VIEW_INCLUSION bật, legacyCode có thể xuất hiện dù không có JsonView.
- Nếu DEFAULT_VIEW_INCLUSION tắt, legacyCode bị loại khỏi thao tác có active view.

Một số framework, chẳng hạn cấu hình ObjectMapper tự động của ứng dụng, có thể thay đổi giá trị mặc định. Không nên suy đoán từ giá trị mặc định của Jackson thuần; hãy kiểm tra mapper thực tế được inject vào ứng dụng.

Với hợp đồng API cần kiểm soát rõ field, thường nên cân nhắc tắt DEFAULT_VIEW_INCLUSION và đánh dấu tường minh các thuộc tính được phép xuất hiện trong từng view.

## 8. Kết hợp nhiều view trên một thuộc tính

Một thuộc tính có thể xuất hiện trong nhiều view độc lập bằng cách truyền nhiều class vào JsonView:

~~~java
public class Report {
    @JsonView({Views.Public.class, AuditView.class})
    private String reportTitle;

    @JsonView(AuditView.class)
    private String auditId;

    @JsonView(Views.Public.class)
    private String summary;
}

public interface AuditView {
}
~~~

reportTitle được đánh dấu cho cả Public và AuditView. auditId chỉ dành cho AuditView, còn summary chỉ dành cho Public.

Một active view đơn lẻ không tự động có nghĩa là hợp của mọi view độc lập. Nếu cần một cách nhìn bao gồm nhiều view không có quan hệ kế thừa, hãy tạo một composite view:

~~~java
public interface PublicAuditView
        extends Views.Public, AuditView {
}
~~~

Sau đó chọn composite view:

~~~java
String json = mapper
    .writerWithView(PublicAuditView.class)
    .writeValueAsString(report);
~~~

Kế thừa interface cho phép view tổng hợp bao gồm các nhóm thuộc tính đã được đánh dấu cho các view cha.

## 9. View kế thừa và quan hệ bao hàm

Kế thừa view nên được thiết kế theo chiều từ ít thông tin đến nhiều thông tin:

~~~java
public interface BasicView {
}

public interface StaffView extends BasicView {
}

public interface SupervisorView extends StaffView {
}
~~~

Các thuộc tính:

~~~java
public class Employee {
    @JsonView(BasicView.class)
    private String name;

    @JsonView(StaffView.class)
    private String workEmail;

    @JsonView(SupervisorView.class)
    private BigDecimal salary;
}
~~~

Kết quả theo quan hệ view:

| Active view | Thuộc tính có thể xuất hiện |
|---|---|
| BasicView | name |
| StaffView | name, workEmail |
| SupervisorView | name, workEmail, salary |

Không nên đảo ngược quan hệ kế thừa. Nếu BasicView kế thừa SupervisorView, view cơ bản sẽ mang theo các thuộc tính nhạy cảm của view cấp cao hơn, trái với ý nghĩa tên gọi.

## 10. Áp dụng view cho object lồng nhau

Active view được truyền trong quá trình serialize xuống các bean lồng nhau. Các thuộc tính của object con cũng được lọc theo annotation view của chính lớp con.

~~~java
public class Address {
    @JsonView(Views.Public.class)
    private String city;

    @JsonView(Views.Internal.class)
    private String street;

    @JsonView(Views.Admin.class)
    private String accessNote;
}

public class UserProfile {
    @JsonView(Views.Public.class)
    private String displayName;

    @JsonView(Views.Public.class)
    private Address address;
}
~~~

Khi ghi UserProfile với Public view, address được đưa vào và các field bên trong Address cũng được lọc theo Public view. Khi ghi với Internal view, city và street có thể xuất hiện do Internal kế thừa Public.

Một điểm khác cần phân biệt là annotation trên thuộc tính address điều khiển việc đưa cả thuộc tính address vào view. Annotation trên các thuộc tính city, street và accessNote điều khiển các trường bên trong object Address. Nếu address không thuộc active view, Jackson sẽ không xuất nhánh đó dù các field con có view phù hợp.

## 11. View trong collection và array

Collection thường chứa các bean có thuộc tính riêng. Khi serialize collection bằng một active view, Jackson áp dụng view đó cho từng phần tử bean:

~~~java
public class TeamResponse {
    @JsonView(Views.Public.class)
    private List<User> members;
}
~~~

Ví dụ ghi:

~~~java
String json = mapper
    .writerWithView(Views.Public.class)
    .writeValueAsString(teamResponse);
~~~

Thuộc tính members được đưa vào theo view của TeamResponse. Mỗi User trong danh sách tiếp tục được lọc theo annotation view của lớp User. Quy tắc tương tự áp dụng với array và các collection lồng nhau.

Với Map<String, User>, thuộc tính Map của bean chịu lọc theo view như một property; các value User là bean nên view cũng có thể áp dụng cho các property của từng User. Các key động của Map không phải property bean được gắn JsonView riêng. Nếu cần ẩn một số entry theo quyền, hãy lọc Map ở tầng nghiệp vụ hoặc dùng kiểu dữ liệu có cấu trúc phù hợp.

## 12. View trên getter, setter và creator

Jackson có thể phát hiện property từ field, getter, setter hoặc constructor/factory. JsonView có thể được đặt trên các thành phần này để mô tả view của property.

Ví dụ gắn view trên getter:

~~~java
public class Account {
    private String username;
    private String password;

    @JsonView(Views.Public.class)
    public String getUsername() {
        return username;
    }

    public void setUsername(String username) {
        this.username = username;
    }

    @JsonView(Views.Internal.class)
    public String getPassword() {
        return password;
    }

    public void setPassword(String password) {
        this.password = password;
    }
}
~~~

Vị trí annotation và cách Jackson hợp nhất metadata có thể ảnh hưởng đến property logic. Khi dùng getter cho serialization và setter/creator cho deserialization, nên xác nhận rằng annotation được nhận diện như mong muốn trong cả hai chiều. Một cách dễ bảo trì là đặt annotation ở một vị trí nhất quán trên property và viết kiểm tra cho serialization lẫn deserialization.

Với constructor bất biến, có thể kết hợp JsonCreator, JsonProperty và JsonView trên tham số:

~~~java
public class UserCommand {
    private final String displayName;
    private final String internalCode;

    @JsonCreator
    public UserCommand(
            @JsonProperty("displayName")
            @JsonView(Views.Public.class)
            String displayName,
            @JsonProperty("internalCode")
            @JsonView(Views.Internal.class)
            String internalCode) {
        this.displayName = displayName;
        this.internalCode = internalCode;
    }

    public String getDisplayName() {
        return displayName;
    }

    public String getInternalCode() {
        return internalCode;
    }
}
~~~

Khi sử dụng creator properties trong dự án, hãy kiểm tra phiên bản Jackson và metadata thực tế của constructor. Nếu annotation trên tham số không được nhận diện do cấu hình hoặc cách biên dịch, có thể đặt view trên field/property tương ứng theo một cấu hình nhất quán.

## 13. JsonView trong Spring MVC

Spring MVC hỗ trợ chọn view cho response thông qua JsonView trên handler method. Ví dụ:

~~~java
@RestController
@RequestMapping("/users")
public class UserController {

    @GetMapping("/{id}")
    @JsonView(Views.Public.class)
    public User getPublicUser(@PathVariable Long id) {
        return userService.findById(id);
    }

    @GetMapping("/{id}/internal")
    @JsonView(Views.Internal.class)
    public User getInternalUser(@PathVariable Long id) {
        return userService.findById(id);
    }
}
~~~

Spring sử dụng view được khai báo để hướng dẫn Jackson serialize response. Cấu hình và cách hỗ trợ cụ thể phụ thuộc phiên bản Spring Framework/Spring Boot và message converter đang sử dụng.

Lưu ý hai annotation cùng có tên JsonView nhưng thuộc hai package khác nhau: trên field/property của DTO dùng com.fasterxml.jackson.annotation.JsonView; trên handler method hoặc tham số request body của Spring MVC dùng org.springframework.web.bind.annotation.JsonView. Khi tích hợp, cần import đúng annotation theo vị trí sử dụng.

Với request body, Spring MVC cũng có thể kết hợp JsonView trên tham số RequestBody ở các phiên bản hỗ trợ:

~~~java
@PostMapping
public User create(
        @RequestBody
        @JsonView(Views.Public.class)
        UserCommand command) {
    return userService.create(command);
}
~~~

Nếu muốn điều khiển view tường minh ở tầng message conversion, Spring cung cấp MappingJacksonValue:

~~~java
MappingJacksonValue response = new MappingJacksonValue(user);
response.setSerializationView(Views.Public.class);
return response;
~~~

MappingJacksonValue hữu ích khi view được quyết định động trong controller hoặc tầng xử lý response. Không nên giả định mọi kiểu return value đều tự chọn view; hãy kiểm tra cách converter của ứng dụng xử lý response.

## 14. Dùng ObjectWriter và ObjectReader thay vì thay đổi mapper dùng chung

ObjectMapper thường được cấu hình một lần rồi tái sử dụng. Khi cần nhiều view, tạo writer/reader tương ứng:

~~~java
ObjectWriter publicWriter = mapper.writerWithView(Views.Public.class);
ObjectWriter internalWriter = mapper.writerWithView(Views.Internal.class);

ObjectReader publicReader = mapper
    .readerWithView(Views.Public.class)
    .forType(User.class);
~~~

Các đối tượng writer/reader là cấu hình bất biến cho thao tác. Có thể lưu chúng để tái sử dụng nếu kiểu và view cố định.

Không nên đổi cấu hình view hoặc các feature nền tảng trên một ObjectMapper đang được nhiều request dùng đồng thời. Tạo writer/reader riêng giúp mỗi thao tác có view rõ ràng mà không phải thay đổi trạng thái mapper dùng chung.

## 15. JsonView và JsonFilter khác nhau thế nào?

JsonView và JsonFilter đều có thể làm thay đổi tập thuộc tính được serialize, nhưng cách mô tả khác nhau:

| Tiêu chí | JsonView | JsonFilter |
|---|---|---|
| Cách khai báo | Gắn property vào các view marker | Gắn filter id lên kiểu/property |
| Cách chọn | Chọn một active view khi đọc/ghi | Đăng ký filter provider khi serialize |
| Quy tắc | Tĩnh, thể hiện trong annotation và quan hệ kế thừa | Có thể động theo request hoặc điều kiện |
| Phù hợp | Các tập field định nghĩa trước như public/internal/admin | Lọc field linh hoạt theo cấu hình hoặc người dùng |

Ví dụ JsonFilter:

~~~java
@JsonFilter("userFilter")
public class FilteredUser {
    public Long id;
    public String name;
    public String email;
}
~~~

~~~java
SimpleBeanPropertyFilter filter =
    SimpleBeanPropertyFilter.filterOutAllExcept("id", "name");

FilterProvider filters = new SimpleFilterProvider()
    .addFilter("userFilter", filter);

String json = mapper.writer(filters).writeValueAsString(user);
~~~

JsonView phù hợp khi các cách nhìn đã biết trước và ít thay đổi. JsonFilter phù hợp khi tập field cần chọn được xác định động. Hai cơ chế có thể cùng xuất hiện trong hệ thống, nhưng nên có quy ước rõ ràng để tránh khó hiểu khi chúng cùng tác động lên một kiểu.

## 16. JsonView không thay thế phân quyền hoặc bảo vệ dữ liệu

JsonView chỉ ảnh hưởng đến quá trình Jackson đọc/ghi theo active view. Nó không kiểm tra người gọi có quyền sử dụng view đó hay không.

Ví dụ:

~~~java
String json = mapper.writeValueAsString(user);
~~~

Nếu gọi serialize mặc định, các thuộc tính có thể được ghi mà không qua view. Nếu endpoint nội bộ vô tình chọn Admin view cho người dùng không có quyền, JsonView không tự ngăn request.

Vì vậy:

- Controller/service phải xác thực danh tính và kiểm tra quyền trước khi chọn view.
- Không chọn view nhạy cảm chỉ dựa vào một tham số do client tự gửi mà không kiểm tra quyền.
- Các đường trả dữ liệu khác như log, message queue, cache hoặc export cũng cần chính sách riêng.
- Với dữ liệu bí mật có yêu cầu bảo vệ nghiêm ngặt, cân nhắc DTO riêng hoặc mapping tường minh cho response công khai.
- Viết kiểm tra bảo đảm endpoint công khai luôn dùng đúng view hoặc đúng DTO.

View giúp định nghĩa cách biểu diễn dữ liệu; phân quyền quyết định ai được phép truy cập cách biểu diễn đó. Hai trách nhiệm này cần được thiết kế riêng.

## 17. Những giới hạn cần hiểu

JsonView hoạt động ở mức property của Jackson bean. Nó không tự biến mọi cấu trúc Java thành một hệ thống projection tổng quát.

Một số giới hạn thường gặp:

- Không tự lọc key động bên trong Map theo annotation của từng key.
- Không thay thế validation dữ liệu đầu vào.
- Không tự kiểm tra quyền của người gọi.
- Không bảo đảm mọi endpoint đều dùng view; caller phải chọn active view.
- Không thay đổi trạng thái object Java sau khi serialize.
- Không tự chuẩn hóa dữ liệu hoặc biến đổi giá trị thuộc tính.
- Không giải quyết việc một thuộc tính cần giá trị khác nhau theo người dùng; trường hợp đó cần logic nghiệp vụ hoặc DTO/mapping riêng.

Nếu mỗi view có cấu trúc rất khác nhau, nhiều trường tính toán hoặc quy tắc hiển thị phức tạp, DTO response riêng thường dễ hiểu hơn việc dồn quá nhiều điều kiện vào annotation.

## 18. Kiểm tra tác động của DEFAULT_VIEW_INCLUSION

Vì feature này có thể làm thay đổi kết quả đáng kể, nên cần kiểm tra cả trường được gắn view và trường không có annotation.

~~~java
public class Profile {
    @JsonView(Views.Public.class)
    private String displayName;

    private String legacyField;
}
~~~

Tạo hai mapper với chính sách khác nhau:

~~~java
ObjectMapper inclusiveMapper = new ObjectMapper();

ObjectMapper strictMapper = JsonMapper.builder()
    .disable(MapperFeature.DEFAULT_VIEW_INCLUSION)
    .build();
~~~

Ghi cùng object:

~~~java
String inclusiveJson = inclusiveMapper
    .writerWithView(Views.Public.class)
    .writeValueAsString(profile);

String strictJson = strictMapper
    .writerWithView(Views.Public.class)
    .writeValueAsString(profile);
~~~

Ở mapper inclusive, legacyField có thể được đưa vào vì không có view được chỉ định và mặc định inclusion đang bật. Ở mapper strict, legacyField bị loại khỏi thao tác có active view.

Khi cấu hình framework, hãy kiểm tra giá trị feature trên ObjectMapper thực tế. Một cấu hình auto-configuration có thể khác mapper được tạo bằng new ObjectMapper().

## 19. Kiểm tra serialization theo từng view

JUnit có thể xác nhận mỗi view chỉ xuất các trường dự kiến:

~~~java
class UserJsonViewTest {

    private final ObjectMapper mapper = JsonMapper.builder()
        .disable(MapperFeature.DEFAULT_VIEW_INCLUSION)
        .build();

    private final User user = new User(
        12L,
        "Mai Nguyen",
        "mai@example.com",
        "internal"
    );

    @Test
    void publicViewContainsOnlyPublicProperties() throws Exception {
        String json = mapper
            .writerWithView(Views.Public.class)
            .writeValueAsString(user);

        JsonNode node = mapper.readTree(json);

        assertTrue(node.has("id"));
        assertTrue(node.has("displayName"));
        assertFalse(node.has("email"));
        assertFalse(node.has("internalNote"));
    }

    @Test
    void internalViewIncludesPublicAndInternalProperties() throws Exception {
        String json = mapper
            .writerWithView(Views.Internal.class)
            .writeValueAsString(user);

        JsonNode node = mapper.readTree(json);

        assertTrue(node.has("id"));
        assertTrue(node.has("displayName"));
        assertTrue(node.has("email"));
        assertFalse(node.has("internalNote"));
    }

    @Test
    void adminViewIncludesAllDeclaredProperties() throws Exception {
        String json = mapper
            .writerWithView(Views.Admin.class)
            .writeValueAsString(user);

        JsonNode node = mapper.readTree(json);

        assertTrue(node.has("id"));
        assertTrue(node.has("displayName"));
        assertTrue(node.has("email"));
        assertTrue(node.has("internalNote"));
    }
}
~~~

Các kiểm tra dùng JsonNode để xác nhận sự hiện diện của field, không phụ thuộc thứ tự field trong JSON. Nếu hợp đồng yêu cầu cả giá trị, có thể kiểm tra thêm node.get("displayName").asText().

## 20. Kiểm tra deserialization theo view

View ở chiều đọc cần được kiểm tra riêng. Ví dụ:

~~~java
String json = """
    {
      "id": 12,
      "displayName": "Mai Nguyen",
      "email": "mai@example.com",
      "internalNote": "internal"
    }
    """;

User publicUser = mapper
    .readerWithView(Views.Public.class)
    .forType(User.class)
    .readValue(json);
~~~

Với strict view inclusion, publicUser được gán các thuộc tính thuộc Public; email và internalNote không được gán qua active view. Các trường không được phép nhận có thể giữ giá trị mặc định hoặc giá trị khởi tạo trong đối tượng.

Có thể kiểm tra:

~~~java
assertEquals(12L, publicUser.getId());
assertEquals("Mai Nguyen", publicUser.getDisplayName());
assertNull(publicUser.getEmail());
assertNull(publicUser.getInternalNote());
~~~

Kết quả cụ thể còn phụ thuộc constructor, giá trị mặc định, setter và cấu hình mapper. Nếu lớp khởi tạo email hoặc internalNote bằng giá trị khác null, kiểm tra phải phản ánh hành vi đó.

Đối với request body, cần kiểm tra thêm các trường bị bỏ qua có được xem là không được phép cập nhật hay không. Một API có thể cần từ chối trường ngoài view thay vì âm thầm bỏ qua; nếu vậy, hãy thiết kế validation hoặc deserializer riêng và kiểm thử rõ hành vi.

## 21. Lỗi thường gặp khi sử dụng JsonView

| Triệu chứng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| Field nội bộ vẫn xuất hiện trong public JSON | Serialize không chọn active view | Dùng writerWithView hoặc tích hợp controller đúng cách |
| Field không annotation vẫn xuất hiện | DEFAULT_VIEW_INCLUSION đang bật | Tắt feature nếu cần view nghiêm ngặt |
| View cấp cao thiếu field của view nền | Quan hệ kế thừa view khai báo sai chiều | Cho view rộng hơn extends view nền |
| Field lồng nhau không được lọc như mong muốn | Chỉ gắn view trên property cha hoặc metadata property con không nhất quán | Kiểm tra annotation trên cả object cha và lớp con |
| Request nhận trường không mong muốn | Không dùng readerWithView hoặc framework không áp dụng view như dự kiến | Chọn reader view rõ ràng và kiểm tra integration |
| Một số field bị mất khi dùng nhiều view | Active view không phải composite view mong muốn | Tạo interface composite kế thừa các view cần kết hợp |
| Dữ liệu nhạy cảm bị lộ ở endpoint khác | Endpoint dùng serialize mặc định hoặc chọn view quá rộng | Kiểm tra quyền và chọn response contract ở mọi luồng |
| Kết quả test phụ thuộc môi trường | Mapper do framework cấu hình khác mapper test | Test bằng mapper thực tế hoặc cấu hình feature tường minh |

## 22. Khi nào nên dùng JsonView và khi nào nên dùng DTO riêng?

JsonView hữu ích khi cùng một mô hình có nhiều cách nhìn đơn giản, các tập thuộc tính có quan hệ bao hàm và phần lớn dữ liệu vẫn dùng chung.

DTO riêng thường phù hợp hơn khi:

- Mỗi response có cấu trúc khác nhau đáng kể.
- Một số field được tính toán hoặc đổi tên theo ngữ cảnh.
- Các endpoint có quy tắc validation và cập nhật khác nhau.
- Cần kiểm soát chặt dữ liệu nhạy cảm qua các ranh giới hệ thống.
- Quan hệ giữa các tập field không thể mô tả gọn bằng kế thừa view.

| Tiêu chí | JsonView | DTO riêng |
|---|---|---|
| Tái sử dụng mô hình | Cao | Có thể lặp một phần cấu trúc |
| Số lớp | Ít hơn | Nhiều hơn |
| Tập field | Khai báo bằng annotation và view | Khai báo trực tiếp trong DTO |
| Logic chuyển đổi | Hạn chế | Linh hoạt |
| Kiểm soát response | Phụ thuộc caller chọn view | Rõ ở kiểu response của endpoint |
| Phù hợp với cấu trúc rất khác nhau | Kém thuận tiện | Thường phù hợp hơn |

Không nên cố dùng JsonView cho mọi trường hợp chỉ để giảm số DTO. Mục tiêu là làm hợp đồng JSON rõ ràng và dễ kiểm soát.

## 23. Ví dụ hoàn chỉnh với Public, Internal và Admin

Ví dụ sau kết hợp view marker, DTO, ObjectWriter và kiểm tra output:

~~~java
import com.fasterxml.jackson.annotation.JsonView;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.ObjectWriter;
import com.fasterxml.jackson.databind.json.JsonMapper;
import com.fasterxml.jackson.databind.MapperFeature;

public final class UserViewExample {

    private UserViewExample() {
    }

    public static final class Views {
        private Views() {
        }

        public interface Public {
        }

        public interface Internal extends Public {
        }

        public interface Admin extends Internal {
        }
    }

    public static class User {
        @JsonView(Views.Public.class)
        private Long id;

        @JsonView(Views.Public.class)
        private String displayName;

        @JsonView(Views.Internal.class)
        private String email;

        @JsonView(Views.Admin.class)
        private String internalNote;

        public User() {
        }

        public User(Long id, String displayName, String email,
                    String internalNote) {
            this.id = id;
            this.displayName = displayName;
            this.email = email;
            this.internalNote = internalNote;
        }

        public Long getId() {
            return id;
        }

        public String getDisplayName() {
            return displayName;
        }

        public String getEmail() {
            return email;
        }

        public String getInternalNote() {
            return internalNote;
        }

        public void setId(Long id) {
            this.id = id;
        }

        public void setDisplayName(String displayName) {
            this.displayName = displayName;
        }

        public void setEmail(String email) {
            this.email = email;
        }

        public void setInternalNote(String internalNote) {
            this.internalNote = internalNote;
        }
    }

    public static void main(String[] args) throws Exception {
        ObjectMapper mapper = JsonMapper.builder()
            .disable(MapperFeature.DEFAULT_VIEW_INCLUSION)
            .build();

        User user = new User(
            12L,
            "Mai Nguyen",
            "mai@example.com",
            "Tài khoản cần kiểm tra"
        );

        ObjectWriter publicWriter =
            mapper.writerWithView(Views.Public.class);
        ObjectWriter internalWriter =
            mapper.writerWithView(Views.Internal.class);
        ObjectWriter adminWriter =
            mapper.writerWithView(Views.Admin.class);

        System.out.println(publicWriter.writeValueAsString(user));
        System.out.println(internalWriter.writeValueAsString(user));
        System.out.println(adminWriter.writeValueAsString(user));
    }
}
~~~

Trong ví dụ:

1. View marker định nghĩa ba mức dữ liệu.
2. Quan hệ kế thừa làm Internal bao gồm Public và Admin bao gồm Internal.
3. JsonView gắn từng property vào mức phù hợp.
4. DEFAULT_VIEW_INCLUSION bị tắt để property không annotation không tự xuất hiện trong active view.
5. Mỗi ObjectWriter giữ một view riêng, không cần thay đổi mapper dùng chung.

## 24. Nguyên tắc thực hành

- Khai báo view marker rõ ràng, ưu tiên interface rỗng.
- Thiết kế kế thừa từ view ít thông tin đến view nhiều thông tin.
- Gắn JsonView nhất quán trên property.
- Chọn active view tường minh bằng ObjectWriter hoặc ObjectReader.
- Kiểm tra DEFAULT_VIEW_INCLUSION trên mapper thực tế.
- Kiểm thử riêng serialization và deserialization.
- Kiểm tra cả object lồng nhau, collection và Map.
- Dùng composite view khi cần hợp nhiều view độc lập.
- Không xem JsonView là cơ chế xác thực hoặc phân quyền.
- Dùng DTO riêng khi cấu trúc hoặc logic của các response khác nhau đáng kể.

JsonView giúp tách nhiều cách nhìn trên cùng một mô hình bằng cách gắn thuộc tính với các view marker và chọn view trong từng thao tác Jackson. Khi hiểu quan hệ kế thừa, chính sách DEFAULT_VIEW_INCLUSION và cách active view được truyền qua object lồng nhau, ứng dụng có thể tạo các JSON contract rõ ràng hơn mà vẫn giữ mô hình Java dùng chung. Việc kiểm soát ai được chọn view nào vẫn thuộc trách nhiệm của tầng ứng dụng.
