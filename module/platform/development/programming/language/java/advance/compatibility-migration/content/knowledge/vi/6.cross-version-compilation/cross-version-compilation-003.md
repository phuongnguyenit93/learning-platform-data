# `-source` và `-target`: phạm vi kiểm soát và rủi ro dùng API mới

Khi một dự án Java cần tiếp tục chạy trên JDK cũ nhưng nhóm phát triển muốn dùng JDK mới để biên dịch, hai tùy chọn `-source` và `-target` thường được dùng để đặt mức tương thích. Tuy nhiên, chúng chỉ kiểm soát hai khía cạnh của quá trình biên dịch: quy tắc ngôn ngữ Java được chấp nhận và định dạng bytecode được tạo ra.

**`-source` và `-target` không giới hạn tập API JDK mà compiler nhìn thấy.** Vì vậy, code có thể biên dịch thành công và tạo class file mang phiên bản cũ, nhưng vẫn gọi một method chỉ xuất hiện trong JDK mới. Khi chạy trên JDK mục tiêu cũ, ứng dụng có thể lỗi `NoSuchMethodError` hoặc `NoClassDefFoundError`.

Đây là rủi ro quan trọng trong Java Compatibility Migration: class file có vẻ tương thích không đồng nghĩa ứng dụng thật sự dùng được trên runtime cũ. Với JDK 9 trở lên, nên ưu tiên `--release` để kết hợp mức ngôn ngữ, mức bytecode và API nền tảng của release mục tiêu.

## 1. Ba khái niệm phải tách biệt

Để hiểu đúng `-source` và `-target`, cần phân biệt ba lớp:

| Lớp | Câu hỏi | Cơ chế kiểm soát |
|---|---|---|
| Ngôn ngữ nguồn | Compiler chấp nhận cú pháp và quy tắc Java của phiên bản nào? | `-source` hoặc `--source` |
| Định dạng bytecode | Class file được tạo ra có phiên bản mà JVM nào có thể đọc? | `-target` hoặc `--target` |
| API nền tảng | Code được phép tham chiếu tới những class, method và field nào của JDK? | `--release`; hoặc cấu hình platform API tương ứng như boot class path trong các môi trường cũ |

Ba khái niệm này liên quan nhưng không thể thay thế cho nhau.

### 1.1. `-source`: giới hạn ngôn ngữ Java

`-source` chỉ định phiên bản ngôn ngữ mà compiler dùng để phân tích source. Nó quyết định các cú pháp, quy tắc ngôn ngữ và một số quy tắc kiểm tra tại compile time được chấp nhận.

Ví dụ, `var` cho local variable chỉ có từ Java 10:

```java
public class SourceLevelExample {
    public static void main(String[] args) {
        var message = "Hello";
        System.out.println(message);
    }
}
```

Nếu biên dịch với mức source 8, compiler sẽ từ chối cú pháp `var`. Khi dùng mức source 10 trở lên, cú pháp này được chấp nhận nếu compiler hỗ trợ release tương ứng.

`-source` không có nghĩa compiler đang chạy bằng JDK của phiên bản đó. Chẳng hạn, lệnh `javac` thuộc JDK 17 vẫn có thể được yêu cầu phân tích source theo quy tắc Java 8. Compiler vẫn là compiler của JDK 17; chỉ mức ngôn ngữ được chọn là Java 8.

### 1.2. `-target`: chọn phiên bản class file

`-target` chỉ định phiên bản định dạng class file mà compiler tạo ra. JVM kiểm tra phiên bản class file khi nạp class. Nếu class file mới hơn mức JVM hỗ trợ, JVM có thể ném `UnsupportedClassVersionError`.

Một số class file major version thường gặp:

| Java release | Class file major version |
|---:|---:|
| Java 8 | 52 |
| Java 9 | 53 |
| Java 10 | 54 |
| Java 11 | 55 |
| Java 17 | 61 |

Ví dụ, `-target 8` yêu cầu compiler tạo class file major version 52. Điều đó giúp JVM Java 8 đọc được định dạng class file, nhưng chưa chứng minh mọi API mà class gọi đều tồn tại trong Java 8.

### 1.3. API nền tảng là lớp riêng

Compiler cần tìm class và method để kiểm tra kiểu khi biên dịch. Nếu compiler đang chạy trên JDK 17, platform classes mà nó nhìn thấy mặc định thuộc JDK 17. Đặt `-source 8 -target 8` không tự thay thế tập class nền tảng đó bằng API của Java 8.

Vì thế, compiler có thể chấp nhận một lời gọi method được thêm ở Java 9, dù class file được xuất ra có major version 52. Đây là nguồn gốc của lỗi “biên dịch thành công nhưng chạy không được trên Java mục tiêu”.

## 2. Ví dụ: bytecode Java 8 nhưng gọi API Java 9

Giả sử dự án muốn tạo artifact chạy trên Java 8, nhưng build server đã nâng lên JDK 17. Source có lời gọi `List.of`, API được bổ sung từ Java 9:

```java
import java.util.List;

public class ApiLeak {
    public static void main(String[] args) {
        System.out.println(List.of("Java", "Compatibility"));
    }
}
```

Nếu biên dịch bằng JDK 17 theo cách sau:

```bash
javac -source 8 -target 8 ApiLeak.java
```

compiler có thể biên dịch thành công và phát cảnh báo rằng bootstrap class path chưa được đặt cùng với `-source 8`. Compiler nhìn thấy `java.util.List` của JDK 17 nên tìm thấy `List.of`.

Có thể kiểm tra phiên bản class file:

```bash
javap -verbose ApiLeak | findstr "major version"
```

Trên Windows, kết quả cho thấy major version 52. Trên Linux/macOS có thể dùng `grep` thay cho `findstr`:

```bash
javap -verbose ApiLeak | grep "major version"
```

Class file mang phiên bản Java 8 nhưng chứa symbolic reference tới method `java.util.List.of`. Khi chạy trên Java 8, class `List` không có method đó; quá trình liên kết method thất bại với `NoSuchMethodError`.

<text color="secondary" size="sm">Luồng lỗi</text>

```text
JDK 17 javac
   |
   | -source 8 -target 8
   v
Source dùng List.of() của Java 9
   |
   v
Class file major version 52
   |
   | JVM Java 8 đọc được class file
   v
Liên kết java.util.List.of()
   |
   v
NoSuchMethodError: Java 8 không có List.of()
```

Điểm quan trọng là `UnsupportedClassVersionError` và `NoSuchMethodError` biểu hiện hai vấn đề khác nhau:

- `UnsupportedClassVersionError`: JVM không đọc được định dạng class file.
- `NoSuchMethodError`: JVM đọc được class file nhưng method được tham chiếu không có trong class được nạp lúc runtime.

Một lỗi tương tự có thể xảy ra với class mới, field mới hoặc constructor mới của API nền tảng, tạo ra `NoClassDefFoundError`, `NoSuchFieldError` hoặc các lỗi liên kết khác.

## 3. Vì sao `-source` và `-target` không đủ?

### 3.1. Compiler dùng platform API của JDK đang chạy

Hai tùy chọn này không thay đổi boot/platform classes mà compiler sử dụng. Khi chạy `javac` từ JDK 17, compiler mặc định nhìn thấy các API thuộc JDK 17. Nếu chỉ đặt mức source và target cũ, code vẫn có thể gọi các API mới.

Đặt `-target` thấp chỉ thay đổi định dạng class file. JVM không đọc metadata của class file để biết rằng tác giả muốn chạy trên Java 8 rồi từ chối mọi API xuất hiện sau Java 8. JVM chỉ phân giải các class, field và method khi cần.

### 3.2. Dependency bên thứ ba cũng có thể gây lỗi

Ngay cả khi source chỉ dùng API Java 8, một thư viện dependency có thể được biên dịch bằng JDK mới và tham chiếu API chỉ có ở Java 11 hoặc 17. Consumer có thể biên dịch được vì compiler đọc được public signature của thư viện, nhưng thư viện lại lỗi khi chạy trên Java 8.

Ngoài ra, nếu dependency được biên dịch với class file major version 61, JVM Java 8 không thể nạp nó. Việc đặt `-target 8` cho source của ứng dụng không tự hạ bytecode của dependency.

Do đó, compatibility target cần áp dụng cho toàn bộ dependency graph, bao gồm thư viện nội bộ và artifact được phát hành riêng.

### 3.3. Không đảm bảo tương thích hành vi

API có thể tồn tại ở cả hai phiên bản nhưng hành vi có thể khác. JDK mới có thể thay đổi thuật toán, giá trị mặc định, provider, cách xử lý TLS, charset, locale hoặc thời điểm phát sinh exception.

`-source`, `-target` và `--release` đều không chứng minh hành vi ứng dụng giống nhau. Cần chạy test trên runtime mục tiêu và kiểm tra các luồng nghiệp vụ thực tế.

### 3.4. Không bảo đảm dependency được resolve phù hợp

Một build có thể resolve dependency khác nhau theo JDK, Gradle/Maven profile, repository hoặc variant metadata. Nếu pipeline chỉ ghi lại version khai báo mà không ghi version thực tế được resolve, kết quả migration khó tái hiện.

Hãy lưu dependency graph của compile/runtime/test và xác minh phiên bản của từng artifact quan trọng.

## 4. `--release`: kiểm soát cả source, target và API

Từ JDK 9, `javac` cung cấp `--release`. Tùy chọn này được thiết kế để biên dịch source cho một Java release cụ thể, đồng thời giới hạn API nền tảng theo release đó.

Ví dụ, dùng JDK 17 để biên dịch cho Java 8:

```bash
javac --release 8 ApiLeak.java
```

Với source gọi `List.of`, compiler báo lỗi vì API này không tồn tại trong Java 8. Nếu đổi code sang API có từ Java 8, ví dụ:

```java
import java.util.Arrays;
import java.util.List;

public class ApiCompatible {
    public static void main(String[] args) {
        List<String> values = Arrays.asList("Java", "Compatibility");
        System.out.println(values);
    }
}
```

thì lệnh `javac --release 8 ApiCompatible.java` có thể biên dịch với JDK 17 và tạo class file cho Java 8.

### 4.1. `--release` làm gì?

Về mặt mục đích, `--release N` kết hợp ba ràng buộc:

1. Chấp nhận cú pháp và quy tắc ngôn ngữ của Java release N.
2. Tạo bytecode tương ứng với release N.
3. Chỉ cho phép truy cập các API nền tảng công khai thuộc release N.

JDK lưu thông tin API lịch sử trong dữ liệu nền tảng được compiler sử dụng, thường được nhắc tới qua `ct.sym`. Nhờ đó, compiler JDK mới có thể kiểm tra source theo API của một release cũ mà không cần một JDK cũ đầy đủ cho từng release.

### 4.2. `--release` có giới hạn gì?

`--release` kiểm soát API nền tảng của Java SE và các API JDK được đưa vào tập API của release tương ứng. Nó không tự kiểm tra toàn bộ dependency bên thứ ba. Nếu một thư viện Maven/Gradle gọi API mới bên trong implementation, compiler của ứng dụng không nhất thiết phát hiện được chỉ từ public signature.

Nó cũng không thay thế kiểm thử trên runtime mục tiêu, không chứng minh behavioral compatibility và không tự kiểm soát native library.

Không dùng đồng thời `--release` với `-source`, `-target` hoặc các tùy chọn thay đổi platform system image không tương thích. Khi đã chọn `--release`, hãy để tùy chọn này làm nguồn cấu hình release duy nhất cho tác vụ compile.

### 4.3. JDK 8 và giới hạn của `--release`

`--release` chỉ có từ JDK 9. Nếu build bằng JDK 8, compiler không nhận tùy chọn này. Khi đó, cách đơn giản và đáng tin cậy để build cho Java 8 là dùng JDK 8 compiler và platform classes tương ứng.

Trong các môi trường cross-compile cũ, `-bootclasspath` có thể được dùng để trỏ tới platform classes của target. Cần bảo đảm boot class path thực sự thuộc đúng JDK/API mục tiêu; chỉ đặt `-source` và `-target` vẫn không giới hạn API.

## 5. Cấu hình Maven

### 5.1. Cách cũ: source và target

Một dự án Maven có thể khai báo:

```xml
<properties>
    <maven.compiler.source>8</maven.compiler.source>
    <maven.compiler.target>8</maven.compiler.target>
</properties>
```

Cấu hình này đặt ngôn ngữ và bytecode target. Nếu Maven chạy bằng JDK 17, nó không tự giới hạn API JDK ở mức Java 8.

### 5.2. Cách khuyến nghị: release

Với Maven Compiler Plugin hỗ trợ thuộc tính `release` (từ dòng plugin 3.6 trở lên), có thể khai báo:

```xml
<properties>
    <maven.compiler.release>8</maven.compiler.release>
</properties>
```

Hoặc cấu hình tường minh plugin:

```xml
<build>
    <plugins>
        <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-compiler-plugin</artifactId>
            <version>3.13.0</version>
            <configuration>
                <release>8</release>
            </configuration>
        </plugin>
    </plugins>
</build>
```

Hãy chọn phiên bản plugin phù hợp với Maven/JDK đang dùng và kiểm tra cấu hình effective POM. Parent POM, profile hoặc plugin management có thể ghi đè giá trị tại module con.

Nếu cần build/test bằng JDK 17 nhưng vẫn hỗ trợ runtime Java 11, có thể đặt `<maven.compiler.release>11</maven.compiler.release>` trong khi Maven chạy bằng JDK 17, miễn là các plugin và dependency hỗ trợ môi trường này.

## 6. Cấu hình Gradle

### 6.1. Phân biệt sourceCompatibility/targetCompatibility và options.release

Gradle Java plugin có các thuộc tính:

- `sourceCompatibility`: mức ngôn ngữ Java cho source.
- `targetCompatibility`: phiên bản bytecode target.
- `options.release`: yêu cầu compiler tuân theo Java release cụ thể, gồm cả API nền tảng.

Ví dụ cách đặt source/target:

```groovy
java {
    sourceCompatibility = JavaVersion.VERSION_1_8
    targetCompatibility = JavaVersion.VERSION_1_8
}
```

Cấu hình trên tương đương việc đặt các mức source/target trong compiler. Nó không thay thế API restriction của `--release`.

### 6.2. Dùng toolchain mới và release cũ

Với Gradle, có thể chạy compiler bằng JDK 17 nhưng biên dịch source cho Java 8:

```groovy
java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

tasks.withType(JavaCompile).configureEach {
    options.release = 8
}
```

Ở ví dụ này, toolchain chọn JDK 17 để chạy compiler; `options.release` giới hạn source language, bytecode và API nền tảng ở Java 8. Nếu dự án muốn chạy trên Java 11, đổi `options.release` thành `11`.

Không nên chỉ nhìn `targetCompatibility` để kết luận API đã được giới hạn. Đồng thời, Gradle variant metadata có thể dùng target compatibility để chọn artifact phù hợp giữa các project; điều này là một chức năng khác với việc giới hạn API nền tảng của compiler.

### 6.3. Nhiều module có release khác nhau

Một build nhiều module có thể có module library hỗ trợ Java 8 và ứng dụng chỉ chạy Java 17. Khi đó, cần đặt release rõ ràng ở từng module và xác minh dependency direction.

Ví dụ:

```groovy
project(":shared-library") {
    tasks.withType(JavaCompile).configureEach {
        options.release = 8
    }
}

project(":modern-service") {
    tasks.withType(JavaCompile).configureEach {
        options.release = 17
    }
}
```

Module Java 17 có thể dùng library Java 8. Chiều ngược lại không đúng nếu library Java 8 phụ thuộc vào API hoặc bytecode của module Java 17. Hãy để dependency graph phản ánh rõ quan hệ này.

Nếu dự án có Kotlin hoặc Scala, `JavaCompile.options.release` chỉ áp dụng cho tác vụ JavaCompile. Cần cấu hình JVM target/API phù hợp riêng cho các compiler plugin đó và kiểm tra artifact cuối cùng.

## 7. Chọn compiler JDK và runtime JDK như thế nào?

Các khái niệm sau cần được ghi riêng trong cấu hình và báo cáo migration:

| Khái niệm | Ý nghĩa |
|---|---|
| Build JDK | JDK chạy Gradle/Maven và các plugin build |
| Compiler toolchain | JDK thực hiện compile source Java |
| Release/source target | Mức ngôn ngữ, bytecode và API mà module hướng tới |
| Runtime JDK | JDK/JRE image thực tế chạy ứng dụng |
| Dependency bytecode target | Phiên bản class file của từng thư viện trong graph |

Ví dụ, một nhóm có thể chạy Gradle trên JDK 17, dùng toolchain JDK 17, compile library bằng `--release 11`, rồi chạy ứng dụng trên JDK 11. Đây là cấu hình hợp lệ nếu toàn bộ dependency và plugin runtime tương thích với Java 11.

Tuy nhiên, nếu dependency đã được biên dịch cho Java 17, runtime Java 11 vẫn không nạp được dependency đó. Việc ứng dụng tự biên dịch ra bytecode 11 không hạ bytecode của thư viện.

Khi migration toàn bộ runtime từ 11 lên 17, cần kiểm tra cả:

- Các module được compile bằng release nào.
- Dependency có class file major version nào.
- Các API JDK mới có bị sử dụng trong module được tuyên bố hỗ trợ runtime cũ không.
- Các thư viện native có artifact cho OS/architecture mục tiêu không.
- Plugin build/test có tương thích với JDK chạy build không.

## 8. Cách kiểm tra artifact có thực sự tương thích

Không nên kết luận chỉ từ dòng cấu hình `release`, `sourceCompatibility` hoặc `targetCompatibility`. Hãy kiểm tra artifact được tạo và chạy nó bằng runtime mục tiêu.

### 8.1. Kiểm tra class file version

Sử dụng `javap`:

```bash
javap -verbose -classpath build/classes/java/main \
  com.example.Application | grep "major version"
```

Major version giúp phát hiện class file mới hơn runtime mục tiêu. Với JAR dependency, có thể giải nén hoặc dùng công cụ phân tích bytecode để kiểm tra các class quan trọng.

### 8.2. Kiểm tra API JDK mục tiêu

Với compiler JDK 9 trở lên, build bằng `--release` hoặc `options.release` là lớp kiểm tra chính cho API nền tảng. Khi cần kiểm tra thêm dependency đã biên dịch, dùng `jdeps`, `jdeprscan` và test trên runtime mục tiêu.

Ví dụ:

```bash
jdeps --jdk-internals --recursive --class-path "lib/*" app.jar
jdeprscan --release 11 --class-path "lib/*" app.jar
```

Chọn release tương ứng với runtime mà artifact cần hỗ trợ. Các công cụ phân tích tĩnh có giới hạn với reflection, service loading và native code.

### 8.3. Chạy test bằng đúng runtime

Nếu artifact cần hỗ trợ Java 11, chạy integration test bằng JDK 11 hoặc runtime image Java 11 thực tế. Nếu artifact chỉ cần Java 17, chạy test bằng JDK 17 và môi trường triển khai tương ứng.

Nên kiểm tra:

- Startup và shutdown.
- Reflection, proxy, bytecode generation và instrumentation.
- Serialization/deserialization và dữ liệu được lưu từ phiên bản cũ.
- TLS, certificate, HTTP client và kết nối database/message broker.
- Charset, locale, timezone và file path.
- JNI/JNA, native library và các phụ thuộc hệ điều hành.
- Các luồng xử lý lỗi, timeout, retry và batch theo lịch.

## 9. Các hiểu nhầm phổ biến

### “Đặt target 11 thì chắc chắn chạy trên Java 11”

Không đúng. `target` chỉ chọn class file format. Source vẫn có thể gọi API Java 17 nếu compiler đang chạy bằng JDK 17 và không giới hạn platform API.

### “Source 11 có nghĩa đang dùng compiler Java 11”

Không đúng. Đây là mức ngôn ngữ source. Compiler thực tế được quyết định bởi JDK chạy `javac` hoặc toolchain được build tool chọn.

### “Compile thành công nghĩa là mọi dependency tương thích”

Không đúng. Compiler có thể kiểm tra public signatures nhưng không chứng minh implementation của thư viện chỉ gọi API có trong runtime mục tiêu. Cần kiểm tra dependency graph, bytecode và chạy trên runtime đích.

### “`--release` giải quyết toàn bộ compatibility”

Không đúng. `--release` kiểm soát API nền tảng khi compile source. Nó không kiểm soát API bên thứ ba, native code, runtime behavior, cấu hình production hoặc schema giao tiếp.

### “Có thể dùng JDK 17 để build rồi chạy trên Java 11 mà không cần test Java 11”

Không nên kết luận như vậy. Nếu Java 11 vẫn là runtime được hỗ trợ, cần có test job chạy bằng JDK/runtime 11 hoặc bằng image tương đương để xác nhận dependency và hành vi.

## 10. Checklist chọn mức source/target/release

- [ ] Đã xác định runtime thấp nhất cần hỗ trợ.
- [ ] Đã xác định JDK thực tế chạy build và compiler toolchain.
- [ ] Với JDK 9+, đã dùng `--release` hoặc `options.release` thay vì chỉ đặt source/target khi cần giới hạn API.
- [ ] Nếu dùng JDK 8 compiler, đã biên dịch với platform API Java 8 tương ứng.
- [ ] Đã kiểm tra class file version của module và dependency quan trọng.
- [ ] Đã kiểm tra dependency trực tiếp và bắc cầu có tương thích runtime mục tiêu.
- [ ] Đã cấu hình riêng compiler Kotlin/Scala nếu module có các ngôn ngữ đó.
- [ ] Đã chạy test bằng runtime thấp nhất được hỗ trợ.
- [ ] Đã ghi rõ release target và lý do cho từng module.

## 11. Kết luận

`-source` kiểm soát ngôn ngữ mà compiler chấp nhận; `-target` kiểm soát định dạng bytecode được tạo ra. Cả hai không tự giới hạn API JDK mà source có thể gọi. Vì vậy, biên dịch bằng JDK mới với source/target cũ có thể tạo class file cũ nhưng chứa tham chiếu tới API mới, dẫn đến lỗi liên kết khi chạy trên runtime cũ.

Với JDK 9 trở lên, hãy ưu tiên `--release` hoặc cấu hình tương đương như Gradle `options.release` và Maven Compiler Plugin `release`. Đồng thời kiểm tra dependency bên thứ ba, bytecode của toàn bộ graph và chạy test trên runtime mục tiêu. Khi làm rõ riêng build JDK, compiler toolchain, release target và runtime JDK, nhóm phát triển sẽ tránh được nhiều lỗi migration chỉ xuất hiện sau khi triển khai.
