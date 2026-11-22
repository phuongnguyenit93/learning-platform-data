# ClassCastException khi tên lớp nguồn và đích giống nhau

Thông báo **`ClassCastException`: “class A cannot be cast to class A”** nhìn có vẻ mâu thuẫn: tên kiểu nguồn và kiểu đích giống nhau nhưng phép ép kiểu vẫn thất bại. Trong JVM, định danh của một **class/interface** không chỉ là tên mà là **cặp (binary name, defining class loader)**. Hai bộ nạp lớp có thể độc lập định nghĩa cùng tên `com.example.Plugin` và tạo thành **hai kiểu JVM khác nhau**, dù sử dụng một file `.class` có bytecode giống nhau đến từng byte.

Bài này tập trung vào cơ chế định danh kiểu, cách tái hiện bằng Java 17, phân biệt defining/initiating loader, chẩn đoán stack trace và cách thiết kế ranh giới giữa host, plugin hay application server.

## 1. Vì sao tên giống nhau chưa chắc cùng class?

~~~text
                  com.example.Plugin
                    /           \
                   v             v
             Loader A         Loader B
                   |             |
              Plugin(A)       Plugin(B)
                   \             /
                KHÔNG CÙNG KIỂU
~~~

Giả sử `classA` và `classB` là `Class<?>` do hai loader **thực sự định nghĩa**:

~~~java
classA.getName().equals(classB.getName())  // true
classA == classB                           // false
~~~

Đây là **fragment minh họa**, chưa phải một chương trình độc lập. Các quy tắc nền tảng:

- `Class.getName()` trả tên nhị phân; không đủ chứng minh hai kiểu có cùng identity.
- `Class.getClassLoader()` trả **defining loader** của class. Với nhiều class nền tảng do bootstrap loader định nghĩa, API dùng `null` để biểu diễn loader.
- `Object.getClass()` trả định nghĩa class runtime của object; cast dựa vào kiểu đó và quan hệ inheritance/implements.
- `instanceof`, `Class.isInstance(...)`, `Class.cast(...)` và bytecode `checkcast` **không chỉ so sánh chuỗi tên**.
- Một loader không được định nghĩa hai class riêng có cùng binary name trong namespace của chính nó; nỗ lực định nghĩa trùng không hợp lệ có thể gây `LinkageError`. Lỗi trong bài thường đến từ **hai defining loader** khác nhau.
- Hai loader child khác nhau vẫn có thể trả lại **cùng một `Class<?>`** nếu cả hai ủy quyền cho parent đã định nghĩa class đó. Phải kiểm tra defining loader thật, không chỉ so sánh hai object loader ban đầu.

Với kiểu mảng có phần tử là class tham chiếu, identity của kiểu mảng chịu ảnh hưởng identity kiểu phần tử. Đừng coi `Plugin[]` từ hai định nghĩa `Plugin` khác nhau là một kiểu mảng tương thích.

## 2. Vì sao JVM ném ClassCastException?

Một object tạo từ `Message(A)`, trong khi code đích yêu cầu kiểu `Message(B)`:

~~~text
Loader A                  Loader B
   |                         |
   v                         v
Message(A)              Message(B)
   |                         ^
   v                         |
object ------ cast ----------+
                 |
          ClassCastException
~~~

JVM kiểm tra liệu object có phù hợp với kiểu đích dựa trên quan hệ class/interface đã liên kết hay không. Hai định nghĩa cùng tên từ hai loader độc lập **không tự có quan hệ kiểu**, kể cả khi bytecode hoàn toàn giống nhau.

Ví dụ thực tế: một plugin implements `com.acme.api.Task` do loader của plugin định nghĩa, nhưng host yêu cầu `Task` do loader host định nghĩa. Một object của plugin có thể không cast được sang interface của host. Reflection chỉ giúp tìm/gọi method theo quyền truy cập phù hợp; nó không biến hai định nghĩa kiểu thành cùng một.

## 3. Chương trình Java 17: cùng một bytecode, hai class loader và lỗi cast

Tạo **hai file** trong cùng một thư mục. Chương trình chính sử dụng hai `URLClassLoader` cùng URL trỏ vào thư mục có `Payload.class`, nhưng parent của mỗi loader là `null` nên lớp ứng dụng `Payload` không được ủy quyền cho application loader. Các lớp nền tảng như `java.lang.Object` vẫn có thể do bootstrap loader phục vụ.

**Tệp `Payload.java`:**

~~~java
public class Payload {
    public String value() {
        return "same bytecode";
    }
}
~~~

**Tệp `LoaderCollisionDemo.java`:**

~~~java
import java.net.URL;
import java.net.URLClassLoader;
import java.nio.file.Path;

public class LoaderCollisionDemo {
    public static void main(String[] args) throws Exception {
        URL directory = Path.of(".")
                .toAbsolutePath()
                .normalize()
                .toUri()
                .toURL();

        try (URLClassLoader loaderA =
                     new URLClassLoader(new URL[] { directory }, null);
             URLClassLoader loaderB =
                     new URLClassLoader(new URL[] { directory }, null)) {

            Class<?> classA = Class.forName("Payload", true, loaderA);
            Class<?> classB = Class.forName("Payload", true, loaderB);

            Object objectA = classA.getDeclaredConstructor().newInstance();

            System.out.println("Names equal: "
                    + classA.getName().equals(classB.getName()));
            System.out.println("Same Class: " + (classA == classB));
            System.out.println("Loader A defines A: "
                    + (classA.getClassLoader() == loaderA));
            System.out.println("Loader B defines B: "
                    + (classB.getClassLoader() == loaderB));
            System.out.println("A accepts object: "
                    + classA.isInstance(objectA));
            System.out.println("B accepts object: "
                    + classB.isInstance(objectA));

            try {
                classB.cast(objectA);
                System.out.println("Unexpected cast");
            } catch (ClassCastException e) {
                System.out.println("Result: ClassCastException");
            }
        }
    }
}
~~~

Biên dịch/chạy bằng **JDK 17 hoặc mới hơn**, tại thư mục chứa các file:

~~~bash
javac --release 17 Payload.java LoaderCollisionDemo.java
java LoaderCollisionDemo
~~~

**Stdout chính xác:**

~~~text
Names equal: true
Same Class: false
Loader A defines A: true
Loader B defines B: true
A accepts object: true
B accepts object: false
Result: ClassCastException
~~~

Phân tích:

1. Chỉ có **một** `Payload.class` được tạo bởi `javac`, nhưng hai loader độc lập định nghĩa hai bản `Payload` khi nhận yêu cầu.
2. `Class.forName("Payload", true, loaderX)` yêu cầu nạp/khởi tạo class qua loader được truyền. Mỗi bản `Payload` ở đây thuộc defining loader tương ứng.
3. `getName()` cùng là `Payload`, nhưng `classA == classB` bằng `false`; hai object `Class<?>` không có cùng identity.
4. `objectA` do constructor `Payload(A)` tạo, vì vậy `classA.isInstance(objectA)` bằng `true`, còn `classB.isInstance(objectA)` bằng `false`.
5. `classB.cast(objectA)` ném `ClassCastException`. Ví dụ bắt exception để in chuỗi cố định; thông báo JVM gốc có thể chứa thông tin loader/module phụ thuộc môi trường.
6. `try-with-resources` gọi `URLClassLoader.close()`; điều này đóng tài nguyên loader, **không buộc JVM unload class ngay**.

Ví dụ dùng default package và parent `null` để dễ thấy hai namespace độc lập, **không phải cấu hình chuẩn cho mọi plugin**.

### Nếu cast trực tiếp từ code ứng dụng?

Fragment sau (không nằm trong chương trình độc lập trên):

~~~java
Payload p = (Payload) objectA;
~~~

cũng có thể thất bại: `Payload` trong source của ứng dụng được liên kết tới kiểu của application loader, còn `objectA` thuộc `Payload(A)`. Nếu application loader đã nạp `Payload` thì có thể tồn tại **ba** định nghĩa class cùng tên trong process.

## 4. Đọc thông báo “A cannot be cast to A”

Một thông báo trên JVM hiện đại có thể có dạng:

~~~text
class com.acme.Plugin cannot be cast to class com.acme.Plugin
(com.acme.Plugin is in unnamed module of loader LoaderA ...;
 com.acme.Plugin is in unnamed module of loader LoaderB ...)
~~~

Đây là **ví dụ minh họa cấu trúc message**, không phải stdout cố định. Tên loader, địa chỉ, module và format có thể thay đổi theo runtime.

| Thành phần | Cách suy luận |
| --- | --- |
| Hai tên class giống nhau | Binary name giống, chưa chứng minh cùng identity. |
| Hai loader khác nhau | Kiểm tra hai defining loader thực sự của source và target. |
| `unnamed module` | Hai loader có thể có unnamed module riêng, không tự chia sẻ class. |
| Tên module rõ ràng | Giúp định vị layer/module, không thay thế kiểm tra Class identity. |
| Stack trace tại cast | Cho biết nơi object đi vào boundary và bên nhận đang yêu cầu kiểu nào. |

Cùng JAR URL, cùng package, cùng tên module, cùng bytecode hay cùng source file **không đủ chứng minh cùng class**. Ngược lại, nhiều loader con cũng có thể cùng nhận lại class do parent định nghĩa.

## 5. Defining loader và initiating loader khác nhau

- **Defining loader:** loader thực sự định nghĩa class từ ClassFile; nó tham gia identity của kiểu. `Class.getClassLoader()` cho biết loader này.
- **Initiating loader:** loader khởi xướng yêu cầu nạp theo tên; có thể ủy quyền cho parent và nhận class do parent định nghĩa.

~~~text
child.loadClass("com.acme.api.Task")
               |
               v
       child hỏi parent
               |
               v
      parent định nghĩa Task
               |
               v
   child trả lại chính Class<?> của Task
~~~

Trong sơ đồ, child là initiating loader nhưng parent là defining loader. Nếu hai child đều ủy quyền cho cùng parent đã định nghĩa `Task`, **chỉ có một kiểu Task**. Nếu parent không thấy `Task` và mỗi child tự định nghĩa, chúng có hai identity khác nhau.

Một custom loader có thể dùng child-first để cô lập dependency, nhưng cần giữ API contract dùng chung theo cơ chế parent/shared loader. Chỉ so `loaderA.getParent() == loaderB.getParent()` **không đủ** để kết luận hai kiểu được chia sẻ.

`Thread.currentThread().getContextClassLoader()` (TCCL) được một số framework và `ServiceLoader` sử dụng để tìm provider. Thay TCCL **không thay đổi identity** của Class đã được định nghĩa. Nó chỉ tác động đến đường tìm lớp nếu API/framework thật sự dùng context loader.

## 6. Những nơi thường gặp lỗi

### 6.1. Plugin đóng gói bản sao API interface của host

~~~text
Host class loader:
  com/acme/api/Processor.class      ← contract gốc

Plugin class loader:
  com/acme/api/Processor.class      ← bản copy API riêng
  com/acme/plugin/ProcessorImpl.class
~~~

`ProcessorImpl` implements `Processor` từ plugin loader. Host cast object thành `Processor` từ host loader và gặp bất tương thích. **Cách sửa:** Host hoặc parent/shared loader định nghĩa đúng **một** `Processor`; plugin chỉ định nghĩa implementation và dùng đúng interface chung.

### 6.2. Application server hot redeploy

Container có thể tạo class loader mới khi deploy lại. Thread, callback, listener, cache hoặc singleton cũ giữ object tạo bởi loader cũ, sau đó truyền vào code mới:

~~~text
Deploy cũ → LoaderOld → com.app.User → object cũ
Deploy mới → LoaderNew → com.app.User → kiểu mới
                         |
               cast object cũ sang kiểu mới
                         |
                 ClassCastException
~~~

Cần dọn lifecycle của thread/cache/listener/callback khi undeploy, không giữ object thuộc class loader cũ qua ranh giới deployment. Đóng loader không bảo đảm object cũ tự mất ngay.

### 6.3. Trùng thư viện qua dependency/shading

Host và plugin có thể cùng đóng gói một `api.jar` hoặc cùng một model class được ship trong nhiều JAR. Có hai JAR trên đĩa **chưa chắc gây lỗi**; lỗi đến khi hai defining loader thực sự tạo hai class khác nhau và code truyền object qua boundary. Shading/relocation có thể phù hợp cho dependency nội bộ nhưng **không nên tạo hai bản API contract** mà host/plugin phải dùng chung.

### 6.4. Reflection, SPI và proxy

`Class.forName(..., loader)`, `ServiceLoader`, proxy factory và discovery framework chọn loader theo cấu hình/TCCL. Provider có thể triển khai interface do loader khác với consumer định nghĩa; việc phản chiếu thành công chưa bảo đảm cast sang interface consumer. Kiểm tra loader thật dùng để nạp **contract**, provider và proxy.

## 7. Chẩn đoán bằng Class<?> thật

Fragment sau giả sử `value` là object không null và `targetType` là `Class<?>` đích của bên nhận:

~~~java
Class<?> actualType = value.getClass();

System.out.println("Actual name: " + actualType.getName());
System.out.println("Target name: " + targetType.getName());
System.out.println("Same Class: " + (actualType == targetType));

System.out.println("Actual loader: " + actualType.getClassLoader());
System.out.println("Target loader: " + targetType.getClassLoader());

System.out.println("Actual module: " + actualType.getModule());
System.out.println("Target module: " + targetType.getModule());

System.out.println("Compatible: " + targetType.isInstance(value));
System.out.println("Assignable: "
        + targetType.isAssignableFrom(actualType));
~~~

**Không kết luận chỉ bằng `actualType == targetType`**: object có thể là subclass hoặc implementation của interface đích, nên hai Class khác nhau mà cast vẫn hợp lệ. `isInstance(value)` phản ánh tương thích với kiểu đích; `isAssignableFrom(actualType)` cũng có ích để kiểm tra quan hệ type.

Có thể định dạng ID loader tạm trong log:

~~~java
ClassLoader loader = actualType.getClassLoader();
String id = loader == null ? "bootstrap"
        : loader.getClass().getName() + "@"
                + Integer.toHexString(System.identityHashCode(loader));
System.out.println(id);
~~~

Đoạn này là fragment phụ thuộc biến `actualType`. `identityHashCode` tiện cho log nhưng có thể trùng; so sánh tham chiếu loader bằng `==` để kết luận cùng object loader.

Thử xem nguồn class từ `ProtectionDomain` và `CodeSource`:

~~~java
var domain = actualType.getProtectionDomain();
var source = domain == null ? null : domain.getCodeSource();
System.out.println(source == null
        ? "(unknown)"
        : source.getLocation());
~~~

Không phải class nào cũng có `CodeSource` hữu ích: bootstrap class, class sinh bytecode trong memory hoặc loader đặc biệt có thể không cung cấp. **Cùng CodeSource chưa chắc cùng identity**.

### Trình tự xử lý sự cố

1. Giữ đầy đủ stack trace và lấy đúng `Class<?>` của object nguồn lẫn kiểu đích.
2. In `getName()`, `getClassLoader()`, `getModule()`, `isInstance(...)` và so sánh `==`.
3. Tìm nơi object tạo ra: factory, constructor, reflection, proxy, deserialize, plugin callback.
4. Kiểm tra API JAR bị duplicate, chiến lược parent-first/child-first, dependency tree và module layer.
5. Nếu lỗi chỉ xảy ra sau redeploy, kiểm tra cache, thread, callback còn giữ loader/object cũ.
6. Đưa **API contract về một defining loader chung** hoặc chuyển dữ liệu qua boundary trung lập.

## 8. Giải pháp và phản ví dụ

| Tình huống | Giải pháp |
| --- | --- |
| Host không cast được plugin sang interface | API interface do parent/shared loader định nghĩa; plugin không định nghĩa lại. |
| Hai plugin trao đổi model nội bộ | Chia sẻ DTO/interface contract hoặc serialize thành định dạng trung lập. |
| Hai phiên bản thư viện phải cùng tồn tại | Giữ implementation trong loader riêng, chỉ chia sẻ contract cần thiết. |
| Lỗi sau redeploy | Hủy cache/thread/listener/callback giữ object/loader của deployment cũ. |
| Framework nạp provider bằng loader sai | Cấu hình discovery/TCCL/loader nhất quán với contract dùng chung. |
| Dependency class duplicate | Căn chỉnh packaging và xác minh defining loader lúc chạy. |

Không nên chỉ bỏ unchecked-cast warning, cast lại, so tên bằng `getName()`, lạm dụng reflection, đổi TCCL sau khi đã tạo object hoặc đưa toàn bộ thư viện vào bootstrap/system loader. **Các cách này không hợp nhất identity của hai định nghĩa class**.

Nếu cần cast trực tiếp qua boundary, hai phía phải tham chiếu tới **cùng định nghĩa interface/base class phù hợp**. Nếu yêu cầu cô lập hoàn toàn, hãy truyền dữ liệu trung lập và tái tạo object hợp lệ ở phía nhận thay vì ép object implementation thuộc miền A sang class của miền B.

## 9. Hiểu nhầm thường gặp

**Hai loader có cùng parent thì chắc chắn nạp một kiểu?** Sai. Parent phải thực sự cung cấp class; nếu không, mỗi child có thể tự định nghĩa.

**Bytecode giống nhau thì JVM hợp nhất?** Sai. Defining loader là phần bắt buộc của identity.

**Interface không bị lỗi này?** Sai. Một interface `Task` do hai loader định nghĩa là hai kiểu khác nhau; implementation của một bản không tự implements bản kia.

**Generics giúp tránh mọi trường hợp?** Không. Type erasure có thể cho một `List` đi qua boundary, nhưng lúc lấy phần tử rồi cast thành model `Payload` của bên nhận, lỗi mới lộ ra.

**Đóng URLClassLoader có unload ngay class không?** Không. `close()` đóng tài nguyên loader; metadata class và object có thể còn được giữ bởi stack, thread, cache hoặc tham chiếu khác, tùy điều kiện unloading/GC.

**ClassCastException có phải NoClassDefFoundError hoặc LinkageError?** Không. `ClassCastException` xảy ra khi cast runtime không hợp lệ; `NoClassDefFoundError` thường liên quan việc JVM không thể có định nghĩa class cần dùng, còn `LinkageError` là nhóm lỗi khi định nghĩa/liên kết. Một sai cấu hình loader có thể hiện thành các lỗi khác nhau ở những pha khác nhau.

## 10. Câu hỏi tự kiểm tra

**Câu 1.** Hai loader A và B đọc cùng `Message.class` rồi đều tự định nghĩa `pkg.Message`. `classA.getName().equals(classB.getName())` bằng `true`. `classA == classB` là gì?

**Đáp án:** `false` vì defining loader khác nhau.

**Câu 2.** Hai child loader cùng ủy quyền nạp `api.Task` cho parent đã định nghĩa `Task`. Có hai kiểu không?

**Đáp án:** Không. Cả hai nhận cùng `Class<?>` do parent định nghĩa.

**Câu 3.** Vì sao nên dùng `targetType.isInstance(value)` chứ không chỉ so tên?

**Đáp án:** Vì nó kiểm tra object có tương thích kiểu đích theo quan hệ superclass/interface thực tế không.

**Câu 4.** Host có interface `Task`; plugin tự mang một `Task` khác cùng tên. Sửa thế nào?

**Đáp án:** Chỉ giữ một định nghĩa API contract tại loader dùng chung, để implementation của plugin implements đúng `Task` của host/parent.

**Câu 5.** Lỗi xuất hiện sau redeploy dù source Java không đổi?

**Đáp án:** Loader mới có thể định nghĩa một kiểu khác; object cũ bị cache giữ vẫn thuộc kiểu của loader cũ, nên không cast được sang kiểu mới.

## Ghi nhớ

**Tên lớp giống nhau không bảo đảm ép kiểu được.** Với class/interface, JVM dùng **(binary name, defining loader)** làm định danh. Khi gặp “A cannot be cast to A”, kiểm tra hai `Class<?>` thực, `getClassLoader()`, `isInstance(...)` và đường đi của object; sau đó chia sẻ **API contract từ một loader chung** hoặc trao đổi qua dữ liệu trung lập.

**Tài liệu chuẩn:**

- *Java Virtual Machine Specification*, Java SE 17 `5.3` — https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html#jvms-5.3
- *Java Language Specification*, Java SE 17 `12.2` — https://docs.oracle.com/javase/specs/jls/se17/html/jls-12.html#jls-12.2
- Java SE 17 API, `ClassLoader` — https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html
- Java SE 17 API, `Class` — https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html
