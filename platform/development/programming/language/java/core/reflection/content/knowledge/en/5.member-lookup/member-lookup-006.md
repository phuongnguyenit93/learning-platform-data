# Tra cứu thành viên bằng tên và kiểu tham số chính xác trong Java Reflection

Khi dùng Reflection, chương trình có thể tìm phương thức (`Method`), constructor (`Constructor`) hoặc trường (`Field`) từ đối tượng `Class<?>` tại thời điểm chạy. Điểm mấu chốt của việc **tra cứu chính xác** là phải truyền đúng tên thành viên, đúng số lượng và thứ tự kiểu tham số, đồng thời chọn API phù hợp với phạm vi hiển thị. Java Reflection **không tự chọn overload theo cách trình biên dịch Java chọn khi gọi phương thức**.

## 1. Những API nào dùng tên và kiểu tham số?

| Thành viên cần tìm | Chỉ lấy `public` (kể cả được kế thừa khi áp dụng) | Chỉ xét thành viên khai báo ngay trong lớp (mọi mức truy cập) | Tiêu chí tra cứu |
| --- | --- | --- | --- |
| Phương thức | `getMethod(String name, Class<?>... parameterTypes)` | `getDeclaredMethod(String name, Class<?>... parameterTypes)` | Tên + danh sách kiểu tham số |
| Constructor | `getConstructor(Class<?>... parameterTypes)` | `getDeclaredConstructor(Class<?>... parameterTypes)` | Danh sách kiểu tham số; không truyền tên |
| Trường | `getField(String name)` | `getDeclaredField(String name)` | Chỉ tên trường; không truyền kiểu tham số |

Ví dụ, nếu `UserService` khai báo `public User find(String key, int limit)`:

```java
Method method = UserService.class.getMethod(
        "find", String.class, int.class);
```

Hai `Class` trong danh sách phải tương ứng **chính xác** với kiểu của tham số thứ nhất và thứ hai. Giá trị truyền vào là đối tượng mô tả kiểu (ví dụ `int.class`), không phải đối tượng tham số thực tế (ví dụ `42`). Trường hợp phương thức không có tham số, chỉ cần `getMethod("name")`.

## 2. Điều kiện khớp của phương thức

Một lời gọi `getMethod` hoặc `getDeclaredMethod` chỉ khớp khi đồng thời thỏa các điều kiện sau:

1. **Tên đúng hoàn toàn:** `"find"` khác `"Find"`; tên phân biệt chữ hoa và chữ thường.
2. **Đúng số lượng tham số:** `find(String)` khác `find(String, int)`.
3. **Đúng thứ tự:** `find(String, int)` khác `find(int, String)`.
4. **Đúng từng kiểu `Class`:** `int.class` khác `Integer.class`; `long.class` khác `int.class`; `Object.class` khác `String.class`. Không có tự động boxing/unboxing, mở rộng kiểu số hay xét quan hệ cha–con **ở bước tra cứu**.
5. **Đúng phạm vi API:** `getMethod` chỉ tìm phương thức `public` thích hợp, kể cả phương thức công khai được kế thừa; `getDeclaredMethod` tìm phương thức do chính lớp đó khai báo, kể cả `private`, nhưng **không tìm phương thức chỉ được kế thừa**.

Tên và kiểu tham số là khóa tra cứu; **kiểu trả về không được truyền** cho `getMethod`. Sau khi tìm được, dùng `method.getReturnType()` để kiểm tra kiểu trả về nếu nghiệp vụ cần. Tương tự, các modifier như `static`, `final` hoặc annotation không nằm trong tham số tra cứu; kiểm tra chúng sau bằng `getModifiers()`, `Modifier` hoặc `getAnnotations()`.

Ví dụ, với chữ ký `void process(int id, String name)`:

| Lời gọi | Kết quả |
| --- | --- |
| `getMethod("process", int.class, String.class)` | Khớp nếu phương thức `public` thuộc phạm vi tìm kiếm |
| `getMethod("process", String.class, int.class)` | `NoSuchMethodException`: sai thứ tự |
| `getMethod("process", Integer.class, String.class)` | `NoSuchMethodException`: `Integer` không phải `int` |
| `getMethod("process", int.class)` | `NoSuchMethodException`: thiếu một tham số |
| `getMethod("Process", int.class, String.class)` | `NoSuchMethodException`: sai tên |

Lưu ý: khi **gọi** một `Method` đã tìm được bằng `invoke`, Java có thể thực hiện một số chuyển đổi giá trị tham số theo quy tắc riêng của Reflection. Việc đó không làm cho `getMethod` chấp nhận chữ ký gần đúng.

## 3. Ví dụ Java 17+ chạy độc lập

Lưu toàn bộ mã dưới đây vào tệp `ExactMemberLookupDemo.java`:

```java
import java.lang.reflect.Method;
import java.lang.reflect.Modifier;
import java.util.Arrays;
import java.util.List;

public class ExactMemberLookupDemo {
    public static class Parent {
        public String inherited(String value) {
            return "parent:" + value;
        }

        public String code = "P";
    }

    public static class Example extends Parent {
        public Example() {}

        private Example(int size) {}

        public String combine(String text, int count) {
            return text + "-" + count;
        }

        public String combine(int value) {
            return "#" + value;
        }

        private void internal(long id) {}

        public void publish(String... labels) {}

        public void save(List<String> names) {}

        private String token = "secret";
    }

    public static void main(String[] args) throws Exception {
        Class<Example> type = Example.class;
        Example example = new Example();

        Method exact = type.getMethod(
                "combine", String.class, int.class);
        System.out.println("exact=" + exact.getName()
                + Arrays.toString(exact.getParameterTypes()));
        System.out.println("invoke=" + exact.invoke(example, "A", 2));
        System.out.println("overload=" + type.getMethod(
                "combine", int.class).invoke(example, 7));

        System.out.println("inherited=" + type.getMethod(
                "inherited", String.class)
                .getDeclaringClass().getSimpleName());
        System.out.println("declaredPrivate=" + Modifier.isPrivate(
                type.getDeclaredMethod(
                        "internal", long.class).getModifiers()));

        System.out.println("varargs=" + type.getMethod(
                "publish", String[].class)
                .getParameterTypes()[0].getTypeName());
        System.out.println("erased=" + type.getMethod(
                "save", List.class).getName());

        System.out.println("ctorPublic=" + type.getConstructor()
                .getParameterCount());
        System.out.println("ctorPrivate=" + Modifier.isPrivate(
                type.getDeclaredConstructor(int.class).getModifiers()));

        System.out.println("fieldInherited=" + type.getField("code")
                .getDeclaringClass().getSimpleName());
        System.out.println("fieldPrivate=" + Modifier.isPrivate(
                type.getDeclaredField("token").getModifiers()));

        try {
            type.getMethod("combine", String.class, Integer.class);
        } catch (NoSuchMethodException e) {
            System.out.println("wrapperMismatch=NoSuchMethodException");
        }

        try {
            type.getDeclaredMethod("inherited", String.class);
        } catch (NoSuchMethodException e) {
            System.out.println("declaredNotInherited=NoSuchMethodException");
        }
    }
}
```

Biên dịch và chạy từ thư mục chứa tệp:

```bash
javac ExactMemberLookupDemo.java
java ExactMemberLookupDemo
```

Kết quả chuẩn:

```text
exact=combine[class java.lang.String, int]
invoke=A-2
overload=#7
inherited=Parent
declaredPrivate=true
varargs=java.lang.String[]
erased=save
ctorPublic=0
ctorPrivate=true
fieldInherited=Parent
fieldPrivate=true
wrapperMismatch=NoSuchMethodException
declaredNotInherited=NoSuchMethodException
```

Diễn giải: `combine` có hai overload nên danh sách `Class` xác định chính xác overload cần tìm. Phương thức `inherited` được kế thừa từ `Parent`, vì vậy `getMethod` tìm được còn `Example.class.getDeclaredMethod` thì không. Constructor `Example(int)` và phương thức `internal(long)` là `private` nhưng vẫn có thể **tìm metadata** bằng API `getDeclared...`. `code` là trường `public` được kế thừa, còn `token` được khai báo `private` ngay trong `Example`.

## 4. Những kiểu tham số thường gây nhầm lẫn

### Primitive và wrapper

`int.class` là đối tượng `Class` của primitive `int`; `Integer.class` là đối tượng `Class` của lớp bao `java.lang.Integer`. Chúng khác nhau ngay cả khi một lời gọi Java thông thường có thể tự boxing:

```java
// Phương thức được khai báo: void setCount(int count)
type.getMethod("setCount", int.class);      // Đúng nếu public.
type.getMethod("setCount", Integer.class);  // NoSuchMethodException.
```

Tương tự, `byte`, `short`, `int`, `long`, `float` và `double` không thể hoán đổi khi tra cứu. `Object.class` cũng không thay thế được `String.class` chỉ vì `String` là con của `Object`.

### Mảng và varargs

Ở cấp chữ ký, tham số khai báo `String... names` có kiểu thực là `String[]`; phương thức `process(int[] values)` có tham số `int[].class`:

```java
getMethod("publish", String[].class); // public void publish(String... labels)
getMethod("sum", int[].class);        // public int sum(int[] values)
```

Đây là minh họa chữ ký, không phải chương trình độc lập: hai phương thức tương ứng phải tồn tại trên `Class` đang tra cứu. `getMethod("publish", String.class)` không khớp với varargs; Reflection không tự trải rộng hay gom các kiểu tham số tại bước tìm.

### Generic và type erasure

Java thường xóa đối số kiểu generic trong chữ ký phương thức ở runtime. Với `void save(List<String> names)`, phải tra cứu bằng `List.class`, **không có** cú pháp `List<String>.class`:

```java
Method save = Example.class.getMethod("save", List.class);
```

`save.getParameterTypes()` trả về kiểu đã erasure; `save.getGenericParameterTypes()` có thể cung cấp thêm thông tin generic được lưu trong metadata. Với type variable như `T`, kiểu dùng để tra cứu là kiểu sau erasure (thường là `Object` hoặc bound đầu tiên).

### Lớp được nạp bởi ClassLoader khác nhau

Hai lớp có cùng tên đầy đủ nhưng do hai class loader khác nhau định nghĩa có thể là **hai kiểu runtime khác nhau**. Vì việc đối chiếu kiểu tham số dựa trên danh tính `Class`, chỉ so tên từ `getName()` là chưa đủ để khẳng định chữ ký sẽ khớp.

## 5. Public, declared, kế thừa và quyền truy cập

`getMethod` và `getField` xét thành viên `public`, bao gồm thành viên công khai được kế thừa theo quy tắc Java. `getDeclaredMethod` và `getDeclaredField` xét thành viên khai báo trực tiếp trong lớp đang cầm `Class`, bất kể `public`, `protected`, package-private hay `private`; chúng **không duyệt lên superclass**. Nếu muốn tìm thành viên `private` khai báo trong superclass, phải lấy `Class` của superclass đó (hoặc tự duyệt chuỗi `getSuperclass()` khi bài toán đòi hỏi).

Constructor không được kế thừa. `getConstructor(int.class)` đòi constructor `public` với đúng một tham số `int`; `getDeclaredConstructor(int.class)` xét constructor do lớp khai báo ở mọi mức truy cập. Không truyền tên lớp khi tìm constructor. Constructor mặc định không phải lúc nào cũng tồn tại: khi lớp khai báo constructor khác, Java không tự sinh constructor không tham số.

**Tra cứu được không đồng nghĩa với gọi hoặc đọc/ghi được.** Ví dụ, tìm `private Method` bằng `getDeclaredMethod` không tự cấp quyền gọi `method.invoke(...)`. Java có thể ném `IllegalAccessException` khi truy cập; `setAccessible(true)` cũng có thể bị từ chối, đặc biệt ở ranh giới module (ví dụ `InaccessibleObjectException`). Không lạm dụng mở truy cập để che đi thiết kế API chưa phù hợp.

## 6. Xử lý lỗi và kiểm tra chữ ký thực tế

Các API tra cứu đơn lẻ không trả về `null` khi không tìm thấy:

- `getMethod`, `getDeclaredMethod`, `getConstructor` và `getDeclaredConstructor` ném `NoSuchMethodException`.
- `getField` và `getDeclaredField` ném `NoSuchFieldException`.
- Một số đầu vào không hợp lệ (ví dụ tên `null` hoặc phần tử kiểu tham số `null`) có thể gây `NullPointerException`; kiểm tra đầu vào trước khi tra cứu động.
- Ràng buộc bảo mật hoặc module có thể gây lỗi khác tại thời điểm tìm hoặc sử dụng thành viên; cần đọc loại ngoại lệ thực tế.

Nếu nhận `NoSuchMethodException`, hãy kiểm tra lần lượt: đối tượng `Class` đang tra cứu có đúng không; tên có đúng ký tự/case; số lượng, thứ tự và từng kiểu có đúng không; đã phân biệt primitive/wrapper, mảng/varargs và erasure; sau cùng chọn đúng `getMethod` hay `getDeclaredMethod`. Khi cần chẩn đoán, có thể liệt kê chữ ký từ chính lớp mục tiêu:

```java
for (Method method : Example.class.getDeclaredMethods()) {
    System.out.println(method.getName()
            + Arrays.toString(method.getParameterTypes()));
}
```

Đoạn trên là mã minh họa đặt trong `main` của ví dụ và dùng `java.lang.reflect.Method` cùng `java.util.Arrays`. Thứ tự do `getDeclaredMethods()` trả về **không được bảo đảm**, nên không dựa vào thứ tự in để viết logic hoặc test. Các phương thức tổng hợp (`synthetic`) hoặc `bridge` do compiler tạo có thể xuất hiện trong kết quả; có thể xem `isSynthetic()` và `isBridge()` để hiểu chúng. Khi thao tác với bytecode đặc biệt có nhiều phương thức cùng tên và tham số nhưng khác kiểu trả về, đừng giả định API tìm một phương thức theo kiểu trả về vì API không nhận tiêu chí đó.

## 7. Tình huống áp dụng và nguyên tắc ghi nhớ

Giả sử framework đọc tên phương thức và các kiểu tham số từ cấu hình, ví dụ `run(String, int)`. Quy trình đáng tin cậy là phân giải **từng tên kiểu** thành đúng đối tượng `Class` (primitive phải xử lý riêng), quyết định tìm `public` hay thành viên khai báo trực tiếp, gọi `getMethod("run", String.class, int.class)`, sau đó mới kiểm tra return type, modifier, quyền truy cập và thực hiện `invoke` nếu được phép. Nếu lấy kiểu bằng `args[i].getClass()`, hãy cẩn thận: giá trị `Integer` không tương đương tham số khai báo `int`; giá trị `null` cũng không có `getClass()`. Cấu hình nên mô tả **chữ ký khai báo**, không suy đoán chữ ký từ các giá trị truyền vào.

Cần nhớ ba quy tắc cốt lõi: **phương thức = tên + dãy kiểu tham số chính xác; constructor = dãy kiểu tham số chính xác; trường = tên chính xác**. Sau đó chọn đúng phạm vi `public`/`declared` và phân biệt bước **tìm thành viên** với bước **truy cập hoặc gọi thành viên**.