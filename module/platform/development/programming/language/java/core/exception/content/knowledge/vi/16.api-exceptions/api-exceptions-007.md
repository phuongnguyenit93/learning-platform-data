# ReflectiveOperationException và các lỗi tra cứu bằng reflection trong Java

## 1. Mục tiêu bài học

**Reflection** cho phép chương trình Java kiểm tra và thao tác với cấu trúc lớp khi đang chạy: tìm lớp theo tên, tra cứu phương thức, trường, constructor, tạo đối tượng, đọc/ghi trường và gọi phương thức động. Nó rất hữu ích trong framework dependency injection, serialization, plugin loading, ORM, test framework và công cụ phát triển.

Tuy nhiên, reflection chuyển một phần lỗi vốn thường được kiểm tra lúc biên dịch thành **lỗi phát sinh ở runtime**. Ví dụ, phương thức `getMethod("find", String.class)` có thể không tìm thấy method đúng chữ ký; `Class.forName("example.Plugin")` có thể không nạp được class; `Method.invoke(...)` có thể không được phép truy cập hoặc chính phương thức đích ném exception.

Java gom nhiều **checked exceptions liên quan thao tác phản chiếu** dưới `java.lang.ReflectiveOperationException`. Nắm cấu trúc này giúp bạn phân biệt:

- **Lỗi tra cứu metadata**: không tìm thấy class, method hoặc field.
- **Lỗi truy cập/thực thể hóa**: không được truy cập, không thể khởi tạo loại class được chọn.
- **Lỗi do code được gọi thực sự ném**: được bọc trong `InvocationTargetException`.
- **Lỗi runtime khác không thuộc nhánh `ReflectiveOperationException`**: đối số sai, module không cho phép mở quyền, lỗi khởi tạo class, security hoặc linkage.
- **Lỗi hợp đồng API**: dùng `getMethod` thay `getDeclaredMethod`, nhầm `int.class` với `Integer.class`, tra cứu sai tên package hoặc overload.

Bài sử dụng **Java 17+**. Các ví dụ hoàn chỉnh đi kèm tên file, lệnh `javac`/`java` và `stdout` dự kiến; mảnh code hoặc ví dụ sai được ghi rõ. Không cần thêm thư viện ngoài JDK.

## 2. Reflection hoạt động ở hai giai đoạn: *tra cứu* và *sử dụng*

Hãy xem hai bước khác nhau:

```text
Tên class / method / field
          |
          v
[1] TRA CỨU bằng reflection
    Class.forName(...)
    type.getMethod(...)
    type.getDeclaredField(...)
    type.getConstructor(...)
          |
          | trả về Class / Method / Field / Constructor
          v
[2] SỬ DỤNG đối tượng phản chiếu
    method.invoke(target, arguments)
    field.get(target), field.set(...)
    constructor.newInstance(arguments)
          |
          v
    Kết quả hoặc exception ở runtime
```

Lỗi ở giai đoạn **tra cứu** không nhất thiết giống lỗi ở giai đoạn **sử dụng**. `getDeclaredMethod(...)` trả về `Method` khi tìm thấy thành viên private, nhưng việc tìm thấy không tự động đồng nghĩa caller có quyền `invoke(...)`. Ngược lại, có thể tra cứu và truy cập thành công, nhưng **phương thức đích** ném `IllegalArgumentException`, `IOException` hay loại Throwable khác trong thân; Java bọc lỗi từ phương thức đích vào `InvocationTargetException` khi gọi qua `Method.invoke`.

### Hai đoạn minh họa

```java
Class<?> type = Class.forName("java.lang.String");
java.lang.reflect.Method method =
        type.getMethod("substring", int.class);
```

`Class.forName` có thể ném `ClassNotFoundException`; `getMethod` có thể ném `NoSuchMethodException`.

```java
String value = (String) method.invoke("abcdef", 2);
```

Đây là **mảnh mã** nối tiếp đoạn trước, bên trong method xử lý/khai báo checked exception. `invoke` có thể ném `IllegalAccessException` và `InvocationTargetException`, trong khi truyền sai target hoặc đối số có thể gây `IllegalArgumentException` hay ngoại lệ runtime khác.

**Thông điệp chính:** đừng bắt `NoSuchMethodException` ở giai đoạn `invoke` rồi tin rằng nó giải quyết được mọi lỗi. Đó là hai thao tác với **hai hợp đồng ngoại lệ** khác nhau.

## 3. Hệ phân cấp `ReflectiveOperationException`

Cây kiểu rút gọn trong Java 17:

```text
Throwable
└── Exception
    └── ReflectiveOperationException               [checked]
        ├── ClassNotFoundException
        ├── IllegalAccessException
        ├── InstantiationException
        ├── NoSuchFieldException
        ├── NoSuchMethodException
        └── java.lang.reflect.InvocationTargetException
```

Mọi subtype vừa liệt kê là **checked exception**, vì `ReflectiveOperationException` thuộc `Exception` nhưng không phải `RuntimeException`. Caller phải `catch` hoặc khai báo `throws` khi API có thể truyền chúng ra ngoài.

| Ngoại lệ | Giai đoạn thường gặp | Điểm cốt lõi |
| --- | --- | --- |
| `ClassNotFoundException` | Nạp class bằng tên | Loader không tìm được class yêu cầu |
| `NoSuchMethodException` | `getMethod`, `getDeclaredMethod`, tra cứu constructor | Không có chữ ký phù hợp theo API tra cứu |
| `NoSuchFieldException` | `getField`, `getDeclaredField` | Không có field đúng tên trong phạm vi tìm kiếm |
| `IllegalAccessException` | `Method.invoke`, `Field.get/set`, `Constructor.newInstance` | Caller không có quyền truy cập thành viên tương ứng |
| `InstantiationException` | Khởi tạo phản chiếu một class không thể instantiate, chẳng hạn abstract class | Loại đích không thể tạo instance theo hợp đồng |
| `InvocationTargetException` | `Method.invoke`, `Constructor.newInstance` | Thân method/constructor được gọi đã ném một Throwable |

Không phải mọi lỗi reflection đều kế thừa lớp này. Ví dụ:

- `IllegalArgumentException` là unchecked: truyền sai số lượng/kiểu tham số, receiver không phù hợp.
- `InaccessibleObjectException` là unchecked: cố mở quyền truy cập bị giới hạn bởi module.
- `SecurityException` là unchecked: chính sách bảo mật không cho thao tác.
- `ExceptionInInitializerError` và `LinkageError` là lỗi kiểu `Error`: sự cố khởi tạo/liên kết class, không phải `ReflectiveOperationException`.
- `NullPointerException` có thể xảy ra với receiver `null` khi gọi instance method qua reflection.
- `ClassCastException` có thể xảy ra khi **caller ép kiểu sai** kết quả của `invoke`.

Do đó `catch (ReflectiveOperationException e)` rất hữu ích để gom **một nhóm checked reflection failure**, nhưng không được diễn giải là “bắt được tất cả lỗi reflection”.

## 4. Checked exception trong reflection và hợp đồng `throws`

Một helper dùng nhiều API reflection có thể khai báo kiểu cha:

```java
static Object createByName(String className)
        throws ReflectiveOperationException {
    Class<?> type = Class.forName(className);
    return type.getDeclaredConstructor().newInstance();
}
```

Đây là **phương thức minh họa**. `Class.forName` có thể ném `ClassNotFoundException`. `getDeclaredConstructor()` có thể ném `NoSuchMethodException`. `newInstance()` có thể ném `InstantiationException`, `IllegalAccessException` và `InvocationTargetException`. Tất cả nằm dưới `ReflectiveOperationException`.

**Ưu điểm:** `throws ReflectiveOperationException` giúp caller có một hợp đồng checked chung cho quá trình reflection.

**Đánh đổi:** nếu caller cần quyết định khác nhau giữa “class không tồn tại” và “constructor đích ném lỗi”, chỉ bắt kiểu cha có thể làm mất mức phân loại tại chỗ. Bạn vẫn có thể kiểm tra `instanceof` hoặc đặt các `catch` cụ thể trước `catch (ReflectiveOperationException)`.

```java
try {
    Object instance = createByName("sample.Plugin");
} catch (ClassNotFoundException missingClass) {
    // Xử lý cấu hình tên class không có.
} catch (NoSuchMethodException missingConstructor) {
    // Không tìm thấy constructor không tham số.
} catch (ReflectiveOperationException otherReflectionFailure) {
    // Những checked reflection failure còn lại.
}
```

Đây là **mảnh minh họa**, không phải chương trình độc lập. Cần phân biệt `ClassNotFoundException` với các runtime errors, kể cả khi đã có handler chung.

### So với gọi method Java thông thường

Một lời gọi `service.doWork()` được javac kiểm tra chữ ký của method ở compile time. Khi dùng `type.getMethod("doWork").invoke(service)`, phần tìm kiếm theo chuỗi và danh sách `Class<?>` được thực hiện ở runtime. Compiler không thể chứng minh mọi class/overload/visibility đều đúng trong mọi lần chạy. Reflection mang theo hợp đồng lỗi động tương ứng.

## 5. `ClassNotFoundException`: không tìm thấy class theo tên

API phổ biến:

```java
Class<?> type = Class.forName("com.example.Plugin");
```

Đây là mảnh minh họa. Dạng `Class.forName(String)` thực hiện nạp và **khởi tạo** class theo quy tắc API; nếu không tìm được class đích, nó có thể ném `ClassNotFoundException`.

Các lý do phổ biến:

- Tên class đầy đủ sai package hoặc sai chữ hoa/chữ thường.
- JAR chứa class không nằm trong classpath/module path phù hợp.
- Class loader đang dùng không thấy class.
- Cấu hình plugin tham chiếu class đã đổi tên, chưa được triển khai hoặc không còn tồn tại.
- Tên binary name không đúng: nested class có thể có dạng `Outer$Inner` thay vì `Outer.Inner` khi dùng chuỗi tên runtime.

**Không nhầm** `ClassNotFoundException` với `NoClassDefFoundError`. Lỗi thứ hai thuộc `LinkageError` và có thể xuất hiện trong quá trình tải/liên kết một class vốn từng được tìm thấy theo tên nhưng không thể có định nghĩa cần thiết ở runtime, hoặc do lỗi khởi tạo class trước đó. Hai tình huống có quan hệ vận hành nhưng **không cùng nhánh exception**.

### Chương trình chạy được: nạp một class có sẵn và bắt lỗi thiếu class

Tạo file **`ClassLookupDemo.java`**:

```java
public class ClassLookupDemo {
    public static void main(String[] args) {
        try {
            Class<?> found = Class.forName("java.lang.String");
            System.out.println("found=" + found.getName());
        } catch (ClassNotFoundException failure) {
            System.out.println("unexpected");
        }

        try {
            Class.forName("training.example.DefinitelyMissingClass");
        } catch (ClassNotFoundException failure) {
            System.out.println("missing="
                    + failure.getClass().getSimpleName());
        }
    }
}
```

```bash
javac ClassLookupDemo.java
java ClassLookupDemo
```

`stdout`:

```text
found=java.lang.String
missing=ClassNotFoundException
```

Chương trình cố ý tìm tên không tồn tại `training.example.DefinitelyMissingClass`. Bài chạy giả định tên này chưa được ứng dụng cung cấp trên classpath/module path, điều đúng với môi trường Java 17 thông thường.

### `Class.forName` và `ClassLoader.loadClass`

`Class.forName(String)` có hành vi khởi tạo class; `ClassLoader.loadClass(String)` thường chỉ nạp class chứ không khởi tạo ngay. Dạng `Class.forName(name, false, loader)` cho phép yêu cầu **không khởi tạo ngay**. Điều này quan trọng vì class có static initializer có thể gây side effect hoặc thất bại trong lúc load/initialize.

Không coi việc “nạp class” là thao tác thuần kiểm tra tên không có hậu quả trong mọi API. Khi class đến từ plugin không tin cậy hoặc cấu hình người dùng, cần đánh giá chính sách loader và quá trình khởi tạo.

## 6. `NoSuchMethodException`: tìm không đúng chữ ký method

`Class.getMethod(name, parameterTypes...)` tìm **public method** theo tên và danh sách kiểu tham số, kể cả các public method được thừa kế phù hợp. `Class.getDeclaredMethod(name, parameterTypes...)` chỉ tìm các method **được khai báo trực tiếp trong class** đang xét, không tự tìm ở superclass; nó có thể tìm private/protected/package-private.

Ví dụ:

```java
java.lang.reflect.Method method =
        String.class.getMethod("substring", int.class);
```

Đây là mảnh code hợp lệ trong method `throws NoSuchMethodException` hoặc `try/catch`. `String.substring(int)` có public method; kết quả là một đối tượng `Method` mô tả phương thức đó.

Sai tên hoặc sai tham số:

```java
String.class.getMethod("substring", String.class);
```

Đây là mảnh code được phép biên dịch nhưng **ném `NoSuchMethodException` ở runtime**, vì không có public `substring(String)` tương ứng.

### Kiểu tham số phải chính xác

Tra cứu method bằng reflection dựa trên **kiểu tham số được đưa vào** qua những token `Class<?>`:

- `int.class` **khác** `Integer.class`.
- `String.class` khác `Object.class`.
- Các overload cùng tên nhưng khác kiểu tham số là những method khác nhau.
- Với mảng, dùng loại array phù hợp, ví dụ `String[].class`.
- `getMethod` không tự đoán overload dựa trên giá trị bạn dự định truyền sau đó vào `invoke`.
- Với generic, type erasure có thể khiến tham số runtime khác với cách viết type parameter trong source.
- Kiểu trả về **không** nằm trong danh sách đối số tra cứu của `getMethod`.

Ví dụ method `sum(int,int)` phải tra bằng `getMethod("sum", int.class, int.class)`. Truyền `Integer.class` sẽ không tự được unbox trong **giai đoạn tra cứu**.

### Chương trình chạy được: public, private và chữ ký sai

Tạo file **`MethodLookupDemo.java`**:

```java
import java.lang.reflect.Method;

public class MethodLookupDemo {
    public static class Greeting {
        public String greet(String name) {
            return "Hello " + name;
        }

        private int code() {
            return 42;
        }
    }

    public static void main(String[] args)
            throws ReflectiveOperationException {
        Greeting target = new Greeting();

        Method publicMethod =
                Greeting.class.getMethod("greet", String.class);
        System.out.println("public="
                + publicMethod.invoke(target, "Java"));

        try {
            Greeting.class.getMethod("code");
        } catch (NoSuchMethodException failure) {
            System.out.println("getMethod private=not found");
        }

        Method privateMethod =
                Greeting.class.getDeclaredMethod("code");
        System.out.println("declared=" + privateMethod.getName());

        try {
            Greeting.class.getMethod("greet", int.class);
        } catch (NoSuchMethodException failure) {
            System.out.println("wrong signature=not found");
        }
    }
}
```

```bash
javac MethodLookupDemo.java
java MethodLookupDemo
```

`stdout`:

```text
public=Hello Java
getMethod private=not found
declared=code
wrong signature=not found
```

Trong chương trình:

1. `getMethod("greet", String.class)` thành công vì có public method khớp chữ ký.
2. `getMethod("code")` thất bại vì `code()` là private, không thuộc tập public method mà API tìm.
3. `getDeclaredMethod("code")` tìm được method private **được khai báo trực tiếp**, nhưng tìm được không có nghĩa mọi caller đều được gọi nó.
4. `getMethod("greet", int.class)` thất bại vì `Greeting` không có overload `greet(int)`.

Không nên thay `NoSuchMethodException` bằng `ClassNotFoundException`: ở giai đoạn này class đã có, nhưng **member không đúng tên/chữ ký**.

## 7. `getMethod` khác `getDeclaredMethod` khi kế thừa

Với class con kế thừa một public method:

- `Child.class.getMethod("inherited")` có thể thành công.
- `Child.class.getDeclaredMethod("inherited")` không tìm thấy nếu class con **không tự khai báo** method đó.
- `getDeclaredMethod` có thể tìm private method của chính class con mà `getMethod` không thấy.
- `getMethods()` và `getDeclaredMethods()` có phạm vi tương tự dạng số nhiều; danh sách trả về không nên bị dựa vào thứ tự mặc định để suy ra API ổn định.

### Chương trình độc lập: phương thức kế thừa

Tạo file **`InheritedMethodLookupDemo.java`**:

```java
public class InheritedMethodLookupDemo {
    public static class Parent {
        public void inherited() {
        }
    }

    public static class Child extends Parent {
        private void local() {
        }
    }

    public static void main(String[] args) {
        try {
            System.out.println("public inherited="
                    + Child.class.getMethod("inherited").getName());
        } catch (NoSuchMethodException failure) {
            System.out.println("unexpected");
        }

        try {
            Child.class.getDeclaredMethod("inherited");
        } catch (NoSuchMethodException failure) {
            System.out.println("declared inherited=missing");
        }

        try {
            System.out.println("declared private="
                    + Child.class.getDeclaredMethod("local").getName());
        } catch (NoSuchMethodException failure) {
            System.out.println("unexpected");
        }
    }
}
```

```bash
javac InheritedMethodLookupDemo.java
java InheritedMethodLookupDemo
```

`stdout`:

```text
public inherited=inherited
declared inherited=missing
declared private=local
```

Trong các ví dụ về class hierarchy, hãy hỏi: *method được khai báo ở lớp nào?* và *API đang yêu cầu public/inherited hay declared/direct?* Điều này thường giải thích `NoSuchMethodException` nhanh hơn việc kiểm tra lại cùng một tên nhiều lần.

### Lưu ý overload, bridge method và varargs

Với generic, compiler có thể sinh **bridge methods** để bảo toàn overriding sau type erasure. `getDeclaredMethods()` có thể hiển thị cả các member synthetic/bridge. Không viết resolver riêng chỉ dựa vào thứ tự của mảng reflection. Nếu cần phân biệt, `Method.isBridge()` và `Method.isSynthetic()` là các API hữu ích.

Varargs được thể hiện bằng **một tham số mảng** ở mức signature. Ví dụ một phương thức `log(String... parts)` dùng `String[].class` khi tra cứu, không phải một số `String.class` tùy ý.

## 8. `NoSuchFieldException`: không tìm thấy trường đúng phạm vi

`Class.getField(name)` tìm **public field** theo quy tắc tra cứu của API, kể cả những public field được thừa kế. `Class.getDeclaredField(name)` tìm field **được khai báo trực tiếp** trong class, bất kể modifier, nhưng không tìm ở superclass.

Các lỗi thường gặp:

- Nhầm field với getter/setter (JavaBean property không nhất thiết là field).
- Tên field viết sai hoặc khác chữ hoa.
- Field là private nên `getField` không thấy.
- Field ở superclass nên `getDeclaredField` của subclass không thấy.
- Nhầm static field với instance field ở bước `Field.get`/`Field.set`.

### Chương trình chạy được: field công khai và field private

Tạo file **`FieldLookupDemo.java`**:

```java
import java.lang.reflect.Field;

public class FieldLookupDemo {
    public static class Box {
        public int count = 3;
        private String token = "secret";
    }

    public static void main(String[] args)
            throws ReflectiveOperationException {
        Box box = new Box();

        Field visible = Box.class.getField("count");
        System.out.println("count=" + visible.getInt(box));

        try {
            Box.class.getField("token");
        } catch (NoSuchFieldException failure) {
            System.out.println("public token=missing");
        }

        Field declared = Box.class.getDeclaredField("token");
        System.out.println("declared token=" + declared.getName());

        try {
            Box.class.getDeclaredField("unknown");
        } catch (NoSuchFieldException failure) {
            System.out.println("unknown=missing");
        }
    }
}
```

```bash
javac FieldLookupDemo.java
java FieldLookupDemo
```

`stdout`:

```text
count=3
public token=missing
declared token=token
unknown=missing
```

Lỗi tra cứu field là `NoSuchFieldException`; việc tìm thấy `Field` rồi gọi `getInt`/`set` có thể gặp `IllegalAccessException` hoặc `IllegalArgumentException` tùy quyền và receiver/type.

### `getField` và `getDeclaredField` không trả về giá trị field

Chúng trả về **đối tượng metadata `Field`**, không phải giá trị trực tiếp. Phải dùng `field.get(receiver)`, `field.getInt(receiver)` hay API thích hợp để truy cập dữ liệu. Đối với instance field, receiver phải có kiểu phù hợp. Đối với static field, API cho phép receiver `null` ở những trường hợp tương ứng.

Nếu class có getter công khai, đôi khi gọi getter qua interface bình thường sẽ an toàn, dễ bảo trì và type-safe hơn truy cập private field bằng reflection.

## 9. Không tìm thấy constructor: vẫn là `NoSuchMethodException`

Reflection constructor dùng `Class.getConstructor(parameterTypes...)` và `Class.getDeclaredConstructor(parameterTypes...)`.

- `getConstructor(...)` chỉ tìm **public constructor** phù hợp trong class đích.
- `getDeclaredConstructor(...)` tìm constructor được khai báo trong class đó, kể cả private.
- Constructor **không được kế thừa**, nên không có “constructor ở superclass kế thừa cho subclass”.
- Không tìm thấy constructor khớp danh sách tham số → `NoSuchMethodException`, **không** có lớp `NoSuchConstructorException` trong API chuẩn này.
- `newInstance(arguments...)` trên đối tượng `Constructor` mới là bước **thực sự tạo object**.

### Chương trình chạy được: hai constructor khác nhau

Tạo file **`ConstructorLookupDemo.java`**:

```java
import java.lang.reflect.Constructor;

public class ConstructorLookupDemo {
    public static class Config {
        private final String mode;

        public Config(String mode) {
            this.mode = mode;
        }

        private Config() {
            this.mode = "internal";
        }

        public String mode() {
            return mode;
        }
    }

    public static void main(String[] args)
            throws ReflectiveOperationException {
        Constructor<Config> publicConstructor =
                Config.class.getConstructor(String.class);
        Config created = publicConstructor.newInstance("production");
        System.out.println("public=" + created.mode());

        try {
            Config.class.getConstructor();
        } catch (NoSuchMethodException failure) {
            System.out.println("public empty=missing");
        }

        Constructor<Config> privateConstructor =
                Config.class.getDeclaredConstructor();
        System.out.println("declared empty="
                + privateConstructor.getParameterCount());
    }
}
```

```bash
javac ConstructorLookupDemo.java
java ConstructorLookupDemo
```

`stdout`:

```text
public=production
public empty=missing
declared empty=0
```

`getDeclaredConstructor()` **tìm được** constructor private không tham số. Ví dụ không tự cố gọi nó ở đây để tránh trộn lỗi *lookup* với vấn đề *access*. Khi có lý do hợp lệ để gọi một constructor non-public, cần kiểm tra chính sách quyền truy cập/module như các mục tiếp theo.

### Tránh `Class.newInstance()`

`Class.newInstance()` đã bị đánh dấu deprecated trong Java hiện đại. Ưu tiên:

```java
Object value = type.getDeclaredConstructor().newInstance();
```

Đây là **mảnh code** với `type` kiểu `Class<?>`. Mẫu dùng `Constructor.newInstance` biểu diễn rõ thao tác tra cứu, quyền truy cập và wrapper `InvocationTargetException`, thay vì đặc điểm nguy hiểm của `Class.newInstance()` khi truyền exception từ constructor ra ngoài theo cách khó kiểm soát checked exception.

## 10. `IllegalAccessException`: tìm được không có nghĩa gọi được

Reflection vẫn phải tôn trọng kiểm tra quyền truy cập Java, trừ khi có cơ chế phù hợp được cho phép. Một object `Method`, `Field` hoặc `Constructor` có thể được tra cứu thành công nhưng vẫn **không được phép sử dụng** từ caller.

`IllegalAccessException` là **checked exception** có thể xuất hiện khi:

- `Method.invoke(...)` cố gọi method mà caller không được truy cập.
- `Constructor.newInstance(...)` cố gọi constructor không được phép.
- `Field.get(...)`/`Field.set(...)` truy cập field không đủ quyền.

### Chương trình chạy được: tra cứu private rồi thử truy cập

Tạo file **`ReflectionAccessDemo.java`**:

```java
import java.lang.reflect.Method;

class PrivateVault {
    private String secret() {
        return "vault-value";
    }
}

public class ReflectionAccessDemo {
    public static void main(String[] args)
            throws ReflectiveOperationException {
        PrivateVault vault = new PrivateVault();
        Method secret =
                PrivateVault.class.getDeclaredMethod("secret");

        try {
            secret.invoke(vault);
        } catch (IllegalAccessException failure) {
            System.out.println("before=IllegalAccessException");
        }

        boolean opened = secret.trySetAccessible();
        System.out.println("trySetAccessible=" + opened);

        if (opened) {
            System.out.println("after=" + secret.invoke(vault));
        }
    }
}
```

```bash
javac ReflectionAccessDemo.java
java ReflectionAccessDemo
```

`stdout` trong một ứng dụng Java 17 thông thường chạy **trên classpath, ở unnamed module**:

```text
before=IllegalAccessException
trySetAccessible=true
after=vault-value
```

Điểm tinh tế: `PrivateVault` là class top-level riêng, **không phải nested class cùng nest** với `ReflectionAccessDemo`. Vì vậy code caller không có quyền trực tiếp gọi method private `secret()` trước khi mở accessibility. Trong cùng unnamed module ở ví dụ, `trySetAccessible()` có thể bật quyền truy cập.

**Không tổng quát hóa output này sang mọi module.** Trong một named module mà package không được `opens` cho module đang gọi, `trySetAccessible()` có thể trả `false`. `setAccessible(true)` có thể ném `InaccessibleObjectException` (unchecked). Với `SecurityManager`/chính sách bảo mật ở môi trường phù hợp, có thể còn gặp `SecurityException`.

### `setAccessible(true)` không phải chìa khóa vượt mọi quyền

Từ Java 9 trở đi, **Java Platform Module System (JPMS)** áp dụng strong encapsulation. Có những trường hợp không được mở quyền truy cập sâu cho private member của module khác, kể cả khi class và method đã được tìm thấy.

- `getDeclaredMethod` chỉ tra cứu metadata.
- `trySetAccessible` yêu cầu nới quyền và trả `true` nếu thành công; có thể trả `false` khi không thể.
- `setAccessible(true)` có thể ném `InaccessibleObjectException` khi không được phép mở.
- Module cung cấp API public nên `exports` package phù hợp nếu cần người dùng bên ngoài.
- Deep reflection vào thành viên non-public giữa modules thường đòi hỏi package được `opens` theo thiết kế hoặc cấu hình chạy phù hợp.

Trong thư viện ứng dụng, **ưu tiên public API và interface** thay vì dựa vào mở private member; không hướng dẫn lạm dụng `--add-opens` chỉ để tránh sửa một thiết kế access đang sai.

## 11. `InvocationTargetException`: phương thức hoặc constructor đích đã ném lỗi

Đây là một điểm rất dễ nhầm.

Giả sử method đích có mã:

```java
public void work() {
    throw new IllegalStateException("business failed");
}
```

Nếu gọi bình thường, caller nhận trực tiếp `IllegalStateException`. Nhưng khi gọi qua:

```java
method.invoke(target);
```

thì **lỗi được method đích ném** được `Method.invoke` bọc trong `InvocationTargetException`. Caller cần đọc `getCause()` hoặc `getTargetException()` của wrapper để biết lỗi đích thực sự là gì.

Không nên ghi “`InvocationTargetException` luôn có nghĩa lookup sai”. Thường lookup đã thành công; **target invocation** đã xảy ra và code đích thất bại.

### Chương trình chạy được: lỗi RuntimeException và checked IOException

Tạo file **`InvocationTargetDemo.java`**:

```java
import java.io.IOException;
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Method;

public class InvocationTargetDemo {
    public static class Worker {
        public void failRuntime() {
            throw new IllegalStateException("invalid state");
        }

        public void failChecked() throws IOException {
            throw new IOException("disk failed");
        }
    }

    public static void main(String[] args)
            throws ReflectiveOperationException {
        Worker target = new Worker();

        Method runtime =
                Worker.class.getMethod("failRuntime");
        try {
            runtime.invoke(target);
        } catch (InvocationTargetException wrapper) {
            Throwable cause = wrapper.getCause();
            System.out.println("runtime wrapper="
                    + wrapper.getClass().getSimpleName());
            System.out.println("runtime cause="
                    + cause.getClass().getSimpleName());
            System.out.println("runtime message=" + cause.getMessage());
        }

        Method checked =
                Worker.class.getMethod("failChecked");
        try {
            checked.invoke(target);
        } catch (InvocationTargetException wrapper) {
            Throwable cause = wrapper.getTargetException();
            System.out.println("checked cause="
                    + cause.getClass().getSimpleName());
            System.out.println("checked message=" + cause.getMessage());
        }
    }
}
```

```bash
javac InvocationTargetDemo.java
java InvocationTargetDemo
```

`stdout`:

```text
runtime wrapper=InvocationTargetException
runtime cause=IllegalStateException
runtime message=invalid state
checked cause=IOException
checked message=disk failed
```

Giải thích:

1. `getMethod(...)` tìm thấy public method; không có `NoSuchMethodException` trong đường thành công.
2. `invoke(...)` thực sự chạy body method.
3. Body ném `IllegalStateException` ở lần thứ nhất, `IOException` ở lần thứ hai.
4. `Method.invoke` gói Throwable đích trong `InvocationTargetException`.
5. `getCause()` và `getTargetException()` cho phép lấy **đối tượng Throwable gốc** được target ném.

Nếu constructor được gọi qua `Constructor.newInstance(...)` và **thân constructor** ném exception, nó cũng có thể được bọc trong `InvocationTargetException`. Nhưng nếu class là abstract và không thể instantiate, có thể nhận `InstantiationException` trước khi body constructor có cơ hội chạy.

### Không tự động xem cause là “unchecked”

Lỗi trong `InvocationTargetException#getCause()` có thể là checked, unchecked hoặc `Error`. Việc phản chiếu không xóa class runtime của throwable đích. Khi chuyển lỗi thành exception miền nghiệp vụ, giữ đúng `cause` nếu phải bọc tiếp.

## 12. `InstantiationException`: lớp không thể tạo instance

`InstantiationException` là checked exception trong nhánh `ReflectiveOperationException`. Một tình huống quen thuộc là cố khởi tạo **abstract class** bằng reflection.

- `AbstractType.class.getDeclaredConstructor()` có thể **tìm được constructor**.
- Nhưng `constructor.newInstance()` không thể tạo một instance trực tiếp của abstract class → `InstantiationException`.
- Đây là thất bại **ở bước tạo object**, không phải `NoSuchMethodException` của bước lookup.

### Chương trình chạy được: abstract class

Tạo file **`InstantiationReflectionDemo.java`**:

```java
import java.lang.reflect.Constructor;

public class InstantiationReflectionDemo {
    public static abstract class AbstractTask {
        public AbstractTask() {
        }
    }

    public static void main(String[] args)
            throws ReflectiveOperationException {
        Constructor<AbstractTask> constructor =
                AbstractTask.class.getDeclaredConstructor();

        System.out.println("constructor found");

        try {
            constructor.newInstance();
        } catch (InstantiationException failure) {
            System.out.println("instantiate="
                    + failure.getClass().getSimpleName());
        }
    }
}
```

```bash
javac InstantiationReflectionDemo.java
java InstantiationReflectionDemo
```

`stdout`:

```text
constructor found
instantiate=InstantiationException
```

Nếu class có constructor không tham số public và là class cụ thể phù hợp, `Constructor.newInstance()` có thể tạo instance. Nhưng constructor có thể thực thi logic nghiệp vụ và thất bại, trong trường hợp đó lỗi body được bọc thành `InvocationTargetException`.

**Đừng chỉ kiểm tra “có constructor” để suy ra “tạo instance chắc thành công”.** Còn phải xét class abstract, quyền truy cập, đối số, initialization và điều kiện môi trường.

## 13. `IllegalArgumentException`: sai target hoặc danh sách đối số

Phần lớn lỗi do truyền receiver/argument không đúng khi **invoke** được mô tả bằng ngoại lệ **unchecked**, không phải `ReflectiveOperationException`. Ví dụ:

- Đưa `String` vào một method instance thuộc class `Worker`.
- Gọi method cần hai tham số nhưng chỉ truyền một.
- Truyền `null` cho tham số primitive bắt buộc.
- Truyền kiểu không chuyển đổi được theo quy tắc `Method.invoke`.
- Gọi constructor với số lượng đối số không phù hợp.

Khi lookup:

```java
Method method = Calculator.class.getMethod(
        "add", int.class, int.class);
```

Sau đó invocation:

```java
method.invoke(new Calculator(), "bad", 2);
```

Đây là **hai mảnh code minh họa** giả định có class `Calculator` với public `add(int,int)`. Lookup có thể **thành công**, nhưng invocation với `"bad"` không phù hợp `int` và gây `IllegalArgumentException` — không phải `NoSuchMethodException`.

### Chương trình chạy được: không đánh đồng `invoke` sai và lookup sai

Tạo file **`InvocationArgumentsDemo.java`**:

```java
import java.lang.reflect.Method;

public class InvocationArgumentsDemo {
    public static class Calculator {
        public int add(int a, int b) {
            return a + b;
        }
    }

    public static void main(String[] args)
            throws ReflectiveOperationException {
        Method add = Calculator.class.getMethod(
                "add", int.class, int.class);

        System.out.println("correct="
                + add.invoke(new Calculator(), 3, 4));

        try {
            add.invoke(new Calculator(), "wrong", 4);
        } catch (IllegalArgumentException failure) {
            System.out.println("bad args=IllegalArgumentException");
        }

        try {
            Calculator.class.getMethod(
                    "add", Integer.class, Integer.class);
        } catch (NoSuchMethodException failure) {
            System.out.println("wrong lookup=NoSuchMethodException");
        }
    }
}
```

```bash
javac InvocationArgumentsDemo.java
java InvocationArgumentsDemo
```

`stdout`:

```text
correct=7
bad args=IllegalArgumentException
wrong lookup=NoSuchMethodException
```

Tại invocation đúng, hai đối số `Integer` từ autoboxing có thể được dùng cho tham số `int` theo quy tắc Method.invoke về unwrapping/widening. Nhưng **getMethod không làm autoboxing khi tìm chữ ký**: `int.class` khác `Integer.class`.

**Nhớ phân biệt:** sai signature ở `getMethod` → `NoSuchMethodException`; method đã tìm thấy nhưng truyền argument không đúng cho `invoke` → thường `IllegalArgumentException`.

## 14. Class initialization và linkage errors không được bao phủ hết

Ngay cả `Class.forName` đã nhận một tên đúng, quá trình **khởi tạo class** có thể thất bại ở static initializer. Điều đó có thể ném `ExceptionInInitializerError`, thuộc nhánh `Error`, chứ không phải `ReflectiveOperationException`.

Một số kiểu cần nhận diện:

| Tình huống | Loại kết quả/lỗi thường gặp | Thuộc `ReflectiveOperationException`? |
| --- | --- | --- |
| Class loader không tìm được class trong lời gọi `Class.forName` | `ClassNotFoundException` | Có |
| Một class cần thiết không thể liên kết/định nghĩa | `NoClassDefFoundError` hoặc `LinkageError` phù hợp | Không |
| Static initializer của class ném lỗi chưa được xử lý | `ExceptionInInitializerError` hoặc lỗi khởi tạo tương ứng | Không |
| Method/constructor được gọi bằng reflection tự ném | `InvocationTargetException` bao lấy lỗi target | Có wrapper |
| `setAccessible(true)` bị module từ chối | `InaccessibleObjectException` | Không |
| Sai argument tại `Method.invoke` | `IllegalArgumentException` | Không |

**Không gộp tất cả thành `ClassNotFoundException`** hoặc bắt `ReflectiveOperationException` rồi chắc chắn chương trình không còn lỗi runtime nào.

### `Class.forName(name, false, loader)` giúp gì?

Nó cho phép yêu cầu **không initialize class ngay**. Nhưng thao tác load/link vẫn có thể thất bại theo hợp đồng loader. Khi sau đó class được initialize lúc dùng, lỗi initializer vẫn có thể xảy ra. Đây là công cụ kiểm soát thời điểm khởi tạo, không phải “vô hiệu hóa mọi lỗi của class”.

Nếu tạo plugin từ tên class do người dùng nhập, cần xem xét *class loader nào được dùng*, class đó có implements interface mong đợi không, và thời điểm nào cho phép thực thi code của plugin.

## 15. Thiết kế factory an toàn kiểu với `Class<T>`

Reflection thường trả `Object`, dễ dẫn tới ép kiểu không an toàn. Nếu API cần tạo object thuộc interface hoặc supertype cụ thể, có thể dùng `Class<? extends T>` hoặc kiểm tra `Class.asSubclass(...)` để gắn hợp đồng kiểu.

Ví dụ phương thức factory đơn giản:

```java
static <T> T instantiate(Class<? extends T> type)
        throws ReflectiveOperationException {
    return type.getDeclaredConstructor().newInstance();
}
```

Đây là **mảnh method hợp lệ**. Nó chỉ hoạt động với class có constructor không tham số **mà caller được phép truy cập**, không phải mọi class tùy ý. Nó có thể ném `NoSuchMethodException`, `IllegalAccessException`, `InstantiationException` và `InvocationTargetException` theo tình huống.

### Chương trình chạy được: factory typed

Tạo file **`TypedReflectionFactoryDemo.java`**:

```java
public class TypedReflectionFactoryDemo {
    public interface Job {
        String run();
    }

    public static class GreetingJob implements Job {
        public GreetingJob() {
        }

        @Override
        public String run() {
            return "job completed";
        }
    }

    static <T> T instantiate(Class<? extends T> type)
            throws ReflectiveOperationException {
        return type.getDeclaredConstructor().newInstance();
    }

    public static void main(String[] args) {
        try {
            Job job = instantiate(GreetingJob.class);
            System.out.println("result=" + job.run());

            Class<?> loaded = Class.forName(
                    TypedReflectionFactoryDemo.GreetingJob.class.getName());
            Class<? extends Job> jobType =
                    loaded.asSubclass(Job.class);
            Job another = instantiate(jobType);
            System.out.println("dynamic=" + another.run());
        } catch (ReflectiveOperationException failure) {
            System.out.println("reflection failed");
        }
    }
}
```

```bash
javac TypedReflectionFactoryDemo.java
java TypedReflectionFactoryDemo
```

`stdout`:

```text
result=job completed
dynamic=job completed
```

Giải thích:

1. `instantiate(GreetingJob.class)` giữ hợp đồng trả về một `Job`.
2. `Class.forName(...)` biểu diễn bước nạp class theo tên ở runtime.
3. `loaded.asSubclass(Job.class)` kiểm tra class thực sự là subtype của `Job`.
4. `instantiate(jobType)` tạo object sau khi đã kiểm tra subtype.
5. Nếu class được nạp không phải một `Job`, `asSubclass` có thể ném **`ClassCastException` (unchecked)**; generic không tự xóa mọi lỗi runtime.

Một factory sản phẩm còn cần kiểm soát **danh sách loại class được phép nạp**, constructor parameters, module access, vòng đời tài nguyên và việc code constructor có thể chạy side effect.

### Không nạp class tùy ý chỉ từ dữ liệu không tin cậy

Tên class từ cấu hình hoặc request không đáng tin có thể làm chương trình tải và thực thi code không mong muốn trong classpath đã triển khai. Dù `Class.forName` có thể tìm class thành công, điều đó **không chứng minh class an toàn để khởi tạo**. Nên dùng allowlist, interface cụ thể, class loader phù hợp và phân quyền ở ranh giới plugin.

## 16. Bọc exception đúng cách khi đi qua tầng trừu tượng

Ở tầng API nội bộ, việc dùng `throws ReflectiveOperationException` có thể hợp lý. Nhưng tại ranh giới nghiệp vụ, caller thường không cần biết framework đang dùng reflection.

Ví dụ chuyển lỗi thành một ngoại lệ miền:

```java
try {
    return instantiate(type);
} catch (ReflectiveOperationException original) {
    throw new IllegalStateException(
            "Cannot create configured service", original);
}
```

Đây là **mảnh mã** giả định `instantiate` và `type` được khai báo. Constructor `(message, cause)` giữ `original` làm `cause`.

Nếu `original` là `InvocationTargetException`, nguyên nhân thực sự của method/constructor đích có thể nằm tại:

```java
original.getCause()
```

Nhưng không được mặc định mọi `ReflectiveOperationException` đều có cause. Ví dụ `NoSuchMethodException` do lookup sai có thể không có cause. Một công cụ chẩn đoán tốt cần đọc cả **loại exception, message, cause và suppressed**, chứ không chỉ gọi `getCause().getMessage()` mà không kiểm tra null.

### Khi xử lý `InvocationTargetException` nên làm gì?

Có ba chính sách hợp lệ tùy tầng:

1. **Giữ nguyên wrapper** làm cause của lỗi miền: bảo toàn đầy đủ ngữ cảnh gọi phản chiếu và nguyên nhân target.
2. **Lấy cause** khi thật sự muốn truyền lỗi nghiệp vụ gốc ra ngoài: phải xét nó có thể là `Exception`, `RuntimeException` hoặc `Error`, đồng thời giữ stack trace và suppressed.
3. **Phân loại cụ thể** theo loại target throwable để quyết định retry, dừng hay phục hồi.

Không tùy tiện `throw (Exception) wrapper.getCause()`: cast này có thể thất bại nếu cause là `Error`. Cũng không thay tất cả lỗi bằng `new RuntimeException(wrapper.getMessage())`, vì làm mất cause target.

## 17. Chương trình tổng hợp: phân loại lookup failure và target failure

Tạo file **`ReflectionFailureDecisionDemo.java`**:

```java
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Method;

public class ReflectionFailureDecisionDemo {
    public static class Handler {
        public void run() {
            throw new IllegalArgumentException("invalid request");
        }
    }

    static void call(String methodName)
            throws ReflectiveOperationException {
        Method method =
                Handler.class.getMethod(methodName);
        method.invoke(new Handler());
    }

    public static void main(String[] args) {
        for (String name : new String[] {"missing", "run"}) {
            try {
                call(name);
            } catch (NoSuchMethodException failure) {
                System.out.println(name + ": method not found");
            } catch (InvocationTargetException failure) {
                System.out.println(name + ": target threw "
                        + failure.getCause()
                                .getClass().getSimpleName());
            } catch (ReflectiveOperationException failure) {
                System.out.println(name + ": other reflection failure");
            }
        }
    }
}
```

```bash
javac ReflectionFailureDecisionDemo.java
java ReflectionFailureDecisionDemo
```

`stdout`:

```text
missing: method not found
run: target threw IllegalArgumentException
```

`NoSuchMethodException` ở vòng lặp đầu xảy ra **trước khi invoke**. Ở vòng sau, lookup thành công; `Handler.run()` ném `IllegalArgumentException` và `Method.invoke` bọc nó trong `InvocationTargetException`. Hai thất bại cần chẩn đoán khác nhau.

**Không đảo thứ tự catch**: `catch (ReflectiveOperationException)` phải đứng **sau** các subtype handler nếu bạn muốn phân loại riêng. Nếu đặt trước, các nhánh subtype không còn khả năng được chọn và javac có thể báo catch không thể truy cập.

## 18. Checklist xử lý reflection failure trong ứng dụng

| Câu hỏi | Nên kiểm tra |
| --- | --- |
| Không tìm thấy class? | Tên binary name, package, classpath/module path, class loader |
| Không tìm thấy method? | `getMethod` hay `getDeclaredMethod`, tên, overload, `int.class`/`Integer.class`, type erasure |
| Không tìm thấy field? | `getField` hay `getDeclaredField`, field hay JavaBean property, lớp khai báo |
| Không tìm thấy constructor? | Public/declared, tham số chính xác, class có constructor phù hợp |
| Tìm được nhưng không gọi được? | Java access modifiers, receiver, named module, `exports`/`opens` |
| `Method.invoke` ném `InvocationTargetException`? | Xem `getCause()`/`getTargetException()`; lỗi ở code đích |
| `Constructor.newInstance` ném `InstantiationException`? | Class abstract/không instantiate được |
| `invoke` ném `IllegalArgumentException`? | Sai receiver, số lượng/kiểu args, primitive conversion |
| `Class.forName` gây `ExceptionInInitializerError`? | Static initializer và điều kiện runtime, không chỉ class lookup |
| Chỉ catch `ReflectiveOperationException` đã đủ? | Chưa; xác định chính sách cho unchecked exception và `Error` |
| Ghi log thế nào? | Log Throwable đầy đủ, cause/suppressed, thêm ngữ cảnh an toàn |
| Cấu hình class đến từ nguồn nào? | Xác thực, allowlist, giới hạn quyền thực thi/khởi tạo |
| Có thể tránh reflection không? | Interface, factory tường minh, `ServiceLoader`, public API |

**Không lạm dụng catch rộng rồi trả thành công giả.** Lỗi cấu hình method/constructor là dấu hiệu quan trọng của incompatibility giữa các phiên bản hoặc API contract bị phá vỡ. Cần báo thất bại với đủ ngữ cảnh, không chỉ in stack trace rồi bỏ qua kết quả.

## 19. Những nhầm lẫn phổ biến

**“`ReflectiveOperationException` là unchecked.”** Sai. Nó kế thừa `Exception` và là checked exception.

**“`catch (ReflectiveOperationException)` bắt được tất cả lỗi reflection.”** Sai. `IllegalArgumentException`, `InaccessibleObjectException`, `ExceptionInInitializerError` và `LinkageError` nằm ngoài nhánh này.

**“`ClassNotFoundException` và `NoClassDefFoundError` là cùng một lớp lỗi.”** Sai. Một cái là checked subtype của `ReflectiveOperationException`, một cái là `Error`.

**“`getDeclaredMethod` tìm cả method kế thừa.”** Sai. Nó tìm member khai báo trực tiếp trong class đang xét.

**“`getMethod` có thể tìm private method nếu biết đúng tên.”** Sai. Nó tìm public methods theo phạm vi API.

**“`getDeclaredMethod` tìm thấy private thì chắc chắn gọi được ngay.”** Sai. Tra cứu metadata và quyền invoke là hai bước.

**“`getMethod("sum", Integer.class)` tìm được `sum(int)` nhờ autoboxing.”** Sai. Reflection method lookup yêu cầu token kiểu tham số phù hợp chính xác.

**“Không có constructor không tham số thì sẽ ném `NoSuchFieldException`.”** Sai. Dùng `getDeclaredConstructor()` và gặp `NoSuchMethodException`.

**“Có một lớp `NoSuchConstructorException` chuyên biệt.”** Sai trong API reflection chuẩn dùng ở bài. Constructor lookup thất bại bằng `NoSuchMethodException`.

**“`InvocationTargetException` nghĩa là method không tồn tại.”** Sai. Method thường đã được tìm và target code thực sự ném lỗi.

**“`InvocationTargetException#getCause()` luôn là `RuntimeException`.”** Sai. Target có thể ném checked exception hoặc `Error`.

**“`Method.invoke` với sai arguments sẽ ném `NoSuchMethodException`.”** Sai. Khi `Method` đã được lấy đúng, arguments không hợp lệ thường gây `IllegalArgumentException`.

**“`InstantiationException` đồng nghĩa không tìm thấy constructor.”** Sai. Có thể tìm thấy constructor nhưng class abstract không thể tạo instance.

**“`setAccessible(true)` luôn vượt qua mọi rào cản trong Java 17.”** Sai. Named modules có strong encapsulation.

**“`getDeclaredField("name")` trả giá trị field.”** Sai. Nó trả metadata `Field`; cần dùng `get`/`getInt` với receiver phù hợp.

**“`Class.newInstance()` vẫn là cách ưu tiên trong Java mới.”** Sai. Nó deprecated; ưu tiên `getDeclaredConstructor().newInstance()`.

**“Cứ bọc lỗi reflection bằng thông điệp mới là giữ cause.”** Sai. Phải truyền đối tượng exception gốc qua constructor có cause.

**“Class.forName chỉ tra cứu metadata, không thể kích hoạt code.”** Sai với overload mặc định: class initialization có thể thực thi static initializer.

**“Một tên class nạp thành công có nghĩa plugin chắc chắn an toàn.”** Sai. Việc tạo object và chạy code có thể gây side effect; phải xác minh loại và quyền được phép.

**“Một catch chung rồi return null giúp hệ thống luôn hoạt động.”** Có thể che lỗi cấu hình quan trọng và gây `NullPointerException` muộn hơn. Cần chính sách phục hồi tường minh.

## 20. Bài tập tự kiểm tra

1. **`ReflectiveOperationException` checked hay unchecked?** Checked.
2. **API nào thường ném `ClassNotFoundException`?** `Class.forName(...)` hoặc `ClassLoader.loadClass(...)` trong điều kiện không tìm được class.
3. **Không tìm được public method tên `run` bằng `getMethod` gây gì?** `NoSuchMethodException`.
4. **`getDeclaredMethod` của subclass có tự tìm method ở superclass không?** Không.
5. **Tra cứu private method qua `getMethod` có tìm được không?** Không, nếu không có một public method khớp khác.
6. **`getDeclaredMethod` tìm private có đồng nghĩa gọi được không?** Không, còn điều kiện quyền truy cập.
7. **Không tìm thấy constructor phù hợp bằng `getConstructor` ném gì?** `NoSuchMethodException`.
8. **`getField("x")` và `getDeclaredField("x")` có cùng phạm vi không?** Không, public/inherited khác declared/direct.
9. **Method.invoke gọi target ném `IOException`: caller nhận wrapper gì?** `InvocationTargetException`, với cause là `IOException` target.
10. **Lấy Throwable gốc từ `InvocationTargetException` bằng cách nào?** `getCause()` hoặc `getTargetException()`.
11. **Một abstract class có constructor được tìm thấy thì `newInstance` luôn thành công?** Không, có thể ném `InstantiationException`.
12. **Gọi method có tham số `int`, tra cứu bằng `Integer.class` có tự match không?** Không.
13. **`Method.invoke` với target sai kiểu thường gặp checked NoSuchMethodException hay unchecked IllegalArgumentException?** Thường là unchecked `IllegalArgumentException`.
14. **`trySetAccessible()` có luôn trả true ở named module bị đóng không?** Không; có thể trả false.
15. **`setAccessible(true)` bị strong encapsulation từ chối có thể ném gì?** `InaccessibleObjectException`, unchecked.
16. **`ExceptionInInitializerError` có thuộc `ReflectiveOperationException` không?** Không; nó thuộc nhánh `Error`.
17. **Chỉ catch `ReflectiveOperationException` có bắt `ClassCastException` do cast kết quả sai không?** Không.
18. **Tại sao `Class.forName("...")` cần cân nhắc static initialization?** Overload một tham số có thể khởi tạo class và chạy initializer.
19. **Phương thức `getDeclaredMethods()` có đảm bảo thứ tự mảng cho resolver của bạn không?** Không nên giả định thứ tự.
20. **Generic factory với `Class<? extends T>` giải quyết vấn đề gì?** Tăng an toàn kiểu khi tạo subtype, nhưng vẫn phải xử lý lookup/access/invocation failures.
21. **Muốn báo lỗi nghiệp vụ từ `ReflectiveOperationException` mà vẫn chẩn đoán lỗi gốc?** Bọc với cause: `new DomainException("context", original)`.
22. **Lỗi target bên trong `InvocationTargetException` có thể mang suppressed exceptions riêng không?** Có, vì nó vẫn là đối tượng `Throwable` gốc.
23. **Nếu interface/public factory đủ dùng, reflection có phải mặc định tốt hơn không?** Không; ưu tiên API tĩnh khi phù hợp.
24. **Thông tin quan trọng nhất khi debug `NoSuchMethodException`?** Tên class, tên method, chính xác danh sách kiểu tham số và phạm vi tra cứu.
25. **Nếu plugin class tồn tại nhưng không implements interface yêu cầu thì `Class.asSubclass` có thể gây gì?** `ClassCastException`, unchecked.

## 21. Tài liệu Java 17 chính thức

- [Java SE 17 — ReflectiveOperationException](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ReflectiveOperationException.html): supertype checked của các lỗi reflection phổ biến.
- [Java SE 17 — Class](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html): `forName`, `getMethod`, `getDeclaredMethod`, `getField`, `getDeclaredConstructor`, `asSubclass`.
- [Java SE 17 — ClassNotFoundException](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassNotFoundException.html): lỗi nạp class theo tên.
- [Java SE 17 — NoSuchMethodException](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/NoSuchMethodException.html): lỗi tra cứu method/constructor.
- [Java SE 17 — NoSuchFieldException](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/NoSuchFieldException.html): lỗi tra cứu field.
- [Java SE 17 — IllegalAccessException](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/IllegalAccessException.html): quyền truy cập reflective operation.
- [Java SE 17 — InstantiationException](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/InstantiationException.html): lỗi không thể tạo đối tượng.
- [Java SE 17 — Method](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Method.html): `invoke`, `isBridge`, `isSynthetic`.
- [Java SE 17 — Field](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Field.html): `get`, `set`, access control.
- [Java SE 17 — Constructor](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Constructor.html): constructor lookup và `newInstance`.
- [Java SE 17 — InvocationTargetException](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/InvocationTargetException.html): wrapper của throwable từ target invocation.
- [Java SE 17 — AccessibleObject](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/AccessibleObject.html): `trySetAccessible`, `setAccessible`, strong encapsulation.
- [Java SE 17 — InaccessibleObjectException](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/InaccessibleObjectException.html): lỗi runtime khi module không cho mở truy cập.
- [Java Language Specification 17 — `11 Exceptions](https://docs.oracle.com/javase/specs/jls/se17/html/jls-11.html): checked/unchecked exceptions.
- [Java Language Specification 17 — `12 Execution](https://docs.oracle.com/javase/specs/jls/se17/html/jls-12.html): loading, linking, initialization và lỗi liên quan.

**Ghi nhớ:** `ReflectiveOperationException` là **checked superclass** cho nhiều lỗi tra cứu và sử dụng reflection. `ClassNotFoundException` là lỗi tìm class; `NoSuchMethodException`/`NoSuchFieldException` là lỗi tìm member; `IllegalAccessException` là lỗi quyền dùng member; `InstantiationException` là lỗi tạo object; `InvocationTargetException` bọc lỗi **do target method/constructor thực sự ném**. Hãy phân biệt lookup với invocation, dùng đúng `getMethod`/`getDeclaredMethod` và các token kiểu tham số, tôn trọng access/module của Java 17, đồng thời nhớ rằng runtime errors như `InaccessibleObjectException` hoặc `IllegalArgumentException` **không** được `catch (ReflectiveOperationException)` tự động bao phủ.
