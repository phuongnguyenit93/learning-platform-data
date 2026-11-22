# Đọc cấu hình từ thư mục và JAR bằng API resource trong Java

## 1. Mục tiêu thực hành

Cùng một ứng dụng Java cần đọc file cấu hình khi chạy trong IDE, bằng lệnh `java -cp` với thư mục chứa class, và sau khi đóng gói thành file `.jar`. Nếu mã viết:

~~~java
Path path = Path.of("resources/config/app.properties");
~~~

thì đây là **đường dẫn hệ thống tệp tương đối với working directory**, không phải đường dẫn classpath. Khi triển khai, `resources` có thể không tồn tại dưới dạng thư mục và file có thể nằm **bên trong JAR**. Vì vậy giải pháp thích hợp cho cấu hình **đóng gói cùng ứng dụng** là sử dụng các **resource APIs**:

- `ClassLoader.getResource(name)` để tìm một `URL` tới resource.
- `ClassLoader.getResourceAsStream(name)` để mở luồng đọc bytes, bất kể resource nằm trong thư mục classpath hay entry của JAR.
- `Class.getResource(name)` và `Class.getResourceAsStream(name)` khi muốn định vị tương đối với package của một class.
- `Properties.load(Reader)` hoặc định dạng parser khác để đọc dữ liệu sau khi có luồng.

**Mục tiêu cuối bài:** Tự tạo một ứng dụng Java 17+, đọc cùng file cấu hình bằng một chương trình duy nhất, chạy được hai cách (directory/JAR), quan sát URL `file:` so với `jar:`, xử lý file không tồn tại, hiểu quy tắc dấu `/`, tránh chuyển URL của JAR thành `File`, và kiểm tra resource khi đóng gói Maven/Gradle.

## 2. Resource khác file trên hệ thống tệp như thế nào?

Một **resource** ở đây là dữ liệu được nhận diện bởi một **tên logic trong phạm vi classpath/module**, ví dụ `config/app.properties`, `demo/local-note.txt`, ảnh/logo hoặc tệp JSON. Một entry resource có thể được lấy từ:

~~~text
Classpath root là thư mục:
out/classes/
├── demo/
│   └── ResourceConfigDemo.class
├── config/
│   └── app.properties
└── demo/
    └── local-note.txt

Hoặc classpath root là JAR:
resource-demo.jar
├── META-INF/MANIFEST.MF
├── demo/ResourceConfigDemo.class
├── config/app.properties
└── demo/local-note.txt
~~~

Ở sơ đồ đầu, thư mục `demo/` chỉ được hiểu là **một thư mục chung**: hai entry `ResourceConfigDemo.class` và `local-note.txt` đều nằm trong đó; không cần tạo hai thư mục `demo`.

**Classpath root** là vị trí mà trình nạp class tìm tên phân cấp:

- Tên class `demo.ResourceConfigDemo` tương ứng entry `demo/ResourceConfigDemo.class`.
- Tên resource `config/app.properties` tương ứng entry `config/app.properties`.
- Không bao gồm tiền tố `src/`, `resources/` hoặc `out/classes/` trong tên resource nếu chúng chỉ là source/build directories.

Nếu chương trình chỉ dùng:

~~~java
Files.newInputStream(Path.of("config/app.properties"));
~~~

nó sẽ đọc file từ working directory và **chỉ chạy khi đúng file vật lý đang tồn tại ở vị trí đó**. Ngược lại:

~~~java
InputStream stream =
        ResourceConfigDemo.class.getClassLoader()
                .getResourceAsStream("config/app.properties");
~~~

sẽ tìm resource trong những nguồn mà class loader nhìn thấy. Đây là **đoạn minh họa** đặt trong class `ResourceConfigDemo`; phần 5 có mã hoàn chỉnh với xử lý null và đóng stream.

## 3. Bốn API quan trọng và quy tắc tên resource

| API | Đối số tên | Giá trị trả về |
| --- | --- | --- |
| `loader.getResource("config/app.properties")` | Tên tương đối **classpath root**, không có `/` đầu | `URL` hoặc `null` |
| `loader.getResourceAsStream("config/app.properties")` | Như trên | `InputStream` hoặc `null` |
| `SomeClass.class.getResource("/config/app.properties")` | Bắt đầu `/` ⇒ từ classpath/module root theo ngữ cảnh API | `URL` hoặc `null` |
| `SomeClass.class.getResource("local-note.txt")` | Không `/` ⇒ tương đối với package của `SomeClass` | `URL` hoặc `null` |

Giả sử `SomeClass` nằm trong package `demo`:

~~~text
SomeClass.class.getResource("local-note.txt")
    -> demo/local-note.txt

SomeClass.class.getResource("/demo/local-note.txt")
    -> demo/local-note.txt

SomeClass.class.getResource("/config/app.properties")
    -> config/app.properties

SomeClass.class.getClassLoader()
    .getResource("config/app.properties")
    -> config/app.properties
~~~

**Một lỗi cực phổ biến:**

~~~java
loader.getResourceAsStream("/config/app.properties");
~~~

Với `ClassLoader`, tên chuẩn phải là `config/app.properties` **không có slash đầu**. `Class#getResource` là API **khác**, nó xử lý slash đầu để biểu thị absolute name. Không có một quy tắc chung áp dụng nguyên xi cho mọi method có tên `getResource`.

### 3.1. Resource names dùng slash

Kể cả chạy Windows, resource name là đường dẫn **phân cấp với dấu `/`**, không phải `\` hoặc đường dẫn ổ `C:\`. Ví dụ đúng:

~~~text
config/app.properties
templates/email/welcome.html
demo/local-note.txt
~~~

Tên `"config\\app.properties"` trong Java source không phải đường resource portable.

### 3.2. Khi nào nên dùng Class thay vì ClassLoader?

- Dùng `MyClass.class.getResource("file.txt")` khi file gắn với package chứa class.
- Dùng `MyClass.class.getResource("/config/app.properties")` cho một resource dưới root.
- Dùng `MyClass.class.getClassLoader().getResourceAsStream("...")` khi mục tiêu là tìm trong lookup scope của defining class loader.
- Với ứng dụng named module, semantics khác classpath truyền thống: `Class#getResource` có thể tìm trong module của class và tuân thủ các quy tắc encapsulation; không đồng nhất mọi overload với một global classpath search.

Nên chọn API có tên đường dẫn rõ ràng, tránh dựa vào **current working directory** nếu dữ liệu được đóng gói cùng bytecode.

## 4. Bài thực hành: bộ file và kết quả mong muốn

Ta tạo một project nhỏ, **không cần Maven, Gradle hay thư viện ngoài**:

~~~text
resource-practice/
├── src/
│   └── demo/
│       └── ResourceConfigDemo.java
└── resources/
    ├── config/
    │   └── app.properties
    └── demo/
        └── local-note.txt
~~~

Ý nghĩa:

- `src/demo/ResourceConfigDemo.java`: chương trình có main.
- `resources/config/app.properties`: file cấu hình đóng gói vào root `config/`.
- `resources/demo/local-note.txt`: file mẫu để phân biệt lookup tương đối với package `demo`.

Sau biên dịch và copy resources, classpath directory phải có:

~~~text
out/classes/
├── demo/
│   ├── ResourceConfigDemo.class
│   └── local-note.txt
└── config/
    └── app.properties
~~~

Sau tạo JAR, cấu trúc **entry names** bên trong JAR vẫn là `demo/...` và `config/...`. Chính sự thống nhất này cho phép **không sửa Java source khi đổi hình thức triển khai**.

## 5. Mã Java 17+ hoàn chỉnh

### 5.1. resources/config/app.properties

Tạo file văn bản UTF-8 với **nội dung chính xác**:

~~~properties
app.name=Resource Demo
app.port=8080
feature.enabled=true
~~~

Các khóa cố ý là ASCII để transcript stdout độc lập locale/terminal encoding. Ở hệ thống thật có thể dùng Unicode; phần 8 giải thích vì sao chọn đúng `Reader` khi load Properties.

### 5.2. resources/demo/local-note.txt

Tạo file text UTF-8 có một dòng:

~~~text
package-local-resource
~~~

### 5.3. src/demo/ResourceConfigDemo.java

~~~java
package demo;

import java.io.FileNotFoundException;
import java.io.IOException;
import java.io.InputStream;
import java.io.InputStreamReader;
import java.net.URL;
import java.nio.charset.StandardCharsets;
import java.util.Enumeration;
import java.util.Properties;

public final class ResourceConfigDemo {
    private static final String CONFIG = "config/app.properties";

    private ResourceConfigDemo() {
    }

    private static Properties loadConfig(ClassLoader loader)
            throws IOException {
        Properties values = new Properties();

        try (InputStream input = loader.getResourceAsStream(CONFIG)) {
            if (input == null) {
                throw new FileNotFoundException(
                        "Missing classpath resource: " + CONFIG);
            }

            try (InputStreamReader reader = new InputStreamReader(
                    input, StandardCharsets.UTF_8)) {
                values.load(reader);
            }
        }

        return values;
    }

    private static String readLocalNote() throws IOException {
        try (InputStream input = ResourceConfigDemo.class
                .getResourceAsStream("local-note.txt")) {
            if (input == null) {
                throw new FileNotFoundException(
                        "Missing package resource: demo/local-note.txt");
            }
            return new String(
                    input.readAllBytes(), StandardCharsets.UTF_8).strip();
        }
    }

    public static void main(String[] args) throws Exception {
        ClassLoader loader = ResourceConfigDemo.class.getClassLoader();

        URL byLoader = loader.getResource(CONFIG);
        if (byLoader == null) {
            throw new FileNotFoundException(
                    "Missing classpath resource: " + CONFIG);
        }

        URL byClass = ResourceConfigDemo.class
                .getResource("/" + CONFIG);

        Properties config = loadConfig(loader);

        String name = config.getProperty("app.name");
        int port = Integer.parseInt(
                config.getProperty("app.port"));
        boolean enabled = Boolean.parseBoolean(
                config.getProperty("feature.enabled"));

        System.out.println("resource found: " + (byLoader != null));
        System.out.println("absolute Class lookup matches: "
                + byLoader.equals(byClass));
        System.out.println("protocol: " + byLoader.getProtocol());
        System.out.println("name: " + name);
        System.out.println("port: " + port);
        System.out.println("feature enabled: " + enabled);
        System.out.println("local note: " + readLocalNote());

        Enumeration<URL> matches = loader.getResources(CONFIG);
        int count = 0;
        while (matches.hasMoreElements()) {
            matches.nextElement();
            count++;
        }
        System.out.println("matching resources: " + count);
    }
}
~~~

### 5.4. Điểm cần hiểu trong mã

**Chọn loader từ class đã biết:** `ResourceConfigDemo.class.getClassLoader()` là defining loader của class ứng dụng. Trong demo này là application loader và khác null. Với các class do bootstrap loader định nghĩa, `getClassLoader()` có thể trả null; không nên mặc định mọi class đều có một loader object khác null.

**Tìm resource qua URL:** `getResource(CONFIG)` trả `URL` nếu tìm được. Khi nạp từ thư mục thông thường, protocol hay là `file`. Khi đọc entry từ JAR, protocol của URL được hỗ trợ thường là `jar`. Chương trình **chỉ in protocol**, không in toàn bộ URL có đường dẫn máy khác nhau.

**Đọc nội dung qua stream:** `getResourceAsStream` trả `null` nếu không tìm thấy resource hoặc không truy cập được theo cơ chế của loader. Phải kiểm tra null **trước** khi tạo `InputStreamReader`, nếu không sẽ gặp `NullPointerException` kém rõ nghĩa.

**Đóng tài nguyên:** `try-with-resources` đóng reader/stream kể cả khi `Properties.load` ném `IOException`. Ở đây cả reader lẫn input đều được khai báo trong nested try; việc đóng input lần nữa an toàn đối với `InputStream` chuẩn, nhưng có thể giản lược thành một try với cả hai resources nếu đã kiểm tra null.

**Đọc UTF-8 rõ ràng:** `Properties.load(Reader)` giải mã theo charset mà reader đã chọn. Đoạn code dùng `StandardCharsets.UTF_8` thay vì phụ thuộc vào charset mặc định của OS hoặc nhầm với overload `load(InputStream)`.

**Class-relative lookup:** `ResourceConfigDemo.class.getResourceAsStream("local-note.txt")` tìm `demo/local-note.txt` vì class đang ở package `demo`. Nếu viết `"/local-note.txt"` thì lookup từ root và sẽ **không** trỏ tới file đã tạo.

**getResources:** `loader.getResources(CONFIG)` trả `Enumeration<URL>` những matches tìm được. Trong hai lệnh chạy cơ bản dưới đây, mỗi process có một nguồn chứa `config/app.properties`, nên count dự kiến là 1. Trong ứng dụng có nhiều classpath roots/JARs cùng tên resource, count có thể lớn hơn.

**Validate cấu hình:** `Integer.parseInt` sẽ ném `NumberFormatException` nếu `app.port` không phải số. `Boolean.parseBoolean` trả false cho mọi chuỗi không bằng "true" (không phân biệt hoa/thường), kể cả typo như `tru`; đối với config production nên kiểm tra giá trị hợp lệ tường minh thay vì âm thầm chấp nhận.

## 6. Chạy trực tiếp từ thư mục classpath

### 6.1. Linux/macOS (bash, zsh)

Đứng tại thư mục `resource-practice`:

~~~bash
mkdir -p out/classes
javac --release 17 -d out/classes src/demo/ResourceConfigDemo.java
cp -R resources/config resources/demo out/classes/
java -cp out/classes demo.ResourceConfigDemo
~~~

Lệnh copy tạo đúng `out/classes/config/app.properties` và `out/classes/demo/local-note.txt`. Nếu copy vào sai `out/classes/resources/config`, tên lookup `config/app.properties` sẽ không khớp.

### 6.2. Windows PowerShell

~~~powershell
New-Item -ItemType Directory -Force out/classes | Out-Null
javac --release 17 -d out/classes src/demo/ResourceConfigDemo.java
Copy-Item -Recurse -Force resources/config out/classes
Copy-Item -Recurse -Force resources/demo out/classes
java -cp out/classes demo.ResourceConfigDemo
~~~

**Không cần sửa Java resource names theo dấu backslash của Windows.** Các resource names vẫn dùng `/` như đã viết trong source.

### 6.3. Stdout dự kiến: directory

~~~text
resource found: true
absolute Class lookup matches: true
protocol: file
name: Resource Demo
port: 8080
feature enabled: true
local note: package-local-resource
matching resources: 1
~~~

Điều kiện cho transcript chính xác: classpath chỉ gồm `out/classes` như trong lệnh; không có classpath root khác chứa `config/app.properties`; các file có nội dung đúng; chạy bằng JDK thông thường hỗ trợ URL `file:`. Vị trí working directory cần đúng để lệnh compile/copy tìm được source, **nhưng bản thân phép đọc resource không phụ thuộc working directory** sau khi classes/resources đã nằm đúng root.

## 7. Đóng gói thành JAR thực thi rồi đọc cùng cấu hình

Sau khi thực hiện mục 6 (đã có `out/classes` chứa cả `.class` và resource files), tạo JAR:

~~~bash
jar --create --file out/resource-demo.jar \
    --main-class demo.ResourceConfigDemo \
    -C out/classes .
~~~

Lệnh trên dùng dấu `\` xuống dòng dành cho bash/zsh. Trong Windows PowerShell hoặc CMD, dùng **một dòng**:

~~~powershell
jar --create --file out/resource-demo.jar --main-class demo.ResourceConfigDemo -C out/classes .
~~~

Kiểm tra nội dung:

~~~bash
jar --list --file out/resource-demo.jar
~~~

Các entry cần tồn tại (JAR có thể chứa thêm `META-INF/` hoặc entry trật tự khác):

~~~text
META-INF/MANIFEST.MF
demo/ResourceConfigDemo.class
demo/local-note.txt
config/app.properties
~~~

Chạy JAR:

~~~bash
java -jar out/resource-demo.jar
~~~

**Stdout dự kiến khi chạy từ JAR:**

~~~text
resource found: true
absolute Class lookup matches: true
protocol: jar
name: Resource Demo
port: 8080
feature enabled: true
local note: package-local-resource
matching resources: 1
~~~

Khi đóng gói đúng, tất cả **business configuration values** và package resource giống hệt chạy từ thư mục. Điểm chủ yếu thay đổi là `protocol: jar`, thể hiện resource được cung cấp qua một JAR URL thay vì một file URL.

**Chú ý:** `java -jar` thường dùng `Main-Class` từ manifest và không lấy app classpath từ `-cp` như cách gọi main class thông thường. Nếu cần dependency JAR khác, phải cấu hình manifest class path, module path hoặc dùng phương án launcher/packaging phù hợp. Demo này không có dependency ngoài JDK.

## 8. Đọc Properties đúng encoding

Java có hai overload quan trọng:

~~~java
Properties p = new Properties();
p.load(inputStream);
~~~

và:

~~~java
Properties p = new Properties();
p.load(reader);
~~~

Đây là **snippets minh họa** với biến `inputStream` hoặc `reader` đã mở. Điểm khác:

- `load(InputStream)` định nghĩa diễn giải bytes của `.properties` theo **ISO-8859-1** và xử lý `\uXXXX` escapes theo format, không tự coi là UTF-8.
- `load(Reader)` đọc các characters do `Reader` cung cấp. Khi reader là `new InputStreamReader(stream, UTF_8)`, file có thể chứa tiếng Việt UTF-8 như `app.title=Quản lý kho`.
- Nếu dùng Java `Properties.store(OutputStream,...)`, cần hiểu định dạng escape/encoding tương ứng; không giả định file do công cụ UTF-8 tạo sẽ luôn được đọc đúng bởi overload InputStream.

Trong chương trình mục 5, `new InputStreamReader(input, StandardCharsets.UTF_8)` bảo đảm encoding **được chỉ định rõ ràng**, không lệ thuộc mặc định hệ điều hành. Cần đảm bảo file `resources/config/app.properties` thực sự được lưu UTF-8.

### 8.1. Properties không chỉ là các dòng key=value đơn giản

`Properties` hỗ trợ comments bằng `#`/`!`, escape characters, continuation lines và các dạng separators. Ví dụ:

~~~properties
# A comment
app.name=Resource Demo
app.port: 8080
feature.enabled=true
~~~

Cả dấu `=` và `:` được chấp nhận theo cú pháp `Properties`. Nếu cấu hình là YAML, JSON, XML hoặc format tùy chỉnh, không nên dùng `Properties.load` để đọc rồi kỳ vọng đúng semantics; vẫn có thể dùng **resource stream**, nhưng parser bên trên phải phù hợp định dạng.

### 8.2. Missing và invalid values

Có thể xử lý fail fast:

~~~java
String rawPort = config.getProperty("app.port");
if (rawPort == null || rawPort.isBlank()) {
    throw new IllegalArgumentException("Missing app.port");
}
int port = Integer.parseInt(rawPort);
if (port < 1 || port > 65535) {
    throw new IllegalArgumentException("Invalid app.port");
}
~~~

Đây là **snippet minh họa** với `config` đã được load. Nó nêu chính sách validation thay vì chấp nhận mọi value tồn tại. Với secrets, tránh in thẳng passwords/tokens và không đóng cứng credentials thật vào JAR.

## 9. Vì sao không đổi resource URL sang File hoặc Path?

Một lỗi quen thuộc:

~~~java
URL url = loader.getResource("config/app.properties");
File file = new File(url.getFile());
~~~

Đây là **mã sai/không portable**, chưa kể phải null-check URL. Khi URL là:

~~~text
file:/.../out/classes/config/app.properties
~~~

một file vật lý có thể tồn tại, nhưng chuyển `URL.getFile()` thẳng sang `File` vẫn có thể xử lý sai escaping, dấu cách, Unicode hoặc URI encoding.

Khi URL là JAR entry, dạng điển hình:

~~~text
jar:file:/.../out/resource-demo.jar!/config/app.properties
~~~

`config/app.properties` **không phải một file riêng trên disk**, nên `new File(url.getFile())` hoặc `Paths.get(url.toURI())` không thể mặc định hoạt động như với file URL. Một số trường hợp có thể xử lý JAR filesystem đặc biệt, nhưng không cần làm vậy để đọc cấu hình.

**Giải pháp mặc định để đọc bytes/text đóng gói:** dùng `getResourceAsStream` hoặc `URL.openStream()` trong `try-with-resources`.

Chỉ chuyển URL thành `Path` khi ứng dụng thực sự yêu cầu path và bạn **biết chắc protocol/file system provider phù hợp**, ví dụ một URL `file:` rồi dùng `Path.of(url.toURI())`, có xử lý exceptions. Không ép mọi resource phải là file vật lý.

### 9.1. Nếu cần chỉnh sửa cấu hình sau khi deploy?

Cấu hình đóng gói trong JAR là **application artifact**; không nên cố mở resource entry để ghi ngược. Nếu config cần chỉnh không rebuild JAR:

- Đặt default config trong JAR.
- Đặt override config ở **external filesystem path** (environment variable, CLI argument, system property hoặc deployment config).
- Đọc default qua `getResourceAsStream`.
- Đọc override bằng `Files.newBufferedReader(path, UTF_8)` nếu file đã được chỉ định và cho phép.
- Áp dụng thứ tự ưu tiên, validate, xử lý lỗi và lifecycle rõ.

Phân biệt hoàn toàn **classpath resource** và **external user-managed config**; mỗi loại dùng API và quyền truy cập phù hợp.

## 10. Trùng tên resource trên nhiều JAR hoặc thư mục

Giả sử:

~~~text
lib-a.jar!/config/app.properties
lib-b.jar!/config/app.properties
out/classes/config/app.properties
~~~

và cả ba nằm trên lookup path. `ClassLoader.getResource("config/app.properties")` tìm **một** resource theo thứ tự tra cứu của loader cụ thể, thường có delegation về parent. `ClassLoader.getResources(...)` có thể liệt kê nhiều matches.

Không nên giả định một **thứ tự nhất quán cho mọi JVM, mọi class loader, mọi module layer**:

- Parent-first và child-first class loaders có thể khác.
- Java module path khác unnamed classpath; các rules cho named modules ảnh hưởng visibility.
- Khi nhiều named modules cùng loader chứa resource trùng, API Javadoc nêu thứ tự tìm có thể **không được quy định**.
- Một ứng dụng phụ thuộc vào “JAR tình cờ được đọc trước” dễ thay config khi build/deploy thay đổi.

Muốn biết tất cả occurrences:

~~~java
Enumeration<URL> resources =
        loader.getResources("config/app.properties");
while (resources.hasMoreElements()) {
    URL current = resources.nextElement();
    System.out.println(current);
}
~~~

**Đoạn minh họa** yêu cầu `loader` tồn tại và method cho phép `IOException`. Để debug, có thể in URL nguồn; nhưng trong log production cần tránh lộ đường dẫn nội bộ hoặc tokens nhúng trong URL.

Đối với cấu hình quan trọng:

1. Ưu tiên **một owner rõ ràng** cho config.
2. Kiểm tra duplicate resources trong build pipeline.
3. Nếu thiết kế overlay/merge, tự định nghĩa thứ tự ưu tiên và hợp đồng merge, không phó mặc lookup order.
4. Trong multi-tenant/plugin architecture, mỗi plugin có loader riêng thì việc gọi `getResource` từ **loader nào** là quyết định quan trọng.

## 11. Parent delegation và context class loader

Trong demo, loader được chọn là defining loader của `ResourceConfigDemo`. Trong ứng dụng thực tế còn có các khả năng:

- **Application class loader**: thấy classes/resources trong app classpath.
- **Plugin class loader**: có thể thấy resources của plugin và parent tùy chính sách; phù hợp khi file thuộc plugin.
- **Thread Context ClassLoader (TCCL)**: dùng bởi một số frameworks/framework SPI để phát hiện providers/resources của context hiện tại; không tự thay defining loader của class.
- **Custom loader**: có thể override `findResource`, `findResources` hoặc dùng URLClassLoader; phải kiểm tra delegation và resource lookup behavior.

Ví dụ minh họa:

~~~java
ClassLoader context =
        Thread.currentThread().getContextClassLoader();

if (context != null) {
    URL pluginConfig = context.getResource("config/plugin.properties");
}
~~~

**Đoạn code minh họa**: TCCL có thể phù hợp nếu caller/framework chủ động quản lý nó. Nhưng không nên dùng TCCL ngẫu nhiên khi file phải gắn cố định với một class/module; TCCL của thread pool hoặc container có thể trỏ tới loader khác, gây missing hoặc duplicate config.

Khi gọi `loader.getResourceAsStream`, API nhận **một resource name**, không nhận một `Class<?>` để “hợp nhất” namespaces. Loader được chọn vẫn quyết định phạm vi lookup.

## 12. Named modules (JPMS) có điểm khác classpath

Trong Java 9+ có named modules, các API resource chịu **encapsulation rules** ngoài đường dẫn đơn thuần. Theo Java 17 Javadoc:

- `ClassLoader.getResource`, `getResourceAsStream`, `getResources` với non-`.class` resources thuộc **packages của named modules** thường chỉ tìm được nếu package **opened unconditionally**; chỉ `opens p to q` có thể chưa đủ cho tìm kiếm kiểu ClassLoader generic.
- `Class.getResource` và `Class.getResourceAsStream` trên class thuộc named module tìm theo module sở hữu class và áp dụng module encapsulation rules; resource trong package không open cho caller module có thể không truy cập được.
- `Module.getResourceAsStream` có semantics gắn với module và caller, phù hợp khi cần resource của một module xác định.
- Resource ở path **không thuộc package** có thể chịu điều kiện khác với resource nằm trong một package module; không lấy classpath examples làm lời hứa cho mọi module.
- `exports` cho public Java API không đồng nghĩa `opens` cho deep reflection/resource encapsulation.

Ví dụ descriptor minh họa nếu module cố ý cho phép truy cập resource trong package `demo.config` bằng ClassLoader generic:

~~~java
module demo.app {
    opens demo.config;
}
~~~

**Đây là snippet mô tả cấu hình JPMS, không phải phần phải thêm vào demo classpath ở mục 5.** Phải có package tồn tại và module descriptor được biên dịch hợp lệ theo project cụ thể; không mở vô điều kiện packages chứa dữ liệu nhạy cảm chỉ để làm API lookup thuận tiện.

**Chủ động chọn cách tổ chức resources:** Config đặt ở path root không đại diện cho package Java, hoặc truy cập resource thông qua code API do module sở hữu, có thể đơn giản và rõ quyền hơn việc mở hàng loạt packages.

## 13. Maven và Gradle: chuẩn đóng gói resources

### 13.1. Maven

Cấu trúc quen thuộc:

~~~text
project/
├── pom.xml
└── src/
    └── main/
        ├── java/demo/ResourceConfigDemo.java
        └── resources/
            ├── config/app.properties
            └── demo/local-note.txt
~~~

Maven Resources Plugin mặc định copy `src/main/resources` vào output classes (thường `target/classes`) và công cụ đóng JAR lấy các entries đó. **File `src/main/resources/config/app.properties` sẽ thành `config/app.properties` trong JAR**, không phải `resources/config/app.properties`.

Bài này không yêu cầu chạy Maven; đây là đối chiếu layout nếu bạn chuyển ví dụ đã chạy sang project Maven.

### 13.2. Gradle

Với Java plugin thông thường:

~~~text
src/main/java/demo/ResourceConfigDemo.java
src/main/resources/config/app.properties
src/main/resources/demo/local-note.txt
~~~

Gradle xử lý resources trong build output (ví dụ `build/resources/main`) và các outputs cần thiết được đưa vào classpath/JAR theo configuration. Nếu có cấu hình source sets hoặc custom packaging, phải kiểm tra **artifact thực tế**, không chỉ dựa vào layout trên source tree.

### 13.3. Lệnh xác minh artifact

~~~bash
jar --list --file out/resource-demo.jar
~~~

Cho JAR ở bài tập mục 7. Khi dùng build tool, thay file path bằng artifact do build tạo. Một file cấu hình có trên disk nhưng **không nằm trong JAR** sẽ không tự xuất hiện qua resource lookup khi chỉ chạy JAR đã đóng gói.

Với executable/fat JAR framework-specific (ví dụ class files/resources trong `BOOT-INF/classes`), loader đặc thù có thể cung cấp URL schemes và cấu trúc package khác. **Đừng suy URL luôn là `jar:file:...!/config/...` trong mọi launcher.** API `getResourceAsStream` vẫn là abstraction được ưu tiên nếu framework loader hỗ trợ.

## 14. Lỗi thường gặp và cách chẩn đoán

| Hiện tượng | Nguyên nhân có thể | Kiểm tra/sửa |
| --- | --- | --- |
| `getResourceAsStream` trả null | Sai name hoặc resources chưa ở classpath/JAR | In tên lookup, kiểm tra build output và `jar --list` |
| Chạy IDE được, `java -jar` lỗi | IDE thêm `src/main/resources` vào classpath nhưng JAR thiếu entries | Kiểm tra cấu hình copy/build |
| Windows chạy sai | Dùng `\` trong resource name | Luôn dùng `/` |
| `Class.getResource("config/x")` không tìm | API này tìm tương đối với package class | Dùng `"/config/x"` hoặc ClassLoader root name |
| `ClassLoader.getResource("/config/x")` null | Sai slash đầu của ClassLoader lookup | Bỏ slash đầu |
| `FileNotFoundException` chỉ khi chạy JAR | Code giả định resource là physical File | Dùng InputStream |
| Java đọc tiếng Việt thành ký tự lạ | Dùng `Properties.load(InputStream)` với UTF-8 bytes | `load(Reader)` với UTF-8 |
| Config từ JAR khác được chọn | Trùng tên resources và lookup order | `getResources`, tránh trùng, define precedence |
| Local note trong package không tìm thấy | Copy sai `demo/local-note.txt` vào build root | Đặt đúng package-relative path |
| `Integer.parseInt` lỗi | Thiếu hoặc giá trị không phải số | Validate key/format với message rõ |
| Resource có tên đúng nhưng module không cho thấy | Named module encapsulation, package not opened | Kiểm tra module/Javadoc API, `opens` có kiểm soát |
| Plugin không đọc thấy config | Chọn sai ClassLoader/TCCL | Dùng defining/plugin loader đúng owner |
| `Resource URL` có protocol lạ | Custom/fat JAR loader cung cấp custom URL scheme | Đọc stream thay vì dựa vào File path |
| File tồn tại trên disk nhưng không thấy | Nó nằm ngoài classpath roots | Copy đóng gói hoặc dùng explicit filesystem API |

### 14.1. Chẩn đoán thứ tự phù hợp

1. **Đọc đúng message** và resource name. Phân biệt `null` với `IOException`/parser exception.
2. Xem lookup dùng **Class hay ClassLoader**, class nằm trong package nào.
3. Xem **classpath hoặc module path thực khi chạy**, không suy từ cửa sổ IDE.
4. Kiểm tra output folder `out/classes` hoặc build/classes/resources.
5. Kiểm tra JAR entries, chú ý resource ở **classpath root**.
6. Nếu nhiều JARs, gọi `getResources` để xem duplicate matches.
7. Nếu là named module, kiểm tra module ownership và encapsulation.
8. Nếu URL không thuộc `file`, tránh `File`/`Path` giả định.
9. Kiểm tra charset và dữ liệu có đúng format `Properties`.
10. Chạy từ thư mục working directory khác để xác nhận chương trình thực sự không phụ thuộc CWD sau khi đóng gói.

## 15. Tự thực hành mở rộng: cấu hình bên ngoài có quyền ưu tiên

Một bài tập thực tế là dùng mặc định từ `config/app.properties` **trong JAR**, rồi cho phép người vận hành cung cấp file bên ngoài:

~~~text
Built-in default (JAR)        app.name=Resource Demo
                              app.port=8080

Optional external override    app.port=9090

Effective config              app.name=Resource Demo
                              app.port=9090
~~~

Ví dụ API minh họa:

~~~java
Properties values = new Properties();
try (InputStream in = loader.getResourceAsStream(
        "config/app.properties")) {
    if (in == null) {
        throw new FileNotFoundException("Missing packaged defaults");
    }
    values.load(new InputStreamReader(
            in, StandardCharsets.UTF_8));
}

if (externalPath != null) {
    try (var reader = Files.newBufferedReader(
            externalPath, StandardCharsets.UTF_8)) {
        values.load(reader);
    }
}
~~~

**Đây là snippet, không phải file runnable độc lập**; `loader`/`externalPath` đã được xác định trước, cần imports, exception handling và validation phù hợp. `Properties.load` lần hai có thể ghi đè các keys cùng tên, nếu đó là precedence bạn lựa chọn.

Nên thiết kế:

- File bên ngoài được **chỉ rõ** qua CLI/ENV, không tự động tìm tùy tiện gần working directory.
- Thông báo rõ default file thiếu hay external override file không tồn tại.
- Giới hạn path được phép nếu người dùng không tin cậy có thể điều khiển đường dẫn.
- Không cho phép config key nguy hiểm chỉ vì tệp tồn tại; cần validate sau merge.
- Không in secrets/token values vào log.
- Phân biệt sửa external file trong runtime với **thay JAR artifact**, không cố ghi ngược vào classpath URL.

## 16. Checklist kiểm thử thực tế

- [ ] `src/demo/ResourceConfigDemo.java` compile với `javac --release 17`.
- [ ] `config/app.properties` được copy dưới **classpath root**, không thừa `resources/`.
- [ ] `demo/local-note.txt` nằm cùng package relative path với class.
- [ ] `java -cp out/classes demo.ResourceConfigDemo` in `protocol: file` và đúng keys/values.
- [ ] JAR chứa `config/app.properties` và `demo/local-note.txt`.
- [ ] `java -jar out/resource-demo.jar` in `protocol: jar` và đúng keys/values.
- [ ] Các streams được đóng với `try-with-resources`.
- [ ] Missing resources được báo rõ thay vì `NullPointerException`.
- [ ] Đọc Properties UTF-8 bằng `InputStreamReader` + `Properties.load(Reader)`.
- [ ] Không dùng `new File(url.getFile())` với một entry nằm trong JAR.
- [ ] Không phụ thuộc thứ tự trùng resources ngoài hợp đồng đã định nghĩa.
- [ ] Nếu có plugins, dùng đúng ClassLoader và đúng resource owner.
- [ ] Nếu dùng JPMS, kiểm tra named-module encapsulation riêng.
- [ ] Nếu có external config, validate thứ tự ưu tiên và chống rò rỉ secrets.

## 17. Câu hỏi tự kiểm tra

**1. Một resource là gì?** Dữ liệu được tìm bằng tên logic trong lookup scope của class loader/module, có thể nằm ở thư mục, JAR hoặc nguồn do loader hỗ trợ.

**2. `ClassLoader.getResourceAsStream("config/app.properties")` có cần file vật lý bên ngoài JAR không?** Không; nó có thể đọc entry bên trong JAR.

**3. Khác nhau giữa `MyClass.class.getResource("x.txt")` và `getResource("/x.txt")`?** Tên không slash đầu tương đối với package của class; slash đầu tính từ root.

**4. Có nên viết `loader.getResource("/config/app.properties")`?** Không theo quy tắc ClassLoader chuẩn; dùng `config/app.properties`.

**5. Vì sao resource chạy IDE được nhưng JAR không thấy?** IDE có thể thêm resource source dir vào classpath, còn JAR đóng gói thiếu file hoặc sai root.

**6. URL resource bên trong JAR thường có protocol gì?** Thường `jar` trong môi trường Java JAR chuẩn; không phụ thuộc vào điều này cho mọi custom launcher.

**7. Vì sao không lấy `new File(url.getFile())` để đọc mọi resource?** Entry trong JAR không phải file riêng trên OS filesystem; còn có URI encoding issues.

**8. `getResourceAsStream` trả gì nếu file thiếu?** `null` theo API; nên kiểm tra và báo lỗi rõ.

**9. `Properties.load(InputStream)` đọc UTF-8 giống `load(Reader UTF_8)` không?** Không. InputStream overload có quy tắc ISO-8859-1; Reader overload dùng characters đã giải mã.

**10. Vì sao `getResources` hữu ích?** Nó cho phép phát hiện nhiều resources cùng tên trong classpath/module lookup scope.

**11. Vì sao cần try-with-resources?** Đóng stream/reader kịp thời, tránh rò rỉ file/JAR handles và resources.

**12. Khác biệt classpath config và external config?** Classpath config là dữ liệu đóng gói cùng artifact; external config do hệ thống triển khai quản lý qua Path rõ ràng.

**13. `Class.getResource` có luôn giống `ClassLoader.getResource` trong named module không?** Không; named modules có quy tắc ownership và encapsulation riêng.

**14. File `src/main/resources/config/app.properties` trong Maven thường xuất hiện ở entry nào trong JAR?** `config/app.properties`.

**15. Khi nhận ClassLoader từ `String.class.getClassLoader()`, có thể null không?** Có. Null thường đại diện bootstrap loader.

## 18. Tham khảo chính thức

- Java SE 17 — `ClassLoader.getResource`, `getResources`, `getResourceAsStream`, module encapsulation: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html
- Java SE 17 — `Class.getResource` và `getResourceAsStream`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html
- Java SE 17 — `Module.getResourceAsStream`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Module.html
- Java SE 17 — `Properties.load(InputStream)` và `load(Reader)`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Properties.html
- Java SE 17 — `URL.openStream`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/URL.html
- Java SE 17 — `JarFile` (khi thực sự cần thao tác archive entries): https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/jar/JarFile.html
- Java SE 17 — `jar` command: https://docs.oracle.com/en/java/javase/17/docs/specs/man/jar.html
