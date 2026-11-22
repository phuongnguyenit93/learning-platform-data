# readNBytes và khác biệt với readAllBytes trong Java I/O

**InputStream** đọc luồng dữ liệu dạng byte. Hai phương thức **readNBytes(...)** và **readAllBytes()** đều trả về các byte được lấy từ *vị trí hiện tại* của luồng, nhưng giải quyết hai nhu cầu khác nhau: **đọc tối đa N byte** và **đọc toàn bộ phần còn lại đến EOF**. Chọn sai API có thể làm mất ranh giới bản tin, đọc thiếu dữ liệu, chờ vô hạn hoặc dùng quá nhiều bộ nhớ.

## 1. Những phương thức cần phân biệt

| API thuộc InputStream | Có từ Java | Trả về | Dừng khi nào |
| --- | --- | --- | --- |
| **byte[] readNBytes(int len)** | 11 | Mảng mới chứa 0 đến **len** byte | Đã đọc đủ **len**, gặp EOF hoặc lỗi I/O |
| **int readNBytes(byte[] b, int off, int len)** | 9 | Số byte thực tế ghi vào mảng có sẵn | Đã đọc đủ **len**, gặp EOF hoặc lỗi I/O |
| **byte[] readAllBytes()** | 9 | Mảng mới chứa tất cả byte còn lại | Gặp EOF hoặc lỗi I/O |
| **int read(byte[] b)** | 1.0 | Số byte đọc được hoặc **-1** khi EOF | Có thể trả về ngay khi đọc được một phần byte |

**EOF** (end of stream) nghĩa là cuối luồng; **len** là số byte yêu cầu, không phải số ký tự. Cả ba phương thức đầu tiên **không đóng InputStream**. Chúng tiêu thụ dữ liệu theo đúng thứ tự: byte đã đọc sẽ không xuất hiện lần nữa, trừ khi tạo luồng mới hoặc thiết lập và sử dụng reset trên luồng có hỗ trợ.

Một lần **read(buffer)** có thể trả về ít hơn kích thước buffer mặc dù dữ liệu vẫn còn. **readNBytes(...)** cố tiếp tục đọc cho đủ số byte được chỉ định; nó có thể trả về ít hơn nếu gặp EOF. Nếu chương trình cần *chính xác* N byte, phải tự kiểm tra kết quả hoặc dùng **DataInputStream.readFully(...)**.

## 2. Cơ chế của readNBytes(int len)

~~~java
byte[] firstFive = input.readNBytes(5);
~~~

Với **len = 5**, Java cố đọc 5 byte từ vị trí hiện tại. Nếu đủ 5 byte trước EOF, mảng trả về dài 5 và dữ liệu còn lại vẫn nằm trong luồng. Nếu chỉ còn 3 byte đến EOF, phương thức trả về mảng dài 3; **không tự ném EOFException vì thiếu 2 byte**. Nếu đang ở EOF, kết quả là mảng rỗng. Nếu **len = 0**, cũng trả về mảng rỗng nhưng không đọc. **len < 0** gây **IllegalArgumentException**.

Phương thức có thể chặn luồng thực thi trong lúc chờ cho đến khi đọc đủ **len**, gặp EOF hoặc gặp lỗi I/O. Một luồng mạng mới gửi 3 byte nhưng vẫn giữ kết nối mở có thể khiến **readNBytes(5)** tiếp tục chờ 2 byte nữa. Do đó, **len** chỉ giới hạn *số byte*, hoàn toàn không giới hạn *thời gian chờ*.

Mảng byte được trả về vừa bằng số byte thực nhận, không tự đệm 0 cho đủ kích thước. Tuy nhiên, nó vẫn cần bộ nhớ tỷ lệ với lượng dữ liệu đọc và có thể gặp **OutOfMemoryError** nếu lượng được yêu cầu quá lớn. Lỗi nguồn đọc có thể ném **IOException**.

## 3. Cơ chế của readAllBytes()

~~~java
byte[] remaining = input.readAllBytes();
~~~

Phương thức **readAllBytes()** đọc cho đến EOF, rồi trả về một mảng chứa **mọi byte còn lại**. Nếu đã đọc 4 byte của luồng 10 byte, sau đó gọi **readAllBytes()**, mảng chỉ có 6 byte. Phương thức không quay về đầu luồng.

Khác với **readNBytes(int len)**, **readAllBytes()** không có tham số để đặt giới hạn byte. Với file lớn, nguồn không tin cậy hoặc luồng vô hạn, việc dồn toàn bộ dữ liệu vào RAM có thể gây áp lực bộ nhớ hoặc **OutOfMemoryError**. Với socket giữ mở, lời gọi có thể tiếp tục chờ cho tới khi nhận EOF dù một phần dữ liệu đã đến.

**Không dùng available() để đo kích thước toàn bộ luồng**: nó chỉ biểu thị ước lượng byte có thể đọc mà không chặn lúc đó, không phải tổng byte còn lại. Cả hai API đều khác với kiểm tra dữ liệu “đang sẵn có”.

## 4. So sánh theo tình huống thực tế

| Câu hỏi | **readNBytes(int len)** | **readAllBytes()** |
| --- | --- | --- |
| Có giới hạn lượng dữ liệu theo tham số? | Có: tối đa **len** byte | Không |
| Có đọc tiếp cho đến EOF dù đã đủ N byte? | Không | Có |
| Nếu EOF đến sớm? | Trả mảng có thể ngắn hơn **len** | Trả toàn bộ byte đã lấy được |
| Luồng giữ mở khi chưa đủ dữ liệu? | Có thể chặn để chờ đủ N | Có thể chặn để chờ EOF |
| Phù hợp đọc header/prefix N byte? | Có | Không, vì sẽ lấy cả phần còn lại |
| Phù hợp đọc một file nhỏ, hữu hạn? | Nếu chỉ cần phần đầu hoặc N byte | Có, nếu chấp nhận chi phí RAM |
| Phù hợp dữ liệu lớn không rõ độ dài? | Dùng từng khối có giới hạn | Nên tránh |
| Có đóng luồng sau lời gọi? | Không | Không |

Nếu cần đọc một khung dữ liệu có độ dài được khai báo trong header, **readNBytes(expectedLength)** hữu ích vì có thể dừng ở ranh giới đó. Nếu cần chính xác độ dài, **bắt buộc kiểm tra bytes.length**. Nếu mục tiêu là lấy toàn bộ một tài nguyên nhỏ, có EOF rõ ràng, **readAllBytes()** tiện hơn.

## 5. Ví dụ Java 17+ chạy được: lượng byte đọc và vị trí luồng

Lưu thành **ReadNBytesDemo.java**:

~~~java
import java.io.ByteArrayInputStream;
import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;

public class ReadNBytesDemo {
    public static void main(String[] args) throws IOException {
        byte[] source = "ABCDEFGHIJ".getBytes(StandardCharsets.US_ASCII);

        // Đọc 4 byte, sau đó đọc phần còn lại.
        try (InputStream in = new ByteArrayInputStream(source)) {
            byte[] prefix = in.readNBytes(4);
            byte[] remaining = in.readAllBytes();
            System.out.println("prefix=" +
                    new String(prefix, StandardCharsets.US_ASCII));
            System.out.println("remaining=" +
                    new String(remaining, StandardCharsets.US_ASCII));
        }

        // Yêu cầu nhiều byte hơn số byte đang có đến EOF.
        try (InputStream in = new ByteArrayInputStream(
                "XYZ".getBytes(StandardCharsets.US_ASCII))) {
            byte[] five = in.readNBytes(5);
            byte[] afterEnd = in.readNBytes(2);
            System.out.println("requested=5, actual=" + five.length);
            System.out.println("bytes=" +
                    new String(five, StandardCharsets.US_ASCII));
            System.out.println("afterEOF=" + afterEnd.length);
        }

        // Biến thể ghi vào buffer có sẵn, offset = 1.
        try (InputStream in = new ByteArrayInputStream(
                "123456".getBytes(StandardCharsets.US_ASCII))) {
            byte[] buffer = new byte[4];
            int count = in.readNBytes(buffer, 1, 3);
            System.out.println("buffer count=" + count + ", segment=" +
                    new String(buffer, 1, count, StandardCharsets.US_ASCII));
            System.out.println("tail=" +
                    new String(in.readAllBytes(), StandardCharsets.US_ASCII));
        }
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac ReadNBytesDemo.java
java ReadNBytesDemo
~~~

Kết quả:

~~~text
prefix=ABCD
remaining=EFGHIJ
requested=5, actual=3
bytes=XYZ
afterEOF=0
buffer count=3, segment=123
tail=456
~~~

Luồng đầu chứa “ABCDEFGHIJ”; **readNBytes(4)** lấy “ABCD”, rồi **readAllBytes()** chỉ lấy “EFGHIJ”. Luồng “XYZ” chỉ có 3 byte, nên **readNBytes(5)** trả về mảng dài 3, và lần sau ở EOF trả về mảng dài 0. Với buffer dài 4, cách gọi **readNBytes(buffer, 1, 3)** ghi “123” vào các phần tử từ chỉ số 1 đến 3; 3 byte “456” vẫn còn.

## 6. readNBytes(byte[] b, int off, int len): điểm dễ nhầm với read

Biến thể này nhận mảng đích có sẵn và trả về **int count** (số byte vừa ghi), tránh phải nhận một mảng mới cho mỗi lần đọc. Các vị trí chứa dữ liệu mới là **b[off]** đến **b[off + count - 1]**. Những phần tử khác có thể vẫn chứa dữ liệu cũ; không xử lý toàn bộ **len** phần tử khi **count < len**.

Điều kiện biên và ngoại lệ:

- Mảng **b** bằng null: **NullPointerException**.
- **off < 0**, **len < 0** hoặc **len > b.length - off**: **IndexOutOfBoundsException**.
- **len = 0**: trả về 0, không đọc gì.
- EOF trước khi có byte nào: trả về **0**, kể cả khi **len > 0**.
- EOF sau khi nhận một phần: trả về số byte thực đọc, có thể nhỏ hơn **len**.
- Lỗi I/O: có thể ném **IOException** sau khi đã sửa một phần mảng đích.

Điểm khác quan trọng: **read(...)** báo EOF bằng **-1** khi yêu cầu có độ dài dương; **readNBytes(buffer, off, len)** trả về **0** ở EOF. Vì thế, một vòng lặp dùng **while (n != -1)** vốn dành cho **read(...)** không thể bê nguyên sang biến thể **readNBytes**: dễ lặp vô hạn ở EOF.

Nếu cần đọc theo khối kích thước cố định trong một luồng hữu hạn, có thể gọi **readNBytes(buffer, 0, buffer.length)** và xử lý đúng đoạn từ chỉ số 0 đến **count - 1**. Với **count == 0** và kích thước yêu cầu dương, luồng đã tới EOF trong điều kiện hoạt động thông thường.

## 7. Đọc đúng N byte cho giao thức: kiểm tra EOF

Một bản tin có thể ghi độ dài payload trong header. Nếu header nói có 5 byte nhưng người gửi chỉ truyền 3 byte rồi đóng luồng, **readNBytes(5)** trả về 3 byte. Coi đó là bản tin hợp lệ là lỗi ứng dụng. Cần so độ dài và ném **EOFException** khi dữ liệu bị cắt.

Ví dụ phương thức đọc payload (lưu thành **PayloadReader.java**; lớp biên dịch độc lập, nhưng chưa có **main** để chạy riêng):

~~~java
import java.io.EOFException;
import java.io.IOException;
import java.io.InputStream;

public final class PayloadReader {
    private static final int MAX_PAYLOAD_BYTES = 1024 * 1024;

    private PayloadReader() {
    }

    public static byte[] readPayload(InputStream in, int expectedBytes)
            throws IOException {
        // Chặn độ dài âm/quá lớn, đặc biệt khi lấy từ input bên ngoài.
        if (expectedBytes < 0 || expectedBytes > MAX_PAYLOAD_BYTES) {
            throw new IllegalArgumentException("Invalid payload length");
        }

        byte[] payload = in.readNBytes(expectedBytes);
        if (payload.length != expectedBytes) {
            throw new EOFException(
                    "Truncated payload: expected " + expectedBytes +
                    " bytes, got " + payload.length);
        }
        return payload;
    }
}
~~~

**MAX_PAYLOAD_BYTES** đặt ngưỡng để không cấp phát tùy tiện khi độ dài do bên ngoài cung cấp. Với nguồn mạng, cần thêm **timeout** theo giao thức/kết nối; đặt ngưỡng byte không ngăn một kết nối đang mở nhưng ngừng gửi dữ liệu làm thao tác đọc chờ lâu.

Một lựa chọn cho yêu cầu **phải đọc chính xác N byte** là **DataInputStream.readFully(byte[])**: nó ném **EOFException** nếu không đọc đủ trước EOF. **readNBytes(...)** chủ ý trả về dữ liệu ngắn hơn khi EOF, vì vậy hợp đồng sử dụng khác nhau.

## 8. Bộ nhớ, dữ liệu lớn và mã hóa ký tự

**InputStream** xử lý *byte*, không phải *ký tự*. UTF-8 có thể mã hóa một ký tự bằng nhiều byte; lấy đúng 5 byte chưa chắc lấy đúng 5 ký tự. Không nên giải mã từng fragment tùy ý khi ranh giới có thể cắt ngang một ký tự UTF-8. Đối với dữ liệu văn bản, dùng charset tường minh như **StandardCharsets.UTF_8**, hoặc đọc qua **InputStreamReader** khi thích hợp.

**readAllBytes()** thích hợp cho dữ liệu **nhỏ, hữu hạn và có giới hạn thực tế**. File vài GB hay luồng vô hạn nên xử lý tăng dần theo buffer, tránh dồn toàn bộ vào mảng. Ví dụ sao chép file bằng luồng (Java 17+):

~~~java
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.nio.file.Files;
import java.nio.file.Path;

public class CopyFileDemo {
    public static void main(String[] args) throws IOException {
        Path source = Path.of("input.bin");
        Path target = Path.of("output.bin");

        try (InputStream in = Files.newInputStream(source);
             OutputStream out = Files.newOutputStream(target)) {
            long copied = in.transferTo(out);
            System.out.println("Copied bytes: " + copied);
        }
    }
}
~~~

Chương trình cần có file **input.bin** trước khi chạy; số byte in ra tùy kích thước file thực tế. **transferTo(OutputStream)** đọc đến EOF và ghi sang đích mà không yêu cầu mã ứng dụng gom toàn bộ nội dung vào một **byte[]** lớn. Đối với luồng mạng hoặc nguồn chậm, thời gian chờ và lỗi đọc/ghi vẫn phải được xử lý.

## 9. Những lỗi thường gặp

1. **Ngộ nhận readNBytes(N) luôn trả về N byte.** Độ dài có thể ngắn hơn khi EOF; hãy kiểm tra độ dài nếu yêu cầu đủ khung dữ liệu.
2. **Ngộ nhận readAllBytes() đọc lại từ đầu.** Nó đọc từ vị trí hiện tại; các byte đã tiêu thụ trước đó không tự quay lại.
3. **Dùng readAllBytes() cho nguồn không giới hạn.** Dữ liệu quá lớn có thể chiếm RAM đáng kể hoặc gây OOME; đặt ngưỡng và đọc theo khối.
4. **Nhầm giữa read và readNBytes(buffer, ...).** EOF của **read(...)** được báo bằng -1; EOF của biến thể **readNBytes(buffer, ...)** được báo bằng 0.
5. **Dùng available() như kích thước file/luồng.** Đây không phải tổng byte còn lại và không phải tín hiệu EOF đáng tin.
6. **Cho rằng readNBytes() có timeout.** Số byte tối đa không phải thời gian tối đa; luồng mạng vẫn có thể chặn.
7. **Giải mã UTF-8 theo mảnh byte cắt tùy ý.** Mảnh byte có thể thiếu một phần ký tự; cần quản lý ranh giới hoặc dùng bộ giải mã phù hợp.
8. **Quên đóng tài nguyên.** Hai phương thức không tự gọi close; dùng **try-with-resources** khi sở hữu luồng.

## 10. Tự kiểm tra kiến thức

- Đọc **readNBytes(4)** trên một luồng 10 byte, rồi **readAllBytes()**: số byte lần lượt là **4** và **6**.
- Đọc **readNBytes(7)** trên luồng còn 2 byte rồi EOF: kết quả dài **2**, không tự ném EOFException.
- Đọc **readAllBytes()** từ socket vẫn mở: có thể chặn chờ **EOF**, dù một số byte đã được gửi.
- Đọc frame bắt buộc đủ 8 byte: dùng **readNBytes(8)** và kiểm tra **length == 8** (hoặc **DataInputStream.readFully**), kèm giới hạn độ dài và timeout khi cần.
- Đọc 3 byte vào **buffer[1..3]** bằng **readNBytes(buffer, 1, 3)**: chỉ xử lý **count** byte thực đọc; EOF của API này trả 0.

**Kết luận:** **readNBytes** giới hạn lượng byte theo **N**, còn **readAllBytes** lấy **tất cả byte còn lại tới EOF**. Chúng khác nhau về ranh giới đọc, thời điểm dừng, bộ nhớ cần dùng và tình huống áp dụng.

### Tham khảo

- [Oracle Java SE 11 — InputStream](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/io/InputStream.html): hợp đồng **readNBytes**, **readAllBytes** và mốc **Since**.
- [Oracle Java SE 11 — DataInputStream](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/io/DataInputStream.html): **readFully** và **EOFException**.
