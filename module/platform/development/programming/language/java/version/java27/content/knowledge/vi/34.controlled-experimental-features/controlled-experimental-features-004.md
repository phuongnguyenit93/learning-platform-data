# Thêm incubator module và kiểm tra nền tảng được hỗ trợ trong Java 27

Không phải mọi API đi kèm một bản JDK đều có cùng cam kết tương thích. Một số tính năng đã được chuẩn hóa và có thể dùng trong ứng dụng thông thường; một số **preview** cần bật chế độ thử nghiệm của ngôn ngữ hoặc JVM; và một số API được phát hành trong **incubator modules** để cộng đồng thử nghiệm, đo hiệu năng và gửi phản hồi trước khi quyết định thiết kế cuối cùng.

Trong chương **Tính năng thử nghiệm có kiểm soát** của chương trình **Java 27**, bài học này giải thích cách **nhận diện, thêm và kiểm tra incubator module** trên đúng bản JDK, cách khai báo cho `javac`, `java`, Gradle/Maven và CI, cùng cách xác định **nền tảng nào thực sự có module và có thể được tăng tốc**. Việc nạp module thành công chỉ chứng minh một điều kiện kỹ thuật; nó không chứng minh API đã ổn định hoặc sẽ đạt hiệu năng tối ưu trên mọi CPU.

**Tình trạng cụ thể của Java 27:** Vector API tiếp tục là **incubator lần thứ 12**, theo **JEP 537**, được phân phối dưới tên module `jdk.incubator.vector`. Tài liệu chính thức của module đánh dấu rõ API này **chưa ổn định và có thể bị loại bỏ ở phiên bản JDK tương lai**. Vì ràng buộc học thuật chỉ sử dụng kiến thức còn áp dụng hiện nay, bài dùng ví dụ **đúng Java 27**, đồng thời chủ động giới hạn chúng trong **thử nghiệm có kiểm soát**. Đường triển khai ổn định vẫn nên sử dụng API Java chính thức không incubating, trừ khi tổ chức chấp nhận, kiểm soát và kiểm thử rủi ro phụ thuộc incubator.

Nguồn chính thức: [Oracle JDK 27 — Module jdk.incubator.vector](https://docs.oracle.com/en/java/javase/27/docs/api/jdk.incubator.vector/module-summary.html), [Oracle — Significant Changes in JDK 27](https://docs.oracle.com/en/java/javase/27/migrate/significant-changes-jdk-27-release.html), [JEP 537 — Vector API (Twelfth Incubator)](https://openjdk.org/jeps/537).

## 1. Incubator module là gì?

**Incubator module** là một Java Platform Module System (JPMS) module được cung cấp cùng một bản JDK để nhà phát triển sử dụng API thử nghiệm. Khác với thư viện bên ngoài được đưa vào dependency repository, module `jdk.incubator.vector` của Java 27 nằm trong **JDK installation hoặc runtime image có chứa nó**.

~~~~text
JDK 27 (đầy đủ, có module Vector)
│
├── java.base                  API Java nền tảng
├── java.logging               API Java chuẩn
├── ...
└── jdk.incubator.vector       API Vector đang incubating
        │
        └── jdk.incubator.vector.IntVector,
            FloatVector, VectorSpecies, VectorMask ...
~~~~

**Ba mệnh đề phải tách biệt:**

1. **Module có trong JDK:** module system *quan sát được* `jdk.incubator.vector` từ system modules.
2. **Module đã được resolve:** module nằm trong **module graph** của chương trình chạy, thông thường sau khi chỉ định `--add-modules` hoặc được module khác yêu cầu qua `requires`.
3. **Tính năng có hiệu quả trên CPU hiện tại:** implementation có thể biên dịch vector operations thành SIMD instructions tối ưu; điều này phụ thuộc architecture, CPU flags, JIT compiler, đặc điểm dữ liệu và các điều kiện vận hành khác.

Một module **có thể hiện diện nhưng chưa được resolve**. Một module **có thể đã được resolve nhưng không có lợi ích hiệu năng rõ ràng** trên thiết bị hiện tại. Không đồng nhất cả ba với “đã hỗ trợ tốt”.

### 1.1. Incubator không phải API ổn định

Vector API Java 27 vẫn được đánh dấu *Incubating Feature*. Code biên dịch trên Java 27 có thể cần thay đổi khi chuyển sang Java tương lai nếu module đổi signature, đổi tên, được chuẩn hóa trong module khác hoặc bị gỡ khỏi JDK.

Những tính chất này cần ghi trong thiết kế:

- **Không có cam kết tương thích lâu dài** tương đương API đã hoàn thiện của Java SE.
- Tên module hoặc package có thể thay đổi; không “đóng băng” phụ thuộc này như một thư viện ổn định.
- Runtime image thu gọn có thể **không chứa** module dù full JDK cùng major có nó.
- Bộ cờ build, test, run và packaging phải **đồng nhất**.
- Cần có chính sách bật thử nghiệm, đo lường, tương thích và cách **thoát khỏi phụ thuộc incubator**.

### 1.2. Đối chiếu stable, preview và incubator

| Loại tính năng | Ví dụ Java 27 | Cách bật cơ bản | Mức cam kết |
| --- | --- | --- | --- |
| **Ổn định** | `java.util.concurrent.CompletableFuture`, `java.lang.foreign.Arena`, virtual threads | Dùng bình thường, không cần cờ preview/incubator | API đã hoàn thiện theo hợp đồng phiên bản |
| **Preview** | Structured Concurrency theo JEP 533 ở Java 27 | `--enable-preview` cùng release compiler và runtime tương ứng | Đang thử nghiệm; có thể thay đổi |
| **Incubator module** | `jdk.incubator.vector` — JEP 537 | `--add-modules jdk.incubator.vector` khi cần resolve module | API đang thử nghiệm, có thể đổi hoặc bị loại bỏ |
| **JVM experimental flag** | Các cờ VM mang trạng thái experimental, nếu có | Cơ chế flag HotSpot riêng, khi được JVM hỗ trợ | Không đồng nghĩa với JPMS incubator module |

**Lưu ý quan trọng:** `--enable-preview` **không** phải cờ bật Vector API. Ngược lại, `--add-modules jdk.incubator.vector` **không** tự bật mọi tính năng preview của Java 27. Hai cơ chế có mục tiêu và điều kiện khác nhau.

Ví dụ minh họa hai cách gọi **không thay thế nhau**:

~~~~text
# Incubator module; không cần --enable-preview chỉ để dùng Vector API:
javac --release 27 --add-modules jdk.incubator.vector VectorExperiment.java
java --add-modules jdk.incubator.vector VectorExperiment

# Chỉ để đối chiếu cú pháp preview; KHÔNG dùng cho Vector API:
# javac --enable-preview --release 27 PreviewDemo.java
# java --enable-preview PreviewDemo
~~~~

**Không tự bổ sung `--enable-preview` hoặc `--add-exports` khi gặp lỗi compile** nếu không hiểu nguyên nhân. `--add-exports` dùng cho các tình huống module encapsulation đặc biệt, **không phải đường hợp lệ để biến một module incubating thành API ổn định**.

## 2. Xác nhận JDK 27 có module cần dùng

### 2.1. Kiểm tra bản Java và bản compiler

~~~~text
java --version
javac --version
~~~~

Đầu ra phải thể hiện JDK/Java **27** nếu đang thực hiện ví dụ theo bài học. Nhưng `java --version` chỉ mô tả command `java` được gọi ở shell; trong dự án dùng Gradle, Maven, IDE hoặc custom runtime image, **JDK thực sự biên dịch và JVM thực sự chạy** có thể khác nhau.

Đừng suy luận “JDK major 27 = mọi vendor/installation đều chứa module giống hệt nhau” khi dùng runtime tùy chỉnh; cần kiểm tra **chính distribution hoặc image triển khai**.

### 2.2. Liệt kê các module hiện diện

Trên Linux/macOS:

~~~~text
java --list-modules | grep '^jdk.incubator.vector@'
~~~~

Với PowerShell:

~~~~powershell
java --list-modules | Select-String "^jdk\.incubator\.vector@"
~~~~

Output minh họa:

~~~~text
jdk.incubator.vector@27
~~~~

`--list-modules` cho biết các **module quan sát được** trong system module universe của Java launcher, không phải danh sách các module đã nằm trong **boot layer của application**. Nó cũng không xác nhận có SIMD instructions được sử dụng.

Nếu kiểm tra không thấy module:

1. Xác nhận launcher đang trỏ đúng JDK/runtime image.
2. Kiểm tra JDK distribution có module này không.
3. Nếu dùng `jlink` image, kiểm tra danh sách module được đưa vào image.
4. Đừng vội tải một JAR có tên `jdk.incubator.vector` từ nguồn không rõ để “thay thế” system module.

### 2.3. Xem mô tả JPMS module

~~~~text
java --describe-module jdk.incubator.vector
~~~~

Tùy phiên bản/implementation, output có thể cho biết module, packages được export và những modules được yêu cầu. Đây là cách **đọc metadata runtime** thay vì đoán theo tên thư mục JDK.

Nếu launcher báo không tìm thấy module, chưa nên bật cờ thử nghiệm ở CI production. Hãy xác định môi trường đang thiếu **module**, đang dùng **JDK sai**, hay có **custom image đã lược bớt module**.

### 2.4. `--validate-modules` và `--dry-run`

~~~~text
java --validate-modules
java --dry-run --add-modules jdk.incubator.vector -cp . VectorExperiment
~~~~

`--validate-modules` kiểm tra những vấn đề module system như xung đột module trong universe được xét; nó không kiểm thử phép tính vector. `--dry-run` khởi tạo runtime và kiểm tra cấu hình launcher mà **không gọi `main`** — hữu ích để xác minh cờ module khi class đã tồn tại. Lệnh thứ hai giả định file `VectorExperiment.class` nằm trong classpath hiện hành.

Không thay thế **unit tests** bằng `--dry-run`: nó chỉ kiểm chứng một phần đường khởi động.

## 3. Bật incubator module khi biên dịch và khi chạy

### 3.1. Classpath application: cần resolve module ở hai thời điểm

Nếu application ở **unnamed module** (chưa có `module-info.java`), một ví dụ thông dụng là:

~~~~text
# JDK 27, thư mục chứa VectorExperiment.java:
javac --release 27 --add-modules jdk.incubator.vector VectorExperiment.java

# Dùng module của runtime JDK 27:
java --add-modules jdk.incubator.vector -cp . VectorExperiment
~~~~

`--add-modules jdk.incubator.vector` yêu cầu module system **thêm module đó làm root khi resolve**. `javac` nhờ vậy thấy package được export; `java` nhờ vậy resolve module khi chương trình chạy.

Trong các bản JDK có incubator module, compiler/runtime có thể thông báo **warning về incubating module(s)**. Đây là cảnh báo trạng thái API, **không phải lỗi SQL, lỗi dependency hoặc lỗi module không tồn tại**. Không nên cố ẩn cảnh báo để hợp thức hóa phụ thuộc bất ổn.

**Nếu chỉ thêm cờ lúc biên dịch** nhưng chạy mà thiếu cờ:

- Module có thể không nằm trong boot layer.
- Một class trực tiếp sử dụng Vector API có thể không được nạp hoặc liên kết thành công, ví dụ phát sinh `NoClassDefFoundError`, tùy thời điểm JVM cần class.
- Không được suy đoán một ngoại lệ cụ thể trong mọi trường hợp; kiểm tra module graph và class loading.

**Nếu chỉ thêm cờ lúc chạy** nhưng compiler không resolve được module, `javac` có thể báo package không visible hoặc module không nằm trong graph. Cần sửa compile invocation.

### 3.2. `--module-path` không phải nơi chép JAR giả của incubator

`jdk.incubator.vector` là **system module** trong full JDK 27 phù hợp. Bạn thường **không cần đưa module vào Maven dependency hoặc copy JMOD thành JAR**. `--module-path` dành cho những **application/library modules** ở ngoài system modules khi cần JPMS resolution.

Các thành phần:

| Thành phần | Vai trò |
| --- | --- |
| `--add-modules jdk.incubator.vector` | Thêm system module làm root |
| `--module-path /path/to/modules` | Chỉ nơi tìm các module của ứng dụng/thư viện |
| `module-info.java: requires jdk.incubator.vector;` | Khai báo dependency tường minh của **named application module** |
| `--enable-preview` | Bật ngôn ngữ/VM preview cho release hiện tại; không bật incubator |

Nếu đặt một `jdk.incubator.vector.jar` tải từ Internet vào classpath, đó **không phải cách chuẩn để bổ sung system incubator module**; còn tăng nguy cơ phụ thuộc không đáng tin và khác ABI.

### 3.3. Named module: dùng `requires` trong `module-info.java`

Với ứng dụng JPMS có tên module `com.example.vectorlab`, khai báo:

~~~~java
// module-info.java
module com.example.vectorlab {
    requires jdk.incubator.vector;
}
~~~~

Đường `requires` cho phép module graph biết dependency **từ module ứng dụng đến module incubator**. Lệnh chạy named module sẽ resolve các `requires` khi module ứng dụng là root, nên **không phải lúc nào cũng cần thêm `--add-modules` một lần nữa** cho chính module đã được `requires` trực tiếp.

Ví dụ cấu trúc:

~~~~text
src/
  module-info.java
  com/example/vectorlab/Main.java
~~~~

Compile và chạy, giả sử mã `Main` có method `main` và JDK 27 thực sự chứa module:

~~~~text
javac --release 27 -d out src/module-info.java src/com/example/vectorlab/Main.java
java --module-path out --module com.example.vectorlab/com.example.vectorlab.Main
~~~~

Đây là **một cách cấu trúc source đơn-module**, không phải lệnh Gradle/Maven cho mọi project modular. Với multi-module build, các `--module-path`, `--module-source-path` và task settings có thể khác. Code ứng dụng khi dùng Vector API vẫn phụ thuộc trạng thái incubating của module ấy.

### 3.4. Đọc đúng lỗi JPMS

| Thông báo hoặc dấu hiệu | Nghi vấn chính | Hành động |
| --- | --- | --- |
| `package jdk.incubator.vector is not visible` | Module hiện diện nhưng chưa được resolve/đọc | Kiểm tra `--add-modules` hoặc `requires` |
| `module jdk.incubator.vector not found` | Wrong JDK/custom runtime hoặc module bị lược bỏ | `java --list-modules` trên đúng launcher |
| `package jdk.incubator.vector does not exist` | Compiler JDK không có API hoặc graph sai | Kiểm tra toolchain/flags |
| Warning “using incubating module(s)” | API thử nghiệm đang được sử dụng | Ghi nhận rủi ro; không xem là lỗi compile |
| `NoClassDefFoundError` khi chạy | Runtime graph thiếu module/class cần thiết | Kiểm tra launch flags/packaging |
| `UnsupportedClassVersionError` | JVM quá cũ so với bytecode | Kiểm tra `javac --release` và runtime version |
| Chương trình chạy nhưng không nhanh | CPU/JIT/workload không có lợi thế SIMD | Benchmark và kiểm tra vector shape |

Thông báo chính xác có thể thay đổi theo JVM/version. Hãy đọc đầy đủ stack trace, compiler arguments và output module introspection trước khi sửa cờ.

## 4. Kiểm tra module bằng Java API, không chỉ bằng shell

Ứng dụng hoặc công cụ CI có thể tự kiểm tra **module hiện diện** và **module đã resolve**, sử dụng API ổn định `java.lang.module.ModuleFinder` và `java.lang.ModuleLayer`.

### 4.1. Chương trình `IncubatorPlatformProbe.java` hoàn chỉnh

~~~~java
import java.lang.module.ModuleFinder;
import java.util.Optional;

public final class IncubatorPlatformProbe {
    private static final String VECTOR_MODULE =
            "jdk.incubator.vector";

    public static void main(String[] args) {
        System.out.println("Java version: " + Runtime.version());
        System.out.println("Java feature: " +
                Runtime.version().feature());
        System.out.println("VM: " +
                System.getProperty("java.vm.name"));
        System.out.println("OS: " +
                System.getProperty("os.name"));
        System.out.println("Architecture: " +
                System.getProperty("os.arch"));

        boolean present = ModuleFinder.ofSystem()
                .find(VECTOR_MODULE)
                .isPresent();

        Optional<Module> resolved = ModuleLayer.boot()
                .findModule(VECTOR_MODULE);

        System.out.println("Module present in runtime: " + present);
        System.out.println("Module resolved in boot layer: " +
                resolved.isPresent());

        if (!present) {
            System.out.println(
                    "Do not run incubator experiment: module unavailable.");
        } else if (resolved.isEmpty()) {
            System.out.println(
                    "Available but not resolved: check --add-modules.");
        } else {
            System.out.println(
                    "Module resolved. SIMD performance is not yet verified.");
        }
    }
}
~~~~

Đoạn này **không import API incubator**, vì thế có thể biên dịch và chạy bằng Java 27 mà không cần `--add-modules`:

~~~~text
javac --release 27 IncubatorPlatformProbe.java
java IncubatorPlatformProbe
java --add-modules jdk.incubator.vector IncubatorPlatformProbe
~~~~

Trên bản JDK 27 đầy đủ có Vector API, kết quả của hai lần chạy có thể tương tự:

~~~~text
# Không truyền --add-modules:
Module present in runtime: true
Module resolved in boot layer: false

# Có truyền --add-modules:
Module present in runtime: true
Module resolved in boot layer: true
~~~~

Những dòng là **ví dụ**, không phải cam kết output ở mọi cách launch: khi module được một **named module khác yêu cầu** hoặc cấu hình module graph khác, nó có thể đã resolve mà không cần thêm root theo cách minh họa. Nếu custom runtime không chứa `jdk.incubator.vector` thì `present=false`.

### 4.2. Mỗi phép kiểm tra đo một khía cạnh riêng

| Phép kiểm tra | Có thể xác minh | Không chứng minh được |
| --- | --- | --- |
| `Runtime.version().feature() == 27` | JVM đang thực thi là Java 27 | Module incubator có được đóng trong image không |
| `ModuleFinder.ofSystem().find(NAME)` | Module có thể được tìm từ system modules | Module đã được resolve |
| `ModuleLayer.boot().findModule(NAME)` | Module có trong boot layer | SIMD được JIT tối ưu trên CPU này |
| `System.getProperty("os.arch")` | Kiến trúc mà OS/JVM báo | Instruction flags thực tế hoặc hiệu năng |
| `java --list-modules` | Tập modules được runtime công bố | API có ổn định hay không |
| Unit tests so với scalar | Tính đúng của phép tính trong trường hợp đã kiểm tra | Lợi ích hiệu năng hoặc ổn định API tương lai |
| Microbenchmark phù hợp | Hiệu năng theo workload/thiết bị đo | Hiệu năng trên mọi môi trường production |

**Không dùng `Class.forName("jdk.incubator.vector.IntVector")` làm cơ chế kiểm tra chính** mà không hiểu class loading/module resolution. Nó có thể thất bại vì module chưa resolve dù module đang được cài trong JDK, dẫn đến kết luận sai là “JDK thiếu Vector API”.

### 4.3. Không để phép kiểm tra tự gây lỗi class loading

Một chương trình kiểm tra môi trường nên **không import hoặc khởi tạo** class trong `jdk.incubator.vector` khi nó đang quyết định module có sẵn hay không. Chương trình `IncubatorPlatformProbe` chỉ dùng **API ổn định của `java.base`**, do đó an toàn về mặt dependency đối với chính incubator module.

Nếu lớp kiểm tra có một field/static initializer trực tiếp dùng `IntVector`, một JVM thiếu module có thể thất bại trong quá trình load/link/initialize **trước khi** code kịp báo rằng module không tồn tại.

## 5. Nền tảng được hỗ trợ: khả năng chạy và khả năng tăng tốc SIMD

Vector API cho phép viết các phép toán theo **SIMD — Single Instruction, Multiple Data**: một vector chứa nhiều *lanes* cùng kiểu nguyên thủy, thao tác được áp dụng theo từng lane. Trong JDK 27, module hiện được mô tả là có thể chạy đúng cả trên nền tảng không có các SIMD instructions chuyên dụng, nhưng **lợi thế hiệu năng không được bảo đảm**.

### 5.1. Nền tảng tối ưu được ghi trong tài liệu Vector API

Javadoc của `Vector` Java 27 cho biết implementation hiện được tối ưu tốt nhất trên:

| Kiến trúc | Hỗ trợ tăng tốc được tài liệu nêu | Lưu ý |
| --- | --- | --- |
| **x64** | Các CPU có **AVX2** và tới **AVX-512** | Một số tính năng masking/instructions có giới hạn |
| **AArch64** | **NEON** | API thiết kế hướng đến SVE nhưng các đường tối ưu SVE cụ thể chưa được triển khai đầy đủ theo mô tả hiện hành |
| Nền tảng khác hoặc không có SIMD phù hợp | API vẫn có thể thực thi đúng | **Không kỳ vọng đặc biệt về hiệu năng** |

Đây là **mô tả implementation tại Java 27**, không phải hợp đồng hardware acceleration cho mọi vendor/JVM/CPU. Thông tin chi tiết có thể thay đổi trong các bản JDK tiếp theo; không hardcode logic ứng dụng dựa trên giả định “ARM luôn dùng SVE” hoặc “x64 luôn có AVX-512”.

### 5.2. CPU architecture không đủ để khẳng định instruction set

~~~~java
System.out.println(System.getProperty("os.arch"));
~~~~

`os.arch` có thể trả những giá trị như `amd64`, `x86_64` hoặc `aarch64` tùy môi trường. Nhưng giá trị này **không báo đủ CPU feature flags**. Ví dụ hai CPU x64 có thể khác nhau về hỗ trợ AVX2/AVX-512; môi trường ảo hóa/container còn có thể che bớt CPU features.

Nếu performance là một điều kiện chấp nhận, cần:

1. Ghi chính xác **JDK vendor/update và JVM implementation**.
2. Ghi OS/architecture và CPU capabilities bằng công cụ hệ thống đáng tin.
3. Chạy phép tính **đúng kết quả**.
4. Chạy benchmark sau warm-up trên workload đại diện.
5. Xác nhận kết quả trên từng môi trường mục tiêu, không suy từ tên CPU chung.

### 5.3. Vector species là thông số do runtime lựa chọn

`VectorSpecies<E>` mô tả kiểu phần tử, số lanes và vector shape. Java 27 cung cấp:

~~~~java
import jdk.incubator.vector.IntVector;
import jdk.incubator.vector.VectorSpecies;

VectorSpecies<Integer> species = IntVector.SPECIES_PREFERRED;

System.out.println("Lanes: " + species.length());
System.out.println("Bits: " + species.vectorBitSize());
System.out.println("Shape: " + species.vectorShape());
~~~~

Đoạn này phải đặt trong một method/class được biên dịch với `--add-modules jdk.incubator.vector`. Giá trị của `SPECIES_PREFERRED` được chọn theo **nền tảng đang chạy**, không phải một hằng số số lanes có thể đoán trước trên mọi máy.

Không cần ép tất cả máy dùng `SPECIES_512` để “tối ưu”. Khi phần cứng không có khả năng phù hợp, lựa chọn cố định có thể làm giảm hiệu quả hoặc tăng chi phí thực thi. Với ứng dụng thử nghiệm đa nền tảng, `SPECIES_PREFERRED` thường là điểm khởi đầu hợp lý để đánh giá.

**Không viện dẫn phương thức `species.isSupported()` như một API chung**: interface `VectorSpecies` Java 27 được tài liệu hóa có `length`, `loopBound`, `vectorBitSize` và những API khác nhưng không có một phép kiểm tra boolean như vậy để quyết định toàn bộ khả năng chạy/tăng tốc trên CPU.

### 5.4. Benchmark mới xác nhận lợi ích thật

Một vòng lặp scalar có thể được HotSpot tự tối ưu/vectorize trong một số trường hợp. Ngược lại, dùng Vector API có thể tạo overhead cho dữ liệu nhỏ, phép toán nhiều nhánh hoặc trường hợp memory-bound. Không kết luận “sử dụng Vector API = luôn nhanh hơn”.

Đánh giá performance cần warm-up, tránh dead-code elimination, kiểm soát GC, dữ liệu và CPU frequency, đo latency/throughput phù hợp, cũng như so sánh với implementation scalar **đã tối ưu**. Một công cụ như **JMH** có thể giúp tổ chức microbenchmark; cần dùng phiên bản JMH được phê duyệt, không viết phép đo `System.nanoTime()` một lần rồi công bố hệ số tăng tốc.

## 6. Ví dụ đầy đủ: cộng hai mảng bằng Vector API và scalar fallback

Code dưới đây chỉ dùng `jdk.incubator.vector.IntVector` và `VectorSpecies` theo JDK 27; **không dùng API preview**. Lưu thành `VectorExperiment.java` trong thư mục thử nghiệm riêng.

~~~~java
import java.util.Arrays;
import java.util.Objects;
import jdk.incubator.vector.IntVector;
import jdk.incubator.vector.VectorSpecies;

public final class VectorExperiment {
    private static final VectorSpecies<Integer> SPECIES =
            IntVector.SPECIES_PREFERRED;

    private VectorExperiment() {
    }

    static int[] addScalar(int[] left, int[] right) {
        checkInputs(left, right);
        int[] result = new int[left.length];

        for (int i = 0; i < left.length; i++) {
            result[i] = left[i] + right[i];
        }
        return result;
    }

    static int[] addVector(int[] left, int[] right) {
        checkInputs(left, right);
        int[] result = new int[left.length];

        int laneCount = SPECIES.length();
        int bound = SPECIES.loopBound(left.length);
        int i = 0;

        for (; i < bound; i += laneCount) {
            IntVector a = IntVector.fromArray(SPECIES, left, i);
            IntVector b = IntVector.fromArray(SPECIES, right, i);
            a.add(b).intoArray(result, i);
        }

        // Xử lý những phần tử cuối không đủ một vector đầy.
        for (; i < left.length; i++) {
            result[i] = left[i] + right[i];
        }

        return result;
    }

    private static void checkInputs(int[] left, int[] right) {
        Objects.requireNonNull(left, "left");
        Objects.requireNonNull(right, "right");
        if (left.length != right.length) {
            throw new IllegalArgumentException(
                    "Input arrays must have the same length");
        }
    }

    public static void main(String[] args) {
        int[] left = {1, 2, 3, 4, 5, 6, 7};
        int[] right = {10, 20, 30, 40, 50, 60, 70};

        int[] scalar = addScalar(left, right);
        int[] vector = addVector(left, right);

        if (!Arrays.equals(scalar, vector)) {
            throw new AssertionError("Vector result differs from scalar");
        }

        System.out.println("Preferred lanes: " + SPECIES.length());
        System.out.println(Arrays.toString(vector));
        // [11, 22, 33, 44, 55, 66, 77]
    }
}
~~~~

Chạy bằng **JDK 27 có system module `jdk.incubator.vector`**:

~~~~text
javac --release 27 --add-modules jdk.incubator.vector VectorExperiment.java
java --add-modules jdk.incubator.vector VectorExperiment
~~~~

### 6.1. Vì sao ví dụ xử lý được kích thước mảng bất kỳ?

`SPECIES.loopBound(left.length)` trả chỉ số giới hạn lớn nhất là **bội số của số lanes** không lớn hơn chiều dài mảng. Vòng vector xử lý các block đầy đủ; vòng scalar sau đó xử lý những phần tử dư.

Ví dụ khi số lanes là 4 và mảng có 7 phần tử:

~~~~text
Index:        0  1  2  3 | 4  5  6
Vector block: [==========]|
Scalar tail:               [======]
loopBound(7) = 4
~~~~

Trên CPU chọn 8 lanes, một mảng 7 phần tử có thể không chạy vòng vector nào và được xử lý **hoàn toàn bằng scalar tail**. Kết quả vẫn đúng, chỉ lợi ích hiệu năng không chắc có.

### 6.2. Tính đúng trước tối ưu

Cả hai phương thức dùng phép cộng `int` nên có cùng ngữ nghĩa **tràn số nguyên theo Java** cho từng phần tử; code không tự chuyển sang phép cộng bão hòa hoặc số lớn hơn. Nếu domain cần phát hiện overflow bằng `Math.addExact`, **không thể thay bằng `IntVector.add` rồi mặc định tính chất overflow vẫn giống**; phải thiết kế chính sách số học riêng.

Khi dùng `float` hoặc `double`, thứ tự phép tính, kết hợp các phép reduction và xử lý NaN/signed zero có thể ảnh hưởng đến so sánh; không mặc định mọi phép toán vector đều đồng nhất từng bit với mọi thứ tự tính scalar. Hãy định nghĩa độ chính xác cần thiết theo nghiệp vụ.

### 6.3. Một chương trình không tự chuyển thành portable chỉ vì có scalar method

`VectorExperiment` **import trực tiếp** incubator classes. Điều đó nghĩa là bản class này vẫn có **phụ thuộc nhị phân** vào module, dù chứa `addScalar`.

Để có bản stable thật sự chạy trên runtime **không có module**, hãy đặt scalar implementation vào một artifact/module **không phụ thuộc incubator**. Đưa code vector vào một module/thành phần *opt-in* riêng rồi chọn tải nó **chỉ sau khi** môi trường đã được kiểm tra.

Không dựa vào một nhánh `if (vectorAvailable)` trong class có static initializer hoặc method signature tham chiếu Vector API rồi khẳng định sẽ tránh được mọi lỗi class loading. Phần phụ thuộc incubator nên được **cô lập ở ranh giới module/artifact**.

## 7. Gradle: chuyển đúng cờ vào compiler, test JVM và launcher

Trong một build Java, có **nhiều tiến trình hoặc nhiệm vụ**:

~~~~text
Gradle daemon JVM
       |
       +--> JavaCompile task -> javac flags
       |
       +--> Test task -> test JVM flags
       |
       +--> JavaExec/run task -> application JVM flags
       |
       +--> installDist scripts -> launcher JVM flags
~~~~

Việc thêm `--add-modules` vào **Gradle daemon JVM** không có nghĩa task `JavaCompile` và application/test JVM tự động nhận cùng cờ. Đây là nguồn lỗi phổ biến khi code biên dịch được ở IDE nhưng không chạy qua CI.

### 7.1. Cấu hình Kotlin DSL đầy đủ cho một lab Java 27

Ví dụ `build.gradle.kts` của một project thử nghiệm, dùng **Gradle có hỗ trợ Java 27 (từ Gradle 9.8.0)**:

~~~~kotlin
import org.gradle.api.tasks.compile.JavaCompile
import org.gradle.api.tasks.testing.Test

plugins {
    application
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(27)
    }
}

tasks.withType<JavaCompile>().configureEach {
    options.release.set(27)
    options.encoding = "UTF-8"
    options.compilerArgs.addAll(
        listOf("--add-modules", "jdk.incubator.vector")
    )
}

tasks.withType<Test>().configureEach {
    jvmArgs("--add-modules", "jdk.incubator.vector")
}

application {
    mainClass.set("VectorExperiment")
    applicationDefaultJvmArgs = listOf(
        "--add-modules", "jdk.incubator.vector"
    )
}
~~~~

**Chú giải theo đối tượng được cấu hình:**

| Cấu hình | Áp dụng lên | Lý do |
| --- | --- | --- |
| `JavaLanguageVersion.of(27)` | Java toolchain được Gradle chọn | Có compiler/runtime Java 27 |
| `options.release.set(27)` | `javac` | Khóa mức ngôn ngữ/class file/API theo 27 |
| `options.compilerArgs` | `javac` | Resolve incubator module khi compile |
| `Test.jvmArgs` | JVM mà Gradle Test dùng | Resolve module khi chạy test |
| `applicationDefaultJvmArgs` | Task `run` và launch scripts được Application plugin tạo | Resolve module khi chạy ứng dụng thử nghiệm |

Trong ví dụ, `mainClass` nằm ở unnamed module/classpath. Nếu sử dụng **named module**, cấu hình `application.mainModule` và `module-info.java` sẽ khác; không áp nguyên xi cách classpath lên mọi project modular.

**Chú ý về Gradle:** `applicationDefaultJvmArgs` không phải một cơ chế toàn cục tự truyền vào mọi task Java do plugin bên thứ ba tạo ra. Nếu integration tests, benchmark hoặc code generator tạo JVM riêng, phải cấu hình **đúng task/JVM đó**.

### 7.2. Gradle Groovy DSL tương đương

Với project sử dụng `build.gradle`:

~~~~groovy
plugins {
    id 'application'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(27)
    }
}

tasks.withType(JavaCompile).configureEach {
    options.release = 27
    options.compilerArgs += [
        '--add-modules', 'jdk.incubator.vector'
    ]
}

tasks.withType(Test).configureEach {
    jvmArgs '--add-modules', 'jdk.incubator.vector'
}

application {
    mainClass = 'VectorExperiment'
    applicationDefaultJvmArgs = [
        '--add-modules', 'jdk.incubator.vector'
    ]
}
~~~~

Đây là **lựa chọn thay thế** cho Kotlin DSL; không cần tạo cả hai file cùng lúc. Hãy giữ phiên bản Gradle đã được nhóm phê duyệt qua Gradle Wrapper và kiểm tra JDK 27 toolchain thực tế.

### 7.3. Các lệnh kiểm tra Gradle

~~~~text
./gradlew --version
./gradlew -q javaToolchains
./gradlew clean test
./gradlew run
~~~~

Trên Windows dùng `.\gradlew.bat`. `./gradlew --version` báo JVM chạy Gradle; `javaToolchains` liệt kê toolchains phát hiện được; log của `compileJava` và `test` giúp xác nhận JDK/flags thực tế.

Nếu một project chỉ thí nghiệm Vector API, nên đặt bài lab trong **source set hoặc subproject riêng** để tránh thêm `--add-modules` cho toàn bộ code production.

### 7.4. Có nên chuyển cờ qua `org.gradle.jvmargs`?

`org.gradle.jvmargs` cấu hình JVM chạy **Gradle daemon**, không phải cách khuyến nghị để truyền incubator module cho mọi `JavaCompile`, `Test` và `JavaExec` task. Đừng ghi:

~~~~properties
# Không dùng làm cách thay thế duy nhất cho các task JVM:
org.gradle.jvmargs=--add-modules jdk.incubator.vector
~~~~

Nếu yêu cầu incubator chỉ cho một module lab, càng không nên gắn cờ cho toàn bộ daemon. Hãy cấu hình **nơi tiêu thụ module**: compile, test và runtime của đúng bài thử nghiệm.

## 8. Maven: compilerArgs và JVM của test runner

Maven Compiler Plugin **3.16.0** có `compilerArgs` để truyền những flag `javac` được hỗ trợ; Maven Surefire Plugin chạy unit tests và có thể cấu hình `argLine` cho JVM được fork.

### 8.1. Ví dụ POM cho project thử nghiệm Java 27

Phần sau là các phần tử đặt trong một `pom.xml` Maven 3 hợp lệ; project vẫn cần `groupId`, `artifactId` và các trường POM cơ bản:

~~~~xml
<properties>
    <maven.compiler.release>27</maven.compiler.release>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
</properties>

<build>
    <plugins>
        <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-compiler-plugin</artifactId>
            <version>3.16.0</version>
            <configuration>
                <release>27</release>
                <compilerArgs>
                    <arg>--add-modules</arg>
                    <arg>jdk.incubator.vector</arg>
                </compilerArgs>
            </configuration>
        </plugin>
        <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-surefire-plugin</artifactId>
            <version>3.6.1</version>
            <configuration>
                <forkCount>1</forkCount>
                <argLine>--add-modules jdk.incubator.vector</argLine>
            </configuration>
        </plugin>
    </plugins>
</build>
~~~~

**Phân biệt:**

- `<release>27</release>` thiết lập `javac --release 27`, **không tự chọn JDK 27**.
- `<compilerArgs>` đưa incubator module vào **compiler invocation**.
- `<argLine>` đưa cờ vào **forked JVM của Surefire**, không phải Maven JVM.
- Project cần **JDK 27 compiler** qua Maven Toolchains Plugin hoặc môi trường Maven thích hợp; khi dùng toolchain, phải xác minh được selection.

Nếu có plugin coverage như JaCoCo cần gắn Java agent vào `argLine`, **không ghi đè vô tình** chuỗi agent arguments. Cần ghép các tham số theo hướng dẫn đúng version của Surefire/coverage plugin; không giả định một lần đặt `argLine` đã giữ mọi cờ JVM được tool khác thêm.

### 8.2. Chạy ứng dụng sau khi Maven biên dịch

~~~~text
mvn --version
mvn clean test

# Giả sử VectorExperiment là class không có package:
java --add-modules jdk.incubator.vector -cp target/classes VectorExperiment
~~~~

Lệnh `java` cuối là **launcher bên ngoài Maven**; nó phải trỏ tới runtime Java 27 chứa module. Không suy ra Maven đã cấu hình `<argLine>` cho Surefire thì lệnh Java độc lập ở production tự động nhận flag.

Nếu dùng Maven Exec Plugin, cần kiểm tra goal và mode thực thi (trong hoặc ngoài Maven JVM) và tài liệu version tương ứng, thay vì tự suy rằng mọi JVM arguments sẽ được forward.

### 8.3. Named module Maven khác classpath Maven

Nếu application có `module-info.java` chứa:

~~~~java
module com.example.vectorlab {
    requires jdk.incubator.vector;
}
~~~~

Maven Compiler Plugin có thể dùng modular compilation, trong đó dependency module được mô tả bằng `requires`. Cần kiểm tra cách plugin xử lý `module-path`/`classpath`, test runtime và module graph trong build thực tế. **Không** thêm mọi flag classpath chỉ vì đã thấy một hướng dẫn cho unnamed module.

### 8.4. Không khai báo system incubator module như Maven dependency bên thứ ba

Phản ví dụ:

~~~~xml
<!-- KHÔNG làm như này để 'cài' jdk.incubator.vector. -->
<!--
<dependency>
    <groupId>jdk.incubator</groupId>
    <artifactId>vector</artifactId>
    <version>27</version>
</dependency>
-->
~~~~

Trong Java 27, `jdk.incubator.vector` được phân phối bằng **JDK module image**. Phụ thuộc runtime bắt nguồn từ **JDK installation**, không phải tọa độ Maven Central mặc định.

## 9. Kiểm tra nền tảng ở CI: điều kiện chạy, điều kiện hiệu năng

Một pipeline kiểm thử thử nghiệm nên phân biệt hai cổng:

1. **Functional gate:** module tồn tại, được resolve, code biên dịch, kết quả đúng.
2. **Performance gate:** CPU/JVM mục tiêu thực sự mang lại cải thiện đủ lớn cho workload; các chỉ số này có thể chịu nhiễu và cần phương pháp đo nghiêm ngặt.

Không để việc “microbenchmark nhanh trên một laptop” thay thế ma trận tương thích JVM/OS/architecture hoặc test nghiệp vụ.

### 9.1. Preflight của job CI dùng JDK 27

Ví dụ shell POSIX trong **job thử nghiệm có quyền phù hợp**:

~~~~sh
set -eu

java --version
javac --version
java --list-modules | grep '^jdk.incubator.vector@'

javac --release 27 --add-modules jdk.incubator.vector \
      VectorExperiment.java

java --add-modules jdk.incubator.vector \
     VectorExperiment
~~~~

Script dùng tên file có sẵn ở thư mục hiện hành. Nó **thất bại** nếu JDK không công bố module hoặc compile/run lỗi; đây là hành vi phù hợp cho một job bắt buộc phải kiểm thử Vector API.

Trên Windows PowerShell, nên viết bước kiểm tra module rõ ràng thay vì chỉ dựa trên pipeline grep:

~~~~powershell
java --version
javac --version

$modules = java --list-modules
if (-not ($modules | Select-String "^jdk\.incubator\.vector@")) {
    throw "Required incubator module is absent"
}

javac --release 27 --add-modules jdk.incubator.vector VectorExperiment.java
if ($LASTEXITCODE -ne 0) {
    throw "Compilation failed"
}

java --add-modules jdk.incubator.vector VectorExperiment
if ($LASTEXITCODE -ne 0) {
    throw "Runtime check failed"
}
~~~~

**Lưu ý:** PowerShell 5.1 không xử lý mọi chuỗi lệnh và lỗi native giống PowerShell mới hơn; kiểm tra `$LASTEXITCODE` giúp CI **không báo PASS khi javac/java thất bại**.

### 9.2. Ma trận nền tảng nên xem xét

| Môi trường | Kiểm tra bắt buộc | Kiểm tra hiệu năng nếu cần |
| --- | --- | --- |
| Linux x64 với JDK 27 chứa module | Compile/run, so kết quả scalar | CPU flags AVX2/AVX-512, JIT, benchmark |
| Linux AArch64 với JDK 27 chứa module | Compile/run, dữ liệu biên | NEON, shape ưu tiên, benchmark |
| Windows x64 dùng JDK 27 | Launcher flags, Gradle/Maven tests | Kiểm tra CPU/JIT/OS phiên bản thật |
| macOS được vendor JDK 27 hỗ trợ | Đúng module/version, kết quả phép tính | Benchmark đúng architecture thiết bị |
| Custom `jlink` runtime Java 27 | `--list-modules` trên **image cuối** | Quan sát JIT và performance sau đóng gói |
| Runtime thiếu module hoặc JDK khác | Scalar baseline phải hoạt động độc lập | Không chạy phép thử incubator bắt buộc |

Ma trận là **gợi ý thiết kế**, không cam kết mỗi ô đều có một JDK distribution được mọi vendor phát hành. Nếu target OS/CPU không được tổ chức hỗ trợ hoặc vendor không cung cấp JDK 27 cho nó, phải ghi rõ trạng thái **unsupported** thay vì chạy script trên máy khác rồi đánh dấu PASS.

### 9.3. Khi nào nên SKIP, FAIL và FALLBACK?

| Tình huống | Chính sách phù hợp |
| --- | --- |
| Job dành riêng để kiểm tra Vector API Java 27, module không tồn tại | **FAIL** vì môi trường không đáp ứng điều kiện thử nghiệm |
| Job compatibility baseline cho runtime không có module | **PASS** nếu scalar implementation hoạt động |
| Một test benchmark tùy chọn chưa có hardware đo phù hợp | **SKIP có lý do**, ghi rõ hardware/metrics bị thiếu |
| Tính năng incubator có thể bị vô hiệu hóa bằng feature flag | **FALLBACK** theo policy, không giấu exception không liên quan |
| Bản build chính có dependency trực tiếp vào incubator dù sản phẩm yêu cầu stable runtime | **FAIL kiến trúc** hoặc yêu cầu review rủi ro chính thức |

Không cho một job dùng cờ `continueOnError` hoặc `ignoreFailures` toàn cục rồi vẫn phát hành artifact chưa qua functional gate. Nếu phép thử incubator là optional, thể hiện **optional và lý do skip** công khai trong report.

## 10. Custom runtime image: `jlink` có thể làm mất incubator module

Một build chạy trên full JDK 27 có thể thành công, nhưng artifact triển khai dùng **custom runtime image** tạo bởi `jlink` chỉ chứa một tập module tối giản. Nếu image không có `jdk.incubator.vector` thì nó **không thể resolve module ấy**, dù `java --version` trong image vẫn là Java 27.

### 10.1. Tạo runtime image dành riêng cho lab

Giả sử lệnh `jlink` đến từ **full JDK 27** có đủ JMODs:

~~~~text
jlink --add-modules java.base,jdk.incubator.vector --output vector-lab-runtime
~~~~

Sau đó kiểm tra **bằng launcher của image vừa tạo**:

~~~~text
vector-lab-runtime/bin/java --version
vector-lab-runtime/bin/java --list-modules
vector-lab-runtime/bin/java --describe-module jdk.incubator.vector
~~~~

Nếu `VectorExperiment.class` nằm trong thư mục hiện hành:

~~~~text
vector-lab-runtime/bin/java --add-modules jdk.incubator.vector \
    -cp . VectorExperiment
~~~~

Lệnh có `\` là cú pháp tiếp dòng **POSIX shell**. Trên Windows PowerShell, hãy dùng một dòng hoặc cú pháp tiếp dòng phù hợp, ví dụ:

~~~~powershell
.\vector-lab-runtime\bin\java.exe --add-modules jdk.incubator.vector -cp . VectorExperiment
~~~~

**Lưu ý:** Image `jlink` mang tính **nền tảng cụ thể**: OS, architecture và các chi tiết distribution/runtime đi kèm. Không copy image Linux x64 sang Windows hoặc AArch64 rồi kỳ vọng chạy được. Vì Vector API có yếu tố tối ưu phần cứng, cần kiểm thử trên **nền tảng triển khai cuối**, không chỉ trên máy build.

### 10.2. Image thiếu module vẫn có thể báo Java 27

Ví dụ đối chiếu:

~~~~text
# Image tối giản không bao gồm incubator:
jlink --add-modules java.base --output scalar-runtime

# Lệnh sau vẫn có thể báo Java 27:
scalar-runtime/bin/java --version

# Nhưng không có jdk.incubator.vector:
scalar-runtime/bin/java --list-modules
~~~~

Nếu cố chạy chương trình Vector trên image này bằng `--add-modules jdk.incubator.vector`, module resolution sẽ thất bại. **Không sửa bằng `--enable-preview`** vì tính năng đó không liên quan đến sự thiếu vắng system module.

### 10.3. Không coi `jdeps` là kiểm chứng duy nhất

`jdeps` hỗ trợ phân tích phụ thuộc lớp/module, hữu ích để tìm những module được tham chiếu tĩnh. Nhưng với reflection, `ServiceLoader`, native libraries hoặc class được tải động, đồ thị phụ thuộc runtime có thể rộng hơn kết quả phân tích tĩnh.

Một quy trình an toàn:

1. Dùng dependency analysis để lập danh sách module dự kiến.
2. Khai báo `--add-modules` phù hợp khi tạo image.
3. Đọc `--list-modules` trên **final runtime image**.
4. Chạy integration tests/smoke tests **bằng launcher của image đó**.
5. Nếu có plugin/vector implementation tùy chọn, test cả khi module **hiện diện** và **không hiện diện** theo hợp đồng.

Đừng chỉ kiểm tra `java --list-modules` trên JDK build host rồi suy đoán image cuối giống hệt.

### 10.4. `jpackage` và container cũng phải chuyển điều kiện module

Nếu `jpackage` tạo runtime image riêng cho ứng dụng, cần chắc rằng module incubator được đưa vào image theo cấu hình, và launcher có module graph đúng. Với container, kiểm tra runtime **bên trong final image** thay vì chỉ kiểm tra Docker builder stage.

Một hệ thống có base image Java 27 nhưng sử dụng `jlink` để loại module thử nghiệm sẽ không tự có Vector API. Khi chuyển môi trường, đừng dùng tên tag image làm bằng chứng module có mặt: kiểm tra **digest, runtime module list và kết quả smoke test**.

## 11. Thiết kế scalar baseline và tính năng opt-in

Nội dung này rất quan trọng với yêu cầu “chỉ dùng kiến thức hiện hành, không dùng API thử nghiệm như một phần ổn định mặc định”.

### 11.1. Phân tách dependency ở ranh giới artifact

Một kiến trúc đơn giản:

~~~~text
stable-core/
    ArrayOperations.java
    ScalarArrayOperations.java
       └── không import jdk.incubator.vector

optional-vector-lab/
    VectorArrayOperations.java
       └── phụ thuộc incubator, chỉ build/chạy với JDK 27 phù hợp

launcher / test harness
    ├── kiểm tra Java version và system module
    ├── chọn optional artifact theo cấu hình/kiểm tra
    └── mặc định chạy stable scalar implementation
~~~~

**Lợi ích:**

- Stable core vẫn có thể chạy trong custom runtime image không có module incubator.
- Optional implementation có vòng đời, dependency và CI job riêng.
- Khi JDK tương lai thay đổi/gỡ module, có thể tạm thời **ngừng phân phối vector lab** mà không phá chức năng cốt lõi.
- Benchmark có scalar baseline thật để so sánh.

### 11.2. Giao diện ổn định, không chứa incubator type trong public API

Trong stable module, giữ contract là API Java bình thường:

~~~~java
public interface ArrayOperations {
    int[] add(int[] left, int[] right);
}
~~~~

Implementation ổn định:

~~~~java
import java.util.Objects;

public final class ScalarArrayOperations implements ArrayOperations {
    @Override
    public int[] add(int[] left, int[] right) {
        Objects.requireNonNull(left);
        Objects.requireNonNull(right);
        if (left.length != right.length) {
            throw new IllegalArgumentException("Array lengths differ");
        }

        int[] result = new int[left.length];
        for (int i = 0; i < left.length; i++) {
            result[i] = left[i] + right[i];
        }
        return result;
    }
}
~~~~

Hai đoạn trên là **hai tệp Java riêng** (`ArrayOperations.java` và `ScalarArrayOperations.java`), không phải một tệp duy nhất chứa cả hai public type. Cả hai có thể được biên dịch bằng Java 27 **không cần `--add-modules`**.

Trong `optional-vector-lab`, implementation Vector có thể triển khai cùng `ArrayOperations` nhưng được build/deploy **chỉ khi** runtime đáp ứng điều kiện thử nghiệm.

### 11.3. Chọn optional implementation bằng hợp đồng rõ ràng

Một số phương án:

- **Chọn artifact lúc deploy:** bản stable chỉ chứa scalar; bản lab chứa cả scalar và vector.
- **Chọn module lúc launch:** cung cấp optional Vector module sau preflight; cấu hình rõ module path và flags.
- **Service provider/cơ chế plugin:** chỉ tải implementation sau khi có bằng chứng module và môi trường phù hợp; xử lý lỗi provider discovery theo chính sách.

Không nên dùng:

~~~~java
// Phản ví dụ: class ở đường chạy stable đã phụ thuộc Vector API.
// import jdk.incubator.vector.IntVector;
// private static final IntVector VALUE = ...;
~~~~

Ngay cả khi có `if (featureEnabled)` ở sau, lớp chứa direct dependency có thể gây lỗi khi load/link/initialize trên môi trường thiếu module.

**Ghi chú:** `ServiceLoader` hoặc reflection không tự bảo đảm không có dependency leak; optional provider phải được đóng gói và thử nghiệm thực sự trên runtime **không có incubator**. Đừng dùng `catch (Throwable)` rồi âm thầm bỏ qua mọi lỗi — cách đó có thể che cả bug nghiêm trọng không liên quan tới module.

### 11.4. Khi nào nên vô hiệu hóa thử nghiệm?

Ví dụ policy:

~~~~text
Vector lab enabled khi TẤT CẢ điều kiện sau đúng:
  - Java feature == 27 (hoặc release được nhóm kiểm chứng riêng)
  - system module jdk.incubator.vector hiện diện
  - module được resolve theo launcher cấu hình
  - optional implementation đã qua functional tests
  - nền tảng thuộc test matrix được phép
  - người vận hành/chủ sở hữu bật experimental feature flag

Nếu một điều kiện không đạt:
  - chuyển về stable scalar implementation
  - ghi sự kiện và lý do nếu có ý nghĩa vận hành
  - không ngụy tạo kết quả SIMD hoặc benchmark thành PASS
~~~~

Không phải mọi môi trường đều cần tự động fallback trong cùng process. Một ứng dụng có yêu cầu an toàn cao có thể chọn **không triển khai optional artifact** ở production, vừa đơn giản vừa giảm rủi ro tích hợp.

## 12. Kiểm thử tính đúng theo số lanes và dữ liệu biên

Test trên một mảng có đúng 8 phần tử thường không đủ. `SPECIES_PREFERRED.length()` có thể khác giữa CPU/JVM, và lỗi thường xuất hiện ở vòng xử lý **tail** hoặc khi mảng nhỏ hơn một vector.

### 12.1. Ma trận dữ liệu thử nghiệm

| Nhóm | Kích thước / dữ liệu | Điều cần xác minh |
| --- | --- | --- |
| Input rỗng | `length = 0` | Không đọc vượt mảng; kết quả rỗng |
| Ngắn hơn một vector | `1, 2, 3` | Scalar tail đúng |
| Bằng số lanes | `species.length()` | Một vector đầy đủ |
| Lớn hơn một vector một phần tử | `species.length() + 1` | Vector loop + một phần tail |
| Không chia hết lanes | `7, 13, 31` | Không bỏ/ghi thừa phần tử |
| Nhiều block | `1024` hoặc dữ liệu dài phù hợp | Kết quả đúng qua nhiều iteration |
| Giá trị âm/zero | `-1, 0, 1` | Dấu và zero đúng |
| Giá trị biên int | `Integer.MAX_VALUE`, `Integer.MIN_VALUE` | Ngữ nghĩa overflow phù hợp |
| Độ dài hai input khác nhau | `[1,2]` và `[3]` | `IllegalArgumentException` theo contract |
| Tham chiếu null | `null` | `NullPointerException` được báo rõ |
| Nhiều platform | x64, AArch64, image khác nhau | Tính đúng không phụ thuộc vector shape |

### 12.2. Đoạn kiểm thử bổ sung cho `VectorExperiment`

Đặt **method** sau vào trong class `VectorExperiment` (hoặc một test class cùng package truy cập được `addScalar` và `addVector`):

~~~~java
static void verifyManyLengths() {
    int[] sizes = {
        0, 1, 2, 3, 7, 8, 15, 16, 17, 31, 32, 33, 1024
    };

    for (int size : sizes) {
        int[] a = new int[size];
        int[] b = new int[size];

        for (int i = 0; i < size; i++) {
            a[i] = (i % 2 == 0) ? i : -i;
            b[i] = Integer.MAX_VALUE - i;
        }

        int[] expected = addScalar(a, b);
        int[] actual = addVector(a, b);

        if (!Arrays.equals(expected, actual)) {
            throw new AssertionError(
                    "Different results for size=" + size);
        }
    }
}
~~~~

Nếu thêm vào `main`:

~~~~java
verifyManyLengths();
System.out.println("All vector/scalar comparisons passed");
~~~~

Đoạn này là kiểm thử logic **không cần thread concurrency**, nhưng cần runtime có Vector module. Nên đưa các kích thước `SPECIES.length() - 1`, `SPECIES.length()` và `SPECIES.length() + 1` vào automated tests để kiểm tra trên từng platform.

### 12.3. Không dùng benchmark thay unit tests

Các phương thức vector có thể cho kết quả đúng nhưng không nhanh hơn scalar, và ngược lại một benchmark có kết quả nhanh **không bảo đảm mọi dữ liệu biên đúng**. Tách:

- **Functional testing:** strict correctness theo inputs và số lanes.
- **Compatibility testing:** JDK, modules, OS/CPU.
- **Performance testing:** benchmark nhiều iteration có kiểm soát và thresholds phù hợp.

Nếu chức năng không thể đáp ứng correctness, không phát hành thử nghiệm chỉ vì benchmark đẹp.

## 13. Nâng JDK và quản trị vòng đời incubator

### 13.1. Không để incubator upgrade trôi tự động

Một bản JDK update hoặc major release có thể thay đổi module được phân phối, hành vi tối ưu hoặc tính sẵn có của incubator API. Với tính năng thử nghiệm, nên giữ:

- **JDK major/update/vendor** đã được kiểm thử, không chỉ `"27"`.
- Gradle/Maven/build plugin versions được phê duyệt.
- Module name, JEP và link Javadoc của chính release đã sử dụng.
- Danh sách CPU/OS/architecture đã qua kiểm thử.
- Kết quả functional tests và benchmark baseline.
- Mức độ rủi ro đã chấp nhận, owner và thời hạn rà soát.

Không tự lấy một JVM mới rồi bật `--add-modules jdk.incubator.vector` trong production mà không kiểm tra API vẫn tồn tại.

### 13.2. Checklist khi nâng từ Java 27 lên bản JDK khác

1. Đọc release notes và danh sách incubator modules của JDK mới.
2. Chạy `java --list-modules` trên **JDK mới thực tế**.
3. So sánh Javadoc/API signatures, JEP status và những giới hạn platform.
4. Biên dịch lại optional Vector implementation bằng đúng compiler mới.
5. Chạy cả scalar tests và vector comparison tests.
6. Kiểm tra toolchain/CI/test/runtime flags và custom `jlink` images.
7. Chạy performance benchmarks trên các CPU mục tiêu.
8. Quyết định **tiếp tục thử nghiệm**, **sửa adapter**, **chuyển sang API ổn định khi có**, hoặc **ngừng sử dụng module**.

**Không** làm cách sau để che sự thay đổi API:

- Tự chép một `jdk.incubator.vector` JAR không rõ nguồn lên module path.
- Sử dụng `--add-opens`/`--add-exports` để phá encapsulation và giả vờ API vẫn còn.
- Tắt toàn bộ integration tests hoặc xóa cảnh báo mà không có review.

### 13.3. Theo dõi thay đổi API chứ không chỉ số JEP

Tên JEP **537** xác định đợt **Vector API incubator thứ 12 trong JDK 27**, không phải một cam kết rằng mọi method/interface của Java 27 sẽ tiếp tục giữ nguyên trong các JDK sau.

Vì vậy, khi một bản tương lai chính thức chuẩn hóa API, cần review **package name, module name, cách compile/run, semantics và migration path** trước khi cập nhật. Không suy đoán rằng chỉ cần xóa `jdk.incubator.` khỏi package name là xong.

## 14. Quy định thử nghiệm và rủi ro vận hành

Chủ đề bài học là **thêm module có kiểm soát**, không phải tìm một thủ thuật để mang API thử nghiệm vào mọi hệ thống.

### 14.1. Mẫu quyết định thử nghiệm

| Câu hỏi | Thông tin phải có |
| --- | --- |
| Vì sao cần incubator? | Bài toán cụ thể, baseline đã đo, lợi ích dự kiến |
| API nào? | `jdk.incubator.vector`, **Java 27**, JEP 537 |
| Tính ổn định? | Incubating, có thể đổi hoặc bị xóa |
| Triển khai ở đâu? | Lab/test/staging có kiểm soát, hoặc phạm vi đã được chấp thuận riêng |
| Nền tảng nào? | Danh sách JDK/OS/architecture/CPU mục tiêu |
| Bật bằng gì? | `--add-modules` ở compile/runtime/test và module dependencies |
| Fallback? | Stable scalar implementation độc lập với module |
| Test cần đạt? | Correctness, boundary cases, runtime compatibility, performance nếu đặt mục tiêu |
| Chủ sở hữu? | Team chịu trách nhiệm code, JDK upgrades và risk review |
| Khi nào dừng? | Module không còn, performance kém, lỗi correctness hoặc policy không đạt |

Nếu không trả lời được **fallback và owner**, việc mang incubator dependency vào đường xử lý dữ liệu quan trọng thường là quyết định quá rủi ro.

### 14.2. Quyền triển khai và feature flag

Một feature flag dùng để bật thử nghiệm có thể cần:

- Giá trị **mặc định tắt** trên production.
- Quyền bật được giới hạn theo vai trò và có audit log.
- Phạm vi thử nghiệm nhỏ, dữ liệu không nhạy cảm khi có thể.
- Chỉ bật trên runtime có **preflight PASS**.
- Có khả năng tắt mà **không cần sửa dữ liệu đang lưu**.
- Có dashboard/metrics để phát hiện thay đổi hiệu năng hoặc lỗi tính toán.

**Feature flag không giải quyết lỗi module bị thiếu trước khi code chạy**: nếu toàn bộ ứng dụng không link được vì dependency trực tiếp, một cờ trong file config không cứu được process. Cần thiết kế **module isolation** để stable path vẫn khởi động được.

### 14.3. Không thay API incubator cho các cơ chế khác

Các cơ chế sau **khác nhau về mục đích**:

| Cơ chế | Không phải |
| --- | --- |
| `--add-modules` | Không phải công cụ cấp quyền bảo mật cho OS/process |
| `--enable-preview` | Không bật incubator system module |
| `--add-opens` | Không tạo module bị thiếu; chủ yếu thay đổi khả năng reflective access |
| `--add-exports` | Không biến internals thành stable API |
| `--enable-native-access` | Dành cho kiểm soát native access trong các tình huống liên quan, không bật Vector API |
| `-XX:+UnlockExperimentalVMOptions` | Không phải lựa chọn chung để resolve JPMS incubator module |

Hệ thống module JPMS kiểm soát cấu trúc module graph và khả năng truy cập package; nó **không thay** xác thực/phân quyền nghiệp vụ hoặc kiểm soát quyền hệ điều hành.

## 15. Bảng lỗi và cách chẩn đoán

| Triệu chứng | Khả năng chính | Bước xác minh | Hướng sửa |
| --- | --- | --- | --- |
| Compiler không tìm thấy package Vector | Compiler sai JDK hoặc module chưa resolve | `javac --version`; module list; flags | JDK 27 + `--add-modules` |
| Runtime báo module không tìm thấy | JDK khác hoặc custom image thiếu module | Chạy `--list-modules` **trên runtime cuối** | Dùng image phù hợp hoặc disable optional lab |
| Warning incubating module | Có API incubator được dùng | Xem warning và JEP status | Chấp nhận có ghi nhận trong lab; không coi là stable |
| Compile OK, test fail `NoClassDefFoundError` | Test JVM không resolve module | Gradle Test JVM args/Surefire `argLine` | Thêm đúng runtime args |
| Gradle `run` khác IDE behavior | Run JVM/IDE launcher không có cùng cờ | Run configuration, `applicationDefaultJvmArgs` | Đồng nhất launch flags |
| Maven compile được, `mvn test` thất bại | Surefire JVM khác compiler JVM | Toolchains/JVM fork và `argLine` | Cấu hình test runner, kiểm tra JDK |
| Named module không nhìn thấy Vector API | Thiếu `requires` hoặc module không quan sát được | `module-info.java`/JPMS graph | Khai báo requires và dùng JDK phù hợp |
| `--enable-preview` không giúp | Đang nhầm preview với incubator | Kiểm tra feature state | Dùng `--add-modules` |
| CPU chạy đúng nhưng chậm hơn scalar | Workload nhỏ, CPU/JIT/shape không tối ưu | JMH/benchmark trên CPU mục tiêu | Dùng scalar hoặc điều chỉnh thuật toán |
| Kết quả sai khi array length lẻ | Quên tail/mask | Test length < lanes hoặc lanes+1 | `loopBound` + scalar tail/mask đúng |
| `IndexOutOfBoundsException` từ `fromArray` | Đọc vector vượt cuối array | Loop bound và vector shape | Sửa loop/tail |
| Build trên JDK 27, deploy runtime 27 nhưng lỗi | Runtime image bị thiếu module | Module list trên final image | Thêm module khi jlink hoặc dùng stable path |
| Thêm module nhưng không có AVX-512 | CPU flags/JIT không có đường tối ưu đó | OS CPU capabilities, benchmark | Không giả định SIMD width; dùng preferred species |
| Code sau upgrade không compile | Incubator API thay đổi/bị gỡ | JEP và Javadoc đúng JDK mới | Sửa adapter hoặc tắt lab |
| Tất cả tests bị skip mà CI vẫn PASS | Policy skip quá rộng | CI matrix/test reports | Fail closed trên functional tests bắt buộc |
| Code stable fail dù feature flag OFF | Stable core còn direct type dependency | Static imports/bytecode/module graph | Tách artifact optional thật sự |

### 15.1. Chuỗi điều tra nhanh

~~~~text
1. Xác nhận compiler JDK và runtime JDK
        |
        v
2. Module jdk.incubator.vector có ở system modules?
       / \
      No Yes
      |   |
      |   v
      | 3. Module đã resolve khi compile/run/test?
      |      / \
      |     No Yes
      |     |   |
      |     |   v
      |     | 4. Unit tests so với scalar có PASS?
      |     |        / \
      |     |       No Yes
      |     |       |   |
      |     |       |   v
      |     |       | 5. Benchmark có lợi ích thật?
      |     |       |       / \
      |     |       |      No Yes
      |     |       |      |   |
      v     v       v      v   v
   Stable  Sửa   Sửa    Stable  Có thể tiếp tục
   fallback flag  logic  fallback lab theo policy
~~~~

Đây là **quy trình ra quyết định**, không phải lời hứa rằng sửa cờ sẽ giải quyết mọi vấn đề hiệu năng.

## 16. Ma trận lựa chọn: khi nào thêm incubator module?

| Bối cảnh | Phương án đề xuất |
| --- | --- |
| Học tập Vector API Java 27 trong sandbox | Bật `jdk.incubator.vector` theo hướng dẫn compile/run |
| Nghiên cứu SIMD trên CPU cụ thể | Benchmark với preferred species + scalar baseline |
| Ứng dụng production yêu cầu tương thích dài hạn | Ưu tiên API ổn định và scalar/JIT optimization |
| Không có module trong JDK/runtime image | Không tự cài JAR giả; dùng stable path hoặc JDK được kiểm chứng |
| Cần hỗ trợ nhiều JDK major | Tách optional incubator adapter theo version; test mỗi target |
| CI test functionality module Vector | Bắt buộc có JDK 27 và module; fail nếu thiếu |
| CI test compatibility khi không có incubator | Chạy stable core độc lập; có lý do SKIP với Vector lab |
| Runtime có module nhưng CPU không tăng tốc | Cho phép correctness, nhưng benchmark có thể quyết định tắt opt-in |
| Dự án sử dụng JPMS named module | Khai báo `requires jdk.incubator.vector` cho module thử nghiệm |
| Project Gradle/Maven classpath | Truyền `--add-modules` cho compiler, test và launcher |
| Dùng `jlink` hoặc `jpackage` | Kiểm tra modules của **image cuối** và chạy smoke test |

## 17. Bài tập thực hành có thể kiểm chứng

### Bài tập A — Hiện diện khác với resolve

1. Chạy `java --list-modules` trên full JDK 27.
2. Xác nhận `jdk.incubator.vector` xuất hiện.
3. Biên dịch `IncubatorPlatformProbe.java` không cần flag.
4. Chạy probe không có `--add-modules`, ghi nhận `present` và `resolved`.
5. Chạy lại với `--add-modules jdk.incubator.vector`.

**Tiêu chí PASS:** giải thích được vì sao module hiện diện nhưng lần chạy đầu có thể chưa resolve. Không đòi hỏi một số lanes cụ thể.

### Bài tập B — Cộng mảng nhiều kích thước

1. Biên dịch `VectorExperiment.java` với JDK 27 và flag incubator.
2. Chạy `main`, so kết quả scalar với vector.
3. Thêm `verifyManyLengths()`.
4. Kiểm thử mảng rỗng, kích thước nhỏ hơn/bằng/lớn hơn `SPECIES.length()`.
5. Ghi nhận `SPECIES.length()` của máy đang chạy.

**Tiêu chí PASS:** kết quả trùng trên mọi input được kiểm thử, không đọc hoặc ghi vượt giới hạn mảng. Tốc độ không phải tiêu chí của bài tập này.

### Bài tập C — Gradle/Maven flags ở từng nơi

1. Đặt code Vector trong một project lab riêng.
2. Khai báo **JDK toolchain Java 27** và `--release 27`.
3. Thêm `--add-modules jdk.incubator.vector` cho compiler.
4. Thêm flag tương ứng cho `Test`/Surefire.
5. Chạy unit tests và launcher.
6. Cố ý gỡ cờ **chỉ khỏi test JVM** trong môi trường thử nghiệm để quan sát sự khác biệt; khôi phục cấu hình sau bài tập.

**Tiêu chí PASS:** hiểu rằng compiler, Gradle/Maven daemon và test/application runtime không chia sẻ mọi cờ JVM một cách tự động.

### Bài tập D — Custom runtime thiếu module

1. Tạo một image `jlink` chỉ có `java.base`.
2. Dùng launcher của image để xác nhận `jdk.incubator.vector` không có.
3. Chạy `IncubatorPlatformProbe`, xác nhận `present=false`.
4. Tạo image khác có cả `java.base,jdk.incubator.vector`.
5. Chạy module probe và VectorExperiment trên image thứ hai.

**Tiêu chí PASS:** kết quả phản ánh **runtime image đang chạy**, không dựa vào danh sách module của JDK ở máy build.

### Bài tập E — Thiết kế fallback thực sự độc lập

1. Viết `ArrayOperations` và `ScalarArrayOperations` không import incubator package.
2. Biên dịch stable code mà không truyền `--add-modules`.
3. Chạy nó trên image chỉ có `java.base`.
4. Giữ implementation Vector trong optional artifact/subproject riêng.
5. Chỉ đưa optional artifact vào môi trường đã qua preflight và được bật thử nghiệm.

**Tiêu chí PASS:** stable core chạy bình thường ngay cả khi module Vector không có; không dùng việc catch lỗi class loading một cách rộng làm cách thiết kế fallback chính.

## 18. Checklist trước khi bật incubator module

### Trước khi biên dịch

- [ ] Tính năng thực sự còn tồn tại trong JDK **đang dùng**, không lấy ví dụ từ phiên bản cũ.
- [ ] Với Java 27, đã xác nhận **JEP 537 / Vector API (Twelfth Incubator)** và tên module `jdk.incubator.vector`.
- [ ] Đã đọc trạng thái **incubating** trong Oracle Javadoc, không coi nó là stable Java SE API.
- [ ] Đã chọn đúng JDK/compiler Java 27; không chỉ dựa vào `JAVA_HOME` chung.
- [ ] Đã xác minh module có trong `java --list-modules` của runtime mục tiêu.
- [ ] Có chính sách rõ về CPU/OS/JDK vendor và các cấu hình được phép thử nghiệm.
- [ ] Có scalar/stable baseline độc lập, không trực tiếp import incubator type.

### Khi tích hợp

- [ ] Thêm `--add-modules jdk.incubator.vector` vào compiler khi cần.
- [ ] Thêm cờ tương ứng cho **test JVM** và **launcher** hoặc khai báo JPMS `requires` khi phù hợp.
- [ ] Không nhầm `--enable-preview`, `--add-opens` hoặc experimental VM flags với incubator resolution.
- [ ] Nếu dùng Gradle, kiểm tra `JavaCompile`, `Test` và `Application/JavaExec` riêng.
- [ ] Nếu dùng Maven, kiểm tra Compiler Plugin, Surefire/FailSafe và JVM chạy ứng dụng thực tế.
- [ ] Không thêm incubator như một Maven dependency giả.
- [ ] Nếu dùng `jlink`/`jpackage`/container, kiểm tra module ở **final image**.
- [ ] Cảnh báo incubator được ghi nhận; không tự che bằng cấu hình thiếu kiểm soát.

### Trước khi kết luận thành công

- [ ] Chương trình thực sự **compile + run** bằng đúng JDK 27.
- [ ] Functional tests so vector với scalar ở nhiều input và kích thước.
- [ ] Đã kiểm tra tail/masks và trường hợp mảng rỗng/nhỏ.
- [ ] Phân biệt module **present**, **resolved** và **CPU acceleration**.
- [ ] Benchmark được chạy bằng phương pháp phù hợp nếu performance là mục tiêu.
- [ ] Có các kết quả riêng cho x64/AArch64/OS và virtualized environments theo support matrix.
- [ ] Không đưa phụ thuộc incubator vào public stable API ngoài phạm vi đã chấp thuận.
- [ ] Có owner, feature flag, rollback/disable policy và kế hoạch nâng JDK.
- [ ] Job CI bắt buộc **fail closed**, không bỏ qua lỗi module một cách âm thầm.

## 19. Tài liệu tham khảo chính thức

- [Java SE 27 — Module jdk.incubator.vector](https://docs.oracle.com/en/java/javase/27/docs/api/jdk.incubator.vector/module-summary.html): tên module, exported package và trạng thái incubating.
- [Oracle JDK 27 — Significant Changes](https://docs.oracle.com/en/java/javase/27/migrate/significant-changes-jdk-27-release.html): Vector API (twelfth incubator), các preview features và thay đổi Java 27.
- [OpenJDK — JEP 537: Vector API (Twelfth Incubator)](https://openjdk.org/jeps/537): mục tiêu và tiến trình incubation trong JDK 27.
- [Java SE 27 — Vector](https://docs.oracle.com/en/java/javase/27/docs/api/jdk.incubator.vector/jdk/incubator/vector/Vector.html): SIMD, lanes, hardware limitations và platform optimization.
- [Java SE 27 — IntVector](https://docs.oracle.com/en/java/javase/27/docs/api/jdk.incubator.vector/jdk/incubator/vector/IntVector.html): `SPECIES_PREFERRED`, `fromArray`, `add`, `intoArray`.
- [Java SE 27 — VectorSpecies](https://docs.oracle.com/en/java/javase/27/docs/api/jdk.incubator.vector/jdk/incubator/vector/VectorSpecies.html): `length`, `loopBound`, `vectorBitSize`, `indexInRange`.
- [Java SE 27 — javac](https://docs.oracle.com/en/java/javase/27/docs/specs/man/javac.html): `--release` và `--add-modules` khi biên dịch.
- [Java SE 27 — java launcher](https://docs.oracle.com/en/java/javase/27/docs/specs/man/java.html): `--add-modules`, `--list-modules`, `--describe-module`, `--dry-run`.
- [Java SE 27 — ModuleFinder](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/module/ModuleFinder.html): tìm system modules bằng Java API ổn định.
- [Java SE 27 — ModuleLayer](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/ModuleLayer.html): `boot()` và `findModule`.
- [Java SE 27 — jlink](https://docs.oracle.com/en/java/javase/27/docs/specs/man/jlink.html): tùy chỉnh runtime modules và kiểm tra image.
- [Gradle — Java Compatibility](https://docs.gradle.org/current/userguide/compatibility.html) và [Application Plugin](https://docs.gradle.org/current/userguide/application_plugin.html): toolchains Java 27 và runtime flags trong `run`/start scripts.
- [Maven Compiler Plugin — Compiler Arguments](https://maven.apache.org/plugins/maven-compiler-plugin/examples/pass-compiler-arguments.html): truyền `--add-modules` khi biên dịch.
- [Maven Surefire Plugin](https://maven.apache.org/surefire/maven-surefire-plugin/): JVM của unit tests và `argLine`.

**Kết luận:** Trong **Java 27**, `jdk.incubator.vector` là module thử nghiệm **đang được phân phối**, không phải API ổn định. Để dùng đúng, cần **xác minh module có trong JDK/runtime image**, resolve bằng `--add-modules` hoặc `requires` phù hợp, truyền cờ đúng cho **compile, tests và runtime**, và kiểm tra kết quả thực tế trên mỗi **JVM/OS/CPU mục tiêu**. Module hiện diện hay đã resolve **không đồng nghĩa SIMD chạy nhanh**: `SPECIES_PREFERRED` và benchmark chỉ là công cụ đánh giá. Trong hệ thống cần ổn định dài hạn, nên **cô lập incubator sau một ranh giới opt-in**, giữ implementation scalar không phụ thuộc module, có CI fail-closed, quyết định fallback và kế hoạch nâng phiên bản rõ ràng.
