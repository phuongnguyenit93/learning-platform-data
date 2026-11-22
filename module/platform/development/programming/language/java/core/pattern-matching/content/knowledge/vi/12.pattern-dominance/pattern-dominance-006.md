# Case default và dominance trong Java Pattern Matching for switch

## 1. Mục tiêu: hiểu chính xác quan hệ giữa `default` và các `case` khác

Trong Java, `switch` chọn một nhánh dựa trên giá trị của biểu thức selector. Với **Pattern Matching for switch** (chuẩn hóa ở **Java 21**, JEP 441), một `case` có thể kiểm tra kiểu của đối tượng bằng type pattern, ví dụ `case String s`, hoặc kiểm tra thêm điều kiện bằng `when`.

Khi kết hợp các case hằng, case pattern và nhãn `default`, người viết phải hiểu hai khái niệm riêng:

- **Dominance (nhánh bị thống trị/che khuất):** một nhãn case nằm trước đã bao phủ các giá trị mà nhãn case ở sau có thể khớp. Trình biên dịch ngăn nhiều trường hợp như vậy vì nhánh sau trở nên không thể được lựa chọn.
- **Default:** nhãn dự phòng khi không nhãn case thích hợp nào khác nhận giá trị (đối với selector khác `null`); nó **không tự khai báo biến pattern** và **không tự xử lý `null`**.

Ví dụ Java 21 **hợp lệ**:

```java
static String describe(Object value) {
    return switch (value) {
        case String text -> "TEXT:" + text;
        case Integer n   -> "INTEGER:" + n;
        case null        -> "NULL";
        default          -> "OTHER";
    };
}
```

Một giá trị `String` được nhánh `case String text` xử lý; `Integer` đi vào nhánh `case Integer n`; `null` có nhãn riêng; mọi giá trị không khớp các case còn lại đi vào `default`.

**Quy tắc nền tảng:** `default` không phải lối thoát khỏi các quy tắc của pattern switch. Thêm `default` có thể làm một switch exhaustive, nhưng không sửa được **dominated case**, case bị đặt sai thứ tự hoặc khai báo pattern variable không hợp lệ.

Bài này phân tích cả **quy tắc thường dùng** lẫn **ngoại lệ tương thích ngược** của Java 21: `default` nên đứng cuối, nhưng đặc tả vẫn cho phép `default` đứng trước những case **chỉ chứa hằng** trong một số cấu trúc. Ngược lại, `default` đứng trước case pattern hoặc `case null` gây lỗi biên dịch.

Các ví dụ hoàn chỉnh trong bài dùng **Java 21 trở lên, không bật preview**. Các đoạn ghi “KHÔNG BIÊN DỊCH” chỉ nhằm giải thích lỗi, không đưa vào chương trình chạy độc lập.

## 2. Dominance là gì?

Xét trường hợp hai case pattern trên cùng selector `Object value`:

```java
// KHÔNG BIÊN DỊCH trên Java 21:
// return switch (value) {
//     case Number number -> "NUMBER";
//     case Integer n     -> "INTEGER"; // Bị Number thống trị.
//     default            -> "OTHER";
// };
```

`Integer` là lớp con của `Number`. Mọi đối tượng `Integer` đều khớp `case Number number`. Vì case tổng quát đứng trước, `case Integer n` phía sau không bao giờ có cơ hội là nhánh được chọn. Đây là lỗi **dominated case label** tại thời điểm biên dịch.

**Cách sửa: case chuyên biệt đứng trước:**

```java
static String numberKind(Object value) {
    return switch (value) {
        case Integer n    -> "INTEGER:" + n;
        case Number other -> "NUMBER:" + other;
        default           -> "OTHER";
    };
}
```

Khi nhận `Integer.valueOf(5)`, nhánh đầu được chọn; khi nhận `Double.valueOf(2.5)`, nhánh `Number other` được chọn. `default` chỉ xử lý các kiểu không khớp hai pattern trên.

Điều đáng chú ý: **`default` ở cuối không làm cho `case Integer n` phía sau `case Number number` hợp lệ**. Lỗi là do **quan hệ bao phủ giữa hai case patterns**, không phải do thiếu nhánh dự phòng.

### 2.1. “Bao phủ” có thể xảy ra giữa pattern và hằng

```java
// KHÔNG BIÊN DỊCH:
// return switch (value) {
//     case Integer n -> "INTEGER";
//     case 42        -> "FORTY_TWO"; // 42 luôn khớp Integer.
//     default        -> "OTHER";
// };
```

Với selector kiểu `Object`, hằng số `42` được so theo nhánh hằng hợp lệ. Nhưng `case Integer n` không guard trước đó đã khớp mọi giá trị `Integer`, trong đó có `42`, nên nhánh hằng đứng sau bị che khuất.

**Đặt case constant trước pattern tổng quát:**

```java
static String classifyInteger(Object value) {
    return switch (value) {
        case 42        -> "FORTY_TWO";
        case Integer n -> "INTEGER:" + n;
        default        -> "OTHER";
    };
}
```

Tương tự với enum: nếu `case State state` đã nhận mọi hằng của `State`, thì `case State.FAILED` nằm sau nó sẽ bị dominated. Muốn xử lý riêng một hằng enum, đặt `case State.FAILED` trước `case State state`.

### 2.2. Dominance khác với exhaustiveness

Hai phép kiểm tra của trình biên dịch giải quyết hai câu hỏi khác nhau:

| Khái niệm | Câu hỏi | Lỗi điển hình |
| --- | --- | --- |
| **Dominance** | Một nhánh đứng sau có bị nhánh đứng trước bao phủ không? | `Number` đứng trước `Integer` |
| **Exhaustiveness** | Toàn bộ những giá trị theo kiểu selector có nhánh xử lý không? | Switch expression trên `Object` chỉ có `case String`, thiếu nhánh còn lại |

Một switch có thể **exhaustive nhờ `default` mà vẫn bị lỗi dominance**, và một switch không có nhánh bị dominated vẫn có thể **thiếu tính exhaustive**.

## 3. `default` hoạt động như thế nào?

Nhãn `default` là lựa chọn cuối khi một giá trị selector khác `null` không khớp các nhãn case còn lại.

```java
static String category(Object value) {
    return switch (value) {
        case String s  -> "STRING";
        case Number n  -> "NUMBER";
        default        -> "OTHER";
    };
}
```

- `category("hi")` trả `"STRING"`.
- `category(10)` trả `"NUMBER"` vì `Integer` là `Number`.
- `category(true)` trả `"OTHER"` vì `Boolean` không khớp `String` hoặc `Number`.

**`default` không khai báo biến**. Không có biểu thức như `case default Object x`; nếu cần biến kiểu `Object` trong một nhánh, dùng một **type pattern** thích hợp như `case Object x` (nhưng xem quy tắc xung đột ở phần 5).

### 3.1. Không phải “thực thi ngay vì đặt trước”

Trong logic lựa chọn nhánh Java 21, `default` được áp dụng khi không nhãn case khác nào nhận selector, không đơn thuần là “nhãn đầu tiên có mặt trong file”. Tuy nhiên, **vị trí trong mã** bị ràng buộc bởi quy tắc cú pháp và dominance, nên cách viết tốt nhất vẫn là **đặt `default` cuối switch**.

Với cú pháp `case ... ->`, mỗi rule xử lý riêng; không có kiểu fall-through của nhóm lệnh dấu `:`. Với các nhóm lệnh `case ... :`, ngoài việc chọn nhãn, người viết còn phải quản lý `break`, `return` hoặc `throw` để tránh rơi tiếp vào nhóm lệnh khác.

### 3.2. `default` làm switch expression exhaustive

```java
static String safeKind(Object value) {
    return switch (value) {
        case String s -> "TEXT:" + s.length();
        default       -> "OTHER";
    };
}
```

`Object` là kiểu mở: giá trị có thể thuộc vô số kiểu khác `String`. Nhãn `default` bao phủ các giá trị còn lại, nên switch expression được coi là **exhaustive về kiểu**. Nhưng khi `value == null`, Java vẫn ném `NullPointerException` nếu không có nhãn `case null`. Đừng nhầm tính exhaustive với xử lý an toàn tất cả giá trị `null`.

## 4. Quy tắc vị trí: `default` thường ở cuối, nhưng cần hiểu đúng ngoại lệ

Theo **Java Language Specification 21, §14.11.1**, các quy tắc sau có hiệu lực:

1. **Lỗi biên dịch** nếu nhãn `default` đứng trước một nhãn `case` chứa **case pattern**.
2. **Lỗi biên dịch** nếu nhãn `default` đứng trước một nhãn `case null`.
3. **Lỗi biên dịch** nếu nhãn kết hợp `case null, default` đứng trước **bất kỳ nhãn switch nào khác**.
4. **Để tương thích ngược**, một `default` đứng trước các nhãn **chỉ chứa case constant, không có `null` hoặc pattern**, vẫn có thể hợp lệ.
5. **Cách viết nên dùng:** luôn đặt `default` hoặc `case null, default` ở cuối để người đọc không phải suy đoán thứ tự.

### 4.1. Sai: `default` trước type pattern

```java
// KHÔNG BIÊN DỊCH:
// static String bad(Object value) {
//     return switch (value) {
//         default       -> "OTHER";
//         case String s -> "STRING";  // Pattern đứng sau default.
//     };
// }
```

Dù bạn nghĩ rằng `case String s` là ngoại lệ chuyên biệt của `default`, thứ tự này không hợp lệ đối với **case pattern**.

**Sửa:**

```java
static String fixed(Object value) {
    return switch (value) {
        case String s -> "STRING:" + s;
        default       -> "OTHER";
    };
}
```

### 4.2. Sai: `default` trước `case null`

```java
// KHÔNG BIÊN DỊCH:
// return switch (value) {
//     default   -> "OTHER";
//     case null -> "NULL";
// };
```

Dạng hợp lệ nên dùng:

```java
return switch (value) {
    case null -> "NULL";
    default   -> "OTHER";
};
```

Mảnh mã trên chỉ minh họa biểu thức `return switch` trong một phương thức có biến `value` được khai báo và kiểu trả về `String`.

### 4.3. Ngoại lệ: `default` trước một case constant có thể hợp lệ

Đặc tả Java 21 cho phép, vì tương thích với các switch trước đây, dạng như sau:

```java
static String legacyOrder(int number) {
    return switch (number) {
        default -> "OTHER";
        case 42 -> "FORTY_TWO";
    };
}
```

Đoạn **biên dịch được**. `legacyOrder(42)` vẫn là `"FORTY_TWO"`, không phải `"OTHER"`, dù `default` được viết trước. `legacyOrder(7)` trả `"OTHER"`.

**Nhưng nên viết theo thứ tự dễ đọc:**

```java
static String recommendedOrder(int number) {
    return switch (number) {
        case 42 -> "FORTY_TWO";
        default -> "OTHER";
    };
}
```

Đây là ngoại lệ của nhãn **hằng**, không phải giấy phép đặt `default` trước `case String s` hoặc `case null`. Một dự án dùng pattern switch nên nhất quán đặt `default` cuối.

## 5. Xung đột: `default` và unconditional pattern

Một **unconditional pattern** đối với kiểu selector là pattern mà mọi giá trị thuộc kiểu selector (theo định nghĩa phù hợp của Java) đều khớp, nên nó có vai trò **bao quát kiểu** giống một nhánh dự phòng.

Ví dụ với selector `Object value`:

```java
static String withoutDefault(Object value) {
    return switch (value) {
        case null     -> "NULL";
        case String s -> "TEXT:" + s;
        case Object o -> "OBJECT:" + o.getClass().getSimpleName();
    };
}
```

Trong `case Object o`, `Object` là type pattern bao quát mọi giá trị **khác `null`** còn lại của selector kiểu `Object`. Trình biên dịch xem switch expression là exhaustive dù **không có `default`**. `case null` được dùng để xử lý riêng giá trị rỗng.

### 5.1. Sai: unconditional pattern rồi tới `default`

```java
// KHÔNG BIÊN DỊCH:
// return switch (value) {
//     case String s -> "STRING";
//     case Object o -> "OBJECT";
//     default       -> "OTHER"; // Default bị che khuất.
// };
```

Khi `case Object o` là pattern không guard và **unconditional cho kiểu selector**, nó đã có vai trò bao quát tất cả đối tượng cần xét. `default` theo sau bị **dominated**.

### 5.2. Đảo lại cũng không sửa được

```java
// KHÔNG BIÊN DỊCH:
// return switch (value) {
//     case String s -> "STRING";
//     default       -> "OTHER";
//     case Object o -> "OBJECT"; // Pattern đứng sau default.
// };
```

Lúc này lỗi là quy tắc **`default` không được đứng trước case pattern**. Do đó, trong switch cùng kiểu selector, không thể giữ đồng thời một **unconditional pattern** và `default` bằng cách đảo vị trí.

**Hai thiết kế thay thế:**

- **Dùng `default`:** `case String s -> ...; default -> ...;`. Không có biến pattern cho nhánh dự phòng.
- **Dùng unconditional type pattern:** `case String s -> ...; case Object o -> ...;`. Biến `o` cho phép xử lý đối tượng tại nhánh tổng quát. Thêm `case null` nếu muốn xử lý `null`.

Khi không cần truy cập chi tiết đối tượng trong nhánh cuối, `default` thường đơn giản hơn. Khi cần lấy kiểu hoặc gọi API chung của đối tượng đã khớp, type pattern bao quát có thể hữu ích.

### 5.3. Không nhầm “union của nhiều case” với một unconditional pattern

Ví dụ sealed interface có hai nhánh:

```java
sealed interface Event permits Started, Finished {}
record Started(String name) implements Event {}
record Finished(int code) implements Event {}
```

Hai pattern `case Started s` và `case Finished f` cùng nhau có thể **exhaustive** cho kiểu `Event`. Tuy nhiên chúng là **hai pattern riêng**, không phải một `case Event e` unconditional.

Để giữ compiler nhắc khi thêm một kiểu con mới, thường **không cần viết `default`**:

```java
static String render(Event event) {
    return switch (event) {
        case Started s  -> "START:" + s.name();
        case Finished f -> "END:" + f.code();
    };
}
```

Phân biệt hai khái niệm: “các case kết hợp lại bao phủ toàn bộ kiểu” (exhaustiveness) và “một pattern đơn lẻ bao phủ mọi giá trị kiểu selector” (unconditional pattern).

## 6. `case null`, `default` và `case null, default`

Đây là ba cấu trúc **khác nhau**:

| Nhãn | Có áp dụng cho `null`? | Có áp dụng cho các giá trị còn lại? | Có khai báo biến? |
| --- | --- | --- | --- |
| `case null` | Có | Không | Không |
| `default` | Không: `null` thường gây `NullPointerException` nếu thiếu nhãn null | Có, khi không case phù hợp khác | Không |
| `case null, default` | Có | Có, như nhánh dự phòng | Không |
| `case Object o` trên selector `Object` | Không khớp `null` | Có, cho đối tượng khác `null` | Có: `o` |

### 6.1. Cách tách null riêng

```java
static String separated(Object value) {
    return switch (value) {
        case null      -> "NO_VALUE";
        case String s  -> "TEXT:" + s;
        default        -> "OTHER";
    };
}
```

Với `null`, trả `NO_VALUE`. Với `"a"`, trả `TEXT:a`. Với `Integer.valueOf(7)`, trả `OTHER`.

### 6.2. Gộp null với default

```java
static String combined(Object value) {
    return switch (value) {
        case String s     -> "TEXT:" + s;
        case null, default -> "OTHER_OR_NULL";
    };
}
```

Đây là cú pháp Java 21 hợp lệ. `case null, default` giúp xử lý `null` và mọi giá trị khác không khớp `String` theo cùng một cách. Nó **phải nằm ở cuối switch**, vì quy tắc Java 21 cấm mọi switch label đứng sau nó.

**Sai:**

```java
// KHÔNG BIÊN DỊCH:
// return switch (value) {
//     case null, default -> "OTHER";
//     case String s      -> "STRING"; // Bất kỳ nhãn sau đều bị cấm.
// };
```

### 6.3. Không thể khai báo hai `default`

```java
// KHÔNG BIÊN DỊCH:
// switch (value) {
//     case String s -> System.out.println("TEXT");
//     default       -> System.out.println("OTHER_A");
//     default       -> System.out.println("OTHER_B");
// }
```

Một switch không được có hơn một nhãn `default`. Một `case null, default` đã chứa `default`, nên không thể thêm `default` thứ hai.

### 6.4. `null` không phải một type pattern

`case null` không giới thiệu biến như `case String s`. Nó là nhãn dành riêng cho giá trị null.

```java
static String nullAware(Object value) {
    return switch (value) {
        case null -> "NULL";
        case String text when text.isBlank() -> "BLANK";
        case String text -> "TEXT:" + text;
        default -> "OTHER";
    };
}
```

Vì `null` được xử lý trước, guard `text.isBlank()` chỉ được đánh giá khi selector đã khớp `String`; không có việc gọi `isBlank()` trên tham chiếu null chưa khớp.

## 7. Guard `when`: vì sao không phải case nào đứng trước cũng dominate case sau?

Một **guarded pattern** chỉ khớp khi:

1. Giá trị selector khớp pattern.
2. Biểu thức `when` đánh giá thành `true`.

Ví dụ:

```java
static String textKind(Object value) {
    return switch (value) {
        case String s when s.isBlank() -> "BLANK";
        case String s                  -> "TEXT:" + s.strip();
        default                        -> "OTHER";
    };
}
```

Nhánh đầu chỉ nhận chuỗi toàn khoảng trắng (bao gồm chuỗi rỗng); nó **không thống trị** nhánh `case String s` phía sau, vì nhiều chuỗi không thỏa `isBlank()`. `default` xử lý các kiểu không phải `String`.

Ngược lại:

```java
// KHÔNG BIÊN DỊCH:
// return switch (value) {
//     case String s                  -> "ANY_STRING";
//     case String s when s.isBlank() -> "BLANK"; // Dominated.
//     default                        -> "OTHER";
// };
```

Nhánh `case String s` không guard đã nhận tất cả đối tượng `String` khác `null`; guard phía sau không có cơ hội chạy.

### 7.1. Guard không tự làm `default` bị dominated

```java
static String longStringOrOther(Object value) {
    return switch (value) {
        case String s when s.length() > 3 -> "LONG";
        default                           -> "NOT_LONG";
    };
}
```

Dù một số `String` đã được nhận ở nhánh đầu, các chuỗi có độ dài nhỏ hơn hoặc bằng 3 và những kiểu đối tượng khác vẫn phải có đường xử lý. Vì vậy `default` là hợp lệ và cần thiết để switch expression exhaustive.

### 7.2. Guard và điều kiện `true` nên viết thế nào?

Đừng dùng `when` chỉ để so hằng enum nếu có thể viết trực tiếp một case constant:

```java
// Có thể diễn đạt đơn giản hơn bằng hằng enum:
case Status.FAILED -> "FAILED";
```

Khi một điều kiện phụ thực sự cần truy cập dữ liệu đã khớp, `case String s when s.length() > 3` có giá trị. Đặt case guard chuyên biệt trước case tổng quát để tránh dominance.

### 7.3. Không thể dùng `default` với `when`

```java
// KHÔNG HỢP LỆ:
// default when flag -> "OTHER";
```

`when` đi với **case pattern**, không phải là công cụ sửa nghĩa của nhãn `default`. Nếu muốn điều kiện bổ sung khi vào nhánh default, viết `if` trong thân rule/block, hoặc thiết kế lại các case chuyên biệt.

## 8. Case hằng, enum và `default`

Các **case constants** gồm hằng nguyên, chuỗi, và hằng enum (khi kiểu selector phù hợp). Dominance cũng xuất hiện khi một pattern rộng hơn đứng trước hằng.

Giả sử:

```java
enum State { CREATED, DONE, FAILED }
```

Một switch trên `Object` có thể viết:

```java
static String stateKind(Object value) {
    return switch (value) {
        case State.FAILED -> "FAILED";
        case State state  -> "STATE:" + state;
        default           -> "OTHER";
    };
}
```

`State.FAILED` là **case constant**: nhận chính hằng đó. `case State state` là **type pattern**: nhận các hằng `State` khác còn lại, ràng buộc biến `state`. Đặt hằng cụ thể trước pattern tổng quát là hợp lệ.

**Nếu đảo thứ tự sẽ lỗi:**

```java
// KHÔNG BIÊN DỊCH:
// return switch (value) {
//     case State state  -> "STATE:" + state;
//     case State.FAILED -> "FAILED"; // Bị pattern State thống trị.
//     default           -> "OTHER";
// };
```

Ở đây thêm `default` không giải quyết được nhánh `State.FAILED` bị dominated.

### Enum exhaustive switch không nhất thiết cần default

```java
static String directState(State state) {
    return switch (state) {
        case CREATED -> "CREATED";
        case DONE    -> "DONE";
        case FAILED  -> "FAILED";
    };
}
```

Switch expression đã exhaustive vì liệt kê đủ ba hằng của `State`. Không cần `default`.

Nếu sau này bổ sung hằng enum mới và **biên dịch lại** mã, việc không có `default` có lợi: compiler có thể yêu cầu cập nhật switch theo domain mới. Nếu dùng `default` để nhận mọi hằng lạ, bạn có thể bỏ qua một trạng thái nghiệp vụ mới.

Tuy vậy, thiếu `case null` đồng nghĩa với việc truyền `null` cho switch enum vẫn có thể ném `NullPointerException`; exhaustive về enum constants không tự xử lý null.

## 9. `default` có phải luôn là giải pháp tốt cho exhaustiveness?

Không. Trong Java 21, **switch expression** và **enhanced switch statement** phải exhaustive, nhưng một số kiểu đầu vào có tập lựa chọn đóng mà compiler có thể kiểm tra đầy đủ.

So sánh:

**Cách 1 — nhận mọi kiểu còn lại bằng default:**

```java
static String openInput(Object value) {
    return switch (value) {
        case String s -> "TEXT";
        case Integer n -> "NUMBER";
        default -> "OTHER";
    };
}
```

Với `Object`, `default` có ý nghĩa vì đối tượng có thể thuộc nhiều kiểu khác.

**Cách 2 — sealed hierarchy không cần default:**

```java
sealed interface Result permits Ok, Error {}
record Ok(String data) implements Result {}
record Error(int code) implements Result {}

static String render(Result result) {
    return switch (result) {
        case Ok ok       -> "OK:" + ok.data();
        case Error error -> "ERR:" + error.code();
    };
}
```

Vì `Result` chỉ cho phép hai loại record trên, compiler có thể chứng minh exhaustiveness. Không có `default`, khi bạn **cập nhật và biên dịch lại** phân cấp sealed để bổ sung loại mới, compiler có cơ hội nhắc cập nhật các switch liên quan.

### 9.1. Exhaustive khác dominance

Một switch trên sealed interface có đủ `case Ok` và `case Error` là exhaustive; nó không đồng nghĩa một trong hai pattern thống trị pattern còn lại. Nếu thay vào đó dùng `case Result result` ngay đầu, nó là pattern bao quát và các case `Ok`/`Error` sau sẽ bị dominated.

**Sai:**

```java
// KHÔNG BIÊN DỊCH:
// return switch (result) {
//     case Result any -> "RESULT";
//     case Ok ok      -> "OK"; // Đã nằm trong Result.
//     case Error err  -> "ERROR";
// };
```

**Sửa:** đặt case chuyên biệt `Ok`, `Error` trước. Nếu chúng đã exhaustive, có thể bỏ nhánh tổng quát.

### 9.2. Runtime vẫn có thể có ngoại lệ

Không nên coi `default` hay exhaustiveness là chứng minh rằng chương trình không bao giờ lỗi. Thân một case vẫn có thể ném ngoại lệ; thiếu `case null` có thể gây NPE; thay đổi thư viện chưa được biên dịch lại có thể tạo bất nhất giữa giả định lúc compile và runtime.

Mục đích của dominance và exhaustiveness là **kiểm tra cấu trúc điều khiển theo ngôn ngữ**, không thay thế kiểm thử nghiệp vụ.

## 10. Mã Java 21 độc lập: quan sát default và các pattern

Tạo file **`DefaultDominanceDemo.java`**:

```java
public class DefaultDominanceDemo {

    enum State { CREATED, DONE, FAILED }

    sealed interface Event permits Started, Finished {}

    record Started(String name) implements Event {}

    record Finished(int code) implements Event {}

    // Pattern chuyên biệt trước pattern rộng hơn;
    // default nhận những giá trị chưa khớp.
    static String classify(Object value) {
        return switch (value) {
            case null                  -> "NULL";
            case Integer n when n < 0  -> "NEG:" + n;
            case Integer n             -> "INT:" + n;
            case CharSequence text     -> "TEXT:" + text;
            default                    -> "OTHER";
        };
    }

    // Một unconditional pattern thay cho default.
    static String catchAll(Object value) {
        return switch (value) {
            case null     -> "NO_VALUE";
            case String s -> "S:" + s;
            case Object o -> "O:" + o.getClass().getSimpleName();
        };
    }

    // Gộp nhãn null với default: phải đặt ở cuối.
    static String longOrOther(Object value) {
        return switch (value) {
            case String s when s.length() > 3 -> "LONG:" + s.length();
            case null, default               -> "NOT_LONG_STRING";
        };
    }

    // Hằng cụ thể trước type pattern enum tổng quát.
    static String state(Object value) {
        return switch (value) {
            case State.FAILED -> "FAILED";
            case State s      -> "STATE:" + s.name();
            default           -> "OTHER";
        };
    }

    // Sealed hierarchy exhaustive, không cần default.
    static String event(Event event) {
        return switch (event) {
            case Started s  -> "START:" + s.name();
            case Finished f -> "END:" + f.code();
        };
    }

    // Ngoại lệ tương thích ngược: default trước case constant
    // được phép, nhưng không nên dùng kiểu viết này thường xuyên.
    static String legacyOrder(int number) {
        return switch (number) {
            default -> "OTHER";
            case 42 -> "FORTY_TWO";
        };
    }

    public static void main(String[] args) {
        System.out.println(classify(-2));
        System.out.println(classify(0));
        System.out.println(classify("Java"));
        System.out.println(classify(new StringBuilder("Hi")));
        System.out.println(classify(1.5));
        System.out.println(classify(null));

        System.out.println(catchAll("A"));
        System.out.println(catchAll(7));
        System.out.println(catchAll(null));

        System.out.println(longOrOther("Java"));
        System.out.println(longOrOther("Go"));
        System.out.println(longOrOther(null));

        System.out.println(state(State.FAILED));
        System.out.println(state(State.DONE));
        System.out.println(state(100));

        System.out.println(event(new Started("Job")));
        System.out.println(event(new Finished(0)));

        System.out.println(legacyOrder(42));
        System.out.println(legacyOrder(7));
    }
}
```

Biên dịch và chạy bằng **JDK 21 trở lên**, không cần preview:

```bash
javac --release 21 DefaultDominanceDemo.java
java DefaultDominanceDemo
```

**Kết quả mong đợi, theo đúng thứ tự:**

```text
NEG:-2
INT:0
TEXT:Java
TEXT:Hi
OTHER
NULL
S:A
O:Integer
NO_VALUE
LONG:4
NOT_LONG_STRING
NOT_LONG_STRING
FAILED
STATE:DONE
OTHER
START:Job
END:0
FORTY_TWO
OTHER
```

### Giải thích các kết quả chính

1. `classify(-2)`: `Integer` khớp, guard `n < 0` đúng, trả `NEG:-2`. `classify(0)` đi tới `case Integer n` tổng quát và trả `INT:0`.
2. `classify("Java")` và `classify(new StringBuilder("Hi"))`: `String` và `StringBuilder` đều triển khai `CharSequence`, nên trả `TEXT:Java` và `TEXT:Hi`.
3. `classify(1.5)` nhận một `Double`; nó không phải `Integer` hoặc `CharSequence`, nên đi vào `default`.
4. `catchAll("A")` đi vào nhánh `String` hẹp hơn; `catchAll(7)` đi vào `case Object o` và lấy tên lớp `Integer`. `catchAll(null)` được `case null` xử lý trước.
5. `longOrOther("Java")` khớp guard độ dài lớn hơn 3; `"Go"` không thỏa guard nên đi tới `case null, default`. Với `null`, nhãn kết hợp cũng được chọn.
6. `state(State.FAILED)` được nhánh enum constant xử lý trước pattern `State s`; `state(State.DONE)` đi vào type pattern; `state(100)` chọn `default`.
7. `event` dùng đủ các kiểu con của `Event` (sealed), nên không cần `default`.
8. `legacyOrder(42)` vẫn chọn `case 42` dù nhãn `default` được viết trước; `legacyOrder(7)` trả `OTHER`. Đây là **ngoại lệ tương thích ngược**, không phải thứ tự nên áp dụng cho pattern switch.

Các ví dụ cố tình **không đưa** các đoạn sai (dominated, default trước pattern/null, `case null, default` chưa ở cuối) vào file chạy. Muốn quan sát lỗi `javac`, hãy thử từng đoạn lỗi riêng trong một file thí nghiệm.

## 11. Bảng lỗi về default và dominance thường gặp

| Cấu trúc | Biên dịch trên Java 21? | Lý do / cách sửa |
| --- | --- | --- |
| `case Integer i` rồi `case Number n` trên selector `Object` | Có | Case hẹp trước case rộng |
| `case Number n` rồi `case Integer i` | Không | `Integer` bị `Number` thống trị |
| `case Integer i` rồi `case 42` | Không | Hằng `42` đã bị pattern `Integer` nhận |
| `case 42` rồi `case Integer i` | Có | Hằng cụ thể trước pattern |
| `case String s when s.isBlank()` rồi `case String s` | Có | Guard đầu chỉ khớp một phần chuỗi |
| `case String s` rồi `case String s when s.isBlank()` | Không | Nhánh thứ hai bị dominated |
| `case String s` rồi `default` | Có | Default bao phủ các kiểu khác |
| `default` rồi `case String s` | Không | Default không được đứng trước case pattern |
| `default` rồi `case null` | Không | Default không được đứng trước null label |
| `case null` rồi `default` | Có | Null xử lý riêng, default xử lý giá trị khác |
| `case null, default` rồi bất kỳ nhãn khác | Không | Nhãn kết hợp phải ở cuối |
| `case String s` rồi `case null, default` | Có | Nhãn cuối bao phủ null và trường hợp còn lại |
| `case Object o` rồi `default` trên selector `Object` | Không | Unconditional pattern thống trị default |
| `default` rồi `case Object o` trên selector `Object` | Không | Default đứng trước case pattern |
| `default` rồi `case 42` trên selector `int` | Có | Ngoại lệ tương thích ngược, nên tránh |
| Hai nhãn `default` trong một switch | Không | Nhãn default chỉ được xuất hiện một lần |

Bảng giả sử các đoạn mã được đặt trong một switch có kiểu selector tương thích và có đủ các rule cần thiết để đáp ứng exhaustiveness. Mỗi hàng dùng để xét **quan hệ giữa các nhãn**, không phải khẳng định rằng hai case đứng riêng lẻ luôn tạo thành một chương trình Java đầy đủ.

## 12. Cách khắc phục khi compiler báo lỗi

### 12.1. `dominated case label`

Nếu thấy thông báo dạng dominated case:

- Xác định nhánh bị báo lỗi đang nằm sau case nào.
- Kiểm tra nhánh phía trước có type pattern rộng hơn không, chẳng hạn `Number` bao phủ `Integer`, `CharSequence` bao phủ `String`, hoặc `Object` bao phủ mọi đối tượng.
- Kiểm tra một **case constant** có bị type pattern trước nhận hết không, chẳng hạn hằng `42` sau `Integer`, hoặc hằng enum sau pattern của enum.
- Sửa bằng cách đặt case hẹp/hằng cụ thể trước, hoặc bỏ nhánh dư thừa.

Không cần thêm `default` để sửa lỗi dominated case vì đây là lỗi của **thứ tự và quan hệ bao phủ**.

### 12.2. `default` đặt không đúng vị trí

Nếu `default` đứng trước `case String s`, `case Point(...)` hoặc `case null`, chuyển `default` xuống **cuối switch**. Với `case null, default`, bảo đảm không có nhãn nào đứng sau. Không nên dựa vào ngoại lệ legacy `default` trước case constant trừ khi bạn thật sự cần giữ mã tương thích cũ.

### 12.3. `switch expression does not cover all possible input values`

Đây là lỗi **không exhaustive**, không phải dominated case. Với selector `Object`, thường cần `default` hoặc unconditional pattern. Với enum, kiểm tra đủ hằng. Với sealed interface, kiểm tra đủ các kiểu con được phép.

Nếu bạn vừa xóa `default` để tránh xung đột với `case Object o`, hãy chắc chắn pattern bao quát đó thực sự unconditional cho kiểu selector, để switch vẫn exhaustive.

### 12.4. `NullPointerException` dù có `default`

Đây là lỗi runtime từ việc thiếu `case null`, không phải lỗi dominance. Thêm `case null`, dùng `case null, default`, hoặc từ chối null trước khi vào switch bằng `Objects.requireNonNull` nếu nghiệp vụ không chấp nhận dữ liệu rỗng.

## 13. Bài tập và đáp án

### Bài 1 — chọn quy tắc đúng

Giả sử `Object value` đã được khai báo:

**A:**

```java
return switch (value) {
    case Number n  -> "NUMBER";
    case Integer i -> "INTEGER";
    default        -> "OTHER";
};
```

**B:**

```java
return switch (value) {
    case Integer i -> "INTEGER";
    case Number n  -> "NUMBER";
    default        -> "OTHER";
};
```

**Đáp án:** A lỗi dominated case vì `Integer` là `Number`. B hợp lệ: trường hợp cụ thể đứng trước trường hợp rộng. Hai đoạn `return switch` là mảnh thân phương thức có kiểu trả về `String`.

### Bài 2 — default đứng đầu có nhất thiết sai?

Xét:

```java
static String test(int n) {
    return switch (n) {
        default -> "OTHER";
        case 1  -> "ONE";
    };
}
```

**Đáp án:** Đoạn này **biên dịch được trong Java 21** do ngoại lệ tương thích ngược cho `default` trước case constant. `test(1)` trả `ONE`, `test(2)` trả `OTHER`. Tuy nhiên, cách viết rõ ràng hơn vẫn là đặt `case 1` trước và `default` cuối.

### Bài 3 — unconditional pattern có cần default?

```java
static String test(Object value) {
    return switch (value) {
        case null     -> "NULL";
        case String s -> "STRING";
        case Object o -> "OTHER_OBJECT";
    };
}
```

**Đáp án:** Không cần `default`. `case Object o` nhận mọi đối tượng khác `null` mà nhánh `String` chưa nhận; `case null` xử lý null. Nếu thêm `default` sau `Object o`, sẽ gây lỗi vì default bị unconditional pattern thống trị.

### Bài 4 — sửa `case null, default` sai vị trí

```java
// KHÔNG BIÊN DỊCH:
// return switch (value) {
//     case null, default -> "OTHER";
//     case String s      -> s;
// };
```

**Sửa thành:**

```java
return switch (value) {
    case String s       -> s;
    case null, default  -> "OTHER";
};
```

Nhãn kết hợp là nhánh cuối, xử lý cả null và mọi kiểu không phải `String`.

### Bài 5 — guard có chặn default không?

```java
static String classify(Object value) {
    return switch (value) {
        case String s when s.length() >= 3 -> "LONG";
        default                           -> "OTHER";
    };
}
```

Dự đoán:

- `classify("Java")` → `"LONG"`.
- `classify("Go")` → `"OTHER"`.
- `classify(100)` → `"OTHER"`.
- `classify(null)` → ném `NullPointerException` vì không có `case null`.

Guard chỉ bao phủ những chuỗi thỏa điều kiện; vì vậy `default` không bị dominated và vẫn cần thiết cho những giá trị còn lại.

### Bài 6 — enum constant hay type pattern trước?

Giả sử có `enum State { CREATED, DONE, FAILED }` và `Object value`. Bạn muốn `State.FAILED` trả `"ALERT"`, các hằng `State` còn lại trả `"STATE"`, đối tượng khác trả `"OTHER"`.

**Đáp án:**

```java
static String classify(Object value) {
    return switch (value) {
        case State.FAILED -> "ALERT";
        case State state  -> "STATE";
        default           -> "OTHER";
    };
}
```

Nếu đảo hai case đầu, `State.FAILED` sẽ bị dominated. Nếu muốn xử lý `null` không gây NPE, thêm `case null`.

## 14. Checklist khi review `default` và dominance

Khi đọc một pattern switch Java 21, hãy kiểm tra theo thứ tự:

1. **Kiểu tĩnh của selector:** `Object`, interface, enum, sealed class hoặc kiểu khác? Dominance và exhaustiveness dựa vào kiểu mà compiler thấy.
2. **Mỗi case là hằng hay pattern?** `case State.FAILED` là hằng enum; `case State s` là type pattern; `default` không phải pattern.
3. **Quan hệ bao phủ:** case tổng quát nào đứng trước case chuyên biệt không? Hằng có bị pattern trước bao phủ không?
4. **Guard:** `case T t when condition` có thể khớp ít giá trị hơn `case T t`; đặt guarded/special cases trước nhánh tổng quát.
5. **Có unconditional pattern không?** Nếu có một pattern bao quát kiểu selector như `case Object o` với selector `Object`, không thêm `default` trùng vai trò.
6. **Vị trí `default`:** đặt cuối, đặc biệt không đặt trước case pattern hoặc `case null`. Nếu thấy `default` trước case hằng, nhận biết đó là ngoại lệ legacy, không phải phong cách nên áp dụng rộng rãi.
7. **Nếu dùng `case null, default`:** nó phải là nhãn cuối, không có nhãn nào khác sau đó.
8. **Exhaustiveness:** một switch expression/enhanced statement có bao phủ mọi khả năng theo kiểu selector không? Có `default`, unconditional pattern, đủ enum constants hoặc đủ sealed subtypes không?
9. **Null:** `default` riêng không xử lý `null`; nếu cần kiểm soát, dùng `case null` hay `case null, default`.
10. **Đường chạy và biến pattern:** case pattern chỉ khai báo biến cho nhánh khớp; không dùng biến đó ở `default` hoặc nhánh không liên quan.

## 15. Kết luận

Trong Java 21, **dominance** ngăn những nhánh `case` phía sau không còn khả năng được chọn vì nhánh trước đã bao phủ chúng. `default` là nhánh dự phòng, nhưng **không loại bỏ quy tắc dominance**.

- Đặt **case chuyên biệt, hằng cụ thể và case có guard** trước case tổng quát thích hợp.
- Nếu có một **unconditional pattern** cho kiểu selector, **không dùng thêm `default`**: đặt trước hay sau đều tạo xung đột theo các quy tắc Java 21.
- **`default` nên đặt cuối**. Đặc tả có ngoại lệ tương thích ngược cho `default` trước **case constant**, nhưng **cấm** nó đứng trước case pattern và `case null`.
- `case null, default` là nhãn kết hợp bao phủ null và nhánh dự phòng, và **phải là nhãn cuối**.
- **Exhaustiveness** trả lời “đã đủ trường hợp chưa?”, còn **dominance** trả lời “có nhánh nào bị che khuất không?”. Hai điều kiện cần xem riêng.
- `default` không tự xử lý `null`, không khai báo biến pattern, và không bảo đảm logic bên trong nhánh sẽ không ném ngoại lệ.

**Câu ghi nhớ:** Khi cần một nhánh mặc định trong pattern switch, hãy xử lý các trường hợp **hẹp trước, rộng sau**, rồi đặt `default` cuối **nếu chưa có một unconditional pattern đóng vai trò bao quát**.

## Tài liệu tham khảo chính thức

- [Java SE 21 Language Specification §14.11.1 — Switch Blocks, Dominance và Default](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.11.1)
- [Java SE 21 Language Specification §14.11.1.1 — Exhaustive Switch Blocks](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.11.1.1)
- [Java SE 21 Language Specification §14.11.1.2 — Determining Which Switch Label Applies](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.11.1.2)
- [Java SE 21 Language Specification §14.30.3 — Properties of Patterns](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.30.3)
- [OpenJDK JEP 441 — Pattern Matching for switch](https://openjdk.org/jeps/441)
- [Oracle Java 21 — Pattern Matching for switch](https://docs.oracle.com/en/java/javase/21/language/pattern-matching-switch.html)
