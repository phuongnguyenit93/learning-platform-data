# Biên dịch mẫu tài liệu bằng cú pháp Java 21 đã hoàn thiện

Một ví dụ Java trong tài liệu chỉ đáng tin khi người đọc có thể lấy mã nguồn, biên dịch bằng đúng mức Java được công bố và chạy để kiểm tra kết quả. Với tài liệu nhắm tới Java 21, hãy dùng `javac --release 21` để xác nhận cả cú pháp lẫn API của nền tảng Java 21.

Bài này tập trung vào các tính năng đã hoàn thiện trong Java 21. Mẫu tài liệu không nên trộn cú pháp Preview, API incubator hoặc API chỉ xuất hiện ở JDK mới hơn rồi gắn nhãn chung là “Java 21”.

## 1. Xác định JDK dùng để biên dịch

Trước khi biên dịch mẫu, kiểm tra phiên bản của cả compiler và runtime:

~~~bash
javac --version
java --version
~~~

Nếu mục tiêu là Java 21, môi trường CI nên cài JDK 21 và dùng chính JDK đó để biên dịch, chạy smoke test. Khi tổ chức build có nhiều JDK, có thể dùng một JDK mới hơn để biên dịch với `--release 21`, nhưng vẫn nên chạy test trên JDK 21 để xác nhận hành vi đúng với runtime mục tiêu.

Không dựa vào `PATH` mà không kiểm tra: máy phát triển có thể vô tình gọi một `javac` khác với `java` được dùng khi chạy ứng dụng. Ghi lại phiên bản công cụ trong log build để kết quả có thể tái hiện.

## 2. Dùng --release 21 thay vì chỉ đặt source và target

Lệnh biên dịch cơ bản:

~~~bash
javac --release 21 -encoding UTF-8 -d build/docs-classes docs/samples/Java21Examples.java
~~~

Ý nghĩa:

| Tùy chọn | Tác dụng |
|---|---|
| `--release 21` | Dùng quy tắc ngôn ngữ Java 21, tạo class file cho Java 21 và giới hạn API theo nền tảng Java 21 |
| `-encoding UTF-8` | Đọc source theo UTF-8, tránh phụ thuộc encoding mặc định của máy |
| `-d build/docs-classes` | Ghi file `.class` vào thư mục output đã chỉ định |
| Đường dẫn `.java` | Source file cần biên dịch |

`--release 21` bao gồm cả ba yêu cầu về source language, class-file target và API nền tảng. Chỉ dùng `-source 21 -target 21` không tự giới hạn API mà compiler nhìn thấy; source vẫn có thể vô tình gọi API chỉ tồn tại ở JDK đang cài.

Không kết hợp `--release` với `-source` hoặc `-target` trong cùng lệnh. Nếu cần biên dịch cho Java 21, đặt một giá trị `--release 21` làm chuẩn duy nhất.

## 3. Một ví dụ hoàn chỉnh dùng tính năng Java 21 đã hoàn thiện

Record Patterns và Pattern Matching for switch là hai tính năng ngôn ngữ được hoàn thiện trong Java 21. Có thể dùng chúng mà không bật Preview.

Tạo file `docs/samples/Java21Examples.java`:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

sealed interface Shape permits Circle, Rectangle {
}

record Circle(double radius) implements Shape {
}

record Rectangle(double width, double height) implements Shape {
}

public class Java21Examples {

    static double area(Shape shape) {
        return switch (shape) {
            case Circle(double radius) ->
                Math.PI * radius * radius;
            case Rectangle(double width, double height) ->
                width * height;
        };
    }

    public static void main(String[] args) throws Exception {
        System.out.printf("Area: %.2f%n", area(new Circle(2)));

        List<String> names =
            new ArrayList<>(List.of("Lan", "Minh"));

        names.addFirst("An");
        System.out.println("Forward: " + names);
        System.out.println("Reverse: " + names.reversed());

        try (var executor =
                 Executors.newVirtualThreadPerTaskExecutor()) {
            Future<String> result =
                executor.submit(() -> "Java 21 virtual thread");

            System.out.println(result.get());
        }
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac --release 21 -encoding UTF-8 -Xlint:all -d build/docs-classes docs/samples/Java21Examples.java
java -cp build/docs-classes Java21Examples
~~~

Kết quả mong đợi:

~~~text
Area: 12.57
Forward: [An, Lan, Minh]
Reverse: [Minh, Lan, An]
Java 21 virtual thread
~~~

Ví dụ này dùng:

- Sealed interface và record để mô hình hóa tập kiểu `Shape` hữu hạn.
- Record pattern trong từng nhánh `switch`.
- Switch expression exhaustive nhờ compiler biết các kiểu được phép của sealed hierarchy.
- Sequenced Collections qua `addFirst` và `reversed`.
- Virtual thread qua `Executors.newVirtualThreadPerTaskExecutor()`.

Đây đều là cú pháp hoặc API đã hoàn thiện trong Java 21. `--release 21` kiểm tra rằng ví dụ không vô tình phụ thuộc vào API của JDK mới hơn.

## 4. Phân biệt tính năng final, Preview và incubator trong Java 21

Không phải mọi tính năng được giới thiệu trong JDK 21 đều có cùng trạng thái. Trước khi đưa một ví dụ vào tài liệu, kiểm tra JEP và Java SE 21 documentation để biết tính năng đó đã final hay mới ở giai đoạn thử nghiệm.

| Tính năng trong Java 21 | Trạng thái trong Java 21 | Dùng trong ví dụ Java 21 ổn định? |
|---|---|---|
| Record Patterns (JEP 440) | Final | Có |
| Pattern Matching for switch (JEP 441) | Final | Có |
| Virtual Threads (JEP 444) | Final API | Có |
| Sequenced Collections (JEP 431) | Final API | Có |
| Key Encapsulation Mechanism API (JEP 452) | Final API | Có |
| String Templates (JEP 430) | Preview | Không |
| Unnamed Patterns and Variables (JEP 443) | Preview | Không |
| Unnamed Classes and Instance Main Methods (JEP 445) | Preview | Không |
| Foreign Function & Memory API (JEP 442) | Preview lần thứ ba | Không |
| Scoped Values (JEP 446) | Preview | Không |
| Structured Concurrency (JEP 453) | Preview | Không |
| Vector API (JEP 448) | Incubator | Không |

Ví dụ, trong Java 21, cú pháp Record Pattern và Pattern Matching for switch đã được hoàn thiện:

~~~java
return switch (value) {
    case Circle(double radius) -> radius * radius * Math.PI;
    case Rectangle(double width, double height) -> width * height;
};
~~~

Trong khi đó, String Templates, unnamed patterns và unnamed variables vẫn là Preview trong Java 21. Không đưa chúng vào ví dụ được mô tả là cú pháp Java 21 final.

Trạng thái Preview gắn với từng bản phát hành. Một tính năng từng là Preview có thể được hoàn thiện, tiếp tục Preview hoặc bị rút khỏi một bản JDK sau đó. Vì vậy, không sao chép ví dụ Preview từ một JDK khác rồi giả định nó là cú pháp Java 21 ổn định.

## 5. Preview cần compiler và runtime cùng bản phát hành

Đối với mục tiêu học hoặc kiểm thử Preview riêng, Java 21 yêu cầu dùng compiler JDK 21 với `--enable-preview` và chạy bằng runtime JDK 21 cũng có cờ này.

~~~bash
javac --enable-preview --release 21 PreviewExample.java
java --enable-preview PreviewExample
~~~

Không dùng các lệnh trên cho source set chứa ví dụ Java 21 final. Preview có thể thay đổi giữa các release và class được biên dịch bằng Preview của một release không được bảo đảm chạy trên release khác.

Nếu tài liệu có mục giải thích lịch sử Preview, hãy để các ví dụ đó trong thư mục hoặc profile riêng, ghi rõ release và trạng thái. Pipeline biên dịch ví dụ final nên chạy mà không có `--enable-preview`; như vậy compiler có thể phát hiện ngay cú pháp Preview bị đưa nhầm vào.

## 6. Biên dịch nhiều source file và dependency

Ví dụ tài liệu có thể gồm nhiều class. Đưa tất cả source cần thiết vào cùng lệnh:

~~~bash
javac --release 21 -encoding UTF-8 -d build/docs-classes docs/samples/Order.java docs/samples/OrderService.java docs/samples/OrderExample.java
~~~

Nếu source dùng thư viện ngoài, cung cấp dependency qua classpath:

~~~bash
javac --release 21 --class-path "lib/dependency.jar" -d build/docs-classes docs/samples/ExternalApiExample.java
~~~

Classpath dùng dấu phân cách theo hệ điều hành: dấu chấm phẩy trên Windows, dấu hai chấm trên Linux/macOS. Với nhiều dependency, dùng đúng runtime/compile classpath của dự án thay vì chỉ thêm một JAR cho đến khi compiler hết báo lỗi.

Với ứng dụng module hóa, dùng module path và module source path:

~~~bash
javac --release 21 --module-path lib --module-source-path src -d build/modules -m com.example.app
~~~

Không đặt JAR module vào classpath chỉ để làm mất lỗi module resolution. Cần biên dịch theo cùng mô hình classpath hoặc module path mà ứng dụng thật sẽ sử dụng.

## 7. Quản lý danh sách mẫu bằng javac argument file

Khi có nhiều ví dụ, có thể lưu danh sách source trong một argument file:

`docs/samples/sources.txt`:

~~~text
docs/samples/Java21Examples.java
docs/samples/SequencedCollectionExample.java
docs/samples/VirtualThreadExample.java
~~~

Biên dịch toàn bộ danh sách:

~~~bash
javac --release 21 -encoding UTF-8 -Xlint:all -d build/docs-classes @docs/samples/sources.txt
~~~

Argument file giúp lệnh build ngắn và ổn định khi danh sách ví dụ dài. Có thể đặt file này trong repository để reviewer biết chính xác source nào được kiểm tra.

Nếu đường dẫn có khoảng trắng, dùng quy tắc quoting của javac argument file. Tránh tạo danh sách source bằng một lệnh shell phụ thuộc riêng vào PowerShell, Bash hoặc glob expansion khi cần pipeline chạy trên nhiều hệ điều hành.

## 8. Tổ chức ví dụ sao cho có thể biên dịch tự động

Một code block trong Markdown thường là một đoạn trích, không phải compilation unit hoàn chỉnh. Nó có thể thiếu import, class declaration, interface, record hoặc method bao quanh. Vì thế, compiler không thể xác minh mọi code fence chỉ bằng cách truyền Markdown cho `javac`.

Nên tổ chức source fixture riêng:

~~~text
docs/
  samples/
    Java21Examples.java
    SequencedCollectionExample.java
    VirtualThreadExample.java
    sources.txt
  guide/
    java21-language.md
    java21-concurrency.md
~~~

Nguyên tắc tổ chức:

- Mỗi ví dụ độc lập có source file hoàn chỉnh, tên file khớp public class.
- Nếu ví dụ phụ thuộc ví dụ khác, ghi rõ dependency và biên dịch chúng cùng nhau.
- Code block trong tài liệu phải được đồng bộ với source fixture đã biên dịch.
- Với snippet chỉ là một phần của method, tạo wrapper nhỏ trong fixture để compiler kiểm tra đúng cú pháp và kiểu.
- Không dùng một class fixture khổng lồ chứa nhiều ví dụ không liên quan; khi lỗi xuất hiện sẽ khó xác định đoạn nào gây ra.
- Không để các ví dụ cùng tên class nằm chung package nếu chúng được biên dịch cùng một lần.

Có thể dùng Javadoc `{@snippet}` để hiển thị đoạn mã từ source file hoặc vùng được đánh dấu. Tuy nhiên, việc Javadoc hiển thị snippet không thay thế bước biên dịch source fixture. Hãy để CI biên dịch file nguồn mà snippet tham chiếu.

## 9. Bật compiler diagnostics cho mẫu tài liệu

Để phát hiện lỗi và warning sớm, thêm các tùy chọn kiểm tra:

~~~bash
javac --release 21 -encoding UTF-8 -Xlint:all -d build/docs-classes @docs/samples/sources.txt
~~~

`-Xlint:all` bật nhiều nhóm cảnh báo của compiler, giúp phát hiện raw type, unchecked operation, deprecation và các vấn đề khác tùy source.

Khi bộ ví dụ đã xử lý hết warning có chủ đích, có thể thêm `-Werror` để biến warning thành lỗi build:

~~~bash
javac --release 21 -encoding UTF-8 -Xlint:all -Werror -d build/docs-classes @docs/samples/sources.txt
~~~

Nếu tài liệu cố ý minh họa một API deprecated hoặc một cảnh báo cụ thể, hãy đặt ví dụ đó trong fixture riêng và mô tả rõ lý do. Không tắt toàn bộ lint cho mọi ví dụ chỉ vì một snippet có warning.

## 10. Cấu hình Gradle cho source và ví dụ tài liệu

Nếu dự án dùng Gradle, khai báo Java toolchain 21 để compiler và task Java dùng đúng JDK:

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
    options.compilerArgs += ['-Xlint:all']
}
~~~

Đặt ví dụ cần biên dịch tự động trong `src/test/java` hoặc một source set riêng. Nếu dùng `src/test/java`, task `compileTestJava` sẽ biên dịch chúng cùng test source; có thể chạy task này trong CI mà không cần thực thi test.

Toolchain chọn JDK để chạy compiler. `options.release = 21` xác định source/API/bytecode mục tiêu. Hai cấu hình này bổ sung cho nhau và giúp build không phụ thuộc JDK mặc định trên máy developer.

Không nên chỉ đặt `sourceCompatibility` và `targetCompatibility` rồi cho rằng API đã được khóa ở Java 21. Với Gradle, ưu tiên `options.release` cho mục tiêu Java SE.

## 11. Cấu hình Maven cho ví dụ tài liệu

Với Maven Compiler Plugin có hỗ trợ `maven.compiler.release`, đặt release và encoding thống nhất trong POM:

~~~xml
<properties>
    <maven.compiler.release>21</maven.compiler.release>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
</properties>
~~~

Đặt các ví dụ cần compile vào `src/test/java` hoặc source root/profile chuyên biệt. Có thể kiểm tra biên dịch source chính và test source mà chưa chạy test:

~~~bash
mvn test-compile
~~~

Pin phiên bản Maven Compiler Plugin được dự án hỗ trợ trong `pluginManagement` hoặc phần `plugins` để các môi trường CI và developer dùng cùng hành vi compiler. Đảm bảo Maven chạy trên JDK phù hợp hoặc cấu hình toolchain Maven để chọn JDK 21.

Không cần chạy toàn bộ integration test mỗi lần sửa một đoạn tài liệu nếu mục tiêu chỉ là xác minh cú pháp; tuy nhiên, các ví dụ có hành vi runtime vẫn cần smoke test theo lịch hoặc trong pipeline thích hợp.

## 12. Chạy smoke test sau khi biên dịch

Biên dịch thành công chỉ chứng minh source hợp lệ theo compiler và API mục tiêu. Nó không chứng minh kết quả runtime đúng, ví dụ có thể sai dữ liệu, sai thứ tự, ném exception hoặc không đóng tài nguyên.

Sau khi compile, chạy các ví dụ có thể thực thi:

~~~bash
java -cp build/docs-classes Java21Examples
~~~

Với ví dụ có output xác định, so sánh output thực tế với output được ghi trong tài liệu. Với ví dụ phụ thuộc thời gian, network hoặc concurrency, kiểm tra invariant và điều kiện kết thúc thay vì so sánh thứ tự thread hoặc thời gian tuyệt đối.

Nếu ví dụ cần database, HTTP server hoặc filesystem đặc biệt, dùng test fixture local và dữ liệu giả lập có thể tái tạo. Không để việc compile documentation phụ thuộc vào dịch vụ production hoặc credential của developer.

Có thể kiểm tra bytecode target bằng `javap`:

~~~bash
javap -verbose build/docs-classes/Java21Examples.class
~~~

Class file của Java 21 có major version 65. Kiểm tra này hữu ích khi cần xác minh artifact không bị build nhầm với target của JDK đang cài.

## 13. Pipeline CI đề xuất

Một job kiểm tra ví dụ tài liệu có thể gồm các bước:

~~~text
Checkout source
      |
      v
Select JDK 21 toolchain
      |
      v
Compile documentation fixtures
      |
      v
Fail on compiler warnings (if baseline is clean)
      |
      v
Run deterministic smoke examples
      |
      v
Compare expected output / assertions
      |
      v
Publish compile and test report
~~~

Các bước kiểm tra nên được giữ tách bạch:

1. **Compile:** mọi fixture được biên dịch với `--release 21`, không bật Preview.
2. **Lint:** ghi nhận warning; chỉ bật `-Werror` khi baseline đã sạch.
3. **Smoke test:** chạy các ví dụ có output hoặc invariant có thể kiểm tra.
4. **Review:** xác nhận code block trong tài liệu khớp fixture.
5. **Report:** lưu JDK version, command, log và kết quả để reviewer có thể tái hiện.

Khi tài liệu thay đổi, CI cần biên dịch lại các fixture liên quan. Khi dependency thay đổi, chạy lại toàn bộ fixture phụ thuộc vào dependency đó.

## 14. Lỗi thường gặp khi biên dịch ví dụ Java 21

| Lỗi | Nguyên nhân | Cách xử lý |
|---|---|---|
| `invalid source release: 21` | Compiler quá cũ, không hỗ trợ release 21 | Chọn JDK 21 trở lên |
| `class file has wrong version` | Dùng class được biên dịch cho JDK mới hơn runtime mục tiêu | Biên dịch dependency tương thích hoặc nâng runtime |
| `cannot find symbol` | Thiếu source hoặc dependency trong classpath/module path | Bổ sung đúng source/dependency |
| `package ... does not exist` | Dependency chưa được đưa vào compiler path hoặc module chưa được resolve | Kiểm tra classpath/module path |
| Preview feature disabled | Source đang dùng cú pháp Preview | Thay bằng cú pháp final hoặc tách ví dụ Preview riêng |
| API không tồn tại trong `--release 21` | Code dùng API được thêm sau Java 21 | Dùng API có trong Java 21 hoặc thay đổi target nếu mục tiêu đã đổi |
| Public class phải ở file cùng tên | Fixture chứa public class với tên file không khớp | Tách file hoặc đổi tên class |
| Ví dụ không chạy dù compile thành công | Thiếu resource/runtime dependency hoặc lỗi logic | Thêm smoke test và fixture cần thiết |

Không sửa lỗi bằng cách xóa `--release 21` hoặc chuyển sang compiler JDK mới nhất mà không giới hạn API. Điều đó có thể làm ví dụ biên dịch được trên máy tác giả nhưng thất bại trên Java 21.

## 15. Checklist biên dịch mẫu tài liệu Java 21

- [ ] Xác nhận compiler và runtime mục tiêu là JDK 21.
- [ ] Dùng `javac --release 21` cho mọi fixture Java 21 final.
- [ ] Đặt encoding UTF-8 rõ ràng.
- [ ] Không trộn `--release` với `-source` hoặc `-target`.
- [ ] Dùng Record Patterns và Pattern Matching for switch theo cú pháp final của Java 21.
- [ ] Chỉ dùng API final có trong Java 21 như Virtual Threads, Sequenced Collections và KEM API.
- [ ] Không đưa String Templates, unnamed patterns hoặc các API Preview vào ví dụ final.
- [ ] Tách ví dụ Preview/incubator khỏi source set ổn định và ghi rõ release nếu có tài liệu riêng.
- [ ] Lưu source fixture hoàn chỉnh cho code block cần biên dịch.
- [ ] Cung cấp đầy đủ classpath hoặc module path.
- [ ] Bật `-Xlint:all` và cân nhắc `-Werror` khi baseline sạch.
- [ ] Chạy smoke test cho ví dụ có output hoặc hành vi cần xác minh.
- [ ] Kiểm tra bytecode target khi cần bằng `javap -verbose`.
- [ ] Chạy lại compile fixtures trong CI mỗi khi source hoặc dependency liên quan thay đổi.

## Tài liệu tham khảo chính thức

- [Java SE 21 Tool Specifications — javac](https://docs.oracle.com/en/java/javase/21/docs/specs/man/javac.html)
- [Java SE 21 — Java Language Changes](https://docs.oracle.com/en/java/javase/21/language/java-language-changes-release.html)
- [Java SE 21 — Java Language Changes Summary](https://docs.oracle.com/en/java/javase/21/language/java-language-changes-summary.html)
- [Java SE 21 — Preview Language and VM Features](https://docs.oracle.com/en/java/javase/21/language/preview-language-and-vm-features.html)
- [Java SE 21 — Preview API List](https://docs.oracle.com/en/java/javase/21/docs/api/preview-list.html)
- [Oracle Java 21 — Significant Changes in JDK 21](https://docs.oracle.com/en/java/javase/21/migrate/significant-changes-jdk-release.html)
- [Oracle Java 21 — Virtual Threads](https://docs.oracle.com/en/java/javase/21/core/virtual-threads.html)
- [Oracle Java 21 — Sequenced Collections](https://docs.oracle.com/en/java/javase/21/core/creating-sequenced-collections-sets-and-maps.html)
- [Gradle — Building Java Projects](https://docs.gradle.org/current/userguide/building_java_projects.html)
- [Maven Compiler Plugin — Setting the --release of the Java Compiler](https://maven.apache.org/plugins/maven-compiler-plugin/examples/set-compiler-release.html)


