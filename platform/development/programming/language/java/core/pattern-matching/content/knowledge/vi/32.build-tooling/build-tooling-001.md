# Cấu hình sourceCompatibility cho Java Pattern Matching

**Ngữ cảnh:** Java Core Pattern Matching — Build và tooling. Bài hướng dẫn thiết lập phiên bản ngôn ngữ cho những cú pháp pattern khác nhau, tập trung vào **Gradle** (Groovy DSL và Kotlin DSL), đồng thời đối chiếu với Maven và cách chạy trực tiếp bằng JDK. Ví dụ chính sử dụng **Java 21 trở lên**, vì record patterns (JEP 440) và pattern matching for switch (JEP 441) được chuẩn hóa ở Java 21.

## 1. sourceCompatibility giải quyết vấn đề gì?

Trong dự án Gradle Java, **sourceCompatibility** cho biết **mức phiên bản ngôn ngữ Java được phép dùng khi biên dịch mã nguồn**. Ví dụ, khi đặt sourceCompatibility là Java 17, trình biên dịch kiểm tra mã như nguồn Java 17; các cú pháp chính thức chỉ xuất hiện ở Java 21 sẽ không được chấp nhận.

Một lỗi thường thấy:

~~~java
// Minh họa Java 21; không biên dịch ở mức source Java 17.
return switch (value) {
    case Point(int x, int y) -> x + y;
    case null -> 0;
    default -> -1;
};
~~~

Đoạn này dùng **record pattern trong case**. Nếu dự án đặt sourceCompatibility ở 17, việc cài JDK 21 trên máy không tự động cho phép cú pháp này: cấu hình mức source vẫn yêu cầu Java 17.

Cần phân biệt ba câu hỏi riêng:

1. **Source level:** Trình biên dịch được phép hiểu cú pháp phiên bản nào? Liên quan sourceCompatibility hoặc tham số javac **--source**.
2. **JDK thực sự biên dịch:** Dùng trình biên dịch javac phiên bản nào? Liên quan **Java toolchain** hoặc JDK mà Gradle dùng.
3. **Khả năng chạy và API được phép dùng:** Bytecode có thể chạy trên JVM tối thiểu nào, và mã nguồn được phép gọi API JDK của phiên bản nào? Liên quan **--release**, targetCompatibility và môi trường runtime.

**Chỉ sửa sourceCompatibility chưa đủ.** Nếu sourceCompatibility là 21 nhưng Gradle vẫn chọn javac từ JDK 17, trình biên dịch cũ sẽ không hiểu mức nguồn 21. Ngược lại, javac 24 có thể biên dịch nguồn Java 17 nhưng điều đó không tự động bảo đảm mã chỉ gọi API của Java 17 nếu không ràng buộc đúng bằng --release.

## 2. Pattern nào yêu cầu phiên bản Java nào?

Từ “pattern matching” có thể chỉ nhiều tính năng được chuẩn hóa tại các mốc khác nhau. Hãy chọn phiên bản nguồn theo **cú pháp thực sự sử dụng**, không nâng lên 21 chỉ vì trong tên chủ đề có chữ pattern.

| Tính năng | Ví dụ | Phiên bản chính thức tối thiểu |
| --- | --- | --- |
| Type pattern trong instanceof | **obj instanceof String s** | Java 16 (JEP 394) |
| Record declaration | **record Point(int x, int y) {}** | Java 16 (JEP 395) |
| Sealed class/interface | **sealed interface Shape permits Circle {}** (ví dụ khái niệm; cần subtype hợp lệ) | Java 17 (JEP 409) |
| Switch expression (không nhất thiết có pattern) | **switch (n) { case 1 -> "one"; default -> "other"; }** | Java 14 (JEP 361) |
| Record pattern trong instanceof | **obj instanceof Point(int x, int y)** | Java 21 (JEP 440) |
| Record pattern lồng nhau | **obj instanceof Segment(Point(var x, var y), var end)** | Java 21 (JEP 440) |
| Pattern matching for switch | **case String s -> ...** | Java 21 (JEP 441) |
| Case null và guard when trong pattern switch chuẩn hóa | **case String s when !s.isBlank() -> ...** | Java 21 (JEP 441) |

**Tình huống 1:** Một dự án Java 17 chỉ dùng **instanceof String s** và sealed hierarchy có thể giữ sourceCompatibility 17.

**Tình huống 2:** Dự án muốn dùng **case Point(int x, int y)** hoặc **case String s when ...** trong switch mà không dùng preview phải chọn **source level 21 hoặc mới hơn**, trình biên dịch tương ứng và môi trường chạy phù hợp.

**Lưu ý về các bản Java trước 21:** Một số phiên bản của pattern switch và record patterns từng tồn tại dưới dạng **preview**. Cú pháp, tên guard và quy tắc giữa các bản preview có thay đổi. Với dự án mới, ưu tiên Java 21+ chính thức thay vì cố sao chép code preview của một bản JDK cũ.

## 3. Cách khuyến nghị: Gradle Java toolchain + --release 21

Trong dự án dùng Gradle Java plugin, cách cấu hình đáng tin cậy là:

- **Toolchain 21:** yêu cầu Gradle sử dụng một **JDK 21** để biên dịch Java.
- **Release 21:** yêu cầu javac biên dịch theo **ngôn ngữ, class-file target và tập API nền tảng** của Java 21.
- **Wrapper tương thích:** dùng phiên bản Gradle hỗ trợ JDK 21. Việc Gradle hỗ trợ chạy daemon trên một JDK và hỗ trợ dùng JDK ấy qua toolchain là hai khả năng cần xét riêng.

### 3.1. Gradle Groovy DSL — build.gradle

Đây là cấu hình mẫu cho dự án Java thường:

~~~groovy
plugins {
    id 'java'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}

tasks.withType(JavaCompile).configureEach {
    options.release = 21
    options.encoding = 'UTF-8'
}
~~~

Giải thích:

1. **plugins { id 'java' }** kích hoạt Java plugin, tạo các task như compileJava, compileTestJava và test.
2. **java.toolchain.languageVersion** chọn trình biên dịch thuộc JDK 21 cho các task Java mà Gradle quản lý.
3. **options.release = 21** dùng tính năng javac **--release 21** để giới hạn mức source, bytecode và API JDK có thể tham chiếu.
4. **options.encoding = 'UTF-8'** giúp mã nguồn có tiếng Việt và ký tự Unicode được giải mã nhất quán giữa máy phát triển và CI.

Khi toolchain đã chọn 21 và không có cấu hình khác ghi đè, Gradle thường lấy mức tương thích source/target từ phiên bản toolchain. Cài **options.release** làm yêu cầu biên dịch và API đích minh bạch hơn. Không cần thiết đồng thời khai báo sourceCompatibility/targetCompatibility thêm lần nữa nếu chúng chỉ lặp lại cùng giá trị.

### 3.2. Gradle Kotlin DSL — build.gradle.kts

Cấu hình tương ứng:

~~~kotlin
import org.gradle.api.tasks.compile.JavaCompile

plugins {
    java
}

java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(21))
    }
}

tasks.withType<JavaCompile>().configureEach {
    options.release.set(21)
    options.encoding = "UTF-8"
}
~~~

Hai file trên là **hai lựa chọn DSL cho cùng mục tiêu**, không dùng chung vào một file. Kotlin DSL dùng cú pháp typed như **languageVersion.set(...)** và **options.release.set(...)**; Groovy DSL thường dùng phép gán trực tiếp.

**Tại sao không chỉ đặt sourceCompatibility?** Vì thuộc tính này **không tự cài hoặc chọn JDK 21**. Toolchain giúp tách nhu cầu compiler khỏi JDK dùng để khởi chạy Gradle daemon, phù hợp hơn cho môi trường nhiều máy và CI.

## 4. Cấu hình sourceCompatibility trực tiếp: dùng thế nào cho đúng?

Nếu dự án không dùng toolchain, Gradle vẫn cho phép đặt sourceCompatibility và targetCompatibility. Ví dụ Groovy DSL:

~~~groovy
plugins {
    id 'java'
}

java {
    sourceCompatibility = JavaVersion.VERSION_21
    targetCompatibility = JavaVersion.VERSION_21
}
~~~

Kotlin DSL tương ứng:

~~~kotlin
plugins {
    java
}

java {
    sourceCompatibility = JavaVersion.VERSION_21
    targetCompatibility = JavaVersion.VERSION_21
}
~~~

Cách này **chỉ quy định source/target Java**, không tự bảo đảm task sử dụng đúng JDK 21. Bạn vẫn phải cung cấp một JDK đủ mới làm compiler và bảo đảm Gradle có thể chạy trên môi trường của mình.

**Khi nào phù hợp?** Dự án nhỏ đã chuẩn hóa JDK biên dịch bằng quy trình khác; hoặc cấu hình legacy được quản lý chặt. Tuy nhiên, với project có nhiều máy phát triển, build agents và CI, toolchain thường làm ý định thiết kế rõ hơn.

### Phân biệt targetCompatibility và --release

- **sourceCompatibility:** mức cú pháp Java nguồn.
- **targetCompatibility:** mức class file mà compiler tạo ra.
- **--release N:** yêu cầu javac biên dịch như Java N cả về **cú pháp, class-file target và API Java SE có sẵn trong N**.

Giả sử javac là JDK 24, bạn đặt sourceCompatibility/targetCompatibility bằng 17 nhưng mã gọi API Java 21: chỉ source/target không nhất thiết ngăn mã gọi API mới nếu trình biên dịch thấy API ấy. Mã có thể biên dịch nhưng gặp lỗi liên kết khi chạy trên JDK 17. **--release 17** sẽ giúp phát hiện API không tồn tại trong Java 17 ngay khi biên dịch.

Ngược lại, **--release 21** đòi hỏi javac được dùng có khả năng hỗ trợ release 21. Một JDK 17 không thể biên dịch Java 21 chỉ vì Gradle được cấu hình **options.release = 21**.

**Giữ các giá trị nhất quán.** Tránh cấu hình một nơi sourceCompatibility 17 nhưng nơi khác --release 21, hoặc dùng nhiều plugin cùng ghi đè task compiler. Nên chọn một chính sách rõ ràng, ưu tiên toolchain + release và kiểm tra lệnh compile thực tế.

## 5. Java source level, class-file version và runtime

Một project được biên dịch bằng Java 21 với target/release 21 tạo class file có major version **65**. Trong khi đó, Java 17 sử dụng major version **61**.

Vì vậy:

| Cấu hình biên dịch | Kết quả quan trọng |
| --- | --- |
| JDK 21, --release 21 | Cú pháp/API Java 21, class file chạy trên Java 21+ tương thích |
| JDK 24, --release 21 | Vẫn giới hạn nguồn/API và class file theo Java 21 |
| JDK 17, sourceCompatibility 21 | Không thể biên dịch nguồn Java 21 bằng javac 17 |
| JDK 21, --release 17 | Không được dùng record patterns/switch patterns chính thức Java 21 |
| Build ra class file 65 rồi chạy JDK 17 | Không chạy được; có thể gặp UnsupportedClassVersionError |

Cần phân biệt **JDK biên dịch** và **JRE/JDK chạy ứng dụng**. Toolchain giải quyết phía build, không triển khai JVM runtime lên production. CI/CD, container image và server vẫn phải dùng phiên bản Java tương thích class file.

**Ví dụ:** Dự án dùng **case Point(int x, int y)** nhưng production bắt buộc chạy Java 17. Không thể “giữ cú pháp Java 21 nhưng đặt targetCompatibility 17” như một mẹo để chạy trực tiếp trên JVM 17. Cần dùng cú pháp tương thích Java 17, nâng runtime hoặc tách thành các module có chiến lược tương thích riêng và giao tiếp qua ranh giới phù hợp.

## 6. Ví dụ Java 21 hoàn chỉnh dùng record pattern và switch

Lưu chương trình sau vào **src/main/java/PatternBuildDemo.java** trong project Gradle dùng default package để minh họa tối giản. Trong ứng dụng thật, nên đặt class vào package có tên phù hợp.

~~~java
public class PatternBuildDemo {
    sealed interface Message permits Text, NumberValue {}

    record Text(String value) implements Message {}
    record NumberValue(int value) implements Message {}

    static String display(Message message) {
        return switch (message) {
            case Text(String value) when value != null && !value.isBlank() ->
                    "TEXT: " + value.trim();

            case Text(var value) -> "EMPTY TEXT";

            case NumberValue(int value) -> "NUMBER: " + value;

            case null -> "NULL";
        };
    }

    public static void main(String[] args) {
        System.out.println(display(new Text("  hello  ")));
        System.out.println(display(new Text(" ")));
        System.out.println(display(new Text(null)));
        System.out.println(display(new NumberValue(7)));
        System.out.println(display(null));
    }
}
~~~

### 6.1. Cú pháp pattern được dùng

- **sealed interface Message:** miền biến thể chỉ gồm Text và NumberValue.
- **record Text/NumberValue:** cấu trúc dữ liệu đơn giản và là final.
- **case Text(String value):** record pattern trích component value.
- **when value != null && !value.isBlank():** guard chỉ áp dụng nhánh đầu nếu chuỗi khác null và có nội dung.
- **case Text(var value):** xử lý các Text còn lại, bao gồm value blank hoặc null; không có lỗ hổng khi guard false.
- **case NumberValue(int value):** trích số nguyên từ record NumberValue.
- **case null:** quy định kết quả cho selector null.
- **Không có default:** vì các subtype của sealed Message được bao phủ hoàn toàn, switch expression là exhaustive.

**Tại sao cần source level 21?** Record pattern trong switch cùng guard when là tính năng chính thức ở Java 21. Giảm sourceCompatibility xuống 17 sẽ làm cấu trúc này không còn là nguồn Java 17 hợp lệ, dù record và sealed riêng lẻ có thể dùng ở phiên bản thấp hơn.

### 6.2. Biên dịch và chạy trực tiếp bằng javac

Ở thư mục chứa file **PatternBuildDemo.java**, dùng JDK 21+:

~~~bash
javac --release 21 PatternBuildDemo.java
java PatternBuildDemo
~~~

Kết quả chính xác:

~~~text
TEXT: hello
EMPTY TEXT
EMPTY TEXT
NUMBER: 7
NULL
~~~

Mã đã được kiểm tra với một JDK mới hơn Java 21 bằng cách chạy trực tiếp các định nghĩa tương đương: năm dòng output khớp kết quả trên. Lệnh **--release 21** thể hiện mức biên dịch mục tiêu; khi chạy trong Gradle, cấu hình **options.release = 21** tương ứng với ý nghĩa này.

### 6.3. Build qua Gradle

Với Gradle wrapper sẵn có của dự án:

~~~bash
./gradlew clean compileJava
./gradlew test
~~~

Trên PowerShell Windows, sử dụng wrapper tương ứng:

~~~powershell
.\gradlew.bat clean compileJava
.\gradlew.bat test
~~~

Các lệnh trên **chỉ biên dịch và chạy test**, không tự chạy main(). Có thể chạy class đã biên dịch bằng Java 21+ (nếu sử dụng project và package đơn giản như trên):

~~~bash
java -cp build/classes/java/main PatternBuildDemo
~~~

Hoặc sử dụng **application plugin** rồi cấu hình mainClass để chạy bằng task Gradle run trong project thực tế:

~~~groovy
// Đoạn Gradle Groovy DSL minh họa cho project ứng dụng.
plugins {
    id 'application'
}
application {
    mainClass = 'PatternBuildDemo'
}
~~~

Nếu class có package, mainClass cần tên đầy đủ bao gồm package. Đừng trộn hai khối plugins riêng biệt vào cùng file một cách không kiểm soát; mẫu application chỉ là tùy chọn cho cấu hình project cụ thể.

## 7. Kiểm tra build thực sự dùng Java nào

Một cách kiểm tra lần lượt:

~~~bash
java -version
javac -version
./gradlew --version
./gradlew javaToolchains
./gradlew compileJava --info
~~~

Trên Windows, thay **./gradlew** bằng **.\gradlew.bat**. Tùy cấu hình task và phiên bản Gradle, thông tin chi tiết hiển thị khác nhau, nhưng có thể dùng chúng để kiểm tra:

1. **java -version:** JDK/JRE trên PATH của terminal, chưa chắc là compiler toolchain mà Gradle chọn.
2. **javac -version:** javac mặc định trên PATH, cũng chưa chắc giống compiler toolchain.
3. **gradlew --version:** phiên bản Gradle wrapper, runtime JVM của Gradle.
4. **gradlew javaToolchains:** những Java installations/toolchains Gradle nhận diện.
5. **gradlew compileJava --info:** thông tin build task, compiler, lỗi cấu hình và đôi khi đường dẫn toolchain.

Không đánh đồng output của **java -version** với compiler thực tế của Gradle. Toolchain có thể chọn JDK khác với JDK khởi chạy daemon. Nếu chưa rõ compiler được chọn, hãy đọc thông tin task/Gradle toolchain thay vì suy đoán.

**Gradle wrapper:** Khả năng sử dụng Java 21 qua toolchain và khả năng chạy chính Gradle trên Java 21 phụ thuộc phiên bản Gradle. Một wrapper quá cũ có thể không biết JavaVersion.VERSION_21 hoặc gặp lỗi khi chạy với JDK mới. Kiểm tra bảng tương thích Java của phiên bản Gradle dùng trong dự án và nâng wrapper khi cần, thay vì chỉ sửa sourceCompatibility.

## 8. Lỗi phổ biến khi cấu hình và cách xử lý

| Lỗi hoặc triệu chứng | Nguyên nhân khả dĩ | Hướng xử lý |
| --- | --- | --- |
| **invalid source release: 21** hoặc **release version 21 not supported** | javac được chọn quá cũ để hỗ trợ Java 21 | Kiểm tra JDK compiler/toolchain; dùng JDK 21+ |
| Code **case Type(...)** không biên dịch khi sourceCompatibility là 17 | Cú pháp record/switch pattern thuộc Java 21 | Đặt source/release 21 và dùng compiler đủ mới |
| **Unsupported class file major version 65** khi build với wrapper cũ | Thành phần build/Gradle không đọc được class file Java 21 | Nâng Gradle/plugin tương thích và kiểm tra JVM chạy Gradle |
| **UnsupportedClassVersionError** khi chạy ứng dụng | Runtime JVM cũ hơn class-file target | Dùng runtime phù hợp hoặc biên dịch cho target thấp hơn bằng cú pháp/API tương thích |
| **Java toolchain not found** | Máy/CI thiếu JDK yêu cầu hoặc Gradle không tìm thấy | Cài JDK 21 hoặc cấu hình provisioning/repositories toolchain hợp lệ |
| **preview feature ... not enabled** | Dùng tính năng còn preview của JDK đang chọn hoặc source level khác mong đợi | Xác định đúng tính năng/phiên bản; pattern switch/record patterns đã final từ Java 21 |
| **switch expression does not cover all possible input values** | Case không exhaustive, không phải mặc định lỗi Gradle | Bổ sung case cho subtype/guard còn thiếu, tránh default để che lỗi |
| IDE chạy được nhưng Gradle fail | IDE và Gradle đang dùng JDK, source level hoặc task khác nhau | Đồng bộ Gradle project, xem toolchain/compileJava thay vì chỉ setting IDE |
| Local build được, CI fail | JDK/Gradle wrapper/agent image hoặc environment khác | Cố định wrapper, toolchain, release và runtime trong pipeline |
| Dùng API JDK mới mà project tuyên bố chạy JDK cũ | Chỉ giới hạn source/target, chưa kiểm tra Java API đích | Dùng options.release, compile và test trên runtime mục tiêu |

### 8.1. Lỗi về source level khác lỗi về logic pattern

Ví dụ, một switch expression trên sealed hierarchy không có case cho subtype mới sẽ **không exhaustive**. Ngay cả khi toolchain và release đều là 21, compiler vẫn báo lỗi. Đừng “sửa” lỗi đó bằng đổi Java version hoặc thêm default bừa bãi; cần cập nhật nhánh theo domain.

Tương tự, một nhánh có **when** có thể bỏ sót giá trị khi guard false; thay cấu hình Gradle không biến nhánh ấy thành exhaustive. Cấu hình compiler chỉ kích hoạt cú pháp, còn tính đúng và tính đầy đủ vẫn do code đảm nhiệm.

### 8.2. Preview flags không dùng cho Java 21 final patterns

Với Java 21, **record patterns** và **pattern matching for switch** không cần **--enable-preview**. Tự thêm preview flag cho các ví dụ chuẩn hóa này không tạo lợi ích và có thể khiến quy trình build/test phức tạp hoặc gây nhầm lẫn.

Nếu dự án thật dùng một **tính năng khác** còn preview ở phiên bản JDK cụ thể, đó là một quyết định riêng: compiler và runtime có thể cần bật preview đúng phiên bản, và phải kiểm tra các yêu cầu của tính năng ấy. Không áp dụng mẹo preview Java 17/19/20 một cách máy móc cho source level 21.

## 9. Nhiều module Gradle: tránh lệch source level

Với multi-project Gradle, từng subproject có thể có Java plugin, compiler task và chính sách tương thích khác nhau. Một module được cấu hình source 21 không tự động làm mọi module khác nhận Java 21.

Ví dụ:

- **core-model:** vẫn dùng instanceof type patterns và sealed type của Java 17, yêu cầu chạy trên JDK 17.
- **pattern-app:** dùng record patterns và switch patterns của Java 21, yêu cầu compiler/release 21.
- **integration-tests:** phải chạy trên môi trường có thể tải class từ pattern-app.

Không thể để một module phát hành class file Java 21 rồi kỳ vọng một ứng dụng Java 17 tải trực tiếp class ấy. Mức runtime của **chuỗi dependency cuối cùng** phải tương thích với binary thực tế.

Trong project nhiều module, hãy tập trung chính sách tại convention plugin hoặc build logic chung khi các module có cùng target. Nếu có lý do chủ đích cho nhiều target, cần ghi rõ module nào phải chạy trên JDK nào; tránh một cấu hình cấp root ghi đè module vốn phải giữ Java 17.

**Kiểm tra thêm:** task compileTestJava, test runtime, annotation processors, code generators và plugin khác cũng có thể bị ảnh hưởng bởi JDK/toolchain. Đặc biệt, plugin build cần tương thích với Gradle và JVM chạy chính plugin, chứ không chỉ tương thích với sourceCompatibility của mã ứng dụng.

## 10. Maven tương đương: maven.compiler.release

Dù tên **sourceCompatibility** thuộc Gradle, yêu cầu mức ngôn ngữ cũng có trong Maven. Với Maven Compiler Plugin, cấu hình release thường dùng:

~~~xml
<properties>
    <maven.compiler.release>21</maven.compiler.release>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
</properties>
~~~

Hoặc trong cấu hình plugin compiler phù hợp:

~~~xml
<build>
    <plugins>
        <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-compiler-plugin</artifactId>
            <configuration>
                <release>21</release>
            </configuration>
        </plugin>
    </plugins>
</build>
~~~

Đây là những đoạn cấu hình **đặt vào pom.xml**, không phải file XML độc lập. Dự án Maven cần một phiên bản Maven Compiler Plugin tương thích với dự án và JDK đang dùng.

**maven.compiler.release=21** có ý nghĩa tương đương **javac --release 21**, nhưng không tự cài JDK 21. Nếu Maven đang chạy bằng javac cũ và không có toolchain phù hợp, build vẫn lỗi. Maven có cơ chế toolchains riêng, tương tự việc cần chọn đúng JDK ở Gradle.

Kiểm tra môi trường:

~~~bash
mvn -version
mvn clean test
~~~

Lưu ý Maven và Gradle là hai hệ build độc lập; chỉ áp dụng phần cấu hình của hệ thực tế đang dùng, không chép các thuộc tính Gradle vào pom.xml.

## 11. IDE và CI: không để sourceCompatibility chỉ đúng trên máy cá nhân

Một project có thể chạy trong IDE nhưng thất bại khi dùng Gradle wrapper vì IDE đang chọn JDK 21 riêng còn Gradle daemon hoặc toolchain lại dùng JDK khác.

Quy trình kiểm tra:

1. **Chọn JDK 21 cho yêu cầu nguồn Java 21**, hoặc cấu hình Gradle toolchain để mọi máy chọn đúng compiler.
2. **Import dự án bằng Gradle** và chạy chính các Gradle tasks; không xem nút Run của IDE là bằng chứng đủ cho CI.
3. **Dùng Gradle wrapper** được commit trong project; tránh phụ thuộc bản Gradle cài toàn cục khác nhau giữa máy.
4. **Cấu hình CI có JDK/toolchain cần thiết** và đảm bảo Gradle có thể xác định compiler.
5. **Chạy test trên runtime thực tế** hoặc image sẽ dùng triển khai; mã Java 21 không thể chạy trực tiếp trên runtime Java 17.
6. **Kiểm tra annotation processor và plugin** nếu chúng thao tác bytecode hoặc API compiler, vì chúng có lịch sử tương thích JDK riêng.
7. **Giữ encoding nhất quán** cho mã nguồn và tài nguyên khi có tiếng Việt.
8. **Dùng log build khi lỗi:** phân biệt lỗi thiếu JDK, lỗi source level, lỗi logic Java và lỗi plugin.

Không cần buộc **Gradle daemon** và **Java compilation toolchain** luôn dùng cùng một JDK; Gradle hỗ trợ tách chúng trong giới hạn tương thích của bản Gradle. Điều quan trọng là xác nhận mỗi thành phần dùng JDK đúng và môi trường deployment đủ mới.

## 12. Đừng trộn mục tiêu tương thích trong cùng một module

Các cấu hình có thể mâu thuẫn về ý định:

~~~groovy
// Ví dụ minh họa cấu hình gây khó hiểu, không khuyến nghị.
java {
    sourceCompatibility = JavaVersion.VERSION_17
}
tasks.withType(JavaCompile).configureEach {
    options.release = 21
}
~~~

Nếu một task dùng --release 21, compiler sẽ dùng ngữ nghĩa release 21 cho task đó, trong khi thông tin compatibility nơi khác lại nói Java 17. Các plugin, IDE integration hoặc task bổ trợ có thể hiểu khác nhau.

Cách thiết kế tốt hơn:

- Mỗi module có **một target Java được tài liệu hóa**.
- Toolchain đủ mới để biên dịch target ấy.
- Compiler task sử dụng **--release cùng target**.
- Test runtime và production runtime đáp ứng class-file target.
- Nếu xuất bản library cho Java 17, không vô tình đưa mã chỉ biên dịch được trên Java 21 vào artifact Java 17.

Nếu thật sự cần nhiều artifact tương thích khác nhau, hãy dùng cấu trúc module, source set hoặc chiến lược multi-release JAR phù hợp, có build/test riêng. Đó là một thiết kế đóng gói có chủ đích, không chỉ là thay sourceCompatibility tại một dòng.

## 13. Quy trình cấu hình và xác minh nhanh

Khi được giao thêm record pattern hoặc pattern switch vào một project Gradle, làm theo trình tự:

1. **Xác định cú pháp cần dùng:** instanceof type pattern Java 16+ hay switch/record patterns Java 21+?
2. **Kiểm tra runtime mục tiêu:** nếu production buộc Java 17, cân nhắc giữ cú pháp Java 17 thay vì tự nâng source lên 21.
3. **Kiểm tra Gradle wrapper:** sử dụng bản Gradle hỗ trợ Java toolchain và JDK mục tiêu.
4. **Chọn toolchain:** với Java 21, đặt languageVersion 21 cho compiler Java.
5. **Đặt release:** options.release = 21 (Groovy) hoặc options.release.set(21) (Kotlin DSL).
6. **Tránh xung đột:** không dùng sourceCompatibility/targetCompatibility khác release mà không có lý do và kiểm chứng.
7. **Biên dịch bằng wrapper:** chạy clean compileJava, test; đọc lỗi javac đúng nguyên nhân.
8. **Kiểm tra runtime:** chạy class/JAR trên JDK mục tiêu, không chỉ trên JDK developer.
9. **Test các case pattern:** bao gồm subtype mới, guard false, record component null và selector null.
10. **Cố định CI:** bảo đảm compiler, plugin và test runtime nhất quán với mục tiêu phát hành.

Một checklist code review:

- [ ] Đã xác định tính năng pattern nào cần Java 21 thay vì chỉ Java 17?
- [ ] Gradle wrapper hỗ trợ JDK và công cụ biên dịch đang chọn?
- [ ] Java toolchain hoặc đường dẫn compiler thật sự dùng JDK 21+?
- [ ] Cấu hình sourceCompatibility, targetCompatibility và --release có nhất quán?
- [ ] Không thêm preview flags không cần thiết cho pattern chính thức Java 21?
- [ ] Mã có build được bằng wrapper và test được trên CI?
- [ ] Class file chạy được trên JVM production?
- [ ] Compile error do thiếu case/guard đã được sửa trong logic thay vì che bằng default?
- [ ] Multi-module và IDE không còn lệch cấu hình?

**Kết luận:** Để viết **record patterns** và **pattern matching for switch** ở trạng thái chính thức, hãy dùng mức nguồn **Java 21+**, compiler hỗ trợ Java 21 và runtime tương thích. Trong Gradle, một cách dễ bảo trì là **Java toolchain 21 + options.release 21**, thay vì chỉ đặt sourceCompatibility rồi giả định mọi môi trường đã sẵn sàng. Giữ rõ ranh giới giữa **cú pháp**, **API/bytecode** và **JDK thực thi** sẽ giúp các ví dụ pattern vừa biên dịch được, vừa chạy đúng trên máy phát triển, CI và production.