# Unary numeric promotion và binary numeric promotion — Java 17+

Trong Java, **numeric promotion (nâng kiểu số)** là các phép chuyển đổi ngầm định mà ngôn ngữ áp dụng để xác định kiểu dùng khi đánh giá một biểu thức số. Hai cơ chế cần phân biệt:

- **Unary numeric promotion**: nâng kiểu cho **một toán hạng số** trong những ngữ cảnh được quy định, ví dụ toán tử một ngôi `+`, `-`, `~`.
- **Binary numeric promotion**: đưa **hai toán hạng số** về một kiểu chung trước một số phép toán hai ngôi, ví dụ cộng số `+`, nhân `*`, so sánh số `<`.

Cả hai đều được compiler quyết định từ **kiểu của biểu thức**, không phải từ giá trị thực tế. Vì vậy hai biến `byte` cộng nhau có kiểu kết quả `int`, ngay cả khi tổng nhỏ và nằm trong miền `byte`.

## 1. Unary numeric promotion: một toán hạng

Với một biểu thức phải áp dụng *unary numeric promotion*:

| Kiểu ban đầu | Kiểu sau promotion |
| --- | --- |
| `byte` | `int` |
| `short` | `int` |
| `char` | `int` |
| `int` | `int` |
| `long` | `long` |
| `float` | `float` |
| `double` | `double` |

Với wrapper số thích hợp như `Byte`, `Short`, `Character` hoặc `Integer`, Java có thể **unbox** trước rồi áp dụng promotion; wrapper `null` có thể gây `NullPointerException`.

Ví dụ:

~~~java
byte b = 100;
int a = +b; // Unary +: byte -> int.
int c = -b; // Unary -: byte -> int, ket qua -100.

short min = Short.MIN_VALUE; // -32768.
int positive = -min;        // int 32768, khong phai short.

byte zero = 0;
int inverted = ~zero;       // int -1, vi ~ ap dung tren 32 bit int.
~~~

**Bẫy phổ biến:** `-Short.MIN_VALUE` không tràn kiểu `short`, vì toán hạng đã được nâng thành `int`. Tuy nhiên, `-Integer.MIN_VALUE` vẫn là phép toán `int`; kết quả tràn và quay về `Integer.MIN_VALUE`. Promotion **không tự phát hiện tràn**.

Với `char`, giá trị 16 bit không dấu được nâng thành `int`. Ví dụ `'A' + 1` cho giá trị số `66` có kiểu `int`, **không phải** `char 'B'`.

## 2. Binary numeric promotion: hai toán hạng

Khi ngữ cảnh yêu cầu *binary numeric promotion*, Java đưa các toán hạng về cùng kiểu theo thứ tự ưu tiên:

1. Nếu có `double`, toán hạng kia chuyển sang `double`.
2. Ngược lại, nếu có `float`, toán hạng kia chuyển sang `float`.
3. Ngược lại, nếu có `long`, toán hạng kia chuyển sang `long`.
4. Nếu không, **cả hai thành `int`** (gồm `byte`, `short`, `char`).

| Biểu thức | Kiểu dùng để tính | Vì sao |
| --- | --- | --- |
| `byte + byte` | `int` | Các kiểu nguyên nhỏ được nâng thành `int` |
| `short + char` | `int` | Cả hai được nâng thành `int` |
| `int + long` | `long` | `long` ưu tiên hơn `int` |
| `long + float` | `float` | `float` ưu tiên hơn `long` |
| `float + double` | `double` | `double` ưu tiên cao nhất |
| `int < double` | Hai toán hạng chuyển thành `double` | Kết quả so sánh là **`boolean`** |
| `int == long` | Hai toán hạng chuyển thành `long` | Kết quả so sánh là **`boolean`** |

Thứ tự ưu tiên nói trên là **quy tắc kiểu**, không phải lời bảo đảm giữ nguyên giá trị: chuyển một `long` rất lớn sang `float` hoặc `double` có thể **mất độ chính xác**.

### Không phải mọi toán tử hai ngôi đều dùng binary numeric promotion

- `"n=" + 1 + 2` là **nối chuỗi** sau khi toán hạng đầu tiên là `String`; kết quả `"n=12"`. `"n=" + (1 + 2)` cho `"n=3"`.
- `boolean && boolean` hay `boolean || boolean` là phép logic, **không** phải phép toán số.
- Toán tử dịch bit `<<`, `>>`, `>>>` **không áp dụng binary numeric promotion cho hai toán hạng**: *mỗi* toán hạng được **unary numeric promotion** riêng. Kiểu kết quả là kiểu đã nâng của **toán hạng bên trái**.

## 3. Chương trình Java 17+ runnable

Tạo file **`NumericPromotionDemo.java`** với nội dung dưới đây:

~~~java
public class NumericPromotionDemo {
    private static void show(String label, Object value) {
        System.out.println(label + "=" + value
                + " (boxedType=" + value.getClass().getSimpleName() + ")");
    }

    public static void main(String[] args) {
        byte first = 100;
        byte second = 27;
        short minimum = Short.MIN_VALUE;
        byte zero = 0;
        char letter = 'A';

        show("bytePlusByte", first + second);
        show("unaryPlusByte", +first);
        show("unaryMinusShort", -minimum);
        show("unaryComplementByte", ~zero);
        show("charPlusOne", letter + 1);
        show("shortPlusChar", (short) 300 + letter);

        show("intPlusLong", 2 + 3L);
        show("floatPlusLong", 0.5f + 2L);
        show("doublePlusFloat", 1.25d + 0.5f);

        short count = 3;
        show("shiftShort", count << 2);
        show("shiftIntByLong", 1 << 2L);
        show("shiftLongByInt", 1L << 2);

        show("intDivision", 5 / 2);
        show("divisionWithDouble", 5 / 2.0);

        byte compound = 100;
        compound += 200;
        show("compoundByte", compound);

        Integer wrapper = 4;
        show("unboxPlusLong", wrapper + 2L);

        System.out.println("numericComparison=" + (first < 200L));
        System.out.println("stringConcat=" + "n=" + 1 + 2);
        System.out.println("stringGrouped=" + "n=" + (1 + 2));

        Integer missing = null;
        try {
            show("missingPlusOne", missing + 1);
        } catch (NullPointerException ex) {
            System.out.println("unboxNull=NullPointerException");
        }
    }
}
~~~

Mở PowerShell (Windows) hoặc Bash (Linux/macOS) tại thư mục có file và sử dụng **JDK 17+**:

~~~bash
java -version
javac -version
javac -encoding UTF-8 NumericPromotionDemo.java
java NumericPromotionDemo
~~~

**Expected output chính xác** của lệnh `java NumericPromotionDemo` (không gồm các dòng phiên bản JDK):

~~~text
bytePlusByte=127 (boxedType=Integer)
unaryPlusByte=100 (boxedType=Integer)
unaryMinusShort=32768 (boxedType=Integer)
unaryComplementByte=-1 (boxedType=Integer)
charPlusOne=66 (boxedType=Integer)
shortPlusChar=365 (boxedType=Integer)
intPlusLong=5 (boxedType=Long)
floatPlusLong=2.5 (boxedType=Float)
doublePlusFloat=1.75 (boxedType=Double)
shiftShort=12 (boxedType=Integer)
shiftIntByLong=4 (boxedType=Integer)
shiftLongByInt=4 (boxedType=Long)
intDivision=2 (boxedType=Integer)
divisionWithDouble=2.5 (boxedType=Double)
compoundByte=44 (boxedType=Byte)
unboxPlusLong=6 (boxedType=Long)
numericComparison=true
stringConcat=n=12
stringGrouped=n=3
unboxNull=NullPointerException
~~~

**Cách đọc tên `boxedType` trong output:** Các biểu thức số được truyền vào tham số `Object value` của `show`, nên Java thực hiện **autoboxing** kết quả nguyên thủy thành wrapper (`int -> Integer`, `long -> Long`...). Nhờ đó, `value.getClass().getSimpleName()` giúp quan sát kiểu nguyên thủy của **kết quả biểu thức trước khi boxing**. Điều này không có nghĩa mọi giá trị số trong Java vốn là đối tượng.

### Phân tích các nhóm kết quả

**Phép một ngôi:** `+first`, `-minimum` và `~zero` đều có kết quả `int`. Riêng `~zero` là phép đảo bit của **32-bit int 0**, nên kết quả `-1`.

**Phép hai ngôi:** `first + second` là `int 127`; `(short) 300 + letter` là `int 365`. `2 + 3L` có kiểu `long`, `0.5f + 2L` có kiểu `float`, `1.25d + 0.5f` có kiểu `double`.

**Phép dịch bit:** `count << 2` có kết quả `int` vì `count` là `short` được nâng lên `int`. Với `1 << 2L`, toán hạng phải là `long` nhưng kết quả **vẫn là `int`**. Còn `1L << 2` trả `long` vì toán hạng trái là `long`.

**Chia nguyên:** `5 / 2` được thực hiện trên `int` nên cho `2`. `5 / 2.0` áp dụng binary numeric promotion sang `double` trước phép chia, cho `2.5`.

**Gán kết hợp:** `compound += 200` cho phép ghi lại kết quả về `byte` dù phép cộng trung gian là `int 300`. Sau chuyển thu hẹp về 8 bit, kết quả là `44`.

**Wrapper:** `wrapper + 2L` unbox `Integer` thành `int` rồi nâng sang `long`; kết quả là `long 6`. Nếu wrapper bằng null, bước unbox gây `NullPointerException`.

## 4. Vì sao `byte` + `byte` không thể gán thẳng vào `byte`?

~~~java
byte x = 10;
byte y = 20;

int correct = x + y;       // Hop le: kieu ket qua la int.
// byte invalid = x + y;   // Loi bien dich, vi x+y la int.
byte narrowed = (byte) (x + y); // Co cast tuong minh.
~~~

Nếu cố gán `x + y` vào một biến `byte` mà không cast, compiler báo lỗi vì **kiểu biểu thức là `int`**, dù bạn biết tổng cụ thể vẫn nằm trong miền `byte`.

**Ngoại lệ đối với biểu thức hằng:** `byte b = 10 + 20;` có thể biên dịch, vì `10 + 20` là biểu thức hằng kiểu `int` với giá trị nằm trong miền `byte`. Quy tắc thu hẹp hằng số ở ngữ cảnh gán **không làm thay đổi** việc `x + y` giữa hai biến `byte` có kiểu `int`.

Một cast ngược về `byte` cũng không tự bảo đảm giữ nguyên giá trị; ví dụ `(byte) (100 + 100)` cho `-56` do kết quả 200 vượt miền `byte`.

## 5. Binary promotion khi so sánh và tính toán

Cùng một quy tắc binary numeric promotion có thể áp dụng cho biểu thức số học và so sánh số:

~~~java
short left = 10;
long right = 20L;

long total = left + right; // long 30.
boolean smaller = left < right; // true.
~~~

Với phép cộng, kiểu kết quả là kiểu số được chọn sau promotion. Với phép so sánh `<`, `<=`, `>`, `>=` hoặc so sánh bằng giữa hai biểu thức số, **các toán hạng** được nâng theo quy tắc thích hợp nhưng **kết quả phép so sánh là `boolean`**, không phải kiểu số.

Do chuyển sang kiểu floating-point có thể mất độ chính xác, hãy cẩn thận khi so sánh `long` rất lớn với `float`/`double`. Không dùng “được Java tự nâng kiểu” như chứng minh rằng mọi phép so sánh đều giữ đúng từng đơn vị nguyên.

## 6. Phép dịch bit: hai toán hạng nâng kiểu riêng

Đây là trường hợp rất hay bị nhầm với binary numeric promotion:

~~~java
short s = 3;
int result = s << 2; // left short -> int; result int.

int x = 1 << 2L;     // RHS long duoc chap nhan; ket qua van int.
long y = 1L << 2;    // Left long; ket qua long.
~~~

Trong phép dịch bit, Java áp dụng **unary numeric promotion** cho *mỗi toán hạng*, rồi lấy **kiểu của toán hạng trái đã nâng** làm kiểu kết quả. Toán hạng phải cung cấp số vị trí dịch; nó không biến kết quả thành `long` chỉ vì nó có kiểu `long`.

Ngoài ra, với toán hạng trái kiểu `int`, Java chỉ dùng **5 bit thấp** của khoảng dịch (tương đương lấy modulo 32); với `long`, Java dùng **6 bit thấp** (tương đương lấy modulo 64). Đây là quy tắc dịch bit riêng, không phải quy tắc chọn kiểu của binary numeric promotion.

## 7. Promotion, ép kiểu và toán tử gán kết hợp khác nhau

| Cơ chế | Ví dụ | Điểm cần nhớ |
| --- | --- | --- |
| Unary numeric promotion | `+((byte) 5)` | Kết quả kiểu `int` |
| Binary numeric promotion | `2 + 3L` | Kết quả kiểu `long` |
| Cast tường minh | `(byte) 200` | Có thể mất dữ liệu |
| Gán kết hợp | `byte b = 100; b += 200;` | Chuyển ngầm kết quả phép toán về kiểu vế trái |
| Autoboxing | `Object o = 2 + 3L;` | Kết quả `long` được boxing thành `Long` |
| Nối chuỗi | `"n=" + 1 + 2` | Không phải cộng số sau khi `String` tham gia |

Khi kết quả có thể vượt miền kiểu đích, nên kiểm tra miền trước khi cast hoặc dùng kiểu đủ rộng. Nếu cần kiểm tra tràn `int`/`long` trong phép cộng, nhân, có thể dùng các phương thức `Math.addExact`, `Math.multiplyExact` theo yêu cầu.

## 8. Bài tập tự kiểm tra

1. **Unary promotion:** `byte b = 5;` thì `+b` có kiểu gì?  
   *Đáp án:* `int`, giá trị 5.
2. **Binary promotion:** `short s = 10; char c = 'A';` thì `s + c` có kiểu và giá trị nào?  
   *Đáp án:* `int`, giá trị 75.
3. **Ưu tiên:** `1L + 0.5f` có kiểu gì?  
   *Đáp án:* `float`, giá trị 1.5f trong trường hợp này.
4. **Dịch bit:** `1 << 2L` có kiểu kết quả `long` không?  
   *Đáp án:* Không, kết quả `int 4`, vì loại toán tử này nâng mỗi toán hạng riêng.
5. **Chia:** `double result = 5 / 2;` có giá trị bao nhiêu?  
   *Đáp án:* `2.0` do phép chia kiểu `int` xảy ra trước khi gán sang `double`.
6. **Gán kết hợp:** `byte b = 100; b += 200;` cho gì?  
   *Đáp án:* `44` sau phép cộng trung gian `int 300` và chuyển thu hẹp về `byte`.
7. **Null wrapper:** `Integer x = null; int y = x + 1;` lỗi ở đâu?  
   *Đáp án:* Khi unboxing `x` để thực hiện phép cộng, ném `NullPointerException`.

## Checklist ghi nhớ

- [ ] Unary promotion: `byte`/`short`/`char` nâng thành `int`; các kiểu số lớn giữ nguyên.
- [ ] Binary promotion: ưu tiên `double > float > long > int` trong các ngữ cảnh số thích hợp.
- [ ] Promotion là quy tắc **kiểu biểu thức**, không phải bảo đảm không mất giá trị.
- [ ] `byte + byte` có kiểu `int`; phép gán hằng có thể có ngoại lệ riêng.
- [ ] Toán tử dịch bit nâng **từng toán hạng riêng**, kiểu kết quả dựa vào vế trái.
- [ ] `+=` có bước chuyển về kiểu biến đích; có thể làm mất dữ liệu.
- [ ] Phân biệt cộng số, nối chuỗi và boxing/unboxing.

**Kết luận:** Trước khi viết phép tính Java, hãy xác định **toán tử có dùng unary hay binary numeric promotion không**, **kiểu của từng toán hạng sau nâng kiểu** và **kiểu kết quả**. Đặc biệt cẩn thận với `byte`/`short`/`char`, phép dịch bit, phép gán kết hợp và chuyển đổi có thể mất độ chính xác.
