# Dấu phân cách tham số khi khởi chạy Java

Khi chạy chương trình Java từ dòng lệnh, tham số đi qua nhiều lớp xử lý: terminal hoặc shell tách dòng lệnh thành các token, Java launcher nhận diện tùy chọn của JVM và xác định chương trình cần chạy, sau đó các token nằm sau điểm khởi chạy được chuyển vào phương thức main. Hiểu đúng ranh giới này giúp tránh nhầm tham số JVM với tham số ứng dụng, đặc biệt khi tham số có dấu gạch ngang, dấu cách hoặc ký tự đặc biệt.

Bài học dùng cú pháp Java 21 làm ví dụ. Quy tắc cơ bản tương tự trên các bản Java hiện đại.

## 1. Ba lớp cần phân biệt

Một dòng lệnh chạy Java có thể được hiểu theo ba lớp:

1. **Shell / terminal:** xử lý dấu cách, dấu nháy, ký tự escape và tạo danh sách đối số truyền cho tiến trình.
2. **Java launcher:** đọc tùy chọn khởi chạy JVM, classpath/module path và xác định lớp, JAR, module hoặc tệp nguồn sẽ chạy.
3. **Ứng dụng Java:** nhận các đối số ứng dụng trong `String[] args` và tự quyết định ý nghĩa của chúng.

Ví dụ:

~~~bash
java -Xmx512m -Dapp.env=dev -cp out ArgsDemo --mode fast --file "report final.csv"
~~~

Trong lệnh này:

- `-Xmx512m` là tùy chọn bộ nhớ heap của JVM.
- `-Dapp.env=dev` đặt system property có tên `app.env`.
- `-cp out` thiết lập classpath cho Java launcher.
- `ArgsDemo` là lớp chính được chạy.
- `--mode`, `fast`, `--file` và `report final.csv` là đối số ứng dụng được chuyển vào `main`.

**Tên lớp chính là ranh giới quan trọng** trong cú pháp chạy lớp: các tùy chọn launcher nằm trước tên lớp; các token sau tên lớp được chuyển cho ứng dụng. Khi dùng JAR, module hoặc source-file mode, vị trí của JAR, module hoặc tệp nguồn đóng vai trò ranh giới tương ứng.

## 2. Cú pháp khởi chạy và ranh giới đối số

Các dạng lệnh phổ biến:

~~~text
java [options] mainclass [args ...]
java [options] -jar jarfile [args ...]
java [options] -m module[/mainclass] [args ...]
java [options] source-file [args ...]
~~~

| Cách chạy | Ranh giới bắt đầu đối số ứng dụng |
|---|---|
| `java [options] com.example.Main [args]` | Ngay sau tên lớp chính |
| `java [options] -jar app.jar [args]` | Ngay sau tên tệp JAR |
| `java [options] -m app/com.example.Main [args]` | Ngay sau tên module/lớp chính |
| `java [options] Main.java [args]` | Ngay sau tên tệp nguồn |

Ví dụ với lớp chính:

~~~bash
java -Dapp.env=dev -cp out com.example.Main --mode fast
~~~

Ứng dụng nhận hai phần tử: `--mode` và `fast`. System property `app.env` có giá trị `dev`.

Ví dụ với JAR:

~~~bash
java -Xmx512m -jar app.jar --mode fast
~~~

Ứng dụng trong JAR nhận `--mode` và `fast`. Tùy chọn heap `-Xmx512m` được xử lý trước khi ứng dụng bắt đầu.

Ví dụ với module:

~~~bash
java --module-path mods -m com.example.app/com.example.Main --mode fast
~~~

`--module-path` và `-m` thuộc launcher. `--mode` và `fast` thuộc ứng dụng.

## 3. Java launcher không có dấu -- kết thúc tùy chọn chung

Một số chương trình dòng lệnh dùng `--` làm dấu kết thúc phần tùy chọn của chính chương trình. Đây là quy ước phổ biến trong nhiều CLI parser, nhưng không nên mặc định rằng Java launcher dùng `--` theo quy ước đó.

Với Java launcher, cú pháp được mô tả là `java [options] mainclass [args ...]` (và các dạng `-jar`, `-m`, source-file). Điểm chuyển từ tùy chọn launcher sang đối số ứng dụng là launch target: tên lớp, tệp JAR, module hoặc tệp nguồn. Không cần chèn một dấu `--` đặc biệt trước đối số ứng dụng.

Ví dụ đúng:

~~~bash
java -cp out ArgsDemo -- --mode fast
~~~

Trong trường hợp này, dấu `--` nằm **sau** tên lớp `ArgsDemo`, vì vậy nó là đối số thứ nhất của ứng dụng. Nếu ứng dụng tự quy định `--` là dấu ngừng đọc tùy chọn, parser của ứng dụng có thể áp dụng quy tắc đó.

Đừng viết `java -- -Xmx512m ArgsDemo` với kỳ vọng `--` sẽ kết thúc tùy chọn JVM. `--` không phải dấu phân cách chung được Java launcher định nghĩa cho mục đích này; hãy đặt tùy chọn JVM trước launch target và đối số ứng dụng sau launch target.

## 4. Dấu cách, dấu nháy và một đối số gồm nhiều từ

Shell thường dùng khoảng trắng để tách các token. Nếu một giá trị chứa dấu cách, hãy đặt giá trị đó trong dấu nháy để shell truyền nó thành một đối số duy nhất.

~~~bash
java -cp out ArgsDemo --file "report final.csv"
~~~

Ứng dụng nhận:

- `args[0]` là `--file`
- `args[1]` là `report final.csv`

Dấu nháy dùng để nhóm token thường được shell loại bỏ trước khi gọi Java. Vì vậy ứng dụng nhận chuỗi `report final.csv`, không nhận hai dấu nháy bao quanh.

Ví dụ một số trường hợp:

| Dòng lệnh sau launch target | Đối số ứng dụng |
|---|---|
| `Main alpha beta` | `"alpha"`, `"beta"` |
| `Main "alpha beta"` | `"alpha beta"` |
| `Main ""` | Một chuỗi rỗng |
| `Main --file "report final.csv"` | `"--file"`, `"report final.csv"` |
| `Main --config=dev` | Một chuỗi `--config=dev` |

Trong Bash hoặc shell POSIX, dấu nháy đơn và dấu nháy kép có quy tắc escape khác nhau. Trong Windows PowerShell, quy tắc xử lý dấu nháy và truyền đối số cũng có khác biệt. Khi cần truyền đường dẫn có khoảng trắng, dùng dấu nháy kép quanh toàn bộ giá trị và kiểm tra bằng chương trình nhỏ trước khi đưa vào script phức tạp.

## 5. Ví dụ Java kiểm tra đối số thực tế

Tạo tệp `ArgsDemo.java`:

~~~java
public class ArgsDemo {
    public static void main(String[] args) {
        System.out.println("app.env=" + System.getProperty("app.env"));
        System.out.println("args.length=" + args.length);

        for (int i = 0; i < args.length; i++) {
            System.out.println("args[" + i + "]=<" + args[i] + ">");
        }
    }
}
~~~

Biên dịch:

~~~bash
javac -d out ArgsDemo.java
~~~

Chạy trên macOS/Linux, Windows Command Prompt hoặc PowerShell:

~~~bash
java -Xmx512m -Dapp.env=dev -cp out ArgsDemo --mode fast --file "report final.csv"
~~~

Kết quả:

~~~text
app.env=dev
args.length=4
args[0]=<--mode>
args[1]=<fast>
args[2]=<--file>
args[3]=<report final.csv>
~~~

Kết quả cho thấy `-Dapp.env=dev` được launcher chuyển thành system property, không xuất hiện trong `args`. Các token sau `ArgsDemo` được giữ theo thứ tự và truyền vào mảng `String[]`.

Thử truyền dấu `--` cho ứng dụng:

~~~bash
java -cp out ArgsDemo -- --mode fast
~~~

Kết quả:

~~~text
app.env=null
args.length=3
args[0]=<-->
args[1]=<--mode>
args[2]=<fast>
~~~

Ứng dụng nhận dấu `--` như một chuỗi bình thường. Chỉ khi code ứng dụng hoặc thư viện phân tích đối số chủ động quy định ý nghĩa cho chuỗi đó thì nó mới trở thành dấu kết thúc tùy chọn ở tầng ứng dụng.

## 6. Phân biệt tùy chọn JVM và tùy chọn ứng dụng

Cùng một chuỗi có thể được xử lý khác nhau tùy vị trí của nó trong dòng lệnh.

| Chuỗi | Trước launch target | Sau launch target |
|---|---|---|
| `-Xmx512m` | Tùy chọn heap của JVM | Đối số ứng dụng |
| `-Dapp.env=dev` | Đặt system property | Đối số ứng dụng |
| `--class-path out` | Tùy chọn classpath của launcher | Đối số ứng dụng |
| `--mode=fast` | Không phải tùy chọn chuẩn chung của Java launcher; có thể bị hiểu là tùy chọn không hợp lệ | Đối số ứng dụng |
| `--` | Không phải dấu kết thúc tùy chọn chung của Java launcher | Đối số ứng dụng |

Ví dụ:

~~~bash
# JVM nhận -Xmx và -D; ứng dụng nhận --mode
java -Xmx512m -Dapp.env=prod -cp out ArgsDemo --mode=fast

# Ở đây -Xmx512m là dữ liệu đầu vào của ứng dụng
java -cp out ArgsDemo -Xmx512m
~~~

Java launcher có các tùy chọn riêng như `-Xmx`, `-D`, `-cp`, `--class-path`, `--module-path`, `-jar` và `-m`. Tên tùy chọn ứng dụng như `--mode`, `--file`, `--help` thường do chính ứng dụng định nghĩa. Đừng đặt tùy chọn ứng dụng trước tên lớp chính với kỳ vọng launcher sẽ tự chuyển tiếp chúng.

Một tùy chọn launcher có giá trị có thể dùng dấu cách hoặc dấu bằng theo cú pháp của tùy chọn. Ví dụ:

~~~bash
java --class-path out ArgsDemo
java --class-path=out ArgsDemo
~~~

Cả hai cách đều đặt classpath là `out`. Từ `out` trong hai lệnh này là giá trị của tùy chọn launcher, không phải đối số `main`.

## 7. Ứng dụng tự quy định dấu phân cách ra sao?

Java chỉ chuyển các đối số thành mảng chuỗi; Java không áp đặt một định dạng chung cho các tùy chọn nghiệp vụ của ứng dụng. Chương trình có thể tự định nghĩa các kiểu cú pháp:

| Quy ước ứng dụng | Ví dụ token | Cách parser thường diễn giải |
|---|---|---|
| Cờ bật/tắt | `--verbose` | Một cờ không có giá trị riêng |
| Tên và giá trị tách rời | `--mode fast` | Hai đối số liên tiếp |
| Tên và giá trị có dấu bằng | `--mode=fast` | Một đối số, parser tách tại `=` |
| Cặp ngắn | `-p 8080` | Hai đối số |
| Dấu kết thúc tùy chọn | `-- file.txt` | Chỉ có ý nghĩa nếu parser ứng dụng hỗ trợ quy ước này |

Ví dụ, với `--mode=fast`, Java chuyển nguyên token `--mode=fast`. Việc tách thành tên `--mode` và giá trị `fast` là công việc của parser trong ứng dụng.

Với `--mode fast`, Java chuyển hai phần tử riêng. Parser cần đọc phần tử tiếp theo làm giá trị của `--mode` và kiểm tra xem phần tử đó có tồn tại hay không.

Nếu tự viết parser, cần xác định rõ:

- Tên tùy chọn có phân biệt chữ hoa/chữ thường không.
- Giá trị có thể chứa dấu `=` hay không.
- Một tùy chọn có thể xuất hiện nhiều lần không.
- Cờ boolean có chấp nhận dạng `--flag=true` không.
- `--` có kết thúc việc phân tích tùy chọn hay không.
- Đối số thiếu giá trị, lặp lại hoặc không được hỗ trợ sẽ báo lỗi như thế nào.

Với ứng dụng lớn, nên dùng thư viện phân tích command-line đã được kiểm thử thay vì tự xử lý mọi trường hợp bằng cách tách chuỗi thủ công.

## 8. Dùng argument file khi dòng lệnh dài

Java launcher hỗ trợ argument file: đặt các tùy chọn, tên lớp và đối số vào một tệp văn bản, sau đó truyền tên tệp với tiền tố @.

Tạo `run.args`:

~~~text
-Xmx512m
-Dapp.env=dev
-cp
out
ArgsDemo
--mode
fast
--file
"report final.csv"
~~~

Chạy:

~~~bash
java @run.args
~~~

Launcher mở rộng nội dung argument file thành danh sách đối số trước khi phân tích lệnh. Trong tệp, khoảng trắng hoặc xuống dòng phân tách các token; dấu nháy kép có thể nhóm giá trị chứa khoảng trắng. Quy tắc của argument file do Java launcher quy định, không phải quy tắc escape của shell.

Argument file hữu ích khi classpath dài hoặc script có nhiều tùy chọn JVM. Đường dẫn tương đối bên trong tệp được tính từ thư mục làm việc hiện tại. Không nhầm argument file `@run.args` của launcher với tệp cấu hình do ứng dụng tự đọc.

## 9. Biến môi trường JDK_JAVA_OPTIONS

`JDK_JAVA_OPTIONS` cho phép thêm các tùy chọn launcher vào đầu danh sách tùy chọn của lệnh `java`. Ví dụ trong Bash:

~~~bash
export JDK_JAVA_OPTIONS="-Xmx512m -Dapp.env=dev"
java -cp out ArgsDemo --mode fast
~~~

Trong Windows PowerShell:

~~~powershell
$env:JDK_JAVA_OPTIONS = "-Xmx512m -Dapp.env=dev"
java -cp out ArgsDemo --mode fast
~~~

Các giá trị trong biến này được xử lý như tùy chọn launcher được thêm trước các đối số dòng lệnh. Chúng không được tự động đưa vào `String[] args`. Java launcher cũng hạn chế một số loại tùy chọn trong biến môi trường, chẳng hạn tùy chọn chọn lớp/JAR chính hoặc tùy chọn khiến launcher thoát ngay.

Khi chương trình chạy với cấu hình bất ngờ, hãy kiểm tra `JDK_JAVA_OPTIONS` cùng các script khởi chạy để biết có tùy chọn JVM nào được chèn thêm hay không.

## 10. Lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
|---|---|---|
| Ứng dụng nhận một giá trị có dấu cách thành hai phần tử | Quên đặt dấu nháy quanh giá trị | Dùng `"report final.csv"` |
| `-Xmx` xuất hiện trong `args` | Đặt `-Xmx` sau tên lớp/JAR/module | Chuyển tùy chọn JVM lên trước launch target |
| `--mode` gây lỗi tùy chọn khi chạy Java | Đặt tùy chọn riêng của ứng dụng trước tên lớp chính | Đặt sau tên lớp/JAR/module/tệp nguồn |
| Ứng dụng không nhận system property như mong đợi | Dùng `-D` sau launch target hoặc viết sai tên property | Đặt `-Dname=value` trước launch target; đọc bằng `System.getProperty` |
| Parser không nhận `--mode=fast` | Parser chỉ hỗ trợ dạng `--mode fast` hoặc ngược lại | Kiểm tra cú pháp mà ứng dụng định nghĩa |
| Dấu nháy xuất hiện trong giá trị nhận được | Đã escape để truyền dấu nháy thật hoặc script xử lý quoting khác dự kiến | In từng phần tử `args` để kiểm tra token thực tế |
| Lệnh chạy khác nhau giữa terminal và IDE | IDE có cấu hình program arguments và VM options riêng | Kiểm tra hai trường cấu hình tách biệt trong Run Configuration |
| Tùy chọn được chèn dù không có trên lệnh chạy | `JDK_JAVA_OPTIONS` hoặc script wrapper thêm tham số | Kiểm tra biến môi trường và script khởi chạy |

## 11. Quy trình kiểm tra khi tham số không đúng

Khi ứng dụng nhận sai tham số, hãy kiểm tra theo thứ tự:

1. **In toàn bộ `args`:** hiển thị số phần tử, chỉ số và nội dung từng phần tử. Không chỉ in cả mảng thành một chuỗi vì sẽ khó phát hiện ranh giới token.
2. **Kiểm tra lệnh đã chạy:** xác định chính xác tên lớp, JAR, module hoặc tệp nguồn ở đâu; mọi token sau launch target sẽ thuộc ứng dụng.
3. **Kiểm tra dấu nháy:** xác nhận shell có gom giá trị chứa khoảng trắng thành một token hay không.
4. **Kiểm tra VM options:** xem `-X`, `-D`, `--class-path`, `--module-path` và các tùy chọn launcher có nằm trước launch target không.
5. **Kiểm tra parser ứng dụng:** xác định parser yêu cầu `--name value`, `--name=value` hay quy ước riêng khác.
6. **Kiểm tra nguồn tham số bổ sung:** xem Run Configuration của IDE, script wrapper, `JDK_JAVA_OPTIONS` và argument file `@...`.

Có thể dùng lệnh trợ giúp để xem cú pháp launcher của đúng JDK:

~~~bash
java --help
java --help-extra
~~~

## 12. Ghi nhớ

- Khoảng trắng phân tách token; dấu nháy giúp giữ một giá trị có khoảng trắng trong một token.
- Tên lớp chính, JAR, module hoặc tệp nguồn xác định ranh giới giữa tùy chọn launcher và đối số ứng dụng.
- `-Xmx`, `-D`, `-cp` và `--module-path` phải được đặt ở phần tùy chọn launcher.
- `--mode`, `--file` và các tùy chọn nghiệp vụ thường được đặt sau launch target.
- Java launcher không định nghĩa `--` như dấu kết thúc tùy chọn chung; nếu `--` xuất hiện sau launch target, ứng dụng nhận nó như một đối số.
- `String[] args` chứa từng token đã được shell và launcher chuyển tiếp; việc diễn giải token thuộc trách nhiệm của ứng dụng.
- Khi lệnh chạy phức tạp, hãy dùng argument file và in `args` để kiểm tra dữ liệu thực tế.

Tài liệu tham khảo: [The java Command — Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/specs/man/java.html), đặc biệt phần Synopsis, Description, Standard Options for Java và Java Command-Line Argument Files.
