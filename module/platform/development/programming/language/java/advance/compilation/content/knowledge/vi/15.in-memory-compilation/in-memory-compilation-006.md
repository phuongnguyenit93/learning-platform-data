# Ánh xạ chẩn đoán về đúng nguồn và vị trí ban đầu khi biên dịch Java trong bộ nhớ

Khi dùng `javax.tools.JavaCompiler` để biên dịch mã nguồn được tạo trong bộ nhớ, compiler có thể trả về một `Diagnostic` trỏ tới tệp ảo như `string:///lab/First.java`. Nhưng người học hoặc người dùng IDE lại đang sửa **một tài liệu, đoạn mã trong trình soạn thảo hoặc snippet đầu vào ban đầu**. Nếu công cụ tự thêm package, class bọc, dòng import hoặc sinh mã trung gian trước khi gọi compiler, dòng/cột mà javac báo có thể **khác dòng/cột ở tài liệu gốc**.

Vì vậy, bài toán không chỉ là “lấy diagnostic từ javac” mà còn là **ánh xạ đúng cặp (nguồn, vị trí)** từ không gian nguồn compiler đã thấy sang tài liệu mà người dùng thực sự viết. Làm sai phép ánh xạ có thể khiến IDE gạch chân nhầm dòng, hệ thống chấm bài chỉ nhầm đáp án hoặc một dịch vụ báo lỗi của người dùng A lên đoạn nguồn của người dùng B.

Bài học có hai mức:

1. **Biên dịch nguyên văn một hay nhiều tệp ảo:** có thể dùng `Diagnostic.getSource()` cùng `getLineNumber()`, `getColumnNumber()` và `getPosition()` để liên kết diagnostic về nguồn đúng, nếu tệp ảo thực sự chứa đúng nội dung gốc.
2. **Biên dịch nguồn đã biến đổi:** cần một **source map / provenance map** được ghi khi tạo mã để chuyển offset, dòng và cột của mã sinh về nguồn gốc. Chỉ dựa vào số dòng của javac là không đủ.

Các ví dụ dùng **Java 17+**, `javax.tools` và compiler có trong JDK. Hai chương trình quan trọng đã được chạy kiểm chứng bằng **OpenJDK 21**.

## 1. Diagnostic đang nói đến nguồn nào?

Với một file vật lý, javac thường hiển thị thông báo gắn với đường dẫn nguồn thực. Với một file trong bộ nhớ, `JavaFileObject` đóng vai trò đại diện cho file nguồn và có thể mang URI do công cụ cung cấp.

Ví dụ một source object có URI:

~~~text
string:///lab/First.java
~~~

Compiler có thể trả diagnostic mang:

~~~text
source  = string:///lab/First.java
line    = 5
column  = 28
kind    = ERROR
message = cannot find symbol ...
~~~

Đây là **ví dụ minh họa về các trường**, không phải toàn bộ stdout được bảo đảm của một phiên bản compiler. Các thông tin truy cập qua API `Diagnostic` độc lập với cách javac trình bày caret trên stderr.

Với Java Compiler API, những phương thức quan trọng là:

| Phương thức | Ý nghĩa |
| --- | --- |
| `getSource()` | Nguồn mà compiler gắn với diagnostic; có thể là `null` |
| `getPosition()` | Offset từ đầu source object, bắt đầu từ **0** khi hợp lệ |
| `getLineNumber()` | Số dòng của vị trí diagnostic, bắt đầu từ **1** khi hợp lệ |
| `getColumnNumber()` | Số cột của vị trí diagnostic, bắt đầu từ **1** khi hợp lệ |
| `getStartPosition()` | Vị trí đầu vùng lỗi mà compiler cung cấp |
| `getEndPosition()` | Vị trí cuối vùng lỗi mà compiler cung cấp |
| `getKind()` | `ERROR`, `WARNING`, `NOTE`, v.v. |
| `getCode()` | Mã diagnostic theo compiler implementation; có thể null |
| `getMessage(Locale)` | Nội dung thông điệp; có thể phụ thuộc implementation/locale |

Theo tài liệu `javax.tools.Diagnostic`, những diagnostic không gắn với vị trí hoặc file là **hợp lệ**. Khi không có vị trí, API dùng `Diagnostic.NOPOS`; nguồn có thể là `null`. Do đó không thiết kế hệ thống theo giả định mọi warning đều có dòng, cột và khoảng ký tự để gạch chân.

### 1.1. Có ba hệ tọa độ cần phân biệt

**Tọa độ của tài liệu gốc:** vị trí trong văn bản mà người dùng thấy trước khi công cụ thêm/bớt nội dung. Nếu editor đánh số dòng từ 1, cột từ 1 thì một vị trí có thể là dòng 2, cột 20.

**Tọa độ của `JavaFileObject` compiler nhận:** offset và dòng/cột trên chuỗi mã được truyền vào `getCharContent(boolean)`. Khi bạn thêm 2 dòng class wrapper, chỗ lỗi nằm tại dòng 4 của nguồn gửi compiler mặc dù chỉ ở dòng 2 của snippet gốc.

**Tọa độ trình bày của UI:** có thể là cặp line/column bắt đầu từ 0 (ví dụ nhiều editor APIs), hoặc offset theo UTF-16, hoặc điểm ảnh. Việc chuyển từ dữ liệu compiler sang UI cũng cần một bước quy đổi nhất quán.

**Không dùng số dòng trên source ảo làm số dòng gốc nếu có bất kỳ phép biến đổi nào.** Cần biết nguồn ảo và phép biến đổi đã áp dụng.

## 2. Bước nền tảng: giữ danh tính nguồn ảo ổn định

Khi tạo tệp trong bộ nhớ, có thể kế thừa `SimpleJavaFileObject` và ghi đè `getCharContent(boolean)`:

~~~java
import java.net.URI;
import javax.tools.JavaFileObject;
import javax.tools.SimpleJavaFileObject;

final class MemorySource extends SimpleJavaFileObject {
    private final String code;

    MemorySource(String name, String code) {
        super(
            URI.create("string:///lab/" + name),
            JavaFileObject.Kind.SOURCE
        );
        this.code = code;
    }

    @Override
    public CharSequence getCharContent(
            boolean ignoreEncodingErrors) {
        return code;
    }
}
~~~

Đây là **lớp minh họa không chứa `main`**; đưa nó vào một chương trình gọi compiler để sử dụng. URI có đuôi `.java` để phù hợp với `JavaFileObject.Kind.SOURCE`, và tên file nên phù hợp với tên public top-level class tương ứng.

Các quy tắc thực hành:

- Mỗi nguồn cần một **URI riêng** trong tập đầu vào của compilation task, ví dụ `string:///lab/First.java` và `string:///lab/Second.java`.
- **Không dùng một URI cho nhiều tài liệu khác nhau** rồi chỉ dựa vào tên hiển thị ở giao diện.
- Khi nhiều request/phiên bản tài liệu cùng tồn tại, cần thêm **document ID + revision/version** trong dữ liệu quản lý của ứng dụng. Một URI tương đối đẹp chưa đủ để bảo đảm toàn cục.
- Ghi lại **chính xác chuỗi source đã đưa vào compiler**. Nếu compiler diagnostic dựa trên văn bản bản A nhưng giao diện hiển thị bản B đã sửa, vị trí có thể sai dù mã mapping đúng.
- Không mặc định `toUri()` là đường dẫn hệ thống file: scheme `string:///` là định danh tệp ảo do ứng dụng quy ước, không phải file trên đĩa.
- Không tin URI từ một nguồn không đáng tin như đường dẫn file thật mà chưa kiểm tra: ứng dụng cần tránh rò rỉ đường dẫn nội bộ hoặc nhầm tenant khi hiển thị lỗi.

**Mấu chốt:** trong tình huống không biến đổi nội dung, quan hệ ánh xạ là một-một giữa **URI tệp ảo + snapshot nội dung** và tài liệu nguồn gốc. Nếu không thể xác định cặp này, không nên cố gán dòng/cột cho một file bất kỳ.

## 3. Ví dụ hoàn chỉnh 1: hai nguồn trong bộ nhớ, hai lỗi ở hai tệp khác nhau

Ví dụ này kiểm tra việc **đọc đúng `getSource()`** thay vì gán toàn bộ diagnostics cho tệp đầu tiên. Tạo `SourceDiagnostics.java`:

~~~java
import java.net.URI;
import java.nio.file.Files;
import java.util.ArrayList;
import java.util.List;
import javax.tools.Diagnostic;
import javax.tools.DiagnosticCollector;
import javax.tools.JavaCompiler;
import javax.tools.JavaFileObject;
import javax.tools.SimpleJavaFileObject;
import javax.tools.StandardJavaFileManager;
import javax.tools.ToolProvider;

public class SourceDiagnostics {
    static final class MemorySource extends SimpleJavaFileObject {
        private final String code;

        MemorySource(String name, String code) {
            super(
                URI.create("string:///lab/" + name),
                Kind.SOURCE
            );
            this.code = code;
        }

        @Override
        public CharSequence getCharContent(boolean ignore) {
            return code;
        }
    }

    public static void main(String[] args) throws Exception {
        String first = String.join("\n",
            "package lab;",
            "public class First {",
            "    public void run() {",
            "        int ok = 1;",
            "        System.out.println(okk);",
            "    }",
            "}");

        String second = String.join("\n",
            "package lab;",
            "public class Second {",
            "    int answer = \"wrong\";",
            "}");

        JavaCompiler compiler =
            ToolProvider.getSystemJavaCompiler();

        DiagnosticCollector<JavaFileObject> diagnostics =
            new DiagnosticCollector<>();

        try (StandardJavaFileManager manager =
                 compiler.getStandardFileManager(
                     diagnostics, null, null)) {

            var output = Files.createTempDirectory("compiler-demo-");

            boolean success = compiler.getTask(
                null, manager, diagnostics,
                List.of("-proc:none", "-d", output.toString()),
                null,
                List.of(
                    new MemorySource("First.java", first),
                    new MemorySource("Second.java", second)
                )
            ).call();

            System.out.println("success=" + success);
        }

        List<String> errors = new ArrayList<>();

        for (Diagnostic<? extends JavaFileObject> d
                : diagnostics.getDiagnostics()) {
            if (d.getKind() != Diagnostic.Kind.ERROR ||
                    d.getSource() == null) {
                continue;
            }

            String path = d.getSource().toUri().getPath();
            String file =
                path.substring(path.lastIndexOf('/') + 1);

            errors.add(
                file + ":" + d.getLineNumber() + ":" +
                d.getKind()
            );
        }

        errors.sort(String::compareTo);
        errors.forEach(System.out::println);
    }
}
~~~

Biên dịch và chạy trên JDK 17+:

~~~bash
javac SourceDiagnostics.java
java SourceDiagnostics
~~~

**Stdout đã kiểm chứng với OpenJDK 21:**

~~~text
success=false
First.java:5:ERROR
Second.java:3:ERROR
~~~

**Vì sao có hai diagnostics?**

- `First.java` có tham chiếu `okk` chưa khai báo ở dòng 5, trong khi tên biến đã khai báo là `ok`.
- `Second.java` cố gán `String` vào field kiểu `int` ở dòng 3.
- Cả hai đoạn mã đều có URI riêng. Collector nhận diagnostic gắn với nguồn tương ứng.
- Chương trình **lọc ERROR, bỏ diagnostic không có source, rồi sắp xếp chuỗi** để trình bày ổn định. Thứ tự javac phát diagnostic không nên được dùng làm khóa nhận diện nguồn.

**Không được rút file name cuối làm identity dài hạn.** Đoạn code chỉ in `First.java` và `Second.java` cho người học dễ đọc. Trong hệ thống thật, hai package hoặc hai tài liệu của người dùng khác nhau có thể cùng tên `Main.java`; cần dùng URI đầy đủ hoặc một source ID nội bộ đã map đến URI.

### 3.1. Compiler không tự chạy chương trình vừa biên dịch

`success=false` là kết quả của **compilation task**; chương trình chủ `SourceDiagnostics` vẫn chạy và in thông tin lỗi bình thường. Nó không có nghĩa Java runtime chạy code của `First` hoặc `Second`. Không được gộp **diagnostic khi compile** với exception khi chạy chương trình đã biên dịch.

Trong ví dụ, `-proc:none` tắt annotation processing để phép thử đơn giản và tránh processor ngoài ý muốn làm thay đổi diagnostics. `-d` chỉ thư mục output tạm; vì source có lỗi nên không nên giả định compiler sinh class hợp lệ cho cả hai.

## 4. Các trường hợp getSource() và getPosition() không đủ

Một hệ thống báo lỗi đáng tin phải hỗ trợ:

| Trạng thái | Hành vi phù hợp |
| --- | --- |
| `getSource()==null` | Hiển thị diagnostic tổng quát, không chọn bừa một file |
| `getPosition()==Diagnostic.NOPOS` | Hiển thị message nhưng không tạo highlight có vị trí |
| `getLineNumber()==NOPOS` | Không tự gán dòng 1 |
| Offset vượt độ dài snapshot | Từ chối mapping và ghi nhận diagnostic không thể ánh xạ |
| URI không thuộc source registry của task | Hiển thị như diagnostic từ nguồn chưa nhận diện; có thể là generated source |
| Source object thuộc revision cũ | Không áp vị trí lên văn bản revision mới |
| Diagnostic chỉ tới đoạn wrapper do tool sinh | Gắn với generated source, không đổ lỗi cho snippet của người dùng |
| Diagnostic span cắt qua nhiều nguồn gốc | Không gạch chân giả một khoảng liên tục trong tài liệu gốc |

Một số diagnostic liên quan tùy chọn compiler hoặc môi trường build không gắn với một tệp `.java`. Đó không phải lỗi của API; chỉ là **loại vấn đề không có vị trí nguồn riêng**.

**Không bỏ qua message và diagnostic kind** khi không có vị trí. Một warning không có source vẫn có thể quan trọng, chẳng hạn vì tùy chọn hoặc cấu hình annotation processor.

## 5. Vấn đề khó hơn: khi source gốc đã được biến đổi

Giả sử người dùng nhập hai dòng sau vào một trình soạn snippet:

~~~java
int ok = 1;
System.out.println(unknown);
~~~

Đây là **mảnh mã dùng trong method**, không phải tệp Java đầy đủ để tự biên dịch. Công cụ tạo một class wrapper:

~~~java
class Wrapper {
    static void run() {
int ok = 1;
System.out.println(unknown);
    }
}
~~~

Compiler thấy lỗi ở dòng **4** của tệp `Wrapper.java` do nó đã được thêm hai dòng phía trên. Nhưng trong editor, `unknown` nằm ở dòng **2**. Nếu hệ thống gạch chân dòng 4 của editor, nó đã ánh xạ sai.

Đường đi khái niệm:

~~~text
Nguồn gốc trong editor: snippet, revision R
  line 1: int ok = 1;
  line 2: System.out.println(unknown);
                  |
                  | thêm prefix + suffix
                  v
Nguồn gửi compiler: string:///generated/Wrapper.java
  line 1: class Wrapper {
  line 2:     static void run() {
  line 3: int ok = 1;
  line 4: System.out.println(unknown);
  line 5:     }
  line 6: }
                  |
                  v
Diagnostic: Wrapper.java, line 4, column 20
                  |
                  | source-map dựa trên vùng ký tự gốc
                  v
Hiển thị đúng: snippet revision R, line 2, column 20
~~~

Trong trường hợp **chỉ thêm một prefix và một suffix, giữ nguyên ký tự snippet ở giữa**, ánh xạ offset đơn giản:

~~~text
generated = prefix + original + suffix

startOfOriginal = prefix.length()
endOfOriginal   = startOfOriginal + original.length()

Nếu vị trí p nằm trong [startOfOriginal, endOfOriginal):
    originalOffset = p - startOfOriginal

Nếu không:
    vị trí thuộc wrapper hoặc nằm ngoài vùng được ánh xạ
~~~

Mấu chốt là **ghi nhận quá trình tạo mã** chứ không đoán vị trí bằng cách tìm đoạn chữ giống nhau trong tệp đã sinh. Hai đoạn nguồn có thể trùng hệt nội dung; tìm kiếm bằng chuỗi sẽ gây nhầm.

## 6. Ví dụ hoàn chỉnh 2: ánh xạ diagnostic của wrapper về snippet gốc

Tạo `MapWrapped.java`:

~~~java
import java.net.URI;
import java.util.List;
import javax.tools.Diagnostic;
import javax.tools.DiagnosticCollector;
import javax.tools.JavaCompiler;
import javax.tools.JavaFileObject;
import javax.tools.SimpleJavaFileObject;
import javax.tools.ToolProvider;

public class MapWrapped {
    static final class Source extends SimpleJavaFileObject {
        private final String code;

        Source(String code) {
            super(
                URI.create("string:///generated/Wrapper.java"),
                Kind.SOURCE
            );
            this.code = code;
        }

        @Override
        public CharSequence getCharContent(boolean ignore) {
            return code;
        }
    }

    static int[] lineColumn(String source, int offset) {
        int line = 1;
        int column = 1;

        for (int i = 0; i < offset; i++) {
            if (source.charAt(i) == '\n') {
                line++;
                column = 1;
            } else {
                column++;
            }
        }

        return new int[] { line, column };
    }

    public static void main(String[] args) {
        String original =
            "int ok = 1;\nSystem.out.println(unknown);";

        String prefix =
            "class Wrapper {\n    static void run() {\n";

        String suffix = "\n    }\n}\n";

        String generated = prefix + original + suffix;

        int start = prefix.length();
        int end = start + original.length();

        JavaCompiler compiler =
            ToolProvider.getSystemJavaCompiler();

        DiagnosticCollector<JavaFileObject> diagnostics =
            new DiagnosticCollector<>();

        boolean ok = compiler.getTask(
            null, null, diagnostics,
            List.of("-proc:none"),
            null,
            List.of(new Source(generated))
        ).call();

        System.out.println("success=" + ok);

        for (Diagnostic<? extends JavaFileObject> d
                : diagnostics.getDiagnostics()) {
            if (d.getKind() != Diagnostic.Kind.ERROR) {
                continue;
            }

            long p = d.getPosition();

            if (p == Diagnostic.NOPOS ||
                    p < start || p >= end) {
                System.out.println("unmapped");
                continue;
            }

            int relative = (int) p - start;
            int[] location = lineColumn(original, relative);

            System.out.println(
                "compiled=" + d.getLineNumber() + ":" +
                d.getColumnNumber()
            );
            System.out.println(
                "original=" + location[0] + ":" +
                location[1]
            );
        }
    }
}
~~~

Biên dịch/chạy bằng JDK 17+ có system compiler:

~~~bash
javac MapWrapped.java
java MapWrapped
~~~

**Stdout đã kiểm chứng trên OpenJDK 21:**

~~~text
success=false
compiled=4:20
original=2:20
~~~

### 6.1. Từng bước của phép ánh xạ

- `original` chứa chính xác đoạn người dùng nhập: hai dòng, mỗi dòng kết thúc theo quy tắc LF trong string Java.
- `prefix` và `suffix` là nội dung hệ thống sinh, **không thuộc tài liệu gốc**.
- `start` và `end` định nghĩa **vùng một-một** giữa đoạn snippet gốc và một khoảng ký tự trong `generated`.
- `d.getPosition()` lấy offset do compiler trả về trên source object `Wrapper.java`.
- Vì vị trí nằm trong khoảng gốc, ta tính `relative=p-start`.
- `lineColumn(original, relative)` đếm dòng/cột trên **chuỗi snippet gốc**, không phải chuỗi wrapper.
- Diagnostic liên quan `unknown` ở dòng 4 của wrapper được hiển thị tại dòng 2 của snippet.

**Điều kiện quan trọng:** đoạn snippet được chèn **không sửa ký tự** và dùng line terminator LF. Vì vậy phép trừ độ dài prefix là đúng với source snapshot trong ví dụ. Nếu công cụ tự thêm bốn dấu cách vào đầu mỗi dòng, chuyển CRLF thành LF, đổi Unicode escape hoặc thay tên biến, phép ánh xạ này **không còn đủ**.

### 6.2. Đây là bản demo một đoạn, không phải source map tổng quát

Chương trình chỉ xem các diagnostic loại `ERROR`, chỉ có một source ảo và một vùng chèn. Nếu diagnostic do wrapper gây ra thì in `unmapped`. Trong hệ thống thật cần:

- Xác minh `d.getSource()` thực sự trỏ về `generated/Wrapper.java` dự kiến.
- Gắn source map với **document ID và revision** đúng.
- Hỗ trợ nhiều tệp ảo, nhiều đoạn nguồn và nhiều dạng biến đổi.
- Xử lý spans cùng các vị trí `NOPOS` và lỗi nằm trong generated boilerplate.
- Chuyển tọa độ sang quy ước của editor (thường bắt đầu 0), thay vì dùng 1-based từ diagnostic như ví dụ stdout.

**Không nên gắn lỗi nằm trong wrapper vào ký tự đầu hoặc cuối snippet để “luôn hiện được một highlight”.** Việc đó tạo ra thông tin sai cho người dùng.

## 7. Thiết kế source map cho nhiều đoạn, nhiều tài liệu

Một hệ thống soạn bài có thể ghép một lớp Java từ các vùng:

~~~text
[boilerplate prefix]
[snippet của người dùng A, revision 13]
[generated helper]
[snippet của người dùng B, revision 8]
[boilerplate suffix]
~~~

Khi đó chỉ có một `JavaFileObject` ảo nhưng nội dung đến từ **nhiều nguồn gốc khác nhau**. Cần một bảng segment metadata:

| Trường metadata | Ví dụ | Chức năng |
| --- | --- | --- |
| generated URI | string:///run42/Combined.java | Nhận diện source đã gửi compiler |
| generated start | 120 | Offset đầu của segment trong source đã sinh |
| generated end | 182 | Offset cuối độc quyền trong source đã sinh |
| original document ID | editor://draft-A | Nhận diện đúng tài liệu người dùng |
| original revision | 13 | Ngăn map vị trí sang bản đã sửa |
| original start | 0 | Offset đầu trong tài liệu gốc |
| mapping kind | exact-copy | Có bảo toàn từng ký tự hay cần map phức tạp |
| generated-only | true/false | Xác định vùng do công cụ sinh không có nguồn gốc trực tiếp |

**Nguyên tắc bất biến khi dùng segment exact-copy:**

~~~text
generated[genStart : genEnd] ==
original[origStart : origStart + (genEnd - genStart)]

Với p trong [genStart, genEnd):
    originalOffset = origStart + (p - genStart)
~~~

Nếu mọi segment có `generated URI` riêng hoặc index có khóa URI, có thể tìm đúng segment theo cặp **(source URI, offset)**. Khi số segment lớn, lưu các segment đã sắp xếp theo generated start và dùng binary search thay vì duyệt tuyến tính cho mỗi diagnostic.

**Không lẫn source URI với file path do người dùng cung cấp.** Chuẩn hóa và quản lý URI ở lớp ứng dụng; khóa thật có thể là ID độc lập và ánh xạ một chiều tới URI dùng trong task. Hai lớp có cùng simple filename nhưng thuộc package khác nhau vẫn phải có identity riêng.

### 7.1. Nhiều phép biến đổi phức tạp

Một phép cộng prefix đơn giản làm offset thay đổi bởi một hằng số. Nhưng các phép biến đổi khác **không tuyến tính**:

- Thêm thụt lề vào **mỗi dòng**: sau mỗi dấu xuống dòng, offset lệch thêm số ký tự indent.
- Đổi CRLF thành LF: mỗi cặp xuống dòng giảm một code unit so với nguồn cũ.
- Chèn imports giữa các đoạn: có thêm một segment generated-only ở giữa.
- Thay identifier hoặc escape: số ký tự thay đổi ngay giữa một đoạn.
- Gộp nhiều snippet: mỗi snippet có start/end và document identity khác nhau.
- Xóa comment hoặc formatter: vị trí tương đối có thể thay đổi trên toàn tệp.

Trong các trường hợp này, cần **source map được tạo đồng thời với thao tác biến đổi**. Cách dễ duy trì là mỗi đoạn output được gắn nguồn gốc: generated-only, exact-copy hoặc mapping theo token/character. Với rewrite không giữ 1–1, phải định nghĩa rõ độ chính xác là **đến ký tự**, **đến token**, hay chỉ **đến một đoạn nguồn gốc gần nhất**.

Không suy ra rằng mọi diagnostic đều có thể ánh xạ tới một vị trí chính xác. Nếu compiler báo lỗi ở một token do hệ thống tạo, sự thật có thể là “lỗi trong mã được sinh” hoặc “không xác định vị trí gốc”. Hiển thị điều đó trung thực hơn gạch chân một từ bất kỳ.

### 7.2. Khi một generated span nằm qua hai đoạn nguồn gốc

`getStartPosition()` và `getEndPosition()` có thể chỉ một khoảng liên quan đến nhiều token. Với map theo segment, một span chỉ có thể được ánh xạ trọn vẹn như một range liên tục của tài liệu gốc **khi mọi phần đều có nguồn gốc phù hợp và thứ tự liên tục**.

Nếu span bắt đầu trong snippet A và kết thúc trong generated helper, không được sinh một vùng highlight “liền mạch” trên tài liệu A. Có thể:

1. Chỉ ánh xạ **primary caret** nếu nó nằm trong segment exact-copy hợp lệ.
2. Không gạch chân span đầy đủ.
3. Hiển thị diagnostic gắn với generated source và ghi nguồn gốc liên quan ở mức thấp hơn.
4. Cung cấp link tới tệp generated để người dùng hoặc developer điều tra.

Không giả định mọi compiler đều diễn giải `getEndPosition()` giống một chỉ số kết thúc độc quyền khi xây dựng hệ thống cross-compiler; cần tham chiếu contract và kiểm thử trước khi dùng API làm span trong UI.

## 8. Dòng, cột, offset và UTF-16

### 8.1. Phân biệt 0-based và 1-based

Với `Diagnostic`:

- `getPosition()` dùng **offset từ 0**.
- `getLineNumber()` bắt đầu từ **1** khi vị trí có sẵn.
- `getColumnNumber()` bắt đầu từ **1** khi vị trí có sẵn.
- Nhiều editor API dùng dòng và cột từ **0**, vì thế cần trừ 1 khi đưa vào editor.
- Một số editor dùng **offset tính theo UTF-16**, trong khi ứng dụng ngôn ngữ khác có thể đếm Unicode code points.

Không dùng `getLineNumber()-1` nếu giá trị là `NOPOS`. Kiểm tra giá trị trước khi chuyển sang chỉ số 0.

### 8.2. UTF-16 và surrogate pairs

Java `String` lưu chuỗi theo UTF-16 code units. Khi code trước điểm lỗi chứa một ký tự Unicode ngoài Basic Multilingual Plane (ví dụ một emoji), `String.length()` tăng **2** code units cho ký tự ấy.

Với javac/Java Compiler API, dùng chính **chuỗi Java gửi compiler** và nhất quán hệ thống chỉ số UTF-16 khi thực hiện phép trừ prefix và ánh xạ offset. **Không lấy số code points của JavaScript/Python rồi trừ trực tiếp khỏi offset UTF-16 của Java mà không chuyển đổi**. Một công cụ đa ngôn ngữ nên ghi rõ encoding/index convention trong source map.

Ví dụ nguyên tắc:

~~~text
Chuỗi:    "A😀B"
Code point: A | 😀 | B        = 3 code points
UTF-16:     A | high | low | B = 4 code units

Vị trí B tính theo UTF-16 offset: 3
Vị trí B tính theo Unicode code point offset: 2
~~~

Nếu editor API yêu cầu UTF-8 byte offset thì còn cần chuyển đổi thêm; không thể dùng trực tiếp `String.length()`.

### 8.3. LF, CRLF và tab

Demo `lineColumn` chỉ xử lý LF. Với nguồn Windows dùng CRLF hoặc có standalone CR, một hàm line mapper production cần:

- Nhận diện **CR**, **LF**, **CRLF** theo chính sách thống nhất.
- Đếm CRLF thành **một line break**.
- Có quy tắc rõ khi offset nằm ngay trong cặp ký tự CRLF.
- Tách **cột theo code units** khỏi **cột hiển thị sau khi tab được mở rộng**.
- Giữ một bảng `lineStarts` để map offset nhanh nếu editor có nhiều diagnostics.

Nếu công cụ quyết định chuẩn hóa toàn bộ source sang LF trước khi compile, phải **ghi phép chuẩn hóa vào source map**; đừng dùng line/column sau chuẩn hóa và giả vờ chúng trùng với tài liệu CRLF gốc.

### 8.4. Không tự ước lượng vị trí bằng cách đếm dấu cách của message

Dấu caret trong output text có thể bị ảnh hưởng bởi tab hoặc hiển thị Unicode. `Diagnostic.getPosition()` và `getLineNumber()/getColumnNumber()` có cấu trúc rõ hơn so với việc parse đoạn stderr có dấu `^`. Vị trí trong API vẫn cần quy đổi đúng source snapshot, nhưng tránh được nhiều lỗi căn chỉnh từ text output.

## 9. Mã lỗi và message cũng phải được giữ đúng nguồn

Ngoài source/position, hãy giữ:

~~~text
DiagnosticRecord
  documentId
  revision
  originalLine / originalColumn / originalRange (nếu mapping hợp lệ)
  generatedUri / generatedPosition
  kind
  code
  message
  mappingStatus
~~~

**`getCode()` là implementation-dependent** và có thể trả `null`. Không dùng mã cụ thể làm khóa duy nhất để chuyển diagnostic sang một tài liệu gốc; chính source identity mới quyết định điều đó.

`getMessage(Locale.ENGLISH)` hoặc locale của ứng dụng là nội dung để hiển thị. Nếu nhận nhiều diagnostics cùng mã hoặc cùng message, chúng **không phải cùng một lỗi**: khác file hoặc khác vị trí vẫn phải là các bản ghi riêng.

Cũng không nên lấy thứ tự collector trả diagnostics làm thứ tự cố định giữa các bản JDK hoặc nhiều compilation tasks. Khi UI muốn sắp xếp, có thể sort theo **document + offset + severity**, nhưng giữ identity ban đầu trước khi sort.

**Lỗi từ processor:** annotation processor có thể phát diagnostic gắn với element/annotation/value; compiler cũng có thể báo từ source được processor sinh. Cần xác định source thực tế của diagnostic, và chỉ ánh xạ về nguồn dùng annotation nếu processor/công cụ có provenance phù hợp. Không phải mọi generated-source error đều có một vị trí chính xác trong annotation gốc.

## 10. Thiết kế quy trình end-to-end của một công cụ biên dịch trong bộ nhớ

Một hệ thống có editor và compiler service nên tách các bước:

~~~text
1. Nhận request
   - documentId, revision, nội dung chính xác, tùy chọn biên dịch

2. Tạo source snapshot bất biến
   - lưu originalText và thông tin line endings

3. Xây nguồn gửi compiler
   - JavaFileObject riêng cho mỗi URI
   - nếu có transform thì lưu generatedText + sourceMap

4. Chạy JavaCompiler
   - cấu hình file manager, classpath, options, processor policy
   - đăng ký DiagnosticCollector

5. Đọc mỗi Diagnostic
   - getSource, getPosition, start/end, line/column, kind/code/message

6. Tìm source record
   - dựa trên URI + task ID/snapshot
   - tuyệt đối không dựa vào simple filename duy nhất

7. Ánh xạ position/range
   - unchanged source: identity mapping
   - transformed source: source map
   - null/NOPOS/unmapped: không highlight giả

8. Quy đổi sang editor coordinates
   - line/column 0-based hoặc UTF-16 offset theo editor API

9. Trả kết quả kèm revision
   - UI chỉ hiển thị highlight nếu revision còn khớp

10. Xác minh
   - test multi-file, generated wrappers, CRLF, Unicode, NOPOS
~~~

### 10.1. Snapshot bất biến quan trọng như source map

Giả sử người dùng bắt đầu compile ở revision **17**, rồi gõ thêm một dòng ở đầu tài liệu thành revision **18** trước khi compiler trả kết quả. Diagnostic có thể map chính xác vào vị trí của revision 17 nhưng không còn chính xác với revision 18.

Giải pháp an toàn:

- Trả về revision cùng diagnostic.
- Nếu editor đang ở revision khác, **không áp highlight lên tọa độ cũ** mà không tái ánh xạ theo các thay đổi của editor.
- Có thể chạy lại compile trên revision mới hoặc dùng document change tracking nếu hệ thống có khả năng.
- Không dựa vào số file giống nhau làm bằng chứng nội dung chưa đổi.

Đối với các dịch vụ nhiều người dùng, source registry nên được phân tách theo **request/tenant**. Không để URI của request cũ còn đăng ký rồi vô tình nhận diagnostic của request mới.

### 10.2. Cẩn thận với JavaFileManager và generated sources

`JavaFileManager` có thể trả file objects cho nguồn/class khác với những source objects người dùng gửi trực tiếp. Khi javac hoặc annotation processor sinh mã, diagnostic có thể trỏ tới **generated JavaFileObject** mới.

Vì vậy, quản lý registry gồm:

- **Input source** do người dùng cung cấp.
- **Generated source** do template/wrapper/processor tạo.
- **Class/resource output** nếu cần theo dõi.
- **Provenance** giữa generated source và input khi có căn cứ.

Trong ví dụ đơn giản, `-proc:none` tránh ảnh hưởng ngoài ý muốn của annotation processors. Trong hệ thống dùng processing thật, không tắt processor một cách mù quáng vì có thể khiến chương trình thiếu mã sinh; thay vào đó cần kiểm soát nguồn processor, output và mapping.

## 11. Phân biệt ánh xạ line-number đơn giản và source map đúng nghĩa

Một lỗi phổ biến là áp:

~~~text
originalLine = generatedLine - số_dòng_prefix
~~~

Công thức này **chỉ đúng** trong một trường hợp rất hẹp: mọi dòng của snippet được giữ nguyên, mỗi generated line có một nguồn gốc liên tục, và không có thêm/chuyển đổi dòng trong phần snippet.

Ngay cả ở bài toán snippet, công cụ có thể:

- Thêm indent vào từng dòng;
- Bọc class/method nhưng đồng thời sửa import;
- Đổi xuống dòng theo hệ điều hành;
- Thay một placeholder bằng biểu thức dài hơn;
- Chèn các dòng helper giữa hai snippet;
- Sinh nhiều file Java từ cùng một tài liệu.

Khi đó **chỉ ánh xạ số dòng không thể cho đúng cột**, và có thể không cho đúng dòng. Hãy ưu tiên mapping theo offset có segment rõ ràng. Dùng line/column chỉ là **bước hiển thị cuối cùng** sau khi đã xác định đúng origin offset.

**Chính sách hữu ích:** source-map segment exact-copy phải chứng minh đoạn output đúng bằng substring gốc. Nếu không chứng minh được, đánh dấu mapping loại khác và chỉ cung cấp độ chính xác bạn có thể bảo đảm.

## 12. Lỗi thực tế và cách khắc phục

| Triệu chứng | Nguyên nhân hay gặp | Cách sửa |
| --- | --- | --- |
| Tất cả lỗi hiển thị ở file đầu tiên | Không đọc `Diagnostic.getSource()` | Dùng source identity cho từng diagnostic |
| Lỗi lệch xuống hai dòng | Compiler biên dịch wrapper có prefix hai dòng | Dùng source map, không lấy generated line làm original line |
| Cột lệch ở các dòng sau | Công cụ thêm indent từng dòng | Lưu mapping theo segment/dòng hoặc theo ký tự |
| Lỗi nhảy sang file cùng tên | Dùng `Main.java` làm khóa duy nhất | Dùng URI/source ID đầy đủ |
| Lỗi gắn với revision mới hơn | Editor đổi nội dung trong lúc compile | Gắn revision vào snapshot và phản hồi |
| Warning không có vị trí bị hiện ở dòng 1 | Không xử lý `NOPOS` hoặc nguồn null | Hiển thị diagnostic chung không có highlight |
| Highlight vượt cuối file | Offset dùng trên snapshot khác hoặc sai UTF-16 | Kiểm tra bounds + encoding convention |
| Lỗi trong generated helper bị đổ cho user | Không có nhãn generated-only | Giữ generated source và mappingStatus=unmapped |
| Lỗi từ annotation processor trỏ generated file | Không theo dõi Filer output | Ghi provenance hoặc báo nguồn generated |
| Có URI hợp lệ nhưng class không đúng | Registry bị reuse/đụng key | Khóa theo task + URI + revision |
| Nội dung message bị parse sai | Phân tích stderr theo regex | Dùng `DiagnosticCollector` |
| Source ảo không được nhận dạng đúng file kind | URI/Kind sai hoặc tên file không tương thích | Dùng URI có đuôi `.java` và `Kind.SOURCE` |

Một quy trình QA nên cố ý đưa vào **lỗi ở đầu, giữa, cuối source**, **hai file cùng simple name ở package khác nhau**, **mã Unicode**, **CRLF**, **transform thêm prefix** và **diagnostic không có source position**.

### 12.1. Phân biệt lỗi mapping và lỗi compiler

Nếu `Diagnostic.getPosition()` đã đúng trong generated source nhưng UI highlight sai ở original, phần lỗi thường nằm ở **source map/editor conversion**. Nếu compiler gắn diagnostic vào vị trí nhìn có vẻ không liên quan, đó có thể là nơi parser phát hiện thiếu dấu chấm phẩy hoặc ngoặc chứ không phải map hỏng.

Không viết logic “tự tìm vị trí tốt hơn” bằng cách search từ khóa trong message hoặc mã source. Một tên biến có thể xuất hiện nhiều lần; tìm chuỗi đầu tiên sẽ làm tăng lỗi sai âm thầm.

### 12.2. Khi chỉ có lỗi của javac dưới dạng stderr

Nếu chạy compiler như tiến trình ngoài qua `ProcessBuilder`, bạn có thể chỉ nhận stderr chứa đường dẫn, dòng và caret. Có thể parse để hỗ trợ công cụ, nhưng:

- Định dạng message có thể đổi theo phiên bản và locale.
- Các lỗi compile liên quan tệp ảo có thể không có đường dẫn thực.
- Caret có thể bị ảnh hưởng bởi tab hoặc terminal.
- Không phải mọi diagnostic đều có line/column.

Khi code chạy trong JVM và có thể dùng Java Compiler API, `DiagnosticCollector` là đường có cấu trúc và đáng tin hơn cho việc mapping.

## 13. Bài tập tự thực hành

**Bài 1 — Nhiều tệp.** Chạy `SourceDiagnostics.java`, xác minh dòng 5 của First.java và dòng 3 của Second.java. Thêm một class khác có tên file giống nhau nhưng package khác nhau; thiết kế URI registry không đụng identity.

**Bài 2 — Wrapper.** Chạy `MapWrapped.java`, giải thích vì sao javac trả `4:20` còn snippet gốc là `2:20`. Tự thêm một dòng comment vào prefix và dự đoán tọa độ compiler thay đổi thế nào; kiểm tra rằng original location vẫn như cũ.

**Bài 3 — Xóa source map.** Giả sử chỉ có thông báo `Wrapper.java:4:20` mà không biết prefix/suffix hay đoạn nguồn gốc. Bạn có đủ thông tin để xác định file và vị trí editor không? Giải thích vì sao không.

**Bài 4 — Unicode.** Đặt một ký tự ngoài BMP trước lỗi trong snippet. So sánh offset tính theo Java `String.length()` với số Unicode code points. Hãy chỉ ra vì sao dùng nhầm hai hệ có thể làm cột lệch.

**Bài 5 — CRLF.** Thay các newline trong original bằng CRLF nhưng giữ một mapping function chỉ đếm LF và tăng cột cho CR. Sửa mapper để CRLF được tính là một line break; viết test cho offset ngay trước/đúng/sau line terminator.

**Bài 6 — Compiler error không gắn source.** Xử lý một diagnostic giả định có `source=null` và `position=NOPOS`: UI nên hiện gì và không nên hiện gì?

**Bài 7 — Generated source.** Giả sử annotation processor sinh `GeneratedMapper.java` rồi compiler báo lỗi trong đó. Xác định những bằng chứng cần để gắn lỗi này về annotation người dùng thay vì gắn bừa vào source gốc.

**Bài 8 — Code review.** Một ứng dụng hiện làm `diagnostics.forEach(d -> editor.highlight(d.getLineNumber()-1))`. Liệt kê ít nhất năm trường hợp sai và đề xuất cấu trúc dữ liệu nguồn/snapshot/source map giúp sửa.

## 14. Câu hỏi tự kiểm tra

1. Vì sao `Diagnostic.getSource()` là dữ kiện bắt buộc trong compilation task có nhiều nguồn?
2. `getPosition()` và `getLineNumber()` dùng hệ tọa độ nào?
3. Khi nào `getSource()` có thể null, và `Diagnostic.NOPOS` có ý nghĩa gì?
4. Tại sao `URI.toString()` chưa đủ để xác định tài liệu đúng phiên bản?
5. Khi nào phép ánh xạ `originalOffset = generatedOffset - prefix.length()` là chính xác?
6. Vì sao thêm thụt lề mỗi dòng phá vỡ một phép trừ offset hằng số?
7. Làm sao phân biệt lỗi ở code wrapper với lỗi ở snippet người dùng?
8. Một diagnostic span cắt qua generated-only region có nên thành một highlight liền mạch ở tài liệu gốc không?
9. UTF-16 code units khác Unicode code points ở vị trí nào?
10. Vì sao một compiler API record có source/position đáng tin hơn thông báo stderr tự parse?
11. Tại sao cần document revision khi biên dịch bất đồng bộ?
12. Vì sao lỗi trong source do annotation processor sinh không tự map chính xác về annotation gốc?

## 15. Nguồn tài liệu chính thức

- **Java SE 21 — javax.tools.Diagnostic API:** https://docs.oracle.com/en/java/javase/21/docs/api/java.compiler/javax/tools/Diagnostic.html
- **Java SE 21 — javax.tools.DiagnosticCollector:** https://docs.oracle.com/en/java/javase/21/docs/api/java.compiler/javax/tools/DiagnosticCollector.html
- **Java SE 21 — javax.tools.JavaCompiler:** https://docs.oracle.com/en/java/javase/21/docs/api/java.compiler/javax/tools/JavaCompiler.html
- **Java SE 21 — javax.tools.JavaFileObject:** https://docs.oracle.com/en/java/javase/21/docs/api/java.compiler/javax/tools/JavaFileObject.html
- **Java SE 21 — javax.tools.SimpleJavaFileObject:** https://docs.oracle.com/en/java/javase/21/docs/api/java.compiler/javax/tools/SimpleJavaFileObject.html
- **Java SE 21 — javax.tools.StandardJavaFileManager:** https://docs.oracle.com/en/java/javase/21/docs/api/java.compiler/javax/tools/StandardJavaFileManager.html
- **Oracle JDK 21 — javac command reference:** https://docs.oracle.com/en/java/javase/21/docs/specs/man/javac.html

**Ghi nhớ:** Khi biên dịch Java trong bộ nhớ, **diagnostic phải được hiểu theo đúng `JavaFileObject` mà compiler đã thấy**. Nếu đó là bản sao nguyên văn của tài liệu gốc, identity mapping thường đủ. Nếu nguồn đã được sinh/bọc/chuẩn hóa, cần **source map ghi lại từ lúc biến đổi**, gắn document ID và revision, xử lý `null/NOPOS`, sau đó mới hiển thị line/column trong editor. **Một lỗi không thể ánh xạ chắc chắn thì phải được ghi là chưa ánh xạ, không được tự tạo vị trí giả.**