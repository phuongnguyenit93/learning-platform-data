# `InputStream.available()` không phải kích thước toàn bộ dữ liệu

## Mục tiêu bài học

Khi làm việc với **luồng byte** trong Java, cần phân biệt lượng dữ liệu *có thể đọc ngay lúc này* với tổng dung lượng của nguồn dữ liệu. Sau bài này, bạn có thể:

- Giải thích đúng ý nghĩa của `InputStream.available()` và lý do kết quả của nó không phải độ dài toàn bộ stream.
- Nhận ra vì sao `available() == 0` **không đồng nghĩa** đã hết dữ liệu (EOF), còn `available() > 0` **không cho biết** toàn bộ dữ liệu dài bao nhiêu.
- Đọc dữ liệu bằng `read()`, `read(byte[])` hoặc những API đọc đến EOF phù hợp; chọn cách xác định kích thước tệp khi thực sự có tệp.
- Tránh cấp phát bộ đệm, điều kiện lặp và logic giao thức dựa vào `available()`.

## 1. `available()` thực sự trả về điều gì?

`java.io.InputStream` khai báo:

```java
public int available() throws IOException
```

Giá trị trả về là **ước lượng số byte có thể đọc hoặc bỏ qua từ stream mà không bị chặn (blocking)** ở thời điểm gọi. Nó có thể bằng `0`, kể cả khi stream vẫn còn dữ liệu và lần gọi `read()` tiếp theo có thể lấy được byte sau khi chờ, hoặc ngay lập tức.

Cần giữ ba khái niệm riêng biệt:

| Khái niệm | Cách hiểu đúng |
| --- | --- |
| `available()` | Ước lượng byte có thể lấy **không phải chờ** ở thời điểm hiện tại; phụ thuộc loại stream. |
| Tổng kích thước nguồn | Số byte toàn bộ tệp, thông điệp hoặc dữ liệu sẽ được cung cấp; nhiều stream không có tổng này từ trước. |
| EOF | Trạng thái hết dữ liệu, được thể hiện khi `read()` trả `-1` (hoặc API tương ứng cho biết đã hết luồng). |

Đặc biệt, triển khai mặc định của `InputStream.available()` trả về **`0`**. Các lớp con có thể ghi đè phương thức này khi chúng biết thêm về dữ liệu đang sẵn có. Vì vậy, không thể suy ra dung lượng toàn bộ stream từ một con số `available()` duy nhất.

## 2. Tại sao kết quả khác nhau giữa các luồng?

- **`ByteArrayInputStream`:** dữ liệu đã có đầy đủ trong mảng byte; `available()` trả về số byte chưa đọc **còn lại trong mảng**. Với riêng lớp này, con số ấy phản ánh phần còn lại của nguồn hiện có.
- **`FileInputStream`:** với tệp thông thường, giá trị thường gần với số byte còn có thể đọc từ vị trí hiện tại, nhưng API vẫn mô tả nó theo hợp đồng `available()`. Đừng biến đặc điểm của `FileInputStream` thành quy tắc chung cho mọi `InputStream`.
- **Luồng từ socket, pipe hoặc nguồn nhận dữ liệu dần:** có thể chưa có byte nào trong bộ đệm *ngay bây giờ*, dù phía gửi sẽ gửi thêm sau đó. `available() == 0` không chứng minh kết nối đã kết thúc hoặc thông điệp đã hoàn chỉnh.
- **Lớp con chỉ triển khai `read()`:** nếu không ghi đè `available()`, giá trị luôn là `0` theo triển khai mặc định, dù dữ liệu vẫn đọc được.

Lưu ý: con số có thể thay đổi sau một lần đọc hoặc khi dữ liệu mới đến. Nó cũng không thay thế một định dạng giao thức quy định trước độ dài thông điệp.

## 3. Thí nghiệm Java 17+: có dữ liệu nhưng `available() == 0`

Lưu đoạn sau vào tệp **`AvailableDemo.java`**:

```java
import java.io.ByteArrayInputStream;
import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;

public class AvailableDemo {
    public static void main(String[] args) throws IOException {
        byte[] data = "ABCDE".getBytes(StandardCharsets.US_ASCII);

        try (InputStream arrayStream = new ByteArrayInputStream(data)) {
            System.out.println("array before = " + arrayStream.available());
            System.out.println("array first  = " + (char) arrayStream.read());
            System.out.println("array after  = " + arrayStream.available());
        }

        try (InputStream customStream = new InputStream() {
            private int index;

            @Override
            public int read() {
                return index < data.length ? (data[index++] & 0xff) : -1;
            }
        }) {
            System.out.println("custom before = " + customStream.available());
            System.out.println("custom first  = " + (char) customStream.read());
            System.out.println("custom after  = " + customStream.available());
        }
    }
}
```

Biên dịch và chạy:

```bash
javac AvailableDemo.java
java AvailableDemo
```

Kết quả chuẩn:

```text
array before = 5
array first  = A
array after  = 4
custom before = 0
custom first  = A
custom after  = 0
```

**Giải thích:**

1. `ByteArrayInputStream` biết mảng chứa năm byte; sau khi đọc `A`, còn bốn byte chưa đọc nên `available()` từ `5` thành `4`.
2. `customStream` chỉ ghi đè `read()` và kế thừa `available()` mặc định. Do đó `available()` luôn là `0`, ngay cả trước khi `read()` trả byte `A` thành công.
3. Cả hai luồng đều được khởi tạo từ dữ liệu `ABCDE`, nhưng phép đo `available()` khác nhau. Điều đó chứng minh phương thức này **không đại diện cho tổng kích thước dữ liệu**.

Ví dụ cố tình dùng một `InputStream` tùy chỉnh nhỏ để quan sát rõ hợp đồng API; đây không phải cách cần tạo mọi luồng trong ứng dụng thực tế.

## 4. Hai cách dùng sai dễ làm mất dữ liệu

### Sai lầm A: cấp phát theo `available()` rồi đọc một lần

```java
// SAI: không bảo đảm giữ được mọi byte của luồng.
byte[] all = new byte[in.available()];
int count = in.read(all);
```

Đoạn này có ít nhất hai lỗi độc lập:

1. `available()` có thể là `0` hoặc nhỏ hơn dữ liệu sẽ đến, nên mảng `all` có thể thiếu chỗ hoặc rỗng dù stream chưa kết thúc.
2. Ngay cả khi mảng đủ lớn, **một lần `read(byte[])` không được bảo đảm điền đầy mảng**; giá trị trả về là số byte thực sự đọc được hoặc `-1` khi EOF. Không được mặc định `count == all.length`.

### Sai lầm B: dùng `available() > 0` để quyết định còn dữ liệu

```java
// SAI: có thể dừng sớm khi chưa nhận hết dữ liệu.
while (in.available() > 0) {
    int oneByte = in.read();
    // Xử lý byte...
}
```

Với một luồng mạng, dữ liệu có thể đến theo từng đợt. Khi bộ đệm tạm thời rỗng, `available()` có thể về `0`; vòng lặp kết thúc dù đầu bên kia vẫn đang truyền. Với lớp `InputStream` không ghi đè `available()`, vòng lặp thậm chí không chạy lần nào.

**Quy tắc:** không dùng `available()` làm điều kiện kết thúc dữ liệu, không dùng nó làm độ dài thông điệp và không dùng nó làm căn cứ cấp phát một bộ đệm chứa toàn bộ stream.

## 5. Cách đúng: đọc cho tới EOF

Đối với một luồng thông thường mà bạn muốn đọc hết, đọc trong vòng lặp và kiểm tra giá trị trả về của `read(byte[])`:

```java
import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;

public class ReadUntilEofDemo {
    public static void main(String[] args) throws IOException {
        byte[] source = "Xin chao IO!".getBytes(StandardCharsets.UTF_8);

        try (InputStream in = new ByteArrayInputStream(source);
             ByteArrayOutputStream out = new ByteArrayOutputStream()) {
            byte[] buffer = new byte[4];
            int count;

            while ((count = in.read(buffer)) != -1) {
                out.write(buffer, 0, count);
            }

            byte[] result = out.toByteArray();
            System.out.println(new String(result, StandardCharsets.UTF_8));
            System.out.println("bytes = " + result.length);
        }
    }
}
```

Lưu thành **`ReadUntilEofDemo.java`**, rồi chạy:

```bash
javac ReadUntilEofDemo.java
java ReadUntilEofDemo
```

Kết quả:

```text
Xin chao IO!
bytes = 12
```

Lý do cách này đúng:

- Bộ đệm `buffer` có kích thước cố định `4` byte, độc lập với `available()`. Đây là dung lượng *mỗi lượt đọc*, không phải kích thước toàn bộ nguồn.
- `read(buffer)` trả về số byte thực tế của lượt đọc. `out.write(buffer, 0, count)` chỉ ghi đúng `count` byte, tránh ghi phần cũ còn sót lại trong mảng.
- Khi API báo `-1`, vòng lặp mới xem là kết thúc stream. Nếu nguồn có thể chặn, `read` có thể cần chờ dữ liệu tiếp theo; đó là hành vi đọc được xác định bởi stream.

`ByteArrayOutputStream` ở ví dụ này giữ tất cả byte trong RAM để minh họa. Với dữ liệu lớn, nên xử lý từng khối hoặc ghi trực tiếp vào `OutputStream` đích thay vì tích lũy toàn bộ vào bộ nhớ.

## 6. Chọn API theo mục tiêu thực tế

| Bạn muốn làm gì? | Cách phù hợp | Lưu ý |
| --- | --- | --- |
| Đọc hết stream chưa biết độ dài | `read(byte[])` trong vòng lặp đến `-1` | Phù hợp khi cần xử lý/ghi từng khối; không cần gọi `available()`. |
| Lấy tất cả byte của luồng **nhỏ, hữu hạn** | `in.readAllBytes()` (Java 9+) | Đọc đến EOF; tiêu tốn bộ nhớ theo lượng dữ liệu và có thể chờ lâu nếu nguồn chưa đóng. |
| Chuyển dữ liệu sang một đầu ra | `in.transferTo(out)` (Java 9+) | Trả về số byte đã chuyển dưới dạng `long`; không cần đo trước độ dài luồng. |
| Cần đọc tối đa `n` byte từ stream | `in.readNBytes(n)` hoặc vòng lặp có giới hạn | Số byte thực nhận có thể ít hơn `n` nếu gặp EOF. |
| Giao thức yêu cầu **đủ chính xác N byte** | Đọc lặp tới khi đủ N; có thể dùng `DataInputStream.readFully(byte[])` | `readFully` ném `EOFException` nếu hết luồng trước khi đọc đủ. |
| Cần kích thước của **tệp trên filesystem** | `Files.size(path)` | Trả về `long` cho tệp tại thời điểm truy vấn; không dùng cho socket hay mọi `InputStream`. |

Ví dụ lấy kích thước một tệp:

```java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;

public class FileSizeDemo {
    public static void main(String[] args) throws IOException {
        Path path = Path.of("data.bin");
        long size = Files.size(path);
        System.out.println("File size (bytes): " + size);
    }
}
```

Đây là chương trình Java hợp lệ; khi chạy cần có tệp `data.bin` ở thư mục làm việc. Giá trị in ra **phụ thuộc tệp thực tế**, nên không có stdout cố định. `Files.size(path)` cho biết kích thước của tệp được chỉ định, không phải số byte hiện có trong bộ đệm một `InputStream` đang mở. Nếu tệp thay đổi trong lúc đọc, kích thước đo trước cũng không thay thế việc kiểm tra kết quả từng lần `read`.

## 7. EOF, blocking và ranh giới thông điệp

Hãy hình dung luồng mạng nhận chuỗi byte theo hai đợt:

```text
Thời điểm t1: [A B] đã đến; phần C D E chưa đến
Thời điểm t2: [C D E] đến sau
Kết thúc:    phía gửi đóng luồng hoặc giao thức xác nhận hết thông điệp
```

Tại một thời điểm giữa hai đợt, `available()` có thể là `0` dù sau đó `read()` vẫn trả byte `C`. Tương tự, có lúc `available()` dương nhưng số đó không chứng minh rằng đã nhận đủ thông điệp.

Phân biệt hai câu hỏi khác nhau:

- **“Luồng đã tới EOF chưa?”** Dựa vào `read() == -1` khi đọc tới cuối stream, không dựa vào `available() == 0`.
- **“Thông điệp đã nhận đủ chưa?”** Phụ thuộc giao thức: ví dụ độ dài được truyền trước, ký tự phân tách, khung dữ liệu, hoặc kết thúc stream. Một kết nối mạng có thể mang nhiều thông điệp trước khi EOF; đừng chờ EOF cho từng thông điệp nếu giao thức dùng cơ chế đóng khung khác.

Trong thực tế, khi `read()` có thể chờ vô thời hạn, hãy dùng giới hạn kích thước, timeout hoặc cơ chế đóng khung tương ứng với loại nguồn. `available()` không thay thế những biện pháp đó.

## 8. Những điểm dễ nhầm khi xử lý byte

1. **Số byte khác số ký tự.** Với UTF-8, một ký tự có thể chiếm nhiều byte; `available()` dù đúng số byte đang có cũng không cho biết số ký tự văn bản.
2. **`read()` trả kiểu `int`.** Một byte hợp lệ được trả về ở khoảng `0..255`; `-1` là dấu EOF. Khi tự triển khai `InputStream.read()`, chuyển `byte` sang int bằng `& 0xff` như ví dụ để tránh nhầm byte có bit dấu thành giá trị âm.
3. **Đọc một lần không đồng nghĩa đọc đủ.** Kiểm tra `count` từ `read(buffer)` và chỉ xử lý đúng vùng `0..count-1`.
4. **Dung lượng bộ đệm là quyết định hiệu năng, không phải độ dài dữ liệu.** Có thể dùng bộ đệm vài KiB và đọc rất nhiều lượt mà không biết tổng kích thước.
5. **Không giữ vô hạn dữ liệu không tin cậy trong RAM.** `readAllBytes()` và `ByteArrayOutputStream` hữu ích với dữ liệu hữu hạn, có giới hạn; với upload hoặc kết nối dài, xử lý luồng theo khối và áp dụng giới hạn riêng.
6. **Chỉ đóng stream do mình sở hữu.** `try-with-resources` giải phóng tài nguyên trong các chương trình minh họa; trong mã thư viện, cần tuân theo hợp đồng về bên sở hữu stream.

## 9. Tự kiểm tra

**Câu 1.** Một `InputStream` trả `available() == 0`. Có thể khẳng định `read()` ngay sau đó trả `-1` không?

**Trả lời:** Không. Stream có thể còn dữ liệu nhưng không có byte sẵn ngay tại thời điểm đo; hoặc lớp con dùng `available()` mặc định luôn trả `0`. EOF phải được xác định qua thao tác đọc.

**Câu 2.** `ByteArrayInputStream` tạo từ mảng 10 byte, đã đọc thành công 3 byte. Trong điều kiện không có thao tác `mark/reset/skip` khác, `available()` của chính lớp này cho kết quả nào?

**Trả lời:** `7`, vì lớp này biết chính xác lượng byte chưa đọc trong mảng. Đó là đặc điểm của `ByteArrayInputStream`, không phải cam kết chung của mọi stream.

**Câu 3.** Muốn sao chép dữ liệu từ một `InputStream` không biết trước độ dài sang một `OutputStream`, có cần tính `available()` không?

**Trả lời:** Không. Có thể dùng `in.transferTo(out)` hoặc vòng lặp `read(buffer)` và `out.write(buffer, 0, count)` cho đến EOF, kèm giới hạn và xử lý timeout khi phù hợp.

**Ghi nhớ:** `available()` trả về *ước lượng số byte có thể lấy ngay mà không blocking*, **không phải tổng kích thước dữ liệu và không phải phép thử EOF**. Đọc bằng kết quả `read()`; lấy độ dài từ nguồn dữ liệu hoặc giao thức nếu thật sự cần biết trước.
