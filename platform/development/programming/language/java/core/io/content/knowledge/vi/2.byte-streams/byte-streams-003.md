# Đọc luồng byte bằng `byte[]`, `offset` và `length` trong Java

Khi làm việc với `InputStream`, ta thường đọc nhiều byte vào một mảng thay vì gọi `read()` từng byte. Hai tham số `offset` và `length` cho phép chỉ định **vùng được phép ghi trong mảng đích**. Hiểu đúng chúng giúp xử lý dữ liệu nhị phân, sao chép tệp, đọc dữ liệu mạng và ghép các phần dữ liệu mà không làm hỏng byte đã có.

## 1. Ba cách đọc cơ bản

```java
int oneByte = in.read();
int count1 = in.read(buffer);
int count2 = in.read(buffer, offset, length);
```

- `read()`: đọc tối đa **một byte**, trả về số nguyên từ `0` đến `255`, hoặc `-1` khi hết luồng. Không ép trực tiếp về `byte` trước khi kiểm tra `-1`.
- `read(byte[] buffer)`: yêu cầu đọc tối đa `buffer.length` byte vào mảng, bắt đầu ở chỉ số `0`; về mặt hợp đồng tương đương vùng `read(buffer, 0, buffer.length)`.
- `read(byte[] buffer, int offset, int length)`: yêu cầu đọc tối đa `length` byte vào `buffer` từ chỉ số `offset`.

Trong ba trường hợp, dữ liệu được lấy từ **vị trí đọc hiện tại của luồng**. `offset` không phải vị trí trong tệp hoặc luồng; nó là chỉ số bắt đầu trong **mảng đích**.

## 2. Ý nghĩa chính xác của `offset` và `length`

Với chữ ký:

```java
int n = in.read(buffer, offset, length);
```

| Thành phần | Ý nghĩa |
|---|---|
| `buffer` | Mảng `byte[]` nhận dữ liệu |
| `offset` (thường viết tắt `off`) | Chỉ số phần tử **đầu tiên được phép ghi** trong mảng |
| `length` (thường viết tắt `len`) | **Số byte tối đa** muốn đọc trong lần gọi này, không phải chỉ số kết thúc |
| `n` | **Số byte thực sự đọc được**; dùng chính giá trị này để xử lý dữ liệu |

Nếu lời gọi trả về `n > 0`, chỉ vùng `buffer[offset]` đến `buffer[offset + n - 1]` chứa dữ liệu mới từ lần đọc đó. Vùng ngoài khoảng nêu trên giữ nguyên; phần còn lại của vùng dự kiến nhưng chưa được đọc **không tự được xóa**.

Điều kiện chỉ số hợp lệ:

```text
buffer != null
offset >= 0
length >= 0
offset <= buffer.length
length <= buffer.length - offset
```

Ví dụ, mảng 8 byte và `read(buffer, 2, 3)` cho phép ghi tại chỉ số `2, 3, 4`, tức khoảng nửa mở `[2, 5)`. Nó **không** ghi đến chỉ số `3` rồi dừng, cũng không bỏ qua hai byte ở đầu luồng.

- `buffer == null` dẫn đến `NullPointerException`.
- Chỉ số hoặc kích thước vùng không hợp lệ dẫn đến `IndexOutOfBoundsException`.
- `length == 0` trả về `0` mà không đọc byte; đừng dùng mảng dài 0 trong vòng lặp chờ `-1`.
- Trong lần đọc có `length > 0`, kết quả thường là một số dương **không vượt quá** `length`, hoặc `-1` khi không còn byte vì đã đến cuối luồng. Một số nguồn có thể chặn (block) để chờ dữ liệu hoặc báo lỗi `IOException`.

## 3. Ví dụ chạy được: giữ nguyên vùng ngoài `offset`

Tạo tệp **`ByteSliceReadDemo.java`**:

```java
import java.io.ByteArrayInputStream;
import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;

public class ByteSliceReadDemo {
    public static void main(String[] args) throws IOException {
        byte[] storage = "........".getBytes(StandardCharsets.US_ASCII);

        try (InputStream in = new ByteArrayInputStream(
                "ABCDE".getBytes(StandardCharsets.US_ASCII))) {
            int first = in.read(storage, 2, 3);
            int second = in.read(storage, 5, 2);
            int eof = in.read(storage, 0, 2);

            System.out.printf("first=%d, second=%d, eof=%d%n",
                    first, second, eof);
            System.out.println(new String(storage, StandardCharsets.US_ASCII));
        }
    }
}
```

Biên dịch và chạy bằng JDK 17+:

```bash
javac ByteSliceReadDemo.java
java ByteSliceReadDemo
```

Kết quả:

```text
first=3, second=2, eof=-1
..ABCDE.
```

Giải thích lần lượt:

1. `read(storage, 2, 3)` lấy `A B C` vào chỉ số `2, 3, 4`; trả `3`.
2. `read(storage, 5, 2)` tiếp tục **từ vị trí luồng sau C**, lấy `D E` vào chỉ số `5, 6`; trả `2`.
3. Lần đọc tiếp theo hết luồng, trả `-1` và không có byte mới để xử lý.
4. Chỉ số `0, 1, 7` vẫn là dấu chấm ban đầu. Với một `ByteArrayInputStream` như ví dụ, lượng dữ liệu trong bộ nhớ đã biết nên kết quả trên xác định; **không suy rộng** rằng mọi luồng đều trả đủ số byte yêu cầu sau mỗi lần đọc.

## 4. Đọc một phần là điều bình thường

`read(buffer, off, len)` yêu cầu **tối đa** `len` byte, **không bảo đảm** lấy đủ `len` byte trong một lần. Ví dụ, yêu cầu 1024 byte có thể chỉ trả `n = 37` khi tại thời điểm đó luồng chỉ cung cấp được một phần. Đọc tệp, socket hoặc luồng đã bọc qua bộ đệm đều phải tuân theo giá trị trả về thực tế.

Với `n > 0`, dùng đúng khoảng `[off, off + n)`:

```java
int n = in.read(buffer, 4, 8);
if (n > 0) {
    out.write(buffer, 4, n); // Viết đúng n byte vừa đọc
}
```

Đoạn trên là **mảnh mã minh họa**, yêu cầu `buffer.length >= 12` cùng các biến `in`, `out` đã được tạo. `length = 8` là tối đa tám byte, còn `n` mới là số byte đã nhận.

Không xử lý toàn bộ `length` hay toàn bộ `buffer.length` nếu `n` nhỏ hơn: phần dư chứa dữ liệu cũ hoặc dữ liệu khởi tạo, sẽ gây sai dữ liệu đầu ra.

## 5. Mẫu hoàn chỉnh: đọc theo từng khối rồi sao chép

Tạo tệp **`ByteStreamCopyDemo.java`**:

```java
import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.util.Arrays;

public class ByteStreamCopyDemo {
    public static void main(String[] args) throws IOException {
        byte[] source = {0, 1, 2, (byte) 255, 4};

        try (InputStream in = new ByteArrayInputStream(source);
             ByteArrayOutputStream out = new ByteArrayOutputStream()) {
            byte[] buffer = new byte[3]; // Kích thước > 0
            int n;

            while ((n = in.read(buffer, 0, buffer.length)) != -1) {
                out.write(buffer, 0, n);
                System.out.println("chunk=" + n);
            }

            System.out.println(Arrays.toString(out.toByteArray()));
        }
    }
}
```

```bash
javac ByteStreamCopyDemo.java
java ByteStreamCopyDemo
```

Kết quả:

```text
chunk=3
chunk=2
[0, 1, 2, -1, 4]
```

Khối cuối chỉ có 2 byte, nên phải dùng `out.write(buffer, 0, n)`. Nếu thay bằng `out.write(buffer)`, toàn bộ ba vị trí sẽ được xuất, bao gồm một byte còn sót lại từ khối trước.

Byte `(byte) 255` được hiển thị là `-1` trong `Arrays.toString(byte[])` vì kiểu `byte` của Java có dấu (giá trị từ `-128` đến `127`). Nội dung nhị phân vẫn giữ mẫu bit `0xFF`. Khi cần xem dạng số không dấu, dùng `buffer[i] & 0xFF`. Giá trị `-1` báo EOF chỉ là **giá trị trả về kiểu `int` của phương thức đọc**, không phải bằng chứng byte `0xFF` là EOF.

Đối với tệp thực, có thể thay nguồn bằng `Files.newInputStream(path)` và đích bằng `Files.newOutputStream(path)` sau khi xác định đường dẫn thích hợp; giữ nguyên cách lặp và nguyên tắc ghi đúng `n` byte. `try-with-resources` bảo đảm đóng luồng cả khi gặp lỗi.

## 6. Muốn điền gần đủ một vùng mảng thì làm sao?

Có hai nhu cầu khác nhau:

**A. Đọc tối đa `length` byte, được phép dừng sớm:** dùng `read(buffer, offset, length)`, kiểm tra `n` và xử lý phần đã nhận.

**B. Cố gắng điền tối đa `length` byte, chấp nhận cần nhiều lần đọc:** từ Java 9, dùng `readNBytes(buffer, offset, length)`. Phương thức này có thể đọc lặp cho đến khi đủ, gặp EOF hoặc lỗi; giá trị trả về là **tổng số byte đã đọc**, từ `0` đến `length`. Đặc biệt, khi EOF trước khi đọc được byte nào, `readNBytes` trả `0` (khác `read` trả `-1`).

Ví dụ chạy được (JDK 17+) trong tệp **`ReadNBytesDemo.java`**:

```java
import java.io.ByteArrayInputStream;
import java.io.IOException;
import java.io.InputStream;
import java.util.Arrays;

public class ReadNBytesDemo {
    public static void main(String[] args) throws IOException {
        byte[] target = {9, 9, 9, 9, 9};

        try (InputStream in = new ByteArrayInputStream(
                new byte[] {10, 20, 30})) {
            int n = in.readNBytes(target, 1, 4);
            System.out.println("n=" + n);
            System.out.println(Arrays.toString(target));
        }
    }
}
```

```bash
javac ReadNBytesDemo.java
java ReadNBytesDemo
```

```text
n=3
[9, 10, 20, 30, 9]
```

Mặc dù yêu cầu tối đa 4 byte, nguồn chỉ có 3 byte. Phần tử cuối của mảng vẫn giữ giá trị 9. Nếu giao thức **bắt buộc đúng số byte** (ví dụ một header dài cố định), dùng `DataInputStream.readFully(buffer, offset, length)`, phương thức chỉ thành công khi đọc đủ và ném `EOFException` nếu EOF đến sớm. Không đánh đồng `readNBytes` với `readFully`.

Khi cần đọc đến hết tệp có kích thước biết trước và phù hợp bộ nhớ, `readAllBytes()` cũng có thể hữu ích; tránh mặc định đọc toàn bộ luồng rất lớn hoặc không giới hạn vào RAM.

## 7. Những lỗi dễ gặp

| Lỗi | Tại sao sai | Cách sửa |
|---|---|---|
| Gọi `read(buffer, 4, 8)` với mảng dài 8 | `length` là số lượng, nên vùng `[4, 12)` vượt mảng | Dùng `read(buffer, 4, 4)` nếu muốn phần tử 4–7 |
| Nghĩ `read(buffer, off, len)` luôn trả `len` | Luồng có thể trả số byte ít hơn | Luôn lưu và kiểm tra `n` |
| Xử lý cả `buffer` sau khi chỉ đọc được `n` byte | Dữ liệu cũ bị trộn vào dữ liệu mới | Xử lý `buffer[off..off+n)` |
| Dùng `while (read(...) > 0)` để đọc mọi luồng | Với lời gọi `length == 0` có thể trả 0 liên tục; còn EOF cần xử lý rõ | Đảm bảo buffer có độ dài dương; kiểm tra `n == -1` |
| Hiểu `offset` là vị trí trong tệp | `offset` chỉ vị trí trong mảng nhận | Vị trí luồng do các thao tác đọc/skip/seek tương ứng quyết định |
| Dùng `available()` làm tổng kích thước luồng | `available()` chỉ là ước lượng byte đọc được mà không chặn | Đọc theo vòng lặp tới EOF hoặc theo giao thức định độ dài |
| Giải mã từng khối byte UTF-8 độc lập | Một ký tự Unicode có thể bị tách giữa hai lần đọc | Với văn bản, dùng `InputStreamReader` hoặc bộ giải mã lưu trạng thái |

Ngoài ra, `IOException` có thể phát sinh trong bất kỳ lần đọc nào. Khi một giao thức yêu cầu lấy đúng N byte, phải chủ động xác định cách xử lý trường hợp EOF sớm, dữ liệu thiếu và lỗi I/O; chỉ kiểm tra điều kiện `n != -1` không tự bảo đảm gói dữ liệu đầy đủ.

## 8. Ghi nhớ khi áp dụng

- `offset` là **vị trí bắt đầu ghi vào mảng đích**; `length` là **số byte tối đa yêu cầu**, với `offset + length <= buffer.length`.
- `read` trả **số byte thực tế**, có thể ít hơn yêu cầu; `-1` nghĩa là **hết luồng**, còn `length == 0` trả `0`.
- Chỉ đọc/xuất các phần tử vừa nhận: từ `offset` đến trước `offset + n`.
- Luôn dùng bộ đệm có kích thước dương và vòng lặp kiểm tra số byte thực tế khi cần đọc cả luồng.
- Chọn `readNBytes` nếu muốn cố gắng điền vùng nhận; chọn `DataInputStream.readFully` nếu bắt buộc đủ dữ liệu hoặc phát hiện EOF sớm là lỗi.
