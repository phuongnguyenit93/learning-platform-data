# CompletionStage từ WebSocket.Listener và thời điểm hoàn tất xử lý trong Java 11+

## 1. Vấn đề: callback đã trả về có nghĩa dữ liệu đã xử lý xong chưa?

Từ **Java 11**, `java.net.http.WebSocket` và `WebSocket.Listener` là HTTP Client/WebSocket API chuẩn của JDK. Khi nhận text, binary, ping hoặc pong, WebSocket gọi một phương thức trên listener, chẳng hạn:

```java
CompletionStage<?> onText(
        WebSocket webSocket, CharSequence data, boolean last);
```

Điểm dễ nhầm là phương thức trả về **hai thứ khác nhau ở hai thời điểm**:

1. **Phương thức `onText(...)` trả về Java call stack**: listener đã hoàn tất phần thực thi đồng bộ của *lần callback hiện tại*. Nó có thể vừa trả về một `CompletionStage` **chưa hoàn thành**.
2. **`CompletionStage` được trả về hoàn thành**: đó là tín hiệu rằng listener đã nhận/xử lý đủ dữ liệu đầu vào của callback theo hợp đồng, và WebSocket **được phép thu hồi hoặc tái sử dụng** đối tượng dữ liệu đã truyền vào (`CharSequence` hoặc `ByteBuffer`). Không đọc/đụng vào đối tượng đó sau khi stage đã hoàn thành.

**Quan trọng nhất:** một `CompletionStage` còn pending **không tự khóa việc gọi listener tiếp theo**. API định nghĩa một cơ chế **`webSocket.request(n)` riêng** để điều khiển số lượng callback nhận vào. WebSocket có thể gọi callback mới sau khi **phương thức listener trước đã trả về**, ngay cả khi `CompletionStage` của callback trước **chưa hoàn thành**, miễn là demand cho phép. Đây là khác biệt giữa **kết thúc lời gọi callback**, **hoàn tất stage**, và **quyền nhận callback tiếp theo**.

Quy tắc này vẫn áp dụng trên các JDK hiện đại. Không được viết code dựa vào giả định “chỉ cần return một future chưa complete là WebSocket sẽ đợi xử lý xong trước khi phát sự kiện mới”.

## 2. Chữ ký các phương thức và ý nghĩa của stage

| Phương thức của `WebSocket.Listener` | Kiểu trả về | Ý nghĩa |
| --- | --- | --- |
| `onOpen(WebSocket)` | `void` | Kết nối đã mở; thường gọi `request(1)` để bắt đầu nhận. |
| `onText(WebSocket, CharSequence, boolean)` | `CompletionStage<?>` | Khi stage hoàn thành, WebSocket có thể thu hồi `CharSequence` của lần callback đó. |
| `onBinary(WebSocket, ByteBuffer, boolean)` | `CompletionStage<?>` | Khi stage hoàn thành, WebSocket có thể thu hồi `ByteBuffer` của lần callback đó. |
| `onPing(WebSocket, ByteBuffer)` | `CompletionStage<?>` | Khi stage hoàn thành, WebSocket có thể thu hồi buffer ping; WebSocket mặc định tự xử lý pong đáp trả. |
| `onPong(WebSocket, ByteBuffer)` | `CompletionStage<?>` | Khi stage hoàn thành, WebSocket có thể thu hồi buffer pong. |
| `onClose(WebSocket, int, String)` | `CompletionStage<?>` | Stage điều khiển thời điểm **phía gửi (output)** có thể được đóng để đáp ứng Close; xem mục 7. |
| `onError(WebSocket, Throwable)` | `void` | Thông báo lỗi kết thúc, **không** có stage trả về. |

Các phương thức receive là `onText`, `onBinary`, `onPing`, `onPong`, `onClose`. `onOpen` và `onError` không thuộc nhóm receive callback chịu bộ đếm demand. Với một WebSocket, Java gọi listener theo thứ tự, không reentrant: lần gọi callback tiếp theo chỉ bắt đầu **sau khi phương thức callback trước trả về**. Nhưng đây **không phải** cam kết đợi stage trước hoàn thành.

Mỗi `WebSocket` quản lý demand riêng và trạng thái đóng riêng. Nếu dùng chung một instance listener cho **nhiều WebSocket khác nhau**, callback từ các kết nối khác nhau **có thể xảy ra đồng thời**; code phải tách state theo kết nối hoặc đồng bộ phù hợp.

## 3. Ba cơ chế cần phân biệt: callback return, stage completion và `request(n)`

### 3.1. Trả về từ callback

`onText(...)` có thể chép dữ liệu vào state của ứng dụng, lên lịch xử lý bất đồng bộ rồi **trả về ngay**. Lúc này call stack đã kết thúc nhưng công việc xử lý dữ liệu trên executor có thể còn đang chạy.

Nếu code không định lưu/đọc lại đối tượng `data` JDK cấp sau khi callback trả về, ví dụ đã copy thành `String` riêng, có thể trả stage đã hoàn tất hoặc `null`. Nếu xử lý dữ liệu dựa trực tiếp vào `data` sau khi callback trả về, phải bảo đảm stage chưa hoàn tất **cho đến khi việc truy cập dữ liệu JDK cấp thực sự xong**.

### 3.2. Stage được hoàn tất

Với `onText`, `onBinary`, `onPing` và `onPong`:

- Trả `null` được xử lý như trả **stage đã hoàn thành bình thường**: có thể thu hồi dữ liệu ngay.
- Trả `CompletableFuture.completedFuture(null)` cũng báo dữ liệu callback có thể thu hồi ngay.
- Trả một `CompletableFuture` chưa hoàn thành có thể giữ quyền sử dụng dữ liệu callback đến khi stage hoàn thành. Khi xử lý xong, gọi `complete(...)`; khi lỗi, gọi `completeExceptionally(error)` nếu thực sự muốn thông báo thất bại cho WebSocket.
- Nếu listener ném exception, hoặc stage trả về hoàn thành exceptionally, WebSocket thông thường báo lỗi tới `onError`, trừ khi hợp đồng của phương thức có quy định khác. Do đó cần phân biệt lỗi xử lý ứng dụng với việc “chờ cho xong”.

Không trả completed stage trong khi một tác vụ khác vẫn giữ và đọc `CharSequence`/`ByteBuffer` gốc. Ngược lại, nếu đã copy dữ liệu cần thiết thành một object thuộc sở hữu ứng dụng thì không nhất thiết giữ stage pending **chỉ để giữ buffer gốc**; có thể theo dõi tiến trình nghiệp vụ bằng future riêng.

### 3.3. `webSocket.request(n)` là điều khiển demand

`request(n)` tăng bộ đếm số **lần gọi receive callback** mà WebSocket được phép thực hiện, không phải số byte và cũng không nhất thiết là số thông điệp hoàn chỉnh. WebSocket trừ bộ đếm khi bắt đầu một receive callback. Nếu bộ đếm bằng 0, WebSocket không phát tiếp receive callback; `onError` có thể được gọi không phụ thuộc bộ đếm.

**Ví dụ:**

```text
onOpen: request(1)           -> cho phép 1 receive callback
onText(data, last=false)     -> tiêu thụ 1 lượt demand
   gọi request(1)            -> cho phép 1 callback tiếp theo
   return pendingStage       -> stage vẫn chưa xong
onText(data, last=true)      -> có thể được gọi sau khi onText trước TRẢ VỀ
                                dù pendingStage trước chưa complete
```

`request(1)` không có nghĩa “nhận 1 message hoàn chỉnh”; một message text/binary có thể được chia thành nhiều lần `onText`/`onBinary` với tham số `last` đánh dấu fragment cuối. `request(0)` hoặc số âm không hợp lệ và ném `IllegalArgumentException`.

**Không đồng nhất `CompletionStage` với bộ đếm demand.** Nếu muốn chủ động chỉ nhận thêm dữ liệu khi đã xử lý xong phần trước, ứng dụng có thể **trì hoãn gọi `request(1)` cho đến khi tác vụ hoàn thành**, thay vì nghĩ rằng future pending sẽ tự chặn callback mới. Cần tính cả callback đóng/ping và đặc tính ứng dụng để không vô tình dừng nhận vô hạn.

## 4. Ví dụ Java 11+ chạy được, không cần kết nối WebSocket thật

Ví dụ dưới đây mô phỏng một `WebSocket` để tập trung vào cách dùng **demand** và **`CompletionStage`**. Đây là **harness kiểm thử listener thuần Java**, không thực hiện handshake hoặc gửi packet qua mạng. `FakeSocket` minh họa phần bộ đếm demand và tự gọi callback sau khi phương thức trước đã trả về; nó **không đại diện đầy đủ** cho triển khai WebSocket của JDK.

Chương trình thử:

1. `onOpen` gọi `request(1)`.
2. Một callback `onText` copy `CharSequence`, gọi `request(1)`, rồi trả future chưa hoàn thành.
3. Vì demand mới đã có và `onText` trước đã **trả về**, harness gọi tiếp `onClose` dù future của text vẫn pending. Với WebSocket thật, đó cũng là một lịch gọi **được phép** theo hợp đồng; không có bảo đảm server sẽ luôn gửi Close đúng lúc này.
4. Hoàn tất future text và future cleanup của Close, quan sát `isDone()` thay đổi.

Lưu vào tệp **`WebSocketStageDemo.java`**:

```java
import java.net.http.WebSocket;
import java.nio.ByteBuffer;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionStage;

public class WebSocketStageDemo {
    public static void main(String[] args) {
        FakeSocket socket = new FakeSocket();
        DemoListener listener = new DemoListener();

        listener.onOpen(socket);
        System.out.println("demandAfterOpen=" + socket.demand);

        CompletionStage<?> textStage =
                socket.deliverText(listener, "hello", true);
        System.out.println("savedText=" + listener.savedText);
        System.out.println("demandAfterText=" + socket.demand);
        System.out.println("textStageDone=" +
                textStage.toCompletableFuture().isDone());

        CompletionStage<?> closeStage =
                socket.deliverClose(listener, WebSocket.NORMAL_CLOSURE, "bye");
        System.out.println("closeWhileTextPending=" +
                !textStage.toCompletableFuture().isDone());
        System.out.println("closeStageDone=" +
                closeStage.toCompletableFuture().isDone());

        listener.processing.complete(null);
        listener.cleanup.complete(null);

        System.out.println("textStageDoneAfter=" +
                textStage.toCompletableFuture().isDone());
        System.out.println("closeStageDoneAfter=" +
                closeStage.toCompletableFuture().isDone());
    }

    static final class DemoListener implements WebSocket.Listener {
        final CompletableFuture<Void> processing = new CompletableFuture<>();
        final CompletableFuture<Void> cleanup = new CompletableFuture<>();
        String savedText;

        @Override
        public void onOpen(WebSocket socket) {
            socket.request(1);
        }

        @Override
        public CompletionStage<?> onText(
                WebSocket socket, CharSequence data, boolean last) {
            savedText = data.toString(); // Copy khỏi CharSequence của JDK.
            socket.request(1);
            return processing;           // Chưa hoàn thành.
        }

        @Override
        public CompletionStage<?> onClose(
                WebSocket socket, int statusCode, String reason) {
            return cleanup;              // Chưa hoàn thành.
        }
    }

    static final class FakeSocket implements WebSocket {
        long demand;
        boolean inputClosed;

        CompletionStage<?> deliverText(
                WebSocket.Listener listener, String text, boolean last) {
            useOneDemand();
            return listener.onText(this, new StringBuilder(text), last);
        }

        CompletionStage<?> deliverClose(
                WebSocket.Listener listener, int statusCode, String reason) {
            useOneDemand();
            inputClosed = true;
            return listener.onClose(this, statusCode, reason);
        }

        private void useOneDemand() {
            if (demand == 0) {
                throw new IllegalStateException("No receive demand");
            }
            demand--;
        }

        @Override
        public void request(long n) {
            if (n <= 0) {
                throw new IllegalArgumentException("n must be positive");
            }
            demand = Long.MAX_VALUE - demand < n
                    ? Long.MAX_VALUE : demand + n;
        }

        @Override
        public CompletableFuture<WebSocket> sendText(
                CharSequence data, boolean last) {
            return CompletableFuture.completedFuture(this);
        }

        @Override
        public CompletableFuture<WebSocket> sendBinary(
                ByteBuffer data, boolean last) {
            return CompletableFuture.completedFuture(this);
        }

        @Override
        public CompletableFuture<WebSocket> sendPing(ByteBuffer data) {
            return CompletableFuture.completedFuture(this);
        }

        @Override
        public CompletableFuture<WebSocket> sendPong(ByteBuffer data) {
            return CompletableFuture.completedFuture(this);
        }

        @Override
        public CompletableFuture<WebSocket> sendClose(
                int statusCode, String reason) {
            return CompletableFuture.completedFuture(this);
        }

        @Override
        public String getSubprotocol() {
            return "";
        }

        @Override
        public boolean isInputClosed() {
            return inputClosed;
        }

        @Override
        public boolean isOutputClosed() {
            return false;
        }

        @Override
        public void abort() {
            inputClosed = true;
        }
    }
}
```

Biên dịch và chạy bằng **JDK 17+**, mã cũng tương thích **Java 11**:

```bash
javac WebSocketStageDemo.java
java WebSocketStageDemo
```

**Stdout chính xác:**

```text
demandAfterOpen=1
savedText=hello
demandAfterText=1
textStageDone=false
closeWhileTextPending=true
closeStageDone=false
textStageDoneAfter=true
closeStageDoneAfter=true
```

**Cách đọc output:**

- `demandAfterOpen=1`: onOpen cấp một lượt receive callback.
- `deliverText` trừ một demand rồi `onText` lại gọi `request(1)`, nên `demandAfterText=1` mặc dù `textStageDone=false`.
- `deliverClose` có thể được gọi khi future xử lý text còn pending; điều này minh họa hai cơ chế **demand** và **stage completion** độc lập.
- `listener.processing.complete(null)` làm stage text hoàn thành. `listener.cleanup.complete(null)` làm stage Close hoàn thành. Với socket thật, stage Close là tín hiệu liên quan thời điểm đóng output; trong fake, nó chỉ là trạng thái future để quan sát.
- Đây **không phải** bài test handshake, TLS, TCP, protocol hoặc tính năng automatic close của JDK; mục đích là kiểm tra logic callback/future không lệ thuộc mạng.

## 5. Khi cần xử lý bất đồng bộ thật trong `onText`

Một cách ứng dụng thường dùng là **copy dữ liệu** ngay khi callback nhận được, rồi đưa nghiệp vụ sang executor riêng:

```java
@Override
public CompletionStage<?> onText(
        WebSocket webSocket, CharSequence data, boolean last) {
    String copied = data.toString();
    webSocket.request(1);

    return CompletableFuture.runAsync(() -> {
        process(copied);
    }, workerExecutor);
}
```

Đây là **đoạn minh họa không độc lập**: `process(String)` là phương thức ứng dụng, `workerExecutor` là `Executor` do ứng dụng cấu hình. Mã trả về future hoàn thành sau khi `process` xong. Vì đã copy nội dung text trước khi return, tác vụ không cần đọc `CharSequence` ban đầu nữa.

Lưu ý then chốt: dù trả future từ `runAsync`, callback kế tiếp **vẫn có thể bắt đầu trước khi `process(copied)` hoàn thành** nếu đã gọi `request(1)` và callback trước đã trả về. Nếu các lần `process` cập nhật một state dùng chung, phải có cơ chế xử lý thứ tự hoặc đồng bộ.

Nếu **muốn chỉ yêu cầu callback tiếp theo sau khi processing xong**, có thể dời `request(1)` vào bước hoàn thành:

```java
@Override
public CompletionStage<?> onText(
        WebSocket socket, CharSequence data, boolean last) {
    String copied = data.toString();

    return CompletableFuture.runAsync(
            () -> process(copied), workerExecutor)
            .whenComplete((unused, error) -> {
                if (error == null) {
                    socket.request(1);
                }
                // Nếu lỗi: stage exceptional để WebSocket báo onError.
            });
}
```

Đoạn này không độc lập; khi ứng dụng có giao thức trao đổi liên tục, cần cân nhắc backlog, ping/pong, đóng kết nối và cách thoát khi lỗi. Nó tạo **backpressure chủ động bằng thời điểm gọi `request(1)`**, chứ không phải vì `CompletionStage` pending tự cấm callback mới. Nếu người dùng không gửi thêm demand, nhận dữ liệu/close callback có thể bị trì hoãn theo bộ đếm.

Với quá trình nhận phân mảnh, có thể vẫn muốn gọi `request(1)` ngay để lấy đủ message trước khi xử lý cả message. Sau đó mới áp dụng backpressure ở ranh giới message tùy thiết kế.

## 6. Khi một message có nhiều fragment: `last`, giữ dữ liệu và stage

`onText(..., last=false)` thông báo mới nhận **một phần** message; `last=true` kết thúc message text hiện tại. Tương tự với `onBinary(..., last)`.

Ví dụ **độc lập về logic nhưng cần đặt trong class listener có field**, có thể tích lũy text:

```java
private final StringBuilder fragments = new StringBuilder();

@Override
public CompletionStage<?> onText(
        WebSocket socket, CharSequence data, boolean last) {
    fragments.append(data);  // Copy ký tự ngay trong callback.
    socket.request(1);

    if (!last) {
        return null; // Không giữ tham chiếu đến data gốc.
    }

    String fullMessage = fragments.toString();
    fragments.setLength(0);
    handleCompleteMessage(fullMessage); // Hàm ứng dụng.
    return null; // Đã xử lý xong phần thuộc data gốc.
}
```

`fragments.append(data)` sao chép ký tự vào builder thuộc sở hữu ứng dụng. Do đó trả `null` cho fragment đã copy là an toàn về **vòng đời của `data`**. Đoạn này xử lý whole message đồng bộ; nếu xử lý nặng, cân nhắc executor và chính sách backlog rõ ràng.

Đừng lưu `List<CharSequence>` gồm **tham chiếu trực tiếp** tới các đối tượng `data` của JDK, rồi trả `null` cho từng fragment: API cho phép WebSocket thu hồi dữ liệu ngay và nội dung lưu lại có thể không còn an toàn. Muốn giữ fragment lâu dài, tạo `String` mới bằng `data.toString()` hoặc copy vào builder; nếu thực sự giữ dữ liệu JDK cấp, các returned stage phải còn pending cho đến khi không còn truy cập chúng.

**Không nhầm số callback với số message:** một text message có thể trải qua nhiều `onText`, và giữa các callback dữ liệu có thể có ping/pong. Dùng `last` để xác định ranh giới message, không giả định mọi `onText` đều là một message hoàn chỉnh.

## 7. `onBinary` và `ByteBuffer`: stage là tín hiệu về quyền sở hữu dữ liệu

Với binary/ping/pong, đối tượng được cấp là `ByteBuffer`. Vùng byte hợp lệ nằm từ `position()` tới `limit()`; không dùng `capacity()` làm số byte nhận thực tế.

Mẫu copy an toàn:

```java
@Override
public CompletionStage<?> onBinary(
        WebSocket socket, ByteBuffer data, boolean last) {
    ByteBuffer safeCopy = ByteBuffer.allocate(data.remaining());
    safeCopy.put(data.slice());
    safeCopy.flip();
    socket.request(1);
    return CompletableFuture.runAsync(() -> {
        consume(safeCopy); // Hàm ứng dụng: xử lý vùng remaining().
    }, workerExecutor);
}
```

Đây là **đoạn minh họa** trong class có `workerExecutor` và phương thức `consume(ByteBuffer)`, không phải chương trình Java độc lập. `data.slice()` một mình **chia sẻ vùng nhớ** với `data` gốc; ở đây, thao tác `put(data.slice())` thực hiện sao chép byte sang một buffer mới độc lập. `flip()` chuẩn bị để đọc. Việc đưa copy sang executor giúp tránh giữ lâu buffer do WebSocket cấp; nhưng vì callback đã gọi `request(1)`, quá trình xử lý có thể chạy song song với callback tiếp theo.

Nếu không copy và cần đọc chính buffer do JDK cấp trên một task khác, giữ stage **pending tới khi task không còn dùng buffer ấy**. Không đọc `data` sau khi stage completed. Khi dùng cả dữ liệu nhạy cảm hoặc buffer lớn, đặt giới hạn kích thước và tránh giữ tham chiếu không cần thiết.

## 8. `onClose` có stage nhưng ngữ nghĩa khác `onText`

`onClose(WebSocket socket, int statusCode, String reason)` được gọi khi **đã nhận Close message** và phía input của WebSocket đã đóng; đây là **receive callback cuối cùng** từ WebSocket đó. Nếu phía output vẫn mở, stage mà `onClose` trả về báo khi **có thể đóng phía output để đáp lại Close**.

Chi tiết quan trọng:

- Nếu `onClose` trả `null`, output có thể được đóng ngay theo hành vi mặc định.
- Nếu trả stage chưa complete, WebSocket có thể chờ stage hoàn thành **trước khi đóng output để phản hồi Close**, trừ khi ứng dụng chủ động gọi `sendClose(...)` hoặc `abort()` trước.
- Theo API, phía output sẽ được đóng sớm nhất giữa: stage hoàn thành, `sendClose(...)` được gọi, hoặc `abort()` được gọi.
- Một stage của `onClose` **không bao giờ complete** có thể khiến quá trình đóng output đáp trả không diễn ra, nếu không có hành động đóng khác. Đừng trả future vĩnh viễn pending để “chặn đóng” mà không có chính sách timeout/cleanup.
- Nếu ứng dụng phải ghi metadata, hoàn tất tác vụ cuối hoặc đóng tài nguyên trước khi đáp trả Close, nên trả stage gắn với **công việc hữu hạn**, có xử lý lỗi. Không đồng nhất stage này với future của `webSocket.sendClose(...)`: một cái là tín hiệu listener, một cái mô tả tác vụ gửi Close.

Ví dụ minh họa:

```java
@Override
public CompletionStage<?> onClose(
        WebSocket socket, int statusCode, String reason) {
    return CompletableFuture.runAsync(
            () -> cleanupForClose(statusCode, reason),
            cleanupExecutor);
}
```

Cần có `cleanupForClose` và `cleanupExecutor` trong class listener; đoạn code này không độc lập. Tránh để bước cleanup mắc vô hạn và chú ý xử lý exceptional completion theo hợp đồng `onError`. Nếu việc cleanup không cần giữ phía gửi mở, có thể hoàn thành ngay và quản lý cleanup theo cách khác, nhưng phải chắc chắn logic ứng dụng không phụ thuộc việc đóng kết nối.

`onError(WebSocket, Throwable)` là `void`, không có stage. Theo hợp đồng, đây là lần gọi cuối của WebSocket tương ứng và input/output đã đóng. Không ném exception từ `onError`; hành vi nếu ném là không được xác định. Ghi nhận lỗi và dọn tài nguyên trên con đường an toàn riêng.

## 9. Giữ thứ tự xử lý nghiệp vụ khi các stage chồng nhau

Java bảo đảm callback cho **cùng một WebSocket** được gọi tuần tự về mặt **bắt đầu/kết thúc thân hàm**. Nhưng nếu `onText` chỉ lên lịch tác vụ async rồi trả về, tác vụ của nhiều message khác nhau **có thể chạy song song hoặc hoàn tất không theo thứ tự**, tùy executor.

Nếu cần xử lý message theo đúng thứ tự, có thể nối một chuỗi `CompletableFuture`:

```java
private CompletableFuture<Void> tail =
        CompletableFuture.completedFuture(null);

@Override
public CompletionStage<?> onText(
        WebSocket socket, CharSequence data, boolean last) {
    fragments.append(data);
    socket.request(1);

    if (!last) {
        return null; // Fragment đã copy, không còn dùng data gốc.
    }

    String message = fragments.toString();
    fragments.setLength(0);

    tail = tail.thenRunAsync(() -> handleInOrder(message), appExecutor);
    return tail;
}
```

Đây là **đoạn minh họa trong một class listener** có `StringBuilder fragments`, `Executor appExecutor` và `handleInOrder(String)` tự định nghĩa. Nhờ chuỗi `tail`, tác vụ xử lý message sau chỉ bắt đầu khi tác vụ trước hoàn thành bình thường. Nếu task trước thất bại, chuỗi có thể hoàn thành exceptionally và không chạy những task sau; cần một chính sách lỗi rõ ràng thay vì âm thầm bỏ message.

Tuy nhiên, **demand ở đây vẫn gọi ngay**, nên listener tiếp tục có thể nhận callback mới trước khi tác vụ business logic xong. Nếu không muốn tạo hàng đợi vô hạn, kết hợp giới hạn backlog/bộ đếm hoặc chỉ `request(1)` khi hệ thống thực sự có khả năng nhận tiếp. Thời điểm hoàn tất stage trả về **không thay** chính sách flow control.

Đặc biệt với nhiều WebSocket dùng chung listener, state `tail` và `fragments` phải được tách theo từng connection. Nếu không, dữ liệu của các kết nối có thể bị trộn hoặc tạo race condition.

## 10. Sự khác nhau giữa future gửi và stage nhận

WebSocket còn có các phương thức gửi:

```java
CompletableFuture<WebSocket> sent =
        socket.sendText("hello", true);
```

Đây là **đoạn minh họa** với biến `socket` là WebSocket thật. Future của `sendText` hoàn thành khi thao tác **gửi** theo hợp đồng hoàn tất, không phải khi server đã **xử lý nghiệp vụ** hay khi listener của client đã nhận response.

So sánh:

| Future/stage | Tạo ra ở đâu? | Điều kiện hoàn tất chính |
| --- | --- | --- |
| `HttpClient.newWebSocketBuilder().buildAsync(uri, listener)` | Bắt đầu kết nối | Handshake/kết nối WebSocket được thiết lập hoặc lỗi |
| `socket.sendText(data, last)` | Gửi message ra ngoài | Thao tác gửi do WebSocket thực hiện hoàn thành hoặc lỗi |
| `listener.onText(...): CompletionStage<?>` | Callback nhận text | WebSocket có thể thu hồi dữ liệu đầu vào của lần callback |
| `listener.onClose(...): CompletionStage<?>` | Callback nhận Close | WebSocket có thể đóng phía output để đáp ứng Close |
| Future nghiệp vụ tự tạo | Ứng dụng xử lý dữ liệu | Do ứng dụng quyết định khi xử lý xong/thất bại |

Không dùng `sendText(...).join()` để suy luận rằng remote server đã commit dữ liệu. Nếu giao thức ứng dụng cần **acknowledgment**, phải định nghĩa message ACK riêng hoặc cơ chế xác nhận ở tầng nghiệp vụ.

## 11. Các lỗi phổ biến

| Hiểu lầm / sai sót | Hậu quả | Cách đúng |
| --- | --- | --- |
| Nghĩ future pending từ `onText` luôn chặn callback tiếp theo | Callback có thể đến trước khi xử lý cũ xong nếu demand dương | Quản lý `request(n)` và backlog độc lập với stage |
| Trả `null` nhưng worker async vẫn đọc `data`/`ByteBuffer` gốc | JDK có quyền thu hồi dữ liệu trước khi worker đọc | Copy dữ liệu hoặc chỉ complete stage sau khi dùng xong |
| Gọi `request(1)` rồi nghĩ nhận một message đầy đủ | Một message có thể bị chia nhiều callback | Dùng `last` để lắp ráp text/binary fragments |
| Bỏ quên `request(...)` trong listener tùy biến | Sau khi demand hết, không nhận thêm receive callbacks | Chủ động cấp demand theo khả năng xử lý |
| Coi `request(1)` là yêu cầu một byte | Demand đếm **lượt callback**, không đếm byte | Tách số callback khỏi số byte |
| Dùng `data.slice()` và nghĩ buffer độc lập | `slice()` chia sẻ vùng nhớ với buffer gốc | Copy byte vào buffer mới nếu cần giữ lâu |
| Dùng chung `StringBuilder` cho nhiều WebSocket | Callback khác kết nối có thể chồng nhau | State riêng từng socket hoặc đồng bộ |
| Đợi stage text hoàn tất để bảo đảm message nghiệp vụ đã xử lý theo thứ tự | Stage không tự serialize các tác vụ ứng dụng khác | Dùng queue/chain hoặc chỉ request tiếp sau khi xử lý |
| Trả `onClose` stage không bao giờ hoàn tất | Output close đáp trả có thể bị treo | Hoàn tất cleanup hoặc đóng rõ bằng `sendClose`/`abort` |
| Ném exception từ `onError` | Hành vi sau đó không xác định | Ghi lỗi, giải phóng tài nguyên, không throw |
| Nghĩ `sendText` future nghĩa remote server đã xử lý message | Chỉ là hoàn tất thao tác gửi | Nếu cần ACK, thiết kế protocol ứng dụng |

## 12. Câu hỏi tự kiểm tra

**Câu 1:** `onText(...)` trả một `CompletableFuture` chưa complete, nhưng đã gọi `webSocket.request(1)`. WebSocket có được gọi `onText` lần tiếp theo không?

**Đáp án:** Có thể, **sau khi thân hàm `onText` trước đã trả về** và nếu còn demand. CompletionStage pending không tự chặn callback mới.

**Câu 2:** Sự kiện nào cho phép JDK thu hồi `ByteBuffer` đã truyền vào `onBinary`?

**Đáp án:** Stage trả về từ `onBinary` hoàn tất bình thường hoặc trường hợp listener trả `null` tương đương stage đã hoàn thành. Sau thời điểm đó không được truy cập buffer JDK cấp.

**Câu 3:** `request(1)` có nghĩa nhận một WebSocket message hoàn chỉnh không?

**Đáp án:** Không. Nó cấp quyền cho **một receive callback**. Text/binary có thể gồm nhiều fragments; dùng `last`.

**Câu 4:** Nếu đã copy text bằng `String copied = data.toString()`, có cần giữ stage pending chỉ để bảo vệ `data` gốc không?

**Đáp án:** Không. Nếu ứng dụng không còn truy cập `data` gốc, có thể hoàn thành stage/return `null` ngay. Future nghiệp vụ có thể theo dõi riêng; nếu trả future nghiệp vụ, vẫn phải quản lý demand riêng.

**Câu 5:** `onClose` trả một future chưa hoàn thành để cleanup. WebSocket output chắc chắn đóng ngay không?

**Đáp án:** Không. Nếu output chưa đóng, nó có thể đợi stage hoàn thành; `sendClose` hoặc `abort` có thể làm output đóng sớm hơn.

**Câu 6:** `onError` có được trả một `CompletionStage` không?

**Đáp án:** Không. `onError` có kiểu trả về `void` và là callback kết thúc lỗi.

**Ghi nhớ:** Đối với `WebSocket.Listener` Java 11+, **callback return**, **`CompletionStage` completion** và **`request(n)` demand** là ba cơ chế khác nhau. Stage của `onText`/`onBinary`/`onPing`/`onPong` chủ yếu báo **thời điểm có thể thu hồi dữ liệu callback**; demand điều khiển **số callback có thể nhận**; stage của `onClose` điều khiển thời điểm **có thể đóng phía gửi**. Để xử lý bất đồng bộ đúng, copy dữ liệu khi cần, quản lý vòng đời buffer, flow control và thứ tự nghiệp vụ một cách tường minh.

**Tài liệu chính thức:** [Java SE 11 — WebSocket.Listener](https://docs.oracle.com/en/java/javase/11/docs/api/java.net.http/java/net/http/WebSocket.Listener.html); [Java SE 11 — WebSocket](https://docs.oracle.com/en/java/javase/11/docs/api/java.net.http/java/net/http/WebSocket.html); [Java SE 25 — WebSocket.Listener](https://docs.oracle.com/en/java/javase/25/docs/api/java.net.http/java/net/http/WebSocket.Listener.html); [Java SE 11 — CompletionStage](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/util/concurrent/CompletionStage.html).
