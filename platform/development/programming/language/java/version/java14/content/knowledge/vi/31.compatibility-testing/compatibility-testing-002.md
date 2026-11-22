# Phân biệt khả năng biên dịch với phiên bản runtime tối thiểu trong Java

## 1. Mục tiêu và câu hỏi cần trả lời

Một chương trình Java **biên dịch thành công** không có nghĩa nó sẽ chạy trên mọi phiên bản Java. Khi kiểm thử tương thích, phải phân biệt:

1. **JDK dùng để biên dịch (build JDK):** phiên bản thực tế của `javac`, chẳng hạn JDK 24.
2. **Mức ngôn ngữ, API và class file đích:** cấu hình `javac --release 17`.
3. **Runtime tối thiểu được sản phẩm cam kết hỗ trợ:** chẳng hạn JVM Java 17, phải được kiểm thử bằng Java 17 thật.
4. **Runtime thực khi triển khai:** `java` từ PATH, service/container image, hoặc runtime riêng do `jlink/jpackage` đóng gói.

Ba khái niệm đầu thường bị trộn thành một câu “ứng dụng dùng Java 17”. Trong thực tế, cùng một mã nguồn có thể build trên JDK 24, xuất class file Java 17, nhưng một dependency hoặc lời gọi API vẫn yêu cầu Java 21. Khi chạy Java 17, chương trình sẽ lỗi dù trước đó compile pass.

**Nguyên tắc trung tâm:** sử dụng `--release` để kiểm soát ngôn ngữ, bytecode và API JDK ở bước compile; sau đó **chạy artifact thật bằng runtime thấp nhất** để xác nhận mức tương thích mà sản phẩm công bố. Hai bước bổ sung cho nhau, không thay thế nhau.

Nội dung dùng các tính năng **đã chính thức và còn được hỗ trợ trên Java hiện đại**, ưu tiên Java 17+. Java 14 chỉ là bối cảnh của lộ trình; bài không dùng API incubator hoặc mẹo biên dịch legacy để giải quyết tương thích mới.

## 2. Bốn lớp của hợp đồng tương thích

| Lớp | Ví dụ | Ý nghĩa |
| --- | --- | --- |
| **Compiler/JDK build** | JDK 24, `javac -version` | Công cụ tạo bytecode và kiểm tra mã nguồn |
| **Compile target** | `--release 17` | Giới hạn syntax, JDK API và class format về Java 17 |
| **Minimum runtime** | Java 17 | JVM thấp nhất **phải chạy đúng** theo cam kết |
| **Runtime được triển khai** | Java 17/21/24 hoặc runtime trong app image | Môi trường thực sự tải class và gọi thư viện |

Một nhóm có thể dùng JDK 24 để build nhưng đặt `--release 17` và vẫn hỗ trợ Java 17. Ngược lại, một phần mềm đóng gói bằng JDK 24 mà **không chỉ định `--release`** thường tạo bytecode mặc định của JDK 24, nên Java 17 không chạy được.

“Minimum runtime” còn có nghĩa **mức được nhà phát triển hỗ trợ**, không nhất thiết là phiên bản cũ nhất mà chương trình tình cờ có thể khởi động. Tổ chức có thể chủ động chỉ hỗ trợ Java 21+ vì chính sách bảo mật, patch hoặc vận hành, dù một class nào đó chạy trên Java 17.

### Ba điều biên dịch thành công không bảo đảm

- Không chứng minh mọi **dependency** cùng có class-file major hợp lệ trên JVM cũ.
- Không chứng minh các **API nạp ở runtime** (reflection, `ServiceLoader`, plugin, JNI) tồn tại trên JVM cũ.
- Không chứng minh môi trường OS/container, module path, TLS, file permissions và các đường nghiệp vụ chạy đúng.

Vì vậy, phải tách **compile checks**, **artifact inspection** và **runtime tests** thành những bước riêng.

## 3. Class file major version: ranh giới định dạng JVM

`javac` tạo tệp `.class`. Mỗi file mang `major_version`, cho biết phiên bản class-file format.

| Java | Major version |
| --- | ---: |
| Java 11 | 55 |
| Java 14 | 58 |
| Java 17 | 61 |
| Java 21 | 65 |
| Java 22 | 66 |
| Java 23 | 67 |
| Java 24 | 68 |
| Java 25 | 69 |
| Java 26 | 70 |

Theo Java Virtual Machine Specification, JVM Java 17 nhận class files thông thường đến major **61**; JVM Java 21 đến **65**; JVM Java 24 đến **68**.

Class file major 68 không thể được nạp trên Java 17, bất kể source chỉ dùng vài phép toán đơn giản. Trường hợp đó thường dẫn đến **`UnsupportedClassVersionError`**.

### Cách xem major version

~~~bash
javap -verbose -classpath out17 CompatibilityDemo
~~~

Trong output có thể tìm:

~~~text
major version: 61
~~~

Đây là kết quả đã kiểm chứng của ví dụ biên dịch `--release 17` ở mục 5.

Nếu ứng dụng gồm nhiều class, cần kiểm tra **tất cả những class có thể được tải**, không chỉ main class. Một JAR được tạo từ nhiều module hoặc một fat JAR có thể trộn class files của nhiều phiên bản Java.

Để xem thành phần:

~~~bash
jar --list --file application.jar
~~~

Đây là lệnh minh họa; `application.jar` phải là file đã build thực tế. Với một class trong JAR:

~~~bash
javap -verbose -classpath application.jar com.example.Main
~~~

Hãy thay tên lớp bằng tên fully qualified thật trong artifact. `javap` kiểm tra class format và bytecode, **không tự chứng minh API hoặc hành vi runtime tương thích**.

### Vì sao class major 61 chưa đủ?

Một class major 61 có thể chứa lời gọi tới phương thức chỉ xuất hiện từ Java 21, nếu được compile trên JDK 24 bằng cấu hình sai. JVM 17 nạp class thành công về mặt định dạng nhưng **không tìm thấy method khi resolve**. Khi đó lỗi điển hình là `NoSuchMethodError`, không phải `UnsupportedClassVersionError`.

Tóm lại: major version là **cửa kiểm tra đầu tiên**, không phải giấy chứng nhận minimum runtime.

## 4. Dùng javac --release thay vì chỉ -source/-target

Lệnh khuyến nghị cho mã Java cần chạy từ Java 17:

~~~bash
javac --release 17 -encoding UTF-8 -d out17 CompatibilityDemo.java
~~~

`--release 17` kiểm soát ba khía cạnh:

1. **Language level:** chỉ những tính năng cú pháp đã có trong Java 17.
2. **Target class file:** sinh định dạng phù hợp Java 17, thông thường major 61.
3. **Platform API:** kiểm tra lời gọi trực tiếp đối với tập **Java SE/JDK APIs công khai, được hỗ trợ cho Java 17**, không mặc nhiên cho gọi API mới của JDK build.

Đặc biệt, điểm (3) làm `--release` khác với:

~~~bash
javac -source 17 -target 17 -d outLoose NewApiPitfall.java
~~~

`-source 17` chủ yếu giới hạn ngôn ngữ; `-target 17` chủ yếu giới hạn class format. Trên JDK mới, chúng có thể vẫn dùng **platform APIs của JDK mới** khi không cấu hình đúng system modules. Đây là một bẫy đã được kiểm thử bằng chương trình Java 21 API ở mục 6.

### Những điều cần lưu ý về --release

- `--release` không tự cài JRE 17, không chọn JVM của người dùng và không tạo runtime 17.
- Không kết hợp `--release 17` với `-source 17` hoặc `-target 17` trong cùng lệnh.
- Các bản `javac` chỉ hỗ trợ một số release trước đó; chạy `javac --help` để xem danh sách được hỗ trợ trên JDK đang dùng.
- `--release` hạn chế truy cập API nội bộ không được công bố ở release đích; không tìm cách vô hiệu hóa kiểm tra bằng `--add-exports`.
- `--release` **không biên dịch lại thư viện bên thứ ba** và không bảo đảm thư viện đó tương thích Java 17.
- `--release` không phát hiện tất cả reflection, dynamic loading, JNI hoặc thay đổi semantics/hành vi giữa các runtime.

Nếu muốn dùng một tính năng từ Java 21, cần **nâng minimum runtime lên Java 21** hoặc thiết kế phần optional implementation riêng, thay vì lách compiler rồi công bố hỗ trợ Java 17.

## 5. Ví dụ hoàn chỉnh: build trên JDK 24, chạy bằng Java 17 và 21

Tạo **`CompatibilityDemo.java`**:

~~~java
import java.util.List;

public class CompatibilityDemo {
    record Line(String sku, long unitCents, int quantity) {}

    public static void main(String[] args) {
        List<Line> lines = List.of(
            new Line("A", 1250, 2),
            new Line("B", 350, 3)
        );

        long sum = 0;
        for (Line line : lines) {
            sum = Math.addExact(
                sum,
                Math.multiplyExact(
                    line.unitCents(), (long) line.quantity()
                )
            );
        }

        System.out.println("total-cents=" + sum);
        System.out.println("record-type=" + Line.class.isRecord());
        System.out.println("runtime-at-least-17=" +
            (Runtime.version().feature() >= 17));
    }
}
~~~

Đây là **chương trình độc lập Java 17+**. Record, `List.of`, `Math.addExact` và `Class.isRecord()` đều thuộc các API/tính năng đã có trên Java 17.

Lệnh:

~~~bash
javac --release 17 -encoding UTF-8 -d out17 CompatibilityDemo.java
javap -verbose -classpath out17 CompatibilityDemo
java -cp out17 CompatibilityDemo
~~~

**`javap` đã in**:

~~~text
major version: 61
~~~

**Stdout đã kiểm thử thực tế trên Java 17 và Java 21**, sau khi biên dịch bằng JDK 24:

~~~text
total-cents=3550
record-type=true
runtime-at-least-17=true
~~~

Giải thích:

- Tổng = `1250 × 2 + 350 × 3 = 3550` cents.
- `Line` là record, `Line.class.isRecord()` trả `true`.
- `Runtime.version().feature()` trả feature version của JVM **đang chạy**, không phải của compiler đã tạo class.
- Trên Java 17 và Java 21, điều kiện `>= 17` đều đúng.
- Quan trọng nhất: mã **thật sự đã chạy** trên runtime thấp nhất trong tuyên bố thử nghiệm (Java 17).

**Một phép kiểm tra Runtime.version() trong main không phải cơ chế bảo đảm tương thích.** Nếu bytecode quá mới, JVM cũ có thể không nạp được main class nên code check này không bao giờ được thực thi.

### Cách gọi đúng Java trên máy có nhiều JDK

Nếu nhóm build đã cấu hình hai biến môi trường `JAVA17_HOME` và `JAVA21_HOME` tới thư mục gốc của các JDK trên Windows PowerShell:

~~~powershell
& (Join-Path $env:JAVA17_HOME "bin\java.exe") -cp out17 CompatibilityDemo
& (Join-Path $env:JAVA21_HOME "bin\java.exe") -cp out17 CompatibilityDemo
~~~

Hai biến môi trường này **phải được cấu hình trước**; ví dụ không giả định chúng có sẵn trên mọi máy. Trên Linux/macOS, dùng đường dẫn tới `bin/java` của JDK tương ứng. Luôn kiểm tra:

~~~bash
java -version
javac -version
~~~

trong chính shell/container/runner được dùng để build hoặc test. PATH có thể khác với JAVA_HOME; xác nhận **đường dẫn thực** khi nghi có nhiều JDK.

## 6. Bẫy đã kiểm thử: class Java 17 nhưng lại gọi List.getFirst() của Java 21

`java.util.List.getFirst()` được bổ sung từ **Java 21**. Nó không có trong Java 17.

Tạo **`NewApiPitfall.java`**:

~~~java
import java.util.List;

public class NewApiPitfall {
    public static void main(String[] args) {
        System.out.println(List.of("old", "new").getFirst());
    }
}
~~~

### 6.1. -source/-target không đủ để giới hạn API

Biên dịch bằng **JDK 24**:

~~~bash
javac -source 17 -target 17 -encoding UTF-8 -d outLoose NewApiPitfall.java
~~~

Trong thử nghiệm, chương trình **compile pass**, kèm warning từ `javac` rằng vị trí system modules không được đặt cho `-source 17` và nên dùng `--release 17`.

Chạy:

~~~bash
javap -verbose -classpath outLoose NewApiPitfall
~~~

Kết quả:

~~~text
major version: 61
~~~

**Nhưng trên runtime Java 17 thật**, nó **không chạy được**, báo lỗi:

~~~text
java.lang.NoSuchMethodError: 'java.lang.Object java.util.List.getFirst()'
~~~

Stack trace và chữ ký trong message có thể thay đổi giữa JDK vendors; loại lỗi `NoSuchMethodError` và nguyên nhân method không tồn tại mới là trọng tâm.

Chính class file đó **chạy thành công trên Java 21**, in:

~~~text
old
~~~

Vì sao?

1. Cú pháp gọi `list.getFirst()` hợp lệ về mặt Java language 17: nó chỉ là một lời gọi method.
2. `-target 17` sinh class major 61.
3. Compiler JDK 24 thấy `List.getFirst()` trong API JDK 24, nên compile thành công.
4. Runtime Java 17 biết class major 61 nhưng **không có method getFirst() trên List**.
5. Khi thực hiện lời gọi, JVM phát sinh `NoSuchMethodError`.

Vậy nên **class-file version bằng Java 17 không đồng nghĩa với minimum runtime Java 17**.

### 6.2. --release 17 bắt API mới ngay khi compile

Biên dịch lại:

~~~bash
javac --release 17 -encoding UTF-8 -d outStrict NewApiPitfall.java
~~~

Kết quả thực nghiệm trên JDK 24: **compile fail**, vì compiler không tìm thấy `getFirst()` trong tập API Java 17.

~~~text
error: cannot find symbol
  symbol:   method getFirst()
  location: interface java.util.List<String>
~~~

Đây là **trích phần thông tin chính** chứ không phải toàn bộ output, vì đường dẫn nguồn và dấu mũ vị trí thay đổi theo môi trường.

Nếu hợp đồng là Java 17, dùng API có mặt trong Java 17; với list chắc chắn không rỗng:

~~~java
List<String> names = List.of("old", "new");
System.out.println(names.get(0));
~~~

Đây là **mảnh mã minh họa**, không phải file độc lập. `get(0)` có hành vi khác khi list rỗng, nên lựa chọn API cần phù hợp hợp đồng.

### 6.3. Bảng kiểm thử thực tế

| Thao tác | Kết quả compile/class | Java 17 | Java 21 |
| --- | --- | --- | --- |
| JDK 24 `--release 17`, `CompatibilityDemo` | PASS, major 61 | PASS | PASS |
| JDK 24 `-source 17 -target 17`, `NewApiPitfall` | PASS, major 61 | **NoSuchMethodError** | PASS, in `old` |
| JDK 24 `--release 17`, `NewApiPitfall` | **Không biên dịch** | Không tới bước chạy | Không tới bước chạy |
| JDK 24 compile mặc định `CompatibilityDemo` | PASS, major 68 | **UnsupportedClassVersionError** | **UnsupportedClassVersionError** |

Các kết quả trên đã được xác nhận với **compiler OpenJDK 24, runtime Java 17 và Java 21**. Đây là kết quả thử nghiệm xác thực, không phải suy đoán.

## 7. Bẫy khác: compile mặc định trên JDK 24 tạo class major 68

Nếu bỏ `--release`:

~~~bash
javac -encoding UTF-8 -d out24 CompatibilityDemo.java
~~~

thì `javac` JDK 24 mặc định dùng target JDK 24, mặc dù source chưa dùng tính năng mới hơn Java 17.

Kiểm tra:

~~~bash
javap -verbose -classpath out24 CompatibilityDemo
~~~

Đã kiểm chứng:

~~~text
major version: 68
~~~

Khi chạy trên Java 17, JVM không thể nạp class major 68 và báo **`UnsupportedClassVersionError`**. Thông điệp thử nghiệm giải thích JVM Java 17 chỉ hỗ trợ tối đa class file **61.0**, trong khi class mới là **68.0**.

Khác biệt quan trọng:

| Lỗi | JVM đã nạp được class format chưa? | Đề xuất đầu tiên |
| --- | --- | --- |
| `UnsupportedClassVersionError` | Chưa, version quá mới | Sửa release/bytecode hoặc chọn JVM mới hơn |
| `NoSuchMethodError` | Có thể có, nhưng phương thức cần gọi không có | Kiểm tra JDK API/dependency thực của runtime |

Cả hai có thể xuất hiện khi chương trình “compile tốt trên máy tôi” nhưng lỗi khi được triển khai ở máy khác.

## 8. Minimum runtime không thể suy ra từ major version duy nhất

Để công bố minimum runtime, phải kiểm tra:

1. **Class major** của app, generated classes và dependencies.
2. **API Java/JDK** mà code dùng trực tiếp hoặc thông qua thư viện.
3. **Các modules** có sẵn trong runtime (như `java.sql`, `java.net.http`, `jdk.management`).
4. **Thư viện ngoài**, gồm cả những thư viện được nạp động.
5. **Reflection**, `Class.forName`, `ServiceLoader`, MethodHandles và code generation.
6. **Native libraries** và điều kiện OS/CPU architecture/ABI.
7. **Preview features** và JDK-specific functionality nếu có.
8. **Hành vi lúc chạy**: TLS/security providers, encoding, locale, file system, container limits.
9. **Đường triển khai**: JAR chạy với Java cài sẵn, container runtime, `jlink` image hay `jpackage` app image.

Một công thức kiểm thử thực tế là:

~~~text
Biên dịch với --release <baseline>
    + Kiểm tra class files/dependencies
    + Kiểm tra JDK APIs/modules bắt buộc
    + Kiểm thử trên JVM <baseline> thật
    + Kiểm thử packaged artifact trên OS/container đích
    = Bằng chứng hỗ trợ runtime <baseline>
~~~

Dòng trên là **quy trình kiểm thử**, không phải chứng minh toán học tuyệt đối cho mọi nhánh ứng dụng. Cần chọn phạm vi test đủ bao phủ các chức năng được hỗ trợ.

### Third-party dependency nâng mức Java tối thiểu

Một ứng dụng chính major 61 có thể tham chiếu một thư viện major 65. Khi JVM Java 17 phải tải class thư viện đó, lỗi **`UnsupportedClassVersionError`** vẫn xảy ra.

Hoặc một library major 61 có thể được build trên JDK mới nhưng gọi API Java 21 do dùng `-source/-target` chưa đúng. Lúc đó lỗi liên kết có thể phát sinh về sau.

`--release 17` **không sửa bytecode của third-party JAR**. Khi nâng dependency, đọc release notes về minimum Java version và chạy lại test matrix.

### jdeps giúp gì và không giúp gì?

Lệnh ví dụ:

~~~bash
jdeps --recursive --summary application.jar
jdeps --jdk-internals application.jar
~~~

`jdeps` giúp phân tích **static dependencies**, mô-đun và truy cập JDK internal APIs trong bytecode. Khi classpath/module path có các JAR ngoài, phải truyền đủ dependency locations theo lựa chọn `jdeps` của JDK đó.

Nó **không thể đảm bảo tìm hết** class được nạp qua reflection, ServiceLoader, JNI hoặc plugin. Kết quả jdeps là đầu vào điều tra, **không thay thế kiểm thử chạy thật**.

## 9. Xác định phiên bản Java qua Runtime.version() có đủ không?

Java cho phép:

~~~java
int feature = Runtime.version().feature();
System.out.println(feature);
~~~

Đây là **mảnh mã**. Giá trị in là feature version của runtime đang chạy, không phải JDK dùng để biên dịch.

Nhưng nếu main class major 68 được đưa vào JVM 17, class **không nạp được**, nên phương thức `main` không thể chạy tới kiểm tra này. Vì vậy:

- `Runtime.version()` hữu ích để hiển thị hoặc quyết định hành vi tùy chọn **sau khi app đã nạp**.
- Không dùng nó thay `--release`.
- Không dùng một `if (feature >= 21)` để mặc nhiên tin code chứa API21 sẽ an toàn trên JVM17.
- Nếu cần phần tính năng chỉ cho Java21, nên tách implementation nạp có điều kiện, kiểm soát class linkage và test trên JVM17 và JVM21.
- Nếu ứng dụng **bắt buộc** Java21, cách đơn giản hơn là công bố minimum Java21 và dùng `--release 21`, rồi test JVM21.

## 10. Preview features không phải cách hạ mức runtime

Một số tính năng ngôn ngữ/JVM từng được cung cấp ở dạng preview trước khi final. Preview có quy tắc `--enable-preview` và **class file minor version 65535** theo JVM Specification.

Không suy rằng code được biên dịch preview trên JDK mới sẽ chạy với preview runtime cũ hoặc mọi runtime mới hơn. Nếu minimum runtime cần tính ổn định cao:

- Ưu tiên tính năng **đã final** ở baseline.
- Không dùng các API incubator/preview chỉ để viết code kiểu mới rồi quảng bá hỗ trợ Java cũ.
- Kiểm tra `major_version` và `minor_version` nếu artifact có preview.
- Test bằng **đúng JVM phiên bản được yêu cầu và flag preview**.
- Khi build đa phiên bản, cân nhắc mô-đun hoặc thư viện được tách theo runtime thay vì gắn preview khắp code base.

Ví dụ `record` chính thức từ Java 16, nên hợp lệ với baseline Java 17. Nó không phải tính năng ổn định của Java 14. Trái lại, `List.getFirst()` chỉ xuất hiện từ Java21 dù cú pháp method call vốn đã tồn tại lâu.

## 11. Multi-release JAR: dùng API mới nhưng vẫn có baseline cũ

**Multi-release JAR** là cơ chế chính thức trong JAR File Specification để cung cấp nhiều implementation tương thích những phiên bản Java khác nhau.

Ví dụ manifest:

~~~text
Multi-Release: true
~~~

và bố cục:

~~~text
com/example/Feature.class
META-INF/versions/21/com/example/Feature.class
~~~

Giả sử class ở root được biên dịch cho Java 17, class trong `META-INF/versions/21` dùng API Java 21:

- JVM Java 17 dùng bản class **ở root**.
- JVM Java 21+ có thể chọn bản versioned phù hợp, theo nguyên tắc phiên bản cao nhất không vượt JVM.
- Cấu trúc và metadata JAR phải chính xác; có những ràng buộc nhất quán đối với **public/protected API** giữa các variants.
- Mỗi variant cần được compile bằng release phù hợp và kiểm thử trên JVM mục tiêu.
- Chỉ đặt một class vào đường dẫn `META-INF/versions/21` **không tự sửa** các dependency hoặc tương thích của bản baseline.

Đây là **sơ đồ artifact minh họa**, không phải script xây MR-JAR hoàn chỉnh. Nếu không có nhu cầu phát hành thư viện hỗ trợ nhiều Java versions, dùng một baseline release thống nhất thường dễ vận hành hơn.

Với `jdeps` kiểm tra multi-release JAR, xem option `--multi-release` của phiên bản JDK đang dùng để phân tích đúng runtime view.

## 12. Maven: compiler release khác JVM chạy tests

Trong **`pom.xml`**, có thể cấu hình:

~~~xml
<properties>
    <maven.compiler.release>17</maven.compiler.release>
</properties>
~~~

Đây là **mảnh cấu hình**, yêu cầu Maven Compiler Plugin phiên bản phù hợp.

Nó định nghĩa mục tiêu compile nhưng **không có nghĩa `mvn test` chắc chắn đang chạy trên Java 17**.

Một quy trình Maven:

1. Kiểm tra `mvn -version` và JDK mà Maven thật sự sử dụng.
2. Đặt compiler release 17.
3. Chọn dependency versions còn hỗ trợ Java17.
4. Chạy unit/integration tests trong CI job dùng **JVM17 thật**.
5. Chạy thêm job trên Java21 và những Java versions khác được cam kết hỗ trợ.
6. Kiểm thử final JAR/container/app image, không chỉ `target/classes`.

Maven Toolchains có thể giúp cố định JDK dùng bởi plugin. Nếu toolchain build và runtime test dùng hai JDK khác nhau, cần ghi rõ từng nhiệm vụ thay vì để PATH quyết định âm thầm.

### Gradle: toolchain và release đều cần hiểu riêng

Ví dụ **`build.gradle.kts`** khi muốn compiler JDK17:

~~~kotlin
java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

tasks.withType<JavaCompile>().configureEach {
    options.release.set(17)
}
~~~

Đây là **mảnh Kotlin DSL** trong dự án đã sử dụng Java plugin.

- `toolchain` chọn JDK để thực hiện tác vụ build tương ứng.
- `options.release.set(17)` đặt source/API/bytecode target.
- Test runtime vẫn cần được cấu hình và kiểm tra qua toolchain/test launcher hoặc CI job.
- Nếu build compiler trên JDK mới hơn, vẫn có thể đặt release 17, nhưng phải xác nhận compiler hỗ trợ release đó.

**Minimum Java để chạy Gradle/Maven bản đang dùng là chuyện khác minimum Java để chạy ứng dụng đã build.** Không nhầm yêu cầu của build tool với compatibility policy của artifact.

## 13. jlink, jpackage và container không tự chọn Java tối thiểu

Tình huống:

1. `javac --release 17` tạo class major 61.
2. Dùng `jpackage --type app-image` bằng JDK 24.
3. Không truyền `--runtime-image`.

`jpackage` có thể dùng `jlink` để tạo runtime **dựa trên JDK build (24)**. Ứng dụng trong app image chạy với runtime đó, **không tự chuyển thành runtime 17** do bytecode target 17.

Phân biệt:

| Công cụ | Kiểm soát |
| --- | --- |
| `javac --release 17` | Ngôn ngữ, JDK API và class file |
| `jlink` | Tập modules và phiên bản Java runtime image được link |
| `jpackage` | Launcher, app image/installer, runtime đi kèm |
| Container base image | Java runtime thực có sẵn trong container, nếu không đóng runtime riêng |

Với một app image đóng runtime, người dùng cuối **không cần cài Java toàn cục**. Câu hỏi deployment khi ấy là runtime nào được nhúng, OS/architecture nào hỗ trợ và ai chịu trách nhiệm cập nhật runtime bảo mật.

Với JAR chạy trực tiếp, việc chọn `java` ở service config/PATH/JAVA_HOME/container ảnh hưởng trực tiếp đến Java runtime thật.

**Kiểm thử artifact sau đóng gói** là thiết yếu. Chạy mã trong IDE không chứng minh rằng bản jpackage, shaded JAR hoặc container cuối cùng giống môi trường đã test.

## 14. Các lỗi runtime nên nhận diện đúng

| Lỗi | Nguyên nhân thường gặp | Hướng xử lý |
| --- | --- | --- |
| `UnsupportedClassVersionError` | Class file major/minor không được JVM hỗ trợ | Xem runtime version, `javap -verbose` và build release |
| `NoSuchMethodError` | Runtime không có method signature đã dùng khi compile | Kiểm tra JDK API và phiên bản dependency thực được tải |
| `NoSuchFieldError` | Field có lúc compile nhưng vắng lúc link runtime | Phân tích binary compatibility/classpath |
| `NoClassDefFoundError` | Class phụ thuộc không tải được hoặc khởi tạo lỗi | Kiểm tra JAR/module path và `Caused by` |
| `ClassNotFoundException` | Dynamic class loading theo tên thất bại | Kiểm tra class loader, JAR và plugin config |
| `java.lang.module.FindException` | Missing required module hoặc module resolution lỗi | Kiểm tra `module-info.java`, jlink image/module path |
| `UnsatisfiedLinkError` | JNI/native library không tương thích hoặc không có | Kiểm tra OS/arch/ABI/library path |
| `InaccessibleObjectException` | Reflection vi phạm module encapsulation | Dùng public API hoặc thiết kế module access phù hợp |
| Kết quả sai dù không exception | Runtime/OS/locale/provider semantics khác | Kiểm thử tích hợp, logs và số liệu môi trường |

**`NoSuchMethodError` không nhất thiết do JDK quá cũ.** Nó còn do library version conflict, classpath shadowing hoặc JAR không tương thích nhị phân. Điều tra chữ ký method, module/JAR thực và runtime loader trước khi kết luận.

## 15. CI matrix để chứng nhận minimum runtime

Giả sử sản phẩm công bố **Java 17+**:

| Job | Build | Runtime tests | Mục tiêu |
| --- | --- | --- | --- |
| Compile baseline | JDK hiện hành, `--release 17` | — | Chặn syntax/API/bytecode trên mức 17 |
| Runtime thấp nhất | Artifact `--release 17` | **Java 17** | Xác nhận compatibility quan trọng nhất |
| Runtime tiếp theo | Cùng artifact | Java 21 | Bắt khác biệt hành vi ở JVM mới hơn |
| Runtime hiện hành | Cùng artifact | JDK build/mới hơn | Phát hiện thay đổi mới |
| Dependency/plugin checks | Artifact đã đóng gói | **Java 17** | Đọc/nạp các nhánh plugin, reflection, JNI |
| Container/app-image tests | Image phát hành thật | Runtime của image | Xác nhận OS/modules/runtime thực tế |

Để CI có bằng chứng:

~~~bash
java -version
javac -version
javap -verbose -classpath out17 CompatibilityDemo
~~~

Với Maven/Gradle, ghi thêm build tool version và JDK của job. Tên nhãn “test on Java 17” không đủ nếu PATH đang trỏ tới `java` của JDK24; hãy kiểm tra executable.

**Tối thiểu phải test trên JVM thấp nhất.** Tests chỉ chạy trên JVM24 không phát hiện lỗi `List.getFirst()` trong artifact có major 61 được tạo bằng `-source/-target`.

### Các đường kiểm thử thiết yếu

- Khởi động app entry point, chạy các flows quan trọng.
- Unit tests và integration tests cho API, database, network, TLS và serialization.
- Nạp plugins, reflection, `ServiceLoader`, code-generated classes.
- Test native/JNI và resources khi runtime/OS khác nhau.
- Test module resolution khi chạy trong jlink image.
- Test packaged artifact final, không chỉ bản classes ở thư mục build.
- Test đường xử lý lỗi, startup/shutdown, scheduled jobs và worker threads.

Không có đủ coverage thì phải mô tả phạm vi xác nhận thay vì tuyên bố **mọi tính năng** đều tương thích.

## 16. Quy trình chẩn đoán khi triển khai thất bại

### A. Lỗi class-file version

Nếu log ghi:

~~~text
UnsupportedClassVersionError: ... class file version 68.0
... runtime only recognizes versions up to 61.0
~~~

Hành động:

1. Chạy `java -version` ngay trong container/service bị lỗi.
2. Dùng `javap -verbose` kiểm tra class thực được đóng gói.
3. Xác định main class hay dependency tạo major 68.
4. Nếu contract là Java17, sửa compile release, chọn dependency hỗ trợ Java17, build lại và test trên Java17.
5. Nếu contract được nâng lên Java24, cập nhật tài liệu/CI/deployment runtime tương ứng.

Đừng sửa thủ công byte major trong tệp `.class`; bytecode hoặc API có thể không còn hợp lệ.

### B. Lỗi NoSuchMethodError dù major 61

Kiểm tra method được nêu là **JDK method hay dependency method**. Tra Javadoc đúng Java17; nếu method chỉ có từ Java21 thì dùng API cũ hơn hoặc nâng minimum. Nếu method thuộc thư viện, kiểm tra đúng version JAR ở runtime và tránh trùng class.

`--release 17` giúp bắt các lời gọi JDK API mới **trực tiếp trong source** khi biên dịch; nó không tự bắt mọi class nạp động.

### C. App chạy ở local nhưng lỗi trong container/app image

Kiểm tra image có runtime nào, modules nào, architecture và native libraries ra sao. Một runtime rút gọn có thể thiếu modules mặc dù full JDK17 hoạt động. Cùng một Java major nhưng hai environment vẫn khác về filesystem, certificates, locale và permissions.

## 17. Những nhầm lẫn cần tránh

| Nhầm lẫn | Sự thật |
| --- | --- |
| “Compiler JDK24 thì runtime phải Java24.” | Có thể nhắm Java17 bằng `--release 17` và test JVM17. |
| “Compiler pass chứng minh runtime tối thiểu.” | Compile không thay cho runtime test. |
| “-source 17 và -target 17 tương đương --release 17.” | Chúng có thể cho phép API JDK mới lọt vào class major61. |
| “Major 61 chắc chắn chạy Java17.” | Có thể gặp `NoSuchMethodError` do API mới. |
| “List.getFirst() có từ trước vì List đã có từ lâu.” | Method này mới từ **Java21**. |
| “Chỉ cần kiểm main class major.” | Dependencies và plugin cũng có class files của riêng chúng. |
| “--release 17 hạ bytecode third-party JAR.” | Không, dependencies phải tương thích riêng. |
| “Runtime.version() trong main sửa được class quá mới.” | JVM cũ có thể không nạp nổi main class. |
| “Preview từ JVM cũ sẽ chạy trên mọi JVM mới.” | Preview có quy tắc version/flag riêng. |
| “Maven compiler release17 khiến mvn test chạy trên Java17.” | Test runtime phụ thuộc CI/toolchain. |
| “App compile release17 nên jpackage tự nhúng runtime17.” | Runtime được chọn độc lập với compiler release. |
| “Java trong container là Java của host.” | Container có runtime do image/container config quyết định. |
| “NoSuchMethodError luôn là JVM thấp.” | Có thể do xung đột phiên bản thư viện. |
| “Kiểm thử JDK24 đủ để công bố Java17.” | Phải kiểm thử **JVM17 thật**. |

## 18. Checklist trước khi công bố phiên bản Java tối thiểu

1. Đã định nghĩa **minimum runtime**, vendor/OS/architecture được hỗ trợ chưa?
2. Đã chạy `javac -version` và xác định JDK của CI chưa?
3. Đã đặt `--release` đúng baseline, thay vì chỉ `-target` chưa?
4. Đã kiểm tra class major/minor của artifact thực tế chưa?
5. Có lời gọi JDK API chỉ xuất hiện sau baseline không?
6. Đã kiểm tra **minimum Java của dependencies**, plugins và generated code chưa?
7. Đã thử nạp reflection/ServiceLoader/JNI trên JVM thấp nhất chưa?
8. Runtime có các modules cần thiết không, nhất là trong jlink image?
9. Có dùng preview/experimental API gây version restriction không?
10. Có chạy integration tests với **JVM thấp nhất** thật chưa?
11. Có test JVM mới hơn mà sản phẩm công bố hỗ trợ chưa?
12. Có thử packaged JAR/app image/container cuối cùng chưa?
13. Đã kiểm tra OS/architecture, TLS, native libs và permissions chưa?
14. Có ghi lại compiler JDK, release target, dependency versions và runtime versions trong CI logs chưa?
15. Khi nâng dependency hoặc toolchain, có chạy lại toàn bộ matrix không?

## 19. Bài tập thực hành có đáp án

### Bài 1 — JDK24 compile, Java17 chạy

**Đề:** ứng dụng chỉ dùng API Java17, máy build là JDK24. Lệnh compiler nào nên dùng?

**Đáp án:** `javac --release 17 ...`, rồi chạy chương trình bằng Java17 thật. Kiểm tra bytecode major61 và các dependencies.

### Bài 2 — Lỗi major

**Đề:** tệp class major68 chạy trên Java21.

**Đáp án:** Java21 chỉ hỗ trợ tới major65. Nếu muốn hỗ trợ Java21 phải biên dịch/đóng gói theo Java21 và dùng API tương thích; không sửa số major thủ công.

### Bài 3 — Class major61 nhưng NoSuchMethodError

**Đề:** `NewApiPitfall` class major61 được tạo từ JDK24 bằng `-source17 -target17`, gọi `List.getFirst()`.

**Đáp án:** method có từ Java21, nên Java17 thiếu API. `--release17` sẽ ngăn compile. Đây không phải lỗi class format.

### Bài 4 — Maven CI xanh

**Đề:** Maven đặt `maven.compiler.release=17` nhưng toàn bộ test chạy trên Java24.

**Đáp án:** chưa chứng minh tương thích Java17. Bổ sung job chạy test thật trên Java17, kiểm tra dependency và artifact cuối.

### Bài 5 — Third-party plugin

**Đề:** `App.class` major61, `Plugin.class` major65.

**Đáp án:** khi Java17 cần nạp plugin, nó có thể báo UnsupportedClassVersionError. Phải chọn plugin tương thích Java17 hoặc nâng minimum runtime.

### Bài 6 — Java version check

**Đề:** một app major65 thêm `if (Runtime.version().feature() < 21)` ở đầu main, rồi thử chạy trên Java17.

**Đáp án:** JVM17 không nạp được class major65; check trong main không chạy. Muốn thông báo đẹp trước khi nạp code mới, cần bootstrap/launcher tương thích thấp hơn hoặc kiểm tra runtime bên ngoài JVM.

### Bài 7 — Multi-release JAR

**Đề:** JAR có root class target17, `META-INF/versions/21` chứa class dùng Java21, manifest có `Multi-Release: true`.

**Đáp án:** Java17 dùng root; Java21+ có thể dùng class versioned phù hợp. Cả hai cần build/test đúng version và ràng buộc public API.

### Bài 8 — Đóng gói bằng jpackage

**Đề:** app compile release17, sau đó jpackage bằng JDK24 không cấp `--runtime-image`.

**Đáp án:** app image có thể nhúng runtime từ JDK24. Release17 mô tả target bytecode/API, không nói runtime nào được đóng vào image.

### Bài 9 — Lập test matrix

Hãy tự chạy `CompatibilityDemo.java` và `NewApiPitfall.java` trong bài với bốn cấu hình ở mục 6.3. Ghi lại:

- `javac` version/flags.
- Compile pass/fail.
- Class major version.
- Java17/Java21 run pass/fail.
- Exception loại nào khi fail và vì sao.

Đối chiếu với kết quả đã kiểm chứng, rồi viết một câu công bố **minimum runtime** dựa trên bằng chứng chứ không dựa vào tên thư mục build.

## 20. Tài liệu chính thức hiện còn áp dụng

- [Oracle JDK 25 — javac Command](https://docs.oracle.com/en/java/javase/25/docs/specs/man/javac.html): `--release` so với `--source/--target`, giới hạn API nền tảng, cross-compilation.
- [Oracle JDK 17 — javac Command](https://docs.oracle.com/en/java/javase/17/docs/specs/man/javac.html): cấu hình Java17 target.
- [Java Virtual Machine Specification 26 — Class-file versions](https://docs.oracle.com/javase/specs/jvms/se26/html/jvms-1.html): bảng major 55, 58, 61, 65, 68, 69, 70.
- [Java Virtual Machine Specification 25 — ClassFile structure](https://docs.oracle.com/javase/specs/jvms/se25/html/jvms-4.html#jvms-4.1): major/minor version, preview.
- [Oracle JDK 21 — List.getFirst()](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/List.html#getFirst()): API có từ Java21, dùng trong tình huống minh họa.
- [Oracle JDK 25 — javap Command](https://docs.oracle.com/en/java/javase/25/docs/specs/man/javap.html): xem metadata/class versions.
- [Oracle JDK 25 — jdeps Command](https://docs.oracle.com/en/java/javase/25/docs/specs/man/jdeps.html): phân tích phụ thuộc và multi-release JARs.
- [Oracle Java 17 — JAR File Specification](https://docs.oracle.com/en/java/javase/17/docs/specs/jar/jar.html): `Multi-Release: true` và `META-INF/versions/N`.
- [Apache Maven Compiler Plugin — Setting --release](https://maven.apache.org/plugins/maven-compiler-plugin/examples/set-compiler-release.html): cấu hình `maven.compiler.release`.
- [Gradle — Java Toolchains](https://docs.gradle.org/current/userguide/toolchains.html): cấu hình Java compiler/toolchain/test runtime.
