# Checklist chọn type pattern

## 1. Chọn đúng công cụ trước khi viết instanceof hoặc switch

Khi xử lý một giá trị có kiểu cha như `Object` hoặc một interface chứa nhiều subtype, Java cho phép kiểm tra kiểu và xử lý các trường hợp bằng **type pattern**. Cú pháp điển hình:

```java
if (value instanceof String text) {
    System.out.println(text.toUpperCase());
}
```

`String text` ở đây là **type pattern**: chương trình kiểm tra giá trị có khớp kiểu `String`, rồi ràng buộc tham chiếu đó với tên `text` có kiểu tĩnh `String`. Không cần viết phép cast thủ công `(String) value` sau khi kiểm tra.

Tuy nhiên, khi đã có type patterns, record patterns, sealed hierarchy và pattern matching for `switch` ở Java 21, câu hỏi không chỉ là “cú pháp nào chạy được?” mà là **“lúc nào type pattern là lựa chọn dễ đọc và ít rủi ro nhất?”**.

Type pattern thường đáng chọn khi:

- Cần phân biệt **đối tượng thuộc subtype nào**.
- Cần sử dụng **cả object đã kiểm tra** hoặc chuyển nó cho một handler khác.
- Subtype **không phải record**, hoặc việc phân rã toàn bộ record không giúp ích.
- Chỉ cần một vài accessor, không cần đọc cấu trúc lồng nhau.
- Một thao tác phân loại thuộc **ngữ cảnh bên ngoài** đối tượng, thay vì là hành vi chung nên gọi qua đa hình.

Ngược lại, khi muốn đọc nhiều component của một record và cấu trúc ấy chính là nội dung cần xử lý, **record pattern** có thể biểu đạt ý định rõ hơn. Khi mọi subtype đều đã cung cấp cùng một hành vi qua interface, **polymorphism** thường tốt hơn việc kiểm tra từng kiểu rồi gọi cùng một phương thức.

**Mục tiêu của bài:** cung cấp checklist quyết định có thể áp dụng khi review code, minh họa bằng `instanceof` và `switch` Java 21, kiểm tra các lỗi phạm vi biến, `null`, thứ tự case, generics và khả năng mở rộng.

## 2. Phân biệt bốn lựa chọn gần nhau

| Công cụ | Ví dụ | Khi nào hợp lý |
| --- | --- | --- |
| `instanceof` thuần | `value instanceof String` | Chỉ cần kết quả true/false; không sử dụng biến đã cast. |
| **Type pattern** | `value instanceof String text` hoặc `case String text -> ...` | Cần kiểm tra kiểu **và** tiếp tục dùng object có kiểu xác định. |
| **Record pattern** | `value instanceof Point(int x, int y)` | Muốn kiểm tra record và **phân rã component** thành biến. |
| **Polymorphism** | `service.execute()` | Đối tượng đã có hợp đồng hành vi chung và caller không cần biết subtype. |

Ví dụ đơn giản nhất: nếu chỉ hỏi “có phải chuỗi không?”, không bắt buộc khai báo biến pattern:

```java
static boolean isText(Object value) {
    return value instanceof String;
}
```

Nếu cần chiều dài chuỗi sau khi xác nhận kiểu:

```java
static int lengthOrZero(Object value) {
    if (value instanceof String text) {
        return text.length();
    }
    return 0;
}
```

Nếu đã có `record Point(int x, int y)` và thật sự cần cả hai tọa độ:

```java
static int coordinateSum(Object value) {
    if (value instanceof Point(int x, int y)) {
        return x + y;
    }
    return 0;
}
```

Các snippet trên minh họa những cách chọn khác nhau. Snippet cuối cần record `Point` trong cùng ngữ cảnh và Java 21 cho record patterns.

**Không nên ép mọi phép thử kiểu sang record pattern**, cũng không nên giữ cast thủ công sau `instanceof` khi type pattern đã diễn đạt rõ điều cần làm.

## 3. Checklist quyết định nhanh theo thứ tự

Hãy đọc các câu hỏi từ trên xuống; dừng ở lựa chọn đã giải quyết đúng nhiệm vụ.

| Câu hỏi | Nếu câu trả lời là “Có” | Ưu tiên |
| --- | --- | --- |
| 1. Chỉ cần boolean để biết đối tượng có thuộc một kiểu không? | Không cần dùng object đã ràng buộc. | `instanceof T` thuần, không tạo tên pattern thừa. |
| 2. Mọi subtype đã có phương thức đúng nghĩa cần gọi? | Ví dụ mọi `PaymentMethod` đều có `pay()`. | Gọi qua interface/đa hình, không tách case chỉ để gọi lại phương thức. |
| 3. Cần object **nguyên vẹn** để truyền cho service hoặc dùng nhiều phương thức? | Ví dụ chuyển `Submit submit` cho validator/handler. | **Type pattern**. |
| 4. Subtype là class thường, không phải record? | Không có record deconstruction phù hợp. | **Type pattern** để kiểm tra và lấy object. |
| 5. Chỉ cần một component trong record có nhiều component? | Phân rã toàn bộ làm code dài/khó hiểu. | Cân nhắc type pattern rồi gọi accessor cần thiết. |
| 6. Cần nhiều component và ý nghĩa thao tác bám trực tiếp vào cấu trúc record? | Ví dụ `Point(int x, int y)` để tính toán. | **Record pattern**. |
| 7. Phải phân rã record lồng nhau có nhiều cấp? | Cấu trúc cần phân tích rất rõ. | Nested record pattern; nếu quá sâu, cân nhắc tách nhỏ. |
| 8. Có nhiều subtype cần phân nhánh trong một phép chuyển đổi? | Ví dụ format log hoặc ánh xạ DTO. | `switch` với type/record patterns. |
| 9. Hierarchy đóng bằng `sealed`? | Tập subtype thuộc quyền quản lý của module. | `switch` không cần `default` khi các case đã exhaustive; tận dụng compiler. |
| 10. Hierarchy mở cho plugin? | Có thể có implementation tương lai. | Ưu tiên hợp đồng đa hình; nếu phân nhánh thì định nghĩa fallback có ý nghĩa. |
| 11. Có yêu cầu xét điều kiện sau khi kiểu khớp? | Ví dụ số lượng ít nhất 10. | Type pattern + `&&` trong `if` hoặc `case T t when ...` trong `switch`. |
| 12. Có thể có `null`? | Selector hoặc component tham chiếu có thể null. | Chính sách rõ: `case null`, kiểm tra trước hoặc validation ở boundary. |

Checklist không phải thuật toán thay thế thiết kế domain. Có thể có nhiều phương án đúng. Điều quan trọng là chọn cách thể hiện **đúng trách nhiệm của logic**, tránh phân rã/cast không cần thiết và giữ khả năng bảo trì khi mô hình tiến hóa.

## 4. Ưu tiên type pattern khi cần giữ nguyên subtype object

Giả sử một API nhận một action có nhiều subtype:

```java
sealed interface Action permits Submit, Cancel, Heartbeat {}

record Submit(String id, int units) implements Action {}

record Cancel(String id, String reason) implements Action {}

final class Heartbeat implements Action {
    private final String node;

    Heartbeat(String node) {
        this.node = node;
    }

    String node() {
        return node;
    }
}
```

Đây là các khai báo minh họa, chưa có validation; chương trình chạy hoàn chỉnh nằm ở phần 10.

Một service cần xử lý nguyên object `Submit`:

```java
if (action instanceof Submit submit) {
    submitHandler.handle(submit);
}
```

`submitHandler` trong snippet này là một dependency minh họa, không phải biến Java có sẵn. **Type pattern** hợp lý vì handler nhận **Submit object**. Nếu phân rã `Submit(String id, int units)` rồi lại phải dựng object để chuyển sang handler, code đã tạo công việc không cần thiết.

Một subtype không phải record như `Heartbeat` **không thể dùng record pattern `Heartbeat(...)`**. Với kiểu này, type pattern là lựa chọn tự nhiên:

```java
if (action instanceof Heartbeat heartbeat) {
    System.out.println(heartbeat.node());
}
```

Cũng có thể dùng type pattern với record:

```java
if (action instanceof Submit submit) {
    System.out.println(submit.id());
    System.out.println(submit.units());
}
```

Type pattern không đòi hỏi subtype phải là class thường. Nó hoạt động với class, interface và record phù hợp với quy tắc kiểu của Java.

### Không phải mọi record đều cần deconstruction

Giả sử có record nhiều component:

```java
record Shipment(
        String id,
        String destination,
        int units,
        long createdAt,
        String customerCode) {}
```

Nếu hàm chỉ cần `id`:

```java
static String shipmentId(Object value) {
    if (value instanceof Shipment shipment) {
        return shipment.id();
    }
    return "UNKNOWN";
}
```

Cách này thể hiện đúng mục đích: kiểm tra `Shipment`, rồi chỉ đọc component cần thiết. Dùng `Shipment(var id, var destination, var units, var createdAt, var customerCode)` chỉ để lấy `id` có thể làm người đọc tưởng các component khác cũng quan trọng.

**Lưu ý hiệu năng:** record pattern truy cập component thông qua accessor. Nhưng không thể khẳng định type pattern luôn nhanh hơn; JIT có thể inline getter đơn giản. Chọn cách rõ nghĩa trước, đo bằng profiler/JMH khi có bottleneck thực sự.

## 5. Ưu tiên record pattern khi mục tiêu là phân rã cấu trúc

Nếu yêu cầu là tính tổng tọa độ của `Point`, bản ghi hai component vốn chính là dữ liệu cần dùng:

```java
record Point(int x, int y) {}

static int sum(Object value) {
    return switch (value) {
        case Point(int x, int y) -> x + y;
        case null -> 0;
        default -> 0;
    };
}
```

Ở đây record pattern làm công thức đọc gần với cấu trúc dữ liệu hơn so với:

```java
static int sumByType(Object value) {
    if (value instanceof Point p) {
        return p.x() + p.y();
    }
    return 0;
}
```

Cả hai cách đều có thể hợp lý. Nếu thao tác chủ yếu phụ thuộc **component**, record pattern thường gọn; nếu cần gọi nhiều phương thức trên `Point` hoặc truyền object cho code khác, type pattern thuận tiện hơn.

### Khi cần nested record pattern

```java
record Address(String city) {}
record Customer(String id, Address address) {}

static String customerCity(Object value) {
    return switch (value) {
        case Customer(var id, Address(var city)) ->
                id + " ở " + city;
        case Customer customer ->
                "Khách thiếu địa chỉ: " + customer.id();
        case null -> "Không có khách";
        default -> "Loại khác";
    };
}
```

Đây là đoạn mã minh họa Java 21 khi các record được khai báo trong cùng ngữ cảnh. Nested record pattern diễn đạt rõ rằng cần thành phố từ `Address` bên trong `Customer`.

Nhánh `case Customer customer` phía sau bao phủ đối tượng `Customer` có component không khớp nested pattern, chẳng hạn `address == null`. Điều đó **khác** với việc ràng buộc `var address`: một `var` cho component tham chiếu có thể nhận giá trị null, còn nested record pattern `Address(...)` không khớp khi bản thân address null.

**Quy tắc:** Nếu không thực sự cần đọc cấu trúc lồng nhau, type pattern có thể giúp giảm độ sâu và tránh tạo một mẫu dài khó sửa.

## 6. Type pattern so với cast thủ công

Trước đây, code thường viết:

```java
if (value instanceof String) {
    String text = (String) value;
    System.out.println(text.length());
}
```

Java 16+ cho phép thay bằng:

```java
if (value instanceof String text) {
    System.out.println(text.length());
}
```

Lợi ích của type pattern:

- Giảm lặp lại tên kiểu và phép ép kiểu.
- Compiler biết biến `text` có kiểu `String` ở nơi mẫu đã khớp.
- Giảm rủi ro thay đổi nhầm kiểu trong cast hoặc đọc sai biến.
- Biến pattern được quản lý theo **flow scoping**: không thể sử dụng trên đường đi không chắc chắn khớp mẫu.

Tuy vậy, type pattern **không thay thế mọi cast**. Ví dụ khi generic type argument bị xóa ở runtime, không thể lấy `instanceof List<String>` làm phép kiểm tra đầy đủ của một danh sách `String`. Nếu cần xác nhận từng phần tử, phải kiểm tra phần tử hoặc sử dụng validation có kiểm soát.

Cũng không nên tạo biến chỉ để bỏ đi:

```java
// Chỉ cần true/false:
boolean isText = value instanceof String;

// Không cần:
// boolean isText = value instanceof String unused;
```

Khi boolean đủ cho nhiệm vụ, `instanceof T` thuần thường ít gây nhiễu hơn.

## 7. Dùng type pattern trong if: flow scope và short-circuit

Đặc trưng quan trọng nhất của type pattern là biến được dùng **chỉ ở nơi compiler chứng minh mẫu đã khớp**.

### Hợp lệ: vế phải của &&

```java
if (value instanceof String text && !text.isBlank()) {
    System.out.println(text.toUpperCase());
}
```

`&&` chỉ đánh giá vế phải khi phép thử `instanceof` đúng, vì vậy `text` đã được ràng buộc.

Có thể viết điều kiện với subtype:

```java
if (action instanceof Submit submit
        && submit.units() >= 10) {
    System.out.println("BULK " + submit.id());
}
```

Đọc từ trái sang phải: kiểm tra kiểu → kiểm tra dữ liệu → thực hiện xử lý.

### Sai: dùng biến ở vế phải của ||

```java
// KHÔNG BIÊN DỊCH nếu bỏ chú thích:
// if (value instanceof String text || text.isBlank()) {
//     System.out.println(text);
// }
```

`||` chỉ đánh giá vế phải khi vế trái **sai**; khi đó `text` chưa chắc tồn tại. Ngoài ra, một `if` dùng phép OR có thể vào thân chỉ vì điều kiện khác đúng, dù pattern không khớp. Nếu cần hai trường hợp độc lập, hãy tách nhánh.

### Sai: dùng ở else hoặc sau if không bảo đảm

```java
if (value instanceof String text) {
    System.out.println(text.length());
} else {
    // Không có text hợp lệ ở đây.
}

// KHÔNG BIÊN DỊCH:
// System.out.println(text);
```

Việc dữ liệu thử nghiệm “luôn là String” không tạo ra bảo đảm về flow scope khi kiểu tĩnh cho phép giá trị khác.

### Hợp lệ: guard clause thoát sớm

```java
static String requireText(Object value) {
    if (!(value instanceof String text)) {
        throw new IllegalArgumentException("Expected String");
    }
    return text.strip();
}
```

Nhánh không khớp kết thúc bằng `throw`, nên mọi đường đi đến `return text.strip()` đã khớp pattern. Nếu chỉ in cảnh báo rồi tiếp tục sau `if`, không có bảo đảm tương tự.

**Checklist khi dùng `if`:** Kiểm tra toán tử `&&`/`||`, phép phủ định `!`, các nhánh `return`/`throw` và vị trí dùng biến. Đừng sửa lỗi scope bằng cast không an toàn.

## 8. Type pattern trong switch: thứ tự, when, null và exhaustiveness

Từ **Java 21**, type patterns trong `switch` là tính năng chính thức, không cần `--enable-preview`.

```java
static String classify(Object value) {
    return switch (value) {
        case String text when !text.isBlank() ->
                "Có chữ: " + text.strip();
        case String ignored ->
                "Chuỗi trống";
        case Integer number ->
                "Số: " + number;
        case null ->
                "Không có dữ liệu";
        default ->
                "Kiểu khác";
    };
}
```

**Mỗi case có vai trò rõ:**

- `case String text when ...`: khớp `String` rồi kiểm tra guard.
- `case String ignored`: khớp mọi `String` còn lại, kể cả chuỗi rỗng hoặc chỉ có khoảng trắng.
- `case Integer number`: xử lý số nguyên, không dùng biến `text` của case khác.
- `case null`: chính sách cho selector null.
- `default`: xử lý những kiểu còn lại trong miền `Object` mở.

### Đặt case đặc thù trước case bao quát

```java
// Đúng:
case Submit submit when submit.units() >= 10 -> "BULK";
case Submit submit -> "STANDARD";
```

Các dòng trên là các nhánh minh họa thuộc một `switch`. Nếu đặt `case Submit submit` không guard lên trước, nó bao phủ mọi `Submit` không null; case có guard phía sau có thể bị compiler báo *dominated*.

Một type pattern tổng quát cũng có thể bao phủ các subtype:

```java
// KHÔNG BIÊN DỊCH nếu đặt như sau trong switch trên Object:
// case Object anything -> "OBJECT";
// case String text -> "TEXT";
```

`case Object anything` khớp mọi object không null, nên `String` phía sau không còn cơ hội chạy. Đặt nhánh cụ thể trước nhánh rộng.

### Sealed và interface mở

Nếu selector là `sealed interface Action` với subtype `Submit`, `Cancel`, `Heartbeat`, một `switch expression` liệt kê đủ các **type patterns** ấy có thể exhaustive **không cần `default`**. Khi thêm subtype vào `permits`, compiler có thể yêu cầu cập nhật nơi phân loại lúc biên dịch lại.

Với interface **mở** dành cho plugin, không thể liệt kê chắc chắn mọi subtype tương lai bằng vài case cụ thể; khi phân loại cần chính sách cho phần còn lại hoặc gọi hành vi qua interface. Một `default` trên miền mở có thể hợp lý, miễn không biến tình huống chưa hỗ trợ thành thành công giả.

### Null không phải default

Với pattern-matching `switch` Java 21, selector `null` cần chính sách riêng. Không nên mặc nhiên cho rằng `default` thay thế `case null`. Nếu null là lỗi, có thể `case null -> throw new IllegalArgumentException(...)` thay vì trả thông báo.

## 9. Type pattern hay polymorphism?

Xét một interface dịch vụ:

```java
interface ReportExporter {
    byte[] export();
}
```

Nếu code chỉ cần xuất dữ liệu, cách dùng phù hợp là:

```java
static byte[] runExport(ReportExporter exporter) {
    return exporter.export();
}
```

Không nên viết hàng loạt `if (exporter instanceof CsvExporter csv) ...` chỉ để gọi `export()` trên từng implementation. Đa hình đã giải quyết việc chọn hành vi, còn caller chỉ cần hợp đồng chung.

Ngược lại, một thao tác **hiển thị nhãn riêng theo subtype**, **chuyển DTO**, **phân loại log** hoặc **kiểm tra loại input tại boundary** có thể cần biết object thuộc trường hợp nào. Type pattern phù hợp nếu logic thuộc về tầng tiêu thụ và không nên được nhét vào interface domain.

Ví dụ:

```java
static String auditLabel(Action action) {
    return switch (action) {
        case Submit submit -> "Submitted " + submit.id();
        case Cancel cancel -> "Cancelled " + cancel.id();
        case Heartbeat heartbeat -> "Heartbeat " + heartbeat.node();
        case null -> "No action";
    };
}
```

Đoạn minh họa này có ý nghĩa khi các subtype được định nghĩa như `Action` ở phần 4 và người viết chỉ cần một nhãn phục vụ audit. Còn nếu việc “thực thi action” đã là hợp đồng của mọi object, nên xem xét một handler/service hoặc đa hình thay vì mặc định chuyển thành switch trên mọi subtype.

**Quy tắc review:** Type pattern nên làm sáng tỏ **một quyết định thật sự phụ thuộc kiểu**; không nên được dùng để mô phỏng bằng tay sự phân phối hành vi mà một interface đã định nghĩa.

## 10. Ví dụ Java 21 chạy độc lập: type pattern là lựa chọn chính

Chương trình dưới đây cố tình kết hợp:

1. `route`: dùng **type patterns** trong `switch`, vì handler muốn giữ toàn bộ object và gọi một số accessor của subtype.
2. `routeByRecord`: dùng **record patterns** trên các record để minh họa khác biệt khi thật sự muốn lấy component; `Heartbeat` không phải record nên vẫn dùng type pattern.
3. `probe`: dùng `instanceof` type pattern với `&&`, cho thấy flow scoping và guard.
4. `describeInput`: dùng type patterns để phân loại `Object`, có `when`, `case null` và `default` cho miền mở.

Tạo tệp **`ChooseTypePatternChecklistDemo.java`**:

```java
public class ChooseTypePatternChecklistDemo {
    static void requireNonBlank(String value, String field) {
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException(
                    field + " must not be blank");
        }
    }

    sealed interface Action permits Submit, Cancel, Heartbeat {}

    record Submit(String id, int units) implements Action {
        Submit {
            requireNonBlank(id, "id");
            if (units <= 0) {
                throw new IllegalArgumentException(
                        "units must be positive");
            }
        }
    }

    record Cancel(String id, String reason) implements Action {
        Cancel {
            requireNonBlank(id, "id");
            requireNonBlank(reason, "reason");
        }
    }

    static final class Heartbeat implements Action {
        private final String node;

        Heartbeat(String node) {
            requireNonBlank(node, "node");
            this.node = node;
        }

        String node() {
            return node;
        }
    }

    static String route(Action action) {
        return switch (action) {
            case Submit submit when submit.units() >= 10 ->
                    "BULK:" + submit.id();

            case Submit submit ->
                    "SUBMIT:" + submit.id();

            case Cancel cancel ->
                    "CANCEL:" + cancel.id();

            case Heartbeat heartbeat ->
                    "HEARTBEAT:" + heartbeat.node();

            case null ->
                    "NULL_ACTION";
        };
    }

    static String routeByRecord(Action action) {
        return switch (action) {
            case Submit(var id, var units) when units >= 10 ->
                    "BULK:" + id;

            case Submit(var id, var units) ->
                    "SUBMIT:" + id;

            case Cancel(var id, var reason) ->
                    "CANCEL:" + id;

            case Heartbeat heartbeat ->
                    "HEARTBEAT:" + heartbeat.node();

            case null ->
                    "NULL_ACTION";
        };
    }

    static String probe(Object input) {
        if (input instanceof Submit submit
                && submit.units() >= 10) {
            return "FLAG:BULK";
        }
        if (input instanceof Submit submit) {
            return "FLAG:SUBMIT";
        }
        if (input instanceof Heartbeat heartbeat) {
            return "FLAG:NODE:" + heartbeat.node();
        }
        return "FLAG:OTHER";
    }

    static String describeInput(Object input) {
        return switch (input) {
            case String text when !text.isBlank() ->
                    "STRING:" + text.strip();

            case String ignored ->
                    "STRING_BLANK";

            case Action action ->
                    "ACTION:" + route(action);

            case null ->
                    "NULL_INPUT";

            default ->
                    "UNSUPPORTED:" + input.getClass().getSimpleName();
        };
    }

    public static void main(String[] args) {
        Action bulk = new Submit("O-10", 10);
        Action standard = new Submit("O-4", 4);
        Action cancelled = new Cancel("O-10", "duplicate");
        Action heartbeat = new Heartbeat("node-a");

        System.out.println(route(bulk));
        System.out.println(route(standard));
        System.out.println(route(cancelled));
        System.out.println(route(heartbeat));
        System.out.println(route(null));

        System.out.println(routeByRecord(bulk));
        System.out.println(routeByRecord(standard));
        System.out.println(routeByRecord(cancelled));
        System.out.println(routeByRecord(heartbeat));
        System.out.println(routeByRecord(null));

        System.out.println(probe(bulk));
        System.out.println(probe(standard));
        System.out.println(probe(heartbeat));
        System.out.println(probe("x"));

        System.out.println(describeInput("  abc  "));
        System.out.println(describeInput("   "));
        System.out.println(describeInput(bulk));
        System.out.println(describeInput(null));
        System.out.println(describeInput(42));

        try {
            new Submit(" ", 1);
        } catch (IllegalArgumentException ex) {
            System.out.println("BAD_ID:" + ex.getMessage());
        }
    }
}
```

**Yêu cầu:** JDK 21 trở lên. Biên dịch và chạy không cần `--enable-preview`:

```bash
javac --release 21 -encoding UTF-8 ChooseTypePatternChecklistDemo.java
java ChooseTypePatternChecklistDemo
```

**Standard output chính xác:**

```text
BULK:O-10
SUBMIT:O-4
CANCEL:O-10
HEARTBEAT:node-a
NULL_ACTION
BULK:O-10
SUBMIT:O-4
CANCEL:O-10
HEARTBEAT:node-a
NULL_ACTION
FLAG:BULK
FLAG:SUBMIT
FLAG:NODE:node-a
FLAG:OTHER
STRING:abc
STRING_BLANK
ACTION:BULK:O-10
NULL_INPUT
UNSUPPORTED:Integer
BAD_ID:id must not be blank
```

### Phân tích kết quả

**Năm dòng đầu:** `route` phân loại bằng type pattern. `Submit("O-10",10)` thỏa guard `units >= 10` nên trả `BULK`; `Submit("O-4",4)` trượt guard đầu, sang case `Submit` không guard và trả `SUBMIT`. `Cancel` và `Heartbeat` được nhận diện theo kiểu. `null` có case riêng.

**Năm dòng tiếp:** `routeByRecord` cho kết quả tương ứng nhưng sử dụng `Submit(var id, var units)` và `Cancel(var id, var reason)` để lấy component. Với `Heartbeat` không phải record, phải dùng type pattern. Bài này không coi `routeByRecord` là phương án luôn tốt hơn: nó chỉ minh họa lựa chọn khi thật sự muốn deconstruction.

**Bốn dòng `FLAG`:** `probe` cho thấy type pattern trong `if` với `&&`; `Submit` số lượng đủ lớn được nhận trước, `Submit` còn lại được nhận sau. `Heartbeat` có nhánh riêng; một chuỗi không thuộc các kiểu được kiểm tra trả `FLAG:OTHER`.

**Năm dòng `describeInput`:** `String` có nội dung được `strip()` để tạo `STRING:abc`; chuỗi chỉ có khoảng trắng đi đến `STRING_BLANK`; một `Action` được truyền cho `route`; `null` vào `NULL_INPUT`; `Integer(42)` không thuộc các kiểu được liệt kê nên `default` trả `UNSUPPORTED:Integer`.

**Dòng cuối:** Constructor `Submit` từ chối `id` blank trước khi object hợp lệ được tạo. Pattern matching nhận diện subtype; nó không tự thay thế validation dữ liệu.

Lưu ý: chương trình dùng một sealed hierarchy **đóng** cho `Action` và một miền **mở** `Object` cho `describeInput`. Chính sự đối lập này giải thích vì sao `route` không cần `default` còn `describeInput` có fallback có chủ đích.

## 11. Chọn type pattern trong switch khi nào?

Một `switch` với type patterns là lựa chọn phù hợp khi có **nhiều nhánh xử lý theo subtype** và muốn quan sát toàn bộ chính sách trong một nơi. Ví dụ mapping API result:

```java
sealed interface Result permits Success, Failure {}

record Success(String message) implements Result {}

record Failure(int code, String reason) implements Result {}

static String toHttpSummary(Result result) {
    return switch (result) {
        case Success success ->
                "success: " + success.message();
        case Failure failure ->
                "error " + failure.code()
                        + ": " + failure.reason();
        case null ->
                "missing result";
    };
}
```

Những khai báo trên là một ví dụ riêng, không thuộc lớp chương trình phần 10. Type pattern có thể phù hợp vì logic trình bày dùng **một vài accessor** nhưng không cần phân rã toàn bộ record.

Khi record có đúng những component cần dùng, có thể viết:

```java
static String toHttpSummaryByRecord(Result result) {
    return switch (result) {
        case Success(var message) ->
                "success: " + message;
        case Failure(var code, var reason) ->
                "error " + code + ": " + reason;
        case null ->
                "missing result";
    };
}
```

Hai cách diễn đạt cùng mục tiêu. Đừng biến một guideline thành mệnh lệnh phải dùng một cú pháp trong toàn codebase; hãy ưu tiên sự nhất quán trong module, khả năng đọc được và mức độ gắn với cấu trúc record.

### Khi nào không nên dùng switch?

Với một nhánh đơn giản, `if (value instanceof T t)` có thể dễ đọc hơn một `switch` nhiều dòng. Nếu logic chỉ nhằm gọi một phương thức đã có trên interface, polymorphism rõ hơn. Nếu việc xử lý theo subtype kéo dài hàng trăm dòng, nên tách handler, helper/service hoặc thiết kế lại trách nhiệm, không dồn toàn bộ nghiệp vụ vào một biểu thức `switch`.

## 12. Lưu ý về generics và kiểu có thể kiểm tra lúc chạy

Type patterns vẫn tuân thủ các giới hạn của **type erasure**:

```java
static int listSize(Object value) {
    if (value instanceof java.util.List<?> list) {
        return list.size();
    }
    return 0;
}
```

`List<?>` là một kiểu có thể kiểm tra phù hợp với `instanceof`. Tuy nhiên, từ `List<?> list` không thể suy ra mọi phần tử là `String`. Ví dụ một `List<Integer>` vẫn khớp pattern `List<?>`.

Đừng viết:

```java
// Không hợp lệ cho phép kiểm tra runtime dạng này:
// if (value instanceof java.util.List<String> list) {
//     ...
// }
```

Vì Java không lưu đầy đủ type argument `String` của `List<String>` ở runtime để kiểm tra bằng `instanceof` theo cách đó.

Nếu cần xác thực cấu trúc phần tử, kiểm tra từng phần tử:

```java
static boolean allStrings(Object value) {
    if (!(value instanceof java.util.List<?> list)) {
        return false;
    }
    for (Object element : list) {
        if (!(element instanceof String)) {
            return false;
        }
    }
    return true;
}
```

Hàm này nhận danh sách rỗng là hợp lệ theo quy tắc “mọi phần tử đều là String”. Nếu domain yêu cầu danh sách không rỗng, hãy thêm điều kiện riêng. Một type pattern giúp ta ràng buộc `List<?>` an toàn, **không tự kiểm tra hợp đồng nội dung của collection**.

## 13. Các lỗi thường gặp khi chọn type pattern

| Lỗi | Vì sao đáng chú ý | Cách sửa |
| --- | --- | --- |
| Viết `instanceof` rồi cast thủ công ở nhánh đúng | Lặp kiểm tra kiểu, nhiều code hơn mức cần thiết. | `value instanceof T t`. |
| Tạo tên pattern dù chỉ cần boolean | Thêm biến không dùng, làm code nhiễu. | `value instanceof T`. |
| Dùng type pattern chỉ để gọi cùng phương thức interface | Caller bị phụ thuộc subtype không cần thiết. | Gọi hành vi đa hình. |
| Dùng record pattern dù chỉ cần nguyên object | Phân rã không phục vụ mục tiêu. | Dùng type pattern và chuyển object cho handler. |
| Dùng type pattern trong case rồi cố dùng biến ở case khác | Sai flow scope. | Giữ biến trong đúng case hoặc truyền dữ liệu có chủ đích. |
| Đặt type pattern tổng quát trước pattern cụ thể | Case cụ thể bị *dominated*. | Đặt nhánh cụ thể/guard trước. |
| Dùng biến type pattern trong vế phải của `||` | Vế phải được xét khi pattern bên trái có thể sai. | Tách nhánh hoặc dùng `&&` khi có phụ thuộc. |
| Tưởng `default` luôn xử lý null | Selector null có quy tắc riêng trong pattern switch. | `case null` hoặc validation trước switch. |
| Gán `default -> "OK"` cho sealed hierarchy | Che thiếu subtype cần xử lý. | Liệt kê case đầy đủ và tận dụng exhaustiveness. |
| Dùng `case Record(...)` cho class thường | Record pattern chỉ dùng trên record có cấu trúc hợp lệ. | Dùng type pattern cho class thường. |
| Cho rằng type pattern chứng minh field không null | Chỉ chứng minh object khớp kiểu. | Validation constructor/boundary và kiểm tra component. |
| Tưởng `List<?>` là `List<String>` | Generic arguments có thể bị xóa lúc chạy. | Xác thực phần tử và quy tắc domain riêng. |
| Cho rằng type pattern luôn nhanh hơn record pattern | Compiler/JIT và lượng công việc thực tế khác nhau. | Đo khi cần, không suy đoán từ cú pháp. |
| Thêm subtype plugin mà chỉ phân loại vài loại cố định | Code không xử lý implementation mới. | Dùng hợp đồng mở hoặc fallback rõ nghĩa. |

### Lỗi kiểm tra kiểu không khả thi

Compiler cũng kiểm tra tính tương thích kiểu tĩnh: không phải mọi phép `instanceof` giữa hai kiểu không liên quan đều hợp lệ. Đừng cố chữa lỗi này bằng cách ép mọi giá trị về `Object` mà không có lý do domain. Hãy thiết kế kiểu cha/interface của API đúng ý nghĩa và dùng type pattern tại ranh giới nơi dữ liệu thực sự có thể có nhiều kiểu.

### Null object so với null component

`value instanceof Submit submit` không khớp khi **value null**. Nếu `submit` đã được ràng buộc, chính object `Submit` không null. Tuy nhiên, `submit.id()` về mặt tổng quát có thể null nếu constructor/API cho phép; ở demo constructor đã cấm null/blank. **Type pattern không tự xác minh mọi component của object**.

## 14. Kiểm thử khi refactor sang type pattern

Một refactor không nên chỉ được đánh giá bằng “biên dịch thành công”. Nên kiểm tra:

1. **Đúng subtype:** mỗi subtype được phân loại vào nhánh mong đợi.
2. **Dữ liệu không thuộc kiểu:** `instanceof` trả false hoặc `switch` đi đến fallback có ý nghĩa.
3. **Null:** test selector null riêng; không giả định `default` là null case.
4. **Guard true/false:** ví dụ `Submit(10)` so với `Submit(9)`, đồng thời test case fallback `Submit`.
5. **Case dominance:** compiler từ chối hoặc test bảo đảm nhánh rộng không che nhánh hẹp.
6. **Component null/blank:** constructor hoặc boundary trả lỗi đúng hợp đồng.
7. **Lỗi/exception:** nếu bỏ cast hay thay record pattern, xác nhận loại exception và đường đi lỗi vẫn phù hợp.
8. **Tính tương thích:** thêm subtype sealed thì cập nhật case; interface mở cần có chính sách type chưa biết.
9. **Generics:** kiểm tra dữ liệu phần tử nếu nghiệp vụ cần, không chỉ kiểu collection.
10. **Hiệu năng:** benchmark nếu đây là đường nóng; không đổi cấu trúc code chỉ vì cảm giác pattern có ít opcode hơn.

### Ví dụ test JUnit Jupiter

Đây là **đoạn test riêng**, cần có JUnit Jupiter và tệp `ChooseTypePatternChecklistDemo.java` cùng package; nó **không** nằm trong chương trình độc lập của phần 10:

```java
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.*;

class ChooseTypePatternChecklistDemoTest {
    @Test
    void bulkSubmitUsesGuard() {
        var action = new ChooseTypePatternChecklistDemo.Submit("O-1", 10);
        assertEquals("BULK:O-1",
                ChooseTypePatternChecklistDemo.route(action));
    }

    @Test
    void standardSubmitFallsThroughToSecondCase() {
        var action = new ChooseTypePatternChecklistDemo.Submit("O-2", 9);
        assertEquals("SUBMIT:O-2",
                ChooseTypePatternChecklistDemo.route(action));
    }

    @Test
    void invalidIdRejectedByConstructor() {
        assertThrows(IllegalArgumentException.class,
                () -> new ChooseTypePatternChecklistDemo.Submit(" ", 1));
    }

    @Test
    void nullActionHasExplicitPolicy() {
        assertEquals("NULL_ACTION",
                ChooseTypePatternChecklistDemo.route(null));
    }
}
```

Test với `units=10` và `9` giúp bắt lỗi đổi `>=` thành `>`. Kiểm tra nhánh khác và null giúp phát hiện việc thêm `default` không phù hợp. Nếu hệ thống có domain behavior thực sự trong handler, test nên xác minh cả **side effect hoặc trạng thái**, không chỉ chuỗi trả về.

## 15. Bài tập áp dụng checklist

**Bài 1 — Chỉ cần kiểm tra kiểu**

Yêu cầu: Phương thức chỉ trả true nếu `value` là `Number`, không cần dùng giá trị ấy. Chọn gì?

**Đáp án:**

```java
static boolean isNumber(Object value) {
    return value instanceof Number;
}
```

`instanceof Number number` không sai, nhưng tạo biến thừa nếu hoàn toàn không sử dụng nó.

**Bài 2 — Chuyển nguyên object cho handler**

Yêu cầu: Nếu giá trị là `Cancel`, đưa toàn bộ command cho handler. Chọn gì?

**Đáp án:** Dùng `if (value instanceof Cancel cancel)` hoặc `case Cancel cancel`, vì handler cần **đối tượng Cancel nguyên vẹn**. Phân rã `Cancel(var id,var reason)` rồi dựng lại object không có lợi.

**Bài 3 — Đọc hai component của record**

Yêu cầu: Từ `Point(x,y)` cần tính `x*x + y*y`. Chọn gì?

**Đáp án:** Record pattern `Point(int x,int y)` làm rõ việc phân rã; type pattern `Point point` rồi gọi `x()`/`y()` vẫn hợp lệ. Chọn cách dễ đọc hơn trong ngữ cảnh.

**Bài 4 — Class không phải record**

Yêu cầu: `Heartbeat` là class thường với accessor `node()`. Có dùng `Heartbeat(var node)` được không?

**Đáp án:** Không, vì nó không phải record. Dùng `Heartbeat heartbeat` rồi gọi `heartbeat.node()`.

**Bài 5 — Kiểm tra ngưỡng**

Yêu cầu: Phân loại `Submit` có `units >= 10` thành BULK; còn lại là STANDARD. Viết `switch` thế nào?

**Đáp án:**

```java
return switch (action) {
    case Submit submit when submit.units() >= 10 -> "BULK";
    case Submit submit -> "STANDARD";
    case Cancel cancel -> "CANCEL";
    case Heartbeat heartbeat -> "HEARTBEAT";
    case null -> "NONE";
};
```

Đây là đoạn minh họa bên trong phương thức trả `String` trên `Action` sealed. Case có guard phải đứng trước case `Submit` bao quát. Không thêm `default` chỉ để bỏ qua subtype mới.

**Bài 6 — Phân loại Object và subtype không biết trước**

Yêu cầu: Input có thể là một implementation plugin mới. Có nên liệt kê vài class hiện tại rồi `default -> "SUCCESS"` không?

**Đáp án:** Không nên báo thành công cho trường hợp chưa được hỗ trợ. Cân nhắc gọi hợp đồng đa hình của interface mở hoặc trả kết quả `UNSUPPORTED`/exception có ý nghĩa tại boundary.

## 16. Checklist cuối cùng để review pull request

Trước khi chọn **type pattern**, trả lời:

- **Mục đích:** Cần biết subtype và dùng object, hay chỉ cần boolean?
- **Hợp đồng:** Có phương thức đa hình đúng nghĩa mà caller nên gọi trực tiếp không?
- **Dữ liệu:** Có thật sự cần phân rã record hoặc nested record, hay chỉ dùng một accessor?
- **Hình dạng:** Subtype là record, class thường, sealed hay interface mở?
- **Vị trí:** Type pattern trong `if` hay `switch` giúp giảm cast và làm rõ lựa chọn case?
- **Flow scope:** Mỗi lần dùng biến pattern đều nằm trên đường đi chắc chắn khớp?
- **Guard:** `&&`/`when` có kiểm tra đúng điều kiện; guard false có case tiếp theo không?
- **Thứ tự:** Case rộng có đang làm nhánh cụ thể bị dominated?
- **Null:** Đã tách selector null và nullable component theo hợp đồng?
- **Exhaustiveness:** Với sealed domain, có tận dụng kiểm tra đủ subtype thay vì thêm default che lỗi?
- **Generics:** Có nhầm kiểm tra raw/runtime type với xác thực type argument không?
- **Bảo trì:** Nếu thêm subtype hoặc thêm thao tác mới, sẽ phải sửa bao nhiêu nơi?
- **Validation:** Cấu trúc khớp kiểu chưa chắc là dữ liệu nghiệp vụ hợp lệ.
- **Testing:** Đã test subtype đúng/sai, guard true/false, null, input lạ và lỗi chưa?
- **Performance:** Đã có bằng chứng profiler/benchmark trước khi tối ưu cú pháp chưa?

## 17. Tài liệu nền

- **JEP 394 — Pattern Matching for instanceof (Java 16):** https://openjdk.org/jeps/394
- **JEP 409 — Sealed Classes (Java 17):** https://openjdk.org/jeps/409
- **JEP 440 — Record Patterns (Java 21):** https://openjdk.org/jeps/440
- **JEP 441 — Pattern Matching for switch (Java 21):** https://openjdk.org/jeps/441
- **Java Language Specification 21 — Patterns (`14.30):** https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.30
- **Java 21 Language Guide — Pattern Matching for switch:** https://docs.oracle.com/en/java/javase/21/language/pattern-matching-switch.html

**Kết luận:** Chọn **type pattern** khi cần **xác nhận subtype và dùng đối tượng đã được ràng buộc**, đặc biệt khi subtype là class thường, phải chuyển cả object cho handler, hoặc không cần phân rã dữ liệu. Chọn **record pattern** khi cấu trúc component chính là điều cần đọc. Chọn **`instanceof` thuần** khi chỉ cần boolean. Chọn **polymorphism** khi hành vi chung đã được định nghĩa. Trong mọi trường hợp, kiểm tra **flow scope, `when`/`&&`, thứ tự case, `null`, tính exhaustive và hợp đồng dữ liệu** trước khi hoàn tất refactor.
