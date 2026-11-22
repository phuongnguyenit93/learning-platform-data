# Class.forName, ClassLoader.loadClass và khả năng tìm theo tên của hidden class

## 1. Trọng tâm cần hiểu

Từ Java 15, Java hỗ trợ **hidden class** thông qua `MethodHandles.Lookup.defineHiddenClass(...)`. Hidden class là một class thực sự được JVM định nghĩa, có thể có phương thức, được khởi tạo, thực thi và được biểu diễn bởi một đối tượng `Class<?>`. Tuy nhiên, **hidden class không có *binary name* hợp lệ để các cơ chế nạp class theo tên tìm lại**.

Hệ quả trực tiếp:

- **`Class.forName(...)` không thể tìm hidden class theo tên.**
- **`ClassLoader.loadClass(...)` cũng không thể tìm hidden class theo tên.**
- `Class.getName()` vẫn trả về một chuỗi tên cho hidden class, nhưng tên đó chứa dấu `/` và **không phải binary name** có thể dùng cho hai API trên.
- Nếu code đã có `Class<?>` của hidden class hoặc `MethodHandles.Lookup` trả về lúc định nghĩa, code vẫn có thể thao tác với class ấy. "Hidden" không có nghĩa là class không tồn tại hay luôn không thể gọi được.

Đây là hành vi được quy định trong API Java hiện hành, áp dụng trên Java 17+ và các bản Java mới hơn, không dựa vào kỹ thuật cũ hoặc API legacy.

## 2. Class thường và hidden class khác nhau ở đâu?

Một class thông thường có **binary name**, chẳng hạn `com.example.OrderService` hoặc `com.example.Outer$Nested`. Tên này được dùng cho việc tra cứu class bằng những cơ chế quen thuộc:

```java
Class<?> a = Class.forName("java.lang.String");
Class<?> b = ClassLoader.getSystemClassLoader()
        .loadClass("java.lang.String");
```

Cả hai phép gọi đều có thể trả về `String.class` trong ngữ cảnh nạp class thông thường.

Với hidden class, JVM cho phép định nghĩa class từ bytecode mà **không đăng ký nó để tìm lại qua binary name**. Dù hidden class có class loader liên kết với nó, class loader không thể tìm lại hidden class bằng cơ chế thông thường chỉ dựa vào chuỗi tên.

| Đặc điểm | Class thông thường (named class) | Hidden class |
| --- | --- | --- |
| Có binary name hợp lệ | Có | Không |
| `Class.getName()` | Thường trả binary name | Trả dạng `N + "/" + suffix` |
| `Class.forName(name)` | Có thể tìm được nếu loader thích hợp | Không tìm được hidden class |
| `ClassLoader.loadClass(name)` | Có thể tìm được nếu loader thích hợp | Không tìm được hidden class |
| `Class.isHidden()` | `false` | `true` |
| Có đối tượng `Class<?>` | Có | Có |
| Có thể gọi thành viên qua handle/reflection phù hợp | Có | Có, nếu có quyền và tham chiếu |
| `Class.describeConstable()` | Thường có mô tả danh nghĩa khi phù hợp | Trả `Optional.empty()` |

**Lưu ý:** Dấu `/` nằm trong chuỗi tên của hidden class không biến nó thành một đường dẫn tài nguyên hay tên JVM class-file thông thường. Chuỗi này có phần hậu tố do JVM gắn vào và không nên được lưu làm định danh ổn định.

## 3. Chính xác `Class.forName` hoạt động thế nào?

`Class.forName(String className)` dùng tên của class để yêu cầu JVM tìm/nạp class trong ngữ cảnh class loader liên quan tới nơi gọi. Với class thường:

```java
Class<?> type = Class.forName("java.util.ArrayList");
```

Kết quả là `ArrayList.class` trong môi trường nạp class thông thường. Nếu không tìm được tên, `ClassNotFoundException` được ném ra. Phiên bản một tham số này cũng có thể dẫn tới **khởi tạo class** nếu class chưa được khởi tạo.

Quá tải có chỉ định loader và quyền khởi tạo:

```java
Class<?> type = Class.forName(
        "java.util.ArrayList",
        false,
        Thread.currentThread().getContextClassLoader()
);
```

Tham số `false` cho biết không yêu cầu khởi tạo class ở lần gọi này. Tuy nhiên, nó **không thay đổi quy tắc về hidden class**: dù dùng `Class.forName(name)` hay `Class.forName(name, false, loader)`, bạn vẫn không thể tìm hidden class bằng tên.

Ngoài ra, `Class.forName(Module module, String name)` là một overload khác, tìm class theo binary name trong module được chỉ định và trả `null` khi không tìm được; nó cũng không cho phép vượt qua đặc tính "hidden".

## 4. Chính xác `ClassLoader.loadClass` hoạt động thế nào?

`ClassLoader.loadClass(String name)` là API nạp class theo tên trong hệ thống class loader. Nó thường kiểm tra class đã nạp và cơ chế ủy quyền tìm kiếm trước khi tự định nghĩa class. Với class thông thường, kết quả có thể là `Class<?>` tương ứng:

```java
ClassLoader loader = Thread.currentThread().getContextClassLoader();
Class<?> type = loader.loadClass("java.util.ArrayList");
```

`loadClass` thông thường **không tự khởi tạo class**; đây là điểm khác biệt với `Class.forName(String)`. Việc tìm class còn phụ thuộc class loader thực sự được sử dụng, module và các quy tắc truy cập liên quan.

Với hidden class, **có `ClassLoader` không đồng nghĩa với có khả năng tìm theo tên**. Ngay cả khi:

```java
hidden.getClassLoader() == NamedType.class.getClassLoader()
```

trả về `true`, lời gọi:

```java
loader.loadClass(hidden.getName());
```

vẫn không tìm được hidden class qua cơ chế nạp theo tên. Sự khác biệt nằm ở *cách hidden class được JVM định nghĩa và nhận diện*, không phải đơn giản do thiếu class loader.

## 5. Vì sao `Class.getName()` không sử dụng lại được?

Giả sử một class thường có binary name `example.Worker`. Khi định nghĩa một hidden class từ bytecode có tên nguồn đó, JVM có thể tạo tên hiển thị theo mẫu:

```text
example.Worker/0x0000...  (hình thức minh họa)
```

Ở đây, `example.Worker` là phần tên bắt nguồn từ class file, còn đoạn sau `/` là hậu tố gắn vào hidden class. **Hậu tố cụ thể không được bảo đảm giống nhau giữa lần chạy/JDK**; không viết unit test so sánh toàn bộ chuỗi tên với một hậu tố cố định.

Trong Java, *binary name* của một class thông thường không có dạng `N/suffix`. Vì vậy:

```java
String hiddenName = hidden.getName();
Class<?> again = Class.forName(hiddenName); // ClassNotFoundException
```

Đây là kết quả đúng theo hợp đồng API, kể cả khi `hidden` là một `Class<?>` đang được tham chiếu và class có thể đang hoạt động.

`hidden.getCanonicalName()` cũng trả `null` vì hidden class không có canonical name theo ngôn ngữ Java. `hidden.describeConstable()` trả một `Optional` rỗng vì class đó không thể biểu diễn bằng descriptor danh nghĩa `ClassDesc`.

## 6. Tạo hidden class và giữ lại tham chiếu bằng `Lookup`

API hiện hành để tạo hidden class là:

```java
MethodHandles.Lookup hiddenLookup = MethodHandles.lookup()
        .defineHiddenClass(
                classBytes,
                true,
                MethodHandles.Lookup.ClassOption.NESTMATE
        );

Class<?> hidden = hiddenLookup.lookupClass();
```

Các thành phần:

- `classBytes`: bytecode class-file hợp lệ, trong cùng runtime package với lookup có quyền thích hợp.
- `true`: yêu cầu JVM khởi tạo hidden class ngay trong quá trình định nghĩa.
- `NESTMATE`: thêm hidden class vào cùng nest với lookup class, khi cần cơ chế quyền truy cập nestmate; có thể bỏ option này nếu tình huống không cần.
- `hiddenLookup`: đối tượng `Lookup` trả về mà lookup class chính là hidden class mới được định nghĩa.
- `hiddenLookup.lookupClass()`: cho đối tượng `Class<?>` để dùng về sau mà **không cần tra cứu lại theo tên**.

`defineHiddenClass` được giới thiệu từ Java 15 và cần lookup có quyền thích hợp. Nó không phải cách để người dùng gõ bất kỳ class name nào rồi nhận về một hidden class đã tồn tại. Ứng dụng hoặc framework định nghĩa hidden class cần tự giữ tham chiếu `Lookup`, `Class<?>`, instance hoặc method handle mà nó muốn tiếp tục sử dụng.

## 7. Ví dụ Java 17+ chạy được: so sánh cách tìm class thường và hidden class

Ví dụ sử dụng một **nested class thông thường** làm khuôn bytecode. Sau khi biên dịch, ta đọc file `.class` của khuôn, dùng `defineHiddenClass` tạo *một class khác* từ các byte ấy. Như vậy có cả class thường và hidden class để quan sát sự khác biệt.

Tạo file **`HiddenClassNameLookupDemo.java`**:

```java
import java.io.InputStream;
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;

public class HiddenClassNameLookupDemo {
    static class Template {
        static String message() {
            return "hello hidden";
        }
    }

    public static void main(String[] args) throws Throwable {
        Class<?> named = Template.class;
        String resource = "/" + named.getName().replace('.', '/') + ".class";
        byte[] bytes;

        try (InputStream input = named.getResourceAsStream(resource)) {
            if (input == null) {
                throw new IllegalStateException("Missing class bytes: " + resource);
            }
            bytes = input.readAllBytes();
        }

        MethodHandles.Lookup hiddenLookup = MethodHandles.lookup()
                .defineHiddenClass(
                        bytes,
                        true,
                        MethodHandles.Lookup.ClassOption.NESTMATE
                );
        Class<?> hidden = hiddenLookup.lookupClass();
        ClassLoader loader = HiddenClassNameLookupDemo.class.getClassLoader();

        System.out.println("namedHidden=" + named.isHidden());
        System.out.println("hidden=" + hidden.isHidden());

        System.out.println("namedViaForName=" +
                (Class.forName(named.getName()) == named));
        System.out.println("namedViaLoader=" +
                (loader.loadClass(named.getName()) == named));
        System.out.println("hiddenNameHasSlash=" +
                hidden.getName().contains("/"));

        try {
            Class.forName(hidden.getName());
            System.out.println("hiddenViaForName=true");
        } catch (ClassNotFoundException ex) {
            System.out.println("hiddenViaForName=false");
        }

        try {
            loader.loadClass(hidden.getName());
            System.out.println("hiddenViaLoader=true");
        } catch (ClassNotFoundException ex) {
            System.out.println("hiddenViaLoader=false");
        }

        System.out.println("sameDefiningLoader=" +
                (hidden.getClassLoader() == named.getClassLoader()));
        System.out.println("hiddenDescribeConstable=" +
                hidden.describeConstable().isPresent());

        MethodHandle handle = hiddenLookup.findStatic(
                hidden, "message", MethodType.methodType(String.class)
        );
        System.out.println("callHidden=" + (String) handle.invokeExact());
    }
}
```

Dùng JDK **17 trở lên**, biên dịch thông thường để tạo cả file class lồng bên trong, rồi chạy:

```bash
javac HiddenClassNameLookupDemo.java
java HiddenClassNameLookupDemo
```

**Output chính xác** (đã kiểm chứng bằng cách biên dịch theo Java 17 và chạy trên JDK 24):

```text
namedHidden=false
hidden=true
namedViaForName=true
namedViaLoader=true
hiddenNameHasSlash=true
hiddenViaForName=false
hiddenViaLoader=false
sameDefiningLoader=true
hiddenDescribeConstable=false
callHidden=hello hidden
```

### Phân tích kết quả

1. `namedHidden=false`: `Template.class` là nested class được biên dịch và nạp thông thường. `hidden=true`: class mới được tạo bởi `defineHiddenClass` có tính chất hidden.
2. `namedViaForName=true` và `namedViaLoader=true`: hai API tìm được **class `Template` thông thường** theo binary name của nó.
3. `hiddenNameHasSlash=true`: tên trả từ `Class.getName()` cho hidden class chứa dấu `/`, thể hiện không phải binary name hợp lệ.
4. `hiddenViaForName=false` và `hiddenViaLoader=false`: cả hai cách tìm theo tên đều ném `ClassNotFoundException`; `try/catch` chuyển điều đó thành output `false`.
5. `sameDefiningLoader=true`: class thường và hidden class có **cùng defining class loader**, nhưng điều đó không làm hidden class có thể tìm theo tên.
6. `hiddenDescribeConstable=false`: `Class.describeConstable()` không thể tạo nominal class descriptor cho hidden class.
7. `callHidden=hello hidden`: mặc dù tìm theo tên thất bại, ta vẫn có thể gọi phương thức của hidden class qua `MethodHandle` lấy từ `hiddenLookup`.

`String resource` tìm file `.class` của nested `Template` ở classpath. Ví dụ này được thiết kế để chạy sau khi gọi **`javac` rồi `java`**, vì khi đó file `HiddenClassNameLookupDemo$Template.class` tồn tại trong thư mục output. Đừng xóa file class con trước khi chạy.

Tham số `throws Throwable` ở `main` dùng cho chương trình minh họa vì `MethodHandle.invokeExact` có thể ném `Throwable`; trong ứng dụng thật cần chiến lược xử lý ngoại lệ phù hợp.

## 8. Nếu lấy phần tên trước dấu `/` để thử thì sao?

Có thể có trường hợp **phần tên trước dấu `/`** khớp với binary name của một class thường (như `Template` trong ví dụ). Khi gọi:

```java
String prefix = hidden.getName().split("/")[0];
Class<?> found = Class.forName(prefix);
```

`found` có thể chính là **class thường**, nếu loader nhìn thấy class có binary name đó. Điều này **không chứng minh tìm được hidden class**: class thường và hidden class là hai class khác nhau, dù chúng được tạo từ cùng bytecode nguồn.

Trong ví dụ trên, `Class.forName(named.getName()) == named` là `true`; nhưng `Class.forName(hidden.getName())` thất bại. Không sử dụng việc cắt hậu tố tên hidden như một cách định danh hoặc tái tạo nó.

## 9. "Hidden" không đồng nghĩa với "không thể phản chiếu" hoặc "an toàn tuyệt đối"

Hidden class được thiết kế để hạn chế **phụ thuộc danh nghĩa và khả năng tìm theo tên** từ các class khác. Nó không tự động trở thành một vùng bảo mật kín:

- Nếu giữ `Class<?>`, bạn vẫn có thể hỏi `isHidden()`, `getDeclaredMethods()`, `getClassLoader()`, v.v. theo quyền và quy tắc phản chiếu áp dụng.
- Nếu có instance của hidden class, `instance.getClass()` vẫn trả về đúng `Class<?>` của hidden class ấy.
- Nếu có `MethodHandles.Lookup` đủ quyền, có thể dùng `findStatic`, `findVirtual` hoặc các handle phù hợp để gọi thành viên.
- Quy tắc quyền truy cập Java và các hạn chế module vẫn có hiệu lực; hidden class không cấp tự động quyền truy cập vào mọi thứ.

Vì vậy, khi một framework tạo hidden class để hiện thực tính năng nội bộ, việc thiết kế **cơ chế giữ tham chiếu** cho các đối tượng cần sử dụng là quan trọng hơn việc cố tìm class qua `Class.forName`.

## 10. Ứng dụng thực tế và giới hạn

Một số thư viện hoặc runtime dùng hidden class trong tình huống sinh code động, hỗ trợ implementation cho lambda hoặc cơ chế triển khai tạm thời. Lợi ích thường liên quan đến việc class sinh ra không trở thành một tên công khai để code khác phụ thuộc vào, và tùy cấu hình vòng đời có thể được thu hồi độc lập với class loader.

Tuy nhiên, không nên suy luận rằng **mọi** class được sinh động đều là hidden class hoặc rằng một tên lạ có dấu `/` là đủ để khẳng định hidden class. Dùng `Class.isHidden()` để kiểm tra chính xác. Với nhu cầu load plugin theo tên, reflection theo cấu hình, hoặc classpath scanning dựa vào binary name, nên thiết kế quanh **class thường có thể tìm bằng tên** hoặc đăng ký trực tiếp `Class<?>`/handle trong framework tương ứng.

Một hệ thống cấu hình chỉ lưu chuỗi `hidden.getName()` rồi kỳ vọng ở lần chạy khác gọi `Class.forName(...)` để tái tạo hidden class sẽ không hoạt động: tên đó không phải khóa định danh có thể load theo tên và thường có hậu tố do JVM sinh ra.

## 11. Lỗi thường gặp

1. **Thấy `hidden.getName()` có giá trị thì nghĩ `forName` phải tìm được.** Sai: `getName()` của hidden class không phải binary name, nên hai API nạp theo tên không tìm được.
2. **Thấy `hidden.getClassLoader()` khác `null` thì cho rằng `loadClass` tìm lại được.** Sai: hidden class có class loader, nhưng không được đăng ký vào cơ chế tra cứu theo binary name.
3. **Truyền phần trước `/` rồi kết luận đã tìm ra hidden class.** Nếu thành công, kết quả có thể là class thường cùng tên phần trước; cần so sánh `Class<?>` để phân biệt.
4. **Thử biến thể `Class.forName(name, false, loader)` để vượt hạn chế.** Cờ `initialize=false` chỉ tác động việc khởi tạo, không giúp tìm hidden class.
5. **In trọn hậu tố tên vào test và so sánh với một chuỗi cố định.** Hậu tố hidden class không ổn định giữa các lần chạy/JDK. Kiểm tra `isHidden()` và hành vi thay vì giá trị suffix.
6. **Cho rằng không tìm bằng tên thì không gọi được.** Nếu giữ `Lookup`, `Class<?>`, method handle hoặc instance phù hợp, class vẫn có thể được dùng.
7. **Dùng hidden class như rào chắn bảo mật.** Nó không thay cho kiểm soát quyền truy cập; đặc tính chính là không thể tham chiếu danh nghĩa qua tên.
8. **Cho rằng `ClassLoader.loadClass` và `Class.forName` luôn có cùng hành vi khởi tạo.** `Class.forName(String)` có thể khởi tạo class; `ClassLoader.loadClass(String)` thông thường chỉ nạp class, chưa tự khởi tạo.

## 12. Checklist ghi nhớ

- Class được định nghĩa bởi `Lookup.defineHiddenClass`? Kiểm tra `Class.isHidden()`.
- Đang muốn **tìm lại theo chuỗi tên**? `Class.forName`/`ClassLoader.loadClass` không hỗ trợ hidden class.
- Đang có `Lookup` trả về từ lúc định nghĩa? Dùng `lookup.lookupClass()` và các `MethodHandle` phù hợp.
- Đang có đối tượng của hidden class? Dùng `object.getClass()` để nhận `Class<?>`.
- Đang viết test? Chú ý hậu tố tên hidden không ổn định; kiểm tra boolean và hành vi thay vì tên nguyên văn.
- Đang thiết kế registry/plugin cần nạp class theo tên? Cần cơ chế lưu `Class<?>`/handle hoặc sử dụng class thông thường có binary name.

**Kết luận kỹ thuật:** hidden class vẫn là class chạy được trong JVM, nhưng không được định danh bằng binary name để hệ thống tra cứu class theo tên tìm thấy. Sự khác biệt này được thể hiện trực tiếp qua `isHidden()`, `getName()`, `Class.forName`, `ClassLoader.loadClass` và `Lookup`.

## Tài liệu tham khảo chính thức, còn hiệu lực

- [Oracle Java SE 26 — `Class`, mục Hidden Classes](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/Class.html): khẳng định hidden class không có binary name và không thể tìm bằng `Class.forName` hoặc `ClassLoader.loadClass`.
- [Oracle Java SE 26 — `MethodHandles.Lookup.defineHiddenClass`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/invoke/MethodHandles.Lookup.html#defineHiddenClass(byte%5B%5D,boolean,java.lang.invoke.MethodHandles.Lookup.ClassOption...)): chữ ký, yêu cầu lookup, cách nhận `Lookup` của hidden class và quyền truy cập.
- [OpenJDK JEP 371 — Hidden Classes](https://openjdk.org/jeps/371): thiết kế hidden class được đưa vào Java 15.
- [Oracle Java SE 26 — `ClassLoader.loadClass`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/ClassLoader.html#loadClass(java.lang.String)): cách nạp class thường theo tên và ngoại lệ.

Các quy tắc trên vẫn là hợp đồng Java hiện hành. Ví dụ dùng API chính thức từ Java 15 và biên dịch được theo mức nguồn Java 17 trở lên.