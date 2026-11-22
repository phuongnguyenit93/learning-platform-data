# Method.getDefaultValue: lấy giá trị mặc định của phần tử annotation bằng Java Reflection

## 1. Khái niệm và mục đích

Một annotation được khai báo bằng `@interface`. Mỗi phần tử (*annotation element*) được viết dưới dạng một khai báo phương thức **không có tham số**, ví dụ `int retries()` hoặc `String name()`. Phần tử có thể khai báo **giá trị mặc định** bằng từ khóa `default`:

```java
@interface Config {
    String name();                  // Bắt buộc cung cấp khi dùng annotation.
    int retries() default 3;       // Giá trị mặc định là 3.
    boolean enabled() default true;
}
```

Trong Reflection, từng phần tử được biểu diễn bằng một đối tượng `java.lang.reflect.Method`. Phương thức:

```java
Object defaultValue = method.getDefaultValue();
```

đọc **giá trị mặc định được khai báo trên chính phần tử annotation** mà `Method` đại diện, không cần khởi tạo đối tượng của lớp được gắn annotation.

**Quy tắc quan trọng nhất:**

- Nếu `Method` đại diện cho phần tử annotation **có khai báo `default`**, `getDefaultValue()` trả giá trị mặc định tương ứng dưới dạng `Object`.
- Nếu phần tử **không có giá trị mặc định**, kết quả là **`null`**.
- Nếu `Method` **không đại diện cho một phần tử khai báo trực tiếp trong kiểu annotation**, kết quả cũng là **`null`**.
- Nếu kiểu phần tử là primitive, giá trị trả về được **boxing** thành wrapper tương ứng. Ví dụ `int retries() default 3` → `Integer.valueOf(3)`.
- `getDefaultValue()` **không lấy giá trị đã ghi đè tại chỗ sử dụng annotation**. Để lấy giá trị hiệu lực của một annotation đang gắn trên lớp/phương thức, hãy đọc đối tượng annotation.

Đây là API hữu ích khi tạo trình đọc metadata, trình kiểm tra cấu hình, tài liệu hóa annotation, công cụ validation, scanner hoặc framework dựa trên Reflection.

## 2. Phân biệt giá trị mặc định và giá trị hiệu lực

Xét:

```java
@Retention(RetentionPolicy.RUNTIME)
@interface Task {
    String name();
    int retries() default 3;
}

@Task(name = "backup", retries = 7)
class BackupTask {}

@Task(name = "cleanup")
class CleanupTask {}
```

Với phần tử `Task.retries()`:

- **Giá trị mặc định của khai báo:** `3`. Đọc qua `Task.class.getDeclaredMethod("retries").getDefaultValue()`.
- **Giá trị hiệu lực trên `BackupTask`:** `7`, vì nơi sử dụng đã ghi đè.
- **Giá trị hiệu lực trên `CleanupTask`:** `3`, vì nơi sử dụng bỏ qua `retries` nên Java áp dụng default.

```java
Method retries = Task.class.getDeclaredMethod("retries");
Object declaredDefault = retries.getDefaultValue(); // Integer(3)

Task backup = BackupTask.class.getAnnotation(Task.class);
int usedByBackup = backup.retries(); // 7

Task cleanup = CleanupTask.class.getAnnotation(Task.class);
int usedByCleanup = cleanup.retries(); // 3
```

Các đoạn trên là **mã minh họa** và cần các import `java.lang.annotation.*`, `java.lang.reflect.*`. Chương trình độc lập đầy đủ sẽ có ở phần 4.

`@Retention(RetentionPolicy.RUNTIME)` cần thiết để lấy **annotation đã gắn** bằng `getAnnotation(...)` khi chương trình chạy. Trong khi đó, `getDefaultValue()` đọc metadata trên `Method` của chính kiểu annotation; không phải là thao tác lấy annotation đang gắn trên một phần tử sử dụng.

**Không thể dựa vào `getDefaultValue()` để xác định tại nơi sử dụng một giá trị hiệu lực có được viết tường minh hay được kế thừa từ default.** Nếu người viết ghi `retries = 3` tường minh, giá trị hiệu lực vẫn là `3`.

## 3. API, kết quả và các kiểu dữ liệu

Chữ ký Java SE 17:

```java
public Object getDefaultValue()
```

| Khai báo phần tử | Giá trị `getDefaultValue()` | Kiểu runtime của kết quả |
| --- | --- | --- |
| `int retries() default 3;` | `3` | `Integer` |
| `boolean enabled() default true;` | `true` | `Boolean` |
| `String label() default "java";` | `"java"` | `String` |
| `String[] tags() default {"a","b"};` | Mảng gồm `"a"`, `"b"` | `String[]` |
| `Class<?> handler() default String.class;` | `String.class` | `Class<?>` |
| `Priority priority() default Priority.HIGH;` | `Priority.HIGH` | Enum `Priority` |
| `Meta meta() default @Meta;` | Đối tượng annotation mặc định | Kiểu annotation `Meta` |
| `String name();` | `null` | Không có giá trị mặc định |

Vì return type là `Object`, phải **kiểm tra/kết hợp với `method.getReturnType()`** trước khi ép kiểu. Ví dụ:

```java
Method method = Config.class.getDeclaredMethod("retries");
Object value = method.getDefaultValue();

if (value instanceof Integer retries) {
    System.out.println(retries);
}
```

Phương thức phần tử trả `int` nhưng `getDefaultValue()` trả một `Integer`. Với kiểu trả về là mảng primitive, ví dụ `int[] levels() default {1,2}`, giá trị trả về là **`int[]`**, không phải `Integer[]`: boxing chỉ áp dụng cho **một giá trị primitive**, không biến đổi cả mảng.

Các loại phần tử annotation hợp lệ theo quy tắc ngôn ngữ Java gồm primitive (không có `void`), `String`, `Class` hoặc dạng tham số cho phép, enum, kiểu annotation và mảng một chiều của các kiểu đó. Không dùng kiểu phần tử bất kỳ như `List<String>` hoặc `Map`, và không thể dùng `null` làm giá trị mặc định hợp lệ.

## 4. Ví dụ Java 17+ chạy được và stdout chính xác

Lưu chương trình sau dưới tên **`AnnotationDefaultDemo.java`**:

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.lang.reflect.Method;
import java.util.Arrays;

public class AnnotationDefaultDemo {
    enum Priority { LOW, HIGH }

    @Retention(RetentionPolicy.RUNTIME)
    @interface Meta {
        String author() default "team";
    }

    @Retention(RetentionPolicy.RUNTIME)
    @Target(ElementType.TYPE)
    @interface Config {
        String name();                              // Không có default.
        int retries() default 3;
        boolean enabled() default true;
        String[] tags() default {"core", "reflection"};
        Class<?> handler() default String.class;
        Priority priority() default Priority.HIGH;
        Meta meta() default @Meta;
    }

    @Config(name = "service", retries = 7, tags = {"prod"})
    static class Service {}

    @Config(name = "backup")
    static class Backup {}

    interface Greeter {
        default String greet() {
            return "hi";
        }
    }

    public static void main(String[] args) throws Exception {
        Method name = Config.class.getDeclaredMethod("name");
        Method retries = Config.class.getDeclaredMethod("retries");

        System.out.println("name default: " + name.getDefaultValue());

        Object retryDefault = retries.getDefaultValue();
        System.out.println("retries default: " + retryDefault
                + " (" + retryDefault.getClass().getSimpleName() + ")");

        System.out.println("enabled default: "
                + Config.class.getDeclaredMethod("enabled").getDefaultValue());

        System.out.println("tags default: " + Arrays.toString(
                (String[]) Config.class.getDeclaredMethod("tags")
                        .getDefaultValue()));

        System.out.println("handler default: "
                + ((Class<?>) Config.class.getDeclaredMethod("handler")
                        .getDefaultValue()).getSimpleName());

        System.out.println("priority default: "
                + Config.class.getDeclaredMethod("priority").getDefaultValue());

        Meta nested = (Meta) Config.class.getDeclaredMethod("meta")
                .getDefaultValue();
        System.out.println("meta.author default: " + nested.author());

        Config service = Service.class.getAnnotation(Config.class);
        Config backup = Backup.class.getAnnotation(Config.class);

        System.out.println("service retries: " + service.retries());
        System.out.println("backup retries: " + backup.retries());
        System.out.println("service tags: "
                + Arrays.toString(service.tags()));
        System.out.println("backup tags: "
                + Arrays.toString(backup.tags()));

        System.out.println("retries via invoke: " + retries.invoke(service));

        Method defaultMethod = Greeter.class.getMethod("greet");
        System.out.println("interface default method isDefault: "
                + defaultMethod.isDefault());
        System.out.println("interface default method getDefaultValue: "
                + defaultMethod.getDefaultValue());

        System.out.println("ordinary method getDefaultValue: "
                + String.class.getMethod("length").getDefaultValue());
    }
}
```

Biên dịch và chạy bằng Java 17 trở lên:

```bash
javac AnnotationDefaultDemo.java
java AnnotationDefaultDemo
```

Stdout:

```text
name default: null
retries default: 3 (Integer)
enabled default: true
tags default: [core, reflection]
handler default: String
priority default: HIGH
meta.author default: team
service retries: 7
backup retries: 3
service tags: [prod]
backup tags: [core, reflection]
retries via invoke: 7
interface default method isDefault: true
interface default method getDefaultValue: null
ordinary method getDefaultValue: null
```

### Giải thích các dòng đáng chú ý

1. `Config.name()` **không** khai báo `default`, nên `name.getDefaultValue()` trả `null`. Phần tử `name` vẫn bắt buộc khai báo khi dùng `@Config`.
2. `Config.retries()` khai báo `default 3`, nên kết quả là đối tượng wrapper `Integer` mang giá trị `3`.
3. Mảng mặc định `tags` là `String[]`. Dùng `Arrays.toString` để hiển thị nội dung; nếu gọi `toString()` trực tiếp trên mảng sẽ không có định dạng liệt kê phần tử mong muốn.
4. Default của `Class<?> handler()` là một `Class`, của `Priority priority()` là một giá trị enum, và của `Meta meta()` là đối tượng annotation tương ứng.
5. Trên `Service`, giá trị `retries` hiệu lực là `7` (ghi đè). Trên `Backup`, giá trị hiệu lực là `3` (default).
6. `retries.invoke(service)` gọi phần tử trên **đối tượng annotation instance** và trả giá trị hiệu lực `7`; nó **khác** `retries.getDefaultValue()`, vốn luôn mô tả default của phần tử.
7. `Greeter.greet()` là **default method của interface** có thân phương thức; `isDefault()` trả `true`, nhưng `getDefaultValue()` vẫn trả `null`. Hai nghĩa của chữ *default* không liên quan.
8. `String.length()` là phương thức thông thường, không phải phần tử annotation; `getDefaultValue()` trả `null`.

## 5. Phải lấy đúng Method của kiểu annotation

Giả sử có `@Config` gắn trên `Service`, cần tránh ba nhầm lẫn:

```java
// Đúng: lấy phần tử đã khai báo trong annotation type.
Method element = Config.class.getDeclaredMethod("retries");
Object defaultValue = element.getDefaultValue();

// Đúng: lấy annotation instance trên nơi sử dụng.
Config annotation = Service.class.getAnnotation(Config.class);
int actual = annotation.retries();

// Sai mục đích: tìm "retries" trên lớp Service.
// Service.class.getDeclaredMethod("retries") thường không tồn tại.
```

Annotation instance có thể được runtime triển khai bằng proxy hoặc kỹ thuật nội bộ, nhưng để đọc default ta nên sử dụng **`Config.class`** hoặc `annotation.annotationType()` và `getDeclaredMethod(elementName)`, thay vì suy ra cấu trúc implementation của đối tượng annotation.

Để phân tích toàn bộ default của annotation type, dùng:

```java
// Phương thức tiện ích minh họa, đặt trong một lớp Java có các import cần thiết.
static void printDefaults(Class<? extends java.lang.annotation.Annotation> type) {
    for (java.lang.reflect.Method element : type.getDeclaredMethods()) {
        Object value = element.getDefaultValue();

        System.out.println(element.getName()
                + " : " + element.getReturnType().getTypeName()
                + " => " + (value == null ? "<required>" : value));
    }
}
```

Đây là **mã minh họa**, không phải một chương trình có `main`. Chương trình xử lý metadata thực tế nên bổ sung bộ định dạng cho **mảng** bằng `Arrays.toString` hoặc `Arrays.deepToString` theo loại dữ liệu, và **sắp xếp** tên phần tử để có kết quả ổn định (vì `getDeclaredMethods()` không đảm bảo thứ tự).

Để tránh lỗi ép kiểu, hãy phân loại `value` bằng `instanceof`, kết hợp `element.getReturnType()` và xử lý `null` trước khi giải nén.

## 6. Null nghĩa là “không khai báo default”, không phải giá trị mặc định null

Annotation element **không thể có** `default null` hợp lệ trong mã nguồn Java. Vì vậy:

```java
@interface Notice {
    String message();                // Không có default.
    String optional() default "";    // Có default là chuỗi rỗng.
    String[] tags() default {};      // Có default là mảng rỗng.
}
```

Bảng phân biệt:

| Khai báo | `getDefaultValue()` | Có default? |
| --- | --- | --- |
| `String message();` | `null` | Không |
| `String optional() default "";` | `""` | Có |
| `String[] tags() default {};` | Mảng `String[]` độ dài `0` | Có |
| `int count() default 0;` | `Integer(0)` | Có |
| `boolean active() default false;` | `Boolean.FALSE` | Có |

Do đó, **không** dùng kiểm tra như `if (!Boolean.TRUE.equals(defaultValue))` để kết luận thiếu default, vì `false` là một default hoàn toàn hợp lệ. Quy tắc đơn giản: `value == null` nghĩa là không có default theo hợp đồng của `getDefaultValue()`.

Lưu ý `getDefaultValue()` được gọi trên `Method` thông thường cũng trả `null`; nếu cần phân biệt “phần tử bắt buộc” với “không phải phần tử annotation”, hãy kiểm tra `method.getDeclaringClass().isAnnotation()`.

## 7. Không nhầm với các khái niệm “default” khác

| Cụm từ/API | Ý nghĩa | Liên quan đến `Method.getDefaultValue()`? |
| --- | --- | --- |
| `@interface X { int n() default 3; }` | Giá trị mặc định của phần tử annotation | **Có**, trả `3` được boxing |
| `interface X { default void run() {} }` | Default method của interface có thân | **Không**, `getDefaultValue()` thường `null` |
| `Method.isDefault()` | Method có phải default method của interface hay không | API **khác** hoàn toàn |
| `@Retention(RUNTIME)` | Annotation được lưu để truy xuất ở runtime tại nơi sử dụng | Không tự tạo default; hữu ích cho `getAnnotation` |
| `@Target(TYPE)` | Giới hạn vị trí sử dụng annotation | Không quyết định giá trị mặc định |
| `Class.getAnnotation(X.class)` | Trả annotation instance đang gắn trên phần tử | Đọc giá trị **hiệu lực** qua `annotation.element()` |
| `Method.invoke(annotationInstance)` | Gọi phương thức phần tử trên annotation instance | Trả giá trị **hiệu lực**; không chỉ default |

**Lưu ý về `@Retention`:** Khi công cụ muốn đọc annotation **đã gắn** ở runtime, khai báo annotation với `@Retention(RetentionPolicy.RUNTIME)`. Nếu chỉ có metadata của một kiểu annotation được nạp, Reflection có thể đọc thông tin về các phương thức phần tử và default của chính kiểu đó mà không cần lấy một annotation instance ở nơi sử dụng.

## 8. Quy tắc default trong annotation và tính tương thích

Annotation có nhiều ràng buộc riêng so với phương thức Java thông thường:

- Phần tử annotation không nhận tham số và không khai báo `throws`.
- Giá trị mặc định cần là biểu thức phù hợp với loại phần tử và các quy tắc hằng/giá trị annotation của Java. Không thể dùng giá trị runtime tùy ý như `default new java.util.Date()`.
- Mảng mặc định chỉ mô tả **một chiều kiểu phần tử hợp lệ**; nếu muốn biểu diễn cấu trúc phức tạp, cân nhắc annotation lồng nhau hoặc thiết kế schema khác.
- Phần tử không có `default` phải được cung cấp khi sử dụng annotation trong mã nguồn, trừ khi có cú pháp cung cấp tương ứng.
- Default thuộc **khai báo annotation type**, không phải được lưu lặp lại thành một giá trị tường minh ở mỗi vị trí sử dụng annotation.

Một hệ quả quan trọng khi tiến hóa thư viện: nếu thay `default 3` thành `default 5` trong phiên bản mới của annotation, các vị trí sử dụng **không khai báo `retries` tường minh** có thể nhận giá trị hiệu lực mới khi chạy với bản annotation mới. Ngược lại, nơi đã ghi `retries = 7` tiếp tục dùng `7` theo khai báo sử dụng của nó. Bởi vậy thay đổi default có thể là **thay đổi hành vi**, dù không cần sửa mọi nơi sử dụng annotation.

Khi viết framework hoặc scanner: xử lý giá trị default như một phần của hợp đồng cấu hình; lưu rõ phiên bản/chính sách nếu default ảnh hưởng đến nghiệp vụ. Không sửa lại `Method` hoặc coi kết quả `getDefaultValue()` là thiết lập runtime có thể ghi đè bằng Reflection.

## 9. Các lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| `getDefaultValue()` trả `null` cho `name()` | Phần tử bắt buộc, không khai báo default | Xác định thiếu default; đọc từ annotation instance nếu đã gắn |
| Trả `3` nhưng nơi sử dụng annotation đặt `retries = 7` | Đang đọc default của khai báo, không phải giá trị hiệu lực | Dùng `annotation.retries()` hoặc `Method.invoke(annotation)` |
| `getDefaultValue()` trả `null` cho default method interface | `default` của interface method khác default của annotation | Dùng `Method.isDefault()` để nhận dạng default method |
| `ClassCastException` khi ép default của `int` về `String` | Primitive được boxing thành `Integer` | Kiểm tra `getReturnType()`, `instanceof` trước khi cast |
| In mảng `tags` ra dạng `[Ljava.lang.String;@...` | Gọi `Object.toString()` của mảng | Dùng `Arrays.toString((String[]) value)` |
| Tưởng `default ""` hoặc `default {}` là không có default | Giá trị rỗng vẫn là default hợp lệ | Chỉ kiểm tra `getDefaultValue() == null` |
| `NoSuchMethodException` khi tìm element qua lớp sử dụng | Element thuộc **annotation type**, không thuộc lớp được gắn | Tìm qua `Config.class.getDeclaredMethod(...)` |
| `getAnnotation(Config.class)` trả `null` | Annotation không gắn/không được giữ ở runtime/vị trí sai | Kiểm tra `@Retention(RUNTIME)` và vị trí khai báo |
| Default chứa `Class` không còn khả dụng lúc đọc | Phụ thuộc kiểu bị thiếu hoặc lỗi nạp lớp | Theo tài liệu API, `getDefaultValue()` có thể ném `TypeNotPresentException` |
| Kết quả duyệt element thay đổi thứ tự | `getDeclaredMethods()` không bảo đảm thứ tự | Sắp xếp theo tên khi xuất báo cáo hoặc serialize |

### Các lỗi khi classpath hoặc binary metadata không còn tương thích

Tài liệu `Method.getDefaultValue()` của Java SE 17 nêu `TypeNotPresentException` nếu giá trị mặc định loại `Class` tham chiếu tới kiểu không còn tải được. Ngoài ra, khi phân tích annotation từ thư viện không đồng nhất phiên bản, có thể xuất hiện lỗi liên kết/định dạng metadata hoặc các lỗi khi truy cập giá trị annotation instance. Không nên giả định mọi annotation trong môi trường plugin đều có binary metadata hợp lệ.

Trong ứng dụng bình thường, **không cần bắt** các lỗi hiếm để đọc một annotation do dự án tự kiểm soát; trong công cụ quét bytecode/library bất kỳ, hãy quyết định chính sách xử lý lỗi có chủ đích và cung cấp thông tin về kiểu annotation/element gây vấn đề.

## 10. Tự kiểm tra kiến thức

1. **Phần tử `int timeout() default 0;` trả gì qua `getDefaultValue()`?** Đối tượng `Integer` có giá trị `0`, không phải `null`.
2. **Phần tử `String id();` trả gì?** `null`, do không có default; nơi sử dụng phải khai báo `id` khi cần.
3. **`@Config(retries = 9)` làm thay đổi `getDefaultValue()` của `retries` thành 9 không?** Không; default trên annotation type không đổi. Giá trị hiệu lực ở nơi sử dụng là `9`.
4. **`String[] tags() default {};` có default không?** Có; trả mảng rỗng, khác với `null`.
5. **Một default method của interface có `Method.isDefault() == true` có nghĩa `getDefaultValue()` khác `null` không?** Không, hai API phục vụ hai khái niệm khác nhau.
6. **Muốn xem tất cả default trên một `@interface`, làm gì?** Duyệt `annotationType.getDeclaredMethods()`, gọi `getDefaultValue()` cho từng `Method`, kiểm tra `null` và định dạng đúng theo kiểu.
7. **Muốn lấy giá trị cuối cùng áp dụng trên một lớp đã gắn annotation thì sao?** Lấy annotation qua `getAnnotation(...)`, sau đó gọi phần tử trên instance; không chỉ đọc `Method.getDefaultValue()`.

**Ghi nhớ:** `Method.getDefaultValue()` lấy **giá trị mặc định trong khai báo phần tử annotation**, trả `null` nếu không có default hoặc không phải phần tử annotation. Nó không tự đọc giá trị được ghi đè trên đối tượng được gắn annotation, và không liên quan tới `Method.isDefault()` của interface.

Tài liệu tham khảo: [Java SE 17 — Method.getDefaultValue](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Method.html#getDefaultValue()), [JLS §9.6.2 — Defaults for Annotation Type Elements](https://docs.oracle.com/javase/specs/jls/se17/html/jls-9.html#jls-9.6.2), [Java SE 17 — Annotation](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/annotation/Annotation.html).