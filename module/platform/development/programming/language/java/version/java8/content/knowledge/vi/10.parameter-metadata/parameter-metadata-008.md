# Tích hợp binding, dependency injection và tài liệu API bằng metadata tham số (Java 8+)

## 1. Bài toán và mục tiêu

**Metadata tham số** là cầu nối giữa một chữ ký method/constructor Java và các hệ thống cần hiểu **mỗi tham số đại diện cho điều gì**. Từ Java 8, `java.lang.reflect.Executable.getParameters()` và `java.lang.reflect.Parameter` cho phép truy cập tên (khi được lưu), kiểu, annotation và một số cờ của tham số. Thông tin này thường được dùng trong ba công việc:

1. **Data binding:** ánh xạ input HTTP, CLI, message hoặc configuration thành các giá trị tương ứng với tham số của handler.
2. **Dependency injection (DI):** xác định dependency nào cần được truyền vào constructor hoặc method, đôi khi thêm qualifier để giải quyết nhiều implementation cùng kiểu.
3. **Tài liệu API:** tạo hoặc kiểm chứng mô tả tên, kiểu, vị trí, bắt buộc/tùy chọn, ý nghĩa của các tham số từ một hợp đồng có cấu trúc.

Đây là các kỹ thuật **đang được dùng trong Java hiện đại**. Tuy nhiên, chúng không đồng nghĩa: data binding xử lý dữ liệu bên ngoài, DI cấp phát các collaborator trong ứng dụng, còn API documentation mô tả hợp đồng giao tiếp. Cả ba có thể đọc `Parameter[]` nhưng **không nên suy ra cùng một chính sách** chỉ từ tên hoặc kiểu Java.

Đọc xong, bạn có thể:

- Lấy metadata từ `Method`/`Constructor` mà không nhầm method parameter với field/local variable.
- Phân biệt tên source do `javac -parameters` lưu và nhãn nghiệp vụ từ annotation tường minh.
- Thiết kế binder có whitelist kiểu, kiểm input bắt buộc, thông báo lỗi và validation.
- Hiểu cách DI chọn constructor, resolve dependency theo kiểu/qualifier và phát hiện thiếu/nhầm dependency.
- Dùng cùng nguồn metadata có kiểm soát để tạo API docs, đồng thời biết những thứ **không thể** suy ra chỉ từ Reflection.
- Kiểm thử contract runtime, build tool, generated docs và trường hợp thiếu `MethodParameters`.
- Chạy một chương trình Java standalone minh họa cả ba luồng; chương trình có output xác định.

**Phạm vi:** Tập trung vào tích hợp metadata tham số trong module Java 8 và ứng dụng Java hiện hành. Những ví dụ tự viết dưới đây có mục đích **học cơ chế**; không được coi là framework HTTP/DI/authorization sẵn sàng cho production. Bài dùng Java 8-origin APIs và có thể biên dịch trên JDK còn được hỗ trợ với `--release 8` khi cần.

## 2. Các lớp metadata dùng trong tích hợp

Giả sử khai báo:

~~~java
void find(
    @QueryKey("customerId") String id,
    @RangeHint(min = 1, max = 20) int limit
) { /* ... */ }
~~~

Với annotation tự định nghĩa đúng target và retention, một công cụ có thể đọc:

| Lớp thông tin | API | Được dùng để làm gì |
| --- | --- | --- |
| Executable và chữ ký | `Method`, `Constructor<?>`, `getParameterCount()`, `getParameters()` | Xác định vị trí và số lượng tham số |
| Tên Java source | `Parameter.getName()`, `isNamePresent()` | Ánh xạ theo tên khi build lưu metadata |
| Kiểu runtime | `getType()` | Quyết định converter, tra dependency theo raw class |
| Kiểu generic | `getParameterizedType()` | Phân tích `List<String>`, `Optional<T>` hoặc generic contract |
| Annotation trên declaration | `getAnnotation(...)` | Ánh xạ tên external, qualifier, validation rule |
| Annotation trên lần dùng kiểu | `getAnnotatedType()` | Nullness/type-use metadata nếu có công cụ diễn giải |
| Cờ tham số | `isVarArgs()`, `isImplicit()`, `isSynthetic()` | Nhận diện signature đặc biệt/varargs |
| Chữ ký ngoại lệ và modifier | `Executable`/`Method` APIs | Phân tích contract method khi cần |

`Parameter` mô tả **formal parameter** của method/constructor đã biên dịch, **không** mô tả giá trị runtime được caller truyền vào. Ví dụ `getType()==String.class` không có nghĩa input HTTP là string an toàn; input vẫn phải được parse, validate, encode và authorize khi thích hợp.

### Lấy đúng executable

~~~java
Method m = UserController.class.getDeclaredMethod(
    "show", String.class, int.class);
Parameter[] parameters = m.getParameters();

Constructor<UserService> ctor =
    UserService.class.getDeclaredConstructor(UserRepository.class);
Parameter[] dependencies = ctor.getParameters();
~~~

Đây là mã **minh họa**, tên class có đầy đủ trong ví dụ chạy ở mục 8. Với overloaded method, phải cung cấp đúng kiểu tham số và thứ tự. `getDeclaredMethod` chỉ tra khai báo trực tiếp của class được chọn; `getMethod` tìm public method theo quy tắc Reflection và có thể thấy method kế thừa. Constructor không được kế thừa.

**Không dựa vào thứ tự `getDeclaredMethods()` hoặc `getDeclaredConstructors()`** để “chọn phần tử đầu tiên”. Nếu hệ thống có nhiều endpoint hoặc constructor, cần quy tắc chọn tường minh và test ambiguity.

## 3. Tên tham số: `-parameters`, tên tổng hợp và annotation tường minh

Compiler Java không bắt buộc lưu tên source của mọi formal parameter dưới dạng Reflection có thể đọc. Khi dùng `javac`, bật:

~~~text
javac --release 8 -parameters -encoding UTF-8 ParameterIntegrationDemo.java
~~~

để yêu cầu ghi **`MethodParameters` attribute**. Sau đó, với method trong source có `String id, int repeat`:

~~~java
Parameter p = method.getParameters()[0];
System.out.println(p.getName());        // id, khi tên source đã được lưu
System.out.println(p.isNamePresent()); // true trong điều kiện đó
~~~

Nếu không có tên trong classfile, `getName()` vẫn trả một chuỗi được sinh như `arg0` và `isNamePresent()` trả false. Đây **không phải tên nghiệp vụ đáng tin**.

### Hai chiến lược binding theo tên

**Chiến lược A — annotation explicit** (nên ưu tiên cho public contract):

~~~java
void show(@QueryKey("id") String id, @QueryKey("repeat") int repeat) {}
~~~

Tên `id`/`repeat` dành cho client đến từ annotation: vẫn rõ ràng nếu source đổi tên `id` thành `userIdentifier`. Annotation cần `@Target(PARAMETER)` và `@Retention(RUNTIME)` nếu binder đọc qua Reflection ở runtime.

**Chiến lược B — suy ra tên Java source**:

~~~java
void show(String id, int repeat) {}
~~~

Binder dùng `Parameter.isNamePresent()`, sau đó `getName()`. Nó chỉ đúng khi class **khai báo executable** được build và đóng gói có metadata tên phù hợp. Nếu không, nên **fail fast** hoặc sử dụng annotation tường minh; không im lặng sử dụng `arg0`/`arg1` làm tên query.

**Ưu tiên đề xuất:** annotation explicit khi đó là tên ổn định trong API public; tên source khi dự án đã tiêu chuẩn hóa `-parameters` và có test trên artifact thật.

| Nguồn tên | Tác động khi refactor tham số | Khi thiếu `-parameters` |
| --- | --- | --- |
| `@QueryKey("id")` | Ổn định nếu annotation giữ nguyên | Vẫn có thể đọc qua Reflection |
| `getName()` với `isNamePresent()` | Có thể thay đổi khi đổi tên source | Không đáng tin; `argN` |
| Vị trí tham số index 0/1 | Tránh cần tên, nhưng dễ vỡ khi đổi thứ tự | Vẫn có index, cần contract rõ |
| Metadata trong framework riêng | Tuỳ quy tắc của framework/build tool | Phải kiểm cơ chế version cụ thể |

Flag `-g` hoặc `-g:vars` lưu debug metadata **khác** `MethodParameters`, không phải cách thay thế đáng tin cho `-parameters`. Một số framework Java hiện đại không còn dựa vào bytecode local-variable debug tables để đoán tên. Khi build thiếu flag, hãy sửa **compiler configuration** của module phát hành class, không chữa bằng đoán chuỗi `arg0`.

### Tác động khi nâng cấp framework hoặc JDK

Bản thân Reflection API này vẫn hiện hành. Nhưng framework có thể thay đổi **chiến lược suy ra tên** khi nâng phiên bản. Ví dụ tài liệu nâng cấp Spring Framework 6.x đã nhấn mạnh việc dùng `-parameters` cho các cơ chế phụ thuộc tên Java thay vì local-variable debug information. Không kết luận rằng “mọi framework luôn cần flag” vì một số framework dùng annotation explicit hoặc quy tắc binding khác. Phải kiểm trên **version được dự án triển khai**.

Maven/Gradle hiện đại có cấu hình chính thức để truyền flag này vào Java compiler. Ví dụ với plugin/compiler phù hợp, cấu hình Maven Compiler Plugin có thuộc tính `<parameters>true</parameters>`; với Gradle, kiểm `options.compilerArgs` hoặc API tương ứng của phiên bản Gradle đang dùng. Sau build, chạy test Reflection hoặc `javap -v` trên **jar đã đóng gói** để chắc chắn metadata không mất qua bytecode transformations.

## 4. Data binding: chuyển dữ liệu ngoài vào tham số

Một request HTTP giả định:

~~~text
GET /users?id=42&repeat=2
~~~

Handler tương ứng:

~~~java
String show(@QueryKey("id") String id, @QueryKey("repeat") int repeat) { ... }
~~~

Luồng xử lý:

~~~text
HTTP request (untrusted strings)
       │
       ▼
Route /users + HTTP method
       │
       ▼
Executable metadata: [@QueryKey id : String, @QueryKey repeat : int]
       │
       ▼
Tên key → lấy dữ liệu → converter (String/int)
       │
       ▼
Validate required/range/format; reject invalid input
       │
       ▼
Authorization + business method invocation
       │
       ▼
Response + error mapping
~~~

**Metadata giúp xây binder; không thay thế binder.** HTTP query nhận chuỗi ký tự. Nếu handler muốn `int`, phải parse `Integer.parseInt` và xử lý `NumberFormatException`; nếu muốn enum/date/UUID/collection, cần converter có hợp đồng riêng. Khi thiếu dữ liệu, phải phân biệt:

- Không có key (`null`/absent).
- Key có mặt nhưng giá trị rỗng (`""`).
- Key được gửi nhiều lần (multivalue).
- Key có dữ liệu sai kiểu, sai khoảng, sai định dạng hoặc quá dài.
- Value hợp lệ về cú pháp nhưng không hợp lệ về business/authorization.

Một binder an toàn **không** dựa vào Reflection để tự khởi tạo tùy ý class được client đưa tên. Hãy dùng whitelist converter và giới hạn input size/complexity. Trong sản phẩm HTTP thực, dùng framework binding đã được cập nhật, kèm validation và error mapping chuẩn; chỉ xây binder Reflection riêng khi có nhu cầu và test đầy đủ.

### Annotation `@Target(PARAMETER)` cho mapping

~~~java
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.PARAMETER)
@interface QueryKey {
    String value();
}
~~~

Binder đọc:

~~~java
QueryKey q = parameter.getAnnotation(QueryKey.class);
String key = q == null
    ? (parameter.isNamePresent() ? parameter.getName() : null)
    : q.value();

if (key == null || key.isEmpty()) {
    throw new IllegalStateException("Missing stable parameter binding key");
}
~~~

Khi input là dữ liệu không tin cậy, kiểm missing và convert theo `parameter.getType()`. Cách này dùng tên tường minh trước; tên source chỉ là fallback có điều kiện. Nếu framework có annotation sẵn như `@RequestParam`/`@PathVariable`, hãy dùng annotation của **framework/version** đó thay vì tự tạo `@QueryKey` ngoài mục đích học.

### Chọn kiểu dữ liệu và required/optional

Kiểu `int` là primitive nên không biểu diễn `null`; nếu query optional, một số framework cho phép `Integer`, `Optional<Integer>` hoặc default value tùy contract riêng. **Không tự suy luận `required=false` chỉ từ wrapper `Integer`**, và không coi `Optional<T>` là metadata mặc định cho mọi framework. API docs, runtime binder và validation phải thống nhất một quy tắc.

Một method có `String id` không tự bảo đảm `id` là UUID hay số định danh hợp lệ, cũng không cho phép truy xuất tài nguyên chưa kiểm quyền sở hữu. Nullability và authorization là hợp đồng riêng, cần thực thi và test.

## 5. Dependency injection: metadata constructor và qualifier

DI đảo chiều việc tạo dependency: service nhận collaborator qua constructor thay vì tự `new` trong logic nghiệp vụ.

~~~java
interface UserRepository {
    String findName(String id);
}

class UserService {
    private final UserRepository repository;

    UserService(UserRepository repository) {
        this.repository = repository;
    }
}
~~~

Một DI container có thể inspect:

1. Constructor nào được chọn? Qua annotation như `@Inject`, qua một constructor duy nhất hoặc quy tắc cụ thể của framework.
2. Mỗi `Parameter` đòi loại dependency nào? `p.getType()`, `p.getParameterizedType()`, qualifier annotations.
3. Trong registry có bean/service cùng type? Có **một**, nhiều hay không có ứng viên?
4. Lifecycle/scope (singleton/request/prototype) và cyclic dependency có hợp lệ?
5. Có được phép truy cập constructor (module boundary, visibility) không?

### Chọn dependency theo type và qualifier

Khi một interface có hai implementation:

~~~java
interface Notifier { void send(String text); }

class EmailNotifier implements Notifier { /* ... */ }
class AuditNotifier implements Notifier { /* ... */ }
~~~

Chỉ nhìn `Notifier.class` không đủ để chọn một bean. DI framework có thể dùng **qualifier** hoặc tên bean:

~~~java
class Alerts {
    Alerts(@Named("audit") Notifier notifier) { /* ... */ }
}
~~~

Trong ví dụ này `@Named` là annotation ý tưởng/annotation tự định nghĩa trong chương trình học; production frameworks thường có annotation, scope và lifecycle riêng. **Không mặc nhiên cho rằng tên tham số Java `notifier` tương đương với bean name `"audit"`.**

Một DI container nghiêm túc cần phát diagnostic khi có nhiều candidate và không có qualifier, thay vì chọn “phần tử đầu tiên” từ `Map` hay Reflection (thứ tự như vậy không phải business rule). Cần xem xét recursion/circular dependencies, thread safety, scopes, disposal và test startup.

### Constructor injection không nên phụ thuộc `arg0`

Constructor:

~~~java
Service(@Named("mainRepository") Repository repository) { ... }
~~~

có qualifier explicit nên bản mini-container ở mục 8 resolve bằng `@Named` và `getType()`. Nếu dùng fallback dựa tên source, bắt buộc kiểm `isNamePresent()` và đặt behavior rõ khi metadata thiếu; với public libraries, annotation explicit thường ít nhạy với refactor tên.

**Quan trọng:** DI runtime không tự validate dữ liệu HTTP. Một instance `UserService` hợp lệ vẫn có thể nhận `id` không hợp lệ nếu layer binder/validation bỏ qua kiểm tra.

## 6. Tài liệu API: metadata là điểm xuất phát, không phải toàn bộ hợp đồng

Một tài liệu endpoint không chỉ có `String id, int repeat`. Với mỗi parameter public, thông tin tối thiểu có thể gồm:

- **Tên external:** tên route/query/header/body field, có thể khác tên Java.
- **Vị trí:** `path`, `query`, `header`, `cookie` hoặc body schema (tuỳ giao thức và OpenAPI).
- **Required:** bắt buộc/tùy chọn và mặc định nếu có.
- **Kiểu/schema:** string, integer, enum, array/object, format, constraints.
- **Mô tả:** ý nghĩa, giới hạn, mẫu giá trị và policy deprecation.
- **Vấn đề bảo mật:** input được phép lộ thông tin gì, có yêu cầu auth và hạn chế nào.

Reflection giúp lấy raw type, generic type và annotation có retention thích hợp. Nhưng **không thể tự suy ra** vị trí HTTP, text mô tả, policy required/nullable, định dạng UUID hoặc phân quyền chỉ từ `Parameter.getType()`. Những phần này cần contract/annotation/schema bổ sung.

### OpenAPI mô tả rõ thay vì dựa vào suy đoán

Ví dụ hợp đồng OpenAPI 3.1 (trích đoạn YAML minh họa, không phải toàn bộ document):

~~~yaml
paths:
  /users/{id}:
    get:
      summary: Lookup a user
      parameters:
        - name: id
          in: path
          required: true
          description: User identifier
          schema:
            type: string
        - name: repeat
          in: query
          required: false
          description: Repetitions, default 1
          schema:
            type: integer
            minimum: 1
            maximum: 3
            default: 1
~~~

Theo OpenAPI, parameter `in: path` **phải có `required: true`**; placeholder trong route phải khớp tên parameter. Một query parameter có thể optional theo contract nhưng runtime binder **phải dùng default/nullable handling tương ứng**. Đừng lấy ví dụ YAML này gắn vào method trong mục 8 mà bỏ qua khác biệt: mục 8 minh họa **hai query parameters đều required**, còn YAML minh họa thêm khả năng path+optional query.

Các công cụ OpenAPI của framework có thể đọc annotation và model rồi sinh spec, nhưng output generated cần được review/test như một artifact API. **Không** coi annotation source là tài liệu đủ nếu contract runtime đã khác hoặc generator không đọc một annotation tùy chỉnh.

### Kiểm tính nhất quán giữa binder, DI và docs

Một lỗi rất thực tế: handler dùng `@QueryKey("id")` nhưng spec lại mô tả `userId`. Client sẽ gửi `userId`, binder tìm `id` rồi trả lỗi. CI có thể so sánh metadata từ handler với parameter names trong spec và test một request thực.

Tương tự, DI qualifier `"repository"` là tên nội bộ của object graph, **không** phải HTTP parameter. Đừng trộn các annotation target `CONSTRUCTOR`/`PARAMETER` dành cho injection với annotation dành cho user input.

## 7. Mô hình ba nhánh sử dụng chung metadata

~~~text
                          Java Method/Constructor
                                   │
                   Executable.getParameters()
                                   │
                 Parameter[type, name, annotations]
                     /             |             \
                    /              |              \
             HTTP binder       DI container      API docs
                |                  |                |
        external key + input    bean type + key   name/location/
        conversion/validation   scopes/lifecycle  schema/required
                |                  |                |
          method argument      constructor arg   OpenAPI contract
                    \              /
                    business method
~~~

Điểm chung là đọc metadata ở **đúng executable**; điểm khác nằm ở policy. Binder nhận dữ liệu không tin cậy; DI resolve collaborator được kiểm soát; document generator tạo mô tả tĩnh cần đối chiếu với runtime behavior.

**Không nên viết một helper “bind everything” áp dụng mọi annotation và loại object**: đó là đường dẫn tới mass assignment, dependency injection ngoài ý muốn, thông tin tài liệu sai hoặc security regressions. Dùng các abstraction tách biệt nhưng chia sẻ cách đọc `Parameter[]` một cách kiểm thử được.

## 8. Chương trình hoàn chỉnh: binding + constructor DI + API description

Tạo một file UTF-8 tên **`ParameterIntegrationDemo.java`**. Chương trình chỉ dùng Java SE: các annotation học tập, một container nhỏ để resolve constructor, một binder query `String/int`, và một helper tạo đoạn mô tả parameter. Nó không mở HTTP server và không thay thế framework production.

~~~java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.lang.reflect.Constructor;
import java.lang.reflect.Method;
import java.lang.reflect.Parameter;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

public final class ParameterIntegrationDemo {

    @Retention(RetentionPolicy.RUNTIME)
    @Target(ElementType.PARAMETER)
    public @interface QueryKey {
        String value();
    }

    @Retention(RetentionPolicy.RUNTIME)
    @Target(ElementType.PARAMETER)
    public @interface Description {
        String value();
    }

    @Retention(RetentionPolicy.RUNTIME)
    @Target(ElementType.CONSTRUCTOR)
    public @interface Inject {
    }

    @Retention(RetentionPolicy.RUNTIME)
    @Target(ElementType.PARAMETER)
    public @interface Named {
        String value();
    }

    interface UserRepository {
        String findName(String id);
    }

    static final class MemoryUserRepository implements UserRepository {
        @Override
        public String findName(String id) {
            return "user-" + id;
        }
    }

    static final class UserService {
        private final UserRepository repository;

        @Inject
        public UserService(@Named("repo") UserRepository repository) {
            this.repository = repository;
        }

        public String repeatName(String id, int repeat) {
            if (repeat < 1 || repeat > 3) {
                throw new IllegalArgumentException("repeat must be 1..3");
            }
            StringBuilder output = new StringBuilder();
            for (int i = 0; i < repeat; i++) {
                if (i > 0) {
                    output.append("|");
                }
                output.append(repository.findName(id));
            }
            return output.toString();
        }
    }

    static final class UserController {
        private final UserService service;

        @Inject
        public UserController(@Named("service") UserService service) {
            this.service = service;
        }

        public String show(
                @QueryKey("id") @Description("User identifier") String id,
                @QueryKey("repeat") @Description("Repetitions") int repeat) {
            return service.repeatName(id, repeat);
        }
    }

    static final class MiniContainer {
        private final Map<String, Object> dependencies =
            new HashMap<String, Object>();

        void register(String key, Object dependency) {
            if (dependencies.containsKey(key)) {
                throw new IllegalArgumentException("duplicate bean: " + key);
            }
            dependencies.put(key, dependency);
        }

        <T> T create(Class<T> type) throws Exception {
            Constructor<?> selected = null;
            for (Constructor<?> c : type.getDeclaredConstructors()) {
                if (c.isAnnotationPresent(Inject.class)) {
                    if (selected != null) {
                        throw new IllegalArgumentException(
                            "ambiguous inject constructors: " + type.getName());
                    }
                    selected = c;
                }
            }
            if (selected == null) {
                throw new IllegalArgumentException(
                    "missing @Inject constructor: " + type.getName());
            }

            Parameter[] parameters = selected.getParameters();
            Object[] args = new Object[parameters.length];

            for (int i = 0; i < parameters.length; i++) {
                Named named = parameters[i].getAnnotation(Named.class);
                if (named == null) {
                    throw new IllegalArgumentException(
                        "missing @Named qualifier at parameter " + i);
                }

                Object dep = dependencies.get(named.value());
                if (dep == null ||
                        !parameters[i].getType().isInstance(dep)) {
                    throw new IllegalArgumentException(
                        "missing or wrong bean: " + named.value());
                }
                args[i] = dep;
            }

            return type.cast(selected.newInstance(args));
        }
    }

    static String externalName(Parameter parameter) {
        QueryKey q = parameter.getAnnotation(QueryKey.class);
        if (q != null && !q.value().isEmpty()) {
            return q.value();
        }
        if (parameter.isNamePresent()) {
            return parameter.getName();
        }
        throw new IllegalStateException(
            "parameter name unavailable; use @QueryKey or -parameters");
    }

    static Object[] bind(Method method, Map<String, String> input) {
        Parameter[] parameters = method.getParameters();
        Object[] args = new Object[parameters.length];

        for (int i = 0; i < parameters.length; i++) {
            Parameter p = parameters[i];
            String key = externalName(p);
            String raw = input.get(key);

            if (raw == null || raw.trim().isEmpty()) {
                throw new IllegalArgumentException(
                    "missing query parameter: " + key);
            }

            if (p.getType() == String.class) {
                args[i] = raw;
            } else if (p.getType() == int.class) {
                try {
                    args[i] = Integer.valueOf(raw);
                } catch (NumberFormatException ex) {
                    throw new IllegalArgumentException(
                        "invalid integer for: " + key, ex);
                }
            } else {
                throw new IllegalArgumentException(
                    "unsupported type: " + p.getType().getTypeName());
            }
        }
        return args;
    }

    static String describe(Method method) {
        List<String> result = new ArrayList<String>();
        for (Parameter p : method.getParameters()) {
            Description desc = p.getAnnotation(Description.class);
            String text = desc == null ? "(no description)" : desc.value();

            result.add(externalName(p) + ":"
                + p.getType().getSimpleName() + " - " + text);
        }
        return String.join("; ", result);
    }

    public static void main(String[] args) throws Exception {
        MiniContainer container = new MiniContainer();
        container.register("repo", new MemoryUserRepository());

        UserService service = container.create(UserService.class);
        container.register("service", service);
        UserController controller = container.create(UserController.class);

        Method handler = UserController.class.getDeclaredMethod(
            "show", String.class, int.class);

        Map<String, String> query = new HashMap<String, String>();
        query.put("id", "42");
        query.put("repeat", "2");

        System.out.println("di: "
            + controller.getClass().getSimpleName());

        Parameter first = handler.getParameters()[0];
        System.out.println("parameter: "
            + first.getName() + "/" + first.isNamePresent());

        Object[] bound = bind(handler, query);
        System.out.println("response: "
            + handler.invoke(controller, bound));

        System.out.println("api: " + describe(handler));

        Map<String, String> invalid = new HashMap<String, String>();
        invalid.put("id", "42");

        try {
            bind(handler, invalid);
        } catch (IllegalArgumentException ex) {
            System.out.println("rejected: " + ex.getMessage());
        }
    }
}
~~~

**Biên dịch và chạy** trên một JDK được duy trì có hỗ trợ `--release 8`:

~~~text
javac --release 8 -parameters -encoding UTF-8 ParameterIntegrationDemo.java
java ParameterIntegrationDemo
~~~

**Stdout kỳ vọng — chính xác 5 dòng:**

~~~text
di: UserController
parameter: id/true
response: user-42|user-42
api: id:String - User identifier; repeat:int - Repetitions
rejected: missing query parameter: repeat
~~~

### Giải thích từng dòng

1. Container tìm constructor có `@Inject` ở `UserService` và `UserController`, đọc `@Named` và `getType()` để cung cấp đúng collaborator. Kết quả tạo được `UserController`.
2. Handler `show` được build với `-parameters` nên `getName()` trả `id` và `isNamePresent()` là true.
3. Binder đọc hai `@QueryKey`, ánh xạ chuỗi `"42"` và `"2"` thành `String` và `int`. Method `show` gọi service và trả `user-42|user-42`. Kết quả không phụ thuộc vào thứ tự iteration của `HashMap` vì binder duyệt **thứ tự `Parameter[]`**.
4. Mô tả API được tạo từ tên explicit, raw types và `@Description`; đó là **đoạn mô tả học tập**, chưa phải OpenAPI document đầy đủ.
5. Input thiếu `repeat` bị từ chối trước method invocation bằng `IllegalArgumentException`; chương trình in lỗi có ý nghĩa.

**Nếu bỏ `-parameters`:** phần binder và docs vẫn hoạt động vì cả hai tham số của handler có `@QueryKey` explicit; dòng `parameter: id/true` sẽ đổi thành dạng `parameter: arg0/false` trên một build `javac` thông thường thiếu metadata tên. Đây là minh chứng cho giá trị của **tách API external name khỏi tên Java source**.

### Giới hạn cố ý của ví dụ

- Chỉ xử lý `String` và `int`; binder production cần converters/schema và xử lý multivalue, default, optional, body, validation.
- Không có HTTP routing, encoding, request size limits, authorization, authentication hoặc exception-to-HTTP mapping.
- Container chỉ nhận những dependency đã register bằng qualifier, tạo object theo thứ tự trong `main`; không có lifecycle scopes, provider, proxy, async hoặc cycle detection đầy đủ.
- `Method.invoke` có thể gói exception từ handler trong `InvocationTargetException`; framework production phải unwrap/map lỗi theo policy, không lộ stack trace ra response.
- `describe` trả một chuỗi đơn giản, không suy ra path/query/required/schema; những thuộc tính đó cần contract riêng.
- Các annotation tự định nghĩa ở đây **không phải** annotation chuẩn Spring/Jakarta/OpenAPI. Khi xây ứng dụng thật, ưu tiên cơ chế chính thức trong stack đang sử dụng và kiểm version phù hợp.

## 9. Đọc generic metadata: khi `getType()` là chưa đủ

Với method:

~~~java
void search(java.util.List<String> ids) { ... }
~~~

`Parameter.getType()` chỉ cho `List.class`. Nếu binder muốn convert nhiều input thành `List<String>`, cần phân tích `getParameterizedType()`, thường là `ParameterizedType` với actual type arguments, hoặc cơ chế type token/type resolver của framework.

~~~java
java.lang.reflect.Type type = parameter.getParameterizedType();

if (type instanceof java.lang.reflect.ParameterizedType) {
    java.lang.reflect.ParameterizedType parameterized =
        (java.lang.reflect.ParameterizedType) type;
    java.lang.reflect.Type[] arguments =
        parameterized.getActualTypeArguments();
    // Ví dụ: arguments[0] có thể là String.class.
}
~~~

Đây là **fragment**, không phải chương trình độc lập. Không cast vô điều kiện vì `Type` còn có thể là `TypeVariable`, `WildcardType`, `GenericArrayType` hoặc `Class<?>`. Type erasure vẫn áp dụng; generic metadata **không tự xác thực** rằng mọi phần tử thật trong một collection runtime là `String`.

### Type-use annotation và declaration annotation

~~~java
void process(
    @QueryKey("ids")
    java.util.List<@ElementHint String> ids
) { ... }
~~~

- `@QueryKey` là annotation trên **declaration parameter**; đọc bằng `Parameter.getAnnotation(QueryKey.class)` khi retention runtime.
- `@ElementHint` là annotation trên **type argument `String`** nếu target `TYPE_USE`; đọc bằng `Parameter.getAnnotatedType()`, xuống `AnnotatedParameterizedType.getAnnotatedActualTypeArguments()[0]` và truy xuất annotation tại node đó.
- Đừng nhầm annotation gắn vào source code với validation được JVM tự thực thi. Phải có checker/validator đọc metadata và áp dụng quy tắc riêng.

Trong DI, parameter như `List<Plugin>` có thể yêu cầu một tập bean theo generic type, khác với một query parameter `List<String>` từ HTTP. Không dùng một converter chung chỉ vì cả hai là `List`.

## 10. Những trường hợp đặc biệt khi introspection

### Parameter annotations không “thừa kế” giống method dispatch

Nếu class thực thi interface và override method, `Parameter.getAnnotations()` trên method interface và method implementation có thể **khác nhau**. Parameter annotations không tự động được JVM Reflection kế thừa từ parameter tương ứng của method bị override. Một framework có thể có cơ chế merged annotations riêng, nhưng không phải `Parameter` mặc nhiên thực hiện.

Ví dụ:

~~~java
interface Endpoint {
    void execute(@QueryKey("id") String input);
}

class EndpointImpl implements Endpoint {
    @Override
    public void execute(String input) { }
}
~~~

Khi tra `Endpoint.class.getMethod("execute", String.class)`, parameter annotation tồn tại trên declaration interface. Khi tra `EndpointImpl.class.getMethod("execute", String.class)`, parameter của implementation có thể không có `@QueryKey`. Một binder cần có **quy tắc rõ ràng** chọn metadata từ interface hay implementation; nếu trộn, phải có test khi override/bridge methods.

### Bridge methods, overload và generic specialization

Compiler có thể sinh **bridge method** để bảo vệ polymorphism sau type erasure. `Method.isBridge()` và `Method.isSynthetic()` giúp phát hiện. Khi scan mọi `getDeclaredMethods()`, nếu đăng ký endpoint bừa, bạn có thể tạo hai route hoặc lấy annotation từ executable không mong muốn. Hãy xác định method nghiệp vụ, loại trừ bridge/synthetic khi phù hợp, và dùng framework metadata resolution đã được kiểm chứng.

Tương tự, overload `show(String)` và `show(String,int)` là hai executable riêng. API doc generator/binder phải có routing và schema phân biệt, không chọn theo tên method đơn thuần.

### Inner classes, enums, records và generated code

Một constructor của non-static inner class có thể có tham số enclosing instance tại JVM level; enum và code generated có signature/flags đặc biệt. `Parameter.isImplicit()`, `isSynthetic()` và `isNamePresent()` trả thông tin khác nhau; **đừng bỏ `arg0` theo heuristic**. Với record (Java 16+), canonical constructor có quy tắc metadata riêng; không suy từ ví dụ class thông thường rằng tất cả parameter name đều cần cùng lựa chọn compile flag.

Nếu một framework hỗ trợ record/data classes, phải test thực tế constructor binding và doc generation trên mức Java/framework tương ứng. Tránh dùng những thư viện hoặc cách parse debug bytecode đã không còn được duy trì.

### Java modules và accessibility

Khi handler/constructor không public hoặc chạy trong named module, `getDeclaredConstructor` và `setAccessible(true)` không mặc định cho phép bỏ qua đóng gói module. Có thể gặp `InaccessibleObjectException` hoặc `IllegalAccessException`. Đừng dựa vào các workaround mở toàn bộ `java.base` hoặc private internals; khai báo module `opens` phù hợp cho framework được phép reflection, hoặc dùng public API/constructor injection chuẩn.

### Compiler flag và packaged artifact

Khi chạy `javap -v`, có thể nhìn thấy `MethodParameters` nếu tên được ghi. Nhưng build shading/obfuscation có thể đổi tên hoặc bỏ metadata; hãy kiểm **artifact cuối cùng**, không chỉ class từ `target/classes` hoặc IDE.

## 11. Kiểm thử end-to-end ba chức năng

Một bộ test đúng nên kết hợp:

| Nhóm | Ca kiểm | Kỳ vọng |
| --- | --- | --- |
| Metadata | Build với `-parameters` | `isNamePresent()==true` cho method thường được compile đúng |
| Metadata | Build không flag | Không nhầm `argN` thành tên external |
| Binder | Query đủ `id`/`repeat` | Convert và invoke đúng thứ tự |
| Binder | Thiếu `repeat` | Trả lỗi đầu vào; không invoke handler |
| Binder | `repeat=abc` | Error kiểu dữ liệu rõ, không bị 500 không kiểm soát |
| Binder | `repeat=0` hoặc `repeat=99` | Business/validation policy từ chối |
| Binder | Giá trị nhạy cảm/không được phép | Không log secret, không bypass authorization |
| DI | Có đúng dependency `@Named("repo")` | Constructor injection pass |
| DI | Thiếu dependency hoặc wrong type | Fail-fast diagnostic |
| DI | Hai candidates cùng type, không qualifier | Báo ambiguity thay vì lựa chọn tùy tiện |
| API docs | Tên `id`, `repeat` trong spec | Khớp tên public binder đọc |
| API docs | `path` parameter | Required true và khớp placeholder |
| API docs | Đổi tên Java source, giữ explicit key | External API contract không đổi |
| API docs | Cập nhật required/default/range | Runtime validation và spec cùng thay đổi |
| Packaged build | Build artifact + reflection scan | Metadata không mất do obfuscation/bytecode transforms |

### Hai test quan trọng nhất cho an toàn

**1. Contract test:** Gửi request mẫu qua router/framework thật, assert response/error và đối chiếu request parameters được document. Một unit test chỉ gọi `bind` mà không qua HTTP pipeline không kiểm được routing, content-type, validation, security filter hoặc error mapping.

**2. Metadata canary:** Có một test biên dịch fixture không `-parameters` để chắc chắn code xử lý thiếu tên đúng như contract (sử dụng annotation explicit hoặc fail-fast). Có thêm test positive trên packaged jar với flag để phát hiện compiler task cấu hình sai.

Đối với DI, ưu tiên integration test **startup context** thật, nhất là khi scope, qualifier, circular dependencies và module boundaries có thể gây lỗi chỉ ở runtime.

## 12. Quy tắc thực dụng khi tích hợp framework

### Web frameworks

Các framework web như Spring MVC, Jakarta REST và các lựa chọn Java hiện đại có annotations và resolvers riêng cho query/path/header/body binding. Đừng tự gán một ý nghĩa thống nhất cho `@RequestParam`, `@QueryParam`, `@PathParam` hoặc annotations tương tự: chúng thuộc **hệ API/framework khác nhau** và có phiên bản/vòng đời riêng. Chọn framework đang được hỗ trợ, đọc contract của nó, rồi viết test cho required, default, conversion và validation.

Spring Framework hiện đại dùng reflection-backed parameter name discovery cho nhiều trường hợp; tài liệu nâng cấp 6.x yêu cầu lưu parameter names khi dựa vào tên Java. Việc dùng explicit annotation value có thể giúp hợp đồng ổn định hơn nhưng không thay thế test trên chính framework.

### Jakarta CDI / DI containers

Jakarta CDI và các DI container hiện đại có quy định injection point, qualifier, scope và lifecycle. `@Inject` trong ví dụ học tập là **annotation tự định nghĩa**, không phải `jakarta.inject.Inject`; đừng nhầm tên giống nhau với behavior tự động. Container thật cần resolution rules, conflict diagnostics và lifecycle scope đúng theo spec.

Constructor injection thường giúp dependency rõ và dễ test, nhưng không đủ để bảo đảm mọi graph hợp lệ. Nếu container cho phép field/method injection, các đường đó cũng có metadata riêng. Kiểm quyết định thiết kế dựa trên khuyến nghị của framework đang dùng, không chỉ viết `@Inject` là xong.

### OpenAPI generator

Nếu dùng generator OpenAPI, kiểm trên output tài liệu sau khi application build/start thay vì tin rằng annotation đã được phát hiện. Đối chiếu `paths`, method HTTP, parameter `name`/`in`, schema, required/default, enum/range và security declarations với routing thật.

Một hợp đồng có `in: path` mà `required: false` là **không hợp lệ** theo OpenAPI. Một query parameter có default trong spec nhưng binder thực tế báo lỗi khi thiếu là **bất đồng contract**. Tất cả phải có CI test tránh phát hành docs sai.

### Không dùng metadata làm ranh giới bảo mật

Reflection có thể thấy tên/type/annotations nhưng không thể tự quyết định user có quyền truy xuất `id`. Authorization phải nằm ở policy/biz layer, và parameter không được dùng để tự inject privileged service dựa trên chuỗi do client cung cấp. Binder và DI phải giữ **ranh giới tin cậy tách biệt**.

## 13. Lỗi thường gặp và cách sửa

### 13.1. Tên `arg0` trở thành query key

**Sai:** luôn gọi `p.getName()` rồi lấy `request.getParameter(name)`. Khi thiếu `-parameters`, code có thể tìm key `arg0` thay vì `id`.

**Đúng:** ưu tiên annotation explicit; nếu dùng fallback theo tên, kiểm `isNamePresent()`. Thêm test trên jar deploy và compile flag rõ ràng.

### 13.2. Dựa vào debug info thay `MethodParameters`

`-g` phục vụ debug, không phải hợp đồng lưu tên cho `Executable.getParameters()`. Hãy cấu hình `-parameters` tại module tạo class cần binding. Không dựa vào một thủ thuật bytecode đã lỗi thời của framework trước đây.

### 13.3. Diễn giải `@Named` thành tên request

Qualifier trong DI chọn dependency của container, không phải tên query/body của client. Nếu dùng một annotation cho cả hai lĩnh vực mà không có contract rõ, dễ vô tình nhận input ngoài ý muốn hoặc lỗi ambiguity.

### 13.4. Bind kiểu tuỳ ý bằng `Class.forName(userInput)`

Đây là thiết kế rủi ro: client có thể điều khiển class được load/khởi tạo. Binder phải dùng whitelist converter cho các loại được schema chấp nhận; DI không được đọc bean class từ dữ liệu HTTP không tin cậy.

### 13.5. Tự động coi mọi `Integer` là optional

Nullability, required, defaults và validation là các khái niệm contract, không suy ra hoàn toàn từ `Class<?>`. Đặc biệt `int` không chứa null; cần policy và test cho dữ liệu thiếu, rỗng và sai kiểu.

### 13.6. Mất generic arguments

`getType()` không thể cho biết `List<String>` hay `List<Long>`. Khi schema/converter cần phần tử, dùng `getParameterizedType()` và type-resolution API đúng ngữ cảnh. Đừng cast mọi `Type` thành `Class<?>`.

### 13.7. Nhầm parameter declaration annotation với type-use

`Parameter.getAnnotations()` không duyệt hết annotations nằm trên generic arguments/array components. Dùng `getAnnotatedType()` khi cần metadata trên lần dùng kiểu, kèm công cụ diễn giải semantics phù hợp.

### 13.8. Bỏ qua method override và bridge

Annotation ở method interface không tự trở thành parameter annotation của overriding method. Bridge/synthetic methods có thể xuất hiện khi scan reflection. Cần quy tắc merge/resolve/skip rõ ràng và test trên class thật.

### 13.9. Sinh tài liệu từ raw type rồi tuyên bố đầy đủ

`String` không tự nói đây là query, header, path, email, UUID hay secret. Tài liệu API cần thông tin location, constraints, required, description, examples, security. Metadata cơ bản chỉ là một nguồn.

### 13.10. Đổi tên source làm API vỡ âm thầm

Đổi `id` thành `customerId` mà binder dựa vào `getName()` có thể làm thay đổi external key dù bytecode descriptor method gần như không đổi. Tên explicit trong annotation/schema giúp contract ổn định hơn; vẫn cần regression test request cũ.

### 13.11. Chọn constructor đầu tiên của Reflection

`getDeclaredConstructors()[0]` không phải “constructor chính” được bảo đảm. Dùng annotation, quy tắc chọn được document hoặc duy nhất constructor theo framework; báo rõ khi ambiguous.

### 13.12. Docs đúng, runtime sai (hoặc ngược lại)

OpenAPI generator có thể đọc annotations khác nguồn với runtime binder. Tạo test so sánh spec với request thật; thêm diff/breaking-change review khi route, parameter key, required/default hoặc schema thay đổi.

## 14. Bài tập và đáp án định hướng

**Bài 1 — Tên source so với public key.** Biên dịch ví dụ mục 8 với và không `-parameters`. Quan sát dòng `parameter` đổi từ `id/true` sang `arg0/false`; các dòng response/docs vẫn ổn nhờ `@QueryKey("id")` và `@QueryKey("repeat")`.

**Bài 2 — Binding thiếu input.** Gửi map chỉ có `id=42`. Dự kiến binder từ chối `repeat` trước khi gọi `show`. Thêm test xác nhận service không bị gọi khi input thiếu.

**Bài 3 — Conversion error.** Thử `repeat=abc` và `repeat=0`. Trường hợp đầu bị từ chối khi parse; trường hợp sau parse hợp lệ nhưng `UserService.repeatName` từ chối bởi business rule. Thiết kế error mapping riêng cho từng nhóm lỗi.

**Bài 4 — Qualifier.** Đổi `@Named("repo")` thành `@Named("other")` mà không register dependency. Dự kiến container báo thiếu bean; không tự chọn object đầu tiên.

**Bài 5 — Wrong type.** Register key `"repo"` với một `String` thay vì `UserRepository`. Container dùng `isInstance` để từ chối, tránh lỗi cast muộn khi gọi service.

**Bài 6 — API docs contract.** Thay `@Description("User identifier")` thành mô tả rõ format và giới hạn; update spec và test response. Giải thích vì sao Java `String.class` không giúp tự suy ra format.

**Bài 7 — Tên external bền vững.** Đổi tên source parameter `id` thành `userId` nhưng giữ `@QueryKey("id")`. Response/docs vẫn dùng `id`. Vì sao tên Java source không nên được xem là public HTTP contract mặc định?

**Bài 8 — Generics.** Thêm handler nhận `List<String> ids`. Viết converter cho input nhiều giá trị dựa trên `getParameterizedType()`; từ chối kiểu phần tử không hỗ trợ thay vì tự ép vào Object.

**Bài 9 — Method override.** Đặt annotation mapping trên parameter ở interface, bỏ annotation trong implementation. So sánh reflection của cả hai methods và xác định rule metadata merging mà framework phải thực hiện nếu muốn dùng annotation ở interface.

**Bài 10 — OpenAPI path vs query.** Viết spec route `/users/{id}` với `id` là path required, `repeat` là query optional có default 1. Viết binder tương ứng và contract test cho request không có `repeat`.

**Bài 11 — Metadata trong jar.** Build module dùng `-parameters`, đóng gói và chạy reflection assertion trên jar cuối cùng. Sau đó thử version không flag; test phải phát hiện `isNamePresent()==false` hoặc dùng annotation explicit.

**Bài 12 — Thiết kế an toàn.** Xây checklist phân tách external input binding, internal DI resolution và API spec generation; xác định nơi validate, authorize, kiểm dependency ambiguity và ngăn rò rỉ dữ liệu nhạy cảm.

**Tiêu chí đạt:** Bạn giải thích được `Parameter` phục vụ cả binder/DI/docs nhưng cần policy khác nhau; chạy chương trình `ParameterIntegrationDemo.java` với năm dòng output; tránh dùng `argN` làm API key, xử lý parse/validation, chọn DI qualifier đúng và biết đối chiếu OpenAPI với runtime.

## 15. Checklist triển khai trong dự án thực tế

- [ ] Xác định JDK/framework versions **đang được hỗ trợ**, không dùng APIs/tooling đã bị loại bỏ.
- [ ] Các module có logic dựa tên Java được compile và đóng gói với `-parameters`; test `isNamePresent()` trên artifact thực.
- [ ] Public HTTP keys có hợp đồng ổn định (annotation explicit hoặc schema source-of-truth).
- [ ] Phân biệt request `query`, `path`, `header`, body và các parameter injection nội bộ.
- [ ] Chỉ convert các kiểu được schema/whitelist cho phép; bắt lỗi parse, null, quá dài và multivalue.
- [ ] Required/default/validation/authorization do runtime thực thi và có test.
- [ ] Constructor/bean resolution có quy tắc không mơ hồ, qualifier và scope chính xác.
- [ ] Không biến untrusted input thành bean/class lookup không được giới hạn.
- [ ] Dùng `getParameterizedType()` khi cần generic schema; dùng `getAnnotatedType()` khi cần type-use annotations.
- [ ] Xử lý bridge methods, overload, inherited/interface parameter annotations theo framework contract.
- [ ] OpenAPI spec được kiểm tên/location/schema/required/default với runtime binder.
- [ ] CI có contract test request thật, context-startup DI test và metadata canary thiếu `-parameters`.
- [ ] Khi nâng compiler/framework, chạy clean build và kiểm generated docs/packaged class metadata.
- [ ] Không lộ stack trace, secrets, access tokens hoặc giá trị nhạy cảm qua error/docs/logging.

## 16. Tài liệu chuẩn và tham khảo đang còn áp dụng

- Java SE Reflection API, `java.lang.reflect.Parameter`: https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/reflect/Parameter.html
- Java SE Reflection API, `java.lang.reflect.Executable`: https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/reflect/Executable.html
- Java SE Reflection API, `java.lang.reflect.AnnotatedType` và `ParameterizedType`: https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/reflect/package-summary.html
- Java SE `javac` manual, `-parameters`: https://docs.oracle.com/en/java/javase/25/docs/specs/man/javac.html
- JVM Specification, `MethodParameters` classfile attribute: https://docs.oracle.com/javase/specs/jvms/se25/html/jvms-4.html#jvms-4.7.24
- OpenAPI Specification 3.1, Parameter Object và path parameter requirements: https://spec.openapis.org/oas/v3.1.2.html
- Spring Framework, hướng dẫn nâng cấp 6.x về parameter name retention: https://github.com/spring-projects/spring-framework/wiki/Upgrading-to-Spring-Framework-6.x
- Jakarta Dependency Injection API và CDI hiện hành: https://jakarta.ee/specifications/dependency-injection/ và https://jakarta.ee/specifications/cdi/

**Ghi nhớ:** `Parameter` cung cấp **metadata kỹ thuật**, không thay thế hợp đồng ứng dụng. Binding cần policy input/validation/authorization; DI cần qualifier/lifecycle; tài liệu API cần location/schema/required/description. Khi các chức năng dùng chung chữ ký Java, hãy kiểm nguồn tên tham số, cấu hình compiler, phiên bản framework và sự thống nhất giữa runtime với tài liệu trước khi phát hành.