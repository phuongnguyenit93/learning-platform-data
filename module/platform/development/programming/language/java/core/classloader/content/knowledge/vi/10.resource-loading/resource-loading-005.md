# getResources, resources và liệt kê nhiều tài nguyên cùng tên

## 1. Khi nào cần liệt kê thay vì tìm một resource?

Một Java application có thể dùng nhiều JAR. Hai hoặc nhiều JAR hoàn toàn có thể chứa **resource cùng tên**, chẳng hạn:

~~~text
parent.jar
└── demo/resource/lesson-source.txt     → PARENT

a.jar
└── demo/resource/lesson-source.txt     → A

b.jar
└── demo/resource/lesson-source.txt     → B
~~~

Nếu chỉ gọi `ClassLoader.getResource(name)`, thường nhận được **một URL đầu tiên** theo đường tìm kiếm của ClassLoader. Nhưng một plugin manager, bộ đọc metadata, hệ thống service discovery hoặc công cụ kiểm tra cấu hình có thể cần **mọi** URL khớp với cùng tên. Khi đó hai API đáng chú ý là:

~~~java
Enumeration<URL> all = loader.getResources(name);
Stream<URL> stream = loader.resources(name);
~~~

Bài học tập trung vào sự khác nhau giữa **tìm một resource** và **liệt kê mọi resource nhìn thấy được**, thứ tự parent/child, cách duyệt `Enumeration` so với `Stream`, và những trường hợp dễ nhầm khi resource trùng tên.

**Phân biệt ngay từ đầu:** Resource thường là dữ liệu như file văn bản, cấu hình, ảnh, `META-INF/services/...`; tên resource không phải tên binary class. `getResources` không phải lệnh đọc tất cả class của một JAR và không liệt kê toàn bộ các file trong JAR khi bạn chỉ cung cấp một tên resource.

## 2. Bốn API thường gặp

Với một đối tượng `ClassLoader loader` và tên tài nguyên `"demo/resource/lesson-source.txt"`:

| API | Kết quả | Ý nghĩa |
|---|---|---|
| `loader.getResource(name)` | `URL` hoặc `null` | Lấy **một** resource đầu tiên theo quy tắc tìm |
| `loader.getResourceAsStream(name)` | `InputStream` hoặc `null` | Mở stream cho resource đầu tiên; caller phải đóng |
| `loader.getResources(name)` | `Enumeration<URL>` | Liệt kê **các URL khớp** mà loader nhìn thấy |
| `loader.resources(name)` | `Stream<URL>` | Truy cập các URL khớp qua Java Stream API (từ Java 9) |

Cả `getResources` và `resources` làm việc với **URL**, không trực tiếp trả byte nội dung. Muốn đọc nội dung thì mở `URL.openStream()` hoặc một API phù hợp khác, rồi đóng stream sau khi xử lý.

Một ví dụ về hình thức API; mã này chỉ để minh họa, chưa phải chương trình chạy độc lập:

~~~java
String name = "demo/resource/lesson-source.txt";
ClassLoader loader = Thread.currentThread().getContextClassLoader();

URL first = loader.getResource(name);
Enumeration<URL> urls = loader.getResources(name);
Stream<URL> stream = loader.resources(name);
~~~

`getResources` có thể ném `IOException`; các I/O lỗi phát sinh khi tiêu thụ `resources` có thể được bọc trong `UncheckedIOException`. Trong ứng dụng thực tế, cũng cần xử lý trường hợp `loader == null` nếu lấy loader từ context hoặc `SomeClass.class.getClassLoader()`.

## 3. Cơ chế tìm theo ClassLoader

Đối với `ClassLoader` tuân **parent-first delegation**, thứ tự tìm thường là:

~~~text
child.getResources("demo/resource/lesson-source.txt")
                   │
                   ▼
            Hỏi parent trước
                   │
           PARENT (nếu có)
                   │
                   ▼
        Duyệt nguồn riêng của child
                   │
              A rồi B
                   │
                   ▼
         Enumeration/Stream URL
           [PARENT, A, B]
~~~

Ví dụ ta tạo parent `URLClassLoader` chứa `parent.jar`. Child cũng là `URLClassLoader` nhưng chứa hai URL theo thứ tự `[a.jar, b.jar]`.

- `child.getResource(name)` tìm **PARENT** trước, trả URL trong `parent.jar`.
- `child.getResources(name)` liệt kê **PARENT, A, B** trong thứ tự của cấu hình thí nghiệm.
- `child.resources(name)` biểu diễn các URL ấy bằng `Stream<URL>`.
- `parent.getResources(name)` không tự duyệt tài nguyên riêng của child, nên trong ví dụ chỉ có **PARENT**.
- Một loader khác không có `parent.jar` trong chuỗi tìm, nhưng có `[a.jar,b.jar]`, sẽ liệt kê **A, B**.

Các quy tắc này giải thích **ví dụ dùng URLClassLoader mặc định**. Một ClassLoader tùy biến có thể override `getResource` hoặc `getResources`, hoặc cung cấp resource từ nguồn không phải JAR. Quy tắc resource của named modules và ảnh hưởng của `opens` cũng phải xét riêng.

## 4. Ví dụ Java 17+ đầy đủ với ba JAR tài nguyên

Ví dụ tạo ba JAR chỉ chứa resource text; host chủ động tạo loader cha và con. Ta chọn một đường resource mang tính riêng cho bài học để tránh trùng ngoài ý muốn với tài nguyên JDK hoặc host.

### 4.1. Cấu trúc thư mục

~~~text
resources-demo/
├── src/
│   └── demo/host/
│       └── ResourceDemo.java
└── resource-src/
    ├── parent/
    │   └── demo/resource/lesson-source.txt
    ├── a/
    │   └── demo/resource/lesson-source.txt
    └── b/
        └── demo/resource/lesson-source.txt
~~~

Các tệp `lesson-source.txt` chứa đúng nhãn tương ứng, mỗi file một dòng:

| Đường dẫn | Nội dung |
|---|---|
| `resource-src/parent/demo/resource/lesson-source.txt` | `PARENT` |
| `resource-src/a/demo/resource/lesson-source.txt` | `A` |
| `resource-src/b/demo/resource/lesson-source.txt` | `B` |

Dùng văn bản UTF-8 không BOM; dấu xuống dòng cuối file có thể có hoặc không vì chương trình sử dụng `strip()`.

### 4.2. File Java chạy được

Tạo file **`src/demo/host/ResourceDemo.java`**:

~~~java
package demo.host;

import java.io.IOException;
import java.io.InputStream;
import java.io.UncheckedIOException;
import java.net.URL;
import java.net.URLClassLoader;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.Enumeration;
import java.util.List;
import java.util.stream.Collectors;
import java.util.stream.Stream;

public final class ResourceDemo {
    private static final String NAME = "demo/resource/lesson-source.txt";

    private ResourceDemo() {
    }

    private static String content(URL url) throws IOException {
        if (url == null) {
            return "(missing)";
        }
        try (InputStream stream = url.openStream()) {
            return new String(
                    stream.readAllBytes(),
                    StandardCharsets.UTF_8).strip();
        }
    }

    private static String content(InputStream input) throws IOException {
        if (input == null) {
            return "(missing)";
        }
        try (InputStream stream = input) {
            return new String(
                    stream.readAllBytes(),
                    StandardCharsets.UTF_8).strip();
        }
    }

    private static String all(Enumeration<URL> urls) throws IOException {
        List<String> names = new ArrayList<>();
        while (urls.hasMoreElements()) {
            names.add(content(urls.nextElement()));
        }
        return String.join(" > ", names);
    }

    private static String all(Stream<URL> urls) {
        try (urls) {
            return urls.map(url -> {
                try {
                    return content(url);
                } catch (IOException ex) {
                    throw new UncheckedIOException(ex);
                }
            }).collect(Collectors.joining(" > "));
        }
    }

    public static void main(String[] args) throws Exception {
        if (args.length != 3) {
            throw new IllegalArgumentException(
                    "Usage: ResourceDemo <parent.jar> <a.jar> <b.jar>");
        }

        Path parentJar = Path.of(args[0]).toAbsolutePath().normalize();
        Path aJar = Path.of(args[1]).toAbsolutePath().normalize();
        Path bJar = Path.of(args[2]).toAbsolutePath().normalize();

        if (!Files.isRegularFile(parentJar)
                || !Files.isRegularFile(aJar)
                || !Files.isRegularFile(bJar)) {
            throw new IllegalArgumentException("All three JARs must exist");
        }

        URL parentUrl = parentJar.toUri().toURL();
        URL aUrl = aJar.toUri().toURL();
        URL bUrl = bJar.toUri().toURL();

        // Parent chứa parent.jar; child chứa a.jar, b.jar.
        // Platform loader không có file demo/resource/lesson-source.txt.
        try (URLClassLoader parent = new URLClassLoader(
                     new URL[] {parentUrl},
                     ClassLoader.getPlatformClassLoader());
             URLClassLoader child = new URLClassLoader(
                     new URL[] {aUrl, bUrl}, parent);
             URLClassLoader noParentJar = new URLClassLoader(
                     new URL[] {aUrl, bUrl},
                     ClassLoader.getPlatformClassLoader())) {

            System.out.println("getResource: "
                    + content(child.getResource(NAME)));
            System.out.println("getResourceAsStream: "
                    + content(child.getResourceAsStream(NAME)));

            System.out.println("getResources: "
                    + all(child.getResources(NAME)));
            System.out.println("resources: "
                    + all(child.resources(NAME)));

            System.out.println("parent getResources: "
                    + all(parent.getResources(NAME)));
            System.out.println("without parent.jar: "
                    + all(noParentJar.getResources(NAME)));

            System.out.println("missing single resource: "
                    + (child.getResource("demo/resource/not-found.txt")
                    == null));
        }
    }
}
~~~

**Các chi tiết có chủ đích:**

- Ta chọn `ClassLoader.getPlatformClassLoader()` làm tổ tiên cho loader cha và loader `noParentJar`. Điều này tránh vô tình tìm resource trong classpath ứng dụng host ở phép thử. Tên tài nguyên cũng được chọn riêng để chắc chắn không nằm trong các JDK modules thông thường.
- Loader `child` có parent chính là URLClassLoader giữ `parent.jar`; đường tìm kiếm riêng của child là `a.jar` rồi `b.jar`.
- Hai overload `content(URL)` và `content(InputStream)` đều đóng stream. Trường hợp resource không tồn tại được biểu diễn rõ là `"(missing)"`.
- `all(Enumeration<URL>)` sử dụng `hasMoreElements()`/`nextElement()` theo thứ tự enumerate.
- `all(Stream<URL>)` dùng Java Stream API; lỗi đọc URL bên trong lambda được chuyển từ `IOException` checked sang `UncheckedIOException` để không nuốt lỗi.
- Chương trình in **nội dung từng resource**, tránh in `jar:file:/...` có đường dẫn tuyệt đối phụ thuộc máy.

### 4.3. Biên dịch và đóng JAR

Chạy lệnh từ thư mục `resources-demo/`, sau khi tạo các file ở trên.

**Bash (Linux, macOS, Git Bash):**

~~~bash
mkdir -p build/classes dist

javac -encoding UTF-8 \
  -d build/classes src/demo/host/ResourceDemo.java

jar --create --file dist/parent.jar -C resource-src/parent .
jar --create --file dist/a.jar -C resource-src/a .
jar --create --file dist/b.jar -C resource-src/b .

java -cp build/classes \
  demo.host.ResourceDemo dist/parent.jar dist/a.jar dist/b.jar
~~~

**Windows PowerShell:**

~~~powershell
New-Item -ItemType Directory -Force build/classes,dist | Out-Null

javac -encoding UTF-8 -d build/classes src/demo/host/ResourceDemo.java

jar --create --file dist/parent.jar -C resource-src/parent .
jar --create --file dist/a.jar -C resource-src/a .
jar --create --file dist/b.jar -C resource-src/b .

java -cp build/classes demo.host.ResourceDemo dist/parent.jar dist/a.jar dist/b.jar
~~~

Chú ý: **không** đưa ba resource JAR lên `-cp` của lệnh chạy host; chương trình sẽ tải chúng qua các `URLClassLoader` mà nó tự tạo. Nếu vô tình đặt `parent.jar` hay `a.jar` trên application classpath, mô hình tìm resource trong ví dụ có thể khác dự kiến.

Kiểm tra JAR nếu cần:

~~~bash
jar --list --file dist/parent.jar
jar --list --file dist/a.jar
jar --list --file dist/b.jar
~~~

Cả ba JAR phải có entry chính xác `demo/resource/lesson-source.txt`. Output của `jar --list` có thể chứa thêm `META-INF/MANIFEST.MF` và các entry thư mục.

### 4.4. Stdout chính xác

Với đúng nội dung 3 file text và lệnh chạy đã cho, kết quả là:

~~~text
getResource: PARENT
getResourceAsStream: PARENT
getResources: PARENT > A > B
resources: PARENT > A > B
parent getResources: PARENT
without parent.jar: A > B
missing single resource: true
~~~

**Giải thích từng dòng:**

1. `getResource` lấy resource đầu tiên trong thứ tự parent-first, vì vậy là `PARENT`.
2. `getResourceAsStream` mở resource đầu tiên ấy, nên cũng đọc ra `PARENT`.
3. `getResources` kết hợp resource từ parent và nguồn URL của child theo thứ tự dự kiến: `PARENT > A > B`.
4. `resources` trả một Stream của các URL khớp với cùng tên; khi tiêu thụ bằng `collect`, ví dụ cho ra cùng thứ tự `PARENT > A > B`.
5. `parent.getResources` chỉ thấy `parent.jar` và tổ tiên của nó; không tìm ngược trong JAR của child nên chỉ có `PARENT`.
6. `noParentJar` trỏ tới A rồi B, parent của nó là platform loader, nên nó không thấy `parent.jar` và cho `A > B`.
7. `getResource` trả `null` với tên không tồn tại.

Đây là **một cấu hình được kiểm soát với URLClassLoader chuẩn**, không phải cam kết mọi ClassLoader đều sắp xếp resource theo cách tương tự.

## 5. `getResources` và `resources` khác nhau ra sao?

### 5.1. `Enumeration<URL>` của `getResources`

~~~java
Enumeration<URL> urls = loader.getResources("example/config.properties");
while (urls.hasMoreElements()) {
    URL url = urls.nextElement();
    // Xử lý từng URL
}
~~~

Đây là API lâu đời, phù hợp thư viện Java cũ và những nơi muốn duyệt lần lượt với `while`. `getResources` khai báo `throws IOException`. `Enumeration` cung cấp thứ tự phần tử từ loader, nhưng bản thân interface Enumeration không tự áp đặt thứ tự cụ thể cho mọi loại nguồn.

**Không tạo giả định “Enumeration nghĩa là không có duplicate”.** Nếu nhiều JAR khác nhau chứa tên resource được hỏi, kết quả có thể có nhiều URL. Nếu cùng resource được xuất hiện qua nhiều đường tìm kiếm, việc phân biệt/trùng lặp kết quả phụ thuộc implementation; caller cần tự xử lý duplicate theo yêu cầu nghiệp vụ.

### 5.2. `Stream<URL>` của `resources`

Từ Java 9, `ClassLoader.resources(String)` trả một `Stream<URL>` để dùng các phép biến đổi/lọc/tập hợp:

~~~java
try (Stream<URL> urls = loader.resources("example/config.properties")) {
    List<URL> matches = urls.toList(); // Java 16+
    System.out.println("Count: " + matches.size());
}
~~~

Đoạn này **chỉ minh họa** khi đã có `loader` và các import thích hợp. Trên Java 17+, `Stream.toList()` khả dụng. Khi dùng Stream:

- Stream thường được xử lý **lười (lazy)**: URL được duyệt khi có terminal operation như `toList()` hoặc `collect(...)`.
- Stream **dùng một lần**; đã tiêu thụ thì không gọi terminal operation thứ hai trên chính Stream ấy.
- Không chạy `parallel()` nếu thứ tự là một phần logic ưu tiên và bạn chưa kiểm chứng contract của collector/nguồn.
- Nếu việc duyệt resource dẫn tới I/O error, theo tài liệu `resources` lỗi có thể xuất hiện dưới dạng `UncheckedIOException` trong khi tiêu thụ Stream.
- `try-with-resources` cho Stream là thực hành rõ ràng khi viết thư viện tổng quát, đặc biệt nếu pipeline có `onClose` handlers. **Không suy diễn** rằng đóng Stream có thể đóng được mọi `InputStream` do bạn đã chủ động mở trong `map`; các input stream đó phải được đóng riêng.

`resources` **không chuyển nội dung của resource thành Stream text lines**. Nó là Stream của **URL**, mỗi URL vẫn cần được đọc riêng khi muốn xử lý dữ liệu.

### 5.3. Chọn API nào?

| Nhu cầu | API nên dùng |
|---|---|
| Một file cấu hình đầu tiên theo loader | `getResource` |
| Một stream để đọc file đầu tiên | `getResourceAsStream` |
| Liệt kê đầy đủ các URL trùng tên và xử lý tuần tự | `getResources` |
| Lọc/sắp xếp/chuyển đổi các URL bằng Stream API | `resources` |
| Nạp service provider từ nhiều JAR | `ServiceLoader`, vì còn phải xử lý định dạng descriptor và hợp đồng service |
| Liệt kê tất cả mục trong một JAR | `JarFile`/ZIP API hoặc hệ thống đọc JAR, **không** phải `getResources(name)` |

## 6. Thứ tự liệt kê quan trọng đến mức nào?

Khi một loader con mặc định ủy quyền cho parent, các resource mà parent thấy được thường xuất hiện trước. Đối với `URLClassLoader` chuẩn, các URL của chính nó được tìm theo thứ tự đường tìm kiếm, ví dụ `[a.jar, b.jar]`. Nhưng:

- ClassLoader con tùy chỉnh có thể đổi cả `getResource` và `getResources`; nếu override một phương thức mà bỏ qua phương thức kia, hành vi của API đơn resource và nhiều resource có thể không tương thích.
- Nếu resource thuộc **named module**, quy tắc đóng gói module và khả năng mở package có thể khiến resource không hiển thị như trong ví dụ classpath.
- Nếu thêm JAR bằng classpath wildcard `lib/*`, thứ tự mở rộng các JAR không nhất thiết ổn định. Không thiết kế độ ưu tiên cấu hình dựa trên tên file alphabet.
- JAR manifest `Class-Path`, loader của framework, hoặc classpath được xây dựng bởi tool có thể thêm nguồn resource vào đường tìm kiếm.
- Nếu cần thứ tự nghiệp vụ ổn định, tốt hơn là định nghĩa **quy tắc ưu tiên rõ ràng** trong ứng dụng (ví dụ config version, priority field, thứ tự plugin) rồi áp dụng sau khi thu thập URL, thay vì trông chờ thứ tự ngẫu nhiên của môi trường.

**Không được đánh đồng thứ tự resource với class identity.** Với class cùng tên, một loader thường chọn một class được định nghĩa tương ứng. Với resource trùng tên, `getResources` có thể trả **nhiều URL** để caller tự quyết định gộp, ưu tiên hoặc xử lý toàn bộ.

## 7. Cùng resource name nhưng nhiều URL: cách quyết định xử lý

Nếu kết quả `getResources(name)` là `[PARENT, A, B]`, ứng dụng có thể chọn ba chiến lược khác nhau:

**Chọn bản đầu tiên:** Dùng `getResource` khi ứng dụng có quy tắc “parent hoặc nguồn đứng trước được ưu tiên”. Không cần enumerate nhiều file nếu chỉ muốn một resource.

**Gộp các cấu hình:** Duyệt `getResources` hoặc `resources`, parse mỗi file và gộp theo quy tắc xác định, ví dụ “lấy bản sau ghi đè key trước” hoặc “trùng key là lỗi”. Phải nêu thứ tự gộp rõ ràng và bảo đảm ổn định theo yêu cầu nghiệp vụ.

**Xử lý tất cả:** Đối với metadata dịch vụ, file index hoặc rule fragments, có thể cần từng resource. Trùng file không có nghĩa nên bỏ qua: mỗi JAR có thể cung cấp một khai báo độc lập.

Ví dụ mẫu gộp theo thứ tự gặp các URL (mã minh họa, không phải chương trình chạy độc lập):

~~~java
Enumeration<URL> urls = loader.getResources("features.properties");
while (urls.hasMoreElements()) {
    URL url = urls.nextElement();
    try (InputStream in = url.openStream()) {
        // Parse file này rồi merge theo quy tắc của ứng dụng.
    }
}
~~~

Nếu file có thể đến từ code hoặc thư viện không tin cậy, không tự động thực thi nội dung hay mở URL ngoài phạm vi cần thiết. URL là vị trí truy cập resource, không phải chứng nhận rằng nội dung đúng hoặc an toàn.

## 8. Resource name, đường dẫn tuyệt đối và tương đối

### 8.1. `ClassLoader.getResource` không tự thêm package

Với `ClassLoader`, thường dùng tên resource theo **đường dẫn từ root** và **không có dấu `/` đầu**:

~~~java
loader.getResource("demo/resource/lesson-source.txt");
~~~

Nếu bạn truyền `"/demo/resource/lesson-source.txt"` cho `ClassLoader.getResource`, việc tìm có thể thất bại vì dấu slash đầu được xem là một phần của tên resource. Hãy dùng path từ root như trong JAR.

### 8.2. `Class.getResource` có quy tắc khác

Với `Class.getResource`:

~~~java
// Ví dụ minh họa với ResourceDemo đã được định nghĩa.
ResourceDemo.class.getResource("local.txt");
ResourceDemo.class.getResource("/demo/resource/lesson-source.txt");
~~~

Tên **không bắt đầu bằng `/`** được diễn giải tương đối với package của class; tên **bắt đầu bằng `/`** được diễn giải từ root. Tuy nhiên, `ResourceDemo.class` thuộc **system loader** và không tự nhìn thấy JAR do child loader tạo trong ví dụ. Vì vậy chỉ sửa tên sang dạng tuyệt đối **không tự làm resource riêng của child trở nên nhìn thấy được**.

Nếu mục tiêu là JAR plugin, hãy tra cứu bằng đúng loader của plugin, ví dụ `child.getResources(name)`, thay vì mặc định dùng class loader của host.

### 8.3. Tên resource không phải tên lớp

Tệp `demo/resource/lesson-source.txt` khác với tên `demo.resource.lesson-source`. Resource sử dụng đường dẫn dấu slash; một class có tên `demo.plugin.Greeter` thường có resource bytecode tương ứng là `demo/plugin/Greeter.class`, nhưng việc truy xuất bytecode qua resource API có thể chịu ràng buộc module/loader và không phải phương pháp tổng quát để “liệt kê class”.

## 9. ServiceLoader: trường hợp thực tế cần nhiều resource cùng tên

Trong mô hình classpath, Java SPI dùng các tệp provider configuration nằm tại:

~~~text
META-INF/services/<tên đầy đủ của interface dịch vụ>
~~~

Ví dụ với `example.api.PaymentProvider`, hai plugin JAR có thể đều có:

~~~text
META-INF/services/example.api.PaymentProvider
~~~

JAR A khai báo `example.plugins.CardProvider`, JAR B khai báo `example.plugins.WalletProvider`. Khi `ServiceLoader` được cung cấp đúng loader nhìn thấy cả hai JAR, nó có thể đọc nhiều tệp descriptor cùng tên và tìm nhiều provider.

Điều quan trọng:

- `ServiceLoader` là API khám phá provider, hiểu định dạng descriptor, kiểm tra lớp/provider có phù hợp interface dịch vụ và khởi tạo đối tượng khi cần.
- `ClassLoader.getResources("META-INF/services/...")` chỉ trả **URL**. Nếu tự parse descriptor, bạn phải tự xử lý comment, encoding, cú pháp, thứ tự và class loader.
- Service interface phải được host và plugin hiểu như **cùng runtime type**; hai interface cùng tên nhưng do loader riêng định nghĩa có thể dẫn tới `ServiceConfigurationError`.
- Trong **JPMS named modules**, service binding dựa vào `uses` và `provides ... with ...` và có thể không cần descriptor classpath truyền thống. Không mô tả toàn bộ JPMS chỉ bằng `META-INF/services`.

Mã minh họa khi đã có `PaymentProvider` và `pluginLoader`:

~~~java
ServiceLoader<PaymentProvider> providers =
        ServiceLoader.load(PaymentProvider.class, pluginLoader);

for (PaymentProvider provider : providers) {
    // Sử dụng provider theo shared interface.
}
~~~

Đoạn này không phải chương trình độc lập: nó giả định interface, provider và loader đã được cấu hình. Đối với ví dụ chạy ở phần 4, ta chỉ dùng resource text để tập trung vào hành vi của API liệt kê.

## 10. Lưu ý JPMS và tính đóng gói của resource

Trên Java 9+, các lớp và resource có thể nằm trong **named modules**. Quy tắc resource lookup có khác biệt đáng kể so với các JAR nằm trên classpath (unnamed modules).

Một số non-class resource trong named module không được trả về khi package chứa resource **không được mở vô điều kiện**, tùy API ClassLoader đang dùng. Nói cách khác, chỉ vì file nằm trong module JAR không có nghĩa `loader.getResources(name)` nhìn thấy file ấy từ mọi ngữ cảnh.

Khi có nghi vấn:

1. Xác minh tài nguyên nằm trong JAR/module thực tế được runtime sử dụng.
2. Xác minh module và package chứa tài nguyên, các khai báo `opens` hoặc `open module` nếu cần.
3. Kiểm tra loader đã yêu cầu và cách framework xây dựng `ModuleLayer`.
4. Kiểm tra có dùng sai đường dẫn `ClassLoader` so với `Class.getResource`.
5. Không tự thêm `--add-opens` hàng loạt chỉ để che lỗi cấu hình; hiểu lý do module đang giới hạn truy cập.

Ví dụ phần 4 **không dùng named modules**, vì thế kết quả resource lookup không phụ thuộc vào khai báo module.

## 11. Thực hành an toàn khi liệt kê nhiều resource

### 11.1. Đóng stream nội dung đúng cách

`URL.openStream()` hoặc `getResourceAsStream` trả `InputStream` phải được đóng; dùng `try-with-resources`. Với nhiều URL, mở và đóng **lần lượt** thường có lợi hơn việc mở toàn bộ stream cùng lúc.

Không nên giữ các stream/JAR handle mở lâu khi plugin cần được thay thế. `URLClassLoader.close()` đóng các JAR handle của loader, nhưng không biến mọi `InputStream` còn đang dùng thành một đối tượng được quản lý vòng đời tự động.

### 11.2. Lỗi I/O không phải “không tìm thấy”

Phân biệt:

- `getResource(name) == null`: loader không tìm được URL theo cơ chế tra cứu.
- `getResources(name)` trả Enumeration rỗng: không có resource phù hợp mà loader có thể liệt kê.
- `IOException` trong lúc enumerate hoặc đọc URL: quá trình truy cập lỗi, không nhất thiết resource không tồn tại.
- `UncheckedIOException` trong xử lý Stream: lỗi I/O bị bọc khi làm việc qua Java Stream API.

Đừng viết `catch (IOException e) { return Collections.emptyList(); }` nếu lỗi I/O cần được báo; làm vậy sẽ âm thầm biến “đọc thất bại” thành “không có resource”.

### 11.3. Dedupe phải phù hợp yêu cầu

Nếu danh sách có cùng URL lặp lại, `distinct()` trên Stream URL hoặc một `Set<URL>` có thể hữu ích với trường hợp cụ thể, nhưng URL equality/normalization có các chi tiết phức tạp; trong một số môi trường, so sánh URL có thể gây hành vi không mong muốn. Khi cần dedupe an toàn, chọn khóa rõ ràng như tên plugin + relative resource path hoặc URI được chuẩn hóa theo chính sách đã kiểm soát.

Nếu hai JAR **khác nhau** cùng cung cấp một resource name nhưng nội dung khác, bỏ bớt chỉ vì tên giống nhau thường làm mất dữ liệu cần xử lý.

## 12. Các lỗi phổ biến

| Hiện tượng | Vì sao xảy ra | Cách xử lý |
|---|---|---|
| `getResource` chỉ trả PARENT dù A/B có cùng resource | Parent-first và chỉ trả URL đầu tiên | Dùng `getResources`/`resources` nếu cần tất cả |
| `getResources` không thấy file của plugin | Dùng system/host loader không thấy URL của plugin | Truyền loader plugin thích hợp |
| `ClassLoader.getResource("/a/b.txt")` trả null | Tên bị thêm dấu slash đầu | Dùng `"a/b.txt"` |
| `Class.getResource("x.txt")` không tìm đúng root | Tên tương đối với package class | Dùng `"/x.txt"` nếu thật sự muốn từ root và đúng loader |
| Chỉ xử lý một tệp `META-INF/services` | `getResource` chỉ có một kết quả | Dùng `ServiceLoader` hoặc enumerate descriptor đúng |
| `Stream has already been operated upon or closed` | Stream `resources` đã tiêu thụ một lần | Tạo stream mới khi cần duyệt lại |
| Kết quả lẫn nhiều JAR không theo thứ tự dự kiến | Parent, URL order, wildcard, framework loader | In danh sách URL, kiểm tra cấu hình loader và đường tìm |
| `IOException` khi mở resource | JAR/URL không đọc được hoặc stream đã lỗi | Báo lỗi thật, đóng tài nguyên đúng cách |
| Tệp nằm trong named module nhưng không nhìn thấy | Đóng gói module, package chưa được mở phù hợp | Xem module ownership và `opens` |
| Đóng loader làm lỗi đọc tài nguyên về sau | Resource lookup hoặc stream bị dùng sau khi loader đóng | Hoàn tất xử lý trong vòng đời loader còn hoạt động |

## 13. Tự kiểm tra

**Câu 1.** Nếu parent có một `settings.txt` và hai JAR child cũng có file cùng tên, `getResource` và `getResources` thường trả gì?

**Đáp án:** `getResource` trả URL đầu tiên của parent, còn `getResources` có thể enumerate cả parent và hai resource child, theo thứ tự parent-first của loader chuẩn.

**Câu 2.** `resources(name)` có trả về Stream các dòng văn bản trong file không?

**Đáp án:** Không. Đây là `Stream<URL>`. Muốn đọc text phải mở URL tương ứng và xử lý input stream.

**Câu 3.** `getResources(name)` có thể dùng như API liệt kê toàn bộ entry một JAR không?

**Đáp án:** Không. Nó tìm các tài nguyên có **tên cụ thể** mà ClassLoader nhìn thấy. Nếu cần liệt kê tất cả entry, dùng `JarFile` hoặc ZIP API.

**Câu 4.** Vì sao một framework dùng `ServiceLoader` có thể tìm nhiều provider dù các JAR đều chứa `META-INF/services/<service>`?

**Đáp án:** Nhiều descriptor cùng tên có thể được tìm qua loader; `ServiceLoader` có quy tắc đọc và xử lý provider từ những descriptor ấy.

**Câu 5.** Vì sao `ResourceDemo.class.getResource("/demo/resource/lesson-source.txt")` trong host không thay thế được `child.getResources("demo/resource/lesson-source.txt")`?

**Đáp án:** `Class.getResource` dùng loader/module gắn với class của host, không tự thấy tài nguyên riêng do child loader quản lý.

**Câu 6.** Đóng Java Stream trả về từ `resources` có tự đóng các `InputStream` mà code mở sau đó trong quá trình xử lý không?

**Đáp án:** Không nên giả định như vậy. Mỗi input stream do ứng dụng mở phải có cơ chế đóng riêng, thường là `try-with-resources` trong hàm đọc.

## 14. Tài liệu chính thức

- [Java SE 17 — ClassLoader](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html): `getResource`, `getResourceAsStream`, `getResources` và `resources`.
- [Java SE 17 — URLClassLoader](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/URLClassLoader.html): đường tìm URL và vòng đời loader.
- [Java SE 17 — ServiceLoader](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ServiceLoader.html): provider configuration, khám phá nhiều provider.
- [Java SE 17 — Class.getResource](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html#getResource(java.lang.String)): đường dẫn tương đối/absolute theo class.
- [Java SE 17 — Java Platform Module System](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Module.html): phạm vi module và quyền truy cập tài nguyên.

**Ghi nhớ:** `getResource` tìm một URL đầu tiên; `getResources` cung cấp `Enumeration<URL>` của nhiều tài nguyên cùng tên; `resources` cung cấp `Stream<URL>` (Java 9+). Kết quả phụ thuộc vào loader cụ thể, parent delegation, đường URL, và trong named modules còn có quy tắc module. Liệt kê URL không tự đọc hoặc gộp nội dung — chính ứng dụng phải quyết định cách xử lý và đóng stream đúng cách.