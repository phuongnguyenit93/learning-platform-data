# ModuleReference, ModuleDescriptor và ModuleReader

Trong Java Platform Module System (JPMS), ba kiểu `ModuleReference`, `ModuleDescriptor` và `ModuleReader` phối hợp để tìm một module, mô tả cấu trúc của module và đọc tài nguyên bên trong module đó. Chúng thường được dùng khi xây dựng công cụ phân tích module, kiểm tra module path, đọc metadata hoặc làm việc với nội dung module theo cách độc lập với vị trí lưu trữ.

Các API này thuộc package `java.lang.module` và vẫn được sử dụng trong các phiên bản Java hiện hành.

## 1. Vai trò và mối quan hệ

| Kiểu | Vai trò | Câu hỏi mà API trả lời |
|---|---|---|
| `ModuleDescriptor` | Mô tả metadata và các directive của module | Module tên gì, phụ thuộc module nào, export/open package nào, cung cấp hoặc sử dụng service nào? |
| `ModuleReference` | Đại diện cho một module đã được tìm thấy và giữ descriptor cùng vị trí tùy chọn | Module này được tìm thấy ở đâu và có thể mở reader bằng cách nào? |
| `ModuleReader` | Đọc tài nguyên nằm trong nội dung module | Module chứa resource nào và có thể lấy nội dung resource ra sao? |

Luồng làm việc thường gặp:

1. Dùng `ModuleFinder` để tìm module trong runtime image hoặc các vị trí trên module path.
2. Nhận một `ModuleReference` từ kết quả tìm kiếm.
3. Gọi `reference.descriptor()` để đọc metadata dưới dạng `ModuleDescriptor`.
4. Gọi `reference.open()` để tạo `ModuleReader`.
5. Dùng reader để tìm, liệt kê hoặc đọc resource; đóng các tài nguyên sau khi sử dụng.

`ModuleReference` không phải một đối tượng `Module` đang chạy trong một `ModuleLayer`. Nó là tham chiếu đến nội dung module và descriptor của nội dung đó. Tương tự, `ModuleReader` đọc resource; nó không tự giải quyết dependency hay nạp class vào JVM.

## 2. ModuleDescriptor: mô tả module

`ModuleDescriptor` là đối tượng metadata bất biến mô tả một module có tên. Descriptor có thể được lấy từ một `ModuleReference`, được phân tích từ file `module-info.class`, hoặc được tạo trong bộ nhớ bằng builder.

### 2.1. Những thông tin chính

Các phương thức thường dùng:

| Phương thức | Ý nghĩa |
|---|---|
| `name()` | Tên module, ví dụ `java.base`. |
| `modifiers()` | Các modifier của module. |
| `isOpen()` | Cho biết đây có phải open module hay không. |
| `isAutomatic()` | Cho biết descriptor đại diện cho automatic module hay không. |
| `requires()` | Tập các module mà module này khai báo phụ thuộc. |
| `exports()` | Các package được export cho module khác. |
| `opens()` | Các package được mở cho truy cập reflection sâu ở runtime. |
| `uses()` | Các service mà module cần sử dụng. |
| `provides()` | Các service mà module cung cấp implementation. |
| `packages()` | Tập tên package thuộc module. |
| `version()`, `rawVersion()` | Phiên bản module nếu có. |
| `mainClass()` | Main class nếu descriptor khai báo. |

Các tập hợp trả về là tập hợp chỉ đọc. Hãy duyệt hoặc truy vấn chúng thay vì cố gắng sửa trực tiếp. `Optional` được dùng cho thông tin có thể không tồn tại, chẳng hạn version, main class hoặc location.

### 2.2. Hiểu các directive

- **`requires`** khai báo dependency giữa các module. `requires transitive` cho phép module phụ thuộc vào module hiện tại cũng đọc được dependency được truyền tiếp. `requires static` biểu thị dependency cần ở thời điểm biên dịch nhưng có thể không hiện diện ở runtime.
- **`exports`** công khai các kiểu public trong package cho module khác. Export không đồng nghĩa với việc mở quyền reflection sâu.
- **`opens`** cho phép truy cập reflection sâu vào package ở runtime. Đây là cơ chế thường cần cho framework cần inspect field hoặc constructor. `open module` mở toàn bộ package của module cho reflection sâu.
- **`uses`** khai báo service mà module tiêu thụ.
- **`provides`** khai báo service và các lớp provider tương ứng; cơ chế này được sử dụng cùng Java Service Loader.

Với `exports` hoặc `opens` có danh sách target, directive chỉ áp dụng cho những module được chỉ định. Tập target rỗng biểu thị directive không giới hạn ở một danh sách module cụ thể.

### 2.3. Tạo descriptor bằng Builder

Các factory method chính:

- `ModuleDescriptor.newModule(name)`: tạo builder cho named module thông thường.
- `ModuleDescriptor.newOpenModule(name)`: tạo builder cho open module.
- `ModuleDescriptor.newAutomaticModule(name)`: tạo builder cho automatic module descriptor.

Builder cung cấp các thao tác như `requires(...)`, `exports(...)`, `opens(...)`, `uses(...)`, `provides(...)`, `packages(...)`, `version(...)` và `mainClass(...)`. Gọi `build()` để tạo descriptor bất biến. Builder kiểm tra tính hợp lệ của metadata; các directive trùng hoặc tên không hợp lệ có thể khiến thao tác tạo descriptor thất bại.

Automatic module vẫn là một phần của JPMS: nó cho phép đưa JAR chưa có `module-info.class` vào module path trong quá trình chuyển đổi. `isAutomatic()` giúp nhận biết trường hợp này. Khi thiết kế module mới, descriptor tường minh thường thể hiện dependency và ranh giới package rõ ràng hơn.

Ví dụ tạo descriptor trong bộ nhớ:

```java
ModuleDescriptor descriptor = ModuleDescriptor.newModule("com.example.orders")
        .requires("java.logging")
        .exports("com.example.orders.api")
        .uses("com.example.orders.spi.PaymentGateway")
        .provides("com.example.orders.spi.PaymentGateway",
                List.of("com.example.orders.internal.DefaultPaymentGateway"))
        .packages(Set.of(
                "com.example.orders.api",
                "com.example.orders.spi",
                "com.example.orders.internal"))
        .build();
```

Đoạn code tạo metadata trong bộ nhớ. Nó không tự tạo file `module-info.class`, JAR, class implementation hay cấu trúc thư mục cho module. Các package và lớp được khai báo phải tương ứng với nội dung module thực tế khi descriptor được dùng để mô tả một module có thật.

### 2.4. Đọc descriptor từ module-info.class

`ModuleDescriptor.read(...)` phân tích descriptor từ byte của file `module-info.class`. Các overload nhận `InputStream` hoặc `ByteBuffer`; overload có thêm `Supplier<Set<String>>` cho phép cung cấp tập package thực tế của module.

Package finder hữu ích khi cần danh sách package đầy đủ, kể cả package không được export hoặc open. Bản thân `module-info.class` mô tả các directive, nhưng không phải danh sách đầy đủ mọi package có trong nội dung module. Nếu dùng `InputStream`, caller chịu trách nhiệm đóng stream. Nếu buffer đến từ `ModuleReader.read`, phải gọi `release(buffer)` sau khi xử lý.

## 3. ModuleReference: tham chiếu đến module đã tìm thấy

`ModuleReference` là abstract class đại diện cho một module cùng descriptor của nó. Constructor được bảo vệ; trong ứng dụng thông thường, bạn nhận instance từ `ModuleFinder` thay vì tự khởi tạo trực tiếp.

Ba phương thức quan trọng:

- `descriptor()`: trả về `ModuleDescriptor` của module.
- `location()`: trả về `Optional<URI>` mô tả vị trí module nếu biết. Không giả định giá trị luôn có mặt hoặc URI luôn dùng giao thức `file:`; module trong runtime image có thể dùng URI dạng `jrt:`.
- `open()`: mở nội dung module và trả về `ModuleReader`; thao tác có thể phát sinh `IOException`.

Ví dụ tìm module trong runtime image:

```java
ModuleReference reference = ModuleFinder.ofSystem()
        .find("java.base")
        .orElseThrow();

ModuleDescriptor descriptor = reference.descriptor();
System.out.println(descriptor.name());
```

`ModuleFinder.ofSystem()` tìm các module thuộc runtime image. `ModuleFinder.of(Path...)` tìm module trong những vị trí được cung cấp, chẳng hạn modular JAR hoặc thư mục exploded module trên module path. `find(name)` trả về `Optional<ModuleReference>`; `findAll()` trả về các module được tìm thấy.

Ứng dụng nâng cao có thể tạo implementation riêng bằng cách kế thừa `ModuleReference` và cung cấp `ModuleReader` phù hợp cho nơi lưu trữ module tùy chỉnh. Phần lớn ứng dụng chỉ cần dùng các reference do `ModuleFinder` trả về.

## 4. ModuleReader: đọc resource trong module

`ModuleReader` là interface mở rộng `Closeable`. Nó cung cấp cách truy cập resource mà không buộc caller phải biết module nằm trong JAR, thư mục hay runtime image.

Tên resource thường dùng dạng đường dẫn tương đối với dấu gạch chéo xuôi, ví dụ `module-info.class` hoặc `java/lang/Object.class`. Không ghép tên resource với đường dẫn filesystem của máy hiện tại.

| Phương thức | Kết quả và cách dùng |
|---|---|
| `find(name)` | Trả về `Optional<URI>` nếu resource tồn tại. URI có thể không phải file URI. |
| `open(name)` | Trả về `Optional<InputStream>` để đọc tuần tự. Đóng stream sau khi dùng. |
| `read(name)` | Trả về `Optional<ByteBuffer>` để đọc nội dung dạng buffer. |
| `release(buffer)` | Giải phóng buffer nhận từ `read` sau khi xử lý xong. |
| `list()` | Trả về `Stream<String>` chứa tên các resource. Phải đóng stream. |
| `close()` | Đóng reader và giải phóng tài nguyên liên quan. |

Chọn phương thức theo nhu cầu:

- Chỉ cần biết resource có tồn tại và URI của nó: dùng `find`.
- Cần đọc dữ liệu theo luồng: dùng `open` và try-with-resources cho `InputStream`.
- Cần truy cập dữ liệu qua `ByteBuffer`: dùng `read`, sau đó gọi `release` trong khối `finally`.
- Cần kiểm kê nội dung: dùng `list` và đóng stream bằng try-with-resources.

Kết quả `Optional.empty()` có nghĩa resource không được tìm thấy. Không nên giả định resource nào cũng tồn tại. `find` trả URI để định vị resource; nếu mục tiêu là lấy byte, `open` hoặc `read` thường phù hợp hơn. URI do reader trả về không được đảm bảo là đường dẫn filesystem có thể truyền trực tiếp cho `Files`.

Reader, stream và buffer có vòng đời riêng. Đóng reader sau khi hoàn tất; đóng stream do `open` trả về; đóng stream do `list` trả về; và release mọi buffer nhận từ `read`. Không tiếp tục sử dụng buffer sau khi đã release. Không nên chia sẻ một reader giữa nhiều luồng nếu implementation cụ thể không cam kết thread-safe.

## 5. Ví dụ hoàn chỉnh: tìm module, đọc descriptor và tạo descriptor mới

Chương trình dưới đây chạy độc lập trên Java 17 trở lên. Nó tìm module hệ thống `java.base`, đọc resource `module-info.class` qua `ModuleReader`, phân tích resource đó bằng `ModuleDescriptor.read`, sau đó tạo một descriptor khác bằng builder.

**ModuleMetadataDemo.java**

```java
import java.io.IOException;
import java.lang.module.ModuleDescriptor;
import java.lang.module.ModuleFinder;
import java.lang.module.ModuleReader;
import java.lang.module.ModuleReference;
import java.nio.ByteBuffer;
import java.util.List;
import java.util.Set;
import java.util.stream.Stream;

public class ModuleMetadataDemo {
    public static void main(String[] args) throws IOException {
        ModuleReference reference = ModuleFinder.ofSystem()
                .find("java.base")
                .orElseThrow();

        ModuleDescriptor actual = reference.descriptor();
        System.out.println("module=" + actual.name());
        System.out.println("automatic=" + actual.isAutomatic());

        try (ModuleReader reader = reference.open()) {
            System.out.println("module-info.class found="
                    + reader.find("module-info.class").isPresent());

            try (Stream<String> names = reader.list()) {
                System.out.println("Object.class listed="
                        + names.anyMatch("java/lang/Object.class"::equals));
            }

            ByteBuffer bytes = reader.read("module-info.class").orElseThrow();
            try {
                ModuleDescriptor parsed = ModuleDescriptor.read(bytes);
                System.out.println("parsed descriptor=" + parsed.name());
            } finally {
                reader.release(bytes);
            }
        }

        ModuleDescriptor declared = ModuleDescriptor.newModule("com.example.orders")
                .requires("java.logging")
                .exports("com.example.orders.api")
                .uses("com.example.orders.spi.PaymentGateway")
                .provides("com.example.orders.spi.PaymentGateway",
                        List.of("com.example.orders.internal.DefaultPaymentGateway"))
                .packages(Set.of(
                        "com.example.orders.api",
                        "com.example.orders.spi",
                        "com.example.orders.internal"))
                .build();

        System.out.println("declared module=" + declared.name());
        System.out.println("requires java.logging=" + declared.requires().stream()
                .anyMatch(requirement -> requirement.name().equals("java.logging")));
        System.out.println("exports API=" + declared.exports().stream()
                .anyMatch(export -> export.source().equals("com.example.orders.api")));
    }
}
```

Biên dịch và chạy:

```bash
javac --release 17 ModuleMetadataDemo.java
java ModuleMetadataDemo
```

Kết quả stdout:

```text
module=java.base
automatic=false
module-info.class found=true
Object.class listed=true
parsed descriptor=java.base
declared module=com.example.orders
requires java.logging=true
exports API=true
```

Trong ví dụ:

- `ModuleFinder.ofSystem()` tìm reference đến `java.base`.
- `reference.descriptor()` đọc metadata mà không cần mở resource.
- `reference.open()` tạo reader; reader được đóng tự động khi thoát khỏi try-with-resources.
- `find` kiểm tra sự hiện diện của `module-info.class`; `list` kiểm tra tên resource trong module.
- `read` lấy byte của descriptor. `ModuleDescriptor.read` phân tích buffer, sau đó `release` trả buffer cho reader ngay cả khi quá trình phân tích phát sinh lỗi.
- Builder tạo một descriptor mới và các truy vấn trên `requires()` cùng `exports()` xác nhận metadata đã được ghi nhận.

Kết quả phụ thuộc vào nội dung runtime image đang chạy; ví dụ này dùng resource chuẩn của module `java.base`, có trong JDK đầy đủ.

## 6. Khi nào nên dùng từng API?

- Dùng **`ModuleDescriptor`** khi cần kiểm tra dependency, modifier, package boundary, service declaration, version hoặc main class mà không cần đọc từng resource.
- Dùng **`ModuleReference`** khi cần giữ một module đã được `ModuleFinder` tìm thấy, lấy descriptor hoặc mở reader cho nội dung module.
- Dùng **`ModuleReader`** khi cần liệt kê, tìm hoặc đọc resource của module theo cách không phụ thuộc định dạng lưu trữ.

Ba API có trách nhiệm riêng. Nếu chỉ cần metadata, đọc descriptor thường đủ. Chỉ mở reader khi cần truy cập nội dung module; việc mở reader tạo thêm tài nguyên cần quản lý.

## 7. Lỗi thường gặp và cách tránh

1. **Giả định `location()` luôn có URI:** giá trị trả về là `Optional`; kiểm tra trước khi sử dụng. URI cũng không nhất thiết là `file:`.
2. **Nhầm descriptor với module đang chạy:** `ModuleDescriptor` chỉ mô tả metadata. Nó không đại diện cho một instance `Module` trong `ModuleLayer`.
3. **Nhầm `exports` với `opens`:** export kiểm soát khả năng truy cập các kiểu public; open cho phép reflection sâu ở runtime.
4. **Quên đóng reader hoặc stream:** dùng try-with-resources cho `ModuleReader`, `InputStream` và `Stream<String>`.
5. **Quên release buffer:** mọi `ByteBuffer` lấy từ `ModuleReader.read` phải được trả lại bằng `release` sau khi xử lý.
6. **Coi URI từ `find` là đường dẫn file:** URI có thể dùng scheme khác. Dùng `open` hoặc `read` nếu cần lấy nội dung.
7. **Cho rằng builder tạo module vật lý:** `ModuleDescriptor.Builder` chỉ tạo metadata. Muốn có module thực thi được, nội dung và descriptor của module phải được đóng gói hoặc bố trí đúng theo JPMS.
8. **Không kiểm tra `Optional`:** module hoặc resource có thể không tồn tại; xử lý trường hợp rỗng thay vì giả định luôn có kết quả.

## 8. Ghi nhớ

`ModuleDescriptor` mô tả module; `ModuleReference` đại diện cho module đã được tìm thấy; `ModuleReader` truy cập resource bên trong module. Trong luồng JPMS thông dụng, `ModuleFinder` tạo điểm bắt đầu, reference cung cấp descriptor và reader, còn caller chịu trách nhiệm quản lý reader, stream và buffer theo đúng vòng đời.