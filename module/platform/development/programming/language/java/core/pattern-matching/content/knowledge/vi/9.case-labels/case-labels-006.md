# Kết hợp nhiều case label trong Java 21

Trong Java, một `switch` có thể cho **nhiều giá trị đầu vào đi tới cùng một cách xử lý**. Với cú pháp hiện đại, cách ngắn nhất là viết nhiều hằng số trong cùng một nhãn `case`, phân tách bằng dấu phẩy:

```java
static String status(int code) {
    return switch (code) {
        case 200, 201, 204 -> "success";
        case 400, 404 -> "client error";
        default -> "other";
    };
}
```

Khi `code` là `200`, `201` hoặc `204`, kết quả đều là `"success"`. Đây là **nhiều case constant trong một case label**, không phải ba nhánh chạy liên tiếp. Cách gộp này cũng có thể dùng với hằng số `String` hay hằng enum tương thích.

Tuy nhiên, trong **Java 21**, cú pháp gộp **pattern** không giống gộp hằng số: `case String s, Integer n ->` **không hợp lệ**. Với *pattern matching for switch*, cần hiểu rõ sự khác nhau giữa **nhãn có nhiều hằng**, **nhiều nhãn đứng chung một colon group**, và **nhãn pattern có biến ràng buộc**. Bài này giải thích các trường hợp hợp lệ, giới hạn compile-time, fall-through, scope và cách thiết kế lại khi nhiều pattern có chung hành vi.

## 1. Phân biệt case label, switch rule và colon group

Một `switch` Java 21 có thể sử dụng hai kiểu block:

- **Switch rule (`->`)**: một nhãn `case` dẫn đến biểu thức, block hoặc `throw`. Thực thi xong rule thì **không fall-through** xuống rule tiếp theo.
- **Switch labeled statement group (`:`)**: một hoặc nhiều nhãn `case` dẫn tới chung một nhóm câu lệnh. Trong `switch statement`, nếu nhóm chạy xong mà không thoát, điều khiển có thể **fall-through** xuống nhóm kế tiếp.

Ví dụ nhiều hằng số dùng arrow rule:

```java
switch (code) {
    case 200, 201, 204 -> System.out.println("success");
    case 400, 404 -> System.out.println("client error");
    default -> System.out.println("other");
}
```

Ví dụ nhiều nhãn theo kiểu colon cổ điển:

```java
switch (code) {
    case 200:
    case 201:
    case 204:
        System.out.println("success");
        break;
    case 400:
    case 404:
        System.out.println("client error");
        break;
    default:
        System.out.println("other");
}
```

Hai đoạn trên là **mã minh họa đặt trong một method có biến `int code`**. Chúng in cùng một dòng cho cùng đầu vào. Đoạn colon xếp nhiều nhãn trên cùng một nhóm câu lệnh; `break` ngăn việc chạy tiếp vào các nhóm phía sau. Dạng arrow không cần `break`.

Cú pháp rút gọn của colon group cũng hợp lệ:

```java
switch (code) {
    case 200, 201, 204:
        System.out.println("success");
        break;
    default:
        System.out.println("other");
}
```

Như vậy, **dấu phẩy không chỉ dành cho arrow rule**: cả hai kiểu switch block đều chấp nhận nhiều *case constant* trong một nhãn.

## 2. Nhóm các hằng số số nguyên, chuỗi và enum

### Hằng số nguyên

```java
static String priority(int level) {
    return switch (level) {
        case 1, 2 -> "low";
        case 3, 4 -> "medium";
        case 5 -> "high";
        default -> "unknown";
    };
}
```

`case 1, 2` chỉ định cùng hành vi cho hai giá trị. Trình biên dịch kiểm tra hằng số có phù hợp với kiểu selector hay không; không thể viết một biểu thức tính toán runtime tùy ý như `case someVariable, 2` nếu `someVariable` không phải hằng hợp lệ tại compile-time.

### Hằng số String

```java
static boolean isPositiveAnswer(String answer) {
    if (answer == null) {
        return false;
    }
    return switch (answer) {
        case "yes", "y", "ok" -> true;
        case "no", "n" -> false;
        default -> false;
    };
}
```

Ở đây các nhãn `String` được so khớp theo **giá trị chuỗi**, không phải theo các nhánh `if` tự viết. Hàm này **phân biệt chữ hoa/chữ thường**: `"YES"` không khớp `"yes"`. Việc kiểm tra `null` tường minh ngăn `switch` trên `String` ném `NullPointerException` trong ví dụ.

### Hằng số enum

```java
enum Day { MONDAY, TUESDAY, WEDNESDAY, THURSDAY, FRIDAY, SATURDAY, SUNDAY }

static String plan(Day day) {
    return switch (day) {
        case SATURDAY, SUNDAY -> "rest";
        case MONDAY, FRIDAY -> "focus";
        case TUESDAY, WEDNESDAY, THURSDAY -> "regular";
        case null -> "unknown";
    };
}
```

Khi selector là `Day`, các tên enum không cần tiền tố `Day.` trong nhãn `case` như trên. Ba nhóm hằng enum đã bao phủ toàn bộ bảy giá trị của enum; nhãn `case null` xử lý riêng tham chiếu rỗng. Do đó, đây là một `switch expression` exhaustive mà không cần `default`.

Các method và `enum` trong ba ví dụ có thể đặt trong cùng một class; chúng không phải những tệp độc lập như được trình bày. Chương trình hoàn chỉnh ở phần sau cho phép chạy thử trực tiếp.

## 3. Gộp nhãn khác với fall-through có chủ đích

Hai cách viết sau rất dễ bị nhầm:

```java
switch (value) {
    case 1:
    case 2:
        System.out.println("same action");
        break;
    default:
        break;
}
```

Đây là **hai nhãn cùng trỏ vào một nhóm xử lý**. Nếu `value=1`, câu lệnh phía sau `case 1:` là một nhãn nữa (`case 2:`), rồi đến `println`. Không có hành động nào riêng dành cho `case 1` cần phải chạy trước.

Khác với:

```java
switch (value) {
    case 1:
        System.out.println("first");
        // fall through intentionally
    case 2:
        System.out.println("second");
        break;
    default:
        break;
}
```

Với `value=1`, đoạn sau in **hai dòng** `first` và `second`. Với `value=2`, chỉ in `second`. Đây là **fall-through từ nhóm có câu lệnh sang nhóm khác**, không đơn thuần là gộp nhãn.

Đối với mục tiêu “nhiều giá trị, một hành vi”, **ưu tiên nhãn hằng phân tách bằng dấu phẩy** và arrow rule; không cần phụ thuộc vào fall-through.

## 4. Java 21 không cho gộp nhiều case pattern bằng dấu phẩy

Khi selector là `Object`, các nhãn sau có thể sử dụng *type pattern*:

```java
static String describe(Object value) {
    return switch (value) {
        case String text -> "string:" + text.strip();
        case Integer number -> "integer:" + number;
        case null -> "missing";
        default -> "other";
    };
}
```

Mỗi nhãn `case String text` hoặc `case Integer number` tạo một **pattern variable riêng**. Biến đó chỉ có hiệu lực khi pattern tương ứng khớp, kể cả trong guard `when` nếu có.

**Sai cú pháp Java 21:**

```java
// KHÔNG BIÊN DỊCH TRONG JAVA 21 (chỉ minh họa):
// return switch (value) {
//     case String text, Integer number -> "supported";
//     default -> "other";
// };
```

Trong Java 21, cấu trúc case label nhận một trong những dạng chính: **danh sách case constant**, **một case pattern (có thể kèm `when`)**, **`case null` (có thể đi cùng `default`)**, hoặc **`default`**. Nó **không** có cú pháp danh sách nhiều pattern tách bằng dấu phẩy. Không được dùng quy tắc `case 1, 2` để suy ra `case String s, Integer n`.

Ngoài khác biệt cú pháp, hai pattern variable `text` và `number` mang **kiểu và đường khớp khác nhau**. Một nhánh chia sẻ duy nhất sẽ không thể giả định cả hai biến đều đã được khởi tạo.

Cách hợp lệ khi cần chung kết quả:

```java
static String supported(Object value) {
    return switch (value) {
        case String ignored -> "supported";
        case Integer ignored -> "supported";
        case null, default -> "other";
    };
}
```

Hai rule khác nhau có thể trả cùng chuỗi. Tên `ignored` là biến pattern riêng ở **từng rule**, không có ý nghĩa chúng chia sẻ một biến qua các nhánh. Khi không cần truy cập biến, vẫn nên giữ code rõ ràng và tránh lặp lại logic dài bằng việc gọi method dùng chung.

## 5. Một ngoại lệ đáng biết: colon group với pattern KHÔNG khai báo biến

Java 21 **có** cho phép nhiều nhãn pattern thuộc **cùng một colon statement group** khi pattern **không khai báo pattern variable**. Ví dụ record pattern của các record rỗng:

```java
record Ping() {}
record Pong() {}

static String messageType(Object value) {
    switch (value) {
        case Ping():
        case Pong():
            return "signal";
        case null:
            return "missing";
        default:
            return "other";
    }
}
```

Đây là đoạn minh họa cần đặt `record` và method trong một class thích hợp. Cả `case Ping():` và `case Pong():` đều là **record pattern** và đều không khai báo biến. Vì không có pattern variable nào bị sử dụng khi chọn nhóm xử lý, việc hai nhãn trỏ về cùng câu `return "signal"` là hợp lệ trong Java 21.

Lưu ý quan trọng:

- Cú pháp hợp lệ ở đây là **hai nhãn colon riêng biệt**, **không phải** `case Ping(), Pong() -> ...`. Dạng comma-separated pattern vẫn không hợp lệ trong Java 21, kể cả khi pattern không khai báo biến.
- Không được tự suy rộng thành `case String s: case Integer i:` rồi dùng `s` hoặc `i` trong cùng nhóm. **Java cấm** nhóm có nhiều switch label khi một nhãn pattern gắn vào câu lệnh đó khai báo pattern variable.
- Nếu cần xử lý pattern có binding, cách dễ hiểu nhất thường là **các case rule độc lập** rồi gọi chung một method xử lý.

Chính sự khác nhau này cho thấy “kết hợp case label” không chỉ là chuyện dấu phẩy: phải xem **loại nhãn** và **cách tổ chức switch block**.

## 6. Tại sao colon group không được gộp pattern có binding?

Ví dụ **không biên dịch**:

```java
// KHÔNG BIÊN DỊCH TRONG JAVA 21:
static void bad(Object value) {
    switch (value) {
        case String text:
        case Integer number:
            System.out.println(number);
            break;
        default:
            break;
    }
}
```

Giả sử `value` là `"hello"`. Nếu trình biên dịch cho phép chọn nhóm từ `case String text`, thì câu lệnh `System.out.println(number)` sẽ cố đọc `number` mặc dù pattern `Integer number` **không khớp**. Java không cho phép tình huống một câu lệnh được gắn với nhiều switch label mà có nhãn pattern khai báo biến.

Một lỗi khác cũng bị ngăn:

```java
// KHÔNG BIÊN DỊCH:
static void badFallthrough(Object value) {
    switch (value) {
        case String text:
            System.out.println(text);
            // Thiếu break: có thể rơi xuống case Integer bên dưới
        case Integer number:
            System.out.println(number + 1);
            break;
        default:
            break;
    }
}
```

Nếu code từ nhánh `String` có thể hoàn thành bình thường rồi đi vào nhánh `Integer`, biến `number` chưa chắc đã được khởi tạo. Java 21 cấm **fall-through vào nhóm có case pattern khai báo biến** từ một nhóm trước đó có thể hoàn thành bình thường.

Điều này khác với một switch chỉ có nhãn hằng hoặc một số record pattern không khai báo biến. Không nên phát biểu chung rằng “switch có pattern thì mọi fall-through đều bị cấm”; giới hạn trọng tâm là **bảo đảm pattern variable được khởi tạo đúng cách**.

## 7. `case null, default`: một kiểu kết hợp đặc biệt

Trong Java 21, `case null, default` là cú pháp **hợp lệ** với selector kiểu tham chiếu:

```java
static String classify(Object value) {
    return switch (value) {
        case String s when !s.isBlank() -> "text";
        case Integer i -> "integer";
        case null, default -> "other";
    };
}
```

Nhánh cuối xử lý **cả `null` lẫn các giá trị không thuộc nhánh trước**. `case null, default` phải là nhãn cuối trong switch block, và không được thêm một nhãn khác phía sau nó. Đây là **tổ hợp đặc biệt** trong ngữ pháp Java 21, không phải quy tắc cho phép tự do gộp `null` với nhiều hằng hoặc pattern.

So sánh:

```java
// Hai nhãn riêng, cùng ý nghĩa với ví dụ trên cho các đường chưa khớp:
case null -> "other";
default -> "other";
```

Hai dòng này là **đoạn minh họa bên trong switch expression**, không phải code đứng độc lập.

Khi dùng `default` **không** đi kèm `case null`, không được mặc nhiên cho rằng `default` sẽ xử lý `null` trong pattern switch. Selector tham chiếu `null` thường cần `case null` rõ ràng, nếu không có thể gây `NullPointerException`.

Với một nhãn `case null, default`, tránh đặt các pattern tổng quát không guard như `case Object anything` phía trước nếu chúng làm nhãn còn lại bị thừa hoặc bị dominated. Thứ tự và tính bao phủ của các nhãn vẫn chịu quy tắc kiểm tra của Java.

## 8. Guard `when`: không biến danh sách pattern thành hợp lệ

Để phân loại cùng một kiểu theo điều kiện khác nhau, viết **nhiều nhánh pattern độc lập**:

```java
static String textKind(Object value) {
    return switch (value) {
        case String s when s.isBlank() -> "blank";
        case String s when s.length() >= 10 -> "long text";
        case String s -> "short text";
        case null, default -> "not text";
    };
}
```

Thứ tự ở đây có ý nghĩa: `String s` không guard được đặt **sau** các nhánh có guard, vì nhánh không guard có thể bao phủ toàn bộ `String` và khiến các nhánh sau trở thành **dominated case**.

Không thể viết `case String s when s.isBlank(), Integer i -> ...` như một dạng gộp. Guard `when` gắn với **một case pattern**. Nếu hai kiểu cần cùng kết quả, hãy tách nhánh và gọi chung một method.

Một cách khác là dùng **common supertype** khi có ý nghĩa mô hình dữ liệu:

```java
static String category(Object value) {
    return switch (value) {
        case Number n -> "number:" + n;
        case CharSequence s -> "characters:" + s.length();
        case null, default -> "other";
    };
}
```

`Number n` bao phủ `Integer`, `Long`, `Double` và các subtype phù hợp, còn `CharSequence s` bao phủ `String`, `StringBuilder` và nhiều kiểu chuỗi khác. Đây là cách **gộp theo quan hệ subtype** bằng một pattern, **không phải** cách gộp tùy ý nhiều kiểu không liên quan. Chỉ dùng khi ý nghĩa nghiệp vụ của kiểu chung đúng với hành vi cần xử lý.

## 9. Những ràng buộc khi gộp nhiều case constant

Trình biên dịch Java kiểm tra các nhãn trong **toàn bộ switch block**, không chỉ trong một dòng `case`.

### Không được có hằng trùng lặp

```java
// KHÔNG BIÊN DỊCH:
switch (code) {
    case 1, 2 -> System.out.println("first");
    case 2, 3 -> System.out.println("second"); // 2 bị lặp
    default -> {}
}
```

`2` xuất hiện trong cả hai nhãn nên dẫn đến lỗi compile-time. Tương tự, hai biểu thức hằng khác cách viết nhưng có **cùng giá trị** cũng có thể bị coi là trùng.

### Kiểu hằng phải phù hợp selector

```java
// KHÔNG BIÊN DỊCH với int code:
// switch (code) {
//     case "200", "201" -> System.out.println("ok");
//     default -> {}
// }
```

Những nhãn `String` không tương thích với selector `int`. Cần phân biệt giá trị `200` kiểu số nguyên và `"200"` kiểu chuỗi.

### Không gắn guard `when` trực tiếp với nhãn hằng

```java
// KHÔNG BIÊN DỊCH trong Java 21:
// case 1, 2 when enabled -> "ok";
```

`when` là phần của **case pattern**. Với hằng số, hãy xét điều kiện trong phần thân rule hoặc ở biểu thức điều khiển trước `switch`.

### Không trộn hai kiểu switch block

```java
// KHÔNG BIÊN DỊCH: cùng một switch block trộn arrow với colon.
// switch (code) {
//     case 1, 2 -> System.out.println("small");
//     case 3:
//         System.out.println("three");
// }
```

Một block phải dùng nhất quán **switch rules** hoặc **switch labeled statement groups**.

## 10. Switch statement và switch expression khi gộp nhãn

Đối với **switch statement**, thường sử dụng arrow để thực hiện hành động:

```java
static void logStatus(int code) {
    switch (code) {
        case 200, 201 -> System.out.println("ok");
        case 400, 404 -> System.out.println("client error");
        default -> System.out.println("other");
    }
}
```

Đối với **switch expression**, mỗi nhánh phải tạo được kết quả:

```java
static String codeLabel(int code) {
    return switch (code) {
        case 200, 201 -> "ok";
        case 400, 404 -> "client error";
        default -> "other";
    };
}
```

Với **colon group** trong switch expression, sử dụng `yield` để trả giá trị:

```java
static String codeLabelColon(int code) {
    return switch (code) {
        case 200:
        case 201:
            yield "ok";
        case 400:
        case 404:
            yield "client error";
        default:
            yield "other";
    };
}
```

Không dùng `break` thay `yield` trong switch expression; `break` chỉ dùng để thoát switch statement hoặc cấu trúc điều khiển liên quan. Với nhãn pattern có binding, dù trong statement hay expression, các ràng buộc scope và fall-through vẫn phải được tôn trọng.

Một **switch expression** cần exhaustive. Trong Java 21, **enhanced switch statement** sử dụng pattern hoặc `case null` cũng cần exhaustive. Với selector `Object`, `default` hoặc `case null, default` là cách thường dùng để bao phủ các đầu vào chưa có nhánh xử lý. Với enum, tất cả enum constant được bao phủ có thể đủ cho tính exhaustive; vẫn cần quyết định cách xử lý selector `null` riêng biệt nếu nó có thể xuất hiện.

## 11. Ví dụ Java 21 hoàn chỉnh

Tạo file **`MultipleCaseLabelsDemo.java`**:

```java
public class MultipleCaseLabelsDemo {
    enum Day {
        MONDAY, TUESDAY, WEDNESDAY, THURSDAY,
        FRIDAY, SATURDAY, SUNDAY
    }

    record Ping() {}
    record Pong() {}

    static String status(int code) {
        return switch (code) {
            case 200, 201, 204 -> "ok";
            case 400, 404 -> "client-error";
            default -> "other";
        };
    }

    static String dayType(Day day) {
        return switch (day) {
            case SATURDAY, SUNDAY -> "weekend";
            case MONDAY, FRIDAY -> "edge-weekday";
            case TUESDAY, WEDNESDAY, THURSDAY -> "weekday";
            case null -> "unknown";
        };
    }

    static String legacyGrouped(int code) {
        String result;
        switch (code) {
            case 200:
            case 201:
            case 204:
                result = "ok";
                break;
            case 400:
            case 404:
                result = "client-error";
                break;
            default:
                result = "other";
        }
        return result;
    }

    static String noBindings(Object value) {
        switch (value) {
            case Ping():
            case Pong():
                return "signal";
            case null:
                return "missing";
            default:
                return "other";
        }
    }

    static String typeAware(Object value) {
        return switch (value) {
            case String s when s.isBlank() -> "blank";
            case String s -> "string:" + s.strip();
            case Integer n -> "integer:" + n;
            case null, default -> "misc";
        };
    }

    public static void main(String[] args) {
        System.out.println(status(200));
        System.out.println(status(404));
        System.out.println(status(999));
        System.out.println(dayType(Day.SUNDAY));
        System.out.println(dayType(Day.WEDNESDAY));
        System.out.println(dayType(null));
        System.out.println(legacyGrouped(201));
        System.out.println(noBindings(new Ping()));
        System.out.println(noBindings(new Pong()));
        System.out.println(noBindings(null));
        System.out.println(typeAware("  Java  "));
        System.out.println(typeAware("  "));
        System.out.println(typeAware(7));
        System.out.println(typeAware(2.5));
        System.out.println(typeAware(null));
    }
}
```

Biên dịch và chạy trên **JDK 21** (không cần `--enable-preview`):

```bash
javac --release 21 MultipleCaseLabelsDemo.java
java MultipleCaseLabelsDemo
```

**Stdout chính xác:**

```text
ok
client-error
other
weekend
weekday
unknown
ok
signal
signal
missing
string:Java
blank
integer:7
misc
misc
```

Đối chiếu từng nhóm:

1. `status` gộp các mã trạng thái bằng danh sách hằng `200, 201, 204` và `400, 404`. Mã `999` vào `default`.
2. `dayType` gộp các hằng enum mà không cần viết `Day.` trước mỗi tên; `case null` xử lý đầu vào rỗng.
3. `legacyGrouped` cho cùng kết quả với arrow trong `status`, nhưng nhóm hằng qua nhiều nhãn colon và cần `break` để ngăn fall-through.
4. `noBindings` dùng hai **record pattern không khai báo biến** trong cùng một colon group. `Ping` và `Pong` đều ra `signal`.
5. `typeAware` đặt các nhánh pattern **tách biệt**, dùng `when` cho chuỗi trắng, rồi kết thúc bằng `case null, default`. Số `7` boxing thành `Integer`, còn `2.5` boxing thành `Double` và đi vào `misc`.

Khi học bằng cách sửa mã, hãy thử chuyển `case 200, 201, 204` thành các nhãn colon xếp chồng, rồi biên dịch lại. Sau đó thử một trong các ví dụ **cố ý không hợp lệ** ở các phần trước để quan sát lỗi về danh sách pattern hoặc trùng hằng; không chép ví dụ sai vào tệp chạy cuối.

## 12. Cách chọn cách gộp nhãn phù hợp

| Nhu cầu | Cách nên dùng trong Java 21 |
| --- | --- |
| Nhiều hằng số cùng một hành vi | `case A, B, C -> ...` |
| Duy trì switch cổ điển với nhiều hằng số | `case A: case B: ... break;` hoặc `case A, B:` |
| Hai kiểu tham chiếu khác nhau cần cùng kết quả | Hai rule pattern riêng, cùng trả kết quả hoặc gọi một method chung |
| Các subtype thực sự có ý nghĩa xử lý chung | Một pattern theo supertype phù hợp như `case Number n` |
| Nhiều record pattern không khai báo biến cùng hành vi | Có thể dùng nhiều nhãn pattern colon trong một group |
| Muốn bắt cả `null` và mọi trường hợp chưa khớp | `case null, default -> ...` ở cuối switch block |
| Phân biệt nhiều điều kiện trên cùng một kiểu | Các nhánh pattern có `when` đứng trước nhánh không guard |
| Muốn tạo giá trị trả về | Switch expression với `-> biểu_thức` hoặc colon group có `yield` |

**Checklist trước khi biên dịch:** (1) các hằng trong nhãn có trùng hay sai kiểu không; (2) có lỡ viết danh sách pattern phân tách bằng dấu phẩy không; (3) colon group có pattern variable bị dùng từ đường đi chưa khớp không; (4) có fall-through ngoài ý muốn không; (5) `default` và `case null` đã xử lý đúng phạm vi chưa; (6) thứ tự case pattern có gây dominance không; và (7) switch expression/enhanced statement có exhaustive không.

**Kết luận:** “Kết hợp nhiều case label” trong Java 21 có **nhiều cơ chế khác nhau**: gộp **case constant** bằng dấu phẩy, chia sẻ **colon statement group** giữa nhiều nhãn, hoặc kết hợp đặc biệt **`case null, default`**. Đối với pattern có biến, hãy dùng từng nhánh riêng hoặc một supertype phù hợp; đừng mang cú pháp gộp hằng số áp sang danh sách pattern. Chính sự phân biệt này giúp code ngắn mà vẫn đúng về scope, fall-through và an toàn kiểu.

### Tài liệu tham khảo

- [Java Language Specification 21, §14.11 — Switch Statements](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.11)
- [Oracle Java 21 — Pattern Matching for switch](https://docs.oracle.com/en/java/javase/21/language/pattern-matching-switch.html)
- [JEP 441 — Pattern Matching for switch](https://openjdk.org/jeps/441)
