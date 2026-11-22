# Đọc field static bằng Reflection: đối số đích bị bỏ qua

## 1. Vấn đề: vì sao Field.get(null) vẫn đọc được giá trị?

Trong Java, **field static thuộc về lớp** (chính xác hơn, thuộc về lớp định nghĩa field trong từng môi trường nạp lớp), thay vì thuộc riêng từng đối tượng. Do đó, khi gọi Reflection để đọc một field static, đối số `obj` của `Field.get(Object obj)` **không được dùng để chọn nơi chứa giá trị**. Theo Javadoc của `java.lang.reflect.Field`:

- Nếu field là **static**: `obj` **bị bỏ qua**; có thể truyền `null`, một instance của lớp khai báo hoặc thậm chí một đối tượng không liên quan.
- Nếu field là **instance**: `obj` bắt buộc là instance của lớp/interface khai báo field (hoặc subtype tương thích); `null` gây `NullPointerException`, đối tượng không tương thích gây `IllegalArgumentException`.

Ví dụ cơ bản:

```java
class Settings {
    public static int port = 8080;
    public int id = 7;
}
```

Khi đã có `Field portField = Settings.class.getDeclaredField("port")`, các lời gọi `portField.get(null)`, `portField.get(new Settings())` và `portField.get(new Object())` đều đọc cùng **giá trị static hiện tại** là `8080`, nếu chưa có code khác cập nhật field. Việc đọc **không cần tạo bất kỳ `Settings` instance nào**.

Ngược lại, `id` là instance field: `Settings.class.getDeclaredField("id").get(null)` không hợp lệ, bởi không có instance nào để tìm giá trị `id`.

**Quy tắc cần nhớ:** Field object quyết định *field nào được đọc*, còn `obj` chỉ định *instance nào cần đọc* **nếu field đó không static**. Với field static, giá trị gắn với `Field.getDeclaringClass()`, không gắn với đối tượng truyền vào.

## 2. Nhận biết field static trước khi đọc

Reflection trả về một `Field` đại diện cho khai báo, gồm tên, kiểu, modifier và lớp khai báo. Cách tương thích Java 17+ để kiểm tra static:

```java
Field f = Settings.class.getDeclaredField("port");
boolean isStatic = Modifier.isStatic(f.getModifiers());
Object value = f.get(isStatic ? null : someInstance);
```

Đoạn trên chỉ là **mảnh mã minh họa**, cần đặt trong một phương thức có xử lý `NoSuchFieldException`/`IllegalAccessException` và cung cấp biến `someInstance`, các import cần thiết.

- `f.getModifiers()` trả về bit mask modifier; `Modifier.isStatic(...)` là cách kiểm tra chuẩn.
- `f.getDeclaringClass()` trả về lớp/interface **khai báo chính field**, không nhất thiết là `getClass()` của đối tượng đích mà bạn đang có.
- `f.getType()` trả về kiểu khai báo của **giá trị field** (ví dụ `int.class` với `port`), không cho biết field static hay instance.
- `f.getName()` cho tên field; `getDeclaredField("port")` tìm khai báo trực tiếp trên `Settings`, còn `getField("port")` tìm field `public` theo quy tắc tìm kiếm public field, gồm thành viên kế thừa.

Trên JDK 20+, `f.accessFlags().contains(AccessFlag.STATIC)` cũng biểu diễn kiểm tra này bằng tập cờ. Tuy nhiên, `accessFlags()` **không có trên JDK 17**; dùng `Modifier` nếu mã cần chạy trên JDK 17.

Trong mã xử lý nhiều field bất kỳ, nên rẽ nhánh rõ ràng:

```java
Object read(Field field, Object instance) throws IllegalAccessException {
    if (Modifier.isStatic(field.getModifiers())) {
        return field.get(null);
    }
    return field.get(instance);
}
```

Đây là phương thức minh họa, không phải chương trình hoàn chỉnh. Cách viết `get(null)` cho field static làm rõ ý định và tránh tạo/đánh giá những biểu thức đối tượng thừa; ở nhánh instance, người gọi phải cung cấp đối tượng phù hợp và quyền truy cập vẫn được kiểm tra.

## 3. Chương trình Java 17+ độc lập, có thể biên dịch/chạy

Lưu toàn bộ mã sau vào **`StaticFieldReadDemo.java`**:

```java
import java.lang.reflect.Field;
import java.lang.reflect.Modifier;

public class StaticFieldReadDemo {
    public static class Settings {
        static { System.out.println("Settings initialized"); }
        public static int port = 8080;
        public int id = 7;
    }

    static Object makeTarget() {
        System.out.println("argument evaluated");
        return new Object();
    }

    public static void main(String[] args) throws ReflectiveOperationException {
        Class<?> type = Class.forName(Settings.class.getName(), false,
                StaticFieldReadDemo.class.getClassLoader());

        Field staticField = type.getDeclaredField("port");
        Field instanceField = type.getDeclaredField("id");

        System.out.println("static modifier = "
                + Modifier.isStatic(staticField.getModifiers()));
        System.out.println("before first get");
        System.out.println("get(null) = " + staticField.get(null));
        System.out.println("get(unrelated) = " + staticField.get(new Object()));
        System.out.println("get(expression) = " + staticField.get(makeTarget()));
        System.out.println("getInt(null) = " + staticField.getInt(null));
        System.out.println("instance get = " + instanceField.get(new Settings()));

        try {
            instanceField.get(null);
        } catch (NullPointerException ex) {
            System.out.println("instance with null = NullPointerException");
        }
        try {
            instanceField.get(new Object());
        } catch (IllegalArgumentException ex) {
            System.out.println("instance with unrelated = IllegalArgumentException");
        }

        staticField.setInt(null, 9090);
        System.out.println("after static set = " + staticField.getInt(new Object()));
    }
}
```

Biên dịch/chạy trong thư mục chứa tệp bằng JDK 17 trở lên:

```bash
javac StaticFieldReadDemo.java
java StaticFieldReadDemo
```

Stdout **đã được kiểm chứng khi chạy trên JDK 24**:

```text
static modifier = true
before first get
Settings initialized
get(null) = 8080
get(unrelated) = 8080
argument evaluated
get(expression) = 8080
getInt(null) = 8080
instance get = 7
instance with null = NullPointerException
instance with unrelated = IllegalArgumentException
after static set = 9090
```

### Phân tích tuần tự

1. `Class.forName(name, false, loader)` nạp/nhận diện lớp mà **không chủ động khởi tạo lớp** khi tham số `initialize` là `false`. `Settings.class.getName()` và `getDeclaredField(...)` cho phép xem metadata mà chưa cần tạo instance; ví dụ cố ý chưa gọi `new Settings()`.
2. `Modifier.isStatic(staticField.getModifiers())` là `true`, nhưng mới chỉ kiểm tra metadata.
3. Lần đầu `staticField.get(null)` **khởi tạo `Settings`** nếu chưa khởi tạo; vì thế dòng `Settings initialized` xuất hiện **sau** `before first get` và **trước** `get(null) = 8080`. Khởi tạo xong mới có thể đọc giá trị field.
4. `staticField.get(new Object())` không ném `IllegalArgumentException` dù đối tượng đích không thuộc `Settings`, bởi field static **bỏ qua đối số đích**.
5. Với `staticField.get(makeTarget())`, **Java vẫn đánh giá biểu thức đối số** `makeTarget()` trước khi bước vào `Field.get`. Vì vậy `argument evaluated` vẫn được in. Chỉ **giá trị tham chiếu trả về** của biểu thức mới bị phương thức bỏ qua khi xác định nơi đọc static field.
6. `getInt(null)` đọc field `int` trực tiếp dưới dạng primitive; `get(null)` trả `Object` chứa `Integer` nhờ boxing.
7. `instanceField.get(new Settings())` đọc đúng instance field `id`. Hai lời gọi tiếp theo minh họa lỗi với `null` và đối tượng sai kiểu đối với **instance field**.
8. `staticField.setInt(null, 9090)` minh họa quy tắc tương tự ở thao tác **ghi** static field không `final`. Giá trị mới được đọc lại qua `getInt(new Object())`; đối tượng `new Object()` vẫn bị bỏ qua.

## 4. Bảng phân biệt các tình huống

Giả sử field có quyền truy cập phù hợp, lớp khởi tạo thành công và chưa bị thay đổi bởi luồng khác:

| Thao tác | Static field | Instance field |
| --- | --- | --- |
| `field.get(null)` | Hợp lệ, đọc giá trị thuộc lớp khai báo | `NullPointerException` |
| `field.get(new DeclaringClass())` | Hợp lệ; instance bị bỏ qua | Hợp lệ, đọc giá trị của instance được truyền |
| `field.get(new Unrelated())` | Hợp lệ; không kiểm tra target có thuộc lớp khai báo không | `IllegalArgumentException` |
| `field.getInt(null)` nếu field có kiểu `int` | Hợp lệ, trả `int` | `NullPointerException` |
| `field.set(null, value)` | Target bị bỏ qua; thao tác ghi còn phụ thuộc quyền truy cập, kiểu và `final` | `NullPointerException` |
| `field.getDeclaringClass()` | Lớp/interface sở hữu field | Lớp/interface sở hữu field |

**Giới hạn của bảng:** `field.get(new Unrelated())` vẫn thực hiện việc **tạo `new Unrelated()` trước khi gọi `get`**; nếu constructor có tác dụng phụ hoặc lỗi, điều đó vẫn xảy ra. “Bị bỏ qua” chỉ có nghĩa là Reflection không dùng **đối tượng đã được truyền vào** để chọn storage của static field.

Một lựa chọn rất nên dùng là `field.get(null)` cho static field: rõ nghĩa, không tạo object, không đánh giá biểu thức thừa.

## 5. Static field là dữ liệu của lớp nào?

Xét **field hiding**, khi lớp con và lớp cha cùng khai báo static field trùng tên:

```java
class Parent {
    public static int count = 10;
}

class Child extends Parent {
    public static int count = 20;
}
```

Với metadata lấy từ **khai báo lớp cha**:

```java
Field parentCount = Parent.class.getDeclaredField("count");
Object result = parentCount.get(new Child()); // 10
```

Đây là mảnh mã minh họa và cần các import/ngoại lệ Reflection tương ứng. `Field` ở đây trỏ thẳng tới **`Parent.count`**. Mặc dù một instance `Child` được truyền vào, static target bị bỏ qua; không có “dynamic dispatch” chọn `Child.count`. Để đọc `Child.count`, phải có `Field childCount = Child.class.getDeclaredField("count")`.

Điều này rất khác với **instance method override**: đọc field (kể cả field instance) không áp dụng quy tắc dynamic dispatch theo class thực tế như gọi method override. `Field.getDeclaringClass()` là căn cứ đúng để biết field thuộc lớp nào.

**Class loader cũng là phần của danh tính lớp.** Hai `Class<?>` có cùng binary name nhưng được nạp bởi hai defining class loader khác nhau là hai runtime class khác nhau và có trạng thái static riêng. Nếu công cụ Reflection dùng sai `Class`/`ClassLoader`, việc thấy giá trị static khác nhau không có nghĩa `get` đã sử dụng target; hãy kiểm tra `field.getDeclaringClass()` và class loader thực tế.

## 6. Class initialization: đọc static có thể kích hoạt `<clinit>`

Javadoc của `Field.get(Object)` quy định rằng **nếu underlying field là static, lớp khai báo field sẽ được khởi tạo nếu trước đó chưa được khởi tạo**. Vì vậy, đọc bằng Reflection không chỉ là thao tác “xem metadata” thuần túy.

Các thao tác thường dễ bị nhầm:

- `Class.forName(name, false, loader)`: yêu cầu không initialize lớp ở bước tìm/nhận `Class`.
- `SomeClass.class`, `Field.getName()`, `Field.getModifiers()` và `Class.getDeclaredField(...)`: dùng để tham chiếu/tra metadata; **không đồng nghĩa với việc đọc giá trị static**.
- `field.get(null)` / `field.getInt(null)` với static field: kích hoạt khởi tạo lớp khai báo, nếu chưa được khởi tạo, rồi mới đọc.
- Nếu static initializer thất bại, lời gọi có thể ném `ExceptionInInitializerError` (hoặc một lỗi khởi tạo liên quan). Những lần sử dụng tiếp theo có thể gặp `NoClassDefFoundError` do lớp đã ở trạng thái khởi tạo lỗi.

Trong ví dụ chính, chính dòng `get(null)` đã làm khối `static { ... }` chạy. Đây là điểm quan trọng khi viết scanner cấu hình hoặc plugin: việc “đọc static để kiểm tra” có thể làm chạy mã khởi tạo ngoài ý muốn, mở kết nối hoặc thực hiện tác vụ khác.

**Trường hằng compile-time không được đánh đồng với mọi static field.** Với `static final int LIMIT = 123`, một biểu thức Java thông thường tham chiếu hằng có thể được compiler inline nên hành vi khởi tạo khác với `Field.get(null)`. Theo quy tắc của Reflection, đọc underlying static field vẫn yêu cầu initialize declaring class nếu chưa khởi tạo. Không dựa vào việc inlining của lời gọi trực tiếp để dự đoán hành vi Reflection.

## 7. Đọc primitive static field: get hay getInt/getLong?

`Field.get(Object)` luôn trả về `Object`. Với field primitive `int`, giá trị được boxing thành `Integer`; với field reference, trả đối tượng được lưu trong field (có thể là `null`).

`Field` còn có các biến thể `getBoolean`, `getByte`, `getChar`, `getShort`, `getInt`, `getLong`, `getFloat`, `getDouble`. **Quy tắc static bỏ qua target cũng áp dụng** cho các cách đọc typed này.

Ví dụ với field `public static int port = 8080`:

```java
Object boxed = staticField.get(null); // Integer(8080)
int primitive = staticField.getInt(null); // 8080
long widened = staticField.getLong(null); // 8080L
```

Đây là đoạn minh họa trong phạm vi ví dụ chính, với `staticField` đã được lấy từ lớp `Settings`.

Typed getter sử dụng **primitive widening conversion** khi hợp lệ. Vì `int` có thể widen thành `long`, `getLong(null)` dùng được với underlying `int`; nhưng `getInt(null)` không thể đọc underlying `long` bằng narrowing về `int` và có thể ném `IllegalArgumentException`. Đừng nhầm việc field static bỏ qua *target* với việc nó bỏ qua *kiểm tra kiểu dữ liệu*.

Với field static có kiểu tham chiếu `String`, dùng `get(null)` rồi cast đúng kiểu, sau khi đã xác nhận metadata `getType()` hoặc điều kiện thực tế. Không gọi `getInt(null)` để đọc một field `String`.

## 8. Các loại lỗi cần tách biệt

| Hiện tượng | Nguyên nhân đúng cần kiểm tra |
| --- | --- |
| `NoSuchFieldException` từ `getDeclaredField(...)` | Không có field tên đó **được khai báo trực tiếp** trên `Class` đang hỏi; có thể field kế thừa, tên sai hoặc sai class loader. |
| `IllegalAccessException` khi `get(null)` | Field không cho phép caller truy cập theo quy tắc Java/module hiện hành. Target `null` không bỏ qua access check. |
| `InaccessibleObjectException` từ `setAccessible(true)` | Không thể cho phép deep reflection do quy tắc module và điều kiện truy cập. |
| `NullPointerException` khi `get(null)` | Có thể đang đọc **instance field**; xác nhận `Modifier.isStatic(f.getModifiers())` trước. |
| `IllegalArgumentException` khi `get(wrongInstance)` | Với instance field, target sai kiểu; với typed getter, còn có thể do kiểu primitive không chuyển đổi hợp lệ. Với **static Field.get(Object)**, riêng target không liên quan **không** là lý do lỗi này. |
| `ExceptionInInitializerError` khi đọc static | Static initialization thất bại; kiểm tra nguyên nhân ở khối static/khởi tạo field của lớp khai báo. |
| Giá trị khác giữa các lần đọc | Có code đã ghi lại field, các luồng thay đổi trạng thái hoặc bạn đang xem hai runtime class từ class loader khác nhau. |

Với field `private static`, truyền `null` vẫn được nhưng **không tự vượt quyền private**. Có thể dùng `trySetAccessible()` khi module/điều kiện cho phép; không bảo đảm thành công. Với JDK 17+, strong encapsulation của module JDK và các named module có thể hạn chế reflection. Prefer public API hoặc thiết kế rõ quyền mở package, thay vì coi `setAccessible(true)` là luôn thành công.

`Field.set(Object, Object)` và `setInt` cũng bỏ qua đối số target nếu field static; tuy nhiên quyền ghi, tính `final`, kiểu giá trị, class initialization và module vẫn được áp dụng. Nhiều **static final field là non-modifiable** qua Reflection ngay cả sau khi bật `setAccessible(true)`; chỉ nên minh họa ghi lên field static **không final** như ví dụ.

## 9. Các hiểu nhầm thường gặp

**Nhầm 1 — `null` luôn gây NullPointerException.** Không đúng với `Field.get(null)` trên **static field**. Với instance field, lỗi là đúng vì thiếu đối tượng chứa giá trị.

**Nhầm 2 — truyền sai class sẽ khiến field static bị đọc từ class khác.** Không. `Field` đã gắn với declaring class ngay khi được tra cứu; `obj` không ảnh hưởng địa chỉ lưu trữ static.

**Nhầm 3 — “ignored” nghĩa là biểu thức đối số không chạy.** Sai. Java đánh giá các đối số trước khi gọi phương thức. `field.get(expensive())` vẫn có thể chạy `expensive()`, ném lỗi hoặc tạo tác dụng phụ. Chỉ giá trị target cuối cùng không được dùng bởi `get` nếu field static.

**Nhầm 4 — Reflection tự khởi tạo class ngay khi hỏi tên field.** Không nhất thiết. Việc tra cứu `getDeclaredField` khác với việc đọc **giá trị static**; `get` có thể kích hoạt class initialization.

**Nhầm 5 — dùng một `new Object()` thì tránh được kiểm tra quyền truy cập.** Sai. Bỏ qua target không bỏ qua `IllegalAccessException`, encapsulation hay quyền module.

**Nhầm 6 — getInt() hoạt động cho mọi kiểu numeric.** Sai. Typed getter thực hiện chuyển đổi primitive hợp lệ theo hướng widening; không tự narrowing, không parse `String` và không biến field kiểu tham chiếu thành primitive tùy ý.

**Nhầm 7 — field static dùng dynamic dispatch giống method override.** Không. Field hiding khác method overriding; `Field.getDeclaringClass()` cho biết đúng field được đọc.

**Nhầm 8 — muốn đọc static bắt buộc tạo instance.** Không. `field.get(null)` là cách đọc có chủ ý và thường là cách dễ hiểu nhất, khi đã đủ quyền.

## 10. Áp dụng trong framework / utility phản chiếu

Khi viết reflection utility xử lý cả static và instance field:

1. **Lấy đúng `Class`** cần khảo sát; nếu có plugin/class loader, xác định loader của lớp.
2. **Tra cứu đúng `Field`** bằng `getDeclaredField` hoặc `getField` theo phạm vi mong muốn; xử lý `NoSuchFieldException`.
3. **Đọc metadata `Modifier.isStatic(field.getModifiers())`** và chuẩn bị target: `null` cho static, instance thực cho non-static.
4. **Kiểm tra khả năng truy cập**; tôn trọng Java access control/module boundary. Nếu field không public, xem có thật sự cần reflection sâu hay có accessor API hợp lệ.
5. **Đọc bằng getter phù hợp** với field type: `get(null)` cho reference/muốn boxing, `getInt(null)` cho primitive int, v.v. Xem xét khả năng static initialization phát sinh tác dụng phụ.
6. **Diễn giải dữ liệu** theo declaring class và cấu trúc field; không suy từ target runtime class rằng field static có “bản sao riêng” trên object.

Một helper gọn có thể dùng cho field đã có quyền truy cập:

```java
import java.lang.reflect.Field;
import java.lang.reflect.Modifier;

public final class FieldReader {
    private FieldReader() {}

    public static Object read(Field field, Object instance)
            throws IllegalAccessException {
        Object target = Modifier.isStatic(field.getModifiers())
                ? null
                : instance;
        return field.get(target);
    }
}
```

Đây là **một lớp utility hoàn chỉnh** nhưng không có `main`; nó được gọi từ ứng dụng khác. Nó không tự bypass private/module access, không đảm bảo target instance đúng kiểu, và không ngăn tác dụng phụ khi class initialization xảy ra. Với field instance, `instance` phải phù hợp; với field static, caller có thể truyền `null`. Java reflection vẫn thực hiện access check bình thường.

## 11. Tự kiểm tra

Giả sử `Field score` trỏ tới `public static int score = 50` trong `Game` và quyền truy cập bình thường:

1. `score.get(null)` cho gì? **`Integer` chứa `50`** qua boxing.
2. `score.get(new Object())` có gây `IllegalArgumentException` vì sai target không? **Không**; target bị bỏ qua.
3. `score.getInt(null)` cho gì? **Primitive `int` bằng `50`**.
4. Nếu `static { System.out.println("init"); }` chưa chạy, lần đầu `score.get(null)` có thể làm gì? **Khởi tạo `Game` và in `init` trước khi trả giá trị**, nếu lớp chưa được initialize.
5. Với `public int level = 2`, `levelField.get(null)` cho gì? **`NullPointerException`** vì thiếu instance.
6. Nếu `score` được khai báo `private static` trong named module không cho phép deep reflection, truyền `null` có chữa lỗi quyền truy cập không? **Không**.
7. Nếu `score.get(makeTarget())`, hàm `makeTarget()` có được chạy không? **Có**, vì biểu thức đối số được đánh giá trước; target object tạo ra vẫn bị bỏ qua sau đó.
8. Hai lớp khác nhau đều có `static int score`: Reflection đọc field nào? **Field của declaring class gắn với đối tượng `Field`**, không dựa trên class của target được truyền.

## 12. Tài liệu chính thức

- [Oracle Java SE 17 — Field.get(Object), set(Object,Object) và typed getters](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Field.html)
- [Oracle Java SE 25 — Field.get(Object), Javadoc](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/reflect/Field.html)
- [Oracle Java SE 17 — Modifier.isStatic(int)](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Modifier.html)
- [Java Language Specification 8.3.1.1 — static Fields](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.3.1.1)
- [Java Language Specification 12.4 — Initialization of Classes and Interfaces](https://docs.oracle.com/javase/specs/jls/se17/html/jls-12.html#jls-12.4)
