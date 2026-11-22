# Chia số nguyên và cắt phần thập phân về phía không — Java 17+

## 1. Mục tiêu: hiểu đúng phép chia `/` trên số nguyên

Trong Java 17+, khi **hai toán hạng của `/` đều thuộc kiểu số nguyên** (`byte`, `short`, `char`, `int`, `long` sau các quy tắc nâng kiểu), kết quả là một **thương số nguyên**. Java lấy phần nguyên của thương toán học bằng cách **cắt phần thập phân theo hướng về 0** (*truncation toward zero*).

~~~java
int a = 7;
int b = 2;

int quotient = a / b;
System.out.println(quotient); // 3
~~~

Về mặt toán học, `7 / 2 = 3.5`; phép chia nguyên trả **3** vì phần `.5` bị loại. Nếu dấu thay đổi:

~~~java
System.out.println(-7 / 2);  // -3, không phải -4
System.out.println(7 / -2);  // -3
System.out.println(-7 / -2); // 3
~~~

Với số âm, “cắt về 0” khác với “làm tròn xuống”:

- `-3.5` cắt về 0 → `-3`.
- `-3.5` làm tròn xuống theo trục số → `-4`.

**Ý chính:** `/` trên hai số nguyên **không tự tính số thực**, không làm tròn gần nhất và không phải `Math.floor`. Muốn kết quả có phần lẻ, phải sử dụng ít nhất một toán hạng dấu phẩy động **trước phép chia**.

## 2. Quy tắc dấu và các ví dụ cơ bản

| Biểu thức Java | Thương số học chính xác | Kết quả chia nguyên | Giải thích |
|---|---:|---:|---|
| `7 / 2` | 3.5 | `3` | Bỏ .5 về 0 |
| `-7 / 2` | -3.5 | `-3` | Bỏ -.5 về 0, không thành -4 |
| `7 / -2` | -3.5 | `-3` | Một dấu âm |
| `-7 / -2` | 3.5 | `3` | Hai dấu âm |
| `-1 / 2` | -0.5 | `0` | `int` không có âm 0 |
| `1 / -2` | -0.5 | `0` | Cắt về 0 |
| `8 / 2` | 4 | `4` | Chia hết |
| `0 / 3` | 0 | `0` | Số bị chia là 0, mẫu khác 0 |

Dấu của **thương khác 0** là âm khi hai toán hạng trái dấu, dương khi cùng dấu. Nếu độ lớn thương nhỏ hơn 1, kết quả nguyên là 0 bất kể dấu số học; Java không có `-0` trong `int` hoặc `long`.

### Không hiểu “cắt phần thập phân” là thao tác trên chuỗi

Phép `7 / 2` hoạt động ở mức **quy tắc số học của ngôn ngữ**, không phải biến `3.5` thành một chuỗi rồi xóa ký tự `.5`. Giá trị trung gian không cần tồn tại dưới dạng `double`:

~~~java
var result = 7 / 2; // result có kiểu int và giá trị 3
~~~

Dùng `var` không đổi kiểu của biểu thức chia.

## 3. Kiểu của toán hạng quyết định kiểu kết quả

| Toán hạng | Biểu thức | Kiểu kết quả | Ví dụ |
|---|---|---|---|
| `int` và `int` | `7 / 2` | `int` | `3` |
| `long` và `int` | `7L / 2` | `long` | `3L` |
| `int` và `long` | `7 / 2L` | `long` | `3L` |
| `float` và `int` | `7f / 2` | `float` | `3.5f` |
| `double` và `int` | `7.0 / 2` | `double` | `3.5` |
| `int` và `double` | `7 / 2.0` | `double` | `3.5` |

Trong Java, `byte`, `short` và `char` được **nâng lên `int`** khi tham gia phép chia số học thông thường:

~~~java
byte first = 9;
short second = 2;

int quotient = first / second; // Kết quả biểu thức là int
System.out.println(quotient); // 4

// byte wrong = first / second; // Lỗi compile: int không tự gán về byte
~~~

Vì sao? Quy tắc *binary numeric promotion* áp dụng trước khi phép `/` được thực hiện. Đừng suy kiểu biểu thức từ kiểu biến nhận hoặc từ việc kết quả tình cờ vừa miền `byte`.

**`boolean` không thể dùng với phép chia.** Các wrapper như `Integer`, `Long` có thể được **unbox** trong phép toán số học; nếu wrapper là `null`, quá trình unboxing có thể ném `NullPointerException` trước khi chia.

## 4. Kiểu biến nhận không thay đổi thương đã tính

~~~java
int numerator = 7, denominator = 2;
double assignedAfter = numerator / denominator;       // 3.0
double castAfter = (double) (numerator / denominator); // 3.0
double castBefore = (double) numerator / denominator;  // 3.5
~~~

Hai dòng đầu dùng phép chia `int / int`, nên phần lẻ đã mất trước khi gán hoặc ép kiểu kết quả. Dòng cuối chuyển **toán hạng trước `/`**, do đó là phép chia số thực. Bài kế tiếp đi sâu vào vị trí cast, kiểu kết quả và giới hạn độ chính xác; trọng tâm ở đây là nhận ra bước **cắt thương về 0**.

## 5. Phần dư là dấu vết của thương cắt về 0

Với `b != 0`, thương nguyên `q = a / b` và dư `r = a % b` thỏa quan hệ toán học `a = q * b + r`. Chẳng hạn `-7 / 2` bằng `-3`, nên `-7 % 2` bằng `-1`: `-7 = (-3) * 2 + (-1)`.

~~~java
System.out.println(-7 / 2); // -3
System.out.println(-7 % 2); // -1
~~~

Phần dư nguyên khác 0 cùng dấu với **số bị chia**. Bài về dấu của phần dư phân tích đầy đủ bốn cặp dấu, `Math.floorMod` và các trường hợp biên.

## 6. `Math.floorDiv`: khác chia nguyên ở số âm

Java 17 có `Math.floorDiv(int, int)` và `Math.floorDiv(long, long)` cùng các overload liên quan. Khác `/` là cắt thương về 0, **`Math.floorDiv` làm tròn thương toán học xuống âm vô cực**.

~~~java
System.out.println(-7 / 2);           // -3
System.out.println(Math.floorDiv(-7, 2)); // -4

System.out.println(7 / -2);           // -3
System.out.println(Math.floorDiv(7, -2)); // -4
~~~

| Cặp số | `a / b` (cắt về 0) | `Math.floorDiv(a,b)` (floor) |
|---|---:|---:|
| 7, 2 | 3 | 3 |
| -7, 2 | -3 | -4 |
| 7, -2 | -3 | -4 |
| -7, -2 | 3 | 3 |
| -1, 2 | 0 | -1 |

Muốn cặp **thương floor và phần dư tương thích**, dùng `Math.floorMod`:

~~~java
int a = -7;
int b = 2;

int q = Math.floorDiv(a, b); // -4
int r = Math.floorMod(a, b); // 1

System.out.println(q * b + r); // -7
~~~

Với số chia **dương**, `Math.floorMod` cho dư **không âm**. Khi số chia âm, kết quả `floorMod` có thể âm; **không nên khái quát** rằng hàm này luôn trả số không âm.

**Chọn quy tắc theo nghiệp vụ:** đếm số phần đầy đủ khi giá trị âm có thể phát sinh, chia thời gian thành các khoảng âm hoặc chuẩn hóa chỉ số là những trường hợp cần cân nhắc `floorDiv`/`floorMod`. Với phép chia nguyên thông thường của Java, toán tử `/` dùng quy tắc cắt về 0.

## 7. Dấu ngoặc và tính kết hợp của `/`

Các toán tử `*`, `/`, `%` cùng nhóm ưu tiên và **kết hợp từ trái sang phải**:

~~~java
System.out.println(20 / 3 / 2);   // 3: (20 / 3) / 2
System.out.println(20 / (3 / 2)); // 20: 20 / 1
~~~

Chú ý mỗi lần chia nguyên đều cắt phần lẻ:

- `20 / 3 / 2`: `20 / 3 = 6`, rồi `6 / 2 = 3`.
- `20 / (3 / 2)`: `3 / 2 = 1`, rồi `20 / 1 = 20`.

**Không thể tùy ý chuyển ngoặc** trong chuỗi phép chia nguyên. Cách nhóm quyết định vị trí mất phần lẻ và do đó thay đổi kết quả.

Trong công thức nghiệp vụ có nhiều lần chia, hãy đặt tên biến trung gian hoặc ghi ngoặc thể hiện ý nghĩa của từng bước.

## 8. Giới hạn: chia nguyên cho 0

Cả `/` và `%` trên số nguyên đều ném `ArithmeticException` khi số chia bằng `0`. Với `double`, `7.0 / 0.0` lại cho `Infinity`, còn `0.0 / 0.0` cho `NaN`; đây **không** phải thương nguyên hợp lệ. Hãy kiểm tra mẫu số trước phép chia nếu mẫu đến từ đầu vào và cần kết quả hữu hạn hoặc có hợp đồng lỗi rõ ràng. Bài chuyên chia cho 0 phân tích cách guard, `OptionalInt`, unboxing và tác dụng phụ.

## 9. Ngoại lệ biên: `MIN_VALUE / -1`

Thương toán học của `Integer.MIN_VALUE / -1` vượt miền `int`, nhưng Java trả `-2147483648` và **không ném ngoại lệ**:

~~~java
System.out.println(Integer.MIN_VALUE / -1);          // -2147483648
System.out.println(((long) Integer.MIN_VALUE) / -1); // 2147483648
~~~

`Long.MIN_VALUE / -1L` cũng tràn miền `long`; muốn giá trị toán học cần kiểu lớn hơn như `BigInteger`. `Math.floorDiv` không phải phép kiểm tra tràn. Bài về tràn số tập trung vào `Math.*Exact`, mở rộng toán hạng đúng lúc và kiểm tra miền.

## 10. Viết hàm chia nguyên có kiểm tra cho nghiệp vụ

Hàm minh họa dưới đây **không chấp nhận** chia cho 0 hoặc tràn `int`:

~~~java
static int divideChecked(int a, int b) {
    if (b == 0) {
        throw new IllegalArgumentException("zero divisor");
    }
    if (a == Integer.MIN_VALUE && b == -1) {
        throw new ArithmeticException("int quotient overflow");
    }
    return a / b;
}
~~~

Kiểm tra `b == 0` là cần thiết vì phép chia nguyên Java ném exception; kiểm tra `MIN_VALUE/-1` là cần thiết **nếu yêu cầu không được âm thầm overflow**.

Tùy API, bạn có thể để `ArithmeticException` tự phát sinh với mẫu số 0, nhưng nên **viết rõ hợp đồng** mà caller có thể dựa vào. Ví dụ trên cố ý ném `IllegalArgumentException` cho đầu vào mẫu số 0 để mô tả yêu cầu dữ liệu.

Nếu nghiệp vụ cho phép trường hợp `MIN_VALUE/-1` theo đúng hành vi tràn Java, không cần hàm riêng; hãy hiểu rõ lựa chọn đó và tránh giả định thương luôn bằng thương toán học chính xác.

## 11. `>>` không phải chia cho lũy thừa 2 trong mọi trường hợp âm

Với số nguyên **không âm**, dịch phải số học một bit thường cho giá trị giống chia nguyên cho 2:

~~~java
System.out.println(7 / 2);  // 3
System.out.println(7 >> 1); // 3
~~~

Nhưng số âm cho kết quả khác:

~~~java
System.out.println(-7 / 2);  // -3: cắt về 0
System.out.println(-7 >> 1); // -4: dịch bit giữ dấu
~~~

Vì `>>` là phép toán dịch bit và không áp dụng quy tắc cắt thương về 0 như `/`. **Đừng thay `x / 2` bằng `x >> 1` khi `x` có thể âm** chỉ với giả định đây là một tối ưu tương đương.

Các JIT hiện đại có thể tối ưu phép chia khi an toàn, nhưng tiêu chí chọn toán tử trong source phải là **ngữ nghĩa đúng**, không phải đoán tốc độ.

## 12. Phép gán kết hợp `/=` và kiểu biểu thức

~~~java
int count = 20;
count /= 3;
System.out.println(count); // 6
~~~

Với kiểu `int`, `count /= 3` cập nhật `count` bằng kết quả chia nguyên `20 / 3 = 6`. Phép gán kết hợp cũng là một biểu thức có tác dụng phụ, nhưng viết `count /= 3;` riêng thường dễ hiểu.

Với toán hạng nhỏ như `byte`:

~~~java
byte value = 9;
value /= 2;
System.out.println(value); // 4
~~~

Lệnh trên **biên dịch**, dù phép `value / 2` được nâng kiểu thành `int`, bởi compound assignment áp dụng chuyển đổi về kiểu biến nhận. Ngược lại:

~~~java
byte value = 9;
// value = value / 2; // Lỗi compile: kết quả chia là int
~~~

Khi sử dụng `/=`, vẫn cần chú ý phép chia cho 0 và các trường hợp mất dữ liệu khi chuyển về kiểu biến đích; cú pháp ngắn hơn không phải cơ chế validation.

## 13. Ứng dụng: chia thành nhóm đầy đủ và phần còn lại

Một ứng dụng gần gũi là chia **11 mục** thành các nhóm chứa tối đa **5 mục**, với `items >= 0`, `size > 0`:

~~~java
int items = 11;
int size = 5;

int fullGroups = items / size;
int remaining = items % size;
int totalGroups = fullGroups + (remaining == 0 ? 0 : 1);

System.out.println(fullGroups); // 2
System.out.println(remaining);  // 1
System.out.println(totalGroups); // 3
~~~

Giải thích: có 2 nhóm đầy đủ, còn dư 1 mục cần thêm 1 nhóm. Công thức này không tự áp dụng cho mọi cách chia có thể có dữ liệu âm, vì **ý nghĩa của nhóm âm và làm tròn số nhóm** cần được định nghĩa riêng.

Trước khi dùng `totalGroups` làm kích thước mảng hoặc số lượt xử lý, hãy đảm bảo miền hợp lệ (`items >= 0`, `size > 0`) và xét giới hạn integer nếu tính toán lớn.

## 14. Chương trình Java 17 hoàn chỉnh, chạy độc lập

Tạo file đúng tên **`IntegerDivisionDemo.java`**:

~~~java
import java.math.BigInteger;

public final class IntegerDivisionDemo {
    private IntegerDivisionDemo() {}

    static void showPair(int a, int b) {
        System.out.println("pair " + a + "/" + b
                + ": q=" + (a / b) + ", r=" + (a % b));
    }

    static int divideChecked(int a, int b) {
        if (b == 0) {
            throw new IllegalArgumentException("zero divisor");
        }
        if (a == Integer.MIN_VALUE && b == -1) {
            throw new ArithmeticException("int quotient overflow");
        }
        return a / b;
    }

    public static void main(String[] args) {
        showPair(7, 2);
        showPair(-7, 2);
        showPair(7, -2);
        showPair(-7, -2);
        showPair(-1, 2);

        System.out.println("int result=" + (7 / 2));
        System.out.println("widen after=" + ((double) (7 / 2)));
        System.out.println("double first=" + (((double) 7) / 2));
        System.out.println("double literal=" + (7 / 2.0));
        System.out.println("long operands=" + (7L / 2));

        byte a = 9;
        short b = 2;
        var inferred = a / b;
        System.out.println("byte/short promoted=" + inferred);

        System.out.println("remainder negative=" + (-7 % 2));
        System.out.println("identity=" + ((-7 / 2) * 2 + (-7 % 2)));
        System.out.println("floorDiv=" + Math.floorDiv(-7, 2));
        System.out.println("floorMod=" + Math.floorMod(-7, 2));
        System.out.println("floor reconstructed="
                + (Math.floorDiv(-7, 2) * 2 + Math.floorMod(-7, 2)));

        System.out.println("group left=" + (20 / 3 / 2));
        System.out.println("group right=" + (20 / (3 / 2)));
        System.out.println("shift positive=" + (7 >> 1));
        System.out.println("shift negative=" + (-7 >> 1));
        System.out.println("divide negative=" + (-7 / 2));

        int count = 20;
        count /= 3;
        System.out.println("compound int=" + count);
        byte small = 9;
        small /= 2;
        System.out.println("compound byte=" + small);

        System.out.println("min int / -1=" + (Integer.MIN_VALUE / -1));
        System.out.println("min int widened="
                + (((long) Integer.MIN_VALUE) / -1));
        System.out.println("min long / -1=" + (Long.MIN_VALUE / -1L));
        BigInteger exactLong = BigInteger.valueOf(Long.MIN_VALUE)
                .divide(BigInteger.valueOf(-1));
        System.out.println("min long BigInteger=" + exactLong);

        int zero = 0;
        try {
            int impossible = 7 / zero;
            System.out.println(impossible);
        } catch (ArithmeticException ex) {
            System.out.println("plain zero=ArithmeticException");
        }
        try {
            divideChecked(7, 0);
        } catch (IllegalArgumentException ex) {
            System.out.println("checked zero=" + ex.getMessage());
        }
        try {
            divideChecked(Integer.MIN_VALUE, -1);
        } catch (ArithmeticException ex) {
            System.out.println("checked overflow=" + ex.getMessage());
        }
        System.out.println("checked normal=" + divideChecked(-7, 2));

        System.out.println("floating / zero=" + (7.0 / 0.0));
        System.out.println("floating 0 / 0=" + (0.0 / 0.0));

        int items = 11;
        int size = 5;
        int full = items / size;
        int remaining = items % size;
        int groups = full + (remaining == 0 ? 0 : 1);
        System.out.println("full groups=" + full);
        System.out.println("remaining=" + remaining);
        System.out.println("total groups=" + groups);
    }
}
~~~

Yêu cầu **JDK 17 hoặc mới hơn** và terminal đang ở thư mục chứa `IntegerDivisionDemo.java`. Không cần Maven, Gradle hay thư viện bên ngoài JDK.

**Bash (Linux/macOS):**

~~~bash
javac --release 17 -encoding UTF-8 IntegerDivisionDemo.java
java -cp . IntegerDivisionDemo
~~~

**PowerShell (Windows):**

~~~powershell
javac --release 17 -encoding UTF-8 .\IntegerDivisionDemo.java
java -cp . IntegerDivisionDemo
~~~

**Expected output chính xác:**

~~~text
pair 7/2: q=3, r=1
pair -7/2: q=-3, r=-1
pair 7/-2: q=-3, r=1
pair -7/-2: q=3, r=-1
pair -1/2: q=0, r=-1
int result=3
widen after=3.0
double first=3.5
double literal=3.5
long operands=3
byte/short promoted=4
remainder negative=-1
identity=-7
floorDiv=-4
floorMod=1
floor reconstructed=-7
group left=3
group right=20
shift positive=3
shift negative=-4
divide negative=-3
compound int=6
compound byte=4
min int / -1=-2147483648
min int widened=2147483648
min long / -1=-9223372036854775808
min long BigInteger=9223372036854775808
plain zero=ArithmeticException
checked zero=zero divisor
checked overflow=int quotient overflow
checked normal=-3
floating / zero=Infinity
floating 0 / 0=NaN
full groups=2
remaining=1
total groups=3
~~~

**Cách đối chiếu kết quả:**

1. Các dòng `pair` cho thấy thương **cắt về 0** và số dư **theo dấu số bị chia**.
2. `widen after` khác `double first`: chuyển kiểu **sau** chia không khôi phục phần lẻ.
3. `byte/short promoted` cho thấy hai toán hạng nhỏ vẫn tạo kết quả phép chia `int`.
4. `floorDiv`/`floorMod` khác `/`/`%` ở số âm, nhưng vẫn tái tạo đúng -7 trong ví dụ.
5. Hai nhóm `20 / 3 / 2` và `20 / (3 / 2)` khác nhau vì chia nguyên cắt sau **mỗi bước**.
6. Dịch bit `-7 >> 1` cho -4, khác `-7 / 2` cho -3.
7. Trường hợp `MIN_VALUE/-1` tràn mà Java **không tự ném exception**; hàm `divideChecked` chủ động phát hiện tràn.
8. Chia cho 0 kiểu nguyên ném exception; kiểu `double` cho Infinity hoặc NaN theo quy tắc số thực.
9. Phần chia nhóm cuối áp dụng cả thương và dư cho dữ liệu không âm.

## 15. Lỗi thường gặp

| Cách viết/ngộ nhận | Vì sao sai? | Hướng xử lý |
|---|---|---|
| `7 / 2` cho 3.5 | Hai toán hạng `int`; chia nguyên | Dùng `7.0 / 2` nếu muốn số thực |
| `double d = 7 / 2;` cho 3.5 | 3 được tạo ra trước rồi mới mở rộng | Cast một toán hạng **trước khi chia** |
| `(double)(7 / 2)` khôi phục .5 | Cast sau khi đã cắt | `((double)7)/2` |
| `-7 / 2` cho -4 | Java cắt về 0, không floor | Dùng `Math.floorDiv(-7, 2)` nếu cần floor |
| `-7 % 2` cho 1 | Dư Java theo dấu số bị chia | Dùng `Math.floorMod` nếu muốn dư không âm với mẫu dương |
| `20 / 3 / 2` luôn như `20 / (3/2)` | Chia nguyên và grouping khác | Giữ ngoặc có chủ đích |
| `long q = intA / intB` luôn chính xác trong long | Phép chia diễn ra trong int trước | Cast một toán hạng sang long khi cần |
| `byte q = byteA / byteB;` | Numeric promotion cho kết quả int | Nhận int hoặc cast có kiểm tra |
| `int q = 7 / 0` cho Infinity | Chia nguyên mẫu 0 ném exception | Kiểm tra mẫu, xử lý lỗi |
| `Integer.MIN_VALUE / -1` ném overflow | Java trả MIN_VALUE khi thương không vừa int | Kiểm tra riêng, dùng long khi thích hợp |
| `Long.MIN_VALUE / -1L` xử lý được bằng long | Thương dương vượt miền long | Dùng `BigInteger` khi cần giá trị exact |
| `x >> 1` luôn tương đương `x / 2` | Số âm có quy tắc khác | Giữ `/` nếu cần cắt về 0 |
| `value /= 2` luôn không mất thông tin | Chia nguyên và compound conversion có thể giảm giá trị | Xác nhận nghiệp vụ trước |
| Chia nhóm với `size = 0` | Mẫu số 0 | Validate `size > 0` |

**Mẹo debug:** luôn hỏi **toán hạng có kiểu gì → phép chia thuộc loại nào → dấu của số → mất phần lẻ ở bước nào → mẫu số có bằng 0 → thương có vượt miền?**

## 16. Bài tập có đáp án

### Bài A — số âm và dư

~~~java
System.out.println(-11 / 4);
System.out.println(-11 % 4);
~~~

**Đáp án:**

~~~text
-2
-3
~~~

Thương -2 vì cắt -2.75 về 0; dư -3 vì `-11 = (-2)*4 + (-3)`.

### Bài B — chia nguyên và chia thực

~~~java
int a = 9, b = 4;
double x = a / b;
double y = ((double) a) / b;
System.out.println(x);
System.out.println(y);
~~~

**Đáp án:**

~~~text
2.0
2.25
~~~

### Bài C — kiểm tra `floorDiv`

~~~java
System.out.println(-11 / 4);
System.out.println(Math.floorDiv(-11, 4));
System.out.println(Math.floorMod(-11, 4));
~~~

**Đáp án:**

~~~text
-2
-3
1
~~~

Vì `-11 = -3 * 4 + 1`.

### Bài D — kiểu biểu thức

~~~java
short a = 9;
short b = 2;
var q = a / b;
System.out.println(q);
~~~

**Đáp án:** in `4`, và `q` có kiểu **int**, không phải short.

### Bài E — chia cho 0

~~~java
int denominator = 0;
// int result = 9 / denominator;
~~~

**Đáp án:** nếu chạy dòng comment, xảy ra `ArithmeticException` trong phép chia nguyên. Phải validate mẫu số trước; không có infinity kiểu `int`.

### Bài F — overflow ở ranh giới

~~~java
int a = Integer.MIN_VALUE;
int result = a / -1;
System.out.println(result);
~~~

**Đáp án:** `-2147483648`, không ném exception. Nếu muốn thương chính xác, dùng `((long) a) / -1` để nhận `2147483648`.

### Bài G — chia thành nhóm

Có 14 vật phẩm và mỗi hộp chứa tối đa 6 vật phẩm. Tính số hộp đầy đủ, số vật phẩm còn lại, và số hộp cần dùng (dữ liệu không âm, sức chứa dương).

**Đáp án:**

~~~java
int items = 14, capacity = 6;
int full = items / capacity;  // 2
int rest = items % capacity;  // 2
int boxes = full + (rest == 0 ? 0 : 1); // 3
~~~

## 17. Checklist và kết luận

- [ ] Biết hai số nguyên chia nhau trả thương nguyên, cắt phần lẻ **về 0**.
- [ ] Phân biệt cắt về 0 với `Math.floorDiv` ở số âm.
- [ ] Biết dấu của thương và vì sao `-1 / 2 == 0`.
- [ ] Hiểu `int / int` được thực hiện trước khi gán vào `double`.
- [ ] Biết đổi một toán hạng sang `double` trước khi chia nếu cần số thực.
- [ ] Biết `byte`/`short`/`char` được nâng lên `int` trong phép chia.
- [ ] Nhớ quy tắc số dư `%` và mối liên hệ thương–dư.
- [ ] Phân biệt `Math.floorMod` với `%` ở dữ liệu âm.
- [ ] Biết dấu ngoặc làm thay đổi kết quả khi nhóm nhiều phép chia nguyên.
- [ ] Kiểm tra mẫu số khác 0 trước khi chia nguyên nếu cần xử lý chủ động.
- [ ] Hiểu trường hợp `Integer.MIN_VALUE / -1` và `Long.MIN_VALUE / -1L`.
- [ ] Không thay chia `/2` bằng dịch phải `>>1` nếu có số âm.
- [ ] Biết `/=` có thể thực hiện phép chia và chuyển kiểu ở biến đích.
- [ ] Chạy `IntegerDivisionDemo.java` bằng Java 17+ và so từng dòng expected output.

**Kết luận:** Toán tử `/` trên kiểu nguyên trong Java 17+ **cắt thương về 0**, kể cả khi một toán hạng âm. Muốn làm tròn xuống dùng `Math.floorDiv`; muốn giữ phần lẻ phải chọn toán hạng dấu phẩy động trước khi chia. Kết hợp hiểu đúng `%`, kiểu của biểu thức, chia cho 0 và trường hợp tràn `MIN_VALUE / -1` sẽ giúp bạn viết phép chia số nguyên chính xác, dự đoán được và an toàn theo yêu cầu nghiệp vụ.