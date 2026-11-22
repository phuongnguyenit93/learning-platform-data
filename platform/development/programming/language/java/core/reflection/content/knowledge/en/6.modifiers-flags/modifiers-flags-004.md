# Phân biệt modifier có ý nghĩa trên lớp, field hoặc executable trong Java Reflection

## 1. Cùng một `int` modifier nhưng ý nghĩa phụ thuộc phần tử

Trong Java Reflection, nhiều thành phần có phương thức `getModifiers()` trả về một số nguyên `int` chứa các bit cờ:

- `Class<?>.getModifiers()`: cờ của lớp hoặc interface.
- `Field.getModifiers()`: cờ của field.
- `Method.getModifiers()`: cờ của phương thức.
- `Constructor<?>.getModifiers()`: cờ của constructor.
- `Parameter.getModifiers()`: cờ liên quan tham số hình thức, nếu cần phân tích sâu hơn.

Thư viện `java.lang.reflect.Modifier` cung cấp các hằng như `PUBLIC`, `STATIC`, `FINAL` và các hàm `isPublic(int)`, `isStatic(int)`, `isFinal(int)`, `toString(int)`. Mỗi bit có thể được kiểm tra bằng phép AND:

```java
int flags = someField.getModifiers();
boolean isStatic = (flags & Modifier.STATIC) != 0;

// Tương đương:
boolean alsoStatic = Modifier.isStatic(flags);
```

Đây là **mảnh mã** cần đặt trong ngữ cảnh đã có biến `someField` và import `java.lang.reflect.Modifier`.

**Quy tắc quan trọng:** Phải biết `flags` lấy từ loại phần tử nào trước khi giải thích. Ví dụ, `final` trên class cấm kế thừa, trên method cấm override, trên field giới hạn phép gán; `static` trên nested class khác `static` trên field hoặc method. Một cờ chỉ có nghĩa khi cấu trúc Java tương ứng cho phép cờ đó.

## 2. Bảng phân loại theo nơi xuất hiện

Ký hiệu: ✓ là có ý nghĩa ở loại phần tử tương ứng, — là không phải modifier áp dụng cho loại đó. Từng trường hợp ✓ còn phụ thuộc vị trí khai báo (top-level, member, interface, v.v.).

| Modifier / đặc tính | `Class<?>` (lớp/interface) | `Field` | `Method` | `Constructor<?>` | Ý nghĩa khi hợp lệ |
| --- | --- | --- | --- | --- | --- |
| `public` | ✓ | ✓ | ✓ | ✓ | Phạm vi truy cập công khai theo quy tắc Java và module |
| `protected` | ✓ với kiểu thành viên phù hợp | ✓ | ✓ | ✓ | Truy cập trong package và theo quy tắc subclass |
| `private` | ✓ với kiểu thành viên phù hợp | ✓ | ✓ | ✓ | Giới hạn truy cập theo ngữ cảnh bao quanh |
| `abstract` | ✓ | — | ✓ | — | Lớp chưa hoàn chỉnh / method chưa có phần triển khai |
| `static` | ✓ với kiểu lồng thành viên | ✓ | ✓ | — | Thành phần gắn với kiểu chứa thay vì từng instance; nested static class không cần instance bao ngoài |
| `final` | ✓ | ✓ | ✓ | — | Cấm subclass / hạn chế gán lại field / cấm override method |
| `transient` | — | ✓ | — | — | Field bị bỏ qua bởi cơ chế tuần tự hóa mặc định của Java |
| `volatile` | — | ✓ | — | — | Cơ chế đọc/ghi field có bảo đảm bộ nhớ theo Java Memory Model |
| `synchronized` | — | — | ✓ | — | Method được đồng bộ hóa bằng monitor |
| `native` | — | — | ✓ | — | Method có phần triển khai native |
| `strictfp` | ✓ trong cú pháp lịch sử | — | ✓ trong cú pháp lịch sử | — | Từng kiểm soát quy tắc số thực; từ Java 17 là thừa theo ngữ nghĩa ngôn ngữ |
| `interface` (bit `Modifier.INTERFACE`) | ✓ cho interface | — | — | — | Phân loại interface ở mức phản chiếu; không phải cờ áp dụng cho field/method/constructor |

Các điểm phải nhớ khi đọc bảng:

- **Top-level class** chỉ có thể khai báo `public` hoặc để mức truy cập package-private; không khai báo trực tiếp `private`, `protected` hay `static`. Nhưng **member class** nằm trong một kiểu khác có thể có các modifier đó nếu phù hợp.
- Interface có quy tắc riêng: ví dụ, method trong interface có thể là `public`, `private`, `abstract`, `static`, hoặc `default` theo cú pháp hợp lệ; không phải mọi tổ hợp trong bảng đều hợp lệ.
- Constructor chỉ nhận modifier truy cập (`public`, `protected`, `private`) hoặc để package-private trong mã nguồn thông thường. Không có `static constructor`, `final constructor` hay `abstract constructor`.
- `transient`/`volatile` dành cho field; `synchronized`/`native` dành cho method. Không kết luận loại một phần tử chỉ bằng tên cờ mà không kiểm tra kiểu metadata.

**Package-private** không có hằng `Modifier.PACKAGE_PRIVATE`: nếu cả `public`, `protected` và `private` đều vắng mặt, cấp truy cập ngôn ngữ là package-private. Đây không phải một bit thứ tư.

## 3. Modifier của kiểu: `Class<?>`

### `public`, `protected`, `private` trên lớp

Một lớp ở mức top-level chỉ được `public` hoặc package-private. Với **member class**, thông tin truy cập có thể là `private`, `protected` hoặc `public`. Phản chiếu bằng:

```java
Class<?> type = java.util.Map.Entry.class;
int m = type.getModifiers();

System.out.println(Modifier.isPublic(m));
System.out.println(Modifier.isStatic(m));
System.out.println(Modifier.isInterface(m));
```

Đây là **mảnh mã trong phương thức** có import `Modifier`. `Map.Entry` là nested interface (một member type) nên có những bit kiểu không thể áp dụng tương tự cho top-level class. Đừng đọc `Modifier.isStatic(type.getModifiers())` thành “mọi class có thể khai báo static”.

### `final`, `abstract`, `static` có ý nghĩa gì?

- `final class`: không cho khai báo subclass. Ví dụ `String.class` là final. Không thể suy ra mọi field hoặc method của lớp đều mang cờ `final` trong metadata.
- `abstract class`: không thể trực tiếp `new` và có thể chứa abstract method; **không phải** cứ abstract class là tất cả method đều abstract. Interface thông thường có tính trừu tượng ở cấp kiểu, nhưng còn có default/static/private methods.
- `static` trên member class: lớp lồng không cần một instance bao ngoài theo cơ chế inner class thông thường. Đây là một đặc tính cấu trúc của nested type, không phải trạng thái tĩnh của mọi đối tượng.
- `Modifier.isInterface(m)` nhận diện bit `interface`; nếu cần phân biệt annotation interface, dùng `type.isAnnotation()`. Interface không đồng nghĩa abstract class dù nhiều API modifier có vẻ gần nhau.

Các loại kiểu mới/cụ thể có API chuyên dụng:

| Cần nhận biết | Reflection API thích hợp | Ghi chú |
| --- | --- | --- |
| Interface | `Class.isInterface()`; hoặc `Modifier.isInterface(type.getModifiers())` | Bit `INTERFACE` thuộc metadata kiểu |
| Annotation interface | `Class.isAnnotation()` | Không chỉ dùng `isInterface()` vì annotation cũng là interface |
| Enum | `Class.isEnum()` | Không có `Modifier.isEnum(int)` |
| Record (Java 16+) | `Class.isRecord()` | Không có `Modifier.isRecord(int)` |
| Sealed type (Java 17+) | `Class.isSealed()`; `getPermittedSubclasses()` | Không có `Modifier.isSealed(int)` |
| Mảng, primitive | `Class.isArray()`, `Class.isPrimitive()` | `Class.getModifiers()` có quy tắc đặc thù; không coi chúng như khai báo class thông thường |

Đặc biệt, `Class.getModifiers()` đối với **array, primitive và `void`** có quy tắc do API định nghĩa; ví dụ các kiểu này được xem là `final` tại phương thức này. Đó không có nghĩa ta có thể viết khai báo nguồn `final int` để mô tả kiểu nguyên thủy. Cần phân biệt metadata của kiểu và modifier có thể gõ trong khai báo nguồn.

### `sealed`, `non-sealed` và `strictfp`

`sealed`/`non-sealed` thuộc cú pháp loại kiểu nhưng **không có** `Modifier.SEALED` hay `Modifier.NON_SEALED` công khai; dùng `Class.isSealed()` nếu cần biết một kiểu có bị niêm phong hay không. Đối với `non-sealed`, riêng `!type.isSealed()` không đủ chứng minh khai báo có chữ `non-sealed`, vì lớp bình thường cũng không sealed.

`strictfp` là modifier lịch sử cho lớp/interface/method. Từ Java 17, đánh giá biểu thức floating-point luôn theo strict semantics, vì vậy `strictfp` dư về ý nghĩa hành vi; tránh xây dựng nghiệp vụ phụ thuộc vào sự hiện diện của bit này trên JDK hiện đại.

## 4. Modifier của field: `Field`

Field đại diện một biến thành viên của lớp hoặc interface, có thể là instance field hoặc static field:

- `static`: field thuộc lớp, không thuộc từng instance. `static` không đồng nghĩa hằng số.
- `final`: sau giai đoạn khởi tạo hợp lệ, không thể gán lại qua mã Java thông thường. **`final` của một reference không làm object được trỏ đến trở thành bất biến sâu**. Việc sửa final field qua Reflection chịu các hạn chế riêng; không suy diễn quyền ghi từ một bit.
- `volatile`: thiết lập quan hệ hiển thị/thứ tự bộ nhớ cho các thao tác đọc ghi field. **`counter++` trên volatile field vẫn không phải một phép tăng nguyên tử.**
- `transient`: loại field khỏi dạng serialization mặc định bằng `ObjectOutputStream`; không đồng nghĩa field bị xóa, không thể đọc, hoặc sẽ bị loại bỏ trong mọi cơ chế JSON/ORM.
- `public`, `protected`, `private`: mô tả phạm vi truy cập khai báo.

Ví dụ mảnh field:

```java
private transient volatile int state;
public static final int LIMIT = 3;
```

Nếu Reflection lấy `getModifiers()` của `state`, `Modifier.toString(...)` hiển thị `"private transient volatile"`; với `LIMIT`, trả `"public static final"`. Thứ tự trả ra từ `toString` là thứ tự chuẩn hóa, không nhất thiết là thứ tự từ khóa đã gõ trong mã nguồn.

Đối với một enum, `Field.isEnumConstant()` cho biết field có phải hằng enum hay không; `Field.isSynthetic()` cho biết field do compiler tạo theo định nghĩa JVM/JLS. Không có `Modifier.isEnumConstant(int)` hay `Modifier.isSynthetic(int)` công khai.

## 5. Modifier của executable: `Method` và `Constructor<?>`

`java.lang.reflect.Executable` là lớp cha chung của `Method` và `Constructor<?>`; cả hai đều có `getModifiers()`. **Executable không bao gồm `Field` hay `Class<?>`**.

### Với `Method`

- `public`, `protected`, `private`: phạm vi truy cập method.
- `static`: method thuộc cấp class; không cần instance để gọi theo cách thông thường.
- `final`: method không thể bị override (nếu method có thể được kế thừa theo các quy tắc khác).
- `abstract`: method không có body ở nơi khai báo; cần phần triển khai ở lớp concrete thích hợp.
- `synchronized`: tự động lấy monitor khi vào method, giải phóng khi thoát kể cả khi ném exception. Instance method dùng monitor của receiver; static synchronized method dùng `Class` object.
- `native`: method có phần triển khai do mã native cung cấp, không có body Java.
- `strictfp`: cú pháp lịch sử, từ Java 17 không thay đổi kết quả số thực.

**Method trong interface** có trường hợp `default` có body, nhưng `Modifier` không có hằng `DEFAULT`. Dùng **`Method.isDefault()`** để nhận biết; không suy ra default method chỉ từ việc không có `abstract` vì interface còn có static và private methods.

### Với `Constructor<?>`

Constructor chỉ dùng các bit truy cập của Java. Không kiểm tra ý nghĩa của `static`, `abstract`, `synchronized`, `final`, `native` trên constructor. Dùng:

```java
Constructor<?> ctor = type.getDeclaredConstructor();
int m = ctor.getModifiers();

boolean privateCtor = Modifier.isPrivate(m);
```

Đây là **mảnh phương thức**, biến `type` là `Class<?>`, cần import `Constructor` và `Modifier`. `getDeclaredConstructor()` có thể lấy metadata constructor private, nhưng **không tự cấp quyền gọi** constructor đó. Java access checks và cơ chế module vẫn có hiệu lực.

### Những thông tin của executable không nên đọc qua `Modifier`

| Điều cần hỏi | API đúng | Loại |
| --- | --- | --- |
| Method là default method? | `Method.isDefault()` | Method |
| Method là bridge method do compiler tạo? | `Method.isBridge()` | Method |
| Executable nhận varargs? | `Executable.isVarArgs()` | Method và constructor |
| Executable được đánh dấu synthetic? | `Executable.isSynthetic()` | Method và constructor |
| Parameter khai báo `final`? | `Modifier.isFinal(parameter.getModifiers())` | Parameter |
| Parameter là implicit/synthetic? | `Parameter.isImplicit()`, `Parameter.isSynthetic()` | Parameter |

Các cờ ở JVM/class file như `bridge`, `varargs`, `synthetic` có thể nằm trong metadata riêng hoặc dùng bit value trùng với cờ ở ngữ cảnh khác. **Không kiểm tra `Modifier.isVolatile(method.getModifiers())` để tìm bridge method, hoặc `Modifier.isTransient(method.getModifiers())` để tìm varargs**, dù có thể gặp trùng giá trị bit ở mức JVM. Phải gọi API có ngữ nghĩa đúng như `isBridge()` và `isVarArgs()`.

`@Override`, `@Deprecated` và nhiều annotations khác cũng không phải cờ của `Modifier`. Khi cần annotations, dùng `getDeclaredAnnotations()`, `isAnnotationPresent(...)` hoặc API thích hợp.

## 6. Ví dụ hoàn chỉnh, chạy với Java 17+

Tạo **`ModifierByContextDemo.java`** với nội dung:

```java
import java.lang.reflect.Constructor;
import java.lang.reflect.Field;
import java.lang.reflect.Method;
import java.lang.reflect.Modifier;

public class ModifierByContextDemo {
    public static final class Box {
        private transient volatile int state;
        public static final int LIMIT = 3;

        private Box() {}

        public final synchronized void bump() {
            state++;
        }

        public void log(String... messages) {}
    }

    interface Action {
        default void perform() {}
    }

    private static void show(String label, int modifiers) {
        System.out.println(label + ": " + Modifier.toString(modifiers));
    }

    public static void main(String[] args)
            throws ReflectiveOperationException {
        Class<?> type = Box.class;
        Field state = type.getDeclaredField("state");
        Field limit = type.getDeclaredField("LIMIT");
        Constructor<?> ctor = type.getDeclaredConstructor();
        Method bump = type.getDeclaredMethod("bump");
        Method log = type.getDeclaredMethod("log", String[].class);
        Method perform = Action.class.getDeclaredMethod("perform");

        show("type", type.getModifiers());
        show("state", state.getModifiers());
        show("LIMIT", limit.getModifiers());
        show("ctor", ctor.getModifiers());
        show("bump", bump.getModifiers());

        System.out.println("type final? "
                + Modifier.isFinal(type.getModifiers()));
        System.out.println("state volatile? "
                + Modifier.isVolatile(state.getModifiers()));
        System.out.println("state transient? "
                + Modifier.isTransient(state.getModifiers()));
        System.out.println("bump synchronized? "
                + Modifier.isSynchronized(bump.getModifiers()));
        System.out.println("ctor private? "
                + Modifier.isPrivate(ctor.getModifiers()));
        System.out.println("log varargs? " + log.isVarArgs());
        System.out.println("perform default? " + perform.isDefault());
    }
}
```

Biên dịch/chạy:

```bash
javac --release 17 ModifierByContextDemo.java
java ModifierByContextDemo
```

Kết quả:

```text
type: public static final
state: private transient volatile
LIMIT: public static final
ctor: private
bump: public final synchronized
type final? true
state volatile? true
state transient? true
bump synchronized? true
ctor private? true
log varargs? true
perform default? true
```

**Giải thích kết quả:**

1. `Box` là **public static final member class**, không phải top-level class. Do đó có cả `static` và `final` trong kết quả type.
2. `state` là **instance field** với hai chính sách độc lập: `transient` và `volatile`. Không có `static`/`final`.
3. `LIMIT` là **static final field**, có thể đọc như hằng số nhưng semantics `final` không đồng nhất với `final class`.
4. `ctor` có mỗi `private`. Không gọi constructor, vì việc đọc metadata không cần khởi tạo instance.
5. `bump` là **final synchronized method**. Hai bit nói về override và lock, không về field hay class.
6. `log` có varargs: `isVarArgs()` trả true dù `Modifier.toString(log.getModifiers())` không in chữ `varargs`.
7. `perform` là default method của interface: `isDefault()` trả true dù không tồn tại `Modifier.DEFAULT`.

Ví dụ này chỉ tra metadata; không cần `setAccessible(true)`, không sửa đối tượng bằng Reflection và không phụ thuộc giá trị tên do compiler tự sinh.

## 7. Bộ lọc modifier theo loại phần tử

`Modifier` còn cung cấp các hàm trả về **mask các modifier được phép có trong khai báo nguồn theo loại phần tử**:

```java
Modifier.classModifiers();
Modifier.interfaceModifiers();
Modifier.fieldModifiers();
Modifier.methodModifiers();
Modifier.constructorModifiers();
Modifier.parameterModifiers();
```

Ví dụ, `Modifier.toString(Modifier.fieldModifiers())` trên JDK 17+ hiển thị các modifier nguồn có thể áp dụng cho field: `public protected private static final transient volatile`. `Modifier.toString(Modifier.constructorModifiers())` chỉ hiển thị `public protected private`.

Muốn giữ lại những bit modifier nguồn thuộc một loại thành phần:

```java
int sourceFieldFlags =
        field.getModifiers() & Modifier.fieldModifiers();
String display = Modifier.toString(sourceFieldFlags);
```

Đây là **mảnh mã trong phương thức** có biến `field` thuộc kiểu `Field`. Việc AND mask **không kiểm chứng** mọi kết hợp có hợp lệ trong ngữ cảnh cụ thể hay không. Ví dụ, mask class cho phép `private` vì có member classes, nhưng `private` vẫn không hợp lệ với top-level class. Các hàm mask cũng không thay thế `isBridge()`, `isSynthetic()`, `isVarArgs()` hay truy vấn khác về metadata không biểu diễn bằng modifier nguồn.

Nếu thư viện xử lý metadata nhận nhiều loại phần tử, có thể phân nhánh kiểu một cách tường minh:

```java
static String describeMember(java.lang.reflect.Member member) {
    int flags = member.getModifiers();

    if (member instanceof java.lang.reflect.Field) {
        return "field: static=" + Modifier.isStatic(flags)
                + ", volatile=" + Modifier.isVolatile(flags)
                + ", transient=" + Modifier.isTransient(flags);
    }

    if (member instanceof java.lang.reflect.Method method) {
        return "method: static=" + Modifier.isStatic(flags)
                + ", abstract=" + Modifier.isAbstract(flags)
                + ", synchronized=" + Modifier.isSynchronized(flags)
                + ", varargs=" + method.isVarArgs();
    }

    if (member instanceof java.lang.reflect.Constructor<?>) {
        return "constructor: private=" + Modifier.isPrivate(flags);
    }

    return "member type not handled";
}
```

Đây là **mảnh phương thức trong class** với `import java.lang.reflect.Modifier;`. `Class<?>` không triển khai interface `Member`, vì vậy xử lý modifier của class ở nhánh riêng bằng `Class.getModifiers()`. Mẫu này ngăn việc áp dụng nhầm một phép kiểm tra chỉ có nghĩa trên field sang method hoặc constructor.

## 8. Những nhầm lẫn dễ gặp

| Nhầm lẫn | Cách kiểm tra đúng |
| --- | --- |
| Thấy `final` thì kết luận “không thể sửa giá trị” trên mọi phần tử | Hỏi `final` nằm trên class, field hay method; ba nghĩa khác nhau |
| `Modifier.isStatic(clazz.getModifiers())` nghĩa là instance của class là static | Chỉ ra kiểu khai báo là member type lồng, nếu cờ này có ý nghĩa |
| `Modifier.isVolatile(method.getModifiers())` để đoán method được compiler tạo | Dùng `Method.isBridge()`/`isSynthetic()`; volatile là modifier dành cho field |
| Constructor có `synchronized`/`static` giống method | Constructor chỉ có các modifier truy cập |
| `Modifier.isPublic(field.getModifiers())` bảo đảm thao tác Reflection sẽ thành công | Access còn phụ thuộc class chứa, nơi gọi, modules và chính sách truy cập |
| Không có cờ `public`/`protected`/`private` nghĩa là `public` | Không có ba bit này nghĩa là package-private theo quy tắc truy cập nguồn |
| `Modifier.toString(...)` hiển thị mọi đặc tính của class/method | Cần thêm các API `isSealed`, `isRecord`, `isDefault`, `isVarArgs`, `isBridge`, `isSynthetic`... |
| `transient` đồng nghĩa “không lưu ở bất cứ đâu” | Chỉ có ý nghĩa đặc biệt đối với serialization mặc định; framework khác có quy tắc riêng |
| `volatile` biến `++` thành nguyên tử | Không; tăng có nhiều thao tác, nên dùng atomics hoặc đồng bộ phù hợp |
| `getDeclaredField("x")`/`getDeclaredConstructor()` đã bỏ qua Java access control | Chúng lấy metadata khai báo; quyền truy cập thực tế được kiểm tra riêng |

Cũng không nên giả định `getModifiers()` mô tả đầy đủ nguyên văn các token trong tệp `.java`: compiler có thể thêm thông tin ngầm định và các chi tiết khác của class file. Kết quả là mô hình Reflection theo đặc tả API, không phải bản ghi lại cú pháp nguồn.

## 9. Cách lựa chọn API khi kiểm tra modifier

1. **Xác định đối tượng đang kiểm tra**: `Class<?>`, `Field`, `Method`, `Constructor<?>` hay `Parameter`.
2. **Chọn tính chất thật sự cần biết**: access level, static/final/abstract; volatile/transient của field; synchronized/native của method; loại interface/record/sealed; hay varargs/default/bridge.
3. **Dùng `Modifier.isXxx` khi tính chất là modifier đúng ngữ cảnh**, và dùng API chuyên dụng khi tính chất không thuộc các bit nguồn công khai.
4. **Diễn giải trong ngữ cảnh khai báo**: top-level khác member class, method interface khác method class, constructor khác method.
5. **Không dùng bit để suy luận xa hơn đặc tả**: kiểm tra access/invocation riêng và xem thêm metadata cần thiết khi định xây dựng công cụ Reflection.

## 10. Bài tập tự kiểm tra

1. Giải thích sự khác nhau của `final` trên `String.class`, field `private final List<String> items` và method `public final void close()`. Trường hợp nào ngăn subclass, trường hợp nào ngăn override, trường hợp nào hạn chế gán lại reference?
2. Viết một member class `private static class Helper {}`. Dự đoán `Modifier.toString(Helper.class.getModifiers())`. Sau đó thử chuyển nó thành top-level class: các modifier nào không còn được phép?
3. Với field `volatile int count`, kiểm tra `Modifier.isVolatile`; giải thích vì sao `count++` vẫn có race condition.
4. So sánh `Method.isDefault()` và `Modifier.isAbstract(method.getModifiers())` cho hai method của một interface: một method khai báo `void run();` và một method `default void stop() {}`.
5. Lấy `Constructor<?>` private qua `getDeclaredConstructor()`; giải thích sự khác nhau giữa “Reflection nhìn thấy metadata” và “Reflection được phép gọi constructor”.
6. Tạo method `void send(String... values) {}`; dùng `isVarArgs()` để nhận diện, sau đó giải thích vì sao không nên kiểm tra `Modifier.isTransient(method.getModifiers())` cho cùng mục đích.

## 11. Tài liệu tham khảo chính thức

- [Java SE 17 — `java.lang.reflect.Modifier`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Modifier.html): hằng bit, `isXxx`, `toString` và các mask theo loại phần tử.
- [Java SE 17 — `Class.getModifiers()`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html#getModifiers()): hành vi với class/interface, mảng, primitive, `void`.
- [Java SE 17 — `Field`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Field.html): modifier của field, `isEnumConstant()` và `isSynthetic()`.
- [Java SE 17 — `Executable`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Executable.html): nền tảng chung của method/constructor, `isVarArgs()` và `isSynthetic()`.
- [Java SE 17 — `Method`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Method.html): `getModifiers()`, `isDefault()`, `isBridge()`.
- [Dev.java — Reading Modifiers](https://dev.java/learn/api/reflection-method-handles/reflection/modifiers/): hướng dẫn Reflection về ý nghĩa cờ theo thành phần.