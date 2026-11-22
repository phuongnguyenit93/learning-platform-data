# `skip`, `skipNBytes` và giới hạn khi bỏ qua dữ liệu trong luồng byte Java

Trong Java I/O, đôi khi chương trình cần bỏ qua một đoạn dữ liệu để đọc phần phía sau: bỏ qua header cố định, bỏ qua một trường chưa cần xử lý hoặc tiến tới payload. Hai phương thức thường gặp trên `java.io.InputStream` là `skip(long n)` và `skipNBytes(long n)`. Chúng đều *tiêu thụ/bỏ qua byte từ vị trí hiện tại* nhưng khác nhau về cam kết hoàn thành, kết quả trả về và cách báo lỗi.

Bài này thuộc nhóm **luồng byte** (`InputStream`). Mọi con số `n` bên dưới đều tính bằng **byte**, không phải ký tự, số dòng hay số phần tử Java.

## 1. Hiểu đúng việc “bỏ qua”

Hãy hình dung luồng có các byte `A B C D E F G` và con trỏ đọc đang ở `A`:

```text
Trước:  [A] B  C  D  E  F  G
Bỏ 3 byte:
Sau:     A  B  C [D] E  F  G
```

Ba byte `A`, `B`, `C` đã được tiêu thụ; lần `read()` kế tiếp trả về byte `D`. Dữ liệu đã bỏ qua không được tự động trả lại. Cả hai phương thức không đóng luồng, không trả về nội dung đã bỏ qua và không tạo một vị trí đọc ngẫu nhiên có thể nhảy lùi như `FileChannel.position(...)`.

“Bỏ qua” không đồng nghĩa với “seek nhanh”. Cài đặt `InputStream.skip` mặc định có thể **đọc rồi loại bỏ** byte bằng bộ đệm tạm; một số lớp con dùng cơ chế hiệu quả hơn. Với luồng mạng, luồng giải nén hoặc luồng bọc, việc bỏ qua vẫn có thể phải đọc/xử lý dữ liệu bên dưới và có thể chặn (block).

## 2. `skip(long n)`: yêu cầu bỏ qua, nhận về số byte thực tế

Chữ ký API:

```java
public long skip(long n) throws IOException
```

- `n` là số byte mong muốn bỏ qua.
- Giá trị trả về `long` cho biết **số byte thực tế đã bỏ qua**. Nó có thể nhỏ hơn `n`, thậm chí bằng `0`; không được mặc định rằng kết quả luôn bằng `n`.
- Nguyên nhân bỏ qua thiếu có thể là hết dữ liệu (EOF), đặc tính của lớp con, hoặc điều kiện I/O khác. `skip(n) == 0` **không đủ** để kết luận chắc chắn đã EOF.
- Với `n <= 0`, triển khai mặc định của `InputStream` bỏ qua 0 byte và trả về `0`; lớp con có thể quy định khác cho số âm. Mã ứng dụng nên từ chối `n < 0` nếu nó biểu thị độ dài không hợp lệ.
- Khi xảy ra lỗi I/O, phương thức có thể ném `IOException`. Không giả định vị trí luồng giữ nguyên sau lỗi.

**Quy tắc:** Nếu chỉ cần bỏ qua *tối đa* `n` byte, có thể chấp nhận số lượng ít hơn; luôn dùng giá trị trả về để tính số byte đã thực sự tiêu thụ.

Ví dụ trên `ByteArrayInputStream` chứa ba byte, `skip(5)` chỉ bỏ qua được ba byte và trả về `3`. Lần đọc tiếp theo trả về `-1` vì đã hết luồng. Đây là hành vi của ví dụ cụ thể; không dùng kết quả đó làm cam kết cho mọi loại `InputStream`.

## 3. `skipNBytes(long n)`: yêu cầu bỏ qua đủ số byte

Chữ ký API (có từ **Java 12**, sử dụng được trong Java 17+):

```java
public void skipNBytes(long n) throws IOException
```

- Nếu hoàn thành bình thường, phương thức đã bỏ qua đúng `n` byte theo hợp đồng API; không có giá trị trả về.
- Nếu gặp EOF trước khi bỏ qua đủ `n` byte, nó ném `EOFException` (lớp con của `IOException`).
- Nó cũng có thể ném `IOException` nếu I/O lỗi, kết quả `skip` bên dưới bất thường hoặc không thể di chuyển tới vị trí cần thiết.
- Trong triển khai mặc định, `n == 0` hoặc `n < 0` không bỏ qua byte; các lớp con có thể xử lý giá trị âm khác. Nên xác thực `n >= 0` tại ranh giới nghiệp vụ để không im lặng chấp nhận độ dài sai.
- Phương thức có thể chặn cho tới khi bỏ qua đủ byte, gặp EOF hoặc có lỗi; nó không đặt giới hạn thời gian.

Cách hoạt động đáng nhớ của **triển khai mặc định**: gọi `skip(remaining)` lặp lại. Nếu `skip` trả `0`, nó thử `read()` một byte để có tiến triển hoặc phát hiện EOF. Nếu `skip` trả số âm hoặc lớn hơn số byte còn phải bỏ qua, nó ném `IOException`. Lớp con có thể ghi đè để tối ưu.

**Quy tắc:** Dùng `skipNBytes(n)` khi cấu trúc dữ liệu đòi hỏi phải bỏ qua **đúng** `n` byte trước khi đọc phần tiếp theo. Nếu luồng ngắn, lỗi được biểu thị rõ bằng ngoại lệ.

## 4. So sánh nhanh

| Tiêu chí | `skip(n)` | `skipNBytes(n)` |
| --- | --- | --- |
| Hợp đồng | Bỏ qua tối đa theo khả năng triển khai; có thể thiếu | Bỏ qua đủ `n` byte hoặc báo lỗi |
| Giá trị trả về | `long`: số byte đã bỏ qua | `void` |
| EOF trước khi đủ | Có thể trả số nhỏ hơn yêu cầu | Ném `EOFException` |
| Trả `0` khi còn muốn bỏ qua | Có thể xảy ra; bên gọi cần quyết định tiếp tục thế nào | Mặc định thử `read()` để tiến thêm hoặc xác định EOF |
| Dùng khi | Bỏ qua tùy khả năng, cần biết số thực tế | Header/trường bắt buộc đủ độ dài |
| Phiên bản Java | Có từ các phiên bản Java đầu tiên | Có từ Java 12 |

Hai phương thức cùng tiêu thụ luồng tại **vị trí hiện tại**. Không dùng `skipNBytes` trên Java 8/11 vì API này chưa tồn tại ở những phiên bản đó.

## 5. Ví dụ Java 17+ có thể chạy trực tiếp

Lưu thành `SkipExample.java`:

```java
import java.io.ByteArrayInputStream;
import java.io.EOFException;
import java.io.FilterInputStream;
import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;

public class SkipExample {
    public static void main(String[] args) throws IOException {
        byte[] sevenBytes = "ABCDEFG".getBytes(StandardCharsets.US_ASCII);

        // skip trả về số byte thực tế đã bỏ qua.
        try (InputStream in = new ByteArrayInputStream(sevenBytes)) {
            long skipped = in.skip(3);
            System.out.println("skip(3): " + skipped
                    + ", next: " + (char) in.read());
        }

        // skipNBytes đảm bảo đủ độ dài nếu trả về bình thường.
        try (InputStream in = new ByteArrayInputStream(sevenBytes)) {
            in.skipNBytes(3);
            System.out.println("skipNBytes(3) next: " + (char) in.read());
        }

        // Nguồn chỉ có 3 byte, nhưng yêu cầu bỏ qua 5 byte.
        try (InputStream in = new ByteArrayInputStream(new byte[] {10, 20, 30})) {
            System.out.println("skip(5) on 3 bytes: " + in.skip(5));
            System.out.println("next at EOF: " + in.read());
        }

        try (InputStream in = new ByteArrayInputStream(new byte[] {10, 20, 30})) {
            try {
                in.skipNBytes(5);
                System.out.println("unexpected success");
            } catch (EOFException e) {
                System.out.println("skipNBytes(5): EOFException");
            }
        }

        // Lớp bọc này chủ động chỉ cho phép mỗi lần skip tối đa 1 byte.
        try (InputStream in = new OneByteSkippingInputStream(
                new ByteArrayInputStream(sevenBytes))) {
            System.out.println("single skip(3): " + in.skip(3));
            System.out.println("next after one skip: " + (char) in.read());
        }

        try (InputStream in = new OneByteSkippingInputStream(
                new ByteArrayInputStream(sevenBytes))) {
            in.skipNBytes(3);
            System.out.println("next after exact skip: " + (char) in.read());
        }
    }

    private static final class OneByteSkippingInputStream
            extends FilterInputStream {
        OneByteSkippingInputStream(InputStream in) {
            super(in);
        }

        @Override
        public long skip(long n) throws IOException {
            return super.skip(Math.min(n, 1L));
        }
    }
}
```

Biên dịch và chạy trong thư mục chứa tệp:

```bash
javac SkipExample.java
java SkipExample
```

Stdout chính xác:

```text
skip(3): 3, next: D
skipNBytes(3) next: D
skip(5) on 3 bytes: 3
next at EOF: -1
skipNBytes(5): EOFException
single skip(3): 1
next after one skip: B
next after exact skip: D
```

Đoạn cuối cố ý dùng lớp bọc chỉ bỏ qua tối đa 1 byte mỗi lần gọi: `skip(3)` đơn lẻ chỉ tiến một byte nên lần đọc kế là `B`; `skipNBytes(3)` tiếp tục gọi `skip` cho tới khi đã bỏ qua đủ ba byte nên lần đọc kế là `D`. Đây là lý do không được viết `in.skip(3);` rồi mặc định rằng luồng chắc chắn đã tiến ba byte.

## 6. Khi cần số lượng thực tế nhưng muốn thử bỏ qua tới giới hạn

Nếu yêu cầu nghiệp vụ là “bỏ qua nhiều nhất `n` byte, đến EOF thì dừng và **trả tổng byte thực tế**”, một lệnh `skip(n)` riêng lẻ chưa đủ đáng tin do có thể bỏ qua thiếu. Có thể tự viết hàm lặp với biện pháp chống vòng lặp vô hạn khi `skip` trả về `0`.

Phương thức sau có thể đặt trong một lớp Java đang dùng `java.io.InputStream` / `java.io.IOException`:

```java
static long skipUpTo(InputStream in, long requested) throws IOException {
    if (requested < 0) {
        throw new IllegalArgumentException("requested must be >= 0");
    }

    long remaining = requested;

    while (remaining > 0) {
        long skipped = in.skip(remaining);

        if (skipped < 0 || skipped > remaining) {
            throw new IOException("Invalid skip result: " + skipped);
        }

        if (skipped > 0) {
            remaining -= skipped;
            continue;
        }

        // skip(remaining) == 0: thử tiêu thụ 1 byte để tiến lên.
        if (in.read() == -1) {
            break;  // EOF: đã bỏ qua được tối đa bao nhiêu thì trả về bấy nhiêu.
        }
        remaining--;
    }

    return requested - remaining;
}
```

Với nguồn `"ABCDE"`, gọi `skipUpTo(in, 3)` trả `3` và lần `read()` tiếp theo trả byte `D`. Gọi `skipUpTo(in, 8)` trên một luồng mới cùng dữ liệu trả `5` và luồng ở EOF. Mỗi vòng lặp hoặc giảm `remaining`, hoặc thoát, hoặc ném ngoại lệ; nhờ vậy không bị lặp vô hạn khi lớp con trả `0`.

Hàm này phù hợp khi thiếu dữ liệu là kết quả chấp nhận được. Nếu **thiếu byte là lỗi**, dùng `skipNBytes` để thể hiện trực tiếp ý định; đừng viết lại một vòng lặp không cần thiết. Với đầu vào từ mạng hoặc pipe, cả `skipNBytes` lẫn hàm tự viết đều có thể chờ dữ liệu; phải quản lý timeout/cancellation bằng cơ chế phù hợp với nguồn I/O.

## 7. Giới hạn và những hiểu nhầm quan trọng

### 7.1. Số byte khác số ký tự

`InputStream` thao tác trên byte thô. Ví dụ chuỗi `"é"` được mã hóa UTF-8 thường dài **2 byte**; `skip(1)` giữa dữ liệu UTF-8 có thể làm lần giải mã kế tiếp gặp phần giữa của một ký tự và sinh ký tự thay thế hoặc lỗi giải mã. Không dùng `skip` để nhảy “5 ký tự” trong tệp văn bản đa byte. Khi cần xử lý văn bản, hãy dùng `Reader` với charset xác định và đếm theo đơn vị ký tự tương ứng, hoặc thiết kế định dạng có ranh giới byte rõ ràng.

### 7.2. `skip` không chứng minh rằng đã đạt vị trí cần thiết

Đây là lỗi sai:

```java
in.skip(headerLength);             // Bỏ qua thiếu mà không biết!
int firstPayloadByte = in.read();   // Có thể vẫn đang ở giữa header.
```

Nếu header có độ dài bắt buộc, sau khi kiểm tra `headerLength >= 0`, dùng:

```java
in.skipNBytes(headerLength);
int firstPayloadByte = in.read();   // Chỉ chạy khi header đã được bỏ qua đủ.
```

Cả hai đoạn là **mảnh mã minh họa**: `in` là một `InputStream` hợp lệ, `headerLength` là số byte đã xác định và phương thức gọi phải xử lý `IOException`. Nếu file/protocol không có đủ header, đoạn thứ hai ném `EOFException` trước khi xử lý payload.

### 7.3. `available()` không phải “số byte còn lại trong file”

`available()` chỉ là **ước lượng byte có thể đọc hoặc bỏ qua mà không bị block**, không phải kích thước dữ liệu còn lại của mọi loại luồng. Nó có thể trả `0` trong khi dữ liệu sẽ đến sau đó (đặc biệt với luồng mạng). Vì thế không dùng `skip(in.available())` để “đi đến EOF”, cũng không dựa vào `available() == 0` để kết luận đã hết dữ liệu.

### 7.4. Ngoại lệ không tự động hoàn tác những byte đã tiêu thụ

Khi `skipNBytes(100)` phát sinh `EOFException` ở byte thứ 80, những byte đã tiêu thụ **không tự quay lại**. Sau một `IOException` vị trí/ trạng thái luồng có thể không còn đáng tin; xử lý lỗi ở mức bản ghi/giao thức, thường là ngừng parse và đóng luồng. Nếu cần đọc lại, `mark/reset` chỉ dùng khi `markSupported()` là `true` và còn thỏa điều kiện mark; không tự giả định mọi luồng hỗ trợ.

### 7.5. Kết quả và chi phí phụ thuộc lớp `InputStream`

- `ByteArrayInputStream` thao tác trên mảng byte đã nằm trong bộ nhớ; ví dụ ở trên có hành vi rõ ràng, tái lập được.
- `BufferedInputStream` có thể tận dụng dữ liệu đã đệm; việc bọc đệm không biến luồng thành thiết bị truy cập ngẫu nhiên.
- `FileInputStream` và `InputStream` của socket, ZIP hoặc luồng giải nén có cơ chế khác nhau. Không khẳng định `skip` luôn O(1), luôn không block hoặc luôn dừng chính xác tại ranh giới file.
- `skipNBytes` có thể nhiều lần gọi `skip`, và ở triển khai mặc định có thể đọc từng byte khi `skip` trả `0`. Đảm bảo về **số byte** khác với đảm bảo về **hiệu năng**.
- Không dùng `skip` để vượt qua kiểm tra tính hợp lệ của một trường dữ liệu bắt buộc kiểm tra nội dung, checksum hoặc ranh giới bản ghi. Bỏ qua byte chỉ di chuyển trong luồng; nó không xác thực dữ liệu.

### 7.6. Không lẫn `skipNBytes` với `readNBytes` hay seek

- `readNBytes(...)` **lấy dữ liệu vào bộ đệm/mảng**; `skipNBytes(...)` **loại bỏ** dữ liệu khi tiến lên.
- `skip(n)` trả số byte **đã bỏ qua**, trong khi `read()` trả dữ liệu hoặc `-1` ở EOF.
- Nếu cần truy cập vị trí bất kỳ trong tệp và biết offset tuyệt đối, cân nhắc `FileChannel.position(long)` / `SeekableByteChannel` thay vì đọc/bỏ qua tuần tự. Với ZIP hay luồng giải nén, vị trí trong byte đã giải nén không đồng nghĩa offset trong file nén.

## 8. Tình huống áp dụng: header dài cố định trước payload

Giả sử một bản tin nhị phân có 4 byte magic, 2 byte version, tiếp đến payload. Nếu bước này chỉ được phép bỏ qua đúng 6 byte header (vì header đã được xử lý/kiểm tra ở chỗ khác):

```java
static int readFirstPayloadByte(InputStream in) throws IOException {
    in.skipNBytes(6);
    return in.read();   // -1: không có payload sau header.
}
```

Với luồng có ít hơn 6 byte, `skipNBytes(6)` ném `EOFException`, giúp phân biệt **header bị cắt cụt** với **header đầy đủ nhưng payload rỗng** (`read() == -1`). Trong ứng dụng thật, nếu magic/version cần kiểm tra, phải **đọc và xác thực các byte header** thay vì bỏ qua chúng. Nếu độ dài header lấy từ đầu vào không tin cậy, xác thực không âm và giới hạn tối đa trước khi bỏ qua, để tránh chờ lâu hoặc đọc qua lượng dữ liệu không hợp lý.

## 9. Lỗi phổ biến và cách tránh

| Lỗi | Hậu quả | Cách xử lý |
| --- | --- | --- |
| Gọi `skip(n)` và bỏ qua giá trị trả về | Parser đọc lệch trường khi skip thiếu | Dùng `skipNBytes` hoặc cộng dồn số byte thực tế |
| Lặp `while (remaining > 0) remaining -= in.skip(remaining);` | Có thể lặp vô hạn khi `skip` trả `0` | Khi trả `0`, thử `read()` một byte hoặc dừng theo hợp đồng |
| Dùng `available()` làm tổng kích thước còn lại | Cắt thiếu dữ liệu trên stream/ socket | Dựa vào độ dài giao thức, EOF hoặc số byte đọc thực tế |
| Nhầm số ký tự Unicode với byte UTF-8 | Cắt giữa byte của một ký tự | Chọn đúng đơn vị và charset; xử lý text bằng API phù hợp |
| Coi `skipNBytes` là thao tác atomic/rollback | Sau EOF/IOException tiếp tục parse sai trạng thái | Xử lý lỗi, kết thúc bản ghi và đóng luồng khi cần |
| Dùng Java 8/11 nhưng gọi `skipNBytes` | Lỗi biên dịch do API chưa có | Yêu cầu Java 12+ hoặc triển khai vòng lặp có kiểm tra |
| Bỏ qua header cần xác thực | Bỏ lọt dữ liệu sai định dạng | Đọc và validate header trước khi xử lý payload |

## 10. Tự kiểm tra kiến thức

1. Một luồng thực tế chỉ có 4 byte, gọi `skip(10)` có luôn trả `4`? **Không.** `skip` có thể trả số ít hơn vì nhiều lý do; chỉ kết quả trả về của lần gọi mới cho biết số đã bỏ qua. Với `ByteArrayInputStream` bốn byte thì trả `4`.
2. `skip(6)` trả `2`; có thể đọc payload ngay không? **Không**, nếu cần bỏ qua đủ 6 byte; phải xử lý 4 byte còn lại hoặc dùng `skipNBytes(6)` ngay từ đầu.
3. `skipNBytes(5)` chỉ còn 3 byte đến EOF thì sao? Nó ném `EOFException`; ba byte có thể đã bị tiêu thụ.
4. `skip(4)` trả `0` có chắc EOF? **Không**. Không được chỉ dựa vào số `0` để kết luận.
5. Có nên dùng `skip(1)` để bỏ một ký tự UTF-8? **Không** khi chưa biết kích thước byte và ranh giới ký tự.
6. Khi nào dùng `skipNBytes`? Khi bản ghi/giao thức đòi hỏi **tiến đúng số byte xác định**, và thiếu byte phải được xem là lỗi.

## Tham khảo API

- [Java 17 — `InputStream.skip(long)`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/InputStream.html#skip(long)).
- [Java 17 — `InputStream.skipNBytes(long)`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/InputStream.html#skipNBytes(long)).

**Ghi nhớ:** `skip` cho biết *đã bỏ qua được bao nhiêu*; `skipNBytes` yêu cầu *bỏ qua đúng bao nhiêu hoặc báo lỗi*. Cả hai đều thao tác trên byte của luồng hiện tại, nên luôn kiểm tra độ dài, xử lý EOF/IOException và chọn cách truy cập dữ liệu phù hợp.