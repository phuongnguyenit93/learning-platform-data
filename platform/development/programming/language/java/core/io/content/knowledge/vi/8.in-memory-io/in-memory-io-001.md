# ByteArrayInputStream và ByteArrayOutputStream: I/O byte trong bộ nhớ Java

## 1. Vì sao cần luồng byte trong bộ nhớ?

Trong Java, `InputStream` mô tả một nguồn byte mà chương trình có thể đọc, còn `OutputStream` mô tả một đích nhận byte. Nguồn/đích không nhất thiết là tệp hay kết nối mạng: đôi khi tất cả dữ liệu đều nằm trong RAM. Hai lớp thuộc `java.io` giải quyết trường hợp đó:

- **`ByteArrayInputStream`** cho phép **đọc** tuần tự từ một mảng `byte[]` đã có.
- **`ByteArrayOutputStream`** cho phép **ghi** từng byte hoặc từng khối byte vào một vùng nhớ tự tăng, rồi lấy kết quả thành `byte[]`.

Nhờ triển khai cùng các API `InputStream` và `OutputStream`, chúng có thể kết nối với những phương thức xử lý luồng thông thường mà không cần tệp thật. Đây là công cụ thuận tiện để kiểm thử, biến đổi nội dung nhỏ trong bộ nhớ, lắp ghép payload và dùng các API chấp nhận một luồng.

~~~text
byte[] có sẵn                        byte[] kết quả
      │                                    ▲
      ▼                                    │ toByteArray()
ByteArrayInputStream ─ read() ─► Xử lý ─ write() ─► ByteArrayOutputStream
      ▲                                    │
      │ đọc từ vùng nhớ                   │ ghi vào vùng nhớ tự mở rộng
      └───────────── không bắt buộc có ổ đĩa hay socket ────────────┘
~~~

Điểm phân biệt quan trọng: tên `Stream` ở đây chỉ **giao diện luồng byte**, không có nghĩa JVM nhất thiết mở file descriptor hoặc socket. Hai lớp này hoạt động trên bộ nhớ Java. Tuy vậy, `byte[]` có giới hạn kích thước và tiêu thụ heap; việc lưu cả tệp lớn vào RAM có thể gây áp lực bộ nhớ.

Bài này giải thích cấu tạo, hợp đồng phương thức, khác biệt về sao chép/chia sẻ mảng, vòng đời, chuyển đổi văn bản theo charset, lỗi thường gặp và các chương trình Java 17+ có thể biên dịch độc lập.

## 2. Hai lớp có vai trò đối xứng nhưng cách lưu dữ liệu khác nhau

| Đặc điểm | `ByteArrayInputStream` | `ByteArrayOutputStream` |
| --- | --- | --- |
| Hướng dữ liệu | Đọc từ mảng byte đầu vào | Ghi vào bộ đệm byte đang tăng |
| Dữ liệu lúc tạo | Cần một `byte[]` nguồn | Có thể tạo rỗng, tùy chọn dung lượng ban đầu |
| Kích thước hữu ích | Phần đọc được xác định khi khởi tạo | Tăng theo lượng byte đã ghi |
| Con trỏ | Có vị trí đọc hiện tại | Có số byte đã ghi (`size()`) |
| API chính | `read()`, `read(byte[],off,len)`, `skip()`, `available()`, `mark()`, `reset()` | `write(int)`, `write(byte[],off,len)`, `writeBytes()`, `writeTo()`, `toByteArray()`, `size()`, `reset()` |
| Có mở tệp/socket? | Không | Không |
| Đóng có làm mất khả năng dùng? | `close()` là thao tác không có hiệu lực theo hợp đồng lớp | `close()` là thao tác không có hiệu lực theo hợp đồng lớp |
| Sao chép dữ liệu lúc tạo/lấy ra | Constructor lưu tham chiếu tới mảng nguồn, không tự sao chép nó | `toByteArray()` tạo **bản sao** chỉ gồm những byte đã ghi |

**Đừng đồng nhất hai hướng:**

- Với đầu vào, ta đã có mảng và chỉ cần đi qua nó lần lượt. Khi đọc, vị trí tăng; kích thước nguồn không tự tăng.
- Với đầu ra, ta chưa cần biết chính xác dung lượng cuối. Mỗi `write` có thể khiến bộ đệm nội bộ mở rộng. `size()` là số byte hợp lệ, không nhất thiết là dung lượng mảng nội bộ.

Trong các ví dụ dưới, tên lớp được viết đầy đủ hoặc import từ `java.io`. Tất cả đều là API nền tảng, không cần thư viện ngoài.

## 3. ByteArrayInputStream: đọc từ byte[] như một InputStream

### 3.1. Hai constructor quan trọng

~~~java
byte[] data = {10, 20, 30, 40};

// Đọc toàn bộ mảng:
ByteArrayInputStream all = new ByteArrayInputStream(data);

// Chỉ đọc một vùng liên tiếp, bắt đầu ở offset 1, tối đa length 2:
ByteArrayInputStream slice = new ByteArrayInputStream(data, 1, 2);
~~~

Đoạn trên minh họa API; khi dùng trong một lớp riêng cần `import java.io.ByteArrayInputStream`. Với `slice`, dữ liệu đọc được là byte `20` và `30`. Tham số thứ ba là **độ dài** (`length`), không phải chỉ số kết thúc. Hãy cấp `offset` và `length` hợp lệ, không dựa vào hành vi với chỉ số âm hoặc vùng ngoài mảng.

Về mặt tư duy, một `ByteArrayInputStream` giữ:

- **`buf`:** tham chiếu đến mảng nguồn.
- **`pos`:** vị trí byte sẽ được đọc tiếp.
- **`count`:** giới hạn kết thúc phần có thể đọc.
- **`mark`:** vị trí ghi dấu để có thể quay lại.

Các trường này được lớp quản lý; ứng dụng thông thường tương tác qua API công khai.

Đặc biệt, constructor **không sao chép byte[]**. Nếu bên ngoài sửa mảng trong khi Scanner hoặc phương thức đọc khác sử dụng `ByteArrayInputStream`, các byte đọc được sau đó có thể bị ảnh hưởng. Muốn đầu vào bất biến theo thời gian, hãy tự tạo bản sao, chẳng hạn `source.clone()`, trước khi truyền vào constructor.

### 3.2. read() và dấu hiệu kết thúc

`int value = in.read()` có hai dạng kết quả:

- `0` đến `255`: giá trị **unsigned** của byte vừa đọc, biểu diễn dưới dạng `int`.
- `-1`: đã đi hết phần dữ liệu của luồng.

Điểm này khác với việc lấy trực tiếp một phần tử `byte` trong Java: `byte` là kiểu có dấu, phạm vi `-128..127`. Byte thô `0xFF` khi đặt trong `byte` có giá trị `-1`, nhưng `InputStream.read()` trả **`255`** cho byte này. Cần dùng `int` để không nhầm dữ liệu `0xFF` với EOF.

Ví dụ độc lập, lưu thành **ByteArrayReadDemo.java**:

~~~java
import java.io.ByteArrayInputStream;

public class ByteArrayReadDemo {
    public static void main(String[] args) throws Exception {
        byte[] bytes = {0, 127, (byte) 0x80, (byte) 0xFF};

        try (ByteArrayInputStream input = new ByteArrayInputStream(bytes)) {
            int value;
            while ((value = input.read()) != -1) {
                System.out.println(value);
            }
            System.out.println("EOF: " + input.read());
        }
    }
}
~~~

Chạy bằng JDK 17+:

~~~bash
javac -encoding UTF-8 ByteArrayReadDemo.java
java ByteArrayReadDemo
~~~

Kết quả chính xác:

~~~text
0
127
128
255
EOF: -1
~~~

Nếu cần chuyển `byte` có dấu sang dạng unsigned `int` trong các thuật toán riêng, dùng `Byte.toUnsignedInt(value)` hoặc `value & 0xFF`. Không cần chuyển kiểu này với kết quả từ `InputStream.read()` vì API đã trả về giá trị trong phạm vi `0..255`.

### 3.3. read(byte[] dst, int off, int len)

Một lần đọc có thể đưa byte vào đoạn của mảng đích:

~~~java
byte[] dst = new byte[8];
int count = input.read(dst, 2, 3);
~~~

Đây là đoạn minh họa: `input` đã được tạo. Nó yêu cầu tối đa ba byte từ nguồn, đặt vào `dst[2]`, `dst[3]`, `dst[4]`. **`count` là số byte thực nhận** (hoặc `-1` nếu EOF khi yêu cầu đọc dữ liệu). Những ô ngoài đoạn được đọc không mang dữ liệu mới của lượt đó.

Với một `ByteArrayInputStream` có dữ liệu sẵn, mỗi lượt đọc thường lấy ngay tối đa lượng byte hiện có. Nhưng khi viết hàm tổng quát nhận `InputStream`, đừng giả định `read(buffer)` luôn lấp đầy mảng: với tệp và mạng, có thể đọc được ít hơn yêu cầu.

Một vòng lặp sao chép đúng:

~~~java
byte[] buffer = new byte[4096];
int count;
while ((count = input.read(buffer)) != -1) {
    output.write(buffer, 0, count);
}
~~~

Đây là đoạn minh họa với `InputStream input`, `OutputStream output` có sẵn, và phương thức bao ngoài xử lý `IOException`. Dùng `count` thay vì `buffer.length` để tránh ghi lại dữ liệu cũ từ phần cuối mảng khi lượt đọc cuối không đầy.

### 3.4. available() và skip()

Đối với `ByteArrayInputStream`, `available()` trả về **số byte còn lại trong phần mảng mà luồng này có thể đọc** mà không bị chặn. Đây là một đặc điểm dễ dự đoán vì toàn bộ dữ liệu vốn đã ở RAM.

Ví dụ một mảng 5 byte, đã đọc hai byte thì `available()` bằng 3. Sau `skip(2)`, còn lại 1. `skip(long n)` chỉ tiến qua nhiều nhất số byte còn lại; không tạo dữ liệu, không đọc ngược khi `n` không dương.

Tuy nhiên, **không khái quát cách hiểu `available()` thành kích thước toàn bộ nội dung của mọi `InputStream`**. Với mạng, file stream hoặc wrapper khác, hợp đồng `available()` thường chỉ nói đến số byte ước tính có thể đọc ngay mà không chặn; giá trị 0 không đồng nghĩa với EOF.

### 3.5. mark(), reset() và khả năng đọc lại

`ByteArrayInputStream` hỗ trợ đánh dấu vị trí và quay lại:

- `markSupported()` trả `true`.
- `mark(int readlimit)` ghi nhớ vị trí đọc hiện tại. Với lớp này, `readlimit` không hạn chế khả năng đánh dấu.
- `reset()` đưa vị trí đọc về mốc đã đánh dấu.
- Nếu không tự đánh dấu, mốc ban đầu tương ứng vị trí lúc tạo luồng (0 đối với constructor toàn mảng, `offset` đối với constructor đọc vùng).

Ví dụ độc lập, **ByteArrayMarkDemo.java**:

~~~java
import java.io.ByteArrayInputStream;

public class ByteArrayMarkDemo {
    public static void main(String[] args) throws Exception {
        byte[] source = {10, 20, 30, 40};

        try (ByteArrayInputStream input = new ByteArrayInputStream(source)) {
            System.out.println("First: " + input.read());
            input.mark(100);
            System.out.println("Second: " + input.read());
            System.out.println("Skipped: " + input.skip(1));
            System.out.println("Fourth: " + input.read());

            input.reset();
            System.out.println("Again: " + input.read());
            System.out.println("Available: " + input.available());
        }
    }
}
~~~

~~~bash
javac -encoding UTF-8 ByteArrayMarkDemo.java
java ByteArrayMarkDemo
~~~

Kết quả:

~~~text
First: 10
Second: 20
Skipped: 1
Fourth: 40
Again: 20
Available: 2
~~~

Dòng `Again: 20` chứng minh `reset()` quay về `mark` sau byte 10; nó không tự quay về đầu mảng khi đã có dấu mới. Với một `InputStream` khác, `markSupported()` có thể trả false hoặc readlimit có ý nghĩa thực sự; đừng áp dụng bảo đảm của `ByteArrayInputStream` lên mọi loại nguồn.

## 4. ByteArrayOutputStream: xây dựng byte[] bằng nhiều lần ghi

### 4.1. Khởi tạo, dung lượng ban đầu và tự mở rộng

`new ByteArrayOutputStream()` bắt đầu với một bộ đệm nội bộ có dung lượng ban đầu mặc định. `new ByteArrayOutputStream(initialSize)` cho phép cung cấp dung lượng ban đầu không âm, hữu ích khi có ước lượng kích thước kết quả.

~~~java
ByteArrayOutputStream output = new ByteArrayOutputStream();
ByteArrayOutputStream estimated = new ByteArrayOutputStream(1024);
~~~

Đây là đoạn minh họa yêu cầu import `java.io.ByteArrayOutputStream`. **Dung lượng ban đầu không phải kích thước nội dung**: cả hai đối tượng mới tạo đều có `size() == 0`. Khi ghi vượt dung lượng, lớp tự mở rộng mảng nội bộ.

Không nên cấp dung lượng quá lớn “cho chắc” vì nó chiếm heap từ đầu. Ngược lại, nếu biết kết quả khoảng vài kilobyte, dung lượng ban đầu hợp lý có thể giảm số lần cấp phát và sao chép nội bộ.

### 4.2. write(int b): chỉ byte thấp được ghi

`output.write(int b)` ghi **8 bit thấp nhất** của `b`. Nó không ghi toàn bộ số nguyên 32-bit theo định dạng nhị phân. Ví dụ `output.write(0x1234)` ghi byte `0x34`, tức giá trị thập phân 52, là ký tự ASCII `'4'`.

Nếu muốn ghi một `int` 32-bit theo thứ tự byte nhất định, phải tự xác định định dạng hoặc dùng lớp như `DataOutputStream` bọc `ByteArrayOutputStream`. Với dữ liệu mạng/file có cấu trúc, định dạng cần xác định **endianness**, độ rộng trường và quy tắc diễn giải.

### 4.3. write(byte[], off, len) và writeBytes(byte[])

- `write(byte[] bytes, int off, int len)` ghi đúng `len` byte bắt đầu ở vị trí `off` của mảng nguồn.
- `writeBytes(byte[] bytes)` (có từ Java 11) ghi toàn bộ byte trong mảng.
- `write(int b)` ghi một byte thấp nhất của số `int`.

Nếu một phần mảng được dùng làm buffer đọc tệp, chỉ ghi `count` byte vừa đọc. Nếu mảng đã đại diện chính xác cho một payload hoàn chỉnh, `writeBytes(payload)` giúp ngắn gọn.

### 4.4. size(), toByteArray(), reset(), writeTo()

`size()` trả số byte đã ghi và còn hữu ích trong bộ đệm. Nó **không** cho biết dung lượng mảng nội bộ đã cấp phát.

`toByteArray()` tạo một **mảng mới** chứa bản sao của đúng `size()` byte hiện tại. Nếu sau đó tiếp tục ghi hoặc `reset()`, bản sao đã trả về không đổi. Việc tạo bản sao cũng có chi phí cấp phát và sao chép, đặc biệt đáng chú ý với payload lớn.

`reset()` đặt số byte hợp lệ về 0 để có thể dùng lại `ByteArrayOutputStream`. Nó **không bắt buộc giải phóng hoặc xóa mảng nội bộ**; bộ đệm có thể được tái sử dụng để giảm cấp phát. Điều này khác với việc tạo đối tượng mới và không nên dùng `reset()` như biện pháp xóa dữ liệu nhạy cảm khỏi RAM.

`writeTo(OutputStream target)` ghi nội dung hợp lệ của bộ đệm hiện tại sang một output stream khác, giúp tránh tạo bản sao `byte[]` bằng `toByteArray()` trước khi ghi. Nó không tự đóng output đích. Trong trường hợp phải chuyển một payload có sẵn vào luồng tệp/socket, cách này thường hữu ích.

### 4.5. Ví dụ độc lập về snapshot và reset

Lưu **ByteArrayWriteDemo.java**:

~~~java
import java.io.ByteArrayOutputStream;
import java.nio.charset.StandardCharsets;

public class ByteArrayWriteDemo {
    public static void main(String[] args) throws Exception {
        try (ByteArrayOutputStream output = new ByteArrayOutputStream(2)) {
            output.write(0x41); // 'A'
            output.write(new byte[]{0x42, 0x43, 0x44}, 1, 2); // 'C', 'D'

            byte[] snapshot = output.toByteArray();
            System.out.println("Size: " + output.size());
            System.out.println("Snapshot: " +
                    new String(snapshot, StandardCharsets.US_ASCII));

            output.reset();
            output.write("Z".getBytes(StandardCharsets.US_ASCII));

            System.out.println("After reset: " +
                    output.toString(StandardCharsets.US_ASCII));
            System.out.println("Old snapshot: " +
                    new String(snapshot, StandardCharsets.US_ASCII));
        }
    }
}
~~~

~~~bash
javac -encoding UTF-8 ByteArrayWriteDemo.java
java ByteArrayWriteDemo
~~~

Kết quả chính xác:

~~~text
Size: 3
Snapshot: ACD
After reset: Z
Old snapshot: ACD
~~~

Ví dụ minh họa ba cơ chế: bộ đệm tự tăng dù khởi tạo kích thước 2, `toByteArray()` trả snapshot độc lập, và `reset()` bắt đầu một nội dung mới mà không thay đổi snapshot cũ.

## 5. Bài thực hành tổng hợp: sao chép văn bản UTF-8 qua hai luồng trong RAM

Một tình huống quen thuộc: chương trình có văn bản Java, mã hóa thành UTF-8, sau đó muốn sử dụng một hàm nhận `InputStream` và ghi sang `OutputStream`. Hai luồng mảng là cách ghép nhanh mà không phải tạo tệp tạm.

Lưu **MemoryStreamsDemo.java**:

~~~java
import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.nio.charset.StandardCharsets;
import java.util.Arrays;

public class MemoryStreamsDemo {
    public static void main(String[] args) throws Exception {
        String original = "Xin chào!";
        byte[] encoded = original.getBytes(StandardCharsets.UTF_8);

        byte[] copied;
        try (ByteArrayInputStream input = new ByteArrayInputStream(encoded);
             ByteArrayOutputStream output = new ByteArrayOutputStream()) {

            byte[] chunk = new byte[3];
            int count;
            while ((count = input.read(chunk)) != -1) {
                output.write(chunk, 0, count);
            }

            copied = output.toByteArray();
        }

        System.out.println("Bytes: " + copied.length);
        System.out.println("Same bytes: " + Arrays.equals(encoded, copied));
        System.out.println("Decoded: " +
                new String(copied, StandardCharsets.UTF_8));
    }
}
~~~

~~~bash
javac -encoding UTF-8 MemoryStreamsDemo.java
java MemoryStreamsDemo
~~~

Kết quả:

~~~text
Bytes: 10
Same bytes: true
Decoded: Xin chào!
~~~

Tại sao `10` byte? `"Xin chào!"` có 9 đơn vị `char`, nhưng ký tự `à` chiếm 2 byte trong UTF-8, nên tổng byte là 10. Vòng lặp sao chép **byte thô**; nó không cố giải mã một khối 3 byte thành String riêng lẻ. Đây là điều đúng vì chuỗi byte UTF-8 của một ký tự có thể bị chia giữa hai lần đọc. Chỉ sau khi có payload đầy đủ, ví dụ mới tạo String với `StandardCharsets.UTF_8`.

Nếu ngay từ đầu chỉ cần chuyển String thành byte[] thì `original.getBytes(UTF_8)` đã đủ; không nhất thiết phải tạo luồng. Điểm dạy học ở đây là cách các API cùng hợp đồng `InputStream` và `OutputStream` có thể dùng bộ nhớ làm nguồn/đích trong một pipeline mà mã xử lý không cần biết đó là tệp, socket hay mảng.

## 6. Những khác biệt về sao chép và chia sẻ mảng

### 6.1. ByteArrayInputStream dùng chung mảng nguồn

~~~java
byte[] source = {65, 66};
ByteArrayInputStream input = new ByteArrayInputStream(source);
source[0] = 90;
int first = input.read(); // 90, tương ứng 'Z'
~~~

Đây là đoạn minh họa; cần `import java.io.ByteArrayInputStream`. Vì constructor không sao chép mảng, cập nhật từ bên ngoài có thể nhìn thấy khi đọc. Nếu muốn stream có dữ liệu riêng:

~~~java
ByteArrayInputStream isolated =
        new ByteArrayInputStream(source.clone());
~~~

Với dữ liệu không thay đổi và được quản lý bởi một thành phần, việc dùng chung mảng tránh sao chép không cần thiết. Với mã có nhiều thành phần hoặc cần bảo đảm dữ liệu đầu vào không thể bị sửa ngoài ý muốn, clone đầu vào là một lựa chọn rõ ràng.

### 6.2. ByteArrayOutputStream tạo bản sao đầu ra

`output.toByteArray()` trả một mảng mới. Sửa mảng nhận được **không** sửa nội dung đang nằm trong `ByteArrayOutputStream`:

~~~java
ByteArrayOutputStream output = new ByteArrayOutputStream();
output.writeBytes(new byte[]{1, 2, 3});
byte[] copy = output.toByteArray();
copy[0] = 99;
// output vẫn giữ 1, 2, 3.
~~~

Đây là đoạn minh họa; cần import `java.io.ByteArrayOutputStream`. Mảng bản sao cũng không “theo dõi” các lần ghi sau này. Nếu muốn chia sẻ kết quả sang nơi khác, hãy xác định rõ nơi nhận được phép sửa mảng hay cần clone thêm.

### 6.3. Sao chép kép và sử dụng bộ nhớ

Mẫu:

~~~java
byte[] data = output.toByteArray();
InputStream input = new ByteArrayInputStream(data);
~~~

có nghĩa `toByteArray()` đã cấp phát bản sao; `ByteArrayInputStream` chỉ giữ tham chiếu tới bản sao đó. Tại thời điểm này có thể cùng tồn tại **bộ đệm nội bộ của ByteArrayOutputStream và mảng data**. Với dữ liệu lớn, chi phí bộ nhớ có thể đáng kể.

Nếu đích là một `OutputStream` khác, `output.writeTo(destination)` có thể tránh mảng trung gian. Nếu hàm nhận bắt buộc là `InputStream`, có thể chấp nhận snapshot đó với dữ liệu nhỏ/vừa, hoặc thay thiết kế để xử lý theo luồng từ nguồn gốc nhằm tránh giữ cả payload trong RAM.

## 7. Read/write theo từng khối: chú ý count và phần đuôi mảng

Dù `ByteArrayInputStream` đọc từ RAM và thường có thể lấp đầy buffer cho đến khi gần EOF, **mã tổng quát phải dựa trên số byte thực sự đọc**.

Ví dụ nguồn 5 byte, buffer 2 byte:

~~~text
Nguồn:                 A B C D E
Lượt đọc 1: count=2 → A B
Lượt đọc 2: count=2 → C D
Lượt đọc 3: count=1 → E   (phần còn lại của mảng vẫn có thể là D)
Lượt đọc 4: count=-1 → EOF
~~~

Nếu viết `output.write(buffer)` ở lượt 3, ta có thể chèn thêm byte cũ không thuộc dữ liệu mới. Với `ByteArrayOutputStream`, lỗi sẽ hiện rất rõ: `size()` tăng thêm byte và `toByteArray()` chứa dữ liệu dư. Dùng `output.write(buffer, 0, count)`.

Một demo độc lập, lưu **ByteChunkDemo.java**:

~~~java
import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.nio.charset.StandardCharsets;

public class ByteChunkDemo {
    public static void main(String[] args) throws Exception {
        byte[] data = "ABCDE".getBytes(StandardCharsets.US_ASCII);

        try (ByteArrayInputStream input = new ByteArrayInputStream(data);
             ByteArrayOutputStream output = new ByteArrayOutputStream()) {
            byte[] buffer = new byte[2];
            int count;
            while ((count = input.read(buffer)) != -1) {
                System.out.println("Read: " + count);
                output.write(buffer, 0, count);
            }
            System.out.println("Copied: " +
                    output.toString(StandardCharsets.US_ASCII));
        }
    }
}
~~~

~~~bash
javac -encoding UTF-8 ByteChunkDemo.java
java ByteChunkDemo
~~~

Kết quả:

~~~text
Read: 2
Read: 2
Read: 1
Copied: ABCDE
~~~

Nhờ nguồn trong RAM, kích thước và số lần đọc ở ví dụ này có thể dự đoán; với nguồn tổng quát như network stream, lượt đọc có thể ngắn hơn buffer vì lý do khác ngoài EOF.

## 8. Chuyển đổi giữa byte[] và String đúng charset

`ByteArrayInputStream` và `ByteArrayOutputStream` **không tự hiểu dữ liệu byte là văn bản**. Nếu byte biểu diễn chuỗi, việc mã hóa và giải mã phải dùng charset khớp với định dạng.

Với Java 17:

~~~java
String text = "Hà Nội";
byte[] utf8 = text.getBytes(StandardCharsets.UTF_8);

ByteArrayInputStream input = new ByteArrayInputStream(utf8);

ByteArrayOutputStream output = new ByteArrayOutputStream();
output.writeBytes(utf8);
String decoded = output.toString(StandardCharsets.UTF_8);
~~~

Đây là đoạn minh họa cần import `java.nio.charset.StandardCharsets` và hai lớp stream. `decoded` bằng `"Hà Nội"`. Lớp `ByteArrayOutputStream` còn có `toString()` không truyền charset, nhưng phương thức đó dùng charset mặc định theo hợp đồng, có thể không phải charset của dữ liệu khi chạy trên môi trường khác; nên ưu tiên `toString(StandardCharsets.UTF_8)` hoặc `new String(output.toByteArray(), UTF_8)` khi cần tính nhất quán.

**Không giải mã từng mảnh UTF-8 độc lập** nếu một ký tự có thể bị chia giữa các mảng; ví dụ dấu tiếng Việt và emoji cần nhiều byte. Hãy gom đủ payload rồi giải mã, hoặc dùng một `InputStreamReader`/`CharsetDecoder` có trạng thái xuyên suốt các khối.

Một số byte như ảnh JPEG, ZIP, khóa nhị phân hoặc thông điệp định dạng riêng **không phải văn bản UTF-8**. Tạo String từ chúng có thể thay đổi dữ liệu vì chuỗi byte không hợp lệ bị thay thế. Giữ chúng dưới dạng `byte[]`, dùng `InputStream`/`OutputStream` và tránh ép qua String.

## 9. Cách tương tác với các API InputStream và OutputStream khác

Giá trị của hai lớp không chỉ nằm ở những phương thức riêng; chúng triển khai các hợp đồng phổ biến của Java I/O.

### 9.1. Dùng một hàm xử lý bất kỳ InputStream nào

Ví dụ một hàm tổng quát:

~~~java
static long copy(InputStream input, OutputStream output)
        throws IOException {
    byte[] buffer = new byte[8192];
    long total = 0;
    int count;
    while ((count = input.read(buffer)) != -1) {
        output.write(buffer, 0, count);
        total += count;
    }
    return total;
}
~~~

Đây là **đoạn mã phương thức**, không phải một chương trình độc lập. Cần import `java.io.InputStream`, `OutputStream` và `IOException` và đặt trong lớp. Hàm **không tự đóng** hai tài nguyên vì chúng được người gọi truyền vào; quyền sở hữu thuộc giao ước bên ngoài.

Trong kiểm thử, có thể dùng `new ByteArrayInputStream(fixture)` làm đầu vào và `new ByteArrayOutputStream()` làm đầu ra để kiểm tra chính xác byte mà không phải tạo tệp. Khi chạy thật, cùng hàm có thể nhận `Files.newInputStream(path)` và `Files.newOutputStream(path)`.

### 9.2. transferTo thay vòng lặp thủ công

Từ Java 9, `InputStream.transferTo(OutputStream)` đọc hết đầu vào còn lại và ghi sang đầu ra, trả về số byte đã chuyển. Với Java 17:

~~~java
long copied = input.transferTo(output);
~~~

Đây là đoạn minh họa với hai stream đã được cung cấp. Phương thức **không tự đóng** các stream. Nếu quyền đóng do người gọi quản lý, cần giữ `try-with-resources` hoặc quy tắc vòng đời tương đương tại nơi sở hữu.

Việc dùng `transferTo` có thể gọn hơn một vòng lặp nếu chỉ cần chuyển toàn bộ byte. Nó không thay thế kiểm tra giới hạn kích thước, xử lý lỗi hay quyết định có cần gom mọi byte vào RAM hay không.

### 9.3. DataOutputStream và DataInputStream

`ByteArrayOutputStream` có thể làm đích của `DataOutputStream` khi cần ghi số theo định dạng nhị phân xác định, còn `ByteArrayInputStream` có thể làm nguồn của `DataInputStream` khi đọc lại. Ví dụ Java 17 độc lập, **BinaryPayloadDemo.java**:

~~~java
import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.DataInputStream;
import java.io.DataOutputStream;

public class BinaryPayloadDemo {
    public static void main(String[] args) throws Exception {
        byte[] payload;

        try (ByteArrayOutputStream raw = new ByteArrayOutputStream();
             DataOutputStream out = new DataOutputStream(raw)) {
            out.writeInt(258);
            out.writeBoolean(true);
            out.flush();
            payload = raw.toByteArray();
        }

        try (DataInputStream in =
                     new DataInputStream(new ByteArrayInputStream(payload))) {
            System.out.println("Length: " + payload.length);
            System.out.println("Number: " + in.readInt());
            System.out.println("Flag: " + in.readBoolean());
        }
    }
}
~~~

~~~bash
javac -encoding UTF-8 BinaryPayloadDemo.java
java BinaryPayloadDemo
~~~

Kết quả:

~~~text
Length: 5
Number: 258
Flag: true
~~~

`DataOutputStream.writeInt` ghi bốn byte theo thứ tự **byte cao trước (big-endian)**, còn `writeBoolean(true)` ghi một byte 1. `DataInputStream` đọc đúng định dạng đó. Đây khác với `ByteArrayOutputStream.write(258)`, vốn chỉ ghi **một byte** có giá trị 2.

Dùng cặp DataInput/DataOutput chỉ khi hai đầu thống nhất định dạng Java này hoặc có hợp đồng tương thích; không tự suy ra đó là định dạng của mọi dịch vụ mạng.

## 10. Vòng đời tài nguyên và tác động của close()

Cả `ByteArrayInputStream` và `ByteArrayOutputStream` đều triển khai các giao diện I/O tương ứng và có thể được đóng bằng `try-with-resources`. Với **chính hai lớp này**, `close()` **không có tác động** đến khả năng sử dụng: sau khi gọi close, `ByteArrayInputStream` vẫn có thể đọc, còn `ByteArrayOutputStream` vẫn có thể ghi và gọi `toByteArray()`.

Điều này phù hợp vì chúng không giữ file descriptor/socket cần giải phóng. Tuy nhiên, **không suy rộng** cho `FileInputStream`, `FileOutputStream`, `BufferedInputStream`, socket stream hoặc các wrapper I/O khác: với nhiều loại stream, đóng là bắt buộc và dùng lại sau khi đóng sẽ lỗi.

Vẫn có ích khi dùng `try-with-resources` cho các ví dụ tổng quát vì:

- Cách viết nhất quán khi sau này thay mảng bằng nguồn tệp hoặc socket.
- Phạm vi sống của đối tượng được thể hiện rõ.
- Các wrapper có thể giữ tài nguyên khác, dù nguồn gốc ban đầu là bộ nhớ.

**Chú ý khi bọc:** ví dụ `DataOutputStream` bọc `ByteArrayOutputStream`. Đóng `DataOutputStream` cũng đóng stream bên dưới; tuy ByteArrayOutputStream vẫn truy cập được sau khi đóng, không nên áp dụng hành vi đó cho các OutputStream tổng quát khác.

### 10.1. Buffering có thật sự cần cho mảng byte?

`BufferedInputStream` và `BufferedOutputStream` thường giúp giảm số lần thao tác I/O tốn chi phí với tệp/socket. Với byte array stream, dữ liệu đã nằm trong RAM nên việc thêm wrapper buffering thường không mang lợi ích đáng kể cho việc giảm gọi hệ điều hành, thậm chí có thể thêm sao chép/bộ đệm không cần thiết.

Nếu API đang yêu cầu wrapper vì định dạng hoặc cơ chế tiện ích, vẫn có thể dùng; nhưng không nên mặc định rằng bọc thêm `BufferedOutputStream` luôn làm nhanh hơn `ByteArrayOutputStream`.

## 11. Sự khác biệt giữa reset() của InputStream và OutputStream

Cả hai lớp đều có `reset()` nhưng ý nghĩa **khác nhau**:

- `ByteArrayInputStream.reset()`: đưa **vị trí đọc** về `mark`, cho phép đọc lại những byte của nguồn. Nó không xóa hay thay dữ liệu nguồn.
- `ByteArrayOutputStream.reset()`: đặt **số byte đã ghi hợp lệ** về 0 để bắt đầu kết quả mới. Nó không làm thay đổi những bản sao đã trả qua `toByteArray()`.

Dễ nhầm nếu cùng một biến tên `stream`. Nên đặt tên mang ý nghĩa `input`/`output` và diễn giải chính xác hành động “đọc lại” với “xóa nội dung logic để ghi lại”.

Đối với `ByteArrayOutputStream`, `reset()` không bảo đảm xóa các byte cũ khỏi vùng nhớ nội bộ; nếu xử lý dữ liệu nhạy cảm, không coi reset là thao tác bảo mật xóa bộ nhớ. Đối với `ByteArrayInputStream`, `reset()` không tự đưa về đầu tuyệt đối nếu đã gọi `mark()` ở vị trí khác.

## 12. Khi nào dùng byte[] trực tiếp và khi nào cần stream?

Không phải thao tác nào với RAM cũng cần hai lớp này:

| Mục đích | Lựa chọn thường hợp lý |
| --- | --- |
| Đã có byte[] và muốn gọi API nhận InputStream | `new ByteArrayInputStream(data)` |
| Muốn ghi dần nhiều khối byte mà chưa biết kích thước cuối | `ByteArrayOutputStream` |
| Chỉ muốn lấy byte của một String | `text.getBytes(UTF_8)` |
| Chỉ muốn đổi byte[] hoàn chỉnh thành String | `new String(bytes, UTF_8)` |
| Muốn ghép vài mảng cố định nhỏ | Có thể tính tổng chiều dài và dùng `System.arraycopy` hoặc `ByteBuffer` |
| Cần giữ payload nhỏ để kiểm thử hàm streaming | Cặp `ByteArrayInputStream` / `ByteArrayOutputStream` |
| Cần truyền dữ liệu liên tục từ tệp lớn sang đích khác | `InputStream`/`OutputStream` theo khối, tránh giữ toàn bộ trong RAM |
| Cần tuần tự hóa object Java theo định dạng riêng | Xem API tuần tự hóa thích hợp; không tự suy ra BAOS đã định dạng object |

`ByteArrayOutputStream` rất thuận tiện khi kích thước đầu ra khó đoán nhưng vẫn **có giới hạn thực tế trong RAM**. Với tệp hàng gigabyte, việc gom mọi byte vào BAOS thường không phải giải pháp tốt: bộ đệm mở rộng chiếm heap, còn `toByteArray()` có thể cần thêm một mảng lớn thứ hai.

Khi ứng dụng đã có nguồn/đích streaming, hãy cân nhắc xử lý dần thay vì lắp ghép toàn bộ nội dung rồi mới ghi.

## 13. Quản lý bộ nhớ, dung lượng và các rủi ro

### 13.1. Bộ đệm tăng có thể gây OutOfMemoryError

`ByteArrayOutputStream` dùng một mảng nội bộ để chứa dữ liệu và có thể phải cấp phát mảng lớn hơn khi hết chỗ. Khi dữ liệu không giới hạn hoặc bị điều khiển bởi đầu vào bên ngoài, bộ đệm có thể làm cạn heap hoặc chạm giới hạn kích thước mảng của JVM.

Một số biện pháp:

1. Xác định **kích thước payload tối đa** theo nghiệp vụ trước khi bắt đầu gom.
2. Nếu có header khai báo độ dài, kiểm tra giá trị đó nhưng vẫn theo dõi lượng byte thực tế; không tin mù quáng vào kích thước do bên ngoài cung cấp.
3. Nếu nội dung lớn, xử lý theo luồng đến nơi tiêu thụ hoặc dùng file tạm khi thiết kế cho phép.
4. Không gọi `toByteArray()` liên tục bên trong vòng lặp ghi vì mỗi lần đều có thể tạo một bản sao lớn.
5. Không tạo `new ByteArrayOutputStream(Integer.MAX_VALUE)` trừ khi thực sự có môi trường và mục đích hợp lý; cấp phát dung lượng ban đầu lớn có thể thất bại ngay.

Một thiết kế dễ kiểm soát có thể theo dõi tổng byte với `long total` trước mỗi lần ghi và từ chối khi vượt ngưỡng. Nhưng bản thân `ByteArrayOutputStream` vẫn dùng mảng Java có giới hạn chỉ số kiểu `int`, nên ứng dụng không thể chứa lượng byte tùy ý chỉ bằng một instance.

### 13.2. Không nhầm size() với capacity

`size()` báo **số byte đã ghi**. Trong nội bộ, BAOS có thể giữ vùng chứa lớn hơn số đó để chừa chỗ ghi tiếp. Không nên suy đoán mức heap chiếm dụng chỉ từ `size()`, và cũng không cần truy cập trường nội bộ để đọc một “capacity” không nằm trong API công khai.

Sau `reset()`, `size()` trở về 0 nhưng buffer có thể vẫn chiếm dung lượng cũ. Nếu kết thúc công việc với mảng lớn, hãy bỏ tham chiếu để đối tượng có thể được GC thu gom khi thích hợp; reset đơn thuần không phải yêu cầu trả bộ nhớ lập tức cho JVM.

### 13.3. Chia sẻ và an toàn khi sửa dữ liệu

Vì `ByteArrayInputStream` dùng chung mảng nguồn, không nên đồng thời sửa mảng từ một thread khác trong lúc đọc mà không có cơ chế đồng bộ phù hợp. Với `ByteArrayOutputStream`, dù một số phương thức được đồng bộ trong triển khai, thiết kế giao thức nhiều bước giữa các thread vẫn cần đảm bảo quyền sở hữu/đồng bộ rõ ràng. Đừng dựa vào việc “dữ liệu ở RAM” để suy ra mọi kiểu truy cập đồng thời đều an toàn.

## 14. Những lỗi phổ biến và cách khắc phục

| Lỗi | Vì sao sai | Cách đúng |
| --- | --- | --- |
| Kiểm tra `byteValue == -1` như dấu hiệu EOF | Byte dữ liệu `0xFF` có giá trị signed -1 | Đọc qua `int value = input.read()` và kiểm tra `value == -1` |
| `output.write(buffer)` sau mỗi lượt đọc | Lượt cuối có thể chưa đầy buffer, ghi thêm byte cũ | `output.write(buffer, 0, count)` |
| `new String(bytes)` không charset | Kết quả có thể khác trên môi trường khác | Chọn `StandardCharsets.UTF_8` hoặc charset theo định dạng |
| Tạo String từ dữ liệu nhị phân bất kỳ | Giải mã làm biến đổi/mất byte | Giữ dữ liệu nhị phân ở dạng byte[] |
| Tưởng BAIS đã sao chép dữ liệu nguồn | Bên ngoài sửa mảng khiến nội dung đọc thay đổi | Dùng `source.clone()` nếu cần bản sao độc lập |
| Tưởng `toByteArray()` trả mảng nội bộ | Sửa kết quả không làm đổi BAOS và có thêm chi phí bộ nhớ | Xem đó là bản sao, dùng `writeTo` khi có thể |
| Gọi `reset()` để xóa dữ liệu nhạy cảm | BAOS chỉ đặt lại `count`, không bảo đảm xóa bộ nhớ | Thiết kế chính sách lưu giữ/xóa phù hợp |
| Dùng `available()` để tính kích thước mọi InputStream | Với nguồn sống, 0 không phải EOF | Chỉ áp dụng giá trị xác định với BAIS; tổng quát thì đọc đến -1 |
| Nghĩ `write(0x1234)` ghi 4 byte của int | Nó chỉ ghi 8 bit thấp nhất | Dùng `DataOutputStream.writeInt` theo định dạng cần thiết |
| Tích lũy tệp rất lớn trong BAOS | Bộ đệm và snapshot dễ làm cạn heap | Sao chép theo luồng, giới hạn payload |
| Giả định đóng stream mảng giống đóng file | `close()` của hai lớp là no-op | Hiểu hợp đồng lớp cụ thể; luôn đóng tài nguyên thật |
| Dùng `ByteArrayInputStream.reset()` để xóa nội dung | Nó chỉ quay vị trí đọc về mốc | Tạo dữ liệu khác hoặc quản lý mảng nguồn riêng |
| Đọc UTF-8 theo chunk rồi tạo `String` độc lập mỗi lượt | Có thể cắt giữa byte của ký tự nhiều byte | Giữ byte và decode một lần hoặc dùng decoder có trạng thái |

## 15. Thực hành mở rộng và câu hỏi tự kiểm tra

**Câu 1.** Một `ByteArrayInputStream` đọc mảng `{(byte)0xFF}`; lời gọi `read()` đầu tiên và thứ hai trả gì?

**Đáp án:** `255` rồi `-1`. API `read()` trả int unsigned cho byte hợp lệ, và chỉ dùng -1 cho EOF.

**Câu 2.** `ByteArrayInputStream` có sao chép mảng truyền vào constructor không?

**Đáp án:** không. Nó lưu tham chiếu; cần `clone()` hoặc `Arrays.copyOf` nếu muốn tách dữ liệu.

**Câu 3.** Sau khi gọi `byte[] snapshot = output.toByteArray()` rồi `output.reset()` và ghi byte mới, `snapshot` có đổi không?

**Đáp án:** không. Snapshot là bản sao của dữ liệu tại thời điểm gọi.

**Câu 4.** Hai lớp này có nên dùng `try-with-resources` không, dù close không có hiệu lực?

**Đáp án:** có thể, đặc biệt để giữ cấu trúc sở hữu rõ ràng và nhất quán với API stream. Nhưng đừng coi việc đóng BAIS/BAOS có tác dụng giải phóng file/socket như lớp tương ứng của tệp.

**Câu 5.** Muốn gửi nội dung BAOS sang một `OutputStream` đã tồn tại mà không tạo mảng trung gian qua `toByteArray()`, dùng gì?

**Đáp án:** `output.writeTo(destination)`. Đích vẫn do người sở hữu đóng; phương thức không tự đóng đích.

**Câu 6.** `ByteArrayOutputStream.write(0x1234)` làm size tăng bao nhiêu, và byte được ghi là gì?

**Đáp án:** tăng 1; byte `0x34`. Muốn ghi int 32-bit, chọn định dạng rõ ràng và API thích hợp như `DataOutputStream.writeInt`.

**Câu 7.** Trong vòng lặp đọc có buffer dài 8, lần cuối `read` trả 3. Ghi mấy byte?

**Đáp án:** đúng 3 byte với `write(buffer, 0, 3)`.

**Câu 8.** Dùng `new String(baos.toByteArray(), UTF_8)` có phù hợp với nội dung là ảnh PNG không?

**Đáp án:** không. Đây là dữ liệu nhị phân; chuyển thành String có thể làm hỏng byte nếu sau đó mã hóa lại. Giữ dưới dạng byte[].

### Bài tập thực hành

1. Đổi `ByteChunkDemo` thành bộ đệm dài 3 và nguồn `"ABCDEFGH"`; dự đoán các giá trị `count` và xác nhận số byte trong output.
2. Tạo một `ByteArrayInputStream` từ vùng `offset=2, length=3` của mảng sáu byte. Đọc đến EOF, gọi `reset()` và kiểm tra nội dung có thể đọc lại từ offset ban đầu.
3. Mở rộng `ByteArrayWriteDemo` bằng `writeTo` tới một BAOS thứ hai. So sánh kết quả với `toByteArray()` và thay đổi snapshot để quan sát tính độc lập.
4. Tạo chuỗi có tiếng Việt và emoji, mã hóa UTF-8, sao chép theo buffer 1 byte, rồi **chỉ giải mã khi toàn bộ payload đã được ghép lại**. Xác nhận `String.equals`, `Arrays.equals` và phân biệt số byte với độ dài UTF-16.
5. Thêm kiểm tra giới hạn dung lượng trước khi ghi vào BAOS; thử với dữ liệu vượt giới hạn để bảo đảm ứng dụng từ chối có kiểm soát.

## 16. Những điểm cần nhớ

- **`ByteArrayInputStream` đọc từ mảng byte có sẵn**; đọc tuần tự, hỗ trợ `mark/reset`, `skip` và `available`. Mảng nguồn được **dùng chung**, không mặc định copy.
- **`ByteArrayOutputStream` tích lũy dữ liệu byte trong mảng tự tăng**, cung cấp `size`, `reset`, `writeTo` và `toByteArray`. `toByteArray` trả **bản sao**.
- Luôn phân biệt **giá trị byte có dấu** với **kết quả `int` của `InputStream.read()`**, trong đó `-1` là EOF.
- Khi sao chép từng khối, **ghi đúng `count` byte mới đọc**. Khi xử lý văn bản, dùng charset rõ ràng và không giải mã từng mảnh UTF-8 tách rời.
- Hai lớp là **I/O trên heap**, không giữ descriptor/socket; `close()` không cấm sử dụng tiếp với chính hai lớp này, nhưng không thể suy ra điều đó cho mọi stream.
- Dữ liệu trong RAM vẫn có chi phí. **Giới hạn kích thước đầu ra**, tránh sao chép không cần thiết và chọn streaming khi payload lớn.

### Tài liệu tham khảo

- [ByteArrayInputStream — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/ByteArrayInputStream.html)
- [ByteArrayOutputStream — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/ByteArrayOutputStream.html)
- [InputStream — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/InputStream.html)
- [OutputStream — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/OutputStream.html)
- [DataOutputStream — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/DataOutputStream.html)
