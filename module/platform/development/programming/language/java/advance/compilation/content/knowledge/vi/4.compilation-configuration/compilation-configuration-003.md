# Thiết lập `javac -encoding` để biên dịch độc lập với môi trường

## 1. Vấn đề cần giải quyết

Mã nguồn Java là một **tệp byte** trên ổ đĩa. Để hiểu các chữ như `café`, `tiếng Việt`, `đường dẫn` hoặc ký tự trong comment và string literal, trình biên dịch phải giải mã các byte thành ký tự Unicode trước khi phân tích cú pháp. Nếu mã nguồn được lưu bằng UTF-8 nhưng `javac` đọc nó như một bảng mã khác, chương trình có thể:

- Báo lỗi ký tự không hợp lệ khi byte không giải mã được.
- Biên dịch **thành công nhưng sai dữ liệu**, chẳng hạn string `"café"` biến thành `"cafÃ©"`.
- Chỉ bị lỗi ở một hệ điều hành hoặc một máy trong CI; máy của tác giả vẫn chạy đúng.

Tùy thuộc vào bản JDK và môi trường, việc bỏ qua `-encoding` có thể khiến compiler dùng một bảng mã mặc định khác. Cách làm tái lập được là **thống nhất mã hóa tệp nguồn và khai báo rõ mã hóa đó cho compiler**.

Ví dụ chuẩn khi tệp `.java` được lưu bằng UTF-8:

~~~bash
javac -encoding UTF-8 -d out src/EncodingDemo.java
~~~

`-encoding UTF-8` nói với `javac`: “hãy **đọc các tệp mã nguồn Java** bằng UTF-8”. Nó không phải tùy chọn để điều chỉnh encoding của console, tệp dữ liệu mà ứng dụng đọc ở runtime hay giao thức mạng.

## 2. Cơ chế: byte nguồn → Unicode → bytecode

Quá trình liên quan đến encoding của mã nguồn có thể hình dung như sau:

~~~text
Tệp .java trên đĩa
  các byte (ví dụ UTF-8: c a f C3 A9)
          |
          | javac -encoding UTF-8
          v
Chuỗi ký tự Unicode: "café"
          |
          | phân tích Java, kiểm tra kiểu, sinh mã
          v
Tệp .class chứa hằng chuỗi đúng
          |
          | JVM chạy chương trình
          v
Ứng dụng xuất / lưu / truyền các ký tự (có quy tắc encoding riêng)
~~~

Ba lớp cần phân biệt:

1. **Encoding của tệp nguồn**: trình soạn thảo, formatter, công cụ tạo mã nguồn và Git lưu những byte nào trong `.java`.
2. **Encoding khi biên dịch**: `javac -encoding <charset>` xác định cách diễn giải byte đầu vào. Nó phải phù hợp encoding thực tế của tệp.
3. **Encoding khi chạy và hiển thị**: đọc/ghi file bằng `Files`, `InputStreamReader`, in ra terminal, kết nối database, HTTP... là các hoạt động khác. Thiết lập `-encoding` khi compile không tự cấu hình chúng.

Sau khi compiler giải mã đúng chuỗi nguồn thành Unicode, định dạng hằng chuỗi trong bytecode do đặc tả JVM quy định, không phải tùy chọn mã hóa văn bản đầu vào của trình biên dịch. Vì vậy **không cần** đặt `-encoding UTF-8` để “đổi định dạng `.class` sang UTF-8”.

## 3. Khi không truyền `-encoding`, Java dùng gì?

Hành vi mặc định không nên được dùng làm hợp đồng build:

| Môi trường | Điểm cần biết |
| --- | --- |
| JDK 17 trở về trước | Charset mặc định của Java thường phụ thuộc hệ điều hành, locale, cấu hình JVM; trên một số máy Windows có thể là mã hóa legacy, trên Linux thường là UTF-8. |
| JDK 18 trở lên | JEP 400 chuẩn hóa UTF-8 làm **default charset** của các API Java phổ biến, bao gồm mặc định của `javac` theo cấu hình thông thường; môi trường hoặc tùy chọn tương thích vẫn có thể ảnh hưởng trong các tình huống cụ thể. |
| Build qua Maven, Gradle, IDE, CI | Công cụ build có thể truyền encoding tường minh hoặc chọn cấu hình riêng. Điều cần kiểm chứng là **lệnh/thiết lập được truyền tới compiler**, không chỉ ngôn ngữ hiển thị của IDE. |

Ví dụ: cùng một mã nguồn UTF-8, một pipeline dùng JDK 17 trên máy có default charset Windows-1252 còn pipeline khác dùng JDK 21 mặc định UTF-8 thì kết quả có thể khác nhau nếu **không khai báo encoding**.

Với dự án hỗ trợ nhiều JDK hoặc chạy trên nhiều hệ điều hành, hãy đặt `UTF-8` ở cấu hình biên dịch thay vì ngầm dựa vào phiên bản JDK, locale hay thiết lập máy cá nhân.

**Không nhầm các tùy chọn:**

- `-encoding UTF-8`: cách **đọc nội dung tệp nguồn**.
- `--release 17`: giới hạn API/ngôn ngữ/bytecode đầu ra ở nền tảng Java 17.
- `-source 17`: mức cú pháp Java được phép sử dụng.
- `-target 17`: phiên bản class file đầu ra (không tự giới hạn API nền tảng).
- `-d out`: nơi lưu file `.class`.
- `-classpath` / `--class-path`: nơi tìm lớp phụ thuộc.
- `-J-Dfile.encoding=...`: truyền system property đến JVM chạy compiler; đây không phải cách thay thế rõ ràng, ổn định cho `-encoding` và không nên dùng để khắc phục bài toán này.

Chẳng hạn `javac --release 17 -encoding UTF-8 -d out src/EncodingDemo.java` kết hợp hai yêu cầu độc lập: dùng API/ngôn ngữ Java 17 và giải mã source bằng UTF-8.

## 4. Thực hành: một chương trình, hai cách giải mã

Tạo tệp `src/EncodingDemo.java`, lưu ở **UTF-8 không BOM**, với nội dung:

~~~java
public class EncodingDemo {
    public static void main(String[] args) {
        String word = "café";
        System.out.println(word);
    }
}
~~~

Tạo thư mục đầu ra và biên dịch bằng JDK 17 trở lên:

~~~bash
mkdir out
javac --release 17 -encoding UTF-8 -d out src/EncodingDemo.java
java -cp out EncodingDemo
~~~

Kết quả chuẩn:

~~~text
café
~~~

Các chữ `c`, `a`, `f` là ASCII; ký tự `é` có mã Unicode U+00E9. Trong **UTF-8**, `é` được biểu diễn bằng hai byte hex `C3 A9`. Với `-encoding UTF-8`, compiler khôi phục ký tự `é` như dự định.

Để quan sát lỗi mà **không sửa nội dung hay byte của `src/EncodingDemo.java`**, hãy biên dịch lại vào thư mục khác nhưng cố ý khai báo sai:

~~~bash
mkdir out-latin
javac --release 17 -encoding ISO-8859-1 -d out-latin src/EncodingDemo.java
java -cp out-latin EncodingDemo
~~~

Kết quả với source UTF-8 ở trên:

~~~text
cafÃ©
~~~

Vì bảng mã ISO-8859-1 diễn giải hai byte `C3 A9` thành hai ký tự `Ã` (U+00C3) và `©` (U+00A9), chuỗi sai `cafÃ©` được đặt trong bytecode. Compiler **không nhất thiết báo lỗi**: hai ký tự này vẫn hợp lệ bên trong string literal Java. Đó là lỗi *mojibake*.

Hai phép biên dịch này có thể chạy cạnh nhau nhờ các thư mục đầu ra `out` và `out-latin`. Lệnh dùng `mkdir` hoạt động trong shell phổ biến; nếu thư mục đã tồn tại, chỉ cần bỏ bước tạo. Nếu terminal không thể hiển thị Unicode chính xác, nội dung màn hình có thể khác dạng minh họa dù chuỗi trong class file đã đúng: xem phần chẩn đoán bên dưới.

### Khi byte đầu vào thực sự không hợp lệ

Nếu source là UTF-8 nhưng người dùng chọn một charset mà một số byte không hợp lệ, `javac` có thể báo lỗi dạng `unmappable character for encoding ...` hoặc `illegal character`, tùy bảng mã và vị trí ký tự. Không được suy luận rằng **mọi** lần chọn sai encoding đều gây lỗi compile; trường hợp `café` ở trên là bằng chứng ngược lại.

Ngược lại, một tệp được lưu thực sự bằng ISO-8859-1 có thể cần `-encoding ISO-8859-1` để đọc đúng trong giai đoạn chuyển đổi. Không chỉ thay tham số `-encoding UTF-8` khi byte nguồn vẫn là ISO-8859-1: phải **chuyển mã tệp nguồn** sang UTF-8 trước, hoặc vẫn khai báo encoding thực tế cho đến khi chuyển xong.

## 5. Cú pháp và phạm vi của tùy chọn `-encoding`

Cú pháp phổ biến:

~~~bash
javac -encoding UTF-8 -d out src/EncodingDemo.java
javac --release 17 -encoding UTF-8 -d out src/EncodingDemo.java
~~~

- Tham số phía sau `-encoding` là tên charset Java nhận biết, chẳng hạn `UTF-8`, `US-ASCII`, `ISO-8859-1`, `windows-1252`. Ưu tiên cách viết `UTF-8` để dễ đọc và thống nhất.
- `-encoding` áp dụng cho tệp **mã nguồn mà invocation của compiler đọc**, kể cả các tệp nguồn được truy tìm qua cấu hình source path. Khi compiler/annotation processor sinh và biên dịch thêm source, cần xem cấu hình riêng của processor hoặc công cụ tạo file để đảm bảo các byte được sinh khớp encoding. Không giả định nó chuyển đổi mọi artifact phát sinh.
- `-encoding` là thiết lập theo **lần gọi `javac`**, không biến tệp nguồn đang lưu bằng bảng mã cũ thành UTF-8.
- Một invocation `javac` dùng một lựa chọn encoding nguồn cho các tệp nó xử lý. Nếu dự án trộn file UTF-8 và legacy charset, nên chuẩn hóa toàn bộ source thay vì mong compiler tự đoán encoding riêng từng file.

Với cấu trúc gói:

~~~text
project/
  src/
    demo/
      App.java
  out/
~~~

Nếu `App.java` khai báo `package demo;`, lệnh và tên lớp khi chạy sẽ là:

~~~bash
javac -encoding UTF-8 -d out src/demo/App.java
java -cp out demo.App
~~~

`-d` và `package` điều khiển đường dẫn file lớp; encoding không thay đổi quy tắc đặt tên hay cấu trúc package.

## 6. Cấu hình trong Maven

Trong dự án Maven, thay vì nhắc mọi người tự nhập `javac -encoding`, hãy khai báo encoding ngay trong `pom.xml`:

~~~xml
<project>
    <!-- Các phần modelVersion, groupId, artifactId, version
         và cấu hình khác của POM đầy đủ nằm ngoài đoạn trích. -->
    <properties>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
        <maven.compiler.release>17</maven.compiler.release>
    </properties>
</project>
~~~

Đoạn XML này minh họa **phần cần thêm vào POM đang có**, không phải POM tối thiểu độc lập. Maven Compiler Plugin thường lấy `project.build.sourceEncoding` làm encoding của các source Java khi không bị ghi đè. Thuộc tính `maven.compiler.release` yêu cầu cấu hình compiler hỗ trợ `--release`.

Nếu muốn biểu đạt trực tiếp trong plugin, dùng cấu hình `encoding`:

~~~xml
<build>
    <plugins>
        <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-compiler-plugin</artifactId>
            <configuration>
                <encoding>UTF-8</encoding>
                <release>17</release>
            </configuration>
        </plugin>
    </plugins>
</build>
~~~

Đây là **đoạn trong phần tử `<project>` của POM đang có**. Với dự án đã có cấu hình plugin, hãy cập nhật cấu hình đó, tránh tạo hai khai báo plugin mâu thuẫn. Plugin có thể có cấu hình ở parent POM, profile hoặc command line; khi chẩn đoán hãy kiểm tra effective POM và compiler invocation thực sự.

Ví dụ kiểm tra sau khi lưu cấu hình:

~~~bash
mvn clean compile
~~~

Lưu ý `project.build.sourceEncoding` được một số Maven plugin khác dùng làm encoding mặc định (ví dụ xử lý resource theo cấu hình plugin), nhưng **`-encoding` của `javac` chỉ phục vụ mã nguồn**. Một số resource, template hoặc dữ liệu runtime có cấu hình encoding riêng và cần xử lý rõ ràng.

## 7. Cấu hình trong Gradle

Với Gradle Groovy DSL (`build.gradle`):

~~~groovy
tasks.withType(JavaCompile).configureEach {
    options.encoding = 'UTF-8'
    options.release = 17
}
~~~

Với Gradle Kotlin DSL (`build.gradle.kts`):

~~~kotlin
tasks.withType<JavaCompile>().configureEach {
    options.encoding = "UTF-8"
    options.release.set(17)
}
~~~

Hai đoạn này là **cấu hình build**, không phải mã Java đưa trực tiếp cho `javac`. Chúng áp dụng encoding cho các tác vụ kiểu `JavaCompile`, bao gồm các source set Java do Gradle quản lý. Cấu hình phát triển phải đảm bảo Gradle dùng JDK hỗ trợ Java 17, chẳng hạn qua Java toolchain.

Chạy:

~~~bash
./gradlew compileJava
~~~

Trên Windows, dùng `gradlew.bat compileJava`. Gradle wrapper cần tồn tại trong repository. Khi có annotation processor, sinh source, Kotlin hoặc các tác vụ biên dịch tùy biến, hãy kiểm tra encoding của **công cụ tương ứng**; `options.encoding` dành cho `JavaCompile`, không tự quyết định encoding của mọi plugin.

## 8. Đảm bảo file nguồn thực sự là UTF-8

Thêm `-encoding UTF-8` chỉ đúng khi file thật sự đã được lưu ở UTF-8. Một quy trình tốt gồm:

1. **Thống nhất quy ước**: toàn bộ `.java` dùng UTF-8, ưu tiên không BOM. Áp dụng với mã nguồn do người lập trình và generator sinh ra.
2. **Cấu hình editor/IDE**: đặt encoding dự án và file là UTF-8. Nếu nhận được tệp legacy, chọn thao tác *convert encoding* để thay đổi byte; thao tác *reopen with encoding* chỉ đổi cách đọc, có thể chưa lưu lại.
3. **Cấu hình build**: Maven/Gradle và các script `javac` dùng encoding tường minh.
4. **CI kiểm chứng**: build trên máy sạch với JDK được hỗ trợ; có test string chứa chữ có dấu để phát hiện lỗi bị biên dịch thành mojibake.
5. **Kiểm tra khi chuyển mã**: xem diff chữ có dấu, comment, string literal, annotation và text block; nếu source có chuỗi `cafÃ©` từ trước thì mặc dù UTF-8 hợp lệ, logic vẫn sai.

Tệp nguồn Java thường nên lưu **UTF-8 không BOM**. BOM là các byte đánh dấu có thể gây vấn đề cho một số phiên bản compiler hoặc pipeline; không cần BOM để `javac -encoding UTF-8` nhận biết UTF-8. Việc xử lý BOM khác nhau giữa công cụ, nên chọn một quy ước duy nhất, có kiểm chứng.

Một tệp chỉ chứa ký tự ASCII không giúp phân biệt UTF-8 và nhiều mã hóa ASCII-compatible. Vì vậy, việc compile thành công với `-encoding UTF-8` không chứng minh chắc chắn mọi file đã chuyển mã đúng.

### `.editorconfig` để giảm sai lệch

Có thể bổ sung tệp `.editorconfig` ở gốc dự án:

~~~ini
root = true

[*.java]
charset = utf-8
end_of_line = lf
~~~

Đây là cấu hình cho editor hoặc công cụ **có hỗ trợ EditorConfig**; nó không tự thay `javac -encoding UTF-8` và không tự chuyển mã các tệp cũ. `end_of_line = lf` chuẩn hóa xuống dòng trong source để giảm diff giữa môi trường, nhưng ký tự xuống dòng là vấn đề khác với bảng mã.

## 9. Chẩn đoán lỗi encoding theo từng lớp

| Triệu chứng | Khả năng / kiểm tra | Hướng xử lý |
| --- | --- | --- |
| `javac` báo `unmappable character` | Byte trong source không phù hợp charset được khai báo | Xác minh encoding gốc; chuyển file hoặc đặt đúng `-encoding`. |
| Biên dịch thành công nhưng string thành `cafÃ©` | UTF-8 bị đọc như ISO-8859-1/Windows-1252 hoặc nội dung đã hỏng từ trước | Kiểm tra raw byte source và giá trị string đã compile; sửa nguồn nếu đã mojibake. |
| `java` in sai chữ nhưng unit test so sánh string vẫn đúng | Charset terminal, font hoặc đường truyền stdout khác nhau | Kiểm tra encoding/terminal và cách decode output. Không tùy tiện đổi `javac -encoding`. |
| IDE đúng, CI sai | Compiler invocation, JDK, charset mặc định hoặc cách sinh nguồn khác | Cố định encoding trong build, kiểm tra toolchain và log CI. |
| Chỉ file do generator sinh ra sai | Generator ghi bằng charset khác `javac` đang đọc | Đặt encoding khi **ghi source**, rồi đặt encoding khi compiler **đọc source**. |
| Resource `.properties`, CSV, JSON sai | Đường đọc resource hoặc parser có quy định mã hóa khác | Cấu hình plugin và API đọc/ghi dữ liệu riêng. |
| File legacy sai sau khi đặt UTF-8 | Byte vẫn ở encoding cũ | Chuyển mã thật sự, sau đó kiểm tra diff và chạy test. |

Cách khoanh vùng ngắn gọn:

- **Bước A:** Xem byte thực tế của `.java`, nhất là đoạn chứa chữ có dấu; với `café` lưu UTF-8, phần `é` phải là `C3 A9`.
- **Bước B:** Xem lệnh compiler hoặc build config; cần xác nhận `UTF-8` thực sự được truyền cho `javac`.
- **Bước C:** Kiểm tra giá trị string trong test chạy JVM, không kết luận chỉ từ chữ hiển thị trên terminal.
- **Bước D:** Nếu lỗi chỉ xảy ra khi đọc file/ghi output ở runtime, chuyển sang kiểm tra API I/O và console; `-encoding` compile không điều khiển bước đó.

Trong mã Java chạy runtime, nếu cần đọc file UTF-8 thì truyền charset một cách rõ ràng, ví dụ:

~~~java
String content = java.nio.file.Files.readString(
        java.nio.file.Path.of("data.txt"),
        java.nio.charset.StandardCharsets.UTF_8);
~~~

Đây là **đoạn đặt bên trong một phương thức** và phương thức cần khai báo/xử lý `IOException`. Nó phục vụ **runtime file I/O**, khác vai trò với `javac -encoding UTF-8`. Với các API Java 17 có mặc định UTF-8, việc ghi tường minh vẫn giúp tài liệu hóa ý định của dự án.

## 10. Lỗi phổ biến và ranh giới của giải pháp

**Chỉ đổi default encoding của máy.** Cách này vô tình làm build phụ thuộc cấu hình toàn hệ thống hoặc IDE cá nhân. Hãy đặt `-encoding UTF-8` trong compiler options hoặc build script và thống nhất file source.

**Chỉ chỉnh `-Dfile.encoding`.** Đây là system property của JVM, cách thiết lập/hành vi thay đổi theo thế hệ Java và không mô tả riêng encoding nguồn. Dùng trực tiếp `-encoding` cho `javac`. Đừng nhầm với các stream do ứng dụng tự tạo khi chạy.

**Chỉ đổi tham số mà không chuyển file.** Nếu file thực tế là Windows-1252, thêm `-encoding UTF-8` có thể khiến lỗi nặng hơn. Source bytes và khai báo compiler phải ăn khớp.

**Suy đoán từ việc không có lỗi compile.** Nhiều bảng mã cho kết quả chữ sai nhưng source vẫn là cú pháp Java hợp lệ. Test nội dung string quan trọng, nhất là thông báo, nhãn UI, regex và chuỗi so sánh.

**Nghĩ `-encoding` điều khiển terminal.** Một class được compile đúng vẫn có thể hiển thị ký tự không đúng do terminal/font/charset. Cũng có trường hợp terminal hiển thị được `cafÃ©` “rất rõ” nhưng đó chính là dữ liệu sai đã compile vào chương trình.

**Lẫn với Unicode escape trong mã Java.** Escape như `\u00E9` sử dụng ký tự ASCII để biểu diễn `é` và được xử lý theo quy tắc từ vựng của Java. Nó có thể hữu ích trong trường hợp đặc biệt, nhưng thay toàn bộ chữ có dấu bằng escape không giải quyết chuẩn hóa file và làm source kém dễ đọc. Unicode escape còn được xử lý rất sớm, kể cả ở một số vị trí comment, nên không phải công cụ chuyển mã tổng quát.

**Giả định mọi tool cùng hỗ trợ một charset.** Editor, compiler, tài nguyên build, processor, script và runtime cần nhất quán; mục tiêu là thiết lập encoding ở từng nơi thực sự đọc hoặc ghi văn bản.

## 11. Quy trình áp dụng cho dự án đang hoạt động

1. **Chọn UTF-8** cho toàn bộ Java source; kiểm tra xem có file legacy chứa chữ khác ASCII cần chuyển không.
2. **Chuyển mã có kiểm soát** các file legacy sang UTF-8 và đọc diff để tránh hỏng literal/comment.
3. **Ghi cấu hình vào build**: `-encoding UTF-8`, `project.build.sourceEncoding` trong Maven, hoặc `JavaCompile.options.encoding` trong Gradle.
4. **Đồng bộ IDE/editor** để file mới được tạo đúng UTF-8; cân nhắc `.editorconfig`.
5. **Biên dịch sạch** bằng JDK được hỗ trợ trên CI và máy cá nhân, kiểm tra source do generator tạo.
6. **Chạy test chứa Unicode thực tế** (ví dụ `"café"`, tiếng Việt có dấu, ký tự không thuộc Latin-1), đồng thời phân biệt lỗi runtime/terminal với lỗi compiler.
7. **Giữ cấu hình trong repository** để mọi người và hệ thống CI sử dụng cùng quy tắc.

### Tự kiểm tra

**Câu 1.** Tệp source được lưu UTF-8 và có chữ `café`. Dùng `javac -encoding ISO-8859-1` có bắt buộc lỗi compile không? **Không.** Mã vẫn có thể biên dịch nhưng string đổi thành `cafÃ©`.

**Câu 2.** Dùng JDK 21 mặc định UTF-8 thì có cần khai báo encoding trong build nữa không? **Nên có.** Nó thể hiện rõ yêu cầu của dự án và bảo vệ các pipeline dùng JDK khác hoặc compiler invocation được cấu hình khác.

**Câu 3.** Thêm `-encoding UTF-8` có làm `Files.readString` hiểu mọi file dữ liệu là UTF-8 không? **Không.** Compile-time source decoding và runtime I/O là hai vấn đề khác nhau.

**Câu 4.** Source đang lưu bằng Windows-1252; cách đúng để chuẩn hóa UTF-8 là gì? **Chuyển mã byte của tệp thật sự**, xác minh nội dung, rồi cấu hình compiler đọc UTF-8.

**Câu 5.** Nếu in ra console sai dấu nhưng unit test giá trị chuỗi đúng, cần sửa ngay `-encoding` không? **Chưa.** Hãy kiểm tra encoding/font của terminal và cách truyền stdout trước.

**Điểm cốt lõi:** `-encoding` định nghĩa cách `javac` chuyển **byte của tệp `.java` thành ký tự Unicode**. Dùng `-encoding UTF-8` cùng với tệp nguồn thực sự lưu bằng UTF-8, cấu hình trực tiếp trong build và test bằng dữ liệu Unicode để tránh kết quả phụ thuộc máy, hệ điều hành hoặc JDK.
