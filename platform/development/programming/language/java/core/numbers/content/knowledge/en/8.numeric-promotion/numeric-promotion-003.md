# Vì sao `byte` cộng `byte` thường cho kết quả `int` trong Java?

Trong Java, biểu thức cộng hai biến `byte` được **nâng kiểu thành `int` trước khi tính**. Vì vậy, dù hai toán hạng có kiểu `byte` thì **kiểu của biểu thức `a + b` là `int`**, không phải `byte`. Đây là quy tắc **binary numeric promotion** (*nâng kiểu số học nhị nguyên*) được ngôn ngữ áp dụng khi biên dịch.

```java
byte a = 10;
byte b = 20;
int sum = a + b;  // hợp lệ, sum == 30
// byte wrong = a + b; // lỗi biên dịch: incompatible types / possible lossy conversion
```

Tính toán ra `30` nằm trong miền `byte` không làm compiler tự đổi kiểu kết quả của `a + b`. Trình biên dịch dựa vào **kiểu của biểu thức**, không suy luận mọi giá trị tương lai của biến. Có một ngoại lệ quan trọng cho **biểu thức hằng tại thời điểm biên dịch** như `byte c = 10 + 20;`, được trình bày bên dưới.

## 1. `byte` lưu được gì, vì sao Java không giữ kiểu `byte` khi cộng?

`byte` là primitive nguyên **8 bit có dấu**, miền `-128` đến `127`. Hai giá trị `byte` hoàn toàn hợp lệ có thể có tổng không biểu diễn được trong 8 bit:

```java
byte a = 100;
byte b = 50;
int sum = a + b; // 150: hợp lệ ở int, vượt byte
```

Nếu kết quả tự bị giới hạn vào `byte`, `150` sẽ thành `-106` khi ép kiểu xuống 8 bit. Java tránh làm hẹp kết quả của phép cộng thông thường một cách ngầm định bằng cách chọn `int` cho biểu thức.

Tuy nhiên, lý do **chuẩn xác ở mức ngôn ngữ** là quy tắc binary numeric promotion: các toán hạng kiểu `byte`, `short` và `char` được nâng thành `int` cho các phép toán số học như `+`, `-`, `*`, `/`, `%`. Việc chọn `int` không phụ thuộc vào tổng cụ thể là 30, 150 hay số âm. Với hai `byte`, `int` luôn đủ để chứa tổng toán học của riêng phép cộng đó: miền tổng là `-256` đến `254`.

Bảng nhanh:

| Toán hạng | Biểu thức | Kiểu biểu thức | Ví dụ kết quả |
| --- | --- | --- | --- |
| `byte` và `byte` | `a + b` | `int` | `10 + 20 = 30` |
| `short` và `short` | `s1 + s2` | `int` | `100 + 200 = 300` |
| `char` và `char` | `c1 + c2` | `int` | `'A' + 'B' = 131` |
| `byte` và `int` | `b + i` | `int` | Phụ thuộc giá trị |
| `byte` và `long` | `b + l` | `long` | Phụ thuộc giá trị |
| `byte` và `float` | `b + f` | `float` | Có thể làm tròn |
| `byte` và `double` | `b + d` | `double` | Có thể làm tròn |

Khi `+` có toán hạng kiểu `String`, nó có thể trở thành phép **nối chuỗi**, và quy tắc bảng số học này không còn áp dụng cho phép nối chuỗi ấy.

## 2. Quy tắc binary numeric promotion

Với các phép toán số học nhị nguyên cần nâng kiểu, Java xét hai toán hạng rồi chọn kiểu chung theo thứ tự ưu tiên:

1. Nếu một trong hai toán hạng là `double`, chuyển toán hạng còn lại sang `double`; kết quả `double`.
2. Ngược lại, nếu một toán hạng là `float`, chuyển toán hạng còn lại sang `float`; kết quả `float`.
3. Ngược lại, nếu một toán hạng là `long`, chuyển toán hạng còn lại sang `long`; kết quả `long`.
4. Nếu không thuộc ba trường hợp trên, cả hai toán hạng được chuyển sang `int`; kết quả `int`.

Vì `byte` không phải `double`, `float` hay `long`, phép cộng `byte + byte` rơi vào bước cuối:

```text
byte a ──widening──> int ──┐
                            ├── phép cộng int ──> int
byte b ──widening──> int ──┘
```

Widening `byte` → `int` giữ chính xác giá trị của từng toán hạng; đây là lý do tổng hai `byte` không tự tràn `byte` trước khi có phép cast hoặc gán thu hẹp khác.

```java
byte a = 120;
byte b = 120;

int result = a + b;        // 240
long widened = a + b;      // int 240 được mở rộng sau phép cộng
float asFloat = a + b;     // int 240 được mở rộng sau phép cộng
```

Chú ý: `widened` có kiểu `long` nhưng `a + b` vẫn là **biểu thức `int`**. Trong ví dụ chỉ có hai `byte`, tổng luôn nằm trong `int`; còn với các toán hạng `int` lớn, việc mở rộng **sau** phép cộng có thể quá muộn để ngăn tràn.

### Không phải mọi toán tử đều trả kiểu `int`

`a < b` với hai `byte` cũng có thể nâng hai toán hạng để so sánh, nhưng **kết quả toán tử so sánh là `boolean`**, không phải `int`. Toán tử cộng chuỗi có quy tắc riêng. Bài học này nói về kiểu của **kết quả các phép toán số học** chứ không tuyên bố mọi biểu thức có `byte` đều trả `int`.

## 3. Vì sao `byte c = a + b;` lỗi dù kết quả có thể nhỏ?

Giả sử:

```java
byte a = 10;
byte b = 20;
// byte c = a + b; // lỗi biên dịch
```

Trình biên dịch biết `a + b` có kiểu `int`. Ngữ cảnh gán trực tiếp từ một **biến hoặc biểu thức `int` thông thường** sang `byte` là **narrowing primitive conversion**, không được phép tự động ở đây.

Bất kể bạn đã “tính nhẩm” thấy 10 + 20 = 30, hai biến có thể đổi trong quá trình chạy. Quan trọng hơn: quy tắc gán hoạt động theo thông tin kiểu và ngoại lệ hằng đã được định nghĩa, chứ không chạy chương trình để dự đoán kết quả.

Các cách sửa tùy yêu cầu:

```java
byte a = 10;
byte b = 20;

int exactSum = a + b;           // nên dùng khi muốn giữ giá trị tổng
byte castSum = (byte) (a + b);   // hợp lệ, nhưng có thể mất dữ liệu nếu tổng ngoài byte
```

Nếu cần chắc chắn không vượt miền `byte`, kiểm tra **trước khi cast**:

```java
int candidate = a + b;
if (candidate < Byte.MIN_VALUE || candidate > Byte.MAX_VALUE) {
    throw new ArithmeticException("Sum outside byte range");
}
byte safeSum = (byte) candidate;
```

Đoạn này dùng trong một method/class đã khai báo `a` và `b`, không phải một chương trình độc lập. Trong ứng dụng, thường dễ hiểu hơn khi giữ kết quả dưới kiểu `int` nếu không bị giới hạn bởi API/bộ nhớ/định dạng dữ liệu buộc dùng `byte`.

## 4. Ngoại lệ quan trọng: biểu thức hằng `int` có thể gán vào `byte`

Vì `10` và `20` là literal kiểu `int`, `10 + 20` cũng là biểu thức `int`. Tuy nhiên Java cho phép **narrowing conversion trong ngữ cảnh gán** đối với một số biểu thức hằng tại thời điểm biên dịch, miễn giá trị nằm trong miền kiểu đích.

```java
byte direct = 10 + 20;     // hợp lệ: biểu thức hằng int = 30, vừa byte
byte maximum = 100 + 27;   // hợp lệ: 127
// byte tooLarge = 100 + 28; // lỗi: 128 nằm ngoài byte

short smallShort = 20_000 + 10_000; // hợp lệ: 30000
char letter = 60 + 5;      // hợp lệ: mã 65, tức 'A'
```

**Đây không phải bằng chứng `10 + 20` có kiểu `byte`.** Nó vẫn có kiểu `int`. Compiler cho phép chuyển hẹp một **giá trị hằng xác định được khi biên dịch** vì biết chắc kết quả nằm trong miền đích.

### `final` có thể tạo *constant variable*

Biến primitive được khai báo `final` và khởi tạo bằng biểu thức hằng có thể tham gia biểu thức hằng:

```java
final byte left = 10;
final byte right = 20;
byte result = left + right; // hợp lệ: left + right là constant expression int = 30
```

Tuy nhiên:

```java
byte left = 10;
byte right = 20;
// byte result = left + right; // lỗi: left/right không phải constant variables
```

Nếu biến `final` chỉ được gán bằng một giá trị xác định **lúc chạy** (ví dụ tham số method), nó không đương nhiên là constant variable theo nghĩa compiler sử dụng ở đây.

Đây là lý do nói “`byte` cộng `byte` **thường** cho kết quả `int`”: trên thực tế **biểu thức cộng luôn có kiểu `int`** khi hai toán hạng mang kiểu `byte`; còn việc gán biểu thức vào biến `byte` có thể được cho phép nhờ **ngoại lệ constant expression**, không nhờ thay đổi kiểu kết quả.

## 5. Cast về `byte`: cắt 8 bit thấp và có thể đổi dấu

`byte narrowed = (byte) (a + b);` yêu cầu narrowing từ `int` sang `byte`. Java giữ **8 bit thấp** của giá trị `int`, rồi diễn giải chúng thành số nguyên có dấu theo bù hai.

| Tổng toán học | `int` từ `a + b` | Cast về `byte` | Nhận xét |
| --- | ---: | ---: | --- |
| `10 + 20` | 30 | 30 | Còn trong miền |
| `100 + 50` | 150 | -106 | 150 - 256 = -106 |
| `120 + 120` | 240 | -16 | 240 - 256 = -16 |
| `-100 + (-50)` | -150 | 106 | Giữ bit thấp, đổi dấu |
| `127 + 1` | 128 | -128 | Qua biên dương |

```java
byte a = 100;
byte b = 50;
int trueSum = a + b;            // 150
byte narrowed = (byte) (a + b); // -106
```

Đây không phải `int` bị tràn khi cộng hai `byte`. **Phép cộng `int` tạo 150 đúng**, còn **cast** làm mất thông tin vì kiểu đích chỉ có 8 bit. Phân biệt vị trí phát sinh mất dữ liệu giúp debug đúng nguyên nhân.

Nếu muốn diễn giải một `byte` như số không dấu từ 0 đến 255, có thể dùng `Byte.toUnsignedInt(value)`. Ví dụ `Byte.toUnsignedInt((byte) 0xFF)` cho 255; bản thân `byte` vẫn có dấu và trong Java không tồn tại kiểu primitive tên `unsigned byte`.

## 6. Tại sao `b += n` và `b++` vẫn biên dịch?

Toán tử **gán kết hợp** như `+=` có quy tắc riêng: tính biểu thức và chuyển kết quả trở lại kiểu của biến đích. Vì vậy:

```java
byte b = 120;
b += 10;             // hợp lệ: 130 bị thu hẹp thành -126
// b = b + 10;        // lỗi: b + 10 kiểu int, không được tự gán cho byte
b = (byte) (b + 10); // hợp lệ nếu chủ ý cast
```

Một cách hiểu gần đúng về kiểu của `E1 op= E2` là `E1 = (T) ((E1) op (E2))`, trong đó `T` là kiểu biến `E1`; điểm khác biệt quan trọng là vế trái `E1` **chỉ được đánh giá một lần**. Đây là ngữ nghĩa gán kết hợp của Java, không phải vì `b + 10` đã mang kiểu `byte`.

### Prefix/postfix `++` và `--`

`++` và `--` cũng có quy tắc đặc biệt để cập nhật biến, nên dùng được với `byte`:

```java
byte b = 127;
byte old = b++; // old = 127; b = -128
byte now = ++b; // now = -127; b = -127
```

Khác với `+b` (kết quả `int` do *unary numeric promotion*), giá trị biểu thức `b++` và `++b` có **kiểu `byte`** khi `b` là `byte`. Chúng tự ghi trở lại biến và có thể tràn khi vượt miền.

Mặc dù `b += 1` và `b++` có thể trông giống phép `b = b + 1`, chúng không có cùng quy tắc chuyển kiểu khi gán. Muốn tránh cast mất dữ liệu, hãy giữ phép tính bằng `int` hoặc kiểm tra miền trước khi ghi lại `byte`.

## 7. `Math.addExact` có đổi kết quả về `byte` không?

Không. `Math.addExact(int, int)` trả `int`, và Java tự widening hai đối số `byte` sang `int` khi truyền tham số:

```java
byte a = 100;
byte b = 50;
int sum = Math.addExact(a, b); // 150, vẫn là int
```

`Math.addExact` bảo vệ phép cộng khỏi tràn **theo kiểu `int`** (hoặc kiểu `long` nếu chọn overload `long`). Nó **không** kiểm tra liệu tổng `150` có còn nằm trong miền `byte` hay không. Muốn bảo đảm giá trị thuộc miền `byte`, vẫn cần kiểm tra `Byte.MIN_VALUE`/`Byte.MAX_VALUE` trước cast.

Có thể viết helper rõ ý nghĩa nghiệp vụ:

```java
static byte addByteExactly(byte a, byte b) {
    int sum = a + b; // phép cộng int chính xác cho hai byte
    if (sum < Byte.MIN_VALUE || sum > Byte.MAX_VALUE) {
        throw new ArithmeticException("Byte overflow");
    }
    return (byte) sum;
}
```

Đây là **một method minh họa đặt trong class**, không phải chương trình độc lập. Nó từ chối tổng ngoài miền `byte` thay vì cho phép quay vòng.

Vì giới hạn `byte` thấp hơn `int` rất nhiều, có thể cộng hai `byte` an toàn ở `int` mà không cần `Math.addExact` cho riêng phép cộng đó. Việc kiểm tra miền `byte` mới là bước quyết định nếu API yêu cầu kết quả `byte`.

## 8. Numeric promotion trong chuỗi biểu thức và method overload

Sau phép cộng đầu tiên, **giá trị biểu thức đã có kiểu `int`**, nên các phép toán tiếp theo sẽ dùng kiểu mới đó (trừ khi xuất hiện toán hạng có kiểu cao hơn theo quy tắc binary numeric promotion):

```java
byte a = 10, b = 20, c = 30;
int total = a + b + c;    // (int)(a+b) + c -> int 60
long longer = a + b + 1L; // phép cộng cuối có long, kết quả long
```

Khi có `long` hoặc số thực, kiểu kết quả khác:

```java
byte a = 10;
byte b = 20;
long resultLong = a + 20L;      // phép cộng long
float resultFloat = a + 20.0f; // phép cộng float
double resultDouble = a + 20.0; // phép cộng double
```

Nếu kết hợp `int` lớn, cần chú ý vị trí của việc mở rộng:

```java
int max = Integer.MAX_VALUE;
long overflowed = max + 1;        // phép cộng int tràn trước rồi mới widening
long correct = (long) max + 1;    // phép cộng long, kết quả 2147483648
```

Mặc dù **hai `byte` cộng nhau không làm tràn `int`**, nguyên tắc về kiểu trung gian vẫn quan trọng khi biểu thức đã có `int` hoặc chứa toán hạng lớn hơn.

### Kết quả `int` ảnh hưởng overload

```java
static String classify(byte n) {
    return "byte";
}

static String classify(int n) {
    return "int";
}
```

Nếu `a` và `b` có kiểu `byte`:

- `classify(a)` chọn overload nhận `byte`.
- `classify(a + b)` chọn overload nhận `int`.
- `classify((byte) (a + b))` chọn overload nhận `byte`.

Đây là các method minh họa để đặt trong một class. Khi Java chọn overload cho `a+b`, nó nhìn **kiểu compile-time `int` của biểu thức**, không vì giá trị cuối tình cờ vừa `byte` mà tự chọn method nhận `byte`.

### `var` cũng suy luận từ kiểu biểu thức

```java
byte a = 10, b = 20;
var result = a + b; // result được suy luận là int, không phải byte
```

`var` không suy luận kiểu “nhỏ nhất có thể chứa giá trị”; nó dùng kiểu của biểu thức khởi tạo đã được ngôn ngữ xác định.

## 9. Wrapper `Byte` và unboxing

`Byte` là kiểu tham chiếu (wrapper) khác với primitive `byte`. Nếu hai tham chiếu `Byte` được cộng, Java có thể **unbox** chúng thành `byte` rồi áp dụng binary numeric promotion:

```java
Byte boxedA = Byte.valueOf((byte) 10);
Byte boxedB = Byte.valueOf((byte) 20);
int sum = boxedA + boxedB; // 30; unbox -> byte -> int -> cộng
```

Không thể tự động gán kết quả `int` cho `Byte` chỉ nhờ boxing:

```java
Byte boxedA = Byte.valueOf((byte) 10);
Byte boxedB = Byte.valueOf((byte) 20);
// Byte wrong = boxedA + boxedB; // lỗi: kết quả int không tự narrow rồi box
Byte ok = (byte) (boxedA + boxedB); // narrowing rõ ràng rồi boxing
```

Nếu một wrapper là `null`, bước unboxing có thể ném `NullPointerException` trước khi xảy ra phép cộng. Đây là một lỗi runtime khác với lỗi biên dịch khi cố gán `int` vào `byte`.

## 10. Phân biệt cộng số và nối chuỗi khi in kết quả

Biểu thức cộng số có kiểu `int`, nhưng toán tử `+` cũng dùng để nối chuỗi:

```java
byte a = 10, b = 20;
System.out.println("sum=" + a + b);   // sum=1020
System.out.println("sum=" + (a + b)); // sum=30
```

`+` có kết hợp từ trái sang phải: câu đầu tiên bắt đầu với `String`, tạo `"sum=10"` rồi nối `20`. Dấu ngoặc trong câu thứ hai buộc phép cộng số `a + b` diễn ra trước, cho `int` `30`, sau đó mới chuyển kết quả sang chuỗi.

Đây không phải vấn đề `byte` hay `int` bị tràn; nó là vấn đề **phân nhóm biểu thức và overload của toán tử `+`**.

## 11. Ví dụ Java 17+ đầy đủ, kiểm chứng kiểu và dữ liệu

Tạo tệp **`ByteAdditionDemo.java`**:

```java
public class ByteAdditionDemo {
    static String classify(byte value) {
        return "byte";
    }

    static String classify(int value) {
        return "int";
    }

    static byte addByteExactly(byte a, byte b) {
        int sum = a + b;
        if (sum < Byte.MIN_VALUE || sum > Byte.MAX_VALUE) {
            throw new ArithmeticException("Byte overflow");
        }
        return (byte) sum;
    }

    public static void main(String[] args) {
        byte a = 10;
        byte b = 20;
        int sum = a + b;
        System.out.println("sum=" + sum);
        System.out.println("firstType=" + classify(a));
        System.out.println("sumType=" + classify(a + b));
        System.out.println("castType=" + classify((byte) (a + b)));

        byte constant = 10 + 20;
        final byte f1 = 10;
        final byte f2 = 20;
        byte fromFinals = f1 + f2;
        System.out.println("constant=" + constant);
        System.out.println("fromFinals=" + fromFinals);

        byte largeA = 100;
        byte largeB = 50;
        System.out.println("wideSum=" + (largeA + largeB));
        System.out.println("narrowSum=" + (byte) (largeA + largeB));

        byte compound = 120;
        compound += 10;
        System.out.println("compound=" + compound);

        byte counter = 127;
        byte old = counter++;
        System.out.println("postOld=" + old);
        System.out.println("postCurrent=" + counter);

        var inferred = a + b;
        System.out.println("varType=" + classify(inferred));
        System.out.println("exactSmall=" + addByteExactly(a, b));

        try {
            addByteExactly(largeA, largeB);
            System.out.println("byteOverflow=missed");
        } catch (ArithmeticException ex) {
            System.out.println("byteOverflow=detected");
        }

        System.out.println("concatNoParen=" + a + b);
        System.out.println("concatWithParen=" + (a + b));

        Byte boxedA = Byte.valueOf((byte) 10);
        Byte boxedB = Byte.valueOf((byte) 20);
        System.out.println("boxedSum=" + (boxedA + boxedB));
    }
}
```

Tại thư mục có tệp trên, chạy:

```bash
javac ByteAdditionDemo.java
java ByteAdditionDemo
```

Output chính xác:

```text
sum=30
firstType=byte
sumType=int
castType=byte
constant=30
fromFinals=30
wideSum=150
narrowSum=-106
compound=-126
postOld=127
postCurrent=-128
varType=int
exactSmall=30
byteOverflow=detected
concatNoParen=1020
concatWithParen=30
boxedSum=30
```

Qua `sumType=int`, ta quan sát được kiểu `int` của biểu thức `a + b` ngay từ lúc compiler chọn overload. `constant` và `fromFinals` chứng minh ngoại lệ gán biểu thức hằng. `wideSum` với `narrowSum` cho thấy mất dữ liệu xảy ra lúc cast xuống `byte`. `compound` và `postCurrent` cho thấy toán tử cập nhật có thể thu hẹp kết quả và quay vòng.

## 12. Các lỗi phổ biến và cách ghi nhớ

| Phát biểu hoặc code | Đánh giá | Lý do |
| --- | --- | --- |
| “Hai biến `byte` cộng nhau trả `byte`.” | Sai | Binary numeric promotion tạo `int` |
| `byte r = a + b;` với `a`, `b` biến thường | Sai | Không tự narrowing `int` → `byte` |
| `byte r = 10 + 20;` | Đúng | Biểu thức hằng `int` bằng 30, vừa `byte` |
| `final byte a=10,b=20; byte r=a+b;` | Đúng | Hai biến `final` khởi tạo bằng hằng tạo constant expression |
| `int r = a + b;` | Đúng | Nhận đúng kiểu biểu thức, giữ mọi tổng của hai `byte` |
| `byte r = (byte)(a+b);` | Biên dịch được | Có thể mất dữ liệu nếu tổng ngoài -128..127 |
| `byte b=120; b+=10;` | Biên dịch được | Gán kết hợp thu hẹp ngầm; b thành -126 |
| `byte b=127; b++;` | Biên dịch được | Cập nhật có thể quay vòng về -128 |
| “`Math.addExact(a,b)` tự trả `byte`.” | Sai | Với hai `byte`, overload `int,int` trả `int` |
| “`var x = a+b` suy luận `byte`.” | Sai | `var` suy luận kiểu biểu thức: `int` |
| “`Byte + Byte` trả `Byte`.” | Sai | Unboxing và numeric promotion khiến kết quả là `int` |

Khi gặp phép cộng với kiểu nguyên nhỏ, hãy tự hỏi:

1. **Toán hạng có kiểu gì?** `byte`, `short`, `char` được nâng sang `int` khi dùng toán tử `+` số học thông thường.
2. **Kiểu biểu thức là gì?** Hai `byte` → `int`, kể cả khi tổng nhỏ.
3. **Biểu thức có là hằng tại thời điểm biên dịch không?** Nếu có và kết quả vừa `byte`, phép gán thu hẹp đặc biệt có thể hợp lệ.
4. **Kết quả được gán vào đâu?** `int` giữ giá trị; cast sang `byte` có nguy cơ mất bit; `+=` và `++` có quy tắc ghi lại khác.
5. **Bài toán có yêu cầu từ chối tràn miền `byte` không?** Kiểm tra khoảng `[-128,127]` trước cast, hoặc giữ kết quả dạng `int`.

**Kết luận:** `byte + byte` trong Java có **kiểu biểu thức `int`** theo quy tắc *binary numeric promotion*. Ngoại lệ biểu thức hằng chỉ nới điều kiện **gán xuống `byte`**, không thay đổi kiểu phép cộng. Biết rõ sự khác nhau này giúp tránh cả lỗi biên dịch lẫn việc cắt bit ngoài ý muốn khi cast hoặc dùng phép gán kết hợp.