# Không suy diễn quyền chỉ từ tên phương thức hoặc kiểu tham số trong AOP

## 1. Vấn đề bảo mật cần giải quyết

**Aspect-Oriented Programming (AOP)** thường được sử dụng để đặt kiểm soát truy cập tại những điểm thực thi dùng chung. Một *pointcut* xác định các *join point* cần can thiệp; *advice* kiểm tra quyền trước khi cho thao tác gốc chạy. Cách làm này hữu ích khi nhiều phương thức cùng cần một cơ chế xác thực và phân quyền nhất quán.

Tuy nhiên, có một sai lầm nguy hiểm: **coi tên phương thức hoặc kiểu tham số là bằng chứng người gọi có quyền thực hiện thao tác**. Những chuỗi tên như `getUser`, `readPublic`, `adminUpdate`, `deleteById` và những kiểu như `AdminRequest`, `UserId`, `DocumentDto` chỉ mô tả cấu trúc phần mềm. Chúng không chứng minh danh tính đã được xác thực, vai trò hợp lệ, quyền trên tài nguyên đích hay điều kiện sử dụng quyền tại thời điểm thực thi.

Ví dụ, hai lời gọi cùng có dạng `readDocument(String documentId)` có thể truy cập hai tài liệu thuộc các chủ sở hữu hoặc tenant khác nhau. Trong cùng một phương thức, tài liệu A có thể được phép xem còn tài liệu B phải bị từ chối. Ngược lại, một phương thức tên `getSecret` có thể trả dữ liệu được phép truy cập đối với một chủ thể đã được cấp quyền. Quyết định phụ thuộc **người thực hiện – hành động – đối tượng – ngữ cảnh**, không phụ thuộc vẻ ngoài của tên hàm.

Nguyên tắc chính:

> **Tên/kiểu là thông tin để xác định điểm cần bảo vệ hoặc cách trích xuất dữ liệu theo một hợp đồng đã kiểm chứng; chúng không tự trở thành nguồn cấp quyền.**

Trong bài này, “suy diễn quyền” nghĩa là lấy một tín hiệu cấu trúc không đáng tin về mặt quyền hạn rồi kết luận `allow` / `deny`. Dùng tên phương thức để **định vị một chính sách khai báo rõ** là hợp lệ; dùng quy tắc kiểu “method bắt đầu bằng `get` thì ai cũng được gọi” để **quyết định được phép hay không** là không an toàn.

## 2. Cấu trúc một quyết định phân quyền đúng

Một quyết định kiểm soát truy cập thường cần tối thiểu bốn yếu tố:

| Yếu tố | Câu hỏi | Ví dụ |
| --- | --- | --- |
| **Subject / principal** | Ai đang yêu cầu? Danh tính có được xác thực không? | Người dùng `alice` thuộc `tenant-1` |
| **Action / permission** | Người đó muốn làm thao tác gì? | `document.read`, `document.publish` |
| **Resource / object** | Thao tác tác động tới đối tượng cụ thể nào? | Tài liệu `doc-7` do `alice` sở hữu |
| **Context / environment** | Điều kiện gì phải đúng tại thời điểm kiểm tra? | Tenant trùng khớp, xác thực tăng cường, trạng thái tài liệu, thời hạn quyền |

Có thể biểu diễn chính sách:

`allow = policy(principal, action, resource, context)`

Các đầu vào phải có nguồn gốc đáng tin phù hợp:

- **Principal** đến từ ranh giới xác thực được tin cậy; tên người dùng, vai trò, tenant hoặc cờ xác thực tăng cường do client tự truyền lên không phải bằng chứng.
- **Action** được ánh xạ tường minh từ operation được bảo vệ sang quyền nghiệp vụ; không đoán từ prefix/suffix của tên phương thức.
- **Resource** phải được định danh theo hợp đồng API, rồi lấy thuộc tính quyền hạn từ nguồn dữ liệu có thẩm quyền. `String documentId` chỉ là khóa tra cứu, không thể hiện người gọi có quyền.
- **Context** gồm điều kiện phiên, chính sách tổ chức, thời gian, trạng thái, phạm vi tenant hay bằng chứng xác thực tăng cường; phải được bảo vệ khỏi giả mạo và cập nhật theo cơ chế phù hợp.

Một quy tắc cho phép có thể là:

`canPublish = authenticated && sameTenant && isOwner && strongAuthenticationVerified`

Hệ thống cũng cần quy định điều gì xảy ra khi thuộc tính không có, policy chưa được khai báo, backend phân quyền lỗi hoặc người gọi không có danh tính. Mặc định an toàn là **deny by default / fail closed** tại ranh giới có yêu cầu quyền. Lỗi trong quá trình lấy dữ liệu chính sách không được tự chuyển thành cho phép.

### Xác thực, phân quyền và xác nhận dữ liệu không phải một việc

- **Authentication:** xác định và kiểm chứng danh tính người gọi.
- **Authorization:** quyết định danh tính đó có thể thực hiện *hành động cụ thể trên tài nguyên cụ thể* hay không.
- **Validation:** dữ liệu đầu vào có đúng định dạng/phạm vi hay không, ví dụ ID không rỗng, số tiền dương, payload hợp lệ.

Một tham số có kiểu `AdminRequest` có thể vượt qua validation mà vẫn không được authorization. Ngược lại, role `ADMIN` trong một token cũng cần được xác minh chữ ký, issuer, audience, hiệu lực, phạm vi và điều kiện sử dụng theo hệ thống xác thực; nhìn thấy chuỗi `ADMIN` không đủ để tin.

## 3. Những suy diễn sai rất thường gặp

### 3.1 Đoán quyền theo tên phương thức

Ví dụ minh họa **phản ví dụ không an toàn**:

~~~java
// KHÔNG AN TOÀN: chỉ để minh họa sai lầm về chính sách.
boolean canInvokeByName(String methodName) {
    return methodName.startsWith("get")
        || methodName.startsWith("list")
        || methodName.contains("Public");
}
~~~

Một phương thức tên `getPayroll` hoặc `listCredentials` có thể truy cập dữ liệu nhạy cảm; tên bắt đầu bằng `get` không làm nó công khai. Một phương thức tên `deleteExpiredCache` có thể là công việc nền hợp lệ không cần quyền người dùng ở tầng áp dụng; tên bắt đầu bằng `delete` cũng chưa đủ để xác định quy tắc chính xác. Đổi tên phương thức hoặc tạo alias có thể vô tình thay đổi kết quả bảo mật nếu policy được suy từ tên.

Không giải quyết được vấn đề bằng cách viết thêm hàng trăm regex trên tên: cùng tên có overload, tên có thể thay đổi khi refactor, wrapper/decorator có thể dùng tên khác, và resource-level authorization vẫn vắng mặt.

### 3.2 Đoán quyền theo kiểu tham số

Ví dụ **phản ví dụ không an toàn**:

~~~java
// KHÔNG AN TOÀN: Class<?> không nói ai được cấp quyền.
boolean isPrivilegedByParameterType(Class<?> type) {
    return type.getSimpleName().equals("AdminRequest")
        || type.getSimpleName().endsWith("TrustedInput");
}
~~~

Một caller có thể tạo một `AdminRequest` từ JSON hoặc gọi trực tiếp constructor nếu lớp đó không bị kiểm soát; lớp dữ liệu mang tên quyền lực không trở thành chứng cứ người gọi đã được cấp đặc quyền. `String`, `UUID`, `long`, `DocumentDto` có thể chứa ID tài nguyên thuộc bất kỳ ai. Kiểu generic tại runtime còn có thể bị xóa thông tin tham số (`type erasure`), nên suy quyền từ thông tin reflection không đầy đủ càng thiếu cơ sở.

Tương tự, tên tham số `ownerId` không chứng minh ID đó là chủ thể đã xác thực; nhận `userId` từ request rồi so với một field khác có thể mở lỗ hổng giả mạo danh tính. Chỉ lấy tài nguyên, chủ sở hữu và tenant từ nguồn đã xác minh.

### 3.3 Đoán quyền từ annotation hoặc tên role một cách hời hợt

Annotation như `@RequiresPermission("document.read")` có thể là **khóa tra chính sách tường minh**. Nhưng annotation tự nó không chứng minh principal được phép. Advice còn phải thực hiện đánh giá policy trên principal và resource thực tế.

Role-based access control (RBAC) cho phép diễn đạt các quyền theo vai trò; attribute-based access control (ABAC) thêm thuộc tính chủ thể, tài nguyên và bối cảnh. Trong nhiều trường hợp có thể kết hợp RBAC và ABAC. Tuy nhiên, cả hai mô hình đều yêu cầu **nguồn gốc tin cậy của thuộc tính** và chính sách được đánh giá tại đúng thời điểm.

## 4. Vai trò thực sự của pointcut và advice trong kiểm soát truy cập

Một thiết kế AOP nên phân biệt rõ hai bước:

1. **Chọn điểm cần bảo vệ:** pointcut nhận diện join point dựa trên cấu trúc phần mềm, annotation hoặc một danh sách operation khai báo cụ thể.
2. **Quyết định quyền:** advice lấy principal từ context tin cậy, xác định action theo policy binding, tìm resource và đánh giá quyền. Chỉ khi được phép mới thực thi hành vi gốc.

Tổng quát:

~~~mermaid
flowchart TD
    A[Yêu cầu vào hệ thống] --> B[Xác thực tại ranh giới tin cậy]
    B --> C[Điểm thực thi qua pointcut AOP]
    C --> D[Resolve action từ mapping tường minh]
    D --> E[Resolve resource và ngữ cảnh thực]
    E --> F{Policy cho phép?}
    F -->|Không hoặc thiếu dữ liệu| G[Deny, không thực thi nghiệp vụ]
    F -->|Có| H[Thực thi nghiệp vụ đúng một lần]
    H --> I[Trả kết quả hoặc lỗi gốc]
~~~

**Trách nhiệm của advice:**

- Từ chối khi operation cần bảo vệ không có policy binding, hoặc mapping bị lỗi.
- Không lấy principal “đã xác thực” từ tham số do caller tự chọn.
- Không tự tin tưởng các thuộc tính quyền do DTO/HTTP body truyền vào.
- Đảm bảo `proceed` hoặc lời gọi nghiệp vụ gốc chỉ diễn ra sau khi được cấp quyền và không bị gọi lặp.
- Bảo toàn kết quả và lỗi nghiệp vụ khi đã được phép thực hiện.
- Phân biệt lỗi từ chối quyền với lỗi nghiệp vụ; không trả thông tin nhạy cảm qua thông điệp exception.
- Không để telemetry/audit biến một quyết định deny thành allow; xử lý lỗi quan sát theo chính sách riêng.

**Một hạn chế cần ghi rõ:** AOP là cách *áp dụng* chính sách tại join point, không tự cung cấp identity provider, kho chính sách, transactional consistency hoặc boundary bảo mật cho mọi đường gọi. Nếu có lời gọi đi vòng điểm chặn, cơ chế này không bảo vệ được đường đó.

## 5. Ví dụ Java 17+ chạy độc lập: action khai báo rõ, quyền phụ thuộc tài nguyên

Ví dụ minh họa một giao diện `Documents` được bảo vệ bằng JDK dynamic proxy và một annotation `@Guarded`. Annotation dùng để **chỉ ra khóa action**; advice không suy “được phép” từ tên `read`/`publish` hay kiểu tham số `String`. Policy đọc thông tin tài liệu có thật, principal hiện tại và điều kiện xác thực tăng cường.

Chương trình dùng context giả lập bằng `ThreadLocal` **chỉ để mô phỏng một ranh giới xác thực đã hoàn tất**. Trong hệ thống thật, principal phải được thiết lập bởi thành phần xác thực đáng tin, không được cho code không đáng tin tùy ý gọi hàm `withUser` để giả mạo danh tính. Proxy ở ví dụ cũng chưa thay thế được bảo vệ mọi đường truy cập kho dữ liệu; phần sau sẽ giải thích cách bảo vệ boundary thực tế.

**Tệp: `ExplicitPolicyAspectDemo.java`**

~~~java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.lang.reflect.InvocationHandler;
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Method;
import java.lang.reflect.Proxy;
import java.util.Map;
import java.util.Set;
import java.util.function.Supplier;

public class ExplicitPolicyAspectDemo {
    @Retention(RetentionPolicy.RUNTIME)
    @Target(ElementType.METHOD)
    public @interface Guarded {
        String value();
    }

    record User(String id, String tenant, boolean mfa, Set<String> roles) {}
    record Document(String id, String tenant, String owner, String body) {}

    static final class AccessDenied extends RuntimeException {
        AccessDenied() {
            super("Access denied");
        }
    }

    interface Documents {
        @Guarded("document.read")
        String read(String documentId);

        @Guarded("document.publish")
        String publish(String documentId);
    }

    static final class Repository {
        private final Map<String, Document> data = Map.of(
            "doc-7", new Document(
                "doc-7", "tenant-A", "alice", "draft contents"
            )
        );

        Document find(String id) {
            return data.get(id);
        }
    }

    static final class DocumentOperations implements Documents {
        private final Repository repository;

        DocumentOperations(Repository repository) {
            this.repository = repository;
        }

        @Override
        public String read(String id) {
            return repository.find(id).body();
        }

        @Override
        public String publish(String id) {
            // Thao tác ghi được biểu diễn bằng kết quả xác định trong demo.
            return "published " + repository.find(id).id();
        }
    }

    static final class Policy {
        static boolean isAllowed(User user, String action, Document doc) {
            if (!user.tenant().equals(doc.tenant())) {
                return false;
            }

            return switch (action) {
                case "document.read" ->
                    user.id().equals(doc.owner())
                    || user.roles().contains("reviewer");

                case "document.publish" ->
                    user.id().equals(doc.owner()) && user.mfa();

                default -> false;
            };
        }
    }

    // Trong demo, hàm withUser ở main giả lập đầu vào đã xác thực.
    // Production phải lấy identity từ ranh giới xác thực đáng tin.
    private static final ThreadLocal<User> CURRENT = new ThreadLocal<>();

    static void withUser(User user, Runnable work) {
        User old = CURRENT.get();
        try {
            CURRENT.set(user);
            work.run();
        } finally {
            if (old == null) {
                CURRENT.remove();
            } else {
                CURRENT.set(old);
            }
        }
    }

    static Documents secured(Documents target, Repository repository) {
        InvocationHandler advice = (Object proxy, Method method,
                                    Object[] args) -> {
            if (method.getDeclaringClass() == Object.class) {
                // Hành vi an toàn của chính đối tượng proxy.
                return switch (method.getName()) {
                    case "toString" -> "SecuredDocumentsProxy";
                    case "hashCode" -> System.identityHashCode(proxy);
                    case "equals" -> proxy == args[0];
                    default -> throw new UnsupportedOperationException();
                };
            }

            Guarded binding = method.getAnnotation(Guarded.class);
            User user = CURRENT.get();

            if (binding == null || user == null || args == null
                || args.length != 1 || !(args[0] instanceof String id)) {
                throw new AccessDenied();
            }

            // Chỉ dùng vị trí/kiểu tham số theo hợp đồng API để lấy ID.
            // Kiểu String không hề là căn cứ cấp quyền.
            Document doc = repository.find(id);
            if (doc == null
                || !Policy.isAllowed(user, binding.value(), doc)) {
                throw new AccessDenied();
            }

            try {
                // Cho phép rồi mới chuyển tiếp chính xác một lần.
                return method.invoke(target, args);
            } catch (InvocationTargetException error) {
                throw error.getCause();
            }
        };

        return (Documents) Proxy.newProxyInstance(
            Documents.class.getClassLoader(),
            new Class<?>[] { Documents.class },
            advice
        );
    }

    static void check(String label, Supplier<String> action) {
        try {
            System.out.println(label + "=" + action.get());
        } catch (AccessDenied denied) {
            System.out.println(label + "=DENIED");
        }
    }

    public static void main(String[] args) {
        Repository repository = new Repository();
        Documents documents = secured(
            new DocumentOperations(repository), repository
        );

        withUser(new User("alice", "tenant-A", false, Set.of()), () -> {
            check("alice-read", () -> documents.read("doc-7"));
            check("alice-publish-no-mfa", () -> documents.publish("doc-7"));
        });

        withUser(new User("alice", "tenant-A", true, Set.of()), () ->
            check("alice-publish-mfa", () -> documents.publish("doc-7"))
        );

        withUser(new User("bob", "tenant-A", false,
                          Set.of("reviewer")), () ->
            check("bob-read", () -> documents.read("doc-7"))
        );

        withUser(new User("eve", "tenant-B", true,
                          Set.of("reviewer")), () ->
            check("eve-read", () -> documents.read("doc-7"))
        );

        check("anonymous-read", () -> documents.read("doc-7"));
    }
}
~~~

Lệnh chạy bằng JDK 17+:

~~~bash
javac ExplicitPolicyAspectDemo.java
java ExplicitPolicyAspectDemo
~~~

Stdout xác định:

~~~text
alice-read=draft contents
alice-publish-no-mfa=DENIED
alice-publish-mfa=published doc-7
bob-read=draft contents
eve-read=DENIED
anonymous-read=DENIED
~~~

**Giải thích từng quyết định:**

1. `alice` thuộc `tenant-A` và là chủ sở hữu tài liệu `doc-7` nên được `document.read` cho phép.
2. Khi `alice` chưa đạt điều kiện `mfa`, `document.publish` bị từ chối **dù cùng người và cùng tài liệu**.
3. Khi `alice` đã có `mfa` hợp lệ trong giả lập, `document.publish` được phép.
4. `bob` có role `reviewer` trong cùng tenant nên được đọc tài liệu; role này chưa mang quyền publish.
5. `eve` mang role `reviewer` nhưng khác tenant; điều kiện tenant được kiểm tra trước và việc đọc vẫn bị từ chối.
6. Khi `CURRENT` không chứa principal, kết quả là deny.

Trong ví dụ, `String` chỉ giúp tìm ID trong tham số của operation đã khai báo. Quyền đọc/ghi đến từ `Guarded` và `Policy`, kết hợp với chủ sở hữu/tenant đã được tra từ `Repository`. Nếu một phương thức mới được đưa vào interface mà quên `@Guarded`, proxy **từ chối** thay vì mặc định cho phép.

**Phạm vi bảo đảm:** Đây là mô phỏng về chính sách và đường chuyển tiếp của một *dynamic proxy*, chưa phải hệ thống xác thực hoàn chỉnh. `withUser` đang được gọi trực tiếp trong `main` để thử tình huống, không tạo ra một chứng cứ xác thực. `DocumentOperations` và repository vẫn có thể bị gọi trực tiếp nếu ứng dụng vô tình cung cấp tham chiếu; thực thi tại proxy không tự bảo vệ mọi đường truy cập. Trong ứng dụng thật, cần chặn các biên liên quan và bảo vệ dữ liệu ở lớp sở hữu tài nguyên.

## 6. Thiết kế policy binding tường minh, không mở nhầm quyền

### 6.1 Mỗi operation có một bản mô tả chính sách

Với một codebase lớn, có thể cấu hình mapping khai báo rõ:

~~~text
operation: documents.read
permission: document.read
resourceResolver: documentId -> trustedDocumentRepository
rule: sameTenant AND (owner OR reviewer)

operation: documents.publish
permission: document.publish
resourceResolver: documentId -> trustedDocumentRepository
rule: sameTenant AND owner AND verifiedStrongAuthentication
~~~

Đây là **cấu hình khái niệm**, không phải cú pháp của một thư viện cố định. Điểm chính là mỗi operation nói rõ action và cách định danh resource. Resolver không được “nhìn thấy kiểu `String` thì coi là documentId” ở mọi API; muốn lấy ID từ vị trí tham số phải dựa trên hợp đồng đã biết và được kiểm thử.

Việc thiếu annotation hoặc mapping cần dẫn tới **configuration error hoặc deny**, cùng một cảnh báo khi triển khai, thay vì mở quyền. Cần kiểm tra những phương thức đã đổi tên/đổi chữ ký để không bỏ sót binding.

### 6.2 Policy engine không phụ thuộc tên phương thức

Một policy engine có thể nhận một cấu trúc chuẩn hóa:

~~~text
principal:
  id: alice
  tenant: tenant-A
  permissions: [document.read]
resource:
  type: document
  id: doc-7
  tenant: tenant-A
  owner: alice
action: document.read
environment:
  strongAuthentication: false
~~~

Các dữ liệu ví dụ ở trên **chỉ minh họa các đầu vào**, không phải sự thật do chữ ký method xác nhận. Policy engine có thể dùng quyền role, quan hệ sở hữu, tenant, trạng thái tài nguyên, điều kiện thời gian, phân loại bí mật hoặc quyền được ủy quyền. Trách nhiệm của AOP là cung cấp dữ liệu đã xác minh đúng nguồn và chỉ chuyển tiếp sau quyết định `allow`.

Một role cao không mặc nhiên được phép vượt mọi tenant hoặc classification. Nếu chính sách thực sự cho phép quyền quản trị xuyên tenant, hãy khai báo và kiểm thử ngoại lệ đó một cách tường minh, không suy ra từ từ `Admin` trong tên phương thức hoặc DTO.

### 6.3 Resource ownership và kiểm soát ngang hàng

Một mẫu sai phổ biến:

~~~text
GET /documents/doc-of-bob
authenticatedUser = alice
method = getDocument(String)
authorization = "method starts with get"
result = allow   <-- lộ tài liệu của bob
~~~

Một thiết kế đúng phải tra `doc-of-bob` từ nguồn tin cậy rồi kiểm tra quan hệ giữa người gọi và document ấy. Việc người dùng được **xem tài liệu của chính mình** không tạo quyền xem mọi tài liệu có cùng kiểu. Đây là nhóm lỗi thường được gọi là *broken object-level authorization* / truy cập vượt quyền theo đối tượng.

Cũng cần kiểm soát **field-level authorization**: cùng một resource có thể cho phép đọc tiêu đề nhưng không cho phép đọc số định danh riêng, lương hoặc khóa bí mật. Nếu API trả một DTO chứa các field khác nhau, chỉ kiểm tra “được phép gọi phương thức read” ở cấp phương thức có thể chưa đủ. Policy có thể cần chọn projection dữ liệu được phép hoặc kiểm soát cách serialize trường nhạy cảm.

## 7. Những đường vượt qua pointcut hoặc proxy

### 7.1 Gọi trực tiếp vào đối tượng gốc

Một interface proxy chỉ chặn lời gọi **đi qua chính proxy**. Nếu caller có tham chiếu tới target và gọi `target.read(...)` trực tiếp, advice không được thực thi. Vì thế:

- Không công khai target hoặc repository cho code không có thẩm quyền.
- Thiết kế điểm kiểm soát tại boundary mà mọi đường truy cập bắt buộc phải đi qua.
- Với dữ liệu rất nhạy cảm, có thể cần kiểm soát bổ sung ở tầng lưu trữ, transaction hoặc chính thao tác quản lý dữ liệu, không chỉ lớp API bên ngoài.

### 7.2 Self-invocation và lời gọi nội bộ

Nếu `serviceA` đã qua proxy nhưng một phương thức trong target gọi `this.sensitiveOperation()` trực tiếp, lời gọi nội bộ có thể không qua proxy. Tính chất cụ thể phụ thuộc cơ chế AOP; không được mặc định mọi lời gọi đều bị chặn.

Giải pháp cần dựa trên kiến trúc thực: chuyển các thao tác yêu cầu quyền sang một boundary được bảo vệ riêng, hoặc dùng cơ chế weaving thực sự bắt được join point mong muốn. Không chọn một phương án chỉ vì có vẻ “tự động”; phải kiểm chứng những đường truy cập thực tế.

### 7.3 Reflection, callback và lời gọi gián tiếp

Các lệnh gọi từ reflection, method handles, event consumer, background job, RPC handler hoặc task chạy trên executor có thể xuất hiện ở những nơi không nằm trong pointcut khai báo. Reflection không tự bỏ qua mọi cơ chế bảo vệ, nhưng **một pointcut không chọn đường đó** sẽ không thực thi advice. Cần lập bản đồ entrypoint và kiểm tra mọi đường xử lý tài nguyên nhạy cảm.

### 7.4 Overload, bridge method, interface và kế thừa annotation

Các chữ ký như `load(String id)` và `load(long id)` có thể cùng tên nhưng được xử lý khác nhau; kiểu tham số có thể bị xóa/generate bridge, annotation trên interface/implementation có thể không được nhìn thấy bằng cùng cách reflection. Một proxy có thể nhận `Method` mô tả phương thức interface, trong khi weaving có thể nhìn implementation method. Vì vậy policy resolver cần giải quyết annotation/mapping **theo semantics chính xác của cơ chế dùng**, kiểm thử overload, inherited method, default method và generic bridge, và từ chối khi mapping không rõ.

Không viết quy tắc `if annotation not found then allow` để tránh lỗi cấu hình: đây là fail-open.

### 7.5 Phương thức Object và đường phụ

`toString()`, `equals()`, `hashCode()` đôi khi đi qua proxy. Nếu ủy quyền nguyên trạng tới đối tượng nghiệp vụ, một `toString()` vô tình trả dữ liệu nhạy cảm có thể lộ thông tin mà policy chưa bảo vệ. Mã ví dụ xử lý chúng với hành vi trung tính và không dùng tên những phương thức ấy để xác định quyền nghiệp vụ.

Không để serializer, debugger hoặc logger có quyền gọi phương thức nhạy cảm mà không đánh giá chính sách. Thông tin debug là dữ liệu có thể cần bảo vệ riêng.

## 8. Lấy principal từ đâu và truyền context qua bất đồng bộ thế nào?

**Principal không được do tham số request tự nhận.** Ví dụ client gửi:

~~~json
{
  "userId": "administrator",
  "tenant": "tenant-A",
  "resourceId": "doc-7"
}
~~~

Hai field `userId` và `tenant` trong body không đủ để trở thành danh tính có quyền. Thành phần xác thực cần kiểm tra bằng chứng phù hợp (session, token đã được xác minh hoặc channel identity) rồi tạo context đáng tin. Tên người dùng và tenant từ payload có thể dùng làm **đối tượng được yêu cầu** hoặc dữ liệu nghiệp vụ, nhưng không thay thế danh tính actor.

Với Java, `ThreadLocal` có thể tiện để truyền context **trong cùng một thread và scope được quản lý**, nhưng không tự lan qua thread mới, executor, reactive callback hoặc completion handler. Một thread trong pool còn có thể được tái sử dụng cho request khác. Nếu không đóng/khôi phục context, request sau có thể thấy principal cũ, tạo lỗ hổng nghiêm trọng.

Trong xử lý bất đồng bộ:

1. Xác thực caller tại ranh giới đã tin cậy.
2. Chụp một context bất biến/có vòng đời rõ và truyền tới tác vụ được ủy quyền theo cơ chế propagation phù hợp.
3. Khôi phục hoặc đóng context trong `finally`/scope được quản lý.
4. Đánh giá lại policy tại nơi sử dụng resource khi các điều kiện có thể đổi (quyền bị thu hồi, chủ sở hữu thay đổi, tenant bị khóa).
5. Tránh gọi `allow` chỉ vì callback không tìm thấy context; thiếu thông tin là trường hợp từ chối hoặc lỗi cấu hình.

Đừng giả định “caller ban đầu được phép” đồng nghĩa một tác vụ chạy sau nhiều giờ vẫn được phép. Với các thao tác dài hoặc queue nền, cần xác định chính sách dùng quyền tại lúc gửi lệnh hay tại lúc thực thi và kiểm chứng quyền còn hiệu lực theo mô hình đe dọa.

## 9. Time-of-check to time-of-use (TOCTOU)

Ngay cả khi advice đánh giá policy đúng tại thời điểm kiểm tra, dữ liệu có thể đổi **giữa kiểm tra và sử dụng**:

~~~text
T1: Advice đọc document.owner = alice
T2: Policy cho alice quyền publish
T3: Tác vụ khác chuyển owner sang bob
T4: Nghiệp vụ publish document mà không kiểm tra lại
~~~

Khi đó authorization có thể trở nên lỗi thời. Nếu đây là thao tác nhạy cảm, có thể cần đặt kiểm tra và thay đổi trạng thái trong **cùng transaction**, dùng version/optimistic locking, kiểm tra có điều kiện tại kho dữ liệu, hoặc thực thi quyền tại chính tầng sở hữu resource. Chính sách có thể cần “điều kiện tại thời điểm commit” thay vì “điều kiện tại thời điểm vào phương thức”.

Một cách khái niệm khi lưu trữ hỗ trợ update có điều kiện:

~~~sql
UPDATE documents
SET published = TRUE
WHERE id = :document_id
  AND tenant_id = :authenticated_tenant
  AND owner_id = :authenticated_user
  AND status = 'DRAFT';
~~~

SQL này minh họa việc gắn ràng buộc resource ngay tại thao tác cập nhật. Trong hệ thật, vẫn cần kiểm tra các điều kiện bổ sung như xác thực tăng cường, version, đối tượng tổ chức, quy tắc quyền kế thừa và xử lý quyền đặc biệt. `:authenticated_user` phải đến từ authentication context đã tin cậy.

## 10. Chức năng cấp quyền và quan sát bảo mật không được trộn lẫn

AOP có thể có nhiều aspect cùng tác động lên một join point: authorization, metrics, tracing, retry, transaction hoặc audit. Thứ tự chạy là quan trọng.

- Authorization cần diễn ra **trước khi side effect nhạy cảm bắt đầu**.
- Retry có thể làm một thao tác được thực thi nhiều lần. Policy phải xác định kiểm tra quyền theo từng attempt hay request logic; quyền có thể đổi giữa các lần thử.
- Transaction có thể quyết định thời điểm lấy dữ liệu, lock và commit. Nếu cần atomicity, thiết kế authorization/check cần tương thích transactional boundary.
- Logging không nên ghi thẳng tham số chứa token, mật khẩu, dữ liệu riêng tư hoặc toàn bộ tài liệu chỉ vì advice nhìn thấy chúng.
- Nếu metrics hoặc audit thất bại, ứng dụng cần chính sách rõ ràng về cho tiếp hay chặn; yêu cầu audit bắt buộc có thể khác telemetry chỉ phục vụ vận hành.
- Thứ tự kết hợp aspect có thể do cấu hình hoặc weaving. Không phụ thuộc vào suy đoán thứ tự; hãy xác minh bằng integration test.

Một điểm cần phân biệt: **authentication aspect** có thể kiểm tra caller đã đăng nhập, nhưng **authorization aspect** vẫn phải kiểm tra quyền đối với action + resource cụ thể. “Đã đăng nhập” chưa phải “được xem mọi dữ liệu”.

## 11. Thiết kế default deny mà không làm mất khả năng vận hành

“Deny by default” không có nghĩa mọi phương thức đều bắt buộc có một annotation quyền theo cùng một mẫu. Các thao tác công khai thực sự như health check hoặc trang thông tin không cần danh tính có thể được gán **policy công khai được khai báo và kiểm thử riêng**, ví dụ `PermitAnonymous` cho endpoint đã được duyệt.

Điều quan trọng là:

- **Mọi điểm truy cập tài nguyên cần bảo vệ đều được bao phủ bởi một policy xác định.**
- Trạng thái “không tìm thấy rule”, “không tìm thấy principal”, “không rõ resource” hoặc “policy engine không phản hồi” không được tự chuyển thành allow.
- Bảo vệ những entrypoint ít gặp: batch job, timer, message consumer, administrative tooling, import/export, callback và dữ liệu tải từ cache.
- Chính sách đặc quyền (break-glass, superuser, delegated authority) cần bằng chứng tường minh, phạm vi và logging/audit, không được suy ra từ một tên gọi.

Khi deny, tránh tiết lộ resource có tồn tại hay không nếu thông tin đó nhạy cảm. Một hệ thống có thể trả thông báo từ chối chung trong cả trường hợp không có quyền và không tìm thấy tài nguyên. Cách ánh xạ sang trạng thái API do hợp đồng quyết định; tuy nhiên log nội bộ vẫn có thể phân loại nguyên nhân phù hợp mà không lộ dữ liệu nhạy cảm cho caller.

### Cẩn thận với “allow list theo phương thức”

Một danh sách các method được phép gọi không đồng nghĩa tất cả đối tượng truy cập từ method đó đều được phép. `documents.read` có thể là operation hợp lệ của một role, nhưng vẫn cần kiểm tra ID cụ thể và tenant. Authorization ở mức phương thức và authorization ở mức đối tượng là các lớp kiểm soát khác nhau, có thể cùng cần thiết.

## 12. Checklist kiểm thử quyền truy cập với AOP

Bài kiểm thử cần trả lời cả **“điểm chặn có hoạt động?”** lẫn **“chính sách có đưa ra quyết định đúng?”**:

| Tình huống | Kết quả mong đợi |
| --- | --- |
| Không có principal | Deny và không thực thi nghiệp vụ |
| Principal hợp lệ, đúng action, đúng resource | Allow nếu mọi điều kiện policy đạt |
| Đúng role, sai tenant | Deny |
| Đúng tenant, không phải chủ sở hữu và không có quyền chia sẻ | Deny |
| Đúng owner nhưng thiếu điều kiện tăng cường | Deny |
| Client tự gửi field `role: admin` hoặc `ownerId` | Không tự được cấp quyền |
| Resource không tồn tại hoặc thiếu metadata | Deny/không lộ thông tin theo hợp đồng |
| Action chưa khai báo policy | Deny và phát hiện cấu hình thiếu |
| Đổi tên method nhưng giữ action binding hợp lệ | Quyết định quyền không tự đổi |
| Overload cùng tên, kiểu tham số khác nhau | Phân giải policy theo binding rõ, không theo tên |
| Phương thức trả `CompletionStage`/stream | Đúng vòng đời và context, không bỏ check |
| Gọi trực tiếp target/self-invocation | Phát hiện đường bypass; bảo vệ boundary thật |
| Policy store chậm, timeout hoặc lỗi | Không fail-open; có fallback được thiết kế |
| Quyền/ownership thay đổi khi thao tác đang chạy | Kiểm tra lại hoặc đảm bảo atomicity theo yêu cầu |
| Advice bị gọi lặp, nhiều thread cùng truy cập | Không cho phép vì race hay context bị rò rỉ |
| Lỗi xảy ra sau khi đã allow | Trả exception nghiệp vụ gốc, không ghi nhầm thành lỗi authorization |

### Kiểm thử tính chất của policy

Ngoài các ví dụ riêng lẻ, có thể kiểm tra một số **bất biến**:

1. Đổi **tên phương thức** nhưng giữ cùng action và resource không được tự thay đổi quyền.
2. Đổi **kiểu bao tham số** mà nội dung nghiệp vụ đã được chuẩn hóa không được tự nâng quyền.
3. Đổi resource owner/tenant sang một đối tượng không được phép phải làm `allow` chuyển thành `deny` theo chính sách tương ứng.
4. Xóa một quyền khỏi tập role đã xác thực không được làm tăng số hành động được phép.
5. Thiếu thông tin bắt buộc dẫn tới từ chối; policy engine lỗi không mở quyền.
6. Khi bị deny, số lần nghiệp vụ gốc được thực thi là **0**; khi được allow theo advice thuần túy, số lần được thực thi là **1**.

Có thể kiểm thử theo ma trận principal × action × resource × context, và bổ sung property-based/fuzz testing để tìm tổ hợp tham số gây vượt quyền. Đừng chỉ dùng một user admin trong test, vì trường hợp đó có thể che giấu lỗi authorization theo đối tượng.

## 13. Rủi ro nâng cao: caching quyết định và quyền thay đổi

Khi policy evaluation tốn kém, một hệ thống có thể cache quyết định `allow/deny`. Cache phải chọn khóa đúng:

`cacheKey = (subject, action, resource, relevantContext, policyVersion)`

Đây là sơ đồ khái niệm; các thuộc tính như tenant, quyền uỷ quyền, phiên xác thực tăng cường, trạng thái tài nguyên và thời điểm cũng có thể ảnh hưởng kết quả. Nếu chỉ cache theo `methodName` hoặc `parameterType`, hệ thống có thể tái sử dụng quyết định của `alice` để cho `bob` truy cập.

Ngay cả khi cache key đủ chi tiết, quyền hoặc ownership có thể bị thu hồi. Cần TTL, invalidation, policy versioning hoặc một nguồn quyết định nhất quán. Không tối ưu chi phí phân quyền bằng cách bỏ qua sự thay đổi quyền mà chưa có hợp đồng về độ trễ thu hồi.

Một aspect có thể “có vẻ đúng” ở thử nghiệm đơn luồng nhưng hỏng khi chạy song song: dữ liệu principal trong biến static dùng chung, mutable context bị sửa, race cập nhật cache hoặc context rò qua thread pool. Mỗi quyết định cần gắn với đúng request/subject; ưu tiên context bất biến, scope rõ và kiểm thử concurrency.

## 14. Phân tích trường hợp trước–sau

**Trước:**

~~~text
Một người dùng đăng nhập được gọi:
  method = getInvoice(String invoiceId)
  invoiceId = invoice của người khác

Pointcut: tên method bắt đầu bằng get
Advice: cho phép vì có chữ get
Kết quả: dữ liệu hóa đơn bị đọc trái phép
~~~

**Sau:**

~~~text
Method binding:
  action = invoice.read
  resolver = lấy invoice theo invoiceId từ kho đáng tin

Advice:
  principal = lấy từ authentication context đã xác minh
  invoice = resolver(invoiceId)
  policy = kiểm tra tenant + owner hoặc grant truy cập
  nếu thiếu/thất bại -> deny
  nếu allow -> gọi nghiệp vụ đúng một lần

Kết quả:
  chỉ dữ liệu được chính sách cấp phép mới được trả
~~~

Trường hợp này minh họa lý do **chữ ký phương thức chỉ giúp tìm dữ liệu cần kiểm tra**, không đủ để kết luận ai được truy cập. Nếu invoice có nhiều field với mức nhạy cảm khác nhau, cần kiểm tra cả quyền xem từng phần dữ liệu hoặc xây projection tương ứng.

## 15. Quy trình thiết kế aspect phân quyền an toàn

1. **Xác định tài sản và mô hình đe dọa:** loại dữ liệu nào nhạy cảm, actor nào có thể gọi từ entrypoint nào, phương thức nào ghi side effect.
2. **Xác định action nghiệp vụ:** ví dụ `document.read`, `document.publish`, `account.transfer`; không dùng prefix của tên hàm như một đặc quyền.
3. **Xác định resource resolver:** từ ID được validate, tra metadata/quan hệ sở hữu ở nguồn đáng tin; hỗ trợ tenant và phân cấp tài nguyên nếu cần.
4. **Xây policy rõ ràng:** quyền role, ownership, grant, thuộc tính, điều kiện session, MFA, trạng thái tài nguyên và ngoại lệ được duyệt.
5. **Bố trí điểm cắt phù hợp:** verify proxy/weaving bắt đúng mọi đường vào cần bảo vệ, xử lý overload/inheritance/default methods.
6. **Cố định nguồn principal:** từ lớp xác thực, tránh tự lấy ID do client khai; truyền context qua async và dọn scope an toàn.
7. **Quy định fail closed:** thiếu annotation/rule/context/resource hoặc policy evaluation lỗi đều không tự tạo allow.
8. **Đảm bảo tính đúng ở data boundary:** cân nhắc transaction, version, conditional update, defense-in-depth khi ownership thay đổi.
9. **Kiểm thử cả positive lẫn negative:** tenant chéo, owner khác, role giả, policy thiếu, bypass, concurrent calls, quyền bị thu hồi.
10. **Theo dõi và rà soát:** audit quyết định quan trọng với dữ liệu tối thiểu; theo dõi deny/error và thay đổi chính sách, tránh log bí mật.

## 16. Những nhầm lẫn cần tránh

**“Tên bắt đầu bằng `get` nghĩa là chỉ đọc, nên an toàn.”** Sai. Đọc dữ liệu bí mật có thể gây thiệt hại lớn và “read-only” không đồng nghĩa “public”.

**“Tham số là `AdminRequest` nên chỉ admin mới tạo được.”** Sai. Một class DTO có thể do bất cứ caller nào dựng; kiểu dữ liệu không chứng minh quyền.

**“Người gọi đã đăng nhập, kiểm tra theo phương thức là đủ.”** Sai. Cần quyết định quyền đối với resource và action cụ thể.

**“Có annotation thì được phép.”** Sai. Annotation có thể định danh chính sách; việc được phép vẫn phải được đánh giá bằng dữ liệu đáng tin.

**“Proxy chặn được method này thì mọi lời gọi đều bị bảo vệ.”** Sai nếu tồn tại tham chiếu target, self-invocation hoặc một entrypoint không đi qua proxy.

**“ThreadLocal có principal nghĩa là đang ở trong request hợp lệ.”** Không chắc. Context có thể bị giả mạo ở lớp không tin cậy hoặc rò rỉ giữa các tác vụ nếu quản lý sai.

**“Đã kiểm tra owner trước khi ghi nên không cần xét gì nữa.”** Chưa chắc. Quyền hoặc metadata có thể thay đổi giữa kiểm tra và commit; thao tác nhạy cảm cần xử lý TOCTOU.

**“Cho phép khi không tìm được policy giúp hệ thống vẫn chạy.”** Đó là fail-open và có thể tạo lỗ hổng khi cấu hình thiếu, kho chính sách bị lỗi hoặc một phương thức mới được thêm.

## 17. Kết luận

AOP giúp **đưa kiểm soát truy cập tới các điểm thực thi một cách nhất quán**, nhưng tính đúng của phân quyền phụ thuộc vào chính sách và nguồn dữ liệu được tin cậy. **Tên phương thức và kiểu tham số chỉ mô tả API; chúng không xác thực danh tính, không chứng minh quyền sở hữu và không cấp đặc quyền.** Một aspect an toàn phải gắn operation với action được khai báo rõ, lấy principal từ ranh giới xác thực, lấy resource từ nguồn đáng tin, đánh giá đầy đủ subject–action–resource–context, từ chối khi thiếu dữ liệu và kiểm tra mọi đường thực thi có thể bỏ qua điểm chặn.