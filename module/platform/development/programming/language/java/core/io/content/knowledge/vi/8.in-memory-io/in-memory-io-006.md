# `PushbackInputStream` và `PushbackReader`

## Mục tiêu bài học

Khi đọc dữ liệu tuần tự, đôi lúc chương trình phải **xem trước một vài byte hoặc ký tự** để quyết định nhánh xử lý. Nếu đó là byte/ký tự thuộc về dữ liệu của bước tiếp theo, chương trình cần “trả lại” cho lần đọc sau. `java.io.PushbackInputStream` và `java.io.PushbackReader` cung cấp một **bộ đệm đẩy lại nhỏ** (*pushback buffer*) cho nhu cầu này.

Sau bài này, bạn có thể:

- Phân biệt pushback ở mức **byte** và mức **ký tự**.
- Sử dụng `read()`/`unread()` để nhìn trước dữ liệu (*lookahead*) mà vẫn giữ đúng thứ tự đọc.
- Hiểu **dung lượng cố định**, cơ chế đọc lại theo kiểu stack (LIFO đối với từng lần `unread`), hành vi tại EOF và ngoại lệ khi pushback buffer đầy.
- Áp dụng `PushbackReader` cho việc phân tích token/dấu phân cách và `PushbackInputStream` cho việc kiểm tra byte mở đầu, chẳng hạn UTF-8 BOM, trên một luồng trong bộ nhớ.
- So sánh pushback với `mark()`/`reset()`, `BufferedInputStream`, `BufferedReader`, `ByteArrayInputStream` và tự giữ một ký tự lookahead trong parser.
- Xác định điểm giới hạn: đây là **đọc tuần tự có khả năng trả lại một lượng nhỏ dữ liệu**, không phải cơ chế tua lại tệp tùy ý.

## 1. Vị trí trong Java I/O

Hai lớp nằm trong `java.io` và là **lớp bao (decorator)** cho nguồn đọc khác:

```text
InputStream nguồn byte
    │
    ▼
PushbackInputStream ──► read byte ──► xử lý
    ▲                       │
    └──────── unread(byte) ──┘

Reader nguồn ký tự
    │
    ▼
PushbackReader ─────► read char ──► phân tích text
    ▲                       │
    └──────── unread(char) ─┘
```

Ví dụ nguồn bên dưới có thể là `ByteArrayInputStream`, `FileInputStream`, `BufferedInputStream`, `StringReader` hoặc `InputStreamReader`.

Các lớp pushback **không ghi ngược dữ liệu về nguồn gốc**. `unread` chỉ đặt byte/ký tự vào buffer nội bộ của wrapper. Lần `read` kế tiếp lấy dữ liệu đã trả lại trước rồi mới đọc tiếp từ underlying stream/reader. Nếu nguồn là file, vị trí thực tế của file descriptor không bị tua lại bởi `unread`; nếu nguồn là mạng, byte cũng không bị gửi ngược qua socket.

### Pushback khác “rewind”

Giả sử nguồn chứa `A B C D`, trình đọc lấy `A`, `B`, rồi gọi `unread(B)`, `unread(A)`:

```text
Nguồn ban đầu:        A  B  C  D
Đã đọc từ nguồn:      A  B          (nguồn kế tiếp ở C)
Pushback buffer:     [A, B]        (A là phần tử sẵn sàng đọc)
Lần đọc tiếp:         A → B → C → D
```

Về quan sát ở wrapper, hai byte A/B xuất hiện lại; nhưng byte nguồn gốc **không được tua lại**. Đối với từng lần `unread(int)` riêng lẻ, phần tử vừa đẩy lại sẽ được đọc trước (LIFO). Nếu muốn trả lại một đoạn gồm nhiều byte/ký tự theo **thứ tự gốc**, hãy dùng `unread(byte[], off, len)` hoặc `unread(char[], off, len)` với đủ dung lượng, hoặc đẩy từng phần tử ngược thứ tự.

## 2. `PushbackInputStream`: trả lại byte

`PushbackInputStream` kế thừa `FilterInputStream`, nhận một `InputStream` bên dưới:

| Constructor | Ý nghĩa |
|---|---|
| `new PushbackInputStream(in)` | Bộ đệm pushback mặc định **1 byte** |
| `new PushbackInputStream(in, size)` | Bộ đệm pushback **`size` byte**, cố định; `size <= 0` không hợp lệ |

Các phương thức quan trọng:

| Phương thức | Hành vi |
|---|---|
| `read()` | Đọc byte pushback trước; nếu trống, đọc nguồn bên dưới; `0..255` hoặc `-1` (EOF) |
| `read(byte[], off, len)` | Đọc byte pushback còn có, sau đó nhận thêm dữ liệu từ nguồn theo hợp đồng `InputStream` |
| `unread(int b)` | Đẩy lại một byte; lần `read` kế tiếp nhận byte đó |
| `unread(byte[] b)` | Đẩy lại cả mảng byte, giữ thứ tự các phần tử khi đọc lại |
| `unread(byte[] b, int off, int len)` | Đẩy lại đoạn `b[off..off+len)` |
| `available()` | Ước tính byte có thể đọc mà không chặn, bao gồm byte pushback; **không** phải tổng byte còn lại |
| `skip(long n)` | Bỏ qua số byte theo hợp đồng `InputStream`, bao gồm phần đang pushback |
| `close()` | Đóng wrapper và underlying stream |

`read()` trả kiểu **`int`**, dù dữ liệu là byte: giá trị `0..255` là byte hợp lệ, còn `-1` nghĩa là hết nguồn. Khi dùng `unread`, **chỉ unread một byte đã đọc thành công**, không unread `-1` của EOF.

### Ví dụ 1 — đọc trước hai byte rồi trả lại đúng thứ tự

Lưu chương trình Java 17 vào **`PushbackByteDemo.java`**:

```java
import java.io.ByteArrayInputStream;
import java.io.IOException;
import java.io.PushbackInputStream;
import java.nio.charset.StandardCharsets;

public class PushbackByteDemo {
    public static void main(String[] args) throws IOException {
        byte[] source = "ABCDE".getBytes(StandardCharsets.UTF_8);

        try (PushbackInputStream input = new PushbackInputStream(
                new ByteArrayInputStream(source), 2)) {
            int first = input.read();
            int second = input.read();

            System.out.println("peeked: " +
                (char) first + (char) second);

            // unread từng byte: đẩy phần tử cuối trước.
            input.unread(second);
            input.unread(first);

            byte[] replayed = input.readNBytes(2);
            System.out.println("replayed: " +
                new String(replayed, StandardCharsets.UTF_8));
            System.out.println("remaining: " +
                new String(input.readAllBytes(), StandardCharsets.UTF_8));
        }
    }
}
```

Chạy:

```bash
javac PushbackByteDemo.java
java PushbackByteDemo
```

Kết quả chính xác:

```text
peeked: AB
replayed: AB
remaining: CDE
```

**Giải thích:** `first` là mã byte `A`, `second` là mã byte `B`. Để đọc lại theo thứ tự A rồi B, chương trình `unread(B)` **trước** và `unread(A)` **sau**. Buffer có dung lượng 2 nên chứa vừa hai byte. `readNBytes(2)` (Java 9+) lấy đúng hai byte pushback trong trường hợp cụ thể này; lần đọc tiếp tục sau đó nhận CDE từ nguồn. Vì ví dụ chỉ dùng ASCII, cast byte thành `char` ở phần hiển thị là hợp lý; **không cast từng byte UTF-8 thành ký tự** khi dữ liệu đa byte.

Dùng `try-with-resources` để đóng `PushbackInputStream`; đóng wrapper cũng đóng `ByteArrayInputStream` bên dưới (với stream trong bộ nhớ không có tài nguyên hệ điều hành phải giải phóng).

### Đẩy lại một mảng thay cho nhiều lời gọi

Khi nhìn trước một đoạn:

```java
byte[] prefix = new byte[4];
int n = input.read(prefix, 0, prefix.length);
if (n > 0) {
    input.unread(prefix, 0, n);
}
```

Đây là **đoạn minh họa**, giả sử `input` là `PushbackInputStream` có dung lượng pushback ít nhất 4 và đã khai báo/được xử lý `IOException`. Phần `prefix[0..n)` được trả lại để lần đọc kế tiếp tiếp tục theo **đúng thứ tự gốc**. `read(...)` có thể đọc **ít hơn 4 byte** ngay cả khi nguồn chưa EOF; mã thật cần lặp nếu giao thức phải chờ đúng 4 byte.

Không làm `input.unread(prefix, 0, 4)` nếu `n` chỉ bằng 2: như vậy sẽ đưa thêm những byte chưa từng đọc từ nguồn vào luồng dữ liệu.

## 3. `PushbackReader`: trả lại ký tự UTF-16 `char`

`PushbackReader` kế thừa `FilterReader`, nhận một `Reader`:

| Constructor | Ý nghĩa |
|---|---|
| `new PushbackReader(reader)` | Buffer pushback mặc định **1 `char`** |
| `new PushbackReader(reader, size)` | Buffer có thể chứa **`size` đơn vị `char`**, cố định |

Các phương thức tương ứng:

- `read()` đọc một đơn vị `char` và trả dưới dạng `int` (`0..65535` hoặc `-1` cho EOF).
- `read(char[], off, len)` đọc một đoạn ký tự.
- `unread(int c)`, `unread(char[] c)`, `unread(char[] c, int off, int len)` trả lại ký tự đã đọc.
- `ready()` cho biết khả năng đọc theo trạng thái buffer/reader; không nên biến kết quả thành cam kết rằng toàn bộ dòng dữ liệu đã sẵn có.
- `close()` đóng wrapper và reader bên dưới.

Quan trọng: `Reader` xử lý các **đơn vị UTF-16 `char`**, không tự động tách grapheme cluster hay Unicode code point. Chẳng hạn emoji 😀 dùng **hai `char`** trong một `String`. Nếu parser đọc theo `char`, nó phải xử lý surrogate pair nếu chính sách ngôn ngữ phân tích theo code point.

`PushbackReader` thích hợp khi parser text cần xem một ký tự để quyết định: “ký tự này thuộc token tiếp theo; tôi phải đẩy lại”. Nó **không** quay ngược quá trình giải mã byte ở `InputStreamReader`.

### Ví dụ 2 — nhìn trước dấu phân cách khi tách token

Lưu **`PushbackCharDemo.java`**:

```java
import java.io.IOException;
import java.io.PushbackReader;
import java.io.StringReader;

public class PushbackCharDemo {
    private static String readToken(PushbackReader reader)
            throws IOException {
        StringBuilder token = new StringBuilder();
        int ch;

        while ((ch = reader.read()) != -1) {
            if (ch == ',') {
                reader.unread(ch); // Token sau sẽ xử lý dấu phân cách.
                break;
            }
            token.append((char) ch);
        }
        return token.toString();
    }

    public static void main(String[] args) throws IOException {
        try (PushbackReader reader = new PushbackReader(
                new StringReader("alpha,beta"), 1)) {
            String first = readToken(reader);
            int delimiter = reader.read();
            String second = readToken(reader);

            System.out.println("first: " + first);
            System.out.println("delimiter: " + (char) delimiter);
            System.out.println("second: " + second);
        }
    }
}
```

Chạy:

```bash
javac PushbackCharDemo.java
java PushbackCharDemo
```

Kết quả:

```text
first: alpha
delimiter: ,
second: beta
```

Ở lần `readToken` đầu, parser đọc đến dấu phẩy và biết nó không thuộc nội dung token. `unread(',')` cho phép tầng gọi đọc chính dấu phẩy đó. Sau khi tầng gọi tiêu thụ delimiter, parser tiếp tục đọc `beta`. Vì chỉ cần xem trước một dấu phân cách, buffer **1 ký tự** đủ dùng.

Đây là ví dụ parser ASCII đơn giản. Với CSV thực tế, dấu phẩy có thể xuất hiện trong trường đặt trong dấu ngoặc kép, dấu ngoặc kép có escaping, có CRLF và nhiều quy tắc khác. Không dùng `readToken` trên làm CSV parser hoàn chỉnh.

## 4. Bộ đệm pushback có giới hạn cố định

Khi tạo:

```java
PushbackInputStream bytes = new PushbackInputStream(source, 2);
PushbackReader chars = new PushbackReader(reader, 2);
```

Đây là **đoạn minh họa**, với `source` là `InputStream` và `reader` là `Reader`. Nếu một wrapper vừa được tạo với capacity 2, nó có tối đa **2 đơn vị trống để unread**, không tăng kích thước tự động.

Ví dụ (chỉ minh họa):

```java
PushbackInputStream pb = new PushbackInputStream(source, 1);
int a = pb.read();
int b = pb.read();
pb.unread(b); // Một chỗ pushback đã được chiếm.
pb.unread(a); // IOException: pushback buffer đã đầy.
```

Không nên dựa vào chuỗi thông báo lỗi `push back buffer is full` trong logic nghiệp vụ; hãy xử lý loại ngoại lệ `IOException` và thiết kế dung lượng phù hợp. Nếu muốn peek tối đa N byte, cần cấp capacity ít nhất N **nếu có lúc phải trả lại toàn bộ N byte**. Dung lượng tối thiểu hợp lệ của constructor `(source, size)` là 1.

Việc `read()` lấy đi một byte đang pushback sẽ giải phóng một chỗ để `unread()` thêm. Buffer chỉ cần chứa **phần chưa đọc lại**; không phải lúc nào nó cũng chứa toàn bộ byte chương trình từng đọc.

### Thứ tự LIFO và unread mảng

Giả sử đã đọc A rồi B:

| Thao tác | Hai ký tự sẽ đọc lại |
|---|---|
| `unread(B)` rồi `unread(A)` | A, B |
| `unread(A)` rồi `unread(B)` | B, A |
| `unread(new byte[]{'A', 'B'})` | A, B |

Với `PushbackReader`, nguyên lý tương tự cho `char[]`. Lý do `unread(byte[])` giữ đúng thứ tự là API đã hỗ trợ đẩy lại **cả đoạn** theo trình tự của nó; bạn không phải tự đảo mảng trước khi gọi.

Đừng nhầm **pushback buffer** với **buffer đọc để tăng hiệu năng**. Buffer pushback phục vụ tính đúng đắn khi nhìn trước; buffer của `BufferedInputStream`/`BufferedReader` giảm nhiều thao tác đọc nhỏ từ underlying source. Một ứng dụng có thể dùng cả hai loại buffer, nhưng phải hiểu thứ tự lớp bao.

## 5. Ứng dụng byte lookahead: UTF-8 BOM

Một tình huống thực tế là kiểm tra ba byte đầu `EF BB BF` (UTF-8 BOM). Nếu định dạng cho phép BOM, chương trình có thể bỏ qua đúng ba byte này; nếu không có BOM, phải **trả lại những byte đã đọc thử** để nội dung văn bản không mất các ký tự đầu.

```text
                 Đọc tối đa 3 byte đầu
                       │
            ┌──────────┴───────────┐
            │                      │
      EF BB BF đúng            Không phải BOM
            │                      │
       Bỏ 3 byte            unread chính xác số
            │               byte đã đọc (0..3)
            └──────────┬───────────┘
                       ▼
              Decode phần còn lại
                     bằng UTF-8
```

Đây là **BOM ở mức byte**, vì vậy `PushbackInputStream` thích hợp. `PushbackReader` hoạt động **sau bước decode**, không dùng để quay ngược những byte decoder đã tiêu thụ. Không áp dụng quy tắc ba byte của UTF-8 BOM cho UTF-16 hoặc UTF-32: các encoding đó có BOM/endianness và độ dài khác.

### Ví dụ 3 — đọc BOM tùy chọn và không làm mất prefix

Lưu **`Utf8BomPushbackDemo.java`**:

```java
import java.io.ByteArrayInputStream;
import java.io.IOException;
import java.io.PushbackInputStream;
import java.nio.charset.StandardCharsets;

public class Utf8BomPushbackDemo {
    private static String decodeOptionalBom(byte[] data)
            throws IOException {
        try (PushbackInputStream input =
                 new PushbackInputStream(
                     new ByteArrayInputStream(data), 3)) {
            byte[] prefix = new byte[3];
            int count = 0;

            // Dùng read() từng byte để xử lý đúng cả nguồn rất ngắn.
            while (count < prefix.length) {
                int next = input.read();
                if (next == -1) {
                    break;
                }
                prefix[count++] = (byte) next;
            }

            boolean isBom = count == 3
                && (prefix[0] & 0xff) == 0xEF
                && (prefix[1] & 0xff) == 0xBB
                && (prefix[2] & 0xff) == 0xBF;

            if (!isBom) {
                // Trả lại chính các byte đã đọc, đúng thứ tự.
                input.unread(prefix, 0, count);
            }

            return new String(
                input.readAllBytes(), StandardCharsets.UTF_8);
        }
    }

    public static void main(String[] args) throws IOException {
        byte[] plain =
            "Xin chào".getBytes(StandardCharsets.UTF_8);
        byte[] withBom = new byte[3 + plain.length];
        withBom[0] = (byte) 0xEF;
        withBom[1] = (byte) 0xBB;
        withBom[2] = (byte) 0xBF;
        System.arraycopy(
            plain, 0, withBom, 3, plain.length);

        System.out.println("plain: " + decodeOptionalBom(plain));
        System.out.println("with BOM: " + decodeOptionalBom(withBom));
        System.out.println(
            "empty: [" + decodeOptionalBom(new byte[0]) + "]");
    }
}
```

Chạy Java 17+:

```bash
javac Utf8BomPushbackDemo.java
java Utf8BomPushbackDemo
```

Kết quả:

```text
plain: Xin chào
with BOM: Xin chào
empty: []
```

Chương trình đọc tối đa ba byte. Nếu **không có BOM**, `unread(prefix, 0, count)` giữ lại toàn bộ số byte đã nhìn trước, kể cả với file có 1 hoặc 2 byte. Nếu đúng BOM, chương trình không unread ba byte BOM mà tiếp tục decode phần còn lại. Nếu input rỗng, `count == 0`, không có byte nào cần đẩy lại.

**Giới hạn ví dụ:** `readAllBytes()` nạp toàn bộ dữ liệu vào bộ nhớ; phù hợp minh họa với `ByteArrayInputStream`, không phù hợp mặc định cho file/network rất lớn. Nếu cần stream liên tục, sau bước BOM detection dùng `InputStreamReader(input, StandardCharsets.UTF_8)` và `BufferedReader` để đọc dần. Một decoder nghiêm ngặt có thể sử dụng `StandardCharsets.UTF_8.newDecoder().onMalformedInput(CodingErrorAction.REPORT)`; constructor `new String(bytes, UTF_8)` thường thay byte lỗi bằng ký tự thay thế theo hợp đồng của nó. Chỉ loại BOM khi định dạng cho phép; có những giao thức yêu cầu UTF-8 **không BOM**.

### Ranh giới đọc không phải ranh giới ký tự UTF-8

Với dữ liệu UTF-8 có dấu tiếng Việt hay emoji, một ký tự có thể dùng 2–4 byte. `PushbackInputStream` chỉ nhìn thấy byte, không tự hiểu Unicode. Nếu bạn đọc đúng một byte đầu của emoji rồi coi nó là ký tự hoàn chỉnh, bạn sẽ giải mã sai. Với nội dung text, thường nên dùng một `InputStreamReader` xử lý charset, rồi `PushbackReader` để nhìn trước ký tự sau khi decode.

Không tự tách “message” theo số byte mỗi `read()` của socket: một message có thể phân mảnh ở nhiều lần đọc, và nhiều message có thể cùng một lần đọc. Pushback chỉ giúp phần **lookahead cục bộ**, không thay thế parser giao thức có framing đúng.

## 6. `mark()/reset()` khác pushback thế nào?

Nhiều ứng dụng chỉ cần nhìn trước một đoạn; ngoài pushback còn có cơ chế **đánh dấu và đọc lại**:

| Cơ chế | Cách hoạt động | Hợp khi nào |
|---|---|---|
| `PushbackInputStream` / `PushbackReader` | Sau khi đọc, gọi `unread` để đưa **dữ liệu đã chọn** vào buffer đầu luồng; dung lượng cố định | Peek một vài byte/ký tự, nhận diện prefix/delimiter |
| `BufferedInputStream.mark(readlimit)` / `reset()` | Ghi nhớ vị trí logic rồi trở lại vị trí đã đánh dấu nếu mark còn hợp lệ | Muốn đọc thử một đoạn và quay lại điểm mark |
| `BufferedReader.mark(readAheadLimit)` / `reset()` | Tương tự với các ký tự | Parser cần quay lại vị trí ký tự đã đánh dấu |
| Lưu giá trị vừa đọc vào biến `lookahead` | Parser giữ chính ký tự tiếp theo mà không unread | Parser có state machine, tokenizing phức tạp |
| `ByteArrayInputStream` / `StringReader` | Nguồn bộ nhớ có cơ chế mark/reset riêng | Input nhỏ đã có sẵn toàn bộ trong bộ nhớ |
| `SeekableByteChannel` / `RandomAccessFile` | Đọc lại tại vị trí theo offset khi nguồn hỗ trợ seek | File cần truy cập ngẫu nhiên |

**`PushbackInputStream` và `PushbackReader` không hỗ trợ `mark/reset`**: `markSupported()` trả `false`; `reset()` ném `IOException`; `mark(...)` không mang hiệu lực quay lại như mong đợi. Đừng “phòng xa” bằng cách gọi `mark()` trên wrapper pushback rồi trông chờ `reset()` cứu parser. Hãy chọn **một cơ chế lookahead** theo nhu cầu.

Khác biệt quan trọng: `mark/reset` thường quay lại **một vị trí đã đánh dấu**, trong khi `unread` cho phép đặt lại **những byte/ký tự cụ thể**. Chương trình có thể `unread` một giá trị không trùng với giá trị từng đọc; API cho phép đưa giá trị vào buffer, nhưng nếu làm vậy thì đang tạo dữ liệu tổng hợp, không chỉ tua lại. Nên tách logic **biến đổi luồng** khỏi logic **peek rồi unread đúng dữ liệu gốc**.

### Về nguồn dữ liệu trong bộ nhớ

`ByteArrayInputStream` và `StringReader` đã cung cấp khả năng mark/reset. Nếu toàn bộ dữ liệu đã ở trong bộ nhớ và bạn chỉ cần đọc lại một vị trí, thường không cần thêm wrapper pushback. Tuy nhiên pushback vẫn hữu ích để giữ một interface parser thống nhất giữa nguồn memory và file/network stream **không seek được**.

Với parser phức tạp cần lookahead dài, lexer/token stream có cursor riêng, trạng thái và giới hạn rõ ràng sẽ dễ kiểm soát hơn việc liên tục mở rộng pushback buffer.

## 7. Ghép `PushbackInputStream`, `PushbackReader` với bộ đệm khác

Thứ tự các lớp bao có thể ảnh hưởng đến kết quả:

```text
Raw byte stream
    ↓
BufferedInputStream         (tăng hiệu quả đọc byte)
    ↓
PushbackInputStream         (byte lookahead, ví dụ kiểm tra header)
    ↓
InputStreamReader(UTF-8)    (decode byte → char)
    ↓
PushbackReader              (char lookahead, ví dụ phân tích dấu phân cách)
    ↓
Parser
```

Đây là **một sơ đồ khái niệm**, không phải cấu hình bắt buộc. Không phải parser nào cũng cần cả hai lớp pushback. Nếu chỉ parse text, thường `InputStreamReader` + `PushbackReader` hoặc `BufferedReader` + state machine là đủ. Nếu cần kiểm tra BOM ở mức byte, có thể peek qua `PushbackInputStream` **trước** khi tạo decoder.

Với việc đẩy lại dữ liệu ở cấp byte, lớp tiếp nhận `unread` phải chính là wrapper qua đó lần đọc tiếp theo sẽ đi qua. Nếu một `BufferedInputStream` bên ngoài đã prefetch byte vào buffer riêng, gọi `unread` trên lớp pushback bên dưới có thể không làm byte xuất hiện ngay ở lần đọc kế tiếp từ lớp buffer bên ngoài. Thiết kế ownership của wrapper rõ ràng và không trộn đọc trực tiếp trên underlying stream sau khi đã đưa wrapper vào sử dụng.

### Reader và stream đọc byte không nên thay phiên tùy tiện

Khi `InputStreamReader` đã đọc byte từ underlying stream, decoder có thể giữ buffer và trạng thái nội bộ. Nếu một phần code đọc ký tự qua reader, phần khác trực tiếp đọc byte hoặc pushback tại stream dưới reader, thứ tự byte/char rất dễ sai.

Nên lựa chọn rõ một điểm làm chủ:

- **Xử lý protocol/header byte trước**, hoàn thành bước peek/unread, sau đó chuyển sang reader decode.
- **Xử lý nội dung ký tự**, dùng một reader và nếu cần peek thì bọc `PushbackReader` trên reader đó.
- Nếu cần cả mức byte và mức ký tự, mô tả ranh giới chuyển đổi và **không xen kẽ** hai cách đọc trên cùng nguồn.

Đặc biệt với Unicode, mỗi `read()` của `PushbackReader` trả về **một UTF-16 code unit**, không nhất thiết là một Unicode code point đầy đủ. Code point nằm ngoài BMP cần hai `char`; parser cần xử lý chúng như một cặp nếu grammar hoạt động trên code point.

## 8. EOF, lỗi I/O và vòng đời tài nguyên

### EOF không phải một byte/ký tự để unread

Một lời gọi `read()` trả `-1` khi không còn dữ liệu. `unread(-1)` **không phải lệnh “đặt EOF trở lại”**; nó có thể đưa giá trị byte/char lấy từ phần bit thấp của số nguyên vào buffer, làm biến dạng luồng. Luôn kiểm tra:

```java
int next = input.read();
if (next != -1) {
    input.unread(next);
}
```

Đoạn minh họa này dùng `PushbackInputStream input`, buffer còn chỗ và được xử lý `IOException`. Với `PushbackReader` cũng cần kiểm tra `-1`.

Nếu underlying source đã tới EOF, bạn **vẫn có thể đọc được byte/ký tự mới được unread hợp lệ** trước khi `read()` trở lại `-1`. Do đó “đã thấy EOF một lần” không có nghĩa mọi lần đọc wrapper về sau đều nhất thiết trả `-1`, nếu ứng dụng chủ động unread thêm dữ liệu.

### `read(byte[])` có thể trả ít hơn yêu cầu

Với file, network hoặc stream có nhiều tầng buffer, `read(buffer, off, len)` không bảo đảm lấp đầy `len` byte mỗi lần. Nếu parser cần đúng N byte header thì phải lặp đọc cho đến khi đủ, EOF hoặc lỗi, đồng thời giới hạn độ dài để tránh chờ vô hạn một input không hoàn chỉnh. `InputStream.readNBytes(n)` giúp đọc tối đa n byte nhưng vẫn có thể trả ít hơn khi EOF. Với text, `Reader.read(char[], off, len)` cũng phải xử lý đọc từng phần và EOF.

### `IOException`, buffer overflow và đóng tài nguyên

`unread` có thể ném `IOException` khi buffer không đủ chỗ hoặc stream/reader đã đóng. Các thao tác đọc có thể ném lỗi từ underlying source. Trong mã sản phẩm:

1. Xác định **số byte/ký tự tối đa phải nhìn trước** để cấp đúng dung lượng.
2. Gọi unread **đúng những dữ liệu đã read thành công**, theo đúng thứ tự.
3. Kiểm tra EOF và partial read.
4. Dùng try-with-resources cho wrapper sở hữu tài nguyên.
5. Không chia sẻ cùng wrapper giữa nhiều luồng đọc/ghi mà chưa thiết kế synchronization và quyền sở hữu rõ ràng.

Khi đóng `PushbackInputStream`/`PushbackReader`, wrapper đóng cả underlying source. Nếu source là `System.in` hoặc một reader dùng chung, không đặt wrapper trong scope đóng tùy tiện mà không hiểu ownership, vì nó có thể khiến phần khác của chương trình không còn đọc được.

## 9. Các lỗi phổ biến

### Lỗi 1: Tạo buffer mặc định 1 byte nhưng unread nhiều hơn

```java
PushbackInputStream pb = new PushbackInputStream(source);
pb.unread(new byte[] {0x01, 0x02}); // IOException do chỉ có 1 chỗ.
```

Đây là **phản ví dụ**, với `source` là `InputStream`, có xử lý `IOException`. Nếu parser cần nhìn trước hai byte, dùng `new PushbackInputStream(source, 2)`. Không phụ thuộc rằng Java sẽ tự mở rộng buffer.

### Lỗi 2: Unread nhiều lần theo thứ tự đọc

Đã đọc A, B mà gọi `unread(A)` rồi `unread(B)`, dữ liệu đọc lại sẽ là **B, A**. Cách đúng để trả lại A trước B là `unread(B)` rồi `unread(A)`, hoặc `unread(new byte[]{'A', 'B'})` khi có đủ chỗ.

### Lỗi 3: Tin `mark/reset` trên pushback

Cả hai wrapper pushback đều báo `markSupported() == false`. `reset()` không thay thế `unread`. Nếu cần quay lại một vị trí đánh dấu, chọn wrapper có hỗ trợ mark hoặc giữ cursor riêng.

### Lỗi 4: Đọc byte Unicode rồi ép thành `char`

UTF-8 có nhiều code point dùng nhiều byte, ví dụ chữ “é” là `C3 A9`. Hai byte không phải hai ký tự độc lập. Chỉ decode **sau khi** gom đúng chuỗi byte hoặc dùng streaming decoder/Reader. `PushbackReader` làm việc sau decode và thích hợp cho cú pháp theo ký tự.

### Lỗi 5: Nhận diện BOM mà làm mất byte đầu

Đọc thử 3 byte rồi bỏ luôn khi không phải `EF BB BF` sẽ làm mất ba byte đầu nội dung thật. Cần `unread` chính xác số byte đã đọc, kể cả nguồn chỉ có 1–2 byte. Không lấy `available()` làm tổng độ dài file hoặc phép kiểm tra đủ header.

### Lỗi 6: Ghép wrapper sai thứ tự và trộn underlying source

Nếu parser đọc qua `BufferedInputStream` bên trên nhưng code lại `unread` trên `PushbackInputStream` bên dưới, byte trả lại có thể chưa xuất hiện ngay do buffer bên trên còn dữ liệu. Không vừa đọc trực tiếp `source` vừa đọc qua wrapper của source; tránh bỏ qua dữ liệu đã buffer.

### Lỗi 7: Coi pushback là tính năng “seek”

Pushback không đặt lại file position, không phục hồi trạng thái giao thức trên mạng và không tự giúp tua lại vô hạn. Nếu cần truy cập offset tùy ý trong file, chọn `SeekableByteChannel`/`FileChannel` hoặc `RandomAccessFile`.

### Lỗi 8: Parser thiếu xử lý input lỗi hoặc malformed

Header có thể thiếu byte, dấu phân cách có thể không xuất hiện, text có thể chứa surrogate không hợp lệ hoặc byte UTF-8 sai. Pushback không kiểm tra tất cả tính hợp lệ đó. Cần validate định dạng, giới hạn bộ nhớ/thời gian đọc và xử lý `IOException`/EOF.

### Lỗi 9: Thêm pushback vào mọi stream vì tưởng tăng tốc

Pushback là công cụ **điều khiển lookahead**, không phải mặc định tối ưu I/O. Đối với đọc tuần tự thông thường, `BufferedInputStream`, `BufferedReader` hoặc đọc theo block có thể thích hợp hơn. Chỉ thêm pushback khi có logic phải trả lại dữ liệu.

## 10. Bảng quyết định lựa chọn

| Nhu cầu | API nên cân nhắc | Lý do |
|---|---|---|
| Peek 1–4 byte đầu của binary protocol | `PushbackInputStream` với capacity đủ | Trả lại prefix nếu không đúng magic/header |
| Kiểm tra UTF-8 BOM trước khi decode | `PushbackInputStream`, sau đó `InputStreamReader` | BOM được nhận diện ở mức byte |
| Peek dấu phân cách khi tokenize văn bản | `PushbackReader` | Làm việc với ký tự sau khi decode |
| Tokenizer có grammar phức tạp và lookahead dài | Parser giữ token/cursor riêng | Dễ biểu diễn trạng thái và backtracking |
| Muốn đọc thử rồi quay lại vị trí đã đánh dấu | `BufferedInputStream.mark/reset`, `BufferedReader.mark/reset` | Phù hợp cơ chế dấu mốc |
| Dữ liệu nhỏ đã nằm trong mảng byte | `ByteArrayInputStream` và cursor/mark | Ít lớp bọc hơn; vẫn dùng pushback nếu API parser yêu cầu |
| Muốn tua đến offset trong file | `FileChannel.position`, `SeekableByteChannel` | Truy cập vị trí thật, không phải buffer trả lại |
| Đọc text thông thường theo dòng | `BufferedReader.readLine` | Không cần lookahead tự quản nếu đã phân tách dòng |
| Đọc ký tự UTF-8 qua nhiều chunk | `InputStreamReader`/decoder streaming | Giữ trạng thái charset thay vì decode byte rời |

## 11. Bài tập tự kiểm tra

**Câu 1.** Nguồn chứa `XYZ`. Bạn đọc X và Y, sau đó gọi `unread(X)`, `unread(Y)` trên buffer đủ lớn. Hai ký tự đọc lại đầu tiên là gì?

**Đáp án:** Y rồi X. Pushback theo từng lần unread hoạt động kiểu LIFO. Để có X rồi Y, gọi `unread(Y)` trước.

**Câu 2.** Constructor `new PushbackReader(reader)` mặc định cho trả lại bao nhiêu `char` cùng lúc?

**Đáp án:** 1 `char`. Khi cần nhiều hơn, chỉ rõ `size` trong constructor.

**Câu 3.** Tại sao `unread(-1)` sau EOF là sai?

**Đáp án:** `-1` là sentinel báo hết dữ liệu, không phải byte/ký tự đã đọc. `unread` có thể đẩy giá trị rút từ `-1` vào buffer, làm giả dữ liệu.

**Câu 4.** Vì sao không dùng `PushbackReader` để kiểm tra ba byte `EF BB BF`?

**Đáp án:** `PushbackReader` hoạt động trên ký tự **sau khi decode**; ba giá trị đó là byte BOM UTF-8. Cần nhận diện mức byte bằng `PushbackInputStream` trước khi tạo reader.

**Câu 5.** Nếu `PushbackInputStream` có capacity 3, `read` được 2 byte, có thể `unread(prefix, 0, 2)` rồi đọc lại không?

**Đáp án:** Có, nếu buffer đang trống và chưa đóng. Hai byte đọc lại giữ đúng thứ tự trong prefix.

**Câu 6.** `PushbackInputStream.markSupported()` trả gì? `reset()` có đưa stream về đầu đoạn đọc thử không?

**Đáp án:** `false`. `reset()` ném `IOException`; phải dùng `unread` hoặc chọn wrapper có hỗ trợ mark/reset.

**Câu 7.** Vì sao không nên dùng `PushbackInputStream` như buffer đọc lớn?

**Đáp án:** Mục đích chính là trả lại **một lượng nhỏ dữ liệu lookahead**, buffer có kích thước cố định và không tự thay cho chiến lược buffering để tăng hiệu năng hay streaming parser có framing.

**Ghi nhớ:** `PushbackInputStream` trả lại **byte**, `PushbackReader` trả lại **`char`**. Cả hai đều đặt dữ liệu vào buffer nhỏ ở **đầu luồng wrapper**, không viết ngược vào nguồn và không hỗ trợ `mark/reset`. Chọn dung lượng theo nhu cầu peek, xử lý đúng thứ tự `unread`, EOF và charset; dùng chúng khi parser cần nhìn trước nhưng vẫn muốn đọc dữ liệu tuần tự qua cùng một interface.
