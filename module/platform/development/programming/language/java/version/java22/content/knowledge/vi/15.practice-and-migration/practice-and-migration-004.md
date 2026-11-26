# Chọn --release phù hợp và hiểu giới hạn khi gọi API chỉ có ở JDK mới

## 1. Bài toán thực tế

Một nhóm dùng JDK 25 để build nhưng còn phải cung cấp artifact chạy trong môi trường Java 22. Trên máy lập trình, IDE gợi ý một phương thức mới và chương trình chạy bình thường. Khi triển khai, chương trình lại lỗi vì runtime không có phương thức đó.

Để tránh tình huống này, cần phân biệt **JDK chạy compiler**, **mức Java đích của mã được biên dịch** và **runtime thực thi artifact**. Tên phiên bản trong thư mục bài học không thay thế được hợp đồng tương thích của ứng dụng.

Trong chương Vận dụng và nâng cấp của module Java 22, bài này tập trung vào cách giữ hợp đồng đó bằng `--release`. Các ví dụ dùng JDK 25 làm compiler và Java 22 làm mốc tương thích minh họa; mã đích chỉ sử dụng tính năng chính thức.

Sau bài học, người học có thể:

- Chọn `--release` từ runtime tối thiểu cần hỗ trợ.
- Nhận biết một thay đổi thuộc cú pháp, API hay định dạng class file.
- Giải thích vì sao `-source` và `-target` đơn lẻ chưa bảo vệ đầy đủ việc gọi API.
- Xử lý trường hợp API mong muốn xuất hiện sau mức đích.
- Kiểm tra thêm dependency, generated code, test JVM và artifact triển khai.

Kiến thức cần có: biên dịch/chạy Java, classpath, JAR và khái niệm dependency.

## 2. Ba mức phiên bản cần ghi rõ

Giả sử hợp đồng của một dịch vụ là “artifact phải chạy được trên Java 22 và được kiểm chứng thêm trên Java 25”.

| Mức phiên bản | Ví dụ | Câu hỏi cần trả lời |
|---|---|---|
| JDK chạy `javac` | JDK 25 | Compiler nào thực sự được gọi? |
| Release đích | `--release 22` | Source, API nền tảng và class file bị giới hạn ở mức nào? |
| Runtime của ứng dụng | Java 22 hoặc Java 25 | JVM nào nạp artifact đã build? |

Một cấu hình hợp lý có thể là:

~~~text
JDK 25 chạy javac
       |
       | --release 22
       v
Artifact dùng cú pháp/API nền tảng thuộc mức Java 22
       |
       +--> kiểm thử trên runtime Java 22
       +--> kiểm thử trên runtime Java 25
~~~

Việc compiler chạy bằng JDK 25 không bắt buộc artifact phải nhắm Java 25. Ngược lại, một thuộc tính “Java 22” trong IDE chưa chứng minh lệnh build thực tế đã đặt release đúng.

Với Maven hoặc Gradle, JVM chạy công cụ build còn có thể khác JDK compiler được toolchain chọn. Vì vậy, nhật ký build nên thể hiện cả toolchain biên dịch và JVM chạy test, thay vì chỉ in `java -version` của terminal.

## 3. --release ràng buộc những gì?

Với một mức `R` được compiler hỗ trợ, `javac --release R` áp dụng đồng thời:

| Thành phần | Ý nghĩa đối với mã được biên dịch |
|---|---|
| Quy tắc ngôn ngữ | Chỉ chấp nhận cú pháp thuộc mức đích |
| API nền tảng | Phân giải theo API Java SE/JDK được hỗ trợ của mức đích |
| Class file đầu ra | Sinh class file nhắm mức phiên bản tương ứng |

`--release` không được kết hợp với `-source` hoặc `-target` trong cùng lời gọi. Compiler chỉ hỗ trợ release hiện tại và một tập hữu hạn release trước đó; xem `javac --help` của compiler đang dùng. [Đặc tả tùy chọn javac](https://docs.oracle.com/en/java/javase/25/docs/specs/man/javac.html#standard-options).

Ví dụ biên dịch thông thường:

~~~shell
javac --release 22 -encoding UTF-8 -d out Main.java
~~~

Cách hiểu đúng của lệnh:

- `javac` vẫn là compiler đã được chọn bởi đường dẫn hoặc toolchain.
- `22` là hợp đồng biên dịch của source đầu vào.
- `out` là nơi nhận class file.
- Tùy chọn này không cài runtime Java 22 và không tự chạy chương trình bằng runtime đó.

Đặc biệt, `--release` không chép implementation của API JDK mới vào artifact. Nếu một phương thức chỉ xuất hiện ở Java 24 thì đặt `--release 22` không tạo ra phương thức tương đương cho runtime Java 22.

Một compiler JDK 22 cũng không thể được biến thành compiler Java 25 bằng `--release 25`. Khi cần một mức đích mới hơn, phải chọn compiler hỗ trợ mức đó.

## 4. Chọn release từ hợp đồng triển khai

### 4.1. Quy trình lựa chọn

Thực hiện theo thứ tự:

1. Liệt kê các runtime mà sản phẩm cam kết hỗ trợ.
2. Xác định runtime thấp nhất trong tập đó.
3. Kiểm tra tính năng ngôn ngữ và API cần dùng có phù hợp với mức này hay không.
4. Chọn compiler có hỗ trợ release đích.
5. Biên dịch và kiểm chứng artifact trên runtime tối thiểu.

Ví dụ quyết định:

| Hợp đồng của sản phẩm | Release thường chọn | Hệ quả |
|---|---|---|
| Thư viện dùng chung phải chạy trên Java 21 trở lên | `21` | Phần cơ sở không dùng tính năng chỉ chính thức từ Java 22 |
| Dịch vụ cần giữ khả năng chạy trên Java 22 | `22` | API bổ sung sau Java 22 chưa được gọi trực tiếp trong phần mã này |
| Dịch vụ chuyển toàn bộ runtime sang Java 25 | `25` | Có thể dùng API chính thức Java 25 sau khi kiểm tra dependency |
| Một thư viện có phần cơ sở cho Java 22 và phần tối ưu cho Java mới | Release riêng cho từng phần | Cần thiết kế đóng gói/chọn implementation rõ ràng |

Đây là các lựa chọn theo hợp đồng giả định, không phải quy tắc “module Java 22 thì mọi dự án phải dùng release 22”.

Trong giai đoạn triển khai cuốn chiếu, nếu cùng một artifact vẫn phải chạy trên cả runtime thấp và cao, mức thấp vẫn là ràng buộc. Chỉ nâng release sau khi việc thay đổi phạm vi hỗ trợ đã được quyết định và kiểm chứng.

### 4.2. Tính năng ngôn ngữ cũng có mức tối thiểu

Unnamed variables là tính năng chính thức từ Java 22. [Các thay đổi ngôn ngữ theo release](https://docs.oracle.com/en/java/javase/25/language/java-language-changes-release.html).

Ví dụ `PortParser.java`:

~~~java
public class PortParser {
    static int parse(String text) {
        try {
            return Integer.parseInt(text);
        } catch (NumberFormatException _) {
            return -1;
        }
    }

    public static void main(String[] args) {
        System.out.println(parse("8080"));
        System.out.println(parse("invalid"));
    }
}
~~~

Với JDK 25, lệnh sau biên dịch theo cú pháp chính thức Java 22:

~~~shell
javac --release 22 -d out22 PortParser.java
java -cp out22 PortParser
~~~

Kết quả mong đợi:

~~~text
8080
-1
~~~

Nếu chuyển lệnh thành `--release 21`, ví dụ trên không còn thuộc cú pháp chính thức của mức đích. Khi sản phẩm phải giữ nền Java 21, có thể đổi biến exception thành một tên thông thường như `ignored`. Không dùng compiler mới để bật lại preview của Java 21 nhằm né hợp đồng biên dịch.

Điểm cần phân biệt: một đoạn mã không gọi API mới vẫn có thể không phù hợp với release thấp hơn vì cú pháp đã thay đổi.

## 5. Ví dụ: lớp đã có, phương thức mới chưa có

### 5.1. Kiểm tra Since của đúng phương thức

`java.io.Reader` đã tồn tại từ lâu, nhưng phương thức `Reader.of(CharSequence)` chỉ có từ Java 24. `Reader.readAllAsString()` có từ Java 25. Vì vậy, tìm thấy tên lớp trong tài liệu Java 22 chưa đủ để kết luận mọi phương thức của lớp đều dùng được ở mức đó. [Reader.of](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/io/Reader.html#of(java.lang.CharSequence)), [Reader.readAllAsString](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/io/Reader.html#readAllAsString()).

Khi kiểm tra một API, xác định đủ:

- Tên lớp và package.
- Tên phương thức.
- Kiểu tham số và kiểu trả về, nhất là khi có overload.
- Mốc `Since` và trạng thái chính thức/preview của declaration đó.

### 5.2. Mã dùng Reader.of

Lưu ví dụ thành `ReaderDemo.java`:

~~~java
import java.io.IOException;
import java.io.Reader;

public class ReaderDemo {
    static Reader open(String text) {
        return Reader.of(text);
    }

    public static void main(String[] args) throws IOException {
        try (Reader reader = open("Java")) {
            System.out.println((char) reader.read());
        }
    }
}
~~~

Dùng compiler JDK 25 và nhắm Java 25:

~~~shell
javac --release 25 -d out25 ReaderDemo.java
java -cp out25 ReaderDemo
~~~

Khi lệnh `java` là runtime Java 25, kết quả mong đợi là:

~~~text
J
~~~

Giữ nguyên source và đổi mức đích:

~~~shell
javac --release 22 -d out22 ReaderDemo.java
~~~

Lệnh này phải bị từ chối ở lời gọi `Reader.of` vì API Java 22 không có phương thức đó. Lỗi thường thuộc nhóm `cannot find symbol`; hình thức thông báo cụ thể phụ thuộc compiler.

Trong tình huống này, compiler đang phát hiện một vi phạm hợp đồng sớm. Việc ví dụ chạy được trên máy JDK 25 chỉ chứng minh đường chạy đó phù hợp với runtime 25.

## 6. Vì sao hạ bytecode đơn lẻ chưa đủ?

### 6.1. Cấu hình dễ làm lọt API mới

Chỉ để tái hiện lỗi cấu hình, dùng JDK 25 biên dịch `ReaderDemo.java` như sau:

~~~shell
javac -source 22 -target 22 -d out-unsafe ReaderDemo.java
~~~

Nếu không chỉ định bộ platform classes phù hợp, compiler vẫn có thể phân giải `Reader.of` từ JDK đang dùng. Class file đầu ra có thể mang mức Java 22 nhưng còn tham chiếu đến phương thức không tồn tại trên runtime Java 22.

Đây là lý do nên dùng `--release` cho hợp đồng cross-compilation thông thường. [Hướng dẫn Maven về targeting Java](https://maven.apache.org/guides/mini/guide-java-target.html), [quy tắc cross-compilation của javac](https://docs.oracle.com/en/java/javase/25/docs/specs/man/javac.html#compiling-for-earlier-releases-of-the-platform).

Nếu class này được chạy trên Java 22 và thực thi lời gọi `Reader.of`, lỗi cần phân biệt là `NoSuchMethodError`: lớp được tìm thấy nhưng phương thức mà bytecode yêu cầu không có trong định nghĩa lớp tại runtime. [Đặc tả NoSuchMethodError](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/NoSuchMethodError.html).

### 6.2. Phân biệt với class file quá mới

Nếu biên dịch bằng `--release 25` rồi chạy artifact đó trên Java 22, JVM có thể từ chối ngay khi nạp class vì phiên bản class file quá mới. Đây là nhóm `UnsupportedClassVersionError`. [Đặc tả UnsupportedClassVersionError](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/UnsupportedClassVersionError.html).

| Tình huống | Vấn đề |
|---|---|
| Class file Java 25 được nạp trên Java 22 | Runtime không hỗ trợ định dạng phiên bản đó |
| Class file Java 22 còn gọi `Reader.of` khi chạy Java 22 | Runtime không có phương thức được tham chiếu |
| Source gọi `Reader.of` và được compile bằng `--release 22` | Compiler chặn việc dùng API ngoài mức đích |

Việc giải quyết đúng một lớp lỗi chưa chứng minh lớp lỗi còn lại đã được xử lý.

### 6.3. Điều kiện kiểm tra phiên bản không thay đổi tập API compile

Đoạn sau vẫn không biên dịch với `--release 22`:

~~~java
import java.io.Reader;
import java.io.StringReader;

class ReaderFactory {
    static Reader open(String text) {
        if (Runtime.version().feature() >= 24) {
            return Reader.of(text);
        }
        return new StringReader(text);
    }
}
~~~

`if` là logic lựa chọn ở runtime. Compiler vẫn phải phân giải lời gọi `Reader.of` trong source theo API đích.

Đừng xem một nhánh điều kiện là cơ chế miễn kiểm tra API. Nếu cần hai implementation theo phiên bản, phải tổ chức chúng bằng một thiết kế có ranh giới biên dịch và nạp lớp phù hợp.

## 7. Xử lý khi API mong muốn mới hơn release đích

### 7.1. Nâng nền runtime khi sản phẩm cho phép

Nếu ứng dụng đã chuyển sang Java 25 và không còn cam kết chạy ở mức thấp hơn, có thể nâng release đích theo quyết định đó.

Các thay đổi cần đi cùng nhau gồm toolchain, release, runtime của test, runtime triển khai và yêu cầu của dependency. Một thay đổi riêng trong IDE không hoàn tất việc nâng nền.

Với ví dụ `ReaderDemo`, chọn release 25 là hợp lý khi hợp đồng runtime đã chuyển sang Java 25. Không nâng release chỉ để làm mất thông báo lỗi rồi để artifact chạy trên runtime cũ.

### 7.2. Giữ nền và chọn implementation phù hợp

Nếu đầu vào của ví dụ là một `String`, có thể sửa phương thức `open`:

~~~java
import java.io.Reader;
import java.io.StringReader;

class ReaderFactory {
    static Reader open(String text) {
        return new StringReader(text);
    }
}
~~~

`StringReader` là API vẫn áp dụng trong Java hiện đại và cung cấp reader đọc từ chuỗi. [Đặc tả StringReader](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/io/StringReader.html).

Đây là thay đổi implementation cho nhu cầu cụ thể “đọc nội dung của một String”. Nếu nhu cầu thực tế là đọc một `CharSequence` có thể thay đổi, cần xem lại hợp đồng dữ liệu; không mặc định rằng việc gọi `toString()` để chụp nội dung có cùng hành vi với mọi cách đọc nguồn ban đầu.

Khi thay API, nên so sánh hành vi ở mức yêu cầu: dữ liệu đọc được, xử lý lỗi, hiệu năng cần thiết và quyền sở hữu tài nguyên. Tuổi đời của một API không tự quyết định nó còn phù hợp hay không.

### 7.3. Tách implementation khi thật sự cần hỗ trợ nhiều nền

Một cấu trúc ứng dụng có thể là:

~~~text
text-core
  interface dùng kiểu dữ liệu thuộc nền chung
  implementation đáp ứng runtime tối thiểu

text-modern
  implementation gọi API JDK mới
  artifact nhắm runtime mới

application
  chọn artifact/implementation theo cấu hình triển khai
~~~

Phần cơ sở phải tránh làm lộ các kiểu chỉ có ở JDK mới trong chữ ký mà runtime thấp cần nạp. Việc tách tên module hoặc package chưa đủ nếu artifact mới vẫn bị nạp trên môi trường không phù hợp.

Với thư viện, multi-release JAR là một cơ chế chuyên biệt: phần cơ sở nằm ở gốc JAR, các biến thể nằm trong `META-INF/versions/N` và manifest có `Multi-Release: true`. Runtime chọn biến thể theo quy tắc của định dạng JAR. [Đặc tả multi-release JAR](https://docs.oracle.com/en/java/javase/25/docs/specs/jar/jar.html#multi-release-jar-files).

Cơ chế này cần quy trình build và kiểm chứng cho từng biến thể. Nó không cho phép toàn bộ source cơ sở gọi tùy ý API mới dưới một cấu hình `--release` thấp.

Reflection hoặc method handle cũng không tạo ra API trên runtime chưa có API đó. Nếu một thiết kế dùng việc dò capability, nó vẫn phải có fallback đúng, ranh giới nạp lớp rõ ràng và xử lý các lỗi tra cứu/gọi phương thức. Chỉ cân nhắc sau khi đã xác định lợi ích so với việc dùng implementation thuộc nền chung.

## 8. Giới hạn quan trọng: dependency đã biên dịch sẵn

### 8.1. --release không biên dịch lại JAR trên classpath

Xét artifact có cấu trúc:

~~~text
Application.class       nhắm Java 22
        |
        +--> library.jar
                Library.class nhắm Java 25
~~~

Dù source ứng dụng dùng `--release 22`, JAR dependency không tự được hạ xuống Java 22. Compiler JDK mới có thể đọc class file của thư viện và biên dịch source gọi một phương thức của thư viện đó; việc này chưa chứng minh runtime Java 22 nạp được dependency.

Một trường hợp khác:

~~~text
Application.class       nhắm Java 22
        |
        +--> library.jar
                Class file đủ thấp
                nhưng implementation gọi API nền tảng mới hơn
~~~

Kiểm tra major version của dependency không phát hiện hết trường hợp thứ hai. Vì vậy, đánh giá dependency cần cả mức runtime công bố và kiểm chứng đường chạy thực tế.

`--release` kiểm soát source đang biên dịch với API nền tảng đích; nó không phải công cụ chứng nhận toàn bộ đồ thị dependency.

### 8.2. Những thành phần dễ bị bỏ sót

| Thành phần | Việc cần xác nhận |
|---|---|
| Dependency trực tiếp | Runtime tối thiểu được nhà phát hành hỗ trợ |
| Dependency bắc cầu | Phiên bản thực tế được resolve khi build |
| Plugin hoặc provider nạp động | Runtime thấp có nạp được và thực thi được không |
| Generated source | Có được biên dịch với cùng release của phần sản phẩm không |
| Bytecode được sinh bởi công cụ khác | Có tuân thủ mức đích và API nền tảng không |
| Native library hoặc runtime image tùy biến | Có đáp ứng môi trường triển khai cần thiết không |

Annotation processor chạy trong môi trường runtime của compiler, còn source mà nó sinh ra được phân tích trong môi trường biên dịch. Hai môi trường này có thể khác mức Java. [Phân biệt môi trường biên dịch và runtime của javac](https://docs.oracle.com/en/java/javase/25/docs/specs/man/javac.html#compilation-environment-and-runtime-environment).

Ví dụ, processor chạy được trên JDK 25 không làm artifact tự yêu cầu Java 25. Tuy nhiên, generated source dùng API chỉ có ở Java 25 vẫn phải bị xem xét theo release của phần sản phẩm.

## 9. Đặt cấu hình trong build

### 9.1. Maven

Với Maven Compiler Plugin hỗ trợ thuộc tính release, đoạn cấu hình trong `pom.xml` có thể là:

~~~xml
<properties>
    <maven.compiler.release>22</maven.compiler.release>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
</properties>
~~~

Đây là lựa chọn mức đích cho compilation, không phải lựa chọn JDK sẽ chạy Maven hoặc test. Toolchain và cấu hình test runtime cần được xác định riêng.

Tài liệu Maven mô tả cả thuộc tính `maven.compiler.release` lẫn tham số `release` của Compiler Plugin. [Hướng dẫn chọn Java đích trong Maven](https://maven.apache.org/guides/mini/guide-java-target.html).

Trong dự án nhiều module, kiểm tra cấu hình hiệu lực của từng module và các lần gọi compiler tùy biến. Tránh để một profile vô tình đổi mức đích khi build artifact phát hành.

### 9.2. Gradle Kotlin DSL

Ví dụ `build.gradle.kts` dưới đây chọn JDK 25 để compile, release 22 cho các tác vụ `JavaCompile` và Java 22 để chạy các tác vụ `Test`:

~~~kotlin
plugins {
    java
}

java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(25))
    }
}

tasks.withType<JavaCompile>().configureEach {
    options.release.set(22)
}

tasks.withType<Test>().configureEach {
    javaLauncher.set(javaToolchains.launcherFor {
        languageVersion.set(JavaLanguageVersion.of(22))
    })
}
~~~

Toolchain chọn bộ công cụ, `options.release` đặt hợp đồng biên dịch, còn `javaLauncher` chọn JVM chạy test. Phiên bản Gradle và các JDK được cài/cấp phát phải hỗ trợ cấu hình đã chọn. [Tài liệu Gradle về toolchain, release và launcher](https://docs.gradle.org/current/userguide/toolchains.html).

Ví dụ cấu hình tất cả tác vụ `Test` về runtime tối thiểu. Nếu cần kiểm chứng thêm runtime Java 25, tạo tác vụ hoặc job CI riêng dùng đúng cùng artifact sản phẩm. Các tác vụ `JavaExec` hoặc tác vụ plugin khác cũng cần được kiểm tra theo cách chúng chọn JVM.

### 9.3. IDE và CI cần đọc cùng hợp đồng

Một quy trình làm việc nên thống nhất:

- IDE nhập cấu hình build đã được quản lý trong dự án.
- Build phát hành ghi nhận compiler thực tế và release hiệu lực.
- Test trên runtime tối thiểu dùng artifact được build theo cấu hình đó.
- Image hoặc máy chủ triển khai chọn runtime theo hợp đồng đã công bố.

Không lấy việc nút Run trong IDE chạy thành công làm bằng chứng duy nhất cho tính tương thích của artifact.

## 10. Preview không phải lối vượt qua mức đích

Bài sử dụng các tính năng chính thức để giữ phạm vi kiến thức áp dụng lâu dài. Tuy vậy, khi nâng cấp mã Java 22, cần nhận diện được ràng buộc preview còn tồn tại trong build.

Với `javac`, bật preview gắn với release hiện tại của compiler; không dùng JDK 25 cùng `--release 22 --enable-preview` để biên dịch lại preview Java 22. Mã đã dùng preview cần được chuyển sang tính năng/API chính thức tương ứng hoặc xử lý trong một kế hoạch nâng cấp riêng.

Ở runtime, class file được đánh dấu phụ thuộc preview của một release không được xem như class file chính thức có thể tự do chuyển sang mọi release cao hơn. Các class file này gắn với đúng release mà chúng phụ thuộc. [Ràng buộc preview trong JVM Specification](https://docs.oracle.com/javase/specs/jvms/se25/html/jvms-1.html#jvms-1.5.1).

Ví dụ áp dụng vào module:

| Tình huống | Cách đánh giá |
|---|---|
| Dùng unnamed variables chính thức Java 22 | Compile ở mức 22 trở lên mà không cần preview cho tính năng này |
| Dùng API ScopedValue chính thức Java 25 | Phần mã đó phải có nền thích hợp với API chính thức Java 25 |
| Có source preview được viết cho Java 22 | Đánh giá việc chuyển mã; không chỉ thêm cờ vào compiler mới |
| Dự án không còn tính năng preview nào | Rà lại cấu hình compile, test và launch để bỏ phụ thuộc cờ không cần thiết |

`ScopedValue` trong API Java 25 được ghi nhận từ phiên bản 25 và không mang trạng thái preview. Điều đó không đưa API chính thức này vào tập API chuẩn của release 22. [ScopedValue Java 25](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/ScopedValue.html).

## 11. Kiểm chứng và chẩn đoán

### 11.1. Xác nhận compiler và runtime thực tế

Trong môi trường thực hành, bắt đầu bằng:

~~~shell
javac -version
java -version
javac --help
~~~

Các lệnh này chỉ cho biết executable được gọi tại thời điểm đó. Khi dự án dùng toolchain, tiếp tục đối chiếu log của build và JVM chạy test.

Để chạy rõ ràng bằng một runtime khác trong PowerShell, có thể dùng đường dẫn đầy đủ. Đường dẫn sau là ví dụ cần thay bằng nơi cài thực tế:

~~~powershell
& 'C:\Java\jdk-22\bin\java.exe' -cp out22 PortParser
~~~

Lệnh `java --release 22 ...` không phải cách buộc launcher chuyển sang runtime Java 22. Muốn thực thi bằng runtime đó, phải chọn đúng executable hoặc launcher/toolchain.

### 11.2. Xem class file bằng javap

Với ví dụ `PortParser` đã được compile:

~~~shell
javap -verbose -classpath out22 PortParser
~~~

`javap` cho phép xem thông tin bổ sung của class và bytecode. [Tài liệu javap](https://docs.oracle.com/en/java/javase/25/docs/specs/man/javap.html).

Các mốc major version hữu ích trong phạm vi bài:

| Java đích | Major version |
|---|---|
| 21 | `65` |
| 22 | `66` |
| 24 | `68` |
| 25 | `69` |

Các số này mô tả phiên bản class file; class file chính thức thông thường ở các mức này có minor version `0`. Class file phụ thuộc preview có quy tắc riêng. [JVM Specification về phiên bản](https://docs.oracle.com/javase/specs/jvms/se25/html/jvms-1.html#jvms-1.2), [cấu trúc class file](https://docs.oracle.com/javase/specs/jvms/se25/html/jvms-4.html#jvms-4.1).

Sau khi thấy major version đúng, vẫn cần kiểm tra runtime và dependency. Một con số đúng chưa chứng minh mọi lời gọi API đều tồn tại.

### 11.3. Dùng jdeps đúng phạm vi

Ví dụ với một JAR ứng dụng thông thường, không phải multi-release JAR:

~~~shell
jdeps --recursive --summary app.jar
~~~

Công cụ giúp xem dependency ở mức package/class và các module liên quan. [Tài liệu jdeps](https://docs.oracle.com/en/java/javase/25/docs/specs/man/jdeps.html).

Không diễn giải kết quả đó thành một chứng nhận rằng mọi phương thức được gọi đều đã tồn tại ở Java 22. Đặc biệt, `--multi-release 22` của `jdeps` dùng để chọn cách xử lý biến thể trong multi-release JAR; nó không tương đương `javac --release 22`.

### 11.4. Đọc lỗi theo giai đoạn

| Dấu hiệu | Điều cần kiểm tra trước |
|---|---|
| `release version ... not supported` | Compiler thực tế và danh sách release mà nó hỗ trợ |
| Lỗi cú pháp khi compile | Tính năng ngôn ngữ đã chính thức ở release đích chưa |
| `cannot find symbol` với phương thức JDK | Declaration, overload và mốc `Since` của API |
| `UnsupportedClassVersionError` | Class gây lỗi, major/minor version và runtime đang nạp nó |
| `NoSuchMethodError` | Định nghĩa lớp được nạp ở runtime có đúng phương thức không |
| `ClassNotFoundException` hoặc `NoClassDefFoundError` | Classpath/module path, dependency và nguyên nhân gốc trong chuỗi lỗi |
| Build qua trên JDK mới nhưng thất bại khi triển khai | Artifact thực tế, dependency được đóng gói và runtime của môi trường đích |

`NoClassDefFoundError` còn có thể liên quan đến lỗi khởi tạo lớp; luôn đọc chuỗi `Caused by` thay vì kết luận ngay là “chỉ thiếu file JAR”.

Với lỗi runtime, cần xác định tên class thực sự gây lỗi. Nó có thể thuộc một dependency được nạp muộn, không phải class chứa `main`.

## 12. Một quy trình nghiệm thu phù hợp

Giả sử nhóm chọn hợp đồng “compile bằng JDK 25, nền Java 22, kiểm chứng trên Java 22 và Java 25”. Quy trình nên tạo ra bằng chứng sau:

| Bước | Bằng chứng cần có |
|---|---|
| Ghi rõ mức hỗ trợ | Tài liệu dự án xác định runtime tối thiểu và runtime được kiểm chứng |
| Chọn compiler | Log thể hiện toolchain JDK 25 |
| Đặt release | Lệnh/configuration hiệu lực có `--release 22` |
| Kiểm tra source | Source và generated source không dùng cú pháp/API vượt mức đích |
| Kiểm tra dependency | Artifact được resolve và đóng gói phù hợp nền đã công bố |
| Kiểm chứng runtime tối thiểu | Test và các đường tích hợp quan trọng chạy trên Java 22 |
| Kiểm chứng runtime cao hơn | Cùng artifact được chạy trên Java 25 |
| Kiểm tra bản đóng gói | JAR/image phát hành chứa đúng class và dependency đã kiểm chứng |

Đối với thay đổi bổ sung một API mới, bản mô tả thay đổi nên ghi rõ API đó có từ phiên bản nào và lựa chọn tương thích là nâng nền, dùng implementation thuộc nền hiện có hay tách phần triển khai.

Mục tiêu của việc chọn `--release` là biến hợp đồng runtime thành một ràng buộc có thể kiểm tra trong quá trình build. Phần còn lại của hợp đồng được chứng minh bằng dependency phù hợp và việc thực thi artifact trên các môi trường đã cam kết.
