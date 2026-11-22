# Kiểm tra trường tồn tại trước khi đọc dữ liệu JFR động

## 1. Vì sao phải kiểm tra trường trước khi đọc?

Trong **Java Flight Recorder (JFR)**, sự kiện có cấu trúc: mỗi event mang tên loại sự kiện, metadata và các trường dữ liệu. Khi xử lý event từ một tệp `.jfr` hoặc từ luồng JFR, ta thường dùng `RecordedEvent` (package `jdk.jfr.consumer`) để đọc dữ liệu.

Ví dụ, một event có thể mang các trường `orderId`, `amount` và `note`. Nhưng ứng dụng phân tích JFR không phải lúc nào cũng kiểm soát được **schema** của từng loại event: tệp có thể đến từ JDK khác, bản ứng dụng khác, plugin khác, hoặc loại event khác. Nếu gọi getter cho một trường không tồn tại, chương trình có thể ném ngoại lệ.

Cách đọc an toàn là **xác minh field trước khi truy cập**:

```java
if (event.hasField("orderId")) {
    String id = event.getString("orderId");
    System.out.println(id);
}
```

Đoạn trên là **mã minh họa**, giả định `event` là một `RecordedEvent` hợp lệ. Phương thức `hasField("orderId")` chỉ kiểm tra sự tồn tại của trường theo schema/đường dẫn trường ở event, còn `getString(...)` thực hiện đọc giá trị.

**Quy tắc quan trọng:** *Trường tồn tại* không đồng nghĩa *giá trị khác `null`*, cũng không tự động bảo đảm *kiểu dữ liệu phù hợp với getter*. Một consumer bền vững cần xử lý cả ba vấn đề.

**Phiên bản:** `RecordedEvent`, `RecordedObject.hasField(...)` và các getter thuộc API JFR hiện đang được hỗ trợ trong Java 17+; đây không phải cú pháp preview của Java 14. Nội dung bài sử dụng API chính thức, tránh các cách xử lý nội bộ/legacy.

## 2. Các API cần biết

`RecordedEvent` kế thừa `RecordedObject`. Chính `RecordedObject` cung cấp các API kiểm tra và đọc trường dùng được cho nhiều đối tượng ghi nhận JFR.

| API | Công dụng | Điều cần nhớ |
| --- | --- | --- |
| `event.hasField(String name)` | Hỏi có trường/đường dẫn trường đó hay không | Trả `true`/`false`; không đọc giá trị thành công thay cho getter |
| `event.getFields()` | Lấy danh sách `ValueDescriptor` mô tả các trường | Hữu ích để khám phá schema và kiểm tra kiểu |
| `event.getValue(String name)` | Lấy giá trị dưới dạng generic | Trả giá trị có thể là `null`; ném `IllegalArgumentException` nếu field không tồn tại |
| `event.getString(String name)` | Đọc trường kiểu `String` | Có thể trả `null`; ném `IllegalArgumentException` nếu field thiếu/sai kiểu |
| `event.getLong(String name)` | Đọc trường số nguyên tương thích `long` | Cho phép một số kiểu nguyên thủy mở rộng sang `long`, không phải mọi kiểu |
| `event.getDouble(String name)` | Đọc trường số tương thích `double` | Kiểm tra schema và quy tắc chuyển đổi trước khi sử dụng |
| `event.getEventType()` | Lấy metadata loại sự kiện | Dùng `getName()` để lọc event type trước khi đọc trường đặc thù |
| `ValueDescriptor.getName()` | Tên trường mô tả | So tên chính xác, phân biệt hoa/thường |
| `ValueDescriptor.getTypeName()` | Tên kiểu trường trong JFR | Hữu ích để chọn getter và phát hiện schema thay đổi |
| `ValueDescriptor.getFields()` | Mô tả trường con của một kiểu phức hợp | Hữu ích khi đọc đối tượng lồng nhau |

`hasField` nhận tên trường là chuỗi **khác `null`**. Các trường hợp như `hasField(null)` không phải phép kiểm tra hợp lệ: Javadoc yêu cầu `name` khác `null`.

### Không nhầm `getFields()` với giá trị của từng trường

`event.getFields()` trả **metadata** (danh sách `ValueDescriptor`), không phải danh sách các giá trị thực tế.

```java
for (ValueDescriptor field : event.getFields()) {
    System.out.println(field.getName() + " : " + field.getTypeName());
}
```

Đây là đoạn minh họa cần `import jdk.jfr.ValueDescriptor;` và một biến `event` hợp lệ. Để lấy **giá trị**, vẫn phải dùng `getValue(name)` hoặc một getter có kiểu như `getString`, `getLong`. Việc duyệt metadata không tự bảo đảm rằng giá trị không có `null`.

## 3. Ba trạng thái rất dễ nhầm: thiếu trường, trường null, sai kiểu

Giả sử event `demo.DynamicOrder` có schema:

| Field | Kiểu | Giá trị thực tế |
| --- | --- | --- |
| `orderId` | `java.lang.String` | `"ORD-42"` |
| `amount` | `long` | `150` |
| `note` | `java.lang.String` | `null` |
| `discountCode` | *Không tồn tại* | Không có dữ liệu |

Đây là bốn trạng thái khác nhau:

### 3.1. Field thực sự không tồn tại

```java
boolean exists = event.hasField("discountCode"); // false
```

Cố đọc:

```java
event.getValue("discountCode");
```

sẽ ném `IllegalArgumentException` khi trường không có trong event. Đây là loại lỗi cơ bản mà `hasField` giúp tránh.

Giải pháp:

```java
String discount = event.hasField("discountCode")
        ? event.getString("discountCode")
        : "not recorded";
```

Đây là mã minh họa với điều kiện `discountCode` được biết là kiểu `String` **nếu nó tồn tại**. Nếu schema không kiểm soát được, nên kiểm tra **kiểu** trước khi dùng `getString`.

### 3.2. Field tồn tại nhưng giá trị là `null`

```java
boolean hasNote = event.hasField("note");   // true
Object value = event.getValue("note");      // null
```

Đây **không phải** lỗi “missing field”. Trường `note` được khai báo trong schema nhưng event cụ thể không có giá trị. `getString("note")` cũng có thể trả `null`.

Nếu dữ liệu nghiệp vụ phân biệt “không có trường” và “trường có giá trị `null`”, cần nhánh riêng:

```java
if (!event.hasField("note")) {
    System.out.println("No note field in schema");
} else {
    String note = event.getString("note");
    if (note == null) {
        System.out.println("Note field exists but its value is null");
    } else {
        System.out.println("Note: " + note);
    }
}
```

### 3.3. Field tồn tại nhưng getter sai kiểu

```java
boolean hasAmount = event.hasField("amount"); // true
String text = event.getString("amount");       // IllegalArgumentException
```

`amount` có kiểu `long`, không phải `String`. `hasField("amount") == true` **không bảo đảm** `getString("amount")` hợp lệ.

Đọc đúng:

```java
long amount = event.getLong("amount");
```

Khi làm việc với event schema thay đổi, nên kiểm tra `ValueDescriptor.getTypeName()` trước nếu getter phụ thuộc kiểu. Một số getter số hỗ trợ **mở rộng kiểu nguyên thủy** theo quy định API (ví dụ `int` có thể đọc qua `getLong`); không nên coi tất cả kiểu số đều tự động chuyển đổi được.

## 4. Quy trình đọc dữ liệu động an toàn

Một consumer JFR có thể xử lý nhiều event types. Nên thực hiện **từ ngoài vào trong**:

1. **Kiểm tra tên loại sự kiện** bằng `event.getEventType().getName()`. Không đọc `orderId` từ event GC hoặc event CPU.
2. **Kiểm tra sự tồn tại của trường** qua `hasField(name)` trước khi truy cập.
3. Nếu schema không cố định, **kiểm tra kiểu metadata** từ `getFields()` / `ValueDescriptor`.
4. Dùng **getter có kiểu tương ứng**, ví dụ `getString` với `String` hoặc `getLong` với `long`.
5. Nếu kiểu trường là tham chiếu, **kiểm tra giá trị `null`** sau khi đọc.
6. Khi field tùy chọn thiếu, **chọn fallback rõ ràng**: bỏ qua, ghi nhận thiếu schema, hoặc giá trị mặc định có chủ đích.
7. Đóng `RecordingFile`/`EventStream` theo vòng đời tài nguyên; không dựa vào callback để giữ tài nguyên mãi.

Với một trường chỉ có ý nghĩa cho một loại sự kiện:

```java
if ("demo.DynamicOrder".equals(event.getEventType().getName())
        && event.hasField("orderId")) {
    String id = event.getString("orderId");
    if (id != null) {
        System.out.println(id);
    }
}
```

Lối viết này **không phụ thuộc thứ tự các sự kiện** trong tệp JFR, vốn có thể chứa nhiều sự kiện hệ thống lẫn ứng dụng.

### Kiểm tra kiểu bằng `ValueDescriptor`

```java
ValueDescriptor amountField = event.getFields().stream()
        .filter(field -> field.getName().equals("amount"))
        .findFirst()
        .orElse(null);

if (amountField != null
        && "long".equals(amountField.getTypeName())) {
    long amount = event.getLong("amount");
    System.out.println(amount);
}
```

Đây là **đoạn mã minh họa**; cần `import jdk.jfr.ValueDescriptor;` và `event` hợp lệ. Trong ví dụ đã biết schema, có thể dùng ngay `getLong("amount")` sau khi `hasField`. Với data source động, việc xem `getTypeName()` hữu ích hơn vì các event có thể có trường cùng tên nhưng **khác kiểu**.

**Chú ý:** Không tự “ép” kiểu JFR bằng cách cast kết quả `getValue` nếu chưa chắc schema. Một kiểu khác kỳ vọng có thể gây `ClassCastException` ở phía ứng dụng. Getter typed của API cho thông tin lỗi phù hợp hơn.

## 5. Ví dụ Java 17+ hoàn chỉnh: field có, thiếu và null

Ví dụ tự tạo một JFR event, ghi vào file `.jfr`, đọc lại và kiểm tra schema thực tế. Không cần tệp ghi mẫu bên ngoài hoặc thư viện bổ sung. Lưu toàn bộ vào **`DynamicJfrFieldsDemo.java`**.

```java
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Duration;
import jdk.jfr.Event;
import jdk.jfr.FlightRecorder;
import jdk.jfr.Name;
import jdk.jfr.Recording;
import jdk.jfr.ValueDescriptor;
import jdk.jfr.consumer.RecordedEvent;
import jdk.jfr.consumer.RecordingFile;

public class DynamicJfrFieldsDemo {
    @Name("demo.DynamicOrder")
    static final class DynamicOrder extends Event {
        String orderId;
        long amount;
        String note;
    }

    public static void main(String[] args) throws Exception {
        if (!FlightRecorder.isAvailable()) {
            System.out.println("JFR unavailable");
            return;
        }

        Path file = Files.createTempFile("dynamic-jfr-", ".jfr");
        try {
            try (Recording recording = new Recording()) {
                recording.enable(DynamicOrder.class)
                         .withThreshold(Duration.ZERO)
                         .withoutStackTrace();
                recording.start();

                DynamicOrder order = new DynamicOrder();
                order.orderId = "ORD-42";
                order.amount = 150L;
                order.note = null;
                order.commit();

                recording.stop();
                recording.dump(file);
            }

            int matched = 0;
            try (RecordingFile recording = new RecordingFile(file)) {
                while (recording.hasMoreEvents()) {
                    RecordedEvent event = recording.readEvent();
                    if (!"demo.DynamicOrder".equals(event.getEventType().getName())) {
                        continue;
                    }
                    matched++;
                    System.out.println("hasOrderId=" + event.hasField("orderId"));
                    System.out.println("hasAmount=" + event.hasField("amount"));
                    System.out.println("hasNote=" + event.hasField("note"));
                    System.out.println("hasDiscount=" + event.hasField("discountCode"));
                    System.out.println("noteIsNull=" + (event.getValue("note") == null));
                    System.out.println("orderId=" + event.getString("orderId"));
                    System.out.println("amount=" + event.getLong("amount"));

                    String typeName = event.getFields().stream()
                            .filter(descriptor -> descriptor.getName().equals("amount"))
                            .findFirst().map(ValueDescriptor::getTypeName)
                            .orElse("missing");
                    System.out.println("amountType=" + typeName);

                    String discount = event.hasField("discountCode")
                            ? event.getString("discountCode")
                            : "not recorded";
                    System.out.println("discount=" + discount);

                    try {
                        event.getValue("discountCode");
                        System.out.println("missingRead=unexpected");
                    } catch (IllegalArgumentException expected) {
                        System.out.println("missingRead=IllegalArgumentException");
                    }

                    try {
                        event.getString("amount");
                        System.out.println("wrongType=unexpected");
                    } catch (IllegalArgumentException expected) {
                        System.out.println("wrongType=IllegalArgumentException");
                    }
                }
            }
            System.out.println("matched=" + matched);
        } finally {
            Files.deleteIfExists(file);
        }
    }
}
```

Biên dịch và chạy trên JDK 17 hoặc mới hơn:

```bash
javac --release 17 DynamicJfrFieldsDemo.java
java DynamicJfrFieldsDemo
```

**Đầu ra đã kiểm chứng trên OpenJDK có JFR:**

```text
hasOrderId=true
hasAmount=true
hasNote=true
hasDiscount=false
noteIsNull=true
orderId=ORD-42
amount=150
amountType=long
discount=not recorded
missingRead=IllegalArgumentException
wrongType=IllegalArgumentException
matched=1
```

Giải thích từng nhóm kết quả:

- `hasOrderId=true`, `hasAmount=true`: hai trường có trong schema event; consumer có thể đọc theo kiểu đã biết.
- `hasNote=true` đồng thời `noteIsNull=true`: **field tồn tại nhưng giá trị tham chiếu `null`**; hai điều kiện không mâu thuẫn.
- `hasDiscount=false`: `discountCode` **không được định nghĩa** trong loại event này, nên logic thay thế `"not recorded"` được chọn.
- `orderId=ORD-42` và `amount=150`: getter có kiểu trả dữ liệu thực tế; `getLong` thích hợp với trường `long`.
- `amountType=long`: metadata `ValueDescriptor` giúp xác nhận kiểu field trước khi chọn getter ở consumer động.
- `missingRead=IllegalArgumentException` và `wrongType=IllegalArgumentException`: minh họa hai lỗi mà code production nên **tránh bằng kiểm tra trước** thay vì bắt exception làm luồng kiểm tra bình thường.
- `matched=1`: file có đúng một event tùy biến được ghi trong ví dụ; các loại event JFR khác nếu tồn tại đã bị lọc bỏ.

**Vì sao có `try-with-resources`?** `Recording` và `RecordingFile` quản lý tài nguyên; cần đóng dù có lỗi. `finally` xóa file tạm để ví dụ không để lại dữ liệu JFR. Trong ứng dụng thực tế, nếu cần giữ file để điều tra, **không xóa file ngay** mà áp dụng quy tắc lưu trữ và quyền truy cập phù hợp.

**Vì sao không in tất cả event?** Tệp JFR có thể chứa sự kiện JVM mà số lượng/thứ tự thay đổi giữa các lần chạy. Chương trình **lọc theo `@Name("demo.DynamicOrder")`** để kết quả của bài học không phụ thuộc những event không liên quan.

## 6. Trường lồng nhau: đường dẫn có dấu chấm

`RecordedObject` có thể đại diện cho một cấu trúc lồng nhau. Javadoc cho phép chỉ định **đường dẫn bằng dấu chấm** trong `hasField` và các getter:

```java
if (event.hasField("eventThread.javaName")) {
    String threadName = event.getString("eventThread.javaName");
    System.out.println(threadName);
}
```

Đây là **mã minh họa**. Tên trường lồng nhau chính xác phụ thuộc schema của event và phiên bản JFR đang đọc; không giả định mọi event đều có `eventThread.javaName`.

Với đường dẫn như `outer.inner.value`, cần phân biệt:

1. Field `outer` có trong schema hay không.
2. Field con `inner` có trong cấu trúc lồng nhau hay không.
3. Giá trị của `outer` hoặc `inner` ở event **có thể `null`**.
4. Field `value` có kiểu/giá trị phù hợp hay không.

Theo API, `hasField("a.b")` có thể trả `false` nếu một đối tượng lồng nhau cần thiết đang `null`. Trong khi đó, **đọc trực tiếp** đường dẫn lồng nhau có thành phần `null` có thể ném `NullPointerException`. Vì vậy, việc kiểm tra đường dẫn trước khi đọc đặc biệt hữu ích, nhưng **không loại bỏ yêu cầu kiểm tra null của chính kết quả cuối**.

Ví dụ dùng một cấu trúc lồng nhau đã có trong sự kiện:

```java
if (event.hasField("sampledThread.javaName")) {
    String javaName = event.getString("sampledThread.javaName");
    if (javaName != null) {
        System.out.println(javaName);
    }
}
```

Đây là mã minh họa, **không khẳng định event của ứng dụng trong phần 5 có field `sampledThread`**. Tên và cấu trúc của trường phải được khám phá bằng `getFields()` hoặc tài liệu event type. Không hardcode một nested path dùng cho tất cả sự kiện.

## 7. Đọc từ nhiều phiên bản hoặc nhiều loại event

Khi xử lý JFR thực tế, một pipeline có thể đọc các file từ nhiều JDK, nhiều bản ứng dụng hoặc plugin. Một event type có thể **bổ sung, đổi tên hoặc bỏ field** giữa các phiên bản. Vì thế, logic consumer nên được chia:

**Phần xác định loại sự kiện**

```java
if (!"demo.DynamicOrder".equals(event.getEventType().getName())) {
    return;
}
```

Đây là **đoạn mã minh họa bên trong một phương thức xử lý một event** (không phải code đặt thẳng vào `main`); `return` kết thúc phương thức xử lý event, không có ý bỏ qua toàn bộ file recording trong ví dụ đầy đủ.

**Phần đọc dữ liệu bắt buộc**

Nếu `orderId` là field bắt buộc để nghiệp vụ hoạt động, đừng âm thầm đặt giá trị mặc định gây sai kết quả:

```java
if (!event.hasField("orderId")) {
    throw new IllegalArgumentException("Unsupported JFR schema: no orderId");
}
String orderId = event.getString("orderId");
if (orderId == null) {
    throw new IllegalArgumentException("Invalid event: orderId is null");
}
```

Đoạn minh họa làm rõ rằng **tùy nghiệp vụ**, một field thiếu là lỗi schema cần báo, chứ không phải lúc nào cũng fallback.

**Phần đọc dữ liệu tùy chọn**

```java
String note = event.hasField("note")
        ? event.getString("note")
        : null;

if (note != null) {
    // Dùng ghi chú nếu có.
}
```

Nếu logic cần phân biệt “không có field” và “field có giá trị null”, **đừng gộp cả hai thành một biến null duy nhất** như ví dụ rút gọn trên. Hãy giữ một cờ `hasField` riêng hoặc biểu diễn trạng thái kết quả bằng kiểu dữ liệu phù hợp.

### Một helper đọc String an toàn hơn khi schema không cố định

```java
static String optionalString(RecordedEvent event, String fieldName,
                             String fallback) {
    if (!event.hasField(fieldName)) {
        return fallback;
    }

    boolean isString = event.getFields().stream()
            .anyMatch(descriptor ->
                    descriptor.getName().equals(fieldName)
                    && "java.lang.String".equals(descriptor.getTypeName()));

    if (!isString) {
        return fallback;
    }

    String value = event.getString(fieldName);
    return value != null ? value : fallback;
}
```

Đây là **phương thức minh họa** cho field top-level, cần đặt trong lớp và import `RecordedEvent`; không dùng nguyên xi cho đường dẫn lồng nhau có dấu chấm vì phần tìm `ValueDescriptor` trên chỉ xét **tên field trực tiếp**. Helper phân biệt được **tồn tại + đúng kiểu + giá trị khác null** trước khi trả về dữ liệu.

Trong hệ thống lớn, nên có chính sách fallback nhất quán: phân loại “optional absent”, “required absent”, “wrong type” và “null value” riêng trong thông tin kiểm tra schema.

## 8. Sử dụng trong `RecordingStream` và xử lý callback

Với consumer theo thời gian thực, `jdk.jfr.consumer.RecordingStream` gửi `RecordedEvent` đến callback `onEvent`. Quy tắc kiểm tra trường **không đổi**:

```java
import jdk.jfr.consumer.RecordingStream;

try (RecordingStream stream = new RecordingStream()) {
    stream.enable("jdk.CPULoad");
    stream.onEvent("jdk.CPULoad", event -> {
        if (event.hasField("machineTotal")) {
            double load = event.getDouble("machineTotal");
            System.out.println(load);
        }
    });
    stream.startAsync();

    // Thực hiện công việc cần theo dõi trong khi stream còn sống.
}
```

Đây là **mã minh họa**, cần đặt trong phương thức phù hợp, không bảo đảm nhận được event CPU trong thời gian ngắn. Đừng phụ thuộc vào `close()` để khẳng định mọi callback đang chờ đã chạy xong. Nếu phải xử lý event đúng thời điểm, hãy thiết kế khoảng thời gian chạy, cơ chế đồng bộ và quản lý lỗi.

**Tại sao vẫn cần `hasField` ở streaming?** Nếu một callback xử lý event từ nhiều JDK/nguồn, hoặc code consumer có khả năng dùng schema khác, sự tồn tại của field vẫn cần được xác minh. Tuy nhiên, với một event type chuẩn và **phiên bản JDK cố định**, một getter có kiểu sau khi chọn đúng event type có thể đủ; không nhất thiết phải kiểm tra lại một field bắt buộc ở mọi vị trí nếu code đã có ràng buộc schema rõ ràng.

## 9. Những sai lầm thường gặp

| Sai lầm | Hậu quả | Cách đúng |
| --- | --- | --- |
| Đọc mọi event như cùng một loại | Getter cho field không có ở event khác | Lọc `getEventType().getName()` trước |
| Gọi `getValue("unknown")` rồi hi vọng trả `null` | Field thiếu gây `IllegalArgumentException` | `hasField` trước, hoặc policy lỗi schema rõ ràng |
| Coi `hasField(name) == true` nghĩa là giá trị khác `null` | Giá trị tham chiếu có thể `null` | Kiểm tra kết quả getter |
| Coi `hasField(name) == true` nghĩa là getter nào cũng đúng | Getter có thể sai kiểu | Kiểm tra `ValueDescriptor.getTypeName()` hoặc biết trước schema |
| Dùng `getString` cho `long` | `IllegalArgumentException` | Dùng `getLong` phù hợp |
| Dùng `getValue` và cast tùy ý | Dễ `ClassCastException` | Ưu tiên getter typed và metadata |
| So tên field không đúng chữ hoa/thường | Bị báo không có field | Dùng tên được schema công bố |
| Dùng `event.getFields()` như giá trị thực | Chỉ nhận metadata, không phải payload | Truy cập getter theo tên |
| Đọc `a.b.c` khi `a` hoặc `a.b` null | Có thể `NullPointerException` | Kiểm tra nested path và dữ liệu |
| Dùng helper xét `getFields()` trực tiếp cho nested path | Không tìm được field con chỉ từ danh sách top-level | Duyệt metadata lồng nhau hoặc dùng `hasField` với path |
| Đặt fallback im lặng cho field bắt buộc | Che schema lỗi và gây dữ liệu nghiệp vụ sai | Ném lỗi/ghi nhận schema không tương thích |
| Đọc `readAllEvents` toàn bộ file lớn | Có thể tốn nhiều bộ nhớ | Dùng `RecordingFile` đọc tuần tự |
| Log tất cả payload JFR không kiểm soát | Dễ lộ dữ liệu nhạy cảm | Chỉ log trường cần thiết, kiểm soát quyền |
| Dùng API `jdk.jfr.internal.*` để đọc field | Không phải API công khai ổn định | Dùng `jdk.jfr.consumer` |

## 10. Tự luyện tập và đáp án

**Câu 1.** `event.hasField("note")` trả `true` nhưng `event.getValue("note")` trả `null`. Đây có phải lỗi thiếu field không?  
**Đáp án:** Không. Field có trong schema, chỉ giá trị của event đó là `null`.

**Câu 2.** Nếu `event.hasField("discountCode")` là `false`, có thể gọi `getValue("discountCode")` và đợi `null` không?  
**Đáp án:** Không. Getter sẽ ném `IllegalArgumentException` khi field không tồn tại.

**Câu 3.** `event.hasField("amount")` là `true` với field kiểu `long`. `getString("amount")` có hợp lệ không?  
**Đáp án:** Không. Field tồn tại nhưng getter sai kiểu; dùng `getLong("amount")`.

**Câu 4.** Cách đọc tên và kiểu của tất cả field top-level là gì?  
**Đáp án:** Duyệt `event.getFields()` và gọi `ValueDescriptor.getName()`, `ValueDescriptor.getTypeName()`.

**Câu 5.** Khi đọc event `jdk.CPULoad`, có thể mặc định mọi event trong file đều có `machineTotal` không?  
**Đáp án:** Không. File có nhiều event types; phải lọc loại sự kiện trước, sau đó mới đọc field phù hợp.

**Câu 6.** `hasField("a.b")` cho kết quả `false` khi nested object `a` null. Có thể kết luận schema **không định nghĩa** `b` không?  
**Đáp án:** Không chắc. Đây có thể là **giá trị trung gian null**, không phải field con không tồn tại trong schema; kiểm tra metadata nếu cần phân biệt.

**Câu 7.** Tại sao chỉ dùng `event.hasField("fieldName")` chưa đủ để đọc dữ liệu động an toàn?  
**Đáp án:** Vì nó không bảo đảm kiểu phù hợp hay giá trị khác null. Cần xem descriptor và kiểm tra kết quả đọc.

**Câu 8.** Trong file JFR từ nhiều phiên bản ứng dụng, field mới `discountCode` chỉ có ở một số event. Nên xử lý thế nào?  
**Đáp án:** Kiểm tra field tồn tại và kiểu trước khi đọc; nếu là trường tùy chọn thì dùng fallback có chủ đích, nếu bắt buộc thì báo lỗi schema rõ ràng.

## 11. Tổng kết và tài liệu chính thức

**Mẫu tư duy bền vững khi đọc event động** là:

**Chọn đúng event type → kiểm tra field tồn tại → xác minh kiểu nếu schema không cố định → đọc bằng getter thích hợp → xử lý giá trị null và fallback theo nghiệp vụ.**

Nhớ các điểm:

- `hasField` trả lời câu hỏi **trường có sẵn hay không**, không phải **trường có giá trị khác null hay không**.
- `getValue` có thể trả null với **field tồn tại**, nhưng ném `IllegalArgumentException` nếu **field thiếu**.
- `getString`, `getLong`, `getDouble` và các getter khác có **quy tắc kiểu** riêng; không tự động chuyển mọi dữ liệu.
- Với nested path có dấu chấm, một đối tượng trung gian null có thể khiến kiểm tra/đọc hoạt động khác với field top-level; đừng nhầm schema thiếu với giá trị null.
- Với JFR từ nhiều JDK/phiên bản ứng dụng, **metadata `ValueDescriptor`** là công cụ quan trọng để viết consumer có khả năng tương thích.

Đây là các API công khai **vẫn còn áp dụng cho Java 17+**, không cần sử dụng thư viện nội bộ hoặc kiến thức legacy.

Tài liệu chính thức:

- [Oracle Java SE 17 — `RecordedObject`](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.jfr/jdk/jfr/consumer/RecordedObject.html): `hasField`, `getFields`, `getValue`, getter có kiểu và đường dẫn lồng nhau.
- [Oracle Java SE 17 — `RecordedEvent`](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.jfr/jdk/jfr/consumer/RecordedEvent.html): thông tin một sự kiện đã ghi, `getEventType` và những API kế thừa.
- [Oracle Java SE 17 — `ValueDescriptor`](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.jfr/jdk/jfr/ValueDescriptor.html): tên/kiểu/trường con của dữ liệu event.
- [Oracle Java SE 17 — `RecordingFile`](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.jfr/jdk/jfr/consumer/RecordingFile.html): cách đọc file JFR tuần tự.
- [Oracle Java SE 17 — `RecordingStream`](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.jfr/jdk/jfr/consumer/RecordingStream.html): tiêu thụ sự kiện trực tuyến.
