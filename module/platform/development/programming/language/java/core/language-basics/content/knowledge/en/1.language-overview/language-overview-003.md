# Phân biệt Java, Java SE, JDK và môi trường chạy

> **Chủ đề:** Java core — language-basics / Tổng quan  
> **Mục tiêu:** Biết chính xác mình đang *viết bằng ngôn ngữ nào*, *dựa vào nền tảng nào*, *dùng bộ công cụ nào để xây dựng*, và *cần gì để chạy ứng dụng*. Sau bài học, bạn có thể dùng `javac` và `java` để tự biên dịch/chạy một chương trình đơn giản, xác định môi trường đang sử dụng và giải thích lỗi sai phiên bản phổ biến.

## 1. Vì sao bốn tên gọi này dễ bị nhầm?

Một bạn mới học thường nói: “Tôi đã cài Java nên có thể viết và chạy mọi chương trình Java”. Câu này chưa đủ rõ: máy có **công cụ biên dịch** không? Có **máy ảo Java** không? Chương trình được xây dựng cho **phiên bản nền tảng** nào? Lệnh `java` trong terminal thực sự trỏ đến bản cài đặt nào?

Một cách phân biệt hữu ích:

| Tên gọi | Nó là gì? | Dùng để làm gì? | Câu hỏi nhận diện |
| --- | --- | --- | --- |
| **Java (ngôn ngữ)** | Ngôn ngữ lập trình có cú pháp, kiểu dữ liệu, class, method và quy tắc ngữ nghĩa | Viết mã nguồn `.java` | “Đoạn mã này viết bằng ngôn ngữ gì?” |
| **Java SE** (*Java Platform, Standard Edition*) | Nền tảng chuẩn: các đặc tả liên quan cùng tập API cơ bản của Java | Xác định khả năng chuẩn mà chương trình Java thông thường dựa vào, ví dụ `java.lang`, `java.util`, `java.io` | “Ứng dụng dựa trên nền tảng/API Java chuẩn nào?” |
| **JDK** (*Java Development Kit*) | Bộ công cụ phát triển kèm khả năng chạy Java | Biên dịch, chạy, đóng gói, kiểm tra chương trình; có `javac`, `java`, `jar`… | “Tôi dùng công cụ nào để viết, biên dịch và xây dựng ứng dụng?” |
| **JVM** (*Java Virtual Machine*) | Máy ảo thực thi bytecode Java | Nạp, kiểm tra và thực thi mã `.class`, quản lý nhiều khía cạnh lúc chạy | “Ai thực sự thực thi bytecode?” |
| **JRE / môi trường chạy** | Khả năng chạy ứng dụng: máy ảo và thư viện/thành phần runtime cần thiết | Thực thi chương trình đã xây dựng mà không nhất thiết cần compiler | “Máy đích cần những thành phần gì để chạy?” |

**Đừng coi đây là năm sản phẩm cạnh tranh.** Các tên chỉ *những tầng khác nhau* của cùng hệ sinh thái. JDK thông thường bao gồm những thành phần cần để phát triển **và** chạy; một runtime tối giản có thể không chứa công cụ `javac`.

### Đặt từng khái niệm vào đúng vị trí

Trong quy trình thông thường, mã nguồn `.java` được viết theo **ngôn ngữ Java**; `javac` thuộc **JDK** tạo bytecode `.class`; lệnh `java` khởi động **JVM** để chạy class cùng những thư viện runtime cần thiết. **Java SE** xác định nền tảng và API chuẩn mà một bản triển khai tương thích cung cấp.

Bài này chú trọng **chọn và kiểm tra đúng môi trường**. Cơ chế nạp class, bytecode và các bước biên dịch được thực hành sâu ở bài về mã nguồn → trình biên dịch → bytecode → JVM.

## 2. Java: tên ngôn ngữ khác với tên nền tảng

Ở cấp ngôn ngữ, Java quy định những thứ như khai báo kiểu, biểu thức, class, interface, câu lệnh điều kiện, xử lý ngoại lệ và cách gọi method. Ví dụ:

~~~java
public class Hello {
    public static void main(String[] args) {
        System.out.println("Xin chào Java!");
    }
}
~~~

Đây là **mã nguồn viết bằng ngôn ngữ Java**. Tệp có tên `Hello.java` vì chứa public class `Hello`.

Tuy nhiên, `System.out.println` không chỉ là cú pháp ngôn ngữ: `System` và `PrintStream` là các lớp được nền tảng cung cấp. Muốn chạy chương trình, bạn cần môi trường có những thành phần chuẩn tương ứng.

Cụm từ **“Java”** trong giao tiếp hằng ngày đôi khi ám chỉ cả ngôn ngữ lẫn nền tảng và công cụ. Khi cấu hình môi trường hoặc giải thích lỗi, nên gọi rõ **JDK**, **JVM**, **Java SE** hay **Java source** để tránh nhầm.

## 3. Java SE: nền tảng chuẩn, không phải tên lệnh cài đặt

**Java SE** là viết tắt của *Java Platform, Standard Edition*, tập trung vào những khả năng nền tảng thường dùng cho ứng dụng Java thông thường:

- Ngôn ngữ và các quy tắc tương thích với một phiên bản Java tương ứng.
- Máy ảo và đặc tả liên quan đến việc thực thi Java.
- Thư viện/API chuẩn, chẳng hạn các gói `java.lang` (kiểu cơ bản), `java.util` (collections), `java.time` (ngày giờ), `java.nio.file` (tệp/đường dẫn), `java.net` (mạng).
- Những tính năng cụ thể tùy theo **phiên bản Java SE**.

Java SE **không phải** một tệp `java-se.exe` hay một chương trình bạn chạy bằng lệnh `java-se`. Một bản phân phối JDK được tạo ra để triển khai nền tảng Java tương ứng, cung cấp compiler và các công cụ phát triển.

**Đặc tả, triển khai và bản phân phối khác nhau:**

| Khái niệm | Ý nghĩa |
| --- | --- |
| Đặc tả Java SE | Quy định các hành vi và API chuẩn cần đáp ứng |
| Triển khai | Mã phần mềm thực hiện các yêu cầu của nền tảng/VM |
| Bản phân phối JDK | Gói cài đặt thực tế từ một nhà cung cấp, có công cụ và runtime |

Chẳng hạn, **OpenJDK** là dự án triển khai Java mã nguồn mở; các tổ chức có thể phát hành những bản dựng JDK dựa trên OpenJDK. Đối với người mới học, quan trọng nhất là chọn một **JDK có phiên bản phù hợp** và kiểm tra đường dẫn công cụ; không phải tìm một chương trình riêng mang tên “Java SE”.

**Phạm vi:** Java SE là nền tảng lõi. Một ứng dụng web doanh nghiệp có thể còn dùng Jakarta EE, Spring hoặc thư viện khác; những thư viện/framework này **không tự động trở thành API chuẩn của Java SE**. Bài này không đi sâu vào các nền tảng đó.

## 4. JDK, JVM, JRE: ai biên dịch và ai chạy?

### 4.1. JDK — bộ đồ nghề phát triển

Một JDK thông thường có:

| Công cụ | Vai trò thường gặp |
| --- | --- |
| `javac` | Biên dịch mã nguồn `.java` thành bytecode `.class` |
| `java` | Khởi động chương trình Java và môi trường thực thi thích hợp |
| `jar` | Tạo, xem hoặc xử lý tệp JAR |
| `javadoc` | Sinh tài liệu từ chú thích JavaDoc |
| `jshell` | Thử các biểu thức/lệnh Java tương tác (các JDK hiện đại) |
| `jlink` | Tạo runtime image tùy biến từ các module cần thiết (JDK 9+) |

Khi học và xây dựng ứng dụng Java core, **cài JDK** là lựa chọn dễ nhất vì có cả compiler lẫn runtime. IDE như IntelliJ IDEA hoặc VS Code là trình soạn thảo/môi trường phát triển **khác với JDK**; IDE có thể tự tải/chọn JDK nhưng bản thân IDE không đồng nghĩa với JDK.

### 4.2. JVM — thành phần thực thi trong runtime

**JVM thực thi bytecode** và quản lý những khía cạnh như tải class, bộ nhớ, ngoại lệ; JVM hiện đại có thể kết hợp thông dịch và JIT. Nó không phải compiler `javac`. Lệnh `java` khởi động runtime có JVM cùng thư viện cần thiết. Bản JVM phải phù hợp hệ điều hành, CPU và phiên bản class file, còn bytecode thường có thể được chia sẻ giữa nhiều bản JVM tương thích.

Cài một JDK phổ biến thường đã có runtime và JVM để chạy ví dụ; người học không cần tải JVM riêng chỉ vì nhìn thấy các khái niệm JDK/JVM trong sơ đồ.

### 4.3. JRE — hiểu đúng theo bối cảnh phiên bản

**JRE** (*Java Runtime Environment*) là cách gọi quen thuộc cho bộ thành phần **chạy** ứng dụng: VM và các thư viện/tệp runtime cần thiết, nhưng không yêu cầu đầy đủ công cụ phát triển như `javac`.

- Ở nhiều bản phát hành Java cũ (đặc biệt Java 8), người học thường gặp **gói JRE riêng** hoặc thư mục `jre` nằm trong JDK.
- Từ thế hệ Java module hiện đại (Java 9+), cách đóng gói thay đổi. **Không nên mặc định** mọi JDK đều có một thư mục `jre` riêng hoặc có bộ cài JRE độc lập.
- Một số nhà cung cấp vẫn phân phối runtime-only; ứng dụng cũng có thể đóng gói runtime image được tạo bằng `jlink`. Vì vậy, nói tuyệt đối “Java mới không còn JRE” là **không chính xác**.

Phân biệt theo *khả năng*: máy có **`java` để chạy** chưa chắc có **`javac` để biên dịch**. Máy cài JDK đúng cách thì thông thường có cả hai.

## 5. Thực hành: kiểm tra, biên dịch và chạy chương trình

Ví dụ dùng **JDK 17 trở lên** để thống nhất các lệnh. Bạn có thể dùng JDK mới hơn, nhưng cần chọn phiên bản mà dự án/khóa học yêu cầu.

### Bước 1 — Kiểm tra công cụ trên máy

Mở terminal và chạy:

~~~bash
java -version
javac -version
~~~

Lệnh đầu xem runtime/launcher Java đang được tìm thấy; lệnh sau xem compiler Java đang được tìm thấy. Kết quả thực tế phụ thuộc bản JDK/bản phân phối bạn cài. **Hai lệnh không bắt buộc trỏ đến cùng một bản cài**, vì `PATH` có thể chứa nhiều JDK/JRE; do đó cần kiểm tra khi thấy phiên bản lệch nhau.

Bạn cũng có thể chạy:

~~~bash
java --version
javac --version
~~~

Cú pháp `--version` áp dụng cho các JDK hiện đại. Với môi trường Java cũ, dạng `-version` quen thuộc hơn.

**Nếu `java` có nhưng `javac` không tồn tại:** bạn có thể đang dùng runtime-only, hoặc `PATH` đang chỉ tới thư mục không chứa compiler. Không kết luận ngay là “Java hỏng”.

### Bước 2 — Viết một tệp nguồn tự kiểm tra runtime

Tạo tệp **JavaEnvironmentDemo.java** (đúng chữ hoa/thường với tên public class) và chép mã sau:

~~~java
public class JavaEnvironmentDemo {
    public static void main(String[] args) {
        String who = args.length == 0 ? "Java" : args[0];

        System.out.println("Xin chào, " + who + "!");
        System.out.println("Java version : "
                + System.getProperty("java.version"));
        System.out.println("Java vendor  : "
                + System.getProperty("java.vendor"));
        System.out.println("VM name      : "
                + System.getProperty("java.vm.name"));
        System.out.println("Runtime home : "
                + System.getProperty("java.home"));
        System.out.println("Số tham số   : " + args.length);
    }
}
~~~

Điểm cần hiểu:

- `main(String[] args)` là điểm bắt đầu của chương trình theo cách chạy class truyền thống.
- `System.getProperty("java.version")` mô tả **môi trường đang chạy chương trình**, không chứng minh compiler nào đã tạo tệp `.class`.
- `java.vm.name` cho biết tên VM hiện tại; `java.vendor` cho biết nhà cung cấp được runtime công bố.
- `java.home` là **đường dẫn runtime đang sử dụng**; không nhất thiết bằng biến môi trường `JAVA_HOME`.
- `args` chứa các đối số sau tên class khi gọi lệnh `java`.

### Bước 3 — Biên dịch rồi chạy

Trong thư mục chứa tệp nguồn:

~~~bash
mkdir out
javac -encoding UTF-8 -d out JavaEnvironmentDemo.java
java -cp out JavaEnvironmentDemo VietNam
~~~

Trước tiên, `mkdir out` tạo thư mục đích `out` (chỉ cần làm khi thư mục chưa có). Vì mã nguồn có chữ tiếng Việt, `-encoding UTF-8` giúp `javac` đọc đúng tệp UTF-8, kể cả trên máy mà encoding mặc định khác UTF-8; tùy chọn này **không** tự đổi encoding terminal. `javac -d out` ghi tệp `.class` vào thư mục đích đã tồn tại; khi có `package`, `javac` có thể tạo các thư mục con phù hợp. `java -cp out JavaEnvironmentDemo` tìm class trong đó rồi chạy phương thức `main`.

Đầu ra minh họa, phần phiên bản và đường dẫn **sẽ khác giữa các máy**:

~~~text
Xin chào, VietNam!
Java version : <phiên bản đang chạy>
Java vendor  : <nhà cung cấp runtime>
VM name      : <tên Java VM>
Runtime home : <đường dẫn runtime>
Số tham số   : 1
~~~

Các chuỗi trong dấu ngoặc nhọn ở ví dụ đầu ra chỉ là **chỗ giữ chỗ**, không phải văn bản Java thực sự in ra.

Chạy lại không truyền đối số:

~~~bash
java -cp out JavaEnvironmentDemo
~~~

Lúc này chương trình in `Xin chào, Java!` và `Số tham số   : 0`. Cùng tệp `.class` nhưng đầu ra khác do **đối số runtime**.

### Bước 4 — Hai cách khởi động khác nhau

Trên JDK 11+, bạn cũng có thể chạy `java JavaEnvironmentDemo.java VietNam` theo *source-file mode*. Launcher biên dịch nguồn phục vụ lần chạy; không cần lệnh `javac` riêng. Với `java -cp out JavaEnvironmentDemo VietNam`, launcher tìm **class đã biên dịch** trong `out`. Cả hai vẫn sử dụng runtime Java; chúng khác nhau ở **đầu vào dành cho launcher** và bước chuẩn bị bytecode.

### Bước 5 — Khi cần đóng gói JAR

Sau khi biên dịch vào thư mục `out`, có thể tạo JAR chạy được:

~~~bash
jar --create --file demo.jar --main-class JavaEnvironmentDemo -C out .
java -jar demo.jar VietNam
~~~

Lệnh `jar` nằm trong bộ công cụ JDK. Tham số `--main-class` tạo thông tin entry point trong manifest; nếu JAR không xác định main class hợp lệ, `java -jar` sẽ không biết bắt đầu ở đâu. Đây là JAR ứng dụng đơn giản **không cần thư viện ngoài**; với dự án có dependency, phải đóng gói hoặc cung cấp chúng bằng cách phù hợp.

## 6. Máy chạy ứng dụng cần gì?

**Một chương trình chỉ dùng API Java SE** cần runtime phù hợp với bytecode và API mà chương trình yêu cầu. Điều này **không bắt buộc** máy người dùng cuối phải có cả compiler hay IDE.

| Tình huống | Cần gì? | Không bắt buộc phải có |
| --- | --- | --- |
| Viết, biên dịch Java source | JDK thích hợp, editor/IDE nếu muốn | Spring, Maven cho ví dụ nhỏ |
| Chạy `.class` đã biên dịch | Runtime Java tương thích; đúng classpath và entry point | `javac` trên máy chạy |
| Chạy JAR ứng dụng | Runtime tương thích; JAR đúng manifest và đủ dependency | IDE hoặc mã nguồn |
| Chạy bằng runtime đóng gói kèm app | Runtime image chứa module/API app cần, cấu hình khởi chạy | JDK đầy đủ ở máy người dùng |

Một cách triển khai thực tế là **máy phát triển/CI dùng JDK để build**, còn máy production dùng runtime tương thích hoặc runtime image đóng gói. Ứng dụng có thư viện ngoài, native library, biến môi trường, tệp cấu hình, DB hoặc network còn phải đáp ứng các phụ thuộc ấy: câu “write once, run anywhere” **không** loại bỏ mọi khác biệt hệ điều hành và hạ tầng.

## 7. Phiên bản JDK và tương thích khi chạy

Khi kiểm tra một máy hoặc cấu hình CI, cần tách **JDK đang biên dịch**, **mức tương thích đã build** và **runtime thật sự chạy**. Lệnh `javac -version` và `java -version` có thể báo hai phiên bản khác nhau nếu `PATH` trỏ đến hai bản cài.

| Tình huống | Điều cần kiểm tra |
| --- | --- |
| Build trên JDK mới để chạy Java 17 | Khi compiler hỗ trợ, dùng `javac --release 17 -encoding UTF-8 -d out JavaEnvironmentDemo.java` để nhắm cú pháp, class file và API chuẩn của Java 17 |
| Chạy class trên JVM cũ hơn đích biên dịch | Có thể gặp `UnsupportedClassVersionError`; kiểm tra phiên bản runtime và mức class file, không chữa bằng cách đổi tên tệp |
| Compiler và launcher đến từ hai bản JDK khác nhau | Xác nhận vị trí thực của `java`, `javac` và cấu hình build thay vì chỉ xem `JAVA_HOME` |
| Có thư viện ngoài hoặc thành phần native | `--release` không tự chứng minh mọi dependency và điều kiện môi trường chạy được trên runtime đích; cần chạy thử bản phân phối thực tế |

Phiên bản được chọn phải khớp yêu cầu của dự án, thư viện, CI và môi trường triển khai. Để xem **môi trường đang thực thi**, sử dụng `java -version` ngay trên máy đích hoặc các property `java.version`, `java.home` trong chương trình mẫu; không suy luận từ máy dùng để biên dịch.

## 8. JAVA_HOME, PATH và classpath: ba vai trò khác nhau

| Tên | Ý nghĩa | Lỗi thường gặp |
| --- | --- | --- |
| `JAVA_HOME` | Biến môi trường thường được công cụ build dùng để tìm thư mục JDK | Trỏ tới JDK khác với JDK mà terminal đang dùng |
| `PATH` | Danh sách thư mục hệ điều hành tìm kiếm lệnh `java`, `javac`… | `java` và `javac` nằm ở hai bộ cài khác nhau |
| **Classpath** (`-cp`/`--class-path`) | Nơi Java tìm class và một số resource của ứng dụng | Biên dịch xong nhưng runtime không tìm thấy main class hoặc dependency |

Một số kiểm tra vị trí lệnh:

**Windows PowerShell:**

~~~powershell
where.exe java
where.exe javac
$env:JAVA_HOME
~~~

**macOS / Linux (terminal shell phổ biến):**

~~~bash
command -v java
command -v javac
echo "$JAVA_HOME"
~~~

Bạn có thể cài nhiều JDK trên một máy. Các lệnh kiểm tra trên chỉ hỗ trợ chẩn đoán; **không tự sửa môi trường**. Đừng vội thay `PATH` cho toàn hệ thống khi dự án khác vẫn cần một phiên bản cũ.

Ví dụ phân biệt classpath và đường dẫn tệp: sau khi `javac -d out` tạo `out/JavaEnvironmentDemo.class`, ta chạy:

~~~bash
java -cp out JavaEnvironmentDemo
~~~

Không chạy bằng tên `JavaEnvironmentDemo.class` trong vị trí tên class. `java` cần **tên lớp** (hoặc tên lớp có package), không phải phần mở rộng `.class`.

Nếu source có `package demo;` và class được biên dịch thành `out/demo/Main.class` thì entry point là **`demo.Main`** và lệnh thường là `java -cp out demo.Main`. Đây là cơ chế tìm lớp, không phải một công cụ khác với JVM.

## 9. Khi gặp lỗi: chẩn đoán môi trường có thứ tự

Đầu tiên, chạy `java -version` và `javac -version`, sau đó tìm vị trí thật của hai lệnh bằng `where.exe` (Windows) hoặc `command -v` (macOS/Linux). So sánh kết quả với `JAVA_HOME` và JDK mà IDE/công cụ build chọn. Khi compiler và runtime đã được xác định, mới xem `-cp`, tên class và dependency.

| Hiện tượng | Câu hỏi chẩn đoán hữu ích |
| --- | --- |
| Có `java` nhưng không có `javac` | Máy chỉ có runtime hay `PATH` đang trỏ sai thư mục `bin` của JDK? |
| Terminal dùng Java A nhưng IDE build bằng Java B | IDE/Gradle chọn JDK nào? `JAVA_HOME` có bị ưu tiên khác với `PATH` không? |
| Build thành công, chạy báo `UnsupportedClassVersionError` | Class file cần phiên bản runtime nào; máy chạy đang dùng `java -version` nào? |
| `Could not find or load main class` | Lệnh `-cp` trỏ đến thư mục gốc chứa package chưa, và có dùng tên class đầy đủ thay vì `.class` không? |
| Chạy JAR nhưng thiếu class ở runtime | Dependency có thực sự được đóng gói hoặc đưa vào classpath/module path không? |

Một lỗi có thể xuất hiện ở bước khởi động hoặc tải class chứ không phải ở việc Java SE/JDK được “cài sai”. Hãy dựa vào thông báo cụ thể để xử lý đúng thành phần và giữ cấu hình các dự án khác trên máy.

## 10. Những hiểu lầm cần tránh

- **JDK không phải JVM.** JDK là bộ công cụ phát triển có runtime; JVM là thành phần thực thi bytecode.
- **Java SE không phải tên bộ cài của một hãng.** Nó là nền tảng/API chuẩn; một bản JDK cụ thể cung cấp triển khai.
- **Có lệnh `java` không bảo đảm có `javac`.** Hãy kiểm tra cả khả năng chạy lẫn biên dịch theo yêu cầu của máy.
- **“Java hiện đại hoàn toàn không còn JRE” là khẳng định quá rộng.** Có nhiều hình thức đóng gói runtime, gồm runtime-only và image tùy biến bằng `jlink`; không nên giả định phải có thư mục `jre` độc lập.
- **IDE và `JAVA_HOME` không tự quyết định kết quả của mọi terminal.** Kiểm tra đường dẫn `java`/`javac` được gọi, JDK của dự án và runtime đích.

## 11. Bài tập tự luyện có lời giải định hướng

**Bài 1 — Gọi đúng tên:** Một máy chỉ cần chạy `demo.jar` đã build. Máy đó bắt buộc phải cài full JDK không? Vì sao?

*Định hướng:* Không bắt buộc. Cần runtime tương thích, có đủ thư viện và dependency, cùng entry point đúng. Máy build mới cần compiler/JDK.

**Bài 2 — Giải thích hai lệnh:** So sánh `javac -encoding UTF-8 -d out JavaEnvironmentDemo.java` với `java -cp out JavaEnvironmentDemo`.

*Định hướng:* Lệnh một tạo bytecode `.class`; lệnh hai khởi động runtime để tìm và thực thi class đã biên dịch. Không dùng phần mở rộng `.class` trong tên entry point.

**Bài 3 — Phân tích môi trường:** `java -version` báo phiên bản A, `javac -version` báo phiên bản B. Có thể kết luận máy thiếu JDK không?

*Định hướng:* Chưa. Có thể cả hai được cài nhưng `PATH` ưu tiên hai vị trí khác nhau. Kiểm tra đường dẫn thực tế của cả hai lệnh và mục tiêu build/runtime.

**Bài 4 — Suy luận lỗi:** Bạn biên dịch bằng compiler mới, đưa tệp `.class` sang máy chạy Java cũ và nhận `UnsupportedClassVersionError`. Có nên đổi tên tệp `.class` để khắc phục?

*Định hướng:* Không. Đây là vấn đề định dạng/phiên bản bytecode. Chọn runtime tương thích hoặc biên dịch cho release thấp hơn mà code và thư viện thực sự hỗ trợ.

**Bài 5 — Thử nghiệm:** Chạy ví dụ `JavaEnvironmentDemo` bằng hai cách: (a) `javac` rồi `java -cp` và (b) `java JavaEnvironmentDemo.java`. Ghi lại điểm giống nhau về nội dung đầu ra và điểm khác nhau về cách launcher chuẩn bị mã chạy.

### Tự kiểm tra trước khi chuyển bài

Bạn đã nắm bài nếu có thể giải thích bằng lời của mình: **Java là ngôn ngữ; Java SE là nền tảng chuẩn; JDK giúp xây dựng và cũng chạy chương trình; JVM thực thi bytecode; runtime/JRE là tập thành phần cần để chạy**. Khi mở terminal, bạn biết kiểm tra `java`/`javac`, chạy ví dụ, nhận diện classpath và biết tại sao phiên bản build và runtime phải tương thích.
