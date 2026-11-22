# Truy cập static field và kiểu được khai báo của field bằng Reflection

Java Reflection cho phép chương trình tra cứu thông tin của một lớp khi chạy, tìm một field theo tên, đọc giá trị field và kiểm tra kiểu được khai báo trong mã nguồn. Với `static field`, ta đọc giá trị thông qua đối tượng `Field` và truyền `null` vào `Field.get`, vì field không thuộc về một instance cụ thể.

## 1. Ba khái niệm cần phân biệt

- **Field được khai báo ở đâu:** `Field.getDeclaringClass()` trả về lớp hoặc interface trực tiếp khai báo field đó.
- **Kiểu được khai báo của field:** `Field.getType()` trả về một `Class<?>` mô tả kiểu field được khai báo, ví dụ `Number`, `String` hoặc `int`. Với field generic, `Field.getGenericType()` cung cấp thêm thông tin kiểu tổng quát khi thông tin đó có trong chữ ký.
- **Kiểu thực tế của giá trị hiện tại:** nếu giá trị khác `null`, gọi `value.getClass()` để xem lớp runtime của đối tượng đang được field tham chiếu tới. Kiểu này có thể là lớp con của kiểu được khai báo.

Ví dụ, nếu khai báo `static Number LIMIT = Integer.valueOf(42);`, thì kiểu được khai báo của `LIMIT` là `Number`, còn lớp runtime của giá trị hiện tại là `Integer`. Hai câu hỏi này khác nhau và Reflection cung cấp API riêng để trả lời.

## 2. Tìm và đọc static field

Các API thường dùng:

| API | Ý nghĩa |
| --- | --- |
| `SomeClass.class` | Lấy đối tượng `Class` đại diện cho kiểu mà không cần tạo instance. |
| `getDeclaredField("NAME")` | Lấy field tên `NAME` được khai báo trực tiếp trong lớp đó; có thể là `public`, `protected`, package-private hoặc `private`. |
| `getField("NAME")` | Tìm field `public`, bao gồm cả field `public` được kế thừa. |
| `field.getType()` | Lấy kiểu được khai báo của field dưới dạng `Class<?>`. |
| `field.getGenericType()` | Lấy kiểu khai báo có thể bao gồm tham số generic dưới dạng `Type`. |
| `Modifier.isStatic(field.getModifiers())` | Kiểm tra field có modifier `static` hay không. |
| `field.get(null)` | Đọc giá trị của static field. Đối số đối tượng bị bỏ qua với field `static`, vì vậy truyền `null` là cách viết rõ ràng. |
| `field.getDeclaringClass()` | Lấy kiểu trực tiếp khai báo field. |

`getDeclaredField` chỉ tìm trong kiểu được gọi trên đó; nó không tự tìm field khai báo ở lớp cha. Nếu không có field với tên đó, phương thức ném `NoSuchFieldException`. Tên field phân biệt chữ hoa và chữ thường.

## 3. Ví dụ hoàn chỉnh chạy với Java 17+

Lưu mã dưới đây vào tệp `StaticFieldReflectionDemo.java`:

```java
import java.lang.reflect.Field;
import java.lang.reflect.Modifier;

public class StaticFieldReflectionDemo {
    public static class Settings {
        public static Number LIMIT = Integer.valueOf(42);
        public static String LABEL = "production";
    }

    public static void main(String[] args) throws ReflectiveOperationException {
        inspect(Settings.class, "LIMIT");
        inspect(Settings.class, "LABEL");
    }

    private static void inspect(Class<?> owner, String fieldName)
            throws ReflectiveOperationException {
        Field field = owner.getDeclaredField(fieldName);
        Object value = field.get(null);

        System.out.println("field: " + field.getName());
        System.out.println("declaring class: "
                + field.getDeclaringClass().getTypeName());
        System.out.println("declared type: " + field.getType().getTypeName());
        System.out.println("static: " + Modifier.isStatic(field.getModifiers()));
        System.out.println("value: " + value);
        System.out.println("runtime type: "
                + (value == null ? "null" : value.getClass().getTypeName()));
        System.out.println();
    }
}
```

Biên dịch và chạy trong thư mục chứa tệp:

```shell
javac StaticFieldReflectionDemo.java
java StaticFieldReflectionDemo
```

Stdout chính xác:

```text
field: LIMIT
declaring class: StaticFieldReflectionDemo$Settings
declared type: java.lang.Number
static: true
value: 42
runtime type: java.lang.Integer

field: LABEL
declaring class: StaticFieldReflectionDemo$Settings
declared type: java.lang.String
static: true
value: production
runtime type: java.lang.String
```

Trong kết quả của `LIMIT`, `getType()` trả về `Number.class`, vì đó là kiểu field đã khai báo. Giá trị hiện tại là một `Integer`, nên `getClass()` trên giá trị trả về `Integer.class`. Không gọi `getClass()` khi giá trị là `null`; ví dụ kiểm tra null trước để tránh `NullPointerException`.

## 4. Đọc static field và instance field khác nhau thế nào?

```java
Field staticField = Settings.class.getDeclaredField("LIMIT");
Object limit = staticField.get(null);

Field instanceField = SomeClass.class.getDeclaredField("name");
Object name = instanceField.get(someObject);
```

Đối với static field, không cần instance của lớp khai báo field; đối số `null` biểu đạt điều đó. Đối với instance field, phải truyền một đối tượng tương thích làm nơi lấy giá trị. Nếu truyền `null` cho một instance field, việc đọc sẽ thất bại với `NullPointerException`. Trong cả hai trường hợp, `getType()` vẫn cho biết kiểu được khai báo, không phụ thuộc vào giá trị hiện tại.

Đọc một static field bằng Reflection có thể kích hoạt khởi tạo lớp nếu lớp chưa được khởi tạo. Vì vậy, nếu việc khởi tạo có side effect, cần tính đến điều đó khi dùng Reflection.

## 5. Field kế thừa, kiểu khai báo thực sự và tác động lên khởi tạo

Khi mã dùng `Child.FIELD`, tên `Child` trước dấu chấm không chứng minh field được **khai báo** trong `Child`. Java phân giải tên field tại lúc biên dịch theo quan hệ kế thừa và che khuất thành viên. Nếu field thực sự do `Parent` khai báo, thao tác đọc field `static` không phải hằng thời điểm biên dịch kích hoạt khởi tạo **`Parent`**, không tự kích hoạt `Child` chỉ do cách viết biểu thức.

Đối tượng `Field` giúp xác minh chủ sở hữu tại runtime: `getDeclaringClass()` xác định nơi khai báo; `getType()` xác định kiểu dữ liệu được khai báo. Hai kết quả này trả lời hai câu hỏi khác nhau. Ví dụ lưu vào `StaticFieldOwnerDemo.java`:

~~~java
import java.lang.reflect.Field;

public class StaticFieldOwnerDemo {
    public static class Parent {
        public static int SHARED = initialize();

        private static int initialize() {
            System.out.println("init Parent");
            return 10;
        }
    }

    public static class Child extends Parent {
        static {
            System.out.println("init Child");
        }

        public static int OWN = 20;
    }

    public static void main(String[] args) throws ReflectiveOperationException {
        Field inherited = Child.class.getField("SHARED");
        System.out.println("declaring type: "
                + inherited.getDeclaringClass().getSimpleName());
        System.out.println("reflective read: " + inherited.get(null));
        System.out.println("Child.SHARED: " + Child.SHARED);
        System.out.println("Child.OWN: " + Child.OWN);
    }
}
~~~

~~~bash
javac StaticFieldOwnerDemo.java
java StaticFieldOwnerDemo
~~~

~~~text
declaring type: Parent
init Parent
reflective read: 10
Child.SHARED: 10
init Child
Child.OWN: 20
~~~

Tra cứu bằng `Child.class.getField("SHARED")` tìm thấy field public được kế thừa mà chưa đọc giá trị field. `getDeclaringClass()` trả về `Parent`; sau đó `get(null)` kích hoạt khởi tạo `Parent` để đọc `SHARED`. Biểu thức `Child.SHARED` cũng trỏ đến field do `Parent` khai báo, nên không khởi tạo `Child`. Chỉ khi đọc `Child.OWN`, field do chính `Child` khai báo, chương trình mới in `init Child`.

**Field hiding** là trường hợp khác: nếu `Child` tự khai báo field cùng tên với `Parent.SHARED`, mỗi khai báo có một field riêng. `Child.class.getDeclaredField("SHARED")` trả về field của `Child`, còn `Parent.class.getDeclaredField("SHARED")` trả về field của `Parent`. Kiểu tham chiếu dùng để truy cập quyết định khai báo được phân giải; với Reflection, hãy kiểm tra `getDeclaringClass()` để tránh suy luận nhầm. Quy tắc này cũng áp dụng khi field được khai báo bởi một interface và được tham chiếu qua tên interface con.

## 6. Field private và giới hạn truy cập

`getDeclaredField` có thể tìm một field `private`, nhưng tìm thấy không có nghĩa là được phép đọc nó. Với field private trong mã do ứng dụng kiểm soát, có thể yêu cầu mở quyền truy cập bằng `field.setAccessible(true)` trước khi đọc:

```java
Field field = Settings.class.getDeclaredField("SECRET");
field.setAccessible(true);
Object secret = field.get(null); // chỉ khi quyền truy cập được cho phép
```

Trong Java hiện đại, `setAccessible(true)` có thể thất bại, chẳng hạn với `InaccessibleObjectException`, nếu ranh giới module không cho phép mở quyền truy cập. Không nên dựa vào việc phá vỡ encapsulation khi API công khai đã đáp ứng nhu cầu. Chỉ đọc private field khi có lý do rõ ràng và kiểm soát được môi trường chạy.

Với `static final` field, việc đọc và việc sửa là hai chuyện khác nhau. Không nên dùng Reflection để cố sửa hằng số; quyền sửa final field bị hạn chế và không phải một cách cập nhật cấu hình đáng tin cậy.

## 7. Xử lý lỗi và các lưu ý thực tế

- `NoSuchFieldException`: tên field không tồn tại trong lớp được truy vấn bằng `getDeclaredField`, hoặc field nằm trong một lớp khác như lớp cha.
- `IllegalAccessException`: chương trình không có quyền truy cập field theo quy tắc truy cập hiện hành.
- `InaccessibleObjectException`: yêu cầu mở quyền truy cập bị hệ thống module từ chối khi dùng `setAccessible(true)`.
- `IllegalArgumentException`: đối tượng truyền cho field instance không tương thích với kiểu khai báo của field. Với static field, đối số instance không được sử dụng.
- `getType()` trả về kiểu khai báo, còn `getGenericType()` hữu ích khi cần thông tin generic như `List<String>`. Do type erasure, `getType()` của field `List<String>` chỉ là `List.class`.
- Nếu giá trị là kiểu nguyên thủy như `int`, Reflection trả giá trị qua cơ chế boxing khi dùng `Field.get`, ví dụ giá trị `int` được biểu diễn dưới dạng `Integer` trong `Object`.
- Khi chỉ cần đọc một giá trị trong mã ứng dụng bình thường, truy cập trực tiếp `Settings.LIMIT` thường rõ ràng và an toàn hơn. Reflection phù hợp khi tên lớp/field cần được khám phá lúc chạy, chẳng hạn trong framework, công cụ kiểm tra hoặc bộ ánh xạ dữ liệu.

## 8. Checklist

- [ ] Dùng đúng `Class<?>` của lớp chứa field.
- [ ] Chọn `getDeclaredField` cho field khai báo trực tiếp hoặc `getField` cho field public kể cả khi được kế thừa.
- [ ] Dùng `Modifier.isStatic(...)` nếu cần xác minh field là static.
- [ ] Gọi `field.get(null)` để đọc static field.
- [ ] Dùng `field.getType()` cho kiểu khai báo và `value.getClass()` cho lớp runtime khi giá trị khác `null`.
- [ ] Xử lý ngoại lệ Reflection và quyền truy cập theo môi trường module.

Quy tắc quan trọng nhất: kiểu khai báo thuộc về định nghĩa field; kiểu runtime thuộc về đối tượng đang được tham chiếu. Khi đọc static field bằng Reflection, lấy field từ đúng lớp, đọc với `get(null)`, rồi chọn API kiểu phù hợp với câu hỏi cần trả lời.
