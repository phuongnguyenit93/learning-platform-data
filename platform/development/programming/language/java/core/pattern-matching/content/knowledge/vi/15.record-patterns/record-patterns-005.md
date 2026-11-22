# Record pattern không phải accessor call thông thường

## 1. Hiểu đúng bản chất

Trong Java 21 trở lên, **record pattern** cho phép vừa kiểm tra kiểu của một giá trị, vừa *giải cấu trúc* (deconstruct) các component của record và ràng buộc chúng vào biến. Ví dụ:

```java
record Point(int x, int y) {}

Object candidate = new Point(2, 3);
if (candidate instanceof Point(var x, var y)) {
    System.out.println(x + y); // 5
}
```

`Point(var x, var y)` là **một pattern** chứ không phải lệnh tạo `Point`, lời gọi hàm `Point(...)` hay hai lời gọi accessor viết tường minh. Nó diễn tả điều kiện “giá trị này là một `Point` và các component của nó phù hợp với những pattern con”.

Có một chi tiết rất quan trọng: **record pattern thực sự sử dụng accessor của record**. Để lấy giá trị hai component, cơ chế matching gọi các accessor tương ứng như `Point.x()` và `Point.y()`; nó không được hiểu là truy cập thẳng vào trường `private final` và cũng không bỏ qua accessor do lập trình viên tự định nghĩa. Điểm khác biệt nằm ở **ngữ nghĩa của toàn bộ phép matching**: kiểm tra kiểu, giải cấu trúc, matching lồng nhau, điều kiện thành công/thất bại, phạm vi biến và xử lý ngoại lệ.

Record patterns được chuẩn hóa trong **Java 21** (JEP 440); ở Java 19/20 chúng từng là tính năng preview. Các ví dụ hoàn chỉnh bên dưới dùng Java 21, không cần `--enable-preview`.

## 2. Cơ chế của `instanceof` record pattern

Xét biểu thức:

```java
value instanceof Point(var x, var y)
```

Về mặt ngữ nghĩa, Java thực hiện các bước sau:

1. Xem giá trị được kiểm tra có khác `null` và có thể được kiểm tra/chuyển thành kiểu record `Point` hay không. Nếu không phù hợp, kết quả `instanceof` là `false`.
2. Khi kiểu record phù hợp, lấy các giá trị component thông qua **accessor tương ứng** của record, thay vì gọi một constructor mới.
3. So khớp từng component với pattern con. `var x`, `var y` suy luận kiểu từ khai báo component; pattern lồng nhau có thể còn kiểm tra kiểu và giải cấu trúc sâu hơn.
4. **Chỉ khi toàn bộ pattern thành công**, các pattern variable mới được ràng buộc và có thể sử dụng trong nhánh mà Java xác định matching đã thành công.

Đó là lý do viết `value instanceof Point(var x, var y)` không đồng nghĩa hoàn toàn với mã thủ công:

```java
Point p = (Point) value;
int x = p.x();
int y = p.y();
```

Đoạn thủ công giả định có thể ép kiểu và gọi phương thức an toàn; nếu kiểu không phù hợp nó có thể ném `ClassCastException`, còn nếu `p == null` thì gọi `p.x()` sẽ ném `NullPointerException`. `instanceof` record pattern trên một giá trị `null` hoặc sai kiểu trả về `false` bình thường. Ngoài ra, pattern còn có quy tắc matching các pattern con và phạm vi biến riêng.

| Khía cạnh | Gọi accessor trực tiếp: `p.x()` | Record pattern: `value instanceof Point(var x, var y)` |
| --- | --- | --- |
| Mục đích | Lấy kết quả của một phương thức | Kiểm tra pattern và giải cấu trúc dữ liệu |
| Kiểm tra kiểu đầu vào | Người viết phải có tham chiếu/ép kiểu phù hợp | Có kiểm tra kiểu record trong matching |
| Gặp `null` ở đối tượng bên ngoài | Gọi phương thức trên `null` gây `NullPointerException` | `instanceof` trả về `false` |
| Giá trị component | Kết quả của accessor được gọi | Giá trị component cũng được lấy qua accessor |
| Pattern lồng nhau | Phải tự viết các phép kiểm tra | Java có thể matching đệ quy |
| Biến kết quả | Biến do người viết khai báo | Pattern variable chỉ nằm trong phạm vi hợp lệ khi match thành công |
| Accessor ném ngoại lệ | Ngoại lệ từ lời gọi trực tiếp được truyền ra | Khi accessor bị gọi trong matching và ném ngoại lệ, Java ném `MatchException` với `cause` là ngoại lệ gốc |

**Lưu ý về tên:** với `record Point(int x, int y)`, `Point(var first, var second)` vẫn hợp lệ và ràng buộc theo **thứ tự component khai báo** (`x` rồi `y`). `first`/`second` là tên biến mới, không phải tên các phương thức accessor mà Java tìm kiếm.

## 3. Ví dụ chạy được: phân biệt kiểm tra kiểu với gọi accessor

Lưu mã sau trong `RecordPatternBasics.java`:

```java
public class RecordPatternBasics {
    record Point(int x, int y) {}

    static void print(Object value) {
        if (value instanceof Point(var x, var y)) {
            System.out.printf("point=(%d, %d), sum=%d%n", x, y, x + y);
        } else {
            System.out.println("not a Point");
        }
    }

    public static void main(String[] args) {
        print(new Point(2, 3));
        print("other");
        print(null);
    }
}
```

Biên dịch và chạy bằng JDK 21 trở lên:

```text
javac --release 21 RecordPatternBasics.java
java RecordPatternBasics
```

Kết quả chuẩn:

```text
point=(2, 3), sum=5
not a Point
not a Point
```

`Point(var x, var y)` khớp giá trị đầu tiên, rồi ràng buộc `x = 2`, `y = 3`. Chuỗi `"other"` không phải `Point` và `null` không khớp record pattern, nên cả hai đi vào nhánh `else`. Không có lời gọi `x()` hoặc `y()` nào cần xuất hiện tường minh trong mã nguồn để lấy hai giá trị.

## 4. Accessor được định nghĩa lại vẫn được gọi

Thông thường, record tự sinh accessor có cùng tên với component (`code()` chứ không phải `getCode()`). Tuy nhiên record có thể khai báo accessor tường minh, miễn là tuân thủ chữ ký hợp lệ. Pattern sẽ quan sát **giá trị do accessor đó trả về**, kể cả khi nó khác cách đọc trực tiếp trường lưu trữ.

Lưu vào `AccessorIsInvoked.java`:

```java
import java.util.Locale;

public class AccessorIsInvoked {
    record Ticket(String code) {
        public String code() {
            System.out.println("Ticket.code() invoked");
            return code.strip().toUpperCase(Locale.ROOT);
        }
    }

    public static void main(String[] args) {
        Object value = new Ticket(" ab-12 ");

        if (value instanceof Ticket(var extracted)) {
            System.out.println("Pattern: " + extracted);
        }

        Ticket ticket = (Ticket) value;
        System.out.println("Direct: " + ticket.code());
    }
}
```

```text
javac --release 21 AccessorIsInvoked.java
java AccessorIsInvoked
```

Kết quả:

```text
Ticket.code() invoked
Pattern: AB-12
Ticket.code() invoked
Direct: AB-12
```

Dòng `Ticket.code() invoked` đầu tiên xuất hiện trong lúc **record pattern giải cấu trúc `Ticket`**; dòng thứ hai xuất hiện từ lời gọi `ticket.code()` viết trực tiếp. Bởi vậy, phát biểu “record pattern chỉ đọc field, không gọi accessor” là **sai**. Phát biểu “record pattern chỉ là cú pháp viết tắt cho một accessor call thông thường” cũng **thiếu chính xác** vì nó bỏ qua phần kiểm tra và matching của pattern.

Với accessor có tác dụng phụ, thao tác matching có thể tạo log, cập nhật trạng thái hoặc ném lỗi. Trong thiết kế record, nên giữ accessor đơn giản, ổn định, ít tác dụng phụ; không viết chương trình phụ thuộc vào việc một pattern phức tạp sẽ gọi mỗi accessor bao nhiêu lần hoặc theo thứ tự nào.

## 5. `null` ở record ngoài khác với `null` trong component

**`null` không bao giờ khớp một record pattern**. Tuy nhiên, một component của record hoàn toàn có thể chứa `null`. Khi pattern con là type pattern *null-matching* như `var` áp dụng trực tiếp cho component phù hợp, nó có thể ràng buộc giá trị `null`. Một **record pattern lồng nhau** thì vẫn không khớp `null`.

Lưu vào `NestedNulls.java`:

```java
public class NestedNulls {
    record City(String name) {}
    record Route(City destination) {}

    public static void main(String[] args) {
        Object first = new Route(new City("Hue"));
        Object second = new Route(null);
        Object third = null;

        System.out.println("first nested: "
                + (first instanceof Route(City(var name))));
        System.out.println("second nested: "
                + (second instanceof Route(City(var name))));
        System.out.println("second direct: "
                + (second instanceof Route(var destination)));
        System.out.println("third outer: "
                + (third instanceof Route(var destination)));

        if (first instanceof Route(City(var city))) {
            System.out.println("City: " + city);
        }
    }
}
```

```text
javac --release 21 NestedNulls.java
java NestedNulls
```

Kết quả:

```text
first nested: true
second nested: false
second direct: true
third outer: false
City: Hue
```

Phân tích:

- `Route(City(var name))` cần cả `Route` và component `destination` khớp record pattern `City(...)`. Vì `second.destination()` trả `null`, phần `City(...)` thất bại.
- `Route(var destination)` chỉ ràng buộc component trực tiếp; ở đây `destination` có thể nhận `null`, vì type pattern suy luận từ `City` là null-matching tại vị trí component này.
- `third` là `null`, nên bản thân `Route(...)` đã không khớp.
- Sau nhánh `if` thành công, biến `city` có kiểu `String` và chỉ dùng được ở vùng phạm vi được phép. Không thể dùng `city` bên ngoài như thể nó luôn được khởi tạo.

Vì vậy, không nên mô tả record pattern là chuỗi accessor call kết hợp “null-safe navigation” tự động. **Mức độ khớp `null` phụ thuộc vào loại pattern tại từng vị trí.**

## 6. Ngoại lệ từ accessor: khác biệt quan trọng về hành vi

Một accessor có thể ném ngoại lệ không kiểm tra (*unchecked exception*). Khi gọi trực tiếp, ngoại lệ đó truyền ra từ lời gọi phương thức. Khi accessor được Java gọi ngầm trong quá trình matching của record pattern, đặc tả Java 21 yêu cầu ném `java.lang.MatchException`, và ngoại lệ ban đầu được giữ ở `getCause()`.

Lưu vào `AccessorExceptions.java`:

```java
public class AccessorExceptions {
    record Broken(String value) {
        public String value() {
            throw new IllegalStateException("cannot read value");
        }
    }

    public static void main(String[] args) {
        Broken broken = new Broken("data");

        try {
            broken.value();
        } catch (IllegalStateException ex) {
            System.out.println("Direct: "
                    + ex.getClass().getSimpleName());
        }

        try {
            Object input = broken;
            if (input instanceof Broken(var value)) {
                System.out.println(value);
            }
        } catch (MatchException ex) {
            System.out.println("Pattern cause: "
                    + ex.getCause().getClass().getSimpleName());
        }
    }
}
```

```text
javac --release 21 AccessorExceptions.java
java AccessorExceptions
```

Kết quả:

```text
Direct: IllegalStateException
Pattern cause: IllegalStateException
```

**Phân biệt ba tình huống:**

- Giá trị bên ngoài sai kiểu hoặc `null` trong biểu thức `instanceof` record pattern: matching thất bại và trả `false`.
- Một pattern con không khớp: toàn bộ record pattern có thể trả `false`, không có nghĩa là lỗi accessor.
- Accessor ném ngoại lệ khi Java đang lấy component: matching kết thúc bất thường bằng `MatchException`; đây **không phải** kết quả `false`, và có thể kiểm tra nguyên nhân qua `getCause()`.

Đây là khác biệt hành vi quan trọng khi xử lý lỗi, logging hoặc chuyển từ mã giải cấu trúc thủ công sang pattern matching.

## 7. Record pattern trong `switch` cũng là matching

Record pattern không bị giới hạn trong `instanceof`. Java 21 cho phép dùng trong `switch` theo cùng ý tưởng kiểm tra kiểu và giải cấu trúc. Đoạn dưới **minh họa trong một lớp đã khai báo** `record Point(int x, int y)`:

```java
static String describe(Object candidate) {
    return switch (candidate) {
        case null -> "null";
        case Point(var x, var y) -> "Point(" + x + ", " + y + ")";
        default -> "other";
    };
}
```

`case Point(...)` không phải lời gọi constructor hay accessor viết tay; nó là nhánh pattern. `case null` xử lý selector `null` một cách tường minh. Đừng suy luận rằng record pattern tự hấp thụ `null` cho toàn bộ biểu thức `switch`: nếu không có nhánh xử lý `null` thích hợp, `switch` có thể ném `NullPointerException`.

Khi cần thêm điều kiện nghiệp vụ, có thể đặt điều kiện sau matching, chẳng hạn `if (candidate instanceof Point(var x, var y) && x > 0)`. Điều kiện `x > 0` chỉ được đánh giá khi pattern đã khớp và biến `x` có giá trị hợp lệ.

## 8. Những nhầm lẫn thường gặp

1. **“Pattern truy cập trực tiếp `private final` field.”** Không đúng. Component value được lấy thông qua accessor tương ứng; accessor tường minh có thể thay đổi giá trị trả về hoặc ném ngoại lệ.
2. **“Có phương thức `x()` và `y()` thì class thường cũng dùng `Point(x, y)` pattern được.”** Không đúng. Cú pháp record pattern áp dụng cho kiểu record; tên phương thức giống accessor không biến một class thường thành record.
3. **“Tên biến trong pattern quyết định accessor.”** Không đúng. Thứ tự và số lượng component đi theo khai báo record: `record Point(int x, int y)` cần pattern gồm đúng hai vị trí, ví dụ `Point(var left, var top)`.
4. **“Pattern thành công thì các biến luôn tồn tại ở mọi nhánh.”** Không đúng. Pattern variables chỉ ở trong phạm vi mà Java chứng minh matching thành công (flow scoping).
5. **“Mọi `null` bên trong record đều làm matching thất bại.”** Không đúng. `null` ở chính vị trí record pattern lồng nhau không khớp; `var` hoặc type pattern null-matching ở component trực tiếp có thể ràng buộc `null`.
6. **“Nếu accessor lỗi thì `instanceof` trả `false`.”** Không đúng. Java 21 ném `MatchException` với nguyên nhân gốc khi accessor ném lỗi trong matching.
7. **“Record pattern có thể dùng ổn định ngay từ Java 17.”** Không đúng. Record pattern trở thành tính năng chính thức từ **Java 21**; bản JDK 21 trở lên biên dịch được các ví dụ này mà không cần bật preview.

## 9. Khi nào dùng pattern, khi nào gọi accessor?

Dùng **record pattern** khi mục đích là phân nhánh theo hình dạng/kiểu dữ liệu, trích xuất đồng thời nhiều component, hoặc giải cấu trúc dữ liệu lồng nhau trong `instanceof` hay `switch`. Dùng **accessor trực tiếp** khi bạn đã có một đối tượng đúng kiểu và chỉ muốn đọc một component rõ ràng.

Trong cả hai trường hợp, chú ý đến accessor do record tự sinh hoặc do lập trình viên khai báo. Khi cấu trúc dữ liệu có thể chứa `null`, xác định rõ bạn cần ràng buộc `null` hay yêu cầu pattern lồng nhau phải khớp. Khi accessor có thể ném lỗi, kiểm tra khác biệt giữa ngoại lệ gọi trực tiếp và `MatchException` của pattern.

**Ghi nhớ:** *record pattern gọi accessor để lấy component, nhưng bản thân record pattern là một phép kiểm tra và giải cấu trúc có quy tắc riêng về kiểu, `null`, phạm vi biến và ngoại lệ.*

## Tham khảo chính thức

- [Oracle Java SE 21 — Record Patterns](https://docs.oracle.com/en/java/javase/21/language/record-patterns.html)
- [Java Language Specification 21 — §14.30.2 Pattern Matching](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.30.2)
- [Java SE 21 API — `MatchException`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/MatchException.html)
