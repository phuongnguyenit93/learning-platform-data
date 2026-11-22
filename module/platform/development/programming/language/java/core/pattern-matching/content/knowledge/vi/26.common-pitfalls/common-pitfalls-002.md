# Lỗi đặt case tổng quát trước case cụ thể trong Java Pattern Matching

Khi dùng **pattern matching cho `switch`**, thứ tự các nhánh `case` không chỉ ảnh hưởng đến hành vi khi chạy: **trình biên dịch Java còn kiểm tra một nhánh có bị nhánh đứng trước che hoàn toàn hay không**. Nếu một `case` phía sau không thể được chọn vì `case` không có guard ở phía trước đã khớp mọi giá trị mà nó có thể khớp, Java báo lỗi **dominance** (nhánh bị chi phối, *dominated case*).

Đây là lỗi thường gặp khi refactor chuỗi `if/else if` thành `switch`, thêm nhánh xử lý kiểu con, hoặc dùng record patterns và `when` trong Java 21.

**Phiên bản:** Bài sử dụng Java 21+ vì *pattern matching for switch* và *record patterns* trở thành tính năng chính thức trong Java 21 (JEP 441, JEP 440). Ví dụ chạy không cần `--enable-preview`.

## 1. Triệu chứng: this case label is dominated by a preceding case label

Xét phương thức minh họa **không biên dịch được**:

```java
static String bad(Object value) {
    return switch (value) {
        case CharSequence chars -> "sequence";
        case String text -> "string"; // LỖI: dominated case
        default -> "other";
    };
}
```

Tại sao lỗi? `String` triển khai `CharSequence`. Vì vậy **mọi đối tượng khớp `String text` đều khớp `CharSequence chars`** ở case trước. Case `String` không bao giờ được chọn.

Một diagnostic thường thấy từ `javac`:

```text
error: this case label is dominated by a preceding case label
```

Đây là **lỗi lúc biên dịch**, không phải `ClassCastException`, lỗi runtime hay chỉ là cảnh báo hiệu năng. Java không chạy chương trình trước rồi mới phát hiện case bị che.

**Cách sửa: đặt nhánh cụ thể trước nhánh tổng quát.**

```java
static String good(Object value) {
    return switch (value) {
        case String text -> "string";
        case CharSequence chars -> "sequence";
        default -> "other";
    };
}
```

Với mã đã sửa, `"Java"` được nhánh `String` xử lý; một `StringBuilder` được nhánh `CharSequence` xử lý; các loại còn lại đi vào `default`.

## 2. Dominance là gì và vì sao thứ tự case quan trọng?

Một **switch label** bị *dominated* nếu, theo những quy tắc kiểm tra tĩnh của Java, mọi giá trị mà label đó có thể xử lý đều đã được một label hợp lệ đứng trước bao phủ.

Đối với pattern labels, quy tắc cốt lõi trong JLS Java 21 là: một case pattern `q` có thể bị chi phối bởi một case pattern `p` **không có guard** ở phía trước, nếu pattern `p` **dominates** pattern `q`. Trong thực tế, điều này thường phản ánh quan hệ kiểu cha–con hoặc cấu trúc record rộng–hẹp.

Cần phân biệt ba khái niệm:

| Khái niệm | Câu hỏi |
| --- | --- |
| **Pattern matching** | Giá trị đang xét có khớp pattern của case hay không? |
| **Dominance** | Case này có bị case trước bao phủ hoàn toàn, khiến compiler từ chối không? |
| **Exhaustiveness** | Switch đã xử lý đủ mọi khả năng cần thiết của selector chưa? |

Một switch có thể **đã bao phủ tất cả kiểu** nhưng vẫn **không biên dịch được** vì có case bị dominated. Ngược lại, sắp đúng thứ tự chưa chắc đã đủ nhánh cho một switch expression. Đây là những kiểm tra riêng.

### Thứ tự khớp khi chạy

Với giá trị selector khác `null`, Java xét các switch labels theo thứ tự và chọn label đầu tiên áp dụng được. Với case có guard `when`, Java cần pattern khớp trước rồi mới đánh giá guard. Quy tắc dominance giúp ngăn những trường hợp mà compiler xác định chắc chắn có label phía sau không thể được chọn.

Ví dụ trực quan:

```text
Sai:  CharSequence -> String -> default
      └──────────────┘
        String bị che

Đúng: String -> CharSequence -> default
      └── hẹp ──┘   └── rộng ──┘
```

Tên biến (`chars`, `text`) không ảnh hưởng đến tính rộng–hẹp. Yếu tố quyết định là kiểu, pattern và guard.

## 3. Type pattern: kiểu cha đặt trước kiểu con

Giả sử đầu vào có kiểu tĩnh `Object`. Các type patterns điển hình là `String text`, `CharSequence chars`, `Integer number`, `Number number` và `Object other`.

### Ví dụ sai: Number che Integer

```java
// Không biên dịch.
static String badNumber(Object input) {
    return switch (input) {
        case Number number -> "number";
        case Integer integer -> "integer"; // Bị Number che.
        default -> "other";
    };
}
```

`Integer` là subtype của `Number`. Bất kỳ `Integer` khác `null` nào cũng khớp `Number number`, nên case `Integer integer` là thừa sau case đó.

### Ví dụ đúng

```java
static String goodNumber(Object input) {
    return switch (input) {
        case Integer integer -> "integer=" + integer;
        case Number number -> "number=" + number;
        default -> "other";
    };
}
```

`goodNumber(7)` trả `integer=7`; `goodNumber(3.5)` trả `number=3.5`.

**Quy tắc thực hành:** nhóm type patterns theo thứ tự **subtype cụ thể → supertype/interface rộng hơn → fallback**. Nếu nhiều kiểu không có quan hệ bao phủ, thứ tự giữa chúng thường không gây dominance, nhưng vẫn nên sắp xếp có chủ đích để dễ đọc.

### Type pattern Object gần như bao phủ mọi đầu vào tham chiếu khác null

Với selector kiểu `Object`:

```java
// Sai: case Object đặt đầu tiên che các type patterns phía sau.
return switch (input) {
    case Object anything -> "some object";
    case String text -> "text";   // Dominated.
};
```

`Object anything` là type pattern đủ rộng để khớp mọi giá trị `Object` **khác `null`**, bao gồm `String`. Hãy đặt nó ở cuối danh sách các case pattern cụ thể (và xử lý `null` riêng nếu cần).

Lưu ý: đoạn ví dụ sai này chỉ minh họa lỗi dominance, không phải mã hoàn chỉnh để chạy.

## 4. Guard when: nhánh có điều kiện phải đứng trước nhánh chung

Một kiểu có thể xuất hiện nhiều lần nếu các case khác nhau ở điều kiện `when`. Đây là cách phân nhóm giá trị hợp lệ.

### Sai: case String tổng quát đứng trước case String có guard

```java
// Không biên dịch: nhánh có guard đã bị nhánh tổng quát che.
return switch (input) {
    case String text -> "any text";
    case String text when text.isBlank() -> "blank text";
    default -> "other";
};
```

`case String text` trước đó không có guard; mọi `String` đều được nó xử lý. Vì vậy, case `String text when text.isBlank()` sẽ không bao giờ chạy.

### Đúng: kiểm tra đặc biệt trước, rồi đến trường hợp còn lại

```java
return switch (input) {
    case String text when text.isBlank() -> "blank text";
    case String text -> "text=" + text;
    default -> "other";
};
```

Luồng xử lý:

1. Nếu là `String` và `text.isBlank()` đúng, chọn nhánh đầu tiên.
2. Nếu là `String` nhưng guard đầu tiên sai, tiếp tục đến nhánh `String` chung.
3. Nếu không phải `String`, đi tiếp đến `default`.

Guard được kiểm tra **sau khi pattern đã khớp**, nên `text` có kiểu tĩnh `String` và khác `null` khi `text.isBlank()` được đánh giá. Không cần lặp `text != null`.

### Ngoại lệ quan trọng: when true

Trong JLS Java 21, một case có guard là biểu thức hằng **`true`** được coi là **unguarded** khi xác định dominance. Vì vậy:

```java
// Không biên dịch: when true được xem tương đương case không guard.
return switch (input) {
    case String text when true -> "text";
    case String text -> "another text";
    default -> "other";
};
```

Đừng nghĩ cứ có từ khóa `when` là một case phía trước không thể chi phối case phía sau. Compiler có quy tắc cụ thể cho guard luôn đúng. Mặt khác, Java 21 cũng không cho phép guard là một **hằng `false`**.

**Chú ý:** Compiler không phải bộ chứng minh tùy ý mọi điều kiện nghiệp vụ. Ví dụ hai guard phức tạp có thể chồng lấn về logic; cần sắp xếp theo ý nghĩa ưu tiên và viết test để xác nhận hành vi, ngoài việc dựa vào kiểm tra dominance.

## 5. Record pattern: pattern rộng che record pattern cụ thể

Dominance cũng áp dụng cho **record patterns**, không chỉ type patterns.

Giả sử:

```java
record Box(Object value) {}
```

Ta muốn phân biệt `Box` có payload kiểu `String` với mọi `Box` còn lại. Mẫu sau **sai**:

```java
// Không biên dịch.
static String badBox(Object input) {
    return switch (input) {
        case Box(var payload) -> "any box";
        case Box(String text) -> "text box"; // Bị Box(var ...) che.
        default -> "other";
    };
}
```

Tại sao?

- `Box(var payload)` khớp **mọi đối tượng `Box` khác `null`**, bất kể thành phần `value` là `String`, `Integer`, `null` hay một đối tượng khác.
- `Box(String text)` chỉ khớp những `Box` có thành phần `value` thực sự là `String` khác `null` (thành phần khai báo kiểu `Object`).
- Tập giá trị của `Box(String text)` là **tập con** của tập giá trị `Box(var payload)`.
- Vì vậy, case `Box(String text)` bị che nếu đặt sau case `Box(var payload)` không có guard.

Sửa bằng cách đặt pattern sâu/cụ thể trước:

```java
static String goodBox(Object input) {
    return switch (input) {
        case Box(String text) -> "text box=" + text;
        case Box(var payload) -> "other box=" + payload;
        default -> "not box";
    };
}
```

Với `new Box("Hi")` kết quả là `text box=Hi`, còn `new Box(42)` là `other box=42` và `new Box(null)` là `other box=null`. Một component `var payload` có thể nhận `null`; điều này **không** có nghĩa selector ngoài cùng bằng `null` có thể khớp `Box(...)`.

### Kết hợp record pattern với when

Nếu cần xử lý String rỗng, String có nội dung và Box khác:

```java
static String classifyBox(Object input) {
    return switch (input) {
        case Box(String text) when text.isBlank() -> "blank box";
        case Box(String text) -> "text box=" + text;
        case Box(var payload) -> "other box=" + payload;
        default -> "not box";
    };
}
```

Ở đây độ cụ thể giảm dần:

1. `Box` có `String` và guard `isBlank()`;
2. mọi `Box` có `String`;
3. mọi `Box` còn lại.

Nếu chuyển case thứ ba lên đầu, hai case đầu sẽ bị dominated; nếu chuyển case thứ hai lên trước case thứ nhất, case `when` bị dominated.

## 6. Case hằng số cũng có thể bị pattern rộng che

Dominance không giới hạn ở hai pattern labels. Một **case constant** cũng có thể bị một type pattern không có guard ở phía trước bao phủ.

Với selector kiểu `Integer`:

```java
// Không biên dịch: case 42 đã bị Integer i bao phủ.
static String badInteger(Integer input) {
    return switch (input) {
        case Integer i -> "some integer";
        case 42 -> "forty-two";
    };
}
```

Đặt hằng cụ thể trước:

```java
static String goodInteger(Integer input) {
    return switch (input) {
        case 42 -> "forty-two";
        case Integer i -> "some integer";
    };
}
```

Mẫu tương tự xảy ra với một số case của `enum` nếu đặt type pattern tổng quát tương ứng lên trước các hằng enum cụ thể. Đây là quy tắc về phạm vi giá trị được bao phủ, không liên quan đến tên hằng hay tên biến.

**Đừng áp dụng máy móc “cứ constant trước pattern” cho mọi tình huống**. Quy tắc chính xác phụ thuộc kiểu selector, tính *unconditional* của pattern và khả năng áp dụng của case constant; khi nghi ngờ, dùng `javac` để đối chiếu với JLS.

## 7. default, null và case tổng quát

### default thường nên đặt cuối

Với pattern switch, `default` biểu diễn nhánh dự phòng. Nếu đặt `default` trước một case pattern, Java có thể báo lỗi; với `case null, default`, không được đặt case nào phía sau.

```java
// Sai cho pattern switch:
return switch (input) {
    default -> "other";
    case String text -> "text"; // default đặt trước pattern.
};
```

Đồng thời, nếu case pattern trước đó **unconditional đối với kiểu selector**, ví dụ `case Object other` với selector `Object`, thì thêm `default` cũng không hợp lệ vì có hai nhãn đóng vai trò fallback cho cùng selector:

```java
// Sai: Object other đã xử lý mọi Object khác null.
return switch (input) {
    case Object other -> "object";
    default -> "other";
};
```

**Sắc thái ngôn ngữ:** Java vẫn cho phép một số `default` đứng trước case hằng trong dạng switch cũ để tương thích ngược; vì vậy không nên phát biểu rằng từ khóa `default` *luôn* phải ở cuối trong mọi chương trình Java. Trong code có pattern matching, đặt nó cuối là quy ước rõ ràng và ít lỗi.

### null selector không khớp Object pattern thông thường

`case Object other` không phải `case null`. Nếu `switch` dùng selector là `null` và không có `case null`, hành vi mặc định của pattern switch là ném `NullPointerException`, không tự vào `default` hoặc `case Object`.

```java
static String nullable(Object input) {
    return switch (input) {
        case null -> "null selector";
        case String text -> "text=" + text;
        case Object other -> "other object";
    };
}
```

Đoạn trên xử lý `null` rõ ràng và vẫn không cần `default` vì `Object other` phủ mọi đối tượng tham chiếu còn lại. Ở đây `case null` đứng đầu chỉ để dễ đọc; nó là quy tắc xử lý riêng cho `null`, không phải một kiểu con của `Object`.

## 8. Sealed hierarchy: exhaustive khác dominance

Xét domain model đóng:

```java
sealed interface Shape permits Circle, Rectangle {}
record Circle(int radius) implements Shape {}
record Rectangle(int width, int height) implements Shape {}
```

`sealed` báo cho compiler các kiểu con trực tiếp được phép. Khi các subtype đã liệt kê đều là record (mặc định `final`), `switch expression` có thể exhaustive mà không cần `default`:

```java
static String describeShape(Shape shape) {
    return switch (shape) {
        case Circle(int radius) when radius == 0 -> "point-circle";
        case Circle(int radius) -> "circle radius=" + radius;
        case Rectangle(var width, var height) ->
                "rectangle area=" + (width * height);
    };
}
```

- Nhánh `Circle` có guard phải đứng trước nhánh `Circle` tổng quát.
- Nhánh tổng quát `Circle(int radius)` bao phủ mọi `Circle` còn lại.
- Nhánh `Rectangle` xử lý toàn bộ subtype thứ hai.
- Không cần `default` vì mọi loại `Shape` khác `null` trong mô hình hiện tại đã được xử lý.
- Nếu thêm subtype mới được phép, compiler thường yêu cầu cập nhật switch để khôi phục **exhaustiveness**. Điều này khác lỗi dominance do thứ tự case.
- `shape == null` không được case nào ở trên xử lý; gọi `describeShape(null)` sẽ ném `NullPointerException`. Nếu nghiệp vụ cho phép null, thêm `case null` với hành vi rõ ràng.

**Thiết kế tốt:** tận dụng `sealed` để compiler bắt thiếu biến thể, thay vì tự động thêm `default` rồi che những trường hợp mới chưa được xử lý.

## 9. Ví dụ Java 21 hoàn chỉnh có thể chạy

Lưu tệp **`CaseDominanceDemo.java`** như sau:

```java
public class CaseDominanceDemo {
    record Box(Object value) {}

    sealed interface Shape permits Circle, Rectangle {}
    record Circle(int radius) implements Shape {}
    record Rectangle(int width, int height) implements Shape {}

    static String describe(Object input) {
        return switch (input) {
            case null -> "null selector";
            case Box(String text) when text.isBlank() -> "blank box";
            case Box(String text) -> "text box=" + text;
            case Box(var value) -> "other box=" + value;
            case String text when text.isBlank() -> "blank string";
            case String text -> "string=" + text;
            case CharSequence chars -> "chars length=" + chars.length();
            case Integer number when number == 0 -> "zero";
            case Integer number -> "integer=" + number;
            case Number number -> "number=" + number;
            case Object other -> "other=" + other.getClass().getSimpleName();
        };
    }

    static String describeShape(Shape shape) {
        return switch (shape) {
            case Circle(int radius) when radius == 0 -> "point-circle";
            case Circle(int radius) -> "circle radius=" + radius;
            case Rectangle(var width, var height) ->
                    "rectangle area=" + (width * height);
        };
    }

    public static void main(String[] args) {
        Object[] inputs = {
                new Box("  "), new Box("Hi"), new Box(42), new Box(null),
                " ", "Java", new StringBuilder("xy"),
                0, 7, 3.5, true, null
        };
        for (Object input : inputs) {
            System.out.println(describe(input));
        }
        System.out.println(describeShape(new Circle(0)));
        System.out.println(describeShape(new Circle(2)));
        System.out.println(describeShape(new Rectangle(3, 4)));
    }
}
```

Dùng JDK 21+ để biên dịch và chạy:

```bash
javac --release 21 -encoding UTF-8 CaseDominanceDemo.java
java CaseDominanceDemo
```

**Stdout chính xác:**

```text
blank box
text box=Hi
other box=42
other box=null
blank string
string=Java
chars length=2
zero
integer=7
number=3.5
other=Boolean
null selector
point-circle
circle radius=2
rectangle area=12
```

Cách đọc kết quả:

1. `new Box("  ")` khớp record pattern có `String`, sau đó guard `text.isBlank()` đúng nên trả `blank box`.
2. `new Box("Hi")` đi qua guard đầu không thành công, rồi khớp `Box(String text)` tổng quát.
3. `new Box(42)` và `new Box(null)` đều được `Box(var value)`; component pattern `var` không yêu cầu giá trị khác `null`.
4. Chuỗi blank và chuỗi có nội dung được xử lý bởi hai nhánh `String` đứng trước nhánh `CharSequence`; `StringBuilder("xy")` đi tới `CharSequence`.
5. `Integer 0` được nhánh có `when number == 0`; `Integer 7` được nhánh `Integer` tổng quát; `Double 3.5` khớp `Number`.
6. `Boolean true` chỉ khớp nhánh `Object` cuối; selector `null` có nhánh riêng.
7. `Shape` loại `Circle` dùng guard đặc biệt cho bán kính 0, còn loại `Rectangle` tính diện tích.

Chương trình được kiểm chứng bằng `javac --release 21` và thực thi thành công với **15 dòng stdout** đúng như trên.

## 10. Mẫu lỗi tái hiện được bằng javac

Đoạn dưới đây là **một chương trình Java cố ý sai** để học cách đọc diagnostic. **Không dùng nó làm ví dụ chạy**; khi biên dịch, ta kỳ vọng gặp lỗi dominance ở ba vị trí.

Lưu tên **`DominatedCases.java`** để tự thực nghiệm riêng:

```java
public class DominatedCases {
    record Box(Object value) {}

    static String wideTypeFirst(Object input) {
        return switch (input) {
            case CharSequence chars -> "general";
            case String text -> "specific";  // Lỗi 1: String bị che
            default -> "other";
        };
    }

    static String wideRecordFirst(Object input) {
        return switch (input) {
            case Box(var payload) -> "general box";
            case Box(String text) -> "text box"; // Lỗi 2: record hẹp bị che
            default -> "not box";
        };
    }

    static String wideGuardFirst(Object input) {
        return switch (input) {
            case String text -> "any text";
            case String text when text.isBlank() -> "blank text"; // Lỗi 3
            default -> "other";
        };
    }
}
```

Dùng:

```bash
javac --release 21 -encoding UTF-8 DominatedCases.java
```

`javac` từ chối biên dịch và ghi ba diagnostic thuộc dạng:

```text
error: this case label is dominated by a preceding case label
3 errors
```

Tên tệp, số dòng và cách xuống dòng của diagnostic tùy môi trường. Thực nghiệm với `javac --release 21` đã xác nhận **ba lỗi** tương ứng với `case String text`, `case Box(String text)` và `case String text when text.isBlank()`.

Hướng sửa: đổi chỗ `CharSequence/String`; đặt `Box(String text)` trước `Box(var payload)`; đặt case `String` có guard trước case `String` không guard. Chương trình ở mục 9 chính là ví dụ đã sửa và chạy được.

## 11. So sánh với if/else if và cách đọc mã cũ

Một chuỗi `if/else if` cũng được xét theo thứ tự:

```java
static String ifElse(Object input) {
    if (input instanceof CharSequence chars) {
        return "sequence";
    } else if (input instanceof String text) {
        return "string";
    }
    return "other";
}
```

Mã này có thể biên dịch, nhưng đối với một giá trị `String`, nhánh `CharSequence` luôn đúng trước, khiến nhánh `String` không được chọn trong chuỗi điều kiện đó. **Không nên suy luận rằng mọi lỗi logic do thứ tự trong `if/else if` sẽ được compiler bắt như dominance của pattern switch.**

Khi refactor, thay thứ tự ngay từ thiết kế:

```java
static String ifElseFixed(Object input) {
    if (input instanceof String text) {
        return "string";
    } else if (input instanceof CharSequence chars) {
        return "sequence";
    }
    return "other";
}
```

Bài học không chỉ là “đảo hai dòng”. Cần hiểu **quan hệ bao phủ tập đầu vào** của từng nhánh để giữ logic và kết quả mong muốn khi chuyển từ `if` sang `switch`.

## 12. Quy trình sửa lỗi dominance

Khi thấy `this case label is dominated by a preceding case label`, dùng trình tự này:

1. **Xác định case bị báo lỗi.** Thông báo thường chỉ case **ở phía sau**; nguyên nhân nằm ở một case rộng hơn **đứng trước**.
2. **Liệt kê mọi case trước nó.** Chú ý type pattern dựa trên superclass/interface, record pattern dùng `var` hoặc component pattern rộng, và case không có guard.
3. **So sánh tập giá trị khớp.** Hỏi: nếu giá trị khớp case đang lỗi, liệu nó luôn khớp case trước hay không? Với `String` và `CharSequence`, câu trả lời là có.
4. **Kiểm tra guard `when`.** Một guard nghiệp vụ có thể làm case cụ thể hơn; đặt nhánh có guard trước nhánh cùng pattern không có guard. Nhớ ngoại lệ `when true`.
5. **Đổi thứ tự hẹp → rộng.** Đặt hằng hoặc biến thể đặc biệt, sau đó type/record pattern cụ thể, cuối cùng case rộng hoặc fallback.
6. **Đảm bảo exhaustive sau khi sửa.** Đảo case không tự bổ sung khả năng chưa xử lý; nếu `switch expression` thiếu trường hợp, cần thêm case đúng nghĩa.
7. **Kiểm tra riêng selector null.** `case Object other` không bắt `null`; nếu `null` là đầu vào hợp lệ, xác định rõ hành vi với `case null`.
8. **Biên dịch lại và chạy test.** Thử các kiểu con, interface, thành phần record có `null`, giá trị nằm ngay ranh giới guard, và kiểu không khớp case chuyên biệt.

### Bảng nhận diện nhanh

| Đặt trước (rộng) | Đặt sau (hẹp) | Cách sửa |
| --- | --- | --- |
| `case CharSequence cs` | `case String s` | `String` trước `CharSequence` |
| `case Number n` | `case Integer i` | `Integer` trước `Number` |
| `case Object o` | `case String s` | `Object` cuối, bỏ `default` trùng nếu có |
| `case Box(var v)` | `case Box(String s)` | `Box(String s)` trước `Box(var v)` |
| `case String s` | `case String s when s.isBlank()` | Case có `when` trước |
| `case Integer i` | `case 42` | Hằng `42` trước pattern tổng quát |
| `default` | Một case pattern | Đặt fallback cuối, kiểm tra cấu trúc switch |

Không phải mọi nhánh trước đều là vấn đề. Nếu hai kiểu không có quan hệ bao phủ thì việc một case xuất hiện trước không tự động làm case phía sau bị dominated.

## 13. Bài tập tự kiểm tra

**Bài 1.** Vì sao đoạn sau lỗi?

```java
return switch (input) {
    case Number n -> "number";
    case Double d -> "double";
    default -> "other";
};
```

*Đáp án:* `Double` là subtype của `Number`, nên case `Number n` không guard bao phủ case `Double d`. Sửa bằng cách đặt `case Double d` trước `case Number n`.

**Bài 2.** Hai case sau có hợp lệ khi đặt theo thứ tự này không?

```java
return switch (input) {
    case String s when s.length() == 0 -> "empty";
    case String s -> "some string";
    default -> "other";
};
```

*Đáp án:* Có. Case `when` trước chỉ xử lý chuỗi rỗng; case thứ hai xử lý `String` còn lại.

**Bài 3.** Với `record Box(Object value) {}`, vì sao `Box(var value)` đặt trước `Box(String s)` gây lỗi?

*Đáp án:* `Box(var value)` khớp mọi `Box` khác `null`, kể cả `Box` có payload `String`. Vì thế `Box(String s)` không thể được chọn.

**Bài 4.** Tại sao `case Object o` ở cuối không thể thay thế hoàn toàn `case null`?

*Đáp án:* Type pattern ở cấp selector không khớp `null`. Nếu không có `case null`, selector `null` trong pattern switch thường ném `NullPointerException`, kể cả khi có `default`.

**Bài 5.** Nếu `switch` trên `sealed interface Shape` đã có đủ case `Circle` và `Rectangle` mà không có `default`, việc thêm subtype mới có tác động gì?

*Đáp án:* Khi tập subtype được phép thay đổi, các switch expression exhaustive có thể không còn đủ trường hợp và compiler yêu cầu cập nhật. Đây là kiểm tra **exhaustiveness**, không phải dominance. Sau khi thêm case mới, vẫn cần đặt đúng thứ tự nếu kiểu mới có quan hệ bao phủ với case khác.

**Tài liệu chính thức:** [JLS Java 21 `14.11.1 – Switch Blocks, Dominance](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.11.1), [JLS Java 21 `14.30.3 – Properties of Patterns](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.30.3), [JEP 441 – Pattern Matching for switch](https://openjdk.org/jeps/441), [JEP 440 – Record Patterns](https://openjdk.org/jeps/440), [Oracle Java 21 – Pattern Matching for switch](https://docs.oracle.com/en/java/javase/21/language/pattern-matching-switch.html).
