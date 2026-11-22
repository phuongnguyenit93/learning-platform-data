# Resource là gì và quan hệ với classpath trong Java

## 1. Resource là gì?

Trong Java, **resource** là dữ liệu mà chương trình muốn đọc theo một **tên tài nguyên** (resource name), không phụ thuộc trực tiếp vào việc dữ liệu đang nằm trong một thư mục trên đĩa hay trong một tệp JAR. Resource thường là dữ liệu đi kèm ứng dụng hoặc thư viện:

- Tệp cấu hình mặc định: `config/app.properties`, `logback.xml`, `META-INF/services/...`.
- Mẫu văn bản, trang HTML, câu lệnh SQL, bản dịch: `templates/email.html`, `sql/schema.sql`, `messages_vi.properties`.
- Ảnh, biểu tượng, chứng chỉ công khai, dữ liệu thử nghiệm, tệp JSON hoặc dữ liệu nhị phân.
- Ngay cả file `.class` cũng có thể được tìm như một resource, mặc dù **tìm bytes tài nguyên** và **định nghĩa một kiểu Java** là hai thao tác khác nhau.

Ví dụ, ứng dụng muốn đọc `demo/config/message.txt`. Khi chạy ở môi trường phát triển, bytes có thể nằm tại `resources/demo/config/message.txt`. Khi đóng gói, chúng có thể nằm **bên trong JAR** với entry name `demo/config/message.txt`. Mã Java dùng tên resource thích hợp có thể đọc cả hai tình huống mà không cần tự giả định đường dẫn file vật lý.

**Điểm cốt lõi:** *Classpath* cung cấp **các gốc tìm kiếm (search roots)** cho cả class và resource trong kiểu chạy classpath truyền thống. *Resource name* là đường dẫn **tương đối với gốc đó**, thường phân tách bằng dấu `/`. Một resource **không cần là Java class**, không có constructor, và không tự trở thành đối tượng `Class<?>` chỉ vì xuất hiện trên classpath.

Bài này giải thích chính xác tên resource, cấu trúc classpath, Java API tìm resource, khác biệt giữa `Class` và `ClassLoader`, việc chạy trong IDE/JAR, xử lý thiếu tài nguyên, nhiều tài nguyên cùng tên và lưu ý với JPMS từ Java 9.

## 2. Classpath là gì?

**Classpath** (đường tìm lớp) là tập các vị trí mà công cụ Java có thể sử dụng để tìm class và resource trong cách chạy dựa trên classpath. Khi truyền `-cp` hoặc `--class-path` cho lệnh `java`, bạn chỉ định những thành phần như:

- **Thư mục gốc** chứa các thư mục package và các file đã biên dịch.
- **Tệp JAR** chứa các class file và resource entries.
- Nhiều thư mục/JAR được liệt kê theo cú pháp phân tách thích hợp với hệ điều hành.

Ví dụ trên Windows:

~~~powershell
java -cp "out;resources;lib/util.jar" demo.Main
~~~

Tương đương về ý tưởng trên Linux/macOS:

~~~bash
java -cp "out:resources:lib/util.jar" demo.Main
~~~

Dấu phân tách classpath là `;` trên Windows và `:` trên Linux/macOS. Dấu `/` nằm **bên trong tên resource** là một quy tắc khác: `demo/config/message.txt` có cùng tên logic trên các hệ điều hành.

Khi `resources` là một **classpath root**, resource `demo/config/message.txt` ứng với:

~~~text
resources/
└── demo/
    └── config/
        └── message.txt
~~~

Khi `out` là classpath root, class có binary name `demo.Main` ứng với:

~~~text
out/
└── demo/
    └── Main.class
~~~

**Không truyền nguyên một đường dẫn file resource như thể đó là classpath root.** Nếu đưa `resources/demo/config/message.txt` vào `-cp` thay vì thư mục `resources`, cơ chế tìm kiếm thông thường sẽ không hiểu đó là một entry cung cấp đúng resource name `demo/config/message.txt`.

Classpath dùng khi **biên dịch** và khi **chạy** có thể khác nhau. `javac -cp` giúp trình biên dịch phân giải các kiểu cần thiết; `java -cp` quyết định đường tìm khi khởi chạy runtime. Một chương trình compile thành công vẫn có thể không đọc được resource nếu gói chạy bỏ quên thư mục resource/JAR.

## 3. Mối quan hệ giữa class và resource trên classpath

Một class và một resource bất kỳ đều có thể được cung cấp từ cùng thư mục/JAR:

~~~text
project/
├── src/
│   └── demo/
│       └── Main.java
├── resources/
│   ├── app.properties
│   └── demo/
│       └── config/
│           └── message.txt
└── out/
    └── demo/
        └── Main.class
~~~

Nếu chạy với `out` và `resources` cùng nằm trên classpath:

- `demo.Main` là **binary name của class**; JVM/class loader tìm biểu diễn class thích hợp, ví dụ entry `demo/Main.class`.
- `demo/config/message.txt` là **resource name**, trỏ đến bytes tùy ý không cần cú pháp Java.
- `app.properties` là resource đặt **ở classpath root**, không thuộc package `demo`.
- `Main.class` có thể được xem như resource bytes bằng tên `demo/Main.class`, nhưng đọc stream không tương đương `ClassLoader.defineClass` và không làm code trong class chạy.

Về phía Java, người viết chương trình thường không cần biết resource nằm trong `file:` URL hay `jar:` URL. Một resource có thể ở trong JAR, trong mô-đun runtime hoặc được custom loader cung cấp bằng cơ chế khác.

**Không nên hiểu classpath là một chuỗi đường dẫn filesystem duy nhất.** Đây là cơ chế tìm kiếm nhiều vị trí, đồng thời những class loader riêng có thể sở hữu phạm vi tìm kiếm khác nhau. Trong Java 9+, named modules còn có quy tắc resource riêng, được trình bày ở phần sau.

## 4. Resource name khác filesystem path

Resource name có đặc trưng:

- Dùng **dấu `/`** để ngăn các thành phần, như `demo/config/message.txt`.
- Thường được hiểu **tương đối với classpath root hoặc phạm vi tìm của class loader**.
- Có phân biệt chữ hoa/chữ thường tùy nguồn đóng gói và môi trường; nên viết đúng tên và không dựa vào sự khoan dung của filesystem.
- Không được giả định là đường dẫn tuyệt đối tới file ngoài đĩa.
- Không tự động lấy `user.dir` làm gốc nếu API được gọi là `ClassLoader.getResource`.

Đối chiếu ba cách truy cập khác nhau:

| Cách viết | Ý nghĩa |
| --- | --- |
| `Path.of("config/app.properties")` | Đường dẫn file tương đối theo working directory của tiến trình |
| `ClassLoader.getSystemResource("config/app.properties")` | Tên resource đối với system class loader |
| `MyClass.class.getResource("config/app.properties")` | Resource **tương đối package của MyClass** theo quy tắc của `Class` |

Cả ba có thể đọc được các bytes tương tự nếu bạn cố ý bố trí thư mục thích hợp, nhưng **không có hợp đồng rằng chúng trỏ cùng nơi**.

Ví dụ working directory là `C:\work\project`, còn resource nằm trong `app.jar`. `Path.of("config/app.properties")` sẽ tra một file trên đĩa liên hệ working directory; nó **không tự chui vào JAR** để đọc entry `config/app.properties`. Ngược lại, `ClassLoader.getResourceAsStream` có thể đọc entry bên trong JAR nếu JAR thuộc miền tìm resource.

## 5. Ba API quan trọng: URL, InputStream và liệt kê

Các phương thức thường dùng:

| API | Trả về | Khi nên dùng |
| --- | --- | --- |
| `ClassLoader.getResource(String)` | `URL` hoặc `null` | Cần địa chỉ logic của một resource, hoặc mở stream từ URL |
| `ClassLoader.getResourceAsStream(String)` | `InputStream` hoặc `null` | Muốn đọc bytes trực tiếp, kể cả khi resource ở JAR |
| `ClassLoader.getResources(String)` | `Enumeration<URL>` | Muốn tìm **tất cả** resource trùng tên có thể nhìn thấy |
| `ClassLoader.resources(String)` | `Stream<URL>` | API Java 9+ để stream nhiều resource |
| `ClassLoader.getSystemResource(String)` | `URL` hoặc `null` | Tìm qua **system class loader** |
| `Class.getResource(String)` | `URL` hoặc `null` | Tìm theo lớp tham chiếu; hỗ trợ tên tương đối package |
| `Class.getResourceAsStream(String)` | `InputStream` hoặc `null` | Đọc bytes theo lớp tham chiếu, hỗ trợ quy tắc package |

`URL` chỉ địa điểm hoặc khả năng truy cập một resource; nó không đảm bảo là file local. `InputStream` cung cấp bytes và cần đóng bằng `try-with-resources`. Khi `getResourceAsStream` trả `null`, nguyên nhân có thể là tài nguyên không tìm thấy, quyền truy cập/resource encapsulation, hoặc cách đóng gói sai.

**Ưu tiên mở stream để đọc nội dung**, thay vì cố biến mọi URL thành `File`. Đối với `jar:file:...!/entry`, phép chuyển `Path.of(url.toURI())` theo filesystem mặc định thường không hoạt động như với URL `file:`.

## 6. Quy tắc đặt tên: Class.getResource và ClassLoader.getResource

Đây là phần dễ gây lỗi nhất.

Giả sử class đang thực thi có package `demo`:

~~~java
package demo;

public class Reader {
}
~~~

Và file resource đặt ở vị trí logic:

~~~text
classpath root/
└── demo/
    └── config/
        └── message.txt
~~~

Các lời gọi tương ứng:

| Lời gọi | Tên resource logic sau khi áp dụng quy tắc | Kỳ vọng |
| --- | --- | --- |
| `Reader.class.getResource("config/message.txt")` | `demo/config/message.txt` | Tìm được |
| `Reader.class.getResource("/demo/config/message.txt")` | `demo/config/message.txt` | Tìm được |
| `Reader.class.getResource("message.txt")` | `demo/message.txt` | Không có nếu resource chỉ ở `demo/config/` |
| `Reader.class.getClassLoader().getResource("demo/config/message.txt")` | `demo/config/message.txt` | Tìm được |
| `Reader.class.getClassLoader().getResource("config/message.txt")` | `config/message.txt` | Không có trong bố trí này |
| `ClassLoader.getSystemResource("demo/config/message.txt")` | `demo/config/message.txt` | Tìm được trong cách chạy chuẩn nếu đúng trên system classpath |

**Điểm khác biệt:**

- `Class.getResource("relative/name")`: nếu tên **không bắt đầu bằng `/`**, Java tự thêm phần package của class đó (`demo/` trong ví dụ).
- `Class.getResource("/absolute/name")`: nếu tên **bắt đầu bằng `/`**, API `Class` bỏ dấu `/` đầu và dùng tên **tính từ gốc**.
- `ClassLoader.getResource("name")`: tên đã được coi là tính từ **gốc tìm của loader**, nên thông thường **không đặt dấu `/` đầu**. Truyền `"/demo/config/message.txt"` vào `ClassLoader.getResource` không phải cách gọi chuẩn tương đương với `Class.getResource("/demo/config/message.txt")`.
- Với một `Class` thuộc **named module**, `Class.getResource` tìm theo module của class, ngoài quy tắc package; không thể hoàn toàn quy nó về việc gọi system class loader.

Nên chọn một kiểu tìm nhất quán: với resource đi theo class/thư viện, `MyClass.class.getResourceAsStream(...)` thường thích hợp; với một loader cụ thể, `loader.getResourceAsStream("absolute/from/loader/root")` thích hợp.

## 7. Ví dụ Java 17+ chạy được: dùng resource ở thư mục classpath

Mục tiêu là chạy **cùng code** khi resource nằm trong thư mục `resources` hoặc khi cả code và resource được đóng trong JAR. Không sử dụng framework hoặc thư viện ngoài JDK.

### 7.1. Cấu trúc dự án thực hành

Tạo đúng các file sau:

~~~text
resource-lab/
├── src/
│   └── demo/
│       └── ResourceExample.java
└── resources/
    ├── app.properties
    └── demo/
        └── config/
            └── message.txt
~~~

Nội dung **resources/demo/config/message.txt** (một dòng; cuối file có newline hay không đều được):

~~~text
Hello from classpath!
~~~

Nội dung **resources/app.properties**:

~~~properties
mode=demo
~~~

### 7.2. File Java đầy đủ

File **src/demo/ResourceExample.java**:

~~~java
package demo;

import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import java.net.URL;

public class ResourceExample {
    private static String read(String resourceName) throws IOException {
        try (InputStream input =
                     ResourceExample.class.getResourceAsStream(resourceName)) {
            if (input == null) {
                throw new IOException("Missing resource: " + resourceName);
            }
            return new String(input.readAllBytes(), StandardCharsets.UTF_8).trim();
        }
    }

    public static void main(String[] args) throws IOException {
        ClassLoader loader = ResourceExample.class.getClassLoader();

        URL relative = ResourceExample.class.getResource(
                "config/message.txt");
        URL absolute = ResourceExample.class.getResource(
                "/demo/config/message.txt");
        URL byLoader = loader.getResource(
                "demo/config/message.txt");

        System.out.println("relative: " + (relative != null));
        System.out.println("absolute: " + (absolute != null));
        System.out.println("by loader: " + (byLoader != null));

        System.out.println("message: " +
                read("/demo/config/message.txt"));
        System.out.println("properties: " +
                read("/app.properties"));
    }
}
~~~

Chương trình có `package demo;` và cần tên file đúng `ResourceExample.java`. Nó lấy ba URL nhưng **không in chính URL**, vì địa chỉ vật lý thay đổi giữa máy chạy và giữa thư mục/JAR. Hàm `read` dùng `try-with-resources` để stream luôn được đóng, kiểm tra `null` để báo thiếu resource rõ ràng, giải mã UTF-8 tường minh và bỏ whitespace ở đầu/cuối thông qua `trim()` để stdout nhất quán khi file có hoặc không có newline cuối.

### 7.3. Biên dịch và chạy trên Windows (PowerShell)

Đứng tại thư mục `resource-lab`:

~~~powershell
javac --release 17 -d out src/demo/ResourceExample.java
java -cp "out;resources" demo.ResourceExample
~~~

### 7.4. Biên dịch và chạy trên Linux/macOS

~~~bash
javac --release 17 -d out src/demo/ResourceExample.java
java -cp "out:resources" demo.ResourceExample
~~~

### 7.5. Stdout chính xác

Cả hai cách chạy trên, nếu cây thư mục và nội dung resource đúng, đều in:

~~~text
relative: true
absolute: true
by loader: true
message: Hello from classpath!
properties: mode=demo
~~~

**Giải thích theo dòng:**

1. `relative: true`: `ResourceExample.class.getResource("config/message.txt")` thêm tiền tố package `demo/`, nên tìm `demo/config/message.txt`.
2. `absolute: true`: `Class.getResource("/demo/config/message.txt")` bỏ slash đầu và tìm từ gốc.
3. `by loader: true`: loader nhận tên đã tính từ gốc `demo/config/message.txt`.
4. `message: ...`: `getResourceAsStream` đọc bytes của file message qua Class, không đòi một `File` trên đĩa.
5. `properties: ...`: tên `/app.properties` là resource ở gốc, không phải `demo/app.properties`.

Như vậy, resource không phải một class Java; đây là dữ liệu dạng văn bản, cùng được tìm qua cơ chế classpath.

## 8. Chạy lại ví dụ từ JAR

Tại thư mục `resource-lab`, sau khi đã compile tạo `out/demo/ResourceExample.class`, đóng gói cả class và resource vào JAR bằng công cụ JDK:

~~~bash
jar --create --file resource-example.jar -C out . -C resources .
~~~

Lệnh `jar` lấy nội dung thư mục `out` và `resources` làm các entry **tính từ gốc JAR**. Có thể kiểm tra:

~~~bash
jar --list --file resource-example.jar
~~~

Những entry quan trọng phải có:

~~~text
demo/ResourceExample.class
demo/config/message.txt
app.properties
~~~

JAR có thể chứa thêm manifest và entry thư mục; không cần so chính xác mọi dòng listing. Chạy chỉ với JAR trên classpath:

~~~bash
java -cp resource-example.jar demo.ResourceExample
~~~

**Stdout vẫn như mục 7.5**, vì cùng các resource names còn tồn tại tại gốc JAR:

~~~text
relative: true
absolute: true
by loader: true
message: Hello from classpath!
properties: mode=demo
~~~

Sự khác biệt nằm ở địa chỉ resource do URL trỏ tới: trong lúc phát triển nó có thể có dạng `file:...`, còn trong JAR thường là `jar:file:...!/demo/config/message.txt`. Code mở `InputStream` có thể tiếp tục hoạt động trong cả hai cách đóng gói.

**Không thay stream bằng `new File(...)` hoặc `Path.of(url.toURI())` một cách máy móc** chỉ vì ví dụ chạy được trên file URL. Đối với JAR, resource entry không phải một đường dẫn file thông thường trên filesystem mặc định.

## 9. Khi nào dùng Properties, Reader và InputStream?

Nếu resource là dữ liệu nhị phân như PNG hoặc bytecode, đọc bytes qua `InputStream`. Nếu là văn bản, cần chọn charset rõ ràng; Java 17 có thể dùng:

~~~java
try (InputStream input =
             MyClass.class.getResourceAsStream("/data/note.txt")) {
    if (input == null) {
        throw new java.io.FileNotFoundException("data/note.txt");
    }
    String content = new String(
            input.readAllBytes(),
            java.nio.charset.StandardCharsets.UTF_8
    );
}
~~~

**Đây là đoạn minh họa đặt trong một phương thức**, giả sử `MyClass` và resource tồn tại.

Với resource `.properties`, có thể dùng `java.util.Properties`:

~~~java
java.util.Properties props = new java.util.Properties();
try (InputStream input =
             MyClass.class.getResourceAsStream("/app.properties")) {
    if (input == null) {
        throw new java.io.FileNotFoundException("app.properties");
    }
    props.load(input);
}
String mode = props.getProperty("mode");
~~~

Đây cũng là đoạn minh họa trong phương thức. Lưu ý `Properties.load(InputStream)` sử dụng quy tắc encoding của định dạng properties truyền thống (ISO-8859-1, Unicode escapes), **không tự giải mã mọi tệp UTF-8 theo cách giống `new String(bytes, UTF_8)`**. Nếu muốn dùng UTF-8 cho file properties theo chủ đích, cung cấp một `Reader` với charset tương ứng qua `Properties.load(Reader)`.

**Không ghi nội dung runtime vào resource bên trong JAR.** Resources đóng gói chủ yếu là dữ liệu triển khai đọc được; cấu hình cần thay đổi thường thuộc file, volume, biến môi trường hoặc dịch vụ cấu hình ngoài artifact.

## 10. Parent delegation và vùng tìm kiếm resource

Đối với `ClassLoader.getResource(name)`, cách triển khai mặc định tìm ở **parent class loader trước**, rồi tìm resource mà loader hiện tại cung cấp qua `findResource`. Điều này tương tự ý tưởng parent-first của class loading, nhưng không phải mọi custom loader nhất thiết dùng đúng chiến lược đó.

Ví dụ:

~~~text
           ParentLoader
            ├── config/app.properties   [bản parent]
            |
            v
           ChildLoader
            └── config/app.properties   [bản child]
~~~

Nếu loader con dùng `getResource("config/app.properties")` theo parent-first mặc định, resource của **parent** có thể là kết quả đầu tiên. Khi có nhiều resource trùng tên, kết quả còn phụ thuộc cấu hình search path, custom loader và named modules.

Một ứng dụng plugin đôi khi cần tìm resource của chính plugin thay vì resource của host. Khi đó phải chọn loader/phạm vi lookup đúng: loader của class plugin, loader theo hợp đồng của framework hoặc **Thread Context ClassLoader** khi API cụ thể yêu cầu.

Không mặc định `ClassLoader.getSystemResource(...)` tìm được mọi resource mà một plugin hoặc application server có thể truy cập. System class loader và một custom plugin loader có thể sở hữu miền tìm khác nhau.

## 11. Nhiều resource trùng tên: getResource so với getResources

Khi classpath chứa hai JAR có cùng entry `META-INF/services/com.example.Service`, gọi:

~~~java
ClassLoader loader = Thread.currentThread().getContextClassLoader();

java.net.URL first = loader.getResource(
        "META-INF/services/com.example.Service");
java.util.Enumeration<java.net.URL> all = loader.getResources(
        "META-INF/services/com.example.Service");
~~~

**Đoạn minh họa**: cần có loader, resource và môi trường thích hợp; `getResources` khai báo `throws IOException` nên code phải đặt trong phương thức xử lý ngoại lệ này.

Ý nghĩa:

- `getResource` tìm **một URL**, thường là resource đầu tiên theo chính sách tìm kiếm của loader.
- `getResources` trả nhiều URL mà loader nhìn thấy. Trong Java 9+, `loader.resources(name)` cung cấp `Stream<URL>` với ý tưởng tương tự.
- Nhiều JAR cùng cung cấp một tên resource là tình huống hợp lệ; thường gặp ở Java Service Provider Interface (SPI).
- Không dựa vào **thứ tự của các URL** như API nghiệp vụ khi Java/JDK không bảo đảm thứ tự ổn định; ở named modules, thứ tự tìm các module có thể đặc biệt khó đoán.
- Đừng chỉ lấy resource đầu tiên khi công việc của bạn thực sự yêu cầu hợp nhất nhiều providers hoặc nhiều tệp cấu hình.

Để quan sát các URL thay vì đoán đường dẫn:

~~~java
while (all.hasMoreElements()) {
    System.out.println(all.nextElement());
}
~~~

Đây là đoạn tiếp của mẫu ở trên; URL có thể có scheme và vị trí khác nhau giữa các môi trường, nên không công bố một stdout cố định.

## 12. Resource và ClassLoader không đồng nghĩa nạp Class

Xét hai API:

~~~java
Class<?> type = loader.loadClass("demo.ResourceExample");
java.net.URL url = loader.getResource("demo/ResourceExample.class");
~~~

**Đoạn minh họa**, giả sử biến `loader` hợp lệ và tên class/resource có mặt.

- `loadClass` được thiết kế để lấy một **Class runtime** từ tên nhị phân. JVM thực hiện các quy tắc loading/linking liên quan.
- `getResource` được thiết kế để tìm **dữ liệu** bằng tên đường dẫn; nó trả URL hoặc null.
- Việc đọc bytes từ `getResourceAsStream("demo/ResourceExample.class")` không tự thực hiện `defineClass`.
- Class loading có thể dùng bytes từ classpath/JAR, nhưng cách tìm/định nghĩa Class không bắt buộc là phép gọi `getResource` đơn giản từ Java source.
- Class được load qua custom loader có thể không công bố bytes gốc dưới dạng resource URL; ngược lại, một resource `.class` tìm được không nhất thiết có thể định nghĩa thành class hợp lệ bằng tên bạn tự chọn.

Đặc biệt, **class binary name** dùng dấu chấm giữa package, ví dụ `demo.ResourceExample`; **resource path** của file class dùng slash và đuôi `.class`, ví dụ `demo/ResourceExample.class`. Với lớp thành viên `Outer.Inner`, binary name thường chứa `$`, và resource path dạng `pkg/Outer$Inner.class`.

## 13. Resource khác gì tài nguyên filesystem bên ngoài ứng dụng?

Chọn resource đóng gói khi dữ liệu **đi cùng phiên bản ứng dụng**: template email mặc định, icons, SQL migration scripts (tùy framework), mẫu dữ liệu hoặc cấu hình mẫu. Chọn filesystem/database/config service khi dữ liệu cần **thay đổi mà không rebuild artifact** hoặc cần quyền ghi.

| Trường hợp | Cơ chế phù hợp |
| --- | --- |
| Đọc template đóng cùng JAR | `getResourceAsStream` |
| Đọc ảnh đi kèm thư viện | `Class.getResource` hoặc stream |
| Đọc file cấu hình do người vận hành đặt ngoài JAR | `Path` / `Files` hoặc API cấu hình của framework |
| Ghi logs, uploads, cache | Filesystem/volume/object storage, không ghi vào JAR resource |
| Tìm class theo binary name | `ClassLoader.loadClass`, không coi resource bytes là Class |
| Đọc tài nguyên từ plugin riêng | Loader của plugin hoặc cơ chế do framework chỉ định |
| Gộp nhiều SPI descriptors cùng tên | `getResources` hoặc API `ServiceLoader` phù hợp |

Một chương trình có thể sử dụng **cả hai**: resource mặc định trong JAR làm fallback, rồi đọc cấu hình ngoài đĩa để ghi đè. Cần quy định thứ tự ưu tiên rõ và không dựa vào thứ tự ngẫu nhiên của resource trùng tên.

## 14. Khác biệt quan trọng với JPMS (Java 9+)

Từ Java 9, Java Platform Module System (JPMS) giới thiệu **named module**. Lúc này không phải mọi tài nguyên đều được tìm bằng cách “duyệt classpath” thông thường.

- Classpath truyền thống đưa class vào **unnamed module** tương ứng loader.
- Module path chứa named modules có cơ chế resolution, class loading và encapsulation riêng.
- Với `Class.getResource` / `Class.getResourceAsStream`, nếu class thuộc named module, việc tìm resource có liên hệ **module của class đó**, và quyền truy cập được kiểm soát theo quy tắc `Module.getResourceAsStream`.
- Với `ClassLoader.getResource` hoặc `getResourceAsStream`, **non-.class resource trong một package của named module thường chỉ có thể được tìm khi package đó được opened unconditionally** (khai báo `opens p;` không giới hạn đích), theo Javadoc Java 17. Đây là ràng buộc nghiêm hơn một số trường hợp truy cập `Class.getResource` từ trong chính module hoặc module đã được cấp quyền mở.
- Với resource nằm ngoài một package của module, quy tắc encapsulation dành cho package không áp dụng theo cùng cách. Dù vậy cách đóng gói/cung cấp resource vẫn phải đúng.
- Một resource trong named module có thể không tìm được qua API dùng system class loader dù nhìn thấy entry bên trong modular JAR; hãy cân nhắc dùng `MyClass.class.getResourceAsStream(...)` trong ngữ cảnh module thích hợp.

Ví dụ declaration:

~~~java
module com.example.reader {
    // Khi cần mở package demo.assets không điều kiện:
    opens demo.assets;
}
~~~

Đây là **minh họa module descriptor**, không phải file hoạt động độc lập; package và resource thực tế cần tồn tại. Chỉ thêm `opens` khi hợp đồng thiết kế yêu cầu, vì mở package ảnh hưởng đến phạm vi truy cập phản chiếu/runtime.

**Không nhầm `exports` và `opens`:** `exports` phục vụ khả năng truy cập các public types từ module khác; `opens` liên quan deep reflection và các quy tắc resource encapsulation. Chỉ `exports` một package không nhất thiết làm non-.class resource trong đó hiển thị qua `ClassLoader.getResource`.

## 15. Resources trong Gradle, Maven và IDE

Trong dự án Java chuẩn, cấu trúc thường là:

~~~text
src/
├── main/
│   ├── java/
│   │   └── demo/
│   │       └── App.java
│   └── resources/
│       ├── app.properties
│       └── demo/
│           └── config/
│               └── message.txt
└── test/
    ├── java/
    └── resources/
        └── test-data.json
~~~

**Với Gradle Java plugin** và **Maven convention** thông thường, `src/main/resources` là thư mục đầu vào; build tool sao chép các tài nguyên vào output phù hợp để chúng hiện diện trên runtime classpath hoặc bên trong JAR.

- Gradle Java plugin thường copy resource đến `build/resources/main`; classes output thường nằm trong `build/classes/java/main`. Khi đóng JAR, tài nguyên được đưa vào các entry tương ứng.
- Maven thông thường copy resource đến `target/classes`, cạnh compiled classes từ `src/main/java`.
- `src/test/resources` phục vụ test classpath; không được giả định tự đi vào production JAR.
- IDE có thể thêm resource directories vào classpath tự động; chạy lệnh `java` thủ công đòi bạn cung cấp đúng path hoặc dùng JAR build output. Đây là lý do “chạy trong IDE được nhưng chạy JAR không thấy resource” xảy ra thường xuyên.

Với Spring Boot executable JAR có cấu trúc đóng gói riêng, resource vẫn có thể được class loader của runtime tìm theo đúng tên, nhưng entry bên trong có thể nằm tại một tầng như `BOOT-INF/classes/...`. Không tự chuyển đường dẫn resource thành filesystem path dựa vào bố cục bên trong JAR của một framework.

Nên kiểm tra artifact thật bằng:

~~~bash
jar --list --file application.jar
~~~

Lệnh áp dụng khi `application.jar` là file JAR bạn đang kiểm tra. Kiểm tra tên resource **tương đối với gốc tìm kiếm của môi trường chạy**, không chỉ nhìn file có tồn tại đâu đó trong mã nguồn.

## 16. Xử lý khi getResourceAsStream trả null

Một lỗi phổ biến là:

~~~java
try (InputStream input =
             MyClass.class.getResourceAsStream("settings.json")) {
    String text = new String(input.readAllBytes());
}
~~~

Đây là **mã minh họa lỗi**, giả sử có `MyClass`. Nếu resource không tìm thấy, `input == null` và `readAllBytes()` gây `NullPointerException`; thông báo không chỉ rõ tên resource.

Mẫu xử lý tốt hơn:

~~~java
String name = "/config/settings.json";
try (InputStream input = MyClass.class.getResourceAsStream(name)) {
    if (input == null) {
        throw new java.io.FileNotFoundException(
                "Classpath resource missing: " + name);
    }
    byte[] bytes = input.readAllBytes();
}
~~~

Đây là **đoạn minh họa trong phương thức**. Trong sản phẩm thực tế, có thể cần kèm tên module, loader hoặc danh sách classpath roots phục vụ debug.

Nếu không tìm thấy resource, kiểm tra theo thứ tự:

1. **Đúng tên, đúng chữ hoa/thường, đúng dấu slash?** Ví dụ `app.properties` khác `config/app.properties`.
2. **Dùng Class hay ClassLoader?** `Class.getResource("x")` tìm tương đối package; `ClassLoader.getResource("x")` tìm từ gốc loader.
3. **Classpath root có đúng không?** `resources` hay `out` có nằm trong classpath của quá trình chạy thực tế?
4. **File có nằm trong JAR/output không?** Dùng `jar --list` và xem thư mục output của build.
5. **Đang chạy trong module hay plugin riêng?** Có thể resource nằm trong module chưa opened, hoặc loader khác có phạm vi tra cứu riêng.
6. **Có nhiều resource trùng tên không?** Kiểm tra `getResources` để biết có nhiều nơi cung cấp dữ liệu.
7. **Có cố biến JAR URL thành File không?** Đọc bằng stream hoặc API filesystem JAR/ZIP thích hợp.
8. **IDE và runtime dùng cùng cấu hình không?** So sánh arguments, working directory, classpath/module path, output artifact.

Nếu API yêu cầu `InputStream`, đóng stream bằng `try-with-resources` và xử lý `IOException`. Nếu chỉ cần biết tồn tại, `getResource` trả URL hoặc null, nhưng kết quả có thể phụ thuộc quyền truy cập và module encapsulation.

## 17. Các lỗi hiểu sai thường gặp

| Hiểu sai | Điều đúng |
| --- | --- |
| “Resource là Java class” | Resource là dữ liệu có tên; `.class` chỉ là một loại file có thể được tìm |
| “Classpath là thư mục chứa source code” | Runtime classpath chứa các **gốc output/JAR** cần thiết, không tự hiểu `src/main/java` hay `src/main/resources` |
| “Tên resource là full OS path” | Tên thường là đường dẫn tương đối với gốc tìm kiếm bằng dấu `/` |
| “`Class.getResource("x")` và `ClassLoader.getResource("x")` luôn giống nhau” | Cái thứ nhất áp dụng package-relative khi không có `/` đầu |
| “Phải thêm `/` vào mọi resource name” | `ClassLoader.getResource` thường dùng tên từ gốc **không có slash đầu** |
| “Resource tìm được là file local” | Nó có thể ở JAR, module runtime hoặc provider khác |
| “`getResourceAsStream` luôn trả stream” | Có thể trả `null` nếu không tìm thấy/không được phép truy cập |
| “Một resource name luôn là một URL duy nhất” | Nhiều classpath entries có thể chứa cùng tên; `getResources` tìm nhiều |
| “`new File(url.getPath())` luôn hợp lệ” | Sai với JAR URL và resource không nằm trên filesystem thông thường |
| “System loader luôn tìm được resource của plugin” | Plugin loader/TCCL có phạm vi riêng |
| “`exports` đủ cho mọi non-.class resource trong JPMS” | Một số resource lookup chịu quy tắc `opens`, đặc biệt qua `ClassLoader` |
| “File có trong IDE là chắc chắn có trong packaged JAR” | Cần kiểm tra build output/artifact thật |

## 18. Bài tập tự kiểm tra

**1. Resource `icons/logo.png` nằm trong `src/main/resources/icons/logo.png`. Khi build tool đưa nội dung vào classpath root, tên để gọi `loader.getResource` là gì?**  
`icons/logo.png`, không bao gồm `src/main/resources`.

**2. Class thuộc package `demo`. `Demo.class.getResource("data.txt")` tìm tên nào?**  
`demo/data.txt`. Muốn từ gốc, dùng `Demo.class.getResource("/data.txt")`.

**3. Vì sao `loader.getResource("/demo/data.txt")` có thể trả null?**  
Vì API ClassLoader dùng tên từ gốc **không cần slash đầu**. Dùng `demo/data.txt`.

**4. Tại sao mã chạy trong IDE đọc được resource nhưng `java -cp out ...` không thấy?**  
Có thể `resources` không có trên runtime classpath; IDE tự bổ sung resource directory, còn lệnh thủ công chỉ đưa `out`.

**5. Tại sao không dùng `Path.of(url.toURI())` cho mọi resource?**  
Resource URL có thể dùng scheme `jar:`, `jrt:` hoặc provider khác, không tương đương file của filesystem mặc định.

**6. Có hai JAR chứa `META-INF/services/...` cùng tên. Nên dùng API nào để xem tất cả?**  
`ClassLoader.getResources(name)` hoặc `ClassLoader.resources(name)` (Java 9+).

**7. `ClassLoader.loadClass("demo.Main")` và `getResource("demo/Main.class")` có trả cùng kiểu dữ liệu không?**  
Không. Một API trả `Class<?>`, API kia trả `URL` tới bytes tài nguyên.

**8. File trong named module có thể bị che dù tồn tại vật lý không?**  
Có. Resource encapsulation và quy tắc `opens`/module ảnh hưởng khả năng tìm, nhất là qua ClassLoader API.

**9. File `app.properties` phải được sửa sau deploy; có nên ghi trở lại trong JAR không?**  
Không nên. Chọn cấu hình ngoài artifact hoặc nguồn lưu trữ dành cho dữ liệu có quyền ghi.

**10. Khi resource stream null, có nên tự động chọn một resource cùng tên ở JAR bất kỳ không?**  
Không. Cần làm rõ loader, module, classpath và chính sách ưu tiên, tránh phụ thuộc vào resource vô tình hiện diện.

## 19. Tài liệu chuẩn

- **Java SE 17, `ClassLoader` API** — getResource, getResources, getResourceAsStream, resource names, delegation và module visibility: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html
- **Java SE 17, `Class` API** — getResource/getResourceAsStream, quy tắc tên tương đối package và tuyệt đối: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html
- **Java SE 17, `Module` API** — module resource encapsulation và getResourceAsStream: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Module.html
- **Java 17, `java` command** — runtime classpath và tùy chọn -cp: https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html
- **Java 17, `jar` command** — tạo và liệt kê nội dung JAR: https://docs.oracle.com/en/java/javase/17/docs/specs/man/jar.html
