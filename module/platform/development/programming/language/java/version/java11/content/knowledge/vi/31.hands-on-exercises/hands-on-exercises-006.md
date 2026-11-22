# WebSocket client: xử lý phân mảnh và điều tiết nhận (Java 11+)

## Mục tiêu

Sau bài này, bạn có thể: (1) phân biệt WebSocket message, frame và từng phần dữ liệu mà Java listener nhận; (2) ghép đúng thông điệp text/binary dựa trên cờ last; (3) dùng cơ chế request(n) để điều tiết số lần callback nhận dữ liệu; (4) tránh giữ bộ đệm vượt giới hạn hoặc truy cập dữ liệu sau khi thư viện được phép tái sử dụng; và (5) kiểm thử kết nối khi dữ liệu đến từng mảnh, chậm hoặc bị ngắt giữa chừng.

Bài dùng API chuẩn trong module java.net.http: HttpClient, WebSocket và WebSocket.Listener, được đưa vào Java 11 và tiếp tục có trong các JDK hiện đại. Không cần thư viện WebSocket bên ngoài để làm client. WebSocket phù hợp khi cần kênh trao đổi hai chiều lâu dài; ứng dụng vẫn phải tự quy định định dạng thông điệp, kích thước tối đa và cách xử lý nghiệp vụ.

## 1. Hiểu đúng message, frame và callback

- **Message** là đơn vị dữ liệu logic của ứng dụng: một thông điệp text hoặc binary. Một message có thể truyền bằng một frame hoặc nhiều frame.
- **Frame** là đơn vị của giao thức WebSocket trên đường truyền. Khi phân mảnh, frame đầu nêu kiểu text/binary, các frame tiếp theo là continuation, và frame cuối có cờ FIN. Ping/Pong là control frame, có thể xuất hiện giữa các frame của một message.
- **Callback nhận dữ liệu** là lần JDK gọi onText hoặc onBinary. Đây là góc nhìn ứng dụng. Không được suy ra rằng một callback luôn tương đương một frame hoặc một message, cũng không được suy ra ranh giới callback từ số lần send của bên gửi.
- **last** trong onText/onBinary bằng false nghĩa là message hiện tại còn phần tiếp theo; bằng true nghĩa là phần hiện tại kết thúc message. last không mang nghĩa “đã hết toàn bộ kết nối”.

Ví dụ, cùng một message text “Xin chào Java” có thể đến như sau:

| Lần callback | data | last | Xử lý |
| --- | --- | --- | --- |
| onText #1 | “Xin ” | false | Tích lũy, chưa phát message |
| onText #2 | “chào ” | false | Tích lũy tiếp |
| onPing | Control frame | Không có last | Xử lý riêng, không xóa text đang ghép |
| onText #3 | “Java” | true | Ghép và phát một message “Xin chào Java” |

Cũng có thể chỉ có một lần onText với toàn bộ chuỗi và last=true. Với binary, ghép đúng các byte theo thứ tự từ vị trí position đến limit của mỗi ByteBuffer. WebSocket không cho phép tự ý xen các mảnh text của một message với mảnh binary của message khác; Ping/Pong là trường hợp control frame được xen giữa.

**Quy tắc cốt lõi:** chỉ chuyển dữ liệu sang lớp xử lý một message hoàn chỉnh khi nhận last=true. Nếu hệ thống thiết kế xử lý streaming từng phần, phải định nghĩa rõ ngữ nghĩa streaming và bảo toàn thứ tự; không thể coi mỗi phần là một thông điệp độc lập.

## 2. Các callback của Java WebSocket.Listener

| Phương thức | Vai trò chính | Điểm cần lưu ý |
| --- | --- | --- |
| onOpen(WebSocket) | Đã kết nối thành công | Nếu tự override, gọi request(1) để bắt đầu nhận; bộ đếm ban đầu là 0 |
| onText(WebSocket, CharSequence, boolean last) | Nhận một phần text | Sao chép hoặc xử lý dữ liệu trong vòng đời hợp lệ; ghép tới last=true |
| onBinary(WebSocket, ByteBuffer, boolean last) | Nhận một phần binary | Dùng remaining(), position/limit; không giữ ByteBuffer gốc ngoài thời gian được phép |
| onPing(WebSocket, ByteBuffer) | Nhận Ping | JDK tự gửi Pong tương ứng; callback vẫn tiêu thụ một lượt demand |
| onPong(WebSocket, ByteBuffer) | Nhận Pong | Cũng tiêu thụ một lượt demand |
| onClose(WebSocket, int, String) | Phía đối tác đóng luồng nhận | Là callback cuối cùng của kết nối này, không tiếp tục request |
| onError(WebSocket, Throwable) | Lỗi kết nối hoặc callback | Là callback cuối cùng; ghi nhận nguyên nhân, giải phóng tài nguyên |

Với một WebSocket, JDK gọi các phương thức listener theo thứ tự, không bắt đầu callback kế tiếp trước khi callback trước trả về. Tuy nhiên, nếu **cùng một listener phục vụ nhiều WebSocket**, các kết nối khác nhau có thể gọi đồng thời: đừng dùng chung StringBuilder hay bộ đếm mà không tách trạng thái theo kết nối.

Dữ liệu CharSequence và ByteBuffer thuộc vòng đời do WebSocket quản lý. CompletionStage do callback trả về báo cho JDK khi có thể thu hồi/tái sử dụng dữ liệu; trả về null có nghĩa có thể thu hồi ngay. Do đó, nếu công việc chạy bất đồng bộ, hãy **sao chép** chuỗi/byte trước khi callback trả về, hoặc quản lý CompletionStage của dữ liệu thật sự đúng cách. Code bên dưới luôn sao chép trước khi trả về null.

## 3. Demand: request(n) điều tiết các lần nhận, không đếm message

WebSocket giữ một bộ đếm demand. Ban đầu demand=0. Mỗi lần gọi webSocket.request(n) với n>0, bộ đếm tăng n. Mỗi lần JDK gọi **một** trong onText, onBinary, onPing, onPong hoặc onClose, bộ đếm giảm 1. Khi demand bằng 0, JDK không gọi tiếp các callback nhận. onOpen và onError không tiêu thụ demand. Nếu request(0) hoặc request(số âm), Java ném IllegalArgumentException.

Ví dụ một chính sách “mỗi lượt xử lý cho phép nhận tiếp một callback”:

1. onOpen gọi request(1): demand=1.
2. onText(“Xin ”, false) đến: demand=0; sao chép phần text, rồi gọi request(1).
3. onPing đến: demand=0; xử lý Ping (JDK tự trả Pong), rồi gọi request(1).
4. onText(“chào”, true) đến: demand=0; xử lý message hoàn chỉnh, rồi gọi request(1).
5. Nếu phía kia gửi Close, onClose dùng lượt demand còn lại; kết nối kết thúc.

Trong ví dụ này, **ba callback nhận chỉ tạo một message text**. Vì vậy request(1) không có nghĩa “cho phép nhận một message”. Không gọi request sau onOpen hoặc bỏ quên request ở nhánh Ping/Pong có thể khiến ứng dụng trông như “đứng hình” dù socket vẫn mở.

Hai cơ chế thường bị nhầm:

- **Demand** quyết định JDK được gọi listener thêm bao nhiêu lần. Đó là công cụ điều tiết nhận.
- **CompletionStage trả về từ onText/onBinary/onPing/onPong** nói khi nào JDK được phép thu hồi dữ liệu callback. CompletionStage **không tự động tăng, giảm hoặc chặn** demand. Nếu muốn đợi công việc nghiệp vụ trước khi nhận tiếp, đặt request(1) ở thời điểm công việc hoàn thành.

Cơ chế này giúp hạn chế callback dồn dập vào ứng dụng, nhưng **không bảo đảm kiểm soát toàn bộ bộ đệm của hệ điều hành, mạng và phía server**. Luôn phối hợp với giới hạn dung lượng message, giới hạn hàng đợi, timeout và quy tắc đóng kết nối.

## 4. Ví dụ Java 11+ chạy được: ghép text/binary, kiểm soát demand

Tệp **FragmentedWebSocketClient.java** dưới đây dùng hoàn toàn API JDK. Chương trình kết nối tới một WebSocket echo server mà bạn có quyền truy cập, gửi một message bằng hai lần sendText, rồi chờ một phản hồi text hoàn chỉnh. Mỗi callback được đọc theo nhịp request(1); chuỗi và byte được ghép theo last; mỗi message có giới hạn bộ nhớ. Vì ranh giới chia mảnh ở phía nhận không được bảo đảm giống phía gửi, chương trình chỉ in nội dung cuối cùng.

~~~java
import java.io.ByteArrayOutputStream;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.WebSocket;
import java.nio.ByteBuffer;
import java.time.Duration;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionException;
import java.util.concurrent.CompletionStage;
import java.util.concurrent.TimeUnit;

public final class FragmentedWebSocketClient {
    private static final int MAX_TEXT_CHARS = 64 * 1024;
    private static final int MAX_BINARY_BYTES = 1024 * 1024;

    static final class AssemblingListener implements WebSocket.Listener {
        private final StringBuilder textParts = new StringBuilder();
        private final ByteArrayOutputStream binaryParts = new ByteArrayOutputStream();

        final CompletableFuture<String> firstText = new CompletableFuture<>();
        final CompletableFuture<Void> closed = new CompletableFuture<>();

        @Override
        public void onOpen(WebSocket ws) {
            System.out.println("CONNECTED");
            ws.request(1); // Cho phép callback nhận đầu tiên
        }

        @Override
        public CompletionStage<?> onText(WebSocket ws,
                                         CharSequence part,
                                         boolean last) {
            // Trừ trước để tránh tràn số khi cộng các độ dài.
            if (part.length() > MAX_TEXT_CHARS - textParts.length()) {
                fail(ws, "Text message vượt giới hạn");
                return null;
            }

            textParts.append(part); // Sao chép nội dung khi còn hợp lệ
            if (last) {
                String complete = textParts.toString();
                textParts.setLength(0); // Sẵn sàng cho message kế tiếp
                System.out.println("TEXT: " + complete);
                firstText.complete(complete);
            }

            ws.request(1); // Callback đã xử lý xong, nhận tiếp một lượt
            return null;
        }

        @Override
        public CompletionStage<?> onBinary(WebSocket ws,
                                           ByteBuffer part,
                                           boolean last) {
            int count = part.remaining(); // Chỉ đọc position..limit
            if (count > MAX_BINARY_BYTES - binaryParts.size()) {
                fail(ws, "Binary message vượt giới hạn");
                return null;
            }

            byte[] copy = new byte[count];
            part.get(copy);          // Không giữ ByteBuffer gốc
            binaryParts.writeBytes(copy);
            if (last) {
                byte[] complete = binaryParts.toByteArray();
                binaryParts.reset();
                System.out.println("BINARY: " + complete.length + " bytes");
                // Ứng dụng thật: giải mã/kiểm tra format của complete tại đây.
            }

            ws.request(1);
            return null;
        }

        @Override
        public CompletionStage<?> onPing(WebSocket ws, ByteBuffer message) {
            // JDK tự gửi Pong tương ứng với Ping.
            ws.request(1); // Ping cũng tiêu thụ một lượt demand
            return null;
        }

        @Override
        public CompletionStage<?> onPong(WebSocket ws, ByteBuffer message) {
            ws.request(1); // Pong cũng tiêu thụ một lượt demand
            return null;
        }

        @Override
        public CompletionStage<?> onClose(WebSocket ws,
                                          int statusCode,
                                          String reason) {
            System.out.println("CLOSE " + statusCode + ": " + reason);
            firstText.completeExceptionally(
                    new IllegalStateException("Peer đóng trước phản hồi text"));
            closed.complete(null);
            return null; // Không request thêm sau Close
        }

        @Override
        public void onError(WebSocket ws, Throwable error) {
            firstText.completeExceptionally(error);
            closed.completeExceptionally(error);
        }

        private void fail(WebSocket ws, String message) {
            IllegalStateException error = new IllegalStateException(message);
            firstText.completeExceptionally(error);
            closed.completeExceptionally(error);
            ws.abort(); // Dừng ngay khi nhận dữ liệu vượt giới hạn
        }
    }

    public static void main(String[] args) {
        if (args.length != 1) {
            System.err.println(
                    "Cách dùng: java FragmentedWebSocketClient <WebSocket-URI>");
            return;
        }

        URI uri = URI.create(args[0]);
        String scheme = uri.getScheme();
        if (!"ws".equals(scheme) && !"wss".equals(scheme)) {
            throw new IllegalArgumentException("URI phải dùng ws hoặc wss");
        }

        AssemblingListener listener = new AssemblingListener();
        WebSocket ws = HttpClient.newHttpClient()
                .newWebSocketBuilder()
                .connectTimeout(Duration.ofSeconds(10))
                .buildAsync(uri, listener)
                .join();

        try {
            // Hai phần thuộc CÙNG một message gửi đi.
            ws.sendText("Xin ", false)
              .thenCompose(socket -> socket.sendText("chào WebSocket!", true))
              .join();

            // Echo server phải phản hồi text; nếu không, timeout rõ ràng.
            listener.firstText.orTimeout(10, TimeUnit.SECONDS).join();
        } finally {
            if (!ws.isOutputClosed()) {
                try {
                    ws.sendClose(WebSocket.NORMAL_CLOSURE, "")
                      .orTimeout(3, TimeUnit.SECONDS).join();
                } catch (CompletionException error) {
                    ws.abort();
                }
            }
            try {
                listener.closed.orTimeout(3, TimeUnit.SECONDS).join();
            } catch (CompletionException error) {
                ws.abort(); // Fallback khi peer không hoàn tất đóng
            }
        }
    }
}
~~~

Biên dịch bằng JDK 11 trở lên (ví dụ JDK 17 hoặc 21):

~~~bash
javac FragmentedWebSocketClient.java
java FragmentedWebSocketClient "$ECHO_WS_URL"
~~~

Trong PowerShell, đối số biến môi trường tương đương là: **java FragmentedWebSocketClient $env:ECHO_WS_URL**. Hãy cấu hình ECHO_WS_URL thành URI ws:// hoặc wss:// của một echo server thực sự trước khi chạy. Không cần thêm dependency. Nếu server echo nguyên văn dữ liệu gửi, dòng nội dung mong đợi là:

~~~text
TEXT: Xin chào WebSocket!
~~~

Số callback và cách server trả Close phụ thuộc server/mạng; không khẳng định rằng phản hồi sẽ có đúng hai mảnh như lúc gửi. Nếu server không echo text, chương trình báo timeout thay vì chờ vô hạn. Khi dùng trên Internet, ưu tiên wss:// để mã hóa đường truyền.

### Vì sao ví dụ xử lý đúng?

1. **Không giả định số mảnh:** onText/onBinary tích lũy cho tới last=true, rồi reset buffer cho message kế tiếp.
2. **Không giữ dữ liệu sống của callback:** StringBuilder.append sao chép các ký tự; ByteBuffer được sao chép sang byte[] ngay trong callback; trả về null an toàn với các dữ liệu đã được sao chép.
3. **Không cấp demand vô hạn:** bắt đầu request(1) và bổ sung một lượt sau mỗi callback xử lý xong, kể cả Ping/Pong. Close/Error là kết thúc.
4. **Giới hạn theo từng message:** MAX_TEXT_CHARS và MAX_BINARY_BYTES ngăn một message phân mảnh vô tận làm tăng bộ đệm ứng dụng. Trường hợp vượt giới hạn ví dụ chọn abort; hệ thống thật nên xác định chính sách lỗi với server.
5. **Gửi đúng thứ tự:** thenCompose chờ lần sendText đầu hoàn thành trước khi gửi phần kết thúc. Boolean false rồi true biểu diễn một message gửi đi. Không gọi hai thao tác gửi dữ liệu đồng thời tùy tiện.

**Giới hạn của ví dụ:** chương trình minh họa nhận text phản hồi đầu tiên, đồng thời có thể ghi nhận binary nếu server gửi. Nó không định nghĩa protocol nghiệp vụ cho binary và không tự reconnect. Giới hạn text dùng số đơn vị ký tự UTF-16, không phải số byte UTF-8; nếu hợp đồng ứng dụng đặt giới hạn theo byte, hãy bổ sung kiểm tra kích thước byte tương ứng. Callback đang xử lý ngắn; với nghiệp vụ chậm, dùng cách điều tiết ở phần tiếp theo.

## 5. Điều tiết theo tốc độ xử lý thực tế: chỉ request khi downstream sẵn sàng

Ở ví dụ trên, in một message hoàn chỉnh là việc nhanh. Nếu mỗi message cần ghi database, giải nén, gọi API hoặc parse dữ liệu lớn, không nên làm việc nặng trong callback mạng hoặc cứ request tiếp ngay khiến công việc tích tụ. Có thể xử lý bất đồng bộ **sau khi đã chép dữ liệu sang đối tượng tự quản lý**, và chỉ gọi request(1) khi tác vụ hoàn thành.

Đoạn dưới minh họa cách **thay nhánh xử lý last=true của onText** trong một listener có ExecutorService worker riêng và hàm handleCompleteText(String). Đây là mẫu tích hợp, không phải chương trình độc lập:

~~~java
// Trong onText, sau khi đã append part vào textParts:
if (!last) {
    ws.request(1); // Còn mảnh của cùng message thì nhận tiếp
    return null;
}

String complete = textParts.toString();
textParts.setLength(0); // Đã copy, không cần giữ CharSequence gốc

CompletableFuture.runAsync(() -> handleCompleteText(complete), worker)
        .whenComplete((ignored, error) -> {
            if (error == null && !ws.isInputClosed()) {
                ws.request(1); // Downstream xong mới mở lượt tiếp
            } else if (error != null) {
                ws.abort(); // Có chính sách báo lỗi/đóng tương ứng
            }
        });
return null;
~~~

Ở đây, khi last=true và công việc còn chạy, không phát thêm request nên demand của kết nối có thể về 0. Việc CompletionStage của callback trả về null **không tự tạo backpressure**; chính vị trí gọi request mới làm được điều đó. Phần dữ liệu đã được sao chép nên JDK có thể tái sử dụng bộ đệm mà không ảnh hưởng tác vụ async.

Nếu dùng hàng đợi nhiều worker, phải định nghĩa số phần tử tối đa, thứ tự xử lý và quy tắc xử lý khi đầy. Nếu yêu cầu bảo toàn thứ tự thông điệp, dùng một worker tuần tự cho mỗi kết nối hoặc cơ chế sequence phù hợp; không giả định xử lý song song sẽ hoàn tất theo thứ tự gửi. Đồng thời quản lý vòng đời worker, ngắt tác vụ khi Close/Error và không request sau khi input đóng.

**Đừng nhầm:** trả về một CompletableFuture chưa hoàn tất từ onText chỉ quản lý quyền sử dụng dữ liệu callback; nó **không phải** tín hiệu cắt demand. Nếu muốn chờ async hoàn tất, bạn phải hoãn lời gọi request(1).

## 6. Phân mảnh chiều gửi và những giới hạn API

- sendText(part, false) gửi một phần của message text; sendText(part, true) kết thúc message đó. sendBinary(ByteBuffer, last) tương tự cho binary.
- Mỗi lời gọi gửi trả về CompletableFuture<WebSocket>; dùng thenCompose/chaining để bảo đảm thứ tự. Nếu cố thực hiện thao tác text/binary mới khi thao tác trước còn pending, hoặc chuyển kiểu khi message trước chưa kết thúc, có thể gặp IllegalStateException.
- Không thay đổi CharSequence khi lệnh sendText chưa hoàn tất; không đụng tới ByteBuffer đang được sendBinary dùng. Sau khi gửi binary hoàn tất, vị trí buffer đã được tiêu thụ theo hợp đồng API.
- sendPing/sendPong dùng control frame có payload tối đa 125 byte. Java WebSocket client tự phản hồi Pong khi nhận Ping, không cần tự gửi thêm một Pong trùng.
- sendClose(WebSocket.NORMAL_CLOSURE, "") là đóng chiều gửi bình thường; phía nhận có thể còn mở tới khi peer đóng. abort() chấm dứt cả hai chiều ngay lập tức.
- **Lưu ý chính xác của Java API:** dù giao thức WebSocket có mã Close 1009 cho message quá lớn, WebSocket.sendClose của JDK liệt kê 1009 trong những mã **không được gửi bằng phương thức này**. Không viết sendClose(1009, ...) rồi cho rằng sẽ hoạt động; ví dụ chọn abort khi vượt giới hạn. Nếu cần close code ứng dụng, thống nhất mã hợp lệ với phía server và kiểm tra tài liệu JDK.

**Giới hạn protocol:** Ping/Pong và Close không bị phân mảnh thành nhiều control frame; control frame có thể xuất hiện giữa các fragment dữ liệu. Không được dùng ranh giới frame làm ranh giới nghiệp vụ hoặc suy ra mỗi lời gọi sendText sẽ được phản chiếu thành đúng một onText ở đầu bên kia.

## 7. Những lỗi thường gặp và cách sửa

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- |
| Kết nối thành công nhưng không nhận gì | Override onOpen mà quên request(1), hoặc nhánh callback không request tiếp | Cấp demand ban đầu; xét mọi nhánh dữ liệu/Ping/Pong |
| Mỗi câu nhận bị thiếu hoặc bị tách | Coi mỗi lần onText là một message hoàn chỉnh | Ghép theo thứ tự tới last=true rồi mới xử lý |
| Memory tăng liên tục khi server gửi lớn | Không giới hạn buffer tích lũy qua nhiều fragment | Giới hạn theo *cả message*, xử lý overflow và đóng kết nối |
| Có lỗi dữ liệu sau khi callback đã trả về | Giữ ByteBuffer/CharSequence gốc quá vòng đời | Sao chép ngay, hoặc quản lý CompletionStage phù hợp |
| Xử lý chậm nhưng queue vẫn phình | request tiếp trước khi worker hoàn thành | Hoãn request tới lúc downstream thật sự sẵn sàng; giới hạn queue |
| Nhận Ping giữa text làm mất dữ liệu | Xóa textParts khi gặp control frame | Xử lý Ping/Pong độc lập; chỉ reset text khi last=true |
| IllegalStateException lúc gửi | Hai send dữ liệu chồng nhau hoặc đổi text/binary giữa message chưa kết thúc | Chain CompletableFuture; kết thúc message trước khi đổi kiểu |
| Chờ Close mãi | Không còn demand, peer không trả Close hoặc kết nối lỗi | Dùng timeout, xử lý onClose/onError và abort dự phòng |
| Test lúc chạy không giống số mảnh kỳ vọng | Sender, mạng, implementation có thể chia/gộp ranh giới | Kiểm tra nội dung message, không assert số callback cố định |

## 8. Bài thực hành và tiêu chí kiểm chứng

Với một server kiểm thử do bạn điều khiển, tạo các kịch bản: một message text giao trong một callback; một message qua nhiều callback last=false rồi last=true; message rỗng last=true; Ping xen giữa các phần text; binary qua nhiều phần; message vượt giới hạn; peer đóng trước khi gửi phản hồi; và downstream cố ý chậm. Bất kỳ kịch bản nào cũng cần xác nhận nội dung sau ghép đúng thứ tự, không phát message trước last=true, không vượt buffer đã khai báo, không truy cập dữ liệu callback sau khi được phép thu hồi và không treo khi đóng/lỗi.

Một chuỗi kiểm thử thuần logic của bộ ghép text:

~~~text
onText("Java ", false)  -> chưa tạo message
onPing(...)             -> không thay đổi bộ ghép
onText("11+", true)     -> tạo đúng một message: "Java 11+"
onText("", true)        -> tạo một message rỗng độc lập
~~~

Cần phân biệt **kiểm thử unit** (chủ động gọi hàm tích lũy dữ liệu trong code, xác nhận quy tắc last/reset) với **kiểm thử tích hợp** (server WebSocket thật điều khiển chia frame, Ping/Pong và đóng kết nối). Khi đo backpressure, log số lượt request, số lần callback, kích thước buffer/queue và độ trễ downstream; kiểm chứng rằng số callback không tăng vượt demand đã cấp, nhưng không giả định toàn bộ bộ nhớ mạng luôn bằng 0 khi demand=0.

## 9. Ghi nhớ và tài liệu chuẩn

- **last** kết thúc *một message*, không phải kết thúc kết nối.
- **request(n)** cho phép thêm *n lần gọi receive callback*, không phải n message; Ping/Pong/Close cũng dùng demand.
- **CompletionStage nhận** quản lý thời điểm dữ liệu có thể bị thu hồi; muốn điều tiết tốc độ, hãy quyết định lúc nào gọi request tiếp.
- **Bảo vệ tài nguyên:** ghép đúng thứ tự, đặt giới hạn dung lượng mỗi message và queue, sao chép dữ liệu trước khi xử lý async, có timeout/Close/Error rõ ràng.
- **Tính tương thích:** java.net.http.WebSocket và Listener là API chuẩn từ Java 11, vẫn có mặt trong Java 21/25; ví dụ không dựa vào API WebSocket cũ đã bị thay thế.

Nguồn đối chiếu:
1. [Oracle Java SE 25 – WebSocket](https://docs.oracle.com/en/java/javase/25/docs/api/java.net.http/java/net/http/WebSocket.html): demand, request(n), sendText/sendBinary, sendClose/abort.
2. [Oracle Java SE 25 – WebSocket.Listener](https://docs.oracle.com/en/java/javase/25/docs/api/java.net.http/java/net/http/WebSocket.Listener.html): last, thứ tự callback, vòng đời CharSequence/ByteBuffer và CompletionStage.
3. [RFC 6455 – WebSocket Protocol, mục 5.4–5.5](https://www.rfc-editor.org/rfc/rfc6455.html): phân mảnh, continuation và control frame xen giữa.
