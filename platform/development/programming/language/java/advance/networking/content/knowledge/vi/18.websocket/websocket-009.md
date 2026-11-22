# Quyền sử dụng CharSequence và ByteBuffer trước khi WebSocket gửi hoàn tất trong Java 17

Trong mô-đun **WebSocket** của Java Advance — networking, việc gửi một message qua **java.net.http.WebSocket** không phải là một thao tác đồng bộ hoàn thành ngay ở dòng gọi phương thức. Hai phương thức phổ biến **sendText(CharSequence data, boolean last)** và **sendBinary(ByteBuffer data, boolean last)** đều khởi tạo một thao tác gửi **bất đồng bộ** và trả về **CompletableFuture<WebSocket>**. Java WebSocket implementation có thể còn đang truy cập dữ liệu bạn cung cấp **sau khi sendText/sendBinary đã trả về**.

Vì vậy, câu hỏi quan trọng không chỉ là “gửi chuỗi hay byte như thế nào”, mà là **ai sở hữu quyền đọc/ghi payload trong khoảng thời gian chưa gửi xong**. Nếu một thread sửa **StringBuilder** khi WebSocket còn gửi, nội dung truyền đi có thể sai hoặc bị race. Nếu ứng dụng **flip/clear/put/get/đọc position** của **ByteBuffer** đang được sendBinary sử dụng, nó vi phạm hợp đồng của Java 17; dữ liệu được gửi, position và lỗi có thể không như bạn kỳ vọng.

Theo **Javadoc Java SE 17**:

- **sendText(data, last)**: **CharSequence không được sửa đổi** cho đến khi **CompletableFuture** mà phương thức trả về **đã hoàn tất**.
- **sendBinary(data, last)**: bytes được lấy từ vùng **position đến limit**. **Không được truy cập ByteBuffer** trước khi CompletableFuture ấy hoàn tất; khi future **hoàn tất bình thường**, buffer **không còn byte nào remaining**.
- **sendPing(ByteBuffer)** và **sendPong(ByteBuffer)** cũng có quy tắc không truy cập buffer đến khi future hoàn tất; payload điều khiển tối đa 125 byte.
- **Future hoàn tất bình thường** nghĩa WebSocket send operation đã thành công theo API, **không phải bằng chứng** ứng dụng ở máy nhận đã đọc, parse hoặc xử lý message.

Bài học giải thích chính xác contract của Java 17, cách phân biệt **immutable String** với **mutable StringBuilder/CharBuffer**, **độc lập dữ liệu** với **ByteBuffer view chia sẻ storage**, nguyên tắc **snapshot/ownership transfer**, cách chain sends và kiểm soát backpressure, failure/cancellation, cùng **hai chương trình chạy được** đã kiểm thử trên JDK với lựa chọn biên dịch **--release 17**. Một chương trình thật sự gửi dữ liệu qua WebSocket localhost; chương trình còn lại chứng minh vì sao **slice/duplicate/asReadOnlyBuffer không phải deep copy**.

## 1. Bản chất của một lần WebSocket send

Một WebSocket client Java 17 được tạo theo kiểu:

~~~java
WebSocket webSocket = HttpClient.newHttpClient()
        .newWebSocketBuilder()
        .buildAsync(uri, listener)
        .join();
~~~

Đây là **đoạn minh họa**, giả định uri là URI **ws:// hoặc wss://** hợp lệ và listener là một **WebSocket.Listener** được cấu hình. **buildAsync** là quá trình mở và handshake kết nối; **sendText/sendBinary** chỉ được thực hiện sau khi đã có WebSocket sẵn sàng.

Khi ứng dụng gọi:

~~~java
CompletableFuture<WebSocket> sent = webSocket.sendText("HELLO", true);
~~~

phương thức **trả về CompletableFuture ngay**, còn việc hoàn tất send xảy ra khi future hoàn tất. Một lần gọi thành công **không tương đương** có thể ngay lập tức tái sử dụng mọi dữ liệu truyền vào.

~~~text
APPLICATION THREAD                   WEBSOCKET SEND OPERATION
      |
      | tạo payload
      | sendText(data, true) --------> khởi tạo send bất đồng bộ
      |    |
      | nhận CompletableFuture        |
      |    |                           | có thể đọc data về sau
      |    |                           | xử lý framing / send
      |    |                           |
      |    +---- future chưa xong ---->| vẫn đang pending
      |    |                           |
      |    | không sửa dữ liệu         |
      |    | được đem gửi             |
      |    |                           |
      |    +---- future hoàn tất <-----+
      |          |
      |          +-- success: send operation thành công
      |          +-- failure: xem exception/cancellation
      |
      +-- có thể giải phóng/tái sử dụng
          dữ liệu theo quy tắc của từng API
~~~

**Một future đã tạo không phải lock tự động.** Java không tự khóa StringBuilder hoặc mảng byte của ứng dụng; chính caller phải bảo đảm quyền truy cập nhất quán. Không có yêu cầu chung rằng provider WebSocket phải **deep-copy** payload ngay tại thời điểm bạn gọi send.

### Điều cần phân biệt

| Sự kiện | Điều đã biết | Điều chưa được suy ra |
|---|---|---|
| **sendText/sendBinary trả CompletableFuture** | Operation đã được khởi tạo hoặc đã cho future báo lỗi | Dữ liệu đã được đọc hết, được gửi hết hoặc đến server |
| **future.isDone() == false** | Operation chưa hoàn tất theo future | Không được sửa CharSequence hoặc truy cập ByteBuffer đang gửi |
| **future hoàn tất bình thường** | Send operation thành công theo WebSocket API | Application bên nhận đã xử lý và commit |
| **future hoàn tất bất thường** | Send operation lỗi | ByteBuffer chắc chắn còn nguyên position hoặc message chưa hề tới peer |
| **sendClose hoàn tất** | Gửi Close theo contract | Tất cả application-level business acknowledgments đã nhận |

Một message thành công có thể bị mất ở tầng nghiệp vụ nếu peer crash sau khi nhận byte; nếu protocol cần bảo đảm xử lý, thêm **application ACK**, request ID, timeout và idempotency. **WebSocket send completion không phải delivery receipt từ application**.

## 2. Quy tắc riêng của sendText(CharSequence, boolean)

Chữ ký Java 17:

~~~java
CompletableFuture<WebSocket> sendText(CharSequence data, boolean last);
~~~

Tham số **data** là **CharSequence**, một **interface**, nên runtime có thể nhận:

- **String**: immutable; String literal hoặc String đã tạo là lựa chọn đơn giản để giữ nội dung không đổi.
- **StringBuilder**: mutable; **không gọi append/insert/delete/setCharAt/replace/setLength** trên object đang được gửi tới khi future hoàn tất.
- **StringBuffer**: mutable và một số operation được đồng bộ, nhưng điều đó **không cấp quyền thay đổi khi send đang pending**.
- **CharBuffer**: có thể là view lên char[] hoặc vùng dữ liệu được chia sẻ; không sửa nội dung hay storage nền của CharBuffer đang gửi.
- Các **CharSequence custom**: có thể đọc dữ liệu thay đổi theo thời gian; nếu không thể cam kết immutable, hãy tạo snapshot độc lập.

**Hợp đồng của sendText là “không sửa CharSequence tới khi future hoàn tất”**, không phải “chỉ cần không sửa trong dòng gọi sendText”. Một lời gọi có thể trả về trước khi client thực sự đọc hết ký tự.

### Mẫu nguy hiểm: sửa StringBuilder quá sớm

~~~java
StringBuilder builder = new StringBuilder("ORDER-001");
CompletableFuture<WebSocket> pending =
        webSocket.sendText(builder, true);

builder.replace(0, builder.length(), "ORDER-999");
// SAI: builder chính là CharSequence đang được send.
~~~

Đây là **anti-pattern**, chưa phải chương trình độc lập và **không được sử dụng để thử may rủi trong production**. Đôi khi chạy ở localhost vẫn thấy ORDER-001 vì provider đã đọc xong rất nhanh; khi nghẽn mạng hoặc thay thread scheduling có thể khác. **Không dựa vào thành công ngẫu nhiên để chứng minh an toàn**.

### Cách đúng A: dùng String bất biến

~~~java
StringBuilder draft = new StringBuilder("ORDER-001");
String stablePayload = draft.toString();

CompletableFuture<WebSocket> pending =
        webSocket.sendText(stablePayload, true);

// An toàn đối với stablePayload:
// draft giờ là một đối tượng khác, không phải CharSequence đã truyền.
draft.replace(0, draft.length(), "ORDER-999");

pending.join();
~~~

Ở đây **sendText nhận stablePayload (String)**, không nhận draft. String là immutable; draft có thể sửa mà không thay nội dung stablePayload. Khi dùng **StringBuilder.toString()**, việc tạo String snapshot phải hoàn thành **trước khi sửa draft**, và vẫn phải đồng bộ nếu nhiều threads đồng thời đang sửa draft lúc snapshot.

### Cách đúng B: giữ quyền sở hữu builder đến completion

~~~java
StringBuilder builder = new StringBuilder("ORDER-001");
CompletableFuture<WebSocket> pending =
        webSocket.sendText(builder, true);

pending.whenComplete((socket, error) -> {
    // Chỉ ở đây mới được xem builder đã hết thời gian bị send giữ.
    if (error != null) {
        reportFailure(error);
    }
    builder.setLength(0);
});
~~~

Đoạn trên **chỉ là minh họa**, reportFailure do ứng dụng định nghĩa; không phải file chạy độc lập. Trong thực tế, bảo đảm không có thread khác sửa builder trước khi whenComplete được kích hoạt và đừng clear/recycle object nếu callback khác còn dùng nó. Nếu future lỗi, phải xử lý khả năng message chưa hoặc đã gửi một phần; muốn retry nên dựng lại payload từ một **nguồn dữ liệu bất biến**, không suy từ trạng thái bên ngoài.

**Không dùng biến StringBuilder chung** cho mọi request trên cùng connection. Một builder chung được append/clear theo event-loop có thể vô tình thay nội dung của một send còn pending. Dùng **per-message immutable snapshot** hoặc **per-message ownership token**.

## 3. CharBuffer, char[] và read-only view không bảo đảm bất biến nội dung

**CharSequence** không đồng nghĩa String. Ví dụ:

~~~java
char[] raw = {'O', 'K'};
CharBuffer view = CharBuffer.wrap(raw).asReadOnlyBuffer();

raw[0] = 'N';
// view là read-only đối với writer dùng view,
// nhưng vẫn thấy giá trị 'N' do mảng nền bị sửa.
~~~

**CharBuffer.asReadOnlyBuffer()** bảo vệ chống gọi **put(...) trực tiếp trên view**, không bảo vệ dữ liệu khỏi một alias bên ngoài sửa mảng nền. **read-only view không phải immutable snapshot**.

Nguyên tắc:

1. Nếu nhận đầu vào là CharSequence mà **không biết nguồn có mutable hay không**, tạo **String snapshot** trước khi send, với giới hạn kích thước và encoding hợp lệ.
2. Nếu CharSequence bọc char[] hoặc một vùng memory dùng chung, **không để thread khác thay backing array** khi send đang pending.
3. Nếu dùng CharBuffer.asReadOnlyBuffer(), vẫn phải tuân thủ ownership của backing storage, bởi source buffer hoặc array bên ngoài có thể sửa dữ liệu.
4. Nếu dữ liệu được cập nhật liên tục và bạn cần gửi “ảnh chụp” nhất quán, tạo snapshot trong một critical section hoặc bằng cấu trúc immutable phù hợp.
5. **StringBuilder không thread-safe**, không được đọc snapshot cùng lúc với writer không đồng bộ rồi kỳ vọng snapshot tự nhất quán.

### UTF-16 và phân đoạn text

Java **CharSequence** chứa **UTF-16 code units**; WebSocket text trên wire dùng UTF-8 hợp lệ. Javadoc Java 17 nói nếu input là **malformed UTF-16 sequence**, sendText operation **thất bại bằng IOException trong future**. Ví dụ ghép fragment hoặc cắt nội dung phải tránh tạo surrogate pair bị hỏng.

**Không cắt text theo số ký tự Java tùy tiện** rồi giả định ranh giới Unicode luôn hợp lệ: một emoji có thể gồm hai UTF-16 code units, và các cụm ký tự hiển thị có thể nhiều code points. Chọn ranh giới fragment theo contract WebSocket/UTF-16 và test với tiếng Việt, emoji, combining marks, dữ liệu quốc tế.

## 4. Quy tắc đặc biệt quan trọng của sendBinary(ByteBuffer, boolean)

Chữ ký:

~~~java
CompletableFuture<WebSocket> sendBinary(ByteBuffer data, boolean last);
~~~

Javadoc Java 17 nêu rõ:

1. Bytes gửi đến từ **vùng hiện tại của data: [position, limit)**.
2. **Không được truy cập data ByteBuffer** cho tới khi **CompletableFuture do sendBinary trả về hoàn tất**. Đây là quy tắc mạnh hơn chỉ “không thay đổi byte”.
3. Khi future **hoàn tất bình thường**, **data.remaining() == 0**.
4. Nếu future **thất bại**, không nên giả định buffer vẫn còn nguyên vị trí, đã được tiêu thụ bao nhiêu hoặc có thể tiếp tục dùng để retry trực tiếp; xử lý lỗi và dựng payload mới nếu nghiệp vụ cần.

**Vì sao “không truy cập” quan trọng?** ByteBuffer chứa **content + position + limit + mark**. Implementation có thể chuyển các byte bằng cách cập nhật position trong quá trình send. Nếu caller đồng thời gọi **get/put/flip/clear/compact/rewind/position/limit/remaining**, bạn có thể gây race trên state của buffer hoặc thay đổi vùng dữ liệu cần gửi.

### Quy tắc position/limit

~~~text
ByteBuffer capacity = 8
          position=2            limit=6
               |                   |
index:  0  1  [2  3  4  5]  6  7
sendBinary sẽ gửi các byte ở [position, limit)
= indexes 2, 3, 4, 5

sau successful completion:
    remaining() == 0
    position == limit
~~~

Đây là mô hình logic, không phải lời hứa rằng những byte ngoài phạm vi gửi sẽ bị xóa hoặc buffer tự động clear. **sendBinary không phải thao tác “gửi toàn bộ capacity”**; vùng gửi phụ thuộc position/limit tại thời điểm gọi và hợp đồng bất động trong suốt pending operation.

### Mẫu nguy hiểm: flip/clear quá sớm

~~~java
ByteBuffer buffer = ByteBuffer.wrap(new byte[] {1, 2, 3, 4});
CompletableFuture<WebSocket> pending =
        webSocket.sendBinary(buffer, true);

buffer.clear(); // SAI: đang pending, không được truy cập buffer.
buffer.put((byte) 99); // SAI: ghi đè nội dung trước completion.
~~~

Cũng sai nếu chỉ gọi **buffer.remaining()** để log trong khoảng pending, vì Java 17 nói **buffer must not be accessed**. Để theo dõi tiến độ, lưu **kích thước dự kiến vào biến số riêng trước send**, hoặc dùng metric ở tầng operation/future sau completion.

### Cách đúng A: đợi send thành công rồi tái sử dụng

~~~java
ByteBuffer buffer = ByteBuffer.wrap(new byte[] {1, 2, 3, 4});
CompletableFuture<WebSocket> pending =
        webSocket.sendBinary(buffer, true);

pending.join();
int remaining = buffer.remaining(); // 0 sau normal completion.
buffer.clear();                     // Bây giờ mới được reuse.
~~~

Đây là đoạn minh họa, cần handle CompletionException khi lỗi, và phải đảm bảo không có alias khác sửa storage trong lúc pending. **Không giả định buffer.clear() xóa các byte trong vùng lưu trữ**: clear chỉ đặt lại position/limit, dữ liệu cũ vẫn có thể nằm trong mảng/direct memory cho tới khi ghi đè/giải phóng.

### Cách đúng B: sao chép bytes sang buffer do send sở hữu

~~~java
byte[] mutableSource = {1, 2, 3, 4};
byte[] ownedBytes = mutableSource.clone();
ByteBuffer ownedBuffer = ByteBuffer.wrap(ownedBytes);

CompletableFuture<WebSocket> pending =
        webSocket.sendBinary(ownedBuffer, true);

// Hợp lệ: sửa mảng gốc, vì WebSocket đang dùng mảng clone.
mutableSource[0] = 99;

// KHÔNG đọc hoặc sửa ownedBuffer hay ownedBytes trước completion.
pending.join();
assert ownedBuffer.remaining() == 0;
~~~

Trong mẫu này **mutableSource** và **ownedBytes** là **hai mảng độc lập**. Chỉ cần đảm bảo application không đụng tới ownedBytes trong suốt pending operation. **ByteBuffer.wrap(ownedBytes)** tự nó **không copy ownedBytes lần nữa**; đó là một view lên mảng clone. Mẫu này tạo snapshot độc lập từ mảng gốc.

### Cách đúng C: copy phần remaining từ buffer nguồn

~~~java
ByteBuffer source = obtainSourceBuffer();
ByteBuffer snapshot = ByteBuffer.allocate(source.remaining());
snapshot.put(source.duplicate());
snapshot.flip();

CompletableFuture<WebSocket> pending =
        webSocket.sendBinary(snapshot, true);

// Caller có thể thay source, nhưng không được sửa snapshot đang pending.
pending.join();
~~~

Đây là đoạn minh họa, với obtainSourceBuffer() do ứng dụng định nghĩa. **source.duplicate() dùng trước send** để đọc vùng remaining mà không thay source.position; **snapshot.allocate + put** tạo vùng chứa bytes **độc lập**. **source** phải ổn định **trong thời gian copy**: nếu một thread khác đang ghi source, bản copy cũng có thể không nhất quán. Muốn snapshot thread-safe, đồng bộ producer/consumer hoặc dùng immutable data/queue ownership.

**Không cần clone mọi buffer trong mọi hệ thống.** Nếu producer sẵn sàng chuyển **quyền sở hữu độc quyền** của buffer cho WebSocket cho tới completion, có thể tránh copy để giảm CPU và allocations. Sự lựa chọn là **copy vs exclusive ownership**, không phải mặc định “chỉ cần duplicate()”.

## 5. ByteBuffer.wrap, duplicate, slice, asReadOnlyBuffer: aliasing khác deep copy

Đây là một trong những hiểu lầm phổ biến nhất:

| Thao tác | Có vùng byte độc lập? | Position/limit độc lập? | Nếu backing storage bị sửa? |
|---|---|---|---|
| **ByteBuffer.wrap(byte[])** | Không: dùng cùng array | Buffer tự giữ state của nó | Buffer thấy mảng thay đổi |
| **original.duplicate()** | Không: chia sẻ content | Có | Cả hai view thấy dữ liệu đổi |
| **original.slice()** | Không: dùng subsequence cùng content | Có | Cả hai view thấy dữ liệu đổi |
| **original.asReadOnlyBuffer()** | Không: chia sẻ content | Có | Read-only view vẫn thấy dữ liệu đổi từ alias |
| **ByteBuffer.allocate(n) + put(source.duplicate())** | Có, vùng byte mới | Có | Snapshot không đổi nếu source thay |
| **Arrays.copyOf(byteArray, length)** | Có, mảng mới | Không áp dụng | Mảng mới không chịu tác động từ mảng gốc |
| **byteArray.clone()** | Có, mảng mới | Không áp dụng | Mảng mới độc lập với mảng gốc |

**Read-only ByteBuffer không phải immutable underlying bytes.** Nó ngăn **ghi qua chính view ấy**, nhưng không chặn người giữ original buffer hoặc byte[] backing sửa dữ liệu. Vì vậy, dùng **asReadOnlyBuffer()** cho sendBinary không tự giải quyết race, và vẫn phải tuân theo Javadoc “buffer must not be accessed until after future completed”.

**duplicate()/slice()** hữu ích để thay đổi **position/limit độc lập** trong một thread hoặc một giai đoạn có ownership rõ, nhưng nội dung bytes **vẫn chia sẻ**. Nếu gửi view A và sửa original B trước khi completion, vẫn có thể làm payload bị thay đổi. **Không dùng duplicate để coi như đã copy bytes.**

### Với direct ByteBuffer

**ByteBuffer.allocateDirect(...)** cấp vùng nhớ direct/off-heap; **asReadOnlyBuffer/duplicate/slice** của direct buffer tiếp tục chia sẻ vùng nhớ trực tiếp. Dù không có byte[] backing accessible, quyền sở hữu và quy tắc không truy cập trong lúc send **vẫn áp dụng**. Đừng giải phóng/mutate direct memory qua cơ chế native/JNI/foreign memory khi provider còn gửi.

## 6. Java 17 runnable: chứng minh aliasing và snapshot bằng ByteBuffer, CharBuffer

Chương trình đầu tiên không cần server/network. Nó tạo array-backed ByteBuffer, các view dùng chung storage, một deep copy độc lập và một CharBuffer read-only view. Sau khi sửa mảng gốc, ta quan sát **view thay đổi còn snapshot không**.

Tạo tệp **BufferAliasingDemo.java**:

~~~java
import java.nio.ByteBuffer;
import java.nio.CharBuffer;

public class BufferAliasingDemo {
    public static void main(String[] args) {
        byte[] array = {10, 20, 30, 40};
        ByteBuffer original = ByteBuffer.wrap(array);
        original.position(1);
        original.limit(3);

        ByteBuffer slice = original.slice();
        ByteBuffer readOnly = original.asReadOnlyBuffer();
        ByteBuffer copy = ByteBuffer.allocate(original.remaining());
        copy.put(original.duplicate());
        copy.flip();

        array[1] = 99;

        System.out.println("Slice first byte: " + slice.get(0));
        System.out.println("Read-only view first byte: " + readOnly.get(1));
        System.out.println("Independent copy first byte: " + copy.get(0));
        System.out.println("Original position: " + original.position());

        char[] letters = {'O', 'K'};
        CharBuffer charView = CharBuffer.wrap(letters).asReadOnlyBuffer();
        String snapshot = charView.toString();
        letters[0] = 'N';
        System.out.println("Read-only CharBuffer now: " + charView);
        System.out.println("String snapshot: " + snapshot);
    }
}
~~~

Biên dịch/chạy bằng JDK 17+:

~~~bash
javac --release 17 BufferAliasingDemo.java
java BufferAliasingDemo
~~~

Kết quả chính xác:

~~~text
Slice first byte: 99
Read-only view first byte: 99
Independent copy first byte: 20
Original position: 1
Read-only CharBuffer now: NK
String snapshot: OK
~~~

**Đã biên dịch với javac --release 17 và chạy thành công**, đầu ra khớp sáu dòng trên.

### Phân tích

- original đặt **position=1, limit=3**, nên **original.remaining()=2** và slice chứa vùng logical indexes tương ứng hai byte 20, 30.
- **slice.get(0)** trả 99 sau khi **array[1]=99**, chứng minh view chia sẻ backing storage.
- **readOnly.get(1)** cũng trả 99; read-only chỉ cấm put qua view, không làm vùng nhớ nền bất biến.
- **copy.put(original.duplicate())** tạo buffer mới với byte 20/30 và giữ original.position() bằng 1. Khi array gốc đổi, copy vẫn bắt đầu bằng 20.
- **CharBuffer.wrap(letters).asReadOnlyBuffer()** vẫn quan sát thay đổi ở letters[0], nên in NK.
- **String snapshot = charView.toString()** lưu nội dung OK độc lập với mảng letters; sửa letters sau đó không thay nội dung snapshot.

**Giới hạn của ví dụ:** tất cả thao tác biến đổi xảy ra tuần tự và **trước một send**; không minh họa “sửa khi WebSocket send pending” vì đó là điều Javadoc cấm và có thể cho kết quả không xác định. Mục tiêu là chứng minh storage aliasing để tránh đưa alias mutable vào in-flight send.

## 7. WebSocket thật trên loopback: gửi immutable String và owned ByteBuffer

Java SE 17 có **WebSocket client API** trong **java.net.http**, nhưng không cung cấp một **public WebSocket server API đối xứng** cùng package. Để bài thực hành tự chạy và không phụ thuộc server ngoài, chương trình dưới đây tạo một **ServerSocket loopback** giả lập **một phần rất nhỏ giao thức WebSocket RFC 6455**:

1. Nhận HTTP Upgrade request, lấy Sec-WebSocket-Key và tính Sec-WebSocket-Accept theo RFC 6455.
2. Trả handshake **101 Switching Protocols**.
3. Nhận các frame nhỏ đã **mask** từ Java client: một text frame, một binary frame và một close frame.
4. Giải mask, ghi nhận payload; trả close frame 1000 rồi thoát.

**Đây là server mô phỏng tối giản dành riêng cho test**, không phải WebSocket server production: nó chỉ hỗ trợ frame ngắn <=125 byte với FIN=true, không xử lý fragmented frames lớn, extensions, phần lớn control opcodes, kiểm tra Origin/authentication, TLS, rate limit và nhiều clients. Với server thật, dùng framework WebSocket đã được kiểm thử.

Client dùng **HttpClient.newWebSocketBuilder().buildAsync(...)**, gửi **String snapshot** của một StringBuilder và **ByteBuffer chứa mảng clone**. Sau khi khởi tạo send:

- Có thể sửa **StringBuilder draft**, vì WebSocket đang dùng **String stableText** tách biệt.
- Có thể sửa **mảng original**, vì WebSocket đang dùng **owned ByteBuffer** bọc **original.clone()**.
- **Không** đọc/sửa **owned ByteBuffer** cho tới khi binarySend hoàn tất.
- Khi binarySend hoàn tất bình thường, **owned.remaining() == 0**.

Tệp **WebSocketPayloadOwnershipDemo.java**:

~~~java
import java.io.ByteArrayOutputStream;
import java.io.EOFException;
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
import java.util.Base64;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

public class WebSocketPayloadOwnershipDemo {
    private record Received(String text, String binaryHex) {}

    private static String httpLine(InputStream in) throws IOException {
        ByteArrayOutputStream out = new ByteArrayOutputStream();
        while (out.size() <= 4096) {
            int b = in.read();
            if (b == -1) throw new EOFException("EOF in handshake");
            if (b == '\n') {
                byte[] bytes = out.toByteArray();
                int len = bytes.length;
                if (len > 0 && bytes[len - 1] == '\r') len--;
                return new String(bytes, 0, len, StandardCharsets.US_ASCII);
            }
            out.write(b);
        }
        throw new IOException("Oversized handshake line");
    }

    private static String acceptKey(String key) throws Exception {
        String merged = key + "258EAFA5-E914-47DA-95CA-C5AB0DC85B11";
        byte[] sha1 = MessageDigest.getInstance("SHA-1")
                .digest(merged.getBytes(StandardCharsets.US_ASCII));
        return Base64.getEncoder().encodeToString(sha1);
    }

    private static String hex(byte[] bytes) {
        StringBuilder out = new StringBuilder();
        for (byte b : bytes) {
            out.append(String.format("%02x", b & 0xff));
        }
        return out.toString();
    }

    private static Received serve(ServerSocket listener) throws Exception {
        try (Socket peer = listener.accept()) {
            peer.setSoTimeout(5000);
            InputStream in = peer.getInputStream();
            OutputStream out = peer.getOutputStream();
            String requestLine = httpLine(in);
            if (!requestLine.startsWith("GET /demo ")) {
                throw new IOException("Unexpected handshake path");
            }

            String key = null;
            for (String line; !(line = httpLine(in)).isEmpty();) {
                if (line.regionMatches(true, 0, "Sec-WebSocket-Key:", 0, 18)) {
                    key = line.substring(18).trim();
                }
            }
            if (key == null) throw new IOException("No websocket key");

            String response = "HTTP/1.1 101 Switching Protocols\r\n"
                    + "Upgrade: websocket\r\nConnection: Upgrade\r\n"
                    + "Sec-WebSocket-Accept: " + acceptKey(key) + "\r\n\r\n";
            out.write(response.getBytes(StandardCharsets.US_ASCII));
            out.flush();

            String text = null, binary = null;
            boolean closed = false;
            while (!closed) {
                int first = in.read(), second = in.read();
                if (first < 0 || second < 0) {
                    throw new EOFException("EOF before websocket close");
                }
                boolean fin = (first & 0x80) != 0;
                int opcode = first & 0x0f;
                int length = second & 0x7f;
                if (!fin || length >= 126 || (second & 0x80) == 0) {
                    throw new IOException("Demo expects short masked frames");
                }
                byte[] mask = in.readNBytes(4);
                byte[] data = in.readNBytes(length);
                if (mask.length != 4 || data.length != length) {
                    throw new EOFException("Truncated frame");
                }
                for (int i = 0; i < data.length; i++) {
                    data[i] ^= mask[i % 4];
                }
                switch (opcode) {
                    case 1 -> text = new String(data, StandardCharsets.UTF_8);
                    case 2 -> binary = hex(data);
                    case 8 -> {
                        out.write(new byte[] {
                                (byte) 0x88, 2, 0x03, (byte) 0xE8});
                        out.flush();
                        closed = true;
                    }
                    default -> throw new IOException("Unexpected opcode: " + opcode);
                }
            }
            if (text == null || binary == null) {
                throw new IOException("Expected text and binary frames");
            }
            return new Received(text, binary);
        }
    }

    public static void main(String[] args) throws Exception {
        ExecutorService worker = Executors.newSingleThreadExecutor();
        try (ServerSocket listener = new ServerSocket(
                0, 8, InetAddress.getByName("127.0.0.1"))) {
            Future<Received> serverResult =
                    worker.submit(() -> serve(listener));

            URI uri = URI.create(
                    "ws://127.0.0.1:" + listener.getLocalPort() + "/demo");
            WebSocket webSocket = HttpClient.newHttpClient()
                    .newWebSocketBuilder()
                    .connectTimeout(java.time.Duration.ofSeconds(5))
                    .buildAsync(uri, new WebSocket.Listener() {})
                    .get(5, TimeUnit.SECONDS);

            StringBuilder draft = new StringBuilder("HELLO");
            String stableText = draft.toString();
            CompletableFuture<WebSocket> textSend =
                    webSocket.sendText(stableText, true);
            draft.replace(0, draft.length(), "CHANGED");
            textSend.get(5, TimeUnit.SECONDS);

            byte[] original = {1, 2, 3, 4};
            ByteBuffer owned = ByteBuffer.wrap(original.clone());
            CompletableFuture<WebSocket> binarySend =
                    webSocket.sendBinary(owned, true);
            original[0] = 99;
            binarySend.get(5, TimeUnit.SECONDS);
            int remainingAfterSend = owned.remaining();

            webSocket.sendClose(WebSocket.NORMAL_CLOSURE, "done")
                    .get(5, TimeUnit.SECONDS);

            Received result = serverResult.get(5, TimeUnit.SECONDS);
            System.out.println("Server text: " + result.text());
            System.out.println("Server binary: " + result.binaryHex());
            System.out.println("Builder after change: " + draft);
            System.out.println("Original byte[0]: " + original[0]);
            System.out.println("Buffer remaining after send: "
                    + remainingAfterSend);
        } finally {
            worker.shutdownNow();
        }
    }
}
~~~

Biên dịch/chạy bằng JDK 17+:

~~~bash
javac --release 17 WebSocketPayloadOwnershipDemo.java
java WebSocketPayloadOwnershipDemo
~~~

Stdout khi thành công:

~~~text
Server text: HELLO
Server binary: 01020304
Builder after change: CHANGED
Original byte[0]: 99
Buffer remaining after send: 0
~~~

**Đã biên dịch javac --release 17 và chạy thành công**, đầu ra khớp năm dòng trên trong môi trường kiểm thử loopback.

### Mỗi dòng đầu ra chứng minh điều gì?

- **Server text: HELLO** chứng minh WebSocket đã nhận **String snapshot**, không nhận **StringBuilder draft** đang được thay đổi. Chúng là hai object khác nhau.
- **Server binary: 01020304** chứng minh WebSocket đã nhận **mảng clone** độc lập, không phải mảng original mà caller thay byte đầu thành 99.
- **Builder after change: CHANGED** không có nghĩa một CharSequence mutable bất kỳ được phép sửa trước completion; builder ở demo **không phải object truyền vào sendText**.
- **Original byte[0]: 99** cho thấy original có thể được sửa khi send dùng clone, không có alias tới owned bytes.
- **Buffer remaining after send: 0** khớp contract **sendBinary** khi future thành công. Việc đọc remaining chỉ diễn ra **sau binarySend.get(...)** hoàn tất.

### Những gì chương trình không khẳng định

- **Không khẳng định** real WebSocket server có thể triển khai bằng parser vài chục dòng. Server trong demo thiếu nhiều kiểm tra RFC 6455 và chỉ phục vụ bài học payload ownership.
- **Không đo lường** server xử lý nghiệp vụ hay lưu dữ liệu; nó chỉ decode frames và in text/bytes đã nhận.
- **Không kiểm thử sửa StringBuilder/ByteBuffer đang pending**, vì đó là thao tác vi phạm Java 17 API contract. Chúng ta kiểm thử **snapshot/clone hợp lệ** thay vì dựa vào một race.
- **Không hứa** mọi mạng sẽ chạy đúng timing. Code dùng loopback, socket timeout và Future.get timeout; nếu firewall cấm loopback hoặc hệ thống rất chậm, chương trình có thể báo lỗi.
- **Không kiểm thử fragment lớn, ping/pong, TLS wss**, nên production cần WebSocket framework có RFC-compliant server, max frame/message length, auth/TLS và backpressure.

## 8. Một message nhiều fragments: last=false, last=true và thứ tự

Tham số **last** trong **sendText/sendBinary** đánh dấu **lần gửi này có hoàn tất message hay không**.

~~~java
webSocket.sendText("Phần một ", false)
        .thenCompose(ws -> ws.sendText("phần hai", true))
        .join();
~~~

Đây là snippet minh họa giả định WebSocket đã connected. Hai lần sendText thuộc **một text message**. Khi sendText("Phần một ", false) hoàn tất, message **chưa hoàn chỉnh**; lần kế tiếp sendText(..., true) đóng message.

Cần phân biệt:

- **Một send operation đã hoàn tất** và **một WebSocket message đã hoàn chỉnh** là hai ý khác nhau.
- **last=false** cho phép tạo message nhiều fragments; **last=true** báo fragment cuối của message.
- Java 17 WebSocket có thể làm sendText hoặc sendBinary future thất bại với **IllegalStateException** khi một **text/binary send operation khác đang pending**.
- Khi một **binary message đang dở dang** (binary fragment trước có last=false), không được chuyển sang **text message** cho tới khi hoàn thành binary; ngược lại, text dở dang không được chuyển sang binary.
- Chỉ hoàn tất fragment trước rồi mới gửi fragment sau, ví dụ dùng **thenCompose**, để tránh concurrency lỗi thứ tự.
- Text fragments phải có dữ liệu UTF-16 hợp lệ theo contract; không cắt surrogate pair thành malformed CharSequence rồi coi giao thức sẽ tự sửa.

### Anti-pattern: gửi song song trên cùng WebSocket

~~~java
CompletableFuture<WebSocket> first =
        webSocket.sendText("first", true);
CompletableFuture<WebSocket> second =
        webSocket.sendBinary(ByteBuffer.wrap(new byte[] {1}), true);
~~~

Đây là **mẫu dễ lỗi**: **second** có thể gặp **IllegalStateException** nếu first text/binary send còn pending. Dù hai futures hoàn tất trong một máy nhanh, không thể dựa vào scheduling để làm đúng thứ tự. Nếu muốn gửi nhiều messages, **serialize gửi** qua chain/queue.

### Mẫu tuần tự theo future

~~~java
CompletableFuture<WebSocket> done = webSocket
        .sendText("first", true)
        .thenCompose(ws ->
                ws.sendBinary(ByteBuffer.wrap(new byte[] {1}), true));

done.join();
~~~

Ở đây lời gọi sendBinary chỉ được tạo khi sendText hoàn tất thành công. **ByteBuffer được tạo mới bên trong lambda**, không bị thread bên ngoài truy cập, nên phù hợp ownership. Nếu first thất bại, thenCompose bị bỏ qua, future tổng báo lỗi; không cố gửi message tiếp trên một connection chưa rõ trạng thái.

## 9. Thiết kế ownership transfer hoặc snapshot trong outbound queue

Trong ứng dụng WebSocket thật, message có thể được tạo bởi hàng trăm request producers rồi xếp vào một queue. **Producer không nên giữ khả năng sửa dữ liệu đã được enqueue nếu WebSocket sẽ gửi nó về sau**.

Một mô hình rõ ràng:

~~~text
Producer builds mutable payload
      |
      v
OPTION A: snapshot vào String/byte[]
   hoặc
OPTION B: transfer độc quyền object/buffer, producer không còn đụng
      |
      v
Bounded outgoing queue
      |
      v
Một sender owner dequeue
      |
      v
sendText/sendBinary -> CompletableFuture
      |
      +-- future success --> mark sent, release/recycle buffer
      |
      +-- future failed  --> mark failed, cleanup/close/retry policy
      |
      v
Dequeue message kế tiếp
~~~

### Không để queue giữ reference mutable của producer

Nếu queue chứa **StringBuilder** mà producer liên tục clear/reuse nó sau enqueue, message có thể đã đổi ngay cả **trước khi sendText bắt đầu**. Nguyên tắc ownership nên áp dụng **từ lúc đưa vào queue**, không chỉ từ lúc gọi send.

Nếu queue giữ **ByteBuffer.duplicate()**, producer sửa array/original buffer vẫn làm data trong view thay đổi. **duplicate không giải quyết chia sẻ dữ liệu**.

### Mẫu queue Java (minh họa, không phải file độc lập)

~~~java
final class SequentialSender {
    private final WebSocket socket;
    private CompletableFuture<WebSocket> tail;

    SequentialSender(WebSocket socket) {
        this.socket = socket;
        this.tail = CompletableFuture.completedFuture(socket);
    }

    synchronized CompletableFuture<WebSocket> sendTextSnapshot(
            CharSequence source) {
        String owned = source.toString(); // Copy khi enqueue.
        tail = tail.thenCompose(ws -> ws.sendText(owned, true));
        return tail;
    }

    synchronized CompletableFuture<WebSocket> sendBinarySnapshot(
            ByteBuffer source) {
        ByteBuffer owned = ByteBuffer.allocate(source.remaining());
        owned.put(source.duplicate()); // Copy trước khi enqueue.
        owned.flip();
        tail = tail.thenCompose(ws -> ws.sendBinary(owned, true));
        return tail;
    }
}
~~~

Đoạn trên **chỉ minh họa mẫu serialization**, giả định đã import WebSocket, CompletableFuture và ByteBuffer; trong sản phẩm thật cần **constructor validation, bounded queue, close/error handling, per-message identity, deadlines**. Chú ý **source** phải ổn định trong lúc snapshot: synchronized ở phương thức không đủ nếu producer thread không dùng cùng lock khi sửa source.

Vì **tail** sẽ hoàn tất bất thường khi một send lỗi, **các thenCompose theo sau không tự gửi tiếp**. Đó là lựa chọn fail-stop phù hợp khi connection lỗi; application phải **báo lỗi cho các messages còn queue, dọn data và quyết định reconnect/retry**. Nếu muốn cơ chế phục hồi, phải tạo state machine explicit, không đơn giản bỏ lỗi bằng exceptionally rồi tiếp tục như thể mọi thứ vẫn đúng.

### Backpressure: không tạo vô hạn futures và buffer copies

Một sequential sender vẫn có thể OOM nếu 100.000 producers liên tục gửi payload 1 MiB vào queue. Cần:

- **maxMessages**, **maxQueuedBytes** và **maxInFlightBytes**.
- Cơ chế reject/await/backpressure khi queue đầy.
- Deadline/TTL cho message chờ quá lâu.
- Cancellation policy cho message chưa dequeue và message đã bắt đầu send.
- Observability: queue depth, active send duration, success/failure, bytes sent, retries.
- Retry chỉ với **payload snapshot ổn định** và với yêu cầu có **idempotency key**, nếu application protocol cần tránh lặp side effect.

**Một WebSocket thường có một send text/binary đang pending** theo Java 17 contract. Nếu muốn throughput tốt, tối ưu scheduling/payload size và backpressure, **không** gọi sendText/sendBinary song song rồi hy vọng provider serialize cho bạn.

## 10. Completion, cancellation, timeout và failure

**CompletableFuture<WebSocket>** có thể hoàn tất:

| Trạng thái | Hành vi an toàn |
|---|---|
| **Success** | Dữ liệu send operation thành công theo API; được phép tái sử dụng/giải phóng payload; binary buffer remaining == 0 |
| **Exceptional completion** | Lấy root cause, báo application, cleanup; không khẳng định binary position vẫn ban đầu |
| **Caller gọi future.cancel(...)** | Không giả định các bytes chắc chắn chưa được truyền; bảo toàn ownership tới khi xác nhận lifecycle theo implementation/policy |
| **Timeout ở future.get(timeout)** | Chỉ giới hạn thời gian đợi của thread, không chứng minh send đã dừng |
| **WebSocket.abort()** | Đóng WebSocket input/output đột ngột; ảnh hưởng các sends đang pending, cần xử lý futures và resources |
| **WebSocket.sendClose(...)** | Bắt đầu đóng output có trật tự; không thay cho ACK nghiệp vụ |

### Failure không tự khôi phục payload

Nếu **sendBinary** thất bại, tránh viết:

~~~java
ByteBuffer buffer = originalBuffer;
webSocket.sendBinary(buffer, true).join();
// Nếu lỗi: webSocket.sendBinary(buffer, true) lại với buffer cũ.
~~~

Đây là **anti-pattern**, đặc biệt khi code không giữ source bytes ở ngoài. Buffer có thể đã được tiêu thụ một phần hoặc connection bị đóng. Đối với retry, tạo connection mới khi cần, **dựng một ByteBuffer mới từ snapshot immutable** và xem nghiệp vụ có thể gửi lại hay không. Một send timeout không chứng minh peer chưa nhận message.

### Timeout phía caller không phải send cancellation chắc chắn

~~~java
CompletableFuture<WebSocket> pending =
        webSocket.sendBinary(ownedBuffer, true);

try {
    pending.get(2, TimeUnit.SECONDS);
} catch (TimeoutException waitExpired) {
    // KHÔNG dùng ownedBuffer.clear() ở đây:
    // timeout chỉ là caller ngừng đợi, send có thể còn pending.
    webSocket.abort();
    // Áp policy cleanup khi future/lifecycle đã được xác nhận.
}
~~~

Đây là **đoạn minh họa** với các import và ownedBuffer đã được khởi tạo. Trong một ứng dụng thật, phải tổ chức vòng đời bất đồng bộ, lưu lại future và xử lý exceptional completion/cancellation; không dùng một **TimeoutException từ get** như tín hiệu quyền tái sử dụng buffer. **abort()** là đóng đột ngột, không phải lời hứa bên nhận chưa xử lý bytes.

### Có được đọc ByteBuffer khi future hoàn tất lỗi không?

Javadoc quy định “buffer must not be accessed until after [the returned future has completed]”. Sau completion về mặt thời điểm có thể hết giai đoạn pending, nhưng **không có bảo đảm rằng byte position phản ánh số bytes được gửi thành công nếu future lỗi**. Với hệ thống đòi tính đúng, **loại bỏ buffer đó và dựng lại từ nguồn canonical**. Khi future hoàn tất **bình thường**, remaining == 0 mới là bảo đảm rõ.

### Mẫu xử lý lỗi qua whenComplete

~~~java
CompletableFuture<WebSocket> pending =
        webSocket.sendText(immutableText, true);

pending.whenComplete((socket, error) -> {
    if (error == null) {
        notifySendSucceeded();
    } else {
        notifySendFailed(error);
    }
});
~~~

Đây là đoạn minh họa với immutableText và các callback tự định nghĩa. Callback không nên block thread networking bằng DB/CPU nặng. Nếu cần metrics hoặc processing lâu, chuyển sang bounded executor. **Một callback thông báo send thành công chưa phải ACK phía ứng dụng nhận**.

## 11. sendPing/sendPong cũng có quyền sở hữu ByteBuffer

Hai API điều khiển WebSocket:

~~~java
CompletableFuture<WebSocket> ping = webSocket.sendPing(pingData);
CompletableFuture<WebSocket> pong = webSocket.sendPong(pongData);
~~~

**pingData/pongData là ByteBuffer, không được truy cập tới khi future tương ứng hoàn tất.** Giới hạn payload protocol là **125 byte**; nếu quá, sendPing/sendPong có thể trả future lỗi hoặc ném **IllegalArgumentException** theo hợp đồng API. **Ping/Pong cũng có pending-state policy riêng**, không được vô hạn gọi control sends khi một ping/pong send đang pending.

Javadoc Java 17 cho biết WebSocket implementation tự trả **Pong** khi nhận Ping, nên phần lớn ứng dụng không cần tự gửi Pong trong onPing. Nếu chương trình dùng Ping để kiểm tra liveness, đừng coi **sendPing future completed** là chứng minh peer đã đáp Pong; cần cơ chế quan sát **onPong** và deadline.

Cũng không được đưa một ByteBuffer đang dùng ở **sendBinary** sang **sendPing** trước khi binary future hoàn tất; dù hai method khác tên, **ownership của cùng data** không tự được tách.

## 12. Nhận dữ liệu ở Listener có hợp đồng ownership chiều ngược lại

Đề bài tập trung **trước khi gửi hoàn tất**, nhưng khi lập trình WebSocket cần phân biệt **buffer thuộc bên gửi** với **buffer do provider cấp cho bên nhận**.

Khi **sendBinary(data, last)**, **application cấp buffer cho provider** và **không truy cập nó cho tới khi send future hoàn tất**.

Khi WebSocket.Listener gọi **onBinary(WebSocket, ByteBuffer data, boolean last)**, chiều sở hữu đảo lại: **provider cấp buffer cho listener**. Theo Javadoc Java 17, **CompletionStage listener trả về** báo khi WebSocket có thể **reclaim buffer**. **Listener không được truy cập ByteBuffer sau khi stage đó hoàn tất**. Nếu cần xử lý sau khi callback return/completion, hãy **copy dữ liệu ngay khi còn quyền** hoặc quản lý stage chưa complete cho tới khi xử lý xong.

Tương tự với **onText(WebSocket, CharSequence data, boolean last)**, CharSequence có thể được reclaim khi CompletionStage tương ứng hoàn tất. Không lưu một reference đến CharSequence do provider cấp rồi đọc từ task khác sau khi đã return một completed stage, trừ khi đã snapshot ra String.

~~~text
OUTGOING:
  App owns payload  --- sendBinary(buffer) ---> WebSocket provider
       |                                        |
       +--- không access buffer cho tới          |
            send future hoàn tất <---------------+

INCOMING:
  WebSocket provider --- onBinary(buffer) ----> App listener
       |                                         |
       +<--- listener CompletionStage hoàn tất --+
                provider có thể reclaim buffer

Nếu cần giữ data lâu: SNAPSHOT thành object độc lập.
~~~

**Một chi tiết quan trọng:** request(n) trên WebSocket **điều khiển số receive callback invocations** theo contract, **không** chuyển quyền truy cập của outbound sendBinary buffer hoặc tự giới hạn số bytes bạn đang enqueue để gửi. **Request(1) ở receive không đồng nghĩa one byte**, tương tự Flow-style demand counters.

### onText/onBinary và last

Với Listener, **boolean last** cho biết callback đang nhận fragment cuối của message. Nếu cần parse một message đầy đủ, phải tích lũy/stream theo framing ứng dụng và **tôn trọng giới hạn kích thước**; không giả định một callback tương ứng đúng một toàn bộ message. Giữ data qua callback phải tuân thủ lifecycle của CompletionStage; snapshot cho xử lý bất đồng bộ dài là cách rõ ràng.

## 13. CharSequence và ByteBuffer có thread-safety ra sao?

### String và StringBuilder

- **String immutable**, có thể chia sẻ an toàn nội dung giữa threads sau khi khởi tạo đúng; sendText không cần được cung cấp một StringBuilder mutable.
- **StringBuilder mutable và không synchronized**; cần quyền sở hữu đơn hoặc locking cho cả snapshot producer lẫn writer.
- **StringBuffer có synchronized methods** nhưng không cho phép mutation khi send operation đang pending; đồng bộ các method riêng lẻ không thay đổi hợp đồng WebSocket.
- **Custom CharSequence** có thể đọc dữ liệu lazily từ buffer ngoài hoặc từ memory-mapped file; không tự coi nó bất biến chỉ vì interface chỉ có length/charAt/subSequence.

### ByteBuffer

- **Buffer không thread-safe** theo Java NIO Buffer Javadoc.
- **position/limit/mark là state mutable**; ngay cả relative get() cũng có thể đổi position.
- **absolute get(index)** không sửa position nhưng vẫn là truy cập buffer: **không gọi trong khi sendBinary pending**.
- **slice/duplicate/readOnly** có position riêng, nhưng **shares bytes**; concurrent mutation của backing storage vẫn nguy hiểm.
- Với **array-backed** buffer, nếu bạn giữ raw byte[] thì phải xem nó là một alias: không sửa array trong lúc provider đang gửi buffer bọc array ấy.
- Với **direct** buffer, không sửa vùng nhớ qua foreign/native alias khi send pending.
- Nếu một ByteBuffer được đặt trong pool, **không trả về pool trước completion**: thread khác có thể mượn và ghi đè content.

### Memory visibility và completion

**CompletableFuture completion** là một mốc điều phối tốt để chuyển ownership trở lại ứng dụng. Để bảo đảm không có race, chỉ bắt đầu reuse **sau khi đã quan sát future hoàn tất**, ví dụ bằng **get/join/thenRun/whenComplete** và có ownership discipline.

Không polling **buffer.position()** để biết send tiến triển. Đó là một truy cập bị cấm lúc pending và không phải progress API đáng tin. Đo tiến độ bằng **future state, bytes expected precomputed, send latency/queue metrics**, không bằng “đọc trộm” vị trí buffer đang được implementation cập nhật.

## 14. Tối ưu copy hay không copy: lựa chọn có điều kiện

**Snapshot/copy** giúp giảm bug aliasing nhưng dùng thêm RAM/CPU. **Zero-copy/ownership transfer** có thể hiệu quả khi có thể thực thi độc quyền rõ ràng.

| Chiến lược | Dữ liệu trước send | Điều producer được làm | Chi phí chính |
|---|---|---|---|
| **String snapshot** | StringBuilder.toString() | Sửa builder sau snapshot | Cấp phát String mới |
| **ByteBuffer.allocate + copy** | Buffer mới chứa vùng bytes cần gửi | Sửa source sau copy xong | Copy bytes và bộ nhớ thêm |
| **byte[].clone() + ByteBuffer.wrap** | Mảng clone độc lập | Sửa array gốc sau clone | Copy toàn mảng |
| **Transfer exclusive ByteBuffer** | Buffer cùng object bàn giao cho sender | **Không đọc/sửa** buffer cho tới completion | Khó quản lý ownership, ít copy |
| **duplicate()/slice()** | View chia sẻ content | Không sửa backing storage khi view send pending | Không copy bytes, **không cô lập dữ liệu** |
| **asReadOnlyBuffer()** | View read-only nhưng chung storage | Không sửa storage gốc khi view send pending | Không copy bytes, chỉ cấm ghi qua view |

**Đo mới quyết định:** với payload nhỏ, String/byte[] copy có thể rẻ hơn nhiều so với chi phí debug race. Với payload lớn/high throughput, quản lý pool và exclusive ownership có thể tránh copy, nhưng phải ràng buộc chặt message lifecycle và backpressure. Tuyệt đối không tối ưu bằng cách vi phạm contract.

### Bảng thời gian ownership

| Mốc | Mutable CharSequence đã pass | ByteBuffer đã pass |
|---|---|---|
| Trước gọi send | Caller được sửa theo hợp đồng của nó | Caller được cấu hình position/limit và dữ liệu |
| Vừa gọi send, future chưa done | **Không sửa data** | **Không truy cập buffer** |
| Future done bình thường | Có thể tái sử dụng, nếu không còn bên khác giữ | Có thể đọc/reuse; remaining()==0 |
| Future done lỗi | Có thể xử lý dữ liệu sau khi lifecycle kết thúc, nhưng không tin message chưa tới peer | Không tin trạng thái bytes; xây lại từ snapshot khi retry |
| Chỉ timeout ở future.get(timeout) | **Chưa được coi send hoàn tất** | **Chưa được coi send hoàn tất** |
| Connection abort/close | Dọn theo futures và contract | Dọn/recycle khi chắc chắn không còn operation đang dùng |

## 15. Bảo mật và giới hạn kích thước dữ liệu

Các lỗi ownership không chỉ là lỗi logic. Trong một hệ thống trao đổi **token, lệnh tài chính, PII hoặc binary protocol**, mutate nhầm payload in flight có thể làm gửi sai user ID, sai request ID hoặc dữ liệu của message khác.

Các nguyên tắc bảo vệ:

- **Không log payload secrets** khi debug race; log message type, ID, hash có kiểm soát, byte count và future state.
- **Không dùng chung một ByteBuffer pool slot** cho hai sessions đang gửi; pool phải có leases/release-on-completion.
- **Giới hạn message size và queued bytes**; một producer độc hại có thể tạo nhiều message lớn và giữ heap/direct memory quá lâu.
- **WebSocket wss:// với TLS** khi đi qua mạng không đáng tin; ws:// chỉ dành cho loopback/lab hoặc môi trường đã có bảo vệ riêng.
- **Validate input** trước khi snapshot/send; một StringBuilder quá lớn vẫn có thể gây OOM khi toString tạo String mới.
- **Không ghi đè credentials giữa messages** bằng shared char[]/ByteBuffer khi send trước chưa hoàn tất.
- **Server-side authorization** và application ACK vẫn cần thiết; WebSocket transport không tự cấp quyền hay bảo đảm commit.

### Mối quan hệ với backpressure

Một server/peer chậm khiến send futures hoàn tất chậm, làm **in-flight buffers** tồn tại lâu. Nếu cứ tiếp tục enqueue snapshots vô hạn, heap/direct memory tăng. Thiết kế resource quota, cảnh báo backlog và policy drop/reject/cancel phù hợp; không tăng đồng thời số sends trên cùng connection vượt contract nhằm “chạy nhanh hơn”.

## 16. Những lỗi lập trình dễ gặp

### Lỗi A — Sửa StringBuilder ngay sau sendText

**Sai:** truyền builder vào sendText rồi append/clear/replace ngay. **Đúng:** truyền String snapshot hoặc đợi future kết thúc trước khi sửa builder.

### Lỗi B — Tự cho rằng sendText đã copy tất cả khi trả về

**Sai:** phụ thuộc “máy test chạy nhanh nên message đúng”. **Đúng:** làm theo Javadoc, không suy diễn thời điểm implementation đọc data.

### Lỗi C — Gọi buffer.remaining() để log ngay sau sendBinary

**Sai:** vẫn là truy cập ByteBuffer khi future pending. **Đúng:** lưu expectedLength trước send; chỉ đọc remaining sau success.

### Lỗi D — Rewind/flip/clear trước completion

**Sai:** thay đổi position/limit mà WebSocket đang sử dụng. **Đúng:** một operation giữ buffer độc quyền cho đến future done.

### Lỗi E — Dùng duplicate/slice làm “bản sao”

**Sai:** hai buffers chia sẻ content. **Đúng:** clone array hoặc allocate+copy nếu cần dữ liệu độc lập.

### Lỗi F — asReadOnlyBuffer làm mọi alias bất biến

**Sai:** readonly view thấy mảng nền bị thay từ nguồn khác. **Đúng:** quản lý backing storage hoặc deep copy.

### Lỗi G — Dùng lại buffer sau future.get(timeout) ném TimeoutException

**Sai:** get timeout chỉ nghĩa caller hết thời gian đợi, send có thể vẫn pending. **Đúng:** bảo vệ ownership tới khi lifecycle được giải quyết và dọn/cancel theo policy.

### Lỗi H — Gửi đồng thời nhiều text/binary operations

**Sai:** gọi sendText và sendBinary cùng lúc rồi hy vọng JDK tự hàng đợi. **Đúng:** chain bằng thenCompose hoặc bounded send queue; handle IllegalStateException.

### Lỗi I — Bỏ last=false và chuyển loại message

**Sai:** text dở dang rồi sendBinary; có thể gặp IllegalStateException. **Đúng:** hoàn tất message đúng loại bằng last=true trước khi đổi loại.

### Lỗi J — Nghĩ future success nghĩa server đã xử lý

**Sai:** không có ACK nghiệp vụ. **Đúng:** thêm app-level response/ACK/request ID khi protocol cần exactly-once/effectively-once semantics.

### Lỗi K — Return/recycle pooled ByteBuffer trước khi future done

**Sai:** consumer khác có thể ghi đè bytes. **Đúng:** retain lease theo future, release sau completion và không reuse khi trạng thái chưa rõ.

### Lỗi L — Giữ CharSequence từ Listener sau receive stage completion

**Sai:** provider có thể reclaim dữ liệu. **Đúng:** tạo String snapshot/byte[] copy trong thời gian còn quyền.

## 17. Ma trận kiểm thử ownership và failure

| Test | Thiết lập | Kỳ vọng |
|---|---|---|
| Immutable text | Gửi String "HELLO" | Server nhận HELLO |
| Mutable builder snapshot | snapshot builder rồi thay builder | Server vẫn nhận snapshot cũ |
| Owned binary buffer | clone mảng rồi gửi | Server thấy bytes của clone |
| Binary completion | sendBinary future success | ByteBuffer.remaining()==0 sau future done |
| ByteBuffer.slice alias | Sửa original backing array | slice thấy bytes đổi |
| ByteBuffer.read-only alias | Sửa backing array | read-only view vẫn thấy bytes đổi |
| Deep copy | allocate+put từ source | snapshot không thay theo source |
| CharBuffer read-only alias | Sửa char[] nguồn | view thấy dữ liệu mới |
| String snapshot | String tạo trước khi sửa char[] | String không đổi |
| Fragmented text | sendText(...,false) rồi sendText(...,true) theo chain | Một message hoàn chỉnh, đúng thứ tự |
| Concurrent text+binary sends | Gửi khi send khác pending | Có thể exceptional IllegalStateException |
| I/O failure | Đóng peer khi send đang chạy | Future failed; cleanup, không retry buffer cũ mù quáng |
| Wait timeout | get(timeout) hết hạn | Không tái dùng payload nếu send vẫn pending |
| Pool reuse | Có lease per send | Không buffer slot nào được cho mượn trước completion |
| High concurrency | N producers gửi message | Bounded queue/bytes, không OOM |
| Malformed UTF-16 | Unpaired surrogate theo test lab | sendText có thể fail IOException qua future |
| Backpressure | Peer đọc chậm | Futures kéo dài, queue được giới hạn |

**Không cần cố ý mutate object đang pending để “test race”**: hành vi ấy đã vi phạm contract. Việc một runtime tình cờ gửi đúng payload không chứng minh code đúng. Thay vì tạo test phụ thuộc timing, tạo tests cho snapshot, aliasing, sequencing, queues và lifecycle.

### Monitoring và vận hành

Các metrics nên có:

- **websocket_send_pending_count** và thời gian send futures chưa done.
- **websocket_outbound_queued_bytes/messages**, in-flight bytes, số buffer leases đang giữ.
- **websocket_send_success/failure** phân theo message type/cause.
- **websocket_close_code**, abnormal close, timeouts, aborts.
- **application_ack_latency** nếu protocol có ACK ở tầng ứng dụng.
- **snapshot_copy_bytes**, direct/heap memory pressure, GC pause, pool exhaustion.

Giới hạn metric cardinality, không đưa message content, token hay user credentials vào nhãn metrics. Một operation thất bại có thể do IOException, connection closed hoặc trạng thái gửi không hợp lệ; log nguyên nhân, không gộp tất cả thành “timeout”.

## 18. Bài tập thực hành

### Bài tập 1 — Chứng minh String snapshot

Chạy **WebSocketPayloadOwnershipDemo.java**. Đổi HELLO thành một text Unicode có tiếng Việt; tạo String snapshot trước send, sửa draft ngay sau khi khởi tạo send. Kỳ vọng server nhận **nội dung snapshot**, không phải bản builder sau sửa. Không đưa mutable builder trực tiếp vào send rồi sửa để thử may rủi.

### Bài tập 2 — Giới hạn vùng ByteBuffer

Tạo byte[] gồm 8 byte, đặt position=2 và limit=6, tạo một **buffer độc lập từ remaining()**, rồi sendBinary. Kiểm tra server nhận đúng byte indexes 2..5 và owned.remaining() bằng 0 sau successful completion. Không đọc buffer đang pending.

### Bài tập 3 — Views vs copy

Trong **BufferAliasingDemo.java**, thử dùng **duplicate()** thay cho allocate+copy rồi sửa backing array. Giải thích vì sao output không còn thể hiện snapshot độc lập. Trả code về phiên bản deep copy.

### Bài tập 4 — CharBuffer readonly

Tạo CharBuffer.wrap(char[]) rồi asReadOnlyBuffer; sửa array nguồn và so với String snapshot. Viết unit test cho kết quả khác nhau, giải thích tại sao readonly không đủ cho sendText an toàn nếu backing array mutable.

### Bài tập 5 — Phân đoạn message

Dùng một WebSocket server lab hỗ trợ fragmentation chuẩn (không phải tiny server trong demo vốn chỉ hỗ trợ FIN=true). Gửi sendText("A",false) rồi thenCompose sendText("B",true). Test listener nhận đúng message AB; không chuyển sang binary trước text last=true.

### Bài tập 6 — Queue nhiều producers

Viết class SequentialSender sở hữu một WebSocket, nhận Strings/snapshots từ nhiều producers qua queue có max 100 messages và max 1 MiB queued data. Chain future, xử lý thất bại fail-stop, release buffers sau completion.

### Bài tập 7 — Thời hạn gửi

Đặt deadline cho một send đang pending trên peer chậm. Khi get(timeout) hết hạn, **không** gọi clear/reuse buffer. Thiết kế abort/cleanup và xử lý application outcome unknown; phân biệt với future exceptional completion.

### Bài tập 8 — Binary pool lease

Tạo pool tối đa 10 ByteBuffers. Mỗi send lấy một lease, chuyển độc quyền sang sender, release chỉ khi future done. Đo active leases; kiểm thử rằng cùng object không thể bị hai sends sở hữu đồng thời.

### Bài tập 9 — Listener ownership

Tạo WebSocket Listener.onBinary, copy payload vào byte[] rồi trả completed stage. Đảm bảo task xử lý byte[] sau đó **không chạm tới ByteBuffer do provider truyền vào**. So với onText tạo String snapshot trước khi callback hoàn tất.

### Bài tập 10 — ACK nghiệp vụ

Xây protocol message có requestId và server gửi ACK sau khi xử lý. Phân biệt **send future success** với **received business ACK**. Khi connection close trước ACK, phân loại outcome unknown và retry theo idempotency policy, tránh nhân đôi side effects.

## 19. Câu hỏi tự kiểm tra

**1. sendText trả CompletableFuture rồi có được sửa StringBuilder đã truyền vào không?** Không, cho tới khi future hoàn tất.

**2. Tại sao String được ưu tiên khi gửi text?** String immutable, không bị caller thay nội dung giữa lúc send.

**3. Có thể sửa StringBuilder sau khi đã tạo String snapshot và truyền snapshot không?** Có, vì WebSocket không dùng builder ấy; cần snapshot nhất quán ở thời điểm tạo.

**4. sendBinary dùng bytes nào?** Vùng [position, limit) của ByteBuffer.

**5. Có được gọi buffer.remaining() khi binary future chưa done không?** Không. Javadoc nói ByteBuffer không được truy cập cho tới khi future hoàn tất.

**6. Khi sendBinary hoàn tất bình thường, remaining() bằng bao nhiêu?** 0.

**7. Khi sendBinary future thất bại, có thể khẳng định position vẫn ban đầu không?** Không. Không dựng retry từ trạng thái suy đoán của buffer.

**8. duplicate() là deep copy?** Không. Nó chia sẻ content nhưng có state position/limit riêng.

**9. slice() có chia sẻ content không?** Có; nó là view một vùng dữ liệu của buffer gốc.

**10. asReadOnlyBuffer() có bảo đảm backing array không thể thay đổi không?** Không. Alias khác vẫn sửa được backing bytes.

**11. CharBuffer.asReadOnlyBuffer() có làm char[] nguồn bất biến không?** Không.

**12. ByteBuffer.wrap(array) có sao chép array không?** Không, buffer chia sẻ mảng gốc.

**13. byteArray.clone() có tạo backing storage riêng không?** Có, với mảng byte.

**14. TimeoutException của future.get(timeout) có nghĩa send chắc chắn dừng chưa?** Chưa; nó chỉ cho biết thread chờ hết thời hạn.

**15. Có thể gửi sendText và sendBinary cùng lúc trên một WebSocket không?** Không được dựa vào điều đó; pending text/binary send có thể gây IllegalStateException, cần serialize.

**16. last=false có nghĩa WebSocket message hoàn tất chưa?** Chưa; còn fragment tiếp theo.

**17. sendText success có nghĩa server business logic đã commit không?** Không. Cần ACK nghiệp vụ nếu muốn xác nhận xử lý.

**18. sendPing(ByteBuffer) có thể truy cập buffer đang gửi không?** Không; cũng phải đợi future. Control payload tối đa 125 byte.

**19. onBinary Listener có dùng cùng quy tắc ownership như sendBinary không?** Hai chiều khác nhau: outgoing caller không truy cập buffer trước send future done; incoming listener không truy cập provider buffer **sau khi stage nhận đã completed**.

**20. Dùng ByteBuffer pool cần nguyên tắc nào?** Không recycle lease đang được future giữ; release sau completion/lifecycle rõ ràng.

**21. Vì sao không nên dùng test sửa dữ liệu pending để kết luận an toàn?** Vì đó là hành vi vi phạm contract và kết quả có thể thay đổi theo scheduling/network/provider.

**22. Cách đơn giản để tránh mutable CharSequence race là gì?** Snapshot thành String bất biến trước khi send, trong khi dữ liệu nguồn được đồng bộ nếu có nhiều writers.

## Nguồn tài liệu chính thức

- **Java SE 17 — WebSocket (sendText, sendBinary, sendPing, sendPong, sendClose):** https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/WebSocket.html
- **Java SE 17 — WebSocket.Listener (ownership của received CharSequence/ByteBuffer):** https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/WebSocket.Listener.html
- **Java SE 17 — WebSocket.Builder (buildAsync):** https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/WebSocket.Builder.html
- **Java SE 17 — ByteBuffer (wrap/duplicate/slice/asReadOnlyBuffer):** https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/ByteBuffer.html
- **Java SE 17 — Buffer (position, limit, thread safety):** https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/Buffer.html
- **Java SE 17 — CharBuffer:** https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/CharBuffer.html
- **Java SE 17 — CompletableFuture:** https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CompletableFuture.html
- **RFC 6455 — The WebSocket Protocol:** https://www.rfc-editor.org/rfc/rfc6455

**Ghi nhớ:** Với **WebSocket.sendText(CharSequence, last)**, không sửa **CharSequence được truyền vào** cho tới khi returned CompletableFuture hoàn tất. Với **sendBinary(ByteBuffer, last)**, **không truy cập ByteBuffer được truyền vào** cho tới khi future hoàn tất; sau successful completion, remaining()==0. **slice/duplicate/asReadOnlyBuffer vẫn chia sẻ dữ liệu nền**, nên không phải deep copy. Sử dụng **String immutable snapshot**, **byte[] clone/allocate+copy** hoặc **exclusive buffer ownership**; serialize send operations bằng futures, quản lý backpressure, timeout/failure và không nhầm send completion với application ACK.