# ModuleFinder và custom module source

## Mục tiêu

Sau bài này, bạn có thể:

- Giải thích vai trò của **ModuleFinder** trong Java Platform Module System (JPMS).
- Phân biệt **ModuleFinder**, **ModuleReference** và **ModuleReader**.
- Tìm module từ module path và runtime image bằng các finder có sẵn.
- Kết hợp nhiều nguồn module bằng **ModuleFinder.compose**.
- Tạo module source tùy chỉnh trong bộ nhớ bằng cách triển khai finder, reference và reader.
- Đưa module tìm được vào quá trình resolve và tạo **ModuleLayer**.

## 1. Vì sao cần ModuleFinder?

Trong JPMS, một module không chỉ là thư mục chứa class. Nó có tên, descriptor và tập package, dependency, API được khai báo. Khi JVM hoặc ứng dụng tạo một module layer bằng API, nó cần biết:

1. Module nào có thể được tìm thấy?
2. Descriptor của từng module mô tả điều gì?
3. Bytecode và resource của module nằm ở đâu, và có thể đọc bằng cách nào?

**ModuleFinder** giải quyết câu hỏi đầu tiên và cung cấp tham chiếu đến module. Hai abstraction tiếp theo hoàn thiện đường đi đến nội dung:

- **ModuleReference** đại diện cho một module đã được tìm thấy. Nó giữ **ModuleDescriptor** và vị trí tùy chọn của module.
- **ModuleReader** mở và đọc các entry bên trong module, chẳng hạn file .class và resource.

Luồng tổng quát:

~~~text
Configuration.resolve(...)
          |
          v
     ModuleFinder
       find(name)
       findAll()
          |
          v
    ModuleReference
    descriptor()
    location()
    open()
          |
          v
      ModuleReader
   find / open / read / list
          |
          v
  class bytes và resources
~~~

**ModuleFinder không biên dịch file .java, không tự tạo class loader và cũng không tạo module layer.** Nó là nguồn thông tin để bộ resolver tìm module. Việc resolve dependency và định nghĩa module thuộc **Configuration** và **ModuleLayer**.

## 2. Ba abstraction cần phân biệt

### 2.1. ModuleFinder — tìm module

**ModuleFinder** là interface có hai thao tác chính:

~~~java
Optional<ModuleReference> find(String name);
Set<ModuleReference> findAll();
~~~

- **find(name)** trả về tham chiếu của module có tên tương ứng, hoặc **Optional.empty()** nếu nguồn này không có module đó.
- **findAll()** trả về các module mà finder cung cấp.

Một finder có thể đại diện cho module path, runtime image, kho lưu trữ riêng, bộ nhớ, database hoặc một nguồn tùy chỉnh khác.

### 2.2. ModuleReference — mô tả một module cụ thể

**ModuleReference** là abstract class đại diện cho một module đã tìm thấy. Nó cung cấp:

- **descriptor()** — **ModuleDescriptor** mô tả tên module, dependency, package, exports, opens, services và các thuộc tính liên quan.
- **location()** — vị trí module dưới dạng **URI** tùy chọn. Nguồn module trong bộ nhớ hoặc nguồn đặc biệt có thể không có vị trí file thông thường.
- **open()** — mở một **ModuleReader** để truy cập nội dung module.

Một ModuleReference là cầu nối giữa metadata của module và cơ chế đọc nội dung của nguồn đó.

### 2.3. ModuleReader — đọc nội dung module

**ModuleReader** là interface dùng để truy cập các entry trong module:

| API | Ý nghĩa |
|---|---|
| **find(name)** | Tìm URI của một entry nếu có thể định vị |
| **open(name)** | Mở entry dưới dạng InputStream |
| **read(name)** | Đọc entry dưới dạng ByteBuffer |
| **release(buffer)** | Trả lại buffer được cấp bởi read khi implementation cần giải phóng tài nguyên |
| **list()** | Liệt kê tên các entry |
| **close()** | Đóng reader và giải phóng tài nguyên |

Tên entry là đường dẫn tương đối bên trong module, dùng dấu /, ví dụ **com/acme/app/Main.class** hoặc **config/default.yml**. Không thêm dấu / ở đầu.

**open** và **read** trả về Optional.empty() khi entry không tồn tại. Khi reader đã đóng, implementation không nên tiếp tục cho phép đọc dữ liệu.

## 3. Dùng ModuleFinder có sẵn

Trong phần lớn ứng dụng, bạn không cần tự triển khai finder. JDK đã cung cấp các factory method phổ biến.

### 3.1. Tìm module trên module path

**ModuleFinder.of(Path...)** tạo finder từ một hoặc nhiều đường dẫn chứa module, ví dụ modular JAR hoặc exploded module.

~~~java
import java.lang.module.ModuleDescriptor;
import java.lang.module.ModuleFinder;
import java.lang.module.ModuleReference;
import java.nio.file.Path;

public class InspectModule {
    public static void main(String[] args) {
        ModuleFinder finder = ModuleFinder.of(Path.of("build/modules"));

        ModuleReference reference = finder
                .find("com.acme.orders")
                .orElseThrow(() ->
                        new IllegalArgumentException("Module not found"));

        ModuleDescriptor descriptor = reference.descriptor();

        System.out.println("Name: " + descriptor.name());
        System.out.println("Location: " + reference.location().orElse(null));

        descriptor.requires().forEach(requirement ->
                System.out.println("Requires: " + requirement.name()));
    }
}
~~~

Ví dụ trên chỉ đọc metadata. Nó chưa resolve dependency và chưa định nghĩa module trong một layer.

### 3.2. Tìm module trong runtime image

**ModuleFinder.ofSystem()** tạo finder cho các module thuộc runtime image của JDK hiện tại.

~~~java
ModuleFinder systemFinder = ModuleFinder.ofSystem();

systemFinder.find("java.base").ifPresent(reference -> {
    System.out.println(reference.descriptor().name());
});
~~~

Đây là cách truy vấn module hệ thống bằng API, thay vì tự đoán nội dung của JDK đang chạy.

### 3.3. Kết hợp nhiều nguồn module

**ModuleFinder.compose(...)** kết hợp nhiều finder thành một finder.

~~~java
ModuleFinder finder = ModuleFinder.compose(
        ModuleFinder.of(Path.of("plugins")),
        ModuleFinder.of(Path.of("build/modules")),
        ModuleFinder.ofSystem()
);

finder.find("com.acme.orders").ifPresent(reference ->
        System.out.println(reference.descriptor()));
~~~

Thứ tự finder có ý nghĩa khi cùng một tên module xuất hiện ở nhiều nguồn: finder được tìm trước có thể cung cấp tham chiếu được chọn cho tên đó. Vì vậy, cần tổ chức nguồn module có chủ đích và tránh để nhiều phiên bản cùng tên cạnh tranh ngoài ý muốn.

Dùng **compose** khi ứng dụng có nhiều vị trí lưu module nhưng vẫn muốn đưa chúng vào resolver qua một interface duy nhất.

## 4. Custom module source hoạt động như thế nào?

Một custom module source là nguồn nội dung module do ứng dụng tự quản lý. Ví dụ:

- Module được tải từ database hoặc object storage.
- Module được giữ trong bộ nhớ sau khi giải mã.
- Module được cung cấp bởi một kho plugin riêng.
- Module nằm trong một định dạng archive mà finder mặc định không hỗ trợ.
- Module được tạo động trong môi trường kiểm thử.

Để đưa nguồn này vào JPMS, cần nối ba phần:

1. **Custom ModuleFinder**: ánh xạ tên module sang tham chiếu.
2. **ModuleReference**: cung cấp descriptor và tạo reader.
3. **Custom ModuleReader**: đọc bytecode/resource từ nguồn thực tế.

Nguồn tùy chỉnh vẫn phải cung cấp dữ liệu đúng hợp đồng của JPMS. Đặc biệt, descriptor phải phản ánh đúng tên module, package, dependency và quyền truy cập. Một module source tùy chỉnh không thể bỏ qua quy tắc resolve hoặc quy tắc encapsulation của module system.

## 5. Ví dụ: ModuleFinder đọc module từ bộ nhớ

Ví dụ dưới đây tạo một module source đơn giản trong bộ nhớ. Nội dung module được lưu bằng **Map<String, byte[]>**. Finder cung cấp một module tên **com.example.memory** và reader có thể đọc resource **com/example/memory/banner.txt**.

Ví dụ tập trung vào cơ chế tìm và đọc module. Đây chưa phải một kho module production hoàn chỉnh; phần quản lý phiên bản, xác thực nguồn, tải bytecode và cache cần được bổ sung theo hệ thống thực tế.

### 5.1. Triển khai MemoryModuleFinder

~~~java
import java.io.ByteArrayInputStream;
import java.io.IOException;
import java.io.InputStream;
import java.lang.module.ModuleDescriptor;
import java.lang.module.ModuleFinder;
import java.lang.module.ModuleReader;
import java.lang.module.ModuleReference;
import java.net.URI;
import java.nio.ByteBuffer;
import java.util.Arrays;
import java.util.HashMap;
import java.util.Map;
import java.util.Objects;
import java.util.Optional;
import java.util.Set;
import java.util.stream.Stream;

public final class MemoryModuleFinder implements ModuleFinder {

    private final Map<String, ModuleReference> references;

    public MemoryModuleFinder(
            String moduleName,
            Map<String, byte[]> sourceEntries
    ) {
        Objects.requireNonNull(moduleName, "moduleName");
        Objects.requireNonNull(sourceEntries, "sourceEntries");

        Map<String, byte[]> snapshot = new HashMap<>();

        sourceEntries.forEach((name, bytes) -> {
            String validName = validateEntryName(name);
            byte[] copy = Objects.requireNonNull(bytes, "entry bytes").clone();
            snapshot.put(validName, copy);
        });

        Map<String, byte[]> entries = Map.copyOf(snapshot);

        ModuleDescriptor descriptor = ModuleDescriptor
                .newModule(moduleName)
                .packages(Set.of("com.example.memory"))
                .build();

        ModuleReference reference = new ModuleReference(
                descriptor,
                URI.create("memory:///" + moduleName + "/")
        ) {
            @Override
            public ModuleReader open() {
                return new MemoryModuleReader(moduleName, entries);
            }
        };

        this.references = Map.of(moduleName, reference);
    }

    @Override
    public Optional<ModuleReference> find(String name) {
        return Optional.ofNullable(references.get(name));
    }

    @Override
    public Set<ModuleReference> findAll() {
        return Set.copyOf(references.values());
    }

    private static String validateEntryName(String name) {
        Objects.requireNonNull(name, "entry name");

        String[] segments = name.split("/", -1);
        boolean invalidSegment = Arrays.stream(segments)
                .anyMatch(segment ->
                        segment.isEmpty()
                                || segment.equals(".")
                                || segment.equals(".."));

        if (name.isBlank()
                || name.startsWith("/")
                || name.indexOf((char) 92) >= 0
                || invalidSegment) {
            throw new IllegalArgumentException(
                    "Invalid module entry name: " + name
            );
        }

        return name;
    }

    private static final class MemoryModuleReader implements ModuleReader {

        private final String moduleName;
        private final Map<String, byte[]> entries;
        private boolean closed;

        private MemoryModuleReader(
                String moduleName,
                Map<String, byte[]> entries
        ) {
            this.moduleName = moduleName;
            this.entries = entries;
        }

        private void ensureOpen() throws IOException {
            if (closed) {
                throw new IOException("ModuleReader is closed");
            }
        }

        @Override
        public Optional<URI> find(String name) throws IOException {
            ensureOpen();

            if (!entries.containsKey(name)) {
                return Optional.empty();
            }

            return Optional.of(
                    URI.create("memory:///" + moduleName + "/" + name)
            );
        }

        @Override
        public Optional<InputStream> open(String name) throws IOException {
            ensureOpen();

            byte[] bytes = entries.get(name);

            if (bytes == null) {
                return Optional.empty();
            }

            return Optional.of(new ByteArrayInputStream(bytes));
        }

        @Override
        public Optional<ByteBuffer> read(String name) throws IOException {
            ensureOpen();

            byte[] bytes = entries.get(name);

            if (bytes == null) {
                return Optional.empty();
            }

            return Optional.of(
                    ByteBuffer.wrap(bytes).asReadOnlyBuffer()
            );
        }

        @Override
        public void release(ByteBuffer buffer) {
            // ByteBuffer.wrap tạo heap buffer; không có native memory cần giải phóng.
        }

        @Override
        public Stream<String> list() throws IOException {
            ensureOpen();

            return entries.keySet().stream().sorted();
        }

        @Override
        public void close() {
            closed = true;
        }
    }
}
~~~

### 5.2. Tạo finder và đọc resource

~~~java
import java.io.InputStream;
import java.lang.module.ModuleReader;
import java.lang.module.ModuleReference;
import java.nio.charset.StandardCharsets;
import java.util.Map;

public class MemoryModuleDemo {

    public static void main(String[] args) throws Exception {
        String resourceName = "com/example/memory/banner.txt";

        Map<String, byte[]> content = Map.of(
                resourceName,
                "Loaded from memory".getBytes(StandardCharsets.UTF_8)
        );

        MemoryModuleFinder finder = new MemoryModuleFinder(
                "com.example.memory",
                content
        );

        ModuleReference reference = finder
                .find("com.example.memory")
                .orElseThrow();

        System.out.println(
                "Module: " + reference.descriptor().name()
        );

        try (ModuleReader reader = reference.open()) {
            System.out.println(
                    "Resource URI: "
                            + reader.find(resourceName).orElseThrow()
            );

            try (InputStream input = reader
                    .open(resourceName)
                    .orElseThrow()) {

                String value = new String(
                        input.readAllBytes(),
                        StandardCharsets.UTF_8
                );

                System.out.println(value);
            }

            System.out.println("Entries:");

            try (var names = reader.list()) {
                names.forEach(System.out::println);
            }
        }
    }
}
~~~

Kết quả minh họa:

~~~text
Module: com.example.memory
Resource URI: memory:///com.example.memory/com/example/memory/banner.txt
Loaded from memory
Entries:
com/example/memory/banner.txt
~~~

Ở đây, **ModuleFinder** tìm được module bằng tên. **ModuleReference** giữ descriptor và tạo reader. Reader trả về URI, stream hoặc buffer tùy API được gọi. Không có file JAR nào cần được tạo trên đĩa.

URI dùng scheme **memory** trong ví dụ là định danh do nguồn tùy chỉnh quy ước. Nó không tự tạo URL handler để ứng dụng có thể gọi URI.toURL().openStream(). Khi cần đọc nội dung, hãy dùng hợp đồng **ModuleReader**. Một implementation production cần quy định rõ cách encode URI cho mọi tên entry hợp lệ.

## 6. Đưa custom finder vào quá trình resolve

Có finder và reference mới chỉ có nghĩa là ứng dụng đã mô tả được nguồn module. Muốn module tham gia vào một module layer, cần resolve configuration và định nghĩa layer.

~~~java
import java.lang.module.Configuration;
import java.lang.module.ModuleFinder;
import java.nio.charset.StandardCharsets;
import java.util.List;
import java.util.Map;
import java.util.Set;

public class ResolveMemoryModule {

    public static void main(String[] args) {
        String resourceName = "com/example/memory/banner.txt";

        ModuleFinder finder = new MemoryModuleFinder(
                "com.example.memory",
                Map.of(
                        resourceName,
                        "Loaded from memory".getBytes(StandardCharsets.UTF_8)
                )
        );

        Configuration configuration = ModuleLayer.boot()
                .configuration()
                .resolve(
                        finder,
                        ModuleFinder.of(),
                        Set.of("com.example.memory")
                );

        ModuleLayer.Controller controller =
                ModuleLayer.defineModulesWithOneLoader(
                        configuration,
                        List.of(ModuleLayer.boot()),
                        ClassLoader.getSystemClassLoader()
                );

        ModuleLayer layer = controller.layer();

        System.out.println(
                layer.findModule("com.example.memory").isPresent()
        );
    }
}
~~~

Các bước có ý nghĩa khác nhau:

1. **Configuration.resolve** tìm module gốc và các dependency cần thiết từ các finder được cung cấp, đồng thời kiểm tra tính nhất quán của đồ thị module.
2. **ModuleLayer.defineModulesWithOneLoader** định nghĩa các module trong configuration trên một class loader chung cho layer mới.
3. **controller.layer()** lấy layer vừa được định nghĩa.

Nếu module có dependency, finder tương ứng phải cung cấp các dependency đó hoặc chúng phải có trong configuration cha. Nếu không, resolve sẽ thất bại. Custom finder không làm mất yêu cầu khai báo **requires** trong descriptor.

Ví dụ này định nghĩa một module chỉ có resource. Khi muốn nạp class từ nguồn tùy chỉnh, map entry cần chứa bytecode .class tương ứng và descriptor phải khai báo đúng package. Class loader của layer sẽ sử dụng module content để tìm class. ModuleReader không biên dịch class từ source code.

Trong ứng dụng thực tế, chỉ định nghĩa layer khi đã có lý do rõ ràng để cô lập một nhóm module, chẳng hạn plugin hoặc phiên bản module riêng. Với ứng dụng thông thường, module path và boot layer thường đã đáp ứng nhu cầu.

## 7. Descriptor phải khớp với nội dung nguồn

Custom source chịu trách nhiệm cung cấp descriptor chính xác. Một descriptor có thể được tạo bằng các builder của **ModuleDescriptor**:

~~~java
ModuleDescriptor descriptor = ModuleDescriptor
        .newModule("com.acme.reporting")
        .requires("java.logging")
        .exports("com.acme.reporting.api")
        .opens("com.acme.reporting.internal")
        .packages(Set.of(
                "com.acme.reporting.api",
                "com.acme.reporting.internal"
        ))
        .build();
~~~

Ý nghĩa các khai báo:

- **requires** khai báo dependency module.
- **exports** cho phép module khác truy cập các public type trong package được export theo quy tắc JPMS.
- **opens** cho phép truy cập reflective vào package theo quy tắc mở package.
- **packages** mô tả tập package có trong module; finder tùy chỉnh cần cung cấp tập này phù hợp với nội dung thực tế.

**exports** và **opens** có mục đích khác nhau. Export là hợp đồng truy cập API ở mức compile/runtime thông thường; open phục vụ reflection. Không dùng open chỉ vì muốn một module có thể được tìm thấy hoặc đọc resource.

Khi tạo descriptor động, cần mô tả cả dependency, service declaration, main class và version nếu module thực sự sử dụng các tính năng đó. Resolver dựa trên metadata này để kiểm tra module graph.

## 8. Những điểm cần chú ý khi viết finder/reader production

### Tính nhất quán của nguồn

- Mỗi tên module phải ánh xạ đến descriptor tương ứng.
- **find(name)** và **findAll()** phải thống nhất: module được liệt kê phải có thể tìm theo tên.
- Không để cùng một module name trỏ đến các nội dung khác nhau trong cùng một lần resolve.
- Nên dùng snapshot bất biến hoặc version cố định trong suốt vòng đời resolve/load.

### Đường dẫn entry

- Chuẩn hóa tên entry theo dạng tương đối và dùng dấu /.
- Chặn **..**, đường dẫn tuyệt đối và các dạng path traversal.
- Không để tên entry tạo URI không hợp lệ.
- Nếu nguồn là archive hoặc remote storage, phải kiểm soát kích thước và số lượng entry.

### ByteBuffer và tài nguyên

- Nếu **read** cấp phát native/direct memory, implementation phải giải phóng đúng cách trong **release**.
- Nếu dùng heap buffer như ví dụ, **release** có thể không cần thao tác giải phóng.
- Stream trả về từ **open** thuộc trách nhiệm đóng của caller.
- **close** phải ngăn các thao tác đọc tiếp theo và giải phóng handle/cache/tài nguyên của nguồn nếu có.

### Đồng bộ và vòng đời

Một **ModuleReader** thường được sử dụng trong một thao tác đọc có vòng đời rõ ràng. Nếu nhiều thread có thể mở reader hoặc đọc cùng một module, cần xác định chính sách thread-safety cho implementation. Không dùng một cờ trạng thái hoặc mutable map dùng chung mà không có đồng bộ thích hợp.

### Tin cậy và tính toàn vẹn

Nếu module đến từ remote repository hoặc database, cần xác minh danh tính/version và tính toàn vẹn của bytecode trước khi đưa vào layer. Finder chỉ trả về module reference; nó không tự xác thực chữ ký, quyền cài đặt plugin hoặc nguồn gốc nội dung.

## 9. Lỗi thường gặp và cách định hướng xử lý

| Hiện tượng | Nguyên nhân cần kiểm tra |
|---|---|
| **find(name)** trả về empty | Finder không có module với tên đó, hoặc tên tra cứu không khớp descriptor |
| Resolve báo thiếu module | Một dependency trong **requires** không có trong finder/configuration cha |
| Resolve thất bại vì xung đột | Descriptor hoặc đồ thị dependency không nhất quán; kiểm tra module trùng tên, package split và constraint |
| Không đọc được resource | Sai entry name, reader không cung cấp entry, hoặc reader đã đóng |
| Đọc resource qua class loader không thành công | Kiểm tra package encapsulation, **opens** và cách truy cập resource |
| Class không được nạp | Kiểm tra bytecode có trong module source, package mapping, descriptor và class loader của layer |
| Reader báo lỗi sau khi đóng | Caller đã giữ reader sau khi kết thúc vòng đời; mở reader mới cho thao tác mới |

Khi debug, nên kiểm tra lần lượt:

1. **finder.find(moduleName)** có trả về reference không?
2. **reference.descriptor()** có đúng tên và dependency không?
3. **reference.open().list()** có liệt kê entry cần thiết không?
4. **reader.open(entryName)** có đọc được entry không?
5. **Configuration.resolve** có hoàn thành không?
6. Layer có chứa module và cung cấp loader tương ứng không?

## 10. Chọn cách tiếp cận phù hợp

| Nhu cầu | Giải pháp |
|---|---|
| Module nằm trong modular JAR hoặc exploded module | **ModuleFinder.of(paths)** |
| Cần truy cập module của JDK | **ModuleFinder.ofSystem()** |
| Module nằm ở nhiều thư mục/kho chuẩn | **ModuleFinder.compose(...)** |
| Module đến từ memory, database, custom archive hoặc remote store | Tự triển khai **ModuleFinder**, **ModuleReference** và **ModuleReader** |
| Cần cô lập plugin hoặc nhóm module ở runtime | Kết hợp finder với **Configuration.resolve** và **ModuleLayer** |

Chỉ nên triển khai custom source khi nguồn dữ liệu thực sự khác với module path tiêu chuẩn. Một custom finder/reader phải xử lý descriptor, bytecode, resource, URI, vòng đời và lỗi I/O; đây là một ranh giới kỹ thuật cần được quản lý như một phần của module infrastructure.

## Kết luận

**ModuleFinder** trả lời câu hỏi “module nào tồn tại trong nguồn này?”. **ModuleReference** mô tả module và mở nội dung của nó. **ModuleReader** cung cấp bytecode và resource cho module system. Khi ba abstraction này được triển khai đúng hợp đồng, JPMS có thể resolve module từ một nguồn tùy chỉnh giống như cách nó resolve module từ module path tiêu chuẩn.

Hãy nhớ phân biệt ba giai đoạn: **tìm module → resolve module graph → định nghĩa module layer**. Tìm được module chưa có nghĩa là dependency đã resolve hoặc module đã sẵn sàng chạy.
