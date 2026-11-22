# Ma trận chủ thể – hành động – tài nguyên để mô tả yêu cầu quyền

> **Ngữ cảnh:** Mô hình kiểm soát truy cập (access control) trong ứng dụng Spring Security. Mục tiêu của bài là biểu diễn rõ **ai** (subject) được thực hiện **hành động nào** (action) trên **tài nguyên nào** (resource), diễn giải quyết định cho phép/từ chối, rồi chuyển mô hình đó thành kiểm tra quyền ở backend.

## 1. Một yêu cầu cấp quyền gồm những thành phần gì?

Để trả lời “người dùng này có được mở tài liệu đó không?”, chỉ biết người dùng đã đăng nhập là chưa đủ. Quyết định truy cập cần ít nhất một bộ ba:

**`(subject, action, resource)`** — hay viết ngắn là **`(S, A, R)`**.

| Thành phần | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| **Subject — S** | Chủ thể đang yêu cầu truy cập: người dùng, tài khoản dịch vụ hoặc vai trò đã được hệ thống xác định | `alice`, `bob`, tài khoản dịch vụ xuất báo cáo |
| **Action — A** | Thao tác nghiệp vụ muốn thực hiện trên tài nguyên | `READ`, `EDIT`, `DELETE`, `APPROVE` |
| **Resource — R** | Loại tài nguyên hoặc **một đối tượng cụ thể** cần bảo vệ | `document:101`, `invoice:987`, `tenant:acme` |
| **Context — C** (khi cần) | Ngữ cảnh ảnh hưởng đến quyết định: tenant, chủ sở hữu, trạng thái, hạn mức, thời gian... | `tenant=acme`, `status=DRAFT` |

Một quyết định chính sách có thể mô tả bằng:

`isAllowed(S, A, R, C) → true/false`.

Trong Java/Spring Security, subject thường xuất phát từ `Authentication` đã được xác minh; action đến từ thao tác nghiệp vụ; resource nên được xác định **từ dữ liệu đáng tin ở server** (ví dụ bản ghi theo ID), không tự tin vào trường `owner` hoặc `tenant` do client cung cấp.

**Điều cần phân biệt:**

- **Authentication** xác định danh tính chủ thể. **Authorization** quyết định bộ ba/quy tắc `(S,A,R)` có được phép hay không.
- Quyền `document:read` nói về **loại hành động**, chưa chắc đủ để đọc **mọi tài liệu**. Còn phải xét tài liệu đích, sở hữu hoặc tenant.
- HTTP method (`GET`, `POST`, `PATCH`...) giúp định tuyến và biểu đạt kiểu yêu cầu, nhưng action nghiệp vụ (`READ`, `EDIT`, `APPROVE`) phải được ánh xạ rõ theo semantics API. Không thể mặc định mọi `POST` đều cùng một quyền.

## 2. Access control matrix: hàng là subject, cột là resource

**Ma trận kiểm soát truy cập** (access control matrix) biểu diễn quyền theo hai chiều. Mỗi **hàng** là một chủ thể, mỗi **cột** là một tài nguyên; **ô giao** chứa tập action được phép trên tài nguyên đó.

Ký hiệu:

`M[S,R] = {A1, A2, ...}`

và:

`allow(S,A,R) ⇔ A ∈ M[S,R]`

Nếu tập ở ô là rỗng, tức không tìm thấy quyền tương ứng. Trong mô hình **default deny**, yêu cầu bị từ chối. Để diễn tả điều kiện động như tenant, ownership, trạng thái đối tượng, ma trận nên được hiểu là **hình ảnh quyền hiệu lực ở một thời điểm/ngữ cảnh nhất định**.

### Ví dụ: ba tài liệu thuộc hai tenant

Hệ thống có ba tài liệu:

- `doc-101`: thuộc tenant `acme`, do Alice sở hữu; Alice chia sẻ **READ** cho Bob.
- `doc-202`: thuộc tenant `acme`, do Bob sở hữu; Bob chia sẻ **READ** cho Alice.
- `doc-301`: thuộc tenant `orbit`, do Carol sở hữu.
- Maya là `MANAGER` của **tenant acme**. Chính sách ví dụ cho phép manager đọc/sửa tài liệu thuộc tenant của mình, nhưng **không vượt sang tenant khác**.

Các action là `READ` (xem nội dung) và `EDIT` (sửa nội dung). Giả định **owner** được cả READ/EDIT; chia sẻ chỉ cấp action đã được ghi; manager chỉ có quyền trong tenant của mình.

| Subject | `doc-101` (acme) | `doc-202` (acme) | `doc-301` (orbit) |
| --- | --- | --- | --- |
| **Alice — acme** | READ, EDIT | READ | ∅ |
| **Bob — acme** | READ | READ, EDIT | ∅ |
| **Carol — orbit** | ∅ | ∅ | READ, EDIT |
| **Maya — acme/MANAGER** | READ, EDIT | READ, EDIT | ∅ |

Đọc ba ô tiêu biểu:

1. `M[alice, doc-101] = {READ, EDIT}`: Alice là chủ sở hữu, nên `(alice, EDIT, doc-101)` được phép.
2. `M[alice, doc-202] = {READ}`: Alice được Bob chia sẻ quyền đọc; `(alice, EDIT, doc-202)` phải bị từ chối.
3. `M[maya, doc-301] = ∅`: Maya có vai trò quản lý **trong acme** nhưng `doc-301` thuộc `orbit`; request phải bị từ chối trước khi xét quyền manager.

**Đừng hiểu ký hiệu ∅ là tài nguyên không tồn tại.** Nó chỉ nói rằng subject này **không có action được cấp** trên resource đó theo chính sách đang xét. Resource có thể tồn tại, nhưng không được phép truy cập.

### Cách chuyển một request thành một ô ma trận

~~~text
Yêu cầu: Alice muốn EDIT doc-202
          |
          v
Xác thực request -> principal = alice
          |
          v
Chuẩn hóa action = EDIT
          |
          v
Nạp doc-202 từ kho dữ liệu đáng tin: tenant=acme, owner=bob
          |
          v
Kiểm tra tenant của Alice == tenant của tài liệu? Có
          |
          v
Tra quyền hiệu lực M[alice, doc-202] = {READ}
          |
          v
EDIT có thuộc {READ} không? Không
          |
          v
DENY (chặn ở backend)
~~~

Một ô được phép không có nghĩa mọi điều kiện khác đều tự động đúng. Ví dụ tài liệu có thể đã bị khóa hoặc Alice có thể bị đình chỉ. Khi đó `allow(S,A,R,C)` còn phụ thuộc ngữ cảnh `C`. **Trình tự đánh giá** và ưu tiên deny/allow phải là quyết định thiết kế rõ ràng.

## 3. Ba cách nhìn cùng một chính sách

**Dạng ma trận đầy đủ** tiện để học, rà soát và kiểm thử. Trong cơ sở dữ liệu thật, ma trận `users × resources` thường quá lớn, nhiều ô rỗng; các hệ thống thường lưu quyền dưới dạng **danh sách quan hệ thưa** hoặc chính sách suy diễn.

### 3.1. Ma trận dạng hàng–cột

Dạng bảng ở mục 2 dễ đọc bởi con người. Nó hỗ trợ câu hỏi “Ai có thể EDIT tài liệu X?” và “Alice được làm gì với tài liệu Y?”.

### 3.2. Danh sách cấp quyền: bộ ba (subject, action, resource)

Một phần các quyền **tường minh** có thể lưu như:

| subject | action | resource |
| --- | --- | --- |
| `bob` | `READ` | `doc-101` |
| `alice` | `READ` | `doc-202` |

Đây là các quyền **chia sẻ**. Quyền của owner và manager trong ví dụ được **suy diễn bằng quy tắc**, nên không cần tạo sẵn mọi bộ ba cho mọi tài liệu. Một bảng tương tự trong database có thể có các cột `subject_id, action, resource_type, resource_id`, kèm thông tin tenant, người cấp quyền và thời điểm hết hiệu lực nếu nghiệp vụ yêu cầu.

### 3.3. ACL gắn với resource

**Access Control List (ACL)** đặt danh sách chủ thể/quyền lên tài nguyên:

~~~text
doc-101:
  owner: alice
  tenant: acme
  acl:
    - subject: bob
      actions: [READ]

doc-202:
  owner: bob
  tenant: acme
  acl:
    - subject: alice
      actions: [READ]
~~~

ACL trả lời thuận tiện “Ai được truy cập tài liệu này?”. Dạng quyền được tổ chức theo subject trả lời thuận tiện “Tài khoản này có thể truy cập những tài liệu nào?”. Cả hai đều có thể là biểu diễn của chính sách tương đương; **đừng nhầm cách lưu trữ với quy tắc bảo mật**.

> Thuật ngữ *capability* có nghĩa chặt chẽ hơn một danh sách quyền theo user: nó thường là một tham chiếu/token quyền không thể giả mạo, cấp khả năng thao tác tài nguyên. Chỉ có danh sách `user → resource → action` chưa đủ để gọi đó là hệ thống bảo mật dựa trên capability.

## 4. Mở rộng bộ ba để mô tả chính sách thực tế

Với nhiều nghiệp vụ, nên đặt tên permission dựa trên **resource type + action**, rồi thêm điều kiện cho resource instance:

| Request | Action nghiệp vụ | Resource | Điều kiện bổ sung |
| --- | --- | --- | --- |
| `GET /api/docs/101` | READ | Document 101 | Owner, được chia sẻ hoặc quản lý đúng tenant |
| `PATCH /api/docs/101` | EDIT | Document 101 | Quyền EDIT, tài liệu chưa khóa |
| `POST /api/invoices/987/approve` | APPROVE | Invoice 987 | Có quyền duyệt, đúng đơn vị, chưa tự tạo hóa đơn |
| `DELETE /api/users/58` | DELETE | User 58 | Quản trị đúng phạm vi, không vi phạm ràng buộc tài khoản |
| `GET /api/projects/74/members` | LIST_MEMBERS | Project 74 | Có tư cách thành viên hoặc quyền quản lý dự án |

Một quyết định có thể viết theo hướng *policy predicate*:

`allow(s, a, r, c) = authenticated(s) ∧ sameTenant(s,r) ∧ hasEffectiveAction(s,a,r) ∧ contextSatisfied(a,r,c)`.

Dấu `∧` nghĩa là **đồng thời thỏa mãn**; chỉ một điều kiện sai phải trả về deny. Trong ứng dụng thật, các hàm có thể khác theo action và resource type. Ví dụ quyền công khai `READ_PUBLIC` có thể không cần đăng nhập, nhưng phải được quy định tường minh thay vì vô tình bỏ chặn.

### So sánh với RBAC và ABAC

- **Ma trận truy cập** là cách **mô tả/quy chiếu quyền**: với subject này và resource này, action nào được phép?
- **RBAC** là cách **gán quyền qua role**: user → role → permission. Có thể tính quyền hiệu lực của từng user rồi điền vào ma trận.
- **ABAC** đưa thuộc tính vào điều kiện: phòng ban của user, tenant của resource, phân loại dữ liệu, thời điểm, trạng thái... Ma trận có thể là **ảnh chụp kết quả** sau khi đánh giá các thuộc tính tại một thời điểm.
- **Owner/ACL** là các cơ chế cấp quyền trên từng resource instance; có thể kết hợp RBAC và ABAC.

Ví dụ: role `DOC_EDITOR` có quyền `document:edit` là điều kiện **cần**, còn tài liệu thuộc tenant nào hoặc người dùng được cấp quyền với instance nào là điều kiện **bổ sung**. **Không** nên kết luận `hasAuthority("document:edit")` đồng nghĩa sửa được mọi tài liệu trong hệ thống.

## 5. Java 17 thuần: tính ma trận quyền hiệu lực từ chính sách

Đoạn sau là **chương trình hoàn chỉnh, độc lập**, biên dịch/chạy bằng JDK 17+ mà không cần thư viện bên ngoài. Dữ liệu mẫu được khai báo trong bộ nhớ. Chương trình không lưu mọi ô ma trận; nó tính từ **tenant + role MANAGER + owner + ACL chia sẻ**.

Tạo tệp tên **`AccessMatrixDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.Set;

public class AccessMatrixDemo {

    enum Action {
        READ, EDIT
    }

    record Subject(String username, String tenant, Set<String> roles) {}

    record Document(
        String id,
        String tenant,
        String owner,
        Map<String, Set<Action>> grants
    ) {}

    static boolean allowed(Subject subject, Action action, Document document) {
        if (subject == null || action == null || document == null) {
            return false;
        }

        // Ranh giới tenant là bắt buộc, kể cả với MANAGER.
        if (!subject.tenant().equals(document.tenant())) {
            return false;
        }

        // Quy tắc nghiệp vụ của ví dụ: MANAGER có READ/EDIT trong tenant.
        if (subject.roles().contains("MANAGER")) {
            return true;
        }

        // Owner có READ/EDIT trên tài liệu của chính mình.
        if (subject.username().equals(document.owner())) {
            return true;
        }

        // Các chủ thể khác chỉ có action được ghi trong ACL.
        return document.grants()
            .getOrDefault(subject.username(), Set.of())
            .contains(action);
    }

    static String rights(Subject subject, Document document) {
        List<String> result = new ArrayList<>();
        for (Action action : Action.values()) {
            if (allowed(subject, action, document)) {
                result.add(action.name());
            }
        }
        return result.isEmpty() ? "-" : String.join(",", result);
    }

    public static void main(String[] args) {
        Subject alice = new Subject("alice", "acme", Set.of("MEMBER"));
        Subject bob = new Subject("bob", "acme", Set.of("MEMBER"));
        Subject carol = new Subject("carol", "orbit", Set.of("MEMBER"));
        Subject maya = new Subject("maya", "acme", Set.of("MANAGER"));

        Document doc101 = new Document(
            "doc-101", "acme", "alice",
            Map.of("bob", Set.of(Action.READ))
        );
        Document doc202 = new Document(
            "doc-202", "acme", "bob",
            Map.of("alice", Set.of(Action.READ))
        );
        Document doc301 = new Document(
            "doc-301", "orbit", "carol", Map.of()
        );

        List<Subject> subjects = List.of(alice, bob, carol, maya);
        List<Document> documents = List.of(doc101, doc202, doc301);

        System.out.println("subject | doc-101 | doc-202 | doc-301");
        for (Subject subject : subjects) {
            List<String> cells = new ArrayList<>();
            for (Document document : documents) {
                cells.add(rights(subject, document));
            }
            System.out.println(
                subject.username() + " | " + String.join(" | ", cells)
            );
        }

        System.out.println(
            "alice EDIT doc-202: " + allowed(alice, Action.EDIT, doc202)
        );
        System.out.println(
            "maya READ doc-301: " + allowed(maya, Action.READ, doc301)
        );
    }
}
~~~

Biên dịch và chạy từ thư mục chứa tệp:

~~~bash
javac AccessMatrixDemo.java
java AccessMatrixDemo
~~~

**Stdout chính xác:**

~~~text
subject | doc-101 | doc-202 | doc-301
alice | READ,EDIT | READ | -
bob | READ | READ,EDIT | -
carol | - | - | READ,EDIT
maya | READ,EDIT | READ,EDIT | -
alice EDIT doc-202: false
maya READ doc-301: false
~~~

### Đọc chương trình theo từng lớp chính sách

1. **`Subject`** mang username, tenant và role. Chương trình mẫu tự cung cấp dữ liệu đã biết; trong ứng dụng thật, những thuộc tính này phải được xác minh/nạp từ nguồn tin cậy.
2. **`Document`** mang ID, tenant, owner và `grants` cho người được chia sẻ.
3. **`allowed(...)`** từ chối đầu vào null và từ chối khác tenant **trước** quyền manager hoặc owner; tránh manager tenant A mở tài liệu tenant B.
4. Sau ranh giới tenant, chương trình xét role manager, owner, rồi ACL. Đây là **chính sách giả định được định nghĩa rõ cho ví dụ**, không phải quy tắc tự có của Spring Security.
5. **`rights(...)`** thử lần lượt `READ` và `EDIT`; tập action được phép tạo ra mỗi ô của ma trận.
6. Hai dòng cuối xác nhận các trường hợp **deny**: Alice được đọc tài liệu của Bob nhưng không được sửa; Maya không được đọc tài liệu tenant khác.

**Lưu ý bảo mật:** thứ tự các nhánh ở đây phù hợp chính sách đơn giản “tenant boundary bắt buộc; sau đó manager/owner/ACL là các nguồn cấp ALLOW”. Nếu sản phẩm có **explicit deny**, tài liệu bị khóa, user bị đình chỉ hoặc mâu thuẫn policy, cần định nghĩa ưu tiên và thêm các điều kiện trước khi trả `true`. Không mặc định “allow luôn thắng deny” hay ngược lại khi chưa có contract.

## 6. Đưa ma trận vào Spring Security: từ principal đến method security

Phần Java ở trên giải thích policy không phụ thuộc framework. Trong Spring Security, cách triển khai điển hình là:

1. Authentication xác minh credential/token và tạo `Authentication`.
2. HTTP security kiểm soát tuyến công khai và yêu cầu đăng nhập cho vùng API.
3. **Method security** nhận `Authentication` và ID tài nguyên, gọi **policy service** để đưa ra quyết định `allowed(subject,action,resource)`.
4. Controller chỉ trả dữ liệu khi method-level authorization cho phép.
5. Những nơi khác gọi nghiệp vụ nên đi qua **cùng service/policy**, tránh trùng chính sách hoặc tin frontend đã kiểm tra.

### Ví dụ Spring Boot Java 17+ đầy đủ

Tạo dự án Maven bằng Spring Initializr với **Java 17+**, dependency **Spring Web** và **Spring Security**. Tạo tệp **`src/main/java/com/example/matrix/MatrixApplication.java`** có nội dung sau. Mã dùng tài khoản/demo data cố định để diễn giải, **không dùng credential hardcode như cấu hình production**.

~~~java
package com.example.matrix;

import java.util.Map;
import java.util.Set;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.http.HttpMethod;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.stereotype.Component;
import org.springframework.stereotype.Service;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
@EnableMethodSecurity
public class MatrixApplication {

    public static void main(String[] args) {
        SpringApplication.run(MatrixApplication.class, args);
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        http.authorizeHttpRequests(auth -> auth
            .requestMatchers(HttpMethod.GET, "/public/ping").permitAll()
            .requestMatchers("/api/docs/**").authenticated()
            .anyRequest().denyAll()
        ).httpBasic(Customizer.withDefaults());
        return http.build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        return new InMemoryUserDetailsManager(
            user("alice", "demo123", "MEMBER", encoder),
            user("bob", "demo456", "MEMBER", encoder),
            user("carol", "demo789", "MEMBER", encoder),
            user("maya", "demo999", "MANAGER", encoder)
        );
    }

    private static UserDetails user(
        String name, String rawPassword, String role, PasswordEncoder encoder
    ) {
        return User.withUsername(name)
            .password(encoder.encode(rawPassword))
            .roles(role)
            .build();
    }

    @RestController
    public static class DocumentController {
        private final DocumentService service;

        public DocumentController(DocumentService service) {
            this.service = service;
        }

        @GetMapping("/public/ping")
        public String ping() {
            return "pong";
        }

        @GetMapping("/api/docs/{id}")
        public String read(@PathVariable("id") long id) {
            return service.read(id);
        }

        // Chỉ xem trước quyền EDIT; GET này không sửa dữ liệu.
        @GetMapping("/api/docs/{id}/edit-preview")
        public String editPreview(@PathVariable("id") long id) {
            return service.editPreview(id);
        }
    }

    @Service
    public static class DocumentService {

        @PreAuthorize("@documentPolicy.allowed(authentication, #p0, 'READ')")
        public String read(long id) {
            return "document " + id;
        }

        @PreAuthorize("@documentPolicy.allowed(authentication, #p0, 'EDIT')")
        public String editPreview(long id) {
            return "edit preview " + id;
        }
    }

    @Component("documentPolicy")
    public static class DocumentPolicy {

        private record Doc(
            long id, String tenant, String owner, Set<String> readers
        ) {}

        private final Map<Long, Doc> documents = Map.of(
            101L, new Doc(101L, "acme", "alice", Set.of("bob")),
            202L, new Doc(202L, "acme", "bob", Set.of("alice")),
            301L, new Doc(301L, "orbit", "carol", Set.of())
        );

        // Demo: tenant được ánh xạ ở server, không nhận từ client.
        private final Map<String, String> userTenants = Map.of(
            "alice", "acme",
            "bob", "acme",
            "carol", "orbit",
            "maya", "acme"
        );

        public boolean allowed(
            Authentication authentication, long id, String action
        ) {
            if (authentication == null || !authentication.isAuthenticated()) {
                return false;
            }

            Doc doc = documents.get(id);
            if (doc == null) {
                return false;
            }

            String username = authentication.getName();
            String tenant = userTenants.get(username);
            if (!doc.tenant().equals(tenant)) {
                return false;
            }

            if (!"READ".equals(action) && !"EDIT".equals(action)) {
                return false;
            }

            boolean manager = authentication.getAuthorities().stream()
                .anyMatch(a -> "ROLE_MANAGER".equals(a.getAuthority()));

            if (manager || username.equals(doc.owner())) {
                return true;
            }

            return "READ".equals(action) && doc.readers().contains(username);
        }
    }
}
~~~

**Giải thích cơ chế Spring Security:**

- `@EnableMethodSecurity` cho phép dùng `@PreAuthorize`; Spring Security starter **không tự bật** method security chỉ vì được khai báo làm dependency.
- `authentication` trong biểu thức lấy chủ thể hiện tại từ security context; `#p0` là tham số thứ nhất của method (ID tài liệu). Policy được gọi **trước khi** nội dung method chạy.
- `@documentPolicy` tham chiếu bean Spring mang tên `documentPolicy`. Đặt chính sách ở một component độc lập giúp tái sử dụng và kiểm thử tập trung.
- `DocumentController` gọi `DocumentService` qua **Spring-managed bean**, để method security proxy áp dụng. Tránh tự gọi phương thức gắn `@PreAuthorize` qua `this` trong cùng bean khi dùng cơ chế proxy thông thường.
- Route `/api/docs/**` chỉ yêu cầu `authenticated()`. Quyết định **được đọc/sửa tài liệu cụ thể nào** thuộc về `DocumentPolicy`; `authenticated()` một mình không đủ.
- Với user Maya, `ROLE_MANAGER` chỉ được xét **sau khi** kiểm tra tenant; người quản lý `acme` không vượt vào `orbit`.
- Ví dụ dùng `GET /edit-preview` vì nó **không thay đổi trạng thái**. Khi triển khai thao tác EDIT thật, sử dụng method HTTP phù hợp (`PATCH`/`PUT`/`POST`) và xử lý CSRF đúng với cơ chế xác thực; không dùng GET để sửa dữ liệu.

Chạy ứng dụng tại thư mục dự án:

~~~bash
# macOS / Linux
./mvnw spring-boot:run

# Windows PowerShell hoặc Command Prompt
mvnw.cmd spring-boot:run
~~~

Thử với `curl` khi server đang chạy ở cổng mặc định 8080:

~~~bash
curl -i http://localhost:8080/public/ping
curl -i http://localhost:8080/api/docs/101
curl -i -u alice:demo123 http://localhost:8080/api/docs/101
curl -i -u alice:demo123 http://localhost:8080/api/docs/202
curl -i -u alice:demo123 http://localhost:8080/api/docs/202/edit-preview
curl -i -u bob:demo456 http://localhost:8080/api/docs/202/edit-preview
curl -i -u maya:demo999 http://localhost:8080/api/docs/101/edit-preview
curl -i -u maya:demo999 http://localhost:8080/api/docs/301
~~~

| Request | HTTP kỳ vọng | Lý do |
| --- | --- | --- |
| `GET /public/ping` (anonymous) | `200`, body `pong` | Tuyến công khai |
| `GET /api/docs/101` (anonymous) | `401` | Chưa xác thực; HTTP Basic yêu cầu credential |
| `GET /api/docs/101` (Alice) | `200`, body `document 101` | Alice sở hữu |
| `GET /api/docs/202` (Alice) | `200`, body `document 202` | Bob chia sẻ READ |
| `GET /api/docs/202/edit-preview` (Alice) | `403` | Alice không có EDIT |
| `GET /api/docs/202/edit-preview` (Bob) | `200`, body `edit preview 202` | Bob sở hữu |
| `GET /api/docs/101/edit-preview` (Maya) | `200`, body `edit preview 101` | Manager trong cùng tenant |
| `GET /api/docs/301` (Maya) | `403` | Khác tenant; quyền manager không vượt phạm vi |

Các status trên áp dụng cho **HTTP Basic và method security** của ví dụ. Với form login, request chưa xác thực có thể được redirect đến màn hình đăng nhập. Với ID không tồn tại, policy hiện trả `false` nên request đã xác thực nhận từ chối; một ứng dụng thật có thể chủ động thiết kế 404 để tránh tiết lộ tài nguyên tồn tại hay không. Chính sách trả 403 hoặc 404 cần nhất quán và tránh rò rỉ thông tin qua chi tiết lỗi.

## 7. Từ ma trận thủ công đến schema dữ liệu và kiểm tra

Khi số lượng tài nguyên lớn, không nên lưu bảng `users × documents` đầy đủ. Có thể lưu **các quyền cấp tường minh** dạng hàng:

~~~sql
-- PostgreSQL, minh họa cấu trúc quyền theo tài nguyên:
CREATE TABLE document_grants (
    tenant_id VARCHAR(100) NOT NULL,
    document_id BIGINT NOT NULL,
    subject_id BIGINT NOT NULL,
    action VARCHAR(30) NOT NULL,
    granted_by BIGINT NOT NULL,
    PRIMARY KEY (tenant_id, document_id, subject_id, action)
);
~~~

Bảng này là **schema minh họa**, chưa bao gồm bảng tài liệu/tài khoản và các foreign key tương ứng. Trong mô hình thực tế, cần khóa ngoại phù hợp, index cho đường truy vấn, ràng buộc action hợp lệ và mô hình thu hồi/hết hạn. Các quyền owner/manager có thể được **tính từ chính sách** thay vì nhân bản vào `document_grants`.

Đọc quyền của chủ thể cho một tài liệu cụ thể (dùng bind parameter trong code):

~~~sql
SELECT action
FROM document_grants
WHERE tenant_id = :tenant_id
  AND document_id = :document_id
  AND subject_id = :subject_id;
~~~

`:tenant_id`, `:document_id` và `:subject_id` là placeholder của tầng truy cập dữ liệu, không phải cú pháp PostgreSQL độc lập để nhập nguyên xi vào `psql`.

**Vấn đề quan trọng:** query ACL chỉ là **một nguồn cấp quyền**. Kết quả deny/allow cuối còn có thể phụ thuộc tenant, owner, role, trạng thái tài liệu. Nên diễn giải trong **policy service dùng chung**, chứ không viết ba biến thể logic ở controller, repository và frontend.

### Authorization trước khi trả dữ liệu

Ở tầng service nên tuân theo thứ tự:

1. Xác định principal từ `Authentication` đã xác thực.
2. Phân tích action theo thao tác đang thực hiện (không lấy tùy ý một chuỗi action từ client rồi cho phép client tự chọn).
3. Nạp resource và tenant/owner/state từ database bằng truy vấn có ràng buộc phù hợp.
4. Đánh giá chính sách quyền với các thuộc tính **đã xác minh**.
5. Chỉ khi ALLOW mới trả dữ liệu hoặc thực hiện thay đổi.

Đối với **LIST/SEARCH** như `GET /api/docs`, không chỉ kiểm tra một document ID. Cần **lọc ngay trong query** theo tenant, owner/chia sẻ/role và các điều kiện truy cập; lấy toàn bộ tài liệu rồi lọc bằng Java có thể rò rỉ dữ liệu qua phân trang, tổng số bản ghi hoặc hiệu năng.

### Tránh kiểm tra trước rồi dùng dữ liệu khác

Trong hoạt động ghi, tình trạng tài liệu hoặc quyền có thể thay đổi giữa lúc kiểm tra và cập nhật (**time-of-check/time-of-use**). Với nghiệp vụ nhạy cảm, bảo đảm phần kiểm tra và tác vụ sử dụng cùng snapshot/transaction phù hợp, hoặc đưa điều kiện quyền/trạng thái vào query ghi có kiểm tra số bản ghi cập nhật. Không mặc định một `@PreAuthorize` luôn đủ khi tài nguyên có thể đổi owner/trạng thái đồng thời.

## 8. Kiểm thử ma trận và các trường hợp phủ định

Một test suite tốt phải lấy ma trận làm **đặc tả hành vi**, không chỉ thử các request “đúng quyền”.

Với 4 subjects × 3 resources × 2 actions trong ví dụ, có **24 bộ ba** cần xem xét. Không nhất thiết viết 24 phương thức test giống nhau: có thể dùng **parameterized tests** hoặc vòng lặp tạo `(subject, action, resource, expectedAllow)`, rồi đối chiếu kết quả chính sách. Tối thiểu cần kiểm tra:

| Trường hợp | Kỳ vọng |
| --- | --- |
| Owner đọc/sửa tài liệu cùng tenant | ALLOW |
| Người được chia sẻ READ đọc tài liệu | ALLOW |
| Người chỉ có READ cố EDIT | DENY |
| Người không được chia sẻ cố READ | DENY |
| MANAGER truy cập tài liệu trong tenant được quản lý | ALLOW theo chính sách ví dụ |
| MANAGER truy cập tài liệu tenant khác | DENY |
| ID tài liệu không tồn tại | DENY hoặc 404 theo hợp đồng API |
| Action không được mô hình hỗ trợ | DENY |
| Request thiếu Authentication cho API bảo vệ | 401/redirect theo cơ chế đăng nhập |
| Client tự đổi `tenantId` hoặc `ownerId` để giả quyền | DENY vì server không tin các trường đó |

Khi thêm quyền hoặc đổi role, cập nhật **ma trận mong đợi** rồi chạy test. Với resource nhiều trạng thái, nên bổ sung các trường hợp: khóa tài liệu, tài khoản bị vô hiệu hóa, hết hạn chia sẻ, token chứa quyền cũ, thay đổi tenant, và nhiều request đồng thời.

## 9. Các nhầm lẫn thường gặp

1. **“User có role EDITOR nên sửa được mọi tài liệu.”** Không nhất thiết: role có thể cấp quyền loại `document:edit`, còn resource instance phải đúng phạm vi tenant/ownership/ACL.
2. **“Đủ username và action là có thể quyết định quyền.”** Thiếu resource instance; Alice được sửa `doc-101` nhưng không được sửa `doc-202`.
3. **“URI là tài nguyên duy nhất cần xét.”** `/api/docs/{id}` có thể trỏ đến nhiều đối tượng khác nhau, với owner/tenant/trạng thái khác nhau.
4. **“Nếu không thấy dòng DENY, cứ ALLOW.”** Sai với chính sách **default deny**: thiếu grant hợp lệ phải bị từ chối.
5. **“Đã chặn ở frontend thì an toàn.”** Frontend ẩn nút không ngăn client gọi API; backend phải thực thi policy.
6. **“MANAGER ở tenant A là MANAGER toàn hệ thống.”** Sai nếu role có scope; phải kiểm tra tenant tại thời điểm quyết định.
7. **“Danh sách action được client gửi lên là đáng tin.”** Client có thể tự gửi `EDIT`; server phải biết endpoint đang thực hiện hành động nghiệp vụ nào và tự kiểm tra permission.
8. **“Mỗi ô ma trận phải tồn tại như một bản ghi.”** Không cần: nhiều quyền hiệu lực được suy diễn từ role, owner, nhóm, ACL hoặc thuộc tính.
9. **“Bảo vệ một ID là đủ cho API danh sách.”** Với LIST/SEARCH, chính query phải tuân thủ phạm vi dữ liệu; phân trang/tổng số có thể tiết lộ bản ghi bị cấm.
10. **“Một lần kiểm tra quyền tồn tại mãi.”** Role, owner, tenant, trạng thái và chia sẻ có thể đổi; session/token/cache và giao dịch phải có chính sách làm mới và thu hồi thích hợp.

## 10. Bài tập tự kiểm tra

Sử dụng ma trận ở mục 2:

1. `(alice, READ, doc-202)` → **ALLOW** vì Bob chia sẻ quyền đọc.
2. `(alice, EDIT, doc-202)` → **DENY** vì Alice không sở hữu và chỉ có READ.
3. `(bob, EDIT, doc-202)` → **ALLOW** vì Bob là chủ sở hữu.
4. `(carol, READ, doc-101)` → **DENY** vì khác tenant.
5. `(maya, EDIT, doc-101)` → **ALLOW** theo chính sách MANAGER trong tenant acme.
6. `(maya, READ, doc-301)` → **DENY** vì tenant orbit khác acme.
7. Nếu Bob chia sẻ thêm EDIT trên `doc-101`, ô nào đổi? **`M[bob, doc-101]`** từ `{READ}` thành `{READ,EDIT}`; các ô khác không tự đổi.
8. Nếu `doc-202` chuyển sang trạng thái khóa, kết quả EDIT có thể đổi không? **Có** nếu chính sách thêm điều kiện `status != LOCKED`; ma trận trước đó là ảnh chụp quyền hiệu lực chưa bao gồm thay đổi trạng thái.

**Ghi nhớ:** Một yêu cầu cấp quyền là **“chủ thể nào – muốn làm gì – trên tài nguyên nào – trong ngữ cảnh nào”**. Access control matrix giúp mô tả và kiểm thử tập quyền theo bộ ba `(S,A,R)`; Spring Security giúp thực thi bằng authentication, request authorization và method/domain policy. Chính sách phải **từ chối mặc định**, dựa trên dữ liệu server đáng tin và kiểm tra đúng resource instance.

## Tài liệu chính thức

- Spring Security — Authorization Architecture: https://docs.spring.io/spring-security/reference/servlet/authorization/architecture.html
- Spring Security — Authorize HTTP Requests: https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html
- Spring Security — Method Security: https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html
- Spring Security — Expression-Based Access Control: https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html#use-authorization-custom-bean
