# I/O là gì? Vai trò của nguồn, đích và dữ liệu

Trong Java, **I/O (Input/Output — nhập/xuất)** là hoạt động chương trình **nhận dữ liệu từ bên ngoài** hoặc **đưa dữ liệu ra bên ngoài** ranh giới xử lý của nó. “Bên ngoài” không nhất thiết là Internet hay thiết bị vật lý: một tệp, bàn phím, kết nối mạng, tiến trình khác và vùng nhớ chứa sẵn byte đều có thể tham gia I/O.

Một hoạt động I/O luôn nên được mô tả bằng ba thành phần:

- **Nguồn (source):** nơi dữ liệu được đọc hoặc nhận.
- **Dữ liệu (data):** nội dung di chuyển từ nguồn sang đích; cần hiểu định dạng, kích thước và cách mã hóa của nó.
- **Đích (destination):** nơi dữ liệu được ghi hoặc gửi đến.

**Chiều “input” và “output” được xác định theo góc nhìn của chương trình đang xét**, không phải theo tên thiết bị.

## 1. Phân biệt input và output

- **Input:** dữ liệu đi **vào chương trình**. Ví dụ: chương trình đọc nội dung `config.txt`, nhận dòng người dùng nhập hoặc đọc byte từ một kết nối.
- **Output:** dữ liệu đi **ra khỏi chương trình**. Ví dụ: chương trình ghi `report.txt`, hiển thị kết quả ra standard output hoặc gửi một phản hồi qua mạng.
- Cùng một chương trình thường làm cả hai: đọc một tệp nguồn, biến đổi nội dung, rồi ghi sang tệp đích.

```text
                    INPUT                          OUTPUT
[Nguồn: tệp/bàn phím/mạng] ---> [CHƯƠNG TRÌNH] ---> [Đích: tệp/màn hình/mạng]
                  dữ liệu đi vào               dữ liệu đi ra
```

Ví dụ, một ứng dụng chuyển đổi văn bản: `raw.txt` là **nguồn**, các byte/chuỗi đọc được là **dữ liệu đầu vào**; chương trình chuyển sang chữ hoa; `upper.txt` là **đích** chứa **dữ liệu đầu ra**. Nội dung đầu ra có thể khác nội dung đầu vào vì chương trình đã xử lý nó.

I/O không đồng nghĩa với tính toán. Phép `sum = a + b` xử lý dữ liệu đang có trong bộ nhớ nhưng tự nó không đọc từ nguồn bên ngoài hoặc ghi ra đích bên ngoài. Ngược lại, `System.out.println(sum)` thực hiện output.

## 2. Nguồn (source): chương trình lấy dữ liệu ở đâu?

Nguồn có thể là:

| Nguồn | Ví dụ Java | Điều chương trình nhận |
|---|---|---|
| Bàn phím hoặc standard input | `System.in` | Byte đi vào luồng nhập chuẩn; có thể được giải mã thành ký tự |
| Tệp trên hệ thống tệp | `Files.newInputStream(path)` hoặc `Files.readString(path)` | Byte hoặc văn bản được đọc từ tệp |
| Kết nối mạng | `socket.getInputStream()` | Byte do đầu bên kia truyền tới |
| Vùng nhớ | `ByteArrayInputStream` | Byte đã được đặt sẵn trong mảng |
| Dữ liệu được tạo từ thành phần khác | Một `InputStream` do thư viện cung cấp | Byte nhận qua giao diện đọc |

Một nguồn không nhất thiết “tự đẩy” dữ liệu vào Java: chương trình thường chủ động gọi `read()` hoặc một API đọc. Lời gọi đọc có thể cần chờ dữ liệu, gặp cuối luồng hoặc phát sinh lỗi. Đừng mặc định một lần đọc là đủ cho toàn bộ nội dung.

**Nguồn là vai trò tại một bước cụ thể, không phải thuộc tính cố định của một tệp.** `fileA.txt` là nguồn khi được đọc; nếu một bước khác ghi vào chính tệp đó, nó trở thành đích của bước ghi.

## 3. Đích (destination): dữ liệu được đưa đi đâu?

Đích có thể là:

| Đích | Ví dụ Java | Tác dụng |
|---|---|---|
| Standard output | `System.out` | In thông tin ra luồng xuất chuẩn, thường thấy trong terminal |
| Standard error | `System.err` | Gửi thông báo lỗi ra luồng lỗi chuẩn |
| Tệp | `Files.newOutputStream(path)` hoặc `Files.writeString(path, text)` | Lưu dữ liệu vào tệp |
| Kết nối mạng | `socket.getOutputStream()` | Gửi byte cho đầu bên kia |
| Vùng nhớ | `ByteArrayOutputStream` | Gom byte đầu ra trong bộ nhớ |

`System.out` **không luôn đồng nghĩa với màn hình**. Khi chạy `java Main > output.txt`, shell chuyển hướng standard output sang tệp; từ góc nhìn Java, chương trình vẫn ghi vào `System.out`.

Khi ghi, chương trình cần biết **đích có cho phép ghi không**, **ghi mới hay nối tiếp**, và **khi nào dữ liệu đã được chuyển từ bộ đệm tới tầng bên dưới**. Ghi ra một luồng không tự bảo đảm dữ liệu đã được lưu bền vững trên đĩa hoặc phía nhận đã xử lý nó.

## 4. Dữ liệu (data): thứ thực sự được truyền

I/O vận chuyển **dữ liệu**, không nhất thiết vận chuyển trực tiếp đối tượng Java theo nguyên dạng trong bộ nhớ. Hai cách nhìn quan trọng:

1. **Byte (nhị phân):** phù hợp với ảnh, file nén, âm thanh, dữ liệu giao thức, hoặc sao chép file bất kỳ. `InputStream` đọc byte; `OutputStream` ghi byte.
2. **Ký tự/văn bản:** phù hợp với chữ, dòng cấu hình, dữ liệu text. `Reader` đọc ký tự; `Writer` ghi ký tự. Khi lưu/truyền văn bản thành byte, cần một **bảng mã ký tự** (charset) như UTF-8.

Ví dụ, chuỗi Java `"Xin chào"` là văn bản, còn khi ghi tệp UTF-8, chuỗi được **mã hóa thành byte**. Khi đọc tệp thành chuỗi, các byte cần được **giải mã đúng bảng mã**. Nếu ghi bằng UTF-8 nhưng đọc theo bảng mã khác, chữ tiếng Việt có thể bị sai. Đối với tệp nhị phân, không tùy tiện chuyển mọi byte thành `String`.

Ngoài nội dung, cần biết **ranh giới dữ liệu**: một tệp có điểm cuối, một thông điệp mạng có thể cần quy tắc độ dài hoặc dấu phân cách, và việc đọc vài byte không nhất thiết nhận được “một thông điệp” hoàn chỉnh.

```text
VĂN BẢN                   BYTE                       VĂN BẢN
"Xin chào" --mã hóa UTF-8--> [dãy byte] --giải mã UTF-8--> "Xin chào"
```

## 5. Dòng chảy I/O trong Java

Với thao tác sao chép tệp:

```text
source.txt  --đọc byte-->  bộ đệm trong Java  --ghi byte-->  destination.txt
    NGUỒN                     DỮ LIỆU                      ĐÍCH
```

- `InputStream.read(byte[])` yêu cầu lấy byte từ nguồn vào bộ đệm. Giá trị trả về là **số byte thực tế đã đọc**, hoặc `-1` khi hết luồng. Không được giả định mỗi lần đọc đầy bộ đệm.
- `OutputStream.write(buffer, 0, count)` chỉ ghi `count` byte hợp lệ vừa đọc. Ghi cả mảng có thể đưa thêm dữ liệu cũ/không hợp lệ.
- Bộ đệm là vùng giữ dữ liệu tạm thời giữa lần đọc và ghi. **Bộ đệm không phải nguồn/đích cuối cùng** của ví dụ này.
- `try-with-resources` đóng các luồng khi rời khối, kể cả khi xảy ra ngoại lệ. `IOException` biểu thị những lỗi I/O cần được xử lý hoặc khai báo.

Trong Java có nhiều mức API. `Files.readString(path, UTF_8)`/`Files.writeString(path, text, UTF_8)` tiện cho văn bản kích thước phù hợp với bộ nhớ; `InputStream`/`OutputStream` cho phép xử lý dữ liệu theo từng khối, thích hợp khi muốn sao chép byte không phụ thuộc định dạng. `Reader`/`Writer` thích hợp khi cần xử lý ký tự thay vì byte.

## 6. Ví dụ chạy được: nguồn tệp, đích tệp, dữ liệu là byte

Ví dụ dùng Java 17+, tạo hai tệp tạm, ghi một văn bản UTF-8 vào tệp nguồn, **sao chép các byte** từ nguồn sang đích bằng luồng I/O, rồi đọc đích để kiểm tra. File nguồn và đích được xóa khi chương trình kết thúc.

Lưu mã sau thành **`IoRolesDemo.java`**:

```java
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Arrays;

public class IoRolesDemo {
    public static void main(String[] args) throws IOException {
        Path source = Files.createTempFile("io-source-", ".txt");
        Path destination = Files.createTempFile("io-destination-", ".txt");

        try {
            Files.writeString(source, "Xin chào I/O\n", StandardCharsets.UTF_8);

            try (InputStream input = Files.newInputStream(source);
                 OutputStream output = Files.newOutputStream(destination)) {
                byte[] buffer = new byte[8192];
                int count;

                while ((count = input.read(buffer)) != -1) {
                    output.write(buffer, 0, count);
                }
            }

            System.out.print(Files.readString(destination, StandardCharsets.UTF_8));
            System.out.println("Cùng dữ liệu: " +
                    Arrays.equals(Files.readAllBytes(source),
                                  Files.readAllBytes(destination)));
        } finally {
            Files.deleteIfExists(source);
            Files.deleteIfExists(destination);
        }
    }
}
```

Biên dịch và chạy trong thư mục chứa tệp mã nguồn:

```bash
javac -encoding UTF-8 IoRolesDemo.java
java IoRolesDemo
```

Kết quả chuẩn khi chương trình chạy thành công:

```text
Xin chào I/O
Cùng dữ liệu: true
```

Đọc ví dụ theo **nguồn → dữ liệu → đích**:

1. `Files.writeString` chuẩn bị nội dung trong **tệp nguồn**. Ở bước chuẩn bị này, `source` là **đích của thao tác ghi**.
2. `Files.newInputStream(source)` mở luồng **đọc từ tệp nguồn**; ở bước sao chép, `source` có vai trò **nguồn**.
3. `input.read(buffer)` nhận tối đa `buffer.length` byte mỗi lần; biến `count` cho biết lượng byte hợp lệ. Dữ liệu lúc này chỉ tạm nằm trong `buffer`.
4. `Files.newOutputStream(destination)` mở luồng ghi tới **tệp đích**; `output.write(buffer, 0, count)` đưa các byte vừa đọc sang đó.
5. `Files.readString(destination, UTF_8)` đọc **lại tệp đích** thành văn bản để in ra standard output. Lúc này `destination` đổi vai trò thành **nguồn của bước kiểm tra**, còn `System.out` là **đích của bước in**.
6. `Arrays.equals` so sánh các byte thực sự trong hai tệp; `true` chứng minh nội dung byte bằng nhau trong lần chạy này. Việc đóng luồng và xóa tệp tạm làm rõ vòng đời tài nguyên.

Điểm cốt lõi: **một đường đi I/O có thể gồm nhiều bước; vai trò nguồn/đích được xác định riêng cho mỗi bước**. “Dữ liệu” có thể biến đổi giữa các bước, nhưng ví dụ sao chép byte trên cố ý giữ nguyên.

## 7. Ví dụ ngắn: người dùng nhập, chương trình trả kết quả

`System.in` là **nguồn**; dòng nhập được giải mã thành `String` là **dữ liệu**; `System.out` là **đích**. Đoạn dưới là **phần thân phương thức**, cần đặt vào phương thức Java có `throws IOException` hoặc xử lý ngoại lệ và có các import tương ứng.

```java
BufferedReader reader = new BufferedReader(
        new InputStreamReader(System.in, StandardCharsets.UTF_8));

System.out.print("Nhập tên: ");
String name = reader.readLine();
System.out.println("Chào, " + name);
```

Import cần dùng: `java.io.BufferedReader`, `java.io.InputStreamReader` và `java.nio.charset.StandardCharsets`. Người dùng gõ `Lan` rồi Enter thì dòng phản hồi là `Chào, Lan`; lời nhắc và nội dung người dùng tự gõ không nên nhầm với dữ liệu do chương trình đọc hoặc xuất. Trong ví dụ này không đóng `System.in` vì đây là luồng chuẩn thường được các phần khác của chương trình tiếp tục sử dụng.

Nếu đầu vào đã được chuyển hướng từ tệp, `reader.readLine()` vẫn đọc standard input. Tương tự, standard output có thể được chuyển hướng sang tệp mà không cần sửa câu lệnh `println`.

## 8. Các nhầm lẫn thường gặp

| Nhầm lẫn | Cách hiểu đúng |
|---|---|
| “Input chỉ là nhập từ bàn phím; output chỉ là in màn hình.” | Tệp, mạng, bộ nhớ, luồng chuẩn đều có thể đóng vai trò nguồn hoặc đích. |
| “Nguồn/đích là thuộc tính cố định của một đối tượng.” | Vai trò phụ thuộc **thao tác**: một tệp có thể là đích lúc ghi, nguồn lúc đọc lại. |
| “Một lần `read` lấy hết dữ liệu.” | `read` có thể trả về ít hơn số byte yêu cầu; phải lặp đến điểm cuối hoặc đủ độ dài mong muốn. |
| “`read` trả về `0` nghĩa là hết luồng.” | Với `InputStream.read(byte[])` và bộ đệm khác rỗng, dấu hiệu kết thúc là **`-1`**. |
| “`write(buffer)` luôn đúng sau `read(buffer)`.” | Cần ghi đúng phần hợp lệ: `write(buffer, 0, count)`. |
| “Văn bản và byte là như nhau.” | Văn bản cần bảng mã khi chuyển sang/từ byte; UTF-8 giúp kiểm soát kết quả. |
| “In ra `System.out` chắc chắn hiển thị trên màn hình.” | Luồng chuẩn có thể được chuyển hướng sang tệp hoặc nơi nhận khác. |
| “Ghi xong có thể bỏ qua việc đóng tài nguyên.” | Dùng `try-with-resources` cho luồng mở từ file/socket; tài nguyên được giải phóng đúng vòng đời. |
| “Output thành công nghĩa là đầu nhận đã sử dụng dữ liệu.” | Ghi thành công vào luồng không chứng minh đích ở tầng khác đã xử lý hoặc dữ liệu đã bền vững. |

## 9. Tự kiểm tra hiểu bài

**Tình huống A:** Chương trình đọc `orders.csv`, tính tổng tiền và ghi `total.txt`. Xác định các thành phần.

- Bước đọc: **nguồn** = `orders.csv`; **dữ liệu đầu vào** = các byte/ký tự biểu diễn đơn hàng.
- Bước tính tổng: xử lý dữ liệu trong chương trình, tự nó không phải hoạt động I/O.
- Bước ghi: **đích** = `total.txt`; **dữ liệu đầu ra** = tổng tiền sau khi được chuyển sang biểu diễn để lưu.

**Tình huống B:** Chương trình tải dữ liệu từ mạng và lưu tệp. Kết nối mạng là nguồn hay đích?

- Với bước **nhận** dữ liệu: kết nối (luồng đọc) là **nguồn**, tệp được ghi là **đích**.
- Với bước **gửi yêu cầu** trước đó: kết nối (luồng ghi) lại là **đích**. Cùng một kết nối có thể tham gia cả hai chiều.

**Tình huống C:** Tại sao phải chỉ định UTF-8 khi ghi và đọc văn bản tiếng Việt?

- Vì ký tự trong `String` cần được **mã hóa** thành byte khi ghi và **giải mã** từ byte khi đọc. Dùng cùng bảng mã ngăn lỗi do giả định khác nhau giữa các môi trường.

### Ghi nhớ

Khi gặp bất kỳ tác vụ I/O nào, hãy hỏi: **Chương trình đang đọc hay ghi? Nguồn là gì? Đích là gì? Dữ liệu là byte hay ký tự, được biểu diễn và mã hóa ra sao?** Trả lời bốn câu hỏi này giúp chọn API Java thích hợp và tìm lỗi đúng chỗ.