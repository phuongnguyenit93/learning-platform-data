# File pointer, `seek` và `getFilePointer` trong Java

## 1. Vị trí con trỏ tệp là gì?

Trong **truy cập ngẫu nhiên** (*random access*), chương trình có thể đọc hoặc ghi tại một vị trí byte bất kỳ của tệp mà không cần đọc tuần tự tất cả các byte phía trước. Với `java.io.RandomAccessFile`, vị trí đang được dùng để đọc/ghi được gọi là **file pointer** (con trỏ tệp).

File pointer là **offset tính theo byte từ đầu tệp**, bắt đầu tại **0**. Nó không phải địa chỉ bộ nhớ, không phải số dòng, cũng không mặc nhiên là vị trí ký tự trong chuỗi Unicode.

Ví dụ tệp có năm byte:

```text
Offset:       0     1     2     3     4
Nội dung:    10    20    30    40    50
                              ^
                       file pointer = 3
```

Nếu gọi `read()` ở pointer 3, phương thức đọc byte giá trị 40 (thập phân) rồi dịch pointer sang 4. Nếu gọi `seek(1)`, pointer chuyển về 1; lần đọc tiếp theo lấy byte tại offset 1.

Khái niệm cốt lõi:

- **`seek(position)`** chủ động đặt vị trí đọc/ghi tuyệt đối.
- **`getFilePointer()`** trả về vị trí hiện tại.
- **Lệnh đọc/ghi thành công** dịch chuyển pointer theo số byte thực tế đã đọc/ghi.
- **`length()`** cho biết độ dài tệp tính bằng byte, độc lập với việc pointer đang ở đâu.

API này phù hợp với các tệp nhị phân có cấu trúc rõ ràng như bản ghi độ dài cố định, vùng header, chỉ mục và dữ liệu cần cập nhật tại offset xác định.

## 2. `RandomAccessFile` và các phương thức liên quan

Khởi tạo bằng một đường dẫn và chế độ truy cập:

```java
try (RandomAccessFile raf = new RandomAccessFile("data.bin", "rw")) {
    // Đọc/ghi tại các offset bằng byte.
}
```

Đây là **đoạn mã minh họa**; trong chương trình đầy đủ cần import `java.io.RandomAccessFile` và xử lý `IOException`.

Các chế độ thường gặp:

| Mode | Ý nghĩa |
| --- | --- |
| `"r"` | Chỉ đọc; tệp phải tồn tại, thao tác ghi bị từ chối |
| `"rw"` | Đọc và ghi; có thể tạo tệp nếu chưa có |
| `"rws"` | Đọc/ghi với yêu cầu đồng bộ nội dung và metadata xuống thiết bị lưu trữ |
| `"rwd"` | Đọc/ghi với yêu cầu đồng bộ các thay đổi nội dung xuống thiết bị lưu trữ |

`"rws"` và `"rwd"` có chi phí I/O cao hơn tùy hệ thống; chúng không thay thế một thiết kế giao dịch an toàn khi mất điện hoặc xử lý nhiều thao tác liên quan.

| Phương thức | Hành vi quan trọng |
| --- | --- |
| `long getFilePointer()` | Lấy offset byte hiện tại |
| `void seek(long pos)` | Đặt pointer tới offset tuyệt đối `pos` |
| `long length()` | Lấy kích thước tệp hiện tại theo byte |
| `int read()` | Đọc một byte không dấu (0–255) hoặc trả về `-1` tại EOF |
| `void readFully(byte[] b)` | Đọc đủ số byte được yêu cầu hoặc ném `EOFException` |
| `void write(int b)` | Ghi tám bit thấp của số nguyên và dịch pointer một byte |
| `void writeInt(int value)` | Ghi một số nguyên 32-bit thành **4 byte**, theo thứ tự big-endian |
| `int readInt()` | Đọc **4 byte** thành số nguyên; thiếu byte thì ném `EOFException` |
| `void setLength(long newLength)` | Cắt ngắn hoặc mở rộng độ dài logic của tệp |

`seek` yêu cầu vị trí không âm. `seek(-1)` gây `IOException`. Tất cả `seek`, `getFilePointer`, `length`, đọc và ghi đều có thể ném `IOException` do vấn đề tệp/hệ thống. Luôn đóng tài nguyên bằng `try-with-resources`.

## 3. File pointer di chuyển như thế nào?

Hình dung tệp ban đầu rỗng, pointer tại offset 0.

| Thao tác | Kết quả | Pointer sau thao tác | `length()` sau thao tác |
| --- | --- | ---: | ---: |
| Mở tệp rỗng | Chưa có byte | 0 | 0 |
| `writeInt(2026)` | Ghi 4 byte tại offset 0–3 | 4 | 4 |
| `writeByte(65)` | Ghi 1 byte tại offset 4 | 5 | 5 |
| `seek(0)` | Quay về đầu tệp, không đọc/ghi | 0 | 5 |
| `readInt()` | Đọc 4 byte | 4 | 5 |
| `readUnsignedByte()` | Đọc một byte trị số 65 | 5 | 5 |
| `read()` tại EOF | Trả về `-1` | 5 | 5 |
| `seek(4)` | Quay về vị trí byte thứ năm | 4 | 5 |
| `writeByte(66)` | **Ghi đè** byte tại offset 4 | 5 | 5 |

**`seek` tự nó không đọc hay ghi byte nào**, vì thế cũng không tự tăng độ dài tệp. Chỉ việc dịch pointer về trước rồi đọc/ghi ở vị trí đó mới ảnh hưởng đến dữ liệu.

Một số hiểu nhầm cần tránh:

- **Offset khác chỉ số “ký tự”**: văn bản UTF-8 có ký tự dài nhiều byte.
- **Byte thứ năm có offset 4**, không phải 5.
- Sau khi đọc 4 byte từ offset 0, pointer ở **4**, tức vị trí sẽ dùng cho thao tác tiếp theo.
- **Ghi tại offset hiện có thường ghi đè**, không chèn và đẩy dữ liệu phía sau sang phải.

## 4. Ví dụ Java 17+ chạy độc lập: quan sát từng lần thay đổi pointer

Chương trình tạo một tệp tạm, ghi hai giá trị, di chuyển và đọc pointer, sau đó ghi đè byte cuối. Tệp tạm được đóng và dọn dẹp.

**Tệp `FilePointerDemo.java`**

```java
import java.io.IOException;
import java.io.RandomAccessFile;
import java.nio.file.Files;
import java.nio.file.Path;

public class FilePointerDemo {
    public static void main(String[] args) throws IOException {
        Path path = Files.createTempFile("file-pointer-", ".bin");

        try {
            try (RandomAccessFile raf =
                     new RandomAccessFile(path.toFile(), "rw")) {

                raf.setLength(0);
                raf.writeInt(2026);
                System.out.println("Sau writeInt: " + raf.getFilePointer());

                raf.writeByte(65);
                System.out.println("Sau writeByte: " + raf.getFilePointer());

                raf.seek(0);
                System.out.println("Sau seek(0): " + raf.getFilePointer());

                int year = raf.readInt();
                System.out.println("Gia tri int: " + year);
                System.out.println("Sau readInt: " + raf.getFilePointer());

                int lastByte = raf.readUnsignedByte();
                System.out.println("Byte thu nam: " + lastByte);
                System.out.println("Read EOF: " + raf.read());
                System.out.println("Pointer tai EOF: " + raf.getFilePointer());

                raf.seek(4);
                System.out.println("Sau seek(4): " + raf.getFilePointer());

                raf.writeByte(66);
                System.out.println("Sau ghi de: " + raf.getFilePointer());

                raf.seek(0);
                System.out.println(
                    "Du lieu cuoi: " + raf.readInt()
                    + ", " + raf.readUnsignedByte());
                System.out.println("Do dai file: " + raf.length());
            }
        } finally {
            Files.deleteIfExists(path);
        }
    }
}
```

Biên dịch và chạy:

```bash
javac FilePointerDemo.java
java FilePointerDemo
```

**Stdout chính xác trong điều kiện thao tác tệp thành công:**

```text
Sau writeInt: 4
Sau writeByte: 5
Sau seek(0): 0
Gia tri int: 2026
Sau readInt: 4
Byte thu nam: 65
Read EOF: -1
Pointer tai EOF: 5
Sau seek(4): 4
Sau ghi de: 5
Du lieu cuoi: 2026, 66
Do dai file: 5
```

Giải thích:

1. `writeInt(2026)` luôn ghi **4 byte** theo hợp đồng `DataOutput`, vì vậy pointer chuyển từ 0 sang 4.
2. `writeByte(65)` ghi một byte và tăng pointer lên 5.
3. `seek(0)` quay về đầu, sau đó `readInt()` tiêu thụ bốn byte và tái tạo đúng số 2026.
4. `readUnsignedByte()` đọc byte 65 tại offset 4 rồi đưa pointer tới EOF = 5.
5. `read()` tại EOF trả về `-1` và không tiêu thụ byte nào; pointer vẫn là 5.
6. `seek(4)` và `writeByte(66)` thay thế giá trị 65 thành 66 tại cùng offset. Không có byte được chèn thêm và `length()` vẫn bằng 5.

Chương trình này minh họa bản chất **đọc/ghi theo vị trí byte**, khác với đọc luồng chỉ tiến về phía trước.

## 5. `seek` vượt EOF: hợp lệ nhưng cần thận trọng

**EOF** (*end of file*) nằm tại offset `length()`. Với tệp dài 5 byte, vùng byte đang tồn tại có offset từ 0 đến 4; pointer tại 5 nghĩa là vị trí ngay sau byte cuối.

`RandomAccessFile.seek(pos)` **có thể đặt pointer vượt quá EOF** nếu `pos` không âm. Ví dụ:

```java
// Giả sử raf trỏ tới tệp dài đúng 5 byte.
raf.seek(10);
System.out.println(raf.getFilePointer()); // 10
System.out.println(raf.length());         // 5
```

Đây chỉ là đoạn mã minh họa, cần một `raf` đang mở. `seek(10)` **không** làm tệp dài 10 byte. Đọc tại vị trí sau EOF bằng `read()` trả về `-1`. Nếu sau `seek(10)` gọi `writeByte(7)`, tệp được kéo dài để chứa byte mới tại offset 10, và độ dài cuối thành **11**.

**Không được giả định nội dung vùng trống giữa EOF cũ và byte mới luôn bằng zero.** Hợp đồng Java không bảo đảm giá trị các byte trung gian khi mở rộng tệp; hành vi cụ thể phụ thuộc nền tảng và hệ thống tệp. Nếu định dạng dữ liệu yêu cầu những byte có giá trị xác định, hãy ghi các byte ấy một cách tường minh.

`setLength(newLength)` có quy tắc riêng:

- Nếu `newLength` nhỏ hơn độ dài cũ, tệp bị cắt ngắn. Nếu pointer cũ lớn hơn độ dài mới, pointer được đưa về bằng độ dài mới.
- Nếu `newLength` lớn hơn độ dài cũ, tệp được mở rộng nhưng **giá trị các byte mới không được bảo đảm**.
- Nếu chỉ thay đổi độ dài theo `setLength` và pointer vốn không vượt qua độ dài mới, pointer giữ nguyên.

Lỗi hay gặp là tưởng `seek(1000)` “cấp phát” 1.000 byte hoặc nghĩ `setLength(1000)` luôn khởi tạo phần mở rộng bằng số 0.

## 6. Ví dụ thực tế: tìm và cập nhật bản ghi độ dài cố định

Truy cập ngẫu nhiên có hiệu quả khi mỗi bản ghi có **kích thước byte cố định**. Giả sử mỗi bản ghi gồm:

| Trường | Kiểu ghi | Kích thước |
| --- | --- | ---: |
| `id` | `writeInt` | 4 byte |
| `quantity` | `writeInt` | 4 byte |
| **Tổng một bản ghi** |  | **8 byte** |

Với chỉ số bản ghi `index` bắt đầu từ 0, vị trí đầu bản ghi là:

\[
\text{offset} = \text{index} \times 8
\]

Ví dụ bản ghi thứ ba (index = 2) bắt đầu tại offset **16**. Công thức hoạt động vì mọi bản ghi có cùng kích thước 8 byte, bất kể giá trị số nguyên. Nếu dùng chuỗi UTF-8 độ dài thay đổi, không thể tiếp tục nhân chỉ số với 8 như thế mà không có quy định đóng gói khác.

**Tệp `FixedRecordDemo.java`**

```java
import java.io.IOException;
import java.io.RandomAccessFile;
import java.nio.file.Files;
import java.nio.file.Path;

public class FixedRecordDemo {
    private static final int RECORD_SIZE = 8;

    public static void main(String[] args) throws IOException {
        Path path = Files.createTempFile("records-", ".bin");

        try {
            try (RandomAccessFile raf =
                     new RandomAccessFile(path.toFile(), "rw")) {
                raf.setLength(0);

                raf.writeInt(101);
                raf.writeInt(5);

                raf.writeInt(102);
                raf.writeInt(7);

                raf.writeInt(103);
                raf.writeInt(9);

                long thirdOffset = 2L * RECORD_SIZE;
                raf.seek(thirdOffset);
                int thirdId = raf.readInt();
                int thirdQuantity = raf.readInt();
                System.out.println("Ban ghi thu ba: "
                        + thirdId + ", " + thirdQuantity);
                System.out.println("Pointer sau doc: "
                        + raf.getFilePointer());

                long secondQuantityOffset = 1L * RECORD_SIZE + 4;
                raf.seek(secondQuantityOffset);
                raf.writeInt(70);

                raf.seek(1L * RECORD_SIZE);
                int secondId = raf.readInt();
                int secondQuantity = raf.readInt();
                System.out.println("Ban ghi thu hai: "
                        + secondId + ", " + secondQuantity);
                System.out.println("Kich thuoc tep: " + raf.length());
            }
        } finally {
            Files.deleteIfExists(path);
        }
    }
}
```

Chạy:

```bash
javac FixedRecordDemo.java
java FixedRecordDemo
```

**Stdout chính xác khi thao tác thành công:**

```text
Ban ghi thu ba: 103, 9
Pointer sau doc: 24
Ban ghi thu hai: 102, 70
Kich thuoc tep: 24
```

**Vì sao như vậy?** Có ba bản ghi, mỗi bản ghi 8 byte, tổng tệp 24 byte. `seek(16)` di chuyển tới bản ghi thứ ba; hai lần `readInt()` đọc 8 byte nên pointer ở 24. Trường `quantity` của bản ghi thứ hai bắt đầu tại offset `1 * 8 + 4 = 12`; `seek(12)` rồi `writeInt(70)` chỉ ghi đè byte 12–15, không thay đổi các bản ghi khác và không đổi chiều dài tệp.

Khi áp dụng thực tế, cần tính offset bằng `long` ngay từ đầu (ví dụ `(long) index * RECORD_SIZE`) để tránh tràn số nguyên 32-bit; kiểm tra `index >= 0`, `offset` không tràn, và `offset + RECORD_SIZE <= raf.length()` trước khi đọc một bản ghi hiện có. Nếu tệp có thể bị bên khác sửa song song, kết quả kiểm tra chiều dài cũng có thể hết hạn trước lúc đọc.

## 7. EOF, đọc thiếu byte và ngoại lệ

`read()` có thể trả về `-1` khi không còn byte. Nhưng **không phải phương thức đọc nào cũng dùng `-1`**:

- `readInt()` cần đủ bốn byte; thiếu bất cứ byte nào sẽ ném `EOFException`.
- `readUnsignedByte()` cần đúng một byte; gọi tại EOF cũng ném `EOFException`.
- `readFully(byte[])` có nghĩa là phải lấy đủ số byte yêu cầu; nếu tệp kết thúc sớm sẽ ném `EOFException`.
- `read(byte[])` có thể trả về một số byte ít hơn độ dài mảng; không được mặc định lần đọc luôn điền đầy mảng.

Ví dụ nếu tệp chỉ có ba byte, thực hiện `raf.seek(0); raf.readInt();` sẽ gây `EOFException` do `readInt` cần bốn byte. Khi một lệnh đọc nhiều byte thất bại, không được mặc nhiên suy ra pointer quay lại vị trí trước khi đọc: một phần byte có thể đã được tiêu thụ. Nếu cần thao tác đọc “tất cả hoặc không gì cả”, chương trình phải thiết kế xử lý và phục hồi vị trí phù hợp.

Một cách phòng ngừa khi đọc bản ghi cố định là kiểm tra độ dài tệp cùng các offset đã tính, sau đó **vẫn bắt và xử lý lỗi I/O khi đọc thật**.

## 8. Pointer khi đọc/ghi kiểu dữ liệu và chuỗi

`RandomAccessFile` triển khai các phương thức của `DataInput` và `DataOutput`. Vì vậy độ dịch pointer phụ thuộc **số byte được mã hóa**, không phải số lượng lệnh hay ký tự.

| Lệnh | Số byte ghi/đọc bình thường |
| --- | ---: |
| `writeByte(int)` / `readUnsignedByte()` | 1 |
| `writeShort(int)` / `readShort()` | 2 |
| `writeChar(int)` / `readChar()` | 2 |
| `writeInt(int)` / `readInt()` | 4 |
| `writeLong(long)` / `readLong()` | 8 |
| `writeFloat(float)` / `readFloat()` | 4 |
| `writeDouble(double)` / `readDouble()` | 8 |
| `writeUTF(String)` / `readUTF()` | Độ dài **thay đổi** |

Các kiểu nguyên thủy nhiều byte được mã hóa theo **big-endian** trong `RandomAccessFile`. Ví dụ số nguyên `0x01020304` được ghi thành bốn byte `01 02 03 04`; con trỏ tăng 4.

`writeUTF` sử dụng **modified UTF-8** và phần tiền tố dài **2 byte** chứa độ dài vùng dữ liệu được mã hóa. Số byte ghi **không đơn giản bằng** `string.length()` hay `string.getBytes(StandardCharsets.UTF_8).length`. Nếu cần truy cập trực tiếp phần tử thứ N trong một tệp chuỗi dài thay đổi, phải có chỉ mục offset, bảng độ dài hoặc một định dạng bản ghi cố định được định nghĩa trước.

Khi phối hợp nhiều thao tác đọc/ghi trên cùng tệp, phải ghi nhớ định dạng nhị phân và offset của từng trường. Đọc `writeInt` bằng `readShort` không “hiểu” tự động cấu trúc; nó chỉ đọc hai byte và để pointer ở vị trí tương ứng.

## 9. `RandomAccessFile`, `FileChannel` và tính đồng thời

`RandomAccessFile` là API dễ học khi cần đọc/ghi các kiểu dữ liệu ngay tại một vị trí. Với NIO, `FileChannel` cho phép làm việc với `ByteBuffer`, thao tác vị trí `position(long)`, hoặc đọc/ghi theo vị trí tường minh như `read(buffer, position)` và `write(buffer, position)`.

Nếu lấy channel bằng `raf.getChannel()` thì **vị trí của channel và file pointer của `RandomAccessFile` có liên hệ**. Thay đổi vị trí trên một bên hoặc đọc/ghi làm thay đổi vị trí cũng có thể ảnh hưởng đến vị trí nhìn thấy từ bên kia. Không nên trộn các thao tác trên cùng handle rồi giả định có hai con trỏ độc lập.

Ngoài ra, **file pointer là trạng thái thay đổi được**. Nếu nhiều luồng cùng chia sẻ một `RandomAccessFile` và thực hiện cặp lệnh `seek(offset)` → `writeInt(value)`, luồng khác có thể làm thay đổi pointer xen giữa, khiến lệnh ghi diễn ra ở offset sai. Để bảo toàn thao tác logic, cần cơ chế đồng bộ phù hợp, hoặc dùng API đọc/ghi theo vị trí tường minh khi thích hợp. Việc lựa chọn còn phụ thuộc yêu cầu nguyên tử, tính nhất quán và khóa tệp; không mặc định một file pointer dùng chung là an toàn trong ứng dụng đồng thời.

Thực hành tốt là sở hữu rõ tài nguyên qua `try-with-resources`, tránh dùng chung handle khi không có thiết kế đồng bộ và ghi rõ định dạng dữ liệu đang lưu trong tệp.

## 10. Những lỗi thường gặp và cách sửa

| Lỗi | Hệ quả | Cách đúng |
| --- | --- | --- |
| Nghĩ `seek(5)` nghĩa là tiến thêm 5 byte | Đọc/ghi tại vị trí sai | `seek` đặt **offset tuyệt đối**; muốn tiến từ vị trí hiện tại thì tính `getFilePointer() + delta` và kiểm tra tràn số |
| Dùng chỉ số bản ghi thay cho offset byte | Lệch dữ liệu | `seek(index * recordSize)` với phép tính `long` |
| Dùng `writeInt` nhưng nghĩ tăng một byte | Tính sai offset các trường | Ghi nhớ `int` chiếm 4 byte |
| Nghĩ `seek` tự kéo dài tệp | Độ dài không như dự đoán | Chỉ ghi hoặc `setLength` mới có thể làm dài tệp |
| Mong chờ `writeByte` “chèn” byte | Ghi đè dữ liệu hiện có | Thiết kế quy trình dịch dữ liệu khi cần chèn |
| Luôn gọi `readInt` tại EOF | `EOFException` | Kiểm tra giới hạn, xử lý ngoại lệ |
| Coi ký tự là byte | Offset sai với văn bản Unicode | Theo dõi byte thực và charset/định dạng |
| Tin vùng mới mở rộng luôn bằng 0 | Dữ liệu không xác định | Khởi tạo giá trị cần thiết bằng thao tác ghi |
| Dùng chung một pointer từ nhiều luồng không đồng bộ | Đọc/ghi sai vị trí | Đồng bộ hoặc chuyển sang thiết kế có vị trí tường minh |
| Quên đóng `RandomAccessFile` | Rò rỉ descriptor/khóa tài nguyên | `try-with-resources` |

## 11. Tự kiểm tra hiểu bài

Giả sử một `RandomAccessFile` mới mở ở mode `"rw"` đang trỏ vào tệp rỗng:

```java
raf.writeLong(10L);       // A
raf.seek(2);              // B
raf.writeByte(99);        // C
raf.seek(8);              // D
int value = raf.read();   // E
```

Đây là đoạn mã để suy luận, không phải chương trình Java hoàn chỉnh. Nếu tất cả lệnh I/O thành công:

- Sau **A**, pointer là **8**, độ dài tệp là **8**.
- Sau **B**, pointer là **2**, độ dài vẫn **8**.
- Sau **C**, pointer là **3**, độ dài vẫn **8** vì chỉ ghi đè một byte tại offset 2.
- Sau **D**, pointer là **8**.
- Tại **E**, `value == -1` vì đang ở EOF; pointer vẫn là **8**.

Bài tập này cho thấy file pointer là **tọa độ byte của lần I/O tiếp theo**, còn `length()` là độ dài dữ liệu; hai giá trị thường trùng nhau khi ở EOF nhưng không đồng nhất về ý nghĩa.

## 12. Ghi nhớ khi sử dụng

1. **`getFilePointer()` trả về offset byte hiện tại**, kiểu `long`, không phải số dòng/ký tự.
2. **`seek(pos)` đặt offset tuyệt đối không âm**; có thể vượt EOF nhưng không tự thay đổi `length()`.
3. Đọc và ghi có thể dịch pointer theo **số byte đã thao tác**; ghi ở vị trí cũ là ghi đè.
4. Cẩn thận **EOF, `EOFException`, offset tràn số, dữ liệu ở vùng mở rộng, định dạng byte và I/O lỗi**.
5. Với bản ghi độ dài cố định, tính `offset = index * recordSize` bằng `long` và xác minh giới hạn.
6. Không chia sẻ file pointer giữa các luồng nếu thiếu phương án đồng bộ; nên đóng file bằng `try-with-resources`.

**Tài liệu chuẩn:** Java SE 17 API của `java.io.RandomAccessFile`, `java.io.DataInput`, `java.io.DataOutput` và `java.nio.channels.FileChannel`.
