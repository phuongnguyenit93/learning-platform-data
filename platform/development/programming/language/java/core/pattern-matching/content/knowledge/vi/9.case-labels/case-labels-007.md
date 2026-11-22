# Nhiều pattern trong cùng một nhánh `switch` của Java

## 1. “Nhiều pattern trong cùng một nhánh” có thể mang ba nghĩa khác nhau

Trong Java, một `switch` chọn cách xử lý dựa trên giá trị của **selector** (biểu thức trong `switch (...)`). Một nhánh được xác định bằng nhãn `case`; nhãn có thể chứa **hằng** hoặc **pattern**, tùy cú pháp và phiên bản Java.

Khi muốn nhiều trường hợp thực hiện cùng một hành động, cần phân biệt:

1. **Nhiều hằng trong một nhãn `case`**, ví dụ `case "N", "NORTH" -> ...`. Đây là cách gộp các hằng đã được Java hỗ trợ ổn định.
2. **Nhiều nhãn `case` dùng chung một nhóm câu lệnh `:`**, ví dụ `case Ping(): case Pong(): ... break;`. Trong Java 21, cách này hợp lệ với record patterns không khai báo biến pattern.
3. **Nhiều pattern phân cách bằng dấu phẩy ngay trong cùng nhãn `case`**, ví dụ `case Ping(), Pong() -> ...`. Đây là cú pháp mở rộng trong các phiên bản **preview của Java 23–26**; **không thuộc Java 21 chuẩn**. Với cú pháp preview này, các pattern được gộp **không được khai báo biến pattern**.

Bất kể viết theo cách nào, mỗi giá trị selector dẫn tới hành động của nhánh phù hợp theo quy tắc `switch`. “Gộp nhánh” nghĩa là các trường hợp có **chung hành động**, không phải tất cả pattern cùng được đánh giá thành công hay nhiều nhánh cùng chạy.

**Mốc phiên bản:** pattern matching cho `switch` là tính năng chính thức từ **Java 21** (JEP 441). Mở rộng danh sách nhiều pattern trong cùng nhãn `case` được đưa vào chuỗi preview của JEP 455 (Java 23), JEP 488 (Java 24), JEP 507 (Java 25) và JEP 530 (Java 26). Phần chương trình Java 21 ở dưới sử dụng cú pháp **ổn định**, còn ví dụ danh sách nhiều pattern trong cùng nhãn được tách riêng và yêu cầu bật preview.

## 2. Nhiều hằng dùng chung nhánh: khác với nhiều pattern

Với một `String`, nhiều hằng có thể chia sẻ một rule `->`:

```java
static String direction(String word) {
    return switch (word) {
        case "N", "NORTH" -> "UP";
        case "S", "SOUTH" -> "DOWN";
        case null, default -> "UNKNOWN";
    };
}
```

Đây là **phương thức minh họa** đặt trong một lớp Java 21. `direction("N")` và `direction("NORTH")` đều trả `"UP"`; `direction("SOUTH")` trả `"DOWN"`; `direction(null)` trả `"UNKNOWN"`.

Những giá trị `"N"` và `"NORTH"` là **case constants** (hằng), không phải pattern. Trình biên dịch so sánh selector với các hằng của nhóm rồi chỉ thực thi **một nhánh**.

Tương tự, với selector `int` có thể viết `case 1, 2, 3 -> ...`. Không được lấy ví dụ nhóm hằng của selector `String` hoặc `int` rồi mặc định các hằng ấy đều hợp lệ với mọi selector `Object`: kiểu selector và kiểu của hằng vẫn phải đáp ứng quy tắc tương thích của `switch`.

### `case null, default` là một dạng gộp đặc biệt

```java
return switch (value) {
    case String text -> "TEXT: " + text;
    case null, default -> "OTHER";
};
```

Đây là **đoạn minh họa trong phương thức trả về `String`** có selector `value` kiểu `Object`. Nhánh `case null, default` xử lý cả selector bằng `null` lẫn mọi giá trị còn lại không khớp các nhánh trước.

**Giới hạn:** Java 21 cho phép kết hợp `null` với `default` theo cú pháp này, nhưng **không** cho kết hợp `case null, String text -> ...`. Đó không phải một cách khai báo biến `text` an toàn cho giá trị `null`.

## 3. Java 21: nhiều record pattern không khai báo biến trong cùng nhóm `:`

Một **record pattern** như `Ping()` hoặc `Pong()` có thể kiểm tra đối tượng thuộc kiểu record tương ứng. Nếu record không có thành phần, pattern không cần khai báo biến.

```java
record Ping() {}
record Pong() {}

static String grouped(Object value) {
    String result;

    switch (value) {
        case Ping():
        case Pong():
            result = "SIGNAL";
            break;

        case null:
            result = "NULL";
            break;

        default:
            result = "OTHER";
    }

    return result;
}
```

Các khai báo record và phương thức trên là **mã minh họa đặt trong một lớp**. Cú pháp của phần `switch` hợp lệ với Java 21:

- Nhãn `case Ping():` kiểm tra một record `Ping`.
- Nhãn `case Pong():` kiểm tra một record `Pong`.
- Cả hai nhãn cùng gắn vào nhóm câu lệnh `result = "SIGNAL"; break;`. Nếu giá trị khớp **một trong hai**, cùng đoạn mã được chạy.
- `break` ngăn chương trình tiếp tục sang nhóm câu lệnh `case` tiếp theo.
- Không pattern nào ở nhóm này khai báo biến cần được khởi tạo. Đây chính là lý do có thể dùng chung nhóm câu lệnh an toàn.

Đây gọi là **switch-labeled statement group** với dấu `:`. Nó khác với **switch rule** có `->`. Trong Java 21, không thể thay nguyên phần trên bằng `case Ping(), Pong() -> "SIGNAL";` rồi kỳ vọng mức nguồn Java 21 chấp nhận; cú pháp danh sách nhiều pattern kiểu dấu phẩy thuộc bản mở rộng preview mới hơn.

### Tại sao nhóm nhiều nhãn chứa biến pattern lại không hợp lệ?

Cố viết:

```java
// Ví dụ CỐ Ý SAI, không biên dịch:
switch (value) {
    case String text:
    case Integer number:
        System.out.println(text); // Nếu value là Integer thì text chưa được gắn.
        break;
    default:
        break;
}
```

Nếu selector là `Integer`, luồng có thể đi vào nhóm câu lệnh chung theo nhãn `case Integer number:` nhưng biến `text` của nhãn `String text` chưa được khởi tạo. Java ngăn kiểu rơi vào nhóm lệnh chứa pattern variable chưa được gắn. Đây là giới hạn **an toàn và phạm vi biến**, không đơn thuần vì tên của các kiểu khác nhau.

Với cú pháp `:`, còn phải tránh việc một nhóm câu lệnh có thể **fall through** sang nhãn kế tiếp có khai báo pattern variable mà chưa thực hiện phép khớp. Khi pattern có biến, dùng các nhánh `->` riêng biệt thường dễ đọc và ít lỗi hơn.

## 4. Java 21: nhiều pattern có biến và hành động giống nhau thì làm thế nào?

Hãy giả sử bạn muốn xử lý cả `String` lẫn `Integer` bằng một logic chuẩn hóa chung. Cách viết sau **không hợp lệ** ở Java 21:

```java
// Không biên dịch ở Java 21:
return switch (value) {
    case String text, Integer number ->
        "Value: " + value;
    default -> "Other";
};
```

Vấn đề đầu tiên là **Java 21 không có cú pháp nhiều case patterns ngăn bằng dấu phẩy**. Ngoài ra, ngay trong các bản preview hỗ trợ cú pháp ấy, đây vẫn **không hợp lệ** vì mỗi pattern khai báo biến khác nhau: ở thân nhánh sẽ không có bảo đảm rằng `text` hay `number` đã được gắn.

### Cách 1 — tách nhãn `case`, chia sẻ phương thức xử lý

```java
static String format(Object value) {
    return switch (value) {
        case String text -> common(text);
        case Integer number -> common(number);
        case null, default -> "Other";
    };
}

static String common(Object value) {
    return "Value: " + value;
}
```

Đây là **hai phương thức minh họa trong một lớp**. Mỗi nhánh độc lập gắn một biến có kiểu rõ ràng, nhưng cùng gọi `common(...)`. Không cần sao chép logic nghiệp vụ; `common` nhận `Object` nên có thể nhận `String` hoặc `Integer`.

Trong ví dụ ngắn, kết quả có thể tạo trực tiếp từ `value`. Nhưng khi nghiệp vụ cần kiểm tra, log, định dạng hoặc gọi dịch vụ, phương thức chung giúp tránh lặp logic và giữ phạm vi biến pattern rõ ràng.

### Cách 2 — dùng một supertype hoặc interface chung, nếu phù hợp

Nếu nhiều lớp đã triển khai một interface chung có hành vi cần thiết, có thể dùng **một type pattern** cho supertype đó:

```java
interface Printable {
    String display();
}

static String display(Object value) {
    return switch (value) {
        case Printable printable -> printable.display();
        case null, default -> "Not printable";
    };
}
```

Đây là ví dụ minh họa đặt trong một lớp; việc khai báo các lớp thực thi `Printable` tùy thuộc ứng dụng.

Một `case Printable printable` xử lý **mọi giá trị runtime** triển khai `Printable`. Nếu bạn chỉ muốn một vài subtype chứ không phải tất cả, cần guard hoặc chia nhánh cụ thể; không nên dùng supertype rộng chỉ để rút ngắn mã rồi vô tình nhận thêm những loại dữ liệu không mong muốn.

### Cách 3 — nhiều nhánh với `when` cho cùng một kiểu

```java
static String describe(Object value) {
    return switch (value) {
        case String text when text.isBlank() -> "Blank";
        case String text -> "Text: " + text;
        case null, default -> "Other";
    };
}
```

Đây là **hai pattern `String text` riêng biệt**, được phép dùng lại tên vì phạm vi của chúng là các nhánh khác nhau. Guard `when` của nhánh đầu được kiểm tra sau khi pattern khớp; nhánh thứ hai xử lý các chuỗi còn lại.

**Thứ tự quan trọng:** nhánh có guard cụ thể đứng trước nhánh tổng quát. Nếu đặt `case String text -> ...` lên trước `case String text when ... -> ...`, nhánh guard phía sau bị che phủ và có thể gây lỗi compile-time (*dominated case label*).

## 5. Chương trình Java 21 hoàn chỉnh: nhóm nhiều nhãn và tái sử dụng hành động

Lưu trong tệp **`MultiplePatternsInCase.java`**:

```java
public class MultiplePatternsInCase {
    record Ping() {}
    record Pong() {}

    static String grouped(Object value) {
        String result;

        switch (value) {
            case Ping():
            case Pong():
                result = "SIGNAL";
                break;
            case String text:
                result = "TEXT:" + text.toUpperCase();
                break;
            case Integer number:
                result = "INT:" + (number + 1);
                break;
            case null:
                result = "NULL";
                break;
            default:
                result = "OTHER";
        }
        return result;
    }

    static String shared(Object value) {
        return switch (value) {
            case String text -> handle(text);
            case Integer number -> handle(number);
            case null, default -> "OTHER";
        };
    }

    static String handle(Object value) {
        return "SHARED:" + value;
    }

    static String direction(String word) {
        return switch (word) {
            case "N", "NORTH" -> "UP";
            case "S", "SOUTH" -> "DOWN";
            case null, default -> "UNKNOWN";
        };
    }

    public static void main(String[] args) {
        Object[] inputs = {
            new Ping(), new Pong(), "java", 4, null, 3.5
        };

        for (Object input : inputs) {
            System.out.println(grouped(input));
        }

        System.out.println(shared("abc"));
        System.out.println(shared(12));
        System.out.println(shared(null));

        System.out.println(direction("N"));
        System.out.println(direction("SOUTH"));
        System.out.println(direction(null));
    }
}
```

Biên dịch với mức ngôn ngữ **Java 21**:

```bash
javac --release 21 MultiplePatternsInCase.java
java MultiplePatternsInCase
```

Stdout chính xác:

```text
SIGNAL
SIGNAL
TEXT:JAVA
INT:5
NULL
OTHER
SHARED:abc
SHARED:12
OTHER
UP
DOWN
UNKNOWN
```

Diễn giải kết quả:

- `Ping` và `Pong` khớp hai nhãn record pattern không khai báo biến rồi thực hiện **cùng nhóm lệnh** `result = "SIGNAL"`.
- `"java"` đi qua nhánh `String text`, gọi `toUpperCase()`, trả `TEXT:JAVA`.
- Số `4` được autoboxing thành `Integer` khi đưa vào `Object[]`, nhánh `Integer number` cộng 1 thành `INT:5`.
- `null` được xử lý trong `case null:`, còn `3.5` là `Double` nên vào `default`.
- `shared("abc")` và `shared(12)` gọi **cùng phương thức** `handle` từ hai nhánh pattern độc lập, trả `SHARED:abc` và `SHARED:12`.
- `direction("N")` và `direction("SOUTH")` minh họa việc nhóm **hằng** bằng dấu phẩy. `direction(null)` vào `case null, default`.

Toàn bộ phần này là cú pháp **Java 21 chính thức**, không cần `--enable-preview`.

## 6. Cú pháp nhiều pattern trong một nhãn `case`: các bản Java preview mới hơn

Các bản preview về primitive patterns và `switch` từ **Java 23 đến Java 26** bổ sung dạng:

```java
case PatternA, PatternB -> sharedAction;
```

Một cách dùng đơn giản là nhóm những record patterns **không khai báo biến**:

```java
case Ping(), Pong() -> "SIGNAL";
```

Trong ví dụ này, `Ping()` và `Pong()` là hai record patterns, mỗi pattern có cấu trúc record rỗng và **không gắn biến**. Nếu selector khớp một trong hai, cùng rule `->` được chọn. Đây là cú pháp gọn tương ứng với hai nhãn `case Ping(): case Pong():` ở chương trình Java 21.

### Ví dụ chạy riêng với JDK 24, bật preview

Tạo tệp **`MultiCasePreview24.java`**:

```java
public class MultiCasePreview24 {
    record Ping() {}
    record Pong() {}

    static String describe(Object value) {
        return switch (value) {
            case Ping(), Pong() -> "SIGNAL";
            case String text -> "TEXT:" + text;
            case null, default -> "OTHER";
        };
    }

    public static void main(String[] args) {
        System.out.println(describe(new Ping()));
        System.out.println(describe(new Pong()));
        System.out.println(describe("hi"));
        System.out.println(describe(null));
    }
}
```

Biên dịch/chạy bằng **JDK 24**, bật tính năng preview của chính phiên bản đó:

```bash
javac --enable-preview --release 24 MultiCasePreview24.java
java --enable-preview MultiCasePreview24
```

Stdout:

```text
SIGNAL
SIGNAL
TEXT:hi
OTHER
```

**Lưu ý:** Không dùng `javac --release 21` với ví dụ này. Trên một JDK khác, preview cần được bật theo **mức ngôn ngữ của chính JDK đó**; `--enable-preview` không mở khóa tùy ý các preview của phiên bản cũ. Tính năng này vẫn thuộc chuỗi preview qua Java 26, nên nên ưu tiên cú pháp ổn định của Java 21 khi dự án cần tương thích lâu dài.

### Tại sao pattern có biến vẫn không thể gộp bằng dấu phẩy?

Dù preview cho phép **nhiều pattern trong một nhãn**, ví dụ sau vẫn bị từ chối:

```java
// CỐ Ý SAI, kể cả khi bật preview:
return switch (value) {
    case String text, Integer number -> "Mixed";
    default -> "Other";
};
```

Nếu `String text` khớp thì `number` không được gắn; nếu `Integer number` khớp thì `text` không được gắn. Vì một rule chung phải có phạm vi biến nhất quán, quy tắc preview **không cho phép một danh sách nhiều case patterns khai báo pattern variables**, ngay cả khi thân nhánh không trực tiếp dùng chúng.

Tương tự, hai record patterns tách thành phần như `case Point(int x, int y), Pair(int a, int b) -> ...` cũng không hợp lệ vì mỗi pattern con khai báo biến. Đừng suy từ việc `case Ping(), Pong()` hợp lệ ra rằng mọi record pattern đều gộp được.

### Phân biệt `case null, default` với danh sách pattern

`case null, default -> ...` là **cặp nhãn đặc biệt** được Java 21 hỗ trợ ổn định; nó không có nghĩa là `null` là một pattern có thể đặt tùy ý trong danh sách. Cú pháp `case null, String text -> ...` không được phép, kể cả trong các phiên bản preview vừa nêu. Hãy xử lý `null` rõ ràng hoặc dùng cặp `null, default` khi hai trường hợp thật sự cần cùng hành động.

## 7. Giới hạn của `switch` khi nhiều điều kiện cùng có khả năng khớp

### Mỗi lượt chỉ chọn một nhánh phù hợp

Khi nhiều nhãn có thể khớp một giá trị, Java xét theo quy tắc so khớp của `switch` và thứ tự nhãn. **Không có chuyện chạy một nhánh cho từng pattern khớp**. Với rule `->`, không xảy ra fall-through sang rule sau.

Ví dụ minh họa:

```java
return switch (value) {
    case String s when s.isBlank() -> "Blank";
    case String s -> "Text";
    case null, default -> "Other";
};
```

Nếu `value` là chuỗi rỗng, nhánh `Blank` được chọn, không chạy tiếp `Text`. Nếu `value` là `"ok"`, guard sai nên nhánh `Text` được chọn.

### Phát hiện nhánh bị bao phủ (*dominance*)

Ví dụ **không hợp lệ**:

```java
return switch (value) {
    case CharSequence sequence -> "Sequence";
    case String text -> "Text"; // Bị nhánh trên bao phủ.
    case null, default -> "Other";
};
```

`String` là subtype của `CharSequence`, nên nhánh `String` không thể được chọn sau nhánh `CharSequence` không guard. Trình biên dịch từ chối nhánh bị bao phủ. Đưa nhánh cụ thể lên trước nhánh tổng quát, hoặc bỏ nhánh dư thừa nếu mục đích xử lý giống nhau.

### `switch` expression phải exhaustive

Với selector kiểu `Object`, chỉ liệt kê `String` và `Integer` sẽ không bao phủ các kiểu khác. Trong `switch` expression, cần bổ sung `default`, `case null, default` hoặc một tập nhãn đã được trình biên dịch chứng minh là đầy đủ, ví dụ trên sealed hierarchy phù hợp.

**Exhaustive về các kiểu không có nghĩa là tự động xử lý `null`.** Nếu có thể nhận `null`, chọn rõ `case null` hoặc `case null, default`. Đừng kỳ vọng nhánh `default` thông thường luôn bắt được selector `null` trong pattern switch.

## 8. Bảng tóm tắt quy tắc theo phiên bản

| Cách viết | Java 21 chuẩn | Java 24 khi bật preview | Ý nghĩa |
| --- | --- | --- | --- |
| `case "A", "B" -> ...` với selector `String` | Hợp lệ | Hợp lệ | Nhiều **hằng**, một rule |
| `case null, default -> ...` | Hợp lệ | Hợp lệ | Gộp `null` và nhánh dự phòng |
| `case Ping(): case Pong(): ... break;` | Hợp lệ | Hợp lệ | Hai **case labels**, một nhóm statement `:` |
| `case Ping(), Pong() -> ...` | Không hỗ trợ | Hợp lệ với preview | Hai **pattern** không khai báo biến trong cùng nhãn |
| `case String s, Integer i -> ...` | Không hỗ trợ | Lỗi biên dịch | Danh sách pattern có biến không được phép |
| `case String s -> common(s); case Integer i -> common(i);` | Hợp lệ | Hợp lệ | Hai nhánh pattern độc lập gọi chung một phương thức |
| `case null, String s -> ...` | Lỗi biên dịch | Lỗi biên dịch | Không phải tổ hợp nhãn cho phép |

Bảng trên giả định các kiểu và khai báo cần thiết tồn tại, selector tương thích, không có nhánh bị dominance, và thân `switch` đáp ứng các yêu cầu về tính bao phủ.

## 9. Lỗi thường gặp và cách sửa

**Lỗi 1 — nhầm nhóm hằng với nhóm pattern:** `case "A", "B"` có nhiều hằng nhưng không chứng minh `case String s, Integer i` hợp lệ. Hãy xem **mỗi phần trong nhãn là hằng hay pattern** và có khai báo biến hay không.

**Lỗi 2 — dùng dấu phẩy với hai record pattern ở dự án Java 21:** `case Ping(), Pong() ->` thuộc cú pháp preview mới hơn. Dùng nhãn `:` liên tiếp với `break`, hoặc tách thành hai rule `->` gọi một phương thức chung.

**Lỗi 3 — gộp case có biến pattern vào một nhóm statement:** nếu một biến chỉ được khởi tạo khi đúng một nhãn nhất định, nhóm chung có thể được truy cập từ nhãn khác. Cách an toàn là **mỗi nhánh gắn biến riêng và gọi chung hàm xử lý**.

**Lỗi 4 — quên `break` trong nhóm `case:`:** khi không có `break`, luồng có thể tiếp tục sang nhóm sau. Với case pattern có biến, compiler còn có thêm quy tắc chặn fall-through không an toàn. Với rule `->`, Java không fall through.

**Lỗi 5 — đặt nhánh tổng quát trước nhánh cụ thể:** `case CharSequence c` trước `case String s` che phủ nhánh `String`. Cần sắp xếp nhánh cụ thể trước, hoặc dùng guard đúng mục tiêu.

**Lỗi 6 — bỏ qua `null` và exhaustiveness:** một `switch` expression trên `Object` cần bao phủ kiểu khác và nên xử lý `null` rõ ràng; `default` không có nghĩa mọi kiểu dữ liệu kể cả `null` đều được xử lý như mong đợi.

**Lỗi 7 — nhầm preview với tính năng chuẩn:** việc mã chạy trên một JDK mới có bật preview không chứng minh nó sẽ biên dịch dưới `--release 21`. Luôn kiểm tra cấu hình nguồn của dự án và các cờ compile/runtime.

## 10. Tự kiểm tra

**Bài 1.** Trong Java 21, biểu thức `switch` có `case "GET", "HEAD" -> "READ";` trên selector kiểu `String` hợp lệ không?

**Đáp án:** Có. Đây là nhiều hằng `String` trong cùng một nhãn, không phải nhiều pattern. Nhánh `READ` được chọn nếu selector bằng một trong hai hằng.

**Bài 2.** Trong Java 21, làm thế nào để `Ping()` và `Pong()` cùng in `"SIGNAL"` mà không khai báo biến?

**Đáp án:** Dùng hai nhãn `case Ping(): case Pong():` gắn chung nhóm statement có `System.out.println("SIGNAL"); break;`. Đây là cú pháp ổn định trong Java 21.

**Bài 3.** Trong JDK 24 có bật preview, `case Ping(), Pong() -> ...` có được dùng không?

**Đáp án:** Có, nếu hai record patterns không khai báo biến, selector tương thích và không bị nhánh trước che phủ. Phải dùng mức nguồn và cờ preview của JDK 24; không viết cú pháp này rồi biên dịch như Java 21 chuẩn.

**Bài 4.** Vì sao `case String s, Integer i -> ...` không hợp lệ, dù cả hai nhánh đều muốn gọi một hàm chung?

**Đáp án:** Một nhánh không thể giả định cùng lúc có cả `s` và `i`. Các phiên bản preview có cú pháp danh sách nhiều pattern vẫn cấm việc khai báo pattern variables trong danh sách. Tách thành `case String s -> common(s);` và `case Integer i -> common(i);`.

**Ghi nhớ:** *Nhiều trường hợp chung một hành động* là mục tiêu; cách diễn đạt tùy vào **hằng hay pattern**, **có khai báo biến hay không**, và **phiên bản Java**. Với Java 21, ưu tiên các rule pattern riêng gọi phương thức chung hoặc nhóm các nhãn không gắn biến trong switch statement. Với Java preview mới hơn, danh sách nhiều pattern bằng dấu phẩy giúp ngắn gọn hơn khi **không có pattern variable nào cần được gắn**.

## Tài liệu tham khảo chính thức

- [Oracle Java 21 — Pattern Matching for switch](https://docs.oracle.com/en/java/javase/21/language/pattern-matching-switch.html).
- [Java Language Specification 21 — §14.11, Switch Statement và switch labels](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.11).
- [OpenJDK JEP 441 — Pattern Matching for switch](https://openjdk.org/jeps/441).
- [OpenJDK JEP 488 — Primitive Types in Patterns, instanceof, and switch (Second Preview, Java 24)](https://openjdk.org/jeps/488).
- [Oracle Java 26 — JEP 530 Fourth Preview specification](https://docs.oracle.com/en/java/javase/26/docs/specs/primitive-types-in-patterns-instanceof-switch-jls.html).