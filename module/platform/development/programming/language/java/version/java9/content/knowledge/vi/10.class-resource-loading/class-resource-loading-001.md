# Vai trò bootstrap, platform và application class loader

Trong Java hiện đại, ba class loader dựng sẵn tạo thành hệ thống phân cấp chính để nạp lớp của JVM và ứng dụng: **bootstrap**, **platform** và **application**. Mỗi loader có phạm vi trách nhiệm riêng, đồng thời ủy quyền cho loader cha theo cơ chế delegation mặc định.

Hiểu đúng vai trò của chúng giúp xác định một class được nạp từ đâu, xử lý lỗi không tìm thấy class, cấu hình thư viện trên classpath/module path và tích hợp framework hoặc plugin. Từ Java 9, platform class loader đảm nhiệm vai trò nền tảng trong kiến trúc mới; các hướng dẫn dựa vào extension loader và thư mục extension cũ không còn phù hợp.

## 1. Bức tranh tổng thể

Với cấu hình mặc định của Java launcher, quan hệ cha-con của các built-in class loader là:

~~~text
Bootstrap Class Loader
        |
        v
Platform Class Loader
        |
        v
Application (System) Class Loader
        |
        v
Các class loader tùy chỉnh của ứng dụng (nếu có)
~~~

Đọc sơ đồ từ dưới lên để hiểu chiều delegation: application loader thường hỏi platform loader trước; platform loader có thể hỏi bootstrap loader. Bootstrap loader là gốc của chuỗi và được JVM xử lý đặc biệt.

| Class loader | Vai trò chính | Ví dụ class thường được nạp |
|---|---|---|
| **Bootstrap** | Nạp các lớp lõi của runtime, đặc biệt các lớp thuộc **java.base** | **java.lang.String**, **java.util.List** |
| **Platform** | Nạp các lớp nền tảng Java nằm ngoài phần lõi do bootstrap nạp | **java.sql.Driver**, **javax.xml.parsers.DocumentBuilder** |
| **Application/System** | Nạp class và resource của ứng dụng từ classpath; thường cũng nạp các application module trên module path | **Main**, class trong thư viện ứng dụng |

Đây là cách phân chia điển hình của runtime mặc định. Ứng dụng có thể tạo class loader riêng hoặc dùng system class loader tùy chỉnh, nên khi chẩn đoán một tiến trình cụ thể hãy kiểm tra loader thực tế thay vì chỉ suy luận từ tên class.

## 2. Bootstrap Class Loader

Bootstrap class loader là loader gốc, do JVM/runtime triển khai. Nó nạp các lớp thiết yếu để Java có thể khởi động và thực thi, trong đó có phần lớn lớp thuộc module lõi **java.base**.

Ví dụ quen thuộc:

- **java.lang.Object**
- **java.lang.String**
- **java.lang.Class**
- **java.util.List**
- **java.io.InputStream**

Có thể kiểm tra loader định nghĩa một class bằng:

~~~java
System.out.println(String.class.getClassLoader());
~~~

Kết quả:

~~~text
null
~~~

Giá trị **null** có ý nghĩa đặc biệt: class được định nghĩa bởi bootstrap loader. Nó **không** có nghĩa class không được nạp bởi class loader. Bootstrap loader không được biểu diễn như một đối tượng **ClassLoader** Java thông thường, vì vậy API trả về **null** cho trường hợp này.

Không nên gọi phương thức trên kết quả **getClassLoader()** mà không kiểm tra **null**. Nếu cần hiển thị tên loader, hãy xử lý bootstrap riêng:

~~~java
static String loaderName(ClassLoader loader) {
    return loader == null ? "bootstrap" : loader.getName();
}
~~~

Bootstrap loader là cha của platform loader. Khi **platform.getParent()** trả về **null**, điều đó biểu thị parent là bootstrap loader; không phải platform loader bị tách khỏi hệ thống phân cấp.

## 3. Platform Class Loader

Platform class loader được cung cấp từ Java 9. Nó nạp các lớp thuộc nền tảng Java mà không do bootstrap loader nạp, ví dụ các lớp trong một số module Java SE như **java.sql** và **java.xml**.

Có thể lấy loader này bằng API:

~~~java
ClassLoader platform = ClassLoader.getPlatformClassLoader();
~~~

Ví dụ, trên runtime mặc định, **java.sql.Driver** được định nghĩa bởi platform loader:

~~~java
System.out.println(java.sql.Driver.class.getClassLoader().getName());
~~~

Kết quả trên JDK được dùng để kiểm tra bài này:

~~~text
platform
~~~

Platform loader nằm giữa bootstrap và application loader. Nó cho phép ứng dụng phụ thuộc vào các API nền tảng theo module graph của runtime mà không cần đưa các lớp Java platform vào classpath ứng dụng.

Một điểm quan trọng: platform loader không phải loader dành cho thư viện bên thứ ba nói chung. Thư viện ứng dụng thường được nạp bởi application loader nếu nằm trên classpath hoặc thuộc application module được giao cho loader này.

Trong Java 9, platform loader thay thế vai trò của extension class loader trong cấu trúc built-in. Khi cấu hình ứng dụng hiện nay, hãy dùng classpath, module path hoặc class loader tùy chỉnh có chủ đích; không dựa vào thư mục extension cũ hay thuộc tính **java.ext.dirs**.

## 4. Application Class Loader và System Class Loader

Application class loader là loader mặc định dành cho mã ứng dụng. API chuẩn lấy loader này là:

~~~java
ClassLoader application = ClassLoader.getSystemClassLoader();
~~~

Trong cấu hình Java launcher mặc định, system class loader chính là application class loader. Nó thường nạp:

- Class của ứng dụng được đặt trên classpath (**-cp** hoặc **--class-path**).
- Thư viện ứng dụng trên classpath.
- Application module được runtime giao cho system/application loader khi khởi động bằng module path.

Ví dụ, nếu **Main** là class đang chạy từ thư mục output trên classpath:

~~~java
System.out.println(Main.class.getClassLoader().getName());
~~~

Kết quả trên JDK được dùng để kiểm tra:

~~~text
app
~~~

Tên **app** là tên loader mặc định trong runtime đã kiểm tra. Trong ứng dụng có custom system class loader, tên và hành vi có thể khác.

**ClassLoader.getSystemClassLoader()** là API lấy system loader, không phải API để lấy mọi loader đang tồn tại. Nếu ứng dụng tạo plugin loader, loader đó cần được giữ và quản lý riêng.

## 5. Delegation: class loader ủy quyền cho parent

Cơ chế delegation mặc định giúp tránh nạp trùng các lớp lõi và giữ một định nghĩa class thống nhất trong chuỗi loader.

Khi một loader nhận yêu cầu nạp class, quy trình chuẩn của **ClassLoader.loadClass** về cơ bản là:

1. Kiểm tra class đã được loader đó nạp trước đó chưa.
2. Nếu có parent, yêu cầu parent nạp class trước.
3. Nếu parent không tìm thấy class, loader hiện tại mới tìm class bằng cơ chế **findClass**.
4. Nếu vẫn không tìm thấy, ném **ClassNotFoundException**.

Ví dụ, application loader cần class **java.lang.String**. Nó ủy quyền lên platform loader; platform loader tiếp tục ủy quyền lên bootstrap loader. Bootstrap loader tìm thấy class lõi và kết quả được dùng trong toàn bộ chuỗi.

Cách làm này thường được gọi là **parent-first delegation**. Nó giảm nguy cơ thư viện ứng dụng vô tình thay thế các class nền tảng có cùng tên.

Lớp **ClassLoader** cung cấp các điểm mở rộng như **findClass** và **findResource**. Khi xây dựng loader riêng, thường nên tùy chỉnh việc tìm class trong **findClass** và giữ cơ chế parent delegation mặc định. Chỉ override **loadClass** khi thực sự cần chính sách khác, chẳng hạn child-first cho một plugin cô lập; thay đổi thứ tự có thể gây xung đột kiểu hoặc nạp nhầm phiên bản thư viện.

## 6. Kiểm tra class loader tại runtime

Một số API thường dùng:

| API | Ý nghĩa |
|---|---|
| **Class.getClassLoader()** | Loader đã định nghĩa class đó; trả về **null** nếu là bootstrap |
| **ClassLoader.getPlatformClassLoader()** | Lấy platform loader |
| **ClassLoader.getSystemClassLoader()** | Lấy system/application loader mặc định |
| **ClassLoader.getParent()** | Lấy parent; **null** biểu thị bootstrap loader |
| **ClassLoader.getName()** | Lấy tên loader nếu có |
| **ClassLoader.loadClass(name)** | Yêu cầu loader nạp class theo tên |
| **Class.forName(name, initialize, loader)** | Tìm class bằng loader chỉ định và quyết định có khởi tạo class hay không |
| **Class.getModule()** | Xem module chứa class, giúp phân biệt module với loader |

Không nhầm **Class.getClassLoader()** với **Thread.currentThread().getContextClassLoader()**. API đầu tiên trả về loader đã định nghĩa class; API thứ hai trả về context loader của thread, thường được framework sử dụng để tìm class hoặc service theo ngữ cảnh của ứng dụng.

## 7. Ví dụ hoàn chỉnh: quan sát ba built-in class loader

Ví dụ sau dùng ba class đại diện: **String** thuộc phần lõi, **Driver** thuộc module nền tảng **java.sql**, và **Main** thuộc ứng dụng. Chương trình cũng kiểm tra quan hệ parent của platform và application loader.

**Tệp Main.java:**

~~~java
import java.sql.Driver;

public class Main {
    private static String name(ClassLoader loader) {
        return loader == null ? "bootstrap" : loader.getName();
    }

    public static void main(String[] args) {
        ClassLoader platform = ClassLoader.getPlatformClassLoader();
        ClassLoader application = ClassLoader.getSystemClassLoader();

        System.out.println("String: " + name(String.class.getClassLoader()));
        System.out.println("Driver: " + name(Driver.class.getClassLoader()));
        System.out.println("Main: " + name(Main.class.getClassLoader()));
        System.out.println("Platform parent is bootstrap: " + (platform.getParent() == null));
        System.out.println("Application parent is platform: " + (application.getParent() == platform));
    }
}
~~~

Biên dịch bằng JDK 17 trở lên:

~~~bash
javac --release 17 -d out Main.java
java -cp out Main
~~~

Kết quả trên JDK 24:

~~~text
String: bootstrap
Driver: platform
Main: app
Platform parent is bootstrap: true
Application parent is platform: true
~~~

Các tên loader và quan hệ parent trên tương ứng với built-in loader của Java launcher mặc định. Nếu ứng dụng dùng custom system loader hoặc môi trường khởi chạy đặc biệt, hãy đọc kết quả runtime thực tế.

## 8. Class loader và Java Module System là hai khái niệm khác nhau

Class loader và module có liên hệ nhưng không đồng nhất:

- **Class loader** chịu trách nhiệm tìm, nạp và định nghĩa class/resource.
- **Module** gom package, khai báo dependency và xác định package nào được export hoặc mở cho reflection.
- Một class đã được nạp có thể được kiểm tra module qua **SomeClass.class.getModule()**.
- Một class loader có thể định nghĩa nhiều module; module không nhất thiết tương ứng một class loader riêng.

Ví dụ, một named module có thể được nạp bởi application loader nhưng vẫn giữ package không export. Việc class đã được nạp thành công không có nghĩa mọi module khác đều được phép truy cập kiểu trong package đó. Quy tắc readability, exports và opens của JPMS vẫn áp dụng.

Mỗi class loader cũng có unnamed module riêng cho các class không thuộc named module do loader đó định nghĩa. Vì vậy, không nên suy luận rằng mọi class trên classpath của mọi loader đều thuộc cùng một unnamed module.

Khi debug, có thể in cả loader và module:

~~~java
Class<?> type = Main.class;
System.out.println("Loader: " + type.getClassLoader());
System.out.println("Module: " + type.getModule());
~~~

Điều này giúp phân biệt lỗi do không tìm thấy class với lỗi do module không đọc module khác hoặc package chưa được export.

## 9. Context Class Loader và framework

Một số framework cần nạp class do ứng dụng hoặc plugin cung cấp, trong khi chính framework có thể được nạp bởi loader khác. Để hỗ trợ tình huống này, Java có **thread context class loader (TCCL)**.

Lấy context loader hiện tại:

~~~java
ClassLoader contextLoader = Thread.currentThread().getContextClassLoader();
~~~

Đặt context loader khi có lý do rõ ràng:

~~~java
Thread thread = Thread.currentThread();
ClassLoader previous = thread.getContextClassLoader();

try {
    thread.setContextClassLoader(pluginLoader);
    // Thực hiện thao tác mà framework cần tìm class/service qua context loader.
} finally {
    thread.setContextClassLoader(previous);
}
~~~

TCCL không thay đổi loader đã định nghĩa class hiện tại. Nó là một tham chiếu theo thread để API hoặc framework có thể dùng loader phù hợp với ngữ cảnh gọi.

**ServiceLoader.load(Service.class)** thường sử dụng context class loader của thread hiện tại. Khi chạy trong môi trường plugin, application server hoặc module layer riêng, hãy xác định loader/layer cần dùng và cân nhắc overload tường minh của **ServiceLoader** để tránh phụ thuộc nhầm context loader.

Nếu thay đổi TCCL, hãy khôi phục giá trị cũ trong **finally**; nếu không, thread được tái sử dụng trong thread pool có thể mang context loader của tác vụ trước và gây rò rỉ class loader hoặc nạp nhầm service.

## 10. Class identity, plugin và lỗi thường gặp

Trong JVM, identity của một class không chỉ dựa vào tên đầy đủ. Class được xác định bởi **binary name và defining class loader**. Hai loader khác nhau có thể định nghĩa hai class cùng tên nhưng JVM xem chúng là hai kiểu khác nhau.

Điều này giải thích một số lỗi thường gặp khi dùng plugin:

| Triệu chứng | Nguyên nhân thường gặp | Hướng xử lý |
|---|---|---|
| **ClassNotFoundException** | Loader được yêu cầu không tìm thấy tên class | Kiểm tra classpath/module path và loader thực sự dùng để tìm class |
| **NoClassDefFoundError** | Class cần thiết không có sẵn lúc liên kết/khởi tạo, hoặc lần nạp trước thất bại | Kiểm tra nguyên nhân gốc, dependency và log khởi tạo |
| **ClassCastException** dù hai class có cùng tên | Hai bản class được định nghĩa bởi hai loader khác nhau | Chia sẻ API type qua loader cha chung; tránh đóng gói trùng API trong plugin |
| **LinkageError** | Xung đột phiên bản, class trùng tên hoặc chữ ký không tương thích giữa các loader | Kiểm tra thứ tự delegation và nguồn class được nạp |
| Framework không tìm thấy service/plugin | Context loader hoặc module layer không đúng | Kiểm tra TCCL, **ServiceLoader** overload và module layer |
| Class nền tảng bị nạp từ thư viện ứng dụng | Loader tùy chỉnh dùng delegation khác thường hoặc đóng gói class thuộc JDK | Không đóng gói class Java platform; giữ parent delegation mặc định |

Khi thiết kế plugin, hãy xác định rõ API nào được chia sẻ từ parent loader và dependency nào được cô lập trong plugin loader. Nếu mỗi plugin tự nạp một bản riêng của interface dùng để trao đổi object, cast giữa hai phía có thể thất bại dù tên interface giống nhau.

Class loader không tự tạo ra ranh giới bảo mật hoàn chỉnh. Không nên dùng việc tách loader như cơ chế duy nhất để chạy mã không tin cậy; hãy dùng ranh giới tiến trình và cơ chế cô lập phù hợp với yêu cầu bảo mật.

## 11. Lưu ý khi phát triển và vận hành trên JDK hiện đại

- **Dùng đúng classpath/module path:** classpath thường được system/application loader xử lý; named module được resolve từ module path và gắn với loader theo cấu hình module layer.
- **Không dựa vào extension directory cũ:** từ Java 9, platform loader đảm nhiệm vai trò nền tảng trong kiến trúc mới. Cấu hình **jre/lib/ext** và **java.ext.dirs** không phải cách triển khai thư viện hiện hành.
- **Không giả định mọi class Java đều do bootstrap nạp:** một số module Java platform được platform loader nạp. Hãy kiểm tra **getClassLoader()** khi cần biết chính xác.
- **Không giả định mọi class ứng dụng đều do application loader nạp:** custom loader, plugin framework và module layer riêng có thể định nghĩa class bằng loader khác.
- **Giữ một nguồn API chung:** với plugin, interface trao đổi giữa host và plugin nên được nạp bởi loader cha chung để tránh lỗi identity.
- **Quản lý vòng đời loader:** tham chiếu tĩnh, thread, TCCL, thread local hoặc cache giữ class từ plugin có thể ngăn loader được thu hồi sau khi plugin dừng.
- **Chỉ khởi tạo class khi cần:** **loadClass** và **Class.forName** có overload với hành vi khởi tạo khác nhau. Không nên nhầm việc nạp/định nghĩa class với chạy static initializer.
- **Ghi lại bằng chứng runtime:** khi chẩn đoán, in tên class, **getClassLoader()** và **getModule()** để xác định nguồn định nghĩa thay vì chỉ nhìn tên JAR.

## 12. Checklist khi chẩn đoán class loader

- [ ] Đã xác định class đang lỗi và binary name chính xác.
- [ ] Đã kiểm tra loader định nghĩa class bằng **Class.getClassLoader()**.
- [ ] Đã xử lý **null** như dấu hiệu bootstrap loader.
- [ ] Đã kiểm tra parent chain qua **getParent()**.
- [ ] Đã phân biệt system/application loader với platform loader.
- [ ] Đã kiểm tra class nằm trên classpath hay module path.
- [ ] Đã kiểm tra module bằng **Class.getModule()** nếu lỗi liên quan JPMS.
- [ ] Đã kiểm tra context class loader nếu framework hoặc ServiceLoader không tìm thấy plugin.
- [ ] Đã kiểm tra class trùng tên được định nghĩa bởi nhiều loader.
- [ ] Đã khôi phục TCCL và giải phóng tham chiếu tới plugin loader khi tác vụ kết thúc.

## 13. Tài liệu tham khảo

- [Java SE 25 API — ClassLoader](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/ClassLoader.html)
- [Java SE 25 API — Class](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Class.html)
- [Java SE 25 API — Thread context class loader](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Thread.html)
- [Java SE 25 API — ServiceLoader](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/ServiceLoader.html)
- [Java Language Specification — Loading, Linking, and Initializing, Chapter 12](https://docs.oracle.com/javase/specs/jls/se17/html/jls-12.html)
- [JEP 261 — Module System](https://openjdk.org/jeps/261)
