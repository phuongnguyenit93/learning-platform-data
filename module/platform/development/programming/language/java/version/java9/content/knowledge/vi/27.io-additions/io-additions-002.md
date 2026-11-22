# Đọc tối đa số byte vào bộ đệm bằng `InputStream.readNBytes(byte[], int, int)`

`InputStream.readNBytes(byte[], int, int)` đọc tối đa số byte được yêu cầu từ một luồng và ghi trực tiếp vào một vùng của mảng `byte` do chương trình cung cấp. Phương thức trả về số byte thực tế đã đọc, vì vậy caller biết chính xác phần nào của bộ đệm chứa dữ liệu mới.

Phương thức này được bổ sung từ Java 9 và vẫn là API hiện hành. Nó phù hợp khi đã có sẵn bộ đệm, cần giới hạn số byte đọc, hoặc muốn tránh tạo một mảng mới cho mỗi lần đọc. Điểm quan trọng là phương thức cố gắng lấp đầy vùng yêu cầu; nếu gặp EOF trước khi đủ byte, nó trả về số byte đã đọc được.

## 1. Chữ ký và ý nghĩa tham số

Chữ ký phương thức:

```java
public int readNBytes(byte[] b, int off, int len) throws IOException
```

| Tham số | Ý nghĩa |
| --- | --- |
| `b` | Mảng đích nhận dữ liệu byte |
| `off` | Chỉ số bắt đầu ghi trong mảng |
| `len` | Số byte tối đa cần đọc và ghi |

Giá trị trả về là số byte thực tế đã ghi vào mảng, nằm trong khoảng từ `0` đến `len`. Vùng được phép ghi là đoạn nửa mở `[off, off + len)`. Phương thức không ghi ra ngoài vùng này và không tự xóa các phần tử còn lại của mảng.

Ví dụ, với `off = 2` và `len = 4`, dữ liệu chỉ có thể được ghi vào các vị trí 2, 3, 4 và 5. Nếu chỉ đọc được 3 byte trước EOF, phương thức trả về `3`; caller chỉ nên xử lý các vị trí từ 2 đến 4.

## 2. Cơ chế đọc và xử lý EOF

Với `len` lớn hơn 0, phương thức chặn (blocking) cho đến khi xảy ra một trong các điều kiện:

- Đã đọc đủ `len` byte.
- Phát hiện kết thúc luồng (EOF).
- Có lỗi I/O và một `IOException` được ném ra.

Điều này khác với một lần gọi `read(byte[], off, len)`: phương thức `read` có thể trả về ít byte hơn `len` ngay cả khi luồng chưa kết thúc. `readNBytes` tiếp tục đọc để lấp đầy vùng yêu cầu nếu dữ liệu vẫn còn, cho đến khi đủ số byte hoặc gặp EOF.

Ví dụ: nếu yêu cầu 8 byte nhưng luồng chỉ còn 5 byte, `readNBytes` ghi 5 byte và trả về `5`. Nó không ném `EOFException` chỉ vì chưa đủ 8 byte. Nếu luồng đã ở EOF trước khi bắt đầu đọc, kết quả là `0`.

Với `len == 0`, không có byte nào được đọc và phương thức trả về `0`. Trường hợp này không cần chờ dữ liệu từ luồng.

## 3. Dùng offset để ghi vào một phần của bộ đệm

Ví dụ sau dùng một mảng có giá trị đánh dấu `-1`. Dữ liệu được đọc bắt đầu tại vị trí 1, còn phần ngoài vùng ghi giữ nguyên:

```java
byte[] buffer = {-1, -1, -1, -1, -1};
try (InputStream input = new ByteArrayInputStream(new byte[] {10, 20, 30})) {
    int count = input.readNBytes(buffer, 1, 4);
    System.out.println("Bytes read: " + count);
    System.out.println("Buffer: " + Arrays.toString(buffer));
}
```

Luồng chỉ có 3 byte, trong khi lời gọi yêu cầu tối đa 4 byte. Kết quả:

```text
Bytes read: 3
Buffer: [-1, 10, 20, 30, -1]
```

Giá trị `-1` ở vị trí 0 và 4 không bị thay đổi. Chỉ ba vị trí bắt đầu từ `off = 1` nhận dữ liệu. Trong Java, kiểu `byte` là kiểu số nguyên có dấu; các giá trị âm khi hiển thị bằng `Arrays.toString()` vẫn đại diện cho byte có cùng bit pattern.

## 4. Đọc tối đa không đồng nghĩa với đọc đủ

`readNBytes` được thiết kế để đọc *tối đa* số byte yêu cầu. Nếu luồng kết thúc sớm, số byte trả về nhỏ hơn `len`. Caller phải luôn kiểm tra kết quả khi nghiệp vụ yêu cầu đủ dữ liệu.

Ví dụ, khi đọc một header có độ dài cố định 4 byte:

```java
byte[] header = new byte[4];
int count = input.readNBytes(header, 0, header.length);
if (count != header.length) {
    throw new EOFException("Header không đủ 4 byte");
}
```

Không được giả định rằng toàn bộ `header` đã được ghi chỉ vì lời gọi kết thúc bình thường. Nếu chỉ đọc được 2 byte, hai byte còn lại có thể vẫn giữ giá trị cũ trong mảng. Chỉ vùng `[off, off + count)` chắc chắn chứa dữ liệu mới từ lần gọi đó.

Có thể đóng gói quy tắc đọc đủ vào một helper:

```java
static void readExactly(InputStream input, byte[] buffer,
                        int offset, int length) throws IOException {
    int count = input.readNBytes(buffer, offset, length);
    if (count != length) {
        throw new EOFException(
                "Expected " + length + " bytes, got " + count
        );
    }
}
```

Helper này biến trường hợp EOF sớm thành lỗi rõ ràng theo yêu cầu của ứng dụng. `readNBytes` tự nó vẫn giữ hợp đồng đọc tối đa và trả về số lượng thực tế.

## 5. Ví dụ Java hoàn chỉnh

Chương trình sau minh họa đọc vào offset, EOF trước khi đủ byte, yêu cầu độ dài bằng 0, đọc đủ dữ liệu và kiểm tra vùng chỉ số không hợp lệ.

Tạo tệp `ReadNBytesBufferDemo.java`:

```java
import java.io.ByteArrayInputStream;
import java.io.EOFException;
import java.io.IOException;
import java.io.InputStream;
import java.util.Arrays;

public class ReadNBytesBufferDemo {
    private static void readExactly(InputStream input, byte[] buffer,
                                    int offset, int length) throws IOException {
        int count = input.readNBytes(buffer, offset, length);
        if (count != length) {
            throw new EOFException("Expected " + length + " bytes, got " + count);
        }
    }

    public static void main(String[] args) throws IOException {
        byte[] buffer = {-1, -1, -1, -1, -1};
        try (InputStream input = new ByteArrayInputStream(new byte[] {10, 20, 30})) {
            int count = input.readNBytes(buffer, 1, 4);
            System.out.println("Bytes read: " + count);
            System.out.println("Buffer: " + Arrays.toString(buffer));
            System.out.println("Bytes after EOF: " + input.readNBytes(buffer, 0, 2));
            System.out.println("Zero-length read: " + input.readNBytes(buffer, buffer.length, 0));
        }

        byte[] exact = new byte[5];
        try (InputStream input = new ByteArrayInputStream(new byte[] {1, 2, 3, 4, 5})) {
            readExactly(input, exact, 0, exact.length);
            System.out.println("Exact buffer: " + Arrays.toString(exact));
        }

        try (InputStream input = new ByteArrayInputStream(new byte[] {1, 2})) {
            try {
                readExactly(input, new byte[3], 0, 3);
            } catch (EOFException ex) {
                System.out.println("Short input rejected");
            }
        }

        try (InputStream input = new ByteArrayInputStream(new byte[] {1})) {
            try {
                input.readNBytes(buffer, -1, 1);
            } catch (IndexOutOfBoundsException ex) {
                System.out.println("Invalid range rejected");
            }
        }
    }
}
```

Biên dịch bằng JDK 9 trở lên:

```bash
javac --release 9 -Xlint:all ReadNBytesBufferDemo.java
java ReadNBytesBufferDemo
```

Kết quả stdout:

```text
Bytes read: 3
Buffer: [-1, 10, 20, 30, -1]
Bytes after EOF: 0
Zero-length read: 0
Exact buffer: [1, 2, 3, 4, 5]
Short input rejected
Invalid range rejected
```

`ByteArrayInputStream` giúp ví dụ có kết quả xác định và không phụ thuộc file hoặc mạng. Với file, socket hoặc một nguồn I/O khác, thời gian chờ và khả năng phát sinh `IOException` còn phụ thuộc nguồn thực tế.

## 6. Kiểm tra tham số và các exception

- Nếu `b` là `null`, phương thức ném `NullPointerException`.
- Nếu `off` âm, `len` âm hoặc đoạn `[off, off + len)` vượt quá độ dài mảng, phương thức ném `IndexOutOfBoundsException`.
- Nếu có lỗi trong quá trình đọc, phương thức có thể ném `IOException`.
- Nếu `len == 0` và vùng chỉ số hợp lệ, phương thức trả về `0` mà không đọc dữ liệu.

Không tự tính `off + len` rồi chỉ kiểm tra kết quả bằng một phép so sánh đơn giản nếu phép cộng có thể tràn số nguyên. Hợp đồng của API kiểm tra đoạn chỉ số; khi tự viết validation, có thể dùng `Objects.checkFromIndexSize(off, len, b.length)` từ Java 9 để kiểm tra cùng quy tắc.

Nếu `IOException` xảy ra sau khi một phần dữ liệu đã được đọc, luồng có thể đã tiến lên và bộ đệm có thể đã bị thay đổi một phần. Không giả định thao tác thất bại sẽ khôi phục vị trí đọc hoặc nội dung mảng như trước.

## 7. So sánh với các phương thức đọc khác

| Phương thức | Kết quả | Khi phù hợp |
| --- | --- | --- |
| `read(byte[], off, len)` | Số byte của một lần đọc; có thể ít hơn `len` | Đọc từng bước và tự quản lý vòng lặp |
| `readNBytes(byte[], off, len)` | Số byte thực đọc vào vùng mảng có sẵn, cố gắng đọc đủ `len` hoặc đến EOF | Đọc có giới hạn vào buffer đã cấp phát |
| `readNBytes(len)` | Mảng mới chứa tối đa `len` byte | Muốn nhận một mảng mới với dữ liệu đọc được |
| `readAllBytes()` | Mảng mới chứa toàn bộ byte còn lại đến EOF | Nguồn có kích thước hữu hạn, đủ nhỏ để giữ trong bộ nhớ |

`readNBytes(byte[], off, len)` không cấp phát mảng kết quả mới, nhưng caller phải tự quản lý bộ đệm và số byte hợp lệ. `readNBytes(len)` tiện hơn khi muốn một mảng riêng, còn `readAllBytes()` có thể dùng nhiều bộ nhớ nếu nguồn lớn hoặc không có giới hạn rõ ràng.

Phương thức không đóng luồng. Caller quản lý vòng đời của `InputStream`, thường bằng try-with-resources khi caller sở hữu luồng đó. Nó cũng không đặt timeout; với socket, hãy cấu hình timeout ở socket hoặc nguồn tương ứng nếu cần giới hạn thời gian chờ.

## 8. Lưu ý khi đọc dữ liệu nhị phân

**Luôn dùng số byte trả về.** Khi tái sử dụng một buffer, không xử lý toàn bộ mảng nếu lần đọc chỉ trả về một phần. Ví dụ với `off = 4` và `count = 3`, chỉ ba byte từ vị trí 4 đến 6 thuộc dữ liệu mới.

**Không nhầm byte với ký tự.** `readNBytes` đọc byte thô. Nếu dữ liệu là văn bản UTF-8, cần giải mã bằng charset phù hợp; giới hạn byte có thể cắt giữa một ký tự nhiều byte, nên không được mặc định mỗi byte tương ứng một ký tự.

**Không coi EOF sớm là dữ liệu đầy đủ.** Với định dạng có trường độ dài cố định hoặc length-prefix, kiểm tra `count` trước khi phân tích header hoặc payload. Nếu cần đúng số byte, chuyển EOF sớm thành `EOFException` như helper ở trên.

**Cân nhắc kích thước yêu cầu.** `readNBytes` ghi vào mảng có sẵn nên không tự cấp phát mảng theo `len`, nhưng vùng đích vẫn phải hợp lệ và đủ chỗ. Nếu `len` đến từ dữ liệu bên ngoài, hãy xác thực giới hạn nghiệp vụ trước khi đọc để tránh chờ quá lâu hoặc xử lý lượng dữ liệu không mong muốn.

`InputStream.readNBytes(byte[], int, int)` là lựa chọn hiện hành từ Java 9 để đọc có giới hạn vào một vùng buffer. Hãy dùng giá trị trả về làm ranh giới dữ liệu hợp lệ, kiểm tra EOF khi cần đủ byte, và để caller quản lý việc đóng luồng cùng timeout của nguồn I/O.