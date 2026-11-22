# WebSocket.request(n): điều tiết số lần gọi nhận, không phải số thông điệp hoàn chỉnh (Java 17)

## 1. Vấn đề: đã request(1), tại sao chưa nhận được cả một message?

Khi xây WebSocket client bằng `java.net.http.HttpClient` trong Java 17, người học thường gặp đoạn mã:

```java
@Override
public void onOpen(WebSocket webSocket) {
    webSocket.request(1);
}
```

Một suy luận hấp dẫn nhưng **sai** là: “`request(1)` yêu cầu WebSocket gửi cho listener **một thông điệp text hoặc binary hoàn chỉnh**.” Trong thực tế, API định nghĩa `request(n)` theo **số lần gọi các phương thức nhận của `WebSocket.Listener`**. Một thông điệp text/binary có thể đến trong **nhiều lần gọi `onText`/`onBinary`**, mỗi lần có cờ `last` cho biết phần đó có kết thúc thông điệp hay chưa.

Ví dụ một WebSocket peer gửi thông điệp logic `Hello`. Listener có thể nhận:

```text
onText("Hel", false)     # phần 1: chưa hết message
onText("lo",  true)      # phần 2: message kết thúc
```

Nếu ứng dụng mới chỉ cấp **1** lượt qua `request(1)`, callback đầu tiên đã tiêu thụ lượt đó. Callback thứ hai sẽ **chưa được gọi** cho đến khi có thêm demand. Nếu code chỉ gọi `request(1)` sau khi thấy `last == true`, nó có thể tự làm mình kẹt giữa một message: chưa nhận được phần cuối thì không request tiếp, mà không request tiếp thì không có phần cuối để nhận.

Thêm nữa, `onPing`, `onPong`, `onClose` cũng là **receive methods** theo hợp đồng Java 17. Một Ping/Pong/Close có thể tiêu thụ một lượt demand mà **không hề hoàn thành một message nghiệp vụ text/binary**. Vì vậy `request(5)` **không có nghĩa “cho phép năm message hoàn chỉnh”**, càng không phải lời hứa nhận đúng năm message.

**Trọng tâm bài học:** hiểu counter nhận nội bộ của `WebSocket`, phân biệt *callback invocation*, *mảnh dữ liệu*, *WebSocket message* và *business message*, cách dùng `last` để gom nội dung, tiếp tục `request(1)` đúng lúc, điều khiển backpressure, xử lý Ping/Pong/Close/Error, và tương tác giữa demand với `CompletionStage` do listener trả về.

Bài này áp dụng API Java SE 17 `java.net.http.WebSocket` và `WebSocket.Listener`.

## 2. Định nghĩa chính xác của `request(n)`

Theo Javadoc Java 17, một đối tượng `WebSocket` có **bộ đếm số lần gọi receive method còn được phép thực hiện**.

Quy trình:

1. WebSocket mới tạo bắt đầu với **counter bằng 0**.
2. Gọi `webSocket.request(n)` với **`n > 0`** làm counter **tăng thêm n**.
3. Mỗi khi WebSocket gọi **một phương thức nhận** trên listener, counter giảm **một**.
4. Khi counter bằng 0, WebSocket **không gọi các receive methods**, dù một số frame đã tới transport và vẫn còn việc cần giao cho application.
5. Ứng dụng có thể gọi `request` nhiều lần để bổ sung lượt; đây là **demand cộng dồn**, không phải quy ước “mỗi lần request tạo một message mới”.

### Những callback được tính vào demand

| `WebSocket.Listener` callback | Có tiêu thụ một lượt demand không? | Nhận nội dung gì? |
|---|---|---|
| `onText(ws, data, last)` | **Có** | Một phần hoặc toàn bộ **text message** |
| `onBinary(ws, buffer, last)` | **Có** | Một phần hoặc toàn bộ **binary message** |
| `onPing(ws, message)` | **Có** | Một Ping control message (tối đa 125 bytes payload) |
| `onPong(ws, message)` | **Có** | Một Pong control message (tối đa 125 bytes payload) |
| `onClose(ws, status, reason)` | **Có** | Close control message và tín hiệu input đã đóng |
| `onOpen(ws)` | **Không** | Thông báo kết nối WebSocket đã mở |
| `onError(ws, error)` | **Không** | Lỗi, có thể được gọi bất kể counter còn demand hay không |

**Nội dung quan trọng nhất:** bộ đếm điều khiển **invocation của năm receive methods**, không đếm payload bytes, WebSocket frames trực tiếp, số lần ứng dụng parse JSON, hoặc số business event đã commit.

### Phân biệt bốn loại “đơn vị”

| Đơn vị | Ví dụ | Quan hệ với `request(n)` |
|---|---|---|
| Byte TCP | Một đoạn bytes socket trả về | `request(n)` **không** tính theo số byte |
| WebSocket frame/fragment | Một phần dữ liệu được đóng gói trong protocol | Không được suy ra một frame luôn bằng một callback Java |
| Listener invocation | Một lần `onText`, `onBinary`, `onPing`, `onPong` hoặc `onClose` | **Đúng đơn vị** demand |
| WebSocket message | Một text/binary message kết thúc khi `last == true` | Có thể cần **nhiều** listener invocations |
| Business record | Một JSON object, transaction hay sự kiện nghiệp vụ | Một WebSocket message có thể chứa nhiều records, hoặc business protocol có quy tắc riêng |

Cơ chế chọn cách phân mảnh dữ liệu, gộp frame hoặc cung cấp callback phụ thuộc API/implementation và dữ liệu thực. Không tự dựng công thức `request(1) == 1 frame == 1 JSON`.

## 3. Mô hình counter: cộng demand, trừ từng callback

Hãy giả sử listener chủ động gọi:

```java
webSocket.request(3);
```

Một chuỗi callback **có thể** diễn ra như sau:

| Bước | Sự kiện | Demand trước | Demand sau | Message text hoàn chỉnh |
|---|---|---:|---:|---:|
| 0 | `request(3)` | 0 | 3 | 0 |
| 1 | `onText("Hel", false)` | 3 | 2 | 0 |
| 2 | `onText("lo", true)` | 2 | 1 | **1** |
| 3 | `onPing(emptyBuffer)` | 1 | 0 | Vẫn **1** |
| 4 | Đã nhận thêm bytes, chưa gọi `request` | 0 | 0 | Chưa có callback tiếp |
| 5 | `request(1)` | 0 | 1 | Chưa tự tạo message |
| 6 | `onText("Bye", true)` | 1 | 0 | **2** |

Ở bước 3, Ping đã tiêu thụ một lượt dù số message text hoàn chỉnh không tăng. Ở bước 4, chương trình không được suy ra peer ngừng gửi; chỉ biết **chưa còn credit để gọi receive method khác**.

### `request(0)` hoặc `request(-1)`

`request(n)` yêu cầu `n > 0`. Theo Java 17, nếu `n <= 0`, phương thức ném `IllegalArgumentException`.

**Sai:**

```java
// Chỉ để minh họa lỗi API; không chạy độc lập.
webSocket.request(0);   // IllegalArgumentException
webSocket.request(-1);  // IllegalArgumentException
```

Không dùng `request(0)` như lệnh pause, không dùng `request(-1)` để trả credit về counter. **Muốn pause** thì tạm **không cấp thêm demand**, đồng thời quản lý những lượt còn tồn tại. Một khi đã gọi `request(1000)`, bạn không có API `unrequest(999)` để rút demand lại ngay; thiết kế cửa sổ nhận nên có chủ đích từ đầu.

### `request(n)` không phải phương thức đợi

`request(n)` không giống `Future.get(n, unit)`, không chờ đủ n callback rồi trả về. Đây là thao tác **khai báo thêm khả năng nhận**. Lỗi network hoặc timeout không được chuyển thành chính sách hoàn tất message chỉ bằng việc gọi request lại.

## 4. Text/Binary fragmentation và cờ `last`

Java 17 nhận text bằng:

```java
CompletionStage<?> onText(
        WebSocket webSocket, CharSequence data, boolean last);
```

và binary bằng:

```java
CompletionStage<?> onBinary(
        WebSocket webSocket, ByteBuffer data, boolean last);
```

Đối số `last` là **chỉ dấu mảnh hiện tại kết thúc WebSocket message hay chưa**:

- `last == false`: còn dữ liệu của **cùng message** sẽ đến trong những lần nhận phù hợp tiếp theo.
- `last == true`: phần hiện tại kết thúc message; application có thể hoàn tất việc ghép/parse message đó.
- Một message nhỏ **có thể** được báo với một callback có `last == true`; nhưng không phải contract cho mọi message.

**Không đoán điểm kết thúc bằng số lượt request hoặc kích thước buffer.** Cũng không lấy việc `CharSequence.length() < X` hay `ByteBuffer.remaining()==0` làm dấu hiệu kết thúc message. `last` mới là tín hiệu kết thúc trong API listener.

### Mẫu text message hai mảnh

```text
Ứng dụng: request(1)
WebSocket: onText("Cà ", false)    -> tiêu thụ 1 credit
Ứng dụng: thêm "Cà " vào StringBuilder
Ứng dụng: request(1)
WebSocket: onText("phê", true)     -> tiêu thụ 1 credit
Ứng dụng: ghép thành "Cà phê", mới xử lý message
```

Bản thân `request(1)` **không cho phép bạn ép runtime chia message thành đúng một callback**; đây chỉ là ví dụ về một chuỗi nhận hợp lệ.

### Binary được đọc trong khoảng position–limit

`onBinary` nhận một `ByteBuffer`: dữ liệu ở vùng từ `buffer.position()` đến `buffer.limit()`. Không đọc toàn bộ `buffer.array()` vì:

- Buffer có thể là direct hoặc read-only, không có mảng truy cập được.
- Vị trí/giới hạn xác định phần data hợp lệ, array có thể chứa byte khác ngoài slice.
- Buffer được runtime quản lý về lifetime, có thể không tồn tại hợp lệ sau khi completion stage kết thúc.

Khi cần giữ dữ liệu lâu hơn, **copy** phần bytes đang còn vào buffer/array do ứng dụng sở hữu. Đừng giữ tham chiếu tới ByteBuffer do callback cung cấp rồi dùng về sau khi đã báo stage hoàn tất.

## 5. `onOpen`, các default methods và nguy cơ cạn demand

`WebSocket.Listener` là interface có các method **default**. Một số hành vi mặc định trên Java 17 giúp listener đơn giản vẫn tiếp tục nhận:

- Default `onOpen` tương đương `webSocket.request(1)`.
- Default `onText`, `onBinary`, `onPing`, `onPong` đều gọi `webSocket.request(1)` rồi trả `null`.
- Default `onClose` trả `null`, cho phép đóng phía output phù hợp contract; nó **không request tiếp**.
- Default `onError` không phải receive method và không làm tăng demand.

### Khi override `onOpen`

Nếu bạn override `onOpen` **mà không** gọi `request(...)`, thì counter vẫn bắt đầu 0, ứng dụng có thể không nhận các callback text/binary/control khác. Ví dụ:

```java
// Minh họa lỗi: onOpen đã override nhưng không cấp demand.
@Override
public void onOpen(WebSocket socket) {
    logConnected();
    // Thiếu socket.request(1).
}
```

Nếu muốn tận dụng default, có thể không override `onOpen` hoặc khi override thì gọi `WebSocket.Listener.super.onOpen(socket)`, nhưng thường rõ ràng hơn là gọi trực tiếp `socket.request(1)` sau khi thiết lập state.

### Khi override `onText`

Một lỗi rất hay gặp:

```java
// Minh họa lỗi: nhận xong một callback rồi không cấp thêm demand.
@Override
public CompletionStage<?> onText(
        WebSocket socket, CharSequence part, boolean last) {
    accumulator.append(part);
    if (last) {
        handleComplete(accumulator.toString());
    }
    return null; // Không tự request tiếp!
}
```

Hàm này **đã thay** default implementation vốn tự request tiếp. Nếu trước đó chỉ còn một credit, connection sẽ không gọi `onText` kế tiếp. Khắc phục: theo policy đã chọn, gọi `request(1)` sau khi sẵn sàng nhận callback tiếp theo, kể cả khi `last == false`.

### Ping/Pong có thể “ăn” credit

Giả sử bạn override `onText`, nhưng không override `onPing`/`onPong`. Các default onPing/onPong **tự cấp thêm 1 credit**; đó là hành vi cụ thể của default listener. Nếu bạn override cả Ping/Pong chỉ để log và quên `request(1)`, một Ping có thể tiêu hết credit cuối, làm ngừng data delivery.

**Tách protocol Ping/Pong khỏi business count:** Ping/Pong là WebSocket control messages, không phải text/binary messages của ứng dụng. Java WebSocket client tự gửi Pong tương ứng khi nhận Ping theo hợp đồng; đa số listener không cần tự gọi `sendPong` chỉ để đáp ứng Ping.

## 6. Một listener nhận text có kiểm soát

Đây là **đoạn mã minh họa**, không phải chương trình Java độc lập. Nó cho thấy vòng nhận đúng theo một credit, ghép các fragment rồi xử lý message:

```java
WebSocket.Listener listener = new WebSocket.Listener() {
    private final StringBuilder partial = new StringBuilder();

    @Override
    public void onOpen(WebSocket socket) {
        socket.request(1);
    }

    @Override
    public CompletionStage<?> onText(
            WebSocket socket, CharSequence data, boolean last) {
        partial.append(data);

        if (last) {
            String message = partial.toString();
            partial.setLength(0);
            processCompleteMessage(message); // do ứng dụng định nghĩa
        }

        socket.request(1); // Một lượt gọi nhận TIẾP THEO.
        return null;
    }
};
```

**Ý nghĩa:**

1. `onOpen` cấp demand ban đầu.
2. `onText` gom từng phần vào `partial`, **không xử lý message trước `last==true`**.
3. Sau mỗi callback, ứng dụng cấp thêm một lượt. Vì vậy message có thể được ghép qua nhiều callback, không bị nghẽn ở fragment đầu.
4. `return null` được API diễn giải như một completion stage đã hoàn tất bình thường, nghĩa là runtime có thể thu hồi `CharSequence` đã cấp. Đoạn code không giữ tham chiếu gốc tới `data`, mà append/copy dữ liệu vào buffer do ứng dụng sở hữu.
5. Đây là chiến lược **không giới hạn queue/bộ nhớ**; khi xử lý lớn hoặc bất đồng bộ, cần buffer limit/backpressure theo phần sau.

**Đừng thêm cả `request(1)` ở `onOpen` lẫn gọi default `super.onOpen` nếu cả hai cùng cấp demand ngoài ý muốn.** Một credit hay nhiều credits là quyết định chính sách, không phải “số request HTTP” hoặc “số message”.

## 7. `onPing`, `onPong`, `onClose`, `onError` và credit

### 7.1. `onPing` và `onPong` là receive methods

Hai callback này nhận `ByteBuffer` với payload không quá **125 bytes** theo WebSocket protocol. Mỗi lời gọi, giống `onText`, tiêu thụ **một** demand.

```java
// Đoạn minh họa: override Ping nhưng vẫn duy trì nhu cầu nhận.
@Override
public CompletionStage<?> onPing(
        WebSocket socket, ByteBuffer payload) {
    recordPing();   // do ứng dụng định nghĩa
    socket.request(1);
    return null;
}
```

Nếu override Ping mà quên rearm, và peer gửi Ping khi chỉ còn một credit, event tiếp theo có thể bị giữ lại. `onPong` tương tự. Java implementation tự động gửi Pong tương ứng khi nhận Ping, nên không cần tự phát Pong thứ hai để bảo đảm phép handshake Ping/Pong thông thường.

### 7.2. `onClose` là receive method cuối cùng

`onClose(socket, statusCode, reason)` tiêu thụ credit giống các callback nhận khác. Khi gọi nó, phía **input** của WebSocket đã đóng theo hợp đồng, và đây là callback **cuối cùng** của socket đó. Không có lý do request thêm data từ chính connection đã đóng.

Nếu phía output chưa đóng, completion stage của `onClose` còn tham gia quyết định lúc nào output có thể đóng tương ứng; không phải chỉ một method để log mã trạng thái. Default `onClose` trả `null`, cho phép output closure theo contract.

### 7.3. `onError` không cần demand

`onError(socket, error)` không thuộc nhóm receive methods bị `request(n)` điều tiết. Nó có thể được gọi khi demand bằng 0. Java 17 mô tả đây là callback cuối cùng khi lỗi xảy ra (sau khi onOpen); khi callback bắt đầu, input và output đã đóng. Code nên cleanup/ghi log có kiểm soát, không gọi request để “chữa lỗi”.

Một exception ném ra từ listener callback hoặc một `CompletionStage` của receive callback hoàn thành thất bại có thể khiến WebSocket gọi `onError`. Vì vậy đừng để parser/handler ném exception ngoài ý muốn mà không có chính sách xử lý.

### 7.4. `sendClose` khác `request`

- `webSocket.sendClose(...)` là **thao tác gửi** Close, liên quan tới phía output.
- `webSocket.request(n)` là **credit nhận** callback từ phía input.
- `webSocket.abort()` đóng input/output đột ngột, không phải backpressure.
- `isInputClosed()` và `isOutputClosed()` giúp quan sát trạng thái, không dùng thay counter điều tiết.

Nếu client đã gửi Close nhưng input chưa đóng, phía nhận vẫn có thể cần xử lý Close callback tương ứng theo lifecycle. Không dùng `request(1)` làm lệnh đóng hoặc `sendClose` làm “cấp thêm credit”.

## 8. `CompletionStage` và `request(n)` là hai cơ chế khác nhau

Listener `onText`, `onBinary`, `onPing`, `onPong` trả `CompletionStage<?>` (hoặc `null`), nhưng **CompletionStage không phải counter demand**.

- **`request(n)`:** cho phép WebSocket **gọi thêm n receive methods** trên listener.
- **Stage hoàn tất:** báo với WebSocket rằng callback đã sử dụng xong đối tượng dữ liệu mà implementation truyền vào (`CharSequence`/`ByteBuffer`), để implementation có thể **thu hồi tài nguyên/đóng vòng nhận** theo contract.
- Stage hoàn thành không tự gọi `request(1)`.
- Gọi `request(1)` không tự hoàn thành stage.
- Theo Javadoc Java 17, WebSocket **không bắt buộc đợi CompletionStage của callback trước hoàn tất** mới được gọi callback tiếp theo khi có demand. Vì vậy callback logic phải quản lý state và dữ liệu đúng.

### Một race tưởng nhỏ

```text
onText(data1, last=false)
  -> ứng dụng giữ tham chiếu data1
  -> request(1)
  -> return completedFuture(null)
WebSocket có quyền thu hồi data1
  -> asynchronous worker vẫn đọc data1
  -> SAI: lifetime dữ liệu không còn được bảo đảm
```

Cách đúng là **copy nội dung cần xử lý** sang buffer/string do ứng dụng sở hữu trước khi trả stage đã hoàn tất, hoặc giữ stage chưa hoàn tất tới khi thật sự không còn cần dữ liệu callback. Đồng thời điều khiển demand phù hợp capacity của worker/queue.

### Sequential callback không đồng nghĩa mọi tác vụ async có thứ tự

Java 17 `WebSocket.Listener` bảo đảm các lời gọi callback của **cùng một WebSocket** được thực hiện **không reentrant**: lời gọi tiếp theo không bắt đầu trước khi lời gọi trước **trả về**. Nhưng callback có thể tạo tác vụ async chạy tiếp **sau** khi phương thức callback trả. Các task đó có thể chạy đồng thời hoặc hoàn thành không đúng thứ tự message nếu bạn không tự tuần tự hóa.

Do đó:

- Tách `onText` append/copy ở trong callback khỏi business task async.
- Nếu message cần xử lý theo thứ tự, dùng per-connection queue/serial executor.
- Đảm bảo một listener dùng cho **nhiều WebSocket** không dùng chung một `StringBuilder`/ByteBuffer mutable mà không đồng bộ hoặc phân vùng state theo socket.
- Không gửi thêm demand vượt khả năng xử lý thực tế chỉ vì callback method đã trả về.

## 9. Đoạn tình huống: request(1) nhưng vẫn chưa có message nào hoàn chỉnh

Giả sử peer gửi **một message duy nhất** dài 50 KiB. Implementation có thể chia callback:

```text
request(1)             credit = 1
onBinary(chunk A,false) credit = 0, complete messages = 0

request(1)             credit = 1
onBinary(chunk B,false) credit = 0, complete messages = 0

request(1)             credit = 1
onBinary(chunk C,true)  credit = 0, complete messages = 1
```

Đã có **3 lần onBinary**, nhưng chỉ **1 message**. Nếu callback B bị kẹt do thiếu demand, một buffer của message đang dở dang có thể ở trạng thái chờ lâu; cần quản lý timeout và cleanup.

Ngược lại, một message nhỏ có thể được đưa vào **một lần** `onText("OK", true)`. Do đó bạn không thể tính:

```text
số complete messages = tổng request(n) đã gọi
```

Đúng hơn, **đếm message khi thấy `last == true`**, và đếm callback riêng nếu muốn quan sát demand. Với business protocol chứa nhiều bản ghi trong một message, còn phải parse theo schema để xác định số business events.

### ByteBuffer và backpressure

Nếu mỗi callback binary có 1 KiB hoặc 64 KiB, `request(1)` vẫn là **một callback**. Nó không bảo đảm cấp đúng n byte hoặc khống chế trực tiếp từng lần đọc TCP. JVM có thể có buffer hoặc protocol frames đã nhận trước khi listener được gọi. Vì vậy demand là **application receive backpressure trên callback delivery**, không phải biện pháp thay thế cho bounded queues, max message size, flow control ở tầng vận chuyển hoặc timeout.

## 10. Chương trình Java 17 chạy được: mô phỏng counter của WebSocket

Để minh họa **chính xác sự khác nhau giữa callback và complete message** mà không phụ thuộc server WebSocket thật, demo dưới đây tạo một **test harness `DemoSocket implements WebSocket`**. Class này chỉ mô phỏng **demand counter và lời gọi listener**, không tạo handshake, không gửi WebSocket frames/TCP, không triển khai client network đầy đủ.

Chương trình dùng **interface thật của Java 17** (`WebSocket`, `WebSocket.Listener`), nên biên dịch/runnable mà không cần thư viện ngoài.

Kịch bản:

1. `onOpen` gọi `request(2)`.
2. Harness gọi `onText("Hel", false)`, rồi `onText("lo", true)` → **2 credit bị tiêu thụ**, nhưng chỉ hoàn thành **1 message Hello**.
3. Credit về 0; harness thử giao Ping nhưng **không gọi listener** khi thiếu credit, trả `false` để dễ thấy vấn đề.
4. Gọi `request(1)` cho Ping, rồi `request(1)` cho text `Bye`, cuối cùng `request(1)` cho Close.
5. Tổng cộng có **5 receive method invocations**, nhưng **chỉ 2 complete text messages**.

Tạo file **`WebSocketDemandDemo.java`**:

```java
import java.net.http.WebSocket;
import java.nio.ByteBuffer;
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionStage;

public class WebSocketDemandDemo {
    static final class DemoSocket implements WebSocket {
        private long demand;
        private WebSocket.Listener listener;
        private boolean inputClosed;
        private boolean outputClosed;

        void open(WebSocket.Listener newListener) {
            listener = newListener;
            listener.onOpen(this);
        }

        long remaining() {
            return demand;
        }

        private boolean consumeOne() {
            if (demand == 0) {
                return false;
            }
            demand--;
            return true;
        }

        boolean deliverText(String part, boolean last) {
            if (!consumeOne()) {
                return false;
            }
            CompletionStage<?> stage =
                    listener.onText(this, part, last);
            if (stage != null) {
                stage.toCompletableFuture().join();
            }
            return true;
        }

        boolean deliverPing() {
            if (!consumeOne()) {
                return false;
            }
            CompletionStage<?> stage =
                    listener.onPing(this, ByteBuffer.allocate(0));
            if (stage != null) {
                stage.toCompletableFuture().join();
            }
            return true;
        }

        boolean deliverClose(int status, String reason) {
            if (!consumeOne()) {
                return false;
            }
            inputClosed = true;
            CompletionStage<?> stage =
                    listener.onClose(this, status, reason);
            if (stage != null) {
                stage.toCompletableFuture().join();
            }
            outputClosed = true;
            return true;
        }

        @Override
        public void request(long n) {
            if (n <= 0) {
                throw new IllegalArgumentException(
                        "n must be positive");
            }
            demand = n > Long.MAX_VALUE - demand
                    ? Long.MAX_VALUE : demand + n;
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
            return outputClosed;
        }

        @Override
        public void abort() {
            inputClosed = true;
            outputClosed = true;
        }

        @Override
        public CompletableFuture<WebSocket> sendText(
                CharSequence data, boolean last) {
            throw new UnsupportedOperationException(
                    "No network in demo");
        }

        @Override
        public CompletableFuture<WebSocket> sendBinary(
                ByteBuffer data, boolean last) {
            throw new UnsupportedOperationException(
                    "No network in demo");
        }

        @Override
        public CompletableFuture<WebSocket> sendPing(
                ByteBuffer message) {
            throw new UnsupportedOperationException(
                    "No network in demo");
        }

        @Override
        public CompletableFuture<WebSocket> sendPong(
                ByteBuffer message) {
            throw new UnsupportedOperationException(
                    "No network in demo");
        }

        @Override
        public CompletableFuture<WebSocket> sendClose(
                int statusCode, String reason) {
            throw new UnsupportedOperationException(
                    "No network in demo");
        }
    }

    static final class CountingListener
            implements WebSocket.Listener {
        private final StringBuilder partial = new StringBuilder();
        private final List<String> messages = new ArrayList<>();

        @Override
        public void onOpen(WebSocket socket) {
            socket.request(2);
            System.out.println("onOpen: request(2)");
        }

        @Override
        public CompletionStage<?> onText(
                WebSocket socket, CharSequence data, boolean last) {
            partial.append(data);
            System.out.println(
                    "onText: " + data + " last=" + last);
            if (last) {
                String complete = partial.toString();
                messages.add(complete);
                partial.setLength(0);
                System.out.println("complete message: " + complete);
            }
            return CompletableFuture.completedFuture(null);
        }

        @Override
        public CompletionStage<?> onPing(
                WebSocket socket, ByteBuffer message) {
            System.out.println("onPing: received");
            return CompletableFuture.completedFuture(null);
        }

        @Override
        public CompletionStage<?> onClose(
                WebSocket socket, int status, String reason) {
            System.out.println("onClose: " + status);
            return CompletableFuture.completedFuture(null);
        }

        int completeMessageCount() {
            return messages.size();
        }
    }

    public static void main(String[] args) {
        DemoSocket socket = new DemoSocket();
        CountingListener listener = new CountingListener();
        socket.open(listener);

        socket.deliverText("Hel", false);
        socket.deliverText("lo", true);
        System.out.println("remaining demand: "
                + socket.remaining());

        boolean pingDelivered = socket.deliverPing();
        System.out.println("ping delivered with zero demand: "
                + pingDelivered);

        socket.request(1);
        socket.deliverPing();
        socket.request(1);
        socket.deliverText("Bye", true);
        socket.request(1);
        socket.deliverClose(1000, "done");

        System.out.println("complete messages: "
                + listener.completeMessageCount());
    }
}
```

Biên dịch và chạy trên **JDK 17+**, không cần mạng:

```bash
javac -encoding UTF-8 --release 17 WebSocketDemandDemo.java
java WebSocketDemandDemo
```

**Stdout chính xác của chương trình:**

```text
onOpen: request(2)
onText: Hel last=false
onText: lo last=true
complete message: Hello
remaining demand: 0
ping delivered with zero demand: false
onPing: received
onText: Bye last=true
complete message: Bye
onClose: 1000
complete messages: 2
```

### Giải thích kỹ kết quả

- `request(2)` tạo **hai lượt nhận** ban đầu; nó **không** tạo một hay hai messages.
- Hai fragment `"Hel"` và `"lo"` mỗi fragment tiêu thụ một lượt; khi `last==true` ở fragment thứ hai, listener **mới** thêm một message hoàn chỉnh `Hello`.
- `remaining demand: 0` sau hai callback là chính xác trong mô phỏng này.
- `ping delivered with zero demand: false` nghĩa là harness **không gọi `onPing`** khi counter 0. Trong network implementation thực, frame có thể đã được đọc/đệm nội bộ, nhưng callback không được gọi khi thiếu demand.
- Sau `socket.request(1)`, Ping được giao, **không tăng** complete text-message count.
- `Bye` là message ngắn đến trong một callback `last=true` và tiêu thụ một credit.
- `onClose` cũng tiêu thụ credit; nó kết thúc reception theo mô hình lifecycle.
- Tổng 2 + 1 + 1 + 1 = **5 callbacks nhận**, nhưng message text hoàn chỉnh chỉ **2**.

### Vì sao phải ghi rõ đây là mô phỏng?

`DemoSocket` **không** mô phỏng toàn bộ semantics của JDK WebSocket implementation như network reads, TLS, close handshake, auto Pong, Async callback scheduling, thread safety, frame buffering hay việc đưa event vào queue. Nó chỉ là một **harness deterministic** để quan sát counter. Một WebSocket server thật có thể chia text message thành nhiều callbacks **khác ví dụ**, và thời điểm gọi `onPing`/`onClose` còn phụ thuộc peer và runtime.

Trong code production, **không implement WebSocket thủ công như DemoSocket**. Dùng `HttpClient.newWebSocketBuilder().buildAsync(uri, listener)` để xây WebSocket client thực, còn `DemoSocket` chỉ phù hợp làm bài test khái niệm.

## 11. Kết nối thật qua HttpClient: phần code cần đặt ở đâu?

Một WebSocket client Java 17 thường có cấu trúc:

```java
// Đoạn minh họa, listener là một WebSocket.Listener hợp lệ;
// URI phải trỏ tới endpoint WebSocket thật (wss://...).
CompletableFuture<WebSocket> connected =
        HttpClient.newHttpClient()
                .newWebSocketBuilder()
                .buildAsync(
                        URI.create("wss://example.com/socket"),
                        listener);

// Khi không dùng nữa: gửi close theo protocol và quản lý timeout;
// nếu cần đóng cưỡng bức input/output thì dùng abort().
```

`HttpClient.newWebSocketBuilder()` khởi tạo client-side handshake; `buildAsync` trả future của WebSocket khi thiết lập kết nối hoàn tất. **Đây là đoạn minh họa**, không runnable độc lập vì `listener` chưa được khai báo và endpoint là ví dụ.

Khi đã connected, `onOpen` của listener được gọi. Nếu dùng default `onOpen` sẽ có 1 demand; nếu tự override, phải quyết định lượng demand. Trong `onText`/`onBinary`, **sử dụng `last` để ghép message**, không suy từ `request(n)` ra số message.

### Một listener hữu ích cho text fragments (minh họa)

```java
// Minh họa logic callback, không phải class độc lập.
final class TextListener implements WebSocket.Listener {
    private final StringBuilder partial = new StringBuilder();
    private final int maxChars = 1_000_000;

    @Override
    public void onOpen(WebSocket socket) {
        socket.request(1);
    }

    @Override
    public CompletionStage<?> onText(
            WebSocket socket, CharSequence chunk, boolean last) {
        if (chunk.length() > maxChars - partial.length()) {
            socket.abort(); // policy: message vượt giới hạn
            return null;
        }

        partial.append(chunk);

        if (last) {
            String complete = partial.toString();
            partial.setLength(0);

            // Giả sử handleMessage là hàm được cài trong ứng dụng,
            // đồng bộ, nhanh và không ném lỗi không kiểm soát.
            handleMessage(complete);
        }

        socket.request(1);
        return null;
    }
}
```

Ở đây cần import `java.net.http.WebSocket` và `java.util.concurrent.CompletionStage`; `handleMessage` do ứng dụng định nghĩa. **Giới hạn `maxChars` chỉ là giới hạn số UTF-16 code units được tích lũy**, không thay cho giới hạn bytes/protocol frames. Nếu handler xử lý lâu, cần một bounded queue và chính sách backpressure chứ không tiếp tục phát request vô hạn.

**Lưu ý lỗi:** nếu `handleMessage` ném exception, WebSocket có thể đi qua `onError`. Một ứng dụng thực nên bắt/log/phân loại lỗi parser và quyết định đóng an toàn. `abort` là đóng cưỡng bức, không phải graceful Close handshake; khi protocol cho phép và connection còn khỏe có thể chọn gửi `sendClose` với status/reason phù hợp.

## 12. Backpressure có thực sự kiểm soát tải không?

`request(n)` giúp điều tiết **số callback nhận được đưa tới application**, nhưng nó **không tự động**:

- Giới hạn tổng bytes của một message.
- Bảo đảm server ngừng gửi byte ngay lập tức.
- Chặn peer độc hại gửi frame lớn hoặc nhiều frame.
- Hạn chế số business jobs mà bạn đã đưa vào thread pool.
- Xử lý memory leak của `StringBuilder`/`ByteBuffer` do bạn tạo.
- Bảo đảm callback là một JSON message hợp lệ hoặc toàn bộ một business event.
- Đặt deadline/timeout cho process message.
- Thay thế queue bounded và error handling.

Nếu muốn thực sự vận hành an toàn, cần thiết kế **bounded receive pipeline**: cấp demand vừa đủ để listener có thể **copy/parse** fragment, ghép message có giới hạn, xử lý hoặc chuyển giao cho downstream có capacity.

### Chiến lược A — mỗi callback cấp tiếp một credit

```java
public CompletionStage<?> onText(
        WebSocket ws, CharSequence part, boolean last) {
    accumulator.append(part);
    if (last) {
        processQuickly(accumulator.toString());
        accumulator.setLength(0);
    }
    ws.request(1);
    return null;
}
```

Đây là **mẫu minh họa**, không phải class đầy đủ. Ưu điểm: đơn giản, không kẹt khi message chia nhiều phần. Nhược: nếu `processQuickly` thực sự tốn thời gian hoặc queue downstream không giới hạn, có thể làm callback thread chậm hoặc bộ nhớ tăng.

### Chiến lược B — chỉ cấp credit khi downstream có capacity

```text
onText(fragment, last=false)
  -> copy/append trong giới hạn
  -> request(1) để lấy phần tiếp, nếu còn capacity

onText(fragment, last=true)
  -> tạo completeMessage
  -> enqueue vào bounded worker queue
  -> chỉ request tiếp khi queue còn chỗ
```

Cần tính đến Ping/Pong và việc fragmentation có thể tạo nhiều callback cho một message, không cho phép queue business quyết định demand dựa thuần trên “mỗi message = một credit”.

### Chiến lược C — giới hạn window nhiều credit

Một bộ nhận xử lý nhanh có thể request `n > 1` để giữ một cửa sổ callback sẵn sàng. Nhưng bạn phải nhớ **n là callbacks**, không messages; một message lớn dùng hết nhiều credits, Ping cũng dùng credits. Với nhiều outstanding demand, application phải có đủ bộ nhớ/capacity và không kỳ vọng `request(100)` tạo giới hạn chính xác 100 business jobs.

**Không cố gọi `request(0)` để pause** vì Java ném `IllegalArgumentException`. Chỉ ngừng cấp credit mới và chờ các credit đã phát được tiêu thụ. Nếu need strict stop, dùng state/cancellation/close theo policy; counter không có API giảm trực tiếp.

## 13. CompletionStage và pipeline xử lý bất đồng bộ

Một listener có thể xử lý business message bằng executor hoặc một dịch vụ async. Có hai dạng quản lý khác nhau:

### 13.1. Copy data rồi trả stage đã hoàn tất

```java
// Đoạn minh họa: data phải được copy trước khi callback kết thúc.
String owned = data.toString();
queue.submit(owned);  // queue bounded do ứng dụng quản lý
ws.request(1);
return null;
```

Điều này **an toàn về lifetime của data** nếu `toString()` tạo snapshot cần thiết, nhưng **không đủ về backpressure**: `queue.submit` phải có chính sách từ chối/giới hạn, và `ws.request(1)` không được cấp tiếp khi queue đã quá tải.

### 13.2. Trả CompletionStage chưa hoàn tất

```java
// Đoạn minh họa: processAsync trả CompletionStage<?>.
// Không giữ data gốc sau khi stage đã complete.
CompletionStage<?> processed = processAsync(data);
return processed;
```

Stage báo thời điểm dữ liệu callback có thể được thu hồi. **Không phải** bằng chứng rằng receive demand đã tự được cấp lại. Nếu không gọi `request(1)` ở một nơi khác, reception có thể dừng khi counter về 0.

Đồng thời, Java 17 ghi rõ stage đang pending **không nhất thiết chặn các listener invocations tiếp theo** khi demand vẫn còn. Nếu `processAsync` thao tác cùng `StringBuilder`/`ByteBuffer` hoặc database state, cần bảo vệ đồng thời và thứ tự.

### 13.3. Xử lý complete message sau `last=true`

Một pattern hợp lý:

```text
Nhận từng callback:
  - kiểm tra connection / frame type
  - copy + tích lũy data theo quota
  - nếu last=false: cấp credit tiếp theo khi có capacity
  - nếu last=true:
      tạo immutable complete message
      đưa vào bounded queue
      cấp credit tiếp khi queue downstream còn chỗ
      tránh để callback thread làm CPU/blocking lâu
```

Nếu xử lý một logical message phải chia thành nhiều đợt, deadline/size limit nên tính **từ fragment đầu**, không reset một timeout dài như mới mỗi fragment và mở cơ hội slow-drip vô hạn.

## 14. Những lỗi phổ biến liên quan trực tiếp đến request(n)

| Lỗi | Biểu hiện | Cách đúng |
|---|---|---|
| Nghĩ `request(1)` = một complete message | Đọc một fragment rồi parse JSON lỗi | Gom `onText/onBinary` theo `last` |
| Chỉ gọi `request(1)` khi `last==true` | Kẹt ở fragment `last=false` | Tiếp tục cấp credit cho fragment tiếp khi còn capacity |
| Override `onOpen` nhưng không request | Không nhận callback dữ liệu | Gọi `request(1)` hoặc chính sách demand rõ ràng |
| Override `onText` và chỉ return `null` | Counter có thể về 0 mãi | Request thêm khi sẵn sàng |
| Override `onPing`/`onPong` quên request | Ping/Pong tiêu thụ credit cuối | Cấp lại demand phù hợp hoặc tận dụng default |
| Nghĩ `onError` cũng cần request | Cleanup lỗi không chạy khi counter 0 | `onError` không phải receive method |
| Nghĩ `onClose` không tiêu credit | Chậm nhận Close callback | `onClose` thuộc receive methods |
| Dùng `request(0)` để pause | `IllegalArgumentException` | Tạm không cấp thêm credit |
| Dùng `request(-1)` để giảm demand | `IllegalArgumentException` | Định nghĩa window/capacity đúng |
| Nhận nhiều fragments mà không limit | StringBuilder/byte array tăng vô hạn | Max complete-message size + timeout |
| Coi `CompletionStage` hoàn tất là tự request tiếp | Reception bị dừng | Hai cơ chế độc lập |
| Coi `request(1)` là cho phép callback chỉ khi stage trước complete | Async tasks bất ngờ overlap | Không reentrant callback, nhưng task async có thể overlap |
| Trả completed stage rồi giữ ByteBuffer callback | Dùng dữ liệu sau lifecycle | Copy bytes hoặc giữ stage đúng thời gian |
| Tin `ByteBuffer.array()` luôn dùng được | Direct/read-only buffers lỗi | Đọc từ position đến limit, copy phần cần |
| Đếm business messages bằng số callback | Metrics sai khi fragmentation/Ping/Pong | Đếm `last=true` và parse business records |
| Request quá nhiều credit trước khi có capacity | Backpressure yếu, tràn queue | Bounded demand + backpressure thật |
| Dùng shared StringBuilder cho nhiều sockets | Race/ghép nhầm message | State per WebSocket, concurrency-safe |
| Không xử lý close/error terminal | Rò rỉ tài nguyên | Cleanup, đóng/abort và trạng thái kết thúc |
| Không phân biệt send và receive | Tưởng `sendText` bị giới hạn bởi `request` | Demand chỉ điều tiết receive callbacks |
| Không test fragmentation | Code chạy với tin nhắn nhỏ nhưng hỏng thực tế | Test nhiều partial callbacks, Ping xen kẽ, Close |

## 15. Kiểm thử đúng ngữ nghĩa: một callback không bằng một message

Một bộ test đơn vị cho listener nên có **các chuỗi callback** chứ không chỉ một `onText("hello", true)`:

| Kịch bản | Chuỗi callback | Kỳ vọng |
|---|---|---|
| Text một phần | `onText("Hi", true)` | 1 complete text message, 1 credit |
| Text chia 2 phần | `onText("Hel", false)`, `onText("lo", true)` | 1 complete text message, 2 credits |
| Text chia 3 phần | false, false, true | 1 message, 3 credits |
| Binary chia 2 phần | `onBinary(bufA,false)`, `onBinary(bufB,true)` | Ghép byte chính xác, 2 credits |
| Ping xen kẽ | Text fragment, `onPing`, final text | Ping tiêu thêm credit, không tạo text message |
| Pong | `onPong` | 1 credit, không tạo text message |
| Close | `onClose` | 1 credit; kết thúc listener callbacks |
| Error khi demand 0 | `onError` | Có thể được gọi, không cần credit |
| Demand 0 | Có dữ liệu tiếp nhưng chưa request | Không gọi receive method mới |
| `request(0)` | Argument không hợp lệ | Ném `IllegalArgumentException` |
| Stage chậm | Callback trả stage pending rồi request tiếp | Không suy rằng callback sau bắt buộc chờ stage hoàn tất |
| Message lớn | Nhiều fragment vượt limit | Đóng/từ chối theo policy, không giữ vô hạn |

**Tách hai loại test:**

- **Unit test/harness** (như `WebSocketDemandDemo`) kiểm tra logic ghép và quản lý credit một cách xác định. Harness có thể chủ động gọi callback theo chuỗi mong muốn.
- **Integration test** với server WebSocket thật kiểm tra handshake, fragmentation trên wire, Ping/Pong, Close handshake, TLS, timeout và behavior của đúng Java runtime. **Không ép JDK phải chia một message thành đúng số callback được phỏng đoán từ số frame**; hãy kiểm tra tính đúng đắn với mọi cách chia hợp lệ.

### Các số đo nên tách riêng

- `receiveInvocations`: số lần vào `onText`, `onBinary`, `onPing`, `onPong`, `onClose`.
- `completeTextMessages`: chỉ tăng khi `onText(..., last=true)` kết thúc message.
- `completeBinaryMessages`: tương tự `onBinary(..., last=true)`.
- `controlMessages`: Ping/Pong/Close riêng, không cộng vào business text count.
- `partialBytes / partialChars`: kích thước message đang tích lũy.
- `queuedMessages`, `processingLatency`, `timeouts`, `errors`, `inputClosed`: phản ánh trạng thái application; không suy ra từ demand một mình.

Một ứng dụng có thể nhận 10 callbacks cho một message binary và 3 Ping, nghĩa là 13 credits đã dùng nhưng chỉ một business message hoàn chỉnh.

## 16. FAQ: các câu hỏi hay bị nhầm

### `request(3)` có nghĩa tôi sẽ nhận chính xác ba messages không?

**Không.** Nó cấp khả năng gọi **tối đa ba receive method invocations nữa**. Đó có thể là ba fragments của một message, một text fragment + Ping + Pong, ba messages nhỏ, hoặc ít hơn ba callback nếu peer không gửi đủ sự kiện/connection kết thúc.

### Nếu peer chỉ gửi một text message nhỏ thì `request(1)` có đủ không?

**Có thể đủ** nếu runtime giao toàn message qua một `onText(..., last=true)`. Nhưng bạn **không được phụ thuộc** vào giả định đó cho mọi message. Listener phải hoạt động đúng khi có nhiều partial callbacks.

### Tôi có nên gọi `request(1)` sau mỗi `onText` không?

Đây là **mẫu đơn giản được Javadoc minh họa** và giúp không kẹt ở fragment giữa chừng. Tuy nhiên, khi downstream quá tải, cần cấp demand **khi thực sự còn capacity**, không cấp vô hạn. Dù dùng cách nào, không quên `last=false` vẫn cần được tiếp tục đọc nếu muốn hoàn thành message.

### `request(1)` có phải ACK cho message bên kia không?

Không. Nó là **credit nội bộ** điều tiết callback delivery của JDK WebSocket client, không gửi một business ACK, không tự xác nhận JSON đã xử lý và không xác nhận transaction. Nếu protocol ứng dụng cần ACK, thiết kế message riêng và gửi bằng `sendText`/`sendBinary` với hợp đồng tương ứng.

### `CompletionStage.completedFuture(null)` có tự cấp thêm demand không?

Không. Stage thể hiện callback đã hoàn tất việc sử dụng dữ liệu/cho phép runtime thu hồi nó; **counter demand độc lập**. Khi cần, listener phải gọi `request` rõ ràng.

### Nếu tôi bỏ qua Ping/Pong callback thì có ảnh hưởng demand không?

Có. Ping/Pong là **receive methods** và tiêu thụ credit. Mặc định của `onPing`/`onPong` trong Java 17 gọi `request(1)`, nên nếu không override sẽ có cơ chế cấp thêm; khi override phải xem lại policy. Không tính Ping/Pong thành complete business message.

### `onError` có bị kẹt khi counter bằng 0 không?

Không theo nghĩa demand. `onError` **không** thuộc receive methods, Java 17 cho phép gọi nó bất cứ lúc nào sau `onOpen`. Nó là callback kết thúc khi lỗi và không phải một message để đếm.

### `onClose` có đếm vào request(n) không?

**Có.** `onClose` nằm trong năm receive methods bị điều tiết. Sau `onClose` sẽ không còn callback nào nữa của WebSocket đó, bất kể còn credit.

### Nếu return stage đang pending, WebSocket có chắc ngừng gọi callback không?

**Không.** Javadoc nói CompletionStage và counter invocations là hai cơ chế khác nhau; vẫn có thể có invocation tiếp theo khi đã cấp demand. Muốn giảm receive rate, quản lý demand và queue; muốn giữ lifetime của buffer, quản lý completion stage.

### Request(n) có điều tiết chiều gửi `sendText` không?

**Không.** `sendText` và `sendBinary` là các thao tác send, trả CompletableFuture mô tả completion phía gửi. `request(n)` điều tiết **phương thức nhận** của listener, không phải send quota.

### Khi một message bị bỏ giữa chừng do lỗi parser thì sao?

Phải có policy kết thúc/đóng rõ ràng. Không để `StringBuilder`/`ByteBuffer` dở dang và giữ kết nối vô hạn; có thể gửi Close theo protocol nếu còn hợp lệ hoặc `abort` trong tình huống cần kết thúc cưỡng bức. Cần cleanup connection state và ghi nhận error không lộ nội dung nhạy cảm.

## 17. Checklist khi viết WebSocket.Listener production

1. **Đọc đúng API Java 17:** `request(n)` tính theo số **receive callbacks**, không phải complete messages hoặc raw frames.
2. **Đặt demand ban đầu trong `onOpen`** nếu override; nhớ default `onOpen` tự request(1).
3. **Ghép text/binary theo `last`**, không parse message hoàn chỉnh khi `last=false`.
4. **Sau mỗi fragment chưa cuối, có cơ chế cấp credit tiếp** khi đủ capacity; tránh kẹt giữa message.
5. **Tính Ping/Pong/Close vào receive budget**; `onOpen`/`onError` không tiêu credit.
6. **Không dùng request(0)/request(-1)**, vì n phải dương; request nhiều lần cộng demand và không có API rút credit.
7. **Hiểu default listener methods**: onText/onBinary/onPing/onPong có cơ chế request(1) mặc định; override là tự chịu trách nhiệm.
8. **Tách CompletionStage khỏi demand**, không dùng stage completion thay `request` hoặc ngược lại.
9. **Bảo vệ dữ liệu callback lifetime**: copy text/bytes trước khi return completed stage nếu cần xử lý sau đó; không giữ ByteBuffer runtime sau completion.
10. **Giới hạn message size, queue size và thời gian xử lý**; demand không thay streaming/bounded backpressure.
11. **Duy trì state per-connection**, tránh shared mutable StringBuilder giữa nhiều WebSockets.
12. **Xử lý close/error terminal**, không request vô nghĩa sau khi input đã đóng; phân biệt `sendClose` và `abort`.
13. **Đừng block lâu trên callback thread**, phối hợp async processing với quyền sở hữu dữ liệu và thứ tự message.
14. **Đo riêng số callbacks, complete messages và business records**, không dùng counter của demand làm KPI nghiệp vụ.
15. **Test fragmentation, control frames và demand 0** bằng unit harness; test handshake/network/TLS bằng integration test thật.
16. **Ghi rõ giới hạn của ví dụ**, không coi in-memory simulator là server WebSocket thật.

**Kết luận:** `WebSocket.request(n)` trong Java 17 cấp **n lượt gọi nhận tiếp theo** qua `onText`, `onBinary`, `onPing`, `onPong`, `onClose`. Một message text/binary có thể chiếm một hoặc nhiều lượt và chỉ được coi là hoàn chỉnh khi fragment tương ứng có `last == true`. `onOpen` và `onError` không tiêu demand; `CompletionStage` là cơ chế quản lý completion/lifetime khác. Thiết kế đúng phải quản lý **credit, fragmentation, buffer ownership và downstream capacity** như bốn trách nhiệm liên quan nhưng không thể thay cho nhau.

### Tài liệu chính thức

- [Java SE 17 — WebSocket.request(long) và receive-invocation counter](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/WebSocket.html#request(long))
- [Java SE 17 — WebSocket.Listener: onText/onBinary/onPing/onPong/onClose/onError](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/WebSocket.Listener.html)
- [Java SE 17 — WebSocket.Builder, buildAsync và WebSocket lifecycle](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/WebSocket.Builder.html)
- [RFC 6455 — WebSocket Protocol: fragmentation và control frames](https://www.rfc-editor.org/rfc/rfc6455)