# Định nghĩa kiểu annotation bằng `@interface` trong Java

## 1. Annotation type là gì?

**Annotation** trong Java là thông tin mô tả (*metadata*) gắn vào khai báo chương trình, chẳng hạn class, method, field hoặc parameter; từ Java 8 còn có annotation áp dụng tại một số vị trí sử dụng kiểu (*type use*). Một annotation có thể được compiler, công cụ sinh mã, framework hoặc chương trình thông qua reflection đọc và xử lý.

**Annotation type** là bản định nghĩa cho các annotation cụ thể. Java dùng từ khóa ghép `@interface` để khai báo kiểu này:

```java
@interface Author {
    String name();
}
```

Khai báo trên tạo ra một annotation type có tên `Author` với một phần tử bắt buộc tên `name`. Sau đó có thể sử dụng:

```java
@Author(name = "An")
class BookService {
}
```

Ở ví dụ này, `@interface Author` **định nghĩa cấu trúc**; `@Author(name = "An")` **cung cấp giá trị cho một lần sử dụng** cấu trúc ấy. Dấu `@` khi dùng annotation và cụm `@interface` khi định nghĩa là hai vai trò khác nhau.

Annotation thường phục vụ cấu hình và công cụ, ví dụ đánh dấu method kiểm thử, mô tả quy tắc ánh xạ URL hoặc cung cấp metadata cho bộ xử lý annotation. **Bản thân việc gắn annotation không tự động tạo hành vi mới**: phải có compiler, annotation processor, framework hoặc mã Java đọc annotation và thực thi logic tương ứng.

## 2. Cấu trúc khai báo cơ bản

Cú pháp cốt lõi:

```java
@interface TenAnnotation {
    KieuTraVe tenPhanTu();
    KieuTraVe tenPhanTuKhac() default giaTriMacDinh;
}
```

Các thành phần:

- `@interface` là cú pháp khai báo một *annotation interface* (thường gọi là *annotation type*).
- `TenAnnotation` là tên kiểu, tuân thủ quy tắc Java identifier; theo quy ước đặt tên kiểu bằng PascalCase.
- `tenPhanTu()` là một **annotation element**: trông giống method không tham số nhưng dùng để mô tả một giá trị annotation.
- Kiểu trả về của element xác định kiểu giá trị hợp lệ tại nơi sử dụng.
- `default` cung cấp giá trị mặc định; element không có `default` cần được cung cấp khi sử dụng annotation.
- Dấu `;` kết thúc từng khai báo element; không có method body.

Ví dụ:

```java
@interface JobInfo {
    String code();
    int maxRetries() default 3;
    boolean active() default true;
}
```

Sử dụng:

```java
@JobInfo(code = "IMPORT")
class ImportJob {}

@JobInfo(code = "EXPORT", maxRetries = 5, active = false)
class ExportJob {}
```

`code()` là bắt buộc, còn `maxRetries()` và `active()` có thể được bỏ qua vì đã có mặc định. Việc bỏ qua không khiến Java tự suy ra giá trị từ tên field hoặc biến khác.

### So sánh nhanh với interface thông thường

```java
interface Runner {
    void run();
}

@interface RunInfo {
    String name();
}
```

| Tiêu chí | `interface Runner` | `@interface RunInfo` |
|---|---|---|
| Mục đích | Khai báo hợp đồng hành vi để class implement | Định nghĩa kiểu metadata có các element |
| Sử dụng | `class X implements Runner` | `@RunInfo(name = "demo")` |
| Thành phần tiêu biểu | Abstract/default/static methods | Annotation elements với kiểu và mặc định bị giới hạn |
| Tạo thể hiện trực tiếp | Không `new Runner()`; có thể tạo class implement | Không `new RunInfo()`; thông thường compiler biểu diễn annotation và công cụ đọc nó |
| Quan hệ với `Annotation` | Không tự động là annotation type | Annotation interface ngầm có `java.lang.annotation.Annotation` là superinterface |

Annotation type là một dạng interface chuyên biệt, nhưng **không khai báo `extends Annotation`** và cũng không khai báo `implements`. Viết `@interface X extends Annotation` là sai cú pháp ngôn ngữ. Annotation interface không có tham số kiểu (`@interface Meta<T>` là không hợp lệ).

## 3. Các kiểu element được Java cho phép

Kiểu trả về hợp lệ của một annotation element thuộc một trong những nhóm sau:

1. Kiểu nguyên thủy: `boolean`, `byte`, `short`, `int`, `long`, `char`, `float`, `double`.
2. `String`.
3. `Class` hoặc dạng `Class<?>` / `Class<? extends SomeType>` thích hợp.
4. Một kiểu `enum`.
5. Một kiểu annotation khác.
6. Mảng **một chiều** của các kiểu trên.

Ví dụ độc lập:

```java
enum Severity {
    LOW, MEDIUM, HIGH
}

@interface Endpoint {
    String path();
    String[] roles() default {};
    int timeoutSeconds() default 30;
    Severity severity() default Severity.LOW;
    Class<?> handler() default Object.class;
}

@interface Module {
    String name();
    Endpoint[] endpoints() default {};
}
```

Trong `Module`, `Endpoint[]` là một mảng annotation type, hợp lệ vì `Endpoint` là annotation type. Dấu ngoặc nhọn `{}` trong `default {}` là mảng rỗng.

Các kiểu **không hợp lệ** cho element:

```java
import java.util.List;

@interface InvalidElements {
    Object data();           // Sai: Object
    List<String> tags();     // Sai: List
    int[][] matrix();        // Sai: mảng hai chiều
    void perform();          // Sai: void
}
```

Ví dụ trên cố ý không biên dịch và chỉ dùng để nhận dạng lỗi. Annotation element không cho phép kiểu đối tượng tùy ý hoặc collection như `List`/`Map`; trong nhiều trường hợp có thể dùng `String[]`, enum hoặc nested annotation để thể hiện cấu hình có cấu trúc.

Không thể dùng `null` làm giá trị element hay làm giá trị `default`. Nếu cần biểu diễn “chưa chỉ định”, hãy thiết kế một mặc định có ý nghĩa, ví dụ chuỗi rỗng, enum `UNSPECIFIED`, mảng rỗng hoặc giá trị sentinel được ghi rõ trong tài liệu.

## 4. Khai báo element bắt buộc và element có `default`

Một element có dạng:

```java
String name();                        // Bắt buộc
int priority() default 1;             // Có mặc định
String[] labels() default {"general"}; // Có mặc định
```

Từ `default` nằm **trong định nghĩa annotation type**, không nằm trong phần sử dụng annotation:

```java
@interface Task {
    String id();
    String description() default "";
    int[] allowedCodes() default {200};
}

@Task(id = "T-01")
class TaskOne {}

@Task(id = "T-02", description = "Import", allowedCodes = {200, 201})
class TaskTwo {}
```

`@Task(id = "T-01")` hợp lệ vì compiler dùng mặc định cho `description` và `allowedCodes`. Những trường hợp như `@Task`, `@Task()` hay `@Task(description = "missing id")` đều thiếu `id` và gây lỗi biên dịch.

Lưu ý:

- `default` là **giá trị hằng được xác định lúc biên dịch** theo quy tắc của annotation element. Không viết `default null`, không gọi phương thức tùy ý để tạo mặc định.
- Giá trị mặc định là một phần của metadata trong annotation type và được dùng khi element không có giá trị tường minh ở nơi sử dụng.
- Thay đổi giá trị `default` có thể làm thay đổi giá trị mà chương trình đọc từ những annotation đã biên dịch trước đó nhưng bỏ qua element ấy. Vì vậy, đổi `default` là thay đổi có ý nghĩa về hành vi và cần cân nhắc tương thích.

## 5. Khai báo element tên `value` và dạng viết tắt

Java dành một cú pháp tiện lợi khi annotation có element tên chính xác là `value`:

```java
@interface Label {
    String value();
}
```

Hai cách sử dụng sau tương đương:

```java
@Label("stable")
class First {}

@Label(value = "stable")
class Second {}
```

Với element khác tên `value`, bắt buộc viết tên:

```java
@interface Path {
    String location();
}

@Path(location = "/api")
class ApiPath {}
```

`@Path("/api")` không hợp lệ vì `Path` không khai báo `value()`. Nếu annotation có thêm element khác, hãy ghi rõ `value = ...` khi muốn truyền nhiều phần tử:

```java
@interface Feature {
    String value();
    boolean enabled() default true;
}

@Feature("search")
class SearchFeature {}

@Feature(value = "billing", enabled = false)
class BillingFeature {}
```

`@Feature("billing", enabled = false)` không phải cú pháp được chấp nhận để trộn một giá trị không tên với các cặp `name = value`.

## 6. Giá trị cho element: hằng, enum, class và annotation lồng nhau

Khả năng khai báo kiểu element không đồng nghĩa có thể truyền bất cứ biểu thức Java nào. Chẳng hạn:

```java
enum Scope {
    LOCAL, GLOBAL
}

@interface RetryRule {
    int limit() default 2;
}

@interface ComponentInfo {
    String name();
    Scope scope() default Scope.LOCAL;
    Class<?> implementation() default Object.class;
    RetryRule retry() default @RetryRule;
    String[] aliases() default {};
}
```

Một cách dùng hợp lệ:

```java
@ComponentInfo(
    name = "order",
    scope = Scope.GLOBAL,
    implementation = String.class,
    retry = @RetryRule(limit = 4),
    aliases = {"checkout", "purchase"}
)
class OrderComponent {}
```

Các điểm cần nhớ:

- `String` và giá trị số/nguyên thủy cần là **constant expression** phù hợp; literal hoặc hằng `static final` được khai báo bằng constant expression có thể đáp ứng.
- `enum` phải là enum constant như `Scope.GLOBAL`, không phải chuỗi `"GLOBAL"`.
- `Class` nhận class literal như `String.class`, không phải đối tượng `new String()`.
- Element có kiểu annotation nhận một annotation literal như `@RetryRule(limit = 4)`.
- Mảng thường được truyền bằng `{...}`. Với element có kiểu mảng, Java cũng chấp nhận một giá trị đơn thuộc kiểu phần tử trong ngữ cảnh annotation, ví dụ `aliases = "checkout"`.
- Không truyền kết quả của lời gọi method chạy ở runtime làm giá trị annotation.

Ví dụ **sai**:

```java
@interface Version {
    String number();
}

class InvalidVersion {
    static String current() { return "2.0"; }

    @Version(number = current()) // Sai: lời gọi method không phải constant expression
    void execute() {}
}
```

Có thể thay bằng hằng thích hợp:

```java
class ValidVersion {
    static final String CURRENT = "2.0";

    @Version(number = CURRENT)
    void execute() {}
}
```

## 7. Các meta-annotation thường gắn vào định nghĩa `@interface`

**Meta-annotation** là annotation được đặt trên một annotation type nhằm quy định metadata của chính kiểu annotation đó. Phổ biến nhất là `@Retention` và `@Target` từ `java.lang.annotation`.

### `@Retention`: annotation tồn tại đến giai đoạn nào?

```java
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;

@Retention(RetentionPolicy.RUNTIME)
@interface Traceable {
    String category() default "general";
}
```

Ba chính sách:

| Chính sách | Ý nghĩa |
|---|---|
| `RetentionPolicy.SOURCE` | Có trong mã nguồn, không được compiler giữ lại trong class file |
| `RetentionPolicy.CLASS` | Được ghi vào class file, không bắt buộc có sẵn qua reflection lúc runtime |
| `RetentionPolicy.RUNTIME` | Có trong class file và có thể được đọc qua Java reflection lúc runtime |

Nếu không khai báo `@Retention`, mặc định là **`RetentionPolicy.CLASS`**. Dùng `RUNTIME` khi thực sự cần các lời gọi như `SomeClass.class.getAnnotation(...)`. Bộ xử lý annotation trong lúc biên dịch không cần retention `RUNTIME` để nhìn thấy annotation trong mã nguồn đang được xử lý.

### `@Target`: annotation được phép gắn ở đâu?

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Target;

@Target({ElementType.TYPE, ElementType.METHOD})
@interface Audited {
}
```

`@Audited` được dùng ở khai báo kiểu và method; không được tự động dùng ở field nếu `FIELD` không có trong danh sách. Một số giá trị `ElementType` thường gặp:

| Giá trị | Vị trí sử dụng |
|---|---|
| `TYPE` | Khai báo class, interface, enum hoặc annotation type |
| `FIELD` | Khai báo field, bao gồm enum constants |
| `METHOD` | Khai báo method |
| `PARAMETER` | Khai báo tham số |
| `CONSTRUCTOR` | Khai báo constructor |
| `ANNOTATION_TYPE` | Khai báo một annotation type |
| `TYPE_USE` | Vị trí sử dụng kiểu, như `List<@NonNull String>` |
| `TYPE_PARAMETER` | Khai báo tham số kiểu, như `class Box<@Marker T>` |

`@Target` không có nghĩa annotation tự chạy tại vị trí ấy; nó chỉ cho compiler biết nơi có thể áp dụng. Nếu bỏ `@Target`, Java áp dụng tập vị trí mặc định rộng hơn cho khai báo; khi muốn tạo *type annotation* rõ ràng nên khai báo `TYPE_USE`.

### Một số meta-annotation khác

- `@Documented` yêu cầu công cụ Javadoc đưa annotation vào tài liệu API khi thích hợp.
- `@Inherited` cho phép một số annotation trên class được nhìn nhận là kế thừa từ superclass qua cơ chế truy vấn annotation của Java; **không** tự động truyền annotation của method hay interface.
- `@Repeatable` cho phép cùng một annotation xuất hiện nhiều lần tại vị trí phù hợp, với một *container annotation type* được khai báo đúng quy tắc.

Khi mới học `@interface`, hãy làm chắc khai báo element, `default`, `@Target` và `@Retention` trước; `@Repeatable` và `@Inherited` là cơ chế bổ sung tùy mục đích.

## 8. Ví dụ Java 17+ hoàn chỉnh: tự định nghĩa và đọc annotation

Tạo file **`AnnotationDefinitionDemo.java`** với toàn bộ mã sau:

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.util.Arrays;

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@interface TaskSpec {
    String id();
    int retries() default 2;
    String[] tags() default {};
}

@TaskSpec(id = "sync")
class SyncTask {}

@TaskSpec(id = "backup", retries = 4, tags = {"io", "critical"})
class BackupTask {}

public class AnnotationDefinitionDemo {
    public static void main(String[] args) {
        printSpec(SyncTask.class);
        printSpec(BackupTask.class);
    }

    private static void printSpec(Class<?> type) {
        TaskSpec spec = type.getAnnotation(TaskSpec.class);
        System.out.println(spec.id() + " | " + spec.retries()
                + " | " + Arrays.toString(spec.tags()));
    }
}
```

Biên dịch và chạy với JDK 17 trở lên:

```bash
javac AnnotationDefinitionDemo.java
java AnnotationDefinitionDemo
```

Kết quả in ra:

```text
sync | 2 | []
backup | 4 | [io, critical]
```

Giải thích theo trình tự:

1. `@interface TaskSpec` định nghĩa ba element: `id` bắt buộc, `retries` mặc định bằng `2` và `tags` mặc định là mảng rỗng.
2. `@Target(ElementType.TYPE)` giới hạn việc sử dụng ở khai báo kiểu.
3. `@Retention(RetentionPolicy.RUNTIME)` giữ metadata để `getAnnotation` đọc được trong khi chương trình đang chạy.
4. `@TaskSpec(id = "sync")` chỉ cung cấp giá trị bắt buộc. Khi đọc từ `SyncTask`, `retries()` trả `2` và `tags()` trả mảng rỗng theo mặc định.
5. `BackupTask` cung cấp các giá trị tường minh, nên khi đọc trả `4` và danh sách `["io", "critical"]`; `Arrays.toString` định dạng mảng thành `[io, critical]`.

**Điểm cốt lõi:** `@interface` định nghĩa hợp đồng dữ liệu; khai báo `@TaskSpec(...)` gắn dữ liệu; reflection ở ví dụ này là **bộ phận đọc dữ liệu**. Annotation không tự gọi `printSpec` hoặc thực hiện công việc “sync/backup”.

## 9. Các lỗi thường gặp khi tự định nghĩa annotation

Các đoạn sau là **ví dụ cố ý sai**, không đặt chung với chương trình chạy ở mục trước.

### Thiếu cú pháp element

```java
@interface BadSyntax {
    String name()      // Sai: thiếu ;
    int priority(1);   // Sai: annotation element không nhận tham số
}
```

Cú pháp đúng là `String name();` và `int priority();` (hoặc `int priority() default 1;`). Annotation element không có tham số, không khai báo method body và không khai báo `throws`.

### Chọn kiểu trả về không được phép

```java
@interface WrongType {
    java.util.List<String> names(); // Sai: List không phải kiểu element hợp lệ
}
```

Thay bằng `String[] names();` nếu phù hợp nghiệp vụ.

### Đặt tên element sai hoặc gõ sai khi sử dụng

```java
@interface Profile {
    String displayName();
}

@Profile(displayname = "Admin") // Sai: khác chữ hoa/thường
class AdminProfile {}
```

Compiler đối chiếu tên chính xác, nên phải viết `displayName = "Admin"`. Element cũng không thể mang tên `2name`, `user-name` hoặc từ khóa Java như `class`.

### Bỏ sót element bắt buộc

```java
@interface EventInfo {
    String event();
    boolean enabled() default true;
}

@EventInfo(enabled = false) // Sai: thiếu event()
class EventHandler {}
```

Sửa bằng `@EventInfo(event = "login", enabled = false)`. Dùng `@EventInfo` hoặc `@EventInfo()` cũng không làm `event` trở thành tùy chọn.

### Nhầm `@interface` với interface bình thường

```java
interface Metadata {
    String name();
}

@Metadata(name = "x") // Sai: Metadata không phải annotation type
class Example {}
```

Muốn sử dụng `@Metadata` thì phải **định nghĩa `@interface Metadata`**. Ngược lại, khi muốn mô tả phương thức mà một class phải implement, cần `interface` thông thường thay vì `@interface`.

### Mong chờ reflection đọc được annotation mặc định retention `CLASS`

```java
@interface Stage {
    String value();
}

@Stage("demo")
class DemoStage {}
```

Khai báo này hợp lệ, nhưng `DemoStage.class.getAnnotation(Stage.class)` không cung cấp instance runtime của `Stage` vì kiểu annotation không khai báo `@Retention(RUNTIME)`. Nếu mục tiêu là đọc từ runtime, thêm `@Retention(RetentionPolicy.RUNTIME)` vào định nghĩa `Stage` và biên dịch lại mã liên quan.

### Sử dụng sai `@Target`

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Target;

@Target(ElementType.METHOD)
@interface MethodOnly {}

@MethodOnly // Sai: đây là class, không phải method
class WrongLocation {}
```

Giữ `@MethodOnly` trên method hoặc thiết kế lại `@Target` nếu thực sự cần dùng ở class.

## 10. Nguyên tắc thiết kế annotation dễ sử dụng

Một annotation type tốt nên diễn đạt **metadata ổn định, khai báo được từ mã nguồn**, và có tên/kiểu element minh bạch.

- Chọn tên kiểu mô tả ý nghĩa (`AuditInfo`, `Endpoint`, `RetryPolicy`) thay vì tên chung chung không thể hiểu khi đặt sau dấu `@`.
- Dùng element bắt buộc cho giá trị thật sự không thể thiếu; dùng `default` cho lựa chọn phụ có mặc định rõ ràng.
- Dùng enum cho các lựa chọn hữu hạn cần kiểm tra tại biên dịch; tránh chuỗi tùy ý nếu giá trị không được phép thay đổi ngoài tập xác định.
- Dùng `Class<?>` khi metadata cần tham chiếu kiểu; dùng nested annotation khi một nhóm thông số có cấu trúc.
- Tránh nhồi logic chạy động hoặc đối tượng nghiệp vụ phức tạp vào annotation. Annotation phù hợp mô tả cấu hình tĩnh hơn là dữ liệu runtime.
- Chọn `@Target` đủ hẹp để phát hiện dùng sai vị trí; chọn `@Retention` theo cách metadata thực sự được tiêu thụ.
- Hạn chế sửa tên, kiểu và đặc biệt là xóa element đã công bố; những thay đổi đó có thể làm hỏng mã sử dụng annotation. Cân nhắc tương thích ngay khi thiết kế `default`.

Ví dụ một thiết kế rõ ý nghĩa:

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

enum AccessLevel { PUBLIC, INTERNAL }

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.METHOD)
@interface ApiOperation {
    String value();  // Tên nghiệp vụ của thao tác
    AccessLevel access() default AccessLevel.INTERNAL;
    boolean audited() default false;
}
```

Nơi sử dụng có thể viết ngắn gọn nếu chỉ cung cấp `value`:

```java
class UserApi {
    @ApiOperation(value = "createUser", access = AccessLevel.PUBLIC, audited = true)
    void createUser() {}

    @ApiOperation("healthCheck")
    void healthCheck() {}
}
```

Ở đây `@ApiOperation` chỉ mang dữ liệu mô tả. Muốn áp dụng phân quyền hoặc ghi audit thật, hệ thống cần một thành phần đọc annotation và hiện thực hóa quy tắc đó.

## 11. Checklist khi khai báo `@interface`

Trước khi dùng một annotation type trong dự án Java, tự kiểm tra:

1. Tôi đã dùng đúng `@interface Ten` để **định nghĩa annotation type** chưa?
2. Mỗi element có dạng `Kieu ten();` hoặc `Kieu ten() default giaTri;`, không có tham số và body chưa?
3. Mỗi kiểu element có nằm trong danh sách Java cho phép, hoặc là mảng **một chiều** của các kiểu đó không?
4. Những element thật sự bắt buộc có được phân biệt với element có `default` không?
5. `default` và các giá trị tại nơi sử dụng có đúng kiểu và tuân thủ yêu cầu hằng số của annotation không?
6. Nếu muốn dùng dạng `@Ten("x")`, annotation có định nghĩa element `value()` không?
7. `@Target` có cho phép các vị trí sử dụng mong muốn không?
8. Nếu cần reflection đọc ở runtime, tôi đã đặt `@Retention(RetentionPolicy.RUNTIME)` chưa?
9. Khi annotation được đọc, có thành phần nào xử lý metadata hay tôi đang kỳ vọng annotation tự tạo hành vi?
10. Sau khi thay đổi định nghĩa, tôi đã biên dịch lại và kiểm tra các nơi sử dụng để phát hiện lỗi tương thích chưa?

Khi hiểu `@interface` là **bản định nghĩa metadata có element và quy tắc chặt chẽ**, bạn sẽ tự thiết kế annotation hợp lệ, biết cách dùng `default`, kiểm soát phạm vi với `@Target` và quyết định thời điểm lưu giữ bằng `@Retention`.