# Giải mã nhiều khối khi ký tự bị chia giữa hai lần đọc trong Java I/O

## 1. Vấn đề: ranh giới khối byte không phải ranh giới ký tự

Khi đọc văn bản từ tệp, socket hoặc một `InputStream`, dữ liệu đến dưới dạng **byte**. Một lần gọi `read(byte[])` chỉ trả về một đoạn byte tại thời điểm đó; đoạn này không nhất thiết kết thúc đúng cuối một ký tự theo bảng mã. Ví dụ trong UTF-8, một ký tự Unicode có thể được mã hóa thành **1–4 byte**. Nếu một lần đọc dừng giữa các byte của ký tự, việc giải mã từng khối độc lập có thể tạo ký tự thay thế `�` hoặc báo lỗi sai.

Ví dụ ký tự `€` (U+20AC) trong UTF-8:

~~~text
Văn bản gốc:               €
Các byte UTF-8 (hex):      E2 82 AC

Lần đọc 1:                 E2 82       ← chưa đủ ký tự
Lần đọc 2:                       AC    ← hoàn tất ký tự

Đúng:   giữ E2 82, nối AC, giải mã → €
Sai:    giải mã E2 82 riêng, rồi AC riêng → chuỗi không còn là €
~~~

Một trường hợp tương tự: emoji `😀` (U+1F600) có chuỗi UTF-8 `F0 9F 98 80`. Bất kỳ ranh giới đọc nào nằm giữa bốn byte này đều cần giữ trạng thái giải mã. Trong Java, emoji đó còn được biểu diễn thành **hai đơn vị `char` (cặp surrogate)** sau khi giải mã thành UTF-16.

Bài học tập trung vào **giải mã tăng dần (incremental decoding)**: xử lý nhiều khối byte liên tiếp như **một dòng văn bản liên tục**, giữ dữ liệu chưa hoàn chỉnh giữa các lần đọc, nhận biết EOF thật, và phát tín hiệu lỗi chính xác.

Kết quả cần đạt:

- Giải thích tại sao không nên tạo `new String(chunk, charset)` riêng cho mỗi khối byte của cùng một dòng dữ liệu.
- Hiểu cách `InputStreamReader` giữ trạng thái giúp ứng dụng đọc ký tự thông thường.
- Tự dùng `CharsetDecoder` với `ByteBuffer` và `CharBuffer` khi cần kiểm soát quá trình giải mã nhiều khối.
- Phân biệt `CoderResult.UNDERFLOW`, `OVERFLOW`, đầu vào lỗi và EOF; đặt `endOfInput` và gọi `flush()` đúng vòng đời.
- Thử được các ranh giới byte bất kỳ, bao gồm ranh giới cắt giữa ký tự tiếng Việt và emoji.

## 2. Ba lớp dữ liệu: byte, code point và char

Trước khi viết vòng lặp, cần tách ba khái niệm:

| Khái niệm | Ví dụ | Vai trò |
| --- | --- | --- |
| Byte | `E2`, `82`, `AC` | Đơn vị dữ liệu thô mà I/O từ tệp hoặc mạng truyền đi |
| Unicode code point | `U+20AC` của `€` | Giá trị trừu tượng đại diện cho một ký tự Unicode |
| Đơn vị mã UTF-16 (`char`) | `'\u20AC'` hoặc một nửa cặp surrogate | Cách nhiều API ký tự Java biểu diễn văn bản |

Trong UTF-8, ASCII như `A` dùng 1 byte; `€` dùng 3 byte; `😀` dùng 4 byte. Sau giải mã, `€` là một `char`, còn `😀` cần hai `char`. Vì vậy:

- **Số byte đọc không bằng số ký tự Java nhận được.**
- **Số `char` không phải lúc nào cũng bằng số code point.**
- **Số byte của một lần đọc không quyết định số ký tự có thể xuất ra ngay.**

Một bộ giải mã đang chờ byte cuối của ký tự có thể **chưa xuất bất kỳ `char` nào**, dù ứng dụng vừa nạp thêm byte. Điều này là bình thường; không nên tự chèn ký tự rỗng hoặc ký tự thay thế chỉ vì khối hiện tại chưa tạo ra output.

## 3. Tại sao giải mã từng mảng byte bằng new String là sai?

Đoạn mã sau minh họa lỗi thường gặp:

~~~java
StringBuilder result = new StringBuilder();
byte[] buffer = new byte[2];
int count;

while ((count = input.read(buffer)) != -1) {
    result.append(new String(buffer, 0, count, StandardCharsets.UTF_8));
}
~~~

**Đây là đoạn minh họa không độc lập:** `input` là `InputStream` đã được mở; cần có import tương ứng và đóng stream ở bên sở hữu. Lỗi nằm ở chỗ **mỗi lần gọi constructor của `String` khởi tạo một quá trình giải mã độc lập**. Nếu dữ liệu UTF-8 bị chia giữa hai `read`, bộ giải mã của lần trước không còn cơ hội nhận các byte tiếp theo.

Ví dụ chính xác hơn, xem một chuỗi chỉ có ký tự `€` được tách thành hai mảng: `{E2, 82}` và `{AC}`. Vì mỗi phần riêng lẻ là chuỗi UTF-8 không hợp lệ, API `new String(byte[], UTF_8)` thường áp dụng chính sách **thay dữ liệu không hợp lệ** thay vì ghép hai phần thành `€`. Việc mỗi phần được giải mã không ném ngoại lệ không chứng minh văn bản còn đúng.

Không giải quyết lỗi bằng cách chọn buffer 4096 hoặc 8192 byte: buffer lớn hơn làm **giảm khả năng gặp** ranh giới chia ký tự trên dữ liệu thông thường, nhưng không loại bỏ được nó. Bất kỳ kích thước khối hữu hạn nào vẫn có thể cắt giữa một chuỗi UTF-8 dài nhiều byte.

Có hai hướng đúng:

1. **Dùng lớp Reader để đọc ký tự đã được giải mã**: phù hợp phần lớn chương trình chỉ cần văn bản.
2. **Giữ một `CharsetDecoder` trong suốt dòng dữ liệu**: phù hợp khi tự điều khiển xử lý ByteBuffer/CharBuffer, đọc bất đồng bộ, xử lý khung dữ liệu hoặc cần chính sách báo lỗi rõ ràng.

## 4. Cách đơn giản: để InputStreamReader giữ trạng thái giải mã

`InputStreamReader` là cầu nối giữa `InputStream` (byte) và `Reader` (ký tự). Lớp này giữ trạng thái giải mã qua nhiều lần đọc byte bên dưới. Người gọi chỉ nhận các đơn vị `char` sau khi thư viện có đủ byte.

~~~java
try (Reader reader = new InputStreamReader(
        input, StandardCharsets.UTF_8)) {
    char[] chars = new char[1024];
    int count;

    while ((count = reader.read(chars)) != -1) {
        // Xử lý đúng chars[0] đến chars[count - 1].
    }
}
~~~

Đoạn minh họa yêu cầu `import java.io.Reader`, `import java.io.InputStreamReader` và `import java.nio.charset.StandardCharsets`, cùng biến `InputStream input` đã được cấp. `try-with-resources` đóng Reader và do đó đóng InputStream bên dưới; chỉ dùng cách này khi đoạn mã **sở hữu** InputStream hoặc được trao quyền đóng.

Dù Reader giải quyết việc UTF-8 bị chia giữa các lần đọc byte, chính Reader vẫn có thể trả từng khối `char[]` cắt giữa **hai đơn vị surrogate** của một code point Unicode. Nếu chỉ ghi nguyên trạng từng khối với `Writer.write(chars, 0, count)` trong cùng một dòng văn bản, cách này phù hợp; nếu xử lý từng khối như chuỗi ký tự độc lập để đảo ngược, lọc hoặc phân tích code point, cần xem xét ranh giới UTF-16.

### 4.1. Ví dụ chạy độc lập với nguồn cung cấp từng byte

Tệp **ReaderAcrossChunksDemo.java**:

~~~java
import java.io.ByteArrayInputStream;
import java.io.InputStreamReader;
import java.io.Reader;
import java.nio.charset.StandardCharsets;

public class ReaderAcrossChunksDemo {
    public static void main(String[] args) throws Exception {
        String original = "A€😀B";
        byte[] bytes = original.getBytes(StandardCharsets.UTF_8);

        try (Reader reader = new InputStreamReader(
                new ByteArrayInputStream(bytes), StandardCharsets.UTF_8)) {
            StringBuilder restored = new StringBuilder();
            char[] buffer = new char[2];
            int count;

            while ((count = reader.read(buffer)) != -1) {
                restored.append(buffer, 0, count);
            }

            System.out.println("UTF-8 bytes: " + bytes.length);
            System.out.println("UTF-16 units: " + restored.length());
            System.out.println("Restored: " + restored);
            System.out.println("Matches: " + original.contentEquals(restored));
        }
    }
}
~~~

Chạy với Java 17+:

~~~bash
javac -encoding UTF-8 ReaderAcrossChunksDemo.java
java ReaderAcrossChunksDemo
~~~

Kết quả:

~~~text
UTF-8 bytes: 9
UTF-16 units: 5
Restored: A€😀B
Matches: true
~~~

`ByteArrayInputStream` trong ví dụ đã có toàn bộ byte trong RAM; Reader có quyền gom byte theo nhu cầu nên lần gọi `read(char[])` không nhất thiết trùng với từng đơn vị byte. Tuy nhiên, kết quả minh họa quy tắc quan trọng: **thông qua cùng một Reader, dữ liệu UTF-8 được giải mã liên tục, không tạo decoder mới cho từng lần đọc**.

Khi phải quan sát/chủ động cấp **chính xác từng mảnh byte**, cần ví dụ `CharsetDecoder` ở phần tiếp theo.

## 5. CharsetDecoder: trạng thái giải mã được giữ ở đâu?

`java.nio.charset.CharsetDecoder` là đối tượng có trạng thái, dùng để biến byte thành các đơn vị UTF-16 của Java. Tạo một decoder duy nhất cho **một dòng dữ liệu liên tục**:

~~~java
CharsetDecoder decoder = StandardCharsets.UTF_8.newDecoder()
        .onMalformedInput(CodingErrorAction.REPORT)
        .onUnmappableCharacter(CodingErrorAction.REPORT);
~~~

Các import cần thiết: `java.nio.charset.CharsetDecoder`, `CodingErrorAction` và `StandardCharsets`. Đây là đoạn minh họa, chưa phải chương trình độc lập.

Khi xử lý đầu vào theo nhiều khối, đối tượng quan trọng là:

- `ByteBuffer input`: giữ những byte hiện có, **bao gồm phần chưa đủ để tạo ký tự**.
- `CharBuffer output`: nơi decoder đặt các đơn vị `char` đã giải mã.
- `CharsetDecoder decoder`: giữ trạng thái của quá trình giải mã, bao gồm các quy tắc của charset và tình trạng cuối luồng.
- `CoderResult result`: báo trạng thái decoder sau một lần xử lý.

Với `CharsetDecoder.decode(input, output, endOfInput)`:

| Kết quả | Ý nghĩa | Cách xử lý |
| --- | --- | --- |
| `UNDERFLOW` | Không thể tạo thêm đầu ra với lượng byte đang có; có thể vì thiếu byte để hoàn thành ký tự hoặc đã tiêu thụ hết | Giữ byte còn lại, nạp thêm; nếu là cuối luồng thì chuẩn bị flush |
| `OVERFLOW` | CharBuffer không đủ chỗ để tạo thêm đầu ra | Đưa các ký tự đã tạo cho nơi tiêu thụ, xóa/trống CharBuffer rồi gọi decode tiếp |
| `isMalformed()` | Chuỗi byte không hợp lệ theo charset | Xử lý theo chính sách lỗi; nếu REPORT thì ném ngoại lệ |
| `isUnmappable()` | Dữ liệu không ánh xạ được thành đầu ra theo charset | Xử lý theo chính sách lỗi; không được tự hiểu là EOF |

**Chú ý:** `UNDERFLOW` không nhất thiết có nghĩa “hết toàn bộ dữ liệu”. Khi `endOfInput=false`, nó có thể chỉ báo rằng decoder đang cần những byte tiếp theo. Đừng kết thúc xử lý toàn bộ nguồn mỗi khi nhìn thấy `UNDERFLOW`.

### 5.1. Chọn chính sách lỗi

Có ba lựa chọn tiêu biểu cho chuỗi byte lỗi:

- `CodingErrorAction.REPORT`: để `CoderResult` báo lỗi (hoặc ném `CharacterCodingException` khi dùng `throwException()`). Phù hợp khi dữ liệu cần chính xác tuyệt đối.
- `CodingErrorAction.REPLACE`: dùng chuỗi thay thế do decoder quy định (thường thấy `�` với UTF-8). Phù hợp khi ưu tiên hiển thị dữ liệu có thể phục hồi.
- `CodingErrorAction.IGNORE`: bỏ dữ liệu lỗi. Có nguy cơ mất dữ liệu một cách im lặng; chỉ dùng khi nghiệp vụ cho phép.

**Byte bị chia giữa hai lần đọc không phải lỗi.** Khi decoder nhận `endOfInput=false`, phần byte chưa hoàn chỉnh cần được giữ lại để thử với byte kế tiếp. Chỉ khi dòng thật sự kết thúc mà vẫn thiếu byte cần thiết thì chuỗi bị cụt mới trở thành đầu vào lỗi theo hợp đồng charset.

## 6. Vòng đời ByteBuffer: position, limit, flip và compact

`ByteBuffer` có ba chỉ số chính:

- `capacity`: dung lượng toàn bộ vùng chứa.
- `position`: vị trí đọc/ghi tiếp theo.
- `limit`: ranh giới hiện tại mà thao tác không được vượt qua.

Khi **ghi byte vào buffer**, buffer thường ở chế độ ghi: `position` tăng sau `put`, `limit` thường bằng `capacity`. Trước khi decoder **đọc từ buffer**, gọi `flip()` để đặt `limit = position` và `position = 0`.

~~~text
ByteBuffer đang ở chế độ đọc:

[ E2 ][ 82 ][  · ][  · ][  · ][  · ]
  ^position      ^limit          ^capacity
  Các byte E2 82 chưa đủ để tạo €

Decoder trả UNDERFLOW, position vẫn trỏ tới byte chưa tiêu thụ.
Gọi compact():
- đưa byte còn lại về đầu mảng
- đặt position sau số byte còn lại
- đưa limit về capacity để có chỗ nạp tiếp

Nạp AC, gọi flip():

[ E2 ][ 82 ][ AC ][  · ][  · ][  · ]
  ^position            ^limit

Decoder tiếp tục → €
~~~

Trong thuật toán đúng, **`compact()` rất quan trọng**: nó bảo toàn những byte decoder chưa tiêu thụ. Nếu dùng `clear()` sau `UNDERFLOW`, bạn sẽ bỏ các byte còn dở của ký tự; khi byte tiếp theo đến, phần còn lại không còn ghép được với phần trước.

Khác biệt cốt lõi:

| Thao tác | Thực hiện | Khi nào dùng |
| --- | --- | --- |
| `flip()` | Chuyển phần dữ liệu vừa ghi thành vùng có thể đọc | Sau khi nạp thêm byte trước khi decode |
| `compact()` | Giữ dữ liệu **chưa đọc** ở đầu buffer và mở chỗ ghi mới | Sau một lần decode trước khi nạp byte tiếp |
| `clear()` | Đặt position=0, limit=capacity, không xóa nội dung vật lý | Chỉ khi chắc chắn không còn byte cũ cần giữ |
| `remaining()` | Trả số phần tử giữa position và limit | Biết còn bao nhiêu byte để đọc/ghi |
| `hasRemaining()` | Kiểm tra còn phần tử hay không | Điều khiển vòng lặp; không tự nói lên EOF của nguồn |

`CharBuffer` cũng có `position`/`limit`. Sau mỗi `decode`, để đưa các ký tự đã tạo cho nơi tiêu thụ: gọi `output.flip()`, đọc các ký tự còn lại, rồi `output.clear()` để decoder có thể tạo thêm. **Không gọi `output.clear()` trước khi lấy dữ liệu đã giải mã**.

## 7. Thuật toán giải mã tăng dần

Một vòng lặp chuẩn cho một chuỗi byte liên tục gồm các bước sau:

1. Tạo **một** `CharsetDecoder` và cấu hình chính sách lỗi.
2. Tạo `ByteBuffer` đủ chỗ chứa chuỗi byte tối đa của charset và có khoảng trống để nạp thêm; tạo `CharBuffer` đủ chỗ cho đầu ra mà decoder có thể sinh khi gặp một ký tự.
3. Lấy một phần byte từ nguồn rồi nạp vào `ByteBuffer`. Dùng `compact()` trước khi nạp để giữ những byte chưa tiêu thụ; dùng `flip()` để decoder nhìn thấy toàn bộ byte hợp lệ.
4. Gọi `decode(input, output, false)` khi **vẫn có thể còn byte** từ nguồn. Với `OVERFLOW`, thu đầu ra rồi gọi lại. Với `UNDERFLOW`, giữ byte còn lại và chờ khối mới.
5. Khi **xác nhận nguồn thực sự EOF**, gọi `decode(input, output, true)` với các byte cuối cùng (có thể rỗng). Lúc này các byte dư không tạo thành ký tự hợp lệ sẽ được xử lý như dữ liệu cuối bị cụt theo chính sách lỗi.
6. Sau khi decode cuối trả `UNDERFLOW`, gọi `decoder.flush(output)`; xử lý `OVERFLOW` bằng cách thu output và gọi flush tiếp, cho đến `UNDERFLOW`.
7. Dùng `decoder.reset()` chỉ khi muốn sử dụng lại decoder cho **một dòng độc lập khác**, sau khi vòng đời hiện tại đã kết thúc đúng cách. Không reset giữa các khối của cùng một nguồn.

Đây là **máy trạng thái**. Gọi `flush()` trước khi `decode(..., true)` hoàn tất hoặc nạp thêm byte vào decoder đã kết thúc mà chưa reset là sai trình tự. Một `CharsetDecoder` không được coi là đối tượng an toàn để nhiều thread cùng thao tác vào trạng thái chia sẻ; mỗi luồng giải mã độc lập nên sở hữu decoder riêng hoặc đồng bộ theo thiết kế.

### 7.1. Lưu ý với ByteBuffer quá nhỏ

Nếu buffer đầu vào không đủ chứa một chuỗi byte cần thiết để decoder tiến triển, vòng lặp có thể mắc kẹt: `UNDERFLOW` giữ tất cả byte, nhưng `compact()` không để lại chỗ nạp thêm. Với UTF-8, một code point cần tối đa 4 byte; ví dụ dưới dùng buffer 8 byte. Khi thiết kế decoder tổng quát cho charset khác, cần bảo đảm dung lượng/bộ đệm phù hợp hoặc có cơ chế mở rộng.

Tương tự, `CharBuffer` phải có đủ chỗ cho một đơn vị đầu ra mà decoder cần sinh cùng lúc; emoji ngoài BMP có thể yêu cầu hai đơn vị `char`. Ví dụ dùng `CharBuffer.allocate(2)`. Nếu CharBuffer có dung lượng 1 và decoder cần phát cặp surrogate cùng lúc, thuật toán đơn giản có thể tiếp tục gặp `OVERFLOW` mà không tạo tiến triển.

## 8. Ví dụ đầy đủ Java 17: cố tình cắt UTF-8 thành các khối 2 byte

Ví dụ dưới tự cung cấp hai byte mỗi lượt, khiến ký tự `€` (3 byte) và `😀` (4 byte) bị chia giữa các lượt. Kết quả phải khớp **chính xác** chuỗi gốc. Ví dụ có xử lý `UNDERFLOW`, `OVERFLOW`, phần dư ByteBuffer và flush cuối.

Lưu vào **Utf8IncrementalDecoderDemo.java**:

~~~java
import java.nio.ByteBuffer;
import java.nio.CharBuffer;
import java.nio.charset.CharacterCodingException;
import java.nio.charset.CharsetDecoder;
import java.nio.charset.CoderResult;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;

public class Utf8IncrementalDecoderDemo {
    public static void main(String[] args) throws Exception {
        String original = "A€😀B";
        byte[] bytes = original.getBytes(StandardCharsets.UTF_8);
        String decoded = decodeInChunks(bytes, 2);

        System.out.println("UTF-8 bytes: " + bytes.length);
        System.out.println("UTF-16 units: " + decoded.length());
        System.out.println("Decoded: " + decoded);
        System.out.println("Matches: " + original.equals(decoded));
    }

    static String decodeInChunks(byte[] bytes, int chunkSize)
            throws CharacterCodingException {
        if (chunkSize <= 0) {
            throw new IllegalArgumentException("chunkSize must be positive");
        }

        CharsetDecoder decoder = StandardCharsets.UTF_8.newDecoder()
                .onMalformedInput(CodingErrorAction.REPORT)
                .onUnmappableCharacter(CodingErrorAction.REPORT);

        ByteBuffer input = ByteBuffer.allocate(8);
        CharBuffer output = CharBuffer.allocate(2);
        StringBuilder result = new StringBuilder();

        // Chế độ đọc với không byte nào đang chờ.
        input.limit(0);
        int next = 0;

        while (next < bytes.length) {
            // Giữ byte chưa tiêu thụ, mở chỗ cho dữ liệu mới.
            input.compact();
            int count = Math.min(
                    chunkSize, Math.min(input.remaining(), bytes.length - next));
            if (count == 0) {
                throw new IllegalStateException("Input buffer too small");
            }

            input.put(bytes, next, count);
            next += count;
            input.flip();

            boolean endOfInput = next == bytes.length;
            decodeAvailable(decoder, input, output, result, endOfInput);
        }

        // Trường hợp toàn bộ đầu vào rỗng vẫn phải kết thúc decoder.
        if (bytes.length == 0) {
            decodeAvailable(decoder, input, output, result, true);
        }

        // Chỉ flush sau khi lần decode cuối đã trả UNDERFLOW.
        while (true) {
            CoderResult status = decoder.flush(output);
            drain(output, result);

            if (status.isOverflow()) {
                continue;
            }
            if (status.isError()) {
                status.throwException();
            }
            if (status.isUnderflow()) {
                break;
            }
        }

        return result.toString();
    }

    private static void decodeAvailable(
            CharsetDecoder decoder, ByteBuffer input, CharBuffer output,
            StringBuilder result, boolean endOfInput)
            throws CharacterCodingException {
        while (true) {
            CoderResult status = decoder.decode(input, output, endOfInput);
            drain(output, result);

            if (status.isOverflow()) {
                // CharBuffer đã được thu và làm trống: thử decode tiếp.
                continue;
            }
            if (status.isError()) {
                status.throwException();
            }
            if (status.isUnderflow()) {
                // ByteBuffer có thể vẫn giữ đầu một ký tự chưa đủ byte.
                break;
            }
        }
    }

    private static void drain(CharBuffer output, StringBuilder result) {
        output.flip();
        result.append(output);
        output.clear();
    }
}
~~~

Biên dịch và chạy (JDK 17+):

~~~bash
javac -encoding UTF-8 Utf8IncrementalDecoderDemo.java
java Utf8IncrementalDecoderDemo
~~~

Kết quả mong đợi:

~~~text
UTF-8 bytes: 9
UTF-16 units: 5
Decoded: A€😀B
Matches: true
~~~

**Điểm then chốt trong ví dụ:**

- `bytes.length == 9` vì `A` chiếm 1 byte, `€` chiếm 3, `😀` chiếm 4, `B` chiếm 1.
- `decodeInChunks(bytes, 2)` cố tình nạp 2 byte mỗi lượt (lượt cuối có thể ngắn hơn). Một số lượt đọc chỉ cung cấp **mảnh đầu/mảnh cuối của cùng một ký tự**.
- `input.compact()` chuyển byte chưa giải mã sang đầu buffer; `input.put` nạp tiếp đúng đoạn của nguồn; `input.flip()` chuẩn bị cho decoder.
- `decodeAvailable` xử lý `OVERFLOW` và thu ký tự từ `CharBuffer` liên tục. Với `UNDERFLOW` chưa đến cuối luồng, nó trả quyền điều khiển để nạp thêm byte.
- `endOfInput` chỉ trở thành `true` sau khi **byte cuối của nguồn đã được cung cấp**. Không suy ra EOF từ một lần `UNDERFLOW`.
- `decoder.flush(output)` diễn ra sau lần decode cuối, bảo đảm toàn bộ trạng thái kết thúc đã được xử lý.
- `StringBuilder.append(output)` lấy các ký tự còn lại trong CharBuffer sau `flip()`; `clear()` chuẩn bị nơi chứa đầu ra mới.

Ví dụ phục vụ học cơ chế. Trong sản phẩm thực, cần kết hợp việc nạp byte từ `InputStream`/`ReadableByteChannel`, xử lý ngoại lệ I/O, hủy thao tác và vòng đời tài nguyên. Một byte source có thể kết thúc với `-1` (EOF), còn `0` nếu đọc qua channel không chặn có thể chỉ là chưa có byte lúc này. Hai trạng thái ấy **không được đánh đồng**.

## 9. Nếu byte đến từ InputStream hoặc Channel thực tế

### 9.1. InputStream.read(byte[])

Với `InputStream`, giá trị `read(buffer)` là:

- Số byte thực tế đã đọc.
- `-1` khi hết dữ liệu.
- Với mảng có độ dài 0, lời gọi có thể trả `0`; đừng dùng mảng rỗng làm bộ đệm vòng lặp.

Ví dụ đọc byte từ tệp theo từng lượt, sau đó có thể cấp phần byte đó vào **cùng decoder** hoặc đơn giản bọc `InputStreamReader`:

~~~java
try (var input = java.nio.file.Files.newInputStream(path);
     var reader = new java.io.InputStreamReader(
             input, java.nio.charset.StandardCharsets.UTF_8)) {
    char[] buffer = new char[2048];
    int count;
    while ((count = reader.read(buffer)) != -1) {
        // Xử lý từng phần ký tự đã giải mã.
    }
}
~~~

Đoạn này cần `Path path` và phương thức khai báo hoặc bắt `IOException`. Nó minh họa Reader giữ trạng thái dù InputStream bên dưới đọc byte theo nhiều lượt; không phải chương trình độc lập.

### 9.2. ReadableByteChannel và I/O không chặn

Một channel không chặn có thể trả về `0` khi **chưa có byte sẵn**, dù kết nối còn mở. Khi đó:

- Không gọi `decode(..., true)`.
- Không gọi `flush()` để “lấy nốt chữ”.
- Giữ byte còn lại và trạng thái decoder, đợi lượt đọc sau.
- Chỉ báo `endOfInput=true` khi giao thức/API xác nhận đã thực sự kết thúc phần dữ liệu cần giải mã.

Với giao thức mà mỗi thông điệp có độ dài riêng, ranh giới kết thúc một thông điệp không tự động là EOF của **toàn bộ kết nối**. Cần quyết định decoder tiếp tục trên cùng luồng ký tự hay mỗi thông điệp là một chuỗi byte độc lập (và phải dùng decoder riêng/reset đúng lúc). Không lấy “mỗi lần socket.read” làm ranh giới ký tự hoặc ranh giới thông điệp.

## 10. Phân biệt UNDERFLOW, OVERFLOW và lỗi: hai tình huống đối chiếu

**Tình huống A — UTF-8 hợp lệ bị chia thành nhiều khối:**

~~~text
Dòng byte:       E2 82 AC
Khối 1:          E2 82
decode(false):   UNDERFLOW; không có ký tự €
Giữ byte:        E2 82
Khối 2:          AC
decode(true):    tạo €; sau đó UNDERFLOW
flush():         UNDERFLOW, hoàn tất
~~~

Đây là kết quả đúng. Dữ liệu chưa hoàn chỉnh ở khối đầu tiên **không phải malformed**.

**Tình huống B — UTF-8 bị cụt thật sự ở cuối nguồn:**

~~~text
Dòng byte:       E2 82
Khối 1:          E2 82
decode(false):   UNDERFLOW; chờ byte tiếp theo
Nguồn kết thúc thật:
decode(true):    MALFORMED (khi chính sách là REPORT)
~~~

Nếu muốn từ chối dữ liệu lỗi, gọi `status.throwException()` để ném `MalformedInputException` (một loại `CharacterCodingException`). Nếu cấu hình `REPLACE`, decoder có thể sinh ký tự thay thế thay vì dừng; ứng dụng phải quyết định chính sách phù hợp.

**Tình huống C — Output buffer không chứa đủ:**

~~~text
Đã đọc đủ byte; decoder muốn phát thêm ký tự
CharBuffer đã đầy hoặc không đủ chỗ
decode(...):     OVERFLOW
Đọc hết ký tự hiện có từ CharBuffer, rồi clear()
decode(...):     tiếp tục xử lý ByteBuffer ở vị trí còn lại
~~~

`OVERFLOW` **không có nghĩa dữ liệu sai**; nó báo thiếu chỗ trống ở đầu ra. Ngược lại, nếu cứ gọi lại `decode` với cùng CharBuffer đầy mà không thu dữ liệu, chương trình có thể lặp mãi không tiến triển.

## 11. Không reset decoder giữa các khối

Sai lầm phổ biến là viết:

~~~java
for (byte[] chunk : chunks) {
    CharsetDecoder decoder = StandardCharsets.UTF_8.newDecoder();
    // Decode riêng từng chunk...
}
~~~

Đoạn trên chỉ là minh họa ý tưởng sai: biến `chunks` được giả định có sẵn, code không độc lập. Mỗi decoder mới có trạng thái ban đầu, nên khối sau không biết các byte còn dở của khối trước. Ngay cả khi giữ cùng decoder nhưng gọi `reset()` sau mỗi lượt cũng làm mất trạng thái của chuỗi dữ liệu liên tục.

Đúng là tạo một decoder cho **cả nguồn**, giữ ByteBuffer chưa tiêu thụ và trạng thái decoder qua các lượt. Chỉ gọi `reset()` sau khi vòng đời hiện tại hoàn tất và khi muốn xử lý một nguồn mới, độc lập về mặt mã hóa. Với charset có trạng thái chuyển đổi (stateful encoding), giữ trạng thái càng quan trọng; không thể áp đặt cách nghĩ “mỗi byte xác định duy nhất cách diễn giải” cho mọi charset.

## 12. Lỗi dữ liệu, kiểm tra chất lượng và chiến lược phục hồi

Một ứng dụng nhập tệp cấu hình hoặc dữ liệu hợp đồng thường cần tính chính xác: dùng `REPORT` để biết nguồn chứa chuỗi byte không hợp lệ hoặc bị cụt. Một trình hiển thị log lại có thể ưu tiên tiếp tục: `REPLACE` hợp lý nếu chấp nhận mất thông tin và có cơ chế thông báo.

Có thể tạo ví dụ kiểm tra lỗi không cần tệp:

~~~java
byte[] incomplete = {(byte) 0xE2, (byte) 0x82};
// Giải mã bằng decoder UTF-8 với REPORT.
// Với endOfInput=false: cần chờ byte kế tiếp.
// Với endOfInput=true: báo malformed.
~~~

Đây là đoạn dữ liệu minh họa; để kiểm tra đầu vào lỗi, hãy dùng chính vòng lặp `decode` trong ví dụ đầy đủ và truyền `incomplete`. `CharsetDecoder` có thể trả `CoderResult` lỗi, rồi `throwException()` ném ngoại lệ; không nên bắt lỗi và tự ghi `"?"` nếu yêu cầu giữ chính xác văn bản.

**Không thể sửa mất dữ liệu bằng cách tự nối các `String` đã giải mã lỗi.** Sau khi mỗi đoạn đã biến byte lỗi thành `�`, thông tin byte gốc có thể mất; phải giữ byte gốc hoặc giải mã lại toàn bộ từ nguồn chuẩn.

Nếu cần phục hồi ở cấp giao thức, hãy xác định rõ liệu phần byte còn dở là:

- Một ký tự đang chờ byte tiếp theo (chưa phải EOF).
- Một chuỗi byte thật sự sai/mất byte.
- Một khối bị cắt vì giới hạn thông điệp; phải quy định có được tiếp tục sang thông điệp tiếp theo hay không.
- Dữ liệu đúng UTF-8 nhưng bị xử lý bằng charset sai.

Các trường hợp này có cùng dấu hiệu “chưa tạo được ký tự”, nhưng cách giải quyết không giống nhau.

## 13. Chú ý về BOM, charset và mã hóa theo từng luồng

UTF-8 không cần Byte Order Mark (BOM), nhưng một nguồn có thể bắt đầu với ba byte `EF BB BF`. Nếu giải mã như nội dung bình thường, decoder UTF-8 có thể tạo ký tự `U+FEFF`. Việc coi ký tự đầu này là dấu hiệu cần loại bỏ hay là dữ liệu cần giữ **phụ thuộc định dạng và hợp đồng đầu vào**.

Nếu BOM bị chia làm nhiều lần đọc, nó cũng cần được xử lý như một chuỗi byte liên tục, tuyệt đối không giải mã riêng mỗi phần. Không nên tự ý loại mọi `U+FEFF` xuất hiện trong văn bản, vì điều đó có thể biến đổi nội dung hợp lệ.

Với UTF-16 và các charset khác, quy tắc byte-order và trạng thái có thể khác UTF-8. Hãy chọn đúng `Charset` ngay từ đầu, đồng thời giữ **cùng decoder** cho cả dòng dữ liệu. Không đổi charset giữa các khối chỉ vì khối nào đó giải mã chưa ra chữ.

## 14. Kiểm thử ranh giới: cùng dữ liệu, mọi cách chia khối đều phải đúng

Một bài kiểm thử tốt không chỉ dùng buffer lớn. Hãy lấy cùng một chuỗi văn bản chứa ASCII, chữ có dấu, ký tự ba byte và emoji bốn byte, rồi thử cung cấp dữ liệu theo các kích thước khối 1, 2, 3, 4, 5... byte. Đối với dữ liệu UTF-8 hợp lệ, **kết quả giải mã cuối cùng phải giống nhau**.

Ví dụ có thể bổ sung ngay vào `main` của `Utf8IncrementalDecoderDemo` sau khi đã có `bytes` và `original`:

~~~java
for (int size = 1; size <= 9; size++) {
    String actual = decodeInChunks(bytes, size);
    if (!original.equals(actual)) {
        throw new AssertionError("Incorrect chunk size: " + size);
    }
}
System.out.println("All chunk sizes passed");
~~~

Đây là **đoạn chèn vào lớp ví dụ ở mục 8**, không phải chương trình độc lập. Nếu chèn sau những lệnh in đã có và chạy lại, chương trình sẽ in thêm:

~~~text
All chunk sizes passed
~~~

Ý nghĩa kiểm thử:

- Kích thước 1 buộc mỗi byte của `€` và `😀` lần lượt đi qua nhiều khối.
- Kích thước 2 và 3 tạo nhiều vị trí cắt giữa ký tự.
- Kích thước 4 trở lên vẫn cần kiểm tra khi dữ liệu có thứ tự ký tự khác.
- Kiểm thử `byte[]` rỗng để bảo đảm decoder vẫn được kết thúc và flush mà không lỗi.
- Kiểm thử byte cuối bị cắt để bảo đảm chế độ `REPORT` phát hiện malformed thay vì âm thầm mất dữ liệu.

Các kiểm thử này giúp phát hiện lỗi thường gặp trong việc gọi `compact()`, đánh dấu `endOfInput` quá sớm, không thu `CharBuffer`, reset decoder giữa lượt hoặc viết thêm ký tự thay thế vô ý.

## 15. Những lỗi triển khai thường gặp

| Lỗi | Hậu quả | Cách đúng |
| --- | --- | --- |
| `new String(chunk, UTF_8)` cho từng lần đọc rồi nối | Một code point nhiều byte bị cắt có thể thành `�` hoặc nội dung sai | `InputStreamReader` hoặc một `CharsetDecoder` xuyên suốt |
| `ByteBuffer.clear()` sau UNDERFLOW dù còn byte | Vứt phần đầu chưa hoàn chỉnh của ký tự | `compact()` để giữ byte chưa tiêu thụ |
| Đặt `endOfInput=true` sau mỗi khối | Decoder coi cuối khối như cuối dòng, báo malformed nhầm | Chỉ đặt true khi EOF thật sự |
| Không gọi `decode(..., true)` khi EOF | Decoder không nhận tín hiệu kết thúc để xử lý phần dư | Thực hiện lần decode cuối |
| Không gọi `flush()` sau decode cuối | Với decoder có trạng thái, có thể bỏ sót đầu ra cuối | Flush đến UNDERFLOW |
| Gặp OVERFLOW nhưng không thu CharBuffer | Vòng lặp thiếu tiến triển, có thể bị kẹt | Flip → đọc đầu ra → clear → decode tiếp |
| Gặp UNDERFLOW rồi vứt input.remaining() | Mất dữ liệu đang chờ byte kế | Bảo toàn phần chưa tiêu thụ |
| Tạo buffer đầu vào quá nhỏ | Không đủ chỗ ghép chuỗi byte nhiều byte | Cấp buffer đủ hoặc mở rộng theo nhu cầu |
| Tạo buffer đầu ra quá nhỏ | Không đủ chỗ sinh cặp surrogate | Cấp đủ chỗ cho đầu ra tối thiểu |
| Reset decoder sau mỗi lượt | Xóa trạng thái của dòng dữ liệu | Chỉ reset trước dòng độc lập mới |
| Đồng nhất `read() == 0` với EOF | Kết thúc sai ở channel không chặn | Phân biệt chưa có dữ liệu với `-1` |
| Không chọn charset rõ ràng | Cùng byte có thể được diễn giải khác nhau | Chỉ định charset theo định dạng đầu vào |
| Nuốt `CharacterCodingException` | Che dữ liệu nguồn hỏng hoặc cấu hình sai | Báo lỗi hoặc ghi nhận chính sách thay thế rõ |
| Đếm ký tự bằng số byte | Sai độ dài với tiếng Việt/emoji | Phân biệt UTF-8 bytes, UTF-16 units và code point |

## 16. Câu hỏi tự kiểm tra

**Câu 1.** Một byte stream cung cấp `E2 82`, decoder UTF-8 với `endOfInput=false` trả UNDERFLOW. Đây có phải dữ liệu lỗi?

**Trả lời:** Chưa. Bộ giải mã thiếu byte thứ ba của một chuỗi UTF-8 ba byte; giữ `E2 82` và nạp tiếp `AC` để nhận `€`.

**Câu 2.** Đã xác nhận EOF, decoder nhận `E2 82` với `endOfInput=true` và chế độ REPORT. Nên chờ nữa không?

**Trả lời:** Không. Nếu EOF thật sự, dữ liệu bị cụt; báo lỗi malformed theo `CoderResult`/`CharacterCodingException`. Chỉ khi giao thức chưa thực sự kết thúc mới được chờ thêm.

**Câu 3.** Decoder trả OVERFLOW. Có nên lập tức nạp thêm byte vào `ByteBuffer`?

**Trả lời:** Không cần. Trước tiên giải phóng `CharBuffer` và tiếp tục decode các byte đã có; OVERFLOW nói về **chỗ trống đầu ra**, không phải thiếu byte đầu vào.

**Câu 4.** Vì sao một `String` hiển thị emoji có `length() == 2` dù emoji được xem là một code point?

**Trả lời:** `String.length()` đếm đơn vị mã UTF-16. Code point ngoài BMP dùng một cặp surrogate gồm hai đơn vị `char`.

**Câu 5.** Khi nào nên chọn `InputStreamReader` thay vì tự gọi `CharsetDecoder`?

**Trả lời:** Khi mục tiêu chỉ là đọc văn bản tuần tự và không cần tự kiểm soát mảng byte, trạng thái decoder hoặc CoderResult. `InputStreamReader` giải quyết vấn đề byte bị chia trong các lượt đọc bên dưới.

**Câu 6.** Một channel không chặn trả `0` byte. Có được gọi `decode(input, output, true)` không?

**Trả lời:** Không chỉ vì kết quả 0. Đây thường là tình trạng chưa có byte sẵn; phải đợi thêm hoặc theo dõi trạng thái theo API giao thức. Chỉ đánh dấu EOF khi nguồn thực sự hoàn tất.

## 17. Ghi nhớ để áp dụng

1. **Một nguồn văn bản là một chuỗi byte liên tục.** Ranh giới `read` không có ý nghĩa mã hóa; một ký tự UTF-8 có thể trải qua nhiều khối.
2. **Giải mã theo trạng thái.** Đơn giản nhất là một `InputStreamReader` cho cả nguồn; khi dùng NIO trực tiếp, giữ một `CharsetDecoder` xuyên suốt.
3. **`UNDERFLOW` cần dữ liệu tiếp hoặc đã hết dữ liệu hiện có; `OVERFLOW` cần chỗ chứa đầu ra.** Cả hai đều không tự là lỗi.
4. **Giữ byte chưa tiêu thụ bằng `ByteBuffer.compact()`**, nạp thêm rồi `flip()`. Với CharBuffer, `flip()` để lấy ký tự và `clear()` khi đã tiêu thụ hết.
5. **Chỉ gọi `decode(..., true)` tại EOF thật**, sau đó `flush()` đến UNDERFLOW. Không reset giữa các khối, không đóng luồng khi chỉ mới hết một lần đọc.
6. **Kiểm thử với khối 1–4 byte, dữ liệu có dấu và emoji.** Kiểm thử dữ liệu bị cụt với chính sách REPORT để bảo đảm phát hiện lỗi thay vì tạo văn bản sai.

### Tài liệu API tham khảo

- [CharsetDecoder — Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/charset/CharsetDecoder.html)
- [CoderResult — Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/charset/CoderResult.html)
- [CodingErrorAction — Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/charset/CodingErrorAction.html)
- [ByteBuffer — Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/ByteBuffer.html)
- [InputStreamReader — Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/InputStreamReader.html)
- [StandardCharsets — Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/charset/StandardCharsets.html)
