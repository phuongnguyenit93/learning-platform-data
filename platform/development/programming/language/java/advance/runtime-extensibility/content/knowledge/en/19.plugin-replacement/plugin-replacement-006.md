# Đóng URLClassLoader giải phóng tệp nhưng không hủy lớp đã nạp

## 1. Vấn đề khi thay thế plugin trong một JVM

Một host Java có thể tạo `URLClassLoader` để nạp một plugin từ JAR, gọi mã của plugin, rồi thay thế plugin bằng bản mới. Khi dừng plugin cũ, host nên gọi `URLClassLoader.close()` để đóng các file được loader mở. Nhưng **đóng classloader không có nghĩa xóa class khỏi JVM hoặc vô hiệu hóa mọi đối tượng đã tạo từ class ấy**.

Đây là sự khác biệt quan trọng giữa hai khái niệm:

- **Giải phóng tài nguyên I/O:** đóng các file/JAR handle mà `URLClassLoader` đã mở, để không tiếp tục giữ những tài nguyên đó vô thời hạn. Việc có thể đổi tên, xóa hoặc thay file trên đĩa vẫn phụ thuộc hệ điều hành, quyền truy cập và những tiến trình/stream khác đang dùng file.
- **Class unloading:** JVM chỉ có thể thu hồi các lớp được định nghĩa bởi một classloader khi các điều kiện về khả năng thu hồi, tham chiếu và garbage collection được thỏa mãn. Gọi `close()` không ép quá trình này xảy ra tức thì.

Theo hợp đồng Java SE 17, sau `close()`, loader không thể định nghĩa thêm **lớp hoặc resource mới do chính nó cung cấp**. Các lớp/resource đã nạp và những thứ đến từ parent loader vẫn có thể truy cập. Nếu một thread khác đang nạp lớp cùng lúc với `close()`, kết quả của lượt nạp đó là **không xác định**, nên host phải tự đồng bộ vòng đời.

Bài này hướng dẫn hiểu đúng `close()`, viết chương trình Java 17 quan sát việc đối tượng cũ vẫn hoạt động, phân biệt hai phiên bản cùng tên class và tổ chức thay thế plugin không rò rỉ file handle, thread hoặc tham chiếu tới loader cũ.

## 2. URLClassLoader thực sự quản lý những gì?

`java.net.URLClassLoader` là một classloader biết tìm lớp và tài nguyên từ danh sách URL, thường là:

- URL của một **JAR**: `file:/.../plugin-v1.jar`.
- URL của thư mục chứa `.class` đã biên dịch: `file:/.../classes/`, thường kết thúc bằng dấu `/`.
- Một đường tìm kiếm có nhiều URL theo thứ tự chỉ định, sau khi đã xét parent trong mô hình delegation mặc định.

Cách tạo loader điển hình:

~~~java
// Đoạn minh họa: giả sử jarPath đã là Path tới JAR tồn tại.
URLClassLoader loader = new URLClassLoader(
        new URL[]{jarPath.toUri().toURL()},
        HostApp.class.getClassLoader()
);
~~~

`jarPath` và `HostApp` trong đoạn này chỉ là ký hiệu minh họa; ví dụ đầy đủ ở mục 5 có file thật và lệnh chạy. Loader có thể mở `JarFile` khi tìm lớp hoặc resource. Việc tạo đối tượng `URLClassLoader` không đồng nghĩa tất cả JAR đã được mở hay mọi class đã được tải.

### 2.1. close() làm gì?

`URLClassLoader` triển khai `Closeable` và `AutoCloseable`, vì vậy có thể đóng bằng `try-with-resources`. Theo API Java 17:

1. `close()` ngừng việc tìm/nạp **các class và resource mới được định nghĩa bởi loader đó**.
2. Với URL kiểu `jar:` và `file:`, nó cố gắng đóng những file mà loader đã mở trong lúc nạp class hoặc resource.
3. Các class đã được nạp, các resource đã có và class/resource có thể tìm qua **parent** không bị hủy chỉ vì loader được đóng.
4. Gọi `close()` trên một loader đã đóng là không có tác động mới (idempotent theo hợp đồng).
5. Đây là nỗ lực đóng các file theo kiểu **best effort**: method có thể ném `IOException` nếu đóng file gặp lỗi, các lỗi I/O bổ sung được ghi như suppressed exceptions.
6. Nếu `close()` chạy đồng thời với một thread đang nạp class qua loader, kết quả lượt nạp đó không được bảo đảm; không dùng việc đóng loader làm primitive đồng bộ với các tác vụ còn chạy.

Ví dụ phạm vi ngắn:

~~~java
try (URLClassLoader loader = new URLClassLoader(
        new URL[]{jarPath.toUri().toURL()},
        getClass().getClassLoader())) {
    // Sử dụng các lớp/tài nguyên mà loader tìm thấy.
}
// close() được gọi cả khi thoát khối do IOException/RuntimeException.
~~~

Đây là **đoạn minh họa nằm trong một phương thức instance**, không phải chương trình độc lập. Khi một plugin hoạt động lâu, loader thường sống dài hơn một block code ngắn; lúc đó plugin manager phải giữ reference và gọi `close()` ở bước dừng có kiểm soát.

### 2.2. close() không làm gì?

`close()` **không**:

- Gọi destructor hay “unload method” tự động cho mọi lớp.
- Đặt tất cả đối tượng plugin đã tạo về `null`, hoặc ném exception trên mọi lần gọi method của chúng.
- Thu hồi một đối tượng `Class<?>` hoặc `Method` mà host còn giữ.
- Dừng thread, executor, timer, scheduled task hay listener do plugin tạo.
- Xóa `ThreadLocal` hay khôi phục `Thread.currentThread().getContextClassLoader()`.
- Đóng một `JarFile` được **code khác** mở độc lập, hoặc tự động dọn mọi socket/client/stream bên ngoài quyền quản lý của loader.
- Xóa, thay thế hoặc đổi tên JAR trên đĩa, hay bảo đảm GC/class unloading xảy ra ngay lập tức.
- Thay đổi classpath của system/application classloader đã hoạt động.

Vì vậy câu “đóng URLClassLoader để gỡ plugin” là cách nói tắt **không đầy đủ**. Chính xác hơn: host dừng công việc của plugin, dọn các tham chiếu và resource do plugin sở hữu, rồi đóng loader; sau đó JVM **có thể** thu hồi loader và các lớp khi không còn bị giữ.

## 3. Tại sao các lớp đã nạp vẫn dùng được?

Trong JVM, một lớp được xác định bởi **tên nhị phân** cùng **defining classloader**. Hai loader khác nhau có thể định nghĩa hai phiên bản của `demo.plugin.GreetingPlugin` và tạo ra **hai class identity khác nhau**, mặc dù tên chuỗi giống hệt.

Khi bytecode đã được nạp và định nghĩa thành `Class<?>`, method code của lớp không phụ thuộc vào việc `URLClassLoader` còn mở JAR để đọc lại **chính các byte đã nạp**. Một instance cũ có thể tiếp tục gọi method đã sẵn sàng, miễn là lệnh đó không cần loader cũ tìm thêm một class/resource mới và các điều kiện liên kết khác đã được đáp ứng.

Hãy phân biệt:

| Thao tác sau `close()` | Điều có thể xảy ra |
| --- | --- |
| Gọi method của instance đã tạo, chỉ dùng những lớp đã sẵn sàng | **Vẫn có thể thành công**; demo mục 5 chứng minh trường hợp này |
| Gọi method khiến JVM phải nạp thêm một class của plugin chưa được loader định nghĩa | Có thể thất bại, thường là lỗi liên kết/nạp lớp; không dựa vào đó để chạy plugin đã dừng |
| Gọi `loader.loadClass(name)` với class đã nạp hoặc class từ parent | Có thể vẫn trả class đã có do cơ chế cache/delegation |
| Gọi `loader.loadClass(name)` với class chưa được nạp, chỉ tồn tại trong JAR của loader đã đóng | Không thể tìm class mới từ JAR ấy; thường `ClassNotFoundException` |
| Tạo `URLClassLoader` mới trỏ tới JAR phiên bản mới | Có thể định nghĩa class phiên bản mới có **identity khác**, nếu parent không “giành” tên đó |
| Gọi `System.gc()` sau `close()` | **Không bảo đảm** GC diễn ra hoặc loader/class cũ bị unload |

Trường hợp method cũ chạy sau `close()` **không** có nghĩa host **nên tiếp tục gọi** plugin đã stop. Nó chỉ cho thấy việc đóng loader không phải một cơ chế thu hồi capability của instance còn sống. Một plugin manager tốt cần ngăn các lời gọi mới bằng state/lifecycle riêng.

### 3.1. Parent delegation và API chung

`URLClassLoader` thông thường tìm lớp qua parent trước, rồi mới tìm trong các URL của chính mình. Nếu host vô tình đặt `plugin-v1.jar` lên application classpath, parent có thể đã định nghĩa `demo.plugin.GreetingPlugin` trước. Khi tạo loader phiên bản 2, lời gọi `loadClass` vẫn có thể trả **class của parent**, không phải bản mới.

Đối với hệ thống plugin thật:

- **Host và plugin** nên chia sẻ một API/SPI chung (ví dụ `Plugin`, `PluginContext`) do loader cha định nghĩa.
- **Implementation plugin** chỉ nằm trong loader của phiên bản plugin; không đặt implementation trên application classpath.
- Hạn chế mang các kiểu implementation/plugin-private qua ranh giới host; dùng API type và DTO do host sở hữu.
- Nếu cần child-first cho một số package, phải thiết kế riêng và bảo vệ các package API dùng chung; đừng tự override `loadClass` vô điều kiện.

Ví dụ ở mục 5 cố ý sử dụng reflection thay vì một API JAR riêng để tập trung quan sát hành vi đóng classloader. Hệ thống sản xuất vẫn nên có SPI nhỏ và ổn định.

## 4. File handle khác với bytecode đã nạp

Giả sử loader 1 mở `plugin-v1.jar` và nạp `GreetingPlugin.class`. JAR có thể còn được loader giữ mở để tìm các lớp/resource tiếp theo. `loader.close()` giúp đóng file mà nó đã mở, nhưng bytecode của `GreetingPlugin` đã được JVM định nghĩa và instance vẫn có thể tồn tại trong heap.

~~~text
Trước khi close:
    plugin-v1.jar --[file handle]--> URLClassLoader v1
                                        |
                                        +--> Class<demo.plugin.GreetingPlugin>
                                                   |
                                                   +--> instance đang được host giữ

Sau khi close:
    plugin-v1.jar --X [file handle do loader quản lý đã được đóng]
    URLClassLoader v1 --X [khả năng tìm lớp mới từ URL của nó]
    Class<demo.plugin.GreetingPlugin> ----> instance cũ vẫn được tham chiếu

Sau khi stop + bỏ mọi tham chiếu:
    loader/class/instance có thể đủ điều kiện GC và class unloading
    (không có thời điểm unload được JVM bảo đảm)
~~~

Hình trên minh họa **hai loại quan hệ khác nhau**. Nó không chứng minh mọi file handle đã đóng trong mọi trạng thái: file có thể vẫn được một `JarFile` khác, stream, tool giám sát, JVM khác hoặc tiến trình khác mở. Khi thử đổi JAR trên Windows, đặc biệt cần quan sát các handle còn mở; trên Linux/macOS, việc unlink/rename một file đang mở có thể thành công nhưng handle cũ vẫn trỏ đến inode trước đó.

Với stream mở qua `URLClassLoader.getResourceAsStream`, tài liệu API mô tả các stream ấy sẽ được đóng khi loader đóng. Dù vậy, **người tiêu thụ stream nên tự dùng try-with-resources** và đóng ngay sau khi đọc, thay vì giữ đến lúc dừng plugin. Không coi `URLClassLoader.close()` là cách dọn mọi tài nguyên I/O của các thư viện bên thứ ba.

## 5. Ví dụ Java 17 hoàn chỉnh: đóng loader cũ nhưng method cũ vẫn chạy

Ví dụ gồm hai JAR implementation có **cùng tên lớp** nhưng trả hai thông điệp khác nhau, cộng với một lớp chỉ nằm trong JAR v1 mà **chưa từng được nạp**. Host thực hiện:

1. Tạo loader v1, tải `GreetingPlugin` và gọi `message()`.
2. Đóng loader v1.
3. Gọi lại `message()` trên **instance đã tạo** để quan sát vẫn hoạt động.
4. Thử tìm `ExtraPlugin` chưa được nạp qua loader v1 đã đóng; không tìm thấy.
5. Tạo loader v2, tải class cùng tên từ JAR v2 và so sánh danh tính lớp với v1.
6. Xác nhận instance v1 vẫn giữ hành vi v1 vì host còn tham chiếu đến nó.

**Đây là demo về cơ chế JVM, không phải mẫu lifecycle sản phẩm.** Trong sản phẩm thật, sau khi dừng v1, host không nên tiếp tục gọi nó.

### 5.1. Cấu trúc thư mục

Tạo các file sau dưới thư mục làm việc `loader-close-demo`:

~~~text
loader-close-demo/
  src/
    v1/demo/plugin/GreetingPlugin.java
    v1/demo/plugin/ExtraPlugin.java
    v2/demo/plugin/GreetingPlugin.java
    host/demo/host/LoaderCloseDemo.java
  build/
    classes/v1/
    classes/v2/
    classes/host/
    jars/
~~~

Các thư mục `build` được tạo bởi lệnh biên dịch. Host **không** biên dịch cùng source plugin và **không** thêm hai JAR plugin vào classpath của mình.

### 5.2. Plugin phiên bản 1

**File `src/v1/demo/plugin/GreetingPlugin.java`:**

~~~java
package demo.plugin;

public final class GreetingPlugin {
    public GreetingPlugin() {
    }

    public String message() {
        return "hello-v1";
    }
}
~~~

**File `src/v1/demo/plugin/ExtraPlugin.java`:**

~~~java
package demo.plugin;

public final class ExtraPlugin {
    public static String id() {
        return "extra-v1";
    }
}
~~~

`ExtraPlugin` chỉ phục vụ kiểm tra nạp class **mới** sau khi loader đã đóng. Trong đoạn code host, không dùng class literal, reflection hay lời gọi nào khiến nó được nạp sớm.

### 5.3. Plugin phiên bản 2

**File `src/v2/demo/plugin/GreetingPlugin.java`:**

~~~java
package demo.plugin;

public final class GreetingPlugin {
    public GreetingPlugin() {
    }

    public String message() {
        return "hello-v2";
    }
}
~~~

Dù cùng tên `demo.plugin.GreetingPlugin`, bản v2 sẽ được định nghĩa bởi một loader khác và trả một chuỗi khác. Việc đặt hai JAR ở hai path khác nhau giúp ví dụ không cần ghi đè một JAR đang mở.

### 5.4. Chương trình host

**File `src/host/demo/host/LoaderCloseDemo.java`:**

~~~java
package demo.host;

import java.lang.reflect.Method;
import java.net.URL;
import java.net.URLClassLoader;
import java.nio.file.Files;
import java.nio.file.Path;

public final class LoaderCloseDemo {
    private LoaderCloseDemo() {
    }

    public static void main(String[] args) throws Exception {
        Path v1 = Path.of("build/jars/plugin-v1.jar");
        Path v2 = Path.of("build/jars/plugin-v2.jar");
        if (!Files.isRegularFile(v1) || !Files.isRegularFile(v2)) {
            throw new IllegalStateException("Plugin JAR missing");
        }

        ClassLoader parent = LoaderCloseDemo.class.getClassLoader();
        URLClassLoader loader1 = new URLClassLoader(
                new URL[]{v1.toUri().toURL()}, parent);

        Class<?> type1;
        Object instance1;
        Method message1;

        // try-with-resources sẽ close loader1 khi rời block.
        try (loader1) {
            type1 = loader1.loadClass("demo.plugin.GreetingPlugin");
            instance1 = type1.getDeclaredConstructor().newInstance();
            message1 = type1.getMethod("message");

            System.out.println(
                    "v1-before-close=" + message1.invoke(instance1));
        }

        // Instance và Method đã có vẫn có thể dùng được.
        System.out.println(
                "v1-after-close=" + message1.invoke(instance1));

        // Class này có trong JAR v1 nhưng chưa được nạp.
        try {
            loader1.loadClass("demo.plugin.ExtraPlugin");
            System.out.println("unexpected");
        } catch (ClassNotFoundException expected) {
            System.out.println("new-class-after-close=unavailable");
        }

        try (URLClassLoader loader2 = new URLClassLoader(
                new URL[]{v2.toUri().toURL()}, parent)) {
            Class<?> type2 =
                    loader2.loadClass("demo.plugin.GreetingPlugin");
            Object instance2 =
                    type2.getDeclaredConstructor().newInstance();
            Method message2 = type2.getMethod("message");

            System.out.println(
                    "v2=" + message2.invoke(instance2));
            System.out.println("same-class=" + (type1 == type2));
        }

        // Host vẫn giữ v1 nên close không đồng nghĩa vô hiệu hóa nó.
        System.out.println(
                "v1-still=" + message1.invoke(instance1));
    }
}
~~~

Giải thích:

- `URLClassLoader loader1` được tạo với parent là application loader của host. Trong lệnh chạy, parent **không chứa** `demo.plugin.*`, nên bản v1 được loader1 định nghĩa.
- `type1`, `instance1` và `message1` là các tham chiếu được giữ ngoài khối `try`. Vì thế chúng vẫn dùng được khi `loader1.close()` đã chạy.
- `message()` chỉ trả string literal, không cần tìm thêm một class riêng của plugin. Do đó hai lần gọi sau khi đóng loader1 vẫn thành công trong demo.
- `ExtraPlugin` có trong JAR v1, nhưng không được nạp trước khi đóng; `loader1.loadClass` không thể đọc định nghĩa mới từ JAR đó. Parent cũng không có class cùng tên, nên nhận `ClassNotFoundException`.
- `loader2` được tạo mới và nhìn thấy `plugin-v2.jar`. Nó định nghĩa một class cùng tên nhị phân với `type1` nhưng **khác defining loader**, vì vậy `type1 == type2` là `false`.
- Không hề gọi GC hoặc khẳng định file v1 đã bị xóa. Dòng output chứng minh **khả năng tiếp tục sử dụng bytecode đã được nạp**, không chứng minh loader đã được giải phóng khỏi heap.

### 5.5. Biên dịch và đóng gói JAR

Tại thư mục `loader-close-demo`, dùng Bash với JDK 17+:

~~~bash
mkdir -p build/classes/v1 build/classes/v2 \
         build/classes/host build/jars

# Hai class của v1, đóng gói thành JAR riêng.
javac --release 17 -encoding UTF-8 \
  -d build/classes/v1 \
  src/v1/demo/plugin/GreetingPlugin.java \
  src/v1/demo/plugin/ExtraPlugin.java
jar --create --file build/jars/plugin-v1.jar \
  -C build/classes/v1 .

# Class cùng tên nhưng implementation khác của v2.
javac --release 17 -encoding UTF-8 \
  -d build/classes/v2 src/v2/demo/plugin/GreetingPlugin.java
jar --create --file build/jars/plugin-v2.jar \
  -C build/classes/v2 .

# Host chỉ dùng Java standard library; không đưa plugin JAR vào -cp.
javac --release 17 -encoding UTF-8 \
  -d build/classes/host \
  src/host/demo/host/LoaderCloseDemo.java

java -cp build/classes/host demo.host.LoaderCloseDemo
~~~

**Stdout chính xác:**

~~~text
v1-before-close=hello-v1
v1-after-close=hello-v1
new-class-after-close=unavailable
v2=hello-v2
same-class=false
v1-still=hello-v1
~~~

Khi dùng PowerShell trên Windows, sau khi biên dịch và tạo JAR, lệnh khởi chạy tương đương là:

~~~powershell
java -cp build/classes/host demo.host.LoaderCloseDemo
~~~

Trong ví dụ này classpath chỉ có một directory, nên không có vấn đề phân cách `:` hoặc `;`. Các lệnh Bash dùng dấu backslash để nối dòng; trong PowerShell, viết `javac`/`jar` thành dòng đầy đủ hoặc dùng cú pháp nối dòng riêng.

Để xác nhận JAR được tạo đúng:

~~~bash
jar --list --file build/jars/plugin-v1.jar
jar --list --file build/jars/plugin-v2.jar
~~~

Trong JAR v1 cần có `demo/plugin/GreetingPlugin.class` **và** `demo/plugin/ExtraPlugin.class`; JAR v2 cần có `demo/plugin/GreetingPlugin.class`. Nếu thêm JAR plugin vào classpath của host, parent delegation có thể thay đổi kết quả ví dụ: tránh làm vậy.

### 5.6. Diễn giải giới hạn của demo

Ví dụ chứng minh ba điều độc lập:

| Quan sát | Kết luận đúng |
| --- | --- |
| Gọi `message1.invoke(instance1)` được sau `loader1.close()` | Code của class đã nạp vẫn có thể chạy; close không làm instance bị hủy |
| Nạp `ExtraPlugin` lần đầu sau close thất bại | Loader đã đóng không định nghĩa class mới từ JAR v1 |
| `type1 != type2` và thông điệp khác | Cùng tên nhị phân nhưng hai defining loaders cho hai class identity riêng |

Ví dụ **không** đo trực tiếp file descriptor, số class đã unload hay điều kiện GC. Vì host vẫn giữ `type1`, `instance1` và `message1`, bản v1 vẫn bị tham chiếu đến. Nếu muốn kiểm tra khả năng GC/unload trong một bài thử khác, phải đưa mọi tham chiếu mạnh ra khỏi phạm vi, ngừng thread/tác vụ, thu dọn registry/cache và quan sát bằng công cụ JVM; `System.gc()` vẫn không phải bằng chứng chắc chắn.

## 6. Tại sao gọi method sau close đôi khi lại lỗi?

Bài học không phải “đóng loader rồi cứ gọi plugin bình thường”. Có sự khác biệt giữa **chạy mã đã nạp đủ dependency** và **đụng một lớp/tài nguyên chưa được nạp**.

Ví dụ về một method của plugin:

~~~java
// Minh họa: đây chỉ là một method trong plugin, không phải file độc lập.
public String format() {
    return new PluginFormatter().format("text");
}
~~~

Giả sử `PluginFormatter` chỉ có trong JAR plugin và chưa được nạp trước `loader.close()`. Lần đầu gọi `format()` sau close có thể khiến JVM phải resolve/nạp `PluginFormatter` và thất bại, thường biểu hiện qua một `LinkageError` như `NoClassDefFoundError`, dù instance ban đầu vẫn tồn tại.

Tương tự, gọi `getResourceAsStream` để đọc một resource mới sau close có thể không tìm thấy resource từ URL của loader. Điều này rất nguy hiểm nếu plugin còn thread nền hay callback nhưng host đã đóng loader.

Vì thế khi **dừng plugin**, đừng dựa vào việc lỗi tự phát sinh sau close để ngăn gọi; hãy dùng state/lifecycle rõ ràng nhằm chặn mọi thao tác mới, chờ các thao tác cũ xong, rồi mới close.

## 7. Quy trình thay thế plugin an toàn

Trong hệ thống sản xuất, thay plugin cần quản lý **hai đối tượng**: bản đang hoạt động và bản chuẩn bị kích hoạt.

Một trình tự tham khảo:

1. **Chuẩn bị phiên bản mới:** tải JAR mới ở **đường dẫn riêng** (ví dụ theo ID/version), kiểm tra checksum/chữ ký theo chính sách và compatibility của API.
2. **Khởi tạo loader v2:** dùng một `URLClassLoader` mới (hoặc cơ chế module layer phù hợp), tìm implementation và tạo instance, chạy bước validate/start. Nếu thất bại, đóng v2 và giữ v1 đang phục vụ.
3. **Chuyển định tuyến:** chuyển registry/entry point của host sang v2 bằng thao tác có đồng bộ. Trong hệ thống cần zero-downtime, điều phối in-flight calls và khả năng retry theo hợp đồng thay vì chỉ thay một biến.
4. **Quiesce v1:** ngừng nhận request mới, để các request đang chạy kết thúc hoặc hủy đúng cách; dừng scheduled tasks và executor của v1.
5. **Dọn tài nguyên v1:** gọi lifecycle hook `stop()/close()`, hủy listener, callback, timer, registration; khôi phục TCCL/ThreadLocal ở đúng thread và đóng các stream/JarFile/plugin-owned resources.
6. **Đóng loader v1:** khi không còn thread nào đang dùng loader để nạp thêm class hoặc resource, gọi `URLClassLoader.close()`. Xử lý `IOException` và suppressed exceptions thay vì coi mọi lần close đều thành công.
7. **Bỏ tham chiếu:** xóa instance, provider, `Class<?>`, `Method`, `ServiceLoader`, lambda, callback và cache gắn với v1 khỏi registry của host. Khi không còn tham chiếu giữ, loader/class có thể trở thành ứng viên thu hồi.
8. **Dọn artifact cũ:** sau khi các handle đã đóng và không còn thành phần dùng JAR cũ, áp dụng quy trình xóa hoặc lưu trữ. Không ghi đè một JAR đang hoạt động; giữ đường rollback cho phiên bản đã kiểm tra.

Trình tự này không bắt buộc v2 phải phục vụ trước khi v1 quiesce trong mọi thiết kế; nếu có state migration hoặc tài nguyên độc quyền, có thể cần dừng v1 trước khi start v2. Nhưng điều bất biến là **không đóng loader khi còn tác vụ có thể cần nó**.

### 7.1. Phác thảo plugin manager (mã minh họa)

~~~java
// Pseudocode - phụ thuộc vào các class lifecycle do ứng dụng định nghĩa.
PluginHandle candidate = prepareAndValidate(newJar);
PluginHandle previous = registry.switchTo(candidate);

previous.rejectNewCalls();
previous.awaitInFlightCalls();
previous.closeRegistrations();
previous.stopPluginOwnedExecutors();
previous.closePluginInstance();
previous.restoreOwnedThreadContexts();
previous.closeClassLoader();
registry.forget(previous);
~~~

Đây là **mã mô hình**, không phải chương trình Java độc lập. Những method trên không thuộc JDK; cần hiện thực dựa theo hợp đồng ứng dụng. Trong hệ thống thực, thứ tự các bước được điều chỉnh theo quan hệ phụ thuộc, timeout, rollback và chính sách lỗi. Nếu candidate thất bại trước khi switch, phải close candidate và giữ previous còn hoạt động; nếu stop previous thất bại, báo trạng thái chưa thu hồi hoàn toàn.

### 7.2. Đóng stream và tài nguyên của plugin trước loader

Nếu plugin mở `JarFile` riêng:

~~~java
try (JarFile jar = new JarFile(jarPath.toFile())) {
    // Đọc entry của plugin rồi đóng ngay khi đọc xong.
}
~~~

Đây là **mã minh họa** với `JarFile` được import từ `java.util.jar` và `jarPath` là `Path`. File này không phải do `URLClassLoader` trực tiếp mở, nên **không thể trông chờ `URLClassLoader.close()` đóng hộ**. Tương tự với stream do HTTP client, database connection, watch service, zip reader, file reader... Chủ thể mở/được giao ownership phải đóng.

Đối với resource lấy từ loader, nên đóng sớm:

~~~java
try (InputStream in =
        pluginLoader.getResourceAsStream("plugin/config.json")) {
    if (in == null) {
        throw new IllegalStateException("Resource not found");
    }
    byte[] content = in.readAllBytes();
    // Xử lý content trong phạm vi nguồn còn mở.
}
~~~

Đây là **mã minh họa**: `pluginLoader` phải tồn tại và `InputStream` được import từ `java.io`. `readAllBytes()` chỉ phù hợp với file nhỏ có giới hạn; dữ liệu lớn phải đọc có buffer/limit. Đừng giữ stream hay `URL` trỏ vào JAR cũ trong cache sống qua phiên plugin.

## 8. Những tham chiếu ngăn classloader được thu hồi

Ngay cả khi đã đóng toàn bộ file handle, loader cũ vẫn có thể còn sống vì bị **tham chiếu mạnh** từ các phần khác của ứng dụng.

| Nguồn giữ | Vì sao nguy hiểm | Cách xử lý |
| --- | --- | --- |
| `Map<String, Object>` lưu instance plugin | Host giữ đối tượng có class do loader cũ định nghĩa | Gỡ provider/instance khỏi registry khi stop |
| `Class<?>`, `Method`, `Constructor<?>` trong static cache | Giữ thông tin reflective của class phiên bản cũ | Xóa cache theo plugin ID/loader identity |
| `ServiceLoader` và provider list | Cache provider/instance; `reload()` không xóa object ở list khác | Bỏ tham chiếu vào service loader/provider cũ |
| `Thread.contextClassLoader` | Thread pool của host còn trỏ đến loader plugin | Khôi phục TCCL bằng `finally` trên chính thread |
| `ThreadLocal` chứa plugin context hoặc instance | Worker thread còn giữ value sau khi request kết thúc | `remove()` trong `finally` trên chính thread |
| Thread, executor, scheduler của plugin | Thread sống lâu có thể giữ class, TCCL, stack frame | Cancel/stop/shutdown/await termination trước khi close |
| Listener, callback, timer registration | Singleton/event bus của host giữ lambda hoặc instance plugin | Hủy đăng ký và giải phóng registration handle |
| Lazy resource URL, stream, JarFile | File handle/connection có thể tồn tại ngoài loader | Đóng đúng owner; không giữ resource sau stop |
| Stack frame đang thực thi code plugin | Lời gọi chưa xong vẫn tham chiếu đến class/loader | Quiesce và chờ in-flight calls |

Ví dụ **khôi phục TCCL đúng phạm vi**:

~~~java
ClassLoader original =
        Thread.currentThread().getContextClassLoader();
try {
    Thread.currentThread().setContextClassLoader(pluginLoader);
    plugin.execute(context);
} finally {
    Thread.currentThread().setContextClassLoader(original);
}
~~~

Đây là mã minh họa; `pluginLoader`, `plugin` và `context` là các biến của hệ thống thật. TCCL phải được khôi phục trên **chính thread được thay đổi**, không thể sửa TCCL của thread A bằng cách đặt lại TCCL trên thread B.

Nếu plugin có `ThreadLocal`:

~~~java
// Minh họa: REQUEST_CONTEXT là ThreadLocal<?> của ứng dụng.
REQUEST_CONTEXT.set(context);
try {
    usePlugin(context);
} finally {
    REQUEST_CONTEXT.remove();
}
~~~

Một `static` field hoặc cache do **host** sở hữu có thể giữ loader cũ suốt đời JVM. Ngược lại, static field thuộc class plugin không tự động là leak nếu toàn bộ classloader/class/instance đã hết tham chiếu; cần xét **đường tham chiếu từ GC roots** thay vì chỉ nhìn thấy chữ `static`.

## 9. Lỗi thường gặp và cách chẩn đoán

| Hiện tượng | Nguyên nhân có thể | Cách kiểm tra |
| --- | --- | --- |
| Đóng loader rồi nhưng method cũ vẫn chạy | Class/instance/method đã nạp vẫn còn tham chiếu | Đây là hành vi hợp lệ; cần lifecycle để chặn gọi mới |
| `ClassNotFoundException` khi nạp lớp mới sau close | Lớp chưa nạp chỉ nằm trong URL của loader đã đóng | Dùng loader mới; không tái sử dụng loader đóng |
| `NoClassDefFoundError` khi gọi instance cũ | Method cần class chưa được loader cũ nạp hoặc runtime dependency thiếu | Xem stack trace, thứ tự stop và dependency đã nạp |
| Plugin v2 vẫn trả kết quả v1 | Host để implementation ở parent classpath, hoặc vẫn gọi instance/cache v1 | Kiểm tra defining loader, routing và artifact version |
| JAR không xóa/đổi tên được trên Windows | File/stream/JarFile/loader còn giữ handle | Kiểm tra open handles, resource ownership và close errors |
| Số classloader sống tăng sau reload | Cache, TCCL, thread, callback, in-flight requests còn giữ loader | Xem heap dominators, thread dump, registry, số loader |
| Không tìm được resource sau close | Resource thuộc URL của loader đã đóng, chưa được mở/đọc trước | Đọc xong và đóng stream trước stop, không mở mới sau close |
| Nạp class đồng thời close cho lỗi không ổn định | Race giữa lifecycle stop và class loading | Đồng bộ quiesce; đừng close trước khi mọi lượt nạp hoàn tất |
| `close()` ném `IOException` | Một hoặc nhiều file được loader mở không đóng được | Log cả suppressed exceptions, xử lý trạng thái cleanup |

Một số công cụ chẩn đoán hữu ích:

- **Thread dump** và heap dump: tìm thread, `ThreadLocal`, callbacks và GC roots giữ instance/classloader.
- **JFR** hoặc JVM logging về class loading/unloading: xem classloader cụ thể có được unload hay không. Trên HotSpot, `-Xlog:class+unload=info` có thể ghi sự kiện unload; không phải lời hứa lúc nào GC sẽ unload.
- **`jcmd`** (nếu JVM hỗ trợ các diagnostic commands tương ứng): kiểm tra classloader statistics hoặc heap histogram tùy phiên bản. Xem `jcmd <pid> help` trên đúng môi trường trước khi sử dụng.
- **OS handle/file descriptor monitoring:** kiểm tra file JAR có đang được tiến trình giữ mở, thay vì lấy khả năng gọi method làm chỉ báo.

Không đánh giá rò rỉ classloader chỉ bằng việc tổng heap/metaspace chưa giảm sau một lần GC: JVM có thể giữ vùng nhớ đã cấp để tái sử dụng. Quan sát nhiều vòng start/stop và chuỗi tham chiếu giữ thực tế.

## 10. Giới hạn bảo mật và tính độc lập phiên bản

`URLClassLoader` là cơ chế nạp code vào **cùng JVM**, không tự tạo sandbox bảo mật đáng tin cậy cho plugin không tin cậy. Một plugin có thể tạo thread, sửa state chung hoặc gọi API mà tiến trình có quyền. Việc đóng loader sau đó không “undo” các tác dụng phụ ấy.

Cần thêm chính sách về nguồn JAR, chữ ký/checksum, compatibility, dependency isolation và kiểm soát vòng đời. Nếu hai plugin dùng các phiên bản thư viện xung đột, classloader riêng có thể giúp quản lý namespace, nhưng phải chia sẻ hợp đồng API đúng cách. Một loader đóng không giải quyết việc rò rỉ tham chiếu xuyên loader, quyền truy cập của plugin hay cleanup của native code.

Trong ứng dụng dùng **JPMS module layers**, tên module, khả năng đọc/export và lifecycle module layer khác với classpath URL loader. Không giả định `URLClassLoader.close()` có thể “gỡ” cả module layer; đây là chủ đề riêng. Bài này tập trung classpath JAR và URLClassLoader.

## 11. Checklist trước khi thay thế JAR

- [ ] JAR v2 được build và kiểm tra ở đường dẫn version riêng, không ghi đè file đang được loader v1 đọc.
- [ ] API dùng chung nằm ở loader cha; implementation không bị tải nhầm từ parent classpath.
- [ ] Plugin mới được tạo, validate/start và sẵn sàng trước khi chuyển routing (hoặc dùng quy trình stop/start rõ ràng khi có tài nguyên độc quyền).
- [ ] Host chặn lời gọi mới tới v1 và chờ/hủy các lời gọi đang chạy theo hợp đồng.
- [ ] Plugin đã shutdown executor, scheduler, thread, listener, callback, connection, watcher và stream do nó sở hữu.
- [ ] TCCL và ThreadLocal được phục hồi/xóa trên đúng thread.
- [ ] `URLClassLoader.close()` được gọi sau khi plugin quiesce; xử lý `IOException` và suppressed exceptions.
- [ ] Host bỏ hết instance, `Class<?>`, reflection metadata và registry/cache của v1.
- [ ] File cũ chỉ được xóa/lưu trữ khi không còn handle, không dựa vào việc loader đã bị GC.
- [ ] Test nhiều chu kỳ v1→v2→v3, cả nhánh lỗi và call song song, theo dõi loader/resource retention.
- [ ] Không diễn giải một lời gọi method cũ sau close là bằng chứng plugin đã unload hoặc loader có thể tái sử dụng.

## 12. Tự kiểm tra

1. Nếu gọi `URLClassLoader.close()`, chuyện gì xảy ra với file JAR do loader đã mở? **Loader cố đóng các file ấy**; việc đổi/xóa file còn phụ thuộc handle khác và hệ điều hành.
2. Instance `GreetingPlugin` đã được tạo có ngừng hoạt động ngay sau close không? **Không.** Khi còn tham chiếu và method không cần nạp thêm dependency mới, code đã nạp vẫn có thể chạy.
3. Sau close có thể gọi `loadClass` cho một class mới chỉ nằm trong JAR cũ không? **Không**, loader đã đóng không định nghĩa class mới từ URL của nó. Các class đã có hoặc class từ parent là trường hợp khác.
4. Tại sao v1 và v2 cùng tên class có thể cùng tồn tại? **Defining classloader khác nhau** tạo class identity khác nhau.
5. Vì sao `System.gc()` không phải công cụ “unload plugin”? **GC không được bảo đảm xảy ra theo yêu cầu**, và loader còn tham chiếu sẽ không đủ điều kiện thu hồi.
6. Có nên đóng loader ngay sau khi chuyển routing sang v2? **Chưa chắc**; phải chờ v1 không còn in-flight calls hoặc task còn cần class/resource của nó.
7. Nếu host cache `Method` hoặc giữ `Thread.contextClassLoader` của v1, close có làm hết leak không? **Không**; phải xóa cache và khôi phục context có chủ đích.
8. Vì sao demo sau close vẫn in `hello-v1`? Nó chỉ gọi method đã nạp, không phải chứng minh loader đã unload.

**Kết luận:** `URLClassLoader.close()` là **bước dọn tài nguyên nạp lớp/I-O**, không phải một phép hủy class. Để thay thế plugin đúng cách, host cần ngừng công việc, thu hồi các tài nguyên và tham chiếu do plugin sở hữu, đóng loader, rồi mới kỳ vọng JVM có thể thu hồi các lớp cũ khi GC phù hợp. Việc class đã nạp còn tồn tại sau close là hành vi Java hợp lệ và cần được thiết kế vào quy trình lifecycle thay plugin.
