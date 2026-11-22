# Vai trò của parent null khi ủy quyền tới bootstrap class loader

## 1. Vấn đề cần hiểu

Khi tự tạo `ClassLoader` trong Java, có thể truyền `null` làm parent:

```java
ClassLoader loader = new ClassLoader(null) { };
```

Nhiều người đọc đoạn này và kết luận “loader không có parent nên không ủy quyền cho ai”. Kết luận đó **sai đối với cơ chế mặc định của `java.lang.ClassLoader`**.

Trong hợp đồng của `ClassLoader`, **parent bằng `null` là cách API biểu diễn việc ủy quyền tới bootstrap class loader**. Bootstrap là tầng nạp những lớp lõi của JVM; nó không được biểu diễn trực tiếp bằng một instance `ClassLoader` thông thường. Vì vậy:

- `new ClassLoader(null) { }` tạo một **custom loader object mới**.
- `loader.getParent() == null` báo không có **parent object Java**; khi dùng thuật toán `loadClass` mặc định, nó sẽ thử dùng **bootstrap class loader** cho bước delegation.
- Nó **không biến loader mới thành bootstrap class loader**, không làm bootstrap bị vô hiệu, và cũng không trao cho loader mới khả năng tìm các class ứng dụng trên class path.
- Sau khi bootstrap không tìm được class, loader mới có thể tự tìm class qua `findClass` nếu đã được triển khai; bản `findClass` kế thừa từ `ClassLoader` mặc định ném `ClassNotFoundException`.

Điểm phân biệt trọng tâm: `null` là **ký hiệu đặc biệt trong API Java**, còn bootstrap class loader là **cơ chế runtime có thật** để nạp lớp nền tảng.

## 2. Parent là gì và tại sao bootstrap được biểu diễn bằng null?

Một class loader có thể yêu cầu một loader cấp trên thử tìm class trước, theo **parent delegation**. Cơ chế này giúp các class ở nhiều loader khác nhau dùng chung các loại nền tảng, chẳng hạn `java.lang.Object` và `java.lang.String`.

Trong JDK 17 có ba tầng built-in thường gặp:

```text
Bootstrap class loader
    (không có đối tượng ClassLoader Java công khai)
                   ^
                   |  getParent() == null ở loader dưới
                   |
Platform class loader
                   ^
                   |
Application / system class loader
                   ^
                   |
Custom loader (nếu chọn app làm parent)
```

Ví dụ thông thường:

```java
ClassLoader platform = ClassLoader.getPlatformClassLoader();
ClassLoader system = ClassLoader.getSystemClassLoader();

System.out.println(platform.getParent() == null);
System.out.println(system.getParent() == platform);
```

Trong cấu hình mặc định của OpenJDK/HotSpot 17, hai dòng thường in `true`, `true`. Các chi tiết về system loader có thể được cấu hình hoặc thay đổi; không suy ra chain thực tế của mọi runtime chỉ từ sơ đồ.

**Tại sao không tạo `BootstrapClassLoader extends ClassLoader`?** Ở các JVM thông dụng, bootstrap loader được thực hiện ở tầng JVM/native và không được expose như một instance `ClassLoader` thông thường. Vì thế API dùng `null` ở những chỗ như `getClassLoader()` và `getParent()` để đại diện cho tầng đó.

Không nên nhầm **quan hệ parent trong cơ chế nạp lớp** với `extends` của Java: hai class loader object không cần kế thừa nhau để một loader được đặt làm parent của loader khác.

## 3. Thuật toán `ClassLoader.loadClass` mặc định khi parent null

Với `ClassLoader.loadClass(String name, boolean resolve)` mặc định, cơ chế chính có thể diễn đạt như sau:

1. Kiểm tra class đã được loader hiện tại ghi nhận là loaded hay chưa, bằng `findLoadedClass(name)`.
2. Nếu chưa, thử nhờ **parent** load class. Nếu parent bằng `null`, thực hiện nhánh nạp thông qua **bootstrap class loader**.
3. Nếu parent/bootstrap không tìm được class, gọi `findClass(name)` của loader hiện tại để nó có cơ hội tự định nghĩa class.
4. Nếu được yêu cầu `resolve=true`, thực hiện resolution theo API; trả về `Class<?>` đã tìm thấy. Nếu tất cả bước đều thất bại, ném `ClassNotFoundException`.

Mã giả sau chỉ minh họa cơ chế, **không phải một bản override có thể copy nguyên xi vào Java**:

```text
loadClass(name, resolve):
    c = findLoadedClass(name)

    if c == null:
        if parent != null:
            thử c = parent.loadClass(name)
        else:
            thử c = bootstrap.loadClass(name)  // mã giả:
                                               // không có biến API "bootstrap"
        nếu c vẫn == null:
            c = findClass(name)

    nếu resolve:
        resolveClass(c)
    return c
```

Trong triển khai Java thực tế, `loadClass` còn có quy tắc synchronization/parallel-capable loaders và các điều kiện nội bộ. Mã giả nhằm làm rõ **đường ủy quyền khi parent null**, không nhằm thay thế Java API documentation.

Một ví dụ để tự diễn giải:

```text
customLoader = new ClassLoader(null) { }

customLoader.loadClass("java.lang.String")
    -> chưa do customLoader tự nạp
    -> parent == null -> hỏi bootstrap
    -> bootstrap đã biết/định nghĩa String
    -> trả về String.class

customLoader.loadClass("com.example.App")
    -> chưa do customLoader tự nạp
    -> parent == null -> hỏi bootstrap
    -> bootstrap không tìm thấy app class này
    -> gọi customLoader.findClass("com.example.App")
    -> bản findClass mặc định không có cách tìm class này
    -> ClassNotFoundException
```

Ví dụ kết quả trên phụ thuộc giả định `com.example.App` là class ứng dụng không thuộc bootstrap và loader không được cấp logic `findClass` riêng. Nếu bạn triển khai `findClass` hoặc chọn parent khác, kết quả có thể thay đổi.

### Delegation có luôn tuyệt đối là parent-first?

Không. `ClassLoader.loadClass` cung cấp thuật toán parent-first mặc định. Một subclass có thể override `loadClass` để đưa ra chính sách lookup khác, miễn tuân thủ contract JVM/Java liên quan. Vì vậy parent `null` **không bảo đảm** mọi loader tùy biến đều đi theo đúng nhánh mã giả trên nếu chính nó ghi đè thuật toán nạp.

Tuy nhiên, với `new ClassLoader(null) { }` **không override** `loadClass` và `findClass`, hành vi nêu trên là điều cần hiểu.

## 4. Chương trình Java 17: parent null vẫn nạp được lớp bootstrap

Tạo file **`NullParentDemo.java`**:

```java
public class NullParentDemo {
    public static void main(String[] args)
            throws ClassNotFoundException {

        ClassLoader isolated = new ClassLoader(null) { };
        ClassLoader app = NullParentDemo.class.getClassLoader();
        ClassLoader appChild = new ClassLoader(app) { };

        System.out.println("Parent is null: "
                + (isolated.getParent() == null));

        Class<?> str = isolated.loadClass("java.lang.String");
        Class<?> obj = isolated.loadClass("java.lang.Object");

        System.out.println("Delegated String: "
                + (str == String.class));
        System.out.println("Delegated Object: "
                + (obj == Object.class));

        System.out.println("String defining loader is bootstrap: "
                + (str.getClassLoader() == null));

        try {
            isolated.loadClass("NullParentDemo");
            System.out.println("Application class found");
        } catch (ClassNotFoundException expected) {
            System.out.println("Application class not visible");
        }

        System.out.println("App-parent finds application class: "
                + (appChild.loadClass("NullParentDemo")
                        == NullParentDemo.class));
    }
}
```

Biên dịch và chạy với **JDK 17 từ class path thông thường**:

```bash
javac NullParentDemo.java
java NullParentDemo
```

Stdout đúng trong môi trường đã nêu:

```text
Parent is null: true
Delegated String: true
Delegated Object: true
String defining loader is bootstrap: true
Application class not visible
App-parent finds application class: true
```

Giải thích theo từng kết quả:

1. `isolated.getParent() == null` xác nhận loader mới có parent API bằng `null`.
2. `isolated.loadClass("java.lang.String")` và `loadClass("java.lang.Object")` thành công nhờ nhánh bootstrap của thuật toán mặc định.
3. `str == String.class` và `obj == Object.class` chứng tỏ loader nhận về **cùng định danh runtime class** với các loại lõi đã có; nó không tạo một bản `String` hoặc `Object` mới.
4. `str.getClassLoader() == null` biểu thị **defining class loader** là bootstrap. Đừng nhầm điều này với loader object `isolated` vốn đã **khởi xướng** lệnh `loadClass`.
5. `isolated.loadClass("NullParentDemo")` thất bại vì bootstrap không tìm class ứng dụng này, còn custom loader không có cách `findClass` bổ sung.
6. `appChild` dùng application loader làm parent nên có thể ủy quyền để tìm chính class ứng dụng; kết quả `Class<?>` bằng `NullParentDemo.class`.

Ví dụ phân biệt rõ hai tính chất:

- **Có thể gọi loader để yêu cầu nạp một class** không có nghĩa chính loader đó **định nghĩa** class được trả về.
- **Không thấy class ứng dụng** không có nghĩa bootstrap loader bị hỏng. Loader chỉ không có đúng đường tìm kiếm cho class được hỏi.

## 5. Bốn chỗ xuất hiện null dễ gây nhầm

Cùng là ký hiệu `null` nhưng ngữ cảnh API quyết định ý nghĩa.

| Biểu thức | Ý nghĩa cần hiểu |
|---|---|
| `new ClassLoader(null) { }` | Tạo custom loader có parent ở cấp API là bootstrap; đây vẫn là một object loader riêng. |
| `loader.getParent() == null` | Không có parent `ClassLoader` object được trả về; trong mô hình loader API, null biểu thị bootstrap. |
| `String.class.getClassLoader() == null` | Class `String` do bootstrap định nghĩa. Không suy ra String chưa load. |
| `Class.forName("java.lang.String", false, null)` | Truyền loader là null: dùng bootstrap loader để tìm/nạp kiểu; `false` không yêu cầu initialization. |

### Null ở `Class.getClassLoader()` không phải null ở `getParent()`

`Class.getClassLoader()` báo loader đã **định nghĩa kiểu runtime** được đại diện (đối với array, theo quy tắc loader của component). `ClassLoader.getParent()` báo parent của **một object loader cụ thể**.

Do vậy:

```java
ClassLoader custom = new ClassLoader(null) { };
Class<?> type = custom.loadClass("java.lang.String");
```

Ở đây:

- `custom` **không null**: một loader object mới đã được tạo.
- `custom.getParent()` **null**: nó delegating lên tầng bootstrap qua thuật toán mặc định.
- `type.getClassLoader()` **null**: định nghĩa `String` do bootstrap cung cấp.
- `custom == type.getClassLoader()` là `false`, vì bên trái là object còn bên phải là `null`.

Đây là cách đọc quan trọng khi debug class loader: phân biệt **initiating loader** (nơi yêu cầu bắt đầu/được ghi nhận) với **defining loader** (nơi thực sự định nghĩa class).

### Null trong `Class.forName`

Với overload ba tham số:

```java
Class<?> c = Class.forName("java.lang.String", false, null);
```

Tham số cuối `null` yêu cầu lookup qua bootstrap. Còn `false` là cờ **không yêu cầu initialize** class; điều đó khác với “không loading”.

Với class chỉ tồn tại ở application class path, chẳng hạn `NullParentDemo`, gọi `Class.forName("NullParentDemo", false, null)` thường ném `ClassNotFoundException`, vì bootstrap không có nghĩa vụ tra cứu class path ứng dụng.

## 6. Bootstrap loader và system loader khác nhau

Trong cấu hình JDK 17 thường gặp:

- **Bootstrap loader** đảm nhận các lớp nền tảng như `java.lang.Object` và `java.lang.String`; không có object `ClassLoader` công khai đại diện nó.
- **Platform loader** có thể lấy qua `ClassLoader.getPlatformClassLoader()`; nó nạp một phần lớp thuộc các platform modules của JDK.
- **System/application loader** lấy qua `ClassLoader.getSystemClassLoader()`; thường xử lý class path ứng dụng và module thuộc phạm vi nó được giao.

Giữa các loader built-in, **bootstrap đứng ở trên cùng** trong mô hình delegation. Nhưng đừng khái quát rằng mọi package bắt đầu `java.` luôn được bootstrap định nghĩa: các lớp JDK thuộc những module khác nhau có thể có defining loader khác nhau. Hãy kiểm tra class thực tế nếu muốn kết luận.

Bảng phân biệt:

| Cách cấu hình custom loader | Điều gì xảy ra với default `loadClass`? | Tình huống dùng |
|---|---|---|
| `new ClassLoader(null) { }` | Bootstrap trước; rồi `findClass` custom (nếu có). Không tự thấy mọi class ứng dụng. | Loader biệt lập cần chủ động định nghĩa class riêng và dùng chung lớp lõi. |
| `new ClassLoader(ClassLoader.getPlatformClassLoader()) { }` | Platform parent sẽ tham gia delegation, có thể tiếp tục tới bootstrap. | Muốn truy cập tập nền tảng qua platform mà không dùng application loader. |
| `new ClassLoader(ClassLoader.getSystemClassLoader()) { }` | Thường thấy các class mà system loader có thể cung cấp, rồi mới tới logic riêng. | Plugin hoặc loader bổ sung cần kế thừa visibility của ứng dụng. |
| `new ClassLoader() { }` | Constructor không tham số thường chọn system class loader làm parent theo API. | Loader custom thông thường dùng default parent. |

**Cẩn thận:** “thấy class” ở bảng là nói về **lookup/visibility theo loader**, không đảm bảo vượt được ràng buộc access, module exports/opens, package integrity hoặc các quy tắc JVM khác. Đặc biệt, cơ chế loader không phải sandbox bảo mật toàn diện.

## 7. Parent null không cô lập mọi thứ

Một loader parent-null có thể không nhìn thấy class ứng dụng khác theo cơ chế mặc định, nhưng vẫn sử dụng được `java.lang.Object`, `java.lang.String` và nhiều kiểu bootstrap khác. Điều đó là chủ đích của Java: mọi loại ứng dụng cần chia sẻ nền tảng runtime.

Hệ quả:

- **Không phải môi trường “không có Java core”.** Class được custom loader định nghĩa vẫn phải được kiểm tra/liên kết theo ngữ nghĩa JVM và có thể tham chiếu những kiểu lõi cần thiết.
- **Không tự động được load JAR.** `new ClassLoader(null) { }` không tự có cơ chế scan mọi thư mục/JAR; cần parent phù hợp hoặc định nghĩa cách tìm class như `URLClassLoader`/`findClass` khi có nhu cầu.
- **Không tạo không gian tên hoàn toàn độc lập.** Hai runtime classes có cùng binary name chỉ được xem là cùng kiểu nếu danh tính runtime phù hợp (đặc biệt defining loader); chia sẻ `Object`/`String` không biến các lớp ứng dụng do hai loader khác nhau định nghĩa thành một kiểu.
- **Không phải ranh giới an toàn để chạy mã không tin cậy.** Code chịu kiểm tra bytecode, access rules, module boundaries và các cơ chế kiểm soát khác; parent null không thay thế sandbox chuyên dụng.

Ví dụ tình huống plugin:

Ứng dụng host cung cấp interface `com.example.api.Plugin` từ loader ứng dụng; mỗi plugin được nạp bằng custom loader parent-null. Khi plugin có class `MyPlugin implements Plugin`, JVM phải resolve tên `com.example.api.Plugin` cho class plugin. Nếu loader parent-null không tìm interface API này, linking/lookup có thể thất bại dù bootstrap đã tìm được `java.lang.Object`.

Một cách thiết kế thường gặp là cho loader plugin **ủy quyền tới loader chứa shared API** hoặc cho phép lookup/shared package có kiểm soát. Cần đảm bảo cả host và plugin sử dụng **cùng một định nghĩa runtime** của interface `Plugin`. Nếu plugin tự định nghĩa một bản interface cùng tên dưới loader khác, sẽ phát sinh vấn đề tương thích kiểu.

Không nên đặt parent null chỉ vì muốn “plugin tách biệt” mà bỏ qua dependency visibility và runtime type identity.

## 8. Ví dụ bổ sung: xem tầng bootstrap và parent chain

Tạo file **`LoaderChainDemo.java`**:

```java
public class LoaderChainDemo {
    public static void main(String[] args) {
        ClassLoader platform = ClassLoader.getPlatformClassLoader();
        ClassLoader system = ClassLoader.getSystemClassLoader();

        System.out.println("Object bootstrap: "
                + (Object.class.getClassLoader() == null));
        System.out.println("String[] bootstrap: "
                + (String[].class.getClassLoader() == null));
        System.out.println("Platform parent bootstrap: "
                + (platform.getParent() == null));

        System.out.println("System parent platform: "
                + (system.getParent() == platform));
        System.out.println("Main defined by system: "
                + (LoaderChainDemo.class.getClassLoader() == system));
    }
}
```

Chạy từ class path mặc định bằng JDK 17 HotSpot/OpenJDK, không cấu hình system loader riêng:

```bash
javac LoaderChainDemo.java
java LoaderChainDemo
```

Stdout:

```text
Object bootstrap: true
String[] bootstrap: true
Platform parent bootstrap: true
System parent platform: true
Main defined by system: true
```

Vì `String` thuộc bootstrap, array class `String[]` cũng có defining loader tương ứng; `String[].class.getClassLoader()` trả `null`. Với array, JVM tạo kiểu mảng runtime theo quy tắc riêng; đây không phải là một class file `String[].class` nằm trong class path.

Ví dụ dùng `==` để kiểm tra quan hệ loader thay vì in `toString()` hoặc class name của loader, bởi tên implementation như `jdk.internal.loader.ClassLoaders$AppClassLoader` có thể thay đổi và không phải contract công khai ổn định.

**Giới hạn ví dụ:** custom system class loader, môi trường chạy module khác hoặc JVM implementation khác có thể làm một vài dòng kiểm tra tầng application trả kết quả khác. Bài học cần giữ nguyên là quy ước null cho bootstrap và ý nghĩa của delegation.

## 9. Parent null và quá trình loading, linking, initialization

`loadClass` tìm/lấy runtime class; nó không đồng nghĩa với việc đã tạo instance hay đã chạy static initializer.

Ba hoạt động khác nhau:

1. **Loading:** tìm/định nghĩa runtime class qua loader thích hợp.
2. **Linking:** verification, preparation và resolution theo quy tắc JVM.
3. **Initialization:** chạy `<clinit>` của class khi có active use thích hợp.

Lệnh:

```java
Class<?> type = isolated.loadClass("java.lang.String");
```

không tạo một đối tượng `String` mới. Nó lấy `Class<?>` tương ứng kiểu `String`.

Tương tự, `Class.forName("java.lang.String", false, null)` yêu cầu lookup qua bootstrap nhưng không yêu cầu initialization vì cờ là `false`. Đừng nhầm cờ initialization với tham số loader: chúng kiểm soát **hai chiều khác nhau**.

Nếu `findClass` của loader mới định nghĩa một class ứng dụng, JVM vẫn phải kiểm tra/liên kết/khởi tạo class theo các quy tắc riêng; việc parent null không làm bỏ qua verification hoặc cấp quyền truy cập đặc biệt.

## 10. Những lỗi hay gặp và cách sửa

### Lỗi: “parent null = không ủy quyền”

**Thực tế:** Default `ClassLoader.loadClass` ủy quyền qua bootstrap khi parent null.

**Cách kiểm tra:** `new ClassLoader(null) {}.loadClass("java.lang.String") == String.class` trong chương trình có cú pháp hợp lệ; xem ví dụ `NullParentDemo`.

### Lỗi: “`getParent() == null` tức custom loader chính là bootstrap”

**Thực tế:** `getParent()` trả quan hệ parent, không trả defining-loader identity của chính object loader. Custom loader vẫn là một instance `ClassLoader` riêng.

**Cách kiểm tra:** gọi `isolated.getClass()` hoặc so sánh `isolated != null`; nó vẫn là một object đang tồn tại, có phương thức `loadClass` riêng.

### Lỗi: “Tạo `ClassLoader(null)` là đủ để load class file của dự án”

**Thực tế:** Bản mặc định `findClass` ném `ClassNotFoundException`. Bootstrap không duyệt tùy ý class path của ứng dụng.

**Cách sửa:** chọn parent nhìn thấy lớp cần dùng, hoặc viết loader biết tìm/định nghĩa bytes từ nguồn thích hợp; bảo đảm mọi shared types dùng đúng runtime identity.

### Lỗi: “Không nạp được class ứng dụng là do bootstrap không hoạt động”

**Thực tế:** Bootstrap vốn được giao nạp tập lớp nền tảng của runtime. `ClassNotFoundException` khi yêu cầu `NullParentDemo` từ loader parent-null chưa triển khai finder là điều dự kiến.

**Cách kiểm tra:** tách câu hỏi “bootstrap tìm được `String` không?” khỏi “custom loader tìm được class ứng dụng không?”. Hai bước cho biết thành phần nào thiếu visibility.

### Lỗi: “Hai class trùng binary name ở hai loader chắc chắn tương thích”

**Thực tế:** JVM xác định runtime identity bằng **binary name + defining class loader**. Lỗi `ClassCastException` hoặc `LinkageError` có thể xảy ra khi các loader định nghĩa bản không tương thích.

**Cách sửa:** xác định loader sở hữu shared API, để plugin và host thống nhất cách resolve các kiểu dùng chung; không vô tình nhân bản thư viện API ở nhiều loader.

### Lỗi: “Parent-first là quy luật cưỡng chế cho mọi custom loader”

**Thực tế:** Nó là cơ chế mặc định; subclass có thể override `loadClass`. Việc tùy biến phải xét constraints của VM và tránh phá các kiểu dùng chung.

**Cách sửa:** đọc code `loadClass` thật của custom loader, không phỏng đoán chỉ từ `getParent()`. Nếu override, ghi rõ trường hợp nào ưu tiên parent, trường hợp nào ưu tiên child và cách bảo vệ package nền tảng.

### Lỗi: “`Class.getClassLoader() == null` nghĩa object Class bị null”

**Thực tế:** `String.class` là một `Class<?>` object có thật; chỉ thuộc tính defining loader được API biểu diễn bằng `null`. Đừng suy từ nullable loader sang việc class/object không tồn tại.

## 11. Cách lựa chọn parent trong thiết kế thực tế

Trước khi chọn `new ClassLoader(null)`, trả lời ba câu hỏi:

1. **Class loader này cần nhìn thấy những class nào?** Nếu cần shared API của ứng dụng, chọn một parent thích hợp (ví dụ loader định nghĩa shared API); parent null thường không đủ.
2. **Các kiểu nào phải có chung runtime identity?** Những interface/DTO truyền qua boundary giữa host và plugin nên được cung cấp nhất quán từ loader được chia sẻ.
3. **Các class riêng được tìm bằng cách nào?** Nếu không có finder phù hợp, loader mới chỉ nhận những class từ parent/bootstrap, không tự nạp một JAR mới.

Bảng ra quyết định:

| Mục tiêu | Thiết lập có thể phù hợp | Điểm cần kiểm tra |
|---|---|---|
| Dùng class lõi của JVM | Parent null + default delegation có thể đủ | Không đòi class ứng dụng từ bootstrap. |
| Plugin dùng shared API của host | Parent là loader nhìn thấy shared API | Shared API phải dùng cùng defining loader. |
| Nạp class từ JAR riêng | Custom loader biết tìm bytes/JAR, parent được chọn theo API cần chia sẻ | Tránh định nghĩa trùng các kiểu dùng chung. |
| Chỉ lấy metadata của class lõi | Dùng `Class.forName(name, false, null)` nếu tên thuộc bootstrap | Cờ `false` liên quan initialization; kiểm tra class name chính xác. |
| Điều tra `ClassNotFoundException` | Kiểm tra loader được gọi, parent chain, `findClass` và class/module path | Tìm failure ở tầng lookup thực tế. |

**Lưu ý kỹ thuật:** Nạp lớp bằng `URLClassLoader` có thể hữu ích trong một số ứng dụng Java truyền thống, nhưng với hệ module hoặc plugin loader phức tạp, cần xét module boundaries và lifecycle (ví dụ đóng tài nguyên của URLClassLoader khi phù hợp). Parent null không tự thiết kế hộ một module/plugin system an toàn và nhất quán.

## 12. Bài tập tự kiểm tra

**Câu 1.** Vì sao `new ClassLoader(null) { }` vẫn nạp được `java.lang.String`?

**Đáp án:** `loadClass` mặc định dùng bootstrap loader khi parent bằng `null`. Bootstrap cung cấp định nghĩa `String` của runtime; custom loader trả `Class<?>` đó.

**Câu 2.** Gọi `loader.getParent() == null` có chứng minh `loader` chính là bootstrap loader không?

**Đáp án:** Không. Nó chỉ phản ánh parent trong API của một loader object. Bootstrap không được biểu diễn bằng object `ClassLoader` thường như custom loader.

**Câu 3.** Tại sao `new ClassLoader(null) { }.loadClass("com.example.App")` thường thất bại với class ứng dụng trên class path?

**Đáp án:** Bootstrap không được giao tìm class ứng dụng ấy; custom loader không có finder nếu không override `findClass`. Đây là lỗi lookup/visibility theo loader, không phải bằng chứng bytecode của `App` sai.

**Câu 4.** `ClassLoader.getSystemClassLoader()` và bootstrap có giống nhau không?

**Đáp án:** Không. System loader là loader API xử lý lớp ứng dụng trong cấu hình phổ biến; bootstrap là tầng nền tảng biểu diễn bằng `null` ở các API liên quan.

**Câu 5.** Một custom loader parent-null gọi `loadClass("java.lang.Object")` thành công. Defining loader của `Object` là custom loader hay bootstrap?

**Đáp án:** Bootstrap. Custom loader khởi xướng lookup và có thể được xem là initiating loader; defining loader của `Object` là bootstrap.

**Câu 6.** Nếu override `loadClass`, parent-null có buộc loader hỏi bootstrap đầu tiên không?

**Đáp án:** Không thể khẳng định chỉ từ thuộc tính parent. Thuật toán mặc định parent-first làm như vậy; override có thể thay lookup order, phải kiểm tra code và các ràng buộc JVM.

**Câu 7.** Cần gọi một interface `com.example.api.Plugin` thuộc class path host từ plugin class loader. Nên kiểm tra gì trước khi chọn parent null?

**Đáp án:** Loader phải resolve được interface từ định nghĩa dùng chung để class plugin có thể liên kết và có runtime type identity tương thích với host. Parent null chỉ thấy nền tảng nếu không có finder/shared lookup bổ sung.

## 13. Ghi nhớ và tài liệu tham khảo

- **`parent == null` trong `ClassLoader`:** default delegation tới **bootstrap**, không phải chặn mọi delegation.
- **`getParent() == null`:** biểu diễn quan hệ loader; **`SomeClass.class.getClassLoader() == null`:** biểu diễn class do bootstrap định nghĩa.
- **`new ClassLoader(null) { }`:** tạo một custom loader object bình thường; nếu không có `findClass` custom thì không tự tải được class app không có ở bootstrap.
- **Có parent khác null:** default loader có thể thấy tập class mà parent nhìn thấy. Chọn parent dựa trên shared API và type identity.
- **Class identity:** binary name **cùng** defining loader; requesting loader có thể không phải defining loader.
- **Delegation ≠ initialization:** `loadClass` không đồng nghĩa chạy `<clinit>` hoặc tạo instance.

Đọc thêm theo tài liệu chính thức:

1. [Java SE 17 — ClassLoader](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html): constructor với parent, `getParent`, `loadClass`, `findClass`, platform/system loaders.
2. [Java SE 17 — Class](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html): `getClassLoader` và `forName`, biểu diễn bootstrap bằng null.
3. [JVM Specification 17 — Chapter 5](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html): loading, linking, initialization, class loader identity và các ràng buộc liên kết.
4. [JEP 261 — Module System](https://openjdk.org/jeps/261): mô hình class loader built-in và các module runtime từ Java 9.