# Kiểm thử Reflection với non-static inner class, enum, record và sealed type

## 1. Vì sao bốn kiểu này cần ca kiểm thử riêng?

Khi viết một công cụ dùng Java Reflection để khám phá, tạo instance, đọc metadata hoặc kiểm tra cấu trúc lớp, không thể coi mọi `Class<?>` như một top-level class thông thường có constructor không tham số và các field có thể chỉnh sửa. **Non-static inner class, enum, record và sealed type** có những hợp đồng khác nhau về constructor, định danh, tính bất biến, quan hệ kế thừa và khả năng tạo đối tượng.

Bài học này tập trung vào **cách thiết kế bài kiểm thử cho công cụ Reflection**. Mục tiêu là kiểm tra hành vi được Java/JDK bảo đảm, tách khỏi chi tiết do compiler sinh ra, và viết assertions rõ ràng thay vì chỉ in metadata rồi suy đoán.

| Loại kiểu | Điều kiện quan trọng | Điều gì nên kiểm thử? |
| --- | --- | --- |
| Non-static member inner class | Instance của outer class gắn với inner instance | `isMemberClass()`, `getEnclosingClass()`, constructor có tham số outer, tạo instance đúng. |
| Enum | Tập constant do khai báo enum quản lý; Reflection không được tạo enum instance mới | `isEnum()`, `getEnumConstants()`, `Field.isEnumConstant()`, `Enum.valueOf` và thử constructor bị từ chối. |
| Record | State được khai báo bởi record components và các field thành phần `final` | `isRecord()`, `getRecordComponents()`, canonical constructor, accessor, không chỉnh sửa field thành phần bằng `Field.set`. |
| Sealed class/interface | Chỉ những direct subtype được cho phép trong `permits` | `isSealed()`, `getPermittedSubclasses()` và kiểm chứng danh sách direct permitted types. |

**Không có một bộ lọc field/constructor chung có thể thay thế những kiểm thử này.** Ví dụ, `getDeclaredFields()` có thể thấy field hỗ trợ cho inner class, còn `getRecordComponents()` lại mô tả thành phần của record theo quy tắc ngôn ngữ.

## 2. Chuẩn bị cách kiểm thử an toàn và ổn định

Dùng **JDK 17 trở lên** vì record và sealed class/interface trở thành tính năng chính thức từ Java 16 và Java 17. Một file demo chạy ở classpath đơn giản giúp tập trung vào ngữ nghĩa Reflection, tránh nhầm lỗi module với lỗi thiết kế kiểu.

Các quy tắc thiết kế test:

1. **Kiểm tra điều kiện bằng assertion**: sử dụng `AssertionError`/JUnit hoặc kiểm tra điều kiện rõ ràng; không chỉ quan sát `println`.
2. **Kiểm tra metadata trước khi gọi thực thi**: tìm constructor khác với `Constructor.newInstance`, đọc field metadata khác `Field.get` hoặc `Field.set`.
3. **Dùng API chuyên biệt**: `isEnum` và `getEnumConstants` cho enum, `isRecord` và `getRecordComponents` cho record, `isSealed` và `getPermittedSubclasses` cho sealed type.
4. **Không chốt tên/compiler artifacts**: không assert field `this$0`, `$VALUES`, tên số của local/anonymous class, hoặc thứ tự các mảng field/method do Reflection trả về.
5. **Kiểm tra lỗi mong đợi đúng loại**: ví dụ `NoSuchMethodException` khi tìm constructor không tồn tại; `IllegalArgumentException` khi cố tạo enum bằng Reflection; `IllegalAccessException` khi cố sửa field thành phần record sau khi bật accessible trong ví dụ.
6. **Tách test harness khỏi ứng dụng thật**: kiểm thử cùng classpath/nest dễ truy cập non-public member; khi triển khai vào named module khác phải thêm test về access boundary.

## 3. Non-static inner class: constructor cần outer instance

Xét `Outer.Inner` là **member class không khai báo `static`**. Mỗi instance `Inner` gắn với một instance `Outer`. Vì vậy constructor ở mức JVM có tham số đầu đại diện enclosing instance của `Outer`, ngay cả khi constructor ở mã nguồn chỉ khai báo `Inner(String label)`.

Ví dụ khái niệm:

~~~java
class Outer {
    class Inner {
        Inner(String label) {}
    }
}
~~~

Đây chỉ là mảnh khai báo; chương trình hoàn chỉnh nằm ở phần 7.

Kiểm thử phù hợp:

- `Outer.Inner.class.isMemberClass()` phải là `true`: đây là **member class**.
- `getEnclosingClass() == Outer.class` xác nhận lớp bao ngoài.
- `getDeclaredConstructor()` **không tồn tại** trong ví dụ chỉ có constructor nhận `String` và enclosing instance; không nên tự giả định có zero-argument constructor.
- `getDeclaredConstructor(Outer.class, String.class)` tìm được constructor phản chiếu.
- `newInstance(new Outer(), "A")` tạo inner instance thành công khi phạm vi truy cập phù hợp.

**Phân biệt:** `Outer.StaticNested` được khai báo `static` không cần enclosing instance. **Local class** nằm trong phương thức có quy tắc capture/constructor khác; đừng đồng nhất mọi nested/local/anonymous class. Các field hỗ trợ chứa outer reference do compiler tạo có thể là synthetic nhưng tên/biểu diễn cụ thể không được dùng làm hợp đồng test.

Nếu gọi `Class.getConstructors()` thay vì `getDeclaredConstructors()`, bạn chỉ xem các constructor `public`. Khi constructor trong ví dụ là package-private, dùng `getDeclaredConstructor` phù hợp hơn. Với module khác, việc tìm thấy constructor không có nghĩa có quyền gọi nó; `canAccess`, `trySetAccessible` và `InaccessibleObjectException` phải được xử lý tùy tình huống.

## 4. Enum: liệt kê constant, không tạo instance qua constructor

Đối với:

~~~java
enum Stage { NEW, DONE }
~~~

`Stage.class.isEnum()` trả `true`, và `Stage.class.getEnumConstants()` trả các constant theo **thứ tự khai báo**: `[NEW, DONE]`. `Enum.valueOf(Stage.class, "DONE")` tra cứu constant hiện có. Dùng `getDeclaredFields()` để nhìn toàn bộ field sẽ có thể gặp cả thành phần liên quan hiện thực, vì vậy nếu thực sự cần phân biệt field biểu diễn enum constant, dùng `Field.isEnumConstant()`.

### Constructor enum là ngoại lệ có chủ đích

`Stage.class.getDeclaredConstructors()` có thể cho thấy constructor của enum, nhưng **`Constructor.newInstance` không được phép tạo thêm enum instance**. API ném `IllegalArgumentException` khi declaring class của constructor là enum, kể cả sau khi đã vượt được kiểm tra quyền truy cập thông thường.

Đừng dùng việc tìm thấy constructor làm lý do để thử `newInstance` cho tất cả `Class<?>`. Factory của enum là các constant đã định nghĩa, truy cập qua `valueOf` hoặc `getEnumConstants`.

**Cạm bẫy:** enum constant có class body riêng có thể có runtime class là một subclass đặc biệt của enum; `constant.getClass().isEnum()` không nhất thiết `true`. `constant.getDeclaringClass()` cho enum type đã khai báo. Không assert các tên lớp đặc thù của compiler.

## 5. Record: kiểm thử components và bất biến của state

Đối với:

~~~java
record Person(String name, int age) {}
~~~

`Person.class.isRecord()` là `true`. `getRecordComponents()` trả các `RecordComponent` theo **thứ tự record header**: `name` rồi `age`. Mỗi component có metadata tên, kiểu và accessor; `getAccessor()` trả `Method` tương ứng.

Ví dụ `Person.class.getDeclaredConstructor(String.class, int.class)` tìm **canonical constructor** với tham số theo thứ tự của record header. Trong demo, constructor này được gọi qua Reflection và tạo `new Person("Lan", 20)`.

### Không coi `setAccessible(true)` là quyền sửa mọi field

Field thành phần của record là `final` theo cơ chế bất biến của record. Trong `java.lang.reflect.Field`, các field `static final`, field `final` của hidden class và field `final` của record là nhóm **non-modifiable final fields**. Kể cả khi `setAccessible(true)` được chấp nhận để đọc, không thể dùng `Field.set` sửa field thành phần record. Với ví dụ, lời gọi `age.set(person, 99)` ném `IllegalAccessException` và `person.age()` vẫn bằng `20`.

Test nên kiểm tra cả **exception** và **state không đổi**. Không nên coi “có thể lấy `Field`” tương đương “có thể ghi field”.

### Field và component không hoàn toàn đồng nhất

`getDeclaredFields()` mô tả field JVM trong lớp, trong khi `getRecordComponents()` phản ánh **cấu trúc khai báo record**. Nếu công cụ xử lý schema/DTO từ record, thường nên lấy record components trước. Annotation trên component, field và accessor có quy tắc `@Target`/propagation riêng: phải kiểm tra annotation ở đúng vị trí mà công cụ sử dụng.

Một class thường trả `null` từ `getRecordComponents()`; đừng duyệt kết quả trước khi xác nhận `isRecord()` hoặc xử lý `null`.

## 6. Sealed type: danh sách direct permitted subclasses

Ví dụ:

~~~java
sealed interface Shape permits Circle, Rectangle {}

record Circle(int radius) implements Shape {}

final class Rectangle implements Shape {}
~~~

Đây là **mảnh khai báo cùng file/package**; chương trình chạy độc lập có khai báo tương đương ở phần 7. `Shape.class.isSealed()` là `true` và `getPermittedSubclasses()` trả các kiểu được phép **trực tiếp** triển khai/mở rộng `Shape`.

Các phép kiểm tra:

- `Shape.class.getPermittedSubclasses()` chứa `Circle.class` và `Rectangle.class`.
- `Circle.class.isRecord()` là `true`; record luôn là final, nên có thể là subtype trực tiếp hợp lệ của sealed interface.
- `Rectangle.class` được khai báo `final`, không phải sealed; `isSealed()` là `false`.
- `getPermittedSubclasses()` không có nghĩa “mọi subtype gián tiếp có thể tồn tại”: trong phân cấp cho phép nhánh `non-sealed`, có thể có nhiều thế hệ con khác. API đang mô tả **direct permitted subtypes**.

**Không dựa vào thứ tự mảng trả về** nếu cần kết quả ổn định; demo ánh xạ sang tên rồi sắp xếp trước khi assert. Với non-sealed type, `Class.getPermittedSubclasses()` trả `null`. Gọi `isSealed()` hoặc kiểm tra `null` trước khi duyệt.

Một lưu ý ứng dụng: **sealed interface không hợp lệ làm interface đầu vào cho JDK `Proxy.newProxyInstance`** (API yêu cầu các interface đầu vào không sealed). Đây là quy tắc riêng của dynamic proxy; không có nghĩa không thể viết một lớp `final` cho phép trong `permits`.

## 7. Chương trình kiểm thử hoàn chỉnh trên Java 17+

Tạo file **`ReflectionSpecialTypesTest.java`** với toàn bộ mã sau. Chương trình dùng `check` để ném `AssertionError` nếu phát hiện sai lệch; do đó dòng cuối chỉ xuất hiện khi bốn nhóm kiểm thử đều vượt qua.

~~~java
import java.lang.reflect.Constructor;
import java.lang.reflect.Field;
import java.lang.reflect.RecordComponent;
import java.util.Arrays;
import java.util.List;

public class ReflectionSpecialTypesTest {
    static void check(boolean condition, String message) {
        if (!condition) throw new AssertionError(message);
    }

    static final class Outer {
        class Inner {
            private final String label;

            Inner(String label) { this.label = label; }

            String display() { return "inner:" + label; }
        }
    }

    enum Stage { NEW, DONE }

    record Person(String name, int age) {}

    sealed interface Shape permits Circle, Rectangle {}

    record Circle(int radius) implements Shape {}

    static final class Rectangle implements Shape {}

    static void testInner() throws Exception {
        Class<?> type = Outer.Inner.class;
        check(type.isMemberClass(), "must be a member class");
        check(type.getEnclosingClass() == Outer.class, "wrong enclosing class");

        boolean noZeroArg = false;
        try {
            type.getDeclaredConstructor();
        } catch (NoSuchMethodException expected) {
            noZeroArg = true;
        }
        check(noZeroArg, "unexpected zero-arg constructor");

        Constructor<?> ctor = type.getDeclaredConstructor(Outer.class, String.class);
        Object instance = ctor.newInstance(new Outer(), "A");
        check(((Outer.Inner) instance).display().equals("inner:A"), "wrong inner value");
        System.out.println("inner: outer argument required, value=inner:A");
    }

    static void testEnum() throws Exception {
        Class<Stage> type = Stage.class;
        check(type.isEnum(), "not an enum");
        check(Arrays.equals(type.getEnumConstants(), Stage.values()), "enum constants differ");
        check(Enum.valueOf(type, "DONE") == Stage.DONE, "lookup mismatch");

        List<String> constants = Arrays.stream(type.getDeclaredFields())
                .filter(Field::isEnumConstant).map(Field::getName).sorted().toList();
        check(constants.equals(List.of("DONE", "NEW")), "enum field filter");
        Constructor<?> ctor = type.getDeclaredConstructors()[0];
        ctor.setAccessible(true);
        boolean forbidden = false;
        try {
            ctor.newInstance("INJECTED", 10);
        } catch (IllegalArgumentException expected) {
            forbidden = true;
        }
        check(forbidden, "enum reflection construction must fail");
        System.out.println("enum: [NEW, DONE], reflective construction rejected");
    }

    static void testRecord() throws Exception {
        Class<Person> type = Person.class;
        check(type.isRecord(), "not a record");
        RecordComponent[] components = type.getRecordComponents();
        check(Arrays.stream(components).map(RecordComponent::getName)
                .toList().equals(List.of("name", "age")), "component order");
        Person person = type.getDeclaredConstructor(String.class, int.class)
                .newInstance("Lan", 20);
        check(components[0].getAccessor().invoke(person).equals("Lan"), "bad accessor");

        Field age = type.getDeclaredField("age");
        age.setAccessible(true);
        boolean immutable = false;
        try {
            age.set(person, 99);
        } catch (IllegalAccessException expected) {
            immutable = true;
        }
        check(immutable && person.age() == 20, "record field changed");
        System.out.println("record: [name, age], final field write rejected");
    }

    static void testSealed() {
        check(Shape.class.isSealed(), "not sealed");
        List<String> permitted = Arrays.stream(Shape.class.getPermittedSubclasses())
                .map(Class::getSimpleName).sorted().toList();
        check(permitted.equals(List.of("Circle", "Rectangle")), "permitted classes");
        check(!Circle.class.isSealed() && !Rectangle.class.isSealed(),
                "implementations should not be sealed");
        check(Circle.class.isRecord(), "Circle must be a record");
        System.out.println("sealed: permitted=[Circle, Rectangle]");
    }

    public static void main(String[] args) throws Exception {
        testInner();
        testEnum();
        testRecord();
        testSealed();
        System.out.println("ALL CHECKS PASSED");
    }
}
~~~

Biên dịch với đúng mức ngôn ngữ Java 17 và chạy:

~~~bash
javac --release 17 ReflectionSpecialTypesTest.java
java ReflectionSpecialTypesTest
~~~

**Standard output đã được kiểm chứng:**

~~~text
inner: outer argument required, value=inner:A
enum: [NEW, DONE], reflective construction rejected
record: [name, age], final field write rejected
sealed: permitted=[Circle, Rectangle]
ALL CHECKS PASSED
~~~

### Đọc các kết quả theo từng đặc điểm

1. **Inner:** constructor phản chiếu nhận `Outer` ở vị trí đầu; test tạo được instance đúng và phát hiện không có constructor zero-arg.
2. **Enum:** lấy constant theo thứ tự khai báo, lọc field thật sự là enum constant; constructor hiện diện về metadata nhưng việc tạo mới bị cấm.
3. **Record:** components khớp header và accessor đọc giá trị đúng. `Field.set` bị chặn cho final record component ngay cả khi `setAccessible(true)` thành công trong phạm vi demo.
4. **Sealed:** danh sách permitted class gồm đúng hai direct subtype; kiểm thử không mặc định chúng phải là sealed. `Circle` đồng thời là record.
5. **Kết quả cuối:** `ALL CHECKS PASSED` chỉ xuất hiện nếu tất cả `check` đều thành công.

### Vì sao có thể chạy được mà không cần `--add-opens`?

Các lớp thử nghiệm là thành viên trong cùng một top-level class, chạy trên classpath (unnamed module). Test đang thực thi từ cùng enclosing class/nest nên có quyền phù hợp. **Không suy ra** rằng code thư viện trong named module khác có thể bật `setAccessible(true)` với mọi private member. Nếu sản phẩm thật làm việc với module JDK hoặc plugin không mở package, hãy thêm test riêng cho `trySetAccessible`, `IllegalAccessException` và `InaccessibleObjectException`.

## 8. Kiểm thử dựa trên hợp đồng, tránh chi tiết compiler

Một công cụ Reflection hoạt động trên nhiều JDK/compiler nên lựa chọn assertion thận trọng:

| Assertion nên dùng | Assertion nên tránh |
| --- | --- |
| Inner member không static có outer instance trong constructor; constructor công khai/khả dụng theo chính khai báo | Dựa vào tên field hỗ trợ outer như `this$0` hoặc vị trí field trong `getDeclaredFields()`. |
| `isEnum` và `getEnumConstants` theo thứ tự khai báo | Dựa vào field compiler-generated `$VALUES` hoặc constructor parameters mang tên cụ thể. |
| `RecordComponent[]` theo record header; accessor đúng | Xem mọi field JVM của record đều là record component hay có thể sửa field `final`. |
| `isSealed` và tập permitted **direct subtypes** | Coi thứ tự array `getPermittedSubclasses()` là một contract cần khóa chặt khi không có yêu cầu. |
| Assert bằng `Class<?>` identity khi cần | So sánh chỉ tên class trong hệ thống có nhiều ClassLoader. |
| Kiểm đúng exception class và trạng thái sau failure | Phụ thuộc thông báo exception chính xác hoặc stack trace thay đổi theo JDK. |

Khi kiểm thử một helper generic:

- Bắt đầu với phân loại `isEnum`, `isRecord`, `isSealed`, `isMemberClass`, `getEnclosingClass` và `Modifier.isStatic`.
- Có thể xét `isLocalClass`, `isAnonymousClass`, `isHidden` nếu helper tuyên bố hỗ trợ nhiều loại Class. Chúng là các chủ đề liên quan nhưng **không nên mặc định cùng hợp đồng constructor như non-static member inner class**.
- Dùng `getDeclaredConstructor(...)` và `getDeclaredMethods()` khi kiểm tra khai báo nội bộ; dùng `getConstructor(...)` / `getMethods()` nếu mục đích là thành viên public.
- Khi lời gọi phản chiếu thực thi ném exception từ bên trong constructor/method, chú ý `InvocationTargetException` và `getCause()`; không nhầm với `NoSuchMethodException` khi chỉ tìm metadata.

## 9. Lỗi thường gặp và cách khắc phục

### Lỗi 1: Gọi constructor không tham số cho tất cả lớp

~~~java
// Mảnh minh họa cần đặt trong phương thức:
Object value = Outer.Inner.class.getDeclaredConstructor().newInstance();
~~~

Lệnh trên ném `NoSuchMethodException` ở giai đoạn tìm constructor trong fixture, do inner cần outer instance và `String`. **Khắc phục:** xây kế hoạch tạo đối tượng dựa trên loại Class và chữ ký constructor; nếu thư viện không hỗ trợ inner, báo unsupported với lý do rõ ràng.

### Lỗi 2: Duyệt field enum rồi coi mọi field là constant

`getDeclaredFields()` không được hứa chỉ trả các enum constants. **Khắc phục:** dùng `getEnumConstants()` khi cần giá trị; dùng `Field.isEnumConstant()` nếu cần metadata field của các constants.

### Lỗi 3: Coi field `private final` trong record là mutable nhờ `setAccessible`

Record component được bảo vệ bởi đặc điểm final không thể sửa bằng `Field.set`. **Khắc phục:** xây object mới bằng canonical constructor hoặc public factory, thay vì lén chỉnh state của instance đã tạo.

### Lỗi 4: Hiểu `getPermittedSubclasses` là tập mọi subtype trong cây

API phản ánh **direct permitted subclass/interface** của sealed type. **Khắc phục:** khi cần toàn bộ hierarchy, duyệt đệ quy có kiểm soát, phân biệt nhánh `non-sealed` có thể mở cho các subtype không liệt kê tĩnh.

### Lỗi 5: Cố ép truy cập `private` trên module khác

`getDeclaredConstructor` có thể tìm thấy member mà không cho phép gọi. **Khắc phục:** ưu tiên API công khai; nếu thật sự cần deep reflection, thiết kế `opens` đúng package/module và test quyền truy cập một cách tường minh.

### Lỗi 6: Test thất bại chỉ vì output metadata đổi thứ tự

Reflection không bảo đảm thứ tự nhiều tập như `getDeclaredFields()` hay `getDeclaredMethods()`. **Khắc phục:** chuyển thành set hoặc sort theo key ổn định; chỉ dựa vào thứ tự khi tài liệu API xác nhận thứ tự có ý nghĩa như enum constants và record components.

## 10. Bài tập tự kiểm tra

1. Tạo thêm `static class Nested` trong `Outer`, dùng `getDeclaredConstructors()` so sánh tham số với `Outer.Inner`. Nêu chính xác sự khác biệt khi không có enclosing instance.
2. Với enum `Stage`, dùng `Field.isEnumConstant()` và `getEnumConstants()`; chứng minh lý do không nên kiểm thử field compiler-generated theo tên.
3. Thêm component `boolean active` vào `Person`, cập nhật canonical constructor trong test và assertion về thứ tự component. Tại sao test phải sửa khi record header thay đổi?
4. Tạo `non-sealed interface Flexible extends Shape` và cho phép nó trong `permits Shape`. `Shape.getPermittedSubclasses()` trả những direct subtype nào? Các implementation của `Flexible` có phải direct permitted subtype của `Shape` không?
5. Thử tạo enum mới bằng `Constructor.newInstance` nhưng bỏ lời gọi `setAccessible(true)`: loại lỗi đầu tiên có thể thay đổi thế nào theo access context? Vì sao phải thiết kế fixture rõ ràng khi kiểm một hợp đồng cụ thể?
6. Tách demo thành bốn bài JUnit 5, dùng `assertThrows` để kiểm `NoSuchMethodException`, `IllegalArgumentException` và `IllegalAccessException`; không phụ thuộc exact exception message.
7. Viết một classifier trả về `"ENUM"`, `"RECORD"`, `"SEALED"`, `"NON_STATIC_MEMBER"` hoặc `"OTHER"`. Quy định ưu tiên kiểm tra cho kiểu có nhiều đặc tính đồng thời (ví dụ record cũng là permitted subtype của sealed interface) thay vì giả định các phân loại luôn loại trừ nhau.

**Tự đánh giá:** Một công cụ Reflection có thể nhìn thấy rất nhiều metadata, nhưng việc tạo object, sửa field hoặc suy diễn quan hệ kiểu phải dựa trên **hợp đồng ngôn ngữ và API cụ thể**. Với bốn nhóm trên, hãy kiểm thử cả điều kiện thành công lẫn tình huống bị từ chối, dùng fixture kiểm soát được và assertions có ý nghĩa.

## 11. Tài liệu chính thức

- [Oracle Java 17 — java.lang.Class](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html) — `isMemberClass`, `getEnclosingClass`, `isEnum`, `getEnumConstants`, `isRecord`, `getRecordComponents`, `isSealed`, `getPermittedSubclasses`.
- [Oracle Java 17 — Constructor.newInstance](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Constructor.html#newInstance(java.lang.Object...)) — kiểm tra truy cập, ngoại lệ và giới hạn tạo enum instance.
- [Oracle Java 17 — Field.set](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Field.html#set(java.lang.Object,java.lang.Object)) — non-modifiable final fields của record.
- [Oracle Java 17 — RecordComponent](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/RecordComponent.html) — metadata component và accessor.
- [JLS Java 17, 8.1.3 — Inner Classes and Enclosing Instances](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.1.3) — ràng buộc về enclosing instance.
- [JLS Java 17, 8.10 — Record Classes](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.10) — record components và constructors.
- [JLS Java 17, 8.9 — Enum Classes](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.9) — enum constants và constructor.
- [JLS Java 17, 9.1.1.4 — Sealed Interfaces](https://docs.oracle.com/javase/specs/jls/se17/html/jls-9.html#jls-9.1.1.4) — `sealed`, `non-sealed` và `permits`.