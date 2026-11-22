# Nhận diện vấn đề tràn số và độ chính xác trước khi viết phép tính — Java 17+

Một phép tính **biên dịch thành công** chưa chắc có **kết quả đúng**. Với kiểu nguyên thủy Java, hai nhóm rủi ro quan trọng là:

- **Tràn số nguyên (*integer overflow*)**: phép toán vượt miền biểu diễn của kiểu `int` hoặc `long` và kết quả có thể quay vòng thành số khác.
- **Sai số số thực (*floating-point rounding/precision*)**: `float` và `double` dùng biểu diễn nhị phân hữu hạn, nên nhiều số thập phân không thể lưu chính xác.

Cách phòng ngừa hiệu quả nhất không phải sửa lỗi sau khi xảy ra, mà là **ước lượng miền đầu vào, miền kết quả trung gian và độ chính xác yêu cầu trước khi chọn kiểu hoặc viết phép tính**.

## 1. Bảng tự kiểm tra trước khi lập trình

| Câu hỏi cần trả lời | Ví dụ rủi ro | Hướng xử lý |
| --- | --- | --- |
| Đầu vào lớn nhất và nhỏ nhất là bao nhiêu? | Cộng vào `Integer.MAX_VALUE` | Kiểm tra giới hạn, dùng `long` hoặc phép toán có kiểm tra |
| **Tích/tổng trung gian** có vượt miền kiểu toán hạng? | `int * int` rồi gán vào `long` | Chuyển sang `long` **trước khi nhân** |
| Phép chia cần lấy phần thập phân? | `5 / 2` cho `2` | Chọn `5 / 2.0` hoặc ép kiểu trước chia |
| Cần giá trị thập phân **chính xác**? | `0.1 + 0.2` không bằng đúng `0.3` ở kiểu `double` | Dùng `BigDecimal` từ chuỗi hoặc đơn vị nguyên phù hợp |
| Có phép chuyển kiểu thu hẹp? | Ép `130` sang `byte` cho `-126` | Kiểm tra miền trước khi cast |
| Phép số thực có thể vượt miền hoặc không xác định? | `Double.MAX_VALUE * 2`, `0.0 / 0.0` | Xử lý `Infinity`, `NaN` khi phù hợp |
| Có số nguyên rất lớn chuyển sang `double`? | `2^53 + 1` không giữ nguyên chính xác | Giữ `long` khi cần đúng từng đơn vị |

Giới hạn hay gặp trên Java 17: `byte` từ −128 đến 127; `short` từ −32.768 đến 32.767; `int` từ −2.147.483.648 đến 2.147.483.647; `long` từ −9.223.372.036.854.775.808 đến 9.223.372.036.854.775.807.

## 2. Chương trình Java 17+ runnable

Lưu tệp **`NumericSafetyDemo.java`**:

~~~java
import java.math.BigDecimal;

public class NumericSafetyDemo {
    public static void main(String[] args) {
        int max = Integer.MAX_VALUE;
        System.out.println("wrapped=" + (max + 1));

        try {
            Math.addExact(max, 1);
        } catch (ArithmeticException ex) {
            System.out.println("addExact=overflow");
        }

        int unit = 80_000;
        int quantity = 35_000;

        long badProduct = (long) (unit * quantity);
        long goodProduct = (long) unit * quantity;
        System.out.println("badProduct=" + badProduct);
        System.out.println("goodProduct=" + goodProduct);

        try {
            Math.multiplyExact(unit, quantity);
        } catch (ArithmeticException ex) {
            System.out.println("multiplyExact=overflow");
        }

        System.out.println("intDivision=" + (5 / 2));
        System.out.println("realDivision=" + (5 / 2.0));

        double floatingSum = 0.1 + 0.2;
        System.out.println("floatingSum=" + floatingSum);
        System.out.println("floatingEqual=" + (floatingSum == 0.3));

        BigDecimal exactSum = new BigDecimal("0.1")
                .add(new BigDecimal("0.2"));
        System.out.println("decimalSum=" + exactSum.toPlainString());
        System.out.println("decimalEqual="
                + (exactSum.compareTo(new BigDecimal("0.3")) == 0));

        long big = 9_007_199_254_740_993L;
        double rounded = big;
        System.out.println("longPrecisionLost=" + ((long) rounded != big));

        System.out.println("floatingOverflow="
                + (Double.MAX_VALUE * 2));
        System.out.println("nan=" + (0.0 / 0.0));
    }
}
~~~

Mở PowerShell (Windows) hoặc Bash (Linux/macOS) ở thư mục chứa tệp. Dùng JDK 17 trở lên:

~~~bash
java -version
javac -version
javac -encoding UTF-8 NumericSafetyDemo.java
java NumericSafetyDemo
~~~

**Expected output:**

~~~text
wrapped=-2147483648
addExact=overflow
badProduct=-1494967296
goodProduct=2800000000
multiplyExact=overflow
intDivision=2
realDivision=2.5
floatingSum=0.30000000000000004
floatingEqual=false
decimalSum=0.3
decimalEqual=true
longPrecisionLost=true
floatingOverflow=Infinity
nan=NaN
~~~

## 3. Vì sao kết quả tràn số nguyên?

`int` dùng 32 bit có dấu. Khi cộng vượt `Integer.MAX_VALUE`, phép toán `int` thông thường **không tự ném ngoại lệ**, mà giữ kết quả theo quy tắc tràn của số nguyên Java:

~~~java
int max = Integer.MAX_VALUE;
int wrapped = max + 1; // -2147483648.
~~~

Nếu tràn là **lỗi nghiệp vụ**, nên phát hiện thay vì nhận giá trị đã quay vòng:

~~~java
int checked = Math.addExact(100, 200); // 300.
int product = Math.multiplyExact(10, 20); // 200.

// Math.addExact(Integer.MAX_VALUE, 1)
// nem ArithmeticException khi ket qua vuot mien int.
~~~

`Math.addExact` và `Math.multiplyExact` có overload cho `int`/`long`, ném `ArithmeticException` khi kết quả không biểu diễn được trong kiểu tương ứng. Chúng không tự làm kết quả lớn hơn; muốn chứa số vượt `long`, cân nhắc `BigInteger`.

### Bẫy: đổi sang `long` sau phép nhân là quá muộn

~~~java
int unit = 80_000;
int quantity = 35_000;

long wrong = (long) (unit * quantity); // -1494967296.
long right = (long) unit * quantity;   // 2800000000.
~~~

Ở dòng `wrong`, `unit * quantity` được tính bằng `int` **trước khi cast**, nên đã tràn. `(long)` chỉ mở rộng **giá trị sai**. Dòng `right` chuyển một toán hạng thành `long` **trước phép nhân**; Java thực hiện phép nhân kiểu `long`.

Tuy nhiên, `long` cũng có giới hạn; nếu tích có thể vượt `Long.MAX_VALUE`, tiếp tục cần kiểm tra hoặc kiểu số nguyên tùy ý `BigInteger`.

## 4. Sai số không giống tràn số

`float` (32 bit) và `double` (64 bit) dùng biểu diễn nhị phân IEEE 754. Nhiều phân số thập phân như `0.1` và `0.2` **không biểu diễn chính xác**. Vì vậy:

~~~java
double sum = 0.1 + 0.2;
System.out.println(sum);        // 0.30000000000000004
System.out.println(sum == 0.3); // false
~~~

`double` thường chính xác hơn `float`, nhưng **không biến phép toán thập phân thành chính xác tuyệt đối**.

| Yêu cầu | Cách chọn |
| --- | --- |
| Tính toán khoa học, đồ họa và thống kê chấp nhận sai số | `double` thông thường; `float` khi định dạng/hiệu năng yêu cầu |
| Tiền tệ với đơn vị nhỏ nhất cố định | Số nguyên biểu diễn cents/đồng, kèm kiểm tra miền |
| Phép tính thập phân cần giữ chữ số chính xác | `BigDecimal`, khởi tạo từ `String` |
| Đếm chính xác vượt miền `long` | `BigInteger` |
| Kiểm tra gần bằng nhau ở miền số thực | Dùng sai số tuyệt đối/tương đối theo đặc tả bài toán |

Để giữ giá trị thập phân `0.1`, viết:

~~~java
BigDecimal amount = new BigDecimal("0.1"); // Chinh xac 0.1.
~~~

Tránh `new BigDecimal(0.1)` nếu mục tiêu là giá trị thập phân chính xác 0,1, vì constructor đó nhận **giá trị `double` đã được làm tròn trong hệ nhị phân**. Khi so sánh giá trị số `BigDecimal`, `compareTo` có thể phù hợp hơn `equals` vì `equals` còn xét **scale** (`1.0` khác `1.00` theo `equals`).

### Số nguyên lớn chuyển sang `double` cũng có thể mất chính xác

`double` có 53 bit độ chính xác cho phần định trị; không thể giữ chính xác **mọi** số nguyên rất lớn:

~~~java
long big = 9_007_199_254_740_993L; // 2^53 + 1.
double rounded = big;
System.out.println((long) rounded != big); // true
~~~

Một phép chuyển kiểu được Java cho phép **không có nghĩa giá trị vẫn chính xác**.

## 5. Các bẫy cần kiểm tra trước khi viết công thức

**Chia số nguyên:** `double result = 5 / 2;` cho `2.0`, không phải `2.5`, vì phép chia đã thực hiện bằng `int`. Viết `5 / 2.0` hoặc `(double) 5 / 2` nếu cần phần thập phân.

**Thu hẹp:** `(byte) 130` cho `-126` do giữ 8 bit thấp rồi diễn giải là số có dấu. Hãy so sánh với miền đích trước khi cast.

**Phép chia cho 0:** `1 / 0` trên kiểu số nguyên ném `ArithmeticException` nếu được thực thi; ngược lại `1.0 / 0.0` cho `Infinity`, `0.0 / 0.0` cho `NaN`. Kiểm tra mẫu số và tính hợp lệ của kết quả theo yêu cầu.

**`NaN` không bằng chính nó:** `Double.NaN == Double.NaN` trả `false`; dùng `Double.isNaN(value)` để phát hiện. Dùng `Double.isFinite(value)` để kiểm tra kết quả hữu hạn nếu bài toán không chấp nhận `NaN` hay vô cực.

**Đừng dùng một epsilon cố định cho mọi bài toán:** so sánh xấp xỉ cần xét thang đo, sai số tuyệt đối/tương đối và rủi ro `NaN`. Với dữ liệu có yêu cầu **chính xác tuyệt đối**, hãy thay đổi biểu diễn thay vì chỉ tăng ngưỡng sai số.

## 6. Checklist thiết kế phép tính

Trước khi viết một công thức, hãy trả lời:

1. **Đầu vào/đầu ra lớn nhất và nhỏ nhất?** Ví dụ số lượng tối đa nhân đơn giá tối đa là bao nhiêu?
2. **Trung gian tính bằng kiểu nào?** Cast trước hay sau toán tử? Có phép cộng/nhân `int` tràn trước khi gán `long`?
3. **Chia lấy nguyên hay thập phân?** Kiểu của từng toán hạng là gì?
4. **Cho phép sai số bao nhiêu?** Nếu là tiền hoặc định danh số nguyên, có cần biểu diễn chính xác?
5. **Có thu hẹp kiểu hoặc chuyển nguyên lớn sang số thực?** Giá trị nào có thể bị mất?
6. **Kết quả bất thường xử lý thế nào?** Ném lỗi bằng `Math.*Exact`, kiểm tra mẫu số, `NaN` và `Infinity`.
7. **Đã thử giá trị biên?** Kiểm tra 0, số âm, giới hạn min/max, tích lớn, phân số nhỏ và dữ liệu ngoài phạm vi.

## 7. Bài tập ngắn

**Bài 1.** Vì sao `long x = 100_000 * 100_000;` cho kết quả không đúng 10.000.000.000? Sửa thế nào?

*Đáp án:* Hai toán hạng là `int` nên tích `int` tràn trước khi gán. Dùng `100_000L * 100_000` hoặc `(long) 100_000 * 100_000`.

**Bài 2.** `Math.addExact(Integer.MAX_VALUE, 1)` trả số âm hay ném lỗi?

*Đáp án:* Ném `ArithmeticException`; phép `+` thông thường mới quay vòng.

**Bài 3.** Tại sao `double x = 7 / 2;` cho `3.0`, còn `double y = 7 / 2.0;` cho `3.5`?

*Đáp án:* Kiểu toán hạng quyết định phép chia nguyên hay số thực **trước khi gán**.

**Bài 4.** Tính chính xác `0.1 + 0.2` theo thập phân. Nên dùng cách nào?

*Đáp án:* `new BigDecimal("0.1").add(new BigDecimal("0.2"))` cho đúng `0.3`.

**Bài 5.** `Double.MAX_VALUE * 2` và `0.0 / 0.0` cho gì?

*Đáp án:* Lần lượt `Infinity` và `NaN`, không giống tràn số nguyên.

**Kết luận:** Trước khi viết phép tính Java, hãy kiểm tra **miền dữ liệu**, **kiểu của mỗi kết quả trung gian** và **độ chính xác mong muốn**. Dùng kiểu rộng **trước phép tính**, kiểm tra tràn bằng `Math.*Exact`, và chọn `BigDecimal`/`BigInteger` khi các giới hạn của primitive không đáp ứng yêu cầu.
