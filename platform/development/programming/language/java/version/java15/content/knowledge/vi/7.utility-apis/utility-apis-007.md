# ArithmeticException khi trị tuyệt đối không thể biểu diễn (Java 15+)

## Mục tiêu

Hiểu tại sao lấy trị tuyệt đối của một số nguyên âm đôi khi **không thể cho kết quả dương cùng kiểu dữ liệu**, vì sao **Math.abs(int/long)** có thể trả về số âm, và cách **Math.absExact(int/long)** phát hiện tình huống này bằng **ArithmeticException**. Biết chọn cách xử lý khi cần báo lỗi tràn số hoặc khi thực sự cần độ lớn chính xác vượt phạm vi int/long.

**Math.absExact(int)** và **Math.absExact(long)** là API chuẩn được bổ sung từ **Java 15**, vẫn được hỗ trợ trong **Java 17 trở lên**. ArithmeticException là ngoại lệ không bắt buộc phải khai báo trong mệnh đề throws vì kế thừa RuntimeException.

## 1. Vấn đề: miền giá trị số nguyên có dấu không đối xứng

Java sử dụng biểu diễn số nguyên có dấu kiểu **bù hai (two's complement)**. Với số có N bit, có **một giá trị âm nhiều hơn** số giá trị dương:

| Kiểu | Giá trị nhỏ nhất | Giá trị lớn nhất | Trị tuyệt đối của giá trị nhỏ nhất |
| --- | ---: | ---: | ---: |
| int (32 bit) | -2.147.483.648 | 2.147.483.647 | 2.147.483.648 (không biểu diễn được bằng int) |
| long (64 bit) | -9.223.372.036.854.775.808 | 9.223.372.036.854.775.807 | 9.223.372.036.854.775.808 (không biểu diễn được bằng long) |

Về toán học, trị tuyệt đối phải không âm: |x| = x nếu x ≥ 0, và |x| = -x nếu x < 0. Với **Integer.MIN_VALUE = -2^31**, kết quả cần là **2^31**; nhưng số dương lớn nhất của int chỉ là **2^31 - 1**. Tương tự, **Long.MIN_VALUE = -2^63** cần **2^63** khi lấy trị tuyệt đối, cũng vượt phạm vi long.

**Chỉ một đầu vào nguyên đặc biệt của mỗi kiểu** gây tràn trong phép lấy trị tuyệt đối: **Integer.MIN_VALUE** đối với int và **Long.MIN_VALUE** đối với long. Các số âm khác, số 0 và các số dương trong miền giá trị đều có trị tuyệt đối biểu diễn được.

Ví dụ:

~~~java
Math.absExact(-25);                 // 25
Math.absExact(0);                   // 0
Math.absExact(Integer.MAX_VALUE);   // 2147483647
Math.absExact(Integer.MIN_VALUE);   // ném ArithmeticException
~~~

Các dòng trên là **biểu thức minh họa**, không phải một tệp Java độc lập. Chương trình hoàn chỉnh có ở mục 5.

## 2. Sự khác nhau giữa Math.abs() và Math.absExact()

### Math.abs(int/long): trả về giá trị âm ở trường hợp MIN_VALUE

Trong phần lớn trường hợp, **Math.abs(x)** trả về trị tuyệt đối như mong muốn. Tuy nhiên, nếu truyền đúng giá trị thấp nhất của kiểu số nguyên có dấu:

~~~java
int oldResult = Math.abs(Integer.MIN_VALUE);
long oldLongResult = Math.abs(Long.MIN_VALUE);
~~~

Kết quả tương ứng vẫn là **-2147483648** và **-9223372036854775808**. Phương thức **Math.abs(int/long) không ném ArithmeticException** trong trường hợp này; nó trả về giá trị âm ban đầu. Đây là hành vi được Java quy định, không phải lỗi của JVM.

Điều nguy hiểm là chương trình có thể tiếp tục dùng giá trị âm trong nơi giả định trị tuyệt đối luôn không âm, chẳng hạn tính điểm, đo độ lớn, sắp xếp hoặc kiểm tra ngưỡng.

### Math.absExact(int/long): báo lỗi khi trị tuyệt đối không biểu diễn được

**Math.absExact(x)** trả về trị tuyệt đối **nếu kết quả có thể biểu diễn đúng trong kiểu đầu vào**. Nếu kết quả dương vượt phạm vi đó, phương thức **ném ArithmeticException** ngay tại lời gọi:

~~~java
int a = Math.absExact(-25);    // 25
long b = Math.absExact(-25L);  // 25

// Hai lời gọi sau ném ArithmeticException:
Math.absExact(Integer.MIN_VALUE);
Math.absExact(Long.MIN_VALUE);
~~~

**Không có giá trị trả về** khi ngoại lệ được ném. Nếu không bắt ngoại lệ ở đây hoặc ở tầng gọi phía trên, luồng thực thi bình thường bị ngắt. Không nên mô tả phương thức như “trả về số âm rồi mới ném lỗi”.

Hai overload của Math.absExact chỉ nhận **int** hoặc **long**. Không có overload absExact dành riêng cho **float/double**; cũng không cần dùng phương thức này để giải quyết bài toán số thực theo cùng cơ chế.

## 3. Cơ chế gây ArithmeticException

Xét lời gọi:

~~~java
Math.absExact(Integer.MIN_VALUE);
~~~

Diễn biến logic:

1. Đầu vào là **-2.147.483.648**, nằm trong miền int hợp lệ.
2. Trị tuyệt đối toán học là **+2.147.483.648**.
3. Giá trị dương đó **lớn hơn Integer.MAX_VALUE**.
4. Không tồn tại kết quả kiểu int vừa **không âm** vừa **chính xác** cho phép tính này.
5. Math.absExact **ném ArithmeticException**, thay vì trả về một kết quả bị tràn.

Tương tự, **Math.absExact(Long.MIN_VALUE)** ném ngoại lệ vì **+9.223.372.036.854.775.808** lớn hơn Long.MAX_VALUE.

**ArithmeticException** là lớp ngoại lệ tổng quát cho các điều kiện số học bất thường, không chỉ phép chia nguyên cho 0. Trong bài này, nguyên nhân cụ thể là **trị tuyệt đối vượt phạm vi kiểu int/long**.

**Không phụ thuộc vào số liệu nhập từ đâu:** dù giá trị được khai báo trực tiếp, đọc từ tệp, lấy từ API, tính từ biểu thức hay nhận làm tham số, quy tắc vẫn giống nhau. Vấn đề nằm ở **giá trị số nguyên**, không nằm ở cách viết literal.

## 4. Các trường hợp biên phải ghi nhớ

| Biểu thức | Kết quả / hành vi |
| --- | --- |
| Math.absExact(-1) | 1 |
| Math.absExact(0) | 0 |
| Math.absExact(1) | 1 |
| Math.absExact(Integer.MAX_VALUE) | 2147483647 |
| Math.abs(Integer.MIN_VALUE) | -2147483648; không ném ngoại lệ |
| Math.absExact(Integer.MIN_VALUE) | ArithmeticException |
| Math.abs(Long.MIN_VALUE) | -9223372036854775808; không ném ngoại lệ |
| Math.absExact(Long.MIN_VALUE) | ArithmeticException |
| Math.absExact((long) Integer.MIN_VALUE) | 2147483648, vì kiểu long chứa được kết quả |

Điểm quan trọng: **ép kiểu sang long trước khi tính trị tuyệt đối** có thể giải quyết trường hợp Integer.MIN_VALUE, vì int có miền nhỏ hơn long.

~~~java
long correct = Math.absExact((long) Integer.MIN_VALUE); // 2147483648
long wrong = Math.abs(Integer.MIN_VALUE);               // -2147483648
~~~

Ở dòng thứ hai, Java thực hiện **Math.abs(int)** trước rồi mới gán kết quả int sang long. Giá trị đã sai trước phép chuyển kiểu, nên long chỉ nhận **-2147483648**. Không thể sửa tràn số bằng cách ép kiểu **sau** phép toán đã tràn.

Đối với **Long.MIN_VALUE**, không có kiểu số nguyên nguyên thủy có dấu rộng hơn long. Khi cần trị tuyệt đối chính xác cho giá trị đó, hãy dùng **BigInteger** hoặc biểu diễn dữ liệu khác phù hợp yêu cầu.

## 5. Chương trình Java 17+ hoàn chỉnh

Lưu tệp **AbsExactDemo.java**. Ví dụ cho thấy giá trị bình thường, hành vi khi tràn, bắt ngoại lệ, vấn đề ép kiểu trước/sau và cách lấy trị tuyệt đối chính xác bằng BigInteger.

~~~java
import java.math.BigInteger;

public class AbsExactDemo {
    public static void main(String[] args) {
        System.out.println("int thường: " + Math.absExact(-35));
        System.out.println("long thường: " + Math.absExact(-35L));
        System.out.println("zero: " + Math.absExact(0));

        System.out.println("Math.abs(int MIN): " + Math.abs(Integer.MIN_VALUE));
        try {
            Math.absExact(Integer.MIN_VALUE);
        } catch (ArithmeticException ex) {
            System.out.println("absExact(int MIN): ArithmeticException");
        }

        System.out.println("Math.abs(long MIN): " + Math.abs(Long.MIN_VALUE));
        try {
            Math.absExact(Long.MIN_VALUE);
        } catch (ArithmeticException ex) {
            System.out.println("absExact(long MIN): ArithmeticException");
        }

        long widenBefore = Math.absExact((long) Integer.MIN_VALUE);
        long widenAfter = Math.abs(Integer.MIN_VALUE);
        System.out.println("Ép sang long trước: " + widenBefore);
        System.out.println("Ép sang long sau: " + widenAfter);

        BigInteger large = BigInteger.valueOf(Long.MIN_VALUE).abs();
        System.out.println("BigInteger long MIN: " + large);
    }
}
~~~

Biên dịch và chạy bằng **JDK 17 trở lên**:

~~~bash
javac --release 17 -encoding UTF-8 AbsExactDemo.java
java AbsExactDemo
~~~

**Stdout chính xác:**

~~~text
int thường: 35
long thường: 35
zero: 0
Math.abs(int MIN): -2147483648
absExact(int MIN): ArithmeticException
Math.abs(long MIN): -9223372036854775808
absExact(long MIN): ArithmeticException
Ép sang long trước: 2147483648
Ép sang long sau: -2147483648
BigInteger long MIN: 9223372036854775808
~~~

Các câu lệnh bắt ngoại lệ **in thông báo tự định nghĩa**, tránh phụ thuộc vào chi tiết câu báo lỗi do phiên bản JDK tạo ra. Lệnh try không có giá trị trả về khi Math.absExact ném ArithmeticException, nên chương trình chuyển sang catch rồi tiếp tục thực hiện những dòng sau.

Mã đã được **biên dịch bằng javac --release 17 và chạy thành công trên JDK 24**; stdout đã được đối chiếu từng dòng.

## 6. Chọn cách xử lý phù hợp trong ứng dụng

### Phương án A: muốn phát hiện dữ liệu không biểu diễn được

Nếu nghiệp vụ yêu cầu trị tuyệt đối **vẫn thuộc kiểu int hoặc long**, dùng Math.absExact và chủ động xác định chính sách lỗi. Ví dụ:

~~~java
int magnitude(int value) {
    return Math.absExact(value);
}
~~~

Đây là **phương thức minh họa** đặt bên trong một lớp Java. Khi đầu vào là Integer.MIN_VALUE, ngoại lệ được truyền lên tầng gọi. Đây thường là lựa chọn đúng khi muốn phát hiện lỗi dữ liệu thay vì âm thầm dùng một con số sai.

Có thể bắt ngoại lệ ở **ranh giới nghiệp vụ** để trả về thông báo, mã lỗi hoặc từ chối tác vụ. **Không nên tự động trả về 0, Integer.MAX_VALUE hoặc Long.MAX_VALUE** nếu chưa có quy tắc nghiệp vụ rõ ràng: các giá trị thay thế làm mất thông tin về độ lớn thật.

Nếu muốn báo lỗi dễ hiểu cho người gọi API, có thể kiểm tra trực tiếp đầu vào trước:

~~~java
if (value == Integer.MIN_VALUE) {
    throw new IllegalArgumentException(
            "Không thể biểu diễn trị tuyệt đối trong int");
}
int positive = Math.absExact(value);
~~~

Đây cũng là **đoạn code minh họa trong phương thức có biến int value**. Một API có thể dùng IllegalArgumentException cho đầu vào không phù hợp; Math.absExact tự ném ArithmeticException khi thao tác số học không thể trả về kết quả chính xác. Chọn chính sách lỗi nhất quán theo hợp đồng API của dự án.

### Phương án B: cần độ lớn chính xác của một giá trị int

Nếu đầu ra có thể là **long**, chuyển kiểu trước rồi lấy trị tuyệt đối:

~~~java
int value = Integer.MIN_VALUE;
long magnitude = Math.absExact((long) value); // 2147483648
~~~

Mọi giá trị int đều có trị tuyệt đối biểu diễn được trong long, nên trường hợp trên cho kết quả chính xác. Đừng nhầm phép tính này với việc gán **Math.abs(value)** vào biến long sau khi Math.abs đã xử lý bằng overload int.

### Phương án C: cần độ lớn chính xác của một giá trị long

Dùng **java.math.BigInteger**, vì BigInteger có thể chứa số nguyên lớn hơn giới hạn long:

~~~java
long value = Long.MIN_VALUE;
BigInteger magnitude = BigInteger.valueOf(value).abs();
// magnitude = 9223372036854775808
~~~

BigInteger.abs() trả về một đối tượng BigInteger không âm. Đây là phép tính chính xác theo số nguyên, khác với việc ép sang double: với các số nguyên long lớn, double **không biểu diễn chính xác mọi giá trị** vì giới hạn độ chính xác của phần định trị.

Nếu hệ thống cần trả về BigInteger, hãy để kiểu trả về là BigInteger hoặc chuỗi thập phân; không tự chuyển ngược về long khi giá trị vượt Long.MAX_VALUE.

## 7. Cẩn thận: tràn số có thể xảy ra trước Math.absExact()

Math.absExact **chỉ kiểm tra phép lấy trị tuyệt đối của đối số đã được tính ra**. Nếu biểu thức sinh đối số đã bị tràn số, Math.absExact không nhất thiết nhận ra lỗi xảy ra trước đó.

Ví dụ: mã nằm trong một phương thức Java với hai biến int:

~~~java
int a = Integer.MAX_VALUE;
int b = Integer.MIN_VALUE;

// SAI: a - b tràn int trước; kết quả bị biến thành -1.
int incorrect = Math.absExact(a - b); // 1, không ném lỗi

// ĐÚNG nếu muốn kết quả kiểu long:
long correct = Math.absExact((long) a - b); // 4294967295
~~~

Giá trị toán học của a - b là **4.294.967.295**, vượt miền int nhưng vẫn nằm trong miền long. Ở biểu thức đầu, phép trừ int đã tràn thành -1; Math.absExact(-1) hợp lệ nên trả về 1, dù phép tính tổng thể sai. Ở biểu thức thứ hai, một toán hạng được đổi sang long **trước phép trừ**, nên phép trừ diễn ra trong long và cho kết quả đúng.

Nếu muốn báo lỗi thay vì tự mở rộng kiểu, dùng **Math.subtractExact(a, b)** để kiểm tra phép trừ. Có thể kết hợp Math.absExact(Math.subtractExact(a, b)), nhưng cả **phép trừ và phép lấy trị tuyệt đối** đều có khả năng ném ArithmeticException; cần xử lý hai bước theo nhu cầu ứng dụng.

Với **hai biến long**, phép trừ cũng có thể vượt miền long. Muốn đo khoảng cách toán học chính xác cho mọi cặp long, có thể dùng:

~~~java
BigInteger distance = BigInteger.valueOf(a)
        .subtract(BigInteger.valueOf(b))
        .abs();
~~~

Trong đoạn này, **a và b là hai biến long đang nằm trong một phương thức** và đã có import java.math.BigInteger. Không dùng phép trừ long trước rồi mới chuyển kết quả sang BigInteger vì lúc đó có thể đã tràn.

## 8. Bẫy thường gặp

1. **Tin rằng Math.abs(int/long) luôn không âm.** Với MIN_VALUE, hai overload này trả về chính giá trị âm nhỏ nhất. Dùng Math.absExact khi cần chắc chắn có kết quả đúng hoặc phát hiện tràn.
2. **Cho rằng ArithmeticException chỉ liên quan chia cho 0.** Math.absExact ném ngoại lệ này vì kết quả tuyệt đối không thể biểu diễn đúng, không có phép chia nào.
3. **Nhầm int MIN với int MAX.** Math.absExact(Integer.MAX_VALUE) hợp lệ; chỉ **Integer.MIN_VALUE** là biên gây ngoại lệ của overload int.
4. **Nhầm long MIN với int MIN.** Math.absExact((long) Integer.MIN_VALUE) hợp lệ; Math.absExact(Long.MIN_VALUE) ném ngoại lệ.
5. **Ép kiểu sau phép toán.** Gán Math.abs(Integer.MIN_VALUE) vào long vẫn giữ kết quả âm; phải mở rộng sang long trước khi gọi Math.abs/Math.absExact.
6. **Bắt ArithmeticException rồi bỏ qua không có quy tắc.** Việc thay thế bằng 0 hoặc một số bất kỳ có thể làm sai số liệu; cần xác định chính sách báo lỗi hoặc dùng kiểu rộng hơn.
7. **Chuyển sang double để chứa độ lớn long chính xác.** double không đủ độ chính xác cho mọi số nguyên long; dùng BigInteger nếu cần giá trị nguyên chính xác.
8. **Để phép cộng/trừ/nhân tràn trước khi gọi absExact.** Math.absExact không kiểm tra lịch sử tạo ra đối số. Cần mở rộng kiểu **trước phép tính**, dùng các hàm exact cho từng bước, hoặc BigInteger cho bài toán lớn.
9. **Viết mã chỉ chạy khi giá trị bình thường.** Test phải bao gồm ít nhất: giá trị âm bình thường, 0, MAX_VALUE và MIN_VALUE; với long cũng kiểm thử riêng các biên của long.
10. **Gán mọi số âm cho lỗi absExact.** Một số âm hợp lệ như -1, -35 hay Integer.MIN_VALUE + 1 đều lấy trị tuyệt đối chính xác được. Không nên từ chối toàn bộ số âm.

## 9. Tự kiểm tra

**Câu 1.** Vì sao Math.abs(Integer.MIN_VALUE) có thể cho kết quả âm?  
**Đáp án:** Trị tuyệt đối toán học là +2^31, lớn hơn Integer.MAX_VALUE = 2^31 - 1; phép lấy trị tuyệt đối trong int bị tràn.

**Câu 2.** Math.absExact(-100L) ném ngoại lệ không?  
**Đáp án:** Không. Nó trả về giá trị long 100.

**Câu 3.** Math.absExact(Long.MIN_VALUE) trả về gì?  
**Đáp án:** **Không trả về long**; nó ném ArithmeticException.

**Câu 4.** Muốn lấy trị tuyệt đối chính xác của Integer.MIN_VALUE, cho phép kết quả kiểu long, viết thế nào?  
**Đáp án:** Math.absExact((long) Integer.MIN_VALUE) trả về 2147483648.

**Câu 5.** Muốn kết quả chính xác cho Long.MIN_VALUE phải dùng gì?  
**Đáp án:** BigInteger.valueOf(Long.MIN_VALUE).abs() hoặc biểu diễn số nguyên lớn tương đương.

## 10. Ghi nhớ

- **Math.absExact(int/long)** trả về trị tuyệt đối chính xác khi còn nằm trong kiểu dữ liệu; nếu giá trị là **MIN_VALUE** tương ứng, nó **ném ArithmeticException**.
- **Math.abs(int/long)** có thể trả về **số âm** cho đúng trường hợp MIN_VALUE; nó không tự báo lỗi như Math.absExact.
- Muốn tính trị tuyệt đối của **int MIN** dưới dạng **long**, mở rộng kiểu **trước khi gọi** phép tính.
- Muốn biểu diễn độ lớn **long MIN** chính xác, dùng **BigInteger**.
- Math.absExact không ngăn tràn ở những phép toán đã thực hiện **trước** lời gọi. Luôn kiểm tra toàn bộ biểu thức, không chỉ phép abs.

## Tài liệu tham khảo

- Oracle, **Math.absExact(int) / Math.absExact(long)**, Java SE 21: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Math.html#absExact(int)
- Oracle, **Math.abs(int)**, Java SE 21: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Math.html#abs(int)
- Oracle, **BigInteger.abs()**, Java SE 21: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/math/BigInteger.html#abs()
