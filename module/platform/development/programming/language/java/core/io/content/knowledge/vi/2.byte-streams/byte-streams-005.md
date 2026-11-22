# Ghi đúng số byte thực tế đã đọc trong Java byte stream

Khi sao chép dữ liệu từ `InputStream` sang `OutputStream`, **chỉ ghi số byte mà lần gọi `read` vừa trả về**. Một buffer có thể chứa nhiều vị trí chưa được ghi mới, nên việc ghi toàn bộ buffer sau mỗi lần đọc có thể làm dữ liệu đầu ra bị thừa hoặc sai.

## 1. Kết quả cần nắm

- `read(buffer)` trả về **số byte thực sự đọc được trong lần gọi hiện tại**, không phải kích thước của buffer.
- Với buffer có độ dài lớn hơn 0, giá trị trả về thường là số dương từ `1` đến `buffer.length`; `-1` báo đã hết dữ liệu (EOF). Không được hiểu một lần đọc ngắn là EOF.
- Dùng `output.write(buffer, 0, bytesRead)` để ghi chính xác đoạn buffer hợp lệ, bắt đầu tại vị trí `0` và dài `bytesRead` byte.
- Tiếp tục đọc đến khi `read` trả `-1`. Không dùng `available()`, số byte mong đợi hoặc kích thước buffer làm tín hiệu kết thúc.

Đây là quy tắc áp dụng cho tệp nhị phân, ảnh, ZIP, dữ liệu mạng và cả văn bản khi xử lý ở mức byte.

## 2. `read` đã thay đổi phần nào của buffer?

Ví dụ một buffer dài 8 byte và nguồn chỉ còn 2 byte cuối:

```text
buffer.length = 8

Lần đọc trước:  [A B C D E F G H]     -> bytesRead = 8
Lần đọc cuối:   [I J C D E F G H]     -> bytesRead = 2
                 ^ ^ |
          chỉ 2 byte mới; C..H là dữ liệu cũ trong buffer
```

Hai byte mới hợp lệ là `I` và `J`. Sáu vị trí còn lại **không được phép ghi ra**, dù chúng vẫn chứa ký tự từ lần đọc trước. Sau khi `read` trả về `2`, lệnh `write(buffer)` sẽ ghi cả 8 byte, biến 10 byte đầu vào thành 16 byte đầu ra trong tình huống này.

Cần phân biệt ba đại lượng:

| Đại lượng | Ý nghĩa |
| --- | --- |
| `buffer.length` | Dung lượng bộ nhớ đệm được cấp phát |
| `bytesRead` | Số byte hợp lệ của **lần đọc hiện tại** |
| `totalBytes` | Tổng các giá trị `bytesRead` dương đã được ghi trong cả quá trình |

`read(buffer)` có thể trả ít hơn `buffer.length` dù nguồn **chưa** kết thúc. Điều này có thể xảy ra với luồng mạng, thiết bị, luồng bọc hoặc nguồn tự giới hạn số byte của mỗi lượt đọc.

## 3. Lỗi điển hình và cách sửa

**Sai: ghi toàn bộ buffer sau mỗi lượt đọc.**

```java
byte[] buffer = new byte[8192];
int bytesRead;

while ((bytesRead = input.read(buffer)) != -1) {
    output.write(buffer);  // Sai khi bytesRead < buffer.length
}
```

`OutputStream.write(byte[])` ghi toàn bộ mảng; phương thức này không biết bao nhiêu byte vừa được `read` đưa vào mảng. Dữ liệu cũ có thể bị lặp ở cuối, làm sai tệp đích, checksum hoặc nội dung giao thức.

**Đúng: ghi đúng đoạn vừa đọc.**

```java
byte[] buffer = new byte[8192];
int bytesRead;

while ((bytesRead = input.read(buffer)) != -1) {
    output.write(buffer, 0, bytesRead);
}
```

Đây là **đoạn mã minh họa nằm trong phương thức đã có `input` và `output`**, chưa phải một chương trình độc lập. Ý nghĩa các tham số của `write(buffer, 0, bytesRead)` là:

- `buffer`: mảng chứa các byte vừa nhận.
- `0`: vị trí bắt đầu của dữ liệu hợp lệ.
- `bytesRead`: số byte cần ghi, lấy trực tiếp từ kết quả `read`.

Nếu đọc bằng `input.read(buffer, offset, length)`, vùng vừa đọc hợp lệ sẽ bắt đầu từ `offset`; khi đó lệnh tương ứng là `output.write(buffer, offset, bytesRead)`. Không được mặc định offset luôn bằng 0 trong mọi chương trình.

## 4. Chương trình Java 17+ chạy được: chủ động tạo các lần đọc ngắn

`ByteArrayInputStream` trực tiếp thường có thể trả về đủ số byte yêu cầu. Để kiểm chứng rằng một lần `read` **không bắt buộc** lấp đầy buffer, ví dụ này bọc luồng nguồn và cố ý giới hạn mỗi lần đọc ở tối đa 3 byte, trong khi buffer có độ dài 8.

Lưu toàn bộ mã sau vào **`ReadActualBytesDemo.java`**:

```java
import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.FilterInputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.nio.charset.StandardCharsets;
import java.util.Arrays;

public class ReadActualBytesDemo {

    public static void main(String[] args) throws IOException {
        byte[] original = "ABCDEFGHIJ".getBytes(StandardCharsets.UTF_8);

        try (InputStream input = new MaxChunkInputStream(
                 new ByteArrayInputStream(original), 3);
             ByteArrayOutputStream output = new ByteArrayOutputStream()) {

            long copied = copy(input, output);
            byte[] result = output.toByteArray();

            System.out.println("Total bytes: " + copied);
            System.out.println("Result: " +
                    new String(result, StandardCharsets.UTF_8));
            System.out.println("Same bytes: " +
                    Arrays.equals(original, result));
        }
    }

    static long copy(InputStream input, OutputStream output)
            throws IOException {
        byte[] buffer = new byte[8];
        long total = 0;
        int bytesRead;

        while ((bytesRead = input.read(buffer)) != -1) {
            output.write(buffer, 0, bytesRead);
            total += bytesRead;
            System.out.println("Read: " + bytesRead);
        }

        output.flush();
        return total;
    }

    static final class MaxChunkInputStream extends FilterInputStream {
        private final int maxChunk;

        MaxChunkInputStream(InputStream source, int maxChunk) {
            super(source);
            if (maxChunk <= 0) {
                throw new IllegalArgumentException("maxChunk must be > 0");
            }
            this.maxChunk = maxChunk;
        }

        @Override
        public int read(byte[] b, int off, int len) throws IOException {
            return super.read(b, off, Math.min(len, maxChunk));
        }
    }
}
```

Biên dịch và chạy (bắt buộc tên tệp trùng tên `public class`):

```bash
javac -encoding UTF-8 ReadActualBytesDemo.java
java ReadActualBytesDemo
```

**Stdout chính xác:**

```text
Read: 3
Read: 3
Read: 3
Read: 1
Total bytes: 10
Result: ABCDEFGHIJ
Same bytes: true
```

Diễn giải từng vòng lặp:

1. Buffer có 8 vị trí, nhưng wrapper chỉ cho đọc `3` byte đầu (A–C); chỉ ghi 3 byte.
2. Hai lần kế tiếp lần lượt đọc D–F và G–I, mỗi lần ghi đúng 3 byte.
3. Lần cuối còn J nên `read` trả `1`; chỉ ghi byte J. Lần kế tiếp trả `-1`, vòng lặp kết thúc.
4. Tổng byte ghi là `3 + 3 + 3 + 1 = 10`, bằng chiều dài nguồn. `Arrays.equals` chứng minh từng byte của đầu ra đúng với đầu vào.

Wrapper giới hạn dữ liệu chỉ để thử nghiệm tình huống đọc ngắn một cách có thể lặp lại. Trong thực tế, số byte của mỗi lượt đọc phụ thuộc vào `InputStream` cụ thể; tính đúng đắn của vòng lặp không phụ thuộc vào việc buffer được lấp đầy.

## 5. Áp dụng để sao chép tệp

Khi làm việc với tệp, hãy mở và đóng cả hai luồng bằng `try-with-resources`. Ví dụ phương thức sau có thể đặt trong một class cùng các `import` tương ứng:

```java
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.nio.file.Files;
import java.nio.file.Path;

static long copyFile(Path source, Path destination) throws IOException {
    try (InputStream input = Files.newInputStream(source);
         OutputStream output = Files.newOutputStream(destination)) {
        byte[] buffer = new byte[8192];
        long totalBytes = 0;
        int bytesRead;

        while ((bytesRead = input.read(buffer)) != -1) {
            output.write(buffer, 0, bytesRead);
            totalBytes += bytesRead;
        }

        return totalBytes;
    }
}
```

Đoạn trên là **phương thức minh họa**, chưa phải file Java độc lập: đưa các `import` lên đầu file class, rồi đặt `copyFile` bên trong class. `Files.newOutputStream(destination)` với tùy chọn mặc định sẽ tạo mới hoặc cắt ngắn tệp đích có sẵn; hãy chọn đường dẫn đích khác đường dẫn nguồn và quyết định rõ chính sách ghi đè trước khi chạy.

Việc đóng `OutputStream` bằng `try-with-resources` sẽ giải phóng tài nguyên và đảm bảo luồng được đóng ngay cả khi có lỗi. Nếu sao chép dữ liệu mạng hay dữ liệu nhị phân, không chuyển từng khối byte thành `String`: một ký tự UTF-8 có thể nằm trên ranh giới giữa hai lần `read`, và dữ liệu nhị phân tùy ý không phải văn bản.

## 6. Những giới hạn và phân biệt quan trọng

### EOF không đồng nghĩa với đọc thiếu buffer

Điều kiện kết thúc là `bytesRead == -1`. Giá trị `1`, `2` hoặc bất kỳ số dương nhỏ hơn kích thước buffer **vẫn là dữ liệu hợp lệ**. Không dừng vòng lặp sau một lần đọc ngắn, nếu không dữ liệu về sau sẽ bị mất.

Với `InputStream` thông thường, khi đọc bằng buffer có kích thước lớn hơn 0, phương thức blocking `read(byte[])` chờ có byte, EOF hoặc lỗi; `0` là kết quả hợp lệ khi yêu cầu độ dài `0` qua `read(b, off, 0)`. Nếu phải tích hợp một adapter khác có thể trả `0` liên tục, cần hiểu contract của adapter và tránh vòng lặp quay CPU vô hạn; ví dụ ở trên dùng đúng contract của `InputStream`.

### Một lần `write` và số byte ghi

`OutputStream.write(buffer, off, len)` được yêu cầu ghi đúng `len` byte hoặc báo lỗi bằng ngoại lệ; nó trả về `void` nên không có “số byte đã ghi” để cộng thêm. Trong vòng lặp trên, `totalBytes` được tăng bằng `bytesRead` sau khi lệnh ghi thành công. Không nhầm API này với một số API channel có thể trả số byte đã ghi, ví dụ `WritableByteChannel.write`.

### Khi cần *chính xác N byte*, thay vì đọc đến EOF

Nếu định dạng giao thức yêu cầu đọc đủ `N` byte (chẳng hạn header có độ dài cố định), một lần gọi `read(buffer)` không bảo đảm đủ `N`. Có thể dùng `DataInputStream.readFully(buffer)` để đọc đủ hoặc ném `EOFException` nếu nguồn kết thúc sớm; hoặc dùng `InputStream.readNBytes(N)`, kiểm tra độ dài mảng trả về và xử lý nếu thiếu. Đây là bài toán khác với sao chép toàn bộ luồng đến EOF.

### Có thể dùng API sao chép sẵn

Từ Java 9 có `input.transferTo(output)` để truyền toàn bộ byte còn lại từ một `InputStream` sang `OutputStream` và trả về tổng số byte đã truyền. API này hữu ích khi chỉ cần sao chép, nhưng việc tự viết vòng lặp giúp hiểu rõ quy tắc dùng kết quả `read` để xác định vùng dữ liệu được ghi.

## 7. Các lỗi thường gặp cần tránh

| Cách làm | Hậu quả | Cách làm đúng |
| --- | --- | --- |
| `output.write(buffer)` ở mọi vòng | Có thể ghi cả byte cũ hoặc byte chưa thuộc dữ liệu mới | `output.write(buffer, 0, bytesRead)` |
| Cho rằng `read` luôn trả `buffer.length` | Sai với nhiều loại luồng; mất hoặc hỏng dữ liệu | Dùng giá trị `bytesRead` thực tế |
| Thoát khi `bytesRead < buffer.length` | Cắt mất dữ liệu khi gặp short read | Chỉ kết thúc khi `bytesRead == -1` |
| Dùng `while (input.available() > 0)` | `available()` chỉ ước lượng byte có thể đọc không chặn, không phải EOF | Lặp theo kết quả `read` |
| Gọi `write(buffer, 0, buffer.length)` | Tương đương ghi cả buffer dù vừa đọc ít hơn | Truyền `bytesRead` vào tham số thứ ba |
| Coi buffer là chuỗi ký tự | Có thể cắt đôi ký tự hoặc làm sai dữ liệu nhị phân | Giữ nguyên byte trong thao tác copy |
| Quên đóng luồng file | Rò rỉ tài nguyên, dữ liệu đệm có thể chưa hoàn tất | Dùng `try-with-resources` |

## 8. Tự kiểm tra

1. Buffer có 8 byte, `read` lần lượt trả `8`, `2`, rồi `-1`. Tổng số byte cần ghi là bao nhiêu? **10 byte**, chia thành hai lệnh `write(buffer, 0, 8)` và `write(buffer, 0, 2)`.
2. Một lần `read` trả `3` trên buffer 8192 byte: có phải hết luồng? **Không**; tiếp tục gọi `read`.
3. Đầu ra có dung lượng lớn hơn đầu vào sau khi sao chép một file ảnh: cần kiểm tra gì trước? **Kiểm tra có chỗ nào gọi `write(buffer)` hoặc truyền nhầm `buffer.length` thay vì `bytesRead` hay không.**
4. Muốn sao chép nhị phân và đảm bảo đúng từng byte: nên kiểm tra bằng gì? **So sánh trực tiếp byte (ví dụ `Arrays.equals` với dữ liệu nhỏ) hoặc so sánh checksum/hash và kích thước với tệp lớn.**

**Quy tắc thực hành:** `read` quyết định *bao nhiêu byte vừa hợp lệ*; `write(buffer, offset, bytesRead)` chỉ được ghi đúng số byte đó.