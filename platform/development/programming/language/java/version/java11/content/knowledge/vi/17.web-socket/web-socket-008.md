# `WebSocket.request(n)` và điều tiết số lần gọi nhận dữ liệu (Java 11 trở lên)

## 1. Bài toán: kết nối WebSocket có thể nhận dữ liệu nhanh hơn tốc độ xử lý

WebSocket giữ một kết nối hai chiều, cho phép server chủ động gửi dữ liệu đến client bất cứ khi nào. Với ứng dụng Java, quá trình nhận message diễn ra thông qua một đối tượng triển khai `java.net.http.WebSocket.Listener`, thường có những callback như `onText`, `onBinary`, `onPing` và `onPong`.

Tình huống thực tế: server gửi nhiều event liên tục, còn client phải parse JSON, ghi database hoặc cập nhật giao diện. Nếu client cho phép callback nhận dữ liệu không giới hạn mà không điều tiết, các hàng đợi và dữ liệu chờ xử lý trong ứng dụng có thể lớn dần.

API WebSocket chuẩn từ **Java 11** cung cấp phương thức:

```java
void request(long n);
```

Ví dụ:

```java
@Override
public void onOpen(WebSocket webSocket) {
    webSocket.request(1);
}
```

Ý nghĩa của `request(1)`: cấp thêm quyền cho **tối đa một lần gọi phương thức nhận dữ liệu** của listener. Khi callback đó được gọi, một quyền trong bộ đếm được tiêu thụ. Ứng dụng có thể chủ động gọi thêm `request(1)` khi sẵn sàng nhận lượt tiếp theo.

**Điều quan trọng nhất:** `request(n)` điều tiết **số lần callback nhận được gọi**, **không phải số message WebSocket hoàn chỉnh, không phải n byte, không phải kích thước queue và không phải số lần gửi dữ liệu của server**.

Kiến thức này thuộc API `java.net.http.WebSocket` đã ổn định từ Java 11 và vẫn áp dụng ở JDK hiện hành. Không nhầm với các API WebSocket incubator từ những bản Java tiền phát hành/đã lỗi thời.

## 2. Ba lớp khái niệm: network frame, message và callback

WebSocket có ba khái niệm liên quan nhưng không trùng nhau:

1. **Frame:** đơn vị đóng gói ở tầng giao thức WebSocket, có thể mang dữ liệu, control frame hoặc mảnh của một message.
2. **Message:** một nội dung text hoặc binary hoàn chỉnh theo protocol; có thể trải trên nhiều frame.
3. **Listener invocation:** một lần HTTP Client gọi `onText(...)`, `onBinary(...)`, `onPing(...)`, `onPong(...)` hoặc `onClose(...)` trong Java.

JDK có thể giao một text/binary message cho listener qua **một hoặc nhiều callback**. Listener biết một message đã kết thúc hay chưa qua tham số boolean `last`.

Ví dụ minh họa (không phải cam kết một frame tương ứng đúng một callback):

```text
Một TEXT message: "Hello"

Callback 1: onText(ws, "Hel", false)
Callback 2: onText(ws, "lo",  true)

=> 2 listener invocations
=> 1 complete text message
=> cần 2 đơn vị demand để nhận cả hai callbacks
```

Một message khác có thể chỉ cần một callback:

```text
onText(ws, "Hello", true)

=> 1 invocation
=> 1 complete text message
```

Vì vậy `request(2)` **không cam kết** nhận hai message. Có thể toàn bộ hai đơn vị demand được dùng cho hai mảnh của một message; cũng có thể các callback nhận được là Ping/Pong hoặc Close.

Với Ping/Pong/Close, mỗi control message được giao trong một callback tương ứng. Các callback control này **cũng tiêu thụ demand**, không nằm ngoài bộ đếm.

## 3. Bộ đếm demand của `WebSocket.request(n)` hoạt động như thế nào?

Theo Javadoc `java.net.http.WebSocket`, mỗi WebSocket duy trì một bộ đếm nội bộ biểu thị **số lần gọi receive methods còn được phép thực hiện**.

### Quy tắc cốt lõi

- Khi WebSocket mới được tạo, bộ đếm demand ban đầu bằng **0**.
- Gọi `webSocket.request(n)` với `n > 0` làm tăng demand lên `n`.
- Mỗi khi WebSocket thực sự gọi một **receive method** của listener, bộ đếm giảm **1**.
- Khi bộ đếm bằng **0**, WebSocket **không gọi** các receive methods cho đến khi có thêm demand.
- Gọi `request(n)` nhiều lần có tính **cộng dồn**: một lần `request(2)` và sau đó `request(3)` cấp thêm tổng cộng năm lượt (trừ những lượt đã sử dụng).
- `request(0)` hoặc `request(-1)` ném **`IllegalArgumentException`**: không dùng số 0 để "tạm dừng". Muốn ngừng cấp lượt mới, đơn giản là **chưa gọi thêm `request`**.
- Demand là một quyền **tối đa**, không cam kết sẽ có đủ dữ liệu để nhận đúng `n` callback. Nếu không có data, server đóng hoặc xảy ra lỗi, số lần thực tế có thể ít hơn.

Giả sử hiện không có demand nào, mô hình logic:

```text
Ban đầu:      demand = 0

request(2):   demand = 2
onText(...):  demand = 1
onPing(...):  demand = 0

Server gửi thêm data -> chưa gọi callback nhận tiếp
request(1):   demand = 1
onText(...):  demand = 0
```

Đây là ví dụ **mô hình bộ đếm**; callback được gọi lúc nào còn phụ thuộc dữ liệu nhận, connection và lịch thực thi.

### Danh sách callback có và không tiêu thụ demand

| `WebSocket.Listener` method | Tiêu thụ 1 đơn vị demand? | Vai trò |
| --- | --- | --- |
| `onText(WebSocket, CharSequence, boolean)` | **Có** | Nhận một phần hoặc toàn bộ text message |
| `onBinary(WebSocket, ByteBuffer, boolean)` | **Có** | Nhận một phần hoặc toàn bộ binary message |
| `onPing(WebSocket, ByteBuffer)` | **Có** | Nhận Ping control message |
| `onPong(WebSocket, ByteBuffer)` | **Có** | Nhận Pong control message |
| `onClose(WebSocket, int, String)` | **Có** | Nhận Close; callback kết thúc |
| `onOpen(WebSocket)` | **Không** | Thông báo đã kết nối, nơi thường cấp demand ban đầu |
| `onError(WebSocket, Throwable)` | **Không** | Thông báo lỗi, có thể được gọi bất kể demand |

**Điểm rất dễ nhầm:** `onClose` **cũng là receive method** theo hợp đồng `WebSocket`, nên muốn callback đóng kết nối được giao qua cơ chế nhận thông thường cũng cần có demand. Trong khi đó `onError` **không cần demand**; nó có thể được gọi kể cả lúc bộ đếm nhận bằng 0.

Sau `onClose` hoặc `onError` của cùng WebSocket, không còn callback nào khác được gọi cho listener đó, bất kể demand còn lại bao nhiêu.

### Demand không biến thành giới hạn bytes

`request(1)` không phải hạn mức "1 KB", "1 frame", "1 message" hoặc "một lần TCP read". Một `onBinary` có thể chứa nhiều byte; một `onText` có thể chứa một mảnh text lớn; cùng một lượng data có thể được giao qua số callback khác nhau.

Muốn giới hạn bộ nhớ, ứng dụng phải **đồng thời** giới hạn kích thước message, dung lượng buffer và queue, số tác vụ đang xử lý cùng lúc và chính sách từ chối data vượt ngưỡng. `request(n)` chỉ là một phần của chiến lược quản lý áp lực nhận.

## 4. Tại sao `onOpen` phải cấp demand ban đầu?

Khi kết nối được tạo qua `HttpClient.newWebSocketBuilder().buildAsync(...)`, demand của WebSocket bắt đầu bằng 0. `onOpen` là callback đầu tiên và không tiêu thụ demand. Do đó cần cấp lượt đầu tại đây, chẳng hạn:

```java
@Override
public void onOpen(WebSocket webSocket) {
    webSocket.request(1);
}
```

Nếu tự override `onOpen` nhưng **quên `request(1)`**, những callback nhận dữ liệu có thể không xuất hiện mặc dù server đã gửi message. Người mới thường tưởng WebSocket không nhận được dữ liệu trong khi thực tế client không cấp demand.

### Default `onOpen` tự cấp một đơn vị

Interface `WebSocket.Listener` có **default method**:

```java
default void onOpen(WebSocket webSocket) {
    webSocket.request(1);
}
```

Điều này giải thích vì sao một listener không override `onOpen` vẫn có thể nhận một callback đầu. Nhưng **khi override**, implementation của bạn thay thế default, nên phải chủ động gọi `request` nếu muốn nhận tiếp.

### Các default callback cũng thường tự yêu cầu lượt tiếp

Trong Java 11, default implementations của `onText`, `onBinary`, `onPing` và `onPong` về cơ bản đều thực hiện `webSocket.request(1)` và trả về `null`. Điều đó giúp các callback **chưa được override** không tự làm pipeline bị kẹt chỉ vì không xin thêm lượt.

Nhưng một khi bạn override một callback để xử lý data, bạn phải **tự quyết định gọi request khi nào**. Không nên cho rằng JDK sẽ âm thầm bù `request(1)` sau khi custom `onText` trả về.

Default `onClose` không tiếp tục cấp demand; đó là sự kiện kết thúc phía nhận. Default `onError` không cần demand, và không được viết logic yêu cầu vô hạn sau khi kết nối đã lỗi.

## 5. Cách điều tiết phổ biến: xin một callback, xử lý, rồi xin lượt mới

Mẫu đơn giản nhất là **`request(1)` ở `onOpen` và tiếp tục `request(1)` sau mỗi callback**.

```java
import java.net.http.WebSocket;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionStage;

public final class SimpleDemandListener implements WebSocket.Listener {
    @Override
    public void onOpen(WebSocket ws) {
        ws.request(1);
    }

    @Override
    public CompletionStage<?> onText(
            WebSocket ws, CharSequence data, boolean last) {
        System.out.println("Received fragment: " + data);
        ws.request(1);
        return CompletableFuture.completedFuture(null);
    }

    @Override
    public CompletionStage<?> onBinary(
            WebSocket ws, java.nio.ByteBuffer data, boolean last) {
        System.out.println("Binary bytes: " + data.remaining());
        ws.request(1);
        return CompletableFuture.completedFuture(null);
    }

    @Override
    public CompletionStage<?> onPing(
            WebSocket ws, java.nio.ByteBuffer message) {
        ws.request(1);
        return CompletableFuture.completedFuture(null);
    }

    @Override
    public CompletionStage<?> onPong(
            WebSocket ws, java.nio.ByteBuffer message) {
        ws.request(1);
        return CompletableFuture.completedFuture(null);
    }
}
```

Đây là một **class có thể biên dịch** đặt trong `SimpleDemandListener.java`; nó không phải chương trình có `main`. Tạo kết nối bằng `HttpClient.newHttpClient().newWebSocketBuilder().buildAsync(uri, new SimpleDemandListener())` ở một đoạn mã khác.

Mẫu trên giúp duy trì luồng callback trong trường hợp xử lý **nhanh, đồng bộ** ngay bên trong callback. Nhưng nó **không tự giới hạn công việc bất đồng bộ**: nếu chỉ đẩy dữ liệu vào một hàng đợi không giới hạn rồi gọi `request(1)` ngay, queue vẫn có thể phình to.

Thay vì chỉ tính callback, hãy xác định điểm nào trong ứng dụng nghĩa là **đã sẵn sàng cho lượt nhận tiếp**:

- Với công việc đơn giản, không block và không giữ dữ liệu lớn: sau khi xử lý xong ngay trong callback.
- Với I/O hoặc parse bất đồng bộ: sau khi hệ thống xử lý hoặc một queue **bounded** chấp nhận dữ liệu.
- Với message bị phân mảnh: cần xin lượt tiếp cho từng phần, **không chờ đến `last=true` mới xin phần tiếp theo**, nếu điều đó khiến thiếu demand.

### Không chỉ xử lý `onText`

Ping, Pong và Close cũng dùng một phần demand. Nếu override `onPing`/`onPong` nhưng quên cấp lượt tiếp và chỉ viết `request(1)` trong `onText`, một Ping/Pong có thể tiêu thụ quyền nhận cuối và khiến luồng text bị dừng.

Khi không cần custom hành vi cho Ping/Pong, có thể **không override** chúng; default implementations của Java 11 đã tự xin lượt kế. Khi override để đo latency/log hoặc kiểm soát chính sách, phải tính việc cấp demand vào thiết kế.

## 6. `last` và text/binary message bị phân mảnh

### Text message có thể đến qua nhiều `onText`

Với chữ `"HELLO"`, WebSocket có thể gọi:

```java
onText(ws, "HE", false);
onText(ws, "LL", false);
onText(ws, "O", true);
```

Ba callback ở trên chỉ là **một message hoàn chỉnh** và tiêu thụ **ba đơn vị demand**. Nếu listener chỉ gọi `request(1)` khi `last==true`, sau callback đầu `last=false` demand sẽ về 0; listener không nhận được phần tiếp, nên không bao giờ gặp `last=true` để gọi thêm. Đây là một dạng deadlock logic phổ biến.

Mẫu tích lũy đúng với text nhỏ:

```java
private final StringBuilder currentText = new StringBuilder();

@Override
public CompletionStage<?> onText(
        WebSocket ws, CharSequence data, boolean last) {
    currentText.append(data);

    if (last) {
        String complete = currentText.toString();
        currentText.setLength(0);
        processCompleteMessage(complete);
    }

    ws.request(1); // Áp dụng cho CẢ mảnh chưa phải cuối.
    return CompletableFuture.completedFuture(null);
}
```

Đây là **đoạn phương thức minh họa**; `processCompleteMessage` do ứng dụng tự định nghĩa. Với sản phẩm thật, phải giới hạn dung lượng `currentText` để tránh message cực lớn gây hết RAM. Đừng chia/parse JSON theo từng mảnh trước khi có message hoàn chỉnh, trừ khi parser có hỗ trợ xử lý streaming fragment đúng.

### Binary message tương tự

`onBinary(WebSocket, ByteBuffer, boolean last)` mang dữ liệu trong khoảng `buffer.position()` đến `buffer.limit()`. Có thể phải gom nhiều mảnh cho đến `last=true`.

```java
@Override
public CompletionStage<?> onBinary(
        WebSocket ws, ByteBuffer data, boolean last) {
    byte[] copy = new byte[data.remaining()];
    data.get(copy); // Chỉ đọc phần dữ liệu hiện có.

    appendBinaryFragment(copy); // Mã ứng dụng cần giới hạn kích thước.
    if (last) {
        finishBinaryMessage();
    }

    ws.request(1);
    return CompletableFuture.completedFuture(null);
}
```

`appendBinaryFragment` và `finishBinaryMessage` là **hàm giả định** do ứng dụng tự triển khai. Lưu ý `ByteBuffer` nhận được có vòng đời do JDK quản lý: sau khi `CompletionStage` do callback trả về hoàn thành, buffer có thể được reclaim/reuse. Nếu công việc bất đồng bộ còn cần bytes, **copy hoặc chuyển ownership theo hợp đồng rõ ràng** trước khi stage hoàn thành.

### Ping có thể xuất hiện xen giữa các fragment

Vì Ping/Pong là control messages, chúng có thể đến xen kẽ trong một quá trình truyền data message dài. Không được mặc định mọi lần nhận sau `onText(..., false)` đều là `onText`: một `onPing` cũng có thể tiêu thụ demand và cần được xử lý đúng.

Điều đó khiến mô hình "cứ request(1) thì sẽ nhận phần tiếp của text" chỉ đúng nếu callback tiếp theo đúng là text. Code bền vững phải quản lý **demand cho mọi receive methods**, đồng thời lưu trạng thái text/binary message đang được ghép.

## 7. `CompletionStage` trả về từ callback khác với demand

Một `WebSocket.Listener` callback nhận text/binary/ping/pong trả về `CompletionStage<?>`. Đây là một cơ chế **khác** `request(n)`.

Theo Javadoc, stage trả về cho biết **khi nào listener đã xử lý xong dữ liệu được cung cấp để JDK có thể thu hồi/reuse `CharSequence` hoặc `ByteBuffer`**.

Ví dụ:

```java
@Override
public CompletionStage<?> onText(
        WebSocket ws, CharSequence data, boolean last) {
    String snapshot = data.toString();
    ws.request(1);
    return CompletableFuture.runAsync(() -> save(snapshot));
}
```

Đây là đoạn **minh họa** với `save` do ứng dụng định nghĩa. `String snapshot` là bản sao logic có thể giữ sau callback; stage thể hiện vòng đời công việc xử lý, nhưng **vì đã gọi `request(1)` ngay**, client vẫn có thể được phép giao một callback nhận mới **trước khi công việc `save` hoàn thành**.

Javadoc quy định rõ: `CompletionStage` hoàn thành **không phải điều kiện** để WebSocket gọi thêm listener callback nếu còn demand. Vì vậy:

- **Demand:** số lần callback có thể được khởi phát.
- **Stage:** vòng đời xử lý và thời điểm dữ liệu callback có thể được reclaim.
- **Business backpressure:** quyết định khi nào cấp demand mới dựa vào sức chứa/xử lý thực tế.

Hai cơ chế liên quan nhưng không tương đương.

### Nếu muốn xử lý xong mới cấp demand?

Có thể **trì hoãn `request(1)` đến khi tác vụ async hoàn thành**:

```java
@Override
public CompletionStage<?> onText(
        WebSocket ws, CharSequence data, boolean last) {
    String snapshot = data.toString();

    CompletableFuture<Void> processed =
            CompletableFuture.runAsync(
                    () -> process(snapshot), workerExecutor);

    return processed.whenComplete((ignored, error) -> {
        if (error == null) {
            ws.request(1);
        }
    });
}
```

Đây là **method minh họa**, `process` và `workerExecutor` thuộc ứng dụng. Trong thực tế, xử lý từng fragment có thể không đúng định dạng; tốt hơn tích lũy message theo `last` và chỉ xử lý khi đủ, như mẫu đầy đủ ở phần 8.

Cần xác định chính sách khi tác vụ lỗi: không tự cấp thêm demand rồi bỏ qua lỗi; có thể để `CompletionStage` exceptional để JDK gọi `onError` hoặc đóng kết nối theo protocol.

### Không giữ reference dữ liệu quá vòng đời stage

Với `onText`, `CharSequence data` có thể bị JDK reclaim sau khi returned stage hoàn thành; không giữ raw reference để worker dùng về sau nếu stage đã hoàn thành. Với `onBinary`/`onPing`/`onPong`, `ByteBuffer` cũng có quy tắc tương tự.

An toàn nhất khi đẩy công việc ra ngoài callback là **chụp dữ liệu** thành `String` hoặc `byte[]` do ứng dụng sở hữu. Không dựa vào mutable buffer của JDK còn nguyên sau khi callback đã kết thúc.

### Callback trên cùng WebSocket được tuần tự hóa

`WebSocket.Listener` đảm bảo các callback của **cùng một WebSocket** không được gọi đồng thời; callback kế tiếp chỉ có thể bắt đầu sau khi callback hiện tại **trả về**. Đây là quan hệ **non-reentrant**.

Tuy nhiên, callback kế tiếp có thể bắt đầu khi `CompletionStage` của callback trước vẫn đang chờ. Và nếu cùng một listener instance được dùng cho **nhiều WebSocket**, các callback từ những kết nối khác nhau có thể chạy đồng thời, nên state dùng chung phải được đồng bộ rõ ràng. Không dùng tính tuần tự của một kết nối để kết luận mọi xử lý async trong ứng dụng được tuần tự.

## 8. Mẫu listener có backpressure theo message hoàn chỉnh

Mẫu sau quản lý hai khía cạnh:

1. **Mỗi fragment không phải cuối** được tích lũy và xin callback kế tiếp để tiếp tục nhận message đang dở.
2. Khi nhận **fragment cuối**, ứng dụng chuyển message hoàn chỉnh cho worker executor và **chỉ request tiếp sau khi xử lý xong**. Điều này tránh gửi hàng loạt message vào một queue không giới hạn khi công việc downstream chậm.

Mẫu chỉ nhận **text messages**. Nếu giao thức yêu cầu binary, hãy triển khai parser binary riêng thay vì silently bỏ byte.

```java
import java.net.http.WebSocket;
import java.nio.ByteBuffer;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionStage;
import java.util.concurrent.Executor;
import java.util.function.Consumer;

public final class BoundedTextListener implements WebSocket.Listener {
    private static final int MAX_CHARS = 1_000_000;

    private final Executor worker;
    private final Consumer<String> sink;
    private final StringBuilder partial = new StringBuilder();

    public BoundedTextListener(
            Executor worker, Consumer<String> sink) {
        this.worker = worker;
        this.sink = sink;
    }

    @Override
    public void onOpen(WebSocket ws) {
        ws.request(1);
    }

    @Override
    public CompletionStage<?> onText(
            WebSocket ws, CharSequence fragment, boolean last) {

        if (fragment.length() > MAX_CHARS - partial.length()) {
            throw new IllegalStateException("Text message too large");
        }

        // Copy nội dung fragment khi nó vẫn còn hợp lệ.
        partial.append(fragment);

        if (!last) {
            // Xin thêm lượt cho phần tiếp, kể cả có Ping xen giữa.
            ws.request(1);
            return CompletableFuture.completedFuture(null);
        }

        String complete = partial.toString();
        partial.setLength(0);

        CompletableFuture<Void> processed =
                CompletableFuture.runAsync(
                        () -> sink.accept(complete), worker);

        // Không cấp demand cho message mới khi worker còn bận.
        return processed.whenComplete((ignored, error) -> {
            if (error == null) {
                ws.request(1);
            }
        });
    }

    @Override
    public CompletionStage<?> onPing(
            WebSocket ws, ByteBuffer data) {
        // JDK tự động trả Pong theo protocol.
        ws.request(1);
        return CompletableFuture.completedFuture(null);
    }

    @Override
    public CompletionStage<?> onPong(
            WebSocket ws, ByteBuffer data) {
        ws.request(1);
        return CompletableFuture.completedFuture(null);
    }

    @Override
    public CompletionStage<?> onBinary(
            WebSocket ws, ByteBuffer data, boolean last) {
        throw new IllegalStateException(
                "Binary messages not supported");
    }

    @Override
    public CompletionStage<?> onClose(
            WebSocket ws, int statusCode, String reason) {
        // Kết thúc nhận, không request thêm.
        return CompletableFuture.completedFuture(null);
    }

    @Override
    public void onError(WebSocket ws, Throwable error) {
        // Ghi log đã loại thông tin nhạy cảm và báo lỗi cho ứng dụng.
        System.err.println(
                "WebSocket receive failed: " +
                error.getClass().getSimpleName());
    }
}
```

Đặt class trong **`BoundedTextListener.java`**, biên dịch:

```bash
javac --release 11 BoundedTextListener.java
```

Đây là **class có thể biên dịch**, không có `main`. Khi dùng, tạo `Executor` có giới hạn và `Consumer<String>` thực hiện công việc của ứng dụng, sau đó truyền listener cho `buildAsync`.

**Giới hạn thiết kế cần hiểu:** Mẫu này giới hạn số ký tự text tích lũy trong một message và trì hoãn demand giữa các message; nó **không** tự thiết lập hàng đợi bounded cho worker executor, không giới hạn tổng kích thước binary frame, không bảo đảm chống mọi kiểu flooding/DoS ở tầng network. Nếu `sink.accept` lỗi, stage sẽ hoàn thành exceptional và JDK có thể gọi `onError`; production phải xử lý shutdown, telemetry và resource cleanup thích hợp.

Một điều tinh tế: trong tình huống message bị phân mảnh, mã request tiếp cho từng fragment và Ping/Pong để message có thể hoàn tất; sau fragment cuối chỉ cấp demand khi message đã xử lý. Đây là backpressure **ở ranh giới message**, xây trên primitive demand **ở ranh giới callback**.

## 9. Chương trình Java 11+ đầy đủ: kiểm tra request(1) với WebSocket thật trên loopback

Để thấy rõ `request(n)` thực sự điều tiết callback, dùng một WebSocket server fixture cực nhỏ chạy trên loopback (`127.0.0.1`). Server thực hiện handshake WebSocket chuẩn theo RFC 6455, gửi hai **text messages** "ONE" và "TWO", sau đó gửi Close với mã 1000.

Client có listener được thiết kế:

- `onOpen` chỉ gọi `request(1)`.
- `onText` nhận một callback nhưng **không tự request tiếp**.
- Sau khi nhận "ONE", dù server đã gửi "TWO", listener vẫn chưa được cấp quyền callback thứ hai.
- Chỉ khi code gọi thêm `socket.request(1)`, callback thứ hai mới được giao.
- Cần cấp **một demand nữa** để `onClose` được gọi.
- `request(0)` phải ném `IllegalArgumentException`.

**Fixture dùng local socket để test**, không liên hệ server Internet và không dùng credential. Nó không thay thế production WebSocket server; mục đích là quan sát chính xác hợp đồng Java Client.

Lưu nguyên chương trình thành **`WebSocketDemandDemo.java`**:

```java
import java.io.BufferedReader;
import java.io.InputStreamReader;
import java.io.OutputStream;
import java.net.InetAddress;
import java.net.ServerSocket;
import java.net.Socket;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.WebSocket;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.Base64;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionStage;
import java.util.concurrent.TimeUnit;

public class WebSocketDemandDemo {
    static void sendFrame(
            OutputStream out, int opcode, byte[] content)
            throws Exception {
        if (content.length >= 126) {
            throw new IllegalArgumentException();
        }
        out.write(0x80 | opcode);
        out.write(content.length);
        out.write(content);
        out.flush();
    }

    static void runServer(ServerSocket listener) {
        try (Socket socket = listener.accept()) {
            BufferedReader reader = new BufferedReader(
                    new InputStreamReader(
                            socket.getInputStream(),
                            StandardCharsets.US_ASCII));
            String line;
            String key = null;

            while ((line = reader.readLine()) != null && !line.isEmpty()) {
                if (line.regionMatches(
                        true, 0, "Sec-WebSocket-Key:", 0, 18)) {
                    key = line.substring(18).trim();
                }
            }

            if (key == null) {
                throw new IllegalStateException("Missing WebSocket key");
            }

            byte[] hash = MessageDigest.getInstance("SHA-1").digest(
                    (key + "258EAFA5-E914-47DA-95CA-C5AB0DC85B11")
                            .getBytes(StandardCharsets.US_ASCII));
            String accept =
                    Base64.getEncoder().encodeToString(hash);

            OutputStream out = socket.getOutputStream();
            String handshake =
                    "HTTP/1.1 101 Switching Protocols\r\n"
                    + "Upgrade: websocket\r\n"
                    + "Connection: Upgrade\r\n"
                    + "Sec-WebSocket-Accept: " + accept + "\r\n\r\n";

            out.write(
                    handshake.getBytes(StandardCharsets.US_ASCII));
            out.flush();

            // Server gửi hai text messages rồi Close.
            sendFrame(out, 1, "ONE".getBytes(StandardCharsets.UTF_8));
            sendFrame(out, 1, "TWO".getBytes(StandardCharsets.UTF_8));
            sendFrame(out, 8, new byte[]{3, (byte) 0xE8});
            Thread.sleep(1500);
        } catch (Exception e) {
            throw new RuntimeException(e);
        }
    }

    static final class MeteredListener implements WebSocket.Listener {
        final List<String> events =
                Collections.synchronizedList(
                        new ArrayList<String>());
        final CompletableFuture<String> first =
                new CompletableFuture<>();
        final CompletableFuture<String> second =
                new CompletableFuture<>();
        final CompletableFuture<Integer> closed =
                new CompletableFuture<>();

        @Override
        public void onOpen(WebSocket socket) {
            events.add("open");
            socket.request(1);
        }

        @Override
        public CompletionStage<?> onText(
                WebSocket socket, CharSequence data, boolean last) {
            String value = data.toString();
            events.add("text=" + value + ",last=" + last);
            if (!first.isDone()) {
                first.complete(value);
            } else {
                second.complete(value);
            }
            // Cố ý KHÔNG request(1) ở đây.
            return CompletableFuture.completedFuture(null);
        }

        @Override
        public CompletionStage<?> onClose(
                WebSocket socket, int code, String reason) {
            events.add("close=" + code);
            closed.complete(code);
            return CompletableFuture.completedFuture(null);
        }

        @Override
        public void onError(WebSocket socket, Throwable error) {
            first.completeExceptionally(error);
            second.completeExceptionally(error);
            closed.completeExceptionally(error);
        }
    }

    public static void main(String[] args) throws Exception {
        try (ServerSocket server = new ServerSocket(
                0, 1, InetAddress.getLoopbackAddress())) {

            CompletableFuture<Void> serving =
                    CompletableFuture.runAsync(
                            () -> runServer(server));

            MeteredListener meter = new MeteredListener();
            WebSocket socket = HttpClient.newHttpClient()
                    .newWebSocketBuilder()
                    .buildAsync(
                            URI.create(
                                    "ws://127.0.0.1:"
                                    + server.getLocalPort() + "/demo"),
                            meter)
                    .get(4, TimeUnit.SECONDS);

            System.out.println(
                    "first=" + meter.first.get(4, TimeUnit.SECONDS));

            try {
                socket.request(0);
                System.out.println("zeroRejected=false");
            } catch (IllegalArgumentException expected) {
                System.out.println("zeroRejected=true");
            }

            Thread.sleep(150);
            long seen = meter.events.stream()
                    .filter(e -> e.startsWith("text="))
                    .count();
            System.out.println(
                    "beforeSecondCredit=" + seen);

            socket.request(1);
            System.out.println(
                    "second=" + meter.second.get(4, TimeUnit.SECONDS));

            socket.request(1);
            System.out.println(
                    "close=" + meter.closed.get(4, TimeUnit.SECONDS));

            System.out.println("events=" + meter.events);
            serving.get(4, TimeUnit.SECONDS);
        }
    }
}
```

Biên dịch/chạy với JDK 11 hoặc mới hơn:

```bash
javac --release 11 WebSocketDemandDemo.java
java WebSocketDemandDemo
```

**Stdout đã kiểm chứng bằng WebSocket handshake và frame thực tế:**

```text
first=ONE
zeroRejected=true
beforeSecondCredit=1
second=TWO
close=1000
events=[open, text=ONE,last=true, text=TWO,last=true, close=1000]
```

### Điều gì đã xảy ra?

1. `onOpen` xin `request(1)`, nên client được phép gọi một receive callback đầu tiên.
2. Server gửi cả "ONE", "TWO" và Close; callback `onText("ONE", true)` tiêu thụ demand còn lại. Listener cố tình **không** xin thêm.
3. Dòng `beforeSecondCredit=1` cho biết tại thời điểm kiểm tra chỉ có một callback text đã được giao, dù server đã gửi message thứ hai.
4. `socket.request(1)` trong `main` cấp một đơn vị mới, cho phép callback `onText("TWO", true)`.
5. `socket.request(1)` tiếp theo cho phép callback `onClose(..., 1000, ...)`. `onClose` cũng thuộc nhóm tiêu thụ demand.
6. `request(0)` ném `IllegalArgumentException` theo Javadoc; chương trình ghi `zeroRejected=true`.
7. Kết quả `events` cho thấy thứ tự callback sau khi cấp demand; không có hai callback text nào được tự kích hoạt khi demand bằng 0.

**Cảnh báo sử dụng fixture:** Server ở đây gửi các frame đơn giản, rất ngắn, không đòi hỏi TLS, authentication hay xử lý nhiều client. Không sử dụng class fixture này làm production server. Phần timestamp/lịch thực thi trong WebSocket thật có thể khác; các assertion nội dung trên được đặt theo điểm đồng bộ `CompletableFuture` của listener.

## 10. Vì sao chỉ trả `completedFuture(null)` không tự cấp thêm lượt?

Một lỗi phổ biến là viết:

```java
@Override
public CompletionStage<?> onText(
        WebSocket ws, CharSequence data, boolean last) {
    process(data);
    return CompletableFuture.completedFuture(null);
}
```

Khi được gọi một lần, callback xử lý xong và trả stage đã hoàn tất; tuy nhiên **demand không được bổ sung**. Nếu trước đó chỉ có `request(1)`, bộ đếm đã về 0, nên listener không tiếp tục nhận data.

Một biến thể tương tự:

```java
@Override
public CompletionStage<?> onText(
        WebSocket ws, CharSequence data, boolean last) {
    process(data);
    return null;
}
```

Javadoc cho phép trả `null` và coi như một stage đã hoàn tất bình thường để JDK có thể reclaim dữ liệu; **điều đó vẫn không tự bổ sung demand**. Muốn nhận thêm callback, phải gọi `request(n)` rõ ràng hoặc thiết kế stage/completion handler cấp demand khi downstream sẵn sàng.

Nói cách khác: **stage complete ≠ request(1)**.

Nếu viết listener dựa vào default `onText` mà không override, default có `request(1)`. Nhưng việc tự override và chỉ trả `null` làm mất chính hành vi cấp demand đó.

## 11. `onClose`, `onError` và cách kết thúc connection

### `onClose` là receive callback cuối

`onClose` được gọi khi nhận Close message, và là **một receive method chịu điều tiết demand**. Với WebSocket Client, khi `onClose` bắt đầu thì phía input đã đóng; sau callback này sẽ không còn callback khác cho cùng connection.

```java
@Override
public CompletionStage<?> onClose(
        WebSocket ws, int statusCode, String reason) {
    System.out.println("Closed: " + statusCode);
    return CompletableFuture.completedFuture(null);
}
```

Nếu phía output chưa đóng, completion của stage từ `onClose` là tín hiệu cho WebSocket có thể đóng output; JDK tự xử lý việc đáp ứng Close theo hợp đồng. Bạn không phải tự gửi Pong cho Ping hoặc tự xử lý Close handshake trong mọi ứng dụng. Nhưng ứng dụng có thể dùng `sendClose` khi cần chủ động đóng kết nối với status/reason phù hợp.

**`sendClose(...)` và `request(n)` không phải cùng thao tác.** `sendClose` bắt đầu đóng phía **output**, không nhất thiết đóng ngay phía input. Muốn đóng đột ngột hai phía, có `abort()`; chỉ dùng khi chính sách/timeout yêu cầu, không coi là đóng kết nối graceful.

### `onError` không chờ demand

`onError(WebSocket, Throwable)` có thể được gọi ngay cả khi demand bằng 0. Khi callback này xảy ra, phía input và output đã đóng và không còn listener callbacks nào khác sau đó cho kết nối này.

```java
@Override
public void onError(WebSocket ws, Throwable error) {
    logSanitized(error); // Hàm ứng dụng, không phải API JDK.
}
```

Đoạn trên chỉ là **method minh họa**. Không ném thêm exception từ `onError`: Javadoc nêu hành vi khi callback này ném lỗi là không xác định. Hãy báo lỗi cho hệ thống quan sát theo chính sách đã che dữ liệu nhạy cảm.

### Cẩn thận với demand bằng 0 khi cần biết peer đã đóng

Vì `onClose` là receive method, nếu ứng dụng không cấp thêm demand, một Close message có thể chưa được báo tới listener đúng lúc. Đừng thiết kế "pause vô thời hạn" rồi giả định `onClose` chắc chắn đã được giao để dọn resources. Cần quy định deadline, trạng thái app, timeout, hoặc chủ động `abort()` khi connection không thể tiếp tục và đã vượt chính sách chờ.

Mặc dù vậy, không dùng `request(Long.MAX_VALUE)` chỉ để "bảo đảm onClose đến": điều này khiến phần điều tiết callback trở nên gần như không còn ý nghĩa. Hãy chọn mức demand phù hợp, hoặc có chiến lược lifecycle riêng.

## 12. Backpressure ở WebSocket không phải áp lực toàn hệ thống

### `request(n)` là điều tiết callback, không bảo đảm peer dừng gửi

Khi demand về 0, Java không gọi thêm receive callback, nhưng **peer vẫn có thể gửi bytes lên mạng**. Buffer của hệ điều hành, TCP flow control, HTTP/WebSocket implementation và bộ đệm khác có thể chịu ảnh hưởng theo thời gian. `request(n)` không phải một lệnh gửi tới server nói "tôi chỉ cho phép gửi đúng n message".

Do đó:

- `request(n)` điều tiết **nhịp giao data đến ứng dụng**.
- TCP flow control có thể gián tiếp hạn chế lượng dữ liệu peer có thể gửi, nhưng không phải một SLA dung lượng queue hoặc kích thước buffer ở mọi tầng.
- Muốn phối hợp với server ở cấp ứng dụng, có thể cần protocol riêng về credit/window/ack/slow consumer hoặc giới hạn tốc độ.
- Bộ nhớ của ứng dụng phải được bảo vệ bởi queue bounded, giới hạn kích thước message, timeout và chính sách bỏ/ngắt kết nối khi quá tải.

Nếu listener nhận được payload quá lớn, có thể throw exception hoặc abort theo contract thay vì tích lũy không giới hạn.

### Không nhầm receive demand với send backpressure

`WebSocket.request(n)` ảnh hưởng **các callback nhận**. Nó không làm thay đổi số lần `sendText`, `sendBinary` được phép gửi.

Ở phía gửi, các phương thức như `sendText`/`sendBinary` trả `CompletableFuture<WebSocket>` phản ánh tiến độ gửi. Nếu ứng dụng gửi nhiều messages, phải quản lý hàng đợi và thứ tự send theo hợp đồng, ví dụ nối chuỗi các futures khi cần:

```java
webSocket.sendText("first", true)
        .thenCompose(ws -> ws.sendText("second", true))
        .exceptionally(error -> {
            logSanitized(error); // Hàm ứng dụng.
            return null;
        });
```

Đây là **đoạn minh họa**; handling exception và lifecycle cụ thể tùy ứng dụng. `request(n)` không điều tiết `sendText` và cũng không cho phép bỏ qua trạng thái send pending.

### Khác với `Flow.Subscription.request(n)`

Javadoc WebSocket so sánh quan hệ WebSocket–Listener với `Flow.Subscription`–`Flow.Subscriber`. Nhưng đây là **hai API riêng biệt**:

| `WebSocket.request(n)` | `Flow.Subscription.request(n)` |
| --- | --- |
| Cấp lượt gọi `onText/onBinary/onPing/onPong/onClose` | Cấp demand cho các item `onNext` trong Flow |
| Một lần callback chưa chắc là một message hoàn chỉnh | Một item `onNext` là một phần tử của Publisher theo contract đó |
| `onOpen` đóng vai trò khởi tạo demand | `Flow.Subscriber.onSubscribe` nhận Subscription |
| `onError` không tiêu thụ demand | `onError` của Flow cũng là tín hiệu lỗi, nhưng thuộc lifecycle khác |
| Có `last` để báo fragment cuối | `onNext` không có `last` chung cho mọi Publisher |

Đừng lấy code `Flow.Subscriber` thay `WebSocket.Listener` mà bỏ qua các callback đặc thù WebSocket.

## 13. Điều tiết bằng từng batch `request(n)`

Không phải hệ thống nào cũng cần `request(1)`. Khi downstream có sức chứa nhất định, có thể cấp một **batch** demand:

```java
@Override
public void onOpen(WebSocket ws) {
    ws.request(8);
}
```

Điều này cho phép tối đa tám callback nhận trước khi cần cấp demand mới. Nhưng **không đồng nghĩa tối đa tám message**, vì fragment, ping, pong và close đều tiêu thụ lượt.

Chiến lược batch phù hợp khi:

- Có bộ xử lý downstream và queue **bounded** đủ chỗ cho số callback dự kiến.
- Một callback được xử lý nhanh, kích thước được kiểm soát.
- Hệ thống có đo đạc backlog và chỉ refill demand sau khi giải phóng capacity.

Chiến lược batch không phù hợp khi mỗi callback có thể chứa một message rất lớn mà hệ thống chưa áp dụng giới hạn kích thước, hoặc khi thiếu tiêu chí cấp lại demand. `request(1000)` không tự biến WebSocket thành "nhanh hơn" nếu CPU, disk hoặc network là bottleneck.

### Tránh cộng demand vô tình

Nếu `onOpen` đã `request(8)`, và **mỗi callback lập tức `request(8)`** nữa, demand sẽ tăng dần rất nhanh. Với mục tiêu cửa sổ tối đa tám lượt, thường nên thiết kế rõ số credit đã cấp và số đã sử dụng, cấp bù theo capacity, không tăng theo cấp số nhiều.

Nếu muốn nghiêm ngặt "xử lý xong một callback thì cấp bù một lượt" cho cửa sổ n callback, có thể khởi đầu `request(n)` rồi sau mỗi phần việc hoàn tất **cấp bù đúng một lượt**, nhưng phải quản lý số callback đã được cấp và đặc biệt xử lý message phân mảnh phù hợp. Mọi queue, worker và byte budget vẫn cần được kiểm soát độc lập.

## 14. Vấn đề về threading, buffer và vận hành lâu dài

### Threading

Các callback của **một WebSocket instance** được gọi tuần tự, không reentrant. Nhưng không có nghĩa chúng luôn chạy trên UI thread hay một thread cố định. Không block event/HTTP client threads bằng thao tác database dài; khi cần, chuyển xử lý nặng sang executor chuyên dụng.

`request(n)` có thể được gọi từ nơi ứng dụng sẵn sàng xử lý thêm, không nhất thiết chỉ từ `onOpen`/`onText`. Chương trình loopback ở phần 9 cố ý gọi từ `main` sau khi nhận tín hiệu đầu tiên. Vì thế cơ chế cấp demand có thể kết hợp với queue callback, UI lifecycle hoặc worker hoàn thành task.

### Vòng đời dữ liệu

- `CharSequence` từ `onText`: không truy cập sau khi returned stage hoàn thành, nếu cần giữ lâu hãy copy thành `String`.
- `ByteBuffer` từ `onBinary`, `onPing`, `onPong`: đọc từ `position` đến `limit`, copy nếu xử lý bất đồng bộ sau callback/stage.
- `last` giúp phân định text/binary message hoàn chỉnh, không phải "lượt callback cuối của kết nối".
- Nếu `CompletionStage` trả về hoàn thành exceptionally hoặc callback throw, WebSocket có thể gọi `onError`; xử lý thông tin lỗi rõ ràng và an toàn.
- Giữ riêng trạng thái của các WebSocket khác nhau, hoặc đồng bộ/actor-model hóa nếu cùng listener instance được tái sử dụng.

### Timeout và shutdown

Không duy trì kết nối "im lặng mãi mãi" chỉ vì bộ đếm demand bằng 0. Với ứng dụng thật, nên có chính sách connection liveness, idle timeout, heartbeat/ping và graceful shutdown phù hợp hệ thống. WebSocket API không thay thế toàn bộ protocol-level heartbeat, reconnect/backoff hay auth token refresh.

Khi cần đóng bình thường:

```java
webSocket.sendClose(WebSocket.NORMAL_CLOSURE, "done")
        .whenComplete((ignored, error) -> {
            if (error != null) {
                webSocket.abort();
            }
        });
```

Đây là đoạn minh họa. `sendClose` khởi đầu đóng phía gửi; phía nhận có thể vẫn mở cho tới khi nhận Close từ peer, bị abort hoặc lỗi. Không thực hiện reconnect tự phát vô hạn khi nhận lỗi authentication hoặc status không được hỗ trợ.

## 15. Lỗi thường gặp và hướng sửa

| Triệu chứng | Nguyên nhân | Cách khắc phục |
| --- | --- | --- |
| WebSocket connect thành công nhưng không có `onText` | Override `onOpen` mà không gọi `request(1)` | Cấp demand đầu tiên tại `onOpen` |
| Chỉ nhận được một callback | Callback custom không gọi request tiếp | Chủ động `request(1)` khi sẵn sàng |
| Dừng giữa một text message dài | Chỉ request khi `last=true`; mảnh đầu `last=false` tiêu thụ demand | Request sau từng mảnh chưa cuối |
| Một Ping khiến data không đến nữa | Override `onPing` nhưng quên cấp demand mới | Request tiếp trong onPing hoặc dùng default |
| `request(2)` không nhận hai text messages | Demand đếm callback, Ping/Pong và fragmentation cũng tiêu thụ | Đếm callback thực, dùng `last` để ghép message |
| `request(0)` bị exception | `n <= 0` không hợp lệ | Không request khi muốn pause; chỉ cấp số dương khi sẵn sàng |
| Trả `completedFuture(null)` nhưng pipeline vẫn dừng | Stage hoàn thành không tăng demand | Tách rõ stage lifecycle và `request(n)` |
| Work queue phình to dù có request(1) | Callback ngay lập tức enqueue rồi request tiếp | Refill khi capacity được giải phóng, áp dụng queue bounded |
| Dữ liệu binary thay đổi sau khi xử lý async | Giữ reference tới JDK-owned `ByteBuffer` sau stage | Copy byte trong callback hoặc giữ stage chưa hoàn thành đến khi xử lý xong |
| Ghép JSON thất bại | Parse từng fragment như message hoàn chỉnh | Gom đến `last=true`, đặt giới hạn byte/ký tự |
| Kết nối Close không được báo trong listener | `onClose` là receive callback, demand bằng 0 | Thiết kế lifecycle/demand để close được xử lý, có timeout/abort policy |
| Lỗi vẫn đến khi đã pause nhận | `onError` không chịu điều tiết demand | Luôn xử lý onError, không coi pause là vô hiệu hóa lỗi |
| Dữ liệu từ nhiều WebSocket ghi đè nhau | Một listener chia sẻ state không đồng bộ | State per-connection, đồng bộ hoặc queue/actor |
| Nhầm request(n) với gửi n messages | `request` thuộc hướng nhận; send có API khác | Quản lý `sendText`/`sendBinary` riêng |
| Tin rằng `request(n)` giới hạn memory tuyệt đối | OS/network buffers vẫn tồn tại | Giới hạn message, queue, processing, timeout và transport policy |
| Sử dụng API incubator cũ của Java 9/10 | Đọc nhầm package `jdk.incubator.http` | Dùng `java.net.http.WebSocket` chính thức từ Java 11 |

## 16. Câu hỏi tự kiểm tra kèm đáp án

**1.** `webSocket.request(3)` nghĩa là chắc chắn sẽ nhận ba message hoàn chỉnh?

**Đáp án:** Không. Nó cho phép thêm tối đa ba **receive callback invocations**, có thể gồm mảnh text/binary hoặc Ping/Pong/Close. Số message hoàn chỉnh có thể ít hơn ba.

**2.** Vì sao một listener mới kết nối nhưng override `onOpen` rỗng có thể không bao giờ nhận `onText`?

**Đáp án:** Demand ban đầu bằng 0. Khi override `onOpen`, default method vốn `request(1)` không còn được chạy, nên client phải chủ động cấp demand.

**3.** `onOpen` và `onError` có tiêu thụ demand không?

**Đáp án:** Không. `onOpen` chạy đầu tiên và thường cấp demand; `onError` có thể đến bất kỳ lúc nào, không phụ thuộc demand.

**4.** `onClose` có phải receive method và tiêu thụ demand không?

**Đáp án:** Có, theo Javadoc `WebSocket`. `onClose` là callback cuối cho connection và cần được tính trong chính sách điều tiết.

**5.** Một text message được giao qua `onText("A", false)` rồi `onText("B", true)`. Cần bao nhiêu demand?

**Đáp án:** Hai đơn vị demand để cho phép hai callback; đó vẫn chỉ là một message `"AB"`.

**6.** Chỉ gọi `request(1)` khi `last=true`, nhưng message đầu có fragment `last=false`. Điều gì có thể xảy ra?

**Đáp án:** Pipeline có thể dừng vì đã tiêu thụ demand mà chưa xin phần tiếp. Cần request tiếp sau fragment chưa cuối.

**7.** `request(0)` hoặc `request(-5)` có dùng để tạm dừng/cancel nhận không?

**Đáp án:** Không. `request(n)` yêu cầu `n > 0`, nếu không ném `IllegalArgumentException`. Muốn tạm không cấp thêm callback thì ngừng request mới; đóng connection dùng `sendClose`/`abort` theo chính sách.

**8.** Khi returned `CompletionStage` từ `onText` đã hoàn thành nhưng không gọi `request`, client tự cấp demand mới không?

**Đáp án:** Không. Stage không phải demand. Chỉ có call `request(n)` hoặc logic mặc định của những callback chưa override mới cấp thêm demand.

**9.** Nếu `onPing` được override, có cần làm gì để tránh kẹt receive flow?

**Đáp án:** Cần xem xét cấp demand tiếp theo (ví dụ `request(1)`) khi sẵn sàng, vì Ping tiêu thụ một lượt. JDK tự gửi Pong; thường không cần tự `sendPong`.

**10.** Có thể giữ `ByteBuffer` do `onBinary` cung cấp sau khi stage hoàn thành không?

**Đáp án:** Không được dựa vào đó; JDK có thể reclaim/reuse dữ liệu. Copy byte ra vùng ứng dụng sở hữu nếu còn cần sau callback/stage.

**11.** Listener trả một future chưa hoàn thành và đã `request(1)` trong callback. Callback tiếp theo có nhất thiết chờ future đó hoàn thành?

**Đáp án:** Không. Theo Javadoc, việc hoàn thành `CompletionStage` độc lập với bộ đếm demand; callback kế tiếp có thể bắt đầu sau khi callback hiện tại trả về, dù stage trước còn chờ.

**12.** Nếu muốn xử lý message hoàn chỉnh lần lượt, cách nào đơn giản?

**Đáp án:** Request tiếp cho từng fragment chưa cuối để gom đủ message. Khi `last=true`, xử lý message (đồng bộ hoặc async), chỉ request thêm khi downstream sẵn sàng; quản lý cả Ping/Pong và giới hạn kích thước.

**13.** `WebSocket.request(n)` có chặn phía server gửi thêm bytes qua TCP không?

**Đáp án:** Không trực tiếp. Nó hạn chế callback giao đến listener. TCP flow control và buffering có cơ chế riêng; cần thêm protocol/queue limits nếu muốn kiểm soát áp lực end-to-end.

**14.** Tại sao `request(8)` rồi sau mỗi callback lại `request(8)` là nguy hiểm?

**Đáp án:** Demand tăng thêm quá nhanh so với số lượt đã tiêu thụ; thiết kế cửa sổ nhận mất ý nghĩa và có thể quá tải downstream. Cấp bù credit theo sức chứa thực tế.

**15.** Có thể dùng `Flow.Subscription.request(n)` thay cho `WebSocket.request(n)` không?

**Đáp án:** Không. Chúng là hai API khác nhau, dù đều mô tả demand. `WebSocket` dùng trực tiếp `WebSocket.Listener` và các callback đặc thù.

## Tài liệu chính thức còn áp dụng

- [Java SE 11 — `java.net.http.WebSocket`](https://docs.oracle.com/en/java/javase/11/docs/api/java.net.http/java/net/http/WebSocket.html): định nghĩa `request(long)`, bộ đếm callback, `n <= 0`, `sendClose`/`abort` và phân biệt nhận/gửi.
- [Java SE 11 — `WebSocket.Listener`](https://docs.oracle.com/en/java/javase/11/docs/api/java.net.http/java/net/http/WebSocket.Listener.html): `onOpen`, `onText`, `onBinary`, `onPing`, `onPong`, `onClose`, `onError`, default request và vòng đời `CompletionStage`.
- [Java SE 26 — `WebSocket.Listener`](https://docs.oracle.com/en/java/javase/26/docs/api/java.net.http/java/net/http/WebSocket.Listener.html): xác nhận các quy tắc callback, stage và demand vẫn áp dụng ở JDK hiện hành.
- [Java SE 25 — `java.net.http.WebSocket`](https://docs.oracle.com/en/java/javase/25/docs/api/java.net.http/java/net/http/WebSocket.html): tham khảo hành vi request/counter ở phiên bản gần đây.
- [Java SE 11 — `HttpClient`](https://docs.oracle.com/en/java/javase/11/docs/api/java.net.http/java/net/http/HttpClient.html): tạo `WebSocket.Builder` qua `newWebSocketBuilder()`.
- [RFC 6455 — The WebSocket Protocol](https://www.rfc-editor.org/rfc/rfc6455.html): frame, continuation, Ping/Pong, Close handshake, phần framing của protocol.

**Ghi nhớ:** `request(n)` là **quyền giao thêm n callback nhận**, không phải quyền giao n message. `onOpen` và `onError` nằm ngoài bộ đếm; `onText/onBinary/onPing/onPong/onClose` đều tiêu thụ demand. Xử lý `last` để ghép message, giữ riêng `CompletionStage` với demand và chỉ cấp thêm credit khi tầng xử lý có khả năng tiếp nhận an toàn.