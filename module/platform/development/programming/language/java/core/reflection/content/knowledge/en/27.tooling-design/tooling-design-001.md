# Tách khám phá metadata khỏi thực thi thao tác trong Java Reflection

Trong các công cụ dựa trên Java Reflection (plugin registry, command runner, hệ thống đăng ký tool, framework kiểm thử), có hai nhiệm vụ riêng:

- **Discovery / khám phá metadata:** tìm các thao tác *có thể* được cung cấp, đọc tên, annotation, tham số, kiểu trả về, quyền truy cập, rồi xây danh mục.
- **Execution / thực thi:** nhận yêu cầu gọi một thao tác cụ thể, kiểm tra quyền và đầu vào, chuẩn bị receiver, rồi mới chạy code thật.

Hai việc thường cùng dùng đối tượng `Class<?>` và `Method`, nhưng không có cùng mức tác động. Việc người dùng bấm “Xem danh sách công cụ” phải không tự trở thành lời gọi xóa dữ liệu, gửi email hoặc cập nhật trạng thái. Tách hai giai đoạn giúp kiểm soát side effect, kiểm thử dễ hơn và ghi dấu việc ai đã thực thi thao tác nào.

## 1. Phân biệt lấy metadata với kích hoạt hành vi

| Hoạt động | API minh họa | Kết quả | Có yêu cầu chạy method nghiệp vụ? |
|---|---|---|---|
| Tham chiếu kiểu | `SomeType.class` | `Class<?>` | Không |
| Tải mà chưa yêu cầu khởi tạo | `Class.forName(name, false, loader)` | `Class<?>` | Không |
| Liệt kê method | `type.getDeclaredMethods()` | `Method[]` | Không |
| Đọc signature/annotation | `getName()`, `getParameterTypes()`, `getAnnotation(...)` | Metadata | Không |
| Đăng ký action | Kiểm tra annotation/chữ ký, tạo descriptor | Catalog | Không |
| Gọi method | `method.invoke(receiver, args...)` | Kết quả/exception/side effect | **Có** |
| Gọi constructor | `constructor.newInstance(...)` | Đối tượng mới | **Có** |
| Đọc/ghi field | `field.get(...)` / `field.set(...)` | Giá trị/thay đổi | Có thao tác thật trên trạng thái |

Ví dụ:

```java
Method action = Service.class.getDeclaredMethod("process", String.class);
// Mới tìm thấy thông tin về method.

Object result = action.invoke(service, "payload");
// Đã thực thi process(...) trên đối tượng service.
```

Đây là đoạn minh họa, giả định `Service`, `service`, kiểu trả về, method và quyền truy cập đều phù hợp. Với static method, receiver cho `Method.invoke` có thể là `null`.

**Lưu ý chính xác:** discovery không đồng nghĩa tuyệt đối “JVM không làm gì”. Nạp lớp hoặc đọc signature có thể khiến JVM tải/resolve class phụ thuộc hay phát sinh `LinkageError`; custom class loader có thể chạy logic của nó. Tuy nhiên, những API metadata trên **không tự gọi các method nghiệp vụ đang được liệt kê**. Nếu muốn tránh yêu cầu class initialization chỉ để đọc metadata, xem xét `Class.forName(name, false, loader)` thay vì `Class.forName(name)`.

## 2. Một kiến trúc tách biệt rõ ràng

```text
Đăng ký các kiểu / plugin được cho phép
                 |
                 v
            DISCOVER
   - Class<?> / getDeclaredMethods()
   - đọc annotation, tên, chữ ký
   - không invoke, không tạo instance để "thử"
                 |
                 v
             VALIDATE
   - allowlist, ID duy nhất, visibility
   - signature, mô tả, mức tác động
                 |
                 v
       IMMUTABLE REGISTRY
      /                  \
     v                    v
LIST/DESCRIBE           EXECUTE
Trả metadata       1. Resolve action ID
Không chạy code    2. Xác thực và phân quyền
                   3. Kiểm tra input / policy
                   4. Chuẩn bị receiver nếu cần
                   5. Invoke, audit, trả kết quả
```

**Registry** là ranh giới giữa danh mục và thực thi. Mỗi entry nên có ID ổn định, mô tả, input schema, output schema, yêu cầu quyền, mức ảnh hưởng (đọc/ghi/gửi ngoài), và một handle hoặc executor **nội bộ**.

Phía client chỉ nên nhận các trường mô tả an toàn, không nhận đối tượng `Method`, receiver hoặc quyền tự gọi Reflection. Khi request gửi `actionId="publish"`, máy chủ tìm entry đã đăng ký, kiểm tra quyền tại **thời điểm thực thi**, rồi mới dispatch.

Những điều cần tách ra:

1. **Discovery không phải authorization:** nhìn thấy action không có nghĩa được quyền chạy.
2. **Annotation không phải sự thật bảo mật:** `mutates=false` là khai báo do lập trình viên cung cấp; code implementation vẫn phải được đánh giá.
3. **Approval của thao tác có tác động** là trạng thái đáng tin cậy do server quản lý, không phải boolean mà caller tùy ý tự chọn.

## 3. Ví dụ Java 17+: xem metadata không kích hoạt static initializer

Chương trình sau giới thiệu một annotation `@ToolAction`, tìm các method hợp lệ trong một lớp, lưu registry và chỉ thực thi khi có lời gọi tường minh. `Actions` có static initializer để quan sát chính xác **lúc nào class được khởi tạo**.

Lưu thành tệp **`ReflectionToolBoundaryDemo.java`**:

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Method;
import java.lang.reflect.Modifier;
import java.util.Map;
import java.util.TreeMap;

public class ReflectionToolBoundaryDemo {
    @Retention(RetentionPolicy.RUNTIME)
    @Target(ElementType.METHOD)
    @interface ToolAction {
        String name();
        boolean mutates() default false;
    }

    public static class Actions {
        static {
            System.out.println("Actions initialized");
        }

        @ToolAction(name = "preview")
        public static String preview(String payload) {
            return "Preview: " + payload;
        }

        @ToolAction(name = "publish", mutates = true)
        public static String publish(String payload) {
            System.out.println("Published: " + payload);
            return "OK";
        }

        public static String hidden(String payload) {
            throw new AssertionError("not registered");
        }
    }

    record ActionDescriptor(String name, boolean mutates, Method method) {}

    static Map<String, ActionDescriptor> discover(Class<?> type) {
        Map<String, ActionDescriptor> actions = new TreeMap<>();
        for (Method method : type.getDeclaredMethods()) {
            ToolAction config = method.getAnnotation(ToolAction.class);
            if (config == null) continue;

            if (!Modifier.isPublic(method.getModifiers())
                    || !Modifier.isStatic(method.getModifiers())
                    || method.getParameterCount() != 1
                    || method.getParameterTypes()[0] != String.class
                    || method.getReturnType() != String.class) {
                throw new IllegalArgumentException(
                        "Invalid action signature: " + method.getName());
            }

            ActionDescriptor previous = actions.putIfAbsent(config.name(),
                    new ActionDescriptor(config.name(), config.mutates(), method));
            if (previous != null) {
                throw new IllegalArgumentException(
                        "Duplicate action: " + config.name());
            }
        }
        return Map.copyOf(actions);
    }

    static String execute(Map<String, ActionDescriptor> actions,
                          String name, String payload, boolean permitMutation)
            throws ReflectiveOperationException {
        ActionDescriptor descriptor = actions.get(name);
        if (descriptor == null) {
            throw new IllegalArgumentException("Unknown action: " + name);
        }
        if (descriptor.mutates() && !permitMutation) {
            throw new SecurityException("requires authorization");
        }

        try {
            return (String) descriptor.method().invoke(null, payload);
        } catch (InvocationTargetException e) {
            Throwable cause = e.getCause();
            if (cause instanceof RuntimeException runtime) throw runtime;
            if (cause instanceof Error error) throw error;
            throw e;
        }
    }

    public static void main(String[] args) throws ReflectiveOperationException {
        System.out.println("1. Discovery");
        Class<?> clazz = Actions.class;
        Map<String, ActionDescriptor> registry = discover(clazz);
        registry.keySet().stream().sorted().forEach(
                name -> System.out.println("found: " + name));

        System.out.println("2. Try without authorization");
        try {
            execute(registry, "publish", "Ada", false);
        } catch (SecurityException ex) {
            System.out.println("blocked: " + ex.getMessage());
        }

        System.out.println("3. Execute preview");
        System.out.println(execute(registry, "preview", "Ada", false));

        System.out.println("4. Execute permitted publish");
        System.out.println(execute(registry, "publish", "Ada", true));
    }
}
```

Lệnh biên dịch và chạy:

```bash
javac --release 17 -encoding UTF-8 ReflectionToolBoundaryDemo.java
java ReflectionToolBoundaryDemo
```

**Stdout thực tế đã kiểm tra với mã này:**

```text
1. Discovery
found: preview
found: publish
2. Try without authorization
blocked: requires authorization
3. Execute preview
Actions initialized
Preview: Ada
4. Execute permitted publish
Published: Ada
OK
```

**Giải thích từng mốc:**

1. `Actions.class` tạo tham chiếu kiểu, `getDeclaredMethods()` cùng `getAnnotation(...)` đọc mô tả, nên chưa có dòng `Actions initialized`.
2. Chỉ hai method có `@ToolAction` được đăng ký. `hidden(String)` dù public vẫn **không** trở thành action. `TreeMap` và lệnh `sorted()` làm thứ tự output ổn định vì thứ tự `getDeclaredMethods()` không được bảo đảm.
3. `publish` chưa được cho phép bị chặn **trước** `Method.invoke`. Class `Actions` vẫn chưa khởi tạo.
4. `preview` được gọi thật bằng `invoke(null, "Ada")`. Vì đây là static method, JVM khởi tạo `Actions` nếu chưa khởi tạo, in `Actions initialized` đúng một lần.
5. `publish` sau khi được cho phép in `Published: Ada`. Lần gọi này không chạy lại static initializer.
6. `Map.copyOf` làm registry trả về không thể bị sửa cấu trúc qua các API `Map` bình thường; việc kiểm soát quyền invoke vẫn thuộc executor. `ActionDescriptor` giữ `Method` để sử dụng nội bộ, không xuất ra phía client.

**Giới hạn chủ đích:** mã mẫu chỉ chấp nhận public static method `String f(String)`, nên không cần tạo receiver. Với instance method, executor phải xác định lifecycle target và dùng receiver đúng kiểu, không tạo instance ngay trong discovery. `permitMutation` ở đây chỉ dùng để chứng minh điểm chặn, **không phải mô hình xác thực**: hệ thống thật phải suy quyền từ context đã xác thực ở server, tuyệt đối không tin cờ do client gửi.

## 4. API nào nên gọi trong mỗi giai đoạn?

### Discovery: chỉ cần tra cứu và kiểm tra

- `Class.getDeclaredMethods()`: lấy cả method khai báo private/package-private/protected/public, nhưng không tự cấp quyền gọi chúng.
- `Class.getMethods()`: lấy các method public, gồm method kế thừa theo ngữ nghĩa API. Chọn một trong hai theo nhu cầu và điều kiện discovery.
- `Method.getName()`, `getModifiers()`, `getParameterTypes()`, `getReturnType()`: đọc chữ ký.
- `AnnotatedElement.getAnnotation(...)`: đọc annotation có thể truy cập tại runtime; annotation cần `@Retention(RUNTIME)` nếu muốn phát hiện ở runtime.
- `Class.getDeclaredConstructors()` / `getDeclaredFields()`: lấy mô tả constructor/field, chưa chạy chúng.

Không biến `getDeclaredMethods()` thành danh sách công cụ tự động. Một class có thể có method nội bộ, callback, getter gây tác động, method quản trị và method `Object`. Discovery cần **allowlist** và bộ kiểm tra kiểu/annotation.

### Execution: hành động có thể có side effect

- `Method.invoke(...)` chạy method; invocation của static method có thể yêu cầu initialization của lớp khai báo.
- `Constructor.newInstance(...)` thực thi constructor, tạo đối tượng và có thể chạy initialization trước đó.
- `Field.get(...)` / `Field.set(...)` truy cập **giá trị**, khác hẳn `getDeclaredField(...)` chỉ tìm metadata. Với static field, có thể kích hoạt initialization.
- `MethodHandle.invoke(...)` / `invokeExact(...)` gọi handle đã tìm, khác với lúc lookup handle.

Nếu muốn tải lớp chỉ để kiểm kê, `Class.forName(binaryName, false, loader)` tránh yêu cầu class initialization của kiểu đích trong lời gọi đó. Tuy nhiên, việc nạp lớp vẫn có thể thất bại vì classpath, class loader, modules hoặc dependency bị thiếu.

## 5. Đăng ký công cụ đúng cách

Một entry registry hữu ích thường có các trường:

| Trường | Mục đích |
|---|---|
| `actionId` | Tên/ID ổn định, không trùng |
| `description` | Giải thích hành động để người gọi hiểu |
| `inputSchema` | Kiểu dữ liệu, ràng buộc, giới hạn kích thước |
| `outputSchema` | Định dạng kết quả được công bố |
| `effect` | Đọc dữ liệu, ghi/sửa, xóa hoặc gửi ra ngoài |
| `requiredPermissions` | Quyền executor phải kiểm tra |
| `method/handler` nội bộ | Điểm thực thi sau khi được cho phép |

Nên:

1. Chỉ đọc những class/package/plugin đã đăng ký hoặc được phép. Nếu plugin đến từ nguồn không đáng tin cậy, việc chỉ dùng Reflection **không tạo sandbox**; cần cơ chế cô lập tương ứng.
2. Dùng annotation marker và kiểm tra schema/signature **trước khi** đưa vào registry. Không công bố method chỉ vì nó có `public`.
3. Từ chối `actionId` trùng thay vì âm thầm ghi đè method; sắp xếp danh mục theo ID để có kết quả ổn định.
4. Không dùng `setAccessible(true)` vô điều kiện để vượt encapsulation; Java module system có thể giới hạn truy cập. Ưu tiên entrypoint public có chủ đích.
5. Tạo snapshot registry bất biến sau khi validate. Nếu hỗ trợ hot reload, xuất bản registry mới bằng một bước thay thế có kiểm soát để request không nhìn thấy danh mục nửa chừng.
6. Khi xuất metadata thành JSON, không serialize raw `Method`, receiver, ClassLoader, secret hay thông tin nội bộ không cần thiết.

## 6. Thực thi đúng cách và xử lý lỗi

Một executor đáng tin cậy nên xử lý theo thứ tự:

1. **Resolve** action ID từ registry đã validate. Không lấy trực tiếp tên class/method từ input của client rồi gọi Reflection tùy ý.
2. **Authenticate và authorize** theo danh tính, vai trò, tenant, đối tượng, phạm vi dữ liệu và trạng thái hiện tại. Quyền phải được kiểm tra **mỗi lần gọi**.
3. **Validate/bind** input theo schema. Phân biệt input không hợp lệ với lỗi thực thi.
4. **Kiểm tra tác động:** thao tác ghi, xóa, gửi ra ngoài cần policy hoặc xác nhận thích hợp; thực thi có retry cần cơ chế idempotency phù hợp. Không coi method tên `preview` hay annotation `readOnly` là bảo đảm vô hại.
5. **Chuẩn bị receiver** cho instance method theo lifecycle service/container; không tạo đối tượng chỉ để xem metadata.
6. **Invoke** và bắt/log lỗi có kiểm soát; audit action ID, caller, quyết định cấp quyền, kết quả và correlation ID, tránh ghi secret trong log.

| Exception/vấn đề | Thường phát sinh ở đâu | Cách xử lý |
|---|---|---|
| `NoSuchMethodException` | Tìm sai tên hoặc signature trong discovery | Báo lỗi cấu hình/đăng ký |
| `ClassNotFoundException`, `LinkageError` | Nạp/resolve lớp hay dependency | Kiểm tra class loader, module path, dependency |
| `IllegalAccessException`, `InaccessibleObjectException` | Truy cập method bị giới hạn | Sửa visibility hoặc module boundary theo thiết kế |
| `IllegalArgumentException` | Bind receiver/tham số sai hoặc validate input | Kiểm tra schema và loại đối số |
| `InvocationTargetException` | Method được gọi ném exception | Đọc `getCause()`, phân loại lỗi nghiệp vụ |
| `ExceptionInInitializerError` | Static initialization bị lỗi | Xác định code khởi tạo, trạng thái class và lỗi gốc |
| Timeout, lặp lại request | Thực thi, đặc biệt thao tác có side effect | Giới hạn tài nguyên, audit, idempotency; cân nhắc cô lập |

**Chú ý:** deadline hoặc timeout không tự bảo đảm một method đang chạy sẽ dừng ngay hay rollback side effect. Không tự retry hành động có tác động nếu không có bảo đảm an toàn phù hợp.

## 7. Các tình huống thực tế

**CLI/command runner:** lệnh `list` và `help` chỉ dùng registry; lệnh `run <action>` mới đi qua executor. Người dùng có thể xem khả năng hệ thống mà chưa thay đổi trạng thái.

**Plugin host:** lúc khởi động đăng ký handler và kiểm tra metadata; lúc người dùng chọn plugin mới tạo instance/gọi method theo lifecycle. Constructor, đăng ký callback hoặc DI có thể có side effect, nên phải được quản lý ở đúng phase.

**Hệ thống tool-calling:** bước “describe tools” chỉ trả tên, mô tả, input schema và ràng buộc. Khi caller yêu cầu gọi một tool, backend xác thực, phân quyền và dispatch thông qua registry; bản thân việc gửi danh mục cho caller **không cấp quyền Reflection**.

**Framework kiểm thử:** discovery liệt kê method được đánh dấu `@Test`; execution mới xây fixture, chạy before-hook, gọi test và thu kết quả. Nếu khởi tạo test class trong discovery, ranh giới hai bước bị mờ và khó kiểm soát side effect.

## 8. Sai lầm cần tránh và câu hỏi tự kiểm tra

- **“Có `Method` là method đã chạy.”** Sai: `Method` chỉ chứa metadata; `invoke` là một đường thực thi.
- **“`getDeclaredMethods()` tự sắp xếp theo thứ tự mã nguồn.”** Sai: không nên phụ thuộc thứ tự này.
- **“Có annotation nghĩa là được phép gọi.”** Sai: annotation giúp đăng ký hoặc mô tả, còn phân quyền thuộc executor.
- **“Chỉ đọc tên class bằng `Class.forName(name)` thì static block chắc chưa chạy.”** Sai: overload một tham số yêu cầu class initialization.
- **“Không gọi nghiệp vụ trong discovery nghĩa là mọi thao tác bên dưới đều tuyệt đối không có tác động.”** Sai: class loading/linkage hay custom loader vẫn có hành vi riêng, nên cần xác định trust boundary.
- **“Tool chỉ đọc luôn vô hại.”** Chưa chắc: getter có thể thay state hoặc gọi I/O; phải xem implementation và policy.
- **“Báo `InvocationTargetException` cho người dùng là đủ.”** Chưa đủ: nên phân loại cause để biết lỗi thực tế từ code được gọi.

**Câu hỏi 1:** Vì sao code mẫu không in `Actions initialized` ngay trong discovery?

Vì thao tác `Actions.class` và đọc các `Method`/annotation không yêu cầu initialization của `Actions`. Static method `preview` được gọi bằng `invoke` mới kích hoạt lần khởi tạo đầu tiên.

**Câu hỏi 2:** Có cần gọi `Constructor.newInstance` để lấy tên các method instance không?

**Không.** Có thể đọc method metadata từ `Class<?>` mà chưa tạo instance. Việc tạo receiver là công việc khi thực thi.

**Câu hỏi 3:** Vì sao vẫn kiểm tra quyền sau khi đã xây registry an toàn?

Vì registry trả lời **“những gì có thể được cung cấp”**, còn quyền thực thi phụ thuộc caller, tài nguyên và thời điểm. Điều kiện đó có thể thay đổi giữa các lần gọi.

## Tài liệu tham khảo

- [Java SE 17 — Class](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html): tra cứu class, method, field, constructor và `forName`.
- [Java SE 17 — Method](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Method.html): metadata và `invoke`.
- [Java SE 17 — AccessibleObject](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/AccessibleObject.html): quyền truy cập Reflection.
- Java Language Specification §12.4.1 và JVM Specification §5: quy tắc loading/linking/initialization.

**Ghi nhớ:** Discovery mô tả **có những thao tác nào**; execution quyết định **ai được phép gọi thao tác nào với input nào** và thực hiện nó có kiểm soát. Không biến việc quét metadata thành việc chạy code nghiệp vụ.
