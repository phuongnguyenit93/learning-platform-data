# Vì sao phép cộng hoặc nhân tràn không tự ném ngoại lệ trong Java?

Với các kiểu số nguyên nguyên thủy `int` và `long`, **phép cộng `+`, phép trừ `-` và phép nhân `*` thông thường không tự ném ngoại lệ khi kết quả vượt phạm vi kiểu**. Java quy định kết quả được giữ lại theo số bit của kiểu; những bit cao vượt quá độ rộng bị loại bỏ, và dãy bit còn lại được diễn giải như một số nguyên có dấu. Vì vậy, giá trị có thể “quay vòng” từ lớn nhất sang nhỏ nhất hoặc ngược lại.

Ví dụ:

```java
int max = Integer.MAX_VALUE;        //  2_147_483_647
int wrapped = max + 1;              // -2_147_483_648
long large = Long.MAX_VALUE + 1L;   // Long.MIN_VALUE
```

Ba dòng trên là mảnh mã hợp lệ bên trong một phương thức Java. Không có `ArithmeticException` ở các phép cộng này. Đây là **hành vi được Java định nghĩa**, không phải hiện tượng phụ thuộc ngẫu nhiên vào CPU hay JVM.

Bài học thuộc nhóm **Tràn và kiểm tra biên** của **Java core – numbers**. Trọng tâm là lý do Java không báo lỗi ở toán tử số học nguyên bình thường, cách tràn xảy ra, khi nào exception thực sự xuất hiện, và cách thiết kế phép tính phải đúng về mặt nghiệp vụ.

## 1. Miền giá trị và tính toán với số bit cố định

Java có các kiểu nguyên thủy mang giá trị nguyên với độ rộng xác định:

| Kiểu | Độ rộng | Giá trị nhỏ nhất | Giá trị lớn nhất |
| --- | ---: | ---: | ---: |
| `byte` | 8 bit | -128 | 127 |
| `short` | 16 bit | -32.768 | 32.767 |
| `int` | 32 bit | -2.147.483.648 | 2.147.483.647 |
| `long` | 64 bit | -9.223.372.036.854.775.808 | 9.223.372.036.854.775.807 |

Các kiểu này có dấu. Số nguyên âm được biểu diễn theo **bù hai** (*two's complement*). Đối với phép cộng, trừ và nhân số nguyên, quy tắc giữ lại các bit thấp tương đương với thực hiện phép toán **theo modulo `2^32` đối với `int`**, hoặc **modulo `2^64` đối với `long`**, rồi diễn giải kết quả là số có dấu.

Có thể hình dung với 32 bit:

```text
Integer.MAX_VALUE  =  2_147_483_647
                   =  0x7FFF_FFFF

Cộng thêm 1:
                     0x7FFF_FFFF
                   + 0x0000_0001
                   = 0x8000_0000

0x8000_0000 dưới dạng int có dấu
                   = -2_147_483_648
                   = Integer.MIN_VALUE
```

Bit cao nhất là bit dấu trong biểu diễn bù hai. Sau khi cộng 1, dãy bit `1000...0000` biểu diễn số nguyên nhỏ nhất của `int`. Không có một “giá trị ngoài miền” được lưu trong biến `int`; phép toán đã tạo ra một kết quả **nằm trong miền bit của kiểu**, nhưng không còn bằng kết quả toán học mà người viết mong muốn.

### “Không có exception” là một phần của quy tắc ngôn ngữ

Java quy định hành vi tràn của các phép toán nguyên thông thường. Đây không phải tình trạng *undefined behavior* do trình biên dịch được quyền xử lý tùy ý. Cùng một biểu thức `Integer.MAX_VALUE + 1` sẽ có kết quả `Integer.MIN_VALUE` theo semantics Java.

Tuy nhiên, “hành vi xác định” **không đồng nghĩa** “kết quả có ý nghĩa với bài toán”. Một biến đếm số đơn hàng bất ngờ trở thành số âm vẫn là lỗi nghiêm trọng, dù JVM thực hiện đúng đặc tả.

## 2. Tại sao Java không kiểm tra tràn ở mỗi toán tử?

Về mặt thiết kế ngôn ngữ, các toán tử số học nguyên thông thường sử dụng quy tắc số nguyên độ rộng cố định. Phép toán không thực hiện phép kiểm tra giới hạn kèm theo để ném lỗi tràn. Việc tính toán theo dãy bit cố định tạo ra hành vi ổn định, tương thích với các phép toán bit và nhiều thuật toán làm việc với số nguyên.

Không nên diễn giải rằng “CPU không thể phát hiện tràn” hoặc “JVM luôn quá nhanh nên bỏ qua kiểm tra”. Một số kiến trúc phần cứng có cờ báo overflow, và Java có thư viện cho phép **yêu cầu kiểm tra tràn một cách tường minh**. Điểm quyết định là **ngữ nghĩa của toán tử Java `+`, `-`, `*` không yêu cầu phát sinh ngoại lệ khi tràn**, bất kể cách JVM biên dịch máy.

Do đó, hai hành vi sau cùng hợp lệ và có chủ đích:

```java
int a = Integer.MAX_VALUE;
int normal = a + 1;              // Trả Integer.MIN_VALUE.

int checked = Math.addExact(a, 1);
// Ném ArithmeticException vì kết quả toán học vượt miền int.
```

`Math.addExact` không thay đổi cơ chế của toán tử `+` trên toàn chương trình; nó là **một API khác** với hợp đồng phát hiện tràn. Người thiết kế phải chọn API hoặc mô hình dữ liệu phù hợp với ý nghĩa của phép tính.

## 3. Phép cộng, trừ và nhân đều có thể tràn mà không báo lỗi

### 3.1. Tràn khi cộng

```java
int next = Integer.MAX_VALUE + 1;
// next == Integer.MIN_VALUE

int belowMinimum = Integer.MIN_VALUE - 1;
// belowMinimum == Integer.MAX_VALUE
```

Ở ví dụ thứ hai là **tràn phía âm** (*underflow đối với miền số nguyên có dấu*), không phải hiện tượng underflow của số dấu phẩy động. Java không ném ngoại lệ cho phép trừ này.

### 3.2. Tràn khi nhân

Phép nhân có thể vượt miền ngay cả khi **cả hai toán hạng đều hợp lệ**:

```java
int records = 1_500_000_000;
int copies = 3;

int wrongTotal = records * copies; // 205_032_704
```

Kết quả toán học là `4_500_000_000`, nhưng `int` chỉ chứa được đến `2_147_483_647`. Vì:

```text
4_500_000_000 - 2^32
= 4_500_000_000 - 4_294_967_296
= 205_032_704
```

nên `wrongTotal` là `205_032_704`. Đây là ví dụ tràn số **mà kết quả vẫn dương và có vẻ hợp lý**. Không thể chỉ kiểm tra `result < 0` để phát hiện mọi phép nhân tràn.

Một ví dụ khác:

```java
int x = 50_000;
int square = x * x; // -1_794_967_296, không phải 2_500_000_000
```

Tràn có thể làm số dương thành âm hoặc thành một số dương sai. Cả hai đều có thể gây lỗi trong tính tiền, kích thước bộ đệm, tổng số lượng và kiểm tra giới hạn.

### 3.3. Đổi dấu và trường hợp số nguyên nhỏ nhất

Trong bù hai, miền âm của `int` có thêm một giá trị về độ lớn so với miền dương. Vì vậy:

```java
int min = Integer.MIN_VALUE;
int negated = -min;           // Vẫn là Integer.MIN_VALUE.
int absolute = Math.abs(min); // Vẫn là Integer.MIN_VALUE.
```

Giá trị toán học `2_147_483_648` không thể biểu diễn bằng `int`. Phép đổi dấu `-` thông thường không ném ngoại lệ. Khi phải phát hiện trường hợp này, dùng `Math.negateExact(min)` hoặc nâng kiểu trước khi đổi dấu:

```java
long positive = -(long) Integer.MIN_VALUE;
// 2_147_483_648L
```

Không nên áp dụng `Math.abs(int)` rồi mặc định kết quả không âm đối với mọi đầu vào.

## 4. Kiểu của biểu thức được xác định trước khi gán

Một bẫy đặc biệt phổ biến là nghĩ rằng gán kết quả vào biến `long` sẽ khiến mọi phép toán trước đó được tính như `long`. Java **xác định kiểu của biểu thức từ toán hạng trước khi phép tính xảy ra**.

```java
int amount = 1_500_000_000;

long tooLate = amount * 3;           // 205_032_704
long widenedFirst = (long) amount * 3; // 4_500_000_000
```

Ở `tooLate`, hai toán hạng của phép nhân là `int`, nên Java tính ra một kết quả `int` đã tràn; sau đó mới chuyển **kết quả sai** sang `long`. Biến `tooLate` lưu `205_032_704L`, không thể tự phục hồi `4_500_000_000L`.

Ở `widenedFirst`, phép ép `(long) amount` được thực hiện **trước phép nhân**. Một toán hạng `long` khiến phép toán được thực hiện ở `long`; trường hợp này nằm trong giới hạn 64 bit nên đúng.

Bẫy tương tự có thể xảy ra ngay với literal:

```java
long late = 2_000_000_000 * 2;     // -294_967_296L
long early = 2_000_000_000L * 2;  // 4_000_000_000L
```

Hậu tố `L` ở literal thay đổi **kiểu toán hạng**, không chỉ cách hiển thị. Nhưng `long` vẫn có giới hạn. Nếu kết quả toán học có thể vượt 64 bit, mở rộng từ `int` sang `long` chỉ trì hoãn vấn đề.

### Chú ý với byte, short, char và phép gán cộng

Trong biểu thức số học bình thường, các toán hạng `byte`, `short`, `char` thường được nâng lên `int`. Sau đó, phép gán hoặc ép kiểu trở lại kiểu nhỏ có thể loại bỏ bit cao:

```java
byte b = 127;
b++;                 // b trở thành -128 (ép về byte sau phép tăng).
// b = b + 1;        // Không biên dịch: biểu thức b + 1 có kiểu int.
b += 1;              // Hợp lệ: compound assignment có chuyển kiểu ngầm.
```

Đây là lý do `byte b = 127; b++;` quay về `-128` dù phép tính trung gian có thể được thực hiện ở `int`. Không có exception tự động khi kết quả bị thu hẹp trở lại.

### Chuỗi phép tính có thể tràn ở giữa

```java
int a = 1_500_000_000;
int b = 1_500_000_000;

long wrong = (a + b) / 2;        // Phép cộng int tràn trước.
long right = ((long) a + b) / 2; // Cộng long trước rồi chia.
```

Đừng chỉ nhìn giá trị đầu vào và kết quả cuối. Hãy kiểm tra **từng phép tính trung gian**: mỗi biểu thức con có kiểu gì, giới hạn nào và khi nào chuyển kiểu.

## 5. Exception nào thật sự có thể xảy ra trong số học nguyên?

Cần phân biệt **tràn số nguyên thông thường** với **chia cho 0** hoặc với lời gọi API kiểm tra.

| Phép toán | Khi vượt phạm vi hoặc gặp biên | Có tự ném `ArithmeticException` không? |
| --- | --- | --- |
| `int + int`, `long + long` | Tràn theo độ rộng kiểu | **Không** |
| `int - int`, `long - long` | Tràn theo độ rộng kiểu | **Không** |
| `int * int`, `long * long` | Tràn theo độ rộng kiểu | **Không** |
| `-Integer.MIN_VALUE` | Trả lại `Integer.MIN_VALUE` | **Không** |
| `Integer.MIN_VALUE / -1` | Thương nguyên tràn, trả `Integer.MIN_VALUE` | **Không** |
| `Integer.MIN_VALUE % -1` | Phần dư bằng `0` | **Không** |
| `a / 0` hoặc `a % 0` trên kiểu nguyên | Số chia bằng 0 | **Có**, khi được đánh giá |
| `Math.addExact`/`multiplyExact` | Kết quả toán học ngoài miền kiểu trả về | **Có** |
| `Math.toIntExact(long)` | Giá trị `long` ngoài miền `int` | **Có** |

**Trường hợp đặc biệt của phép chia:** phép chia `Integer.MIN_VALUE / -1` có thương toán học là `2_147_483_648`, vượt `int`, nhưng phép chia nguyên Java vẫn trả `Integer.MIN_VALUE` và không ném ngoại lệ; `Math.floorDiv` không phải một công cụ kiểm tra tràn. Nếu cần thương dương chính xác, nâng lên `long` **trước khi chia**:

```java
long exactQuotient = (long) Integer.MIN_VALUE / -1;
// 2_147_483_648L
```

Ngoài ra, số dấu phẩy động `double`/`float` có quy tắc khác: phép toán có thể tạo `Infinity` hoặc `NaN`; không thể áp dụng các kết luận tràn số nguyên từ bài này trực tiếp sang floating point.

## 6. Khi cần báo lỗi thay vì để toán tử quay vòng

Vì `+`, `-`, `*` nguyên thủy không tự kiểm tra overflow, ứng dụng cần chọn phương thức `Math.addExact`, `Math.subtractExact` hoặc `Math.multiplyExact` nếu muốn phép tính vượt miền ném `ArithmeticException`. Chẳng hạn `Math.multiplyExact(50_000, 50_000)` ném khi kết quả không vừa `int`, còn `Math.multiplyExact(50_000L, 50_000)` thành công với tích `long` 2.500.000.000.

Cần đặt kiểm tra **ở chính phép toán gây tràn**. Nếu tính `a * b` trước rồi truyền kết quả đã tràn vào `addExact`, API không phát hiện được lỗi trước đó. Các overload, trường hợp sát biên và chính sách xử lý exception được thực hành sâu trong bài riêng về ba phương thức `Exact`. Ở đây điều cốt lõi là phân biệt hợp đồng toán tử thường với API có kiểm tra, đồng thời kiểm tra miền nghiệp vụ riêng.

## 7. Khi kết quả cần vượt cả `long`

Nếu miền dữ liệu không thể giới hạn trong 64 bit, có thể chuyển **toán hạng** sang `BigInteger` trước khi cộng hoặc nhân: `BigInteger.valueOf(Long.MAX_VALUE).add(BigInteger.ONE)` cho chính xác 9223372036854775808. Ngược lại, `BigInteger.valueOf(Long.MAX_VALUE + 1)` giữ kết quả `long` đã tràn. `BigInteger` dùng các phương thức `add`, `multiply` và bị giới hạn bởi tài nguyên thực tế; bài cuối chương phân tích chi tiết việc lựa chọn, chuyển đổi và kiểm soát chi phí.

## 8. Chương trình Java 17+ chạy độc lập

Lưu chương trình sau thành **`OverflowDemo.java`**. Nó cho thấy phép cộng/nhân thông thường quay vòng, việc gán vào `long` quá muộn, checked arithmetic ném exception có chủ đích, phép đổi dấu ở giá trị nhỏ nhất, và cách `BigInteger` giữ được giá trị vượt `long`.

```java
import java.math.BigInteger;

public class OverflowDemo {
    public static void main(String[] args) {
        int max = Integer.MAX_VALUE;
        System.out.println("int-wrap=" + (max + 1));
        System.out.println("long-wrap=" + (Long.MAX_VALUE + 1L));

        int quantity = 1_500_000_000;
        long late = quantity * 3;
        long early = (long) quantity * 3;
        System.out.println("multiply-late=" + late);
        System.out.println("multiply-early=" + early);

        try {
            Math.addExact(max, 1);
        } catch (ArithmeticException ex) {
            System.out.println("add-exact=overflow");
        }

        try {
            Math.multiplyExact(quantity, 3);
        } catch (ArithmeticException ex) {
            System.out.println("multiply-exact=overflow");
        }

        System.out.println("checked-wide=" +
                Math.multiplyExact((long) quantity, 3L));

        byte small = 127;
        small++;
        System.out.println("byte-wrap=" + small);

        System.out.println("negate-min=" + (-Integer.MIN_VALUE));
        System.out.println("abs-min=" + Math.abs(Integer.MIN_VALUE));
        System.out.println("min-div=" + (Integer.MIN_VALUE / -1));
        System.out.println("min-rem=" + (Integer.MIN_VALUE % -1));
        System.out.println("wide-div=" + ((long) Integer.MIN_VALUE / -1));

        try {
            Math.toIntExact(2_147_483_648L);
        } catch (ArithmeticException ex) {
            System.out.println("to-int-exact=overflow");
        }

        BigInteger big = BigInteger.valueOf(Long.MAX_VALUE)
                .add(BigInteger.ONE);
        System.out.println("big-integer=" + big);
    }
}
```

Biên dịch và chạy bằng JDK 17 hoặc mới hơn:

```bash
javac OverflowDemo.java
java OverflowDemo
```

Stdout:

```text
int-wrap=-2147483648
long-wrap=-9223372036854775808
multiply-late=205032704
multiply-early=4500000000
add-exact=overflow
multiply-exact=overflow
checked-wide=4500000000
byte-wrap=-128
negate-min=-2147483648
abs-min=-2147483648
min-div=-2147483648
min-rem=0
wide-div=2147483648
to-int-exact=overflow
big-integer=9223372036854775808
```

Các phép toán tràn đầu tiên **không vào `catch`** vì không có exception để bắt. Chỉ các lời gọi có hợp đồng checked như `Math.addExact`, `Math.multiplyExact`, `Math.toIntExact` ném `ArithmeticException` ở những giá trị đã chọn. Một phép tính `long` phù hợp miền vẫn chạy được qua `Math.multiplyExact`.

## 9. Bẫy khi lập trình với dữ liệu thực

### 9.1. Kích thước cần cấp phát

Giả sử tính dung lượng `count * bytesPerRecord`. Nếu phép nhân `int` tràn và trở thành số âm/nhỏ hơn dự kiến, quá trình kiểm tra kích thước có thể bị vượt qua hoặc cấp phát sai. Trước khi tạo mảng, cần xác minh miền dữ liệu, tính kích thước bằng cách an toàn, và kiểm tra có thể biểu diễn bằng chỉ số mảng Java hay không.

```java
static int checkedArrayBytes(int count, int bytesPerItem) {
    if (count < 0 || bytesPerItem < 0) {
        throw new IllegalArgumentException("Values must be nonnegative");
    }
    return Math.multiplyExact(count, bytesPerItem);
}
```

Đây là một hàm minh họa: nó phát hiện tràn `int` và đầu vào âm. Việc mảng có thực sự cấp phát được hay không còn phụ thuộc giới hạn JVM/bộ nhớ và API nhận kích thước; kiểm tra tràn chỉ là **một điều kiện cần**, không bảo đảm cấp phát thành công.

### 9.2. Tính tiền bằng số nguyên đơn vị nhỏ nhất

Nếu lưu số cent trong `long`, việc tính `unitPriceCents * quantity` cần checked multiply khi dữ liệu có thể rất lớn:

```java
static long totalCents(long priceCents, int quantity) {
    if (priceCents < 0 || quantity < 0) {
        throw new IllegalArgumentException("Negative price/quantity");
    }
    return Math.multiplyExact(priceCents, (long) quantity);
}
```

Ví dụ giả định giá và số lượng không âm. Bài toán thực tế có thể có hoàn tiền hay điều chỉnh âm, nên ràng buộc miền phải do nghiệp vụ quyết định. Nếu giá trị vượt `long`, cân nhắc `BigInteger` hoặc cấu trúc nghiệp vụ khác; nếu dùng số thập phân, `BigDecimal` là một hướng thiết kế riêng.

### 9.3. Bộ đếm tăng liên tục

```java
int count = Integer.MAX_VALUE;
count++; // Trở thành Integer.MIN_VALUE.
```

Nếu biến là bộ đếm yêu cầu không giảm, việc quay vòng vi phạm bất biến. Dùng `Math.incrementExact(count)` để phát hiện, hoặc quy định bộ đếm thực sự dùng phép quay vòng và cách so sánh sau khi quay vòng.

Ngay cả `AtomicInteger.incrementAndGet()` cũng không mặc định ném ngoại lệ khi tràn: tính nguyên tử và **phát hiện tràn** là hai yêu cầu khác nhau. Với nhu cầu cập nhật nguyên tử **kèm phát hiện tràn**, có thể dùng hàm cập nhật với `Math.incrementExact` và kiểm thử quy tắc concurrency riêng.

### 9.4. Validation sau khi tràn có thể quá muộn

Một biểu thức như:

```java
int total = unitCount * unitSize;
if (total <= limit) {
    // ...
}
```

không chứng minh kích thước hợp lệ nếu `unitCount * unitSize` đã tràn. Việc so sánh có thể dựa trên kết quả sai. Cần xác thực đầu vào, chọn kiểu đủ lớn hoặc checked arithmetic **trước khi** dùng kết quả cho kiểm soát giới hạn.

## 10. Nhầm lẫn thường gặp

| Nhận định sai | Giải thích đúng |
| --- | --- |
| “Tràn `int` sẽ ném `ArithmeticException`.” | Các toán tử nguyên thông thường quay vòng theo số bit, không ném ngoại lệ do tràn. |
| “Java luôn bảo vệ số học nên không thể mất giá trị.” | An toàn bộ nhớ/kiểm tra chỉ số không thay thế kiểm tra kết quả toán học. |
| “Kết quả âm là cách phát hiện overflow.” | Nhân/cộng có thể tràn thành kết quả dương trông hợp lý. |
| “Gán sang `long` thì phép nhân sẽ là `long`.” | Kiểu của phép nhân dựa trên toán hạng; chuyển sau phép nhân có thể quá muộn. |
| “Cast sau phép tính sửa được kết quả.” | Giá trị đã tràn không thể khôi phục bằng cast. |
| “Dùng `long` là hết tràn.” | `long` cũng có biên ±9,22×10¹⁸; phép nhân có thể vượt biên. |
| “`Math.abs(x)` luôn không âm.” | `Math.abs(Integer.MIN_VALUE)` và tương đương `long` có ca biên tràn. |
| “`BigInteger.valueOf(a * b)` bảo vệ được phép nhân.” | Phải chuyển toán hạng trước khi thực hiện phép tính. |
| “`Math.addExact` xác minh mọi điều kiện nghiệp vụ.” | Nó chỉ phát hiện vượt miền kiểu; phải kiểm tra giới hạn và đơn vị riêng. |
| “Mọi `ArithmeticException` đều là overflow.” | Chia nguyên cho 0 cũng ném `ArithmeticException`; loại lỗi cần xét theo thao tác. |

### Tại sao không bật một cờ để mọi phép toán tự ném lỗi?

Trong Java thông thường, **không có chế độ ngôn ngữ mặc định** khiến toàn bộ toán tử `+`/`-`/`*` nguyên chuyển thành phép toán checked. Có thể chọn các phương thức `Math.*Exact`, xây abstraction, dùng static analysis hoặc thiết kế kiểu miền thích hợp. Khi yêu cầu đúng đắn đòi phát hiện overflow, cần đưa quyết định ấy vào code và test ở những điểm tính toán tương ứng.

## 11. Kiểm thử biên và checklist thiết kế

Một phép cộng/nhân trông đúng với số nhỏ chưa chứng minh được tính đúng đắn. Nên kiểm thử những vùng sau:

| Trường hợp | Điều cần xác minh |
| --- | --- |
| `Integer.MAX_VALUE + 1` | Phép `+` bình thường quay vòng; `Math.addExact` ném |
| `Integer.MIN_VALUE - 1` | Phép trừ bình thường quay vòng |
| `50_000 * 50_000` ở `int` | Nhân tràn dù toán hạng có vẻ nhỏ |
| `1_500_000_000 * 3` | Nhân tràn thành số dương sai |
| `(long) a * b` với kết quả nằm trong `long` | Nâng kiểu đúng thời điểm |
| `Long.MAX_VALUE + 1L` | `long` cũng có thể tràn |
| `-Integer.MIN_VALUE` và `Math.abs(Integer.MIN_VALUE)` | Ca biên đổi dấu không có số dương đối xứng |
| `Integer.MIN_VALUE / -1` | Thương tràn không ném, phần dư 0 |
| `a / 0`, `a % 0` | Phép chia nguyên cho 0 ném ngoại lệ |
| `Math.toIntExact((long) Integer.MAX_VALUE + 1)` | Thu hẹp có kiểm tra phải ném |
| `BigInteger.valueOf(a).multiply(BigInteger.valueOf(b))` | Chuyển toán hạng trước phép tính để giữ kết quả lớn |

**Checklist trước khi triển khai:**

1. Xác định miền đầu vào, giá trị lớn nhất/nhỏ nhất và các giá trị trung gian của từng biểu thức.
2. Quyết định overflow có được phép quay vòng theo thuật toán hay phải coi là lỗi.
3. Nếu phải phát hiện, sử dụng `Math.*Exact` hoặc phép tính trên `BigInteger` trước khi mất thông tin.
4. Kiểm soát chuyển kiểu: `(long) a * b` khác với `(long) (a * b)`.
5. Tách kiểm tra tràn khỏi kiểm tra nghiệp vụ như không âm, giới hạn cấp phát, đơn vị dữ liệu và quyền truy cập.
6. Thêm test tại `MIN_VALUE`, `MAX_VALUE`, tích gần giới hạn, và cả trường hợp tràn thành số **dương**.
7. Không dùng exception làm luồng điều khiển chính của dữ liệu bình thường nếu miền dữ liệu có thể xác định hợp lệ trước; chọn API và chính sách lỗi rõ ràng.

## 12. Câu hỏi tự luyện

1. Giải thích bằng bit vì sao `Integer.MAX_VALUE + 1` cho `Integer.MIN_VALUE`. Tại sao JVM không phải ném ngoại lệ?
2. Dự đoán `int x = 50_000 * 50_000;` và giải thích bằng cách lấy kết quả toán học theo modulo `2^32`.
3. Phân biệt `long a = 1_500_000_000 * 3;` và `long b = 1_500_000_000L * 3;`. Phép toán nào tính với `int`?
4. Viết `checkedTotalPriceCents(long unitPriceCents, int quantity)` có validation miền phù hợp và báo lỗi nếu phép nhân vượt `long`.
5. Vì sao phép `Math.abs(Integer.MIN_VALUE)` trả giá trị âm? Có hai cách nào để xử lý ý định lấy trị tuyệt đối: báo lỗi hoặc mở rộng kiểu?
6. Một ứng dụng sinh ID tuần tự bằng `AtomicInteger.incrementAndGet()`. Tính nguyên tử có đủ bảo đảm ID không trở thành âm ở biên `MAX_VALUE` không? Thiết kế cách kiểm tra.
7. Vì sao `BigInteger.valueOf(Long.MAX_VALUE * 2)` không cho kết quả đúng? Hãy viết cách tính giữ nguyên ý định.
8. Nêu khác biệt giữa overflow integer thông thường, chia số nguyên cho 0, và overflow được phát hiện bởi `Math.multiplyExact`: thao tác nào phát sinh exception, thao tác nào không?

## 13. Ghi nhớ

- **`+`, `-`, `*` trên số nguyên Java thông thường không ném ngoại lệ khi tràn**; kết quả được xác định theo độ rộng cố định của kiểu.
- Kết quả quay vòng có thể **âm hoặc dương**, nên dấu của kết quả không phải cách phát hiện tràn đáng tin cậy.
- **`Math.*Exact`** thực hiện phép toán hoặc chuyển kiểu với kiểm tra tràn và ném `ArithmeticException` khi không biểu diễn được.
- **Nâng kiểu trước phép toán**, không chỉ gán/ép kiểu sau khi kết quả đã bị tính sai.
- **`long` vẫn có giới hạn**; cần `BigInteger` khi yêu cầu toán học không nằm trong miền cố định.
- **Validation nghiệp vụ** và **checked arithmetic** bổ sung cho nhau: phép tính vừa phải đúng trong kiểu vừa phải có ý nghĩa trong miền dữ liệu.

Lý do Java không tự ném ngoại lệ khi cộng hoặc nhân tràn là vì **đó chính là quy tắc được định nghĩa cho các toán tử số học nguyên thông thường**. Khi một hệ thống không cho phép mất thông tin số học, người viết phải chủ động dùng kiểm tra tràn, kiểu đủ rộng và kiểm thử biên.
