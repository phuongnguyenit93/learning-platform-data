# Tách pattern để tránh dominance khó hiểu trong Java `switch`

## 1. Vấn đề: nhánh quá rộng che nhánh cụ thể

Trong pattern matching cho `switch`, **dominance** xảy ra khi một nhãn `case` đứng trước có khả năng khớp tất cả giá trị mà một nhãn `case` sau có thể khớp. Nếu đặt nhánh sau để xử lý riêng một trường hợp nhưng nó không bao giờ có cơ hội được chọn, Java báo lỗi biên dịch.

Ví dụ sau **cố ý sai** (giả sử `value` có kiểu `Object`):

```java
return switch (value) {
    case CharSequence chars -> "Text-like";
    case String text -> "String";
    default -> "Other";
};
```

Mọi `String` đều triển khai `CharSequence`. Do đó, nếu một giá trị khớp `case String text` thì nó đã khớp `case CharSequence chars` phía trước. Trình biên dịch Java 21 báo lỗi gần với **“this case label is dominated by a preceding case label”**.

Muốn tránh dominance khó hiểu, **tách** nhóm giá trị thành các trường hợp có ý nghĩa rõ ràng: đặt trường hợp đặc biệt trước trường hợp tổng quát; tách nhánh có guard `when` trước nhánh không guard; dùng phương thức chung cho logic trùng lặp thay vì cố gộp mọi pattern vào một nhãn.

Bài này sử dụng **Java 21**: record patterns và pattern matching cho `switch` đã là tính năng chính thức trong Java 21. Các ví dụ `case Record(...)` và `when` dưới đây không yêu cầu `--enable-preview` khi biên dịch bằng `javac --release 21`.

## 2. Tại sao compiler từ chối dù chương trình trông vẫn có đủ `case`?

Công việc của compiler không chỉ là xem danh sách `case` dài hay ngắn. Nó kiểm tra **quan hệ kiểu**, **cấu trúc pattern**, **guard**, thứ tự nhánh và **tính bao phủ**.

Hai khái niệm quan trọng:

- **Dominance:** có nhãn `case` nào bị một nhãn đứng trước che, khiến nhãn đó không còn đường được chọn?
- **Exhaustiveness:** tập nhãn có bao phủ các giá trị được hệ thống kiểu cho phép hay không, đối với những dạng `switch` bắt buộc phải exhaustive?

Một `switch` có thể exhaustive mà vẫn lỗi vì dominance. Thêm `default` cũng **không sửa được** một nhãn đã bị nhánh trước che.

**Dominance không phải vấn đề tên biến.** Hai rule khác nhau được phép dùng chung tên pattern variable nếu scope không chồng lấn. Vấn đề nằm ở **những giá trị pattern có thể khớp** và **thứ tự đặt nhãn**.

Ngoài ra, việc đổi thứ tự case có thể thay đổi hành vi chương trình. Vì vậy, refactor đúng phải dựa vào **ý định nghiệp vụ** thay vì chỉ di chuyển dòng đến khi compiler ngừng báo lỗi.

## 3. Trường hợp 1: supertype đứng trước subtype

### Cách viết bị dominance

```java
// Đặt trong phương thức có Object value.
// CỐ Ý SAI: Java 21 không biên dịch.
return switch (value) {
    case CharSequence sequence -> "SEQUENCE";
    case String text -> "STRING"; // Nhánh này bị che.
    default -> "OTHER";
};
```

`String` là subtype của `CharSequence`. Nhánh `String` không thể chạy khi nhánh `CharSequence` không guard đứng trước.

### Cách tách hợp lệ và dễ hiểu

```java
return switch (value) {
    case String text -> "STRING:" + text;
    case CharSequence sequence ->
        "SEQUENCE:" + sequence.length();
    default -> "OTHER";
};
```

Thứ tự này có nghĩa:

1. Nếu giá trị là `String`, xử lý riêng ở nhánh đầu.
2. Nếu không phải `String` nhưng vẫn là `CharSequence`, xử lý ở nhánh thứ hai; ví dụ `StringBuilder`.
3. Các kiểu còn lại được chuyển tới `default`.

Với selector `null`, `default` thông thường trong pattern `switch` **không tự xử lý `null`**. Nếu yêu cầu không được ném `NullPointerException`, hãy thêm `case null`.

**Khi nào nên bỏ nhánh subtype?** Nếu mọi `CharSequence` đều cần hành vi y hệt nhau, có thể chỉ giữ `case CharSequence sequence`. Không cần tạo case `String` nếu không có chính sách xử lý riêng. Ngược lại, nếu ứng dụng chỉ hỗ trợ `String` và `StringBuilder`, một nhánh `CharSequence` tổng quát có thể **nhận quá nhiều kiểu**; lúc ấy hãy giữ hai case riêng và cùng gọi một helper.

### `Object` cũng có thể che mọi subtype

```java
// CỐ Ý SAI:
return switch (value) {
    case Object any -> "OBJECT";
    case Integer number -> "INTEGER";
};
```

`case Object any` khớp mọi đối tượng không `null`. Nhánh `Integer` phía sau không có tác dụng. Để xử lý số nguyên riêng, đưa `case Integer number` lên trước và dùng `default` cuối cùng cho dữ liệu còn lại. `case null` có vai trò khác với `case Object` và cần được xét riêng.

## 4. Trường hợp 2: record pattern tổng quát che pattern có `when`

Khai báo:

```java
record Point(int x, int y) {}
```

Một cách viết **sai**:

```java
// CỐ Ý SAI:
return switch (value) {
    case Point(int x, int y) -> "ANY_POINT";
    case Point(int x, int y) when x == y ->
        "DIAGONAL";
    default -> "OTHER";
};
```

Record pattern đầu tiên không có guard và khớp mọi `Point` phù hợp. Nhánh sau chỉ muốn nhận một tập con — các điểm có `x == y` — nhưng tập con ấy đã bị nhánh trên nhận trước.

**Cách sửa:**

```java
return switch (value) {
    case Point(int x, int y) when x == y ->
        "DIAGONAL:" + x;
    case Point(int x, int y) ->
        "POINT:" + x + "," + y;
    default -> "OTHER";
};
```

Trong nhánh đầu, `Point(...)` phải khớp trước, rồi mới đánh giá guard `x == y`. Với `Point(2,2)`, guard đúng và nhánh đầu được chọn. Với `Point(2,3)`, guard sai nên Java xét nhánh `Point(...)` không guard bên dưới.

**Công thức hữu ích:**

```text
case Kiểu(components...) when điều_kiện_riêng -> xử_lý_riêng
case Kiểu(components...)                    -> xử_lý_còn_lại
```

Đây là **khung minh họa**, không phải cú pháp Java độc lập để dán vào tệp. Thứ tự **cụ thể → tổng quát** giúp thấy rõ fallback của cùng một kiểu.

### Compiler không chứng minh mọi quan hệ logic giữa guards

Đừng giả định compiler suy ra hai biểu thức `when` bất kỳ luôn loại trừ nhau. Guard có thể gọi hàm, có side effect hoặc phụ thuộc dữ liệu runtime. Nếu mục tiêu là xử lý mọi giá trị của một kiểu, thêm **một case không guard** cuối nhóm thường dễ hiểu hơn các guard phức tạp mà người đọc phải tự chứng minh bao phủ hết.

Ví dụ:

```java
case String text when text.isBlank() -> "BLANK";
case String text -> "TEXT:" + text;
```

Hai case là hai nhánh riêng; tên `text` được dùng lại hợp lệ. `case String text` thứ hai đảm nhận các chuỗi không thỏa guard của nhánh thứ nhất.

## 5. Trường hợp 3: record lồng nhau cần nhánh riêng trước fallback

Khi record chứa record khác:

```java
record Point(int x, int y) {}
record Pair(Point point) {}
```

Nếu cần nhận biết `Pair` chứa điểm gốc `Point(0,0)`, không nên đặt `case Pair(var point)` lên đầu:

```java
// CỐ Ý SAI, nhánh sau bị dominance:
return switch (value) {
    case Pair(var point) -> "ANY_PAIR";
    case Pair(Point(int x, int y))
            when x == 0 && y == 0 ->
        "ORIGIN";
    default -> "OTHER";
};
```

`case Pair(var point)` là pattern bao quát với thành phần `point`; nó đã khớp các `Pair` có điểm gốc, nên nhánh sau không thể được chọn.

Bản tách hợp lệ:

```java
return switch (value) {
    case Pair(Point(int x, int y))
            when x == 0 && y == 0 ->
        "ORIGIN";

    case Pair(var point) ->
        point == null ? "PAIR_MISSING" : "PAIR_OTHER";

    case null, default ->
        "NOT_PAIR";
};
```

Ý nghĩa của các case:

- `Pair(new Point(0,0))`: nhánh record lồng có guard, kết quả `ORIGIN`.
- `Pair(new Point(3,4))`: record lồng khớp nhưng guard sai; nhánh `Pair(var point)` nhận fallback, kết quả `PAIR_OTHER`.
- `Pair(null)`: pattern lồng `Point(...)` **không khớp `null`**, nhưng component pattern `var point` trong Java 21 có thể gắn giá trị `null`; kết quả `PAIR_MISSING`.
- Bản thân selector bằng `null` hoặc không phải `Pair`: `case null, default`, kết quả `NOT_PAIR`.

**Chú ý về `null`:** `var point` tại thành phần record là pattern unconditional đối với kiểu thành phần nên có thể nhận `null` ở đây. Điều này không có nghĩa `null instanceof Point p` là đúng; biểu thức `instanceof` với toán hạng `null` vẫn trả `false`. Hãy kiểm tra `point != null` trước khi gọi các accessor nếu fallback có thể nhận record chứa thành phần rỗng.

Khi nested pattern quá phức tạp, một thiết kế thay thế là **chỉ** dùng `case Pair(var point) -> classifyPoint(point)`, rồi để helper phân biệt điểm gốc, điểm khác và `null`. Không nhất thiết giữ cả nested case lẫn helper; chọn cách thể hiện ý định rõ hơn.

## 6. Chương trình Java 21 hoàn chỉnh

Tệp **`DominanceRefactorDemo.java`**:

```java
public class DominanceRefactorDemo {
    sealed interface Event permits TextEvent, CountEvent, Done {}

    record TextEvent(String value) implements Event {}
    record CountEvent(int value) implements Event {}
    record Done() implements Event {}

    record Point(int x, int y) {}
    record Pair(Point point) {}

    static String describe(Event event) {
        return switch (event) {
            case null -> "NULL";

            case TextEvent(String text)
                    when text != null && text.isBlank() ->
                "BLANK";

            case TextEvent(String text) ->
                "TEXT:" + text;

            case CountEvent(int count) when count < 0 ->
                "NEGATIVE:" + count;

            case CountEvent(int count) ->
                "COUNT:" + count;

            case Done() ->
                "DONE";
        };
    }

    static String describeObject(Object value) {
        return switch (value) {
            case null -> "NULL";
            case String text -> "STRING:" + text.toUpperCase();
            case CharSequence chars ->
                "SEQUENCE:" + chars.length();
            default -> "OTHER";
        };
    }

    static String describePair(Object value) {
        return switch (value) {
            case Pair(Point(int x, int y))
                    when x == 0 && y == 0 ->
                "ORIGIN";

            case Pair(var point) ->
                point == null ? "PAIR_MISSING" : "PAIR_OTHER";

            case null, default ->
                "NOT_PAIR";
        };
    }

    public static void main(String[] args) {
        Event[] events = {
            new TextEvent("  "),
            new TextEvent("ok"),
            new TextEvent(null),
            new CountEvent(-2),
            new CountEvent(3),
            new Done(),
            null
        };

        for (Event event : events) {
            System.out.println(describe(event));
        }

        System.out.println(describeObject("hi"));
        System.out.println(describeObject(new StringBuilder("hello")));
        System.out.println(describeObject(4));

        System.out.println(describePair(new Pair(new Point(0, 0))));
        System.out.println(describePair(new Pair(new Point(3, 4))));
        System.out.println(describePair(new Pair(null)));
        System.out.println(describePair(null));
    }
}
```

Biên dịch và chạy bằng **JDK 21+**:

```bash
javac --release 21 DominanceRefactorDemo.java
java DominanceRefactorDemo
```

Stdout:

```text
BLANK
TEXT:ok
TEXT:null
NEGATIVE:-2
COUNT:3
DONE
NULL
STRING:HI
SEQUENCE:5
OTHER
ORIGIN
PAIR_OTHER
PAIR_MISSING
NOT_PAIR
```

### Đọc kết quả từng nhóm

**Nhóm `describe(Event)`:** `Event` là `sealed interface` với ba dạng record cho phép. Nhánh `TextEvent` có guard nhận chuỗi trắng, nhánh `TextEvent` không guard nhận các trường hợp còn lại. `TextEvent(null)` đi vào fallback: component type pattern trực tiếp `String text` có thể gắn giá trị `null` trong record pattern Java 21, nên phép nối chuỗi tạo `TEXT:null`. Nhánh `CountEvent` có guard tách số âm khỏi các số còn lại. `Done()` được xử lý riêng. Vì các subtype được phép đều được bao phủ, `switch` expression exhaustive mà không cần `default`. `case null` xử lý selector rỗng tường minh.

**Nhóm `describeObject(Object)`:** `String` được nhận trước `CharSequence`, nên `"hi"` được in `STRING:HI`; `StringBuilder("hello")` không phải `String` nhưng là `CharSequence`, in `SEQUENCE:5`. Số `4` được autoboxing thành `Integer` khi gọi phương thức nhận `Object`; nó không khớp hai nhánh trên và trả `OTHER`.

**Nhóm `describePair(Object)`:** `Pair(Point(0,0))` nhận `ORIGIN`; `Pair(Point(3,4))` nhận `PAIR_OTHER`; `Pair(null)` nhận `PAIR_MISSING`. Selector `null` thì vào `case null, default`, nhận `NOT_PAIR`.

Ví dụ không chỉ đảo thứ tự các case mà còn **tách đúng ba vai trò**: xử lý riêng theo guard, fallback của cùng loại, và fallback cho kiểu khác.

## 7. Khi các pattern khác nhau cần cùng logic, tách case nhưng chia sẻ helper

Một nguyên nhân khiến `switch` khó đọc là lặp lại xử lý giống nhau ở nhiều nhánh. Thay vì dùng pattern của supertype quá rộng hoặc gộp những biến không tương thích vào cùng một case, hãy tách việc **nhận dạng loại dữ liệu** khỏi việc **thực thi xử lý**:

```java
static String normalize(CharSequence value) {
    return value.toString().strip();
}

static String read(Object value) {
    return switch (value) {
        case String text -> normalize(text);
        case StringBuilder builder -> normalize(builder);
        case null, default -> "UNSUPPORTED";
    };
}
```

Hai phương thức này là **mã minh họa đặt trong cùng một lớp Java 21+**, không phải tệp chương trình độc lập.

- Các nhánh `String` và `StringBuilder` nhận hai loại được hỗ trợ.
- Cả hai gọi `normalize(CharSequence)` vì chúng cùng đáp ứng interface `CharSequence`.
- Một implementation `CharSequence` khác không tự được nhận, vì ta đã chọn chỉ chấp nhận hai loại cụ thể.

Nếu thực sự muốn hỗ trợ **mọi** `CharSequence`, chỉ cần một `case CharSequence chars -> normalize(chars)`. Ngược lại, nếu nghiệp vụ chỉ cho phép hai lớp, việc thay bằng case supertype sẽ **làm rộng tập đầu vào hợp lệ**, không phải refactor tương đương.

Một ví dụ dễ mắc lỗi:

```java
// CỐ Ý SAI với Java 21:
case String text, Integer number -> shared();
```

Java 21 không hỗ trợ viết nhiều type patterns khai báo biến theo cách này trong cùng một nhãn. Hơn nữa, khi một pattern khớp, biến của pattern kia không được bảo đảm đã được gắn. Hãy dùng hai case độc lập:

```java
case String text -> common(text);
case Integer number -> common(number);
```

Ở đây `common(Object)` là helper tương ứng được khai báo ở lớp chứa. Khi các nhánh có trách nhiệm giống nhau, **helper dùng chung** an toàn và rõ nghĩa hơn việc cố ép những kiểu khác nhau vào cùng một scope.

## 8. Dominance khác với scope và exhaustiveness

| Vấn đề | Bản chất | Ví dụ | Sửa phù hợp |
| --- | --- | --- | --- |
| **Dominance** | Case phía trước bao phủ case phía sau | `CharSequence` đứng trước `String` | Case cụ thể trước, hoặc bỏ case dư |
| **Scope/binding** | Biến pattern không tồn tại trên đường đi đang xét | Dùng `text` của case `String` bên trong case `Integer` | Để biến trong rule của nó; truyền đến helper |
| **Exhaustiveness** | Tập case chưa xử lý hết kiểu có thể xảy ra | `switch (Object)` chỉ có `String` | Thêm case còn thiếu, `default`, hoặc pattern tổng quát phù hợp |
| **Guard logic** | Điều kiện `when` phân chia một kiểu thành nhiều phần | `case String s when s.isBlank()` | Guard trước, case không guard sau |
| **Null policy** | Selector hoặc component có thể rỗng | `Pair(null)` khác selector `null` | Xử lý riêng vị trí có thể `null` |

**Một `switch` exhaustive vẫn có thể lỗi dominance.** Chẳng hạn `case CharSequence` trước `case String`, cộng thêm `default`, không làm nhánh `String` hợp lệ trở lại.

**Một `switch` hết lỗi dominance có thể vẫn không exhaustive.** Nếu bỏ `default` khỏi `switch` expression trên `Object`, các đối tượng không phải những kiểu được liệt kê vẫn chưa có nhánh xử lý.

**Trùng tên không phải dominance.** Với hai rule độc lập `case String value -> ...` và `case Integer value -> ...`, cùng tên `value` có thể hợp lệ vì phạm vi hai biến pattern không chồng lấn. Phải xét quan hệ kiểu và thứ tự nhãn, không chỉ so tên biến.

## 9. Những lỗi refactor thường gặp

### Chỉ đảo thứ tự mà không xét mục đích

Đổi từ `case CharSequence` rồi `case String` thành `case String` rồi `case CharSequence` sửa được dominance, nhưng cũng thay đổi **nhánh nào xử lý String**. Hãy xác nhận đây thực sự là điều mong muốn. Nếu cả hai cùng làm đúng một việc, bỏ case thừa có thể gọn hơn.

### Dùng `default` như cách che lỗi

Thêm `default -> "Unknown"` không sửa nhánh bị dominance. Với một sealed hierarchy hoặc enum đóng, thêm `default` còn có thể khiến việc bổ sung subtype/hằng trong tương lai không bắt buộc phải sửa logic theo từng trường hợp. Nếu muốn compiler nhắc xử lý trạng thái mới, hãy liệt kê các trường hợp đặc thù mà không thêm fallback tùy tiện.

### Coi `when` là chú thích không có hành vi runtime

Guard được **đánh giá khi chạy** sau khi phần pattern đã khớp. Ví dụ:

```java
case String text when auditAndAccept(text) -> handle(text);
case String text -> fallback(text);
```

Đây là **hai nhãn minh họa**, chỉ chạy khi các phương thức liên quan tồn tại. Nếu `auditAndAccept` có side effect, thay đổi thứ tự hoặc di chuyển guard có thể làm đổi số lần gọi và kết quả. Không sửa dominance bằng cách sao chép/move guard bừa bãi. Guard thuần, có tên rõ nghĩa sẽ dễ kiểm thử hơn.

### Nhầm `null` của record với `null` của selector

Một selector `null` không tự khớp record pattern `Pair(...)`; một record `Pair(null)` có selector là đối tượng `Pair` khác `null` nhưng có thành phần null. Nhánh fallback cần được thiết kế theo **vị trí null** thực tế, nhất là với pattern lồng nhau.

### Gộp logic xử lý và logic phân loại vào một case quá rộng

Đưa mọi hành động vào `case Object obj` rồi tự dùng `if` có thể hợp lệ, nhưng khiến lợi ích của pattern `switch` — compiler nhận diện các nhánh kiểu rõ ràng — bị giảm. Cân nhắc giữ các case cụ thể và chỉ trích xuất phần hành động dùng chung.

### Lạm dụng nested patterns

Một nested pattern có nhiều tầng `RecordA(RecordB(RecordC(...)))` cùng nhiều guard có thể khó bảo trì. Nếu điều kiện quá sâu, hãy tách một case outer record rồi gọi phương thức xử lý thành phần. **Rõ nghĩa quan trọng hơn số dòng ít nhất.**

## 10. Quy trình kiểm tra trước khi sửa `switch`

1. **Xem kiểu tĩnh của selector.** `Object`, interface, record, enum hay sealed type? Đây là cơ sở suy luận case nào bao phủ case nào.
2. **Viết ra tập giá trị dự kiến cho từng case.** Chẳng hạn case `String` là tập con của `CharSequence`; guard `x == y` là tập con của mọi `Point`.
3. **Xác định case nào thực sự đặc biệt.** Nếu không có hành động riêng, bỏ nhánh thừa thay vì cố giữ.
4. **Đặt nhánh cụ thể trước.** Với type hierarchy: subtype trước supertype. Với cùng record: guard trước fallback không guard. Với nested record: cấu trúc cụ thể trước deconstruction bao quát.
5. **Đưa logic dùng chung vào helper.** Nhiều case có thể gọi cùng hàm mà không cần khai báo nhiều biến trong một nhãn.
6. **Xử lý `null` có chủ đích.** Phân biệt selector `null` và thành phần record `null`.
7. **Kiểm tra exhaustiveness.** Sau khi tách hoặc xóa case, `switch` expression/enhanced statement vẫn phải bao phủ những giá trị cần thiết.
8. **Biên dịch đúng version và chạy case biên.** Với ví dụ của bài: `javac --release 21`. Thử subtype, supertype, guard đúng/sai và hai dạng `null`.

Không phải mọi switch dài đều cần nhiều case hơn. Đôi khi **loại một nhánh dư thừa** mới là cách sửa tốt nhất.

## 11. Bài tập tự kiểm tra

**Bài A — Quan hệ kiểu.** Đoạn sau có biên dịch trong Java 21 không?

```java
return switch (value) {
    case Number n -> "Number";
    case Integer i -> "Integer";
    default -> "Other";
};
```

**Đáp án:** Không. `Integer` là subtype của `Number` nên case `Integer` bị che. Nếu cần xử lý riêng số nguyên, đặt `case Integer i` trước `case Number n`. Nếu không, có thể bỏ case `Integer`.

**Bài B — Guard.** Với `record Point(int x, int y) {}`, `Point(2,3)` sẽ đi vào đâu?

```java
return switch (value) {
    case Point(int x, int y) when x == y -> "Diagonal";
    case Point(int x, int y) -> "Other point";
    default -> "Other type";
};
```

**Đáp án:** Nhánh `Other point`. Record pattern của nhánh đầu khớp, nhưng guard sai. Cấu trúc này không bị dominance vì nhánh có guard đứng trước fallback.

**Bài C — Record có thành phần rỗng.** `new Pair(null)` có khớp `case Pair(Point(int x, int y))` không? Có khớp `case Pair(var point)` không?

**Đáp án:** Không khớp pattern lồng `Point(...)`, nhưng khớp fallback `Pair(var point)` trong Java 21, với `point == null`. Nếu cần đọc thuộc tính của điểm thì phải bảo vệ trường hợp null.

**Bài D — Giới hạn nghiệp vụ.** Chỉ `String` và `StringBuilder` được hỗ trợ. Có nên thay hai nhánh thành `case CharSequence chars` để mã ngắn hơn?

**Đáp án:** Không, trừ khi yêu cầu đã mở rộng sang mọi `CharSequence`. Hai case cụ thể gọi chung helper là cách vừa tránh lặp logic vừa giữ ranh giới kiểu.

**Ghi nhớ:** Tách pattern hiệu quả nghĩa là để mỗi `case` có một phạm vi nhận giá trị dễ hiểu: **cụ thể trước, tổng quát sau, fallback rõ ràng, logic chung ở helper**. Cách này tránh dominance, giảm nhầm lẫn về biến pattern và giúp bảo trì khi hierarchy thay đổi.

## Tài liệu chính thức

- [Oracle Java 21 — Pattern Matching for switch](https://docs.oracle.com/en/java/javase/21/language/pattern-matching-switch.html).
- [Java Language Specification 21 — §14.11, Switch Statements](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.11).
- [Java Language Specification 21 — §14.30, Patterns](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.30).
- [OpenJDK JEP 441 — Pattern Matching for switch](https://openjdk.org/jeps/441).
- [OpenJDK JEP 440 — Record Patterns](https://openjdk.org/jeps/440).