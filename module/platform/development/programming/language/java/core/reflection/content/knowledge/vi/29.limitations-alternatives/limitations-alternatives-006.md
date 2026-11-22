# Kiểm tra quyền và giới hạn dữ liệu đầu vào khi chọn lớp hoặc phương thức bằng Java Reflection

## 1. Vấn đề: reflection biến tên thành hành vi thực thi

Reflection cho phép chương trình tìm `Class`, `Method`, `Field` hoặc `Constructor` lúc chạy. Nếu tên lớp/phương thức, kiểu tham số hoặc đối tượng đích được chọn **trực tiếp từ request, JSON, query parameter, header, cấu hình bên ngoài hoặc thông điệp hàng đợi**, ứng dụng có thể vô tình tạo một cơ chế **gọi chức năng tùy ý**.

Ví dụ nguy hiểm về mặt thiết kế, **chỉ để phân tích, không dùng trong ứng dụng**:

~~~java
// Ví dụ KHÔNG AN TOÀN. Đây là đoạn trích, không phải chương trình độc lập.
Class<?> clazz = Class.forName(requestedClassName);
Object object = clazz.getDeclaredConstructor().newInstance();
Method method = clazz.getMethod(requestedMethodName, String.class);
Object result = method.invoke(object, requestedArgument);
~~~

Các tên `requestedClassName` và `requestedMethodName` ở đây không được phép do client tùy ý quyết định. Nếu phần mềm chứa nhiều lớp có tác động đến dữ liệu, quyền của người dùng chỉ nên cho phép gọi một tập tác vụ hẹp; đoạn code trên không áp đặt ranh giới đó.

**Mục tiêu bảo vệ:** người gọi chỉ được lựa chọn **hành động đã được công bố**, trên **tài nguyên mà họ có quyền**, với **đối số đã được kiểm tra**, thông qua **receiver và Method do mã đáng tin cậy kiểm soát**.

Một quy tắc quan trọng: **`public` trong Java không có nghĩa “user hiện tại được phép gọi qua API”**. Tương tự, `setAccessible(true)` có liên quan đến kiểm tra truy cập của reflection và giới hạn module, **không hề thực hiện kiểm tra quyền nghiệp vụ**.

## 2. Threat model: phân biệt bốn nguồn dữ liệu

| Thành phần | Nguồn an toàn mong đợi | Rủi ro nếu để client kiểm soát |
| --- | --- | --- |
| **Danh tính và vai trò** | Bối cảnh xác thực đã được server kiểm tra, token được xác minh chữ ký/hiệu lực, session hợp lệ | Client tự khai là `ADMIN`, giả mạo tenant hoặc principal |
| **Tên thao tác** | Key ngắn trong allowlist do server định nghĩa, ví dụ `profile.read` | Gọi method nội bộ như `resetAll` hoặc chọn class ngoài ý định |
| **Receiver/Method** | Instance/Method được server resolve, đăng ký và cache trước | Tự chọn một class hoặc method bất kỳ; tạo object ngoài phạm vi |
| **Đối số nghiệp vụ** | Chuỗi/ID/schema đã parse, validate và được kiểm tra quyền sở hữu | IDOR/BOLA, vượt phạm vi tenant, payload quá lớn, chuyển đổi kiểu sai |

*Authentication* trả lời “caller là ai?”. *Authorization* trả lời “caller có quyền thực hiện **hành động này trên tài nguyên này** không?”. *Input validation* trả lời “dữ liệu có đúng kiểu, đúng dạng, đúng giới hạn không?”. Ba bước phải được thực hiện **độc lập**; một bước không thay thế được bước còn lại.

Ví dụ user có quyền đọc profile của chính mình nhưng **không mặc nhiên** có quyền đọc profile của người khác; admin có thể được cho phép một số thao tác đặc quyền, nhưng mỗi thao tác vẫn cần policy cụ thể. Trong hệ thống đa tenant, kiểm tra tenant của đối tượng đích còn quan trọng hơn chỉ kiểm tra tên method.

## 3. Kiến trúc nên dùng: allowlist hành động, không mở reflection theo tên tùy ý

~~~text
Client:
  action = "profile.read"
  userId = "U-0001"
      |
      v
[1] Lấy danh tính từ phiên/token đã xác thực trên server
      |
      v
[2] Tra action trong allowlist cố định
    "profile.read" -> ProfileService.read(String)
    "account.lock" -> AdminService.lock(String)
      |
      v
[3] Validate input: kiểu, độ dài, pattern, số phần tử...
      |
      v
[4] Authorization: role + quyền trên tài nguyên/tenant
      |
      v
[5] Invoke đúng Method/receiver server đã đăng ký
      |
      v
[6] Trả kết quả công khai phù hợp; log/audit có kiểm soát
~~~

Không đưa tên class đầy đủ `com.company.AdminService` hay chữ ký tùy ý của Java vào giao diện request. Hãy map một mã hành động ổn định sang receiver và method **do server sở hữu**:

- Allowlist cần **tường minh**: ví dụ `"profile.read"` và `"account.lock"`, không quét toàn bộ method `public` rồi tự coi tất cả được phép.
- Cố định signature: `getMethod("read", String.class)` khác `getMethod("read", Object.class)` và khác các overload còn lại.
- Bind **chính sách bảo mật vào route đã đăng ký**; không chỉ kiểm tra tên request rồi chọn `Method` khác sau đó.
- Không có route khớp thì **deny by default**. Đừng fallback sang `Class.forName(userInput)` hay `getDeclaredMethod(userInput)`.
- Nếu không cần reflection, lời gọi Java trực tiếp hoặc router kiểu interface/strategy thường dễ audit và an toàn hơn. Reflection không phải bắt buộc để làm dispatch động.

## 4. Chương trình Java 17+ đầy đủ: chọn phương thức an toàn

Ví dụ tối giản minh họa: hai hành động được công khai, actor có `USER` hoặc `ADMIN`, quyền đọc profile **của chính mình** hoặc của admin, còn khóa tài khoản chỉ admin được phép. Các dịch vụ trong demo trả chuỗi, **không thực sự truy cập hay thay đổi tài khoản**.

Lưu thành **`SafeReflectionRouterDemo.java`**:

~~~java
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Method;
import java.util.Map;
import java.util.regex.Pattern;

public class SafeReflectionRouterDemo {
    enum Role { USER, ADMIN }
    enum Policy { SELF_OR_ADMIN, ADMIN_ONLY }

    // Actor chỉ được tạo từ bối cảnh xác thực đáng tin cậy trên server.
    record Actor(String userId, Role role) {}

    record Route(Object receiver, Method method, Policy policy) {}

    public static final class ProfileService {
        public String read(String userId) {
            return "profile:" + userId;
        }
    }

    public static final class AdminService {
        public String lock(String userId) {
            return "locked:" + userId;
        }
    }

    // Mã tài nguyên là ASCII cố định, không nhận đường dẫn hoặc class name.
    private static final Pattern USER_ID = Pattern.compile("U-[0-9]{4}");

    // Method/receiver được resolve từ hằng số tin cậy, duy nhất một lần.
    private static final Map<String, Route> ROUTES = buildRoutes();

    private static Map<String, Route> buildRoutes() {
        try {
            ProfileService profile = new ProfileService();
            AdminService admin = new AdminService();

            return Map.of(
                "profile.read",
                new Route(
                    profile,
                    ProfileService.class.getMethod("read", String.class),
                    Policy.SELF_OR_ADMIN),
                "account.lock",
                new Route(
                    admin,
                    AdminService.class.getMethod("lock", String.class),
                    Policy.ADMIN_ONLY)
            );
        } catch (NoSuchMethodException ex) {
            throw new ExceptionInInitializerError(ex);
        }
    }

    static String dispatch(Actor actor, String action, String targetId) {
        // Mã action không phải tên class hoặc tên method Java.
        if (action == null || action.length() > 40) {
            throw new IllegalArgumentException("UNSUPPORTED_ACTION");
        }

        Route route = ROUTES.get(action);
        if (route == null) {
            throw new IllegalArgumentException("UNSUPPORTED_ACTION");
        }

        if (targetId == null || !USER_ID.matcher(targetId).matches()) {
            throw new IllegalArgumentException("INVALID_ID");
        }

        // Danh tính phải đến từ hệ thống auth, không phải JSON request.
        if (actor == null || actor.role() == null) {
            throw new SecurityException("DENIED");
        }

        boolean permitted = switch (route.policy()) {
            case ADMIN_ONLY -> actor.role() == Role.ADMIN;
            case SELF_OR_ADMIN -> actor.role() == Role.ADMIN
                    || actor.userId().equals(targetId);
        };

        if (!permitted) {
            throw new SecurityException("DENIED");
        }

        try {
            return (String) route.method().invoke(
                    route.receiver(), targetId);
        } catch (IllegalAccessException ex) {
            throw new IllegalStateException("SERVER_CONFIGURATION_ERROR", ex);
        } catch (InvocationTargetException ex) {
            // Không trả stack trace hay nội dung exception đích cho client.
            throw new IllegalStateException("OPERATION_FAILED");
        }
    }

    static void show(Actor actor, String action, String userId) {
        try {
            System.out.println(action + " -> "
                    + dispatch(actor, action, userId));
        } catch (IllegalArgumentException | SecurityException ex) {
            System.out.println(action + " -> " + ex.getMessage());
        }
    }

    public static void main(String[] args) {
        Actor owner = new Actor("U-0001", Role.USER);
        Actor admin = new Actor("U-9000", Role.ADMIN);

        show(owner, "profile.read", "U-0001");
        show(owner, "profile.read", "U-0002");
        show(owner, "account.lock", "U-0002");
        show(admin, "account.lock", "U-0002");
        show(owner, "java.lang.Runtime.exec", "U-0001");
        show(admin, "profile.read", "U-0001/../../");
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac --release 17 -encoding UTF-8 SafeReflectionRouterDemo.java
java SafeReflectionRouterDemo
~~~

Output kỳ vọng:

~~~text
profile.read -> profile:U-0001
profile.read -> DENIED
account.lock -> DENIED
account.lock -> locked:U-0002
java.lang.Runtime.exec -> UNSUPPORTED_ACTION
profile.read -> INVALID_ID
~~~

### Vì sao ví dụ này an toàn hơn cách chọn class/method tùy ý?

1. **Client chọn key, không chọn Class.** `"java.lang.Runtime.exec"` không phải key được đăng ký nên bị từ chối; không có lệnh `Class.forName(action)`.
2. **Receiver và Method cố định.** `ProfileService.class.getMethod(...)` và `AdminService.class.getMethod(...)` chỉ thực thi trên hằng số của server lúc khởi tạo. Không có wildcard như “mọi public method của một class”.
3. **Policy gắn với Route.** `profile.read` chỉ chấp nhận chính chủ hoặc admin; `account.lock` chỉ chấp nhận admin. Việc có tên action hợp lệ **chưa đủ** để được phép thực thi.
4. **Đối số được giới hạn.** `U-[0-9]{4}` là ví dụ về ID hợp lệ có đúng 6 ký tự. Chuỗi giống đường dẫn bị từ chối; regex dùng `matches()` nên phải khớp **toàn bộ** giá trị, không chỉ khớp một phần.
5. **Mọi request vẫn được authorize.** Cache `Method` chỉ để tránh lookup lặp lại; **không cache một kết quả “đã được phép” để dùng cho người gọi khác**.
6. **Không tăng quyền truy cập reflection.** Ví dụ chỉ dùng phương thức `public` được đăng ký. Nó không gọi `setAccessible(true)` hay `trySetAccessible()` để mở các member riêng tư.

**Giới hạn của demo:** `Actor` được tạo trực tiếp trong `main` để mô phỏng môi trường đã xác thực. Trong dịch vụ thật, **không được** dựng `Actor(userId, role)` từ hai trường client tự cung cấp. Phải dùng identity/claims đã được xác minh ở lớp auth, đồng thời kiểm tra đối tượng đích qua database/service theo tenant và quyền sở hữu. `ProfileService` và `AdminService` trong ví dụ chỉ trả chuỗi nên chưa biểu diễn kiểm tra dữ liệu thật, transaction, audit hoặc rate limit.

## 5. Các lớp kiểm tra phải có trong production

### 5.1. Authentication: caller lấy quyền từ đâu?

- Server xác thực session hoặc token: chữ ký, issuer, audience, thời hạn, thu hồi khi hệ thống có cơ chế đó.
- Identity, role và tenant không được quyết định chỉ bằng `request.getParameter("role")` hoặc một JSON field.
- Khi service gọi service, cần phân biệt danh tính người dùng cuối và danh tính máy; service account không tự động được phép thay người dùng thực hiện mọi thao tác.
- Request thiếu hoặc không hợp lệ phải fail closed trước khi gọi member tác động tới dữ liệu.

### 5.2. Authorization: kiểm tra cả thao tác lẫn tài nguyên

| Câu hỏi | Ví dụ |
| --- | --- |
| Caller có quyền gọi action không? | User thường không được gọi `account.lock` |
| Caller có quyền trên **đối tượng này** không? | Được `profile.read` nhưng chỉ với profile thuộc phạm vi được cấp |
| Tài nguyên có thuộc đúng tenant/organization không? | Không đọc tài khoản tenant khác dù ID đúng format |
| Trạng thái tài nguyên có cho phép thao tác không? | Tài khoản đã khóa hoặc đã xóa cần được xử lý theo state machine |
| Có cần kiểm tra lại ngay trước thay đổi không? | Tránh TOCTOU khi quyền hoặc trạng thái dữ liệu có thể thay đổi |
| Ai ghi nhận việc thay đổi? | Audit actor, action, resource ID, outcome; loại bỏ dữ liệu bí mật |

**ID có regex hợp lệ không phải bằng chứng sở hữu.** Ví dụ chỉ minh họa self-or-admin; trong ứng dụng thật, object-level authorization phải thực hiện theo dữ liệu đáng tin cậy. Với multi-tenant, có thể truy vấn tài nguyên bằng **cặp** `(tenantId, resourceId)` rồi kiểm tra quyền trước khi xử lý. Tầng service/domain nên có kiểm tra quyền tương ứng để không bị vượt qua nếu bị gọi từ con đường khác ngoài HTTP router.

### 5.3. Input validation: giới hạn chi phí và bề mặt tấn công

Không chỉ kiểm tra tên class/method. Mọi đối số truyền vào reflection cũng là dữ liệu đầu vào:

- **Allowlist hành động:** chỉ các key đã đăng ký. Giới hạn độ dài, mã hóa và dạng thức; không nhận tên lớp fully qualified tùy ý.
- **Arity và type:** `Method` được chọn phải có đúng chữ ký đăng ký; parse JSON thành DTO/schema cố định trước khi invoke. Không cho client truyền tên các kiểu trong mảng `Class<?>[]` để tự chọn overload.
- **Chuỗi, ID và path:** giới hạn độ dài và tập ký tự; khi cần đường dẫn, chuẩn hóa và kiểm tra path trong root được phép **sau khi resolve**, tránh traversal và symlink ngoài phạm vi.
- **Kích thước và độ sâu:** giới hạn request body, số lượng phần tử collection, nesting depth, số lần gọi, timeout/rate limit. Một action được phép vẫn có thể gây resource exhaustion nếu payload không có trần.
- **Kiểu số và enum:** giới hạn min/max, overflow và giá trị hợp lệ; không dựa vào `Method.invoke` tự bắt mọi lỗi nghiệp vụ.
- **Output:** lọc trường dữ liệu được phép trả về, không serialise toàn bộ object nội bộ hay exception/stacktrace.
- **Ghi log:** không log password, token, PII nhạy cảm hoặc toàn bộ `args`. Có thể log action key, correlation ID và quyết định cấp quyền.

### 5.4. Lựa chọn class trong plugin/configuration

Có ứng dụng thật sự cần cấu hình tên lớp (ví dụ kiến trúc plugin). Khi đó:

1. Phân biệt **config do operator quản lý** và input từ người dùng cuối. Không coi hai nguồn có cùng mức độ tin cậy.
2. Áp dụng allowlist hoặc registry các provider được phê duyệt; kiểm tra nguồn artifact, chữ ký và phiên bản theo mô hình triển khai.
3. Sau `Class.forName(...)`, kiểm tra `expectedInterface.isAssignableFrom(clazz)` và API/constructor được phép. **Type check chỉ xác nhận tương thích kiểu, không chứng minh code đáng tin.**
4. Hạn chế quyền và tài nguyên ở cấp **process/container/OS/service account** cho plugin không đáng tin; class loader riêng **không phải sandbox bảo mật**.
5. Phân quyền và validate đối số riêng cho mỗi capability. Không biến “plugin được load” thành “plugin được phép làm mọi thứ”.
6. Ưu tiên cơ chế đăng ký capability hoặc factory có kiểm soát thay vì cho phép tên class tùy ý từ request.

Lưu ý `Class.forName(String)` không phải thao tác kiểm chứng vô hại: overload một đối số có thể dẫn đến **khởi tạo class** theo ngữ nghĩa API, nên code `static` của class cũng đáng quan tâm. Overload `Class.forName(name, false, loader)` có thể tránh khởi tạo tại bước đó nhưng **không biến việc load class tùy ý thành an toàn**, cũng không thay kiểm soát quyền.

## 6. Reflection access khác quyền nghiệp vụ

Java có nhiều tầng kiểm soát, không được lẫn chúng:

| Tầng | Cơ chế | Không bảo đảm điều gì |
| --- | --- | --- |
| Ngôn ngữ Java | `public`, `protected`, package-private, `private` | Không xác nhận user HTTP có quyền nghiệp vụ |
| Reflection API | `getMethod`/`getDeclaredMethod`, `canAccess`, `trySetAccessible` | Không kiểm tra ownership, role, tenant |
| Java module system (JPMS) | `exports`, `opens` và quy tắc deep reflection | Không xác nhận một request hợp lệ về hành vi |
| Ứng dụng | Authentication, authorization, tenant/object policy, validation, audit | Cần lập trình rõ ràng; JVM không tự hiểu quy tắc nghiệp vụ |

`getDeclaredMethod(...)` có thể **tìm được** private method nhưng không có nghĩa caller được phép invoke. `setAccessible(true)` chỉ yêu cầu bỏ qua một số kiểm tra access **trong phạm vi module cho phép** và có thể ném `InaccessibleObjectException`; không làm một thao tác trở thành đúng về security. Tránh dùng `--add-opens` để mở module chỉ nhằm “chạy được mọi request”.

Ngoài ra, Java reflection có ngoại lệ runtime cần xử lý đúng: `NoSuchMethodException` khi lookup không có kết quả, `IllegalAccessException` khi invoke không được phép truy cập, `IllegalArgumentException` khi receiver/argument sai, và `InvocationTargetException` bao nguyên nhân do thân method ném. Những lỗi này **không thay thế** logic từ chối yêu cầu trước khi thực hiện.

## 7. Anti-pattern và cách thay thế

| Anti-pattern | Vì sao nguy hiểm | Thiết kế thay thế |
| --- | --- | --- |
| `Class.forName(request.className)` trên input tùy ý | Chọn class ngoài tập chức năng dự kiến, có thể kích hoạt initialization | Registry/allowlist class tin cậy hoặc không cho chọn class |
| `clazz.getMethod(request.methodName, ...)` rồi invoke | Public method không đồng nghĩa được expose cho request | Action key cố định → `Route` chứa Method và policy |
| `setAccessible(true)` để gọi private API | Mở rộng khả năng deep reflection; bỏ qua ranh giới thiết kế | Public facade đã được audit; quyền OS/module tối thiểu |
| `isAdmin = request.get("admin")` | Client tự quyết định đặc quyền | Principal và claims từ auth server đã verify |
| Chỉ kiểm tra `id.matches(...)` | Đúng dạng nhưng có thể là tài nguyên người khác | Object/tenant authorization từ nguồn dữ liệu tin cậy |
| Cache quyết định authorize theo method | User khác nhau có quyền khác nhau | Cache metadata, **evaluate policy cho từng lời gọi** |
| Auto-expose mọi method có annotation `@Action` | Annotation không đủ nếu không có kiểm soát review/policy | Registry được phê duyệt, policy rõ ràng, quét có kiểm soát |
| Trả `ex.getCause().toString()` cho client | Rò rỉ nội bộ và có thể lộ dữ liệu | Mã lỗi công khai chuẩn hóa, log nội bộ có bảo vệ |
| So `startsWith("com.safe.")` rồi nhận mọi class | Namespace/package không chứng minh code hoặc capability đáng tin | Allowlist type cụ thể và kiểm soát artifact/source |

## 8. Checklist trước khi đưa vào production

1. Giao diện request chỉ chọn **mã hành động đã công bố**; không nhận tên class, private method hay constructor tùy ý.
2. Registry lưu **receiver + Method + policy** do server thiết lập. Không có route → từ chối.
3. Identity/role/tenant đến từ nguồn **đã xác thực**; không đọc trực tiếp từ payload để xác định quyền.
4. Kiểm tra quyền **mỗi lần gọi** cả theo action lẫn resource/tenant; với thao tác thay đổi trạng thái, xét cả race/TOCTOU.
5. Giới hạn schema/kiểu/độ dài/số lượng/depth/rate; không giao việc validate cho `Method.invoke`.
6. Không dùng `setAccessible` hoặc `--add-opens` như cơ chế phân quyền; coi public API và authorization là hai vấn đề khác nhau.
7. Test các case: action lạ, method overload, user không có role, cross-tenant ID, request kích thước lớn, null input, và exception từ target.
8. Audit các từ chối và thao tác quan trọng bằng dữ liệu tối thiểu; thông báo lỗi cho client không tiết lộ stacktrace/nội bộ.
9. Cache `Method` để giảm lookup là được, **không được bỏ qua policy check** chỉ vì Method đã cache.
10. Với plugin class động, yêu cầu allowlist/quản trị artifact và cơ chế isolation ở cấp hệ thống nếu code không đáng tin.

## 9. Tự kiểm tra

- Vì sao `getMethod(...)` trả được public method nhưng vẫn phải kiểm tra authorization riêng?
- Nếu user có quyền `profile.read`, tại sao họ chưa chắc có quyền với mọi user ID hợp lệ?
- Sự khác nhau giữa **allowlist action** và **lọc package bằng prefix** là gì?
- Vì sao gọi `Class.forName(untrustedName)` từ request có rủi ro ngay cả trước `Method.invoke(...)`?
- Có nên cache cả kết quả `"được phép gọi Method này"` cho mọi user? Vì sao?
- Khi plugin chạy code ngoài tổ chức, chỉ tạo `ClassLoader` mới đã đủ tạo sandbox chưa?

### Tài liệu chính thức

- Java SE 21 — `Class` và `Class.forName`: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Class.html
- Java SE 21 — `Method` và `Method.invoke`: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/reflect/Method.html
- Java SE 21 — `AccessibleObject`: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/reflect/AccessibleObject.html
- Java SE 21 — `InaccessibleObjectException`: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/reflect/InaccessibleObjectException.html
- OWASP Authorization Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html
- OWASP Input Validation Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Input_Validation_Cheat_Sheet.html