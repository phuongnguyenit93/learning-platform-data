# `RandomAccessFile.length()`, `setLength()` và vùng dữ liệu chưa được ghi

## 1. Mục tiêu và phạm vi

Khi truy cập ngẫu nhiên bằng `java.io.RandomAccessFile`, chương trình có thể di chuyển con trỏ đến bất kỳ vị trí byte hợp lệ nào, đọc hoặc ghi tại vị trí đó, xem độ dài tệp và chủ động thay đổi độ dài. Ba thao tác dễ bị nhầm với nhau là:

- `length()`: hỏi **độ dài logic hiện tại của tệp**, tính bằng byte.
- `seek(position)`: thay đổi **vị trí con trỏ tệp** dùng cho lần đọc/ghi tiếp theo.
- `setLength(newLength)`: thay đổi **độ dài logic** của tệp, có thể cắt bớt hoặc kéo dài tệp.

Bài tập trung vào hành vi của `RandomAccessFile` (Java 17+), đặc biệt là những byte nằm trong vùng được kéo dài nhưng chưa được ứng dụng ghi giá trị xác định. Bạn sẽ hiểu khi nào việc đọc trả EOF, vì sao không được giả định phần mở rộng chứa toàn byte `0`, và cách chủ động khởi tạo dữ liệu nếu định dạng tệp cần kết quả chắc chắn.

## 2. Hai đại lượng độc lập: độ dài và con trỏ

Với một `RandomAccessFile raf`:

| API | Đơn vị và ý nghĩa | Có thay đổi độ dài tệp? |
| --- | --- | --- |
| `raf.length()` | `long`: tổng số byte của tệp tại thời điểm gọi | Không |
| `raf.getFilePointer()` | `long`: vị trí byte của thao tác đọc/ghi tiếp theo | Không |
| `raf.seek(pos)` | Đặt con trỏ đến offset `pos` (từ đầu tệp, bắt đầu từ 0) | Không, chỉ di chuyển con trỏ |
| `raf.read()` | Đọc byte hiện tại, trả giá trị 0–255 hoặc `-1` nếu EOF | Không |
| `raf.write(value)` | Ghi tại con trỏ và đẩy con trỏ đi một byte | **Có thể**, nếu ghi tới/vượt cuối tệp |
| `raf.setLength(n)` | Đặt độ dài logic mới thành `n` byte | Có, nếu `n` khác độ dài cũ |

Ví dụ tệp chứa ba byte đã được ghi là `ABC`:

```text
offset             0    1    2    3
byte đã ghi        A    B    C    | EOF
length() = 3                     ^
getFilePointer() có thể là 0, 2, 3, 10... tùy seek/đọc/ghi
```

Offset là **byte offset**, không phải vị trí ký tự Unicode. Một ký tự tiếng Việt mã hóa UTF-8 có thể chiếm nhiều byte; `length()` không cho biết số lượng ký tự. Một lần gọi `seek(10)` trên tệp dài 3 byte là hợp lệ (miễn vị trí không âm); con trỏ sẽ ở offset 10 nhưng `length()` vẫn là 3. Cho đến khi có thao tác ghi hoặc đổi độ dài, vùng giữa offset 3 và 10 chưa vì `seek` mà trở thành một phần của tệp.

Phân biệt hai khái niệm sau:

- **EOF (end of file)** là ranh giới cuối độ dài logic. Nếu con trỏ tại hoặc vượt EOF, `read()` trả `-1`.
- **Vùng dữ liệu chưa được ứng dụng ghi rõ ràng** có thể **nằm bên trong độ dài logic** sau khi tệp bị kéo dài. Không được xem vùng này là EOF chỉ vì ứng dụng chưa ghi nội dung vào đó.

Cả `length()` và `getFilePointer()` đều trả `long` vì tệp có thể lớn hơn giới hạn của `int`. Kết quả đo tệp có thể thay đổi khi tiến trình khác sửa cùng tệp; các API không tạo ra một snapshot nhất quán cho mọi thao tác tiếp theo.

## 3. `setLength(newLength)` khi thu nhỏ tệp

Nếu độ dài hiện tại là `L` và gọi `setLength(n)` với `0 <= n < L`, các byte từ offset `n` trở đi bị loại khỏi nội dung logic của tệp. Đây là **truncate**, thao tác có thể làm mất dữ liệu.

Ví dụ trước khi cắt:

```text
offset       0   1   2   3   4   5   6
byte         A   B   C   D   E   F   | EOF
length = 6
pointer = 5
```

Sau `setLength(3)`:

```text
offset       0   1   2   3
byte         A   B   C   | EOF
length = 3
pointer = 3
```

**Quy tắc con trỏ:** nếu vị trí hiện tại lớn hơn độ dài mới khi thu nhỏ, `RandomAccessFile` đưa con trỏ về đúng `newLength`. Nếu vị trí hiện tại nhỏ hơn hoặc bằng độ dài mới, con trỏ giữ nguyên. Ví dụ: pointer đang ở 1 khi cắt xuống 3 thì vẫn ở 1; pointer đang ở 5 khi cắt xuống 3 thì trở thành 3.

Trường hợp `setLength(0)` cắt toàn bộ nội dung tệp, không xóa chính tệp và không tự tạo bản sao lưu. Lệnh này cần được sử dụng cẩn thận đối với tệp dữ liệu đang có giá trị. Việc tệp bị truncate không bảo đảm có thể khôi phục phần đã bị cắt bằng cách kéo dài lại.

## 4. `setLength(newLength)` khi kéo dài tệp

Nếu độ dài hiện tại `L` và `newLength > L`, tệp được kéo dài đến đúng độ dài logic `newLength`. Theo hợp đồng API của `RandomAccessFile`, **nội dung phần được kéo dài không được xác định** (`the contents of the extended portion of the file are not defined`).

```text
Ban đầu: length = 3
offset             0   1   2   3
nội dung           A   B   C   | EOF

Sau setLength(8):
offset             0   1   2   3   4   5   6   7   8
nội dung           A   B   C   ?   ?   ?   ?   ?   | EOF
                               └──── vùng chưa có giá trị do ứng dụng xác định
length = 8
```

Dấu `?` **không** biểu thị EOF; đó là những vị trí byte hợp lệ bên trong file, nhưng bạn không được dựa vào giá trị của chúng theo hợp đồng Java. Trên nhiều hệ điều hành và filesystem, các “lỗ” có thể được đọc như byte 0, song đó không phải cơ sở portable để thiết kế định dạng dữ liệu. Việc được hệ thống tệp cấp phát vật lý ra sao cũng không đồng nghĩa với việc ứng dụng đã ghi và xác nhận dữ liệu.

Khi **mở rộng** tệp, `setLength` không dịch chuyển con trỏ đang ở vị trí hợp lệ trước đó. Con trỏ có thể đang nằm tại offset cũ hoặc thậm chí vượt EOF mới vì `seek` trước đó. Chỉ quy tắc cắt bớt khi pointer vượt độ dài mới mới tự động điều chỉnh pointer.

Lưu ý:

- `setLength` nhận giá trị `long` không âm; giá trị âm gây `IllegalArgumentException`.
- Nếu tệp không được mở để ghi (ví dụ mode `"r"`), yêu cầu đổi độ dài không thể thực hiện thành công và có thể ném `IOException`.
- Kéo dài, cắt bớt hoặc lấy metadata cũng có thể thất bại vì quyền, lỗi I/O, giới hạn dung lượng, quota hoặc hệ thống tệp. Không nên che giấu `IOException`.
- `setLength` không bảo đảm dữ liệu được “đặt trước” thành các block vật lý thực tế. Filesystem hỗ trợ sparse file có thể chỉ cấp phát block khi chúng được ghi.

## 5. `seek` vượt EOF rồi mới ghi: vùng trống có ý nghĩa gì?

Giả sử tệp chứa `ABC` (dài 3 byte). Sau `seek(10)`:

```text
0  1  2  3  4  5  6  7  8  9 10
A  B  C  | EOF                  ^ pointer
length = 3; pointer = 10
```

Nếu gọi `read()` lúc này, kết quả là `-1` vì pointer nằm ngoài độ dài logic. Nếu thay bằng `writeByte('Z')` tại offset 10, thao tác ghi sẽ làm tệp có độ dài ít nhất 11 byte. Byte ở offset 10 được ứng dụng ghi rõ là `Z`; **các byte offset 3–9 không nên bị diễn giải như dữ liệu đã khởi tạo hợp lệ**.

```text
0  1  2  3  4  5  6  7  8  9 10 11
A  B  C  ?  ?  ?  ?  ?  ?  ?  Z  | EOF
length = 11; pointer = 11
```

Đừng gộp “vùng chưa từng ghi”, “vùng được tạo do kéo dài” và “vùng EOF” thành một trạng thái. Nếu định dạng tệp có các record hợp lệ, cần có cách đánh dấu record đã tạo, bitmap, header, sentinel do bạn thực sự ghi, hoặc khởi tạo đầy đủ từng byte mà chương trình cần đọc.

## 6. Ví dụ Java 17+ chạy được: kiểm chứng length, pointer và EOF

Lưu tệp **`RandomAccessLengthDemo.java`**:

```java
import java.io.RandomAccessFile;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

public class RandomAccessLengthDemo {
    public static void main(String[] args) throws Exception {
        Path path = Files.createTempFile("raf-length-", ".bin");

        try {
            try (RandomAccessFile raf =
                         new RandomAccessFile(path.toFile(), "rw")) {

                // Ba byte ASCII đã xác định: A B C
                raf.write(new byte[] {65, 66, 67});
                System.out.println("after write: length=" + raf.length()
                        + ", pointer=" + raf.getFilePointer());

                // Chỉ dịch con trỏ; tuyệt đối chưa làm dài file.
                raf.seek(10);
                System.out.println("after seek(10): length=" + raf.length()
                        + ", pointer=" + raf.getFilePointer());
                System.out.println("read beyond EOF=" + raf.read());

                // Mở rộng file nhưng không dựa vào các byte chưa ghi.
                raf.seek(3);
                raf.setLength(12);
                System.out.println("after setLength(12): length=" + raf.length()
                        + ", pointer=" + raf.getFilePointer());

                // Ghi và đọc đúng một byte mà ta biết chắc giá trị.
                raf.seek(10);
                raf.writeByte('Z');
                raf.seek(10);
                System.out.println("known byte at 10="
                        + (char) raf.readUnsignedByte());

                raf.seek(12);
                System.out.println("read at 12=" + raf.read());

                // Pointer đang ở 12; cắt file về 2 => pointer về 2.
                raf.setLength(2);
                System.out.println("after setLength(2): length=" + raf.length()
                        + ", pointer=" + raf.getFilePointer());

                raf.seek(0);
                byte[] prefix = new byte[2];
                raf.readFully(prefix);
                System.out.println("remaining prefix="
                        + new String(prefix, StandardCharsets.US_ASCII));
            }
        } finally {
            Files.deleteIfExists(path);
        }
    }
}
```

Chạy với JDK 17 trở lên:

```bash
javac RandomAccessLengthDemo.java
java RandomAccessLengthDemo
```

Stdout dự kiến khi các thao tác I/O thành công:

```text
after write: length=3, pointer=3
after seek(10): length=3, pointer=10
read beyond EOF=-1
after setLength(12): length=12, pointer=3
known byte at 10=Z
read at 12=-1
after setLength(2): length=2, pointer=2
remaining prefix=AB
```

Vì sao ví dụ có thể có output xác định? Chương trình **chỉ đọc những byte đã được ghi rõ** (`ABC`, `Z`) hoặc đọc tại vị trí EOF (trả `-1`). Không hề in hay kiểm tra giá trị của vùng kéo dài ở offset 3–9 và 11. `Files.createTempFile` tạo tệp mới riêng; `try-with-resources` đóng `RandomAccessFile` trước khi `finally` xóa tệp.

Nếu máy không cho phép tạo/ghi/xóa tệp trong thư mục tạm, thao tác sẽ ném lỗi và ví dụ sẽ không có toàn bộ stdout ở trên; đây là lỗi môi trường I/O chứ không thay đổi quy tắc byte offset.

## 7. Khởi tạo vùng mở rộng để dữ liệu có giá trị xác định

Nếu định dạng tệp yêu cầu byte mới phải là 0 (chẳng hạn mảng bản ghi cố định), hãy **ghi 0 vào toàn bộ vùng cần khởi tạo** thay vì tin rằng `setLength` tự làm điều đó theo hợp đồng API.

Ví dụ hoàn chỉnh **`InitializeExtendedRegion.java`**:

```java
import java.io.IOException;
import java.io.RandomAccessFile;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Arrays;

public class InitializeExtendedRegion {
    private static void fillWithZeros(
            RandomAccessFile raf, long from, long endExclusive)
            throws IOException {
        if (from < 0 || endExclusive < from) {
            throw new IllegalArgumentException("Invalid byte interval");
        }

        byte[] zeros = new byte[8192];
        raf.seek(from);
        long remaining = endExclusive - from;

        while (remaining > 0) {
            int count = (int) Math.min((long) zeros.length, remaining);
            raf.write(zeros, 0, count);
            remaining -= count;
        }
    }

    public static void main(String[] args) throws Exception {
        Path path = Files.createTempFile("raf-initialize-", ".bin");
        try {
            try (RandomAccessFile raf =
                         new RandomAccessFile(path.toFile(), "rw")) {
                raf.write(new byte[] {10, 20});

                long originalLength = raf.length();
                long targetLength = originalLength + 5;

                raf.setLength(targetLength);
                fillWithZeros(raf, originalLength, targetLength);

                raf.seek(0);
                byte[] bytes = new byte[(int) raf.length()];
                raf.readFully(bytes);
                System.out.println(Arrays.toString(bytes));
            }
        } finally {
            Files.deleteIfExists(path);
        }
    }
}
```

```bash
javac InitializeExtendedRegion.java
java InitializeExtendedRegion
```

Stdout khi thành công:

```text
[10, 20, 0, 0, 0, 0, 0]
```

Cơ chế: chương trình ghi hai byte đầu (`10`, `20`), mở rộng độ dài từ 2 lên 7, sau đó ghi **chính xác năm byte 0** lên offset 2–6. Vì vùng đó đã được ứng dụng ghi, lần đọc sau có thể phụ thuộc vào giá trị 0 (với điều kiện không có tác nhân khác sửa tệp).

Đây là một ví dụ nhỏ để in toàn bộ tệp. Với tệp lớn, **không** cấp phát một mảng byte có kích thước bằng `raf.length()`; hãy đọc/ghi theo chunk hữu hạn, có giới hạn và kiểm tra overflow khi tính offset. Phương thức `fillWithZeros` đã ghi theo block 8192 byte để tránh tạo mảng khổng lồ cho vùng cần khởi tạo.

**Đánh đổi quan trọng:** ghi hàng gigabyte byte 0 thật sự tốn thời gian và I/O, đồng thời có thể làm mất lợi ích sparse storage. Nếu hệ thống chỉ cần phân biệt bản ghi tồn tại hay chưa, metadata quản lý trạng thái bản ghi thường hợp lý hơn so với khởi tạo toàn bộ vùng dung lượng lớn.

## 8. `read()`, `readFully()` và nội dung chưa ghi

Phương thức đọc cũng dễ gây nhầm:

| Thao tác | Khi con trỏ đúng EOF hoặc vượt EOF | Khi con trỏ nằm trong vùng mở rộng chưa khởi tạo |
| --- | --- | --- |
| `read()` | Trả `-1` | Có thể đọc một byte; **không dựa vào giá trị trả về** |
| `read(byte[])` | Trả `-1` khi không thể đọc byte nào do EOF | Có thể trả số byte đã đọc; dữ liệu vùng chưa khởi tạo không có giá trị ứng dụng bảo đảm |
| `readFully(buffer)` | Ném `EOFException` nếu không đủ byte theo yêu cầu | Có thể hoàn thành nếu đủ byte theo độ dài logic, nhưng không chứng minh các byte là record hợp lệ |
| `length()` | Trả tổng chiều dài hiện tại | Bao gồm cả phần tệp đã được mở rộng dù nội dung phần đó chưa xác định |

`readFully` là hữu ích khi định dạng yêu cầu đọc chính xác `N` byte và muốn biết khi nào bị thiếu dữ liệu do EOF. Nhưng nó **không thể tự chứng minh** rằng toàn bộ `N` byte đã được ứng dụng khởi tạo có ý nghĩa. Đó là nhiệm vụ của định dạng tệp (header, record count, trạng thái bản ghi, checksum hoặc metadata tương ứng).

Ví dụ với file 3 byte `ABC`: `seek(2)` rồi `readFully(new byte[2])` sẽ ném `EOFException` vì chỉ còn 1 byte. Ngược lại, nếu đã `setLength(10)`, lệnh đọc 2 byte từ offset 2 có thể trả đủ hai byte về mặt độ dài, nhưng byte offset 3 thuộc vùng chưa được ứng dụng viết giá trị xác định.

Đối với `read(byte[])`, không giả định nó luôn đọc đủ độ dài của mảng trong một lần gọi; cần kiểm tra giá trị trả về hoặc dùng `readFully` khi yêu cầu đủ byte.

## 9. Độ dài logic, dung lượng vật lý và sparse file

Khi gọi `setLength(1_000_000_000L)`, `length()` có thể trả một tỷ byte dù quá trình chưa ghi một tỷ byte dữ liệu. Nhiều filesystem hỗ trợ **sparse file**, nơi các vùng chưa có block thực tế được ánh xạ hoặc cấp phát theo chính sách riêng.

Có ba khái niệm phải phân biệt:

1. **Logical size:** độ dài tệp mà Java báo qua `length()` hoặc `Files.size(path)`.
2. **Allocated storage:** block/bộ nhớ lưu trữ thực được cấp phát theo filesystem; có thể khác đáng kể logical size.
3. **Initialized application data:** những byte mà ứng dụng đã ghi, hoặc có đủ bằng chứng theo định dạng để diễn giải thành dữ liệu hợp lệ.

`RandomAccessFile.setLength` không phải API bảo đảm cấp phát block vật lý hay bảo đảm có sẵn dung lượng cho mọi lần ghi sau. Sparse file, giới hạn quota, compression và filesystem mạng khiến cách lưu trữ thực tế khác nhau. Nếu cần đặt trước dung lượng vật lý theo cam kết cụ thể, hãy nghiên cứu API của hệ điều hành/filesystem thay vì coi `setLength` là cam kết portable.

Đừng diễn giải tệp có logical size lớn là đã sở hữu tương ứng từng ấy disk space hoặc chắc chắn có thể ghi kín tệp mà không gặp `IOException`. Cũng đừng dùng thống kê dung lượng từ FileStore để xác nhận từng byte đã khởi tạo.

## 10. Tình huống áp dụng: định dạng bản ghi truy cập ngẫu nhiên

Giả sử một tệp lưu các record dài cố định 32 byte, có header 16 byte:

```text
header        record 0       record 1       record 2
[0 .. 15]     [16 .. 47]     [48 .. 79]     [80 .. 111]
```

Offset đầu của record thứ `i` là `16 + i * 32` (theo **byte**, với `i >= 0`). `raf.seek(offset)` cho phép đọc hoặc ghi record mà không đi qua toàn bộ các record trước. Một câu hỏi quan trọng: nếu bạn mới ghi record 0 và record 2, record 1 có hợp lệ không?

**Không thể chỉ dựa vào `length()` để trả lời.** Khi ghi record 2, logical size có thể kéo dài qua record 1. Một đọc 32 byte tại offset 48 có thể hoàn thành theo logical size, nhưng những byte đó chưa được ứng dụng định nghĩa thành record 1. Các cách thiết kế phù hợp tùy yêu cầu là:

- Duy trì record count/bitmap/trạng thái slot và **ghi trạng thái hợp lệ sau khi ghi đủ payload** (xét thêm tính crash-safe nếu triển khai thật).
- Khởi tạo tất cả slot cần đọc với giá trị mặc định do ứng dụng thực sự ghi, rồi quy ước ý nghĩa giá trị đó.
- Ghi header chứa phiên bản định dạng, kích thước record và thông tin nhận biết record hợp lệ; kiểm tra offset/length trước khi diễn giải bytes.

Khi tính `offset = headerSize + index * recordSize`, phải kiểm tra chỉ số đầu vào, khả năng tràn số `long` (`Math.multiplyExact` / `Math.addExact` có thể giúp), kích thước record và quyền truy cập. Một `seek` hợp lệ về mặt số học không có nghĩa dữ liệu tại đó tồn tại hoặc hợp lệ.

## 11. So sánh các API liên quan

| API | Điều đáng nhớ |
| --- | --- |
| `RandomAccessFile.length()` | Độ dài logic hiện tại (byte) |
| `RandomAccessFile.setLength(n)` | Có thể thu nhỏ **hoặc kéo dài** đến `n`; vùng kéo dài có nội dung không xác định |
| `RandomAccessFile.seek(n)` | Chỉ chuyển con trỏ; chưa ghi thì không thay đổi length |
| `Files.size(path)` | Lấy logical size qua đường dẫn; cũng có thể thất bại nếu không đọc metadata được |
| `FileChannel.size()` | Lấy kích thước file qua channel |
| `FileChannel.truncate(n)` | Nếu `n` nhỏ hơn size hiện tại, cắt xuống `n`; nếu `n` >= size hiện tại thì **không kéo dài file** |
| `FileChannel.position(n)` | Đổi vị trí channel; bản thân đổi vị trí không tự kéo dài file |

Điểm cần tránh: gọi `channel.truncate(1000)` trên tệp dài 10 byte **không tương đương** `raf.setLength(1000)`. `truncate` của `FileChannel` chỉ có tác dụng thu nhỏ khi kích thước được chỉ định nhỏ hơn kích thước hiện tại. Dù xử lý cùng một tệp, API có hợp đồng khác nhau.

Nếu sử dụng đồng thời `RandomAccessFile` và `getChannel()` của chính nó, vị trí của file descriptor/channel có quan hệ chung; cần hiểu cách các thao tác thay đổi position và tránh giả định chúng độc lập. Trong ví dụ học tập, thao tác trên một đối tượng `RandomAccessFile` giúp hành vi đơn giản, dễ kiểm tra.

## 12. Lỗi thường gặp, kiểm thử và xử lý lỗi

1. **Giả định `seek(largeOffset)` kéo dài file:** chỉ ghi sau seek hoặc gọi `setLength` mới có thể thay đổi độ dài.
2. **Giả định phần kéo dài luôn bằng `0`:** Java không xác định nội dung vùng đó; phải tự ghi dữ liệu cần thiết.
3. **Dùng `length()` làm số record đã ghi:** các “lỗ” có thể nằm trong vùng logical length; nên quản lý record hợp lệ bằng metadata.
4. **Tưởng `setLength(0)` là dời pointer về đầu mà không mất dữ liệu:** nó cắt toàn bộ nội dung. Muốn về đầu chỉ gọi `seek(0)`.
5. **Bỏ qua quy tắc pointer khi truncate:** nếu pointer đang vượt newLength, API đưa pointer về newLength. Kiểm tra `getFilePointer()` khi code phụ thuộc vị trí.
6. **Giả định extend là preallocate vật lý:** logical size, allocated size và khả năng ghi thành công là các thứ khác nhau.
7. **Không xử lý ngoại lệ:** `seek(-1)` và `setLength(-1)` không hợp lệ; các thao tác I/O có thể thất bại vì quyền, tệp bị thay đổi hoặc storage cạn.
8. **Nhầm byte với ký tự:** xử lý binary offset theo byte; nếu dùng UTF-8, cần encoding và cấu trúc record rõ ràng.
9. **Ghi/cắt tệp đang được tiến trình khác sử dụng mà không phối hợp:** có thể tạo dữ liệu bị mất, ghi chồng hoặc đọc không nhất quán. Phân quyền, khóa và giao thức cập nhật phải được thiết kế phù hợp.
10. **Kiểm thử các giá trị không được API bảo đảm:** test portable nên khẳng định `length`, quy tắc pointer, EOF và các byte đã chủ động ghi; không khẳng định giá trị vùng chưa ghi.

Một bộ kiểm tra nên có các tình huống:

- Tệp mới dài 0; `seek(100)` rồi `length()` vẫn 0.
- Ghi 3 byte; `length()` bằng 3; đọc tại offset 3 trả `-1`.
- `setLength(8)`; `length()` bằng 8, con trỏ giữ nguyên nếu không vượt điều kiện truncate.
- Sau khi ghi rõ vùng mở rộng, đọc lại chính những byte đó phải đúng.
- `setLength(2)` từ tệp dài hơn; phần sau offset 1 không còn thuộc logical file, pointer đang vượt 2 phải về 2.
- `setLength(0)` rồi đọc từ đầu phải báo EOF.
- Thử giá trị âm, mode chỉ đọc và lỗi I/O phù hợp, tránh biến kết quả lỗi môi trường thành một kết luận sai về nội dung chưa ghi.

## 13. Câu hỏi tự kiểm tra

1. Tệp dài 5 byte. Sau `seek(100)`, `length()` và `getFilePointer()` lần lượt là bao nhiêu? Điều gì xảy ra nếu gọi `read()`?
2. Tệp dài 5 byte, pointer ở 4. Sau `setLength(20)`, độ dài và pointer là bao nhiêu? Có được khẳng định byte ở offset 19 bằng 0 không?
3. Tệp dài 20 byte, pointer ở 18. Sau `setLength(7)`, pointer còn bao nhiêu? Nội dung ở offset 7–19 có còn được phép đọc như dữ liệu hiện tại không?
4. Vì sao sau `setLength(20)`, lệnh `readFully(new byte[5])` tại offset 10 có thể đọc đủ byte nhưng vẫn chưa chứng minh đó là một record hợp lệ?
5. Nếu cần khởi tạo 2 GiB byte 0 một cách có thể kiểm chứng ở tầng ứng dụng, bạn sẽ tránh cấp phát mảng khổng lồ bằng cách nào? Đánh đổi với sparse storage là gì?
6. `FileChannel.truncate(100)` và `RandomAccessFile.setLength(100)` có cho cùng kết quả khi tệp ban đầu dài 10 byte không?

## 14. Ghi nhớ

- `length()` là **số byte logic** hiện có; `getFilePointer()` là **vị trí** đọc/ghi tiếp theo. Hai giá trị độc lập.
- `seek()` tự nó không kéo dài tệp. Ghi vượt EOF hoặc `setLength` mở rộng mới có thể làm logical length tăng.
- `setLength` thu nhỏ thì cắt nội dung và đưa pointer về `newLength` nếu pointer đang lớn hơn độ dài mới.
- `setLength` kéo dài tạo ra những byte bên trong logical file có **nội dung không được Java xác định**; không nên xem chúng là dữ liệu đã khởi tạo.
- Nếu nghiệp vụ cần dữ liệu mặc định rõ ràng, hãy **ghi rõ các byte cần khởi tạo** hoặc quản lý trạng thái hợp lệ bằng cấu trúc dữ liệu riêng. Kiểm tra cùng lúc logical length, pointer, EOF, dữ liệu đã ghi và lỗi I/O.
