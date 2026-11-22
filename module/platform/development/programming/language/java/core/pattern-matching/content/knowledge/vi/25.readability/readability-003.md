# Chọn giữa if và switch: ưu tiên tính dễ đọc khi dùng pattern matching trong Java

## 1. Mục tiêu của bài học

Trong Java, cả `if / else if / else` lẫn `switch` đều có thể điều khiển luồng chương trình. Với **pattern matching**, hai cách này càng có nhiều điểm giao nhau: có thể kiểm tra kiểu, lấy giá trị từ `record` và dùng các biến được ràng buộc để xử lý logic. Vì vậy, câu hỏi thực tế không chỉ là “cú pháp nào ngắn hơn?” mà là:

> **Cấu trúc nào giúp người đọc nhanh chóng hiểu điều kiện lựa chọn, kết quả của từng nhánh, đường đi bình thường và trường hợp chưa được xử lý?**

Bài tập trung vào việc **chọn giữa `if` và `switch` dựa trên tính dễ đọc và dễ bảo trì**. Sau bài học, bạn có thể:

- Nhận diện trường hợp `if` / guard clause rõ ràng hơn, nhất là các điều kiện độc lập và kiểm tra sớm.
- Dùng `switch` khi một giá trị đầu vào có nhiều dạng hoặc nhiều lựa chọn loại trừ nhau.
- So sánh cách viết có **type patterns**, **record patterns**, guard `when`, `switch expression`, `yield` và `sealed interface`.
- Hiểu giới hạn về `null`, thứ tự nhánh, **domination**, **exhaustiveness** và phạm vi biến pattern.
- Refactor có kiểm thử thay vì thay cú pháp chỉ vì muốn giảm số dòng.

**Phiên bản:** Pattern matching cho `instanceof` là tính năng chuẩn từ Java 16 (JEP 394); record patterns và pattern matching cho `switch` là tính năng chuẩn trong **Java 21** (JEP 440, JEP 441). Ví dụ hoàn chỉnh trong bài chạy với **JDK 21 trở lên**, không cần preview.

## 2. Quy tắc chọn nhanh: hỏi “mình đang quyết định dựa vào điều gì?”

Một cách nhìn hữu ích:

- **`if`** diễn đạt: “Nếu điều kiện này đúng, làm việc này; nếu không, kiểm tra điều kiện tiếp theo”. Điều kiện có thể dùng nhiều biến, phép so sánh, hàm predicate hoặc trạng thái độc lập.
- **`switch`** diễn đạt: “Dựa trên **một selector** (giá trị đầu vào đang xét), chọn một trong các trường hợp”. Selector có thể được so khớp với hằng, kiểu hoặc cấu trúc record. Những nhánh có thể có `when` để lọc thêm.
- **`switch expression`** còn nhấn mạnh: “Từ selector này, **tính ra một giá trị**”. Nó yêu cầu các trường hợp được bao phủ đầy đủ.
- **Guard clause bằng `if`** nhấn mạnh: “Đầu vào/điều kiện tiên quyết không hợp lệ thì thoát sớm; phần nghiệp vụ chính nằm sau”.

Bảng so sánh thực dụng:

| Tình huống | Thường ưu tiên | Lý do về tính dễ đọc |
| --- | --- | --- |
| Một hoặc hai điều kiện đơn giản | `if` | Tránh dùng nhiều cú pháp cho bài toán nhỏ. |
| Kiểm tra đầu vào không hợp lệ rồi `return`/`throw` | `if` với guard clause | Đường đi thành công không bị lồng sâu. |
| Điều kiện dựa trên **nhiều giá trị độc lập** như tuổi, quyền, hạn mức, trạng thái | `if / else if` | Mỗi predicate biểu đạt tự nhiên mà không phải ép thành selector giả. |
| Nhiều dạng của **cùng một đầu vào**: `Created`, `Changed`, `Deleted` | `switch` với type/record patterns | Các lựa chọn cùng nằm trên một mặt phẳng, dễ quét và đối chiếu. |
| Ánh xạ đầu vào thành một kết quả duy nhất | `switch expression` | Mỗi nhánh sinh một giá trị; compiler hỗ trợ kiểm tra tính đầy đủ. |
| `sealed interface` có các subtype đã biết | `switch` | Có thể liệt kê hết subtype mà không cần `default`, giúp compiler nhắc xử lý nhánh mới khi thay đổi hệ kiểu. |
| Mỗi nhánh dài, nhiều tác dụng phụ hoặc phụ thuộc trạng thái phức tạp | Cân nhắc `if` và phương thức phụ | Một `switch` lớn với nhiều block vẫn khó đọc; tách nghiệp vụ quan trọng hơn cú pháp. |
| Chỉ cần một component của một record đã biết kiểu | Accessor trực tiếp hoặc `if` đơn giản | Không cần deconstruct toàn bộ record chỉ để lấy một giá trị. |

Bảng chỉ là **hướng dẫn**, không phải quy tắc compiler. Ưu tiên cấu trúc khiến logic nghiệp vụ và các trường hợp lỗi rõ ràng nhất cho nhóm phát triển.

## 3. Khi if tốt hơn: điều kiện tuần tự, độc lập và guard clause

### 3.1. Một điều kiện rõ ràng không cần switch

Ví dụ kiểm tra đầu vào:

```java
static String title(Object raw) {
    if (raw instanceof String text && !text.isBlank()) {
        return text.strip();
    }
    return "Untitled";
}
```

Điều kiện này trả lời trực tiếp: “Nếu là chuỗi và không trắng thì sử dụng; còn lại dùng mặc định”. Viết một `switch` có `case String s when ...` và `default` cũng hợp lệ trong Java 21, nhưng không chắc dễ đọc hơn cho chỉ một phép kiểm tra.

### 3.2. Điều kiện dựa trên nhiều biến độc lập

```java
static int priority(int age, boolean vip) {
    if (age < 0) return -1;
    if (vip && age >= 65) return 3;
    if (vip || age >= 65) return 2;
    return 1;
}
```

Ở đây quyết định dựa trên **cả tuổi và trạng thái VIP**, đồng thời thứ tự ưu tiên các điều kiện có ý nghĩa. `if` mô tả trực tiếp các predicate; không cần tạo một enum hoặc chuỗi trung gian chỉ để ép sang `switch`. Đặc biệt tránh những cách viết giả lập `switch (true)`: trong Java 21, không nên dùng boolean selector như một mẹo thay thế `if`.

### 3.3. Guard clause giúp giảm nesting

```java
record Point(int x, int y) {}

static String pointLabel(Object value) {
    if (!(value instanceof Point(var x, var y))) {
        return "not a point";
    }
    if (x < 0 || y < 0) {
        return "invalid point";
    }
    return "sum=" + (x + y);
}
```

Guard đầu kiểm tra dữ liệu có khớp `Point` hay không. Nếu không khớp, phương thức kết thúc ngay. Khi đi tiếp, Java bảo đảm hai biến pattern `x` và `y` đã được ràng buộc (quy tắc **flow scoping**). Guard thứ hai xử lý điều kiện nghiệp vụ; đường thành công nằm thẳng ở cuối. Viết thành `switch` cho ba bước phụ thuộc nhau không nhất thiết làm logic dễ đọc hơn.

**Chú ý:** Pattern variable chỉ hợp lệ ở các đường điều khiển mà compiler biết pattern chắc chắn khớp. Chẳng hạn, nếu `if (!(value instanceof Point(var x, var y)))` chỉ ghi log rồi tiếp tục, bạn không thể dùng `x, y` sau đó như thể đã chắc chắn được gán.

## 4. Khi switch tốt hơn: một đầu vào, nhiều kiểu trường hợp

Giả sử hệ thống nhận các sự kiện khác dạng:

```java
sealed interface Event permits Created, Changed, Deleted {}
record Created(String id, int count) implements Event {}
record Changed(String id, int before, int after) implements Event {}
record Deleted(String id) implements Event {}
```

Yêu cầu: từ một sự kiện `Object value`, tạo nhãn:

- `Created`: `"created <id>/<count>"`.
- `Changed`: nếu `after > before`, tạo nhãn tăng trưởng; nếu không, nhãn thay đổi chung.
- `Deleted`: nhãn xóa.
- `null`: `"missing"`; kiểu khác: `"unsupported"`.

Cách viết dùng `if`:

```java
static String withIf(Object value) {
    if (value == null) return "missing";

    if (value instanceof Created(var id, var count)) {
        return "created " + id + "/" + count;
    }
    if (value instanceof Changed(var id, var before, var after)) {
        if (after > before) {
            return "growth " + id + "/" + (after - before);
        }
        return "changed " + id;
    }
    if (value instanceof Deleted(var id)) {
        return "deleted " + id;
    }
    return "unsupported";
}
```

Cách viết này hợp lý và dễ hiểu. Nhưng người đọc phải theo dõi việc từng `if` có `return` để biết nhánh nào loại trừ nhánh nào, cùng một chuỗi xử lý `value` nằm trải từ trên xuống dưới.

Cùng logic bằng `switch expression`:

```java
static String withSwitch(Object value) {
    return switch (value) {
        case null -> "missing";
        case Created(var id, var count) -> "created " + id + "/" + count;
        case Changed(var id, var before, var after) when after > before -> {
            int delta = after - before;
            yield "growth " + id + "/" + delta;
        }
        case Changed(var id, var before, var after) -> "changed " + id;
        case Deleted(var id) -> "deleted " + id;
        default -> "unsupported";
    };
}
```

Trong trường hợp này, `switch` có ưu điểm dễ nhận thấy:

1. **Một selector duy nhất:** mọi nhánh đều trả lời “`value` thuộc kiểu/trường hợp nào?”.
2. **Các nhánh nằm cùng một cấp:** dễ nhìn danh sách `Created`, `Changed`, `Deleted`.
3. **Không fall-through:** cú pháp mũi tên `->` tự tách các nhánh.
4. **Chỉ rõ giá trị kết quả:** `return switch (...)` trả về một `String`, không lặp `return` ở từng nhánh.
5. **Có thể dùng `when`:** nhánh `Changed` tăng trưởng đứng trước nhánh `Changed` tổng quát.

Nhánh `Changed ... when after > before` dùng block có hai lệnh và `yield` để đưa kết quả ra khỏi **switch expression**. Nếu nhánh chỉ có một biểu thức, không cần `yield`. Nếu chuyển thành **switch statement** với mục đích trực tiếp `return` khỏi phương thức, block có thể chứa `return` thay vì `yield`. Không nhầm `yield` (trả giá trị cho biểu thức switch) với `return` (trả giá trị cho phương thức).

Ở đây record patterns giúp lấy component `id`, `before`, `after` ngay tại nhánh `case`; mỗi record pattern phải ghi đủ component theo đúng thứ tự khai báo.

## 5. Khi switch expression đặc biệt hữu ích: tính đầy đủ nhờ sealed types

Giả sử phương thức nhận `Event` chứ không phải `Object`. Vì `Event` là `sealed interface`, compiler biết ba subtype trực tiếp được cho phép: `Created`, `Changed` và `Deleted`. Ta có thể tính nhãn bằng `switch expression` mà **không cần nhánh `default`**:

```java
static String sealedSwitch(Event event) {
    return switch (event) {
        case null -> "missing";
        case Created(var id, var count) -> "created " + id + "/" + count;
        case Changed(var id, var before, var after) when after > before
                -> "growth " + id + "/" + (after - before);
        case Changed(var id, var before, var after) -> "changed " + id;
        case Deleted(var id) -> "deleted " + id;
    };
}
```

Đây là lựa chọn có lợi cho bảo trì:

- Biểu thức `switch` phải **exhaustive**: có nhánh cho mọi trường hợp mà kiểu selector cho phép.
- Nhánh `Changed` có `when` **không đủ** bao phủ mọi `Changed` vì điều kiện có thể sai. Nhánh `Changed` không guard phía sau xử lý phần còn lại.
- Nếu code nguồn thay đổi hierarchy bằng cách thêm subtype hợp lệ vào `permits`, compiler có thể yêu cầu cập nhật `switch` khi biên dịch lại.
- Tránh thêm `default` vô điều kiện chỉ để “cho chắc” trong sealed hierarchy: `default` có thể che giấu việc quên xử lý subtype mới. Tuy vậy, cần thiết kế xử lý fallback phù hợp nếu API yêu cầu tương thích rộng.

Không phải lúc nào `switch` cũng thay thế được `if`: khi cần kiểm tra tuần tự nhiều bất biến của một object và trả lỗi **chính xác theo từng cấp**, guard clauses thường diễn đạt ý định tốt hơn.

**Lưu ý về `null`:** `case null` xử lý selector `null` có chủ đích. Không coi `default` là phương án thay thế cho `case null`; một `switch` không xử lý null có thể ném `NullPointerException` với selector null. Bài ví dụ chọn trả `"missing"`, nhưng một API khác có thể muốn ném ngoại lệ.

## 6. Ví dụ Java 21 hoàn chỉnh: cùng kết quả, hai cấu trúc

Tạo tệp **`IfOrSwitchDemo.java`**:

```java
public class IfOrSwitchDemo {
    record Point(int x, int y) {}
    sealed interface Event permits Created, Changed, Deleted {}
    record Created(String id, int count) implements Event {}
    record Changed(String id, int before, int after) implements Event {}
    record Deleted(String id) implements Event {}

    static String withIf(Object value) {
        if (value == null) return "missing";
        if (value instanceof Created(var id, var count)) {
            return "created " + id + "/" + count;
        }
        if (value instanceof Changed(var id, var before, var after)) {
            if (after > before) return "growth " + id + "/" + (after - before);
            return "changed " + id;
        }
        if (value instanceof Deleted(var id)) return "deleted " + id;
        return "unsupported";
    }

    static String withSwitch(Object value) {
        return switch (value) {
            case null -> "missing";
            case Created(var id, var count) -> "created " + id + "/" + count;
            case Changed(var id, var before, var after) when after > before -> {
                int delta = after - before;
                yield "growth " + id + "/" + delta;
            }
            case Changed(var id, var before, var after) -> "changed " + id;
            case Deleted(var id) -> "deleted " + id;
            default -> "unsupported";
        };
    }

    static String sealedSwitch(Event event) {
        return switch (event) {
            case null -> "missing";
            case Created(var id, var count) -> "created " + id + "/" + count;
            case Changed(var id, var before, var after) when after > before
                -> "growth " + id + "/" + (after - before);
            case Changed(var id, var before, var after) -> "changed " + id;
            case Deleted(var id) -> "deleted " + id;
        };
    }

    static int priority(int age, boolean vip) {
        if (age < 0) return -1;
        if (vip && age >= 65) return 3;
        if (vip || age >= 65) return 2;
        return 1;
    }

    static String pointLabel(Object value) {
        if (!(value instanceof Point(var x, var y))) return "not a point";
        if (x < 0 || y < 0) return "invalid point";
        return "sum=" + (x + y);
    }

    public static void main(String[] args) {
        Object[] values = {
            null,
            new Created("A", 2),
            new Changed("B", 3, 8),
            new Changed("C", 9, 6),
            new Deleted("D"),
            "random"
        };
        for (Object value : values) {
            String expected = withIf(value);
            System.out.println(expected + " | equal=" + expected.equals(withSwitch(value)));
        }
        System.out.println("sealed=" + sealedSwitch(new Deleted("X")));
        System.out.println("priority=" + priority(70, false));
        System.out.println("point=" + pointLabel(new Point(2, 3)));
        System.out.println("invalid=" + pointLabel(new Point(-1, 2)));
    }
}
```

Biên dịch và chạy bằng JDK 21+:

```bash
javac --release 21 IfOrSwitchDemo.java
java IfOrSwitchDemo
```

**Kết quả chính xác:**

```text
missing | equal=true
created A/2 | equal=true
growth B/5 | equal=true
changed C | equal=true
deleted D | equal=true
unsupported | equal=true
sealed=deleted X
priority=2
point=sum=5
invalid=invalid point
```

Phân tích:

- Sáu dòng đầu so sánh kết quả từ `withIf` với `withSwitch` trên cùng một giá trị. `equal=true` xác nhận hai cách cho cùng chuỗi trong sáu trường hợp: null, tạo mới, tăng trưởng, thay đổi không tăng, xóa và kiểu không hỗ trợ.
- `Changed("B", 3, 8)` thỏa `after > before` nên tính chênh lệch `5`; `Changed("C", 9, 6)` đi vào nhánh `Changed` không guard và nhận nhãn chung.
- `sealed=deleted X` cho thấy `switch` trên `Event` bao phủ hierarchy mà không cần `default`.
- `priority=2` minh họa `if` phù hợp với điều kiện tuổi và VIP độc lập (tuổi 70, không VIP).
- `point=sum=5` và `invalid=invalid point` minh họa guard clause với một cấu trúc `Point` đã khớp; kiểm tra tọa độ âm rõ ràng hơn nếu giữ thành một `if` riêng.

Các giá trị `equal=true` trong ví dụ là **kiểm thử hồi quy cho sáu trường hợp**, không phải chứng minh mọi biến thể dữ liệu đều tương đương. Trong dự án thật, bổ sung biên dữ liệu, null ở component, giá trị âm và hành vi ngoại lệ trước khi thay toàn bộ mã cũ.

## 7. Phân biệt switch statement và switch expression trước khi chọn

Cả hai cùng dùng từ khóa `switch`, nhưng mục đích không giống nhau.

**Switch expression** tạo ra một giá trị:

```java
static String category(Object input) {
    return switch (input) {
        case null -> "none";
        case String s -> "text";
        case Integer n when n >= 0 -> "nonnegative number";
        case Integer n -> "negative number";
        default -> "other";
    };
}
```

**Switch statement** thực hiện các hành động/câu lệnh. Ví dụ khi cần log theo loại dữ liệu:

```java
static void logType(Object input) {
    switch (input) {
        case null -> System.out.println("none");
        case String s -> System.out.println("text: " + s);
        default -> System.out.println("other");
    }
}
```

Nếu mục tiêu chủ yếu là **tính một giá trị** như nhãn, phân loại hoặc DTO, `switch expression` thường gọn và giúp compiler kiểm tra các nhánh có tạo kết quả đầy đủ. Nếu các nhánh chỉ thực hiện câu lệnh như log hoặc gọi dịch vụ, `switch statement` hoặc các phương thức nhỏ có thể phù hợp hơn.

Với `switch expression`, nhánh nhiều lệnh cần `yield`:

```java
// Ví dụ minh họa bên trong phương thức trả về int.
return switch (input) {
    case String s -> {
        String normalized = s.strip();
        yield normalized.length();
    }
    case Integer n -> n;
    default -> 0;
};
```

`yield` cung cấp giá trị cho **biểu thức switch**; `return` trả giá trị cho **phương thức**. Không dùng `break 5;` để thay `yield 5;`. Cũng không viết block của một nhánh expression mà mọi đường chạy bình thường kết thúc không có giá trị.

## 8. Những quy tắc quan trọng để switch vẫn dễ đọc

### 8.1. Nhánh cụ thể trước nhánh bao quát

Cú pháp sau có ý định tính tăng trưởng nhưng thứ tự không hợp lệ:

```java
// Sai: nhánh Changed không guard ở trước che khuất nhánh khi after > before.
return switch (value) {
    case Changed(var id, var before, var after) -> "changed " + id;
    case Changed(var id, var before, var after) when after > before
            -> "growth " + id;
    default -> "other";
};
```

Nhánh `Changed` không guard khớp mọi `Changed`, nên nhánh có `when` phía sau bị **dominated**. Đưa nhánh có `when` lên trước. Cách này tương tự việc sắp xếp một chuỗi `if / else if`: nếu điều kiện tổng quát đứng trước, điều kiện đặc thù có thể không còn cơ hội chạy. Khác biệt là compiler của pattern `switch` có khả năng phát hiện một số nhánh bị bao phủ như vậy.

### 8.2. Guard `when` nên ngắn và thể hiện điều kiện nghiệp vụ

`case Changed(var id, var before, var after) when after > before -> ...` nói rõ điều kiện chọn nhánh. Nếu guard cần nhiều truy cập I/O, nhiều side effects hoặc logic khó đọc, hãy đưa tính toán vào phương thức thuần với tên có ý nghĩa. `when` không phải là lệnh `return` sớm: khi guard false, Java tiếp tục xét case phù hợp khác.

### 8.3. Tránh record pattern quá sâu khi chỉ cần một dữ liệu

Ví dụ `case Order(Customer(Address(var city, ...), ...), ...)` có thể hữu ích khi ta cần **vừa kiểm tra cấu trúc vừa lấy thành phố**. Nhưng nếu chỉ cần xác định một object là `Order` rồi chuyển toàn bộ record cho một phương thức, `case Order order -> handle(order)` hoặc một `if (input instanceof Order order)` có thể rõ hơn. Đừng deconstruct mọi component chỉ để tạo ra một cây ngoặc dài.

### 8.4. Dùng default có chủ đích

Với selector mở như `Object`, thông thường cần `default` vì có nhiều kiểu ngoài những case đã viết. Với một hierarchy `sealed` đã biết đầy đủ, việc liệt kê tất cả subtype không `default` có thể giúp compiler phát hiện thiếu nhánh sau khi mã nguồn hierarchy thay đổi.

Tuy nhiên `default` không thay thế tự động `case null`. Đầu vào `null` cần xử lý rõ theo hợp đồng ứng dụng, bằng `case null` hoặc kiểm tra trước.

### 8.5. Đặt tên pattern variables có ý nghĩa

`case Changed(var id, var before, var after)` đọc tốt hơn biến tên `a, b, c`. Với record có nhiều trường nhưng chỉ dùng một component, Java 21 vẫn yêu cầu khai báo đủ vị trí; dùng tên như `var ignoredField` cho component không dùng. Unnamed pattern `_` là tính năng chuẩn từ Java 22, không đưa vào mã yêu cầu `--release 21`.

## 9. Khi không nên refactor if thành switch

Đừng chuyển mọi `if / else` sang `switch` chỉ vì có cú pháp mới. Có những dấu hiệu `if` dễ đọc hơn:

1. **Điều kiện không cùng một selector**: ví dụ `age >= 18`, `account.active()`, `quota > 0` có ý nghĩa độc lập.
2. **Một loạt điều kiện tiên quyết phải đúng cùng lúc**, cần thông báo lỗi riêng: guard clauses theo thứ tự giúp giữ hợp đồng lỗi.
3. **Nhánh thành công cần tiếp tục xử lý sau phần kiểm tra**: guard clauses có `return`/`throw` sớm để phần nghiệp vụ nằm thẳng ở cuối.
4. **Chỉ một nhánh xử lý đặc biệt**: `if (value instanceof Foo f)` có thể ngắn và tự nhiên hơn switch có hai case.
5. **Nhánh xử lý phức tạp**, không phải một phép phân loại: tách phương thức `processCreated`, `processChanged` có thể tạo cải thiện lớn hơn đổi `if` thành `switch`.

Tương tự, đừng ép dữ liệu thành enum giả chỉ để có thể dùng switch nếu logic gốc vốn là nhiều điều kiện kết hợp độc lập. Mục tiêu là **minh bạch luật nghiệp vụ**, không phải loại bỏ từ khóa `if`.

### Dễ đọc không đồng nghĩa hiệu năng luôn tốt hơn

Không có quy tắc chung “`switch` nhanh hơn `if`” cho mọi pattern matching. Cả hai đều được compiler và JVM tối ưu tùy loại dữ liệu, thứ tự nhánh và runtime. Với logic thông thường, ưu tiên lựa chọn có thể đọc, review và kiểm thử; chỉ tối ưu hiệu năng sau khi có đo lường trên đường chạy quan trọng.

## 10. Checklist khi review và refactor

Khi quyết định giữ `if` hay chuyển sang `switch`, tự hỏi:

1. **Một hay nhiều selector?** Nếu nhiều điều kiện độc lập, `if` thường tự nhiên. Nếu cùng một selector với nhiều dạng, `switch` là ứng viên tốt.
2. **Mục tiêu là trả một giá trị?** Nếu có, cân nhắc `switch expression`; nếu là kiểm tra điều kiện rồi tiếp tục, guard clause có thể rõ hơn.
3. **Các nhánh có loại trừ nhau không?** `switch` với `->` làm ranh giới các case rõ ràng; `if` cần giữ thứ tự và các `return`/`else` hợp lý.
4. **Có subtype đã biết không?** Với `sealed`, switch có lợi thế exhaustive checking.
5. **Có null và lỗi cần phân biệt không?** Phải bảo toàn hành vi `null`, ngoại lệ, thứ tự lỗi và kết quả mặc định.
6. **Pattern variables có phạm vi rõ không?** Biến của case chỉ dùng trong guard/nhánh hợp lệ; với `if`, chú ý flow scoping sau `return`.
7. **Có nhánh bị che khuất không?** Đặt case có `when` đặc thù trước case type/record bao quát.
8. **Có ít lặp và dễ mở rộng không?** Nếu mỗi case dài hàng chục dòng, trích phương thức để phần lựa chọn chỉ còn là tên hành động/nghiệp vụ.
9. **Đã kiểm thử trước–sau chưa?** So sánh cả happy path, dữ liệu không hợp lệ, null, subtype mới và các giá trị biên.

Khi review một PR, nhận xét “đổi sang switch cho hiện đại” không đủ mạnh bằng nhận xét “các nhánh này đều phân loại cùng một Event; switch biểu diễn đầy đủ subtype, cho thấy rõ nhánh mới còn thiếu”. Tương tự, hãy giữ `if` khi nó giúp nhận diện các bất biến và lỗi theo trình tự.

## 11. Bài tập thực hành: chọn cấu trúc rồi giải thích vì sao

### Bài A — Các loại kết quả độc lập

Cho các record:

```java
sealed interface OperationResult permits Success, Invalid, Retry {}
record Success(String id) implements OperationResult {}
record Invalid(String reason) implements OperationResult {}
record Retry(int seconds) implements OperationResult {}
```

Viết phương thức `static String message(OperationResult result)` trả:

- `Success("A1")` → `"ok:A1"`
- `Invalid("bad input")` → `"invalid:bad input"`
- `Retry(5)` → `"retry:5"`
- null → `"no result"`

**Lời giải:** Chọn `switch expression` vì đầu vào là **một hierarchy sealed**, các nhánh được xác định theo loại và mục tiêu là trả chuỗi.

```java
static String message(OperationResult result) {
    return switch (result) {
        case null -> "no result";
        case Success(var id) -> "ok:" + id;
        case Invalid(var reason) -> "invalid:" + reason;
        case Retry(var seconds) -> "retry:" + seconds;
    };
}
```

Mọi subtype trực tiếp được bao phủ, không cần `default`. Nếu yêu cầu thêm loại kết quả mới, switch không có default giúp compiler phát hiện việc cần cập nhật xử lý khi build lại.

### Bài B — Nhiều điều kiện tiên quyết tuần tự

Cho phương thức nhận `Object value`, chỉ chấp nhận `String` không rỗng, độ dài tối đa 8. Yêu cầu thông báo lỗi khác nhau cho sai kiểu, chuỗi trắng và quá dài; nếu hợp lệ trả chính chuỗi đã chuẩn hóa.

**Lời giải:** Chọn `if` với guard clauses để các điều kiện theo thứ tự được đọc rõ ràng:

```java
static String normalize(Object value) {
    if (!(value instanceof String text)) return "wrong type";
    String normalized = text.strip();
    if (normalized.isEmpty()) return "blank";
    if (normalized.length() > 8) return "too long";
    return normalized;
}
```

Các điều kiện không phải là bốn “loại object” khác nhau; chúng là các bước kiểm tra tuần tự trên một giá trị đã được xác minh kiểu. Guard clauses giúp bảo toàn ưu tiên lỗi mà không làm lồng sâu phần kết quả thành công.

### Bài C — Khi nào phải dùng cả hai?

Giả sử một `Event` có ba subtype nhưng riêng `Changed` phải kiểm tra nhiều điều kiện nghiệp vụ và gọi dịch vụ. Bạn có thể dùng `switch` để **điều phối theo subtype**, rồi gọi phương thức `handleChanged(Changed c)`. Bên trong phương thức đó, dùng **`if`/guard clauses** để kiểm tra các bất biến nghiệp vụ. Đừng bắt toàn bộ công việc xảy ra trong một case dài.

Cách kết hợp này thường dễ review hơn một chuỗi `if` khổng lồ hoặc một `switch` chứa quá nhiều block lồng nhau.

## 12. Kết luận

**Chọn `if` khi bạn đang kiểm tra điều kiện; chọn `switch` khi bạn đang lựa chọn giữa các trường hợp của một giá trị.** Nếu mục tiêu còn là tạo ra một kết quả, `switch expression` giúp việc ánh xạ đầu vào sang đầu ra rõ và được compiler kiểm tra tính đầy đủ. Khi điều kiện nghiệp vụ độc lập, có thứ tự ưu tiên hoặc cần guard clauses, `if` thường giữ được luồng kiểm soát dễ hiểu hơn.

Không có cấu trúc thắng trong mọi tình huống. Hãy đánh giá tính dễ đọc bằng câu hỏi: người bảo trì có thấy ngay **đầu vào nào được xử lý, nhánh nào sinh kết quả, nhánh nào có thể bị bỏ sót và mã sẽ phản ứng thế nào với null hoặc dữ liệu mới** hay không.

**Tham khảo:** [JEP 394 — Pattern Matching for instanceof](https://openjdk.org/jeps/394), [JEP 440 — Record Patterns](https://openjdk.org/jeps/440), [JEP 441 — Pattern Matching for switch](https://openjdk.org/jeps/441), [Oracle Java 21 — Pattern Matching for switch](https://docs.oracle.com/en/java/javase/21/language/pattern-matching-switch.html), [Java SE 21 Language Specification — Switch Expressions](https://docs.oracle.com/javase/specs/jls/se21/html/jls-15.html#jls-15.28).
