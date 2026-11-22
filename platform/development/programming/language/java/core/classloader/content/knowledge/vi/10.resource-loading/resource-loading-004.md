# getResourceAsStream và xử lý trường hợp không tìm thấy tài nguyên trong Java

**`getResourceAsStream`** là API giúp đọc một **resource** được đóng gói cùng ứng dụng Java hoặc nhìn thấy được qua cơ chế tra cứu của class loader: tệp cấu hình, mẫu văn bản, dữ liệu JSON, chứng chỉ, biểu tượng, v.v. Nó trả về **`InputStream` nếu tìm được**, hoặc **`null` nếu không tìm được** — chứ không tự động ném `FileNotFoundException` cho một tài nguyên vắng mặt.

Điều này khiến các lỗi như `NullPointerException` khi tạo `InputStreamReader`, ứng dụng chạy trong IDE nhưng hỏng sau khi đóng gói JAR, hoặc "tệp nằm trong project mà JVM vẫn không thấy" rất phổ biến. Cách giải quyết là phân biệt **resource path**, **loader được dùng**, **tài nguyên thực sự nằm ở đâu trên runtime classpath/module path**, **chính sách xử lý missing** và **đóng luồng đúng cách**.

Bài viết sử dụng **JDK 17+**. Các chương trình hoàn chỉnh dùng `javac`/`java`; các ví dụ đóng gói resource minh họa cả Windows PowerShell và Linux/macOS, vì thao tác copy file khác nhau theo hệ điều hành.

## 1. Trước khi xử lý `null`, xác định nơi tra cứu

Một resource name như `config/app.properties` là tên dữ liệu trong phạm vi tìm kiếm của class loader hoặc module, không phải đường dẫn file tương đối với thư mục đang đứng. Lúc chạy, cùng tên đó có thể trỏ tới file trong thư mục output, entry trong JAR hoặc resource do một loader tùy chỉnh cung cấp.

Khi `getResourceAsStream(name)` trả `null`, hãy phân biệt ba câu hỏi:

1. **Tên có đúng không?** Với `ClassLoader` tên được tính từ resource root; với `Class` có thể tương đối với package.
2. **Nguồn có chứa resource không?** Cần kiểm tra output/JAR của bản thực sự chạy, không chỉ file trong `src/main/resources`.
3. **Ngữ cảnh có cho phép tìm không?** Loader được chọn và module encapsulation có thể khiến file hiện hữu không nhìn thấy được.

`ClassLoader.loadClass` nạp định nghĩa lớp, còn `getResourceAsStream` chỉ tìm/mở dữ liệu. Đừng thay resource lookup bằng `Path.of(name)` hay ép một URL `jar:` thành `File`: hai cách đó bỏ qua cách JAR và module tổ chức dữ liệu.

## 2. Hai họ API cùng tên nhưng quy tắc đường dẫn khác nhau

Phân biệt:

```java
ClassLoader loader = Example.class.getClassLoader();
InputStream a = loader.getResourceAsStream("config/app.properties");
InputStream b = Example.class.getResourceAsStream("/config/app.properties");
InputStream c = Example.class.getResourceAsStream("local.txt");
```

Đây là **snippet minh họa**, cần import `java.io.InputStream` và một class `Example` có thật. Hai cách lấy resource có chính sách diễn giải tên:

### `ClassLoader.getResourceAsStream(String name)`

- Tên là **resource name từ gốc namespace của loader**; ví dụ `"config/app.properties"`.
- Dùng dấu `/` để phân tách các phần của resource name, kể cả khi chạy trên Windows.
- **Không thêm `/` ở đầu**. `loader.getResourceAsStream("/config/app.properties")` thường không tìm được resource tại `config/app.properties`, vì loader không có bước chuẩn loại leading slash giống `Class.getResource...`.
- Thư mục output hoặc các JAR mà loader nhìn thấy quyết định có tài nguyên ấy không.
- `getResourceAsStream` thường dựa vào `getResource` rồi mở stream; nếu không có URL hoặc không mở được, kết quả có thể là `null`. Không coi `null` chỉ có một nguyên nhân duy nhất là sai tên.

### `Class.getResourceAsStream(String name)`

- Nếu `name` **bắt đầu bằng `/`**, tìm từ **gốc namespace**: `SomeClass.class.getResourceAsStream("/config/app.properties")`.
- Nếu `name` **không bắt đầu bằng `/`**, tên được hiểu **tương đối với package của class**: với `demo.Example`, `Example.class.getResourceAsStream("local.txt")` tìm resource tương ứng `demo/local.txt`.
- Cách này tiện cho tài nguyên nằm ngay cạnh class, nhưng cũng dễ sai khi người viết nghĩ `"config/app.properties"` luôn là đường dẫn từ classpath root.

### Bảng quy đổi

Giả sử `demo.Example` nằm trong package `demo` và runtime có hai resource `config/app.properties`, `demo/local.txt`:

| Lệnh gọi | Resource name được tra cứu | Kỳ vọng |
| --- | --- | --- |
| `loader.getResourceAsStream("config/app.properties")` | `config/app.properties` | Tìm được |
| `loader.getResourceAsStream("/config/app.properties")` | `/config/app.properties` | Thường không tìm được |
| `Example.class.getResourceAsStream("/config/app.properties")` | `config/app.properties` | Tìm được |
| `Example.class.getResourceAsStream("local.txt")` | `demo/local.txt` | Tìm được |
| `Example.class.getResourceAsStream("/demo/local.txt")` | `demo/local.txt` | Tìm được |
| `Example.class.getResourceAsStream("config/app.properties")` | `demo/config/app.properties` | Không tìm được nếu chỉ có resource ở gốc |

Trên Java 9+, named modules có các quy tắc **encapsulation** đối với resource. Vì vậy bảng trên là mô hình lookup thông thường cho tài nguyên của classpath/unnamed module; với named modules còn phải xét quyền truy cập và cách tài nguyên được đóng gói.

## 3. Không tìm thấy trả `null`: phải kiểm tra trước khi đọc

Sai lầm rất thường gặp:

```java
InputStream input =
        Example.class.getClassLoader()
                .getResourceAsStream("config/missing.properties");
Properties props = new Properties();
props.load(input); // input == null: thất bại do dùng null
```

Đoạn trên là **code minh họa lỗi**, không phải bài thực hành nên làm. Nếu không tìm được resource, `getResourceAsStream` trả `null`. Khi chuyển `null` cho `Properties.load` hoặc `new InputStreamReader(input)`, ứng dụng có thể ném `NullPointerException`, khiến người đọc log không rõ resource nào đã bị thiếu.

Đúng hơn là **quyết định chính sách** trước khi đọc:

- **Resource bắt buộc:** báo lỗi với **tên resource và ngữ cảnh loader/module** đủ để debug. Có thể ném `FileNotFoundException` hoặc `IllegalStateException` tùy API boundary.
- **Resource tùy chọn:** dùng giá trị mặc định được tài liệu hóa; không làm như thể resource đã tồn tại.
- **Resource cung cấp bởi plugin:** nếu loader không nhìn thấy, kiểm tra plugin dependency/packaging, không âm thầm đọc nhầm bản từ loader khác.
- **Resource có nội dung nhạy cảm:** lỗi có thể ghi resource name đã được kiểm soát, nhưng tránh in secrets hoặc URL chứa credentials vào log.

Một mẫu bắt buộc, không che nguyên nhân:

```java
static InputStream openRequired(ClassLoader loader, String name)
        throws java.io.FileNotFoundException {
    InputStream stream = loader.getResourceAsStream(name);
    if (stream == null) {
        throw new java.io.FileNotFoundException(
                "Classpath resource not found: " + name);
    }
    return stream;
}
```

Đây là một **method minh họa**; gọi nó từ class cụ thể, đặt kết quả trong `try-with-resources`. Không truyền `loader == null` vào mẫu trên; với bootstrap classes hoặc module khác, hãy chọn API lookup phù hợp thay vì giả định luôn có loader object.

### `FileNotFoundException` là do mã của ta ném, không phải do `getResourceAsStream`

Nếu resource thiếu, `getResourceAsStream` trả `null`. Trong mẫu `openRequired`, chính ứng dụng lựa chọn ném `FileNotFoundException` để diễn đạt contract "resource bắt buộc". Nhờ vậy stacktrace rõ hơn nhưng không được nói rằng phương thức JDK trực tiếp ném lỗi này.

## 4. Thực hành A — đọc `.properties` UTF-8, kiểm tra null và đóng stream

Tạo một project nhỏ:

```text
resource-lab/
├── src/
│   └── demo/
│       └── ConfigDemo.java
└── resources/
    └── config/
        └── app.properties
```

**`resources/config/app.properties`:**

```properties
app.name=Inventory
timeout.seconds=15
welcome=Chào Java
```

**`src/demo/ConfigDemo.java`:**

```java
package demo;

import java.io.FileNotFoundException;
import java.io.InputStream;
import java.io.InputStreamReader;
import java.nio.charset.StandardCharsets;
import java.util.Properties;

public final class ConfigDemo {
    public static void main(String[] args) throws Exception {
        String resourceName = "config/app.properties";
        ClassLoader loader = ConfigDemo.class.getClassLoader();

        InputStream input = loader.getResourceAsStream(resourceName);
        if (input == null) {
            throw new FileNotFoundException(
                    "Missing required resource: " + resourceName);
        }

        Properties properties = new Properties();
        try (InputStream stream = input;
             InputStreamReader reader =
                     new InputStreamReader(stream, StandardCharsets.UTF_8)) {
            properties.load(reader);
        }

        System.out.println("name=" +
                properties.getProperty("app.name"));
        System.out.println("timeout=" +
                properties.getProperty("timeout.seconds"));
        System.out.println("welcome=" +
                properties.getProperty("welcome"));
    }
}
```

**Biên dịch** từ thư mục `resource-lab`:

```sh
javac --release 17 -d out src/demo/ConfigDemo.java
```

Lệnh `javac -d out` chỉ tạo `.class`. Ta cần **chép resource vào thư mục output** để namespace runtime có entry `config/app.properties`.

Trên **Windows PowerShell**:

```powershell
New-Item -ItemType Directory -Force out\config | Out-Null
Copy-Item resources\config\app.properties out\config\app.properties
java -cp out demo.ConfigDemo
```

Trên **Linux/macOS**:

```sh
mkdir -p out/config
cp resources/config/app.properties out/config/app.properties
java -cp out demo.ConfigDemo
```

**Stdout của lệnh `java`, khi tệp được lưu là UTF-8:**

```text
name=Inventory
timeout=15
welcome=Chào Java
```

**Vì sao chương trình chạy đúng?**

1. `ConfigDemo.class.getClassLoader()` trả về loader nhìn thấy `out` do `-cp out`.
2. `"config/app.properties"` là tên resource từ classpath root, tương ứng `out/config/app.properties` sau khi copy.
3. `getResourceAsStream` trả `InputStream`; chúng ta kiểm tra `null` trước khi đưa nó vào Reader.
4. `InputStreamReader(stream, StandardCharsets.UTF_8)` giải mã bytes văn bản với charset rõ ràng, giữ dấu tiếng Việt.
5. `Properties.load(Reader)` đọc từng cặp `key=value`; `getProperty` trả chuỗi giá trị.
6. `try-with-resources` đóng Reader và stream, kể cả khi `Properties.load` ném `IOException`.

**Chi tiết charset đáng nhớ:** `Properties.load(InputStream)` theo Java API diễn giải byte theo ISO-8859-1 (các ký tự ngoài bảng mã phải escape). Muốn đọc tệp properties **UTF-8 trực tiếp**, dùng `Properties.load(Reader)` với `InputStreamReader(StandardCharsets.UTF_8)` như trên. Đừng tùy tiện thay bằng `properties.load(input)` nếu tệp có dấu tiếng Việt.

**Không nhầm runtime working directory và classpath:** đường dẫn `resources/config/app.properties` tồn tại trong source tree không bảo đảm loader thấy nó. Trình chạy dùng `-cp out`, nên tài nguyên phải nằm trong `out` (hoặc trong JAR/classpath khác mà loader nhìn thấy). Trên Maven/Gradle, resource processing thường copy từ `src/main/resources` vào output, nhưng ví dụ thủ công này yêu cầu bước copy rõ ràng.

## 5. Thực hành B — chứng minh package-relative và classpath-root khác nhau

Bài tiếp theo dùng một class ở package `demo` và hai resources có **cùng filename** nhưng nằm ở hai vị trí khác nhau:

```text
path-lab/
├── src/demo/PathDemo.java
└── resources/
    ├── messages.txt
    └── demo/
        └── messages.txt
```

**`resources/messages.txt`:**

```text
hello-from-root
```

**`resources/demo/messages.txt`:**

```text
hello-from-package
```

**`src/demo/PathDemo.java`:**

```java
package demo;

import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;

public final class PathDemo {
    static String text(InputStream input) throws IOException {
        if (input == null) {
            return "<missing>";
        }
        try (InputStream stream = input) {
            return new String(stream.readAllBytes(),
                    StandardCharsets.UTF_8).trim();
        }
    }

    public static void main(String[] args) throws Exception {
        ClassLoader loader = PathDemo.class.getClassLoader();

        System.out.println("relative=" +
                text(PathDemo.class.getResourceAsStream("messages.txt")));
        System.out.println("class absolute=" +
                text(PathDemo.class.getResourceAsStream("/messages.txt")));
        System.out.println("loader root=" +
                text(loader.getResourceAsStream("messages.txt")));
        System.out.println("loader leading slash missing=" +
                (loader.getResourceAsStream("/messages.txt") == null));
        System.out.println("missing=" +
                text(PathDemo.class.getResourceAsStream("absent.txt")));
    }
}
```

Biên dịch:

```sh
javac --release 17 -d out src/demo/PathDemo.java
```

**Windows PowerShell** — copy đúng hai resources rồi chạy:

```powershell
New-Item -ItemType Directory -Force out\demo | Out-Null
Copy-Item resources\messages.txt out\messages.txt
Copy-Item resources\demo\messages.txt out\demo\messages.txt
java -cp out demo.PathDemo
```

**Linux/macOS**:

```sh
mkdir -p out/demo
cp resources/messages.txt out/messages.txt
cp resources/demo/messages.txt out/demo/messages.txt
java -cp out demo.PathDemo
```

**Stdout của lệnh `java`:**

```text
relative=hello-from-package
class absolute=hello-from-root
loader root=hello-from-root
loader leading slash missing=true
missing=<missing>
```

Nhận xét:

- `PathDemo.class.getResourceAsStream("messages.txt")` dùng package của `PathDemo` → `demo/messages.txt`.
- `PathDemo.class.getResourceAsStream("/messages.txt")` dùng **classpath root** → `messages.txt`.
- `loader.getResourceAsStream("messages.txt")` cũng dùng tên từ **gốc namespace loader** → `messages.txt`.
- `loader.getResourceAsStream("/messages.txt")` không áp dụng quy tắc bỏ slash của `Class`; do vậy không thấy resource đã đóng gói.
- `PathDemo.class.getResourceAsStream("absent.txt")` cho `null`, và helper `text` biến thành chuỗi hiển thị `<missing>`. Trong hệ thống thật, nên phân biệt resource bắt buộc/tùy chọn chứ không luôn nuốt trường hợp thiếu.

Trong ví dụ học tập, `trim()` chỉ loại khoảng trắng/newline ở cuối để stdout dễ kiểm tra. Không dùng `trim()` bừa bãi cho các định dạng mà whitespace mang ý nghĩa, như template thụt dòng, chữ ký hoặc file cấu hình yêu cầu chính xác từng byte.

## 6. Thực hành C — phân biệt resource bắt buộc và resource tùy chọn

Đây là một API wrapper dễ áp dụng: **bắt buộc thì ném lỗi có thông tin**, còn **tùy chọn thì fallback được chỉ định tường minh**.

Cấu trúc:

```text
missing-lab/
├── src/demo/MissingDemo.java
└── resources/templates/report.txt
```

**`resources/templates/report.txt`:**

```text
Report template
```

**`src/demo/MissingDemo.java`:**

```java
package demo;

import java.io.FileNotFoundException;
import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;

public final class MissingDemo {
    static String required(ClassLoader loader, String name)
            throws IOException {
        InputStream opened = loader.getResourceAsStream(name);
        if (opened == null) {
            throw new FileNotFoundException(
                    "Resource not found: " + name);
        }
        try (InputStream stream = opened) {
            return new String(stream.readAllBytes(),
                    StandardCharsets.UTF_8).trim();
        }
    }

    static String optional(ClassLoader loader, String name,
                           String fallback) throws IOException {
        InputStream opened = loader.getResourceAsStream(name);
        if (opened == null) {
            return fallback;
        }
        try (InputStream stream = opened) {
            return new String(stream.readAllBytes(),
                    StandardCharsets.UTF_8).trim();
        }
    }

    public static void main(String[] args) throws IOException {
        ClassLoader loader = MissingDemo.class.getClassLoader();

        System.out.println("required=" +
                required(loader, "templates/report.txt"));
        try {
            required(loader, "templates/absent.txt");
        } catch (FileNotFoundException e) {
            System.out.println("missing=" + e.getMessage());
        }
        System.out.println("optional=" +
                optional(loader, "templates/absent.txt", "fallback"));
    }
}
```

Biên dịch:

```sh
javac --release 17 -d out src/demo/MissingDemo.java
```

Copy tài nguyên và chạy trên **Windows PowerShell**:

```powershell
New-Item -ItemType Directory -Force out\templates | Out-Null
Copy-Item resources\templates\report.txt out\templates\report.txt
java -cp out demo.MissingDemo
```

Trên **Linux/macOS**:

```sh
mkdir -p out/templates
cp resources/templates/report.txt out/templates/report.txt
java -cp out demo.MissingDemo
```

**Stdout của lệnh `java`:**

```text
required=Report template
missing=Resource not found: templates/absent.txt
optional=fallback
```

Giải thích contract:

- `required(...)` ném `FileNotFoundException` **chỉ khi lookup trả `null`**. Khi resource có nhưng đọc thất bại, `IOException` từ luồng được truyền ra nguyên nhân tương ứng.
- `optional(...)` chỉ trả fallback **khi không tìm được resource**; nó **không coi lỗi I/O khi đọc một resource có thật là như chưa có**. Cách này tránh che lỗi file/JAR bị hỏng.
- Cả hai phương thức dùng `try-with-resources` nên đóng luồng kể cả khi việc đọc phát sinh lỗi.
- Fallback `"fallback"` là ví dụ cho tùy chọn hợp lệ. Không tự động đưa fallback cho cấu hình quan trọng như khóa ký, endpoint thanh toán hay certificate bắt buộc.
- Tên resource là một phần của thông điệp lỗi, giúp debug khác biệt giữa `templates/report.txt` và `templates/absent.txt`.

Một ứng dụng thực tế có thể trả `Optional<String>` cho resource tùy chọn. Tuy nhiên nếu dùng `Optional`, đừng ép mọi exception thành `Optional.empty()`: **vắng mặt** và **đọc thất bại** là hai trạng thái khác nhau.

## 7. Resource đóng gói trong JAR vẫn được đọc qua cùng API

Sau khi đã có thư mục `out` của ví dụ A (bao gồm `demo/ConfigDemo.class` và `config/app.properties`), đóng gói:

```sh
jar --create --file resource-demo.jar -C out .
jar --list --file resource-demo.jar
java -cp resource-demo.jar demo.ConfigDemo
```

Đây là các lệnh có trong JDK 17+. Trong output `jar --list`, hãy tìm **cả**:

```text
demo/ConfigDemo.class
config/app.properties
```

Hai dòng trên là **các entries cần kiểm tra**, không phải cam kết toàn bộ output của `jar --list` chỉ có hai dòng hay đúng thứ tự ấy.

**Stdout của lệnh `java` trong ví dụ A vẫn là:**

```text
name=Inventory
timeout=15
welcome=Chào Java
```

Điều này hoạt động vì JVM và `URLClassLoader`/built-in loader biết đọc resource dưới dạng entry của JAR. Ứng dụng không cần đoán đường dẫn tạm để giải nén.

Tránh cách sau:

```java
URL url = ConfigDemo.class.getResource("/config/app.properties");
File file = new File(url.getFile());
```

Đây là **mẫu dễ sai** (thiếu import `URL`/`File` nếu copy độc lập): nó có thể tình cờ chạy khi `url` là `file:` nhưng không đáng tin khi URL là `jar:file:...!/...` hoặc khi tên tệp có dấu cách/percent-encoding. Với dữ liệu chỉ cần đọc, **`getResourceAsStream`** loại bỏ sự phụ thuộc vào URL→filesystem path.

Nếu một thư viện thực sự đòi `Path`, bạn có thể phải copy nội dung từ stream sang **temporary file** và quản lý xóa file; hoặc dùng API filesystem provider dành cho JAR khi phù hợp. Nhưng không nên làm thế chỉ để đọc vài kilobytes cấu hình.

## 8. Classpath, working directory và thứ tự build

Một lý do khiến resource chạy trong IDE nhưng không chạy khi dùng `java -cp` là **khác cách đóng gói**:

```text
source layout:                         runtime -cp out:
src/demo/ConfigDemo.java              out/demo/ConfigDemo.class
resources/config/app.properties       out/config/app.properties
```

Dòng `resources/config/app.properties` không được `javac` tự copy vào `out`. Khi chạy `java -cp out demo.ConfigDemo`, loader tra cứu namespace dưới `out`. Nếu quên copy, `getResourceAsStream("config/app.properties") == null`.

Trong dự án dùng Maven hoặc Gradle, thư mục convention như `src/main/resources` thường được build tool copy vào class output/JAR. Đây là **hành vi build tooling**, không phải một tính năng tự động của `ClassLoader`. Luôn kiểm tra artifact runtime:

- Thư mục classes/output có file nằm đúng relative path chưa?
- JAR có entry resource không? Kiểm bằng `jar --list --file app.jar`.
- IDE run configuration có classpath khác bản release không?
- Artifact fat/uber JAR có merge tài nguyên từ nhiều dependency đúng chính sách không?
- Test resources có chỉ xuất hiện trong test classpath, không xuất hiện trong application artifact không?
- Container deployment có bỏ sót hoặc thay thư mục/JAR bằng bản cũ không?

**Working directory** ảnh hưởng những lệnh như `Files.readString(Path.of("config/app.properties"))`; nó **không tự quyết định root của classpath resource lookup**. Trong các ví dụ, ta nhắc chạy từ project root để lệnh copy và `jar` đi đúng đường dẫn, không phải vì `getResourceAsStream` tìm resource từ working directory.

### Không thêm `src/main/resources` vào đường dẫn tra cứu

Nếu build đã copy `src/main/resources/config/app.properties` thành `config/app.properties` ở classpath root, gọi đúng là:

```java
loader.getResourceAsStream("config/app.properties");
```

Không phải `"src/main/resources/config/app.properties"`, vì `src/main/resources` là **vị trí trong repository**, không phải bắt buộc là một phần của **resource name trong artifact**.

## 9. `getResourceAsStream`, `getResource` và `getResources`

Ba API có mục đích khác nhau:

- **`getResourceAsStream(name)`:** muốn **đọc nội dung** ngay. Nhận `InputStream` và đóng sau khi dùng.
- **`getResource(name)`:** muốn **biết URL được chọn** trước khi mở stream. Hữu ích để debug nơi resource được tìm thấy, nhưng URL có thể đại diện entry của JAR hoặc giao thức tùy runtime.
- **`getResources(name)`:** muốn **liệt kê các resource trùng tên** mà loader tìm được qua cơ chế của nó. Trả về `Enumeration<URL>`, không phải `InputStream`.

Ví dụ method hỗ trợ debug khi nghi ngờ **trùng tên resource ở nhiều JAR**:

```java
static void printResources(ClassLoader loader, String name)
        throws java.io.IOException {
    java.util.Enumeration<java.net.URL> urls =
            loader.getResources(name);
    while (urls.hasMoreElements()) {
        System.out.println(urls.nextElement());
    }
}
```

Đây là method **minh họa**, cần được gọi với loader và tên resource thực tế; kết quả URL phụ thuộc môi trường nên không có một stdout cố định. `getResources` có thể giúp chẩn đoán nhiều JAR cung cấp `META-INF/services/...`, `config/app.properties` hay metadata cùng tên.

**Đừng tự áp đặt rằng `getResource` phải chọn "JAR được liệt kê đầu tiên trong source tree"**. Thứ tự lookup phụ thuộc loader graph, classpath/module placement và implementation. Default `ClassLoader.getResource` thông thường ủy quyền cho parent trước khi tự tìm, nhưng custom loaders có thể override cơ chế resource lookup. Nếu ứng dụng yêu cầu ưu tiên rõ, cần thiết kế/kiểm thử chính sách riêng thay vì dựa vào thứ tự ngầm.

Với resources từ nhiều module ở các layers khác nhau, hành vi khám phá còn phụ thuộc module access và class loader cụ thể. Không dùng `getResources` như cách bỏ qua encapsulation.

## 10. Quan hệ với parent delegation và nhiều class loaders

**Resource lookup không giống class loading**, dù cả hai thường dựa vào loader graph:

```text
HostLoader
  ├── class: api.Plugin
  └── resource: config/defaults.properties
       ▲
       │ parent
  PluginLoader
  ├── class: impl.MyPlugin
  └── resource: plugin/settings.json
```

Khi plugin gọi:

```java
InputStream stream =
        pluginLoader.getResourceAsStream("config/defaults.properties");
```

kết quả phụ thuộc **policy của `pluginLoader` và ancestor**. Với loader parent-first mặc định, resource của parent có thể được trả về. Nhưng custom plugin loaders có thể override `getResource` hoặc `getResources`; một loader dùng child-first class policy chưa chắc dùng cùng thứ tự cho resources.

### Chọn loader nào?

Có nhiều lựa chọn:

| Bối cảnh | Lựa chọn đáng cân nhắc | Vì sao |
| --- | --- | --- |
| Resource đóng gói cùng class `demo.MyComponent` | `MyComponent.class.getResourceAsStream("name.txt")` | Package-relative, gắn lookup với runtime `Class<?>` cụ thể. |
| Resource tại root của classpath mà loader đang quản lý | `loader.getResourceAsStream("config/x.properties")` | Tường minh root, tường minh loader. |
| Plugin cần resource nằm trong JAR plugin | Loader đã định nghĩa plugin class, hoặc `PluginImplementation.class.getResourceAsStream(...)` | Tránh mặc định hỏi system loader không nhìn thấy plugin JAR. |
| Framework tìm provider/resource theo thread context | `Thread.currentThread().getContextClassLoader()` khi contract framework quy định | TCCL có thể do container/plugin framework cấu hình. |
| Class loader của một class là `null` | `SomeClass.class.getResourceAsStream(...)` hoặc API module/phương án hệ thống phù hợp | Không gọi method trên loader `null`; thường class được bootstrap định nghĩa. |

### Class loader của resource và class loader định nghĩa class khác nhau

Ví dụ plugin JAR có class `impl.Plugin` do plugin loader định nghĩa. Nếu code host cố gọi:

```java
HostMain.class.getClassLoader()
        .getResourceAsStream("plugin/settings.json");
```

có thể nhận `null`, vì host loader không nhìn thấy JAR plugin (thường plugin loader là **child**, host là **parent**). Ngược lại, code trong plugin dùng `impl.Plugin.class.getResourceAsStream("/plugin/settings.json")` có thể thấy resource riêng nếu lookup được loader/module của plugin cho phép.

**Đừng đổi tất cả sang system loader** khi thấy `null`. Phải biết resource thuộc artifact/module nào và **loader nào được thiết kế để nhìn thấy nó**.

## 11. Thread Context Class Loader (TCCL) không phải loader mặc định của mọi API

Đọc TCCL:

```java
ClassLoader context =
        Thread.currentThread().getContextClassLoader();
```

Đây là snippet hợp lệ trong method. Trong launcher phổ biến, main thread có TCCL là system loader; framework có thể đổi khi thực thi plugin code.

Hai lời gọi sau **không tương đương**:

```java
MyService.class.getResourceAsStream("service.json");
Thread.currentThread().getContextClassLoader()
        .getResourceAsStream("service.json");
```

- Lời gọi trên class dùng **package-relative** với `MyService` và lookup theo class/module.
- Lời gọi qua TCCL dùng **resource name từ root namespace** của TCCL và chính loader object đó. Nó không tự gắn với package `MyService`.
- TCCL có thể là `null` trong một số ngữ cảnh; nếu framework chấp nhận điều đó, cần quyết định fallback tường minh. Không dereference null.
- `ClassLoader.getSystemResourceAsStream(name)` là một API static dùng **system class loader**, không phải mặc định dùng TCCL.
- TCCL không thay đổi parent của những loader khác và không làm resource không có trong artifact tự xuất hiện.

Các API framework như `ServiceLoader` có thể dùng TCCL cho discovery, nhưng code tự gọi `SomeClass.class.getResourceAsStream` **không tự chuyển sang TCCL** chỉ vì thread đang chạy trong plugin context.

## 12. Named modules: tìm thấy class nhưng resource vẫn có thể bị che

Từ Java 9, resource lookup qua **named modules** có quy tắc **strong encapsulation**. Javadoc của `ClassLoader.getResource`/`getResourceAsStream` chỉ rõ resource trong các package của named module có thể không nhìn thấy nếu package đó **không được mở vô điều kiện** cho các lookup kiểu này (trừ những quy định riêng như resource kết thúc bằng `.class`). Một package có `exports` không đồng nghĩa mọi resource bên trong đều có thể đọc qua loader từ bên ngoài.

Các khái niệm phải phân biệt:

- **Module readability**: code ở module A có đọc module B hay không?
- **Exports**: package có cho các module khác truy cập public types không?
- **Opens**: package có cho phép cơ chế reflection/resource access theo quy tắc JPMS không?
- **Loader visibility**: loader có thể xác định/tra cứu mục resource hay không?
- **Resource access**: API nào được gọi, từ module/caller nào, package có được mở cho caller đó không?

Nếu code **bên trong một module** cần đọc resource được đóng gói trong chính module, `SomeClass.class.getResourceAsStream(...)` là lựa chọn tự nhiên vì API này gắn với module của class. Trong các trường hợp cross-module phức tạp, `Module.getResourceAsStream(name)` có quy tắc cụ thể về quyền truy cập; cần đọc Javadoc và kiểm thử trong cấu hình module thực tế.

Ví dụ module descriptor:

```java
module com.example.reports {
    exports com.example.reports.api;
    opens com.example.reports.templates;
}
```

Đây là **module-info.java minh họa**, không phải ví dụ chạy độc lập. `opens` vô điều kiện cho package có thể làm resource trong package ấy nhìn thấy qua một số API resource lookup. Tuy nhiên mở package công khai cũng có ảnh hưởng về deep reflection; **không nên mở tràn lan chỉ để tránh một lỗi path**. Nếu module tự đọc resource riêng, nên dùng API và thiết kế package/module phù hợp.

Khi đã kiểm tra resource nằm trong JAR/module nhưng `getResourceAsStream` vẫn là `null`, đừng kết luận ngay loader sai; **encapsulation** có thể là nguyên nhân.

## 13. Đọc dữ liệu text, binary và quản lý charset

`getResourceAsStream` trả byte stream. API không biết resource là UTF-8, ISO-8859-1, PNG hay Protobuf. Chính caller phải quyết định **cách giải mã nội dung**.

### Text nhỏ

```java
static String readUtf8(java.io.InputStream stream)
        throws java.io.IOException {
    try (java.io.InputStream in = stream) {
        return new String(in.readAllBytes(),
                java.nio.charset.StandardCharsets.UTF_8);
    }
}
```

Method này nhận **stream không null**, đọc hết vào bộ nhớ và đóng stream. Chỉ phù hợp resource có kích thước vừa phải; đừng dùng `readAllBytes()` cho một resource rất lớn hoặc nguồn untrusted có thể stream không giới hạn.

### Text lớn

Với tài liệu lớn, đọc theo buffer hoặc `BufferedReader`:

```java
try (InputStream input = loader.getResourceAsStream(name)) {
    if (input == null) {
        throw new FileNotFoundException(name);
    }
    try (BufferedReader reader = new BufferedReader(
            new InputStreamReader(input, StandardCharsets.UTF_8))) {
        String line;
        while ((line = reader.readLine()) != null) {
            // Xử lý từng dòng thay vì giữ toàn bộ vào RAM.
        }
    }
}
```

Đây là **snippet**, giả sử đã khai báo `loader`, `name` và import `java.io.*`/`java.nio.charset.StandardCharsets`. Chú ý `try-with-resources` **chấp nhận reference null** lúc khởi tạo resource, nhưng ta vẫn phải kiểm tra trước khi dùng; việc có `try (...)` không làm resource thiếu tự tạo stream. Đóng `BufferedReader` cũng đóng luồng đầu vào bên dưới.

### Binary

Đối với PNG/ZIP/keystore/certificate bytes, **không** gọi `new String(bytes, UTF_8)` rồi ghi ngược ra file nếu muốn giữ từng byte. Hãy sao chép stream sang output:

```java
try (InputStream input = loader.getResourceAsStream(name)) {
    if (input == null) {
        throw new FileNotFoundException(name);
    }
    try (OutputStream output = Files.newOutputStream(destination)) {
        input.transferTo(output);
    }
}
```

Snippet cần biến `loader`, `name`, `destination` và imports `java.io.*`/`java.nio.file.Files`. `InputStream.transferTo` có từ Java 9, truyền bytes mà không đổi charset. Trước khi cho ghi file theo `destination`, ứng dụng vẫn phải xác thực đường dẫn được phép. Không dùng resource lookup như cơ chế cấp quyền tùy ý để đọc/ghi file trên máy.

### Resource có thể rỗng

`getResourceAsStream` trả **non-null stream** cho resource tồn tại nhưng 0 byte; đọc sẽ trả EOF. **Không đồng nhất file rỗng với missing**. Nếu config bắt buộc phải có nội dung, sau khi mở stream cần validation riêng (ví dụ parser yêu cầu key bắt buộc).

## 14. Đóng luồng, lỗi I/O và quyền sở hữu tài nguyên

Một tài nguyên có thể nằm trong JAR và việc đọc có thể giữ handle tới archive hoặc kết nối nguồn dữ liệu. **Đóng stream sau khi dùng** để trả tài nguyên về hệ thống và tránh resource leaks.

Mẫu code nên tuân theo:

1. **Tra cứu:** `InputStream opened = loader.getResourceAsStream(name)`.
2. **Kiểm tra missing:** `opened == null` thì ném lỗi hoặc fallback theo contract.
3. **Đọc trong `try-with-resources`.**
4. **Parse/validate nội dung.**
5. **Truyền lỗi I/O hoặc bọc kèm ngữ cảnh mà vẫn giữ cause.**

Không nên:

```java
try {
    InputStream input = loader.getResourceAsStream(name);
    return new String(input.readAllBytes(), StandardCharsets.UTF_8);
} catch (Exception ignored) {
    return "";
}
```

Đây là **mẫu sai**: vừa có `NullPointerException` khi missing, vừa có thể nuốt `IOException`, lại không đóng stream. Chuỗi rỗng sẽ đánh đồng resource thiếu, resource hỏng và resource có nội dung rỗng.

Một wrapper production có thể chọn ném `UncheckedIOException` từ API không khai báo checked exceptions. Nếu vậy hãy **giữ cause gốc** để người dùng phân biệt "not found" với "cannot read" và biết resource name, loader/context liên quan.

### Resource nằm trong JAR và stream có thể mở được nhưng đọc hỏng

`getResourceAsStream` có thể trả stream trước khi các lỗi đọc bytes được phát hiện. Không giả định non-null stream có nghĩa dữ liệu hoàn chỉnh hoặc hợp lệ. Với JSON/CSV/properties, cần xử lý parse errors và validation riêng; log tên resource và nguyên nhân, không tự động chuyển mọi lỗi thành `null`.

## 15. Một resource tồn tại nhiều lần: ưu tiên và xung đột

Hai dependency JAR cùng có `config/app.properties`:

```text
a.jar!/config/app.properties
b.jar!/config/app.properties
```

Nếu ứng dụng dùng:

```java
ClassLoader loader = App.class.getClassLoader();
URL selected = loader.getResource("config/app.properties");
```

Đây là snippet minh họa cần `App`/`URL`. Loader có thể trả **một URL được chọn** theo policy của nó. Không có ý nghĩa chuẩn rằng `a.jar` luôn được ưu tiên trong mọi build và launcher. Nếu nhiều resources cần hợp nhất, `getResources(name)` có thể cung cấp enumeration để ứng dụng áp chính sách rõ ràng.

Trường hợp điển hình:

- `META-INF/services/<service binary name>` thường xuất hiện ở nhiều JAR và cần cơ chế discovery đọc nhiều resources.
- `logging.properties` hay `config/app.properties` xuất hiện ở nhiều JAR có thể tạo lỗi cấu hình khó thấy nếu lookup chỉ trả bản đầu tiên.
- Resource trùng tên giữa host/plugin có thể vô tình lấy bản của parent thay vì plugin.

Cách phòng tránh:

- Dùng tên resource có namespace rõ, ví dụ `plugins/my-feature/settings.json`.
- Định nghĩa nơi đặt config override có thứ tự ưu tiên **được ghi trong tài liệu**.
- Nếu plugin phải có dữ liệu riêng, dùng loader/module của plugin hoặc một API cung cấp resource tường minh.
- Kiểm thử **artifact thực tế**, không chỉ test file nguồn trong IDE.
- In/ghi log URL bằng `getResource` khi debug, nhưng tránh tiết lộ đường dẫn nhạy cảm trong thông báo dành cho người dùng cuối.

## 16. Kiểm tra bảo mật: đừng biến resource name thành đường dẫn tùy ý

Khi tên resource được tạo từ đầu vào không tin cậy:

```java
String name = "templates/" + userChoice + ".txt";
InputStream stream = loader.getResourceAsStream(name);
```

Đây là snippet giải thích nguy cơ. Không được giả định việc cộng chuỗi như vậy tự ngăn tên có dấu `../`, package namespace bất ngờ hoặc một resource nhạy cảm nằm trong artifact. **Ưu tiên allowlist** các template được phép thay vì nhận đường dẫn tùy ý:

```java
static String allowedTemplate(String choice) {
    return switch (choice) {
        case "welcome" -> "templates/welcome.txt";
        case "goodbye" -> "templates/goodbye.txt";
        default -> throw new IllegalArgumentException(
                "Unknown template: " + choice);
    };
}
```

Đây là method Java 17+ hợp lệ để đặt trong class, nhưng không phải chương trình độc lập. Nó ánh xạ các giá trị nghiệp vụ sang resource names cố định, giúp dễ audit. Nếu resource data cần bảo mật, không đóng gói credentials/password production trực tiếp vào JAR và xem việc che tên file như một cơ chế bảo vệ.

**Lưu ý:** `getResourceAsStream` là API tra cứu và đọc; nó không tạo sandbox hoàn chỉnh. Một custom loader hoặc URL handler có thể có side effects, và resource contents vẫn cần validation trước khi dùng.

## 17. Bảng lỗi thường gặp và cách sửa

| Triệu chứng | Nguyên nhân hay gặp | Cách kiểm tra và sửa |
| --- | --- | --- |
| `getResourceAsStream(...) == null` dù tệp trong repository | Build không copy resource vào classpath/module artifact | Kiểm tra `out/...`, `target/classes`, `build/resources/main` và JAR entry đúng đường dẫn. |
| `null` khi dùng `"/config/x"` qua `ClassLoader` | Có slash đầu khiến tên không khớp | Dùng `loader.getResourceAsStream("config/x")`. |
| `null` khi dùng `SomeClass.class.getResourceAsStream("x")` | API tìm theo package của class, không từ root | Chuyển thành `"/x"` nếu resource nằm ở root, hoặc đặt file trong package. |
| Chạy IDE được, JAR thất bại | Resource không được đóng gói hoặc bị shadow | Xem `jar --list`, build artifact, classpath và URL lookup. |
| `NullPointerException` ở `InputStreamReader`/`Properties.load` | Stream trả `null` chưa được kiểm tra | Check trước, báo lỗi kèm resource name, không nuốt lỗi. |
| Văn bản tiếng Việt lỗi dấu | Đọc text với charset sai, hoặc `Properties.load(InputStream)` dùng ISO-8859-1 | Đọc với `InputStreamReader(StandardCharsets.UTF_8)` và `Properties.load(Reader)`. |
| `IOException` khi resource có thật | Lỗi I/O khi mở/đọc archive/network hoặc nguồn loader | Giữ cause, phân biệt với missing, kiểm tra artifact và nguồn. |
| Resource ở plugin JAR nhưng host không thấy | Host loader không nhìn được JAR ở child plugin loader | Dùng plugin-defined class/loader hoặc thiết kế bridge phù hợp. |
| Đọc nhầm cấu hình ở JAR khác | Nhiều resources cùng tên và lookup chọn bản khác | Dùng `getResources`/`getResource` để debug, namespace và thứ tự ưu tiên rõ. |
| Trong named module tìm class được nhưng resource không đọc được | Module resource encapsulation | Kiểm tra package `opens` và chọn `Class`/`Module` resource API phù hợp. |
| `FileNotFoundException` khi dùng `Files.newInputStream` nhưng lookup resource khác kết quả | File-system path ≠ classpath resource name | Chọn đúng API theo nơi lưu resource. |
| Resource tồn tại nhưng nội dung rỗng | Entry có 0 byte | Tách tồn tại (non-null stream) khỏi content validation. |
| Memory tăng khi đọc file lớn | `readAllBytes` nạp toàn bộ content vào RAM | Stream theo buffer/line, giới hạn dung lượng và size check. |

### Một quy trình debug ngắn nhưng đủ thông tin

1. Ghi **resource name thực tế**, có/không có leading slash.
2. Ghi **API được dùng**: `Class.getResourceAsStream` hay `ClassLoader.getResourceAsStream`; hai API không cùng quy tắc path.
3. Xác định **Class/ClassLoader/Module** được dùng để lookup. Với plugin, không mặc định dùng system loader.
4. Kiểm tra file **đã vào runtime artifact** với đúng case và directory chưa. Trên Linux, case khác nhau sẽ tạo tên entry khác nhau; JAR entries cũng có tên case-sensitive.
5. Dùng `getResource(name)` để xem URL được chọn, hoặc `getResources(name)` khi nghi trùng tên.
6. Nếu chạy named module, kiểm tra **module encapsulation** và package opens.
7. Nếu có stream mà vẫn lỗi, xem **charset, parser, nội dung rỗng, IOException, kích thước**.
8. Với resource bắt buộc, ném lỗi rõ ràng; với resource tùy chọn, áp fallback được thiết kế.

## 18. Gợi ý kiểm thử tự động

Đối với module có tài nguyên quan trọng, nên kiểm tra:

- **Unit test đọc resource bắt buộc**: nội dung parse được, có keys bắt buộc, giá trị đúng schema.
- **Test resource thiếu**: phương thức wrapper ném exception mong muốn, thông điệp có resource name; không trả chuỗi trống mơ hồ.
- **Test resource tùy chọn**: fallback chỉ dùng khi missing; lỗi parse/I/O không bị coi là missing.
- **Test UTF-8**: nội dung có dấu tiếng Việt hoặc ký tự ngoài ASCII vẫn đọc chính xác.
- **Test package-relative versus root**: đường dẫn được chuẩn hóa đúng; slash đầu xử lý phù hợp API.
- **Integration test chạy từ JAR cuối cùng**: kiểm tra file thật sự được đóng gói và loader thấy tài nguyên.
- **Test nhiều loader/plugin** nếu kiến trúc hỗ trợ: resource plugin được lookup bởi loader phù hợp, không bị bản ở parent che khuất không mong muốn.
- **Test named module** nếu dùng JPMS: package opens/encapsulation và các resource API hoạt động trong môi trường production giống test.

### Mẫu assertion độc lập build tool

Ví dụ kiểm tra một resource bắt buộc trên classpath:

```java
static void assertResourcePresent(Class<?> anchor, String absoluteName) {
    try (InputStream input = anchor.getResourceAsStream(absoluteName)) {
        if (input == null) {
            throw new AssertionError(
                    "Missing packaged resource: " + absoluteName);
        }
    } catch (java.io.IOException e) {
        throw new java.io.UncheckedIOException(e);
    }
}
```

Đây là **method minh họa**, cần import `java.io.InputStream`, đặt trong class và gọi với `absoluteName` bắt đầu bằng `/` khi muốn root. Dùng `try-with-resources` kể cả trong assertion để tránh resource leak. Nếu resource cần kiểm chứng nội dung, đọc/parse sau khi xác nhận non-null.

Không chỉ test với IDE source roots. Integration test nên dùng **distribution artifact cuối cùng** vì lỗi thường nằm ở khâu đóng gói.

## 19. Những ngộ nhận cần tránh

- **"Không tìm thấy resource thì `getResourceAsStream` ném `FileNotFoundException`."** Sai: API trả `null`; caller tự chọn xử lý.
- **"Thêm `/` ở đầu resource name luôn đúng."** Sai: `Class` hỗ trợ absolute resource name có slash; `ClassLoader` thường yêu cầu tên **không slash đầu**.
- **"Mọi resource path đều tính từ working directory."** Sai: classpath/module lookup khác `Path.of(...)` theo filesystem.
- **"Thấy tệp trong `src/main/resources` thì JVM luôn đọc được."** Sai: build/deploy phải đóng gói nó vào runtime classpath/module image.
- **"`Class.forName` nạp class rồi thì resource ở cạnh class chắc chắn cũng nạp theo."** Sai: class loading và resource lookup là hai API và hai hành vi.
- **"Resource trong JAR phải giải nén ra file vật lý mới dùng được."** Sai: `getResourceAsStream` đọc trực tiếp archive entry qua loader hỗ trợ.
- **"Nếu stream khác null thì dữ liệu chắc chắn hợp lệ."** Sai: tệp có thể rỗng, lỗi I/O hoặc parse.
- **"Có thể bỏ `close()` vì tài nguyên đi cùng ứng dụng."** Sai: stream vẫn cần đóng để giải phóng handles.
- **"`Properties.load(InputStream)` mặc định dùng UTF-8."** Sai: API truyền thống dùng ISO-8859-1; với UTF-8 hãy dùng Reader.
- **"Một resource trùng tên ở nhiều JAR luôn được hợp nhất."** Sai: `getResourceAsStream` thường trả một kết quả; muốn liệt kê dùng `getResources`.
- **"Thay TCCL sẽ khiến mọi `SomeClass.class.getResource...` dùng loader mới."** Sai: API trên `Class` dùng ngữ cảnh class/module tương ứng.
- **"Nếu resource tồn tại thì JPMS không thể chặn lookup."** Sai: named module encapsulation có thể ảnh hưởng.
- **"Không tìm thấy nên cứ trả rỗng và tiếp tục."** Sai với resource bắt buộc: như vậy che lỗi build, deploy và cấu hình.

## 20. Câu hỏi tự kiểm tra

**1. Khi `loader.getResourceAsStream("config/missing.properties")` không tìm thấy, kết quả thông thường là gì?** `null`, không phải `FileNotFoundException` do method trực tiếp ném.

**2. `Demo.class.getResourceAsStream("sample.txt")` tìm ở đâu nếu `Demo` thuộc package `demo`?** Ở `demo/sample.txt` trong namespace resource mà class/module nhìn thấy.

**3. Muốn tìm `sample.txt` ở root bằng API trên `Class` thì viết gì?** `Demo.class.getResourceAsStream("/sample.txt")`.

**4. Muốn tìm cùng entry ở root bằng `ClassLoader` thì viết gì?** `loader.getResourceAsStream("sample.txt")`, không có slash đầu.

**5. Vì sao file tồn tại trong repository nhưng resource lookup vẫn null?** File có thể chưa được copy/đóng gói đúng vào runtime classpath/module artifact, hoặc loader/module không nhìn thấy.

**6. Tại sao bắt buộc kiểm tra null trước khi tạo `InputStreamReader`?** Vì lookup không tìm được sẽ trả `null` và Reader không thể đọc từ một stream null.

**7. Tại sao dùng `try-with-resources`?** Đảm bảo đóng stream khi đọc xong hoặc khi có exception, giảm rò file/JAR handles.

**8. Muốn đọc `.properties` chứa ký tự tiếng Việt UTF-8 bằng Java thì làm thế nào?** Tạo `InputStreamReader(stream, StandardCharsets.UTF_8)` rồi gọi `Properties.load(Reader)`.

**9. Vì sao `new File(classUrl.getFile())` không đáng tin cho resource trong JAR?** Vì URL có thể là `jar:...!...` hoặc bị percent-encoding, không tương ứng đường dẫn file vật lý.

**10. Một plugin có resource riêng nhưng system loader không thấy; sửa thế nào?** Tra bằng loader/class/module gắn với plugin hoặc thiết kế loader graph phù hợp, không chỉ đổi filename.

**11. Khi hai JAR có cùng resource name, API nào giúp kiểm tra mọi candidate?** `ClassLoader.getResources(name)` trả enumeration các URL có thể nhìn thấy.

**12. Resource tồn tại nhưng stream có 0 byte: có phải missing không?** Không. Non-null stream là dấu hiệu resource được mở; cần validate nội dung riêng.

**13. Trong named module, điều gì ngoài path có thể ngăn đọc resource?** Encapsulation, package `opens` và quy tắc của API `ClassLoader`/`Class`/`Module` được sử dụng.

**14. Resource tùy chọn nên xử lý lỗi I/O khi đọc như thế nào?** Không đồng nhất IOException với resource vắng mặt; báo lỗi hoặc áp chính sách xử lý rõ ràng.

## 21. Tài liệu chuẩn

- [Java SE 17 — `ClassLoader` API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html): `getResource`, `getResourceAsStream`, `getResources`, parent delegation và resource/module encapsulation.
- [Java SE 17 — `Class` API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html): `getResource` và `getResourceAsStream`, tên tuyệt đối bắt đầu bằng `/` và tên tương đối với package.
- [Java SE 17 — `Module` API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Module.html): `getResourceAsStream` trong module, điều kiện truy cập qua encapsulation.
- [Java SE 17 — `InputStream` API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/InputStream.html): quản lý stream, `readAllBytes`, `transferTo` và `close`.
- [Java SE 17 — `Properties` API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Properties.html): khác biệt `load(InputStream)` so với `load(Reader)` và mã hóa ký tự.
- [JDK 17 — `jar` tool](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jar.html): tạo và liệt kê nội dung JAR, xác thực resource đã được đóng gói.

**Ghi nhớ:** **`getResourceAsStream` tìm resource qua loader/module và trả stream hoặc `null`; nó không tìm trong thư mục source theo phép màu, cũng không tự ném exception khi thiếu.** Hãy chọn đúng cách diễn giải đường dẫn (`Class` tương đối với package, `ClassLoader` từ resource root), xác minh artifact runtime, kiểm tra null, đọc với charset/format thích hợp, đóng stream và phân biệt **không tồn tại** với **đọc/parse thất bại**.
