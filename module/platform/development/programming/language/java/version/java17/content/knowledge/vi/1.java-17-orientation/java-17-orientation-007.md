# Cách tra đặc tả ngôn ngữ, API Docs và ghi chú phát hành trong Java 17

Khi làm việc với Java 17, tìm thấy một đoạn code chạy được chưa đủ để kết luận rằng nó đúng, ổn định hoặc có thể sử dụng trên mọi môi trường Java 17. Cần biết **tìm câu trả lời ở tài liệu nào, đọc đúng phiên bản nào và phân biệt quy định của ngôn ngữ với cam kết của thư viện**. Ba nguồn tra cứu quan trọng nhất là **Java Language Specification (JLS)**, **Java SE/JDK API Documentation (Javadoc)** và **JDK Release Notes**. Tài liệu về **JEP (JDK Enhancement Proposal)** giải thích bối cảnh thiết kế và tiến trình đưa tính năng vào JDK.

Bài này tập trung vào cách tra cứu hiện còn hữu ích khi phát triển, duy trì hoặc nâng cấp ứng dụng chạy trên Java 17. Ví dụ đều dùng API và cú pháp có sẵn trong Java 17; những tính năng ở trạng thái *preview* được chỉ rõ.

## 1. Chọn đúng nguồn cho đúng câu hỏi

| Khi bạn cần trả lời câu hỏi… | Nguồn nên mở trước | Nguồn bổ sung khi cần |
| --- | --- | --- |
| `sealed`, `record`, generic, overload hoặc `switch` được phép viết và hoạt động theo quy tắc nào? | **JLS của Java SE 17** | Hướng dẫn ngôn ngữ, JEP tương ứng |
| Compiler sinh và JVM xử lý class file, bytecode, liên kết hoặc nạp lớp thế nào? | **Java Virtual Machine Specification (JVMS) 17** | Tài liệu JVM và công cụ JDK |
| `Stream.toList()`, `List.of()`, `Files.readString()` trả về gì, ném ngoại lệ nào, có sửa được kết quả không? | **Java SE 17 API Docs (Javadoc)** | JLS khi vấn đề liên quan cú pháp/kiểu dữ liệu |
| Tính năng được đề xuất để làm gì, được phát hành ở bản nào, có phải preview không? | **JEP và danh sách tính năng của JDK 17** | JLS/API Docs của Java 17 để xác nhận hành vi chính thức |
| Nâng cấp từ JDK cũ bị lỗi, tùy chọn JVM thay đổi, có thay đổi tương thích hoặc bảo mật nào? | **Release Notes theo đúng bản JDK** | Migration Guide, JEP, thông báo của nhà cung cấp JDK |
| Một hành vi phụ thuộc bản vá `17.0.x`, hệ điều hành hoặc nhà cung cấp JDK? | **Release Notes/advisory của bản phân phối đang dùng** | JDK bug tracker và tài liệu triển khai tương ứng |

**Nguyên tắc ưu tiên:** JLS/JVMS xác định các quy tắc đặc tả; API Docs xác định hợp đồng công khai của thư viện; Release Notes ghi thay đổi của bản phát hành. JEP giải thích mục tiêu và thiết kế, nhưng một ý tưởng trong JEP không tự động trở thành cú pháp hoặc API có thể dùng ở Java 17. Bài blog hoặc câu trả lời diễn đàn là gợi ý để tìm từ khóa, không thay thế các nguồn trên.

## 2. Ghim phiên bản trước khi tra cứu

Mỗi trang tài liệu phải khớp với **phiên bản mục tiêu của chương trình**, không nhất thiết khớp với phiên bản Java mới nhất đang được công bố. Đối với dự án chạy Java 17, hãy bắt đầu từ các URL có `se17` hoặc `/java/javase/17/`.

```bash
java -version
javac -version
java -XshowSettings:properties -version
```

Hai lệnh đầu cho biết Java runtime và compiler đang được chọn qua môi trường hiện tại; chúng có thể trỏ tới hai bản cài khác nhau. Lệnh thứ ba giúp xem các thông tin như `java.home`, `java.vendor`, `java.version`. Nếu ứng dụng chạy trong container, CI hoặc server, hãy kiểm tra **ngay trên môi trường đó** thay vì chỉ kiểm tra máy lập trình.

Ví dụ:

```text
openjdk version "17.0.x" ...
javac 17.0.x
```

Trong chuỗi phiên bản `17.0.x`, **17** là dòng phát hành ngôn ngữ/nền tảng cần tra cứu; **17.0.x** chỉ rõ bản cập nhật thực tế. Bản cập nhật có thể sửa lỗi, bảo mật, chứng chỉ, dữ liệu múi giờ và hành vi vận hành mà không đưa cú pháp mới từ các bản Java đời sau vào Java 17.

Nếu build bằng JDK mới hơn nhưng ứng dụng phải chạy trên Java 17, dùng tùy chọn compiler:

```bash
javac --release 17 Example.java
```

`--release 17` yêu cầu compiler kiểm tra cú pháp và các API nền tảng mà Java 17 hỗ trợ; chỉ đặt `-source 17` riêng lẻ chưa kiểm soát đầy đủ việc vô tình sử dụng API mới hơn. Trong dự án Maven/Gradle, cấu hình mức `release` tương đương trong công cụ build và kiểm tra JDK dùng khi chạy thực tế.

### Bộ liên kết tra cứu chính thức

| Tài liệu | Địa chỉ |
| --- | --- |
| Java Language Specification, Java SE 17 | <https://docs.oracle.com/javase/specs/jls/se17/html/index.html> |
| Java Virtual Machine Specification, Java SE 17 | <https://docs.oracle.com/javase/specs/jvms/se17/html/index.html> |
| Java SE 17 & JDK 17 API Specification | <https://docs.oracle.com/en/java/javase/17/docs/api/index.html> |
| Các hướng dẫn và đặc tả công cụ JDK 17 | <https://docs.oracle.com/en/java/javase/17/docs/specs/index.html> |
| Thay đổi ngôn ngữ trong Java SE 17 | <https://docs.oracle.com/en/java/javase/17/language/java-language-changes-release.html> |
| Danh sách JEP của dự án JDK 17 | <https://openjdk.org/projects/jdk/17/> |
| JDK 17 Release Notes ban đầu | <https://www.oracle.com/java/technologies/javase/17-relnote-issues.html> |
| Danh mục Release Notes các bản cập nhật JDK 17 của Oracle | <https://www.oracle.com/java/technologies/javase/17u-relnotes.html> |
| Hướng dẫn di chuyển lên JDK 17 | <https://docs.oracle.com/en/java/javase/17/migrate/index.html> |

Đây là các điểm bắt đầu cố định theo Java 17. Với bản phân phối không phải Oracle JDK, cũng cần xem thông tin bản vá và hỗ trợ từ nhà cung cấp đang sử dụng; không mặc định mọi bản phân phối có cùng lịch cập nhật.

## 3. Tra Java Language Specification (JLS)

### 3.1. JLS trả lời điều gì?

JLS là đặc tả quy tắc của **mã nguồn Java**, ví dụ:

- Cú pháp hợp lệ của khai báo lớp, interface, record, biểu thức và câu lệnh.
- Quy tắc phạm vi tên, khả năng truy cập, kế thừa, kiểu dữ liệu, ép kiểu và suy luận kiểu.
- Cách chọn phương thức khi overload, quy tắc override và kiểm tra lỗi ở thời điểm biên dịch.
- Ý nghĩa của biểu thức, luồng điều khiển, khởi tạo đối tượng và xử lý ngoại lệ.

JLS không phải danh mục hàm thư viện. Muốn biết `List.copyOf()` có cho phép `null` hay không thì cần tra API Docs; muốn biết một biểu thức generic có được compiler chấp nhận hay không mới là câu hỏi điển hình dành cho JLS.

### 3.2. Cách đọc và dẫn chiếu một điều khoản

1. Mở **JLS SE 17**, tìm từ khóa trong mục lục hoặc dùng chức năng tìm trong trang.
2. Chọn chương liên quan: *Types, Values, and Variables*; *Conversions and Contexts*; *Classes*; *Interfaces*; *Expressions*; hoặc *Statements*.
3. Đi tới tiểu mục có số như `§8.1.1.2`. Đọc cả định nghĩa, hạn chế và các liên kết tham chiếu tới điều khoản khác.
4. Phân biệt câu quy định (*compile-time error*, *must*, *may*) với ví dụ minh họa; nếu cần kiểm chứng, tạo một ví dụ nguồn nhỏ với `javac --release 17`.
5. Khi ghi chú hoặc trao đổi kỹ thuật, dẫn cả **phiên bản lẫn điều khoản**, chẳng hạn “JLS Java SE 17, §8.1.1.2”.

Các liên kết hữu ích cho Java 17:

- [JLS §8.1.1.2 — `sealed`, `non-sealed` và `final` classes](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.1.1.2).
- [JLS §8.1.6 — Permitted Direct Subclasses](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.1.6).
- [JLS §8.10 — Record Classes](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.10).
- [JLS §15.12 — Method Invocation Expressions](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.12) khi cần hiểu overload và lựa chọn phương thức.

### 3.3. Ví dụ: `sealed` kết hợp `record` có hợp lệ trong Java 17 không?

Trong Java 17, **sealed classes/interfaces là tính năng chính thức** ([JEP 409](https://openjdk.org/jeps/409)); `record` cũng đã chính thức từ Java 16 và tiếp tục dùng ổn định trên Java 17. Có thể viết một file `ShapeDemo.java` như sau:

```java
sealed interface Shape permits Circle, Rectangle {}

record Circle(double radius) implements Shape {}
record Rectangle(double width, double height) implements Shape {}

public class ShapeDemo {
    static double area(Shape shape) {
        if (shape instanceof Circle circle) {
            return Math.PI * circle.radius() * circle.radius();
        }
        if (shape instanceof Rectangle rectangle) {
            return rectangle.width() * rectangle.height();
        }
        throw new IllegalArgumentException("Unsupported shape");
    }

    public static void main(String[] args) {
        System.out.println(area(new Circle(2)));
    }
}
```

```bash
javac --release 17 ShapeDemo.java
java ShapeDemo
```

Để hiểu **vì sao** đoạn code hợp lệ, lần theo ba câu hỏi: `sealed` giới hạn các kiểu con trực tiếp như thế nào (JLS §8.1.1.2, §8.1.6 và phần interface tương ứng); `record` tự sinh những thành phần nào (JLS §8.10); `instanceof` với biến pattern hoạt động ra sao (mục về `instanceof` trong JLS). Không suy từ ví dụ này rằng mọi dạng pattern matching đều đã ổn định trong Java 17.

### 3.4. Khi nào mở JVMS thay vì JLS?

Nếu câu hỏi chuyển từ **mã nguồn** sang **bytecode và máy ảo**, dùng JVMS: cấu trúc class file, quy tắc xác minh bytecode, nạp/liên kết/khởi tạo lớp, bộ lệnh JVM. Chẳng hạn, có thể xem cấu trúc file biên dịch bằng:

```bash
javap -v ShapeDemo
```

Kết quả `javap` giúp quan sát class file; **JVMS 17** mới là nguồn đối chiếu các cấu trúc, trường và opcode. Không suy ra hợp đồng API chỉ từ bytecode hay từ chi tiết hiện thực của một JVM cụ thể.

## 4. Tra Java SE 17 API Docs (Javadoc)

### 4.1. Đi từ module tới package, lớp và phương thức

Trang Javadoc Java 17 có hệ thống điều hướng theo **Module → Package → Class/Interface → Field/Constructor/Method**. Ví dụ, để tra `Stream.toList()`:

1. Mở [Java SE 17 API Specification](https://docs.oracle.com/en/java/javase/17/docs/api/index.html).
2. Tìm `Stream`, chọn `java.util.stream.Stream` trong module `java.base`.
3. Trên [trang `Stream`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/Stream.html), tìm phương thức `toList()` trong *Method Summary* hoặc phần mô tả chi tiết.
4. Đọc **câu mô tả hợp đồng** và những mục như *Returns*, *Parameters*, *Throws*, *Since*, *API Note*, *Implementation Requirements*, *Implementation Note*.
5. Nếu có overload, chọn đúng chữ ký phương thức; hai hàm cùng tên có thể khác về tham số, ngoại lệ và kết quả.

Khi tra một lớp, cũng nên đọc phần mô tả đầu trang: các ràng buộc áp dụng cho toàn bộ lớp thường không được nhắc lại đầy đủ ở từng phương thức. Xem `@since` để biết API có từ phiên bản nào, nhưng **`Since: 16` không có nghĩa API bị loại ở Java 17**. Đọc đúng phần *Deprecated* và trạng thái *for removal* nếu cần đánh giá vòng đời API.

### 4.2. Đọc hợp đồng API thay vì đoán theo tên phương thức

Ví dụ, [Javadoc Java 17 của `Stream.toList()`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/Stream.html) ghi rõ:

- Kết quả là một `List` chứa phần tử của stream theo thứ tự gặp nếu stream có thứ tự đó.
- Danh sách trả về **không thể sửa** (*unmodifiable*); gọi `add`, `remove`, `set`… sẽ ném `UnsupportedOperationException`.
- Không có cam kết về lớp triển khai cụ thể hay khả năng serialization.
- API này có từ **Java 16** và dùng được trong **Java 17**.

```java
import java.util.ArrayList;
import java.util.List;
import java.util.stream.Collectors;
import java.util.stream.Stream;

public class ApiDocsExample {
    public static void main(String[] args) {
        List<String> readOnly = Stream.of("An", "Binh").toList();
        System.out.println(readOnly); // [An, Binh]

        // readOnly.add("Chi"); // UnsupportedOperationException khi chạy

        List<String> editable = Stream.of("An", "Binh")
                .collect(Collectors.toCollection(ArrayList::new));
        editable.add("Chi");
        System.out.println(editable); // [An, Binh, Chi]
    }
}
```

```bash
javac --release 17 ApiDocsExample.java
java ApiDocsExample
```

Điểm cần phân biệt: `Stream.toList()` **cam kết** danh sách không thể sửa; `Collectors.toList()` **không cam kết** kiểu danh sách hoặc tính có thể sửa; `Collectors.toCollection(ArrayList::new)` cho phép yêu cầu rõ một `ArrayList` có thể sửa. Đây là lý do không nên dựa vào việc “trên máy tôi phương thức trả `ArrayList`” để viết chương trình. Tra thêm [Javadoc của `Collectors`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/Collectors.html) để so sánh hợp đồng từng collector.

### 4.3. Các nhãn thường gặp trong Javadoc

| Nhãn/mục | Cách đọc đúng |
| --- | --- |
| *Type Parameters*, *Parameters* | Ý nghĩa và điều kiện của tham số kiểu hoặc tham số phương thức. |
| *Returns* | Giá trị trả về và các ràng buộc được bảo đảm. |
| *Throws* | Ngoại lệ được đặc tả; đừng cho rằng chỉ những ngoại lệ được liệt kê mới có thể phát sinh từ mọi lỗi runtime. |
| *Since* | Phiên bản đầu tiên cung cấp API; kiểm tra với phiên bản mục tiêu. |
| *Deprecated* / *for removal* | API không còn được khuyến khích hoặc được dự kiến loại bỏ; cần xem thông tin cụ thể về thay thế và tương thích. |
| *API Note* | Lời khuyên về cách sử dụng API, thường kèm ví dụ. |
| *Implementation Requirements* | Yêu cầu đối với cách triển khai API nếu mục đó xuất hiện. |
| *Implementation Note* | Thông tin về cách triển khai, không tự động trở thành hợp đồng chung cho mọi bản triển khai. |

**Chú ý:** Một kết quả là *unmodifiable* không đồng nghĩa đối tượng chứa trong đó là bất biến; thuộc tính bất biến của các phần tử và việc những nguồn dữ liệu khác thay đổi được hay không phải xem hợp đồng riêng. Tương tự, tên phương thức có chữ `copyOf` hoặc `of` không đủ để kết luận cách xử lý `null`, trùng lặp hay thứ tự phần tử.

## 5. Tra JEP và phân biệt tính năng chính thức với preview

**JEP** trình bày động cơ, mục tiêu, phương án thiết kế và lịch sử đề xuất thay đổi JDK. Khi đọc, kiểm tra tối thiểu **số JEP, trạng thái, release mục tiêu và tính năng đã chính thức hay còn preview/incubator**. Sau đó xác nhận tính năng ở JLS hoặc API Docs của Java 17.

Các trường hợp dễ nhầm:

| Tính năng | Trạng thái khi dùng Java 17 | Tài liệu cần tra |
| --- | --- | --- |
| `sealed` class/interface | **Chính thức trong Java 17** | [JEP 409](https://openjdk.org/jeps/409), JLS SE 17 |
| `record` | **Chính thức từ Java 16**, vẫn dùng được trong Java 17 | [JEP 395](https://openjdk.org/jeps/395), JLS §8.10 |
| Pattern matching cho `instanceof` | **Chính thức từ Java 16**, dùng được trong Java 17 | [JEP 394](https://openjdk.org/jeps/394), JLS SE 17 |
| Pattern matching cho `switch` | **Preview trong Java 17**; không phải cú pháp ổn định mặc định của Java 17 | [JEP 406](https://openjdk.org/jeps/406), tài liệu ngôn ngữ Java 17 |
| Enhanced Pseudo-Random Number Generators | API chính thức có trong Java 17 | [JEP 356](https://openjdk.org/jeps/356), Javadoc `java.util.random` |

Một ví dụ điển hình: Java 17 hỗ trợ `switch` expression thông thường đã được chuẩn hóa trước đó, nhưng **pattern matching trong `switch`** của Java 17 lại ở trạng thái preview. Không nên thấy một bài giới thiệu `switch` ở Java đời sau rồi suy ra mọi cú pháp `case Type x -> ...` đều chạy mặc định trong Java 17.

Nếu **cố ý thử nghiệm** preview đúng trên JDK 17, phải bật preview ở thời điểm biên dịch và chạy:

```bash
javac --enable-preview --release 17 PreviewExample.java
java --enable-preview PreviewExample
```

Tính năng preview có thể thay đổi giữa các bản Java; class file sử dụng preview cũng có các hạn chế phiên bản. Trong code cần duy trì ổn định trên Java 17, ưu tiên tính năng đã chính thức và xác nhận điều kiện hỗ trợ trước khi sử dụng preview.

## 6. Đọc Release Notes đúng phiên bản và đúng mục đích

Release Notes trả lời câu hỏi **“bản JDK này đã thay đổi những gì?”**; chúng thường gồm tính năng mới, thay đổi hành vi, vấn đề tương thích, thay đổi tùy chọn JVM, tính năng bị deprecated/removed, bản sửa lỗi, các lưu ý bảo mật và known issues.

### 6.1. Phân biệt bản phát hành gốc với bản cập nhật

- **Java/JDK 17 GA:** tra [JDK 17 Release Notes](https://www.oracle.com/java/technologies/javase/17-relnote-issues.html) để hiểu các thay đổi lớn khi lên Java 17 từ các dòng trước.
- **JDK 17.0.x:** tra [danh sách Release Notes JDK 17](https://www.oracle.com/java/technologies/javase/17u-relnotes.html), chọn **đúng số bản cập nhật** đang chạy. Bản vá cụ thể có thể có thay đổi về chứng chỉ, timezone, bảo mật hoặc sửa lỗi.
- **Bản phân phối khác:** xem release notes/advisory của nhà cung cấp JDK đó để biết bản vá, lịch hỗ trợ, cấu hình build và các khác biệt đóng gói.

Chỉ dựa vào trang release notes ban đầu của `17` thì có thể bỏ sót thay đổi của `17.0.x`; ngược lại, đọc release notes của một bản JDK mới hơn không có nghĩa các thay đổi đó tự động xuất hiện trong Java 17.

### 6.2. Quy trình tìm nguyên nhân khi nâng cấp bị lỗi

Giả sử chương trình dùng reflection vào chi tiết nội bộ JDK và sau khi chuyển lên Java 17 gặp `java.lang.reflect.InaccessibleObjectException`.

1. Ghi lại `java -version`, nhà cung cấp JDK, bản cập nhật, hệ điều hành và stack trace.
2. Tìm trong Release Notes Java 17 các từ khóa `encapsulation`, `internal API`, `reflection`.
3. Đọc [JEP 403 — Strongly Encapsulate JDK Internals](https://openjdk.org/jeps/403) để hiểu thay đổi về đóng gói nội bộ JDK trong Java 17.
4. Xác định thư viện hoặc dòng code đang phụ thuộc JDK internals; dùng `jdeps` để tìm phụ thuộc tĩnh khi thích hợp.
5. Thay bằng API công khai được hỗ trợ hoặc cập nhật thư viện. Nếu chưa thể sửa ngay, có thể cần một cấu hình `--add-opens` **chỉ định chính xác module/package**, sau khi đánh giá phụ thuộc thực tế; đó là biện pháp tương thích có phạm vi hẹp, không phải API thay thế lâu dài.

Ví dụ công cụ hỗ trợ điều tra:

```bash
jdeps --jdk-internals path/to/app.jar
jdeprscan --release 17 path/to/app.jar
```

`jdeps --jdk-internals` tìm một số phụ thuộc tới API nội bộ JDK qua phân tích bytecode; nó không bảo đảm phát hiện mọi cách truy cập động bằng reflection. `jdeprscan` giúp tìm API đã đánh dấu deprecated theo dữ liệu công cụ. Kết quả cần đọc cùng stack trace, dependency tree và tài liệu cập nhật của thư viện liên quan. Xem thêm [tài liệu công cụ JDK 17](https://docs.oracle.com/en/java/javase/17/docs/specs/index.html).

Một điểm dễ gặp: tùy chọn `--illegal-access` của các giai đoạn chuyển đổi trước đây **không còn là cách nới lỏng đóng gói hữu hiệu trên JDK 17**. Không áp dụng lại nguyên xi hướng dẫn cũ khi sửa vấn đề tương thích Java 17.

### 6.3. Đọc trạng thái deprecated, for removal và removed

Ba khái niệm có ý nghĩa khác nhau:

- **Deprecated:** API/tính năng vẫn có thể còn hiện diện nhưng không được khuyến nghị cho code mới; xem tài liệu thay thế.
- **Deprecated for removal:** có chủ đích loại bỏ trong một bản phát hành tương lai, nhưng **không đồng nghĩa đã bị xóa khỏi JDK 17**.
- **Removed:** phần API/tính năng được nêu đã không còn trong bản phát hành tương ứng; cần sửa mã hoặc cấu hình phụ thuộc.

Ví dụ, JEP 411 đánh dấu **Security Manager là deprecated for removal trong Java 17**; đó là thông tin vòng đời API, không được diễn giải thành “Security Manager đã bị loại bỏ khỏi Java 17”. Khi xử lý chương trình thực tế, phải đối chiếu cả API Docs và Release Notes của đúng phiên bản.

## 7. Quy trình tra cứu từ câu hỏi đến câu trả lời có thể kiểm chứng

Áp dụng sáu bước sau cho một vấn đề kỹ thuật bất kỳ:

1. **Viết lại câu hỏi thật cụ thể.** Ví dụ: “Trên Java 17, `Stream.toList()` có cho phép `add()` không?” thay vì “Stream bị lỗi”.
2. **Xác định môi trường.** Ghi `JDK 17.0.x`, vendor, runtime, phiên bản compiler và `--release` của dự án.
3. **Chọn nguồn gốc.** Cú pháp/kiểu → JLS; phương thức/thư viện → Javadoc; thay đổi giữa bản JDK → Release Notes; mục đích và trạng thái tính năng → JEP.
4. **Đọc đúng điều khoản hoặc đúng chữ ký API.** Kiểm tra các từ khóa ràng buộc, ngoại lệ, `Since`, `Deprecated`, `Preview`; chú ý không lấy đặc điểm triển khai thay cho hợp đồng.
5. **Kiểm chứng với ví dụ tối thiểu trên Java 17.** Nếu là lỗi tương thích, tái hiện trong cùng môi trường JDK và dependency. Ví dụ thực nghiệm hỗ trợ chẩn đoán, nhưng không thay thế đặc tả.
6. **Lưu kết luận cùng nguồn.** Ghi URL có phiên bản, điều khoản JLS hoặc chữ ký phương thức, phiên bản bản vá nếu liên quan, và ngày tra cứu khi ghi tài liệu dài hạn.

### Mẫu ghi chú tra cứu hữu ích trong dự án

```text
Câu hỏi: Danh sách từ Stream.toList() có thêm phần tử được không?
Môi trường: JDK 17, build với --release 17
Nguồn: Java SE 17 API Docs → java.util.stream.Stream → toList()
Hợp đồng: kết quả unmodifiable; mutator ném UnsupportedOperationException
Giải pháp: dùng Collectors.toCollection(ArrayList::new) nếu cần List có thể sửa
Kiểm chứng: biên dịch/chạy ví dụ nhỏ trên JDK 17
```

Với lỗi cú pháp `sealed` có thể ghi nguồn là “JLS SE 17 §8.1.1.2, §8.1.6”; với lỗi sau nâng cấp JDK có thể ghi nguồn là “JDK 17 Release Notes + JEP 403 + bản cập nhật và vendor cụ thể”. Những thông tin này giúp người khác kiểm tra lại kết luận khi sửa code sau nhiều tháng.

## 8. Những sai lầm cần tránh khi tra tài liệu Java 17

| Sai lầm thường gặp | Cách làm đúng |
| --- | --- |
| Kết quả tìm kiếm mở API Docs của Java 21/25/26 nhưng dự án chạy Java 17. | Kiểm tra thanh địa chỉ có `/java/javase/17/`; nếu một phương thức không tồn tại ở trang Java 17 thì không mặc nhiên sử dụng nó. |
| Dùng nội dung bài blog về cú pháp Java mới và cho rằng Java 17 đã hỗ trợ. | Kiểm tra JEP, trạng thái preview và JLS Java SE 17. |
| Cho rằng `Since: 16` nghĩa là API chỉ dành cho Java 16. | Hiểu `Since` là mốc xuất hiện đầu tiên; xác nhận API còn hiện diện trong Javadoc Java 17. |
| Nhìn một ví dụ trả `ArrayList` rồi suy ra phương thức cam kết luôn trả `ArrayList`. | Đọc *Returns*, *Implementation Note* và cam kết về loại danh sách, khả năng sửa, null, thread safety. |
| Chỉ xem Release Notes GA khi lỗi xuất hiện ở một bản vá `17.0.x`. | Đọc release notes của **đúng bản vá** và nhà cung cấp JDK. |
| Dùng workaround từ thời JDK 8/11 mà không kiểm tra lại. | Ưu tiên API công khai hiện được hỗ trợ; đối chiếu Migration Guide và Release Notes của Java 17. |
| Đánh đồng deprecated, for removal và removed. | Đọc chính xác nhãn và trạng thái áp dụng ở **Java 17**, đồng thời lên kế hoạch chuyển đổi nếu API đã deprecated. |
| Sử dụng `-source 17` nhưng vô tình gọi API nền tảng của JDK mới hơn. | Khi dùng compiler mới hơn, thiết lập `--release 17` hoặc cấu hình tương đương của build tool. |

## 9. Bài tập tra cứu có hướng dẫn

**Bài 1 — Quy tắc ngôn ngữ.** Một `sealed interface` cho phép những lớp nào `implements` trực tiếp? Truy cập JLS SE 17, tìm phần về sealed interfaces và permitted subclasses; viết ví dụ gồm hai implementation được cho phép. Giải thích vì sao một lớp thứ ba không được phép sẽ bị compiler từ chối.

**Bài 2 — Hợp đồng API.** So sánh `Stream.toList()`, `Collectors.toList()` và `Collectors.toCollection(ArrayList::new)` theo Javadoc Java 17. Với mỗi API, ghi lại: kiểu trả về, cam kết về khả năng sửa kết quả, và điểm nào **không được đặc tả**.

**Bài 3 — Trạng thái tính năng.** Kiểm tra JEP 409 và JEP 406: tính năng nào dùng mặc định trong Java 17, tính năng nào cần preview? Viết ngắn gọn lý do không nên suy luận từ cú pháp Java mới hơn.

**Bài 4 — Thay đổi sau nâng cấp.** Một ứng dụng chuyển từ JDK 11 sang JDK 17 gặp lỗi reflective access. Lập danh sách thông tin môi trường cần ghi nhận, trang Release Notes/JEP cần đọc và công cụ `jdeps` có thể giúp điều tra. Đề xuất hướng sửa dựa trên API công khai được hỗ trợ.

Khi hoàn thành, mỗi câu trả lời nên kèm **liên kết tài liệu chính thức, đúng phiên bản Java 17 và một bằng chứng từ điều khoản hoặc hợp đồng API**. Thói quen đó quan trọng hơn việc thuộc lòng tên trang: nó giúp tự xác minh thông tin khi bản JDK, thư viện và tài liệu kỹ thuật tiếp tục phát triển.
