# Giới hạn mô hình cache tài nguyên đắt tiền trong ThreadLocal

`ThreadLocal` cho phép mỗi thread giữ một giá trị riêng, vì vậy có thể dùng để tái sử dụng một số đối tượng mutable, không thread-safe và tốn chi phí khởi tạo mà không phải đồng bộ giữa các thread. Tuy nhiên, `ThreadLocal` chỉ gắn giá trị với vòng đời của thread; nó không phải một object pool có giới hạn, không tự quản lý việc đóng tài nguyên và không bảo đảm dữ liệu được chuyển theo một request khi request đổi thread.

Mô hình này phù hợp nhất với đối tượng phụ trợ có vòng đời đơn giản, chỉ dùng bởi một thread tại một thời điểm và có thể reset sau mỗi lần sử dụng, chẳng hạn một `MessageDigest`. Với kết nối cơ sở dữ liệu, socket, file handle, transaction hoặc tài nguyên native cần đóng và giới hạn số lượng, nên dùng cơ chế quản lý tài nguyên hoặc pool chuyên dụng. Java 21 còn có virtual threads, khiến việc tạo một bản sao tài nguyên đắt tiền cho mỗi thread càng cần được cân nhắc kỹ.

## 1. `ThreadLocal` lưu một giá trị riêng trên mỗi thread

Một đối tượng `ThreadLocal<T>` đại diện cho một biến có giá trị riêng đối với từng thread. Các thread gọi `get()` trên cùng một `ThreadLocal` sẽ nhận giá trị gắn với chính thread đang gọi:

```java
private static final ThreadLocal<StringBuilder> BUFFER =
        ThreadLocal.withInitial(StringBuilder::new);

static String buildMessage(String value) {
    StringBuilder builder = BUFFER.get();
    builder.setLength(0);
    builder.append("Hello, ").append(value);
    String result = builder.toString();

    // Không giữ buffer có capacity quá lớn sau một request bất thường.
    if (builder.capacity() > 64 * 1024) {
        BUFFER.remove();
    }
    return result;
}
```

Nếu thread A và thread B cùng gọi `buildMessage()`, mỗi thread có một `StringBuilder` riêng. Không cần khóa để hai thread tránh ghi đồng thời vào cùng một builder. Tuy vậy, mỗi thread có thể giữ một builder trong suốt thời gian sống của nó, kể cả khi không còn xử lý request.

Các phương thức chính:

| Phương thức | Ý nghĩa |
| --- | --- |
| `ThreadLocal.withInitial(supplier)` | Tạo `ThreadLocal` có hàm khởi tạo; supplier được gọi khi thread lần đầu gọi `get()` mà chưa có giá trị. |
| `get()` | Lấy giá trị gắn với thread hiện tại; nếu chưa có, khởi tạo giá trị. |
| `set(value)` | Gán giá trị cho thread hiện tại. |
| `remove()` | Xóa giá trị gắn với thread hiện tại; lần `get()` tiếp theo sẽ khởi tạo lại. |
| `initialValue()` | Phương thức có thể override để cung cấp giá trị khởi tạo; mặc định trả về `null`. |

`ThreadLocal` không chia sẻ một instance cho các thread. Nó cũng không tự sao chép giá trị khi công việc được chuyển từ thread này sang thread khác. Nếu một request chạy lần lượt trên nhiều executor thread, mỗi thread sẽ đọc giá trị ThreadLocal riêng của nó.

Reset nội dung không nhất thiết giải phóng bộ nhớ đã cấp phát. Chẳng hạn, `StringBuilder.setLength(0)` xóa nội dung logic nhưng thường giữ nguyên capacity; một request lớn bất thường có thể khiến worker thread giữ buffer lớn qua nhiều request sau. Có thể bỏ cache vượt ngưỡng như ví dụ trên, hoặc thay value bằng một buffer mới sau khi đã lấy kết quả. Ngưỡng phải được chọn theo kích thước dữ liệu và số worker thực tế.

## 2. Khi nào cache theo thread có ích?

Mô hình này có thể phù hợp khi đồng thời thỏa mãn các điều kiện sau:

- Đối tượng tốn chi phí tạo mới hoặc chuẩn bị trạng thái ban đầu.
- Đối tượng mutable hoặc không thread-safe nên không thể chia sẻ trực tiếp giữa nhiều thread.
- Đối tượng không giữ tài nguyên bên ngoài cần đóng theo từng request, hoặc có quy trình reset/cleanup rõ ràng.
- Số lượng thread sử dụng cache được kiểm soát và chi phí giữ một instance cho mỗi thread chấp nhận được.
- Công việc không cần chuyển chính instance đó sang thread khác.

Ví dụ điển hình là một bộ tính toán mutable như `MessageDigest`. Nó giữ trạng thái trong lúc cập nhật dữ liệu và không được thiết kế để nhiều thread đồng thời thao tác trên cùng một instance. Có thể tạo một instance cho mỗi thread và reset sau mỗi phép tính.

Ngược lại, nếu đối tượng immutable và thread-safe, thường nên chia sẻ một instance thay vì tạo cache theo thread. Ví dụ `DateTimeFormatter` là immutable và thread-safe; không cần đặt nó trong `ThreadLocal` chỉ để tránh chia sẻ.

## 3. Ví dụ: tái sử dụng `MessageDigest` theo thread

`MessageDigest` là API chuẩn dùng để tính digest. Việc lấy instance thông qua `MessageDigest.getInstance()` có chi phí tra cứu và khởi tạo provider; một ứng dụng thực hiện nhiều phép tính có thể tái sử dụng instance riêng cho từng thread.

```java
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.HexFormat;

public final class Sha256Cache {
    private static final ThreadLocal<MessageDigest> SHA_256 =
            ThreadLocal.withInitial(Sha256Cache::newDigest);

    private Sha256Cache() {}

    private static MessageDigest newDigest() {
        try {
            return MessageDigest.getInstance("SHA-256");
        } catch (NoSuchAlgorithmException e) {
            throw new IllegalStateException("SHA-256 is unavailable", e);
        }
    }

    public static String hashHex(byte[] input) {
        MessageDigest digest = SHA_256.get();
        try {
            return HexFormat.of().formatHex(digest.digest(input));
        } finally {
            // Đảm bảo không giữ trạng thái của lần tính trước.
            digest.reset();
        }
    }
}
```

`ThreadLocal.withInitial()` tạo `MessageDigest` khi một thread lần đầu gọi `get()`. Những lần gọi sau trên cùng thread có thể dùng lại instance. Thread khác nhận instance khác. `digest(byte[])` hoàn tất phép tính và reset trạng thái theo hợp đồng của `MessageDigest`; lệnh `reset()` trong `finally` làm rõ ý định đưa đối tượng về trạng thái ban đầu kể cả khi code xử lý kết quả phát sinh lỗi.

Cache này chỉ giữ một `MessageDigest` cho mỗi thread đã gọi `hashHex()`. Nó không tạo một digest dùng chung giữa các thread và cũng không giới hạn tổng số instance nếu ứng dụng tạo rất nhiều thread.

Không nên giữ tham chiếu `MessageDigest` trả về từ ThreadLocal để dùng ở thread khác. Hãy giữ phạm vi sử dụng bên trong phương thức, hoàn tất phép tính và reset trước khi trả kết quả.

## 4. Giới hạn về vòng đời và chi phí bộ nhớ

`ThreadLocal` không có chính sách eviction, giới hạn tổng dung lượng hoặc giới hạn số lượng giá trị. Mỗi thread gọi `get()` có thể giữ một giá trị riêng. Nếu mỗi instance chiếm 2 MB và 200 thread cùng khởi tạo cache, phần bộ nhớ giữ lại có thể xấp xỉ 400 MB, chưa tính overhead và dữ liệu phụ.

Số lượng instance không nhất thiết bằng số request. Trong thread pool, nhiều request có thể lần lượt dùng cùng một worker thread và tái sử dụng cùng một giá trị. Nhưng với mô hình tạo thread linh hoạt hoặc virtual thread, số thread từng chạm vào cache có thể rất lớn.

Hãy đánh giá cả hai chi phí:

- **Chi phí khởi tạo:** số lần tạo mới đối tượng khi thread bắt đầu dùng cache.
- **Chi phí lưu giữ:** số instance còn sống và lượng bộ nhớ/tài nguyên chúng giữ trong toàn bộ vòng đời thread.

ThreadLocal chỉ có lợi khi tiết kiệm chi phí khởi tạo lớn hơn chi phí lưu giữ và cleanup. Nếu instance lớn, hiếm khi được dùng lại hoặc thread tồn tại lâu hơn request rất nhiều, cache có thể làm tăng bộ nhớ và giữ tài nguyên nhàn rỗi.

## 5. Thread pool tái sử dụng thread: phải reset và quản lý giá trị

Trong thread pool, một worker thread có thể xử lý nhiều request khác nhau. Giá trị ThreadLocal không tự được xóa khi một task kết thúc; task tiếp theo trên cùng worker có thể nhận lại giá trị cũ.

```java
private static final ThreadLocal<String> REQUEST_ID = new ThreadLocal<>();

static void handleRequest(String requestId) {
    REQUEST_ID.set(requestId);
    try {
        processRequest();
    } finally {
        REQUEST_ID.remove();
    }
}

static void processRequest() {
    System.out.println("Processing " + REQUEST_ID.get());
}
```

Ví dụ trên dùng ThreadLocal để lưu context theo request, không phải cache dài hạn. `remove()` trong `finally` ngăn request sau nhìn thấy dữ liệu của request trước và giúp giải phóng tham chiếu khi worker còn sống.

Với cache đối tượng tái sử dụng như `MessageDigest`, xóa sau mỗi request sẽ khiến lợi ích cache biến mất. Khi đó, cần reset trạng thái sau mỗi lần sử dụng và xác định thời điểm kết thúc vòng đời cache, chẳng hạn khi worker/executor kết thúc hoặc khi ứng dụng dừng. Hai mục tiêu khác nhau cần hai chính sách khác nhau:

| Mục đích | Sau mỗi task | Khi nào gọi `remove()` |
| --- | --- | --- |
| Lưu context riêng của request | Xóa dữ liệu bằng `remove()` trong `finally`. | Cuối request, kể cả khi có exception. |
| Cache đối tượng phụ trợ có thể tái sử dụng | Reset object về trạng thái sạch. | Khi cache không còn cần thiết hoặc khi thread/ứng dụng kết thúc. |

Không giữ dữ liệu nhạy cảm như token, thông tin xác thực hoặc dữ liệu cá nhân trong ThreadLocal mà không có chính sách xóa cụ thể. Worker thread có thể được tái sử dụng cho người dùng khác.

## 6. Vì sao `remove()` quan trọng?

`ThreadLocal.remove()` xóa entry của ThreadLocal hiện tại khỏi thread hiện tại. Nó không xóa giá trị ở các thread khác. Nếu gọi `get()` sau đó, `initialValue()` hoặc supplier của `withInitial()` được chạy lại.

```java
private static final ThreadLocal<StringBuilder> BUFFER =
        ThreadLocal.withInitial(StringBuilder::new);

static void finishTask() {
    BUFFER.remove();
}
```

Gọi `remove()` khi giá trị không còn cần thiết giúp thread pool không giữ object hoặc dữ liệu request quá lâu. Tuy nhiên, `remove()` không phải phương thức đóng tài nguyên. Nếu value giữ một object `AutoCloseable`, phải gọi `close()` theo đúng hợp đồng rồi mới remove.

```java
private static final ThreadLocal<SomeResource> RESOURCE =
        ThreadLocal.withInitial(SomeResource::open);

static void closeCurrentThreadResource() throws Exception {
    SomeResource resource = RESOURCE.get();
    try {
        resource.close();
    } finally {
        RESOURCE.remove();
    }
}
```

Ví dụ giả định `SomeResource` có phương thức `open()` trả về một resource và triển khai `close()`. Đây chỉ là minh họa thứ tự cleanup; không nên dùng mô hình này cho resource cần được pool quản lý nếu ứng dụng không có cách gọi cleanup trên đúng worker thread. `ThreadLocal.remove()` chỉ tác động đến thread đang thực hiện lệnh, nên thread điều phối không thể gọi `remove()` thay cho tất cả worker khác.

## 7. Rủi ro retention và class-loader leak

Trong triển khai OpenJDK, mỗi thread có cấu trúc lưu các entry ThreadLocal. Key của entry là tham chiếu yếu đến đối tượng `ThreadLocal`, nhưng value vẫn là tham chiếu mạnh. Khi key bị thu gom, value không nhất thiết được thu gom ngay; entry cũ chỉ được dọn trong những lần thao tác phù hợp trên ThreadLocalMap hoặc khi thread kết thúc.

Điều này đặc biệt đáng chú ý với thread pool có worker sống lâu:

1. Một task tạo ThreadLocal tạm thời và gắn một object lớn vào worker.
2. Tham chiếu tới đối tượng ThreadLocal biến mất sau task.
3. Key yếu có thể bị thu gom, nhưng value vẫn có thể được giữ bởi entry cũ.
4. Worker tiếp tục sống và giữ value cho đến khi entry được dọn hoặc thread kết thúc.

Trong ứng dụng chạy trong application server, value có thể tham chiếu đến class được nạp bởi class loader của ứng dụng. Nếu worker thuộc thread pool sống lâu ở cấp server, tham chiếu đó có thể ngăn class loader của ứng dụng được giải phóng sau redeploy. Đây là một nguồn class-loader leak thường gặp.

Biện pháp thực tế:

- Dùng `static final ThreadLocal` cho cache có vòng đời rõ ràng thay vì tạo ThreadLocal mới trong từng request.
- Gọi `remove()` trong `finally` với dữ liệu theo request hoặc cache có vòng đời ngắn.
- Reset object để không giữ lại buffer, input hoặc dữ liệu nhạy cảm từ task trước.
- Đóng resource trước khi remove; không trông chờ garbage collector thay cho `close()`.
- Dừng executor do ứng dụng sở hữu và kết thúc worker đúng vòng đời khi ứng dụng shutdown/redeploy.

Chi tiết weak key/strong value là mô tả triển khai OpenJDK, không phải API contract để ứng dụng dựa vào thời điểm cleanup. Quy tắc an toàn vẫn là quản lý vòng đời tường minh và không để ThreadLocal giữ tham chiếu lâu hơn cần thiết.

## 8. Không dùng ThreadLocal như object pool cho tài nguyên cần đóng

Một connection, socket, file handle hoặc transaction thường có trạng thái bên ngoài và yêu cầu cleanup rõ ràng. Gắn chúng vào ThreadLocal có thể dẫn đến các vấn đề:

- Resource được giữ lâu hơn request hoặc transaction dự kiến.
- Worker thread có thể giữ connection nhàn rỗi trong thời gian dài, làm cạn giới hạn connection của database.
- Một task bị hủy hoặc luồng xử lý phát sinh exception có thể bỏ qua cleanup nếu không có `finally` đáng tin cậy.
- ThreadLocal không giới hạn số resource theo dung lượng pool; số lượng có thể tăng theo số worker thread.
- Một request chuyển sang thread khác không mang theo connection hoặc transaction trong ThreadLocal.

Với JDBC, hãy ưu tiên `DataSource` và connection pool chuyên dụng. Mượn connection khi bắt đầu đơn vị công việc, đóng/return connection bằng try-with-resources khi kết thúc. Với socket/file, dùng API quản lý vòng đời rõ ràng và đóng trong `try`-with-resources. Với transaction, dùng transaction manager hoặc cơ chế truyền context phù hợp.

ThreadLocal có thể chứa trạng thái hỗ trợ nhỏ, có thể reset và có vòng đời rõ ràng; cấu hình bất biến hoặc factory dùng chung thường phù hợp hơn khi đặt ở một field `static final`.

## 9. Virtual threads trong Java 21 làm thay đổi phép tính cache

Java 21 chuẩn hóa virtual threads. Mỗi virtual thread có trạng thái ThreadLocal riêng; giá trị không thuộc về carrier thread đang tạm chạy virtual thread đó. Vì virtual thread thường được tạo theo task và có thể có số lượng rất lớn, cache một resource nặng cho mỗi virtual thread có thể tạo ra rất nhiều instance và tiêu tốn bộ nhớ/tài nguyên.

Ví dụ, nếu server xử lý hàng chục nghìn request bằng virtual threads và mỗi request gọi `RESOURCE.get()`, một ThreadLocal có thể khởi tạo hàng chục nghìn resource, thay vì chỉ một resource cho mỗi vài worker thread như mô hình pool cố định.

Do đó:

- Không giả định ThreadLocal trong virtual thread được chia sẻ theo carrier hoặc theo CPU.
- Tránh dùng ThreadLocal để giữ connection, client hoặc buffer lớn nếu mỗi virtual thread chỉ dùng trong thời gian ngắn.
- Với tài nguyên khan hiếm, dùng pool/bounded concurrency hoặc semaphore để giới hạn số tài nguyên đồng thời.
- Với đối tượng immutable và thread-safe, chia sẻ một instance chung thường phù hợp hơn.
- Chỉ dùng ThreadLocal cho dữ liệu hoặc scratch object nhỏ, có vòng đời gắn với virtual thread và có thể thu hồi khi task kết thúc.

Virtual thread kết thúc thì các giá trị ThreadLocal gắn với nó có thể được thu hồi cùng thread khi không còn tham chiếu khác. Tuy nhiên, không nên dựa vào garbage collection để đóng resource native hoặc trả connection về pool; vẫn cần cleanup rõ ràng.

## 10. Reentrancy và việc tái sử dụng cùng một object

ThreadLocal bảo đảm các thread khác nhau không dùng chung value, nhưng không ngăn một thread gọi lồng nhau vào cùng một phương thức. Nếu phương thức lấy một mutable object từ ThreadLocal rồi gọi callback hoặc phương thức khác cũng dùng chính ThreadLocal đó trước khi thao tác đầu hoàn tất, lần gọi lồng nhau có thể ghi đè trạng thái của lần gọi ngoài.

Ví dụ, một `MessageDigest` lấy từ ThreadLocal rồi được `update()` từng phần; nếu giữa các lần update gọi code bên ngoài có thể gọi lại hàm hash, lần gọi lồng nhau sẽ reset hoặc thay đổi cùng digest.

Để tránh lỗi:

- Giữ vùng sử dụng object ngắn và không gọi callback tùy ý khi object đang ở trạng thái trung gian.
- Dùng API thao tác hoàn chỉnh như `digest(input)` rồi reset trước khi trả về.
- Nếu có yêu cầu reentrant, dùng stack/depth-aware holder hoặc tạo instance tạm cho lần gọi lồng nhau.
- Không trả mutable object đang được cache cho caller tự giữ và sử dụng sau khi phương thức kết thúc.

## 11. ThreadLocal không phải cơ chế truyền context giữa các thread

Giá trị ThreadLocal gắn với thread hiện tại, không gắn với request hoặc task. Khi một task được gửi sang executor khác, thread thực thi mới không tự nhận các giá trị ThreadLocal của thread gửi. `InheritableThreadLocal` có cơ chế kế thừa khi tạo thread, nhưng không phải giải pháp tổng quát cho thread pool hoặc virtual-thread task handoff; nó cũng có thể sao chép context không mong muốn và kéo dài vòng đời dữ liệu.

Với context nghiệp vụ, hãy cân nhắc truyền tham số tường minh hoặc dùng cơ chế context propagation được framework hỗ trợ. Không dùng ThreadLocal để truyền ngầm trạng thái qua ranh giới executor hoặc để giả định một request luôn chạy trên cùng thread.

## 12. Bảng quyết định sử dụng ThreadLocal

| Trường hợp | Có nên dùng ThreadLocal? | Lý do / lựa chọn phù hợp |
| --- | --- | --- |
| `MessageDigest` mutable, tái sử dụng nhiều lần trên cùng worker | Có thể phù hợp | Một instance riêng mỗi thread; reset sau mỗi lần dùng và đo lợi ích thực tế. |
| `DateTimeFormatter` immutable, thread-safe | Không cần | Chia sẻ instance `static final`. |
| Request ID hoặc context tạm trong thread pool | Có điều kiện | Đặt trước khi xử lý và `remove()` trong `finally`; cân nhắc context propagation nếu task đổi thread. |
| JDBC connection | Không nên | Dùng `DataSource`/connection pool và đóng/return connection theo đơn vị công việc. |
| Socket, file handle hoặc transaction | Không nên làm cache mặc định | Cần lifecycle, timeout, cleanup và giới hạn số lượng rõ ràng. |
| Buffer rất lớn trong virtual threads | Thường không phù hợp | Dễ nhân bộ nhớ theo số virtual thread; dùng buffer pool có giới hạn nếu cần. |
| Dữ liệu nhạy cảm của người dùng | Tránh nếu không có cleanup chặt | Worker thread được tái sử dụng; phải xóa trong mọi nhánh kết thúc. |
| Object cần dùng xuyên nhiều thread | Không phù hợp | ThreadLocal không truyền cùng instance; dùng thiết kế chia sẻ thread-safe hoặc truyền tham chiếu rõ ràng. |

## 13. Checklist khi thiết kế cache ThreadLocal

1. Xác nhận object thực sự mutable hoặc không thread-safe; nếu thread-safe, ưu tiên chia sẻ.
2. Đo chi phí khởi tạo và lợi ích tái sử dụng trước khi thêm cache.
3. Ước lượng số thread tối đa, số instance và bộ nhớ giữ lại.
4. Xác định object có giữ resource ngoài, dữ liệu request hoặc tham chiếu class-loader hay không.
5. Thiết kế reset sau mỗi lần sử dụng; dùng `remove()` khi kết thúc vòng đời cache hoặc dữ liệu theo task.
6. Nếu value là `AutoCloseable`, đóng đúng lúc trước khi remove.
7. Kiểm tra thread pool reuse, task exception/cancellation và shutdown/redeploy.
8. Kiểm thử trên virtual threads nếu ứng dụng dùng mô hình này; không giả định số ThreadLocal value bằng số carrier thread.
9. Xem xét reentrancy và việc task chuyển thread.
10. Dùng pool có giới hạn cho tài nguyên khan hiếm; không dùng ThreadLocal để thay thế cơ chế pool.

## 14. Tài liệu tham khảo chính thức

- [Java SE 21 API — `ThreadLocal`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/ThreadLocal.html): `get`, `set`, `remove`, `withInitial` và vòng đời giá trị theo thread.
- [Java SE 21 API — `InheritableThreadLocal`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/InheritableThreadLocal.html): cơ chế kế thừa giá trị khi tạo thread và giới hạn của nó.
- [Java SE 21 API — `MessageDigest`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/security/MessageDigest.html): tạo, sử dụng và reset đối tượng digest.
- [Java SE 21 API — `DateTimeFormatter`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/format/DateTimeFormatter.html): formatter immutable và thread-safe.
- [JEP 444 — Virtual Threads](https://openjdk.org/jeps/444): mô hình virtual thread và khuyến nghị về ThreadLocal trong ứng dụng dùng nhiều virtual threads.
