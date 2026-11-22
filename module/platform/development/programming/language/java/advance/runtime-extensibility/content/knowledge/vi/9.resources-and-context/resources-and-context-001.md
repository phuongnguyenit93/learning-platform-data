# Tìm một hoặc nhiều tài nguyên bằng getResource, getResources và getResourceAsStream

Một ứng dụng Java thường cần đọc những tệp **đi cùng mã đã biên dịch**: cấu hình mặc định, template, câu lệnh SQL, bản địa hóa, dữ liệu mẫu hoặc thông tin mô tả plugin. Khi triển khai bằng JAR, nhiều tệp này **không còn là file thông thường nằm trong thư mục làm việc**. Java cung cấp cơ chế tìm **resource theo tên logic** thông qua `Class` và `ClassLoader` để chương trình hoạt động nhất quán hơn giữa môi trường phát triển, bản đóng gói JAR và hệ thống có nhiều class loader.

Ba thao tác cốt lõi có ý nghĩa riêng:

- **`getResource(name)`**: tìm **một** resource và trả về `URL`, hoặc `null` khi không tìm được; URL phù hợp nếu cần biết vị trí nguồn hoặc muốn chủ động mở luồng đọc.
- **`getResources(name)`**: tìm **nhiều** resource có **cùng tên chính xác**, trả về `Enumeration<URL>`; phù hợp với kiến trúc plugin có nhiều JAR đóng góp cùng một tài nguyên.
- **`getResourceAsStream(name)`**: trả về `InputStream` để **đọc nội dung**, hoặc `null` nếu không lấy được stream; thường thuận tiện khi không cần URL.

**Phải xác định đối tượng gọi:** `SomeClass.class.getResource(...)` và `someClassLoader.getResource(...)` có quy tắc phân giải tên khác nhau. Trong ứng dụng mở rộng lúc chạy, **class loader được chọn** cũng quyết định bạn nhìn thấy những JAR/resource nào.

## 1. Resource trong Java là gì?

Resource ở đây là một entry có tên mà lớp/module hoặc class loader có thể tìm được; nó không nhất thiết là một tệp độc lập trên ổ đĩa.

Ví dụ, cấu trúc nguồn dự kiến:

```text
src/
  demo/resources/
    ResourceLookupDemo.java

resources/
  main/
    demo/resources/messages/welcome.txt
    config/app.properties
    config/choice.txt
  second/
    config/choice.txt
```

Nếu chạy ứng dụng với `resources/main` và `resources/second` trên classpath:

- Tên resource `demo/resources/messages/welcome.txt` chỉ tới nội dung tương ứng trong `resources/main`.
- `config/app.properties` nằm ở gốc classpath của thư mục `resources/main`.
- **Hai** nơi cùng cung cấp tên `config/choice.txt`; `getResources("config/choice.txt")` có thể cho cả hai vị trí theo cơ chế tìm kiếm của class loader.
- Khi đóng `resources/main` vào JAR, tên logic trên vẫn giữ nguyên dù hệ điều hành không nhìn thấy nó như một file rời.

**Không đồng nhất:**

| Khái niệm | Ý nghĩa |
|---|---|
| Đường dẫn resource | Tên tương đối trong không gian mà `Class`/`ClassLoader` quản lý, ví dụ `config/app.properties` |
| Classpath entry | Một thư mục hoặc JAR mà class loader có thể tìm class/resource |
| `URL` resource | Địa chỉ trỏ tới resource, có thể là `file:`, `jar:file:...!/`, `jrt:` hoặc giao thức khác do loader cung cấp |
| `Path` filesystem | Đường dẫn theo filesystem provider; **không tự đồng nghĩa** với một entry nằm bên trong JAR |
| Working directory | Thư mục hiện hành của tiến trình; không mặc định là gốc classpath hoặc gốc JAR |

`new File("config/app.properties")` và `getResource("config/app.properties")` tìm ở hai không gian khác nhau. Lệnh `new File(...)` dùng filesystem theo thư mục hiện hành (nếu là đường dẫn tương đối), còn `getResource(...)` phụ thuộc class/module loader và tên resource.

## 2. Những API cần phân biệt

| API | Đầu vào `name` | Kết quả | Khi dùng |
|---|---|---|---|
| `Class.getResource(String)` | Tương đối với package của class, hoặc bắt đầu bằng `/` để tính từ gốc resource | `URL` hoặc `null` | Resource gắn với chính class, package, module |
| `Class.getResourceAsStream(String)` | Quy tắc tên như `Class.getResource` | `InputStream` hoặc `null` | Đọc template/config nằm cạnh class |
| `ClassLoader.getResource(String)` | Tên từ gốc không gian resource, **không có dấu `/` ở đầu** | `URL` hoặc `null` | Tìm một resource bằng loader đã chọn |
| `ClassLoader.getResources(String)` | Tên từ gốc không gian resource | `Enumeration<URL>`; có thể rỗng; phương thức có thể ném `IOException` | Tìm tất cả vị trí cùng tên để tự tổng hợp/xử lý xung đột |
| `ClassLoader.getResourceAsStream(String)` | Tên từ gốc không gian resource | `InputStream` hoặc `null` | Đọc resource bằng loader đã chọn mà không cần URL |

### 2.1. `Class.getResource`: tên tương đối và tên tuyệt đối

Giả sử class là `demo.resources.ResourceLookupDemo`:

```java
// Tìm từ package demo.resources:
URL a = ResourceLookupDemo.class.getResource("messages/welcome.txt");

// Tìm từ gốc không gian resource bằng dấu / đầu tiên:
URL b = ResourceLookupDemo.class.getResource(
        "/demo/resources/messages/welcome.txt");
```

Cả hai dùng tên logic `demo/resources/messages/welcome.txt`. Một lời gọi như `ResourceLookupDemo.class.getResource("config/app.properties")` lại tìm `demo/resources/config/app.properties`, **không** phải `config/app.properties` ở gốc.

Dấu `/` đầu tiên là quy tắc **riêng của `Class.getResource`**, được xử lý để tạo tên tuyệt đối trong không gian resource. Nó không có nghĩa là đường dẫn gốc filesystem của hệ điều hành.

### 2.2. `ClassLoader.getResource`: luôn dùng tên từ gốc

```java
ClassLoader loader = ResourceLookupDemo.class.getClassLoader();

URL a = loader.getResource("demo/resources/messages/welcome.txt");
URL b = loader.getResource("config/app.properties");
```

Khác với `Class`, `ClassLoader` không tự thêm package của class và không dùng `/` đầu tiên làm cú pháp “tuyệt đối” để bỏ package. Vì thế, quy tắc an toàn và rõ ràng khi gọi `ClassLoader.getResource`/`getResources`/`getResourceAsStream` là **tên không bắt đầu bằng `/`**.

`Class.getClassLoader()` có thể trả `null` cho class do bootstrap loader định nghĩa. Ví dụ trên dùng class của ứng dụng do application loader nạp nên có loader. Với thư viện phổ biến, nên chọn rõ loader theo hợp đồng thư viện thay vì luôn giả định một loader duy nhất trong cả JVM.

### 2.3. `getResourceAsStream`: đọc ngay, nhưng phải đóng

Khi chỉ cần nội dung, `getResourceAsStream` tránh việc phải thao tác trực tiếp với `URL`:

```java
try (InputStream in = ResourceLookupDemo.class.getResourceAsStream(
        "messages/welcome.txt")) {
    if (in == null) {
        throw new IllegalStateException("Missing welcome resource");
    }
    // Đọc từ in trong phạm vi try, sau đó đóng tự động.
}
```

Đoạn trên là **minh họa một phạm vi đọc**, cần thêm `import java.io.InputStream;` và logic đọc thực tế nếu đặt trong chương trình riêng. Trong code production, kiểm tra `null` **trước** khi phụ thuộc vào stream; `try-with-resources` hỗ trợ đóng stream sau khi đọc, kể cả lúc xử lý nội dung ném lỗi. Lỗi I/O khi đọc vẫn cần được báo đúng.

Không dùng `InputStream.available()` để suy ra toàn bộ kích thước tài nguyên; nó chỉ cho biết lượng byte có thể đọc ngay trong một số điều kiện, không phải kích thước file. Với nội dung văn bản hãy chủ động chọn charset, thường là UTF-8.

## 3. Ví dụ Java 17 chạy được: tìm một, tìm nhiều và đọc stream

Ví dụ sau cho thấy cùng một file có thể được tìm bằng `Class` hoặc `ClassLoader`, đồng thời phát hiện hai resource trùng tên `config/choice.txt`. Để stdout không phụ thuộc vào thứ tự phát hiện từ loader, nội dung của hai resource được **sắp xếp** trước khi in.

### 3.1. Tạo cấu trúc và nội dung chính xác

Tệp `src/demo/resources/ResourceLookupDemo.java`:

```java
package demo.resources;

import java.io.BufferedReader;
import java.io.IOException;
import java.io.InputStream;
import java.io.InputStreamReader;
import java.net.URL;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.Collections;
import java.util.Enumeration;
import java.util.List;

public final class ResourceLookupDemo {

    private ResourceLookupDemo() {}

    private static String firstLine(InputStream input) throws IOException {
        if (input == null) {
            return "<missing>";
        }
        try (BufferedReader reader = new BufferedReader(
                new InputStreamReader(input, StandardCharsets.UTF_8))) {
            return reader.readLine();
        }
    }

    private static String firstLine(URL url) throws IOException {
        if (url == null) {
            return "<missing>";
        }
        return firstLine(url.openStream());
    }

    public static void main(String[] args) throws IOException {
        ClassLoader loader = ResourceLookupDemo.class.getClassLoader();

        URL relative = ResourceLookupDemo.class.getResource(
                "messages/welcome.txt");
        URL absolute = ResourceLookupDemo.class.getResource(
                "/demo/resources/messages/welcome.txt");
        URL fromLoader = loader.getResource(
                "demo/resources/messages/welcome.txt");

        System.out.println("Class relative: " + firstLine(relative));
        System.out.println("Class absolute: " + firstLine(absolute));
        System.out.println("Class stream: " + firstLine(
                ResourceLookupDemo.class.getResourceAsStream(
                        "messages/welcome.txt")));
        System.out.println("Loader URL: " + firstLine(fromLoader));
        System.out.println("Loader stream: " + firstLine(
                loader.getResourceAsStream("config/app.properties")));

        Enumeration<URL> matches = loader.getResources(
                "config/choice.txt");
        List<String> values = new ArrayList<>();

        while (matches.hasMoreElements()) {
            URL location = matches.nextElement();
            values.add(firstLine(location));
        }
        Collections.sort(values);

        System.out.println("Matches: " + values.size());
        System.out.println("All matches: " + values);
        System.out.println("Missing URL: " +
                (loader.getResource("config/not-found.txt") == null));
    }
}
```

Nội dung **một dòng** của từng resource (có thể kết thúc bằng newline thông thường):

`resources/main/demo/resources/messages/welcome.txt`:

```text
Hello from package
```

`resources/main/config/app.properties`:

```properties
mode=study
```

`resources/main/config/choice.txt`:

```text
base
```

`resources/second/config/choice.txt`:

```text
plugin
```

Từ thư mục gốc chứa `src` và `resources`, dùng JDK 17 trở lên để biên dịch:

```bash
javac -d out src/demo/resources/ResourceLookupDemo.java
```

Lệnh chạy **Windows** (classpath ngăn cách bằng dấu chấm phẩy):

```powershell
java -cp "out;resources/main;resources/second" demo.resources.ResourceLookupDemo
```

Lệnh chạy **Linux/macOS** (classpath ngăn cách bằng dấu hai chấm):

```bash
java -cp "out:resources/main:resources/second" demo.resources.ResourceLookupDemo
```

Stdout của ví dụ với nội dung file như trên:

```text
Class relative: Hello from package
Class absolute: Hello from package
Class stream: Hello from package
Loader URL: Hello from package
Loader stream: mode=study
Matches: 2
All matches: [base, plugin]
Missing URL: true
```

**Vì sao kết quả như vậy?**

1. Ba URL và stream của `Class` hoặc `ClassLoader` trỏ đúng `demo/resources/messages/welcome.txt` sau khi áp dụng quy tắc tên của API tương ứng.
2. `getResourceAsStream("config/app.properties")` đọc nội dung từ gốc classpath `resources/main`.
3. `getResources("config/choice.txt")` tìm hai tài nguyên cùng tên ở hai classpath entry. Trong chương trình, `Collections.sort(values)` chỉ bảo đảm **thứ tự dòng in ra**, không sửa thứ tự loader đã phát hiện.
4. Resource không tồn tại khiến `getResource(...)` trả `null`; ví dụ in `true` để biểu diễn phép kiểm tra này.

**Ranh giới ví dụ:** `firstLine` chỉ đọc **dòng đầu tiên** để kết quả ngắn và rõ. Với file cấu hình nhiều dòng hoặc JSON/YAML, phải dùng parser thích hợp; ví dụ này không phải bộ đọc tất cả nội dung.

### 3.2. Thử đóng phần resource chính vào JAR

Từ cùng thư mục dự án, sau khi biên dịch, tạo JAR:

```bash
jar --create --file demo.jar -C out . -C resources/main .
```

JAR này chứa class đã biên dịch và toàn bộ resource trong `resources/main`. Để thấy hai nơi cùng đóng góp `config/choice.txt`, tiếp tục để `resources/second` ở classpath.

Windows:

```powershell
java -cp "demo.jar;resources/second" demo.resources.ResourceLookupDemo
```

Linux/macOS:

```bash
java -cp "demo.jar:resources/second" demo.resources.ResourceLookupDemo
```

Stdout **giữ nguyên** như lần chạy từ thư mục. Sự khác biệt là URL của resource trong JAR có thể dùng dạng `jar:file:/.../demo.jar!/config/app.properties` thay vì `file:/.../resources/main/config/app.properties`; vì thế code đọc qua `InputStream` sẽ dễ tái sử dụng hơn code mặc định ép URL thành filesystem `Path`.

## 4. `getResource` và `getResources` khi có nhiều JAR

Trong Java runtime extensibility, cùng một tên có thể xuất hiện trong nhiều plugin JAR. Ví dụ, hai provider đóng góp:

```text
plugins/alpha.jar!/META-INF/services/com.example.spi.Processor
plugins/beta.jar!/META-INF/services/com.example.spi.Processor
```

Khi loader có khả năng nhìn thấy cả hai JAR, `getResources("META-INF/services/com.example.spi.Processor")` có thể tìm ra hai URL. Cơ chế `ServiceLoader` của Java dựa vào việc phát hiện mô tả provider theo SPI; tuy vậy **đọc trực tiếp các resource không tương đương với việc ServiceLoader đã xác thực/nạp được implementation**. Nếu mục tiêu là chọn provider đúng hợp đồng, ưu tiên `ServiceLoader` hoặc một plugin registry thay vì tự xử lý descriptor như văn bản tùy tiện.

### 4.1. Một kết quả có nghĩa gì?

`getResource("config/choice.txt")` chỉ đưa ra **một URL theo cách loader tìm kiếm**, kể cả khi có nhiều bản trùng tên. Trong các loader phổ biến, cơ chế ủy quyền cha/con và thứ tự classpath ảnh hưởng URL được trả về. **Đừng xem đó là thứ tự ưu tiên nghiệp vụ được đảm bảo trên mọi class loader**.

Nếu cần chỉ có **một** cấu hình duy nhất, dùng `getResources` để phát hiện xung đột rồi:

- Không thấy: báo lỗi thiếu cấu hình hoặc dùng default **chỉ khi hợp đồng cho phép**.
- Thấy đúng một: đọc và xác thực.
- Thấy nhiều: thông báo danh sách nguồn và yêu cầu chỉ định tường minh, hoặc áp dụng **quy tắc merge/override đã định nghĩa rõ**.

Nếu hệ thống cho phép nhiều nhà cung cấp tài nguyên, hãy quy định cách gộp và chống lặp. Chẳng hạn nhiều plugin đóng góp file quy tắc, hệ thống có thể duyệt toàn bộ URL, parse từng file và gộp theo `id`; khi hai mục trùng `id` thì phải có policy conflict hoặc từ chối. Không lấy một cách ngẫu nhiên.

### 4.2. Vì sao không nên suy luận thứ tự Enumeration?

`Enumeration<URL>` phản ánh quy tắc của loader cụ thể, bao gồm delegation, cấu hình và cách triển khai module. Một số loader thông dụng có thể trả parent resources trước rồi child resources, nhưng loader tùy chỉnh, môi trường application server hoặc module có thể thay đổi tập kết quả và thứ tự.

Vì vậy:

- Không viết logic “file đầu tiên thắng” nếu thứ tự này chưa được định nghĩa và kiểm thử cho loader đang chạy.
- Để dễ chẩn đoán, có thể chuẩn hóa URL thành chuỗi để **hiển thị**, nhưng không dùng thứ tự từ điển của URL làm chính sách đáng tin cậy nếu bản chất phụ thuộc vào ưu tiên plugin.
- Nếu chọn theo priority, đọc manifest/metadata provider, xác thực version và chọn bằng một selector tường minh.
- Nếu các bản cùng tên là lỗi đóng gói, fail fast với thông tin nhận dạng từng nguồn.

Một đặc điểm quan trọng: **`getResources("folder")` không phải API duyệt tất cả file trong folder.** Nó chỉ tìm resource tên chính xác `folder`, nếu entry ấy tồn tại. Directory entry có thể không được đóng trong JAR; không dùng `getResources` như công cụ liệt kê thư mục tùy ý. Muốn biết tất cả extension, nên có index/manifest/SPI hoặc registry rõ ràng.

## 5. Chọn class loader nào trong hệ thống plugin?

Một JVM có thể có **nhiều** class loader và module layer, mỗi loader nhìn thấy tập tài nguyên khác nhau. “Tìm resource của ứng dụng” và “tìm resource của plugin” có thể ra hai kết quả.

### 5.1. Loader gắn với class

```java
ClassLoader pluginLoader = SomePlugin.class.getClassLoader();

URL pluginConfig = pluginLoader.getResource(
        "com/example/plugin/defaults.properties");
```

Đây là đoạn **minh họa**; `SomePlugin` là class đã được khai báo trong plugin thực tế. Cách này hợp lý khi biết class nào sở hữu tài nguyên và muốn tra cứu trong phạm vi loader có thể nhìn thấy class ấy. Nếu tài nguyên nằm **cùng package với class**, `SomePlugin.class.getResource("defaults.properties")` thường diễn đạt chính xác hơn.

**Chú ý:** class loader kiểu parent-first có thể tìm thấy một resource cùng tên ở loader cha trước bản ở plugin. `SomePlugin.class.getClassLoader()` không tự bảo đảm “chỉ lấy resource thuộc JAR của SomePlugin”. Muốn cách ly namespace và quyền ưu tiên, phải xác định chính sách riêng trong loader/registry.

### 5.2. Thread context class loader (TCCL)

Các framework/SPIs thường dùng:

```java
ClassLoader contextLoader =
        Thread.currentThread().getContextClassLoader();
```

TCCL là loader gắn với thread theo ngữ cảnh chạy; nó **có thể khác** loader đã nạp một class của thư viện. `ServiceLoader.load(ServiceType.class)` mặc định dùng context class loader của thread hiện tại trong đường gọi thông dụng. Một hệ thống plugin có thể muốn dùng `ServiceLoader.load(ServiceType.class, pluginLoader)` để truyền loader tường minh.

Nếu cần đổi TCCL tạm thời trong vùng gọi plugin, phải khôi phục trong `finally` để không rò ngữ cảnh sang tác vụ khác:

```java
Thread thread = Thread.currentThread();
ClassLoader previous = thread.getContextClassLoader();
try {
    thread.setContextClassLoader(pluginLoader);
    // Gọi framework cần context loader của plugin tại đây.
} finally {
    thread.setContextClassLoader(previous);
}
```

Hai đoạn là **minh họa trong phương thức đã có** và giả định `pluginLoader` được cung cấp hợp lệ. Việc đổi TCCL không làm class loader mới tự xuất hiện, không đưa JAR mới vào runtime, không đóng class loader và không cô lập mã không tin cậy.

### 5.3. Quan hệ với `URLClassLoader` và vòng đời plugin

Nếu hệ thống hỗ trợ thêm JAR lúc chạy, một `URLClassLoader` có thể được tạo để nhìn thấy các URL JAR mới. Khi đó cần:

1. Quy định API chung được nạp ở class loader nào để không có hai bản của cùng interface với danh tính class khác nhau.
2. Chọn parent/child delegation và namespace resource theo hợp đồng.
3. Khởi tạo, xác minh và đăng ký các provider được phát hiện; không giả định `getResource` đồng nghĩa class đã load thành công.
4. Quản lý phiên bản snapshot, instance, thread và các stream đang mở khi cập nhật plugin.
5. Đóng loader/tài nguyên khi hoàn tất và không còn tham chiếu cần dùng.

Nạp lại danh sách bằng `getResources` **không** có nghĩa class loader đang dùng sẽ tự quan sát một JAR mới trên đĩa; tập URL/search scope phải được cập nhật theo cơ chế của hệ thống.

## 6. Classpath và Java Platform Module System (JPMS)

Trong ứng dụng Java 9+ dùng **named modules**, resource visibility có thể bị ảnh hưởng bởi encapsulation của module, bên cạnh đường dẫn và class loader.

- Resource thuộc module có thể được tra cứu theo cơ chế module tương ứng; không nên giả định tất cả resource trong mọi module đều được nhìn thấy bởi một lời gọi `ClassLoader.getResource`.
- Với resource **không phải `.class`** nằm trong package của named module, quy tắc mở package (`opens`) ảnh hưởng khả năng truy cập bằng phương thức của class loader. Một module có thể có resource nhưng lookup từ nơi khác vẫn trả `null`.
- `Class.getResource`/`getResourceAsStream` có ngữ cảnh module của class được gọi và quy tắc riêng; thử nghiệm trên classpath không tự kiểm chứng ứng dụng chạy với `--module-path`.
- Cần đặt tên resource đúng, kiểm tra `module-info.java`/`opens` khi cần, và test trong chính chế độ đóng gói production.

**Không mở tất cả package vô điều kiện chỉ để sửa một lỗi path.** Hãy xác định resource nào cần công bố, đối tượng gọi nào thực sự sở hữu lookup và phạm vi quyền nào thích hợp. Với cấu hình nội bộ của một module, lookup tương ứng với class thuộc chính module thường dễ kiểm soát hơn.

## 7. Đọc dữ liệu đúng và quản lý tài nguyên

### 7.1. Kiểm tra thiếu resource và lỗi I/O

Ba kết quả cần phân biệt:

- `getResource(...) == null`: không tìm thấy URL trong phạm vi lookup đang dùng.
- `getResourceAsStream(...) == null`: không thu được stream, có thể vì không tìm thấy hoặc không mở được tài nguyên; API này không bảo đảm cung cấp chẩn đoán IOException cụ thể.
- `getResources(...)` có thể trả enumeration rỗng, hoặc ném `IOException` trong lúc tìm; còn `url.openStream()` có thể lỗi dù URL đã tìm thấy.

Nếu thiếu cấu hình bắt buộc, đừng dùng `new String(byte[0])` hoặc trả giá trị giả rồi chạy tiếp. Hãy báo resource name, loader/module liên quan và hướng dẫn đóng gói đúng. Với resource tùy chọn, dùng default đã được công bố trong hợp đồng.

Ví dụ mẫu đọc file UTF-8 có xử lý thiếu resource tường minh:

```java
import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import java.util.Objects;

public final class RequiredResource {
    public static String readUtf8(String name) throws IOException {
        ClassLoader loader = RequiredResource.class.getClassLoader();
        InputStream input = Objects.requireNonNull(
                loader.getResourceAsStream(name),
                "Missing classpath resource: " + name);

        try (input) {
            return new String(input.readAllBytes(), StandardCharsets.UTF_8);
        }
    }
}
```

`RequiredResource` là một class độc lập dùng Java 17+, nhưng không có `main` nên được thiết kế để **gọi từ ứng dụng**. `readAllBytes()` thích hợp với tài nguyên **nhỏ và đã biết giới hạn kích thước**; với file lớn hãy xử lý theo luồng để tránh chiếm nhiều bộ nhớ. `Objects.requireNonNull` ở đây giúp fail fast bằng tên resource.

Khi cần parse `.properties`, dùng `Properties.load(InputStream)` theo encoding/quy tắc của định dạng properties (InputStream diễn giải ISO-8859-1 và escape), hoặc `Properties.load(Reader)` nếu chủ động dùng reader UTF-8. Đừng đọc byte thành String UTF-8 rồi giả định mọi parser sẽ tự hiểu giống nhau.

### 7.2. Tránh phụ thuộc vào đường dẫn filesystem

Mẫu dễ lỗi:

```java
URL url = RequiredResource.class.getResource("/config/app.properties");
// Không giả định URL này luôn có scheme "file".
```

Nếu URL trỏ tới entry trong JAR, `Path.of(url.toURI())` không mặc định biến nó thành một `Path` của file thông thường; `File` không biểu diễn một entry bên trong ZIP/JAR như file OS. Hãy dùng `url.openStream()` hoặc `getResourceAsStream()` khi chỉ cần đọc byte.

Nếu thư viện bên thứ ba **bắt buộc nhận file thật**, đó là yêu cầu khác: có thể phải copy resource ra temp file, kiểm soát quyền truy cập, đóng stream, dùng file, rồi dọn đúng vòng đời. Không đổi API resource lookup thành lời hứa rằng lúc nào cũng có filesystem path.

### 7.3. Tài nguyên trùng tên và dữ liệu nhạy cảm

Tài nguyên trong JAR thường có thể được giải nén và đọc; không đóng gói password, private key hoặc token vào resource rồi coi nó là bí mật. Trong plugin system, JAR bên thứ ba có thể đóng góp resource trùng tên, nên cần kiểm tra nguồn/ID/version và không tin dữ liệu chỉ vì nó đi kèm JAR. Nếu tải tên resource do người dùng cung cấp, dùng allowlist và giới hạn namespace, kích thước, format và nguồn loader.

Một stream chưa được đóng có thể giữ descriptor hoặc handle tới file/JAR tùy implementation. Sử dụng `try-with-resources` là chuẩn; trả `InputStream` ra khỏi method thì phải quy định **bên nhận chịu trách nhiệm đóng**.

## 8. Kiểm thử và chẩn đoán lookup

Để test việc đóng gói thực sự, cần ít nhất một lần chạy từ **JAR đã build**, không chỉ từ IDE. Những trường hợp sau kiểm tra các failure mode thường gặp:

| Tình huống | Kỳ vọng |
|---|---|
| Resource cạnh class trong package | `Class.getResource("name")` tìm đúng tên có prefix package |
| Resource ở root classpath | `ClassLoader.getResource("config/name")` tìm được |
| Dùng `/` ở đầu cho `ClassLoader` | Không áp dụng quy tắc tên tương đối/absolute của `Class`; sửa tên lookup cho đúng |
| Resource bắt buộc bị thiếu | Fail fast với tên resource rõ ràng |
| Resource tùy chọn bị thiếu | Default đã định nghĩa; không che lỗi tính năng bắt buộc |
| Có hai JAR đóng góp cùng tên | `getResources` phát hiện tất cả resource trong phạm vi loader; xử lý xung đột |
| Chỉ gọi `getResource` khi có hai bản | Có thể nhận một URL, không đủ bằng chứng rằng resource là duy nhất |
| Resource trong JAR thay vì thư mục | `InputStream` vẫn đọc được, code không phụ thuộc `File` |
| Đọc resource tiếng Việt | UTF-8 tường minh, không lệ thuộc charset mặc định |
| Chạy qua plugin loader khác với app loader | Phải chọn đúng loader và xác minh parent/child visibility |
| Chạy bằng named module | Test `opens`/module visibility và tên resource |
| Stream đã đọc xong | Được đóng ngay cả khi parse ném lỗi |

Khi chẩn đoán, những log hữu ích là **tên logic resource**, class loader hoặc module chịu trách nhiệm, số lượng URL tìm được, URL ở dạng đã lược bỏ thông tin nhạy cảm, và lỗi đọc/parse riêng biệt. Không cần dump toàn bộ nội dung file cấu hình vào log.

## 9. Những nhầm lẫn thường gặp

1. **“Tên trong getResource là đường dẫn tương đối so với working directory.”** Sai: đó là tên resource theo package/class loader; working directory chỉ liên quan nếu code dùng API filesystem riêng.
2. **“Class.getResource và ClassLoader.getResource nhận cùng một tên.”** Không luôn đúng: `Class` có quy tắc package-relative và cú pháp `/` đầu, còn `ClassLoader` dùng tên từ gốc.
3. **“getResourceAsStream không cần close.”** Sai: stream vẫn chiếm tài nguyên I/O; dùng `try-with-resources`.
4. **“Nếu có hai JAR cùng tên, getResource sẽ báo trùng.”** Sai: nó trả một URL hoặc null. Phải dùng `getResources` nếu cần kiểm tra nhiều vị trí.
5. **“Enumeration URL có thứ tự ưu tiên plugin mặc nhiên.”** Sai: thứ tự theo cơ chế loader, không tự tương ứng chính sách nghiệp vụ.
6. **“getResources(path) sẽ liệt kê file trong thư mục path.”** Sai: API tìm nhiều resource có đúng tên `path`.
7. **“URL nào cũng chuyển trực tiếp thành File được.”** Sai với entry trong JAR và các giao thức không phải filesystem.
8. **“Chạy được trong IDE thì JAR chắc chắn có resource.”** Sai: build có thể bỏ qua resource, đổi đường dẫn hoặc module visibility.
9. **“Class loader của framework và plugin luôn giống nhau.”** Sai: TCCL, application loader, custom URLClassLoader và module layer có thể khác.
10. **“Không tìm được resource luôn là file bị thiếu.”** Sai: có thể sai package prefix, dấu `/`, classpath/module path, module encapsulation hoặc loader search scope.

**Điểm cần nhớ:** `getResource` tìm **một vị trí URL**, `getResources` tìm **nhiều vị trí cùng tên**, `getResourceAsStream` cung cấp **luồng đọc byte**. Trước khi sử dụng phải xác định **đúng tên logic**, **đúng API `Class` hay `ClassLoader`**, **đúng loader/module**, và **hành vi khi thiếu hoặc trùng resource**. Đó là nền tảng để ứng dụng Java nạp cấu hình và tài nguyên của plugin một cách dự đoán, có thể kiểm thử và hoạt động cả khi đã đóng gói JAR.