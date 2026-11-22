# Ánh xạ tên lớp tới nguồn dữ liệu có giới hạn rõ ràng trong custom ClassLoader

## 1. Bài toán cần giải quyết

Một custom `ClassLoader` có thể định nghĩa các lớp Java từ dữ liệu lấy ở thư mục, JAR, cơ sở dữ liệu, mạng hoặc một kho bytecode riêng. Tuy nhiên, từ **binary class name** như `demo.plugins.Greeting` đến **nguồn dữ liệu bytes** là một quyết định thiết kế quan trọng. Nếu biến mọi chuỗi tên lớp thành một đường dẫn hoặc URL tùy ý mà không giới hạn, loader dễ rơi vào tình huống nạp nhầm bytecode, truy cập ngoài vùng cho phép, phụ thuộc vào thứ tự tìm kiếm không rõ ràng hoặc tiêu thụ quá nhiều tài nguyên.

Mục tiêu của bài này là thiết kế **ánh xạ rõ ràng, có phạm vi (bounded mapping)**:

1. Xác định **những binary class names nào được chấp nhận**.
2. Xác định **nguồn bytes tương ứng với từng tên**.
3. Giới hạn **thư mục hoặc kho được phép đọc** và kiểm tra đường dẫn sau chuẩn hóa.
4. Giới hạn **kích thước dữ liệu, số lớp hoặc lượng công việc** theo yêu cầu vận hành.
5. Phân biệt **parent delegation** với **nguồn bytecode riêng** do loader này kiểm soát.
6. Giải thích cách trả `ClassNotFoundException` hoặc lỗi phù hợp thay vì tự đoán một class khác khi tên/nguồn không khớp.
7. Không lẫn lộn tính hợp lệ của bytecode, khả năng định nghĩa lớp và việc tin cậy/truy cập an toàn đối với mã được thực thi.

Ví dụ nguyên tắc:

~~~text
Binary name                Approved source
----------------------------------------------------------
demo.plugins.Greeting   ->  plugin-classes/demo/plugins/Greeting.class
demo.plugins.Parser     ->  [không có trong allowlist: từ chối]
java.lang.String        ->  bootstrap/platform qua delegation

Không bao giờ dùng một tên người dùng nhập để tự ý
chọn file ngoài trusted root hoặc URL bất kỳ.
~~~

**Phạm vi bảo vệ rất quan trọng:** ánh xạ được giới hạn ở đây bảo vệ **nguồn dữ liệu do `findClass` của custom loader tự đọc và định nghĩa**. Nó **không phải sandbox bảo mật để ngăn code plugin đọc file, mở kết nối mạng hay dùng mọi Java API**. Trong Java 17+, không nên dựa vào `SecurityManager` như biện pháp sandbox đáng tin cậy; Java Security Manager đã bị deprecated for removal trong Java 17 và không phải cơ chế cách ly code tùy ý cho thiết kế mới.

## 2. Tên lớp dùng ở API: binary name chứ không phải tên đường dẫn

`ClassLoader.loadClass(String name)` và `findClass(String name)` làm việc với **binary name** của một kiểu, chẳng hạn:

| Loại | Ví dụ |
| --- | --- |
| Lớp trong package | `com.example.Greeting` |
| Lớp ở unnamed package | `Greeting` |
| Lớp thành viên nested | `com.example.Outer$Inner` |
| Tên class file entry tương ứng | `com/example/Greeting.class` |
| Resource path tương ứng | `com/example/Greeting.class` |
| JVM internal name trong class file | `com/example/Greeting` |

Không được thay chuỗi binary name bằng một URL, `../secret` hoặc một path tùy ý. Tên nested class trong class file thường có dấu `$`, không phải dấu `.` của source syntax. Ví dụ `Outer.Inner` có thể là tên canonical/source, còn binary name là `Outer$Inner`.

Một quy ước **có thể** dùng là:

~~~java
String resource = binaryName.replace('.', '/') + ".class";
~~~

Đây là **đoạn minh họa**, không phải chính sách đủ an toàn khi dùng với đầu vào chưa được kiểm soát. Nó chuyển tên thành path, nhưng **chưa trả lời** tên nào hợp lệ, thư mục nào được phép, người gọi có quyền yêu cầu tên ấy không, file có nằm trong root không, bytes có đúng class file và giới hạn kích thước không.

Nếu yêu cầu rất hẹp, **explicit allowlist map** thường rõ ràng hơn việc chuyển mọi tên thành đường dẫn.

## 3. Hai cách ánh xạ phổ biến và khi chọn

### 3.1. Ánh xạ tường minh từng binary name

Ví dụ:

~~~java
Map<String, Path> approved = Map.of(
        "demo.plugins.Greeting",
        Path.of("demo", "plugins", "Greeting.class")
);
~~~

Điều này thể hiện rõ:

- Chỉ `demo.plugins.Greeting` được custom loader tìm trong kho riêng.
- Đường dẫn là **relative path** bên dưới trusted root, không phải đường dẫn tuyệt đối do người gọi quyết định.
- Một tên khác như `demo.plugins.Admin` sẽ không có ánh xạ.
- Việc tên nằm trong `demo.plugins` vẫn **chưa đủ** để được load nếu nó không có trong allowlist.

Ưu điểm: dễ review, audit, hash/checksum, version pinning. Nhược điểm: với nhiều lớp cần quản lý manifest lớn; nên sinh manifest từ quá trình build/đăng ký plugin có kiểm soát thay vì nhập thủ công hàng nghìn mục.

### 3.2. Ánh xạ theo prefix/package đã kiểm tra

Với kho lớn hơn, có thể chấp nhận tất cả tên khớp một **package boundary chính xác**, rồi chuyển theo quy ước đường dẫn, ví dụ `demo.plugins.*`. Nhưng cần kiểm tra cả:

- Binary name có cú pháp được chính sách cho phép.
- Tiền tố là `demo.plugins.` **bao gồm dấu chấm kết thúc**, tránh vô tình cho phép `demo.pluginsEvil.*`.
- Không chứa `/`, dấu gạch ngược, chuỗi path traversal hoặc tên giả mạo.
- Chuỗi sau prefix có phù hợp những dạng binary name cần hỗ trợ (including nested names `$`) không.
- Đường dẫn cuối cùng phải nằm trong root đã xác thực, sau khi xét symlinks và cách canonicalize của filesystem.

**Không đặt một regex đơn giản làm tiêu chuẩn toàn bộ tên Java hợp lệ** nếu công cụ cần hỗ trợ Unicode identifiers, generated class names, các dạng nested/anonymous hoặc định nghĩa đặc biệt. Chính sách chỉ cho phép một tập con là hợp lệ nếu được công bố rõ; đừng tuyên bố nó kiểm tra mọi binary name hợp lệ theo JVM spec.

Bài thực hành dưới đây dùng **explicit allowlist** để bài toán mapping rõ nhất.

## 4. Ba ranh giới cần định nghĩa tường minh

### 4.1. Ranh giới tên (namespace)

Cho phép những binary names hoặc package scopes đã đăng ký. Không nên cho custom loader tự định nghĩa các package nền tảng như `java.*`; JVM hạn chế việc định nghĩa `java.*` trong application class loaders, đồng thời việc cố nạp bản riêng của core API có thể gây lỗi nghiêm trọng về type identity.

Danh sách tên được phép có thể do config đáng tin cậy, build-generated manifest hoặc registry có xác thực cung cấp. **Đầu vào người dùng cuối không nên tự tạo quyền load một class bất kỳ**.

### 4.2. Ranh giới dữ liệu (source boundary)

Gốc thư mục hay kho dữ liệu phải được chọn từ cấu hình đáng tin cậy, không phải ghép tự do từ input. Với filesystem:

~~~text
trustedRoot = /srv/app/plugins/v1/classes/
requested = demo.plugins.Greeting
relative = demo/plugins/Greeting.class
candidate = trustedRoot/relative
~~~

Kiểm tra:

1. Relative path thực sự **không tuyệt đối**.
2. Candidate sau canonicalization/real-path resolution vẫn **ở trong** trusted root.
3. Nguồn là regular file được phép và kích thước không vượt giới hạn.
4. Nếu symlink được chấp nhận, **đích cuối cùng** của symlink vẫn ở trong root; nếu không cho phép symlink thì phải kiểm soát từng thành phần đường dẫn.
5. Không xem phép `String.startsWith("/srv/app/plugins")` là ranh giới path: `/srv/app/plugins-evil/...` có cùng tiền tố chuỗi nhưng nằm ngoài root. Dùng `Path.startsWith(otherPath)` sau khi chuẩn hóa phù hợp.

Trong môi trường filesystem do đối tượng không đáng tin có thể thay đổi đồng thời, việc gọi `toRealPath` rồi mới đọc file có thể gặp **TOCTOU race**. Kiểm tra path trước khi mở không phải bảo đảm chống kẻ tấn công có khả năng thay symlink/thư mục giữa hai bước. Với threat model như vậy, cần thiết kế kho immutable/permission-controlled hoặc dùng các primitive truy cập qua directory handle/`SecureDirectoryStream` khi provider hỗ trợ, cộng các kiểm soát ở cấp hệ điều hành.

### 4.3. Ranh giới tài nguyên (resource limits)

Một class file có thể quá lớn hoặc kho plugin có hàng triệu entry. Giới hạn cần gắn với nhu cầu:

- **Bytes tối đa mỗi class file**, có cap ở bước đọc, không chỉ `Files.size` trước đó.
- **Số lớp được phép** hoặc số class definitions theo manifest.
- **Thời gian I/O hoặc request timeout** nếu bytes đến từ mạng.
- **Số request đồng thời/caches** để tránh bùng nổ bộ nhớ.
- **Nguồn tin cậy/hash/chữ ký** khi plugin supply chain là thành phần quan trọng.

Một giới hạn byte không chứng minh bytecode an toàn; JVM verification cũng không phải sandbox quyền file/network. Một allowlist giới hạn **cái gì loader tự tìm**, chứ không thay thế cách ly process/container đối với code không tin cậy.

## 5. Ví dụ Java 17+ độc lập: loader chỉ đọc một class từ root cố định

Chúng ta tạo một host app và một plugin class tách biệt. Custom loader sau đây:

- Chỉ cho phép **binary name `demo.plugins.Greeting`** trong kho riêng.
- Đọc file tương ứng từ một root được truyền **một lần ở lúc tạo loader**.
- Dùng `toRealPath` và `Path.startsWith` để từ chối đích thoát ra ngoài root.
- Kiểm tra regular file, cap đọc **1 MiB**.
- Gọi `defineClass` với **chính binary name đã yêu cầu**, để JVM kiểm tra tên trong class file.
- Dùng platform loader làm parent, cho phép các Java runtime classes cần thiết được tìm qua delegation.
- Không tự tải class khi tên khác allowlist, dù có file mang tên khác trong root.

### 5.1. Cây thư mục

~~~text
bounded-loader-demo/
├── plugin-src/
│   └── demo/
│       └── plugins/
│           └── Greeting.java
└── host-src/
    └── HostDemo.java
~~~

Sau biên dịch, chúng ta có hai thư mục độc lập:

~~~text
bounded-loader-demo/
├── plugin-classes/
│   └── demo/
│       └── plugins/
│           └── Greeting.class
└── host-classes/
    ├── HostDemo.class
    └── HostDemo$BoundedLoader.class
~~~

**Quan trọng:** không đưa `plugin-classes` vào host application classpath. Nếu parent cũng thấy plugin class, parent-first delegation có thể trả về class do parent định nghĩa, khiến demo không còn chứng minh loader tự nạp bytecode riêng.

### 5.2. File plugin: plugin-src/demo/plugins/Greeting.java

~~~java
package demo.plugins;

public class Greeting {
    public String message() {
        return "hello from mapped class";
    }
}
~~~

Đây là file Java độc lập cho plugin. Constructor mặc định do javac cung cấp có quyền truy cập phù hợp với public class. Nó không tham chiếu host class nào.

### 5.3. File host: host-src/HostDemo.java

~~~java
import java.io.IOException;
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Map;

public class HostDemo {
    static final class BoundedLoader extends ClassLoader {
        private static final int MAX_BYTES = 1_048_576;

        private final Path trustedRoot;
        private final Map<String, Path> approved = Map.of(
                "demo.plugins.Greeting",
                Path.of("demo", "plugins", "Greeting.class")
        );

        BoundedLoader(Path root) throws IOException {
            super(ClassLoader.getPlatformClassLoader());
            this.trustedRoot = root.toRealPath();

            if (!Files.isDirectory(trustedRoot)) {
                throw new IOException("Not a directory: " + trustedRoot);
            }
        }

        @Override
        protected Class<?> findClass(String binaryName)
                throws ClassNotFoundException {
            Path relative = approved.get(binaryName);

            if (relative == null) {
                throw new ClassNotFoundException(
                        "Not allowlisted: " + binaryName);
            }

            try {
                if (relative.isAbsolute()) {
                    throw new IOException("Expected relative path");
                }

                Path candidate = trustedRoot.resolve(relative).toRealPath();
                if (!candidate.startsWith(trustedRoot)) {
                    throw new IOException("Outside trusted root");
                }
                if (!Files.isRegularFile(candidate)) {
                    throw new IOException("Not a regular class file");
                }

                byte[] bytes;
                try (InputStream in = Files.newInputStream(candidate)) {
                    bytes = in.readNBytes(MAX_BYTES + 1);
                }

                if (bytes.length == 0 || bytes.length > MAX_BYTES) {
                    throw new IOException("Invalid class-file size");
                }

                return defineClass(
                        binaryName, bytes, 0, bytes.length);
            } catch (IOException error) {
                throw new ClassNotFoundException(
                        "Cannot read approved class: " + binaryName,
                        error);
            }
        }
    }

    public static void main(String[] args) throws Exception {
        if (args.length != 1) {
            throw new IllegalArgumentException(
                    "Usage: HostDemo <plugin-classes-directory>");
        }

        BoundedLoader loader = new BoundedLoader(Path.of(args[0]));

        Class<?> plugin = loader.loadClass("demo.plugins.Greeting");
        Object instance = plugin.getDeclaredConstructor().newInstance();
        String message = (String) plugin.getMethod("message")
                .invoke(instance);

        System.out.println("defined by bounded loader: "
                + (plugin.getClassLoader() == loader));
        System.out.println("message: " + message);

        Class<?> stringType = loader.loadClass("java.lang.String");
        System.out.println("standard class uses bootstrap: "
                + (stringType.getClassLoader() == null));

        try {
            loader.loadClass("demo.plugins.Unknown");
            System.out.println("unknown plugin class rejected: false");
        } catch (ClassNotFoundException expected) {
            System.out.println("unknown plugin class rejected: true");
        }
    }
}
~~~

Điểm kỹ thuật của code:

- `Map.of` là immutable map về cấu trúc (không có API chỉnh entries tại runtime); cấu hình mapping không thay đổi giữa những lần tra cứu.
- `toRealPath()` của root và candidate giải quyết đường dẫn thực tồn tại, bao gồm symlink theo hành vi mặc định của provider. `Path.startsWith` kiểm tra **path components**, tránh nhầm tiền tố chuỗi.
- `readNBytes(MAX_BYTES + 1)` giới hạn bytes đọc/đưa vào mảng; nếu file lớn hơn 1 MiB thì array sẽ chứa thêm một byte rồi bị từ chối. Không dùng `Files.readAllBytes` vô hạn trên nguồn có thể rất lớn.
- `defineClass(binaryName, bytes, 0, bytes.length)` yêu cầu bytes thể hiện class phù hợp tên đang được load. Nếu file bytes sai định dạng hoặc sai internal class name, JVM báo lỗi tương ứng, không tự đổi tên class theo tên file.
- Parent loader là **platform loader**, nên những class cốt lõi như `java.lang.String` vẫn được bootstrap/runtime loaders xử lý.
- `findClass` chỉ quản lý nguồn riêng; `loadClass` mặc định vẫn thực hiện delegation cho parent. **Không được coi đây là allowlist tuyệt đối của mọi class mà loader có thể trả về.**

### 5.4. Biên dịch và chạy

Mở terminal tại thư mục `bounded-loader-demo`. Những lệnh sau chạy bằng JDK 17 trở lên trên Windows, Linux và macOS khi thư mục được tạo đúng:

~~~bash
javac --release 17 -d plugin-classes plugin-src/demo/plugins/Greeting.java
javac --release 17 -d host-classes host-src/HostDemo.java
java -cp host-classes HostDemo plugin-classes
~~~

**Stdout chính xác khi chạy với các file trên và cấu hình thông thường:**

~~~text
defined by bounded loader: true
message: hello from mapped class
standard class uses bootstrap: true
unknown plugin class rejected: true
~~~

Diễn giải:

1. Vì chỉ `host-classes` được đưa vào `-cp`, system/app loader của host không được cung cấp bytes của `demo.plugins.Greeting` từ thư mục plugin.
2. `BoundedLoader` gọi parent trước; platform loader không có `demo.plugins.Greeting` trong JDK chuẩn, nên chuyển đến `findClass` của loader và đọc bytes từ trusted root.
3. `getClassLoader() == loader` đúng vì **loader này là defining loader** của plugin class.
4. Reflection tạo instance và gọi phương thức public `message()`. String trả về là Java core type, được chia sẻ phù hợp qua bootstrap/platform delegation.
5. `java.lang.String` được tìm qua parent/bootstrap; plugin loader không tự định nghĩa bản sao String.
6. Tên `demo.plugins.Unknown` không có trong allowlist. Parent không tìm được tên đó trong tình huống demo; `findClass` ném `ClassNotFoundException` nên ứng dụng in kết quả từ chối.

## 6. Giới hạn của ví dụ: bảo vệ mapping chứ không sandbox plugin

Ví dụ ở mục 5 là một **mẫu bounded filesystem mapping để học API**, không phải runtime an toàn cho mã không tin cậy. Những giới hạn được chủ động chỉ rõ:

**Thứ nhất, parent vẫn có quyền tìm class.** Nếu gọi `loader.loadClass("java.util.List")`, parent/bootstrap có thể trả về type Java runtime. Điều này cần thiết để plugin thực thi Java code. Nếu người viết kỳ vọng chỉ duy nhất `Greeting` và hoàn toàn không có class nào khác được trả về, thì `findClass` allowlist **không đáp ứng** kỳ vọng đó. Một số cơ chế plugin cố override `loadClass` để áp chính sách khác, nhưng chặn các core types tùy tiện sẽ làm việc liên kết của plugin thất bại. Không cố biến class loading boundary thành quyền bảo mật hệ thống.

**Thứ hai, file root phải đáng tin và có kiểm soát quyền ghi.** `toRealPath()` + `startsWith` chặn việc đường dẫn hiện tại trỏ ra ngoài root tại thời điểm kiểm tra; chúng không cung cấp giao dịch nguyên tử giữa kiểm tra và mở file. Nếu kẻ tấn công có quyền đổi symlink hoặc thay file trong kho cùng lúc, cần kho immutable, file ownership/permissions ở OS, ký bytecode hoặc cách mở file qua directory-handle phù hợp.

**Thứ ba, giới hạn byte không kiểm tra độ tin cậy của bytecode.** Một class file nhỏ hơn 1 MiB có thể làm nhiều việc khi được khởi tạo/thực thi. Verification của JVM bảo vệ tính an toàn kiểu bytecode, nhưng không hạn chế mọi hành vi I/O, CPU, mạng hay tác dụng phụ của static initializer.

**Thứ tư, custom loader không tự làm unload/reload an toàn.** Một `Class<?>` đã được định nghĩa bởi một loader không thể được “đổi bytes” tùy ý chỉ bằng cách sửa file rồi gọi `loadClass` lần nữa. Để dùng một định nghĩa mới của cùng binary name, thường phải tạo loader mới, quản lý lifecycle và giải phóng tham chiếu tới loader cũ nếu muốn GC có thể unload.

**Thứ năm, byte cap và allowlist không phải resource quota toàn tiến trình.** JVM có thể nạp dependency khác, plugin có thể cấp phát heap hoặc spawn thread; application cần những giới hạn và cô lập bổ sung nếu threat model đòi hỏi.

### 7. Vì sao không dùng className.replace để đọc bất kỳ file nào?

Một đoạn mã dễ gặp:

~~~java
@Override
protected Class<?> findClass(String name)
        throws ClassNotFoundException {
    String file = name.replace('.', '/') + ".class";
    byte[] bytes = Files.readAllBytes(Path.of("/some/root", file));
    return defineClass(name, bytes, 0, bytes.length);
}
~~~

**Đây là anti-pattern mang tính minh họa; không phải file runnable độc lập.** Ngoài việc thiếu xử lý `IOException`, đoạn code còn có vấn đề:

- Không xác định package hoặc tên lớp nào thực sự được cho phép.
- Không có kiểm tra candidate path thực nằm trong trusted root.
- Không xử lý symlink đưa candidate sang file ngoài root.
- Không giới hạn kích thước file trước khi cấp bộ nhớ đọc toàn bộ.
- Không ghi rõ dependency được ủy quyền cho parent hay do loader tự nạp.
- Không phân biệt “không tìm thấy class” và “đường dẫn bị từ chối bởi policy”.
- Không đảm bảo bytes đến từ artifact đã được phê duyệt.

Việc ghép một path chỉ là **cơ chế chuyển đổi hình thức tên**, không phải đầy đủ chính sách “bản đồ tên lớp → nguồn dữ liệu tin cậy”.

Với một thư viện có rất nhiều class hợp lệ, có thể lập manifest từ thời điểm build để ánh xạ tên sang các JAR entries, thêm hash và version, rồi dùng cùng triết lý kiểm soát phạm vi. Không nên mở rộng quyền đơn giản bằng cách cho tất cả tên binary và tất cả URLs.

## 8. Nếu nguồn là JAR thay vì thư mục

Một thiết kế có thể ánh xạ:

~~~text
com.example.spi.PluginA -> plugins/plugin-a-v3.jar!/com/example/spi/PluginA.class
com.example.spi.PluginB -> plugins/plugin-b-v1.jar!/com/example/spi/PluginB.class
~~~

Đây là **bản đồ khái niệm**, không phải cú pháp đường dẫn file mà `Path.of` hiểu nguyên văn. `!/...` thường gợi nhớ cú pháp resource URL dạng `jar:file:...!/entry`.

Các giới hạn cần có:

1. Chọn JAR đã được phê duyệt bằng manifest/registry, không lấy arbitrary URL từ tên lớp.
2. Giới hạn kích thước và nguồn của JAR; chống nén quá mức/zip bomb nếu nguồn không đáng tin.
3. Chỉ cho phép entry đã đăng ký; kiểm tra tên entry theo chuẩn và không chấp nhận path traversal khi giải nén.
4. Giới hạn bytes class mà loader đọc từ từng entry; tránh đọc không giới hạn.
5. Có chiến lược parent delegation rõ đối với API host/JDK.
6. Chọn `URLClassLoader`/module APIs sẵn có khi phù hợp, thay vì tự viết trình phân tích ZIP/class file.
7. Đóng `URLClassLoader` sau khi không dùng để giải phóng resources mở; việc close không làm mọi class đã được định nghĩa lập tức unload.

Ví dụ API Java 17:

~~~java
try (java.net.URLClassLoader loader =
         new java.net.URLClassLoader(
                 new java.net.URL[] { approvedJar.toUri().toURL() },
                 ClassLoader.getPlatformClassLoader())) {
    Class<?> type = loader.loadClass("com.example.spi.PluginA");
}
~~~

**Đoạn minh họa**, giả sử `approvedJar` là một `Path` đã được kiểm tra và thực sự chứa class. Mặc dù JAR URL đã giới hạn ở một file, bản thân `URLClassLoader` **không tạo allowlist tên class** như ví dụ `BoundedLoader`; nếu cần allowlist nghiêm ngặt, kiểm tra tên ở API wrapper/loader policy thích hợp. Parent delegation cũng có thể trả về class từ parent.

## 9. Nếu nguồn là mạng, database hoặc object storage

Có thể ánh xạ tên binary sang một **định danh nội bộ ổn định**, ví dụ:

~~~text
demo.plugins.Greeting
    -> artifact-id: plugin-greeting@sha256:...
    -> trusted object storage entry
    -> byte[] sau xác thực / giới hạn
    -> defineClass(binaryName, ...)
~~~

Điểm mấu chốt: **binary name không phải URL do người gọi tự chọn**. Loader không nên làm:

~~~java
// KHÔNG phải mẫu an toàn: người gọi điều khiển URL nguồn
URL url = new URL(userInput);
byte[] bytes = url.openStream().readAllBytes();
~~~

Đây là anti-pattern minh họa; không phải chương trình hoàn chỉnh. Ngoài vấn đề unbounded bytes, cách này có nguy cơ truy cập những network endpoints ngoài dự kiến (SSRF trong ngữ cảnh service), thiếu xác thực integrity và khó điều phối cache/version.

Thiết kế hợp lý hơn:

- Service registry/manifest ánh xạ **allowed binary name** sang artifact identifier được xác thực.
- Storage client truy cập **chỉ các buckets/endpoints đã cấu hình**.
- TLS, authn/authz và hash/signature đảm bảo dữ liệu đến từ nguồn được phép.
- Timeout, retry giới hạn, byte limit và circuit breaker tránh treo loader thread.
- Các lỗi fetch/validation được bọc phù hợp trong `ClassNotFoundException` khi tên không có định nghĩa; lỗi bytecode/linkage vẫn để JVM báo nguyên nhân tương ứng.
- Có cơ chế quan sát (logs/metrics) cho tên requested, artifact ID và thời gian fetch mà không tiết lộ bí mật.
- Không kích hoạt network fetch bất ngờ trên mọi `loadClass`; cân nhắc tải trước dữ liệu đã approved hoặc cache có giới hạn.

## 10. Parent-first delegation và allowlist: ranh giới nào đang áp dụng?

Cách triển khai mặc định của `ClassLoader.loadClass(String, boolean)` thường:

~~~text
loadClass(name)
      |
      v
findLoadedClass(name)
      |
      v
parent.loadClass(name)
      |
  không tìm được
      |
      v
findClass(name)
      |
      v
defineClass(name, bytes, ...)
~~~

Vì vậy, nếu parent đã biết `demo.plugins.Greeting` thì child có thể **không đọc** file mapping của mình, dù allowlist có tên ấy.

Hệ quả thiết kế:

- Trong plugin isolation, đặt APIs chia sẻ ở parent và implementation độc lập ở loader riêng.
- Đừng coi allowlist ở `findClass` là chặn mọi thứ parent có thể trả về.
- Nếu cần **chặn tuyệt đối một binary name** khỏi việc được trả về, phải thiết kế policy ở lớp API/loader routing phù hợp, xét cả parent delegation và những ràng buộc JVM về core classes.
- Nếu cần **child-first** cho package plugin, cần override `loadClass` cẩn thận, tránh tự định nghĩa các core/shared API classes gây `ClassCastException`/`LinkageError`. Child-first không tự nhiên an toàn hơn.
- Parent loader có thể là platform loader, application loader hoặc một loader chung; lựa chọn phụ thuộc package sharing và dependencies của plugin.

Phân biệt **initiating loader** (loader nhận/tham gia yêu cầu nạp) và **defining loader** (loader thực sự định nghĩa kiểu). Khi parent trả về một Class, `type.getClassLoader()` báo defining loader, có thể không phải child.

## 11. Khi nào trả ClassNotFoundException, khi nào để LinkageError nổi lên?

Đối với `findClass(String)`, hợp đồng chính là ném `ClassNotFoundException` nếu loader không tìm thấy một định nghĩa cho tên được yêu cầu.

Các tình huống:

| Tình huống | Hướng xử lý |
| --- | --- |
| Tên không nằm trong allowlist | `ClassNotFoundException` với thông điệp dễ debug |
| File mapped chưa tồn tại | `ClassNotFoundException` có cause `IOException` thích hợp |
| File nằm ngoài trusted root sau resolve symlink | Từ chối, không đọc; ví dụ dùng `ClassNotFoundException` với cause policy/IO |
| File không đọc được hoặc vượt byte cap | Từ chối theo policy; cause I/O và mô tả rõ |
| Bytes không phải class file hợp lệ | `defineClass` có thể ném `ClassFormatError` |
| Bytes mang binary name khác tên yêu cầu | JVM có thể ném `NoClassDefFoundError` cho wrong name |
| Class name trùng định nghĩa trái phép trong cùng loader | `LinkageError` |
| Vi phạm loader constraints khi liên kết | `LinkageError` phù hợp |

**Không nên bắt tất cả `Throwable` rồi chuyển hết thành `ClassNotFoundException`.** Làm vậy che `OutOfMemoryError`, `LinkageError` và vấn đề lập trình nghiêm trọng. Ví dụ chỉ catch `IOException` quanh phần đọc bytes; các errors do JVM ném từ `defineClass` tiếp tục mang ngữ nghĩa gốc.

Trong môi trường production, nếu một policy reject do file ngoài trusted root, có thể dùng loại lỗi policy nội bộ rõ hơn ở API phía trên loader; vì giao diện `findClass` yêu cầu `ClassNotFoundException` cho tình huống không cung cấp định nghĩa, việc gói cause có ý nghĩa trong cách triển khai mẫu.

## 12. Kiểm tra tên bên trong bytecode và type identity

`defineClass(name, bytes, 0, bytes.length)` không chỉ “đặt nhãn” tùy ý cho một mảng bytes. Class file chứa định danh kiểu nội bộ. JVM kiểm tra sự nhất quán giữa tên yêu cầu và định nghĩa; nếu mismatch hoặc bytes sai định dạng, việc define thất bại.

Ngoài ra, **runtime type identity** là sự kết hợp của:

~~~text
(binary class name, defining ClassLoader)
~~~

Hai loader khác nhau có thể định nghĩa cùng binary name từ cùng mảng bytes, thành hai kiểu runtime riêng. Vì vậy:

- `Class<?>` của hai loader có thể cùng `getName()` nhưng `a == b` là `false`.
- Cast object từ phiên bản A sang cùng-named class B có thể ném `ClassCastException`.
- Mỗi định nghĩa có static fields/initialization riêng.
- Một shared interface/API nên được định nghĩa bởi parent chung, không đóng nhiều bản API vào plugin loaders khác nhau.
- Mapping thay đổi nguồn bytes không “cập nhật” định nghĩa Class cũ đã nạp. Muốn hot reload thông thường cần tạo defining loader mới.

Class loader mapping và class identity liên hệ chặt chẽ: **nguồn bytes được chọn quyết định nội dung class, còn defining loader quyết định namespace runtime của class đó**.

## 13. Các kiểm tra an toàn tối thiểu và giới hạn thực tế

| Rủi ro | Kiểm tra tối thiểu | Giới hạn còn lại |
| --- | --- | --- |
| Arbitrary class name | Exact allowlist/manifest đã ký | Parent vẫn có thể nạp những tên khác |
| Path traversal | Relative path + canonical root + `Path.startsWith` | Concurrent filesystem changes cần mô hình mạnh hơn |
| Symlink ra ngoài root | Kiểm tra target `toRealPath` nằm trong root | Có TOCTOU race nếu kho cho phép sửa đồng thời |
| File size quá lớn | `readNBytes(MAX+1)` và từ chối nếu vượt | Nhiều class nhỏ vẫn tiêu thụ nhiều tổng memory |
| Bytecode giả mạo | Allowlisted artifact, integrity/hash/signature | Bytecode hợp lệ vẫn có thể thực thi tác dụng phụ |
| Dependency conflict | Parent API sharing, version policy | Cần testing, module/loader constraints |
| Network source độc hại | Fixed endpoint, auth, timeout, byte cap | Cần bảo vệ credential, retry và SSRF |
| Hot reload memory leak | Loader lifecycle và giải phóng references | Static caches, TCCL, threads có thể giữ loader |

**Nguyên tắc sản phẩm:** nếu plugin do bên không tin cậy cung cấp và cần ngăn đọc file/network/process APIs, hãy dùng **cách ly ở process/container/VM cùng OS permissions và policy** phù hợp. Java class loader chủ yếu cung cấp **cơ chế nạp và cô lập danh tính kiểu**, không phải thay thế security sandbox.

## 14. Cách viết test cho bounded mapping

Một bộ test tốt phải xác minh cả happy path lẫn policy rejects:

1. **Đúng tên, đúng nguồn:** `demo.plugins.Greeting` được define thành công từ file tương ứng.
2. **Tên ngoài allowlist:** `demo.plugins.Unknown` bị từ chối (trừ khi parent cung cấp theo chính sách đã chọn).
3. **Không có file:** cấu hình root thiếu file approved dẫn tới error hợp lý, không tự tìm file lân cận.
4. **Mismatched class bytes:** file được đặt tên Greeting.class nhưng bên trong là class khác; JVM không được im lặng chấp nhận tên yêu cầu.
5. **Quá byte cap:** nguồn vượt giới hạn bị từ chối mà không đọc vô hạn.
6. **Symlink ra ngoài root:** với filesystem cho phép symlinks, canonical target ngoài root bị từ chối.
7. **Parent class:** `java.lang.String` vẫn được tìm qua bootstrap, không bị self-define.
8. **Cùng tên ở parent:** biết chắc parent-first sẽ ưu tiên parent hay cần thay chính sách routing.
9. **Hai loader độc lập:** nếu mỗi loader define cùng bytes, xác nhận `classA != classB` và static state được cô lập.
10. **Nhiều thread yêu cầu cùng class:** dùng synchronization đúng `ClassLoader.loadClass` để không tự define trùng; tránh cache tự viết không an toàn.
11. **Root bị sửa khi loader hoạt động:** xác định policy chống race hoặc yêu cầu immutable data source.
12. **Log:** rejected names và causes đủ chẩn đoán, nhưng không tiết lộ đường dẫn nội bộ/bí mật cho user cuối nếu không cần.

Không cần dùng một framework cụ thể để kiểm thử, nhưng hãy đảm bảo test phân biệt **lỗi tìm class**, **policy reject**, **bytecode verification/linkage** và **lỗi static initializer**.

## 15. Những lỗi phổ biến khi tự thiết kế ánh xạ

**Lỗi 1: Ghép trực tiếp chuỗi input với path.** Dẫn tới path traversal, tên không đúng package, và quyền nạp class quá rộng.

**Lỗi 2: Chỉ kiểm tra string prefix.** `/data/plugins-evil` cũng bắt đầu bằng `/data/plugins` theo nghĩa chuỗi; dùng `Path.startsWith` trên canonical/real paths.

**Lỗi 3: Tin rằng normalize là đủ để ngăn symlink.** `normalize()` xử lý `.`/`..` ở mức cú pháp, **không tự giải quyết symbolic links**. `toRealPath` cung cấp thông tin thực tế khi file tồn tại; với kho có hostile concurrent writes vẫn cần bảo vệ khác.

**Lỗi 4: Dùng `Files.readAllBytes` không cap từ nguồn tùy ý.** Có nguy cơ cấp phát lớn hoặc cạn tài nguyên.

**Lỗi 5: Giả sử findClass allowlist kiểm soát cả parent.** `loadClass` mặc định hỏi parent trước; tên khác có thể được trả về từ parent.

**Lỗi 6: Định nghĩa lại `java.lang.*` hoặc shared API class.** Dễ gây vi phạm JVM constraints và xung đột danh tính kiểu.

**Lỗi 7: Nuốt mọi Throwable và báo ClassNotFoundException.** Che thông tin cấu trúc class file hỏng, lỗi liên kết, OOM hoặc lỗi chạy của static initializer.

**Lỗi 8: Tự gọi `resolveClass` và nghĩ đã chạy mã plugin.** Linking khác class initialization; cần hiểu thời điểm `<clinit>`.

**Lỗi 9: Đổi file trên đĩa rồi kỳ vọng `loadClass` trả Class cập nhật.** Class đã define thuộc loader cũ không tự biến đổi; có thể cần loader mới.

**Lỗi 10: Xem bytecode verification là sandbox.** Class hợp lệ có thể truy cập file, mạng hoặc API nguy hiểm tùy quyền của process.

**Lỗi 11: Bỏ qua package metadata/sealing/signers.** Khi chuyển sang loader đóng gói từ JAR, có thể cần bảo toàn quy tắc package sealing, code source, certificates và `ProtectionDomain` phù hợp; việc chỉ đọc bytes rồi gọi `defineClass` không tự tái hiện tất cả thông tin JAR packaging.

**Lỗi 12: Không ghi lại quyết định mapping.** Khi debug nhiều plugin cùng binary name, cần biết defining loader, artifact version và source identifier thực tế, không chỉ log một chuỗi tên class.

## 16. Khi nào dùng URLClassLoader hoặc API sẵn có?

Tự viết `ClassLoader` có ích khi cần kiểm soát đặc biệt về source mapping, verification policy và delegation. Nhưng nếu cần tải class từ một tập JAR URLs cố định, `URLClassLoader` (Java 17) có thể phù hợp và giảm nhu cầu tự đọc class bytes.

Trong JPMS, nếu plugin là named module thực sự, nên tìm hiểu `ModuleFinder`, `Configuration` và `ModuleLayer` để thiết kế module resolution/module loaders đúng ngữ nghĩa thay vì giả định một directory mapping đủ thay thế JPMS.

Một lựa chọn thực tế:

| Nhu cầu | Hướng thiết kế |
| --- | --- |
| Một số class cụ thể từ một thư mục được kiểm soát | Explicit allowlist + custom `findClass` |
| Nhiều JAR được phê duyệt, classpath-like loading | `URLClassLoader` và source/URL allowlist |
| Plugin có named modules, requires/exports | JPMS `ModuleFinder`/`ModuleLayer` |
| Bytecode được sinh động | `defineClass`/hidden-class APIs theo hợp đồng phù hợp |
| Code từ bên không tin cậy cần cách ly quyền hệ thống | Cách ly process/container, không dùng ClassLoader làm sandbox |

## 17. Tự kiểm tra

**1. Vì sao `name.replace('.', '/') + ".class"` chưa phải bounded mapping?**  
Vì nó chỉ chuyển tên sang đường dẫn, chưa giới hạn tên, nguồn dữ liệu, kích thước hay quyền truy cập.

**2. Exact allowlist tốt hơn package prefix trong trường hợp nào?**  
Khi chỉ có một tập nhỏ class được approved hoặc cần gắn từng class với artifact/hash/version cụ thể.

**3. Vì sao phải kiểm tra `candidate.toRealPath().startsWith(root.toRealPath())`?**  
Để nhận diện đích canonical ngoài root, kể cả khi path đi qua symlink; vẫn cần xét TOCTOU với kho có writer không tin cậy.

**4. Tại sao `findClass` từ chối tên Unknown nhưng `loader.loadClass("java.lang.String")` vẫn được?**  
Vì parent/bootstrap delegation diễn ra trước `findClass` trong default loader.

**5. Nếu file tên Greeting.class chứa bytecode của WrongName, JVM có coi nó là Greeting không?**  
Không; `defineClass` kiểm tra tính nhất quán của tên class file và có thể báo linkage error.

**6. Giới hạn 1 MiB bảo đảm code plugin không thể làm hại app không?**  
Không. Đây chỉ là byte cap cho việc đọc một class, không phải kiểm soát quyền hành vi của Java code.

**7. Vì sao không catch `Throwable` quanh `defineClass` để luôn trả `ClassNotFoundException`?**  
Vì phải giữ nguyên nghĩa lỗi class file/linkage và các lỗi nghiêm trọng như OOM để chẩn đoán đúng.

**8. Khi một parent loader đã có cùng binary name, child sẽ define bản của mình trong default `loadClass` không?**  
Thông thường không; parent-first delegation sẽ trả Class của parent.

**9. Một class đã load từ file, sửa file rồi gọi `loadClass` lần nữa sẽ có bytes mới không?**  
Không mặc nhiên. Class runtime đã define vẫn thuộc loader cũ; hot reload thường cần loader mới và quản lý lifecycle.

**10. Nếu cần ngăn plugin đọc filesystem thật sự, bounded ClassLoader có đủ không?**  
Không. Cần isolation/permissions ở mức process, OS, container hoặc VM theo threat model.

## 18. Tài liệu tham chiếu

- **Java SE 17 — ClassLoader**: `findClass`, `loadClass`, `defineClass`, `getClassLoadingLock`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html
- **Java SE 17 — Path**: `resolve`, `normalize`, `startsWith`, `toRealPath`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Path.html
- **Java SE 17 — Files**: `newInputStream`, `isRegularFile`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html
- **Java SE 17 — InputStream**: `readNBytes`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/InputStream.html
- **Java SE 17 — URLClassLoader**: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/URLClassLoader.html
- **JVMS 17 §5.3 — Creation and Loading** (defining/initiating loaders): https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html#jvms-5.3
- **JLS 17 §12.2 — Loading of Classes and Interfaces**: https://docs.oracle.com/javase/specs/jls/se17/html/jls-12.html#jls-12.2
