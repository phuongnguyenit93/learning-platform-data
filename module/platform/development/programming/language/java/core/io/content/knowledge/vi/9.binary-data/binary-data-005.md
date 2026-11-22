# readFully khác read và cách xử lý EOFException trong Java I/O

Trong xử lý **dữ liệu nhị phân**, không thể mặc định một lệnh đọc sẽ nhận đủ số byte cần thiết. Một header dài 4 byte, một bản ghi cố định 16 byte hay payload có độ dài khai báo 1.024 byte đều cần được đọc **đủ chính xác số byte yêu cầu** trước khi giải mã thành cấu trúc hoàn chỉnh. Đây là khác biệt trọng tâm giữa `read(...)` và `readFully(...)`.

- **`read(...)`**: thực hiện một lượt đọc và **trả về số byte thực tế nhận được**. Con số này có thể nhỏ hơn độ dài yêu cầu; `-1` thường biểu thị EOF.
- **`DataInputStream.readFully(...)`**: đọc lặp cho tới khi **đủ số byte yêu cầu**, hoặc ném **`EOFException`** nếu luồng kết thúc trước khi đủ. Phương thức trả về `void`, không trả số byte.
- **`EOFException`**: báo “đã hết dữ liệu trước khi hoàn thành cấu trúc bắt buộc”, cần xử lý theo ý nghĩa nghiệp vụ: bản tin bị cắt, file thiếu, kết nối đóng quá sớm hoặc thiếu dữ liệu theo định dạng.

Mục tiêu của bài là biết khi nào nên chấp nhận **short read**, khi nào cần đọc **exact length**, và làm sao tránh sử dụng dữ liệu thiếu sau `EOFException`.

## 1. Phân biệt dữ liệu “đang có” và “đủ theo định dạng”

Giả sử một phần của file nhị phân khai báo rằng payload kế tiếp **phải dài 5 byte**. Tầng I/O chỉ chuyển về 2 byte ở lượt đầu:

```text
Yêu cầu:  5 byte dữ liệu

Nguồn:    A B C D E
read #1:  A B           -> trả về 2
read #2:      C D       -> trả về 2
read #3:          E     -> trả về 1
read #4: EOF

read(buffer[5]) một lần:    có thể chỉ nhận A B
readFully(buffer[5]):       tiếp tục tới khi nhận đủ A B C D E
```

Nếu dùng `read(buffer)` rồi giả định buffer đã đủ 5 byte, ba vị trí còn lại có thể vẫn chứa giá trị mặc định hoặc dữ liệu cũ. Nếu có bytes bị thiếu thực sự, `readFully` phải báo lỗi. **Một lượt đọc ít hơn kích thước buffer không có nghĩa đã EOF**: một luồng mạng có thể cung cấp dữ liệu thành nhiều mảnh.

| Tiêu chí | `read(byte[])` | `DataInputStream.readFully(byte[])` |
| --- | --- | --- |
| Mục đích | Nhận số byte hiện có của một lượt đọc | Nhận **đúng N byte** theo yêu cầu |
| Số lượt đọc tầng dưới | Không được yêu cầu đọc tới khi lấp đầy | Tự đọc tiếp nếu lượt trước ngắn |
| Giá trị trả về | `int` = số byte, hoặc `-1` khi EOF | `void` |
| Nguồn hết trước khi đủ N | Có thể trả `-1` / trả ít byte | Ném `EOFException` |
| Cần tự kiểm tra số byte? | **Có** | Thành công nghĩa là đủ N |
| Tình huống thích hợp | Sao chép luồng tới EOF, xử lý chunk | Đọc header, record, payload biết trước độ dài |

Các quy tắc trên xét buffer có độ dài **dương**. Yêu cầu đọc `0` byte có trường hợp đặc biệt: `readFully(b, off, 0)` hoàn thành ngay cả khi luồng ở EOF; còn `InputStream.read(b, off, 0)` trả `0`.

## 2. `read(byte[])` trả về điều gì?

`InputStream.read(byte[])` và `DataInputStream.read(byte[])` có chữ ký:

```java
int bytesRead = input.read(buffer);
```

Đoạn minh họa giả định `input` là `InputStream` hoặc `DataInputStream` đã có và `buffer` là `byte[]`.

Với `buffer.length > 0` và một `InputStream` tuân thủ hợp đồng thông thường, kết quả là:

- `1..buffer.length`: số byte hợp lệ **ở lần gọi vừa rồi**;
- `-1`: EOF, không còn byte để đọc;
- `IOException`: lỗi I/O.

Ví dụ `byte[] buffer = new byte[8192]` không đảm bảo `read(buffer) == 8192`. Nguồn có thể trả 1, 2 hay vài trăm byte dù còn dữ liệu trong tương lai. **Không dùng một lượt `read` để kết luận đã nhận đủ cả bản tin.**

### Khi không biết trước tổng độ dài: dùng vòng lặp theo số byte

```java
byte[] buffer = new byte[8192];
int n;

while ((n = input.read(buffer)) != -1) {
    output.write(buffer, 0, n);
}
```

Đây là đoạn minh họa với `input` và `output` đã mở. `output.write(buffer, 0, n)` ghi **đúng `n` byte vừa đọc**, tránh ghi rác từ các vị trí chưa được điền hoặc còn dữ liệu cũ. Lặp đến EOF phù hợp để **sao chép toàn bộ luồng**; nếu protocol xác định độ dài riêng cho từng message, EOF không thay thế được việc kiểm soát ranh giới message.

## 3. `DataInputStream.readFully(...)` hoạt động ra sao?

`DataInputStream` triển khai giao diện `DataInput`, cung cấp các phương thức đọc dữ liệu nhị phân có cấu trúc. Hai overload chính:

```java
dataInput.readFully(buffer);
dataInput.readFully(buffer, offset, length);
```

Các đoạn trên giả định `dataInput` là `DataInputStream` và `buffer` là `byte[]`.

- `readFully(buffer)` yêu cầu điền **toàn bộ** `buffer.length` byte.
- `readFully(buffer, offset, length)` yêu cầu điền đúng `length` byte, bắt đầu ở chỉ số `offset`. Những phần tử ngoài đoạn đích không phải vùng cần ghi.
- Nếu **đọc đủ**, phương thức hoàn thành bình thường, không trả số byte. **Không cần** gọi thêm một `read` để “xác nhận đủ”.
- Nếu **EOF trước khi đủ**, nó ném `EOFException`, một lớp con của `IOException`.
- Nếu có lỗi I/O khác, nó có thể ném `IOException` tương ứng.
- Nếu tham số `offset` hoặc `length` không hợp lệ, phương thức báo lỗi chỉ số; đừng thay thế lỗi lập trình này bằng nhánh xử lý EOF.

Ví dụ cần nhận đúng 8 byte đầu của một record:

```java
byte[] header = new byte[8];
dataInput.readFully(header);  // Chỉ tiếp tục khi đã có đủ 8 byte.
parseHeader(header);         // parseHeader là hàm nghiệp vụ minh họa.
```

**Điểm then chốt:** không gọi `parseHeader` nếu `readFully` ném `EOFException`. Khi thiếu byte, dữ liệu trong buffer có thể bị **thay đổi một phần**. Vì `readFully` trả `void`, nó không thông báo đã điền được bao nhiêu byte trước lỗi; không coi buffer thiếu là một header hợp lệ.

### Nguyên lý vòng đọc bên trong

Có thể hình dung `readFully(b, off, len)` thực hiện logic tương tự:

```java
// Pseudocode để giải thích ý tưởng, không phải mã nguồn thư viện.
int total = 0;
while (total < len) {
    int n = input.read(b, off + total, len - total);
    if (n == -1) {
        throw new EOFException();
    }
    total += n;
}
```

Đây là **pseudocode** với `input` giả định tuân thủ hợp đồng đọc buffer dương; không dùng để thay thế implementation của JDK hay bỏ qua xử lý các stream tùy chỉnh vi phạm hợp đồng trả `0` liên tục. Mục tiêu là hiểu vì sao một lần `read` ngắn **không** khiến `readFully` bỏ cuộc, nhưng EOF trước khi điền đủ **là lỗi**.

## 4. Ví dụ Java 17+ độc lập: short read, readFully và EOFException

Chương trình sau cố ý bọc `InputStream` để **mỗi lần đọc vào mảng nhận tối đa 2 byte**, dù buffer được yêu cầu lớn hơn. Nhờ vậy kiểm tra được hành vi ngay cả khi một `ByteArrayInputStream` bình thường có thể cung cấp đủ nhiều byte trong một lượt.

Lưu đúng tên tệp **`ReadFullyDemo.java`**:

```java
import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.DataInputStream;
import java.io.DataOutputStream;
import java.io.EOFException;
import java.io.FilterInputStream;
import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import java.util.Arrays;

public class ReadFullyDemo {

    public static void main(String[] args) throws IOException {
        demonstrateShortRead();
        demonstrateTruncatedInput();
        demonstrateLengthPrefixedFrame();
    }

    private static void demonstrateShortRead() throws IOException {
        byte[] source = "ABCDE".getBytes(StandardCharsets.US_ASCII);
        byte[] result = new byte[5];

        try (DataInputStream input = new DataInputStream(
                new TwoByteInputStream(new ByteArrayInputStream(source)))) {

            int first = input.read(result);
            System.out.println("First read: " + first);

            input.readFully(result, first, result.length - first);
            System.out.println("Reconstructed: " +
                    new String(result, StandardCharsets.US_ASCII));
            System.out.println("EOF after data: " + input.read());
        }
    }

    private static void demonstrateTruncatedInput() throws IOException {
        byte[] shortSource = {10, 20, 30};
        byte[] requestedFive = new byte[5];
        Arrays.fill(requestedFive, (byte) -1);

        try (DataInputStream input = new DataInputStream(
                new TwoByteInputStream(
                        new ByteArrayInputStream(shortSource)))) {

            try {
                input.readFully(requestedFive);
                System.out.println("Unexpected success");
            } catch (EOFException e) {
                System.out.println("Truncated: " +
                        e.getClass().getSimpleName());
            }
        }

        // Chỉ minh họa buffer đã bị điền dở, tuyệt đối
        // KHÔNG xử lý buffer này như một record hợp lệ.
        System.out.println("Partial buffer (invalid): " +
                Arrays.toString(requestedFive));
    }

    private static void demonstrateLengthPrefixedFrame()
            throws IOException {
        byte[] message = "Xin chào".getBytes(StandardCharsets.UTF_8);

        ByteArrayOutputStream wire = new ByteArrayOutputStream();
        try (DataOutputStream output = new DataOutputStream(wire)) {
            output.writeInt(message.length);
            output.write(message);
        }

        try (DataInputStream input = new DataInputStream(
                new TwoByteInputStream(
                        new ByteArrayInputStream(wire.toByteArray())))) {

            int declaredLength = input.readInt();

            if (declaredLength < 0 || declaredLength > 1024) {
                throw new IOException("Invalid frame length");
            }

            byte[] payload = new byte[declaredLength];
            input.readFully(payload);

            System.out.println("Frame bytes: " + payload.length);
            System.out.println("Frame text: " +
                    new String(payload, StandardCharsets.UTF_8));
        }
    }

    private static final class TwoByteInputStream
            extends FilterInputStream {

        private TwoByteInputStream(InputStream source) {
            super(source);
        }

        @Override
        public int read(byte[] target, int offset, int length)
                throws IOException {
            return super.read(
                    target, offset, Math.min(length, 2));
        }
    }
}
```

Biên dịch/chạy bằng JDK 17+:

```bash
javac -encoding UTF-8 ReadFullyDemo.java
java ReadFullyDemo
```

**Stdout dự kiến:**

```text
First read: 2
Reconstructed: ABCDE
EOF after data: -1
Truncated: EOFException
Partial buffer (invalid): [10, 20, 30, -1, -1]
Frame bytes: 9
Frame text: Xin chào
```

Diễn giải ba trường hợp:

1. **Short read:** nguồn có đủ `ABCDE` nhưng giới hạn chỉ cho đọc tối đa 2 byte/lượt. `read(result)` trả `2`; gọi `readFully(result, 2, 3)` tiếp tục đọc nốt `CDE`. Lúc này có thể xử lý đủ 5 byte.
2. **Truncated:** nguồn chỉ có `10, 20, 30` nhưng đích đòi đủ 5 byte. `readFully(requestedFive)` điền được vài byte rồi chạm EOF và ném `EOFException`. Nội dung buffer sau lỗi có thể đã thay đổi; hiển thị buffer **chỉ để thấy dữ liệu điền dở**, không phải “kết quả gần đúng” được phép sử dụng.
3. **Length-prefixed frame:** `DataOutputStream.writeInt(message.length)` ghi 4 byte độ dài theo quy ước big-endian của `DataOutput`, sau đó ghi payload UTF-8. `DataInputStream.readInt()` đọc đúng số byte cần cho một `int`, rồi `readFully(payload)` nhận đủ số byte được khai báo. Chuỗi `"Xin chào"` có 9 byte UTF-8 và được giải mã đúng sau khi nhận đầy đủ.

Wrapper `TwoByteInputStream` là công cụ giả lập nguồn trả ít byte; code không nên dựa vào số byte mỗi lần đọc khi vận hành với mạng hay file thực tế.

## 5. Hiểu đúng `EOFException`

`EOFException` kế thừa `IOException`:

```text
Exception
  -> IOException
       -> EOFException
```

Sự khác biệt cốt lõi:

| Thao tác | Khi EOF | Diễn giải |
| --- | --- | --- |
| `InputStream.read()` | Trả `-1` | Hết byte theo API đọc đơn |
| `InputStream.read(byte[])` (buffer dương) | Trả `-1` nếu đã hết trước khi đọc thêm | Kết thúc một luồng thông thường |
| `DataInputStream.readFully(byte[N])` | Ném `EOFException` nếu thiếu để đủ N | Không đủ dữ liệu cho cấu trúc bắt buộc |
| `DataInputStream.readInt()` | Ném `EOFException` nếu thiếu byte của `int` | Không thể hình thành một số `int` hoàn chỉnh |
| `RandomAccessFile.readFully(byte[N])` | Ném `EOFException` nếu thiếu N byte | Không đủ dữ liệu trong tệp |

**EOF không luôn là lỗi.** Đọc luồng cho tới khi hết là nghiệp vụ hợp lệ: `read(...)` trả `-1` là tín hiệu bình thường. Nhưng khi một record **bắt buộc** phải dài N byte, gặp EOF trước N byte nghĩa là record thiếu; `readFully` chủ động ném exception thay vì trả một bộ dữ liệu ngắn.

### Catch đúng lớp và đúng phạm vi

```java
try {
    input.readFully(record);
    processCompleteRecord(record);
} catch (EOFException truncated) {
    throw new IOException(
            "Record bị cắt trước khi đủ " + record.length + " byte",
            truncated);
}
```

Đây là minh họa cần biến `input` (kiểu `DataInputStream`), `record` (mảng byte), và hàm `processCompleteRecord`. Việc bọc ngoại lệ giúp tầng gọi biết rằng một record cụ thể không hoàn chỉnh, đồng thời giữ nguyên nguyên nhân bằng `cause`.

Nếu đây là protocol có nhiều record, **không tiếp tục đọc record tiếp theo sau EOFException như thể record cũ đã thành công**. Kết nối đã kết thúc trước khi đủ frame; thường cần coi frame là lỗi và dừng đọc/đóng hoặc báo lỗi.

### EOF sạch ở ranh giới record khác với record bị cắt

Giả sử protocol có header 4 byte chứa độ dài. Khi `readInt()` gặp `EOFException`, có hai khả năng:

- **EOF sạch:** không có byte nào của header mới, nghĩa là hết luồng tại đúng ranh giới record.
- **Header bị cắt:** có 1–3 byte của header rồi mới hết, dữ liệu sai định dạng.

Chỉ `catch (EOFException)` từ `readInt()` **không đủ thông tin phân biệt** hai tình huống, vì cả hai đều ném cùng loại ngoại lệ. Để phân biệt, protocol/decoder cần quản lý ranh giới rõ ràng, hoặc đọc byte đầu header riêng trước rồi buộc đọc đủ 3 byte còn lại. Không tự coi mọi `EOFException` của `readInt` là “hết file hợp lệ”.

Ví dụ logic riêng cho một luồng các bản ghi có header dài 4 byte:

```java
int first = input.read();

if (first == -1) {
    // EOF trước byte đầu header: hết luồng sạch ở ranh giới record.
    return;
}

byte[] restOfHeader = new byte[3];
input.readFully(restOfHeader); // Thiếu 1-3 byte: lỗi truncated header.

// Ghép header theo chuẩn giao thức (big-endian) nếu cần.
int length = ((first & 0xFF) << 24)
        | ((restOfHeader[0] & 0xFF) << 16)
        | ((restOfHeader[1] & 0xFF) << 8)
        | (restOfHeader[2] & 0xFF);
```

Đây là **đoạn minh họa** đặt trong một phương thức được phép `return`, với `input` là `DataInputStream`. Định dạng header ví dụ dùng số nguyên 32-bit big-endian như `DataInputStream.readInt()`. Cần tiếp tục **kiểm tra `length`** theo giới hạn của protocol trước khi cấp phát buffer; nếu payload thiếu byte, `readFully` sẽ ném `EOFException`.

## 6. Trường hợp có offset và độ dài

`readFully(buffer, off, len)` chỉ yêu cầu điền vào vùng `[off, off + len)`. Ví dụ một mảng 12 byte, muốn đọc 4 byte dữ liệu từ chỉ số 5:

```java
byte[] frame = new byte[12];
input.readFully(frame, 5, 4);
```

Phương thức yêu cầu 4 byte mới cho các vị trí `5, 6, 7, 8`. Nếu thành công, những byte ngoài đoạn chỉ định không phải dữ liệu mới của lần gọi này.

Khi tự kiểm tra dữ liệu đã đọc, đừng nhầm tham số `len` là *vị trí kết thúc*: `off=5, len=4` là bốn byte từ chỉ số 5, không phải đoạn từ 5 đến 4.

Với `read(buffer, off, len)`, phương thức trả `n` byte vừa đọc trong đoạn đó; để lấp đầy một phần bằng vòng đọc thủ công, cần tăng offset theo `n` **chứ không theo `len`**.

## 7. Nếu không dùng `readFully`, tự đọc đủ N byte thế nào?

Khi bạn chỉ có `InputStream`, có thể tự viết hàm đọc đúng số byte yêu cầu. Ví dụ dưới đây hoạt động với `InputStream` tuân thủ hợp đồng thông thường cho buffer có độ dài dương:

```java
import java.io.EOFException;
import java.io.IOException;
import java.io.InputStream;

static void readExactly(InputStream input, byte[] buffer)
        throws IOException {
    int offset = 0;

    while (offset < buffer.length) {
        int n = input.read(
                buffer, offset, buffer.length - offset);

        if (n == -1) {
            throw new EOFException(
                    "Unexpected EOF after " + offset +
                    " of " + buffer.length + " bytes");
        }

        offset += n;
    }
}
```

Đây là phương thức minh họa phải đặt trong một class. `offset` chỉ tăng bằng **số byte thực đọc `n`**. Khi buffer đầy, hàm hoàn thành. Nếu EOF trước khi đầy, hàm ném `EOFException`.

Trong thực tế, `DataInputStream.readFully` đã cung cấp chức năng này cho trường hợp cần nhận đúng N byte. Không nên tự viết lại chỉ vì muốn “tối ưu” khi API chuẩn đã phù hợp.

Với các nguồn I/O tùy chỉnh có thể trả `0` liên tục dù yêu cầu đọc số byte dương (không tuân thủ hợp đồng của `InputStream`), một vòng lặp tự viết thiếu kiểm soát sẽ có nguy cơ quay vô hạn; cần xử lý theo contract cụ thể của nguồn. Mã học tập ở trên dựa vào hợp đồng chuẩn.

## 8. So với `InputStream.readNBytes` và `readAllBytes`

Từ Java 9, `InputStream` có thêm các API tiện dụng:

| API | Hành vi khi EOF trước số lượng mong muốn |
| --- | --- |
| `readNBytes(int len)` | Trả `byte[]` có thể **ngắn hơn `len`**; người gọi kiểm tra độ dài |
| `readNBytes(byte[] b, int off, int len)` | Trả số byte thực đọc, có thể **ít hơn `len`** |
| `readAllBytes()` | Đọc tất cả byte còn lại đến EOF; không thể bảo đảm cấu trúc N byte nếu không tự đối chiếu |
| `DataInputStream.readFully(byte[] b)` | **Ném `EOFException`** nếu chưa đủ đúng `b.length` byte |

Nếu muốn chính sách “bắt buộc đủ N”, vẫn có thể dùng `readNBytes` rồi kiểm tra:

```java
byte[] bytes = input.readNBytes(expectedLength);
if (bytes.length != expectedLength) {
    throw new EOFException("Expected " + expectedLength
            + " bytes, got " + bytes.length);
}
```

Đoạn minh họa giả định `input` là `InputStream`, `expectedLength` là số nguyên không âm đã **qua kiểm tra giới hạn**, và đã import `EOFException`. Điểm khác biệt là `readNBytes` **không tự báo EOF thiếu N như `readFully`**, mà để lập trình viên đối chiếu độ dài.

**Không dùng `available()` làm số byte còn lại của file/network stream**: `available()` chỉ cho biết ước lượng byte có thể đọc ngay mà không chặn trong một số tình huống, không phải kích thước bản tin hoặc điều kiện kết thúc chính xác.

## 9. Áp dụng cho file và giao thức có chiều dài khai báo

Bài toán phổ biến: phần đầu của mỗi frame chứa **độ dài payload**, sau đó là đúng số byte payload. Nếu đã đọc và xác thực header, logic điển hình:

```java
int payloadSize = input.readInt();

if (payloadSize < 0 || payloadSize > MAX_PAYLOAD_BYTES) {
    throw new IOException("Payload length out of bounds");
}

byte[] payload = new byte[payloadSize];
input.readFully(payload); // Thiếu byte => EOFException.
handlePayload(payload);
```

Đây là đoạn minh họa chưa độc lập: `input` là `DataInputStream`, `MAX_PAYLOAD_BYTES` là giới hạn tin cậy, và `handlePayload` là hàm ứng dụng.

**Phải xác thực độ dài trước khi cấp phát.** Dữ liệu bên ngoài có thể khai báo số âm, rất lớn hoặc cố ý sai. Không cấp phát `new byte[untrustedLength]` rồi mới kiểm tra, vì có thể gây lỗi bộ nhớ. Ngoài kích thước tối đa, ứng dụng mạng còn cần chính sách timeout, tổng dữ liệu được phép nhận và xử lý kết nối chết/chậm.

Các bước đọc nhị phân an toàn theo cấu trúc thường là:

1. Xác định trạng thái luồng và ranh giới record hiện tại.
2. Đọc đủ header theo đúng định dạng; phân biệt EOF sạch tại ranh giới với header thiếu.
3. Giải mã và **kiểm tra giá trị độ dài**.
4. Cấp phát trong giới hạn đã kiểm tra hoặc xử lý theo từng khối nếu payload quá lớn cho RAM.
5. `readFully` đúng số byte payload; nếu EOF sớm thì báo frame bị cắt.
6. Chỉ giải mã hoặc xử lý **payload đã hoàn chỉnh**.

Không nên coi việc `readFully` thành công là kiểm tra toàn bộ tính hợp lệ của payload. Dữ liệu có thể đủ byte nhưng sai magic number, checksum, nội dung UTF-8, cấu trúc hoặc business rule; các bước xác thực ấy vẫn phải có.

## 10. Lỗi thường gặp

| Cách làm sai | Hậu quả | Cách xử lý |
| --- | --- | --- |
| Gọi `read(buffer)` đúng một lần rồi parse N byte | Dữ liệu có thể chỉ mới nhận một phần | Lặp đọc đủ hoặc dùng `readFully` |
| Dừng khi `bytesRead < buffer.length` | Short read không đồng nghĩa EOF | Chỉ kết thúc luồng thường bằng `-1` |
| Gọi `write(buffer)` sau short read | Ghi cả byte chưa hợp lệ/byte cũ | `write(buffer, 0, bytesRead)` |
| Catch `EOFException` rồi parse buffer như record đủ | Buffer có thể bị điền dở | Bỏ record thiếu; thông báo lỗi |
| Catch `EOFException` ở `readInt` rồi xem là kết thúc sạch mọi lúc | Không phân biệt hết ở ranh giới với header bị cắt | Theo dõi số byte header hoặc thiết kế framing rõ |
| Tưởng `readFully` trả số byte | Phương thức trả `void` | Thành công nghĩa là đủ số byte |
| Dùng `available()` để quyết định đã đủ N | Không phản ánh chính xác tổng byte còn lại | Dùng contract của protocol và `readFully` |
| Cấp phát trực tiếp từ độ dài chưa kiểm tra | Rủi ro bộ nhớ, từ chối dịch vụ | Kiểm tra giới hạn trước khi cấp phát |
| Dùng `readAllBytes()` với input vô hạn/lớn | Có thể sử dụng quá nhiều RAM | Giới hạn dữ liệu, đọc có kiểm soát |
| Bỏ qua EOF của frame khi socket đóng | Đọc bản tin thiếu như thành công | Báo truncated frame và dừng xử lý |

## 11. Tự kiểm tra

1. `byte[] b = new byte[10]`, gọi `read(b)` và nhận `3`. Có được parse cả 10 byte không? **Không**; chỉ có 3 byte mới hợp lệ.
2. `readFully(b)` cần 10 byte nhưng luồng chỉ còn 7 byte. Kết quả là gì? **Ném `EOFException`**; không trả 7 và không được dùng buffer làm record hoàn chỉnh.
3. `readFully(b, 4, 3)` cần đọc vào các chỉ số nào? **4, 5, 6**.
4. `readFully(b, 0, 0)` khi đã EOF có ném `EOFException` không? **Không**, vì yêu cầu 0 byte.
5. `readNBytes(10)` gặp EOF sau 7 byte có luôn ném `EOFException` không? **Không**; thường trả mảng 7 byte, lập trình viên kiểm tra độ dài nếu bắt buộc đủ 10.
6. `readInt()` ném `EOFException`. Có kết luận chắc chắn “hết record sạch” được không? **Không**; header có thể thiếu 1–3 byte.
7. File có header 4 byte khai báo payload dài 2 GB trong khi ứng dụng chỉ cho phép 1 MB. Nên làm gì? **Từ chối độ dài trước khi tạo `byte[]`**.
8. `readFully` nhận đủ payload nghĩa là nội dung hợp lệ tuyệt đối? **Không**; vẫn cần kiểm tra định dạng, checksum và quy tắc của dữ liệu.

**Ghi nhớ:** `read` trả **bao nhiêu byte thực tế vừa nhận**; `readFully` yêu cầu **đúng N byte hoặc ném `EOFException`**. Hãy chỉ giải mã cấu trúc khi đã đọc đủ, và coi EOF giữa một record bắt buộc là **dữ liệu bị cắt**, không phải record thành công.