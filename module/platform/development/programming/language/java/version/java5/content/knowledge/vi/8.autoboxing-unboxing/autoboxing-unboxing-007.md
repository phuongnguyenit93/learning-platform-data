# Phối hợp boxing, unboxing và mở rộng kiểu nguyên thủy

## 1. Khái niệm: các phép chuyển đổi khác nhau

Xét ba loại chuyển đổi:

| Loại | Ví dụ | Điều thay đổi |
| --- | --- | --- |
| Boxing | `int -> Integer` | Giá trị nguyên thủy đi qua lớp bao tương ứng |
| Unboxing | `Integer -> int` | Lấy giá trị nguyên thủy từ lớp bao |
| Mở rộng kiểu nguyên thủy | `int -> long` | Giá trị được biểu diễn qua một kiểu nguyên thủy rộng hơn được ngôn ngữ cho phép |

Còn một phép khác cần phân biệt: **mở rộng kiểu tham chiếu**, chẳng hạn `Integer -> Number` hoặc `Integer -> Object`. Phép này dùng một đối tượng qua kiểu cha, không đổi lớp thực tế của đối tượng.

Java cho phép một số phép kết hợp trong những ngữ cảnh cụ thể. Nó không tự tìm mọi đường đi có thể tưởng tượng để biến giá trị sang kiểu đích.

```java
// Minh họa trong một phương thức.
int primitive = 7;
Integer boxed = primitive;
long widened = boxed;
```

Câu lệnh cuối kết hợp `Integer -> int -> long`: unboxing trước, rồi mở rộng nguyên thủy.

Ngược lại, `Long value = primitive;` không tự thực hiện `int -> long -> Long` trong một phép gán như vậy.

Các quy tắc trong bài vẫn áp dụng trong Java hiện đại. Chương trình thực hành dùng Java 17 trở lên.

## 2. Vì sao cần theo dõi cả kiểu và ngữ cảnh?

Những câu lệnh nhìn gần giống nhau có thể có kết quả biên dịch khác nhau:

```java
// Minh họa trong một phương thức.
long a = 1;
Integer b = 1;
Number c = 1;
```

Cả ba hợp lệ nhưng đi qua các bước khác nhau:

- `a`: mở rộng `int -> long`.
- `b`: boxing `int -> Integer`.
- `c`: boxing `int -> Integer`, rồi mở rộng tham chiếu `Integer -> Number`.

Nếu thay dòng cuối bằng `Long c = 1;`, nó không còn hợp lệ. `Long` không phải kiểu cha của `Integer`; đây không phải mở rộng tham chiếu.

Để phân tích một câu lệnh:

1. Xác định kiểu của biểu thức nguồn.
2. Xác định kiểu mà vị trí nhận yêu cầu.
3. Phân biệt chuyển đổi giá trị nguyên thủy với chuyển đổi cách nhìn tham chiếu.
4. Xét chuỗi chuyển đổi được phép trong phép gán, lời gọi hoặc biểu thức đang dùng.

## 3. Mở rộng kiểu nguyên thủy không phải quan hệ kế thừa lớp bao

Các hướng mở rộng số nguyên thủy thông dụng:

| Kiểu nguồn | Có thể mở rộng sang |
| --- | --- |
| `byte` | `short`, `int`, `long`, `float`, `double` |
| `short` | `int`, `long`, `float`, `double` |
| `char` | `int`, `long`, `float`, `double` |
| `int` | `long`, `float`, `double` |
| `long` | `float`, `double` |
| `float` | `double` |

`boolean` không tham gia các chuyển đổi số này. `byte -> char` hoặc `char -> short` cũng không phải mở rộng ngầm định chỉ vì cùng có liên quan đến các giá trị nhỏ.

Với lớp bao, không có chuỗi kế thừa `Integer -> Long -> Double`. Các lớp này biểu diễn những kiểu khác nhau; việc cùng liên quan đến `Number` không cho phép gán tham chiếu tùy ý giữa chúng.

Đây là lý do “số nguyên có thể mở rộng sang long” không kéo theo “Integer có thể dùng trực tiếp ở mọi nơi cần Long”.

## 4. Boxing rồi mở rộng tham chiếu

Java cho phép:

```java
// Minh họa trong một phương thức.
int value = 7;

Number number = value;
Object object = value;
```

Luồng chuyển đổi:

```text
int --boxing--> Integer --mở rộng tham chiếu--> Number
int --boxing--> Integer --mở rộng tham chiếu--> Object
```

Trong cả hai trường hợp, lớp bao thực tế là `Integer`. Một biến kiểu `Number` không làm Java lựa chọn ngẫu nhiên `Long` hoặc `Double` để boxing một `int`.

Ngược lại:

```java
// Minh họa lỗi; không biên dịch.
Long value = 7;
```

Boxing trực tiếp một `int` cho ra kiểu `Integer`; nó không tương thích với kiểu tham chiếu `Long`.

Nếu giá trị cần được boxing thành `Long`, tạo một biểu thức nguyên thủy kiểu `long` trước:

```java
// Minh họa trong một phương thức.
Long first = 7L;

int value = 7;
Long second = (long) value;
```

`7L` đã có kiểu `long`. Ở dòng cuối, biểu thức ép kiểu tạo kết quả `long`; phép gán bên ngoài mới boxing kết quả đó thành `Long`.

## 5. Unboxing rồi mở rộng kiểu nguyên thủy

Đây là một chuỗi thường gặp và hợp lệ:

```java
// Minh họa trong một phương thức.
Integer boxed = 7;

long asLong = boxed;
double asDouble = boxed;
```

Luồng tương ứng:

```text
Integer --unboxing--> int --mở rộng nguyên thủy--> long
Integer --unboxing--> int --mở rộng nguyên thủy--> double
```

Unboxing lấy đúng kiểu nguyên thủy gắn với lớp bao trước. `Integer` được unboxing thành `int`, không phải trực tiếp “unboxing thành Long”.

Các ví dụ khác:

```java
// Minh họa trong một phương thức.
Byte small = Byte.valueOf((byte) 1);
int number = small;

Character letter = Character.valueOf('A');
int code = letter;
```

`Byte -> byte -> int` và `Character -> char -> int` đều phù hợp với các hướng mở rộng được phép.

Chiều thu hẹp không tự được thêm vào chuỗi:

```java
// Minh họa lỗi; không biên dịch.
Integer boxed = 7;
short narrowed = boxed;
```

Sau unboxing, `int -> short` là thu hẹp, không phải mở rộng. Nếu thuật toán thật sự cần thu hẹp, phải viết và kiểm tra chính sách về phạm vi/mất dữ liệu rõ ràng; không dùng một phép ép kiểu chỉ để làm lỗi biến mất.

## 6. Không tự thêm bước boxing lần nữa vào cùng phép gán

Câu lệnh sau không hợp lệ:

```java
// Minh họa lỗi; không biên dịch.
Integer source = 7;
Long target = source;
```

Không có chuyển đổi tham chiếu `Integer -> Long`, và phép gán này cũng không tự nối chuỗi:

```text
Integer -> int -> long -> Long
```

Muốn có giá trị `Long`, có thể viết rõ ranh giới giữa các bước:

```java
// Minh họa trong một phương thức.
Integer source = 7;

long widened = source;  // Unboxing rồi mở rộng nguyên thủy.
Long target = widened;  // Boxing một biểu thức đã có kiểu long.
```

Hoặc dùng một biểu thức tạo giá trị `long` trước bước gán:

```java
// Minh họa trong một phương thức có source kiểu Integer.
Long target = (long) source;
```

Đây không phải phép ép tham chiếu biến đối tượng `Integer` thành đối tượng `Long`. Biểu thức ép kiểu xử lý giá trị nguyên thủy, rồi kết quả được boxing ở phép gán bên ngoài.

Một phương thức chuyển đổi số như `source.longValue()` cũng tạo một kết quả `long` tường minh trước khi boxing nếu gán cho `Long`. Việc này vẫn cần `source` khác `null`.

## 7. Biểu thức có thể tạo kiểu nguyên thủy mới trước khi boxing

Cần phân biệt “chuỗi ngầm định bị cấm trong một ngữ cảnh” với một biểu thức có các bước tính toán riêng.

Ví dụ:

```java
// Minh họa trong một phương thức.
Integer source = 7;
Long result = source + 0L;
```

Đoạn này hợp lệ:

1. Phép cộng lấy giá trị nguyên thủy từ `source`.
2. Toán hạng `0L` có kiểu `long`; phép tính số áp dụng quy tắc thăng hạng thích hợp và có kết quả `long`.
3. Phép gán boxing kết quả `long` thành `Long`.

Điều đó không khiến `Long result = source;` trở nên hợp lệ. Ở hai câu lệnh, biểu thức nguồn của phép gán không có cùng kiểu.

Không khuyến khích cộng `0L` chỉ để giấu ý định chuyển kiểu. Biến trung gian có tên hoặc bước chuyển đổi tường minh thường dễ đọc hơn. Ví dụ này nhằm làm rõ các ranh giới ngữ cảnh.

Tương tự, cộng hai giá trị `Byte` hoặc `Short` không có nghĩa kết quả tự giữ kiểu nhỏ ấy. Phép toán số có quy tắc thăng hạng riêng; luôn xác định kiểu kết quả biểu thức trước khi xét bước gán sang lớp bao.

## 8. Lời gọi phương thức và lựa chọn overload

Một tham số nguyên thủy `long` có thể nhận một `Integer` bằng unboxing rồi mở rộng:

```java
// Phương thức minh họa, đặt bên trong một lớp.
static long acceptLongPrimitive(long value) {
    return value;
}
```

```java
// Minh họa trong một phương thức.
Integer boxed = 7;
long result = acceptLongPrimitive(boxed);
```

Nhưng một tham số lớp bao `Long` không tự nhận một `Integer` bằng chuỗi unboxing–mở rộng–boxing.

Khi có overload:

```java
// Các phương thức minh họa trong cùng một lớp.
static String choose(long value) {
    return "long";
}

static String choose(Integer value) {
    return "Integer";
}
```

Kết quả:

| Lời gọi | Overload được chọn trong ví dụ |
| --- | --- |
| `choose(1)` | `choose(long)` |
| `choose(Integer.valueOf(1))` | `choose(Integer)` |

Với đối số `int`, mở rộng sang `long` đã làm một ứng viên áp dụng ở giai đoạn chưa cần boxing. Java không tiếp tục coi boxing sang `Integer` là một cách tốt hơn để thay thế lựa chọn của giai đoạn ấy.

Với đối số đã có kiểu `Integer`, overload `Integer` nhận đúng kiểu mà không cần unboxing; chuyển sang `long` cần unboxing rồi mở rộng.

Đây là cách phân tích theo giai đoạn của overload, không phải một luật “mọi chuyển đổi nguyên thủy luôn thắng mọi lớp bao” trong mọi nhóm phương thức.

### Ngữ cảnh gán có ngoại lệ hằng số riêng

`Byte b = 1;` có thể hợp lệ vì phép gán cho phép thu hẹp một hằng số nguyên biểu diễn được rồi boxing trong trường hợp quy định. Đó không phải mở rộng nguyên thủy và không có nghĩa mọi lời gọi nhận `Byte` đều nhận literal `int` như vậy.

Đừng dùng ngoại lệ này để suy ra rằng `Long b = 1;` phải hợp lệ; chúng là các chuỗi chuyển đổi khác nhau.

## 9. Number không tự unboxing thành một kiểu số tùy ý

```java
// Minh họa lỗi; không biên dịch.
Number number = Integer.valueOf(7);
long value = number;
```

Biểu thức `number` có kiểu `Number`, không phải một trong các lớp bao cụ thể để áp dụng bước unboxing phù hợp ở đây.

Nếu hợp đồng là lấy giá trị `long` từ bất kỳ đối tượng `Number` nào, gọi API chuyển đổi số tường minh:

```java
// Minh họa trong một phương thức có number khác null.
long value = number.longValue();
```

Đây là lời gọi phương thức theo hợp đồng `Number`, không phải việc trình biên dịch tự chọn lớp bao dựa vào đối tượng thực tế. Nếu số ban đầu có phần lẻ hoặc nằm ngoài phạm vi kiểu đích, cần kiểm tra quy tắc chuyển đổi của loại số cụ thể.

Tương tự, một biến `Object` đang giữ `Integer` không được tự gán sang mọi kiểu nguyên thủy chỉ vì người viết biết dữ liệu bên trong. Đừng dùng ép tham chiếu thiếu kiểm chứng để thay cho một hợp đồng kiểu rõ ràng.

## 10. Hai rủi ro runtime: null và độ chính xác

### Unboxing null xảy ra trước bước mở rộng

```java
// Minh họa lỗi khi chạy.
Integer missing = null;
long value = missing;
```

Không có một `int` để mở rộng sang `long`. Chuyển đích sang kiểu rộng hơn không tránh được `NullPointerException`.

### Mở rộng không luôn giữ mọi chữ số chính xác

`int -> long` giữ được toàn bộ giá trị `int`. Nhưng một số chuyển đổi sang số dấu phẩy động có thể mất độ chính xác, dù được phân loại là mở rộng.

```java
// Minh họa trong một phương thức.
Integer exact = 16_777_217;
float rounded = exact;
int observed = (int) rounded;
```

`exact` được unboxing thành `int`, rồi mở rộng sang `float`. Giá trị `16_777_217` không được biểu diễn chính xác ở dạng `float` trong trường hợp này; `observed` là `16_777_216`.

Boxing/unboxing không tự tạo thêm độ chính xác cho phép chuyển nguyên thủy phía sau. Khi dữ liệu yêu cầu giữ chính xác số nguyên lớn hoặc phần thập phân theo quy tắc nghiệp vụ, phải chọn mô hình số phù hợp và kiểm tra phạm vi.

## 11. Chương trình đầy đủ

Lưu vào `ConversionCompositionDemo.java`:

```java
public class ConversionCompositionDemo {
    static String choose(long value) {
        return "long";
    }

    static String choose(Integer value) {
        return "Integer";
    }

    static long acceptLongPrimitive(long value) {
        return value;
    }

    public static void main(String[] args) {
        int primitive = 7;
        long widenedPrimitive = primitive;
        System.out.println("primitive=" + widenedPrimitive);

        Integer boxed = primitive;
        Number number = boxed;
        Object object = primitive;
        System.out.println("boxedKinds="
                + number.getClass().getSimpleName() + "/"
                + object.getClass().getSimpleName());

        long widenedFromBox = boxed;
        System.out.println("unboxed=" + widenedFromBox);

        Long directLong = 7L;
        System.out.println("wrapper=" + directLong);

        long intermediate = boxed;
        Long twoSteps = intermediate;
        System.out.println("twoSteps=" + twoSteps);

        Long fromCast = (long) boxed;
        System.out.println("cast=" + fromCast);

        Long fromArithmetic = boxed + 0L;
        System.out.println("arithmetic=" + fromArithmetic);

        Character letter = 'A';
        int code = letter;
        System.out.println("charCode=" + code);

        System.out.println(choose(1));
        System.out.println(choose(Integer.valueOf(1)));

        System.out.println("parameter=" + acceptLongPrimitive(boxed));

        Integer exact = 16_777_217;
        float rounded = exact;
        System.out.println("rounded=" + (int) rounded);

        Integer missing = null;
        try {
            long value = missing;
            System.out.println(value);
        } catch (NullPointerException ex) {
            System.out.println("null cannot unbox");
        }
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 -encoding UTF-8 ConversionCompositionDemo.java
java ConversionCompositionDemo
```

Stdout chính xác:

```text
primitive=7
boxedKinds=Integer/Integer
unboxed=7
wrapper=7
twoSteps=7
cast=7
arithmetic=7
charCode=65
long
Integer
parameter=7
rounded=16777216
null cannot unbox
```

Các dòng `twoSteps`, `cast` và `arithmetic` cho cùng giá trị nhưng không đi qua cùng một cấu trúc biểu thức. Chúng minh họa vì sao cần xác định kiểu tại từng ranh giới thay vì chỉ nhìn giá trị cuối.

Ví dụ bắt `NullPointerException` chỉ để tiếp tục quan sát trong chương trình học. Trong ứng dụng, nên kiểm tra và xử lý dữ liệu thiếu theo hợp đồng trước khi chuyển sang kiểu nguyên thủy.

## 12. Tự kiểm tra và cách tránh lỗi

Khi gặp một chuyển đổi khó hiểu, viết ra chuỗi kiểu cụ thể, rồi kiểm tra ngữ cảnh cho từng mũi tên.

| Câu lệnh | Hợp lệ? | Chuỗi chính |
| --- | --- | --- |
| `Number n = 1;` | Có | `int -> Integer -> Number` |
| `Integer i = 1; long n = i;` | Có nếu i khác null khi chạy | `Integer -> int -> long` |
| `Long n = 1;` | Không | Không tự mở rộng rồi boxing ở phép gán này |
| `Integer i = 1; Long n = i;` | Không | Không tự unboxing–mở rộng–boxing |
| `Integer i = 1; Long n = (long) i;` | Có nếu i khác null khi chạy | Biểu thức cast tạo `long`, rồi gán boxing |
| `Number n = 1; long x = n;` | Không | Không tự chọn unboxing từ kiểu `Number` |

Bài tập:

1. Giải thích sự khác nhau giữa mở rộng `int -> long` và mở rộng tham chiếu `Integer -> Number`.
2. Dự đoán tính hợp lệ của `Object x = 1;`, `Double y = 1;` và `Double z = 1.0;`.
3. Viết cách chuyển một `Integer` khác `null` sang `Long` bằng biến trung gian, không ép tham chiếu giữa hai lớp bao.
4. Vì sao `Long x = i + 0L;` hợp lệ nhưng `Long x = i;` không hợp lệ khi `i` là `Integer`?
5. Nếu thay `i` bằng `null`, những cách chuyển giá trị nào trong bài sẽ cần chính sách xử lý thiếu trước?
6. Đổi đối số của `choose` từ `int` sang `Integer` và giải thích overload được chọn theo giai đoạn.
7. Vì sao tên “mở rộng” không đủ để khẳng định mọi giá trị số nguyên vẫn chính xác sau khi đi qua `float`?

Tránh các lỗi như coi mọi lớp bao số là có thể gán qua lại, cho rằng mở rộng tránh được unboxing `null`, hoặc dùng một biểu thức tính toán khó đọc chỉ để lách lỗi chuyển kiểu.

## Tài liệu đối chiếu

- [Java Language Specification — Widening Primitive Conversion (§5.1.2)](https://docs.oracle.com/javase/specs/jls/se25/html/jls-5.html#jls-5.1.2): hướng mở rộng và các trường hợp mất độ chính xác.
- [Java Language Specification — Boxing và Unboxing (§5.1.7–§5.1.8)](https://docs.oracle.com/javase/specs/jls/se25/html/jls-5.html#jls-5.1.7): cặp nguyên thủy/lớp bao.
- [Java Language Specification — Assignment Contexts (§5.2)](https://docs.oracle.com/javase/specs/jls/se25/html/jls-5.html#jls-5.2): các chuỗi chuyển đổi trong phép gán.
- [Java Language Specification — Invocation Contexts (§5.3)](https://docs.oracle.com/javase/specs/jls/se25/html/jls-5.html#jls-5.3): chuyển đổi khi truyền đối số.
- [Java Language Specification — Method Applicability (§15.12.2)](https://docs.oracle.com/javase/specs/jls/se25/html/jls-15.html#jls-15.12.2): các giai đoạn chọn overload.
