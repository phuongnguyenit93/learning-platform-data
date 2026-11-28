# Giải mã từng phần khi ký tự UTF-8 bị chia giữa các buffer

## 1. Mục tiêu và bối cảnh

Khi đọc dữ liệu UTF-8 từ socket, tệp lớn, HTTP body hoặc một luồng byte, ranh giới giữa các lần đọc không nhất thiết trùng với ranh giới ký tự. Một ký tự Unicode có thể được mã hóa bằng 1 đến 4 byte UTF-8. Vì vậy, một lần đọc có thể kết thúc ở giữa chuỗi byte của một ký tự.

Ví dụ, ký tự **€** được mã hóa thành ba byte:

~~~text
E2 82 AC
~~~

Nếu lần đọc thứ nhất chỉ nhận được `E2 82` và lần đọc tiếp theo mới nhận `AC`, hai byte đầu chưa đủ để tạo ký tự. Bộ giải mã phải giữ chúng lại, chờ byte tiếp theo rồi mới giải mã hoàn chỉnh.

Java cung cấp `CharsetDecoder` và `ByteBuffer` cho tình huống này. Điểm quan trọng là dùng cùng một decoder xuyên suốt luồng, gọi `decode(input, output, endOfInput)` với `endOfInput=false` khi còn dữ liệu và bảo toàn các byte chưa được tiêu thụ khi decoder trả về `UNDERFLOW`.

Sau bài học, bạn có thể:

- Giải thích vì sao một ký tự UTF-8 có thể bị chia qua hai lần đọc.
- Phân biệt giải mã từng khối độc lập với giải mã tăng dần bằng `CharsetDecoder`.
- Dùng `flip()`, `compact()` và `clear()` đúng trạng thái của `ByteBuffer`/`CharBuffer`.
- Xử lý `UNDERFLOW`, `OVERFLOW` và lỗi mã hóa.
- Báo EOF đúng lúc, gọi `flush()` và phát hiện chuỗi UTF-8 bị cắt cụt.
- Xây dựng bộ đọc UTF-8 tăng dần có thể xử lý dữ liệu đến theo từng khối.

Bài tập trung vào API NIO hiện đại như `StandardCharsets`, `CharsetDecoder` và `ByteBuffer`. Với UTF-8, hãy chỉ định tường minh `StandardCharsets.UTF_8` để quy tắc giải mã không phụ thuộc charset mặc định của môi trường.

## 2. Vì sao ranh giới buffer không phải ranh giới ký tự?

UTF-8 mã hóa một Unicode code point bằng số byte thay đổi:

| Khoảng code point | Số byte UTF-8 | Ví dụ |
| --- | ---: | --- |
| U+0000 đến U+007F | 1 | `A` → `41` |
| U+0080 đến U+07FF | 2 | `é` → `C3 A9` |
| U+0800 đến U+FFFF (trừ surrogate) | 3 | `€` → `E2 82 AC` |
| U+10000 đến U+10FFFF | 4 | `😀` → `F0 9F 98 80` |

Một luồng byte không biết trước nơi kết thúc của ký tự. Ví dụ, dữ liệu có thể đến như sau:

**Dữ liệu logic:** `A€B`

| Lần đọc | Byte nhận được | Ý nghĩa tại ranh giới |
| --- | --- | --- |
| 1 | `41 E2 82` | `41` là `A`; `E2 82` mới là phần đầu của `€`. |
| 2 | `AC 42` | `AC` hoàn tất `€`; `42` là `B`. |

Kết quả sau khi ghép output: **`A€B`**.

Nếu giải mã từng lần đọc như một mảng byte độc lập, decoder của lần thứ nhất nhìn thấy một chuỗi UTF-8 chưa hoàn chỉnh ở cuối mảng. Nó không thể biết rằng byte `AC` sẽ đến sau. Khi tạo một `String` mới từ mỗi mảng, byte lỗi thường bị thay bằng ký tự thay thế `�`; lần đọc sau bắt đầu bằng byte continuation nên cũng có thể bị báo lỗi.

Đây là lỗi phổ biến trong xử lý dữ liệu streaming: **một chunk byte không nhất thiết là một chuỗi UTF-8 hoàn chỉnh**.

### Ví dụ cách làm sai

~~~java
String first = new String(firstChunk, StandardCharsets.UTF_8);
String second = new String(secondChunk, StandardCharsets.UTF_8);
String text = first + second;
~~~

Mỗi lời gọi tạo `String` giải mã chunk như dữ liệu độc lập. Nếu `firstChunk` kết thúc giữa một ký tự nhiều byte, thông tin về phần byte chưa hoàn chỉnh không được mang sang lần giải mã thứ hai.

Không dùng cách này để giải mã các chunk liên tiếp của cùng một luồng UTF-8.

## 3. CharsetDecoder có trạng thái và hợp đồng input/output

Tạo decoder UTF-8 bằng:

~~~java
CharsetDecoder decoder = StandardCharsets.UTF_8.newDecoder();
~~~

`CharsetDecoder` là một bộ giải mã có trạng thái. Luồng xử lý chuẩn có các giai đoạn:

1. **Reset:** decoder sẵn sàng nhận dữ liệu mới.
2. **Decode:** gọi `decode(input, output, false)` cho các khối dữ liệu tiếp theo.
3. **End of input:** khi nguồn đã kết thúc, gọi `decode(input, output, true)`.
4. **Flush:** gọi `flush(output)` để hoàn tất quá trình chuyển đổi.
5. **Flushed:** decoder đã hoàn tất; muốn tái sử dụng phải `reset()` trước khi bắt đầu luồng mới.

Phương thức tăng dần có dạng:

~~~java
CoderResult result = decoder.decode(input, output, endOfInput);
~~~

Trong đó:

- `input` là `ByteBuffer` chứa byte UTF-8.
- `output` là `CharBuffer` nhận các UTF-16 code unit đã giải mã.
- `endOfInput` là `false` nếu còn dữ liệu sẽ đến; là `true` khi không còn byte nào nữa.
- Kết quả là `CoderResult` cho biết giải mã đã hết dữ liệu hiện tại, hết chỗ ghi hoặc gặp lỗi.

### Decoder không tự giữ các byte chưa hoàn chỉnh trong buffer nội bộ

Đây là điểm quan trọng nhất của bài học. Khi `decode(..., false)` trả về `UNDERFLOW` vì cuối input đang có một chuỗi byte chưa đủ, decoder **không tiêu thụ các byte đó**. Chúng vẫn nằm trong `ByteBuffer` từ vị trí hiện tại đến `limit`.

Ứng dụng phải giữ phần còn lại đó, thêm byte mới vào sau, rồi gọi decode tiếp. Cách phổ biến là `input.compact()`.

Với UTF-8, một ký tự cần tối đa bốn byte. Vì vậy, ở ranh giới chunk hợp lệ, tối đa ba byte đầu của một ký tự có thể còn chờ byte tiếp theo.

## 4. Hiểu UNDERFLOW, OVERFLOW và lỗi

`CoderResult` có ba trạng thái cần xử lý:

| Kết quả | Ý nghĩa | Hành động |
| --- | --- | --- |
| `UNDERFLOW` | Decoder đã xử lý hết phần input có thể xử lý lúc này; có thể còn một chuỗi byte chưa hoàn chỉnh ở cuối khi `endOfInput=false`. | Giữ các byte còn lại và chờ dữ liệu tiếp theo. |
| `OVERFLOW` | Output buffer không còn đủ chỗ để ghi thêm ký tự. | Đọc/xử lý output, làm rỗng buffer rồi gọi decode tiếp với input còn lại. |
| Error | Dữ liệu không hợp lệ hoặc không thể ánh xạ theo charset. | Chọn chính sách lỗi và xử lý, ví dụ `throwException()`. |

### UNDERFLOW không đồng nghĩa với lỗi

Nếu chunk kết thúc sau byte `E2 82` của ký tự `€` và `endOfInput=false`, đây là tình huống bình thường. Decoder trả về `UNDERFLOW` và để hai byte đó trong input buffer.

Khi byte `AC` đến, ứng dụng nối nó sau hai byte còn lại. Decoder lúc này có đủ `E2 82 AC` để tạo ký tự `€`.

### OVERFLOW không có nghĩa là input sai

Output buffer có thể nhỏ hơn lượng ký tự cần sinh ra. Decoder dừng với `OVERFLOW`, giữ input chưa tiêu thụ để ứng dụng lấy output ra và tiếp tục. Không được bỏ input hoặc tạo decoder mới chỉ vì gặp overflow.

### Error cần có chính sách rõ ràng

Có thể cấu hình hành vi với `CodingErrorAction`:

- `REPORT`: trả về lỗi để ứng dụng phát hiện và quyết định xử lý. Phù hợp khi dữ liệu phải chính xác.
- `REPLACE`: thay chuỗi byte lỗi bằng ký tự thay thế.
- `IGNORE`: bỏ qua dữ liệu lỗi.

Ví dụ cấu hình nghiêm ngặt:

~~~java
CharsetDecoder decoder = StandardCharsets.UTF_8.newDecoder()
        .onMalformedInput(CodingErrorAction.REPORT)
        .onUnmappableCharacter(CodingErrorAction.REPORT);
~~~

Với UTF-8, mọi Unicode scalar value hợp lệ đều có biểu diễn trong charset này; tình huống thường cần quan tâm là chuỗi byte sai định dạng hoặc bị cắt cụt. Dùng `REPORT` giúp không âm thầm biến dữ liệu hỏng thành văn bản khác.

## 5. Vòng đời của ByteBuffer: flip, compact và clear

Một `ByteBuffer` có ba thuộc tính trạng thái cần theo dõi:

- `capacity`: số byte tối đa buffer có thể chứa.
- `position`: vị trí đọc/ghi tiếp theo.
- `limit`: ranh giới mà thao tác đọc/ghi không được vượt qua.

Trong ví dụ streaming, input buffer luân phiên giữa hai chế độ.

~~~mermaid
flowchart TD
    A[Write mode: nhận byte mới] --> B[flip: chuyển sang read mode]
    B --> C[decode: xử lý byte hoàn chỉnh]
    C --> D[compact: giữ byte chưa tiêu thụ]
    D --> E[Đọc thêm byte vào phần trống]
    E --> B
~~~

Sau `flip()`, `limit` bằng vị trí ghi trước đó và `position` về 0. Sau `compact()`, byte còn lại được dồn về đầu buffer, `position` đặt ngay sau phần còn lại và `limit` trở lại bằng `capacity`.

Vai trò của các thao tác:

- `flip()`: kết thúc ghi và chuẩn bị đọc.
- `compact()`: giữ các byte chưa được tiêu thụ, dồn chúng về đầu buffer và chuẩn bị ghi tiếp.
- `clear()`: bỏ dữ liệu đã có về mặt logic, đặt buffer về write mode. Dùng cho output sau khi đã lấy hết ký tự; **không dùng clear trên input khi còn byte chưa hoàn chỉnh**.

`CharBuffer` output cũng thường dùng `flip()` để đọc các ký tự vừa sinh ra, rồi `clear()` để nhận output tiếp theo.

## 6. Ví dụ hoàn chỉnh: giải mã InputStream theo từng chunk

Phương thức sau đọc một `InputStream` bằng các mảng byte có kích thước cố định. Mỗi lần `read()` có thể kết thúc ở bất kỳ vị trí nào, kể cả giữa một ký tự UTF-8.

~~~java
import java.io.IOException;
import java.io.InputStream;
import java.nio.ByteBuffer;
import java.nio.CharBuffer;
import java.nio.charset.CharsetDecoder;
import java.nio.charset.CoderResult;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;

public final class Utf8StreamDecoder {
    private static final int CHUNK_SIZE = 4096;

    private Utf8StreamDecoder() {
    }

    public static String decode(InputStream source) throws IOException {
        CharsetDecoder decoder = StandardCharsets.UTF_8.newDecoder()
                .onMalformedInput(CodingErrorAction.REPORT)
                .onUnmappableCharacter(CodingErrorAction.REPORT);

        byte[] chunk = new byte[CHUNK_SIZE];

        // UTF-8 có thể để lại tối đa 3 byte chưa hoàn chỉnh giữa hai lần đọc.
        ByteBuffer input = ByteBuffer.allocate(CHUNK_SIZE + 4);
        CharBuffer output = CharBuffer.allocate(CHUNK_SIZE);
        StringBuilder decoded = new StringBuilder();

        int count;
        while ((count = source.read(chunk)) != -1) {
            input.put(chunk, 0, count);
            input.flip();

            decodeAvailable(decoder, input, output, decoded, false);

            // Giữ lại byte chưa được decoder tiêu thụ để nối với lần đọc sau.
            input.compact();
        }

        // EOF: báo cho decoder biết không còn byte nào sẽ đến.
        input.flip();
        decodeAvailable(decoder, input, output, decoded, true);

        // Chỉ flush sau khi decode với endOfInput=true đã hoàn tất.
        while (true) {
            CoderResult result = decoder.flush(output);
            output.flip();
            decoded.append(output);
            output.clear();

            if (result.isOverflow()) {
                continue;
            }
            if (result.isError()) {
                result.throwException();
            }
            break; // UNDERFLOW: flush hoàn tất.
        }

        return decoded.toString();
    }

    private static void decodeAvailable(
            CharsetDecoder decoder,
            ByteBuffer input,
            CharBuffer output,
            StringBuilder decoded,
            boolean endOfInput) throws IOException {

        while (true) {
            CoderResult result = decoder.decode(input, output, endOfInput);

            output.flip();
            decoded.append(output);
            output.clear();

            if (result.isOverflow()) {
                continue; // Output đã được lấy; tiếp tục với input còn lại.
            }
            if (result.isError()) {
                result.throwException();
            }
            break; // UNDERFLOW: chờ chunk tiếp theo hoặc kết thúc input.
        }
    }
}
~~~

Sử dụng với tệp:

~~~java
Path path = Path.of("message.txt");

try (InputStream input = Files.newInputStream(path)) {
    String text = Utf8StreamDecoder.decode(input);
    System.out.println(text);
}
~~~

Cần thêm import `java.nio.file.Files` và `java.nio.file.Path` cho đoạn sử dụng. Phương thức `decode` không đóng stream do bên gọi sở hữu tài nguyên; ví dụ `try-with-resources` chịu trách nhiệm đóng nó.

Phương thức mẫu trả về toàn bộ nội dung dưới dạng `String`, vì vậy bộ nhớ tăng theo kích thước văn bản. Với luồng rất lớn, thay `StringBuilder` bằng một `Writer` hoặc consumer xử lý từng phần output ngay sau mỗi lần decode; nguyên tắc giữ byte chưa hoàn chỉnh và vòng đời decoder không thay đổi.

### Vì sao buffer có kích thước CHUNK_SIZE + 4?

Mỗi lần đọc lấy tối đa `CHUNK_SIZE` byte. Sau lần decode, nếu UTF-8 kết thúc giữa một code point, tối đa ba byte đầu có thể còn lại. Buffer cần đủ chỗ cho phần còn lại đó cộng với chunk tiếp theo. Dùng thêm bốn byte tạo một khoảng dự phòng nhỏ và bảo đảm thao tác `put` không tràn buffer.

### Vì sao phải lặp khi OVERFLOW?

`decodeAvailable` luôn lấy các ký tự đã sinh ra khỏi output trước khi kiểm tra kết quả. Nếu kết quả là `OVERFLOW`, input có thể vẫn còn byte chưa xử lý. Vòng lặp gọi decode tiếp với cùng input và output đã được làm rỗng.

Nếu kết quả là `UNDERFLOW`, vòng lặp dừng. Khi `endOfInput=false`, input có thể còn byte chưa hoàn chỉnh; lệnh `compact()` ngay sau đó giữ chúng cho lần đọc tiếp theo.

### Vì sao cần flush?

`decode(input, output, true)` báo rằng đây là lần gọi cuối với dữ liệu nguồn. Sau khi decode hoàn tất, `flush(output)` cho decoder cơ hội phát ra phần output còn được giữ trong trạng thái chuyển đổi. Đây là bước cuối của hợp đồng `CharsetDecoder` và phải thực hiện trước khi bỏ decoder.

## 7. Minh họa ký tự bị chia qua hai lần đọc

Giả sử luồng chứa ký tự `A€B` với byte UTF-8:

~~~text
41 E2 82 AC 42
~~~

Nguồn đọc trả về hai chunk:

~~~text
Chunk 1: 41 E2 82
Chunk 2: AC 42
~~~

Tiến trình:

| Bước | Input sau flip | Kết quả decode | Byte còn lại |
| --- | --- | --- | --- |
| Đọc chunk 1 | `41 E2 82` | Sinh `A`, trả `UNDERFLOW` | `E2 82` |
| compact | Dồn `E2 82` về đầu | Chuyển sang write mode | `E2 82` |
| Đọc chunk 2 | `E2 82 AC 42` | Sinh `€B`, trả `UNDERFLOW` | Không còn |
| EOF | Input rỗng, `endOfInput=true` | Không còn byte để giải mã | Không còn |
| flush | Output cuối cùng | Hoàn tất decoder | Không còn |

Kết quả ghép từ các lần output là:

~~~text
A€B
~~~

Không có ký tự thay thế `�` vì decoder đã nhận đủ ba byte trước khi phải kết thúc luồng.

## 8. EOF và chuỗi UTF-8 bị cắt cụt

Cần phân biệt hai tình huống:

**Chunk tạm thời kết thúc giữa ký tự:** nguồn chưa kết thúc, vì vậy gọi `decode(..., false)`. Decoder trả `UNDERFLOW` và để byte chưa đủ trong input. Đây là tình huống bình thường.

**Toàn bộ luồng kết thúc giữa ký tự:** không còn byte nào sẽ đến, vì vậy gọi `decode(..., true)`. Chuỗi byte còn thiếu lúc này là dữ liệu UTF-8 malformed. Với chính sách `REPORT`, decoder trả lỗi và `throwException()` ném `MalformedInputException`.

Ví dụ ký tự `€` cần ba byte, nhưng luồng chỉ có:

~~~text
E2 82
~~~

Nếu còn dữ liệu trong tương lai, giữ lại hai byte. Nếu đã EOF, hai byte đó không thể tạo thành một ký tự hợp lệ.

### Chọn chính sách lỗi theo yêu cầu dữ liệu

| Chính sách | Hành vi khi EOF giữa ký tự | Khi phù hợp |
| --- | --- | --- |
| `REPORT` | Báo `MalformedInputException`. | Dữ liệu cấu hình, giao thức, log cần phát hiện hỏng hoặc bị cắt cụt. |
| `REPLACE` | Ghi ký tự thay thế cho chuỗi byte lỗi. | Nội dung hiển thị không quan trọng việc bảo toàn tuyệt đối. |
| `IGNORE` | Bỏ qua chuỗi byte lỗi. | Chỉ dùng khi việc mất dữ liệu được chấp nhận rõ ràng. |

Không nên dùng `REPLACE` để che giấu lỗi truyền tải nếu ứng dụng cần bảo đảm dữ liệu chính xác. Nếu giao thức có checksum hoặc length prefix, hãy kiểm tra chúng cùng với lỗi giải mã.

## 9. Các lỗi triển khai thường gặp

| Cách làm sai | Hậu quả | Cách làm đúng |
| --- | --- | --- |
| Tạo `new String(chunk, UTF_8)` cho từng lần đọc. | Ký tự bị chia có thể thành `�` hoặc mất dữ liệu. | Dùng một `CharsetDecoder` cho toàn luồng. |
| Gọi `decoder.decode(input)` cho mỗi chunk. | Overload tiện ích xử lý input như một chuỗi hoàn chỉnh, reset và kết thúc decoder. | Dùng `decode(input, output, false)` trong lúc đọc. |
| Gọi `input.clear()` sau UNDERFLOW. | Xóa byte đầu của ký tự chưa hoàn chỉnh. | Gọi `input.compact()` để giữ byte còn lại. |
| Không xử lý OVERFLOW. | Mất output hoặc bỏ dở input còn lại. | Lấy output ra, clear output và gọi decode tiếp. |
| Luôn truyền `endOfInput=true` cho mỗi chunk. | Chunk tạm thời bị xem như toàn bộ luồng; sequence chia đôi bị báo malformed. | Chỉ truyền true khi nguồn thật sự kết thúc. |
| Không gọi `flush()` sau decode cuối. | Không hoàn tất đúng vòng đời decoder. | Decode với true đến UNDERFLOW rồi flush đến UNDERFLOW. |
| Gọi decode tiếp sau khi đã end-of-input và flush. | Vi phạm trạng thái decoder. | Tạo decoder mới hoặc gọi reset trước luồng mới. |
| Dùng chung một decoder cho nhiều luồng đồng thời. | Trạng thái giải mã bị trộn; CharsetDecoder không thread-safe. | Mỗi luồng có decoder và buffer riêng. |

## 10. Tích hợp với NIO và giao thức streaming

Ví dụ `InputStream` phía trên phù hợp cho nguồn blocking. Với NIO, cùng nguyên tắc áp dụng khi đọc từ `FileChannel` hoặc `SocketChannel`:

1. Đọc byte vào `ByteBuffer` ở write mode.
2. `flip()` để decoder đọc.
3. Gọi `decode(input, output, false)` trong khi nguồn còn mở.
4. Xử lý output và lặp nếu `OVERFLOW`.
5. `compact()` để giữ byte chưa hoàn chỉnh.
6. Khi kênh báo EOF, gọi decode với `endOfInput=true`.
7. Flush decoder sau khi decode cuối hoàn tất.

Với `SocketChannel` non-blocking, `read()` có thể trả về 0 khi hiện chưa có byte. Khi đó không nên busy-loop; quay lại selector/event loop và chỉ đọc tiếp khi kênh sẵn sàng. Việc quản lý byte UTF-8 chưa hoàn chỉnh vẫn dùng `compact()` như trên.

### Không gắn decoder với một lần read của socket

Một lần `SocketChannel.read()` chỉ phản ánh số byte hiện có trong lần đọc đó. TCP là luồng byte, không bảo toàn ranh giới message hoặc ký tự. Nếu giao thức cần biết message kết thúc ở đâu, ứng dụng phải dùng framing riêng như length prefix, delimiter hoặc cấu trúc protocol. UTF-8 decoder chỉ giải quyết chuyển đổi byte thành ký tự, không xác định ranh giới message.

### Mỗi stream có một decoder riêng

`CharsetDecoder` có trạng thái nội bộ và không an toàn khi nhiều thread cùng gọi. Hãy sở hữu decoder trong đối tượng xử lý một stream/session, hoặc tạo decoder cục bộ cho mỗi thao tác. Không dùng singleton decoder dùng chung cho các kết nối đồng thời.

## 11. Bài tập thực hành

### Bài tập 1: Dự đoán UNDERFLOW

Một chunk kết thúc bằng hai byte `E2 82`. Với UTF-8 và `endOfInput=false`, decoder trả kết quả nào? Hai byte đó nằm ở đâu sau khi decode? Vì sao không được gọi `clear()` trên input?

### Bài tập 2: Theo dõi buffer

Cho input buffer có capacity 8, sau khi ghi nhận `41 E2 82` thì gọi `flip()` và decode. Decoder tiêu thụ `41` nhưng giữ `E2 82`. Hãy ghi lại `position` và `limit` trước và sau `compact()`. Sau đó cho biết byte mới phải được ghi từ vị trí nào.

### Bài tập 3: Phân biệt EOF tạm thời và EOF thật

Với hai chunk `E2 82` rồi `AC`, giải thích vì sao lần đầu phải dùng `endOfInput=false`. Điều gì xảy ra nếu lần đầu dùng true? Khi nào mới được gọi `flush()`?

### Bài tập 4: Kiểm thử chuỗi bị cắt cụt

Tạo một luồng chỉ chứa `E2 82` rồi kết thúc. Cấu hình `CodingErrorAction.REPORT` và gọi decode cuối với `endOfInput=true`. Xác định exception được ném. Lặp lại với `REPLACE` và quan sát ký tự thay thế.

### Bài tập 5: Xử lý OVERFLOW

Giảm output buffer xuống hai ký tự, nhưng cung cấp một chunk chứa nhiều ký tự ASCII. Theo dõi số lần `decode()` được gọi và giải thích vì sao input phải được giữ nguyên giữa các lần OVERFLOW.

### Bài tập 6: So sánh cách giải mã

Giải mã byte của `A€B` theo hai chunk `41 E2 82` và `AC 42`. So sánh kết quả của hai cách: tạo `String` riêng cho từng chunk và dùng một `CharsetDecoder` cùng input buffer được compact. Giải thích vì sao chỉ cách thứ hai bảo toàn ký tự.

**Tự kiểm:** dùng một decoder cho toàn stream; giữ byte chưa tiêu thụ sau UNDERFLOW; lặp khi OVERFLOW; chỉ kết thúc khi EOF thật; flush đúng thứ tự; xử lý malformed input theo chính sách rõ ràng.

## 12. Ghi nhớ

- **UTF-8 code point có thể cần từ 1 đến 4 byte.** Ranh giới lần đọc không bảo đảm trùng ranh giới ký tự.
- **Không giải mã từng chunk độc lập.** Một chunk có thể kết thúc giữa sequence nhiều byte và bị thay bằng ký tự lỗi.
- **Dùng một `CharsetDecoder` cho toàn luồng.** Gọi `decode(input, output, false)` cho đến khi nguồn kết thúc.
- **UNDERFLOW yêu cầu giữ input còn lại.** Dùng `compact()` để dồn byte chưa hoàn chỉnh về đầu buffer trước khi đọc tiếp.
- **OVERFLOW yêu cầu lấy output ra và decode tiếp.** Không bỏ input chưa tiêu thụ.
- **Chỉ truyền `endOfInput=true` khi đã EOF thật.** Chuỗi byte còn thiếu ở cuối luồng sẽ trở thành malformed input.
- **Gọi `flush()` sau lần decode cuối.** Hoàn tất vòng đời decoder trước khi bỏ hoặc reset nó.
- **Chọn `REPORT`, `REPLACE` hoặc `IGNORE` có chủ đích.** Dữ liệu cần toàn vẹn nên ưu tiên phát hiện lỗi thay vì âm thầm bỏ hoặc thay byte.
- **Javadoc, compiler và decoder có nhiệm vụ riêng.** Hãy kiểm thử luồng dữ liệu thực tế bằng test chia chunk ở nhiều vị trí, đặc biệt giữa các byte UTF-8.

## Tài liệu chính thống

- [Oracle – Java SE 26 API: CharsetDecoder](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/nio/charset/CharsetDecoder.html).
- [Oracle – Java SE 26 API: CoderResult](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/nio/charset/CoderResult.html).
- [Oracle – Java SE 26 API: ByteBuffer](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/nio/ByteBuffer.html).
- [Oracle – Java SE 26 API: StandardCharsets](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/nio/charset/StandardCharsets.html).
- [The Unicode Standard – UTF-8 encoding form](https://www.unicode.org/versions/latest/core-spec/chapter-3/).

