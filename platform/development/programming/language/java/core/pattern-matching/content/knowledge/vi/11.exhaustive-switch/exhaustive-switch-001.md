# Exhaustive switch là gì trong Java Pattern Matching?

## 1. Khái niệm: một `switch` bao phủ toàn bộ trường hợp

**Exhaustive switch** là một biểu thức hoặc câu lệnh `switch` mà các nhãn `case` của nó, theo quy tắc kiểm tra **tĩnh của trình biên dịch**, đã bao phủ tất cả những khả năng cần được xử lý của **kiểu selector** (giá trị đưa vào `switch`). Nếu một dạng `switch` bắt buộc phải exhaustive nhưng còn thiếu khả năng, Java báo **lỗi biên dịch**.

Ví dụ với enum:

```java
enum Signal { RED, YELLOW, GREEN }

static String traffic(Signal signal) {
    return switch (signal) {
        case RED    -> "STOP";
        case YELLOW -> "WAIT";
        case GREEN  -> "GO";
    };
}
```

Biểu thức `switch` này **exhaustive** vì `Signal` chỉ có ba enum constants được khai báo: `RED`, `YELLOW`, `GREEN`; cả ba đều có case tương ứng. Không cần thêm `default`.

Ngược lại, đoạn sau **không biên dịch**:

```java
// KHÔNG HỢP LỆ: switch expression thiếu GREEN.
// static String traffic(Signal signal) {
//     return switch (signal) {
//         case RED    -> "STOP";
//         case YELLOW -> "WAIT";
//     };
// }
```

Trình biên dịch biết `signal` có thể là `GREEN`, nhưng không có nhánh nào cung cấp giá trị cho trường hợp đó.

**Mấu chốt:** exhaustive là thuộc tính về **độ bao phủ theo kiểu khi biên dịch**, không phải nhận định rằng “đã chạy hết mọi case khi kiểm thử”. Một bộ kiểm thử có thể chạy qua nhiều trường hợp nhưng vẫn bỏ sót giá trị hợp lệ; compiler có thể chỉ ra một số kiểu thiếu bao phủ mà không cần chạy chương trình.

Bài này dùng **Java 21 trở lên**, vì *Pattern Matching for switch* đã được chuẩn hóa ở Java 21 (JEP 441). Những ví dụ chỉ dùng enum switch expression có thể hoạt động trên các phiên bản cũ hơn, nhưng ví dụ dùng case patterns, sealed types và `case null` được viết cho Java 21.

## 2. Vì sao Java cần exhaustive switch?

`switch` thường dùng để chuyển một đầu vào thành kết quả hoặc chọn hành vi thích hợp. Nếu một nhánh có thể bị bỏ sót, chương trình dễ gặp tình huống không được xử lý.

Với **switch expression**, Java cần một giá trị để gán hoặc `return`. Nếu một trường hợp không tạo được giá trị, biểu thức không còn đáng tin cậy:

```java
String action = switch (signal) {
    case RED    -> "stop";
    case YELLOW -> "slow";
    case GREEN  -> "go";
};
```

Trình biên dịch kiểm tra rằng các case bao phủ kiểu `Signal`, nhờ đó mỗi giá trị enum đã biết đều dẫn đến một rule.

Với **pattern matching**, selector có thể là một kiểu tổng quát như `Object` hoặc một `sealed interface`:

```java
static String describe(Object value) {
    return switch (value) {
        case String s  -> "TEXT:" + s;
        case Integer n -> "INT:" + n;
        default        -> "OTHER";
    };
}
```

`Object` có thể chứa nhiều kiểu khác ngoài `String` và `Integer`; vì vậy `default` giúp bao phủ những giá trị khác.

Lợi ích của exhaustiveness:

1. **Phát hiện thiếu nhánh khi biên dịch:** lỗi xuất hiện sớm, trước khi hệ thống chạy thật.
2. **Giảm lỗi do thêm giá trị enum hoặc kiểu con mới:** khi sửa mã nguồn và biên dịch lại, compiler có thể yêu cầu cập nhật các switch đã liệt kê hết trường hợp.
3. **Làm rõ hợp đồng xử lý:** người đọc biết switch đang cố xử lý toàn bộ kiểu đầu vào, không chỉ một vài trường hợp được quan tâm.
4. **Hỗ trợ mô hình hóa domain bằng sealed types:** các trạng thái hoặc loại kết quả được giới hạn tạo điều kiện để switch có thể exhaustive mà không cần default tùy tiện.

Tính exhaustive **không chứng minh** các nhánh đúng nghiệp vụ, không bảo đảm không ném ngoại lệ và cũng không thay thế kiểm thử.

## 3. Switch expression và switch statement có cùng yêu cầu không?

Không hoàn toàn. Đây là phân biệt quan trọng trong **Java 21**.

| Dạng switch | Có bắt buộc exhaustive? | Giải thích |
| --- | --- | --- |
| **Switch expression** `return switch (...) { ... };` | **Có, luôn luôn** | Cần có kết quả hoặc một đường hoàn tất phù hợp cho mọi giá trị cần xét |
| **Enhanced switch statement** | **Có** | Java 21 yêu cầu dạng statement dùng pattern, `case null`, hoặc selector thuộc kiểu tham chiếu mới được hỗ trợ phải exhaustive |
| **Switch statement cổ điển** | **Không bắt buộc** | Giữ tương thích với mã Java đã tồn tại; thiếu case có thể dẫn đến không thực hiện nhánh nào |

### 3.1. Switch expression: bắt buộc exhaustive

```java
static int grade(Signal signal) {
    return switch (signal) {
        case RED    -> 0;
        case YELLOW -> 1;
        case GREEN  -> 2;
    };
}
```

Đây là một **biểu thức** có kiểu `int`. Compiler yêu cầu bộ case exhaustive.

Với block có nhiều câu lệnh, sử dụng `yield` để cung cấp giá trị:

```java
static int value(Object input) {
    return switch (input) {
        case String s -> {
            int length = s.strip().length();
            yield length;
        }
        case Integer n -> n;
        default -> 0;
    };
}
```

`yield` trả giá trị cho **switch expression**, không phải `return` khỏi phương thức. Việc các nhánh dùng biểu thức trực tiếp hay `yield` không làm thay đổi yêu cầu exhaustive.

### 3.2. Enhanced switch statement: cũng bắt buộc exhaustive

Trên Java 21, `switch statement` được gọi là **enhanced** nếu thỏa ít nhất một điều kiện:

- Kiểu selector không thuộc tập kiểu cho phép bởi switch cổ điển: `char`, `byte`, `short`, `int`, các wrapper tương ứng, `String` hoặc enum; ví dụ `Object`, `Number`, interface.
- Hoặc trong switch có **case pattern** hay nhãn **`case null`**.

Ví dụ sau là **enhanced switch statement** và hợp lệ:

```java
static void printCategory(Object value) {
    switch (value) {
        case String s -> System.out.println("STRING:" + s);
        default       -> System.out.println("OTHER");
    }
}
```

`default` bao phủ các kiểu khác `String`. Nếu bỏ `default` ở ví dụ `Object` này, mã sẽ bị từ chối do **non-exhaustive switch statement**.

Một enhanced switch statement dùng toàn bộ các kiểu của sealed hierarchy cũng có thể exhaustive mà không cần `default` (xem phần 6).

### 3.3. Switch statement cổ điển: ngoại lệ vì tương thích ngược

```java
static void printTraffic(Signal signal) {
    switch (signal) {
        case RED -> System.out.println("STOP");
    }
}
```

Đoạn này **vẫn biên dịch trên Java 21** vì đây là switch statement cổ điển trên enum, không có case pattern và không có `case null`. Nếu `signal` là `YELLOW` hoặc `GREEN`, không có nhánh nào khớp và câu lệnh kết thúc mà không in gì.

**Đừng kết luận rằng mọi `switch` đều bắt buộc exhaustive.** Quy tắc đúng là: **mọi switch expression và mọi enhanced switch statement** đều yêu cầu exhaustive; còn classic switch statement được giữ linh hoạt để tương thích với mã cũ.

## 4. Cách 1: exhaustive bằng `default`

Cách dễ thấy nhất là thêm nhánh `default`:

```java
static String classify(Object value) {
    return switch (value) {
        case String s  -> "STRING";
        case Integer n -> "INTEGER";
        default        -> "OTHER";
    };
}
```

Ở đây:

- `String` được xử lý bởi type pattern `String s`.
- `Integer` được xử lý bởi `Integer n`.
- Các đối tượng khác `null` còn lại được xử lý bởi `default`.

Nhờ `default`, switch **được xem là exhaustive theo kiểm tra tĩnh**. Nhưng có hai chú ý:

1. `default` không tự động xử lý giá trị `null` theo cách nhiều người tưởng (phần 8).
2. `default` có thể làm compiler **không còn nhắc** khi sau này bạn bổ sung enum constant hoặc một kiểu con mới, vì nhánh mặc định đã bao phủ chúng. Đôi khi đó là chủ đích; đôi khi nó che giấu lỗi thiếu xử lý nghiệp vụ.

### Khi nào `default` hợp lý?

`default` phù hợp khi đầu vào thực sự mở, ví dụ `Object`, hoặc khi có hành vi chung hợp lý cho tất cả giá trị chưa được chuyên biệt hóa. Với domain đóng bằng enum/sealed types, hãy cân nhắc để compiler kiểm tra đủ các case **không có default** nếu muốn thay đổi kiểu buộc bạn xem xét lại logic.

### `case null, default` có nghĩa gì?

Java 21 còn hỗ trợ nhãn gộp:

```java
static String safeClassify(Object value) {
    return switch (value) {
        case String s     -> "STRING:" + s;
        case Integer n    -> "INTEGER:" + n;
        case null, default -> "OTHER_OR_NULL";
    };
}
```

Nhãn `case null, default` xử lý cả **`null`** lẫn các giá trị còn lại. Theo cú pháp Java 21, đây là một dạng nhãn đặc biệt; không phải một type pattern, và nên đặt ở cuối switch.

## 5. Cách 2: liệt kê đủ enum constants

Enum xác định một **tập giá trị hữu hạn**. Vì vậy compiler có thể kiểm tra exhaustiveness bằng cách đếm đủ các hằng.

```java
enum PaymentStatus { NEW, PAID, REJECTED }

static String paymentText(PaymentStatus status) {
    return switch (status) {
        case NEW      -> "Chờ xử lý";
        case PAID     -> "Đã thanh toán";
        case REJECTED -> "Bị từ chối";
    };
}
```

Không cần `default` vì cả ba hằng của `PaymentStatus` đã xuất hiện trong các case.

Có thể gộp những hằng có cùng cách xử lý:

```java
static boolean finalState(PaymentStatus status) {
    return switch (status) {
        case NEW            -> false;
        case PAID, REJECTED -> true;
    };
}
```

`case PAID, REJECTED` bao phủ **hai enum constants**; cùng với `NEW`, toàn bộ enum được xử lý.

### Thiếu một hằng sẽ ra sao?

```java
// KHÔNG BIÊN DỊCH: thiếu REJECTED.
// static String paymentText(PaymentStatus status) {
//     return switch (status) {
//         case NEW  -> "new";
//         case PAID -> "paid";
//     };
// }
```

Đây là lỗi tại thời điểm biên dịch, **không phải** trường hợp switch expression trả `null` hay một giá trị mặc định ngầm định.

### Vì sao bỏ `default` đôi khi tốt hơn?

Giả sử enum ban đầu gồm `NEW`, `PAID`, `REJECTED`. Nếu sau này thêm `REFUNDED` rồi **biên dịch lại mã nguồn**, switch expression liệt kê ba hằng cũ sẽ báo không exhaustive. Nhờ vậy người bảo trì phải cân nhắc xử lý hoàn tiền.

Nếu trước đó đã viết `default -> "OTHER"`, đoạn mã thường tiếp tục biên dịch mà không buộc cập nhật nhánh nghiệp vụ mới. Cả hai cách đều hợp lệ; lựa chọn phụ thuộc vào mức độ muốn compiler bảo vệ hợp đồng enum.

## 6. Cách 3: sealed type + case patterns

**Sealed classes/interfaces** giới hạn các kiểu được phép kế thừa hoặc triển khai trực tiếp. Đây là nền tảng quan trọng để tạo một pattern switch exhaustive **không cần `default`**.

Giả sử có các kết quả nghiệp vụ:

```java
sealed interface ApiResult permits Success, Failure {}

record Success(String data) implements ApiResult {}

record Failure(int code) implements ApiResult {}
```

Java biết một giá trị `ApiResult` hợp lệ thuộc một trong những kiểu được cho phép. Ta có thể viết:

```java
static String render(ApiResult result) {
    return switch (result) {
        case Success s -> "OK:" + s.data();
        case Failure f -> "ERROR:" + f.code();
    };
}
```

Mã hợp lệ và exhaustive vì `Success` và `Failure` là toàn bộ tập kiểu con được phép. `Success` và `Failure` đều là records, mặc nhiên `final`.

**Điểm cần hiểu:**

- `case Success s` là **type pattern**: khớp mọi đối tượng `Success` khác `null` và gắn biến `s`.
- `case Failure f` bao phủ mọi đối tượng `Failure` khác `null`.
- Tập hai case bao phủ **kiểu `ApiResult`** theo quy tắc sealed hierarchy.
- Vì hai kiểu con không còn loại thứ ba được khai báo hợp lệ trong phân cấp này, compiler không yêu cầu `default`.

### Không phải cứ là interface thì có thể bỏ default

Với interface thông thường:

```java
interface Work {}
record Task(String name) implements Work {}
```

Một `Work` có thể được triển khai bởi nhiều lớp khác, kể cả các lớp được thêm sau. Vì vậy đoạn:

```java
// KHÔNG BIÊN DỊCH: interface mở còn nhiều triển khai có thể có.
// static String workKind(Work work) {
//     return switch (work) {
//         case Task t -> t.name();
//     };
// }
```

không exhaustive. Có thể thêm `default` hoặc một type pattern bao quát các giá trị `Work` để xử lý.

### Nếu một nhánh sealed vẫn cho phép mở rộng?

Một kiểu được `permits` có thể là `non-sealed`, cho phép các lớp con mới ở dưới nó. Khi đó bạn không thể giả định chỉ một số lớp con cụ thể đã liệt kê là đủ. Một case type pattern trên **toàn bộ nhánh `non-sealed`** sẽ bao phủ mọi đối tượng thuộc nhánh đó.

Ví dụ ý tưởng:

```java
sealed interface Message permits TextMessage, SystemMessage {}

record TextMessage(String text) implements Message {}

non-sealed interface SystemMessage extends Message {}
```

Muốn exhaustive không dùng default, có thể dùng `case TextMessage t` cùng `case SystemMessage s`; pattern thứ hai bao phủ mọi triển khai của `SystemMessage`, không chỉ một lớp con đang có.

**Quy tắc:** exhaustiveness được quyết định bằng **độ bao phủ kiểu**, không đơn thuần bằng số dòng `case`.

## 7. Cách 4: type pattern bao quát (unconditional pattern)

Một cách khác để bao phủ đầu vào mở là dùng một pattern có thể nhận mọi giá trị **khác `null`** của kiểu selector.

```java
static String anyNonNull(Object value) {
    return switch (value) {
        case String s -> "TEXT:" + s;
        case Object o -> "OTHER_OBJECT:" + o.getClass().getSimpleName();
    };
}
```

Trên Java 21, `case Object o` là một **unconditional type pattern** đối với selector kiểu `Object`; nó bao phủ mọi giá trị đối tượng khác `null` còn lại. Vì vậy switch expression được xem là exhaustive, không cần `default`.

Nhưng `anyNonNull(null)` vẫn ném `NullPointerException` vì **không có `case null`**.

Nếu muốn định nghĩa rõ cách xử lý `null`, thêm nó:

```java
static String anyValue(Object value) {
    return switch (value) {
        case null     -> "NULL";
        case String s -> "TEXT:" + s;
        case Object o -> "OBJECT:" + o.getClass().getSimpleName();
    };
}
```

Ở đây `case Object o` bao phủ những giá trị khác `null` chưa thuộc `String`, còn `case null` xử lý trường hợp rỗng.

### Quy tắc thứ tự: case hẹp trước, case rộng sau

```java
// KHÔNG BIÊN DỊCH: String bị Object bao phủ trước.
// return switch (value) {
//     case Object o -> "OBJECT";
//     case String s -> "STRING";
// };
```

Java chặn nhánh `String` bị **dominated** bởi `Object`. Muốn xử lý riêng `String`, đặt `case String s` trước `case Object o`.

Đồng thời không nên thêm `default` sau một unconditional pattern trên chính selector đó: hai nhãn cùng đóng vai trò bắt tất cả sẽ xung đột theo quy tắc của switch.

## 8. `null` là ngoại lệ cần xử lý riêng

Đây là sự nhầm lẫn quan trọng nhất về khái niệm exhaustive.

**Exhaustive không có nghĩa tự động xử lý `null`.** Java kiểm tra độ bao phủ các giá trị theo kiểu, nhưng `null` không phải một giá trị enum và không khớp type pattern thông thường.

```java
static String color(Signal signal) {
    return switch (signal) {
        case RED    -> "red";
        case YELLOW -> "yellow";
        case GREEN  -> "green";
    };
}
```

Biểu thức này exhaustive đối với kiểu `Signal`, nhưng:

```java
// Nếu chạy:
// color(null);
// -> NullPointerException.
```

Vì không có `case null`, đầu vào rỗng dẫn tới ngoại lệ, **dù quá trình biên dịch đã thành công**.

### Chọn cách xử lý `null` theo nghiệp vụ

**Cách 1: bắt `null` trong switch Java 21**

```java
static String safeColor(Signal signal) {
    return switch (signal) {
        case null   -> "missing";
        case RED    -> "red";
        case YELLOW -> "yellow";
        case GREEN  -> "green";
    };
}
```

**Cách 2: từ chối `null` ngay đầu phương thức**

```java
static String requiredColor(Signal signal) {
    java.util.Objects.requireNonNull(signal, "signal");
    return switch (signal) {
        case RED    -> "red";
        case YELLOW -> "yellow";
        case GREEN  -> "green";
    };
}
```

Cách 2 không biến `null` thành một enum constant; nó chỉ làm điều kiện không cho phép `null` trở nên tường minh.

**Cách 3: gộp `null` với `default`** nếu muốn cùng một kết quả cho cả hai:

```java
static String category(Object value) {
    return switch (value) {
        case String s     -> "TEXT:" + s;
        case null, default -> "UNKNOWN";
    };
}
```

**Lưu ý:** `default` đơn lẻ không phải nhãn xử lý `null`. Với pattern switch Java 21, nếu muốn `null` đi vào một nhánh, dùng `case null` hoặc `case null, default`.

## 9. Guard `when` có làm switch exhaustive không?

**Guard** là điều kiện bổ sung được kiểm tra sau khi type pattern khớp. Ví dụ:

```java
static String numberCase(Object value) {
    return switch (value) {
        case Integer n when n > 0 -> "POSITIVE";
        case Integer n            -> "NON_POSITIVE_INTEGER";
        default                   -> "OTHER";
    };
}
```

`case Integer n when n > 0` **không bao phủ mọi `Integer`**: nó chỉ khớp số dương. Một `Integer` bằng 0 hoặc âm đi tới `case Integer n` không guard. `default` xử lý các kiểu khác.

Nếu chỉ có một guarded pattern:

```java
// KHÔNG BIÊN DỊCH: không exhaustive.
// static String onlyPositive(Object value) {
//     return switch (value) {
//         case Integer n when n > 0 -> "POSITIVE";
//     };
// }
```

thì switch expression vẫn còn rất nhiều giá trị chưa được bao phủ: số không, số âm, chuỗi, các đối tượng khác.

### Guard không phải bảo đảm tĩnh bao phủ mọi giá trị

Khi phân tích exhaustiveness, trình biên dịch sử dụng các **case constants** và các **case patterns không bị giới hạn bởi guard động**, cùng những quy tắc bao phủ kiểu. Không được giả định rằng compiler có thể suy luận sự đầy đủ từ mọi biểu thức boolean tùy ý.

Ví dụ ý tưởng:

```java
// KHÔNG NÊN COI là exhaustive chỉ vì hai guard có vẻ
// chia đầy đủ các tình huống Integer:
// case Integer n when n >= 0 -> ...
// case Integer n when n < 0  -> ...
```

Với selector `Integer`, compiler không xem hai điều kiện nghiệp vụ `n >= 0` và `n < 0` là một bằng chứng tổng quát thay thế cho case không guard.

**Cách rõ ràng:** đặt case có guard trước, rồi một case cùng kiểu không guard phía sau. Với selector là `Object`, thêm nhánh cho kiểu khác hoặc `default` để exhaustive.

### Dominance không đồng nghĩa exhaustiveness

Nếu đặt `case Integer n` không guard **trước** `case Integer n when n > 0`, nhánh có guard sau sẽ bị bao phủ hoàn toàn và gây lỗi **dominated case**. Như vậy Java có ít nhất hai loại kiểm tra khác nhau:

- **Exhaustiveness:** có thiếu trường hợp cần xử lý không?
- **Dominance:** có case nào đứng sau không thể được chọn vì case trước đã bao phủ nó không?

Một switch có `default` vẫn có thể mắc lỗi dominance; hai quy tắc không thay thế nhau.

## 10. Record patterns và exhaustiveness

**Record pattern** (chuẩn hóa ở Java 21, JEP 440) có thể tách thành phần record và tham gia vào phép kiểm tra exhaustiveness.

Ví dụ:

```java
record Point(int x, int y) {}

static String pointKind(Point point) {
    return switch (point) {
        case Point(int x, int y) -> "POINT:" + x + "," + y;
    };
}
```

Với `Point` chứa **hai thành phần `int`**, record pattern trên bao phủ mọi giá trị `Point` khác `null` hợp lệ: mỗi điểm đều có một giá trị nguyên cho `x` và `y`. Do đó switch expression exhaustive đối với kiểu `Point`.

### Nếu record pattern chỉ khớp một phần kiểu thành phần?

```java
record Box(Object content) {}
```

Một `Box` có thể chứa `String`, `Integer`, `null` hoặc kiểu khác. Vì thế:

```java
// KHÔNG BIÊN DỊCH: thiếu nhiều khả năng Box.
// static String onlyString(Box box) {
//     return switch (box) {
//         case Box(String text) -> text;
//     };
// }
```

không exhaustive. `case Box(String text)` chỉ khớp những `Box` mà thành phần tương ứng phù hợp `String`; nó không đủ bao phủ mọi `Box`.

**Cách sửa dễ hiểu và an toàn:**

```java
static String boxKind(Box box) {
    return switch (box) {
        case Box(String text) -> "TEXT:" + text;
        case Box other        -> "OTHER_BOX";
    };
}
```

`case Box other` là **type pattern** bao phủ toàn bộ các `Box` khác `null` còn lại, bất kể nội dung. Nó nằm sau nhánh chuyên biệt, tránh dominance.

Lưu ý: record patterns phức tạp còn có quy tắc kết hợp nhiều nhánh để chứng minh độ bao phủ. Đối với bài học nhập môn, hãy kiểm tra liệu các component patterns đã bao phủ **mọi giá trị có thể có của mỗi thành phần** hay chưa. Nếu không chắc, một type pattern tổng quát cho record hoặc `default` là giải pháp dễ đọc.

### Record pattern và `null` ở component khác với `null` ở selector

`new Box(null)` **không phải** giá trị selector `null`; nó là một đối tượng `Box` hợp lệ có trường `content == null`. Nhánh `case Box other` nhận được đối tượng này, còn `case Box(String text)` không khớp khi component là `null`. Sự phân biệt này rất quan trọng khi viết các case có record deconstruction.

## 11. Mối quan hệ với sealed hierarchy, generic và evolution

### 11.1. Thêm kiểu con mới có thể làm mất exhaustiveness

Giả sử hiện tại:

```java
sealed interface Result permits Success, Failure {}
record Success(String value) implements Result {}
record Failure(String reason) implements Result {}
```

Một switch có hai case `Success` và `Failure` có thể exhaustive.

Nếu sau này **chỉnh lại nguồn sealed interface** để cho phép thêm `Pending`:

```java
// Minh họa thay đổi thiết kế, không đặt cùng các khai báo trước:
// sealed interface Result permits Success, Failure, Pending {}
// record Pending() implements Result {}
```

thì khi biên dịch lại mã nguồn liên quan, những switch expression chưa có nhánh cho `Pending` có thể bị compiler đánh dấu không exhaustive. Đây là một giá trị lớn của **sealed + pattern switch**.

### 11.2. Generic có thể làm độ bao phủ tinh vi hơn

Với sealed interface có tham số kiểu, một kiểu con có thể chỉ triển khai một cách tham số hóa nhất định. Vì thế không phải lúc nào cũng cần liệt kê mọi kiểu con `permits` cho **mọi phiên bản generic của selector**. Trình biên dịch xét tính phù hợp của kiểu con với kiểu selector thực tế.

Quy tắc tổng quát vẫn là: **compiler chứng minh khả năng bao phủ dựa trên kiểu tĩnh**, không dựa vào dữ liệu đang có trong một lần chạy. Khi dùng generic phức tạp, ưu tiên kiểm tra với đúng Java language level của dự án, và đọc JLS §14.11.1.1 để hiểu chi tiết.

### 11.3. Điều gì xảy ra nếu lớp/enum thay đổi mà chưa biên dịch lại phía gọi?

Kiểm tra exhaustiveness xảy ra lúc **biên dịch**. Trong các hệ thống phân phối nhiều thư viện độc lập, có thể xuất hiện tình huống code chứa switch đã được biên dịch với một enum hoặc sealed hierarchy cũ, rồi runtime nạp phiên bản thư viện đã thay đổi.

Ở Java 21, nếu thực thi một **exhaustive switch** và thực tế không có nhãn case nào áp dụng cho giá trị khác `null`, runtime có thể ném **`MatchException`**. Điều này phản ánh việc giả định bao phủ lúc biên dịch không còn đúng với môi trường runtime.

Vì vậy exhaustive là một bảo đảm rất mạnh ở mức biên dịch, **nhưng không thay thế quản lý tương thích nhị phân, nâng cấp phụ thuộc và kiểm thử tích hợp**.

## 12. Một chương trình Java 21 hoàn chỉnh

Tạo file **`ExhaustiveSwitchDemo.java`**:

```java
public class ExhaustiveSwitchDemo {

    enum Signal {
        RED, YELLOW, GREEN
    }

    sealed interface Event permits Started, Finished {}

    record Started(String name) implements Event {}

    record Finished(int code) implements Event {}

    record Point(int x, int y) {}

    // Exhaustive bằng cách liệt kê toàn bộ enum constants.
    static String traffic(Signal signal) {
        return switch (signal) {
            case RED    -> "STOP";
            case YELLOW -> "WAIT";
            case GREEN  -> "GO";
        };
    }

    // Exhaustive bằng sealed hierarchy.
    static String event(Event value) {
        return switch (value) {
            case Started s  -> "START:" + s.name();
            case Finished f -> "FINISH:" + f.code();
        };
    }

    // Selector Object: cần bao phủ mọi kiểu còn lại.
    // Có case null để xử lý riêng null.
    static String classify(Object value) {
        return switch (value) {
            case null                          -> "NULL";
            case String s when s.isBlank()      -> "BLANK";
            case String s                       -> "TEXT:" + s.strip();
            case Number n                       -> "NUMBER:" + n;
            default                             -> "OTHER";
        };
    }

    // Record pattern tổng quát bao phủ mọi Point khác null.
    static String pointKind(Point point) {
        return switch (point) {
            case Point(int x, int y) when x == y -> "DIAGONAL:" + x;
            case Point(int x, int y)             -> "POINT:" + x + "," + y;
        };
    }

    // Đây là enhanced switch STATEMENT, cũng phải exhaustive.
    static void printAction(Object value) {
        switch (value) {
            case null     -> System.out.println("ACTION:NULL");
            case String s -> System.out.println("ACTION:TEXT");
            default       -> System.out.println("ACTION:OTHER");
        }
    }

    public static void main(String[] args) {
        System.out.println(traffic(Signal.RED));
        System.out.println(traffic(Signal.YELLOW));
        System.out.println(traffic(Signal.GREEN));

        System.out.println(event(new Started("Job")));
        System.out.println(event(new Finished(0)));

        System.out.println(classify("  Java  "));
        System.out.println(classify("   "));
        System.out.println(classify(3.5));
        System.out.println(classify(true));
        System.out.println(classify(null));

        System.out.println(pointKind(new Point(2, 2)));
        System.out.println(pointKind(new Point(2, 5)));

        printAction("abc");
        printAction(10);
        printAction(null);
    }
}
```

Biên dịch và chạy bằng **JDK 21 trở lên** (không cần preview):

```bash
javac --release 21 ExhaustiveSwitchDemo.java
java ExhaustiveSwitchDemo
```

**Kết quả chuẩn:**

```text
STOP
WAIT
GO
START:Job
FINISH:0
TEXT:Java
BLANK
NUMBER:3.5
OTHER
NULL
DIAGONAL:2
POINT:2,5
ACTION:TEXT
ACTION:OTHER
ACTION:NULL
```

### Vì sao từng switch trong chương trình exhaustive?

| Phương thức | Kiểu selector | Vì sao exhaustive? | Có xử lý `null`? |
| --- | --- | --- | --- |
| `traffic` | `Signal` | Đủ `RED`, `YELLOW`, `GREEN` | Không: `null` gây NPE |
| `event` | `Event` sealed | Đủ hai kiểu được phép: `Started`, `Finished` | Không: `null` gây NPE |
| `classify` | `Object` | Có `default` bao phủ các kiểu còn lại | Có: `case null` |
| `pointKind` | `Point` | Record pattern không guard bao phủ mọi `Point`; guard chuyên biệt trước | Không: `null` gây NPE |
| `printAction` | `Object` | Enhanced switch statement có `default` | Có: `case null` |

Chương trình không gọi các phương thức không xử lý `null` với giá trị `null`; cột cuối nhằm giải thích ranh giới của kiểm tra exhaustive, không phải mô tả một đầu ra được in trong chương trình.

`printAction` là **switch statement**, nên các rule sau `->` là các lệnh `System.out.println(...)` hợp lệ. Những phương thức khác trả về **switch expression** và phải cung cấp kết quả phù hợp.

## 13. Các lỗi thường gặp

### Lỗi A: nghĩ rằng thêm vài case thường gặp là đủ

```java
// KHÔNG BIÊN DỊCH:
// static String kind(Object value) {
//     return switch (value) {
//         case String s  -> "TEXT";
//         case Integer n -> "NUMBER";
//     };
// }
```

Vì `Object` còn có `Double`, `Boolean`, danh sách, record..., switch expression chưa exhaustive. Cần thêm `default` hoặc một type pattern phù hợp để bao phủ phần còn lại.

### Lỗi B: nhầm switch statement cổ điển với enhanced switch statement

Một statement cổ điển trên `Signal` chỉ có `case RED` vẫn được phép. Nhưng một statement nhận `Object` chỉ có `case String s` bị từ chối nếu thiếu nhánh bao quát. Cả hai đều dùng từ khóa `switch`, song quy tắc exhaustiveness khác nhau ở Java 21.

### Lỗi C: nghĩ `default` bắt `null`

```java
// Khi value == null, KHÔNG chọn default chỉ vì có default.
// static String kind(Object value) {
//     return switch (value) {
//         case String s -> s;
//         default       -> "OTHER";
//     };
// }
```

Nếu selector rỗng và không có `case null`, switch ném `NullPointerException`. Thêm `case null` hoặc `case null, default` nếu muốn xử lý thay vì ném ngoại lệ.

### Lỗi D: nghĩ guard luôn bao phủ toàn bộ kiểu

`case Integer n when n > 0` không nhận số `0` và số âm. Một biểu thức switch chỉ có guarded case này không exhaustive. Thêm `case Integer n` tổng quát phía sau hoặc `default` phù hợp.

### Lỗi E: dùng `default` để “chữa” dominance

```java
// KHÔNG BIÊN DỊCH:
// return switch (value) {
//     case Number n  -> "NUMBER";
//     case Integer i -> "INTEGER";
//     default        -> "OTHER";
// };
```

`Integer` là một `Number`, nên case `Integer` phía sau bị **dominated**. `default` không sửa được lỗi này; phải đặt case hẹp trước case rộng.

### Lỗi F: liệt kê một vài kiểu con của interface mở rồi bỏ default

Nếu interface không `sealed` và có thể được triển khai bởi nhiều lớp, compiler không thể giả định các lớp hiện đang thấy là toàn bộ khả năng. Để exhaustive, dùng `default` hoặc một pattern tổng quát bao phủ interface. Chỉ dùng sealed khi điều đó phù hợp với thiết kế domain.

### Lỗi G: biến exhaustive thành cam kết “không bao giờ có ngoại lệ”

Một case có thể tự ném ngoại lệ, gọi phương thức thất bại, hoặc xử lý input `null` sai cách. Exhaustive chỉ kiểm tra **độ bao phủ các nhãn**. Vẫn cần kiểm tra dữ liệu, xử lý ngoại lệ và viết test.

## 14. Quy trình tự kiểm tra một switch có exhaustive hay không

Khi review code Java 21, hãy hỏi lần lượt:

1. **Đây là expression hay statement?** Nếu là expression, exhaustive là bắt buộc. Nếu là statement, nó có thuộc dạng enhanced (pattern/case null/selector mới) không?
2. **Kiểu tĩnh của selector là gì?** `enum`, sealed interface/class, `Object`, interface mở, record?
3. **Có `default` không?** Nếu có, switch thường exhaustive theo quy tắc bao phủ; vẫn phải kiểm tra dominance và `null`.
4. **Nếu không có default, các case có thực sự bao phủ kiểu selector?** Với enum: đủ hằng. Với sealed: đủ các nhánh kiểu được phép. Với Object: có pattern bao quát. Với record pattern: thành phần có được bao phủ đủ không?
5. **Các guard có bỏ sót giá trị không?** `when` với điều kiện động thường không thay cho một nhánh tổng quát.
6. **Có case nào bị case trước bao phủ không?** Nếu có, lỗi dominance tồn tại độc lập với exhaustiveness.
7. **`null` được xử lý ra sao?** Có `case null`, `case null, default`, chủ động reject null, hay chấp nhận NPE?
8. **Có khả năng thay đổi thư viện giữa compile-time và runtime không?** Nếu có, tính exhaustive biên dịch không thay thế kiểm thử tương thích nhị phân.

Bảng tổng kết:

| Tình huống Java 21 | Exhaustive? | Kết luận |
| --- | --- | --- |
| Expression trên enum, liệt kê đủ mọi hằng | Có | Không cần `default` |
| Expression trên enum, thiếu một hằng, không `default` | Không | Lỗi biên dịch |
| Statement cổ điển trên enum, chỉ có một case | Không cần exhaustive | Vẫn biên dịch, có thể bỏ qua giá trị khác |
| Expression trên `Object` có `case String` và `default` | Có | Bao phủ cả các kiểu khác `String` |
| Enhanced statement trên `Object` chỉ có `case String` | Không | Lỗi biên dịch |
| Expression trên sealed interface với đủ type patterns | Có | Compiler chứng minh đủ các nhánh kiểu |
| Expression trên interface mở chỉ liệt kê một kiểu triển khai | Không | Cần nhánh bao phủ phần còn lại |
| Expression trên record `Point(int,int)` với `case Point(int x,int y)` | Có | Bao phủ mọi `Point` khác `null` |
| Expression chỉ có guarded pattern `case Integer i when i > 0` | Không | Các giá trị còn lại chưa được xử lý |
| Expression có `default` nhưng không có `case null` | Có về kiểu | `null` vẫn có thể gây `NullPointerException` |

## 15. Bài tập và đáp án

### Bài 1: thiếu enum constant

Cho:

```java
enum Priority { LOW, MEDIUM, HIGH }
```

Đoạn sau có exhaustive không?

```java
static int weight(Priority p) {
    return switch (p) {
        case LOW    -> 1;
        case MEDIUM -> 2;
    };
}
```

**Đáp án:** Không. Đây là switch expression thiếu `HIGH`, nên lỗi biên dịch. Thêm `case HIGH -> 3;` sẽ làm biểu thức exhaustive.

### Bài 2: statement cổ điển

```java
static void show(Priority p) {
    switch (p) {
        case HIGH -> System.out.println("High");
    }
}
```

**Đáp án:** Biên dịch được ở Java 21. Đây là classic switch statement trên enum, không có pattern hay `case null`, nên không bị bắt buộc exhaustive. Với `LOW` hoặc `MEDIUM`, phương thức không in gì.

### Bài 3: sealed hierarchy

Cho:

```java
sealed interface Node permits Leaf, Branch {}
record Leaf(int value) implements Node {}
record Branch(Node left, Node right) implements Node {}
```

Hãy viết switch expression đếm số nhánh trực tiếp: `Leaf` trả 0, `Branch` trả 2.

**Đáp án:**

```java
static int childCount(Node node) {
    return switch (node) {
        case Leaf l   -> 0;
        case Branch b -> 2;
    };
}
```

Đây là exhaustive vì `Node` chỉ cho phép `Leaf` và `Branch` trực tiếp triển khai. Lưu ý điều đó không tự đệ quy duyệt cây, và `node == null` vẫn gây NPE nếu không có `case null`.

### Bài 4: xử lý null

Xét:

```java
static String kind(Object o) {
    return switch (o) {
        case String s -> "S";
        default       -> "OTHER";
    };
}
```

- `kind(5)` → `"OTHER"`.
- `kind("Java")` → `"S"`.
- `kind(null)` → ném `NullPointerException`, không phải `"OTHER"`.

**Cách sửa nếu muốn `null` trả `"EMPTY"`:**

```java
static String kind(Object o) {
    return switch (o) {
        case null     -> "EMPTY";
        case String s -> "S";
        default       -> "OTHER";
    };
}
```

### Bài 5: điều kiện động có thay thế case tổng quát không?

```java
static String score(Object value) {
    return switch (value) {
        case Integer n when n > 0 -> "POSITIVE";
        case Integer n when n < 0 -> "NEGATIVE";
    };
}
```

**Đáp án:** Không exhaustive: giá trị `Integer.valueOf(0)` đã không khớp hai guard, chưa kể kiểu khác `Integer`. Cách sửa rõ ràng là thêm `case Integer n -> "ZERO";` sau hai nhánh guard và `default -> "OTHER";` cho các kiểu còn lại.

### Bài 6: thiết kế `switch` có khả năng tự nhắc khi domain mở rộng

Một ứng dụng có `sealed interface Payment permits Cash, Card` và hai lớp record tương ứng. Muốn khi bổ sung một kiểu `Transfer` trong nguồn, compiler nhắc người viết xem lại logic định tuyến thanh toán. Nên làm gì?

**Đáp án:** Dùng **switch expression exhaustive bằng hai type patterns `case Cash c` và `case Card c`**, không thêm `default` trừ khi có nhu cầu nghiệp vụ rõ ràng. Khi cập nhật `permits` và biên dịch lại, thiếu nhánh `Transfer` sẽ được phát hiện nếu chưa có pattern nào bao phủ nó.

## 16. Kết luận

**Exhaustive switch** trong Java là `switch` mà compiler có thể chứng minh đã bao phủ kiểu selector. Java 21 yêu cầu:

- **Mọi switch expression** phải exhaustive.
- **Mọi enhanced switch statement** phải exhaustive.
- **Switch statement cổ điển** không bắt buộc exhaustive để bảo toàn tính tương thích với mã trước đây.

Các cách tạo exhaustiveness gồm **`default`**, **đủ enum constants**, **đủ kiểu con trong sealed hierarchy**, hoặc **pattern bao quát**. **Record patterns** có thể tham gia chứng minh độ bao phủ khi các component patterns phù hợp.

Đặc biệt cần nhớ: **exhaustiveness không đồng nghĩa tự xử lý `null`**, không bảo đảm logic nghiệp vụ đúng và không ngăn mọi ngoại lệ runtime. Hãy phân biệt ba câu hỏi: *đủ nhánh chưa?* (exhaustiveness), *nhánh nào bị che khuất?* (dominance), và *xử lý null thế nào?* (null handling). Trả lời được cả ba sẽ giúp viết pattern switch an toàn, dễ mở rộng và dễ bảo trì.

## Tài liệu tham khảo chính thức

- [Java SE 21 Language Specification, §14.11.1.1 — Exhaustive Switch Blocks](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.11.1.1)
- [Java SE 21 Language Specification, §14.11.2 — The Switch Block of a switch Statement](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.11.2)
- [Java SE 21 Language Specification, §15.28 — Switch Expressions](https://docs.oracle.com/javase/specs/jls/se21/html/jls-15.html#jls-15.28)
- [JEP 441 — Pattern Matching for switch](https://openjdk.org/jeps/441)
- [JEP 440 — Record Patterns](https://openjdk.org/jeps/440)
- [Oracle Java 21 — Pattern Matching for switch](https://docs.oracle.com/en/java/javase/21/language/pattern-matching-switch.html)
