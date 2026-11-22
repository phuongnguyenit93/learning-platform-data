# Đọc thông báo lỗi dominance trong pattern `switch` của Java

## 1. Dominance là gì, và vì sao cần biết cách đọc lỗi?

Trong **pattern matching for `switch`** (tính năng chính thức từ Java 21), Java dùng các nhãn `case` để chọn cách xử lý dựa trên kiểu đối tượng, hằng số, record pattern và điều kiện `when`. Mỗi nhãn có thể nhận một tập giá trị.

Một nhãn `case` bị **dominated** khi một nhãn đứng **trước** đã bao phủ tất cả giá trị mà nhãn đứng **sau** có thể nhận theo quy tắc dominance của ngôn ngữ. Khi đó nhánh sau không thể được chọn, nên compiler từ chối chương trình.

Ví dụ:

```java
static String describe(Object value) {
    return switch (value) {
        case CharSequence text -> "sequence";
        case String text -> "string"; // LỖI: nhánh sau bị dominate
        default -> "other";
    };
}
```

`String` hiện thực `CharSequence`. Vì vậy mọi giá trị khớp `case String text` cũng đã khớp `case CharSequence text` phía trước. Đó là xung đột **tập giá trị khớp**, không phải xung đột **tên biến**; việc đổi biến thứ hai thành `s` sẽ không sửa được lỗi.

Thông báo Java compiler thường có dạng:

```text
error: this case label is dominated by a preceding case label
```

Thông điệp này có ba manh mối quan trọng:

- **`this case label`:** nhãn được đánh dấu trong chẩn đoán là nhãn **bị che khuất**, thường nằm phía dưới.
- **`is dominated`:** compiler biết theo quy tắc kiểu/pattern rằng nhãn ấy không còn cơ hội được chọn.
- **`by a preceding case label`:** phải tìm **nhãn ở phía trên** bao phủ nó; nhãn gây lỗi không nhất thiết nằm ngay trước một dòng.

Từ đó có thể đặt câu hỏi đúng: **“Case nào trước đó đã nhận mọi giá trị của case đang được đánh dấu?”** thay vì chỉ chỉnh sửa đoạn lệnh nằm trong thân case.

## 2. Đọc một chẩn đoán `javac` từng phần

Giả sử file `DominatedExample.java` chứa:

```java
public class DominatedExample {
    static String inspect(Object value) {
        return switch (value) {
            case CharSequence cs -> "sequence";
            case String s -> "string";
            default -> "other";
        };
    }
}
```

Biên dịch bằng **JDK 21 trở lên**:

```bash
javac --release 21 DominatedExample.java
```

Đây là **ví dụ cố ý không biên dịch**. Nội dung chẩn đoán thường tương tự:

```text
DominatedExample.java:5: error: this case label is dominated by a preceding case label
            case String s -> "string";
                 ^
1 error
```

*Lưu ý:* tên file, cột dấu `^`, cách hiển thị và câu chữ có thể khác theo phiên bản `javac` và giao diện IDE. Hãy nhận diện **bản chất lỗi**, không phụ thuộc vào số dòng hoặc một câu chữ chính xác.

Cách đọc:

1. **Tên file và vị trí:** compiler chỉ đến file và nhãn `case` bị từ chối. Không nhất thiết đó là nơi bắt nguồn vấn đề về thứ tự.
2. **Loại lỗi:** từ “dominated” báo rằng case sau đã bị phủ bởi case trước.
3. **Kiểu pattern bị đánh dấu:** ở đây là `String`.
4. **Tìm ngược các case phía trên:** `CharSequence` là superinterface của `String`, nên pattern phía trên nhận mọi `String`.
5. **Xác định mục đích:** có cần phân biệt `String` với `StringBuilder` và các `CharSequence` khác không? Nếu có, đặt `String` trước. Nếu không, bỏ nhánh `String` dư thừa.

Sửa đúng:

```java
static String inspect(Object value) {
    return switch (value) {
        case String s -> "string";
        case CharSequence cs -> "sequence";
        default -> "other";
    };
}
```

Lúc này `"abc"` đi vào case `String`; `new StringBuilder("abc")` đi vào case `CharSequence`. Mỗi nhánh đều có khả năng được chọn.

**Không sửa theo kiểu đối phó:** đổi tên pattern variable, thêm `break` ở nhánh `->`, hoặc đổi chuỗi trả về **không thay đổi** quan hệ subtype đã gây dominance.

## 3. Những quan hệ kiểu thường gây dominated case

### 3.1. Class cha đứng trước class con

Với `Integer extends Number`, ví dụ này lỗi:

```java
// LỖI: Integer bị case Number phía trên che khuất.
static String invalid(Object value) {
    return switch (value) {
        case Number n -> "number";
        case Integer i -> "integer";
        default -> "other";
    };
}
```

Vì một `Integer` luôn là `Number`, nhánh `Integer` không bao giờ chạy. Sửa bằng cách xử lý từ hẹp đến rộng:

```java
static String valid(Object value) {
    return switch (value) {
        case Integer i -> "integer";
        case Number n -> "number";
        default -> "other";
    };
}
```

Cũng lưu ý: `Long`, `Double` và các subtype khác của `Number` có thể đi vào nhánh `Number`, còn `Integer` đi vào nhánh đầu.

### 3.2. Interface rộng đứng trước class hoặc interface hẹp

```java
// LỖI:
return switch (value) {
    case CharSequence cs -> "char sequence";
    case String s -> "string"; // String implements CharSequence
    default -> "other";
};
```

Không chỉ `extends` giữa hai class, quan hệ `implements` cũng ảnh hưởng dominance. `StringBuilder` cũng là `CharSequence`, nhưng nó không phải `String`; do vậy đặt `String` trước `CharSequence` có ý nghĩa.

### 3.3. Hai type pattern giống nhau nhưng khác tên

```java
// LỖI:
return switch (value) {
    case String first -> "first";
    case String second -> "second"; // Dominated
    default -> "other";
};
```

Tên biến khác nhau không tạo ra hai điều kiện match khác nhau. Cả hai đều kiểm tra cùng một kiểu `String` (không guard), nên nhánh sau bị che khuất.

### 3.4. Pattern cha phủ cả nhánh con của sealed hierarchy

Giả sử:

```java
sealed interface Shape permits Circle, Square {}
record Circle(int radius) implements Shape {}
record Square(int side) implements Shape {}
```

Đây là thứ tự sai:

```java
// LỖI trong ngữ cảnh Shape ở trên:
return switch (shape) {
    case Shape s -> "any shape";
    case Circle c -> "circle"; // Dominated
};
```

`case Shape s` không guard đã nhận mọi `Shape` khác `null`, bao gồm `Circle`. Nếu muốn xử lý `Circle` riêng, đặt `case Circle c` trước rồi mới đến pattern tổng quát. Nếu muốn xử lý mọi subtype tường minh, dùng `case Circle` và `case Square` mà không cần `case Shape`.

## 4. Lỗi dominance khi dùng `when`

Guard `when` là điều kiện bổ sung được đánh giá **sau khi pattern khớp**. Nó cho phép các nhánh cùng kiểu xử lý những miền giá trị khác nhau, nhưng thứ tự quan trọng.

### 4.1. Không guard trước, có guard sau: bị dominated

```java
// LỖI:
return switch (value) {
    case String s -> "all strings";
    case String s when s.isBlank() -> "blank"; // Dominated
    default -> "other";
};
```

Pattern đầu nhận **mọi String**, nên nhánh sau không còn giá trị nào để xử lý.

### 4.2. Guard trước, không guard sau: hợp lệ

```java
return switch (value) {
    case String s when s.isBlank() -> "blank";
    case String s -> "non-blank text";
    default -> "other";
};
```

Nếu `s.isBlank()` sai, chương trình tiếp tục tìm case áp dụng; `case String s` không guard tiếp nhận các chuỗi còn lại. Đây là mẫu **case chuyên biệt → case tổng quát cùng kiểu**.

### 4.3. `when true` không phải cách tránh dominance

```java
// LỖI:
return switch (value) {
    case String s when true -> "first";
    case String s -> "second"; // Dominated
    default -> "other";
};
```

Trong Java 21, guard bằng constant expression `true` không hạn chế pattern; khi phân tích dominance nó được xem tương tự một pattern không guard. Nếu compiler báo dominated trong trường hợp này, hãy tìm `when true` như một thủ phạm.

Và guard có giá trị **constant `false`** cũng là lỗi biên dịch riêng:

```java
// LỖI: guard là constant expression false.
return switch (value) {
    case String s when false -> "never";
    default -> "other";
};
```

Đây không phải một mẹo để tạo nhánh dự phòng không thể chạy; Java không cho guard hằng false trong case label.

### 4.4. Hai guard có quan hệ logic vẫn có thể biên dịch

Đoạn sau **có thể biên dịch** nhưng nhánh thứ hai vô dụng về mặt logic:

```java
static String classify(Object value) {
    return switch (value) {
        case Integer n when n > 0 -> "positive";
        case Integer n when n > 10 -> "large";
        case Integer n -> "not positive";
        default -> "other";
    };
}
```

Mọi `n > 10` cũng có `n > 0`, nên nhánh `"large"` không bao giờ được chọn. Tuy nhiên Java compiler **không giải toán logic tổng quát** cho các biểu thức `when` thông thường để báo dominance.

Sửa theo ưu tiên:

```java
static String classify(Object value) {
    return switch (value) {
        case Integer n when n > 10 -> "large";
        case Integer n when n > 0 -> "positive";
        case Integer n -> "not positive";
        default -> "other";
    };
}
```

**Giới hạn cần hiểu:** *không có lỗi dominance* không đồng nghĩa với *không có nhánh logic chết*. Khi rà soát các guard, hãy tự kiểm tra quan hệ bao hàm, kể cả khi compiler chấp nhận mã.

## 5. Trùng hằng `case` không phải cùng loại lỗi dominance

Một lỗi dễ bị nhầm là **duplicate case label**:

```java
// LỖI: hai constant label có cùng giá trị.
static String invalid(int x) {
    return switch (x) {
        case 1 -> "one";
        case 1 + 0 -> "one again";
        default -> "other";
    };
}
```

Vì `1 + 0` là constant expression có giá trị `1`, compiler phát hiện **trùng hằng**. Chẩn đoán thường chứa:

```text
error: duplicate case label
```

Đây là trường hợp khác với quan hệ `CharSequence` và `String`: vấn đề nằm ở **giá trị hằng lặp lại**, không phải tập kiểu được pattern trước bao phủ.

Cách xử lý:

- Nếu hai hằng chỉ cùng một giá trị, **xóa nhãn lặp** hoặc gộp logic vào một nhánh.
- Nếu muốn nhóm nhiều giá trị **khác nhau**, dùng `case 1, 2 -> ...`.
- Nếu muốn xử lý kiểu con/hằng cụ thể trước nhánh rộng, hãy đổi **thứ tự**, không phải xóa bừa.
- Hai `case null` hoặc hai `default` cũng gây lỗi nhãn bị lặp, không phải lỗi subtype dominance thuần túy.

Ví dụ hợp lệ:

```java
static String category(int x) {
    return switch (x) {
        case 1, 2 -> "small";
        case 3 -> "three";
        default -> "other";
    };
}
```

`case 1, 1 ->` vẫn sai vì trùng giá trị ngay trong cùng nhãn.

## 6. Hằng số có thể bị type pattern phía trước che khuất

Không phải chỉ có pattern–pattern mới gây dominance. Với selector kiểu `Integer`:

```java
// LỖI:
static String invalid(Integer n) {
    return switch (n) {
        case Integer value -> "any integer";
        case 1 -> "one"; // Case 1 bị dominated
    };
}
```

`case Integer value` không guard nhận mọi giá trị `Integer` khác `null`, bao gồm giá trị `1`. Compiler có thể báo rằng nhãn hằng sau đã bị nhánh trước dominate.

Đặt hằng đặc biệt trước pattern tổng quát:

```java
static String valid(Integer n) {
    return switch (n) {
        case 1 -> "one";
        case Integer value when value > 0 -> "positive";
        case Integer value -> "other integer";
    };
}
```

Đoạn này exhaustive cho các giá trị `Integer` **khác null**. Nếu truyền `null` và không có `case null`, `switch` vẫn ném `NullPointerException`.

Một guard tùy ý đứng trước hằng có thể tạo ra lỗi **logic** dù compiler không báo dominated:

```java
static String confusing(Integer n) {
    return switch (n) {
        case Integer value when value > 0 -> "positive";
        case 1 -> "one"; // Hợp lệ về cú pháp, nhưng 1 đã vào nhánh trên
        case Integer value -> "other";
    };
}
```

Sắp xếp an toàn và dễ đọc: **hằng cần ưu tiên → pattern có guard đặc biệt → pattern không guard rộng**.

## 7. Chẩn đoán khác: unconditional pattern và `default` xung đột

Với selector có kiểu tĩnh `Object`, pattern `case Object value` không guard có khả năng nhận mọi đối tượng `Object` khác null. Nếu thêm một `default` riêng, compiler có thể đưa ra thông báo:

```text
error: switch has both an unconditional pattern and a default label
```

Ví dụ cố ý sai:

```java
static String invalid(Object input) {
    return switch (input) {
        case Object obj -> "object";
        default -> "other"; // Không kết hợp fallback kiểu này
    };
}
```

Khác với lỗi subtype thông thường, thông báo không nhất thiết dùng từ `dominated`, nhưng vẫn liên quan việc **hai nhánh đều muốn đóng vai trò bắt tất cả giá trị còn lại**.

Cách sửa:

```java
static String withDefault(Object input) {
    return switch (input) {
        case String s -> "text:" + s;
        default -> "other";
    };
}
```

Hoặc, nếu cần một pattern variable kiểu `Object`:

```java
static String withTotalPattern(Object input) {
    return switch (input) {
        case String s -> "text:" + s;
        case Object obj -> "other:" + obj.getClass().getSimpleName();
    };
}
```

**Lưu ý `null`:** một type pattern thông thường như `case Object obj` không match `null`; `default` đứng riêng cũng không xử lý `null` trong pattern `switch` Java 21. Nếu `input` có thể null, thêm `case null` và xác định chính sách rõ ràng.

```java
static String withNull(Object input) {
    return switch (input) {
        case null -> "missing";
        case String s -> s;
        default -> "other";
    };
}
```

Không dùng `case null, String s` như một cách gộp nhánh: nhãn kết hợp đó không hợp lệ vì đường `null` không có giá trị để khởi tạo `s`. Dạng hợp lệ khi muốn gộp null với fallback là `case null, default`.

## 8. Chẩn đoán khác: `switch` chưa exhaustive

Nếu `switch expression` còn nhiều giá trị chưa được xử lý, javac có thể báo:

```text
error: the switch expression does not cover all possible input values
```

Ví dụ:

```java
// LỖI: chỉ bao phủ String và Integer; Object còn nhiều khả năng.
static String incomplete(Object value) {
    return switch (value) {
        case String s -> "text";
        case Integer n -> "integer";
    };
}
```

Đây là **lỗi thiếu nhánh**, không phải dominated: không có một nhánh thừa bị phủ; trái lại, **thiếu coverage** cho phần còn lại. Sửa bằng cách thêm `default` (nếu muốn fallback) hoặc bổ sung các pattern bao phủ đầy đủ kiểu selector.

Trong Java 21, `switch expression` và **enhanced `switch` statement** có pattern phải exhaustive. Một legacy `switch statement` trên `int` hoặc enum không dùng pattern có thể không cần `default` và vẫn biên dịch, vì quy tắc của nó khác.

Với sealed hierarchy, một `switch` trên kiểu sealed có thể exhaustive mà **không cần `default`** nếu các subtype được phép đã được bao phủ. Khi đó việc thêm `default` vô tội vạ có thể che tín hiệu hữu ích nếu sau này một subtype mới được thêm vào hệ phân cấp và ứng dụng được biên dịch lại.

**Cách phân biệt nhanh:**

| Thông báo | Vấn đề chính | Cách bắt đầu sửa |
| --- | --- | --- |
| `dominated by a preceding case label` | Case **sau** đã bị case **trước** bao phủ | Tìm pattern/constant rộng phía trên |
| `duplicate case label` | Nhãn hằng hoặc `null` bị lặp | Xóa/gộp nhãn có cùng giá trị |
| `duplicate default label` | Có nhiều `default` | Chỉ giữ một fallback |
| `unconditional pattern and a default label` | Có hai cơ chế bắt mọi giá trị non-null | Chọn một cơ chế tổng quát |
| `does not cover all possible input values` | Switch **thiếu** coverage | Bổ sung nhánh hoặc default |
| `guard ... constant expression ... false` | Case có guard hằng false không hợp lệ | Xóa nhánh hoặc sửa điều kiện |

Không phải mọi lỗi trong bảng đều là lỗi dominance, nhưng chúng thường xuất hiện trong cùng một lần sửa `switch`. Đọc đúng thông điệp sẽ tránh chữa một lỗi bằng cách gây ra lỗi khác.

## 9. Giao nhau về giá trị nhưng **không** bị dominated

Hai type pattern đôi khi cùng khớp **một số** đối tượng mà không có pattern nào bao phủ **mọi** đối tượng của pattern kia. Trường hợp này có thể hợp lệ.

```java
static String byInterface(Object value) {
    return switch (value) {
        case CharSequence cs -> "sequence";
        case java.io.Serializable serializable -> "serializable";
        default -> "other";
    };
}
```

Một `String` hiện thực cả `CharSequence` lẫn `Serializable`, nên `"abc"` có thể khớp cả hai. Tuy nhiên `CharSequence` không phải subtype của `Serializable` và chiều ngược lại cũng không đúng; mỗi interface có những implementation không thuộc interface kia. Do đó không có quan hệ dominance bao phủ toàn bộ theo kiểu của ví dụ này.

Nhánh đứng trước được chọn khi một giá trị khớp cả hai. Nếu đảo thứ tự, kết quả với `String` có thể đổi, dù mã vẫn biên dịch.

**Cách đọc lỗi ở đây:** nếu javac **không** báo dominance, bạn vẫn cần hỏi:
- Có giá trị nào khớp nhiều nhánh không?
- Thứ tự chọn nhánh có thể làm sai ưu tiên nghiệp vụ không?
- Có nên tạo nhánh cho kiểu cụ thể (ví dụ `String`) đứng trước hai interface tổng quát không?

Dominance là lỗi được compiler phát hiện; *overlap* chỉ là sự giao nhau cần được lập trình viên hiểu và kiểm thử.

## 10. Chương trình Java 21 chạy độc lập sau khi sửa dominance

Lưu vào file **`DominanceDiagnosticsDemo.java`**:

```java
public class DominanceDiagnosticsDemo {
    static String classify(Object value) {
        return switch (value) {
            case null -> "null";

            case String s when s.isBlank() -> "blank";
            case String s -> "text:" + s;

            case Integer n when n >= 0 -> "nonnegative-int:" + n;
            case Integer n -> "negative-int:" + n;

            case Number n ->
                "other-number:" + n.getClass().getSimpleName();

            case CharSequence cs ->
                "char-sequence:" + cs.getClass().getSimpleName();

            default -> "other:" + value.getClass().getSimpleName();
        };
    }

    static String classifyGuard(Object value) {
        return switch (value) {
            case Integer n when n > 10 -> "large";
            case Integer n when n > 0 -> "positive";
            case Integer n -> "nonpositive";
            default -> "not-integer";
        };
    }

    public static void main(String[] args) {
        Object[] values = {
            null, " ", "Java", 4, -2, 3.5,
            new StringBuilder("hi"), true
        };

        for (Object value : values) {
            System.out.println(classify(value));
        }

        System.out.println("12:" + classifyGuard(12));
        System.out.println("5:" + classifyGuard(5));
        System.out.println("0:" + classifyGuard(0));
    }
}
```

Biên dịch và chạy bằng JDK 21 trở lên:

```bash
javac --release 21 DominanceDiagnosticsDemo.java
java DominanceDiagnosticsDemo
```

Kết quả:

```text
null
blank
text:Java
nonnegative-int:4
negative-int:-2
other-number:Double
char-sequence:StringBuilder
other:Boolean
12:large
5:positive
0:nonpositive
```

Giải thích cách các case không còn che khuất nhau:

1. `case null` xử lý null rõ ràng; không nhầm `default` với null.
2. `String` rỗng/trắng đi vào nhánh guarded; các `String` khác đi vào nhánh `String` không guard.
3. `Integer` không âm đi vào nhánh có guard; `Integer` âm đi vào nhánh cùng kiểu không guard.
4. `Number` được đặt **sau** `Integer`, nên xử lý các số không phải `Integer` như `Double`.
5. `CharSequence` được đặt **sau** `String`, nên xử lý các chuỗi ký tự khác như `StringBuilder`.
6. `default` tiếp nhận các đối tượng non-null còn lại, như `Boolean`.
7. Trong `classifyGuard`, ngưỡng `> 10` đứng trước `> 0`, vì vậy `12` nhận `large`, `5` nhận `positive`, `0` nhận `nonpositive`.

Ví dụ này minh họa **cả dominance do kiểu và ưu tiên guard**. Phần chương trình là mã đầy đủ để chạy; các đoạn được ghi **LỖI** ở những mục trước là ví dụ cố ý không biên dịch và không được ghép vào cùng file này.

## 11. Quy trình sửa một lỗi dominance trong code thật

Khi gặp lỗi từ `javac`, IDE hoặc CI, dùng quy trình sau:

**Bước 1 — Ghi nhận vị trí case bị đánh dấu.** Xem đúng `switch` nào báo lỗi và type pattern/constant nào đang ở nhãn đó. Trường hợp một phương thức có nhiều `switch`, đừng dựa vào tên biến giống nhau ở khối khác.

**Bước 2 — Kiểm tra kiểu tĩnh của selector.** `Object`, `Number`, `Integer`, interface hay sealed class có thể làm các phép kiểm tra kiểu và quan hệ dominance khác nhau. Đừng chỉ nhìn đối tượng được gán ở một dòng test.

**Bước 3 — Tìm nhãn đứng trước bao phủ case được đánh dấu.** Xét `extends`, `implements`, generic type arguments, pattern vô điều kiện và constant case. Một pattern rộng nằm cách nhiều dòng vẫn có thể là thủ phạm.

**Bước 4 — Đọc guard theo nghĩa logic.** Nếu case trước không có guard hoặc có `when true`, nó có thể che hoàn toàn case sau. Nếu case trước có `when` tùy ý, xem liệu sự chồng chéo chỉ là logic nghiệp vụ mà compiler không phát hiện.

**Bước 5 — Chọn sửa theo ý định:** nếu case cụ thể cần hành vi riêng, đặt **cụ thể trước → tổng quát sau**; nếu hai case thực sự xử lý giống nhau, gộp hoặc xóa case thừa; nếu cần ưu tiên điều kiện, đặt guard hẹp trước guard rộng; nếu một nhánh rộng không còn cần thiết, bỏ nó.

**Bước 6 — Kiểm tra lại exhaustiveness.** Sau khi thay/xóa case, `switch expression` hoặc enhanced `switch` có thể thiếu nhánh. Nếu có `default`, cân nhắc liệu default có che mất yêu cầu bảo trì của sealed hierarchy không.

**Bước 7 — Kiểm tra null và runtime.** `default` không tự xử lý selector `null`. Thêm `case null` nếu có chính sách riêng. Nhận diện rằng guard có thể ném ngoại lệ ngay trong quá trình chọn case nếu mã guard truy cập một field/component null không an toàn.

**Bước 8 — Chạy test ranh giới.** Ví dụ với guard số học, test `0`, `1`, `10`, `11`; với chuỗi, test `""`, `" "`, `"abc"`; với subtype, test class cha, class con và interface giao nhau. Nếu có nhiều nhánh chồng lấn, xác minh **nhánh nào thực tế thắng**.

**Bước 9 — Biên dịch bằng phiên bản Java mục tiêu.** Cú pháp `case String s when ...` dùng ổn định từ Java 21; không nên lấy chẩn đoán của Java 17 preview hoặc cú pháp Java đời khác để khẳng định mọi thông báo phải giống nhau. Có thể dùng `javac --release 21 -Xdiags:verbose File.java` để xem thêm ngữ cảnh khi chẩn đoán ngắn khó hiểu.

Một quy tắc sửa code hữu ích: **đừng chỉ làm lỗi biến mất; hãy chứng minh rằng mọi case còn lại đều có một bộ giá trị mục tiêu, và thứ tự case thể hiện đúng ưu tiên xử lý.**

## 12. Những cách sửa sai thường gặp

- **Chỉ đổi tên biến mẫu:** `case String s` và `case String text` cùng kiểu và không guard vẫn có tập giá trị khớp như nhau.
- **Đặt `default` vào cuối và tưởng mọi lỗi được sửa:** `default` giúp coverage nhưng không hợp thức hóa nhánh bị dominated; nó còn có thể xung đột với unconditional pattern.
- **Xóa case cụ thể để chương trình biên dịch:** có thể làm mất xử lý riêng cho subtype, khiến tất cả rơi vào case cha.
- **Cho rằng hai guard giống nhau sẽ luôn bị javac từ chối:** các guard không hằng có thể trùng logic mà không có chẩn đoán.
- **Thấy hai interface overlap và tưởng chắc chắn lỗi:** chỉ có giao nhau một phần chưa đủ để kết luận dominated.
- **Cho rằng lỗi runtime `ClassCastException` là lỗi dominance:** dominance được xác định ở compile time; cast sai là vấn đề runtime khác.
- **Nhầm với `duplicate case label`:** trùng constant là quy tắc riêng; đổi thứ tự hai constant bằng nhau không giúp gì.
- **Đặt supertype trước subtype vì muốn “bắt chung trước”:** thực tế nhánh rộng sẽ chặn nhánh cụ thể phía sau.
- **Quên null:** `case Object o` không có nghĩa selector null match; `default` đơn lẻ cũng không tự xử lý null.
- **Lấy Java 17 làm ví dụ compile chính cho `switch` pattern:** Java 21 mới là mốc sử dụng ổn định của tính năng này.

## 13. Bài tập chẩn đoán có đáp án

**Bài 1.** Thông báo `this case label is dominated by a preceding case label` xuất hiện tại `case Integer i`. Phía trên có `case Number n`. Nhánh nào cần đổi vị trí?

**Đáp án:** Đưa `case Integer i` lên trước `case Number n`, nếu cần xử lý riêng số nguyên. `Integer` là subtype của `Number`, nên nhánh tổng quát trước sẽ che nhánh cụ thể.

**Bài 2.** Hai nhãn `case 1` và `case 1 + 0` báo `duplicate case label`. Có thể đổi thứ tự để sửa không?

**Đáp án:** Không. Hai nhãn luôn có cùng giá trị hằng `1`; phải bỏ nhãn lặp hoặc gộp logic vào một nhánh.

**Bài 3.** Viết `case String s -> ...` rồi `case String t when t.isBlank() -> ...`. Vì sao báo dominated?

**Đáp án:** Pattern đầu đã nhận mọi `String`, kể cả blank. Hãy đưa nhánh có guard lên trước nhánh không guard.

**Bài 4.** Vì sao `case Integer n when n > 0` trước `case Integer n when n > 10` có thể vẫn biên dịch?

**Đáp án:** Javac không giải mọi quan hệ bao hàm giữa các guard tùy ý. Ở runtime, nhánh `n > 10` không được chọn vì mọi số thỏa nó đều đã bị `n > 0` nhận. Đặt guard hẹp hơn trước.

**Bài 5.** Có `case CharSequence cs` và `case java.io.Serializable s`. Giá trị `"abc"` có thể match cả hai. Đây có nhất thiết là lỗi dominance không?

**Đáp án:** Không. Hai interface giao nhau nhưng không interface nào hoàn toàn là subtype của interface kia theo ví dụ. Thứ tự case xác định nhánh thắng cho `String`; compiler có thể chấp nhận cả hai.

**Bài 6.** Có `case Object obj` và `default` riêng trên selector `Object`. Compiler báo lỗi gì về bản chất?

**Đáp án:** Hai cơ chế fallback non-null xung đột; dùng một trong hai. Nếu cần xử lý null, bổ sung `case null` riêng.

**Bài 7.** Compiler báo `the switch expression does not cover all possible input values`. Có nghĩa một case đang bị dominated không?

**Đáp án:** Không. Đây là lỗi **thiếu case bao phủ**, gần như đối lập với lỗi case thừa. Bổ sung nhánh cần thiết hoặc fallback phù hợp.

### Tóm tắt cần nhớ

- Đọc `dominated by a preceding case label` là tín hiệu: **nhìn lên phía trên** để tìm case che phủ.
- Pattern **cụ thể trước, tổng quát sau**; với cùng kiểu, **guard hạn chế trước, unguarded sau**.
- `when true` không tránh dominance; guard tùy ý có thể trùng logic mà compiler không báo.
- Đừng đánh đồng dominance với trùng hằng, hai default, thiếu exhaustiveness hay lỗi runtime.
- Sau khi sửa, kiểm tra **coverage, thứ tự ưu tiên, null và ví dụ ranh giới**.

### Tài liệu chính thức

- [JLS Java SE 21 §14.11 — The switch Statement, nhãn case và dominance](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.11)
- [JLS Java SE 21 §14.30.3 — Properties of Patterns](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.30.3)
- [JLS Java SE 21 §15.28 — Switch Expressions](https://docs.oracle.com/javase/specs/jls/se21/html/jls-15.html#jls-15.28)
- [Oracle Java 21 — Pattern Matching for switch Expressions and Statements](https://docs.oracle.com/en/java/javase/21/language/pattern-matching-switch.html)
- [JEP 441 — Pattern Matching for switch](https://openjdk.org/jeps/441)
