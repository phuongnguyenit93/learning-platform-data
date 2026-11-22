# Giới hạn kích thước đầu vào và lượng bộ nhớ sử dụng trong Java I/O

## 1. Vì sao giới hạn dữ liệu là một phần của thiết kế an toàn?

Ứng dụng Java thường đọc dữ liệu từ HTTP request, socket, file tải lên, file ZIP, log, message queue hoặc nguồn từ hệ thống khác. Nhiều ví dụ nhập môn chỉ đọc toàn bộ đầu vào:

```java
byte[] data = input.readAllBytes();
```

Cách này thuận tiện cho dữ liệu **nhỏ, đã được tin cậy và có giới hạn rõ ràng**, nhưng nguy hiểm nếu kích thước đầu vào do nguồn bên ngoài quyết định. Một client có thể gửi hàng gigabyte dữ liệu, một luồng có thể không bao giờ kết thúc, hoặc một file nén có thể rất nhỏ trên đĩa nhưng giải nén thành dữ liệu cực lớn. Khi đó chương trình có nguy cơ:

- Vượt giới hạn heap, phát sinh `OutOfMemoryError`.
- Tạo áp lực GC, tăng độ trễ cho các request khác.
- Chiếm CPU, I/O, ổ đĩa hoặc dung lượng mạng quá lâu.
- Làm một luồng bị kẹt vì đầu vào không kết thúc.
- Cho phép từ chối dịch vụ do tài nguyên bị tiêu thụ bất cân xứng (*resource exhaustion/DoS*).
- Để lại file tạm, output một phần hoặc trạng thái nghiệp vụ không nhất quán sau khi vượt giới hạn.

**Mục tiêu:** giới hạn **khối lượng dữ liệu thực tế được chấp nhận**, sử dụng **bộ đệm có kích thước kiểm soát được**, giới hạn số request đồng thời và hoàn tất hoặc từ chối đầu vào theo chính sách đã định.

Bài này tập trung vào các kỹ thuật trong **Java Core I/O và NIO**, dùng Java 17+ và không phụ thuộc framework web. Đây là kiến thức nền để triển khai chính sách upload trong Spring, servlet hoặc hệ thống streaming khác.

## 2. Phân biệt các giới hạn khác nhau

Một hệ thống an toàn thường cần nhiều loại giới hạn, bởi **một con số “tối đa 10 MB” không thể bảo vệ mọi tài nguyên**.

| Loại giới hạn | Tài nguyên kiểm soát | Ví dụ |
| --- | --- | --- |
| Kích thước đầu vào thô | Số byte nhận từ nguồn trước giải mã/giải nén | Tối đa byte upload |
| Kích thước sau giải nén | Số byte dữ liệu thật sau GZIP/ZIP | Ngăn file nén phình quá mức |
| Bộ nhớ cho một request | Array, buffer, parser object và state | Hạn mức bộ nhớ làm việc/request |
| Số phần tử | Số file ZIP, JSON nodes, records, headers | Tránh hàng triệu đối tượng nhỏ |
| Độ sâu cấu trúc | Nested JSON/XML/archive/object graph | Tránh recursion sâu và stack/resource exhaustion |
| Thời gian xử lý | Timeout cho đọc, parse và toàn request | Ngăn đầu vào chậm/không kết thúc |
| Số request đồng thời | Số tác vụ đang giữ tài nguyên | Tránh nhân nhiều giới hạn nhỏ thành tổng lớn |
| Dung lượng đĩa tạm | File spool và nội dung đang chờ xử lý | Tránh đầy filesystem |
| Kích thước output | Byte trả ra và dữ liệu tạm sinh ra | Tránh output không giới hạn |

Ví dụ: giới hạn mỗi request ở 8 MiB **không có nghĩa** 100 request đồng thời chỉ dùng 8 MiB. Nếu mỗi request giữ một `byte[]` 8 MiB, riêng những mảng ấy đã có thể chiếm khoảng 800 MiB, chưa tính buffer phụ, metadata, chuỗi, parser, heap khác và chi phí runtime. Nếu giải mã ra `String`, parse JSON và giữ bản sao trong cache, bộ nhớ đỉnh có thể lớn hơn nhiều.

Hạn mức phải gắn với **cách đọc, xử lý, giải nén, cấp phát và mức song song thực tế**. Một giới hạn kích thước chỉ có giá trị khi được kiểm tra **trước hoặc trong lúc tài nguyên tương ứng được tiêu thụ**.

## 3. Những API dễ đọc toàn bộ dữ liệu vào RAM

Các API sau hữu ích nhưng phải được dùng đúng trường hợp:

| API | Hành vi cần lưu ý |
| --- | --- |
| `InputStream.readAllBytes()` | Đọc mọi byte còn lại cho tới EOF và trả về `byte[]` |
| `Files.readAllBytes(path)` | Đọc cả nội dung file thành `byte[]` |
| `Files.readString(path)` | Đọc cả file thành `String` |
| `InputStream.transferTo(output)` | Chuyển tới EOF; có thể ghi lượng output không giới hạn nếu không có wrapper kiểm soát |
| `ByteArrayOutputStream` | Tích lũy byte trên heap; dung lượng tăng theo số byte đã ghi |
| `StringBuilder` | Giữ toàn bộ chuỗi đang xây, có thể tăng dần theo input |
| `BufferedReader.lines().toList()` | Có thể giữ tất cả dòng trong bộ nhớ |
| `ZipInputStream.readAllBytes()` trên entry | Có thể giải nén và giữ cả entry không giới hạn |
| `GZIPInputStream.readAllBytes()` | Có thể giải nén thành số byte lớn hơn file nguồn rất nhiều |

Javadoc Java 17 nói rõ `InputStream.readAllBytes()` dành cho các trường hợp đơn giản khi lượng dữ liệu phù hợp để lưu trữ; **không phải lựa chọn mặc định cho đầu vào lớn**. Nó có thể ném `OutOfMemoryError` nếu không thể cấp phát mảng cần thiết. `InputStream.transferTo()` không trả `byte[]` lớn, nhưng vẫn **đọc và ghi đến EOF**; nếu đích là `ByteArrayOutputStream` hoặc ổ đĩa không kiểm soát, tài nguyên vẫn có thể tăng không giới hạn.

**Đừng nhầm “streaming API” với “chính sách giới hạn đã được áp dụng”.** Một pipeline chỉ có vòng lặp streaming nhưng không giới hạn tổng byte, số record hoặc thời gian vẫn có thể tiêu thụ vô hạn tài nguyên ở tầng khác.

### `readNBytes(int)` có phải tự động an toàn không?

`input.readNBytes(n)` (Java 11+) đọc tối đa `n` byte và trả về mảng chứa số byte đọc thực tế. Đây có thể là công cụ phù hợp **nếu `n` đã được xác thực và bị giới hạn bởi chính sách**. Nhưng:

- Nếu truyền giá trị `n` khổng lồ do client cung cấp, vẫn có thể gây áp lực bộ nhớ.
- Nếu cần từ chối input **dài hơn `n`**, chỉ đọc `n` byte **không đủ** để kết luận đầu vào đã kết thúc; cần đọc thêm một byte để phát hiện phần dư, hoặc dùng giao thức quy định chính xác độ dài.
- Nếu không cần giữ toàn bộ nội dung trong RAM, mảng kết quả vẫn là chi phí bộ nhớ không cần thiết; dùng buffer cố định sẽ tốt hơn.

## 4. Không lấy `InputStream.available()` làm kích thước file

`available()` trả về **ước lượng số byte có thể đọc mà không chặn**, không phải tổng kích thước input và cũng không bảo đảm số byte còn lại cho tới EOF.

Cách sai:

```java
byte[] data = new byte[input.available()];
input.read(data); // Có thể đọc thiếu; kích thước mảng có thể sai.
```

Đoạn minh họa này có thể cho kết quả không đầy đủ và bỏ qua số byte thực tế trả về. Với network stream, `available()` có thể bằng 0 dù peer sẽ gửi dữ liệu sau đó. Với `ByteArrayInputStream`, nó có thể trông đúng vì implementation biết lượng byte còn lại, nhưng **không được suy rộng hợp đồng đó sang mọi InputStream**.

Muốn đọc tới EOF, cần vòng lặp dựa vào **giá trị trả về thực** của `read`. Muốn giới hạn tối đa, cần **đếm từng byte đã đọc và từ chối khi tổng vượt budget**.

## 5. Kiểm tra kích thước khai báo: cần nhưng không đủ

Một số nguồn biết trước kích thước hoặc công bố kích thước:

- `Files.size(path)` trả kích thước file tại thời điểm kiểm tra.
- HTTP `Content-Length` là số byte khai báo trong request header, nếu có.
- Frame nhị phân có trường độ dài 32-bit/64-bit.
- `ZipEntry.getSize()` trả kích thước dữ liệu chưa nén theo metadata nếu biết; có thể trả `-1` khi chưa biết.

Các giá trị này là tín hiệu để **từ chối sớm** hoặc chọn chiến lược xử lý, nhưng không thay thế việc giới hạn khi đọc:

1. **Metadata có thể vắng mặt hoặc không đáng tin**; client có thể gửi dữ liệu dài khác khai báo.
2. **File có thể thay đổi** giữa lúc kiểm tra `Files.size` và lúc đọc (*TOCTOU*).
3. **Giá trị âm, quá lớn, hoặc overflow** khi cộng/nhân có thể làm phép cấp phát sai.
4. **Kích thước nén không nói lên kích thước giải nén**; phải đếm byte sau giải nén.
5. **Nhiều thành phần** có thể cùng nằm dưới một container: phải giới hạn **cả từng phần và toàn bộ**.

Mẫu kiểm tra trước khi cấp phát:

```java
int length = input.readInt(); // Ví dụ frame có độ dài 4-byte.
if (length < 0 || length > MAX_FRAME_BYTES) {
    throw new IOException("Invalid frame length");
}
byte[] payload = input.readNBytes(length);
if (payload.length != length) {
    throw new EOFException("Truncated frame");
}
```

Đây là đoạn minh họa, giả sử `input` là `DataInputStream` và `MAX_FRAME_BYTES` là cấu hình **đã bị giới hạn một cách đáng tin**. Giá trị `length` phải được kiểm tra **trước** khi tạo mảng. Đừng làm `new byte[length]` rồi mới kiểm tra. Nếu payload lớn nhưng vẫn nằm trong policy, cân nhắc xử lý theo luồng thay vì giữ cả khối vào RAM.

## 6. Giới hạn đầu vào theo byte thực sự đọc

Một giải pháp nền tảng là **bounded streaming copy**: đọc bằng bộ đệm cố định, cộng dồn byte thực sự đã đọc, và không cho phép vượt hạn mức.

Giả sử chính sách cho phép **tối đa 10 byte**. Có ba tình huống:

| Input | Kết luận |
| --- | --- |
| Đúng 10 byte và sau đó EOF | Chấp nhận |
| 9 byte rồi EOF | Chấp nhận nếu giao thức cho phép ít hơn giới hạn |
| 11 byte | Từ chối vì vượt giới hạn |

Một triển khai đúng phải tránh lỗi **off-by-one**: nếu đọc được đúng 10 byte nhưng không kiểm tra EOF, nó chưa thể biết còn byte thứ 11 hay không. Đồng thời, muốn phát hiện vượt giới hạn mà không giữ nhiều dữ liệu, có thể **đọc thăm dò thêm đúng một byte** sau khi đã tiêu thụ 10 byte.

Cần xác định hợp đồng:

- `maxBytes` là giới hạn **bao gồm**: 10 byte vẫn được chấp nhận.
- `copied` là tổng số byte đã được chuyển đến output thành công.
- Chỉ đọc tối đa lượng byte còn trong budget.
- Khi đạt budget, đọc thêm **một byte** để phát hiện input dài hơn; không ghi byte thăm dò vào output.
- Nếu vượt budget, ném ngoại lệ và **coi output đã ghi trước đó là bản không hoàn chỉnh**, phải rollback/xóa hoặc không publish.
- Không dùng cách ép `(int) maxBytes` khi giá trị có thể lớn hơn `Integer.MAX_VALUE`; đếm tổng bằng `long` và giới hạn kích thước mỗi lượt đọc bằng buffer `int`.

## 7. Ví dụ Java 17 chạy được: `boundedCopy` không giữ toàn bộ input trong RAM

Chương trình dưới đây dùng mảng 8 KiB và không phân bổ bộ nhớ tỷ lệ với toàn bộ kích thước input. Nó chạy trên `ByteArrayInputStream` để kết quả có thể kiểm tra chính xác, nhưng thuật toán cũng có thể dùng với input là network/file stream. Khi input vượt hạn mức, output có thể đã nhận **phần tiền tố hợp lệ**: ví dụ thể hiện điều này để người học không nhầm ngoại lệ là rollback tự động.

**Tệp `BoundedCopyDemo.java`:**

```java
import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.nio.charset.StandardCharsets;

public class BoundedCopyDemo {
    static long copyBounded(InputStream input, OutputStream output,
                            long maxBytes) throws IOException {
        if (maxBytes < 0) {
            throw new IllegalArgumentException("maxBytes < 0");
        }

        byte[] buffer = new byte[8192];
        long copied = 0;

        while (copied < maxBytes) {
            int wanted = (int) Math.min(
                    (long) buffer.length, maxBytes - copied);
            int n = input.read(buffer, 0, wanted);

            if (n == -1) {
                return copied;
            }
            if (n == 0) {
                throw new IOException("Input made no progress");
            }

            output.write(buffer, 0, n);
            copied += n;
        }

        // Đã chạm budget: kiểm tra đúng một byte tiếp theo.
        if (input.read() != -1) {
            throw new IOException(
                    "Input exceeds " + maxBytes + " bytes");
        }
        return copied;
    }

    public static void main(String[] args) throws IOException {
        ByteArrayOutputStream accepted = new ByteArrayOutputStream();
        byte[] exactlyTen =
                "ABCDEFGHIJ".getBytes(StandardCharsets.US_ASCII);

        long size = copyBounded(
                new ByteArrayInputStream(exactlyTen),
                accepted, 10);

        System.out.println("Accepted bytes: " + size);
        System.out.println("Accepted data: "
                + accepted.toString(StandardCharsets.US_ASCII));

        ByteArrayOutputStream partial = new ByteArrayOutputStream();
        byte[] eleven =
                "ABCDEFGHIJK".getBytes(StandardCharsets.US_ASCII);

        try {
            copyBounded(new ByteArrayInputStream(eleven),
                    partial, 10);
            System.out.println("Unexpected acceptance");
        } catch (IOException ex) {
            System.out.println("Rejected: " + ex.getMessage());
            System.out.println(
                    "Partial output bytes: " + partial.size());
        }

        long empty = copyBounded(
                new ByteArrayInputStream(new byte[0]),
                new ByteArrayOutputStream(), 0);
        System.out.println("Zero limit, empty input: " + empty);
    }
}
```

Lệnh biên dịch/chạy:

```bash
javac BoundedCopyDemo.java
java BoundedCopyDemo
```

**Stdout chính xác khi chương trình thành công:**

```text
Accepted bytes: 10
Accepted data: ABCDEFGHIJ
Rejected: Input exceeds 10 bytes
Partial output bytes: 10
Zero limit, empty input: 0
```

Phân tích:

1. Input đúng 10 byte: vòng lặp đọc 10 byte; lần `input.read()` thăm dò sau đó trả `-1` nên chấp nhận.
2. Input 11 byte: vòng lặp chỉ ghi 10 byte; lần thăm dò trả về byte thứ 11 nên ném `IOException`. Output đã giữ **10 byte đầu** — phải quản lý rollback.
3. Khi `maxBytes=0` và input rỗng, vòng lặp không chạy, lần thăm dò trả EOF nên trả `0`.
4. Dù input lớn bao nhiêu, **mảng làm việc vẫn chỉ 8 KiB**; biến đếm dùng `long`.
5. Đoạn kiểm tra `n==0` tránh vòng lặp không tiến triển do implementation vi phạm/ngoài dự kiến; theo hợp đồng chuẩn `InputStream.read(byte[], off, len)` với `len>0`, kết quả thông thường là số byte dương hoặc `-1`, không phải 0.

**Giới hạn của ví dụ:** bộ đệm đọc cố định không có nghĩa toàn bộ ứng dụng chỉ dùng 8 KiB: output ở đây là `ByteArrayOutputStream` nên vẫn giữ dữ liệu đã chấp nhận lên đến 10 byte. Khi input từ mạng và output là file tạm, phần tăng bộ nhớ có thể nhỏ hơn nhiều; muốn thực sự giới hạn RAM phải kiểm soát **cả nguồn, bộ đệm trung gian và đích**.

## 8. Output một phần: phải có bước commit/rollback

Nếu phương thức sao chép ghi thẳng vào tên file chính thức, khi input vượt budget nó có thể để lại file chứa phần đầu dữ liệu. Người dùng hoặc tiến trình khác có thể tưởng file ấy đã hoàn chỉnh.

Một chiến lược an toàn hơn:

```text
Nguồn không tin cậy
       |
       v
bounded copy (kiểm tra số byte thực)
       |
       v
tệp tạm thuộc quyền ứng dụng
       |
       +-- Thất bại/vượt limit --> đóng + xóa tệp tạm
       |
       +-- Thành công ---------> xác thực format/checksum
                                  |
                                  v
                             publish/rename
```

Quy trình đề xuất:

1. Tạo file tạm trong vị trí có hạn mức và quyền truy cập thích hợp.
2. Ghi vào file tạm trong lúc đọc có giới hạn.
3. Nếu kiểm tra giới hạn, nội dung và cấu trúc thành công thì mới công bố file cho người sử dụng.
4. Nếu có `IOException`, timeout, validation error hoặc request bị hủy, đóng các stream và xóa file tạm trong `finally`.
5. Nếu có cạnh tranh writer, cần chính sách tên, overwrite và đồng bộ hóa phù hợp.
6. `Files.move(..., ATOMIC_MOVE)` có thể được hỗ trợ tùy filesystem/provider; không giả định move atomically luôn khả dụng.

**Quy tắc:** “đã đọc không quá X byte” không đồng nghĩa “đã xử lý thành công”. Dữ liệu có thể thiếu định dạng, thiếu checksum, giải nén lỗi, hoặc bị ngắt ở giữa. Chỉ ghi trạng thái **COMPLETED** sau khi các điều kiện tương ứng thực sự thành công.

## 9. Ví dụ Java 17: frame có độ dài khai báo, kiểm tra trước khi cấp phát

Nhiều giao thức nhị phân dùng cấu trúc:

```text
[ length: 4-byte signed int ][ payload: length bytes ]
```

Nếu đọc độ dài do client gửi rồi lập tức tạo `new byte[length]`, client có thể khiến server xin mảng rất lớn hoặc dùng số âm. Phải xác thực **trước khi cấp phát**. Phương thức `readNBytes(length)` phù hợp khi `length` đã bị chặn bởi một hạn mức tương đối nhỏ, và phải kiểm tra dữ liệu có đủ đúng số byte hay không.

**Tệp `FrameLimitDemo.java`:**

```java
import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.DataInputStream;
import java.io.DataOutputStream;
import java.io.EOFException;
import java.io.IOException;
import java.nio.charset.StandardCharsets;

public class FrameLimitDemo {
    private static final int MAX_FRAME_BYTES = 8;

    static byte[] readFrame(DataInputStream input) throws IOException {
        int length = input.readInt();
        if (length < 0 || length > MAX_FRAME_BYTES) {
            throw new IOException("Rejected length: " + length);
        }

        byte[] payload = input.readNBytes(length);
        if (payload.length != length) {
            throw new EOFException("Truncated frame");
        }
        return payload;
    }

    static byte[] frame(int declaredLength, byte[] payload)
            throws IOException {
        ByteArrayOutputStream bytes = new ByteArrayOutputStream();
        try (DataOutputStream output = new DataOutputStream(bytes)) {
            output.writeInt(declaredLength);
            output.write(payload);
        }
        return bytes.toByteArray();
    }

    public static void main(String[] args) throws IOException {
        byte[] cat = "CAT".getBytes(StandardCharsets.US_ASCII);

        try (DataInputStream input = new DataInputStream(
                new ByteArrayInputStream(frame(cat.length, cat)))) {
            System.out.println("Accepted: " + new String(
                    readFrame(input), StandardCharsets.US_ASCII));
        }

        try (DataInputStream input = new DataInputStream(
                new ByteArrayInputStream(frame(1_000_000, new byte[0])))) {
            readFrame(input);
        } catch (IOException ex) {
            System.out.println(ex.getMessage());
        }

        try (DataInputStream input = new DataInputStream(
                new ByteArrayInputStream(frame(5, cat)))) {
            readFrame(input);
        } catch (EOFException ex) {
            System.out.println("Rejected: " + ex.getMessage());
        }
    }
}
```

Lệnh chạy:

```bash
javac FrameLimitDemo.java
java FrameLimitDemo
```

**Stdout chính xác:**

```text
Accepted: CAT
Rejected length: 1000000
Rejected: Truncated frame
```

Các tình huống:

- Payload `CAT` dài 3 byte, khai báo 3: được chấp nhận.
- Khai báo 1.000.000 byte trong khi policy chỉ cho 8: bị từ chối **trước khi cấp phát mảng payload**.
- Khai báo 5 byte nhưng thực tế chỉ có 3: `readNBytes(5)` trả mảng 3 byte; ứng dụng ném `EOFException` vì frame bị thiếu.

**Đừng dùng `read(byte[])` một lần rồi mặc định đã đủ frame.** `InputStream.read` có thể trả ít byte hơn số được yêu cầu. `readNBytes(len)` hoặc một vòng lặp đọc đúng số lượng giúp kiểm soát thiếu byte theo hợp đồng.

Nếu giao thức dùng **unsigned 32-bit length**, cần chuyển sang `long` và kiểm tra khoảng hợp lệ mà **không làm tràn `int`** trước khi cấp phát. Hạn mức cấu hình phải là giá trị tin cậy từ server, không phải do client tự quyết.

## 10. Kiểu số và chống tràn khi tính kích thước

Một giới hạn đúng vẫn có thể bị vô hiệu hóa bởi số học sai.

### 10.1. Đừng cộng hai `int` lớn trước khi so sánh

Không nên:

```java
int total = currentBytes + nextBytes;
if (total > maxBytes) {
    throw new IOException("Too large");
}
```

Vì cộng hai `int` có thể **overflow** trước khi so sánh, biến `total` có thể âm hoặc nhỏ hơn dự kiến. Mã là minh họa với các biến tồn tại.

Nếu chỉ xử lý giá trị không âm và `currentBytes <= maxBytes`, có thể dùng phép trừ:

```java
if (nextBytes < 0 || nextBytes > maxBytes - currentBytes) {
    throw new IOException("Limit exceeded");
}
currentBytes += nextBytes;
```

Hoặc sử dụng `Math.addExact(...)` và bắt `ArithmeticException` khi cần cộng chính xác. Dùng `long` cho tổng byte, số record và offset lớn, nhưng vẫn phải ngăn tràn `long` nếu input/metadata không đáng tin.

### 10.2. Đừng ép xuống `int` không kiểm tra

```java
long declaredLength = input.readLong();
byte[] buffer = new byte[(int) declaredLength]; // Sai nếu long quá lớn.
```

Một `long` lớn khi ép sang `int` có thể bị cắt bớt bit hoặc thành số âm. Chỉ ép sau khi xác thực `0 <= length <= configuredMaximum` và `length <= Integer.MAX_VALUE`. Với file lớn, đọc theo từng khối hoặc lưu ra đĩa thay vì cấp mảng chứa toàn bộ.

### 10.3. Chỉ số phần tử và tổng byte phải cùng được kiểm tra

Ví dụ 10.000 phần tử, mỗi phần 10 KiB, có thể chiếm gần 100 MiB trước overhead dù một phần nhỏ. Nếu định dạng chứa nhiều header/record, cần giới hạn **cả số lượng và kích thước mỗi phần**.

## 11. File size và khả năng thay đổi trong lúc đọc

Với file nguồn:

```java
long announcedSize = Files.size(path);
if (announcedSize > MAX_BYTES) {
    throw new IOException("File too large");
}
```

Đây là bước *early rejection* tốt khi metadata có sẵn. Nhưng từ lúc kiểm tra đến lúc `Files.newInputStream(path)` hoặc `Files.readAllBytes(path)`, file có thể bị tiến trình khác thay đổi. Cũng có các file đặc biệt hoặc filesystem mà hành vi size không tương ứng một luồng dữ liệu ổn định.

**Cách chắc chắn hơn:** kiểm tra size để từ chối sớm, **vẫn** áp dụng bộ đếm giới hạn trong vòng đọc để cưỡng chế chính sách trên số byte thực nhận. Nếu yêu cầu nhất quán cao, phối hợp locking/snapshot/versioning, hoặc đọc từ handle có đặc tính phù hợp; không coi `Files.size` là giao dịch chặn writer khác.

Một file vừa vượt hạn mức có thể làm chương trình phát hiện ở lần đọc cuối; do đó chính sách tệp tạm, cleanup và rollback vẫn cần thiết kể cả sau precheck.

## 12. GZIP/ZIP: kiểm tra **dữ liệu sau giải nén**

Đối với dữ liệu nén, size của phần nén **không phải** ngân sách RAM hoặc output sau giải nén.

Ví dụ một luồng chứa nhiều byte lặp lại có thể nén thành file rất nhỏ nhưng giải nén thành lượng byte lớn. Nếu server chỉ kiểm tra tổng byte HTTP body trước khi tạo `GZIPInputStream` hoặc `ZipInputStream`, nó vẫn có nguy cơ bị **decompression bomb/zip bomb**.

Phải áp dụng giới hạn ở **phía sau bước giải nén**:

```text
Đầu vào nén
    |
    | giới hạn compressed bytes / thời gian / nguồn
    v
GZIPInputStream hoặc ZipInputStream
    |
    | giới hạn decompressed bytes thực đọc
    v
bounded parser / tệp tạm / output
    |
    v
validate rồi publish
```

Ngoài kích thước giải nén, nên giới hạn số entry ZIP, kích thước mỗi entry, tổng kích thước nhiều entry, độ sâu nested archive, số file giải nén và dung lượng đĩa. Ratio nén/giải nén có thể là một **tín hiệu bổ sung**, không thay cho tổng byte thực tế.

`ZipEntry.getSize()` có thể là `-1` hoặc không đáng tin ở thời điểm đọc, nên chỉ sử dụng để từ chối sớm khi phù hợp; **đếm byte `ZipInputStream.read(...)` thực tế** mới là lớp kiểm soát chính.

## 13. Ví dụ Java 17: giới hạn GZIP theo byte đã giải nén

Chương trình sau tạo một GZIP nhỏ trong bộ nhớ, sau đó giải nén bằng `GZIPInputStream`. Mọi byte đi ra từ decoder đều được tính vào giới hạn qua vòng đọc. Ví dụ dùng limit 10 byte: text `Java` hợp lệ, nhưng chuỗi 12 ký tự `X` vượt hạn mức và bị từ chối.

**Tệp `GzipLimitDemo.java`:**

```java
import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.util.zip.GZIPInputStream;
import java.util.zip.GZIPOutputStream;

public class GzipLimitDemo {
    static byte[] gzip(byte[] data) throws IOException {
        ByteArrayOutputStream sink = new ByteArrayOutputStream();
        try (GZIPOutputStream output = new GZIPOutputStream(sink)) {
            output.write(data);
        }
        return sink.toByteArray();
    }

    static String decodeBounded(byte[] compressed, int maxBytes)
            throws IOException {
        ByteArrayOutputStream result = new ByteArrayOutputStream();

        try (GZIPInputStream input = new GZIPInputStream(
                new ByteArrayInputStream(compressed))) {

            byte[] buffer = new byte[4];
            int total = 0;
            int n;

            while ((n = input.read(buffer)) != -1) {
                if (n == 0) {
                    throw new IOException("No read progress");
                }
                if (n > maxBytes - total) {
                    throw new IOException("Decompressed limit exceeded");
                }
                total += n;
                result.write(buffer, 0, n);
            }
        }
        return result.toString(StandardCharsets.UTF_8);
    }

    public static void main(String[] args) throws IOException {
        byte[] small = gzip(
                "Java".getBytes(StandardCharsets.UTF_8));
        System.out.println("Accepted: "
                + decodeBounded(small, 10));

        byte[] large = gzip(
                "XXXXXXXXXXXX".getBytes(StandardCharsets.US_ASCII));

        try {
            System.out.println(decodeBounded(large, 10));
        } catch (IOException ex) {
            System.out.println("Rejected: " + ex.getMessage());
        }
    }
}
```

Chạy:

```bash
javac GzipLimitDemo.java
java GzipLimitDemo
```

**Stdout khi thành công:**

```text
Accepted: Java
Rejected: Decompressed limit exceeded
```

**Nhận xét:**

- Chương trình đếm **byte giải nén**, không phải `compressed.length`.
- Trong `decodeBounded`, mảng làm việc chỉ 4 byte nhằm minh họa các lần đọc nhiều chunk.
- `ByteArrayOutputStream` tích lũy output nhưng bị giới hạn gián tiếp bởi chính sách 10 byte; với hạn mức lớn hơn, nên chuyển trực tiếp sang parser hoặc file tạm.
- `maxBytes` trong production phải được kiểm tra là số không âm và thuộc khoảng cấu hình được phép trước khi gọi; ở đây là hằng số đáng tin 10.
- Chỉ có giới hạn decompressed bytes thì **chưa đủ** nếu luồng nén không kết thúc hoặc decoder tiêu tốn nhiều CPU; phải bổ sung timeout và tổng kích thước input nén.

Không dùng `GZIPInputStream.readAllBytes()` trên nội dung nén từ nguồn không tin cậy rồi **mới** kiểm tra kích thước mảng đầu ra. Khi đến được bước kiểm tra, tài nguyên đã có thể bị tiêu thụ quá mức.

## 14. Kiểm soát ZIP theo số entry và tổng byte giải nén

ZIP có **nhiều entry**. Nếu chỉ giới hạn 1 MiB mỗi entry nhưng archive chứa hàng chục nghìn entry, tổng dữ liệu vẫn rất lớn. Vì vậy dùng các bộ đếm:

- `maxEntries`: số entry tối đa.
- `maxBytesPerEntry`: số byte giải nén tối đa của từng entry.
- `maxTotalExpandedBytes`: tổng byte giải nén tối đa của toàn archive.
- `maxDepth`: nếu cho phép ZIP lồng trong ZIP hay các dạng container lồng nhau.
- `maxOutputFiles` và tổng dung lượng disk khi giải nén ra file.

Mỗi lần đọc một chunk dài `n`:

```java
if (n > maxEntryBytes - entryBytes
        || n > maxTotalBytes - totalBytes) {
    throw new IOException("Expanded ZIP limit exceeded");
}

entryBytes += n;
totalBytes += n;
```

Đây là đoạn minh họa, giả định counters/budgets đã kiểm tra là không âm và counters chưa vượt budget. Dùng so sánh dựa trên **phép trừ** để tránh overflow. Không cần giữ toàn bộ entry trong RAM chỉ để biết có vượt limit hay không.

### Ví dụ Java 17: từ chối ZIP khi tổng byte vượt giới hạn

**Tệp `ZipExpansionLimitDemo.java`:**

```java
import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.util.zip.ZipEntry;
import java.util.zip.ZipInputStream;
import java.util.zip.ZipOutputStream;

public class ZipExpansionLimitDemo {
    static byte[] createZip(String body) throws IOException {
        ByteArrayOutputStream sink = new ByteArrayOutputStream();
        try (ZipOutputStream output = new ZipOutputStream(sink)) {
            output.putNextEntry(new ZipEntry("item.txt"));
            output.write(body.getBytes(StandardCharsets.US_ASCII));
            output.closeEntry();
        }
        return sink.toByteArray();
    }

    static int inspect(byte[] bytes, int maxEntries,
                       int maxPerEntry, int maxTotal)
            throws IOException {
        if (maxEntries < 0 || maxPerEntry < 0 || maxTotal < 0) {
            throw new IllegalArgumentException("Negative budget");
        }

        int entries = 0;
        int total = 0;

        try (ZipInputStream input = new ZipInputStream(
                new ByteArrayInputStream(bytes))) {
            ZipEntry entry;
            byte[] buffer = new byte[4];

            while ((entry = input.getNextEntry()) != null) {
                entries++;
                if (entries > maxEntries) {
                    throw new IOException("Entry count exceeded");
                }

                int entryBytes = 0;
                int n;
                while ((n = input.read(buffer)) != -1) {
                    if (n == 0) {
                        throw new IOException("No read progress");
                    }
                    if (n > maxPerEntry - entryBytes
                            || n > maxTotal - total) {
                        throw new IOException(
                                "Expanded ZIP limit exceeded");
                    }

                    entryBytes += n;
                    total += n;
                }
                input.closeEntry();
            }
        }

        return total;
    }

    public static void main(String[] args) throws IOException {
        byte[] small = createZip("CAT");
        System.out.println("Accepted bytes: "
                + inspect(small, 2, 10, 10));

        byte[] large = createZip("ABCDEFGHIJKL");
        try {
            inspect(large, 2, 10, 10);
        } catch (IOException ex) {
            System.out.println("Rejected: " + ex.getMessage());
        }
    }
}
```

Lệnh:

```bash
javac ZipExpansionLimitDemo.java
java ZipExpansionLimitDemo
```

**Stdout khi chương trình thành công:**

```text
Accepted bytes: 3
Rejected: Expanded ZIP limit exceeded
```

Điểm chính: chương trình đếm bytes **sau giải nén** và không dựa vào `ZipEntry.getSize()`. Nó cũng giới hạn entry count và từng entry riêng biệt. Ví dụ tạo ZIP trong RAM để dễ tái hiện; trong ứng dụng thật có thể đọc từ `Files.newInputStream` hoặc nguồn mạng đã bị giới hạn, và tránh giải nén tất cả entry vào một `ByteArrayOutputStream`.

**Chưa phải extractor production**: chương trình trên chỉ *kiểm tra và đếm*, không ghi file. Nếu phát triển thành extractor, phải chống **Zip Slip**, kiểm soát symlink, path traversal, quyền file, số lượng file, dung lượng đĩa, timeouts, nested archives và cleanup khi thất bại.

## 15. Byte limit, character limit và Unicode không giống nhau

Một văn bản có ít ký tự không nhất thiết có ít byte. Ví dụ UTF-8 mã hóa ASCII bằng 1 byte, nhưng nhiều ký tự có dấu dùng hơn 1 byte; emoji có thể dùng 4 byte. Java `String.length()` trả số **UTF-16 code units**, không phải số UTF-8 bytes và cũng không hẳn bằng số ký tự mà người dùng nhìn thấy (*grapheme clusters*).

Ví dụ minh họa:

```java
String text = "A😀B";

System.out.println(text.length()); // 4 UTF-16 code units
System.out.println(text.codePointCount(0, text.length())); // 3
System.out.println(text.getBytes(StandardCharsets.UTF_8).length); // 6
```

Với Java source mã hóa UTF-8, `A` và `B` là hai byte ASCII, emoji dùng bốn byte UTF-8. Tổng là **6 byte**, **3 Unicode code points**, nhưng `String.length()==4`.

**Nên đặt giới hạn ở đúng lớp:**

1. **Raw input byte limit**: trước khi decode, bảo vệ network/file/memory.
2. **Decoded text length limit**: sau khi decode, bảo vệ parser và logic text.
3. **Số dòng, số token, nesting depth**: bảo vệ cấu trúc dữ liệu.
4. **Output byte limit**: nếu serialize/encode response có thể phình thêm.

Đừng coi `String.length()` là giới hạn byte của HTTP request. Đừng tự động cắt `byte[]` theo limit nếu có thể chia đôi một UTF-8 sequence hoặc dữ liệu nhị phân cần tính toàn vẹn. Khi vượt giới hạn, **từ chối toàn bộ payload** hoặc dùng giao thức stream hỗ trợ phân đoạn rõ ràng.

### Charset decoder nghiêm ngặt

Nếu dữ liệu bắt buộc là UTF-8 hợp lệ, dùng decoder có `CodingErrorAction.REPORT` khi cần từ chối chuỗi byte không hợp lệ, thay vì âm thầm thay thế bằng ký tự khác. Có thể sử dụng `CharsetDecoder` hoặc API parser tương ứng, và kiểm soát byte budget trước khi decode. Với text streaming, giữ lại phần byte dở dang của ký tự giữa các chunk — không tự decode từng chunk độc lập bằng `new String(buffer, 0, n, UTF_8)` rồi ghép nếu chunk có thể kết thúc giữa một chuỗi UTF-8.

## 16. Bộ nhớ đỉnh có thể lớn hơn kích thước input

Đọc input 5 MiB vào `byte[]`, giải mã thành `String`, parse thành cây object và giữ lại bản sao trong cache có thể giữ **nhiều biểu diễn cùng lúc**. Hơn nữa:

- `byte[]` có object header và alignment.
- `ByteArrayOutputStream` có thể giữ internal array và `toByteArray()` tạo bản sao.
- `String` và decoder dùng biểu diễn/mảng riêng.
- JSON/XML parser có thể tạo nhiều object nhỏ, map, list, string, node metadata.
- Compression/decompression có buffer native hoặc nội bộ.
- Thư viện có thể cache hoặc giữ tham chiếu khiến object sống lâu hơn request.
- Direct `ByteBuffer` và memory mapping dùng tài nguyên ngoài heap, không hiện rõ chỉ bằng metric heap.

Do đó **giới hạn byte input không phải giới hạn heap tiêu thụ theo tỉ lệ 1:1**. Cần đo **peak retained + temporary allocations** với workload thật, tính margin cho GC/runtime và số request đồng thời.

### Ví dụ ngân sách ở mức thiết kế

Giả sử mỗi tác vụ giữ:
- tối đa 4 MiB input đã được chấp nhận trong một mảng;
- tối đa 4 MiB output trung gian;
- thêm overhead parser và runtime.

Nếu 50 tác vụ như vậy đồng thời tồn tại, chỉ hai mảng 4 MiB mỗi tác vụ đã có thể chiếm khoảng **400 MiB**, chưa tính overhead. Thay vì tối đa 50 request cùng parse trong heap, hệ thống có thể dùng semaphore giới hạn số tác vụ nặng hoặc stream dữ liệu sang file tạm.

Đây là con số minh họa cho kỹ thuật tính ngân sách, **không phải cấu hình khuyến nghị chung**. Chọn hạn mức theo heap, memory container, workload thực và SLO.

## 17. Giới hạn concurrency và backpressure

Một request 1 MiB có thể nhỏ, nhưng nếu cho phép 50.000 request giữ mỗi request một bản sao 1 MiB trong RAM, tổng bộ nhớ sẽ vượt xa giới hạn của hầu hết tiến trình ứng dụng.

Cần **hai lớp admission control**:

- **Per-request limit:** byte/record/depth/time của một request.
- **Global limit:** tổng request đang hoạt động, byte in-flight, worker tasks, kết nối đang chờ hoặc dung lượng hàng đợi.

Kỹ thuật phổ biến:

1. Dùng `Semaphore` để giới hạn số request cùng giữ bộ nhớ lớn hoặc cùng giải nén.
2. Dùng hàng đợi có độ dài cố định và từ chối sớm khi đầy.
3. Tạm ngừng đọc từ upstream khi downstream không xử lý kịp (*backpressure*).
4. Tách bộ nhớ làm việc nhỏ với file spool có quota đĩa và TTL cleanup.
5. Giải phóng tài nguyên bằng `try-with-resources`, hủy tác vụ khi timeout/cancellation và cập nhật metrics.
6. Dùng công cụ đo và cảnh báo khi tiến gần hạn mức; **không chờ `OutOfMemoryError` mới xử lý**.

Với Java NIO non-blocking, `SocketChannel.read(ByteBuffer)` có thể trả 0 khi chưa có dữ liệu; việc chặn số byte đã nhận vẫn cần đặt ở **state của từng kết nối**, không chỉ dựa vào kích thước buffer. `ByteBuffer.clear()` tái sử dụng buffer nhưng **không xóa tổng byte đã nhận**; ứng dụng phải duy trì counter riêng xuyên nhiều lần read.

## 18. Timeout và input không bao giờ kết thúc

Một giới hạn byte **không chặn được client gửi rất chậm** (ví dụ mỗi phút chỉ gửi vài byte) hoặc một nguồn treo trước EOF. Vì vậy cần chính sách thời gian:

- **Connect timeout**: tối đa chờ thiết lập kết nối.
- **Read idle timeout**: tối đa thời gian không nhận tiến độ.
- **Overall deadline**: tổng thời gian cho toàn yêu cầu, kể cả chậm nhưng vẫn có tiến độ.
- **Parsing/decompression budget**: giới hạn CPU/time sau khi nhận dữ liệu.
- **Cancellation**: khi người dùng hủy hoặc deadline hết, dừng luồng xử lý và cleanup.

Không dùng vòng lặp `while (read(...) == 0)` không điều kiện với channel non-blocking; đó là **busy spin**. Cần readiness/`Selector`, backoff phù hợp hoặc lịch xử lý theo sự kiện. Với `InputStream` blocking, việc cắt deadline có thể đòi hỏi timeout trên socket/transport hoặc việc đóng/hủy từ thread khác theo API cụ thể; `Thread.interrupt()` không có tác dụng giống nhau với mọi nguồn I/O.

**Giới hạn tổng số byte và timeout là hai trục khác nhau**, cần phối hợp.

## 19. EOF, read một phần và trách nhiệm parser

`InputStream.read(byte[])` trả về **số byte thực nhận**, có thể nhỏ hơn kích thước buffer; `-1` biểu thị EOF. Không được giả định một lần đọc đã lấy hết dữ liệu cần thiết.

Với khung thông điệp có kích thước xác định, EOF trước khi đủ byte là **truncated input**. Với upload không có kích thước xác định, EOF có thể là ranh giới kết thúc, nhưng ứng dụng vẫn phải kiểm tra tổng byte <= limit và kiểm tra định dạng hợp lệ.

`DataInputStream.readFully(byte[])` có thể hữu ích nếu đã cấp mảng có kích thước **đã được kiểm tra trước**; nếu EOF sớm, nó ném `EOFException`. Nhưng nó **không tự giới hạn input** nếu bạn cấp mảng theo độ dài không đáng tin.

Một parser tốt phải xác định rõ:
- “Đọc đủ” là bao nhiêu byte?
- Nếu thiếu, hành động từ chối là gì?
- Nếu thừa, có phải lỗi protocol hay phần mở đầu của frame kế tiếp?
- Nếu dữ liệu hợp lệ về kích thước nhưng sai checksum/schema, xử lý ra sao?
- Nếu dữ liệu đến thành nhiều chunk, state nào được giữ và khi nào cleanup?

Đối với streaming nhiều frame, **đừng đọc một byte thăm dò rồi đánh mất nó** nếu byte đó thuộc frame tiếp theo. Kỹ thuật thăm dò một byte của `BoundedCopyDemo` phù hợp cho **một input được kỳ vọng kết thúc tại EOF**. Với giao thức nhiều frame, dựa trên ranh giới đã khai báo và giữ trạng thái reader cho frame kế tiếp.

## 20. Giới hạn toàn pipeline, không chỉ một thành phần

Một luồng xử lý thực có thể đi qua:

```text
HTTP body / socket
      |
      v
transport request limit
      |
      v
decompression / decoding
      |
      v
expanded-byte and character limit
      |
      v
parser depth / item count limit
      |
      v
business validation
      |
      v
temporary file / output quota
      |
      v
commit / publish
```

Ví dụ HTTP body giới hạn 10 MiB nhưng cho phép một payload ZIP trong đó:

- 10 MiB chỉ kiểm soát **input nén**.
- Một ZIP 10 MiB có thể có **số entry rất lớn** hoặc giải nén thành hàng gigabyte.
- Parser sau giải nén có thể tạo cây object nhiều lần lớn hơn bytes gốc.
- Nhiều request cùng lúc có thể cộng dồn chi phí.

Một tầng kiểm soát thất bại không nên khiến mọi tầng sau hoàn toàn tin dữ liệu. **Defense in depth** là giới hạn bằng những bộ đếm độc lập, ở đúng điểm chuyển đổi dữ liệu.

## 21. Những lỗi thiết kế thường gặp

| Sai lầm | Hậu quả | Cách xử lý |
| --- | --- | --- |
| Dùng `readAllBytes()` trên input không giới hạn | Có thể tiêu thụ heap lớn/OOME | Bounded stream và limit bytes |
| Dùng `InputStream.available()` như tổng kích thước | Phán đoán sai, đọc thiếu | Đếm byte trả về từ `read` |
| Tin tuyệt đối `Content-Length` | Client có thể khai báo sai/không khai báo | Check sớm và cưỡng chế khi đọc |
| `new byte[untrustedLength]` trước khi validate | Cấp phát lớn/âm/overflow | Kiểm tra độ dài trước |
| Dùng `readNBytes(max)` rồi kết luận input không quá max | Có thể còn byte phía sau | Probe EOF hoặc frame protocol |
| Dùng `transferTo(ByteArrayOutputStream)` không limit | Giữ toàn bộ data trên heap | Bounded copy hoặc bounded sink |
| Kiểm tra limit sau khi tích lũy hết bytes | Đã tiêu thụ tài nguyên quá mức | Kiểm tra ở mỗi chunk |
| Dùng `int` cho tổng byte lớn rồi cộng trực tiếp | Overflow làm bypass limit | Dùng `long` và phép so sánh dựa vào trừ |
| Chỉ giới hạn kích thước file ZIP/GZIP nén | Có thể giải nén thành nhiều GB | Giới hạn bytes sau giải nén |
| Chỉ giới hạn per-entry ZIP | Nhiều entry cộng dồn quá lớn | Giới hạn tổng và số entry |
| Chỉ giới hạn byte thô | Parser có thể tạo object graph rất lớn | Thêm item/depth/char limits |
| Một request tối đa nhỏ nhưng concurrency không giới hạn | Tổng heap vẫn tăng không kiểm soát | Admission control/semaphore/queue |
| Vượt limit nhưng giữ file output một phần | Có thể publish dữ liệu hỏng | Tệp tạm + commit/rollback |
| Chỉ có byte cap, không có deadline | Slow client chiếm tài nguyên lâu | Idle timeout và overall deadline |
| Cắt UTF-8 ở ranh giới byte và giải mã chunk riêng | Ký tự bị lỗi/trả replacement char | Stateful decoder và validation |
| Nghĩ `ByteBuffer.clear()` đặt lại byte budget | Có thể bypass limit qua nhiều lần read | Counter riêng cho request/connection |
| Bắt `OutOfMemoryError` rồi tiếp tục bình thường | Tiến trình có thể đang ở trạng thái suy kiệt | Cưỡng chế limit từ đầu, giám sát tài nguyên |
| Không đóng stream khi có lỗi | Rò rỉ file descriptor/temp files | `try-with-resources` và cleanup trong `finally` |

## 22. Bài tập tự kiểm tra

**Câu 1.** API nhận tối đa 1024 byte. `input.readNBytes(1024)` trả một mảng đúng 1024 byte. Có thể khẳng định input hợp lệ về kích thước không?

**Đáp án:** Chưa. Input có thể còn byte thứ 1025. Với payload phải kết thúc ở EOF, đọc thăm dò thêm một byte và từ chối nếu có. Với giao thức nhiều frame, không tiêu thụ byte của frame tiếp theo một cách tùy tiện; phải dùng framing đúng.

**Câu 2.** Một file ZIP có kích thước 1 MiB và chứa 100 entry, mỗi entry giải nén thành 2 MiB. Chỉ kiểm tra file ZIP <= 5 MiB có an toàn không?

**Đáp án:** Không. Tổng dữ liệu giải nén có thể khoảng 200 MiB. Cần giới hạn kích thước **nén, từng entry, tổng byte giải nén, số entry và tài nguyên xử lý**.

**Câu 3.** Có 100 request đồng thời, mỗi request giữ mảng input 4 MiB và output 4 MiB. Riêng hai mảng đó chiếm bao nhiêu?

**Đáp án:** Khoảng **800 MiB**, chưa tính overhead và các biểu diễn trung gian. Per-request cap không thay cho concurrency limit.

**Câu 4.** Tại sao `available()==0` không có nghĩa EOF?

**Đáp án:** `available` chỉ ước tính byte có thể đọc không chặn; một socket chưa nhận dữ liệu có thể trả 0 nhưng vẫn sẽ nhận thêm byte sau đó. EOF cần được xác định theo kết quả `read` và giao thức.

**Câu 5.** Nếu pipeline streaming dùng buffer 8 KiB rồi ghi vào file tạm không có quota, pipeline đã hoàn toàn an toàn về resource exhaustion chưa?

**Đáp án:** Chưa. Heap làm việc có thể nhỏ, nhưng file tạm có thể lớn không giới hạn, thời gian/CPU có thể không giới hạn, và nhiều request có thể chiếm hết đĩa. Cần byte limit, disk quota, timeout, concurrency cap và cleanup.

**Câu 6.** Vì sao phải kiểm tra `n > max - current` thay vì chỉ `current + n > max`?

**Đáp án:** Kiểm tra bằng trừ tránh overflow trong phép cộng, miễn `current` và `max` đã được xác thực và `current<=max`.

**Câu 7.** Một chuỗi Java có `text.length()==4` nhưng UTF-8 có 6 byte. Có mâu thuẫn không?

**Đáp án:** Không. `String.length()` đếm UTF-16 code units; UTF-8 là biểu diễn byte. Byte cap phải đo ở tầng byte, character cap phải đo ở tầng text theo quy ước mong muốn.

## 23. Checklist triển khai thực tế

Trước khi nhận input:

1. Định nghĩa đơn vị của từng giới hạn: **byte thô**, **byte đã giải nén**, **ký tự**, **số record**, **thời gian**, **bộ nhớ**, **đĩa**.
2. Đặt giá trị server-side đáng tin, không cho client tự nới limit.
3. Đặt giới hạn đồng thời của tác vụ cần cấp phát nhiều bộ nhớ.
4. Xác định nguồn nào có metadata đáng tin và cách từ chối sớm.

Trong khi đọc/giải mã:

1. Đọc theo **chunk có kích thước cố định**, không giữ cả input nếu không cần.
2. Cộng dồn **số byte thực nhận**, giới hạn trước khi ghi/chấp nhận thêm.
3. Kiểm tra độ dài khai báo trước `new byte[n]` hoặc `readNBytes(n)`.
4. Giới hạn thêm dữ liệu **sau giải nén** và số entry/record/depth.
5. Xử lý partial read, EOF sớm, idle timeout và tổng deadline.
6. Theo dõi request-level state qua mọi lần read; không đặt lại chỉ vì tái sử dụng buffer.

Khi hoàn tất hoặc thất bại:

1. Kiểm tra dữ liệu đã đủ và hợp lệ theo schema/giao thức.
2. Chỉ publish artifact sau khi mọi kiểm tra thành công.
3. Đóng stream/channel, xóa file tạm, giải phóng semaphore/quota.
4. Ghi metrics: bytes accepted/rejected, bộ nhớ đỉnh, temp disk, timeout, overflow, số request đồng thời.
5. Test ranh giới: **0**, **limit−1**, **limit**, **limit+1**, metadata âm/cực lớn, truncated input, compressed bomb, nhiều request đồng thời và nguồn đọc chậm.

## 24. Tổng kết

Giới hạn kích thước đầu vào là **hợp đồng tài nguyên**, không chỉ là kiểm tra một trường header. Trong Java I/O:

- **Đừng gọi `readAllBytes` tùy tiện trên nguồn không tin cậy**. Ưu tiên đọc theo chunk và đếm byte thực tế.
- **Đừng tin `available()` hoặc metadata** để suy ra tổng lượng dữ liệu; chúng chỉ có vai trò hỗ trợ.
- **Đừng cấp phát trước khi kiểm tra length**; xử lý overflow, độ dài âm và dữ liệu thiếu.
- **Kiểm tra đúng byte budget**, gồm trường hợp bằng limit và vượt limit đúng một byte.
- **Giới hạn sau giải nén** ZIP/GZIP, cùng số entry và tổng byte toàn archive.
- **Tính ngân sách đồng thời và peak memory**, không chỉ giới hạn từng request.
- **Xử lý lỗi theo transactional workflow**: output tạm → validate → publish; lỗi → cleanup.
- **Bổ sung deadline, disk quota và parser limits**, bởi mỗi tài nguyên có một con đường bị khai thác khác nhau.

Một thiết kế an toàn bảo đảm rằng **đầu vào vượt chính sách bị từ chối trước khi tài nguyên tương ứng tăng không kiểm soát**, và ngay cả khi có lỗi, ứng dụng vẫn biết cách giải phóng các tài nguyên đã sử dụng.

**Tài liệu Java SE 17:**

- [InputStream](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/InputStream.html) — `read`, `readAllBytes`, `readNBytes`, `available`, `transferTo`.
- [Files](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html) — `size`, `newInputStream`, `readAllBytes`, `createTempFile`, `move`.
- [DataInputStream](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/DataInputStream.html) — `readInt` và `readFully`.
- [GZIPInputStream](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/zip/GZIPInputStream.html) và [ZipInputStream](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/zip/ZipInputStream.html).
- [ByteArrayOutputStream](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/ByteArrayOutputStream.html), [ByteBuffer](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/ByteBuffer.html), [CharsetDecoder](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/charset/CharsetDecoder.html).
