# Mở rộng số nguyên sang số thực vẫn có thể mất độ chính xác

> **Java core — language-basics / Chuyển đổi kiểu**  
> **Môi trường:** JDK 17+; chỉ dùng thư viện chuẩn.  
> **Mục tiêu:** Hiểu tại sao `int → float` và `long → double` là các phép chuyển kiểu mở rộng hợp lệ nhưng có thể làm tròn mất dữ liệu. Biết ngưỡng chính xác 24/53 bit, nguy cơ so sánh hỗn hợp và cách xử lý giá trị nguyên cần giữ tuyệt đối.

## 1. Mở rộng kiểu không bảo đảm giữ nguyên giá trị

Java cho phép chuyển số nguyên sang số thực mà không cần ép kiểu:

~~~java
int count = 123;
float f = count;   // Hợp lệ.
double d = count;  // Hợp lệ.

long id = 9_007_199_254_740_993L;
double approximateId = id; // Hợp lệ, nhưng có thể mất chính xác.
~~~

`int` và `long` biểu diễn chính xác từng số nguyên trong miền có dấu của chúng. `float` và `double` biểu diễn số thực dạng nhị phân IEEE 754. Chúng có miền độ lớn rất rộng nhưng phần trị chỉ có số bit chính xác hữu hạn:

- **`float`:** 24 bit chính xác phần trị, tính cả bit dẫn đầu của số chuẩn hóa.
- **`double`:** 53 bit chính xác phần trị.
- **`int`:** 32 bit có dấu; **`long`:** 64 bit có dấu.

Khi số nguyên không biểu diễn chính xác được bằng kiểu số thực đích, Java làm tròn sang một giá trị số thực có thể biểu diễn; với trường hợp chính giữa hai giá trị, phép chuyển đổi chọn giá trị có bit cuối phần trị chẵn (*round to nearest, ties to even*).

**Chuyển kiểu widening** nghĩa là chuyển đổi được ngôn ngữ cho phép mà không cần cast. Nó **không** có nghĩa luôn giữ được mọi chữ số của số nguyên.

## 2. Chuyển đổi nào luôn chính xác?

| Phép chuyển đổi | Widening tự động? | Chính xác với **mọi** giá trị nguồn? |
| --- | --- | --- |
| `byte` → `float`/`double` | Có | Có |
| `short` → `float`/`double` | Có | Có |
| `char` → `float`/`double` | Có | Có (giá trị code unit 0–65535) |
| `int` → `double` | Có | **Có** |
| `int` → `float` | Có | **Không** |
| `long` → `double` | Có | **Không** |
| `long` → `float` | Có | **Không** |

Giới hạn quan trọng:

- `float` biểu diễn được **mọi** số nguyên từ `-2^24` đến `2^24` (±16.777.216).
- `double` biểu diễn được **mọi** số nguyên từ `-2^53` đến `2^53` (±9.007.199.254.740.992).
- Trên các ngưỡng này, **một số** số nguyên vẫn biểu diễn chính xác (ví dụ số chẵn ở ngay trên `2^24` có thể vừa `float`), nhưng **không phải tất cả số nguyên liên tiếp**.

Bởi vậy toàn bộ giá trị `int` chuyển sang `double` vẫn chính xác, trong khi `int` chuyển sang `float` hoặc `long` chuyển sang `double` có nguy cơ làm tròn.

## 3. Ranh giới `2^24 + 1` khi đổi `int` sang `float`

~~~java
int first = 16_777_216;       // 2^24
int second = 16_777_217;      // 2^24 + 1
float a = first;
float b = second;
~~~

`a` bằng 16.777.216 chính xác. Ở độ lớn này, khoảng cách giữa các giá trị `float` liên tiếp là **2**, nên số 16.777.217 nằm giữa 16.777.216 và 16.777.218. Quy tắc ties-to-even làm tròn `b` thành **16.777.216**.

Hệ quả:

~~~java
System.out.println(first == second); // false
System.out.println(a == b);          // true
~~~

`Math.ulp(a)` cho khoảng cách giữa `a` và giá trị `float` kế tiếp tại độ lớn này: **2.0f**. Nếu cần lưu đúng bất kỳ giá trị `int`, nên giữ `int` hoặc chuyển thành `double`, thay vì ép thành `float`.

## 4. Ranh giới `2^53 + 1` khi đổi `long` sang `double`

~~~java
long first = 9_007_199_254_740_992L; // 2^53
long second = first + 1;              // 2^53 + 1
double a = first;
double b = second;
~~~

`a` và `b` trở thành **cùng một giá trị `double`** là 9.007.199.254.740.992, dù hai số nguyên nguồn khác nhau. Chú ý phép so sánh hỗn hợp:

~~~java
System.out.println(second == b);       // true - dễ nhầm!
System.out.println(second == (long) b); // false
~~~

Trong `second == b`, Java **nâng kiểu số** (*binary numeric promotion*): chuyển số `long second` sang `double` trước khi so sánh. Khi hai vế cùng bị làm tròn, phép `==` cho true **không chứng minh dữ liệu được giữ chính xác**.

Ép `b` trở lại `long` trong ví dụ này cho 9.007.199.254.740.992 và giúp thấy sai lệch 1. Tuy nhiên, cast số thực sang số nguyên còn có quy tắc bỏ phần lẻ và giới hạn giá trị; nó **không phải phương pháp tổng quát** để kiểm tra chuyển đổi có chính xác hay không.

## 5. Ví dụ Java 17+ chạy được

Tạo tệp **IntegerFloatPrecisionDemo.java**:

~~~java
import java.math.BigDecimal;

public final class IntegerFloatPrecisionDemo {
    public static void main(String[] args) {
        int baseInt = 16_777_216;
        int nextInt = baseInt + 1;

        float fa = baseInt;
        float fb = nextInt;
        double preciseInt = nextInt;

        System.out.println("intNext=" + nextInt);
        System.out.println("floatAsInt=" + (int) fb);
        System.out.println("doubleIntAsInt=" + (int) preciseInt);
        System.out.println("floatEqual=" + (fa == fb));
        System.out.println("floatUlp=" + (int) Math.ulp(fa));

        long baseLong = 9_007_199_254_740_992L;
        long nextLong = baseLong + 1;
        double da = baseLong;
        double db = nextLong;

        System.out.println("longNext=" + nextLong);
        System.out.println("doubleAsLong=" + (long) db);
        System.out.println("doubleEqual=" + (da == db));
        System.out.println("mixedEqual=" + (nextLong == db));
        System.out.println("roundTripEqual=" + (nextLong == (long) db));
        System.out.println("doubleUlp=" + (int) Math.ulp(da));

        System.out.println("allIntToDoubleExact="
                + ((long) (double) Integer.MAX_VALUE
                        == Integer.MAX_VALUE));
        System.out.println("exactDecimal="
                + BigDecimal.valueOf(nextLong).toPlainString());
    }
}
~~~

Mở terminal tại thư mục chứa file (Bash, PowerShell hoặc Command Prompt) và chạy:

~~~bash
javac -encoding UTF-8 IntegerFloatPrecisionDemo.java
java IntegerFloatPrecisionDemo
~~~

**Expected output chính xác:**

~~~text
intNext=16777217
floatAsInt=16777216
doubleIntAsInt=16777217
floatEqual=true
floatUlp=2
longNext=9007199254740993
doubleAsLong=9007199254740992
doubleEqual=true
mixedEqual=true
roundTripEqual=false
doubleUlp=2
allIntToDoubleExact=true
exactDecimal=9007199254740993
~~~

Các dòng `floatAsInt` và `doubleAsLong` cho thấy **giá trị sau khi làm tròn**, chứ không phải kiểu mới tự lưu thêm số. Hai kết quả `floatUlp=2` và `doubleUlp=2` thể hiện bước nhảy giữa các giá trị số thực tại các ngưỡng đang xét (đã cast sang `int` để dễ đọc). `BigDecimal.valueOf(nextLong)` lấy **trực tiếp từ số nguyên gốc**, giữ nguyên số 9.007.199.254.740.993.

## 6. Cách chọn kiểu khi cần chính xác

| Nhu cầu | Khuyến nghị |
| --- | --- |
| ID, số lượng, timestamp nguyên, tiền lưu bằng đơn vị nguyên | Dùng `int`/`long` nếu miền giá trị phù hợp |
| Chuyển toàn bộ miền `int` sang số thực mà chưa tính tiếp | `double` giữ chính xác mọi giá trị `int` |
| `long` lớn và **không được sai một đơn vị** | Tránh chuyển sang `double` để lưu hoặc so sánh |
| Số nguyên cần vượt miền `long` | Dùng `BigInteger` |
| Thập phân cần chính xác theo quy tắc nghiệp vụ | Dùng `BigDecimal` từ `String` hoặc số nguyên gốc, với scale/rounding rõ ràng |
| Đo lường hay đồ họa chấp nhận xấp xỉ | `float`/`double` nếu sai số chấp nhận được |

**Không có cách “lấy lại” các bit đã mất** chỉ bằng `Math.round`, cast ngược hoặc tạo `BigDecimal` từ giá trị `double` đã làm tròn. Nếu đòi hỏi số nguyên chính xác, giữ số nguyên gốc xuyên suốt luồng dữ liệu và các phép so sánh.

`int → double` đúng tuyệt đối **ở bước chuyển đổi**, nhưng các phép tính `double` về sau vẫn có thể sinh sai số làm tròn, `NaN` hoặc vô cực. Độ chính xác của phép gán không bảo đảm độ chính xác của toàn bộ thuật toán.

## 7. Bài tập kiểm tra

**Bài 1.** Vì sao `(float) 16_777_216 == (float) 16_777_217` cho true, dù hai literal số nguyên khác nhau?

**Bài 2.** Nêu vì sao `int → double` chính xác với mọi `int`, nhưng `long → double` thì không. Giải thích vai trò của 53 bit phần trị.

**Bài 3.** Cho `long id = 9_007_199_254_740_993L; double d = id;`. Dự đoán `id == d` và `id == (long) d`; chỉ ra bước numeric promotion.

**Bài 4.** Đổi `BigDecimal.valueOf(id)` thành `BigDecimal.valueOf((double) id)`. So sánh chuỗi số thập phân thu được và giải thích tại sao không thể phục hồi phần đã mất.

**Bài 5.** Thiết kế một ứng dụng lưu ID 64 bit chính xác, rồi xuất dạng văn bản. Đề xuất cách chuyển thẳng `long` thành `String` mà không đi qua `double`.

### Ghi nhớ

**Chuyển số nguyên sang số thực là widening hợp lệ nhưng không luôn lossless.** `float` chỉ có 24 bit chính xác, `double` có 53 bit. Vì vậy `int → float` và `long → double` có thể làm tròn; ngược lại **mọi `int → double` đều chính xác**. Nếu cần lưu đúng từng đơn vị của số nguyên lớn, đừng đưa giá trị qua số thực xấp xỉ.
