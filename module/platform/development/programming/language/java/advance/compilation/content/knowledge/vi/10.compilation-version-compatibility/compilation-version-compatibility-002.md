# Ý nghĩa và giới hạn của -source và -target khi biên dịch Java

## 1. Bài toán: biên dịch bằng JDK mới nhưng cần chạy trên Java cũ

Khi dự án dùng JDK 17, 21 hoặc mới hơn để biên dịch, ta có thể cần cung cấp ứng dụng cho môi trường chỉ có Java 8, 11 hoặc 17. Nhưng câu “chương trình tương thích Java 8” có ít nhất **ba ý nghĩa độc lập**:

1. **Ngôn ngữ nguồn:** trình biên dịch chấp nhận những cấu trúc cú pháp nào? Ví dụ lambda thuộc Java 8, `record` là tính năng chuẩn từ Java 16.
2. **Định dạng bytecode:** file `.class` dùng class-file major version nào để JVM mục tiêu có thể nạp?
3. **API nền tảng:** chương trình đang tham chiếu những class/method/field thuộc phiên bản Java SE nào? Một API tồn tại ở JDK mới có thể chưa xuất hiện ở JDK cũ.

Hai tùy chọn truyền thống của `javac` kiểm soát hai tầng đầu:

- `--source N` hoặc `-source N`: chọn **mức ngôn ngữ nguồn** được chấp nhận.
- `--target N` hoặc `-target N`: chọn **phiên bản class file** do compiler tạo ra.

Điều quan trọng: **chỉ đặt `-source` và `-target` không bảo đảm chương trình chỉ dùng API có trên Java N**. Để kiểm tra cả ba tầng khi dùng JDK 9+, thông thường nên dùng `--release N`.

~~~text
                          Biên dịch bằng JDK mới
                                |
          +---------------------+---------------------+
          |                     |                     |
     Ngôn ngữ nguồn        Bytecode đầu ra       API nền tảng
       --source N            --target N         Không bị khóa
          |                     |               chỉ bởi hai cờ
          +---------------------+---------------------+
                                |
                     --release N (thường ưu tiên)
                   nguồn + class version + API N
                                |
                        Kiểm thử trên JDK N
~~~

Từ “thường” ở đây rất quan trọng: `--release` kiểm tra các **API nền tảng được hỗ trợ và công khai** của release mục tiêu; nó không thay thế việc kiểm tra dependency bên thứ ba, hành vi runtime, cấu hình triển khai hoặc tính tương thích dữ liệu.

## 2. -source: kiểm soát cú pháp và quy tắc ngôn ngữ

Ví dụ:

~~~bash
javac --source 8 Main.java
~~~

Yêu cầu `javac` phân tích nguồn theo các quy tắc Java 8 mà compiler hiện tại hỗ trợ. Với nguồn dùng `record`, Java 8 chưa có cú pháp đó nên compiler phải báo lỗi thay vì coi đây là Java 8 hợp lệ.

Mốc điển hình:

| Tính năng | Phiên bản Java nơi trở thành tính năng chuẩn | Nhận xét khi `--source` thấp hơn |
| --- | --- | --- |
| Lambda và method reference | 8 | Không hợp lệ nếu mức ngôn ngữ không hỗ trợ |
| Local-variable type inference với `var` | 10 | Không hợp lệ với `--source 8` |
| Switch expression | 14 | Không hợp lệ với `--source 11` |
| Text block | 15 | Không hợp lệ với `--source 11` |
| Record | 16 | Không hợp lệ với `--source 11` |
| Sealed classes/interfaces | 17 | Không hợp lệ với `--source 11` |

Bảng dùng các phiên bản **đã chuẩn hóa**; nhiều tính năng từng có giai đoạn preview ở phiên bản sớm hơn. Không suy ra tính năng preview sẽ được hỗ trợ chỉ bằng việc đặt `--source` thấp hơn trên một compiler mới.

`-source` tác động tới cách parser/type checker áp dụng quy tắc ngôn ngữ, nhưng **không tự chọn thư viện hệ thống của phiên bản cũ**. Đây là lỗi cấu hình tương thích phổ biến nhất.

### Ví dụ A: chương trình Java 17 hợp lệ

Tạo tệp `RecordDemo.java`:

~~~java
public record RecordDemo(int x, int y) {
    public static void main(String[] args) {
        RecordDemo p = new RecordDemo(2, 3);
        System.out.println(p.x() + p.y());
    }
}
~~~

Biên dịch và chạy bằng JDK 17+:

~~~bash
javac --source 17 --target 17 RecordDemo.java
java RecordDemo
~~~

Stdout:

~~~text
5
~~~

Tệp khai báo `public record RecordDemo` nên tên tệp `RecordDemo.java` phải khớp. Với JDK 17, chương trình có thể được biên dịch cả bằng `javac --release 17 RecordDemo.java`.

Nếu đổi lệnh thành:

~~~bash
javac --source 8 --target 8 RecordDemo.java
~~~

compiler từ chối vì `record` không thuộc ngôn ngữ Java 8. Đây là **lỗi về source language**, chưa cần xét file class đầu ra.

Lưu ý: dùng `--target 8` **không thể “dịch ngược” tùy ý một tính năng Java 17 thành cấu trúc Java 8**. `javac` không phải công cụ transpile mọi cú pháp mới thành bytecode cũ.

## 3. -target: kiểm soát phiên bản class file, không kiểm tra API

JVM đọc class file theo một định dạng có số phiên bản. Header bắt đầu bằng magic `CAFEBABE`, tiếp theo có minor version và major version; major version tăng qua các bản Java.

Một số mốc thông dụng:

| Java SE | Major version của class file |
| --- | ---: |
| Java 8 | 52 |
| Java 11 | 55 |
| Java 17 | 61 |
| Java 21 | 65 |

Với compiler hỗ trợ các giá trị tương ứng, `javac --target 8` tạo class file major version 52. JVM Java 8 có thể hiểu **định dạng** bytecode này, còn một JVM cũ hơn mức được hỗ trợ có thể báo `UnsupportedClassVersionError`.

Nhưng khả năng **đọc được định dạng class file** không đồng nghĩa **chạy được chương trình**: bytecode có thể tham chiếu method không tồn tại trên runtime Java 8, thư viện bên ngoài đòi phiên bản cao hơn, hoặc hệ thống thiếu tài nguyên/native code.

`-target` chỉ định version của class file do *lượt biên dịch đó* tạo. Nó **không tự biên dịch lại** JAR dependency; một dependency có class file version 61 vẫn không thể chạy trên Java 8 chỉ vì ứng dụng được compile với target 8.

### Xác minh bằng javap

Từ ví dụ `RecordDemo.java`, chạy:

~~~bash
javap -verbose RecordDemo
~~~

Trong phần đầu có thể thấy:

~~~text
major version: 61
~~~

Đây là thông tin cần đối chiếu sau khi compile với target 17; các dòng constant pool, timestamp, tên entry và chi tiết còn lại có thể khác giữa compiler. Dùng `javap -verbose` hoặc `javap -v` để đọc file đã tạo, thay vì suy từ tên file JAR.

Nếu biên dịch vào thư mục `build/classes`, có thể dùng:

~~~bash
javap -classpath build/classes -verbose com.example.Main
~~~

Lệnh này là **mẫu**; chỉ chạy được khi thư mục thực sự có `com/example/Main.class`.

## 4. Vì sao -source 8 -target 8 vẫn có thể gọi API sau Java 8?

Giả sử dùng JDK 17 (hoặc JDK mới hơn có hỗ trợ `--source 8`/`--target 8`). Tạo `ApiTrap.java`:

~~~java
import java.util.List;

public class ApiTrap {
    public static void main(String[] args) {
        System.out.println(List.of("A", "B").size());
    }
}
~~~

`List.of` là API được bổ sung từ Java 9. Cú pháp gọi static method và generic method invocation ở đây vẫn **hợp lệ ở mức ngôn ngữ Java 8**.

Biên dịch bằng JDK mới:

~~~bash
mkdir -p out/legacy
javac --source 8 --target 8 -d out/legacy ApiTrap.java
java -cp out/legacy ApiTrap
~~~

Trên JDK 17, `javac` có thể biên dịch thành công khi sử dụng platform API hiện tại; nó có thể phát cảnh báo về bootstrap/platform classpath do đang biên dịch cho release cũ. Stdout của lệnh **chạy trên JDK 17+**:

~~~text
2
~~~

Class file sinh ra vẫn có major version **52**. Nhưng khi mang class đó sang **Java 8 runtime**, `java.util.List` của Java 8 **không có** static method `of`. Đến lúc method được liên kết/được gọi, chương trình có thể thất bại bằng `NoSuchMethodError` thay vì `UnsupportedClassVersionError`.

Đây là khác biệt cốt lõi:

- `UnsupportedClassVersionError`: JVM không hỗ trợ **định dạng class file** yêu cầu.
- `NoSuchMethodError` hoặc `NoClassDefFoundError`: class file có thể đọc được nhưng **API hoặc class phụ thuộc** không hiện diện/tương thích tại runtime.
- `-source 8`: compiler chỉ kiểm tra mã có theo quy tắc **ngôn ngữ Java 8**; nó không tự cấm gọi `List.of`.
- `-target 8`: compiler có thể tạo class file major 52, không đồng nghĩa đã kiểm tra đủ Java 8 API.

Đặc biệt, mã có thể compile thành công với `-source 8 -target 8` và chạy tốt trên JDK của máy build; điều đó **không phải bằng chứng** ứng dụng chạy được trên Java 8 thật.

## 5. --release kết hợp ba tầng cần thiết cho tương thích

Từ JDK 9, `javac` có tùy chọn:

~~~bash
javac --release 8 ApiTrap.java
~~~

Tùy chọn này hướng compiler thực hiện cùng lúc các mục tiêu:

1. Áp quy tắc ngôn ngữ của Java 8.
2. Tạo class file phù hợp với Java 8 (major 52).
3. Chỉ cho mã tham chiếu các **Java SE/JDK API công khai được hỗ trợ của release 8**, theo thông tin platform API tích hợp trong compiler.

Vì `List.of` chưa tồn tại ở Java 8, lệnh `javac --release 8 ApiTrap.java` sẽ bị từ chối ở bước biên dịch. Thông báo lỗi có thể mang dạng `cannot find symbol` cho method `List.of`; không giả định dòng lỗi nguyên văn giống nhau giữa các JDK.

Đối chiếu:

| Lệnh (với JDK mới hỗ trợ Java 8) | Ngôn ngữ | Class version | API bị giới hạn về Java 8? |
| --- | --- | --- | --- |
| `javac --source 8 --target 8 ApiTrap.java` | Java 8 | 52 | Không, nếu không cấu hình platform API cũ |
| `javac --release 8 ApiTrap.java` | Java 8 | 52 | Có, với documented/supported platform API |
| `javac --release 17 RecordDemo.java` | Java 17 | 61 | Có, với platform API của Java 17 |
| `javac RecordDemo.java` trên JDK 17 | Mặc định JDK 17 | Mặc định JDK 17 | Dùng platform hiện tại |

Giá trị `N` được `--release`, `--source` và `--target` chấp nhận **phụ thuộc phiên bản `javac`**. Đừng cho rằng compiler hiện tại hỗ trợ mọi release Java từng tồn tại. Kiểm tra:

~~~bash
javac -version
javac --help
~~~

Trong `javac --help` có danh sách supported releases của từng tùy chọn. Với JDK 8, `--release` chưa tồn tại; muốn cross-compile phải dùng những tùy chọn và platform classes phù hợp với JDK thời kỳ đó.

### Ví dụ B: chương trình đúng Java 8 từ nguồn đến API

Tạo file độc lập `CompatibleEight.java`:

~~~java
import java.util.Arrays;
import java.util.List;

public class CompatibleEight {
    public static void main(String[] args) {
        List<String> words = Arrays.asList("Java", "8");
        System.out.println(String.join("-", words));
    }
}
~~~

`Arrays.asList` và `String.join` đều có trên Java 8. Dùng JDK 17+ có hỗ trợ release 8:

~~~bash
mkdir -p out/release8
javac --release 8 -d out/release8 CompatibleEight.java
javap -classpath out/release8 -verbose CompatibleEight
java -cp out/release8 CompatibleEight
~~~

Các điểm quan sát được:

- `javac --release 8` biên dịch thành công trên toolchain thích hợp.
- Output của `javap -verbose` có `major version: 52`.
- Lệnh chạy `java` in ra stdout chính xác:

~~~text
Java-8
~~~

Vì không dựa vào API mới hơn Java 8, chương trình này có cơ sở tương thích tốt hơn với runtime Java 8 so với `ApiTrap`. Tuy nhiên, **để xác nhận triển khai**, vẫn cần thử với đúng Java 8 runtime, không chỉ suy từ compile result và class major version.

### Ví dụ C: cú pháp mới bị chặn dù API quen thuộc

Tệp `RecordDemo.java` ở mục 2 dùng record. Dù body chỉ tính toán số nguyên rất đơn giản, lệnh `javac --release 8 RecordDemo.java` vẫn thất bại vì cú pháp `record` chưa nằm trong ngôn ngữ Java 8. `--release` kiểm tra **cú pháp lẫn API**, không chỉ class-file format.

## 6. Không thể ghép tùy ý -source, -target và --release

Các trường hợp cấu hình cần tránh:

~~~bash
# Sai: --release và hai cờ nguồn/đích là những cơ chế loại trừ nhau.
javac --release 8 --source 8 CompatibleEight.java
javac --release 8 --target 8 CompatibleEight.java
~~~

Compiler từ chối dùng `--release` đồng thời với `--source` hoặc `--target`. Chọn một chiến lược tương thích có chủ đích.

`--source` và `--target` cần **tương thích với nhau**. Ví dụ, không thể mong compiler chấp nhận mọi cú pháp Java 17 rồi tạo ra bytecode Java 8:

~~~bash
# Sai/không được compiler hỗ trợ: source mới hơn target một cách bất hợp lệ.
javac --source 17 --target 8 RecordDemo.java
~~~

`-target` không phải một công cụ *desugar* toàn diện có thể hạ cấp mọi tính năng ngôn ngữ và runtime semantics. Kể cả ở những trường hợp compiler cho phép một sự kết hợp, cũng phải kiểm soát platform APIs và kiểm thử runtime.

Ngoài ra:

- Nếu chỉ định `--source N` mà bỏ `--target`, hoặc ngược lại, hãy đọc behavior của **phiên bản javac đang dùng** thay vì giả định mọi bản JDK đều có cùng giá trị mặc định. Cách đáng tin hơn là dùng `--release N` hoặc khai báo cả hai với platform classes phù hợp.
- Một Java release có thể bị **ngừng hỗ trợ** làm target/source trong compiler đời sau. Khi đó lệnh vốn chạy với JDK cũ có thể thất bại; điều này không đồng nghĩa source code sai.
- `--enable-preview` chỉ phục vụ preview features của **release do compiler đang hỗ trợ theo quy tắc preview hiện hành**. Không thể sử dụng `--enable-preview` như đường lách để biên dịch source preview mới thành một Java release cũ bất kỳ.
- Nếu biên dịch code có `module-info.java`, sự hỗ trợ module thuộc Java 9+. Không thể tạo deployment Java 8 bằng cách đơn giản đặt `--target 8` cho một module descriptor.

## 7. Cross-compilation với -source/-target và platform classes

Về nguyên tắc, để cross-compile **không dùng `--release`**, cần cung cấp các **platform class** đúng phiên bản mục tiêu; nếu không, compiler có thể nhìn thấy API mới từ JDK đang chạy.

Với mục tiêu **JDK 8 trở về trước**, các công cụ JDK đời thích hợp sử dụng *boot class path* cho Java platform classes cũ, thông qua tùy chọn như `-bootclasspath`. Chỉ chỉ định `-source 8 -target 8` mà không cung cấp platform classes của Java 8 là không đủ để xác nhận API compatibility.

Với mục tiêu **JDK 9 trở lên**, nền tảng Java dùng system modules; các compiler hiện đại có tùy chọn `--system` để chọn vị trí JDK platform classes phù hợp trong những tình huống cross-compilation thủ công. Không dùng `-bootclasspath` để cấu hình platform module hệ thống của JDK 9+.

Diễn giải (đây là **cú pháp minh họa**, không phải lệnh chạy độc lập vì phải cung cấp đường dẫn JDK hợp lệ):

~~~text
# Target Java 8 với đúng platform classes cũ, trên toolchain còn hỗ trợ:
javac -source 8 -target 8 -bootclasspath <java8-platform-classes> ...sources...

# Target Java 11 với đúng JDK system modules tương ứng:
javac -source 11 -target 11 --system <path-to-jdk11> ...sources...
~~~

Không thay placeholder bằng đường dẫn thư viện ứng dụng, bởi các tùy chọn này dành cho **platform classes/modules**. Mỗi compiler có giới hạn lựa chọn kết hợp options; cần kiểm tra `javac --help` và tài liệu JDK tương ứng.

`--release N` được thiết kế để đơn giản hóa phần này, dùng dữ liệu platform API có sẵn trong JDK biên dịch. Theo nguyên tắc, `--release` không cho phép kết hợp tùy tiện các tùy chọn ghi đè platform classes hay phá encapsulation (ví dụ `--add-exports` để lách quyền truy cập JDK internals). Nếu dự án phụ thuộc API nội bộ không được hỗ trợ, việc cross-compile an toàn cần **loại bỏ/đổi API nội bộ** hoặc đưa ra ràng buộc runtime rõ ràng, không dựa vào cách compiler tình cờ cho qua.

## 8. Những gì --release cũng không đảm bảo

`--release 8` là một kiểm tra mạnh, nhưng không phải chứng nhận chương trình sẽ hoạt động trong mọi môi trường Java 8. Có nhiều tầng ngoài phạm vi của javac:

### 8.1. Thư viện bên thứ ba

`--release 8` không tự đảm bảo mọi dependency JAR đều chạy được trên Java 8 hoặc mọi phiên bản thư viện có API tương thích. Một dependency có class file major 61 có thể làm ứng dụng hỏng trên Java 8, dù class main được compile major 52.

Với dependency có nhiều phiên bản, cần kiểm tra **minimum Java version của dependency**, class-file versions, dependency graph và hành vi. Build tool phải chọn đúng phiên bản library; compiler không tự tải/giải phiên bản chỉ nhờ `--release`.

### 8.2. API bên ngoài Java SE/JDK

Compiler kiểm tra nền tảng Java của release mục tiêu, nhưng một JAR ngoài có thể thay đổi/biến mất giữa máy build và máy chạy. `--release` không đóng gói thư viện bên ngoài vào output. Phải phân biệt compile classpath và runtime classpath.

### 8.3. Runtime behavior, môi trường và cập nhật vá lỗi

Hai runtime cùng có tên major release vẫn có thể khác update level, security policies, trust store, TLS settings, fonts, locale database, OS/CPU architecture, native libraries và cấu hình JVM. Một chương trình dùng API tồn tại ở Java 8 vẫn có thể không chạy thành công nếu môi trường thiếu tài nguyên hoặc gặp hành vi phụ thuộc nền tảng.

Tương thích cú pháp/API/bytecode là **điều kiện cần quan trọng**, nhưng kiểm thử triển khai vẫn là bước kiểm chứng riêng.

### 8.4. Reflection, ServiceLoader và dynamic loading

Lời gọi qua reflection như `Class.forName("...")` hoặc tìm method bằng chuỗi không được phân giải như lời gọi Java tĩnh thông thường. `--release` không thể chứng minh mọi tên class/method mà chương trình tạo động đều tồn tại trên runtime. Service providers, plugin JAR hoặc class loader tự viết cũng có thể nạp code không tương thích.

### 8.5. Java modules

Với `--release 9` trở lên, có thể dùng cấu trúc module tương ứng nếu mục tiêu hỗ trợ. Nhưng compiler vẫn không kiểm tra thay cho toàn bộ cấu hình deployment: cần xét module path, `requires`, `exports`, service providers, các tham số module runtime và dependency modules có trên môi trường thực tế.

### 8.6. Preview features và các định dạng mới

Một class build từ preview feature có những ràng buộc đặc biệt về compiler/runtime và preview version. Đừng dùng `--target` để giả định rằng preview code có thể chạy trên JVM cũ. Với ứng dụng cần tương thích dài hạn, ưu tiên tính năng Java đã chuẩn hóa của release mục tiêu.

## 9. Phân biệt source compatibility, binary compatibility và behavioral compatibility

| Câu hỏi | Ví dụ lỗi | Cách kiểm chứng |
| --- | --- | --- |
| Source compatibility: code có thể compile theo ngôn ngữ N? | `record` không có ở Java 8 | `--release N` hoặc kiểm tra `--source N` |
| Class-file compatibility: JVM có hiểu bytecode không? | Major 61 trên JVM chỉ hỗ trợ major 52 | `--target N`, `javap -verbose` |
| Platform API compatibility: Java N có method được gọi không? | `List.of` thiếu trên Java 8 | `--release N`, chạy trên Java N |
| Dependency compatibility: thư viện/JAR cùng chạy được? | JAR major 61 trong app Java 8 | Kiểm tra tất cả JAR và thử runtime |
| Linkage/binary compatibility: class và method signatures khớp? | `NoSuchMethodError` khi đổi dependency | Kiểm tra phiên bản/binary API và integration test |
| Behavioral compatibility: cùng hành vi khi chạy? | Locale, TLS, timezone, native code khác nhau | Chạy integration tests trên runtime/OS đích |

Không được đồng nhất ba khái niệm đầu. `--source 8` giải quyết câu hỏi cú pháp; `--target 8` giải quyết khả năng đọc class file; `--release 8` đồng thời áp thêm hàng rào kiểm tra platform APIs có trong Java 8.

## 10. Gradle: chọn toolchain và release đúng mục tiêu

Với Gradle plugin `java`, nếu build chạy bằng một JDK mới nhưng cần artifact Java 8, nên cấu hình **toolchain** cho compiler đã chọn và `options.release` cho target platform. Ví dụ `build.gradle` theo Groovy DSL:

~~~groovy
plugins {
    id 'java'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

tasks.withType(JavaCompile).configureEach {
    options.release = 8
    options.encoding = 'UTF-8'
}
~~~

Ý nghĩa:

- Toolchain yêu cầu dùng **JDK 17 compiler** cho tác vụ JavaCompile khi Gradle tìm được toolchain phù hợp; đó là *compiler JDK version*.
- `options.release = 8` truyền tương đương `javac --release 8` để kiểm soát **source language, class version và platform API Java 8**.
- `options.encoding = 'UTF-8'` làm rõ cách compiler đọc tệp nguồn.

**JDK 17 toolchain và Java 8 target là hai quyết định độc lập.** Chỉ đặt `sourceCompatibility = '8'` và `targetCompatibility = '8'` trên một JDK mới không có đầy đủ hàng rào platform API như `options.release`. Tương tự, chỉ đặt Java toolchain 17 không có nghĩa output sẽ tương thích Java 8.

Nếu dự án buộc dùng API chỉ có ở JDK mới, cần quyết định nâng minimum runtime hoặc thiết kế phương án tương thích, thay vì loại bỏ kiểm tra `--release` để build qua rồi triển khai bị lỗi.

Để xác minh thực tế trên dự án có Gradle Wrapper, dùng nhiệm vụ compile/test:

~~~bash
./gradlew clean compileJava test
~~~

Trên Windows dùng `gradlew.bat`. Lệnh này là **lệnh dự án**, không phải lệnh độc lập từ hai tệp ví dụ ở trên; kết quả phụ thuộc build.gradle, test framework, dependency và môi trường đã thiết lập.

Nếu dự án dùng Java test code cần cú pháp/API mới hơn production, cần cấu hình task/source set/toolchain tương ứng một cách có chủ đích; không âm thầm làm thay đổi artifact production hoặc kéo cả test classes vào runtime.

## 11. Maven: dùng maven.compiler.release thay vì chỉ source/target

Trong `pom.xml` của Maven, phần dưới đây là **fragment thuộc phần tử `project`**:

~~~xml
<properties>
    <maven.compiler.release>8</maven.compiler.release>
</properties>
~~~

Với phiên bản Maven Compiler Plugin hỗ trợ property này và một compiler JDK 9+ thích hợp, nó cấu hình compile theo `--release 8`. Điều này khác với cách đặt:

~~~xml
<properties>
    <maven.compiler.source>8</maven.compiler.source>
    <maven.compiler.target>8</maven.compiler.target>
</properties>
~~~

Cặp source/target kiểm soát ngôn ngữ và class file, nhưng không tự giải quyết vấn đề platform APIs mới. Cấu hình plugin/toolchain cụ thể vẫn cần tương thích với JDK đang dùng. Maven Compiler Plugin phiên bản cũ hoặc JDK 8 có khả năng hỗ trợ khác, vì `--release` được giới thiệu từ JDK 9.

Các test/build plugins và dependency JAR cũng có thể yêu cầu JDK riêng. Vì vậy hãy kiểm tra cả compiler toolchain, plugin version và runtime thực sự được CI/deployment dùng.

## 12. Lỗi thường gặp và cách đọc thông báo

| Triệu chứng | Nguyên nhân có thể | Hướng kiểm tra |
| --- | --- | --- |
| Compiler báo cú pháp `record` không hỗ trợ | Source language level thấp | Chọn release đủ mới hoặc thay cú pháp |
| `invalid source release` / `invalid target release` | Compiler không hỗ trợ giá trị cấu hình | `javac -version`, `javac --help`; đổi toolchain |
| Compiler báo `source release ... requires target release ...` | `--source` và `--target` mâu thuẫn | Đồng bộ lựa chọn theo release mục tiêu |
| Cảnh báo bootstrap classpath khi dùng source 8 | Compiler mới đang dùng platform classes không được khóa về Java 8 | Dùng `--release 8` hoặc bootclasspath đúng |
| `List.of` compile được nhưng Java 8 chạy lỗi | Source/target không chặn API mới | Dùng `--release 8`, kiểm thử Java 8 |
| `UnsupportedClassVersionError` | File class/JAR đòi JVM mới hơn | Dùng `javap -verbose` cho app và dependencies |
| `NoSuchMethodError` | Binary API ở runtime khác compile time | Kiểm tra đúng phiên bản JDK/API/JAR |
| `--release` không dùng cùng `--source` hoặc `--target` | Options loại trừ nhau | Chỉ dùng `--release N` |
| `--release` không cho gọi JDK internal APIs | API nội bộ không được public/supported trong release | Thay thế bằng API được hỗ trợ |
| Compile qua nhưng integration test thất bại trên runtime cũ | Chỉ kiểm tra mã nguồn, thiếu kiểm thử runtime/environment | Chạy CI matrix trên JDK đích |
| Dùng Java 17 toolchain nhưng JAR vẫn yêu cầu Java 17 | Chưa đặt `options.release`/target mong muốn | Tách compiler JDK và target artifact |

**Lưu ý:** chính xác tên và thứ tự thông báo `javac` có thể khác giữa các bản JDK. Dùng nhóm lỗi và lời giải thích để chẩn đoán, thay vì viết test phụ thuộc một chuỗi stderr cố định.

## 13. Quy trình kiểm chứng tương thích từ source tới runtime

Một dự án tuyên bố “chạy được trên Java 8” nên có chứng cứ theo nhiều lớp:

1. **Chốt minimum runtime:** dự án cần Java 8, 11, 17 hay phiên bản nào khác? Ghi rõ trong tài liệu và CI.
2. **Chọn compiler toolchain:** JDK phiên bản được kiểm thử, hỗ trợ `--release N` tương ứng. Không giả định mọi javac mới hỗ trợ mọi N cũ.
3. **Compile bằng `--release N`:** kiểm soát ngôn ngữ, bytecode và public platform API.
4. **Đọc class version:** dùng `javap -verbose` với class của sản phẩm và kiểm tra binary dependencies; artifact phải có phiên bản JVM phù hợp.
5. **Kiểm tra dependency graph:** mọi JAR runtime có minimum Java version, method/class availability và cấu hình dependency tương thích.
6. **Chạy trên JDK thực tế mục tiêu:** smoke test/functional/integration tests bằng Java N, kể cả các đường thực thi dùng reflection hoặc service loading.
7. **Kiểm thử môi trường triển khai:** OS/CPU, encoding, locale, timezone, TLS, certificate/trust store, native libraries, JVM flags khi liên quan.
8. **Đảm bảo reproducible build:** pin toolchain và dependency versions; CI build từ checkout sạch, không dựa vào file class/JAR còn sót.

### Bài thực hành đối chứng

Tạo hai file độc lập `ApiTrap.java` và `CompatibleEight.java` như mục 4 và 5. Dùng JDK mới có hỗ trợ Java 8:

~~~bash
# Thử nghiệm: source/target đơn thuần có thể chấp nhận API Java mới.
javac --source 8 --target 8 -d out/legacy ApiTrap.java

# Kiểm tra tương thích thực sự với Java 8 API: dòng này phải bị từ chối.
javac --release 8 -d out/release8 ApiTrap.java

# Một chương trình đúng Java 8 API có thể được biên dịch thành công.
javac --release 8 -d out/release8 CompatibleEight.java

# Quan sát major version 52 và kết quả Java-8.
javap -classpath out/release8 -verbose CompatibleEight
java -cp out/release8 CompatibleEight
~~~

**Đừng đặt toàn bộ chuỗi trên thành một shell script có giả định tất cả lệnh đều exit 0**: lệnh compile `ApiTrap` bằng `--release 8` được thiết kế để **thất bại**, chứng minh compiler đã chặn API mới.

Sau cùng, nếu có Java 8 runtime, chạy `CompatibleEight` trên JVM đó và quan sát `Java-8`. Nếu không có runtime đích, chỉ có thể khẳng định đã qua kiểm tra tĩnh của compiler, chưa thể khẳng định kiểm thử runtime thành công.

## 14. Các nguyên tắc cần nhớ

- `--source N` kiểm soát **mức ngôn ngữ**; không tự giới hạn Java platform APIs ở N.
- `--target N` kiểm soát **class-file version**; không tự viết lại library dependencies hoặc bảo đảm runtime có API cần dùng.
- `--release N` thường là lựa chọn phù hợp khi cần compile từ JDK mới cho Java N, vì kết hợp source, target và API compatibility ở **nền tảng Java N được hỗ trợ**.
- `--release` không thay thế việc kiểm tra thư viện bên thứ ba, môi trường runtime, reflection/native code hay behavior giữa các phiên bản.
- Giá trị N được hỗ trợ thay đổi theo phiên bản compiler; kiểm tra `javac --help` trên toolchain thực tế.
- Tránh cấu hình mâu thuẫn giữa `--release` với `--source`/`--target`; không kỳ vọng `-target` tự chuyển các tính năng Java mới xuống bytecode cũ.
- Đọc `major version` bằng `javap -verbose`, rồi **chạy kiểm thử trên JVM nhỏ nhất được tuyên bố hỗ trợ**.

## Tài liệu để đối chiếu

- [Oracle JDK 17 — javac Command](https://docs.oracle.com/en/java/javase/17/docs/specs/man/javac.html): chi tiết các tùy chọn `--source`, `--target`, `--release` và giới hạn khi cross-compiling.
- [OpenJDK JEP 247 — Compile for Older Platform Versions](https://openjdk.org/jeps/247): lý do ra đời `--release` và vấn đề các API mới vẫn lọt qua `-source/-target`.
- [Oracle JVM Specification — Class File Format](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-4.html): class-file version và cấu trúc class file.
