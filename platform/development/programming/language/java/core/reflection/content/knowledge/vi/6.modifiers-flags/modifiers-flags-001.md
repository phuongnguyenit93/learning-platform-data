# `getModifiers()` và cách giải mã cờ bằng `Modifier` trong Java Reflection

Khi dùng Java Reflection để xem khai báo của một lớp, phương thức, constructor hoặc field, ta có thể cần trả lời: thành phần có `public` không, có `static`/`final` không, field có `volatile` không, method có `synchronized` không? Java không cung cấp một đối tượng riêng cho từng từ khóa này trong API `getModifiers()`. Thay vào đó, nó trả về **một số nguyên `int` chứa tập hợp các bit cờ**. Lớp tiện ích `java.lang.reflect.Modifier` dùng để giải mã các bit ấy.

Điều quan trọng là **cờ mô tả khai báo**, không tự động cho biết liệu một lời gọi hoặc truy cập reflective thực sự được phép, cũng không biểu diễn mọi đặc điểm của class file hay mọi từ khóa Java mới.

## 1. `getModifiers()` trả về gì?

Các API `getModifiers()` xuất hiện ở:

| Đối tượng reflection | Cách lấy cờ | Thành phần được mô tả |
| --- | --- | --- |
| `Class<?>` | `SomeClass.class.getModifiers()` | Class hoặc interface |
| `Field` | `field.getModifiers()` | Trường dữ liệu |
| `Method` | `method.getModifiers()` | Phương thức |
| `Constructor<?>` | `constructor.getModifiers()` | Constructor |
| `Parameter` | `parameter.getModifiers()` | Các cờ của tham số hình thức, ví dụ `final` |

Giá trị trả về là **bitmask**, nghĩa là mỗi bit được dùng để biểu thị sự hiện diện của một cờ. Nếu nhiều modifier cùng tồn tại, chúng được ghép bằng phép OR bitwise `|`; ví dụ:

```java
int flags = Modifier.PUBLIC | Modifier.STATIC | Modifier.FINAL;
System.out.println(flags); // 25
```

Trong ví dụ này, `PUBLIC = 0x0001`, `STATIC = 0x0008` và `FINAL = 0x0010`; OR tạo ra `0x0019`, tức `25` trong hệ thập phân.

**Không nên coi số nguyên `25` là hợp đồng định dạng để hiển thị cho người dùng.** Giải mã bằng `Modifier` sẽ vừa rõ ý nghĩa vừa tránh các phép so sánh số nguyên sai.

Ví dụ một khai báo `public static final int LIMIT` có thể được kiểm tra bằng:

```java
Field field = SomeClass.class.getDeclaredField("LIMIT");
int modifiers = field.getModifiers();

boolean publicField = Modifier.isPublic(modifiers);
boolean staticField = Modifier.isStatic(modifiers);
boolean finalField = Modifier.isFinal(modifiers);
String humanReadable = Modifier.toString(modifiers);
```

Đoạn trên là **minh họa API**, với `SomeClass` giả định có field `LIMIT`; chương trình độc lập đầy đủ ở phần 5.

## 2. `Modifier`: kiểm tra từng cờ

`java.lang.reflect.Modifier` là lớp tiện ích chứa hằng bit và các phương thức `static`. Các nhóm thường gặp:

| Nhóm | Hằng cờ | Phương thức kiểm tra | Nơi thường gặp |
| --- | --- | --- | --- |
| Truy cập | `PUBLIC`, `PROTECTED`, `PRIVATE` | `isPublic`, `isProtected`, `isPrivate` | Class/member |
| Thành viên cấp lớp | `STATIC` | `isStatic` | Field, method, nested type |
| Hạn chế thay đổi/kế thừa | `FINAL` | `isFinal` | Class, field, method |
| Yêu cầu cài đặt | `ABSTRACT` | `isAbstract` | Class, method |
| Dấu hiệu interface | `INTERFACE` | `isInterface` | Class biểu diễn interface |
| Đồng bộ | `SYNCHRONIZED` | `isSynchronized` | Method |
| Kết nối native | `NATIVE` | `isNative` | Method |
| Field không tham gia mặc định vào Java object serialization | `TRANSIENT` | `isTransient` | Field |
| Ngữ nghĩa bộ nhớ chia sẻ | `VOLATILE` | `isVolatile` | Field |
| Ngữ nghĩa dấu phẩy động | `STRICT` | `isStrict` | `strictfp` (lịch sử) |

Một số lưu ý về ngữ nghĩa:

- Các cờ truy cập `public`, `protected`, `private` không thể đồng thời có trên cùng một khai báo hợp lệ. **Không có cờ `PACKAGE_PRIVATE`**: không có cả ba cờ trên nghĩa là *package-private* đối với class/member thích hợp.
- `Modifier.isInterface(classFlags)` nhận biết flag interface ở `Class`; thông thường `Class.isInterface()` diễn đạt trực tiếp ý định này hơn.
- `synchronized` thuộc về method; `volatile` và `transient` thuộc về field. Không kiểm tra những cờ này ngoài ngữ cảnh thích hợp.
- `final` không đồng nghĩa với đối tượng bất biến; với `final List<String> list`, tham chiếu không được gán lại bình thường nhưng nội dung `List` có thể thay đổi.
- `volatile` đảm bảo những tính chất visibility và ordering được Java Memory Model quy định; nó **không** làm phép `count++` trở nên atomic.
- Trên Java 17+, `strictfp` không còn thay đổi kết quả biểu thức floating-point theo cách trước kia do ngữ nghĩa floating-point luôn strict; khi đọc dữ liệu cũ vẫn có thể gặp khái niệm này.

## 3. Hai cách giải mã: predicate và toán tử bit

### Cách ưu tiên — `Modifier.isXxx(int)`

```java
int flags = field.getModifiers();

if (Modifier.isPrivate(flags)) {
    System.out.println("Field được khai báo private");
}
if (Modifier.isStatic(flags) && Modifier.isFinal(flags)) {
    System.out.println("Field mang đồng thời static và final");
}
```

Mỗi `isXxx` trả về `true` nếu cờ tương ứng có mặt, bất kể những cờ khác. Đây là cách dễ đọc khi kiểm tra chính sách hoặc tạo metadata.

### Cách bitwise — dùng hằng `Modifier.Xxx`

Các hằng là các bit khác nhau; kiểm tra một cờ:

```java
boolean isStatic = (flags & Modifier.STATIC) != 0;
```

Kiểm tra **đồng thời tất cả** các cờ yêu cầu:

```java
int required = Modifier.PUBLIC | Modifier.STATIC | Modifier.FINAL;
boolean containsAll = (flags & required) == required;
```

Kiểm tra **ít nhất một** trong số cờ yêu cầu:

```java
int either = Modifier.PUBLIC | Modifier.PROTECTED;
boolean containsAny = (flags & either) != 0;
```

Tính package-private cho member đang xét:

```java
boolean packagePrivate = !Modifier.isPublic(flags)
        && !Modifier.isProtected(flags)
        && !Modifier.isPrivate(flags);
```

**Sai lầm kinh điển:** viết `flags == Modifier.PUBLIC` để hỏi thành phần có `public` không. Nếu field có `public static final`, kết quả đó sai vì số nguyên còn có các bit `STATIC` và `FINAL`. Tương tự, `(flags & required) != 0` chỉ chứng minh *ít nhất một cờ* xuất hiện, không chứng minh *tất cả*.

Không dùng phép phủ định bit `~flags` rồi giải mã như thể đó là tập các modifier Java hợp lệ; các bit ngoài nhóm được định nghĩa có thể xuất hiện.

## 4. Hiển thị cờ bằng `Modifier.toString()`

`Modifier.toString(int)` chuyển bitmask thành chuỗi các từ khóa có thứ tự, cách nhau bằng dấu cách:

```java
int flags = Modifier.PUBLIC | Modifier.STATIC | Modifier.FINAL;
System.out.println(Modifier.toString(flags));
// public static final
```

Nếu không có cờ thuộc tập mà `toString` biểu diễn, chuỗi có thể rỗng. Điều đó **không** nói class/member «không tồn tại» hay «không có đặc điểm nào».

`Modifier.toString()` là bộ **giải mã và định dạng**, không phải bộ xác thực tính hợp lệ của một khai báo Java. Bạn có thể OR những cờ xung đột như `PUBLIC | PRIVATE` và vẫn nhận được chuỗi, dù mã nguồn Java hợp lệ không thể khai báo một member vừa `public` vừa `private`.

Các phương thức `Modifier.classModifiers()`, `interfaceModifiers()`, `fieldModifiers()`, `methodModifiers()`, `constructorModifiers()`, `parameterModifiers()` trả về mask các source modifier áp dụng cho *loại khai báo tương ứng*. Chúng hữu ích khi cần lọc nhóm cờ trước khi hiển thị:

```java
int fieldWords = field.getModifiers() & Modifier.fieldModifiers();
System.out.println(Modifier.toString(fieldWords));
```

Đừng dùng `Modifier.toString()` như bản ghi đầy đủ mọi access flag ở class file: một số flag nội bộ, `synthetic`, `bridge`, `varargs`, `enum`, và thuộc tính mới không nhất thiết được biểu diễn bằng từ khóa của `Modifier`.

## 5. Ví dụ Java 17+ hoàn chỉnh

Lưu nội dung sau vào tệp `ModifierDemo.java`, rồi chạy bằng `javac` và `java`. Chương trình có class lồng nhau, nhiều field/method khác modifier, constructor và một default method trong interface.

```java
import java.lang.reflect.Constructor;
import java.lang.reflect.Field;
import java.lang.reflect.Method;
import java.lang.reflect.Modifier;

public class ModifierDemo {
    public static class Sample {
        public static final int MAX = 10;
        private transient String token;
        protected volatile long revision;

        public Sample() {}

        public synchronized void refresh() {}

        private native void nativeHook();
    }

    public interface Processor {
        default void process() {}
    }

    public static void main(String[] args) throws Exception {
        Class<?> type = Sample.class;
        System.out.println("class: "
                + Modifier.toString(type.getModifiers()));

        Field max = type.getDeclaredField("MAX");
        int maxFlags = max.getModifiers();
        System.out.println("MAX: " + Modifier.toString(maxFlags));
        System.out.println("MAX public/static/final: "
                + (Modifier.isPublic(maxFlags)
                && Modifier.isStatic(maxFlags)
                && Modifier.isFinal(maxFlags)));

        int required = Modifier.PUBLIC | Modifier.STATIC | Modifier.FINAL;
        System.out.println("MAX bitmask: "
                + ((maxFlags & required) == required));

        Field token = type.getDeclaredField("token");
        System.out.println("token: "
                + Modifier.toString(token.getModifiers()));

        Field revision = type.getDeclaredField("revision");
        System.out.println("revision: "
                + Modifier.toString(revision.getModifiers()));

        Method refresh = type.getDeclaredMethod("refresh");
        System.out.println("refresh: "
                + Modifier.toString(refresh.getModifiers()));
        System.out.println("refresh synchronized: "
                + Modifier.isSynchronized(refresh.getModifiers()));

        Method hook = type.getDeclaredMethod("nativeHook");
        System.out.println("nativeHook: "
                + Modifier.toString(hook.getModifiers()));

        Constructor<?> ctor = type.getDeclaredConstructor();
        System.out.println("constructor: "
                + Modifier.toString(ctor.getModifiers()));

        Method process = Processor.class.getDeclaredMethod("process");
        System.out.println("default method modifiers: "
                + Modifier.toString(process.getModifiers()));
        System.out.println("isDefault(): " + process.isDefault());

        System.out.println("interface flag: "
                + Modifier.isInterface(Processor.class.getModifiers()));
    }
}
```

Lệnh:

```bash
javac ModifierDemo.java
java ModifierDemo
```

Đầu ra:

```text
class: public static
MAX: public static final
MAX public/static/final: true
MAX bitmask: true
token: private transient
revision: protected volatile
refresh: public synchronized
refresh synchronized: true
nativeHook: private native
constructor: public
default method modifiers: public
isDefault(): true
interface flag: true
```

Giải thích:

1. `Sample` là **member class** khai báo `public static` nên `Class.getModifiers()` phản ánh cả hai cờ. Với top-level class, modifier `static` không thể xuất hiện như trong ví dụ member class.
2. `MAX` mang ba cờ `public static final`; dùng ba predicate hoặc phép AND với mask đều trả kết quả đúng.
3. `token` khai báo `private transient`; `revision` khai báo `protected volatile`. Các cờ phản ánh khai báo chứ chưa chứng minh logic serialization hay thread safety của cả chương trình.
4. `refresh` có cờ `synchronized`; `nativeHook` có cờ `native`, **không cần gọi** phương thức native để đọc metadata. Ví dụ chỉ đọc tên và modifier nên không cần thư viện native.
5. Default method `process()` có `getModifiers()` hiển thị `public`, còn `isDefault() == true`. Từ khóa `default` của interface method **không có hằng `Modifier.DEFAULT`**.

Cả `getDeclaredField`, `getDeclaredMethod` và `getDeclaredConstructor` trong ví dụ chỉ **lấy metadata**. Lấy metadata của thành viên `private` không đồng nghĩa đã được phép đọc/ghi/gọi thành viên đó.

## 6. Phân biệt *declared* và *public/inherited* trước khi đọc modifier

Các phương thức chọn member ảnh hưởng đến việc bạn sẽ giải mã cờ của **thành viên nào**:

| API | Phạm vi tìm kiếm quan trọng |
| --- | --- |
| `getDeclaredFields()` | Các field được khai báo trực tiếp, mọi mức truy cập; không bao gồm field kế thừa |
| `getFields()` | Các field `public` trong phạm vi thành viên có thể thấy, kể cả kế thừa |
| `getDeclaredMethods()` | Các method khai báo trực tiếp, mọi mức truy cập; không bao gồm method kế thừa |
| `getMethods()` | Các method `public` được phản ánh từ class/interface và phần kế thừa |
| `getDeclaredConstructors()` | Các constructor khai báo trong class, mọi mức truy cập |
| `getConstructors()` | Các constructor `public` của class; constructor không được kế thừa |

Vì vậy, nếu viết bộ quét metadata và muốn tìm field `private transient`, thường phải dùng `getDeclaredFields()`. Nếu chỉ quét `getFields()`, bạn sẽ bỏ qua field `private`.

Ví dụ phác thảo một bộ lọc (giả định `type` là `Class<?>` cần quét):

```java
for (Field field : type.getDeclaredFields()) {
    int mod = field.getModifiers();
    if (Modifier.isStatic(mod) && Modifier.isFinal(mod)) {
        System.out.println(field.getName() + ": "
                + Modifier.toString(mod));
    }
}
```

Với API mở rộng, cần cân nhắc field/method do compiler sinh ra và method bridge; đừng suy ra mọi phần tử `getDeclaredXxx()` đều tương ứng một khai báo hiển thị nguyên văn trong mã nguồn.

## 7. Những đặc điểm không nên suy ra chỉ từ `Modifier`

Java có các trạng thái hoặc dấu hiệu cần API chuyên biệt:

| Đặc điểm cần hỏi | API phù hợp | Vì sao `Modifier` chưa đủ |
| --- | --- | --- |
| Default method trong interface | `Method.isDefault()` | Không có `Modifier.DEFAULT` |
| Method bridge do compiler sinh ra | `Method.isBridge()` | Bridge là đặc tính method/class file |
| Phương thức có varargs | `Executable.isVarArgs()` | Không có `Modifier.VARARGS` |
| Member do compiler sinh ra | `Member.isSynthetic()` | Không có predicate `Modifier.isSynthetic` |
| Class là enum | `Class.isEnum()` | Không có `Modifier.ENUM` |
| Class là annotation type | `Class.isAnnotation()` | Không có `Modifier.ANNOTATION` |
| Class là record | `Class.isRecord()` | Không có `Modifier.RECORD` |
| Class/interface là sealed | `Class.isSealed()` | Không có `Modifier.SEALED` |

Chú ý: những API trên không có nghĩa tất cả đều là «modifier» trong cú pháp Java; một số đại diện cho thông tin class file hoặc đặc điểm mô hình ngôn ngữ.

Từ Java 20, API `Class.accessFlags()` và `Member.accessFlags()` cung cấp một tập `AccessFlag` có tính kiểu hóa, thuận tiện để đọc cả access flags ngoài tập modifier cổ điển. Nhưng **trong dự án phải chạy Java 17**, hãy dùng `getModifiers()` + `Modifier` và những phép kiểm tra chuyên biệt có sẵn; không gọi `accessFlags()` nếu cần hỗ trợ Java 17.

`Modifier.STRICT`/`isStrict` cũng đòi hỏi đọc theo phiên bản Java: từ Java 17 biểu thức dấu phẩy động mặc định đã strict, vì vậy sự hiện diện hay vắng mặt của cờ này không phải phép thử «mã có tính toán số thực chính xác hay không».

## 8. Modifier không đồng nghĩa với quyền truy cập có hiệu lực

Đây là hai câu hỏi khác nhau:

1. **Thành viên khai báo gì?** Đọc `field.getModifiers()` rồi `Modifier.isPrivate(...)` hoặc `Modifier.isPublic(...)`.
2. **Caller này có thể truy cập thành viên trên receiver cụ thể không?** Dùng `AccessibleObject.canAccess(receiver)`, cân nhắc quy tắc Java access checks và giới hạn module.

Ví dụ:

```java
Field field = type.getDeclaredField("token");

boolean declaredPrivate =
        Modifier.isPrivate(field.getModifiers());

// 'instance' là đối tượng phù hợp với field instance 'token'.
boolean currentlyAccessible = field.canAccess(instance);
```

`declaredPrivate` không thay đổi khi accessibility checks được suppress. Nếu cố truy cập `private` field từ caller không có quyền, chỉ biết cờ `private` không làm API truy cập thành công. `trySetAccessible()` có thể yêu cầu suppress Java language access checks **khi module system cho phép**; nó có thể trả `false`. `setAccessible(true)` có thể ném `InaccessibleObjectException`. Các thiết lập này cũng không biến `private` thành `public` và không khiến `getModifiers()` trả giá trị khác.

Ngược lại, member có cờ `public` vẫn có thể không truy cập được từ module khác nếu class chứa nó không accessible hoặc package không được module `exports` thích hợp. Vì vậy, **không dùng `Modifier.isPublic(member.getModifiers())` làm quyết định duy nhất rằng reflective invocation sẽ thành công**.

Nếu mục tiêu là kiểm tra khả năng truy cập trước lời gọi, hãy xác định receiver, loại member (static/instance), class khai báo và module/caller context. `canAccess(null)` phù hợp với static member hoặc constructor, còn instance member cần receiver phù hợp; truyền sai receiver sẽ gây lỗi.

## 9. Lỗi phổ biến và cách sửa

### Lỗi A — So sánh nguyên số mask

Sai:

```java
boolean isPublic = field.getModifiers() == Modifier.PUBLIC;
```

Một field `public static` cũng là `public` nhưng biểu thức sai. Đúng: `Modifier.isPublic(field.getModifiers())` hoặc `(mask & Modifier.PUBLIC) != 0`.

### Lỗi B — Nhầm «có bất kỳ cờ» với «có đủ mọi cờ»

Sai khi phải kiểm tra đồng thời `static` và `final`:

```java
boolean staticAndFinal =
        (field.getModifiers() & (Modifier.STATIC | Modifier.FINAL)) != 0;
```

Biểu thức này cũng đúng khi chỉ có `static`. Sửa:

```java
int required = Modifier.STATIC | Modifier.FINAL;
boolean staticAndFinal = (field.getModifiers() & required) == required;
```

### Lỗi C — Suy luận truy cập từ cờ `public`

`public` chỉ là một phần điều kiện của cơ chế Java access control. Với reflection, caller, package, declaring class và Java Platform Module System đều liên quan. Kiểm tra `canAccess` hoặc `trySetAccessible` khi thật sự cần thao tác member.

### Lỗi D — Nghĩ `final`/`volatile` là giải pháp chung cho bất biến hoặc thread safety

`final` bảo vệ ràng buộc nhất định của biến, phương thức hoặc lớp tùy ngữ cảnh. `volatile` quy định visibility/ordering cho field; với thao tác read-modify-write như `count++`, cần đồng bộ hoặc công cụ atomic phù hợp.

### Lỗi E — Hiển thị `Modifier.toString(mask)` như toàn bộ metadata

Một method có thể là `bridge`, `synthetic` hoặc `default` mà chuỗi modifier không ghi đủ. Kiểm tra `isBridge()`, `isSynthetic()`, `isDefault()` tương ứng; với `sealed` và `record` dùng API của `Class`.

### Lỗi F — Chọn sai tập member

Dùng `getMethods()` rồi kết luận class không có method `private` là sai vì hàm đó chỉ trả method `public`. Dùng `getDeclaredMethods()` để quét các method khai báo trực tiếp, và xử lý riêng việc kế thừa khi cần.

## 10. Checklist khi viết công cụ Reflection

Khi viết bộ phân tích class, framework đăng ký method hay công cụ kiểm tra field:

1. Xác định bạn muốn metadata của **lớp, field, method, constructor hay parameter**.
2. Chọn nhóm `getDeclaredXxx` hay `getXxx` phù hợp với phạm vi thành viên.
3. Lưu `int modifiers = member.getModifiers()` và dùng `Modifier.isXxx` cho các điều kiện đơn; dùng bitmask khi cần kiểm tra kết hợp.
4. In `Modifier.toString(modifiers)` để hỗ trợ đọc; đừng dùng chuỗi này thay toàn bộ thông tin API.
5. Bổ sung các API chuyên biệt: `isSynthetic`, `isBridge`, `isDefault`, `isVarArgs`, `isRecord`, `isSealed` tùy mục tiêu và phiên bản Java.
6. Trước khi truy cập/gọi thực tế, thực hiện **access check** theo đúng caller/receiver/module; cờ khai báo chưa phải quyền thao tác.

**Ghi nhớ:** `getModifiers()` trả về **các bit mô tả khai báo**; `Modifier.isXxx()` là cách kiểm tra ý nghĩa của từng bit; `Modifier.toString()` là cách hiển thị quen thuộc. Đọc modifier chính xác đòi hỏi biết **member nào** đang xét và **câu hỏi thuộc metadata hay quyền truy cập thực tế**.
