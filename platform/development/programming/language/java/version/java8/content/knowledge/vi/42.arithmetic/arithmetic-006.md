# Math.incrementExact, decrementExact, negateExact và toIntExact — số học nguyên có kiểm tra tràn (Java 8+)

## 1. Mục tiêu và tình huống thực tế

Trong Java, biểu thức số nguyên thông thường có thể **tràn phạm vi** nhưng vẫn trả về một giá trị kiểu int hoặc long. Giá trị đó không nhất thiết còn phản ánh kết quả toán học mong muốn:

~~~java
int counter = Integer.MAX_VALUE;
counter++;
System.out.println(counter);
// -2147483648
~~~

Phép **++** không tự ném ArithmeticException khi tràn. Giá trị dương lớn nhất của int có thể bị vòng về giá trị âm nhỏ nhất. Nếu biến chứa số thứ tự, giới hạn dữ liệu, bộ đếm, số lượng hàng hoặc kích thước, một kết quả như vậy thường là **lỗi nghiệp vụ nguy hiểm**.

Java 8 giới thiệu các phương thức số học nguyên có kiểm tra tràn trong **java.lang.Math**:

- **Math.incrementExact(int/long):** tăng một đơn vị; ném ArithmeticException nếu vượt giá trị lớn nhất.
- **Math.decrementExact(int/long):** giảm một đơn vị; ném ArithmeticException nếu vượt dưới giá trị nhỏ nhất.
- **Math.negateExact(int/long):** đổi dấu; ném ArithmeticException nếu đối số là giá trị âm nhỏ nhất.
- **Math.toIntExact(long):** chuyển long sang int **chỉ nếu giá trị vẫn biểu diễn được bằng int**; ngoài phạm vi sẽ ném ArithmeticException.

Cả bốn API **vẫn được hỗ trợ trong Java SE hiện hành**, phù hợp yêu cầu chỉ học kiến thức còn áp dụng, không dựa vào API legacy. Đây là phương án **fail fast** khi không muốn Java âm thầm làm tràn số hoặc cắt bớt bit trong phép đổi kiểu.

**Cần nhớ:** kiểm tra tràn số chỉ bảo vệ tính biểu diễn trong kiểu nguyên đã chọn. Nó không tự kiểm tra giá trị hợp lệ về nghiệp vụ, không cung cấp transaction, và không tự xử lý tranh chấp giữa nhiều thread.

## 2. Phạm vi int và long: các giới hạn phải thuộc

| Kiểu | Số bit | Nhỏ nhất | Lớn nhất |
| --- | --- | --- | --- |
| **int** | 32 bit, signed | -2.147.483.648 | 2.147.483.647 |
| **long** | 64 bit, signed | -9.223.372.036.854.775.808 | 9.223.372.036.854.775.807 |

Các hằng số:

~~~java
Integer.MIN_VALUE
Integer.MAX_VALUE
Long.MIN_VALUE
Long.MAX_VALUE
~~~

Không cần tự ghi literal dài trong logic biên. Java sử dụng integer arithmetic với phạm vi giới hạn của kiểu; khi phép tính nguyên thông thường vượt giới hạn, các bit kết quả được giữ theo kiểu dữ liệu và không có thông báo tràn kiểu checked overflow.

Ví dụ int:

~~~java
int max = Integer.MAX_VALUE;
System.out.println(max + 1);
// -2147483648

int min = Integer.MIN_VALUE;
System.out.println(min - 1);
// 2147483647
~~~

Ở đây **max + 1** và **min - 1** tính ở kiểu int. Chúng không trở thành long chỉ vì ta in ra màn hình hoặc gán vào một biến long sau đó.

**Lưu ý về dấu âm:** số dương **2.147.483.648** không tồn tại trong kiểu int, nên không có kết quả int hợp lệ cho phép đổi dấu **Integer.MIN_VALUE**. Tình huống tương tự áp dụng với Long.MIN_VALUE.

## 3. Chữ ký chính xác của bốn API

Trong **java.lang.Math**, các overload vẫn còn áp dụng từ Java 8:

~~~java
public static int  incrementExact(int a)
public static long incrementExact(long a)

public static int  decrementExact(int a)
public static long decrementExact(long a)

public static int  negateExact(int a)
public static long negateExact(long a)

public static int  toIntExact(long value)
~~~

**Tất cả là static methods**, gọi như Math.incrementExact(value), không tạo object Math. Chúng không có trạng thái nội bộ và không tự thay đổi biến được truyền vào.

**ArithmeticException** được ném khi kết quả cần biểu diễn vượt phạm vi đích (int hoặc long). Với giá trị hợp lệ, phương thức trả kết quả số học chính xác, không trả Optional và không làm phép saturation.

**Khác biệt về overload:** ba phép tăng/giảm/đổi dấu có cả int và long; **toIntExact chỉ nhận long và trả int**. Nếu gọi với đối số int, Java có thể widen int lên long rồi trả int, nhưng chẳng mang lại lợi ích về kiểm tra narrowing vì giá trị int đã nằm trong phạm vi đích.

**Không có overload cho float/double, BigInteger hay BigDecimal** trong bốn phương thức Math này. Muốn kiểm tra độ chính xác của các kiểu khác phải dùng API/hợp đồng tương ứng.

## 4. Math.incrementExact — tăng một đơn vị và phát hiện tràn

Quy tắc:

~~~java
int next = Math.incrementExact(current);
long nextLong = Math.incrementExact(currentLong);
~~~

Hai dòng trên là snippet trong một method có biến current kiểu int, currentLong kiểu long.

Ví dụ đầu vào an toàn:

~~~java
System.out.println(Math.incrementExact(41));
// 42

System.out.println(Math.incrementExact(-1));
// 0

System.out.println(Math.incrementExact(Integer.MIN_VALUE));
// -2147483647
~~~

**Chỉ trường hợp giá trị đã bằng MAX_VALUE** mới gây tràn khi cộng một:

~~~java
Math.incrementExact(Integer.MAX_VALUE); // ArithmeticException
Math.incrementExact(Long.MAX_VALUE);    // ArithmeticException
~~~

Với giá trị int có kiểu rõ ràng, compiler chọn overload int; với Long.MAX_VALUE, compiler chọn overload long.

**Không khác ++ về mục tiêu tăng một đơn vị, nhưng khác hoàn toàn về cách báo lỗi tràn.** Trong công việc cần số thứ tự tăng liên tục, trả về số âm sau khi chạm giới hạn có thể làm hỏng thứ tự, lookup hoặc điều kiện dừng.

Cần phân biệt **phạm vi kiểu** và **giới hạn nghiệp vụ**. Ví dụ counter chỉ được chạy tới 1000: Math.incrementExact(1000) vẫn trả 1001 vì nó chỉ bảo vệ giới hạn int/long, không hiểu quy tắc 1000 của ứng dụng.

## 5. Math.decrementExact — giảm một đơn vị và phát hiện underflow

Quy tắc:

~~~java
int previous = Math.decrementExact(current);
long previousLong = Math.decrementExact(currentLong);
~~~

Ví dụ:

~~~java
System.out.println(Math.decrementExact(41));
// 40

System.out.println(Math.decrementExact(0));
// -1

System.out.println(Math.decrementExact(Integer.MAX_VALUE));
// 2147483646
~~~

**Chỉ trường hợp giá trị đã bằng MIN_VALUE** mới gây tràn khi trừ một:

~~~java
Math.decrementExact(Integer.MIN_VALUE); // ArithmeticException
Math.decrementExact(Long.MIN_VALUE);    // ArithmeticException
~~~

So với toán tử **--**:

~~~java
int value = Integer.MIN_VALUE;
value--;
System.out.println(value);
// 2147483647
~~~

Toán tử -- trên số nguyên có thể wrap, còn decrementExact từ chối kết quả không biểu diễn được.

**Ứng dụng:** số lượng hàng còn lại, cursor giảm dần, bộ đếm rollback, số phiên bản giảm hoặc các độ lệch signed. Nếu nghiệp vụ yêu cầu **không âm**, vẫn phải kiểm tra giá trị: decrementExact(0) trả -1 hoàn toàn hợp lệ về kiểu int, nhưng có thể không hợp lệ về nghiệp vụ.

## 6. Math.negateExact — đổi dấu và bẫy MIN_VALUE

Đổi dấu toán học là a → -a. Với hầu hết giá trị int/long, điều này có thể biểu diễn được:

~~~java
System.out.println(Math.negateExact(41));
// -41

System.out.println(Math.negateExact(-41));
// 41

System.out.println(Math.negateExact(0));
// 0

System.out.println(Math.negateExact(Integer.MAX_VALUE));
// -2147483647
~~~

**Ngoại lệ đúng tại MIN_VALUE** vì phạm vi signed không đối xứng:

~~~java
Math.negateExact(Integer.MIN_VALUE); // ArithmeticException
Math.negateExact(Long.MIN_VALUE);    // ArithmeticException
~~~

Với số nguyên thông thường, phép đổi dấu unary - không bắt buộc báo lỗi:

~~~java
int min = Integer.MIN_VALUE;
System.out.println(-min);
// -2147483648
~~~

Tức là kết quả vẫn âm, không phải số dương mà người lập trình có thể mong đợi.

**Math.abs không phải giải pháp tự động cho bẫy này**: Math.abs(Integer.MIN_VALUE) vẫn trả Integer.MIN_VALUE, và Math.abs(Long.MIN_VALUE) cũng vẫn là Long.MIN_VALUE. Nếu nghiệp vụ đòi giá trị không âm, phải xử lý rõ MIN_VALUE hoặc đổi sang kiểu đủ lớn/BigInteger.

**Đừng hiểu negateExact là phủ định logic Boolean.** Nó chỉ dành cho số nguyên có dấu, không phải **!condition**.

## 7. Math.toIntExact — narrowing conversion có kiểm tra

Một long có phạm vi rộng hơn int. Ép kiểu thông thường:

~~~java
long value = 2147483648L;
int narrowed = (int) value;

System.out.println(narrowed);
// -2147483648
~~~

Nó chỉ giữ các bit thấp theo quy tắc narrowing của Java, không báo rằng kết quả đã khác giá trị long ban đầu.

Thay bằng:

~~~java
int safe = Math.toIntExact(value);
// ArithmeticException nếu value ngoài [Integer.MIN_VALUE, Integer.MAX_VALUE].
~~~

Các trường hợp trong phạm vi:

~~~java
System.out.println(Math.toIntExact(0L));                 // 0
System.out.println(Math.toIntExact(-1L));                // -1
System.out.println(Math.toIntExact(2147483647L));       // 2147483647
System.out.println(Math.toIntExact(-2147483648L));      // -2147483648
~~~

Các trường hợp vượt ngoài:

~~~java
Math.toIntExact(2147483648L);   // ArithmeticException
Math.toIntExact(-2147483649L);  // ArithmeticException
Math.toIntExact(Long.MAX_VALUE);// ArithmeticException
Math.toIntExact(Long.MIN_VALUE);// ArithmeticException
~~~

**toIntExact không yêu cầu số dương**; nó chỉ yêu cầu kết quả long biểu diễn được nguyên vẹn bằng int. Một giá trị âm nằm trong phạm vi là hợp lệ. Nếu API đích đòi index hoặc length không âm, cần kiểm tra domain riêng.

**toIntExact cũng không kiểm tra bộ nhớ.** Kể cả value là 1.500.000.000 và chuyển được sang int, việc tạo một mảng có số phần tử ấy vẫn có thể thất bại vì memory/giới hạn mảng.

## 8. Bảng điều kiện tràn: chính xác chỗ nào ném lỗi?

| API | Đầu vào bình thường | Trường hợp biên bị từ chối | Điều kiện lỗi |
| --- | --- | --- | --- |
| incrementExact(int) | 7 → 8 | Integer.MAX_VALUE | a + 1 vượt int |
| incrementExact(long) | 7L → 8L | Long.MAX_VALUE | a + 1 vượt long |
| decrementExact(int) | 7 → 6 | Integer.MIN_VALUE | a - 1 thấp hơn int |
| decrementExact(long) | 7L → 6L | Long.MIN_VALUE | a - 1 thấp hơn long |
| negateExact(int) | -7 → 7 | Integer.MIN_VALUE | -a không có int dương hợp lệ |
| negateExact(long) | -7L → 7L | Long.MIN_VALUE | -a không có long dương hợp lệ |
| toIntExact(long) | 7L → 7 | Integer.MAX_VALUE + 1L hoặc MIN_VALUE - 1L | Giá trị không nằm trong int |

Trong **tất cả các trường hợp overflow của bảng**, Java ném **ArithmeticException**. Không có giá trị được trả về từ lời gọi thất bại.

Không nên assert **thông điệp** của ArithmeticException bằng chuỗi cụ thể. Ví dụ "integer overflow" hoặc "long overflow" có thể khác giữa method, implementation và JDK. Kiểm tra **loại exception và kết quả/hậu quả của API gọi** đáng tin hơn.

**Phân biệt lỗi trước khi gọi:** nếu code phải unbox một Integer null để gọi incrementExact(int), có thể xảy ra NullPointerException trước khi method bắt đầu; đây không phải ArithmeticException do tràn số.

## 9. So sánh với ++, --, dấu trừ và ép kiểu int

| Biểu thức | Kiểm tra tràn? | Khi vượt phạm vi |
| --- | --- | --- |
| **x++**, **++x** | Không | Giá trị int/long wrap; còn khác nhau ở giá trị expression trả về |
| **x--**, **--x** | Không | Wrap |
| **x + 1**, **x - 1** | Không | Wrap nếu đang tính trên kiểu nguyên giới hạn |
| **-x** | Không | Với MIN_VALUE, kết quả vẫn MIN_VALUE |
| **(int) longValue** | Không | Narrowing giữ các bit thấp, giá trị có thể đổi |
| **Math.incrementExact(x)** | Có | ArithmeticException nếu MAX |
| **Math.decrementExact(x)** | Có | ArithmeticException nếu MIN |
| **Math.negateExact(x)** | Có | ArithmeticException nếu MIN |
| **Math.toIntExact(longValue)** | Có | ArithmeticException nếu ngoài int |

Toán tử ++ và -- **thay đổi biến**; các phương thức Math trả kết quả và **không sửa biến đầu vào**:

~~~java
int original = 7;
int updated = Math.incrementExact(original);
System.out.println(original + " -> " + updated);
// 7 -> 8
~~~

Nếu muốn thay giá trị, phải gán rõ:

~~~java
original = Math.incrementExact(original);
~~~

**Có một lợi ích khi lỗi xảy ra:** nếu incrementExact ném ArithmeticException trong vế phải, phép gán trên dòng đó không được hoàn thành, nên biến đích vẫn giữ giá trị trước đó trong ngữ cảnh single-thread. Nhưng điều này **không đồng nghĩa thao tác đọc–gán nguyên tử** khi nhiều thread chia sẻ biến.

## 10. Đúng kiểu của biểu thức: widening phải xảy ra trước phép toán

Một lỗi tinh vi:

~~~java
long wrong = Integer.MAX_VALUE + 1;
System.out.println(wrong);
// -2147483648
~~~

Dù biến đích là **long**, hai toán hạng **Integer.MAX_VALUE** và **1** đều có kiểu int. Java **tính phép cộng int trước**, gây wrap; sau đó mới widen kết quả sai thành long.

Đúng khi thực sự muốn tính vượt int:

~~~java
long correct = (long) Integer.MAX_VALUE + 1L;
System.out.println(correct);
// 2147483648
~~~

Vì một toán hạng là long trước phép cộng, kết quả được tính trong phạm vi long.

Khi muốn kết quả cuối vẫn là int, kiểm tra narrowing:

~~~java
long nextLong = (long) Integer.MAX_VALUE + 1L;
int nextInt = Math.toIntExact(nextLong);
// ArithmeticException, không được phép cắt về số âm.
~~~

**Không viết Math.toIntExact(Integer.MAX_VALUE + 1) để phát hiện tràn trong phép cộng int.** Nếu biểu thức đã wrap trước khi gọi, toIntExact chỉ nhìn thấy long được widen từ giá trị int sai và sẽ không biết phép toán trước đó từng overflow.

Đúng hơn có thể dùng **Math.addExact(Integer.MAX_VALUE, 1)** để phát hiện ngay ở phép cộng int hoặc tính trong long rồi dùng toIntExact theo chủ đích.

## 11. Ghép phép toán và thứ tự kiểm tra

Mỗi Math.*Exact chỉ kiểm tra **phép toán của chính lời gọi đó**. Nếu chuỗi có nhiều bước, phải bảo vệ từng bước có khả năng tràn:

~~~java
long base = 2147483647L;
long next = Math.incrementExact(base);   // 2147483648L, hợp lệ trong long.
int index = Math.toIntExact(next);       // ArithmeticException.
~~~

Ngược lại:

~~~java
int index = Math.incrementExact(Math.toIntExact(base));
// ArithmeticException ở incrementExact vì base vừa bằng Integer.MAX_VALUE.
~~~

Cả hai cách từ chối kết quả int không hợp lệ, nhưng điểm phát sinh exception và kiểu trung gian khác nhau.

**Kiểm tra cuối không sửa được bước tính đã bị wrap trước đó:**

~~~java
long badIntermediate = Long.MAX_VALUE + 1L;
// Giá trị đã wrap thành Long.MIN_VALUE.
int result = Math.toIntExact(badIntermediate);
// Vẫn báo lỗi ở ví dụ này, nhưng không truy ra chính xác phép cộng long đã lỗi.
~~~

Nếu intermediate có thể wrap rồi tình cờ rơi trở lại một phạm vi chấp nhận được trong chuỗi nhiều bước, kiểm tra cuối thậm chí có thể **không phát hiện lỗi ban đầu**. Vì vậy hãy dùng **addExact/subtractExact/multiplyExact**, hoặc đổi sang BigInteger khi cần một phép toán đúng trên phạm vi rộng hơn long.

**Quy tắc:** xác định kiểu của từng toán hạng, phạm vi được phép ở mỗi phép toán và thời điểm cần chuyển kiểu. Không chỉ nhìn vào kiểu của biến đích.

## 12. ArithmeticException là tín hiệu lỗi, không phải giá trị sentinel

Các phương thức này **không bão hòa (saturate)** về MAX/MIN và không trả một mã đặc biệt như -1 khi tràn. Chúng **ném ArithmeticException**.

Ví dụ:

~~~java
try {
    int next = Math.incrementExact(current);
    // Chỉ chạy khi next nằm trong phạm vi int.
} catch (ArithmeticException overflow) {
    // Chính sách ứng dụng: từ chối, trả error có ý nghĩa, dùng kiểu lớn hơn...
}
~~~

Đây là snippet trong một method với biến current kiểu int.

**Đừng tự động thay lỗi bằng 0 hoặc Integer.MAX_VALUE** nếu nghiệp vụ không định nghĩa như vậy. Một bộ đếm quan trọng và một chỉ số dữ liệu có thể cần dừng tác vụ hoặc cảnh báo thay vì tiếp tục bằng giá trị giả.

Không dùng exception như cơ chế vòng lặp bình thường nếu **biên nghiệp vụ có thể kiểm tra rõ và được chạm thường xuyên**. Ví dụ trạng thái từ 0 tới 100, check quota trước, rồi dùng Math.incrementExact như lớp bảo vệ phạm vi kiểu khi cần.

**Phân loại chính xác:** ArithmeticException do Math.*Exact khác lỗi **IllegalArgumentException** khi giá trị vẫn vừa kiểu nhưng không hợp lệ theo quy tắc nghiệp vụ, chẳng hạn một index âm.

## 13. Tình huống ứng dụng: counter, ID, phân trang và độ lớn dữ liệu

### Counter và sequence

~~~java
int nextSequence(int lastSequence) {
    return Math.incrementExact(lastSequence);
}
~~~

Đây là method minh họa, hợp lệ khi sequence được giới hạn bởi int và overflow phải bị báo lỗi. Tuy nhiên nó không tự bảo đảm **duy nhất toàn hệ thống**: nếu nhiều process cùng tạo ID hoặc nếu sequence khởi động lại, cần storage/protocol đồng bộ riêng.

### Vòng lặp với biên max

~~~java
int value = Integer.MAX_VALUE - 1;
value = Math.incrementExact(value);  // MAX, vẫn hợp lệ.
// Lần tăng tiếp theo ném ArithmeticException.
~~~

Nếu index có thể đạt tới MAX trong một vòng for, điều kiện dừng phải được thiết kế để không phụ thuộc vào việc **i++** wrap trở lại số âm.

### Chuyển kích thước long sang int

Các API Java có thể cung cấp kích thước/offset/count kiểu long; API đích dùng int:

~~~java
int checkedLength = Math.toIntExact(lengthLong);
~~~

**Sau khi chuyển vẫn cần kiểm tra** lengthLong không âm, không vượt giới hạn dữ liệu hoặc ngân sách bộ nhớ. Math.toIntExact(-1L) vẫn trả -1, hợp lệ về kiểu nhưng không hợp lệ cho độ dài.

### Tính khoản bù có dấu

~~~java
long inverse = Math.negateExact(deltaLong);
~~~

Nếu deltaLong bằng Long.MIN_VALUE thì không có inverse dương biểu diễn được trong long; nghiệp vụ cần báo lỗi hoặc dùng BigInteger.

## 14. Chương trình Java 17+ hoàn chỉnh: mọi đường biên

Tạo file **ExactMathDemo.java**. Bản demo dùng **record Page** (tính năng Java 16+, hợp lệ trên Java 17) để minh họa kiểm tra chuyển long thành cặp int. Hàm checkInt/checkLong chỉ bắt **ArithmeticException**, in loại lỗi thay vì message để output ổn định.

~~~java
import java.util.function.IntSupplier;
import java.util.function.LongSupplier;

public class ExactMathDemo {
    record Page(int first, int last) { }

    static void checkInt(String label, IntSupplier operation) {
        try {
            System.out.println(label + ": " + operation.getAsInt());
        } catch (ArithmeticException ex) {
            System.out.println(label + ": ArithmeticException");
        }
    }

    static void checkLong(String label, LongSupplier operation) {
        try {
            System.out.println(label + ": " + operation.getAsLong());
        } catch (ArithmeticException ex) {
            System.out.println(label + ": ArithmeticException");
        }
    }

    static Page pageFromLong(long first, long last) {
        if (first < 0 || last < first) {
            throw new IllegalArgumentException("invalid range");
        }
        return new Page(Math.toIntExact(first), Math.toIntExact(last));
    }

    public static void main(String[] args) {
        int original = 7;
        int updated = Math.incrementExact(original);
        System.out.println("return, no mutation: " + original + " -> " + updated);

        checkInt("increment int 41", () -> Math.incrementExact(41));
        checkInt("increment int MAX", () -> Math.incrementExact(Integer.MAX_VALUE));
        checkLong("increment long MAX", () -> Math.incrementExact(Long.MAX_VALUE));
        checkInt("decrement int -41", () -> Math.decrementExact(-41));
        checkInt("decrement int MIN", () -> Math.decrementExact(Integer.MIN_VALUE));
        checkLong("decrement long MIN", () -> Math.decrementExact(Long.MIN_VALUE));
        checkInt("negate int -41", () -> Math.negateExact(-41));
        checkInt("negate int zero", () -> Math.negateExact(0));
        checkInt("negate int MIN", () -> Math.negateExact(Integer.MIN_VALUE));
        checkLong("negate long MIN", () -> Math.negateExact(Long.MIN_VALUE));
        checkInt("toIntExact 123456789L", () -> Math.toIntExact(123456789L));
        checkInt("toIntExact int MAX", () -> Math.toIntExact((long) Integer.MAX_VALUE));
        checkInt("toIntExact int MIN", () -> Math.toIntExact((long) Integer.MIN_VALUE));
        checkInt("toIntExact MAX+1", () -> Math.toIntExact((long) Integer.MAX_VALUE + 1L));
        checkInt("toIntExact MIN-1", () -> Math.toIntExact((long) Integer.MIN_VALUE - 1L));

        int wrapped = Integer.MAX_VALUE;
        wrapped++;
        System.out.println("plain ++ wraps: " + wrapped);
        long outside = (long) Integer.MAX_VALUE + 1L;
        System.out.println("plain (int) wraps: " + (int) outside);
        System.out.println("plain unary -MIN wraps: " + (-Integer.MIN_VALUE));

        System.out.println("valid page: " + pageFromLong(10L, 20L));
        try {
            System.out.println(pageFromLong(0L, (long) Integer.MAX_VALUE + 1L));
        } catch (ArithmeticException ex) {
            System.out.println("oversize page: ArithmeticException");
        }
        try {
            System.out.println(pageFromLong(-1L, 10L));
        } catch (IllegalArgumentException ex) {
            System.out.println("negative page: IllegalArgumentException");
        }
        long value = (long) Integer.MAX_VALUE;
        checkInt("checked long arithmetic then narrow",
                () -> Math.toIntExact(Math.incrementExact(value)));
    }
}
~~~

Biên dịch/chạy bằng JDK 17+:

~~~bash
javac ExactMathDemo.java
java ExactMathDemo
~~~

**Stdout đã được kiểm chứng bằng javac --release 17 và chạy thành công:**

~~~text
return, no mutation: 7 -> 8
increment int 41: 42
increment int MAX: ArithmeticException
increment long MAX: ArithmeticException
decrement int -41: -42
decrement int MIN: ArithmeticException
decrement long MIN: ArithmeticException
negate int -41: 41
negate int zero: 0
negate int MIN: ArithmeticException
negate long MIN: ArithmeticException
toIntExact 123456789L: 123456789
toIntExact int MAX: 2147483647
toIntExact int MIN: -2147483648
toIntExact MAX+1: ArithmeticException
toIntExact MIN-1: ArithmeticException
plain ++ wraps: -2147483648
plain (int) wraps: -2147483648
plain unary -MIN wraps: -2147483648
valid page: Page[first=10, last=20]
oversize page: ArithmeticException
negative page: IllegalArgumentException
checked long arithmetic then narrow: ArithmeticException
~~~

**Vì sao bài test có cả kết quả và exception?**

- incrementExact/decrementExact/negateExact chỉ ném ở những biên thực sự không còn giá trị biểu diễn.
- toIntExact chấp nhận **chính xác cả hai đầu biên int** và từ chối ngay ngoài chúng.
- Các ví dụ toán tử thông thường minh họa silent wrap/cast khác với API exact.
- Page kiểm tra **nghiệp vụ trước**, sau đó mới narrowing; kết quả oversize và negative thuộc hai loại lỗi khác nhau.
- **return, no mutation** nhắc rằng phương thức Math không tự sửa biến original.
- Từng test catch chỉ một exception mong đợi. Không kiểm tra exception message để tránh phụ thuộc JDK.

## 15. Java 8 runnable: cập nhật AtomicInteger/AtomicLong có kiểm tra tràn

Khi biến counter được dùng chung giữa nhiều thread, chỉ viết **current = Math.incrementExact(current)** không đủ atomic: hai thread có thể đọc cùng giá trị cũ rồi cùng ghi, làm mất lần tăng.

**AtomicInteger.updateAndGet(IntUnaryOperator)** và **AtomicLong.updateAndGet(LongUnaryOperator)** là API hiện hành cho phép cập nhật theo một hàm. Dùng method reference **Math::incrementExact** hoặc **Math::decrementExact** để kết hợp việc cập nhật nguyên tử với phát hiện tràn.

Tạo file **CheckedCounterJava8Demo.java**:

~~~java
import java.math.BigInteger;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicLong;

public class CheckedCounterJava8Demo {
    static void throwsArithmetic(String label, Runnable action) {
        try {
            action.run();
            throw new AssertionError("expected ArithmeticException for " + label);
        } catch (ArithmeticException expected) {
            System.out.println(label + ": ArithmeticException");
        }
    }

    public static void main(String[] args) {
        AtomicInteger counter = new AtomicInteger(Integer.MAX_VALUE - 1);
        System.out.println("atomic next: " +
                counter.updateAndGet(Math::incrementExact));
        throwsArithmetic("atomic overflow", () ->
                counter.updateAndGet(Math::incrementExact));
        System.out.println("counter kept: " + counter.get());

        AtomicLong remaining = new AtomicLong(Long.MIN_VALUE + 1);
        System.out.println("atomic decrement: " +
                remaining.updateAndGet(Math::decrementExact));
        throwsArithmetic("atomic underflow", () ->
                remaining.updateAndGet(Math::decrementExact));
        System.out.println("remaining kept: " + remaining.get());

        int[] values = {0, 1, -1, 41, Integer.MIN_VALUE + 1, Integer.MAX_VALUE - 1};
        boolean reversible = true;
        for (int value : values) {
            reversible &= Math.decrementExact(Math.incrementExact(value)) == value;
            reversible &= Math.incrementExact(Math.decrementExact(value)) == value;
        }
        System.out.println("round trip in safe range: " + reversible);

        System.out.println("big integer beyond long: " +
                BigInteger.valueOf(Long.MAX_VALUE).add(BigInteger.ONE));
        throwsArithmetic("big integer narrow",
                () -> BigInteger.valueOf(Integer.MAX_VALUE)
                        .add(BigInteger.ONE).intValueExact());
        System.out.println("min can narrow: " +
                Math.toIntExact((long) Integer.MIN_VALUE));
    }
}
~~~

Để chạy trên JDK hiện đại có hỗ trợ biên dịch target Java 8:

~~~bash
javac --release 8 CheckedCounterJava8Demo.java
java CheckedCounterJava8Demo
~~~

**Stdout đã kiểm chứng khi biên dịch với javac --release 8:**

~~~text
atomic next: 2147483647
atomic overflow: ArithmeticException
counter kept: 2147483647
atomic decrement: -9223372036854775808
atomic underflow: ArithmeticException
remaining kept: -9223372036854775808
round trip in safe range: true
big integer beyond long: 9223372036854775808
big integer narrow: ArithmeticException
min can narrow: -2147483648
~~~

**Hai điều về AtomicInteger/AtomicLong:**

1. **updateAndGet** có thể gọi update function nhiều lần dưới cạnh tranh, nên function phải **side-effect-free**. Math.incrementExact và Math.decrementExact là hàm thuần phù hợp.
2. Khi lời gọi updateAndGet dùng function exact ném ArithmeticException từ giá trị hiện tại, phép tính đó **không ghi giá trị đã tràn**. Demo cho thấy counter vẫn ở MAX và remaining vẫn ở MIN sau lần tăng/giảm bị từ chối. Với chương trình thực tế có writer cạnh tranh, giá trị có thể bị một writer khác thay đổi riêng sau đó; không hiểu exception là một transaction khóa toàn hệ thống.

**So sánh:** AtomicInteger.incrementAndGet() thông thường **không ném ArithmeticException khi tràn**; có thể wrap. Khi overflow phải bị từ chối, chọn updateAndGet với function exact và policy lỗi phù hợp.

## 16. Khi nào dùng int, long và BigInteger?

Ba cấp độ lựa chọn:

**int:** số cần xử lý chắc chắn nằm trong phạm vi signed 32-bit; dùng các phương thức exact để phát hiện vượt giới hạn.

**long:** nếu int quá nhỏ cho tính toán, dùng long từ đầu và kết hợp exact long operations nếu long vẫn có nguy cơ overflow.

**BigInteger:** nếu phạm vi toán học có thể vượt 64-bit signed, BigInteger hỗ trợ số nguyên độ lớn tùy ý trong giới hạn tài nguyên.

~~~java
BigInteger bigger = BigInteger.valueOf(Long.MAX_VALUE)
        .add(BigInteger.ONE);

System.out.println(bigger);
// 9223372036854775808
~~~

BigInteger là immutable; phép add trả object mới, không sửa object cũ. Nó có các phương thức **intValueExact()** và **longValueExact()** để chuyển về primitive **có kiểm tra mất phần giá trị**, phù hợp khi logic trước đó đã dùng BigInteger.

~~~java
int narrowed = bigger.intValueExact();
// ArithmeticException: giá trị vượt int.
~~~

**Không dùng BigInteger vì nghĩ nó miễn phí:** nó có chi phí cấp phát/bộ nhớ/tính toán, và vẫn cần giới hạn đầu vào để phòng resource exhaustion.

**Nếu dữ liệu là tiền hoặc số thập phân cần thang đo chính xác**, cân nhắc BigDecimal với quy tắc scale/rounding phù hợp; bốn phương thức Math đang học là số học **nguyên**, không phải cơ chế xử lý tiền tệ nói chung.

## 17. Xây test biên có hệ thống

Ít nhất cần những trường hợp sau:

| Phương thức | Hợp lệ phải thử | Không hợp lệ phải thử |
| --- | --- | --- |
| incrementExact(int) | MIN, -1, 0, MAX-1 | MAX |
| incrementExact(long) | MIN, -1L, 0L, MAX-1 | MAX |
| decrementExact(int) | MIN+1, 0, 1, MAX | MIN |
| decrementExact(long) | MIN+1, 0L, 1L, MAX | MIN |
| negateExact(int) | 0, 1, -1, MAX, MIN+1 | MIN |
| negateExact(long) | 0L, 1L, -1L, MAX, MIN+1 | MIN |
| toIntExact(long) | (long)MIN, -1L, 0L, (long)MAX | MIN-1L, MAX+1L, Long.MIN/MAX |

**Kiểm tra cả giá trị trả về và loại exception**. Với lời gọi có trạng thái bao quanh, kiểm tra cả việc state không bị ghi sai khi exact operation thất bại.

### Kiểm tra một tính chất đảo ngược khi trong phạm vi an toàn

~~~java
int[] samples = {0, 1, -1, 41, Integer.MIN_VALUE + 1, Integer.MAX_VALUE - 1};
for (int n : samples) {
    assert Math.decrementExact(Math.incrementExact(n)) == n;
    assert Math.incrementExact(Math.decrementExact(n)) == n;
}
~~~

Đây là đoạn minh họa trong method; **assert** của Java thường tắt nếu không bật **-ea**. Chương trình Java 8 ở phần 15 dùng so sánh boolean rồi in kết quả, không phụ thuộc vào việc bật assertion.

**Không dùng property đảo ngược tại biên không hợp lệ**: increment(MAX) và decrement(MIN) cố ý ném exception. Một property test phải giới hạn miền đầu vào của phép biến đổi.

### Assertion lỗi kiểu JUnit 5 (minh họa)

~~~java
assertThrows(ArithmeticException.class,
        () -> Math.incrementExact(Integer.MAX_VALUE));
assertEquals(Integer.MIN_VALUE,
        Math.toIntExact((long) Integer.MIN_VALUE));
~~~

Đây là snippet **chỉ chạy trong project đã có JUnit Jupiter**, với static imports của Assertions; không phải Java SE standalone. Dùng JUnit 5 là tùy chọn cho test suite hiện đại, không thay thế được việc xác minh biên đúng.

## 18. Các lỗi thiết kế phổ biến

1. **Dùng ++/-- rồi tưởng Java tự ném khi overflow.** Số nguyên thông thường wrap.
2. **Coi Math.incrementExact(x) đã đổi x.** Phương thức trả kết quả, cần gán rõ.
3. **Coi Math.toIntExact(long) là phép ép kiểu cắt bit.** Nó báo ArithmeticException nếu long ngoài int.
4. **Dùng Math.toIntExact sau khi biểu thức đã overflow ở int/long.** Kết quả đầu vào có thể đã sai; kiểm tra từng bước.
5. **Nhầm Integer.MIN_VALUE có đối số dương int tương ứng.** Đổi dấu MIN không biểu diễn được trong cùng kiểu.
6. **Dùng Math.abs(MIN_VALUE) làm giá trị tuyệt đối dương.** Kết quả vẫn âm tại trường hợp biên.
7. **Chỉ test MAX và bỏ MIN.** decrementExact, negateExact và toIntExact cần phía âm.
8. **Đoán ArithmeticException message.** Chỉ kiểm tra loại lỗi và semantics.
9. **Đồng nhất tràn số với domain validation.** Math.decrementExact(0) hợp lệ; số lượng âm có thể không hợp lệ về nghiệp vụ.
10. **Tin rằng (long) result luôn tránh tràn.** Nếu toán hạng ban đầu là int, overflow xảy ra trước khi kết quả được widen.
11. **Dùng int literal không có hậu tố L ở giá trị vượt int** trong chỗ cần long, hoặc nhầm lẫn phép toán promotion.
12. **Tin rằng math exact khiến các phép đọc–gán trên biến chia sẻ trở nên atomic.** Không có bảo đảm concurrency như vậy.
13. **Coi AtomicInteger.incrementAndGet là checked overflow.** Nó có thể wrap.
14. **Đặt side effect trong updateAndGet function.** Function có thể chạy lại khi CAS contention.
15. **Tự động retry ArithmeticException vô hạn.** Giá trị đã sát biên sẽ không tự thay đổi nếu không có một policy khác.
16. **Chuyển long sang int trước khi kiểm tra giới hạn nghiệp vụ.** Sau khi narrow, thông tin giá trị gốc có thể bị mất nếu dùng cast.
17. **Tưởng toIntExact bảo đảm index hợp lệ cho array.** Còn phải kiểm tra không âm và nhỏ hơn array.length.
18. **Dùng các phương thức exact cho float/double.** Bốn method này chỉ dành cho int/long; float/double có quy tắc khác.
19. **Tưởng ArithmeticException là checked exception.** Nó là RuntimeException, caller không bị buộc khai báo throws nhưng vẫn cần policy xử lý.
20. **Không phân biệt overload int/long.** Kiểu của đối số quyết định phiên bản được gọi.
21. **Dùng một phép toán BigInteger rồi narrow bằng intValue thay vì intValueExact khi mất dữ liệu không được phép.**
22. **Coi phát hiện overflow là kiểm tra mọi lỗi nghiệp vụ.** Nó chỉ kiểm tra khả năng biểu diễn của kiểu.

## 19. Trường hợp dữ liệu đến từ parsing, API hoặc database

Giả sử API gửi một số lượng dạng văn bản:

~~~java
long parsed = Long.parseLong(raw);
int quantity = Math.toIntExact(parsed);
if (quantity < 0) {
    throw new IllegalArgumentException("quantity must be non-negative");
}
~~~

Đây là snippet trong method có biến raw. **Long.parseLong** có thể ném **NumberFormatException** nếu chuỗi không phải số hợp lệ hoặc vượt phạm vi long. **Math.toIntExact** có thể ném ArithmeticException khi số long hợp lệ nhưng vượt phạm vi int. **Domain check** xử lý số âm hợp kiểu nhưng sai quy tắc.

Đừng bắt gộp cả ba rồi trả một giá trị mặc định như 0 nếu API không công bố chính sách như vậy.

Nếu dữ liệu đến từ SQL COUNT hoặc file size được biểu diễn là long, cần xác định:

- Giữ **long** khi API có thể chấp nhận.
- Chỉ narrowing khi bên nhận thật sự cần int và giá trị đã được kiểm tra.
- Nếu muốn số đếm lớn hơn Long.MAX_VALUE, cần model/type khác; đừng chờ exact method tự mở rộng kiểu.

**Nếu kết quả đi vào phân trang:** kiểm tra cả start/end, không âm, end >= start, giới hạn page size, và index nằm trong phạm vi thực của collection. Math.toIntExact chỉ là một lớp bảo vệ nhỏ.

## 20. Stream, lambda và thời điểm ArithmeticException xuất hiện

Một pipeline dùng kiểu long và chuyển thành int:

~~~java
int[] values = LongStream.of(1L, 2L, (long) Integer.MAX_VALUE + 1L)
        .mapToInt(Math::toIntExact)
        .toArray();
// ArithmeticException khi terminal operation tiêu thụ giá trị ngoài int.
~~~

Đây là snippet có import **java.util.stream.LongStream**. Giống các intermediate operations khác của Stream, mapToInt tạo pipeline; giá trị chưa được xử lý đến khi terminal operation yêu cầu. Nếu nguồn có giá trị ngoài phạm vi, phép chuyển của một phần tử sẽ gây ArithmeticException trong quá trình tiêu thụ.

**Không có "kết quả int[] thành công một phần" được trả về** từ toArray khi exception xảy ra. Nếu pipeline có side effect ngoài như ghi database, side effect trước lỗi có thể vẫn tồn tại: phải có chính sách rollback/transaction riêng.

Với Stream<Integer>, dùng Math::incrementExact có thể hoạt động qua unboxing/boxing, nhưng cần hiểu kiểu generic và null. Nếu phần tử null được unbox sang int, NullPointerException có thể xảy ra trước khi Math.incrementExact chạy, không phải ArithmeticException do overflow.

Trong parallel stream, exception có thể xuất hiện ở thread xử lý khác và được truyền về terminal operation; không nên dùng order of failures làm một hợp đồng nghiệp vụ.

## 21. Lưu ý về số nguyên, dấu và các phép toán khác

Các phương thức **Math.addExact, subtractExact, multiplyExact** cũng là thành viên hiện hành của nhóm checked integer arithmetic. Khi số liệu có nhiều hơn một phép toán, việc kết hợp những phương thức này thường giúp bảo vệ các bước trung gian.

Ví dụ tính số chỗ còn trống:

~~~java
int capacity = 100;
int used = 40;
int remaining = Math.subtractExact(capacity, used);
// 60
~~~

**Nhưng Math.subtractExact không biết capacity >= used**. Nếu used=150, kết quả -50 vẫn vừa int và không gây tràn. Vẫn cần domain rule.

Một điều thú vị: số nguyên âm **Integer.MIN_VALUE** không có số dương đối xứng trong int; nhưng **(long) Integer.MIN_VALUE** có thể đổi dấu an toàn:

~~~java
long positiveMagnitude = Math.negateExact((long) Integer.MIN_VALUE);
System.out.println(positiveMagnitude);
// 2147483648
~~~

Ta đã **widen lên long trước khi negate**. Điều này khác với Math.negateExact(Integer.MIN_VALUE), vốn chọn overload int và ném ArithmeticException.

**Khi đọc code:** chú ý thứ tự cast và loại toán hạng trong mỗi biểu thức. Đây thường là nguồn lỗi khó thấy hơn chính lời gọi Math.*Exact.

## 22. Câu hỏi tự luyện và lời giải

**1.** Math.incrementExact(Integer.MAX_VALUE) trả giá trị gì? — **Không trả**; ném ArithmeticException.

**2.** Math.incrementExact(Long.MAX_VALUE) có tự chuyển sang BigInteger không? — **Không**; ném ArithmeticException.

**3.** Math.decrementExact(Integer.MIN_VALUE) cho Integer.MAX_VALUE như -- không? — **Không**; ném ArithmeticException.

**4.** Math.decrementExact(0) có báo lỗi không? — **Không**, trả -1. Giá trị âm có hợp nghiệp vụ hay không là kiểm tra riêng.

**5.** Math.negateExact(-5) và Math.negateExact(0) trả gì? — **5 và 0**.

**6.** Vì sao Math.negateExact(Integer.MIN_VALUE) thất bại? — Giá trị 2.147.483.648 không nằm trong int signed.

**7.** Math.toIntExact((long) Integer.MAX_VALUE) có hợp lệ? — **Có**, trả Integer.MAX_VALUE.

**8.** Math.toIntExact((long) Integer.MAX_VALUE+1L) thì sao? — **ArithmeticException**, vì vượt biên int.

**9.** Math.toIntExact(-1L) có báo lỗi vì âm? — **Không**, trả -1. Phương thức không kiểm tra index hợp lệ.

**10.** Sau int y=Math.incrementExact(x), x có thay đổi không? — **Không**, trừ khi gán kết quả ngược lại cho x.

**11.** Vì sao long a=Integer.MAX_VALUE+1 có thể thành số âm? — Phép cộng hai int xảy ra và overflow trước khi kết quả được widen sang long.

**12.** Dùng cast (int) một long ngoài int có ném ArithmeticException? — **Không**; giá trị có thể bị cắt bit.

**13.** AtomicInteger.incrementAndGet có được bảo vệ tràn kiểu Math.incrementExact? — **Không**; dùng updateAndGet(Math::incrementExact) với policy lỗi nếu cần.

**14.** Vì sao updateAndGet lambda không nên gửi email? — Hàm update có thể bị gọi lại dưới contention, làm side effect lặp.

**15.** Math.abs(Integer.MIN_VALUE) có đảm bảo không âm? — **Không**; bẫy MIN_VALUE vẫn tồn tại.

**16.** Khi cần số nguyên vượt Long.MAX_VALUE thì làm gì? — Cân nhắc BigInteger, xử lý giới hạn resource và dùng intValueExact/longValueExact khi chuyển về primitive.

**17.** Math.incrementExact trên một int shared có tự atomic không? — **Không**; là phép tính thuần, cần atomic/synchronization nếu nhiều thread cùng cập nhật.

**18.** Có nên chỉ test trường hợp 0 và 1 không? — **Không**; phải test MAX/MIN, sát biên và ngoài biên cho narrowing.

## 23. Checklist đưa vào ứng dụng thật

**Kiểu:** xác định nguồn là int hay long; nếu cần kết quả lớn hơn kiểu hiện tại, widen **trước** phép toán; nếu long vẫn không đủ, dùng BigInteger.

**Overflow policy:** nếu không được phép wrap, dùng Math.*Exact ở **từng bước có rủi ro tràn**, không chỉ kiểm tra cuối pipeline.

**Narrowing:** toIntExact khi long → int cần giữ nguyên giá trị; thêm kiểm tra nonnegative, bounds, giới hạn memory và policy nghiệp vụ.

**Exception handling:** ArithmeticException là tín hiệu kết quả không biểu diễn được; không nuốt lỗi hay đổi thành default tùy tiện. Nếu API cần mã lỗi, chuyển đổi có chủ đích tại ranh giới phù hợp.

**Concurrency:** không coi x=Math.incrementExact(x) là atomic; dùng AtomicInteger/AtomicLong.updateAndGet với pure function hoặc cơ chế đồng bộ theo thiết kế.

**Test:** bao phủ MIN/MAX, MIN±1/MAX±1, kết quả âm hợp lệ, tính không thay đổi biến nguồn, compose nhiều phép toán, wrap của toán tử thường, state sau lỗi, và tình huống thread contention.

**Dữ liệu ngoài:** tách lỗi parse, overflow, domain validation; không coi các trường hợp này là một loại duy nhất.

**Theo dõi vận hành:** overflow trên counter/ID thường là tín hiệu cần đổi schema hoặc chính sách cấp số; không tiếp tục tạo ID bị wrap mà không đánh giá hậu quả.

## 24. Tóm tắt và tài liệu chính thức còn áp dụng

**Những điều bắt buộc nhớ:**

1. **incrementExact** tăng 1; lỗi tại MAX của int/long.
2. **decrementExact** giảm 1; lỗi tại MIN của int/long.
3. **negateExact** đổi dấu; lỗi tại MIN vì không có số dương tương ứng trong cùng kiểu.
4. **toIntExact(long)** chỉ chuyển sang int khi giá trị nằm giữa Integer.MIN_VALUE và Integer.MAX_VALUE.
5. Cả bốn **ném ArithmeticException** khi tràn, thay vì lặng lẽ wrap.
6. Các phép toán **không sửa biến**; phép gán phải được viết rõ.
7. **++/--, unary - và (int)long** không cho cùng bảo đảm checked overflow.
8. **Đừng để biểu thức đã wrap trước khi gọi toIntExact**; bảo vệ các phép toán trung gian.
9. **Kiểm tra domain tách biệt** với kiểm tra phạm vi kiểu.
10. **Không nhầm phép tính exact với cập nhật thread-safe**; Atomic update cần cơ chế atomic riêng.
11. **Giữ giá trị long nếu có thể**, hoặc BigInteger khi cần miền số rộng hơn 64 bit.
12. **Test đầy đủ hai biên dương/âm**, không dựa vào exception message.

**Nguồn Oracle Java SE 26 (đã kiểm tra các chữ ký, điều kiện tràn và mục Since: 1.8):**

- **Math** — incrementExact, decrementExact, negateExact, toIntExact và họ addExact/subtractExact/multiplyExact: https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/Math.html
- **Integer** — MIN_VALUE và MAX_VALUE: https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/Integer.html
- **Long** — phạm vi signed 64-bit: https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/Long.html
- **ArithmeticException** — RuntimeException cho các điều kiện số học bất thường: https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/ArithmeticException.html
- **BigInteger** — phép toán nguyên độ lớn tùy ý và intValueExact/longValueExact: https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/math/BigInteger.html
- **AtomicInteger** — updateAndGet và function có thể được chạy lại: https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/concurrent/atomic/AtomicInteger.html
- **AtomicLong** — updateAndGet cho long: https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/concurrent/atomic/AtomicLong.html
- **Java Language Specification, §4.2.2** — ngữ nghĩa của các kiểu số nguyên/overflow: https://docs.oracle.com/javase/specs/jls/se26/html/jls-4.html#jls-4.2.2

**Phiên bản:** Cả bốn phương thức Math được học đều **có từ Java 8 (Since: 1.8)** và vẫn được Oracle tài liệu hóa trong Java 26; không dùng API legacy. Ví dụ chính dùng record nên yêu cầu Java 17+; ví dụ thứ hai biên dịch với target Java 8, chỉ dùng API phù hợp Java 8.

**Kết luận:** chọn Math.*Exact khi tính đúng và thông báo tràn quan trọng hơn việc âm thầm nhận một giá trị wrap; chọn toIntExact khi chuyển long → int phải giữ nguyên giá trị. Tính đúng vẫn đòi kiểm tra từng bước, loại dữ liệu, giới hạn nghiệp vụ và tính an toàn đồng thời ở cấp ứng dụng.
