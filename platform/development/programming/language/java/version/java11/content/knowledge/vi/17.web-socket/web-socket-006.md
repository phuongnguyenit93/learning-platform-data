# WebSocket Java 11: sendText, sendBinary và bảo đảm thứ tự gửi

## Mục tiêu

Trong ứng dụng real-time, WebSocket cho phép hai phía trao đổi **text** và **binary** trên một kết nối đã bắt tay. Java 11 cung cấp client WebSocket chính thức thuộc module `java.net.http`. Hai phương thức trung tâm của bài học là:

~~~java
CompletableFuture<WebSocket> sendText(CharSequence data, boolean last);
CompletableFuture<WebSocket> sendBinary(ByteBuffer data, boolean last);
~~~

Cả hai đều **khởi tạo thao tác gửi bất đồng bộ** và trả lại `CompletableFuture<WebSocket>`. Tuy nhiên, một WebSocket **không phải hàng đợi tự động sắp xếp mọi lệnh gửi do nhiều luồng gọi đồng thời**: nếu thao tác text/binary trước đang pending, thao tác text/binary mới có thể thất bại; nếu message text hoặc binary đã bắt đầu nhưng chưa được kết thúc, không được đan xen một message của loại còn lại.

Học xong, bạn có thể:

1. Tạo `WebSocket` bằng `HttpClient.newWebSocketBuilder().buildAsync(...)` và hiểu kết quả bất đồng bộ.
2. Gửi **một text message đầy đủ** hoặc **binary message đầy đủ**, phân biệt `String/CharSequence` với `ByteBuffer`.
3. Dùng tham số **`last=true/false`** để phân mảnh **một message logic** thành nhiều lần gửi, đồng thời kết thúc đúng loại trước khi chuyển loại.
4. Tạo chuỗi gửi **đúng thứ tự** bằng `CompletableFuture.thenCompose`; xử lý nhiều producer bằng cơ chế nối queue/ownership trên cùng socket.
5. Hiểu vòng đời dữ liệu: text đầu vào không được thay đổi khi send pending; `ByteBuffer` dùng bytes từ `position` đến `limit` và bị tiêu thụ trên completion thành công.
6. Phân biệt **send future completed** với **server đã nhận/xử lý/ack ở tầng nghiệp vụ**, tránh cam kết giao hàng quá mức.
7. Xử lý `IllegalStateException` do pending hoặc phân mảnh sai, `IOException`/đóng output, UTF-16 không hợp lệ, cancellation và đóng kết nối.
8. Biên dịch/chạy một chương trình Java 11 tự chứa **HTTP Upgrade + RFC 6455 echo server cục bộ**, rồi kiểm tra UTF-8 tiếng Việt, nhị phân, message fragments, thứ tự gửi, lỗi trộn loại và close handshake.

`java.net.http.WebSocket` có **Since: 11**, vẫn xuất hiện trong Javadoc JDK hiện hành. Không dùng API incubator HTTP/WebSocket của các JDK cũ hoặc thư viện khác khi hướng dẫn trực tiếp API chuẩn Java 11.

## 1. WebSocket trong Java 11 hoạt động thế nào?

### 1.1. Tạo kết nối

Client được tạo thông qua `HttpClient`, sau đó gọi WebSocket builder:

~~~java
HttpClient client = HttpClient.newHttpClient();

CompletableFuture<WebSocket> opening =
        client.newWebSocketBuilder()
              .connectTimeout(Duration.ofSeconds(5))
              .buildAsync(
                  URI.create("wss://example.com/events"),
                  listener);
~~~

Đây là **đoạn minh họa**, giả định `listener` là một đối tượng `WebSocket.Listener` và đã import các lớp tương ứng; URL chỉ mang tính minh họa. `buildAsync(...)` trả `CompletableFuture<WebSocket>`, chưa phải socket đã kết nối ngay tại thời điểm gọi.

Phân biệt:

- `ws://`: kết nối WebSocket không mã hóa ở tầng TLS, thích hợp cho **loopback test** khi có kiểm soát.
- `wss://`: WebSocket qua TLS; dùng cho mạng không tin cậy và dữ liệu thực, kiểm tra chứng chỉ/TLS theo thiết kế.
- WebSocket **bắt tay qua HTTP**, sau đó trao đổi frame WebSocket; `HttpClient.sendAsync(HttpRequest, BodyHandler)` là API HTTP request-response thông thường, **không phải** cách gửi message WebSocket sau khi upgrade.
- `WebSocket` có **input side** và **output side** độc lập; gửi hoạt động khi output còn mở, nhận hoạt động khi input còn mở.

Khi `opening` thành công, kết quả là một `WebSocket` có listener liên kết. Trong một event-driven app, dùng composition/callback thay vì gọi `join()` ngay tại UI/event-loop thread.

### 1.2. Message khác frame, phần tử callback khác message

WebSocket phân biệt **Text message** và **Binary message**. Một message có thể được truyền thành nhiều **frame** trên wire. Java API mô tả dữ liệu gửi bằng một hoặc nhiều lần gọi `sendText/sendBinary` với `last`, nhưng code ứng dụng **không nên dựa vào việc mỗi lệnh gửi đồng nghĩa đúng một packet TCP hoặc đúng một lần callback nhận**.

Listener có thể nhận dữ liệu bằng nhiều callback:

~~~java
CompletionStage<?> onText(
        WebSocket webSocket, CharSequence data, boolean last);

CompletionStage<?> onBinary(
        WebSocket webSocket, ByteBuffer data, boolean last);
~~~

Ở phía **nhận**, `last` báo phần dữ liệu callback này đã kết thúc message logic hay chưa. Nếu `last == false`, hãy tích lũy đoạn dữ liệu cho đến khi nhận `last == true`. Callback nhận **không đồng nhất** với send future ở phía gửi và có thể được tách/gộp khác với cách ứng dụng gửi.

## 2. sendText(CharSequence data, boolean last)

### 2.1. Gửi message text hoàn chỉnh

~~~java
CompletableFuture<WebSocket> sent =
        ws.sendText("Xin chào Java 11", true);
~~~

- `data` là `CharSequence` (thường sử dụng một `String` không thay đổi).
- `last = true`: lần gọi kết thúc **text message hiện tại**. Nếu trước đó không có text fragment đang mở, đây là một message hoàn chỉnh.
- `sent` hoàn tất bình thường khi thao tác gửi của WebSocket hoàn thành. Nó trả chính đối tượng socket `WebSocket` để có thể chain tiếp.
- Không sửa nguồn `CharSequence` khi thao tác đang pending. `StringBuilder`/`StringBuffer` là mutable, nên ưu tiên chụp thành `String` bất biến nếu dữ liệu được chia sẻ giữa các thread.

Text được trao đổi trên WebSocket theo **UTF-8** trên wire theo giao thức WebSocket. Java mã hóa từ chuỗi UTF-16 của `String/CharSequence`; không tự biến text thành bytes Latin-1 rồi gọi `sendText` để «chọn charset». Nếu giao thức ứng dụng cần binary riêng, dùng `sendBinary`.

### 2.2. Chuỗi tiếng Việt và Unicode bổ sung

~~~java
String text = "Tiếng Việt " + new String(
        Character.toChars(0x1F642));

CompletableFuture<WebSocket> result = ws.sendText(text, true);
~~~

Đây là đoạn minh họa trong một scope có `ws`. U+1F642 là ký tự Unicode ngoài BMP, dùng **hai UTF-16 code units** trong Java `String` nhưng **bốn byte UTF-8** trên wire. Java 11 xử lý một chuỗi hợp lệ; không dùng `String.length()` để suy ra số byte WebSocket sẽ truyền.

Một `CharSequence` có surrogate đơn lẻ không hợp lệ (**malformed UTF-16**) có thể khiến future gửi thất bại với `IOException` theo ghi chú implementation của Javadoc. Đừng cắt đôi surrogate pair khi chia text thành fragment; một `String` hợp lệ có thể được tạo bằng `Character.toChars(codePoint)` hoặc được nhận từ nguồn text đã validate.

### 2.3. Gửi text thành nhiều phần

~~~java
CompletableFuture<WebSocket> completeText =
        ws.sendText("Xin ", false)
          .thenCompose(socket -> socket.sendText("chào", true));
~~~

**Ý nghĩa:**

1. `sendText("Xin ", false)` bắt đầu một **text message chưa kết thúc**.
2. Chỉ **sau khi thao tác gửi phần đầu hoàn tất**, `thenCompose` gọi `sendText("chào", true)`.
3. `last=true` kết thúc **cùng text message**; phía nhận phải ghép ra `"Xin chào"`.
4. Giữa hai lần gọi này, **không** gửi một binary message độc lập để xen vào giữa text fragments.

Từ **`false` không có nghĩa «gửi một message và chờ message khác»**; nó nói message logic hiện tại **chưa hoàn tất**. Nếu không gửi phần cuối với `last=true`, ứng dụng để message dang dở và không thể chuyển sang loại đối lập hợp lệ. Không để open fragment kéo dài vô hạn trong hệ thống thật.

## 3. sendBinary(ByteBuffer data, boolean last)

### 3.1. Gửi một binary message hoàn chỉnh

~~~java
ByteBuffer buffer = ByteBuffer.wrap(
        new byte[] {0, (byte) 0xFF, 65});

CompletableFuture<WebSocket> sent =
        ws.sendBinary(buffer, true);
~~~

`sendBinary` gửi **những bytes hiện có giữa `buffer.position()` (bao gồm) và `buffer.limit()` (không bao gồm)**. Mảng gốc chứa byte âm theo kiểu `byte` Java không có nghĩa payload bị thay đổi: `(byte)0xFF` vẫn là octet có bit pattern FF.

Theo Javadoc:

- **Không truy cập hoặc thay đổi `ByteBuffer` khi send future chưa hoàn tất**. Điều này bao gồm cả position/limit và dữ liệu bên dưới buffer.
- Khi future hoàn tất **bình thường**, `ByteBuffer` **không còn remaining bytes** (`position == limit`). Vì vậy đừng tái sử dụng nó mà chưa chuẩn bị lại vị trí một cách rõ ràng.
- Nếu thao tác thất bại, không được mặc định buffer còn ở position ban đầu hoặc đã được gửi đủ.
- `sendBinary` **không tự biến bytes thành text/JSON**; ứng dụng phải tự định nghĩa nội dung và framing của payload nhị phân.

### 3.2. Chỉ gửi một phạm vi của ByteBuffer

~~~java
byte[] raw = {99, 0, (byte) 0xFF, 88};

ByteBuffer slice = ByteBuffer.wrap(raw);
slice.position(1);
slice.limit(3);

CompletableFuture<WebSocket> sent = ws.sendBinary(slice, true);

// Chỉ SAU KHI sent hoàn tất bình thường:
// slice.hasRemaining() == false; hai bytes gửi là 00 FF.
~~~

Trên wire chỉ có **`00 FF`**, không có `63` ở đầu và `58` ở cuối. Đây là **phạm vi ByteBuffer**, khác với overload HTTP `BodyPublishers.ofByteArray(buf, offset, length)`: ở đây không có các tham số offset/length; bạn điều chỉnh `position`/`limit` của buffer.

Nếu cần giữ cursor của buffer nguồn, tạo `duplicate()` hoặc `slice()` theo yêu cầu. **Cẩn thận:** `duplicate/slice` chia sẻ vùng nhớ byte bên dưới, nên **không** cho thread khác sửa mảng/ByteBuffer gốc trong lúc dữ liệu vẫn đang được gửi. Nếu cần snapshot độc lập, sao chép bytes vào một buffer mới trước khi send.

### 3.3. Gửi binary thành nhiều phần

~~~java
CompletableFuture<WebSocket> binaryMessage =
        ws.sendBinary(ByteBuffer.wrap(new byte[]{1, 2}), false)
          .thenCompose(socket -> socket.sendBinary(
                  ByteBuffer.wrap(new byte[]{3}), true));
~~~

Đây là **một binary message logic** gồm các byte `01 02 03`, không phải hai message riêng. Khi fragment đầu tiên chưa kết thúc, không được gửi text message xen vào; hoàn thành binary với `last=true` trước rồi mới đổi sang `sendText(...)`.

Không dựa vào một callback `onBinary` duy nhất bên nhận: listener có thể nhận nhiều đoạn với `last` khác nhau và phải ghép nếu cần kiểm chứng **toàn message**.

## 4. Thứ tự gửi: vì sao CompletableFuture.thenCompose quan trọng?

### 4.1. Một send operation đang pending

Javadoc `WebSocket` định nghĩa: một send operation đã khởi tạo nhưng future chưa hoàn tất là **pending**. Với `sendText` và `sendBinary`, future có thể hoàn tất exceptionally với **`IllegalStateException`** nếu một thao tác gửi text/binary khác vẫn đang pending.

Ví dụ không nên dùng khi cần thứ tự:

~~~java
CompletableFuture<WebSocket> a = ws.sendText("first", true);
CompletableFuture<WebSocket> b = ws.sendBinary(
        ByteBuffer.wrap(new byte[]{1, 2}), true);
~~~

Hai dòng **khởi tạo độc lập**; `b` không đợi `a` hoàn tất. Tùy thời điểm, `b` có thể gặp pending send và thất bại. Ngay cả trong trường hợp test ngẫu nhiên không xảy ra lỗi, code vẫn không thể hiện một hợp đồng sắp xếp thứ tự an toàn.

**Không** sửa bằng `CompletableFuture.allOf(a, b)`: `allOf` chỉ đợi cả hai future đã được khởi tạo, **không** áp thứ tự khởi tạo hay giải quyết xung đột pending.

### 4.2. Nối phụ thuộc bằng thenCompose

~~~java
CompletableFuture<WebSocket> ordered =
        CompletableFuture.completedFuture(ws)
            .thenCompose(socket -> socket.sendText("first", true))
            .thenCompose(socket -> socket.sendBinary(
                    ByteBuffer.wrap(new byte[]{1, 2}), true))
            .thenCompose(socket -> socket.sendText("third", true));
~~~

- Stage thứ hai chỉ **bắt đầu** sau khi stage gửi text đầu tiên thành công.
- Stage thứ ba chỉ **bắt đầu** sau khi binary gửi xong.
- Tất cả sử dụng **cùng socket** do future trước trả về.
- Nếu một stage thất bại, các `thenCompose` phía sau **không tự chạy**; future `ordered` hoàn tất exceptionally.
- `ordered` hoàn tất khi thao tác gửi cuối đã hoàn tất ở client; **không** chứng minh phía server đã xử lý xong message.

Đây là một cách diễn đạt **thứ tự chủ đích trong code**, không phải tuyên bố rằng tất cả server WebSocket cần xử lý nghiệp vụ đồng bộ, hay mọi future completions luôn song song/không dùng thread nào.

### 4.3. Vì sao thenApply dễ nhầm?

~~~java
// Sai kiểu kết quả khi muốn flatten:
CompletableFuture<CompletableFuture<WebSocket>> nested =
        CompletableFuture.completedFuture(ws)
                .thenApply(socket -> socket.sendText("hello", true));
~~~

`thenApply` ở đây trả về **future lồng trong future**. `thenCompose` là phép làm phẳng đúng khi lambda trả thêm một `CompletionStage`. Đối với chuỗi gửi theo thứ tự, dùng `thenCompose` thay vì tự giải quyết nested future.

### 4.4. Gửi từ nhiều producer/thread

Một chain `thenCompose` cục bộ chỉ sắp xếp các bước **trong chain đó**. Nếu producer A và B cùng có quyền gọi `ws.sendText` trực tiếp, cả hai vẫn có thể tạo thao tác pending chồng nhau.

Mô hình nên chọn:

1. **Một chủ sở hữu outbound** cho từng `WebSocket`: một event loop, actor hoặc sender dispatcher chịu trách nhiệm sắp thứ tự.
2. Producer khác đưa **message hoàn chỉnh** vào hàng đợi bounded của sender; không gọi API gửi đồng thời trực tiếp.
3. Sender lấy message theo thứ tự nghiệp vụ, gọi `sendText/sendBinary` và **chờ future hoàn tất** trước khi lấy send tiếp theo, hoặc duy trì chuỗi future được cập nhật **một cách thread-safe**.
4. Nếu một message có fragments, sender phải **giữ quyền sở hữu cả message** cho tới fragment `last=true`, không để message của producer khác chen giữa.
5. Khi send thất bại, áp chính sách rõ: dừng, retry theo protocol/idempotency, drop với lỗi, hoặc đóng socket; **không nuốt lỗi và tiếp tục gửi như chưa có gì**.
6. Hạn chế queue theo **số message và tổng bytes**, phân biệt backpressure với việc tạo vô hạn `CompletableFuture`/ByteBuffer trên heap.

Một cách minh họa về chain dùng chung:

~~~java
// Đoạn minh họa cấu trúc: chỉ sender thread được sửa tail.
CompletableFuture<WebSocket> tail =
        CompletableFuture.completedFuture(ws);

tail = tail.thenCompose(s -> s.sendText("A", true));
tail = tail.thenCompose(s -> s.sendBinary(
        ByteBuffer.wrap(new byte[]{1}), true));
~~~

Nếu tail bị **nhiều luồng đọc/ghi không đồng bộ hóa**, lại xuất hiện race/lost update ngay trong ứng dụng. `CompletableFuture` thread-safe ở trạng thái hoàn tất **không** biến biến `tail` hay dữ liệu queue tùy ý thành transaction thread-safe. Có thể dùng `AtomicReference` với CAS đúng cách hoặc tốt hơn dùng **single-owner queue** để dễ kiểm soát thứ tự, limits và lifecycle.

## 5. Hai quy tắc riêng biệt phải cùng đúng

Lỗi pending và lỗi phân mảnh là **hai điều kiện khác nhau**.

### 5.1. Pending send: thao tác trước chưa xong

~~~text
sendText("A", true)  ---- future pending ----> completed
       |
       +--- gọi sendBinary ngay tại đây: có thể fail (pending)
~~~

Ngay cả khi `last=true`, send future có thể vẫn pending do phải đưa bytes ra mạng. Hãy chain hoặc đợi future, không suy ra thao tác xong chỉ vì phương thức đã trả về đối tượng future.

### 5.2. Unfinished message: fragment chưa có last=true

~~~text
sendText("A", false) ---- completed
sendBinary(bytes, true)   -> IllegalStateException (text message dang dở)
sendText("B", true)       -> hoàn thành text message "AB"
~~~

**Đợi future của `sendText("A", false)` hoàn tất vẫn chưa đủ** để chuyển sang binary: message text đang dang dở do `last=false`. Cần gửi tiếp **text** với `last=true` trước.

Chiều ngược lại cũng vậy:

~~~text
sendBinary(part1, false) -> binary message dang dở
sendText("X", true)      -> IllegalStateException
sendBinary(part2, true)  -> hoàn tất binary message
~~~

Theo Javadoc Java 11, các trường hợp sai này được biểu diễn bằng **future gửi hoàn tất exceptionally**; thường khi `join()` bạn sẽ thấy `CompletionException` bọc `IllegalStateException`. Không nên kiểm thử bằng cách chỉ mong phương thức ném trực tiếp một exception tại đúng dòng gọi, vì một lỗi bất đồng bộ có thể xuất hiện trên future.

### 5.3. Sự kiện control và thứ tự

`WebSocket.sendPing`, `sendPong` và `sendClose` là các phương thức khác với send text/binary. WebSocket protocol có quy tắc riêng cho **control frames**, có thể xử lý Ping/Pong xen kẽ fragments ở tầng giao thức. Bởi vậy không đồng nhất «không được chen text/binary message» với «không control frame nào được phép xuất hiện».

Trong Java 11, `sendPing`/`sendPong` giới hạn payload **125 bytes** và có những hạn chế pending riêng. `sendClose(WebSocket.NORMAL_CLOSURE, "")` mở quá trình đóng **output**, không đồng nghĩa đã đợi bên kia đóng input. Khi yêu cầu strict ordering ở tầng ứng dụng, vẫn nên điều phối outbound send/control/close qua chính sách thống nhất.

## 6. Future đã hoàn tất có nghĩa server đã xử lý chưa?

Không. Hợp đồng `sendText/sendBinary` là future hoàn tất khi thao tác **gửi** đã hoàn tất ở client WebSocket. Điều đó **không phải ACK nghiệp vụ** từ server và không bảo đảm server đã parse, ghi database, phát event hoặc lưu bền vững.

Sơ đồ:

~~~text
Client                                 Server
sendText(...)
  |
  +-- send future completed
  |   (client send operation succeeded)
  |
  +-------------------------------> onMessage(...)
                                      |
                                      +-- business processing
                                      |
        <-----------------------------+-- application ACK (if defined)
  |
  +-- receive listener ACK
      => application knows server acknowledged according to protocol
~~~

Nếu ứng dụng cần **at-least-once**, **at-most-once**, ack timeout, retry hay bảo toàn thứ tự nghiệp vụ qua reconnect, phải định nghĩa **message ID**, ACK, deduplication và thứ tự theo phiên. TCP/WebSocket cung cấp luồng ordered **trong một kết nối đang sống**, nhưng không thay thế độ bền nghiệp vụ, xử lý lại sau mất mạng, hoặc thứ tự giữa các kết nối/reconnect.

Không coi `send...().join()` là lời bảo đảm giao dịch thành công ở server. Đừng retry message có tác dụng phụ một cách mù quáng sau timeout/lỗi send nếu server có thể đã nhận.

## 7. Ví dụ runnable Java 11: echo WebSocket thực bằng RFC 6455 trên loopback

Để test **sendText/sendBinary thật** mà không cần dịch vụ Internet, ta khởi động một server tối giản dựa trên `ServerSocket`, thực hiện HTTP Upgrade/WebSocket handshake và đọc frame WebSocket client. Server này:

- Chỉ lắng nghe `127.0.0.1`, port hệ điều hành tự chọn.
- Đọc `Sec-WebSocket-Key`, tính `Sec-WebSocket-Accept` từ SHA-1 + GUID theo WebSocket handshake.
- Đọc **client frame có masking**, mở masking và ghép text/binary fragments.
- Echo mỗi **message logic** thành một frame không masked do server gửi.
- Phản hồi Close frame để client có thể kiểm graceful close.
- Chỉ hỗ trợ payload **nhỏ, đúng định dạng** phục vụ test; không được dùng trực tiếp làm WebSocket server production.

**Lý do có server code tương đối dài:** Java 11 cung cấp **WebSocket client**, nhưng không có một WebSocket server đầy đủ tương ứng trong `java.net.http`. Mẫu loopback này bảo đảm người học có thể chạy test từ một file Java 11 duy nhất, không cài dependency hay cần mạng ngoài.

### 7.1. Kịch bản kiểm thử

| Case | Thao tác gửi | Kỳ vọng |
| --- | --- | --- |
| Unicode | `sendText(TEXT, true)` | Echo đúng tiếng Việt và U+1F642 |
| Binary range | `sendBinary(slice,true)` với position 1, limit 3 | Chỉ nhận bytes `00 FF`; buffer hết remaining khi send complete |
| Text fragments | `sendText("hello ",false)` rồi `sendText("world",true)` | Một text message `"hello world"` |
| Binary fragments | `sendBinary([01,02],false)` rồi `sendBinary([03],true)` | Một binary message `01 02 03` |
| Sai thứ tự loại | Text `"open-"` với `last=false` rồi thử binary | Binary send future lỗi `IllegalStateException` |
| Hồi phục hợp lệ | `sendText("end",true)` tiếp sau lỗi, rồi text `"after"` | Nhận hai text messages riêng `"open-end"`, `"after"` |
| Tổng thứ tự | Server echo theo cùng connection | Danh sách nhận đúng thứ tự sáu message |
| Đóng | `sendClose(1000,"")`, nhận `onClose` | Close handshake hoàn tất trong test |

**File: WebSocketSendOrderDemo.java**

~~~java
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.InetAddress;
import java.net.ServerSocket;
import java.net.Socket;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.WebSocket;
import java.nio.ByteBuffer;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.time.Duration;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Base64;
import java.util.List;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionException;
import java.util.concurrent.CompletionStage;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicReference;

public class WebSocketSendOrderDemo {
    private static final String TEXT =
            "Ti\u1EBFng Vi\u1EC7t " + new String(Character.toChars(0x1F642));
    private static final String GUID =
            "258EAFA5-E914-47DA-95CA-C5AB0DC85B11";

    private static void check(boolean ok, String label) {
        if (!ok) throw new AssertionError(label);
    }

    private static String hex(byte[] data) {
        StringBuilder out = new StringBuilder();
        for (byte value : data) {
            if (out.length() > 0) out.append(' ');
            int b = value & 255;
            out.append(Character.forDigit(b >>> 4, 16));
            out.append(Character.forDigit(b & 15, 16));
        }
        return out.toString().toUpperCase(java.util.Locale.ROOT);
    }

    private static byte[] readExactly(InputStream in, int size)
            throws IOException {
        byte[] data = in.readNBytes(size);
        if (data.length != size) throw new IOException("Truncated frame");
        return data;
    }

    private static long readLength(InputStream in, int marker)
            throws IOException {
        if (marker < 126) return marker;
        int n = marker == 126 ? 2 : 8;
        byte[] bytes = readExactly(in, n);
        long length = 0;
        for (byte b : bytes) length = (length << 8) | (b & 255);
        return length;
    }

    private static final class Frame {
        final int opcode;
        final boolean last;
        final byte[] data;
        Frame(int opcode, boolean last, byte[] data) {
            this.opcode = opcode;
            this.last = last;
            this.data = data;
        }
    }

    private static Frame readFrame(InputStream in) throws IOException {
        int first = in.read();
        if (first < 0) return null;
        int second = in.read();
        if (second < 0) throw new IOException("Truncated frame header");
        boolean last = (first & 128) != 0;
        int opcode = first & 15;
        boolean masked = (second & 128) != 0;
        long length = readLength(in, second & 127);
        if (!masked || length > 1_000_000)
            throw new IOException("Expected small masked client frame");
        byte[] mask = readExactly(in, 4);
        byte[] payload = readExactly(in, (int) length);
        for (int i = 0; i < payload.length; i++)
            payload[i] ^= mask[i & 3];
        return new Frame(opcode, last, payload);
    }

    private static void sendFrame(OutputStream out, int opcode, byte[] data)
            throws IOException {
        if (data.length > 125) throw new IOException("Test echo too large");
        out.write(128 | opcode);
        out.write(data.length);
        out.write(data);
        out.flush();
    }

    private static void handshake(InputStream in, OutputStream out)
            throws Exception {
        ByteArrayOutputStream received = new ByteArrayOutputStream();
        int state = 0;
        while (state < 4 && received.size() < 8192) {
            int next = in.read();
            if (next < 0) throw new IOException("Handshake closed");
            received.write(next);
            if ((state == 0 || state == 2) && next == 13) state++;
            else if ((state == 1 || state == 3) && next == 10) state++;
            else state = next == 13 ? 1 : 0;
        }
        if (state != 4) throw new IOException("Invalid handshake");
        String headers = received.toString(StandardCharsets.US_ASCII.name());
        String key = null;
        for (String line : headers.split("\r\n")) {
            if (line.toLowerCase(java.util.Locale.ROOT)
                    .startsWith("sec-websocket-key:")) {
                key = line.substring(line.indexOf(':') + 1).trim();
            }
        }
        if (key == null) throw new IOException("No WebSocket key");
        byte[] hash = MessageDigest.getInstance("SHA-1").digest(
                (key + GUID).getBytes(StandardCharsets.US_ASCII));
        String accept = Base64.getEncoder().encodeToString(hash);
        String response = "HTTP/1.1 101 Switching Protocols\r\n"
                + "Upgrade: websocket\r\n"
                + "Connection: Upgrade\r\n"
                + "Sec-WebSocket-Accept: " + accept + "\r\n\r\n";
        out.write(response.getBytes(StandardCharsets.US_ASCII));
        out.flush();
    }

    private static void serve(Socket socket) throws Exception {
        socket.setSoTimeout(10000);
        InputStream in = socket.getInputStream();
        OutputStream out = socket.getOutputStream();
        handshake(in, out);
        ByteArrayOutputStream message = new ByteArrayOutputStream();
        int messageType = 0;
        for (;;) {
            Frame frame = readFrame(in);
            if (frame == null) return;
            if (frame.opcode == 8) {
                sendFrame(out, 8, frame.data);
                return;
            }
            if (frame.opcode == 9) {
                sendFrame(out, 10, frame.data);
                continue;
            }
            if (frame.opcode == 10) continue;
            if (frame.opcode == 1 || frame.opcode == 2) {
                check(messageType == 0, "Interleaved messages on wire");
                messageType = frame.opcode;
            } else if (frame.opcode != 0 || messageType == 0) {
                throw new IOException("Unexpected continuation");
            }
            message.write(frame.data);
            if (frame.last) {
                sendFrame(out, messageType, message.toByteArray());
                message.reset();
                messageType = 0;
            }
        }
    }

    private static final class Events implements WebSocket.Listener {
        final CountDownLatch received = new CountDownLatch(6);
        final CountDownLatch closed = new CountDownLatch(1);
        final List<String> messages =
                java.util.Collections.synchronizedList(new ArrayList<>());
        final AtomicReference<Throwable> failure = new AtomicReference<>();
        final StringBuilder text = new StringBuilder();
        final ByteArrayOutputStream binary = new ByteArrayOutputStream();

        @Override
        public void onOpen(WebSocket ws) {
            ws.request(1);
        }

        @Override
        public CompletionStage<?> onText(WebSocket ws, CharSequence data,
                                         boolean last) {
            text.append(data);
            if (last) {
                messages.add("T:" + text.toString());
                text.setLength(0);
                received.countDown();
            }
            ws.request(1);
            return CompletableFuture.completedFuture(null);
        }

        @Override
        public CompletionStage<?> onBinary(WebSocket ws, ByteBuffer data,
                                           boolean last) {
            byte[] piece = new byte[data.remaining()];
            data.get(piece);
            binary.write(piece, 0, piece.length);
            if (last) {
                messages.add("B:" + hex(binary.toByteArray()));
                binary.reset();
                received.countDown();
            }
            ws.request(1);
            return CompletableFuture.completedFuture(null);
        }

        @Override
        public CompletionStage<?> onClose(WebSocket ws, int code,
                                          String reason) {
            closed.countDown();
            return CompletableFuture.completedFuture(null);
        }

        @Override
        public void onError(WebSocket ws, Throwable error) {
            failure.compareAndSet(null, error);
        }
    }

    public static void main(String[] args) throws Exception {
        try (ServerSocket server = new ServerSocket(
                0, 1, InetAddress.getByName("127.0.0.1"))) {
            AtomicReference<Throwable> serverError = new AtomicReference<>();
            Thread echoThread = new Thread(() -> {
                try (Socket socket = server.accept()) {
                    serve(socket);
                } catch (Throwable failure) {
                    serverError.set(failure);
                }
            }, "local-websocket-echo");
            echoThread.start();

            WebSocket ws = null;
            try {
                Events listener = new Events();
                HttpClient http = HttpClient.newHttpClient();
                ws = http.newWebSocketBuilder()
                        .connectTimeout(Duration.ofSeconds(4))
                        .buildAsync(URI.create("ws://127.0.0.1:"
                                        + server.getLocalPort() + "/echo"),
                                    listener)
                        .orTimeout(5, TimeUnit.SECONDS).join();

                ByteBuffer slice = ByteBuffer.wrap(
                        new byte[]{99, 0, (byte) 255, 88});
                slice.position(1);
                slice.limit(3);
                ByteBuffer part1 = ByteBuffer.wrap(new byte[]{1, 2});
                ByteBuffer part2 = ByteBuffer.wrap(new byte[]{3});

                CompletableFuture<WebSocket> ordered =
                        CompletableFuture.completedFuture(ws)
                        .thenCompose(s -> s.sendText(TEXT, true))
                        .thenCompose(s -> s.sendBinary(slice, true))
                        .thenCompose(s -> s.sendText("hello ", false))
                        .thenCompose(s -> s.sendText("world", true))
                        .thenCompose(s -> s.sendBinary(part1, false))
                        .thenCompose(s -> s.sendBinary(part2, true));
                ordered.orTimeout(5, TimeUnit.SECONDS).join();
                check(!slice.hasRemaining() && !part1.hasRemaining()
                        && !part2.hasRemaining(),
                        "sendBinary must consume ByteBuffer");
                System.out.println("PASS ordered text/binary futures");
                System.out.println("PASS sendBinary buffer range");
                System.out.println("PASS fragmented text and binary");

                ws.sendText("open-", false).join();
                boolean rejected = false;
                try {
                    ws.sendBinary(ByteBuffer.wrap(new byte[]{55}), true).join();
                } catch (CompletionException expected) {
                    rejected = expected.getCause()
                            instanceof IllegalStateException;
                }
                check(rejected, "binary cannot interrupt text fragments");
                ws.sendText("end", true).join();
                System.out.println("PASS illegal mixed fragments rejected");

                ws.sendText("after", true).join();
                check(listener.received.await(5, TimeUnit.SECONDS),
                        "all six echo messages received");
                check(listener.failure.get() == null, "listener failed");
                List<String> expected = Arrays.asList(
                        "T:" + TEXT, "B:00 FF", "T:hello world",
                        "B:01 02 03", "T:open-end", "T:after");
                check(expected.equals(new ArrayList<>(listener.messages)),
                        "message order and contents");
                System.out.println("PASS echo message ordering and UTF-8");

                ws.sendClose(WebSocket.NORMAL_CLOSURE, "")
                        .orTimeout(5, TimeUnit.SECONDS).join();
                check(listener.closed.await(5, TimeUnit.SECONDS),
                        "close response received");
                System.out.println("PASS graceful close handshake");

                echoThread.join(2000);
                check(serverError.get() == null,
                        "server failed: " + serverError.get());
                System.out.println("ALL WEBSOCKET SEND TESTS PASSED");
            } finally {
                if (ws != null && !ws.isOutputClosed()) ws.abort();
            }
        }
    }
}
~~~

### 7.2. Biên dịch và chạy

Lưu thành file `WebSocketSendOrderDemo.java` trong một thư mục có quyền ghi, dùng **JDK 11** (hoặc JDK mới biên dịch target Java 11):

~~~bash
javac --release 11 -encoding UTF-8 WebSocketSendOrderDemo.java
java WebSocketSendOrderDemo
~~~

**Không cần dependency ngoài JDK.** Chương trình dùng `ServerSocket`/`MessageDigest`/`Base64` để test handshake trên loopback và `java.net.http.WebSocket` làm client thật.

Đầu ra chính xác khi mọi assertion thành công:

~~~text
PASS ordered text/binary futures
PASS sendBinary buffer range
PASS fragmented text and binary
PASS illegal mixed fragments rejected
PASS echo message ordering and UTF-8
PASS graceful close handshake
ALL WEBSOCKET SEND TESTS PASSED
~~~

Phân tích:

1. Client kết nối tới echo server qua `buildAsync`.
2. Một chuỗi `thenCompose` gửi lần lượt **text Unicode**, **binary `00 FF`**, một **text message hai fragments** và một **binary message hai fragments**.
3. Sau khi send future hoàn tất, `slice`, `part1`, `part2` đều không còn remaining bytes. Code **không** đọc các buffer này khi tương lai của send đang pending.
4. Test bắt đầu một text message `"open-"` với `last=false`. Gọi `sendBinary(...)` ở thời điểm này không hợp lệ **dù send text trước đã hoàn tất**; result future thất bại với `IllegalStateException`. Sau đó tiếp tục `sendText("end",true)` để kết thúc text message.
5. Test gửi thêm `"after"` và chờ đủ sáu message echo. Listener ghép phần nhận qua `onText/onBinary`, rồi so sánh **đúng cả thứ tự và nội dung**: không chỉ kiểm futures hoàn tất.
6. `sendClose(NORMAL_CLOSURE, "")` khởi tạo close handshake; client còn đợi `onClose` phản hồi trong bài test, không suy luận send-close future bằng việc đóng cả hai phía tức thì.

### 7.3. Giới hạn an toàn của test server

Server tự viết này **chỉ là fixture học tập** để kiểm thử client WebSocket:

- Hạn chế frame gửi từ server ở **125 bytes**, giới hạn frame nhận từ client **1 MiB**, chưa có toàn bộ logic kiểm định RFC 6455, giới hạn message tích lũy qua các fragments, protocol extensions hay protection của một server công khai.
- Dùng SHA-1 **chỉ để thực hiện đúng bước `Sec-WebSocket-Accept` của WebSocket handshake RFC 6455**, **không** dùng SHA-1 làm chữ ký/mã hóa bảo mật của ứng dụng.
- Không TLS, không xác thực, không authorization, không origin/access checks, không rate limiting và không multi-client; chỉ lắng nghe loopback.
- Mục đích kiểm **client Java 11** gửi frame đã mask, server mở mask và echo. Tránh copy server này vào production hoặc công bố port trên Internet.
- Với dự án thật, dùng WebSocket server/framework được duy trì, có kiểm thử bảo mật và vận hành. Client Java `java.net.http.WebSocket` có thể làm việc với server chuẩn tương thích.

## 8. Phía nhận: listener, demand và fragment reassembly

`WebSocket.Listener` xử lý dữ liệu qua các phương thức `onText` và `onBinary`. Ngoài ý nghĩa `last`, cần biết `webSocket.request(n)` là **demand cho số lần gọi receive method**, **không** phải số message và không phải số byte. Mỗi callback nhận có thể cung cấp một phần của message lớn.

Một mẫu listener ngắn:

~~~java
final class TextListener implements WebSocket.Listener {
    private final StringBuilder assembled = new StringBuilder();

    @Override
    public void onOpen(WebSocket socket) {
        socket.request(1);
    }

    @Override
    public CompletionStage<?> onText(WebSocket socket,
                                     CharSequence data, boolean last) {
        assembled.append(data);
        if (last) {
            String completeMessage = assembled.toString();
            assembled.setLength(0);
            // Đưa completeMessage sang xử lý nghiệp vụ phù hợp.
        }
        socket.request(1);
        return CompletableFuture.completedFuture(null);
    }
}
~~~

Đây là **đoạn lớp minh họa**, cần imports và không có `main`. Phương thức `onText` trả một `CompletionStage` cho phép WebSocket biết khi nào có thể reclaim `CharSequence` đã giao. **Không giữ tham chiếu tới `CharSequence/ByteBuffer` và đọc nó sau khi stage đã hoàn tất**; copy nội dung ngay hoặc giữ stage chưa complete đến khi xử lý xong theo hợp đồng.

- Listener callbacks cho **cùng WebSocket** được gọi theo trật tự tuần tự; callback của **các WebSocket khác nhau** có thể chạy đồng thời.
- `request(1)` thường là điểm khởi đầu dễ hiểu, nhưng nếu bạn gọi tiếp trước khi xử lý dữ liệu thực sự xong, ứng dụng vẫn có thể xếp nhiều việc lên queue phía sau.
- `onClose` và `onError` là terminal situations; quản lý buffer/message dang dở và future chờ ACK theo policy.
- `sendText/sendBinary` thuộc **output side**, còn `request(n)` điều chỉnh **input side**; hai cơ chế khác nhau, không xem `request(1)` là «cho phép một lần send».

## 9. Xử lý lỗi và kiểm soát vòng đời

### 9.1. Ngoại lệ và future

| Tình huống | Hành vi cần xử lý |
| --- | --- |
| Gọi `sendText/sendBinary` khi thao tác text/binary khác pending. | Future có thể complete exceptionally với `IllegalStateException`. |
| Gọi `sendBinary` khi text message trước chưa `last=true`; hoặc chiều ngược lại. | Future có thể complete exceptionally với `IllegalStateException`. |
| Gửi text có malformed UTF-16. | Future lỗi `IOException` theo ghi chú implementation. |
| I/O lỗi hoặc output đã đóng. | Future có thể lỗi `IOException`. |
| Truyền `null` làm data. | API quy định lỗi `NullPointerException`. |
| Hủy/abort connection, reconnect. | Các thao tác gửi/nhận có thể thất bại; cần thiết kế hành vi dọn dẹp và tái gửi theo ứng dụng. |
| Gọi `sendClose` mã/reason không hợp lệ. | `IllegalArgumentException` theo hợp đồng; ví dụ bình thường dùng `NORMAL_CLOSURE=1000`. |

Nên xử lý bất đồng bộ:

~~~java
CompletableFuture<WebSocket> sent =
        ws.sendText("message", true);

sent.whenComplete((socket, error) -> {
    if (error != null) {
        // Ghi log nguyên nhân không chứa dữ liệu bí mật,
        // đóng/dọn dẹp hoặc báo lại nghiệp vụ theo policy.
    }
});
~~~

Đoạn minh họa này quan sát outcome; `whenComplete` **không** tự biến lỗi thành thành công. Nếu dùng `sent.join()` trong test/CLI, ngoại lệ bất đồng bộ thường được bọc trong `CompletionException`; xem `getCause()`.

Không nên viết `exceptionally(error -> ws)` chỉ để che lỗi send rồi thực hiện các send tiếp theo như thể chắc chắn đã giao dữ liệu: một message có thể gửi được một phần hoặc không rõ đã được server nhận chưa.

### 9.2. Đóng output và input

~~~java
CompletableFuture<WebSocket> closing =
        ws.sendClose(WebSocket.NORMAL_CLOSURE, "");
~~~

`sendClose` đóng **output side** sau close operation theo hợp đồng, nhưng input side có thể còn mở cho đến khi nhận Close từ peer, `abort()` hoặc lỗi. Do đó nếu cần graceful close, thường chờ close response/`onClose` theo timeout. Khi hết thời gian hoặc có lỗi nghiêm trọng, `ws.abort()` đóng đột ngột cả input/output, có thể làm mất message chưa hoàn tất.

Một application thường cần:

- Không nhận thêm message mới để gửi khi đã bắt đầu closing.
- Xử lý xong hoặc báo thất bại cho các message outbound còn pending theo chính sách.
- Gửi Close frame theo mã đúng; cho peer thời gian phản hồi; sau deadline thì abort nếu cần.
- Dọn dẹp queue, buffer, timeout, listener state và nguồn lực liên quan.

### 9.3. Không tạo queue vô hạn khi server chậm

Giả sử producer tạo 100.000 message/giây trong khi WebSocket chỉ phát được 1.000 message/giây. Một chain tương lai dài vô hạn **vẫn có thể giữ toàn bộ message và ByteBuffer trong bộ nhớ**, dù từng send được sắp thứ tự.

Đặt **hạn mức số message đang chờ và tổng bytes**, chọn chính sách quá tải: reject sớm, drop theo loại sự kiện, block producer ở nơi phù hợp hoặc ghi ra hàng đợi bền vững được quản lý. Với UI/event-loop, tránh blocking trực tiếp. Nên đo **queue depth, age, send latency, failed sends, reconnect count và ACK latency** nếu nghiệp vụ cần xác nhận phía server.

Một `CompletableFuture` chain là **cơ chế dependency/ordering**, không tự cung cấp **rate limiting, bounded queue, retry đúng ngữ nghĩa hay flow control toàn hệ thống**.

## 10. Những lỗi phổ biến và cách sửa

| Sai lầm | Biểu hiện | Cách làm đúng |
| --- | --- | --- |
| Gọi `sendText` và `sendBinary` độc lập mà không đợi operation trước. | Race/pending `IllegalStateException`. | Nối `thenCompose` hoặc một sender dispatcher có thứ tự. |
| Dùng `allOf` để «bảo đảm thứ tự». | Các send đã khởi tạo đồng thời, có thể xung đột. | `thenCompose` để khởi tạo từng send sau khi trước hoàn tất. |
| Nghĩ `last=false` đã kết thúc message. | Không gửi được loại đối lập, message dang dở. | Gửi fragment cuối **cùng loại** với `last=true`. |
| Xen binary vào text fragments hoặc text vào binary fragments. | `IllegalStateException`. | Giữ quyền sở hữu toàn message tới khi kết thúc. |
| Nghĩ một lần gửi = một TCP packet hay callback phía nhận. | Parser nhận thiếu, xử lý một message nhiều lần. | Dùng `last` ở phía nhận để ghép message. |
| Đọc/sửa `ByteBuffer` khi send đang pending. | Payload không ổn định, race hoặc sai position. | Giữ buffer bất biến tới khi future hoàn tất; copy khi cần. |
| Cho rằng `sendBinary` không thay `position`. | Lần gửi tiếp có body rỗng do remaining == 0. | Theo Javadoc, completion thành công tiêu thụ buffer đến `limit`. |
| Tự dùng `String.length()` làm số bytes UTF-8 của text. | Ước lượng sai dung lượng/giới hạn. | Mã hóa UTF-8 để tính bytes khi cần. |
| Phân mảnh text cắt đôi surrogate pair. | Malformed UTF-16, future gửi lỗi. | Cắt tại ranh giới ký tự/code point hợp lệ. |
| Dùng chung một biến `tail` không đồng bộ giữa nhiều thread. | Lost update, sai thứ tự producer. | Dùng single-owner sender hoặc cập nhật atomic đúng cách. |
| Coi send future thành công là server đã commit. | Mất message nghiệp vụ sau reconnect. | Xây ACK/message ID và retry/dedupe theo yêu cầu. |
| Chặn `join()` trong event-loop/UI. | App đơ khi mạng chậm. | Chain non-blocking; chỉ chờ tại boundary được phép. |
| Gọi `sendClose` rồi giả định input đã đóng. | Resource/lifecycle không khớp. | Chờ `onClose`/timeout, abort khi cần. |
| Dùng `ws://` cho thông tin nhạy cảm qua Internet. | Không có TLS bảo vệ đường truyền. | Dùng `wss://`, xác minh TLS và nguồn endpoint. |
| Dùng raw echo server test làm production. | Không đủ bảo mật/limits/validation. | Chọn server framework chuẩn và duy trì. |
| Retry vô điều kiện sau IOException/timeout. | Có thể gửi trùng message có tác dụng phụ. | Dùng ack, idempotency/message IDs và phân loại lỗi. |

## 11. Câu hỏi tự đánh giá

**1.** `sendText("hello", true)` trả về gì?

**Đáp án:** `CompletableFuture<WebSocket>`. Future hoàn tất khi send operation ở client thành công/thất bại, không phải ACK từ server.

**2.** `sendText("A",false)` đã hoàn tất future. Có thể gọi ngay `sendBinary(...,true)` chưa?

**Đáp án:** Chưa. Text **message logic** vẫn dang dở vì `last=false`. Phải tiếp tục bằng `sendText(...,true)` để kết thúc trước khi chuyển loại.

**3.** Dùng `thenCompose` hay `allOf` để gửi text xong rồi binary đúng thứ tự?

**Đáp án:** `thenCompose`. `allOf` không ép thứ tự khởi tạo send.

**4.** `ByteBuffer.wrap(new byte[]{1,2,3,4})`, đặt `position=1` và `limit=3`, `sendBinary` sẽ gửi bytes nào?

**Đáp án:** `02 03` (hai byte ở index 1 và 2). Sau future hoàn tất bình thường, buffer không còn remaining bytes.

**5.** Vì sao không nên sửa mảng gốc của ByteBuffer trong khi send pending?

**Đáp án:** Buffer tham chiếu vùng dữ liệu còn được đọc để gửi; thay đổi có thể tạo race và payload không như dự định. Giữ ổn định hoặc copy trước.

**6.** Nếu text chứa surrogate đơn lẻ, khi gọi `sendText` sẽ thế nào?

**Đáp án:** Đó là malformed UTF-16. Java WebSocket implementation ghi trong Javadoc rằng future có thể thất bại với `IOException`.

**7.** Listener `onText` nhận `last=false`; đã có một message text hoàn chỉnh chưa?

**Đáp án:** Chưa. Cần ghép các lần callback tiếp theo đến `last=true` mới có trọn message logic.

**8.** `ws.request(1)` cho phép gửi một message đúng không?

**Đáp án:** Không. Đây là demand cho **một lần receive callback** (`onText/onBinary/onPing/onPong/onClose`) trên input, không điều khiển output send.

**9.** `sendClose(1000,"")` hoàn tất nghĩa là WebSocket đã đóng cả hai phía chưa?

**Đáp án:** Không nhất thiết. `sendClose` khởi đầu đóng output; input có thể còn mở cho đến khi nhận Close hoặc abort/lỗi.

**10.** Hai producer cùng gọi `sendText` lên một WebSocket mà không có sender coordinator, có bảo đảm thứ tự theo thời điểm enqueue không?

**Đáp án:** Không. Cần một cơ chế ownership/queue/thread-safe sequencing do ứng dụng thiết kế; bản thân các lời gọi đồng thời có thể gặp pending send.

**11.** `sendText` hoàn thành nghĩa là message đã được ghi database ở server chưa?

**Đáp án:** Không. Nếu nghiệp vụ cần, server phải phát ACK và client phải theo dõi message ID, timeout, retry/dedupe.

**12.** Mục tiêu thật sự của `last` là gì?

**Đáp án:** Đánh dấu lần gửi/callback **hoàn tất message logic**, không phải lời hứa «mỗi lần gọi là một TCP packet» hay timeout.

## 12. Checklist hoàn thành

- [ ] Dùng đúng API `java.net.http.WebSocket` (Since 11), tạo qua `HttpClient.newWebSocketBuilder()`.
- [ ] Phân biệt `sendText(CharSequence, last)` và `sendBinary(ByteBuffer, last)`.
- [ ] Sắp xếp các send operation bằng `thenCompose` hoặc sender single-owner để tránh pending race.
- [ ] Giữ kiểu text/binary đồng nhất đến fragment cuối `last=true`.
- [ ] Không truy cập/sửa `ByteBuffer` trước khi future send hoàn tất; biết buffer hết remaining khi thành công.
- [ ] Dùng `String` hợp lệ và cắt text tại ranh giới code point; nhận thức UTF-16/UTF-8.
- [ ] Dùng listener `onText/onBinary(...,last)` để ghép message phía nhận.
- [ ] Biết `request(n)` thuộc **receive**, không phải lệnh gửi.
- [ ] Xử lý `IllegalStateException`, `IOException`, close, abort và future errors.
- [ ] Giới hạn outbound queue và tách send-complete khỏi application ACK.
- [ ] Dùng `wss://` + TLS phù hợp cho dữ liệu thật; test `ws://127.0.0.1` chỉ trên loopback.
- [ ] Chạy `WebSocketSendOrderDemo.java` bằng `javac --release 11`, xác minh đủ 6 nhóm PASS.

## Tài liệu chính thức

1. [Java SE 11 — WebSocket: sendText/sendBinary, future, pending, last, close, request](https://docs.oracle.com/en/java/javase/11/docs/api/java.net.http/java/net/http/WebSocket.html)
2. [Java SE 11 — WebSocket.Listener: onText/onBinary và last, receive demand](https://docs.oracle.com/en/java/javase/11/docs/api/java.net.http/java/net/http/WebSocket.Listener.html)
3. [Java SE 11 — WebSocket.Builder: buildAsync, connectTimeout](https://docs.oracle.com/en/java/javase/11/docs/api/java.net.http/java/net/http/WebSocket.Builder.html)
4. [Java SE 11 — HttpClient: newWebSocketBuilder](https://docs.oracle.com/en/java/javase/11/docs/api/java.net.http/java/net/http/HttpClient.html)
5. [Java SE 11 — CompletableFuture: thenCompose, completion, exceptionally](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/util/concurrent/CompletableFuture.html)
6. [Java SE 11 — ByteBuffer: position/limit/remaining/duplicate/slice](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/nio/ByteBuffer.html)
7. [RFC 6455 — The WebSocket Protocol: message fragmentation, masking, control, handshake](https://www.rfc-editor.org/rfc/rfc6455.html)
8. [Java SE 26 — WebSocket: đối chiếu API vẫn được hỗ trợ](https://docs.oracle.com/en/java/javase/26/docs/api/java.net.http/java/net/http/WebSocket.html)
