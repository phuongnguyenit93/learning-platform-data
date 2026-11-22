# Guard có side effect và rủi ro trong Java pattern matching

## 1. Khi một điều kiện chọn nhánh làm thay đổi chương trình

Từ Java 21, pattern matching trong `switch` hỗ trợ nhãn dạng:

~~~java
case String text when text.length() >= 3 -> "VALID:" + text;
~~~

Phần sau `when` là **guard**: một biểu thức kiểu `boolean` hoặc `Boolean`, được đánh giá **sau khi pattern đã khớp**. Guard đúng thì case được chọn; guard sai thì Java xem xét nhãn tiếp theo.

Dù trông giống một phép kiểm tra, guard vẫn là **biểu thức Java bình thường**. Nó có thể gọi phương thức, truy cập một đối tượng có thể thay đổi, ghi log, tăng bộ đếm, cập nhật dữ liệu hoặc ném ngoại lệ. Các thao tác làm thay đổi trạng thái hay tạo hiệu ứng quan sát được được gọi là **side effect** (tác dụng phụ).

Ví dụ có rủi ro:

~~~java
case Ticket t when consumeCredit(t) -> "APPROVED";
~~~

Nếu `consumeCredit(t)` **trừ credit trước khi trả kết quả**, nó có thể làm thay đổi dữ liệu ngay cả khi guard trả `false` và Java chuyển sang nhánh `DECLINED`. Pattern matching không tự đảo ngược những thay đổi đó.

**Mục tiêu bài học:**

- Hiểu chính xác khi nào guard được đánh giá và vì sao một guard trả `false` vẫn có thể để lại side effect.
- Phân biệt side effect có thể quan sát được với logic kiểm tra thuần (*pure predicate*).
- Nhận ra rủi ro từ mutation, logging/metrics, I/O, lỗi runtime, Boolean nullable và việc chạy lại thao tác.
- Biết Java 21 giới hạn việc thay đổi biến cục bộ trong guard như thế nào, nhưng không ngăn mọi side effect.
- Tổ chức code theo hướng **guard kiểm tra – nhánh xử lý thực hiện hành động**, đồng thời hiểu giới hạn về đồng thời (*concurrency*) của cách tách này.
- Viết test chứng minh thứ tự guard, kết quả và trạng thái sau khi chạy.

Các chương trình hoàn chỉnh dùng `javac --release 21`; **không cần preview**. Những đoạn được ghi “cố ý không biên dịch” chỉ nhằm phân tích lỗi.

## 2. Cơ chế đánh giá: pattern trước, guard sau, nhánh cuối cùng

Xét:

~~~java
String result = switch (value) {
    case String s when checkA(s) -> "A";
    case String s when checkB(s) -> "B";
    case String s -> "OTHER_STRING";
    case null -> "NULL";
    default -> "OTHER";
};
~~~

Đây là trích đoạn trong một phương thức có `Object value`; `checkA` và `checkB` là các phương thức minh họa cần được định nghĩa.

Quy tắc thực thi quan trọng:

1. Java đánh giá selector `value` rồi tìm nhãn có thể áp dụng theo thứ tự các case.
2. Một nhãn `case String s` phải khớp kiểu `String` trước. Nếu không khớp, Java **không** gọi guard của nhãn đó.
3. Nếu pattern khớp, `s` được gắn và guard `checkA(s)` được đánh giá.
4. Nếu guard đúng, Java chạy rule `-> "A"` và hoàn tất switch expression; `checkB(s)` không được gọi.
5. Nếu guard sai, Java xét nhãn tiếp theo. Nếu đó là nhãn có guard, guard khác có thể được gọi.
6. Guard trả `false` **không** khôi phục trạng thái ban đầu. Nếu nó đã thay đổi biến hoặc đối tượng thì tác dụng phụ vẫn còn.
7. Nếu guard ném ngoại lệ, việc chọn nhánh kết thúc bất thường bằng ngoại lệ. Java không xem đó như `false` và không tự chuyển sang case tiếp theo.

**Guard không phải transaction và không phải một hàm luôn được đánh giá:** nó chỉ chạy nếu việc khớp pattern tương ứng thành công và luồng xét nhãn đi tới vị trí đó. Với nhiều guarded case, một lần switch có thể gọi nhiều guard trước khi chọn được nhánh.

Với `null`, type pattern `String s` không khớp nên các guard `String` không chạy. Tuy nhiên, bản thân switch trên `null` vẫn cần đường xử lý phù hợp như `case null`; chỉ có `default` thường không thay thế được `case null` trong pattern switch Java 21.

## 3. Side effect là gì trong một guard?

Một **pure predicate** chỉ tính câu trả lời đúng/sai từ đầu vào theo một cách không thay đổi trạng thái quan sát được. Ví dụ với một `String` không thay đổi:

~~~java
case String s when s.length() >= 3 && !s.isBlank() -> "VALID";
~~~

Các phép đọc độ dài, kiểm tra blank và toán tử Boolean không sửa đối tượng `String`. Nếu cùng đầu vào và cùng trạng thái liên quan, kết quả có thể dự đoán.

Ngược lại, các hoạt động sau tạo side effect hoặc phụ thuộc trạng thái thay đổi:

| Hoạt động trong guard | Side effect hoặc rủi ro |
| --- | --- |
| `counter.incrementAndGet() > 3` | Tăng bộ đếm mỗi khi guard được gọi, kể cả khi nhánh chưa được chọn |
| `ticket.credits-- > 0` | Thay đổi dữ liệu nghiệp vụ trong lúc lựa chọn nhánh |
| `repository.save(record)` | Có thể ghi cơ sở dữ liệu, làm phát sinh I/O và ngoại lệ |
| `queue.poll() != null` | Tiêu thụ một phần tử hàng đợi để kiểm tra, khiến lần gọi sau khác |
| `sendEmail(...)` | Hành động bên ngoài có thể xảy ra trước khi biết nhánh cuối |
| `clock.instant().isAfter(deadline)` | Thường không làm thay đổi clock, nhưng kết quả phụ thuộc thời gian; không phải điều kiện ổn định giữa các lần gọi |
| `externalFlag.get()` | Đọc trạng thái chia sẻ có thể thay đổi vì thread khác; cần xét tính nhất quán |

**Không phải mọi side effect đều luôn sai.** Ví dụ tăng số lần guard được xét có thể phục vụ mục đích quan sát, nhưng nó phải là hành vi chủ đích. Rủi ro xuất hiện khi người viết code tưởng guard chỉ xác định đúng/sai mà không nhận ra nó có thể thay đổi trạng thái, ghi dữ liệu hoặc làm kết quả phụ thuộc thứ tự xét case.

Các phương thức trong bảng là ví dụ ý tưởng; không phải API Java nào cũng có tên giống như minh họa. Mọi thao tác không được định nghĩa trong chương trình đầy đủ cần có implementation thích hợp.

## 4. Chương trình chạy được: guard bị gọi dù case không được chọn

Để thấy các lần đánh giá thật sự, ta thêm một bộ đếm và in log mỗi khi guard chạy. Lưu thành `GuardTraceDemo.java`:

~~~java
import java.util.concurrent.atomic.AtomicInteger;

public class GuardTraceDemo {
    static final AtomicInteger calls = new AtomicInteger();

    static boolean probe(String label, String text, boolean passed) {
        System.out.println("GUARD " + label + " " + text
            + " -> " + passed + ", calls=" + calls.incrementAndGet());
        return passed;
    }

    static String classify(Object value) {
        return switch (value) {
            case String s when probe("A", s, s.startsWith("A")) -> "STARTS_A";
            case String s when probe("LONG", s, s.length() >= 3) -> "LONG";
            case String s -> "OTHER_STRING";
            case null -> "NULL";
            default -> "NOT_STRING";
        };
    }

    public static void main(String[] args) {
        System.out.println("RESULT " + classify("Anna"));
        System.out.println("RESULT " + classify("Bob"));
        System.out.println("RESULT " + classify("Hi"));
        System.out.println("RESULT " + classify(42));
        System.out.println("RESULT " + classify(null));
        System.out.println("TOTAL=" + calls.get());
    }
}
~~~

Chạy trên JDK 21+:

~~~bash
javac --release 21 GuardTraceDemo.java
java GuardTraceDemo
~~~

Kết quả chính xác:

~~~text
GUARD A Anna -> true, calls=1
RESULT STARTS_A
GUARD A Bob -> false, calls=2
GUARD LONG Bob -> true, calls=3
RESULT LONG
GUARD A Hi -> false, calls=4
GUARD LONG Hi -> false, calls=5
RESULT OTHER_STRING
RESULT NOT_STRING
RESULT NULL
TOTAL=5
~~~

Giải thích theo từng lần gọi:

- **`"Anna"`:** pattern `String s` khớp; guard `A` được gọi, trả `true`, tăng counter lên 1. Rule `STARTS_A` được chọn, guard `LONG` phía sau không chạy.
- **`"Bob"`:** guard `A` trả `false` nhưng đã tăng counter lên 2; guard `LONG` được gọi, tăng counter lên 3 rồi trả `true`. Kết quả là `LONG`.
- **`"Hi"`:** hai guard đều trả `false`; counter tăng thêm hai lần (4 và 5). Kết quả cuối là `OTHER_STRING`.
- **`42`:** không khớp `String` nên hai guard không được gọi; `default` trả `NOT_STRING`.
- **`null`:** đi vào `case null`; hai guard cũng không chạy.

**Bài học quan trọng:** số lần gọi guard **không bằng** số lần nhánh của guard được chọn. Một guard `false` vẫn có thể làm tăng metrics, tạo log hoặc cập nhật dữ liệu. Nếu kiểm thử chỉ nhìn giá trị `RESULT` mà không kiểm tra counter, rất dễ bỏ sót lỗi.

Trong demo, `AtomicInteger.incrementAndGet()` làm mỗi lần tăng là thao tác nguyên tử cho riêng biến đếm. Nhưng **tính nguyên tử của bộ đếm không khiến toàn quá trình chọn case và xử lý nghiệp vụ trở thành một transaction**.

## 5. Rủi ro mutation: guard làm mất credit ngay cả khi từ chối

Ví dụ sau mô phỏng một vé có số lượt sử dụng. Chương trình viết guard có side effect **cố ý để thấy lỗi thiết kế**. Lưu `GuardMutationDemo.java`:

~~~java
public class GuardMutationDemo {
    static final class Ticket {
        int credits;
        Ticket(int credits) { this.credits = credits; }
    }

    static boolean consumeEvenOnFailure(Ticket t) {
        --t.credits;
        return t.credits >= 0;
    }

    static String attempt(Object value) {
        return switch (value) {
            case Ticket t when consumeEvenOnFailure(t) ->
                "APPROVED, credits=" + t.credits;
            case Ticket t -> "DECLINED, credits=" + t.credits;
            default -> "OTHER";
        };
    }

    public static void main(String[] args) {
        Ticket ticket = new Ticket(2);
        System.out.println(attempt(ticket));
        System.out.println(attempt(ticket));
        System.out.println(attempt(ticket));
    }
}
~~~

~~~bash
javac --release 21 GuardMutationDemo.java
java GuardMutationDemo
~~~

Kết quả:

~~~text
APPROVED, credits=1
APPROVED, credits=0
DECLINED, credits=-1
~~~

Vấn đề:

1. `case Ticket t` khớp đối tượng vé.
2. Guard gọi `consumeEvenOnFailure(t)` và **giảm `t.credits` trước khi kiểm tra điều kiện**.
3. Hai lần đầu số lượt giảm từ 2 → 1 → 0, guard trả `true` và nhánh `APPROVED` chạy.
4. Lần thứ ba giảm 0 → -1, guard trả `false` và Java chuyển sang case `Ticket t` không guard.
5. Dù kết quả là `DECLINED`, số dư đã thành **-1**. Nếu ví dụ này là giao dịch thật, nó có thể làm hỏng dữ liệu nghiệp vụ.

Guard không cung cấp khả năng rollback. Tình huống tương tự xuất hiện nếu guard gửi yêu cầu thanh toán, xóa một phần tử khỏi queue, ghi trạng thái user, hoặc tăng số lần thử đăng nhập **trước khi biết nhánh cuối cùng**.

Một dấu hiệu code smell: tên phương thức guard chứa động từ hành động như `charge`, `consume`, `reserve`, `delete`, `publish` hoặc `send`, trong khi nhiệm vụ cần làm chỉ là kiểm tra một điều kiện.

## 6. Tách quyết định và hành động: để when chỉ kiểm tra

Một phiên bản dễ hiểu hơn là dùng guard để xét trạng thái, còn thao tác tiêu thụ credit nằm ở **rule body** sau khi case được chọn. Lưu `GuardActionSeparationDemo.java`:

~~~java
public class GuardActionSeparationDemo {
    static final class Ticket {
        int credits;
        Ticket(int credits) { this.credits = credits; }
    }

    static String attempt(Object value) {
        return switch (value) {
            case Ticket t when t.credits > 0 -> {
                t.credits--;
                yield "SPENT, credits=" + t.credits;
            }
            case Ticket t -> "NO_CREDIT, credits=" + t.credits;
            default -> "OTHER";
        };
    }

    public static void main(String[] args) {
        Ticket ticket = new Ticket(2);
        System.out.println(attempt(ticket));
        System.out.println(attempt(ticket));
        System.out.println(attempt(ticket));
        System.out.println(attempt("other"));
    }
}
~~~

~~~bash
javac --release 21 GuardActionSeparationDemo.java
java GuardActionSeparationDemo
~~~

Kết quả:

~~~text
SPENT, credits=1
SPENT, credits=0
NO_CREDIT, credits=0
OTHER
~~~

Khác với demo trước:

- Guard `t.credits > 0` chỉ **đọc** trạng thái. Khi sai, nhánh `NO_CREDIT` trả kết quả mà không trừ credit.
- Rule body `case Ticket t when ... -> { ... }` mới thực hiện trừ credit và `yield` kết quả.
- Với lần thử thứ ba, credit giữ nguyên `0` chứ không thành `-1`.

**Giới hạn rất quan trọng:** ví dụ sửa này chỉ minh họa hành vi đúng trong **luồng đơn**. Nếu cùng `Ticket` được nhiều thread xử lý đồng thời, một thread có thể thấy `credits > 0` rồi bị thread khác thay đổi credit **trước khi bước trừ diễn ra**. Tách guard và hành động giúp giảm side effect ẩn, nhưng **không tự tạo atomicity**.

Với trạng thái chia sẻ, cần một thao tác điều kiện–cập nhật nguyên tử như compare-and-set thích hợp, khóa bảo vệ trạng thái, transaction cơ sở dữ liệu hoặc API nghiệp vụ có bảo đảm đồng thời. Nếu không, vẫn có lỗi **TOCTOU** (*time-of-check to time-of-use*): điều kiện đã đúng lúc kiểm tra nhưng không còn đúng khi thực hiện hành động.

Để thiết kế tốt hơn, thường tách thành:

- **Phân loại dữ liệu:** pattern và guard tập trung xác nhận kiểu/điều kiện.
- **Quyết định:** chọn một kết quả hoặc mô hình lệnh/ý định.
- **Thực hiện hành động:** xử lý tại ranh giới nghiệp vụ rõ ràng, có đồng bộ/transaction khi cần.

Không dùng việc tách bước để thay thế kiểm tra nguyên tử ở nơi có tranh chấp tài nguyên.

## 7. Guard ném ngoại lệ: Java không tự chuyển sang case khác

Một guard có thể ném exception trong quá trình đánh giá. Đó là **abrupt completion**: việc tìm nhãn `case` chấm dứt bằng ngoại lệ. Guard ném lỗi **không** được xem như guard trả `false`.

Ví dụ thường gặp là parse dữ liệu trong guard. Lưu `GuardExceptionDemo.java`:

~~~java
public class GuardExceptionDemo {
    static boolean positiveNumber(String text) {
        System.out.println("PARSE " + text);
        return Integer.parseInt(text) > 0;
    }

    static String classify(Object value) {
        return switch (value) {
            case String s when positiveNumber(s) -> "POSITIVE";
            case String s -> "OTHER_STRING";
            case null -> "NULL";
            default -> "OTHER";
        };
    }

    public static void main(String[] args) {
        System.out.println("RESULT " + classify("7"));
        System.out.println("RESULT " + classify("0"));
        try {
            System.out.println("RESULT " + classify("abc"));
        } catch (NumberFormatException ex) {
            System.out.println("CAUGHT NumberFormatException");
        }
    }
}
~~~

~~~bash
javac --release 21 GuardExceptionDemo.java
java GuardExceptionDemo
~~~

Kết quả:

~~~text
PARSE 7
RESULT POSITIVE
PARSE 0
RESULT OTHER_STRING
PARSE abc
CAUGHT NumberFormatException
~~~

Đọc kết quả:

- `"7"` parse được số dương nên guard đúng; nhánh `POSITIVE` chạy.
- `"0"` parse được nhưng điều kiện `> 0` sai; Java tiếp tục tới case `String s` và trả `OTHER_STRING`.
- `"abc"` làm `Integer.parseInt` ném `NumberFormatException`; nhánh `OTHER_STRING` **không chạy** vì quá trình đánh giá guard đã kết thúc bằng ngoại lệ.
- `System.out.println("PARSE " + text)` cũng là side effect: log đã được ghi ra trước khi ngoại lệ xảy ra.

Nếu dữ liệu có thể không parse được và “parse lỗi” nên được coi là kết quả không khớp, hãy viết một predicate có chính sách lỗi rõ ràng, ví dụ `try/catch NumberFormatException` và trả `false` khi lỗi parse là điều kiện bình thường. **Chỉ bắt những lỗi thật sự dự kiến**; đừng dùng `catch (Exception) { return false; }` để âm thầm che lỗi kết nối, dữ liệu hoặc lỗi lập trình nghiêm trọng.

Nếu parse là bước có giá trị nghiệp vụ cần dùng ở nhánh đã chọn, cân nhắc parse một lần ở tầng trước rồi dùng một kiểu dữ liệu đã xác thực, thay vì lặp thao tác có thể ném lỗi trong nhiều guard.

## 8. Boolean nullable cũng có thể làm guard ném NullPointerException

JLS Java 21 cho phép guard có kiểu `boolean` **hoặc `Boolean`**. Nếu guard trả `Boolean`, Java sẽ unbox thành `boolean` để quyết định nhánh. Nếu giá trị là `null`, việc unboxing gây `NullPointerException`.

Lưu `GuardBooleanNullDemo.java`:

~~~java
public class GuardBooleanNullDemo {
    static Boolean nullableFlag(String s) {
        return s.isEmpty() ? null : Boolean.TRUE;
    }

    static String classify(Object value) {
        return switch (value) {
            case String s when nullableFlag(s) -> "TRUE";
            case String s -> "FALSE";
            default -> "OTHER";
        };
    }

    public static void main(String[] args) {
        System.out.println(classify("x"));
        try {
            System.out.println(classify(""));
        } catch (NullPointerException ex) {
            System.out.println("CAUGHT NullPointerException");
        }
    }
}
~~~

~~~bash
javac --release 21 GuardBooleanNullDemo.java
java GuardBooleanNullDemo
~~~

Kết quả:

~~~text
TRUE
CAUGHT NullPointerException
~~~

Với chuỗi rỗng `""`, pattern `String s` khớp nhưng `nullableFlag(s)` trả `null`. Guard không coi `null` là `false`; nó ném lỗi khi unbox và không chạy case `String s` kế tiếp.

**Cách tránh:** ưu tiên predicate trả về primitive `boolean`. Nếu API bắt buộc trả `Boolean` nullable, quy định rõ chính sách null: có thể dùng `Boolean.TRUE.equals(nullableFlag(s))` để chỉ coi `true` là đạt. Cách này không tự bắt các ngoại lệ khác mà lời gọi phương thức có thể ném.

Khác biệt cần phân biệt:

- Selector `null` không khớp `case String s`, nên guard của pattern này không được gọi.
- Selector là một `String` không null, nhưng guard trả `Boolean null`, có thể gây `NullPointerException` trong quá trình đánh giá guard.

## 9. Java 21 chặn một số mutation trực tiếp trong guard, nhưng không chặn mọi side effect

Một chi tiết dễ bỏ qua trong JLS `14.11.1: local variable, formal parameter hoặc exception parameter **được dùng nhưng không được khai báo trong guard** phải là `final` hoặc *effectively final*. Nghĩa là không thể tùy tiện tăng/giảm biến cục bộ rồi dùng nó trong guard.

Ví dụ sau **cố ý không biên dịch**:

~~~java
static String invalid(Object value) {
    int attempts = 0;
    return switch (value) {
        case String s when ++attempts > 0 -> "YES";
        default -> "NO";
    };
}
~~~

`javac --release 21` báo:

~~~text
error: local variables referenced from a guard must be final or effectively final
~~~

Vì câu lệnh `++attempts` làm thay đổi local `attempts`, nó không thỏa quy tắc *effectively final*.

**Tuy nhiên, đây không phải một cơ chế bảo đảm guard không có side effect:**

- Có thể giữ tham chiếu đến một đối tượng biến đổi được trong biến `final` và gọi phương thức thay đổi nội dung đối tượng đó. Ví dụ `AtomicInteger.incrementAndGet()` trong `GuardTraceDemo` vẫn hợp lệ.
- Có thể thay đổi trường của đối tượng được pattern variable tham chiếu, ví dụ `--t.credits` trong `GuardMutationDemo`.
- Có thể gọi I/O, phương thức ghi log hoặc API bên ngoài ngay trong guard.
- Có thể đọc các trạng thái thay đổi theo thời gian; kể cả không ghi gì, kết quả cũng không nhất thiết ổn định.

**Tính bất biến của tham chiếu** khác với **tính bất biến của đối tượng**. `final AtomicInteger counter` ngăn gán lại biến `counter` sang đối tượng khác, không ngăn gọi `counter.incrementAndGet()`.

Một giới hạn khác được Java kiểm tra: guard không được là **constant expression** có giá trị `false`. `case String s when false -> ...` gây lỗi compile-time. Không nhầm quy tắc này với guard trả `false` tại runtime, điều đó hoàn toàn hợp lệ và xảy ra thường xuyên.

## 10. Thiết kế guard thuần, dễ đoán và dễ kiểm thử

Một predicate chỉ kiểm tra điều kiện thường là cách tốt nhất để viết `when`. Lưu chương trình đầy đủ `GuardPureDemo.java`:

~~~java
public class GuardPureDemo {
    static boolean eligible(String s) {
        return s != null && s.length() >= 3
            && s.chars().allMatch(Character::isLetter);
    }

    static String classify(Object value) {
        return switch (value) {
            case String s when eligible(s) -> "ACCEPT:" + s;
            case String s -> "REJECT:" + s;
            case null -> "NULL";
            default -> "OTHER";
        };
    }

    public static void main(String[] args) {
        System.out.println(classify("Java"));
        System.out.println(classify("a2"));
        System.out.println(classify(""));
        System.out.println(classify(null));
    }
}
~~~

~~~bash
javac --release 21 GuardPureDemo.java
java GuardPureDemo
~~~

Kết quả:

~~~text
ACCEPT:Java
REJECT:a2
REJECT:
NULL
~~~

Phương thức `eligible` chỉ đọc chuỗi và trả `boolean`; nó không tăng counter, trừ credit hay ghi dữ liệu. Trong bài này, các đầu vào thử là chuỗi ký tự ASCII; nếu hệ thống phải xử lý đầy đủ ký tự Unicode ngoài Basic Multilingual Plane, cân nhắc `codePoints()` thay cho `chars()` khi kiểm tra “chữ cái”.

Cách viết này đem lại những lợi ích:

1. **Mục đích rõ ràng:** người đọc nhìn `when eligible(s)` hiểu đây là một phép kiểm tra, không phải hành động.
2. **Dễ test:** có thể kiểm tra `eligible` độc lập theo các trường hợp đạt/không đạt.
3. **Dễ bảo trì:** thêm nhánh `case String s` dự phòng không làm thay đổi dữ liệu chỉ vì guard trước đó trả sai.
4. **Dễ đo lường:** nếu cần log hoặc metrics, đặt chúng ở nơi có ranh giới trách nhiệm rõ, ví dụ bộ điều phối bên ngoài hoặc nhánh đã chọn, không ẩn trong predicate.
5. **Dễ giải thích null:** `case String s` không khớp null; `case null` được xử lý riêng thay vì dựa vào việc guard tự gánh mọi loại dữ liệu.

Một predicate vẫn có thể phụ thuộc dữ liệu mutable mà không viết vào dữ liệu; trong môi trường nhiều thread, cần bảo đảm việc đọc nhất quán và vòng đời dữ liệu phù hợp. “Không gây side effect” **không đồng nghĩa** “tự động thread-safe” hoặc “kết quả bất biến mãi mãi”.

## 11. Rủi ro về thứ tự case và thời điểm kiểm tra

Một số kết quả về guard chỉ đúng trong ngữ cảnh cụ thể vì thứ tự các case quyết định **guard nào được gọi**.

~~~java
switch (value) {
    case String s when checkA(s) -> actionA();
    case String s when checkB(s) -> actionB();
    case String s -> fallback();
    default -> other();
}
~~~

Đây là đoạn **minh họa** trong switch statement, với các hàm tự định nghĩa. Nếu `checkA(s)` trả `true` thì `checkB(s)` không được gọi. Nếu `checkA(s)` trả `false` sau khi đã cập nhật trạng thái, `checkB(s)` có thể quan sát **trạng thái sau thay đổi**, không còn trạng thái ban đầu.

Ví dụ nguy hiểm: `checkA` trừ hạn mức rồi trả `false`, còn `checkB` quyết định một hành động khác dựa trên hạn mức còn lại. Chỉ cần đổi thứ tự hai case, kết quả nghiệp vụ có thể khác nhau. Một thay đổi mang vẻ ngoài “refactor cách phân loại” lại có thể gây lỗi trạng thái khó phát hiện.

**Dominance** cũng liên quan: một case `case String s -> ...` không guard ở trước `case String s when ...` sẽ bao trùm case sau và bị compiler từ chối. Nhưng Java không thể suy luận mọi sự giao nhau phức tạp của nhiều guard; programmer phải tự kiểm soát ý nghĩa thứ tự điều kiện.

Khi cần xử lý nhiều trường hợp, nên:

- Đặt điều kiện cụ thể trước nhãn tổng quát và không đưa mutation vào các điều kiện.
- Đặt case dự phòng cùng kiểu để xử lý khi guard sai.
- Dùng tên predicate gợi ý **kiểm tra**, chẳng hạn `isEligible`, `hasEnoughCredit`, `isValidPeriod`.
- Nếu logic phân loại quá phức tạp, đưa nó vào một hàm độc lập trả giá trị mô tả trạng thái, rồi switch trên trạng thái đó.
- Không giả định guard sẽ được gọi đúng một lần trong toàn đời nghiệp vụ: cùng switch có thể được gọi nhiều lần do retry, event redelivery, loop hoặc yêu cầu khác.

## 12. Side effect ngoài hệ thống: retry, transaction và concurrency

Trong một ứng dụng server, tác dụng phụ của guard có thể vượt xa một bộ đếm trong bộ nhớ.

**Retry và idempotency.** Nếu một request được xử lý lại vì timeout hoặc job được redeliver, switch cũng có thể được gọi lại. Nếu guard gửi email, đặt hàng hoặc ghi database, hành động có thể xảy ra **nhiều lần**. Cần tách lệnh thực thi khỏi điều kiện; với hành động có thể bị retry, cân nhắc *idempotency key* và cơ chế chống xử lý trùng phù hợp.

**Transaction.** Việc Java đánh giá guard không mở, commit hay rollback một transaction. Nếu guard thay đổi dữ liệu rồi trả false, các side effect đã xảy ra sẽ không tự biến mất. Nếu đang có transaction do ứng dụng quản lý, quy tắc commit/rollback do transaction manager và code ứng dụng quyết định, **không phải** do kết quả true/false của guard.

**Concurrency.** Nếu guard đọc số dư hoặc trạng thái chia sẻ và nhánh được chọn mới thực hiện thay đổi, một thread khác có thể thay đổi trạng thái giữa hai bước. `AtomicInteger` giúp thao tác riêng lẻ có tính nguyên tử, nhưng cặp “đọc/kiểm tra → ghi cập nhật” không đương nhiên nguyên tử. Có thể cần khóa, compare-and-set, optimistic locking hoặc transaction tùy loại dữ liệu.

**Observability.** Log, audit và metrics cũng là side effect. Một counter được tăng trong guard thường biểu thị **số lần đánh giá điều kiện**, không biểu thị **số lần hành động thành công**. Đặt tên metric chính xác hoặc cập nhật metric “success” trong nhánh thành công. Nếu guard có side effect để đo thời gian/call count, test cần xác nhận cả phép đếm và kết quả.

**Bảo mật.** Không nên dùng guard để thực hiện hành động nhạy cảm như cấp quyền, trừ tiền hoặc tạo token trước khi toàn bộ yêu cầu được xác thực. Guard có thể từ chối nhánh nhưng hiệu ứng nhạy cảm vẫn xảy ra. Ủy quyền nên là điều kiện kiểm tra, còn hành động có bảo vệ và được thực thi trong ranh giới nhất quán.

## 13. Short-circuit trong guard làm side effect khó dự đoán hơn

Một guard có thể kết hợp `&&`, `||` hoặc các phép điều kiện khác. Java dùng short-circuit:

~~~java
case String s when !s.isEmpty() && expensiveCheck(s) -> "MATCH";
~~~

Nếu `s.isEmpty()` đúng, `expensiveCheck(s)` không được gọi. Nếu không rỗng, phương thức bên phải mới chạy. Cách này hữu ích để tránh công việc thừa; nhưng nếu `expensiveCheck` có side effect, **số lần gọi nó phụ thuộc vào giá trị đầu vào và thứ tự các toán hạng**.

Với `||`:

~~~java
case String s when s.isEmpty() || expensiveCheck(s) -> "MATCH";
~~~

Nếu `s.isEmpty()` đúng thì vế sau không chạy. Đổi thứ tự điều kiện có thể thay đổi số lần gọi phương thức có side effect, dù kết quả Boolean trong một số trường hợp vẫn giống nhau.

Các ví dụ này là **trích đoạn** yêu cầu một phương thức `expensiveCheck(String)` trả `boolean`, không phải chương trình độc lập. Nên bảo đảm những phương thức chỉ kiểm tra trạng thái như `expensiveCheck` không tự ý làm thay đổi dữ liệu.

Một guard thuần có short-circuit thường làm mã an toàn hơn:

~~~java
case String s when !s.isEmpty() && s.charAt(0) == 'A' -> "A";
~~~

Ở đây `charAt(0)` không chạy với chuỗi rỗng nên không có lỗi truy cập chỉ số. Điều kiện chỉ kiểm tra dữ liệu mà không sửa chuỗi. Tuy nhiên, guard có thể còn ném ngoại lệ nếu phương thức bên trong không tuân thủ tiền điều kiện; short-circuit chỉ bảo vệ những đường được viết đúng.

## 14. Các lỗi biên dịch cần phân biệt với rủi ro runtime

Không phải mọi guard nguy hiểm đều bị compiler từ chối. Những ví dụ sau giúp phân biệt **quy tắc hợp lệ của Java** và **tính an toàn nghiệp vụ**.

### 14.1. Tăng biến cục bộ bên ngoài guard

~~~java
static String invalid(Object value) {
    int attempts = 0;
    return switch (value) {
        case String s when ++attempts > 0 -> "YES";
        default -> "NO";
    };
}
~~~

**Cố ý không biên dịch:** `attempts` không còn effectively final; `javac --release 21` từ chối vì local variable được tham chiếu từ guard phải final hoặc effectively final.

### 14.2. Guard là hằng false

~~~java
static String invalid(Object value) {
    return switch (value) {
        case String s when false -> "NEVER";
        default -> "OTHER";
    };
}
~~~

**Cố ý không biên dịch:** JLS Java 21 không cho guard là constant expression bằng `false`; compiler báo `this case label has a guard that is a constant expression with value 'false'`. Điều này khác với một predicate trả `false` ở runtime.

### 14.3. Guard không phải điều kiện boolean

~~~java
static String invalid(Object value) {
    return switch (value) {
        case String s when s.length() -> "YES";
        default -> "NO";
    };
}
~~~

**Cố ý không biên dịch:** `s.length()` trả `int`, không phải `boolean` hoặc `Boolean`. Cách sửa là `s.length() > 0`.

### 14.4. Guard bị che bởi nhãn rộng trước đó

~~~java
static String invalid(Object value) {
    return switch (value) {
        case String s -> "ALL_STRINGS";
        case String s when s.isBlank() -> "BLANK";
        default -> "OTHER";
    };
}
~~~

**Cố ý không biên dịch:** case `String s` đầu đã bắt mọi đối tượng String nên nhãn có guard phía sau bị dominated. Hãy đảo thứ tự hai case.

### 14.5. Code biên dịch nhưng vẫn có side effect không mong muốn

~~~java
case Ticket t when consumeEvenOnFailure(t) -> "APPROVED";
~~~

**Có thể biên dịch** nếu `Ticket` và phương thức `consumeEvenOnFailure` được định nghĩa tương ứng, như `GuardMutationDemo` ở phần 5. Compiler không đảm bảo đó là một thao tác kiểm tra thuần. Nếu guard trả false, nó vẫn có thể đã thay đổi `t.credits`.

**Kết luận:** compiler kiểm tra cú pháp, tính tương thích kiểu, quy tắc final/effectively final, dominance và exhaustiveness; nó **không** xác minh tính idempotent, không tự rollback mutation và không bảo đảm transaction cho logic nghiệp vụ.

## 15. Chiến lược kiểm thử guard có rủi ro

Chỉ kiểm tra kết quả trả về của switch là chưa đủ nếu guard thực thi hành động. Một test tốt nên xem cả **kết quả** lẫn **trạng thái/hệ quả sau khi chạy**.

| Kịch bản | Điều cần xác minh |
| --- | --- |
| Pattern không khớp | Guard không được gọi; side effect trong guard không xảy ra |
| Pattern khớp, guard đúng | Nhánh thích hợp được chọn; xác minh số lần guard chạy |
| Pattern khớp, guard sai | Chuyển tới nhãn dự phòng; xác minh không có mutation không mong muốn |
| Nhiều guarded case cùng kiểu | Thứ tự đánh giá đúng, và số lần gọi phương thức được kiểm soát |
| Guard ném ngoại lệ | Ngoại lệ được chuyển ra đúng ranh giới xử lý; không vô tình chạy fallback |
| Guard trả `Boolean null` | Kiểm tra chính sách null để tránh unboxing NPE |
| Lặp lại cùng thao tác | Không có trừ tiền/gửi yêu cầu nhiều lần ngoài dự kiến |
| Nhiều thread cùng trạng thái | Quy tắc đồng thời/transaction được kiểm tra độc lập |

Ba phép kiểm thử quan trọng có thể nhìn ngay từ output các chương trình:

1. `GuardTraceDemo` chứng minh 3 lần gọi `classify` với chuỗi tạo ra **5 lần gọi guard**, dù chỉ có 2 nhánh có guard được chọn.
2. `GuardMutationDemo` chứng minh lần thử thất bại vẫn làm `credits` giảm xuống **-1**.
3. `GuardActionSeparationDemo` chứng minh lần từ chối ở luồng đơn giữ `credits` ở **0**.

Khi viết JUnit test thực tế, có thể dùng spy/mock để đếm các lời gọi phụ thuộc, nhưng cũng nên xác minh trạng thái thật của đối tượng. Không coi mock interaction là bằng chứng về tính nguyên tử trong môi trường đồng thời.

## 16. Bài tập và đáp án

### Bài 1 — Guard false có side effect không?

Xét:

~~~java
case String s when metrics.incrementAndGet() > 10 -> "HIGH";
case String s -> "LOW";
~~~

Giả sử `metrics` là một `AtomicInteger` hợp lệ, giá trị ban đầu bằng 9. Một lần switch với selector `"abc"` trả kết quả gì và bộ đếm bằng bao nhiêu?

**Đáp án:** Guard tăng bộ đếm lên 10, điều kiện `10 > 10` sai, switch chọn `LOW`. Bộ đếm **vẫn là 10**. Guard false không rollback side effect.

### Bài 2 — Guard ném ngoại lệ

Với guard `Integer.parseInt(s) > 0` và nhãn `case String s -> "OTHER"` phía sau, điều gì xảy ra nếu selector là `"abc"`?

**Đáp án:** `parseInt` ném `NumberFormatException`; switch kết thúc bất thường. Java **không** tự nhảy tới `"OTHER"`. Muốn parse lỗi được coi là không khớp, cần logic kiểm tra/parse có chính sách exception phù hợp.

### Bài 3 — Phân biệt final và immutable

Vì sao dùng `final AtomicInteger counter` với `counter.incrementAndGet()` trong guard vẫn biên dịch, nhưng `++attempts` với một local `int attempts` bên ngoài guard bị lỗi?

**Đáp án:** `final` của tham chiếu chỉ ngăn gán lại biến sang đối tượng khác, không ngăn thay đổi nội dung đối tượng `AtomicInteger`. Guard Java 21 yêu cầu local variable tham chiếu từ ngoài phải final/effectively final; phép `++attempts` làm vi phạm quy tắc này.

### Bài 4 — Cải thiện an toàn cho guard

Bạn có:

~~~java
case Order o when repository.save(o) != null -> "SAVED";
case Order o -> "REJECTED";
~~~

Vấn đề là gì, và nên tái cấu trúc thế nào?

**Đáp án:** `save` là hành động I/O trong lúc chọn nhánh; nó có thể thay đổi database hoặc ném lỗi ngay cả khi kết quả guard không dẫn đến nhánh `SAVED`. Nên để guard chỉ kiểm tra điều kiện đủ, sau đó thực hiện `repository.save(o)` ở luồng xử lý được chọn, bên trong transaction/chính sách retry phù hợp. Cần xử lý lỗi và tính idempotent cho hành động ghi dữ liệu thay vì coi guard false là rollback.

`Order` và `repository` ở đây là các thành phần minh họa của ứng dụng, không phải API Java Core sẵn có.

### Bài 5 — Hai cách có cùng kết quả boolean nhưng khác side effect

~~~java
case String s when isShort(s) || auditAndCheck(s) -> "YES";
~~~

so với:

~~~java
case String s when auditAndCheck(s) || isShort(s) -> "YES";
~~~

Nếu `isShort(s)` trả true, trong hai trường hợp `auditAndCheck` có chắc được gọi cùng số lần không?

**Đáp án:** Không. Ở cách thứ nhất, `||` short-circuit nên `auditAndCheck` không chạy. Ở cách thứ hai, `auditAndCheck` chạy trước; nếu có side effect thì nó đã xảy ra trước khi xét `isShort`. Vì vậy dùng side effect trong guard làm thứ tự toán hạng trở nên quan trọng hơn chỉ tính Boolean.

### Bài 6 — Đồng thời

Hai thread cùng xử lý một `Ticket` có `credits = 1`. Mỗi thread kiểm tra guard `t.credits > 0` và trừ credit ở nhánh được chọn. Có chắc chỉ một thread thành công không?

**Đáp án:** Không. Nếu không có đồng bộ, cả hai thread có thể quan sát `credits > 0` trước khi một thread cập nhật trạng thái. Việc di chuyển mutation ra khỏi guard làm code minh bạch, nhưng **không** đảm bảo atomicity. Cần thao tác kiểm tra–cập nhật nguyên tử hoặc transaction/khóa phù hợp.

## 17. Checklist review và ghi nhớ

Khi review một `case Pattern p when predicate(p)`, hãy hỏi:

1. Guard có thực sự chỉ kiểm tra điều kiện hay đang gọi API tạo side effect?
2. Guard có thể trả false **sau khi đã thay đổi trạng thái** không?
3. Giá trị guard có thể ném ngoại lệ hay trả `Boolean null` không?
4. Nếu pattern không khớp, guard có được bỏ qua như mong đợi không?
5. Thứ tự các guarded case có thể khiến một side effect xảy ra nhiều lần hoặc khác thứ tự không?
6. Những local variable bên ngoài guard có đáp ứng final/effectively final theo Java 21 không?
7. Metrics có đếm số lần **đánh giá điều kiện** hay số lần **nhánh thành công**? Tên gọi có đúng không?
8. Nếu operation retry hoặc chạy nhiều thread, hành động có idempotent và atomic/transactional đúng mức không?
9. Các side effect nghiệp vụ đã được chuyển sang code xử lý rõ ràng, có ranh giới lỗi phù hợp chưa?
10. Test đã kiểm tra cả kết quả lẫn thay đổi trạng thái, exception và đường guard false chưa?

**Nguyên tắc chính:** `when` là công cụ **chọn nhánh**, không phải ranh giới commit hay rollback. Ưu tiên guard ngắn gọn, kiểm tra thuần và ít phụ thuộc trạng thái biến đổi; đưa hành động nghiệp vụ vào nơi thực thi rõ ràng, đồng thời sử dụng cơ chế đồng bộ/transaction khi dữ liệu được chia sẻ.

### Tài liệu chính thức

- Java SE 21 JLS `14.11.1 — Switch Blocks, điều kiện của guard và quy tắc đánh giá: https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.11.1
- Java SE 21 JLS `6.3.3 — Scope for Pattern Variables in case Labels: https://docs.oracle.com/javase/specs/jls/se21/html/jls-6.html#jls-6.3.3
- Oracle Java 21 — Pattern Matching for switch Expressions and Statements: https://docs.oracle.com/en/java/javase/21/language/pattern-matching-switch.html
- OpenJDK JEP 441 — Pattern Matching for switch (Java 21): https://openjdk.org/jeps/441
