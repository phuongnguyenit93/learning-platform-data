# Case null và xử lý null rõ ràng trong switch Java 21

**Phạm vi:** phần *Case label* của Java Core Pattern Matching. Bài sử dụng Java SE 21, khi *pattern matching for switch* đã ổn định theo JEP 441. Trọng tâm là cách viết và hiểu nhãn `case null`, phân biệt với `default`, quyết định chính sách xử lý giá trị thiếu, và bảo đảm mã rõ ràng khi phối hợp với pattern, guard và các loại `switch`.

## 1. Vấn đề: selector có thể mang giá trị null

Trong một `switch`, **selector expression** là biểu thức nằm giữa dấu ngoặc của `switch (...)`. Java đánh giá biểu thức này để xác định nhánh `case` phù hợp.

```java
static String classify(Object input) {
    return switch (input) {
        case String text -> "string: " + text;
        case Integer number -> "integer: " + number;
        default -> "other";
    };
}
```

Đây là `switch` expression hợp lệ trong Java 21. Với `"Java"`, kết quả là `"string: Java"`; với `12`, kết quả là `"integer: 12"`; với `true`, kết quả là `"other"`. Nhưng **`classify(null)` ném `NullPointerException`** dù có `default`.

Nguyên nhân: trong `switch` Java 21, **`default` đơn lẻ chỉ là nhánh dự phòng cho các giá trị khác null** mà không nhãn nào khác áp dụng; `null` cần nhãn `case null` nếu muốn được xử lý.

Sửa đúng:

```java
static String classify(Object input) {
    return switch (input) {
        case null -> "missing";
        case String text -> "string: " + text;
        case Integer number -> "integer: " + number;
        default -> "other";
    };
}
```

Giờ đây, `classify(null)` trả về `"missing"`. Không cần kiểm tra `if (input == null)` ở ngoài chỉ để tránh NPE trước `switch`.

**Ý nghĩa quan trọng:** `case null` là **một dạng switch label trong ngôn ngữ**, có cú pháp và hành vi được JLS quy định. Đây không phải một type pattern, cũng không phải một phép so sánh `== null` được Java tự thêm vào mọi nhánh `default`.

## 2. Cú pháp case label theo JLS

Ở Java SE 21, các dạng nhãn liên quan tới bài gồm:

```text
case CONSTANT_1 [, CONSTANT_2 ...]
case null
case null, default
case PATTERN [when GUARD]
default
```

Đây là **biểu diễn rút gọn để học**, không phải toàn bộ ngữ pháp formal trong JLS `14.11.1.

Ví dụ đối chiếu các thành phần:

```java
static String describe(Object value) {
    return switch (value) {
        case null -> "null selector";            // null label
        case String s when s.isBlank() -> "blank"; // pattern + guard
        case String s -> "string";                // type pattern
        case Integer n when n >= 1 && n <= 3 -> "small integer"; // type pattern + guard
        default -> "other";                      // default label
    };
}
```

Trong ví dụ với selector kiểu `Object`, nhánh `case Integer n when n >= 1 && n <= 3` dùng type pattern kèm guard để nhận các giá trị `Integer` từ 1 tới 3. Các nhãn hằng `case 1, 2, 3` chỉ hợp lệ trong `switch` có kiểu selector tương thích (ví dụ `int` hoặc `Integer`), không hợp lệ trực tiếp với selector có kiểu tĩnh `Object`. `case null` là nhãn đặc biệt dành cho null selector, **không khai báo biến**. `case String s` là type pattern và khai báo biến `s` khi khớp. `when` là guard bổ sung điều kiện cho **pattern**, không phải phần mở rộng chung của mọi nhãn.

### Khi selector bằng null, nhãn nào được chọn?

Theo JLS `14.11.1.2:

1. Đánh giá biểu thức selector. Nếu nó kết thúc bằng ngoại lệ, toàn bộ `switch` cũng kết thúc theo ngoại lệ đó.
2. Nếu giá trị selector là `null`, một nhãn `case null` (bao gồm trường hợp gộp `case null, default`) được áp dụng nếu tồn tại.
3. Nếu giá trị selector khác `null`, Java xác định nhãn hằng số hoặc pattern áp dụng theo quy tắc của ngôn ngữ; guard được kiểm tra khi pattern đã khớp.
4. `default` được dùng khi các nhãn khác không áp dụng cho một giá trị khác null.

Vì vậy, vị trí `case null` trong nhóm nhãn không biến nó thành nhánh “chỉ chạy sau mọi pattern”. Nếu selector là null, cơ chế áp dụng nhãn null diễn ra riêng.

## 3. Ba lựa chọn khác nhau cho null và nhánh còn lại

### 3.1. Case null riêng: phân biệt dữ liệu thiếu với dữ liệu sai kiểu

```java
static String label(Object input) {
    return switch (input) {
        case null -> "missing value";
        case String text -> "text: " + text;
        default -> "unsupported value";
    };
}
```

Kết quả:

| Input | Nhãn | Kết quả |
| --- | --- | --- |
| `null` | `case null` | `missing value` |
| `"Hi"` | `case String text` | `text: Hi` |
| `42` | `default` | `unsupported value` |

Đây là cách rõ ràng nhất khi nghiệp vụ muốn phân biệt **không có dữ liệu** và **có dữ liệu nhưng không đúng dạng**.

### 3.2. Default riêng: null là trường hợp bị từ chối

```java
static String strictLabel(Object input) {
    return switch (input) {
        case String text -> "text";
        default -> "other";
    };
}
```

`strictLabel(null)` ném `NullPointerException`. Không cần có nhãn `case null` nếu hợp đồng phương thức quy định selector không được null và muốn lỗi được phát hiện.

Nếu cần thông điệp cụ thể hơn, vẫn có thể khai báo nhãn null để chủ động từ chối:

```java
static String strictLabelWithMessage(Object input) {
    return switch (input) {
        case null -> throw new IllegalArgumentException("input must not be null");
        case String text -> "text";
        default -> "other";
    };
}
```

Như vậy, **có `case null` không đồng nghĩa phải chấp nhận `null`**. Nó có thể xử lý hợp lệ, trả giá trị mặc định, hoặc ném ngoại lệ rõ ràng tùy hợp đồng.

### 3.3. Case null, default: cùng một xử lý cho null và kiểu khác

Java 21 có dạng đặc biệt:

```java
static String compact(Object input) {
    return switch (input) {
        case String text -> "text";
        case null, default -> "not-text";
    };
}
```

Kết quả:

- `compact("Java")` trả `"text"`.
- `compact(null)` trả `"not-text"`.
- `compact(10)` trả `"not-text"`.

Dùng `case null, default` khi chính sách nghiệp vụ **thật sự coi null và mọi giá trị còn lại như nhau**. Nếu cần log riêng hoặc mã lỗi riêng cho null, hãy tách hai nhãn.

**Đây là một ngoại lệ cú pháp cụ thể:** Java 21 cho phép `case null, default` nhưng không cho viết `case null, String text` hoặc `case String text, default` như cách gộp tùy ý các pattern.

### Bảng so sánh

| Nhãn | Selector null | Giá trị khác null | Biến pattern |
| --- | --- | --- | --- |
| `case null` | Có | Không | Không |
| `default` | Không | Giá trị còn lại sau các nhãn khác | Không |
| `case null, default` | Có | Giá trị còn lại sau các nhãn khác | Không |
| `case String s` | Không | Chỉ giá trị khớp kiểu `String` | Có: `s` |
| `case Object value` | Không | Mọi đối tượng phù hợp với `Object` | Có: `value` |

## 4. Case null và pattern không hoán đổi cho nhau

Một type pattern như `String text` hoặc `Object any` kiểm tra **một đối tượng khác null** có phù hợp với kiểu tương ứng hay không. Vì vậy:

```java
static String nonNull(Object input) {
    return switch (input) {
        case Object any -> "object";
    };
}
```

Đây là `switch` expression exhaustive cho selector có kiểu `Object`, nhưng:

- `nonNull("Java")` trả `"object"`.
- `nonNull(7)` trả `"object"`.
- `nonNull(null)` ném `NullPointerException`.

Ngay cả pattern *unconditional* như `Object any` cũng **không** tự bắt null selector. Muốn xử lý null, thêm `case null`:

```java
static String withNull(Object input) {
    return switch (input) {
        case null -> "missing";
        case Object any -> "object";
    };
}
```

Hai nhánh này đã phân biệt đủ selector null và mọi đối tượng khác null; không cần `default`.

### Case null không phải một pattern có guard

Code sau **không biên dịch**:

```java
// KHÔNG BIÊN DỊCH:
// return switch (input) {
//     case null when true -> "missing";
//     default -> "other";
// };
```

Trong Java 21, `when` gắn với **case pattern**. Nó không áp dụng lên `case null` hoặc các nhãn chỉ chứa hằng số.

Thay vào đó, đặt logic cần thiết trong thân nhánh null:

```java
static String nullDecision(Object input, boolean optional) {
    return switch (input) {
        case null -> optional ? "optional missing" : "required missing";
        case String text -> text;
        default -> "unsupported";
    };
}
```

Chương trình chỉ thực hiện quyết định bổ sung nếu selector null đi vào đúng nhánh null.

## 5. Exhaustiveness và null: hai kiểm tra khác nhau

**Exhaustiveness** nghĩa là tập nhãn `switch` đáp ứng các quy tắc bao phủ của trình biên dịch. Theo Java 21:

- Một **`switch` expression** phải exhaustive.
- Một **enhanced `switch` statement** (ví dụ có pattern/null label hoặc selector kiểu tham chiếu khác những kiểu switch truyền thống) cũng phải exhaustive.
- `default` là một cách đạt exhaustiveness, hoặc dùng những pattern đã bao phủ tất cả giá trị liên quan theo kiểu selector, chẳng hạn mẫu kiểu tổng quát.
- **Exhaustive không bảo đảm selector null không gây NPE.**

Ví dụ:

```java
static int length(String text) {
    return switch (text) {
        case String s -> s.length();
    };
}
```

Đoạn trên hợp lệ trong Java 21: type pattern `String s` bao phủ mọi giá trị **khác null** của selector kiểu `String`. Nhưng `length(null)` vẫn ném `NullPointerException` vì không có null label.

Muốn chính sách null trả độ dài 0:

```java
static int safeLength(String text) {
    return switch (text) {
        case null -> 0;
        case String s -> s.length();
    };
}
```

`safeLength(null)` trả `0`; `safeLength("abc")` trả `3`.

**Chú ý:** nếu `switch` expression trên `Object` chỉ có `case null` và `case String s`, đó là mã **không exhaustive**, vì còn `Integer` và các kiểu khác. Bổ sung `default` hoặc một tập pattern bao phủ mọi giá trị khác null.

### Enhanced switch statement cũng phải bao phủ đủ

```java
// KHÔNG BIÊN DỊCH: enhanced switch statement không exhaustive.
// static void incomplete(Object input) {
//     switch (input) {
//         case null -> System.out.println("missing");
//         case String s -> System.out.println(s);
//     }
// }
```

Sửa bằng một nhánh `default` phù hợp:

```java
static void complete(Object input) {
    switch (input) {
        case null -> System.out.println("missing");
        case String s -> System.out.println(s);
        default -> System.out.println("another type");
    }
}
```

Khi một nhánh mới được thêm để xử lý null, vẫn cần kiểm tra **đầy đủ các trường hợp khác** theo quy tắc Java 21.

## 6. Dùng case null với String, wrapper và enum

### String selector

```java
static String classifyText(String text) {
    return switch (text) {
        case null -> "missing";
        case "" -> "empty";
        case "OK" -> "accepted";
        default -> "other text";
    };
}
```

Phân biệt:

- `null`: không có đối tượng `String`.
- `""`: có đối tượng `String` nhưng chuỗi rỗng.
- `"  "`: chuỗi chứa khoảng trắng, không bằng chuỗi rỗng; muốn xem là blank thì dùng logic `isBlank()` với pattern guard.

### Wrapper number selector

```java
static String classifyNumber(Integer number) {
    return switch (number) {
        case null -> "missing";
        case 0 -> "zero";
        default -> "number";
    };
}
```

`Integer` có thể null và cho phép `case null`. Ngược lại, `int` nguyên thủy **không thể** mang null:

```java
// KHÔNG BIÊN DỊCH:
// static String wrong(int number) {
//     return switch (number) {
//         case null -> "missing"; // Selector int là kiểu nguyên thủy.
//         default -> "number";
//     };
// }
```

Đừng tự unbox một `Integer` trước khi xử lý null: phép chuyển từ `Integer` null sang `int` có thể ném NPE trước khi `switch` chọn được nhãn.

### Enum selector

```java
enum State { OPEN, CLOSED }

static String stateLabel(State state) {
    return switch (state) {
        case null -> "unknown";
        case OPEN -> "open";
        case CLOSED -> "closed";
    };
}
```

Không bắt buộc viết `default`: tập hằng số enum đã được liệt kê đầy đủ để thỏa mãn kiểm tra exhaustiveness, và `case null` được xử lý riêng. Nếu sau này enum có hằng số mới, cần đánh giá lại các nhánh; với kiểu enum phát triển theo phiên bản thư viện, cũng cân nhắc tính tương thích runtime.

## 7. Null selector và null ở bên trong record pattern là hai chuyện khác nhau

Xét record:

```java
record Ticket(String id) {}
```

Hai giá trị sau rất khác nhau:

```java
Ticket missing = null;          // Chính selector có thể là null.
Ticket noId = new Ticket(null); // Selector là một Ticket, component id là null.
```

Với Java 21, có thể xử lý rõ ràng:

```java
static String ticketLabel(Object input) {
    return switch (input) {
        case null -> "ticket missing";
        case Ticket(String id) when id == null -> "ticket without id";
        case Ticket(String id) -> "ticket " + id;
        default -> "not a ticket";
    };
}
```

Kết quả:

- `ticketLabel(null)` → `"ticket missing"`.
- `ticketLabel(new Ticket(null))` → `"ticket without id"`.
- `ticketLabel(new Ticket("T7"))` → `"ticket T7"`.
- `ticketLabel("T7")` → `"not a ticket"`.

**Vì sao record pattern với component null vẫn có thể khớp?** Ở đây, type pattern `String id` trong record pattern là unconditional đối với kiểu component `String`. Theo quy tắc record pattern Java 21, nó có thể nhận giá trị component `null`. Đối tượng record ở ngoài vẫn phải khác null. Với một kiểu component và pattern khác, null-matching có thể khác; không được kết luận tất cả pattern lồng nhau luôn khớp null.

Guard `when id == null` được đánh giá **sau** khi record pattern `Ticket(String id)` đã khớp và biến `id` có giá trị (có thể là null trong trường hợp này). Phép so sánh `== null` không dereference biến, nên an toàn.

## 8. Thứ tự nhãn, dominance và lỗi biên dịch

### Nhãn null là duy nhất

Một `switch` block không được có hai nhãn `case null`. Không dùng đồng thời `case null` riêng và `case null, default`: như vậy lặp lại null label.

```java
// KHÔNG BIÊN DỊCH:
// return switch (value) {
//     case null -> "first";
//     case null -> "second"; // Trùng null label.
//     default -> "other";
// };
```

### Không viết case null, String s

```java
// KHÔNG BIÊN DỊCH:
// return switch (value) {
//     case null, String s -> "missing-or-text";
//     default -> "other";
// };
```

Nếu hai trường hợp dùng chung kết quả, có thể tách nhãn và trả cùng chuỗi; hoặc viết helper chung và gọi từ mỗi nhánh:

```java
static String sameMessage(Object value) {
    return switch (value) {
        case null -> "unknown";
        case String s -> "unknown";
        default -> "other";
    };
}
```

### Tránh để default trước case null hoặc case pattern

Theo JLS Java 21, `default` đứng trước nhãn `case null` hoặc nhãn chứa pattern là **lỗi biên dịch**. Với code mới, hãy đặt `default` cuối khối để dễ đọc và nhất quán.

`case null, default` là một nhãn tổng hợp: **không được có bất kỳ switch label nào sau nó**. Cú pháp này thuộc về nhánh cuối của khối.

```java
// KHÔNG BIÊN DỊCH:
// return switch (value) {
//     case null, default -> "remaining";
//     case String s -> "string"; // Nhãn sau case null, default.
// };
```

### Tránh pattern quá rộng che phủ nhánh còn lại

```java
// KHÔNG BIÊN DỊCH:
// return switch (value) {
//     case Object obj -> "object";
//     default -> "other"; // Object obj đã bao phủ mọi giá trị khác null.
// };
```

Một pattern không có guard và unconditional với kiểu selector có thể dominate `default`. Nếu cần xử lý null cùng pattern tổng quát, viết `case null` và `case Object obj` thay vì thêm default không cần thiết.

### Guard không thay thế nhánh null

```java
static String textCategory(Object value) {
    return switch (value) {
        case null -> "missing";
        case String s when s.isBlank() -> "blank";
        case String s -> "nonblank";
        default -> "not a String";
    };
}
```

Đặt điều kiện đặc thù với guard trước pattern `String s` tổng quát, vì đặt pattern `String s` không guard lên trước sẽ che khuất nhánh guard đứng sau.

## 9. Switch expression và switch statement có null label

### Switch expression trả về một giá trị

```java
static String normalize(String input) {
    return switch (input) {
        case null -> "(missing)";
        case String s when s.isBlank() -> "(blank)";
        case String s -> s.trim();
    };
}
```

`switch` expression có thể dùng `case null -> "..."` ngay như một giá trị. Nếu cần nhiều lệnh trong nhánh, dùng khối với `yield`:

```java
static String normalizeVerbose(String input) {
    return switch (input) {
        case null -> {
            String fallback = "(missing)";
            yield fallback;
        }
        case String s -> s.trim();
    };
}
```

`yield` trả giá trị từ nhánh của **switch expression**. Không dùng `break` có giá trị để thay `yield`.

### Switch statement thực thi hành động

```java
static void printValue(String input) {
    switch (input) {
        case null -> System.out.println("missing");
        case String s when s.isBlank() -> System.out.println("blank");
        default -> System.out.println(input);
    }
}
```

Với switch statement dùng các nhánh mũi tên `->`, mỗi nhánh chỉ chạy hành động của nó, tránh *fall-through* ngoài ý muốn.

### Tránh fall-through làm biến pattern chưa khởi tạo

Với nhãn dấu hai chấm `:`, ngôn ngữ có cơ chế *fall-through*, nhưng không được làm luồng điều khiển rơi vào nhóm lệnh dùng pattern variable chưa chắc được khởi tạo:

```java
// KHÔNG BIÊN DỊCH:
// switch (input) {
//     case null:
//     case String s:
//         System.out.println(s); // Có đường vào từ case null không gắn s.
//         break;
//     default:
//         break;
// }
```

Với nhãn null và nhãn pattern, lựa chọn dễ đọc nhất trong đa số tình huống là dùng `->` riêng cho mỗi nhánh, rồi gọi chung một helper nếu thật sự trùng xử lý.

## 10. Ví dụ Java 21 hoàn chỉnh

Tạo file **`CaseNullLabelsDemo.java`**:

```java
public class CaseNullLabelsDemo {
    record Ticket(String id) {}

    enum State { OPEN, CLOSED }

    static String render(Object input) {
        return switch (input) {
            case null -> "missing";

            case String text when text.isBlank() -> "blank";
            case String text -> "text:" + text;

            case Ticket(String id) when id == null -> "ticket-without-id";
            case Ticket(String id) -> "ticket:" + id;

            default -> "unsupported:" + input.getClass().getSimpleName();
        };
    }

    static String compact(Object input) {
        return switch (input) {
            case String text -> "text";
            case null, default -> "not-text";
        };
    }

    static String statusLabel(State state) {
        return switch (state) {
            case null -> "unknown";
            case OPEN -> "open";
            case CLOSED -> "closed";
        };
    }

    static String strict(Object input) {
        return switch (input) {
            case String text -> "string";
            default -> "other";
        };
    }

    static void show(String value) {
        switch (value) {
            case null -> System.out.println("printed:missing");
            case String text when text.isBlank() ->
                    System.out.println("printed:blank");
            default -> System.out.println("printed:" + value);
        }
    }

    public static void main(String[] args) {
        Object[] values = {
                null, " ", "Java", new Ticket(null), new Ticket("T7"), 42
        };

        for (Object value : values) {
            System.out.println(render(value));
        }

        System.out.println(compact(null));
        System.out.println(compact(99));
        System.out.println(statusLabel(null));
        System.out.println(statusLabel(State.OPEN));
        show(null);

        try {
            System.out.println(strict(null));
        } catch (NullPointerException exception) {
            System.out.println("strict:NPE");
        }
    }
}
```

**Biên dịch và chạy với JDK 21 trở lên, không cần bật preview:**

```bash
javac --release 21 -encoding UTF-8 CaseNullLabelsDemo.java
java CaseNullLabelsDemo
```

**Kết quả chính xác:**

```text
missing
blank
text:Java
ticket-without-id
ticket:T7
unsupported:Integer
not-text
not-text
unknown
open
printed:missing
strict:NPE
```

**Diễn giải:**

1. `null` vào `case null` và được thông báo là thiếu dữ liệu.
2. Chuỗi một khoảng trắng khớp `String text` và guard `isBlank()`; `"Java"` đi vào nhánh String còn lại.
3. `new Ticket(null)` không phải null selector; record pattern khớp, guard phát hiện component null. `new Ticket("T7")` vào nhánh record tiếp theo.
4. `42` được boxing thành `Integer` và rơi vào `default`, nơi `input.getClass()` an toàn vì null selector đã được chặn.
5. `compact(null)` và `compact(99)` cùng trả `"not-text"` qua `case null, default`.
6. `statusLabel(null)` xử lý null cho enum; `statusLabel(State.OPEN)` dùng nhãn enum.
7. `show(null)` minh họa xử lý null trên switch statement, in `printed:missing`.
8. `strict(null)` không có null label nên ném NPE và được bắt ở `main`.

## 11. Chính sách rõ ràng cho ứng dụng thực tế

Việc có dùng `case null` phải xuất phát từ **hợp đồng dữ liệu**. Ba hướng thiết kế thường gặp:

| Chính sách | Cách viết | Khi phù hợp |
| --- | --- | --- |
| Null là đầu vào hợp lệ | `case null -> defaultValue` | Giá trị tuỳ chọn, dữ liệu chưa được cung cấp |
| Null phải được phân biệt và báo lỗi | `case null -> throw new IllegalArgumentException(...)` | API yêu cầu giá trị có nghĩa, muốn lỗi rõ ràng |
| Null là vi phạm hợp đồng không cần nhánh riêng | `Objects.requireNonNull(input)` trước `switch` hoặc để NPE xuất hiện | Đầu vào thuộc vùng nội bộ có hợp đồng non-null rõ |
| Null và kiểu khác được xử lý giống nhau | `case null, default -> fallback` | Mục tiêu thực sự là nhóm “không dùng được” chung |

**Khi trả fallback:** chọn giá trị không tạo ra hiểu lầm với dữ liệu hợp lệ. Ví dụ, với chiều dài chuỗi, trả `0` cho `null` có thể khiến “thiếu dữ liệu” và “chuỗi rỗng” không còn phân biệt; nếu ứng dụng cần phân biệt, trả một trạng thái riêng hoặc ném ngoại lệ phù hợp.

**Khi logging:** tránh dùng `value.getClass()` trong nhánh null. Chỉ gọi `getClass()` ở nhánh đã xác định đầu vào khác null.

**Khi làm việc với Optional:** `Optional<T>` và `case null` giải quyết hai tầng hợp đồng khác nhau. `Optional.empty()` là một đối tượng `Optional` khác null; không tự đi vào `case null`. Hãy chọn một biểu diễn vắng mặt nhất quán trong API.

**Khi xử lý dữ liệu bên ngoài:** kiểm thử cả selector null, kiểu hợp lệ, kiểu bất ngờ và trường hợp record có component null. Việc “đã có default” chưa phải bằng chứng đã xử lý null.

## 12. Các bài tập tự kiểm tra

**Bài tập 1 — default có bắt null không?** Đoán hành vi:

```java
Object value = null;
String result = switch (value) {
    case Integer number -> "number";
    default -> "other";
};
```

**Đáp án:** ném `NullPointerException`; không trả `"other"`. Để trả `"missing"`, thêm `case null -> "missing";`.

**Bài tập 2 — pattern bao trùm.** Hãy dự đoán:

```java
static String test(Object value) {
    return switch (value) {
        case Object any -> "object";
    };
}
```

**Đáp án:** với `"abc"` trả `"object"`; với `null` ném NPE. Trình biên dịch coi `switch` expression này exhaustive cho kiểu `Object`, nhưng không biến pattern thành null-matching.

**Bài tập 3 — gộp case null, default.** Đổi hàm `compact` thành hai nhánh sao cho null trả `"missing"`, còn kiểu không phải String trả `"unknown"`.

**Đáp án:**

```java
static String split(Object input) {
    return switch (input) {
        case null -> "missing";
        case String s -> "text";
        default -> "unknown";
    };
}
```

**Bài tập 4 — có thể gắn guard lên null không?** Cú pháp `case null when flag -> ...` có đúng không?

**Đáp án:** Không hợp lệ trong Java 21. `when` chỉ gắn với case pattern. Viết điều kiện bên trong thân `case null` hoặc xử lý logic trước `switch`.

**Bài tập 5 — record với null component.** Vì sao `new Ticket(null)` vào nhánh `Ticket(String id)`, không vào `case null`?

**Đáp án:** selector là một đối tượng `Ticket` khác null. Trường `id` có giá trị null và được xử lý bởi pattern component có quy tắc matching tương ứng; `case null` chỉ dành cho chính giá trị selector null.

**Bài tập 6 — enum và exhaustive.** Với `enum State { OPEN, CLOSED }`, nếu `switch` expression có đủ hai nhánh `OPEN` và `CLOSED` nhưng không có `case null`, chuyện gì xảy ra khi selector là null?

**Đáp án:** biểu thức có thể exhaustive về các giá trị enum nhưng vẫn ném NPE cho null. Thêm `case null` khi nghiệp vụ cần xử lý nó.

## Tài liệu tham khảo chính thức

- [JLS Java SE 21 `14.11.1 — Switch Blocks](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.11.1): các dạng case label, guard, null label, kiểm tra dominance và quy tắc ngữ pháp.
- [JLS Java SE 21 `14.11.1.1 — Exhaustive Switch Blocks](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.11.1.1): tính exhaustive đối với nhãn trong switch.
- [JLS Java SE 21 `14.11.1.2 — Determining Which Switch Label Applies](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.11.1.2): cách xác định nhãn với selector null và giá trị khác null.
- [JLS Java SE 21 `14.11.3 — Execution of a switch Statement](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.11.3): runtime behavior khi không có nhãn cho null.
- [JLS Java SE 21 `14.30 — Patterns](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.30): type/record pattern và các quy tắc khớp.
- [OpenJDK JEP 441 — Pattern Matching for switch](https://openjdk.org/jeps/441): tính năng ổn định trong Java 21.
