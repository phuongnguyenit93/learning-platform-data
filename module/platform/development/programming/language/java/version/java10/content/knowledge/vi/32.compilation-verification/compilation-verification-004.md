# Phân biệt cấu hình ngôn ngữ nguồn với lựa chọn API nền tảng trong Java

## 1. Vấn đề: mã có cú pháp Java 10 chưa chắc chạy được trên Java 10

Hãy xét đoạn mã này:

~~~java
public class Example {
    public static void main(String[] args) {
        var text = "  Java  ";
        System.out.println(text.strip());
    }
}
~~~

- `var` dùng để khai báo biến cục bộ với kiểu suy luận; đây là **tính năng ngôn ngữ Java 10** (JEP 286).
- `String.strip()` là **phương thức API thư viện chuẩn được thêm từ Java 11**.
- Một compiler JDK 17 có thể hiểu **cú pháp** trên và tìm thấy `strip()` trong thư viện Java 17.
- Nhưng một JVM Java 10 không có phương thức `String.strip()`. Nếu chỉ tạo bytecode Java 10 mà vẫn link tới API Java 17, ứng dụng có thể bị `NoSuchMethodError` khi đến lời gọi đó.

Đây là lỗi phân biệt **mức cú pháp nguồn** với **API nền tảng có sẵn trên runtime đích**.

Nguyên tắc quan trọng:

> **Cú pháp hợp lệ ở một Java release không chứng minh rằng mọi class/method đang được gọi đều tồn tại trên chính release ấy.**

Muốn tạo artifact chạy trên một Java runtime cụ thể, cần kiểm **ba tầng**:

1. **Source language level**: mã nguồn được phép dùng những đặc tính cú pháp Java nào?
2. **Class-file target level**: compiler tạo phiên bản file `.class` mà JVM nào có thể đọc?
3. **Platform API level**: lúc biên dịch, code được phép tham chiếu tới những class/method/field của Java SE/JDK release nào?

Ngoài ba tầng trên còn phải xét **thư viện bên thứ ba**, **runtime thật** và các điều kiện của ứng dụng như operating system, module configuration hoặc native libraries.

Bài thuộc mục **Biên dịch và kiểm chứng** trong module **Java 10**. Tuy vậy, hướng dẫn chính sử dụng `javac --release` và công cụ build **còn được hỗ trợ trên các JDK hiện đại**. Java 10 được dùng để giải thích sự ra đời của `var` và lỗi tương thích, không được đề xuất như một runtime production cần triển khai ngày nay.

## 2. Những khái niệm nền tảng

### 2.1. Source level: compiler chấp nhận cú pháp gì?

Lệnh `javac` có tùy chọn:

~~~text
--source <release>
-source <release>
~~~

Ví dụ, trên một compiler có hỗ trợ mục tiêu này:

~~~bash
javac --source 17 MyProgram.java
~~~

`--source 17` yêu cầu compiler kiểm **quy tắc ngôn ngữ Java 17**. Nó kiểm tra các đặc tính như switch expression, records, pattern matching theo mức ngôn ngữ tương ứng, việc dùng từ khóa dành riêng hoặc cú pháp được giới thiệu sau mức đó.

Nhưng `--source` **không tự đặt bộ API nền tảng** về đúng Java 17 nếu bạn đang chạy compiler JDK 25. Nếu thiếu cấu hình API platform, trình biên dịch vẫn có thể nhìn các class/method thuộc **platform của compiler đang dùng**, rồi chấp nhận một lời gọi không tồn tại trên runtime mục tiêu.

Và `--source` **không tự buộc mọi dependency** hỗ trợ Java 17.

### 2.2. Class-file target: JVM nào đọc được bytecode?

Tùy chọn:

~~~text
--target <release>
-target <release>
~~~

Ví dụ:

~~~bash
javac --source 17 --target 17 MyProgram.java
~~~

`--target 17` tạo bytecode theo phiên bản class-file dành cho Java 17. JVM cũ hơn Java 17 sẽ không đọc được class-file có major version 61.

Bảng tham khảo một số **class-file major versions**:

| Java release | Class-file major |
| ---: | ---: |
| Java 8 | 52 |
| Java 9 | 53 |
| Java 10 | 54 |
| Java 11 | 55 |
| Java 17 | 61 |
| Java 21 | 65 |
| Java 25 | 69 |
| Java 26 | 70 |

Lưu ý một class có **major version 54** là **điều kiện cần** để JVM Java 10 hiểu được định dạng bytecode đó, **không phải điều kiện đủ** để bảo đảm các API mà class gọi tồn tại trong Java 10.

`--target` cũng không thay đổi dependency JAR, thư viện native hay môi trường triển khai. Nếu một JAR bên ngoài chứa class-file major quá mới, runtime cũ vẫn có thể ném `UnsupportedClassVersionError` khi tải class ấy.

### 2.3. Platform API level: class/method có tồn tại trên release đích?

Ví dụ API có mốc phát hành cụ thể:

| API/thành phần | Có từ release | Ghi chú |
| --- | ---: | --- |
| `java.util.List.of(...)` | Java 9 | Factory tạo danh sách không chỉnh sửa được |
| `String.strip()` | Java 11 | Loại bỏ leading/trailing whitespace theo Unicode semantics |
| `String.isBlank()` | Java 11 | Kiểm chuỗi chỉ gồm whitespace |
| `Files.readString(Path)` | Java 11 | Đọc file thành string |
| `Stream.toList()` | Java 16 | Terminal operation trả list unmodifiable |
| `java.util.HexFormat` | Java 17 | Chuyển đổi dữ liệu hex |

Một chương trình chỉ dùng cú pháp Java 10 vẫn có thể gọi `String.strip` hoặc `Stream.toList` nếu compiler đang nhìn API Java 17+. **Lựa chọn API nền tảng** phải được ràng buộc riêng để tránh lỗi khi triển khai trên Java 10.

### 2.4. JDK biên dịch khác JVM chạy

Cần phân biệt:

- **Build JDK/toolchain**: JDK chứa `javac`, Java compiler APIs, annotation processors và tools dùng trong CI.
- **Target platform release**: Java release mà artifact tuyên bố hỗ trợ.
- **Test JDK**: JDK thực tế dùng chạy unit/integration tests.
- **Production JVM**: phiên bản/build/vendor JVM sẽ chạy artifact.

Ví dụ: dùng JDK 21 để biên dịch bằng `--release 17`. Khi đó compiler là JDK 21 nhưng source, bytecode và platform API của ứng dụng được nhắm tới Java 17.

Tuy nhiên, muốn xác nhận ứng dụng thật vận hành đúng, vẫn phải **test trên JVM 17** và với dependencies/cấu hình thực.

## 3. --source, --target và --release: khác nhau ở đâu?

Oracle Java SE 17/25/26 `javac` documentation mô tả:

| Lựa chọn | Giới hạn cú pháp nguồn | Giới hạn class-file | Giới hạn Java platform APIs |
| --- | --- | --- | --- |
| `--source 17` | **Có** | Không phải toàn bộ mục tiêu | **Không tự bảo đảm** |
| `--target 17` | Không tự quy định source theo mục tiêu đầy đủ | **Có** | **Không** |
| `--source 17 --target 17` | **Có** | **Có** | **Không tự bảo đảm** |
| `--release 17` | **Có** | **Có** | **Có**, theo documented API của release 17 |
| Dùng đúng JDK 17 để compile và run | JDK 17 hiểu cú pháp 17 | Đầu ra theo compiler 17 | Compile nhìn JDK 17 APIs | 

**Kết luận:** Khi sử dụng một **JDK mới để xây artifact nhắm runtime cũ hơn**, thường ưu tiên:

~~~bash
javac --release 17 -d out MyProgram.java
~~~

Tùy chọn `--release` thiết lập **đồng thời** ba ràng buộc: language level, class-file target và **tập Java SE/JDK API được hỗ trợ theo release được chọn**.

### 3.1. --release không phải viết gọn “source + target” thuần túy

Lập luận sau **không đúng**:

~~~text
--release 17  ==  --source 17 --target 17
~~~

Bên trái còn khóa **platform API**. Bên phải có thể biên dịch code gọi API mới hơn 17 khi chạy compiler JDK mới mà không chỉ định platform classes đúng phiên bản 17.

Tùy chọn `--release` dựa trên khả năng cross-compilation được giới thiệu bởi **JEP 247 — Compile for Older Platform Versions** (Java 9). Cơ chế nội bộ của `javac` cung cấp thông tin các API hợp lệ cho những release mà compiler hỗ trợ.

### 3.2. --release không đảm bảo toàn bộ ứng dụng tương thích

`--release 17` **không** tự động:

- Kiểm class-file version và API của **mọi JAR third-party** trên runtime.
- Hạ phiên bản một dependency từ Java 21 về Java 17.
- Bảo đảm JNI/native libraries chạy được trên OS/CPU đích.
- Bảo đảm reflection/dynamic class loading chỉ truy cập API 17.
- Bảo đảm tài nguyên cấu hình, dịch vụ mạng, database hoặc module access phù hợp.
- Bảo đảm một method có API hợp lệ nhưng behavior sẽ giống nhau trên mọi vendor/build.
- Bảo đảm mã được tạo bởi một tool build bên ngoài `javac` đã tuân thủ cùng mục tiêu.
- Thay thế bài kiểm tra integration và deployment smoke test.

Đây là **ràng buộc rất hữu ích ở bước compile**, không phải giấy chứng nhận tương thích end-to-end.

### 3.3. Những release nào được hỗ trợ?

Mỗi `javac` chỉ hỗ trợ release hiện tại và **một tập hữu hạn những release cũ hơn**. Đừng mặc định một JDK rất mới vẫn cho phép `--release 10` mãi mãi, hoặc một compiler cũ có thể chọn release mới hơn nó.

Để xem chính xác compiler đang sử dụng và supported values:

~~~bash
javac -version
javac --help
~~~

Nếu nhận lỗi `release version 10 not supported`, lý do là **compiler được dùng không hỗ trợ release đó**; không có nghĩa mọi khái niệm Java 10 đã bị xóa khỏi Java. Hãy chọn **một toolchain/compiler hỗ trợ release mục tiêu** hoặc điều chỉnh mức tương thích theo chính sách sản phẩm.

## 4. Java 10: cú pháp var và API String.strip từ Java 11

### 4.1. Đặt hai khái niệm cạnh nhau

Xét chương trình:

~~~java
public class SourceApiMismatchDemo {
    public static void main(String[] args) {
        var input = "  Java  ";
        System.out.println(input.strip());
    }
}
~~~

`var` được giới thiệu từ Java 10 cho **local-variable type inference**. Đây không phải kiểu runtime `var`; compiler suy luận `String`.

`String.strip()` chỉ được đưa vào **Java 11**. Nó không thể được gọi trên `java.lang.String` của Java 10.

Trên **JDK 17** (hoặc compiler mới hơn vẫn chấp nhận Java 10 source/target), câu lệnh:

~~~bash
javac --source 10 --target 10 -d out-mismatch SourceApiMismatchDemo.java
~~~

có thể **biên dịch thành công** vì:

1. Cú pháp `var` hợp lệ ở source level 10.
2. Compiler tạo class-file Java 10 (major 54).
3. Compiler chạy trên JDK 17 vẫn có thể thấy `String.strip()` trong **platform API hiện tại** vì không có ràng buộc `--release 10`.
4. Compile success không tự nghĩa runtime Java 10 có phương thức ấy.

`javac` có thể in cảnh báo về hệ thống module/target platform khi dùng `--source`/`--target`. Tên và số lượng warnings phụ thuộc JDK; không dùng warning text làm stdout chuẩn.

### 4.2. --release 10 giúp bắt lỗi sớm

Với **JDK 17 javac**, có thể chạy:

~~~bash
javac --release 10 -d out10 SourceApiMismatchDemo.java
~~~

Kết quả mong đợi: **biên dịch thất bại** vì `String.strip()` **không nằm trong API Java 10**. Thông báo compiler thường nói không tìm thấy method `strip()` tương ứng; nội dung diagnostic cụ thể thay đổi giữa bản JDK và locale, nên **không coi bất kỳ bản ghi lỗi nguyên văn là output bất biến**.

Điều này minh họa tác dụng thiết thực của `--release`: **ngăn accidental use của API ra đời sau release mục tiêu ngay trong lúc biên dịch**.

Lưu ý: chỉ chạy được `--release 10` khi `javac --help` xác nhận compiler hỗ trợ 10. Ví dụ này sử dụng JDK 17 để việc luyện tập có phạm vi rõ, không yêu cầu duy trì Java 10 runtime ngoài thực tế.

### 4.3. Chạy trên JVM hiện đại thì sao?

Nếu biên dịch mã với JDK 17 mà dùng Java 17 runtime:

~~~bash
java -cp out-mismatch SourceApiMismatchDemo
~~~

thì `String.strip()` **có** tồn tại, nên chương trình in:

~~~text
Java
~~~

Nhưng nếu mang class-file major 54 ấy sang JVM Java 10, việc gọi `String.strip()` có thể gây:

~~~text
java.lang.NoSuchMethodError: ... java.lang.String.strip()
~~~

Đây là **ví dụ dạng lỗi**, không bảo đảm toàn bộ message/stack trace giống nhau trên mọi HotSpot.

Lỗi này minh họa một artifact **có class-file tương thích nhưng thiếu API runtime**. JVM vẫn có thể tải class, nhưng sẽ thất bại ở điểm thực sự cần resolve phương thức không tồn tại.

### 4.4. Từ hai mục tiêu riêng đến một cấu hình duy nhất

~~~text
JDK 17 compiler
    |
    +-- --source 10 --target 10
    |      Language grammar: Java 10
    |      Class-file format: Java 10
    |      Platform API: có thể vẫn là JDK 17
    |      => String.strip() có thể lọt qua compile
    |
    +-- --release 10
           Language grammar: Java 10
           Class-file format: Java 10
           Platform API: Java 10
           => String.strip() bị từ chối khi compile
~~~

Đây là sự phân biệt quan trọng nhất của chủ đề, áp dụng tương tự khi xây bằng JDK 25 nhưng target JDK 17, miễn compiler hỗ trợ `--release 17`.

## 5. Ví dụ Java 17+ chạy được: cú pháp Java 10 và API Java 11

Lưu tệp **`SourceApiMismatchDemo.java`**:

~~~java
import java.util.List;

public class SourceApiMismatchDemo {

    public static void main(String[] args) {
        // var là cú pháp nguồn từ Java 10.
        var raw = "  Java  ";

        // List.of là API Java 9, đã có ở Java 10.
        var languages = List.of("Java", "Kotlin");

        // strip chỉ xuất hiện từ API Java 11.
        String cleaned = raw.strip();

        System.out.println("normalized=" + cleaned);
        System.out.println("count=" + languages.size());
        System.out.println("first=" + languages.get(0));
        System.out.println("languageFeature=var");
        System.out.println("apiFeature=String.strip");
    }
}
~~~

**Biên dịch bằng JDK 17 hoặc mới hơn có hỗ trợ release 17:**

~~~bash
javac --release 17 -encoding UTF-8 -d out17 SourceApiMismatchDemo.java
java -cp out17 SourceApiMismatchDemo
~~~

**Stdout chính xác:**

~~~text
normalized=Java
count=2
first=Java
languageFeature=var
apiFeature=String.strip
~~~

### 5.1. Vì sao chạy ổn trên JDK 17?

- `var raw` suy luận `String` theo cú pháp Java 10+.
- `List.of(...)` là API đã có từ Java 9; nó trả danh sách với hai phần tử.
- `String.strip()` có từ Java 11 và vẫn được Java 17 hỗ trợ.
- `--release 17` cho phép cả các đặc tính trên.
- Chương trình không phụ thuộc environment, clock, file system hoặc network nên stdout ổn định.

### 5.2. Bây giờ thử biên dịch cho Java 10

Trên **JDK 17**, thử:

~~~bash
javac --release 10 -d out10 SourceApiMismatchDemo.java
~~~

Lệnh **phải thất bại ở bước compile** vì `strip()` không tồn tại trong platform API Java 10, mặc dù `var` và `List.of` hợp lệ theo release này.

So sánh với lệnh chỉ dùng source/target:

~~~bash
javac --source 10 --target 10 -d out-unsafe SourceApiMismatchDemo.java
~~~

Ở JDK 17, lệnh này **có thể thành công** và tạo class-file Java 10. Đừng đọc **compile success** là “đã kiểm API Java 10”; compile đang nhìn API JDK 17.

**Không chạy Java 10 production chỉ để quan sát lỗi này.** Nếu dự án thật cần một runtime được hỗ trợ, hãy chọn target như Java 17/21/25 và áp dụng cùng kỹ thuật kiểm tra bằng `--release`.

### 5.3. Sửa lỗi để code thật sự tương thích Java 10

Thay:

~~~java
String cleaned = raw.strip();
~~~

bằng:

~~~java
String cleaned = raw.trim();
~~~

`String.trim()` đã tồn tại từ trước Java 10. Tuy nhiên, `trim` và `strip` **không hoàn toàn tương đương về quy tắc whitespace Unicode**. Chỉ thay khi behavior đó đáp ứng yêu cầu sản phẩm.

Đây là điểm rất quan trọng trong migration: sửa một lỗi **API availability** không được vô tình thay đổi semantics của ứng dụng.

## 6. Ví dụ thứ hai: --release 10 cho mã chỉ dùng API Java 10

Chương trình tiếp theo dùng:

- `var`: ngôn ngữ Java 10.
- `List.of`: API Java 9.
- `String.join`: API từ trước Java 10.
- Không dùng `String.strip` hay API ra đời sau Java 10.

Lưu file **`PortableJava10Demo.java`**:

~~~java
import java.util.List;
import java.util.Locale;

public class PortableJava10Demo {

    public static void main(String[] args) {
        var names = List.of("Ada", "Lin");

        System.out.println(
                "names=" + String.join(",", names));
        System.out.println("count=" + names.size());
        System.out.println("firstUpper="
                + names.get(0).toUpperCase(Locale.ROOT));
    }
}
~~~

Biên dịch trên **JDK 17 javac**:

~~~bash
javac --release 10 -encoding UTF-8 -d out10 PortableJava10Demo.java
java -cp out10 PortableJava10Demo
~~~

**Stdout chính xác trên Java 17+:**

~~~text
names=Ada,Lin
count=2
firstUpper=ADA
~~~

### 6.1. Điều gì được kiểm tra?

`--release 10` đảm bảo compiler chỉ chấp nhận cú pháp Java 10 và những Java platform APIs phù hợp release 10, đồng thời tạo class-file target Java 10.

Chương trình có thể được chạy trên Java 17 vì runtime mới hỗ trợ các cú pháp đã được compiler chuyển thành bytecode và các API cũ đang dùng.

Tuy nhiên, việc chạy Java 17 **không thay thế** test trên Java 10 nếu ứng dụng có yêu cầu tương thích Java 10 thực tế. Java 10 không còn là lựa chọn runtime production được duy trì phổ biến; đối với hệ thống mới, nên chọn một JDK release còn hỗ trợ theo chính sách của tổ chức.

### 6.2. Tại sao dùng Locale.ROOT?

`String.toUpperCase(Locale.ROOT)` cho phép ví dụ có output ổn định, tránh sự khác biệt uppercase giữa các locale như Turkish. Đây là chi tiết nhỏ nhưng hữu ích khi đưa **stdout chính xác** vào tài liệu học hoặc CI tests.

### 6.3. Xem class-file version

Dùng `javap` của JDK:

~~~bash
javap -verbose out10/PortableJava10Demo.class
~~~

Trong phần thông tin class-file, có thể thấy:

~~~text
major version: 54
~~~

Đây là major version của Java 10. Lưu ý các dòng còn lại của `javap -verbose` thay đổi theo compiler và môi trường; không cần so toàn bộ output.

Với một file được biên dịch thành công bằng `--release 17`, class-file major sẽ là **61**. Chỉ đọc major version **không cho phép** biết chắc các platform APIs được tham chiếu đã được giới hạn đúng mức.

## 7. Ví dụ API mới không cần cú pháp mới

Không có từ khóa `var` thì vẫn có thể mắc lỗi tương tự.

~~~java
import java.nio.file.Files;
import java.nio.file.Path;

public class SimpleApiGap {
    public static void main(String[] args)
            throws Exception {
        String data = Files.readString(
                Path.of("notes.txt"));
        System.out.println(data.length());
    }
}
~~~

Trong ví dụ:

- Cú pháp class/method/try/exception là cú pháp quen thuộc.
- `Files.readString` và `Path.of` là APIs của **Java 11**.
- Nếu chọn source/target 8 hoặc 10 trên một JDK hiện đại mà **không khóa platform APIs**, mã có thể compile dù runtime cũ không có các phương thức đó.
- `javac --release 10` sẽ từ chối những APIs Java 11 trên compiler hỗ trợ release 10.

Đây là **mã minh họa không độc lập với dữ liệu môi trường**, vì cần tệp `notes.txt` tồn tại. Không đưa ra stdout chính xác cho đoạn đó; ví dụ runnable hoàn chỉnh ở mục 5 và 6 không cần file.

### 7.1. Những lỗi runtime thường xảy ra

| Triệu chứng | Điều có thể đã sai | Ví dụ |
| --- | --- | --- |
| `UnsupportedClassVersionError` | Class-file major mới hơn khả năng JVM | Class Java 17 chạy Java 11 |
| `NoSuchMethodError` | Bytecode gọi method không có trong runtime đã tải | `String.strip` trên Java 10 |
| `NoClassDefFoundError` | Không tìm được class cần thiết khi link/load | Thiếu dependency runtime |
| `ClassNotFoundException` | Tìm class bằng cơ chế reflective loader không có | `Class.forName` với class thiếu |
| `IllegalAccessError` | Vấn đề kiểm soát truy cập/linkage | Package/module visibility thay đổi |
| `NoSuchFieldError` | Binary signature/field không khớp | Compile bằng dependency mới, runtime library cũ |

Không phải tất cả những lỗi trên đều do `--source`/`--target`; dependencies, JAR shadowing, module path, class loaders và package relocation cũng có thể là nguyên nhân. Phân tích đúng lỗi và classpath trước khi chỉnh compiler flags.

## 8. Vì sao --release kiểm cả platform API?

### 8.1. Bối cảnh JEP 247

**JEP 247 — Compile for Older Platform Versions** đưa `--release` vào `javac` từ Java 9. Trước đó, việc cross-compile với `-source`/`-target` cần cấu hình platform classes thích hợp, nếu không compiler có thể vô tình dùng API mới.

`--release` cung cấp compiler một **góc nhìn các API public, documented** mà release mục tiêu có, ngoài việc chọn language grammar và class-file version.

Khi chọn:

~~~bash
javac --release 17 -d build/classes MyProgram.java
~~~

compiler sẽ từ chối lời gọi Java platform APIs chỉ xuất hiện sau Java 17. Điều này đặc biệt hữu ích khi **CI đang dùng JDK 25** nhưng sản phẩm vẫn phải chạy trên **JDK 17**.

### 8.2. Không phải chỉ là bytecode rewriting

`--release` không biến lời gọi API mới thành implementation tương đương ở JVM cũ. Nếu `String.strip` chưa tồn tại trên Java 10, `--release 10` **bắt lỗi**, không tự sinh một phiên bản Java 10 của `strip`.

Cách sửa là:

- Dùng API đã tồn tại ở release mục tiêu và bảo đảm semantics đúng.
- Tự viết implementation thay thế có kiểm thử.
- Chọn dependency hỗ trợ release đó.
- Nâng **runtime baseline** theo kế hoạch nếu cần tính năng mới.

### 8.3. Module system và API exports

Từ Java 9, Java Platform Module System phân chia các APIs thành modules với exports rõ ràng.

Khi dùng `--release` cho một release hỗ trợ modules, compiler cũng giới hạn tập Java SE/JDK APIs theo exports của release đó. Theo Oracle `javac` docs, không thể dùng `--add-exports` để **mở rộng** các package thuộc Java SE/JDK/system modules vốn bị đóng trong platform API view của release đích.

**Không dùng internal API như `sun.*` hoặc `com.sun.tools.javac.*` như một cách lách kiểm tra** để tạo ứng dụng “Java 10 compatible”. API nội bộ có thể thay đổi và không được bảo đảm bởi Java SE contract.

### 8.4. Không dùng --release cùng --source/--target

Các lệnh sau **không hợp lệ**:

~~~bash
javac --release 17 --source 17 MyProgram.java
javac --release 17 --target 17 MyProgram.java
~~~

Theo `javac` documentation, `--release` không được dùng đồng thời với `--source` hoặc `--target`. Một option đã bao gồm cả hai trách nhiệm và kiểm API, nên không cần lặp.

### 8.5. Preview language features

`--enable-preview` được dùng khi cố ý phát triển với một preview feature của JDK hỗ trợ. Các giới hạn source/release của preview phụ thuộc compiler hiện hành; thông thường preview phải áp dụng cho **release của compiler đang dùng**, không phải một bản release cũ tùy ý.

Không dùng `--enable-preview` như mẹo lách `--release 17` để đưa API Java 25 vào một artifact Java 17. Những tính năng preview cũng có yêu cầu runtime flag và rủi ro thay đổi qua các bản phát hành.

## 9. API Java nền tảng khác dependency bên thứ ba

`--release 17` giới hạn APIs của **Java SE/JDK platform**. Nó không bảo đảm mọi dependency trên `--class-path` hoặc `--module-path` tương thích Java 17.

Ví dụ mô hình:

~~~text
App:
  --release 17
  compiles to class-file major 61

Dependency util.jar:
  được biên dịch bằng Java 21
  có class-file major 65

Runtime:
  Java 17

App class có thể được JVM đọc,
nhưng khi cần load một class từ util.jar có major 65,
runtime Java 17 có thể báo UnsupportedClassVersionError.
~~~

Một dependency cũng có thể được biên dịch với bytecode 17 nhưng **gọi API chỉ có trên Java 21** nếu nhà sản xuất JAR đã build sai tương tự.

### 9.1. Phải kiểm toàn bộ dependency graph

- Chọn versions của dependencies có công bố **minimum supported Java version** phù hợp.
- Kiểm transitive dependencies và các code-generation plugins.
- Để CI resolve dependencies từ repository có lock/version control phù hợp.
- Kiểm module/classpath ở runtime giống cấu hình release.
- Chạy integration tests trên runtime **thấp nhất** mà ứng dụng công bố hỗ trợ.
- Nếu làm fat JAR hoặc shaded JAR, kiểm classes được đóng gói có major version hợp lệ và dependencies không bị thay nhầm phiên bản.

Compiler không có khả năng tự chứng minh mọi phép reflective call, dynamic proxy, service loader hoặc native code đều chạy trên JDK target.

### 9.2. API của library có lifecycle khác Java SE API

Một thư viện có thể khai báo API `Client.send()` giống nhau trên nhiều versions nhưng implementation phụ thuộc API JDK mới. Việc source của bạn chỉ dùng `Client.send()` không đảm bảo JAR hiện tại thực sự chạy trên JDK thấp nhất được hỗ trợ.

Vì vậy có **hai bài toán tách biệt**:

1. Ràng buộc Java SE platform API bằng `--release`.
2. Ràng buộc dependencies và behavior bằng dependency metadata, CI tests, static checks khi cần.

### 9.3. Reflection có thể vượt khả năng kiểm tĩnh của --release

~~~java
Class<?> type = Class.forName(
        "some.optional.platform.ClassName");
~~~

Tên class là string; compiler không tự giải nghĩa mọi giá trị runtime. `--release` không phải bộ phân tích full reflection graph. Code phải kiểm runtime feature availability hoặc dùng abstraction phù hợp khi có optional features.

**Không dùng reflection để lách kiểm tra release một cách mù quáng**. Việc chương trình chạy trên release nào phải được test trên JVM đó.

## 10. Cấu hình Maven để phân biệt language/API đúng

Với Maven Compiler Plugin hiện đại, tài liệu Apache Maven khuyến nghị dùng property `maven.compiler.release` hoặc cấu hình `release` phù hợp cho Maven 3; Maven 4 có thêm cơ chế khai báo source target version trong cấu trúc `sources`, tùy phiên bản plugin.

Một phần cấu hình **Maven 3 POM**:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>platform-api-check</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.16.0</version>
                <configuration>
                    <release>17</release>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

**Ý nghĩa:** Maven chạy `javac` với target release 17, dùng source grammar, bytecode và Java platform APIs Java 17. Cấu hình không tự chỉ định Maven sẽ chạy bằng JDK 17: Maven có thể đang chạy dưới JDK 21/25 hoặc dùng toolchain riêng.

Với dự án thực, luôn pin phiên bản Maven Compiler Plugin phù hợp môi trường/CI và kiểm cấu hình effective POM. Ví dụ trên là một POM tối thiểu để minh họa compiler settings, không liệt kê test plugins, dependencies hay application packaging.

### 10.1. Chỉ đặt source và target trong Maven chưa đủ

Ví dụ:

~~~xml
<properties>
    <maven.compiler.source>17</maven.compiler.source>
    <maven.compiler.target>17</maven.compiler.target>
</properties>
~~~

Nó diễn đạt cú pháp/bytecode, **không tự ràng buộc Java platform APIs** khi build với JDK mới. Vì thế nên ưu tiên `maven.compiler.release` khi muốn đảm bảo API target.

### 10.2. Maven Toolchains khác release

Maven Toolchains chọn một **JDK cụ thể để chạy compiler/tools**, còn `release` chọn **source+bytecode+platform API view** của artifact.

Ví dụ:

~~~text
Build toolchain: JDK 21
maven.compiler.release: 17

Compiler thực thi bằng JDK 21
Source grammar: Java 17
Class-file: Java 17
Java platform API: Java 17
~~~

Cả hai cơ chế có thể bổ sung cho nhau. Toolchain kiểm soát môi trường compiler; `release` bảo vệ compatibility target của artifact.

### 10.3. Maven 4 có khai báo sources/targetVersion

Apache Maven Compiler Plugin 4.x docs giới thiệu dạng:

~~~xml
<sources>
    <source>
        <targetVersion>17</targetVersion>
    </source>
</sources>
~~~

Cú pháp này cần đúng **Maven 4 và phiên bản compiler plugin 4.x**. Không tự áp vào POM Maven 3 nếu chưa nâng build stack. Nếu project dùng Maven 3, property `maven.compiler.release` là lựa chọn rõ ràng, còn được hỗ trợ.

## 11. Cấu hình Gradle: toolchain và options.release làm hai việc khác nhau

Gradle có **Java toolchains**, `sourceCompatibility`, `targetCompatibility` và `JavaCompile.options.release`. Theo Gradle documentation hiện hành, để cross-compile an toàn, nên **kết hợp toolchain và release** thay vì chỉ gán source/target.

Ví dụ **build.gradle.kts**:

~~~kotlin
plugins {
    java
}

java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(21))
    }
}

tasks.withType<JavaCompile>().configureEach {
    options.release.set(17)
}
~~~

Ý nghĩa:

- Toolchain yêu cầu **compiler JDK 21**.
- `options.release = 17` yêu cầu biên dịch theo Java 17 language rules, class-file target 17 và **Java 17 platform APIs**.
- Project vẫn cần dependencies phù hợp và test Java 17 runtime.

Đoạn cấu hình này dùng **Gradle Kotlin DSL** hiện hành. Cách Gradle tìm/tải JDK toolchain có thể cần cấu hình repositories, môi trường CI và quyền truy cập thích hợp; không mặc định tự download thành công trên mọi máy.

### 11.1. sourceCompatibility không thay thế release

~~~kotlin
java {
    sourceCompatibility = JavaVersion.VERSION_17
    targetCompatibility = JavaVersion.VERSION_17
}
~~~

Hai giá trị đó tương ứng với `-source` và `-target`. Chúng **không khóa API nền tảng** như `options.release`. Nếu sử dụng compiler JDK 21, project có thể lỡ gọi một API Java 21 mà runtime 17 không có.

### 11.2. Gradle toolchain không tự hạ platform API

Nếu chỉ đặt toolchain JDK 21 mà không đặt release, thường các tác vụ compile sẽ dùng mức source/target theo toolchain JDK 21 hoặc cấu hình mặc định hiện hữu. **Không** suy rằng toolchain tự hiểu app phải hỗ trợ Java 17.

Hai câu hỏi cần được viết riêng trong build policy:

~~~text
JDK nào dùng để chạy compiler? => toolchain
App phải chạy từ Java nào?      => options.release
~~~

### 11.3. Gradle source/target vẫn có công dụng?

Có, trong những trường hợp đặc thù hoặc các dự án cũ. Nhưng khi có `options.release`, đây thường là ràng buộc **rõ và an toàn hơn** cho cross-compilation. Không cần pha trộn cấu hình gây mâu thuẫn; hãy chọn một baseline Java release được kiểm soát.

## 12. Kiểm chứng artifact và runtime sau compile

### 12.1. Kiểm bản JDK đang chạy thực sự

Các lệnh:

~~~bash
java -version
javac -version
javac --help
~~~

Hãy chạy cả trên máy phát triển **và CI**. Có tình huống `java` trỏ JDK 17 nhưng `javac` trỏ JDK 21 do PATH/JAVA_HOME khác nhau. Một lần build local thành công không chứng minh pipeline production dùng cùng compiler.

### 12.2. Kiểm class-file version

~~~bash
javap -verbose out17/SourceApiMismatchDemo.class
~~~

Tìm dòng:

~~~text
major version: 61
~~~

Chỉ có nghĩa class-file có format Java 17. Không đủ kết luận API compatibility: bạn cần kiểm compile đã dùng `--release 17` hoặc đúng runtime API và có tests.

### 12.3. Kiểm dependencies

- Chạy dependency tree của Maven/Gradle để phát hiện JAR bất ngờ.
- Đọc minimum Java runtime được maintainer công bố.
- Kiểm classfile versions của các classes đóng gói (có thể dùng `javap`/build checks).
- Đặc biệt lưu ý libraries dùng reflection, native code hoặc bytecode generation.
- Nếu code build thành **multi-release JAR**, kiểm các entries `META-INF/versions/` không tải vào runtime sai.

### 12.4. Kiểm chạy trên release tối thiểu

Nếu sản phẩm công bố hỗ trợ Java 17, CI nên có một job **chạy tests bằng JDK 17 thật**. Sau đó có thể thêm các phiên bản JDK mới mà tổ chức hỗ trợ.

Một chiến lược:

~~~text
Compile JDK 21 / --release 17
  |
  +-- Unit tests on JDK 17  [minimum runtime]
  +-- Integration tests on JDK 17
  +-- Tests on JDK 21      [newer supported runtime]
  +-- Security/dependency checks
  +-- Deployment smoke test
~~~

Điều này phát hiện nhiều lỗi mà compiler không thể dự báo: libraries không tương thích, module access, reflective calls, OS-dependent code, behavior khác nhau và launcher configuration.

### 12.5. Khi chạy thất bại, phân loại nguyên nhân trước khi sửa

Nếu thấy `UnsupportedClassVersionError`, kiểm class-file major và runtime version trước; không vội viết lại source.

Nếu thấy `NoSuchMethodError`, kiểm:

1. Method thuộc Java platform hay thư viện bên thứ ba?
2. Code đã compile bằng JDK nào và flags gì?
3. Runtime thực tế load class/method từ đâu?
4. Có dependency version khác giữa build/run không?
5. Có reflection/class loader/plugin che khuất class đúng không?

Chỉ khi đã xác định **API nền tảng mới hơn runtime** mới quy trực tiếp cho việc không ràng buộc `--release` đúng mức.

## 13. Annotation processing, code generation và các ranh giới khác

### 13.1. Annotation processor chạy ở build JDK

Annotation processors có thể chạy bằng compiler/JDK mới dù app target runtime cũ. Hai thứ cần kiểm riêng:

- **Processor tool:** có tương thích compiler/build JDK không?
- **Generated source/classes:** có tuân theo `--release` của artifact mục tiêu không?

`--release` kiểm code do `javac` biên dịch trong compilation đang cấu hình, nhưng không tự đảm bảo mọi tool thứ ba tạo bytecode bên ngoài compiler có target đúng. Nếu framework sinh classes runtime bằng ASM/Byte Buddy, cần kiểm target class-file và API dependency.

### 13.2. Mã generated có API mới hơn

Một annotation processor có thể sinh:

~~~java
// Java 17 code vẫn dùng API đúng Java 17.
String hex = java.util.HexFormat
        .of().toHexDigits(255);
~~~

`HexFormat` có từ Java 17, nên nếu target Java 11 thì `--release 11` phải từ chối generated source tham chiếu `HexFormat`. Dự án cần chọn generator phù hợp hoặc nâng runtime baseline.

### 13.3. JNI và native libraries

`--release` không đảm bảo version hệ thống của thư viện C/C++, ABI hay architecture phù hợp. Nếu ứng dụng gọi JNI, vẫn cần kiểm đúng OS, libc, CPU architecture và native resources.

### 13.4. Module path và classpath

`--release` khóa **platform API view**, nhưng classpath/module path còn có libraries riêng. Một module có thể yêu cầu version Java cao hơn target; compiler flags không tự chuyển những modules thành tương thích.

Khi dùng Java modules, tránh áp dụng `--add-exports` để vượt quyền truy cập vào internal JDK APIs; đặc biệt với `--release` nhắm JDK 9+ còn có những hạn chế được `javac` kiểm soát.

## 14. Những giới hạn dễ quên của --release

| Điều --release kiểm soát | Điều không kiểm soát |
| --- | --- |
| Java grammar của release mục tiêu | Dữ liệu config/runtime environment |
| Class-file target version | OS architecture và native libraries |
| APIs thuộc Java SE/JDK platform được compiler cho phép | Mọi API bên thứ ba và transitive JAR |
| Platform modules/exports phù hợp compile view | Reflection/dynamic loading không thể phân tích hết |
| Lỗi API mới hơn target trong source được compile | Runtime behavior của API trên mọi vendor |
| Phát hiện nguồn không tương thích tại compile time | Business logic correctness |
| Ngăn một số cách dùng API nội bộ | Security vulnerabilities trong dependencies |
| Giúp reproducible compatibility policy | Chạy test trên runtime tối thiểu |

### 14.1. --release không cài đặt Java runtime đích

Lệnh:

~~~bash
javac --release 17 MyProgram.java
~~~

không tạo một JDK 17 bên trong JAR, không cài JRE và không đổi `java -version`. Deployment vẫn phải có JVM phù hợp.

### 14.2. --release không bảo đảm Java API bất biến về behavior

Một method tồn tại từ Java 8 có thể vẫn có những thay đổi implementation/behavior được tài liệu hóa hoặc liên quan OS, timezone, locale và security policy. Compile chỉ xác nhận method/type hợp lệ theo API model, không chứng minh business behavior.

### 14.3. --release có thể không hoạt động với target quá cũ

Mỗi bản compiler có danh sách release được hỗ trợ. Khi quá cũ, bạn có thể cần một toolchain phù hợp hoặc nâng baseline. Đừng tìm cách bỏ `--release` chỉ để hết lỗi rồi tuyên bố artifact tương thích.

### 14.4. --release và internal API

`--release` chỉ cung cấp documented public supported platform API. Không đảm bảo code đang phụ thuộc một internal package hoặc JDK implementation detail sẽ vẫn compile. Lỗi này thường là **tín hiệu cần sửa phụ thuộc API nội bộ**, không phải lý do để tắt mọi kiểm soát.

## 15. Hướng dẫn migration source/target sang release

### Bước 1 — Ghi nhận các phiên bản hiện có

- Build đang chạy bằng JDK nào (JDK 17, 21, 25...)?
- `--source` và `--target` đang được đặt ở đâu (CLI/Maven/Gradle/IDE)?
- Runtime tối thiểu được sản phẩm cam kết là bản nào?
- Có multi-release JAR hoặc nhiều modules với target khác nhau?
- Dependencies có yêu cầu JDK mới hơn không?

### Bước 2 — Chọn minimum supported Java runtime

Ví dụ hệ thống chấp nhận Java 17 trở lên. Đó phải là quyết định dựa trên chính sách bảo trì, dependency support và production environment, không chỉ do developer đang có JDK 25.

### Bước 3 — Đổi compiler settings sang --release

CLI:

~~~bash
javac --release 17 -d out17 MyProgram.java
~~~

Maven 3:

~~~xml
<properties>
    <maven.compiler.release>17</maven.compiler.release>
</properties>
~~~

Gradle Kotlin DSL:

~~~kotlin
tasks.withType<JavaCompile>().configureEach {
    options.release.set(17)
}
~~~

Chọn compiler/toolchain **có hỗ trợ** release 17; với build phức tạp, xác nhận effective compiler arguments.

### Bước 4 — Sửa accidental API usage

Nếu code lỡ gọi `String.formatted` (Java 15) khi target Java 11, `--release 11` sẽ bắt lỗi. Lúc đó:

- Thay bằng `String.format` nếu semantics phù hợp.
- Hoặc nâng runtime baseline nếu cần feature mới.
- Hoặc giữ API compat qua abstraction và nhiều artifacts có version rõ.

**Không** đổi trở lại `--source 11 --target 11` chỉ để một lời gọi mới hơn 11 lọt compile rồi fail khi deploy.

### Bước 5 — Test runtime tối thiểu và cập nhật CI

Chạy unit/integration/smoke tests trên JDK mục tiêu thật. Đặc biệt kiểm các modules được tải động, dependencies và native libraries.

### Bước 6 — Kiểm release policy định kỳ

Khi nâng compiler JDK, danh sách supported `--release` values có thể thay đổi. Kiểm `javac --help` trên CI. Đồng thời rà lại dependency minimum JDK requirements và support windows, tránh trường hợp build thành công nhưng runtime baseline đã không còn được tổ chức hoặc vendor hỗ trợ.

## 16. Những lỗi hiểu nhầm phổ biến

| Nhận định sai | Sự thật | Cách giải quyết |
| --- | --- | --- |
| “--source 10 nghĩa chỉ dùng API Java 10.” | Chỉ giới hạn language grammar | Dùng `--release 10` trên compiler hỗ trợ |
| “--target 10 bảo đảm chạy mọi app trên Java 10.” | Chỉ class-file format | Khóa API và test runtime |
| “--release chỉ là source+target viết gọn.” | Nó còn khóa platform API | Ưu tiên `--release` |
| “Mã chỉ dùng cú pháp cũ luôn chạy trên Java cũ.” | Có thể gọi API mới | So API release của từng method |
| “Có bytecode major 54 là đủ chạy Java 10.” | API/dependency có thể thiếu | Cross-compile đúng release |
| “JDK 25 compiler đương nhiên hỗ trợ mọi release trước.” | Có tập hữu hạn | Xem `javac --help` |
| “Lỗi NoSuchMethodError luôn do Java SE.” | Có thể do dependency version mismatch | Kiểm classpath/runtime |
| “Toolchain 21 tự ràng buộc API 17.” | Toolchain chọn JDK, không tự đặt release 17 | Cấu hình release riêng |
| “Maven source/target đủ chặn API mới.” | Không khóa platform API | `maven.compiler.release` |
| “Gradle targetCompatibility đảm bảo API cũ.” | Không | `options.release` |
| “Release 17 hạ dependency Java 21 xuống 17.” | JAR third-party vẫn như cũ | Chọn dependency compatible |
| “Release 17 cài JRE 17 vào artifact.” | Không | Deployment chọn runtime |
| “Preview giúp đưa API mới về JVM cũ.” | Không phải backporting | Dùng supported APIs |
| “--release và --source dùng cùng nhau được.” | Không | Chỉ dùng release |
| “Java 10 var là một kiểu Object.” | var chỉ là local type inference tại compile | Đọc kiểu được suy luận |
| “List.of là API Java 10 mới thêm.” | List.of từ Java 9 | Đọc Javadoc since field |
| “String.strip có từ Java 10.” | Có từ Java 11 | Sửa API hoặc nâng target |
| “JVM mới hơn lúc chạy luôn tương thích mọi lib.” | Behavior/modules/dependencies có thể đổi | Test matrix |
| “Compiler success đủ chứng nhận vận hành.” | Compile không kiểm production environment | Integration/smoke tests |

## 17. Checklist code review và CI

### Developer

- [ ] Xác định Java runtime tối thiểu sản phẩm hỗ trợ.
- [ ] Phân biệt source grammar, class-file target và platform API.
- [ ] Dùng `javac --release` khi build với JDK mới cho runtime cũ.
- [ ] Không giả định `--source` tự giới hạn Java platform APIs.
- [ ] Không nghĩ `--target` sẽ hạ dependencies.
- [ ] Kiểm API `@since` trong Javadoc khi nghi method quá mới.
- [ ] Không dùng unsupported internal APIs để lách module exports.
- [ ] Kiểm annotation processors và generated code.
- [ ] Không dùng Java preview features cho baseline khác.
- [ ] Có unit tests cho thay đổi API tương đương về behavior.

### Build/CI

- [ ] Pin build JDK/toolchain vendor/build khi cần reproducibility.
- [ ] Chạy `javac --help` để kiểm release supported của compiler đó.
- [ ] Khai báo `maven.compiler.release` hoặc Gradle `options.release`.
- [ ] Không để source/target và release mâu thuẫn.
- [ ] Build/test dùng dependency versions được kiểm soát.
- [ ] Test trên minimum supported runtime thật.
- [ ] Kiểm class-file version của JARs (đặc biệt transitive/fat JAR).
- [ ] Kiểm runtime modules, classpath và native dependencies.
- [ ] Tránh compile với JDK mới rồi deploy trên JDK cũ mà không test.
- [ ] Ghi rõ policy khi thay đổi minimum Java version.

### Câu hỏi tự kiểm tra

**Câu 1.** `javac --source 17` giới hạn những gì?

**Đáp án:** Cú pháp Java source theo ngôn ngữ Java 17; không tự khóa mọi Java platform APIs của compiler về đúng Java 17.

**Câu 2.** `javac --target 17` làm gì?

**Đáp án:** Chọn class-file format tương thích Java 17, không chứng minh method/class dùng có ở Java 17.

**Câu 3.** `javac --release 17` thêm điều gì so với source/target?

**Đáp án:** Ràng buộc tập Java SE/JDK platform APIs được phép dùng theo release 17.

**Câu 4.** Vì sao `var` và `String.strip` cho ví dụ Java 10?

**Đáp án:** `var` là cú pháp Java 10; `String.strip` là API Java 11, nên code có thể đúng cú pháp nhưng sai API target Java 10.

**Câu 5.** Với JDK 17 javac, `--source 10 --target 10` có thể biên dịch mã gọi `String.strip` không?

**Đáp án:** Có thể, vì compiler nhìn API mới hơn mà không bị khóa theo Java 10.

**Câu 6.** Vì sao `--release 10` có thể từ chối chính mã đó?

**Đáp án:** Java 10 platform API không có method `String.strip()`.

**Câu 7.** Class-file major 54 có bảo đảm artifact chạy Java 10?

**Đáp án:** Không. Nó chỉ nói class-file encoding phù hợp; API/dependency có thể không có.

**Câu 8.** `--release 17` có kiểm JAR third-party đã biên dịch bằng Java 21 không?

**Đáp án:** Không tự bảo đảm toàn bộ dependency graph; phải kiểm JAR versions và runtime tests.

**Câu 9.** Gradle toolchain JDK 21 và `options.release=17` có mâu thuẫn không?

**Đáp án:** Không. Toolchain quyết định compiler JDK; release quyết định artifact target Java 17.

**Câu 10.** Maven `maven.compiler.source=17` có thay `maven.compiler.release=17` không?

**Đáp án:** Không. Property source giới hạn cú pháp, còn release bao gồm platform APIs.

**Câu 11.** Tại sao một JDK mới có thể không hỗ trợ `--release 10`?

**Đáp án:** Compiler chỉ hỗ trợ current và một số previous releases, cần xem `javac --help`.

**Câu 12.** Để tuyên bố hỗ trợ Java 17, cần bước nào ngoài compile?

**Đáp án:** Chạy test thật trên JDK 17, kiểm dependencies/modules/native code và deployment configuration.

## 18. Tài liệu chính thức và nguồn còn áp dụng

- [Oracle Java SE 26 — The javac Command](https://docs.oracle.com/en/java/javase/26/docs/specs/man/javac.html): hợp đồng hiện đại của `--source`, `--target`, `--release`; giới hạn API và cross-compilation.
- [Oracle Java SE 25 — The javac Command](https://docs.oracle.com/en/java/javase/25/docs/specs/man/javac.html): chi tiết các options và supported releases.
- [Oracle Java SE 17 — The javac Command](https://docs.oracle.com/en/java/javase/17/docs/specs/man/javac.html): ví dụ áp dụng với JDK 17, nhất là so source/target và release 10.
- [OpenJDK JEP 247 — Compile for Older Platform Versions](https://openjdk.org/jeps/247): nguồn gốc và mục tiêu ràng buộc platform API với `--release`.
- [OpenJDK JEP 286 — Local-Variable Type Inference](https://openjdk.org/jeps/286): `var` được giới thiệu ở Java 10.
- [Oracle Java SE 17 — String.strip()](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/String.html#strip()): phương thức có `@since 11`.
- [Oracle Java SE 17 — List.of()](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/List.html#of()): API có từ Java 9.
- [Apache Maven — Guide to Targeting a Java Version](https://maven.apache.org/guides/mini/guide-java-target.html): `maven.compiler.release` và giới hạn `source`/`target`.
- [Apache Maven Compiler Plugin 4.x — Setting the --release of the Java Compiler](https://maven.apache.org/plugins/maven-compiler-plugin-4.x/examples/set-compiler-release.html): phân biệt Maven 3 và Maven 4 configuration.
- [Gradle — Toolchains for JVM Projects](https://docs.gradle.org/current/userguide/toolchains.html): toolchain vs `options.release` vs source/target compatibility.
- [Gradle — Building Java & JVM Projects](https://docs.gradle.org/current/userguide/building_java_projects.html): các phương án chọn Java version và ý nghĩa API compatibility.
- [Oracle Java SE 17 — javap](https://docs.oracle.com/en/java/javase/17/docs/specs/man/javap.html): xác định class-file major version.
- [Java Virtual Machine Specification — Class File Format](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-4.html): `major_version`, `minor_version` và điều kiện JVM tải classes.

**Ghi nhớ:** `--source` điều khiển **ngôn ngữ nguồn**, `--target` điều khiển **class-file format**, còn `--release` điều khiển **cả hai cùng với Java platform APIs**. Chương trình chỉ dùng cú pháp Java 10 vẫn có thể vô tình gọi API Java 11 rồi lỗi khi chạy trên Java 10 nếu build thiếu ràng buộc API. Khi xây một ứng dụng cho JVM cũ hơn compiler, **ưu tiên `--release`, xác nhận compiler hỗ trợ target, kiểm dependencies và chạy tests trên runtime tối thiểu thật**.