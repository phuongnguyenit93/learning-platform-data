# Enum switch và tập giá trị cố định: viết `switch` exhaustive

> **Module:** Java Core Pattern Matching → Exhaustive switch. Trọng tâm: tính **đầy đủ (exhaustiveness)** khi `switch` nhận một giá trị thuộc `enum` — kiểu liệt kê có tập hằng số hữu hạn do khai báo kiểu xác định. Các ví dụ chính dùng **Java 21**; những nguyên tắc cơ bản về `switch expression` và `enum` cũng áp dụng cho nhiều JDK trước đó. Mã được đánh dấu **ERROR** là ví dụ cố ý không biên dịch.

## Mục tiêu học tập

Sau bài này, bạn có thể:

- Giải thích vì sao compiler biết **tất cả hằng số enum** và có thể chứng minh một `switch expression` bao phủ đủ các giá trị đó.
- Viết `switch` với `case NEW -> ...`, gộp nhiều hằng trong một `case`, và phân biệt **enum constant label** với **type pattern**.
- Hiểu vì sao `switch expression` trên enum có thể **không cần `default`** khi mọi hằng đã được liệt kê, nhưng một `switch statement` truyền thống có thể hợp lệ dù thiếu nhánh.
- Giải thích vai trò của `default`, `case null`, thay đổi tập enum theo thời gian và tác động của việc biên dịch lại.
- Thiết kế xử lý trạng thái rõ ràng, tránh bỏ sót trạng thái mới hoặc dùng `ordinal()` thay cho ý nghĩa nghiệp vụ.

## 1. Enum là một tập hằng số hữu hạn theo khai báo

Trong Java, `enum` định nghĩa một kiểu có **các đối tượng hằng được khai báo tường minh**. Ví dụ:

~~~java
enum OrderState {
    NEW,
    PROCESSING,
    DONE
}
~~~

Ở phiên bản mã nguồn này, tập các giá trị enum không null là:

~~~text
{ NEW, PROCESSING, DONE }
~~~

Một biến khai báo `OrderState state` có thể tham chiếu một trong ba hằng trên, hoặc có giá trị `null` bởi vì enum là **kiểu tham chiếu**.

~~~java
OrderState state = OrderState.PROCESSING;
boolean isDone = state == OrderState.DONE; // false
~~~

Đây là mã minh họa đặt trong một lớp/phương thức phù hợp; chưa phải chương trình độc lập.

**Đặc trưng hữu ích của enum trong switch:**

- Compiler đọc khai báo `OrderState` và biết **các tên hằng** có thể có khi biên dịch.
- Mỗi hằng là một đối tượng singleton của enum tương ứng trong class loader của nó; việc so sánh các hằng cùng enum bằng `==` là tự nhiên.
- Không thể tự viết một lớp kế thừa `OrderState` rồi tạo thêm hằng tùy ý ở bên ngoài khai báo enum.
- Tập hằng hữu hạn tại một phiên bản **không đồng nghĩa vĩnh viễn bất biến giữa các phiên bản thư viện**: người phát triển có thể chỉnh sửa khai báo enum và bổ sung `CANCELLED` sau này.

Chính đặc điểm tập giá trị hữu hạn này cho phép Java xét **exhaustiveness** theo kiểu tĩnh, thay vì phải biết tất cả đối tượng runtime riêng lẻ.

## 2. Cú pháp `case` cho enum: nhãn hằng, không phải pattern variable

Với selector có kiểu `OrderState`:

~~~java
static String label(OrderState state) {
    return switch (state) {
        case NEW -> "new";
        case PROCESSING -> "processing";
        case DONE -> "done";
    };
}
~~~

`case NEW`, `case PROCESSING` và `case DONE` là các **enum constant labels**. Chúng so sánh selector với **hằng enum được chỉ định**. Chúng **không khai báo biến mới**, khác với:

~~~java
case String text -> text.toUpperCase(); // Type pattern nếu selector phù hợp.
~~~

Type pattern `String text` tạo ra biến `text`; nhãn hằng `case NEW` chỉ chọn một giá trị đã đặt tên.

### Gộp nhiều enum constants

Khi các trạng thái dùng cùng hành vi:

~~~java
static String phase(OrderState state) {
    return switch (state) {
        case NEW, PROCESSING -> "open";
        case DONE -> "closed";
    };
}
~~~

Một nhãn `case NEW, PROCESSING` đại diện cho **hai hằng enum**. Về độ bao phủ, compiler tính cả `NEW` và `PROCESSING`; kết hợp với `DONE`, mọi hằng của `OrderState` đã xuất hiện.

Dùng dấu phẩy trong cùng nhãn `case` **không phải fall-through**. Với cú pháp `->`, chỉ nhánh được chọn chạy, không cần `break`. Cú pháp nhóm label cũ dạng `case NEW: case PROCESSING:` cũng tồn tại, nhưng cách viết với `->` rõ ràng và giảm lỗi rơi xuyên.

### Nhãn hằng phải thuộc kiểu phù hợp

Nếu selector có kiểu `OrderState`, bạn không thể dùng một hằng thuộc enum không tương thích hoặc tên không tồn tại:

~~~java
enum OrderState { NEW, PROCESSING, DONE }

// ERROR: Không hề khai báo hằng CANCELLED trong OrderState.
static String broken(OrderState state) {
    return switch (state) {
        case NEW -> "new";
        case PROCESSING -> "processing";
        case DONE -> "done";
        case CANCELLED -> "cancelled"; // ERROR.
    };
}
~~~

Compiler kiểm tra điều này **trước khi chương trình chạy**. Đừng nhầm nhãn enum với chuỗi: `case "NEW"` không thể thay `case NEW` khi selector có kiểu enum.

## 3. `Exhaustive switch` nghĩa là gì?

Một `switch` được coi là **exhaustive** khi các nhãn của nó bao phủ mọi giá trị thuộc tập giá trị của kiểu selector theo quy tắc ngôn ngữ, hoặc có `default` làm nhánh dự phòng.

Với `OrderState`:

| Hằng enum | Nhãn xử lý |
| --- | --- |
| `NEW` | `case NEW` |
| `PROCESSING` | `case PROCESSING` |
| `DONE` | `case DONE` |

Đủ cả ba ⇒ bộ nhãn enum **bao phủ toàn bộ enum**. Nếu thiếu một hằng mà không có `default`, một **switch expression** sẽ bị compiler từ chối.

Ví dụ hoàn chỉnh về mặt phương thức:

~~~java
static String label(OrderState state) {
    return switch (state) {
        case NEW -> "new";
        case PROCESSING -> "processing";
        case DONE -> "done";
    };
}
~~~

**Không có `default` vẫn hợp lệ.** Compiler Java 21 có thể chứng minh rằng mọi giá trị `OrderState` không null đều match một nhãn. Tài liệu Oracle mô tả compiler cung cấp nhánh mặc định ngầm cho enum switch expression exhaustive. Bạn không phải tự đoán trạng thái bị bỏ sót.

### Ví dụ cố ý không biên dịch

~~~java
static String incomplete(OrderState state) {
    return switch (state) {
        case NEW -> "new";
        case PROCESSING -> "processing";
        // ERROR: còn DONE mà không có nhãn xử lý.
    };
}
~~~

Đây là **lỗi compile time**, không phải chương trình chạy rồi mới ném lỗi vì thiếu `DONE`. Một `switch expression` phải tạo giá trị hoặc ném ngoại lệ cho mọi nhánh được xét, nên compiler không cho phép một giá trị enum hợp lệ rơi ra ngoài `switch` mà không có kết quả.

**Cách sửa tốt nhất cho nghiệp vụ cần phân biệt từng trạng thái:** thêm `case DONE -> "done";`. Đôi khi thêm `default` là một lựa chọn có chủ đích, nhưng nó thay đổi khả năng compiler nhắc bạn khi enum được mở rộng (xem phần 6).

## 4. `switch expression` khác `switch statement` truyền thống

Đây là điểm thường gây hiểu nhầm nhất khi học exhaustiveness.

### 4.1. `Switch expression` phải exhaustive

`Switch expression` có dạng:

~~~java
String description = switch (state) {
    case NEW -> "new";
    case PROCESSING -> "working";
    case DONE -> "finished";
};
~~~

Nó trả về một giá trị được gán cho `description`, và **phải có cách tạo giá trị hoặc throw** trong mọi trường hợp mà compiler yêu cầu. Nhánh có block dùng `yield` để trả về kết quả:

~~~java
String description = switch (state) {
    case NEW -> "new";
    case PROCESSING -> {
        String message = "working";
        yield message;
    }
    case DONE -> "finished";
};
~~~

Ở ví dụ này, tập nhãn enum exhaustive nên không cần `default`. Không dùng `break "value"` để trả kết quả: `yield` mới là cơ chế của switch expression khi nhánh có block.

### 4.2. `Switch statement` cơ bản trên enum có thể **không** exhaustive

Ví dụ **hợp lệ** ngay cả trong Java 21:

~~~java
static void logOnlyNew(OrderState state) {
    switch (state) {
        case NEW -> System.out.println("new order");
    }
}
~~~

Nếu `state == DONE` hoặc `state == PROCESSING`, không nhãn nào áp dụng, và **switch statement cơ bản hoàn thành mà không làm gì**. Không có lỗi biên dịch chỉ vì bỏ sót hai hằng.

Lý do là **tương thích với Java cũ**. Theo JLS 21 `14.11, một switch statement chỉ dùng enum constant labels và không có pattern/null label là một **basic switch statement**; nó không bắt buộc exhaustive như switch expression.

**Hệ quả thực tế:** Đừng nghĩ cú pháp mũi tên `->` tự động khiến mọi switch statement phải exhaustive. Điều kiện bắt buộc không nằm ở mũi tên, mà ở **loại switch** và các nhãn được dùng.

### 4.3. `Enhanced switch statement` trong Java 21 lại phải exhaustive

Trong Java 21, một switch statement trở thành **enhanced** nếu dùng case pattern hoặc `case null`, hoặc selector thuộc loại không được switch truyền thống hỗ trợ. Enhanced switch statement **phải exhaustive**.

Ví dụ sau **cố ý không biên dịch**:

~~~java
static void brokenNullAware(OrderState state) {
    switch (state) {
        case null -> System.out.println("missing");
        case NEW -> System.out.println("new");
        // ERROR: enhanced switch statement chưa bao phủ PROCESSING, DONE.
    }
}
~~~

Ở đây chỉ cần thêm `case null` cũng làm switch statement thuộc nhóm enhanced; việc thiếu `PROCESSING` và `DONE` không còn được bỏ qua như basic enum switch statement.

**Sửa:** bổ sung các nhánh enum còn thiếu hoặc thêm `default` phù hợp.

### Bảng đối chiếu nhanh

| Tình huống trong Java 21 | Cần exhaustive? | Nếu thiếu hằng enum và không có `default` |
| --- | --- | --- |
| `return switch (enumValue) { ... };` | **Có** | Lỗi biên dịch |
| `switch (enumValue) { case NEW -> ...; }` chỉ có nhãn hằng | **Không bắt buộc** | Biên dịch được; giá trị không match ⇒ không làm gì |
| `switch (enumValue) { case null -> ...; case NEW -> ...; }` | **Có** | Lỗi biên dịch |
| Switch statement có pattern label | **Có** | Phải có type coverage/default phù hợp |
| Enum switch expression có `default` | **Có thể được bao phủ nhờ default** | Hợp lệ, nhưng enum mới có thể vào default |

**Kết luận:** Khi muốn compiler ép kiểm kê hết các trạng thái enum, ưu tiên **switch expression không `default`** và liệt kê toàn bộ hằng hiện có.

## 5. `null` là trường hợp riêng, không phải hằng enum

Một biến enum là tham chiếu, vì vậy:

~~~java
OrderState state = null; // Hợp lệ ở mức kiểu.
~~~

`null` **không phải** hằng `NEW`, `PROCESSING` hay `DONE`. Do đó, một switch expression liệt kê đủ ba hằng vẫn có thể ném `NullPointerException` nếu selector là `null` và không có nhãn xử lý null.

~~~java
static String label(OrderState state) {
    return switch (state) {
        case NEW -> "new";
        case PROCESSING -> "processing";
        case DONE -> "done";
    };
}

// label(null) -> NullPointerException trong Java 21.
~~~

### Xử lý null tường minh (Java 21+)

~~~java
static String safeLabel(OrderState state) {
    return switch (state) {
        case null -> "missing";
        case NEW -> "new";
        case PROCESSING -> "processing";
        case DONE -> "done";
    };
}
~~~

`case null` được hỗ trợ chính thức trong Java 21; nó bắt giá trị null trước khi chọn một enum case. **Không cần `default`** vì các hằng đã được liệt kê đầy đủ và null được xử lý riêng.

**Quan trọng:** `default` đơn lẻ không tự bắt null:

~~~java
static String misleading(OrderState state) {
    return switch (state) {
        case DONE -> "done";
        default -> "not done";
    };
}

// misleading(null) -> NullPointerException, KHÔNG trả "not done".
~~~

Nếu muốn gộp null và các trường hợp còn lại một cách có chủ đích, Java 21 cho phép `case null, default -> ...`. Tuy nhiên, tách `case null` riêng thường rõ ràng hơn khi dữ liệu thiếu là lỗi hoặc trạng thái nghiệp vụ khác biệt.

### Khi nào nên từ chối null?

Nếu enum là tham số nghiệp vụ bắt buộc, có thể kiểm tra ở ranh giới API:

~~~java
static String requireState(OrderState state) {
    java.util.Objects.requireNonNull(state, "state");
    return switch (state) {
        case NEW -> "new";
        case PROCESSING -> "processing";
        case DONE -> "done";
    };
}
~~~

Bây giờ `null` bị từ chối có thông báo rõ nghĩa ngay tại boundary, còn switch tập trung vào tập enum hợp lệ. Chọn **xử lý null** hay **từ chối null** theo hợp đồng API; không bỏ mặc cho hành vi mặc định tình cờ.

## 6. Khi thêm hằng enum mới, điều gì xảy ra?

Ban đầu:

~~~java
enum OrderState {
    NEW, PROCESSING, DONE
}
~~~

Sau một yêu cầu mới, sản phẩm bổ sung:

~~~java
enum OrderState {
    NEW, PROCESSING, DONE, CANCELLED
}
~~~

Có ba tình huống cần phân biệt.

### 6.1. Biên dịch lại code dùng switch expression **không default**

~~~java
static String label(OrderState state) {
    return switch (state) {
        case NEW -> "new";
        case PROCESSING -> "processing";
        case DONE -> "done";
    };
}
~~~

Khi compiler nhìn thấy khai báo enum **đã có `CANCELLED`**, nó sẽ báo `switch expression does not cover all possible input values` hoặc thông báo tương đương. Lúc này việc thiếu nhánh là **lỗi biên dịch hữu ích**, giúp bắt buộc người phát triển trả lời câu hỏi: trạng thái bị hủy phải được xử lý ra sao?

Sửa:

~~~java
case CANCELLED -> "cancelled";
~~~

Dòng trên là **nhãn minh họa**, cần đặt trong switch expression đúng ngữ cảnh.

### 6.2. Có `default` sẵn: mã có thể tiếp tục biên dịch mà không nhắc

~~~java
static String labelWithDefault(OrderState state) {
    return switch (state) {
        case DONE -> "done";
        default -> "other";
    };
}
~~~

Sau khi enum thêm `CANCELLED`, compiler vẫn thấy `default` nên biểu thức exhaustive. Giá trị mới đi vào `"other"`. Đây có thể là **hành vi mong muốn** khi mọi trạng thái lạ đều dùng chung cách xử lý, nhưng là rủi ro nếu nghiệp vụ cần nhánh riêng cho trạng thái hủy.

**Quy tắc thực hành:** Nếu mỗi trạng thái enum đều có ý nghĩa riêng, tránh `default` chung chung; để compiler báo khi enum tiến hóa. Nếu fallback thực sự là hợp đồng nghiệp vụ, dùng `default` nhưng **kiểm thử trạng thái mới** và ghi rõ ý định.

### 6.3. Thay enum đã biên dịch, **không** biên dịch lại code switch cũ

Đây là bài toán **binary evolution**: một module đã biên dịch switch expression khi enum chỉ có ba hằng, nhưng lúc chạy nó nhận enum từ thư viện đã được cập nhật có thêm hằng mới.

Theo JLS Java 21, nếu **switch expression** được coi là exhaustive tại compile time mà runtime gặp giá trị **không khớp bất kỳ case label nào**, nó ném **`MatchException`** (trong điều kiện không có nhánh default bắt giá trị mới). Nếu selector là null mà không có nhãn null, ngữ nghĩa tương ứng là `NullPointerException`.

Phân biệt:

- **Biên dịch lại cùng nguồn enum mới:** compiler có cơ hội báo thiếu `CANCELLED`.
- **Chỉ cập nhật enum/library rồi chạy bytecode cũ:** compiler không được chạy lại trên code switch; đường runtime thiếu nhãn có thể xuất hiện và ném `MatchException` theo ngữ nghĩa Java 21.
- **Switch statement cơ bản thiếu nhánh:** nếu không có nhãn match, nó có thể **bỏ qua xử lý** thay vì tạo kết quả, theo JLS `14.11.3.

Đừng giả định một ứng dụng luôn tự động an toàn trước thay đổi enum giữa các module triển khai độc lập. Khi nâng phiên bản thư viện chứa enum, hãy biên dịch lại mã phụ thuộc và chạy kiểm thử toàn bộ nhánh.

## 7. Enum switch và tính bao phủ của pattern switch

### 7.1. Tập hằng enum là một cách chứng minh exhaustive

Với selector kiểu `OrderState`, ba nhãn `case NEW`, `case PROCESSING`, `case DONE` đủ để bao phủ enum. Đây là **enum constant coverage**, không cần type pattern.

### 7.2. Pattern switch trên selector rộng hơn có bài toán khác

Ví dụ selector kiểu `Object` có thể chứa `OrderState`, `String`, `Integer` hoặc loại bất kỳ:

~~~java
static String describeAny(Object input) {
    return switch (input) {
        case OrderState state -> "order state: " + state.name();
        case String text -> "text: " + text;
        default -> "other";
    };
}
~~~

Ở đây `case OrderState state` là **type pattern**. Nó xác nhận runtime object có thuộc kiểu enum `OrderState` không, rồi bind `state`. Nó **không** liệt kê từng hằng enum. `default` cần cho các kiểu `Object` không match hai type patterns trên (hoặc một nhánh tổng quát tương đương).

Nếu bạn cần xử lý **từng hằng** sau khi xác nhận `OrderState`, có thể lồng một switch expression trên biến `state`:

~~~java
static String describeAny(Object input) {
    return switch (input) {
        case OrderState state -> switch (state) {
            case NEW -> "new";
            case PROCESSING -> "processing";
            case DONE -> "done";
        };
        default -> "not an OrderState";
    };
}
~~~

Đây là ví dụ về hai cấp kiểm tra:

- Switch ngoài: **kiểu tham chiếu** của `Object`.
- Switch trong: **tập hằng hữu hạn** của enum.

Không nhầm `case OrderState state` (type pattern) với `case NEW` (enum constant label).

### 7.3. Một enum là tập đóng theo khai báo, nhưng có thể có hợp đồng dữ liệu bên ngoài

Nếu trạng thái được nhận từ HTTP/JSON/database dưới dạng chuỗi `"NEW"`, đó là **String**, chưa phải `OrderState`. Hãy chuyển dữ liệu vào enum ở ranh giới hệ thống bằng API phù hợp, kiểm tra trường hợp không hợp lệ, rồi mới đưa enum vào switch.

~~~java
static OrderState parseState(String raw) {
    if (raw == null) {
        throw new IllegalArgumentException("state is required");
    }
    try {
        return OrderState.valueOf(raw);
    } catch (IllegalArgumentException ex) {
        throw new IllegalArgumentException("Unknown state: " + raw, ex);
    }
}
~~~

`Enum.valueOf` đòi **đúng tên hằng**, phân biệt hoa/thường; một chuỗi không hợp lệ gây `IllegalArgumentException`. Đừng dùng `ordinal()` để mã hóa trạng thái nghiệp vụ lâu dài: chèn/đổi thứ tự hằng có thể đổi ordinal của các giá trị cũ.

Các phương thức trong phần 7 là **mã minh họa** đặt trong một lớp có enum `OrderState`; không phải chương trình độc lập. Phần 9 cung cấp ví dụ chạy được.

## 8. Cách thiết kế enum switch dễ bảo trì

### 8.1. Liệt kê mọi hằng khi mỗi trạng thái cần xử lý riêng

~~~java
static String action(OrderState state) {
    return switch (state) {
        case NEW -> "validate";
        case PROCESSING -> "monitor";
        case DONE -> "archive";
    };
}
~~~

Code này ép nhóm phát triển xử lý khi enum có hằng mới lúc biên dịch lại. **Không nên thêm `default -> "unknown"` chỉ để che lỗi compile time** khi nghiệp vụ thực sự chưa định nghĩa cách xử lý hằng mới.

### 8.2. Gộp nhánh nếu đúng theo ý nghĩa nghiệp vụ

~~~java
static boolean isOpen(OrderState state) {
    return switch (state) {
        case NEW, PROCESSING -> true;
        case DONE -> false;
    };
}
~~~

Gộp `NEW` và `PROCESSING` vì cùng thuộc trạng thái mở, không phải vì tiện rút ngắn code. Nếu sau này thêm `CANCELLED`, compiler sẽ yêu cầu quyết định `CANCELLED` là mở hay đóng.

### 8.3. Khi một nhánh thật sự là tình huống lỗi, dùng `throw`

~~~java
static int progressPercent(OrderState state) {
    return switch (state) {
        case NEW -> 0;
        case PROCESSING -> 50;
        case DONE -> 100;
    };
}
~~~

Nếu trong một biến thể khác có trạng thái bị cấm tại nơi gọi, một nhánh cụ thể có thể `throw new IllegalStateException("...")` thay vì sinh giá trị. Việc nhánh `throw` hoàn thành đột ngột vẫn là cách xử lý hợp lệ trong switch expression; chỉ cần đảm bảo **mọi hằng đều được bao phủ**.

### 8.4. Không ép dùng switch cho mọi enum

Nếu nhiều trạng thái có cùng một thuộc tính ổn định, có thể cân nhắc đưa hành vi vào enum hoặc một cấu trúc mapping với kiểm tra bao phủ riêng. `switch expression` đặc biệt phù hợp khi điều bạn muốn là **compiler buộc mỗi trạng thái có một quyết định**, rõ ràng tại chỗ gọi.

### 8.5. Kiểm thử không thay thế kiểm tra exhaustiveness

Kiểm thử theo `OrderState.values()` là hữu ích:

~~~java
for (OrderState state : OrderState.values()) {
    System.out.println(state + " => " + action(state));
}
~~~

`values()` trả mảng các hằng được khai báo tại runtime. Bài kiểm thử như trên có thể bắt sai logic trong mỗi nhánh, nhưng **compiler** mới là nơi phát hiện thiếu nhánh của switch expression ngay khi mã được biên dịch với enum mới. Cần cả hai cho hệ thống quan trọng.

## 9. Chương trình Java 21 chạy đầy đủ

Lưu tệp **`EnumExhaustiveDemo.java`**:

~~~java
public class EnumExhaustiveDemo {

    enum OrderState {
        NEW, PROCESSING, DONE
    }

    // Exhaustive enum switch expression: không cần default.
    static String describe(OrderState state) {
        return switch (state) {
            case NEW -> "new";
            case PROCESSING -> "processing";
            case DONE -> "done";
        };
    }

    // Gộp các hằng có cùng ý nghĩa.
    static String phase(OrderState state) {
        return switch (state) {
            case NEW, PROCESSING -> "open";
            case DONE -> "closed";
        };
    }

    // Có default: trạng thái không phải DONE dùng kết quả chung.
    static String fallback(OrderState state) {
        return switch (state) {
            case DONE -> "done";
            default -> "not done";
        };
    }

    // Java 21: xử lý null tường minh.
    static String nullSafe(OrderState state) {
        return switch (state) {
            case null -> "missing";
            case NEW -> "new";
            case PROCESSING, DONE -> "existing";
        };
    }

    // Basic switch statement: không bắt buộc exhaustive.
    static void statement(OrderState state) {
        switch (state) {
            case NEW -> System.out.println("statement: NEW");
        }
    }

    public static void main(String[] args) {
        for (OrderState state : OrderState.values()) {
            System.out.println(
                    state + " => " + describe(state) + ", " + phase(state)
            );
        }

        System.out.println("fallback=" + fallback(OrderState.PROCESSING));
        System.out.println("null=" + nullSafe(null));

        statement(OrderState.DONE);
        System.out.println("statement: after DONE");
        statement(OrderState.NEW);

        try {
            describe(null);
        } catch (NullPointerException ex) {
            System.out.println("without null: NPE");
        }
    }
}
~~~

Biên dịch và chạy bằng **JDK 21+**:

~~~bash
javac --release 21 EnumExhaustiveDemo.java
java EnumExhaustiveDemo
~~~

**Stdout chính xác:**

~~~text
NEW => new, open
PROCESSING => processing, open
DONE => done, closed
fallback=not done
null=missing
statement: after DONE
statement: NEW
without null: NPE
~~~

**Giải thích kết quả:**

1. Vòng lặp `OrderState.values()` đi qua ba hằng trong thứ tự khai báo, mỗi hằng được `describe` và `phase` xử lý bằng switch expression đã exhaustive.
2. `fallback(PROCESSING)` trả `not done` vì chỉ `DONE` có nhánh riêng; `default` nhận `PROCESSING`.
3. `nullSafe(null)` trả `missing` vì có `case null`.
4. `statement(DONE)` **không in gì** vì basic switch statement không có nhãn `DONE`. Vì vậy ngay sau các dòng đầu chỉ thấy `statement: after DONE`.
5. `statement(NEW)` in `statement: NEW`.
6. `describe(null)` ném `NullPointerException`, được `catch` trong demo chuyển thành dòng `without null: NPE`. Dù `describe` có đủ ba enum case, nó không tự xử lý null.

### Ba đoạn cố ý sai để thử compiler

**Thiếu enum constant trong switch expression**:

~~~java
static String incomplete(OrderState state) {
    return switch (state) {
        case NEW -> "new";
        case PROCESSING -> "processing";
        // ERROR: thiếu DONE và không có default.
    };
}
~~~

**Thiếu nhãn trong enhanced switch statement có `case null`**:

~~~java
static void incompleteEnhanced(OrderState state) {
    switch (state) {
        case null -> System.out.println("null");
        case NEW -> System.out.println("new");
        // ERROR: còn PROCESSING và DONE.
    }
}
~~~

**Trùng enum constant trong switch**:

~~~java
static String duplicate(OrderState state) {
    return switch (state) {
        case NEW -> "a";
        case NEW -> "b"; // ERROR: duplicate case label.
        case PROCESSING -> "c";
        case DONE -> "d";
    };
}
~~~

Ba phương thức này chỉ nhằm minh họa **lỗi biên dịch** trong một lớp có enum `OrderState`; đừng chép vào lớp demo nếu muốn giữ bản chạy được.

## 10. Lỗi thường gặp và cách sửa

| Hiểu nhầm/lỗi | Điều đúng trong Java 21 | Cách khắc phục |
| --- | --- | --- |
| “Enum switch luôn exhaustive.” | Chỉ một số dạng bắt buộc; basic switch statement có thể thiếu nhánh | Dùng switch expression để compiler kiểm tra hoặc tự liệt kê nhánh |
| “Muốn switch expression hợp lệ phải có default.” | Với enum, đủ mọi hằng thì **không cần default** | Liệt kê toàn bộ hằng |
| “Default bắt được null.” | `null` không tự đi vào `default` | Dùng `case null` hoặc kiểm tra ở API boundary |
| “Có default là an toàn hơn trước enum mới.” | Default có thể **che mất** việc thêm trạng thái cần xử lý riêng | Bỏ default nếu mong compiler báo thiếu hằng mới |
| “Gộp `case NEW, PROCESSING` sẽ bỏ một nhánh.” | Gộp vẫn tính đủ cả hai hằng | Chỉ gộp khi logic nghiệp vụ giống nhau |
| “Mọi nhãn enum đều là type pattern.” | `case NEW` là nhãn hằng; `case OrderState state` mới là type pattern | Phân biệt nhãn hằng với biến được bind |
| “Dùng `case "NEW"` cho selector OrderState.” | Chuỗi khác kiểu enum | Dùng `case NEW` |
| “Có `case null` thì switch statement vẫn có thể bỏ sót enum constants.” | `case null` làm nó enhanced và cần exhaustive | Thêm mọi hằng còn thiếu hoặc default |
| “Compiler sẽ tự báo khi thư viện enum thay đổi lúc ứng dụng chạy.” | Không có bước biên dịch lại thì không thể có chẩn đoán compile time mới | Biên dịch lại các module phụ thuộc và chạy test |
| “`ordinal()` là mã số trạng thái ổn định.” | Thứ tự hằng có thể thay đổi khi chỉnh enum | Lưu mã nghiệp vụ riêng hoặc tên hằng theo hợp đồng |
| “Không có case match sẽ luôn ném lỗi.” | Basic statement có thể hoàn thành bình thường; expression có đường runtime ngoại lệ khi thiếu label | Hiểu loại switch đang dùng |

## 11. Quy trình rà soát enum switch trước khi merge

1. **Xác định kiểu selector:** có đúng `OrderState` hay là `Object/String`? Không áp dụng suy luận về enum constant coverage cho selector quá rộng.
2. **Liệt kê tập hằng đang khai báo:** `NEW`, `PROCESSING`, `DONE`. Ghi nhận null có thể xuất hiện theo hợp đồng API.
3. **Xác định loại switch:** expression, basic statement, hay enhanced statement? Từ đó biết có bắt buộc exhaustive không.
4. **So khớp các nhãn:** mỗi hằng có xuất hiện trong một `case` (kể cả case gộp) không? Có nhãn lặp/trùng không?
5. **Đánh giá `default`:** có thực sự muốn fallback, hay nó che mất yêu cầu xử lý hằng mới?
6. **Quy định null:** sử dụng `case null` ở Java 21 hoặc kiểm tra đầu vào ở boundary. Đừng trông chờ default.
7. **Kiểm tra thay đổi enum/library:** đã biên dịch lại các client và chạy thử sau khi bổ sung hằng mới chưa?
8. **Kiểm thử kết quả:** thử từng trạng thái qua `values()`, thử null nếu API cho phép, và thử hành vi khi dữ liệu nguồn không hợp lệ.

## 12. Bài tập tự kiểm tra

**Câu 1.** Với `enum Color { RED, GREEN, BLUE }`, switch expression dưới đây có biên dịch không? Vì sao?

~~~java
return switch (color) {
    case RED -> "R";
    case GREEN -> "G";
};
~~~

**Câu 2.** Cũng enum `Color` ấy, một **switch statement** chỉ có `case RED -> println("red");` có biên dịch không? Nếu `color == BLUE` thì điều gì xảy ra?

**Câu 3.** Cần thêm nhãn gì để switch expression trong câu 1 exhaustive mà **không có default**?

**Câu 4.** Nếu thêm hằng `YELLOW` và biên dịch lại một switch expression từng liệt kê đủ ba hằng, nhưng không có `default`, điều gì xảy ra?

**Câu 5.** Nếu switch expression đó có `default -> "other"` ngay từ đầu thì sao khi thêm `YELLOW`? Lợi và hại?

**Câu 6.** `case RED, GREEN -> "warm"` có được tính là bao phủ cả hai hằng không? Có phải type pattern không?

**Câu 7.** Switch expression enum có đủ tất cả các case, nhưng truyền `null`. Nó trả giá trị nào nếu không có `case null`?

**Câu 8.** Một switch statement có `case null`, chỉ xử lý `RED`, không có `default` và bỏ qua `GREEN`, `BLUE`. Nó có còn là basic switch statement không? Compiler nói gì?

**Câu 9.** Phân biệt `case Color c -> ...` và `case RED -> ...` về kiểu selector và khả năng bind biến.

**Câu 10.** Vì sao một enum switch expression đã exhaustive khi biên dịch có thể gặp `MatchException` sau khi chỉ cập nhật thư viện chứa enum mà không biên dịch lại mã switch?

**Câu 11.** Khi enum bổ sung hằng `CANCELLED`, tại sao lưu trạng thái bằng `ordinal()` hoặc giả định ordinal không đổi là nguy hiểm?

**Câu 12.** Với nghiệp vụ “`NEW` và `PROCESSING` là mở; `DONE` là đóng”, viết switch expression trả `boolean` không dùng default và đề xuất test cho mỗi hằng.

### Đáp án gợi ý

1. **Không.** Thiếu `BLUE`, mà switch expression phải exhaustive.
2. **Có.** Basic switch statement trên enum không bắt buộc exhaustive; với `BLUE`, nó kết thúc mà không in dòng nào.
3. Thêm `case BLUE -> "B";`.
4. Compiler thấy thêm `YELLOW` và báo switch expression không exhaustive, buộc cập nhật nhánh.
5. Vẫn biên dịch được, `YELLOW` đi vào `default`. Có ích nếu thực sự muốn fallback, nhưng làm mất cảnh báo bắt buộc xử lý trạng thái mới.
6. **Có**, bao phủ `RED` và `GREEN`; đây là **enum constant label list**, không phải type pattern.
7. **Ném `NullPointerException`** trong Java 21 nếu không có xử lý null phù hợp.
8. Không. `case null` làm statement thành **enhanced**, nên compiler yêu cầu exhaustive; thiếu `GREEN` và `BLUE` gây lỗi.
9. `case Color c` là **type pattern**, thường dùng khi selector có kiểu rộng hơn như `Object`, tạo biến `c`; `case RED` so khớp hằng enum khi selector có kiểu enum phù hợp, không bind biến.
10. Bytecode switch được biên dịch với tập hằng cũ; một hằng mới không có nhãn ở runtime khiến switch expression không chọn được nhánh và có thể ném `MatchException` theo JLS 21. Cần biên dịch lại client.
11. `ordinal()` phản ánh vị trí hằng trong khai báo; chèn/đổi thứ tự có thể đổi số của các hằng khác. Dùng tên hoặc mã nghiệp vụ có hợp đồng rõ ràng.
12. Ví dụ `return switch(state) { case NEW, PROCESSING -> true; case DONE -> false; };`. Chạy thử cả ba giá trị hoặc lặp `Color.values()`/`OrderState.values()` tương ứng với enum được dùng.

## Tài liệu tham khảo chính thức

- [Oracle Java 21 — Switch Expressions and Statements](https://docs.oracle.com/en/java/javase/21/language/switch-expressions-and-statements.html): tập enum, exhaustiveness của switch expression, switch statement và cách gộp case.
- [Java Language Specification 21 — `14.11.1.1 Exhaustive Switch Blocks](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.11.1.1): quy tắc enum coverage; mọi enum constant được liệt kê thì không cần default.
- [Java Language Specification 21 — `14.11.2 The Switch Block of a switch Statement](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.11.2): phân biệt enhanced/basic switch statement và yêu cầu exhaustive.
- [Java Language Specification 21 — `14.11.3 Execution of a switch Statement](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.11.3): nếu không nhãn nào match, basic statement có thể kết thúc bình thường.
- [Java Language Specification 21 — `15.28 Switch Expressions](https://docs.oracle.com/javase/specs/jls/se21/html/jls-15.html#jls-15.28): chọn nhánh; `MatchException` hoặc `NullPointerException` khi không có nhãn áp dụng.
- [Java Language Specification 21 — `8.9 Enum Classes](https://docs.oracle.com/javase/specs/jls/se21/html/jls-8.html#jls-8.9): mô hình enum và tập enum constants.
