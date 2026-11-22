# Đọc đối số chương trình từ `String[] args` — Java 17+

## 1. `String[] args` là gì?

Một ứng dụng Java có thể nhận dữ liệu ngay khi được gọi từ dòng lệnh (*command line*). Điểm vào quen thuộc là:

~~~java
public static void main(String[] args) {
    // Đọc và xử lý các đối số mà người chạy chương trình truyền vào.
}
~~~

- `main` là phương thức điểm vào của chương trình Java theo cách chạy truyền thống.
- `String[] args` là **tham số hình thức** có kiểu **mảng chuỗi**. Mỗi phần tử `args[i]` chứa một **đối số ứng dụng** mà người dùng truyền sau tên lớp chính.
- `args.length` cho biết số lượng phần tử thực sự được truyền.
- Chỉ số bắt đầu từ `0` và kết thúc ở `args.length - 1`.
- Dữ liệu trong `args` ban đầu là **String**, kể cả khi người dùng nhập `123` hoặc `true`. Chương trình phải tự chuyển sang kiểu khác nếu cần.

Ví dụ:

~~~bash
java -cp . CommandLineArgsDemo Lan 3 --upper
~~~

Ở đây, mảng trong `main` có:

~~~text
args.length = 3
args[0]     = "Lan"
args[1]     = "3"
args[2]     = "--upper"
~~~

Các dấu ngoặc kép ở khối mô tả trên chỉ minh họa chuỗi, **không phải ký tự Java tự thêm vào giá trị**. Trong ví dụ hoàn chỉnh ở mục 9, chương trình nhận tên người dùng, số lần chào và một tùy chọn viết hoa.

## 2. Phân biệt tùy chọn của `java` với đối số của ứng dụng

Xét lệnh:

~~~bash
java -cp . CommandLineArgsDemo "Lan Anh" 2
~~~

| Phần trong lệnh | Vai trò |
|---|---|
| `java` | Trình khởi chạy Java |
| `-cp .` | Tùy chọn của **launcher/JVM**: đặt classpath root là thư mục hiện tại |
| `CommandLineArgsDemo` | Tên lớp chứa `main` |
| `"Lan Anh"` | **Đối số ứng dụng thứ nhất** (index 0); dấu nháy của shell nhóm hai từ |
| `2` | **Đối số ứng dụng thứ hai** (index 1), trong Java là chuỗi `"2"` |

**Tên lớp chính không nằm trong `args`.** Tương tự, tùy chọn `-cp` đứng trước tên lớp không phải một phần tử của `args`. Lệnh minh họa trên tạo `args.length == 2`.

Các tham số **sau tên lớp chính** được chuyển cho ứng dụng. Nếu gõ `--upper` sau tên lớp, Java không tự hiểu đây là cờ nghiệp vụ: chính **mã ứng dụng** phải kiểm tra `args[i]` và quyết định nó có ý nghĩa gì.

Các tùy chọn JVM như `-ea` hoặc `-Dkey=value` thường phải được đặt **trước tên lớp chính** khi muốn JVM xử lý. Nếu đặt sau tên lớp, chúng có thể trở thành chuỗi trong `args` của chương trình, tùy cách khởi chạy.

## 3. Duyệt mảng và kiểm tra độ dài trước khi đọc

Cách duyệt giữ được **thứ tự và chỉ số**:

~~~java
for (int i = 0; i < args.length; i++) {
    System.out.println("args[" + i + "]=" + args[i]);
}
~~~

Cách duyệt chỉ cần giá trị:

~~~java
for (String argument : args) {
    System.out.println(argument);
}
~~~

Khi muốn đọc một vị trí bắt buộc, phải đảm bảo vị trí ấy tồn tại:

~~~java
if (args.length == 0) {
    System.out.println("No arguments");
    return;
}
String first = args[0];
System.out.println(first);
~~~

Nếu người dùng chạy mà **không truyền đối số nào**, `args.length == 0` và `args[0]` sẽ ném `ArrayIndexOutOfBoundsException` nếu bị truy cập. Đây là lỗi phải phòng tránh bằng kiểm tra điều kiện, không phải dấu hiệu Java tự cung cấp một chuỗi rỗng thay thế.

Với Java launcher thông thường, `main` được gọi với một mảng `String[]` chứa các đối số ứng dụng (có thể rỗng). Nếu code khác gọi trực tiếp `main(null)` thì đó là một tình huống riêng do mã gọi tạo ra; không phải hành vi chạy CLI tiêu chuẩn cần dựa vào.

## 4. Mỗi phần tử ban đầu đều là chuỗi

Giả sử:

~~~bash
java -cp . CommandLineArgsDemo Lan 3
~~~

`args[1]` có kiểu `String` và giá trị `"3"`, không phải số nguyên `3`. Không viết phép nhân số học với `args[1]` khi chưa chuyển đổi.

~~~java
int times;
try {
    times = Integer.parseInt(args[1]);
} catch (NumberFormatException ex) {
    System.out.println("Invalid integer");
    return;
}
~~~

- `Integer.parseInt("3")` trả `3`, một `int`.
- `Integer.parseInt("abc")` ném `NumberFormatException`.
- `Integer.parseInt("3.5")` cũng không chuyển được thành `int` theo cú pháp số nguyên thập phân.
- `Integer.parseInt(" 3 ")` không tự bỏ khoảng trắng hai bên; cần quy tắc xử lý rõ ràng, ví dụ `args[1].strip()` trước khi parse nếu hợp đồng cho phép.
- Nếu văn bản biểu diễn số nằm ngoài phạm vi `int`, `parseInt` cũng có thể ném `NumberFormatException`.

Chuyển đổi thành công **chưa đủ** để xác nhận đầu vào hợp lệ. Nếu tham số `times` của ứng dụng chỉ được phép trong `1..5`, còn phải kiểm tra:

~~~java
if (times < 1 || times > 5) {
    System.out.println("times must be 1..5");
    return;
}
~~~

Việc validate miền giá trị của dữ liệu đầu vào **luôn phải chạy**, không thay bằng câu lệnh `assert` có thể bị vô hiệu khi khởi động JVM.

## 5. Đối số bắt buộc, đối số tùy chọn và thứ tự

Một chương trình CLI nên công bố **hợp đồng đầu vào** rõ ràng. Ví dụ bài này quy ước:

~~~text
java -cp . CommandLineArgsDemo <name> <times> [--upper]
~~~

| Vị trí | Bắt buộc? | Ý nghĩa | Ví dụ |
|---|---|---|---|
| `args[0]` | Có | Tên người được chào, không được toàn khoảng trắng | `Lan`, `"Lan Anh"` |
| `args[1]` | Có | Số lần chào, số nguyên thập phân từ 1 đến 5 | `3` |
| `args[2]` | Không | Cờ duy nhất được hỗ trợ: `--upper` | `--upper` |

Vì có hai đối số bắt buộc và một đối số tùy chọn, số lượng hợp lệ là **2 hoặc 3**. Cách kiểm tra:

~~~java
if (args.length < 2 || args.length > 3) {
    // Thông báo cách dùng và từ chối yêu cầu.
}
~~~

Vị trí có ý nghĩa: `CommandLineArgsDemo 3 Lan` **không tự được hoán đổi** thành tên Lan và ba lần chào. Chương trình có thể gặp lỗi chuyển `Lan` thành `int` vì vị trí thứ hai phải là số.

`[--upper]` trong phần hướng dẫn sử dụng (*usage*) là **ký hiệu tài liệu** rằng tùy chọn có thể bỏ qua; người dùng **không gõ dấu ngoặc vuông** trừ khi ứng dụng quy định khác.

Tùy chọn `--upper` do chương trình tự định nghĩa. Java launcher không tự tạo cơ chế phân tích `--name`, `--times` hoặc thứ tự cờ linh hoạt. Muốn hỗ trợ các dạng phức tạp hơn, phải tự viết parser hoặc sử dụng thư viện CLI phù hợp.

## 6. Dấu nháy của shell, khoảng trắng và Unicode

Khi muốn chuyển một tên có khoảng trắng thành **một đối số**, cần dùng cú pháp trích dẫn phù hợp với shell:

**Bash (Linux/macOS):**

~~~bash
java -cp . CommandLineArgsDemo "Lan Anh" 2
~~~

**PowerShell (Windows):**

~~~powershell
java -cp . CommandLineArgsDemo "Lan Anh" 2
~~~

Trong cả hai lệnh trên, `args[0]` là chuỗi `Lan Anh` có một dấu cách ở giữa. Dấu `"` giúp shell nhóm chữ, bình thường không trở thành ký tự nằm trong giá trị của `args[0]`.

Nếu bỏ dấu nháy:

~~~bash
java -cp . CommandLineArgsDemo Lan Anh 2
~~~

thì ứng dụng nhận **ba đối số** `"Lan"`, `"Anh"`, `"2"`. Theo hợp đồng của bài, chương trình sẽ cố parse `"Anh"` như số lần chào và từ chối.

Các ký tự đặc biệt như dấu cách, `*`, `$`, dấu nháy và dấu gạch chéo ngược có quy tắc shell khác nhau. Không dựa vào một chuỗi escape của Bash để kết luận nó hoạt động y hệt PowerShell. Với ví dụ phổ thông, dấu nháy kép cho tên có khoảng trắng là đủ.

Java hỗ trợ chuỗi Unicode trong `args`. Khi nhập tiếng Việt, console và cấu hình mã hóa font/terminal phải hỗ trợ Unicode để hiện chữ chính xác. Chương trình hoàn chỉnh dùng dữ liệu ASCII cho những khối stdout được yêu cầu khớp tuyệt đối.

## 7. Chuẩn hóa, xác thực và từ chối đầu vào không hợp lệ

Cần phân biệt **đọc được đối số** với **đầu vào hợp lệ**:

~~~java
String name = args[0].strip();

if (name.isEmpty()) {
    System.out.println("name must not be blank");
    return;
}
~~~

`String.strip()` (có từ Java 11) loại bỏ một số khoảng trắng Unicode theo `Character.isWhitespace`. Nếu tên chỉ chứa các khoảng trắng mà `strip` nhận diện, chuỗi còn lại rỗng và bị từ chối.

Đối với `times`, cần xác thực hai tầng: (1) chuyển được sang `int`; (2) giá trị thuộc miền được phép. Đối với cờ:

~~~java
boolean upper = false;
if (args.length == 3) {
    if (!"--upper".equals(args[2])) {
        System.out.println("unknown option");
        return;
    }
    upper = true;
}
~~~

So sánh chuỗi bằng `String.equals` thay vì `==`: `==` kiểm tra hai tham chiếu có trỏ cùng một đối tượng hay không, không phải so nội dung chuỗi.

**Không ghi mật khẩu/token trực tiếp trong đối số CLI** nếu môi trường có thể hiển thị danh sách tiến trình, lịch sử shell hoặc log lệnh. Trong ứng dụng thật, không tự động echo toàn bộ `args` khi chúng có thể mang thông tin nhạy cảm. Bài demo chỉ in những đối số không nhạy cảm được cung cấp để học cú pháp.

## 8. Truyền kết quả về hệ điều hành: mã thoát

Ứng dụng dòng lệnh thường cần phân biệt thành công với cú pháp/đầu vào sai. Một quy ước phổ biến:

- **Exit status 0**: xử lý thành công.
- **Exit status khác 0**, ví dụ 2: đầu vào/lời gọi không hợp lệ theo hợp đồng của chương trình.

~~~java
public static void main(String[] args) {
    int status = run(args);
    if (status != 0) {
        System.exit(status);
    }
}
~~~

`System.exit(2)` kết thúc JVM với mã 2; đây là lời gọi ở ranh giới ứng dụng, **không nên đưa vào một method tiện ích thư viện** khiến caller không có cơ hội xử lý.

Chương trình demo bên dưới cố ý in thông báo cách dùng lên **stdout** để có thể đối chiếu stdout chính xác ở các tình huống học tập. Trong CLI thực tế, lỗi/usage thường được in trên **stderr** bằng `System.err`, còn output dữ liệu thành công in trên `System.out`; khi áp dụng cần định nghĩa hợp đồng rõ ràng. Cũng lưu ý: dấu nhắc lệnh và exit code không phải một phần nội dung stdout.

## 9. Chương trình Java 17+ hoàn chỉnh

Tạo file đúng tên **`CommandLineArgsDemo.java`**:

~~~java
import java.util.Locale;

public final class CommandLineArgsDemo {
    private CommandLineArgsDemo() {}

    static int run(String[] args) {
        // Minh họa vị trí và nội dung từng phần tử đầu vào.
        System.out.println("args.length=" + args.length);
        for (int i = 0; i < args.length; i++) {
            System.out.println("args[" + i + "]=" + args[i]);
        }

        // Hai đối số bắt buộc, một tùy chọn.
        if (args.length < 2 || args.length > 3) {
            System.out.println("error: expected 2 or 3 arguments");
            printUsage();
            return 2;
        }

        String name = args[0].strip();
        if (name.isEmpty()) {
            System.out.println("error: name must not be blank");
            return 2;
        }

        int times;
        try {
            times = Integer.parseInt(args[1]);
        } catch (NumberFormatException ex) {
            System.out.println("error: times must be an integer");
            return 2;
        }

        if (times < 1 || times > 5) {
            System.out.println("error: times must be 1..5");
            return 2;
        }

        boolean upper = false;
        if (args.length == 3) {
            if (!"--upper".equals(args[2])) {
                System.out.println("error: unknown option " + args[2]);
                return 2;
            }
            upper = true;
        }

        System.out.println("name=" + name);
        System.out.println("times=" + times);
        System.out.println("upper=" + upper);

        String message = "Hello, " + name + "!";
        if (upper) {
            message = message.toUpperCase(Locale.ROOT);
        }
        for (int i = 0; i < times; i++) {
            System.out.println(message);
        }
        return 0;
    }

    private static void printUsage() {
        System.out.println(
                "usage: java -cp . CommandLineArgsDemo <name> <times> [--upper]");
    }

    public static void main(String[] args) {
        int status = run(args);
        if (status != 0) {
            System.exit(status);
        }
    }
}
~~~

**Yêu cầu:** JDK 17 trở lên, không cần Maven, Gradle, thư viện ngoài hoặc preview features. Lưu bằng UTF-8. `run` làm phần xử lý đầu vào, còn `main` là điểm vào và trả mã thoát khi lỗi. Chương trình **không tự đoán** tên và số lần chào nếu thiếu đối số.

### Biên dịch

**Bash (Linux/macOS):**

~~~bash
javac --release 17 -encoding UTF-8 CommandLineArgsDemo.java
~~~

**PowerShell (Windows):**

~~~powershell
javac --release 17 -encoding UTF-8 .\CommandLineArgsDemo.java
~~~

Biên dịch tạo `CommandLineArgsDemo.class` trong thư mục hiện tại. Dùng `-cp .` khi chạy từ thư mục chứa file `.class`.

### Chạy hợp lệ — tên có dấu cách

~~~bash
java -cp . CommandLineArgsDemo "Lan Anh" 2
~~~

Cùng cú pháp trên sử dụng được trong PowerShell với các đối số minh họa này.

**Exact expected stdout:**

~~~text
args.length=2
args[0]=Lan Anh
args[1]=2
name=Lan Anh
times=2
upper=false
Hello, Lan Anh!
Hello, Lan Anh!
~~~

### Chạy hợp lệ — dùng cờ `--upper`

~~~bash
java -cp . CommandLineArgsDemo Lan 3 --upper
~~~

**Exact expected stdout:**

~~~text
args.length=3
args[0]=Lan
args[1]=3
args[2]=--upper
name=Lan
times=3
upper=true
HELLO, LAN!
HELLO, LAN!
HELLO, LAN!
~~~

`Locale.ROOT` giúp chuyển chữ hoa ổn định cho thông điệp ví dụ, tránh những khác biệt chuyển đổi chữ do locale mặc định của máy. Cả hai lệnh hợp lệ trả **exit status 0**.

### Chạy thiếu đối số

~~~bash
java -cp . CommandLineArgsDemo
~~~

**Exact expected stdout:**

~~~text
args.length=0
error: expected 2 or 3 arguments
usage: java -cp . CommandLineArgsDemo <name> <times> [--upper]
~~~

Vì không đọc `args[0]` khi chưa đủ phần tử, chương trình không gặp `ArrayIndexOutOfBoundsException`. Nó in hướng dẫn và kết thúc với **exit status 2**.

### Chạy với số không hợp lệ

~~~bash
java -cp . CommandLineArgsDemo Lan abc
~~~

**Exact expected stdout:**

~~~text
args.length=2
args[0]=Lan
args[1]=abc
error: times must be an integer
~~~

`Integer.parseInt("abc")` phát sinh `NumberFormatException`. Chương trình bắt ngoại lệ đúng nơi để giải thích điều kiện đầu vào và trả **exit status 2**.

### Chạy với số ngoài phạm vi

~~~bash
java -cp . CommandLineArgsDemo Lan 0
~~~

**Exact expected stdout:**

~~~text
args.length=2
args[0]=Lan
args[1]=0
error: times must be 1..5
~~~

Giá trị `0` parse thành công nhưng không hợp lệ theo quy tắc số lần chào `1..5`. Vì thế vẫn trả **exit status 2**. Đây là ví dụ rõ ràng cho việc **chuyển kiểu đúng chưa đồng nghĩa dữ liệu hợp lệ**.

## 10. Đọc nhiều đối số và lựa chọn cách thiết kế CLI

Nếu một ứng dụng nhận **danh sách nhiều tên** không cố định số lượng, có thể dùng một vòng lặp:

~~~java
for (String name : args) {
    System.out.println("Hello, " + name + "!");
}
~~~

Đây là mã minh họa trong một `main` phù hợp, khác hợp đồng của `CommandLineArgsDemo` trong mục 9. Với danh sách biến độ dài, vòng lặp enhanced `for` phù hợp khi chỉ cần giá trị; vòng `for` có chỉ số phù hợp khi cần biết vị trí.

Trong dự án thật, nên xác định rõ phong cách đầu vào:

| Dạng CLI | Ví dụ | Điểm cần tự xử lý |
|---|---|---|
| Positional arguments | `tool input.txt 3` | Số lượng, vị trí, chuyển kiểu |
| Optional flag | `tool input.txt --verbose` | Cờ được hỗ trợ, giá trị mặc định |
| Key-value option | `tool --count=3` | Phân tích khóa, giá trị và trùng khóa |
| Nhiều mục | `tool Alice Bob Carol` | Số lượng không cố định, có cần trích dẫn tên |
| Input tương tác | `Scanner(System.in)` | Đọc từ stdin trong lúc chạy, **không phải `args`** |

`String[] args` phục vụ dữ liệu **được truyền khi khởi chạy**, trong khi `System.in`/`Scanner` phục vụ dữ liệu **được đọc trong lúc chương trình chạy**. Chúng là hai nguồn input khác nhau, có thể kết hợp nhưng không tự thay thế cho nhau.

Nếu một CLI phức tạp nhiều subcommand, cờ có giá trị, trợ giúp hoặc định dạng chuẩn, thư viện parse dòng lệnh có thể hữu ích; trước hết cần hiểu chính xác `args` là một mảng chuỗi.

## 11. Các lỗi phổ biến

| Sai lầm | Nguyên nhân | Cách xử lý |
|---|---|---|
| Đọc `args[0]` ngay, không kiểm tra `length` | Không có đối số gây `ArrayIndexOutOfBoundsException` | Kiểm tra đủ số phần tử |
| Cho rằng `args[1]` đã là `int` | Phần tử luôn có kiểu `String` | Gọi `Integer.parseInt` và bắt lỗi |
| Parse được số liền xem là hợp lệ | Giá trị có thể âm, 0 hoặc vượt giới hạn | Kiểm tra thêm miền giá trị |
| Nhầm tên class hoặc `-cp` là một đối số | Chúng là phần của lệnh launcher | Đối số ứng dụng bắt đầu **sau tên lớp** |
| Gõ tên nhiều từ không có trích dẫn | Shell tách thành nhiều phần tử | Dùng dấu nháy theo cú pháp shell |
| Dùng `args[0] == "--upper"` | `==` so tham chiếu | `"--upper".equals(args[0])` |
| Nghĩ Java tự hiểu mọi cờ `--flag` | `args` chỉ là mảng các chuỗi | Viết parser cho các cờ được hỗ trợ |
| Lặng lẽ chấp nhận cờ không biết | Lỗi đánh máy của người dùng bị bỏ qua | Từ chối và thông báo |
| Đặt `-ea` sau tên lớp rồi mong JVM bật assertions | Sau tên lớp thường được truyền cho `args` | Đặt tùy chọn JVM trước tên lớp |
| Đưa mật khẩu vào tham số CLI và echo toàn bộ args | Có thể lộ trong lịch sử shell/log/process list | Tránh truyền/ghi thông tin nhạy cảm như vậy |
| Dùng `assert` để kiểm tra input bắt buộc | Assertion có thể bị tắt | Dùng `if`, ngoại lệ, thông báo lỗi luôn chạy |
| In lỗi không cho người dùng biết cú pháp cần nhập | Khó sửa lời gọi | Ghi thông điệp cụ thể và usage thích hợp |

## 12. Bài tập có đáp án

**A — Xác định mảng.** Với lệnh:

~~~bash
java -cp . CommandLineArgsDemo "Mai Anh" 2 --upper
~~~

`args.length` bằng bao nhiêu, `args[0]` là gì?

**Đáp án:** `args.length == 3`; `args[0]` là `"Mai Anh"`, `args[1]` là `"2"`, `args[2]` là `"--upper"`.

**B — Đối số thứ nhất.** Với `java -cp . CommandLineArgsDemo`, thao tác nào gây lỗi nếu thực hiện ngay?

**Đáp án:** đọc `args[0]`, vì mảng không có phần tử. Phải kiểm tra `args.length` trước.

**C — Chuyển kiểu.** Vì sao `Integer.parseInt(args[1])` có thể thất bại?

**Đáp án:** vì người dùng có thể truyền chuỗi không đại diện cho một `int` hợp lệ, ví dụ `"abc"` hoặc giá trị vượt miền `int`. Phải bắt `NumberFormatException` hoặc xử lý theo hợp đồng.

**D — Đối số sai thứ tự.** Lệnh `java -cp . CommandLineArgsDemo 3 Lan` có hợp lệ theo giao diện bài không?

**Đáp án:** **Không**. `args[0]` bị hiểu là tên `3`; `args[1]` là `Lan`, không parse thành `int` được.

**E — Hai shell.** Muốn đưa tên `Lan Anh` thành **một phần tử**, phải làm gì?

**Đáp án:** dùng trích dẫn phù hợp như `"Lan Anh"` trong các lệnh Bash/PowerShell minh họa.

**F — Flag tùy chọn.** Với lệnh `java -cp . CommandLineArgsDemo Lan 2 --upper`, ai quyết định ý nghĩa của `--upper`?

**Đáp án:** mã ứng dụng. Java launcher chuyển chuỗi này tới `args[2]`; trong `run`, code kiểm tra `"--upper".equals(args[2])`.

**G — Phân biệt dòng lệnh và stdin.** `Scanner(System.in)` có tự đọc lại phần tử `args[0]` không?

**Đáp án:** **Không**. `System.in` là luồng input trong khi chạy; `args` là mảng các đối số đã được truyền khi khởi động.

## 13. Checklist và kết luận

- [ ] Biết `public static void main(String[] args)` nhận mảng chuỗi đối số ứng dụng.
- [ ] Đọc đúng `args.length` và phần tử `args[i]`.
- [ ] Không nhầm `-cp`, tên lớp chính với nội dung `args`.
- [ ] Kiểm tra số lượng đối số trước khi đọc theo chỉ số.
- [ ] Biết mọi `args[i]` ban đầu đều là `String`.
- [ ] Biết chuyển `String` sang `int` và bắt `NumberFormatException`.
- [ ] Xác thực miền giá trị sau khi parse.
- [ ] Hiểu cách dấu nháy của shell nhóm đối số có khoảng trắng.
- [ ] Phân biệt đối số bắt buộc và cờ tùy chọn do ứng dụng tự định nghĩa.
- [ ] Dùng `String.equals` để so cờ, không dùng `==`.
- [ ] Biết xử lý lỗi và mã thoát không bằng 0 khi lời gọi không hợp lệ.
- [ ] Tránh in bí mật từ command line trong log/console.
- [ ] Phân biệt đối số CLI với input đọc lúc chạy từ `System.in`.
- [ ] Biên dịch `CommandLineArgsDemo.java` với JDK 17+, chạy đủ trường hợp tốt/xấu và đối chiếu exact stdout.

**Kết luận:** `String[] args` là **mảng chuỗi đối số do người chạy cung cấp cho ứng dụng Java**. Đọc đúng phải bắt đầu từ `args.length`, hiểu **thứ tự và vị trí**, chuyển kiểu khi cần và **validate** dữ liệu trước khi xử lý. Dấu nháy shell, tùy chọn JVM, cờ riêng ứng dụng và input từ `System.in` thuộc các lớp xử lý khác nhau; phân biệt rõ chúng giúp viết CLI Java dễ sử dụng và an toàn.