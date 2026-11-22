# @AuthorizeReturnObject và bảo vệ thành viên của đối tượng theo phiên bản

> **Chủ đề:** Spring Security — Kiểm tra sau phương thức và bảo vệ object trả về. Bài học này giải thích `@AuthorizeReturnObject` làm gì, cách nó **proxy kết quả trả về** để thực thi `@PreAuthorize`/`@PostAuthorize` ở **getter hoặc method của object**, cách xử lý object lồng nhau, `Optional`, `List`, serialization, AOT/native image và sự khác nhau giữa các phiên bản Spring Security. Ví dụ dùng **Java 17+, Spring Boot 3.5.x và Spring Security 6.5.x**, theo mô hình Servlet/Spring MVC.

## 1. Bài toán: cho xem tên nhưng không cho xem email và số điện thoại

Một endpoint hoặc service có thể trả về một object chứa nhiều thành viên:

~~~text
ProfileView
  ├── name:  "Lan"               (thông tin cơ bản)
  ├── email: "lan@example.test"  (cần profile:email)
  └── contact: ContactView
         ├── city:  "HCM"        (thông tin cơ bản)
         └── phone: "0900000000" (cần profile:phone)
~~~

Người dùng có `profile:read` được phép **nhận object profile**, nhưng không mặc nhiên có quyền đọc **mọi getter**. Người dùng chỉ có `profile:email` (mà thiếu `profile:phone`) được thấy email, nhưng không được thấy số điện thoại.

Một cách xử lý là tạo nhiều DTO/endpoint được cấp quyền riêng. Spring Security còn hỗ trợ cách tiếp cận khác: trả về **object có proxy bảo mật** để kiểm tra mỗi khi ứng dụng gọi getter nhạy cảm.

Hãy phân biệt hai câu hỏi:

1. **Có được trả object `ProfileView` hay không?** Một `@PreAuthorize` trên method service có thể kiểm `profile:read` trước khi tạo/trả profile.
2. **Có được gọi `ProfileView.getEmail()` không?** `@PreAuthorize` gắn trên getter quyết định chuyện này khi getter được gọi **qua proxy**.

`@AuthorizeReturnObject` kết nối hai tầng: đánh dấu một method **trả về đối tượng cần được bọc proxy**, để các annotation bảo mật trên **method của đối tượng trả về** tiếp tục được thực thi.

**Điểm cốt lõi:** chỉ viết `@PreAuthorize` trên getter của một POJO tự tạo không có nghĩa getter ấy đã được Spring AOP bảo vệ. Phải có cơ chế proxy/interception phù hợp.

## 2. `@AuthorizeReturnObject` hoạt động ra sao?

Annotation đầy đủ:

~~~java
import org.springframework.security.authorization.method.AuthorizeReturnObject;
~~~

Một service Spring có thể viết:

~~~java
@Service
class ProfileService {

    @AuthorizeReturnObject
    public ProfileView findById(String id) {
        return repository.loadProfile(id);
    }
}
~~~

Đây là **fragment**, cần service/repository/model thật. `@AuthorizeReturnObject` được đặt trên **method trả về** object, không nhất thiết trên class của object. Khi service được gọi qua Spring-managed proxy, interceptor dùng `AuthorizationProxyFactory` để bọc object kết quả.

Class kết quả:

~~~java
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

    @PreAuthorize("hasAuthority('profile:email')")
    public String getEmail() {
        return email;
    }
}
~~~

Đây là **class minh họa**; để dùng cần import `PreAuthorize` và trả một instance của nó từ method có `@AuthorizeReturnObject`. Các method được công khai, không `final`, lớp không `final` để proxy subclass có thể hoạt động.

Khi caller nhận kết quả của `service.findById(...)`:

- Gọi `view.getName()`: không có guard trên getter, nên được thực hiện (nếu đã vượt qua các rào cản trước đó).
- Gọi `view.getEmail()`: proxy nhìn thấy `@PreAuthorize("hasAuthority('profile:email')")` và yêu cầu đúng authority.
- User thiếu `profile:email`: bị từ chối tại **lời gọi getter**, thường ném một `AccessDeniedException` / `AuthorizationDeniedException`.
- User đủ authority: getter trả giá trị email.

**Không phải object bị sửa field:** dữ liệu `email` vẫn nằm trong target; proxy kiểm **lời gọi tới thành viên**. Không coi đó là encryption, field-level filtering tại database hay khả năng tự động che mọi con đường phản chiếu tới dữ liệu.

## 3. Phân biệt ba cơ chế dễ bị nhầm

| Cơ chế | Nơi gắn | Thời điểm kiểm | Quy mô quyết định |
| --- | --- | --- | --- |
| `@PreAuthorize` | Service method hoặc getter/method bất kỳ được proxy | **Trước** khi target method chạy | Cho/từ chối **một lời gọi** |
| `@PostAuthorize` | Method có kết quả | **Sau** khi target chạy | Cho/từ chối việc **trả toàn bộ kết quả** dựa trên SpEL, ví dụ `returnObject.owner` |
| `@AuthorizeReturnObject` | Method/class trả object | Sau khi method nguồn trả object, lúc bọc kết quả | **Tạo proxy**, để method/getter của object kết quả được bảo vệ khi gọi |

Ví dụ hai kiểu thiết kế:

### 3.1. Chặn toàn object bằng `@PostAuthorize`

~~~java
@PostAuthorize("returnObject.owner == authentication.name")
public ProfileView readProfile(String id) {
    return repository.loadProfile(id);
}
~~~

Nếu owner không hợp lệ, caller **không được nhận object**. Đây là hậu kiểm toàn bộ giá trị trả về. Nó không tự tách quyền `getEmail` và `getPhone`.

### 3.2. Cho nhận object, bảo vệ riêng thành viên

~~~java
@PreAuthorize("hasAuthority('profile:read')")
@AuthorizeReturnObject
public ProfileView readProfile(String id) {
    return repository.loadProfile(id);
}
~~~

Với `ProfileView.getEmail()` có `@PreAuthorize("hasAuthority('profile:email')")`, người dùng vẫn có thể đọc name, nhưng lời gọi email bị từ chối nếu thiếu quyền. Như vậy:

- `@PreAuthorize` trên service bảo vệ **đường vào**.
- `@AuthorizeReturnObject` đưa ra **proxy**.
- `@PreAuthorize` trên getter bảo vệ **từng thành viên**.
- Nếu getter dùng `@PostAuthorize` thay vào đó, getter có thể **đã chạy** rồi mới bị từ chối. Đây là lý do lựa chọn pre/post trên getter cần có chủ đích.

**Không coi `@AuthorizeReturnObject` là một biểu thức cho ALLOW/DENY**; annotation này không có chuỗi SpEL như `@PreAuthorize("...")`.

## 4. Luồng gọi qua hai tầng proxy

~~~text
HTTP GET /api/profiles/P-1/email
    |
    v
SecurityFilterChain: cần đăng nhập
    |
    v
Controller gọi Spring-managed ProfileService
    |
    v
Service proxy:
    @PreAuthorize(profile:read) ----DENY----> 403
    |
    v ALLOW
Target service tạo ProfileView
    |
    v
@AuthorizeReturnObject:
    AuthorizationProxyFactory bọc ProfileView
    |
    v
Controller nhận ProfileView có proxy
    |
    v
Controller gọi view.getEmail()
    |
    v
ProfileView proxy:
    @PreAuthorize(profile:email) ---DENY---> 403
    |
    v ALLOW
Target ProfileView.getEmail() -> "lan@example.test"
    |
    v
Controller trả String cho client
~~~

Điểm quan trọng nhất: **method bảo vệ ở object trả về chạy tại thời điểm caller sử dụng object**, không nhất thiết tại lúc service method tạo object. Khi chưa ai gọi `getEmail()`, kiểm tra authority cho getter đó có thể chưa diễn ra.

Trường hợp method `ProfileService.find...` tự trả về object đã tạo bằng `new` không phải vấn đề nếu chính **service** được Spring proxy và `@AuthorizeReturnObject` đã bọc kết quả. Nhưng nếu bạn gọi `new ProfileService().find...` hoặc gọi nội bộ bằng `this.find...` bỏ qua proxy service, bước bọc có thể bị bỏ qua.

Ngoài ra, caller phải sử dụng **instance được proxy trả về**, không dùng một reference tới object thô (raw object) đã lưu ở nơi khác rồi kết luận getter luôn được bảo vệ.

## 5. Phiên bản tương thích: không dùng API ngoài đời quá sớm

Đây là chi tiết bắt buộc vì `@AuthorizeReturnObject` **không tồn tại trong mọi thế hệ Spring Security**.

| Dải phiên bản | Điểm cần biết |
| --- | --- |
| Spring Security **6.2 trở về trước** | Không thể coi `@AuthorizeReturnObject` là annotation có sẵn; chọn bảo vệ service/DTO/`@PostAuthorize` hoặc nâng cấp có kiểm chứng |
| Spring Security **6.3** | Javadoc ghi `@AuthorizeReturnObject` **Since: 6.3**; hỗ trợ bọc return object bằng method security advice |
| Spring Security **6.4** | Các API AOT hints như `AuthorizeReturnObjectHintsRegistrar` có Javadoc `Since: 6.4`; cần chú ý native image khi type bị generic erasure |
| Spring Security **6.5** | Tài liệu chính thức mô tả proxy object, `Optional`/collection/map value, nested `@AuthorizeReturnObject`, `TargetVisitor`, `AuthorizationProxyFactory`, AOT; cải thiện tích hợp Spring MVC cũng được nêu trong release notes 6.5 |
| Spring Security **7.x trở lên** | Tên API có thể vẫn tồn tại nhưng cách config/AOT/serialization có thể thay đổi; kiểm tra reference và JavaDoc **đúng phiên bản đang chạy**, không lấy sample 6.5 làm cam kết vĩnh viễn |

**Lưu ý quan trọng:** Spring Boot quản lý phiên bản Spring Security theo dependency management. “Ứng dụng dùng Java 17” **không** có nghĩa đang có Spring Security 6.5. Hãy xác định dependency thực tế bằng Maven/Gradle thay vì suy đoán từ import hoặc blog post.

Ví dụ kiểm tra:

~~~bash
# Trong Maven project, xem artifact thực sự được resolve:
./mvnw dependency:tree -Dincludes=org.springframework.security

# Với Gradle:
./gradlew dependencyInsight --dependency spring-security-config \
    --configuration runtimeClasspath
~~~

Trên Windows dùng `mvnw.cmd`/`gradlew.bat`. Cú pháp flag/cấu hình của build tool cần phù hợp project. Nếu đang dùng Boot 3.x với Spring Security thấp hơn 6.3, import `AuthorizeReturnObject` sẽ **không biên dịch**, đó là vấn đề dependency/version, không phải quyền runtime.

## 6. Những điều kiện để proxy được tạo đúng

### 6.1. Bean nguồn phải đi qua Spring AOP

`@EnableMethodSecurity` cần được bật; method trả object thuộc Spring-managed bean và lời gọi phải đi qua proxy. Self-invocation (`this.findById(...)`) trong cùng service có thể bỏ qua interceptor `@AuthorizeReturnObject`.

### 6.2. Object trả về phải thích hợp để proxy

Một class POJO bình thường, có getter/method public **không final**, là lựa chọn dễ kiểm soát. Một số kiểu có giới hạn:

- Java `record` là `final`; không giả định có thể tạo class-based proxy cho record giống POJO thường.
- `String`, `Integer`, `Double` và nhiều value types không thích hợp cho việc proxy subclass.
- Method `private`, `final`, đối tượng đã bị đóng gói theo một proxy strategy khác có thể không nhận advice như mong đợi.
- Kotlin classes mặc định final nếu không dùng `open`/plugin mở class; test với cấu hình Kotlin thực tế.
- Dùng object từ Hibernate/JPA hoặc proxy của thư viện khác có thể tương tác phức tạp với Spring Security proxy; không kết luận chỉ từ annotation trên entity.

**Quy tắc học tập:** sử dụng non-final Java class, getter public, không đưa security-critical value vào public field. Kiểm thử proxy ở runtime.

### 6.3. Không gắn annotation class-level tràn lan

Theo API, `@AuthorizeReturnObject` có thể đặt ở class-level; về ý nghĩa là áp dụng cho mỗi method trong class đó. Nhưng khi class có method trả `String`, `int`, `Integer` hay kiểu số/giá trị, Spring Security có thể cố **proxy cả những return types không nên proxy**.

~~~java
// Cảnh báo: class-level khiến tất cả các method bị bao phủ.
@AuthorizeReturnObject
@Service
class MixedService {
    public ProfileView find() { return new ProfileView(); }
    public String health() { return "ok"; }
}
~~~

Đây là **phản ví dụ**. Trong ứng dụng cụ thể, `new ProfileView()` cần constructor phù hợp; mục đích chỉ để thấy phạm vi class-level. Không copy class này như đoạn runnable.

Cách rõ ràng hơn là **gắn `@AuthorizeReturnObject` lên từng method trả object cần bọc**. Nếu có lý do dùng class-level, Spring Security 6.5 đề xuất `TargetVisitor` để bỏ qua value types:

~~~java
// Fragment Spring configuration, cần import:
// org.springframework.security.authorization.method
//     .AuthorizationAdvisorProxyFactory.TargetVisitor

@Bean
static TargetVisitor skipSimpleValues() {
    return TargetVisitor.defaultsSkipValueTypes();
}
~~~

Đây là tùy chỉnh cho trường hợp có mục đích cụ thể, không bắt buộc trong ví dụ đầy đủ phía dưới vì chúng ta **không** dùng class-level annotation.

## 7. Bảo vệ thành viên lồng nhau bằng thêm `@AuthorizeReturnObject`

Một `ProfileView` có thể chứa `ContactView`. Việc proxy một `ProfileView` **không đồng nghĩa mọi object ở bên trong được proxy sâu vô hạn**. Để bảo vệ tiếp getter của `ContactView`, đánh dấu method trả `ContactView`:

~~~java
public class ProfileView {
    private final ContactView contact;

    public ProfileView(ContactView contact) {
        this.contact = contact;
    }

    @AuthorizeReturnObject
    public ContactView getContact() {
        return contact;
    }
}

public class ContactView {
    private final String city;
    private final String phone;

    public ContactView(String city, String phone) {
        this.city = city;
        this.phone = phone;
    }

    public String getCity() {
        return city;
    }

    @PreAuthorize("hasAuthority('profile:phone')")
    public String getPhone() {
        return phone;
    }
}
~~~

Hai class là **fragments** được biểu diễn để thấy cơ chế, cần import Spring Security annotations tương ứng. Khi `ProfileView` đã là proxy, lời gọi `view.getContact()` được interceptor của `@AuthorizeReturnObject` bọc tiếp `ContactView`. Người gọi sau đó sử dụng `contact.getPhone()` phải có `profile:phone`.

**Phân biệt rõ đường đi:**

- `view.getName()`: thông tin không có annotation quyền tại getter.
- `view.getEmail()`: cần `profile:email` nếu getter annotated.
- `view.getContact().getCity()`: việc lấy `ContactView` có thể không đòi `profile:phone`, còn `getCity()` không có guard.
- `view.getContact().getPhone()`: cần `profile:phone`.

Nếu bỏ `@AuthorizeReturnObject` trên `getContact()`, bạn có thể nhận **raw ContactView**, và `@PreAuthorize` trên `getPhone()` của raw POJO không được áp dụng như kỳ vọng. Test **negative** cho getter lồng nhau là bắt buộc.

## 8. `Optional`, `List`, `Map` và object khác

Spring Security 6.5 mô tả `AuthorizationProxyFactory` có thể proxy:

- Object đơn như `ProfileView`.
- `Optional<ProfileView>`: giá trị bên trong có thể được bọc proxy.
- `List<ProfileView>`/`Collection`: các phần tử object được proxy.
- Array, stream, iterator: có cơ chế traversal hỗ trợ theo tài liệu.
- `Map<K, ProfileView>`: **map values** được proxy khi factory xử lý map.

Ví dụ:

~~~java
@Service
class ProfileService {

    @AuthorizeReturnObject
    public Optional<ProfileView> findOptional(String id) {
        return repository.findOptional(id);
    }

    @AuthorizeReturnObject
    public List<ProfileView> findAll() {
        return repository.findAll();
    }
}
~~~

Đây là **fragment**; cần repository/model. Với `Optional.empty()` không có object bên trong để gọi getter. Với `List`, việc lấy list không nhất thiết đã gọi `getEmail()` của từng phần tử; authorization của getter chỉ diễn ra khi phần tử được sử dụng qua proxy.

**Không hiểu nhầm “proxy collection” là “lọc dữ liệu”.** Nếu list gồm mười profile, một `@PreAuthorize` trên `getEmail` chỉ kiểm khi caller đọc email của từng profile; nó không xóa trước các profile không thuộc tenant. Muốn lọc danh sách theo owner/tenant, ưu tiên truy vấn có điều kiện quyền ở database hoặc `@PostFilter` khi phù hợp.

### Tránh tưởng rằng Map key cũng được bảo vệ

Trong `Map<String, ProfileView>`, tài liệu nhấn mạnh factory proxy **giá trị** của map, không phải một chính sách tự bảo vệ key. Nếu map key chứa thông tin nhạy cảm, chỉ proxy value chưa đủ. Cần kiểm/thiết kế dữ liệu trả ngay ở tầng service.

### Khi dùng generics và AOT

Ở JVM thường, một `List<ProfileView>` được duyệt/proxy theo type runtime. Nhưng Spring AOT/native image cần biết trước các classes phải tạo proxy. Vì **type erasure**, quy trình AOT có thể không suy ra mọi kiểu phần tử chỉ từ method return type. Mục 12 sẽ trình bày cách đăng ký hints rõ ràng.

## 9. Java 17 thuần: mô phỏng bảo vệ getter trước khi dùng Spring

Đây là mô hình dùng **delegation**, giúp thấy cách “cho nhận một view nhưng chặn getter nhạy cảm”. Nó **không triển khai Spring AOP** và không chứng minh `@AuthorizeReturnObject` chạy ở framework thật.

Tạo file **`MemberAccessDemo.java`**:

~~~java
import java.util.Set;
import java.util.function.Supplier;

public class MemberAccessDemo {

    record RawProfile(String name, String email, String phone) {}

    static final class SecuredProfile {
        private final RawProfile profile;
        private final Set<String> authorities;

        SecuredProfile(RawProfile profile, Set<String> authorities) {
            this.profile = profile;
            this.authorities = authorities;
        }

        private void require(String authority) {
            if (!authorities.contains(authority)) {
                throw new SecurityException("Missing " + authority);
            }
        }

        String getName() {
            require("profile:read");
            return profile.name();
        }

        String getEmail() {
            require("profile:email");
            return profile.email();
        }

        String getPhone() {
            require("profile:phone");
            return profile.phone();
        }
    }

    static String attempt(Supplier<String> operation) {
        try {
            return operation.get();
        } catch (SecurityException exception) {
            return "DENY";
        }
    }

    public static void main(String[] args) {
        RawProfile raw = new RawProfile(
            "Lan", "lan@example.test", "0900000000"
        );

        SecuredProfile reader = new SecuredProfile(
            raw, Set.of("profile:read")
        );
        SecuredProfile emailer = new SecuredProfile(
            raw, Set.of("profile:read", "profile:email")
        );
        SecuredProfile phoneUser = new SecuredProfile(
            raw, Set.of("profile:read", "profile:phone")
        );
        SecuredProfile outsider = new SecuredProfile(
            raw, Set.of()
        );

        System.out.println("reader.name=" + attempt(reader::getName));
        System.out.println("reader.email=" + attempt(reader::getEmail));
        System.out.println("reader.phone=" + attempt(reader::getPhone));
        System.out.println("emailer.email=" + attempt(emailer::getEmail));
        System.out.println("phoneUser.phone=" + attempt(phoneUser::getPhone));
        System.out.println("outsider.name=" + attempt(outsider::getName));
    }
}
~~~

Chạy:

~~~bash
javac MemberAccessDemo.java
java MemberAccessDemo
~~~

**Stdout chính xác:**

~~~text
reader.name=Lan
reader.email=DENY
reader.phone=DENY
emailer.email=lan@example.test
phoneUser.phone=0900000000
outsider.name=DENY
~~~

Ở đây `RawProfile` là một **record final** vì chỉ là dữ liệu của chương trình Java thuần; `SecuredProfile` làm việc bằng **delegation thủ công**, không phải Spring proxy. Trong ứng dụng Spring phía dưới, `ProfileView`/`ContactView` là **non-final public classes** để phù hợp với proxy method authorization.

## 10. Spring Boot 3.5 / Spring Security 6.5: ứng dụng chạy được

### 10.1. Kịch bản phân quyền

Ứng dụng cung cấp một profile `P-1`:

| Field | Giá trị | Quyền cần |
| --- | --- | --- |
| `name` | `Lan` | `profile:read` ở service, không có guard riêng ở getter |
| `email` | `lan@example.test` | `profile:read` + `profile:email` |
| `contact.city` | `HCM` | `profile:read` |
| `contact.phone` | `0900000000` | `profile:read` + `profile:phone` |

Tài khoản:

| User | Authorities |
| --- | --- |
| `reader` | `profile:read` |
| `emailer` | `profile:read`, `profile:email` |
| `phoneuser` | `profile:read`, `profile:phone` |
| `superreader` | `profile:read`, `profile:email`, `profile:phone` |
| `outsider` | `ROLE_USER` |

Mục tiêu không phải tạo ra “role cao nhất được xem hết” theo suy đoán. Mỗi quyền là authority literal được cấp rõ ràng. Tất cả HTTP endpoint dùng GET để tập trung vào method security thay vì lẫn với CSRF của method ghi.

### 10.2. Dependencies

Tạo Maven Spring Boot **3.5.x**, Java 17+, có:

- `spring-boot-starter-web`.
- `spring-boot-starter-security`.
- `spring-boot-starter-test` ở test scope.
- `spring-security-test` ở test scope.

Nếu dùng Spring Initializr và Boot BOM/parent, các phiên bản được quản lý nhất quán. **Xác minh** dependency `spring-security-config` thực sự thuộc **6.5.x** trước khi dùng API trong bài.

### 10.3. Một file ứng dụng đầy đủ

Tạo file **`src/main/java/com/example/returned/ReturnObjectApplication.java`**:

~~~java
package com.example.returned;

import java.util.List;
import java.util.Optional;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.http.HttpStatus;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.authorization.method.AuthorizeReturnObject;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.stereotype.Service;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

@SpringBootApplication
@EnableMethodSecurity
public class ReturnObjectApplication {

    public static void main(String[] args) {
        SpringApplication.run(ReturnObjectApplication.class, args);
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/public/ping").permitAll()
                .requestMatchers("/api/profiles/**").authenticated()
                .anyRequest().denyAll()
            )
            .httpBasic(Customizer.withDefaults());
        return http.build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        UserDetails reader = User.withUsername("reader")
            .password(encoder.encode("reader123"))
            .authorities("profile:read")
            .build();

        UserDetails emailer = User.withUsername("emailer")
            .password(encoder.encode("emailer123"))
            .authorities("profile:read", "profile:email")
            .build();

        UserDetails phoneuser = User.withUsername("phoneuser")
            .password(encoder.encode("phone123"))
            .authorities("profile:read", "profile:phone")
            .build();

        UserDetails superreader = User.withUsername("superreader")
            .password(encoder.encode("super123"))
            .authorities(
                "profile:read", "profile:email", "profile:phone"
            )
            .build();

        UserDetails outsider = User.withUsername("outsider")
            .password(encoder.encode("outsider123"))
            .roles("USER")
            .build();

        return new InMemoryUserDetailsManager(
            reader, emailer, phoneuser, superreader, outsider
        );
    }

    // Đối tượng được proxy: KHÔNG final và getter KHÔNG final.
    public static class ProfileView {
        private final String id;
        private final String name;
        private final String email;
        private final ContactView contact;

        public ProfileView(String id, String name,
                           String email, ContactView contact) {
            this.id = id;
            this.name = name;
            this.email = email;
            this.contact = contact;
        }

        public String getId() {
            return id;
        }

        public String getName() {
            return name;
        }

        @PreAuthorize("hasAuthority('profile:email')")
        public String getEmail() {
            return email;
        }

        // Chuyển sang proxy cho object lồng nhau.
        @AuthorizeReturnObject
        public ContactView getContact() {
            return contact;
        }
    }

    public static class ContactView {
        private final String city;
        private final String phone;

        public ContactView(String city, String phone) {
            this.city = city;
            this.phone = phone;
        }

        public String getCity() {
            return city;
        }

        @PreAuthorize("hasAuthority('profile:phone')")
        public String getPhone() {
            return phone;
        }
    }

    @Service
    public static class ProfileService {

        private ProfileView sample() {
            return new ProfileView(
                "P-1",
                "Lan",
                "lan@example.test",
                new ContactView("HCM", "0900000000")
            );
        }

        @PreAuthorize("hasAuthority('profile:read')")
        @AuthorizeReturnObject
        public ProfileView find(String id) {
            if (!"P-1".equals(id)) {
                throw new ResponseStatusException(
                    HttpStatus.NOT_FOUND, "Profile not found"
                );
            }
            return sample();
        }

        @PreAuthorize("hasAuthority('profile:read')")
        @AuthorizeReturnObject
        public Optional<ProfileView> findOptional(String id) {
            return "P-1".equals(id)
                ? Optional.of(sample())
                : Optional.empty();
        }

        @PreAuthorize("hasAuthority('profile:read')")
        @AuthorizeReturnObject
        public List<ProfileView> findAll() {
            return List.of(sample());
        }
    }

    @RestController
    static class Api {
        private final ProfileService service;

        Api(ProfileService service) {
            this.service = service;
        }

        @GetMapping("/public/ping")
        String ping() {
            return "pong";
        }

        @GetMapping("/api/profiles/{id}/name")
        String name(@PathVariable("id") String id) {
            return service.find(id).getName();
        }

        @GetMapping("/api/profiles/{id}/email")
        String email(@PathVariable("id") String id) {
            return service.find(id).getEmail();
        }

        @GetMapping("/api/profiles/{id}/contact/city")
        String city(@PathVariable("id") String id) {
            return service.find(id).getContact().getCity();
        }

        @GetMapping("/api/profiles/{id}/contact/phone")
        String phone(@PathVariable("id") String id) {
            return service.find(id).getContact().getPhone();
        }

        // Optional có phần tử: bên trong phải được proxy.
        @GetMapping("/api/profiles/optional/{id}/email")
        String optionalEmail(@PathVariable("id") String id) {
            return service.findOptional(id)
                .map(ProfileView::getEmail)
                .orElseThrow(() -> new ResponseStatusException(
                    HttpStatus.NOT_FOUND, "Profile not found"
                ));
        }

        // List phần tử: getter của từng phần tử cần được bảo vệ.
        @GetMapping("/api/profiles/all/emails")
        List<String> allEmails() {
            return service.findAll().stream()
                .map(ProfileView::getEmail)
                .toList();
        }

        @GetMapping("/api/unknown")
        String unknown() {
            return "must not be reached";
        }
    }
}
~~~

### 10.4. Tại sao ví dụ dùng controller trả String thay vì trả raw ProfileView?

Một object có `getEmail()` gắn `@PreAuthorize` sẽ bị kiểm khi một framework **gọi getter**. Nếu controller trả nguyên `ProfileView` để Jackson tự serialize, Jackson có thể gọi **mọi getter**, bao gồm các getter nhạy cảm. Khi getter bị từ chối, toàn request có thể nhận **403** thay vì tự động có JSON “thiếu trường email”.

Bởi vậy ứng dụng demo chọn từng endpoint và **chủ động gọi getter**:

- `/name`: gọi getter thường.
- `/email`: gọi getter có `profile:email` guard.
- `/contact/city`: object lồng nhau được proxy; city có thể xem.
- `/contact/phone`: getter lồng nhau có `profile:phone` guard.

Cách này tạo ra ma trận 200/403 rõ ràng. **Không hiểu nhầm `@AuthorizeReturnObject` là JSON masking mặc định**. Nếu cần trả một JSON object với field email được ẩn, nên dùng **DTO projection theo quyền** hoặc `@HandleAuthorizationDenied` với policy masking đã được thiết kế/kiểm thử phù hợp.

### 10.5. Tại sao `ProfileView` và `ContactView` không phải record?

Java `record` thường là `final`, còn class-based proxy cần khả năng intercept method. Vì bài này cố ý kiểm bằng AOP proxy, sử dụng class public, không final, với getter public không final. Dùng immutable record hoặc Kotlin data class trong hệ thống thật cần một thiết kế proxy khác hoặc mapping sang DTO trước khi expose; không coi record là “bị lỗi framework” nếu nó không proxy được theo cách này.

## 11. Ma trận kết quả cần kiểm chứng

### 11.1. HTTP endpoints

| User | GET name | GET email | GET city | GET phone |
| --- | :---: | :---: | :---: | :---: |
| Anonymous | 401 | 401 | 401 | 401 |
| Reader — chỉ `profile:read` | **200** | 403 | **200** | 403 |
| Emailer — read + email | **200** | **200** | **200** | 403 |
| Phoneuser — read + phone | **200** | 403 | **200** | **200** |
| Superreader — cả ba | **200** | **200** | **200** | **200** |
| Outsider — chỉ `ROLE_USER` | 403 | 403 | 403 | 403 |

Tất cả request đều dùng `P-1` trong path và được gửi bằng HTTP Basic như ứng dụng mẫu. Đối với tài khoản có `profile:read`, `GET /api/profiles/X/name` phải nhận 404 vì `X` không tồn tại. Với outsider thiếu `profile:read`, có thể bị 403 trước khi lookup. Cần xác định chính sách trả 403/404 khi không muốn lộ sự tồn tại của object.

### 11.2. Optional và List

| Endpoint | Reader | Emailer | Phoneuser | Superreader |
| --- | :---: | :---: | :---: | :---: |
| `GET /api/profiles/optional/P-1/email` | 403 | 200 | 403 | 200 |
| `GET /api/profiles/optional/X/email` | 404 | 404 | 404 | 404 |
| `GET /api/profiles/all/emails` | 403 | 200 | 403 | 200 |

`Optional.empty()` không có member để kiểm. `List<ProfileView>` chứa các phần tử đã được proxy: quá trình gọi `getEmail` trên từng phần tử phải đi qua guard. Đây **không** phải `@PostFilter` và không tự lọc một phần tử khỏi list nếu email bị từ chối.

### 11.3. Body các endpoint ALLOW

| Request | Body dự kiến |
| --- | --- |
| Public ping | `pong` |
| Reader GET name | `Lan` |
| Reader GET city | `HCM` |
| Emailer GET email | `lan@example.test` |
| Phoneuser GET phone | `0900000000` |
| Superreader GET all/emails | JSON list `["lan@example.test"]` |

**403 nghĩa là một guard không cho thực hiện lời gọi**, không phải object không tồn tại. Với form login hoặc custom exception handling, status và body có thể khác demo.

## 12. Chạy thử bằng curl

Từ root Maven project:

~~~bash
# Linux / macOS:
./mvnw spring-boot:run

# Windows:
mvnw.cmd spring-boot:run
~~~

Khi app mở ở `http://localhost:8080`:

~~~bash
# Public và anonymous:
curl -i http://localhost:8080/public/ping
curl -i http://localhost:8080/api/profiles/P-1/name

# Reader xem name/city, không được xem email/phone:
curl -i -u reader:reader123 http://localhost:8080/api/profiles/P-1/name
curl -i -u reader:reader123 http://localhost:8080/api/profiles/P-1/contact/city
curl -i -u reader:reader123 http://localhost:8080/api/profiles/P-1/email
curl -i -u reader:reader123 http://localhost:8080/api/profiles/P-1/contact/phone

# Emailer xem email nhưng không xem phone:
curl -i -u emailer:emailer123 http://localhost:8080/api/profiles/P-1/email
curl -i -u emailer:emailer123 http://localhost:8080/api/profiles/P-1/contact/phone

# Phoneuser xem phone nhưng không xem email:
curl -i -u phoneuser:phone123 http://localhost:8080/api/profiles/P-1/contact/phone
curl -i -u phoneuser:phone123 http://localhost:8080/api/profiles/P-1/email

# Optional, list, not-found:
curl -i -u emailer:emailer123 http://localhost:8080/api/profiles/optional/P-1/email
curl -i -u reader:reader123 http://localhost:8080/api/profiles/all/emails
curl -i -u reader:reader123 http://localhost:8080/api/profiles/X/name

# HTTP default deny:
curl -i -u superreader:super123 http://localhost:8080/api/unknown
~~~

Trong production, không dùng mật khẩu mẫu. HTTP Basic cần HTTPS; quyền từ `UserDetailsService` ở demo chỉ phục vụ học tập, còn hệ thống thật phải có identity provider và chính sách cấp quyền phù hợp.

## 13. Kiểm thử bằng Spring Security Test và MockMvc

### 13.1. Dependencies test

Trong `pom.xml` đảm bảo có (không thêm dependency trùng):

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-test</artifactId>
    <scope>test</scope>
</dependency>
<dependency>
    <groupId>org.springframework.security</groupId>
    <artifactId>spring-security-test</artifactId>
    <scope>test</scope>
</dependency>
~~~

Đây là fragment XML nằm trong `<dependencies>` của POM. Spring Boot dependency management nên quản lý version nhất quán.

### 13.2. Lớp test hoàn chỉnh

Tạo file **`src/test/java/com/example/returned/ReturnObjectApplicationTests.java`**:

~~~java
package com.example.returned;

import java.util.List;
import java.util.Optional;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.CsvSource;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.test.context.support.WithMockUser;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.request.MockHttpServletRequestBuilder;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class ReturnObjectApplicationTests {

    @Autowired
    MockMvc mvc;

    @Autowired
    ReturnObjectApplication.ProfileService service;

    @ParameterizedTest
    @CsvSource({
        // username,password,path,expected HTTP status
        "anonymous,none,/public/ping,200",
        "anonymous,none,/api/profiles/P-1/name,401",
        "reader,reader123,/api/profiles/P-1/name,200",
        "reader,reader123,/api/profiles/P-1/email,403",
        "reader,reader123,/api/profiles/P-1/contact/city,200",
        "reader,reader123,/api/profiles/P-1/contact/phone,403",
        "reader,reader123,/api/profiles/X/name,404",
        "reader,reader123,/api/profiles/optional/P-1/email,403",
        "reader,reader123,/api/profiles/optional/X/email,404",
        "reader,reader123,/api/profiles/all/emails,403",

        "emailer,emailer123,/api/profiles/P-1/name,200",
        "emailer,emailer123,/api/profiles/P-1/email,200",
        "emailer,emailer123,/api/profiles/P-1/contact/phone,403",
        "emailer,emailer123,/api/profiles/optional/P-1/email,200",
        "emailer,emailer123,/api/profiles/all/emails,200",

        "phoneuser,phone123,/api/profiles/P-1/email,403",
        "phoneuser,phone123,/api/profiles/P-1/contact/phone,200",
        "phoneuser,phone123,/api/profiles/all/emails,403",

        "superreader,super123,/api/profiles/P-1/email,200",
        "superreader,super123,/api/profiles/P-1/contact/phone,200",
        "superreader,super123,/api/profiles/all/emails,200",
        "superreader,super123,/api/unknown,403",

        "outsider,outsider123,/api/profiles/P-1/name,403",
        "outsider,outsider123,/api/profiles/P-1/email,403"
    })
    void httpAuthorizationMatrix(
            String username, String password,
            String path, int expectedStatus
    ) throws Exception {
        MockHttpServletRequestBuilder request = get(path);
        if (!"anonymous".equals(username)) {
            request.with(httpBasic(username, password));
        }
        mvc.perform(request).andExpect(status().is(expectedStatus));
    }

    @Test
    void returnedNameIsAllowedButEmailIsDenied() throws Exception {
        mvc.perform(get("/api/profiles/P-1/name")
                .with(httpBasic("reader", "reader123")))
            .andExpect(status().isOk())
            .andExpect(content().string("Lan"));

        mvc.perform(get("/api/profiles/P-1/email")
                .with(httpBasic("reader", "reader123")))
            .andExpect(status().isForbidden());
    }

    @Test
    void emailAndPhoneAreIndependent() throws Exception {
        mvc.perform(get("/api/profiles/P-1/email")
                .with(httpBasic("emailer", "emailer123")))
            .andExpect(status().isOk())
            .andExpect(content().string("lan@example.test"));

        mvc.perform(get("/api/profiles/P-1/contact/phone")
                .with(httpBasic("emailer", "emailer123")))
            .andExpect(status().isForbidden());

        mvc.perform(get("/api/profiles/P-1/contact/phone")
                .with(httpBasic("phoneuser", "phone123")))
            .andExpect(status().isOk())
            .andExpect(content().string("0900000000"));
    }

    @Test
    void listContainsSecuredElements() throws Exception {
        mvc.perform(get("/api/profiles/all/emails")
                .with(httpBasic("superreader", "super123")))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$[0]").value("lan@example.test"));

        mvc.perform(get("/api/profiles/all/emails")
                .with(httpBasic("reader", "reader123")))
            .andExpect(status().isForbidden());
    }

    @Test
    @WithMockUser(authorities = "profile:read")
    void directServiceProxyProtectsMembers() {
        ReturnObjectApplication.ProfileView view = service.find("P-1");
        assertEquals("Lan", view.getName());
        assertThrows(AccessDeniedException.class, view::getEmail);

        ReturnObjectApplication.ContactView contact = view.getContact();
        assertEquals("HCM", contact.getCity());
        assertThrows(AccessDeniedException.class, contact::getPhone);
    }

    @Test
    @WithMockUser(authorities = {"profile:read", "profile:email"})
    void optionalAndListProxyTheirElements() {
        Optional<ReturnObjectApplication.ProfileView> optional =
            service.findOptional("P-1");

        assertTrue(optional.isPresent());
        assertEquals("lan@example.test", optional.orElseThrow().getEmail());

        List<ReturnObjectApplication.ProfileView> views =
            service.findAll();
        assertEquals(1, views.size());
        assertEquals("lan@example.test", views.get(0).getEmail());
        assertThrows(
            AccessDeniedException.class,
            () -> views.get(0).getContact().getPhone()
        );
        assertFalse(service.findOptional("X").isPresent());
    }

    @Test
    @WithMockUser(authorities = "profile:email")
    void cannotReceiveViewWithoutBaseReadPermission() {
        assertThrows(
            AccessDeniedException.class,
            () -> service.find("P-1")
        );
    }

    @Test
    void badPasswordIsAuthenticationFailure() throws Exception {
        mvc.perform(get("/api/profiles/P-1/name")
                .with(httpBasic("reader", "wrong-password")))
            .andExpect(status().isUnauthorized());
    }
}
~~~

### 13.3. Ý nghĩa các ca test

- **HTTP matrix:** không chỉ test superreader được 200, mà còn test reader bị 403 ở email/phone và outsider bị chặn ngay từ service.
- **Direct Spring bean test:** xác minh **đúng object proxy** từ `service.find(...)`. Đối tượng được trả đã cho xem name nhưng từ chối `getEmail`.
- **Nested test:** `getContact()` phải trả ContactView có proxy; nếu bỏ `@AuthorizeReturnObject` trên nested getter, test `contact.getPhone()` thiếu quyền sẽ có nguy cơ thất bại.
- **Optional/List test:** chứng minh bảo vệ các phần tử, không chỉ object đơn. `Optional.empty` không gây phép gọi getter.
- **Base permission test:** nếu người dùng chỉ có `profile:email` nhưng không có `profile:read`, service `@PreAuthorize` từ chối trước khi tạo/trả ProfileView.
- **Authentication test:** mật khẩu sai dẫn tới 401 với HTTP Basic; không nhầm với getter 403.

**Không dùng `new ProfileService()` để viết security test** vì object tự tạo không qua Spring AOP proxy. `@WithMockUser` trong test được cung cấp bởi `spring-security-test` và giả lập Authentication để kiểm quy tắc trực tiếp; `httpBasic` đi qua UserDetailsService demo.

### 13.4. Chạy test

~~~bash
# Linux/macOS:
./mvnw test

# Windows:
mvnw.cmd test
~~~

Các status/output ở trên là **kỳ vọng được thiết kế**, không phải tuyên bố rằng bộ test đã được chạy. Khi nâng Spring Security hoặc đổi proxy settings, hãy chạy trên đúng artifact/dependency version của ứng dụng để xác minh kết quả.

## 14. Jackson/REST serialization: bài toán hay gây nhầm nhất

Một API có thể muốn trả:

~~~json
{
  "name": "Lan",
  "email": null,
  "contact": {
    "city": "HCM",
    "phone": null
  }
}
~~~

Nhưng **`@AuthorizeReturnObject` không tự bảo đảm tạo JSON như vậy**. Jackson gọi getter trên proxy; getter thiếu quyền mặc định có thể ném `AccessDeniedException`. Tùy điểm lỗi, toàn response có thể bị từ chối hoặc chịu ảnh hưởng của exception mapper/serialization buffering. Không hứa “các field không được phép sẽ tự biến mất”.

Có ba hướng triển khai:

1. **Chọn DTO theo quyền từ service/controller:** chỉ đưa field được phép vào DTO, tránh gọi getter cấm. Hữu ích khi API có hợp đồng rõ ràng và cần phân trang, field masking nhất quán.
2. **Sử dụng `@HandleAuthorizationDenied` với policy trả fallback/masking:** ở Spring Security 6.5, có thể cung cấp `MethodAuthorizationDeniedHandler` để trả null hoặc chuỗi đã che khi thiếu quyền. Handler phải được implement/registered đúng; không tự động có chỉ vì dùng `@AuthorizeReturnObject`.
3. **Trả 403 toàn request:** phù hợp khi bất kỳ field bắt buộc nào thiếu quyền sẽ khiến cả response không được phép xuất ra.

### `@HandleAuthorizationDenied` không phải “mở quyền”

Ví dụ mô hình:

~~~java
// Fragment: annotation cho một getter. Class MaskingHandler phải
// implement MethodAuthorizationDeniedHandler phù hợp và là Spring bean.
@PreAuthorize("hasAuthority('profile:email')")
@HandleAuthorizationDenied(handlerClass = MaskingHandler.class)
public String getEmail() {
    return email;
}
~~~

Đây là **fragment**, `MaskingHandler` không phải class mặc định của Spring. Handler có thể trả `null` hoặc giá trị đã che theo contract của `MethodAuthorizationDeniedHandler`. Một handler sai có thể **làm rò dữ liệu bị từ chối**, nhất là khi được phép xem giá trị gốc. Không copy fragment khi chưa có handler đáng tin, test bằng các user đủ/thiếu quyền và kiểm JSON thực.

Nếu muốn ẩn cả tên field khi null, Spring Boot có tùy chọn Jackson non-null inclusion; cũng cần kiểm serialization thực và hợp đồng API.

### Bảo mật field không dừng ở Jackson

Ngay cả khi getter proxy từ chối, dữ liệu nhạy cảm vẫn có thể tồn tại trong **raw target**, cache, log, event hoặc field access của serializer không đi qua getter. Không nên chỉ dựa vào getter interception để bảo vệ mọi đường truy cập một object JPA/entity thô. DTO minimization, scope query và policy server-side vẫn rất quan trọng.

## 15. AOT/native image: vì sao phiên bản và generic type quan trọng?

Spring AOT/native image thường cần đăng ký proxy/hints tại build time. Spring Security 6.5 có thể scan các Spring beans và những method gắn `@AuthorizeReturnObject`, sau đó đi sâu vào return types/nested `@AuthorizeReturnObject` để đăng ký proxy classes và expression-related hints.

Nhưng khi method có return type `List<ProfileView>` hoặc interface generic, Spring không phải lúc nào suy ra đầy đủ **runtime element type** trước khi native build. Với trường hợp này, cần cung cấp hints rõ ràng.

### 15.1. Đăng ký bổ sung types cho AOT

Ví dụ **fragment cấu hình Spring Security 6.5**:

~~~java
import org.springframework.beans.factory.config.BeanDefinition;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Role;
import org.springframework.security.aot.hint.AuthorizeReturnObjectHintsRegistrar;
import org.springframework.security.aot.hint.SecurityHintsRegistrar;
import org.springframework.security.authorization.method.AuthorizationProxyFactory;

@Bean
@Role(BeanDefinition.ROLE_INFRASTRUCTURE)
static SecurityHintsRegistrar registerReturnObjectTypes(
        AuthorizationProxyFactory proxyFactory) {
    return new AuthorizeReturnObjectHintsRegistrar(
        proxyFactory, ProfileView.class, ContactView.class
    );
}
~~~

**Lưu ý:** Đây là fragment đặt bên trong một `@Configuration`/`@SpringBootApplication` class; `ProfileView` và `ContactView` phải là class thật thuộc project. Nếu chúng là nested classes như ở ví dụ mục 10 nhưng fragment nằm ở class khác, hãy dùng `ReturnObjectApplication.ProfileView.class` và `ReturnObjectApplication.ContactView.class`.

API `AuthorizeReturnObjectHintsRegistrar` thuộc package **`org.springframework.security.aot.hint`**; nó có Javadoc `Since: 6.4`. Tài liệu API lưu ý nên **liệt kê đầy đủ mọi type cần proxy** mà scan mặc định bỏ lỡ; không mặc định một registrar tùy chỉnh sẽ duyệt hết mọi đồ thị runtime tùy ý.

### 15.2. Có cần AOT hints khi chỉ chạy JVM bình thường không?

Thường **không** cần thêm đăng ký này chỉ để chạy ứng dụng Spring Boot JVM theo bài mẫu. Chỉ thêm khi cấu hình AOT/native image, type bị erased hoặc đã thấy native proxy/hints thiếu trong build/test. **Không nên thêm hints một cách mù quáng** thay cho kiểm thử runtime.

### 15.3. Những thứ cần test với native image

- Object thực sự được proxy trên JVM và native.
- Nested getter `getContact()` tiếp tục có guard.
- Optional/List elements có được proxy đúng không.
- Custom SpEL beans / property getters có đủ reflection hints không.
- JSON serializer có hoạt động với proxied class không.
- Khi thiếu quyền, response có từ chối hoặc masking đúng như hợp đồng không.

Một bộ test JVM thành công **không chứng minh native image thành công**; native build cần kiểm tra riêng.

## 16. Programmatic proxy: `AuthorizationProxyFactory`

Ngoài `@AuthorizeReturnObject`, Spring Security 6.5 còn cung cấp `AuthorizationProxyFactory` để bọc object **bằng mã** khi ứng dụng có luồng không thuận tiện gắn annotation lên method trả về.

Ví dụ **fragment test**:

~~~java
@Autowired
AuthorizationProxyFactory proxyFactory;

@Test
@WithMockUser(authorities = "profile:read")
void directFactoryProxyChecksEmail() {
    ProfileView raw = new ProfileView(
        "P-1", "Lan", "lan@example.test",
        new ContactView("HCM", "0900000000")
    );

    ProfileView secured = proxyFactory.proxy(raw);
    assertThrows(AccessDeniedException.class, secured::getEmail);
}
~~~

Cần imports JUnit5, `@WithMockUser` và class `ProfileView/ContactView`. Đây là **fragment trong Spring test class** có bean factory và `@EnableMethodSecurity`, không phải bài test độc lập.

Có thể tạo factory bằng `AuthorizationAdvisorProxyFactory.withDefaults()` khi cần, hoặc cấu hình `TargetVisitor` tùy use case. Tuy nhiên, việc tạo factory thủ công có thể khác factory Spring đang sử dụng (advisors/role hierarchy/customization); với ứng dụng production, nên kiểm một nguồn cấu hình consistent.

**Lưu ý về security context:** nếu object proxy thoát khỏi request/thread ban đầu rồi được gọi từ background worker, `SecurityContext` lúc gọi có thể khác hoặc không có. Không giả định proxy “đóng băng authority tại thời điểm tạo”; cần hiểu thời điểm method interceptor lấy danh tính và bảo vệ task/async theo thiết kế.

## 17. Những sai lầm hay gặp

| Sai lầm | Hậu quả | Cách sửa |
| --- | --- | --- |
| Dùng `@AuthorizeReturnObject` trên Spring Security 6.2 | API chưa tồn tại như ví dụ | Xác minh dependency; dùng 6.3+ hoặc giải pháp khác |
| Gắn `@PreAuthorize` trên getter POJO nhưng object chưa proxy | Getter không được intercept | Dùng `@AuthorizeReturnObject` ở method nguồn/proxy factory |
| Chỉ gắn `@AuthorizeReturnObject` nhưng không có guard trên member | Chưa có chính sách cụ thể cần kiểm | Đặt `@PreAuthorize`/`@PostAuthorize` tại method nhạy cảm |
| Service method bị self-invocation | Có thể không bọc return object | Gọi qua Spring-managed proxy |
| Gắn annotation ở class-level indiscriminately | Cố proxy String/int/value types | Chỉ đánh dấu method cần thiết hoặc dùng `TargetVisitor` |
| Trả Java record/final class rồi trông chờ CGLIB | Không thể proxy kiểu subclass như POJO | Dùng loại proxy phù hợp hoặc non-final view |
| Quên `@AuthorizeReturnObject` trên getter lồng nhau | Nested object raw, getter bảo mật có thể bị bỏ qua | Đánh dấu nested getter và test 403 |
| Nghĩ `List<ProfileView>` sẽ tự lọc phần tử | List giữ các phần tử, chỉ getter có guard | Lọc theo query/`@PostFilter` khi thích hợp |
| Nghĩ Map keys được bảo vệ vì values được proxy | Có thể lộ key/metadata | Hạn chế dữ liệu ở tầng service |
| Trả raw proxy cho Jackson và mong auto-mask | Getter bị DENY gây 403/serialization error | Chọn DTO, handler hay explicit 403 |
| Dùng `@HandleAuthorizationDenied` thiếu review | Handler có thể làm rò giá trị nhạy cảm | Kiểm masking/return type và negative tests |
| Chỉ test user đủ quyền | Không phát hiện proxy bị bỏ qua | Test thiếu email/phone quyền phải bị DENY |
| Bỏ qua AOT/nested generic types | Native proxy/hints thiếu | Đăng ký `AuthorizeReturnObjectHintsRegistrar` theo version |
| Dùng JDK proxy/class proxy sai cấu trúc | Annotation không được áp dụng như kỳ vọng | Kiểm kiểu proxy, final/private, interface, tests |
| Trông chờ getter protection thay thế ACL/tenant | IDOR/BOLA còn tồn tại | Kiểm ownership, tenant, field scope sớm |
| Gọi proxy ở thread khác mà không có context | Quyền phụ thuộc context không đúng | Thiết kế SecurityContext propagation |
| Chỉ nhìn HTTP 403 mà không xác định chỗ chặn | Debug sai HTTP vs service vs getter | Đối chứng request và direct proxy test |

## 18. Câu hỏi tự kiểm tra

**Câu 1.** `@AuthorizeReturnObject` làm gì khác `@PostAuthorize`?  
**Đáp án:** Nó yêu cầu bọc object kết quả bằng proxy có authorization advice, thay vì tự ra quyết định cho phép/từ chối toàn kết quả dựa trên `returnObject`.

**Câu 2.** Có thể gắn `@PreAuthorize` trên `getEmail()` của POJO rồi mong người dùng tự `new` POJO luôn bị chặn không?  
**Đáp án:** Không. Getter phải được gọi qua proxy/interceptor phù hợp.

**Câu 3.** Spring Security bắt đầu có `@AuthorizeReturnObject` từ phiên bản nào?  
**Đáp án:** **6.3**, theo `Since: 6.3` trên JavaDoc chính thức.

**Câu 4.** `@AuthorizeReturnObject` trên service method có tự cấp `profile:email` không?  
**Đáp án:** Không. Quyền phải được kiểm ở getter bằng `@PreAuthorize`/policy thích hợp.

**Câu 5.** Vì sao thêm `@AuthorizeReturnObject` vào `getContact()`?  
**Đáp án:** Để object `ContactView` lồng nhau cũng được proxy và `getPhone()` nhận authorization advice.

**Câu 6.** Nếu user reader xem name được 200 nhưng email 403, điều đó chứng minh gì?  
**Đáp án:** `profile:read` đã qua, còn getter email bị rào bởi `profile:email`; không nhất thiết cả object bị từ chối.

**Câu 7.** Với `Optional<ProfileView>`, khi Optional empty có gọi `getEmail()` không?  
**Đáp án:** Không. Không có phần tử để gọi. Khi có phần tử, factory có thể bọc phần tử bằng proxy.

**Câu 8.** Nếu trả `List<ProfileView>`, `@AuthorizeReturnObject` có tự xóa profile không thuộc user không?  
**Đáp án:** Không. Nó proxy các phần tử; policy lọc list là chuyện riêng.

**Câu 9.** Vì sao không gắn `@AuthorizeReturnObject` class-level cho service trả nhiều String/Integer?  
**Đáp án:** Spring có thể cố proxy value types không thích hợp; nên chỉ gắn trên method cần thiết hoặc dùng `TargetVisitor`.

**Câu 10.** `@AuthorizeReturnObject` có tự tạo JSON với email=null khi thiếu quyền không?  
**Đáp án:** Không. Jackson gọi getter và có thể gặp exception; masking cần policy/handler hoặc DTO rõ ràng.

**Câu 11.** Khi chạy native image, vì sao `List<ProfileView>` có thể cần hints bổ sung?  
**Đáp án:** Generic erasure làm scan AOT không phải lúc nào xác định được kiểu phần tử cần proxy trước khi build.

**Câu 12.** AOT registrar tên gì và xuất hiện từ phiên bản nào?  
**Đáp án:** `AuthorizeReturnObjectHintsRegistrar` trong `org.springframework.security.aot.hint`, Javadoc `Since: 6.4`.

**Câu 13.** Nếu raw entity của ứng dụng bị log trước khi proxied getter deny, proxy có xóa log không?  
**Đáp án:** Không. Cần bảo vệ luồng dữ liệu/log/cache ở tầng domain và observability.

**Câu 14.** Làm sao chứng minh `getContact().getPhone()` thật sự được bảo vệ?  
**Đáp án:** Test trên Spring-managed `ProfileService` có `@AuthorizeReturnObject`, user thiếu `profile:phone` gọi nested getter phải ném `AccessDeniedException`.

**Câu 15.** Nếu thêm `@PreAuthorize` lên service method nhưng caller đi qua `this.method()`, kết quả luôn an toàn không?  
**Đáp án:** Không. Self-invocation trong proxy mode thông thường có thể bỏ qua cả pre-check và proxying return object.

**Câu 16.** Có nên dùng proxy member authorization thay cho tenant/owner checks đối với tài liệu nhạy cảm không?  
**Đáp án:** Không. Proxy member chỉ là một rào cản; phải giới hạn truy vấn, dữ liệu trả và kiểm quyền trên từng tài nguyên.

**Tóm tắt:** **`@AuthorizeReturnObject` bọc đối tượng trả về bằng authorization proxy**, cho phép các annotation như `@PreAuthorize` trên **getter/method của chính object đó** được kiểm tra khi caller sử dụng object. Từ Spring Security **6.3**, API này hữu ích với object, nested members, Optional và collections. Trên 6.5 hãy chú ý class/value types, serializer và AOT/native hints; luôn có **positive/negative tests** chứng minh cả base permission và từng field nhạy cảm.

## Tài liệu chính thức

- Spring Security 6.5 — Method Security, **Authorizing Arbitrary Objects**, Proxying Collections, AOT và denied results: https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/method-security.html
- Spring Security 6.5 — `AuthorizeReturnObject` API (`Since: 6.3`): https://docs.spring.io/spring-security/site/docs/6.5.6/api/org/springframework/security/authorization/method/AuthorizeReturnObject.html
- Spring Security 6.5 — `AuthorizeReturnObjectMethodInterceptor`: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/authorization/method/AuthorizeReturnObjectMethodInterceptor.html
- Spring Security 6.5 — `AuthorizationProxyFactory` API: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/authorization/method/AuthorizationProxyFactory.html
- Spring Security 6.5 — `AuthorizeReturnObjectHintsRegistrar` (`Since: 6.4`): https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/aot/hint/AuthorizeReturnObjectHintsRegistrar.html
- Spring Security 6.5 — `MethodAuthorizationDeniedHandler` và `@HandleAuthorizationDenied`: https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/method-security.html
- Spring Security 6.5 RC1 release notes — cải thiện tích hợp Spring MVC với `@AuthorizeReturnObject`: https://spring.io/blog/2025/04/21/spring-security-6-5-0-RC1-is-out/
