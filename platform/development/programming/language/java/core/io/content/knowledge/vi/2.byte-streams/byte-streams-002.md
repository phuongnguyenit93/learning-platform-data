# `InputStream.read()`: giá trị byte 0–255 và dấu hiệu EOF `-1`

## 1. Giá trị trả về của `read()`

Trong Java I/O, `InputStream` đọc dữ liệu theo **byte**. Phương thức cơ bản được khai báo:

```java
public abstract int read() throws IOException;
```

Một lần gọi `read()` có hai loại kết quả:

- **`0` đến `255`:** đọc được một byte. Số nguyên thể hiện **giá trị không dấu** của 8 bit trong byte đó.
- **`-1`:** **end of stream (EOF)**, không còn byte tiếp theo được luồng cung cấp theo hợp đồng của phương thức.

Ví dụ, đọc chuỗi byte hex `00 7F 80 FF`:

| Lần gọi | Byte thực tế | `read()` trả về |
| --- | --- | ---: |
| 1 | `0x00` | `0` |
| 2 | `0x7F` | `127` |
| 3 | `0x80` | `128` |
| 4 | `0xFF` | `255` |
| 5 | Hết byte | `-1` |

**Không nhầm lẫn:** `0` là byte dữ liệu hợp lệ; `255` cũng là byte hợp lệ. Chỉ `-1` mới báo EOF. Dấu hiệu `-1` **không phải** byte `0xFF` được lưu trong luồng và không được xử lý như dữ liệu đầu vào.

## 2. Vì sao đọc byte nhưng nhận `int`?

`byte` trong Java là số nguyên có dấu 8 bit, có miền **`-128..127`**. Nhưng mọi byte đọc từ luồng có thể mang một trong 256 mẫu bit, thông thường biểu diễn không dấu từ **`0..255`**.

Nếu kết quả trả về có kiểu `byte`, byte chứa `11111111` (`0xFF`) sẽ có giá trị `-1`, trùng dấu hiệu EOF. Bởi vậy `InputStream.read()` dùng `int`: 256 giá trị dành cho dữ liệu và một giá trị riêng cho kết thúc.

| Mẫu bit | `byte` có dấu trong Java | `int` do `read()` trả về |
| --- | ---: | ---: |
| `0x00` | `0` | `0` |
| `0x7F` | `127` | `127` |
| `0x80` | `-128` | `128` |
| `0xFF` | `-1` | `255` |

Cần nhớ:

- **Giữ kết quả `read()` ở biến `int`** cho đến sau khi kiểm tra EOF.
- **Không ép sang `byte` rồi so sánh với `-1`**, vì dữ liệu `0xFF` cũng biến thành `(byte) -1`.
- Khi đã có `byte b` và muốn diễn giải thành số không dấu, dùng `Byte.toUnsignedInt(b)` hoặc `b & 0xFF`. Với `int` do `read()` trả về trong khoảng `0..255` thì không cần chuyển đổi.

## 3. Chương trình Java 17+ chạy độc lập

Tạo tệp **`ReadByteDemo.java`** với nội dung:

```java
import java.io.ByteArrayInputStream;
import java.io.IOException;
import java.io.InputStream;

public class ReadByteDemo {
    public static void main(String[] args) throws IOException {
        byte[] data = {0x00, 0x7F, (byte) 0x80, (byte) 0xFF};

        try (InputStream input = new ByteArrayInputStream(data)) {
            int value;
            while ((value = input.read()) != -1) {
                System.out.printf("%d -> 0x%02X%n", value, value);
            }

            System.out.println("Sau EOF: " + input.read());
        }
    }
}
```

Biên dịch, chạy:

```bash
javac ReadByteDemo.java
java ReadByteDemo
```

Đầu ra **chính xác**:

```text
0 -> 0x00
127 -> 0x7F
128 -> 0x80
255 -> 0xFF
Sau EOF: -1
```

Giải thích:

1. Mảng lưu bốn mẫu bit `00`, `7F`, `80` và `FF`. Cần `(byte)` với `0x80`, `0xFF` vì hai hằng int ấy vượt miền `byte` có dấu.
2. `ByteArrayInputStream` lần lượt cung cấp bốn byte. Mỗi `input.read()` trả về số `int` không dấu `0..255`, nên `0x80` trở thành `128` và `0xFF` trở thành `255`.
3. `(value = input.read()) != -1` vừa gán byte mới vào `value` vừa dừng **chỉ khi EOF**; không làm mất byte `0x00`. Một vòng chỉ thực hiện một lần đọc.
4. `%02X` in số hex hai chữ số. Đây là mẫu hiển thị; dữ liệu thực đọc vẫn là byte nhị phân.
5. Sau bốn byte, `ByteArrayInputStream` trả `-1`; với chính lớp này, gọi tiếp sau EOF vẫn nhận `-1`. Không coi dòng cuối là byte thứ năm.
6. `try-with-resources` đóng luồng kể cả khi xuất hiện ngoại lệ.

Với `FileInputStream`, điều kiện lặp `int` và `-1` vẫn đúng; thời điểm EOF tùy theo độ dài tệp. Mảng ví dụ trên giúp kết quả được xác định mà không cần chuẩn bị tệp ngoài.

## 4. Điều kiện vòng lặp đúng và các lỗi điển hình

Mẫu đọc từng byte:

```java
int value;
while ((value = input.read()) != -1) {
    // value là dữ liệu 0..255, xử lý tại đây
}
```

Đây là **đoạn mã minh họa**, giả sử `input` là một `InputStream` đã mở và nơi chứa đoạn mã xử lý hoặc khai báo `IOException`. Điều kiện `>= 0` cũng đúng vì hợp đồng `read()` chỉ cho kết quả `-1` hoặc `0..255`; viết `!= -1` nhấn mạnh ý nghĩa EOF.

Những cách viết sai:

```java
// SAI: dừng khi gặp byte hợp lệ 0x00.
while ((value = input.read()) > 0) {
    // ...
}

// SAI: 0xFF và EOF cùng biến thành byte -1 sau phép ép.
byte b = (byte) input.read();
if (b == -1) {
    // Không phân biệt được 0xFF với EOF.
}

// SAI: sử dụng giá trị trước khi kiểm tra.
int n = input.read();
// Không được coi n là một byte nếu n == -1.
```

Nếu cần lưu một byte vào `byte`, hãy đọc vào `int`, kiểm tra `n != -1`, rồi mới ép kiểu trong nhánh thành công. Khi `n == 255`, `(byte)n` là `-1` theo biểu diễn có dấu của Java, nhưng **byte dữ liệu vẫn tồn tại**; EOF đã được kiểm tra trước đó.

## 5. EOF không phải “chưa có dữ liệu” hoặc lỗi

`InputStream.read()` có thể **chặn (blocking)**, tùy loại luồng. Nếu byte tiếp theo chưa sẵn sàng và chưa có EOF, lệnh có thể chờ có dữ liệu, chờ kết thúc hoặc ném `IOException`. Phân biệt:

- **`0..255`:** đọc được một byte, kể cả byte có giá trị `0`.
- **`-1`:** luồng báo đã đến cuối đầu vào theo hợp đồng `read()`.
- **Đang chờ:** chưa có kết quả trả về; không thể tự suy luận là EOF.
- **`IOException`:** có lỗi I/O; không nên giả lập thành `-1` rồi im lặng bỏ lỗi.

`input.available() == 0` **không chứng minh EOF**: `available()` chỉ ước lượng số byte có thể đọc mà không chặn. Một socket chẳng hạn có thể tạm thời chưa nhận byte nào nhưng vẫn tiếp tục được gửi dữ liệu. EOF của luồng socket thường liên quan đến việc bên kia đóng chiều gửi; một lần đọc không nhận được dữ liệu ngay lập tức không tạo thành dấu hiệu kết thúc.

Nếu chương trình cần giới hạn thời gian chờ hoặc biết ranh giới từng thông điệp, dùng cơ chế timeout hoặc quy ước định dạng/giao thức phù hợp. Bản thân `read()` và dấu `-1` chỉ mô tả luồng byte và kết thúc luồng.

## 6. Phân biệt với `read(byte[])`

Giá trị trả về **có ý nghĩa khác nhau** giữa hai kiểu đọc:

| Lời gọi | Kết quả trả về |
| --- | --- |
| `input.read()` | **Giá trị byte** `0..255` hoặc `-1` ở EOF |
| `input.read(buffer)` | **Số byte thực đọc** vào buffer hoặc `-1` ở EOF |
| `input.read(buffer, offset, length)` | **Số byte thực đọc** trong vùng yêu cầu; `0` nếu `length == 0`; `-1` nếu EOF trước khi đọc byte nào với yêu cầu có độ dài dương |

Khi đọc mảng, phải duyệt `buffer[0]` tới `buffer[count - 1]`. Các ô khác có thể chứa dữ liệu từ lần đọc trước. Một lần `read(buffer)` không bảo đảm lấp đầy cả mảng với mọi loại luồng.

Ví dụ Java 17+ độc lập, tạo **`ReadBufferDemo.java`**:

```java
import java.io.ByteArrayInputStream;
import java.io.IOException;
import java.io.InputStream;

public class ReadBufferDemo {
    public static void main(String[] args) throws IOException {
        byte[] data = {(byte) 0xFF, 0x00, 0x2A};

        try (InputStream input = new ByteArrayInputStream(data)) {
            byte[] buffer = new byte[2];
            int count;

            while ((count = input.read(buffer)) != -1) {
                System.out.print("Đọc " + count + " byte:");
                for (int i = 0; i < count; i++) {
                    System.out.print(" " + Byte.toUnsignedInt(buffer[i]));
                }
                System.out.println();
            }
        }
    }
}
```

Biên dịch và chạy:

```bash
javac ReadBufferDemo.java
java ReadBufferDemo
```

Kết quả:

```text
Đọc 2 byte: 255 0
Đọc 1 byte: 42
```

Lần đầu `count == 2`; buffer có dữ liệu mới `255`, `0`. Lần sau `count == 1`; chỉ `buffer[0]` chứa byte mới `42`, còn `buffer[1]` giữ giá trị cũ `0`. Sau đó EOF trả `-1`. Cách chia `2` byte rồi `1` byte được bảo đảm với `ByteArrayInputStream` cụ thể trong ví dụ; các luồng khác có thể trả về ít byte hơn kích thước buffer trong một lần đọc.

Khi `length == 0`, `read(buffer, offset, length)` trả `0` mà không đọc dữ liệu. Với yêu cầu đọc có độ dài dương, hợp đồng thông thường của `InputStream` trả số byte dương hoặc `-1` tại EOF. Vì vậy **không được áp dụng quy tắc kiểm tra EOF của `read()` cho mọi giá trị mang tên “read” mà không xét chữ ký phương thức**.

Các phương thức tiện ích `readNBytes` và `readAllBytes` có hợp đồng riêng về lượng dữ liệu đọc và cấp phát bộ nhớ; chúng không làm thay đổi ý nghĩa `0..255` và `-1` của `read()` không tham số.

## 7. Tự kiểm tra

Trước khi hoàn tất một vòng lặp đọc byte, xác nhận:

1. Biến nhận `read()` có kiểu `int`?
2. Có kiểm tra `-1` **trước** khi ép thành `byte` hoặc dùng như dữ liệu?
3. Byte `0x00` và `0xFF` đều được xử lý?
4. Với buffer, chỉ duyệt đúng số byte thực đọc?
5. Có phân biệt EOF với trạng thái đang chờ và với `IOException`?
6. Luồng được đóng khi không dùng nữa, thường bằng `try-with-resources`?

**Bài tập nhỏ:** Luồng chứa đúng hai byte `00 FF`. Ba lời gọi `read()` liên tiếp phải trả **`0`, `255`, `-1`**. Nếu dừng tại `0` hoặc coi `255` là EOF, hãy kiểm tra lại điều kiện lặp và phép ép kiểu.

**Ghi nhớ:** `InputStream.read()` trả về `int` vì cần chứa đầy đủ **256 giá trị byte không dấu (`0..255`)** cùng **dấu EOF riêng (`-1`)**. Luôn kiểm tra `-1` rồi mới xử lý byte.