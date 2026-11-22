# Buffer nhận, độ dài packet và dữ liệu bị cắt cụt khi nhận UDP trong Java

> Chủ đề: UDP và datagram. Nội dung áp dụng cho Java 15 và các phiên bản Java hiện đại; ví dụ dùng các API `java.net`, `java.nio` vẫn được hỗ trợ. Trọng tâm là số byte thực sự nhận được, giới hạn của vùng đệm và cách xử lý datagram quá dài.

## 1. UDP nhận theo từng datagram, không theo dòng byte

UDP là giao thức hướng datagram: mỗi lần bên gửi gọi `send` tạo một thông điệp UDP riêng. Khi phía nhận gọi `DatagramSocket.receive(DatagramPacket)`, lời gọi lấy **một datagram** đang chờ, chép dữ liệu vào vùng đệm của packet và cung cấp địa chỉ/port nguồn.

- UDP giữ **ranh giới datagram**, khác TCP là luồng byte. Hai datagram gửi liên tiếp không được ghép thành một thông điệp trong một lần `receive`.
- UDP **không bảo đảm** datagram đến nơi, đến đúng thứ tự hay chỉ đến một lần. Ứng dụng tự thiết kế cơ chế xác nhận, số thứ tự, phát hiện trùng hoặc truyền lại nếu cần.
- **Nếu datagram dài hơn sức chứa nhận được cấu hình trong `DatagramPacket`, phần dư bị cắt bỏ.** Phần dư không nằm chờ cho lần `receive` tiếp theo; lời gọi tiếp theo nhận datagram khác nếu có.
- Một datagram có thể có payload dài **0 byte**; độ dài bằng 0 không đồng nghĩa socket bị đóng.

Ví dụ: bên gửi phát lần lượt `"cat"` (3 byte) và `"abcdefghij"` (10 byte). Bên nhận dùng packet có khả năng chứa tối đa 6 byte sẽ thấy hai lần nhận tương ứng `"cat"` và `"abcdef"`. Bốn byte `"ghij"` không được nhận tiếp ở lần thứ ba.

## 2. Phân biệt ba loại “buffer/length” dễ nhầm

| Khái niệm | Ý nghĩa thực tế | Cách xem hoặc cấu hình |
| --- | --- | --- |
| Mảng byte ứng dụng | Vùng nhớ Java lưu dữ liệu được chép vào, tính bằng byte | `byte[] buffer = new byte[2048]`, `buffer.length` |
| Độ dài của `DatagramPacket` dùng để nhận | **Trước** `receive`: số byte tối đa được phép chép vào packet, bắt đầu từ offset; **sau** `receive`: số byte thực sự đã chép | `new DatagramPacket(buffer, offset, length)`, `setLength(length)`, `getLength()` |
| Socket receive buffer của hệ điều hành | Bộ đệm/khả năng xếp hàng cho các datagram đã đến socket trước khi ứng dụng xử lý; khác với mảng byte truyền vào một lần `receive` | `setReceiveBufferSize`, `getReceiveBufferSize` hoặc socket option `SO_RCVBUF` |

Hai số dễ bị đánh đồng nhất:

```java
byte[] buffer = new byte[1024];
DatagramPacket packet = new DatagramPacket(buffer, 128);
```

Trong ví dụ trên, `buffer.length == 1024` nhưng giới hạn dữ liệu của **một lần nhận vào packet là 128 byte**. Datagram 200 byte sẽ bị cắt về tối đa 128 byte, dù mảng còn nhiều chỗ. Lý do là tham số thứ hai trong constructor của `DatagramPacket` là giới hạn byte nhận, không phải chỉ dẫn về kích thước toàn bộ mảng.

Trường hợp có offset:

```java
byte[] buffer = new byte[100];
DatagramPacket packet = new DatagramPacket(buffer, 10, 40);
```

Vùng dữ liệu hợp lệ sau khi nhận nằm trong khoảng chỉ số từ `getOffset()` (10) đến `getOffset() + getLength() - 1`; số byte tối đa ở lần nhận này là 40, **không phải** 100 hay 90. Điều kiện hợp lệ cho cấu hình là `0 <= offset`, `0 <= length` và `offset + length <= buffer.length`.

## 3. Thực sự xảy ra gì khi datagram vượt giới hạn?

Giả sử mảng đủ 8 byte, offset = 0, giới hạn nhận = 8 byte:

| Số byte bên gửi | `getLength()` sau khi nhận | Dữ liệu bên nhận còn giữ | Kết luận |
| ---: | ---: | --- | --- |
| 3 | 3 | Cả 3 byte | Không bị cắt do buffer |
| 8 | 8 | Cả 8 byte | Vừa khít |
| 12 | 8 | 8 byte đầu | 4 byte cuối bị loại bỏ |

Điểm quan trọng: **giá trị `getLength() == 8` ở cả hai trường hợp cuối.** API `DatagramPacket` không cung cấp cờ báo “truncated” hoặc độ dài gốc của datagram bị cắt. Chỉ nhìn kết quả nhận 8 byte **không thể khẳng định** gói vừa khít hay đã bị cắt.

Không gọi `receive` lần nữa để “nhặt phần còn lại”; UDP không cung cấp cách đọc tiếp các byte đã bị bỏ. Nếu ứng dụng cần thông điệp lớn, hãy tăng giới hạn nhận phù hợp với *giao thức ứng dụng*, hoặc thiết kế cơ chế phân mảnh/ghép thông điệp và kiểm tra tính đầy đủ ở tầng ứng dụng.

## 4. Ví dụ Java chạy được: nhận ngắn, dùng lại packet và cắt cụt

Chương trình tự gửi ba datagram qua loopback trên một máy nên không cần server bên ngoài. Buffer của bên nhận chỉ có 8 byte. Phương thức `receiveAndPrint` khôi phục giới hạn nhận trước **mỗi** lần dùng lại `DatagramPacket`.

Tạo tệp `UdpBufferDemo.java`:

```java
import java.io.IOException;
import java.net.DatagramPacket;
import java.net.DatagramSocket;
import java.net.InetAddress;
import java.nio.charset.StandardCharsets;

public class UdpBufferDemo {
    private static void send(
            DatagramSocket socket, InetAddress host, int port, String text)
            throws IOException {
        byte[] data = text.getBytes(StandardCharsets.UTF_8);
        socket.send(new DatagramPacket(data, data.length, host, port));
    }

    private static void receiveAndPrint(
            DatagramSocket socket, DatagramPacket packet, String label)
            throws IOException {
        // Lần receive trước đã thay đổi packet.length.
        // Reset về sức chứa còn lại tính từ offset.
        packet.setLength(packet.getData().length - packet.getOffset());
        socket.receive(packet);

        String text = new String(
                packet.getData(),
                packet.getOffset(),
                packet.getLength(),
                StandardCharsets.UTF_8);

        System.out.println(
                label + ": bytes=" + packet.getLength() + ", text=" + text);
    }

    public static void main(String[] args) throws Exception {
        InetAddress loopback = InetAddress.getLoopbackAddress();

        try (DatagramSocket receiver = new DatagramSocket(0, loopback);
             DatagramSocket sender = new DatagramSocket()) {
            receiver.setSoTimeout(3000);

            byte[] buffer = new byte[8];
            DatagramPacket packet =
                    new DatagramPacket(buffer, buffer.length);
            int port = receiver.getLocalPort();

            send(sender, loopback, port, "OK");
            receiveAndPrint(receiver, packet, "1");

            send(sender, loopback, port, "ABCDEFG");
            receiveAndPrint(receiver, packet, "2");

            send(sender, loopback, port, "ABCDEFGHIJKL");
            receiveAndPrint(receiver, packet, "3");
        }
    }
}
```

Biên dịch và chạy với JDK 17+ (cũng tương thích cú pháp Java 15):

```bash
javac UdpBufferDemo.java
java UdpBufferDemo
```

Kết quả mong đợi khi datagram loopback đến bình thường:

```text
1: bytes=2, text=OK
2: bytes=7, text=ABCDEFG
3: bytes=8, text=ABCDEFGH
```

Giải thích:

1. `"OK"` chiếm 2 byte; `getLength() == 2` mặc dù `buffer.length == 8`.
2. Trước lần nhận thứ hai, `setLength(8)` mở lại toàn bộ sức chứa. Vì vậy 7 byte `"ABCDEFG"` được giữ nguyên. Nếu quên reset, packet có thể tiếp tục giới hạn ở 2 byte từ lần trước và làm hỏng datagram dài hơn.
3. Datagram thứ ba chứa 12 byte ASCII nhưng chỉ 8 byte đầu được chép; bốn byte `"IJKL"` bị bỏ. Bên nhận chỉ thấy độ dài 8, không thể tự biết tổng gói gốc là 12 chỉ từ API nhận.

`setSoTimeout(3000)` giúp tránh chờ vô hạn khi không nhận được gói; hết hạn sẽ ném `SocketTimeoutException`. Đây là timeout, không phải tín hiệu cho biết có cắt cụt. `try-with-resources` tự đóng cả hai socket khi rời khối.

## 5. Quy tắc xử lý đúng số byte nhận được

Đọc dữ liệu bằng đúng **offset và length** do packet trả về:

```java
String text = new String(
        packet.getData(),
        packet.getOffset(),
        packet.getLength(),
        StandardCharsets.UTF_8);
```

Đoạn này chỉ là phần trích từ chương trình có sẵn biến `packet`, không phải chương trình độc lập. Dạng `new String(packet.getData(), UTF_8)` thường **sai** nếu mảng lớn hơn datagram: nó giải mã cả byte chưa dùng hoặc còn sót từ lần nhận trước. `getData().length` là chiều dài mảng, **không phải** số byte vừa nhận.

Khi dữ liệu được xử lý bất đồng bộ hoặc bạn sẽ gọi `receive` tiếp trên cùng một mảng, hãy sao chép phần byte hợp lệ trước khi giao cho phần khác của chương trình:

```java
byte[] stableCopy = java.util.Arrays.copyOfRange(
        packet.getData(),
        packet.getOffset(),
        packet.getOffset() + packet.getLength());
```

Nếu không sao chép, dữ liệu của lần nhận tiếp theo có thể ghi đè mảng mà luồng xử lý cũ vẫn tham chiếu.

Với văn bản UTF-8, giới hạn nhận tính bằng **byte**, không phải số ký tự Java. Một ký tự Unicode có thể chiếm nhiều byte; cắt giữa chuỗi byte của ký tự có thể tạo văn bản giải mã lỗi hoặc ký tự thay thế. Với nội dung nhị phân, hãy kiểm tra định dạng và độ dài trước khi parse, không tự động chuyển thành `String`.

## 6. Tái sử dụng DatagramPacket: nhớ khôi phục length

`DatagramPacket` vừa chứa dữ liệu vừa giữ giới hạn nhận. `receive` cập nhật `length` thành số byte đã chép. Khi dùng lại cùng packet cho datagram kế tiếp, gọi một trong các cách sau **trước** `receive`:

- Với offset = 0 và muốn dùng cả mảng: `packet.setLength(packet.getData().length)`.
- Với offset khác 0: `packet.setLength(packet.getData().length - packet.getOffset())`, hoặc đặt giới hạn cố định đã quy định bởi giao thức.
- Khi muốn thay mảng/offset/giới hạn cùng lúc: `packet.setData(newBuffer, offset, allowedLength)`; hoặc tạo `DatagramPacket` mới cho mỗi lượt.

Cần tách hai chiều sử dụng: trước khi **gửi**, `length` xác định số byte được đưa lên mạng; sau khi **nhận**, `getLength()` phản ánh số byte đã được chép vào buffer. Nếu dùng cùng một đối tượng cho cả gửi và nhận, quản lý chiều dữ liệu và độ dài càng phải rõ ràng.

## 7. Nhận biết datagram bị cắt bằng cách nào?

Với `DatagramSocket.receive` và `DatagramPacket` thông thường, không có phép thử tuyệt đối dựa trên `getLength()`. Quy tắc:

- `getLength() < giới hạn nhận đã đặt`: datagram này không bị cắt vì thiếu chỗ trong `DatagramPacket` ở lần nhận đó.
- `getLength() == giới hạn nhận đã đặt`: có thể gói **vừa khít**, có thể **bị cắt**. Chỉ có giá trị bằng giới hạn thì chưa đủ kết luận.
- `getLength() > giới hạn nhận đã đặt`: không phải kết quả hợp lệ của lần nhận đó.

Cách thiết kế đáng tin hơn là quy định **giới hạn payload lớn nhất** và **định dạng thông điệp** ở tầng ứng dụng:

1. Ví dụ giao thức chỉ cho phép payload tối đa 1024 byte: cấp đủ không gian cho toàn bộ header và payload hợp lệ; từ chối thông điệp vượt giới hạn theo quy định.
2. Có thể đặt một trường độ dài payload trong header (ví dụ số nguyên không dấu 2 byte theo thứ tự mạng), rồi kiểm tra số byte thực nhận khớp `headerLength + declaredPayloadLength`. Nếu ít hơn, báo thông điệp thiếu dữ liệu và loại bỏ. Header cũng phải được kiểm tra đủ byte trước khi đọc.
3. Với thông điệp có số thứ tự hoặc checksum/MAC do ứng dụng định nghĩa, kiểm tra theo đặc tả để phát hiện thiếu, trùng, sai dữ liệu; checksum/MAC chỉ có ý nghĩa khi được thiết kế và xác thực đúng.
4. Nếu gói vượt kích thước tối đa đã thống nhất, không suy luận hay tự ghép với datagram kế tiếp. Bên gửi phải giảm kích thước hoặc dùng cơ chế chia/ghép thông điệp có định danh, thứ tự, giới hạn bộ nhớ và timeout.

Trường độ dài do bên gửi khai báo giúp phát hiện thiếu byte khi được khai báo **đúng và còn đọc được**, nhưng không tự tạo bảo đảm về mạng, cũng không ngăn một bên gửi độc hại khai báo sai. Luôn giới hạn kích thước trước khi cấp phát.

## 8. Không nhầm giới hạn ứng dụng với SO_RCVBUF

`DatagramSocket.setReceiveBufferSize(int)` điều chỉnh gợi ý `SO_RCVBUF` cho bộ đệm socket của hệ điều hành. Nó có thể ảnh hưởng khả năng xếp hàng khi nhiều datagram đến nhanh; giá trị thực tế phụ thuộc nền tảng và có thể đọc bằng `getReceiveBufferSize()`. Nó **không** thay thế `byte[]` hoặc `DatagramPacket.setLength()`.

Ví dụ:

- Hàng đợi socket đủ lớn nhưng `DatagramPacket` chỉ cho nhận 128 byte: datagram 500 byte vẫn bị cắt khi chép vào packet.
- Mảng nhận đủ lớn nhưng ứng dụng xử lý chậm, hàng đợi socket đầy: có thể **mất nguyên datagram** trước khi Java gọi `receive`. Tăng mảng ứng dụng không tự giải quyết nghẽn hàng đợi.

Tài liệu Java cũng nêu `SO_RCVBUF` là gợi ý; mức tối đa datagram nhận được có thể phụ thuộc cách triển khai. Vì vậy không dựa vào một giá trị buffer OS để khẳng định tất cả datagram lớn đều sẽ được nhận đầy đủ.

## 9. Với DatagramChannel và ByteBuffer thì sao?

`DatagramChannel.receive(ByteBuffer)` là API NIO hiện hành. Nó chép **một datagram** vào khoảng trống còn lại của `ByteBuffer`, tính từ `position()` đến `limit()`. Nếu `remaining()` nhỏ hơn datagram, **phần dư bị bỏ âm thầm**, tương tự lỗi thiếu sức chứa ở `DatagramPacket`.

Đoạn minh họa dưới đây giả định `channel` là `DatagramChannel` đã mở và bind; đây là trích đoạn trong vòng lặp nhận, không phải chương trình độc lập:

```java
java.nio.ByteBuffer dst = java.nio.ByteBuffer.allocate(2048);

// Mỗi vòng lặp:
dst.clear(); // position = 0, limit = capacity
java.net.SocketAddress from = channel.receive(dst);
if (from != null) { // non-blocking mode có thể trả null
    dst.flip();      // position = 0, limit = số byte đã chép
    int receivedBytes = dst.remaining();
    // Chỉ xử lý receivedBytes byte hiện có trong dst.
}
```

Đừng quên `clear()` trước lần nhận tiếp theo: nếu còn ít `remaining()`, datagram mới dễ bị cắt. `flip()` giúp đọc đúng lượng byte vừa ghi. Nếu số byte nhận **bằng** dung lượng còn trống ban đầu, vẫn không thể kết luận gói vừa khít hay đã bị cắt chỉ từ con số này.

## 10. Các lỗi phổ biến và cách khắc phục

| Lỗi | Hậu quả | Cách làm đúng |
| --- | --- | --- |
| Dùng `buffer.length` thay `packet.getLength()` để parse | Đọc cả byte thừa/cũ | Dùng `getOffset()` và `getLength()` sau mỗi lần nhận |
| Tạo packet với `length` quá nhỏ dù mảng lớn | Datagram bị cắt không cần thiết | Đặt giới hạn phù hợp với kích thước thông điệp hợp lệ |
| Dùng lại packet mà không reset `length` | Datagram sau bị giới hạn bởi độ dài datagram trước | Gọi `setLength(...)` trước mỗi lần nhận lại |
| Cho rằng `getLength() == capacity` nghĩa là chắc chắn bị cắt | Báo lỗi giả cho gói vừa khít | Chỉ coi là dấu hiệu cần kiểm tra bằng giao thức |
| Gọi `receive` lần nữa để lấy “phần còn lại” | Nhận nhầm datagram tiếp theo | Không dựa vào UDP như luồng liên tục |
| Tăng `SO_RCVBUF` để sửa buffer ứng dụng quá nhỏ | Vẫn bị cắt khi chép vào packet | Phân biệt hàng đợi OS và sức chứa của packet |
| Giải mã cả mảng thành UTF-8 | Byte đệm và ký tự bị cắt gây dữ liệu sai | Chỉ giải mã đoạn hợp lệ; thiết kế giới hạn theo byte |
| Giữ tham chiếu mảng dùng chung trong xử lý bất đồng bộ | Nội dung thay đổi sau lần nhận kế | Sao chép đoạn byte hợp lệ hoặc quản lý vòng đời buffer |

## 11. Nguyên tắc thiết kế khi đưa vào ứng dụng thật

- Xác định độ dài thông điệp UDP tối đa theo yêu cầu giao thức trước khi cấp buffer; giới hạn đầu vào để tránh cấp phát không giới hạn. Nên tránh datagram lớn dễ gây IP fragmentation và độ tin cậy kém trên đường truyền có MTU khác nhau.
- Nếu payload có thể lớn hoặc cần truyền đáng tin cậy/thứ tự nghiêm ngặt, cân nhắc TCP hay giao thức phù hợp; nếu vẫn dùng UDP, ứng dụng phải thiết kế phân mảnh, xác nhận, timeout, xử lý mất/trùng/sai thứ tự.
- Đo đạc riêng số datagram nhận, số thông điệp bị từ chối do giới hạn, số timeout và số thứ tự bị thiếu (nếu protocol có sequence number). Không gọi tất cả hiện tượng đó là “truncation”.
- Kiểm tra địa chỉ nguồn, tính hợp lệ của header, độ dài và ranh giới dữ liệu **trước** khi parse sâu. Nhớ rằng UDP bản thân không xác thực bên gửi.
- Thử nghiệm với datagram ngắn hơn, đúng bằng và lớn hơn giới hạn; với datagram 0 byte; với offset khác 0; và khi liên tục tái sử dụng một packet.

## 12. Tự kiểm tra

**Câu 1.** `byte[256]` và `new DatagramPacket(buffer, 64)`: datagram 80 byte được nhận bao nhiêu byte?  
**Đáp án:** Tối đa 64 byte; phần dư bị bỏ, mặc dù mảng có 256 byte.

**Câu 2.** Buffer cho phép 512 byte, `getLength() == 512`. Có chắc bị cắt không?  
**Đáp án:** Không. Gói có thể dài đúng 512 byte hoặc dài hơn và bị cắt. Cần quy ước kích thước/độ dài ở tầng ứng dụng để kiểm tra.

**Câu 3.** Nhận gói 4 byte, rồi dùng lại cùng `DatagramPacket` nhận gói 200 byte vào mảng 1024 byte. Quên thao tác nào?  
**Đáp án:** Khôi phục `setLength(...)` trước lần nhận thứ hai; nếu giữ giới hạn 4 byte của lần trước, gói sau có thể bị cắt về 4 byte.

**Câu 4.** Tăng `setReceiveBufferSize` có bảo đảm datagram 10 KB không bị cắt khi packet Java có giới hạn 1 KB không?  
**Đáp án:** Không. Đó là hai lớp bộ đệm khác nhau; packet Java vẫn chỉ chứa tối đa 1 KB.

## Tài liệu API chính thức

- [DatagramSocket — Java SE 25](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/net/DatagramSocket.html): hành vi `receive` khi datagram vượt `packet.length`, timeout và `SO_RCVBUF`.
- [DatagramPacket — Java SE 25](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/net/DatagramPacket.html): `getData`, `getOffset`, `getLength`, `setLength` và các constructor nhận buffer.
- [DatagramChannel — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/nio/channels/DatagramChannel.html): `receive(ByteBuffer)` và việc bỏ phần dữ liệu vượt `ByteBuffer.remaining()`.
