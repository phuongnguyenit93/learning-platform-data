# javac --release 17 và giới hạn API đích

Khi biên dịch một ứng dụng Java 17, chỉ đặt mức cú pháp hoặc định dạng bytecode chưa đủ để bảo đảm chương trình chạy được trên Java 17. Một compiler mới hơn có thể nhìn thấy các API mới của JDK mà runtime Java 17 chưa có. Nếu code gọi những API đó, file class vẫn có thể mang định dạng bytecode tương thích với Java 17 nhưng lại lỗi khi chạy vì thiếu method hoặc class.

Tùy chọn **javac --release 17** giải quyết vấn đề này bằng cách đồng bộ ba giới hạn quan trọng:

1. Ngôn ngữ Java được dùng khi biên dịch ở mức Java 17.
2. File class được tạo ra theo định dạng của Java 17.
3. Compiler chỉ cho phép tham chiếu các API nền tảng được hỗ trợ và công bố cho Java 17.

Điểm thứ ba là khác biệt quan trọng so với việc chỉ dùng **-source 17 -target 17**. Tùy chọn **--release** giúp phát hiện ngay trong lúc biên dịch những lời gọi API chỉ xuất hiện ở JDK mới hơn. Đây là lựa chọn phù hợp khi build trên JDK mới nhưng sản phẩm cần chạy trên Java 17.

## 1. --release 17 làm gì?

Tùy chọn **--release N** yêu cầu javac biên dịch source code theo phiên bản Java SE N. Với --release 17, compiler áp dụng:

- Quy tắc ngôn ngữ và cú pháp của Java 17.
- Định dạng class file tương ứng Java 17, có major version 61.
- Bộ API nền tảng được công bố và hỗ trợ cho Java 17.

Ví dụ:

~~~bash
javac --release 17 -d out src/com/example/Main.java
~~~

Nếu source dùng cú pháp chỉ được đưa vào một phiên bản Java sau 17, compiler sẽ từ chối. Nếu source gọi method hoặc dùng class nền tảng chỉ xuất hiện sau Java 17, compiler cũng sẽ từ chối.

Tùy chọn --release có từ JDK 9. Với JDK 17, có thể chọn các bản phát hành được compiler đó hỗ trợ, trong đó có Java 17. Một compiler chỉ có thể biên dịch cho các release mà chính nó hỗ trợ; JDK 17 không thể tạo target Java 21, còn JDK mới hơn có thể dùng --release 17 để tạo artifact cho Java 17.

### Ví dụ biên dịch chương trình Java 17

~~~java
package com.example;

import java.util.List;

public class Main {
    public static void main(String[] args) {
        List<String> names = List.of("Lan", "Minh");
        names.forEach(System.out::println);
    }
}
~~~

Biên dịch:

~~~bash
javac --release 17 -d out src/com/example/Main.java
~~~

Chạy bằng Java 17:

~~~bash
java -cp out com.example.Main
~~~

List.of() là API có từ Java 9 nên có sẵn trong Java 17. File class được tạo theo mức bytecode Java 17.

## 2. Vì sao -source và -target chưa đủ?

Hai tùy chọn này kiểm soát hai phần khác nhau:

- **-source N**: giới hạn cú pháp/ngôn ngữ được chấp nhận.
- **-target N**: chọn định dạng bytecode class file đầu ra.

Chúng không tự giới hạn tập API của JDK mà compiler nhìn thấy. Nếu dùng JDK 21 để biên dịch với -source 17 -target 17, compiler vẫn có thể nhìn thấy method được thêm vào JDK 21.

Ví dụ, List.getFirst() được bổ sung trong Java 21:

~~~java
import java.util.List;

public class NewerApiExample {
    public static void main(String[] args) {
        List<String> values = List.of("first", "second");
        System.out.println(values.getFirst());
    }
}
~~~

Nếu dùng JDK 21 và chỉ đặt source/target:

~~~bash
javac -source 17 -target 17 -d out NewerApiExample.java
~~~

Compiler có thể chấp nhận lời gọi getFirst() vì API List của JDK 21 có method đó. Class đầu ra có thể mang bytecode version 61, nhưng khi chạy trên Java 17, runtime không có List.getFirst() và có thể ném NoSuchMethodError.

Nếu dùng:

~~~bash
javac --release 17 -d out NewerApiExample.java
~~~

Compiler báo lỗi vì List.getFirst() không thuộc API Java 17. Đây là lỗi được phát hiện sớm ở bước build thay vì xuất hiện khi ứng dụng chạy trên môi trường đích.

### Bảng so sánh

| Tùy chọn | Giới hạn ngôn ngữ | Định dạng class file | Giới hạn API nền tảng theo release |
| --- | --- | --- | --- |
| Chỉ -source 17 | Có | Không tự đặt target tương ứng | Không |
| Chỉ -target 17 | Không tự giới hạn cú pháp | Có | Không |
| -source 17 -target 17 | Có | Có | Không |
| --release 17 | Có | Có | Có |

Vì vậy, khi mục tiêu là chạy trên Java 17, --release 17 thường là cách diễn đạt ý định đầy đủ và ít gây nhầm lẫn hơn việc ghép -source với -target.

Không truyền đồng thời --release với -source hoặc -target cho cùng một lần biên dịch. --release đã thiết lập các mức đó và không được kết hợp với các tùy chọn source/target riêng.

## 3. Giới hạn API đích có ý nghĩa gì?

Khi biên dịch với --release 17, javac kiểm tra tham chiếu tới API nền tảng theo tập API của Java 17. Những class, method hoặc field chỉ được thêm vào ở release sau sẽ không khả dụng trong quá trình biên dịch đó.

Ví dụ các API theo phiên bản:

| API | Release được bổ sung | Có dùng được khi --release 17? |
| --- | ---: | --- |
| List.of(...) | Java 9 | Có |
| String.isBlank() | Java 11 | Có |
| Files.mismatch(...) | Java 12 | Có |
| Stream.toList() | Java 16 | Có |
| List.getFirst() | Java 21 | Không |

Bảng này minh họa nguyên tắc: API có trong release 17 hoặc cũ hơn có thể được sử dụng nếu còn thuộc API được hỗ trợ; API được thêm sau Java 17 sẽ bị giới hạn.

### Không chỉ kiểm tra tên method

Giới hạn API còn áp dụng cho:

- Class và interface.
- Constructor.
- Method và overload.
- Field và constant.
- Các kiểu dữ liệu trong chữ ký method.
- API module nền tảng được công bố cho release đó.

Ví dụ, một method có thể tồn tại từ Java 17 nhưng một overload nhận kiểu mới hơn chỉ xuất hiện ở Java 21. Compiler với --release 17 sẽ không cho dùng overload mới.

### API JDK được công bố và internal API

--release hướng tới public, supported và documented APIs của release được chọn. Các package nội bộ như jdk.internal.* không trở thành API ổn định chỉ vì chúng có trong một bản JDK.

Không nên dùng internal API để lách giới hạn đích. Nếu một chức năng không có API công khai phù hợp trong Java 17, cần chọn thư viện tương thích hoặc thiết kế cách triển khai khác.

## 4. Build bằng JDK mới nhưng chạy trên Java 17

Một tình huống phổ biến là máy build đã cài JDK 21 hoặc mới hơn, nhưng môi trường triển khai vẫn dùng Java 17.

Nếu chỉ dùng compiler mặc định của JDK mới, source code có thể vô tình tham chiếu API mới. Cách cấu hình rõ ràng:

~~~bash
javac --release 17 -d out src/com/example/*.java
~~~

Compiler có thể là JDK mới hơn, nhưng API nền tảng và bytecode đầu ra bị giới hạn ở Java 17.

Sau đó chạy kiểm thử trên runtime Java 17:

~~~bash
java -version
java -cp out com.example.Main
~~~

--release 17 không cài Java 17 runtime và cũng không tự chọn runtime khi chạy. Nó chỉ cấu hình compiler. Máy build vẫn có thể đang chạy JDK 21, còn ứng dụng cần được kiểm thử bằng một JDK 17 thực tế hoặc môi trường tương đương.

### Kiểm tra compiler và runtime đang dùng

Trên máy có nhiều JDK, javac và java có thể trỏ tới các bản khác nhau qua PATH:

~~~bash
javac -version
java -version
~~~

Hai lệnh giúp xác định phiên bản compiler và runtime đang được gọi. Với CI, build container hoặc build agent, nên ghi rõ JDK/toolchain để kết quả có thể tái lập.

## 5. Kiểm tra class file sau khi biên dịch

Class file của Java 17 có major version 61. Có thể kiểm tra bằng javap:

~~~bash
javap -verbose -classpath out com.example.Main
~~~

Trong output, tìm dòng:

~~~text
major version: 61
~~~

Đây là bằng chứng định dạng class file tương ứng Java 17. Tuy nhiên, chỉ kiểm tra major version chưa chứng minh mọi dependency hoặc mọi lời gọi API đều tương thích với runtime 17. Cần kết hợp kiểm tra dependency và chạy test trên JDK 17.

### Chạy javap cho một class cụ thể

Nếu class có package:

~~~bash
javap -verbose -classpath out com.example.Main
~~~

Nếu class không có package:

~~~bash
javap -verbose -classpath out Main
~~~

javap là công cụ đọc thông tin class file. Không chỉnh bytecode bằng tay chỉ để thay major version từ một giá trị cao xuống 61; việc đổi con số không chuyển cú pháp, API hoặc bytecode mới thành dạng Java 17 hiểu được.

## 6. --release không backport tính năng Java mới

--release 17 không chuyển đổi code Java 21 thành code Java 17. Nó yêu cầu source vốn đã tuân thủ ngôn ngữ Java 17 và chỉ dùng API có sẵn ở release 17.

Ví dụ:

- Cú pháp ngôn ngữ mới hơn Java 17 sẽ bị từ chối.
- API nền tảng chỉ có từ Java 21 sẽ bị từ chối.
- Bytecode được tạo vẫn là bytecode Java 17.

Nếu muốn dùng một tính năng ngôn ngữ/API mới hơn, cần nâng runtime tối thiểu hoặc tìm cách triển khai tương đương trên Java 17. Không thể chỉ đổi cờ compiler để làm runtime cũ hiểu được tính năng mới.

### Preview features là trường hợp riêng

Preview feature gắn với một release cụ thể và phải được bật rõ ràng khi biên dịch/chạy bằng JDK tương ứng. Chúng không phải API ổn định để mặc định đưa vào một ứng dụng yêu cầu tương thích lâu dài. Với mục tiêu Java 17 thông thường, hãy dùng tính năng đã được hoàn thiện trong Java 17 và không phụ thuộc preview.

## 7. Những gì --release 17 không bảo đảm

--release là một hàng rào quan trọng, nhưng không thay thế toàn bộ quy trình kiểm tra tương thích.

### Không kiểm tra toàn bộ dependency bên thứ ba

Compiler kiểm tra API nền tảng theo Java 17, nhưng dependency trên classpath/module path là một đầu vào riêng. Nếu thư viện yêu cầu Java 21 hoặc gọi API chỉ có trên Java 21, ứng dụng vẫn có thể gặp vấn đề khi chạy Java 17.

Ví dụ:

- Một JAR có class file version cao hơn 61 có thể gây UnsupportedClassVersionError khi runtime Java 17 nạp class đó.
- Một thư viện được biên dịch ở mức bytecode thấp hơn nhưng gọi API JDK mới qua reflection hoặc dynamic loading có thể thất bại khi thực thi.
- Một thư viện có thể dùng class nền tảng mới trong code path chỉ được gọi ở một tình huống hiếm; compile ứng dụng không nhất thiết phát hiện được mọi lỗi runtime trong dependency.

Vì vậy, kiểm tra yêu cầu Java tối thiểu của từng dependency và chạy test trên runtime mục tiêu.

### Không bảo đảm tương thích với JDK internals

Nếu code dùng reflection, Class.forName, MethodHandles hoặc tên class được tạo từ chuỗi để truy cập thành phần nội bộ, compiler có thể không phát hiện được dependency đó. Strong encapsulation của Java 17 và module access vẫn áp dụng ở runtime.

Không dựa vào sun.*, jdk.internal.* hoặc private member của JDK để xây API ứng dụng.

### Không chọn runtime cho ứng dụng

Build bằng --release 17 không buộc production chạy Java 17. Nếu production chạy Java 11, bytecode version 61 vẫn không tương thích. Nếu production chạy Java 21, chương trình thường có thể chạy nhưng hành vi vẫn cần được kiểm thử trên runtime thực tế.

### Không thiết lập encoding hoặc cấu hình build khác

--release không thay thế các cấu hình như:

- Source encoding (-encoding UTF-8).
- Classpath hoặc module path.
- Annotation processor.
- Resource filtering và packaging.
- Runtime JVM options.
- Cấu hình test runner.

Những thành phần đó vẫn cần được cấu hình riêng.

## 8. --release và module system

Với ứng dụng modular, --release 17 vẫn giới hạn API nền tảng theo Java 17. Các module ứng dụng và dependency cần được đặt trên module path theo cách phù hợp.

Ví dụ cấu trúc:

~~~text
src/
  com.example.app/
    module-info.java
    com/example/app/Main.java
~~~

Module descriptor:

~~~java
module com.example.app {
    requires java.net.http;
    exports com.example.app;
}
~~~

Biên dịch:

~~~bash
javac --release 17 \
      -d out \
      --module-source-path src \
      -m com.example.app
~~~

Chạy:

~~~bash
java --module-path out \
     -m com.example.app/com.example.app.Main
~~~

Ví dụ dùng module java.net.http, có từ Java 11 nên có trong Java 17. Khi biên dịch với --release 17, compiler sẽ từ chối module hoặc API nền tảng chỉ xuất hiện ở release sau.

### Không thể dùng --add-exports để mở rộng API system module khi đã chọn --release

--release cố định tập API và module platform theo release đích. Vì thế, compiler không cho dùng --add-exports để mở rộng các package của system module ngoài tập đã chọn trong cùng lần biên dịch.

Nếu source phụ thuộc một package nội bộ của system module, đây là tín hiệu cần xem lại dependency. Không nên phá giới hạn API đích để làm cho code phụ thuộc JDK internals biên dịch được.

--add-exports và --add-opens có vai trò khác nhau trong module access; chúng không phải cách thay thế cho API công khai tương thích.

## 9. Cấu hình Maven cho Java 17

Với Maven, dùng thuộc tính maven.compiler.release để cấu hình compiler plugin:

~~~xml
<properties>
    <maven.compiler.release>17</maven.compiler.release>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
</properties>
~~~

Đảm bảo maven-compiler-plugin trong build sử dụng phiên bản hỗ trợ thuộc tính release. Có thể khai báo plugin rõ ràng trong build/plugins:

~~~xml
<build>
    <plugins>
        <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-compiler-plugin</artifactId>
            <version>3.11.0</version>
            <configuration>
                <release>17</release>
            </configuration>
        </plugin>
    </plugins>
</build>
~~~

Ví dụ dùng phiên bản plugin cụ thể để minh họa cấu trúc cấu hình. Trong dự án thực tế, dùng phiên bản plugin được tổ chức quản lý và hỗ trợ trong build hiện tại; không để plugin quá cũ bỏ qua hoặc không hiểu cấu hình release.

### Vì sao không chỉ đặt source và target trong Maven?

Cấu hình cũ:

~~~xml
<maven.compiler.source>17</maven.compiler.source>
<maven.compiler.target>17</maven.compiler.target>
~~~

chỉ mô tả source/target. Khi build bằng JDK mới hơn, compiler vẫn có thể nhìn thấy API mới. Với mục tiêu Java 17, ưu tiên:

~~~xml
<maven.compiler.release>17</maven.compiler.release>
~~~

### Chọn JDK build bằng Maven Toolchains

Nếu tổ chức cần chỉ định JDK compiler riêng, Maven Toolchains cho phép build chọn JDK đã cấu hình thay vì phụ thuộc hoàn toàn vào JDK chạy Maven. Cần phân biệt:

- JDK chạy Maven.
- JDK compiler được chọn qua toolchain.
- maven.compiler.release là mức API/bytecode đích.
- JDK chạy test hoặc ứng dụng.

Đặt release không tự cài hoặc chọn JDK toolchain. CI cần cung cấp đúng JDK và kiểm tra phiên bản thực tế.

## 10. Cấu hình Gradle cho Java 17

Gradle có Java toolchain để chọn JDK dùng cho compile/test/run và options.release để giới hạn release API/bytecode.

Ví dụ Groovy DSL:

~~~groovy
java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

tasks.withType(JavaCompile).configureEach {
    options.release = 17
}
~~~

Ví dụ Kotlin DSL:

~~~kotlin
java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

tasks.withType<JavaCompile>().configureEach {
    options.release = 17
}
~~~

Toolchain yêu cầu Gradle tìm JDK 17 phù hợp cho tác vụ. options.release = 17 đặt mức API/bytecode đích của Java compiler. Nếu chủ đích là dùng JDK mới hơn để build nhưng phát hành cho Java 17, có thể chọn toolchain mới hơn và vẫn đặt release 17, miễn compiler đó hỗ trợ release này.

### Toolchain và release giải quyết hai câu hỏi khác nhau

| Cấu hình | Câu hỏi được trả lời |
| --- | --- |
| Java toolchain | Dùng JDK/compiler nào để thực hiện build? |
| options.release | Artifact Java được biên dịch theo release/API nào? |
| Test launcher/runtime | Test thực sự chạy trên JDK nào? |

Không giả định rằng chỉ đặt toolchain là mọi task bên ngoài hoặc mọi plugin đều dùng cùng runtime. Kiểm tra cấu hình compile, test và execution của build.

## 11. CI: biên dịch theo release và chạy trên runtime đích

Một pipeline CI cho ứng dụng Java 17 nên tách các bước:

1. Chọn JDK/compiler được tổ chức hỗ trợ.
2. Biên dịch với --release 17 hoặc cấu hình tương đương của build tool.
3. Chạy unit test trên Java 17.
4. Chạy integration test trên Java 17 với các dependency thật hoặc môi trường mô phỏng phù hợp.
5. Kiểm tra dependency có yêu cầu runtime mới hơn hay không.
6. Kiểm tra artifact và class file version khi cần.
7. Đóng gói và triển khai bằng runtime Java 17 đã được xác định.

Nếu build bằng JDK 21 nhưng production dùng JDK 17, nên có job test thật trên JDK 17. Việc compiler chấp nhận --release 17 là một lớp bảo vệ quan trọng, không thay thế kiểm thử runtime.

### Ví dụ lệnh build trực tiếp trong CI

~~~bash
javac --release 17 -encoding UTF-8 -d out @sources.txt
java -cp out com.example.Main
~~~

File sources.txt chứa danh sách file source cần biên dịch, mỗi đường dẫn trên một dòng. Lệnh -encoding UTF-8 cấu hình encoding source riêng; nó không phải một phần của --release.

Trong CI thực tế, chạy hai lệnh trên bằng JDK 17 hoặc dùng runtime Java 17 riêng để xác nhận artifact.

## 12. Kiểm tra dependency và artifact

### Kiểm tra class file version

Dùng javap -verbose để xác nhận class ứng dụng có major version 61:

~~~bash
javap -verbose -classpath build/classes/java/main com.example.Main
~~~

Nếu dùng Maven, thư mục class output thường nằm dưới target/classes; với Gradle thường là build/classes/java/main. Đường dẫn cụ thể tùy cấu hình build.

### Phân tích dependency với jdeps

jdeps giúp xem dependency giữa class, package và module. Ví dụ:

~~~bash
jdeps --multi-release 17 --summary application.jar
~~~

Có thể dùng jdeps --jdk-internals để tìm một số tham chiếu tới internal API của JDK:

~~~bash
jdeps --jdk-internals application.jar
~~~

Các lệnh này hỗ trợ phân tích artifact, không chứng minh mọi code path runtime đều tương thích. Reflection theo tên chuỗi, dynamic loading và logic chỉ chạy trong một tình huống cụ thể có thể không được phát hiện đầy đủ bằng phân tích tĩnh.

### Kiểm tra yêu cầu phiên bản của thư viện

Trước khi thêm dependency:

- Đọc yêu cầu Java tối thiểu trong tài liệu của thư viện.
- Chọn artifact/version hỗ trợ Java 17.
- Kiểm tra các dependency bắc cầu.
- Chạy test trên runtime 17.
- Tránh chỉ dựa vào việc compile trên JDK mới thành công.

Một ứng dụng có thể được biên dịch với --release 17 nhưng vẫn không chạy được trên Java 17 nếu một thư viện đóng gói bytecode phiên bản cao hơn hoặc cần API mới hơn.

## 13. Những trường hợp dễ hiểu nhầm

### Build trên JDK 21 không có nghĩa ứng dụng cần Java 21

Nếu dùng JDK 21 với --release 17, source tuân thủ Java 17 và dependency tương thích, artifact có thể được thiết kế để chạy trên Java 17. Phiên bản JDK chạy compiler và phiên bản runtime tối thiểu của ứng dụng là hai thông tin khác nhau.

### Class file version 61 không bảo đảm API tương thích

Một class file có major version 61 chỉ cho biết định dạng bytecode phù hợp Java 17. Nó không chứng minh class không tham chiếu method chỉ có ở Java 21, đặc biệt nếu bytecode được tạo hoặc chỉnh sửa bằng công cụ khác, hoặc tham chiếu được nạp động.

### Compile thành công không chứng minh dependency chạy được

Compiler kiểm tra source và các type mà nó nhìn thấy. Nó không chạy toàn bộ code path, không thực hiện mọi reflective access và không xác nhận dịch vụ ngoài có tồn tại.

### --release không phải công cụ hạ bytecode

Không lấy một JAR Java 21 rồi chạy javac --release 17 để hạ JAR đó. --release áp dụng khi biên dịch source; nó không chuyển class file có major version 65 thành class file version 61, không thay API call và không backport dependency.

### Cờ compiler không thay thế chính sách runtime

Ứng dụng vẫn cần runtime được hỗ trợ, cấu hình heap/GC, certificate, native library và dependency phù hợp. --release chỉ giải quyết compatibility ở một phần của quá trình build.

## 14. Lỗi thường gặp và cách xử lý

| Tình huống | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Dùng -source 17 -target 17 nhưng runtime Java 17 ném NoSuchMethodError | Code đã tham chiếu API JDK mới hơn | Dùng --release 17 và biên dịch lại |
| Compiler báo không tìm thấy method với --release 17 | Method không thuộc API Java 17 | Dùng API tương thích hoặc nâng runtime tối thiểu |
| Java 17 báo UnsupportedClassVersionError | Dependency/class được biên dịch cho Java mới hơn | Chọn dependency build cho Java 17 hoặc thay version |
| javac báo không hỗ trợ release 17 | Compiler quá cũ | Cài JDK/compiler hỗ trợ release 17 |
| Build local chạy nhưng CI thất bại | JDK/toolchain hoặc dependency khác nhau | Ghi và cố định toolchain, kiểm tra phiên bản |
| Maven bỏ qua cấu hình release | Compiler plugin quá cũ hoặc property sai | Dùng plugin hỗ trợ release và kiểm tra effective POM |
| Gradle compile bằng JDK ngoài dự kiến | Chưa cấu hình toolchain hoặc task khác | Cấu hình toolchain và kiểm tra JavaCompile tasks |
| Compile thành công nhưng test Java 17 thất bại | Dependency hoặc code path runtime không tương thích | Chạy test trên JDK 17 và kiểm tra dependency |
| Cố đổi major version của JAR bằng công cụ bytecode | Chỉ sửa header, không chuyển API/bytecode | Biên dịch source/dependency từ đầu cho target phù hợp |
| API mới bị gọi qua reflection | Compiler không thấy lời gọi tĩnh | Kiểm tra chuỗi class/method và test runtime |
| Dùng --add-exports để mở rộng system API khi có --release | Hai mục tiêu cấu hình xung đột | Dùng API được hỗ trợ cho release đích |

## 15. Quy trình chọn API đích Java 17

Khi dự án cần chạy trên Java 17:

### Bước 1: Xác định runtime tối thiểu

Ghi rõ ứng dụng yêu cầu Java 17. Điều này ảnh hưởng lựa chọn cú pháp, API, dependency, build tool và môi trường triển khai.

### Bước 2: Chọn compiler/toolchain

Có thể dùng JDK 17 hoặc JDK mới hơn có hỗ trợ target release 17. Ghi rõ compiler vendor/version để build có thể tái lập.

### Bước 3: Cấu hình --release 17

Dùng trực tiếp:

~~~bash
javac --release 17 ...
~~~

Hoặc cấu hình tương đương trong Maven/Gradle. Tránh chỉ dùng -source và -target khi cần giới hạn API.

### Bước 4: Kiểm tra dependency

Chọn thư viện có yêu cầu Java tối thiểu tương thích với runtime 17. Kiểm tra class file version, API và module requirements khi cần.

### Bước 5: Test trên Java 17

Chạy unit test, integration test và smoke test trên runtime thực tế. Đặc biệt kiểm tra code dùng reflection, service loading, native library, serialization và API mới.

### Bước 6: Kiểm tra artifact

Dùng javap để xem major version khi cần. Dùng jdeps để phân tích module/internal API. Không coi một chỉ số duy nhất là bằng chứng đầy đủ.

### Bước 7: Giữ cấu hình trong CI

Đưa release target, toolchain, runtime test và dependency constraints vào cấu hình build được version control. Tránh phụ thuộc vào JDK ngẫu nhiên cài trên máy developer.

## 16. Nguyên tắc thực hành

Khi biên dịch và phát hành ứng dụng Java 17:

1. Dùng javac --release 17 để đồng bộ source language, bytecode target và API nền tảng.
2. Không chỉ dùng -source 17 -target 17 nếu build có thể chạy trên JDK mới hơn.
3. Hiểu rằng --release giới hạn API nền tảng theo Java 17, không backport API mới.
4. Phân biệt JDK chạy compiler, release target và JDK chạy ứng dụng.
5. Kiểm tra dependency bên thứ ba; --release không chuyển bytecode hoặc giới hạn API của mọi JAR.
6. Dùng Maven/Gradle compiler configuration có hỗ trợ release và cấu hình toolchain rõ ràng.
7. Chạy test trên Java 17 thực tế, không chỉ compile trên JDK mới.
8. Dùng javap để xem class version và jdeps để hỗ trợ phân tích dependency.
9. Không dựa vào JDK internals hoặc mở rộng system module để lách API boundary.
10. Ghi cấu hình compiler, runtime và dependency vào CI để bảo đảm build có thể tái lập.

--release 17 là cách rõ ràng để nói với compiler rằng sản phẩm phải tuân thủ ngôn ngữ, bytecode và API nền tảng của Java 17. Nó ngăn nhiều lỗi tương thích được phát hiện muộn ở runtime, đặc biệt khi build trên JDK mới hơn. Để bảo đảm ứng dụng thực sự chạy được trên Java 17, vẫn cần dependency phù hợp và kiểm thử trên đúng runtime đích.
