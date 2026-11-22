# Runtime image, jrt: và việc loại bỏ rt.jar

Từ **Java 9**, JDK chuyển sang mô hình **modular runtime image**: các lớp và tài nguyên của chính nền tảng Java được tổ chức trong những **module** của runtime, thay cho việc cung cấp phần lớn thư viện lõi qua tệp **`rt.jar`** như Java 8 trở về trước. Khi cần tham chiếu một tài nguyên của JDK mới, ta thường gặp URL có scheme **`jrt:`**, chẳng hạn `jrt:/java.base/java/lang/Object.class`.

Đây là thay đổi về **cách đóng gói và truy cập lớp của runtime**, liên quan trực tiếp tới cách các **built-in class loader** tìm các lớp nền tảng. Nó **không có nghĩa class loader bị loại bỏ**, JVM hết dùng bytecode `.class`, hay mọi JAR của ứng dụng cũng biến mất.

Bài này giải thích vì sao `rt.jar` không còn tồn tại, `jrt:` thực sự đại diện cho điều gì, sự khác nhau giữa module/runtime image/JAR/JMOD và cách quan sát bằng các API, công cụ Java 17 trở lên.

## 1. Runtime image là gì?

**Runtime image** là tập các thành phần cần thiết để chạy chương trình Java, bao gồm Java launcher, JVM, các module chứa thư viện và tài nguyên runtime cùng những thành phần native/configuration phù hợp.

Từ Java 9, runtime image được tổ chức theo **module**. Chẳng hạn:

- `java.base`: các API nền tảng như `java.lang`, `java.util`, `java.io`, `java.nio`; mọi module Java đều đọc `java.base` theo quy tắc của module system.
- `java.logging`: API ghi log chuẩn của Java.
- `java.sql`: các API JDBC.
- `java.xml`: các API XML chuẩn.
- Một số module `jdk.*`: công cụ hoặc API thuộc JDK, không nhất thiết hiện diện trong mọi runtime image.

Không phải runtime image nào cũng có cùng tập module. Một JDK đầy đủ thường bao gồm nhiều module/công cụ; **custom runtime image** do `jlink` tạo có thể chỉ bao gồm các module cần cho ứng dụng và phụ thuộc của chúng.

### So sánh mô hình trước và sau Java 9

~~~text
JDK 8 và trước (đơn giản hóa)
└─ JRE / thư mục runtime
   └─ lib/
      └─ rt.jar             ← nhiều lớp nền tảng, ví dụ java.lang.String
   └─ các thư viện, file và thành phần native khác

Java 9+ (đơn giản hóa)
└─ runtime image
   ├─ bin/java
   ├─ lib/modules           ← container runtime image của implementation JDK phổ biến
   ├─ conf/                 ← cấu hình runtime
   └─ các thư viện, file và thành phần native khác
           ↓
     module java.base, java.logging, java.sql, ...
~~~

Sơ đồ là **hình dung chức năng**, không phải cam kết rằng mọi bản phân phối Java/OS có chính xác cây thư mục trên. Đặc tả module và các API chuẩn quan trọng hơn việc mã ứng dụng giả định tên tệp nội bộ của JVM. Với HotSpot/OpenJDK, `lib/modules` thường dùng định dạng runtime image riêng, không phải một file ZIP/JAR có thể mở bằng `JarFile`.

**Phân biệt “runtime image” và “module”**: runtime image là toàn bộ môi trường chạy; mỗi module là một đơn vị tên và ranh giới phụ thuộc/đóng gói bên trong môi trường ấy. Một `module-info.class` mô tả module có chứa package nào, yêu cầu module nào, export/open package nào, v.v. Runtime image chứa nhiều module, không phải chỉ một “JAR khổng lồ” thay tên.

## 2. Vì sao `rt.jar` bị loại bỏ?

Ở Java 8, các lớp thuộc phần lớn thư viện runtime cốt lõi được lưu trong `rt.jar`. Công cụ cũ thường đi thẳng đến:

~~~text
<JAVA_HOME>/jre/lib/rt.jar
~~~

để tìm `java/lang/Object.class`, `java/lang/String.class` hoặc dùng `JarFile` duyệt tất cả lớp chuẩn.

Từ Java 9, **JEP 220 — Modular Run-Time Images** thay đổi cấu trúc runtime image để hỗ trợ mô hình module, đóng gói linh hoạt và quản lý nội bộ tốt hơn. Các tệp như **`rt.jar`**, **`tools.jar`**, **`dt.jar`** không còn tồn tại dưới vai trò cũ trong JDK modular. Cấu trúc `jre/` lồng bên trong thư mục cài đặt JDK cũng không còn theo cách cũ.

Thay đổi giải quyết nhiều vấn đề:

1. **Tổ chức theo module**: thư viện chuẩn có danh tính, phụ thuộc và quy tắc truy cập rõ ràng hơn so với một tập class phẳng.
2. **Tạo runtime vừa đủ**: `jlink` có thể ghép các module cần thiết để phân phối một runtime image riêng cho ứng dụng.
3. **Cho JVM và công cụ linh hoạt về biểu diễn nội bộ**: không buộc mọi implementation phải dùng cấu trúc ZIP của `rt.jar`.
4. **Hạn chế code phụ thuộc đường dẫn triển khai**: ứng dụng và công cụ có giao diện như `jrt:` và Java API để truy cập module/resource theo cách phù hợp.

**Điều không thay đổi:** bytecode vẫn dựa trên định dạng **ClassFile**; Java vẫn nạp lớp, xác minh bytecode, liên kết và khởi tạo lớp. JAR vẫn rất phổ biến để đóng gói thư viện/ứng dụng, cả ở classpath và module path. Việc bỏ `rt.jar` chỉ áp dụng cho **cách đóng gói lớp runtime của JDK**, không xóa bỏ định dạng `.jar`.

## 3. `jrt:` là gì?

`jrt:` viết tắt theo cách hiểu thực hành là **Java runtime image protocol/scheme**. Nó cung cấp một **không gian địa chỉ logic** cho module, lớp và tài nguyên lưu trong runtime image, giúp công cụ dùng URI/URL để truy cập mà không biết file container nội bộ được tổ chức ra sao.

Ví dụ:

~~~text
jrt:/java.base/java/lang/Object.class
│    │         └─ đường dẫn resource/class bên trong module
│    └─ tên module java.base
└─ scheme jrt
~~~

Với JDK 17 tiêu chuẩn, `ClassLoader.getSystemResource("java/lang/Object.class")` có thể trả URL:

~~~text
jrt:/java.base/java/lang/Object.class
~~~

trong khi trước Java 9, cùng mục đích truy cập tài nguyên có thể tạo URL dạng:

~~~text
jar:file:/.../jre/lib/rt.jar!/java/lang/Object.class
~~~

Điểm quan trọng là **`jrt:` không phải đường dẫn file thông thường trên ổ đĩa**. `jrt:/java.base/java/lang/Object.class` không có nghĩa một thư mục vật lý tên `jrt:` nằm trên ổ đĩa, cũng không phải lệnh HTTP tải class từ mạng.

### Scheme `jrt:` khác `jar:` và `file:`

| Scheme | Ý nghĩa thường gặp | Ví dụ |
| --- | --- | --- |
| `file:` | File hoặc thư mục được hệ điều hành cung cấp. | `file:/opt/app/classes/Demo.class` |
| `jar:` | Entry nằm bên trong một JAR/ZIP được tham chiếu qua URL. | `jar:file:/opt/app/lib/api.jar!/com/example/Api.class` |
| `jrt:` | Module và resource bên trong **runtime image**. | `jrt:/java.base/java/lang/Object.class` |

`jrt:` giải quyết bài toán **định danh/truy cập resource**, còn việc lớp thực sự do bootstrap, platform hay application loader định nghĩa là khía cạnh **class loading**. Không được nhìn scheme `jrt:` rồi suy ra “tất cả các lớp qua `jrt:` đều thuộc bootstrap loader”.

## 4. Runtime image cung cấp một hệ thống file ảo `jrt`

Bên cạnh URL `jrt:`, JDK hiện đại có **NIO FileSystem Provider** cho runtime image. Gốc filesystem mang URI `jrt:/`.

Một cấu trúc thường gặp khi duyệt bằng provider:

~~~text
jrt:/
├── modules/
│   ├── java.base/
│   │   ├── module-info.class
│   │   ├── java/lang/Object.class
│   │   └── ...
│   ├── java.logging/
│   └── ...
└── packages/
    ├── java.lang/
    ├── java.util/
    └── ...
~~~

**Cực kỳ dễ nhầm hai loại đường dẫn**:

- **URL đến resource**: `jrt:/java.base/java/lang/Object.class`.
- **Path trong `jrt` FileSystem**: `/modules/java.base/java/lang/Object.class`.

Đây là **hai cách biểu diễn cùng nguồn dữ liệu logic** theo quy ước của hai API khác nhau. Khi dùng `Files.exists` hoặc `Files.readAllBytes` với JRT NIO FileSystem, lấy `Path` từ provider và dùng cấu trúc `/modules/...`; không tự tạo `Path.of("jrt:/...")` rồi mong hệ thống file mặc định hiểu scheme ấy.

Các đường dẫn `/packages/...` có thể hỗ trợ tra cứu package → module trong cấu trúc ảo; nó không có nghĩa các package bắt buộc tồn tại thành thư mục thật. Nội dung mỗi image phụ thuộc tập module được liên kết vào image đó.

## 5. Ví dụ Java 17: đọc lớp trong `java.base` qua URL và JRT FileSystem

Tạo tệp **`RuntimeImageExplorer.java`**:

~~~java
import java.net.URI;
import java.net.URL;
import java.nio.file.FileSystem;
import java.nio.file.FileSystems;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Map;

public class RuntimeImageExplorer {
    public static void main(String[] args) throws Exception {
        Module module = Object.class.getModule();
        URL resource = Object.class.getResource("Object.class");

        System.out.println("Module: " + module.getName());
        System.out.println("Resource scheme: " + resource.getProtocol());

        URI imageUri = URI.create("jrt:/");
        try (FileSystem image = FileSystems.newFileSystem(imageUri, Map.of())) {
            Path classFile = image.getPath(
                    "/modules/java.base/java/lang/Object.class");

            System.out.println("Class exists: " + Files.isRegularFile(classFile));

            byte[] bytes = Files.readAllBytes(classFile);
            System.out.printf(
                    "ClassFile magic: %02X%02X%02X%02X%n",
                    bytes[0] & 0xFF,
                    bytes[1] & 0xFF,
                    bytes[2] & 0xFF,
                    bytes[3] & 0xFF);
        }
    }
}
~~~

Biên dịch/chạy bằng **JDK 17 hoặc mới hơn**, từ thư mục chứa file:

~~~bash
javac --release 17 RuntimeImageExplorer.java
java RuntimeImageExplorer
~~~

Trên **JDK 17 tiêu chuẩn có provider `jrt`**, stdout là:

~~~text
Module: java.base
Resource scheme: jrt
Class exists: true
ClassFile magic: CAFEBABE
~~~

Giải thích:

1. `Object.class.getModule()` trả module định nghĩa `java.lang.Object`, đó là `java.base`.
2. `Object.class.getResource("Object.class")` định vị resource cùng package; URL thuộc scheme `jrt` trên runtime modular tiêu chuẩn.
3. `FileSystems.newFileSystem(URI.create("jrt:/"), Map.of())` mở một `FileSystem` do JRT provider cung cấp. `try` bảo đảm filesystem được đóng sau khi dùng.
4. `image.getPath("/modules/java.base/java/lang/Object.class")` trỏ tới ClassFile trong cấu trúc ảo của runtime image.
5. Bốn byte đầu ClassFile là `CA FE BA BE` (magic number của định dạng ClassFile); `%02X` và phép `& 0xFF` hiển thị từng byte theo hệ 16.

**Giới hạn của ví dụ:** Nó cần một môi trường JDK modular thực tế và provider `jrt`; nếu image tùy biến hoặc JVM khác không có resource/provider mong đợi, chương trình có thể không hoạt động như trên. Trong ứng dụng thật, nên kiểm tra `resource != null` trước khi dùng và xử lý `IOException`/lỗi provider phù hợp. Không hard-code rằng mọi class ứng dụng đều thuộc module `java.base`; đó chỉ là trường hợp của `Object.class`.

### Nếu chỉ cần xác định module của một lớp

Bạn không cần đọc bytecode:

~~~java
System.out.println(String.class.getModule().getName());
System.out.println(String.class.getClassLoader());
~~~

Đoạn trên là **fragment**, có thể đặt trong method. Trên JDK thông thường, `String.class` thuộc `java.base` và `String.class.getClassLoader()` trả `null` để biểu diễn **bootstrap loader** trong API. `null` không đồng nghĩa JVM không dùng cơ chế nạp lớp. Một class ứng dụng nằm trên classpath thông thường thuộc **unnamed module** của defining class loader và không nhất thiết có URL `jrt:`.

## 6. Runtime image có liên quan thế nào tới ba built-in class loader?

Trong Java hiện đại, ba loader thường được nhắc tới:

| Loader | Vai trò khái quát |
| --- | --- |
| **Bootstrap class loader** | Loader gắn với JVM, định nghĩa các lớp nền tảng cốt yếu, trong đó có phần lớn `java.base`; Java API thường trả `null` cho loader này. |
| **Platform class loader** | Định nghĩa nhiều lớp trong các module nền tảng khác của JDK; truy cập qua `ClassLoader.getPlatformClassLoader()`. |
| **Application/system class loader** | Phụ trách các lớp ứng dụng và nhiều thư viện quan sát được trên classpath/module path; truy cập qua `ClassLoader.getSystemClassLoader()`. |

Trước Java 9, nhiều tài liệu giải thích bootstrap loader đọc class từ `rt.jar`, extension loader đọc từ `lib/ext`, application loader đọc từ classpath. **Không dùng nguyên xi mô hình vị trí lưu trữ đó cho Java 9+**. Cơ chế extension loader và thư mục `lib/ext` thuộc mô hình cũ; platform loader thay thế vai trò trong thiết kế mới, với tổ chức module khác trước.

Một sơ đồ đúng ở mức tổng quan:

~~~text
             Runtime image (nhiều module)
                  │
                  ├── java.base
                  ├── java.logging
                  ├── java.sql
                  └── module JDK khác
                        │
                        ▼
             Built-in loader thích hợp
                        │
                  định nghĩa Class
                        ▼
               JVM liên kết/khởi tạo

     Classpath và module path của ứng dụng
                        │
                        ▼
         Application hoặc custom loader
                        │
                  định nghĩa Class
~~~

Sơ đồ **không có nghĩa tất cả module được nạp đồng loạt lúc khởi động**. Module resolution thiết lập đồ thị module cho một lần chạy; việc nạp từng class và thời điểm khởi tạo class là hoạt động khác.

**Parent delegation vẫn có vai trò**, nhưng bạn không thể suy từ đường dẫn `lib/modules` rằng bootstrap loader nạp tất cả mọi module. Một số module được gán cho platform hoặc application loader; các custom loader có thể cùng tồn tại. Ngoài ra, khả năng module đọc module khác (`requires`), export/open package là các quy tắc truy cập cấp module, không phải tên gọi khác của parent delegation.

## 7. `rt.jar` khác `lib/modules`, `jmods` và JAR thư viện thế nào?

Ba vị trí/định dạng này thường bị hiểu sai là tương đương:

| Mục | Mục đích | Có trực tiếp dùng như JAR classpath không? |
| --- | --- | --- |
| **`rt.jar`** (Java 8 trở về trước) | Chứa nhiều lớp nền tảng của Java trong JAR runtime cũ. | Là JAR, nhưng thuộc runtime do JVM quản lý, không phải thư viện ứng dụng thông thường. |
| **`lib/modules`** (JDK modular phổ biến) | Container triển khai nội bộ cho module trong **runtime image** đang chạy. | **Không.** Không coi là ZIP/JAR hay dependency ứng dụng để đưa vào `-cp`. |
| **`jmods/*.jmod`** (JDK đầy đủ, khi có) | Các artifact module đầu vào thường dùng bởi công cụ như `jlink`. | **Không.** JMOD khác JAR và không phải định dạng đặt trực tiếp trên runtime module path. |
| **JAR thường**, kể cả **modular JAR** | Phân phối thư viện hoặc ứng dụng. | Có thể dùng trên classpath hoặc module path, tùy cấu hình và tính chất JAR. |

Đặc biệt, một **JMOD** có thể đóng gói cả class và tài nguyên/native file để hỗ trợ lắp ghép runtime image. Còn `jrt:` biểu diễn dữ liệu **đã nằm trong runtime image**, không phải một scheme dẫn đến tệp `.jmod` bất kỳ trên ổ đĩa.

Java 9+ không buộc mọi ứng dụng phải tự viết `module-info.java` hoặc chuyển mọi dependency thành JMOD. **Classpath và unnamed module vẫn được hỗ trợ**. Việc thư viện bên ngoài nằm trong `.jar` không mâu thuẫn với việc `rt.jar` của JDK đã bị loại bỏ.

## 8. Công cụ quan sát runtime image

Các lệnh dưới đây dùng **JDK 17+** khi công cụ tương ứng được cài cùng JDK. Chúng là ví dụ công cụ CLI và không chỉnh sửa runtime hiện có.

### 8.1. Liệt kê module có sẵn

~~~bash
java --list-modules
~~~

Kết quả có thể chứa:

~~~text
java.base@17...
java.logging@17...
java.sql@17...
~~~

Dấu `...` là **ký hiệu lược bớt phiên bản và các dòng khác trong ví dụ**, không phải phần cố định của output. Danh sách thật phụ thuộc bản JDK/runtime image. `--list-modules` giúp trả lời “runtime hiện tại có module nào?”, nhưng không nói những class nào đã được tải vào JVM.

### 8.2. Xem chi tiết module

~~~bash
java --describe-module java.base
~~~

Lệnh cho biết metadata `java.base`: package export, module requirements và thông tin module khác theo format của Java launcher. Đây là thông tin **module system**, không phải toàn bộ nội dung bytecode của mỗi `.class`.

### 8.3. Xem một ClassFile chuẩn bằng javap

~~~bash
javap -c java.lang.String
~~~

`javap` phân tích định nghĩa lớp/bytecode để trình bày các phương thức. Nếu muốn chi tiết constant pool/attributes, dùng `javap -v java.lang.String` (output rất dài). Không cần tìm `rt.jar` và trích xuất `String.class` thủ công.

### 8.4. Xem container runtime bằng jimage

~~~text
jimage list <path-to-JDK>/lib/modules
~~~

Thay `<path-to-JDK>` bằng đường dẫn cài đặt JDK thực tế. `jimage` là công cụ trên JDK hỗ trợ định dạng container triển khai do JDK cung cấp; đường dẫn ví dụ có thể khác theo runtime. Đây là lựa chọn cho **công cụ phân tích**, không phải giao diện mà ứng dụng nên phụ thuộc để tìm class.

### 8.5. Tạo image tối giản bằng jlink

Ví dụ trên một JDK có `jlink` và các module đầu vào mặc định:

~~~bash
jlink --add-modules java.base --output minimal-runtime
~~~

Sau đó, trên Linux/macOS:

~~~bash
./minimal-runtime/bin/java --list-modules
~~~

Hoặc trên Windows PowerShell:

~~~powershell
.\minimal-runtime\bin\java.exe --list-modules
~~~

Image mới chỉ gồm `java.base` và phụ thuộc cần thiết (nếu có), nên nhiều module khác của JDK đầy đủ không hiện diện. `jlink` **tạo thư mục output mới**; nếu tên thư mục đã tồn tại, cần chọn tên output khác. Ví dụ chỉ nhằm minh họa khả năng cắt gọn runtime; không phải chỉ dẫn đóng gói đầy đủ một ứng dụng phức tạp. Ứng dụng thực tế phải đưa vào đầy đủ các module và phụ thuộc cần thiết, kể cả dịch vụ được nạp động khi phù hợp.

## 9. Di chuyển code cũ từng phụ thuộc `rt.jar`

Một pattern ở Java 8 có thể như sau:

~~~java
// Ví dụ anti-pattern: code cũ tự dò rt.jar từ thư mục cài Java.
String path = System.getProperty("java.home") + "/lib/rt.jar";
~~~

Đây là **fragment minh họa lỗi thiết kế**, không phải chương trình chạy độc lập và cũng không phải quy tắc đúng cho mọi layout JDK 8. Nếu sau đó mở đường dẫn bằng `new JarFile(path)`, nó sẽ thất bại trên JDK 9+ vì `rt.jar` không tồn tại.

Hãy chọn giải pháp theo mục đích thật:

| Nhu cầu | Cách tiếp cận phù hợp trên JDK hiện đại |
| --- | --- |
| **Nạp hoặc dùng class chuẩn** | Dùng API Java thông thường hoặc `Class.forName(...)` phù hợp; JVM và loader quyết định nguồn class. |
| **Tìm resource của một lớp** | `SomeClass.class.getResource(...)` hoặc `getResourceAsStream(...)`. |
| **Tìm resource qua system class loader** | `ClassLoader.getSystemResource(...)`, đồng thời xử lý kết quả `null` và URL `jrt:`. |
| **Duyệt class/resource của module trong runtime image** | JRT FileSystem Provider (`FileSystems.newFileSystem(URI.create("jrt:/"), ...)`) hoặc công cụ `jimage`. |
| **Tìm module nào chứa class/định nghĩa** | `SomeClass.class.getModule()`, `ModuleLayer` hoặc các công cụ mô-đun khi phù hợp. |
| **Xây runtime phân phối cùng ứng dụng** | `jlink`, sau khi phân tích module dependencies và provider cần dùng. |
| **Phân tích bytecode** | `javap` cho nhu cầu cơ bản; thư viện đọc ClassFile thích hợp cho công cụ chuyên sâu. |

Không nên chuyển mọi đoạn `rt.jar` sang đường dẫn hard-code `$JAVA_HOME/lib/modules`. Mục tiêu là **loại bỏ sự phụ thuộc vào đường dẫn/định dạng container nội bộ**. Cũng không nên coi `jrt:/` là đường dẫn classpath cần bổ sung thủ công: các lớp runtime đã được hệ thống module và built-in loader quản lý.

### Đọc tài nguyên an toàn bằng InputStream

Nếu chỉ cần đọc bytes của một resource, API trên chính class thường dễ dùng hơn thao tác đường dẫn:

~~~java
try (var stream = Object.class.getResourceAsStream("Object.class")) {
    if (stream == null) {
        throw new IllegalStateException("Cannot locate Object.class");
    }
    byte[] bytes = stream.readAllBytes();
    System.out.println(bytes.length > 4);
}
~~~

Đây là **fragment** để đặt trong method có khả năng ném/điều khiển `IOException`. Với JDK chuẩn, nó in `true`; dùng `getResourceAsStream` tránh giả định rằng URL phải có `file:` hoặc `jar:` scheme. Đọc nguyên ClassFile chỉ phù hợp khi thực sự cần bytes; sử dụng API của lớp không cần tự đọc `.class`.

## 10. Những giới hạn và lỗi thường gặp

### 10.1. `FileSystems` mặc định không tự hiểu `jrt:`

`Path.of("jrt:/java.base/java/lang/Object.class")` tạo path theo **default filesystem** (có thể trở thành chuỗi tên file bình thường), không đại diện cho JRT resource. Cần dùng `Path` từ JRT provider như ví dụ ở mục 5.

### 10.2. Không được cast system/platform loader thành URLClassLoader

Trên Java 9+, built-in application và platform loader có triển khai nội bộ khác JDK 8; code kiểu:

~~~java
// Sai giả định trên JDK hiện đại:
java.net.URLClassLoader loader =
        (java.net.URLClassLoader) ClassLoader.getSystemClassLoader();
~~~

có thể ném `ClassCastException`. Đây là đoạn anti-pattern minh họa **có thể biên dịch**, nhưng không nên thực thi để quản lý classpath. Dùng API `ClassLoader`/module chuẩn hoặc custom loader được thiết kế rõ ràng thay cho ép kiểu.

### 10.3. Đường dẫn resource có thể thay đổi hoặc không truy cập được

Không phải mọi resource đều công khai để tra cứu từ mọi module/loader. Module encapsulation có thể ảnh hưởng `getResource` hoặc `getResourceAsStream` trong các trường hợp không phải lớp/bao bọc API công khai. Các custom runtime image có thể thiếu module mà bạn đang tìm. Luôn kiểm tra `null`, quyền truy cập và điều kiện module thay vì coi có JDK là tồn tại mọi module.

### 10.4. `jrt:` không chứng minh module đang khởi tạo

Có đường dẫn `jrt:/java.base/...class` chỉ xác nhận resource/định nghĩa tương ứng có thể được cung cấp; điều đó không nói class đang initialized, đã tạo object hay đã được JIT compile. **Resource resolution**, **class loading**, **class linking**, **class initialization** là các hoạt động khác nhau.

### 10.5. Không “patch” `lib/modules` bằng sửa byte thủ công

Container runtime image là chi tiết triển khai, không phải JAR tương thích để người dùng trực tiếp thay entry. Việc sửa thủ công có thể làm hỏng runtime hoặc phá các giả định của JVM/công cụ. Khi cần bổ sung thư viện, hãy dùng classpath/module path và quy trình build; khi cần image mới, hãy dùng `jlink` với tập module phù hợp.

### 10.6. Không nhầm JMOD, JAR và runtime image

- **Modular JAR** có `module-info.class` và có thể được đưa trên module path.
- **JMOD** thường dùng để cung cấp nội dung cho linking và các công cụ JDK; không dùng như dependency JAR trên runtime module path.
- **Runtime image** là môi trường đã được tổ hợp để thực thi, với danh sách module và cấu trúc phù hợp implementation.

## 11. Tự kiểm tra

**Câu 1.** Java 17 có cần `rt.jar` để dùng `java.lang.String` không?

**Trả lời:** Không. Các lớp nền tảng nằm trong module của runtime image, và JVM cùng built-in loader cung cấp việc định nghĩa lớp theo cơ chế hiện đại.

**Câu 2.** URL `jrt:/java.base/java/lang/Object.class` là đường dẫn vật lý tới một file JAR?

**Trả lời:** Không. Đây là URL logic có scheme `jrt:`, chỉ resource thuộc module `java.base` trong runtime image. API/provider che giấu cấu trúc container triển khai.

**Câu 3.** Vì sao khi dùng JRT FileSystem lại lấy `/modules/java.base/java/lang/Object.class`?

**Trả lời:** JRT NIO FileSystem trình bày một cây ảo gồm `/modules/...`. Quy ước `Path` này khác với cú pháp URL tài nguyên `jrt:/java.base/...`.

**Câu 4.** Có thể thêm `$JAVA_HOME/lib/modules` vào classpath để thay `rt.jar` không?

**Trả lời:** Không nên và không đúng ý nghĩa: `lib/modules` là file/container của runtime image, không phải JAR dependency trên classpath. Loader của JVM đã quản lý các module hệ thống.

**Câu 5.** `jlink` tạo gì và ứng dụng cần chú ý gì?

**Trả lời:** Nó tạo custom runtime image gồm module gốc được chọn và các phụ thuộc được giải quyết. Ứng dụng phải xác định đúng những module cần lúc chạy, kể cả các provider chỉ xuất hiện qua nạp động.

**Câu 6.** `Object.class.getClassLoader() == null` trên JDK phổ biến có nghĩa là không có class loading?

**Trả lời:** Không. `null` là cách API biểu diễn bootstrap loader; class vẫn được JVM nạp/định nghĩa theo cơ chế thích hợp.

## 12. Ghi nhớ và tài liệu chuẩn

**Nắm ba ý chính:**

1. Từ Java 9, **`rt.jar` bị loại bỏ**, các lớp chuẩn thuộc module trong **modular runtime image**; đây là sự thay đổi cấu trúc phân phối JDK, không phải xóa JAR của thư viện ứng dụng.
2. **`jrt:`** là scheme truy cập logic tới resource của runtime image. Để duyệt như filesystem, dùng **JRT NIO provider** và `/modules/<module>/...`; không phụ thuộc đường dẫn vật lý của container.
3. **Built-in class loader vẫn định nghĩa lớp**; module graph, loader và class initialization là những khái niệm riêng. Để sửa code cũ, thay thao tác trực tiếp trên `rt.jar` bằng **API resource/module phù hợp**, `javap`, `jimage` hoặc `jlink` tùy mục đích.

**Tài liệu chính thức:**

- OpenJDK, **JEP 220: Modular Run-Time Images** — https://openjdk.org/jeps/220
- Oracle, **Migrating From JDK 8 to Later JDK Releases**, mục *Removed rt.jar and tools.jar* — https://docs.oracle.com/en/java/javase/17/migrate/migrating-jdk-8-later-jdk-releases.html
- Oracle Java SE 17 API, **module `java.base`**, phần JRT file system provider — https://docs.oracle.com/en/java/javase/17/docs/api/java.base/module-summary.html
- Oracle Java SE 17, **jlink** — https://docs.oracle.com/en/java/javase/17/docs/specs/man/jlink.html
