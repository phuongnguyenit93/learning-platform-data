# Xử lý null, tính đầy đủ và nhánh không thể tiếp cận trong Pattern Matching Java

Pattern matching giúp mã Java kiểm tra cấu trúc hoặc kiểu của một giá trị rồi trực tiếp sử dụng các thành phần đã khớp. Khi kết hợp với `switch`, lập trình viên có thể biểu diễn các biến thể dữ liệu rõ ràng, thay thế nhiều khối ép kiểu thủ công.

Tuy nhiên, một câu lệnh `switch` dùng pattern chỉ đúng khi chúng ta hiểu ba quy tắc:

1. Giá trị `null` được xử lý thế nào?
2. Các nhánh đã **đủ** để bao phủ mọi trường hợp cần xét hay chưa (*exhaustiveness*)?
3. Có nhánh nào bị một nhánh trước đó bao phủ hoàn toàn, nên không bao giờ được chọn (*dominance*, thường được mô tả là nhánh không thể tiếp cận)?

Bài học nằm trong chương **Pattern matching**, thuộc module **Java 27 và các kiến thức liên quan**. Các ví dụ tập trung vào `instanceof` pattern (chính thức từ Java 16), `switch` pattern (chính thức từ Java 21), record pattern (chính thức từ Java 21), `sealed` type và `switch` expression. Đây đều là những tính năng đã được chuẩn hóa, không yêu cầu bật preview. Chúng tiếp tục là kiến thức nền tảng phù hợp khi học Java 27; không dựa vào đề xuất preview hoặc tính năng thử nghiệm chưa ổn định.

## 1. Ba khái niệm cần phân biệt

| Khái niệm | Câu hỏi kiểm tra | Hệ quả thường gặp |
|---|---|---|
| **Null handling** | Khi biểu thức cần kiểm tra có giá trị `null`, nhánh nào được chọn? | `NullPointerException`, nhánh `case null`, hoặc `false` với `instanceof` |
| **Exhaustiveness** | Cấu trúc có thể tạo kết quả/hành vi cho mọi giá trị trong miền cần xét không? | Compiler yêu cầu đủ nhánh ở `switch` expression và pattern `switch` statement |
| **Dominance** | Một nhánh trước đã bắt hết giá trị có thể đến nhánh sau chưa? | Compiler báo lỗi do nhánh sau bị bao phủ |
| **Reachability** | Một dòng lệnh có thể được thực thi theo luồng điều khiển không? | Có thể phát sinh lỗi unreachable statement, nhưng không đồng nghĩa hoàn toàn với dominance |

Ví dụ đầu tiên:

```java
static String describe(Object value) {
    return switch (value) {
        case null -> "Không có dữ liệu";
        case String text -> "Chuỗi: " + text;
        case Integer number -> "Số nguyên: " + number;
        default -> "Đối tượng khác";
    };
}
```

Hành vi:

| Đầu vào | Kết quả |
|---|---|
| `null` | `"Không có dữ liệu"` |
| `"Java"` | `"Chuỗi: Java"` |
| `42` | `"Số nguyên: 42"` |
| `3.5` | `"Đối tượng khác"` |

`case null` xử lý giá trị không có tham chiếu; các type pattern xử lý đối tượng không `null` phù hợp; `default` xử lý phần còn lại.

## 2. Null trong instanceof pattern matching

Với cú pháp `instanceof` pattern:

```java
Object input = "Java";

if (input instanceof String text) {
    System.out.println(text.length());
}
```

Biến pattern `text` được khai báo khi phép kiểm tra kiểu khớp, không cần ép kiểu `(String) input` bằng tay.

### 2.1. Giá trị null luôn không khớp với instanceof type pattern

```java
Object input = null;

if (input instanceof String text) {
    System.out.println(text.length());
} else {
    System.out.println("Không phải String khác null");
}
```

Kết quả:

```text
Không phải String khác null
```

Biểu thức `input instanceof String text` trả về `false` khi `input == null`, chứ không ném `NullPointerException`.

Điều này cũng đúng với kiểm tra `instanceof String` truyền thống: `null instanceof String` là `false`.

### 2.2. Phân biệt null và sai kiểu

Nếu cần báo lỗi khác nhau cho trường hợp không có dữ liệu và trường hợp sai kiểu, phải kiểm tra tường minh:

```java
static int lengthOfString(Object input) {
    if (input == null) {
        throw new IllegalArgumentException("Thiếu giá trị");
    }

    if (input instanceof String text) {
        return text.length();
    }

    throw new IllegalArgumentException("Yêu cầu String");
}
```

Nếu chỉ viết một nhánh `if (input instanceof String text) ... else ...`, cả `null` lẫn đối tượng không phải String đều vào `else`.

### 2.3. Scope của pattern variable và điều kiện kết hợp

Biến pattern chỉ có mặt tại vị trí mà compiler xác định pattern chắc chắn đã khớp (*flow scoping*).

Hợp lệ:

```java
static boolean hasLongName(Object value) {
    return value instanceof String name && name.length() > 8;
}
```

`&&` đánh giá vế phải khi vế trái là `true`, nên `name` đã được xác định và khác `null`.

Không hợp lệ:

```java
// Không biên dịch: vế phải của || có thể chạy khi pattern không khớp.
// if (value instanceof String name || name.isEmpty()) {
//     ...
// }
```

Điều kiện `||` cần kiểm tra vế phải khi vế trái `false`, lúc đó `name` chưa chắc được khai báo trong phạm vi hợp lệ.

**Quy tắc thực hành:** không suy đoán scope của pattern variable chỉ từ dấu ngoặc; hãy xét luồng đánh giá boolean mà Java kiểm tra ở thời điểm biên dịch.

## 3. Null trong switch có pattern

Khác `instanceof`, một `switch` với selector kiểu tham chiếu thường **ném `NullPointerException` khi selector là `null`**, trừ khi có nhãn `case null` phù hợp.

```java
static String classify(Object value) {
    return switch (value) {
        case String text -> "String: " + text;
        case Integer number -> "Integer: " + number;
        default -> "Khác";
    };
}
```

Các lời gọi:

```java
classify("hello"); // "String: hello"
classify(12);      // "Integer: 12"
classify(2.5);     // "Khác"
// classify(null); // ném NullPointerException
```

Điểm dễ nhầm: **`default` không phải là nhánh xử lý `null`**. Nó xử lý những giá trị không `null` mà các case khác chưa bao phủ, theo quy tắc của `switch`.

### 3.1. Xử lý null trực tiếp bằng case null

```java
static String classifyNullable(Object value) {
    return switch (value) {
        case null -> "Thiếu dữ liệu";
        case String text -> "String: " + text;
        case Integer number -> "Integer: " + number;
        default -> "Khác";
    };
}
```

Lúc này:

```java
System.out.println(classifyNullable(null)); // Thiếu dữ liệu
```

`case null` là nhãn cho giá trị null, không phải một type pattern thông thường. Nó có thể đứng trước các case còn lại để người đọc thấy rõ chính sách xử lý thiếu dữ liệu.

### 3.2. Null có thể là dữ liệu hợp lệ hoặc một lỗi API

Không phải API nào cũng nên trả chuỗi thông báo khi nhận `null`. Có ít nhất ba chính sách phù hợp tùy hợp đồng:

- **Chấp nhận null:** `case null` trả một giá trị có nghĩa, chẳng hạn `"Chưa có trạng thái"`.
- **Từ chối null:** kiểm tra `Objects.requireNonNull(value)` hoặc cho phép `switch` ném `NullPointerException`, nếu API đã mô tả null là không hợp lệ.
- **Biểu diễn sự vắng mặt bằng kiểu khác:** khi việc vắng dữ liệu là một trường hợp nghiệp vụ thường xuyên, cân nhắc `Optional<T>` ở vị trí phù hợp hoặc một biến thể trong mô hình dữ liệu.

Tránh thêm `case null -> ...` một cách máy móc chỉ để "chống lỗi": nếu `null` là vi phạm hợp đồng, trả về một giá trị giả có thể che giấu bug ở nơi gọi.

### 3.3. Nhãn case null, default

Trong cú pháp pattern `switch` đã chuẩn hóa, có thể dùng nhãn đặc biệt:

```java
static String display(Object value) {
    return switch (value) {
        case String text -> text;
        case null, default -> "Không có nội dung hiển thị";
    };
}
```

Nhãn kết hợp `case null, default` dùng chung hành vi cho `null` và mọi giá trị còn lại. Đây là cú pháp đặc biệt; không nên suy ra rằng có thể ghép bất kỳ hai nhãn tùy ý với mọi type pattern.

Khi ý nghĩa của `null` khác với các trường hợp không được nhận diện, **ưu tiên viết hai nhánh tách biệt**:

```java
case null -> "Thiếu dữ liệu";
default -> "Loại dữ liệu không được hỗ trợ";
```

Hai dòng trên là các nhãn minh họa bên trong một `switch`; chúng không phải một file Java độc lập.

## 4. Type pattern không tự khớp null

Một type pattern, kể cả type pattern rất rộng như `Object`, chỉ khớp những đối tượng thích hợp **khác null**.

```java
static String inspect(Object value) {
    return switch (value) {
        case null -> "NULL";
        case Object object -> "NON_NULL: " + object.getClass().getSimpleName();
    };
}
```

Ở đây, `case Object object` bao phủ mọi giá trị **khác null** trong miền của `Object`. Không cần `default`: mọi đối tượng khác null được nhánh thứ hai bao phủ, còn null đã có nhánh riêng.

Nếu bỏ `case null`, một `switch` chỉ có `case Object object` vẫn có thể đầy đủ về **miền kiểu không null**, nhưng truyền null sẽ ném `NullPointerException`.

### 4.1. Tránh dùng null như một nhánh ngầm của default

Mã sau **không** diễn đạt chính xác việc "null hoặc loại khác":

```java
return switch (value) {
    case String text -> text;
    default -> "null hoặc không phải String";
};
```

Chuỗi trong `default` gây hiểu lầm: nếu `value == null`, thông thường code không đi vào default mà ném exception.

Sửa theo đúng mục tiêu:

```java
return switch (value) {
    case null -> "Không có dữ liệu";
    case String text -> text;
    default -> "Không phải String";
};
```

## 5. Tính đầy đủ (exhaustiveness) là gì?

Một `switch` đầy đủ khi compiler có thể xác định mọi trường hợp thuộc miền selector thích hợp đều có nhánh xử lý. Việc xác định này dựa trên kiểu của biểu thức selector và các nhãn `case`, không dựa trên việc lập trình viên "nghĩ rằng giá trị ấy sẽ không bao giờ xảy ra".

### 5.1. Switch expression phải đầy đủ

`switch` expression luôn phải tạo ra kết quả hoặc kết thúc theo một cách hợp lệ cho tất cả trường hợp được xem xét. Ví dụ không hợp lệ:

```java
enum Color {
    RED, GREEN, BLUE
}

// Không biên dịch: bỏ sót GREEN và BLUE.
// static String nameOf(Color color) {
//     return switch (color) {
//         case RED -> "Đỏ";
//     };
// }
```

Bản hợp lệ:

```java
static String nameOf(Color color) {
    return switch (color) {
        case RED -> "Đỏ";
        case GREEN -> "Xanh lá";
        case BLUE -> "Xanh dương";
    };
}
```

Vì tất cả hằng `Color` được liệt kê, compiler xem `switch` expression này là exhaustive dù không có `default`.

Tuy nhiên, `nameOf(null)` vẫn ném `NullPointerException`. **Đầy đủ về các hằng enum không đồng nghĩa đã xử lý null.**

### 5.2. Khác biệt giữa switch statement cổ điển và pattern switch statement

Các `switch` statement không dùng pattern hoặc null label vẫn có thể hợp lệ dù không liệt kê hết mọi trường hợp:

```java
static void logColor(Color color) {
    switch (color) {
        case RED -> System.out.println("Đỏ");
    }
}
```

Nếu `color` là `GREEN`, statement không thực hiện hành động nào.

Ngược lại, một **pattern switch statement** yêu cầu exhaustiveness:

```java
// Không biên dịch: thiếu các kiểu khác String.
// static void logObject(Object obj) {
//     switch (obj) {
//         case String s -> System.out.println(s);
//     }
// }
```

Sửa:

```java
static void logObject(Object obj) {
    switch (obj) {
        case String s -> System.out.println(s);
        default -> System.out.println("Không phải String");
    }
}
```

Việc thêm `default` làm statement bao phủ các giá trị không null còn lại. Nếu muốn chấp nhận null, thêm `case null` riêng.

### 5.3. Exhaustiveness là kiểm tra tại thời điểm biên dịch

Khi source code được biên dịch lại sau khi bổ sung một enum constant hay một subtype được phép, compiler có thể buộc cập nhật một `switch` expression không có nhánh bao quát phù hợp.

Đây là lợi thế: những vị trí cần xử lý biến thể mới được phát hiện rõ ràng, thay vì tự động rơi vào một nhánh `default` làm mất tín hiệu rằng mô hình đã mở rộng.

Nhưng đây **không phải chứng minh rằng nghiệp vụ đã xử lý đúng**. Một nhánh có thể tồn tại mà vẫn trả sai dữ liệu, gây side effect sai hoặc ném exception ngoài ý muốn.

## 6. Exhaustiveness với sealed interface

`sealed` interface cho phép liệt kê tập subtype được phép trực tiếp hoặc gián tiếp theo quy tắc của Java. Khi tập các nhánh kiểu đã được xác định, compiler có thể xem `switch` là exhaustive mà không cần `default`.

```java
sealed interface PaymentResult
        permits PaymentSucceeded, PaymentFailed {}

record PaymentSucceeded(String transactionId)
        implements PaymentResult {}

record PaymentFailed(String reason)
        implements PaymentResult {}
```

Một `switch` expression xử lý đủ hai loại:

```java
static String message(PaymentResult result) {
    return switch (result) {
        case PaymentSucceeded ok ->
                "Đã thanh toán: " + ok.transactionId();
        case PaymentFailed failed ->
                "Bị từ chối: " + failed.reason();
    };
}
```

Compiler có thể kết luận mỗi giá trị `PaymentResult` khác null đều thuộc một subtype được phép và đã có case phù hợp.

### 6.1. Xử lý null tách biệt với tính đầy đủ kiểu

Như với enum, `message(null)` ném `NullPointerException`. Nếu API chấp nhận null, ghi rõ:

```java
static String messageNullable(PaymentResult result) {
    return switch (result) {
        case null -> "Chưa nhận được kết quả";
        case PaymentSucceeded ok ->
                "Đã thanh toán: " + ok.transactionId();
        case PaymentFailed failed ->
                "Bị từ chối: " + failed.reason();
    };
}
```

Không thêm `default` khi chỉ cần hỗ trợ null: một nhánh `case null` riêng vẫn giữ lợi ích kiểm tra đầy đủ các biến thể khi mã nguồn được cập nhật.

### 6.2. Thêm subtype mới và lợi ích kiểm tra exhaustiveness

Ví dụ nếu sau này có thêm trạng thái `PaymentPending`, cần cập nhật khai báo `permits` và các nhánh `switch` cần xử lý biến thể này:

```java
// Phác thảo thay đổi mô hình:
// sealed interface PaymentResult
//         permits PaymentSucceeded, PaymentFailed, PaymentPending {}
//
// record PaymentPending(long expiresAtEpochSeconds)
//         implements PaymentResult {}
```

Khi biên dịch lại toàn bộ mã, những `switch` biểu thức thiếu nhánh xử lý subtype mới có thể bị báo lỗi. Đây là một cơ chế hỗ trợ bảo trì hữu ích.

**Lưu ý về binary compatibility:** mã đã được biên dịch từ trước có thể chạy với phiên bản class hoặc thư viện mới. Nếu xuất hiện một biến thể không được `switch` cũ dự tính, một `switch` từng được compiler xem là exhaustive có thể gặp `MatchException` lúc chạy khi không có nhánh áp dụng. Vì vậy, không nên nhầm kiểm tra exhaustiveness của source với cam kết tương thích nhị phân tuyệt đối.

## 7. Exhaustiveness không đồng nghĩa mọi guard đã đúng

Pattern `case ... when condition` được gọi là **guarded pattern**: một nhánh chỉ được chọn khi type pattern phù hợp và biểu thức guard trả về `true`.

```java
static String label(Object value) {
    return switch (value) {
        case null -> "NULL";
        case String s when s.isBlank() -> "Chuỗi trắng";
        case String s -> "Chuỗi: " + s;
        default -> "Kiểu khác";
    };
}
```

Luồng chọn nhánh:

1. Nếu `value == null`, chọn `case null`.
2. Nếu là `String`, guard `s.isBlank()` được đánh giá.
3. Nếu guard đúng, chọn `"Chuỗi trắng"`.
4. Nếu guard sai, xét nhánh `case String s` tiếp theo.
5. Những đối tượng khác chọn `default`.

Với chuỗi `""` hoặc `"   "`, guard đúng. Với `"Java"`, nhánh `case String s` không guard xử lý.

### 7.1. Guarded case không nhất thiết bao phủ mọi giá trị của kiểu

Đoạn sau **không exhaustive** cho mọi `String`:

```java
// Không biên dịch: một String không rỗng không có nhánh.
// static String bad(String value) {
//     return switch (value) {
//         case String s when s.isEmpty() -> "Rỗng";
//     };
// }
```

Compiler không được phép suy ra `s.isEmpty()` luôn đúng. Một điều kiện nghiệp vụ có thể thay đổi theo đầu vào và không thay cho nhánh không guard.

Bản đúng:

```java
static String describeText(String value) {
    return switch (value) {
        case null -> "Thiếu";
        case String s when s.isEmpty() -> "Rỗng";
        case String s -> "Có nội dung";
    };
}
```

`case String s` phía sau bao phủ mọi chuỗi không null còn lại. Nhánh `case null` xử lý null riêng biệt.

### 7.2. Guard chỉ chạy sau khi pattern khớp

Trong nhánh `case String s when s.length() >= 3`, biến `s` chắc chắn là tham chiếu `String` khác null ở lúc guard chạy. Không cần kiểm tra `s != null` chỉ để tránh null của chính giá trị selector.

Tuy nhiên, **các field hoặc giá trị mà method trả về có thể vẫn null**:

```java
record User(String name) {}

static String displayUser(Object value) {
    return switch (value) {
        case null -> "Không có người dùng";
        case User u when u.name() != null && !u.name().isBlank() ->
                u.name();
        case User u -> "Người dùng chưa có tên";
        default -> "Không phải User";
    };
}
```

Ở đây, pattern `User u` kiểm tra đối tượng `User`, chứ không đảm bảo `u.name()` luôn khác null. Guard kiểm tra dữ liệu con trước khi sử dụng.

## 8. Dominance: nhánh bị bao phủ là gì?

Một nhánh `case` bị **dominated** khi mọi giá trị có thể khớp với nhánh ấy đã khớp với một nhánh đứng trước trong cùng `switch`. Java từ chối loại nhánh không thể được chọn này tại thời điểm biên dịch.

Ví dụ:

```java
// Không hợp lệ: String là một CharSequence.
// static String wrong(Object value) {
//     return switch (value) {
//         case CharSequence sequence -> "Chuỗi ký tự";
//         case String text -> "String"; // bị nhánh trước bao phủ
//         default -> "Khác";
//     };
// }
```

Mọi `String` đều triển khai `CharSequence`. Khi `case CharSequence sequence` đứng trước, một `String` sẽ khớp tại đó; nhánh `case String text` không có cơ hội được chọn.

Sửa bằng cách đưa trường hợp cụ thể lên trước:

```java
static String classifyText(Object value) {
    return switch (value) {
        case null -> "Thiếu";
        case String text -> "String: " + text;
        case CharSequence sequence -> "CharSequence khác String";
        default -> "Khác";
    };
}
```

**Quy tắc đọc:** từ cụ thể đến tổng quát thường là thứ tự hợp lý khi nhiều type pattern có quan hệ kế thừa. Compiler mới là bên kiểm tra dominance thực tế, không chỉ dựa trên tên case.

### 8.1. Nhánh Object đứng trước các kiểu cụ thể

```java
// Không hợp lệ:
// switch (value) {
//     case Object obj -> "Bất kỳ đối tượng khác null";
//     case Integer n -> "Integer"; // dominated
// }
```

`case Object obj` áp dụng cho mọi đối tượng khác null. Vì vậy, không nên đặt nó trước các type pattern hẹp hơn mà vẫn muốn xử lý riêng.

`case Object obj` cũng được gọi là **unconditional pattern** trong trường hợp nó bao phủ tất cả giá trị không null của kiểu selector. Nó có thể làm vai trò nhánh cuối.

### 8.2. Unconditional pattern và default xung đột

Câu lệnh sau không hợp lệ:

```java
// Không hợp lệ: switch có cả unconditional pattern và default.
// return switch (value) {
//     case Object obj -> obj.toString();
//     default -> "Khác";
// };
```

Khi `case Object obj` đã bao phủ mọi đối tượng khác null, `default` không còn trường hợp không null để xử lý. Theo quy tắc switch, không thể đặt đồng thời một unconditional pattern và một default label trong cùng switch block.

Nếu vẫn cần xử lý null, dùng một `case null` riêng:

```java
static String stringify(Object value) {
    return switch (value) {
        case null -> "null";
        case Object obj -> obj.toString();
    };
}
```

### 8.3. Hai nhánh cho cùng một kiểu

```java
// Không hợp lệ:
// switch (value) {
//     case String first -> "1";
//     case String second -> "2"; // bị dominated
//     default -> "Khác";
// }
```

Hai type pattern cùng kiểu và đều không có guard không phải là hai trường hợp riêng biệt. Hãy xóa nhánh trùng hoặc phân biệt bằng guarded pattern có ý nghĩa.

### 8.4. Guarded pattern và dominance

Guard làm một nhánh hẹp hơn điều kiện khớp kiểu, vì vậy thứ tự phổ biến là:

```java
static String categorizeString(Object value) {
    return switch (value) {
        case null -> "null";
        case String s when s.isBlank() -> "blank";
        case String s when s.length() > 20 -> "long";
        case String s -> "other string";
        default -> "other type";
    };
}
```

Những nhánh có guard chỉ xử lý tập con của `String`, sau đó nhánh `case String s` không có guard xử lý phần còn lại.

Ngược lại, thứ tự này sai:

```java
// Không hợp lệ: nhánh unguarded đã bao phủ String.
// switch (value) {
//     case String s -> "String";
//     case String s when s.isBlank() -> "Blank"; // dominated
//     default -> "Khác";
// }
```

Một nhánh unguarded đã nhận mọi `String`, nên nhánh guarded phía sau không thể được chọn.

**Điểm tinh tế:** compiler không cố giải toàn bộ logic nghiệp vụ trong guard. Nó áp dụng quy tắc của ngôn ngữ về những điều kiện có thể được xem là bao phủ, không phải một bộ giải toán tổng quát. Không nên trông đợi compiler chứng minh rằng hai điều kiện `when` tùy ý luôn đối nghịch nhau và vì vậy đủ bao phủ một kiểu.

## 9. Dominance khác unreachable statement

Hai khái niệm liên quan nhưng không giống nhau.

### 9.1. Dominance thuộc về lựa chọn case

```java
// case CharSequence -> ... đứng trước case String -> ...
```

Đó là quan hệ bao phủ giữa các label trong pattern `switch`, được compiler kiểm tra theo các quy tắc cụ thể của switch.

### 9.2. Unreachable statement thuộc về luồng điều khiển

```java
// Không hợp lệ: câu lệnh phía sau return không thể chạy.
// static int calculate() {
//     return 10;
//     // System.out.println("Không bao giờ chạy");
// }
```

Dù đều liên quan đến "không thể tới", **không nên sửa lỗi dominance bằng cách thêm code tùy tiện**. Hãy sửa **thứ tự, kiểu hoặc guard của case** để các nhánh biểu đạt những trường hợp thực sự phân biệt.

### 9.3. Nhánh hợp lệ nhưng không phát sinh trong dữ liệu thực tế

Một nhánh có thể không bao giờ xảy ra trong hệ thống hiện tại mà vẫn **không bị dominated** theo luật Java:

```java
static String fromInput(Object input) {
    return switch (input) {
        case String s -> s;
        case Integer i -> "Số: " + i;
        default -> "Loại khác";
    };
}
```

Nếu toàn bộ ứng dụng hiện chỉ truyền `String`, điều đó không khiến `case Integer` bị compiler coi là dominated. Compiler xét miền **kiểu và quy tắc switch**, không xét dữ liệu sản xuất đã quan sát được.

## 10. Record pattern và xử lý dữ liệu lồng nhau

Record pattern dùng để kiểm tra một giá trị record rồi trích xuất các thành phần:

```java
record Point(int x, int y) {}

static String describePoint(Object value) {
    return switch (value) {
        case null -> "Không có điểm";
        case Point(int x, int y) -> "Điểm (" + x + ", " + y + ")";
        default -> "Không phải Point";
    };
}
```

Trong nhánh `case Point(int x, int y)`, compiler biết đối tượng `Point` khớp và có thể dùng hai thành phần `x`, `y`. Ở đây hai thành phần là `int`, nên không phát sinh câu hỏi về null của chúng.

### 10.1. Record pattern không thay thế mọi kiểm tra null nghiệp vụ

Nếu record có field tham chiếu, record có thể chứa `null` trừ khi constructor đã cấm. Với logic cần rõ chính sách thiếu dữ liệu, type pattern cộng accessor có thể là lựa chọn dễ đọc:

```java
record Customer(String name, String email) {}

static String emailOf(Object value) {
    return switch (value) {
        case null -> "Thiếu khách hàng";
        case Customer c when c.email() == null -> "Thiếu email";
        case Customer c -> c.email();
        default -> "Không phải khách hàng";
    };
}
```

Ở đây `null` ở mức selector (`value == null`) khác với `null` ở một thành phần bên trong record (`c.email() == null`). Đây là hai điều kiện nghiệp vụ khác nhau và nên được diễn đạt riêng.

Khi dùng nested record pattern, các quy tắc khớp của từng pattern con cũng phải được xem xét. Không nên giả định "record ngoài khác null" đồng nghĩa "mọi thành phần lồng bên trong đều khác null".

### 10.2. Record pattern và exhaustiveness của sealed type

Ta có thể kết hợp sealed hierarchy với record pattern:

```java
sealed interface Shape permits Circle, Rectangle {}

record Circle(double radius) implements Shape {}
record Rectangle(double width, double height) implements Shape {}

static double area(Shape shape) {
    return switch (shape) {
        case Circle(double radius) -> Math.PI * radius * radius;
        case Rectangle(double width, double height) -> width * height;
    };
}
```

Trong ví dụ, các thành phần record là primitive và cả hai subtype được phép đều có case. Vì vậy, ví dụ minh họa rõ việc record pattern lấy dữ liệu đồng thời sealed type giúp compiler xác định exhaustiveness.

Một `switch` đầy đủ về kiểu vẫn không tự kiểm tra bán kính âm, `NaN` hoặc chiều dài âm. **Kiểm tra hợp lệ của dữ liệu** nên nằm trong constructor hoặc tầng domain phù hợp; exhaustiveness chỉ giải quyết việc bao phủ trường hợp lựa chọn.

## 11. Default: khi nào nên có, khi nào nên tránh?

`default` có vai trò hữu ích khi selector được thiết kế cố ý mở hoặc kiểu của nó rộng, chẳng hạn `Object`:

```java
static String humanReadable(Object input) {
    return switch (input) {
        case null -> "(missing)";
        case String s -> s;
        case Number number -> number.toString();
        default -> input.getClass().getSimpleName();
    };
}
```

Ở đây, `Object` cho phép nhiều kiểu ngoài `String` và `Number`, nên một fallback là hợp lý.

Ngược lại, với `enum` hay `sealed` hierarchy đóng, dùng `default` rộng có thể che giấu việc bổ sung biến thể mới:

```java
enum JobState {
    QUEUED, RUNNING, FINISHED
}

// Ít hỗ trợ phát hiện bổ sung trạng thái:
static String weakLabel(JobState state) {
    return switch (state) {
        case QUEUED -> "Chờ";
        default -> "Khác";
    };
}
```

Khi thêm `FAILED`, code có thể tiếp tục biên dịch mà không nhắc người viết bổ sung nhãn chính xác.

Nếu mục tiêu là mỗi trạng thái có hành vi riêng, nên viết:

```java
static String preciseLabel(JobState state) {
    return switch (state) {
        case QUEUED -> "Chờ";
        case RUNNING -> "Đang chạy";
        case FINISHED -> "Hoàn tất";
    };
}
```

Khi mô hình thay đổi và được biên dịch lại, thiếu case mới có thể trở thành lỗi biên dịch.

Tóm lại: **dùng default khi miền thực sự mở hoặc fallback là một phần cố ý của hợp đồng; tránh default bao trùm khi muốn compiler giúp phát hiện thay đổi ở tập biến thể đóng.**

## 12. Ví dụ Java hoàn chỉnh: xử lý null, exhaustiveness và guard

Lưu đoạn mã sau thành file `PatternMatchingDemo.java`. Chương trình dùng sealed interface, hai record cho kết quả thanh toán, xử lý null tường minh, các guarded case và các nhánh không guard giúp bao phủ hết tập kiểu.

```java
sealed interface PaymentOutcome
        permits Approved, Rejected {}

record Approved(String transactionId) implements PaymentOutcome {}

record Rejected(String reason) implements PaymentOutcome {}

public class PatternMatchingDemo {

    public static String describe(PaymentOutcome outcome) {
        return switch (outcome) {
            case null -> "Không có kết quả thanh toán";

            case Approved approved
                    when approved.transactionId() != null
                         && !approved.transactionId().isBlank() ->
                    "Thành công: " + approved.transactionId();

            case Approved approved ->
                    "Đã thành công nhưng mã giao dịch chưa hợp lệ";

            case Rejected rejected
                    when rejected.reason() != null
                         && !rejected.reason().isBlank() ->
                    "Thất bại: " + rejected.reason();

            case Rejected rejected ->
                    "Thất bại: không có lý do cụ thể";
        };
    }

    public static void main(String[] args) {
        PaymentOutcome[] samples = {
            new Approved("TX-1001"),
            new Approved(null),
            new Rejected("Không đủ số dư"),
            new Rejected(""),
            null
        };

        for (PaymentOutcome sample : samples) {
            System.out.println(describe(sample));
        }
    }
}
```

Biên dịch và chạy với một JDK hỗ trợ đầy đủ tính năng này (Java 21 trở lên):

```bash
javac PatternMatchingDemo.java
java PatternMatchingDemo
```

Kết quả:

```text
Thành công: TX-1001
Đã thành công nhưng mã giao dịch chưa hợp lệ
Thất bại: Không đủ số dư
Thất bại: không có lý do cụ thể
Không có kết quả thanh toán
```

### 12.1. Vì sao ví dụ exhaustive?

`PaymentOutcome` là sealed interface chỉ cho phép `Approved` và `Rejected`. Mỗi kiểu có một nhánh không guard:

```java
case Approved approved -> ...
case Rejected rejected -> ...
```

Các nhánh có guard đứng **trước** nhánh không guard cùng kiểu, nên không bị dominated. Mọi đối tượng `PaymentOutcome` khác null đều được bao phủ; null có `case null` riêng.

### 12.2. Thử đổi thứ tự để thấy lỗi dominance

Nếu đặt:

```java
case Approved approved -> ...
```

trước:

```java
case Approved approved when approved.transactionId() != null -> ...
```

thì nhánh guarded sẽ bị dominated. Compiler sẽ không cho phép thứ tự ấy.

### 12.3. Thử bỏ nhánh tổng quát để thấy lỗi exhaustiveness

Nếu chỉ giữ các guarded case cho `Approved` và `Rejected`, một kết quả có mã/ràng buộc không đạt guard sẽ không còn nhánh xử lý. Compiler không xem các guard tùy ý là bao phủ tất cả giá trị của kiểu.

### 12.4. Thử bỏ case null

Nếu xóa `case null`, hai nhánh kiểu không guard vẫn làm cho pattern switch exhaustive đối với giá trị không null, nhưng `describe(null)` sẽ ném `NullPointerException`.

Đây là ba bài kiểm tra độc lập giúp phân biệt **null handling**, **exhaustiveness** và **dominance**.

## 13. Kết hợp pattern matching với API nhận dữ liệu ngoài

Dữ liệu JSON, message queue, database hoặc các hệ thống khác có thể mang giá trị thiếu và trường hợp chưa được nhận diện. Dù một đối tượng trong Java có kiểu chính xác tại thời điểm biên dịch, dữ liệu đầu vào ở ranh giới hệ thống vẫn phải được kiểm tra.

Một quy trình thực tế:

1. **Parse và validate đầu vào**: phân biệt field thiếu, `null` được phép, sai kiểu, sai định dạng.
2. **Chuyển thành mô hình Java có hợp đồng rõ**: record hoặc sealed type phù hợp.
3. **Dùng pattern matching** trên mô hình đã được kiểm tra, không trộn mọi lỗi dữ liệu vào một default mơ hồ.
4. **Định nghĩa chính sách tương thích**: khi thêm biến thể ở API, quyết định phía tiêu thụ báo lỗi, bỏ qua, lưu giữ hay xử lý fallback.
5. **Ghi test** bao gồm cả null, biến thể mới và dữ liệu không đạt guard.

Ví dụ một bộ phân loại đơn giản:

```java
static String classifyInput(Object input) {
    return switch (input) {
        case null -> "missing";
        case String s when s.isBlank() -> "blank";
        case String s -> "text";
        case Number n -> "number";
        default -> "unsupported";
    };
}
```

Đây là bước phân loại tại ranh giới nhận dữ liệu động, không có nghĩa mọi tầng nội bộ nên dùng `Object`. Sau khi xác minh, nên chuyển sang kiểu domain cụ thể để compiler phát huy hiệu quả của hệ kiểu.

## 14. Trường hợp enum và sealed có bổ sung giá trị ở thời gian chạy

Exhaustiveness được quyết định ở lúc biên dịch với thông tin về kiểu đã biết. Trong hệ thống có nhiều phiên bản thư viện, mã client cũ có thể gặp enum constant hoặc subtype mới mà nó chưa biết.

Tình huống minh họa:

```text
Thời điểm T1:
  enum Status { NEW, DONE }
  client được biên dịch với switch có đủ NEW, DONE

Thời điểm T2:
  thư viện chứa thêm Status.FAILED
  client cũ không được biên dịch lại
```

Tùy thay đổi kiểu và ngữ cảnh chạy, khi một `switch` được xem là exhaustive ở lúc biên dịch nhưng không có case phù hợp ở lúc chạy, Java hiện đại có thể ném `MatchException`.

Điều này **khác** `NullPointerException`: NPE liên quan đến việc selector là null mà không có case null; `MatchException` có thể phát sinh khi assumptions về tính bao phủ tại runtime không còn đúng.

Hướng xử lý:

- Với ứng dụng kiểm soát được toàn bộ mã: biên dịch lại và cập nhật `switch` khi mở rộng miền kiểu.
- Với API nhiều phiên bản: định nghĩa chiến lược tương thích và kiểm thử tích hợp giữa các phiên bản.
- Không dùng `default` chỉ để che mọi lỗi phiên bản; dùng fallback khi chính hợp đồng yêu cầu xử lý biến thể chưa biết.

## 15. Các lỗi phổ biến và cách sửa

| Vấn đề | Nguyên nhân | Cách sửa |
|---|---|---|
| Tưởng `default` xử lý null | Null selector thường ném NPE nếu không có `case null` | Viết `case null` hoặc từ chối null trước khi switch |
| Tưởng `instanceof` ném NPE với null | `instanceof` trả false cho null | Tách nhánh null khi cần |
| Biến pattern ngoài scope | Kiểu chưa chắc khớp trên mọi đường đi | Dùng `&&`, cấu trúc `if` hoặc `switch` phù hợp |
| Thiếu nhánh của switch expression | Expression phải exhaustive | Thêm trường hợp còn thiếu hoặc fallback đúng hợp đồng |
| Chỉ viết guarded cases | Guard không tự bao phủ mọi giá trị của kiểu | Thêm nhánh unguarded phù hợp |
| `case CharSequence` trước `case String` | Nhánh tổng quát đứng trước nhánh cụ thể | Đảo thứ tự |
| `case Object` trước `case Integer` | Object đã nhận hết đối tượng không null | Đưa kiểu cụ thể lên trước |
| Unconditional pattern cùng `default` | Hai nhánh bao trùm xung đột | Chỉ giữ một nhánh bao quát |
| `case String` lặp không guard | Nhánh sau bị dominated | Gộp hoặc thêm guard có ý nghĩa trước nhánh chung |
| Tin rằng exhaustive đồng nghĩa null-safe | Tính đầy đủ kiểu không tự xử lý null | Tách chính sách null |
| Dùng default rộng với sealed/enum | Che chỗ cần bổ sung khi thêm biến thể | Liệt kê rõ các trường hợp nếu muốn compiler hỗ trợ |
| Dùng `when` trên dữ liệu con có thể null | Guard có thể ném NPE | Kiểm tra thành phần nullable trong guard |
| Nhầm dominance với unreachable statement | Hai loại kiểm tra khác nhau | Sửa thứ tự/cấu trúc case thay vì sửa luồng bất kỳ |
| Chỉ dựa vào exhaustiveness cho bảo đảm nghiệp vụ | Compiler không kiểm tra tính đúng đắn của kết quả | Thêm validation và unit/property tests |

## 16. Bài tập thực hành

### Bài 1: Phân biệt null và sai kiểu

Viết method `render(Object input)` theo các quy tắc:

- `null` trả `"(missing)"`.
- `String` rỗng hoặc toàn khoảng trắng trả `"(blank)"`.
- `String` khác trả chính chuỗi.
- `Number` trả `"number:"` kèm giá trị.
- Các kiểu khác trả `"(unsupported)"`.

Dùng `switch` expression với `case null`, guarded pattern và `default`.

### Bài 2: Sửa nhánh dominated

Giải thích lỗi và viết lại để mỗi loại dữ liệu có kết quả riêng:

```java
// Code không hợp lệ:
switch (value) {
    case Object o -> "object";
    case String s -> "string";
    case CharSequence cs -> "sequence";
    default -> "other";
}
```

Gợi ý: đặt `String` trước `CharSequence`, rồi quyết định cần `Object` **hay** `default`, không giữ cả hai trong trường hợp một nhánh là unconditional pattern.

### Bài 3: Switch exhaustive với enum

Định nghĩa enum `DeliveryState` gồm `CREATED`, `IN_TRANSIT`, `DELIVERED`. Viết `switch` expression trả nhãn tiếng Việt, không dùng `default`. Sau đó thêm `RETURNED` và quan sát điều gì xảy ra khi biên dịch lại mà không cập nhật nhánh.

### Bài 4: Sealed result

Tạo sealed interface `FetchResult` gồm ba record `Found(String value)`, `Missing(String key)`, `Failed(String reason)`. Viết method `message(FetchResult result)` xử lý đủ ba kiểu và `null`, không dùng default. Với `Found`, xử lý trường hợp `value` có thể null bằng guard và nhánh không guard.

### Bài 5: Nhánh guard có bao phủ hết không?

Cho kiểu `String`, hãy phân tích ba nhánh:

```java
case String s when s.length() > 10 -> "long";
case String s when s.length() <= 10 -> "short";
```

Compiler có thể chứng minh hai guard đó luôn bao phủ toàn bộ String hay không? Hãy thêm một nhánh để đảm bảo tính đầy đủ mà không làm nhánh trước bị dominated.

### Bài 6: Thiết kế hợp đồng null

Với API nhận `PaymentOutcome`, đề xuất hai phiên bản:

1. Một API không bao giờ chấp nhận null và mô tả lỗi khi nhận null.
2. Một API cho phép null, xem đó là "chưa có kết quả".

Viết một `switch` phù hợp với mỗi hợp đồng và giải thích vì sao thêm `case null` không phải lúc nào cũng là thay đổi tốt.

### Bài 7: Phân biệt dữ liệu đầu vào và miền kiểu

Viết method nhận `Object`, phân loại `String`, `Number` và các giá trị khác bằng pattern switch. Sau đó mô hình hóa miền nghiệp vụ bằng sealed interface với những record cụ thể để bỏ `default` rộng. So sánh lợi ích về kiểm tra exhaustiveness.

## 17. Tóm tắt

**Null handling** trả lời điều gì xảy ra khi selector hoặc biểu thức được xét là `null`. `instanceof` pattern trả `false` với null; `switch` trên tham chiếu thường ném `NullPointerException` nếu không có `case null`. `default` không tự thay cho `case null`.

**Exhaustiveness** bảo đảm `switch` expression và pattern switch statement có đủ trường hợp xử lý theo quy tắc compiler. Enum và sealed hierarchy thường cho phép liệt kê toàn bộ biến thể mà không cần default, giúp phát hiện thiếu nhánh khi thay đổi mô hình. Việc một switch exhaustive không chứng minh guard hoặc logic nghiệp vụ đúng và không đồng nghĩa đã xử lý null.

**Dominance** xảy ra khi nhánh `case` trước bao phủ toàn bộ giá trị mà nhánh sau có thể nhận. Thứ tự từ kiểu cụ thể đến kiểu tổng quát và đặt guarded case trước unguarded case cùng kiểu giúp tránh nhiều lỗi phổ biến. Compiler kiểm tra dominance theo quy tắc ngôn ngữ; nó không phải bộ giải mọi điều kiện nghiệp vụ.

Khi viết pattern matching trong Java hiện đại, hãy định nghĩa rõ chính sách null, khai thác exhaustiveness của miền kiểu đóng, sắp xếp nhánh có chủ đích và kiểm thử cả trường hợp biên lẫn tương thích phiên bản.

## Tài liệu tham khảo

- [JEP 441 — Pattern Matching for switch (chính thức từ Java 21)](https://openjdk.org/jeps/441)
- [JEP 440 — Record Patterns (chính thức từ Java 21)](https://openjdk.org/jeps/440)
- [JEP 394 — Pattern Matching for instanceof (chính thức từ Java 16)](https://openjdk.org/jeps/394)
- [JEP 409 — Sealed Classes (chính thức từ Java 17)](https://openjdk.org/jeps/409)
- [Java Language Specification — §14.11 The switch Statement](https://docs.oracle.com/javase/specs/jls/se25/html/jls-14.html#jls-14.11)
- [Java Language Specification — §15.28 The switch Expression](https://docs.oracle.com/javase/specs/jls/se25/html/jls-15.html#jls-15.28)
