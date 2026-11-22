# Vòng đời của `ByteBuffer` và `CharSequence` trong callback `WebSocket.Listener` (Java 11+)

## 1. Vì sao phải hiểu vòng đời dữ liệu trong WebSocket callback?

`java.net.http.WebSocket` là **WebSocket client API chuẩn từ Java 11**. Khi phía đối tác gửi text, binary hoặc control message, Java gọi các phương thức của `WebSocket.Listener` để chuyển dữ liệu vào ứng dụng.

Hai callback quan trọng nhất:

```java
CompletionStage<?> onText(WebSocket webSocket,
                          CharSequence data,
                          boolean last);

CompletionStage<?> onBinary(WebSocket webSocket,
                            ByteBuffer data,
                            boolean last);
```

Vấn đề dễ mắc: biến `data` do **WebSocket implementation cung cấp**. Không nên giữ đối tượng `CharSequence` hoặc `ByteBuffer` đó mãi mãi, đưa nó cho một task chạy sau rồi mặc định rằng nội dung không đổi. Theo hợp đồng API, WebSocket có thể **thu hồi/tái sử dụng** đối tượng nhận được **khi `CompletionStage` do callback trả về đã hoàn tất**. Nếu callback trả `null`, nó được xem tương đương một stage đã hoàn thành bình thường, nên dữ liệu có thể được thu hồi **ngay lập tức**.

Javadoc nêu rõ: **không được tiếp tục truy cập `data` sau khi stage do callback trả về hoàn tất**.

Bài học giải thích cách làm việc an toàn với đối tượng đầu vào theo hai chiến lược:

1. **Copy dữ liệu trong callback** thành `String` hoặc `byte[]` do ứng dụng sở hữu, rồi trả stage đã hoàn tất. Sau đó có thể xử lý các bản sao bất đồng bộ.
2. **Mượn dữ liệu gốc đến khi xử lý xong**, trả một `CompletionStage` còn hiệu lực và chỉ cho nó hoàn tất **sau khi không còn truy cập `data`**. Cách này yêu cầu quản lý vòng đời, thread và flow control cẩn thận hơn.

Các quy tắc này vẫn còn áp dụng trong JDK hiện hành; đây không phải hành vi của một API đã lỗi thời.

## 2. Các callback của `WebSocket.Listener`

| Callback | Dữ liệu / sự kiện | Vòng đời cần quan tâm |
| --- | --- | --- |
| `onOpen(WebSocket)` | Kết nối WebSocket đã được thiết lập | Nên gọi `webSocket.request(1)` để cấp nhu cầu nhận ban đầu |
| `onText(WebSocket, CharSequence, boolean)` | Một phần hoặc toàn bộ **text message** | `CharSequence` chỉ được giữ/truy cập tới khi stage trả về hoàn tất |
| `onBinary(WebSocket, ByteBuffer, boolean)` | Một phần hoặc toàn bộ **binary message** | `ByteBuffer` chỉ được giữ/truy cập tới khi stage trả về hoàn tất |
| `onPing(WebSocket, ByteBuffer)` | Ping control message; tối đa 125 byte | Cùng hợp đồng thu hồi `ByteBuffer` sau stage |
| `onPong(WebSocket, ByteBuffer)` | Pong control message; tối đa 125 byte | Cùng hợp đồng thu hồi `ByteBuffer` sau stage |
| `onClose(WebSocket, int, String)` | Input của WebSocket đã đóng | Stage trả về điều khiển thời điểm output có thể đóng, **không phải hợp đồng giữ `ByteBuffer`** |
| `onError(WebSocket, Throwable)` | Lỗi kết nối hoặc xử lý callback | Trả `void`; là callback cuối của socket liên quan |

**Lưu ý:** `onOpen` và `onError` không tiêu thụ một đơn vị yêu cầu nhận từ counter `request(n)`. Các lời gọi nhận như `onText`, `onBinary`, `onPing`, `onPong` và `onClose` thuộc nhóm receive methods của WebSocket. Khi WebSocket mới được tạo, counter nhận ban đầu bằng **0**.

Những implementation mặc định của `onText`, `onBinary`, `onPing` và `onPong` về cơ bản gọi `webSocket.request(1)` rồi trả `null`. Nếu override callback, bạn cần chủ động thiết kế chính sách `request(n)` của mình.

## 3. Hợp đồng quan trọng nhất: `CompletionStage<?>` là tín hiệu sở hữu dữ liệu

### 3.1. Stage hoàn tất có nghĩa gì?

Với `onText` và `onBinary`:

- Callback nhận một tham chiếu `data` từ WebSocket.
- Callback trả **`CompletionStage<?>`**, dùng để báo **khi nào WebSocket có thể thu hồi** `data`.
- Trước khi stage hoàn tất, callback/application có thể dùng dữ liệu theo hợp đồng API và quy tắc thread-safety phù hợp.
- **Sau khi stage hoàn tất, không truy cập `data` nữa**; bộ nhớ hoặc đối tượng cung cấp trước đó có thể được tái sử dụng.
- Trả **`null`** có nghĩa dữ liệu có thể được thu hồi ngay, giống trả một stage đã hoàn thành bình thường.

Sơ đồ:

```text
WebSocket nhận một phần dữ liệu
           |
           v
onText(ws, CharSequence, last)
       hoặc
onBinary(ws, ByteBuffer, last)
           |
           | application đọc/copy dữ liệu
           v
callback trả CompletionStage
           |
           | còn đang pending: WebSocket chưa được thông báo
           | quyền thu hồi của dữ liệu callback đó
           v
stage hoàn tất / callback trả null
           |
           v
WebSocket có thể reclaim data
           |
           v
KHÔNG truy cập lại CharSequence / ByteBuffer đã mượn
```

Từ khóa là **“có thể thu hồi”**, không phải “chắc chắn đã ghi đè bộ nhớ ngay”. Một chương trình có vẻ vẫn đọc đúng dữ liệu sau stage completion là **hành vi không được bảo đảm** và có thể lỗi ngẫu nhiên khi tải tăng hoặc triển khai thay đổi.

### 3.2. `null`, `completedFuture` và stage bất đồng bộ

| Callback trả về | Thời điểm WebSocket có thể reclaim dữ liệu |
| --- | --- |
| `null` | Ngay lập tức khi callback kết thúc |
| `CompletableFuture.completedFuture(null)` | Stage đã hoàn tất, có thể reclaim ngay |
| Một `CompletableFuture<Void> pending` | Khi future đó được hoàn tất |
| Stage của một tác vụ xử lý bất đồng bộ | Khi stage của tác vụ hoàn tất; **không truy cập data sau đó** |

Không nên cố kéo dài một stage mãi mãi chỉ để giữ tham chiếu gốc. Điều đó làm phức tạp quản lý tài nguyên và rủi ro lỗi/hủy. Để giữ dữ liệu phục vụ lưu trữ, phân tích hoặc chuyển sang thread khác lâu dài, **copy thành giá trị do ứng dụng quản lý** là lựa chọn thông thường.

### 3.3. Stage và `request(n)` không phải cùng một cơ chế

Đây là điểm rất dễ nhầm:

- **`CompletionStage` trả về:** thông báo thời điểm dữ liệu mà **callback cụ thể** nhận được có thể được WebSocket thu hồi; đồng thời stage lỗi có thể khiến `onError` được gọi.
- **`webSocket.request(n)`:** tăng **số lần callback nhận dữ liệu** mà WebSocket được phép gọi (demand counter).

Một stage **chưa hoàn tất không tự động ngăn** các callback sau nếu ứng dụng đã cấp demand. Javadoc nêu rõ stage và counter yêu cầu nhận **độc lập**: listener có thể nhận thêm callback trong lúc stage của callback trước vẫn pending.

**Ví dụ tư duy:** application gọi `request(10)` rồi `onBinary` đầu tiên trả stage pending. Nếu còn demand, các callback tiếp theo vẫn có thể được gọi; stage pending không phải khóa chặn toàn bộ WebSocket.

Khi muốn điều tiết nhận dữ liệu theo năng lực xử lý, **quyết định khi nào gọi `request(1)`**, đồng thời quản lý stage trả về theo vòng đời dữ liệu. Không dùng một trong hai cơ chế thay cơ chế còn lại.

## 4. `CharSequence` trong `onText`: không giả định nó luôn là `String`

`onText(WebSocket, CharSequence, boolean)` nhận một đối tượng triển khai `CharSequence`. Kiểu compile-time chỉ là interface; không có cam kết nó luôn là `String` bất biến.

Các implementation của `CharSequence` có thể bao gồm `String`, `StringBuilder`, `StringBuffer`, `CharBuffer` hoặc một implementation khác. Nếu giữ trực tiếp tham chiếu `CharSequence` hoặc gọi `subSequence(...)`, bạn có thể vẫn đang trỏ đến vùng dữ liệu mà nơi khác được phép thay đổi/tái sử dụng.

### 4.1. Snapshot an toàn

```java
@Override
public CompletionStage<?> onText(
        WebSocket webSocket, CharSequence data, boolean last) {
    String snapshot = data.toString(); // Giữ nội dung thành String ổn định.
    processTextPiece(snapshot, last);
    webSocket.request(1);
    return CompletableFuture.completedFuture(null);
}
```

**Đoạn trên chỉ minh họa callback**, cần có class listener, import `WebSocket`, `CompletionStage`, `CompletableFuture` và phương thức `processTextPiece`. Ví dụ đầy đủ ở mục 9 biên dịch và chạy độc lập.

`data.toString()` tạo/thu được `String` có nội dung tại thời điểm gọi. `String` bất biến: sau này dù nguồn `CharSequence` mượn đã hết vòng đời, **snapshot vẫn có nội dung riêng có thể sử dụng**. Nếu `data` vốn là `String`, `toString()` có thể trả chính nó, điều này vẫn an toàn vì String không thể bị sửa nội dung qua API.

### 4.2. Đừng lưu `CharSequence` gốc để ghép sau

Không an toàn nếu stage đã được hoàn tất:

```java
// SAI: giữ tham chiếu đối tượng do WebSocket cung cấp.
// List<CharSequence> parts = new ArrayList<>();
// public CompletionStage<?> onText(WebSocket ws, CharSequence data, boolean last) {
//     parts.add(data);
//     ws.request(1);
//     return null; // data có thể bị reclaim ngay.
// }
```

Thay bằng bản sao:

```java
// Khi dùng message fragmentation:
String piece = data.toString();
parts.add(piece); // List<String>, từng phần bất biến.
```

Nếu bạn muốn giữ trực tiếp `CharSequence` cho đến khi xử lý xong, phải duy trì stage chưa hoàn tất **cho đến sau lần truy cập cuối**, có đồng bộ hóa và quản lý demand phù hợp. Cách giữ danh sách `String` đơn giản và dễ kiểm thử hơn.

### 4.3. `last` là dấu kết thúc message, không phải dấu kết thúc kết nối

Một text message có thể tới qua nhiều lần `onText`:

```text
onText("Xin ", false)
onText("chào", true)
=> 1 message hoàn chỉnh: "Xin chào"
```

**`last == false`:** còn phần của **cùng message** sẽ theo sau. **`last == true`:** callback hiện tại hoàn tất message đó. Nó không có nghĩa WebSocket sẽ đóng hoặc không có message khác nữa.

Javadoc Java 11 bảo đảm `CharSequence` trong `onText` là một **chuỗi UTF-16 hợp lệ**. Tuy vậy, việc chuyển `String` thành byte hay biết kích thước mạng vẫn phải xác định encoding; `String.length()` đếm UTF-16 code unit, **không phải số byte UTF-8**.

Nếu text message được ghép thành một chuỗi lớn, cần giới hạn số ký tự/byte theo hợp đồng ứng dụng. Không để một client không tin cậy phát hàng triệu fragment khiến `StringBuilder` tăng vô hạn.

## 5. `ByteBuffer` trong `onBinary`: chỉ đọc `position..limit`

`onBinary(WebSocket, ByteBuffer, boolean)` nhận các byte nằm trong vùng:

```text
data.position() <= index < data.limit()
```

Không được mặc định dữ liệu có từ index `0` hoặc có số byte bằng `capacity()`.

| Thuộc tính | Ý nghĩa |
| --- | --- |
| `capacity()` | Dung lượng vùng nhớ có thể chứa |
| `position()` | Vị trí byte hợp lệ tiếp theo để đọc |
| `limit()` | Giới hạn trên của vùng dữ liệu được đưa vào callback |
| `remaining()` | Số byte chưa đọc: `limit() - position()` |
| `hasArray()` | Cho biết buffer có expose backing `byte[]` hay không |

**Đúng:** `data.remaining()` là số byte của phần binary hiện tại khi bắt đầu đọc theo `position..limit`.

**Sai:** `data.capacity()` hoặc `data.array().length` là số byte thực của callback. Buffer có thể có prefix/suffix, có thể là **direct buffer**, hoặc không cho truy cập mảng nền.

### 5.1. Cách copy byte an toàn

```java
ByteBuffer view = data.asReadOnlyBuffer();
byte[] snapshot = new byte[view.remaining()];
view.get(snapshot);
```

Giải thích:

1. `asReadOnlyBuffer()` tạo **view** có trạng thái position/limit riêng để đọc, tránh làm thay đổi position của `data` gốc khi gọi `view.get(...)`.
2. `view.remaining()` tính đúng số byte từ vị trí đến giới hạn của callback.
3. `new byte[view.remaining()]` cấp mảng **do ứng dụng sở hữu**.
4. `view.get(snapshot)` **copy từng byte** vào mảng mới. Sau khi copy, có thể giữ `snapshot` ngoài vòng đời callback.
5. **Bản thân `view` chưa phải bản sao dữ liệu độc lập!** Nó vẫn chia sẻ cùng vùng nhớ với buffer gốc; chỉ `byte[] snapshot` vừa tạo mới độc lập.

Một cách khác:

```java
ByteBuffer view = data.duplicate();
byte[] snapshot = new byte[view.remaining()];
view.get(snapshot);
```

`duplicate()` tạo view có position/limit riêng nhưng **chia sẻ nội dung gốc**. Nó chỉ an toàn cho retention nếu bạn **copy** trước khi stage callback hoàn tất.

### 5.2. Vì sao `slice` và `asReadOnlyBuffer` chưa đủ?

Các cách sau **không sở hữu một bản sao của byte dữ liệu**:

```java
ByteBuffer duplicate = data.duplicate();
ByteBuffer slice = data.slice();
ByteBuffer readOnly = data.asReadOnlyBuffer();
```

Tất cả đều có thể chia sẻ backing storage với `data`. Sau khi WebSocket được phép reclaim `data`, các view đó cũng có thể quan sát dữ liệu bị thay đổi. **Read-only** chỉ cấm ghi **qua view**, không biến dữ liệu được chia sẻ thành bất biến.

Nếu cần giữ một `ByteBuffer` độc lập thay vì `byte[]`:

```java
ByteBuffer view = data.asReadOnlyBuffer();
ByteBuffer owned = ByteBuffer.allocate(view.remaining());
owned.put(view);
owned.flip();
// 'owned' giữ một bản sao byte riêng.
```

Lúc này vùng nhớ của `owned` là vùng mới, nên có thể truyền qua một queue bất đồng bộ sau khi callback trả stage hoàn tất. `owned` vẫn là buffer mutable do ứng dụng quản lý; hãy bảo vệ khỏi chỉnh sửa đồng thời ngoài ý muốn.

### 5.3. Direct buffer và mảng nền

`ByteBuffer` callback **không được đảm bảo là heap buffer**. Vì vậy:

```java
// Không an toàn cho mọi ByteBuffer:
// byte[] raw = data.array();
```

Với direct buffer, `hasArray() == false`; gọi `array()` sẽ ném `UnsupportedOperationException`. Ngay cả với heap buffer, `array()` có thể chứa byte nằm ngoài vùng `position..limit` và `arrayOffset()` có thể khác `0`.

Dùng `duplicate()/asReadOnlyBuffer()` + `get(byte[])` là cách không phụ thuộc loại buffer và dễ giữ đúng vùng byte hợp lệ.

## 6. Giữ dữ liệu cho xử lý bất đồng bộ

### 6.1. Cách khuyên dùng: copy trước khi trả stage

Khi muốn chuyển dữ liệu tới một worker/queue, snapshot trong callback trước:

```java
@Override
public CompletionStage<?> onBinary(
        WebSocket webSocket, ByteBuffer data, boolean last) {
    ByteBuffer view = data.asReadOnlyBuffer();
    byte[] snapshot = new byte[view.remaining()];
    view.get(snapshot); // Sao chép trước khi WebSocket được reclaim.

    enqueue(snapshot, last); // Chỉ chuyển bản sao do ứng dụng sở hữu.
    webSocket.request(1);
    return CompletableFuture.completedFuture(null);
}
```

Đây là **mã minh họa**, cần có phương thức `enqueue` hợp lệ. Chính sách queue và lỗi của `enqueue` cần được thiết kế cẩn thận. Với queue có giới hạn, không gọi `request(1)` vô hạn khi queue đầy: cần trì hoãn cấp demand hoặc xử lý quá tải theo contract ứng dụng.

Sau khi callback hoàn tất, phía worker **không đọc `data` hay `view`**, chỉ đọc `snapshot`.

### 6.2. Nếu phải giữ nguyên data đến khi tác vụ xong

Một thiết kế khác là trả stage chỉ hoàn tất khi việc xử lý input gốc hoàn tất:

```java
@Override
public CompletionStage<?> onBinary(
        WebSocket socket, ByteBuffer data, boolean last) {
    CompletableFuture<Void> processing =
            CompletableFuture.runAsync(
                    () -> consumeBorrowedBuffer(data, last),
                    processingExecutor);

    return processing.whenComplete((ignored, error) -> {
        if (error == null) {
            socket.request(1);
        }
    });
}
```

Đây là **mã minh họa không độc lập**: cần khai báo `processingExecutor`, `consumeBorrowedBuffer` và cơ chế lỗi/đóng khi task thất bại. Phải bảo đảm:

- `consumeBorrowedBuffer` **không giữ tham chiếu/không truy cập `data`** sau khi task kết thúc.
- Không còn callback hay thread nào khác đụng vào cùng dữ liệu ngoài phạm vi mà API bảo đảm.
- Nếu xử lý thất bại, stage hoàn thành **exceptionally**, và WebSocket có thể gọi `onError` theo hợp đồng.
- `socket.request(1)` quyết định nhận thêm dữ liệu; **không được hiểu** stage pending tự động ngăn callback kế tiếp nếu trước đó còn demand.
- Không dùng executor không giới hạn hoặc task blocking vô thời hạn; theo dõi tài nguyên, timeout và cancellation.

Đây là lựa chọn **phức tạp hơn**; nếu không cần tránh một lần copy, thường nên snapshot rồi chỉ làm việc với bản sao.

### 6.3. `CompletionStage` không thay thế giới hạn bộ nhớ

Ngay cả khi ứng dụng chỉ `request(1)` sau xử lý, một message lớn vẫn có thể được chia thành nhiều fragment. Bạn phải giới hạn tổng số byte hoặc ký tự của message và tổng dữ liệu đang chờ trong queue. Một client không tin cậy có thể gửi message rất lớn dù mỗi fragment nhỏ.

Tránh gọi `join()` hoặc `get()` trên một future chưa hoàn tất **ngay bên trong callback** chỉ để giả vờ giữ dữ liệu lâu: cách đó có thể làm nghẽn thread callback. Dùng continuation/queue cùng stage, hoặc copy nhanh rồi trả quyền sở hữu.

## 7. Fragmentation và trạng thái tích lũy từng message

### 7.1. Text message nhiều callback

Một message có thể chia thành nhiều phần `last=false` rồi `last=true`:

```java
StringBuilder wholeText = new StringBuilder();

@Override
public CompletionStage<?> onText(
        WebSocket socket, CharSequence data, boolean last) {
    wholeText.append(data.toString());
    if (last) {
        String completeMessage = wholeText.toString();
        wholeText.setLength(0);
        handleCompleteText(completeMessage);
    }
    socket.request(1);
    return CompletableFuture.completedFuture(null);
}
```

Mã **minh họa** cần class, import và `handleCompleteText`. Cần kiểm soát `wholeText.length()` trước khi append nếu dữ liệu đến từ nguồn không tin cậy.

Đừng coi mỗi `onText` là một message hoàn chỉnh. `last` chỉ cho biết mảnh hiện tại có kết thúc message hay không.

### 7.2. Binary message nhiều callback

Tương tự, dùng `ByteArrayOutputStream` hoặc vùng đệm do ứng dụng quản lý để ghép các **byte đã copy** từ các phần nhận:

```java
ByteArrayOutputStream parts = new ByteArrayOutputStream();

@Override
public CompletionStage<?> onBinary(
        WebSocket socket, ByteBuffer data, boolean last) {
    ByteBuffer view = data.asReadOnlyBuffer();
    byte[] fragment = new byte[view.remaining()];
    view.get(fragment);
    parts.write(fragment, 0, fragment.length);

    if (last) {
        byte[] completeMessage = parts.toByteArray();
        parts.reset();
        handleCompleteBinary(completeMessage);
    }
    socket.request(1);
    return CompletableFuture.completedFuture(null);
}
```

Đây là **mã minh họa** cần fields, imports và phương thức handler. Lưu ý `toByteArray()` trả bản sao `byte[]`, còn `reset()` cho phép dùng lại bộ đệm tích lũy cho message tiếp theo.

### 7.3. Control message và lifecycle

Một Ping/Pong có dữ liệu `ByteBuffer` tối đa 125 byte theo WebSocket protocol; callback `onPing`/`onPong` có **hợp đồng reclaim** tương tự `onBinary`. Nếu cần giữ payload control frame để log hoặc kiểm thử, hãy copy trước khi stage hoàn tất.

WebSocket client tự xử lý phản hồi Pong cho Ping và Close handshake theo protocol; ứng dụng thường không cần tự gửi Pong chỉ vì `onPing` được gọi. Nhưng nếu override `onPing`/`onPong`, vẫn cần thiết kế demand và stage; mặc định callback đã thực hiện `request(1)` và trả `null`.

Control frames có thể xuất hiện trong lúc một data message đang được chia nhỏ. Do đó, trạng thái tích lũy của text/binary message phải được quản lý riêng và không bị reset khi chỉ nhận Ping/Pong.

## 8. `request(n)`, tuần tự callback và xử lý song song

### 8.1. Demand counter vận hành thế nào?

Một WebSocket vừa tạo có internal receive counter bằng `0`:

1. `onOpen` thường gọi `request(1)` để cho phép **một callback nhận**.
2. Khi WebSocket gọi một receive method, counter giảm `1`.
3. Sau khi listener đã nhận/xử lý phần dữ liệu mong muốn, nó có thể gọi `request(1)` để cho phép callback tiếp theo.
4. Nếu counter về `0`, WebSocket **không tiếp tục gọi receive methods** cho tới khi ứng dụng cấp thêm demand; `onError` có cơ chế riêng và có thể xảy ra bất kể demand.

Một cách dùng phổ biến:

```java
@Override
public void onOpen(WebSocket socket) {
    socket.request(1);
}
```

Nếu override `onText`/`onBinary` nhưng **quên `request` lại**, ứng dụng có thể chỉ nhận một callback rồi đứng chờ mãi, dù kết nối vẫn còn mở.

### 8.2. Callback có tuần tự tuyệt đối không?

Theo Javadoc, **đối với một WebSocket cụ thể**, callback listener được gọi theo trình tự an toàn, **không reentrant**: lời gọi callback sau chỉ bắt đầu khi **phương thức callback trước đã trả về**.

Nhưng phải phân biệt:

- **Phương thức callback đã trả về:** có thể gọi callback tiếp theo nếu còn demand.
- **`CompletionStage` do callback trước trả về đã hoàn tất:** không phải điều kiện để được gọi callback tiếp theo.

Hai tác vụ bất đồng bộ được khởi động bởi hai callback liên tiếp có thể **chạy cùng lúc**, dù chính hai lần gọi method callback không chồng lên nhau. Nếu cùng sửa `StringBuilder`/`ByteArrayOutputStream` của listener từ các thread phụ, cần đồng bộ hóa hoặc tổ chức single-threaded processing rõ ràng.

Nếu **cùng một listener instance** được gắn cho **nhiều WebSocket**, callback đến từ các socket khác nhau có thể đồng thời. Không dùng chung trạng thái message giữa socket A và B nếu không định danh và phân tách từng phiên.

### 8.3. Stage lỗi và callback cuối

Theo API, nếu listener callback ném exception hoặc stage do nó trả về hoàn thành exceptionally, WebSocket có thể gọi `onError`. Đừng chôn ngoại lệ trong future mà không có giám sát. `onError` là callback cuối của WebSocket liên quan, không nên ném thêm ngoại lệ từ `onError` vì hành vi sau đó không được định nghĩa.

`onClose` là callback đặc biệt: stage trả về điều khiển khi nào WebSocket **có thể đóng phía output**, khác mục đích lifetime của `ByteBuffer`/`CharSequence` trong các callback data.

## 9. Chương trình Java 11 hoàn chỉnh — kiểm tra copy trước khi reclaim

Chương trình dưới đây **không mở kết nối mạng**. Nó tạo một listener như ứng dụng thực tế và một **`CountingSocket` giả lập** chỉ ghi nhận số lần `request(n)`. Sau đó main **gọi trực tiếp callback** để kiểm thử:

- `CharSequence` có thể thay đổi (một `StringBuilder`) nhưng bản sao `String` của listener không đổi.
- `ByteBuffer` trực tiếp (direct) chỉ có vùng `position..limit` được copy.
- Sau callback, buffer gốc bị sửa nhưng mảng `byte[]` đã copy vẫn giữ giá trị cũ.
- Stage hoàn tất và demand counter là hai khái niệm độc lập.

Đây là **unit test về code xử lý callback**, không mô phỏng một WebSocket protocol engine thực sự và **không chứng minh chính sách thu hồi bộ nhớ của implementation**; chính sách lifetime được quy định bởi Javadoc ở mục 3.

Tạo tệp **`CallbackDataLifecycleDemo.java`**:

```java
import java.io.ByteArrayOutputStream;
import java.net.http.WebSocket;
import java.nio.ByteBuffer;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionStage;

public class CallbackDataLifecycleDemo {
    static final class SafeListener implements WebSocket.Listener {
        private final StringBuilder textParts = new StringBuilder();
        private final ByteArrayOutputStream binaryParts = new ByteArrayOutputStream();
        private final List<String> texts = new ArrayList<>();
        private final List<byte[]> binaries = new ArrayList<>();

        @Override
        public void onOpen(WebSocket socket) {
            socket.request(1);
        }

        @Override
        public CompletionStage<?> onText(
                WebSocket socket, CharSequence data, boolean last) {
            String snapshot = data.toString();
            textParts.append(snapshot);
            if (last) {
                texts.add(textParts.toString());
                textParts.setLength(0);
            }
            socket.request(1);
            return CompletableFuture.completedFuture(null);
        }

        @Override
        public CompletionStage<?> onBinary(
                WebSocket socket, ByteBuffer data, boolean last) {
            ByteBuffer view = data.asReadOnlyBuffer();
            byte[] snapshot = new byte[view.remaining()];
            view.get(snapshot);
            binaryParts.write(snapshot, 0, snapshot.length);
            if (last) {
                binaries.add(binaryParts.toByteArray());
                binaryParts.reset();
            }
            socket.request(1);
            return CompletableFuture.completedFuture(null);
        }
    }

    static final class CountingSocket implements WebSocket {
        private long requests;

        @Override
        public void request(long n) {
            if (n <= 0) {
                throw new IllegalArgumentException("n must be positive");
            }
            requests += n;
        }

        @Override
        public CompletableFuture<WebSocket> sendText(CharSequence data, boolean last) {
            throw new UnsupportedOperationException("test only");
        }

        @Override
        public CompletableFuture<WebSocket> sendBinary(ByteBuffer data, boolean last) {
            throw new UnsupportedOperationException("test only");
        }

        @Override
        public CompletableFuture<WebSocket> sendPing(ByteBuffer data) {
            throw new UnsupportedOperationException("test only");
        }

        @Override
        public CompletableFuture<WebSocket> sendPong(ByteBuffer data) {
            throw new UnsupportedOperationException("test only");
        }

        @Override
        public CompletableFuture<WebSocket> sendClose(int statusCode, String reason) {
            throw new UnsupportedOperationException("test only");
        }

        @Override
        public String getSubprotocol() {
            return "";
        }

        @Override
        public boolean isInputClosed() {
            return false;
        }

        @Override
        public boolean isOutputClosed() {
            return false;
        }

        @Override
        public void abort() {
        }
    }

    public static void main(String[] args) {
        CountingSocket socket = new CountingSocket();
        SafeListener listener = new SafeListener();
        listener.onOpen(socket);

        StringBuilder mutableText = new StringBuilder("Xin ");
        listener.onText(socket, mutableText, false);
        mutableText.replace(0, mutableText.length(), "OVERWRITTEN");
        listener.onText(socket, new StringBuilder("chào"), true);
        System.out.println("complete text: " + listener.texts.get(0));
        System.out.println("original text now: " + mutableText);

        ByteBuffer direct = ByteBuffer.allocateDirect(6);
        direct.put(new byte[] {99, 1, 2, 3, 88, 77});
        direct.flip();
        direct.position(1);
        direct.limit(4);
        listener.onBinary(socket, direct, false);
        direct.put(1, (byte) 42);
        listener.onBinary(socket, ByteBuffer.wrap(new byte[] {4, 5}), true);
        System.out.println("complete binary: " + Arrays.toString(listener.binaries.get(0)));
        System.out.println("original buffer position: " + direct.position());
        System.out.println("original buffer first byte now: " + direct.get(1));
        System.out.println("requested callbacks: " + socket.requests);

        CompletableFuture<Void> pending = new CompletableFuture<>();
        WebSocket.Listener deferred = new WebSocket.Listener() {
            @Override
            public CompletionStage<?> onBinary(
                    WebSocket socket, ByteBuffer data, boolean last) {
                return pending; // Chỉ mô phỏng tín hiệu stage, không gửi mạng.
            }
        };
        deferred.onBinary(socket, ByteBuffer.wrap(new byte[] {6}), true);
        System.out.println("stage done before: " + pending.isDone());
        pending.complete(null);
        System.out.println("stage done after: " + pending.isDone());
        System.out.println("requests after completing stage: " + socket.requests);
    }
}
```

Biên dịch và chạy bằng **JDK 11+**. Với JDK mới, `--release 11` bảo đảm code chỉ dùng API/ngôn ngữ đã có trong Java 11:

```bash
javac --release 11 -encoding UTF-8 CallbackDataLifecycleDemo.java
java CallbackDataLifecycleDemo
```

**Đầu ra chính xác đã kiểm thử:**

```text
complete text: Xin chào
original text now: OVERWRITTEN
complete binary: [1, 2, 3, 4, 5]
original buffer position: 1
original buffer first byte now: 42
requested callbacks: 5
stage done before: false
stage done after: true
requests after completing stage: 5
```

### 9.1. Diễn giải kết quả

1. Listener nhận hai phần text: `"Xin "` với `last=false` và `"chào"` với `last=true`. Nó gọi `toString()` ngay trong callback để giữ snapshot, tạo một message hoàn chỉnh `"Xin chào"`.
2. Sau callback đầu, main sửa `StringBuilder` ban đầu thành `"OVERWRITTEN"`. Vì listener lưu **snapshot String**, phần text trước đó vẫn đúng.
3. `ByteBuffer` direct chứa sáu byte nhưng callback chỉ được cấp vùng từ `position=1` tới `limit=4`, tức **`[1, 2, 3]`**. Callback tiếp theo thêm `[4, 5]`, nên message binary hoàn chỉnh là `[1, 2, 3, 4, 5]`.
4. `asReadOnlyBuffer()` cho một view với position riêng để đọc. Do đó **position của buffer gốc vẫn là `1`**. Khi main sửa `direct.put(1, 42)`, mảng snapshot đã lưu không thay đổi.
5. `requested callbacks: 5` là **tổng số đơn vị demand mà `CountingSocket` giả lập đã ghi nhận**: một lần `request(1)` từ `onOpen` và bốn lần từ hai `onText` + hai `onBinary`. Đây **không phải** số demand còn lại trong một WebSocket thật, vì fake không mô phỏng bước trừ counter khi callback diễn ra.
6. `pending` minh họa stage chưa hoàn tất rồi hoàn tất. Việc hoàn tất stage **không tự gọi `request(1)`** trong fake, nên tổng yêu cầu vẫn là 5. Đây là kiểm chứng riêng về cách application dùng future; **không phải** kiểm chứng WebSocket engine có reclaim buffer khi nào.

Trong hệ thống thực tế, đừng dùng `CountingSocket` để gửi HTTP/WebSocket. Nó chỉ là test double có những phương thức gửi cố tình ném `UnsupportedOperationException` nhằm tách bài toán lifetime ra khỏi vấn đề mạng.

## 10. Đừng nhầm vòng đời dữ liệu nhận với dữ liệu gửi

Các phương thức outbound của `WebSocket` cũng dùng `ByteBuffer` hoặc `CharSequence`, nhưng **hợp đồng sở hữu là khác nhau**.

| Hướng | API | Quy tắc |
| --- | --- | --- |
| **Nhận** | `Listener.onText(ws, CharSequence, last)` | Không truy cập tham số gốc sau khi **stage callback trả về** hoàn tất |
| **Nhận** | `Listener.onBinary(ws, ByteBuffer, last)` | Không truy cập tham số gốc sau khi **stage callback trả về** hoàn tất |
| **Gửi** | `webSocket.sendText(CharSequence data, last)` | **Caller không sửa** CharSequence cho tới khi **CompletableFuture của sendText** hoàn tất |
| **Gửi** | `webSocket.sendBinary(ByteBuffer data, last)` | **Caller không truy cập** ByteBuffer cho tới khi **CompletableFuture của sendBinary** hoàn tất; nếu send thành công, buffer không còn byte remaining |
| **Gửi** | `sendPing/sendPong(ByteBuffer)` | Quy tắc tương tự về không truy cập buffer cho tới khi future gửi hoàn tất |

Ví dụ gửi binary theo đúng vòng đời:

```java
ByteBuffer output = ByteBuffer.wrap(new byte[] {10, 20, 30});
CompletableFuture<WebSocket> sent = webSocket.sendBinary(output, true);

// Trong khi 'sent' pending: KHÔNG đọc/ghi/clear/flip 'output'.
sent.thenAccept(socket -> {
    // Sau khi future gửi thành công, có thể tái sử dụng buffer.
    output.clear();
});
```

Đây là **mã minh họa** cần WebSocket thật và imports. Tránh sửa/read buffer ở thread khác trong lúc send còn pending. `sendText` cũng không được sửa nguồn `CharSequence` trước khi future gửi hoàn tất. `last=true` khi gửi xác định kết thúc message, không có nghĩa phải đóng kết nối.

**Khác biệt chính:** nhận là WebSocket cấp dữ liệu và lấy lại quyền sau **stage listener**; gửi là ứng dụng cấp dữ liệu và đợi **future gửi** hoàn tất trước khi đụng vào vùng nhớ đó.

## 11. Các lỗi thường gặp

| Hiểu nhầm / lỗi | Nguy cơ | Cách làm đúng |
| --- | --- | --- |
| Lưu `CharSequence data` trực tiếp trong `List` rồi trả `null` | Implementation có thể reclaim/tái sử dụng CharSequence | `data.toString()` ngay trong callback, giữ `String` |
| Chuyển `ByteBuffer data` vào queue rồi trả stage hoàn tất | Thread khác đọc buffer đã hết vòng đời | Copy `byte[]` hoặc trì hoãn hoàn tất stage đến hết lần truy cập cuối |
| Lưu `data.slice()` hoặc `data.asReadOnlyBuffer()` rồi tưởng đã copy | View vẫn chia sẻ byte bộ nhớ nguồn | `get(byte[])` hoặc `owned.put(view)` để copy |
| Đọc từ `0` tới `capacity` | Lẫn prefix, suffix hoặc byte không thuộc fragment | Chỉ dùng `position..limit` / `remaining()` |
| Luôn gọi `data.array()` | Direct/read-only buffer không có array được expose | Dùng `duplicate` hoặc `asReadOnlyBuffer` và `get` |
| Không dùng `last` | Xử lý các fragment như message độc lập | Tích lũy từng phần, hoàn tất khi `last=true` |
| Đọc `String.length()` làm byte count | UTF-16 code unit khác số byte UTF-8 | Mã hóa bằng charset phù hợp rồi đếm byte |
| Nghĩ stage pending tự khóa callback sau | Demand và stage là hai cơ chế độc lập | Điều phối `request(n)` và giới hạn queue |
| Quên `request(1)` sau khi override callback | Counter cạn, không nhận message tiếp theo | Cấp demand sau khi đã sẵn sàng xử lý thêm |
| `request(Long.MAX_VALUE)` rồi xử lý chậm/giữ dữ liệu không giới hạn | Ứng dụng có thể bị dồn backlog, tăng RAM | Demand có kiểm soát; giới hạn message size, queue |
| Tưởng callback của nhiều WebSocket không bao giờ chạy đồng thời | Listener chung cho nhiều socket có thể bị truy cập song song | Tách state per socket hoặc đồng bộ hóa |
| Xử lý bất đồng bộ ghi cùng `StringBuilder` mà không khóa | Race condition trong app state | Copy và dùng single-threaded queue / thread-safe design |
| Mapper/handler lỗi nhưng không giám sát `CompletionStage` | WebSocket có thể gọi `onError`, mất dữ liệu | Theo dõi lỗi, đóng và cleanup đúng hợp đồng |
| Truy cập buffer outbound ngay sau `sendBinary` | Future gửi còn pending | Chỉ truy cập sau khi future gửi hoàn tất |
| Xử lý Ping/Pong như message không giới hạn | Có thể giữ payload sai vòng đời | Copy payload và nhớ giới hạn 125 byte |
| Dùng `onClose` như callback onBinary | Stage của onClose có ý nghĩa đóng output | Xử lý close handshake, không giả định giữ buffer |

## 12. Thực hành tốt cho hệ thống WebSocket

1. **Phân biệt sở hữu:** callback input là tài nguyên do WebSocket cấp tạm thời; muốn dùng dài hạn phải copy hoặc quản lý stage cho đến lần truy cập cuối.
2. **Ưu tiên snapshot nhanh:** `String snapshot = data.toString()` cho text; `byte[] snapshot` copy từ `ByteBuffer` theo `remaining()` cho binary.
3. **Không dựa vào việc buffer đang là heap/direct/readonly:** đoạn copy phải xử lý mọi loại ByteBuffer hợp lệ.
4. **Dùng `last` để ghép message:** không assume mỗi callback là message trọn vẹn; có thể có nhiều callback cho một message.
5. **Kiểm soát backpressure:** `request(n)` phải phản ánh khả năng nhận/đưa vào queue; stage hoàn tất không tự tăng demand.
6. **Giới hạn kích thước:** áp hạn mức từng fragment, tổng message, số message in-flight và hàng đợi, đặc biệt khi server không đáng tin cậy.
7. **Theo dõi lỗi và đóng kết nối đúng lúc:** xử lý `onError`, `onClose`, cleanup state và tài nguyên; không tự động retry vô hạn nếu dữ liệu có side effect.
8. **Không block callback lâu:** tránh chờ future bằng `join()`, thao tác IO dài hoặc parse nặng ngay trong callback; chuyển sang executor phù hợp và giữ ranh giới dữ liệu rõ.
9. **Tách state per connection:** listener dùng cho nhiều sockets cần cấu trúc dữ liệu riêng cho mỗi socket và đồng bộ hóa khi cần.
10. **Không log toàn bộ payload nhạy cảm:** mask credential, token, thông tin cá nhân; giới hạn logging text/binary.
11. **Không nhầm hướng gửi và nhận:** future từ `sendBinary/sendText` ràng buộc việc caller được phép tái dùng dữ liệu đầu ra; stage từ listener ràng buộc khi WebSocket được reclaim dữ liệu đầu vào.
12. **Dùng API Java 11+ hiện hành:** `java.net.http.WebSocket` và `WebSocket.Listener` vẫn được duy trì trong JDK mới. Không cần thư viện hoặc API incubator đã lỗi thời để học các hợp đồng này.

## 13. Bài tập tự kiểm tra

**Câu 1.** `onText` nhận `StringBuilder`, callback lưu nó vào một list rồi trả `null`. Có an toàn khi đọc list sau này không?  
**Đáp án:** Không. WebSocket có thể reclaim `CharSequence` ngay khi callback trả `null`. Chuyển nó thành `String` trước khi lưu.

**Câu 2.** `onBinary` nhận buffer có `position=2`, `limit=5`, `capacity=10`. Bao nhiêu byte thuộc callback?  
**Đáp án:** **3 byte**, từ vị trí 2, 3 và 4. Không dùng capacity 10 để suy ra số byte nhận.

**Câu 3.** `data.asReadOnlyBuffer()` có đủ để giữ bytes sau stage completion không?  
**Đáp án:** Không. View read-only có thể chia sẻ backing storage. Cần copy dữ liệu vào mảng/buffer mới hoặc giữ stage pending cho tới khi đọc xong.

**Câu 4.** Stage của `onBinary` chưa hoàn tất. WebSocket có thể gọi callback nhận khác không?  
**Đáp án:** Có, nếu còn demand. Counter `request(n)` và completion của stage là hai cơ chế độc lập.

**Câu 5.** `last=true` trong `onText` có phải đóng WebSocket không?  
**Đáp án:** Không. Nó đánh dấu kết thúc **text message hiện tại**.

**Câu 6.** Khi tự override `onText` mà quên `request(1)`, chuyện gì có thể xảy ra?  
**Đáp án:** Bộ đếm demand cạn và không còn receive callbacks được gọi cho đến khi có `request(n)` mới.

**Câu 7.** `onPing`/`onPong` có được giữ nguyên `ByteBuffer` sau khi trả stage completed không?  
**Đáp án:** Không. Quy tắc reclaim giống `onBinary`; copy nếu cần giữ.

**Câu 8.** Khi gửi `sendBinary(buffer,true)`, có được `buffer.clear()` ngay không?  
**Đáp án:** Không. Chờ future gửi hoàn tất; với gửi thành công, buffer sẽ không còn byte remaining.

**Câu 9.** Listener không reentrant có bảo đảm tất cả task async do listener tạo sẽ không chạy song song không?  
**Đáp án:** Không. Chỉ **lời gọi method callback** là tuần tự trên một WebSocket; các stage/tác vụ async có thể overlap.

## 14. Ghi nhớ

- **`CharSequence` trong `onText`** và **`ByteBuffer` trong `onBinary`** là **dữ liệu mượn từ WebSocket**, không phải object mặc nhiên thuộc sở hữu lâu dài của application.
- **`CompletionStage` do callback trả về** là mốc mà WebSocket **được phép reclaim** dữ liệu; **`null` tương đương đã hoàn tất ngay**. Không truy cập object gốc sau mốc này.
- Với text: **`data.toString()` để có `String` ổn định**. Với binary: **copy vùng `position..limit`** sang `byte[]` hoặc một ByteBuffer mới thực sự sở hữu byte.
- `duplicate()`, `slice()`, `asReadOnlyBuffer()` **không tự copy nội dung**.
- **`request(n)` điều khiển số lần callback được phép gọi**, tách biệt với `CompletionStage`; stage pending không tự chặn callback kế tiếp.
- **`last` đánh dấu phần cuối message**, không đóng WebSocket; phải ghép fragment và giới hạn tổng dung lượng.
- `onPing` và `onPong` cũng có quy tắc lifetime cho ByteBuffer.
- Trong **hướng gửi**, `sendText/sendBinary` trả future riêng; caller không sửa/truy cập vùng dữ liệu gửi cho đến khi future hoàn tất theo hợp đồng API.

**Tài liệu chính thức, hiện hành:** [Oracle Java 11 — WebSocket.Listener](https://docs.oracle.com/en/java/javase/11/docs/api/java.net.http/java/net/http/WebSocket.Listener.html), [Oracle Java 11 — WebSocket (request, sendBinary, sendText)](https://docs.oracle.com/en/java/javase/11/docs/api/java.net.http/java/net/http/WebSocket.html), [Oracle Java 11 — ByteBuffer](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/nio/ByteBuffer.html), [Oracle Java 11 — CompletionStage](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/util/concurrent/CompletionStage.html), [Oracle Java 26 — WebSocket.Listener](https://docs.oracle.com/en/java/javase/26/docs/api/java.net.http/java/net/http/WebSocket.Listener.html).