# EOF bình thường khác dữ liệu bị cắt cụt trong Java I/O

Khi đọc file, socket hoặc một nguồn dữ liệu bằng Java, việc gặp **EOF** (*end of file/end of stream*) có thể là điều hoàn toàn bình thường: nguồn không còn phần tử để đọc. Nhưng EOF cũng có thể xuất hiện **quá sớm** so với lượng dữ liệu một giao thức, định dạng file hay bản ghi yêu cầu; khi đó ứng dụng phải nhận diện **dữ liệu bị cắt cụt** (*truncated data*).

Điểm cốt lõi là **EOF chỉ nói “không còn dữ liệu từ nguồn”; nó không tự xác nhận “thông điệp đã đầy đủ”**. Muốn phân biệt EOF hợp lệ với cắt cụt, chương trình phải biết **điều kiện hoàn tất ở tầng ứng dụng**: kích thước kỳ vọng, dấu kết thúc, số bản ghi, framing, checksum, cấu trúc định dạng hoặc quy tắc được xác định trước.

Bài học thuộc nhóm **Tài nguyên và lỗi** của Java Core I/O. Nội dung hướng dẫn các dấu hiệu EOF trong API, cách đọc đủ dữ liệu, phân biệt kết thúc hợp lệ với kết thúc sớm, các ví dụ Java 17 chạy độc lập, những bẫy với dữ liệu văn bản và mạng, cùng chiến lược kiểm tra tính toàn vẹn.

## 1. Định nghĩa: EOF và truncation không phải hai trạng thái đối lập hoàn toàn

**EOF** (*end of file/end of stream*) là trạng thái cho biết không còn dữ liệu tiếp theo trong nguồn đọc. Trong Java:

- `InputStream.read()` trả **`-1`** khi không còn byte để đọc.
- `Reader.read()` trả **`-1`** khi không còn đơn vị ký tự để đọc.
- `BufferedReader.readLine()` trả **`null`** khi không còn dòng để đọc.
- `DataInputStream` có những thao tác bắt buộc đủ byte, như `readInt()` và `readFully(...)`, có thể ném **`EOFException`** nếu thiếu dữ liệu trước khi hoàn tất.
- `ByteBuffer` và `CharBuffer` không tự đồng nghĩa “EOF”; chúng là bộ đệm. API kênh hoặc bộ giải mã quyết định cách báo trạng thái kết thúc.

**Truncation** là tình huống nội dung **ngắn hơn hoặc thiếu thành phần** so với một định dạng/contract. Ví dụ một khung tin khai báo payload 100 byte nhưng thực tế chỉ nhận được 60 byte trước EOF.

Một nguồn byte có thể kết thúc bình thường ở tầng hệ điều hành nhưng vẫn là dữ liệu **không hợp lệ ở tầng ứng dụng**. Ngược lại, một file ngắn có thể là file hoàn toàn hợp lệ nếu định dạng của nó cho phép độ dài đó.

| Tình huống | Có EOF? | Có bị cắt cụt? | Lý do |
|---|---|---|---|
| File text hợp lệ kết thúc sau dòng cuối không có newline | Có | **Không nhất thiết** | Nhiều quy ước cho phép dòng cuối kết thúc bởi EOF |
| Byte stream không hứa độ dài; caller đọc đến `-1` | Có | **Không thể kết luận chỉ từ EOF** | Không có kích thước/sentinel kỳ vọng |
| Header ghi “payload dài 100 byte” nhưng chỉ có 60 byte | Có | **Có** | Thiếu 40 byte theo contract |
| Header 4 byte mới nhận được 2 byte rồi EOF | Có | **Có**, nếu header 4 byte bắt buộc | Không thể giải mã trọn header |
| File định dạng có footer bắt buộc nhưng footer biến mất | Có | **Có**, nếu footer bắt buộc | Thiếu cấu trúc hoàn tất |
| Kết nối mạng tạm thời chưa có byte để đọc | Chưa chắc | Chưa chắc | Thiếu dữ liệu ngay lúc đó không đồng nghĩa EOF |
| Đọc `read(buffer)` được ít hơn dung lượng buffer | Chưa chắc | Chưa chắc | Một lần đọc ngắn không chứng minh EOF hoặc truncation |

**Chỉ caller hiểu contract mới xác định được lúc nào EOF là bình thường.** API I/O có thể cung cấp dấu hiệu, nhưng không tự biết một bản ghi nghiệp vụ hoàn chỉnh gồm những gì.

## 2. EOF hiển thị như thế nào trong Java?

### `InputStream.read()` và `Reader.read()`

`InputStream.read()` trả về `int` trong khoảng **`0..255`** cho byte thực tế và **`-1`** khi EOF. Vì byte là kiểu có dấu trong Java, việc dùng `int` tránh nhầm byte `0xFF` với giá trị đặc biệt `-1`.

`Reader.read()` trả về `int` trong khoảng **`0..65535`** cho một UTF-16 `char`, hoặc **`-1`** khi EOF. Nó không nhất thiết đọc nguyên một Unicode code point cho mỗi lần gọi; ký tự ngoài BMP có thể gồm hai code unit.

Ví dụ vòng lặp đọc byte đến EOF:

```java
int value;
while ((value = input.read()) != -1) {
    // Xử lý byte từ 0 đến 255.
}
```

Đây là **đoạn minh họa**, không phải chương trình hoàn chỉnh: `input` phải là một `InputStream` đã khởi tạo và phương thức cần xử lý `IOException`. Mẫu vòng lặp đúng là so sánh `value != -1`; không ép về `byte` rồi so `-1`, bởi byte dữ liệu `0xFF` sẽ bị nhầm thành EOF.

`read()` có thể **chặn** (block) để đợi byte, trả byte, báo EOF hoặc ném `IOException` theo đặc tính nguồn. **Đang đợi dữ liệu** không có nghĩa đã tới EOF.

### `read(byte[])` và `read(char[])`

`int n = input.read(buffer)` trả về **số byte thực sự đọc được** hoặc `-1` nếu EOF (với mảng có độ dài dương và theo hợp đồng chuẩn). `Reader.read(char[])` tương tự ở đơn vị UTF-16 code unit.

Không suy luận:

- “Buffer dài 4096, lần này được 100 byte, vậy chắc dữ liệu đã bị cắt.”
- “Mỗi lần đọc phải lấp đầy cả buffer.”
- “Đọc ngắn chính là EOF.”

Một lần đọc có thể hợp lệ dù trả ít hơn số phần tử được yêu cầu. Với mảng/đoạn đọc có `len == 0`, Java có thể trả **`0`**; đừng xem `0` như EOF.

Vòng lặp đọc một luồng không biết trước kích thước:

```java
byte[] buffer = new byte[4096];
int n;
while ((n = input.read(buffer)) != -1) {
    output.write(buffer, 0, n);
}
```

Đây là **mã minh họa**: cần có `input` và `output` đã khởi tạo, quản lý đóng và `IOException`. Mục tiêu là sao chép đến EOF. Nếu có một số byte cần đạt, **phải đếm và xác thực thêm** trước khi coi kết quả thành công.

### Các cách đọc theo dòng

`BufferedReader.readLine()` trả `null` khi không còn dòng; một dòng rỗng hợp lệ trả `""`. Không được dùng `line.isEmpty()` để xác định EOF, vì dòng rỗng là dữ liệu.

Ví dụ:

```java
String line;
while ((line = reader.readLine()) != null) {
    // Có thể là chuỗi rỗng nhưng vẫn là một dòng hợp lệ.
}
```

Đoạn trên cần `reader` là `BufferedReader` đã mở. Cần chú ý `readLine()` **loại dấu kết thúc dòng** (LF, CRLF hoặc CR); vì thế nó có thể đọc cùng một chuỗi dòng cuối dù file có hay không có terminal newline.

## 3. EOF là bình thường khi nào?

EOF có thể là **dấu hiệu hoàn tất hợp lệ** khi giao thức/định dạng yêu cầu đọc cho đến hết nguồn mà **không có điều kiện hoàn tất khác**. Một vài ví dụ:

1. Đọc toàn bộ file text tự do, không yêu cầu dấu xuống dòng cuối.
2. Đọc hết một file nhị phân bất kỳ chỉ để sao chép **toàn bộ nội dung hiện có**, không có số byte kỳ vọng và không cần khẳng định tính nguyên vẹn nguồn ban đầu.
3. Một giao thức ứng dụng được thiết kế dùng **đóng kết nối làm dấu kết thúc thông điệp**, với các điều kiện an toàn phù hợp. Cần phân biệt đây là một lựa chọn framing được quy định, không phải quy tắc của mọi giao thức mạng.
4. Đọc một collection/nguồn hữu hạn được định nghĩa là “tất cả phần tử đến khi không còn phần tử”.

Tại đây, ứng dụng thực thi một contract dạng: *“Lấy những gì nguồn đang cung cấp cho đến EOF.”* EOF là điều kiện dừng của thao tác, không tự báo lỗi.

**Giới hạn:** “Sao chép đến EOF thành công” không chứng minh file hay thông điệp ở nguồn **không bị thiếu so với bản gốc của tác giả**. Nếu không có kích thước, checksum hoặc cấu trúc chuẩn đáng tin cậy để đối chiếu, caller có thể không có cách phát hiện thiếu dữ liệu.

## 4. EOF trở thành dấu hiệu cắt cụt khi nào?

EOF là bất thường khi xuất hiện **trước một điều kiện hoàn tất bắt buộc**. Các dạng thường gặp:

- **Độ dài cố định:** cần đúng 16 byte để đọc một trường nhị phân nhưng chỉ lấy được 11.
- **Độ dài khai báo trong header:** header nói body có 500 byte nhưng nguồn hết khi mới có 200.
- **Dấu kết thúc bắt buộc:** định dạng yêu cầu footer, marker, checksum hoặc thẻ đóng, nhưng đọc hết nguồn mà không gặp.
- **Số lượng phần tử khai báo:** file chứa header “10 bản ghi” nhưng mới parse được 9.
- **Bản ghi nhiều trường:** đã đọc trường đầu nhưng còn thiếu trường bắt buộc.
- **Mã hóa ký tự không hoàn chỉnh:** chuỗi UTF-8 cần thêm continuation byte, nhưng dòng byte kết thúc giữa một code point.
- **Luồng nén hoặc container:** cấu trúc nội bộ yêu cầu footer/CRC/độ dài hoặc block kết thúc mà dữ liệu đã bị cắt bỏ.

Từng trường hợp cần **một tiêu chí kỹ thuật rõ** để xác định thiếu gì. Không nên ném một `EOFException` tùy tiện chỉ vì đạt EOF trong một chương trình vốn thiết kế đọc đến hết file.

### Ví dụ khung dữ liệu độ dài cố định

Giả sử một giao thức quy định:

```text
+--------------------+-------------------------+
| Length (4 byte)    | Payload (length byte)   |
| big-endian signed  |                         |
+--------------------+-------------------------+
```

Nếu byte stream chỉ còn hai byte trong header, **không thể đọc đủ `int`**. Nếu header có đủ nhưng payload ngắn hơn `length`, cũng là cắt cụt. Nếu đủ header và đủ payload, frame là hoàn chỉnh **theo điều kiện độ dài** (dù nội dung payload vẫn có thể không hợp lệ theo nghiệp vụ hoặc charset).

Một điểm quan trọng: header khai báo độ dài phải được kiểm tra **không âm** và **không vượt giới hạn** để tránh cấp phát mảng khổng lồ từ dữ liệu không đáng tin. Khi dữ liệu đến từ mạng, kiểm tra giới hạn kích thước trước khi cấp phát hay đọc đủ payload.

## 5. Các API đọc đến EOF so với API đòi hỏi đủ dữ liệu

| API | Khi hết nguồn | Ý nghĩa |
|---|---|---|
| `InputStream.read()` | Trả `-1` | EOF bình thường ở mức nguồn |
| `InputStream.read(byte[])` | Trả `-1` nếu không còn byte và len dương | Mỗi lần đọc trước đó có thể ngắn |
| `InputStream.readNBytes(int len)` | Trả mảng có **tối đa** `len` byte; có thể ít hơn nếu EOF | **Caller phải kiểm tra** kích thước nếu cần đủ |
| `InputStream.readNBytes(byte[], off, len)` | Trả số byte đã đọc, có thể nhỏ hơn `len` ở EOF | Caller cần so sánh với số byte kỳ vọng |
| `InputStream.readAllBytes()` | Trả mọi byte còn lại đến EOF | Không biết độ dài kỳ vọng nếu caller không cung cấp |
| `InputStream.transferTo(output)` | Trả số byte chuyển được đến EOF | Sao chép đến EOF, không tự xác nhận số byte mong muốn |
| `DataInputStream.readFully(byte[])` | **Ném `EOFException`** nếu chưa điền đủ mảng | Cực kỳ tiện cho trường có độ dài bắt buộc |
| `DataInputStream.readInt()` | Ném `EOFException` nếu chưa có đủ 4 byte | Đọc trường nhị phân cố định |
| `BufferedReader.readLine()` | Trả `null` khi không còn dòng | Không tự kiểm tra newline cuối |
| `Reader.read()` | Trả `-1` | EOF ở mức ký tự |
| `FileChannel.read(ByteBuffer)` | Trả `-1` khi kênh đã tới end-of-stream | Không tự biết số byte định dạng cần |
| `SocketChannel.read(ByteBuffer)` | Trả `-1` nếu kênh đã tới end-of-stream | Chế độ non-blocking còn có thể trả `0` khi chưa đọc được byte |

**Lưu ý:** `EOFException` là lớp con của `IOException`. Nó thường xuất hiện từ API cần một số byte xác định (ví dụ `DataInputStream`), không có nghĩa mọi thao tác `InputStream.read()` đều ném ngoại lệ tại EOF.

Nếu đọc một file mà chỉ biết “đọc đến khi hết”, việc dùng `readAllBytes()` có thể phù hợp cho dữ liệu nhỏ, nhưng gây dùng nhiều RAM với file lớn. Với dữ liệu lớn, ưu tiên đọc khối có giới hạn, stream hoặc các cơ chế phù hợp. Tránh coi `readAllBytes()` là bằng chứng rằng file có cấu trúc đúng.

## 6. Ví dụ 1 — `-1` là EOF, còn đọc thiếu kích thước kỳ vọng phải được kiểm tra

Tạo tệp `StreamEofDemo.java` (Java 17+):

```java
import java.io.ByteArrayInputStream;
import java.io.InputStream;
import java.util.Arrays;

public class StreamEofDemo {
    public static void main(String[] args) throws Exception {
        byte[] bytes = {10, 20};
        try (InputStream in = new ByteArrayInputStream(bytes)) {
            System.out.println("first=" + in.read());
            System.out.println("second=" + in.read());
            System.out.println("EOF=" + in.read());
            System.out.println("EOF again=" + in.read());
        }

        try (InputStream in = new ByteArrayInputStream(bytes)) {
            byte[] result = in.readNBytes(4);
            System.out.println("requested=4, received=" + result.length);
            System.out.println("data=" + Arrays.toString(result));
            System.out.println("complete fixed-size field=" + (result.length == 4));
        }
    }
}
```

Chạy:

```bash
javac -encoding UTF-8 --release 17 StreamEofDemo.java
java StreamEofDemo
```

Đầu ra:

```text
first=10
second=20
EOF=-1
EOF again=-1
requested=4, received=2
data=[10, 20]
complete fixed-size field=false
```

**Giải thích:**

1. Hai lời gọi `read()` đầu lấy byte 10 và 20; lời gọi tiếp theo trả `-1` vì mảng hết dữ liệu. Đó là **EOF bình thường ở tầng stream**. Ví dụ gọi tiếp một lần trên `ByteArrayInputStream` vẫn nhận `-1`.
2. `readNBytes(4)` được yêu cầu **tối đa** 4 byte nhưng mảng chỉ có 2. Nó trả mảng dài 2 **mà không tự ném `EOFException`**.
3. Nếu ứng dụng chỉ muốn “đọc mọi byte đang có”, 2 byte có thể là kết quả hoàn chỉnh. Nếu trường giao thức yêu cầu **chính xác 4 byte**, biểu thức `result.length == 4` là `false` và dữ liệu là **cắt cụt theo contract**.

Đừng coi một giá trị `-1` luôn là lỗi, cũng đừng coi việc `readNBytes` trả về thành công là bằng chứng đã đủ dữ liệu.

## 7. `DataInputStream.readFully` — đọc chính xác độ dài bắt buộc

`DataInputStream` bọc một `InputStream` để đọc các kiểu dữ liệu nhị phân theo quy ước của Java. Hai phương thức rất hữu ích:

- `readInt()` yêu cầu đúng **4 byte**, đọc số nguyên có dấu theo thứ tự big-endian. Nếu hết nguồn khi chưa đủ 4 byte, ném `EOFException`.
- `readFully(byte[])` cố đọc cho đến khi **điền đủ mảng**, nguồn báo EOF hoặc có lỗi I/O. Nếu EOF trước khi điền đủ, ném `EOFException`. Lưu ý không có lời hứa rằng nó sẽ nhanh hay chắc chắn hoàn thành nếu nguồn vẫn mở mà không gửi đủ dữ liệu.

Có thể tự viết vòng lặp đọc đúng n byte và so sánh số lượng, nhưng `readFully` đã cung cấp semantics “phải đủ” rõ ràng cho các trường byte cố định.

### Ví dụ 2 — dữ liệu length-prefixed đầy đủ, thiếu header và thiếu payload

Tạo tệp `FramedPayloadDemo.java` (Java 17+):

```java
import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.DataInputStream;
import java.io.DataOutputStream;
import java.io.EOFException;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.util.Arrays;

public class FramedPayloadDemo {
    static byte[] frame(String text) throws IOException {
        byte[] payload = text.getBytes(StandardCharsets.UTF_8);
        ByteArrayOutputStream out = new ByteArrayOutputStream();
        try (DataOutputStream data = new DataOutputStream(out)) {
            data.writeInt(payload.length);
            data.write(payload);
        }
        return out.toByteArray();
    }

    static String readFrame(byte[] bytes) throws IOException {
        try (DataInputStream in =
                     new DataInputStream(new ByteArrayInputStream(bytes))) {
            int size = in.readInt();
            if (size < 0 || size > 1024) {
                throw new IOException("Invalid length");
            }
            byte[] payload = new byte[size];
            in.readFully(payload);
            return new String(payload, StandardCharsets.UTF_8);
        }
    }

    static void verify(String label, byte[] frame) throws IOException {
        try {
            System.out.println(label + "=" + readFrame(frame));
        } catch (EOFException e) {
            System.out.println(label + "=TRUNCATED (" + e.getClass().getSimpleName() + ")");
        }
    }

    public static void main(String[] args) throws Exception {
        byte[] complete = frame("OK");
        verify("complete", complete);
        verify("short header", new byte[] {0, 0});
        verify("short payload", Arrays.copyOf(complete, complete.length - 1));
    }
}
```

```bash
javac -encoding UTF-8 --release 17 FramedPayloadDemo.java
java FramedPayloadDemo
```

```text
complete=OK
short header=TRUNCATED (EOFException)
short payload=TRUNCATED (EOFException)
```

**Diễn giải ba ca kiểm thử:**

1. **`complete`:** chương trình ghi header `int` bằng độ dài byte của `"OK"` theo UTF-8, rồi ghi đúng payload. `readInt()` và `readFully` thành công.
2. **`short header`:** chỉ hai byte tồn tại trong khi `readInt()` cần bốn; `EOFException` được ném.
3. **`short payload`:** header vẫn khai báo đủ hai byte payload, nhưng mảng đã bị cắt mất một byte cuối. `readFully` phát hiện EOF trước khi đọc đủ.

Trong ví dụ, `size` được giới hạn `0..1024` **trước khi cấp phát mảng**. Đó là một bước an toàn bắt buộc với input không tin cậy; ứng dụng thực tế còn cần ràng buộc bộ nhớ, timeout và tổng số frame.

**Điểm cần chú ý:** ví dụ xác nhận đã nhận đủ **một frame** theo header, nhưng không kiểm tra dữ liệu dư sau frame vì một kết nối thật có thể chứa **nhiều frame nối tiếp**. Nếu định dạng yêu cầu “toàn file chứa đúng một frame và không còn byte thừa”, hãy bổ sung kiểm tra EOF **sau** frame theo hợp đồng đó.

Ngoài ra, `new String(payload, UTF_8)` là bước giải mã text và có thể thay byte UTF-8 không hợp lệ. Việc đủ **số byte** và việc payload là **văn bản UTF-8 hợp lệ** là hai tiêu chí khác nhau, cần kiểm tra riêng nếu định dạng yêu cầu strict Unicode.

## 8. Phân biệt dấu EOF với lỗi I/O khác

Không phải mọi thao tác đọc thất bại đều là EOF:

| Tín hiệu hoặc ngoại lệ | Điều nói được | Không nên kết luận |
|---|---|---|
| `read() == -1` | Nguồn đã báo hết dữ liệu | Toàn thông điệp nghiệp vụ chắc chắn đầy đủ |
| `EOFException` khi `readFully` | Chưa đủ dữ liệu cho thao tác bắt buộc | Bản thân nguồn luôn “có lỗi”; thiếu có thể do file cắt hoặc contract sai |
| `SocketTimeoutException` | Thao tác socket vượt thời gian chờ theo cấu hình | Peer đã đóng và chắc chắn không gửi thêm |
| `IOException` khác | Có vấn đề I/O cụ thể | Mọi lỗi đều chỉ do hết file |
| `read(buffer)` trả số dương nhỏ | Đọc được một phần dữ liệu | Đã EOF hoặc đã bị cắt |
| Đọc non-blocking `SocketChannel` trả `0` | Hiện chưa lấy được byte từ lời gọi này | EOF |
| `BufferedReader.readLine() == null` | Không còn dòng | Dòng cuối phải có newline hay không |

**Timeout khác truncation.** Nếu ứng dụng đang đợi thêm byte của một frame và vượt deadline, có thể báo thao tác **không hoàn tất đúng hạn**; chưa đủ bằng chứng rằng peer đã kết thúc luồng. Có thể retry hoặc hủy theo chính sách, nhưng không được tự coi timeout là EOF.

**Kết nối TCP đóng không đồng nghĩa thông điệp hợp lệ.** Một TCP FIN khiến phía đọc tiến tới EOF sau khi tiêu thụ dữ liệu còn lại, nhưng thông điệp có đủ header/body hay không là trách nhiệm framing ở tầng ứng dụng. TCP reset có thể xuất hiện dưới dạng lỗi I/O chứ không phải EOF sạch. Phải xử lý cả hai đường.

**Đóng nguồn bởi code của chính ứng dụng khác việc nguồn đã tự hết dữ liệu.** Gọi `close()` để giải phóng tài nguyên không phải cơ chế phát hiện bản ghi đã hoàn chỉnh.

## 9. Văn bản: dòng cuối không có newline có phải bị cắt?

Không có quy tắc chung rằng file text **phải** kết thúc bằng LF. Nhiều chương trình đọc được dòng cuối mà không có dấu xuống dòng. `BufferedReader.readLine()` có thể trả lại dòng cuối ở cả hai trường hợp:

```text
"alpha\nbeta"   (không có LF ở cuối)
"alpha\nbeta\n" (có LF ở cuối)
```

Cả hai đều có hai nội dung dòng là `alpha` và `beta`. Nếu gọi `readLine()` lần thứ ba, cả hai đều trả `null`. Nhưng **byte gốc khác nhau** và hợp đồng của một định dạng cụ thể có thể yêu cầu newline cuối.

### Ví dụ 3 — `readLine` không tự xác nhận terminal newline

Tạo tệp `TextLineEofDemo.java`:

```java
import java.io.BufferedReader;
import java.io.StringReader;

public class TextLineEofDemo {
    static void show(String label, String text) throws Exception {
        try (BufferedReader reader = new BufferedReader(new StringReader(text))) {
            System.out.println(label + " line1=" + reader.readLine());
            System.out.println(label + " line2=" + reader.readLine());
            System.out.println(label + " EOF=" + (reader.readLine() == null));
            System.out.println(label + " terminal LF=" + text.endsWith("\n"));
        }
    }

    public static void main(String[] args) throws Exception {
        show("no LF", "alpha\nbeta");
        show("with LF", "alpha\nbeta\n");
    }
}
```

```bash
javac -encoding UTF-8 --release 17 TextLineEofDemo.java
java TextLineEofDemo
```

```text
no LF line1=alpha
no LF line2=beta
no LF EOF=true
no LF terminal LF=false
with LF line1=alpha
with LF line2=beta
with LF EOF=true
with LF terminal LF=true
```

`readLine()` chỉ cho biết nội dung và EOF theo logic dòng, nên không cung cấp dấu terminator đã bị loại. Trong ví dụ, chương trình còn giữ `text` gốc nên tự kiểm tra `endsWith("\n")` được. Nếu dữ liệu có thể dùng CR hoặc CRLF, kiểm tra trailing terminator phải bao gồm quy tắc tương ứng thay vì chỉ LF.

Khi một định dạng bắt buộc **mọi bản ghi phải kết thúc bằng LF**, thiếu LF cuối có thể là lỗi format hoặc dấu hiệu truncation. Nếu format cho phép dòng cuối kết thúc bởi EOF, thiếu LF **không phải lỗi**. Không thể quyết định chỉ qua việc nhìn thấy `readLine() == null`.

### Định dạng có cấu trúc và dòng

Một parser CSV, JSON hoặc log có thể có cú pháp kết thúc riêng. Ví dụ CSV cho phép newline bên trong trường trích dẫn theo quy tắc parser; đọc `readLine()` không đủ để xác định bản ghi đã hoàn tất. JSON có thể kết thúc hợp lệ ở EOF nếu đối tượng/cấu trúc đã đóng đầy đủ; đọc được nửa một object trước EOF là văn bản **chưa hoàn chỉnh về cú pháp**.

**Dòng vật lý** và **bản ghi logic** là hai khái niệm khác nhau. Cần parser đúng định dạng, không chỉ logic đếm newline.

## 10. EOF giữa một UTF-8 code point: malformed input

Một file văn bản có thể đủ số byte của một khối theo logic nào đó nhưng lại kết thúc giữa **chuỗi mã hóa nhiều byte**. Chẳng hạn ký tự `€` là UTF-8 `E2 82 AC` (ba byte). Nếu file chỉ còn `E2 82` ở cuối, chuỗi UTF-8 chưa hoàn chỉnh.

`CharsetDecoder` ở chế độ strict có thể ném `MalformedInputException` khi được thông báo đã đến cuối input mà còn thiếu continuation byte. Trong khi đó, các API dễ dùng như `new String(bytes, StandardCharsets.UTF_8)` thường **thay** đầu vào sai bằng `U+FFFD` thay vì ném ngoại lệ.

### Ví dụ 4 — UTF-8 kết thúc giữa code point

Tạo tệp `TruncatedUtf8Demo.java`:

```java
import java.nio.ByteBuffer;
import java.nio.charset.CharacterCodingException;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;
import java.util.Arrays;

public class TruncatedUtf8Demo {
    public static void main(String[] args) throws Exception {
        byte[] valid = "A\u20ac".getBytes(StandardCharsets.UTF_8);
        byte[] truncated = Arrays.copyOf(valid, valid.length - 1);
        System.out.println("complete matches="
                + "A\u20ac".equals(new String(valid, StandardCharsets.UTF_8)));

        try {
            StandardCharsets.UTF_8.newDecoder()
                    .onMalformedInput(CodingErrorAction.REPORT)
                    .decode(ByteBuffer.wrap(truncated));
        } catch (CharacterCodingException e) {
            System.out.println("strict decoder=" + e.getClass().getSimpleName());
        }

        String lenient = new String(truncated, StandardCharsets.UTF_8);
        System.out.println("lenient decoder="
                + lenient.replace("\uFFFD", "<U+FFFD>"));
    }
}
```

```bash
javac -encoding UTF-8 --release 17 TruncatedUtf8Demo.java
java TruncatedUtf8Demo
```

```text
complete matches=true
strict decoder=MalformedInputException
lenient decoder=A<U+FFFD>
```

**Diễn giải:**

- `valid` chứa byte UTF-8 cho `A€`. Bỏ byte cuối của `€` tạo chuỗi byte không hợp lệ.
- Decoder strict gặp input chưa hoàn chỉnh khi đã tới cuối và ném `MalformedInputException`. Đây là lỗi **mã hóa văn bản**, độc lập với việc giao thức bên ngoài có khai báo tổng số byte hay không.
- `new String(...)` trong trường hợp này chèn replacement `U+FFFD`. Để stdout ổn định bất kể font console, ví dụ đổi riêng ký tự replacement thành chuỗi `<U+FFFD>` trước khi in.
- **Không phải mọi byte bị thiếu đều khiến decoder phát hiện được.** Nếu một byte cuối biến mất nhưng phần byte còn lại vẫn là UTF-8 hợp lệ, bộ giải mã có thể không báo gì; chỉ framing/độ dài/checksum mới xác định được đoạn text bị thiếu theo contract.

Với đọc từng chunk, đừng đánh dấu `endOfInput=true` chỉ vì một **chunk** chưa đủ byte. Một mã UTF-8 hợp lệ có thể bị chia giữa hai lần đọc; phải giữ state của decoder cho đến khi nguồn thực sự kết thúc.

## 11. Dùng framing để biết đâu là “đã nhận đủ”

Các mô hình framing phổ biến có ưu/nhược điểm khác nhau:

### 11.1 Độ dài cố định

Một bản ghi có đúng **N byte**. Caller phải đọc đủ N bằng `DataInputStream.readFully` hoặc vòng lặp tích lũy đến N. Nếu EOF trước N thì báo thiếu. Phù hợp với header cố định hoặc record binary có layout định trước.

### 11.2 Length-prefix

Header chứa độ dài của payload tiếp theo. Sau khi đọc header **đủ**, kiểm tra giới hạn rồi đọc đúng số byte đó. Nếu EOF trước số byte đã khai báo, đây là truncation. Cần quyết định header tính theo **byte** hay **ký tự**; trong giao thức byte stream, kích thước payload thường là số byte và phải được tính từ byte đã mã hóa.

**Không dùng `String.length()` làm số byte UTF-8.** Ký tự tiếng Việt hoặc emoji thường dùng nhiều byte, khác độ dài UTF-16. Ví dụ truyền string `"😊"` có `String.length() == 2` nhưng UTF-8 cần **4 byte**; nếu header ghi độ dài 2, receiver sẽ đọc sai framing.

### 11.3 Delimiter hoặc marker kết thúc

Đọc đến ký hiệu phân tách (ví dụ LF, sentinel byte hay terminator chuyên dụng). Nếu contract yêu cầu marker, EOF trước marker có thể là lỗi. Nhưng phải có quy tắc escaping/quoting nếu marker có thể xuất hiện trong payload. Khi delimiter là LF, có thể cần hỗ trợ CRLF tùy đặc tả, không suy luận từ nền tảng.

### 11.4 Đóng luồng là dấu kết thúc

Một số protocol dùng “đến khi peer đóng kết nối” làm dấu kết thúc body. Khi đó EOF **có thể** là điều kiện hoàn tất theo framing đó. Tuy nhiên, nếu upstream cắt dữ liệu rồi đóng sạch, receiver có thể **không phát hiện** nếu không có độ dài/checksum/marker ngoài. Vì thế cần cân nhắc khả năng chẩn đoán thiếu dữ liệu.

### 11.5 Checksum, hash hoặc footer

Checksum có thể giúp phát hiện dữ liệu đã nhận bị thay đổi hoặc thiếu, **nếu** giá trị kỳ vọng được truyền/lưu theo cách đáng tin và thuật toán phù hợp. Với file nén hoặc container, footer/CRC và cấu trúc cuối có thể giúp parser phát hiện kết thúc bất thường.

**Lưu ý:** checksum thông thường như CRC không cung cấp tính xác thực chống giả mạo; nếu đối thủ có thể sửa cả nội dung và CRC, cần MAC hoặc chữ ký phù hợp. Kiểm tra số byte và checksum còn phải tách khỏi **xác thực ngữ nghĩa** của dữ liệu.

## 12. Một quy trình đọc frame đáng tin cậy

Với một protocol có header độ dài và payload, quy trình điển hình:

1. **Xác định contract**: header dài bao nhiêu byte, thứ tự byte (endianness), độ dài body tính theo byte hay ký tự, số lượng frame, encoding, cách kết thúc kết nối.
2. **Đọc đủ header**. Nếu EOF khi chưa có phần nào của header, kiểm tra contract: đó có thể là kết thúc hợp lệ của *danh sách frame*; nếu EOF giữa header thì thường là truncation. Trong ví dụ `readFrame` cho **một frame bắt buộc**, EOF ngay trước header cũng là lỗi.
3. **Validate header**: từ chối length âm, vượt giới hạn, header không hợp lệ. Không cấp phát array theo số không kiểm soát.
4. **Đọc đủ body** theo length đã xác thực. Dùng `readFully` hoặc tích lũy byte đến đúng length. Nếu EOF trước length thì báo lỗi thiếu dữ liệu.
5. **Kiểm tra integrity**: checksum, footer, số record, schema, giải mã strict khi cần.
6. **Xử lý phần còn lại** theo protocol: nếu có nhiều frame, lặp đến điều kiện dừng. Nếu chỉ cho đúng một frame, kiểm tra byte dư theo quy định.
7. **Đóng tài nguyên** bằng `try-with-resources` khi caller sở hữu nguồn; xử lý timeout/hủy sao cho không giữ file descriptor hoặc kết nối vô thời hạn.
8. **Báo lỗi có ngữ cảnh**: tên record, độ dài kỳ vọng và byte đã đọc; hạn chế ghi nội dung bí mật thô vào log.

### Ví dụ thuật toán kiểm tra số byte

Đây là **mã minh họa** dùng trong một phương thức có `InputStream in`, `int expected` và xử lý `IOException`:

```java
if (expected < 0 || expected > 1_000_000) {
    throw new IllegalArgumentException("Invalid length");
}
byte[] payload = in.readNBytes(expected);
if (payload.length != expected) {
    throw new java.io.EOFException(
            "Expected " + expected + " bytes, got " + payload.length);
}
// Đọc đủ số byte; tiếp theo cần validate nội dung theo format.
```

Cách trên dùng `readNBytes` và kiểm tra độ dài. `DataInputStream.readFully` giúp chuyển ngay điều kiện thiếu byte thành `EOFException`; nhưng sau exception từ `readFully`, không phải lúc nào bạn cũng biết chính xác đã đọc được bao nhiêu byte từ mảng nếu chưa đếm riêng.

Nếu body lớn, không nhất thiết cấp phát toàn bộ vào một mảng; có thể lặp với buffer giới hạn, tích lũy số byte nhận được và truyền sang parser/đích streaming.

## 13. Không dùng `available()` để đoán EOF hoặc completeness

`InputStream.available()` trả **ước lượng số byte có thể đọc mà không chặn** theo hợp đồng của stream. Nó không phải tổng kích thước nguồn, số byte còn lại chắc chắn trong file hay độ dài message ở tầng ứng dụng.

Sai lầm phổ biến:

```java
// KHÔNG nên dùng available() làm điều kiện hoàn tất:
while (input.available() > 0) {
    input.read();
}
```

Đây là **đoạn minh họa sai**, không phải quy trình đọc đúng. Với network stream, `available() == 0` có thể chỉ là chưa có byte sẵn **ngay lúc kiểm tra**, chứ không phải peer đã đóng. Chương trình có thể dừng quá sớm và coi một message dở dang là hoàn chỉnh.

Đúng hơn:

- Nếu đọc “cho đến EOF”, gọi `read()`/`read(buffer)` đến `-1`.
- Nếu cần đủ N byte, thực hiện phép đọc đủ và so sánh với N.
- Nếu protocol dùng delimiter, parser phải tìm delimiter theo quy tắc.
- Nếu cần timeout, sử dụng timeout/deadline như điều kiện lỗi/hủy độc lập, không giả làm EOF.

## 14. Trường hợp tương tự trong NIO và xử lý phi đồng bộ

Đối với `ReadableByteChannel`/`FileChannel` và `SocketChannel`, ý tưởng vẫn vậy nhưng tín hiệu cụ thể cần xem tài liệu của từng loại kênh.

- Với một channel được đọc đến EOF, `read(ByteBuffer)` có thể trả **`-1`** khi tới end-of-stream.
- Với `SocketChannel` ở chế độ **non-blocking**, một lần gọi `read` trả **`0`** có thể chỉ nói “hiện chưa đọc được byte nào”; nó không đồng nghĩa EOF. Caller phải đợi readiness hoặc sự kiện phù hợp rồi tiếp tục.
- `ByteBuffer.remaining()` là số phần tử còn có thể đọc/ghi trong **buffer**, không phải kích thước byte còn lại trên socket hoặc tính hoàn chỉnh của frame.
- Nếu một callback/event cung cấp 300 byte nhưng message yêu cầu 500, phải **giữ state của frame** và tích lũy ở các sự kiện tiếp theo. Không ném truncation chỉ vì một lần đọc chưa đủ.
- Khi kênh thực sự báo end-of-stream, so sánh trạng thái parser hiện tại với quy tắc hoàn tất. Nếu còn dang dở header, body, delimiter, thì báo incomplete/truncated.

**Ranh giới chunk không phải ranh giới message.** TCP là byte stream: số lần `write` ở sender không có quan hệ một-một với số lần `read` ở receiver. Đây là lý do thiết kế protocol cần framing rõ ràng, không phụ thuộc vào “mỗi lần read là một bản ghi”.

## 15. File I/O, độ dài và tính nhất quán khi đọc

Với file có sẵn, `Files.size(path)` có thể giúp biết kích thước hiện tại trước khi đọc, nhưng **không phải bằng chứng tuyệt đối** rằng số byte đó sẽ luôn sẵn trong một file bị sửa đồng thời. File có thể thay đổi sau khi đo kích thước.

Một quy trình an toàn hơn là xác định yêu cầu:

- Nếu cần **snapshot nhất quán**, sử dụng cơ chế snapshot, khóa hoặc phương án thiết kế phù hợp với hệ thống file và môi trường.
- Nếu định dạng file có **length nội bộ**, kiểm tra số byte thực đọc so với length đó.
- Nếu cần bảo đảm **đúng bản phát hành**, so sánh checksum/hash với nguồn kỳ vọng đáng tin.
- Với file đang được ghi tiếp (ví dụ log append-only), EOF hiện tại thường chỉ có nghĩa **chưa có byte mới tại thời điểm đọc**, chứ không có nghĩa producer sẽ không ghi thêm vào tương lai. Nếu muốn “follow” file, phải dùng cơ chế polling/watch/tailing riêng.
- Nếu dữ liệu bị cắt bởi thao tác sao chép/download, kiểm tra kích thước kỳ vọng, HTTP metadata có độ tin cậy phù hợp, checksum hoặc định dạng kết thúc file.

**Đừng biến một lần đọc ngắn thành việc ghi đè file.** Trước hết phải xác định nguồn có phải đang được cập nhật, read có bị timeout hay không, và contract nào xác nhận sự thiếu hụt.

## 16. Nguyên tắc xử lý exception, tài nguyên và retry

### Nhận diện đúng loại thất bại

- **EOF hợp lệ:** kết thúc vòng lặp hoặc trạng thái parse hoàn chỉnh theo contract.
- **Dữ liệu bị cắt cụt:** báo lỗi cấp ứng dụng (có thể dùng `EOFException` khi thiếu byte bắt buộc), ghi rõ expected vs actual nếu biết.
- **I/O failure:** xử lý `IOException`/lỗi mạng tương ứng, không đánh đồng với byte stream kết thúc.
- **Hết hạn:** xử lý timeout và chính sách hủy/retry riêng, không tự chuyển thành kết quả EOF thành công.
- **Định dạng sai:** ví dụ length âm, UTF-8 malformed hoặc cấu trúc payload lỗi, cần thông báo rõ nguyên nhân thay vì chỉ ghi “EOF”.

Trong Java, `EOFException` là subtype của `IOException`. Khi cần phân nhánh cụ thể:

```java
try {
    data.readFully(payload);
} catch (java.io.EOFException e) {
    // Dữ liệu đầu vào thiếu so với payload.length.
    throw e;
} catch (java.io.IOException e) {
    // Lỗi I/O khác.
    throw e;
}
```

Đây là **đoạn minh họa**, cần `data` là `DataInputStream`, `payload` là `byte[]` đã khởi tạo và phương thức khai báo `throws IOException` hoặc xử lý tiếp. Tránh bắt `Exception` chung rồi trả một chuỗi trống, vì như vậy không còn phân biệt “bản ghi trống hợp lệ” với “bản ghi bị lỗi”.

### Retry và khả năng đọc lại

Retry hợp lý nếu nguyên nhân có thể là lỗi tạm thời và caller có nguồn có thể khôi phục hoặc yêu cầu lại. Với stream đã đọc dở, **không tự giả định** có thể tua lại rồi đọc lần nữa. `mark/reset` chỉ khả dụng theo hợp đồng cụ thể, và socket thường không cho tua ngược byte đã tiêu thụ.

Nếu đã ghi một phần output trước khi phát hiện truncation, cần quản lý **atomicity**: ghi vào file tạm, kiểm tra hoàn tất/integrity rồi mới đổi tên hoặc commit, thay vì công bố ngay file dở dang như kết quả thành công. Chính sách atomic move còn tùy nền tảng và filesystem.

### Đóng tài nguyên

Dùng `try-with-resources` với nguồn/đích mà bạn sở hữu. Đóng tài nguyên giúp không rò rỉ file descriptor/socket, nhưng **không phải kiểm tra tính hoàn chỉnh**. Kiểm tra length, delimiter, checksum hay trạng thái parser **trước khi** đánh dấu tác vụ thành công.

## 17. Những lỗi lập trình thường gặp

1. **Đọc `read() == -1` là luôn xảy ra lỗi.** Nếu contract là đọc đến EOF, đây là kết thúc bình thường.
2. **Gặp EOF rồi trả thành công cho mọi message.** Nếu frame yêu cầu N byte thì EOF trước N là truncation.
3. **Coi read ngắn là kết thúc.** Một lần `read(buffer)` không phải lời hứa sẽ điền đầy buffer.
4. **Không so sánh `readNBytes(n).length` với `n`.** API có thể trả ít hơn n nếu EOF.
5. **Dùng `available() == 0` để kết luận EOF.** Nó chỉ biểu thị số byte đọc được không chặn theo ước lượng, không phải thông điệp kết thúc.
6. **Quên `readFully`/header length validation.** Dữ liệu thiếu hoặc header độc hại có thể gây lỗi, cấp phát bộ nhớ không kiểm soát.
7. **Dùng `String.length()` làm độ dài byte UTF-8.** Một emoji ngoài BMP chiếm hai UTF-16 code unit nhưng bốn byte UTF-8.
8. **Giả định `readLine()` phân biệt dòng cuối có newline.** Phương thức này bỏ terminator.
9. **Coi file không có LF cuối là truncation trong mọi trường hợp.** Phải xem định dạng có yêu cầu LF cuối không.
10. **Dùng decoder thay thế mặc định để xác thực văn bản nghiêm ngặt.** Dữ liệu UTF-8 cuối file bị cắt có thể biến thành `U+FFFD` thay vì lỗi.
11. **Không phân biệt timeout và EOF.** Timeout nghĩa là chưa hoàn tất đúng thời gian; không chứng minh nguồn đã đóng.
12. **Giả định một lần `SocketChannel.read` là một message.** TCP có thể phân đoạn hoặc gộp byte bất kỳ.
13. **Giả định checksum luôn đủ.** Checksum kiểm tra một lớp integrity theo mô hình tin cậy cụ thể; không thay thế framing hoặc xác thực schema.
14. **Bỏ qua dữ liệu dư sau message duy nhất.** Nếu format quy định đúng một frame thì byte thừa cũng là vi phạm contract.
15. **Coi `readAllBytes` thành công là format file hợp lệ.** Nó chỉ đã đọc đến EOF; parser/validator vẫn phải kiểm tra nội dung.
16. **Giữ file kết quả dở dang như file hoàn chỉnh.** Chỉ công bố output sau khi mọi điều kiện hoàn tất đã được xác nhận.

## 18. Bảng quyết định nhanh

| Mục tiêu | Dấu hiệu thành công | Cách làm |
|---|---|---|
| Duyệt byte đến hết nguồn | Gặp `read() == -1` sau khi xử lý mọi byte trước đó | Vòng lặp `read` đến EOF |
| Đọc đúng trường N byte | Đã tích lũy **đúng N byte** | `readFully` hoặc `readNBytes` + kiểm tra length |
| Đọc header 4 byte | `readInt` đọc đủ | Bắt `EOFException` khi thiếu |
| Đọc frame length-prefixed | Header hợp lệ và body đủ length | Validate length, `readFully`, validate payload |
| Đọc file text tự do | Parser chấp nhận hết input | `BufferedReader`/`Files`, kiểm tra quy tắc định dạng |
| Xác nhận newline cuối | Có terminator theo contract | Phân tích text thô/byte thô, không chỉ `readLine()` |
| Xác nhận text UTF-8 hợp lệ | Decoder strict chấp nhận toàn bộ byte | `CharsetDecoder` với `REPORT` |
| Xử lý socket non-blocking | Parser đã nhận đủ frame, không chỉ một lần `read` có dữ liệu | Tích lũy state qua các lần đọc |
| Phát hiện file bị cắt khi tải xuống | Đủ số byte và integrity theo metadata đáng tin | Length + checksum/hash khi có |
| Xử lý lỗi tạm thời | Retry/hủy theo policy rõ ràng | Phân biệt timeout, EOF, IOException |

## 19. Tự kiểm tra

**Câu 1.** Một `InputStream` chỉ chứa 2 byte. Gọi `read()` ba lần trả 10, 20, -1. Có thể khẳng định dữ liệu bị cắt không?  
**Đáp án:** không. EOF bình thường cho nguồn 2 byte; chỉ bị cắt nếu có contract yêu cầu nhiều hơn.

**Câu 2.** `input.readNBytes(100)` trả mảng có 73 byte mà không ném exception. Điều đó có hợp lệ không?  
**Đáp án:** có theo API, nếu EOF đến sớm. Nhưng nếu caller **bắt buộc** phải có 100 byte thì phải báo thiếu 27 byte.

**Câu 3.** Vì sao `DataInputStream.readFully` có thể ném `EOFException` nhưng `InputStream.read()` lại trả `-1`?  
**Đáp án:** `readFully` có điều kiện hoàn tất là **đủ số byte**, nên EOF trước khi đủ là ngoại lệ; `read()` đơn lẻ chỉ báo tình trạng nguồn.

**Câu 4.** `BufferedReader.readLine()` trả `"last"` rồi lần sau trả `null`. File có LF cuối không?  
**Đáp án:** không thể biết chỉ từ `readLine()`, vì terminator đã bị bỏ.

**Câu 5.** Một message có header khai báo 64 byte body nhưng chỉ nhận được 30 byte rồi TCP FIN. Đó là gì?  
**Đáp án:** EOF ở byte stream; **truncation ở tầng framing** do thiếu 34 byte so với khai báo.

**Câu 6.** `SocketChannel.read` non-blocking trả `0`. Đây có phải EOF?  
**Đáp án:** không. Thao tác hiện chưa đọc được byte nào; EOF được biểu thị bằng `-1` theo contract tương ứng.

**Câu 7.** Chuỗi byte UTF-8 kết thúc `E2 82` rồi EOF. Có thể coi là text UTF-8 hợp lệ không?  
**Đáp án:** không. Bộ giải mã strict phát hiện chuỗi mã hóa nhiều byte chưa hoàn tất ở cuối input.

**Câu 8.** Một file text kết thúc ngay sau ký tự cuối của dòng không có LF. Có mặc nhiên lỗi không?  
**Đáp án:** không; tùy định dạng có yêu cầu newline cuối hay không.

## Kết luận

**EOF là tín hiệu hết dữ liệu của nguồn, còn “dữ liệu bị cắt cụt” là kết luận dựa trên hợp đồng đầy đủ của định dạng hoặc giao thức.** Java dùng `-1` hay `null` để báo kết thúc bình thường ở nhiều API đọc; các phép đọc đủ như `DataInputStream.readFully` có thể ném `EOFException` khi thiếu byte bắt buộc. Để không chấp nhận nhầm một thông điệp dở dang, hãy quy định rõ length, delimiter, footer, checksum hoặc trạng thái parser; kiểm tra đủ dữ liệu, xử lý riêng timeout/I/O failure và quản lý tài nguyên đúng vòng đời.

### Tài liệu tra cứu Java SE 17

- [`InputStream`: `read`, `readNBytes`, `readAllBytes`, `transferTo`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/InputStream.html)
- [`DataInputStream`: `readInt`, `readFully`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/DataInputStream.html)
- [`EOFException`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/EOFException.html)
- [`BufferedReader.readLine`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/BufferedReader.html)
- [`SocketChannel.read`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/SocketChannel.html)
- [`CharsetDecoder` và `CodingErrorAction`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/charset/CharsetDecoder.html)
