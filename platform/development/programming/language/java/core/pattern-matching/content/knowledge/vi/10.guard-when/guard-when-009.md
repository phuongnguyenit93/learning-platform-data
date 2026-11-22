# Khi nào dùng `when` thay vì `if` lồng trong Java Pattern Matching?

Trong Java 21+, `when` là **guard** gắn với một **pattern case label** của `switch`. Nó bổ sung điều kiện boolean **sau khi pattern khớp** và quyết định liệu nhánh `case` ấy có được chọn hay không. Ngược lại, `if` lồng trong thân `case` kiểm tra điều kiện **sau khi nhánh đã được chọn**.

Đây là khác biệt quan trọng nhất:

- Dùng **`when`** khi điều kiện cần tham gia **quyết định chọn nhánh nào** của `switch`: nếu guard sai, Java có thể thử một `case` khác, rồi tới `default` nếu cần.
- Dùng **`if` lồng** khi kiểu/pattern đã xác định nhánh và bạn muốn **thực hiện các bước xử lý bên trong nhánh đó**: kiểm tra nghiệp vụ phụ, tính toán, log, lựa chọn kết quả, hoặc nhiều hành động.
- Dùng **`if` thông thường, không cần `switch`** khi bạn chỉ cần một phép thử kiểu và một điều kiện, ví dụ `if (value instanceof String text && !text.isBlank())`.

Không nên chọn `when` chỉ vì cú pháp ngắn hơn. Hãy chọn theo ý nghĩa **định tuyến nhánh** hay **xử lý sau khi định tuyến**.

> **Phiên bản:** `when` trong pattern matching cho `switch` được chuẩn hóa từ **Java 21**. Java 17 hỗ trợ pattern matching cho `instanceof` nhưng chưa hỗ trợ cú pháp `case String s when ...` như một tính năng chính thức.

## 1. Đặt `when` và `if` lồng cạnh nhau

Xét đầu vào `Object value`, với hai quy tắc:

1. Nếu là chuỗi bắt đầu bằng chữ `A`, trả về `"starts-with-A"`.
2. Nếu là chuỗi khác, trả về `"other-string"`; nếu không phải chuỗi, trả về `"not-string"`.

**Dùng `when` — điều kiện là một phần của việc chọn `case`:**

```java
static String usingWhen(Object value) {
    return switch (value) {
        case String text when text.startsWith("A") -> "starts-with-A";
        case String text -> "other-string";
        default -> "not-string";
    };
}
```

Java xét `String text`, sau đó mới xét `text.startsWith("A")`. Nếu giá trị là `"Java"`, type pattern vẫn khớp nhưng guard sai; Java tiếp tục tới `case String text` phía sau và trả về `"other-string"`.

**Dùng `if` lồng — nhánh `String` đã được chọn trước:**

```java
static String usingNestedIf(Object value) {
    return switch (value) {
        case String text -> {
            if (text.startsWith("A")) {
                yield "starts-with-A";
            }
            yield "other-string";
        }
        default -> "not-string";
    };
}
```

Hai cách ở trên có thể cho **cùng kết quả**, nhưng chúng tổ chức logic khác nhau:

- `when` biểu diễn **hai trường hợp phân loại chuỗi** như hai nhánh `case`.
- `if` biểu diễn **một nhánh dành cho chuỗi**, trong đó thực hiện quyết định phụ để chọn giá trị cuối cùng.
- Trong `switch expression`, block `case ... -> { ... }` phải dùng `yield` để cung cấp kết quả bình thường; không dùng `return` thay `yield` cho một `switch expression` trả về từ phương thức theo cách này.

Sự tương đương về **kết quả** chỉ đúng vì nhánh `if` lồng tự xử lý đầy đủ cả trường hợp đúng lẫn sai. Nếu không có `else` hoặc `yield` dự phòng, hành vi khác ngay.

## 2. Cơ chế chính xác của guarded pattern

Cú pháp Java 21+:

```java
switch (selector) {
    case SomeType variable when booleanExpression -> action;
    case SomeType variable -> fallbackForSameType;
    default -> generalFallback;
}
```

Trong một nhãn `case SomeType variable when booleanExpression`:

1. Java đánh giá **selector expression** của `switch` để có giá trị cần chọn nhánh.
2. Java thử **type pattern** `SomeType variable`. Nếu không khớp, guard **không được đánh giá**.
3. Nếu pattern khớp, **pattern variable** được binding và có thể dùng ngay trong guard.
4. Java đánh giá **biểu thức boolean** sau `when`. Nếu kết quả `true`, nhánh đó được chọn và thực thi.
5. Nếu guard trả về `false`, nhánh ấy không được chọn; quá trình tìm nhánh thích hợp tiếp tục. Giá trị có thể khớp pattern khác, một pattern rộng hơn hoặc rơi vào `default`.
6. Nếu guard **ném exception**, exception lan ra theo quy tắc thông thường; Java không tự coi exception là `false` và không tự vào `default`.

```text
Đánh giá selector một lần
            |
            v
   Thử pattern của case
       /            \
  không khớp        khớp -> binding variable
      |                         |
      v                         v
  xét case khác         đánh giá guard when
                        /       |       \
                     true     false    exception
                       |        |          |
                  chọn case  xét case     lan ra
                              khác
```

Ví dụ:

```java
case String text when !text.isBlank() && text.length() >= 5 -> "long text";
```

Guard là biểu thức boolean; có thể dùng `&&`, `||`, lời gọi phương thức và các phép so sánh hợp lệ. Nhờ pattern `String text` đã khớp, `text` có kiểu tĩnh `String` và ở trong scope của guard. Với selector `null` hoặc `Integer`, guard ở nhánh `String` không chạy.

**Điểm cần tránh:** không có cơ chế “chạy `default` trong thân `case` nếu `if` trả về `false`”. `default` chỉ được xét trong quá trình **chọn case**, không phải cơ chế `else` cho một `if` đã nằm trong nhánh được chọn.

## 3. Ví dụ Java 21+ chạy được: nhiều nhóm điều kiện với `when`

Lưu nội dung sau thành tệp **`GuardWhenDemo.java`**:

```java
public class GuardWhenDemo {
    static String classify(Object value) {
        return switch (value) {
            case null -> "missing";

            case String text when text.isBlank() -> "blank";
            case String text when text.length() >= 5 ->
                    "long:" + text.toUpperCase();
            case String text -> "short:" + text;

            case Integer number when number < 0 ->
                    "negative:" + number;
            case Integer number -> "number:" + number;

            default -> "unsupported";
        };
    }

    public static void main(String[] args) {
        System.out.println(classify(null));
        System.out.println(classify("   "));
        System.out.println(classify("Java"));
        System.out.println(classify("Spring"));
        System.out.println(classify(-2));
        System.out.println(classify(7));
        System.out.println(classify(2.5));
    }
}
```

Biên dịch và chạy với JDK 21 trở lên:

```bash
javac GuardWhenDemo.java
java GuardWhenDemo
```

Kết quả chính xác:

```text
missing
blank
short:Java
long:SPRING
negative:-2
number:7
unsupported
```

Phân tích:

| Input | Pattern/guard | Nhánh cuối cùng |
| --- | --- | --- |
| `null` | `case null` | `"missing"` |
| `"   "` | `String` khớp, `isBlank()` đúng | `"blank"` |
| `"Java"` | `String` khớp; `isBlank()` sai, độ dài 4 không đủ 5 | `case String text` không guard, `"short:Java"` |
| `"Spring"` | `String` khớp; `isBlank()` sai, độ dài 6 đạt 5 | `"long:SPRING"` |
| `-2` | `Integer` khớp, `number < 0` đúng | `"negative:-2"` |
| `7` | `Integer` khớp, guard âm sai | `case Integer number` không guard, `"number:7"` |
| `2.5` | Không thuộc `String` hay `Integer` | `default`, `"unsupported"` |

**Vì sao `when` phù hợp ở đây?** Các dòng `case` chính là **bảng quy tắc phân loại đầu vào**. Đọc từ trên xuống thấy ngay: chuỗi trống, chuỗi dài, chuỗi còn lại, số nguyên âm, số nguyên còn lại, kiểu không hỗ trợ. Nếu tất cả logic đặt trong một `case String` với nhiều `if`, phần lựa chọn các trường hợp chuỗi khó quan sát như các nhánh độc lập.

Đồng thời, việc có `case String text` và `case Integer number` không guard ở phía sau giúp xử lý trọn hai kiểu này, kể cả khi không guard nào đúng.

## 4. Cùng kết quả nhưng cách tổ chức khác nhau: ví dụ đầy đủ

Lưu **`BranchChoiceDemo.java`**:

```java
public class BranchChoiceDemo {
    static String usingWhen(Object value) {
        return switch (value) {
            case String text when text.startsWith("A") -> "starts-with-A";
            case String text -> "other-string";
            default -> "not-string";
        };
    }

    static String usingNestedIf(Object value) {
        return switch (value) {
            case String text -> {
                if (text.startsWith("A")) {
                    yield "starts-with-A";
                }
                yield "other-string";
            }
            default -> "not-string";
        };
    }

    public static void main(String[] args) {
        System.out.println(usingWhen("Apple"));
        System.out.println(usingNestedIf("Apple"));
        System.out.println(usingWhen("Java"));
        System.out.println(usingNestedIf("Java"));
        System.out.println(usingWhen(42));
        System.out.println(usingNestedIf(42));
    }
}
```

```bash
javac BranchChoiceDemo.java
java BranchChoiceDemo
```

```text
starts-with-A
starts-with-A
other-string
other-string
not-string
not-string
```

### Khi `when` đọc rõ hơn

Nếu quy tắc thực chất là “một chuỗi bắt đầu bằng `A` là một loại đầu vào riêng”, biểu diễn nó trực tiếp ở nhãn `case` làm code mang ý nghĩa *pattern + điều kiện chọn nhánh*:

```java
case String text when text.startsWith("A") -> "starts-with-A";
case String text -> "other-string";
```

Ta có thể bổ sung nhiều điều kiện cùng kiểu theo thứ tự ưu tiên (miễn không tạo nhánh bị thống trị), hoặc dành nhánh `default` cho dữ liệu chưa được hỗ trợ.

### Khi `if` lồng đọc rõ hơn

Nếu sau khi biết đầu vào là `String`, chương trình cần làm một chuỗi hành động riêng cho `String`, kiểm tra điều kiện chỉ để điều chỉnh kết quả phụ, thì đặt logic trong **một block** thường tự nhiên hơn:

```java
case String text -> {
    String normalized = text.strip();
    if (normalized.isEmpty()) {
        yield "empty";
    }
    yield normalized.toUpperCase();
}
```

Đây là **một nhánh xử lý kiểu `String`** với quy trình chuẩn hóa và quyết định nội bộ. Không cần biến mỗi thao tác nhỏ thành một guarded case.

*Đoạn trên là một phần của `switch expression` Java 21+, không phải lớp Java độc lập.*

## 5. Bẫy quan trọng: `if` lồng không chuyển sang `default`

Hai đoạn sau **không tương đương**.

**Phương án A: `if` nằm trong một `case String` đã được chọn:**

```java
switch (value) {
    case String text -> {
        if (text.length() > 4) {
            System.out.println("inside: long");
        }
    }
    default -> System.out.println("inside: fallback");
}
```

Nếu `value = "Go"`, case `String` đã được chọn vì giá trị là một chuỗi. `text.length() > 4` là `false` nên không in gì. Sau khi nhánh kết thúc, **Java không đi tiếp vào `default`**. Đó là hành vi bình thường: `if` lồng chỉ điều khiển lệnh bên trong nhánh.

**Phương án B: `when` là điều kiện để case áp dụng:**

```java
switch (value) {
    case String text when text.length() > 4 ->
            System.out.println("guard: long");
    default -> System.out.println("guard: fallback");
}
```

Nếu `value = "Go"`, pattern `String` khớp nhưng guard `length() > 4` sai, nên case này **không được chọn**. Không còn case nào khác, vì thế `default` được chọn và in `guard: fallback`.

### Chạy để chứng minh

Lưu **`NestedIfPitfallDemo.java`**:

```java
public class NestedIfPitfallDemo {
    static void nested(Object value) {
        switch (value) {
            case String text -> {
                if (text.length() > 4) {
                    System.out.println("inside: long");
                }
            }
            default -> System.out.println("inside: fallback");
        }
    }

    static void guarded(Object value) {
        switch (value) {
            case String text when text.length() > 4 ->
                    System.out.println("guard: long");
            default -> System.out.println("guard: fallback");
        }
    }

    public static void main(String[] args) {
        nested("Go");
        guarded("Go");
        nested(42);
        guarded(42);
    }
}
```

```bash
javac NestedIfPitfallDemo.java
java NestedIfPitfallDemo
```

Đầu ra:

```text
guard: fallback
inside: fallback
guard: fallback
```

**Không có dòng nào từ `nested("Go")`.** Chương trình in tổng cộng ba dòng vì lời gọi đầu tiên chọn nhánh `String` nhưng điều kiện `if` lồng sai. Đây chính là tình huống nên dùng `when` nếu bạn thực sự cần **nhánh dự phòng ở cấp `switch`** xử lý chuỗi ngắn.

Đừng suy luận rằng một `if` trong case có thể thay đổi lựa chọn case sau khi `switch` đã chọn nhánh.

## 6. Những trường hợp nên chọn `when`

### 6.1. Quy tắc phân loại phụ thuộc cả kiểu và điều kiện bổ sung

```java
return switch (value) {
    case Integer score when score >= 90 -> "excellent";
    case Integer score when score >= 60 -> "passed";
    case Integer score -> "failed";
    default -> "not a score";
};
```

*Đây là đoạn switch expression minh họa Java 21+.*

Các nhánh thể hiện rõ **thứ tự ưu tiên**. Điểm 95 thỏa cả `>= 90` và `>= 60`, nhưng nhánh `>= 90` đứng trước được chọn. Điểm 75 bỏ qua nhánh đầu và chọn nhánh thứ hai. Điểm 40 vào nhánh `Integer` còn lại. Mẫu này phù hợp với **các nhóm trạng thái tách biệt**, chẳng hạn phân hạng hoặc định tuyến chiến lược xử lý.

### 6.2. Cần tiếp tục thử nhánh sau nếu một điều kiện không đạt

```java
return switch (value) {
    case String text when text.startsWith("admin:") -> "admin";
    case String text when text.startsWith("user:") -> "user";
    case String text -> "unrecognized string";
    default -> "unsupported";
};
```

Điểm mạnh của `when` là **guard false cho phép thử case khác**. Dùng `if` lồng mà không có `else` phù hợp sẽ làm mất lựa chọn nhánh dự phòng ở cấp `switch`.

### 6.3. Muốn thể hiện guard ngay bên cạnh pattern để dễ đọc

```java
case String command when !command.isBlank() -> handle(command);
```

Đoạn trên thể hiện rằng một giá trị chỉ thuộc case nếu **vừa là `String`, vừa không trống**. Người đọc không cần mở một block dài để tìm điều kiện định tuyến. Đây là cách tốt khi điều kiện ngắn, thuần khiết (*pure*) và mô tả rõ bản chất của case.

### 6.4. Record pattern cần kiểm tra thêm điều kiện nghiệp vụ

Ví dụ minh họa Java 21+:

```java
record Purchase(String category, int amount) {}

static String route(Object value) {
    return switch (value) {
        case Purchase(String category, int amount) when amount >= 100 ->
                "priority: " + category;
        case Purchase(var category, var amount) ->
                "standard: " + category;
        case null -> "missing";
        default -> "unsupported";
    };
}
```

Record pattern giúp thử cấu trúc và binding các thành phần; `when amount >= 100` bổ sung điều kiện ưu tiên. Nếu số tiền dưới 100, pattern ưu tiên không áp dụng và nhánh `Purchase` thông thường có thể nhận giao dịch đó.

**Lưu ý:** `String category` là type pattern của một thành phần; nếu thành phần `category` là `null`, nó không khớp nhánh ưu tiên ấy. Ngược lại, `var category` ở record component pattern có thể binding thành phần `null`. Vì vậy không nên quy mọi khác biệt giữa hai nhánh chỉ cho điều kiện `amount >= 100` nếu dữ liệu record có thể chứa null. Đây là **đoạn mã minh họa trong một lớp Java 21+**, không phải tệp độc lập.

## 7. Những trường hợp nên giữ `if` lồng hoặc chỉ dùng `if`

### 7.1. Chỉ có một phép thử kiểu và một điều kiện

```java
if (value instanceof String text && !text.isBlank()) {
    System.out.println(text.strip());
}
```

Nếu không có nhiều trường hợp để phân nhánh, `switch` kèm `when` thường tăng độ phức tạp không cần thiết. Cú pháp `instanceof` với pattern variable và `&&` đã phù hợp, đồng thời hoạt động trong Java 17+.

### 7.2. Đã chọn nhánh thì muốn hoàn thành công việc ngay trong nhánh đó

```java
switch (value) {
    case String text -> {
        System.out.println("Received a string");
        if (text.isBlank()) {
            System.out.println("Warning: blank input");
        }
        System.out.println("String handling finished");
    }
    case Integer number -> System.out.println("Number: " + number);
    case null -> System.out.println("Missing");
    default -> System.out.println("Unsupported");
}
```

Ở đây `if` chỉ điều khiển việc in lời cảnh báo. **Dù chuỗi có trống hay không, nhánh `String` vẫn cần thực hiện bước kết thúc**. Dùng `when` chỉ để in cảnh báo có thể buộc lặp lại phần xử lý chung hoặc làm logic khó theo dõi.

### 7.3. Logic dài, có nhiều bước, hoặc cần kiểm tra trong nội bộ

```java
case String text -> {
    String normalized = text.strip();
    if (normalized.length() > 100) {
        normalized = normalized.substring(0, 100);
    }
    yield normalized;
}
```

Nếu nhiều lệnh cùng phục vụ một trường hợp sau khi đã xác định kiểu, block với `if` có thể dễ đọc hơn một loạt nhánh `case` lặp lại. Với `switch expression`, cần `yield` khi hoàn thành bình thường từ block.

### 7.4. Không muốn dùng Java 21 hoặc phải hỗ trợ Java 17

Java 17 hỗ trợ:

```java
static String classify(Object value) {
    if (value instanceof String text) {
        if (text.isBlank()) {
            return "blank";
        }
        return "text:" + text;
    }
    return "other";
}
```

Đây là một phương thức hợp lệ trong một lớp Java 17, không cần preview feature. Java 17 không có cú pháp `case String text when ...` chính thức. Khi thư viện hoặc dự án bị khóa phiên bản `--release 17`, `if` lồng hoặc `if/else if` là lựa chọn phù hợp hơn.

### 7.5. Logic là hành động phụ, không phải điều kiện chọn case

Các thao tác như logging, cập nhật chỉ số, chuẩn hóa dữ liệu, gọi dịch vụ hoặc kiểm tra phụ thuộc nhiều bước thường nên đặt trong thân nhánh hoặc một phương thức riêng. Guard giúp mô tả **điều kiện chọn case**, không phải một nơi để thực hiện cả quy trình nghiệp vụ.

## 8. Flow scoping: `when` chỉ được dùng biến sau khi pattern khớp

Ví dụ:

```java
case String text when text.length() >= 5 -> text.toUpperCase();
```

`text` là pattern variable, không phải một biến có sẵn trước `switch`. Java cho phép dùng `text` trong guard vì **type pattern `String text` đã khớp**; nó cũng hợp lệ trong biểu thức bên phải `->` khi case được chọn.

Điều kiện trong `when` phải có kiểu **`boolean`**. Một lời gọi trả về `int` không phải guard hợp lệ:

```java
// Sai: text.length() là int, không phải boolean.
// case String text when text.length() -> "long";
```

Cách đúng:

```java
case String text when text.length() > 4 -> "long";
```

`when` không phải từ nối dùng thay mọi `if`. Bạn không viết:

```java
// Sai: when không phải cú pháp cho if thông thường.
// if (value instanceof String text) when text.length() > 4 { ... }
```

Cũng không gắn `when` vào nhãn không có pattern như `case null` hoặc `default`:

```java
// Sai: guard chỉ dành cho case có pattern.
// case null when someCondition -> ...;
// default when someCondition -> ...;
```

Nếu cần kiểm tra logic phụ cho `null`, hãy dùng `case null -> { if (...) ... }` hoặc xử lý trước `switch`.

## 9. Thứ tự case và lỗi dominance

Khi các pattern có thể cùng khớp một kiểu, **thứ tự nhãn rất quan trọng**. Một type pattern không guard có thể bao phủ toàn bộ giá trị cùng kiểu. Vì vậy thứ tự sau là **đúng**:

```java
switch (value) {
    case String text when text.length() >= 5 ->
            System.out.println("long");
    case String text ->
            System.out.println("other string");
    default ->
            System.out.println("not a string");
}
```

Nhưng thứ tự sau bị compiler từ chối:

```java
// KHÔNG BIÊN DỊCH:
// switch (value) {
//     case String text -> System.out.println("any string");
//     case String text when text.length() >= 5 ->
//             System.out.println("long");
//     default -> System.out.println("other");
// }
```

Vì `case String text` không guard đã áp dụng cho mọi `String`, guarded case `String` phía sau **bị thống trị** (*dominated*) và không thể được chọn. Đây là lỗi biên dịch; Java không cố lách bằng cách nhìn vào nội dung điều kiện.

Quy tắc thực hành: **đặt guarded patterns cụ thể trước pattern tổng quát không guard**, và kết thúc với nhánh dự phòng hợp lệ khi cần. Đối với pattern khác kiểu hoặc kế thừa, Java cũng có dominance rules; đừng giả định mọi hoán đổi thứ tự đều hợp lệ.

Một guard cũng không phải bộ kiểm tra sau khi case đã được chọn: nó thực sự ảnh hưởng đến *khả năng case áp dụng*, vì thế compiler cần xét sự bao phủ và thống trị.

## 10. Exhaustiveness: guard không mặc nhiên bao phủ toàn bộ kiểu

Trong `switch expression`, compiler cần chứng minh các giá trị thông thường có nhánh xử lý (*exhaustive*). Một guard có thể `false`, vì thế chỉ viết một guarded case thường **không đủ**:

```java
// KHÔNG BIÊN DỊCH: switch expression chưa exhaustive.
// static String bad(Object value) {
//     return switch (value) {
//         case String text when text.length() >= 5 -> text;
//     };
// }
```

Có thể sửa bằng một case khác dành cho `String` và `default` cho kiểu khác:

```java
static String good(Object value) {
    return switch (value) {
        case String text when text.length() >= 5 -> "long";
        case String text -> "short";
        default -> "other";
    };
}
```

*Đây là một phương thức minh họa Java 21+.* Lưu ý `good(null)` vẫn **ném `NullPointerException`**, bởi vì chưa có `case null`. `default` không tự bắt null selector trong Java 21. Nếu null là đầu vào hợp lệ, thêm:

```java
case null -> "missing";
```

ở vị trí phù hợp trong khối `switch`.

Đối với **enhanced switch statement** có pattern, cũng cần xem quy tắc exhaustive. Đừng suy ra từ `switch statement` truyền thống chỉ dùng hằng rằng mọi `switch` có pattern đều được phép thiếu nhánh bao phủ còn lại.

## 11. Guard cần rõ ràng, an toàn và không gây tác dụng phụ bất ngờ

`when` có thể gọi phương thức thông thường:

```java
case String text when isEligible(text) -> process(text);
```

*Đoạn này giả định `isEligible` trả về `boolean` và `process` đã được định nghĩa.*

Tuy nhiên:

- Guard chỉ chạy **nếu pattern tương ứng khớp**. Đừng đặt trong guard một tác vụ mà chương trình phải thực hiện cho *mọi* loại input.
- Nếu guard trả về `false`, Java tiếp tục xét case khác. Nếu guard **ném exception**, exception lan ra; `default` không phải khối `catch`.
- Side effect như ghi database, gửi HTTP request, cập nhật trạng thái hay thay đổi biến chia sẻ trong guard khiến thứ tự chọn case khó hiểu. Nên ưu tiên điều kiện đơn giản, ổn định, ít hoặc không có side effect.
- Với điều kiện phức tạp, cân nhắc tách thành phương thức predicate có tên biểu thị ý nghĩa, ví dụ `isEligible(text)`, hoặc thực hiện xác thực cần thiết **trước** `switch`.
- Khi nhiều guard trên cùng kiểu có thể cùng đúng, nhánh phù hợp trước được chọn. Thứ tự đặt rule là một phần của logic; không nên sắp xếp lại vì lý do thẩm mỹ mà không kiểm thử.
- `when` không bảo đảm nhanh hơn `if` lồng. Hiệu năng thực tế phụ thuộc mã nguồn, cấu trúc nhánh, JIT và chi phí của predicate. Nên chọn theo ngữ nghĩa và khả năng bảo trì trước.

Đặc biệt, nếu phần lớn xử lý là logic nội bộ của một case và guard chỉ đóng vai trò “bật/tắt một hành động”, `if` lồng có thể làm ý đồ rõ hơn và tránh nhiều điều kiện bị lặp.

## 12. So sánh nhanh khi review code

| Câu hỏi | Ưu tiên `when` | Ưu tiên `if` lồng |
| --- | --- | --- |
| Điều kiện có quyết định case nào được chọn không? | Có | Không, case đã được chọn |
| Nếu điều kiện sai, có muốn thử case khác/default? | Có | Không tự động |
| Có nhiều rule cùng kiểu cần tách thành nhánh rõ ràng? | Thường có | Không bắt buộc |
| Có nhiều bước xử lý chung sau khi nhận ra một kiểu? | Dễ lặp code | Thường hợp lý |
| Chỉ có một phép thử `instanceof`? | Có thể quá mức | Dùng `if`/`&&` trực tiếp |
| Cần chạy Java 17 không preview? | Không phù hợp | Phù hợp |
| Guard chứa nhiều side effect? | Nên tránh | Đặt logic vào thân nhánh/phương thức riêng |
| Cần `yield` trong block của `switch expression`? | Không nếu dùng expression arm | Có khi block cần trả giá trị |
| Một rule sai có được xem là loại input “khác” không? | Dễ biểu đạt bằng case tiếp theo | Phải viết nhánh `else` rõ ràng |

Không có quy tắc rằng “`when` luôn tốt hơn `if` lồng”. Một biểu thức `switch` có ba case đơn giản thường đọc tốt với guard, nhưng một case có workflow dài thường đọc tốt hơn khi chỉ dùng một case và tổ chức nội bộ bằng `if`.

## 13. Sai lầm thường gặp và cách sửa

**Sai lầm 1 — Nghĩ `if` lồng sai sẽ nhảy xuống `default`.**

```java
case String text -> {
    if (text.isBlank()) {
        System.out.println("blank");
    }
}
default -> System.out.println("fallback");
```

Nếu `text` không blank, nhánh `String` đã được chọn rồi; `default` không chạy. Muốn nhánh dự phòng của `switch` nhận chuỗi không blank, hãy dùng `case String text when text.isBlank() -> ...; default -> ...;` hoặc thêm nhánh xử lý sau điều kiện.

**Sai lầm 2 — Đặt case rộng trước case có guard.**

```java
// Sai: guarded String phía sau bị dominated.
// case String text -> "any";
// case String text when text.isBlank() -> "blank";
```

Đổi thứ tự: guarded case trước, unguarded case sau.

**Sai lầm 3 — Nghĩ `when` là phép kiểm tra null.**

```java
// Không bắt được selector null:
// case String text when text == null -> "null";
```

Type pattern `String text` không match null, nên guard không bao giờ chạy cho null selector. Dùng `case null` riêng.

**Sai lầm 4 — Nghĩ `when` hoạt động trên `case null` hoặc `default`.**

```java
// Không hợp lệ:
// case null when true -> "null";
// default when true -> "other";
```

Guard chỉ gắn với pattern case label, không gắn với các nhãn trên.

**Sai lầm 5 — Viết `switch expression` với block nhưng quên `yield`.**

```java
case String text -> {
    String result = text.trim();
    yield result;
}
```

*Đây là block minh họa của một `switch expression`.* Không thể viết block tính `result` rồi rơi ra cuối mà không cho kết quả bình thường của expression.

**Sai lầm 6 — Nghĩ exception trong guard đồng nghĩa guard false.**

```java
case String text when text.charAt(0) == 'A' -> "A";
```

Với chuỗi rỗng, `text.charAt(0)` ném `StringIndexOutOfBoundsException`, không chuyển sang default. Dùng:

```java
case String text when !text.isEmpty() && text.charAt(0) == 'A' -> "A";
```

Vế phải của `&&` chỉ chạy khi `text` không rỗng.

**Sai lầm 7 — Dùng `when` để làm các bước xử lý có tác dụng phụ.**

Nên tách việc **xác định case** (predicate) khỏi **thực thi nghiệp vụ** trong thân case, để dễ kiểm thử và không phụ thuộc thứ tự đánh giá nhiều guard.

## 14. Hướng dẫn quyết định thực tế

Khi đứng trước lựa chọn `when` hay `if` lồng, hãy hỏi tuần tự:

1. **Cần phân loại input thành những trường hợp nào?** Nếu mỗi nhánh là một loại có ý nghĩa riêng, dùng `switch` với pattern có thể phù hợp.
2. **Điều kiện có quyết định case được chọn hay chỉ quyết định một bước xử lý bên trong case?** Loại thứ nhất nghiêng về `when`; loại thứ hai nghiêng về `if`.
3. **Nếu điều kiện sai, phải chuyển sang rule tiếp theo không?** Nếu có, `when` diễn đạt trực tiếp. Nếu không, một `case` với `if` nội bộ thường đủ.
4. **Các trường hợp có chồng lấp không?** Xếp guard cụ thể trước case tổng quát; tránh dominance và kiểm thử thứ tự.
5. **Nhánh dự phòng có rõ không?** Có case cùng kiểu không guard hoặc `default` khi cần? Có `case null` nếu null hợp lệ?
6. **Mục tiêu Java là gì?** Chỉ dùng `when` của `switch` trên Java 21+; với Java 17 dùng `instanceof` kết hợp `if`/`&&`.
7. **Guard có an toàn không?** Kiểm tra điều kiện boolean, trường hợp chuỗi rỗng, exception, chi phí thực thi và side effect.
8. **Viết test cho cả guard đúng và sai.** Kiểm tra nhánh tiếp theo, `default`, input khác kiểu và null; không chỉ thử happy path.

### Kết luận

**Dùng `when` khi bạn muốn điều kiện bổ sung trở thành một phần của việc *chọn case*: pattern khớp nhưng guard sai thì nhánh đó không được chọn và Java tiếp tục tìm nhánh khác.** Dùng **`if` lồng** khi case đã được chọn và điều kiện chỉ phân chia công việc **bên trong case**; `if` không tự làm Java quay lại chọn case khác.

Giữ ý nghĩa này rõ ràng giúp tránh hai lỗi lớn nhất: nghĩ rằng `if` lồng sẽ kích hoạt `default`, và đặt guarded case phía sau một case cùng kiểu đã bao phủ hết dữ liệu.

### Tài liệu tham khảo

- [Oracle Java 21 — Pattern Matching for switch Expressions and Statements](https://docs.oracle.com/en/java/javase/21/language/pattern-matching-switch.html): `when` guard, dominance, exhaustive switch và xử lý null.
- [Oracle Java 21 — Switch Expressions](https://docs.oracle.com/en/java/javase/21/language/switch-expressions.html): cú pháp nhánh `->`, block và `yield`.
- [Java Language Specification 21 — Switch Statements `14.11](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.11): quy tắc chọn nhãn, pattern guards và switch.
