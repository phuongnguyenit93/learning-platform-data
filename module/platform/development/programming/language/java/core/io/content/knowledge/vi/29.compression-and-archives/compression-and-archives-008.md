# `JarFile`, `JarInputStream` và `Manifest` ở mức Java I/O

## 1. Mục tiêu: đọc một tệp JAR như một kho ZIP có metadata

JAR (*Java ARchive*) là một dạng archive dựa trên ZIP: nó chứa nhiều entry có tên như `com/example/App.class`, `config/settings.properties`, `docs/readme.txt` và có thể chứa file metadata `META-INF/MANIFEST.MF`. Khi thao tác ở **mức I/O**, chương trình không nhất thiết phải tải class hoặc thực thi JAR; nó có thể chỉ cần liệt kê entry, lấy tài nguyên, đọc manifest, kiểm tra thông tin về entry và đóng stream đúng cách.

Hai lớp thường gặp:

- **`java.util.jar.JarFile`**: mở một **tệp JAR đã có trên filesystem**, tra cứu entry theo tên, liệt kê các entry và mở `InputStream` cho từng entry; extends `java.util.zip.ZipFile`.
- **`java.util.jar.JarInputStream`**: đọc một JAR **tuần tự từ `InputStream`**; extends `java.util.zip.ZipInputStream`. Phù hợp khi nguồn là dữ liệu truyền qua stream mà không có tệp để truy cập tùy ý.
- **`java.util.jar.Manifest`**: mô hình dữ liệu cho `META-INF/MANIFEST.MF`, gồm **main attributes** và **per-entry attributes**. Đây là metadata về archive và từng entry, không phải nội dung của mọi file bên trong JAR.

Bài tập trung vào các API Java SE 17+ ở tầng I/O: cách đọc đúng, vị trí manifest, vòng đời entry/stream, so sánh hiệu năng và các giới hạn bảo mật. Những khái niệm về class loading, launcher và chữ ký JAR chỉ được trình bày đủ để tránh suy diễn sai từ dữ liệu I/O.

## 2. Một JAR trông như thế nào?

Một archive có thể chứa:

```text
sample.jar
├── META-INF/
│   └── MANIFEST.MF
├── com/example/Main.class
├── docs/
│   └── readme.txt
└── config/
    └── app.properties
```

Các “thư mục” trong JAR thường là entry có tên kết thúc bằng dấu `/` (ví dụ `docs/`). Không bắt buộc mọi đường dẫn cha đều có một directory entry riêng; có thể tồn tại `docs/readme.txt` mà không có entry `docs/`.

Ví dụ nội dung manifest:

```text
Manifest-Version: 1.0
Main-Class: com.example.Main
Created-By: Example

Name: docs/readme.txt
X-Role: documentation

```

Ý nghĩa:

- `Manifest-Version`: thuộc tính phiên bản định dạng manifest.
- `Main-Class`: tên lớp chính dùng trong trường hợp JAR được launcher chạy theo cơ chế có hỗ trợ; giá trị là tên lớp theo cú pháp Java, không phải tên `.class` trong ZIP.
- `Created-By`: ví dụ thuộc tính metadata do công cụ tạo JAR cung cấp.
- `Name: docs/readme.txt` bắt đầu **một section theo entry**; thuộc tính `X-Role` bên dưới thuộc section của file đó, không thuộc main attributes.

Dòng trắng ngăn cách các section. Định dạng manifest có các quy tắc riêng về kết thúc dòng, mã hóa và xuống dòng tiếp nối những giá trị dài; để tạo manifest hợp lệ, nên dùng lớp `Manifest` thay vì nối chuỗi tùy ý. Tên entry trong manifest được dùng để liên hệ metadata với entry tương ứng; **việc tồn tại một section không tự chứng minh archive chứa entry ấy**, và một entry bình thường có thể không có section metadata riêng.

## 3. So sánh `JarFile` và `JarInputStream`

| Tiêu chí | `JarFile` | `JarInputStream` |
| --- | --- | --- |
| Cơ sở API | extends `ZipFile` | extends `ZipInputStream` |
| Đầu vào | File/JAR có thể mở dưới dạng file | Bất kỳ `InputStream` phù hợp |
| Kiểu duyệt | Tra cứu entry theo tên, liệt kê các entry | Đọc lần lượt bằng `getNextJarEntry()` |
| Lấy manifest | `getManifest()`, có thể tìm manifest trong archive | `getManifest()` với **điều kiện vị trí manifest đầu stream** |
| Đọc nội dung entry | `jar.getInputStream(entry)` | Đọc `jarInput.read(...)` trên entry hiện tại |
| Chuyển tới entry khác | Tra cứu entry mới độc lập | `getNextJarEntry()` dịch sang entry kế tiếp |
| Nguồn mạng/pipe chưa lưu file | Cần có bản JAR dạng file phù hợp trước | Có thể dùng trực tiếp stream |
| Quản lý tài nguyên | Đóng `JarFile` và các entry streams | Đóng `JarInputStream` bao bọc nguồn |
| Có thể truy cập entry thứ hai trước entry đầu? | Có thể, qua `getJarEntry(name)` | Không; dữ liệu được đọc tuần tự |

**Đừng nhầm chữ “random access” với tùy ý sửa bytes.** `JarFile` hỗ trợ *tra cứu và mở stream theo tên entry* mà không phải đọc lần lượt toàn bộ entry trước đó, nhưng đây vẫn là API **đọc archive**, không phải `RandomAccessFile` cho phép thay đổi tùy ý byte của ZIP. Khi cần tạo JAR hoặc thay nội dung, dùng `JarOutputStream`/công cụ đóng gói và tạo lại archive theo kế hoạch phù hợp.

Một JAR có thể có entry nén theo `DEFLATED` hoặc không nén theo `STORED`. Khi đọc entry, API trả ra **byte nội dung sau giải nén**, chứ không phải chuỗi byte nén trong archive.

## 4. `JarFile`: tra cứu và đọc entry bằng tên

API thường gặp:

```java
try (JarFile jar = new JarFile(jarPath.toFile())) {
    Manifest manifest = jar.getManifest(); // có thể null
    JarEntry entry = jar.getJarEntry("docs/readme.txt");

    if (entry != null && !entry.isDirectory()) {
        try (InputStream in = jar.getInputStream(entry)) {
            byte[] bytes = in.readAllBytes();
            // Chỉ dùng readAllBytes() nếu đã giới hạn kích thước dữ liệu!
        }
    }
}
```

Đây là snippet, **không phải chương trình độc lập**; cần `jarPath` có giá trị `Path` đúng, import `JarFile`, `JarEntry`, `Manifest`, `InputStream`, và xử lý `IOException`.

### `getJarEntry(name)` và `getEntry(name)` khác gì?

- `JarFile.getJarEntry(String name)` trả `JarEntry` hoặc `null` nếu không tìm thấy.
- `JarFile.getEntry(String name)` trả kiểu `ZipEntry` hoặc `null`; `JarEntry` là một dạng entry mở rộng của `ZipEntry`.
- `jar.entries()` trả `Enumeration<JarEntry>` để duyệt các entry. Có thể dùng `jar.stream()` để nhận stream entry theo hỗ trợ của `ZipFile`.
- `jar.getInputStream(entry)` mở một luồng để **đọc nội dung của entry đã được xác định**.

Tránh nhầm `JarFile.getInputStream(entry)` với việc đọc từ một `JarInputStream` đang đứng tại entry hiện tại. Với `JarFile`, bạn có thể chọn `docs/readme.txt` trước, rồi chọn `config/app.properties`, không phụ thuộc trình tự vật lý của ZIP. Với `JarInputStream`, muốn tới entry ở gần cuối phải đi qua entry trước theo thứ tự stream.

### Đọc theo chunk, không nạp vô hạn vào RAM

`InputStream.readAllBytes()` trong snippet thích hợp với file nhỏ có giới hạn do ứng dụng kiểm soát. Với JAR từ nguồn không tin cậy hoặc resource có thể rất lớn:

```java
byte[] block = new byte[8192];
long total = 0;
int n;
while ((n = in.read(block)) != -1) {
    total += n;
    if (total > MAX_ALLOWED_BYTES) {
        throw new IOException("Entry too large");
    }
    // Gửi block[0..n) đến bộ xử lý theo stream.
}
```

Đây là snippet yêu cầu `in`, `MAX_ALLOWED_BYTES` và hàm xử lý do chương trình định nghĩa. Trong code thật nên hạn chế thêm tốc độ, số entry, tổng byte giải nén và thời gian xử lý; tránh overflow số học bằng cách kiểm tra giới hạn trước khi cộng khi cần.

## 5. `JarInputStream`: duyệt tuần tự và đọc entry hiện tại

Tạo từ một input stream:

```java
try (JarInputStream jis =
        new JarInputStream(Files.newInputStream(jarPath))) {

    Manifest manifest = jis.getManifest();

    JarEntry entry;
    while ((entry = jis.getNextJarEntry()) != null) {
        System.out.println("entry=" + entry.getName());

        if (!entry.isDirectory()) {
            byte[] bytes = jis.readAllBytes();
            // Chỉ dùng cách này khi file có kích thước nhỏ/giới hạn rõ.
        }

        jis.closeEntry();
    }
}
```

Snippet cần các import và xử lý `IOException`. `getNextJarEntry()` di chuyển tới đầu entry tiếp theo và trả `null` khi hết archive. Trong khi đang ở entry, `jis.read(...)` đọc **byte giải nén của entry ấy**. Khi tới cuối entry, `read` trả `-1` cho entry hiện tại; điều đó không có nghĩa toàn bộ JAR đã hết — gọi `getNextJarEntry()` để lấy entry kế tiếp.

**Không được** tạo một `new JarInputStream` cho mỗi entry trong cùng input stream và mong quay lại đầu JAR; stream đã tiến về phía trước. Nếu cần đọc lại, nguồn phải có cách tái tạo stream (hoặc ghi ra file rồi dùng `JarFile`).

### `closeEntry()` có tác dụng gì?

`closeEntry()` kết thúc việc đọc entry hiện tại, bỏ qua những byte nội dung entry còn chưa tiêu thụ nếu có và chuẩn bị chuyển tiếp. `getNextJarEntry()` cũng xử lý việc tiến đến entry kế tiếp theo hợp đồng của ZIP stream. Trong vòng xử lý có kiểm chứng chữ ký hoặc integrity, **đọc hết entry** giúp cho verification/integrity checks có cơ hội hoàn tất; không giả định chỉ đọc header là đủ để kiểm tra toàn bộ nội dung.

### `JarInputStream` không tự tạo `InputStream` độc lập cho từng entry

`JarInputStream` **chính là** luồng đang đọc entry hiện tại. Bạn không gọi `jis.getInputStream(entry)` như `JarFile`. Nếu muốn tách riêng nội dung từng entry, phải copy các byte của entry sang đích hoặc xử lý ngay trong lúc đang đứng ở entry đó.

## 6. `Manifest`: main attributes và per-entry attributes

Các API cần nhớ:

| API | Trả về / ý nghĩa |
| --- | --- |
| `jar.getManifest()` | `Manifest` hoặc `null` nếu archive không có manifest |
| `jis.getManifest()` | `Manifest` khi manifest được nhận ở vị trí đầu hợp lệ, hoặc `null` |
| `manifest.getMainAttributes()` | `Attributes` của phần main |
| `manifest.getEntries()` | `Map<String, Attributes>` chứa các section theo tên entry |
| `manifest.getAttributes("docs/readme.txt")` | `Attributes` của section chỉ định, hoặc `null` |
| `attrs.getValue(Attributes.Name.MAIN_CLASS)` | Giá trị attribute được định danh bằng `Attributes.Name`, hoặc `null` |
| `attrs.getValue("X-Role")` | Giá trị attribute theo tên chuỗi, hoặc `null` |

Ví dụ:

```java
Manifest manifest = jar.getManifest();
if (manifest != null) {
    Attributes main = manifest.getMainAttributes();

    String version = main.getValue(Attributes.Name.MANIFEST_VERSION);
    String mainClass = main.getValue(Attributes.Name.MAIN_CLASS);

    Attributes docs = manifest.getAttributes("docs/readme.txt");
    String role = docs == null ? null : docs.getValue("X-Role");
}
```

Snippet giả định `jar` là `JarFile` hợp lệ. **`Manifest.getEntries()` không liệt kê tất cả file trong JAR**: nó chỉ liệt kê các section có metadata trong manifest. Muốn liệt kê archive entries, dùng `JarFile.entries()` hoặc `JarInputStream.getNextJarEntry()`.

Tương tự, **`Main-Class` là metadata**, không phải bằng chứng rằng lớp được chỉ định thực sự tồn tại, có hàm `public static void main(String[])` đúng, hoặc JAR sẽ chạy thành công với `java -jar`. Muốn xác minh cần kiểm tra archive và quá trình launch theo yêu cầu.

Các giá trị tên section thường sử dụng dạng tên entry ZIP với dấu `/`, không phải đường dẫn tuyệt đối của máy. Đừng chuyển thẳng tên entry vào `Path` ngoài archive mà không kiểm soát mục tiêu.

## 7. Điểm khác biệt quan trọng: vị trí manifest đối với `JarInputStream`

Không phải mọi file có tên `META-INF/MANIFEST.MF` ở bất kỳ chỗ nào trong archive đều được `JarInputStream.getManifest()` nhận tự động.

Theo hợp đồng API Java 17:

- `JarInputStream.getManifest()` trả manifest nếu `META-INF/MANIFEST.MF` là **entry đầu tiên** trong luồng ZIP/JAR.
- Hoặc nếu entry đầu tiên là thư mục `META-INF/` và **entry thứ hai** là `META-INF/MANIFEST.MF`.
- Nếu manifest nằm ở vị trí khác, `getManifest()` **không bảo đảm tìm/đọc nó** như manifest đầu luồng. Hành vi có bỏ qua nó ở những vị trí muộn hơn hay không cũng không nên dựa vào.

Khi manifest ở đầu hợp lệ, `getNextJarEntry()` / `getNextEntry()` **bỏ qua entry manifest** đã được constructor xử lý; nếu entry đầu là `META-INF/` rồi manifest, cả hai entry đó được bỏ qua trong quá trình duyệt bình thường.

Sơ đồ:

```text
JAR A:
  META-INF/
  META-INF/MANIFEST.MF
  docs/readme.txt
             ^
  getManifest() đọc metadata;
  getNextJarEntry() bắt đầu bằng docs/readme.txt

JAR B:
  docs/readme.txt
  META-INF/MANIFEST.MF
             ^
  Không giả định getManifest() sẽ đọc manifest xuất hiện muộn!
```

Trái lại, `JarFile` đọc cấu trúc archive như một file ZIP và có thể truy cập entry manifest theo tên; `getManifest()` không phụ thuộc việc các entry nằm ở đầu stream như `JarInputStream`.

**Cách tạo JAR đúng thứ tự:** dùng `new JarOutputStream(output, manifest)`. Constructor này hỗ trợ tạo entry manifest sớm theo hợp đồng API, giúp `JarInputStream` nhận `Manifest` trong ví dụ học tập. Khi tạo JAR bằng công cụ ngoài, cần kiểm tra quy cách đóng gói nếu logic xử lý stream yêu cầu manifest đầu luồng.

## 8. Ví dụ Java 17+ hoàn chỉnh: tạo rồi đọc JAR bằng cả hai API

Chương trình sau tạo JAR tạm từ Java, bổ sung manifest và hai file nội dung nhỏ. Sau đó nó đọc cùng archive theo hai cách để thể hiện **tra cứu entry theo tên** với `JarFile` và **duyệt tuần tự** với `JarInputStream`.

Lưu thành **`JarFileVsInputStreamDemo.java`**:

```java
import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.jar.Attributes;
import java.util.jar.JarEntry;
import java.util.jar.JarFile;
import java.util.jar.JarInputStream;
import java.util.jar.JarOutputStream;
import java.util.jar.Manifest;

public class JarFileVsInputStreamDemo {
    private static void addFile(
            JarOutputStream out, String name, String content)
            throws IOException {
        JarEntry entry = new JarEntry(name);
        out.putNextEntry(entry);
        out.write(content.getBytes(StandardCharsets.UTF_8));
        out.closeEntry();
    }

    public static void main(String[] args) throws Exception {
        Path path = Files.createTempFile("jar-io-demo-", ".jar");

        try {
            Manifest manifest = new Manifest();
            Attributes main = manifest.getMainAttributes();
            main.put(Attributes.Name.MANIFEST_VERSION, "1.0");
            main.put(Attributes.Name.MAIN_CLASS, "example.Main");

            Attributes document = new Attributes();
            document.putValue("X-Role", "documentation");
            manifest.getEntries().put("docs/readme.txt", document);

            try (JarOutputStream out = new JarOutputStream(
                    Files.newOutputStream(path), manifest)) {
                addFile(out, "docs/readme.txt", "HELLO");
                addFile(out, "config/app.properties", "mode=demo\n");
            }

            // CÁCH A: JarFile cho phép tra cứu entry bằng tên.
            try (JarFile jar = new JarFile(path.toFile())) {
                Manifest meta = jar.getManifest();
                System.out.println("jarfile-main="
                        + meta.getMainAttributes().getValue(
                                Attributes.Name.MAIN_CLASS));

                JarEntry readme = jar.getJarEntry("docs/readme.txt");
                try (InputStream in = jar.getInputStream(readme)) {
                    System.out.println("jarfile-readme="
                            + new String(in.readAllBytes(),
                                    StandardCharsets.UTF_8));
                }

                Attributes perEntry =
                        meta.getAttributes("docs/readme.txt");
                System.out.println("jarfile-role="
                        + perEntry.getValue("X-Role"));

                System.out.println("jarfile-config="
                        + (jar.getJarEntry("config/app.properties") != null));
            }

            // CÁCH B: JarInputStream chỉ đọc lần lượt các entry.
            try (JarInputStream stream = new JarInputStream(
                    Files.newInputStream(path))) {
                Manifest meta = stream.getManifest();
                System.out.println("stream-main="
                        + meta.getMainAttributes().getValue(
                                Attributes.Name.MAIN_CLASS));

                List<String> names = new ArrayList<>();
                JarEntry entry;
                while ((entry = stream.getNextJarEntry()) != null) {
                    if (!entry.isDirectory()) {
                        names.add(entry.getName());
                        // Chỉ vì ví dụ có hai file rất nhỏ.
                        byte[] content = stream.readAllBytes();
                        if (entry.getName().equals("docs/readme.txt")) {
                            System.out.println("stream-readme="
                                    + new String(content,
                                            StandardCharsets.UTF_8));
                        }
                    }
                    stream.closeEntry();
                }

                Collections.sort(names); // không dựa vào thứ tự ZIP
                System.out.println("stream-files=" + names);
            }
        } finally {
            Files.deleteIfExists(path);
        }
    }
}
```

Lệnh biên dịch và chạy:

```bash
javac JarFileVsInputStreamDemo.java
java JarFileVsInputStreamDemo
```

**Stdout khi tạo/đọc file thành công (Java 17+):**

```text
jarfile-main=example.Main
jarfile-readme=HELLO
jarfile-role=documentation
jarfile-config=true
stream-main=example.Main
stream-readme=HELLO
stream-files=[config/app.properties, docs/readme.txt]
```

Điều gì xảy ra theo thứ tự?

1. `Manifest` được tạo bằng API chính thức; `Manifest-Version` là `1.0` và `Main-Class` là `example.Main`.
2. `manifest.getEntries()` có một section riêng cho `docs/readme.txt` với metadata `X-Role=documentation`.
3. `JarOutputStream` nhận manifest ngay khi khởi tạo và viết các entry cần thiết; sau đó chương trình thêm hai file nội dung nhỏ.
4. `JarFile` lấy manifest không phải duyệt lần lượt entry, rồi tra tên `docs/readme.txt` và đọc byte UTF-8. Nó cũng kiểm tra một entry khác có tồn tại không.
5. `JarInputStream` lấy manifest ban đầu, sau đó `getNextJarEntry()` tuần tự đọc các entry file; nó không cần/không cung cấp chức năng tra theo tên tức thì. Danh sách được sắp xếp **trước khi in** để không phụ thuộc thứ tự metadata/entry trong archive.
6. `JarInputStream.readAllBytes()` trong vòng lặp đọc **nội dung entry hiện tại**, không nuốt luôn toàn bộ những entry còn lại. Ví dụ chỉ chứa vài byte nên sử dụng `readAllBytes()` có thể chấp nhận; với JAR không tin cậy phải xử lý theo block và áp giới hạn.
7. Hai đối tượng đọc và các entry streams đều được đóng đúng cách trước khi xóa tệp tạm.

Việc JAR chứa `Main-Class: example.Main` trong bài **không** làm nó trở thành ứng dụng Java có thể chạy: JAR mẫu không chứa `example/Main.class`. Ví dụ kiểm tra **đọc metadata ở tầng I/O**, không kiểm thử `java -jar`.

## 9. Khi nguồn là mạng hoặc stream một lần

Ví dụ bạn nhận dữ liệu JAR qua một HTTP response body dạng `InputStream`, hoặc một file được giải nén từ một tầng khác:

```java
try (JarInputStream jar = new JarInputStream(responseBody)) {
    JarEntry entry;
    while ((entry = jar.getNextJarEntry()) != null) {
        if (!entry.isDirectory()) {
            // Xử lý byte nội dung entry hiện tại ở đây.
        }
        jar.closeEntry();
    }
}
```

Đoạn này **không độc lập**: `responseBody` là một `InputStream` do ứng dụng cung cấp, và cần xử lý `IOException`. Quan trọng:

- `JarInputStream` đọc tuần tự, phù hợp khi bạn không thể seek ngược hoặc không muốn lưu toàn bộ archive ra file trước.
- Đóng `JarInputStream` sẽ đóng luồng nguồn phía dưới. Nếu HTTP client còn cần stream cho mục đích khác, cần thiết kế quyền sở hữu rõ ràng.
- Chỉ vì có byte đến từ mạng không có nghĩa JAR đã nhận đủ. Nếu kết nối ngắt giữa chừng, code phải xử lý `IOException`, EOF bất thường, và kiểm tra integrity theo nhu cầu.
- Nếu muốn tìm nhanh một entry ở cuối archive nhiều lần, cân nhắc **ghi tạm có giới hạn dung lượng** rồi sử dụng `JarFile`; không sao chép toàn bộ input stream vào RAM vô hạn chỉ để mở lại.
- Manifest **có thể là `null`** dù archive là ZIP hợp lệ, đặc biệt khi không có manifest ở đầu luồng đúng vị trí.

Khi chuyển stream sang file tạm, tránh đặt niềm tin vào tên file do phía gửi cung cấp để tạo path truy cập ngoài thư mục cho phép; và giới hạn tổng byte nhận.

## 10. Metadata của `JarEntry`: cái gì đọc được và cái gì chưa chắc có?

`JarEntry` extends `ZipEntry`, nên có các trường:

| API | Ý nghĩa / lưu ý |
| --- | --- |
| `getName()` | Đường dẫn logic của entry bên trong archive |
| `isDirectory()` | True với directory entry (thường tên kết thúc bằng `/`) |
| `getSize()` | Kích thước giải nén nếu biết, có thể `-1` |
| `getCompressedSize()` | Kích thước dữ liệu nén nếu biết, có thể `-1` |
| `getCrc()` | CRC-32 nếu biết, có thể `-1` |
| `getMethod()` | Phương thức nén ZIP (thường `STORED` hoặc `DEFLATED`) |
| `getTime()` | Thời gian sửa đổi nếu có, chi tiết phụ thuộc metadata archive |
| `getComment()` | Comment entry nếu có |
| `getAttributes()` | Main? **Không**: đây là API của `Manifest`, không phải `JarEntry` |
| `getCertificates()` / `getCodeSigners()` | Metadata chữ ký sau khi xác thực nội dung đã đọc đầy đủ, có thể `null` |

Lưu ý đặc biệt: không có phương thức `JarEntry.getAttributes()` để trả về section manifest. Muốn metadata theo entry, dùng `Manifest.getAttributes(entry.getName())`; còn `getCertificates()/getCodeSigners()` liên quan đến chữ ký nếu JAR có ký và quá trình xác minh entry đã diễn ra.

Giá trị `size` hoặc `compressedSize` của entry là metadata archive, **không phải giới hạn an toàn tuyệt đối**. Khi stream đọc một archive không tin cậy, kích thước có thể chưa biết trước khi đọc xong, hoặc header không đủ để bảo vệ khỏi việc giải nén dữ liệu khổng lồ. Luôn đếm **byte giải nén thực tế** và giới hạn trong quá trình đọc.

## 11. Xác minh chữ ký JAR không đồng nghĩa tin tưởng nguồn phát

Java hỗ trợ JAR được ký và metadata liên quan tới chữ ký. Một số constructor của `JarFile` nhận flag `verify`; `JarInputStream` cũng có overload nhận `boolean verify`.

Điều quan trọng:

1. `verify=true` yêu cầu kiểm tra chữ ký khi nội dung được đọc theo những điều kiện có hỗ trợ, **không** có nghĩa toàn bộ archive đã được kiểm tra ngay lúc constructor trả về.
2. Với một entry đã ký, metadata `getCertificates()/getCodeSigners()` thường chỉ có sau khi **đọc hết nội dung entry và xác minh xong**.
3. Một JAR không có chữ ký có thể có `getCertificates()==null` hoặc `getCodeSigners()==null`, dù quá trình đọc thành công.
4. **Xác minh chữ ký/đối chiếu digest không tự xác nhận publisher được tin cậy**. Ứng dụng phải có chính sách tin cậy chứng thư, chuỗi chứng chỉ, hạn dùng và danh tính bên ký phù hợp, thay vì chỉ kiểm tra “có signers”.
5. Đối với `JarInputStream`, xử lý signed JAR còn phụ thuộc manifest đúng vị trí đầu và các entry chữ ký xuất hiện theo thứ tự phù hợp. Không suy diễn signed-JAR verification tùy ý như một bảo đảm dành cho mọi JAR bị đóng gói sai trật tự.
6. `JarFile` hỗ trợ việc xử lý chữ ký khi dùng đúng API; nhưng lỗi đọc, entry hỏng hoặc kiểm tra chữ ký thất bại phải được coi là lỗi, không được lặng lẽ bỏ qua.

Snippet kiểm tra một entry đã được đọc hết:

```java
try (JarFile jar = new JarFile(file, true)) {
    JarEntry entry = jar.getJarEntry("docs/readme.txt");
    if (entry == null) {
        throw new IOException("Entry not found");
    }

    try (InputStream in = jar.getInputStream(entry)) {
        in.transferTo(OutputStream.nullOutputStream());
    }

    // Nếu jar được ký phù hợp, chỉ khi đọc hết entry
    // mới có cơ sở xét signer/certificate metadata.
    var signers = entry.getCodeSigners();
    // signers == null không chứng minh JAR độc hại;
    // signers != null chưa chứng minh nguồn phát được tin cậy.
}
```

Đây là snippet **không độc lập**: `file` là `File`, cần import `JarFile`/`JarEntry`/`InputStream`/`OutputStream`/`IOException` và xử lý theo chính sách bảo mật. Đoạn mã không đưa ra kết luận trust và cũng không kiểm chứng chữ ký của mọi entry nếu chỉ đọc một entry.

Khi xử lý plug-in hoặc artifact tải từ nguồn không tin cậy, nên có một quy trình trust policy riêng (checksum/digest qua kênh đáng tin, chữ ký và chain validation, repository signing, sandbox, phân quyền). JarFile/JarInputStream chỉ là công cụ I/O và kiểm chứng theo hợp đồng API, không phải hệ thống quản lý trust hoàn chỉnh.

## 12. `Manifest` và multi-release JAR

Java 9+ hỗ trợ **multi-release JAR**, nơi có thể chứa các lớp/tài nguyên phiên bản:

```text
META-INF/MANIFEST.MF
com/example/Lib.class
META-INF/versions/9/com/example/Lib.class
META-INF/versions/17/com/example/Lib.class
```

Trong main attributes của manifest có thể có:

```text
Multi-Release: true
```

Điều này cho phép các cơ chế đọc phù hợp runtime chọn versioned entry trong điều kiện được API hỗ trợ. `JarFile` có các constructor/method hỗ trợ chọn version của multi-release archive (ví dụ overload có `Runtime.Version`) và cách nhìn các entry vật lý/logic có thể khác nhau theo cấu hình.

**Không** đồng nhất `JarInputStream` với một runtime class loader: nó duyệt **stream entry vật lý**, không tự hứa chọn entry theo phiên bản Java mà bạn cần. Khi chương trình chỉ muốn liệt kê archive bytes, cần quyết định mục tiêu là xem **entry được lưu vật lý** hay **view tương ứng version**. Dùng overload của `JarFile` theo tài liệu khi yêu cầu multi-release rõ ràng.

Trong ví dụ đầu bài, manifest không có `Multi-Release` nên không có vấn đề chọn phiên bản. Không nên thêm logic multi-release vào bài toán đơn giản chỉ đọc `docs/readme.txt` khi không cần.

## 13. Một số phương pháp liệt kê khác

### Duyệt với `JarFile.entries()`

```java
try (JarFile jar = new JarFile(path.toFile())) {
    var entries = jar.entries();
    while (entries.hasMoreElements()) {
        JarEntry entry = entries.nextElement();
        if (!entry.isDirectory()) {
            System.out.println(entry.getName());
        }
    }
}
```

Đây là snippet cần `Path path` và import; thứ tự liệt kê **không phải hợp đồng sắp xếp theo tên**. Nếu muốn output ổn định, gom danh sách các tên entry rồi `Collections.sort(...)` trước khi in.

### Duyệt bằng `JarInputStream` và giới hạn byte

```java
JarEntry entry;
while ((entry = jis.getNextJarEntry()) != null) {
    if (entry.isDirectory()) {
        jis.closeEntry();
        continue;
    }

    long bytesForThisEntry = 0;
    int count;
    byte[] chunk = new byte[8192];
    while ((count = jis.read(chunk)) != -1) {
        bytesForThisEntry += count;
        if (bytesForThisEntry > limitPerEntry) {
            throw new IOException("Entry too large");
        }
        // Xử lý chunk[0..count) một cách có giới hạn.
    }

    jis.closeEntry();
}
```

Đây là snippet, giả định `jis` và `limitPerEntry` đã khai báo. Với archive độc hại, vẫn cần giới hạn **tổng kích thước sau giải nén, số entry và thời gian**. Không chỉ dựa trên `getSize()`.

## 14. Đọc metadata không cần “extract” ra filesystem

Không phải nhu cầu nào cũng cần giải nén JAR thành nhiều file thật:

- Đọc `config/app.properties`: tra `JarEntry` hoặc duyệt stream, mở nội dung trong `InputStream` rồi truyền cho `Properties.load` nếu dữ liệu ở đúng định dạng.
- Đọc `docs/readme.txt`: lấy byte, chuyển sang text bằng charset cụ thể.
- Kiểm tra version build: đọc một thuộc tính main hoặc per-entry trong `Manifest`, nếu có.
- Liệt kê tài nguyên: duyệt danh sách tên entry, tránh tạo file tạm không cần thiết.
- Kiểm tra dấu hiệu entry có tồn tại: `JarFile.getJarEntry("...") != null`.

Nếu mục tiêu chỉ là tra cứu một tài nguyên đã biết trong một archive trên đĩa, `JarFile` thường đơn giản hơn giải nén toàn bộ. Nếu archive đến từ một luồng một lần, `JarInputStream` tránh bước ghi xuống file nhưng yêu cầu duyệt tuần tự.

### Đọc `Properties` từ entry

```java
try (JarFile jar = new JarFile(jarPath.toFile())) {
    JarEntry entry = jar.getJarEntry("config/app.properties");
    if (entry == null) {
        throw new IOException("Missing config entry");
    }

    Properties props = new Properties();
    try (InputStream in = jar.getInputStream(entry)) {
        props.load(in);
    }

    String mode = props.getProperty("mode");
}
```

Đây là snippet cần `jarPath` và các import. `Properties.load(InputStream)` dùng quy tắc định dạng properties riêng; không mặc định tương đương parser UTF-8 cho mọi ký tự trực tiếp trong file. Nếu dữ liệu được định nghĩa là UTF-8, dùng `Reader` với `StandardCharsets.UTF_8` để gọi `Properties.load(Reader)`.

Trong ví dụ `JarFileVsInputStreamDemo`, `config/app.properties` chỉ có ASCII `mode=demo`, nên không nảy sinh khác biệt encoding.

## 15. Không dùng tên entry chưa tin cậy để giải nén tùy tiện

Một JAR có thể chứa tên entry không an toàn, ví dụ:

```text
../outside.txt
../../etc/config
/absolute/path.txt
dir/../../escape.txt
```

Nếu chương trình chuyển `entry.getName()` thẳng thành `Path` dưới thư mục đích rồi ghi file, có nguy cơ **Zip Slip / path traversal**: file có thể được ghi bên ngoài thư mục mong muốn.

Cách bắt đầu kiểm tra:

```java
Path root = extractionDir.toAbsolutePath().normalize();
Path target = root.resolve(entry.getName()).normalize();

if (!target.startsWith(root)) {
    throw new IOException("Entry escapes extraction directory");
}
```

Đây là snippet, chưa phải phương pháp extract bảo mật hoàn chỉnh: `extractionDir` và `entry` cần khai báo. Kiểm tra thêm:

- Entry absolute path, directory traversal và tên không hợp lệ với OS.
- **Symbolic links** đã tồn tại trong thư mục đích có thể làm đường dẫn thực khác đường dẫn lexical. `normalize()` và `startsWith(root)` chưa bảo vệ đầy đủ khỏi symlink/race; nên extract trong thư mục mới có quyền phù hợp, có cơ chế kiểm tra/mở an toàn và chính sách cấm symlink khi cần.
- Giới hạn tổng byte sau giải nén, độ sâu path, số entry, thời gian, quota.
- Hai entry có cùng tên hoặc tên chuẩn hóa trùng nhau; không tự động ghi đè dữ liệu người dùng.
- Lỗi CRC, lỗi cấu trúc ZIP và các entry có khả năng gây tiêu tốn tài nguyên quá mức.
- Không khởi chạy code trong JAR vừa nhận chỉ vì metadata manifest ghi tên `Main-Class`.

Nếu chỉ cần đọc metadata/entry trong memory, không extract ra đĩa sẽ tránh một phần rủi ro path traversal, nhưng vẫn cần giới hạn tài nguyên khi giải nén.

## 16. Vòng đời tài nguyên và lỗi I/O

### Với `JarFile`

`JarFile` giữ tài nguyên liên quan đến file ZIP đã mở. Dùng `try-with-resources` để đóng `JarFile`. Các `InputStream` của entry cũng nên được đóng sau khi dùng. Đừng lưu một entry stream rồi đóng `JarFile` trước và kỳ vọng stream ấy đọc tiếp bình thường.

### Với `JarInputStream`

`JarInputStream` bọc `InputStream` nền. Đóng `JarInputStream` sẽ đóng stream nền theo cơ chế `FilterInputStream`, do đó chỉ trao quyền sở hữu stream nếu thực sự cho phép đóng.

Không trộn nhiều consumer đọc cùng `JarInputStream` trong các thread khác nhau mà không phối hợp: vị trí entry và trạng thái giải nén là tuần tự. Nếu muốn đọc hai entry độc lập, `JarFile` với các entry stream riêng biệt thường phù hợp hơn, nhưng vẫn cần quản lý lifetime `JarFile` và thread-safety của phần ứng dụng.

### Lỗi thường gặp

- `IOException`: lỗi đọc filesystem, EOF bất thường, archive bị hỏng hoặc provider từ chối thao tác.
- `ZipException` (subclass của `IOException`): cấu trúc ZIP không hợp lệ, CRC hoặc lỗi giải nén.
- `SecurityException` trong một số trường hợp xác minh signed JAR, quyền truy cập hoặc xử lý bảo mật.
- `NullPointerException` có thể xảy ra nếu bạn gọi `jar.getInputStream(jar.getJarEntry(name))` mà entry không tồn tại; hãy kiểm tra `null` trước.
- `jar.getManifest() == null` là trường hợp **bình thường** với JAR không có manifest; không được mặc định luôn tồn tại.
- `entry.isDirectory()` true nghĩa là entry mô tả thư mục; không cố giải mã nó thành text resource.
- `jarInput.getNextJarEntry() == null` mới là điều kiện hết các entry được duyệt, khác `read() == -1` đối với **entry hiện tại**.

Khi đọc archive từ nguồn bên ngoài, không coi một ngoại lệ là “file rỗng” rồi bỏ qua; phải xử lý lỗi phù hợp với mức độ an toàn của dữ liệu.

## 17. Ví dụ nhỏ khác: đọc `Manifest` từ JAR trong bộ nhớ

Nếu bạn chỉ có `byte[]` mô tả JAR (ví dụ do một API vừa tạo trong memory), `JarInputStream` làm việc trực tiếp với `ByteArrayInputStream`.

Lưu **`InMemoryJarDemo.java`**:

```java
import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.nio.charset.StandardCharsets;
import java.util.jar.Attributes;
import java.util.jar.JarEntry;
import java.util.jar.JarInputStream;
import java.util.jar.JarOutputStream;
import java.util.jar.Manifest;

public class InMemoryJarDemo {
    public static void main(String[] args) throws Exception {
        Manifest m = new Manifest();
        m.getMainAttributes().put(
                Attributes.Name.MANIFEST_VERSION, "1.0");
        m.getMainAttributes().putValue("X-Label", "memory-demo");

        ByteArrayOutputStream bytes = new ByteArrayOutputStream();
        try (JarOutputStream out = new JarOutputStream(bytes, m)) {
            out.putNextEntry(new JarEntry("hello.txt"));
            out.write("OK".getBytes(StandardCharsets.US_ASCII));
            out.closeEntry();
        }

        try (JarInputStream input = new JarInputStream(
                new ByteArrayInputStream(bytes.toByteArray()))) {
            Manifest manifest = input.getManifest();
            System.out.println("label="
                    + manifest.getMainAttributes().getValue("X-Label"));

            JarEntry entry = input.getNextJarEntry();
            System.out.println("entry=" + entry.getName());
            System.out.println("content="
                    + new String(input.readAllBytes(),
                            StandardCharsets.US_ASCII));
            input.closeEntry();

            System.out.println("next=" + input.getNextJarEntry());
        }
    }
}
```

Chạy:

```bash
javac InMemoryJarDemo.java
java InMemoryJarDemo
```

Stdout khi thành công:

```text
label=memory-demo
entry=hello.txt
content=OK
next=null
```

Ví dụ này **không cần file tạm**. `JarOutputStream(bytes, manifest)` đã ghi manifest theo vị trí đầu đúng quy tắc của `JarInputStream`, và chỉ có một entry nội dung do ứng dụng bổ sung. `getNextJarEntry()` sau khi đọc `hello.txt` trả `null` khi không còn entry nào. `ByteArrayOutputStream` không làm mất byte khi `close()`; tuy nhiên với JAR lớn, tạo `byte[]` cho toàn bộ archive sẽ tốn RAM, nên ưu tiên stream hoặc file theo yêu cầu.

## 18. Checklist lựa chọn và thực hành

Khi triển khai logic đọc JAR, tự hỏi theo thứ tự:

1. **Nguồn ở đâu?** Nếu là file, `JarFile` phù hợp cho tra cứu; nếu là stream một lần, `JarInputStream` phù hợp cho đọc tuần tự.
2. **Chỉ cần metadata hay byte nội dung?** Đọc `Manifest` nếu chỉ cần attributes; dùng entry `InputStream`/`JarInputStream.read` nếu cần payload.
3. **Manifest có bảo đảm đầu stream không?** Với `JarInputStream`, điều này quyết định khả năng nhận `getManifest()`.
4. **Có cần duyệt tất cả entry không?** Với `JarFile` có thể tra trực tiếp theo tên; stream tuần tự phải đi lần lượt.
5. **Có xử lý file không tin cậy không?** Giới hạn số entry, byte giải nén, dung lượng tạm và thời gian; kiểm soát đường dẫn khi extract.
6. **Có yêu cầu chữ ký không?** Đọc đủ entry để hoàn tất verification và có chính sách trust độc lập, không chỉ nhìn metadata `Main-Class`/`signers`.
7. **Có multi-release JAR không?** Xác định muốn đọc entry vật lý hay versioned view và chọn API/overload phù hợp.
8. **Ai đóng tài nguyên?** `try-with-resources` cho `JarFile`, từng entry stream và `JarInputStream`. Không đóng archive trong lúc code còn đọc entry.
9. **Charset là gì?** Byte trong entry không mặc định là UTF-8 hoặc văn bản; chỉ decode bằng charset khi định dạng quy định.
10. **Test những gì?** JAR có và không có manifest, manifest đầu/muộn, entry vắng mặt, directory entry, UTF-8 text, archive hỏng, entry nén lớn, null metadata và signed JAR nếu nghiệp vụ dùng chữ ký.

## 19. Bài tập tự kiểm tra

1. Vì sao `JarFile` có thể mở `config/app.properties` mà không cần đọc toàn bộ `docs/readme.txt` trước?
2. Khi đã dùng `JarInputStream`, API nào đưa con trỏ đến entry tiếp theo? API nào đọc byte của entry hiện tại?
3. Khi `JarInputStream.read()` trả `-1` ở một entry, có được kết luận cả archive đã hết không?
4. Tại sao `JarInputStream.getManifest()` có thể trả `null` dù archive có file `META-INF/MANIFEST.MF` nằm ở vị trí muộn?
5. `Manifest.getEntries()` có liệt kê tất cả `.class` và resource trong JAR không? Phải dùng API nào?
6. `Main-Class` có đủ để chứng minh JAR chạy được bằng `java -jar` không?
7. `Manifest.getAttributes("docs/readme.txt")` khác với `Manifest.getMainAttributes()` ở đâu?
8. Tại sao phải đóng `JarFile` sau khi đã đóng các `InputStream` cho entry?
9. Khi nhận một JAR 2 GB từ mạng, vì sao `Files.readAllBytes` hoặc `JarInputStream.readAllBytes` trên entry không có giới hạn có thể rủi ro?
10. `entry.getSize() == -1` nghĩa là gì? Có được tin tuyệt đối vào size do ZIP header cung cấp khi dữ liệu không tin cậy không?
11. Khi nào `JarEntry.getCodeSigners()` mới có thể mang dữ liệu chữ ký, và vì sao `signers != null` vẫn chưa xác nhận nguồn đáng tin?
12. `JarInputStream` có tự chọn entry `META-INF/versions/17` như class loader cho multi-release JAR không?
13. Nếu một ZIP entry có tên `../secrets.txt` và chương trình extract ra ổ đĩa, cần ngăn rủi ro gì? `Path.normalize()` đã đủ chống symlink chưa?
14. Hãy chạy hai chương trình thực hành, đối chiếu stdout và sửa `JarFileVsInputStreamDemo` để thêm entry `images/icon.bin`. Vì sao không nên ép decode một tệp ảnh thành text?
15. Nếu một ứng dụng chỉ kiểm tra tồn tại `META-INF/MANIFEST.MF` mà không kiểm tra `Manifest-Version` và định dạng manifest, những giả định nào có thể sai?

## 20. Tài liệu Java SE 17

- [`JarFile` — Java 17 API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/jar/JarFile.html): truy cập entry, manifest, đa phiên bản và chữ ký.
- [`JarInputStream` — Java 17 API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/jar/JarInputStream.html): đọc tuần tự, `getManifest()`, `getNextJarEntry()`.
- [`JarEntry` — Java 17 API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/jar/JarEntry.html): thông tin entry, certificate và code signer.
- [`Manifest` — Java 17 API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/jar/Manifest.html): main/per-entry attributes.
- [`JarOutputStream` — Java 17 API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/jar/JarOutputStream.html): tạo archive và thêm manifest.
- [`ZipFile` và `ZipInputStream` — Java 17 API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/zip/package-summary.html): nền tảng định dạng ZIP và semantics entry.

## 21. Ghi nhớ

**`JarFile`** mở JAR trên filesystem, tra cứu entry theo tên và cấp stream đọc từng entry; **`JarInputStream`** đọc tuần tự archive từ một `InputStream`. **`Manifest`** là metadata ở `META-INF/MANIFEST.MF` gồm main attributes và per-entry attributes, không phải danh sách mọi file.

Khi dùng `JarInputStream`, vị trí manifest **đầu archive** là điều kiện quan trọng để `getManifest()` hoạt động theo hợp đồng; manifest đã được nhận ở đầu sẽ không hiện lại như entry thông thường qua `getNextJarEntry()`. Luôn kiểm tra `null`, phân biệt EOF của entry với EOF của archive, giới hạn byte giải nén, đóng tài nguyên đúng thứ tự và không đồng nhất việc đọc manifest/chữ ký với thực thi hay tin tưởng nội dung JAR.
