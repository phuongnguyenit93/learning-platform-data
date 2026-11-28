# WebSocket client và xử lý thông điệp có kiểm soát nhu cầu trong Java 27

WebSocket là giao thức trao đổi dữ liệu **hai chiều** qua một kết nối tồn tại lâu dài. Sau khi thiết lập kết nối bằng opening handshake, client và server có thể gửi các thông điệp văn bản, nhị phân và control frame theo cả hai hướng. Nó phù hợp với thông báo thời gian thực, bảng giá trực tuyến, ứng dụng tương tác hay đồng bộ trạng thái.

Trong **Java SE 27**, API WebSocket client tiêu chuẩn nằm trong module `java.net.http`. Khác với cách lập trình callback không giới hạn thông thường, API này có cơ chế **kiểm soát nhu cầu nhận** (*receive demand control*): chương trình phải gọi `WebSocket.request(n)` để cấp quyền gọi các callback nhận dữ liệu. Một đơn vị demand biểu diễn **một lần gọi callback**, không phải một thông điệp hoàn chỉnh hay một số byte cố định.

Bài học thuộc chương **Mạng và HTTP**, trình bày các API hiện hành của Java 27: `HttpClient`, `WebSocket`, `WebSocket.Builder`, `WebSocket.Listener`, `CompletableFuture`, `CompletionStage` và `ByteBuffer`. Trọng tâm là nhận dữ liệu có kiểm soát, phân mảnh message, an toàn bộ nhớ, xử lý bất đồng bộ, đóng kết nối và thiết kế phù hợp cho hệ thống thực tế.

## 1. WebSocket khác HTTP request/response thế nào?

Với HTTP thông thường, client gửi một request và nhận response tương ứng. Với WebSocket, client mở một phiên, sau đó hai bên có thể chủ động gửi nhiều thông điệp.

~~~text
HTTP:
Client --- request ---> Server
Client <-- response --- Server

WebSocket:
Client --- opening handshake ---> Server
Client <-- thành công ------------- Server
Client --- text/binary -----------> Server
Client <--- text/binary ----------- Server
Client <--- Ping ------------------ Server
Client --- Pong ------------------> Server
Client <--- Close ----------------- Server
~~~

WebSocket không đồng nghĩa với HTTP streaming. Nó có framing, phân loại thông điệp, ping/pong và quy trình đóng riêng. WebSocket chỉ vận chuyển payload: **JSON schema, xác thực, quyền truy cập, ID bản tin và quy tắc xử lý** là trách nhiệm của ứng dụng.

### 1.1. ws và wss

| Scheme | Ý nghĩa | Sử dụng |
|---|---|---|
| `ws://` | WebSocket không được bảo vệ bằng TLS | Phát triển cục bộ hoặc môi trường có bảo vệ khác |
| `wss://` | WebSocket sử dụng TLS | Kết nối production và truyền dữ liệu nhạy cảm |

Ví dụ:

~~~text
ws://localhost:8080/events
wss://stream.example.org/v1/events
~~~

Trong sản phẩm, ưu tiên `wss://` với chứng chỉ TLS hợp lệ. TLS không thay thế xác thực ứng dụng hoặc kiểm tra dữ liệu do server gửi tới.

## 2. Bản đồ API Java 27

| API | Vai trò |
|---|---|
| `HttpClient` | Cung cấp cấu hình HTTP, TLS, proxy và tạo WebSocket builder |
| `HttpClient.newWebSocketBuilder()` | Tạo `WebSocket.Builder` |
| `WebSocket.Builder` | Cấu hình timeout, handshake header, subprotocol và URI |
| `buildAsync(uri, listener)` | Thực hiện thiết lập kết nối, trả `CompletableFuture<WebSocket>` |
| `WebSocket` | Gửi message, gọi `request(n)`, đóng input/output |
| `WebSocket.Listener` | Nhận callback mở kết nối, text, binary, ping, pong, close và error |
| `request(n)` | Cho phép thêm n lần gọi callback nhận |
| `CompletionStage<?>` | Báo khi dữ liệu callback có thể được WebSocket thu hồi/tái sử dụng |
| `sendText`, `sendBinary` | Gửi dữ liệu bất đồng bộ |
| `sendPing`, `sendPong` | Gửi control message |
| `sendClose`, `abort` | Đóng có bắt tay hoặc đóng đột ngột |

Module ứng dụng cần khai báo `requires java.net.http;` khi sử dụng JPMS:

~~~java
module com.example.websocketclient {
    requires java.net.http;
}
~~~

Chương trình chạy trên class path thông thường không bắt buộc có `module-info.java`.

### 2.1. Khởi tạo kết nối bằng HttpClient

~~~java
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.WebSocket;
import java.time.Duration;
import java.util.concurrent.CompletableFuture;

HttpClient client = HttpClient.newHttpClient();

WebSocket.Listener listener = new WebSocket.Listener() {
    @Override
    public void onOpen(WebSocket socket) {
        System.out.println("Đã kết nối");
        socket.request(1);
    }
};

CompletableFuture<WebSocket> connecting =
        client.newWebSocketBuilder()
                .connectTimeout(Duration.ofSeconds(10))
                .buildAsync(
                        URI.create("wss://stream.example.org/v1/events"),
                        listener
                );
~~~

Đây là đoạn minh họa API, **không phải lời khẳng định rằng máy chủ example.org có WebSocket endpoint hoạt động**. Ở ví dụ chạy đầy đủ bên dưới, endpoint sẽ được truyền qua tham số dòng lệnh.

`buildAsync` trả future, không trả socket kết nối ngay. Kết nối có thể thất bại vì TCP, TLS, opening handshake, từ chối dịch vụ hoặc hết timeout. `WebSocket.Builder` là đối tượng cấu hình mutable, **không thread-safe** nếu nhiều thread cùng dùng mà không đồng bộ bên ngoài.

### 2.2. Cấu hình opening handshake

~~~java
WebSocket.Builder builder = client.newWebSocketBuilder()
        .connectTimeout(Duration.ofSeconds(8))
        .subprotocols("chat.v2", "chat.v1");

// Header tùy chỉnh, không được trùng header thuộc protocol:
builder.header("Authorization", "Bearer " + accessToken);

CompletableFuture<WebSocket> connecting =
        builder.buildAsync(uri, listener);
~~~

Đoạn trên giả định `client`, `accessToken`, `uri` và `listener` đã có giá trị hợp lệ. Chỉ gửi token tới endpoint đã xác thực và cho phép. `header` từ chối các header do WebSocket protocol tự quản lý. Sau kết nối, `socket.getSubprotocol()` trả subprotocol đã được chấp nhận, hoặc chuỗi rỗng nếu không có.

**Connect timeout chỉ áp dụng cho giai đoạn thiết lập**, không phải idle timeout hay timeout xử lý từng message. Các loại timeout này cần cấu hình/triển khai riêng.

## 3. WebSocket.Listener và vòng đời nhận dữ liệu

Callback của một kết nối:

~~~text
buildAsync(...)
      |
   onOpen()
      |
      +------ onText(...) hoặc onBinary(...)
      |                   (có thể nhiều fragment)
      +------ onPing(...) hoặc onPong(...)
      |
   onClose(...) HOẶC onError(...)
      |
   Không có callback nào khác từ WebSocket đó
~~~

| Callback | Sự kiện | Tốn receive demand? |
|---|---|---|
| `onOpen` | Kết nối được mở | Không |
| `onText` | Nhận một phần text | Có |
| `onBinary` | Nhận một phần binary | Có |
| `onPing` | Nhận Ping | Có |
| `onPong` | Nhận Pong | Có |
| `onClose` | Nhận Close | Có |
| `onError` | Lỗi kết nối hoặc xử lý listener | Không |

`onClose` đánh dấu input đã đóng; `onError` là thông báo lỗi kết thúc kết nối, có thể được gọi mà **không cần demand**. Với cùng một WebSocket, sau `onClose` hoặc `onError` không có callback listener tiếp theo.

### 3.1. Thứ tự callback và thread safety

Với **một WebSocket**, các phương thức listener được gọi theo thứ tự, không tái nhập: callback kế tiếp không bắt đầu trước khi callback trước **trả về**. Điều này cho phép dùng một `StringBuilder` nội bộ để ghép các mảnh tuần tự.

Tuy nhiên:

- Callback kế tiếp **có thể được gọi trước khi `CompletionStage` trả về từ callback trước hoàn thành**, nếu còn demand.
- Không có cam kết mọi callback đều dùng một thread cụ thể.
- Cùng một listener instance dùng cho **nhiều WebSocket** có thể nhận callback của các connection khác nhau đồng thời.
- Tác vụ bất đồng bộ do listener tự khởi chạy không tự được bảo vệ bởi cơ chế gọi callback tuần tự.

Mẫu đơn giản và dễ kiểm soát là **một listener instance cho một kết nối**, mỗi listener sở hữu bộ đệm ghép fragment và trạng thái đóng riêng.

## 4. request(n): kiểm soát nhu cầu nhận

WebSocket mới có bộ đếm receive demand bằng 0. Lời gọi:

~~~java
socket.request(1);
~~~

cộng thêm một đơn vị demand. Mỗi lần WebSocket gọi `onText`, `onBinary`, `onPing`, `onPong` hoặc `onClose`, nó giảm bộ đếm một đơn vị.

~~~text
demand = 0
    |
request(1)
    v
demand = 1
    |
WebSocket gọi onText(...)
    v
demand = 0
    |
Listener xử lý và quyết định cấp tiếp
    |
request(1)
    v
demand = 1
~~~

Khi demand bằng 0, WebSocket không gọi thêm các callback **nhận**. `onOpen` và `onError` không bị chặn bởi điều kiện này.

### 4.1. Demand là số lượt callback, không phải số message

Giả sử server gửi **một** text message dưới ba phần:

~~~text
onText("Xin ", false)
onText("chào ", false)
onText("Java!", true)
~~~

Để nhận trọn message, listener cần **ba lượt callback**. Nếu chỉ request một lần rồi không cấp tiếp demand, nó sẽ nhận phần đầu nhưng không thể trông đợi phần sau tự đến listener.

Ping, Pong và Close cũng dùng một đơn vị demand. Vì vậy, không thể chỉ cấp tiếp ở callback text rồi bỏ qua control message.

### 4.2. Một listener request từng callback

~~~java
import java.net.http.WebSocket;
import java.util.concurrent.CompletionStage;

final class SimpleListener implements WebSocket.Listener {
    @Override
    public void onOpen(WebSocket socket) {
        socket.request(1);
    }

    @Override
    public CompletionStage<?> onText(
            WebSocket socket, CharSequence data, boolean last) {

        System.out.println("Nhận phần: " + data);
        System.out.println("Có phải phần cuối? " + last);

        socket.request(1);
        return null;
    }
}
~~~

Đây là ví dụ để học cơ chế cấp demand. Nếu thay phần in bằng đưa dữ liệu vào một hàng đợi **không giới hạn**, ứng dụng vẫn có thể hết RAM. `request(1)` không tự đảm bảo rằng hệ thống downstream có đủ tài nguyên.

### 4.3. request(0) và request(-1) là lỗi

~~~java
// Các lời gọi sau sẽ ném IllegalArgumentException:
// socket.request(0);
// socket.request(-1);

socket.request(1);
~~~

Tham số phải lớn hơn 0. Gọi nhiều lần `request(n)` cộng thêm demand; không cần mỗi lần bằng 1, nhưng cửa sổ demand nhỏ giúp dễ phân tích bộ nhớ khi downstream chậm.

### 4.4. Vì sao không cấp demand vô hạn?

Dữ liệu nhận có thể cần giải mã, kiểm tra schema, ghi xuống database, chạy thuật toán hoặc đẩy vào một queue. Một cửa sổ demand rất lớn không phải là giới hạn byte, không tạo ra tốc độ xử lý cao hơn và cũng không ngăn bộ nhớ tăng nếu callback tiếp tục tạo công việc bất đồng bộ.

Chiến lược an toàn thường là:

1. Nhận đủ một message theo các fragment.
2. Giới hạn kích thước đã ghép.
3. Đưa message hoàn chỉnh sang một bước xử lý có giới hạn.
4. **Chỉ request tiếp sau khi downstream chấp nhận/hoàn thành công việc**.

## 5. CompletionStage khác request(n)

`onText`, `onBinary`, `onPing` và `onPong` trả `CompletionStage<?>`, hoặc có thể trả `null`.

| Cơ chế | Chức năng |
|---|---|
| `socket.request(n)` | Cấp quyền WebSocket gọi thêm n callback nhận |
| `CompletionStage` của callback | Thông báo thời điểm WebSocket có thể thu hồi/tái sử dụng dữ liệu mà callback nhận |

**Completing một `CompletionStage` không tự tăng demand.** Gọi `request(1)` cũng không buộc WebSocket phải đợi `CompletionStage` trước đó hoàn tất trước khi gọi callback tiếp theo.

### 5.1. Trả null khi đã nhận/copy xong

~~~java
@Override
public CompletionStage<?> onText(
        WebSocket socket, CharSequence data, boolean last) {

    String copy = data.toString();
    System.out.println(copy);

    socket.request(1);
    return null;
}
~~~

Trả `null` có nghĩa dữ liệu callback có thể được tái sử dụng **ngay**. `String` được tạo bởi `toString()` tách khỏi vòng đời của `CharSequence` được callback nhận, nên thích hợp để chuyển qua xử lý khác.

Không lưu giữ `data` gốc trong queue rồi trả `null`: WebSocket được phép tái sử dụng dữ liệu đó.

### 5.2. CompletionStage chưa hoàn tất không thay thế backpressure

~~~java
@Override
public CompletionStage<?> onText(
        WebSocket socket, CharSequence data, boolean last) {

    CompletableFuture<Void> consumed = new CompletableFuture<>();

    asyncConsumer(data).whenComplete((value, error) -> {
        if (error == null) {
            consumed.complete(null);
        } else {
            consumed.completeExceptionally(error);
        }
    });

    socket.request(1);
    return consumed;
}
~~~

Đây là ví dụ **khái niệm**. `asyncConsumer` phải được định nghĩa và không được sử dụng `data` sau khi `consumed` hoàn thành. Mặc dù `consumed` còn pending, WebSocket vẫn có thể gọi callback kế tiếp vì `request(1)` đã được cấp.

Để **không nhận message nghiệp vụ mới trước khi xử lý message hiện tại**, cần giữ demand bằng 0 sau mảnh cuối và chỉ cấp lại khi xử lý thành công.

### 5.3. Copy dữ liệu trước khi chuyển thread

Đối với text:

~~~java
String copiedText = data.toString();
~~~

Đối với binary:

~~~java
ByteBuffer readOnly = data.asReadOnlyBuffer();
byte[] bytes = new byte[readOnly.remaining()];
readOnly.get(bytes);
~~~

Đối với binary, các byte hợp lệ nằm trong phạm vi `position` đến `limit`. Không mặc định gọi `array()`, vì buffer có thể không có backing array hoặc ở chế độ read-only.

Việc copy giúp tách lifetime của dữ liệu khỏi callback, nhưng **không miễn trừ yêu cầu giới hạn kích thước và tổng số message đang chờ xử lý**.

## 6. onOpen: cấp demand ban đầu

~~~java
@Override
public void onOpen(WebSocket socket) {
    System.out.println("Kết nối đã mở");
    socket.request(1);
}
~~~

Implementation mặc định của `onOpen` gọi `request(1)`. Nếu bạn override `onOpen` mà không tự gọi `request` hoặc không gọi default implementation, hành vi đó không còn nữa. Kết nối có thể mở thành công nhưng các callback nhận sẽ không được phát cho đến khi có demand, trừ `onError`.

Nếu hệ thống chưa sẵn sàng nhận, có thể trì hoãn `request`, nhưng phải có chính sách deadline/hủy rõ ràng nếu tình trạng này kéo dài.

## 7. onText: ghép fragment bằng cờ last

Callback:

~~~java
CompletionStage<?> onText(
        WebSocket socket, CharSequence data, boolean last)
~~~

có thể được gọi nhiều lần cho cùng một message:

- `last == false`: còn dữ liệu tiếp theo của message.
- `last == true`: phần cuối của message.

Ví dụ ghép mảnh:

~~~java
import java.net.http.WebSocket;
import java.util.concurrent.CompletionStage;

final class JoinTextListener implements WebSocket.Listener {
    private final StringBuilder parts = new StringBuilder();

    @Override
    public void onOpen(WebSocket socket) {
        socket.request(1);
    }

    @Override
    public CompletionStage<?> onText(
            WebSocket socket, CharSequence data, boolean last) {

        parts.append(data);

        if (last) {
            String message = parts.toString();
            parts.setLength(0);
            System.out.println("Đã ghép: " + message);
        }

        socket.request(1);
        return null;
    }
}
~~~

Mẫu trên **chưa an toàn với message quá lớn hoặc không kết thúc** vì không có hạn mức. Để tránh hết RAM, cần kiểm tra giới hạn trước mỗi `append`.

### 7.1. Giới hạn text đã giải mã

~~~java
private static final int MAX_UTF16_UNITS = 64 * 1024;
private final StringBuilder parts = new StringBuilder();

private void appendBounded(CharSequence data) {
    if ((long) parts.length() + data.length() > MAX_UTF16_UNITS) {
        throw new IllegalArgumentException("Text quá lớn");
    }
    parts.append(data);
}
~~~

`CharSequence.length()` và `StringBuilder.length()` đếm **UTF-16 code units**, không phải số byte trên wire. Nếu giao thức yêu cầu hạn mức UTF-8 byte hoặc hạn mức theo code point, hãy đo đúng đại lượng đó. Kiểm soát RAM cho text đã giải mã vẫn hữu ích nhưng không phải quota network chính xác.

### 7.2. Callback có thể nhận một phần hoặc toàn bộ message

Đừng mặc định mọi `onText` đều có `last == true`; message có thể bị chia nhỏ tùy implementation, kích thước và điều kiện nhận. Thiết kế đúng phải cho ra cùng một kết quả không phụ thuộc việc server chia message thành một, hai hay nhiều fragment.

## 8. onBinary: ByteBuffer và dữ liệu nhị phân

Callback:

~~~java
CompletionStage<?> onBinary(
        WebSocket socket, ByteBuffer data, boolean last)
~~~

nhận phần binary message với số byte nằm trong `data.remaining()`.

~~~java
@Override
public CompletionStage<?> onBinary(
        WebSocket socket, ByteBuffer data, boolean last) {

    ByteBuffer source = data.asReadOnlyBuffer();
    byte[] chunk = new byte[source.remaining()];
    source.get(chunk);

    processChunk(chunk, last); // Hàm ứng dụng tự triển khai.

    socket.request(1);
    return null;
}
~~~

`last` có cùng ngữ nghĩa kết thúc message như `onText`. Đừng giả định binary message luôn đến trong một callback hoặc buffer luôn là heap buffer.

### 8.1. Ghép binary trong quota

~~~java
import java.io.ByteArrayOutputStream;
import java.nio.ByteBuffer;

final class BoundedBinaryMessage {
    private static final int MAX_BYTES = 256 * 1024;
    private final ByteArrayOutputStream output =
            new ByteArrayOutputStream();

    byte[] accept(ByteBuffer part, boolean last) {
        int length = part.remaining();

        if ((long) output.size() + length > MAX_BYTES) {
            throw new IllegalArgumentException(
                    "Binary message quá lớn"
            );
        }

        ByteBuffer readOnly = part.asReadOnlyBuffer();
        byte[] chunk = new byte[readOnly.remaining()];
        readOnly.get(chunk);

        output.writeBytes(chunk);

        if (!last) {
            return null;
        }

        byte[] completeMessage = output.toByteArray();
        output.reset();
        return completeMessage;
    }
}
~~~

Với payload lớn, thay vì giữ toàn bộ trong RAM, cần xử lý theo chunk hoặc ghi vào nơi lưu trữ được giới hạn và kiểm soát. Đừng chuyển dữ liệu nhị phân tùy ý sang `String`.

## 9. onPing và onPong cũng tiêu thụ demand

WebSocket dùng Ping/Pong để kiểm tra kết nối. Trong Java `WebSocket`, việc nhận Ping đã có **cơ chế tự động phản hồi Pong** theo giao thức, vì vậy hiếm khi cần tự gửi Pong trong `onPing`.

~~~java
@Override
public CompletionStage<?> onPing(
        WebSocket socket, ByteBuffer payload) {

    System.out.println("Có Ping");
    socket.request(1);
    return null;
}

@Override
public CompletionStage<?> onPong(
        WebSocket socket, ByteBuffer payload) {

    System.out.println("Có Pong");
    socket.request(1);
    return null;
}
~~~

Nếu override hai callback này, hãy **cấp lại demand theo chính sách nhận**, vì cả hai cũng làm bộ đếm giảm một. Nếu chỉ request thêm trong `onText`, một Ping có thể tiêu thụ đơn vị demand cuối và khiến ứng dụng ngừng nhận tiếp.

Payload Ping/Pong tối đa **125 byte**. Ví dụ gửi Ping:

~~~java
socket.sendPing(ByteBuffer.wrap(new byte[] {1, 2, 3}));
~~~

Future của `sendPing` chỉ báo lần **gửi** hoàn thành; nó không có nghĩa client đã nhận Pong tương ứng. Muốn phát hiện heartbeat timeout, theo dõi `onPong` và dùng deadline riêng.

## 10. Gửi text/binary và thứ tự gửi

Các phương thức gửi trả `CompletableFuture<WebSocket>`:

~~~java
socket.sendText("Xin chào!", true);
socket.sendBinary(ByteBuffer.wrap(new byte[] {1, 2, 3}), true);
~~~

Cờ `last` có nghĩa:

- `false`: message chưa hoàn chỉnh, lời gọi sau sẽ gửi tiếp.
- `true`: hoàn tất message hiện tại.

Khi gửi nhiều phần, **xâu chuỗi các future**:

~~~java
socket.sendText("Xin ", false)
        .thenCompose(ws -> ws.sendText("chào!", true))
        .thenCompose(ws ->
                ws.sendClose(WebSocket.NORMAL_CLOSURE, ""))
        .join();
~~~

Không khởi chạy các send data độc lập cùng lúc rồi giả định thứ tự: nếu còn một data send đang pending hoặc trước đó đang ở giữa message chưa hoàn tất, API có thể báo `IllegalStateException`.

### 10.1. Vòng đời dữ liệu gửi

- Không sửa `CharSequence` gửi qua `sendText` trước khi future tương ứng hoàn tất.
- Không truy cập `ByteBuffer` gửi qua `sendBinary` khi send còn pending; sau lần gửi thành công, vị trí buffer tiến theo số byte đã gửi.
- Nên dùng `String` bất biến và buffer riêng cho mỗi send.
- Cần **send queue có giới hạn** khi nhiều producer cùng muốn gửi. Receive demand không giới hạn số message đang xếp hàng gửi.

### 10.2. Đóng bình thường và abort

~~~java
socket.sendClose(WebSocket.NORMAL_CLOSURE, "")
        .join();
~~~

`sendClose` đóng **output**, còn input có thể vẫn mở cho đến khi nhận Close từ peer hoặc có lỗi/abort. Với kết nối kết thúc bình thường, cần chờ phản hồi Close có thời hạn. Nếu peer không đóng:

~~~java
socket.abort();
~~~

`abort` đóng cả input và output đột ngột, làm các send pending thất bại. Đây là phương án thu hồi khi deadline hết, không thay thế quy trình đóng có bắt tay trong tình huống bình thường.

## 11. Kiểm soát nhu cầu theo từng message hoàn chỉnh

Một listener nhận fragment theo cửa sổ một callback có thể hoạt động:

~~~text
onOpen
   |
 request(1)
   |
onText(last=false) -> copy fragment, kiểm tra quota -> request(1)
   |
onText(last=true)
   |
ghép message, tách String độc lập
   |
giao downstream xử lý
   |
KHÔNG request thêm ngay tại đây
   |
xử lý hoàn tất và chấp nhận message
   |
request(1) để nhận callback mới

onPing/onPong: xử lý nhanh rồi request(1)
onClose: kết thúc, không request tiếp
onError: lỗi, không phụ thuộc demand
~~~

Nhờ trì hoãn `request(1)` sau mảnh cuối, một kết nối có thể giới hạn số **complete message đang xử lý** xuống một, trong khi vẫn request mảnh tiếp theo để ghép cho trọn message hiện tại.

**Giới hạn của cơ chế:** Java demand kiểm soát lần gọi callback ở tầng API, không phải chặn chắc chắn mọi byte đã gửi ở network/TCP. Runtime có thể đã nhận/buffer dữ liệu từ peer. Vẫn cần giới hạn kích thước từng message, quota lưu trữ, deadline xử lý và chính sách đóng khi quá tải.
## 12. Ví dụ hoàn chỉnh: client nhận một message mỗi lượt xử lý

Ví dụ sau là một chương trình Java độc lập minh họa cách kết hợp:

- `HttpClient.newWebSocketBuilder()` và `buildAsync`.
- `onOpen` cấp một đơn vị demand.
- `onText` ghép fragment với giới hạn số UTF-16 code units.
- Khi nhận đủ message, **tạm dừng cấp demand**, chạy việc xử lý trên executor riêng.
- Sau khi xử lý thành công, mới `request(1)` để tiếp tục nhận.
- `onPing` và `onPong` xử lý nhanh và bù demand.
- `onClose`/`onError` hoàn thành các future trạng thái.
- Khi close handshake không kết thúc đúng hạn, ứng dụng fallback `abort()`.

Chương trình nhận **một endpoint WebSocket echo** qua tham số. Echo server là server gửi lại text được client gửi; chương trình chỉ hoạt động đúng luồng chờ phản hồi nếu endpoint thực sự hỗ trợ hành vi này.

~~~java
import java.io.IOException;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.WebSocket;
import java.nio.ByteBuffer;
import java.time.Duration;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionStage;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;

public final class DemandControlledWebSocketClient {

    private static final int MAX_UTF16_UNITS = 64 * 1024;

    private static final class BoundedTextListener
            implements WebSocket.Listener {

        private final ExecutorService messageExecutor;
        private final StringBuilder fragments = new StringBuilder();

        private final CompletableFuture<String> firstProcessed =
                new CompletableFuture<>();

        private final CompletableFuture<Void> closed =
                new CompletableFuture<>();

        private BoundedTextListener(ExecutorService messageExecutor) {
            this.messageExecutor = messageExecutor;
        }

        @Override
        public void onOpen(WebSocket socket) {
            System.out.println("Kết nối thành công");
            socket.request(1);
        }

        @Override
        public CompletionStage<?> onText(
                WebSocket socket, CharSequence data, boolean last) {

            // Giới hạn trước khi append để không giữ message vô hạn.
            if ((long) fragments.length() + data.length()
                    > MAX_UTF16_UNITS) {

                fail(socket, new IOException(
                        "Text message vượt giới hạn"
                ));
                return null;
            }

            // Copy đồng bộ từ CharSequence do WebSocket sở hữu.
            fragments.append(data);

            if (!last) {
                // Vẫn đang ở giữa message; cần fragment tiếp theo.
                socket.request(1);
                return null;
            }

            // Tách thành String độc lập, không giữ callback buffer.
            String completeMessage = fragments.toString();
            fragments.setLength(0);

            // Không request ở đây: chỉ một message đang xử lý.
            CompletableFuture
                    .runAsync(() -> process(completeMessage),
                            messageExecutor)
                    .whenComplete((unused, error) -> {
                        if (error != null) {
                            fail(socket, error);
                            return;
                        }

                        // Hạ nguồn đã xử lý xong: cấp demand tiếp.
                        socket.request(1);
                        firstProcessed.complete(completeMessage);
                    });

            // Dữ liệu callback đã được copy xong.
            return null;
        }

        private void process(String message) {
            // Thay bằng xử lý nghiệp vụ có giới hạn thực tế.
            System.out.println("Đã xử lý: " + message);
        }

        @Override
        public CompletionStage<?> onBinary(
                WebSocket socket, ByteBuffer data, boolean last) {

            // Client ví dụ chỉ hỗ trợ text.
            fail(socket, new IOException(
                    "Không chấp nhận binary message"
            ));
            return null;
        }

        @Override
        public CompletionStage<?> onPing(
                WebSocket socket, ByteBuffer message) {

            // JDK đã tự gửi Pong theo protocol.
            socket.request(1);
            return null;
        }

        @Override
        public CompletionStage<?> onPong(
                WebSocket socket, ByteBuffer message) {

            socket.request(1);
            return null;
        }

        @Override
        public CompletionStage<?> onClose(
                WebSocket socket, int statusCode, String reason) {

            System.out.printf(
                    "Peer đóng: code=%d, reason=%s%n",
                    statusCode,
                    reason
            );

            firstProcessed.completeExceptionally(
                    new IOException("Đóng trước khi có phản hồi")
            );
            closed.complete(null);

            // JDK có thể hoàn thành việc đóng output mặc định.
            return null;
        }

        @Override
        public void onError(WebSocket socket, Throwable error) {
            firstProcessed.completeExceptionally(error);
            closed.completeExceptionally(error);
        }

        private void fail(WebSocket socket, Throwable error) {
            firstProcessed.completeExceptionally(error);
            closed.completeExceptionally(error);
            socket.abort();
        }
    }

    public static void main(String[] args) {
        if (args.length != 1) {
            System.err.println(
                    "Dùng: java DemandControlledWebSocketClient "
                    + "wss://<echo-server>/socket"
            );
            return;
        }

        URI uri = URI.create(args[0]);

        if (!"wss".equalsIgnoreCase(uri.getScheme())
                && !"ws".equalsIgnoreCase(uri.getScheme())) {
            throw new IllegalArgumentException(
                    "Endpoint phải dùng ws:// hoặc wss://"
            );
        }

        try (HttpClient http = HttpClient.newHttpClient();
             ExecutorService messageExecutor =
                     Executors.newSingleThreadExecutor()) {

            BoundedTextListener listener =
                    new BoundedTextListener(messageExecutor);

            WebSocket socket = http.newWebSocketBuilder()
                    .connectTimeout(Duration.ofSeconds(8))
                    .buildAsync(uri, listener)
                    .orTimeout(10, TimeUnit.SECONDS)
                    .join();

            try {
                socket.sendText("Xin chào từ Java 27", true)
                        .orTimeout(5, TimeUnit.SECONDS)
                        .join();

                // Demo này đợi echo server trả text và xử lý xong.
                String echo = listener.firstProcessed
                        .orTimeout(15, TimeUnit.SECONDS)
                        .join();

                System.out.println("Echo đã nhận: " + echo);

                socket.sendClose(WebSocket.NORMAL_CLOSURE, "")
                        .orTimeout(5, TimeUnit.SECONDS)
                        .join();

                // Chờ peer phản hồi Close; nếu quá hạn,
                // khối finally sẽ abort kết nối còn mở.
                listener.closed
                        .orTimeout(5, TimeUnit.SECONDS)
                        .join();
            } finally {
                if (!socket.isInputClosed()
                        || !socket.isOutputClosed()) {
                    socket.abort();
                }
            }
        }
    }
}
~~~

### 12.1. Cách chạy

Lưu toàn bộ chương trình thành `DemandControlledWebSocketClient.java`, sau đó biên dịch:

~~~shell
javac --release 27 -encoding UTF-8 DemandControlledWebSocketClient.java
~~~

Chạy với endpoint **do bạn vận hành hoặc đã kiểm tra đáng tin cậy**:

~~~shell
java DemandControlledWebSocketClient wss://your-echo-host.example/socket
~~~

Tên host ở trên chỉ là placeholder. Một endpoint WebSocket thường không tự động là echo server; nếu server không trả text tương ứng, ví dụ sẽ hết thời gian chờ như thiết kế.

Ví dụ cũng cho phép `ws://` để thử nghiệm nội bộ, nhưng **không dùng token hoặc dữ liệu nhạy cảm qua ws không có TLS**. Với dịch vụ production, hãy xác thực URI/host bằng allowlist; không cho phép input không tin cậy trực tiếp quyết định đích kết nối.

### 12.2. Phân tích luồng request chi tiết

Giả sử echo server trả text trong ba fragment:

~~~text
onOpen: request(1)
    |
    v
onText("Xin ", false)
    |
    +--> ghép, request(1)
    v
onText("chào ", false)
    |
    +--> ghép, request(1)
    v
onText("Java 27", true)
    |
    +--> copy full message, đưa sang messageExecutor
    |    demand hiện là 0
    |
    v
process(...) hoàn thành
    |
    +--> request(1)
    +--> firstProcessed.complete(message)
    |
    v
onClose có thể đến khi peer gửi Close
~~~

Nếu downstream chậm, callback text mới **không được request** cho đến khi xử lý xong message trước. Đây là điểm tạo ra cửa sổ xử lý một message, thay vì đặt một future trong callback rồi tiếp tục request ngay.

### 12.3. Vì sao onPing/onPong vẫn request?

Ping và Pong cũng giảm demand. Nếu một Ping đến ngay trong lúc đang ghép message, cần cấp thêm một lượt callback để phần text còn lại có thể đến. Khi chương trình chủ động dừng demand do downstream đang xử lý, callback Ping/Pong cũng không được gửi đến listener cho đến khi có demand.

Do đó, heartbeat phải được thiết kế phù hợp với chính sách nhận; không thể lấy việc `sendPing` thành công làm bằng chứng rằng `onPong` chắc chắn đã chạy.

### 12.4. Vì sao return null vẫn đúng?

Trong `onText`, chương trình đã gọi `fragments.append(data)` đồng bộ. Khi message hoàn chỉnh, nó chuyển thành `String` độc lập. Không có tác vụ bất đồng bộ nào giữ `CharSequence` mà callback nhận. Vì vậy trả `null` là đúng hợp đồng vòng đời dữ liệu.

Việc xử lý bất đồng bộ chậm được điều tiết bằng **thời điểm gọi `request(1)`**, không phải bằng việc giữ callback `CompletionStage` pending.

### 12.5. Giới hạn của chương trình mẫu

Đây là ví dụ học thuật, không phải WebSocket client production hoàn chỉnh:

- Nó chỉ cho phép một complete text message đang được xử lý tại một thời điểm.
- Giới hạn `MAX_UTF16_UNITS` không đo byte trên mạng.
- Không hỗ trợ binary message; nhận binary sẽ abort và báo lỗi.
- Xử lý lỗi `CompletableFuture` có thể bọc nguyên nhân trong `CompletionException`; ứng dụng thực cần phân loại/logging phù hợp.
- Khi xử lý trong `messageExecutor` kéo dài, demand bị giữ ở 0; cần deadline cho cả công việc đó.
- Không có reconnect/backoff, refresh credential hay heartbeat policy hoàn chỉnh.
- Để kiểm soát số message đang chờ gửi, còn cần **send queue có giới hạn**.
- Không có server echo tích hợp; kết quả phụ thuộc endpoint bạn chỉ định.

## 13. onClose, onError và trạng thái input/output

`WebSocket` có **hai chiều độc lập**:

- Input: nhận từ peer.
- Output: gửi sang peer.

Các phương thức:

~~~java
boolean inputClosed = socket.isInputClosed();
boolean outputClosed = socket.isOutputClosed();
~~~

báo trạng thái hiện tại. Khi một chiều đã đóng, nó không được mở lại.

### 13.1. onClose nhận status code và reason

~~~java
@Override
public CompletionStage<?> onClose(
        WebSocket socket, int statusCode, String reason) {

    System.out.printf(
            "Peer closed: %d, reason=%s%n",
            statusCode, reason
    );

    terminated.complete(null);
    return null;
}
~~~

Đoạn minh họa giả định `terminated` là một `CompletableFuture<Void>` đã khai báo. Khi nhận `onClose`, input đã đóng. Nếu output chưa đóng, việc hoàn tất stage trả về cho phép implementation thực hiện đóng output theo quy trình phản hồi Close mặc định.

`onClose` **tiêu thụ một đơn vị demand**. Nếu ứng dụng dừng request vô thời hạn, nó cũng có thể trì hoãn quan sát Close từ peer.

### 13.2. Không request thêm sau onClose

`onClose` là callback kết thúc, không phải một message nghiệp vụ để request thêm. Trả `null` hoặc một completed stage theo hợp đồng khi có thể hoàn tất đóng; không tạo một stage không bao giờ hoàn thành nếu bạn thực sự mong muốn WebSocket đóng đúng cách.

### 13.3. onError là callback cuối và không cần demand

~~~java
@Override
public void onError(WebSocket socket, Throwable error) {
    System.err.println("WebSocket thất bại: " + error);
    terminated.completeExceptionally(error);
}
~~~

Khi `onError` bắt đầu, cả input và output đã bị đóng theo hợp đồng. Không tiếp tục gửi hoặc request với kỳ vọng connection sẽ phục hồi. Nếu muốn kết nối lại, tạo WebSocket mới và khởi động giao thức phiên mới.

Không ném ngoại lệ từ `onError`: hành vi phát sinh từ việc đó không được xác định bởi hợp đồng listener. Hãy ghi nhận lỗi vào một future hoặc kênh theo dõi khác.

### 13.4. sendClose và abort khác nhau

| API | Ý nghĩa | Thời điểm dùng |
|---|---|---|
| `sendClose(WebSocket.NORMAL_CLOSURE, "")` | Bắt đầu gửi Close, đóng output theo quy trình | Đóng bình thường |
| `onClose(...)` | Peer đã gửi Close, input đã đóng | Nhận biết close handshake |
| `abort()` | Đóng đột ngột cả hai chiều, thất bại các send đang chờ | Timeout, lỗi nghiêm trọng hoặc hủy khẩn cấp |

Với `sendClose`, status code phải hợp lệ theo API. `WebSocket.NORMAL_CLOSURE` là `1000`. Không tự đưa các mã trạng thái bị cấm như `1006` hoặc `1009` vào `sendClose`, dù chúng có thể xuất hiện trong tài liệu protocol với mục đích mô tả khác.

Lý do đóng được mã hóa UTF-8, tối đa **123 byte**. Không gửi exception stack trace hoặc dữ liệu nhạy cảm trong Close reason.

## 14. Handshake, xác thực và subprotocol

### 14.1. URI và TLS

Khi kết nối, client cần xác minh:

1. Scheme có là `ws` hoặc `wss` không?
2. Host có nằm trong danh sách endpoint được phép không?
3. Với `wss`, chứng chỉ TLS có tin cậy và khớp tên host không?
4. Có yêu cầu xác thực không, và token có được lấy từ nơi lưu an toàn không?
5. Đã đặt connect timeout chưa?
6. Đã xác định subprotocol và schema message mà server hỗ trợ chưa?

Khi dùng input người dùng để chọn endpoint, cần phòng chống **SSRF** hoặc kết nối tới loopback/metadata service/internal network ngoài ý muốn. Các ví dụ đơn giản nhận URI từ CLI chỉ thích hợp khi người vận hành chủ động kiểm soát tham số.

### 14.2. Header Authorization

~~~java
WebSocket socket = client.newWebSocketBuilder()
        .connectTimeout(Duration.ofSeconds(10))
        .header("Authorization", "Bearer " + token)
        .buildAsync(uri, listener)
        .join();
~~~

Cần bảo đảm:

- `token` lấy từ nguồn an toàn, không hard-code trong source.
- Chỉ gửi token đến server tin cậy qua `wss`.
- Không ghi token vào log, exception text hay URL query tùy tiện.
- Không dùng `header(...)` để tự đặt các header protocol được JDK quản lý.

### 14.3. Subprotocol được đàm phán

~~~java
WebSocket socket = client.newWebSocketBuilder()
        .subprotocols("events.v2", "events.v1")
        .buildAsync(uri, listener)
        .join();

String protocol = socket.getSubprotocol();

if (!protocol.isEmpty()) {
    System.out.println("Protocol đã chọn: " + protocol);
}
~~~

Phần code cần được bao trong một phương thức có các biến phù hợp. Nếu không có subprotocol được đàm phán, `getSubprotocol()` trả chuỗi rỗng. Nếu ứng dụng yêu cầu một subprotocol nhất định, phải **kiểm tra và từ chối hoạt động** khi kết quả không phù hợp, thay vì lặng lẽ hiểu mọi payload theo schema mong muốn.

### 14.4. Lỗi opening handshake

`buildAsync` có thể hoàn thành ngoại lệ `WebSocketHandshakeException` khi server từ chối/không hoàn tất handshake hợp lệ. Ngoại lệ này cung cấp thông tin HTTP response liên quan để hỗ trợ chẩn đoán.

Không log tùy tiện các header nhạy cảm hoặc dữ liệu cá nhân từ phản hồi. Phân biệt thất bại handshake với việc kết nối đã mở nhưng sau đó gặp `onError` trong lúc trao đổi message.

## 15. Xử lý timeout, cancel và reconnect có trách nhiệm

Một WebSocket client thực tế có nhiều đồng hồ thời gian khác nhau:

| Loại timeout | Vấn đề giải quyết |
|---|---|
| Connect/handshake timeout | Không đợi thiết lập kết nối mãi |
| Timeout của send operation | Không giữ future gửi pending vô hạn |
| Idle timeout | Phát hiện ứng dụng không nhận dữ liệu trong thời gian cho phép |
| Heartbeat/Pong timeout | Phát hiện kết nối không phản hồi heartbeat |
| Downstream processing timeout | Không giữ demand bằng 0 quá lâu |
| Close handshake timeout | Fallback abort nếu peer không hoàn tất đóng |
| Tổng deadline của request nghiệp vụ | Hạn chế thời gian toàn workflow |

Không dùng một `connectTimeout` rồi cho rằng nó đồng thời là idle timeout hoặc timeout toàn phiên.

### 15.1. CompletableFuture.orTimeout

~~~java
WebSocket socket = client.newWebSocketBuilder()
        .connectTimeout(Duration.ofSeconds(8))
        .buildAsync(uri, listener)
        .orTimeout(10, TimeUnit.SECONDS)
        .join();
~~~

`orTimeout` làm future kết thúc ngoại lệ khi đến thời hạn, nhưng **không nên mặc định nó sẽ giải phóng mọi tài nguyên hoặc hủy tất cả các thao tác I/O bên dưới**. Cần có luồng cleanup riêng, kể cả khi khởi tạo đã bắt đầu.

Với kết nối đã thành công, nhớ quản lý `WebSocket.abort()` hoặc đóng bình thường theo deadline.

### 15.2. Heartbeat cần tương quan Ping/Pong

~~~java
ByteBuffer ping = ByteBuffer.wrap(new byte[] {42});
socket.sendPing(ping)
        .orTimeout(3, TimeUnit.SECONDS);
~~~

Đoạn này chỉ đợi **gửi Ping**, không chờ Pong. Để có heartbeat thật:

1. Ghi thời điểm/ID payload Ping hợp lệ.
2. Gửi Ping và theo dõi lỗi gửi.
3. Quan sát `onPong`, đối chiếu ID/payload nếu cần.
4. Dùng deadline dựa trên `System.nanoTime()` hoặc cơ chế lập lịch.
5. Nếu không có Pong hợp lệ đúng hạn, quyết định reconnect/abort.

Vì Ping và Pong callback cũng tiêu thụ demand, việc dừng request trong thời gian xử lý có thể ảnh hưởng tới heartbeat ở mức listener. Deadline phải tính đến chính sách receive demand.

### 15.3. Reconnect có backoff và jitter

Khi mất mạng hoặc server bảo trì, kết nối lại có thể hợp lý. Tuy nhiên:

- Không reconnect ngay lập tức vô hạn.
- Dùng exponential backoff có **jitter** và giới hạn thời gian/số lần.
- Không khởi động nhiều vòng reconnect cho cùng session.
- Khi reconnect, xem xét token expiry và xác thực lại.
- Nếu protocol có sequence ID, quản lý resume, duplicate và missing message.
- Không giả định reconnect tự khôi phục những message bị mất trong thời gian offline.

Ví dụ, WebSocket có thể chở dữ liệu sự kiện, nhưng API Java tự nó **không cung cấp bảo đảm exactly-once delivery**. Cần thiết kế protocol ứng dụng cho những bảo đảm như vậy.

## 16. Một send queue có giới hạn để tránh quá tải chiều gửi

Receive demand chỉ kiểm soát callback nhận. Nếu hàng chục producer liên tục gọi `sendText`, có thể tạo nhiều payload/future đang đợi và gặp lỗi gửi đồng thời.

Một mẫu quản lý đơn giản là serialize những lời gọi send trên một connection. Ý tưởng:

~~~java
CompletableFuture<WebSocket> chain =
        CompletableFuture.completedFuture(socket);

chain = chain.thenCompose(ws ->
        ws.sendText("message A", true));

chain = chain.thenCompose(ws ->
        ws.sendText("message B", true));
~~~

Đây chỉ là phần minh họa cấu trúc future. Trong ứng dụng có producer đồng thời, cần đồng bộ quyền cập nhật chuỗi `chain` hoặc dùng một actor/single-writer queue; không để nhiều thread cùng cập nhật biến này mà không bảo vệ.

**Một chuỗi future nối dài không giới hạn vẫn có thể giữ rất nhiều payload trong bộ nhớ.** Để thật sự có backpressure chiều gửi:

- Dùng queue có dung lượng tối đa K message hoặc B byte.
- Khi đầy, block có timeout, từ chối, gộp sự kiện hoặc áp dụng drop policy theo yêu cầu nghiệp vụ.
- Không giữ payload mutable đang được dùng bởi `sendBinary`.
- Theo dõi số send đang pending và thời gian hoàn tất.
- Khi đóng, xác định xử lý những message còn trong queue như thế nào.

### 16.1. Không dùng synchronized làm backpressure duy nhất

Một method `synchronized send(...)` chỉ đảm bảo các lời gọi Java không xen lẫn tại thời điểm đó. Nếu method mỗi lần chỉ gọi `sendText` rồi trả ngay, nhiều send operation vẫn có thể đang pending trên WebSocket.

Phải điều phối theo **future hoàn tất**, không chỉ khóa quanh lời gọi khởi tạo send.

## 17. Bảo mật và hạn mức trong hệ thống thực tế

### 17.1. Không tin cậy payload từ peer

Một message text có thể chứa JSON không hợp lệ, nội dung rất lớn, chuỗi Unicode phức tạp hoặc dữ liệu được tạo nhằm tiêu thụ tài nguyên.

Với mọi payload:

1. Giới hạn kích thước trước và trong quá trình ghép mảnh.
2. Parse có giới hạn độ sâu/kích thước.
3. Validate schema và kiểu dữ liệu.
4. Kiểm tra quyền truy cập cho từng hành động nghiệp vụ.
5. Không log toàn bộ payload chứa token, dữ liệu nhạy cảm.
6. Không sử dụng trực tiếp một path/URL từ message để truy cập file hoặc mạng.
7. Quy định chính sách xử lý message không hợp lệ: bỏ qua có kiểm soát, từ chối hoặc đóng connection.

### 17.2. Demand không thay thế giới hạn bộ nhớ

Giả sử một text message được chia thành hàng triệu fragment. Nếu listener vẫn cấp `request(1)` sau mỗi fragment nhưng chỉ giới hạn số message hoàn chỉnh đang xử lý, bộ ghép mảnh **vẫn có thể phình to**.

Vì vậy, phải kết hợp hai lớp:

- **Fragment accumulation quota:** giới hạn byte/code unit cho một message chưa hoàn chỉnh.
- **Processing concurrency quota:** chỉ cho tối đa K message đã hoàn chỉnh ở downstream.

Ngoài ra, cần quan tâm số connection đồng thời, tổng RAM, tốc độ nhận dữ liệu, timeout cho message bị bỏ dở và giới hạn hạ tầng mạng.

### 17.3. Đừng block lâu trong callback

Ví dụ dễ gây vấn đề:

~~~java
@Override
public CompletionStage<?> onText(
        WebSocket socket, CharSequence data, boolean last) {

    database.save(data.toString()); // Có thể chặn lâu.
    socket.request(1);
    return null;
}
~~~

Nếu `database.save` chậm hoặc treo, callback bị chiếm lâu, làm trì hoãn xử lý control message và ảnh hưởng đến phản ứng của kết nối. Thường nên copy dữ liệu, đưa sang worker/executor phù hợp, **chỉ cấp tiếp demand khi downstream sẵn sàng**.

Tuy nhiên, chỉ đơn giản đưa vào unbounded queue là sai. Queue phải có giới hạn và chính sách quá tải.

### 17.4. Giới hạn connection và xác thực nguồn

Với ứng dụng kết nối tới nhiều endpoint:

- Áp dụng allowlist cho host/port/protocol.
- Ưu tiên `wss`.
- Không đặt credential trong URI nếu không cần.
- Giới hạn số kết nối đang mở và số lần reconnect.
- Kiểm tra certificate và subprotocol.
- Phân biệt lỗi do handshake, mạng và ứng dụng.
- Không bỏ qua TLS validation để “sửa” lỗi chứng chỉ.

## 18. Các lỗi thường gặp và cách phân tích

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Đã kết nối nhưng không nhận `onText` | Override `onOpen` nhưng không `request` | Cấp demand ban đầu |
| Nhận đúng một fragment rồi dừng | Demand đã về 0, chưa request tiếp | Request theo từng fragment |
| Ping đến rồi ngừng nhận text | `onPing` tiêu thụ demand nhưng không bù | Xử lý Ping và cấp demand mới |
| `onClose` không được quan sát | Không còn receive demand | Duy trì chính sách request/timeout; dùng abort khi cần |
| Message bị cắt | Xử lý mỗi `onText` như message đầy đủ | Ghép fragment đến `last == true` |
| Heap tăng dần | Message chưa giới hạn hoặc queue downstream vô hạn | Quota per-message và bounded queue |
| Dữ liệu binary bị sai | Dùng `ByteBuffer.array()` hoặc quên `position/limit` | Đọc đúng `remaining()`, copy phù hợp |
| Lỗi dùng buffer sau callback | Giữ reference sau khi stage hoàn tất | Copy dữ liệu hoặc quản lý stage đúng |
| `IllegalStateException` khi gửi | Pending data send hoặc message trước chưa hoàn tất | Serialize send bằng future chain có giới hạn |
| `sendPing` hoàn tất nhưng không có Pong | Send future không biểu diễn Pong receipt | Theo dõi `onPong` và timeout |
| `sendClose` xong nhưng kết nối chưa hoàn toàn đóng | Chỉ output đóng | Đợi `onClose` hoặc abort khi hết deadline |
| `WebSocketHandshakeException` | Server không chấp nhận handshake | Kiểm tra URL, auth, TLS, subprotocol và response |
| `HttpTimeoutException` khi kết nối | Handshake/connect vượt thời hạn | Xem network, proxy, server và timeout phù hợp |
| `onError` không tới sau khi ngừng request | `onError` vẫn có thể tới không cần demand, nhưng không phải tất cả trạng thái im lặng đều là lỗi I/O | Dùng heartbeat/deadline chủ động |
| Reconnect tạo bản tin trùng | Protocol ứng dụng chưa có ID/dedup | Thiết kế ID, resume và idempotency |

## 19. Kiểm thử demand và fragmentation

Để kiểm thử, nên dùng **WebSocket test server cục bộ** hoặc server tích hợp trong môi trường test. Java SE 27 có WebSocket **client** tiêu chuẩn trong `java.net.http`, không cung cấp một API server WebSocket tương đương theo cùng giao diện.

### 19.1. Tình huống test thiết yếu

| Test | Kết quả mong đợi |
|---|---|
| Listener không request sau `onOpen` | Không có receive callback thường, trừ `onError` |
| Request 1 rồi server gửi text nhiều fragment | Nhận một callback, cần request tiếp để có fragment kế |
| Request 1, nhận Ping | Demand giảm; cần cấp lại để tiếp tục |
| Gửi text nhiều fragment | Ghép đúng một logical message |
| Message trống | Xử lý đúng khi `last == true` |
| Message vượt MAX_UTF16_UNITS | Từ chối, không tăng buffer vô hạn |
| Binary ngoài schema | Phản ứng theo chính sách lỗi, không giả làm text |
| Worker xử lý chậm | Không request complete message mới quá sớm |
| Worker ném ngoại lệ | Connection được kết thúc/cấp quản lý quan sát thất bại |
| Peer gửi Close | `onClose` chỉ kết thúc một lần khi có demand |
| Peer cắt kết nối | `onError` hoặc timeout/heartbeat phát hiện sự cố |
| Gửi hai data send đồng thời | Không thiết kế phụ thuộc hành vi không được cam kết |
| Send close rồi peer im lặng | Close deadline kích hoạt abort |
| URI không đáng tin | Bị chặn theo chính sách allowlist |
| Reconnect sau lỗi | Backoff/jitter và giới hạn số kết nối |

### 19.2. Tránh kiểm thử bằng Thread.sleep tùy tiện

~~~java
Thread.sleep(100);
// Không chứng minh listener đã xử lý message.
~~~

Một máy CI chậm có thể khiến test thất bại ngẫu nhiên. Thay vào đó, dùng `CompletableFuture` hoặc latch được hoàn thành bởi **sự kiện thực** trong listener rồi gọi `get(timeout, unit)`.

Đừng để test chờ vô hạn khi server không gửi callback do hết demand.

### 19.3. Đo lường những gì?

Các metric có ích:

- Kết nối đang mở và tỉ lệ handshake thành công/thất bại.
- Số message và fragment nhận theo loại.
- Kích thước message đã ghép; số lần vượt quota.
- Thời gian xử lý downstream.
- Số message trong bounded queue và tỉ lệ bị từ chối.
- Thời gian gửi message, số send pending.
- Heartbeat round-trip hoặc deadline vi phạm.
- Mã đóng kết nối, số lần reconnect và độ trễ backoff.

Không đưa payload/credential vào metric labels. Đừng coi số callback là số message hoàn chỉnh vì mỗi message có thể có nhiều callback.

## 20. Lựa chọn thiết kế theo yêu cầu

| Yêu cầu | Cách thiết kế phù hợp |
|---|---|
| Nhận message text nhỏ để in log | Listener đơn giản, request từng callback và quota cơ bản |
| Nhận text nhiều fragment | `StringBuilder` có giới hạn, xử lý khi `last == true` |
| Nhận binary | Đọc `ByteBuffer.remaining`, giới hạn byte và copy/stream |
| Downstream chậm | Không request message mới trước khi xử lý trước xong |
| Cần xử lý nhiều message đồng thời | Queue bounded, worker pool và demand theo sức chứa |
| Cần chỉ một message đang xử lý | Request fragments tiếp, ngừng request sau last đến khi xử lý xong |
| Nhiều producer gửi dữ liệu | Send queue serialized có giới hạn byte/message |
| Cần health check | Ping/Pong được tương quan và có deadline |
| Cần đóng đúng cách | `sendClose`, chờ `onClose` có timeout, fallback `abort` |
| Cần tự động kết nối lại | Reconnect có backoff/jitter, chính sách resume và dedup |
| Cần an toàn production | `wss`, auth, allowlist, quota, schema validation và không log bí mật |

## 21. Bài tập thực hành

### Bài tập 1: Demand cơ bản

Tạo listener chỉ cấp `request(1)` trong `onOpen`, rồi kết nối tới server test gửi hai text messages. Quan sát callback. Sau đó bổ sung request trong `onText`.

**Câu hỏi:** Tại sao một đơn vị demand không tương đương một text message?

### Bài tập 2: Text fragmentation

Tạo bộ ghép text có `MAX_UTF16_UNITS = 1000`. Server test lần lượt gửi các fragment với `last=false`, `last=false`, `last=true`.

Yêu cầu: chỉ xử lý một logical message khi đủ fragment; reset buffer sau `last=true`; ngắt connection khi vượt quota.

### Bài tập 3: Backpressure theo downstream

Giả lập xử lý mỗi message mất một khoảng thời gian, sử dụng executor một thread.

Yêu cầu: chỉ cấp `request(1)` sau mảnh cuối khi future xử lý hoàn tất; có deadline cho xử lý; nếu executor từ chối task, phải báo lỗi và hủy theo chính sách.

**Câu hỏi:** Trả về một `CompletionStage` chưa hoàn thành có tự ngăn callback kế tiếp nếu đã cấp demand không?

### Bài tập 4: Binary và ByteBuffer lifetime

Tạo listener nhận binary, copy đúng phạm vi `position/limit` rồi gửi bản sao sang worker. Không truy cập buffer callback sau khi stage hoàn thành.

**Câu hỏi:** Tại sao `data.array()` không phải lựa chọn đúng cho mọi `ByteBuffer`?

### Bài tập 5: Ping, Close và lỗi

Tạo server test gửi Ping trước text và sau đó Close. Listener phải cấp lại demand sau Ping, nhận text đúng và hoàn tất `onClose`. Sau đó mô phỏng kết nối bị cắt không gửi Close.

**Câu hỏi:** Khi nào cần dùng `abort()` thay vì chỉ `sendClose()`?

## 22. Checklist triển khai an toàn

- [ ] Endpoint có dùng `wss://` ở môi trường production?
- [ ] Host và port có được kiểm soát bằng allowlist khi nhận từ input ngoài?
- [ ] Token/credential có được bảo vệ và không ghi log?
- [ ] Có thiết lập connect timeout và deadline tổng thể?
- [ ] Listener có cấp demand ban đầu trong `onOpen`?
- [ ] Có nhớ Ping, Pong và Close cũng tiêu thụ demand?
- [ ] Có phân biệt số lượt callback với số message/byte?
- [ ] Text và binary có được ghép theo `last` không?
- [ ] Message chưa hoàn tất có được giới hạn kích thước?
- [ ] Có copy hoặc giữ stage đúng để tránh truy cập dữ liệu callback đã được tái sử dụng?
- [ ] Có phân biệt CompletionStage với backpressure của `request`?
- [ ] Khi downstream chậm, demand có được trì hoãn phù hợp?
- [ ] Worker queue và send queue có giới hạn số lượng/byte?
- [ ] Các thao tác gửi có được serialize theo future completion?
- [ ] Có heartbeat/idle timeout, quan sát Pong và hủy khi quá hạn?
- [ ] Có xử lý `onClose`/`onError` mà không rò rỉ tài nguyên?
- [ ] Có thiết kế close handshake có deadline và fallback abort?
- [ ] Có policy reconnect/backoff, khôi phục session và xử lý duplicate?
- [ ] Có test fragment, Ping, payload quá lớn, server im lặng và lỗi handshake?
- [ ] Có kiểm tra source code theo đúng Java SE 27 API thay vì dùng API incubator/lỗi thời?

## 23. Tóm tắt

- **Java 27** cung cấp WebSocket client tiêu chuẩn qua `java.net.http.HttpClient` và `WebSocket`.
- `buildAsync` thiết lập kết nối bất đồng bộ và trả future.
- `WebSocket.Listener` nhận callback text, binary, control message và sự kiện đóng/lỗi.
- **`request(n)` cấp quyền cho n receive callbacks, không phải n logical messages hoặc n byte.**
- `onOpen` và `onError` không tiêu thụ demand; `onText`, `onBinary`, `onPing`, `onPong` và `onClose` đều tiêu thụ.
- Cờ `last` xác định khi nào một message text/binary đã hoàn tất qua các fragment.
- **`CompletionStage` báo vòng đời buffer callback, không tự điều khiển nhu cầu nhận.**
- Nếu downstream chậm, hãy copy fragment có giới hạn, xử lý message hoàn chỉnh và **chỉ request tiếp khi downstream sẵn sàng**.
- `sendText`/`sendBinary` là bất đồng bộ; điều phối các send bằng future chain hoặc bounded queue.
- `sendClose` chỉ bắt đầu đóng output; chờ phản hồi Close có deadline, rồi `abort` khi cần.
- Một client production còn phải đảm bảo TLS, auth, schema validation, timeout, quota, heartbeat và reconnect có kiểm soát.

## Tài liệu tham khảo chính thức

- [WebSocket — Java SE 27 API](https://docs.oracle.com/en/java/javase/27/docs/api/java.net.http/java/net/http/WebSocket.html)
- [WebSocket.Listener — Java SE 27 API](https://docs.oracle.com/en/java/javase/27/docs/api/java.net.http/java/net/http/WebSocket.Listener.html)
- [WebSocket.Builder — Java SE 27 API](https://docs.oracle.com/en/java/javase/27/docs/api/java.net.http/java/net/http/WebSocket.Builder.html)
- [HttpClient — Java SE 27 API](https://docs.oracle.com/en/java/javase/27/docs/api/java.net.http/java/net/http/HttpClient.html)
- [WebSocketHandshakeException — Java SE 27 API](https://docs.oracle.com/en/java/javase/27/docs/api/java.net.http/java/net/http/WebSocketHandshakeException.html)
- [CompletableFuture — Java SE 27 API](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/concurrent/CompletableFuture.html)
- [CompletionStage — Java SE 27 API](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/concurrent/CompletionStage.html)
- [ByteBuffer — Java SE 27 API](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/nio/ByteBuffer.html)
- [RFC 6455 — The WebSocket Protocol](https://www.rfc-editor.org/rfc/rfc6455)
