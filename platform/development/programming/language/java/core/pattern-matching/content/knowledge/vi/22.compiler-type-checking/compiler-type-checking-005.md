# Dominance analysis trong Pattern Matching (Java 21)

## 1. Mục tiêu và vị trí của dominance analysis

Khi dùng pattern matching trong `switch`, một giá trị có thể khớp với **nhiều** nhánh: ví dụ `String` vừa là `String` vừa là `CharSequence`; một record `Point(2, 2)` có thể khớp cả mẫu `Point(var x, var y)` lẫn mẫu có điều kiện `when x == y`. Java chọn nhánh áp dụng theo thứ tự mã nguồn. Để chương trình dễ dự đoán và tránh các nhánh chắc chắn bị che khuất, **compiler thực hiện dominance analysis** đối với nhãn `case`.

Trong Java 21, **dominance** (quan hệ bao phủ giữa các pattern/nhãn) là một quy tắc **kiểm tra tại thời điểm biên dịch**. Một nhãn phía sau bị coi là *dominated* nếu compiler xác định rằng một nhãn đứng trước đã bao phủ mọi giá trị mà nhãn phía sau có thể áp dụng. Đó là lỗi biên dịch, chứ không phải chỉ là nhánh ít khả năng chạy.

Sau bài học, bạn có thể:

- Giải thích dominance giữa type patterns như `CharSequence cs` và `String s`.
- Sắp xếp nhánh hằng số, nhánh có guard `when`, nhánh tổng quát, `null` và `default`.
- Nhận diện trường hợp đặc biệt `when true` và lý do compiler không cố chứng minh mọi mệnh đề `when`.
- Áp dụng dominance cho **record patterns**, bao gồm nested record patterns và component patterns.
- Phân biệt **dominance**, **exhaustiveness** (tính đầy đủ) và **flow scoping** của pattern variables.
- Đọc lỗi `this case label is dominated by a preceding case label` và sửa theo đúng quy tắc.

**Yêu cầu phiên bản:** Pattern matching cho `switch` (JEP 441) và record patterns (JEP 440) chính thức từ Java 21. Ví dụ thực hành dùng `javac --release 21` và không cần bật preview.

## 2. Compiler phân tích điều gì?

Xét ví dụ cố ý sai:

```java
static String describe(Object value) {
    return switch (value) {
        case CharSequence chars -> "sequence: " + chars.length();
        case String text -> "text: " + text; // LỖI dominance
        default -> "other";
    };
}
```

`String` là subtype của `CharSequence`. Do đó mọi giá trị không `null` match `case String text` cũng match `case CharSequence chars`. Nhánh `CharSequence` đứng trước, không có guard nên luôn được chọn cho các giá trị `String`; nhánh `String` phía sau bị dominated. Compiler Java 21 báo lỗi tại nhánh thứ hai.

Cách sửa là đặt **kiểu cụ thể trước kiểu tổng quát**:

```java
static String describe(Object value) {
    return switch (value) {
        case String text -> "text: " + text;
        case CharSequence chars -> "sequence: " + chars.length();
        default -> "other";
    };
}
```

Tư duy kiểm tra theo hai bước:

1. Xác định **tập giá trị** mà nhãn phía sau có thể áp dụng.
2. Kiểm tra một nhãn **đứng trước và không bị guard hạn chế** có bao phủ toàn bộ tập giá trị đó theo quy tắc ngôn ngữ hay không.

Về mặt định tính, nếu nhãn A bao phủ mọi giá trị mà nhãn B có thể nhận, A đứng trước B thì B không còn cơ hội được chọn. Tuy nhiên, không được coi đây là một bộ giải mọi biểu thức boolean tùy ý: Java quy định cách xác định dominance chủ yếu dựa trên **quan hệ kiểu**, cấu trúc pattern và một vài trường hợp xác định được ở thời điểm biên dịch.

### Vì sao compiler kiểm tra trước khi chạy?

Compiler đã biết kiểu khai báo của biến selector và kiểu của từng pattern. Nó có thể suy ra quan hệ subtype/bao phủ mà không cần chạy chương trình. Việc chặn nhánh bị dominated giúp tránh nhầm lẫn do đặt sai thứ tự. Khi nhiều nhánh **hợp lệ** cùng có thể match, runtime vẫn xét từ trên xuống và chọn nhãn áp dụng đầu tiên.

**Lưu ý:** Một nhánh sai dominance không được "bỏ qua tự động" để chương trình vẫn biên dịch. Phải sửa thứ tự hoặc nội dung nhãn.

## 3. Dominance giữa type patterns

### 3.1. Quan hệ kiểu cha – con

Ví dụ `String implements CharSequence`, `Integer extends Number`:

```java
// Hợp lệ: kiểu hẹp trước, kiểu rộng sau.
return switch (value) {
    case String s -> "string: " + s;
    case CharSequence cs -> "char sequence";
    case Integer i -> "integer: " + i;
    case Number n -> "number: " + n;
    case null -> "null";
    default -> "other";
};
```

Trong đoạn trên, `value` có kiểu `Object`. Nhánh `Integer` đứng trước `Number`; nhánh `String` đứng trước `CharSequence`. Hai cặp có thể match cùng một giá trị ở runtime, nhưng nhánh cụ thể được đặt trước nên không bị che khuất.

Đảo thứ tự:

```java
// CỐ Ý SAI: Integer bị Number bao phủ.
return switch (value) {
    case Number n -> "number";
    case Integer i -> "integer"; // LỖI
    default -> "other";
};
```

Lỗi không phải do `Integer` hoặc `Number` không dùng được với `Object`; lỗi là **thứ tự nhãn làm nhánh sau không thể được chọn**.

### 3.2. Pattern không phụ thuộc tên biến

Hai nhánh có cùng type pattern nhưng chỉ khác tên biến cũng bị dominance nếu nhánh đầu không guard:

```java
// CỐ Ý SAI:
return switch (value) {
    case String first -> "first";
    case String second -> "second"; // LỖI
    default -> "other";
};
```

Tên `first`/`second` chỉ là tên pattern variable, không làm mẫu phân biệt thêm trạng thái nào. Đặt thêm một nhánh không có guard với cùng kiểu không tạo ra điều kiện mới.

### 3.3. Pattern rộng bao phủ một nhánh hằng số

Trường hợp selector có kiểu phù hợp với hằng số (ví dụ `Integer`), pattern `Integer i` có thể bao phủ nhãn `case 0`:

```java
// CỐ Ý SAI:
return switch (value) {
    case Integer i -> "integer";
    case 0 -> "zero"; // LỖI: đã bị nhánh Integer bao phủ
    case null -> "null";
};
```

Tại đây `value` có kiểu `Integer`. Khắc phục: đưa hằng số **lên trước** nhánh tổng quát, xem ví dụ trong phần 5. Hằng số trùng nhau cũng là lỗi riêng của `switch`; không nên gọi mọi lỗi hằng số lặp là dominance.

## 4. Guard `when` ảnh hưởng dominance như thế nào?

Guard bổ sung một điều kiện boolean sau khi pattern đã match:

```java
return switch (value) {
    case String s when s.isBlank() -> "blank";
    case String s -> "other string";
    default -> "other type";
};
```

Ví dụ **hợp lệ**. Nhãn đầu chỉ chọn `String` nếu `s.isBlank()` là `true`. Nhãn tiếp theo dành cho những chuỗi không thỏa guard trước. Đây là một lối viết rất thường gặp: **case có guard ở trên, case không guard ở dưới**.

Đảo hai nhánh:

```java
// CỐ Ý SAI:
return switch (value) {
    case String s -> "any string";
    case String s when s.isBlank() -> "blank"; // LỖI dominated
    default -> "other";
};
```

Ở nhánh đầu, `String s` không guard bao phủ mọi chuỗi, nên nhánh có guard phía dưới không thể được chọn.

### 4.1. Guard thường không được dùng làm chứng minh dominance

Ví dụ sau được chấp nhận ở Java 21:

```java
return switch (value) {
    case String s when s.length() >= 0 -> "first";
    case String s -> "fallback";
    default -> "other";
};
```

Với một `String` thực tế, độ dài luôn không âm, nên nhánh fallback không có cơ hội chạy theo logic của biểu thức này. **Compiler vẫn không suy luận và dùng ý nghĩa tổng quát của `s.length() >= 0` để đánh dấu dominated.** Quy tắc dominance đối với guard được giới hạn có chủ đích; không phải mọi điều kiện tương đương "luôn đúng" đều được compiler chứng minh.

### 4.2. Ngoại lệ quan trọng: `when true`

Một guard là **constant expression có giá trị `true`** được xem như nhánh không guard trong phân tích dominance:

```java
// CỐ Ý SAI:
return switch (value) {
    case String s when true -> "string";
    case String s -> "again"; // LỖI dominated
    default -> "other";
};
```

`when true` làm nhánh đầu bao phủ mọi `String`. Ngược lại, `when false` với giá trị hằng `false` bị Java 21 **cấm ngay lúc biên dịch** (một lỗi guard riêng), không phải mẹo để tạm tắt nhánh.

### 4.3. Đừng dựa vào compiler để chứng minh tính rời nhau

Hai guard như `when n > 10` và `when n > 5` có thể cùng đúng. Nếu được đặt liên tiếp, nhánh đầu ưu tiên với mọi `n > 10`; nhánh thứ hai xử lý các giá trị còn lại thỏa điều kiện thứ hai. Compiler không thay bạn quyết định cách phân chia khoảng giá trị theo ý định nghiệp vụ.

Quy tắc thực tế dễ hiểu: **hằng số cụ thể → pattern có guard cụ thể → pattern không guard tổng quát**. Đây là gợi ý sắp xếp code để dễ đọc; mối quan hệ có/không dominance vẫn phải xét theo các quy tắc chính thức.

## 5. Hằng số, `null` và `default`

Ví dụ selector có kiểu `Integer`:

```java
static String numberKind(Integer value) {
    return switch (value) {
        case 0 -> "zero";
        case Integer i when i > 0 -> "positive";
        case Integer i -> "negative";
        case null -> "null integer";
    };
}
```

- `case 0` đặt trước, để không bị `case Integer i` bao phủ.
- `case Integer i when i > 0` xử lý số dương còn lại.
- `case Integer i` không guard xử lý các số nguyên không `null` chưa được chọn, lúc này là số âm.
- `case null` xử lý selector `null`.

**`null` cần xử lý riêng khi API yêu cầu.** Một type pattern như `case Integer i` không thay thế `case null`. Nếu `switch` gặp `null` và không có nhánh phù hợp, thông thường phát sinh `NullPointerException`; `default` đơn lẻ không tự biến thành nhánh nhận `null`.

### 5.1. `default` và pattern bao phủ kiểu selector

Khi selector là `Object`, nhánh `case Object o` không guard là một pattern **unconditional** cho kiểu selector. Nếu viết thêm `default`, compiler có thể báo:

```java
// CỐ Ý SAI:
return switch (value) {
    case Object o -> "something";
    default -> "other"; // LỖI: cả unconditional pattern và default
};
```

Pattern `Object o` ở đây đã đảm nhiệm vai trò giống nhánh mặc định cho các giá trị không `null`. Cần chọn một cách tổ chức hợp lý; không xếp hai nhãn tổng quát chồng lên nhau. `case null` vẫn là nhãn riêng nếu muốn xử lý `null`.

Trong cấu trúc có pattern, hãy đặt `default` sau các nhánh đặc thù. Java 21 coi việc để `default` đứng trước pattern hoặc nhãn `null` là lỗi; có một số ngoại lệ tương thích với legacy `switch` chỉ chứa hằng số, nhưng không phải phong cách phù hợp cho pattern matching.

### 5.2. Không nhầm các lỗi của `switch`

| Tình huống | Vấn đề |
| --- | --- |
| `case Integer i` trước `case 0` | Hằng số phía sau bị dominated |
| Hai nhãn `case 0` cùng giá trị | Lỗi hằng số trùng, độc lập với dominance của pattern |
| `case Object o` và `default` trong `switch(Object)` | Có hai nhánh mang tính bao phủ toàn bộ |
| `case null` lặp lại | Lỗi nhãn `null` trùng |
| `switch` expression bỏ sót các kiểu còn lại | Lỗi **không exhaustive**, khác dominance |
| `case String s when false` | Lỗi guard hằng `false`, không đồng nghĩa với dominance |

## 6. Dominance cho record patterns và nested patterns

Không chỉ type pattern, record patterns cũng tham gia dominance. Xét:

```java
record Point(int x, int y) {}
record Holder(Point point) {}
```

Một record pattern có thể tách các component:

```java
case Point(var x, var y) -> ...
```

Trong phân tích dominance, **type pattern bao phủ kiểu record** có thể dominate record pattern. Với hai record patterns của **cùng một record class**, Java 21 còn so các **component patterns tương ứng** theo quan hệ bao phủ (xem JLS §14.30.3). Điều này tạo ra quy tắc đệ quy cho các record lồng nhau.

Ví dụ cố ý sai:

```java
// CỐ Ý SAI:
return switch (value) {
    case Holder(var p) -> "any Holder";
    case Holder(Point(var x, var y)) -> "Holder with Point"; // LỖI
    default -> "other";
};
```

Lý do: với record `Holder`, `var p` là component pattern tổng quát cho component kiểu `Point`. Nếu nested `Point(var x, var y)` match, component cũng được nhận bởi `var p`. Vì vậy `Holder(var p)` đứng trước che nhánh nested phía sau.

Cách đúng:

```java
return switch (value) {
    case Holder(Point(var x, var y)) -> "Holder point";
    case Holder(var p) -> "Other Holder";
    default -> "other";
};
```

Có thể thêm `when` để phân loại cụ thể hơn:

```java
return switch (value) {
    case Holder(Point(var x, var y)) when x == y -> "diagonal";
    case Holder(Point(var x, var y)) -> "point";
    case Holder(var p) -> "holder without point";
    default -> "other";
};
```

Ở đây `value` có kiểu `Object`. Nếu `value` là `new Holder(null)`, nested `Point(...)` không match `null`, nhưng `Holder(var p)` có thể match với `p == null`. Nếu chính selector bằng `null`, không có record pattern nào match, và muốn xử lý riêng thì thêm `case null`.

### Dominance không đồng nghĩa với "mọi record pattern đều unconditional"

Một record pattern không được xem là unconditional cho kiểu ngoài nói chung, vì `null` không match record pattern. Tuy nhiên, một record pattern **rộng hơn về component** vẫn có thể dominate một record pattern hẹp hơn của cùng record class. Phân biệt hai quy tắc này giúp tránh nhầm với nhánh `default`.

## 7. Phân biệt dominance với exhaustiveness

**Dominance** hỏi: *Có nhánh nào phía sau chắc chắn bị nhánh trước che khuất không?*  
**Exhaustiveness** hỏi: *Có đủ nhánh để xử lý tất cả các giá trị thuộc miền kiểu của selector mà compiler cần xét không?*

Một `switch` expression có thể:

- **Không dominated nhưng chưa exhaustive:** chỉ có `case String s` cho selector kiểu `Object` và thiếu `default`.
- **Exhaustive nhưng dominated:** có `default`, song đặt `case CharSequence cs` trước `case String s`; compiler vẫn từ chối.
- **Vừa exhaustive vừa không dominated:** sắp xếp đúng các nhánh đặc biệt, nhánh tổng quát và xử lý `null` theo yêu cầu.

Đối với **sealed interface**, compiler biết danh sách subtype được phép, nên có thể kiểm tra tính đầy đủ mà không cần `default`:

```java
sealed interface Shape permits Circle, Square {}
record Circle(int radius) implements Shape {}
record Square(int side) implements Shape {}

static String shapeKind(Shape shape) {
    return switch (shape) {
        case Circle(var r) when r <= 0 -> "invalid circle";
        case Circle(var r) -> "circle: " + r;
        case Square(var s) -> "square: " + s;
        case null -> "null shape";
    };
}
```

`Circle(var r)` có guard đứng trước nhánh `Circle` tổng quát, nên không có dominance. Hai subtype `Circle` và `Square` đã được bao phủ: `switch` exhaustive theo sealed type. Không cần `default`; `case null` chỉ là lựa chọn xử lý `null` tường minh. Nếu mở rộng sealed hierarchy về sau, compiler có thể giúp chỉ ra chỗ cần thêm case.

### Dominance và flow scoping là hai lớp kiểm tra khác nhau

Trong `case Point(var x, var y) when x == y`, biến `x`/`y` có phạm vi hợp lệ để dùng trong guard và body của nhánh. Điều này thuộc **flow scoping/pattern binding**. Quan hệ dominance lại quyết định **toàn bộ nhánh case có thể được chọn hay không**. Một pattern có biến hợp lệ vẫn có thể bị dominated nếu đặt dưới một pattern bao phủ rộng hơn.

## 8. Chương trình Java 21 hoàn chỉnh

Tạo tệp **`DominanceAnalysisDemo.java`** với nội dung sau; đây là chương trình chạy độc lập, không phải các đoạn code sai cố ý minh họa ở trên:

```java
public class DominanceAnalysisDemo {
    record Point(int x, int y) {}
    record Holder(Point point) {}

    sealed interface Shape permits Circle, Square {}
    record Circle(int radius) implements Shape {}
    record Square(int side) implements Shape {}

    static String classify(Object value) {
        return switch (value) {
            case String s when s.isBlank() -> "blank string";
            case String s when s.length() > 3 -> "long string: " + s;
            case String s -> "string: " + s;
            case CharSequence cs -> "other CharSequence: " + cs.length();
            case Point(var x, var y) when x == y -> "diagonal: " + x;
            case Point(var x, var y) -> "point: " + x + "," + y;
            case Integer i -> "integer: " + i;
            case Number n -> "number: " + n;
            case null -> "null";
            default -> "other";
        };
    }

    static String numberKind(Integer value) {
        return switch (value) {
            case 0 -> "zero";
            case Integer i when i > 0 -> "positive";
            case Integer i -> "negative";
            case null -> "null integer";
        };
    }

    static String nested(Object value) {
        return switch (value) {
            case Holder(Point(var x, var y)) when x == y ->
                    "holder diagonal: " + x;
            case Holder(Point(var x, var y)) ->
                    "holder point: " + x + "," + y;
            case Holder(var p) -> "holder without point";
            case null -> "null holder";
            default -> "not holder";
        };
    }

    static String shapeKind(Shape shape) {
        return switch (shape) {
            case Circle(var radius) when radius <= 0 -> "invalid circle";
            case Circle(var radius) -> "circle: " + radius;
            case Square(var side) -> "square: " + side;
            case null -> "null shape";
        };
    }

    public static void main(String[] args) {
        System.out.println(classify("   "));
        System.out.println(classify("Java"));
        System.out.println(classify("hi"));
        System.out.println(classify(new StringBuilder("ab")));
        System.out.println(classify(new Point(2, 2)));
        System.out.println(classify(new Point(2, 5)));
        System.out.println(classify(7));
        System.out.println(classify(2.5));
        System.out.println(classify(null));
        System.out.println(classify(new Object()));

        System.out.println(numberKind(0));
        System.out.println(numberKind(8));
        System.out.println(numberKind(-3));
        System.out.println(numberKind(null));

        System.out.println(nested(new Holder(new Point(4, 4))));
        System.out.println(nested(new Holder(new Point(4, 5))));
        System.out.println(nested(new Holder(null)));
        System.out.println(nested("hello"));

        System.out.println(shapeKind(new Circle(3)));
        System.out.println(shapeKind(new Circle(0)));
        System.out.println(shapeKind(new Square(2)));
        System.out.println(shapeKind(null));
    }
}
```

Biên dịch và chạy bằng JDK 21 hoặc mới hơn:

```bash
javac --release 21 DominanceAnalysisDemo.java
java DominanceAnalysisDemo
```

**Kết quả stdout thực tế:**

```text
blank string
long string: Java
string: hi
other CharSequence: 2
diagonal: 2
point: 2,5
integer: 7
number: 2.5
null
other
zero
positive
negative
null integer
holder diagonal: 4
holder point: 4,5
holder without point
not holder
circle: 3
invalid circle
square: 2
null shape
```

Giải thích các nhóm kết quả:

1. **`classify`:** nhánh `String` có guard đứng trước `String` tổng quát, rồi mới đến kiểu cha `CharSequence`. `Integer` đứng trước `Number`. Các `Point` dùng guard trước nhánh record tổng quát. Chương trình kiểm tra tính hợp lệ của thứ tự pattern qua đầu ra đa dạng.
2. **`numberKind`:** nhánh `case 0` đứng trước các nhánh có pattern; guard số dương đứng trước `Integer` không guard; `null` được xử lý riêng.
3. **`nested`:** các nested `Point(...)` có guard và không guard đứng trước `Holder(var p)`. Với `Holder(null)`, nhánh nested không match và nhánh rộng hơn nhận record.
4. **`shapeKind`:** sealed hierarchy cho phép switch expression đầy đủ mà không cần `default`; nhánh `Circle` có guard không dominate nhánh `Circle` chung.

Toàn bộ chương trình dùng Java 21 và không phụ thuộc thư viện bên ngoài JDK.

## 9. Các lỗi dominance đã được kiểm chứng với `javac`

Một đoạn code không được biên dịch là minh họa hữu ích để hiểu quy tắc compiler. Những ví dụ sau **cố ý sai**, không nên thêm vào tệp chương trình chạy ở mục 8.

### 9.1. Pattern kiểu cha đứng trước kiểu con

```java
// Selector là Object.
return switch (obj) {
    case CharSequence cs -> "wide";
    case String s -> "narrow"; // lỗi: dominated
    default -> "other";
};
```

**Sửa:** `String` trước `CharSequence`.

### 9.2. Nhánh không guard đứng trước nhánh cùng kiểu có guard

```java
return switch (obj) {
    case String s -> "all strings";
    case String s when s.isBlank() -> "blank"; // lỗi: dominated
    default -> "other";
};
```

**Sửa:** nhánh `when` trước nhánh `String s` không guard.

### 9.3. Guard là hằng `true`

```java
return switch (obj) {
    case String s when true -> "all strings";
    case String s -> "again"; // lỗi: dominated
    default -> "other";
};
```

**Sửa:** bỏ guard hằng `true` dư thừa, hoặc bỏ case lặp. Không nhầm với `when predicate(...)`: các guard thông thường không được compiler chứng minh luôn đúng để đánh dấu dominated.

### 9.4. Hằng số sau pattern bao phủ

```java
// Selector là Integer.
return switch (value) {
    case Integer i -> "any";
    case 0 -> "zero"; // lỗi: dominated
    case null -> "null";
};
```

**Sửa:** đặt `case 0` trước `case Integer i`.

### 9.5. Record pattern tổng quát trước nested pattern

```java
return switch (obj) {
    case Holder(var p) -> "any holder";
    case Holder(Point(var x, var y)) -> "point holder"; // lỗi
    default -> "other";
};
```

**Sửa:** nested `Holder(Point(...))` trước `Holder(var p)`.

### 9.6. `default` sau unconditional pattern

```java
return switch (obj) {
    case Object o -> "anything";
    default -> "other"; // lỗi: đã có unconditional pattern
};
```

**Sửa:** chọn cách biểu diễn trường hợp tổng quát phù hợp; nếu cần bắt `null` riêng, dùng `case null`.

Với JDK 21, năm trường hợp đầu cùng tạo chẩn đoán dạng `this case label is dominated by a preceding case label`. Trường hợp cuối tạo chẩn đoán `switch has both an unconditional pattern and a default label`. Các chẩn đoán cụ thể có thể thay đổi giữa các phiên bản/nhà phân phối `javac`, nhưng nguyên tắc ngôn ngữ không thay đổi.

## 10. Phương pháp đọc lỗi và xử lý dominance

Khi compiler báo dominated case:

1. **Xác định selector type:** chẳng hạn `Object`, `Integer`, sealed interface hoặc record.
2. **Tìm case bị báo:** ghi rõ kiểu pattern, có guard hay không, cấu trúc record/component.
3. **So các case đứng trước:** có case nào không guard nhận tất cả giá trị mà case đang xét có thể nhận không?
4. **Xét quan hệ subtype và component:** `CharSequence` bao `String`, `Number` bao `Integer`; `Holder(var p)` rộng hơn `Holder(Point(...))`.
5. **Xem nhánh hằng số và guard:** hằng số thường nên đứng trước nhánh pattern bao phủ; `when true` như unguarded, còn guard bình thường không tự làm compiler giải được mọi điều kiện nghiệp vụ.
6. **Sửa thứ tự hoặc tách điều kiện:** đặt nhánh hẹp trước nhánh rộng, tránh case lặp; nếu cần một kết quả cho tất cả trường hợp, có thể gộp case.
7. **Biên dịch lại rồi kiểm tra output:** kiểm tra cả đầu vào phân biệt nhánh hẹp, nhánh rộng, dữ liệu có guard đúng/sai và `null`.

### Một số nhầm lẫn cần tránh

- **Cho rằng dominance xảy ra khi hai case chỉ "có thể" cùng match.** Chồng lấn một phần không luôn là dominance. Ví dụ `String` và `CharSequence` chồng lấn, nhưng đặt `String` trước `CharSequence` là hợp lệ vì kiểu hẹp không bao trùm toàn bộ kiểu rộng.
- **Nhầm với unreachable statement thông thường.** Dominance là quy tắc dành cho nhãn `switch` dựa trên pattern và sự bao phủ; flow analysis về câu lệnh không thể đến được có quy tắc riêng.
- **Cho rằng compiler phân tích được mọi `when`.** Ngoài trường hợp hằng `true` được quy định, đừng kỳ vọng nó giải được ý nghĩa của các predicate nghiệp vụ.
- **Nghĩ rằng `when false` có thể dùng để vô hiệu hóa tạm case.** Guard là constant expression `false` bị Java 21 từ chối ở compile time.
- **Nhầm `default` với `case null`.** `null` cần được xử lý theo quy tắc riêng; một type pattern không tự nhận `null` ở top-level.
- **Đồng nhất dominance với exhaustiveness.** Không có nhánh bị dominated chưa chắc `switch` đã bao phủ hết các loại giá trị.
- **Quên nested record patterns.** Một record pattern rộng về component có thể che nested pattern hẹp phía sau.
- **Sửa bằng cách thay guard bất kỳ thành `when true`.** Việc này làm mất logic phân loại và có thể gây dominance ngay lập tức.

### Nguyên tắc thiết kế dễ đọc

Sắp xếp nhánh theo độ đặc hiệu mà người đọc thấy ngay: **hằng số đặc biệt → type/record patterns với guard → type/record patterns cụ thể không guard → pattern cha/tổng quát → `default`**. Không nhất thiết mọi `switch` đều phải có tất cả các nhóm. Nếu dùng sealed hierarchy và đã bao phủ mọi subtype thì không cần `default`; khi xử lý `null` theo nghiệp vụ, thêm `case null` phù hợp.

## 11. Câu hỏi và bài tập tự kiểm tra

**1.** Với selector kiểu `Object`, vì sao `case CharSequence cs` trước `case String s` bị lỗi?  
*Đáp án:* Mọi `String` cũng là `CharSequence`; case trước không guard bao phủ case sau.

**2.** Có phải mọi cặp case cùng match một giá trị đều gây dominance?  
*Đáp án:* Không. `case String s` trước `case CharSequence cs` là hợp lệ; nhánh đầu không bao phủ mọi `CharSequence`.

**3.** Vì sao `case String s when s.isBlank()` trước `case String s` hợp lệ?  
*Đáp án:* Nhánh có guard chỉ chọn một phần giá trị; nhánh không guard xử lý những giá trị còn lại của cùng kiểu.

**4.** `when true` có khác guard bình thường trong dominance không?  
*Đáp án:* Có. Constant guard `true` được xem như unguarded, do đó có thể dominate case cùng kiểu phía sau.

**5.** Trong `switch(Integer)`, nên đặt `case 0` trước hay sau `case Integer i`?  
*Đáp án:* Trước. Pattern `Integer i` không guard sẽ bao phủ hằng `0` nếu đứng trước.

**6.** Có thể đặt `case Holder(var p)` trước `case Holder(Point(var x, var y))` không?  
*Đáp án:* Không. Component `var p` bao phủ mọi trường hợp mà nested `Point(...)` match, nên case sau bị dominated.

**7.** Một switch expression xử lý hết `Circle` và `Square` của sealed interface có luôn cần `default` không?  
*Đáp án:* Không. Nếu compiler chứng minh các subtype đã được bao phủ, switch exhaustive mà không cần default. `null` là trường hợp xử lý riêng nếu muốn trả kết quả cho đầu vào null.

**8.** Nếu không có dominated case nhưng switch expression trên `Object` chỉ chứa `case String s`, điều gì xảy ra?  
*Đáp án:* Compiler báo không exhaustive vì vẫn còn các giá trị không phải `String` chưa có nhánh.

**9.** Có nên thay toàn bộ `when condition` thành `when true` để compiler dễ kiểm tra không?  
*Đáp án:* Không. Điều đó làm nhánh không còn điều kiện và có thể che các case phía sau, thay đổi hành vi nghiệp vụ.

## Tham khảo

- [JEP 441 — Pattern Matching for switch](https://openjdk.org/jeps/441)
- [JEP 440 — Record Patterns](https://openjdk.org/jeps/440)
- [Oracle Java 21 — Pattern Matching for switch](https://docs.oracle.com/en/java/javase/21/language/pattern-matching-switch.html)
- [JLS Java SE 21 §14.11.1 — Switch Blocks, Dominance and Exhaustiveness](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.11.1)
- [JLS Java SE 21 §14.30.3 — Properties of Patterns](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.30.3)
