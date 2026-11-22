# Record pattern bị pattern khác chi phối (dominance) trong Java 21+

## 1. Hiểu đúng “bị chi phối” trong pattern switch

Khi dùng **record pattern** trong `switch`, một nhánh có thể trở thành **không thể được chọn** nếu nhánh ở trước đã bao phủ tất cả các giá trị mà nhánh đó có thể match. Java gọi quan hệ này là **dominance**: một case label *dominated* bởi case label đứng trước sẽ gây **lỗi biên dịch**, thay vì âm thầm trở thành mã chết.

Ví dụ Java 21:

```java
record Point(int x, int y) {}

static String invalid(Object value) {
    return switch (value) {
        case Point point -> "some point";
        case Point(int x, int y) -> "point components"; // Lỗi: dominated
        default -> "other";
    };
}
```

Trong ví dụ trên, `case Point point` là **type pattern**, khớp mọi đối tượng `Point` khác `null`. `case Point(int x, int y)` là **record pattern**, cũng chỉ có thể match một đối tượng `Point`. Mọi đối tượng đi đến nhánh record pattern đều đã bị nhánh đầu xử lý, nên compiler từ chối nhánh sau với lỗi đại ý **“this case label is dominated by a preceding case label”**.

Nội dung chính của bài:

- Record pattern có thể bị chi phối bởi **type pattern tổng quát** hoặc bởi **record pattern khác có component patterns rộng hơn**.
- Sự chi phối còn xét **cấu trúc lồng nhau** của các record patterns.
- `when` guard ảnh hưởng đến việc nhánh phía trước có chắc chắn bao phủ nhánh phía sau hay không.
- `null` của selector và `null` của record component cần được xét tách biệt.
- Biết quy tắc giúp sắp xếp nhánh từ **cụ thể** đến **tổng quát** mà không mất tính rõ ràng.

**Phiên bản:** record patterns được chuẩn hóa ở **Java 21 (JEP 440)**; pattern matching for switch được chuẩn hóa ở **Java 21 (JEP 441)**. Toàn bộ ví dụ dùng cú pháp ổn định của JDK 21+, không cần `--enable-preview`.

## 2. Record pattern là gì và có thể match những gì?

Record pattern vừa kiểm tra kiểu record, vừa deconstruct (lấy ra) các component để match các pattern tương ứng.

```java
record Parcel(Object value) {}

Object input = new Parcel("Java");

String description = switch (input) {
    case Parcel(String text) -> "text:" + text;
    case Parcel(var other) -> "other:" + other;
    default -> "not a Parcel";
};
```

`Parcel(String text)` chỉ khớp khi selector là `Parcel` và component `value` khớp pattern `String text`. `Parcel(var other)` rộng hơn: nó khớp các `Parcel` còn lại và suy luận `other` là kiểu `Object` từ component `Parcel.value()`.

Với `new Parcel("Java")`, kết quả là `"text:Java"`. Với `new Parcel(10)`, nhánh `Parcel(var other)` được chọn.

Record pattern **không** phải một lời gọi `equals()` và cũng không phải cú pháp constructor mới. Nó kiểm tra kiểu record, lấy giá trị các component bằng accessor, rồi áp dụng các pattern bên trong. Các biến `text`, `other` thuộc phạm vi nhánh khớp, không phải các field được gán thêm vào record.

Một record có thể chứa record khác, khi đó cú pháp có thể lồng nhau:

```java
record Point(int x, int y) {}
record Frame(Point point, Object tag) {}

// Minh họa pattern lồng nhau:
case Frame(Point(var x, var y), String label) -> "...";
```

Khi kiểm tra dominance, compiler xét không chỉ tên `Frame` mà cả mức độ tổng quát của các component patterns bên trong.

## 3. Trường hợp 1: type pattern đứng trước chi phối record pattern

Một **type pattern** bao phủ toàn bộ kiểu record có thể chi phối record pattern của chính kiểu đó.

Ví dụ **không biên dịch**:

```java
record Parcel(Object value) {}

static String wrong(Object input) {
    return switch (input) {
        case Parcel parcel -> "any Parcel";
        case Parcel(String text) -> "text:" + text; // Dominated
        default -> "other";
    };
}
```

Giải thích:

1. Nhánh `Parcel parcel` khớp mọi selector là `Parcel` khác `null`, dù `value` là chuỗi, số, đối tượng hay `null`.
2. Nhánh `Parcel(String text)` là **tập con** của các `Parcel`: nó yêu cầu thêm việc component phải match `String`.
3. Nếu một giá trị khớp nhánh sau, nó chắc chắn đã khớp nhánh trước. Compiler báo nhánh sau bị chi phối.

Cách sửa là **đưa pattern chuyên biệt lên trước**, sau đó mới dùng type pattern dự phòng:

```java
static String correct(Object input) {
    return switch (input) {
        case Parcel(String text) -> "text:" + text;
        case Parcel parcel -> "other Parcel";
        default -> "not a Parcel";
    };
}
```

Khi `input` là `new Parcel("Java")`, trả `"text:Java"`. Với `new Parcel(10)`, trả `"other Parcel"`. Với `42`, trả `"not a Parcel"`.

Type pattern **của một lớp cha** còn có thể chi phối record pattern cụ thể. Vì mọi record Java đều mở rộng `java.lang.Record`, đoạn sau cũng không biên dịch:

```java
static String wrongAncestor(Object input) {
    return switch (input) {
        case Record record -> "some record";
        case Parcel(String text) -> "specific Parcel"; // Dominated
        default -> "other";
    };
}
```

Khi cần xử lý riêng một loại record, hãy đặt nhánh record pattern trước `case Record record` hoặc `case Object obj`.

## 4. Trường hợp 2: record pattern tổng quát chi phối record pattern cụ thể

Dominance còn xảy ra **giữa hai record patterns của cùng một record**.

Giả sử:

```java
record Parcel(Object value) {}
```

Đoạn này **sai**:

```java
static String wrong(Object input) {
    return switch (input) {
        case Parcel(var any) -> "some Parcel";
        case Parcel(String text) -> "String Parcel"; // Dominated
        default -> "other";
    };
}
```

Vì component `value` có kiểu khai báo là `Object`, pattern `var any` trong `Parcel(var any)` có thể nhận mọi giá trị component. Do đó tất cả các `Parcel` mà `Parcel(String text)` có thể match đều đã được nhánh đầu bao phủ.

Một trường hợp tương tự:

```java
static String alsoWrong(Object input) {
    return switch (input) {
        case Parcel(Number number) -> "number";
        case Parcel(Integer integer) -> "integer"; // Dominated
        default -> "other";
    };
}
```

Ở đây `Integer` là subtype của `Number`. Bất kỳ component `Integer` nào khớp pattern thứ hai đều đã khớp `Number number` của pattern thứ nhất. Nhãn `Parcel(Integer integer)` bị dominated.

**Mô hình dễ nhớ:** khi record pattern đứng trước yêu cầu cùng record nhưng **component pattern rộng hơn** (hoặc tương đương) so với pattern sau, nó có thể chi phối pattern sau.

| Nhánh đứng trước | Nhánh đứng sau | Kết quả trên Java 21 |
| --- | --- | --- |
| `case Parcel parcel` | `case Parcel(String s)` | Nhánh sau bị dominated |
| `case Record record` | `case Parcel(String s)` | Nhánh sau bị dominated |
| `case Parcel(var v)` | `case Parcel(String s)` | Nhánh sau bị dominated |
| `case Parcel(Number n)` | `case Parcel(Integer i)` | Nhánh sau bị dominated |
| `case Parcel(String s)` | `case Parcel(var v)` | Hợp lệ: nhánh sau xử lý các component còn lại |
| `case Parcel(String s) when điềuKiện` | `case Parcel(String s)` | Hợp lệ với guard động: còn trường hợp guard sai |

Bảng trên xét các nhánh trong cùng một switch có selector phù hợp, ví dụ `Object`. Không suy diễn rằng Java có một bộ giải mọi quan hệ logic tùy ý giữa các biểu thức guard; các quy tắc dominance được xác định cụ thể trong ngôn ngữ.

## 5. Trường hợp 3: dominance lan vào record pattern lồng nhau

Với record nhiều tầng:

```java
record Point(int x, int y) {}
record Frame(Point point, Object tag) {}
```

Một nhánh rộng như sau có thể che nhánh cần `tag` là `String`:

```java
static String invalidNested(Object input) {
    return switch (input) {
        case Frame(Point(var x, var y), var tag) -> "frame";
        case Frame(Point(var x, var y), String name) -> "named"; // Dominated
        default -> "other";
    };
}
```

Tại nhánh đầu, `Point(var x, var y)` deconstruct một `Point`. Cả `x` và `y` được suy luận là `int` vì `Point` khai báo hai component kiểu `int`. Component `tag` được match bằng `var` và không bị giới hạn phải là `String`.

Nhánh thứ hai có cùng pattern cho `point` nhưng yêu cầu thêm `tag` khớp `String name`. Vì thế mọi giá trị khớp nhánh sau cũng khớp nhánh đầu. Compiler báo dominated.

Cách sửa:

```java
static String correctNested(Object input) {
    return switch (input) {
        case Frame(Point(var x, var y), String name) ->
                "named:" + name;
        case Frame(Point(var x, var y), var tag) ->
                "other tag:" + tag;
        case Frame(var point, var tag) ->
                "other point:" + point;
        default -> "not Frame";
    };
}
```

Với `new Frame(new Point(2, 3), "A")`, nhánh đầu khớp. Với `new Frame(new Point(2, 3), 7)`, nhánh thứ hai khớp. Với `new Frame(null, "A")`, pattern `Point(var x, var y)` **không** khớp vì component `point` là `null`; nhánh `Frame(var point, var tag)` cuối cùng có thể xử lý.

Đây là lý do khi thiết kế nested record patterns phải xét các **đường match thực sự của từng component**, không chỉ tên record ngoài cùng.

## 6. Null của selector khác null của component

Phân biệt hai trường hợp:

- **Selector null:** `switch ((Object) null)` cần một nhánh `case null` nếu muốn xử lý giá trị null. `default` không tự bắt null trong pattern switch Java 21; nếu thiếu nhánh null, switch thường ném `NullPointerException`.
- **Selector là record khác null nhưng component null:** `new Parcel(null)` vẫn là một `Parcel` và có thể match các record patterns tùy thuộc cách pattern component được khai báo.

Ví dụ quan trọng, đã kiểm tra bằng Java 21:

```java
static String show(Object input) {
    return switch (input) {
        case Parcel(String s) -> "text:" + s;
        case Parcel(var value) -> "other:" + value;
        default -> "not Parcel";
    };
}
```

Với `new Parcel(null)`, nhánh `Parcel(String s)` **không** khớp: component có kiểu khai báo `Object` nhưng giá trị `null` không khớp type pattern `String s` trong ngữ cảnh này. Nhánh `Parcel(var value)` nhận `null` và trả `"other:null"`.

Một tinh tế về **unconditional patterns** (pattern khớp vô điều kiện đối với kiểu component): với record `Parcel(Object value)`, `Parcel(Object v)` cũng có thể khớp component `null` khi được dùng như component pattern trong Java 21, bởi `Object v` là type pattern unconditional đối với component có kiểu tĩnh `Object`. Vì thế **không thể kết luận đơn giản rằng mọi pattern component có tên kiểu đều loại trừ null**.

```java
// Với record Parcel(Object value):
case Parcel(Object v) -> "value:" + v;
```

Nhánh trên có thể xử lý `new Parcel(null)`. Khi sắp xếp nhánh, compiler cũng xét quan hệ kiểu của pattern component; `case Parcel(Object v)` đặt trước `case Parcel(String s)` sẽ làm nhánh sau bị dominated.

**Nguyên tắc an toàn:** kiểm tra riêng `null` của selector, chú ý kiểu khai báo component và sự khác nhau giữa pattern đặc thù (`String s`) và pattern unconditional (`Object v`, `var v` trong ngữ cảnh tương ứng). Không đặt giả định sai về null vào thứ tự nhánh.

## 7. Chương trình Java 21 chạy đầy đủ

Lưu mã sau thành **DominatedRecordPatternDemo.java**:

```java
public class DominatedRecordPatternDemo {
    record Parcel(Object value) {}
    record Point(int x, int y) {}
    record Frame(Point point, Object tag) {}

    static String describe(Object input) {
        return switch (input) {
            case null -> "null";
            case Parcel(String s) when s.startsWith("#") ->
                    "tag:" + s.substring(1);
            case Parcel(Integer n) -> "count:" + n;
            case Parcel(String s) -> "text:" + s;
            case Parcel(var v) -> "other:" + String.valueOf(v);
            default -> "not-parcel";
        };
    }

    static String nested(Object input) {
        return switch (input) {
            case Frame(Point(var x, var y), String label) ->
                    "labeled:" + label + "@" + x + "," + y;
            case Frame(Point(var x, var y), var tag) ->
                    "frame:" + x + "," + y + ":" + tag;
            case Frame(var point, var tag) ->
                    "remaining-frame:" + point + ":" + tag;
            default -> "not-frame";
        };
    }

    static String wideType(Object input) {
        return switch (input) {
            case Parcel(String s) -> "string-parcel";
            case Parcel parcel -> "parcel";
            default -> "other";
        };
    }

    public static void main(String[] args) {
        System.out.println(describe(new Parcel("#A")));
        System.out.println(describe(new Parcel("hello")));
        System.out.println(describe(new Parcel(7)));
        System.out.println(describe(new Parcel(null)));
        System.out.println(describe(new Parcel(3.5)));
        System.out.println(describe("x"));
        System.out.println(describe(null));

        System.out.println(nested(
                new Frame(new Point(2, 3), "A")));
        System.out.println(nested(
                new Frame(new Point(4, 5), 7)));
        System.out.println(nested(new Frame(null, "z")));

        System.out.println(wideType(new Parcel("hi")));
        System.out.println(wideType(new Parcel(9)));
    }
}
```

Biên dịch và chạy:

```bash
javac DominatedRecordPatternDemo.java
java DominatedRecordPatternDemo
```

**Đầu ra chính xác:**

```text
tag:A
text:hello
count:7
other:null
other:3.5
not-parcel
null
labeled:A@2,3
frame:4,5:7
remaining-frame:null:z
string-parcel
parcel
```

### Phân tích luồng chọn nhánh

1. `new Parcel("#A")` khớp `Parcel(String s)` và guard `startsWith("#")` đúng, nên trả `"tag:A"`.
2. `new Parcel("hello")` khớp `Parcel(String s)` nhưng guard của nhánh đầu sai; `Integer` pattern cũng không khớp. Nhánh `Parcel(String s)` không guard phía sau được chọn.
3. `new Parcel(7)` khớp `Parcel(Integer n)`; không vào nhánh `Parcel(var v)` ở cuối nhóm.
4. `new Parcel(null)` không khớp `Parcel(String s)` hoặc `Parcel(Integer n)`, nhưng khớp `Parcel(var v)`, nên xuất `other:null`.
5. `new Parcel(3.5)` có component kiểu runtime `Double`, không khớp `String`/`Integer` và rơi vào `var`.
6. Chuỗi `"x"` không phải `Parcel`, nên vào `default`. Selector `null` có nhánh `case null` riêng.
7. Với `Frame(Point(2,3), "A")`, nhánh record pattern lồng nhau cụ thể nhất khớp, xuất `labeled:A@2,3`.
8. Với `Frame(Point(4,5), 7)`, nhánh cần `String label` không khớp; nhánh có `var tag` được chọn.
9. Với `Frame(null, "z")`, cả hai nhánh cần component `Point(...)` đều không khớp; nhánh rộng hơn `Frame(var point, var tag)` xử lý và in `remaining-frame:null:z`.
10. `wideType` đặt `Parcel(String s)` trước `Parcel parcel` nên không bị dominance; chuỗi đi nhánh đầu, số đi nhánh sau.

Đây là cách đọc và thiết kế switch theo **“pattern chuyên biệt trước, pattern dự phòng sau”**, có xét cả component bên trong record.

## 8. Ảnh hưởng của `when` guard đến dominance

Một record pattern đứng trước có thể có guard:

```java
static String guarded(Object input) {
    return switch (input) {
        case Parcel(var value) when value != null ->
                "non-null Parcel";
        case Parcel(String text) -> "text:" + text;
        case Parcel(var value) -> "remaining Parcel";
        default -> "other";
    };
}
```

Đoạn trên **biên dịch được trên Java 21**. Vì nhánh đầu có điều kiện động `when value != null`, nó không được compiler xem là pattern unconditional bao phủ mọi giá trị `Parcel`; ví dụ `new Parcel(null)` làm guard sai. Nhánh sau vẫn có thể được khai báo.

Tuy nhiên, với một component `String` khác null, guard `value != null` đã đúng, nên nhánh `Parcel(String text)` **không được chọn trên thực tế** trong logic này. Compiler không chứng minh mọi quan hệ giữa các guard động và các pattern. Vì vậy:

- **Lỗi dominance do compiler báo** và **nhánh không thể tới được do logic nghiệp vụ** là hai vấn đề liên quan nhưng không hoàn toàn giống nhau.
- Đừng trông cậy compiler phát hiện mọi trường hợp “guard đầu luôn đúng với mọi giá trị của nhánh sau”.
- Sắp xếp nhánh `Parcel(String text)` trước guard rộng nếu thực sự muốn xử lý riêng chuỗi.

### Guard `when true`

Đoạn này **không hợp lệ**:

```java
static String invalidGuard(Object input) {
    return switch (input) {
        case Parcel(var value) when true -> "all Parcel";
        case Parcel(String text) -> "String Parcel"; // Dominated
        default -> "other";
    };
}
```

`when true` là guard hằng đúng, nên với compiler nó có thể tạo dominance như một pattern không guard. Nếu muốn kiểm tra thêm điều kiện thực sự, viết guard động và xác định rõ nhánh nào nên ưu tiên. `when false` là guard hằng sai và bị compiler từ chối vì không có giá trị nào có thể chọn nhánh đó.

### Guard ném ngoại lệ

Guard được đánh giá sau khi pattern khớp. Nếu guard gọi phương thức ném ngoại lệ, Java **không coi ngoại lệ là guard false** để tiếp tục nhánh sau. Ngoại lệ truyền ra như thông thường. Tránh cho guard có side effects khó dự đoán hoặc truy cập component nullable không được kiểm tra.

## 9. Dominance khác exhaustiveness

**Dominance** hỏi: “Một case label ở phía sau có bị case label đứng trước che hoàn toàn không?”

**Exhaustiveness** hỏi: “Toàn bộ các nhánh có đủ để xử lý mọi giá trị selector hợp lệ theo yêu cầu `switch` hay không?”

Hai bài toán là khác nhau.

Ví dụ selector kiểu `Object`:

```java
static String incomplete(Object input) {
    return switch (input) {
        case Parcel(String s) -> "text";
        case Parcel(Integer n) -> "number";
        // Thiếu nhánh cho các kiểu khác: lỗi không exhaustive.
    };
}
```

Không có dominance giữa hai nhánh trên, vì `String` và `Integer` là các kiểu khác nhau; nhưng switch expression vẫn **không exhaustive** cho mọi `Object`.

Thêm nhánh `default` hoặc pattern bao phủ thích hợp:

```java
static String complete(Object input) {
    return switch (input) {
        case Parcel(String s) -> "text";
        case Parcel(Integer n) -> "number";
        case Parcel(var v) -> "other Parcel";
        default -> "other";
    };
}
```

Các nhánh cụ thể đứng trước nhánh record rộng nên không bị dominated; `default` xử lý đối tượng không phải `Parcel` (không bao gồm `null` nếu không có `case null` trong Java 21).

Một switch expression trên selector kiểu `Parcel` có thể đủ bao phủ bằng một record pattern unconditional đối với các component, hoặc một type pattern tổng quát cho `Parcel`, nhưng vẫn cần nhận thức riêng về selector `null`. Nói “switch exhaustive” không có nghĩa là `null` đã được xử lý theo yêu cầu nghiệp vụ.

## 10. Quy trình rà soát record pattern bị chi phối

Khi compiler báo `this case label is dominated by a preceding case label`, có thể kiểm tra theo thứ tự:

1. **Xác định kiểu selector**: `Object`, `Parcel`, interface, sealed type hay lớp cha nào? Selector type quyết định các case labels hợp lệ.
2. **Xem type pattern ở phía trước**: có `case Parcel p`, `case Record r`, `case Object o` hay pattern cha bao phủ record cần xử lý không?
3. **So record pattern cùng kiểu**: `Parcel(var v)` có đứng trước `Parcel(String s)` không? `Parcel(Number n)` có đứng trước `Parcel(Integer i)` không?
4. **Đi sâu vào component lồng nhau**: pattern trước có `Frame(Point(var x,var y), var tag)` bao phủ nhánh `Frame(Point(var x,var y), String label)` không?
5. **Kiểm tra guard**: nhánh trước có `when` động hay `when true`? Nếu có guard động, khả năng compiler cho phép nhiều nhánh không bảo đảm thứ tự nghiệp vụ đã đúng.
6. **Kiểm tra `null`**: `case null` là cho selector; nullable record component có thể làm một nested pattern thất bại hoặc vẫn khớp với unconditional pattern.
7. **Sắp xếp lại theo độ chuyên biệt**: đưa nhánh có cấu trúc/kiểu component cụ thể lên trước, nhánh `var`/type pattern rộng về sau.
8. **Kiểm tra exhaustiveness sau khi sửa**: đảm bảo switch còn nhánh xử lý các giá trị khác, đặc biệt khi selector có kiểu rộng như `Object`.

Không phải lỗi dominance nào cũng nên chữa bằng cách thêm `default`. `default` không làm một case bị dominated trở thành hợp lệ; cần thay đổi **thứ tự hoặc điều kiện pattern**.

## 11. Những hiểu lầm phổ biến

| Hiểu lầm | Cách hiểu đúng |
| --- | --- |
| “Hai record patterns của cùng record là trùng nhau.” | Cùng record vẫn có thể khác điều kiện component; ví dụ `Parcel(String s)` và `Parcel(Integer i)` không chi phối nhau. |
| “Chỉ type pattern mới gây dominance.” | Record pattern với component tổng quát, ví dụ `Parcel(var v)`, cũng có thể chi phối record pattern cụ thể. |
| “Kiểm tra kiểu record ngoài cùng là đủ.” | Phải xét component patterns và các mức record lồng nhau. |
| “`case Parcel(var v)` giống `case Parcel(String s)`.” | `var` rộng hơn nhiều; nó nhận cả component khác `String` và `null` trong ví dụ này. |
| “Đặt nhánh rộng trước giúp tiết kiệm so khớp.” | Nó có thể làm nhánh chuyên biệt phía sau bị dominated hoặc không được chọn. |
| “Guard động chắc chắn được compiler phân tích logic hết.” | Compiler không chứng minh mọi quan hệ giữa các guard động; code có thể biên dịch nhưng nhánh sau không bao giờ chạy với dữ liệu thực tế. |
| “Nếu `Parcel(String s)` không match `Parcel(null)` thì mọi component type pattern cũng không match null.” | Unconditional patterns cho kiểu component tương ứng, như `Object v` ở `Parcel(Object value)`, có thể match null. |
| “`default` sẽ xử lý mọi selector null.” | Với pattern switch Java 21, cần `case null` riêng nếu null được chấp nhận. |
| “Bỏ một case dominated là switch đã hoàn chỉnh.” | Sau khi sửa dominance vẫn phải kiểm tra tính exhaustive. |
| “Dominance là lỗi runtime.” | Đây là lỗi **compile-time** do quan hệ giữa các case labels; mã sai không được biên dịch. |

## 12. Bài tập tự kiểm tra

### Bài 1 — Nhận diện nhánh dominated

Cho:

```java
record Box(Object item) {}

static String classify(Object input) {
    return switch (input) {
        case Box(Number n) -> "number";
        case Box(Integer n) -> "integer";
        case Box(String s) -> "string";
        default -> "other";
    };
}
```

**Câu hỏi:** nhánh nào không biên dịch và tại sao?

**Đáp án:** `case Box(Integer n)` bị `case Box(Number n)` phía trước chi phối, vì `Integer extends Number`. `case Box(String s)` không bị nhánh `Box(Number n)` chi phối vì `String` không là subtype của `Number`. Sửa bằng cách đưa `Box(Integer n)` lên trước `Box(Number n)`.

### Bài 2 — Chuỗi, null và fallback

Cho:

```java
record Box(Object item) {}

static String label(Object input) {
    return switch (input) {
        case Box(String text) -> "string";
        case Box(var item) -> "other";
        default -> "not-box";
    };
}
```

**Đáp án:** `label(new Box("A"))` trả `"string"`; `label(new Box(7))` trả `"other"`; `label(new Box(null))` cũng trả `"other"`. `var` bắt được component null, còn `String text` ở đây không match null.

### Bài 3 — Sửa record pattern lồng nhau

Cho:

```java
record Point(int x, int y) {}
record Frame(Point point, Object tag) {}

static String wrong(Object input) {
    return switch (input) {
        case Frame(Point(var x, var y), var tag) -> "frame";
        case Frame(Point(var x, var y), String label) -> "labeled";
        default -> "other";
    };
}
```

**Đáp án:** nhánh `Frame(..., String label)` bị dominated vì `var tag` của nhánh đầu bao phủ cả `String`. Đổi thứ tự hai nhánh. Khi `point` là `null`, cả hai nhánh cần `Point(...)` đều không khớp; thêm `case Frame(var point, var tag)` nếu cần nhận mọi `Frame` còn lại.

### Bài 4 — Guard có cứu được nhánh sau không?

```java
record Box(Object item) {}

static String route(Object input) {
    return switch (input) {
        case Box(var item) when item != null -> "non-null";
        case Box(String text) -> "string";
        case Box(var item) -> "remaining";
        default -> "other";
    };
}
```

**Đáp án:** đoạn trên biên dịch trên Java 21 vì nhánh đầu có guard động. Tuy nhiên với mọi `Box` chứa `String` khác null, guard đầu đã đúng, vì vậy nhánh `Box(String text)` không được chọn trong thực tế. Đưa `Box(String text)` lên trước nếu chuỗi cần xử lý riêng. Với `Box(null)`, guard đầu sai và nhánh `Box(var item)` cuối nhận giá trị.

### Bài 5 — Phân biệt compile-time với runtime

Tại sao `case Parcel p` đứng trước `case Parcel(String s)` làm compiler báo lỗi nhưng `case Parcel(String s)` đứng trước `case Parcel p` lại hợp lệ?

**Đáp án:** type pattern `Parcel p` bao phủ tất cả giá trị `Parcel` mà record pattern chuyên biệt có thể match; nhánh record pattern phía sau trở nên vô hiệu. Khi đảo thứ tự, nhánh `Parcel(String s)` chỉ match một phần các Parcel; nhánh `Parcel p` phía sau vẫn có thể nhận các Parcel chứa số, null hoặc các kiểu component khác. Đây là tính chất của tập giá trị được match, không phải sự thay đổi runtime type của record.

## 13. Ghi nhớ

**Record pattern bị chi phối khi một case label đứng trước đã bao phủ toàn bộ trường hợp mà record pattern phía sau có thể match.** Trên Java 21, sự chi phối có thể đến từ một type pattern của chính record/lớp cha, một record pattern cùng kiểu có component rộng hơn hoặc một record pattern lồng nhau rộng hơn.

Cách tránh lỗi là **đặt pattern cụ thể trước, pattern tổng quát sau**, đánh giá tính giao nhau của các guard và kiểm tra riêng `null` ở selector so với component. Ngoài dominance, luôn kiểm tra **exhaustiveness** để bảo đảm switch còn xử lý đủ những trường hợp khác.

Tài liệu tham khảo chính thức:

- [JEP 440 — Record Patterns](https://openjdk.org/jeps/440)
- [JEP 441 — Pattern Matching for switch](https://openjdk.org/jeps/441)
- [Oracle Java 21 — Record Patterns](https://docs.oracle.com/en/java/javase/21/language/record-patterns.html)
- [Oracle Java 21 — Pattern Matching for switch](https://docs.oracle.com/en/java/javase/21/language/pattern-matching-switch.html)
- [Java SE 21 Language Specification — Switch Statements, including dominance (§14.11)](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.11)
- [Java SE 21 Language Specification — Patterns (§14.30)](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.30)
