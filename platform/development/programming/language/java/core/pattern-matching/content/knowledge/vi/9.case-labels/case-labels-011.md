# Case label bị trùng nghĩa trong pattern `switch` của Java

## 1. “Trùng nghĩa” không chỉ là viết trùng một dòng `case`

Từ Java 21, `switch` hỗ trợ **pattern matching** chính thức: nhánh `case` có thể là hằng, type pattern, record pattern hoặc pattern kèm điều kiện `when`. Vì vậy, hai nhãn `case` có thể “trùng nghĩa” theo nhiều cách:

1. **Trùng giá trị hằng** (*duplicate case constant*): hai nhãn chỉ đến cùng một hằng số, dù cách viết biểu thức khác nhau.
2. **Trùng nhãn đặc biệt**: hai `default` hoặc hai `case null` trong cùng `switch`.
3. **Bị bao phủ bởi một nhánh trước** (*dominated case label*): mọi giá trị có thể được nhánh sau nhận đều đã được một nhánh trước không có guard hạn chế tiếp nhận; nhánh sau không thể chạy.
4. **Giao nhau về tập giá trị khớp nhưng không bị compiler cấm**: hai pattern có thể cùng khớp một số giá trị, hoặc các guard tương đương về logic. Khi đó **thứ tự nhánh** ảnh hưởng kết quả và compiler không nhất thiết phát hiện lỗi logic.

Cần phân biệt **lỗi biên dịch** với **trùng nghĩa về mặt nghiệp vụ**. Java bảo vệ các quy tắc rõ ràng về constant, `null`, `default`, pattern dominance và exhaustiveness; Java **không** chứng minh mọi biểu thức `when` có tương đương logic hay không.

Ví dụ tổng quát:

```java
static String category(Object value) {
    return switch (value) {
        case String s when s.isBlank() -> "blank";
        case String s -> "text";
        case Integer n -> "integer";
        case null -> "null";
        default -> "other";
    };
}
```

Hai nhãn `String` **không trùng nghĩa theo quy tắc dominance**: nhánh đầu chỉ nhận `String` rỗng/trắng, nhánh sau nhận `String` còn lại. Ngược lại, nếu đưa `case String s` không guard lên trước, nhánh `String` có guard trở nên vô nghĩa và bị compiler từ chối.

## 2. Trùng hằng: `duplicate case label`

Trong `switch` dùng nhãn hằng, Java không cho hai hằng có **cùng giá trị** trong một khối `switch`.

```java
// LỖI: hai nhãn hằng đều có giá trị 1.
static String invalid(int value) {
    return switch (value) {
        case 1 -> "first";
        case 1 -> "second"; // duplicate case label
        default -> "other";
    };
}
```

Quy tắc so sánh **giá trị hằng đã tính được lúc biên dịch**, không chỉ so sánh văn bản mã nguồn. Vì thế đây cũng là lỗi:

```java
// LỖI: 1 + 0 là constant expression có giá trị 1.
static String invalidExpression(int value) {
    return switch (value) {
        case 1 -> "one";
        case 1 + 0 -> "still one"; // duplicate case label
        default -> "other";
    };
}
```

Cách gộp nhiều hằng vào một nhánh chỉ hợp lệ khi các giá trị **khác nhau**:

```java
static String valid(int value) {
    return switch (value) {
        case 1, 2 -> "small";
        case 3 -> "three";
        default -> "other";
    };
}
```

Viết `case 1, 1 -> "small";` vẫn là **trùng hằng**; việc hai giá trị nằm trong cùng một nhãn không hợp thức hóa sự lặp lại.

Với enum, nhãn `case RED` và một nhãn `case RED` khác trong cùng khối cũng là trùng. Java xét **cùng enum constant**, không phải tên biến được dùng ở phần xử lý.

**Cách sửa:** gộp những giá trị muốn xử lý chung vào **một** nhãn không trùng, hoặc loại bỏ nhãn lặp. Không giải quyết lỗi bằng cách đổi phần thân nhánh: cùng hằng số không được xuất hiện hai lần kể cả khi hành động khác nhau.

## 3. Trùng `null` và `default`

Trong Java 21, `case null` là nhãn đặc biệt cho selector đúng bằng `null`. Một `switch` không được khai báo `case null` hai lần:

```java
// LỖI: duplicate case null.
static String invalidNull(Object value) {
    return switch (value) {
        case null -> "missing";
        case String s -> s;
        case null -> "still missing"; // duplicate case label
        default -> "other";
    };
}
```

Tương tự, không được viết hai nhãn `default`:

```java
// LỖI: duplicate default label.
static String invalidDefault(Object value) {
    return switch (value) {
        case String s -> s;
        default -> "other";
        default -> "again"; // duplicate default label
    };
}
```

Có thể xử lý `null` và fallback trong **cùng nhánh đặc biệt**:

```java
static String fallback(Object value) {
    return switch (value) {
        case String s -> "text:" + s;
        case null, default -> "unsupported or null";
    };
}
```

`case null, default` nhận `null` và mọi giá trị còn lại không được nhánh `String` tiếp nhận. Nếu đã dùng nhãn này, không thêm một `case null` hoặc `default` độc lập nữa.

**Đừng nhầm:** `default` đứng riêng **không bắt `null`** trong pattern `switch` Java 21. Nếu selector là `null` và không có `case null`, chương trình ném `NullPointerException`, dù có `default`.

```java
static String withoutNull(Object value) {
    return switch (value) {
        case String s -> s;
        default -> "other";
    };
}

// withoutNull(42)   -> "other"
// withoutNull(null) -> ném NullPointerException
```

Chỉ dùng một `default` không phải là “trùng nghĩa” với một `case null`; chúng xử lý hai miền khác nhau. Muốn cùng xử lý, viết `case null, default`.

## 4. Pattern dominance: nhánh sau bị nhánh trước bao phủ

Trong pattern `switch`, **dominance** là quy tắc phát hiện nhánh không thể được chọn vì một nhánh trước đã bao phủ toàn bộ trường hợp của nó. Các case được so khớp theo thứ tự xuất hiện; do đó Java từ chối những nhãn bị dominated.

Xét:

```text
CharSequence
    ^
    |
  String
```

Mọi `String` đều thực hiện `CharSequence`. Nếu đặt pattern tổng quát trước:

```java
// LỖI trong Java 21: String bị CharSequence trước đó bao phủ.
static String invalidOrder(Object value) {
    return switch (value) {
        case CharSequence cs -> "sequence";
        case String s -> "string"; // dominated case label
        default -> "other";
    };
}
```

Vì mọi giá trị có thể khớp `case String s` cũng sẽ khớp `case CharSequence cs`, nhánh `String` không có cơ hội chạy. Thông báo của compiler thường chứa nội dung tương tự *this case label is dominated by a preceding case label*.

**Cách sửa: đặt kiểu cụ thể trước kiểu rộng**:

```java
static String validOrder(Object value) {
    return switch (value) {
        case String s -> "String";
        case CharSequence cs -> "CharSequence";
        default -> "Other";
    };
}
```

Với `"Java"` nhánh `String` được chọn; với `new StringBuilder("x")`, nhánh `CharSequence` được chọn.

Quy tắc cũng đúng với quan hệ lớp:

```java
// LỖI: Number bao phủ Integer.
static String invalidNumberOrder(Object value) {
    return switch (value) {
        case Number n -> "number";
        case Integer i -> "integer"; // dominated
        default -> "other";
    };
}
```

Đổi thứ tự thành `case Integer i` trước, sau đó `case Number n` sẽ hợp lệ: nhánh `Integer` xử lý số nguyên, nhánh `Number` xử lý các kiểu số khác.

**Quan trọng:** dominance kiểm tra **tập giá trị có thể khớp**, chứ không kiểm tra tên pattern variable. Đổi `case String s` thành `case String text` không tránh được dominance.

## 5. Hai `case` cùng kiểu: guard quyết định có bị trùng hay không

### 5.1. Pattern không guard đặt trước pattern cùng kiểu: lỗi

```java
// LỖI: nhánh String phía dưới không bao giờ được chọn.
static String invalidGuardOrder(Object value) {
    return switch (value) {
        case String s -> "any string";
        case String s when s.isBlank() -> "blank"; // dominated
        default -> "other";
    };
}
```

`case String s` không guard đã tiếp nhận **mọi String khác null**, bao gồm cả chuỗi trắng. Vì thế nhánh có `when` ở phía sau không còn giá trị.

### 5.2. Guard đặt trước, pattern không guard đặt sau: hợp lệ

```java
static String validText(Object value) {
    return switch (value) {
        case String s when s.isBlank() -> "blank";
        case String s -> "text";
        default -> "other";
    };
}
```

Nhánh đầu chỉ nhận chuỗi thỏa `isBlank()`; khi guard sai, nhánh `String` tiếp theo có thể được chọn. Đây là cách viết **phân loại chuyên biệt rồi fallback cùng kiểu**.

### 5.3. Guard `when true` được xem là không có guard

```java
// LỖI: when true là biểu thức hằng true.
static String invalidTrueGuard(Object value) {
    return switch (value) {
        case String s when true -> "string";
        case String s -> "also string"; // dominated
        default -> "other";
    };
}
```

Đừng cho rằng thêm `when` sẽ tự động tách được hai nhãn. Trong Java 21, guard là **constant expression `true`** được coi như không có điều kiện hạn chế khi xét dominance. Guard là constant expression `false` cũng không hợp lệ.

## 6. Trùng nhau về logic trong `when` có thể vẫn biên dịch

Khác với quan hệ subtype, Java thường **không chứng minh** một điều kiện `when` tùy ý bao hàm hay tương đương điều kiện khác.

Ví dụ:

```java
static String confusing(Object value) {
    return switch (value) {
        case Integer n when n > 0 -> "positive";
        case Integer n when n > 10 -> "large";
        case Integer n -> "zero or negative";
        default -> "not integer";
    };
}
```

Mã trên có thể **biên dịch**, nhưng về logic, giá trị `n > 10` luôn thỏa `n > 0` trước. Vì vậy nhánh `"large"` **không thể được chọn** ở thời điểm chạy, dù compiler không báo dominated cho dạng guard này.

Đặt điều kiện **hẹp hơn trước, rộng hơn sau**:

```java
static String correct(Object value) {
    return switch (value) {
        case Integer n when n > 10 -> "large";
        case Integer n when n > 0 -> "positive";
        case Integer n -> "zero or negative";
        default -> "not integer";
    };
}
```

Tương tự, hai nhánh có **cùng một điều kiện guard** cũng có thể được compiler chấp nhận:

```java
static String repeatedGuards(Object value) {
    return switch (value) {
        case Integer n when n > 0 -> "first";
        case Integer n when n > 0 -> "second"; // Có thể biên dịch!
        case Integer n -> "not positive";
        default -> "other";
    };
}
```

Với mọi `Integer` dương, nhánh `"first"` được chọn; nhánh `"second"` không bao giờ chạy. Đây là **trùng nghĩa ở cấp logic, không nhất thiết là lỗi cú pháp**.

Quy tắc JLS Java 21 về dominance chủ yếu xử lý các nhãn **không có guard hạn chế**; một guard tùy ý thường không được dùng làm bằng chứng để xác định nó dominate nhãn sau. Ngoại lệ rõ ràng là `when true`. Chính vì vậy, **biên dịch thành công không chứng minh các nhánh `case` không chồng chéo về nghiệp vụ**.

Khi có nhiều điều kiện, sắp xếp từ **đặc thù đến tổng quát**, và viết test cho các giá trị nằm ở ranh giới: `-1`, `0`, `1`, `10`, `11`.

## 7. Pattern bao phủ hằng số: trùng giá trị khác với dominated constant

Với `switch` có selector kiểu `Integer`, nhánh type pattern `Integer n` không guard nhận mọi giá trị `Integer` khác null. Vì thế đặt hằng `case 1` sau nó dẫn đến lỗi dominated:

```java
// LỖI: case 1 bị Integer n phía trên bao phủ.
static String invalidConstant(Integer value) {
    return switch (value) {
        case Integer n -> "an integer";
        case 1 -> "one"; // dominated by preceding pattern
    };
}
```

Muốn xử lý số `1` đặc biệt, đặt hằng trước:

```java
static String validConstant(Integer value) {
    return switch (value) {
        case 1 -> "one";
        case Integer n when n > 0 -> "positive";
        case Integer n -> "zero-or-negative";
    };
}
```

Các nhãn trên exhaustive cho mọi giá trị `Integer` khác null; không cần thêm `default`. Nếu `value == null`, `switch` vẫn ném `NullPointerException` do không có `case null`.

Có một khác biệt tinh tế:

```java
static String guardBeforeConstant(Integer value) {
    return switch (value) {
        case Integer n when n > 0 -> "positive";
        case 1 -> "one";
        case Integer n -> "other integer";
    };
}
```

Đoạn trên **có thể biên dịch**, vì guard `n > 0` không được coi là pattern vô điều kiện khi xét dominance. Tuy nhiên với `value == 1`, nhánh đầu được chọn và nhánh `case 1` không bao giờ nhận giá trị này ở runtime.

**Lời khuyên:** khi dùng hằng cùng type pattern, hãy ưu tiên **hằng trước → guarded patterns → unguarded patterns**. Thứ tự này vừa rõ ý định vừa tránh bỏ sót các giá trị cụ thể.

Lưu ý: ví dụ về nhãn số dùng selector `Integer`; **không** tùy tiện lấy `Object` làm selector rồi thêm `case 1`: tính hợp lệ của constant case còn phụ thuộc kiểu tĩnh của selector theo quy tắc `switch` Java 21.

## 8. Hai pattern cùng có thể match nhưng không nhất thiết bị cấm

Hãy xem hai interface:

```java
CharSequence
java.io.Serializable
```

Một `String` thực hiện cả hai interface, nên đối tượng `"Java"` có thể khớp cả hai pattern. Tuy nhiên, không phải mọi `CharSequence` đều là `Serializable`, cũng không phải mọi `Serializable` đều là `CharSequence`. Compiler không có cơ sở nói một pattern **bao phủ toàn bộ** pattern còn lại.

```java
static String classify(Object value) {
    return switch (value) {
        case CharSequence seq -> "sequence";
        case java.io.Serializable serializable -> "serializable";
        default -> "other";
    };
}
```

Đoạn này hợp lệ trong Java 21. Với `"Java"`, nhánh `CharSequence` đứng trước được chọn; nếu đảo hai nhánh, `String` sẽ đi vào nhánh `Serializable` trước.

**Bài học:** *overlap* (có giá trị cùng match) **không đồng nghĩa** với *dominance* (một nhánh trước bao phủ **mọi** giá trị của nhánh sau). Sự giao nhau không bị cấm thì thứ tự nhánh trở thành một phần của hành vi chương trình.

Điều này cũng đúng khi hai guard khác nhau có miền giá trị giao nhau. Nếu `n > 0` và `n % 2 == 0` đều đúng với `n = 2`, chỉ nhánh đầu tiên có guard thỏa sẽ được chọn. Hãy đặt thứ tự theo ưu tiên nghiệp vụ, không trông chờ compiler tự chọn “nhánh tốt hơn”.

## 9. `default` và pattern vô điều kiện cũng có thể trùng vai trò

Một pattern **unconditional cho kiểu selector** có thể đóng vai trò nhánh tổng quát. Với selector có kiểu tĩnh `Object`:

```java
// LỖI: Object o là pattern không guard bao phủ mọi Object non-null,
// nên không thể thêm default như nhánh dự phòng riêng.
static String invalidFallback(Object value) {
    return switch (value) {
        case Object o -> "object";
        default -> "other"; // unconditional pattern + default
    };
}
```

Tương tự, nếu `case Object o` xuất hiện trước `case String s`, nhánh `String` bị dominated.

Cách xử lý:

- Dùng **`default`** nếu chỉ cần fallback, không cần bind biến pattern cụ thể.
- Dùng **`case Object o`** để có một biến `o` ở nhánh tổng quát cho các giá trị non-null.
- Nếu cần xử lý `null`, thêm **`case null`** rõ ràng; một type pattern thông thường không match `null`.
- Không kết hợp một pattern tổng quát vô điều kiện với `default` riêng trong cùng khối.

Một `case null, default` đã gộp hai nhu cầu đặc biệt thành một nhãn; không thêm `case null` hoặc `default` khác sau đó.

**Tính exhaustive** là câu hỏi khác: `switch` expression và enhanced `switch` statement cần bao phủ mọi giá trị non-null có thể có ở kiểu selector. Thêm `default` thường giúp đạt exhaustiveness, nhưng không làm cho các nhánh bị dominated trở nên hợp lệ. Với enum hoặc sealed hierarchy được bao phủ đủ, nhiều `switch` expression không cần `default`.

## 10. Chương trình Java 21 độc lập: những trường hợp đúng

Lưu toàn bộ chương trình vào **`CaseLabelOverlapDemo.java`**:

```java
public class CaseLabelOverlapDemo {
    static String classify(Object value) {
        return switch (value) {
            case null -> "null";
            case String s when s.isBlank() -> "blank";
            case String s -> "text:" + s;
            case Integer n when n > 0 -> "positive:" + n;
            case Integer n -> "integer:" + n;
            default -> "other";
        };
    }

    static String byType(Object value) {
        return switch (value) {
            case String s -> "String";
            case CharSequence cs -> "CharSequence";
            default -> "Other";
        };
    }

    static String guarded(Object value) {
        return switch (value) {
            case Integer n when n > 10 -> "big";
            case Integer n when n > 0 -> "positive";
            case Integer n -> "nonpositive";
            default -> "other";
        };
    }

    public static void main(String[] args) {
        Object[] inputs = {null, " ", "Java", 12, -2, 3.14};

        for (Object value : inputs) {
            System.out.println(classify(value));
        }

        System.out.println(byType("abc"));
        System.out.println(byType(new StringBuilder("x")));

        System.out.println(guarded(20));
        System.out.println(guarded(5));
        System.out.println(guarded(0));
    }
}
```

Biên dịch/chạy với **JDK 21+**, không cần bật preview:

```bash
javac --release 21 CaseLabelOverlapDemo.java
java CaseLabelOverlapDemo
```

Đầu ra:

```text
null
blank
text:Java
positive:12
integer:-2
other
String
CharSequence
big
positive
nonpositive
```

Giải thích kết quả:

1. `null` đi vào `case null`, không phải `default`.
2. `" "` có kiểu `String` và thỏa `isBlank()`, nên chọn nhánh String có guard.
3. `"Java"` không thỏa `isBlank()` nhưng vẫn là `String`, nên chọn nhánh String không guard.
4. `12` đi vào `Integer n when n > 0`; `-2` đi vào `Integer n` không guard.
5. `3.14` là `Double` và không khớp pattern nào ở trên, nên vào `default`.
6. Trong `byType`, String được đặt trước CharSequence; mỗi nhánh giữ phạm vi xử lý có ý nghĩa.
7. `guarded(20)` cho `big`, `guarded(5)` cho `positive`, và `guarded(0)` cho `nonpositive` vì thứ tự guard **hẹp trước, rộng sau**.

Chương trình này chứa các case giao nhau hợp lệ và dùng các pattern variable riêng theo từng nhánh; kết quả cho thấy thứ tự không phải chi tiết trang trí.

Các đoạn được ghi **LỖI** ở mục 2–9 là ví dụ *cố ý không biên dịch* nhằm nhận diện rule. Không ghép chúng vào file chạy độc lập ở mục này.

## 11. Bảng phân biệt nhanh các kiểu “trùng nghĩa”

| Tình huống | Java 21 có cho phép không? | Nguyên nhân / cách khắc phục |
| --- | --- | --- |
| `case 1`, rồi `case 1` | Không | Trùng constant value; chỉ giữ một |
| `case 1`, rồi `case 1 + 0` | Không | Giá trị hằng cùng bằng 1 |
| `case 1, 1` | Không | Trùng hằng ngay trong một nhãn |
| Hai `case null` | Không | Không được lặp `null` |
| Hai `default` | Không | Không được lặp `default` |
| `case CharSequence c`, rồi `case String s` | Không | Pattern sau bị dominate; đảo thứ tự |
| `case String s`, rồi `case CharSequence c` | Có | String cụ thể trước, CharSequence rộng sau |
| `case String s`, rồi `case String t` | Không | Pattern không guard đầu bao phủ toàn bộ String |
| `case String s`, rồi `case String t when t.isBlank()` | Không | Nhánh sau bị bao phủ |
| `case String s when s.isBlank()`, rồi `case String s` | Có | Guard trước, fallback String sau |
| `case String s when true`, rồi `case String s` | Không | Guard hằng true được xem là vô điều kiện |
| Hai `case Integer n when n > 0` | Có thể | Java không giải được mọi quan hệ guard; nhánh sau vô dụng về logic |
| `case Integer n` rồi `case 1` (selector Integer) | Không | Constant bị pattern trước dominate |
| `case 1` rồi `case Integer n` (selector Integer) | Có | Constant được chọn trước pattern rộng |
| `case Object o` và `default` (selector Object) | Không | Trùng nhánh tổng quát |
| `case null` và một `default` | Có | Hai mục đích khác nhau |
| `case null, default` | Có | Nhãn kết hợp đặc biệt, không được lặp null/default thêm lần nữa |

Thông báo lỗi cụ thể có thể khác theo bản JDK, nhưng các quy tắc phân loại ở đây dựa trên Java SE 21.

## 12. Cách xử lý khi gặp lỗi compiler

Khi compiler báo `duplicate case label`, `duplicate default label`, hoặc `dominated by a preceding case label`, đừng chỉ đổi tên biến. Thực hiện theo trình tự:

1. **Xác định kiểu selector** của `switch` và phiên bản Java đang dùng. Pattern `switch` với `when` chính thức ở Java 21. Java 17 chỉ có một số tính năng pattern `switch` ở chế độ preview, vì vậy không nên đem ví dụ Java 21 sang `javac --release 17`.
2. **Kiểm tra hằng**: có nhãn nào dùng cùng giá trị, kể cả một constant expression như `1 + 0` hoặc cùng enum constant, không?
3. **Kiểm tra nhãn đặc biệt**: có bao nhiêu `case null`, `default`, hay `case null, default`?
4. **Xét kiểu pattern từ trên xuống**: pattern trước có phải supertype hoặc pattern unconditional bao phủ một pattern sau không? Ví dụ `CharSequence` trước `String`.
5. **Xét guard**: pattern trước có `when` không? Nếu guard là `true` hằng, nó không hạn chế nhánh. Nếu guard tùy ý, compiler thường không chứng minh bao hàm logic, nên cần tự xem điều kiện.
6. **Kiểm tra constant so với pattern**: trên selector phù hợp, constant nằm sau một pattern vô điều kiện có bị bao phủ không?
7. **Giữ exhaustiveness**: sau khi xóa/đổi thứ tự nhánh, `switch` expression hoặc enhanced `switch` vẫn phải có đủ trường hợp xử lý. Thêm fallback khi cần; nếu dùng sealed hierarchy và muốn compiler cảnh báo subtype mới, cân nhắc không dùng `default`.
8. **Chạy test ranh giới**: với điều kiện số học, dùng `0`, `1`, `10`, `11`; với String, thử `""`, `" "`, `"Java"`; với kiểu, thử superclass, subclass và `null`.

### Về `switch` dùng dấu `:` và dấu `->`

Ví dụ trong bài dùng nhánh `->` để mỗi nhãn có một phần xử lý riêng, không fall-through. Với dạng `case A:` truyền thống, nhiều nhãn có thể cố ý dùng chung một nhóm lệnh; điều này **không** cho phép khai báo lặp lại cùng hằng, `null` hoặc `default`.

```java
// Nhóm nhiều hằng khác nhau vào cùng phần xử lý:
static String describe(int value) {
    String result;
    switch (value) {
        case 1:
        case 2:
            result = "small";
            break;
        default:
            result = "other";
    }
    return result;
}
```

Đây là mẫu hợp lệ của switch statement. Nhưng nếu viết `case 1:` hai lần, compiler vẫn báo trùng hằng. Với pattern variables, quy tắc flow scoping và fall-through còn có thể tạo lỗi biên dịch khác; nên ưu tiên `->` khi mới học pattern `switch`.

## 13. Câu hỏi tự kiểm tra

**Câu 1.** Hai nhãn `case 1 ->` và `case 1 + 0 ->` có khác nhau không?

**Đáp án:** Không về giá trị hằng. Java tính constant expression khi biên dịch; hai nhãn cùng giá trị nên bị từ chối.

**Câu 2.** Vì sao `case CharSequence c` rồi `case String s` sai, nhưng đảo thứ tự lại đúng?

**Đáp án:** Vì `String` là subtype của `CharSequence`. Pattern tổng quát đặt trước sẽ nhận mọi String, khiến nhánh cụ thể phía sau bị dominated. Đặt cụ thể trước giữ được hai nhánh có ích.

**Câu 3.** Hai nhãn `case Integer n when n > 0` và `case Integer n when n > 10` được compiler cho phép thì có nghĩa không bị chồng chéo không?

**Đáp án:** Không. Giá trị `11` khớp cả hai điều kiện, nhưng nhánh `n > 0` đứng trước được chọn. Nhánh sau không được chọn với bất kỳ số nào, dù compiler có thể không phát hiện về mặt logic.

**Câu 4.** `case String s when true` trước `case String s` có hợp lệ không?

**Đáp án:** Không. Guard hằng `true` được xem là không hạn chế pattern, nên nhánh String thứ hai bị dominated.

**Câu 5.** Với selector kiểu `Object`, hai nhãn `case CharSequence c` và `case java.io.Serializable s` có chắc là lỗi không?

**Đáp án:** Không. Hai interface có thể cùng được một đối tượng implement (ví dụ `String`), nhưng không interface nào bao phủ toàn bộ interface kia. Cả hai pattern có thể hợp lệ và **thứ tự** quyết định nhánh được chọn cho giá trị giao nhau.

**Câu 6.** Thêm `default` sau `case Object o` trên selector kiểu `Object` có giải quyết được lỗi thiếu nhánh không?

**Đáp án:** Không. `case Object o` vô điều kiện đã nhận mọi đối tượng non-null, nên một `default` khác bị xem là trùng vai trò. Nếu cần xử lý `null`, viết `case null` riêng.

**Câu 7.** Có hai nhãn `case null` và `default` trong cùng `switch`, vậy đã trùng ý nghĩa chưa?

**Đáp án:** Chưa. `case null` xử lý selector `null`; `default` đơn lẻ xử lý các giá trị non-null không được case khác nhận. Có thể dùng nhãn đặc biệt `case null, default` để gom hai đường xử lý.

## 14. Ghi nhớ trọng tâm

- **Duplicate constant:** trùng *giá trị* hằng, kể cả biểu thức hằng viết khác nhau → lỗi compile time.
- **Duplicate `null`/`default`:** nhãn đặc biệt bị lặp → lỗi compile time.
- **Dominance:** một nhánh trước không bị guard hạn chế bao phủ toàn bộ giá trị nhánh sau có thể nhận → lỗi compile time.
- **Guard:** đặt guard cụ thể trước unguarded pattern. Guard hằng `true` được coi như không guard; các guard thông thường có thể trùng logic mà compiler không phát hiện.
- **Overlap hợp lệ:** hai pattern cùng khớp một số đối tượng không nhất thiết gây lỗi; nhánh đầu được áp dụng sẽ thắng.
- **Thứ tự thường an toàn:** constant case → pattern cụ thể → pattern có guard → pattern rộng không guard → fallback, tùy quan hệ thực tế giữa các nhãn.
- **`default` không thay thế `case null`**. Giữ đúng tính exhaustive nhưng không dùng `default` để che các trường hợp cần xử lý rõ.

**Kết luận:** Khi thấy các `case` “trùng nghĩa”, hãy hỏi liệu chúng **trùng chính xác một hằng**, **một nhánh bao phủ toàn bộ nhánh sau**, hay **chỉ chồng chéo trên một số giá trị**. Ba trường hợp khác nhau dẫn đến ba cách xử lý khác nhau: xóa nhãn lặp, đổi thứ tự/thu hẹp pattern, hoặc xem lại ưu tiên nghiệp vụ và test guard.

### Tài liệu chính thức

- [Java SE 21 JLS §14.11 — The switch Statement / Switch Blocks](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.11)
- [Java SE 21 JLS §14.30.3 — Properties of Patterns / Dominance](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.30.3)
- [Java SE 21 JLS §15.28 — switch Expressions](https://docs.oracle.com/javase/specs/jls/se21/html/jls-15.html#jls-15.28)
- [Oracle Java 21 — Pattern Matching for switch Expressions and Statements](https://docs.oracle.com/en/java/javase/21/language/pattern-matching-switch.html)
- [JEP 441 — Pattern Matching for switch](https://openjdk.org/jeps/441)
