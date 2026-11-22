# 3.4 Tạo đối tượng bằng `Constructor.newInstance` và xử lý constructor không tham số

Trong Java, toán tử `new` tạo đối tượng khi biết kiểu ở thời điểm biên dịch. Khi kiểu chỉ được xác định ở **thời điểm chạy** (đọc tên lớp từ cấu hình, khám phá plugin, bộ chuyển đổi dữ liệu, test framework, dependency injection), Reflection có thể tìm một constructor và gọi nó bằng `java.lang.reflect.Constructor<T>.newInstance(...)`.

Điểm cốt lõi: **có một đối tượng `Class<T>` không bảo đảm lớp có constructor không tham số**, và tìm thấy constructor không đồng nghĩa với được phép gọi nó. Cần phân biệt chính xác bước tìm constructor, kiểm tra quyền truy cập, chuẩn bị đối số, thực thi, và xử lý ngoại lệ phát sinh bên trong constructor.

Sau bài học, bạn có thể:

- Phân biệt `Class.getConstructor(...)` với `Class.getDeclaredConstructor(...)` và chọn đúng khi cần constructor không tham số.
- Tạo đối tượng bằng `Constructor.newInstance()` với constructor public hoặc constructor có tham số; hiểu vì sao việc tìm constructor có thể thất bại.
- Hiểu **default constructor được compiler cấp** khác với constructor không tham số được khai báo tường minh.
- Xử lý chính xác `NoSuchMethodException`, `IllegalAccessException`, `InstantiationException`, `InvocationTargetException`, lỗi đối số và hạn chế module.
- Nhận ra trường hợp interface, abstract class, enum, record, inner class và constructor private; quyết định khi nào nên dùng factory thay vì Reflection.

## 1. Từ `Class<T>` đến một instance mới

Quy trình Reflection chuẩn:

```java
Class<Widget> type = Widget.class;                   // 1. Đối tượng mô tả kiểu
Constructor<Widget> ctor = type.getConstructor();    // 2. Tìm public constructor không tham số
Widget widget = ctor.newInstance();                  // 3. Thực thi constructor để tạo instance
```

Đây là **đoạn minh họa**: cần có lớp `Widget` với public no-arg constructor và xử lý checked exceptions để chạy độc lập. Tham số truyền cho `getConstructor(...)` là danh sách `Class<?>` biểu diễn **kiểu tham số khai báo**; gọi không có đối số nghĩa là tìm chữ ký `()`, không phải lấy constructor đầu tiên có trong lớp.

Khi `newInstance()` thành công, JVM cấp phát đối tượng và chạy quá trình khởi tạo bình thường: khởi tạo lớp nếu cần, khởi tạo superclass, instance initializers và body constructor theo quy tắc Java. Các invariant được áp dụng như lúc gọi `new Widget()`. Reflection không phải cơ chế để bỏ qua constructor; nếu constructor ném ngoại lệ, quá trình tạo đối tượng không thành công.

`Class<T>` là mô tả kiểu; `Constructor<T>` mô tả một constructor cụ thể; `newInstance(Object... initargs)` **gọi** constructor đó. `Constructor<T>` giữ kiểu kết quả `T` để giảm cast và lỗi gán kiểu trong code:

```java
Class<Widget> type = Widget.class;
Constructor<Widget> ctor = type.getConstructor();
Widget value = ctor.newInstance();
```

Nếu chỉ có `Class<?>`, giá trị kết quả thường được dùng như `Object` hoặc được ràng buộc qua một hợp đồng kiểu rõ ràng. Tránh ép kiểu mù từ tên class do người dùng nhập.

## 2. Hai API tìm constructor: public và declared

| API | Constructor được tìm | Khi không tìm thấy | Ý nghĩa thực tế |
| --- | --- | --- | --- |
| `type.getConstructor()` | Public constructor có đúng **0 tham số** | `NoSuchMethodException` | Muốn gọi API khởi tạo công khai |
| `type.getConstructor(String.class, int.class)` | Public constructor đúng `(String, int)` | `NoSuchMethodException` | Muốn gọi một overload public cụ thể |
| `type.getDeclaredConstructor()` | Constructor 0 tham số **khai báo trong lớp**, bất kể public/protected/package-private/private | `NoSuchMethodException` | Cần kiểm tra hoặc dùng constructor không public |
| `type.getDeclaredConstructor(int.class)` | Constructor được khai báo có đúng một tham số `int` | `NoSuchMethodException` | Dùng chữ ký chính xác |
| `type.getConstructors()` | Các public constructors của lớp | Trả mảng, có thể rỗng | Khảo sát trước khi chọn |
| `type.getDeclaredConstructors()` | Tất cả constructors được khai báo, kể cả không public | Trả mảng, có thể rỗng | Khảo sát các lựa chọn và modifier |

Một constructor **không được kế thừa** như instance method. Vì vậy `Child.class.getConstructor()` không trả về một constructor được khai báo trong `Parent`; nó chỉ có thể trả constructor của chính `Child`. Dù source không ghi constructor, compiler có thể đã tạo một default constructor cho `Child`, nên vẫn cần xem trường hợp cụ thể.

Các phương thức lấy mảng constructors **không bảo đảm thứ tự**, không nên dùng `getDeclaredConstructors()[0]` để đoán no-arg hoặc constructor “mặc định”. Hãy chỉ rõ các kiểu tham số rồi yêu cầu chữ ký chính xác.

### 2.1. Constructor đã tìm thấy vẫn có thể không gọi được

`getDeclaredConstructor()` có thể trả về một private constructor. Phương thức đó chỉ **khám phá metadata**; quyền gọi còn được kiểm tra tại `ctor.newInstance()`. Trong trường hợp bị hạn chế quyền truy cập, có thể phát sinh `IllegalAccessException`. `setAccessible(true)` hoặc `trySetAccessible()` có thể cho phép truy cập sâu trong các điều kiện nhất định, nhưng Java Platform Module System có thể ngăn việc này. Không coi `getDeclaredConstructor()` là công cụ tự động vượt qua mọi hạn chế.

Đọc modifier bằng `ctor.getModifiers()` cùng `Modifier.isPublic(...)` nếu cần kiểm tra chính sách. Tuy nhiên, constructor public của một lớp không public vẫn có thể không truy cập được từ caller ở package/module khác; phải xét cả quyền của lớp bao quanh và quan hệ module.

## 3. Constructor không tham số và default constructor là hai khái niệm khác nhau

**No-arg constructor** (constructor không tham số) là constructor có chữ ký `()`, dù viết tường minh hay do compiler sinh. **Default constructor** trong JLS là constructor không tham số do compiler cung cấp cho lớp bình thường khi **không có bất kỳ khai báo constructor nào**.

```java
class Automatic {
    // Không khai báo constructor: compiler cung cấp Automatic().
}

class Explicit {
    Explicit() {
        System.out.println("created");
    }
}

class WithParameter {
    WithParameter(String name) {
    }
    // Không còn default constructor tự sinh.
}
```

- `Automatic.class.getDeclaredConstructor()` tìm được constructor do compiler sinh, với quyền truy cập tương ứng với lớp `Automatic` (ở ví dụ là package-private).
- `Explicit.class.getDeclaredConstructor()` tìm được constructor được khai báo tường minh.
- `WithParameter.class.getDeclaredConstructor()` ném `NoSuchMethodException`: **chỉ cần một constructor được khai báo**, compiler không cấp thêm default no-arg.
- Cả ba lớp trên đều không có public constructor nên `getConstructor()` không tìm thấy chúng (constructor của `Automatic` không public). Đừng nhầm “có no-arg” với “có public no-arg”.

Nếu một lớp `public class PublicModel { }` không khai báo constructor nào, compiler cung cấp public default constructor tương ứng; `PublicModel.class.getConstructor()` sẽ tìm được. Một lớp có constructor tham số và muốn giữ khả năng khởi tạo không tham số cần tự khai báo thêm:

```java
class Account {
    private final String owner;

    Account() {
        this("guest");
    }

    Account(String owner) {
        this.owner = owner;
    }
}
```

Đây là constructor overload tường minh, `Account()` ủy quyền cho `Account(String)` để giữ invariant. Nó có package-private access; `Account.class.getDeclaredConstructor()` tìm được, còn `Account.class.getConstructor()` không tìm được. Muốn dùng như một public extension point, phải thiết kế mức truy cập và hợp đồng của lớp cho phù hợp.

Không được tự giả định constructor không tham số sẽ đặt mọi field vào trạng thái hợp lệ cho nghiệp vụ. Constructor không tham số có thể thiết lập các giá trị mặc định cần thiết; một đối tượng có được tạo hay không phải được xác định theo hợp đồng lớp, không theo sở thích của Reflection framework.

## 4. Chương trình Java 17+ hoàn chỉnh: public constructor, overload và ngoại lệ

Tạo file **`ConstructorNewInstanceDemo.java`** với nội dung sau. Các lớp lồng nhau được khai báo `public static` để công khai constructor và không cần instance của lớp bao ngoài.

```java
import java.lang.reflect.Constructor;
import java.lang.reflect.InvocationTargetException;

public class ConstructorNewInstanceDemo {
    public static class PublicBox {
        private final String value;

        public PublicBox() {
            this("empty");
        }

        public PublicBox(String value) {
            this.value = value;
        }

        @Override
        public String toString() {
            return "PublicBox[" + value + "]";
        }
    }

    public static class NeedsValue {
        private final int value;

        public NeedsValue(int value) {
            this.value = value;
        }

        @Override
        public String toString() {
            return "NeedsValue[" + value + "]";
        }
    }

    public abstract static class AbstractJob {
        public AbstractJob() {}
    }

    public static class Exploding {
        public Exploding() {
            throw new IllegalStateException("invalid state");
        }
    }

    public static void main(String[] args)
            throws ReflectiveOperationException {
        Constructor<PublicBox> noArg =
                PublicBox.class.getConstructor();
        System.out.println(noArg.newInstance());

        Constructor<PublicBox> byName =
                PublicBox.class.getConstructor(String.class);
        System.out.println(byName.newInstance("ready"));

        try {
            NeedsValue.class.getConstructor();
        } catch (NoSuchMethodException e) {
            System.out.println("NeedsValue: missing no-arg");
        }

        Constructor<NeedsValue> byNumber =
                NeedsValue.class.getConstructor(int.class);
        System.out.println(byNumber.newInstance(7));

        try {
            AbstractJob.class.getConstructor().newInstance();
        } catch (InstantiationException e) {
            System.out.println("AbstractJob: abstract");
        }

        try {
            Exploding.class.getConstructor().newInstance();
        } catch (InvocationTargetException e) {
            Throwable cause = e.getCause();
            System.out.println(
                    "Exploding: " + cause.getClass().getSimpleName()
                            + ": " + cause.getMessage());
        }
    }
}
```

Biên dịch/chạy bằng JDK 17 hoặc mới hơn:

```bash
javac --release 17 ConstructorNewInstanceDemo.java
java ConstructorNewInstanceDemo
```

Stdout chính xác:

```text
PublicBox[empty]
PublicBox[ready]
NeedsValue: missing no-arg
NeedsValue[7]
AbstractJob: abstract
Exploding: IllegalStateException: invalid state
```

Giải thích:

1. `PublicBox` có **public no-arg constructor**, gọi `this("empty")`; kết quả `PublicBox[empty]`.
2. `getConstructor(String.class)` chọn overload nhận `String`, tạo `PublicBox[ready]`.
3. `NeedsValue` chỉ khai báo constructor `(int)`, không được compiler tự sinh no-arg: việc **tìm** `()` thất bại bằng `NoSuchMethodException`. Để tạo đối tượng hợp lệ, code dùng chữ ký `(int)` và cung cấp giá trị `7`.
4. `AbstractJob` có public constructor `()` trong metadata nhưng vẫn là abstract class: **tìm được không đồng nghĩa với tạo được**, `newInstance` ném `InstantiationException`.
5. `Exploding` có constructor hợp lệ nhưng chính body ném `IllegalStateException`; Reflection bọc ngoại lệ gốc vào `InvocationTargetException`. Lấy nguyên nhân bằng `getCause()`, không coi đó là lỗi thiếu constructor.

Chương trình cố tình chỉ bắt riêng các lỗi **được minh họa**; `main` khai báo `throws ReflectiveOperationException` cho các lỗi phản chiếu khác. Trong ứng dụng thực tế, cần xử lý tại ranh giới framework/API sao cho không làm mất stack trace và nguyên nhân.

## 5. Tạo đối tượng bằng constructor không public

Nếu framework có quyền phù hợp và buộc phải gọi constructor được khai báo `private`, quá trình gồm: tìm bằng `getDeclaredConstructor()`, kiểm tra khả năng truy cập, xin quyền qua `trySetAccessible()` khi thiết kế cho phép, rồi mới `newInstance()`.

Ví dụ có thể chạy độc lập với JDK 17 **trên classpath thông thường (unnamed module)**. Tạo file **`AccessDemo.java`**:

```java
import java.lang.reflect.Constructor;

class Secret {
    private Secret() {}

    String message() {
        return "created";
    }
}

public class AccessDemo {
    public static void main(String[] args)
            throws ReflectiveOperationException {
        try {
            Secret.class.getConstructor();
        } catch (NoSuchMethodException e) {
            System.out.println("public no-arg: absent");
        }

        Constructor<Secret> ctor =
                Secret.class.getDeclaredConstructor();
        System.out.println("accessible before: "
                + ctor.canAccess(null));

        try {
            ctor.newInstance();
        } catch (IllegalAccessException e) {
            System.out.println("without override: denied");
        }

        boolean enabled = ctor.trySetAccessible();
        System.out.println("override allowed: " + enabled);
        if (enabled) {
            System.out.println(ctor.newInstance().message());
        }
    }
}
```

Biên dịch/chạy:

```bash
javac --release 17 AccessDemo.java
java AccessDemo
```

Stdout trong môi trường nêu trên:

```text
public no-arg: absent
accessible before: false
without override: denied
override allowed: true
created
```

`Secret` là **top-level class riêng**, không phải nested class cùng nest với `AccessDemo`. Vì vậy `AccessDemo` không có quyền gọi private constructor nếu chưa mở quyền. Điều này quan trọng: kể từ Java 11, hai lớp **nestmates** (ví dụ outer class và nested class của nó) có thể truy cập private members của nhau; viết ví dụ private nested class rồi tuyên bố Reflection chắc chắn thất bại sẽ dễ sai.

`canAccess(null)` hỏi khả năng truy cập hiện tại đối với constructor (constructor không cần receiver object). `trySetAccessible()` trả `true` nếu suppression của kiểm tra truy cập được bật thành công, hoặc `false` nếu không thể mở quyền theo quy tắc module; nó vẫn có thể gặp `SecurityException` dưới cơ chế bảo mật liên quan. `setAccessible(true)` ném `InaccessibleObjectException` khi module không cho phép mở quyền theo cách yêu cầu.

**Ranh giới module:** Nếu class nằm trong named module khác, `exports` thường chỉ cho phép truy cập API public hợp lệ; truy cập sâu private/package-private có thể cần `opens` package cho module thực hiện Reflection. Ví dụ khai báo module (minh họa, chỉ áp dụng khi bạn kiểm soát module chứa domain class):

```java
module com.example.domain {
    opens com.example.domain.model to com.example.framework;
}
```

Không nên tự thêm `--add-opens` hoặc mở toàn bộ package chỉ để “làm code chạy” trong production. Ưu tiên thiết kế public factory, public constructor rõ ràng hoặc API mở rộng được hỗ trợ. Khi không được cấp quyền, báo lỗi có ngữ cảnh thay vì cố bypass Java module system.

## 6. Bảng ngoại lệ: lỗi xảy ra ở bước nào?

| Ngoại lệ / lỗi | Bước thường gặp | Nguyên nhân đặc trưng | Hướng xử lý |
| --- | --- | --- | --- |
| `NoSuchMethodException` | `getConstructor` / `getDeclaredConstructor` | Không có constructor đúng chữ ký; ví dụ thiếu `()`, hoặc tra cứu sai `int.class` và `Integer.class` | Kiểm tra chữ ký; chọn overload hợp lệ hoặc factory; không tự sinh no-arg |
| `IllegalAccessException` | `ctor.newInstance` | Constructor hoặc declaring class không truy cập được từ caller | Tôn trọng visibility; dùng public API, hoặc mở quyền nếu được phép |
| `InstantiationException` | `ctor.newInstance` | Ví dụ declaring class là abstract class | Không cố tạo abstract class; dùng implementation cụ thể |
| `InvocationTargetException` | `ctor.newInstance` | Code bên trong constructor ném exception/error | Lấy `getCause()`, lưu nguyên nhân và truyền lỗi đúng lớp trách nhiệm |
| `IllegalArgumentException` | `ctor.newInstance` | Sai số lượng/kiểu đối số, null không hợp lệ cho primitive, hoặc cố tạo enum bằng Reflection | Chọn đúng signature, kiểm tra giá trị và dạng argument |
| `ExceptionInInitializerError` | Khởi tạo lớp khi gọi constructor | Static initialization của declaring class thất bại | Kiểm tra static initializer và root cause; không nhầm với lỗi constructor |
| `InaccessibleObjectException` | `setAccessible(true)` | Không thể suppress access check vì module chưa mở package | Dùng API public hoặc cấu hình module chính thức |
| `SecurityException` | Tra cứu / thay đổi accessibility trong môi trường có security checks | Security policy chặn quyền tương ứng | Không thử vượt quyền; trả lỗi phù hợp |

Không phải ngoại lệ nào cũng là subclass của `ReflectiveOperationException`: `IllegalArgumentException`, `InaccessibleObjectException`, `ExceptionInInitializerError`, `SecurityException` cần được xem riêng tùy API và ngữ cảnh. Trong khi đó `NoSuchMethodException`, `InstantiationException`, `IllegalAccessException`, `InvocationTargetException` đều là checked reflection exceptions thuộc họ `ReflectiveOperationException`.

**Cách đọc đúng `InvocationTargetException`:** Đây là wrapper báo “phương thức/constructor được gọi đã ném lỗi”. `e.getCause()` là exception/error thật xảy ra bên trong. `getMessage()` của wrapper có thể không mô tả nguyên nhân. Đừng chỉ log `InvocationTargetException` rồi bỏ `getCause()`.

Ví dụ đoạn xử lý dùng trong một method có khai báo `throws ReflectiveOperationException`:

```java
try {
    return ctor.newInstance();
} catch (InvocationTargetException e) {
    Throwable cause = e.getCause();
    if (cause instanceof RuntimeException re) {
        throw re;
    }
    if (cause instanceof Error error) {
        throw error;
    }
    throw new IllegalStateException("Constructor failed", cause);
}
```

Đây chỉ là **một nhánh xử lý trong method** có biến `ctor` đã tồn tại, không phải chương trình độc lập. Ứng dụng có thể muốn bọc mọi lỗi vào một exception riêng của domain/framework; nếu vậy, vẫn nên giữ `cause` để không mất bằng chứng gốc.

## 7. Không có no-arg constructor: nên xử lý thế nào?

Với lớp yêu cầu dữ liệu bắt buộc để bảo vệ invariant, việc thiếu no-arg có thể hoàn toàn là thiết kế đúng:

```java
class ConnectionOptions {
    private final String host;
    private final int port;

    public ConnectionOptions(String host, int port) {
        if (host == null || host.isBlank()) {
            throw new IllegalArgumentException("host is required");
        }
        if (port <= 0 || port > 65535) {
            throw new IllegalArgumentException("invalid port");
        }
        this.host = host;
        this.port = port;
    }
}
```

`ConnectionOptions.class.getConstructor()` sẽ ném `NoSuchMethodException`. Đừng chữa bằng việc “tạo object rỗng” nếu loại đối tượng đó không có trạng thái rỗng hợp lệ. Cách tạo đúng là:

```java
Constructor<ConnectionOptions> ctor =
        ConnectionOptions.class.getConstructor(String.class, int.class);
ConnectionOptions options =
        ctor.newInstance("localhost", 8080);
```

Đây là đoạn minh họa trong method có thể xử lý checked exceptions; `ConnectionOptions` và `ctor` cần nằm trong cùng package hoặc môi trường có quyền phù hợp. Vì `ConnectionOptions` ở ví dụ không public, code ở package khác có thể không gọi constructor dù constructor thành viên được khai báo `public`. Nếu muốn API công khai giữa các package, khai báo cả lớp là `public` trong file phù hợp.

Quy trình lựa chọn khi gặp `NoSuchMethodException`:

1. Xác nhận chữ ký thật sự bằng `getDeclaredConstructors()` trong bước chẩn đoán; đừng dựa vào thứ tự của mảng.
2. Nếu có constructor tham số thích hợp, chọn bằng các `Class<?>` chính xác và chuẩn bị đối số hợp lệ.
3. Nếu class cung cấp static factory (`of(...)`, `create(...)`), builder hoặc factory interface, ưu tiên hợp đồng đó khi được thiết kế cho use case.
4. Nếu framework bắt buộc public no-arg để thực hiện hợp đồng, yêu cầu loại plugin/model cung cấp constructor thích hợp hoặc đăng ký factory tùy biến. Không lặng lẽ thêm no-arg constructor làm mất invariant.
5. Nếu không có đường khởi tạo hợp lệ, trả một lỗi cấu hình có tên lớp, chữ ký yêu cầu và cách khắc phục; không tạo đối tượng bằng thủ thuật bỏ qua initialization.

Dù có thể thiết kế fallback, **không tự chọn constructor “ít tham số nhất”** và chèn `null`/`0` tùy ý. Cách đó phá hợp đồng domain, có thể khiến lỗi xuất hiện xa nơi tạo đối tượng.

## 8. Truyền đối số đúng kiểu khi gọi `newInstance(Object...)`

Tra cứu constructor là **so khớp chữ ký chính xác**; gọi constructor sau đó mới áp dụng các conversion được cho phép. Ví dụ:

```java
record Purchase(int quantity, String item) {}

Constructor<Purchase> ctor =
        Purchase.class.getDeclaredConstructor(int.class, String.class);
Purchase purchase =
        ctor.newInstance(Integer.valueOf(3), "book");
```

Đoạn này cần import `java.lang.reflect.Constructor` và xử lý exceptions. `getDeclaredConstructor(int.class, String.class)` đúng vì khai báo nhận primitive `int`; khi gọi `newInstance`, `Integer.valueOf(3)` được **unbox** thành `int` theo quy tắc của Reflection. Nhưng `getDeclaredConstructor(Integer.class, String.class)` sẽ thất bại do không có constructor với chữ ký khai báo như vậy.

Những lưu ý quan trọng:

- **Thứ tự và số lượng tham số:** `(String, int)` khác `(int, String)`. Nếu `newInstance` nhận thiếu hoặc thừa tham số, nó có thể ném `IllegalArgumentException`.
- **Primitive conversion:** `newInstance` có thể unbox wrapper và áp dụng primitive widening hợp lệ; không tự thực hiện narrowing tùy tiện. Truyền `null` vào tham số primitive không hợp lệ.
- **Reference conversion:** đối tượng cần tương thích với declared parameter type. `getConstructor` không tự tìm “overload gần nhất” khi bạn cung cấp kiểu parameter khác.
- **Generic erasure:** nếu khai báo constructor nhận `List<String>`, khi tìm bằng Reflection sử dụng `List.class` cho raw parameter type, không có literal `List<String>.class`.
- **Varargs của chính API Reflection:** `Constructor.newInstance(Object... initargs)` nhận danh sách `Object`; cần phân biệt với mảng thực sự là **một tham số** của constructor đích.

Ví dụ cuối cùng rất dễ nhầm:

```java
class Names {
    public Names(String... items) {
        System.out.println(items.length);
    }
}
```

Chữ ký Reflection là `(String[])`, không phải `(String, String)`. Cách gọi đúng (trong method xử lý exceptions):

```java
Constructor<Names> ctor = Names.class.getDeclaredConstructor(String[].class);
ctor.newInstance((Object) new String[] {"A", "B"}); // stdout: 2
```

Cast sang `Object` ở đây làm mảng `String[]` trở thành **một argument** trong varargs `Object...` của API Reflection. Nếu bỏ cast và viết `ctor.newInstance(new String[] {"A","B"})`, compiler có thể áp dụng varargs theo cách làm mảng bị xem là nhiều argument, dẫn đến lời gọi không khớp chữ ký thực tế. Vì vậy trong chương trình chung nhận constructor có tham số mảng, hãy đóng gói argument một cách tường minh.

**No-arg:** gọi `ctor.newInstance()` là rõ ràng nhất. Đừng cố “sửa” no-arg bằng một `null` tùy tiện: `ctor.newInstance((Object) null)` có nghĩa cung cấp **một argument null**, không phải zero arguments.

## 9. Các loại lớp đặc biệt: constructor không tham số có thể không có hoặc không dùng được

| Kiểu `Class<?>` | Điều cần lưu ý | Hướng xử lý |
| --- | --- | --- |
| Interface | Không có constructor, không được `new` trực tiếp | Tìm implementation cụ thể hoặc một factory/proxy có chủ đích |
| Abstract class | Có thể có constructor để subclass gọi, nhưng không instantiate trực tiếp | Chọn subclass cụ thể |
| Primitive, `void`, array | Không có constructor kiểu class để tra cứu theo API này | Mảng dùng `java.lang.reflect.Array.newInstance` khi cần; primitive/void không có instance theo cách đó |
| Enum | Không cho phép tạo thêm enum constant bằng `Constructor.newInstance` | Dùng các hằng có sẵn, `getEnumConstants()`, `Enum.valueOf(...)` |
| Record | Mặc định có canonical constructor theo record components; không đương nhiên có no-arg | Dùng canonical constructor hoặc khai báo no-arg hợp lệ có `this(...)` |
| Non-static inner class | Constructor runtime thường có tham số enclosing instance ở đầu, kể cả source viết `()` | Cung cấp instance của outer class và tìm đúng chữ ký |
| Static nested class | Không có tham số outer instance ngầm | Xử lý như class bình thường |
| Lớp private/package-private | Có thể tìm constructor nhưng không gọi được từ caller khác | Tuân theo accessibility/module hoặc công khai factory |

### 9.1. Record và yêu cầu khởi tạo có dữ liệu

```java
record Endpoint(String host, int port) {}
```

`Endpoint.class.getDeclaredConstructor()` ném `NoSuchMethodException` vì canonical constructor có hai tham số. Cách gọi hợp lệ:

```java
Constructor<Endpoint> ctor =
        Endpoint.class.getDeclaredConstructor(String.class, int.class);
Endpoint endpoint = ctor.newInstance("localhost", 8080);
```

Nếu nghiệp vụ có trạng thái mặc định thực sự hợp lệ, record có thể khai báo constructor bổ sung không tham số và **bắt buộc ủy quyền đến constructor khác bằng `this(...)`**:

```java
record DefaultEndpoint(String host, int port) {
    DefaultEndpoint() {
        this("localhost", 8080);
    }
}
```

`DefaultEndpoint.class.getDeclaredConstructor()` nay tìm được; nhưng đây là quyết định thiết kế có chủ đích, không phải constructor do compiler tự sinh cho mọi record.

### 9.2. Non-static inner class và tham số outer ẩn

```java
class Outer {
    class Inner {
        Inner() {}
    }
}
```

Trong source, `Inner()` nhìn như không tham số, nhưng non-static inner class gắn với một enclosing `Outer` instance. Khi tra cứu bằng core Reflection, enclosing instance xuất hiện làm tham số đầu tiên. Ví dụ minh họa trong cùng package, với `ReflectiveOperationException` được xử lý:

```java
Outer outer = new Outer();
Constructor<Outer.Inner> ctor =
        Outer.Inner.class.getDeclaredConstructor(Outer.class);
Outer.Inner inner = ctor.newInstance(outer);
```

`Outer.Inner.class.getDeclaredConstructor()` không tìm ra chữ ký thực tế `()`. Nếu công cụ Reflection gặp class lồng bên trong, kiểm tra `getEnclosingClass()`, `Modifier.isStatic(...)` và chữ ký constructor thay vì mặc định xem đây là lỗi người viết quên no-arg.

## 10. Xây utility tạo đối tượng có public no-arg một cách rõ ràng

Đoạn sau là **method tái sử dụng**, đặt bên trong class tiện ích Java 17+ và import `java.lang.reflect.Constructor`, `java.lang.reflect.InvocationTargetException`, `java.lang.reflect.Modifier`. Đây không phải file độc lập; mục tiêu là làm rõ đường lỗi:

```java
static <T> T createWithPublicNoArg(Class<T> type) {
    if (type == null) {
        throw new IllegalArgumentException("type is null");
    }
    if (type.isInterface()
            || java.lang.reflect.Modifier.isAbstract(type.getModifiers())
            || type.isPrimitive()
            || type == void.class
            || type.isArray()
            || type.isEnum()) {
        throw new IllegalArgumentException(
                "Cannot instantiate: " + type.getTypeName());
    }

    try {
        Constructor<T> ctor = type.getConstructor();
        return ctor.newInstance();
    } catch (NoSuchMethodException e) {
        throw new IllegalArgumentException(
                "Missing public no-arg constructor: "
                        + type.getTypeName(), e);
    } catch (InvocationTargetException e) {
        Throwable cause = e.getCause();
        if (cause instanceof RuntimeException runtime) {
            throw runtime;
        }
        if (cause instanceof Error error) {
            throw error;
        }
        throw new IllegalStateException(
                "Constructor failed: " + type.getTypeName(), cause);
    } catch (InstantiationException | IllegalAccessException e) {
        throw new IllegalStateException(
                "Constructor is not invocable: "
                        + type.getTypeName(), e);
    }
}
```

Ý đồ của utility là **chỉ dùng public no-arg**. Nó không tự mở constructor private và không suy diễn cách tạo đối tượng cho type thiếu no-arg. Việc kiểm tra trước giúp tạo thông điệp lỗi dễ hiểu; vẫn phải bắt checked exceptions vì trạng thái và khả năng truy cập thực tế quyết định ở bước gọi.

Phép kiểm tra `Modifier.isAbstract` cần thiết bên cạnh `isInterface()` để nhận diện abstract class. Các lớp public có public constructor nhưng bản thân lớp không truy cập được từ caller vẫn có thể gây `IllegalAccessException`. Trường hợp lỗi static initializer hoặc lỗi runtime độc lập với checked exceptions phải được xử lý ở ranh giới cao hơn nếu API yêu cầu.

Trong ứng dụng có nhiều kiểu plugin, một lựa chọn tốt hơn là đăng ký `Supplier<? extends Service>`, factory tương ứng hoặc dependency injection. Khi đó việc tạo đối tượng có thể cần tham số và dependency, tránh buộc mọi implementation phải cung cấp no-arg.

## 11. Vì sao không nên dùng `Class.newInstance()` nữa?

API cũ:

```java
Widget instance = Widget.class.newInstance();
```

đã bị **deprecated từ Java 9**. Nó chỉ theo lối khởi tạo không tham số và đặc biệt có thể truyền thẳng exception do constructor ném ra, kể cả checked exception, làm sai lệch khả năng kiểm tra ngoại lệ ở compile time.

Cách viết được khuyến nghị khi cần Reflection:

```java
Constructor<Widget> ctor =
        Widget.class.getDeclaredConstructor();
Widget instance = ctor.newInstance();
```

Khác biệt có ý nghĩa:

- Nếu không có constructor `()`, `getDeclaredConstructor()` ném `NoSuchMethodException` rõ ràng.
- Nếu constructor chạy và ném exception, `Constructor.newInstance()` bọc nó trong `InvocationTargetException` để caller xử lý theo cơ chế thống nhất.
- Việc tìm thấy constructor không public **không** tự miễn kiểm tra quyền truy cập. Nếu hợp đồng chỉ cho phép constructor public, thay bằng `getConstructor()`.

Đừng đổi `type.newInstance()` sang `type.getDeclaredConstructor().newInstance()` chỉ bằng tìm/thay rồi nuốt tất cả exceptions. Cần quyết định explicit public access, quyền với module, các trường hợp class không khởi tạo được, và cách preserve cause.

## 12. Các lỗi thực tế thường gặp

1. **“Có `Class` nên chắc chắn có `()`.”** Sai: class có constructor tham số sẽ không tự có default no-arg. Dùng `getConstructor()`/`getDeclaredConstructor()` và phản ứng với `NoSuchMethodException`.
2. **“Constructor public đồng nghĩa với lớp public.”** Sai: member public có thể nằm trong declaring class không được caller truy cập; Reflection vẫn kiểm tra quyền của declaring class.
3. **“Không thấy public constructor thì lớp không có constructor.”** Sai: thử `getDeclaredConstructor()` khi nhiệm vụ được phép khảo sát private/package-private constructor.
4. **“`getDeclaredConstructor()` bảo đảm gọi được constructor private.”** Sai: việc tìm metadata tách khỏi quyền gọi; `trySetAccessible` có thể thất bại, module system có thể chặn truy cập sâu.
5. **“`NoSuchMethodException` nghĩa là constructor đã chạy và lỗi.”** Sai: nó phát sinh ở **bước tìm chữ ký**. `InvocationTargetException` mới cho biết code được gọi đã ném lỗi.
6. **“`InvocationTargetException` là nguyên nhân gốc.”** Sai: dùng `getCause()`, và không biến một lỗi domain thành thông báo “Reflection failed” khó chẩn đoán.
7. **“Chỉ cần `catch (Exception ignored)` rồi trả null.”** Sai: làm mất nguyên nhân, dẫn đến `NullPointerException` xa gốc lỗi. Trả lỗi có kiểu và cause hoặc xử lý tại tầng cao hơn.
8. **“Java tự tìm constructor overload tương thích khi `getConstructor(Integer.class)`.”** Sai: tra cứu chữ ký chính xác; unboxing/widening được xét ở giai đoạn invoke.
9. **“Gọi `newInstance(null)` là không truyền tham số.”** Đây là biểu thức varargs dễ mơ hồ; với không tham số hãy dùng `newInstance()`. Nếu định truyền một `null` reference, diễn đạt rõ `newInstance((Object) null)`.
10. **“Dùng `Unsafe.allocateInstance` thay constructor để vượt lỗi no-arg.”** Cách đó có thể bỏ qua constructor và invariant, không phải cách sửa an toàn cho lớp domain hay framework thông thường.
11. **“Enum, record, inner class đều có no-arg như class POJO.”** Enum không được tạo thêm constant qua `Constructor.newInstance`; record thường cần canonical constructor; non-static inner class cần enclosing instance.
12. **“Constructor không tham số luôn vô hại.”** Constructor và class initialization có thể có side effects, ném lỗi, cấp tài nguyên hoặc gây tác động không mong muốn; không chạy class do input không tin cậy chỉ vì Reflection cho phép.

## 13. Gợi ý kiểm thử khi phát triển framework sử dụng Reflection

Nên có test case riêng cho: public no-arg thành công; class có constructor tham số nhưng thiếu no-arg; private no-arg với module mở/chưa mở; abstract class; constructor ném checked hoặc unchecked exception; constructor có tham số primitive; non-static inner class; record và enum. Những case này phân biệt **lỗi lookup, access, instantiation, target logic**, là điều mà một happy-path test thường không phát hiện.

Ở tầng nhận class name từ cấu hình, kiểm soát tập kiểu được phép tạo; không cho phép đầu vào tùy ý kích hoạt initialization/constructor của một class bất kỳ. Có thể yêu cầu kiểu triển khai interface dùng chung:

```java
if (!Service.class.isAssignableFrom(candidate)) {
    throw new IllegalArgumentException("Not a Service type");
}
Class<? extends Service> implementation =
        candidate.asSubclass(Service.class);
Service service = createWithPublicNoArg(implementation);
```

Đoạn này minh họa khi đã có interface `Service`, một biến `candidate` kiểu `Class<?>` và method utility từ mục 10. `asSubclass` cung cấp kiểm tra runtime và ràng buộc kiểu; nó không tự chứng nhận class đó đáng tin hoặc constructor không gây side effects. Khi thiết kế hệ thống plugin, cần thêm chính sách đăng ký/cho phép các implementation cụ thể.

## 14. Câu hỏi tự kiểm tra

**1.** `class A { A(int x) {} }`. Tại sao `A.class.getDeclaredConstructor()` thất bại? Thêm constructor nào nếu muốn tạo `A` không cần đối số?

**Đáp án:** vì class đã khai báo một constructor `(int)`, compiler không sinh default `()`. Thêm `A() { this(0); }` **nếu `0` là trạng thái hợp lệ**, hoặc cung cấp argument phù hợp cho constructor hiện có.

**2.** Tại sao `getDeclaredConstructor()` tìm được private constructor nhưng `newInstance()` vẫn có thể ném `IllegalAccessException`?

**Đáp án:** metadata lookup và access check khi thực thi là hai bước khác nhau. Caller có thể không được phép gọi private constructor; việc mở quyền chịu ràng buộc của language access và modules.

**3.** `NeedsValue.class.getConstructor(int.class)` khác `NeedsValue.class.getConstructor(Integer.class)` thế nào nếu khai báo `public NeedsValue(int value)`?

**Đáp án:** chữ ký đầu tiên khớp, chữ ký thứ hai ném `NoSuchMethodException`. Khi đã tìm được constructor nhận `int`, `newInstance(Integer.valueOf(7))` có thể unbox khi gọi.

**4.** Constructor body `throw new IllegalStateException("broken")`. Caller quan sát ngoại lệ nào từ `ctor.newInstance()`?

**Đáp án:** `InvocationTargetException`; `e.getCause()` là `IllegalStateException("broken")`.

**5.** Vì sao abstract class có public no-arg constructor vẫn không tạo được qua Reflection?

**Đáp án:** constructor tồn tại để phục vụ subclass, nhưng abstract class không thể có instance trực tiếp; `Constructor.newInstance()` ném `InstantiationException`.

**6.** Với `record User(String name) {}`, gọi `User.class.getDeclaredConstructor()` có được không? Cách khởi tạo hợp lệ là gì?

**Đáp án:** không, nó không tự có no-arg; tìm canonical constructor bằng `getDeclaredConstructor(String.class)` rồi truyền `name`, hoặc thiết kế một constructor no-arg tường minh ủy quyền `this(...)` nếu có giá trị mặc định hợp lệ.

**7.** Trong Reflection, constructor source `Inner()` của non-static `Outer.Inner` thường được tìm bằng chữ ký nào?

**Đáp án:** `Outer.Inner.class.getDeclaredConstructor(Outer.class)`, vì cần enclosing `Outer` instance được truyền làm đối số đầu tiên khi khởi tạo.

**8.** Hệ thống plugin yêu cầu no-arg, nhưng một plugin cần dependency bắt buộc. Thêm no-arg cho mọi class hay thay đổi cơ chế khởi tạo?

**Đáp án:** nếu no-arg không bảo đảm invariant, nên đăng ký factory/`Supplier` hoặc dùng DI để cung cấp dependency. Chỉ yêu cầu public no-arg khi đó là một hợp đồng rõ ràng và hợp lệ đối với mọi implementation.

## Tài liệu chuẩn để đối chiếu

- Java SE 21 API `Constructor<T>`: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/reflect/Constructor.html — cách gọi `newInstance`, conversion tham số, ngoại lệ và quyền truy cập.
- Java SE 21 API `Class<T>`: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Class.html — `getConstructor`, `getDeclaredConstructor`, các trường hợp không có constructor, `Class.newInstance()` deprecated.
- Java SE 21 API `AccessibleObject`: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/reflect/AccessibleObject.html — `canAccess`, `trySetAccessible`, `setAccessible` trong Java module system.
- Java Language Specification 21, §8.8 Constructors và §8.10 Record Classes: https://docs.oracle.com/javase/specs/jls/se21/html/jls-8.html — default constructor, tham số của inner class, canonical constructor của record.