# Refactor một module legacy sang Pattern Matching trong Java 21

## 1. Mục tiêu thực hành tổng hợp

Một module legacy thường có chuỗi `if/else if` với `instanceof`, cast thủ công, nhiều điều kiện lồng nhau, các getter có side effect và fallback cho dữ liệu không hợp lệ. Java 21 cho phép viết lại logic điều phối bằng **type patterns**, **record patterns**, **guard `when`** và **switch expressions**. Mục tiêu không phải chỉ rút ngắn code, mà là **giữ nguyên hành vi quan sát được trong khi tăng tính rõ ràng và an toàn kiểu**.

Bài tập sử dụng một module định tuyến thông điệp có các dữ liệu:

- `TextMessage`: chứa nội dung, getter `readBody()` đếm số lần đọc.
- `CountMessage`: chứa số nguyên, có nhánh cho số âm.
- `PacketMessage`: có header/payload, mỗi getter có bộ đếm.
- `Header`: record nội bộ gồm `channel` và `priority`, có ngưỡng high = 10.
- `Heartbeat`: loại thông điệp chỉ báo tín hiệu.
- `ExplodingMessage`: cố ý ném ngoại lệ để test khả năng bảo toàn lỗi.
- `null` và kiểu ngoài module: có fallback tường minh.

Chúng ta sẽ so sánh `legacyRoute(Object)` với `modernRoute(Object)`, dùng 21 input và đối chiếu **giá trị trả về, exception, số lần gọi getter**. Ngoài ra có một phản ví dụ `when` viết sai làm getter được gọi ba lần, dù chuỗi kết quả nhìn có vẻ đúng.

**Phạm vi:** "module" là nhóm chức năng trong ứng dụng, không nhất thiết là Java Platform Module System/`module-info.java`. Ví dụ tổ chức một file Java để chạy dễ dàng, sau đó giải thích cách áp dụng cho Maven/Gradle module đa class và CI.

**Phiên bản:** Pattern matching với `instanceof` chuẩn từ Java 16; record patterns (JEP 440) và pattern matching for `switch` (JEP 441) chuẩn từ **Java 21**. Không cần `--enable-preview` khi biên dịch với `javac --release 21`.

### Kết quả cần đạt

Sau bài học, bạn biết cách kiểm kê hợp đồng cũ; chọn chỗ refactor phù hợp; giữ public POJO API khi cần; viết `switch` expression có `when`, `case null` và `default` đúng; kiểm thử lỗi, thứ tự nhánh, side effects và độ tương thích; triển khai từng bước có rollback.

## 2. Trước khi refactor: kiểm kê hợp đồng và rủi ro

Đừng bắt đầu bằng lệnh tự động "Convert to switch" trên cả module. Hãy liệt kê các thành phần mà caller thực sự quan sát:

| Thành phần | Câu hỏi cần trả lời | Hậu quả có thể xảy ra |
| --- | --- | --- |
| Public method signature | Method nhận/trả kiểu gì? Có checked exceptions không? | Source/binary compatibility |
| Public DTO/POJO | Getter, setter, constructor, subclass, JSON/JPA binding? | Đổi sang record có thể phá API |
| Thứ tự nhánh | Khi hai điều kiện cùng đúng, nhánh nào được chọn? | Kết quả nghiệp vụ thay đổi |
| Selector `null` | Trả fallback, ném NPE hay bỏ qua? | Khác semantics của `switch` |
| Nested `null` | Object trung gian null hay component null? | Pattern không match hoặc guard sai |
| Unknown types | `else`/`default` trả gì? Có plugin extensibility? | Thất bại với subclass/extension |
| Exception | Loại, thời điểm, cause, message cần giữ? | Caller và logging đổi hành vi |
| Side effect | Getter, audit, metrics, I/O, mutation chạy bao lần? | Duplicate event hoặc chậm bất ngờ |
| JDK/toolchain | Source/release và runtime production bao nhiêu? | Build pass ở IDE nhưng deploy fail |
| Tests/monitoring | Có baseline, CI, integration tests, rollback? | Regression không được phát hiện |

Một module thực tế có thể có:

```text
message-module/
  src/main/java/com/example/message/
    MessageRouter.java
    TextMessage.java
    CountMessage.java
    PacketMessage.java
    Heartbeat.java
  src/test/java/com/example/message/
    MessageRouterContractTest.java
    MessageRouterIntegrationTest.java
  pom.xml  hoặc build.gradle(.kts)
```

Đây chỉ là layout minh họa; không cần tạo thư mục này để chạy file ở mục 8. Với dự án đã có kiến trúc riêng, giữ convention hiện tại.

### 2.1. Không đổi public DTO đồng thời với refactor dispatcher

Pattern matching **không yêu cầu các class đầu vào phải là record**. `case TextMessage message` match POJO class thông thường. Trong ví dụ, `TextMessage`/`CountMessage`/`PacketMessage` vẫn là class final. Chỉ `Header` là record carrier nội bộ để thực hành record pattern.

Nếu chuyển công khai một class mutable sang record, bạn còn phải đánh giá constructor, getters, setters, inheritance, reflection, framework mapping, serialized schema, identity và thread-safety. Đó là **thay đổi mô hình/API**, không tự được coi là refactor cú pháp thuần.

## 3. Ghi baseline trước khi sửa mã

Với module mẫu, hợp đồng cũ là:

| Trường hợp | Kết quả được yêu cầu | Số lượt đọc accessor |
| --- | --- | --- |
| `TextMessage(" Java ")` | `text:Java` | 1 |
| `TextMessage(" \\t ")` | `text:<blank>` | 1 |
| `TextMessage(null)` | `text:<null>` | 1 |
| `CountMessage(-1)` | `count:negative` | 0 |
| `CountMessage(0)` | `count:0` | 0 |
| `PacketMessage(Header(" api ",10)," body ")` | `packet:high:api:body` | 2 |
| `PacketMessage(Header("evt",9),"hello")` | `packet:normal:evt:hello` | 2 |
| `PacketMessage(Header(null,10),"body")` | `packet:invalid-channel` | 2 |
| `PacketMessage(null,"body")` | `packet:missing-header` | 2 |
| `ExplodingMessage` | `IllegalStateException("corrupted payload")` | 1 |
| `Heartbeat` | `heartbeat` | 0 |
| Unknown type | `unsupported` | 0 |
| Selector `null` | `null-input` | 0 |

Trong chương trình thật, hãy bổ sung HTTP response, audit records, transaction boundaries hoặc error codes nếu chúng thuộc hợp đồng của module. Không chỉ chụp một screenshot UI làm baseline.

**Quan trọng:** Một refactor bảo toàn behavior cần so ít nhất ba mặt: *giá trị*, *ngoại lệ*, *side effects*. Có thể phải kiểm tra cả **thứ tự** các side effects, không chỉ số lượng.

### 3.1. Chốt các ranh giới đầu vào

Ở ví dụ có các ngưỡng: priority 9/10, count -1/0, chuỗi null/blank/nonblank, payload null/empty và unknown Object. Đưa ranh giới vào test trước khi thay code. Với chuỗi Unicode, `strip()` và `trim()` không luôn tương đương; không đổi phương thức xử lý whitespace mà không có yêu cầu.

## 4. Mã cũ: `instanceof` và cast thủ công

Đây là dispatcher theo phong cách legacy. Những class/helper được định nghĩa hoàn chỉnh ở mục 8:

```java
static String legacyRoute(Object input) {
    if (input == null) return "null-input";

    if (input instanceof TextMessage) {
        TextMessage message = (TextMessage) input;
        String body = message.readBody();
        return textLabel(body);
    }
    if (input instanceof CountMessage) {
        CountMessage count = (CountMessage) input;
        if (count.count() < 0) return "count:negative";
        return "count:" + count.count();
    }
    if (input instanceof PacketMessage) {
        PacketMessage message = (PacketMessage) input;
        Header header = message.header();
        String payload = message.payload();
        return legacyPacket(header, payload);
    }
    if (input instanceof Heartbeat) return "heartbeat";
    if (input instanceof ExplodingMessage) {
        ExplodingMessage message = (ExplodingMessage) input;
        return message.read();
    }
    return "unsupported";
}
```

Lưu ý các tính chất bắt buộc được bảo toàn:

- Null được xử lý **trước** các kiểm tra kiểu.
- `readBody()` chạy đúng một lần cho nhánh Text.
- `header()` và `payload()` chạy đúng một lần mỗi getter cho Packet.
- Với Count âm, kết quả khác Count không âm.
- Getter của ExplodingMessage ném lỗi và lỗi được lan truyền, không bị đổi thành fallback.
- Các input không thuộc các class đã liệt kê trả `unsupported`.

Nếu code legacy có cast trực tiếp **không được bảo vệ** bởi `instanceof`, nó có thể ném `ClassCastException` hoặc `NullPointerException`. Thay cast đó bằng `instanceof ... ? value : fallback` sẽ đổi behavior; cần phê duyệt riêng nếu muốn thay hợp đồng.

### 4.1. Giai đoạn an toàn đầu tiên: type pattern `instanceof`

Trước khi dùng switch mới, có thể chỉ viết lại nhánh Text:

```java
if (input instanceof TextMessage message) {
    String body = message.readBody();
    return textLabel(body);
}
```

Cách này bỏ cast thủ công nhưng giữ cấu trúc `if`, thứ tự và số lần getter. Java 16+ đã hỗ trợ. Trong dự án còn target Java 17, đây có thể là bước tiến nhỏ phù hợp mà chưa bắt buộc nâng source level lên 21.

## 5. Bản Java 21: chuyển dispatch sang pattern switch

Khi baseline đã có, dispatcher có thể viết:

```java
static String modernRoute(Object input) {
    return switch (input) {
        case null -> "null-input";
        case TextMessage message -> textLabel(message.readBody());
        case CountMessage count when count.count() < 0 ->
                "count:negative";
        case CountMessage count -> "count:" + count.count();
        case PacketMessage message ->
                patternPacket(message.header(), message.payload());
        case Heartbeat h -> "heartbeat";
        case ExplodingMessage message -> message.read();
        default -> "unsupported";
    };
}
```

**Đây là switch expression**, vì toàn bộ switch tạo ra `String` để return. Dấu `->` là dạng thân rule; pattern nằm ở nhãn `case Type variable`.

Cách ánh xạ semantic:

| Legacy | Java 21 | Điều phải giữ |
| --- | --- | --- |
| `input == null` | `case null` | Cùng fallback |
| `instanceof TextMessage` + cast | `case TextMessage message` | Cùng getter/cùng output |
| `if (count.count() < 0)` | `when count.count() < 0` | Cùng ưu tiên nhánh âm |
| `else/count >= 0` | `case CountMessage count` | Nhánh không guard đứng sau |
| `PacketMessage` + nested ifs | `case PacketMessage message` + helper record pattern | Giữ lượt đọc/exception |
| `Heartbeat` | `case Heartbeat h` | Đúng loại input |
| `ExplodingMessage.read()` | `case ExplodingMessage message -> message.read()` | Exception vẫn lan truyền |
| Final `else` | `default` | Unknown input còn được hỗ trợ |

Nếu bỏ `case null` vì tưởng `default` xử lý null, có thể xuất hiện NPE. Nếu đặt `case CountMessage count` không guard trước case có `when`, compiler có thể báo **dominance**. Nếu dùng interface/class cha chung, đặt subtype cụ thể trước supertype.

### 5.1. Tại sao không tự biến interface legacy thành sealed?

Nếu ứng dụng cho plugin bên ngoài triển khai interface hoặc kế thừa class công khai, đổi nó thành `sealed` có thể phá extensibility. Tính exhaustive của sealed hierarchy rất hữu ích **khi tập subtype thực sự đóng**, nhưng nó không phải yêu cầu bắt buộc để dùng pattern matching. Ở ví dụ, selector là `Object` và có `default` để giữ unknown type fallback.

## 6. Record pattern bên trong module: refactor Header

Giả sử cấu trúc header là record nội bộ:

```java
record Header(String channel, int priority) {}
```

Bản xử lý cũ:

```java
static String legacyPacket(Header header, String payload) {
    if (header == null) return "packet:missing-header";
    String channel = header.channel();
    int priority = header.priority();

    if (channel == null || channel.isBlank()) {
        return "packet:invalid-channel";
    }
    if (priority >= 10) {
        return "packet:high:" + channel.strip()
                + ":" + payloadLabel(payload);
    }
    return "packet:normal:" + channel.strip()
            + ":" + payloadLabel(payload);
}
```

Bản mới dùng deconstruction + `when`:

```java
static String patternPacket(Header header, String payload) {
    return switch (header) {
        case Header(var channel, var priority)
                when channel == null || channel.isBlank() ->
                "packet:invalid-channel";
        case Header(var channel, var priority) when priority >= 10 ->
                "packet:high:" + channel.strip()
                        + ":" + payloadLabel(payload);
        case Header(var channel, var priority) ->
                "packet:normal:" + channel.strip()
                        + ":" + payloadLabel(payload);
        case null -> "packet:missing-header";
    };
}
```

**Điểm quan trọng:**

1. `Header(var channel, var priority)` kiểm tra record object non-null, đọc các component và bind chúng vào biến pattern.
2. Nhánh guard đầu chặn channel null/blank **trước** khi dùng `strip()`.
3. Nhánh high dùng `priority >= 10`: đúng ngưỡng 10 được tính high.
4. Nhánh không guard là fallback cho mọi Header còn lại; cần đứng sau nhánh guarded.
5. `case null` xử lý header reference null; không thêm `default` vì switch đã bao phủ Header non-null và null.

**Null ở hai cấp khác nhau:** `header == null` không match record pattern `Header(...)`, trong khi `new Header(null,10)` là một Header non-null, `var channel` có thể bind null. Không coi record pattern là bộ validator tự động cho từng component.

Trong Java 21, nested type patterns unconditional cho kiểu component có thể có quy tắc **null-matching** đặc biệt, do đó đổi `var channel` thành `String channel` không phải cách đáng tin để cấm channel null. Hãy kiểm tra rõ ràng trong guard.

### 6.1. Đừng đặt guard high trước guard invalid

Nếu viết `case Header(var channel,var priority) when priority >= 10` lên trước và thân nhánh gọi `channel.strip()`, một Header priority cao nhưng channel null có thể ném NPE thay vì `packet:invalid-channel`. Thứ tự case là một phần contract, không phải chi tiết thẩm mỹ.

## 7. Side effects: giá trị đúng vẫn có thể là refactor sai

Một số getter của class legacy không thuần. Ví dụ:

```java
static final class TextMessage {
    private final String body;
    private int reads;

    TextMessage(String body) { this.body = body; }

    String readBody() {
        reads++;
        return body;
    }

    int reads() { return reads; }
}
```

Trong chương trình, bản legacy và modern đều chỉ gọi `readBody()` một lần. Bản refactor **cố ý sai** dưới đây gọi nó nhiều lần:

```java
static String naiveTextRoute(Object input) {
    return switch (input) {
        case TextMessage message
                when message.readBody() != null
                        && !message.readBody().isBlank() ->
                "text:" + message.readBody().strip();
        case TextMessage message -> "text:<blank>";
        default -> "unsupported";
    };
}
```

Với body `" Java "`, các lời gọi xảy ra theo thứ tự:

1. `readBody() != null` — đọc lần 1.
2. `!readBody().isBlank()` — đọc lần 2.
3. `readBody().strip()` — đọc lần 3.

Mã mới trả đúng `text:Java` nhưng **reads=3**, so với bản cũ **reads=1**. Nếu getter thực hiện I/O, ghi metric hoặc lấy snapshot dữ liệu thay đổi theo thời điểm, đây là regression nghiêm trọng. Với body `null`, bản naive trả `text:<blank>` thay cho `text:<null>`: còn thay cả output.

**Giải pháp:** chỉ gọi getter một lần rồi xử lý giá trị đã lấy, như `case TextMessage message -> textLabel(message.readBody());`. Guard `when` nên dùng cho các điều kiện thực sự cần chọn nhánh và tránh đọc lặp dữ liệu có side effect.

### 7.1. Packet getter cũng cần giữ số lần và thứ tự

`PacketMessage.header()` và `PacketMessage.payload()` trong demo đều tăng counter; cả hai phiên bản gọi đúng một lần mỗi method. Khi refactor:

```java
case PacketMessage message ->
        patternPacket(message.header(), message.payload());
```

Java đánh giá đối số lời gọi phương thức từ trái sang phải, nên header được đọc trước payload. Đổi sang guard nhiều lần gọi `message.header()` có thể phát sinh side effects khác. Nếu thứ tự có ý nghĩa, test một event log như `["header","payload"]` chứ không chỉ cộng tổng lượt đọc.

### 7.2. Custom record accessors và ngoại lệ

Record pattern deconstruction gọi accessor của record. Với record Header mặc định trong bài, accessor chỉ trả component. Nhưng Java cho phép record khai báo accessor tùy biến; nó có thể thay đổi state hoặc ném exception. Khi áp dụng vào record thật, cần xác minh số lần/thứ tự getter và ngoại lệ từ deconstruction (trong trường hợp accessor ném lỗi, pattern matching có thể tạo `MatchException` theo quy tắc Java 21).

Đừng mặc định mọi record pattern ít thao tác hơn cast. Chọn độ sâu pattern theo dữ liệu thực sự cần.

## 8. Chương trình chạy độc lập và differential tests

Tạo file **`LegacyModuleRefactorDemo.java`**. Chương trình không cần JUnit, Maven hay thư viện bên ngoài. Nó chạy kiểm tra dữ liệu cũ/mới bằng 21 ca, so cả return/exception và số lượt đọc. Dùng `Supplier<Object>` để sinh **hai instance độc lập** có cùng trạng thái ban đầu.

```java
import java.util.Objects;
import java.util.function.Function;
import java.util.function.Supplier;

public class LegacyModuleRefactorDemo {
    record Header(String channel, int priority) {}

    record Outcome(String result, String errorType, String errorMessage) {
        static Outcome ok(String s) {
            return new Outcome(s, null, null);
        }

        static Outcome error(String type, String message) {
            return new Outcome(null, type, message);
        }

        String display() {
            return errorType == null ? result
                    : errorType + ":" + errorMessage;
        }
    }

    static final class TextMessage {
        private final String body;
        private int reads;

        TextMessage(String body) { this.body = body; }

        String readBody() {
            reads++;
            return body;
        }

        int reads() { return reads; }
    }

    static final class CountMessage {
        private final int count;

        CountMessage(int count) { this.count = count; }

        int count() { return count; }
    }

    static final class PacketMessage {
        private final Header header;
        private final String payload;
        private int headerReads;
        private int payloadReads;

        PacketMessage(Header header, String payload) {
            this.header = header;
            this.payload = payload;
        }

        Header header() {
            headerReads++;
            return header;
        }

        String payload() {
            payloadReads++;
            return payload;
        }

        int reads() { return headerReads + payloadReads; }
    }

    static final class Heartbeat {}

    static final class ExplodingMessage {
        private int reads;

        String read() {
            reads++;
            throw new IllegalStateException("corrupted payload");
        }

        int reads() { return reads; }
    }

    static String textLabel(String body) {
        if (body == null) return "text:<null>";
        if (body.isBlank()) return "text:<blank>";
        return "text:" + body.strip();
    }

    static String payloadLabel(String payload) {
        return payload == null ? "<null>" : payload.strip();
    }

    static String legacyPacket(Header header, String payload) {
        if (header == null) return "packet:missing-header";
        String channel = header.channel();
        int priority = header.priority();

        if (channel == null || channel.isBlank()) {
            return "packet:invalid-channel";
        }
        if (priority >= 10) {
            return "packet:high:" + channel.strip()
                    + ":" + payloadLabel(payload);
        }
        return "packet:normal:" + channel.strip()
                + ":" + payloadLabel(payload);
    }

    static String patternPacket(Header header, String payload) {
        return switch (header) {
            case Header(var channel, var priority)
                    when channel == null || channel.isBlank() ->
                    "packet:invalid-channel";
            case Header(var channel, var priority) when priority >= 10 ->
                    "packet:high:" + channel.strip()
                            + ":" + payloadLabel(payload);
            case Header(var channel, var priority) ->
                    "packet:normal:" + channel.strip()
                            + ":" + payloadLabel(payload);
            case null -> "packet:missing-header";
        };
    }

    static String legacyRoute(Object input) {
        if (input == null) return "null-input";

        if (input instanceof TextMessage) {
            TextMessage message = (TextMessage) input;
            String body = message.readBody();
            return textLabel(body);
        }
        if (input instanceof CountMessage) {
            CountMessage count = (CountMessage) input;
            if (count.count() < 0) return "count:negative";
            return "count:" + count.count();
        }
        if (input instanceof PacketMessage) {
            PacketMessage message = (PacketMessage) input;
            Header header = message.header();
            String payload = message.payload();
            return legacyPacket(header, payload);
        }
        if (input instanceof Heartbeat) return "heartbeat";
        if (input instanceof ExplodingMessage) {
            ExplodingMessage message = (ExplodingMessage) input;
            return message.read();
        }
        return "unsupported";
    }

    static String modernRoute(Object input) {
        return switch (input) {
            case null -> "null-input";
            case TextMessage message ->
                    textLabel(message.readBody());
            case CountMessage count when count.count() < 0 ->
                    "count:negative";
            case CountMessage count -> "count:" + count.count();
            case PacketMessage message ->
                    patternPacket(message.header(), message.payload());
            case Heartbeat h -> "heartbeat";
            case ExplodingMessage message -> message.read();
            default -> "unsupported";
        };
    }

    // Cố ý sai: đọc getter có side effect nhiều lần.
    static String naiveTextRoute(Object input) {
        return switch (input) {
            case TextMessage message
                    when message.readBody() != null
                            && !message.readBody().isBlank() ->
                    "text:" + message.readBody().strip();
            case TextMessage message -> "text:<blank>";
            default -> "unsupported";
        };
    }

    static Outcome capture(Function<Object, String> fn, Object input) {
        try {
            return Outcome.ok(fn.apply(input));
        } catch (RuntimeException e) {
            return Outcome.error(
                    e.getClass().getSimpleName(), e.getMessage());
        }
    }

    static int reads(Object input) {
        if (input instanceof TextMessage text) return text.reads();
        if (input instanceof PacketMessage packet) return packet.reads();
        if (input instanceof ExplodingMessage bad) return bad.reads();
        return 0;
    }

    static int cases;
    static int assertions;

    static void check(String label, Supplier<Object> inputFactory,
                      Outcome expected, int expectedReads) {
        Object oldInput = inputFactory.get();
        Object newInput = inputFactory.get();
        Outcome before = capture(
                LegacyModuleRefactorDemo::legacyRoute, oldInput);
        Outcome after = capture(
                LegacyModuleRefactorDemo::modernRoute, newInput);

        if (!Objects.equals(before, expected)) {
            throw new AssertionError(
                    label + " legacy: " + before + " vs " + expected);
        }
        assertions++;
        if (!Objects.equals(after, expected)) {
            throw new AssertionError(
                    label + " modern: " + after + " vs " + expected);
        }
        assertions++;
        if (reads(oldInput) != expectedReads) {
            throw new AssertionError(
                    label + " old reads=" + reads(oldInput));
        }
        assertions++;
        if (reads(newInput) != expectedReads) {
            throw new AssertionError(
                    label + " new reads=" + reads(newInput));
        }
        assertions++;

        cases++;
        System.out.println(label + " => " + expected.display()
                + " | reads=" + expectedReads);
    }

    public static void main(String[] args) {
        check("text-trim", () -> new TextMessage(" Java "),
                Outcome.ok("text:Java"), 1);
        check("text-blank", () -> new TextMessage(" \t "),
                Outcome.ok("text:<blank>"), 1);
        check("text-null", () -> new TextMessage(null),
                Outcome.ok("text:<null>"), 1);
        check("text-unicode", () -> new TextMessage(" Xin chào "),
                Outcome.ok("text:Xin chào"), 1);

        check("count-negative", () -> new CountMessage(-1),
                Outcome.ok("count:negative"), 0);
        check("count-zero", () -> new CountMessage(0),
                Outcome.ok("count:0"), 0);
        check("count-positive", () -> new CountMessage(7),
                Outcome.ok("count:7"), 0);
        check("count-max",
                () -> new CountMessage(Integer.MAX_VALUE),
                Outcome.ok("count:2147483647"), 0);

        check("packet-high-boundary",
                () -> new PacketMessage(
                    new Header(" api ", 10), " body "),
                Outcome.ok("packet:high:api:body"), 2);
        check("packet-high",
                () -> new PacketMessage(
                    new Header("evt", 12), "hello"),
                Outcome.ok("packet:high:evt:hello"), 2);
        check("packet-normal-boundary",
                () -> new PacketMessage(
                    new Header("evt", 9), "hello"),
                Outcome.ok("packet:normal:evt:hello"), 2);
        check("packet-normal-negative",
                () -> new PacketMessage(
                    new Header("evt", -5), "hello"),
                Outcome.ok("packet:normal:evt:hello"), 2);
        check("packet-invalid-blank",
                () -> new PacketMessage(
                    new Header(" ", 10), "body"),
                Outcome.ok("packet:invalid-channel"), 2);
        check("packet-invalid-null",
                () -> new PacketMessage(
                    new Header(null, 10), "body"),
                Outcome.ok("packet:invalid-channel"), 2);
        check("packet-missing-header",
                () -> new PacketMessage(null, "body"),
                Outcome.ok("packet:missing-header"), 2);
        check("packet-null-payload",
                () -> new PacketMessage(
                    new Header("evt", 3), null),
                Outcome.ok("packet:normal:evt:<null>"), 2);
        check("packet-empty-payload",
                () -> new PacketMessage(
                    new Header("evt", 3), " "),
                Outcome.ok("packet:normal:evt:"), 2);

        check("heartbeat", Heartbeat::new,
                Outcome.ok("heartbeat"), 0);
        check("exploding", ExplodingMessage::new,
                Outcome.error(
                    "IllegalStateException", "corrupted payload"), 1);
        check("unsupported", Object::new,
                Outcome.ok("unsupported"), 0);
        check("selector-null", () -> null,
                Outcome.ok("null-input"), 0);

        System.out.println("PARITY CASES PASS: " + cases);

        TextMessage unsafe = new TextMessage(" Java ");
        String naive = naiveTextRoute(unsafe);
        if (!"text:Java".equals(naive) || unsafe.reads() != 3) {
            throw new AssertionError("expected naive triple-read");
        }
        assertions++;
        System.out.println("NAIVE GUARD => " + naive
                + " | reads=" + unsafe.reads());
        System.out.println("ASSERTIONS PASS: " + assertions);
    }
}
```

### 8.1. Biên dịch và chạy

Dùng JDK 21+ tại thư mục chứa file:

```bash
javac --release 21 LegacyModuleRefactorDemo.java
java LegacyModuleRefactorDemo
```

**Stdout đã kiểm chứng:**

```text
text-trim => text:Java | reads=1
text-blank => text:<blank> | reads=1
text-null => text:<null> | reads=1
text-unicode => text:Xin chào | reads=1
count-negative => count:negative | reads=0
count-zero => count:0 | reads=0
count-positive => count:7 | reads=0
count-max => count:2147483647 | reads=0
packet-high-boundary => packet:high:api:body | reads=2
packet-high => packet:high:evt:hello | reads=2
packet-normal-boundary => packet:normal:evt:hello | reads=2
packet-normal-negative => packet:normal:evt:hello | reads=2
packet-invalid-blank => packet:invalid-channel | reads=2
packet-invalid-null => packet:invalid-channel | reads=2
packet-missing-header => packet:missing-header | reads=2
packet-null-payload => packet:normal:evt:<null> | reads=2
packet-empty-payload => packet:normal:evt: | reads=2
heartbeat => heartbeat | reads=0
exploding => IllegalStateException:corrupted payload | reads=1
unsupported => unsupported | reads=0
selector-null => null-input | reads=0
PARITY CASES PASS: 21
NAIVE GUARD => text:Java | reads=3
ASSERTIONS PASS: 85
```

### 8.2. Vì sao có 85 assertions?

Mỗi `check(...)` so **bốn điều kiện**: giá trị/exception của mã cũ đúng expected, của mã mới đúng expected, số lượt đọc bên cũ đúng, số lượt đọc bên mới đúng. Với 21 ca: \(21\times4=84\). Sau đó thêm một assertion gộp xác nhận phản ví dụ `naiveTextRoute` cho đúng text nhưng gọi getter ba lần: tổng **85**.

Chương trình dùng `throw new AssertionError` nên không cần cờ JVM `-ea` để bật kiểm tra. Không có benchmark và không có kết nối dịch vụ thật.

### 8.3. Vì sao phải tạo hai instance độc lập?

Hàm `check` nhận `Supplier<Object>` và tạo `oldInput`/`newInput` riêng:

```java
Object oldInput = inputFactory.get();
Object newInput = inputFactory.get();
```

Nếu chạy old rồi new trên cùng một `TextMessage`, bộ đếm đã tăng từ lượt trước, khiến việc so sánh side effects bị nhiễu. Khi test production có database hoặc network, hãy dùng sandbox hoặc transaction isolation; **không gửi hai lệnh thật làm thay đổi hệ thống** chỉ để so parity.

### 8.4. Giới hạn của bộ test

`capture(...)` chỉ bắt `RuntimeException` và so class name/message; nó không so stack trace hay cause. Nếu module thật cần bảo toàn checked exception, error code, log, audit, transaction hoặc performance, phải mở rộng test. Các fixture chỉ bao phủ một tập input hữu hạn; PASS không chứng minh mọi trạng thái có thể có.

## 9. Ma trận kiểm thử hồi quy cần có trong module thật

| Nhóm | Ca cần kiểm tra | Vì sao quan trọng |
| --- | --- | --- |
| Happy path | Một input hợp lệ cho từng loại | Bảo toàn kết quả |
| Null selector | Input `null` | Switch không tự coi null là default |
| Null nested record | Header null | Record pattern không match null |
| Null component | Channel/payload null | Guard không ném NPE bất ngờ |
| Blank và Unicode | `" "`, tab, tiếng Việt | Không đổi normalization |
| Numeric boundary | -1, 0, 9, 10, giá trị lớn | Không đổi điều kiện `>=` |
| Unknown type | `new Object()`, plugin subtype | Giữ fallback |
| Exception | Getter ném lỗi | Không đổi exception class/contract |
| Getter count/order | Text, Packet, custom record accessor | Không nhân đôi side effect |
| Serialization | JSON/XML/JPA binding nếu public DTO liên quan | Giữ wire/schema contract |
| Integration | Handler → DB/queue/service | Không đổi transaction hoặc event |
| Performance | CPU, latency, allocation sau khi parity PASS | Phát hiện regression |

Đừng chỉ so hai version với nhau. Nếu cả hai cùng lỗi, test parity vẫn xanh. Cần **expected theo hợp đồng** hoặc golden baseline độc lập, như các `Outcome.ok(...)` và `Outcome.error(...)` trong demo.

Với side effects có thứ tự, có thể dùng spy ghi một chuỗi sự kiện như `["header","payload","audit"]` rồi so old/new. Tổng số lượt đọc bằng nhau chưa chứng minh trình tự thực hiện giống nhau.

## 10. Các lỗi biên dịch khi viết pattern switch

Những fragment dưới đây **cố ý không hợp lệ**; phải tách khỏi file runnable mục 8.

### 10.1. Dominance: type rộng trước type hẹp

```java
// CỐ Ý SAI:
return switch (input) {
    case CharSequence seq -> "sequence";
    case String s -> "string";
    default -> "other";
};
```

`String` là `CharSequence` nên nhánh sau bị bao phủ. `javac --release 21` báo `this case label is dominated by a preceding case label`. Đặt nhánh String trước.

### 10.2. Guard hằng false

```java
// CỐ Ý SAI:
return switch (header) {
    case Header h when false -> "never";
    default -> "other";
};
```

Compiler Java 21 từ chối một nhãn có guard là constant expression `false`. Không dùng nó để tạm tắt một case.

### 10.3. Biến pattern ngoài scope

```java
// CỐ Ý SAI:
return switch (input) {
    case String s when s.isBlank() -> "blank";
    default -> s;
};
```

Biến `s` không tồn tại ở nhánh default, compiler báo `cannot find symbol`. Flow scoping cho phép dùng biến trong `when` và thân case khi match, không cho dùng tùy tiện bên ngoài.

### 10.4. `return` trong switch expression block

```java
// CỐ Ý SAI:
return switch (input) {
    case String s -> { return s; }
    default -> "other";
};
```

Compiler báo `attempt to return out of a switch expression`. Nếu dùng block, sử dụng `yield`:

```java
return switch (input) {
    case String s -> {
        String normalized = s.strip();
        yield normalized;
    }
    default -> "other";
};
```

Bốn trường hợp sai ở trên đã được kiểm thử riêng với `javac --release 21`. Compiler có thể khác đôi chút về thông báo/line number theo JDK version. Các lỗi này là **compile-time**; không thể đặt chúng trong bài test runtime rồi mong runner xử lý.

### 10.5. Compiler không kiểm chứng mọi hành vi nghiệp vụ

Một `switch` có thể exhaustive mà vẫn trả sai payload, bỏ qua null, ghi log hai lần hoặc dùng sai ngưỡng. Vì vậy cần kết hợp compiler gate và regression tests.

## 11. Từng bước refactor trên dự án thật

Một quy trình an toàn nên làm theo thứ tự có thể review:

1. **Khoanh vùng module:** xác định API, DTO, caller, code cần refactor và dependency graph.
2. **Chụp baseline:** test happy path, null/exception, unknown types, side effect counts/order; lưu dữ liệu kiểm thử phù hợp.
3. **Phân loại các casts:** guarded cast khác direct cast không guard; đừng xóa exception contract.
4. **Nếu có thể, đổi từng `instanceof + cast` sang `instanceof Type variable`** trước, không đổi toàn bộ luồng.
5. **Giữ public POJOs ổn định**; nếu cần record adapter nội bộ, tạo ở phạm vi đã duyệt và test mapping.
6. **Chuyển dispatcher sang `switch` patterns Java 21**, dùng `case null`, `default`, thứ tự case phù hợp và `when` khi cần.
7. **Refactor helper nội bộ**, ví dụ `Header` record → record pattern, không để guard đọc getter stateful nhiều lần.
8. **Chạy differential tests trên fixture độc lập**, so output, exception và side effects.
9. **Chạy integration/contract tests** cho DB, JSON, queue, audit, framework binding nếu liên quan.
10. **Review và chạy CI với Java release mục tiêu**. Không đưa compiler preview syntax cũ vào code chuẩn Java 21.
11. **Triển khai có kế hoạch rollback** theo feature flag/canary/revert khi hệ thống hỗ trợ.
12. **Theo dõi số liệu sau triển khai** và loại bỏ implementation cũ khi đã hoàn tất chuyển đổi theo chính sách.

**Đừng gộp vào một PR**: đổi public class thành record, seal class hierarchy, nâng JDK, đổi nghiệp vụ và tối ưu thuật toán. Những thay đổi lớn đó có thể đều hợp lý, nhưng cần tách quyết định, rủi ro và bộ test tương ứng.

### 11.1. Shadow comparison phải tránh side effects kép

Nếu handler thực hiện giao dịch thật, không gọi cả old/new trên cùng sự kiện production nếu cả hai đều lưu DB/gửi message. Shadow test chỉ an toàn khi phần logic được so là thuần hoặc chạy trong môi trường cô lập. Không nên biến việc kiểm thử parity thành một nguyên nhân tạo dữ liệu trùng.

## 12. Cấu hình Java 21 trong build và CI

### Maven

Trong phần `<properties>` của `pom.xml`:

```xml
<properties>
    <maven.compiler.release>21</maven.compiler.release>
</properties>
```

Đây là đoạn cấu hình, không phải POM hoàn chỉnh. Maven/compiler plugin phải hỗ trợ `release 21`; kiểm tra Maven Toolchains/parent POM nếu có override. `mvn -version` giúp xác định JVM mà Maven thực sự chạy.

```bash
mvn -version
mvn test
```

### Gradle Kotlin DSL

Ví dụ trong `build.gradle.kts`:

```kotlin
plugins {
    java
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}

tasks.withType<JavaCompile>().configureEach {
    options.release.set(21)
}
```

Cần Gradle version phù hợp Java 21 và toolchain đã cài/provision đúng. Với Gradle wrapper, dùng `./gradlew test` hoặc `gradlew.bat test` tùy OS.

### Runtime triển khai

Biên dịch ra classfile Java 21 thì production runtime cũng phải hỗ trợ Java 21. Kiểm tra container image, CI runner, IDE project language level, Maven/Gradle target, agent instrumentation và thư viện framework. Một IDE nhận cú pháp Java 21 **không chứng minh** module đang deploy đúng JDK.

## 13. Dùng JUnit cho module đa file

Chương trình ở mục 8 không cần thư viện ngoài JDK. Trong dự án đã có JUnit Jupiter, hãy chuyển các ca vào test classes. Ví dụ minh họa dưới đây giả định test và `LegacyModuleRefactorDemo` nằm cùng package để sử dụng members package-private:

```java
import static org.junit.jupiter.api.Assertions.*;
import org.junit.jupiter.api.Test;

class MessageRouterRefactorTest {
    @Test
    void getterIsReadOnce() {
        var before = new LegacyModuleRefactorDemo.TextMessage(" Java ");
        var after = new LegacyModuleRefactorDemo.TextMessage(" Java ");

        assertEquals("text:Java",
                LegacyModuleRefactorDemo.legacyRoute(before));
        assertEquals("text:Java",
                LegacyModuleRefactorDemo.modernRoute(after));
        assertEquals(1, before.reads());
        assertEquals(1, after.reads());
    }

    @Test
    void nullKeepsFallback() {
        assertEquals("null-input",
                LegacyModuleRefactorDemo.legacyRoute(null));
        assertEquals("null-input",
                LegacyModuleRefactorDemo.modernRoute(null));
    }

    @Test
    void runtimeExceptionIsPreserved() {
        var before = new LegacyModuleRefactorDemo.ExplodingMessage();
        var after = new LegacyModuleRefactorDemo.ExplodingMessage();

        var oldError = assertThrows(IllegalStateException.class,
                () -> LegacyModuleRefactorDemo.legacyRoute(before));
        var newError = assertThrows(IllegalStateException.class,
                () -> LegacyModuleRefactorDemo.modernRoute(after));

        assertEquals(oldError.getMessage(), newError.getMessage());
        assertEquals(1, before.reads());
        assertEquals(1, after.reads());
    }
}
```

Đây là **mảnh JUnit phụ thuộc thư viện**, không chạy chỉ với `javac` JDK thuần. Với test trong package khác, cần điều chỉnh visibility hoặc chuyển test vào cùng package. Không mở public API chỉ để test private internals nếu có cách tốt hơn.

**Parameterized tests:** Dùng `@MethodSource`/`Arguments` cho bảng input và expected, nhưng tạo instance mới cho mỗi đường chạy. Với DTO có mutable state, dùng fixture factories; đừng chia sẻ một instance giữa test chạy song song.

**Integration tests:** Nếu module ghi DB, gửi queue hoặc deserialize JSON, kiểm tra wire/schema/transaction và các event đã phát. Type pattern refactor có thể đúng ở unit level nhưng thay DTO/serialization sẽ cần test riêng.

## 14. Hiệu năng và cách quan sát sau refactor

Pattern matching làm code rõ ràng hơn nhưng **không tự cam kết chạy nhanh hơn** cách `instanceof`/cast cũ. HotSpot/JIT có thể tối ưu cả hai. Nếu module ở hot path:

- Profile để xác định thời gian thực sự nằm ở dispatch, getter, regex, DB hay network.
- Đo baseline CPU, allocation, GC, throughput, latency p95/p99.
- Dùng JMH nếu cần microbenchmark dispatch, với input đa dạng và warm-up/forks phù hợp.
- Đảm bảo hai implementation thực hiện **cùng công việc**, nếu không benchmark so sánh sai mục tiêu.
- Đo lại sau deploy và rollback khi có regression.

Demo chứng minh **số lần đọc accessor** thay đổi khi viết guard naive, không phải một phép đo tốc độ. Không báo tỷ lệ tăng tốc nếu chưa có benchmark đáng tin.

## 15. Checklist code review

- [ ] Xác định đúng phạm vi module, public API và caller.
- [ ] Giữ POJO contracts; không tự chuyển public class thành record.
- [ ] Toolchain/source release/production runtime hỗ trợ Java 21.
- [ ] `instanceof + cast` chỉ được chuyển khi bảo toàn nhánh và exception.
- [ ] Type pattern trên class cũ hoạt động đúng; record pattern chỉ dùng trên record thích hợp.
- [ ] `switch` expression exhaustive; các loại không hỗ trợ giữ `default` khi cần.
- [ ] `case null` giữ đúng null policy, không trông chờ `default` bắt null.
- [ ] Guard `when` đúng cú pháp Java 21 và không có dominated case.
- [ ] Điều kiện ngưỡng 9/10, -1/0 vẫn đúng.
- [ ] Null selector, null nested record, null component được test riêng.
- [ ] Getter có side effect được gọi đúng số lần và thứ tự.
- [ ] Exception class/message/cause được giữ khi là contract.
- [ ] Output Unicode/whitespace giữ nguyên; không đổi `strip` thành `trim` tùy tiện.
- [ ] Differential tests dùng hai fixture độc lập nhưng tương đương.
- [ ] Có expected baseline độc lập, không chỉ so old/new giống nhau.
- [ ] Unit/integration/CI và compile gate đều PASS.
- [ ] Rollout có observability, kế hoạch rollback/revert.
- [ ] Không tuyên bố tăng tốc nếu chưa có bằng chứng đo.

**Definition of Done:** Code Java 21 biên dịch/chạy trên target; module giữ hợp đồng API đã chốt; mọi ca baseline quan trọng cho output, exception và side effects đạt; PR có thể review, triển khai và rollback có kiểm soát. Nếu refactor kèm thay đổi nghiệp vụ, hãy ghi rõ và phê duyệt riêng thay vì gọi là tương đương.

## 16. Những sai lầm thường gặp

**1. "Dùng pattern matching phải đổi mọi class thành record."** Không. Type patterns dùng trực tiếp với POJO class. Việc đổi class thành record có ảnh hưởng API và framework riêng.

**2. "Mã mới ít dòng thì không thể đổi behavior."** Sai. `case null`, `default`, thứ tự `when` và getter calls có thể thay đổi.

**3. "Getter trong guard không có side effect."** Không chắc. Demo dùng `TextMessage.readBody()` để chứng minh số lượt gọi 1 so với 3.

**4. "Compiler chấp nhận switch nghĩa là nghiệp vụ đúng."** Compiler chỉ xác nhận cú pháp, typing và một số quy tắc dominance/exhaustiveness; không chứng minh ngưỡng priority hay output đúng.

**5. "Nếu old/new giống nhau thì đã đủ."** Cả hai có thể cùng sai. Cần expected dựa trên hợp đồng, dữ liệu biên và integration tests.

**6. "Default tự xử lý null."** Không. Khi refactor `if instanceof` sang switch, xử lý null tường minh nếu behavior cũ có fallback.

**7. "Đổi thứ tự case giúp nhanh hơn mà không ảnh hưởng gì."** Thứ tự ảnh hưởng dominance và ưu tiên guard; chỉ thay khi có phê duyệt/test.

**8. "Cứ thay cast trực tiếp bằng pattern + fallback."** Điều đó có thể thay `ClassCastException`/NPE thành giá trị khác.

**9. "Bật sealed cho mọi interface legacy."** Không nếu caller/plugin còn được phép mở rộng.

**10. "Benchmark quan trọng hơn regression tests."** Không. Tối ưu nhanh nhưng sai hành vi không đạt mục tiêu refactor an toàn.

## 17. Bài tập và đáp án gợi ý

**Bài tập 1:** Chuyển duy nhất nhánh `TextMessage` từ `instanceof + cast` sang `instanceof TextMessage message`. Bộ test nào phải giữ nguyên?  
*Gợi ý:* Output, null behavior, một lượt đọc body, exception.

**Bài tập 2:** Bỏ `case null` trong `modernRoute`. Ca nào thất bại?  
*Gợi ý:* `selector-null`; switch có thể ném NPE.

**Bài tập 3:** Đổi `priority >= 10` thành `priority > 10` trong `patternPacket`. Test nào phát hiện?  
*Gợi ý:* `packet-high-boundary` với priority 10.

**Bài tập 4:** Chuyển `case PacketMessage message` thành `case PacketMessage(...)`. Vì sao compiler từ chối?  
*Gợi ý:* `PacketMessage` hiện là POJO class, không phải record.

**Bài tập 5:** Đặt `case CountMessage count` không guard trước case `when count.count() < 0`. Chuyện gì xảy ra?  
*Gợi ý:* Dominance; nhánh có guard không còn có cơ hội được chọn.

**Bài tập 6:** Thử dùng `naiveTextRoute(new TextMessage(null))`. So output và số lượt đọc với legacy.  
*Gợi ý:* Bản naive trả text blank thay vì text null; logic đã đổi.

**Bài tập 7:** Với JUnit, tạo test xác minh `ExplodingMessage` ném đúng `IllegalStateException` và chỉ gọi getter một lần.  
*Gợi ý:* Dùng `assertThrows` và fixture riêng old/new.

**Bài tập 8:** Nếu một public DTO đang được JSON framework dùng getters/setters, bạn có nên chuyển ngay nó thành record trong PR này không?  
*Gợi ý:* Chưa. Kiểm tra schema/framework compatibility và tách migration nếu cần.

**Bài tập 9:** Thiết kế một event trace cho `PacketMessage` để xác nhận thứ tự `header()` trước `payload()`.  
*Gợi ý:* Ghi tên accessor vào một danh sách trong spy; so hai trace.

**Bài tập 10:** Dùng Maven hoặc Gradle khóa release Java 21 và chạy toàn bộ tests của module. Vì sao chỉ đổi JDK của IDE chưa đủ?  
*Gợi ý:* Build tool, CI và production runtime có thể vẫn dùng JDK/target khác.

## Tham khảo chính thức

- [JEP 394 — Pattern Matching for instanceof](https://openjdk.org/jeps/394)
- [JEP 395 — Records](https://openjdk.org/jeps/395)
- [JEP 409 — Sealed Classes](https://openjdk.org/jeps/409)
- [JEP 440 — Record Patterns](https://openjdk.org/jeps/440)
- [JEP 441 — Pattern Matching for switch](https://openjdk.org/jeps/441)
- [Oracle Java SE 21 — Pattern Matching for switch](https://docs.oracle.com/en/java/javase/21/language/pattern-matching-switch.html)
- [Oracle Java SE 21 — Record Patterns](https://docs.oracle.com/en/java/javase/21/language/record-patterns.html)
- [JLS SE 21 §14.11 — Switch Statements and Dominance](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.11)
- [JLS SE 21 §14.30 — Patterns and Pattern Matching](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.30)
- [JLS SE 21 §6.3 — Scope of Declarations](https://docs.oracle.com/javase/specs/jls/se21/html/jls-6.html#jls-6.3)
- [Apache Maven Compiler Plugin — Setting compiler release](https://maven.apache.org/components/plugins/maven-compiler-plugin/examples/set-compiler-release.html)
- [Gradle — Toolchains for JVM projects](https://docs.gradle.org/current/userguide/toolchains.html)
- [OpenJDK — Java Microbenchmark Harness (JMH)](https://github.com/openjdk/jmh)
