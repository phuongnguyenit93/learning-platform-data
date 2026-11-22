# SSLEngineResult.HandshakeStatus.FINISHED và hoàn tất bắt tay

## 1. FINISHED trả lời câu hỏi gì?

Bắt tay TLS thiết lập các tham số để hai đầu truyền dữ liệu được bảo vệ. Với `SSLEngine`, ứng dụng tự đưa dữ liệu qua `wrap()` và `unwrap()`, nên cũng phải tự nhận biết thời điểm có thể chuyển từ giai đoạn bắt tay ban đầu sang xử lý dữ liệu ứng dụng.

`SSLEngineResult.HandshakeStatus.FINISHED` báo rằng **chính lời gọi `wrap()` hoặc `unwrap()` vừa hoàn tất một lần bắt tay ở engine cục bộ**. Nó là dấu mốc cần quan sát trên kết quả của lời gọi, không phải một trạng thái bền vững để liên tục hỏi engine.

Đây vẫn là hợp đồng API đang áp dụng trên JDK hiện đại. Việc lớp có từ Java 5 không phải lý do sử dụng giao thức, thuật toán hay cấu hình tin cậy cũ.

Theo [định nghĩa FINISHED](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/javax/net/ssl/SSLEngineResult.HandshakeStatus.html#FINISHED), giá trị này chỉ xuất hiện trong kết quả `wrap()/unwrap()` khi lời gọi đó hoàn tất bắt tay; `SSLEngine.getHandshakeStatus()` không trả nó.

## 2. Phân biệt sự kiện vừa xảy ra với trạng thái hiện tại

Hai phương thức sau có tên gần giống nhau nhưng phục vụ cách quan sát khác nhau:

| Cách đọc | Thông tin cần dùng |
| --- | --- |
| `result.getHandshakeStatus()` | Trạng thái bắt tay gắn với lời gọi vừa thực hiện; đây là nơi quan sát `FINISHED` |
| `engine.getHandshakeStatus()` | Nhu cầu xử lý bắt tay hiện tại của engine để chọn công việc tiếp theo |

Đoạn mã đúng về vị trí quan sát:

```java
// Minh họa tích hợp: engine, netIn và appIn đã được quản lý bên ngoài.
SSLEngineResult result = engine.unwrap(netIn, appIn);

if (result.getHandshakeStatus()
        == SSLEngineResult.HandshakeStatus.FINISHED) {
    // Ghi nhận engine vừa hoàn tất bắt tay.
}
```

Cần đặt việc quan sát tương tự sau `wrap()`. Nếu chỉ kiểm tra kết quả `unwrap()`, chương trình có thể bỏ lỡ lần hoàn tất xảy ra khi tạo dữ liệu gửi.

Sai lầm thường gặp:

```java
// Sai: phương thức này không trả FINISHED.
while (engine.getHandshakeStatus()
        != SSLEngineResult.HandshakeStatus.FINISHED) {
    // Chỉ hỏi lại trạng thái không làm engine tiến triển.
}
```

Vòng lặp trên vừa kiểm tra một điều kiện không thể đạt theo hợp đồng API, vừa không thực hiện công việc giao thức. Ngay cả thay điều kiện bằng một enum khác, việc hỏi liên tục cũng không thay thế `wrap()`, `unwrap()`, tác vụ được giao hoặc I/O.

### NOT_HANDSHAKING không phải bằng chứng lịch sử

`NOT_HANDSHAKING` cho biết hiện không có bắt tay đang diễn ra. Nó không mang thông tin “kết nối này đã bắt tay thành công trước đó”.

Suy luận bằng một tình huống đơn giản: engine mới tạo nhưng chưa bắt đầu xử lý không thể được coi là kết nối đã sẵn sàng chỉ vì hiện chưa bắt tay. Nếu chương trình cần biết “đã hoàn tất bắt tay ban đầu chưa”, phải lưu giai đoạn kết nối hoặc lưu sự kiện hoàn tất.

Không dùng `engine.getHandshakeStatus() == NOT_HANDSHAKING` làm điều kiện duy nhất để đánh dấu kết nối sẵn sàng.

## 3. Hoàn tất ở engine không có nghĩa hoàn tất mọi công việc I/O

`SSLEngine` xử lý bộ đệm và độc lập với tầng vận chuyển. Nó không tự gửi dữ liệu qua socket. Trách nhiệm vận chuyển và giữ thứ tự byte thuộc ứng dụng, theo [SSLEngine API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/javax/net/ssl/SSLEngine.html).

Giả sử bộ điều khiển vừa gọi `wrap()` và nhận `FINISHED`. Nếu có byte TLS mới trong bộ đệm đích thì các byte đó vẫn cần được chuyển cho phía bên kia. Gọi callback “TLS đã sẵn sàng” rồi ghi đè bộ đệm đầu ra sẽ phá hỏng luồng truyền.

Cần phân biệt ba dấu mốc:

| Dấu mốc | Điều đã biết | Điều chưa được chứng minh |
| --- | --- | --- |
| `FINISHED` trong kết quả | Engine cục bộ vừa hoàn tất bắt tay | Mọi byte đầu ra đã ra khỏi bộ đệm của ứng dụng |
| Hàng đợi mạng đã gửi hết | Ứng dụng đã giao hết byte đang chờ cho tầng vận chuyển | Ứng dụng bên kia đã xử lý một yêu cầu cụ thể |
| Nhận phản hồi giao thức ứng dụng | Phía bên kia đã phản hồi theo giao thức đó | Thành công của các yêu cầu khác |

Bảng này là mô hình suy luận để thiết kế chương trình. Nó tránh gán cho `FINISHED` những ý nghĩa thuộc TCP hoặc giao thức ứng dụng.

Sau khi engine cục bộ hoàn tất và các kiểm tra chính sách cần thiết đã đạt, ứng dụng có thể được cho phép xếp dữ liệu gửi mới vào hàng đợi. Điều kiện là dữ liệu TLS tạo sau phải nằm **sau** dữ liệu TLS đã tạo trước. Không bắt buộc biến mọi lần gửi thành thao tác chặn chờ đầu bên kia xác nhận, nhưng bắt buộc bảo toàn thứ tự.

## 4. Xử lý kết quả hoàn tất mà không bỏ sót dữ liệu

Một kết quả có nhiều thông tin độc lập. `FINISHED` thuộc `HandshakeStatus`; `OK`, `BUFFER_OVERFLOW`, `BUFFER_UNDERFLOW`, `CLOSED` thuộc `Status`. Không đặt `FINISHED` vào `switch(result.getStatus())`.

Ngoài ra, `bytesConsumed()` và `bytesProduced()` mô tả dữ liệu của lời gọi. Không suy ra rằng `FINISHED` luôn đi kèm số byte ứng dụng dương hoặc luôn đi kèm số byte đầu ra bằng 0. Hợp đồng các trường nằm trong [SSLEngineResult API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/javax/net/ssl/SSLEngineResult.html).

Một thứ tự xử lý có thể áp dụng trong bộ điều khiển do ứng dụng sở hữu:

1. Giữ lại kết quả vừa nhận, thay vì bỏ nó rồi chỉ hỏi trạng thái hiện tại.
2. Bảo toàn byte TLS mới tạo hoặc dữ liệu ứng dụng mới giải mã theo đúng chiều.
3. Kiểm tra trạng thái xử lý; sửa điều kiện bộ đệm, quản lý đóng hoặc ghi nhận lỗi.
4. Quan sát `FINISHED` trên kết quả để chuyển giai đoạn bắt tay.
5. Kiểm tra các điều kiện ứng dụng cần trước khi phát sự kiện sẵn sàng.
6. Tiếp tục đẩy hàng đợi mạng và xử lý các trạng thái mới của engine.

Các bước có thể được tổ chức khác trong một thư viện, nhưng không được làm mất đầu ra hoặc bỏ qua điều kiện lỗi. Nếu gọi callback ngay trong luồng xử lý kết quả, cần đề phòng callback tự gửi dữ liệu, đóng kết nối hoặc gọi ngược vào bộ điều khiển. Cách dễ kiểm soát hơn là cập nhật trạng thái trước, rồi lên lịch thông báo theo cùng cơ chế điều phối của kết nối.

## 5. Thiết kế trạng thái sẵn sàng của ứng dụng

Một cờ duy nhất có thể đủ cho ví dụ nhỏ, nhưng hệ thống thực tế thường có nhiều giai đoạn:

```text
NEW -> HANDSHAKING -> ACTIVE
          |             |
          v             v
        FAILED        CLOSING -> CLOSED
```

Đây là trạng thái do ứng dụng thiết kế, không phải enum mới của JSSE.

- `NEW`: chưa khởi động bắt tay ban đầu.
- `HANDSHAKING`: đang tiến hành bắt tay; có thể đang chờ mạng, bộ đệm hoặc tác vụ.
- `ACTIVE`: bắt tay ban đầu đã hoàn tất và chính sách sẵn sàng đã được kiểm tra.
- `FAILED`: kết nối thất bại; không mở lại chỉ do một callback đến muộn.
- `CLOSING/CLOSED`: đang đóng hoặc đã đóng; không nhận thêm yêu cầu ứng dụng mới.

Cần phân biệt **đã quan sát hoàn tất TLS** với **ứng dụng đã chấp nhận kết nối**. Chẳng hạn, ứng dụng có thể cần kiểm tra giao thức ALPN đã thương lượng trước khi chọn bộ phân tích HTTP. Nếu chính sách yêu cầu một giao thức cụ thể nhưng không thương lượng được, không bật sẵn sàng chỉ vì TLS đã hoàn tất.

Sự kiện sẵn sàng ban đầu thường chỉ được phát một lần. Nếu hàm xử lý bị gọi lại hoặc chương trình phát lại một thông báo nội bộ, không được khởi chạy lại yêu cầu mở đầu của giao thức, gửi hai lần thông tin đăng nhập hoặc đăng ký trùng kết nối trong nhóm tái sử dụng.

Trong mô hình nhiều luồng, cập nhật giai đoạn, xếp đầu ra và phát callback phải có quan hệ đồng bộ rõ ràng. Cờ `boolean` riêng lẻ không tự bảo đảm thứ tự với các bộ đệm và hàng đợi khác. Ví dụ tiếp theo cố ý dùng một luồng để tập trung vào logic giai đoạn.

## 6. Ví dụ Java 17+: ghi nhận hoàn tất đúng một lần

Chương trình dưới đây kiểm tra một bộ ghi nhận sự kiện bằng các `SSLEngineResult` **được tạo giả lập**. Nó không bắt tay TLS thật, không mở socket và không xác thực chứng chỉ. Các kết quả được đưa vào để chứng minh `NOT_HANDSHAKING` không bật sẵn sàng, còn sự kiện hoàn tất chỉ tạo một lần chuyển giai đoạn.

Lưu thành `HandshakeCompletionDemo.java`:

```java
import javax.net.ssl.SSLEngineResult;
import javax.net.ssl.SSLEngineResult.HandshakeStatus;
import javax.net.ssl.SSLEngineResult.Status;

public class HandshakeCompletionDemo {
    private enum Phase {
        NEW, HANDSHAKING, ACTIVE, FAILED
    }

    private static final class InitialHandshake {
        private Phase phase = Phase.NEW;
        private int readyEvents;

        void begin() {
            if (phase != Phase.NEW) {
                throw new IllegalStateException("Already started");
            }
            phase = Phase.HANDSHAKING;
        }

        void observe(SSLEngineResult result) {
            if (phase == Phase.HANDSHAKING
                    && result.getHandshakeStatus()
                    == HandshakeStatus.FINISHED) {
                phase = Phase.ACTIVE;
                readyEvents++;
            }
        }

        void fail() {
            phase = Phase.FAILED;
        }

        boolean isReady() {
            return phase == Phase.ACTIVE;
        }

        int readyEvents() {
            return readyEvents;
        }
    }

    public static void main(String[] args) {
        InitialHandshake handshake = new InitialHandshake();
        System.out.println("new ready=" + handshake.isReady());

        handshake.begin();
        handshake.observe(new SSLEngineResult(
                Status.OK, HandshakeStatus.NOT_HANDSHAKING, 0, 0));
        System.out.println("idle result ready=" + handshake.isReady());

        SSLEngineResult completed = new SSLEngineResult(
                Status.OK, HandshakeStatus.FINISHED, 0, 0);
        handshake.observe(completed);
        System.out.println("finished ready=" + handshake.isReady());

        // Cố ý đưa lại cùng sự kiện để kiểm tra không phát trùng.
        handshake.observe(completed);
        System.out.println("ready events=" + handshake.readyEvents());

        handshake.fail();
        handshake.observe(completed);
        System.out.println("after failure ready=" + handshake.isReady());
    }
}
```

Chạy bằng JDK 17+:

```shell
javac HandshakeCompletionDemo.java
java HandshakeCompletionDemo
```

Stdout:

```text
new ready=false
idle result ready=false
finished ready=true
ready events=1
after failure ready=false
```

Lần đưa lại `completed` là phép kiểm tra tự thiết kế cho bộ ghi nhận; không có nghĩa engine thật sẽ trả lặp cùng kết quả. Bộ ghi nhận cũng không phải bộ điều khiển TLS đầy đủ: nó giả định bên ngoài đã bảo toàn đầu ra và xử lý kết quả/lỗi trước khi cho phép chuyển sang `ACTIVE`. Khi thêm chính sách ứng dụng, có thể tách thêm giai đoạn “TLS hoàn tất, đang kiểm tra chính sách” trước `ACTIVE`.

## 7. FINISHED không bù cho cấu hình xác thực sai

TLS chỉ kiểm tra theo cấu hình đã được cung cấp. Nếu ứng dụng cố tình sử dụng một `TrustManager` chấp nhận mọi chứng chỉ, việc thấy `FINISHED` không làm cấu hình đó trở nên an toàn.

Tương tự, khi đóng vai máy khách HTTPS bằng `SSLEngine`, cần cấu hình kiểm tra danh tính đầu cuối trước bắt tay, cùng ngữ cảnh tin cậy phù hợp:

```java
// Minh họa cấu hình máy khách HTTPS.
// sslContext đã được khởi tạo với cấu hình tin cậy phù hợp.
SSLEngine engine = sslContext.createSSLEngine("example.com", 443);
engine.setUseClientMode(true);

SSLParameters parameters = engine.getSSLParameters();
parameters.setEndpointIdentificationAlgorithm("HTTPS");
engine.setSSLParameters(parameters);
engine.beginHandshake();
```

Đây là đoạn cấu hình, không phải chương trình mở kết nối hoàn chỉnh. Không lấy nhãn `"HTTPS"` áp dụng tùy tiện cho mọi giao thức ứng dụng; cần dùng cách xác định danh tính phù hợp với giao thức đó. Xem [SSLParameters và kiểm tra danh tính đầu cuối](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/javax/net/ssl/SSLParameters.html#setEndpointIdentificationAlgorithm(java.lang.String)).

Nếu yêu cầu quyền truy cập ở tầng ứng dụng, vẫn phải kiểm tra riêng sau TLS. Hoàn tất kênh bảo mật không tự cấp quyền thực hiện mọi thao tác nghiệp vụ.

## 8. Sau hoàn tất vẫn phải điều khiển engine

Không thiết kế kết nối theo giả định “thấy `FINISHED` rồi từ nay chỉ mã hóa/giải mã dữ liệu ứng dụng”. TLS 1.3 có các thông điệp sau bắt tay như `NewSessionTicket` và `KeyUpdate`. TLS 1.3 cũng không sử dụng cơ chế thương lượng lại phiên theo kiểu TLS cũ. Vì vậy, không coi mọi hoạt động điều khiển sau đó là bắt đầu lại cùng một chuỗi bắt tay ban đầu.

Các cơ chế giao thức này được quy định trong [RFC 8446, mục 4.6](https://www.rfc-editor.org/rfc/rfc8446.html#section-4.6). Cách chúng thể hiện qua lời gọi cụ thể còn phụ thuộc JSSE, cấu hình và thông điệp nhận được; không gắn cứng một chuỗi enum duy nhất cho mọi nhà cung cấp.

Bộ điều khiển vẫn phải đọc kết quả mỗi `wrap()/unwrap()`, thực hiện công việc engine yêu cầu, giữ thứ tự gửi và xử lý đóng/lỗi. Cờ “bắt tay ban đầu đã xong” phục vụ vòng đời ứng dụng; nó không cho phép bỏ qua máy trạng thái giao thức.

## 9. Chẩn đoán khi không thấy sự kiện hoàn tất

| Triệu chứng | Điểm cần kiểm tra |
| --- | --- |
| Hỏi trạng thái liên tục nhưng không thấy `FINISHED` | Có đang hỏi getter của engine thay vì đọc kết quả lời gọi không? |
| Chỉ máy khách hoặc máy chủ báo sẵn sàng | Đầu ra TLS còn nằm trong hàng đợi chưa gửi, hoặc đầu kia chưa xử lý hết không? |
| Đứng ở `NEED_TASK` | Tác vụ đã chạy xong hay mới được đưa vào hàng đợi? |
| Đứng ở `NEED_UNWRAP` | Có giữ byte đầu vào chưa tiêu thụ, đọc thêm và gọi lại đúng chế độ bộ đệm không? |
| Đứng ở `NEED_WRAP` | Có cho phép tạo dữ liệu bắt tay khi hàng đợi ứng dụng rỗng không? |
| Không có kết quả hoàn tất, kết nối đã lỗi | Có `SSLException`, lỗi tác vụ, timeout hoặc đóng vận chuyển cần được báo thất bại không? |

Không chờ vô hạn khi không có tiến triển. Dùng thời hạn bắt tay do ứng dụng quản lý và kết thúc rõ ràng nếu hết hạn. Khi ghi log, ưu tiên mã kết nối, chiều `wrap/unwrap`, hai trạng thái và số byte tiêu thụ/tạo ra; không cần ghi plaintext hay khóa bí mật để quan sát dấu mốc.

## 10. Tự kiểm tra

1. Vì sao kiểm tra `engine.getHandshakeStatus() == FINISHED` sai? **Getter của engine không trả giá trị này; phải kiểm tra kết quả `wrap()/unwrap()`.**
2. Có thể hoàn tất trong `wrap()` không? **Có; vì vậy phải quan sát kết quả của cả hai chiều.**
3. `FINISHED` có cho phép xóa mọi bộ đệm đầu ra không? **Không; vẫn phải bảo toàn và gửi dữ liệu TLS đã tạo.**
4. Thấy `NOT_HANDSHAKING` có chứng minh đã bắt tay thành công không? **Không; cần thông tin giai đoạn đã lưu.**
5. Vì sao sự kiện sẵn sàng phải tránh phát trùng? **Ứng dụng có thể khởi động công việc chỉ được phép thực hiện một lần cho kết nối.**
6. Sau hoàn tất có bỏ qua các trạng thái bắt tay ở kết quả sau được không? **Không; bộ điều khiển vẫn phải thực hiện yêu cầu giao thức và xử lý lỗi/đóng.**
