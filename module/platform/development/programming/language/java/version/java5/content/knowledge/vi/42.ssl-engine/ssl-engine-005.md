# Các trạng thái xử lý và trạng thái bắt tay của SSLEngine

## 1. Hai câu hỏi khác nhau sau mỗi lần xử lý

`SSLEngine` xử lý TLS nhưng không tự đọc hay ghi socket. Chương trình cung cấp các bộ đệm, gọi `wrap()` để tạo dữ liệu gửi đi hoặc `unwrap()` để xử lý dữ liệu nhận được, rồi tự vận chuyển các byte qua mạng. Vì vậy, một lời gọi thành công chưa có nghĩa là bắt tay đã xong hoặc dữ liệu đã tới máy bên kia.

Cần phân biệt hai câu hỏi:

- **Trạng thái xử lý (`Status`):** lần `wrap()/unwrap()` vừa rồi gặp điều kiện gì?
- **Trạng thái bắt tay (`HandshakeStatus`):** muốn tiến tiếp thì bộ máy TLS cần hành động nào?

Ví dụ, kết quả `OK + NEED_WRAP` có nghĩa lần xử lý vừa rồi hoàn tất bình thường nhưng phía này còn phải tạo dữ liệu TLS để gửi. Nếu chỉ kiểm tra `OK` rồi chuyển sang chờ đọc mạng, hai đầu có thể cùng chờ nhau.

Bài này học API vẫn sử dụng trên Java hiện đại. `SSLEngine` xuất hiện từ Java 5, nhưng không vì thế mà cần dùng giao thức hay cấu hình bảo mật của thời Java 5. Các ví dụ dùng Java 17+, không bật lại SSL hoặc các phiên bản TLS đã bị loại khỏi cấu hình an toàn.

Mô hình phân chia giữa xử lý TLS và vận chuyển được mô tả trong [tài liệu SSLEngine](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/javax/net/ssl/SSLEngine.html).

## 2. Đọc đủ bốn thông tin của SSLEngineResult

Mỗi lần `wrap()` hoặc `unwrap()` trả về một `SSLEngineResult`:

```java
// Đoạn minh họa: engine và các ByteBuffer do bộ điều khiển kết nối quản lý.
SSLEngineResult result = engine.unwrap(netIn, appIn);

SSLEngineResult.Status status = result.getStatus();
SSLEngineResult.HandshakeStatus handshake = result.getHandshakeStatus();
int consumed = result.bytesConsumed();
int produced = result.bytesProduced();
```

Ý nghĩa của bộ đệm phụ thuộc chiều xử lý:

| Lời gọi | Nguồn được tiêu thụ | Đích nhận byte mới |
| --- | --- | --- |
| `wrap(appOut, netOut)` | Dữ liệu ứng dụng cần gửi | Dữ liệu TLS phải gửi qua mạng |
| `unwrap(netIn, appIn)` | Dữ liệu TLS đã nhận | Dữ liệu ứng dụng đã được giải mã |

`bytesConsumed()` và `bytesProduced()` cho biết số byte của **lời gọi đó**. Trong bắt tay, một lần xử lý có thể không tạo byte ứng dụng; điều này không tự nó là lỗi. Ngược lại, byte TLS đã tạo vẫn cần được gửi dù không có byte ứng dụng nào bị tiêu thụ.

Các số đếm này giúp quan sát tiến triển; không dùng chúng để đoán rằng một bản tin ứng dụng đã hoàn chỉnh. Việc phân tách bản tin thuộc giao thức ứng dụng.

Hợp đồng các trường kết quả nằm trong [SSLEngineResult API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/javax/net/ssl/SSLEngineResult.html).

## 3. Bốn trạng thái xử lý

Theo [Status API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/javax/net/ssl/SSLEngineResult.Status.html), `Status` không biểu diễn tiến độ bắt tay.

| Status | Ý nghĩa trực tiếp | Hướng xử lý |
| --- | --- | --- |
| `OK` | Lời gọi hoàn tất bình thường | Xem tiếp trạng thái bắt tay, các byte được tạo và công việc còn lại |
| `BUFFER_OVERFLOW` | Bộ đệm đích thiếu chỗ | Giải phóng chỗ ở đích hoặc tăng dung lượng; sau đó mới thử lại |
| `BUFFER_UNDERFLOW` | `unwrap()` thiếu byte nguồn để xử lý một gói đầy đủ | Giữ phần dữ liệu chưa tiêu thụ, bổ sung dữ liệu mạng; kiểm tra dung lượng nguồn |
| `CLOSED` | Chiều xử lý này vừa đóng hoặc đã đóng | Chuyển sang xử lý đóng kết nối và bảo toàn mọi dữ liệu đã tạo |

Hai trạng thái bộ đệm là kết quả trả về của engine, khác với ngoại lệ `BufferOverflowException` hoặc `BufferUnderflowException` khi chương trình tự thao tác `ByteBuffer` sai.

### 3.1. BUFFER_OVERFLOW: đích nào đang thiếu chỗ?

Với `wrap()`, đích là `netOut`. Với `unwrap()`, đích là `appIn`. Tăng nhầm `netIn` khi `unwrap()` báo overflow sẽ không sửa được nguyên nhân.

Ví dụ tự xây dựng: `appIn` có dung lượng đủ lớn nhưng vẫn chứa dữ liệu ứng dụng chưa được bên nhận xử lý. Việc cấp thêm bộ nhớ liên tục có thể che giấu việc bên nhận tiêu thụ quá chậm. Trước hết cần chuyển dữ liệu đó cho ứng dụng hoặc áp dụng cơ chế điều tiết nhận dữ liệu.

### 3.2. BUFFER_UNDERFLOW: dữ liệu chưa đủ, không phải mất kết nối

TCP có thể chia một bản ghi TLS thành nhiều lần đọc. Đọc được 100 byte không bảo đảm đã có một bản ghi hoàn chỉnh.

Không gọi lại `unwrap()` vô hạn trên chính 100 byte đó. Cần giữ lại phần chưa tiêu thụ rồi đọc thêm. Nếu bộ đệm đã đầy nhưng vẫn không đủ chỗ cho bản ghi, cần tăng dung lượng theo thông tin phiên TLS.

### 3.3. Kích thước và chế độ bộ đệm

`engine.getSession().getPacketBufferSize()` là gợi ý kích thước cho dữ liệu TLS; `getApplicationBufferSize()` dành cho dữ liệu ứng dụng. Hai giá trị không có cùng vai trò và cần được đọc lại khi xử lý thiếu chỗ, thay vì cố định một hằng số cho mọi kết nối. Xem [SSLSession API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/javax/net/ssl/SSLSession.html).

Khi mở rộng bộ đệm, phải giữ dữ liệu còn cần và đặt đúng `position/limit`. Với `netIn` đang ở chế độ đọc sau `unwrap()`, `compact()` giữ các byte chưa đọc rồi chuyển sang chế độ ghi để nhận thêm; `clear()` đặt lại các mốc và khiến chương trình bỏ qua phần dữ liệu đang chờ. Khi chuẩn bị đọc tiếp bằng engine, dùng `flip()` theo quy ước quản lý bộ đệm của chương trình. Các thao tác này được định nghĩa trong [ByteBuffer API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/nio/ByteBuffer.html).

## 4. Sáu trạng thái bắt tay trong Java hiện đại

| HandshakeStatus | Bộ điều khiển cần làm gì? |
| --- | --- |
| `NEED_WRAP` | Gọi `wrap()` và đưa các byte TLS tạo ra vào hàng đợi gửi |
| `NEED_UNWRAP` | Xử lý dữ liệu nhận bằng `unwrap()`; nếu thiếu thì chờ thêm dữ liệu mạng |
| `NEED_TASK` | Lấy và thực thi các tác vụ được giao trước khi tiếp tục |
| `FINISHED` | Ghi nhận sự kiện lời gọi vừa hoàn tất bắt tay |
| `NOT_HANDSHAKING` | Hiện tại không có bắt tay đang diễn ra |
| `NEED_UNWRAP_AGAIN` | Với DTLS, gọi `unwrap()` để xử lý tiếp dữ liệu đã nhận, không đợi một gói mới |

`NEED_UNWRAP_AGAIN` được bổ sung từ Java 9 và chỉ áp dụng cho DTLS. Bài học không giả định enum của Java 5 vẫn là danh sách đầy đủ khi viết mã cho JDK hiện đại. Định nghĩa và giới hạn của sáu giá trị nằm trong [HandshakeStatus API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/javax/net/ssl/SSLEngineResult.HandshakeStatus.html).

### 4.1. NEED_WRAP không đồng nghĩa có dữ liệu ứng dụng để gửi

Trong bắt tay, phía này có thể cần gửi bản tin TLS dù hàng đợi ứng dụng rỗng. Bộ điều khiển có thể gọi `wrap()` với bộ đệm nguồn rỗng và bộ đệm đích đủ chỗ. Chờ đến lúc người dùng gửi dữ liệu ứng dụng mới gọi `wrap()` sẽ khiến bắt tay đứng lại.

`wrap()` chỉ tạo byte trong bộ nhớ. Sau đó, việc ghi socket có thể chỉ gửi được một phần. Chương trình phải giữ các byte chưa gửi và tiếp tục khi có thể ghi; không ghi đè `netOut` khi dữ liệu cũ còn chờ.

### 4.2. NEED_UNWRAP là yêu cầu xử lý đầu vào

Nếu `netIn` đã có dữ liệu, thử xử lý dữ liệu đang có. Khi gặp underflow, giữ phần dư và đợi đọc thêm. Không mặc định phải thực hiện một lần đọc mạng mới trước mọi `unwrap()`: một lần đọc trước đó có thể đã chứa nhiều bản ghi.

### 4.3. NEED_TASK yêu cầu hoàn thành công việc được giao

Một số công việc như kiểm tra chứng chỉ có thể tốn thời gian. Engine cung cấp các `Runnable` qua `getDelegatedTask()`. Mô hình đơn giản lấy đến khi phương thức trả `null`, chạy các tác vụ rồi kiểm tra lại trạng thái.

```java
// Đoạn minh họa cho môi trường cho phép chạy đồng bộ.
Runnable task;
while ((task = engine.getDelegatedTask()) != null) {
    task.run();
}
SSLEngineResult.HandshakeStatus next = engine.getHandshakeStatus();
```

Trong hệ thống dùng vòng lặp sự kiện, không mặc định chạy mọi tác vụ ngay trên luồng phục vụ I/O. Có thể chuyển tác vụ sang bộ thực thi phù hợp, nhưng bộ điều khiển phải đợi chúng hoàn tất, rồi tiếp tục xử lý engine theo cơ chế đồng bộ đã thiết kế. Chỉ đưa tác vụ vào hàng đợi chưa có nghĩa là kết quả đã sẵn sàng.

### 4.4. FINISHED là một sự kiện, không phải trạng thái để chờ bằng polling

Điểm cần nhớ:

```java
// result: kết quả của lời gọi wrap()/unwrap() vừa thực hiện.
if (result.getHandshakeStatus()
        == SSLEngineResult.HandshakeStatus.FINISHED) {
    // Ghi nhận bắt tay vừa hoàn tất.
}
```

`engine.getHandshakeStatus()` không trả `FINISHED`. Vì vậy, vòng lặp chờ `engine.getHandshakeStatus() == FINISHED` sẽ sai. Cần quan sát kết quả của chính lời gọi hoàn tất bắt tay.

`NOT_HANDSHAKING` cũng không tự chứng minh kết nối đã bắt tay thành công: engine mới tạo, chưa bắt đầu bắt tay cũng có thể không đang bắt tay. Bộ điều khiển nên lưu giai đoạn kết nối hoặc cờ đã quan sát hoàn tất bắt tay ban đầu.

## 5. Ghép hai loại trạng thái để quyết định đúng

Ví dụ dưới đây là các tình huống suy luận để thiết kế bộ điều khiển, không phải chuỗi log bắt buộc của mọi nhà cung cấp JSSE:

| Kết quả | Cách đọc và hành động |
| --- | --- |
| `OK + NEED_WRAP` | Lời gọi bình thường; tạo và gửi dữ liệu TLS tiếp theo |
| `BUFFER_UNDERFLOW + NEED_UNWRAP` | Chưa đủ đầu vào; bảo toàn phần dư và đợi thêm |
| `BUFFER_OVERFLOW + NEED_UNWRAP` | Cần xử lý đầu vào nhưng đích thiếu chỗ; sửa đích trước khi thử lại |
| `OK + FINISHED` | Ghi nhận hoàn tất; vẫn giao nhận mọi byte mà lời gọi vừa tạo |
| `OK + NOT_HANDSHAKING` | Xem giai đoạn đã lưu, dữ liệu ứng dụng và hàng đợi gửi |
| `CLOSED` | Kiểm tra riêng chiều vào, chiều ra và phần TLS còn chờ gửi |

Không viết hai nhánh độc lập cùng ra lệnh mâu thuẫn, chẳng hạn vừa lên lịch chờ đọc vì underflow vừa lập tức gọi lại trên bộ đệm chưa đổi. Điều kiện bộ đệm quyết định có thể gọi lại ngay hay phải chờ; trạng thái bắt tay quyết định công việc giao thức cần tiến tới.

Một lượt điều khiển thực tế có thể được tổ chức như sau:

1. Nhận kết quả và lưu số byte tiêu thụ/tạo ra.
2. Bảo toàn mọi đầu ra; đưa dữ liệu tới ứng dụng hoặc hàng đợi mạng đúng chiều.
3. Sửa điều kiện bộ đệm hoặc xử lý đóng nếu cần.
4. Ghi nhận `FINISHED` từ kết quả; hoàn thành tác vụ được giao nếu có.
5. Chỉ gọi tiếp khi có điều kiện tiến triển, hoặc đăng ký chờ sự kiện phù hợp.

Đây là thiết kế suy ra từ hợp đồng API, không phải một thuật toán TLS riêng. Không tự thực hiện mật mã hay xác thực chứng chỉ thay JSSE.

## 6. Ví dụ Java 17+: đọc kết quả và chọn việc tiếp theo

Chương trình sau **tạo kết quả giả lập để học cách đọc API**. Nó không tạo kết nối TLS và không chứng minh một lần bắt tay thật đã thành công. Cách này giúp tách việc phân loại trạng thái khỏi chứng chỉ, socket và nhà cung cấp TLS.

Lưu thành `ResultStatesDemo.java`:

```java
import javax.net.ssl.SSLEngineResult;
import javax.net.ssl.SSLEngineResult.HandshakeStatus;
import javax.net.ssl.SSLEngineResult.Status;

public class ResultStatesDemo {
    private static String action(SSLEngineResult result) {
        return switch (result.getStatus()) {
            case BUFFER_OVERFLOW -> "MAKE_DESTINATION_SPACE";
            case BUFFER_UNDERFLOW -> "KEEP_INPUT_AND_WAIT_FOR_MORE";
            case CLOSED -> "HANDLE_DIRECTIONAL_CLOSE";
            case OK -> switch (result.getHandshakeStatus()) {
                case NEED_TASK -> "COMPLETE_DELEGATED_TASKS";
                case NEED_WRAP -> "WRAP_AND_QUEUE_NETWORK_OUTPUT";
                case NEED_UNWRAP -> "UNWRAP_AVAILABLE_INPUT";
                case NEED_UNWRAP_AGAIN -> "UNWRAP_DTLS_BUFFERED_INPUT";
                case FINISHED -> "RECORD_HANDSHAKE_COMPLETION";
                case NOT_HANDSHAKING -> "CHECK_CONNECTION_PHASE";
            };
        };
    }

    private static void show(SSLEngineResult result) {
        System.out.printf("%s/%s consumed=%d produced=%d => %s%n",
                result.getStatus(), result.getHandshakeStatus(),
                result.bytesConsumed(), result.bytesProduced(),
                action(result));
    }

    public static void main(String[] args) {
        show(new SSLEngineResult(Status.OK,
                HandshakeStatus.NEED_WRAP, 0, 0));
        show(new SSLEngineResult(Status.BUFFER_UNDERFLOW,
                HandshakeStatus.NEED_UNWRAP, 0, 0));
        show(new SSLEngineResult(Status.OK,
                HandshakeStatus.FINISHED, 120, 0));
        show(new SSLEngineResult(Status.CLOSED,
                HandshakeStatus.NOT_HANDSHAKING, 0, 0));
    }
}
```

Biên dịch và chạy bằng JDK 17+:

```shell
javac ResultStatesDemo.java
java ResultStatesDemo
```

Stdout:

```text
OK/NEED_WRAP consumed=0 produced=0 => WRAP_AND_QUEUE_NETWORK_OUTPUT
BUFFER_UNDERFLOW/NEED_UNWRAP consumed=0 produced=0 => KEEP_INPUT_AND_WAIT_FOR_MORE
OK/FINISHED consumed=120 produced=0 => RECORD_HANDSHAKE_COMPLETION
CLOSED/NOT_HANDSHAKING consumed=0 produced=0 => HANDLE_DIRECTIONAL_CLOSE
```

Các số byte trong ví dụ do chương trình tự đặt. Không dùng chúng làm kích thước bản tin TLS chuẩn. Hàm `action()` chỉ gợi ý **việc ưu tiên** sau một kết quả; bộ điều khiển đầy đủ vẫn cần bảo toàn đầu ra, lưu giai đoạn và quản lý I/O. Đặc biệt, khi trạng thái khác `OK`, không được vì chọn hành động ưu tiên mà quên quan sát `FINISHED` hoặc dữ liệu được tạo trong kết quả thực tế.

## 7. Phát hiện không tiến triển và đóng kết nối

### Không quay vòng khi chưa có điều kiện mới

Nếu một lời gọi tiêu thụ 0 byte, tạo 0 byte và không đổi trạng thái, gọi lại với mọi điều kiện giữ nguyên thường không giúp gì. Trước khi lặp, cần xác định ít nhất một thay đổi hữu ích: thêm đầu vào, thêm chỗ ở đích, hoàn thành tác vụ, gửi bớt đầu ra hoặc chuyển trạng thái.

Tuy nhiên, không kết luận mọi kết quả `0/0` đều là lỗi. Ví dụ `OK + NEED_TASK` có thể cần thực thi tác vụ; chờ đọc socket sẽ bỏ qua đúng công việc cần làm. Nên ghi log trạng thái cũ/mới và các mốc bộ đệm để phân biệt chờ hợp lệ với vòng lặp bận.

### CLOSED không thay thế quản lý hai chiều

Chiều vào và chiều ra có thể kết thúc khác thời điểm. Dùng `isInboundDone()` và `isOutboundDone()` để theo dõi riêng. Khi yêu cầu đóng chiều ra bằng `closeOutbound()`, chương trình còn phải cho engine tạo dữ liệu đóng và gửi hết dữ liệu đó; không đóng socket ngay chỉ vì đã gọi phương thức này.

EOF ở tầng vận chuyển không tương đương chắc chắn đã nhận thông báo đóng TLS hợp lệ. Cần xử lý `closeInbound()` và ngoại lệ theo chính sách kết nối; không biến một đường truyền bị cắt thành thành công âm thầm.

`SSLException` không phải giá trị enum thứ năm. Lời gọi có thể ném ngoại lệ thay vì trả kết quả để tiếp tục thông thường. Trường hợp lỗi xác thực không được giải quyết bằng cách bỏ qua kiểm tra chứng chỉ. Các trách nhiệm xử lý I/O và đóng của ứng dụng được trình bày trong [hướng dẫn JSSE](https://docs.oracle.com/en/java/javase/25/security/java-secure-socket-extension-jsse-reference-guide.html).

## 8. Tự kiểm tra

1. `wrap()` trả `OK` có chứng minh dữ liệu đã tới máy bên kia không? **Không.** Chương trình còn phải gửi byte TLS qua tầng vận chuyển.
2. Đợi `engine.getHandshakeStatus()` trả `FINISHED` có đúng không? **Không.** Sự kiện đó được quan sát trên kết quả `wrap()/unwrap()`.
3. `unwrap()` báo underflow thì có nên `clear()` dữ liệu nguồn rồi đọc lại không? **Không.** Phải giữ phần chưa tiêu thụ.
4. `NEED_WRAP` nhưng ứng dụng chưa gửi gì thì làm gì? **Cho engine tạo dữ liệu bắt tay với nguồn ứng dụng rỗng**, đồng thời quản lý bộ đệm đích và gửi đầu ra.
5. `NOT_HANDSHAKING` có đủ để bật trạng thái “sẵn sàng gửi dữ liệu ứng dụng” không? **Chưa đủ.** Phải xét giai đoạn kết nối và việc bắt tay ban đầu đã hoàn tất.
6. Một lần `unwrap()` không tạo byte ứng dụng có phải TLS lỗi không? **Không nhất thiết.** Nó có thể đang xử lý dữ liệu điều khiển; đọc cả hai trạng thái và dấu hiệu tiến triển.
