# Kết hợp kết quả số và các phép chuyển kiểu trong `switch` expression

## 1. Mục tiêu: biết kiểu kết quả được xác định như thế nào

Từ Java 14, `switch` expression là cú pháp ổn định: mỗi nhánh được chọn phải tạo **một giá trị** (dùng `case ... -> biểuThức` hoặc `yield biểuThức` trong khối). Kết quả có thể thuộc kiểu `int`, `long`, `double`, `Integer`, `Number` hoặc một kiểu tham chiếu phù hợp. **Kiểu selector** trong `switch (selector)` và **kiểu kết quả** của `switch` là hai vấn đề khác nhau.

Ví dụ: selector ở đây là `int`, nhưng kết quả được yêu cầu là `double`:

~~~java
double price = switch (choice) {
    case 0 -> 10;     // int được mở rộng thành double
    case 1 -> 12.5;   // double
    default -> 0.0;   // double
};
~~~

Đây là đoạn mã minh họa đặt trong phương thức có biến `int choice`, không phải chương trình độc lập. Java xét **mọi biểu thức kết quả** để kiểm tra kiểu ngay lúc biên dịch; tại thời gian chạy, Java **chỉ đánh giá nhánh được chọn**. Cần phân biệt hai cơ chế:

- **Poly expression (biểu thức chịu ảnh hưởng của kiểu đích):** `switch` xuất hiện trong ngữ cảnh gán hoặc truyền đối số có kiểu đích, ví dụ `double total = switch (...) { ... };` hay `acceptNumber(switch (...) { ... });`. Kiểu đích được truyền vào từng biểu thức kết quả; từng nhánh phải tương thích với kiểu đó.
- **Standalone expression (biểu thức tự suy ra kiểu):** không có ngữ cảnh đích phù hợp, điển hình là `var total = switch (...) { ... };`. Java suy ra **một kiểu chung** từ các nhánh theo quy tắc ngôn ngữ. `var` không phải một kiểu đích đã biết để ép các nhánh.

Vì vậy, cùng một dãy nhánh có thể dẫn đến kiểu và hành vi boxing/unboxing **khác nhau** tùy chỗ sử dụng `switch`. Những quy tắc này được quy định trong Java Language Specification hiện hành (§15.28 và §5.6), không phải cơ chế cũ đã ngừng hỗ trợ.

## 2. Trường hợp có kiểu đích: kiểm tra chuyển đổi riêng từng nhánh

Khi viết `T result = switch (...) { ... };` với `T` là kiểu cụ thể, `switch` là poly expression có kiểu đích `T`. Mỗi biểu thức `case ->` và mỗi biểu thức `yield` được xét trong ngữ cảnh tương thích với `T`.

Các nhóm chuyển đổi quan trọng:

| Kiểu đích và nhánh | Kết luận | Cơ chế |
| --- | --- | --- |
| `double` ← nhánh `int` | Hợp lệ | Widening primitive `int -> double` |
| `long` ← nhánh `int` | Hợp lệ | Widening primitive `int -> long` |
| `byte` ← nhánh hằng `int 100` | Hợp lệ | Narrowing *hằng số nguyên nằm trong miền biểu diễn* |
| `byte` ← nhánh hằng `int 128` | Lỗi biên dịch | `128` vượt khoảng `byte` (−128…127) |
| `int` ← nhánh `double 2.5` | Lỗi biên dịch | Không tự động narrowing `double -> int` |
| `Number` ← nhánh `int 7` | Hợp lệ | Boxing `int -> Integer`, rồi widening reference đến `Number` |
| `Number` ← nhánh `double 2.5` | Hợp lệ | Boxing `double -> Double`, rồi widening reference đến `Number` |
| `Long` ← nhánh `int 1` | Lỗi biên dịch | Không có chuyển đổi gán ngầm `int -> long -> Long` |
| `Long` ← nhánh `long 1L` | Hợp lệ | Boxing `long -> Long` |

**Hằng số nguyên cần nằm trong khoảng:** đây là ưu đãi cho *biểu thức hằng kiểu nguyên* phù hợp với kiểu đích `byte`, `short` hoặc `char`; không phải Java luôn cho phép thu hẹp kiểu. Ví dụ:

~~~java
byte level = switch (choice) {
    case 0 -> 10;
    default -> 100;
};
~~~

Hợp lệ vì cả hai biểu thức kết quả `10` và `100` đều là hằng `int` nằm trong khoảng `byte`. Nhưng thay `100` bằng `128` sẽ lỗi biên dịch. Nếu nhánh trả **biến `int`** (dù tại thời gian chạy biến đang chứa `10`), không có quy tắc tự thu hẹp đặc biệt cho biến đó; dùng kiểu đích lớn hơn hoặc ép kiểu tường minh có kiểm tra phạm vi.

Với nhánh `yield` trong một khối, quy tắc tương thích kiểu đích **giống hệt** nhánh mũi tên trực tiếp:

~~~java
long count = switch (choice) {
    case 0 -> {
        int initial = 12;
        yield initial; // int -> long theo kiểu đích long
    }
    default -> 100L;
};
~~~

Hai đoạn này là ví dụ trong phương thức có `int choice`. Việc dùng `yield` không tạo ra “một kiểu riêng” và không bỏ qua kiểm tra kiểu.

## 3. Trường hợp `var` / standalone: Java tìm kiểu chung từ các kết quả

Với `var value = switch (choice) { ... };`, `switch` là standalone expression. Đặc tả xét theo thứ tự:

1. Nếu **tất cả biểu thức kết quả cùng kiểu**, dùng chính kiểu đó. Ví dụ hai nhánh đều `Integer` thì kiểu là `Integer`, **không tự unbox**.
2. Nếu các kết quả khác kiểu nhưng đều thuộc `boolean`/`Boolean`, kết quả là `boolean` (unbox nhánh `Boolean` khi được chọn). Đây là một trường hợp riêng, **không phải phép nâng kiểu số**.
3. Nếu các kết quả khác kiểu và đều có thể chuyển về kiểu số (bao gồm wrapper số), áp dụng **general numeric promotion** (§5.6). Nhánh wrapper có thể cần unboxing; kiểu chung có thể là `double`, `float`, `long`, `int`, hoặc trong một số trường hợp hằng số là `byte`, `short`, `char`.
4. Nếu không thuộc các trường hợp trên, các nhánh kiểu nguyên thủy được boxing khi cần, sau đó Java tìm kiểu tham chiếu chung theo *least upper bound* (LUB). Ví dụ trộn chuỗi với một số không được suy ra thành `double` chỉ vì có nhánh số.

**Quy tắc nâng kiểu số tổng quát** cho standalone `switch` có các kết quả số:

- Có `double` ⇒ kiểu chung `double`.
- Nếu không có `double` nhưng có `float` ⇒ `float`.
- Nếu không có hai kiểu trên nhưng có `long` ⇒ `long`.
- Với những kiểu số nhỏ còn lại, thông thường là `int`, **nhưng có ngoại lệ bảo toàn `byte`/`short`/`char`** theo quy tắc numeric choice: chẳng hạn một nhánh `byte` và nhánh kia là hằng `int` nằm vừa trong `byte` thì kiểu chung có thể vẫn là `byte`; `byte` kết hợp `short` có thể thành `short`. Nếu có `int` **không phải biểu thức hằng** thì quy tắc cho các kiểu nhỏ này thường dẫn đến `int`.

Các ví dụ sau đều là biểu thức standalone khi khai báo bằng `var`:

| Biểu thức kết quả ở các nhánh | Kiểu suy ra | Lý do |
| --- | --- | --- |
| `int 7` và `double 2.5` | `double` | Có nhánh `double` |
| `short 2` và `long 3L` | `long` | Có nhánh `long` |
| `byte 5` và hằng `int 6` | `byte` | `6` nằm trong miền `byte` |
| `byte 5` và hằng `int 200` | `int` | `200` không nằm trong miền `byte` |
| `byte 5` và `short 6` | `short` | Numeric choice giữ `short` khi phù hợp |
| `Integer` và `Long` | `long` | Wrapper khác kiểu; unboxing rồi nâng kiểu số |
| `Integer` và `int` | `int` | Khác kiểu; nhánh `Integer` cần unboxing |
| `Integer` và `Integer` | `Integer` | Các nhánh **cùng kiểu**; không áp dụng quy tắc nâng kiểu số |

Các số ghi trong bảng như `byte 5` nghĩa là **biểu thức có kiểu `byte`**, chẳng hạn `(byte) 5`; một literal nguyên `5` không có hậu tố mặc định là `int`. Với `short 6`, dùng `(short) 6`. Đây là khác biệt quan trọng khi tự kiểm tra kiểu.

Không nên thuộc lòng quy tắc sai “`byte` và `short` lúc nào cũng thành `int`”: phép toán số học như `byte + short` có quy tắc khác một số tình huống **numeric choice** giữa các nhánh `switch`.

## 4. Chương trình Java 14+: kiểu đích, `var`, boxing và unboxing

Tạo tệp `SwitchNumericTypes.java`:

~~~java
public class SwitchNumericTypes {
    static Number asNumber(int selection) {
        return switch (selection) {
            case 0 -> 7;
            case 1 -> 2.5;
            default -> 9L;
        };
    }

    static void acceptNumber(Number value) {
        System.out.println("invoke=" + value.getClass().getSimpleName());
    }

    public static void main(String[] args) {
        var sameByte = switch (0) {
            case 0 -> (byte) 5;
            default -> (byte) 6;
        };
        byte a = sameByte;

        var byteAndConstant = switch (0) {
            case 0 -> (byte) 5;
            default -> 6;
        };
        byte b = byteAndConstant;

        var byteAndShort = switch (1) {
            case 0 -> (byte) 5;
            default -> (short) 6;
        };
        short s = byteAndShort;

        var toLong = switch (0) {
            case 0 -> (short) 2;
            default -> 3L;
        };
        long l = toLong;

        var toDouble = switch (0) {
            case 0 -> 7;
            default -> 2.5;
        };
        double d = toDouble;

        byte directNarrowing = switch (0) {
            case 0 -> 10;
            default -> 100;
        };

        System.out.println("byte=" + a + "," + b
            + ";short=" + s + ";long=" + l
            + ";double=" + d + ";byteTarget=" + directNarrowing);

        Number asNum = asNumber(1);
        System.out.println("target=" + asNum.getClass().getSimpleName()
            + ":" + asNum);

        acceptNumber(switch (2) {
            case 0 -> 7;
            default -> 2.5;
        });

        Integer nullable = null;
        Integer nullableResult = switch (1) {
            case 0 -> 5;
            default -> nullable;
        };
        System.out.println("boxedTarget=" + nullableResult);

        var allInteger = switch (1) {
            case 0 -> Integer.valueOf(5);
            default -> nullable;
        };
        Integer sureIntegerType = allInteger;
        System.out.println("sameType=" + sureIntegerType);

        try {
            var mixed = switch (1) {
                case 0 -> 5;
                default -> nullable;
            };
            System.out.println(mixed);
        } catch (NullPointerException ex) {
            System.out.println("standaloneUnboxing=NPE");
        }

        int truncated = switch (1) {
            case 0 -> 5;
            default -> (int) 2.9;
        };
        System.out.println("explicitCast=" + truncated);
    }
}
~~~

Biên dịch và chạy với JDK hỗ trợ Java 14 trở lên; `--release 14` kiểm tra chính xác rằng mã không đòi hỏi tính năng mới hơn:

~~~bash
javac --release 14 -encoding UTF-8 SwitchNumericTypes.java
java SwitchNumericTypes
~~~

Stdout chính xác:

~~~text
byte=5,5;short=6;long=2;double=7.0;byteTarget=10
target=Double:2.5
invoke=Double
boxedTarget=null
sameType=null
standaloneUnboxing=NPE
explicitCast=2
~~~

Giải thích những điểm không hiển nhiên:

- `sameByte` là `byte` vì cả hai nhánh cùng kiểu `byte`; `byteAndConstant` cũng là `byte` vì hằng `6` nằm trong miền `byte`. `byteAndShort` có kiểu `short`, còn `toLong` thành `long` và `toDouble` thành `double`.
- `directNarrowing` nhận hai hằng phù hợp với kiểu đích `byte`. Điều đó **không biến mọi biểu thức `int` thành `byte`**.
- `asNumber(1)` là một `switch` poly vì phương thức khai báo kết quả `Number`. Nhánh `double 2.5` được boxing thành `Double`; `asNumber(0)` tương tự trả `Integer`. Kiểu tĩnh mà bên gọi nhìn thấy là `Number`.
- Đối số trong `acceptNumber(switch ...)` cũng có kiểu đích `Number` từ tham số phương thức, nên nhánh `2.5` trở thành đối tượng `Double`.
- `Integer nullableResult = switch (...)` dùng đích `Integer`: nhánh `5` được boxing, còn nhánh `nullable` có thể trả nguyên `null`. Phép gán này **không cần unbox**, nên in `null`.
- `var allInteger = switch (...)` có hai nhánh cùng kiểu `Integer`, nên kết quả suy ra là `Integer` và có thể `null`.
- Nhưng `var mixed = switch (...)` kết hợp `int 5` với `Integer nullable` ⇒ standalone có kiểu `int`. Khi chọn nhánh `nullable` mang `null`, Java phải unbox và ném NPE. Như vậy, **thay `Integer` bằng `var` có thể làm thay đổi hành vi runtime**.
- `(int) 2.9` là một cast tường minh và cho kết quả `2` (cắt phần lẻ theo hướng về 0), không phải làm tròn `3`.

Chỉ một nhánh được chọn có mã chạy, nhưng mọi nhánh vẫn phải **vượt qua kiểm tra kiểu tại thời gian biên dịch**.

## 5. Ba lỗi biên dịch do chuyển kiểu không hợp lệ

Các dòng sau là **minh họa lỗi biên dịch**; không ghép chúng vào chương trình chạy thành công ở trên:

~~~java
// 1. Hằng số vượt miền byte:
byte a = switch (choice) {
    case 0 -> 128;   // compile error: int -> byte có thể mất dữ liệu
    default -> 1;
};

// 2. Không tự động đổi double thành int:
int b = switch (choice) {
    case 0 -> 1;
    default -> 2.5;  // compile error: double -> int
};

// 3. Không tự động widen rồi box thành Long:
Long c = switch (choice) {
    case 0 -> 1;     // compile error: int không chuyển ngầm thành Long
    default -> 2L;
};
~~~

Trong đoạn minh họa, `choice` là biến `int` đã khai báo bên ngoài. Cả ba trường hợp đều bị `javac --release 14` từ chối. Hướng xử lý đúng:

- Nếu kết quả phải chứa `128`, chọn `short`/`int` thay vì `byte`; chỉ cast `(byte) 128` khi **thật sự** muốn hành vi tràn giá trị sang `-128`.
- Nếu cần giữ phần thập phân, chọn `double`; nếu cần số nguyên, làm rõ quy tắc chuyển đổi (ví dụ `(int) 2.5` → `2`) và chấp nhận khả năng mất thông tin.
- Nếu đích là `Long`, đổi `1` thành `1L` để nhánh có kiểu `long` rồi boxing thành `Long`. Không suy diễn rằng mọi chuỗi “widening rồi boxing” đều được phép trong assignment context. Nếu đích chỉ cần số nguyên, `long` primitive có thể nhận cả `1` và `2L` qua widening.

## 6. Chuyển kiểu đúng nhưng vẫn có thể mất dữ liệu

Biên dịch thành công không bảo đảm giá trị số luôn được bảo toàn. Đặc biệt, **kiểu đích không thay đổi cách biểu thức bên trong nhánh đã tính ra kết quả**. Ví dụ độc lập sau dùng class `SwitchNumericEdges.java`:

~~~java
public class SwitchNumericEdges {
    static Number asNumber(int selection) {
        return switch (selection) {
            case 0 -> 7;
            default -> 2.5;
        };
    }

    public static void main(String[] args) {
        var biggerThanByte = switch (0) {
            case 0 -> (byte) 3;
            default -> 200;
        };
        int provenInt = biggerThanByte;

        var mixedBoxes = switch (0) {
            case 0 -> Integer.valueOf(9);
            default -> Long.valueOf(10);
        };
        long provenLong = mixedBoxes;

        long wrong = switch (0) {
            case 0 -> Integer.MAX_VALUE + 1;
            default -> 0L;
        };
        long correct = switch (0) {
            case 0 -> (long) Integer.MAX_VALUE + 1;
            default -> 0L;
        };

        float imprecise = switch (0) {
            case 0 -> 16_777_217;
            default -> 1.0f;
        };

        System.out.println("large=" + provenInt + ";boxesLong=" + provenLong);
        System.out.println("Number0=" + asNumber(0).getClass().getSimpleName()
            + ";Number1=" + asNumber(1).getClass().getSimpleName());
        System.out.println("overflow=" + wrong + ";correct=" + correct);
        System.out.println("float=" + imprecise);
    }
}
~~~

~~~bash
javac --release 14 -encoding UTF-8 SwitchNumericEdges.java
java SwitchNumericEdges
~~~

Stdout chính xác:

~~~text
large=3;boxesLong=9
Number0=Integer;Number1=Double
overflow=-2147483648;correct=2147483648
float=1.6777216E7
~~~

Diễn giải:

1. `biggerThanByte` là `int` dù chọn nhánh `(byte) 3`: nhánh còn lại `200` không thể nằm trong `byte`. Quy tắc chọn kiểu xét **tất cả nhánh ở compile time**, không chỉ nhánh chạy.
2. `mixedBoxes` trộn `Integer` và `Long` nên standalone dùng unboxing và numeric promotion để thành `long`. Ở lượt này chỉ `Integer.valueOf(9)` được đánh giá và chuyển thành `9L`.
3. Với `wrong`, `Integer.MAX_VALUE + 1` đã thực hiện phép cộng theo `int` và tràn thành `-2147483648` **trước khi chuyển sang `long`**. Với `correct`, cast toán hạng đầu thành `long` trước phép cộng nên kết quả là `2147483648`. Kiểu `long` của biến không sửa được phép cộng `int` đã tràn.
4. `16_777_217` không thể biểu diễn chính xác bằng `float` (24 bit độ chính xác ở phần định trị). Kết quả gần nhất hiển thị `1.6777216E7`, tức `16_777_216`. Mở rộng từ một kiểu nguyên sang số thực có thể hợp lệ nhưng vẫn mất độ chính xác; điều này cũng đáng chú ý với `long -> double` ở giá trị rất lớn.

## 7. Quy trình phân tích và thiết kế

Khi đọc hoặc viết một `switch` có kết quả số, hãy trả lời lần lượt:

1. **Biểu thức kết quả nào tồn tại?** Liệt kê tất cả nhánh `case -> ...` và `yield ...` (kể cả `default`); ghi kiểu thật của từng biểu thức, phân biệt `5` là `int`, `5L` là `long`, `5.0` là `double` và `5.0f` là `float`.
2. **Có kiểu đích không?** `Number n = switch ...` khác `var n = switch ...`. Khi có kiểu đích, kiểm tra chuyển đổi **từng nhánh** đến kiểu đích. Khi standalone, áp dụng thứ tự cùng kiểu → boolean → general numeric promotion → LUB tham chiếu.
3. **Có wrapper không?** Chú ý `Integer`, `Long` có thể `null`. Hai nhánh `Integer` giữ kiểu `Integer`, còn trộn `Integer` và `int` khi standalone có thể buộc unboxing ở nhánh được chọn.
4. **Có narrowing hoặc boxing không hợp lệ không?** Kiểm tra giá trị hằng nằm trong miền `byte`/`short`/`char`, tránh tự động `double -> int` hay `int -> Long`.
5. **Phép tính trong nhánh dùng kiểu nào?** Đổi kiểu **toán hạng trước phép toán** khi cần chống tràn, ví dụ `(long) a + b`; không chờ đến lúc gán kết quả `switch` vào `long`.
6. **Mất độ chính xác có chấp nhận được không?** Tránh dùng số thực dấu phẩy động cho phép tính yêu cầu số thập phân chính xác (ví dụ số tiền). Khi nghiệp vụ cần độ chính xác thập phân, dùng `BigDecimal` với quy tắc khởi tạo/làm tròn rõ ràng; nếu chỉ cần độ lớn hoặc đo lường, `double` có thể phù hợp.

Tách **kiểu mong muốn của kết quả** khỏi **cách từng nhánh tính ra giá trị** giúp tránh ba lớp lỗi khác nhau: không biên dịch được, NPE do unboxing, và kết quả sai âm thầm vì tràn số/mất độ chính xác.

## Đối chiếu đặc tả Java hiện hành

- Java Language Specification 26, §15.28 *switch Expressions* (poly/standalone và quy tắc kết quả): https://docs.oracle.com/javase/specs/jls/se26/html/jls-15.html#jls-15.28
- Java Language Specification 26, §5.6 *Numeric Contexts* (general numeric promotion, numeric choice và ngoại lệ cho hằng số): https://docs.oracle.com/javase/specs/jls/se26/html/jls-5.html#jls-5.6
- Java Language Specification 26, §5.2 *Assignment Contexts* (widening, boxing/unboxing, narrowing hằng số): https://docs.oracle.com/javase/specs/jls/se26/html/jls-5.html#jls-5.2
- Java Language Specification 26, §5.1.2–§5.1.3 (widening/narrowing số): https://docs.oracle.com/javase/specs/jls/se26/html/jls-5.html