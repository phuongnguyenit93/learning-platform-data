# `Reader.ready()` khác kiểm tra EOF như thế nào trong Java I/O?

## 1. Hai câu hỏi hoàn toàn khác nhau

Khi đọc dữ liệu bằng `java.io.Reader`, có hai vấn đề dễ bị nhầm lẫn:

- **Readiness:** Nếu gọi `read()` tiếp, thao tác đó có phải **chờ dữ liệu đầu vào** hay không? Đây là mục đích của `Reader.ready()`.
- **End of stream / EOF:** Nguồn đã **hết ký tự** theo hợp đồng của reader chưa? Điều này được báo bởi **giá trị trả về của thao tác đọc**, chẳng hạn `read() == -1` hoặc `readLine() == null`.

**`ready()` không phải phương thức kiểm tra EOF.** Một reader có thể chưa sẵn sàng *ở thời điểm hiện tại* nhưng vẫn còn dữ liệu sẽ xuất hiện sau; ngược lại, có reader trả `true` khi đã EOF bởi lần `read()` tiếp theo có thể trả `-1` ngay mà không cần chờ.

Theo hợp đồng của Java SE 17, `Reader.ready()` trả `true` nếu lời gọi `read()` kế tiếp **được bảo đảm không chặn để đợi input**. Trả `false` chỉ là **không có bảo đảm đó**; điều này **không có nghĩa** lời gọi `read()` chắc chắn sẽ chặn.

~~~text
                 CÂU HỎI: điều gì xảy ra khi đọc tiếp?
                         |
             +-----------+-----------+
             |                       |
        reader.ready()           reader.read()
             |                       |
       true / false          ký tự / -1 / IOException
             |                       |
       mức sẵn sàng             nội dung / EOF / lỗi
       cho read() tiếp
~~~

Ví dụ thực tế: kết nối mạng có thể chưa nhận thêm ký tự ở thời điểm kiểm tra, nên `ready()` là `false`, nhưng bên gửi vẫn đang hoạt động và sẽ gửi tiếp; **đó chưa phải EOF**.

## 2. Bảng so sánh API

| Tiêu chí | `Reader.ready()` | `Reader.read()` / `Reader.read(char[])` | `BufferedReader.readLine()` |
| --- | --- | --- | --- |
| Mục đích | Hỏi liệu `read()` kế tiếp có phải đợi input | Thực sự đọc ký tự | Thực sự đọc một dòng |
| Giá trị thông thường | `boolean`: `true`/`false` | `int`: giá trị char, số ký tự, hoặc `-1` | `String` hoặc `null` |
| Dấu hiệu EOF | **Không có** | **`-1`** | **`null`** |
| Có thể chặn? | Không dùng để đọc dữ liệu | Có thể chặn chờ ký tự, lỗi hoặc EOF | Có thể chặn đến khi có dòng, lỗi hoặc EOF |
| Có tiêu thụ ký tự? | Không lấy ký tự về cho chương trình | Có | Có |
| Dùng làm điều kiện vòng lặp đến hết file? | **Không** | **Có**, kiểm tra `-1` | **Có**, kiểm tra `null` |

Với `Reader.read()`, kết quả là số nguyên `0` đến `65535` đại diện cho một đơn vị UTF-16 (`char`), hoặc `-1` khi hết nguồn. **Không ép kiểu sang `char` trước khi kiểm tra `-1`**: phép ép kiểu loại bỏ ý nghĩa giá trị sentinel EOF.

Với `Reader.read(char[], off, len)`, kết quả là số ký tự đọc được, hoặc `-1` nếu hết nguồn; nếu `len == 0`, phương thức được phép trả `0` mà không đọc ký tự nào. Với lần đọc có `len > 0` trên các reader tuân thủ hợp đồng chuẩn, việc không có ký tự vì EOF được biểu diễn bằng `-1`, không phải `0`.

Với `BufferedReader.readLine()`, một dòng rỗng trả `""` (String rỗng); **chỉ `null` là EOF**. Dòng cuối không có ký tự xuống dòng vẫn được trả về nếu còn ký tự.

## 3. Chương trình Java 17+ chứng minh `ready() == true` vẫn có thể ở EOF

`StringReader` đọc từ một chuỗi đã nằm sẵn trong bộ nhớ. Đối với một `StringReader` đang mở, thao tác `read()` có thể được giải quyết ngay, kể cả khi không còn ký tự và nó sẽ trả `-1`. Triển khai `StringReader.ready()` của JDK trả `true` trong trường hợp này.

Tạo file **ReadyAtEofDemo.java**:

~~~java
import java.io.IOException;
import java.io.StringReader;

public class ReadyAtEofDemo {
    public static void main(String[] args) throws IOException {
        try (StringReader reader = new StringReader("Hi")) {
            System.out.println("readyBefore=" + reader.ready());
            System.out.println("first=" + (char) reader.read());
            System.out.println("second=" + (char) reader.read());

            int next = reader.read();
            System.out.println("readAtEof=" + next);
            System.out.println("readyAtEof=" + reader.ready());
            System.out.println("readAgain=" + reader.read());
        }
    }
}
~~~

Biên dịch và chạy với JDK 17 trở lên:

~~~bash
javac -encoding UTF-8 ReadyAtEofDemo.java
java ReadyAtEofDemo
~~~

Stdout:

~~~text
readyBefore=true
first=H
second=i
readAtEof=-1
readyAtEof=true
readAgain=-1
~~~

Diễn giải:

1. `readyBefore=true`: hai ký tự trong bộ nhớ có thể đọc ngay.
2. Hai lần `read()` lần lượt tiêu thụ `H` và `i`.
3. Lần đọc tiếp theo trả **`-1`**: đã EOF.
4. `readyAtEof=true` nhưng vẫn EOF. Lý do: lần `read()` kế tiếp trả `-1` ngay, không phải đợi input.
5. Lần đọc sau nữa tiếp tục trả `-1`.

**Kết luận từ ví dụ:** Nếu dùng `while (reader.ready())` để kiểm tra “còn dữ liệu không”, chương trình có thể tiếp tục lặp ở EOF mà không dừng; nếu bên trong đọc ký tự bằng ép kiểu `(char) reader.read()`, nó có thể xử lý sai `-1` như dữ liệu bình thường.

**Giới hạn của ví dụ:** `readyAtEof=true` ở trên là hành vi cụ thể của `StringReader`; không được suy ra rằng mọi `Reader` đều trả `true` ở EOF. Điều đúng cho mọi Reader là **không dùng `ready()` làm dấu EOF**.

## 4. `ready() == false` cũng không chứng minh đã hết dữ liệu

Ngược lại, `false` chỉ nói reader **không bảo đảm** `read()` tiếp theo sẽ không cần chờ. Có thể việc đọc sẽ chặn, cũng có thể trả ký tự ngay, báo lỗi ngay hoặc trả EOF ngay tùy reader.

Tình huống điển hình: một nguồn streaming (chẳng hạn dữ liệu đến từ mạng hoặc đường ống) chưa có ký tự để trả ở thời điểm kiểm tra. Nếu người gửi chỉ tạm dừng, không có lý do gì để kết luận nguồn đã đóng.

~~~text
Thời điểm T0: receiver có thể thấy ready() == false
Thời điểm T1: sender gửi tiếp các byte
Thời điểm T2: read() có thể trả ký tự
Thời điểm T3: sender đóng luồng theo giao thức
Thời điểm T4: read() có thể trả -1 (EOF)
~~~

Các thời điểm trên chỉ là kịch bản minh họa, không phải lời hứa rằng mọi Reader sẽ trả `false` tại T0 hay kết thúc đúng thứ tự thời gian đó.

**Sai lầm phổ biến:**

~~~java
// SAI: ready() == false không chứng minh EOF.
while (reader.ready()) {
    int ch = reader.read();
    // Xử lý ch...
}
~~~

Đoạn này có thể **bỏ sót dữ liệu** nếu `ready()` tạm thời trả `false`; với một reader cụ thể luôn ready tại EOF, cũng có nguy cơ lặp vô hạn nếu không tự kiểm tra kết quả `read()`.

**Cách đúng khi yêu cầu là đọc toàn bộ ký tự đến EOF:**

~~~java
// Đúng: cần có Reader reader còn mở và xử lý IOException.
int ch;
while ((ch = reader.read()) != -1) {
    // Dùng (char) ch sau khi đã loại trừ giá trị -1.
    System.out.print((char) ch);
}
~~~

Đây là mảnh code dành cho phương thức đã có reader hợp lệ; nó có thể **chặn khi chưa có dữ liệu**. Nếu luồng không bao giờ đóng và không có quy tắc kết thúc khác, vòng lặp cũng có thể chờ vô thời hạn. Đó là vấn đề về vòng đời của nguồn dữ liệu, không thể sửa bằng `ready()`.

## 5. `BufferedReader.ready()` và ý nghĩa của dữ liệu trong bộ đệm

`BufferedReader` là lớp bọc (`decorator`) có bộ đệm ký tự nhằm giảm số lần đọc nguồn bên dưới. Theo Java SE 17, `BufferedReader.ready()` có thể trả `true` **khi bộ đệm còn ký tự hoặc reader bên dưới sẵn sàng**.

~~~text
InputStream (byte)
       |
       v
InputStreamReader (decode byte -> char theo charset)
       |
       v
BufferedReader (giữ trước một số char trong buffer)
       |
       +--> ready(): buffer còn ký tự / nguồn sẵn sàng?
       |
       +--> read() / readLine(): thực sự tiêu thụ ký tự
~~~

Ví dụ về bộ đệm:

- Reader nền có thể **tạm không sẵn sàng** để đọc thêm byte/ký tự mới từ nguồn.
- Nhưng `BufferedReader` đã đọc trước một số ký tự vào buffer nên **`BufferedReader.ready()` vẫn có thể là `true`**.
- Khi buffer cạn, `ready()` có thể đổi thành `false`; điều này không có nghĩa nguồn đã EOF.
- Khi EOF đến, kết quả đáng tin cậy vẫn là **`read() == -1`** hoặc **`readLine() == null`**, không phải một giá trị cố định của `ready()`.

**Một khác biệt tinh tế:** Hợp đồng `ready()` nói về **lời gọi `read()` kế tiếp** không chặn để đợi input. Nếu chương trình gọi `readLine()`, chỉ có một vài ký tự trong buffer mà chưa có dấu kết thúc dòng, `readLine()` vẫn có thể cần chờ thêm. Vì thế **`ready() == true` không phải bảo đảm rằng toàn bộ dòng tiếp theo đã sẵn sàng**.

Tương tự, một lần gọi `read(char[])` yêu cầu nhiều ký tự; ngay cả khi đã đọc được một số ký tự, việc điền thêm phần còn lại phụ thuộc reader và điều kiện của nguồn. Không dùng `ready()` để cam kết độ dài thông điệp hoặc tốc độ đọc toàn bộ payload.

## 6. Đọc từng dòng đến EOF: cách kiểm tra khác với chuỗi rỗng

Tạo file **ReadLinesDemo.java**:

~~~java
import java.io.BufferedReader;
import java.io.IOException;
import java.io.StringReader;

public class ReadLinesDemo {
    public static void main(String[] args) throws IOException {
        String input = "first\n\nlast";

        try (BufferedReader reader =
                new BufferedReader(new StringReader(input))) {
            String line;
            while ((line = reader.readLine()) != null) {
                System.out.println("line=[" + line + "]");
            }
            System.out.println("EOF");
        }
    }
}
~~~

Chạy:

~~~bash
javac -encoding UTF-8 ReadLinesDemo.java
java ReadLinesDemo
~~~

Stdout:

~~~text
line=[first]
line=[]
line=[last]
EOF
~~~

Ví dụ cho thấy:

- `"first"`: dòng đầu kết thúc bởi LF.
- `""`: dòng thứ hai trống, **không phải EOF**.
- `"last"`: dòng cuối không có ký tự xuống dòng vẫn được trả về.
- `null`: không còn dòng nào để đọc, lúc đó mới in `EOF`.

Không viết `while (reader.readLine() != "")` hoặc `while (reader.ready())` để thay cho phép so sánh với `null`. Biến `line` trong điều kiện phải được gán từ **một lần đọc duy nhất** để không vô tình bỏ qua dòng.

Với file text UTF-8 thực tế, có thể dùng:

~~~java
// Mảnh code trong phương thức có Path path và xử lý IOException.
try (BufferedReader reader =
        java.nio.file.Files.newBufferedReader(
                path, java.nio.charset.StandardCharsets.UTF_8)) {
    String line;
    while ((line = reader.readLine()) != null) {
        // Xử lý từng dòng.
    }
}
~~~

Chọn charset tường minh giúp việc chuyển từ byte file sang ký tự đúng theo định dạng. Việc bọc buffer hỗ trợ hiệu năng nhưng không đổi điều kiện phát hiện EOF.

## 7. Đọc theo từng khối char: chú ý giá trị đếm và `-1`

Nếu cần đọc dữ liệu lớn, thay vì đọc từng ký tự, dùng buffer:

~~~java
// Mảnh code trong phương thức có Reader reader và xử lý IOException.
char[] buffer = new char[4096];
int count;
while ((count = reader.read(buffer, 0, buffer.length)) != -1) {
    // Chỉ vùng [0, count) có ký tự mới đọc trong lượt này.
    process(buffer, 0, count);
}
~~~

Ở đây `process` là hàm xử lý do chương trình cung cấp; ví dụ minh họa không phải chương trình chạy độc lập. Kích thước buffer 4096 là mức tối đa mỗi lần yêu cầu; **`read` không hứa trả đủ 4096 ký tự**. Nếu trả 120 thì chỉ 120 phần tử đầu là dữ liệu mới. Chạy vòng lặp đến khi `-1`, không dựa vào `ready()`.

Trong hợp đồng chuẩn `Reader.read(char[], off, len)`, với `len > 0`, `-1` là EOF; nếu `len == 0`, có thể nhận `0`, kể cả khi đã EOF. Vì vậy dùng mảng không rỗng và `buffer.length > 0` khi tạo vòng lặp đọc bình thường.

Nếu dữ liệu là nhị phân (ảnh, ZIP...), dùng `InputStream.read(byte[])` và `-1` tương ứng. **`InputStream.available()` cũng không phải cách phát hiện EOF**: nó cho biết ước lượng byte có thể đọc mà không chặn, không phải kích thước còn lại của luồng hay dấu kết thúc.

## 8. Vì sao không dùng `ready()` để làm polling hoặc timeout?

Một đoạn kiểu này thường có vẻ hợp lý nhưng không an toàn:

~~~java
// SAI nếu mục tiêu là đọc hết một stream:
while (true) {
    if (reader.ready()) {
        int ch = reader.read();
        if (ch == -1) break;
        handle(ch);
    } else {
        // Giả sử đã EOF rồi thoát, hoặc vòng lặp nóng chờ.
        break;
    }
}
~~~

Nếu `ready()` trả `false` chỉ vì dữ liệu chưa tới, `break` làm **mất phần dữ liệu sẽ đến sau**. Thay `break` bằng việc lặp liên tục không giới hạn có thể khiến chương trình **busy-spin**, chiếm CPU. Mặt khác, ngay cả khi `ready()` trả `true`, những bước xử lý khác vẫn có thể tốn thời gian hoặc phát sinh lỗi; đó không phải cơ chế deadline/timeouts.

Phải chọn giải pháp theo yêu cầu:

| Yêu cầu | Hướng xử lý |
| --- | --- |
| Đọc file/dữ liệu hữu hạn đến hết | `read() != -1`, `readLine() != null` hoặc `read(buffer) != -1` |
| Giao thức biết trước độ dài message | Đọc đủ độ dài đã định, xử lý thiếu byte/ký tự như lỗi giao thức |
| Message kết thúc bằng delimiter | Đọc đến delimiter đã quy định, không suy từ `ready()` |
| Socket có thể chờ lâu | Cấu hình timeout hoặc giới hạn vòng đời ở tầng socket/protocol; xử lý EOF và lỗi riêng |
| Kết nối event-driven/nonblocking | Dùng API được thiết kế cho nonblocking I/O như `java.nio.channels.Selector` với channel phù hợp, thay vì giả lập bằng `Reader.ready()` |
| Chỉ muốn biết thao tác `read()` tiếp có được bảo đảm không chờ input | Khi đó mới cân nhắc `ready()`, nhưng vẫn phải kiểm tra giá trị trả về của `read()` |

**EOF của socket:** thường chỉ xuất hiện khi phía gửi kết thúc chiều gửi của kết nối, hoặc giao thức/nguồn kết thúc và reader tiêu thụ hết dữ liệu đã đệm; “tạm thời chưa có byte” không phải EOF. Đọc socket có thể trả lỗi I/O thay vì EOF tùy tình huống.

Đối với dữ liệu có dấu ngắt dòng, `readLine()` có thể chờ lâu khi bên gửi chưa gửi newline dù có một số ký tự. Nếu cần phản hồi tức thời theo ký tự, thiết kế giao thức/reader cho yêu cầu đó thay vì dùng `ready()` để đoán “đã có một dòng”.

## 9. Các trường hợp biên cần nhớ

**Reader đang đóng:** `ready()` và `read()` có thể ném `IOException`; đóng luồng không phải một cách thay cho kiểm tra `-1`. Trong chương trình đúng, dùng try-with-resources để đảm bảo giải phóng tài nguyên.

**Buffer còn dữ liệu sau khi nguồn bên dưới đã hết:** `BufferedReader` vẫn có thể trả những ký tự đã đệm. Chỉ khi ký tự trong buffer đã được tiêu thụ hết thì thao tác đọc tiếp mới trả `-1`.

**Nguồn vô hạn hoặc chưa biết khi nào kết thúc:** một lần `read()` có thể chặn để đợi dữ liệu; việc duyệt “đến EOF” không tự có deadline. Ứng dụng cần timeout, đóng luồng, tín hiệu dừng hoặc frame protocol phù hợp.

**Một ký tự Unicode nhìn thấy không luôn là một `char`:** `Reader.read()` trả về một đơn vị UTF-16; một code point ngoài BMP có thể cần hai lần đọc. Điều kiện EOF vẫn là `-1`, bất kể cách ghép surrogate pair của dữ liệu.

**`readLine() == null` khác `readLine().isEmpty()`:** chuỗi rỗng là một dòng hợp lệ; nên gán kết quả vào biến rồi kiểm tra `null` trước khi xử lý.

**Nhiều thread cùng đọc một reader:** gọi `ready()` ở thread A rồi `read()` ở thread B hoặc có thread khác tiêu thụ dữ liệu ở giữa có thể tạo trạng thái thay đổi theo thời gian. Không dùng `ready()` như cơ chế phối hợp đồng bộ giữa các thread.

## 10. Bảng sửa lỗi nhanh

| Code / suy luận sai | Vì sao sai | Cách sửa |
| --- | --- | --- |
| `if (!reader.ready()) EOF` | False không khẳng định hết dữ liệu | Gọi `read()` và kiểm tra `-1` |
| `while (reader.ready()) { ... }` | Có thể bỏ dữ liệu, hoặc không tự dừng ở EOF | Dùng kết quả đọc làm điều kiện |
| `char c = (char) reader.read()` ngay lập tức | Có thể ép `-1` thành `char`, làm mất dấu EOF | Giữ `int`, kiểm tra `-1` trước |
| `while ((line = reader.readLine()) != "")` | So sánh sai ngữ nghĩa dòng trống và EOF | `while ((line = reader.readLine()) != null)` |
| `reader.ready() == true` nghĩa là đã có đủ nguyên một dòng | Readiness của `read()` không nói đủ delimiter | `readLine()` có thể phải chờ tiếp |
| `InputStream.available() == 0` nghĩa là EOF | Available là tín hiệu sẵn có, không phải EOF | Dùng `InputStream.read() == -1` |
| `read(char[])` luôn lấp đầy buffer | Reader được phép trả ít hơn độ dài yêu cầu | Xử lý đúng `count` mỗi lần |
| `ready()` thay thế socket timeout | Không cam kết thời hạn, không phải API timeout | Dùng deadline/timeout ở nguồn hoặc giao thức |

## 11. Câu hỏi tự kiểm tra

**Câu 1.** `reader.ready()` trả `false`. Có thể kết luận luồng đã EOF chưa?  
**Đáp án:** Không. Lần đọc tiếp theo chưa được bảo đảm là không chặn; dữ liệu vẫn có thể tới sau, hoặc lần đọc có thể trả ngay.

**Câu 2.** `reader.ready()` trả `true`. Có bảo đảm lần `read()` kế tiếp trả một ký tự không?  
**Đáp án:** Không. Nó chỉ bảo đảm không chặn vì chờ input; lần đọc vẫn có thể trả `-1` ở EOF. `StringReader` là ví dụ dễ thấy.

**Câu 3.** Khi đọc `Reader` từng ký tự, đâu là điều kiện dừng chuẩn?  
**Đáp án:** Đọc vào biến `int` và dừng khi `read() == -1`.

**Câu 4.** `BufferedReader.readLine()` trả `""`. Có phải EOF?  
**Đáp án:** Không. Đó là dòng rỗng; EOF được thể hiện bằng `null`.

**Câu 5.** Tại sao `BufferedReader.ready()` có thể `true` dù nguồn bên dưới không sẵn sàng?  
**Đáp án:** Vì buffer của `BufferedReader` đã có sẵn ký tự để trả ngay.

**Câu 6.** Nếu đang đọc socket mà thiếu byte cuối cùng, `ready()` giúp xác định tổng số byte còn lại không?  
**Đáp án:** Không. Phải dựa vào framing/giao thức hoặc EOF thực sự, và dùng timeout khi cần; `ready()` không cung cấp độ dài payload.

**Câu 7.** `ready()` trả `true` có bảo đảm `readLine()` không chặn không?  
**Đáp án:** Không. Một ký tự có thể đã sẵn sàng nhưng chưa có dấu kết thúc dòng, nên `readLine()` vẫn có thể chờ thêm.

## 12. Tài liệu chuẩn để đối chiếu hợp đồng

- [Java SE 17 — Reader](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/Reader.html): đặc tả `ready()`, `read()`, `read(char[], off, len)`.
- [Java SE 17 — BufferedReader](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/BufferedReader.html): đặc tả bộ đệm, `ready()` và `readLine()`.
- [Java SE 17 — StringReader](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/StringReader.html): reader từ chuỗi trong bộ nhớ, ví dụ để quan sát EOF.

**Điểm nhớ cốt lõi:** **`ready()` trả lời câu hỏi về khả năng đọc mà không phải chờ input**, còn **EOF được báo bởi kết quả thực sự của `read()` (`-1`) hoặc `readLine()` (`null`)**. Trong vòng lặp xử lý toàn bộ dữ liệu, luôn đặt điều kiện dừng theo kết quả đọc, không theo `ready()`.
