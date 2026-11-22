# Phân biệt ngôn ngữ Java, Java SE, JVM, JDK và môi trường chạy

## Mục tiêu

Sau bài này, bạn có thể phân biệt rõ năm khái niệm thường bị gọi chung là “Java”, giải thích từ mã nguồn đến bytecode và tiến trình chạy, xác định bộ công cụ cần dùng để phát triển/triển khai, và chẩn đoán lỗi do phiên bản hoặc môi trường không tương thích.

## 1. Bản đồ năm khái niệm

| Thành phần | Là gì? | Vai trò chính | Ví dụ |
| --- | --- | --- | --- |
| **Ngôn ngữ Java** | Ngôn ngữ lập trình, có cú pháp, hệ kiểu và ngữ nghĩa được quy định trong Java Language Specification (JLS) | Quy định cách *viết* và hiểu mã nguồn | `class`, `interface`, `record`, `if`, lambda |
| **Java SE (Java Platform, Standard Edition)** | Nền tảng Java tiêu chuẩn với các đặc tả ngôn ngữ, JVM và thư viện API chuẩn theo phiên bản | Quy định hợp đồng của *nền tảng/API tiêu chuẩn* | `java.lang`, `java.util`, `java.time`, `java.io` |
| **JVM (Java Virtual Machine)** | Máy ảo được đặc tả để nạp, xác minh và thực thi mã theo định dạng class file | *Thực thi* bytecode | HotSpot VM, Eclipse OpenJ9 |
| **JDK (Java Development Kit)** | Bộ công cụ phát triển và các thành phần cần thiết để chạy Java | *Biên dịch, chạy, đóng gói và phân tích* | `javac`, `java`, `jar`, `javap`, `jlink` |
| **Môi trường chạy (runtime environment)** | Java runtime thực tế kết hợp với thư viện, hệ điều hành, kiến trúc máy và cấu hình triển khai | Quyết định ứng dụng có *chạy được trong thực tế* hay không | JVM + Java SE modules + dependencies + OS/CPU + cấu hình |

**Quan hệ:** lập trình viên **viết bằng ngôn ngữ Java**, có thể **gọi API Java SE**, dùng **JDK** để biên dịch thành class file, rồi một **JVM** thuộc **môi trường chạy** thực thi bytecode. Không thể dùng năm thuật ngữ này để thay thế lẫn nhau.

## 2. Ngôn ngữ Java: quy tắc của mã nguồn

Ngôn ngữ Java xác định quy tắc khai báo lớp/giao diện, kiểu dữ liệu, tên, biểu thức, câu lệnh, ngoại lệ, generic, lambda và nhiều cấu trúc khác. Tài liệu **Java Language Specification (JLS)** mô tả cú pháp và ngữ nghĩa theo từng phiên bản.

Ví dụ `int x = 2;` phù hợp quy tắc ngôn ngữ; gán `String text = 123;` là lỗi kiểu trong trường hợp thông thường. Cú pháp mới có thể đòi phiên bản ngôn ngữ mới: `record` là tính năng chính thức từ Java 16, nên không thể dùng khi biên dịch với mức ngôn ngữ Java 11.

**Ngôn ngữ không đồng nghĩa với thư viện hoặc máy ảo.** Mã Java có thể gọi thư viện ngoài Java SE như Spring; ngược lại, JVM có thể chạy bytecode được biên dịch từ Kotlin hoặc Scala. Dù có chữ “Java”, Spring không phải cú pháp của ngôn ngữ và không thuộc tập API Java SE tiêu chuẩn.

## 3. Java SE: nền tảng và API chuẩn

**Java SE** là tên nền tảng Java tiêu chuẩn. Nền tảng này bao gồm các đặc tả ngôn ngữ, JVM và thư viện/API tiêu chuẩn tương ứng với phiên bản phát hành. Khi nhấn mạnh “Java SE API”, ta đang nói đến tập API công khai chuẩn hóa, ví dụ:

- `java.lang`: `Object`, `String`, `System`, `Thread` (gói được import ngầm).
- `java.util`: `List`, `Map`, `Optional` và các tiện ích.
- `java.time`: các kiểu ngày/giờ hiện đại.
- `java.io`, `java.nio.file`: nhập/xuất và hệ thống tệp.
- `java.net`, `java.net.http`: mạng và HTTP client.

Từ Java 9, các thành phần nền tảng được tổ chức qua **hệ thống module**; mọi module đều đọc ngầm module cốt lõi `java.base`. Một số API tồn tại ở bản Java SE mới nhưng không có ở bản cũ, vì thế cần kiểm tra phiên bản nền tảng đích.

**Java SE không phải một executable hay một bộ cài duy nhất.** JDK mang đến công cụ và bản triển khai nền tảng. Java SE cũng không đồng nghĩa toàn bộ hệ sinh thái: **Jakarta EE**, **Spring**, nhiều JDBC driver và những thư viện bên thứ ba cần được cung cấp riêng; JavaFX không còn được đóng kèm như một phần của JDK chuẩn kể từ Java 11.

## 4. JVM: tầng thực thi, không phải ngôn ngữ hay bộ công cụ

**JVM** theo *Java Virtual Machine Specification (JVMS)* là máy trừu tượng có hợp đồng về định dạng `.class`, bytecode, loading/linking/initialization và thực thi. **HotSpot** và **OpenJ9** là những cách hiện thực máy ảo ấy. Chúng có thể chọn interpreter, JIT và GC khác nhau trong khi phải giữ ngữ nghĩa được đặc tả.

Khi chạy `java HelloJvm`, launcher của bộ runtime/JDK khởi động JVM; VM nạp và thực thi class file, còn các lời gọi `List.of` và `System.out.println` sử dụng thư viện Java SE. Vì thế **JVM không phải `javac`, không phải toàn bộ Java SE và không phải máy ảo mô phỏng một hệ điều hành**. Các bước và vùng nhớ bên trong JVM được phân tích ở bài về cấu trúc thực thi, thay vì lặp chi tiết loading và JIT tại đây.

## 5. JDK: bộ công cụ phát triển

**Java Development Kit** gồm các công cụ giúp lập trình, biên dịch, kiểm tra, đóng gói, chạy và phân tích ứng dụng Java; đồng thời cung cấp các thành phần runtime.

| Công cụ JDK | Dùng để |
| --- | --- |
| `javac` | Biên dịch nguồn `.java` thành class file `.class` |
| `java` | Khởi động JVM và chạy class, JAR hoặc module |
| `jar` | Tạo/xem/cập nhật tệp JAR |
| `javadoc` | Sinh tài liệu API |
| `javap` | Xem thông tin class file; `javap -c` cho biết lệnh bytecode |
| `jshell` | Thử nhanh biểu thức/đoạn Java trong REPL |
| `jdeps` | Phân tích phụ thuộc của class/JAR |
| `jlink` | Tạo runtime image tùy biến từ các module |

Ví dụ, **`javac` không phải JVM**: `javac` thông thường phân tích mã nguồn, kiểm tra kiểu và sinh bytecode; JVM đọc class file và thực thi bytecode đó, có thể tối ưu/JIT khi chạy. Cũng không nên gọi Java SE là JDK: Java SE mô tả nền tảng, còn JDK là bộ công cụ gắn với một bản triển khai cụ thể.

JDK có các mức phát hành như **17**, **21** và nhiều bản phân phối từ các vendor. Cần phân biệt **phiên bản Java/JDK**, **vendor/bản build** và **triển khai JVM**; chúng ảnh hưởng đến API được cung cấp, mức class file, bản vá, cấu hình và đôi khi đặc tính runtime.

## 6. “Môi trường chạy”, JRE và runtime image

Trong cách gọi truyền thống, **JRE (Java Runtime Environment)** là một gói có JVM và thư viện/tài nguyên cần để chạy Java nhưng không có trọn bộ công cụ phát triển như `javac`. Thời Java 8, bộ cài JRE và JDK thường được phân phối riêng.

Từ Java 9, hệ thống module và runtime image thay đổi cách phân phối; nhiều vendor Java hiện đại không phát hành một bộ cài mang tên “JRE” tách biệt theo kiểu Java 8. Trong thực tế, Java 17+ thường chạy bằng:
- **JDK đầy đủ**, có cả công cụ và runtime.
- **Runtime image** do nhà cung cấp đóng gói, có thể không kèm compiler.
- **Runtime image do `jlink` tạo**, chỉ bao gồm những module được chọn và phụ thuộc module cần thiết.

Môi trường chạy còn rộng hơn Java runtime: bao gồm **OS/CPU**, native libraries, JAR dependencies, classpath/module path, quyền hệ thống, biến môi trường, file cấu hình, bộ nhớ/tài nguyên và kết nối bên ngoài. Ví dụ, một JVM hoạt động tốt vẫn không thể tự cung cấp JAR của framework đang bị thiếu; một thư viện native cho Linux/x86-64 cũng không tự chạy trên Windows/ARM64.

**Phân biệt rõ:**
- **JVM** là thành phần thực thi bytecode.
- **JRE/runtime image** là tập thành phần được đóng gói cho nhu cầu chạy chương trình.
- **JDK** bao gồm công cụ phát triển và khả năng chạy.
- **Môi trường chạy thực tế** còn gồm tất cả điều kiện deployment kể trên.
- Một máy có thể có một JDK nhưng chạy nhiều **tiến trình JVM** khác nhau.

## 7. Gắn năm khái niệm vào một chương trình cụ thể

```text
Nguồn Java (cú pháp/ngữ nghĩa) + Java SE API (List, String, System)
          |
          | javac: công cụ trong JDK
          v
       HelloJvm.class
          |
          | java launcher → JVM
          v
Thư viện Java SE + dependencies + OS/CPU + cấu hình
          |
          v
      Chương trình chạy
```

Lưu tệp **`HelloJvm.java`**:

```java
import java.util.List;

public class HelloJvm {
    public static void main(String[] args) {
        List<String> concepts = List.of(
                "Ngôn ngữ Java",
                "Java SE",
                "JVM");
        System.out.println("Ba lớp: " + String.join(" | ", concepts));
    }
}
```

Biên dịch và chạy bằng JDK 17+:

```bash
javac --release 17 HelloJvm.java
java HelloJvm
```

**Stdout chính xác**:

```text
Ba lớp: Ngôn ngữ Java | Java SE | JVM
```

Trong ví dụ, khai báo lớp, generic và lời gọi phương thức thuộc **ngôn ngữ Java**; `List`, `String.join` và `System.out` thuộc **API Java SE**; `javac` và `java` nằm trong **JDK**; **JVM** thực thi class file; **runtime environment** bao gồm cả thư viện, phụ thuộc và OS. `--release 17` chọn ngôn ngữ, class-file version và Java SE API mục tiêu, **không tự kiểm chứng** dependency hay thư viện native ở máy đích.

Để theo dõi **chính xác các bước biên dịch và opcode**, dùng `javap -c` cùng bài tiếp theo về đường đi `.java → .class → mã máy`. Phân loại năm khái niệm ở đây không đòi người học thuộc thuật toán class loading hay chi tiết JIT.

## 8. Kiểm tra phiên bản và tương thích

~~~bash
java -version
javac -version
~~~

Lệnh thứ nhất chỉ runtime/launcher thực tế được gọi; lệnh thứ hai chỉ compiler thực tế được gọi. **Hai lệnh có thể chọn hai bản cài khác nhau** vì `PATH`, `JAVA_HOME`, IDE, Maven/Gradle toolchains hoặc container; `JAVA_HOME` là quy ước nhiều công cụ sử dụng, còn executable đang chạy mới quyết định JVM thực tế.

Khi xác minh một ứng dụng, đặt bốn câu hỏi độc lập:

1. **Ngôn ngữ:** compiler có hiểu cú pháp và mức `--release`/`--source` yêu cầu không?
2. **Bytecode:** runtime JVM có hỗ trợ class file tạo ra không? Ví dụ Java 17 ứng với class file major **61**, Java 21 ứng với major **65**. JVM 17 không hiểu class file major 65.
3. **API và thư viện:** runtime có các API Java SE, module, JAR bên thứ ba tương ứng không?
4. **Nền tảng:** OS, CPU, native binary, cấu hình, quyền và tài nguyên có phù hợp không?

**Trường hợp A — `UnsupportedClassVersionError`:** thường class file được tạo cho bản JVM mới hơn runtime đang chạy. Kiểm tra phiên bản, biên dịch lại với target phù hợp hoặc nâng JVM.

**Trường hợp B — có `java` nhưng không có `javac`:** có thể đang dùng runtime image hoặc đường dẫn chỉ trỏ tới runtime. Chạy class file thích hợp có thể được, nhưng cần compiler/JDK nếu muốn biên dịch thông thường.

**Trường hợp C — `ClassNotFoundException`/`NoClassDefFoundError`:** thường phải kiểm tra JAR/module/classpath, lỗi khởi tạo lớp và chuỗi nguyên nhân trong stack trace. Đây không tự động là lỗi của cú pháp Java.

**Trường hợp D — chạy máy cá nhân nhưng lỗi trên server:** so sánh phiên bản, các module cắt gọn bằng `jlink`, native libraries, OS/CPU và cấu hình triển khai. **“Write once, run anywhere”** diễn đạt mục tiêu tính di động; không có nghĩa mọi phụ thuộc bên ngoài bytecode tự tương thích.

## 9. Những khẳng định sai thường gặp

| Hiểu sai | Cách nói chính xác |
| --- | --- |
| “Java = JVM.” | Java là ngôn ngữ, JVM là máy ảo; JVM có thể chạy bytecode từ nhiều ngôn ngữ. |
| “Java SE chính là JDK.” | Java SE là nền tảng/đặc tả; JDK là bộ công cụ và một bản triển khai các thành phần cần thiết. |
| “`javac` sinh trực tiếp mã máy.” | `javac` thông thường sinh JVM bytecode; VM thực thi và có thể JIT biên dịch mã máy. |
| “JVM là một máy ảo chứa hệ điều hành riêng.” | JVM thực thi bytecode và dựa vào OS bên dưới. |
| “Cài Java runtime là tự động có compiler.” | Runtime image có thể không chứa `javac`. |
| “Không có gói JRE riêng thì không chạy được Java.” | JDK hoặc runtime image phù hợp đã có thể chạy ứng dụng. |
| “JDK mới luôn chạy được trên JVM cũ.” | Bytecode phải nhắm đúng mức JVM; API và phụ thuộc cũng cần tương thích. |
| “JAR là máy ảo.” | JAR là định dạng đóng gói class files và tài nguyên. |

## 10. Tự kiểm tra và đáp án

**Câu 1.** Trong `List.of("A", "B")`, cú pháp gọi phương thức và API `List.of` thuộc khái niệm nào?

**Đáp án:** cú pháp thuộc **ngôn ngữ Java**; `List.of` là **API Java SE** (được bổ sung từ Java 9).

**Câu 2.** Có lệnh `java` nhưng không có `javac`. Có thể chạy chương trình Java không?

**Đáp án:** **Có thể**, nếu runtime và tất cả dependency tương thích. Nhưng không thể khẳng định máy có compiler; cần JDK nếu muốn dùng `javac` để biên dịch nguồn theo cách thông thường.

**Câu 3.** JDK 21 biên dịch bằng `javac --release 17`; chương trình có chắc chạy được trên JVM 17 không?

**Đáp án:** tùy chọn nhắm đến ngôn ngữ, bytecode và Java SE API của Java 17 nên giúp đạt tương thích ở những lớp này, nhưng **chưa đủ bảo đảm**: phải kiểm tra thư viện ngoài Java SE, các dependency, native code và môi trường thực tế.

**Câu 4.** Kotlin tạo bytecode để chạy trên JVM. Có phải Kotlin trở thành ngôn ngữ Java không?

**Đáp án:** **Không.** Kotlin là ngôn ngữ riêng; có thể dùng JVM làm môi trường thực thi bytecode.

**Câu 5.** Vai trò riêng của Java SE và JVM trong việc dùng `java.util.List` là gì?

**Đáp án:** **Java SE** đặc tả API `java.util.List`; bản triển khai nền tảng cung cấp thư viện tương ứng; **JVM** thực thi bytecode gọi API đó.

## 11. Mô hình nhớ nhanh

- **Language** → viết mã bằng cú pháp/ngữ nghĩa Java.
- **Java SE** → hợp đồng nền tảng và API chuẩn.
- **JDK** → biên dịch, đóng gói, chạy, phân tích.
- **JVM** → nạp và thực thi class file/bytecode.
- **Runtime environment** → JVM, thư viện, OS, cấu hình và mọi điều kiện để chương trình chạy thật.

Khi gặp lỗi, hãy xác định nó nằm ở lớp nào: **nguồn/cú pháp → compiler/tool → class file/JVM → API/dependency → cấu hình/máy chạy**. Phân biệt đúng các lớp giúp chọn đúng bước xử lý.
