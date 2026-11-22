# Console.readPassword và cách tránh hiển thị mật khẩu trong Java 17+

## 1. Tại sao cần readPassword?

Ứng dụng CLI đôi khi cần hỏi người dùng mật khẩu, passphrase hoặc credential. Nếu dùng một API đọc văn bản thông thường, những ký tự người dùng gõ có thể được **echo** (hiển thị lại) trong terminal, dễ bị người đứng gần, camera, bản ghi terminal hoặc phần mềm ghi màn hình quan sát.

Java cung cấp lớp **`java.io.Console`** và hai phương thức chuẩn, vẫn được hỗ trợ trong các JDK hiện đại:

```java
char[] password = console.readPassword();
char[] secret = console.readPassword("Nhập mật khẩu: ");
```

Đây là snippet: `console` phải là một `Console` hợp lệ. Cả hai overload đọc với **echo bị tắt**, trả **`char[]`** chứa những ký tự đã nhập (không gồm ký tự kết thúc dòng); khi gặp **EOF**, chúng trả về **`null`**.

Ba trách nhiệm cần phân biệt:

1. **Che nội dung trong lúc gõ:** `Console.readPassword(...)` xử lý echo cho lần đọc ở terminal.
2. **Không làm lộ nội dung sau khi đọc:** ứng dụng không được in/log/đưa mật khẩu vào exception, telemetry hoặc object debug.
3. **Giới hạn vòng đời secret trong bộ nhớ:** giữ trong `char[]` khi có thể, xóa phần tử bằng `Arrays.fill(...)` trong `finally` sau khi bên nhận đã xử lý xong.

**Quan trọng:** `readPassword` chỉ là kỹ thuật **nhập liệu trên console**, không phải cơ chế mã hóa, lưu trữ password, xác thực tài khoản, phòng chống keylogger hay sandbox. Không dùng việc “không hiện ký tự” làm bằng chứng một hệ thống đã được bảo mật toàn diện.

## 2. Phân biệt các API của Console

| Phương thức | Kết quả | Chế độ echo | Mục đích |
| --- | --- | --- | --- |
| `readPassword()` | `char[]` hoặc `null` | **Tắt echo** | Đọc bí mật, sau khi đã hiển thị prompt riêng nếu cần. |
| `readPassword(String fmt, Object... args)` | `char[]` hoặc `null` | **Tắt echo** | Hiển thị prompt định dạng rồi đọc bí mật. |
| `readLine()` | `String` hoặc `null` | Không bảo đảm tắt echo | Đọc tên, lựa chọn menu hoặc văn bản không nhạy cảm. |
| `readLine(String fmt, Object... args)` | `String` hoặc `null` | Không bảo đảm tắt echo | Prompt rồi đọc văn bản thường. |
| `printf(...)` / `format(...)` | `Console` | Chỉ ghi dữ liệu | Hiển thị thông báo **không chứa secret**. |

Ví dụ prompt được phép:

```java
char[] password = console.readPassword("Mật khẩu: ");
```

Ví dụ prompt động nhưng **không truyền dữ liệu bí mật**:

```java
char[] password = console.readPassword(
        "Mật khẩu cho %s: ", "tài khoản thử nghiệm");
```

Hai đoạn là snippet nằm trong phương thức Java đã có `console`. `fmt` tuân theo cú pháp `Formatter`; format sai hoặc thiếu đối số có thể ném `IllegalFormatException`. Để đơn giản và an toàn, dùng format string cố định, tránh dựng prompt từ dữ liệu không kiểm soát; **không đưa mật khẩu vào prompt**.

**Không sử dụng `readLine()` hoặc `Scanner.nextLine()` thay cho `readPassword()`** khi muốn ẩn ký tự trên console: các API đọc dòng này không có hợp đồng tắt echo. Việc đọc bằng `Scanner` cũng thường tạo `String` khó chủ động xóa nội dung.

## 3. System.console() có thể không tồn tại

Lấy console bằng:

```java
Console console = System.console();
```

Cần import `java.io.Console`. Theo hợp đồng API, `System.console()` **có thể trả `null`** nếu JVM không có console device phù hợp. Điều này thường gặp trong một số IDE, test runner, dịch vụ nền hoặc môi trường redirect I/O. Tùy JDK và cách host cấu hình terminal, kết quả có thể khác; không mặc định rằng mọi tiến trình Java đều có console tương tác.

Mẫu không an toàn:

```java
char[] secret = System.console().readPassword();
```

Khi `System.console()` là `null`, đoạn trên ném `NullPointerException`. Cách phòng ngừa:

```java
Console console = System.console();
if (console == null) {
    System.err.println(
            "Không có console tương tác; hãy chạy từ terminal.");
    return;
}
```

Đây là snippet trong phương thức trả về `void`. Sau khi kiểm tra, mới gọi `console.readPassword(...)`. Nếu ứng dụng chạy không tương tác, cần thiết kế **kênh cung cấp credential riêng** (ví dụ credential provider/secret manager được quản lý), không tự động hạ cấp sang `System.in`, shell command arguments hoặc biến cấu hình không được bảo vệ.

Việc `Console` bị thiếu là trạng thái bình thường ở một số môi trường. Nó không có nghĩa `readPassword` đã trở nên lỗi thời.

## 4. Chương trình Java 17+ hoàn chỉnh: đọc, không echo, xóa char[]

Bài tập có tên file **`PasswordPromptDemo.java`**. Nó nhận một giá trị bí mật, không in nội dung, kiểm tra EOF và đầu vào rỗng, rồi xóa mảng trong `finally`. **Không có logic đăng nhập hoặc kiểm tra password đúng/sai**; chương trình chỉ minh họa nhập liệu an toàn hơn.

```java
import java.io.Console;
import java.io.IOError;
import java.util.Arrays;

public final class PasswordPromptDemo {

    public static void main(String[] args) {
        Console console = System.console();

        if (console == null) {
            System.err.println(
                    "Không có console tương tác; hãy chạy từ terminal.");
            return;
        }

        char[] password = null;

        try {
            // Console quản lý echo trong lần đọc này.
            password = console.readPassword("Nhập mật khẩu: ");

            if (password == null) {
                console.printf("Đã hủy nhập (EOF).%n");
                return;
            }

            if (password.length == 0) {
                console.printf("Không chấp nhận dữ liệu rỗng.%n");
                return;
            }

            // Demo chỉ xác nhận đã nhận input, KHÔNG xác thực.
            // Với ứng dụng thật: chuyển tới API xử lý char[] phù hợp,
            // không chuyển thành String nếu không cần.
            console.printf(
                    "Đã đọc dữ liệu bí mật; chưa thực hiện xác thực.%n");

        } catch (IOError ex) {
            System.err.println("Không thể đọc mật khẩu từ console.");
        } finally {
            if (password != null) {
                // Giảm thời gian giá trị còn trong mảng do ta sở hữu.
                Arrays.fill(password, '\0');
            }
        }
    }
}
```

### 4.1. Biên dịch và chạy

Từ terminal tương tác thực sự, với JDK 17 trở lên:

```bash
javac PasswordPromptDemo.java
java PasswordPromptDemo
```

Ví dụ những dòng **người sử dụng nhìn thấy** khi đã gõ một giá trị không rỗng rồi ấn Enter:

```text
Nhập mật khẩu:
Đã đọc dữ liệu bí mật; chưa thực hiện xác thực.
```

Trong lúc gõ, **ký tự mật khẩu không được echo**. Cách xuống dòng, vị trí con trỏ hoặc giao diện prompt còn tùy terminal và JDK; đây là **minh họa hiển thị**, không phải cam kết từng byte stdout cố định cho mọi host. Không chèn mật khẩu mẫu vào transcript vì dữ liệu không nên xuất hiện trên màn hình.

**Các nhánh có thể xảy ra:**
- Không có console: in `Không có console tương tác; hãy chạy từ terminal.` lên stderr và không đọc input.
- EOF (hết dữ liệu): `readPassword` trả `null`; in `Đã hủy nhập (EOF).` và thoát.
- Người dùng chỉ ấn Enter: có thể nhận mảng dài 0; in `Không chấp nhận dữ liệu rỗng.` và dọn mảng.
- Đầu vào không rỗng: in thông báo đã nhận dữ liệu; **không phải thông báo đăng nhập thành công**.
- I/O lỗi: `readPassword` có thể phát sinh `IOError`; chương trình in lỗi trung tính.
- Nhánh thoát sớm hoặc lỗi: `finally` xóa `password` nếu đã có mảng.

**Vì sao không ghi độ dài mật khẩu?** Độ dài cũng có thể là metadata nhạy cảm. Bài học tập trung vào nhận input mà không tiết lộ nội dung hay đặc điểm không cần thiết.

## 5. Vì sao Java trả char[] chứ không trả String?

`String` bất biến: sau khi tạo ra một `String` chứa password, không có API bảo đảm xóa nội dung của String theo yêu cầu. `char[]` cho phép ghi đè **mảng mà ứng dụng đang giữ**:

```java
char[] chars = { 'a', 'b', 'c' };
try {
    // Truyền chars cho API có thể xử lý char[].
} finally {
    Arrays.fill(chars, '\0');
}
```

Đây là **snippet** có import `java.util.Arrays`. Ký tự `'\0'` là ký tự NUL, không phải chuỗi gồm hai ký tự. `Arrays.fill(chars, '\0')` ghi đè từng phần tử mảng bằng NUL.

| So sánh | `char[]` | `String` |
| --- | --- | --- |
| Có thể chủ động ghi đè nội dung? | Có, qua `Arrays.fill`. | Không, vì bất biến. |
| `readPassword` trả trực tiếp kiểu này? | Có. | Không. |
| Có bảo đảm không có bản sao trong heap/OS? | **Không.** | **Không.** |
| Có tự động mã hóa thông tin? | Không. | Không. |
| Phù hợp xử lý secret ngắn hạn? | Có, nếu downstream API hỗ trợ `char[]` và vòng đời được kiểm soát. | Chỉ khi API bắt buộc, chấp nhận hạn chế không thể xóa trực tiếp. |

**Giới hạn của zeroization:** việc xóa `char[]` chỉ ảnh hưởng **mảng hiện tại**. JDK, thư viện, GC, native buffers, OS hoặc logic ứng dụng có thể tạo bản sao. Không hứa rằng `Arrays.fill` loại bỏ mọi dấu vết trong tiến trình hoặc trong memory dump. Xem đó là **giảm cửa sổ phơi lộ dữ liệu**, không thay thế mã hóa, xác thực hoặc kiểm soát quyền truy cập.

Nếu một API bắt buộc nhận `String`, việc chuyển `new String(password)` tạo bản sao không thể trực tiếp zero hóa. Khi bắt buộc phải tương tác với API đó, hãy hiểu thiết kế thư viện, chỉ tạo bản sao khi cần và giảm vòng đời reference; không được khẳng định “không có String” khi thực tế có.

## 6. Những cách vô tình làm lộ password

Sau khi `readPassword` không echo input, chính code vẫn có thể **in** giá trị. Các dòng sau là **anti-pattern tuyệt đối tránh với secret thật**:

```java
// KHÔNG làm với mật khẩu thực:
System.out.println(password);
System.out.print(password);
System.out.println(Arrays.toString(password));
System.out.println(new String(password));
logger.info("password=" + new String(password));
```

Đây là **các đoạn phản ví dụ**, không phải chương trình khuyến nghị chạy. `PrintStream.println(char[])` và `print(char[])` có overload nhận mảng và in **từng ký tự**, nên câu `System.out.println(password)` có thể làm lộ toàn bộ mật khẩu. `Arrays.toString(password)` cũng làm lộ các phần tử dưới dạng chữ. `new String(password)` sao chép thông tin vào một String tồn tại độc lập với mảng gốc.

Đừng trông chờ rằng “password là `char[]` nên logging sẽ tự ẩn”. Các tình huống khác:
- Tạo exception message bằng phép nối `String` chứa secret.
- Đưa secret vào bản ghi log DEBUG/TRACE, telemetry, request traces, crash reports.
- Dùng `toString()` của object có field bí mật.
- Ghi secret trong file cấu hình hoặc test snapshot.
- Đưa password qua process arguments (ví dụ `--password=...`) hoặc câu lệnh shell, có thể xuất hiện trong shell history hay process inspection.
- Dán secret vào terminal recorder hoặc lệnh mẫu để debug.

**Chỉ hiển thị trạng thái trung tính.** Ví dụ: “Đã nhận dữ liệu”, “Không có console”, “Không thể đọc dữ liệu”. Đừng thêm giá trị đã nhập, ký tự đầu/cuối, số ký tự, hash debug hoặc exception chứa credential khi không có lý do bảo mật chính đáng.

## 7. Finally là bắt buộc trong mọi nhánh thoát

Một `char[]` phải được xóa sau khi kết thúc xử lý; viết duy nhất `Arrays.fill` ở cuối block mà bỏ qua các nhánh `return`/exception dễ gây lỗi. Mẫu kiểm soát vòng đời:

```java
char[] secret = null;
try {
    secret = console.readPassword("Mật khẩu: ");
    if (secret == null) {
        return;
    }
    if (secret.length == 0) {
        return;
    }

    // Sử dụng secret với API xử lý phù hợp.
} finally {
    if (secret != null) {
        Arrays.fill(secret, '\0');
    }
}
```

Đây là snippet trong method `void` đã có `console` và import `Arrays`. `finally` chạy khi thoát qua `return` hoặc exception theo ngữ nghĩa Java thông thường, nhưng **không hứa chạy nếu tiến trình/JVM bị chấm dứt đột ngột**.

### 7.1. Nhập hai lần để xác nhận

Nếu ứng dụng muốn hỏi lại cùng một passphrase, hãy dọn **cả hai mảng**:

```java
char[] first = null;
char[] repeated = null;
try {
    first = console.readPassword("Mật khẩu: ");
    if (first == null) {
        return;
    }

    repeated = console.readPassword("Nhập lại: ");
    if (repeated == null) {
        return;
    }

    boolean same = Arrays.equals(first, repeated);
    console.printf(same
            ? "Hai lần nhập trùng nhau.%n"
            : "Hai lần nhập không trùng nhau.%n");
} finally {
    if (first != null) {
        Arrays.fill(first, '\0');
    }
    if (repeated != null) {
        Arrays.fill(repeated, '\0');
    }
}
```

Đây là **snippet cho UX xác nhận nhập**, không phải ví dụ xác thực người dùng. `Arrays.equals(char[],char[])` không cung cấp bảo đảm so sánh thời gian hằng cho verifier mật mã. Đối với xác thực thực tế, dùng hệ thống identity và primitive xác thực được thiết kế cho mục tiêu đó; không so sánh plaintext từ client với mật khẩu hardcode hay credential trong source.

**Ownership rất quan trọng:** không xóa mảng khi một thành phần bất đồng bộ còn đang sử dụng nó. Hãy xác định rõ API nào giữ reference/copy và chỉ dọn khi consumer đã hoàn tất. Khi truyền secret sang thư viện có thể tạo bản sao, việc xóa bản gốc không tự xóa các bản sao đó.

## 8. Phân biệt echo, zeroization, xác thực và lưu trữ

| Biện pháp | Bảo vệ điều gì? | Có sẵn trong readPassword? |
| --- | --- | --- |
| Tắt echo | Không hiển thị ký tự đang nhập trên console | **Có**. |
| Trả `char[]` | Cho phép code ghi đè mảng do mình sở hữu | **Có**. |
| Xóa mảng sau dùng | Giảm thời gian secret còn trong ứng dụng | **Không tự động**; dùng `finally`/`Arrays.fill`. |
| TLS/mã hóa giao tiếp | Bảo vệ credential khi truyền trên mạng | Không. |
| Password hashing có salt phía backend | Bảo vệ verifier được lưu | Không. |
| MFA/passkeys/identity policies | Xác thực và giảm nguy cơ chiếm tài khoản | Không. |
| Cách ly process và chống keylogger | Hạn chế xâm nhập môi trường nhập liệu | Không. |

Một ứng dụng CLI chuẩn có thể dùng `readPassword` để lấy credential **rồi** chuyển cho thành phần xác thực có hợp đồng API và biện pháp bảo vệ riêng. Không viết `if (new String(password).equals("secret123"))` làm bài mẫu “xác thực an toàn”; đó là so sánh secret cứng trong source, dễ tạo bản sao String và không xử lý thỏa đáng vấn đề lưu trữ/verifier.

## 9. Làm gì khi chạy trong IDE, CI hoặc container?

**Terminal có người nhập:** chạy file `.class` từ PowerShell, Windows Terminal, terminal macOS/Linux có console tương tác. Kiểm tra `System.console()` để biết process có được cấp Console API phù hợp hay không; đặc điểm có thể tùy JDK/host.

**IDE/test runner:** một số IDE chỉ cung cấp input/output giả lập nên `System.console()` trả `null`. Nếu cần test nhánh terminal, mở terminal thật hoặc cấu hình chế độ terminal phù hợp nếu IDE hỗ trợ. Không chữa bằng cách dùng `Scanner.nextLine` và giả định echo vẫn ẩn.

**Dịch vụ nền, cron, CI:** thông thường không cần người gõ passphrase trong lúc start. Hãy nhận credential qua secret manager, credential provider, identity service hoặc cơ chế cấp secret được nền tảng cho phép, có phân quyền và rotation. Đừng coi việc đặt password vào `args` hoặc environment variables là an toàn tuyệt đối: mức độ hiển thị và log khác nhau giữa OS, CI và container runtime.

**Từ xa/SSH:** `readPassword` tắt echo tại console mà JVM được gắn vào, nhưng không ngăn các thành phần có quyền cao hơn ghi lại bàn phím/terminal. Chỉ sử dụng host, kết nối và công cụ quản trị đáng tin cậy.

## 10. EOF, chuỗi rỗng và lỗi đọc

`Console.readPassword` có ba trường hợp khác nhau cần xử lý rõ:

1. **`null`** — EOF, không có mảng để duyệt. Không được gọi `password.length`, `new String(password)` hoặc `Arrays.fill(password, ...)` khi chưa kiểm tra null.
2. **`char[]` rỗng** — người dùng có thể nhấn Enter ngay. Quy tắc chấp nhận hay từ chối phụ thuộc nghiệp vụ; ví dụ bài học từ chối.
3. **`char[]` không rỗng** — ứng dụng đã nhận input. Điều này **không có nghĩa** mật khẩu hợp lệ hay xác thực thành công.

Ngoài kết quả bình thường, `readPassword` có thể ném **`IOError`** khi có lỗi I/O. Overload nhận format có thể ném **`IllegalFormatException`** nếu prompt format sai. Những ngoại lệ này không cho phép chúng ta bỏ `finally`; nếu muốn bắt để báo lỗi thân thiện, đừng đưa dữ liệu bí mật vào thông báo.

Tùy phiên bản JDK/terminal, dấu xuống dòng sau khi nhập, rendering Unicode và cách hiển thị ký tự điều khiển có thể khác. Không dùng một transcript có placeholder như `[hidden]` để suy luận mật khẩu thật được in ra; `readPassword` không chủ động in nội dung đã đọc.

## 11. Kiểm thử thực tế mà không lộ secret

Để kiểm thử, **chỉ dùng mật khẩu thử nghiệm không nhạy cảm**, không đưa credential thật vào tài liệu, terminal recorder hoặc CI fixtures.

| Tình huống | Kết quả kỳ vọng |
| --- | --- |
| Nhập trong console có hỗ trợ | Ký tự không echo; ứng dụng chỉ in trạng thái. |
| Không có console | Code kiểm tra `null` và thoát có kiểm soát. |
| Gặp EOF | Nhận `null` và không dereference. |
| Nhập rỗng | Xử lý theo policy; không nhầm với EOF. |
| Có dữ liệu và thoát sớm | `finally` luôn ghi đè mảng khi kết thúc sử dụng. |
| Lỗi I/O | Không in secret hay nội dung nhạy cảm trong lỗi/log. |
| Cấu hình build/CI | Không cần hoặc không để lộ secret trong arguments/history. |
| Tích hợp xác thực | Kiểm tra riêng kênh truyền, backend, verifier và secret lifetime. |

Unit test thường nên tách **logic xử lý credential** khỏi **lớp tương tác console** bằng abstraction do ứng dụng định nghĩa, vì không phải lúc nào unit test cũng có terminal thật. Có thể kiểm tra một `char[]` giả lập có bị xóa sau khi xử lý, mà không cần tạo `Console` mới. End-to-end test với pseudo-terminal cần tắt log keystrokes và xóa toàn bộ dữ liệu test sau khi chạy.

Không cố khẳng định chỉ nhìn stdout sạch là đã an toàn; secret có thể vẫn được giữ trong heap, object copy hoặc log của thành phần khác.

## 12. Các lỗi phổ biến cần tránh

| Sai lầm | Hệ quả | Cách khắc phục |
| --- | --- | --- |
| `System.console().readPassword()` không kiểm tra | `NullPointerException` khi không có console | Lấy `Console` và kiểm tra `null`. |
| Dùng `readLine()` cho password | Không có hợp đồng tắt echo | Dùng `readPassword()`. |
| In `System.out.println(password)` | `PrintStream.println(char[])` có thể in nội dung bí mật | Không in/log mảng ký tự. |
| `Arrays.toString(password)` | Biểu diễn tất cả ký tự dưới dạng text | Tránh debug secret. |
| `new String(password)` tùy tiện | Tạo bản sao bất biến không xóa trực tiếp | Ưu tiên API nhận `char[]`. |
| Không có `finally` | Early return hoặc lỗi có thể bỏ qua xóa mảng | `Arrays.fill(password, '\0')` trong `finally`. |
| Tưởng `Arrays.fill` xóa mọi buffer | Không bảo đảm xóa bản sao của JDK/OS/thư viện | Hiểu đây chỉ là biện pháp giảm rủi ro. |
| Đọc thành công rồi tuyên bố “đăng nhập thành công” | Chưa có xác thực credential | Phân biệt input và authentication. |
| In secret trong prompt hoặc exception | Phá hỏng cơ chế che ký tự | Dùng message trung tính. |
| Tự fallback sang `Scanner` khi thiếu Console | Secret có thể echo hoặc bị ghi log | Thiết kế kênh cấp secret phù hợp. |
| Đưa mật khẩu qua CLI arguments | Có nguy cơ lịch sử shell/process inspection | Tránh command-line plaintext credentials. |
| So sánh mật khẩu server bằng `Arrays.equals` | Không phải verifier chuyên dụng thời gian hằng | Sử dụng cơ chế xác thực/password hashing phù hợp. |

## 13. Câu hỏi ôn tập

**Câu 1.** `Console.readPassword()` trả gì khi người dùng nhập xong? Vì sao không nên dùng `readLine()`?

**Đáp án:** Nó trả `char[]` hoặc `null` nếu EOF; trong khi nhập, echo bị tắt. `readLine` không hứa tắt echo và trả `String` khó xóa trực tiếp.

**Câu 2.** Sự khác nhau giữa `null` và mảng dài 0?

**Đáp án:** `null` là EOF; mảng dài 0 thể hiện input rỗng. Phải kiểm tra `null` trước `password.length`.

**Câu 3.** Có thể log `System.out.println(password)` vì `password` là mảng, không phải String?

**Đáp án:** Không. `println(char[])` in trực tiếp các ký tự của mảng, làm lộ secret.

**Câu 4.** Vì sao phải dùng `finally` cho `Arrays.fill(password, '\0')`?

**Đáp án:** Để xóa mảng đã nhận kể cả khi xử lý có `return`, exception hoặc một nhánh dừng sớm theo ngữ nghĩa Java bình thường.

**Câu 5.** Zero `char[]` có bảo đảm JVM không còn bản sao nào không?

**Đáp án:** Không; chỉ ghi đè mảng được truyền vào `Arrays.fill`. Các buffer/copy khác vẫn có thể tồn tại.

**Câu 6.** Không có console trong CI thì có nên đọc từ `Scanner(System.in)` mặc định không?

**Đáp án:** Không nên coi nó tương đương đọc không echo. Với chạy không tương tác, dùng kênh secret được thiết kế/quản lý riêng.

**Câu 7.** Hai lần `readPassword` và `Arrays.equals` đủ để xác thực tài khoản không?

**Đáp án:** Không. So sánh chỉ giúp xác nhận hai lần người dùng nhập có trùng nhau; xác thực tài khoản cần hệ thống identity và cơ chế verifier riêng.

## 14. Tài liệu chính thức

- [Oracle Java SE 17 — Console](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/Console.html): `readPassword` tắt echo, kiểu `char[]`, EOF, các overload và ghi chú chủ động xóa mảng.
- [Oracle Java SE 25 — Console](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/io/Console.html): API vẫn được hỗ trợ trong JDK hiện đại; không cần phụ thuộc overload chỉ có ở bản JDK mới hơn để chạy ví dụ Java 17.
- [Oracle Java SE 17 — System](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/System.html): `System.console()` và trường hợp không có console.
- [Oracle Java SE 17 — Arrays](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Arrays.html): `Arrays.fill(char[], char)`.
- [Oracle Java SE 17 — IOError](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/IOError.html): cơ chế báo lỗi I/O từ Console API.
