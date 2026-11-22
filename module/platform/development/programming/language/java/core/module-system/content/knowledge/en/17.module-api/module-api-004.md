# ModuleReference, ModuleReader và resource

Trong Java Module System, package \`java.lang.module\` cung cấp API để tìm, mô tả và đọc nội dung của một module. Hai kiểu quan trọng là **ModuleReference** và **ModuleReader**:

- **ModuleReference** đại diện cho một tham chiếu tới module: nó giữ ModuleDescriptor và biết cách mở nội dung module.
- **ModuleReader** cung cấp cách đọc các resource bên trong module mà không cần nạp class vào JVM.

Các API này hữu ích khi xây dựng công cụ kiểm tra module, phân tích module path, đóng gói ứng dụng, tìm resource hoặc làm việc với quá trình resolve module.

## 1. Vị trí của các kiểu trong Module API

Một module có thể được nhìn từ ba góc độ:

| Kiểu | Vai trò |
|---|---|
| ModuleDescriptor | Mô tả metadata của module: tên, version, requires, exports, opens, uses, provides và các package |
| ModuleReference | Kết hợp descriptor với một tham chiếu tới nội dung module |
| ModuleReader | Đọc resource thực tế trong nội dung module |

Luồng làm việc thường gặp:

~~~text
ModuleFinder
    |
    | find("module.name")
    v
ModuleReference
    |-- descriptor()  -> ModuleDescriptor
    |-- location()    -> URI hoặc null
    |
    | open()
    v
ModuleReader
    |-- find(name)    -> Optional<URI>
    |-- open(name)    -> Optional<InputStream>
    |-- read(name)    -> Optional<ByteBuffer>
    |-- list()        -> Stream<String>
    |-- release(...)
    |-- close()
~~~

ModuleReference và ModuleReader không phải là đối tượng Module trong package java.lang. Module là module đã được định nghĩa trong runtime; ModuleReference là tham chiếu được dùng trong quá trình tìm và resolve module; ModuleReader là giao diện đọc nội dung của module.

## 2. ModuleReference

ModuleReference là lớp trừu tượng trong java.lang.module. Một đối tượng đại diện cho một module có thể được tìm thấy bởi ModuleFinder.

Các phương thức chính:

| Phương thức | Ý nghĩa |
|---|---|
| descriptor() | Trả về ModuleDescriptor của module |
| location() | Trả về URI xác định vị trí nội dung module, hoặc null nếu không biết vị trí |
| open() | Mở ModuleReader để đọc nội dung module; có thể ném IOException |

ModuleReference không tự nạp class. Nó cung cấp metadata và điểm truy cập để công cụ đọc nội dung module.

Ví dụ lấy tham chiếu tới module hệ thống java.base:

~~~java
import java.lang.module.ModuleFinder;
import java.lang.module.ModuleReference;

ModuleReference reference = ModuleFinder.ofSystem()
        .find("java.base")
        .orElseThrow(() ->
                new IllegalStateException("Không tìm thấy java.base"));

System.out.println(reference.descriptor().name());
System.out.println(reference.location());
~~~

ModuleFinder.ofSystem() tìm các module thuộc runtime image hiện tại. Với module nằm trên module path, có thể tạo finder bằng ModuleFinder.of(Path...). Sau khi có ModuleReference, có thể xem descriptor hoặc mở ModuleReader.

Không nên giả định location() luôn trả về một URI có thể chuyển trực tiếp thành Path. Vị trí có thể không được cung cấp hoặc dùng một URI scheme mà ứng dụng không xử lý như file thông thường. Nếu mục tiêu là đọc nội dung, hãy dùng ModuleReader.

## 3. ModuleReader và cách truy cập resource

ModuleReader là interface mở rộng Closeable. Nó cung cấp nhiều cách truy cập cùng một resource, tùy theo việc cần URI, InputStream hay ByteBuffer.

Tên resource là tên tương đối bên trong module, dùng dấu gạch chéo xuôi để phân tách package/thư mục. Ví dụ:

- java/lang/Object.class
- com/example/config.properties
- META-INF/services/com.example.PaymentProvider

Không thêm dấu gạch chéo ở đầu tên resource. Tên resource không phải đường dẫn tuyệt đối trên filesystem.

### find(name): tìm URI của resource

find(name) trả về Optional<URI>. Nếu tìm thấy resource, URI mô tả vị trí của resource theo cách triển khai ModuleReader cung cấp.

~~~java
import java.io.IOException;
import java.lang.module.ModuleReader;
import java.lang.module.ModuleReference;
import java.net.URI;
import java.util.Optional;

try (ModuleReader reader = reference.open()) {
    Optional<URI> result = reader.find("java/lang/Object.class");

    result.ifPresent(uri ->
            System.out.println("Resource URI: " + uri));
}
~~~

find() phù hợp khi cần biết resource có tồn tại và cần URI của nó. URI này không nhất thiết là file URI. Không nên mặc định dùng Paths.get(uri) hoặc File để đọc mọi URI trả về.

### open(name): đọc resource bằng InputStream

open(name) trả về Optional<InputStream>. Đây là lựa chọn thuận tiện khi cần đọc tuần tự dữ liệu, chẳng hạn file properties, JSON hoặc nội dung nhị phân.

~~~java
import java.io.IOException;
import java.io.InputStream;
import java.lang.module.ModuleReader;
import java.util.Optional;

try (ModuleReader reader = reference.open()) {
    Optional<InputStream> result =
            reader.open("java/lang/Object.class");

    if (result.isPresent()) {
        try (InputStream input = result.get()) {
            byte[] bytes = input.readAllBytes();
            System.out.println("Số byte: " + bytes.length);
        }
    } else {
        System.out.println("Không tìm thấy resource");
    }
}
~~~

Có hai tài nguyên cần đóng trong ví dụ: ModuleReader và InputStream. Mỗi đối tượng được đặt trong try-with-resources để bảo đảm được đóng kể cả khi có exception.

### read(name): đọc resource bằng ByteBuffer

read(name) trả về Optional<ByteBuffer>. Cách này có thể phù hợp với công cụ xử lý dữ liệu nhị phân hoặc API làm việc trực tiếp với NIO.

~~~java
import java.io.IOException;
import java.lang.module.ModuleReader;
import java.nio.ByteBuffer;
import java.util.Optional;

try (ModuleReader reader = reference.open()) {
    Optional<ByteBuffer> result =
            reader.read("java/lang/Object.class");

    if (result.isPresent()) {
        ByteBuffer buffer = result.get();

        try {
            byte[] bytes = new byte[buffer.remaining()];
            buffer.get(bytes);
            System.out.println("Số byte: " + bytes.length);
        } finally {
            reader.release(buffer);
        }
    }
}
~~~

Khi read() trả về buffer, gọi release() trên chính ByteBuffer được trả về sau khi dùng xong. Việc giải phóng cụ thể phụ thuộc vào implementation; với một số implementation, buffer có thể dùng bộ nhớ ngoài heap. Không thay buffer gốc bằng một bản duplicate hoặc slice khi gọi release().

### list(): liệt kê tên resource

list() trả về Stream<String> chứa tên các resource trong module. Stream này cần được đóng sau khi sử dụng.

~~~java
import java.io.IOException;
import java.lang.module.ModuleReader;
import java.util.stream.Stream;

try (ModuleReader reader = reference.open()) {
    try (Stream<String> names = reader.list()) {
        names.filter(name -> name.endsWith(".properties"))
             .forEach(System.out::println);
    }
}
~~~

Không nên giả định list() chỉ trả về các file mà ứng dụng tự tạo. Nội dung module có thể gồm class, metadata và các resource khác. Hãy lọc theo tên hoặc phần mở rộng phù hợp với mục tiêu.

## 4. Chọn phương thức đọc nào?

| Nhu cầu | API nên dùng |
|---|---|
| Kiểm tra resource có tồn tại và lấy URI | find(name) |
| Đọc tuần tự bằng API stream | open(name) |
| Xử lý dữ liệu bằng NIO ByteBuffer | read(name), sau đó release(buffer) |
| Liệt kê resource trong module | list() |

Nếu chỉ cần đọc nội dung, open() thường dễ sử dụng vì InputStream có thể được đóng bằng try-with-resources. read() hữu ích khi phần còn lại của chương trình đã làm việc với ByteBuffer và có thể quản lý vòng đời buffer đúng cách.

## 5. Quản lý vòng đời và lỗi

ModuleReader đại diện cho một phiên truy cập nội dung module. Sau khi mở reader, cần đóng nó khi hoàn tất:

~~~java
try (ModuleReader reader = reference.open()) {
    // find, open, read hoặc list resource tại đây
}
~~~

Một số điểm cần nhớ:

1. reference.open() và các thao tác đọc có thể ném IOException. Xử lý hoặc khai báo exception phù hợp.
2. find(), open() và read() dùng Optional để biểu diễn trường hợp không tìm thấy resource. Kiểm tra Optional trước khi lấy giá trị.
3. InputStream lấy từ open() phải được đóng riêng.
4. Stream lấy từ list() phải được đóng sau khi duyệt.
5. ByteBuffer lấy từ read() phải được trả lại cho reader bằng release() khi không còn sử dụng.
6. Không tiếp tục dùng reader sau khi đã đóng reader.

Dùng try-with-resources cho reader, stream và input stream giúp tránh rò rỉ tài nguyên. Với ByteBuffer, dùng finally để bảo đảm release() vẫn được gọi nếu xử lý dữ liệu gặp lỗi.

## 6. Quan hệ với ModuleFinder và quá trình resolve

ModuleFinder chịu trách nhiệm tìm các ModuleReference. Nó có thể tìm module trong runtime image hoặc từ các vị trí module path được cung cấp.

~~~java
import java.lang.module.ModuleFinder;
import java.lang.module.ModuleReference;
import java.nio.file.Path;
import java.util.Set;

ModuleFinder finder = ModuleFinder.of(Path.of("mods"));
Set<ModuleReference> references = finder.findAll();

for (ModuleReference reference : references) {
    System.out.println(reference.descriptor().name());
}
~~~

Trong ví dụ, thư mục mods được dùng làm đầu vào cho ModuleFinder. Mỗi kết quả là một ModuleReference. Từ reference, chương trình có thể đọc descriptor hoặc mở ModuleReader để kiểm tra nội dung.

Trong quá trình resolve, Java sử dụng các ModuleReference và ModuleDescriptor để xác định module nào cần có mặt, các quan hệ requires và cách tạo Configuration. ModuleReader cung cấp khả năng truy cập nội dung module cho các thao tác cần đọc resource. Việc đọc resource bằng ModuleReader không đồng nghĩa với việc module đã được định nghĩa trong một ModuleLayer hoặc class của module đã được nạp.

## 7. Phân biệt với ClassLoader và Module

| Thành phần | Trách nhiệm |
|---|---|
| ModuleReference | Tham chiếu module được tìm thấy, có descriptor và khả năng mở reader |
| ModuleReader | Đọc resource từ nội dung module |
| Module | Đại diện cho module trong runtime |
| ClassLoader | Nạp class và cung cấp cơ chế tìm resource theo quy tắc của class loader |

ModuleReader là API cấp thấp để làm việc với nội dung module. Nếu ứng dụng chỉ cần tải resource trong lúc chạy theo cơ chế thông thường, API resource của ClassLoader hoặc Module có thể phù hợp hơn. Nếu đang xây dựng công cụ phân tích, đóng gói hoặc kiểm tra module trước khi nạp, ModuleReference và ModuleReader là những API phù hợp.

## 8. Những lỗi thường gặp

- **Giả định location() luôn khác null:** vị trí module có thể không được biết. Dùng ModuleReader để truy cập nội dung.
- **Coi URI là đường dẫn file:** URI có thể dùng scheme khác file. Không chuyển URI thành Path một cách mặc định.
- **Quên đóng reader hoặc InputStream:** dùng try-with-resources.
- **Quên đóng Stream từ list():** đóng stream sau khi duyệt.
- **Quên release ByteBuffer:** gọi reader.release() với buffer gốc sau khi xử lý.
- **Dùng tên resource như đường dẫn tuyệt đối:** truyền tên tương đối, phân tách bằng dấu gạch chéo xuôi và không thêm dấu / ở đầu.
- **Nhầm ModuleReference với Module:** reference phục vụ việc tìm và đọc module; Module đại diện cho module đã có trong runtime.

## 9. Ghi nhớ

ModuleReference trả lời câu hỏi: “Module này được mô tả như thế nào và có thể mở nội dung ở đâu?”. ModuleReader trả lời câu hỏi: “Có thể tìm, liệt kê và đọc resource nào bên trong module?”. Kết hợp ModuleFinder, ModuleReference và ModuleReader cho phép công cụ Java khám phá metadata và nội dung module mà không cần nạp các class của module vào ứng dụng.
