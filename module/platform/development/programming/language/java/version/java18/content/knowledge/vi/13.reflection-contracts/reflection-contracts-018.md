# Thiết kế bảng kiểm chứng Method, Constructor và Field với đầu vào hợp lệ cùng các ca biên

> **Chương:** Hợp đồng reflection  
> **Phạm vi:** Java 18 trở lên; các API công khai `java.lang.Class`, `java.lang.reflect.Method`, `java.lang.reflect.Constructor`, `java.lang.reflect.Field` vẫn được hỗ trợ trên JDK hiện đại.

## 1. Tại sao phải kiểm chứng hợp đồng reflection?

Reflection cho phép chương trình tìm và thao tác với các thành viên của lớp tại runtime. Nó thường xuất hiện trong framework ánh xạ dữ liệu, dependency injection, kiểm thử, thư viện serialization và công cụ phát triển. Tuy nhiên, một lời gọi có thể thất bại ở nhiều **giai đoạn khác nhau**:

1. **Tìm thành viên:** tên hoặc kiểu tham số không khớp, hoặc nhầm thành viên khai báo trực tiếp với thành viên kế thừa.
2. **Kiểm tra quyền truy cập:** tìm thấy thành viên nhưng mã gọi không được phép sử dụng; giới hạn module cũng có thể ngăn mở quyền.
3. **Kiểm tra receiver và đối số:** đối tượng đích `null`, sai kiểu, sai số lượng tham số hoặc sai họ kiểu nguyên thủy.
4. **Thực thi:** constructor hoặc method chạy rồi ném ngoại lệ; API reflection bọc ngoại lệ thực thi bằng `InvocationTargetException`.
5. **Quan sát kết quả:** giá trị trả về, trạng thái field và kiểu runtime phải khớp với hợp đồng mong đợi.

Mục tiêu của bài là thiết kế **bảng kiểm chứng có đầu vào và kết quả dự kiến rõ ràng**, sau đó triển khai một chương trình Java thuần có thể chạy lặp lại trên JDK 18 hoặc mới hơn. Chỉ dùng API reflection còn được hỗ trợ; không sử dụng `Class.newInstance()` (API đã lỗi thời), API nội bộ JDK hoặc giả định có thể mở mọi thành viên bằng `setAccessible(true)`.

## 2. Đọc đúng hợp đồng của ba nhóm thành viên

| Đối tượng reflection | Tìm thành viên public, có xét kế thừa khi phù hợp | Chỉ tìm thành viên khai báo tại lớp | Thao tác cốt lõi |
| --- | --- | --- | --- |
| `Method` | `Class.getMethod(name, parameterTypes...)` | `Class.getDeclaredMethod(name, parameterTypes...)` | `Method.invoke(receiver, args...)` |
| `Constructor` | `Class.getConstructor(parameterTypes...)` | `Class.getDeclaredConstructor(parameterTypes...)` | `Constructor.newInstance(args...)` |
| `Field` | `Class.getField(name)` | `Class.getDeclaredField(name)` | `Field.get(receiver)`, `Field.set(receiver, value)` và các biến thể kiểu nguyên thủy |

**Điểm khác nhau quan trọng:** `getMethod` và `getField` có thể tìm thành viên public được kế thừa; `getDeclaredMethod` và `getDeclaredField` chỉ tìm các thành viên khai báo trực tiếp (kể cả private). Constructor **không được kế thừa**. Có được đối tượng `Method`, `Constructor` hoặc `Field` chưa đồng nghĩa với có quyền thao tác trên thành viên đó.

Tra cứu method và constructor dùng **danh sách kiểu tham số chính xác**: `int.class` khác `Integer.class`, `String.class` khác `CharSequence.class`, và tham số varargs `String...` có kiểu khai báo là `String[].class`. Khả năng boxing/unboxing và widening primitive khi **gọi** phản chiếu không làm thay đổi quy tắc **tìm** thành viên.

## 3. Ma trận ca kiểm chứng cần thiết

Đặt ID riêng cho mỗi ca để log dễ đối chiếu với bảng. `PASS` nghĩa là hành vi thực tế đúng với kết quả dự kiến, **kể cả** khi ca kiểm thử cố ý kỳ vọng một ngoại lệ.

### 3.1. `Method`: tìm kiếm, gọi và bọc ngoại lệ

| ID | Đầu vào/tác vụ | Kết quả kỳ vọng | Hợp đồng đang kiểm chứng |
| --- | --- | --- | --- |
| M01 | `getMethod("echo", String.class)` rồi `invoke` với chuỗi | Trả `str:ok`; overload dùng `Object.class` trả `obj:ok` | Chọn đúng chữ ký tại bước tra cứu |
| M02 | Tìm method public kế thừa bằng `getMethod`, rồi `getDeclaredMethod` trên lớp con | Lần đầu thành công; lần sau `NoSuchMethodException` | Phân biệt tìm có kế thừa với thành viên khai báo tại lớp |
| M03 | Tìm method private bằng `getDeclaredMethod`, gọi khi chưa mở quyền | Tìm thấy; `getMethod` không thấy; `invoke` ném `IllegalAccessException` | Phân biệt phát hiện và quyền truy cập |
| M04 | Tìm method bằng kiểu tham số không đúng; gọi sai kiểu; gọi instance với receiver `null` | Tương ứng `NoSuchMethodException`, `IllegalArgumentException`, `NullPointerException` | Kiểu tham số, đối số và receiver |
| M05 | Gọi instance method nhận `int` bằng `Integer` và static method với receiver `null` | Trả `Integer(42)` và `static:x` | Unboxing hợp lệ và static invocation |
| M06 | Gọi method `join(String...)` với một `String[]`; sau đó truyền hai đối số rời | Trả `a,b`; lần thứ hai `IllegalArgumentException` | Reflection không tự trải đối số varargs của method đích |
| M07 | Method đích ném `IllegalStateException("boom")` | `InvocationTargetException` với `getCause()` là `IllegalStateException` | Tách ngoại lệ trong thân method khỏi lỗi reflection |

### 3.2. `Constructor`: public, private, đối số và lỗi khởi tạo

| ID | Đầu vào/tác vụ | Kết quả kỳ vọng | Hợp đồng đang kiểm chứng |
| --- | --- | --- | --- |
| C01 | `getConstructor(int.class).newInstance(7)` | Đối tượng có `value == 7` | Khởi tạo hợp lệ và đối số nguyên thủy |
| C02 | Tra constructor không tham số bằng `getConstructor()`, sau đó lấy private constructor qua `getDeclaredConstructor()` | `NoSuchMethodException` rồi `IllegalAccessException` khi `newInstance()` | Khác nhau giữa public và declared; kiểm tra quyền |
| C03 | Gọi constructor nhận `int` bằng chuỗi `"7"` | `IllegalArgumentException` | Không tự chuyển chuỗi thành số |
| C04 | Constructor thực thi và ném `IllegalStateException("ctor-fail")` | `InvocationTargetException`, cause giữ ngoại lệ đích | Ngoại lệ từ code constructor |
| C05 | Gọi constructor public của abstract class qua reflection | `InstantiationException` | Không thể tạo instance của abstract class |

### 3.3. `Field`: quyền truy cập, kiểu dữ liệu và receiver

| ID | Đầu vào/tác vụ | Kết quả kỳ vọng | Hợp đồng đang kiểm chứng |
| --- | --- | --- | --- |
| F01 | Đọc/ghi public `int count` bằng `getInt`/`setInt` | Đọc `2`, ghi thành `7` | Truy cập và thay đổi field instance đúng kiểu |
| F02 | Tìm public field kế thừa bằng `getField`, sau đó `getDeclaredField` trên lớp con | Tìm được field của lớp cha; lần sau `NoSuchFieldException` | Hành vi kế thừa field |
| F03 | Tìm private field bằng `getDeclaredField` rồi đọc khi chưa mở quyền | `getField` không thấy; `get` ném `IllegalAccessException` | Phát hiện khác với quyền đọc |
| F04 | Ghi chuỗi vào field `int`; dùng receiver sai lớp; dùng receiver `null` | `IllegalArgumentException`, `IllegalArgumentException`, `NullPointerException` | Kiểm tra loại giá trị và receiver instance |
| F05 | Đọc public static final field bằng `get(null)` | Trả chuỗi hằng `fixture` | Field static không cần receiver |
| F06 | Dùng `Field.set` đặt `Short` vào field `int` | Đọc lại được số `10` | Unboxing và widening primitive hợp lệ |
| F07 | Dùng `trySetAccessible()` cho private field trong cùng unnamed module | Trả `true`; đọc được `hidden` | Giới hạn quyền truy cập theo module; ca được kiểm soát trong classpath |

**Không đưa vào phép thử bắt buộc:** việc ghi `final`/`static final` bằng reflection, phụ thuộc thứ tự trả về của `getDeclaredMethods()`, hoặc truy cập field private nội bộ của `java.base`. Các tình huống đó dễ tạo giả định sai hoặc phụ thuộc triển khai. Cách khởi tạo trạng thái bất biến nên dùng constructor hoặc API chính thức.

## 4. Fixture Java có thể biên dịch độc lập

Tạo tệp `ReflectionContractMatrix.java` với toàn bộ mã sau. Ba lớp fixture ở cuối tệp là các **top-level class riêng biệt**, để lời gọi private qua reflection thực sự bị kiểm tra quyền theo Java; nếu đặt chúng thành nested class cùng nest với chương trình kiểm thử, quy tắc *nestmate access* có thể khiến ca `IllegalAccessException` thay đổi.

```java
import java.lang.reflect.Constructor;
import java.lang.reflect.Field;
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Method;
import java.util.Objects;

public final class ReflectionContractMatrix {
    private static int passed;
    private static int failed;

    @FunctionalInterface
    private interface CheckedAction {
        void execute() throws Exception;
    }

    private static void check(String id, CheckedAction action) {
        try {
            action.execute();
            passed++;
            System.out.println("PASS " + id);
        } catch (Throwable error) {
            failed++;
            System.out.println("FAIL " + id + " -> "
                    + error.getClass().getName() + ": "
                    + error.getMessage());
        }
    }

    private static void equal(Object actual, Object expected) {
        if (!Objects.equals(actual, expected)) {
            throw new AssertionError(
                    "expected=" + expected + ", actual=" + actual);
        }
    }

    private static <T extends Throwable> T expectThrows(
            Class<T> expected, CheckedAction action) throws Exception {
        try {
            action.execute();
        } catch (Throwable actual) {
            if (expected.isInstance(actual)) {
                return expected.cast(actual);
            }
            throw new AssertionError(
                    "expected " + expected.getName()
                    + ", got " + actual.getClass().getName(), actual);
        }
        throw new AssertionError("expected " + expected.getName());
    }

    public static void main(String[] args) {
        DemoObject target = new DemoObject();

        check("M01", () -> {
            Method byString = DemoObject.class.getMethod(
                    "echo", String.class);
            equal(byString.getReturnType(), String.class);
            equal(byString.invoke(target, "ok"), "str:ok");
            Method byObject = DemoObject.class.getMethod(
                    "echo", Object.class);
            equal(byObject.invoke(target, "ok"), "obj:ok");
        });

        check("M02", () -> {
            Method inherited = DemoObject.class.getMethod("inherited");
            equal(inherited.getDeclaringClass(), ParentDemo.class);
            equal(inherited.invoke(target), "parent");
            expectThrows(NoSuchMethodException.class,
                    () -> DemoObject.class.getDeclaredMethod("inherited"));
        });

        check("M03", () -> {
            expectThrows(NoSuchMethodException.class,
                    () -> DemoObject.class.getMethod("secret"));
            Method hidden = DemoObject.class.getDeclaredMethod("secret");
            expectThrows(IllegalAccessException.class,
                    () -> hidden.invoke(target));
        });

        check("M04", () -> {
            expectThrows(NoSuchMethodException.class,
                    () -> DemoObject.class.getMethod(
                            "echo", CharSequence.class));
            Method method = DemoObject.class.getMethod(
                    "echo", String.class);
            expectThrows(IllegalArgumentException.class,
                    () -> method.invoke(target, 123));
            expectThrows(NullPointerException.class,
                    () -> method.invoke(null, "ok"));
        });

        check("M05", () -> {
            Method sum = DemoObject.class.getMethod("plusOne", int.class);
            equal(sum.invoke(target, Integer.valueOf(41)), 42);
            Method staticMethod = DemoObject.class.getMethod(
                    "staticEcho", String.class);
            equal(staticMethod.invoke(null, "x"), "static:x");
        });

        check("M06", () -> {
            Method join = DemoObject.class.getMethod(
                    "join", String[].class);
            equal(join.invoke(target, (Object) new String[] {"a", "b"}),
                    "a,b");
            expectThrows(IllegalArgumentException.class,
                    () -> join.invoke(target, "a", "b"));
        });

        check("M07", () -> {
            Method method = DemoObject.class.getMethod("explode");
            InvocationTargetException wrapped = expectThrows(
                    InvocationTargetException.class,
                    () -> method.invoke(target));
            equal(wrapped.getCause().getClass(),
                    IllegalStateException.class);
            equal(wrapped.getCause().getMessage(), "boom");
        });

        check("C01", () -> {
            Constructor<ConstructorDemo> ctor =
                    ConstructorDemo.class.getConstructor(int.class);
            ConstructorDemo created = ctor.newInstance(7);
            equal(created.value, 7);
        });

        check("C02", () -> {
            expectThrows(NoSuchMethodException.class,
                    () -> ConstructorDemo.class.getConstructor());
            Constructor<ConstructorDemo> hidden =
                    ConstructorDemo.class.getDeclaredConstructor();
            expectThrows(IllegalAccessException.class,
                    () -> hidden.newInstance());
        });

        check("C03", () -> {
            Constructor<ConstructorDemo> ctor =
                    ConstructorDemo.class.getConstructor(int.class);
            expectThrows(IllegalArgumentException.class,
                    () -> ctor.newInstance("7"));
        });

        check("C04", () -> {
            Constructor<ConstructorDemo> ctor =
                    ConstructorDemo.class.getConstructor(String.class);
            InvocationTargetException wrapped = expectThrows(
                    InvocationTargetException.class,
                    () -> ctor.newInstance("test"));
            equal(wrapped.getCause().getClass(),
                    IllegalStateException.class);
            equal(wrapped.getCause().getMessage(), "ctor-fail");
        });

        check("C05", () -> {
            Constructor<AbstractDemo> ctor =
                    AbstractDemo.class.getConstructor();
            expectThrows(InstantiationException.class,
                    () -> ctor.newInstance());
        });

        check("F01", () -> {
            Field count = DemoObject.class.getField("count");
            equal(count.getInt(target), 2);
            count.setInt(target, 7);
            equal(count.getInt(target), 7);
        });

        check("F02", () -> {
            Field field = DemoObject.class.getField("parentCount");
            equal(field.getDeclaringClass(), ParentDemo.class);
            equal(field.getInt(target), 9);
            expectThrows(NoSuchFieldException.class,
                    () -> DemoObject.class.getDeclaredField("parentCount"));
        });

        check("F03", () -> {
            expectThrows(NoSuchFieldException.class,
                    () -> DemoObject.class.getField("secretValue"));
            Field field = DemoObject.class.getDeclaredField("secretValue");
            expectThrows(IllegalAccessException.class,
                    () -> field.get(target));
        });

        check("F04", () -> {
            Field field = DemoObject.class.getField("count");
            expectThrows(IllegalArgumentException.class,
                    () -> field.set(target, "7"));
            expectThrows(IllegalArgumentException.class,
                    () -> field.getInt(new Object()));
            expectThrows(NullPointerException.class,
                    () -> field.getInt(null));
        });

        check("F05", () -> {
            Field field = DemoObject.class.getField("LABEL");
            equal(field.get(null), "fixture");
        });

        check("F06", () -> {
            Field field = DemoObject.class.getField("count");
            field.set(target, Short.valueOf((short) 10));
            equal(field.getInt(target), 10);
        });

        check("F07", () -> {
            Field field = DemoObject.class.getDeclaredField("secretValue");
            equal(field.trySetAccessible(), true);
            equal(field.get(target), "hidden");
        });

        System.out.printf("TOTAL=%d PASS=%d FAIL=%d%n",
                passed + failed, passed, failed);
        if (failed > 0) {
            System.exit(1);
        }
    }
}

class ParentDemo {
    public int parentCount = 9;

    public String inherited() {
        return "parent";
    }
}

class DemoObject extends ParentDemo {
    public int count = 2;
    public static final String LABEL = "fixture";
    private String secretValue = "hidden";

    public String echo(String value) {
        return "str:" + value;
    }

    public String echo(Object value) {
        return "obj:" + value;
    }

    public int plusOne(int value) {
        return value + 1;
    }

    public static String staticEcho(String value) {
        return "static:" + value;
    }

    public String join(String... parts) {
        return String.join(",", parts);
    }

    public void explode() {
        throw new IllegalStateException("boom");
    }

    private String secret() {
        return secretValue;
    }
}

class ConstructorDemo {
    public final int value;

    public ConstructorDemo(int value) {
        this.value = value;
    }

    public ConstructorDemo(String reason) {
        throw new IllegalStateException("ctor-fail");
    }

    private ConstructorDemo() {
        this.value = -1;
    }
}

abstract class AbstractDemo {
    public AbstractDemo() {
    }
}
```

### Vì sao dùng các fixture là top-level class?

Trong Java, các lớp lồng nhau thuộc cùng một *nest* có thể truy cập thành viên private của nhau theo quy tắc nestmate. Nếu đặt `DemoObject` và `ConstructorDemo` thành lớp lồng trong `ReflectionContractMatrix`, các ca M03, C02 và F03 có thể **không** ném `IllegalAccessException` như bảng dự kiến. Dùng các top-level class riêng trong cùng tệp `.java` giữ phép thử đúng mục tiêu, đồng thời không cần tạo thêm file nguồn.

Chương trình chủ động không gọi `setAccessible(true)` trước khi chạy M03, C02 và F03. Ca F07 nằm sau đó, xác minh việc mở quyền **trong cùng unnamed module** theo cấu hình chạy trên classpath. `AccessibleObject.trySetAccessible()` không bảo đảm thành công với mọi module hoặc gói; với gói chưa `opens` cho caller, phương thức có thể trả `false`.

## 5. Cách chạy và đọc báo cáo

Chọn JDK 18 trở lên, mở terminal tại thư mục chứa tệp nguồn rồi chạy:

```bash
javac ReflectionContractMatrix.java
java ReflectionContractMatrix
```

Vì mã không có khai báo `package` và chạy trên classpath mặc định, tất cả lớp top-level nằm trong unnamed module. Không cần build tool, thư viện bên ngoài hoặc cờ `--add-opens`.

Ví dụ đầu ra **dự kiến** khi hợp đồng được đáp ứng:

```text
PASS M01
PASS M02
PASS M03
PASS M04
PASS M05
PASS M06
PASS M07
PASS C01
PASS C02
PASS C03
PASS C04
PASS C05
PASS F01
PASS F02
PASS F03
PASS F04
PASS F05
PASS F06
PASS F07
TOTAL=19 PASS=19 FAIL=0
```

Đây là kết quả mẫu để người học đối chiếu; **chưa phải** log của một lần chạy được thực hiện trong bài viết. Trường hợp có `FAIL`, chương trình in ID và kiểu ngoại lệ/chi tiết nhận được, sau đó thoát với mã `1`. Khi mọi ca đều đúng, chương trình kết thúc bình thường với mã `0`.

Để lưu bằng chứng kiểm chứng trên từng JDK, lưu thêm phiên bản công cụ và log chạy, chẳng hạn:

```bash
java -version
javac -version
java ReflectionContractMatrix
```

Trong CI hoặc khi nâng cấp JDK, ghi kết quả `TOTAL`, `PASS`, `FAIL` cùng phiên bản JDK. Không lấy duy nhất thông điệp ngoại lệ làm tiêu chí vì câu chữ có thể thay đổi; so sánh **kiểu ngoại lệ**, `cause` và giá trị thực tế.

## 6. Diễn giải các ca biên dễ nhầm

### 6.1. Không nhầm `NoSuchMethodException` với `IllegalAccessException`

`NoSuchMethodException` xuất hiện trong ví dụ khi phương thức không có trong phạm vi tìm kiếm hoặc chữ ký không trùng. `IllegalAccessException` xuất hiện khi có đối tượng `Method` hoặc `Constructor` hợp lệ nhưng caller không có quyền truy cập tại thời điểm gọi.

Cùng nguyên tắc này, `NoSuchFieldException` là lỗi **tìm field**; `IllegalAccessException` là lỗi **đọc/ghi field** sau khi đã tìm thấy. Tách hai dạng này giúp chẩn đoán chính xác việc sai metadata hay sai thiết kế quyền truy cập.

### 6.2. Đối số sai gây lỗi ở lớp reflection; ngoại lệ của mã đích được bọc

`Method.invoke` và `Constructor.newInstance` có thể thực hiện unboxing và widening primitive hợp lệ. Ví dụ, `Integer(41)` được đưa vào tham số `int` và `Short(10)` có thể được gán vào field `int`. Nhưng chuỗi `"7"` không tự chuyển thành số nguyên; số lượng tham số không đúng cũng gây `IllegalArgumentException`.

**Phân biệt nguồn lỗi:** truyền đối số sai dẫn tới `IllegalArgumentException` ngay từ reflection; nếu method/constructor thực sự chạy và tự ném `IllegalStateException`, `InvocationTargetException.getCause()` mới chứa lỗi đích. Khi viết test nên kiểm tra cả kiểu lớp bọc và nguyên nhân gốc.

### 6.3. Varargs có hai tầng

Chữ ký nguồn `join(String... parts)` có một tham số kiểu `String[]`. Lời gọi `Method.invoke(target, ...)` bản thân cũng khai báo varargs kiểu `Object...`. Vì vậy cần ép `(Object)` cho mảng `String[]` để toàn bộ mảng trở thành **một** tham số của method đích:

```java
Method join = DemoObject.class.getMethod("join", String[].class);
Object ok = join.invoke(new DemoObject(),
        (Object) new String[] {"a", "b"}); // "a,b"
```

Truyền trực tiếp hai `String` tách rời vào lời gọi reflection sẽ khiến số tham số thực tế không trùng chữ ký đích và dẫn đến `IllegalArgumentException`. Không suy từ cách gọi varargs thông thường rằng reflection sẽ tự gom các phần tử thành `String[]`.

### 6.4. Quyền truy cập và ranh giới module

`getDeclared*` cho phép **phát hiện** thành viên private, nhưng không tự cấp quyền gọi hoặc đọc. `trySetAccessible()` có thể thành công khi quy tắc module cho phép (như ca F07 chạy trên classpath trong unnamed module), hoặc trả `false` khi không thể mở quyền. Với member của named module không mở package tương ứng, gọi `setAccessible(true)` có thể ném `InaccessibleObjectException`.

Thiết kế thư viện bền vững nên ưu tiên public API, constructor/factory hoặc `opens` rõ ràng trong module do mình quản lý. Tránh dựa vào trường private của JDK hay thêm `--add-opens` để sửa một thiết kế phản chiếu thiếu hợp đồng.

### 6.5. Static, final, thừa kế và thứ tự thành viên

- Với static method hoặc field, receiver có thể là `null`; với thành viên instance, cần receiver hợp lệ.
- Field `final` phản ánh trạng thái bất biến theo thiết kế; việc cố ghi bằng reflection có giới hạn chặt và không nên dùng làm chiến lược cập nhật.
- `getMethod` và `getField` xét thành viên public được kế thừa, nhưng constructor không được kế thừa; `getDeclared*` chỉ phản ánh những gì lớp tự khai báo.
- Không viết test phụ thuộc **thứ tự phần tử** trong `getDeclaredMethods()`, `getDeclaredFields()` hoặc `getDeclaredConstructors()`: API không cam kết thứ tự ổn định.

## 7. Mẫu ghi kết quả kiểm chứng khi nâng cấp JDK

Bảng sau là khuôn báo cáo, điền từ **lần chạy thật** của bạn:

| JDK / môi trường | Tổng ca | PASS | FAIL | Ca lỗi | Nhận định |
| --- | ---: | ---: | ---: | --- | --- |
| JDK hiện tại / OS hiện tại | 19 | _(điền)_ | _(điền)_ | _(ID nếu có)_ | _(đối chiếu với ma trận)_ |
| JDK đích khi nâng cấp / OS đích | 19 | _(điền)_ | _(điền)_ | _(ID nếu có)_ | _(so sánh sai khác)_ |

Nếu xuất hiện FAIL, xác định lần lượt: đang chạy đúng JDK và classpath chưa; `getMethod` có đúng chữ ký không; receiver/đối số có đúng kiểu không; ca thử đang kỳ vọng đúng ngoại lệ theo hợp đồng không; có đang chạy trong named module hoặc cấu hình `opens` khác không. Chỉ sửa bài kiểm thử sau khi đối chiếu tài liệu API của **phiên bản JDK thực tế**, không cập nhật kỳ vọng theo cảm tính.

## 8. Bài tập mở rộng

1. Bổ sung trường hợp `Method.invoke` gọi method trả `void`, kiểm tra giá trị reflection trả về là `null`.
2. Bổ sung phương thức nhận `long` và xác minh widening từ `Integer` sang `long` khi gọi; đồng thời xác minh tra cứu với `Integer.class` không tìm thấy chữ ký `long.class`.
3. Tạo class có public constructor nhận `String...`, kiểm tra cách truyền **một mảng** qua `Constructor.newInstance` và ca truyền sai số đối số.
4. Chuyển các fixture sang một named module của riêng bạn; thử `trySetAccessible()` khi package được hoặc không được `opens` cho module gọi. Ghi rõ module path và quy tắc truy cập.
5. Thêm một lớp con có field cùng tên với field của lớp cha; kiểm tra `getDeclaringClass()` thay vì đoán member nào được chọn qua thứ tự liệt kê.

**Câu hỏi tự đánh giá:** Khi `getDeclaredMethod("secret")` thành công nhưng `invoke` thất bại, phải ghi lỗi ở giai đoạn nào? Vì sao `InvocationTargetException` và `IllegalArgumentException` không thể được coi là cùng một kiểu lỗi? Tại sao các fixture dùng top-level class thay cho nested class?

**Tài liệu đối chiếu:** Javadoc của `java.lang.Class`, `java.lang.reflect.Method`, `java.lang.reflect.Constructor`, `java.lang.reflect.Field`, `java.lang.reflect.AccessibleObject` trong phiên bản JDK đang chạy. Những hợp đồng này tiếp tục hữu ích từ Java 18 đến các JDK hiện đại và có thể xác minh bằng phép thử độc lập ở trên.
