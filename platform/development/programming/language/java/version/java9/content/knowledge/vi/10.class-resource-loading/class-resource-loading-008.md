# Duyệt nội dung mô-đun bằng `ModuleReader`

## Mục tiêu

Java Platform Module System (JPMS) cung cấp `java.lang.module.ModuleReader` để đọc nội dung của một mô-đun đã được tìm thấy. API này cho phép ứng dụng liệt kê tài nguyên, tìm URI của tài nguyên, mở luồng đọc hoặc lấy nội dung dưới dạng `ByteBuffer` mà không cần tự giải nén JAR hay giả định mô-đun nằm trên hệ thống tệp.

`ModuleReader` thường được dùng cùng `ModuleFinder` và `ModuleReference`: finder tìm mô-đun, reference đại diện cho mô-đun đó, rồi `ModuleReference.open()` mở reader để duyệt nội dung. Đây là API mức thấp để làm việc với nội dung mô-đun; nó không thay thế class loader và không tự nạp hay khởi tạo lớp.

## 1. Vị trí của ModuleReader trong JPMS

Luồng làm việc phổ biến:

```text
ModuleFinder
    │ tìm theo module path
    ▼
ModuleReference
    │ open()
    ▼
ModuleReader
    ├── list()   → liệt kê tên tài nguyên
    ├── find()   → tìm URI của tài nguyên
    ├── open()   → mở InputStream
    └── read()   → đọc ByteBuffer
```

- `ModuleFinder` tìm mô-đun trong các vị trí như thư mục module path, exploded module hoặc modular JAR.
- `ModuleReference` giữ descriptor và thông tin tham chiếu đến mô-đun tìm được.
- `ModuleReader` cung cấp thao tác đọc nội dung mô-đun và phải được đóng sau khi dùng.

Ví dụ lấy reader:

```java
ModuleReference reference = ModuleFinder.of(Path.of("mods"))
        .find("com.example.assets")
        .orElseThrow();

try (ModuleReader reader = reference.open()) {
    // Duyệt nội dung mô-đun tại đây.
}
```

`ModuleReference.open()` có thể ném `IOException`. Dùng try-with-resources để bảo đảm reader được đóng kể cả khi thao tác đọc phát sinh lỗi.

## 2. Các phương thức chính

| Phương thức | Kết quả | Mục đích |
|---|---|---|
| `list()` | `Stream<String>` | Liệt kê tên các tài nguyên trong mô-đun |
| `find(String name)` | `Optional<URI>` | Tìm URI của một tài nguyên nếu có |
| `open(String name)` | `Optional<InputStream>` | Mở luồng đọc tài nguyên |
| `read(String name)` | `Optional<ByteBuffer>` | Đọc tài nguyên vào buffer |
| `release(ByteBuffer buffer)` | `void` | Giải phóng buffer đã nhận từ `read()` |
| `close()` | `void` | Đóng reader và giải phóng tài nguyên liên quan |

Tên tài nguyên thường là đường dẫn tương đối, dùng dấu `/` làm dấu phân cách, ví dụ `com/example/assets/config/message.txt`. Không thêm dấu `/` ở đầu tên. Tên tài nguyên không hợp lệ có thể khiến phương thức ném `IllegalArgumentException`.

### `list()` — duyệt tên tài nguyên

`list()` trả về một `Stream<String>` chứa tên các tài nguyên trong mô-đun. Kết quả có thể bao gồm file `.class`, file cấu hình, tài nguyên đóng gói và các mục thư mục tùy cách lưu trữ của module reader. Không giả định thứ tự kết quả; nếu cần thứ tự ổn định, hãy sắp xếp.

Stream có thể giữ tài nguyên của reader, vì vậy nên đóng stream bằng try-with-resources:

```java
try (var names = reader.list()) {
    names.filter(name -> name.endsWith(".txt"))
            .sorted()
            .forEach(System.out::println);
}
```

Không giữ stream để dùng sau khi reader đã đóng. Khi chỉ cần kiểm tra một tên cụ thể, có thể dùng `anyMatch` rồi đóng stream ngay.

### `find()` — lấy URI

`find(name)` trả về `Optional<URI>` nếu reader có thể xác định vị trí của tài nguyên. URI có thể hữu ích để ghi log, chẩn đoán hoặc chuyển cho API phù hợp.

```java
Optional<URI> uri = reader.find("com/example/assets/config/message.txt");
System.out.println("uriPresent=" + uri.isPresent());
```

Không giả định URI luôn dùng scheme `file:` hoặc có thể chuyển trực tiếp thành `Path`. Với tài nguyên nằm trong modular JAR, URI có thể biểu diễn vị trí bên trong JAR. Nếu mục tiêu là đọc nội dung, ưu tiên `open()` hoặc `read()` của chính `ModuleReader`.

### `open()` — đọc bằng InputStream

`open(name)` trả về `Optional<InputStream>`. Cách này phù hợp khi muốn đọc tuần tự, xử lý dữ liệu dạng luồng hoặc giải mã văn bản bằng charset xác định.

```java
try (InputStream input = reader.open(resourceName).orElseThrow()) {
    String text = new String(input.readAllBytes(), StandardCharsets.UTF_8);
    System.out.println(text);
}
```

Đóng `InputStream` sau khi đọc. Nếu tài nguyên không tồn tại, kết quả là `Optional.empty()`; xử lý trường hợp đó trước khi gọi `orElseThrow()` trong ứng dụng thực tế.

### `read()` và `release()` — đọc bằng ByteBuffer

`read(name)` trả về `Optional<ByteBuffer>`. Cách này hữu ích khi API tiếp theo nhận `ByteBuffer` hoặc khi cần thao tác byte trực tiếp.

```java
ByteBuffer buffer = reader.read(resourceName).orElseThrow();
try {
    byte[] bytes = new byte[buffer.remaining()];
    buffer.get(bytes);
    System.out.println(new String(bytes, StandardCharsets.UTF_8));
} finally {
    reader.release(buffer);
}
```

**Phải gọi `release(buffer)` cho buffer do `read()` trả về**, kể cả khi quá trình xử lý buffer gặp lỗi. Một implementation có thể dùng bộ nhớ hoặc tài nguyên đặc thù; không giữ buffer sau khi đã release. Nếu cần dữ liệu lâu hơn, hãy sao chép sang cấu trúc do ứng dụng sở hữu như `byte[]` hoặc một buffer riêng.

`open()` và `read()` đều trả `Optional` vì tài nguyên có thể không tồn tại. `read()` không có nghĩa là nội dung chắc chắn được lưu trong heap; hãy xử lý buffer theo hợp đồng của API và gọi `release()` đúng cách.

## 3. Ví dụ hoàn chỉnh: đọc tài nguyên trong modular JAR

Ví dụ tạo một mô-đun `com.example.assets` có file văn bản đi kèm, đóng gói mô-đun thành JAR rồi dùng mô-đun `com.example.reader` để tìm và đọc tài nguyên qua `ModuleReader`.

Cấu trúc thư mục:

```text
project/
├── src/
│   ├── com.example.assets/
│   │   ├── module-info.java
│   │   ├── com/example/assets/AssetMarker.java
│   │   └── com/example/assets/config/message.txt
│   └── com.example.reader/
│       ├── module-info.java
│       └── com/example/reader/Main.java
├── out/
└── mods/
    └── com.example.assets.jar
```

### Mô-đun chứa tài nguyên

**`src/com.example.assets/module-info.java`**

```java
module com.example.assets {
    exports com.example.assets;
}
```

**`src/com.example.assets/com/example/assets/AssetMarker.java`**

```java
package com.example.assets;

public final class AssetMarker {
    private AssetMarker() {}
}
```

**`src/com.example.assets/com/example/assets/config/message.txt`**

```text
ModuleReader resource sample
Line two
```

### Mô-đun đọc tài nguyên

**`src/com.example.reader/module-info.java`**

```java
module com.example.reader {
}
```

Ứng dụng reader không cần khai báo `requires com.example.assets` vì nó không gọi lớp Java của mô-đun assets. Nó khám phá mô-đun bằng `ModuleFinder`, sau đó đọc nội dung qua `ModuleReader`.

**`src/com.example.reader/com/example/reader/Main.java`**

```java
package com.example.reader;

import java.io.InputStream;
import java.lang.module.ModuleFinder;
import java.lang.module.ModuleReader;
import java.lang.module.ModuleReference;
import java.nio.ByteBuffer;
import java.nio.charset.StandardCharsets;
import java.nio.file.Path;

public class Main {
    public static void main(String[] args) throws Exception {
        if (args.length != 1) {
            System.err.println("Usage: Main <module-path>");
            return;
        }

        ModuleReference reference = ModuleFinder.of(Path.of(args[0]))
                .find("com.example.assets")
                .orElseThrow();
        String resource = "com/example/assets/config/message.txt";

        try (ModuleReader reader = reference.open()) {
            try (var names = reader.list()) {
                boolean listed = names.anyMatch(resource::equals);
                System.out.println("listed=" + listed);
            }

            System.out.println("uriPresent=" + reader.find(resource).isPresent());
            System.out.println("missingPresent="
                    + reader.find("com/example/assets/config/missing.txt").isPresent());

            try (InputStream input = reader.open(resource).orElseThrow()) {
                String text = new String(input.readAllBytes(), StandardCharsets.UTF_8)
                        .trim().replace("\n", "|");
                System.out.println("open=" + text);
            }

            ByteBuffer buffer = reader.read(resource).orElseThrow();
            try {
                byte[] bytes = new byte[buffer.remaining()];
                buffer.get(bytes);
                String text = new String(bytes, StandardCharsets.UTF_8)
                        .trim().replace("\n", "|");
                System.out.println("read=" + text);
            } finally {
                reader.release(buffer);
            }
        }
    }
}
```

### Biên dịch và đóng gói

Chạy từ thư mục `project` trong Windows PowerShell:

```powershell
New-Item -ItemType Directory -Force out, mods
javac --module-source-path src -d out -m com.example.assets,com.example.reader
New-Item -ItemType Directory -Force out/com.example.assets/com/example/assets/config
Copy-Item src/com.example.assets/com/example/assets/config/message.txt out/com.example.assets/com/example/assets/config/message.txt
jar --create --file mods/com.example.assets.jar -C out/com.example.assets .
```

`javac` biên dịch mã Java nhưng không tự sao chép mọi file tài nguyên tùy ý từ source tree sang output. Vì vậy, ví dụ sao chép `message.txt` vào exploded module trước khi đóng gói JAR. Maven, Gradle hoặc quy trình build tương đương thường có bước xử lý resource riêng.

Trên Linux hoặc macOS, có thể tạo thư mục bằng `mkdir -p out mods out/com.example.assets/com/example/assets/config`; thay `Copy-Item` bằng `cp src/com.example.assets/com/example/assets/config/message.txt out/com.example.assets/com/example/assets/config/message.txt`. Các lệnh `javac` và `jar` giữ nguyên.

### Chạy với modular JAR

```powershell
java --module-path out -m com.example.reader/com.example.reader.Main mods
```

Stdout trên JDK 24.0.2:

```text
listed=true
uriPresent=true
missingPresent=false
open=ModuleReader resource sample|Line two
read=ModuleReader resource sample|Line two
```

Để thử với exploded module thay cho JAR:

```powershell
java --module-path out -m com.example.reader/com.example.reader.Main out/com.example.assets
```

Reader vẫn tìm và đọc được cùng tài nguyên. Như vậy, cùng một API có thể làm việc với nội dung mô-đun đã đóng gói trong modular JAR hoặc thư mục exploded module.

## 4. Xử lý tài nguyên không tồn tại và lỗi I/O

Không nên mặc định mọi tên tài nguyên đều có mặt. Các phương thức `find`, `open` và `read` trả `Optional.empty()` khi không tìm được tài nguyên. Có thể kiểm tra trước:

```java
Optional<URI> location = reader.find(resourceName);
if (location.isEmpty()) {
    System.out.println("Resource not found: " + resourceName);
}
```

Trong ứng dụng thực tế, hãy phân biệt:

- **Không tìm thấy:** `Optional.empty()`; đây có thể là trường hợp bình thường nếu tài nguyên là tùy chọn.
- **Không đọc được:** `IOException` có thể xảy ra khi mở reader, mở stream hoặc đọc nội dung.
- **Tên không hợp lệ:** có thể phát sinh `IllegalArgumentException`.
- **Reader đã đóng:** không tiếp tục dùng reader sau khi đóng; hoàn tất mọi thao tác trước khi thoát khỏi try-with-resources.

Đừng bắt mọi exception rồi trả về chuỗi rỗng. Nếu tài nguyên bắt buộc, hãy báo lỗi có tên mô-đun và tên tài nguyên để chẩn đoán chính xác.

## 5. ModuleReader và cách nạp tài nguyên thông thường

`ModuleReader` không phải lựa chọn duy nhất để đọc resource. Nếu mã ứng dụng đã có một lớp thuộc mô-đun và chỉ cần resource liên quan đến lớp đó, các API quen thuộc như `Class.getResourceAsStream()` hoặc `ClassLoader.getResourceAsStream()` thường đơn giản hơn.

`ModuleReader` phù hợp hơn khi ứng dụng cần làm việc với **nội dung mô-đun được khám phá theo tên hoặc đường dẫn**, trước khi nạp lớp của mô-đun đó. Ví dụ:

- trình kiểm tra hoặc công cụ phân tích modular JAR;
- bộ cài đặt/plugin manager cần liệt kê metadata và tài nguyên trước khi kích hoạt plugin;
- công cụ chẩn đoán nội dung module path;
- hệ thống build hoặc triển khai cần kiểm tra resource đã được đóng gói.

Không nên dùng `ModuleReader` chỉ để thay thế `Class.getResourceAsStream()` trong mã nghiệp vụ thông thường nếu ứng dụng đã biết lớp sở hữu tài nguyên.

## 6. Vòng đời và quản lý tài nguyên

Quy tắc an toàn:

1. Tìm `ModuleReference` bằng `ModuleFinder`.
2. Mở `ModuleReader` bằng `reference.open()` trong try-with-resources.
3. Đóng stream trả về từ `reader.open()` sau khi đọc.
4. Đóng stream trả về từ `reader.list()` sau khi duyệt.
5. Gọi `reader.release(buffer)` trong `finally` cho mọi buffer nhận từ `reader.read()`.
6. Không dùng reader hoặc các stream/buffer liên quan sau khi đã đóng hoặc release.

`ModuleReader` là abstraction về nội dung mô-đun; không tự chuyển URI thành đường dẫn tệp và không yêu cầu ứng dụng giải nén modular JAR. Dùng các phương thức của reader giúp code không phụ thuộc vào cách module được lưu trữ.

## 7. Những nhầm lẫn cần tránh

- **Nhầm `ModuleReader` với class loader:** reader đọc nội dung; class loader chịu trách nhiệm nạp lớp vào JVM.
- **Cho rằng `find()` đã đọc nội dung:** `find()` chỉ trả URI nếu xác định được vị trí. Dùng `open()` hoặc `read()` để lấy byte.
- **Giả định URI luôn là file URI:** tài nguyên có thể nằm bên trong modular JAR. Không luôn dùng `Path.of(uri)` hoặc `Files.readAllBytes`.
- **Quên đóng `ModuleReader`:** có thể giữ file handle hoặc tài nguyên của provider.
- **Quên đóng stream từ `list()`:** stream có thể giữ tài nguyên cho đến khi đóng.
- **Quên `release()` sau `read()`:** implementation có thể quản lý buffer bằng tài nguyên cần được trả lại.
- **Giả định `javac` sao chép file resource:** cần cấu hình bước resource của build tool hoặc sao chép vào exploded module trước khi đóng gói.
- **Xem `Optional.empty()` là lỗi I/O:** không tìm thấy tài nguyên khác với việc đọc tài nguyên thất bại do `IOException`.
- **Xem ModuleReader là cơ chế sandbox:** đọc nội dung mô-đun không tạo ranh giới bảo mật hay giới hạn quyền thực thi của mã.

## 8. Checklist khi duyệt nội dung mô-đun

- [ ] Đã tìm đúng module bằng `ModuleFinder` và xác minh tên trong descriptor.
- [ ] Đã mở reader bằng `ModuleReference.open()`.
- [ ] Tên resource dùng đường dẫn tương đối với dấu `/` và không có dấu `/` đầu.
- [ ] Đã đóng stream từ `list()` và `open()`.
- [ ] Đã gọi `release()` cho mọi `ByteBuffer` trả về từ `read()`.
- [ ] Đã xử lý `Optional.empty()` cho resource không tồn tại.
- [ ] Đã xử lý `IOException` và tên tài nguyên không hợp lệ.
- [ ] Không giả định URI là đường dẫn file thông thường.
- [ ] Đã xác minh tài nguyên thực sự được đóng gói trong modular JAR hoặc exploded module.

## Tài liệu tham khảo

1. [Java SE 25 API — ModuleReader](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/module/ModuleReader.html), `list`, `find`, `open`, `read`, `release` và `close`.
2. [Java SE 25 API — ModuleReference](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/module/ModuleReference.html), cách mở `ModuleReader` từ module reference.
3. [Java SE 25 API — ModuleFinder](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/module/ModuleFinder.html), tìm mô-đun từ module path.
4. [Java SE 25 API — ModuleDescriptor](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/module/ModuleDescriptor.html), thông tin descriptor của mô-đun.
5. [The javac Command — Java SE 25](https://docs.oracle.com/en/java/javase/25/docs/specs/man/javac.html) và [The jar Command — Java SE 25](https://docs.oracle.com/en/java/javase/25/docs/specs/man/jar.html), biên dịch mô-đun và đóng gói modular JAR.