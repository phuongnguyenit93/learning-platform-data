# ModuleReference và ModuleReader trong Java Platform Module System (JPMS)

## 1. Mục tiêu và vị trí trong module resolution

Trong JPMS (Java 9 trở lên), một module không chỉ có tên và các chỉ thị trong `module-info.java`. Hệ thống còn cần **tìm bản triển khai của module**, **đọc mô tả**, **giải quyết quan hệ phụ thuộc** và đôi khi **truy cập trực tiếp nội dung** bên trong module. Hai API ở gói `java.lang.module` phục vụ phần việc này:

- `ModuleReference`: đại diện cho một module **có thể quan sát/tìm thấy** từ một `ModuleFinder`, cùng với mô tả của module và thông tin vị trí (nếu có).
- `ModuleReader`: giao diện đọc tài nguyên của module được `ModuleReference` đại diện; ví dụ liệt kê tên tài nguyên, mở `InputStream` hoặc lấy `ByteBuffer` chứa nội dung.

Hai kiểu này rất hữu ích khi viết công cụ phân tích module, công cụ đóng gói, bộ kiểm tra nội dung, trình nạp module tùy chỉnh hoặc mã khám phá module. Chúng không thay thế bước resolution, không tự tạo `ModuleLayer` và không tự tải lớp vào JVM.

## 2. Vị trí của các API trong luồng xử lý

```text
Đường dẫn module / tập module hệ thống
             │
             ▼
       ModuleFinder
       find / findAll
             │
             ▼
      ModuleReference ── descriptor() ──► ModuleDescriptor
             │                              tên, requires, exports, ...
             │
             ├── open() ──► ModuleReader ──► tài nguyên (.class, cấu hình, ...)
             │
             ▼
Configuration.resolve(...) ──► Configuration ──► ResolvedModule
                                                  │
                                                  └── reference()
             │
             ▼
        ModuleLayer + ClassLoader (ở bước xây dựng layer)
```

Điểm cần phân biệt:

| Kiểu | Vai trò chính | Không đồng nghĩa với |
|---|---|---|
| `ModuleFinder` | Tìm các module quan sát được bằng tên | Danh sách các module đã được resolve |
| `ModuleReference` | Tham chiếu tới một bản module và descriptor của nó | `java.lang.Module` đang thuộc một layer |
| `ModuleDescriptor` | Mô tả khai báo: tên, `requires`, `exports`, `opens`, `uses`, `provides`, phiên bản... | Nội dung file của module |
| `Configuration` / `ResolvedModule` | Kết quả phân giải các module và quan hệ đọc | ClassLoader hoặc bytecode đã được load |
| `ModuleReader` | Truy cập các tài nguyên bên trong module | `ClassLoader`, `Class.forName` hay quyền truy cập theo `exports` |
| `java.lang.Module` | Đối tượng module ở runtime, thuộc một `ModuleLayer` | `ModuleReference` từ một finder |

Một module được `ModuleFinder` tìm thấy **chưa chắc đã được chọn** vào `Configuration` hiện tại. Ngược lại, từ `ResolvedModule` trong một configuration có thể lấy lại `ModuleReference` bằng `reference()`.

## 3. Hiểu và sử dụng ModuleReference

`ModuleReference` là lớp trừu tượng trong `java.lang.module`. Các thao tác công khai thường gặp:

| Phương thức | Kết quả và cách hiểu |
|---|---|
| `descriptor()` | Trả về `ModuleDescriptor`, cho biết tên và các đặc tính khai báo của module |
| `location()` | Trả về `Optional<URI>` chỉ vị trí module nếu provider công bố |
| `open()` | Mở `ModuleReader` để truy cập nội dung; có thể phát sinh `IOException` |

### 3.1. Lấy tham chiếu bằng ModuleFinder

```java
import java.lang.module.ModuleFinder;
import java.lang.module.ModuleReference;

public class FindSystemModule {
    public static void main(String[] args) {
        ModuleFinder finder = ModuleFinder.ofSystem();

        ModuleReference ref = finder.find("java.base")
                .orElseThrow(() -> new IllegalArgumentException(
                        "Không tìm thấy module java.base"));

        System.out.println("Tên: " + ref.descriptor().name());
        System.out.println("Các requires: " + ref.descriptor().requires());
        System.out.println("URI: " + ref.location()
                .map(Object::toString)
                .orElse("(không có URI)"));
    }
}
```

`ModuleFinder.ofSystem()` truy cập tập module hệ thống trong runtime image. Để tìm module từ một hoặc nhiều đường dẫn trên module path, dùng:

```java
import java.lang.module.ModuleFinder;
import java.lang.module.ModuleReference;
import java.nio.file.Path;

ModuleFinder finder = ModuleFinder.of(Path.of("mods"));
ModuleReference ref = finder.find("com.example.report")
        .orElseThrow(() -> new IllegalArgumentException(
                "Chưa thấy com.example.report trên module path"));

System.out.println(ref.descriptor());
```

Ví dụ thứ hai giả định thư mục `mods` chứa module tương ứng và được biên dịch/đóng gói đúng định dạng. Việc tìm thấy tham chiếu không có nghĩa module đã được resolve hoặc sẵn sàng cho `Class.forName`.

### 3.2. Vị trí module không nhất thiết là đường dẫn file

`location()` trả về `Optional<URI>`, không phải `Path`. URI có thể dùng sơ đồ `jrt:` cho module trong runtime image, `file:` cho một vị trí trên hệ thống file, hoặc không có giá trị. Vì vậy:

- Luôn xử lý trường hợp `Optional.empty()`.
- Không áp đặt rằng mọi URI đều có thể chuyển bằng `Path.of(uri)` hoặc đọc bằng `Files.readAllBytes(...)`.
- Khi cần truy cập nội dung theo cách độc lập với cách lưu trữ, ưu tiên `reference.open()` rồi dùng `ModuleReader`.

## 4. Hiểu và sử dụng ModuleReader

`ModuleReader` là interface kế thừa `Closeable`. Một reader đọc tài nguyên của **một** module cụ thể mà tham chiếu của nó đã mở.

| Phương thức | Mục đích |
|---|---|
| `find(String name)` | Trả về `Optional<URI>` cho tài nguyên mang tên tương đối trong module, nếu tìm được |
| `open(String name)` | Trả về `Optional<InputStream>` để đọc nội dung tài nguyên |
| `read(String name)` | Trả về `Optional<ByteBuffer>` chứa dữ liệu tài nguyên |
| `release(ByteBuffer bb)` | Giải phóng buffer đã được reader cấp qua `read` khi không cần dùng nữa |
| `list()` | Trả về `Stream<String>` gồm các tên tài nguyên trong module |
| `close()` | Đóng reader và tài nguyên liên quan |

Tên tài nguyên dùng dấu `/` làm dấu phân cách và được hiểu **tương đối với gốc module**, chẳng hạn:

- `java/lang/String.class`
- `com/example/report/ReportService.class`
- `config/app.properties`
- `META-INF/services/com.example.spi.Service`

Tên tài nguyên không phải là tên module, không phải tên nhị phân của lớp và không phải đường dẫn file tuyệt đối. Chẳng hạn `java.lang.String` là tên lớp, còn `java/lang/String.class` mới là tên tài nguyên tương ứng.

### 4.1. Ví dụ hoàn chỉnh: đọc module java.base

Chương trình sau chạy trực tiếp trên JDK 11+ mà không cần module riêng. Nó lấy tham chiếu từ configuration của boot layer, liệt kê một số tài nguyên và thử hai cách đọc file class.

```java
import java.io.IOException;
import java.io.InputStream;
import java.lang.module.ModuleReader;
import java.lang.module.ModuleReference;
import java.lang.module.ResolvedModule;
import java.net.URI;
import java.nio.ByteBuffer;
import java.util.Optional;
import java.util.stream.Stream;

public class ModuleContentDemo {
    public static void main(String[] args) throws IOException {
        ResolvedModule resolved = ModuleLayer.boot()
                .configuration()
                .findModule("java.base")
                .orElseThrow();

        ModuleReference ref = resolved.reference();

        System.out.println("Module: " + ref.descriptor().name());
        System.out.println("Location: " + ref.location()
                .map(URI::toString)
                .orElse("(không công bố URI)"));

        String resource = "java/lang/String.class";

        try (ModuleReader reader = ref.open()) {
            // Liệt kê một số tài nguyên trong package java.lang
            try (Stream<String> names = reader.list()) {
                names.filter(name -> name.startsWith("java/lang/"))
                        .limit(5)
                        .forEach(System.out::println);
            }

            // Cách 1: đọc qua InputStream, sau đó đóng stream
            try (InputStream input = reader.open(resource).orElseThrow()) {
                byte[] prefix = input.readNBytes(4);
                for (byte value : prefix) {
                    System.out.printf("%02X ", value & 0xFF);
                }
                System.out.println();
            }

            // Cách 2: đọc qua ByteBuffer, sau đó release đúng buffer
            Optional<ByteBuffer> maybeBuffer = reader.read(resource);
            if (maybeBuffer.isPresent()) {
                ByteBuffer buffer = maybeBuffer.get();
                try {
                    System.out.println("Byte còn lại: "
                            + buffer.remaining());
                } finally {
                    reader.release(buffer);
                }
            }

            // Lấy URI tài nguyên, nếu implementation hỗ trợ
            System.out.println("Resource URI: "
                    + reader.find(resource)
                            .map(URI::toString)
                            .orElse("(không tìm thấy)"));
        }
    }
}
```

Lưu thành `ModuleContentDemo.java` rồi chạy:

```bash
javac ModuleContentDemo.java
java ModuleContentDemo
```

Bốn byte đầu của một file class hợp lệ là `CA FE BA BE`. Thứ tự và số lượng tên tài nguyên được in ra phụ thuộc implementation và nội dung runtime; không dựa vào thứ tự của `list()` để xây dựng logic.

### 4.2. open() và read(): chọn cách nào?

- Dùng `open(name)` khi muốn xử lý dữ liệu theo luồng hoặc chuyển vào API nhận `InputStream`. Luôn đóng stream nhận được.
- Dùng `read(name)` khi cần thao tác trên `ByteBuffer`, ví dụ đọc header hoặc phân tích bytecode. Luôn gọi `release(buffer)` trong `finally` cho buffer được reader trả về.
- Dùng `find(name)` khi chỉ cần biết URI của một tài nguyên. URI có thể là URI đặc thù provider; không suy ra rằng tài nguyên là file thông thường.
- Dùng `list()` để khám phá tài nguyên. Với stream có tài nguyên đi kèm, nên đóng stream trong `try-with-resources`; đóng reader sau khi hoàn tất việc tiêu thụ stream.

Việc `release` không tương đương `close`: nó dành cho buffer do `read` cấp, còn `close` đóng toàn bộ reader. Không dùng buffer sau khi đã release.

## 5. Liên hệ trực tiếp với quá trình module resolution

Giả sử một module ứng dụng `com.example.report` đã nằm trên module path. Ta có thể đi từ quá trình resolution đến tham chiếu của module đó:

```java
import java.lang.module.Configuration;
import java.lang.module.ModuleFinder;
import java.lang.module.ModuleReference;
import java.nio.file.Path;
import java.util.Set;

ModuleFinder before = ModuleFinder.of(Path.of("mods"));
ModuleFinder after = ModuleFinder.of();

Configuration config = ModuleLayer.boot()
        .configuration()
        .resolve(before, after, Set.of("com.example.report"));

ModuleReference ref = config
        .findModule("com.example.report")
        .orElseThrow()
        .reference();

System.out.println("Module đã resolve: " + ref.descriptor().name());
```

Trong ví dụ:

1. `before` cung cấp những module có thể quan sát từ `mods`; `after` là finder bổ sung rỗng.
2. `resolve(...)` chọn các module cần thiết để thỏa mãn quan hệ phụ thuộc từ root `com.example.report` và tạo một `Configuration` mới.
3. `findModule(...)` ở `Configuration` trả về `ResolvedModule`; `reference()` dẫn về `ModuleReference` đã được chọn.
4. Nếu muốn truy cập file bên trong module đó, gọi `ref.open()` để lấy reader.
5. Nếu muốn **thực thi lớp** thuộc module đó, vẫn cần xây dựng `ModuleLayer` với cơ chế định nghĩa module/class loader phù hợp. Chỉ có `Configuration` hay `ModuleReader` là chưa đủ.

Phân biệt hai cách tìm là quan trọng: `finder.find(name)` trả về module quan sát được trên một nguồn; `configuration.findModule(name)` trả về module **đã được chọn trong kết quả resolution**.

## 6. Các tình huống sử dụng thực tế

### 6.1. Công cụ kiểm kê module

Dùng `ModuleFinder.ofSystem().findAll()` hoặc `ModuleFinder.of(path).findAll()` để liệt kê tham chiếu và lấy `descriptor()`. Có thể tổng hợp tên module, các `requires`, `exports`, `opens` và các service được công bố mà chưa cần load lớp.

### 6.2. Công cụ kiểm tra thành phần đóng gói

Mở `ModuleReader` để tìm tài nguyên cấu hình hoặc class mong đợi:

```java
import java.io.IOException;
import java.lang.module.ModuleReader;
import java.lang.module.ModuleReference;

static boolean hasResource(ModuleReference ref, String name)
        throws IOException {
    try (ModuleReader reader = ref.open()) {
        return reader.find(name).isPresent();
    }
}
```

Giá trị trả về chỉ phản ánh tài nguyên được reader tìm thấy. Nó không khẳng định lớp có thể khởi tạo, module có được yêu cầu từ module khác hay service provider có thể chạy thành công.

### 6.3. Phân tích bytecode

Một công cụ có thể đọc `*.class` bằng `open` hoặc `read` rồi chuyển byte vào thư viện phân tích class file. `ModuleReader` cung cấp byte thô; việc diễn giải constant pool, methods và annotations thuộc trách nhiệm thư viện phân tích.

### 6.4. Khám phá tài nguyên của module chưa được resolve

Có thể lấy `ModuleReference` trực tiếp từ một finder và mở reader của nó, ngay cả trước khi thêm module vào configuration. Điều này phù hợp cho công cụ khảo sát cấu trúc module. Tuy nhiên, đọc được tài nguyên không bảo đảm mọi dependency của module đó hợp lệ.

## 7. Quản lý tài nguyên, lỗi và giới hạn

| Tình huống | Cách xử lý |
|---|---|
| `finder.find(name)` trả về rỗng | Kiểm tra tên module và module path; không dùng `get()` khi chưa kiểm tra |
| `configuration.findModule(name)` trả về rỗng | Module chưa nằm trong configuration đang xét; phân biệt với kết quả của finder |
| `reader.open/read/find(name)` trả về rỗng | Tài nguyên không tồn tại với tên đã cung cấp hoặc provider không tìm được |
| `ModuleReference.open()` hay thao tác reader ném `IOException` | Xử lý ngoại lệ I/O theo ngữ cảnh; đóng reader bằng `try-with-resources` |
| `reader.list()` trả về stream | Tiêu thụ khi reader còn mở; đóng stream trước reader |
| `reader.read(name)` thành công | Gọi `reader.release(buffer)` trong `finally` khi dùng xong |
| `location()` rỗng hoặc có URI không phải `file:` | Không suy luận đường dẫn thật; dùng reader để truy cập nội dung |
| Lỗi phân giải phụ thuộc như module không tìm thấy hoặc graph không hợp lệ | Xử lý trong bước resolution; `ModuleReader` không giải quyết dependency |
| Module có package không `exports` | Đọc byte bằng reader không cấp quyền truy cập Java code vào package đó |

Ngoài ra:

- Reader không được chia sẻ hoặc dùng đồng thời một cách tùy tiện; tuân thủ hợp đồng và giới hạn của provider cụ thể.
- Không giữ `InputStream` hoặc `ByteBuffer` của reader lâu hơn vòng đời cần thiết.
- Không giả định thứ tự của `list()`, tên đường dẫn phụ thuộc hệ điều hành hay khả năng biến URI thành `Path`.
- Khi làm việc với module path do bên ngoài cung cấp, cần xử lý dữ liệu bytecode/tài nguyên như dữ liệu đầu vào không đáng tin cậy.
- Dùng `ModuleReader` để kiểm tra nội dung không có nghĩa bỏ qua các quy tắc `requires`, `exports` và `opens` khi Java thực sự liên kết lớp hoặc sử dụng reflection.

## 8. Câu hỏi thường gặp

**ModuleReference khác java.lang.Module ở điểm nào?**

`ModuleReference` đại diện cho một module được finder xác định và cung cấp cách đọc nội dung. `java.lang.Module` đại diện cho module ở runtime, gắn với một module layer. Không thể gọi `reference.open()` rồi coi đó là tạo xong module runtime.

**Có thể lấy ModuleReference từ một module đã resolve không?**

Có. Lấy `ResolvedModule` từ `Configuration.findModule(name)`, rồi gọi `reference()`. Ví dụ với boot layer: `ModuleLayer.boot().configuration().findModule("java.base").orElseThrow().reference()`.

**ModuleReader có tải class giống ClassLoader không?**

Không. `open` và `read` cung cấp dữ liệu của tài nguyên, có thể là bytecode `.class`, nhưng không thực hiện định nghĩa lớp, liên kết, khởi tạo hay quản lý quyền truy cập giữa các module.

**Tại sao không dùng Files hoặc JarFile để đọc module?**

Cách đó có thể thích hợp cho một loại đóng gói cụ thể. `ModuleReader` cung cấp giao diện chung cho module trong runtime image và những module do provider khác cung cấp, giúp công cụ ít phụ thuộc định dạng lưu trữ hơn.

**Khi nào nên đọc ModuleDescriptor mà không mở ModuleReader?**

Khi chỉ cần metadata như tên, yêu cầu phụ thuộc, các package được exports/opens và dịch vụ sử dụng/cung cấp. Chỉ mở reader khi thực sự cần danh sách hoặc nội dung tài nguyên.

## 9. Ghi nhớ

`ModuleFinder` **tìm** module; `ModuleReference` **đại diện** cho bản module được tìm thấy và cho truy cập `ModuleDescriptor`; resolution tạo `Configuration` chứa `ResolvedModule`; `ModuleReader` **đọc tài nguyên** được tham chiếu; còn `ModuleLayer` và class loader là các thành phần đưa module vào môi trường runtime. Phân biệt các vai trò này giúp dùng JPMS đúng tầng trách nhiệm và tránh nhầm giữa việc tìm thấy module, giải quyết phụ thuộc, đọc bytecode và thực thi lớp.
