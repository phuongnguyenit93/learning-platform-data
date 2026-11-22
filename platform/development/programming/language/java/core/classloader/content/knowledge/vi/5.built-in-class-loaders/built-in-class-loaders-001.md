# Bootstrap class loader và vai trò của JVM

## 1. Bootstrap class loader là gì?

**Bootstrap class loader** (bộ nạp lớp khởi động) là cơ chế nạp các lớp nền tảng thiết yếu để Java Virtual Machine (JVM) có thể vận hành và thực thi chương trình Java. Các kiểu như `java.lang.Object`, `java.lang.String`, `java.lang.Class` và nhiều kiểu thuộc module `java.base` được định nghĩa bởi bootstrap class loader trên JDK 17 thông thường.

Nói ngắn gọn: **JVM là môi trường thực thi**, còn **bootstrap class loader là một phần cơ chế nạp lớp ở tầng nền tảng của JVM**. Bootstrap loader cung cấp những định nghĩa lớp cốt lõi để JVM và các class loader cấp cao hơn cùng sử dụng. Không nên coi hai khái niệm này là một:

- **JVM** thực thi bytecode, kiểm tra và liên kết lớp, quản lý bộ nhớ/GC, quản lý threads và thực hiện quy tắc khởi tạo lớp.
- **Bootstrap class loader** đảm nhiệm việc tìm và định nghĩa các lớp được giao cho tầng bootstrap. Nó chỉ là **một mắt xích của hệ thống nạp lớp**, không phải toàn bộ bộ máy thực thi Java.
- **Java class loader khác** (platform, application/system, class loader do người dùng tạo) phối hợp để nạp những lớp mà bootstrap loader không định nghĩa.

Sự phân biệt này quan trọng khi đọc `Class.getClassLoader()`, khi gặp `ClassNotFoundException`, khi thiết kế plugin, hoặc khi điều tra hai lớp **trùng tên** nhưng không thể ép kiểu cho nhau.

## 2. Tại sao JVM cần một bộ nạp lớp ở tầng bootstrap?

Một chương trình Java rất nhỏ cũng cần các định nghĩa kiểu nền tảng. Chẳng hạn:

```java
public class Hello {
    public static void main(String[] args) {
        System.out.println("Hello");
    }
}
```

Trong quá trình thực thi, JVM cần định nghĩa của `java.lang.Object`, `java.lang.Class`, `java.lang.String` và nhiều thành phần thư viện runtime liên quan. Nếu mọi class loader đều phải là một object Java do một class loader khác nạp trước, quá trình khởi động sẽ rơi vào vòng phụ thuộc: muốn tạo class loader đầu tiên lại phải có các lớp thiết yếu đã được nạp.

Bootstrap class loader giải quyết nhu cầu **khởi tạo hệ sinh thái kiểu ban đầu**. Trên các triển khai JVM phổ biến như HotSpot, bộ nạp này được triển khai ở tầng JVM/native và **không có một object `java.lang.ClassLoader` thông thường đại diện trực tiếp cho nó** trong API Java.

Điều đó lý giải tại sao:

```java
System.out.println(String.class.getClassLoader()); // null
```

Trên JDK 17 thông thường, dòng này in:

```text
null
```

Giá trị `null` là **quy ước API biểu thị bootstrap class loader**, không có nghĩa “lớp không được nạp” hay “JVM không dùng class loader”.

> Không gán `null` cho một class loader object rồi hiểu đó là một object tên BootstrapClassLoader. Trong Java API, null biểu thị tầng bootstrap ở những vị trí được tài liệu quy định.

## 3. Bootstrap, platform và application class loader trên JDK 17

Từ Java 9, hệ thống module (JPMS) thay đổi cách JDK tổ chức thư viện nền tảng. Trên JDK 17, ba tầng built-in class loader cần phân biệt là:

| Tầng | Vai trò điển hình | Quan sát trên Java 17 |
|---|---|---|
| **Bootstrap** | Định nghĩa những lớp nền tảng cốt lõi, bao gồm phần lớn các lớp trong `java.base` | `String.class.getClassLoader() == null` |
| **Platform** | Định nghĩa các lớp thuộc một số Java SE/JDK platform modules khác, theo ánh xạ module của runtime | `ClassLoader.getPlatformClassLoader()` |
| **Application / System** | Nạp lớp ứng dụng trên class path và các module ứng dụng tương ứng | `ClassLoader.getSystemClassLoader()` |

Đây là **mô hình hữu ích để học**, nhưng không phải luật “package `java.*` thuộc bootstrap, package khác thuộc application”. Ví dụ, không được suy rằng mọi class trong tất cả module `java.*` đều được bootstrap loader định nghĩa. Tầng nào định nghĩa class cụ thể phụ thuộc vào cấu hình runtime/module và cách JDK triển khai.

Các loader built-in của JDK 17 thường có quan hệ parent như sau:

```text
Bootstrap class loader
  (không có đối tượng ClassLoader thông thường)
                ^
                | parent ở cấp API biểu diễn bằng null
                |
Platform class loader
                ^
                |
Application / System class loader
                ^
                |
Custom ClassLoader thường dùng app loader làm parent
```

Mũi tên trên thể hiện **hướng delegation thông thường**, không phải quan hệ kế thừa Java (`extends`) của các class loader và cũng không có nghĩa JVM buộc mọi loader tùy biến phải tuân thủ một chính sách parent-first tuyệt đối.

**Mốc thay đổi theo phiên bản:**

- **JDK 8 và trước:** thường nói bootstrap loader tìm lớp lõi trong `rt.jar`/bootstrap class path, extension loader xử lý phần mở rộng, application loader xử lý class path.
- **JDK 9 trở đi:** không còn mô hình `rt.jar`/extension mechanism như cũ. JDK cung cấp runtime image và named modules; extension loader đã được thay bằng **platform class loader**. Vì vậy việc tìm `$JAVA_HOME/jre/lib/rt.jar` trên JDK 17 là kỳ vọng lỗi thời.
- **JDK 17:** các lớp nền tảng nằm trong runtime image của JDK, có thể được duyệt dưới dạng `jrt:/` qua công cụ và API thích hợp. Không được xem `jrt:/` là một đường dẫn file JAR vật lý thông thường.

Các lệnh hỗ trợ quan sát cấu trúc module trên JDK 17:

```bash
java --list-modules
java --describe-module java.base
```

Chúng in danh sách/chi tiết module của runtime hiện tại. Thông tin module **bổ sung** cho kiến thức class loader, không thay thế việc xác định defining loader thực tế của từng class.

## 4. Vai trò cụ thể của bootstrap loader trong cơ chế JVM

Một hình dung theo quá trình:

1. JVM được khởi động bởi chương trình launcher `java` và chuẩn bị runtime.
2. JVM cần các kiểu nền tảng để có thể định nghĩa, kiểm tra, liên kết và thực thi các class khác. Bootstrap loader đảm nhiệm việc định nghĩa tập kiểu cốt lõi tương ứng.
3. Khi cần một class ứng dụng, runtime sử dụng cơ chế loader phù hợp. Class loader ứng dụng thường phối hợp với parent loaders; nếu bootstrap có thể tìm và định nghĩa một class nền tảng được yêu cầu, ứng dụng sẽ dùng chung định nghĩa đó.
4. Khi đã có định nghĩa class, JVM tiếp tục xử lý **linking** (verification, preparation và resolution theo quy tắc) rồi **initialization** nếu cần, sau đó thực thi code.

Điều cần tránh: **loading không đồng nghĩa với initialization**. Nạp/định nghĩa `String` là hoạt động khác với chạy phần khởi tạo class khi một thao tác Java yêu cầu. Bootstrap class loader không thay thế các quy tắc verification, initialization, execution hay garbage collection của JVM.

### Class loader tìm và định nghĩa; JVM còn làm gì?

- **Loading:** tạo hoặc tìm một class/interface runtime từ dạng nhị phân thích hợp qua class loader.
- **Verification:** kiểm tra class file/bytecode theo quy tắc an toàn và cấu trúc JVM.
- **Preparation:** chuẩn bị static fields và giá trị ban đầu theo quy tắc VM.
- **Resolution:** đổi symbolic references thành tham chiếu runtime; JVM được phép làm một phần theo nhu cầu.
- **Initialization:** thực hiện `<clinit>` theo điều kiện kích hoạt initialization.
- **Execution:** trình thông dịch/JIT và runtime thực hiện phương thức/lệnh bytecode.
- **Garbage collection và class unloading:** quản lý khả năng thu hồi bộ nhớ, class metadata và các object khi đủ điều kiện.

**Bootstrap loader chủ yếu liên quan đến giai đoạn định nghĩa các lớp nền tảng.** Các giai đoạn tiếp theo thuộc ngữ nghĩa và cơ chế thực thi của JVM, áp dụng cho class bất kể defining loader nào.

## 5. Parent delegation: bootstrap đứng ở đâu?

Mô hình nạp lớp thông thường của `ClassLoader.loadClass(String)` trong Java có thể tóm tắt như sau:

```text
loadClass("com.example.Service")
          |
          v
Đã được nạp bởi loader này? -- Có --> trả Class<?> đã nạp
          |
         Chưa
          v
Đề nghị parent nạp (nếu parent == null: dùng bootstrap)
          |
          +-- Parent nạp thành công --> dùng định nghĩa parent trả về
          |
          +-- Parent không tìm thấy
                  |
                  v
            Loader hiện tại tự tìm/định nghĩa (findClass)
                  |
                  v
            Trả Class<?> hoặc ClassNotFoundException
```

Đây là thuật toán **mặc định điển hình** của `ClassLoader.loadClass`. Một class loader tùy biến có thể override `loadClass` để dùng chiến lược khác, và loader built-in ở hệ module có thể xử lý lookup theo ánh xạ module; không nên nói mọi class loader trên mọi JVM luôn tìm bootstrap trước mọi loại class trong mọi trường hợp.

### Vì sao thường ưu tiên parent?

Giả sử ứng dụng hoặc plugin chứa một file đặt tên `java/lang/String.class`. Không thể suy rằng vì file này nằm trên class path nên JVM sẽ dùng nó thay cho `java.lang.String` vốn đã được runtime định nghĩa. Cơ chế delegation, ràng buộc package/runtime và các quy tắc bảo vệ class/platform cùng tham gia ngăn việc tùy tiện giả mạo các lớp lõi.

Lợi ích thực tế:

- **Chia sẻ kiểu nền tảng:** đa số class ứng dụng cùng tham chiếu tới định nghĩa `java.lang.String` từ bootstrap, tránh vô tình tạo các kiểu lõi không tương thích.
- **Tính nhất quán:** các API ở các tầng khác nhau có thể truyền/nhận cùng runtime type của thư viện nền tảng.
- **Ranh giới tải lớp:** một loader ứng dụng không có quyền mặc nhiên thay thế hoặc định nghĩa lại namespace nền tảng chỉ bằng cách thêm một JAR.
- **Hỗ trợ cách ly:** class loader tùy biến có thể tách các kiểu do chính nó định nghĩa, nhưng thường vẫn chia sẻ nền tảng JVM với parent.

**Parent delegation không phải hệ thống bảo mật hoàn chỉnh.** Với Java hiện đại, class loader, JPMS, access checks và bytecode verification đảm nhiệm các chức năng riêng; không nên xem việc có parent-first đồng nghĩa ứng dụng đã được sandbox an toàn.

## 6. Danh tính runtime của class và ảnh hưởng của bootstrap loader

Trong JVMS, một class/interface runtime được xác định về danh tính bởi **binary name và defining class loader**. Chẳng hạn:

- `java.lang.String` do bootstrap loader định nghĩa là kiểu nền tảng dùng chung.
- `com.example.Plugin` do loader A định nghĩa có thể khác `com.example.Plugin` do loader B định nghĩa, dù bytecode hoặc binary name trùng nhau.
- Việc cả hai loại class đều dùng `java.lang.String` làm parameter không làm chúng tự động tương thích với nhau.

Phân biệt hai khái niệm:

- **Defining loader**: loader thực sự định nghĩa runtime class.
- **Initiating loader**: loader đã khởi xướng yêu cầu nạp class đó; có thể nhận về định nghĩa do parent thực hiện.

Ví dụ, application loader yêu cầu `java.lang.String` qua delegation; bootstrap loader cung cấp định nghĩa. Khi gọi `String.class.getClassLoader()`, ta thấy **defining loader** ở tầng bootstrap (biểu diễn `null`), dù thao tác khởi xướng có thể đến từ code ứng dụng.

Nếu một lớp do custom loader định nghĩa dùng field `String name`, bản thân field vẫn dùng định nghĩa `String` phù hợp từ bootstrap; custom loader không cần định nghĩa lại `java.lang.String`.

### Static state và class identity

Static fields gắn với từng runtime class identity. Với một class do loader A và loader B định nghĩa riêng, mỗi định nghĩa có thể có static state của chính nó. Ngược lại, `String` từ bootstrap là cùng một runtime class mà các tầng ứng dụng thường sử dụng; các instance thuộc kiểu nền tảng này không trở thành các kiểu khác chỉ vì nằm trong nhiều plugin.

## 7. Kiểm tra bootstrap loader bằng Java 17

Ví dụ sau sử dụng đúng API công khai, tránh in tên triển khai nội bộ có thể khác theo JDK.

Tạo file **`BootstrapLoaderDemo.java`**:

```java
public class BootstrapLoaderDemo {
    static class Sample { }

    public static void main(String[] args)
            throws ClassNotFoundException {

        ClassLoader app = BootstrapLoaderDemo.class.getClassLoader();
        ClassLoader platform = ClassLoader.getPlatformClassLoader();

        System.out.println("String bootstrap: "
                + (String.class.getClassLoader() == null));
        System.out.println("Object bootstrap: "
                + (Object.class.getClassLoader() == null));
        System.out.println("String[] bootstrap: "
                + (String[].class.getClassLoader() == null));

        System.out.println("Main class via app: "
                + (app == ClassLoader.getSystemClassLoader()));
        System.out.println("Nested class via app: "
                + (Sample.class.getClassLoader() == app));
        System.out.println("Platform parent is bootstrap: "
                + (platform.getParent() == null));
        System.out.println("App parent is platform: "
                + (app.getParent() == platform));

        Class<?> resolved = Class.forName(
                "java.lang.String", false, null);
        System.out.println("Bootstrap resolves String: "
                + (resolved == String.class));

        System.out.println("String module: "
                + String.class.getModule().getName());
    }
}
```

Biên dịch và chạy trong **cấu hình class path mặc định của JDK 17 HotSpot/OpenJDK phổ biến**, không dùng custom system class loader:

```bash
javac BootstrapLoaderDemo.java
java BootstrapLoaderDemo
```

Stdout:

```text
String bootstrap: true
Object bootstrap: true
String[] bootstrap: true
Main class via app: true
Nested class via app: true
Platform parent is bootstrap: true
App parent is platform: true
Bootstrap resolves String: true
String module: java.base
```

Giải thích:

1. `String`, `Object` thuộc lõi runtime và do bootstrap loader định nghĩa. `getClassLoader()` trả `null` cho các class đó.
2. `String[]` là **một array class runtime khác `String`**, nhưng array class của kiểu tham chiếu có defining loader tương ứng defining loader của component type; vì thế `String[].class.getClassLoader() == null`.
3. Class `BootstrapLoaderDemo` và nested class `Sample` được ứng dụng biên dịch/chạy từ class path và do loader ứng dụng mặc định định nghĩa.
4. `platform.getParent() == null` phản ánh việc platform loader có bootstrap loader làm parent theo quy ước API; `app.getParent() == platform` đúng cho chain built-in mặc định trong ví dụ.
5. `Class.forName("java.lang.String", false, null)` truyền **`null` ở tham số loader**: API dùng bootstrap loader cho yêu cầu này. `false` có nghĩa **không yêu cầu initialization**, không phải “không load”.
6. `String.class.getModule().getName()` in `java.base`, giúp xác nhận class thuộc module lõi.

Lưu ý về tính di động: class loader là thành phần có thể cấu hình hoặc tùy biến. Nếu dùng `-Djava.system.class.loader`, agent đặc biệt hoặc runtime khác, một số phép so sánh **app parent** có thể khác. Các phép so sánh ở ví dụ là bằng chứng cho **cấu hình đã nêu**, không phải cam kết cho mọi JVM có thể tồn tại.

### Tại sao `String[].class` cũng báo bootstrap?

Theo quy tắc JVM, với array có component type là reference type, defining loader của array gắn với defining loader của component type. Với array của primitive, chẳng hạn `int[]`, JVM tạo array class và không có component class do người dùng định nghĩa; `int[].class.getClassLoader()` cũng thường cho `null` trong Java. Đừng từ `null` suy ra có một file `int[].class` trong runtime image.

## 8. Parent bằng null không tạo ra một bootstrap loader mới

Một điểm dễ nhầm khi đọc Java API: constructor của `ClassLoader` chấp nhận `null` làm parent **không làm instance đó trở thành bootstrap loader**.

Tạo file **`BootstrapParentDemo.java`**:

```java
public class BootstrapParentDemo {
    public static void main(String[] args) throws Exception {
        ClassLoader isolated = new ClassLoader(null) { };

        System.out.println("Parent is null: "
                + (isolated.getParent() == null));

        Class<?> core = isolated.loadClass("java.lang.String");
        System.out.println("Delegated String: "
                + (core == String.class));

        try {
            isolated.loadClass("BootstrapParentDemo");
            System.out.println("Unexpectedly loaded app class");
        } catch (ClassNotFoundException expected) {
            System.out.println("Application class not visible");
        }
    }
}
```

Chạy từ class path thông thường bằng JDK 17:

```bash
javac BootstrapParentDemo.java
java BootstrapParentDemo
```

Stdout:

```text
Parent is null: true
Delegated String: true
Application class not visible
```

Đây là một **đối tượng class loader mới**, subclass ẩn danh của `ClassLoader`, có parent API là `null`. Nó có thể nhờ bootstrap nạp `String`, nhưng mặc định không có cơ chế `findClass` tùy chỉnh để tìm file `BootstrapParentDemo.class` trên class path. Do vậy lời gọi nạp class ứng dụng thất bại trong môi trường đã mô tả.

Điểm cần nhớ: **bootstrap loader không phải một instance tạo bằng `new ClassLoader(null)`**; instance đó chỉ **ủy quyền tới bootstrap** khi parent bằng `null`.

Muốn nạp class ứng dụng, custom loader phải có chiến lược nạp thích hợp: được gán parent phù hợp, hoặc tự implement việc tìm/định nghĩa các class mà nó quản lý. Không tùy tiện dùng `new ClassLoader(null)` như “phương án cô lập an toàn” vì lỗi visibility và module access có thể phát sinh.

## 9. Bootstrap loader có tự khởi tạo mọi lớp nó nạp không?

**Không.** Cần tách rõ ba bước thường bị trộn:

1. **Loading**: class runtime được tìm/định nghĩa bởi loader.
2. **Linking**: JVM kiểm tra và chuẩn bị, resolve tham chiếu theo nhu cầu.
3. **Initialization**: JVM chạy `<clinit>` khi có điều kiện active use thích hợp.

Một class có defining loader là bootstrap **không có nghĩa** bootstrap trực tiếp điều khiển thời điểm static initializer của nó chạy; initialization tuân theo JVM/JLS và phụ thuộc cách class được sử dụng.

Tương tự với class ứng dụng:

```java
Class<?> c = Class.forName(
        "com.example.SomeType", false, loader);
```

Giá trị `false` có ý nghĩa trì hoãn việc yêu cầu initialization. Nếu về sau chương trình dùng `new SomeType()`, truy cập một static field không phải compile-time constant, gọi static method hoặc thao tác khác kích hoạt initialization, JVM mới phải khởi tạo theo quy tắc.

Sự phân biệt giúp tránh tác dụng phụ khi chỉ quét metadata của class. Ví dụ, công cụ phân tích class path hoặc hệ thống plugin có thể cần biết class có tồn tại trước khi cho phép static initializer thực thi.

## 10. Bootstrap loader, platform module và runtime image

### Không dùng mô hình `rt.jar` cho Java 17

Trên JDK 8, tài liệu thường minh họa bootstrap class loader đọc lõi Java từ `rt.jar`. Cách giải thích đó **phụ thuộc phiên bản**. Từ JDK 9, modular runtime image thay cách đóng gói thư viện. JDK 17 cung cấp các module của runtime, trong đó `java.base` là module bắt buộc chứa các API cơ bản.

Bạn có thể xem chi tiết trực tiếp:

```bash
java --describe-module java.base
```

Các tool và provider phù hợp có thể hiển thị tài nguyên trong runtime bằng URL dạng `jrt:/java.base/...`. Đó là một **URI scheme của runtime image**, không phải lời khẳng định rằng tất cả class được Java đọc từ một JAR tên `jrt.jar`.

### Không phải mọi class JDK đều được bootstrap nạp

Ví dụ `java.lang.String` trong `java.base` thuộc bootstrap. Nhưng JDK còn những module Java SE và module công cụ/triển khai khác, có thể được gán cho bootstrap, platform hoặc application loader tùy cấu hình. Đừng lập bảng phân loại chỉ dựa theo tiền tố package `java.`, `javax.`, `jdk.` hoặc theo tên module đoán chừng.

Khi cần kết luận trong chương trình cụ thể, hãy kiểm tra **actual runtime class**:

```java
Class<?> type = Class.forName("java.lang.String");
ClassLoader definingLoader = type.getClassLoader();
Module module = type.getModule();
```

Đây là đoạn **minh họa** cần nằm trong một method có khai báo/khử `ClassNotFoundException`. `definingLoader == null` nghĩa class do bootstrap định nghĩa. `module.getName()` cung cấp tên named module nếu có, nhưng **module name và class loader là hai thuộc tính khác nhau**.

### Không thay thế thư viện lõi bằng cách đưa JAR lên đầu class path

Thêm một JAR chứa bytecode trùng tên class lõi vào class path không phải phương pháp hợp lệ để “override `java.lang.String`”. JDK áp dụng cơ chế loader/module/package và các ràng buộc JVM tương ứng.

Có những tùy chọn JVM dành cho **instrumentation, patching, nghiên cứu nội bộ** như patch module hoặc bootstrap class path append trên một số JVM; chúng có điều kiện, giới hạn riêng và **không có nghĩa có thể tùy ý ghi đè mọi class của `java.base`**. Khi làm việc với JDK 17, hãy đọc tài liệu chính xác của VM và tùy chọn mình dùng thay vì bê nguyên hướng dẫn `-Xbootclasspath/p` thời JDK 8.

## 11. Class loader không đồng nghĩa với mọi cơ chế bảo vệ JVM

Bootstrap loader thường được giải thích cùng các lợi ích “an toàn” vì nó giúp lớp nền tảng dùng chung không bị ứng dụng thay tùy tiện. Tuy nhiên cần hiểu đúng ranh giới:

- **Bytecode verification** thuộc cơ chế kiểm tra tính hợp lệ class file của JVM, không đơn giản là “bootstrap duyệt bytecode rồi cho chạy”.
- **Access control** (`public`, `protected`, package access, module exports/opens, nestmates...) thực hiện theo ngữ nghĩa Java/JVM; loader identity có tác động tới runtime package và khả năng tương thích kiểu.
- **JPMS** quy định readability, exports, opens giữa các module; “do bootstrap định nghĩa” không có nghĩa code ở mọi module được phép truy cập mọi internal API của lớp đó.
- **Security Manager** không phải cơ chế được khuyến nghị để sandbox code không tin cậy trên Java hiện đại. Đừng cho rằng parent delegation đủ để cô lập bytecode độc hại.

Vì vậy, cần dùng class loader để hiểu **visibility, identity, delegation**, dùng các cơ chế API/module/runtime khác cho các yêu cầu truy cập, kiểm tra và cô lập phù hợp.

## 12. Lỗi thực tế và cách điều tra

### Lỗi 1: “`getClassLoader() == null` nghĩa class chưa load”

Sai. Với `String.class`, `null` chính là dấu hiệu defining loader được API biểu diễn là bootstrap. Class đã có mặt và `Class<?>` đang đại diện cho runtime type đó.

### Lỗi 2: “Cứ tên bắt đầu bằng `java.` là bootstrap”

Sai. Tập module của JDK hiện đại rộng hơn `java.base`; phải kiểm tra defining loader và module mapping thực tế. Ngoài ra JDK cấm nhiều cách định nghĩa sai lớp thuộc namespace hệ thống.

### Lỗi 3: “Bootstrap loader chính là `ClassLoader.getSystemClassLoader()`”

Sai. `ClassLoader.getSystemClassLoader()` trả về system/application loader, thường dùng cho ứng dụng. `ClassLoader.getPlatformClassLoader()` trả platform loader. Bootstrap loader không được trả về như một object `ClassLoader` bình thường.

### Lỗi 4: “Parent bằng null là không có cơ chế delegation”

Sai. Trong contract mặc định của `ClassLoader`, parent `null` làm delegation tới bootstrap. Ví dụ `BootstrapParentDemo` cho thấy chính điểm này.

### Lỗi 5: “Application loader và bootstrap định nghĩa hai bản `String`”

Trong chương trình JDK 17 thông thường, các loader khác ủy quyền/được cấu hình để dùng định nghĩa `String` chung từ bootstrap. Không suy rằng mỗi loader giữ một bản class lõi riêng. Khả năng định nghĩa cùng tên ở hai custom loaders chủ yếu liên quan tới class ứng dụng/namespace được phép.

### Lỗi 6: “Bị `ClassNotFoundException` tức bootstrap bị hỏng”

Không đúng. `ClassNotFoundException` có thể đến từ việc loader được yêu cầu không nhìn thấy class/path/module tương ứng. Một custom loader parent-null như ví dụ chỉ thấy bootstrap và những gì nó tự định nghĩa; việc không thấy `BootstrapParentDemo` từ class path không phải dấu hiệu JVM hỏng.

Các lỗi liên quan khác:

- `NoClassDefFoundError` có thể xuất hiện khi class cần lúc linking/runtime không tìm được hoặc initialization trước đó thất bại; tên lỗi không chứng minh bootstrap loader bị lỗi.
- `ClassCastException` giữa hai class cùng tên có thể liên quan hai **defining loaders** khác nhau.
- `LinkageError` có thể phản ánh sai khác không tương thích trong quá trình loading/linking/resolution. Cần xem stack trace đầy đủ, không chỉ dòng đầu.

### Quy trình chẩn đoán ngắn

1. Ghi lại **binary name chính xác** của kiểu, ví dụ `com.example.Plugin`, kèm cách program gọi loader.
2. Kiểm tra `clazz.getClassLoader()`, `clazz.getModule()` và `clazz.getProtectionDomain()` ở nơi hợp lệ, tránh giả định dựa trên tên package. `getProtectionDomain()` có thể có cấu hình/quyền truy cập khác nhau và không phải luôn cần thiết.
3. Kiểm tra parent chain và module/class path của loader **đang thực sự được gọi**.
4. Nếu có hai `Class<?>`, so sánh trực tiếp `classA == classB`; nếu false, xem defining loader của từng class.
5. Với HotSpot, dùng log loading, nhưng phân biệt **dòng class được load** với **dòng class được initialized**.

Lệnh logging class loading trên HotSpot JDK 17:

```bash
java -Xlog:class+load=info BootstrapLoaderDemo
```

Log có thể rất dài vì JDK và thư viện tải nhiều class. Chạy với và không chạy ứng dụng để điều tra đường nạp lớp, tránh kết luận sai khi chỉ nhìn log không có thông tin class initialization.

## 13. Bài tập tự kiểm tra

**Câu 1.** `String.class.getClassLoader()` trả `null` trên JDK 17 thông thường. Điều đó có ý nghĩa gì?

**Đáp án:** `String` được định nghĩa bởi bootstrap class loader; API dùng `null` để biểu diễn defining loader này, không có nghĩa không có class.

**Câu 2.** Trên JDK 17, tìm mã `java.lang.String` ở `rt.jar` có đúng cách không?

**Đáp án:** Không. Từ Java 9, runtime được tổ chức thành module image; `java.lang.String` thuộc `java.base`. Mô hình `rt.jar` là đặc trưng tài liệu/hệ JDK trước đây.

**Câu 3.** Nếu class ứng dụng có field `java.lang.String title`, nó có cần tự định nghĩa `String` không?

**Đáp án:** Không. Loader ứng dụng thường dùng định nghĩa `String` từ bootstrap qua cơ chế phù hợp; JVM xác định kiểu theo runtime class identity.

**Câu 4.** `ClassLoader.getPlatformClassLoader().getParent() == null` có nghĩa platform loader không còn parent?

**Đáp án:** Ở cấp API Java, `null` biểu thị bootstrap; platform loader có thể dùng bootstrap làm parent theo cơ chế này.

**Câu 5.** Hai custom class loader định nghĩa `com.example.Widget` riêng biệt. Hai runtime classes có bằng nhau không?

**Đáp án:** Không, nếu defining loader khác nhau. Binary name bằng nhau là chưa đủ; `Widget.class` của hai định nghĩa khác nhau không có cùng runtime identity.

**Câu 6.** Vì sao `new ClassLoader(null) {}` không phải “khởi tạo lại bootstrap class loader”?

**Đáp án:** Nó tạo **một object loader Java riêng** có parent được biểu diễn bằng `null`. Loader đó có thể ủy quyền cho bootstrap nhưng không trở thành cơ chế bootstrap của JVM.

**Câu 7.** Nạp `java.lang.String` qua bootstrap đã đồng nghĩa “JVM chạy constructor của một đối tượng `String`” chưa?

**Đáp án:** Chưa. Class loading/initialization là chuyện của định nghĩa lớp; object construction là chuyện của từng instance cụ thể. JVM có thể định nghĩa một lớp mà không thực thi constructor để tạo một object của chính lớp đó.

## 14. Ghi nhớ và tài liệu chuẩn

- **Bootstrap** là tầng định nghĩa các lớp lõi; ở Java API, `getClassLoader() == null` thường biểu thị defining loader bootstrap.
- **JVM** là hệ thống rộng hơn, thực hiện linking, initialization, bytecode execution, quản lý bộ nhớ và nhiều hoạt động khác.
- **JDK 17:** dùng runtime module image, có các tầng bootstrap/platform/application; đừng đồng nhất với mô hình `rt.jar` và extension loader của JDK 8.
- **Loader identity:** runtime class identity phụ thuộc cả binary name và defining class loader. Delegation giúp class ứng dụng dùng chung lõi runtime.
- **Kiểm tra thực nghiệm:** dùng `Class.getClassLoader()`, `getModule()` và ``Class.forName(name, false, null)`` để hiểu từng trường hợp theo đúng API.

Tài liệu chính thức:

1. [Java Virtual Machine Specification 17, §5 — Loading, Linking, and Initializing](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html).
2. [Java SE 17 — `java.lang.ClassLoader`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html): parent delegation, `loadClass`, platform/system loader.
3. [Java SE 17 — `java.lang.Class`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html): `getClassLoader()`, `forName`, `getModule()`.
4. [JEP 261 — Module System](https://openjdk.org/jeps/261): hệ module và hành vi built-in loaders từ Java 9.
5. [JEP 220 — Modular Run-Time Images](https://openjdk.org/jeps/220): thay đổi tổ chức runtime image và mô hình `rt.jar`.