# Hạn chế dữ liệu đối số, chuỗi hóa đối tượng và nguy cơ helper gọi lại mã ứng dụng

Một điểm đo (probe) trong Java agent thường được chèn vào đầu/cuối phương thức để thu thập thời gian, số lần gọi, trạng thái lỗi hoặc thông tin truy vết. Vì probe chạy **ngay trên luồng ứng dụng**, sai lầm trong phần thu thập đối số có thể khiến ứng dụng chậm hơn, làm lộ dữ liệu hoặc thậm chí **chạy thêm mã nghiệp vụ** mà lời gọi gốc không định thực hiện.

Ba nguyên tắc dẫn dắt thiết kế:

1. **Mặc định không lấy giá trị đối số.** Phần lớn phép đo latency/call count chỉ cần định danh method đã được chuẩn hóa, thời điểm, kết quả tổng quát và một số nhãn có số lượng hữu hạn.
2. **Đừng biến đối tượng ứng dụng thành chuỗi trong hot path.** `String.valueOf(value)`, phép nối chuỗi, formatter, logger và các serializer có thể gọi `toString()`, getter hoặc serialization hooks của chính đối tượng ấy.
3. **Helper phải có cơ chế chống tái nhập và tự giới hạn tác động.** Helper gọi logger/client, serializer, thư viện JSON hoặc một phương thức đã được instrument có thể quay lại probe, gây đệ quy, lặp sự kiện, deadlock hay `StackOverflowError`.

Bài này thuộc nhóm **Thiết kế điểm đo** của Java Instrumentation; trọng tâm là cách giữ đúng hành vi của ứng dụng khi thêm observability, không phải cách thu thập càng nhiều dữ liệu càng tốt.

## 1. Đặt đúng ranh giới giữa transformer, probe và helper

Có ba phần dễ bị trộn lẫn:

```text
JVM định nghĩa / retransform một lớp
          |
          v
ClassFileTransformer.transform(...)   [thời điểm tạo/đổi bytecode]
          |
          | chèn lệnh gọi helper vào method body
          v
Class mới được dùng trong ứng dụng
          |
          v
Ứng dụng gọi OrderService.process(request)
          |
          +--> ProbeHelper.enter(methodId, ...)
          |        |
          |        +--> ghi sự kiện rất nhỏ, không gọi lại request
          |        +--> nếu gọi formatter/logger/app code: RỦI RO
          |
          +--> thân process(request) gốc
          |
          +--> ProbeHelper.exit(methodId, duration, outcome)
```

`ClassFileTransformer.transform(...)` được gọi trong chu kỳ class load/redefine/retransform, còn `ProbeHelper.enter/exit` do **bytecode được chèn** gọi trong lúc phương thức ứng dụng thực thi. Cả hai đều có rủi ro class loading và phụ thuộc vào mã ứng dụng, nhưng thời điểm và dữ liệu có sẵn khác nhau.

**Điểm đo chạy cùng ngữ cảnh ứng dụng:** thường cùng thread, stack, class-loader environment và quyền truy cập mà lời gọi gốc có. Chỉ cần helper ném một unchecked exception trước khi thân method chạy, kết quả nghiệp vụ đã có thể đổi. Nếu helper gọi mạng đồng bộ trong một method `synchronized`, thời gian giữ lock bị kéo dài. Nếu helper gọi `request.toString()`, code của `request` đã được thực thi thêm một lần.

| Thành phần | Việc nên làm | Việc cần tránh |
|---|---|---|
| Transformer | Filter class/method chính xác, tạo bytecode hợp lệ, cập nhật frames và bảo đảm helper khả kiến | Load hàng loạt class, gọi serializer/logger ứng dụng trong `transform` |
| Entry probe | Gửi method ID hoặc dữ liệu primitive tối thiểu; chọn sampling/budget sớm | Tạo snapshot của toàn bộ args, gọi getters hoặc `toString` |
| Exit probe | Đo elapsed time, đánh dấu success/error không lộ payload | Serialize return value hoặc exception object |
| Runtime helper | Chống tái nhập, ghi vào sink có giới hạn, không làm thay đổi kết quả ứng dụng | I/O có thể block, giữ reference tới object ứng dụng, gọi lại method đã instrument |
| Exporter ngoài hot path | Batching, policy dữ liệu, giới hạn tài nguyên, retry có kiểm soát | Vô hạn queue, retry đồng bộ trên thread xử lý request |

## 2. “Chỉ log object” thực chất có thể gọi những phương thức nào?

### 2.1. `toString()` là một lời gọi ảo, không phải đọc dữ liệu thụ động

`Object.toString()` có thể được override. Mã bên trong tùy ý: truy cập database, chờ lock, gọi service, sửa trạng thái object, ném exception, hay gọi một method đang được instrument.

```java
// KHÔNG nên dùng trong điểm đo chung cho mọi object:
String message = "argument=" + argument;
String text = String.valueOf(argument);
String pretty = String.format("argument=%s", argument);
```

Với object khác `null`, các cách tạo chuỗi trên có thể gọi `argument.toString()`. `Objects.toString(argument)` cũng có rủi ro tương tự. Việc tạo chuỗi với `%s` hoặc phép nối chuỗi không được làm an toàn chỉ nhờ cú pháp ngắn hơn.

**Đừng chỉ cắt chuỗi sau khi tạo:**

```java
// SAI về kiểm soát side effect: toString đã chạy trước khi cắt.
String shortText = String.valueOf(argument);
shortText = shortText.substring(0, Math.min(shortText.length(), 100));
```

Giới hạn 100 ký tự chỉ giới hạn phần **kết quả được lưu**, không giới hạn công việc của `toString()`: nó có thể đã duyệt cả đồ thị object, mở kết nối hoặc làm phát sinh dữ liệu rất dài trước đó.

### 2.2. Logger và formatter không tự tạo biên an toàn

```java
logger.debug("request={}", request);
logger.info("request=" + request);
System.out.println(request);
```

Các ví dụ trên có khả năng khiến object được format/stringify, dù cách đánh giá là **eager** hay **deferred** tùy thư viện, mức log và cấu hình. Với một logging framework có tham số lười, không được suy rằng object chắc chắn an toàn: formatter vẫn có thể gọi `toString` khi event được render, kể cả ở thread khác. Một số framework có cơ chế bắt lỗi của `toString`, nhưng không bảo đảm chặn được tác dụng phụ trước khi lỗi xảy ra.

Ngay cả code:

```java
if (logger.isDebugEnabled()) {
    logger.debug("request={}", request);
}
```

chỉ tránh được một số chi phí khi debug tắt; **khi debug bật**, việc stringify vẫn có thể chạy app code. Việc chuyển từ concatenation sang placeholder logging cải thiện chi phí trong trường hợp nhất định nhưng **không giải quyết rủi ro side effect hoặc bí mật dữ liệu**.

### 2.3. Các lối gọi gián tiếp thường bị bỏ sót

| Thao tác trong helper | Có thể kích hoạt gì? | Rủi ro |
|---|---|---|
| `String.valueOf(obj)`, `obj.toString()` | Override `toString` của app | Gọi lại business logic, exception, I/O |
| `List.toString()`, `Arrays.deepToString(...)` | Duyệt phần tử và chuỗi hóa phần tử | Vòng tham chiếu, chi phí cao, tiết lộ nested objects |
| JSON mapper serialize object | Getter, field accessor, custom serializer, proxy handling tùy thư viện/cấu hình | Lazy loading, dữ liệu nhạy cảm, truy vấn DB |
| Java `ObjectOutputStream.writeObject(obj)` | Duyệt đồ thị và serialization callbacks | `writeObject`/`writeReplace` chạy app code, tốn bộ nhớ |
| Reflection gọi getter | User-defined getter/proxy interceptors | Không “read-only”: getter có thể gây side effect |
| `obj.hashCode()`/`obj.equals(...)` | Override do ứng dụng viết | HashMap/cache lookup có thể chạy logic tùy ý |
| `String.format("%s", obj)` | Formatter dẫn tới string representation | Tương tự `toString` |
| Throwable formatting / stack trace | Message, stack, cause chain và formatter | Chi phí, log recursion, lộ thông tin, có override |
| Log framework hoặc exporter | Encoder, appender, serializer, network client | Gọi lại code đã instrument, block/throw |

**Phân biệt mức độ chắc chắn:** Java `ObjectOutputStream` có các custom serialization methods được đặc tả. JSON getter discovery phụ thuộc thư viện/cấu hình; không phải mọi mapper đều gọi mọi getter, nhưng helper không được **giả định là không gọi**. `System.identityHashCode(obj)` khác override `obj.hashCode()`: không gọi `hashCode` của class, song vẫn không nên dùng làm ID bền vững hay bí mật; nó chỉ phù hợp với tình huống chẩn đoán có chủ đích.

### 2.4. Java Serialization không phải “bản sao JSON an toàn”

Java Serialization có thể ghi transitively các object tham chiếu từ object gốc, gọi `writeObject` hoặc `writeReplace` theo hợp đồng `Serializable`. Nếu chính helper chủ động serialize một đối số:

- Nó có thể gây **side effect do app-defined serialization hooks**.
- Dữ liệu trong graph có thể chứa token, mật khẩu, thông tin cá nhân và các trường nội bộ không hề cần cho latency measurement.
- Chi phí và kích thước output không thể kiểm soát chỉ bằng cách “cắt số byte sau khi serialize”.
- Không phải object nào cũng `Serializable`; lỗi `NotSerializableException` có thể phá yêu cầu nếu lọt khỏi helper.

Không triển khai generic snapshot bằng `ObjectOutputStream` chỉ vì thư viện Java chuẩn có sẵn. Nếu cần telemetry dạng cấu trúc, nên thiết kế **schema rõ ràng** từ các giá trị đã được phê duyệt, thay vì lưu toàn bộ object graph.

## 3. Chính sách đối số: từ mặc định không lấy đến cho phép có giới hạn

### 3.1. Phân loại dữ liệu trước khi viết bytecode

Để đo thời gian gọi `PaymentService.submit(card, request)`, thông tin thật sự cần có thể chỉ là:

```json
{
  "methodId": 2041,
  "outcome": "SUCCESS",
  "durationMicros": 840,
  "sampled": true
}
```

Đó là schema minh họa, không phải một giao dịch thực. **Không có** số thẻ, account ID, họ tên, email hay `request.toString()`. Dù method signature chứa object giàu dữ liệu, các đối số vẫn không cần đi qua helper.

Một quy tắc thu thập tốt:

1. **Khởi điểm: `NO_ARGUMENT_VALUES`.** Cấu hình mặc định cho mọi method.
2. **Allowlist theo use case:** chỉ method/field đã qua đánh giá và người chịu trách nhiệm dữ liệu phê duyệt mới được lấy giá trị; không allowlist theo package rộng rồi lấy tất cả.
3. **Tối thiểu hóa:** nếu cần “size bucket” thì lấy bucket đã xác định từ dữ liệu đáng tin, không stringify object rồi đo chuỗi.
4. **Nhất quán privacy:** cấm plaintext secret, credential, access token, session cookie, payment details, PII nhạy cảm. Định danh request/tenant có thể là nhãn cardinality cao và nhạy cảm, không dùng tự do.
5. **Ràng buộc đầu ra:** giới hạn số trường, độ dài, số phần tử, byte budget, thời gian, throughput, thời hạn lưu và nơi xuất dữ liệu.
6. **Bằng chứng:** metric `argument_capture_dropped` và lý do `NOT_ALLOWLISTED`, `BUDGET_EXCEEDED`, `POLICY_DENIED` nếu cần, thay vì âm thầm rơi vào stringify fallback.

### 3.2. Bảng quyết định lấy đối số

| Dữ liệu muốn thu | Mặc định | Cách tiếp cận phù hợp nếu có yêu cầu hợp lệ |
|---|---|---|
| Tên/mã method | Cho phép nếu khai báo từ trước | Dùng `methodId`/descriptor đã đăng ký; không resolve reflectively mỗi lần |
| Loại kết quả success/error | Có thể dùng | Enum/counter từ instrumentation path; không serialize exception |
| Duration | Có thể dùng | `System.nanoTime()` và duration; tránh đồng nhất với wall-clock |
| Giá trị `int`/`long` tham số | Không mặc định | Allowlist cụ thể; số primitive cũng có thể là OTP, số thẻ, ID |
| `String` từ ứng dụng | Không mặc định | Chỉ khi field đã được phê duyệt; chặn secret và áp cap **trước khi copy/export** |
| Object tham chiếu bất kỳ | **Không stringify** | Tốt nhất chỉ ghi `null/non-null` khi thật cần, không gọi method của object |
| `Collection` hoặc `Map` | Không gọi `size/toString/iterator` tự động | Chỉ dùng metadata do ứng dụng cung cấp qua API quan sát chuyên biệt, hoặc adapter tin cậy |
| Throwable/return value | Không serialize | Chỉ status/error classification tĩnh; không lấy message/stack tùy tiện |
| Raw JSON/Java serialized graph | Không dùng cho probe tổng quát | Nếu nghiệp vụ bắt buộc, dùng pipeline chuyên biệt ngoài hot path, với chính sách và schema riêng |

Một số việc tưởng là rẻ cũng không an toàn với object bất kỳ. `collection.size()` có thể là lời gọi vào một implementation của ứng dụng. `obj.getClass()` không gọi override `toString`, nhưng tên kiểu vẫn có thể lộ chi tiết nội bộ, việc xử lý metadata cũng có chi phí; nếu không có mục đích đo lường, **đừng lấy chỉ vì có thể lấy được**.

### 3.3. Đặt budget trước công việc đắt đỏ

Một bộ budget mang tính mẫu:

```text
captureMode              = NO_ARGUMENT_VALUES   (mặc định)
maxCapturedArguments     = 0
maxPayloadBytesPerEvent  = 256
maxExportQueueEvents     = 10_000
maxEventsPerSecond       = giới hạn theo deployment
maxCaptureDuration       = giới hạn theo ngân sách độ trễ
onOverflow               = DROP_WITH_COUNTER
```

Các số là **ví dụ thiết kế**, không phải hằng số khuyến nghị cho mọi hệ thống. Trong chế độ `NO_ARGUMENT_VALUES`, `maxCapturedArguments=0` là một giới hạn có ý nghĩa; nếu bật capture chọn lọc, mọi giới hạn khác phải được định nghĩa thực tế và kiểm thử.

**Thứ tự đúng:** chọn lọc method → quyết định sampling → xác định quyền capture → áp budget trước khi đọc/copy dữ liệu → xây event tối thiểu → gửi không block. Không làm ngược là serialize hàng chục MB trước rồi cắt 256 bytes.

### 3.4. Giới hạn giúp hiệu năng nhưng không tự bảo đảm riêng tư

Việc lưu “chỉ 8 ký tự đầu của token” **vẫn là rò rỉ**. Độ dài chuỗi, loại object hoặc hash không khóa cũng có thể lộ thông tin trong vài trường hợp. Không giả định hashing làm ẩn danh: ID ít entropy có thể bị dò ngược. Với dữ liệu nhạy cảm, ưu tiên không thu thập hoặc dùng kỹ thuật mã hóa/HMAC và chính sách quản lý khóa đã được thiết kế riêng.

Các biện pháp đi kèm gồm phân quyền truy cập logs/traces, encryption in transit/at rest, thời hạn giữ, kiểm toán thay đổi cấu hình capture và cơ chế tắt khẩn cấp mà không phải chờ phát hành application code mới.

## 4. Reentrancy: khi helper vô tình gọi lại mã đã instrument

### 4.1. Vòng gọi rất dễ xuất hiện

```text
UserController.handle(req)         [đã được instrument]
  └─ ProbeHelper.enter(...)
       └─ logger.info("req={}", req)
            └─ req.toString()
                 └─ UserService.loadMetadata()   [cũng đã instrument]
                      └─ ProbeHelper.enter(...)
                           └─ logger / serializer / ...
                                └─ ... lặp
```

Hệ quả có thể là:

- Vòng đệ quy cho đến `StackOverflowError`; stack của thread ứng dụng bị sử dụng hết.
- Helper và business code tranh lock, gây deadlock hoặc kéo dài critical section.
- Truy vấn DB, RPC, I/O hoặc lazy load phát sinh chỉ để tạo một log.
- Phép đo bị sai do tự đo chính logger/exporter của agent, làm số lượng sự kiện tăng theo cấp số.
- Class-loading cycle khi helper lần đầu khởi tạo logger/JSON library trong lúc JVM đang define class.
- Một exception ở `toString` hoặc getter tràn qua probe, biến lời gọi vốn thành công thành thất bại.

**Nguy cơ không chỉ do `toString`.** Logger, executor, telemetry exporter, HTTP client, proxy, exception handler, reflection hay phương thức utility đã instrument cũng có thể dẫn đến một vòng gọi ngược.

### 4.2. ThreadLocal guard: hữu ích nhưng có phạm vi

Một cờ `ThreadLocal<Boolean>` đặt trước khi helper làm việc sẽ phát hiện **một lời gọi probe khác trên cùng thread** trong lúc helper đang hoạt động. Với mục tiêu giữ probe không tự instrument chính nó, đây là một chốt chặn đầu tiên.

```text
probe entry
  |
  +-- guard của thread đang active?  -- YES --> bỏ qua reentrant probe
  |
  +-- NO --> đặt guard=true
               |
               v
          chỉ thực hiện logic rất nhỏ
               |
               v
          finally: clear/remove guard
```

Cần nhớ:

- Phải đặt guard **trước** lời gọi có thể kích hoạt mã được instrument.
- Luôn reset bằng `finally`, kể cả khi logic ghi nhận ném exception.
- `remove()` giúp tránh giữ giá trị `ThreadLocal` trong thread pool; không giữ reference tới object ứng dụng trong ThreadLocal.
- Guard chỉ hoạt động với **cùng thread**. Nếu helper đẩy công việc sang thread khác rồi công việc ấy quay lại ứng dụng, cờ của thread ban đầu không đi theo.
- Nếu helper tạo vòng gọi lại ứng dụng trong cùng thread, guard có thể chặn **probe lặp**, nhưng **không chặn chính lời gọi business code không mong muốn**. Nó không sửa side effect của `toString`.
- Khởi tạo guard/helper quá muộn trong bytecode callback có thể gây class loading không mong muốn; hãy quản lý việc load helper và dependencies bằng thiết kế agent.

Do đó **ThreadLocal guard là tuyến phòng thủ thứ hai**, không thay thế quy tắc đầu tiên “đừng gọi object tùy ý”.

## 5. Thí nghiệm Java 17+ chạy độc lập: `toString` gọi ngược vào probe

Chương trình này không cần `javaagent`, vì mục tiêu là cô lập hành vi **runtime helper** trước khi thực sự chèn bytecode. Nó chứng minh:

1. Safe entry nhận object nhưng **không truy vấn nó**.
2. Nhánh unsafe cố chuỗi hóa object; `toString()` lại gọi `ProbeGuard.record` và tạo một **reentrant probe**.
3. Một `toString()` khác ném exception và có thể thay đổi luồng điều khiển.
4. Guard dùng `finally`, nên lần gọi sau lỗi không bị kẹt trong trạng thái `IN_PROBE`.

Tạo đúng hai file cùng thư mục.

### 5.1. File `ProbeGuard.java`

```java
public final class ProbeGuard {
    private static final ThreadLocal<Boolean> IN_PROBE =
            new ThreadLocal<>();

    // Chỉ dùng bộ đếm đơn giản cho thí nghiệm một luồng.
    private static int recorded;
    private static int reentries;

    private ProbeGuard() {
    }

    public static void record(int methodId, Object ignoredArgument) {
        if (Boolean.TRUE.equals(IN_PROBE.get())) {
            reentries++;
            return;
        }

        IN_PROBE.set(Boolean.TRUE);
        try {
            if (methodId >= 0) {
                // Không đụng đến ignoredArgument, không toString/getter.
                recorded++;
            }
        } finally {
            IN_PROBE.remove();
        }
    }

    // CỐ TÌNH KHÔNG AN TOÀN: chỉ dùng để thấy lỗi trong demo.
    public static void unsafeInspect(Object argument) {
        if (Boolean.TRUE.equals(IN_PROBE.get())) {
            reentries++;
            return;
        }

        IN_PROBE.set(Boolean.TRUE);
        try {
            String text = String.valueOf(argument);
            if (!text.isEmpty()) {
                recorded++;
            }
        } finally {
            IN_PROBE.remove();
        }
    }

    public static String counters() {
        return "recorded=" + recorded + ", reentries=" + reentries;
    }
}
```

`record` là đường **an toàn hơn**: quyết định dựa vào `methodId`, không gọi method của `ignoredArgument`. Tham số object trong demo chỉ để so sánh hai chiến lược. Trong bytecode instrumentation thực, nếu không cần đối số, **đừng truyền reference ấy vào helper ngay từ đầu**; giảm chi phí, giảm nguy cơ giữ reference và giảm diện tấn công.

`unsafeInspect` minh họa điều **không nên triển khai**: `String.valueOf(argument)` có thể gọi `toString()` do ứng dụng override. Guard ngăn lặp việc ghi event trên cùng thread; nó không làm cho việc stringify trở thành thao tác an toàn.

Hai biến `recorded`/`reentries` không thread-safe; ví dụ chỉ chạy một luồng. Đừng sao chép bộ đếm này sang production nhiều thread: dùng `LongAdder`/counter thích hợp và thiết kế chính sách sampling, exporter, failure handling.

### 5.2. File `ProbeDemo.java`

```java
public final class ProbeDemo {
    static final class ReentrantArgument {
        @Override
        public String toString() {
            // Một ứng dụng có thể vô tình gọi method đã instrument ở đây.
            ProbeGuard.record(900, this);
            return "rendered";
        }
    }

    static final class ThrowingArgument {
        @Override
        public String toString() {
            throw new IllegalStateException("toString failed");
        }
    }

    public static void main(String[] args) {
        Object value = new ReentrantArgument();

        ProbeGuard.record(101, value);
        System.out.println("SAFE " + ProbeGuard.counters());

        ProbeGuard.unsafeInspect(value);
        System.out.println("UNSAFE " + ProbeGuard.counters());

        try {
            ProbeGuard.unsafeInspect(new ThrowingArgument());
        } catch (IllegalStateException e) {
            System.out.println("UNSAFE_ERROR " + e.getMessage());
        }

        ProbeGuard.record(102, value);
        System.out.println("AFTER " + ProbeGuard.counters());
    }
}
```

### 5.3. Biên dịch và chạy

Dùng JDK 17 trở lên:

```shell
javac ProbeGuard.java ProbeDemo.java
java ProbeDemo
```

**Stdout chính xác với hai file trên:**

```text
SAFE recorded=1, reentries=0
UNSAFE recorded=2, reentries=1
UNSAFE_ERROR toString failed
AFTER recorded=3, reentries=1
```

Giải thích từng bước:

- `SAFE`: `record(101, value)` chỉ tăng một counter. `ReentrantArgument.toString()` **không** được gọi, nên `reentries=0`.
- `UNSAFE`: `unsafeInspect(value)` gọi `String.valueOf(value)` → `ReentrantArgument.toString()` → `ProbeGuard.record(900, this)`. Vì guard đang active trên thread đó, lời gọi lặp chỉ tăng `reentries` rồi return; sau đó `unsafeInspect` tăng `recorded` lên 2.
- `UNSAFE_ERROR`: `ThrowingArgument.toString()` ném `IllegalStateException`. Vì `unsafeInspect` không catch, lỗi đi ra ngoài tới `try/catch` trong `main`. **Đây là bằng chứng helper không an toàn có thể thay đổi luồng thực thi ứng dụng.**
- `AFTER`: `finally` đã remove guard dù có exception, nên `record(102, value)` lại được chấp nhận; tổng `recorded=3`.

**Không dùng `unsafeInspect` làm production probe.** Nhánh này cố tình có lỗi để giáo dục. Ngoài thí nghiệm, nếu lỗi của helper lọt ra từ bytecode chèn vào method thật, nó có thể cắt ngang nghiệp vụ hoặc che exception gốc.

### 5.4. Vì sao ví dụ không dùng javaagent?

Ví dụ độc lập này kiểm thử **cơ chế reentrancy trong helper** mà không cần thư viện tạo bytecode hay manifest. Một agent thực cần thêm `premain`/`agentmain`, `Instrumentation`, transformer hợp lệ, class-loader visibility và mã chèn lời gọi `ProbeGuard.record`. Những phần đó là một bài toán riêng; không nên biến ví dụ nhỏ thành agent phức tạp chỉ để chứng minh hành vi của `toString`.

## 6. Thiết kế helper production: không throw, không block, không gọi lại app code

### 6.1. Interface tối thiểu tốt hơn nhận `Object[] args`

Nên ưu tiên một hợp đồng như:

```java
// Mẫu interface thiết kế (không phải chương trình chạy độc lập):
void onEnter(int methodId);
void onExit(int methodId, long durationNanos, int outcomeCode);
```

Ở đây `methodId` là ID từ danh sách method đã instrument, `durationNanos` được tính bằng hiệu của hai lần `System.nanoTime()` trên cùng đo lường, và `outcomeCode` là nhãn tĩnh như success/error. Không có raw args, return object, exception object, `Map<String,Object>` hay serializer.

Điều này giúp:

- Hạn chế memory retention và allocation.
- Kiểm soát số lượng label; tránh metrics cardinality nổ theo user IDs.
- Không mở rộng surface cho `toString`/getter/serialization hooks.
- Cố định kiểu dữ liệu để bytecode injection dễ kiểm tra locals/stack maps.
- Độc lập với class loader của model/domain object.

Nếu một phép đo thực sự cần field nghiệp vụ (ví dụ loại giao dịch), hãy cung cấp nó qua **adapter tường minh do ứng dụng kiểm soát** với schema đã được duyệt. Tránh một “generic argument exporter” có quyền nhìn/serialize mọi object.

### 6.2. Reentrancy guard nên được kết hợp với exclude list

Khi agent chọn lớp để instrument, thường cần **loại trừ**:

- Bản thân helper, các class thực thi sink/exporter của agent.
- Logging/serialization/network libraries mà helper dùng, nếu việc instrument chúng gây vòng gọi hoặc chi phí không chấp nhận được.
- Các lớp rất nhạy cảm ở giai đoạn bootstrap/class loading khi agent chưa hoàn tất khởi tạo.
- Runtime/framework infrastructure mà instrumentation không có đủ kiểm chứng tương thích.

Exclude list và guard là hai lớp phòng thủ khác nhau: exclude không bảo đảm không có lối gọi gián tiếp khác; guard cùng thread không chặn task phát sinh ở thread khác. Thiết kế tốt giảm số dependency của helper thay vì chỉ liên tục mở rộng exclude list khi phát hiện recursion mới.

### 6.3. Bounded, nonblocking sink

Trong method hot path, helper nên tạo một event nhỏ và cố đẩy vào ring buffer/queue có giới hạn. Nếu queue đầy, chấp nhận **drop event với counter** theo chính sách quan sát, thay vì bắt request chờ network hoặc đưa toàn bộ event vào bộ nhớ không giới hạn.

```text
Application thread
    |
    v
cheap guard + policy + sampling
    |
    v
small immutable event (methodId, duration, outcome)
    |
    v
bounded queue  --full--> drop event + increment drop counter
    |
    v
exporter thread -> batching/encoding/transport
```

Ngay cả khi exporter chạy thread riêng, nó vẫn phải tránh gọi code ứng dụng tùy ý (ví dụ log một object gốc bị giữ trong queue). **Chỉ chuyển primitive/snapshot được phép**, không chuyển raw object reference rồi stringify muộn: rủi ro app code vẫn còn và còn kéo dài thời gian sống của object.

### 6.4. Đảm bảo không thay đổi exception gốc

Ví dụ sơ đồ chèn probe ở entry/exit:

```text
start = monotonic time
try:
    emit_enter(methodId)              // phải rất nhẹ và an toàn
    run original method body          // không sửa semantics
finally:
    emit_exit(methodId, elapsed, ...) // không được che lỗi của body
```

Đây là **pseudocode**, không phải Java source có thể biên dịch hoặc công thức bytecode áp thẳng cho mọi method. Cụ thể:

- Nếu `emit_enter` ném exception, thân method gốc có thể chưa chạy.
- Nếu thân method ném exception nhưng `emit_exit` cũng ném, exception helper có thể **che** exception gốc.
- Method constructor có `this` chưa khởi tạo trước `invokespecial` tới constructor cha; không tùy tiện chèn lệnh đọc `this` ở đoạn verifier không cho phép.
- Thao tác trong `synchronized`/monitor, `try-with-resources`, `finally` hoặc exceptional control flow phải được biến đổi với bytecode frames/exception handlers hợp lệ.
- Tránh dùng `catch(Throwable)` rộng một cách thiếu suy xét để giấu `OutOfMemoryError` và các lỗi JVM nghiêm trọng. Thiết kế helper có ít điểm lỗi, xử lý lỗi có thể phục hồi và cho phép chính sách vận hành quyết định khi gặp lỗi không phục hồi.

## 7. Nguy cơ ngoài recursion: class loading, lock, memory, cardinality

### 7.1. Class loading trong helper

Lần gọi probe đầu tiên có thể làm JVM nạp/khởi tạo helper và các dependency. Nếu việc đó xảy ra trong giai đoạn class loading, constructor, method static initializer hay code dưới lock, lỗi rất khó tái hiện:

- `NoClassDefFoundError`/`LinkageError` nếu loader của ứng dụng không thấy helper.
- `ExceptionInInitializerError` nếu class initialization của helper phụ thuộc cấu hình/logger chưa sẵn sàng.
- Đệ quy class loading khi resolver/logger lại dùng class đang được transform.
- Deadlock do lock trên class initialization, logger hay thread-safety primitive.

Cần thiết kế chỗ đặt helper: class loader nào sẽ resolve lời gọi từ bytecode, có phải dùng `appendToBootstrapClassLoaderSearch` hay helper nằm trong classpath/module phù hợp không, và bootstrap helper có dependency nào. Dùng bootstrap append có giới hạn/đánh đổi về linkage và trust; không tự động nhét một thư viện JSON/logging lớn vào bootstrap loader để tiện gọi từ mọi nơi.

### 7.2. Gọi app code có thể xảy ra dù không stringify

`equals`/`hashCode` khi dùng object làm key trong map, getter khi xây record telemetry, proxy interceptors, lazy-load ORM, custom collection iteration, validation frameworks và reflection đều có thể gọi ứng dụng. Khi gắn method probe vào các utility đó, một helper tưởng là “đọc dữ liệu” có thể tạo thêm method invocations.

Ví dụ anti-pattern:

```java
// Có thể gọi overridden hashCode()/equals() của argument:
cache.put(argument, metadata);

// Có thể gọi getter, proxy interceptor hoặc custom logic:
String customer = request.getCustomer().getName();

// Có thể phát sinh lazy loading và duyệt nhiều object:
String json = objectMapper.writeValueAsString(request);
```

Các đoạn trên **không tự đứng độc lập** (phụ thuộc `cache`, `metadata`, `request`, `objectMapper`), chỉ minh họa những thao tác cần tránh trong generic probe. Không dùng bản copy những đoạn đó để “diagnostic nhanh” trong một agent đang chạy production.

### 7.3. Giữ object reference làm thay đổi lifetime

Nếu queue/singleton của helper giữ `Object[] args` hoặc một `Map` chứa request object, GC có thể không thu hồi graph liên quan khi request đã kết thúc. Một vài hàng nghìn event có thể pin những graph rất lớn, class loader hoặc vùng nhớ chứa dữ liệu nhạy cảm.

Giải pháp là đưa vào queue **immutable event nhỏ với primitive/enum hoặc dữ liệu đã được phê duyệt và sao chép có giới hạn**. Không chuyển raw `Throwable` hoặc `request` sang exporter để “xử lý sau”: đó vẫn là data retention và deferred app-code execution.

### 7.4. Metrics cardinality và phí lưu trữ

`methodId` có số lượng hữu hạn; `requestId`, `email`, `orderId` và chuỗi từ `toString` có thể tạo label riêng cho từng request. Khi nhiều label biến thành metric dimensions, hệ thống thời gian thực có thể tăng bộ nhớ, chi phí và độ trễ ngay cả khi bản thân từng event nhỏ.

Chọn nhãn có tập giá trị **hữu hạn và kiểm soát được**, như feature, outcome code, method group hoặc percentile bucket. ID có cardinality cao nên đi vào trace/log được bảo vệ khi thực sự cần, không phải nhãn metric tổng quát.

## 8. Bảng quyết định cho một yêu cầu đo cụ thể

| Mong muốn | Có cần truyền object vào helper? | Phương án tối thiểu | Rủi ro còn lại |
|---|---|---|---|
| Đếm số lượt gọi method | Không | `methodId` + counter | Overhead/tái nhập nếu counter path phức tạp |
| Đo latency | Không | `methodId` + elapsed nanos | Clock overhead, stack/locals khi chèn bytecode |
| Tỷ lệ lỗi | Không cần raw Throwable | `methodId` + enum outcome | Phân loại cần chính sách rõ |
| Biết một tham số có `null` không | Không cần giữ object | Bytecode kiểm tra null và truyền cờ | Metadata có thể vẫn nhạy cảm trong ngữ cảnh đặc biệt |
| Ước lượng kích thước payload | Không nên serialize object | Dùng size do ứng dụng công bố hoặc adapter có hợp đồng | Adapter có thể vẫn gây side effect nếu gọi trong hot path |
| Log request JSON | **Không phù hợp với generic probe** | Thiết kế opt-in ở tầng ứng dụng, schema và redaction, có ngân sách | Rủi ro privacy, getter/lazy loading, hiệu năng |
| Điều tra một lỗi cụ thể | Chỉ khi được phê duyệt rõ | Enable tạm thời có phạm vi, sampling, TTL, audit | Dữ liệu có thể chứa secret, không thể chỉ dựa vào truncation |
| Debug type của argument | Thường không | Gắn type category do caller khai báo hoặc metadata tĩnh | Runtime type names và class loaders có thể nhạy cảm |

## 9. Kiểm thử bắt buộc trước khi triển khai agent

### 9.1. Correctness tests

- **Không thay return value:** method trả kết quả giống trước/sau instrumentation.
- **Không thay exception:** phương thức ném cùng loại/cause mong muốn, helper không thay thế stack/exception từ app.
- **Không gọi `toString`/getters ngoài ý muốn:** dùng object test có `toString` đếm lượt gọi hoặc cố ý ném exception; probe an toàn phải không làm tăng lượt.
- **Không tái nhập:** helper có fake exporter/logger gọi lại một method đã được instrument; guard và exclude policy ngăn vòng lặp.
- **Constructor/static initialization:** thử các method có `this` chưa khởi tạo, static init và class loader khác; bytecode phải qua verifier.
- **Không leak object:** kiểm thử vòng đời request và class loader trong điều kiện stress; các queue không giữ tham chiếu tùy ý.

### 9.2. Performance và resilience tests

- Load cao trên method ngắn để thấy probe overhead, allocation rate và p99/p999 latency.
- Queue đầy/ exporter không phản hồi: request không được bị block vô hạn; drop counters tăng.
- Multi-thread, executor pools, virtual threads nếu runtime có: guard chỉ theo thread, metrics/counters thread-safe.
- Agent helper chưa initialize, logger lỗi, exporter ném exception hoặc API không khả dụng: báo lỗi nội bộ đúng và giữ chính sách app.
- Log/trace disabled: không tự động tạo chuỗi đối số trước khi kiểm tra policy.
- Repeated retransformation: không nhân đôi probe hoặc tạo nested wrappers mà không kiểm soát.

Một ma trận lỗi hữu ích:

| Test | Kỳ vọng |
|---|---|
| `toString` ném exception | Probe mặc định không gọi nó, business code không thấy lỗi mới |
| `toString` gọi lại instrumented method | Không xảy ra vì không stringify; nếu helper khác vẫn gây vòng, guard chặn reentrant probe |
| Queue full | Event bị drop theo policy, không giữ object và không block |
| Request chứa credential | Telemetry không có plaintext credential |
| Custom collection `size()` có side effect | Generic probe không tự gọi `size()` |
| JSON mapper tự gọi getter | Không dùng generic mapper trong hot path |
| Instrumented method ném lỗi gốc | Probe không mask exception gốc |
| Hai class loader có cùng class name | Helper resolution, filters và provenance đúng từng loader |

### 9.3. Monitoring cho chính điểm đo

Theo dõi cả **hệ thống thu thập**, không chỉ app:

```text
probe_events_accepted_total{feature,method_group}
probe_events_dropped_total{reason}
probe_reentrancy_suppressed_total{feature}
probe_capture_denied_total{policy}
probe_helper_errors_total{kind}
probe_queue_depth
probe_export_failures_total
```

Các tên metric là gợi ý, không phải API chuẩn. Tránh label như raw `argument`, `toString`, user ID, exception message hoặc full class name động. Nếu một metrics exporter tự dùng agent-instrumented method, phải kiểm tra vòng lặp của chính pipeline observability.

## 10. Những hiểu nhầm thường gặp

1. **“`toString` chỉ là đọc trạng thái, không thể làm đổi nghiệp vụ.”** Sai: là lời gọi ảo có thể chứa logic tùy ý.
2. **“Giới hạn output 200 ký tự là giới hạn chi phí stringify.”** Sai: `toString`/serializer đã làm việc trước khi cắt.
3. **“Logging placeholder `{}` luôn an toàn.”** Sai: formatter có thể gọi `toString` khi render.
4. **“Dùng JSON mapper là đọc field thụ động.”** Sai với nhiều serializer/config: getter, custom adapter và proxy có thể được gọi.
5. **“Java Serialization chỉ ghi bytes, không gọi mã object.”** Sai: `writeObject`/`writeReplace` có thể chạy.
6. **“Guard ThreadLocal ngăn mọi loại recursion.”** Sai: chỉ ngăn một số vòng trên cùng thread và không ngăn side effect của lời gọi app code ban đầu.
7. **“Chuyển object sang exporter thread là an toàn hơn.”** Sai: vẫn giữ reference, chuyển rủi ro stringify sang thread khác, và có thể gây leakage/retention.
8. **“Đối số primitive thì mặc định vô hại.”** Sai: `long` có thể là user ID, token hoặc thông tin nhạy cảm.
9. **“Lấy nguyên exception cho tiện debug.”** Sai: giữ `Throwable` trong queue có thể pin graph và lộ message/stack.
10. **“Nếu helper thất bại thì JVM tự bỏ qua như `ClassFileTransformer`.”** Sai: exception từ **runtime helper được chèn vào method** là exception runtime bình thường nếu không được xử lý.
11. **“Class có trong system loader nên mọi class loader đều gọi được helper.”** Sai: helper visibility/module access phải khớp bytecode và loader thật.
12. **“Sampling sau khi stringify sẽ giảm đáng kể overhead.”** Sai: phần nguy hiểm đã chạy trước khi quyết định sample.
13. **“Instrument toàn bộ logging/network dependencies để được nhiều telemetry hơn.”** Có thể tự tạo vòng lặp. Chọn exclude scope và guard rõ ràng.
14. **“Không có dữ liệu đối số nghĩa là probe vô dụng.”** Sai: latency, count, error-rate và tracing đa số vẫn có giá trị từ method ID/timing/status.

## 11. Câu hỏi tự kiểm tra

1. **Tại sao `String.valueOf(request)` không phải thao tác “chỉ đọc”?** Vì object có thể override `toString()` để chạy logic ứng dụng, I/O, side effect hoặc ném exception.
2. **Nếu stringify trả chuỗi dài một triệu ký tự rồi mới cắt 100 ký tự, có kiểm soát được chi phí và privacy chưa?** Chưa. Toàn bộ logic stringify/duyệt object đã chạy trước khi cắt.
3. **Vì sao không nên đưa `Object[] args` vào queue rồi xử lý sau?** Nó giữ reference/lifetime của object, có thể chứa dữ liệu nhạy cảm và khiến exporter thực thi code ứng dụng muộn hơn.
4. **Một `ThreadLocal` guard đảm bảo không có vòng gọi gián tiếp ở thread khác không?** Không. Nó chỉ theo trạng thái của thread hiện tại.
5. **Nếu helper gọi logger rồi logger gọi method đã instrument, có thể xảy ra điều gì?** Reentrant probe, đệ quy, số liệu tăng giả, chi phí cao hoặc deadlock.
6. **Khi method chỉ cần đo latency, tham số helper tốt nhất là gì?** Method ID, duration và outcome, không cần raw args hay return object.
7. **Một `Collection.size()` trên object bất kỳ có luôn an toàn?** Không. Implementation tùy ý có thể gọi mã app, có side effect hoặc chi phí cao.
8. **Tại sao không nên dùng raw user ID làm metric label?** Cardinality cao, có thể nhạy cảm, tăng chi phí lưu trữ và ảnh hưởng hiệu năng.
9. **Nếu method gốc đang ném exception và exit helper cũng ném, chuyện gì có thể xảy ra?** Exception của helper có thể che lỗi gốc và thay đổi hành vi quan sát được.
10. **Trong demo, `reentries` tăng lúc nào?** Khi `unsafeInspect` stringify `ReentrantArgument`, và `toString()` gọi `record` trong khi guard đang active.
11. **Tại sao `finally` quan trọng với reentrancy guard?** Nó xóa trạng thái active sau cả đường thành công và đường exception, tránh “kẹt” trạng thái ở thread pool.
12. **Có nên dựa vào số ký tự giới hạn để xác nhận dữ liệu đã ẩn danh?** Không. Redaction/privacy cần chính sách dữ liệu, không chỉ độ dài.
13. **Agent khởi tạo helper ở thời điểm nào cần chú ý?** Khi helper được load/initialized và đang class load/constructor/under lock, vì dependency có thể gây linkage/cycle/deadlock.
14. **Biện pháp đầu tiên để tránh nguy cơ `toString` là gì?** **Không truyền và không stringify đối số** nếu phép đo không thực sự cần chúng.

## 12. Tài liệu tham khảo đáng tin cậy

- [Java SE 21 — `java.lang.Object`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Object.html): hợp đồng và khả năng override `toString()`, `equals()`, `hashCode()`.
- [Java SE 21 — `java.lang.ThreadLocal`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/ThreadLocal.html): trạng thái theo thread và `remove()`.
- [Java SE 21 — `java.io.Serializable`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/io/Serializable.html): custom `writeObject`, `writeReplace` và hợp đồng serialization.
- [Java SE 21 — `java.io.ObjectOutputStream`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/io/ObjectOutputStream.html): việc ghi object graph và các giới hạn của Java Serialization.
- [Java SE 21 — `java.lang.instrument`](https://docs.oracle.com/en/java/javase/21/docs/api/java.instrument/java/lang/instrument/package-summary.html): mô hình Java agent và việc instrument bytecode.
- [Java SE 21 — `ClassFileTransformer`](https://docs.oracle.com/en/java/javase/21/docs/api/java.instrument/java/lang/instrument/ClassFileTransformer.html): callback transform ở thời điểm class load/redefine/retransform.

**Ghi nhớ:** probe tốt là probe **không biến object ứng dụng thành một đồ thị dữ liệu cần log**. Hãy đo bằng định danh tĩnh, primitive metadata và budget rõ ràng; tránh `toString`/serializer/getters trong hot path, dùng reentrancy guard để giảm vòng lặp và không bao giờ coi guard là giấy phép gọi lại mã ứng dụng. Quan sát được hệ thống mà không thay đổi kết quả của nó mới là tiêu chuẩn quan trọng nhất.