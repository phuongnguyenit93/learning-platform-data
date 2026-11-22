# BUFFER_UNDERFLOW, BUFFER_OVERFLOW và điều chỉnh bộ đệm trong SSLEngine

## 1. Hai trạng thái cho biết cần thay đổi điều gì?

`SSLEngine` xử lý TLS trong bộ nhớ; ứng dụng tự đọc/ghi mạng và quản lý `ByteBuffer`. Vì vậy, nhận được một trạng thái thiếu dữ liệu hoặc thiếu chỗ chứa chưa có nghĩa là kết nối TLS bị lỗi. Trước tiên phải xác định **thiếu byte ở đầu vào hay thiếu chỗ trống ở đầu ra**.

| Trạng thái | Ý nghĩa | Hành động chính |
| --- | --- | --- |
| `BUFFER_UNDERFLOW` | `unwrap()` chưa có đủ byte đầu vào để xử lý một bản ghi TLS hoàn chỉnh | Giữ phần chưa tiêu thụ, bảo đảm có chỗ nhận tiếp và đọc thêm từ mạng |
| `BUFFER_OVERFLOW` | Bộ đệm đích không đủ chỗ cho kết quả của thao tác | Tiêu thụ/gửi bớt dữ liệu đích hoặc tăng bộ đệm đích rồi thử lại |

Đây là các giá trị của `SSLEngineResult.Status`, khác với `java.nio.BufferUnderflowException` và `BufferOverflowException` do thao tác `get()`/`put()` sai giới hạn. API trả trạng thái để ứng dụng điều phối bước tiếp theo; không bắt ngoại lệ NIO để thay cho việc kiểm tra trạng thái này. Xem [SSLEngineResult.Status](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/javax/net/ssl/SSLEngineResult.Status.html).

Bài học dùng API vẫn áp dụng trên Java hiện đại, với ví dụ Java 17+. Không cần dùng giao thức SSL cũ hoặc cấu hình mật mã đã lỗi thời để quan sát cơ chế bộ đệm.

## 2. Gắn trạng thái với đúng bộ đệm

Một kết nối thường có bốn bộ đệm:

```text
Ứng dụng gửi: appOut --wrap()--> netOut --ghi mạng--> đối tác
Ứng dụng nhận: appIn <--unwrap()-- netIn <--đọc mạng-- đối tác
```

| Thao tác | Nguồn được đọc | Đích được ghi | Khi OVERFLOW cần xử lý |
| --- | --- | --- | --- |
| `wrap(appOut, netOut)` | Dữ liệu ứng dụng `appOut` | Dữ liệu TLS `netOut` | `netOut` |
| `unwrap(netIn, appIn)` | Dữ liệu TLS `netIn` | Dữ liệu ứng dụng `appIn` | `appIn` |

`BUFFER_UNDERFLOW` gắn với việc giải mã đầu vào qua `unwrap()`. Khi nguồn `appOut` hết dữ liệu, không nên mặc định gọi đó là underflow: trong quá trình bắt tay, `wrap()` còn có thể cần tạo dữ liệu TLS dù nguồn ứng dụng rỗng.

Mẹo kiểm tra: **OVERFLOW nhìn sang đích; UNDERFLOW nhìn về nguồn mạng**. Nếu tăng nhầm `appOut` khi `netOut` thiếu chỗ, lần gọi tiếp theo vẫn mắc cùng vấn đề.

## 3. Capacity lớn chưa chắc còn chỗ trống

Phải biết bộ đệm đang ở chế độ đọc hay chế độ ghi:

- Ở chế độ đọc, `remaining() = limit - position` là số byte chưa tiêu thụ.
- Ở chế độ ghi, cùng công thức đó là chỗ còn có thể ghi.
- `flip()` chuyển miền vừa ghi thành miền để đọc.
- `compact()` giữ byte chưa đọc, dồn chúng về đầu và chuẩn bị ghi tiếp phía sau.
- `clear()` mở lại toàn bộ vùng để ghi; nó không giữ ranh giới dữ liệu còn chờ xử lý. Nó cũng không xóa vật lý nội dung bộ nhớ.

Ví dụ một bộ đệm đích có capacity 16 KiB nhưng position đã là 15 KiB chỉ còn 1 KiB để nhận kết quả. So sánh yêu cầu với capacity rồi kết luận “đủ lớn” sẽ bỏ sót nguyên nhân overflow. Các thao tác và ranh giới này được mô tả trong [ByteBuffer](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/ByteBuffer.html).

Nên có quy ước rõ trong mã: `netIn` ở chế độ ghi khi đọc socket, ở chế độ đọc khi gọi `unwrap()`; `netOut` ở chế độ ghi khi gọi `wrap()`, ở chế độ đọc khi ghi socket. Chỉ chuyển chế độ tại những điểm đã xác định.

## 4. Xử lý BUFFER_UNDERFLOW trên đường nhận

### 4.1. Trường hợp thường gặp: bản ghi đến chưa đủ

TLS chạy trên TCP nhận một luồng byte. Một lần đọc mạng có thể lấy được một phần bản ghi hoặc nhiều bản ghi; ranh giới lần đọc không phải ranh giới bản ghi TLS.

Giả sử một bản ghi cần 900 byte nhưng mới nhận được 250 byte. `unwrap()` có thể báo underflow. Cấp bộ đệm 1 MiB không làm 650 byte còn lại xuất hiện. Cần giữ 250 byte, chờ mạng có dữ liệu và nối thêm đúng thứ tự.

Chu trình xử lý cho TLS trên TCP:

```text
netIn đang ở chế độ đọc, vừa được unwrap()
    ↓
Giữ miền [position, limit) bằng compact()
    ↓
Kiểm tra kích thước bộ đệm mạng theo session hiện tại
    ↓
Tăng nếu cần và còn trong ngân sách; giữ toàn bộ byte đang chờ
    ↓
Đọc thêm vào phần trống của netIn
    ↓
Nếu có byte mới: flip(), tiếp tục máy trạng thái TLS
Nếu read = 0: giữ nguyên dữ liệu, chờ sự kiện đọc
Nếu read = -1: xử lý EOF/đóng TLS, không chờ vô hạn
```

Không dùng `clear()` ở bước đầu: nó khiến lần đọc tiếp có thể ghi đè phần bản ghi còn thiếu. Không gọi lại `unwrap()` liên tục trên đúng dữ liệu chưa thay đổi: đó là vòng lặp bận, không tạo tiến triển.

### 4.2. Khi nào cần tăng netIn?

Đọc lại `engine.getSession().getPacketBufferSize()` để có kích thước bản ghi mạng được session dự kiến hỗ trợ. Nếu capacity hiện tại nhỏ hơn yêu cầu, tăng nó trước khi tiếp tục tích lũy dữ liệu. Những giá trị kích thước này phụ thuộc session; không nên coi số lấy lúc khởi tạo là bất biến. Xem [SSLSession: kích thước bộ đệm](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/javax/net/ssl/SSLSession.html#getPacketBufferSize()).

Sau `compact()`, position là số byte còn giữ. Có thể đặt:

```text
requiredCapacity = max(sessionPacketSize, sốByteĐangGiữ + chỗMuốnĐọcThêm)
```

Tính bằng kiểu đủ lớn và kiểm tra ngân sách trước khi cấp phát. Nếu bộ đệm đã đủ lớn và còn chỗ, đọc thêm thay vì nhân đôi chỉ vì underflow. Nếu nó đầy, vẫn underflow và đã đạt giới hạn, cần báo lỗi/đóng theo chính sách tài nguyên; không cấp phát vô hạn theo dữ liệu từ đối tác.

EOF cũng không được coi là “thiếu một ít byte, cứ thử lại”. Nếu luồng bị cắt giữa bản ghi, dữ liệu còn thiếu sẽ không đến. Chuyển sang quy trình đóng của ứng dụng, xử lý `closeInbound()` và ngoại lệ TLS tương ứng nếu có; không mặc định nuốt mọi `SSLException`.

## 5. Xử lý BUFFER_OVERFLOW trên đường nhận và gửi

### 5.1. unwrap() thiếu chỗ trong appIn

Có hai lựa chọn:

1. Chuyển `appIn` sang đọc, giao phần đã giải mã cho bên xử lý ứng dụng, rồi `compact()` để giữ phần chưa được tiêu thụ.
2. Nếu vẫn cần thêm chỗ, tăng bộ đệm, giữ phần đang chờ và dành thêm không gian ghi theo `getApplicationBufferSize()` hiện tại.

Nếu đích đang ở chế độ ghi và phải giữ `k = position()` byte, một phương án bảo thủ là bảo đảm capacity ít nhất `k + applicationBufferSize`. Không chỉ cấp phát đúng `applicationBufferSize` rồi quên rằng dữ liệu cũ cũng phải được giữ.

Nếu bên nhận ứng dụng đang chậm, ưu tiên giới hạn lượng dữ liệu tích lũy và tạm ngừng đọc mạng khi phù hợp. Tăng bộ đệm không thay thế được cơ chế điều tiết khi bên tiêu thụ không theo kịp (backpressure).

### 5.2. wrap() thiếu chỗ trong netOut

`netOut` có thể còn dữ liệu TLS chưa gửi hết. Trước tiên thử gửi dữ liệu đó ra socket. Với kênh không chặn, một lần `write()` có thể chỉ gửi một phần hoặc trả về 0; phải giữ phần chưa gửi.

Khi đã chuyển `netOut` về chế độ ghi bằng `compact()`, nếu cần tăng, bảo đảm có chỗ theo `getPacketBufferSize()` ngoài số byte còn giữ. Chỉ thử lại `wrap()` khi đã có thêm không gian hoặc máy trạng thái yêu cầu một thao tác khác.

Không `clear()` bộ đệm chứa dữ liệu TLS chưa gửi. Mất vài byte bản mã không chỉ làm mất một thông điệp ứng dụng; nó có thể phá khả năng xử lý phần tiếp theo của luồng TLS.

Hướng xử lý dựa trên kích thước session và việc thử lại sau khi sửa điều kiện bộ đệm là hợp đồng của [SSLEngine](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/javax/net/ssl/SSLEngine.html). Việc chọn gửi bớt, tăng bao nhiêu và đặt ngân sách bao nhiêu là thiết kế của ứng dụng.

## 6. Ví dụ chạy được: tăng bộ đệm mà không mất byte

Chương trình dưới đây kiểm tra cơ chế giữ dữ liệu khi thay bộ đệm. Các chuỗi ASCII chỉ là dữ liệu kiểm chứng việc sao chép; chương trình **không thực hiện bắt tay TLS, không giả lập kết quả SSLEngine**. Đây là phần có thể kiểm tra độc lập trước khi tích hợp vào vòng lặp TLS.

Hàm `ensureWritable()` có tiền điều kiện: bộ đệm ở chế độ ghi, miền cần giữ là `[0, position)`, limit bằng capacity, bộ đệm có thể ghi và không có bên khác đang dùng chung nó. Đầu ra tiếp tục ở chế độ ghi.

Lưu thành `BufferSizingDemo.java`:

```java
import java.nio.ByteBuffer;
import java.nio.charset.StandardCharsets;

public class BufferSizingDemo {
    // Dau vao va dau ra deu o che do ghi; chi giu mien [0, position).
    static ByteBuffer ensureWritable(ByteBuffer old, int minimumFree,
                                     int maximumCapacity) {
        if (minimumFree < 0 || maximumCapacity < old.capacity()) {
            throw new IllegalArgumentException("Invalid buffer limit");
        }
        long required = (long) old.position() + minimumFree;
        if (required > maximumCapacity) {
            throw new IllegalStateException("Buffer budget exceeded");
        }
        if (old.remaining() >= minimumFree) {
            return old;
        }
        long doubled = Math.max(1L, old.capacity()) * 2L;
        int capacity = (int) Math.max(required,
                Math.min(doubled, maximumCapacity));
        ByteBuffer next = old.isDirect()
                ? ByteBuffer.allocateDirect(capacity)
                : ByteBuffer.allocate(capacity);
        next.order(old.order());
        old.flip();
        next.put(old);
        return next;
    }

    static String takeText(ByteBuffer writing) {
        writing.flip();
        return StandardCharsets.US_ASCII.decode(writing).toString();
    }

    public static void main(String[] args) {
        ByteBuffer netIn = ByteBuffer.allocate(6);
        netIn.put("ABCDEF".getBytes(StandardCharsets.US_ASCII));
        netIn.flip();
        netIn.position(3); // Gia su ABC da duoc tieu thu.
        netIn.compact();   // Giu DEF, position = 3, limit = 6.
        netIn = ensureWritable(netIn, 5, 64);
        netIn.put("GHIJK".getBytes(StandardCharsets.US_ASCII));
        System.out.println("net capacity=" + netIn.capacity());
        System.out.println("net data=" + takeText(netIn));

        ByteBuffer appIn = ByteBuffer.allocate(4);
        appIn.put("HEAD".getBytes(StandardCharsets.US_ASCII));
        appIn = ensureWritable(appIn, 4, 64);
        appIn.put("BODY".getBytes(StandardCharsets.US_ASCII));
        System.out.println("app capacity=" + appIn.capacity());
        System.out.println("app data=" + takeText(appIn));
    }
}
```

Biên dịch và chạy với JDK 17+:

```shell
javac --release 17 -encoding UTF-8 BufferSizingDemo.java
java BufferSizingDemo
```

Cũng có thể chạy trực tiếp bằng chế độ chạy tệp nguồn:

```shell
java BufferSizingDemo.java
```

Kết quả:

```text
net capacity=12
net data=DEFGHIJK
app capacity=8
app data=HEADBODY
```

Giải thích:

- Đường nhận giả sử `ABC` đã được tiêu thụ; `compact()` giữ lại `DEF`. Tăng bộ đệm và nối `GHIJK` phải tạo `DEFGHIJK`, không chứa lại `ABC` và không mất `DEF`.
- Đường đích giữ `HEAD` rồi tạo chỗ cho `BODY`. Nếu chỉ thay bằng bộ đệm mới mà không sao chép dữ liệu đang giữ, kết quả sẽ thiếu `HEAD`.
- Phép nhân đôi dùng `long` trước khi ép về `int`; giới hạn tối đa được kiểm tra trước khi cấp phát.
- Khi thực sự tăng, hàm đọc hết bộ đệm cũ để sao chép. Sau phép gán, chỉ tiếp tục dùng bộ đệm mới; không dùng tham chiếu cũ hoặc view cũ như thể nó tự đổi theo.
- Giá trị 64 là ngân sách nhỏ phục vụ minh họa, không phải kích thước bộ đệm TLS nên dùng trong thực tế.

Khi tích hợp, với `appIn` đang ở chế độ ghi có thể dùng `ensureWritable(appIn, engine.getSession().getApplicationBufferSize(), budget)`. Với `netOut` ở chế độ ghi, dùng kích thước packet. Với `netIn` sau underflow phải `compact()` trước; tính phần cần bổ sung dựa trên capacity yêu cầu và byte đang giữ, không sao chép theo chế độ đọc một cách tùy tiện.

## 7. Thử lại phải đi cùng tiến triển và trạng thái bắt tay

Mỗi `SSLEngineResult` còn cho biết `bytesConsumed()`, `bytesProduced()` và `getHandshakeStatus()`. Số byte tiêu thụ/sinh ra giúp xác nhận tiến triển; trạng thái bắt tay quyết định cần chạy tác vụ, tạo dữ liệu gửi hay tiếp tục nhận. `Status.OK` không đồng nghĩa bắt tay đã hoàn tất. Xem [SSLEngineResult](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/javax/net/ssl/SSLEngineResult.html).

Sau mỗi lần gọi:

1. Giữ đúng vị trí do engine cập nhật; không tua lại nguồn về 0 để “thử lại”.
2. Xử lý dữ liệu đầu ra đã sinh ra nếu có, kể cả khi chưa nhận được dữ liệu ứng dụng.
3. Sửa điều kiện thiếu đầu vào/đầu ra theo status và thực hiện yêu cầu của máy trạng thái bắt tay.
4. Nếu chưa có thêm byte, chỗ trống, tác vụ hoàn tất hoặc chuyển trạng thái hữu ích, nhường vòng lặp để chờ sự kiện thay vì lặp vô hạn.

Một vòng lặp đầy đủ còn cần xử lý `NEED_TASK`, `NEED_WRAP`, `NEED_UNWRAP`, đóng kết nối và các yêu cầu khác của giao thức/provider. Không thể thay toàn bộ máy trạng thái đó bằng một vòng `while (status != OK)`. Phần tích lũy byte/EOF ở bài này dành cho TLS trên TCP; không áp dụng nguyên xi cách nối byte đó cho DTLS trên datagram.

## 8. Lỗi thường gặp và cách tự kiểm tra

| Hiện tượng | Nguyên nhân cần kiểm tra | Cách sửa |
| --- | --- | --- |
| CPU tăng cao khi mạng im lặng | Thử lại underflow mà không đọc thêm | Giữ byte và chờ khả năng đọc |
| Overflow lặp lại dù capacity lớn | Đích còn đầy dữ liệu cũ hoặc limit sai | Xem position/limit; gửi hoặc tiêu thụ bớt rồi compact |
| Dữ liệu TLS lỗi sau vài lần đọc | Clear làm mất bản ghi dở, sao chép sai miền hoặc gửi trùng byte | Ghi rõ chế độ đọc/ghi và giữ nguyên thứ tự byte |
| Bộ nhớ tăng liên tục | Tăng mỗi lần underflow hoặc ứng dụng tiêu thụ quá chậm | Giới hạn bộ đệm, dùng kích thước session và điều tiết đọc |
| Treo khi đối tác ngắt kết nối | Coi EOF là lần đọc tạm thời không có dữ liệu | Chuyển sang xử lý đóng/truncation |
| Kết quả ứng dụng bị lặp | Rewind nguồn sau khi engine đã tiêu thụ byte | Tiếp tục từ position hiện tại |

Khi chẩn đoán, ghi loại thao tác, status, handshake status, bytesConsumed/bytesProduced và position/limit/capacity trước–sau. Những số đo này thường đủ để tìm lỗi quản lý bộ đệm; tránh ghi toàn bộ dữ liệu ứng dụng hoặc bí mật phiên vào log.

Bài tập:

1. Bỏ `compact()` trong ví dụ rồi giải thích vì sao miền dữ liệu được giữ không còn đúng hợp đồng của hàm.
2. Đổi ngân sách của lần tăng `appIn` từ 64 thành 6. Dự đoán ngoại lệ trước khi chạy: hàm phải từ chối vì cần giữ 4 byte và thêm 4 byte, tổng cộng 8.
3. Thiết kế ca kiểm tra tích hợp gửi một bản ghi qua nhiều lần đọc nhỏ; xác nhận dữ liệu đến ứng dụng đúng một lần và vòng lặp nhường khi socket trả 0.
4. Thiết kế ca ghi mạng từng phần; xác nhận byte trong `netOut` chỉ bị loại sau khi socket thực sự gửi thành công.
