# So sánh bằng `==` và sử dụng enum trong `switch` — Java 17+

Trong Java, `enum` mô tả **một tập hằng có tên được định nghĩa trước, có kiểu rõ ràng**. Khi một biến có kiểu `OrderStatus`, nó chỉ có thể tham chiếu một trong các hằng của chính enum ấy hoặc mang giá trị `null`. Mỗi hằng enum là một **đối tượng** được Java tạo theo định nghĩa enum, và cùng một hằng luôn chỉ tới cùng một đối tượng trong phạm vi một lần định nghĩa runtime của enum. Vì vậy, **`==` là cách so sánh tự nhiên và an toàn** khi muốn biết hai biến có đại diện cho **cùng một hằng enum** hay không.

Một lợi ích khác: enum là loại selector được `switch` hỗ trợ trực tiếp. Thay vì `if/else` so chuỗi như `"NEW"`, `"PAID"`, bạn có thể rẽ nhánh theo `OrderStatus.NEW`, `OrderStatus.PAID` với compiler kiểm tra kiểu và các nhãn `case`. Với Java 17, có **switch statement** truyền thống, dạng `case ... ->`, và **switch expression** trả về giá trị.

Bài thuộc module **Java core – class-object**, nhóm **Enum**, mục **So sánh bằng == và sử dụng enum trong switch**. Các ví dụ dùng Java **17+**, ghi rõ tệp, lệnh chạy và stdout tương ứng. Các đoạn cố tình sai được ghi rõ là **minh họa lỗi biên dịch**, không được hiểu là chương trình chạy được.

## 1. Bản chất đối tượng của hằng enum

Khai báo:

~~~java
enum OrderStatus {
    NEW, PROCESSING, PAID, CANCELLED
}
~~~

Đây là một khai báo kiểu hợp lệ. `NEW`, `PROCESSING`, `PAID`, `CANCELLED` là những **enum constants** thuộc **kiểu OrderStatus**. Chúng không phải những chuỗi ký tự và không phải số nguyên được compiler tự thay bằng `0`, `1`, `2`.

Có thể viết:

~~~java
OrderStatus a = OrderStatus.NEW;
OrderStatus b = OrderStatus.NEW;
OrderStatus c = OrderStatus.PAID;
~~~

Đây là snippet hợp lệ sau khai báo enum, đặt trong method hoặc initializer phù hợp. `a` và `b` tham chiếu **cùng một hằng**; `c` tham chiếu hằng khác. Cả ba biến có kiểu OrderStatus.

Java không cho chương trình tùy tiện `new OrderStatus()` để tạo thêm một hằng bên ngoài khai báo. Hợp đồng enum giữ tập hằng được định nghĩa trong source, ngoại trừ khả năng biến reference có giá trị `null`.

## 2. Vì sao dùng `==` với enum?

Toán tử `==` trên các reference có nghĩa **cùng một object reference**. Đối với enum, mỗi hằng có identity ổn định trong runtime enum class tương ứng nên:

- `OrderStatus.NEW == OrderStatus.NEW` là `true`.
- `OrderStatus.NEW == OrderStatus.PAID` là `false`.
- Hai biến trỏ `OrderStatus.NEW` cho kết quả `true` dù được gán ở hai nơi khác nhau.
- `status == null` hợp lệ và không gọi method nào trên `status`.
- So sánh hằng với biến `null`, như `status == OrderStatus.NEW`, trả `false`, **không ném NullPointerException**.

Khác với String, bạn **không cần cân nhắc nội dung chuỗi hoặc string interning** để quyết định hai enum constants có giống nhau không.

**Quy ước gợi ý:** viết `if (status == OrderStatus.PAID)` khi cần kiểm tra một giá trị enum. Dạng `OrderStatus.PAID == status` cũng đúng, kể cả khi status null; chọn một kiểu viết nhất quán trong dự án.

## 3. Chương trình hoàn chỉnh 1 — identity và `==`

Tệp **`EnumIdentityDemo.java`**:

~~~java
enum OrderStatus {
    NEW, PROCESSING, PAID, CANCELLED
}

public class EnumIdentityDemo {
    public static void main(String[] args) {
        OrderStatus first = OrderStatus.NEW;
        OrderStatus second = OrderStatus.NEW;
        OrderStatus paid = OrderStatus.PAID;

        System.out.println("first=" + first);
        System.out.println("same=" + (first == second));
        System.out.println("different=" + (first == paid));
        System.out.println("same type="
                + (first.getClass() == paid.getClass()));

        OrderStatus unknown = null;
        System.out.println("null is NEW="
                + (unknown == OrderStatus.NEW));
        System.out.println("null is null=" + (unknown == null));
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac -encoding UTF-8 EnumIdentityDemo.java
java EnumIdentityDemo
~~~

**Stdout chính xác:**

~~~text
first=NEW
same=true
different=false
same type=true
null is NEW=false
null is null=true
~~~

`first` và `second` cùng tham chiếu OrderStatus.NEW; `paid` tham chiếu hằng khác. `getClass()` trả về cùng runtime class vì enum này không có constant-specific class bodies. Dòng so sánh null minh họa ưu thế của `==`: không cần gọi method trên reference có thể null.

**Giới hạn của phát biểu identity:** mỗi enum class được nạp bởi một class loader có một bộ enum constants tương ứng. Trong những hệ thống có nhiều class loaders, đừng giả định chỉ cần trùng *tên văn bản* là hai hằng thuộc cùng một runtime type. Trong code Java thông thường với cùng một enum type, `==` là lựa chọn đúng.

## 4. `equals` với enum: kết quả giống nhau khi reference không null

`java.lang.Enum` đã có implementation `equals(Object)` dựa trên **reference identity**, và method này là `final`: enum của bạn không được override nó để thay nghĩa equality.

Do đó, khi `a` không null:

~~~java
a == b
a.equals(b)
~~~

thường có kết quả boolean giống nhau cho các enum references cùng kiểu. Nhưng **`a.equals(b)` gọi method trên a**, nên nếu `a == null` thì ném `NullPointerException`, trong khi `a == b` vẫn là một phép so sánh reference hợp lệ.

Các kiểu so sánh này trả lời câu hỏi **“có cùng hằng enum không?”**. Chúng không so các thuộc tính nghiệp vụ mà bạn có thể gắn với enum, như mã hiển thị, mô tả hoặc mức phí.

Vì sao không cần ghi `Enum.valueOf(...)` hoặc `name().equals(...)` để so sánh? Vì những thao tác đó biến hoặc đọc **tên**, còn bạn đã có những object enum cùng kiểu để so trực tiếp.

## 5. Chương trình hoàn chỉnh 2 — `==`, `equals`, và `null`

Tệp **`EnumEqualsNullDemo.java`**:

~~~java
enum Level {
    LOW, MEDIUM, HIGH
}

public class EnumEqualsNullDemo {
    public static void main(String[] args) {
        Level a = Level.HIGH;
        Level b = Level.HIGH;
        Level c = Level.LOW;

        System.out.println("a==b=" + (a == b));
        System.out.println("a.equals(b)=" + a.equals(b));
        System.out.println("a==c=" + (a == c));
        System.out.println("a.equals(c)=" + a.equals(c));

        Level missing = null;
        System.out.println("missing==HIGH="
                + (missing == Level.HIGH));
        System.out.println("HIGH.equals(missing)="
                + Level.HIGH.equals(missing));

        try {
            System.out.println(missing.equals(Level.HIGH));
        } catch (NullPointerException ex) {
            System.out.println("missing.equals throws="
                    + ex.getClass().getSimpleName());
        }
    }
}
~~~

Chạy:

~~~bash
javac -encoding UTF-8 EnumEqualsNullDemo.java
java EnumEqualsNullDemo
~~~

**Stdout:**

~~~text
a==b=true
a.equals(b)=true
a==c=false
a.equals(c)=false
missing==HIGH=false
HIGH.equals(missing)=false
missing.equals throws=NullPointerException
~~~

`Level.HIGH.equals(missing)` an toàn vì receiver là hằng enum không null. Tuy vậy khi cả hai biến vốn là enum, `==` ngắn gọn hơn và không tạo ra nguy cơ gọi method trên biến null.

## 6. Không nhầm so enum với so String

Xét hai lựa chọn thiết kế:

~~~java
String statusText = "PAID";
OrderStatus status = OrderStatus.PAID;
~~~

Đây là snippet trong phạm vi có enum OrderStatus. Hai biến không cùng kiểu: một biến là String, biến kia là OrderStatus.

- String mô tả **text**; so nội dung String bằng `equals` hoặc `Objects.equals`.
- Enum mô tả một **hằng typed**; so cùng hằng bằng `==`.
- `OrderStatus.PAID.name()` trả String `"PAID"`, nhưng String ấy không phải object OrderStatus.PAID.
- Không chuyển enum sang String chỉ để viết `if ("PAID".equals(status.name()))` khi đã có enum reference; cách đó dài hơn và có thể gây NullPointerException nếu status null.
- Nếu dữ liệu **đầu vào là text** từ JSON, file hoặc request, chuyển đổi một lần theo chính sách input rồi làm việc với enum trong domain code.

Ví dụ: `OrderStatus.valueOf("PAID")` trả OrderStatus.PAID; `valueOf("paid")` không tự bỏ qua chữ hoa/chữ thường, và input không trùng tên sẽ gây `IllegalArgumentException`. Việc chuẩn hóa đầu vào là trách nhiệm API tiếp nhận dữ liệu, không phải phép so sánh enum.

## 7. Chương trình hoàn chỉnh 3 — parse text rồi so hằng

Tệp **`EnumParsingComparisonDemo.java`**:

~~~java
import java.util.Locale;

enum Access {
    GUEST, MEMBER, ADMIN
}

public class EnumParsingComparisonDemo {
    static Access parse(String raw) {
        if (raw == null) {
            throw new IllegalArgumentException("missing access");
        }
        return Access.valueOf(
                raw.trim().toUpperCase(Locale.ROOT));
    }

    public static void main(String[] args) {
        Access fromText = parse(" admin ");
        System.out.println("parsed=" + fromText);
        System.out.println("is admin="
                + (fromText == Access.ADMIN));

        try {
            parse("owner");
        } catch (IllegalArgumentException ex) {
            System.out.println("invalid="
                    + ex.getClass().getSimpleName());
        }
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac -encoding UTF-8 EnumParsingComparisonDemo.java
java EnumParsingComparisonDemo
~~~

**Stdout:**

~~~text
parsed=ADMIN
is admin=true
invalid=IllegalArgumentException
~~~

Hàm parse chủ động quyết định xử lý whitespace/case. Sau khi có Access.ADMIN, chương trình so hằng với `==`, không tiếp tục so strings. Với hệ thống thật, cân nhắc versioning của external codes: `name()` thích hợp cho identity nội bộ nhưng không phải luôn là mã tích hợp bên ngoài ổn định.

## 8. `switch` trên enum giúp kiểm tra kiểu của nhánh

Java cho phép dùng một enum expression làm selector:

~~~java
switch (status) {
    case NEW:
        System.out.println("New");
        break;
    case PAID:
        System.out.println("Paid");
        break;
    default:
        System.out.println("Other");
}
~~~

Đây là snippet hợp lệ khi status là biến có kiểu OrderStatus. Trong `case NEW:`, tên enum constant được viết **không kèm `OrderStatus.`** theo cú pháp enum case labels thông thường của Java 17. Java biết selector có kiểu OrderStatus nên phân giải `NEW` là hằng tương ứng.

**Khác với so bằng `==`:** `switch` dùng selector để chọn **một đường điều khiển**, thuận tiện khi có nhiều nhánh. Bạn vẫn có thể dùng `if (status == OrderStatus.NEW)` cho một hoặc hai điều kiện đơn giản.

Không viết `case "NEW":` nếu selector là OrderStatus; String literal không phải enum constant. Cũng không đặt trực tiếp `case OrderStatus.NEW:` trong enum switch theo quy tắc case labels Java 17 thông thường.

## 9. Switch statement truyền thống: cần hiểu `break`

Cú pháp colon `case X:` của **switch statement** hỗ trợ **fall-through**: nếu một nhánh được chọn mà không có `break`, `return`, `throw` hoặc cơ chế thoát khác, việc thực thi có thể đi tiếp vào phần statements của nhãn case kế tiếp.

Ví dụ:

~~~java
switch (status) {
    case NEW:
        System.out.println("Create");
        break;
    case PROCESSING:
        System.out.println("In progress");
        break;
    case PAID:
        System.out.println("Completed");
        break;
    case CANCELLED:
        System.out.println("Stopped");
        break;
}
~~~

Đây là switch statement minh họa hợp lệ trong method có selector OrderStatus. Không nhất thiết phải có `default` nếu bạn chủ động liệt kê mọi trường hợp và không cần hành vi mặc định. Tuy nhiên với **switch statement**, compiler không buộc mọi hằng enum phải có case label như khi dùng **switch expression**.

Một switch statement có thể không chạy nhánh nào khi thiếu case phù hợp và không có default. Vì vậy nếu rẽ nhánh biểu diễn hành vi bắt buộc, nên xem xét một đường xử lý rõ cho mọi hằng.

## 10. Chương trình hoàn chỉnh 4 — switch statement và `break`

Tệp **`EnumSwitchStatementDemo.java`**:

~~~java
enum Ticket {
    OPEN, ASSIGNED, RESOLVED, CLOSED
}

public class EnumSwitchStatementDemo {
    static void printAction(Ticket ticket) {
        switch (ticket) {
            case OPEN:
                System.out.println("create task");
                break;
            case ASSIGNED:
                System.out.println("work on task");
                break;
            case RESOLVED:
                System.out.println("verify result");
                break;
            case CLOSED:
                System.out.println("archive");
                break;
        }
    }

    public static void main(String[] args) {
        printAction(Ticket.OPEN);
        printAction(Ticket.RESOLVED);
        printAction(Ticket.CLOSED);
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac -encoding UTF-8 EnumSwitchStatementDemo.java
java EnumSwitchStatementDemo
~~~

**Stdout:**

~~~text
create task
verify result
archive
~~~

Hàm `printAction` là `void`: nó thực hiện một hành động phụ là in kết quả, không trả một giá trị. Mỗi case có `break` nên chỉ in nhánh được chọn, không chảy sang nhánh kế.

## 11. Gom nhiều enum constants vào cùng một nhánh

Khi nhiều trạng thái cần cùng hành vi, bạn có thể nhóm nhãn trong switch statement dạng colon:

~~~java
switch (status) {
    case NEW:
    case PROCESSING:
        System.out.println("Not finished");
        break;
    case PAID:
    case CANCELLED:
        System.out.println("Finalized");
        break;
}
~~~

Đây là snippet hợp lệ với OrderStatus. Nhiều nhãn case liên tiếp **không có statements nằm giữa** thể hiện chủ ý chia sẻ code, không phải lỗi quên `break`.

Với Java 17, dạng arrow thường gọn hơn:

~~~java
switch (status) {
    case NEW, PROCESSING -> System.out.println("Not finished");
    case PAID, CANCELLED -> System.out.println("Finalized");
}
~~~

Cú pháp `case NEW, PROCESSING ->` liệt kê nhiều hằng enum trong một nhãn; không gây fall-through giữa các nhánh arrow.

**Ghi nhớ:** gom nhãn có chủ đích khác với quên `break` giữa hai nhánh mang hành vi khác nhau.

## 12. Chương trình hoàn chỉnh 5 — grouped cases dạng arrow

Tệp **`EnumGroupedCasesDemo.java`**:

~~~java
enum Shipment {
    CREATED, PACKED, SHIPPED, DELIVERED, RETURNED
}

public class EnumGroupedCasesDemo {
    static String phase(Shipment shipment) {
        return switch (shipment) {
            case CREATED, PACKED -> "Preparing";
            case SHIPPED -> "In transit";
            case DELIVERED, RETURNED -> "Finished";
        };
    }

    public static void main(String[] args) {
        System.out.println("CREATED="
                + phase(Shipment.CREATED));
        System.out.println("SHIPPED="
                + phase(Shipment.SHIPPED));
        System.out.println("RETURNED="
                + phase(Shipment.RETURNED));
    }
}
~~~

Chạy:

~~~bash
javac -encoding UTF-8 EnumGroupedCasesDemo.java
java EnumGroupedCasesDemo
~~~

**Stdout:**

~~~text
CREATED=Preparing
SHIPPED=In transit
RETURNED=Finished
~~~

Đây là **switch expression**, không phải statement: method trả ngay String do expression tính ra. Tất cả năm hằng Shipment đều được bao phủ, nên không cần nhánh `default`.

## 13. Dạng arrow của switch statement: không fall-through

Java 17 cho phép viết **switch statement** bằng các switch rules dạng `case CONSTANT -> statement`. Ví dụ:

~~~java
switch (status) {
    case NEW -> System.out.println("Created");
    case PROCESSING -> System.out.println("Working");
    case PAID -> System.out.println("Finished");
    case CANCELLED -> System.out.println("Cancelled");
}
~~~

Đây là **statement** vì kết quả được dùng để thực hiện các lệnh in, không phải một expression gán/trả giá trị. Arrow `->` đảm bảo một rule được chọn không tự động thực thi body rule kế tiếp.

Nếu một rule cần nhiều statements, dùng một block:

~~~java
switch (status) {
    case NEW -> {
        System.out.println("validate");
        System.out.println("accept");
    }
    case PROCESSING, PAID, CANCELLED ->
            System.out.println("already recorded");
}
~~~

Đoạn này cũng là switch statement hợp lệ. **Không dùng `yield` tùy ý để trả về giá trị từ statement**; `yield` là cơ chế cung cấp giá trị từ block trong switch expression. Nếu method cần một kết quả, chuyển sang switch expression hoặc dùng một return theo quy tắc method thông thường.

## 14. Switch expression: lấy một giá trị từ enum

Khi yêu cầu là **ánh xạ một enum thành một giá trị**, switch expression thường ngắn, rõ và giúp compiler kiểm tra tính đầy đủ:

~~~java
int fee = switch (tier) {
    case BASIC -> 0;
    case PLUS -> 20;
    case PREMIUM -> 50;
};
~~~

Đây là snippet Java 17 hợp lệ nếu `tier` có kiểu enum với đúng ba hằng BASIC, PLUS, PREMIUM.

Các khác biệt với switch statement truyền thống:

- **Expression** tạo một giá trị có kiểu, ở đây là `int`.
- Mỗi nhánh có thể là expression, block với `yield`, hoặc `throw`.
- Expression phải **exhaustive**: mọi giá trị selector hợp lệ phải được bao phủ; với enum, các case cho toàn bộ constants đáp ứng điều kiện này mà không cần default.
- Dạng `->` không fall-through.
- `break` của switch statement không được dùng để cung cấp giá trị thay cho `yield` ở switch expression.

Với `default`, compiler có một nhánh tổng quát; nhưng thêm default vô điều kiện có thể che mất cơ hội compiler nhắc bạn cập nhật biểu thức khi enum được thêm hằng mới.

## 15. Chương trình hoàn chỉnh 6 — ánh xạ enum thành giá trị

Tệp **`EnumSwitchExpressionDemo.java`**:

~~~java
enum Subscription {
    FREE, STANDARD, BUSINESS
}

public class EnumSwitchExpressionDemo {
    static int monthlyFee(Subscription subscription) {
        return switch (subscription) {
            case FREE -> 0;
            case STANDARD -> 99;
            case BUSINESS -> 249;
        };
    }

    static String description(Subscription subscription) {
        return switch (subscription) {
            case FREE -> "Starter";
            case STANDARD -> "Personal";
            case BUSINESS -> "Team";
        };
    }

    public static void main(String[] args) {
        System.out.println("FREE="
                + monthlyFee(Subscription.FREE));
        System.out.println("STANDARD="
                + monthlyFee(Subscription.STANDARD));
        System.out.println("BUSINESS="
                + monthlyFee(Subscription.BUSINESS));
        System.out.println("description="
                + description(Subscription.BUSINESS));
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac -encoding UTF-8 EnumSwitchExpressionDemo.java
java EnumSwitchExpressionDemo
~~~

**Stdout:**

~~~text
FREE=0
STANDARD=99
BUSINESS=249
description=Team
~~~

Các giá trị 99 và 249 chỉ là dữ liệu của ví dụ, không phải bảng giá ngoài đời. Với một hệ thống thương mại, chính sách giá có thể cần model riêng hoặc nguồn dữ liệu cấu hình; switch mapping phù hợp nhất với những quy tắc nhỏ, cố định theo enum.

## 16. Nhiều statements trong một rule: dùng block và `yield`

Một switch expression có thể tính kết quả từ nhiều dòng bằng `yield`:

~~~java
String text = switch (level) {
    case LOW -> "low";
    case MEDIUM -> {
        String prefix = "middle";
        yield prefix + " priority";
    }
    case HIGH -> "high";
};
~~~

Đây là snippet hợp lệ trong method có `Level` như ví dụ trước.

`yield expression;` **trả giá trị cho switch expression**, không phải `return` khỏi method đang chứa switch. Ví dụ nếu method đang tính một chuỗi cho nhiều hạng mục, `yield` chỉ hoàn tất biểu thức switch đó; các statements sau expression vẫn có thể chạy.

Các nhánh block cần bảo đảm mọi đường đi bình thường đều `yield` giá trị phù hợp hoặc kết thúc bằng `throw` khi có điều kiện lỗi. Không thể đi tới cuối block mà không cung cấp giá trị cho switch expression.

## 17. Chương trình hoàn chỉnh 7 — dùng `yield` trong switch expression

Tệp **`EnumSwitchYieldDemo.java`**:

~~~java
enum Risk {
    LOW, MEDIUM, HIGH
}

public class EnumSwitchYieldDemo {
    static String explain(Risk risk) {
        return switch (risk) {
            case LOW -> "No review";
            case MEDIUM -> {
                int checks = 2;
                yield "Review " + checks + " checks";
            }
            case HIGH -> {
                String action = "Escalate";
                yield action + " now";
            }
        };
    }

    public static void main(String[] args) {
        System.out.println("LOW=" + explain(Risk.LOW));
        System.out.println("MEDIUM=" + explain(Risk.MEDIUM));
        System.out.println("HIGH=" + explain(Risk.HIGH));
    }
}
~~~

Chạy:

~~~bash
javac -encoding UTF-8 EnumSwitchYieldDemo.java
java EnumSwitchYieldDemo
~~~

**Stdout:**

~~~text
LOW=No review
MEDIUM=Review 2 checks
HIGH=Escalate now
~~~

`MEDIUM` và `HIGH` dùng block vì cần khai báo biến cục bộ rồi xây dựng kết quả. `LOW` chỉ cần một expression nên arrow rule trực tiếp là đủ.

## 18. Bẫy fall-through ở dạng colon

Giả sử lập trình viên quên `break`:

~~~java
switch (step) {
    case STARTED:
        System.out.println("start");
    case VERIFIED:
        System.out.println("verify");
        break;
    case FINISHED:
        System.out.println("finish");
        break;
}
~~~

Đây là snippet Java 17 hợp lệ, nhưng nếu `step == STARTED`, nó in **hai dòng** `start` và `verify` vì không có `break` sau STARTED. Nếu muốn chỉ thực hiện một nhánh, hãy thêm `break` hoặc dùng arrow rules.

Đôi khi fall-through được dùng có chủ đích để gom nhánh, nhưng người mới đọc code dễ tưởng rằng mọi `case:` tự dừng khi hết statements. Điều đó **không đúng** với dạng colon truyền thống.

## 19. Chương trình hoàn chỉnh 8 — so sánh fall-through và arrow

Tệp **`EnumFallThroughDemo.java`**:

~~~java
enum Phase {
    STARTED, VERIFIED, FINISHED
}

public class EnumFallThroughDemo {
    static void colon(Phase phase) {
        switch (phase) {
            case STARTED:
                System.out.println("colon:start");
            case VERIFIED:
                System.out.println("colon:verify");
                break;
            case FINISHED:
                System.out.println("colon:finish");
                break;
        }
    }

    static void arrow(Phase phase) {
        switch (phase) {
            case STARTED ->
                    System.out.println("arrow:start");
            case VERIFIED ->
                    System.out.println("arrow:verify");
            case FINISHED ->
                    System.out.println("arrow:finish");
        }
    }

    public static void main(String[] args) {
        colon(Phase.STARTED);
        arrow(Phase.STARTED);
        colon(Phase.FINISHED);
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac -encoding UTF-8 EnumFallThroughDemo.java
java EnumFallThroughDemo
~~~

**Stdout:**

~~~text
colon:start
colon:verify
arrow:start
colon:finish
~~~

Ví dụ cố ý để lộ fall-through ở nhánh STARTED của method `colon`. Với code nghiệp vụ, đừng vô tình chuyển `case:` có `break` thành một nhánh không `break`, hoặc ngược lại, mà chưa kiểm tra hành vi kỳ vọng.

## 20. `null` và enum switch trong Java 17

Đây là một điểm rất dễ nhầm khi đã quen dùng `==`:

~~~java
OrderStatus status = null;

boolean isNew = (status == OrderStatus.NEW);
~~~

Hai dòng trên hợp lệ; `isNew` là false. **Nhưng switch bình thường trên selector null sẽ ném `NullPointerException`** trong Java 17 khi không dùng những tính năng preview đặc biệt.

Tức là:

- `status == OrderStatus.NEW` là phép so reference null-safe.
- `OrderStatus.NEW.equals(status)` là một lời gọi method hợp lệ, trả false.
- `status.equals(OrderStatus.NEW)` ném NPE nếu status null.
- `switch (status) { ... }` không tự chọn `default` cho null trong Java 17 dạng thông thường.
- `switch (status)` dưới dạng expression cũng không tự trả giá trị fallback khi status null.

**Cách xử lý:** xác lập invariant “status không null” bằng validation hoặc `Objects.requireNonNull`, hoặc chuẩn hóa null sang một hằng như `UNKNOWN` theo chính sách rõ ràng. Không biến null thành UNKNOWN vô điều kiện nếu nghiệp vụ phải phân biệt “thiếu dữ liệu” với “trạng thái thực sự không xác định”.

## 21. Chương trình hoàn chỉnh 9 — xử lý null trước switch

Tệp **`EnumNullSwitchDemo.java`**:

~~~java
import java.util.Objects;

enum State {
    READY, STOPPED, UNKNOWN
}

public class EnumNullSwitchDemo {
    static String message(State state) {
        State safe = Objects.requireNonNullElse(
                state, State.UNKNOWN);
        return switch (safe) {
            case READY -> "ready";
            case STOPPED -> "stopped";
            case UNKNOWN -> "unknown";
        };
    }

    static String strict(State state) {
        return switch (state) {
            case READY -> "ready";
            case STOPPED -> "stopped";
            case UNKNOWN -> "unknown";
        };
    }

    public static void main(String[] args) {
        State missing = null;

        System.out.println("null==READY="
                + (missing == State.READY));
        System.out.println("safe=" + message(missing));
        System.out.println("ready=" + message(State.READY));

        try {
            strict(missing);
        } catch (NullPointerException ex) {
            System.out.println("strict="
                    + ex.getClass().getSimpleName());
        }
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac -encoding UTF-8 EnumNullSwitchDemo.java
java EnumNullSwitchDemo
~~~

**Stdout chính xác:**

~~~text
null==READY=false
safe=unknown
ready=ready
strict=NullPointerException
~~~

Method `message` công khai chính sách null → UNKNOWN; method `strict` không làm vậy và sẽ ném NPE với null. Đây là hai quyết định API khác nhau, chứ không phải một cách viết đúng và một cách viết sai cho mọi dự án.

## 22. Đủ nhánh (exhaustiveness) khi viết switch expression

Giả sử enum có ba hằng:

~~~java
enum Direction {
    NORTH, SOUTH, EAST
}
~~~

Switch expression phải bao phủ tất cả. Ví dụ:

~~~java
String code = switch (direction) {
    case NORTH -> "N";
    case SOUTH -> "S";
    case EAST -> "E";
};
~~~

Đây là snippet hợp lệ khi `direction` có kiểu Direction. Không bắt buộc `default` vì mọi hằng đã được nêu.

Nếu bỏ `case EAST` và vẫn không có `default`, **switch expression không exhaustive và compiler báo lỗi**. Ngược lại, switch statement thiếu case có thể vẫn biên dịch, nhưng không thực hiện hành vi cho những hằng bị bỏ sót.

**Khi thêm một hằng enum mới:** nếu biên dịch lại source có một switch expression không có default và chưa xử lý hằng mới, compiler có thể buộc cập nhật switch, rất có ích khi refactor domain states. Việc phối hợp binary class files biên dịch ở các thời điểm khác nhau có các quy tắc runtime khác; nên build và test đồng bộ các modules thay vì giả định an toàn khi enum đổi mà consumer chưa được rebuild.

## 23. Chương trình hoàn chỉnh 10 — biểu thức exhaustive, statement có default

Tệp **`EnumExhaustivenessDemo.java`**:

~~~java
enum Direction {
    NORTH, SOUTH, EAST, WEST
}

public class EnumExhaustivenessDemo {
    static String code(Direction direction) {
        return switch (direction) {
            case NORTH -> "N";
            case SOUTH -> "S";
            case EAST -> "E";
            case WEST -> "W";
        };
    }

    static void describe(Direction direction) {
        switch (direction) {
            case NORTH, SOUTH ->
                    System.out.println("vertical");
            case EAST, WEST ->
                    System.out.println("horizontal");
        }
    }

    public static void main(String[] args) {
        System.out.println("code=" + code(Direction.WEST));
        describe(Direction.NORTH);
        describe(Direction.EAST);
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac -encoding UTF-8 EnumExhaustivenessDemo.java
java EnumExhaustivenessDemo
~~~

**Stdout:**

~~~text
code=W
vertical
horizontal
~~~

Switch expression `code` liệt kê đủ bốn constants và tạo String. Switch statement `describe` dùng nhóm arrow cases để thực hiện tác dụng phụ in ra màn hình; cả hai đều tránh fall-through.

## 24. Có nên luôn thêm `default`?

Không có quy tắc “switch trên enum phải luôn có default”. Quyết định phụ thuộc mục tiêu:

**Muốn compiler buộc xét đủ trạng thái khi enum thay đổi:** với switch expression nhỏ và đóng theo domain, hãy cân nhắc **liệt kê từng hằng không có default**. Việc thêm hằng mới sẽ làm thiếu exhaustiveness khi biên dịch lại.

**Muốn một fallback thực sự được quy định bởi nghiệp vụ:** dùng `default` là hợp lý, ví dụ một policy coi mọi trạng thái chưa phân nhóm là “other”, miễn hành vi đó được chấp nhận và có kiểm thử.

**Khi dùng switch statement làm side effect bắt buộc:** cân nhắc một nhánh `default` rõ (có thể `throw new IllegalStateException(...)`) nếu thiếu xử lý một hằng phải được xem là lỗi. Đừng tự thêm `default -> null` chỉ để làm compiler ngừng cảnh báo nếu null sẽ gây lỗi ở bước sau.

Tương tự, khi cần chấp nhận dữ liệu không hợp lệ từ bên ngoài, **`Enum.valueOf` thất bại trước switch**; switch default không thay thế validation của input text.

## 25. Nhãn `case` enum: những lỗi compile-time thường gặp

Với selector `OrderStatus status`, Java 17 thông thường viết:

~~~java
switch (status) {
    case NEW -> System.out.println("new");
    case PROCESSING -> System.out.println("processing");
    case PAID -> System.out.println("paid");
    case CANCELLED -> System.out.println("cancelled");
}
~~~

Code trên là **switch statement snippet hợp lệ** trong method.

Những trường hợp **cố ý không hợp lệ nếu bỏ comment**:

~~~java
// case OrderStatus.NEW -> System.out.println("new");
// Với enum case label Java 17, dùng tên hằng không qualified.

// case "NEW" -> System.out.println("new");
// String literal không hợp kiểu OrderStatus.

// case STARTED -> System.out.println("new");
// Nếu OrderStatus không khai STARTED, không có enum constant hợp lệ.

// case NEW -> System.out.println("A");
// case NEW -> System.out.println("B");
// Một constant xuất hiện ở hai case labels của cùng switch.
~~~

Trong Java 17, `case null` thường liên quan tới các tính năng pattern switch **preview** nếu được bật; bài này tập trung các switch thông thường của Java 17 và không sử dụng preview. Đừng copy `case null` từ tài liệu cho một release Java mới hơn rồi mặc định nó chạy trên Java 17 khi không bật tính năng đặc biệt.

## 26. Enum có fields/methods vẫn dùng `==` và switch như thường

Enum không chỉ là danh sách tên. Bạn có thể gắn constructor, fields, instance methods:

~~~java
enum Priority {
    LOW(1), MEDIUM(2), HIGH(3);

    private final int weight;

    Priority(int weight) {
        this.weight = weight;
    }

    int weight() {
        return weight;
    }
}
~~~

Đây là một khai báo hợp lệ. `Priority.HIGH.weight()` trả 3 nhưng **identity** của hằng vẫn là Priority.HIGH. `==` kiểm tra **cùng hằng**, không so trường weight.

Có thể viết:

~~~java
Priority first = Priority.HIGH;
Priority second = Priority.HIGH;
boolean same = first == second;
int score = first.weight() + second.weight();
~~~

Đây là snippet hợp lệ trong method; `same` true và `score` bằng 6.

Nếu hai hằng khác nhau có cùng weight, chúng vẫn **không bằng nhau theo `==`**, vì weight chỉ là thuộc tính chứ không phải identity.

## 27. Chương trình hoàn chỉnh 11 — kết hợp thuộc tính enum, `==` và switch

Tệp **`EnumWithPropertiesDemo.java`**:

~~~java
enum Priority {
    LOW(1), MEDIUM(2), HIGH(3);

    private final int weight;

    Priority(int weight) {
        this.weight = weight;
    }

    int weight() {
        return weight;
    }
}

public class EnumWithPropertiesDemo {
    static String action(Priority priority) {
        return switch (priority) {
            case LOW -> "Queue";
            case MEDIUM -> "Review";
            case HIGH -> "Escalate";
        };
    }

    public static void main(String[] args) {
        Priority first = Priority.HIGH;
        Priority second = Priority.HIGH;

        System.out.println("same=" + (first == second));
        System.out.println("weight=" + first.weight());
        System.out.println("action=" + action(first));
        System.out.println("low action=" + action(Priority.LOW));
    }
}
~~~

Lệnh:

~~~bash
javac -encoding UTF-8 EnumWithPropertiesDemo.java
java EnumWithPropertiesDemo
~~~

**Stdout:**

~~~text
same=true
weight=3
action=Escalate
low action=Queue
~~~

Enum constants có thể có dữ liệu và hành vi, nhưng việc thêm instance fields không làm `equals` chuyển thành field-based equality. Trong chương trình này, trạng thái định danh bởi hằng; switch quyết định hành động.

## 28. Khi nào dùng switch, khi nào dùng hành vi nằm ngay trên enum?

Hai thiết kế đều có chỗ dùng.

**Switch bên ngoài enum:** phù hợp khi hành vi phụ thuộc vào ngữ cảnh caller, ví dụ màn hình hiển thị thông báo khác với chính sách billing. Nó giữ trách nhiệm của enum nhỏ và cho compiler kiểm tra mapping.

**Method bên trong enum:** phù hợp khi mỗi hằng có một hành vi gắn bản chất với chính giá trị ấy, ví dụ `direction.opposite()`. Có thể viết method thông thường bằng switch hoặc constant-specific class bodies; không phải mọi enum đều cần override method từng constant.

Nếu hàng chục switch giống hệt nhau xuất hiện rải rác, đó có thể là dấu hiệu logic chung nên gom lại. Nhưng **không ép mọi switch vào enum**, nếu nó thuộc một policy service độc lập, có dependency hoặc thay đổi theo chức năng.

## 29. Chương trình hoàn chỉnh 12 — method của enum dùng switch expression

Tệp **`EnumBehaviorDemo.java`**:

~~~java
enum TrafficLight {
    RED, YELLOW, GREEN;

    String instruction() {
        return switch (this) {
            case RED -> "Stop";
            case YELLOW -> "Slow down";
            case GREEN -> "Go";
        };
    }

    TrafficLight next() {
        return switch (this) {
            case RED -> GREEN;
            case GREEN -> YELLOW;
            case YELLOW -> RED;
        };
    }
}

public class EnumBehaviorDemo {
    public static void main(String[] args) {
        TrafficLight current = TrafficLight.RED;

        System.out.println("start=" + current);
        System.out.println("instruction="
                + current.instruction());

        current = current.next();
        System.out.println("next=" + current);
        System.out.println("instruction="
                + current.instruction());

        System.out.println("is GREEN="
                + (current == TrafficLight.GREEN));
    }
}
~~~

Chạy:

~~~bash
javac -encoding UTF-8 EnumBehaviorDemo.java
java EnumBehaviorDemo
~~~

**Stdout:**

~~~text
start=RED
instruction=Stop
next=GREEN
instruction=Go
is GREEN=true
~~~

Trong instance method của enum, `this` là chính hằng enum đang gọi method; switch expression dùng `this` làm selector. Việc gán `current = current.next()` chỉ **đổi reference trong biến current**, không sửa identity hay thứ tự của các enum constants.

## 30. Không dùng `ordinal()` để thay cho `==` hoặc switch

Mỗi enum constant có một **ordinal** tương ứng vị trí khai báo, bắt đầu từ 0. Tuy nhiên:

- `status.ordinal()` là **một chỉ số vị trí**, không phải mã nghiệp vụ ổn định.
- Chèn hoặc đổi thứ tự enum constants có thể thay đổi ordinal.
- `if (status.ordinal() == 2)` khó đọc hơn `status == OrderStatus.PAID`, dễ gãy khi refactor.
- `switch (status.ordinal())` biến nhánh typed enum thành nhánh int, mất lợi ích kiểm tra nhãn case theo enum.
- Không serialize/persist ordinal để biểu diễn trạng thái lâu dài trừ khi giao thức cụ thể kiểm soát chặt mapping và versioning.

Tương tự `compareTo` của enum dựa trên thứ tự khai báo; nó không nhất thiết mô tả mức độ ưu tiên nghiệp vụ hay thứ tự workflow. Dùng trường explicit như `priority.weight()` khi cần một con số định nghĩa rõ.

## 31. Chương trình hoàn chỉnh 13 — phân biệt tên, ordinal và identity

Tệp **`EnumOrdinalVsIdentityDemo.java`**:

~~~java
enum Size {
    SMALL, MEDIUM, LARGE
}

public class EnumOrdinalVsIdentityDemo {
    public static void main(String[] args) {
        Size a = Size.MEDIUM;
        Size b = Size.valueOf("MEDIUM");

        System.out.println("name=" + a.name());
        System.out.println("ordinal=" + a.ordinal());
        System.out.println("same=" + (a == b));
        System.out.println("compare=" + a.compareTo(b));
        System.out.println("large ordinal="
                + Size.LARGE.ordinal());
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac -encoding UTF-8 EnumOrdinalVsIdentityDemo.java
java EnumOrdinalVsIdentityDemo
~~~

**Stdout:**

~~~text
name=MEDIUM
ordinal=1
same=true
compare=0
large ordinal=2
~~~

`Size.valueOf("MEDIUM")` trả lại chính hằng MEDIUM, không tạo một Size object mới. Kết quả của `ordinal()` ở đây phụ thuộc thứ tự khai báo SMALL, MEDIUM, LARGE; đừng dùng các con số đó làm stable IDs cho database.

## 32. Tập hợp enum và bảng ánh xạ: `EnumSet`, `EnumMap`

Khi chương trình cần kiểm tra **một nhóm hằng** hoặc ánh xạ các hằng đến dữ liệu, `switch` không phải lựa chọn duy nhất.

- `EnumSet<OrderStatus>` lưu tập hợp các hằng; `contains(status)` diễn đạt membership.
- `EnumMap<OrderStatus, String>` ánh xạ từng hằng enum tới dữ liệu; phù hợp nếu mapping là bảng có thể xây từ cấu hình hoặc được cập nhật.
- `switch` phù hợp nếu cần **điều khiển hành vi**, logic per-case hoặc mapping nhỏ, cố định.
- `==` phù hợp nếu cần so với **một hằng cụ thể**.

Dùng `EnumSet.of(...)` thường rõ hơn một chuỗi `if (s == A || s == B || s == C)` khi nhóm hằng có tên và được dùng lại.

Lưu ý: `EnumMap.get` trả null nếu không có mapping (hoặc nếu cho phép null value); vì vậy nếu invariant đòi mọi hằng có mapping, hãy kiểm tra completeness ở construction/test. Switch expression liệt kê đầy đủ constants có lợi thế compiler kiểm tra exhaustiveness.

## 33. Chương trình hoàn chỉnh 14 — nhóm bằng `EnumSet`, ánh xạ bằng `EnumMap`

Tệp **`EnumCollectionsDemo.java`**:

~~~java
import java.util.EnumMap;
import java.util.EnumSet;
import java.util.Map;
import java.util.Set;

enum Workflow {
    CREATED, REVIEWING, APPROVED, REJECTED
}

public class EnumCollectionsDemo {
    public static void main(String[] args) {
        Set<Workflow> finalStates =
                EnumSet.of(Workflow.APPROVED, Workflow.REJECTED);

        Map<Workflow, String> labels =
                new EnumMap<>(Workflow.class);
        labels.put(Workflow.CREATED, "Created");
        labels.put(Workflow.REVIEWING, "In review");
        labels.put(Workflow.APPROVED, "Approved");
        labels.put(Workflow.REJECTED, "Rejected");

        Workflow current = Workflow.APPROVED;

        System.out.println("is final="
                + finalStates.contains(current));
        System.out.println("is approved="
                + (current == Workflow.APPROVED));
        System.out.println("label=" + labels.get(current));
        System.out.println("size=" + labels.size());
    }
}
~~~

Chạy:

~~~bash
javac -encoding UTF-8 EnumCollectionsDemo.java
java EnumCollectionsDemo
~~~

**Stdout:**

~~~text
is final=true
is approved=true
label=Approved
size=4
~~~

Ví dụ không in trực tiếp thứ tự duyệt Map hoặc Set, nên không phụ thuộc representation text của collections. Dữ liệu được kiểm tra bằng `contains`, `get` và `size`.

## 34. Enum khác kiểu: không dùng cùng một switch hoặc phép `==` tùy tiện

Giả sử:

~~~java
enum PaymentState {
    PAID
}

enum ShippingState {
    PAID
}
~~~

Hai enum có hằng trùng **tên văn bản**, nhưng `PaymentState.PAID` và `ShippingState.PAID` có hai kiểu khác nhau. Trong mã Java thông thường, phép so trực tiếp:

~~~java
// boolean same = PaymentState.PAID == ShippingState.PAID;
~~~

là **đoạn cố ý không hợp lệ nếu bỏ comment**, do hai operand có kiểu reference không thể chuyển đổi tương thích theo quy tắc `==`.

Không nên làm:

~~~java
// PaymentState.PAID.name().equals(ShippingState.PAID.name())
~~~

rồi kết luận hai **trạng thái nghiệp vụ** là một. Biểu thức so chuỗi tên sẽ cho true, nhưng đó chỉ là trùng text, không phải type identity.

Nếu cần ánh xạ giữa hai domain enums, hãy định nghĩa một **mapping function tường minh** với cases phù hợp để người đọc hiểu ý nghĩa của mỗi chuyển đổi.

## 35. Chương trình hoàn chỉnh 15 — mapping rõ giữa hai enum domains

Tệp **`EnumDomainMappingDemo.java`**:

~~~java
enum PaymentStatus {
    PENDING, PAID, FAILED
}

enum UiBadge {
    NEUTRAL, SUCCESS, ERROR
}

public class EnumDomainMappingDemo {
    static UiBadge badge(PaymentStatus status) {
        return switch (status) {
            case PENDING -> UiBadge.NEUTRAL;
            case PAID -> UiBadge.SUCCESS;
            case FAILED -> UiBadge.ERROR;
        };
    }

    public static void main(String[] args) {
        PaymentStatus state = PaymentStatus.PAID;
        UiBadge badge = badge(state);

        System.out.println("payment=" + state);
        System.out.println("badge=" + badge);
        System.out.println("is success="
                + (badge == UiBadge.SUCCESS));
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac -encoding UTF-8 EnumDomainMappingDemo.java
java EnumDomainMappingDemo
~~~

**Stdout:**

~~~text
payment=PAID
badge=SUCCESS
is success=true
~~~

Đây là chuyển đổi **có chính sách** từ trạng thái thanh toán sang nhãn hiển thị, không phải ép kiểu giữa hai enum. Enum switch expression giúp biểu diễn đầy đủ từng trường hợp và giữ các domain types độc lập.

## 36. Cần kiểm tra gì khi thay `if/else` bằng `switch`?

Không nên thay mọi if bằng switch mà không xem logic cũ.

**Thích hợp với switch enum:** biểu thức cần chọn nhánh theo **một giá trị enum** và mỗi nhánh có hành vi/kết quả riêng.

**Có thể nên giữ if/else:** điều kiện kết hợp nhiều biến (`amount > limit && status == PAID`), kiểm tra khoảng số, null policy hoặc quyền truy cập phụ thuộc nhiều dữ liệu. Trong Java 17 switch enum thông thường không có guards theo điều kiện arbitrary trên từng label.

Ví dụ:

~~~java
if (status == OrderStatus.PAID && amount > 1_000) {
    System.out.println("manual verification");
}
~~~

Đây là snippet minh họa; switch đơn thuần trên OrderStatus không thay luôn điều kiện `amount > 1_000` nếu không viết thêm if bên trong nhánh.

Khi dữ liệu có thể null, nên validate hoặc normalize trước để switch diễn đạt rõ danh sách trạng thái thực tế.

## 37. Quy tắc thiết kế `switch` dễ bảo trì

1. **Tên enum nói đúng domain:** `OrderStatus`, `PaymentStatus`, `TrafficLight` thay vì `Type` chung chung.
2. **Không dùng String magic constants** khi code đã có enum typed.
3. **So một hằng bằng `==`**, không vòng qua `name()` hoặc `ordinal()`.
4. **Dùng switch expression** khi cần ánh xạ một enum thành một giá trị có kiểu.
5. **Dùng arrow rules** để tránh fall-through ngoài ý muốn.
6. **Chỉ dùng colon fall-through khi có mục đích rõ**, chẳng hạn group nhiều case labels.
7. **Chọn null policy rõ ràng**: reject null hay map sang UNKNOWN.
8. **Cân nhắc bỏ default trong exhaustive expression** nếu mong compiler nhắc cập nhật khi enum đổi.
9. **Thêm default nếu đó là behavior thực sự**, không chỉ để giấu thiếu nhánh.
10. **Không phụ thuộc ordinal** như mã domain ổn định.
11. **Xét scope của policy:** mapping thuộc enum hay một service bên ngoài?
12. **Test đủ hằng** và chú ý khi thêm hằng mới.
13. **Giữ code per-case ngắn**; logic phức tạp có thể tách method riêng.
14. **Không trộn business state với display text**; dùng mapping/hành vi theo contract.

## 38. Những lỗi thường gặp

| Nhầm lẫn | Điều đúng trong Java 17 | Cách xử lý |
| --- | --- | --- |
| Enum là String nên phải dùng `equals` so text | Enum constant là object có kiểu enum riêng | `status == Status.PAID` |
| Enum reference luôn không null | Biến kiểu enum vẫn có thể mang null | Validate hoặc null policy |
| `status.equals(PAID)` luôn an toàn | NPE nếu status null | `status == Status.PAID` |
| `switch(null)` đi tới default | Switch enum thông thường ném NPE | Normalize/check trước |
| `case Status.PAID` trong enum switch | Case label enum thường dùng tên không qualified | `case PAID` |
| `case "PAID"` với enum selector | String không phải enum constant | `case PAID` |
| `case:` tự dừng | Dạng colon có fall-through | `break` hoặc arrow |
| Arrow rule vẫn chảy vào case kế | Arrow không fall-through | Tin theo cú pháp `->` |
| Switch expression có thể thiếu case tùy ý | Phải exhaustive | Bổ sung enum cases/default |
| Switch statement luôn phải exhaustive | Không bắt buộc như expression | Xem behavior khi thiếu cases |
| `yield` và `return` giống nhau | `yield` trả giá trị cho switch expression | Dùng đúng cấu trúc |
| Mọi switch phải có default | Không bắt buộc nếu đã đủ enum constants | Quyết định theo policy |
| `ordinal()` là business ID | Ordinal là vị trí khai báo | Dùng tên/mã domain ổn định |
| Hai enums có hằng cùng tên là cùng giá trị | Chúng khác typed identity | Mapping tường minh |
| Enum `equals` so các fields | Enum.equals dùng reference identity | So fields riêng nếu thật cần |
| Enum switch giải quyết validation text input | Parsing xảy ra trước switch | Xác nhận input/versioning |

## 39. Bài tập tự luyện

**Câu 1.** Vì sao `Status.READY == Status.READY` luôn đúng trong cùng runtime enum class?

**Câu 2.** Hai biến cùng kiểu enum cùng trỏ tới một hằng, `equals` và `==` trả kết quả khác nhau không?

**Câu 3.** Một biến enum `status = null`. `status == Status.READY` trả gì?

**Câu 4.** Với status null, `status.equals(Status.READY)` có gì xảy ra?

**Câu 5.** Với status null, switch enum thông thường của Java 17 có vào default không?

**Câu 6.** Khi selector có kiểu `Status`, hãy viết nhãn case cho hằng READY trong Java 17.

**Câu 7.** Dạng `case READY:` và `case READY ->` khác nhau thế nào ở fall-through?

**Câu 8.** Có thể viết `switch` với nhiều enum constants trong cùng một nhãn arrow không?

**Câu 9.** Switch expression trên enum bỏ một constant mà không có default thì compiler xử lý ra sao?

**Câu 10.** Switch statement trên enum bỏ một constant mà không có default có nhất thiết lỗi compile-time không?

**Câu 11.** Khi nào `yield` cần thiết trong switch expression?

**Câu 12.** Switch expression liệt kê đủ mọi hằng enum có buộc viết default không?

**Câu 13.** Vì sao thêm default vô điều kiện có thể khiến quên cập nhật switch khi enum thêm constant?

**Câu 14.** `name()` khác enum identity như thế nào?

**Câu 15.** Vì sao `ordinal()` không nên dùng làm mã lưu database?

**Câu 16.** Enum có constructor và fields riêng thì `==` còn hợp lệ không?

**Câu 17.** Hai constants khác nhau có cùng numeric weight có `==` bằng true không?

**Câu 18.** Phân biệt `EnumSet.contains(status)` và `status == ONE_CONSTANT`.

**Câu 19.** Khi nào dùng EnumMap thay switch mapping?

**Câu 20.** Hai enum domains khác nhau có cùng tên `PAID`; phép `==` trực tiếp giữa chúng có hợp lệ không?

**Câu 21.** Với input `" paid "`, nên xử lý thế nào trước khi dùng enum switch?

**Câu 22.** `valueOf("UNKNOWN")` với enum không có hằng UNKNOWN ném gì?

**Câu 23.** Nếu enum nhận thêm một constant mới, nên chạy loại kiểm thử nào?

**Câu 24.** Nếu logic phụ thuộc cả enum và số tiền, có bắt buộc bỏ if/else hoàn toàn không?

### Đáp án tham khảo

1. Vì mỗi hằng là một object duy nhất cho runtime enum class ấy; cả hai references chỉ cùng object.
2. Không khi receiver không null: Enum.equals dựa trên identity; `==` cũng so references.
3. False, không ném NPE.
4. Ném `NullPointerException`.
5. Không: switch enum thường trên null ném NPE trước khi chọn nhánh.
6. `case READY:` hoặc `case READY ->` theo dạng switch.
7. Colon cho phép fall-through nếu không thoát; arrow không fall-through.
8. Có: `case READY, PAUSED -> ...` nếu enum có hai constants ấy.
9. Báo lỗi vì expression không exhaustive.
10. Không; nhưng có thể bỏ sót hành vi.
11. Trong một block rule cần tính/trả giá trị cho expression sau nhiều statements.
12. Không nếu mọi constants đã được bao phủ.
13. Default nhận hằng mới, compiler không buộc sửa từng case của exhaustive expression.
14. `name()` là String tên constant, còn enum identity là object có kiểu.
15. Ordinal phụ thuộc thứ tự khai báo, có thể đổi khi refactor.
16. Có; fields không thay đổi identity của hằng.
17. Không; hai constants khác nhau vẫn là hai objects.
18. EnumSet kiểm tra thành viên của một nhóm, còn `==` kiểm tra đúng một hằng.
19. Khi cần một mapping theo bảng có thể được chuẩn bị, cấu hình hoặc cập nhật, không chỉ điều khiển luồng code.
20. Không theo phép so references trực tiếp giữa hai enum types không tương thích; cần mapping domain.
21. Chuẩn hóa input theo policy (`trim`, uppercase Locale.ROOT nếu thích hợp), parse `valueOf`, rồi so/switch enum.
22. `IllegalArgumentException`.
23. Rebuild các consumer switch expressions, unit tests toàn bộ constants, null và các mapping.
24. Không; `if` vẫn phù hợp cho biểu thức logic phối hợp nhiều điều kiện.

## 40. Checklist kiến thức cốt lõi

- Đã dùng enum thật thay vì String constants giả trạng thái?
- Đã hiểu cùng enum constant có identity ổn định?
- Với một hằng, đã ưu tiên `==`?
- Có trường hợp status null và đã xử lý rõ?
- Có phân biệt `status == CONST`, `status.equals(CONST)` và `switch(status)` khi null?
- Trong enum switch, nhãn case dùng tên hằng không qualified phù hợp Java 17?
- Có phân biệt **switch statement** và **switch expression**?
- Với colon statement, đã đặt `break` khi không muốn fall-through?
- Với arrow rules, có hiểu không cần `break` để ngăn chảy nhánh?
- Với expression, có bao phủ mọi constants hoặc có default đúng policy?
- Với block rule của expression, đã `yield` đúng giá trị?
- Khi thêm enum constant mới, đã cập nhật các mapping và tests?
- Có tránh sử dụng `ordinal()` làm mã external?
- Nếu enum có fields, có giữ riêng khái niệm identity và attribute value?
- Nếu cần nhóm trạng thái, đã cân nhắc EnumSet?
- Nếu cần tra bảng enum → value, đã cân nhắc EnumMap?
- Có tránh so sánh hai enum domains chỉ vì cùng tên?
- Có bảo đảm stdout ví dụ không phụ thuộc hash iteration, class-loader hay runtime implementation names?

## 41. Tài liệu Java 17 chính thức

- [JLS 17 §8.9 — Enum Classes](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.9): hằng enum, cấu trúc class và những quy định dành riêng cho enum.
- [JLS 17 §15.21 — Equality Operators](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.21): `==` trên references.
- [JLS 17 §14.11 — The switch Statement](https://docs.oracle.com/javase/specs/jls/se17/html/jls-14.html#jls-14.11): switch statements, labels, rules và fall-through.
- [JLS 17 §15.28 — Switch Expressions](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.28): expression, tính exhaustive và kết quả.
- [JLS 17 §14.21 — The yield Statement](https://docs.oracle.com/javase/specs/jls/se17/html/jls-14.html#jls-14.21): `yield` trong switch expressions.
- [Java SE 17 API — Enum](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Enum.html): equality, `name`, `ordinal`, `compareTo`, `valueOf`.
- [Java SE 17 API — EnumSet](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/EnumSet.html): tập hợp tối ưu cho các enum constants.
- [Java SE 17 API — EnumMap](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/EnumMap.html): mapping keyed theo enum.
- [Java SE 17 API — Objects.requireNonNullElse](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Objects.html#requireNonNullElse(T,T)): chọn fallback khác null khi policy yêu cầu.

## 42. Tổng kết

**So cùng enum constant bằng `==`** vì enum constants là objects có identity được kiểm soát bởi Java, không phải strings. `Enum.equals` cũng dựa trên identity, nhưng gọi `equals` trên một biến null sẽ ném exception; `==` thì không. Đừng dùng `name()` hoặc `ordinal()` để giả lập identity khi đã có enum references.

Với nhiều nhánh, **`switch` trên enum** diễn đạt rõ ràng và được compiler kiểm tra kiểu. Trong Java 17, `case CONSTANT ->` tránh fall-through, **switch expression** trả về giá trị và đòi **exhaustiveness**, còn `case CONSTANT:` truyền thống phải được viết cẩn thận với `break`. **Null không tự đi vào default** trong switch enum thông thường: validate hoặc quy định fallback trước khi switch.

Khi bảo trì, ưu tiên những cấu trúc bộc lộ ý định: `==` cho một hằng, `EnumSet` cho một nhóm, `EnumMap` cho bảng mapping, và switch expression cho logic nhiều nhánh cố định theo một enum type. Giữ chính sách parse input, null và thay đổi enum constants rõ ràng để code vừa đúng kiểu vừa dễ cập nhật.
