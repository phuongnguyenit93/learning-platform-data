# Parent delegation và mục đích dùng chung kiểu nền tảng trong Java

**Parent delegation** (ủy quyền cho class loader cha) là cơ chế mặc định của `java.lang.ClassLoader`: khi một loader nhận yêu cầu nạp một lớp, nó **ưu tiên để loader cha tìm lớp trước**, chỉ tự tìm/định nghĩa lớp nếu đường ủy quyền không nạp được. Cách tổ chức này giúp ứng dụng và các loader con dùng **chung định nghĩa của các kiểu nền tảng và kiểu API đã được loader cha cung cấp**, tránh tình trạng nhiều bản sao runtime của cùng một tên lớp làm hỏng việc gán kiểu, ép kiểu hoặc giao tiếp giữa plugin và ứng dụng.

Hai nguyên tắc cần nhớ:

1. **Một tên lớp chưa đủ xác định một kiểu Java lúc chạy.** Danh tính runtime class phụ thuộc vào cả *binary name* và *defining class loader*.
2. **Parent-first là chính sách mặc định của `ClassLoader.loadClass`**, không phải mệnh lệnh buộc mọi class loader tùy biến đều phải hoạt động hệt nhau. Một số loader chuyên dụng cố tình dùng thứ tự khác để cô lập dependency.

## 1. Vì sao Java có nhiều class loader?

Ứng dụng không nhất thiết có một bảng tên lớp duy nhất. Class loader cho phép JVM tìm, định nghĩa và tổ chức các lớp đến từ những nguồn khác nhau, ví dụ JDK modules, classpath, plugin, mã được sinh trong runtime hoặc các vùng triển khai độc lập.

Với Java 17+ thông thường, chuỗi loader có thể hình dung như sau:

```text
Application / System ClassLoader
        |
        | parent
        v
Platform ClassLoader
        |
        | parent
        v
Bootstrap loader (do JVM cung cấp, không phải một ClassLoader Java thường)
```

- **Bootstrap loader** định nghĩa nhiều lớp cốt lõi như `java.lang.Object`, `java.lang.String`; `String.class.getClassLoader()` trả `null`, theo quy ước API đại diện cho bootstrap loader.
- **Platform class loader** có nhiệm vụ nạp các lớp trong tập platform modules theo cơ chế JDK hiện đại.
- **Application/System class loader** thường nạp mã ứng dụng trên classpath và các thành phần tương ứng.

Sơ đồ là mô hình phổ biến giúp hiểu parent delegation, **không phải bản đồ đầy đủ của mọi đường nạp lớp**: Java Platform Module System (JPMS), module reader, class loader tùy biến và một số cách triển khai JDK có thể khiến việc phân công module hoặc định tuyến class phức tạp hơn chuỗi minh họa. Đặc biệt, `getParent() == null` không có nghĩa “không hề có code nền tảng nào để ủy quyền”; đối với API `ClassLoader`, nó biểu diễn đường tới bootstrap loader.

Một ứng dụng cũng có thể tạo các loader khác:

```text
                  Application Loader (chứa shared-api)
                  /                  \
                 v                    v
           Plugin A Loader      Plugin B Loader
           (plugin-a.jar)      (plugin-b.jar)
```

Hai plugin có thể có các implementation riêng nhưng cùng nhìn thấy `shared.api.Plugin` từ application loader. Chính **định nghĩa API được chia sẻ** này làm các đối tượng plugin có thể được kiểm tra bằng `instanceof`, ép về interface và truyền cho ứng dụng.

## 2. Parent delegation hoạt động như thế nào?

Phương thức trọng tâm là `ClassLoader.loadClass(String name)` hoặc biến thể protected `loadClass(String name, boolean resolve)`. Với **triển khai mặc định của `ClassLoader`**, thuật toán có thể mô tả:

1. Nhận **binary name** như `com.example.service.OrderService`, không phải đường dẫn `com/example/service/OrderService.class`.
2. Dùng `findLoadedClass(name)` để xem loader hiện tại đã là loader khởi phát (*initiating loader*) của lớp đó chưa; nếu có, trả về `Class<?>` đã biết.
3. Nếu chưa, **ủy quyền cho parent loader**, hoặc thử bootstrap loader khi không có Java parent.
4. Chỉ khi đường parent/bootstrap không tìm được lớp, gọi `findClass(name)` của loader hiện tại.
5. Nếu yêu cầu resolve, gọi `resolveClass(...)`; trả về đối tượng `Class<?>`.

Minh họa bằng giả mã (không phải nguyên văn triển khai JDK):

```text
loadClass(binaryName, resolve):
    lock phù hợp cho yêu cầu tải lớp

    c = findLoadedClass(binaryName)

    if c == null:
        try:
            c = parent != null
                ? parent.loadClass(binaryName)
                : bootstrapFind(binaryName)
        catch ClassNotFoundException:
            c = null

        if c == null:
            c = findClass(binaryName)

    if resolve:
        resolveClass(c)

    return c
```

Khi tự viết loader, thường override `findClass` để đọc byte và gọi `defineClass`; kế thừa `loadClass` giữ nguyên thứ tự parent-first. Việc override `loadClass` để ép child-first là lựa chọn có hậu quả về tính tương thích và nên được giới hạn rất cụ thể.

**Điều kiện lỗi:** nếu parent không tìm thấy lớp, nó báo `ClassNotFoundException` để loader con có cơ hội tự tìm. Nhưng nếu class file có vấn đề thật sự, chẳng hạn `ClassFormatError`, `VerifyError` hoặc lỗi linking khác, không được mặc định coi đó là “không tìm thấy” để âm thầm thay phiên bản khác. Đây là những lỗi khác bản chất.

### Parent-first không nhất thiết luôn gọi `findClass`

Nếu parent đã tìm thấy `java.util.List` hoặc `com.example.SharedApi`, class loader con thường **không phải định nghĩa lại** tên đó. Nó nhận cùng tham chiếu `Class<?>` mà đường cha cung cấp.

Ngược lại, khi parent không chứa `com.plugin.Feature` nhưng child loader có bytecode của lớp này, child gọi `findClass`, sau đó `defineClass` để tạo runtime class được định nghĩa bởi chính child.

`resolveClass` thuộc quá trình linking, không đồng nghĩa với việc chạy khối khởi tạo `static`. Gọi `loadClass` thông thường **không bắt buộc khởi tạo lớp**.

## 3. “Dùng chung kiểu nền tảng” nghĩa là gì?

Đây là trọng tâm của parent delegation. Java kiểm tra tương thích kiểu theo **runtime type identity**. Đối với lớp/interface có cùng binary name, loader định nghĩa khác nhau thường tạo **hai kiểu khác nhau**.

Ta có thể biểu diễn danh tính của một kiểu lớp thường bằng cặp:

```text
Runtime type identity =
    (binary name, defining class loader)
```

Ví dụ:

```text
("shared.api.Message", ApplicationLoader)  ≠
("shared.api.Message", PluginLoader)
```

Dù tên lớp và bytecode giống nhau, đây vẫn là hai định nghĩa runtime khác nhau. Nếu một plugin trả về đối tượng triển khai phiên bản `shared.api.Message` tự định nghĩa, ứng dụng đang sử dụng phiên bản từ parent có thể không chấp nhận phép cast hoặc chữ ký API như mong đợi.

### 3.1. Các kiểu JDK cốt lõi

Những kiểu như `Object`, `String`, `Throwable`, `Class`, `List` và `Map` cung cấp ngôn ngữ kiểu chung để mọi phần ứng dụng giao tiếp. Đường parent delegation giúp loader con dùng cùng những định nghĩa đó từ bootstrap/platform theo kiến trúc runtime.

Ví dụ:

- Một plugin tạo chuỗi `String` và trả cho ứng dụng. Cả hai sử dụng cùng lớp nền tảng `java.lang.String`.
- Một plugin trả `java.util.List<String>`. Kiểu thô `java.util.List` và `String` được chia sẻ ở runtime; tính đúng đắn của từng phần tử và generic contract vẫn cần tuân thủ (generic type parameters bị xóa phần lớn ở runtime).
- Một plugin ném `IllegalArgumentException`. Ứng dụng nhận diện được kiểu exception thuộc runtime nền tảng.

Parent delegation là một phần giúp tránh “hai `java.lang.String` không tương thích”, nhưng **không tự động đảm bảo mọi API của plugin đều tương thích**: application-specific API và dependency còn phải được định nghĩa từ loader chung hoặc tương thích qua cơ chế cầu nối phù hợp.

### 3.2. Các interface và model dùng chung

Giả sử có API:

```java
package shared.api;

public interface Plugin {
    String execute();
}
```

Application nạp `shared.api.Plugin` từ loader cha. Mỗi plugin loader nên nạp **chính interface đó** qua delegation, còn `plugins.alpha.AlphaPlugin` và `plugins.beta.BetaPlugin` có thể do loader con tương ứng định nghĩa. Ứng dụng khi đó có thể nhận và gọi object bằng kiểu `shared.api.Plugin`.

Tuy nhiên, nếu mỗi plugin mang riêng một bản `shared.api.Plugin` và loader tùy biến child-first tự định nghĩa nó, việc tên package và class giống nhau không làm hai interface trở thành cùng kiểu. Các thao tác như cast và đăng ký service có thể thất bại.

Đoạn interface trên là **một phần API minh họa**, không có `main` và cần được biên dịch/triển khai như dependency chia sẻ của hệ thống plugin.

## 4. Ví dụ Java 17+: parent-first chia sẻ Class object, child-first tạo kiểu khác

Thực hành với hai tệp Java trong **cùng thư mục nguồn**. Mục đích là chứng minh parent delegation mặc định và đối chiếu với một loader cố tình đi ngược chính sách.

Tạo tệp **`SharedApi.java`**:

```java
public final class SharedApi {
    public SharedApi() {
    }

    public String message() {
        return "hello";
    }
}
```

Tạo tệp **`ParentDelegationDemo.java`**:

```java
import java.io.IOException;
import java.io.InputStream;

public class ParentDelegationDemo {
    static final class SelectiveChildFirstLoader extends ClassLoader {
        private final String nameToIsolate;

        SelectiveChildFirstLoader(ClassLoader parent, String nameToIsolate) {
            super(parent);
            this.nameToIsolate = nameToIsolate;
        }

        @Override
        protected Class<?> loadClass(String name, boolean resolve)
                throws ClassNotFoundException {
            if (!name.equals(nameToIsolate)) {
                return super.loadClass(name, resolve);
            }

            synchronized (getClassLoadingLock(name)) {
                Class<?> type = findLoadedClass(name);
                if (type == null) {
                    type = findClass(name);
                }
                if (resolve) {
                    resolveClass(type);
                }
                return type;
            }
        }

        @Override
        protected Class<?> findClass(String name)
                throws ClassNotFoundException {
            String resourceName = name.replace('.', '/') + ".class";

            try (InputStream stream =
                    getParent().getResourceAsStream(resourceName)) {
                if (stream == null) {
                    throw new ClassNotFoundException(name);
                }
                byte[] bytes = stream.readAllBytes();
                return defineClass(name, bytes, 0, bytes.length);
            } catch (IOException error) {
                throw new ClassNotFoundException(name, error);
            }
        }
    }

    public static void main(String[] args) throws Exception {
        ClassLoader appLoader =
                ParentDelegationDemo.class.getClassLoader();

        ClassLoader defaultChild = new ClassLoader(appLoader) {
        };
        Class<?> delegated = defaultChild.loadClass("SharedApi");

        System.out.println("Parent-first shares class: "
                + (delegated == SharedApi.class));

        ClassLoader isolatedLoader =
                new SelectiveChildFirstLoader(appLoader, "SharedApi");
        Class<?> isolated = isolatedLoader.loadClass("SharedApi");

        System.out.println("Same binary name: "
                + isolated.getName().equals(SharedApi.class.getName()));
        System.out.println("Same runtime class: "
                + (isolated == SharedApi.class));
        System.out.println("Same defining loader: "
                + (isolated.getClassLoader()
                        == SharedApi.class.getClassLoader()));

        Object object = isolated.getDeclaredConstructor().newInstance();
        System.out.println("Can cast to parent's SharedApi: "
                + (object instanceof SharedApi));

        try {
            SharedApi converted = (SharedApi) object;
            System.out.println(converted.message());
        } catch (ClassCastException expected) {
            System.out.println("Cast result: ClassCastException");
        }

        System.out.println("String uses bootstrap loader: "
                + (String.class.getClassLoader() == null));
    }
}
```

Biên dịch và chạy bằng JDK 17+ từ thư mục chứa hai tệp:

```bash
javac --release 17 -d out SharedApi.java ParentDelegationDemo.java
java -cp out ParentDelegationDemo
```

Kết quả dự kiến với runtime Java chuẩn:

```text
Parent-first shares class: true
Same binary name: true
Same runtime class: false
Same defining loader: false
Can cast to parent's SharedApi: false
Cast result: ClassCastException
String uses bootstrap loader: true
```

**Tại sao có kết quả này?**

1. `defaultChild` là loader con chỉ kế thừa `ClassLoader.loadClass`. Khi nó yêu cầu `SharedApi`, application loader đã có thể tìm class file trên `out` và cung cấp cùng runtime class với `SharedApi.class`, do đó phép so sánh đầu trả `true`.
2. `SelectiveChildFirstLoader` được viết chỉ để **ưu tiên định nghĩa riêng đúng tên `SharedApi`**. Nó lấy bytecode `SharedApi.class` làm dữ liệu, gọi `defineClass` và tạo một `Class<?>` mới có **defining loader khác**.
3. `isolated.getName()` và `SharedApi.class.getName()` giống nhau, nhưng hai đối tượng `Class` khác nhau. Đối tượng được tạo bằng reflection từ bản isolated không phải instance của kiểu `SharedApi` phía application loader.
4. Vì vậy `instanceof` trả `false` và cast ném `ClassCastException`. Đây là điều xảy ra **ngay cả khi bytecode của hai bản lớp là cùng một tệp**.
5. `java.lang.String` vẫn có defining loader bootstrap; loader con không tự định nghĩa lại `String`.

**Cảnh báo về phạm vi ví dụ:** Đây là loader dùng để minh họa khác biệt danh tính kiểu. Nó cố tình phá thứ tự parent-first đối với đúng một tên, không phải trình quản lý plugin hoàn chỉnh. Việc lấy byte từ `getParent().getResourceAsStream(...)` chỉ đơn giản hóa cách lấy mẫu bytecode; trong plugin thật phải quản lý nguồn bytecode, lớp API chung, package sealing, quyền truy cập, dependency và vòng đời loader.

### Quan sát bằng Class#getClassLoader()

Từ ví dụ:

```java
ClassLoader definingLoader = isolated.getClassLoader();
ClassLoader parentDefiningLoader = SharedApi.class.getClassLoader();
boolean sameDefinition = isolated == SharedApi.class;
```

Đây là **đoạn minh họa dùng các biến đã khai báo trong `main`**, không phải chương trình độc lập. Nó nhấn mạnh rằng `getClassLoader()` trả loader *định nghĩa* class, trong khi một loader khác có thể là *initiating loader* do đã ủy quyền tìm thành công. Không kết luận “child định nghĩa lớp” chỉ vì code gọi `child.loadClass(...)`.

## 5. Parent-first mang lại lợi ích gì?

| Mục tiêu | Parent delegation hỗ trợ như thế nào? | Giới hạn |
|---|---|---|
| **Chung danh tính kiểu nền tảng** | Child dùng `String`, `Object`, `Throwable`... do runtime nền tảng định nghĩa | Không xác minh mọi logic sử dụng kiểu đó |
| **Chung API giữa app và plugin** | Cùng interface, DTO hoặc contract từ loader cha | Cần bố trí shared API ở parent thực sự |
| **Tránh định nghĩa trùng lặp** | Child không cần tải/định nghĩa một class mà parent đã nạp được | Parent có thể cung cấp phiên bản khác phiên bản plugin mong đợi |
| **Giảm rủi ro spoofing lớp cốt lõi** | Loader bình thường ưu tiên lớp JDK từ parent/bootstrap | Đây không phải sandbox toàn diện; class loader tùy biến có thể thay chiến lược trong phần phạm vi được phép |
| **Đơn giản hóa dependency chung** | Nhiều child dùng chung core library và class identity | Không tự động giải quyết dependency version conflict hoặc module readability |
| **Duy trì một bản static state của shared class** | Các child nhìn cùng runtime class từ parent và static fields của nó | Có thể tạo coupling hoặc xung đột cấu hình dùng chung |

Có một **đánh đổi về isolation**: khi parent đã cung cấp tên `com.lib.JsonParser` phiên bản A, child có thể không được dùng phiên bản B có cùng tên trên đường parent-first của nó. Đây là lý do một số plugin container, application server hoặc module framework thiết kế namespace/loader policy khác cho phần implementation và thư viện riêng.

## 6. Parent-first không có nghĩa “tất cả class đều nạp bởi parent”

Cần phân biệt ba tình huống:

### A. Parent có lớp

```text
child.loadClass("shared.api.Plugin")
    -> parent.loadClass(...)
    -> thành công
    -> child nhận lại chính Class<?> từ parent
```

Trong một kiến trúc plugin, đây là kết quả mong đợi với `shared.api.Plugin`.

### B. Parent không có lớp; child có lớp

```text
child.loadClass("plugins.alpha.AlphaPlugin")
    -> parent: ClassNotFoundException
    -> child.findClass(...)
    -> child.defineClass(...)
    -> child định nghĩa plugin implementation
```

Đây cũng là parent delegation đúng chuẩn: loader con chỉ tìm sau khi parent bỏ lỡ.

### C. Parent có lớp nhưng child muốn bản riêng

```text
child-first cho một namespace cụ thể:
    -> child.findClass(...)
    -> child.defineClass(...)
    -> có khả năng khác runtime type với lớp cùng tên ở parent
```

Chính sách này có thể phù hợp với plugin isolation, nhưng phải **loại trừ các API xuyên biên giới** khỏi vùng nạp riêng. Nếu interface mà app và plugin giao tiếp bị định nghĩa hai lần, hai bên có thể không ép kiểu qua lại.

**Quy tắc thiết kế phổ biến:** Đặt `java.*` và shared contracts dưới parent delegation; dùng child-specific namespace cho phần triển khai riêng. Một loader chuyên dụng có thể còn có chính sách chi tiết hơn, nhưng không nên sao chép tất cả dependency sang child theo kiểu thiếu kiểm soát.

## 7. Class identity và loader constraints sâu hơn một bước

Một JVM class không được nhận diện chỉ bằng tên của file, URL nguồn hay source code. Nó được định nghĩa bởi *binary name* cùng *defining loader*. Vì vậy:

```text
Loader P defines shared.api.Event
Loader A delegates shared.api.Event to P
Loader B delegates shared.api.Event to P

A's Event == B's Event == P's Event
```

Ngược lại:

```text
Loader A defines shared.api.Event
Loader B defines shared.api.Event

A's Event != B's Event
```

Khi classes từ những loader khác nhau giao tiếp qua method/field descriptors, JVM có các **loading constraints** để giữ nhất quán kiểu trong những ngữ cảnh tương ứng. Xung đột có thể dẫn đến `LinkageError`, trong khi thao tác ép kiểu không hợp lệ ở runtime có thể dẫn đến `ClassCastException`.

Ví dụ thực tế: `com.example.User cannot be cast to com.example.User` nghe vô lý nếu chỉ nhìn tên lớp, nhưng có thể chính xác khi hai `User` có defining loaders khác nhau. Một số stack trace JDK hiện đại còn ghi module/loader liên quan, giúp phát hiện nguyên nhân.

Cũng cần phân biệt:

- `ClassNotFoundException` thường được API tra cứu tường minh như `loadClass` hoặc `Class.forName` báo khi không tìm thấy lớp.
- `NoClassDefFoundError` thường xuất hiện trong lúc JVM cần liên kết/sử dụng một lớp mà định nghĩa không còn giải quyết được; nó cũng có thể xảy ra khi class từng **khởi tạo thất bại**.
- `ClassCastException` có thể do hai runtime types không tương thích, kể cả khi cùng tên.
- `LinkageError` còn có thể phát sinh do loader constraints, duplicate definition, version hoặc các lỗi liên kết khác.

Không kết luận tất cả lỗi trên đều do “parent delegation sai”. Hãy tìm class name, *defining loader*, classpath/module path và phiên bản thực tế.

## 8. Vì sao parent nhìn không thấy lớp con?

Mối quan hệ **ủy quyền từ child lên parent**, không mặc nhiên cho phép parent tự tìm thấy class của child.

```text
Parent loader: chứa shared.api.Plugin
       ^
       | parent-first delegation
       |
Child loader: chứa plugins.alpha.AlphaPlugin
```

Child có thể load interface từ parent. Nhưng nếu parent gọi `parent.loadClass("plugins.alpha.AlphaPlugin")`, nó không tự động duyệt danh sách mọi child loader để tìm lớp này.

Cách giao tiếp là **child tạo instance của implementation rồi đưa ra như shared interface**, hoặc hệ thống chủ động giữ một registry/loader reference để tìm plugin. Không nên kỳ vọng Java tự có “reverse delegation”.

### Thread context class loader (TCCL)

Một số SPI/framework phải tìm provider do child chứa ngay cả khi code tra cứu chạy trong thư viện do parent định nghĩa. Khi đó, **thread context class loader** có thể đóng vai trò chỉ dẫn:

```java
ClassLoader loader = Thread.currentThread().getContextClassLoader();
Class<?> provider = loader.loadClass("plugins.alpha.AlphaPlugin");
```

Đây là **đoạn minh họa** đòi hỏi loader phù hợp đã được đặt vào thread; `getContextClassLoader()` có thể trả `null` và `loadClass` có thể ném `ClassNotFoundException`. Ở ứng dụng thực tế cần xử lý hai trường hợp đó.

TCCL không tự thay đổi cách `ClassLoader.loadClass` phân giải mọi class. Nó chỉ là một tham chiếu loader mà code/framework có thể chủ động sử dụng; ví dụ `ServiceLoader` có các cách chọn loader phù hợp để tìm provider. Đặc biệt trong thread pool, phải khôi phục context loader sau tác vụ nếu đã tạm thay đổi nó, tránh rò rỉ ngữ cảnh plugin giữa các request.

## 9. Phân biệt parent delegation với những khái niệm dễ nhầm

### Classpath và module path

**Classpath** quyết định nguồn có thể tìm lớp; **parent delegation** quyết định loader nào được hỏi và theo thứ tự nào. Có file `.class` trong JAR của child không có nghĩa child luôn định nghĩa lớp: nếu parent đã có class cùng tên, mặc định parent thắng.

Trong **JPMS** (Java 9+), module readability, exports/opens và module-to-loader mapping đặt thêm giới hạn/quan hệ. Một loader có thể nạp lớp nhưng code vẫn không được truy cập một package do quy tắc module/access. Không đồng nhất cơ chế parent delegation với module access control.

### Loading, linking và initialization

- `loadClass("pkg.Type")` nhận binary name và trả `Class<?>` sau quá trình tìm/nạp thích hợp, có thể kèm resolve nếu đường gọi yêu cầu.
- `Class.forName("pkg.Type", false, loader)` cho phép lấy `Class<?>` mà không yêu cầu khởi tạo.
- `Class.forName("pkg.Type")` thường yêu cầu initialization.
- `String.class.getClassLoader() == null` là cách quan sát defining loader bootstrap, **không phải** bằng chứng về thứ tự gọi các API nạp lớp.

### Class và resource

`ClassLoader.getResource("pkg/Type.class")` tìm **tài nguyên** với dấu `/`, còn `loadClass("pkg.Type")` nạp **lớp** bằng binary name. Cả hai có thể được implement/delegate theo chính sách riêng; tìm thấy một file resource không nhất thiết đồng nghĩa class được định nghĩa bởi loader truy vấn đó. Không dựa chỉ vào đường dẫn `.class` để khẳng định identity.

### “Parent-first = bảo mật đầy đủ”

Parent-first làm khó việc thay thế ngẫu nhiên các class quan trọng được parent tìm thấy và việc định nghĩa package `java.*` còn bị Java runtime hạn chế. Tuy vậy, **class loader không phải sandbox an ninh chung**: nó không thay thế kiểm soát quyền truy cập file, network, process, native code hoặc đánh giá độ tin cậy của plugin.

## 10. Những lỗi thiết kế thường gặp

| Lỗi | Hậu quả | Cách xử lý |
|---|---|---|
| Đóng gói shared API vào mỗi plugin rồi child-first cho API đó | `instanceof`/cast sai, loader constraint conflicts | Định nghĩa shared API ở parent; plugin delegate namespace API |
| Dùng `child.loadClass` rồi tưởng child luôn định nghĩa class | Chẩn đoán sai loader sở hữu class | Xem `clazz.getClassLoader()` và so sánh `Class<?>` |
| Override toàn bộ `loadClass` để child-first mọi tên | Đụng core/third-party/shared types | Chỉ áp dụng child-first cho namespace riêng thực sự cần |
| Đổi binary name thành `pkg/Type.class` khi gọi `loadClass` | `ClassNotFoundException` | Dùng `pkg.Type`; path chỉ dành cho resource lookup |
| Giả định parent có thể nạp implementation chỉ nằm ở child | Plugin không được tìm thấy | Dùng loader của plugin, registry hoặc context loader phù hợp |
| Giả định cùng FQCN thì ép kiểu được | `ClassCastException` hoặc `LinkageError` | Kiểm tra defining loaders và nơi đặt shared contracts |
| Cho rằng parent-first tự giải quyết mọi khác biệt version | Plugin dùng sai API/`NoSuchMethodError` | Thiết kế classpath và vùng dependency isolation đúng |
| Giữ tham chiếu đến child loader, `Class`, thread hoặc object mãi mãi | Loader khó được thu gom khi plugin unload | Giải phóng registry, task, thread/TCCL và resource theo lifecycle |

Một trường hợp quan trọng là **static singleton**. Nếu cùng một class bị định nghĩa riêng trong hai loader, mỗi runtime class có các static fields riêng. Khi class được chia sẻ qua parent, các child cùng truy cập trạng thái static của **cùng một runtime class**. Điều này có thể là mục tiêu (shared registry) hoặc rủi ro (coupling và khó cô lập cấu hình); cần chọn phạm vi loader chủ động.

## 11. Cách chẩn đoán sự cố class loading

Khi gặp `ClassCastException` khó hiểu hoặc xung đột dependency, thực hiện theo thứ tự:

1. **Lấy binary name của cả hai kiểu** từ exception hoặc code liên quan.
2. **In defining loader**: `someObject.getClass().getClassLoader()`, `ExpectedApi.class.getClassLoader()`, kể cả khi một bên là `null` (bootstrap).
3. **So sánh `Class<?>` trực tiếp**: `obj.getClass() == ExpectedApi.class` khi điều kiện có ý nghĩa; hoặc `ExpectedApi.class.isAssignableFrom(obj.getClass())` khi muốn kiểm tra quan hệ subtype.
4. **Xem parent chain** và chính sách override `loadClass`, `findClass`, `getResource`. Parent-first mặc định khác custom child-first.
5. **Kiểm tra placement của API/dependency**: shared contract nằm trong app/platform parent hay bị sao chép vào các plugin?
6. **Xác minh nguồn class thực tế** bằng cách kiểm tra code source/resource khi có thể; lưu ý đường URL không thay thế thông tin defining loader.
7. **Xem bối cảnh module/service discovery** nếu dùng JPMS, `ServiceLoader` hoặc thread context class loader.
8. **Sửa classpath và loader policy có chủ đích**. Tránh giải quyết bằng cách đổi tên class, bắt bỏ `ClassCastException` hoặc ép reflection truy cập ngoài contract.

Đoạn hỗ trợ chẩn đoán có thể đặt trong phương thức Java:

```java
static void describe(Class<?> type) {
    System.out.println("Name: " + type.getName());
    System.out.println("Defining loader: " + type.getClassLoader());
}
```

Đây là method có thể dùng trong một class, **không phải chương trình độc lập**. Kết quả dòng loader phụ thuộc JVM, deployment và cách loader override `toString()`, nên không có stdout cố định cho ví dụ này.

## 12. Tự kiểm tra kiến thức

1. **Child gọi `loadClass("java.lang.String")` có nhất thiết tự định nghĩa String?** Không. Trong trường hợp chuẩn, class nền tảng được tìm theo delegation và cùng định nghĩa từ bootstrap.
2. **Parent-first có nghĩa child không bao giờ định nghĩa class?** Không. Nếu parent không tìm được, child có thể `findClass`/`defineClass`.
3. **Hai `com.acme.User` bytecode giống hệt nhưng khác defining loader có là cùng kiểu không?** Không. Danh tính runtime khác nhau nên phép cast có thể thất bại.
4. **Tại sao shared interface phải nằm ở loader chung?** Để ứng dụng và plugin dùng cùng runtime type làm contract, nhờ đó giá trị từ plugin có thể gán cho interface mà ứng dụng đã biết.
5. **Khi nào child-first có thể có ích?** Khi plugin cần phiên bản dependency riêng mà parent không nên áp đặt; phải có quy tắc bảo vệ shared API.
6. **Parent có thể tự động tìm mọi class chỉ nằm trong child loader?** Không; cần loader reference, registry, service mechanism hoặc context loader.
7. **Gọi `child.loadClass("pkg.Type")` rồi thấy `clazz.getClassLoader() == parent` là lỗi?** Không, đó có thể chính là parent delegation hoạt động đúng.
8. **Parent delegation có thay thế được quyền truy cập module và bảo mật ứng dụng?** Không. Đó là các cơ chế độc lập với những mục tiêu riêng.

## 13. Nguồn tham khảo chính thức

- Java SE 17 API, `ClassLoader` và hành vi mặc định của `loadClass`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html
- Java Virtual Machine Specification, `5.3 “Creation of Classes and Interfaces”` (defining/initiating loaders, danh tính lớp): https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html#jvms-5.3
- Java Virtual Machine Specification, `5.3.4 “Loading Constraints”`: https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html#jvms-5.3.4
- Java SE 17 API, `Thread.getContextClassLoader`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Thread.html#getContextClassLoader()

**Ghi nhớ:** Parent delegation mặc định ưu tiên tìm lớp ở loader cha; nhờ vậy nhiều child loader có thể dùng **cùng các kiểu nền tảng và contract chung**. Khi cùng binary name bị định nghĩa bởi các loader khác nhau, chúng là các runtime types khác nhau. Đặt shared API ở loader cha, tách implementation trong child và chỉ dùng chính sách child-first khi thực sự cần vùng phụ thuộc riêng.
