# Tránh lộ dữ liệu nhạy cảm và vòng lặp khi tuần tự hóa đối tượng thành JSON trong Spring Boot

## 1. Tại sao JSON response là một ranh giới bảo mật?

Một REST controller Spring Boot có thể trả về một Java object và để `HttpMessageConverter` biến object thành JSON. Cách viết này rất tiện, nhưng object trong tầng dữ liệu/nghiệp vụ thường chứa **nhiều thông tin hơn mức API được phép công khai**. Ngoài dữ liệu nhạy cảm, những quan hệ hai chiều như `Account -> Order -> Account` còn tạo **đồ thị đối tượng có chu trình**; trình tuần tự hóa có thể đi theo vòng tham chiếu và thất bại.

Hai câu hỏi phải được trả lời riêng:

1. **Dữ liệu nào được phép xuất hiện?** Một user có được xem `email`, `passwordHash`, `recoveryToken`, vai trò quản trị, thông tin thanh toán hoặc dữ liệu của user khác hay không?
2. **Đồ thị được biểu diễn thế nào?** API có cần một danh sách order tóm tắt, hay phải serialize toàn bộ quan hệ JPA hai chiều? Phải tránh đệ quy không có điểm dừng, truy vấn lazy ngoài ý muốn, payload khổng lồ và `StackOverflowError`.

**Giải pháp mặc định an toàn:** định nghĩa **response DTO theo allowlist** — chỉ khai báo trường được phép xuất ra, ánh xạ từ domain/entity sang DTO và chỉ trả DTO từ controller. Jackson annotation là công cụ hỗ trợ; không phải cơ chế phân quyền thay cho authorization ở service/security layer.

Bài tập trung vào **Spring Boot 3.5.16 + Jackson 2 + Spring MVC + Java 17+** để có ví dụ Maven/MockMvc nhất quán. Với Spring Boot 4.x, Jackson 3 là lựa chọn mặc định; phần cuối nêu những khác biệt cần rà soát khi nâng phiên bản.

## 2. Luồng tuần tự hóa và điểm dễ gây lỗi

~~~text
HTTP GET /api/accounts/42
         |
         v
Spring MVC chọn Controller
         |
         v
Service lấy Account domain/JPA entity
         |
         +-- id, displayName, email, passwordHash, recoveryToken
         |
         +-- orders: List<PurchaseOrder>
                           |
                           +-- id, sku, owner: Account
                                             |
                                             +-- orders -> ...
         |
         v
Controller chọn đối tượng trả về
         |
         +-- Trả domain/entity trực tiếp -> dễ lộ field + vòng tham chiếu
         |
         +-- Map sang AccountView DTO -> chỉ id, displayName,
                                         orders[id,sku]
         |
         v
MappingJackson2HttpMessageConverter (Boot 3.5, Spring MVC)
         |
         v
JSON theo contract API, không lộ secrets và không có vòng đệ quy
~~~

Khi controller dùng `@RestController` hoặc `@ResponseBody`, Spring MVC thường chọn `HttpMessageConverter` dựa trên return type và content negotiation. Với JSON, Spring Boot 3.5 mặc định tích hợp Jackson 2: các public properties/getters, record components và annotation Jackson ảnh hưởng cấu trúc JSON tạo ra.

**Lưu ý:** Jackson serialize *biểu diễn đối tượng được trả về*, không tự hiểu field nào là “bí mật” theo nghiệp vụ. Một `getPasswordHash()` công khai, một getter mới do Lombok sinh ra, hoặc một trường liên kết entity vừa được thêm có thể khiến response thay đổi nếu controller trả domain object nguyên bản.

Với WebFlux, các reactive JSON encoders/codecs là đường thực thi khác, nhưng rủi ro lộ property và reference cycle khi ánh xạ object bằng Jackson tương tự. Không trộn tên `HttpMessageConverter` của MVC với toàn bộ codec WebFlux trong một mô tả implementation.

## 3. Hai loại rủi ro cần phân biệt

### 3.1. Lộ dữ liệu ngoài ý muốn: excessive data exposure

Ví dụ một entity/domain:

~~~java
public class Account {
    private long id;
    private String displayName;
    private String email;
    private String passwordHash;
    private String recoveryToken;
    // getters, setters, các quan hệ ...
}
~~~

Đoạn này **chỉ để minh họa mô hình**, không phải file chạy độc lập. Nếu trả một instance có getters tương ứng từ controller, JSON có thể chứa cả `passwordHash` hoặc `recoveryToken`, dù frontend không hiển thị chúng. Kẻ gọi API có thể xem trực tiếp response trong network tools.

Vấn đề vẫn tồn tại ngay cả khi:

- HTML/frontend không render trường nhạy cảm.
- Một route yêu cầu user đã đăng nhập nhưng chưa kiểm tra **quyền xem từng trường** hoặc đối tượng được yêu cầu.
- Backend định bỏ field ở JavaScript phía client sau khi đã nhận JSON.
- Giá trị là hash thay vì password gốc: hash có thể hữu ích cho tấn công offline và không được gửi cho client.
- Field hiện tại rỗng/`null`: sau này khi có giá trị thật, một thay đổi ngầm có thể làm lộ thông tin.

Theo OWASP API3:2023 (Broken Object Property Level Authorization), API cần xác định **thuộc tính nào requester có quyền đọc/ghi**; tránh trả nguyên object chỉ vì serialization có sẵn.

### 3.2. Chu trình tham chiếu hoặc object graph quá lớn

Trong quan hệ hai chiều:

~~~text
Account(id=42)
  orders[0] -> PurchaseOrder(id=501)
                     owner -> Account(id=42)
                                 orders[0] -> ...
~~~

Nếu Jackson được yêu cầu duyệt cả hai chiều, nó có thể liên tục mở rộng cùng object. Tùy annotation/mapper/converter, kết quả có thể là `JsonMappingException` liên quan infinite recursion hoặc `StackOverflowError`, thường dẫn tới HTTP 500 hoặc response không được tạo thành công.

Một đồ thị **không có chu trình** vẫn có thể bị serialize quá sâu nếu nó chứa hàng nghìn entity, nhiều collection và các quan hệ ORM lazy. Các vấn đề khác gồm:

- Dữ liệu của entity liên quan vượt phạm vi API.
- Truy vấn **N+1** khi Jackson gọi getter quan hệ lazy.
- `LazyInitializationException` hoặc lỗi proxy sau khi session đóng.
- Response rất lớn, tăng heap/CPU/băng thông và bộc lộ metadata không cần thiết.
- Serialization vô tình kích hoạt tính toán nặng hoặc side effect trong getter.

**Chống vòng lặp không đồng nghĩa chống lộ secrets.** Có thể dùng `@JsonIdentityInfo` để serializer tạo tham chiếu ID thay vì đệ quy, nhưng nếu object gốc chứa password hash thì JSON vẫn có thể lộ password hash đó.

## 4. Giải pháp ưu tiên: Response DTO theo allowlist

Thay vì trả `Account`, tạo một schema công khai:

~~~java
public record AccountView(
        long id,
        String displayName,
        List<OrderView> orders) {

    public record OrderView(long id, String sku) {
    }
}
~~~

Đây là **trích đoạn DTO**, chưa bao gồm imports và code ánh xạ. Nó chỉ có các trường cần thiết cho chức năng, không có `email`, `passwordHash`, `recoveryToken` hay tham chiếu `Order.owner`. Khi domain thay đổi, public API **không tự mọc thêm field**.

Ưu điểm:

1. **Allowlist rõ ràng:** API owner có thể review contract ngay tại DTO.
2. **Tách trách nhiệm:** domain/entity chứa nghiệp vụ và quan hệ; DTO là biểu diễn dành cho client.
3. **Không có graph cycle:** `OrderView` không chứa `AccountView` hay một `Account` domain object.
4. **Ổn định hơn:** thay đổi quan hệ JPA, tên cột, getter hoặc password storage không tự thay JSON.
5. **Dễ kiểm thử:** so sánh toàn bộ tập field JSON cho từng role/endpoint.
6. **Có nơi áp dụng chính sách:** trước khi map DTO, service có thể kiểm tra requester được đọc account nào và field nào; sau đó mới tạo DTO phù hợp.

Không nên làm kiểu này:

~~~java
// Chỉ là ví dụ thiết kế sai: trả object có thể chứa dữ liệu nội bộ.
@GetMapping("/api/accounts/{id}")
public Account getAccount(@PathVariable long id) {
    return accountService.load(id);
}
~~~

Ngay cả khi một số field đã có `@JsonIgnore`, endpoint vẫn phụ thuộc vào annotation và sự thay đổi tương lai của domain. **DTO ở ranh giới API là rào chắn cấu trúc** mạnh hơn một tập annotation phân tán.

Trong hệ thống đa quyền, có thể dùng các DTO rõ ràng như `PublicAccountView`, `OwnAccountView` và `AdminAccountView`, chỉ tạo loại tương ứng sau khi authorization. Đừng để client gửi `?includeSecrets=true` hoặc tự chọn property nhạy cảm theo ý muốn.

## 5. Các annotation Jackson thường dùng và giới hạn của chúng

Những annotation dưới đây thuộc Jackson 2 package `com.fasterxml.jackson.annotation.*`. Trong Jackson 3 được Spring Boot 4.x mặc định sử dụng, **module Jackson annotations vẫn duy trì package này** để tương thích; các thư viện Jackson databind/core khác chuyển sang `tools.jackson.*`.

| Kỹ thuật | Mục đích | Không giải quyết được |
|---|---|---|
| `@JsonIgnore` | Không đưa logical property vào JSON và thông thường bỏ qua khi deserialize | Không quyết định user có quyền đọc record hay không |
| `@JsonProperty(access = WRITE_ONLY)` | Cho phép nhận giá trị khi deserialize nhưng không xuất property khi serialize | Không tự hash password hoặc bảo mật dữ liệu trong log |
| `@JsonProperty(access = READ_ONLY)` | Cho phép serialize nhưng không nhận giá trị từ JSON input | Không thay thế kiểm tra quyền cập nhật ở service |
| `@JsonIgnoreProperties({"x","y"})` | Bỏ qua những tên property nhất định ở class | Danh sách denylist dễ thiếu khi domain thêm field mới |
| `@JsonManagedReference`/`@JsonBackReference` | Đánh dấu quan hệ forward/back để không serialize back-link | Không lọc dữ liệu nhạy cảm ở chiều forward |
| `@JsonIdentityInfo` | Biểu diễn identity/reference theo ID, giảm lặp instance và vòng đệ quy | Không giảm quyền truy cập vào object, có thể lộ ID |
| `@JsonView` | Điều khiển nhóm field cho những JSON view được chỉ định | Không tự thực hiện authorization theo user/role |
| `@JsonInclude(NON_NULL)` | Bỏ giá trị null khỏi JSON | Không giấu secret có giá trị khác null |
| `@JsonFilter` | Lọc property theo cấu hình serializer/filter provider | Dễ tạo sơ hở nếu filter không được áp dụng nhất quán |

### 5.1. @JsonIgnore cho property không bao giờ xuất JSON

~~~java
import com.fasterxml.jackson.annotation.JsonIgnore;

public class Account {
    private String passwordHash;

    @JsonIgnore
    public String getPasswordHash() {
        return passwordHash;
    }
}
~~~

Đây là code **minh họa annotation**, tách biệt khỏi project chạy ở mục 8. Với Jackson default property introspection, `getPasswordHash` bị bỏ khỏi serialization. Theo semantics mặc định, `@JsonIgnore` áp dụng cho logical property, nên nó còn ảnh hưởng deserialization; nếu mục tiêu là **nhận password khi đăng ký nhưng không trả lại**, hãy dùng DTO đầu vào riêng hoặc `@JsonProperty(access = WRITE_ONLY)`.

Đừng gắn `@JsonIgnore` tùy tiện lên getter rồi kết luận mọi đường rò đều chặn: object có thể được log bằng `toString()`, serialize bởi thư viện khác, hoặc truyền qua hệ thống khác không tuân theo Jackson annotation.

### 5.2. @JsonProperty(access = WRITE_ONLY) cho input-only field

~~~java
import com.fasterxml.jackson.annotation.JsonProperty;

public record SignupRequest(
        String displayName,
        @JsonProperty(access = JsonProperty.Access.WRITE_ONLY)
        String password) {
}
~~~

Trong cách nhìn của Jackson:

- `WRITE_ONLY`: Jackson có thể **ghi giá trị vào object khi deserialize JSON đầu vào**, nhưng không **đọc object để ghi ra JSON** property đó.
- `READ_ONLY`: hướng ngược lại — property có thể được serialize, nhưng không nhận từ JSON đầu vào.

Tên read/write ở đây là **từ góc nhìn Java property**, dễ gây nhầm nếu suy luận từ góc nhìn HTTP.

Trong thiết kế production, `SignupRequest` là input DTO, nên **không trả nó từ endpoint** dù đã có `WRITE_ONLY`. Password phải được xử lý bằng password encoder phù hợp và không bao giờ log body đăng ký. Một field `passwordHash` tồn tại ở database/domain không phải field trả về.

Đừng phối hợp `@JsonIgnore` và `@JsonProperty(access=WRITE_ONLY)` trên cùng logical property mà không hiểu Jackson annotation merging: `@JsonIgnore` có thể thắng và làm mất luôn đường nhận input.

### 5.3. @JsonIgnoreProperties là denylist, không phải allowlist

~~~java
@JsonIgnoreProperties({"passwordHash", "recoveryToken"})
class InternalAccount {
    public String displayName;
    public String email;
    public String passwordHash;
    public String recoveryToken;
}
~~~

Đoạn này là **minh họa**. Hai property bị bỏ, nhưng `email` vẫn xuất. Nếu tháng sau có thêm `privateKey`, `apiToken` hoặc `isAdmin`, denylist không tự biết phải giấu chúng. Vì vậy DTO chỉ khai báo trường được phép là cách kiểm soát phạm vi xuất dữ liệu bền vững hơn.

`@JsonIgnoreProperties(ignoreUnknown = true)` là thiết lập cho **input unknown fields**; nó không có nghĩa mọi field nhạy cảm sẽ bị bỏ khi serialize. Đây là hai chức năng khác nhau, không được đánh đồng.

## 6. Những cách xử lý object cycle

### 6.1. Cắt chu trình bằng DTO — cách khuyến nghị

Nếu domain có `Account.orders -> Order.owner -> Account`, API chỉ cần:

~~~json
{
  "id": 42,
  "displayName": "Mai",
  "orders": [
    {"id": 501, "sku": "BOOK-1"}
  ]
}
~~~

JSON này không có `owner` trong từng order, cũng không có các trường nhạy cảm. DTO chủ động **định nghĩa điểm dừng** cho graph traversal. Khi endpoint khác thật sự cần thông tin owner, có thể thêm owner summary gồm trường được phép, ví dụ `ownerId` hoặc `ownerDisplayName`, thay vì nhúng nguyên `Account`.

### 6.2. @JsonManagedReference / @JsonBackReference

Với quan hệ parent-child đơn giản có thể dùng:

~~~java
class Account {
    @JsonManagedReference("account-orders")
    private List<PurchaseOrder> orders;
}

class PurchaseOrder {
    @JsonBackReference("account-orders")
    private Account owner;
}
~~~

Đây là **trích đoạn**, không phải file Java biên dịch độc lập; cần imports/getters/constructors tương ứng. `@JsonManagedReference` đánh dấu forward link để serialize bình thường, `@JsonBackReference` đánh dấu back-link không được serialize. Trong deserialization, Jackson có thể nối ngược reference cho property tương thích.

**Hạn chế quan trọng:**

- Back-reference nên đặt trên property kiểu **bean**, không đặt trên một collection/map/array; ví dụ `Order.owner` phù hợp, còn đặt `@JsonBackReference` lên `Account.orders` là sai hướng.
- Quan hệ nhiều chiều có thể cần đặt **tên cặp reference** khác nhau; dùng một cặp annotation cho một vòng không giải quyết mọi graph phức tạp.
- Thông tin nhạy cảm trên `Account` vẫn có thể được serialize theo forward direction.
- Với JPA entity, serializer vẫn có thể kích hoạt lazy loading.
- Bản JSON sẽ mất back-link ở chiều serialize, chưa chắc đúng contract của mọi endpoint.

Dùng DTO nếu mục tiêu là contract REST ổn định; dùng cặp annotation khi cần serialize một mô hình hai chiều ở phạm vi chặt chẽ và đã kiểm thử.

### 6.3. @JsonIdentityInfo và reference ID

~~~java
@JsonIdentityInfo(
        generator = ObjectIdGenerators.PropertyGenerator.class,
        property = "id")
class Account {
    public long id;
    public List<PurchaseOrder> orders;
}
~~~

Đây là **minh họa** cơ chế identity, cần Jackson imports và class `PurchaseOrder`. Khi các object liên quan có identity hợp lệ và được cấu hình phù hợp, serializer có thể biểu diễn một lần object đầy đủ, những lần gặp lại dùng identifier thay vì mở rộng vô hạn.

Nhưng `@JsonIdentityInfo` không tự giới hạn schema, không ẩn password hash và có thể làm lộ ID nội bộ. Nếu client cần owner ID, **một DTO `OrderView(ownerId)` minh bạch hơn** so với phụ thuộc semantics reference ID của Jackson.

### 6.4. Không dùng cấu hình serializer toàn cục để “cứu” domain không an toàn

Thay `ObjectMapper`, bật default typing/polymorphic deserialization bừa bãi, bỏ visibility hoặc tự động bỏ toàn bộ property theo package có thể gây hậu quả ngoài dự tính với các endpoint khác. Nếu cần custom serializer:

- Giới hạn trong một **kiểu DTO cụ thể**, thay vì thay mapping mọi object.
- Tránh side effect và network/database IO trong serializer.
- Kiểm thử các field xuất ra, cấu trúc nested, error behavior và performance.
- Không bật insecure default typing cho dữ liệu JSON không đáng tin. Polymorphic input chỉ nên dùng theo allowlist subtype và cấu hình bảo mật thích hợp.

## 7. JPA/Hibernate: tại sao entity trực tiếp càng rủi ro?

Spring Data JPA entity thường có hai chiều:

~~~text
@OneToMany: User -> List<Order>
@ManyToOne: Order -> User
~~~

Trả entity từ controller có thể dẫn đến:

1. **Recursion** nếu getter mở cả quan hệ con và back-reference.
2. **LazyInitializationException** nếu serializer truy cập quan hệ lazy ngoài persistence context.
3. **N+1 queries** nếu serializer đang duyệt collection làm Hibernate nạp từng quan hệ.
4. **Data exposure** nếu serializer theo quan hệ sang thực thể có field không được công khai.
5. **Proxy / Hibernate type metadata** gây JSON không mong đợi hoặc không serialize được.
6. **Bất ổn định contract** khi entity thêm trường/quan hệ cho yêu cầu database mà response tự thay đổi.

Một hướng giải quyết:

~~~text
Controller
   -> Service kiểm tra quyền truy cập đối tượng
      -> Repository query lấy dữ liệu cần thiết (projection/DTO/entity với fetch plan)
         -> Service ánh xạ sang response DTO trong transaction thích hợp
            -> Controller trả DTO
               -> Jackson chỉ serialize đồ thị DTO hữu hạn
~~~

Nếu có lazy relation, service nên quyết định **khi nào và bao nhiêu quan hệ cần fetch**, ví dụ dùng projection, `JOIN FETCH`, `@EntityGraph` hoặc truy vấn chuyên dụng. Không để serializer trở thành nơi quyết định fetch plan.

Trong dự án JPA, có thể cân nhắc:

~~~properties
spring.jpa.open-in-view=false
~~~

Nó giúp tránh việc persistence context còn mở xuyên giai đoạn rendering response trong nhiều kiến trúc MVC, nhưng **không tự sửa cycle, không tự tạo DTO và không tự loại N+1**. Phải map DTO/resolve quan hệ cần thiết trước khi transaction/session kết thúc.

Các annotation `@JsonIgnore` trên entity có thể hữu ích như defense-in-depth, nhưng mapping JPA (`@OneToMany`, `@ManyToOne`, `FetchType.LAZY`) không phải authorization policy hoặc JSON contract.

**Lombok `@Data` và vòng lặp khác:** Lombok-generated `toString()`, `equals()`, `hashCode()` trên entity có quan hệ hai chiều cũng có thể tự đệ quy, ngay cả khi JSON được xử lý bằng DTO. Nên tránh `@Data` trên JPA entity có graph phức tạp, chủ động chọn field cho `equals/hashCode` và dùng `@ToString.Exclude` khi cần. `@ToString.Exclude` chỉ tác động `toString()`, **không** có tác dụng ngăn Jackson serialize property.

## 8. Ví dụ hoàn chỉnh Spring Boot 3.5.16, Java 17+: domain có chu trình, API trả DTO an toàn

Ví dụ này cố ý tạo domain hai chiều `Account -> PurchaseOrder -> Account` và gán **giá trị giả** vào field riêng tư để test rằng response không lộ chúng. Đây không phải hệ thống lưu password thật hoặc cơ chế authentication/authorization production; nó chỉ kiểm tra **JSON serialization boundary**.

### 8.1. Cấu trúc file

~~~text
safe-json-demo/
  pom.xml
  src/
    main/
      java/com/example/safejson/
        SafeJsonApplication.java
        Account.java
        PurchaseOrder.java
        AccountService.java
        AccountView.java
        AccountController.java
    test/
      java/com/example/safejson/
        AccountControllerTest.java
~~~

### 8.2. pom.xml

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.16</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>safe-json-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Dòng 3.5.16 đã được phát hành; ví dụ dùng nó để cố định package/Jackson 2, không khẳng định đây là dòng mới nhất hoặc còn vòng đời OSS support. Với dự án mới, nên chọn dòng Spring Boot đang được hỗ trợ và áp dụng bản vá bảo mật thích hợp.

### 8.3. Main class

File `src/main/java/com/example/safejson/SafeJsonApplication.java`:

~~~java
package com.example.safejson;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class SafeJsonApplication {
    public static void main(String[] args) {
        SpringApplication.run(SafeJsonApplication.class, args);
    }
}
~~~

### 8.4. Domain Account có fields không dành cho client

File `src/main/java/com/example/safejson/Account.java`:

~~~java
package com.example.safejson;

import java.util.ArrayList;
import java.util.List;

public final class Account {
    private final long id;
    private final String displayName;
    private final String email;
    private final String passwordHash;
    private final String recoveryToken;
    private final List<PurchaseOrder> orders = new ArrayList<>();

    public Account(long id, String displayName, String email,
                   String passwordHash, String recoveryToken) {
        this.id = id;
        this.displayName = displayName;
        this.email = email;
        this.passwordHash = passwordHash;
        this.recoveryToken = recoveryToken;
    }

    public long getId() { return id; }
    public String getDisplayName() { return displayName; }
    public String getEmail() { return email; }
    public String getPasswordHash() { return passwordHash; }
    public String getRecoveryToken() { return recoveryToken; }

    public List<PurchaseOrder> getOrders() {
        return List.copyOf(orders);
    }

    public void addOrder(PurchaseOrder order) {
        orders.add(order);
    }
}
~~~

Các getter của `email`, `passwordHash`, `recoveryToken` tồn tại cho **logic domain minh họa**. Chúng **không đồng nghĩa được phép trả trong API**. Mẫu này cố ý **không** dùng `@JsonIgnore` để minh họa lý do DTO là hàng rào bảo mật quan trọng, thay vì chỉ dựa vào annotation trên domain.

### 8.5. Domain PurchaseOrder trỏ ngược về Account

File `src/main/java/com/example/safejson/PurchaseOrder.java`:

~~~java
package com.example.safejson;

public final class PurchaseOrder {
    private final long id;
    private final String sku;
    private final Account owner;

    public PurchaseOrder(long id, String sku, Account owner) {
        this.id = id;
        this.sku = sku;
        this.owner = owner;
    }

    public long getId() { return id; }
    public String getSku() { return sku; }
    public Account getOwner() { return owner; }
}
~~~

Nếu serialize trực tiếp một `Account`, Jackson có thể đi qua `getOrders()`, rồi `getOwner()`, quay về `Account` ban đầu. `List.copyOf` chỉ cung cấp một danh sách snapshot không sửa được, **không** cắt chu trình giữa các object.

### 8.6. Service tạo dữ liệu demo và xử lý không tìm thấy

File `src/main/java/com/example/safejson/AccountService.java`:

~~~java
package com.example.safejson;

import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import org.springframework.web.server.ResponseStatusException;

@Service
public class AccountService {
    public Account load(long id) {
        if (id != 42L) {
            throw new ResponseStatusException(
                    HttpStatus.NOT_FOUND, "Account not found");
        }

        Account account = new Account(
                42L, "Mai", "private@example.test",
                "DEMO_HASH_ONLY_NOT_REAL",
                "DEMO_TOKEN_ONLY_NOT_REAL");

        account.addOrder(
                new PurchaseOrder(501L, "BOOK-1", account));
        return account;
    }
}
~~~

Các string `DEMO_...` không phải hash/token thực tế mà chỉ là sentinel test data. `AccountService` không có database và **chưa triển khai kiểm tra quyền**; với production, service phải xác định requester được xem account ID 42 hay không trước khi trả kết quả.

### 8.7. Response DTO và mapper chỉ chọn fields public

File `src/main/java/com/example/safejson/AccountView.java`:

~~~java
package com.example.safejson;

import java.util.List;

public record AccountView(
        long id,
        String displayName,
        List<OrderView> orders) {

    public record OrderView(long id, String sku) {
    }

    public static AccountView from(Account account) {
        List<OrderView> items = account.getOrders().stream()
                .map(order -> new OrderView(
                        order.getId(), order.getSku()))
                .toList();

        return new AccountView(
                account.getId(), account.getDisplayName(), items);
    }
}
~~~

**Điểm quyết định:** ánh xạ từ `PurchaseOrder` chỉ lấy `id` và `sku`, **không truyền `order.getOwner()`** sang response. DTO không chứa reference đến domain, không có getter cho secrets, và không có back-link nên serialization hữu hạn.

### 8.8. Controller trả DTO, không trả Account

File `src/main/java/com/example/safejson/AccountController.java`:

~~~java
package com.example.safejson;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class AccountController {
    private final AccountService accountService;

    public AccountController(AccountService accountService) {
        this.accountService = accountService;
    }

    @GetMapping("/api/accounts/{id}")
    public AccountView getAccount(@PathVariable("id") long id) {
        Account account = accountService.load(id);
        return AccountView.from(account);
    }
}
~~~

Controller công khai **response contract** bằng return type `AccountView`. Việc một entity có thêm field mới hoặc quan hệ mới không tự làm response nở ra. Khi thêm field hợp lệ, cần thay DTO/mapper/test một cách có chủ đích.

### 8.9. Chạy và đọc response

Yêu cầu JDK 17+ và Maven, tại thư mục chứa `pom.xml`:

~~~bash
mvn spring-boot:run
~~~

Nếu dự án có Maven Wrapper, có thể dùng `./mvnw spring-boot:run` hoặc `mvnw.cmd spring-boot:run` trên Windows. Với server chạy ở port mặc định 8080:

~~~bash
curl -sS http://localhost:8080/api/accounts/42
~~~

JSON logic kỳ vọng:

~~~json
{
  "id": 42,
  "displayName": "Mai",
  "orders": [
    {
      "id": 501,
      "sku": "BOOK-1"
    }
  ]
}
~~~

Jackson có thể serialize JSON gọn trên một dòng; khoảng trắng và thứ tự field không phải phần quan trọng của test. Kết quả quan trọng là JSON **chỉ có ba key cấp cao** `id`, `displayName`, `orders`, và **hai key trong phần tử order** `id` và `sku`.

Không có `email`, `passwordHash`, `recoveryToken`, `owner`; không có dữ liệu `DEMO_HASH_ONLY_NOT_REAL` và `DEMO_TOKEN_ONLY_NOT_REAL` trong response. Vì DTO không chứa back-reference, không có recursion mặc dù domain gốc thực sự có cycle.

Thử ID khác:

~~~bash
curl -i http://localhost:8080/api/accounts/99
~~~

Dự kiến HTTP 404 do service ném `ResponseStatusException`. Response error body tùy cấu hình Spring Boot, không phải một JSON cố định do ví dụ định nghĩa.

## 9. MockMvc kiểm tra tính an toàn của JSON contract

File `src/test/java/com/example/safejson/AccountControllerTest.java`:

~~~java
package com.example.safejson;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest
@AutoConfigureMockMvc
class AccountControllerTest {
    @Autowired
    MockMvc mvc;

    @Autowired
    ObjectMapper mapper;

    @Test
    void responseContainsOnlyApprovedFields() throws Exception {
        String body = mvc.perform(get("/api/accounts/42"))
                .andExpect(status().isOk())
                .andReturn()
                .getResponse()
                .getContentAsString();

        JsonNode root = mapper.readTree(body);
        assertEquals(3, root.size());
        assertEquals(42L, root.get("id").asLong());
        assertEquals("Mai", root.get("displayName").asText());

        JsonNode orders = root.get("orders");
        assertEquals(1, orders.size());
        JsonNode order = orders.get(0);
        assertEquals(2, order.size());
        assertEquals(501L, order.get("id").asLong());
        assertEquals("BOOK-1", order.get("sku").asText());

        assertFalse(root.has("email"));
        assertFalse(root.has("passwordHash"));
        assertFalse(root.has("recoveryToken"));
        assertFalse(order.has("owner"));
        assertFalse(body.contains("DEMO_HASH_ONLY_NOT_REAL"));
        assertFalse(body.contains("DEMO_TOKEN_ONLY_NOT_REAL"));
        assertFalse(body.contains("private@example.test"));
    }

    @Test
    void unknownAccountDoesNotReturnAnObject() throws Exception {
        mvc.perform(get("/api/accounts/99"))
                .andExpect(status().isNotFound());
    }
}
~~~

Chạy bằng Maven:

~~~bash
mvn test
~~~

Các assert có ba tác dụng:

- **Positive assertions:** client nhận đúng dữ liệu cần thiết.
- **Schema allowlist:** kiểm tra chính xác số key ở mỗi mức, khiến một field mới lọt ra response dễ bị phát hiện.
- **Negative assertions:** không có field name, sentinel bí mật hoặc tham chiếu `owner` trong JSON.

Test sẽ kết thúc nếu JSON được tạo hợp lệ, vì thế cũng là kiểm chứng thực tế rằng **domain circular graph không làm serializer đi vào vòng lặp** qua DTO. Test không chứng minh authentication/authorization đúng; production cần test user A không xem được đối tượng hoặc field chỉ dành cho user B/admin.

**Không nên chỉ viết `assertFalse(json.contains("password"))`:** kết quả có thể không chứa tên field nhưng chứa chính giá trị secret ở một property khác. Hãy kiểm tra **cả shape JSON lẫn dữ liệu nhạy cảm giả lập** và rà soát contract theo quyền người gọi.

## 10. Xử lý JSON views, dynamic fields và các quyền khác nhau

### 10.1. Khi role khác nhau cần response khác nhau

Một API có thể có các biến thể:

| Người gọi | DTO ví dụ | Trường được phép |
|---|---|---|
| Guest | `PublicAccountView` | ID public, display name |
| Chủ tài khoản | `OwnAccountView` | ID, display name, email được phép, danh sách order tối thiểu |
| Support agent | `SupportAccountView` | Chỉ các trường được phê duyệt cho support |
| Admin | `AdminAccountView` | Các trường phục vụ vận hành sau authorization, vẫn không chứa password hash hoặc token bí mật |

Ánh xạ này phải đứng sau **object-level authorization** và **property-level authorization**. Một DTO chứa field dành cho admin không nên được trả cho user thường rồi dựa vào frontend ẩn đi.

Có thể dùng `@JsonView` cho các API khác nhau, nhưng nó dễ trở nên rối khi nhiều view kế thừa, default view inclusion hoặc `@ResponseBody` không gắn view. Những trường thực sự nhạy cảm nên được kiểm soát bằng DTO/policy độc lập, không xem `@JsonView` như hệ thống phân quyền.

### 10.2. Map động và JsonNode cũng cần allowlist

Với:

~~~java
Map<String, Object> response = new HashMap<>();
response.putAll(domainProperties);
return response;
~~~

một danh sách property được build động có thể làm lộ field ngoài ý muốn. Đổi kiểu từ entity sang `Map<String,Object>` **không tự an toàn hơn** nếu chỉ copy toàn bộ thuộc tính.

Khi cần response động, nên xác định allowlist key và kiểm tra từng giá trị, kể cả nested objects; tránh đặt entity/secret object làm value của map, vì Jackson vẫn serialize nội dung nested đó.

### 10.3. Hạn chế log/trace leak dù JSON đã an toàn

DTO an toàn chỉ kiểm soát **response body ở API boundary**. Thông tin nhạy cảm vẫn có thể rò ở:

- `logger.info("account={}", account)` nếu `toString()` chứa email/hash/token.
- Access log, tracing, APM hoặc request/response logging filter không redact header/body.
- Exception message chứa raw tokens hoặc request payload.
- JSON từ event queue, cache hoặc export job sử dụng domain object thay vì DTO riêng.
- API lỗi debug vô tình trả stack trace, internal properties hoặc `cause`.
- Spring Actuator endpoints nếu phơi cấu hình/dữ liệu mà không có kiểm soát truy cập.

Áp dụng **redaction**, giới hạn field thu thập, secret management, phân quyền quan sát log và test các đường dữ liệu ra ngoài. Không bật `logging.level.org.springframework.web=TRACE` hoặc log toàn bộ HTTP body trong production nếu chưa đánh giá rò PII/credential.

## 11. Các sai lầm cần tránh

| Sai lầm | Hệ quả | Hướng sửa |
|---|---|---|
| Trả JPA `@Entity` trực tiếp | Có thể lộ field mới, recursion, lazy-loading | DTO response theo allowlist |
| Chỉ ẩn bằng CSS/frontend | Network response vẫn chứa secret | Bỏ field ở backend trước serialization |
| Tưởng `@JsonIgnore` thay authorization | User vẫn có thể truy cập object hoặc field khác không được phép | Kiểm tra quyền ở service/security + DTO đúng role |
| Đặt `@JsonBackReference` lên collection | Không đúng hướng parent/back reference | Đặt back reference trên child -> parent bean |
| Dùng `@JsonIdentityInfo` như cách giấu dữ liệu | Hạn chế recursion nhưng vẫn có thể lộ field/ID | DTO và filter field theo policy |
| Dựa vào `@JsonInclude(NON_NULL)` | Secret khác null vẫn được serialize | Không đặt secret trong response DTO |
| Tưởng `@Transient` của JPA luôn ẩn JSON | JPA persistence mapping khác Jackson property introspection | Dùng DTO/annotation JSON đúng chỗ |
| Dùng `@ToString.Exclude` để chặn JSON | Chỉ tác động `toString()`, không phải serialization | DTO/Jackson annotation |
| Serialize lazy entity trong controller | N+1, `LazyInitializationException`, payload lớn | Fetch/DTO mapping trong service |
| Dùng mixin/global serializer không có test | Thay đổi endpoint khác ngoài ý muốn | Scope hẹp và contract tests |
| Giữ `ObjectMapper` custom không xét Boot auto-config | Mất module, Java Time support, codec, security config | Dùng auto-configured mapper hoặc builder customizer |
| Tắt Jackson `FAIL_ON_SELF_REFERENCES` với hy vọng khỏi lỗi | Không phải giải pháp để biểu diễn graph an toàn | Cắt graph bằng DTO hoặc identity/ref có kiểm thử |
| Tạo response DTO từ entity chưa authorization | DTO không tự ngăn trả dữ liệu của account khác | Kiểm tra object/field access trước mapping |
| Chỉ test field có mặt | Không phát hiện thêm secret field | Test cả key allowlist và negative assertions |
| Dùng `@JsonProperty(WRITE_ONLY)` mà vẫn log password | JSON response có thể an toàn nhưng log vẫn rò | Không log credential, redaction và DTO input riêng |

## 12. Phân biệt Jackson 2 trên Spring Boot 3.5 và Jackson 3 trên Boot 4.x

Spring Boot 3.5 sử dụng **Jackson 2** với `com.fasterxml.jackson.databind.ObjectMapper`. Ví dụ project ở trên tương ứng với môi trường này và dùng `spring-boot-starter-web`.

Spring Boot 4.x chuyển sang **Jackson 3** làm JSON mapper mặc định, dùng `tools.jackson.databind.json.JsonMapper` và tổ chức starter/module mới. Đặc biệt:

- `com.fasterxml.jackson.annotation.JsonIgnore`, `JsonProperty`, `JsonManagedReference`, `JsonBackReference` vẫn ở package `com.fasterxml.jackson.annotation` thông qua module annotations tương thích.
- Những import databind/core và cách tạo/customize mapper cần rà soát: nhiều class chuyển từ `com.fasterxml.jackson.*` sang `tools.jackson.*`.
- Khi code dùng Boot-specific `Jackson2ObjectMapperBuilderCustomizer`, Boot 4 có `JsonMapperBuilderCustomizer` và các điểm mở rộng mới.
- Jackson 2 có cơ chế hỗ trợ chuyển tiếp trong Boot 4, nhưng đã deprecated; không nên coi đó là kế hoạch dài hạn.
- Starter Spring MVC của Boot 4.x dùng `spring-boot-starter-webmvc` làm tên rõ ràng hơn, và test imports/module cần kiểm tra theo phiên bản.
- Cấu hình Jackson 3 mặc định có thể khác Jackson 2; test exact schema, null handling, polymorphism, Java Time và nested reference sau upgrade.

**Bản chất bảo mật không đổi:** dù Jackson 2 hay 3, chỉ những trường được phép mới nên xuất hiện trong response; DTO/authorization là lựa chọn thiết kế, annotation chỉ là công cụ biểu diễn. Nâng cấp mapper không tự sửa endpoint trả entity lộ secrets.

## 13. Quy trình kiểm thử và rà soát pull request

Áp dụng checklist sau cho mọi endpoint thêm hoặc sửa JSON response:

1. **Liệt kê dữ liệu nhạy cảm:** password, passwordHash, recovery token, API key, refresh token, personal data, finance, secret config, nội bộ vận hành.
2. **Xác định quyền:** ai xem được đối tượng nào và từng property nào? Kiểm tra object-level và property-level authorization trước khi map.
3. **Xác định JSON schema contract:** return DTO cụ thể; không expose entity hoặc object graph không giới hạn.
4. **Cắt quan hệ hai chiều:** đối tượng nested dùng DTO summary, ID được cho phép hoặc URI; giới hạn collection/depth/page.
5. **Kiểm tra ORM fetch plan:** tránh N+1, lazy serialization, side effects, transaction mở quá lâu.
6. **Review annotation:** `@JsonIgnore`, `WRITE_ONLY`, ref/identity/view phải được hiểu đúng semantics, không phải security policy.
7. **Positive & negative JSON tests:** assert key đúng, key thừa không tồn tại và sentinel bí mật không xuất hiện.
8. **Kiểm tra mọi role:** user thường, chủ tài khoản, support, admin, user không đăng nhập, requester không có quyền.
9. **Kiểm tra lỗi và quan sát:** exception handler không lộ stacktrace, log/trace không ghi secret, health/management endpoint được bảo vệ.
10. **Test payload sâu và lớn:** pagination, max response size, không serialize graph không giới hạn hoặc lặp vô hạn.
11. **Test migration:** đặc biệt Jackson 2 → 3, và thay đổi getter/ORM relation.
12. **Lưu evidence:** contract API, ví dụ body và bộ test trong CI; bổ sung test khi thêm field/domain relation.

**Kết luận:** tránh lộ dữ liệu và tránh vòng lặp là hai yêu cầu độc lập nhưng cùng xuất hiện tại **ranh giới serialization**. Hãy **kiểm tra quyền → chọn response DTO chỉ chứa field được phép → map object graph hữu hạn → serialize → test positive/negative**. `@JsonIgnore`, `@JsonBackReference` và `@JsonIdentityInfo` hỗ trợ các tình huống cụ thể, nhưng không thay thế allowlist DTO và authorization.

## Tài liệu tham khảo

- Spring Boot 3.5 — JSON mapping: https://docs.spring.io/spring-boot/3.5/reference/features/json.html
- Spring Boot 4.x — JSON, Jackson 3 là mặc định: https://docs.spring.io/spring-boot/reference/features/json.html
- Spring Boot 4.0 Migration Guide — Jackson 3 và compatibility: https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-4.0-Migration-Guide
- Spring Framework — MVC Response Body / Message Converters: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/responsebody.html
- Jackson 2 Javadoc — JsonIgnore: https://javadoc.io/doc/com.fasterxml.jackson.core/jackson-annotations/latest/com/fasterxml/jackson/annotation/JsonIgnore.html
- Jackson 2 Javadoc — JsonProperty.Access: https://javadoc.io/doc/com.fasterxml.jackson.core/jackson-annotations/latest/com/fasterxml/jackson/annotation/JsonProperty.Access.html
- Jackson 2 Javadoc — JsonManagedReference: https://javadoc.io/doc/com.fasterxml.jackson.core/jackson-annotations/latest/com/fasterxml/jackson/annotation/JsonManagedReference.html
- Jackson 2 Javadoc — JsonBackReference: https://javadoc.io/doc/com.fasterxml.jackson.core/jackson-annotations/latest/com/fasterxml/jackson/annotation/JsonBackReference.html
- Jackson 2 Javadoc — JsonIdentityInfo: https://javadoc.io/doc/com.fasterxml.jackson.core/jackson-annotations/latest/com/fasterxml/jackson/annotation/JsonIdentityInfo.html
- OWASP API Security Top 10 — API3:2023 Broken Object Property Level Authorization: https://owasp.org/API-Security/editions/2023/en/0xa3-broken-object-property-level-authorization/
- Spring Boot 3.5.16 Maven artifact: https://central.sonatype.com/artifact/org.springframework.boot/spring-boot-starter-parent/3.5.16
