# Điều kiện guard được đánh giá khi nào? — Guard when trong Java

## 1. Câu trả lời ngắn gọn

Trong **pattern matching for switch** của Java 21, guard là biểu thức điều kiện nằm sau từ khóa `when` của một nhãn `case` có pattern:

~~~java
return switch (value) {
    case String s when s.length() > 3 -> "Long string";
    case String s -> "Other string";
    default -> "Not a string";
};
~~~

**Điều kiện `when` chỉ được đánh giá sau khi giá trị selector đã khớp với pattern của chính nhãn `case` đó.** Nếu pattern không khớp, guard **không chạy**. Nếu pattern khớp:

- Guard trả `true`: nhãn `case` được chọn và thân nhánh được thực thi.
- Guard trả `false`: nhãn đó **không được chọn**; Java tiếp tục xét các nhãn phù hợp tiếp theo.
- Guard ném ngoại lệ: quá trình chọn nhãn kết thúc bằng ngoại lệ; Java **không** tự bỏ qua và chuyển sang case sau.

Nói cách khác, một nhãn `case T t when condition(t)` được chọn khi **cả hai điều kiện** đều thỏa: *pattern khớp* **và** *guard true*. Quy tắc này áp dụng cho cả **switch statement** và **switch expression** có pattern.

**Mốc phiên bản:** `when` với pattern case là tính năng chính thức trong **Java 21** (JEP 441). `switch expression` riêng lẻ đã chính thức từ Java 14, nhưng `case String s when ...` không phải cú pháp được hỗ trợ như một tính năng chính thức trong Java 17. Ví dụ chạy trong bài sử dụng JDK 21 trở lên.

## 2. Thứ tự các bước mà Java thực hiện

Xét:

~~~java
Object input = "Java";

String label = switch (input) {
    case String s when s.length() > 3 -> "LONG";
    case String s -> "STRING";
    default -> "OTHER";
};
~~~

Java thực hiện theo trình tự logic:

1. **Đánh giá biểu thức selector** `input` để lấy một giá trị. Trong một lượt chạy của switch, selector được đánh giá một lần; nó không được tính lại chỉ vì một guard trả false.
2. **Xác định nhãn case phù hợp**. Với selector không null, quá trình xét các nhãn case theo thứ tự từ trên xuống, tuân theo các quy tắc của switch.
3. **Thử pattern của nhãn có guard**. Với `case String s when ...`, Java trước hết kiểm tra giá trị có khớp `String s` hay không.
4. **Chỉ khi pattern khớp**, biến mẫu `s` được khởi tạo và guard `s.length() > 3` mới được đánh giá.
5. Nếu guard true, thực thi nhánh đó; nếu false, tiếp tục xét case sau. **Không** thực thi phần sau `->` của nhánh có guard false.
6. Nếu một nhãn không có guard khớp, nhãn đó được chọn trực tiếp. Nếu không nhãn cụ thể nào áp dụng thì `default` có thể được chọn, theo điều kiện của switch.

Một sơ đồ giúp ghi nhớ:

~~~text
Đánh giá selector một lần
          |
          v
   Thử case pattern hiện tại
          |
     +----+----+
     |         |
 Không khớp   Khớp
     |         |
     |     Có "when"?
     |       /    \
     |     Không   Có
     |       |      |
     |     Chọn   Tính guard
     |     case     / | \
     |           true false ngoại lệ
     |            |    |      |
     |         Chọn  Thử   Thoát switch
     |         case  case  bằng ngoại lệ
     |               tiếp
     +--> Thử nhãn case tiếp theo
~~~

Điểm quan trọng: biểu thức guard nằm **giữa hai thời điểm**: sau khi một pattern đã khớp nhưng **trước khi** thân case được chọn. Do đó, không nên xem `when` như một `if` được chạy vô điều kiện trước tất cả case hoặc như một `if` trong thân case sau khi case đã được chọn.

## 3. Các tình huống: khi nào guard chạy và khi nào bị bỏ qua?

Ví dụ:

~~~java
static String describe(Object value) {
    return switch (value) {
        case null -> "NULL";
        case String s when s.isBlank() -> "BLANK";
        case String s when s.length() >= 5 -> "LONG";
        case String s -> "SHORT";
        case Integer n when n > 0 -> "POSITIVE";
        case Integer n -> "NONPOSITIVE";
        default -> "OTHER";
    };
}
~~~

Đây là **phương thức minh họa Java 21**, đặt bên trong class trước khi biên dịch. Bảng sau giả định các pattern case được xét theo thứ tự ở ví dụ:

| Giá trị selector | Guard `s.isBlank()` | Guard `s.length() >= 5` | Guard `n > 0` | Kết quả |
| --- | --- | --- | --- | --- |
| `"   "` | Được đánh giá → true | Không chạy | Không chạy | `BLANK` |
| `"Java"` | Được đánh giá → false | Được đánh giá → false | Không chạy | `SHORT` |
| `"Java21"` | Được đánh giá → false | Được đánh giá → true | Không chạy | `LONG` |
| `Integer.valueOf(7)` | Không chạy | Không chạy | Được đánh giá → true | `POSITIVE` |
| `Integer.valueOf(-1)` | Không chạy | Không chạy | Được đánh giá → false | `NONPOSITIVE` |
| `Double.valueOf(2.5)` | Không chạy | Không chạy | Không chạy | `OTHER` |
| `null` | Không chạy | Không chạy | Không chạy | `NULL` |

Vì sao có thể truy cập `s` trong `when s.length() >= 5`? Bởi **pattern `String s` đã khớp trước đó**; biến mẫu `s` nằm trong scope của guard. Với selector là `Integer`, Java không thể khớp `String s` nên **không thử** `s.isBlank()` hoặc `s.length()`.

Nếu guard thứ nhất trả false, Java có thể tiếp tục kiểm tra guard thứ hai của case sau. Không tồn tại quy tắc “mỗi switch tối đa một guard”; cũng không có quy tắc “guard false nghĩa là chạy default ngay”.

## 4. Chương trình Java 21 quan sát chính xác thứ tự đánh giá

Lưu thành **`GuardTimingDemo.java`**:

~~~java
public class GuardTimingDemo {
    static int checks;

    static boolean probe(String name, boolean result) {
        ++checks;
        System.out.println("guard:" + name);
        return result;
    }

    static String classify(Object input) {
        return switch (input) {
            case null -> "NULL";

            case String s when probe("long", s.length() > 3)
                    -> "LONG:" + s;

            case String s when probe("nonblank", !s.isBlank())
                    -> "TEXT:" + s;

            case String s -> "OTHER_STRING:" + s;

            case Integer n when probe("positive", n > 0)
                    -> "POSITIVE:" + n;

            case Integer n -> "NONPOSITIVE:" + n;

            default -> "OTHER";
        };
    }

    static void run(Object input) {
        checks = 0;
        String result = classify(input);
        System.out.println("result=" + result + ";checks=" + checks);
    }

    public static void main(String[] args) {
        run("Java");
        run("ab");
        run(" ");
        run(-2);
        run(7);
        run(3.14);
        run(null);
    }
}
~~~

Biên dịch/chạy bằng JDK 21:

~~~bash
javac GuardTimingDemo.java
java GuardTimingDemo
~~~

Đầu ra:

~~~text
guard:long
result=LONG:Java;checks=1
guard:long
guard:nonblank
result=TEXT:ab;checks=2
guard:long
guard:nonblank
result=OTHER_STRING: ;checks=2
guard:positive
result=NONPOSITIVE:-2;checks=1
guard:positive
result=POSITIVE:7;checks=1
result=OTHER;checks=0
result=NULL;checks=0
~~~

Đọc kết quả theo từng nhóm:

- Với `"Java"`, `String s` khớp và guard `long` true, nên chỉ có **một** lời gọi `probe`. Các case sau không được thử.
- Với `"ab"`, guard `long` false; Java tiếp tục thử case String thứ hai, guard `nonblank` true. Vì thế **hai** lời gọi `probe` và kết quả `TEXT:ab`.
- Với `" "`, cả hai guard String đều false; sau đó case `String s` không guard khớp và tạo kết quả `OTHER_STRING: `.
- Với `-2` và `7`, chỉ case `Integer n` có guard `positive` được đánh giá; các guard dành cho String không chạy.
- Với `3.14` (kiểu `Double`) và `null`, không có lời gọi `probe` nào. `Double` đi vào `default`, còn null đi vào `case null`.

Biến `checks` chỉ nhằm minh họa số lần guard được đánh giá; **không nên dùng tác dụng phụ như thế trong logic guard của ứng dụng thực tế**. Một lời gọi khác tới `classify` sẽ bắt đầu quá trình chọn case mới, nên guard thích hợp có thể được đánh giá lại.

## 5. Guard false khác gì với if false bên trong thân case?

Hai đoạn trông giống nhau nhưng **không tương đương về luồng chọn case**.

**Có guard:**

~~~java
static String guarded(Object value) {
    return switch (value) {
        case String s when s.length() > 3 -> "LONG";
        case String s -> "SHORT";
        default -> "OTHER";
    };
}
~~~

Với `"ab"`, case String đầu **không áp dụng** vì guard false, nên Java thử case String thứ hai và trả `SHORT`.

**Chỉ if trong case:**

~~~java
static String insideCase(Object value) {
    return switch (value) {
        case String s -> {
            if (s.length() > 3) {
                yield "LONG";
            }
            yield "SHORT";
        }
        default -> "OTHER";
    };
}
~~~

Với `"ab"`, case `String s` đã được **chọn**; biểu thức `if` chỉ điều khiển việc tính kết quả **bên trong nhánh đã chọn**, không làm Java quay lại chọn một nhãn `case` khác.

Cả hai ví dụ trả kết quả giống nhau cho các giá trị đang xét, nhưng cơ chế khác nhau:

- `when` quyết định **case có được chọn không**.
- `if` trong block quyết định **thao tác bên trong case đã được chọn**.

Vì vậy, `when` đặc biệt hữu ích để viết nhiều nhánh đặc thù trên cùng một kiểu mà vẫn bảo toàn thứ tự ưu tiên. Khi chỉ có một nhánh cùng kiểu và xử lý nội bộ đơn giản, `if` trong nhánh cũng có thể dễ đọc hơn.

## 6. Selector được đánh giá một lần; nhiều guard có thể chạy

Một nhầm lẫn khác: do Java có thể thử nhiều case, lập trình viên tưởng biểu thức selector cũng bị gọi lại.

Ví dụ độc lập (**Java 21**), lưu thành **`GuardRecordDemo.java`**:

~~~java
public class GuardRecordDemo {
    record Order(int units, String id) {}

    static int sourceCalls;

    static Object source() {
        ++sourceCalls;
        System.out.println("source called");
        return new Order(3, "A1");
    }

    static boolean audit(String name, boolean result) {
        System.out.println("guard:" + name);
        return result;
    }

    static String route(Object order) {
        return switch (order) {
            case null -> "NULL";

            case Order(int units, String id)
                    when audit("bulk", units >= 10)
                    -> "BULK:" + id;

            case Order(int units, String id)
                    when audit("positive", units > 0)
                    -> "SMALL:" + id;

            case Order o -> "EMPTY:" + o.id();

            default -> "OTHER";
        };
    }

    public static void main(String[] args) {
        System.out.println("result=" + route(source()));
        System.out.println("sourceCalls=" + sourceCalls);
    }
}
~~~

~~~bash
javac GuardRecordDemo.java
java GuardRecordDemo
~~~

Kết quả chính xác:

~~~text
source called
guard:bulk
guard:positive
result=SMALL:A1
sourceCalls=1
~~~

Ở đây:

1. `source()` được gọi **một lần** để tạo selector: một record `Order(3, "A1")`.
2. Java thử record pattern đầu. Pattern khớp và trích xuất `units = 3`, `id = "A1"`; **sau đó** mới gọi `audit("bulk", units >= 10)`. Guard false.
3. Java thử record pattern thứ hai; nó cũng khớp và gọi `audit("positive", units > 0)`. Guard true.
4. Case thứ hai được chọn, tạo `SMALL:A1`. Case `Order o` phía dưới không được dùng.
5. `sourceCalls` vẫn là 1: nhiều lần xét pattern/guard **không đồng nghĩa đánh giá lại selector**.

Ví dụ này còn cho thấy guard của **record pattern** được đánh giá **sau khi pattern ngoài cùng và các component patterns đã khớp**. Nếu một component pattern không khớp, guard của nhãn đó không chạy.

## 7. Guard có thể thấy pattern variable từ lúc nào?

Quy tắc phạm vi quan trọng của `when`:

~~~java
case String s when s.length() > 3 -> "LONG:" + s;
~~~

- `String s` được kiểm tra trước.
- Nếu khớp, `s` đã được khởi tạo và **nằm trong scope của biểu thức guard**.
- Nếu guard true và case được chọn, `s` cũng có thể được dùng trong thân case.
- Nếu guard false, nhãn case đó bị bỏ qua; **không thể** sử dụng `s` của nhãn này ở một case khác như thể đây là cùng một biến.

Ví dụ lỗi (mảnh mã cố ý không biên dịch):

~~~java
return switch (value) {
    case String s when s.length() > 3 -> "LONG:" + s;
    case Integer n -> "NUMBER:" + s; // Lỗi: s không thuộc case này
    default -> "OTHER";
};
~~~

Mỗi case có scope riêng. Trong nhãn `case String s` thứ hai, nếu bạn khai báo lại tên `s`, đó là pattern variable của **nhãn khác**, không phải biến được chuyển từ case trước sang.

Vì pattern đã khớp trước khi đánh giá guard, bạn không cần làm một cast lặp lại:

~~~java
case String s when s.startsWith("ID-") -> s.substring(3);
~~~

Gọi `s.startsWith(...)` an toàn về mặt kiểu trong guard, vì `s` đã được gán từ một String thành công. Tuy nhiên, nếu pattern là record pattern với component có thể null, cần kiểm tra null cho **component đó** trước khi gọi phương thức (phần sau sẽ nhắc).

## 8. Guard có &&, ||: thứ tự ngắn mạch vẫn được áp dụng

Guard là một biểu thức Java có kiểu `boolean` hoặc `Boolean`; vì thế các toán tử `&&` và `||` giữ nguyên **short-circuit evaluation**.

Ví dụ:

~~~java
case String s when !s.isBlank() && s.length() >= 5 -> "LONG_TEXT";
~~~

Quy trình:

1. Pattern `String s` phải khớp.
2. Java tính `!s.isBlank()`.
3. Chỉ nếu vế trái true, Java mới tính `s.length() >= 5`.
4. Nếu kết quả guard cuối cùng true, case được chọn; nếu false, Java thử case tiếp theo.

Với guard dùng `||`:

~~~java
case String s when s.isBlank() || s.startsWith("#") -> "SPECIAL_TEXT";
~~~

Vế phải chỉ chạy khi `s.isBlank()` false. Các phép đánh giá ngắn mạch xảy ra **bên trong** guard; bản thân guard vẫn chỉ bắt đầu chạy sau khi **pattern String đã khớp**.

Tránh đưa phép tính nặng, có side effect hoặc làm biến đổi dữ liệu vào guard. Nếu một biểu thức đắt đỏ được gọi ở nhiều guard hoặc nhiều lượt switch, hiệu năng và tính dự đoán được có thể giảm. Nên dùng guard cho một **điều kiện boolean ngắn, rõ, ít tác dụng phụ**.

## 9. Guard false, guard ném ngoại lệ và Boolean null

Nhiều người chỉ xét true/false mà quên trường hợp guard **không hoàn tất bình thường**.

### 9.1. Guard false: tiếp tục tìm nhãn khác

~~~java
static String route(Object value) {
    return switch (value) {
        case String s when s.isEmpty() -> "EMPTY";
        case String s -> "NON_EMPTY";
        default -> "OTHER";
    };
}
~~~

Với `"abc"`, pattern String đầu khớp, guard `isEmpty()` trả false và case String thứ hai được chọn. Java không ném ngoại lệ chỉ vì một guard trả false.

### 9.2. Guard ném ngoại lệ: switch dừng bằng ngoại lệ

~~~java
static boolean fail(String text) {
    throw new IllegalStateException("invalid guard");
}

static String risky(Object value) {
    return switch (value) {
        case String s when fail(s) -> "A";
        case String s -> "B";
        default -> "OTHER";
    };
}
~~~

Đây là **mã minh họa hợp lệ khi đặt trong một class Java 21**. Với selector String, guard `fail(s)` ném ngoại lệ. Java **không** tự chuyển qua `case String s -> "B"`; ngoại lệ được truyền ra. Nếu selector là Integer, pattern String không khớp, `fail` **không được gọi** và nhánh default có thể chạy.

### 9.3. Guard kiểu Boolean bị null: lỗi khi unbox

Guard có thể có kiểu `Boolean`. Java sẽ **unbox** giá trị Boolean nhận được để quyết định true/false. Nếu Boolean là null, bước unbox gây `NullPointerException`. Đây **không** phải guard false.

Chương trình độc lập để thấy cả hai trường hợp, lưu thành **`GuardFailureDemo.java`**:

~~~java
public class GuardFailureDemo {

    static boolean explode(String text) {
        System.out.println("guard:throw");
        throw new IllegalStateException("guard failed");
    }

    static Boolean maybeNull(String text) {
        return null;
    }

    static String risky(Object input) {
        return switch (input) {
            case String s when explode(s) -> "MATCH";
            case String s -> "FALLBACK";
            default -> "OTHER";
        };
    }

    static String boxed(Object input) {
        return switch (input) {
            case String s when maybeNull(s) -> "TRUE";
            case String s -> "FALSE";
            default -> "OTHER";
        };
    }

    public static void main(String[] args) {
        try {
            System.out.println(risky("text"));
        } catch (IllegalStateException ex) {
            System.out.println(ex.getMessage());
        }

        System.out.println(risky(42));

        try {
            System.out.println(boxed("abc"));
        } catch (NullPointerException ex) {
            System.out.println("guard unboxing NPE");
        }
    }
}
~~~

~~~bash
javac GuardFailureDemo.java
java GuardFailureDemo
~~~

Đầu ra:

~~~text
guard:throw
guard failed
OTHER
guard unboxing NPE
~~~

Giải thích:

- `risky("text")`: khớp String, gọi `explode`; ngoại lệ được catch **bên ngoài** switch.
- `risky(42)`: không khớp String; guard `explode` không chạy; default trả `OTHER`.
- `boxed("abc")`: khớp String, guard trả một `Boolean` null; unboxing gây NPE; case String dự phòng **không chạy**.

Nếu giá trị Boolean có thể null, nên xử lý rõ trong guard, chẳng hạn `Boolean.TRUE.equals(maybeNull(s))`, thay vì để Java tự unbox null. Chọn hành vi false, exception hay báo lỗi riêng tùy yêu cầu nghiệp vụ.

## 10. Guard và null selector

Trong Java 21, `switch` hỗ trợ nhãn `case null`:

~~~java
static String inspect(Object value) {
    return switch (value) {
        case null -> "NULL";
        case String s when s.isBlank() -> "BLANK";
        case String s -> "TEXT";
        default -> "OTHER";
    };
}
~~~

Khi `value == null`:

- `case null` nhận selector.
- Guard `s.isBlank()` **không được gọi** vì không có một String nào khớp với `String s` ở đầu vào null.
- Nếu không có nhãn xử lý null phù hợp, một switch trên reference selector có thể ném `NullPointerException`; `default` thường **không tự bắt null** trong Java 21.

Không viết `case null when ...` như thể `null` là một type pattern có thể gắn guard. Trong Java 21, `when` gắn với **case pattern**, không phải với nhãn constant/null thông thường.

Khi muốn xử lý null có điều kiện đặc biệt, cách rõ ràng nhất là xử lý `case null` (hoặc kiểm tra null trước switch), rồi dùng `when` cho các pattern không null.

## 11. Record pattern, component null và thời điểm guard

Trong Java 21, record pattern giải cấu trúc một đối tượng record:

~~~java
record Payment(String currency, int amount) {}

static String label(Object value) {
    return switch (value) {
        case Payment(String currency, int amount)
                when currency != null
                        && currency.equals("USD")
                        && amount >= 100
                -> "LARGE_USD";
        case Payment p -> "OTHER_PAYMENT";
        default -> "OTHER";
    };
}
~~~

Đây là **mã minh họa**; đặt record và phương thức trong class Java 21.

Điều kiện `when` chỉ được đánh giá **sau khi** pattern `Payment(String currency, int amount)` khớp và biến component đã có giá trị. Trường hợp một component là null **không tương đương** toàn bộ selector là null:

- Một `Payment` thật sự có thể chứa `currency == null`. Với record pattern phù hợp, guard vẫn có thể bắt đầu chạy; phép `currency != null && ...` ngăn việc gọi `equals` trên null.
- Nếu selector ngoài cùng là null, không có record `Payment` để khớp, nên guard của case Payment không chạy.
- Nếu một component pattern lồng nhau không khớp, guard của case đó cũng không chạy.

Không suy ra “có pattern variable trong guard nên mọi biến component đều không null”. Quy tắc null của **component patterns** có khác biệt so với type pattern kiểm tra trực tiếp bằng `instanceof`; thiết kế guard vẫn cần phù hợp kiểu dữ liệu thực.

## 12. Guard không làm Java bỏ qua các lỗi compile time khác

Một guard chỉ can thiệp vào việc chọn case **khi chạy**; nó không thể biến một nhãn sai thành hợp lệ.

### 12.1. Dominance: thứ tự case đặc thù trước tổng quát

Mã cố ý lỗi:

~~~java
return switch (value) {
    case String s -> "ALL_STRINGS";
    case String s when s.isBlank() -> "BLANK"; // COMPILE ERROR
    default -> "OTHER";
};
~~~

Case String đầu đã bao phủ tất cả String. Nhánh có guard phía sau **bị che** (*dominated*), dù guard có thể true với một số chuỗi. Cách đúng:

~~~java
return switch (value) {
    case String s when s.isBlank() -> "BLANK";
    case String s -> "OTHER_STRING";
    default -> "OTHER";
};
~~~

Cả hai đoạn là **mảnh phương thức switch minh họa**, cần đặt trong class/phương thức phù hợp. Với `when true` — một guard hằng đúng — Java xem nhãn có hành vi tương tự nhãn không guard trong các quy tắc dominance; không nên dựa vào guard hằng đúng để né kiểm tra nhãn bị che.

### 12.2. Applicability: kiểu pattern phải phù hợp selector

Nếu selector có kiểu tĩnh `String`, không được thêm `case Integer n when n > 0` chỉ vì một guard sẽ “không bao giờ chạy”. Java phải chứng minh pattern applicable ở compile time trước. Thêm `when` không sửa được sự không tương thích kiểu.

### 12.3. Exhaustiveness: guard không tự bao phủ mọi giá trị

Với switch expression, compiler yêu cầu các nhãn bao phủ mọi giá trị có thể nhận. Một nhãn có guard phụ thuộc runtime có thể trả false, nên **không thể tùy tiện coi nó bao phủ tất cả**:

~~~java
// CỐ Ý KHÔNG ĐẦY ĐỦ
static String incomplete(Object value) {
    return switch (value) {
        case String s when s.length() > 0 -> "NONEMPTY";
        // Không có case String s dự phòng hoặc default.
    };
}
~~~

Sửa bằng một case String không guard và một `default` (hoặc dùng bộ patterns đầy đủ phù hợp loại selector).

**Cần tách ba câu hỏi:** pattern applicable không? các case có bị dominated không? switch exhaustive không? Thời điểm đánh giá guard ở runtime chỉ là câu hỏi thứ tư; cả bốn đều quan trọng.

## 13. Hiệu năng và side effects: guard được gọi bao nhiêu lần?

Trong một lượt chọn case:

- Guard của nhãn có pattern **không khớp**: **0 lần**.
- Guard của nhãn pattern khớp và được thử: **1 lần** cho lượt thử nhãn đó.
- Một nhãn guard false có thể dẫn đến **nhiều guard khác nhau** được thử tiếp.
- Khi một case được chọn, các nhãn phía sau không cần được đánh giá để chọn case.
- Khi switch được thực thi **một lần nữa** trong vòng lặp/phương thức khác, các guard có thể lại được thực thi.

Vì guard là biểu thức Java bình thường, nó **có thể** gọi phương thức, đọc trạng thái hoặc có side effect. Nhưng cách viết như sau thường khó dự đoán:

~~~java
case String s when auditAndMutateState(s) -> "ACCEPT";
~~~

Nếu `auditAndMutateState` thay đổi trạng thái toàn cục, hành vi có thể phụ thuộc vào **số lần và thứ tự** các guard được thử, rất khó kiểm thử. Cách viết an toàn hơn:

~~~java
case String s when s.length() >= 4 -> "ACCEPT";
~~~

Rồi đặt các thao tác tạo side effect vào **thân case đã được chọn** (hoặc xử lý tách riêng) khi thật sự cần. Guard thuần túy là điều kiện quyết định nhãn sẽ giúp code dễ review và dễ bảo trì hơn.

Đừng nhầm “selector được đánh giá một lần” với “toàn bộ kiểm tra chỉ chạy một lần”. Các pattern/guard khác nhau có thể lần lượt được thử trên **cùng giá trị selector**.

## 14. Khi kết hợp với switch statement và switch expression

Quy tắc thời điểm đánh giá guard **giống nhau** trong cả hai cấu trúc Java 21:

**Switch expression** trả về giá trị:

~~~java
static String asExpression(Object value) {
    return switch (value) {
        case String s when s.length() >= 4 -> "LONG";
        case String s -> "SHORT";
        default -> "OTHER";
    };
}
~~~

**Switch statement** thực hiện hiệu ứng:

~~~java
static void asStatement(Object value) {
    switch (value) {
        case String s when s.length() >= 4
                -> System.out.println("LONG");
        case String s -> System.out.println("SHORT");
        default -> System.out.println("OTHER");
    }
}
~~~

Cả hai đều: **thử pattern → tính guard nếu khớp → chọn case nếu guard true**. Điểm khác nằm ở mục đích: switch expression tạo ra giá trị, còn switch statement chạy các câu lệnh.

Trong một switch expression dùng block, từ khóa `yield` cho giá trị **sau khi case đã được chọn**:

~~~java
return switch (value) {
    case String s when s.length() >= 4 -> {
        String cleaned = s.strip();
        yield "LONG:" + cleaned;
    }
    case String s -> "SHORT";
    default -> "OTHER";
};
~~~

`yield` không tham gia quyết định guard có chạy hay không; nó là phần xử lý **bên trong nhánh đã chọn**.

## 15. Lỗi phổ biến và cách tránh

| Ngộ nhận / lỗi | Sự thật | Cách làm đúng |
| --- | --- | --- |
| Guard được kiểm tra với mọi giá trị selector | Guard chỉ chạy khi pattern của **chính case đó** khớp | Đặt việc kiểm tra chung trước switch nếu cần |
| Guard chạy trước khi biến mẫu được gán | Pattern khớp và khởi tạo biến trước, guard mới chạy | Dùng biến mẫu trực tiếp trong `when` |
| Guard false nghĩa là chạy default ngay | Java tiếp tục xét các case tiếp theo | Đặt case dự phòng đúng thứ tự |
| Guard false giống if false bên trong case | Guard false loại case khỏi lựa chọn; if trong case chỉ điều khiển nhánh đã chọn | Chọn cấu trúc phù hợp ý định |
| Mỗi switch chỉ tính tối đa một guard | Nhiều case guard có thể lần lượt được đánh giá | Tránh kiểm tra nặng lặp lại |
| Guard ném ngoại lệ thì case sau vẫn chạy | Ngoại lệ dừng quá trình chọn nhãn | Xử lý ngoại lệ rõ ràng nếu cần |
| `Boolean` null trong guard là false | Unboxing null ném NPE | Dùng `Boolean.TRUE.equals(...)` khi hợp lý |
| Đặt `case String s` trước guard String đặc thù | Case sau bị dominance | Đặt case đặc thù trước case tổng quát |
| `when` áp dụng được cho `case null` | `when` là phần của guarded pattern label | Xử lý null qua `case null` |
| Thêm `when` để pattern không tương thích vẫn biên dịch | Applicability là điều kiện compile time độc lập | Sửa kiểu selector/pattern |
| Guard làm switch tự exhaustive | Guard có thể false, không bao phủ toàn bộ | Bổ sung nhãn không guard/default |
| Selector bị gọi lại mỗi khi thử guard sau | Selector được đánh giá một lần cho một switch | Phân biệt selector với từng phép matching/guard |

## 16. Tự kiểm tra

**Câu 1.** Với `Object x = 42;`, case `case String s when expensive(s) -> ...` có gọi `expensive` không?

**Đáp án:** Không. `Integer` không khớp `String s`; Java không đánh giá guard.

**Câu 2.** Với `x = "ab"`, điều gì xảy ra?

~~~java
return switch (x) {
    case String s when s.length() > 3 -> "LONG";
    case String s when s.length() > 0 -> "TEXT";
    case String s -> "EMPTY";
    default -> "OTHER";
};
~~~

**Đáp án:** Guard đầu được đánh giá và false; guard thứ hai được đánh giá và true; kết quả `TEXT`. Không chạy case String thứ ba.

**Câu 3.** `when s.length() > 0` chạy trước hay sau khi pattern `String s` khớp?

**Đáp án:** Sau. Biến `s` đã được khởi tạo từ kết quả matching rồi guard mới được đánh giá.

**Câu 4.** Khi guard gọi phương thức ném `IllegalStateException`, switch tự chọn case sau hay không?

**Đáp án:** Không. Quá trình chọn nhãn hoàn tất đột ngột bằng ngoại lệ; không được hiểu thành guard false.

**Câu 5.** Nếu `source()` là biểu thức selector và case guard đầu false, `source()` bị gọi lần nữa cho case thứ hai không?

**Đáp án:** Không trong cùng một lượt thực thi switch. Giá trị selector đã được tính một lần; Java thử các case với giá trị đó.

**Câu 6.** Với `when Boolean.TRUE.equals(flag)` và `flag == null`, guard có gây NPE khi tự unbox null không?

**Đáp án:** Không. `Boolean.TRUE.equals(null)` trả false, nên guard false và Java có thể xét case tiếp theo. Điều này khác viết `when flag` nếu `flag` là `Boolean` null: trường hợp đó cần unbox và có thể ném NPE.

## 17. Tài liệu chính thức

Các điểm chính dựa trên **Java Language Specification 21** và tài liệu Oracle:

- [JLS `14.11.1.2 — Determining which Switch Label Applies at Run Time](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.11.1.2): selector, matching, thời điểm guard được đánh giá, unboxing, kết quả true và ngoại lệ.
- [JLS `14.11.1 — Switch Blocks](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.11.1): nhãn case, dominance, exhaustiveness.
- [JLS `14.30.2 — Pattern Matching](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.30.2): cách một giá trị khớp pattern và khởi tạo pattern variables.
- [JLS `15.28 — switch Expressions](https://docs.oracle.com/javase/specs/jls/se21/html/jls-15.html#jls-15.28): quy tắc chọn case và tạo kết quả từ switch expression.
- [Oracle Java 21 — When Clauses](https://docs.oracle.com/en/java/javase/21/language/pattern-matching-switch.html): cú pháp `p when e` và phạm vi biến mẫu trong guard.
- [JEP 441 — Pattern Matching for switch](https://openjdk.org/jeps/441): lịch sử chuẩn hóa pattern switch ở Java 21.

**Kết luận cần nhớ:** Trong `switch` có pattern của Java 21, Java **thử pattern trước**. Chỉ khi nó khớp thì mới **đánh giá `when`**. Guard true chọn case; guard false cho phép thử case tiếp theo; guard ném ngoại lệ khiến switch kết thúc bằng ngoại lệ. Selector được tính một lần trong mỗi lượt switch, nhưng có thể có nhiều pattern và guard được xét lần lượt.
