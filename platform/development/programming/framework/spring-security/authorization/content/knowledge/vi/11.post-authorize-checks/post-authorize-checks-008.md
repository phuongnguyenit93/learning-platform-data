# Proxy đối tượng trả về, kiểu lồng nhau và giới hạn tương thích

## 1. Bối cảnh: kết quả của service chưa chắc an toàn cho mọi người đọc

Trong Spring Security, việc cho phép gọi một service không đồng nghĩa cho phép xem **mọi trường của đối tượng** mà service trả về. Một hồ sơ có thể chứa tên hiển thị công khai, email cá nhân, số điện thoại, địa chỉ và thông tin tài chính. Một response có thể chứa nhiều cấp lồng nhau như `Order → Customer → Contact`. Quyền xem Order chưa mặc nhiên bao hàm quyền xem Contact.

Một object có annotation ở getter:

```java
public class UserProfile {
    public String getDisplayName() { ... }

    @PreAuthorize("hasAuthority('profile:email:read')")
    public String getEmail() { ... }
}
```

chưa chắc được bảo vệ khi nó chỉ là POJO do service tạo bằng `new` rồi đưa ra ngoài. Các annotation method security thông dụng được đánh giá trên **lời gọi đi qua interceptor/proxy**. Nếu consumer nhận reference **thô**, `getEmail()` có thể chạy mà không đi qua chốt.

Spring Security 6.3+ cung cấp `@AuthorizeReturnObject`: đánh dấu method trả đối tượng cần **bọc authorization advice**. Khi caller sau đó truy cập getter/method có annotation bảo mật trên object đã được proxy, Spring Security có thể kiểm tra permission ở chính lời gọi ấy.

Bài học này tập trung vào năm câu hỏi thực tế:

1. Sự khác nhau giữa `@PostAuthorize`, `@PostFilter` và `@AuthorizeReturnObject` là gì?
2. Proxy được gắn vào object nào, thời điểm nào, và getter được kiểm quyền lúc nào?
3. Object lồng nhau, `List`, `Optional`, `Map`, array, stream được xử lý ra sao?
4. Vì sao kiểu `final`/`record`, `String`, Jackson, Hibernate, AOT và type erasure gây giới hạn?
5. Làm sao kiểm thử để không bỏ sót lối lộ dữ liệu qua raw reference, serialization và tenant khác?

**Nguyên tắc nền:** proxy trả về là công cụ **bổ sung**. Không thay thế xác thực, role/permission, quyền sở hữu, query theo tenant, safe DTO hoặc kiểm tra nhất quán khi ghi dữ liệu.

### Hình dung vòng đời

```text
Controller / caller
      |
      v
Spring-managed service proxy
      |
      v
@PreAuthorize kiểm tra được gọi service?
      |
      v
Service tạo ProfileView thô
      |
      v
@AuthorizeReturnObject
      |
      v
ProfileView đã bọc proxy
      |
      +-- getDisplayName() --> giá trị ít nhạy cảm
      |
      +-- getContact()     --> ContactView được bọc tiếp?
                                   |
                                   v
                           getEmail()
                           @PreAuthorize
                             /     \
                           DENY    ALLOW
                            |        |
                          exception  email
```

Dấu hỏi ở object con là lời nhắc phải **thiết kế và test đường proxy của từng cấp**. Framework không hứa tự bảo vệ mọi field nếu code truy cập trực tiếp hoặc giữ reference gốc.

## 2. Ba cơ chế kiểm tra kết quả không đồng nghĩa

| Công cụ | Thời điểm kiểm tra | Đối tượng | Tác dụng | Điểm cần nhớ |
| --- | --- | --- | --- | --- |
| `@PostAuthorize` | Sau khi thân method thực thi, trước khi trả kết quả được phép | `returnObject` | Cho phép/từ chối toàn bộ lượt trả | Đã chạy logic method; side effect có thể đã xảy ra |
| `@PostFilter` | Sau khi method tạo kết quả dạng container hỗ trợ | Từng `filterObject` | Loại bỏ phần tử không đủ quyền | Có thể đã tải nhiều dữ liệu không cần thiết vào memory |
| `@AuthorizeReturnObject` | Khi return value được tạo; bọc object bằng proxy | Object được trả về, nested object/container được hỗ trợ | Kiểm tra các lời gọi getter/method sau này | Phụ thuộc proxyable type, context và đúng đường gọi |

### 2.1. @PostAuthorize — đánh giá cả kết quả sau method

```java
@PostAuthorize("returnObject.owner == authentication.name")
public AccountView readAccount(long accountId) {
    return repository.read(accountId);
}
```

Spring Security cho phép dùng `returnObject` trong expression để đọc dữ liệu của object vừa được trả. Nếu owner khác tên principal, lời gọi method có thể bị từ chối. Đây là một cách kiểm tra bổ sung khi thông tin ownership chỉ có sau khi load.

**Đừng dùng riêng @PostAuthorize cho write:** với việc chuyển tiền, gửi email, xóa record, gọi webhook, side effect có thể đã diễn ra trước quyết định. Nếu có transaction, rollback behavior còn phụ thuộc thứ tự advice và loại side effect. Kiểm tra trước method và điều kiện ghi ở DB vẫn cần có.

### 2.2. @PostFilter — loại phần tử

```java
@PostFilter("filterObject.owner == authentication.name")
public List<AccountView> listAccounts() {
    return repository.findCandidates();
}
```

Kết quả chỉ còn những phần tử thỏa expression sau khi filter. Tuy nhiên, `findCandidates()` có thể đã tải account ngoài tenant/owner vào memory; với danh sách lớn, N+1 SQL và chi phí lọc có thể cao. Truy vấn scoped tại database theo verified tenant và owner/share phù hợp vẫn là hướng mặc định.

`@PostFilter` **không tự tạo proxy getter** cho những account còn lại. Quyết định “phần tử nào được có trong list” khác với “được xem thuộc tính nào của mỗi phần tử”.

### 2.3. @AuthorizeReturnObject — bọc object để tiếp tục kiểm tra

```java
public class ProfileView {
    private final String name;
    private final String email;

    public ProfileView(String name, String email) {
        this.name = name;
        this.email = email;
    }

    public String getName() {
        return name;
    }

    @PreAuthorize("hasAuthority('profile:email:read')")
    public String getEmail() {
        return email;
    }
}

@Service
public class ProfileService {
    @AuthorizeReturnObject
    public ProfileView getProfile(long id) {
        return repository.findVisibleProfile(id);
    }
}
```

Ví dụ này là **mã tích hợp Spring**, không phải file Java độc lập. Cần import annotations, repository, service, context và principal. Khi service được gọi qua Spring proxy và return-object advice hoạt động, object trả về có thể là proxy; `getEmail()` được đánh giá khi caller **thực sự gọi getter** trên proxy đó.

Một test chỉ gọi `getProfile(...)` thành công **chưa đủ**: nó không chứng minh user thiếu email permission sẽ bị chặn lúc lấy email.

### 2.4. Đặt cả chốt trước và chốt return

```java
@PreAuthorize("hasAuthority('profile:read')")
@AuthorizeReturnObject
public ProfileView getProfile(long id) {
    return repository.findVisibleForCurrentTenant(id);
}
```

Rule `profile:read` bảo vệ chức năng lấy hồ sơ. Rule trên getter email bảo vệ thuộc tính nhạy cảm. Nhưng `findVisibleForCurrentTenant` phải thật sự giới hạn tenant/owner/share; một object ngoài tenant vẫn có thể lộ tên/metadata qua getter khác dù email đã bị deny.

## 3. Bật infrastructure và xác định ranh giới proxy

### 3.1. @EnableMethodSecurity

Với Spring Security Servlet 6.5:

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;

@Configuration
@EnableMethodSecurity
public class MethodSecurityConfig {
}
```

Mặc định, method security đăng ký các advisors cho `@PreAuthorize`, `@PostAuthorize`, `@PreFilter` và `@PostFilter`. Những annotation Secured/JSR-250 chỉ hoạt động khi có cờ tương ứng; không nên mặc định rằng proxy factory có tất cả các loại advice nếu ứng dụng đã tắt hoặc custom cấu hình.

Method trả return object cũng cần được gọi qua Spring-managed bean/proxy hoặc cơ chế interception thích hợp. Nếu tạo service bằng `new`, hoặc gọi `this.getProfile()` trong cùng object ở chế độ AOP proxy, advice có thể bị bỏ qua.

### 3.2. Sự khác nhau giữa bean proxy và object proxy

Trong cùng một request, có thể có nhiều thứ đều được gọi là proxy:

- **Security proxy của service:** intercept lời gọi vào Spring-managed service.
- **Return-object authorization proxy:** bọc đối tượng được trả để intercept getter/method của nó.
- **Hibernate/JPA proxy:** lazy-load entity/association từ DB.
- **JDK interface proxy:** implement interface bằng delegation.
- **Class-based proxy:** thường tạo subclass trong các ranh giới mà JVM cho phép.

Chúng phục vụ **mục đích khác nhau**, không tự hoán đổi. Một DTO không phải Spring bean vẫn có thể được bảo vệ bằng return-object proxy; điều đó không khiến DTO tự có transaction hoặc dependency injection.

### 3.3. @AuthorizeReturnObject từ phiên bản nào?

JavaDoc của `@AuthorizeReturnObject` và `AuthorizeReturnObjectMethodInterceptor` ghi **Since: 6.3**. Tài liệu Spring Security 6.5 trình bày khả năng proxy container/nested và AOT; API factory/visitor đã phát triển trong các bản 6.x. Spring Security 7.x vẫn hỗ trợ cơ chế này, nhưng khi triển khai phải tham chiếu **đúng phiên bản đã khóa trong dự án**.

Không copy API `AuthorizationAdvisorProxyFactory`/`TargetVisitor` của 6.5/7.x vào 6.2 rồi cho rằng sẽ compile.

### 3.4. Test đối tượng đã proxy, không test object thô

Giả sử code:

```java
ProfileView raw = new ProfileView("Alice", "secret@example.test");
ProfileView secured = service.getProfile(42L);
```

Nếu test gọi `raw.getEmail()`, nó chỉ chứng minh raw POJO trả email. Nếu test gọi `secured.getEmail()` với principal thiếu quyền, nó mới kiểm tra return-object interceptor.

Cũng cần kiểm việc code khác **không giữ raw reference** để đưa sang JSON serializer, cache, exporter hoặc logger ngoài chốt.

## 4. Kiểu lồng nhau: Profile → Contact → Email

Một hồ sơ chứa một object Contact riêng có thể yêu cầu quyền khác cho `getEmail()`. Ta cần xác định **mỗi cạnh của cây object** có đang đi qua proxy hay không.

### 4.1. Mã mô tả cấu trúc hai cấp

```java
public class ContactView {
    private final String label;
    private final String email;

    public ContactView(String label, String email) {
        this.label = label;
        this.email = email;
    }

    public String getLabel() {
        return label;
    }

    @PreAuthorize("hasAuthority('profile:email:read')")
    public String getEmail() {
        return email;
    }
}
```

Lớp cha:

```java
public class ProfileView {
    private final String displayName;
    private final ContactView contact;

    public ProfileView(
            String displayName, ContactView contact) {
        this.displayName = displayName;
        this.contact = contact;
    }

    public String getDisplayName() {
        return displayName;
    }

    @AuthorizeReturnObject
    public ContactView getContact() {
        return contact;
    }
}
```

Service:

```java
@Service
public class ProfileService {
    @PreAuthorize("hasAuthority('profile:read')")
    @AuthorizeReturnObject
    public ProfileView findVisibleById(long id) {
        return repository.findVisibleForVerifiedActor(id);
    }
}
```

Đây là **những fragment Spring Security**, không phải dự án tự chạy; cần imports, Spring context, repository và các kiểu domain. Các class cần tương thích với proxy do version hiện tại sử dụng.

Luồng mong muốn:

1. Spring kiểm `profile:read` trước khi service chạy.
2. Service trả `ProfileView` được `@AuthorizeReturnObject` bọc.
3. Caller gọi `getDisplayName()`, nhận tên theo policy public/tenant của use case.
4. Caller gọi `getContact()`. Annotation trên getter này yêu cầu proxy tiếp cho `ContactView` được trả.
5. Caller gọi `getEmail()` trên ContactView đã proxy; `@PreAuthorize` kiểm `profile:email:read`.
6. User thiếu quyền email bị deny **ngay tại getter**, dù đã nhận ProfileView thành công.

### 4.2. Không đánh dấu nested getter thì sao?

Nếu `ProfileView.getContact()` chỉ trả raw ContactView và **không có cơ chế proxy khác**, không được tự suy ra method security trên `ContactView.getEmail()` chắc chắn hoạt động. Proxy không phải bộ lọc ma thuật tự động gắn vào mọi field hoặc bất kỳ đối tượng nào nằm sâu trong graph.

Vẽ từng cạnh:

```text
Service.findById() -> ProfileView         [@AuthorizeReturnObject]
ProfileView.getContact() -> ContactView   [@AuthorizeReturnObject]
ContactView.getEmail() -> String          [@PreAuthorize]
```

Nếu thêm `ProfileView.getOrders() -> List<OrderView>` và `OrderView.getPayment() -> PaymentView`, hãy quyết định ở những method trả object nào cần tạo proxy. Test cả nested getter và collection element.

### 4.3. Vì sao annotation trên getter tốt hơn truy cập field thô?

Method security kiểm tra lời gọi method đã được advice. Nếu thư viện đọc field trực tiếp bằng reflection, hoặc code giữ object gốc và truy cập field, nó có thể không đi qua getter proxy.

Do đó:

- Không dùng public fields cho dữ liệu nhạy cảm nếu dựa vào getter authorization.
- Không serialize raw entity chứa secret rồi kỳ vọng proxy getter xử lý.
- Không gửi raw object vào log/cache không kiểm soát.
- Hạn chế reference raw được giữ lại sau lúc tạo proxy.
- Đặt query scope và DTO projection ở nơi dữ liệu được lấy từ DB.

### 4.4. Owner, tenant và attribute permission

`hasAuthority('profile:email:read')` chỉ là quyền chức năng. Một user có permission này ở tenant A không nên tự đọc email user thuộc tenant B. Để bảo vệ đúng object, cần policy bean hoặc query scoped:

```text
CAN_READ_EMAIL =
  authenticated
  AND sameTenant
  AND has(profile:email:read)
  AND (isOwner OR permittedAuditor OR explicitlyShared)
```

Nếu một getter không có tham số ID nhưng có target object, có thể thiết kế authorization dựa trên metadata đáng tin của object và actor; phải xem expression target access và cơ chế evaluation của version cụ thể. Trong nhiều API, kiểm object ownership tại service/query trước khi trả DTO dễ kiểm thử hơn việc diễn đạt toàn bộ ownership trong SpEL getter.

## 5. Optional, List, Map, array, Stream và Iterator

Tài liệu Spring Security 6.5 mô tả `AuthorizationProxyFactory` hỗ trợ container chuẩn bằng cách proxy **các element**, với map thì proxy **value**.

| Return type | Đơn vị được bọc theo hỗ trợ tiêu chuẩn | Cần test |
| --- | --- | --- |
| `ProfileView` | Object trực tiếp | Getter có annotation |
| `Optional<ProfileView>` | Object bên trong Optional khi có | Empty và nonempty |
| `List<ProfileView>` | Từng phần tử | Iterator/get trả secured reference |
| `Set<ProfileView>` | Từng phần tử | Equality, hashCode và collection behavior |
| `ProfileView[]` | Từng phần tử | Array component compatibility |
| `Map<String, ProfileView>` | **Giá trị map** | Key có thể vẫn tiết lộ metadata |
| `Stream<ProfileView>` | Các phần tử khi stream xử lý | Deferred execution/context/lifetime |
| `Iterator<ProfileView>` | Các phần tử được duyệt | Context khi iteration |
| Container tự viết | Không có bảo đảm mặc định | Custom TargetVisitor/adapter nếu cần |

### 5.1. List chứa đúng object được phép chưa?

Một service:

```java
@AuthorizeReturnObject
public List<ProfileView> listProfiles() {
    return repository.findAllProfiles();
}
```

không an toàn nếu `findAllProfiles()` lấy toàn bộ hồ sơ mọi tenant. Dù getter email bị chặn, list length, tên hiển thị hoặc ID vẫn có thể rò rỉ dữ liệu. **Return-object proxy bảo vệ method của element, không thay chính sách membership/visibility của chính danh sách.**

Nên:

```java
@PreAuthorize("hasAuthority('profile:list')")
@AuthorizeReturnObject
public List<ProfileView> listProfiles() {
    return repository.findVisibleForVerifiedActor();
}
```

Query phải hạn chế tenant/owner/share; proxy getter sau đó chỉ là tầng bổ sung.

### 5.2. Optional

Với `Optional<ProfileView>`, khi có element, element có thể được proxy; với `Optional.empty()` không có object để bọc. Không suy diễn empty đồng nghĩa permission hay not-found; đây là business/API contract cần thống nhất.

Nên test rằng:

- Empty không gây lỗi proxy bất ngờ.
- Nonempty trả element có getter được chặn đúng.
- Chưa xác thực và sai tenant không làm lộ sự tồn tại của profile qua lỗi khác biệt ngoài ý muốn.

### 5.3. Map

Với `Map<String, ProfileView>`, factory có thể proxy value. Nhưng key có thể là email, username, customer ID, department; **proxy value không tự che key**. Dữ liệu bí mật ở key hoặc thứ tự/size collection có thể lộ ngay khi caller đọc Map.

Không dùng key nhạy cảm hoặc trả map vượt tenant rồi hy vọng getter proxy bảo vệ đủ. Thiết kế shape và access scope từ đầu.

### 5.4. Stream và Iterator

Với stream/iterator, việc truy cập element có thể diễn ra **sau** khi service trả hoặc ở một thread khác. Những rủi ro:

- `SecurityContextHolder` ở thread gọi getter không còn đúng caller.
- ORM session/transaction đóng trước khi lazy association được chạm tới.
- Parallel stream không tự mang SecurityContext sang worker thread.
- Stream gắn cursor cần được đóng đúng cách.
- AOT generic erasure có thể làm loại element khó được quét trước.

Với API công khai, scoped query + DTO snapshot thường dễ quản lý vòng đời hơn stream dài chứa secured entity proxies.

### 5.5. Proxy container khác @PostFilter

Đặt cạnh nhau:

```text
@AuthorizeReturnObject List<User>:
  Giữ các element; từng element có thể bị proxy
  Getter nhạy cảm được kiểm khi gọi.

@PostFilter List<User>:
  Loại element không đủ quyền theo filterObject
  Không hứa bảo vệ getter của element còn lại.
```

Cả hai không thay thế truy vấn DB có tenant/owner scope. Đối với hệ thống dữ liệu lớn, cần xét chi phí load/iteration và nguy cơ metadata leak trước khi chọn giải pháp.

## 6. Class-level proxy và các kiểu value

### 6.1. Vì sao class-level annotation dễ tạo lỗi?

`@AuthorizeReturnObject` có thể đặt ở class-level, tương đương gắn vào các method trong class. Ví dụ:

```java
@AuthorizeReturnObject
@Service
public class MixedReturnService {
    public ProfileView findProfile(long id) { ... }
    public String getStatusText() { ... }
    public int countProfiles() { ... }
    public List<String> listTags() { ... }
}
```

Một số return type như `String`, `Integer` và primitive không phải kiểu domain phù hợp để tạo class-based authorization proxy. Tài liệu Spring Security cảnh báo việc Spring cố proxy cả những value types ấy khi đánh dấu class-level.

**Ưu tiên đặt @AuthorizeReturnObject trên method cụ thể** thay vì gắn rộng toàn class nếu service trả nhiều loại. Nếu bắt buộc class-level, test mọi return type.

### 6.2. Bỏ qua value types bằng TargetVisitor

Theo tài liệu Spring Security 6.5, một bean cấu hình visitor:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.authorization.method.AuthorizationAdvisorProxyFactory.TargetVisitor;

@Configuration
public class ReturnObjectProxyConfiguration {

    @Bean
    static TargetVisitor skipValueTypes() {
        return TargetVisitor.defaultsSkipValueTypes();
    }
}
```

Mục đích là cấu hình xử lý loại trừ những kiểu value cơ bản khỏi việc cố proxy. Nếu cấu hình custom TargetVisitor, cần xem JavaDoc đúng version; visitor sai có thể bỏ qua **cả object cần bảo vệ**.

Chú ý phân biệt **skip value types** với **bỏ kiểm tra permission**. Một chuỗi `String` chỉ nên xuất hiện ở public response nếu service/getter đã áp chính sách phù hợp trước khi trả nó; skip proxy không phải `permitAll`.

### 6.3. Final, record, sealed và interface

Trong Java:

- `record` mặc định là final; không thể tạo subclass class-based proxy thông thường.
- `final class` và `final method` hạn chế interception bằng subclass.
- `sealed class` kiểm soát các permitted subclasses, nên không tự cho phép proxy subclass bất kỳ.
- Một interface projection có thể phù hợp với JDK dynamic proxy nhưng phải phù hợp return type/serialization.
- Kotlin class/method có thể final theo mặc định nếu không có cấu hình open/plugin.
- ORM entity có thể bị proxy thêm lần nữa, gây tương tác với lazy loading và equality.

Không khẳng định rằng một flag sẽ làm mọi object final trở nên proxyable. Khi việc proxy phức tạp, có thể an toàn hơn khi **quyết định quyền trước, map ra record/DTO chỉ chứa trường được phép rồi trả trực tiếp**.

### 6.4. equals, hashCode, getClass, toString

Proxy có thể thay đổi class quan sát được qua `getClass()` và reference identity. `equals/hashCode` phụ thuộc implementation/proxy behavior, có thể gây bất ngờ khi dùng làm key trong HashMap/element trong HashSet hoặc ORM identity map.

Nên so theo domain ID rõ ràng, tránh đưa secured proxy vào persistence graph và test `toString()`/logging. Một record hoặc entity `toString()` có thể in ra email dù getter authorization được bật ở nơi khác.

## 7. Tạo proxy theo chương trình

Spring Security còn có `AuthorizationProxyFactory` để bọc object không xuất phát trực tiếp từ method đã đánh dấu.

Fragment theo tài liệu 6.5:

```java
@Autowired
AuthorizationProxyFactory proxyFactory;

public void demo() {
    ProfileView raw = new ProfileView(...);
    ProfileView secured = proxyFactory.proxy(raw);
}
```

Dùng với collection:

```java
List<ProfileView> securedList =
    proxyFactory.proxy(List.of(rawA, rawB));
```

Đây là code mô tả cách dùng API, cần imports, bean và object concrete phù hợp. Factory lấy các `AuthorizationAdvisor` được cấu hình trong ứng dụng; nếu tự tạo `AuthorizationAdvisorProxyFactory.withDefaults()`, phải xác minh liệu nó có đủ custom advisors, role hierarchy và denied handlers của project hay không.

**Đừng coi proxy factory là bước thay thế authentication.** Caller phải có SecurityContext đúng lúc getter được đánh giá. Một POJO được proxy không tự nhận Spring transaction/JPA session hoặc context propagation.

## 8. Java 17 standalone: mô phỏng proxy object và object lồng nhau

Đoạn Java sau **biên dịch và chạy bằng JDK 17**, không cần thư viện Spring. Nó minh họa cơ chế bằng `java.lang.reflect.Proxy`:

- Một Profile đã proxy kiểm tra tenant trước khi cho xem tên/contact.
- Khi gọi `contact()`, wrapper trả một Contact **được proxy tiếp**.
- Getter `email()` cần `profile:email:read` và caller là owner hoặc auditor cùng tenant.
- List/Optional chỉ dùng secured references.
- Raw reference còn lưu có thể **bỏ qua** proxy; đây là lý do không được đưa raw entity ra nơi không tin cậy.

Đây là **mô hình kiến thức**, không mô phỏng code nội bộ Spring hay proxy class-based/AOT/Jackson.

Lưu file `ReturnedObjectProxyDemo.java`:

```java
import java.lang.reflect.Proxy;
import java.util.List;
import java.util.Optional;
import java.util.Set;

public class ReturnedObjectProxyDemo {

    interface Profile {
        String displayName();
        Contact contact();
    }

    interface Contact {
        String label();
        String email();
    }

    record RawContact(
        String label, String email
    ) implements Contact {}

    record RawProfile(
        String displayName, Contact contact,
        String ownerId, String tenantId
    ) implements Profile {}

    record Actor(
        String id, String tenantId,
        Set<String> grants, boolean active
    ) {}

    static void requireTenant(Actor actor, String tenant) {
        if (actor == null || !actor.active()
                || actor.tenantId() == null
                || !actor.tenantId().equals(tenant)) {
            throw new SecurityException("Tenant denied");
        }
    }

    static Profile secureProfile(
            RawProfile raw, Actor actor) {

        return (Profile) Proxy.newProxyInstance(
            Profile.class.getClassLoader(),
            new Class<?>[] {Profile.class},
            (proxy, method, args) -> {
                requireTenant(actor, raw.tenantId());

                return switch (method.getName()) {
                    case "displayName" -> raw.displayName();
                    case "contact" -> secureContact(
                        raw.contact(), actor,
                        raw.ownerId(), raw.tenantId()
                    );
                    default -> throw new UnsupportedOperationException(
                        method.getName()
                    );
                };
            }
        );
    }

    static Contact secureContact(
            Contact raw, Actor actor,
            String ownerId, String tenantId) {

        return (Contact) Proxy.newProxyInstance(
            Contact.class.getClassLoader(),
            new Class<?>[] {Contact.class},
            (proxy, method, args) -> {
                requireTenant(actor, tenantId);

                return switch (method.getName()) {
                    case "label" -> raw.label();
                    case "email" -> {
                        boolean allowedPermission =
                            actor.grants() != null
                            && actor.grants().contains(
                                "profile:email:read"
                            );
                        boolean owner =
                            actor.id() != null
                            && actor.id().equals(ownerId);
                        boolean auditor =
                            actor.grants() != null
                            && actor.grants().contains(
                                "ROLE_TENANT_AUDITOR"
                            );

                        if (!allowedPermission
                                || !(owner || auditor)) {
                            throw new SecurityException(
                                "Email denied"
                            );
                        }
                        yield raw.email();
                    }
                    default -> throw new UnsupportedOperationException(
                        method.getName()
                    );
                };
            }
        );
    }

    static boolean denied(Runnable read) {
        try {
            read.run();
            return false;
        } catch (SecurityException e) {
            return true;
        }
    }

    static void show(String label, Object value) {
        System.out.println(label + ": " + value);
    }

    public static void main(String[] args) {
        RawProfile aliceRaw = new RawProfile(
            "Alice",
            new RawContact("work", "alice@example.test"),
            "alice", "T1"
        );
        RawProfile bobRaw = new RawProfile(
            "Bob",
            new RawContact("private", "bob@example.test"),
            "bob", "T1"
        );

        Actor alice = new Actor(
            "alice", "T1",
            Set.of("profile:email:read"), true
        );
        Actor bob = new Actor(
            "bob", "T1", Set.of(), true
        );
        Actor auditor = new Actor(
            "audit", "T1",
            Set.of("ROLE_TENANT_AUDITOR",
                   "profile:email:read"), true
        );
        Actor foreignAuditor = new Actor(
            "audit", "T2",
            Set.of("ROLE_TENANT_AUDITOR",
                   "profile:email:read"), true
        );

        Profile aliceView = secureProfile(aliceRaw, alice);
        Profile bobView = secureProfile(aliceRaw, bob);
        Profile auditorView = secureProfile(aliceRaw, auditor);
        Profile foreignView =
            secureProfile(aliceRaw, foreignAuditor);

        show("alice display", aliceView.displayName());
        show("alice email", aliceView.contact().email());
        show("bob display", bobView.displayName());
        show("bob email denied", denied(
            () -> bobView.contact().email()
        ));
        show("auditor email", auditorView.contact().email());
        show("foreign display denied", denied(
            () -> foreignView.displayName()
        ));

        List<Profile> forBob = List.of(
            secureProfile(aliceRaw, bob),
            secureProfile(bobRaw, bob)
        );
        show("secured list size", forBob.size());
        show("list first email denied", denied(
            () -> forBob.get(0).contact().email()
        ));

        Optional<Profile> optional =
            Optional.of(secureProfile(aliceRaw, alice));
        show("optional email",
            optional.orElseThrow().contact().email());

        // Mục đích: chứng minh raw reference không có proxy.
        show("raw reference unprotected",
            aliceRaw.contact().email().equals(
                "alice@example.test"
            ));
    }
}
```

Chạy:

```bash
javac ReturnedObjectProxyDemo.java
java ReturnedObjectProxyDemo
```

Kết quả stdout dự kiến:

```text
alice display: Alice
alice email: alice@example.test
bob display: Alice
bob email denied: true
auditor email: alice@example.test
foreign display denied: true
secured list size: 2
list first email denied: true
optional email: alice@example.test
raw reference unprotected: true
```

**Đọc kết quả:**

1. Alice là owner T1, có email permission nên được xem email.
2. Bob cùng tenant được xem tên theo policy demo nhưng thiếu email permission nên bị chặn ở nested Contact getter.
3. Auditor T1 có role audit và permission nên được xem email theo ngoại lệ được khai báo rõ.
4. Auditor tenant T2 không qua được điều kiện tenant, dù role/permission giống.
5. List chứa hai secured references; phần tử đầu vẫn chặn email cho Bob.
6. Optional chứa secured reference; unwrap không làm mất bảo vệ getter.
7. Dòng cuối cho thấy một reference **thô** có thể đọc email mà không qua proxy. Trong sản phẩm, không giữ/đưa raw object tới caller chưa được tin cậy.

Chương trình cố tình giới hạn các method được handler hỗ trợ; nó chưa xử lý đầy đủ `equals/hashCode/toString`, không có Spring `SecurityContextHolder`, không xác thực token, không kết nối DB và không tạo proxy cho class concrete. Mục đích là làm rõ **ủy quyền sau khi đã trả một object và truy cập object con**.

## 9. Serialization, Jackson và khác biệt giữa deny với redaction

### 9.1. Getter có thể được Jackson gọi gián tiếp

Trong REST API, Jackson thường gọi getter để tạo JSON. Nếu getter có `@PreAuthorize` mà caller thiếu permission, serializer có thể gặp exception. Điều đó **không đảm bảo** JSON sẽ tự bỏ trường hoặc thay nó bằng null.

Ví dụ response dự kiến của sản phẩm:

```json
{
  "displayName": "Alice",
  "contact": {
    "label": "work"
  }
}
```

Để đạt contract này, cần một safe DTO/mapper hoặc denied handler/masking đã cấu hình và **kiểm thử HTTP thực tế**. Không chỉ dựa vào getter ném AccessDeniedException rồi cho rằng Jackson tự bỏ qua field.

Có thể xảy ra khác biệt về status (403, lỗi serializer, 500), độ sâu graph và thời điểm response body được ghi. Nếu response đã stream một phần, không thể giả định exception sau đó thu hồi mọi byte đã gửi. Spring Security 6.5 cải thiện tích hợp MVC cho `@AuthorizeReturnObject`, nhưng phải test đúng stack Boot/Spring/Jackson của hệ thống.

### 9.2. DTO đã sanitize thường dễ an toàn

Một API public ổn định có thể dùng record:

```java
public record PublicProfileResponse(
    String displayName,
    String contactLabel
) {}

public record PrivateProfileResponse(
    String displayName,
    String contactLabel,
    String email
) {}
```

Service kiểm permission/owner/tenant rồi chọn projection phù hợp. DTO public **không chứa email**, nên không thể lộ email chỉ vì một serializer chọn cách đọc field khác getter. Record final khó cho class-based proxy nhưng nếu đã sanitized, không cần proxy field-level để ẩn secret vốn không có.

Với GraphQL/REST có trường dữ liệu nhạy cảm, một schema/DTO projection có kiểm soát có thể rõ hơn trả entity raw + nhiều lớp proxy.

### 9.3. Denied handler và masking

Spring Security 6.5 có `@HandleAuthorizationDenied` và cơ chế handler cho một số trường hợp pre/post deny. Nếu muốn getter trả null hoặc mask khi permission thiếu, hãy nghiên cứu đúng version và kiểm soát:

- Khi denied, handler không bao giờ trả raw secret.
- Null có thể được serialize thành key null hoặc bỏ key, tùy Jackson config.
- Lỗi khi getter đã có side effect không được giải quyết bằng che output.
- Schema API phải quy định field nào tùy chọn và ý nghĩa dữ liệu che.
- Test end-to-end với principal đủ/thiếu quyền, không chỉ test handler unit.

## 10. JPA/Hibernate, transaction và object identity

### 10.1. Proxy chồng proxy

Một object từ Hibernate có thể đã là lazy proxy. Bọc thêm authorization proxy tạo chuỗi:

```text
Spring Security return proxy
   -> Hibernate entity proxy
      -> entity / lazy association
         -> database
```

Rủi ro:

- Method visibility khác nhau giữa entity/proxy/type thực tế.
- Getter gọi sau khi transaction đóng có thể gặp `LazyInitializationException`.
- Lazy association khi serialize dẫn tới N+1 SQL.
- `equals/hashCode/getClass` trả hành vi khác dự kiến.
- Final class/method hoặc constructor không phù hợp với cách proxy.
- ORM/persistence cache giữ raw reference không có security advice.

Không coi việc bật Open Session in View là giải pháp quyền toàn diện. Scoped query và projection/DTO có transaction boundary rõ thường dễ kiểm soát hơn.

### 10.2. PostAuthorize sau write quá muộn

`@PostAuthorize` cho phép kiểm tra returnObject sau method, không ngăn việc method đã cập nhật database hoặc gửi message. Transaction rollback của một exception tùy advice order và thiết kế, nhưng side effect ngoài DB không tự hoàn tác.

Với ghi/duyệt/xóa, dùng `@PreAuthorize`, policy server-side và UPDATE có điều kiện tenant/owner/status/version. Nếu quyền bị thu hồi giữa hai thời điểm, cần transaction/recheck theo nghiệp vụ.

### 10.3. Identity và hashCode

Một secured proxy có thể không có cùng reference/class quan sát được với raw object. Dùng `==` hoặc `getClass()` để quyết định ownership là sai; dùng domain ID và verified principal.

Nếu proxy được dùng làm Map key hoặc Set element, test `equals/hashCode`. Tránh log `toString()` của entity chứa secret, vì proxy getter không tự bảo vệ mọi cách biểu diễn object.

## 11. AOT / GraalVM Native và generic erased

### 11.1. Vì sao AOT phải biết return types?

Trong JVM thường, proxy có thể được tạo tại runtime. Native/AOT cần chuẩn bị proxy class, reflection/runtime hints. Spring Security 6.5 quét các bean có `@AuthorizeReturnObject` rồi tìm các return types; nếu gặp nested method có annotation tương ứng, nó tiếp tục duyệt.

```text
Controller.getMessage()
   @AuthorizeReturnObject -> MessageView
MessageView.getRecipient()
   @AuthorizeReturnObject -> UserView
UserView.getEmail()
   @PreAuthorize(...)
```

Khi type rõ ràng, scanner có khả năng thu thập những object cần advice/hints.

### 11.2. Generic erasure

Một method:

```java
@AuthorizeReturnObject
public List<MessageView> getMessages() {
    return repository.findVisibleMessages();
}
```

có thể gây khó cho AOT scanner vì Java xóa một phần thông tin generic khi chạy. Tài liệu Spring Security 6.5 dùng tình huống tương tự để giải thích vì sao scanner không luôn tìm được concrete type `MessageView` trước lúc build.

Các tình huống `Object`, raw collections, generic wildcard, polymorphism và wrapper custom càng cần chú ý. Test chạy JVM thành công **không chứng minh** native image đã có đủ proxy hints.

### 11.3. Registrar cho type khó dò

Theo Spring Security 6.5, có thể đăng ký `SecurityHintsRegistrar` bằng `AuthorizeReturnObjectHintsRegistrar` cho các type không được quét tự động:

```java
import org.springframework.beans.factory.config.BeanDefinition;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Role;
import org.springframework.security.aot.hint.SecurityHintsRegistrar;
import org.springframework.security.aot.hint.AuthorizeReturnObjectHintsRegistrar;
import org.springframework.security.authorization.method.AuthorizationProxyFactory;

@Bean
@Role(BeanDefinition.ROLE_INFRASTRUCTURE)
static SecurityHintsRegistrar registerReturnObjectHints(
        AuthorizationProxyFactory factory) {
    return new AuthorizeReturnObjectHintsRegistrar(
        factory, MessageView.class, UserView.class
    );
}
```

Fragment này cần nằm trong class cấu hình, với MessageView/UserView có thật. Kiểm tra JavaDoc đúng Spring Security patch đang dùng. Registrar chỉ chuẩn bị metadata/proxy cho AOT, **không cấp permission**. Nếu native image báo thiếu type, sửa hints và test deny/allow thay vì tắt authorization.

### 11.4. Custom container và TargetVisitor

Một container tự viết không mặc định có cùng cách duyệt như List/Optional/Map. Muốn factory proxy element, có thể cần custom `TargetVisitor` theo API của version. Đừng thay visitor mặc định bằng visitor bỏ qua hết kiểu lạ; điều đó có thể bỏ qua chính những object cần bảo vệ.

Runtime wrapping và AOT hints là **hai yêu cầu khác nhau**. Phải kiểm chứng cả proxy được tạo tại runtime lẫn các type được đăng ký trong native build.

## 12. Hướng kiểm thử đúng: getter, nested, HTTP và native

### 12.1. Test Spring-managed service, không phải raw POJO

Với JUnit 5 và Spring Security Test:

```java
@SpringBootTest
class ProfileProxyTest {
    @Autowired ProfileService service;

    @Test
    @WithMockUser(authorities = {
        "profile:read", "profile:email:read"
    })
    void emailAllowed() {
        ProfileView view = service.findVisibleById(42L);
        assertEquals(
            "alice@example.test",
            view.getContact().getEmail()
        );
    }

    @Test
    @WithMockUser(authorities = {"profile:read"})
    void emailDenied() {
        ProfileView view = service.findVisibleById(42L);
        assertNotNull(view.getDisplayName());
        assertThrows(
            AccessDeniedException.class,
            () -> view.getContact().getEmail()
        );
    }
}
```

Đây là **mã test tích hợp**, cần imports, service, dữ liệu fixture và class Spring phù hợp. Với `@WithMockUser`, Authentication là giả lập; test này không chứng minh JWT validation hay mapping role thật.

Fixture phải cho user test được xem Profile 42 theo tenant/owner policy để cô lập **email getter**, nếu không service có thể bị chặn trước.

### 12.2. Ma trận test

| Trường hợp | Điều cần chứng minh |
| --- | --- |
| Chưa có email permission nhưng có quyền profile | Nhận profile nhưng getter email bị deny |
| Có cả profile và email permission | Getter email được phép theo policy |
| Tài liệu thuộc tenant khác | Không lấy được record/metadata, không chỉ chặn getter email |
| Nested Contact không được proxy | Test phát hiện nguy cơ raw getEmail |
| List có hai phần tử | Từng element được proxy, không chỉ list |
| Map key nhạy cảm | Key không bị lộ dù value proxy |
| Optional empty/nonempty | Không lỗi và element đúng |
| Stream lazy qua thread khác | Context/permission được kiểm đúng, không bị bypass |
| Class-level String/Integer | Value types không gây proxy lỗi |
| Record/final type | Có phương án DTO/projection phù hợp |
| Jackson serialize | Response status, fields, null/omission chính xác |
| Hibernate lazy association | Không lỗi session, N+1 hoặc dữ liệu ngoài tenant |
| Native generic List<T> | Đủ hints, getter deny thật |
| Raw object/log/cache | Không có lối xuất secret ngoài proxy |
| Method self-invocation | Không có đường bypass service authorization |

### 12.3. MockMvc kiểm tra serialization

Với endpoint `GET /profiles/42`, tạo hai principal: người có `profile:read` nhưng thiếu `profile:email:read` và người có đủ cả hai. Chọn **một hợp đồng API** cho email không được phép: 403 toàn response, null, mask hay omit field; sau đó kiểm status + JSON body exact.

Đừng xem 403 ở HTTP là bằng chứng getter đã chạy: có thể do URL matcher hoặc `@PreAuthorize` trên service. Test riêng method qua proxy với user có quyền lấy profile để xác nhận getter-level denial. Khi field bị deny giữa lúc serialize, cần xác minh không có JSON partial leak.

### 12.4. Native/AOT test

Với ứng dụng native, build và chạy các case có `@AuthorizeReturnObject` trả Object, List, Optional, nested Contact. Test thực tế permission đủ/thiếu trong native image. Một test JVM xanh không đủ nếu thiếu runtime hints.

## 13. Các giới hạn tương thích theo phiên bản

| Dòng phiên bản | Điểm cần biết |
| --- | --- |
| Trước 6.3 | Không giả định `@AuthorizeReturnObject` đã tồn tại |
| 6.3 | Annotation/interceptor return-object được giới thiệu |
| 6.4 | Factory/visitor API phát triển; đối chiếu chữ ký JavaDoc đúng bản |
| 6.5 | Tài liệu mô tả container, nested, TargetVisitor skip, AOT hints, denied handler và tích hợp MVC |
| 7.x | Giữ khái niệm nhưng phải kiểm tra defaults/annotation/factory/hints đúng patch |

Để nâng cấp, đọc dependency tree của dự án, không đoán qua tên Spring Boot. Không copy code 7.x vào Spring Security 6.2 rồi kỳ vọng class/method tồn tại.

## 14. Lỗi phổ biến

| Lỗi | Hệ quả | Cách khắc phục |
| --- | --- | --- |
| Có @PreAuthorize trên POJO thô | Getter không có advice | Tạo return-object proxy đúng điểm |
| @AuthorizeReturnObject nhưng method không qua Spring proxy | Không bọc kết quả | Gọi bean/proxy thực |
| Nested getter trả raw object | Getter con không được chặn | Bọc cạnh nested cần thiết |
| List có record tenant khác | Rò count/name/ID | Scoped DB query |
| Map key chứa email bí mật | Key lộ dù value bảo vệ | Không dùng key nhạy cảm |
| Class-level proxy String/Integer | Runtime proxy lỗi | Method-level hoặc TargetVisitor skip |
| Record/final class cần subclass proxy | Proxy không tạo được | Interface projection/safe DTO |
| Jackson gọi getter bị deny | Serialization exception | DTO/denied handler + HTTP test |
| Jackson/mapper đọc raw field | Lộ secret ngoài getter | Không đưa raw secret ra boundary |
| JPA lazy proxy + security proxy | Session/identity/N+1 lỗi | Projection/transaction boundary |
| @PostAuthorize làm chốt ghi | Side effect trước deny | Pre-check + DB guard |
| Generic erased ở native | Thiếu proxy type hints | Hints registrar + native test |
| Parallel stream đổi thread | SecurityContext sai/mất | Context propagation hoặc DTO |
| Logger in raw object | Rò dữ liệu | Redact/mapping trước log |
| Nhầm proxy với record masking | API contract không đúng | DTO riêng hoặc handler được test |
| Test chỉ load object | Không biết getter có bị chặn | Test getter deny/allow |
| 403 được sửa bằng permitAll | Vô hiệu hóa quyền | Chẩn đoán đúng tầng |

## 15. Bài tập thực hành

1. **PostAuthorize so với return proxy:** Viết một read-only service dùng `@PostAuthorize` kiểm owner. Sau đó dùng `@AuthorizeReturnObject` và `@PreAuthorize` trên getter email. Test hai mốc kiểm tra khác nhau.
2. **Nested object:** Mở rộng ProfileView → ContactView → AddressView, định nghĩa quyền riêng cho street. Test khi chỉ được đọc label nhưng không đọc street.
3. **Collection:** Trả `List<ProfileView>` và `Map<String, ProfileView>`; kiểm element proxies và không lộ map key.
4. **Class-level:** Đánh dấu class có method trả String, Integer và ProfileView; quan sát proxy behavior, áp `TargetVisitor.defaultsSkipValueTypes()` trong môi trường test phù hợp.
5. **Java 17:** Chạy `ReturnedObjectProxyDemo.java`, đối chiếu 10 dòng stdout. Thêm actor inactive và kiểm cả raw/secured references.
6. **Serialization:** Dùng Jackson và MockMvc; xác định khi thiếu email permission thì response 403, null hay omit key. Test không lộ secret và không có partial JSON.
7. **Hibernate:** Tạo lazy association, serialize ngoài transaction, rồi thay bằng DTO projection scoped để tránh N+1/lazy failure.
8. **Native/AOT:** Trả `List<MessageView>` có nested UserView, bổ sung hints nếu scanner thiếu type; test cả allow lẫn deny trên native image.

## 16. Checklist trước production

- [ ] @EnableMethodSecurity được bật và advisor tương ứng có hiệu lực.
- [ ] Service method được gọi qua Spring proxy, không phải self-invocation/new object.
- [ ] @AuthorizeReturnObject đặt đúng điểm trả object cần bảo vệ.
- [ ] Getter/method nhạy cảm có @PreAuthorize/@PostAuthorize hoặc manager phù hợp.
- [ ] Mỗi cạnh nested cần proxy đã được đánh dấu và kiểm thử.
- [ ] List/Map/Optional/Stream có đúng element/value được bọc.
- [ ] Query đã giới hạn tenant/owner/share; không dựa vào proxy để ẩn metadata ngoài quyền.
- [ ] Class-level annotation không cố proxy String/Integer/primitive ngoài ý định.
- [ ] DTO final/record được dùng khi nên loại hẳn field nhạy cảm.
- [ ] Jackson/JSON contract có test đủ quyền và thiếu quyền.
- [ ] Không giữ raw references trong logger/cache/exporter chưa kiểm soát.
- [ ] Hibernate lazy loading và transaction boundary được thiết kế.
- [ ] Stream/async không đánh giá getter trong SecurityContext sai.
- [ ] Native/AOT có runtime hints đầy đủ cho erased/nested types.
- [ ] Không dùng @PostAuthorize làm chốt duy nhất cho side effect.
- [ ] Test proxy thật thay vì chỉ kiểm annotation bằng reflection.
- [ ] Test negative: sai tenant, thiếu permission, raw field, nested getter, native và serialization.

## 17. Tự kiểm tra

1. **@PostAuthorize kiểm tra khi nào?** Sau khi method đã chạy, trước khi kết quả được chấp nhận trả về.
2. **@PostFilter làm gì?** Loại phần tử không đủ quyền khỏi một container được hỗ trợ.
3. **@AuthorizeReturnObject làm gì?** Bọc return object để method/getter được đánh giá quyền khi gọi.
4. **Service trả Profile thành công có nghĩa email được phép không?** Không.
5. **Nested Contact có tự được proxy không?** Chỉ khi đường trả về có cấu hình proxy/advice phù hợp.
6. **Annotation getter trên raw POJO có chắc được enforce không?** Không.
7. **Map được proxy chủ yếu ở key hay value?** Giá trị, theo khả năng container được tài liệu mô tả.
8. **Class-level @AuthorizeReturnObject rủi ro vì sao?** Nó áp dụng cho mọi return type, kể cả String/Integer.
9. **TargetVisitor.defaultsSkipValueTypes có tác dụng gì?** Tránh cố proxy những kiểu value không phù hợp.
10. **Java record có thuận lợi cho subclass proxy không?** Không, record là final.
11. **Jackson tự omit getter bị deny?** Không thể giả định.
12. **Vì sao DTO sanitized hữu ích?** Không chứa secret ở boundary nên giảm khả năng lộ qua serializer/log.
13. **@PostAuthorize phù hợp làm chốt duy nhất trước chuyển tiền không?** Không, vì phương thức đã chạy.
14. **Lỗi AOT với List<T> thường do đâu?** Type erasure/build-time scanner có thể bỏ sót concrete element type.
15. **Hints registrar có cấp permission không?** Không; chỉ đăng ký metadata/proxy cần thiết.
16. **Stream khác List ở đâu?** Lazy evaluation có thể diễn ra khi SecurityContext/transaction đã đổi.
17. **Thấy 403 có chứng minh getter bị deny không?** Không, có thể chốt HTTP/service từ chối trước.
18. **Kiểm thử cần những gì?** Caller được xem profile nhưng thiếu email permission; nested getter phải deny trên proxy thật.
19. **Một raw reference còn giữ có rủi ro gì?** Có thể bypass getter proxy và lộ secret.
20. **Khi nào ưu tiên DTO thay return proxy?** API public có schema rõ, dữ liệu rất nhạy cảm, kiểu final/ORM/serializer phức tạp.

**Ghi nhớ:** `@AuthorizeReturnObject` hữu ích để gắn authorization advice cho **các lời gọi trên kết quả trả về**, kể cả một số container và object lồng nhau. Nó không tự lọc tập dữ liệu, không bảo vệ reference thô, không thay query tenant/owner, và không bảo đảm serializer bỏ trường bị deny. Lựa chọn an toàn cần kết hợp **chính sách đầu vào, proxy đúng đường, DTO/projection phù hợp, test negative, và kiểm soát kiểu dữ liệu/AOT**.

### Tài liệu chính thức

- [Spring Security 6.5 – Method Security và Authorizing Arbitrary Objects](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/method-security.html)
- [Spring Security 7.0 – Method Security](https://docs.spring.io/spring-security/reference/7.0/servlet/authorization/method-security.html)
- [Spring Security 6.5 – AuthorizeReturnObject JavaDoc](https://docs.spring.io/spring-security/site/docs/6.5.6/api/org/springframework/security/authorization/method/AuthorizeReturnObject.html)
- [Spring Security 6.5 – AuthorizationAdvisorProxyFactory JavaDoc](https://docs.spring.io/spring-security/site/docs/6.5.x/api/org/springframework/security/authorization/method/AuthorizationAdvisorProxyFactory.html)
- [Spring Security 6.5 – AOT return-object hints](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/method-security.html#method-security-aot)