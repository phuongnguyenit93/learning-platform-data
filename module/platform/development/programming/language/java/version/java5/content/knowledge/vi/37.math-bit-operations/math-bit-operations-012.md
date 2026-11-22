# Kiểm thử NaN, vô cực, số không có dấu và các giá trị biên

## 1. Kiểm thử số thực bắt đầu từ hợp đồng của phép tính

Một hàm số học có thể chạy hết mà vẫn trả về kết quả không phù hợp yêu cầu. Với `double` và `float`, cần kiểm tra cả giá trị thông thường, kết quả đặc biệt và hành vi sát giới hạn biểu diễn.

Trong bài này, phần kiểm thử số không xét cả **số không mang dấu dương `+0.0` và số không mang dấu âm `-0.0`**: đây là hai giá trị có dấu (signed zero), không phải kiểu số nguyên không dấu. Hai số không có thể bằng nhau khi dùng `==` nhưng vẫn dẫn đến kết quả khác ở phép tính tiếp theo.

Trước khi viết phép kiểm tra, hãy quyết định:

- Đầu vào NaN hoặc vô cực được chấp nhận, truyền tiếp hay bị từ chối?
- Kết quả phải đúng chính xác từng biểu diễn hay chỉ gần đúng trong một sai số cho phép?
- Dấu của số không có ý nghĩa với thuật toán không?
- Hàm làm gì tại điểm biên và ngay bên ngoài miền hợp lệ?

Ví dụ, hàm căn bậc hai phục vụ một quy trình chỉ nhận dữ liệu hữu hạn có thể chủ động từ chối NaN/vô cực. Một hàm thư viện toán tổng quát lại có thể giữ nguyên quy tắc của `Math.sqrt`. Kiểm thử phải bám vào lựa chọn đã công bố.

## 2. Phân loại giá trị trước khi so sánh

| Nhóm | Ví dụ `double` | Cách kiểm tra phù hợp |
|---|---|---|
| Hữu hạn thông thường | `-2.5`, `1.0` | `Double.isFinite(x)`, rồi so sánh chính xác hoặc gần đúng |
| Số không | `+0.0`, `-0.0` | `x == 0.0` cho cả hai; so bit nếu cần phân biệt dấu |
| Số dưới chuẩn (subnormal) | `Double.MIN_VALUE` | Xét giá trị khác 0 và trị tuyệt đối nhỏ hơn `Double.MIN_NORMAL` |
| Vô cực | `Double.POSITIVE_INFINITY`, `Double.NEGATIVE_INFINITY` | `Double.isInfinite(x)`; kiểm tra riêng dấu |
| Không phải số (NaN) | `Double.NaN`, `0.0 / 0.0` | `Double.isNaN(x)` |

`Double.MIN_VALUE` là số `double` **dương nhỏ nhất khác 0**, không phải số âm nhỏ nhất. Biên hữu hạn âm là `-Double.MAX_VALUE`. `Double.MIN_NORMAL` đánh dấu số dương chuẩn nhỏ nhất; các số dương khác 0 nhỏ hơn nó vẫn có thể biểu diễn dưới dạng dưới chuẩn. Đây là các nhóm giá trị hiện hành của Java. Xem [JLS §4.2.3–4.2.4](https://docs.oracle.com/javase/specs/jls/se21/html/jls-4.html#jls-4.2.3).

Khi tên phép kiểm tra chỉ là “kết quả hợp lệ”, rất dễ bỏ sót một nhóm. Hãy đặt tên rõ như “từ chối NaN”, “giữ dấu âm của số không”, “đầu ra hữu hạn tại đầu vào cực đại”.

## 3. NaN, vô cực và số không: chọn đúng phép xác nhận

### NaN không dùng phép bằng số học

`x == Double.NaN` luôn cho `false`, kể cả khi `x` là NaN. `x != x` nhận diện được NaN, nhưng `Double.isNaN(x)` thể hiện ý định rõ hơn. Với NaN, các so sánh thứ tự `<`, `<=`, `>`, `>=` đều cho `false`.

Hệ quả khi kiểm tra đầu vào: điều kiện `x < 0.0` không loại được NaN. Nếu chỉ nhận số hữu hạn không âm, dùng `!Double.isFinite(x) || x < 0.0` để từ chối.

### Vô cực phải xét cả hai dấu

`Double.isInfinite(x)` xác nhận nhóm vô cực nhưng không cho biết dấu. Nếu hợp đồng yêu cầu vô cực dương, hãy so sánh thêm với `Double.POSITIVE_INFINITY`.

Phép chia số thực cho số không không ném `ArithmeticException` như chia số nguyên cho 0. Một số trường hợp cần kiểm thử:

| Biểu thức | Kết quả |
|---|---|
| `1.0 / +0.0` | Vô cực dương |
| `1.0 / -0.0` | Vô cực âm |
| `0.0 / 0.0` | NaN |
| `Double.POSITIVE_INFINITY + Double.NEGATIVE_INFINITY` | NaN |
| `0.0 * Double.POSITIVE_INFINITY` | NaN |

Các quy tắc so sánh và phép toán này được quy định trong [JLS §15.21.1](https://docs.oracle.com/javase/specs/jls/se21/html/jls-15.html#jls-15.21.1) và [JLS §15.17.2](https://docs.oracle.com/javase/specs/jls/se21/html/jls-15.html#jls-15.17.2).

### Hai số không cần một quyết định có chủ đích

Nếu hợp đồng coi hai dấu số không là tương đương, `expected == actual` phù hợp cho trường hợp đó. Nếu phải phân biệt chúng, có thể dùng:

```java
Double.doubleToLongBits(expected) == Double.doubleToLongBits(actual)
```

Biểu thức này cũng coi mọi NaN là tương đương nhờ chuẩn hóa NaN. `Double.equals` và `Double.compare(a, b) == 0` có cùng cách phân biệt số không và gộp NaN theo nghĩa này; chúng khác `==` số học. Không dùng `==` giữa hai biến kiểu `Double` để kiểm tra giá trị, vì đó có thể là so sánh tham chiếu.

Khi cần khảo sát bit NaN, `doubleToRawLongBits` giữ thông tin mà `doubleToLongBits` chuẩn hóa. Tuy nhiên, không yêu cầu mọi phép tính sinh cùng mẫu bit NaN; việc bảo toàn mọi mẫu signaling NaN cũng không phải giả định di động. Xem [API Double](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Double.html).

## 4. Tạo dữ liệu sát biên bằng giá trị liền kề

Đừng mặc định rằng “biên cộng `1e-9`” luôn là giá trị liền sau. Ở thang giá trị rất lớn, cộng lượng đó có thể không làm số thay đổi; ở thang rất nhỏ, nó lại bỏ qua nhiều giá trị.

Dùng `Math.nextDown(b)`, `b`, `Math.nextUp(b)` để tạo ba điểm quanh biên `b`. Với biên hữu hạn của miền nghiệp vụ, kiểm tra riêng cả ba theo điều kiện đóng/mở của miền. Ví dụ miền `[0, 1]` phải chấp nhận hai đầu mút, từ chối giá trị liền dưới 0 và liền trên 1.

Những bộ dữ liệu đáng có:

| Khu vực | Dữ liệu tiêu biểu | Lỗi có thể lộ ra |
|---|---|---|
| Quanh số không | `-Double.MIN_VALUE`, `-0.0`, `+0.0`, `Double.MIN_VALUE` | Nhầm dấu, từ chối sai miền |
| Chuyển dưới chuẩn → chuẩn | `Math.nextDown(Double.MIN_NORMAL)`, `Double.MIN_NORMAL`, `Math.nextUp(Double.MIN_NORMAL)` | Ngầm coi mọi số quá nhỏ là 0 |
| Cực đại hữu hạn | `Math.nextDown(Double.MAX_VALUE)`, `Double.MAX_VALUE` và hai giá trị âm tương ứng | Tràn ở bước trung gian |
| Ngưỡng thuật toán | Giá trị liền trước, đúng ngưỡng và liền sau | Sai điều kiện `<`/`<=` |
| Làm tròn gần số thông thường | `Math.nextDown(1.0)`, `1.0`, `Math.nextUp(1.0)` | Giả định khoảng cách luôn giống nhau |

`nextUp(Double.MAX_VALUE)` là vô cực dương. `nextUp(0.0)` là `Double.MIN_VALUE`; `nextDown(0.0)` là `-Double.MIN_VALUE`. `Math.ulp(x)` giúp xem độ lớn một đơn vị ở vị trí biểu diễn cuối, nhưng không phải một mức sai số nghiệp vụ dùng chung cho mọi thuật toán.

Tràn số thực có thể tạo vô cực. Hụt dưới có thể tạo số dưới chuẩn hoặc số không; chẳng hạn `Double.MIN_VALUE / 2.0` cho `+0.0`, còn `-Double.MIN_VALUE / 2.0` cho `-0.0`. Kiểm thử phải quan sát kết quả thực tế thay vì chỉ chờ ngoại lệ. Các hàm lân cận và trường hợp đặc biệt của hàm toán được mô tả trong [API Math](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Math.html).

## 5. Khi nào dùng sai số?

Phép kiểm tra gần đúng là một **quyết định của bài toán**. Trước hết tách NaN/vô cực; sau đó mới đo khoảng cách giữa các số hữu hạn.

Một tiêu chí thường dùng là:

```text
|expected - actual| <= max(absTol, relTol * max(|expected|, |actual|))
```

- Sai số tuyệt đối `absTol` kiểm soát vùng gần 0.
- Sai số tương đối `relTol` thích ứng theo thang giá trị.
- Hai ngưỡng phải được chọn từ đơn vị đo và độ chính xác cần đạt; `1e-15` và `1e-12` trong ví dụ dưới chỉ là lựa chọn minh họa.

Không chấp nhận một công thức gần đúng mà chưa kiểm thử chính nó. Ví dụ NaN làm phép so sánh cuối thành `false`; hai vô cực cùng dấu khi trừ nhau tạo NaN; trừ hai số hữu hạn trái dấu cực lớn có thể tràn.

Hàm `closeFinite` dưới đây từ chối mọi đầu vào không hữu hạn, kể cả hai vô cực giống nhau. Nó giới hạn `relTol` trong `[0, 1]` và yêu cầu cả hai ngưỡng hữu hạn, không âm. Nhờ đó vế giới hạn không tự tràn; khi phép trừ trái dấu tràn, kết quả là không gần nhau theo tiêu chí đã chọn. Hàm coi hai dấu số không là gần nhau. Nếu cần kiểm tra dấu, dùng phép so biểu diễn riêng.

Không dùng sai số để che một lỗi mất độ chính xác. Nếu thuật toán đòi chính xác thập phân, hãy xác định cách biểu diễn và làm tròn phù hợp trước khi quyết định cách kiểm thử.

## 6. Chương trình kiểm thử độc lập trên Java 17+

Lưu toàn bộ chương trình sau vào `FloatingPointBoundaryChecks.java`. Chương trình không cần thư viện kiểm thử bên ngoài. Mỗi kỳ vọng sai sẽ ném `AssertionError`; không dùng từ khóa `assert`, nên không phụ thuộc tùy chọn `-ea`.

```java
public class FloatingPointBoundaryChecks {
    private static void check(String label, boolean condition) {
        if (!condition) {
            throw new AssertionError(label);
        }
    }

    private static void sameRepresentation(
            String label, double expected, double actual) {
        check(label, Double.doubleToLongBits(expected)
                == Double.doubleToLongBits(actual));
    }

    private static boolean closeFinite(
            double expected, double actual,
            double absTol, double relTol) {
        if (!Double.isFinite(absTol) || absTol < 0.0
                || !Double.isFinite(relTol)
                || relTol < 0.0 || relTol > 1.0) {
            throw new IllegalArgumentException("Invalid tolerance");
        }
        if (!Double.isFinite(expected) || !Double.isFinite(actual)) {
            return false;
        }
        if (expected == actual) {
            return true;
        }
        double difference = Math.abs(expected - actual);
        double scale = Math.max(Math.abs(expected), Math.abs(actual));
        return difference <= Math.max(absTol, relTol * scale);
    }

    private static double checkedSqrt(double x) {
        if (!Double.isFinite(x) || x < 0.0) {
            throw new IllegalArgumentException("Finite nonnegative input required");
        }
        return Math.sqrt(x);
    }

    private static void rejectsSqrt(String label, double x) {
        try {
            checkedSqrt(x);
        } catch (IllegalArgumentException expected) {
            return;
        }
        throw new AssertionError(label);
    }

    public static void main(String[] args) {
        double nan = Double.NaN;
        check("zero divided by zero", Double.isNaN(0.0 / 0.0));
        check("sqrt negative", Double.isNaN(Math.sqrt(-1.0)));
        check("NaN is not numerically equal to itself", nan != nan);
        check("NaN is unordered", !(nan < 0.0) && !(nan >= 0.0));
        check("opposite infinities", Double.isNaN(
                Double.POSITIVE_INFINITY + Double.NEGATIVE_INFINITY));
        check("zero times infinity", Double.isNaN(
                0.0 * Double.POSITIVE_INFINITY));
        sameRepresentation("canonical NaNs", nan, 0.0 / 0.0);

        sameRepresentation("positive infinity",
                Double.POSITIVE_INFINITY, 1.0 / 0.0);
        sameRepresentation("negative infinity",
                Double.NEGATIVE_INFINITY, 1.0 / -0.0);
        check("infinite predicate", Double.isInfinite(-1.0 / 0.0));
        check("infinity is not finite", !Double.isFinite(1.0 / 0.0));
        check("overflow", Double.isInfinite(Double.MAX_VALUE * 2.0));

        check("zeros numerically equal", +0.0 == -0.0);
        check("zeros have different representations",
                Double.doubleToLongBits(+0.0)
                        != Double.doubleToLongBits(-0.0));
        check("wrapper equality distinguishes zeros",
                !Double.valueOf(+0.0).equals(Double.valueOf(-0.0)));
        sameRepresentation("sqrt preserves negative zero",
                -0.0, Math.sqrt(-0.0));
        sameRepresentation("min chooses negative zero",
                -0.0, Math.min(+0.0, -0.0));
        sameRepresentation("abs removes negative sign",
                +0.0, Math.abs(-0.0));

        sameRepresentation("smallest positive neighbor",
                Double.MIN_VALUE, Math.nextUp(0.0));
        sameRepresentation("smallest negative neighbor",
                -Double.MIN_VALUE, Math.nextDown(0.0));
        sameRepresentation("positive underflow",
                +0.0, Double.MIN_VALUE / 2.0);
        sameRepresentation("negative underflow",
                -0.0, -Double.MIN_VALUE / 2.0);
        check("last subnormal",
                Math.nextDown(Double.MIN_NORMAL) > 0.0
                        && Math.nextDown(Double.MIN_NORMAL)
                                < Double.MIN_NORMAL);
        check("next above max is infinity",
                Math.nextUp(Double.MAX_VALUE)
                        == Double.POSITIVE_INFINITY);
        sameRepresentation("one neighbor",
                1.0, Math.nextDown(Math.nextUp(1.0)));

        check("decimal sum differs", 0.1 + 0.2 != 0.3);
        check("decimal sum within selected tolerance",
                closeFinite(0.3, 0.1 + 0.2, 1e-15, 1e-12));
        check("finite comparison rejects infinity",
                !closeFinite(Double.POSITIVE_INFINITY,
                        Double.POSITIVE_INFINITY, 1e-15, 1e-12));
        check("finite comparison rejects NaN",
                !closeFinite(nan, nan, 1e-15, 1e-12));
        check("opposite extremes are not close",
                !closeFinite(Double.MAX_VALUE,
                        -Double.MAX_VALUE, 0.0, 1e-12));

        rejectsSqrt("reject NaN", nan);
        rejectsSqrt("reject infinity", Double.POSITIVE_INFINITY);
        rejectsSqrt("reject just below zero", Math.nextDown(0.0));
        sameRepresentation("accept negative zero",
                -0.0, checkedSqrt(-0.0));
        sameRepresentation("accept positive zero",
                +0.0, checkedSqrt(+0.0));
        check("accept just above zero",
                Double.isFinite(checkedSqrt(Math.nextUp(0.0))));
        sameRepresentation("ordinary root", 2.0, checkedSqrt(4.0));

        System.out.println("All boundary checks passed.");
    }
}
```

Biên dịch và chạy:

```shell
javac -encoding UTF-8 --release 17 FloatingPointBoundaryChecks.java
java FloatingPointBoundaryChecks
```

Stdout khi tất cả phép kiểm tra thành công:

```text
All boundary checks passed.
```

Các nhóm kiểm tra trong chương trình có mục đích khác nhau:

1. Nhóm NaN/vô cực chứng minh vì sao “không có ngoại lệ” chưa đủ.
2. Nhóm số không phân biệt bằng nhau về số học và giống nhau về biểu diễn.
3. Nhóm biên thử các điểm liền kề và kết quả tràn/hụt dưới.
4. Nhóm sai số kiểm tra cả trường hợp chấp nhận lẫn từ chối của chính hàm so gần đúng.
5. Nhóm `checkedSqrt` kiểm tra chính sách đầu vào: chỉ nhận số hữu hạn không âm, chấp nhận cả hai dấu số không và giữ dấu của kết quả căn.

Trong `rejectsSqrt`, chỉ `IllegalArgumentException` đáp ứng hợp đồng từ chối đầu vào. Nếu hàm trả bình thường hoặc ném loại lỗi khác, bài kiểm tra thất bại. Đây là cách tránh kiểm thử quá rộng kiểu “có bất kỳ lỗi nào cũng xem là đạt”.

## 7. Chuyển cách làm sang kiểm thử của dự án

Khi đưa vào bộ kiểm thử dự án, tách mỗi nhóm hành vi thành trường hợp có tên rõ và giữ thông tin đầu vào trong thông báo thất bại. Có thể dùng dữ liệu tham số hóa, nhưng kỳ vọng phải đọc được: đầu vào nào bị từ chối, đầu vào nào trả NaN, đầu vào nào cần giữ dấu số không.

Với `float`, xây một bộ dữ liệu riêng bằng `Float.NaN`, `Float.MIN_VALUE`, `Float.MIN_NORMAL`, `Float.MAX_VALUE` và các đối số `float` cho hàm `Math` có overload phù hợp. Dùng `Float.floatToIntBits` khi so biểu diễn. Hậu tố `f` như `0.1f` rất quan trọng: biểu thức có hằng `double` có thể khiến phép tính được thực hiện ở độ chính xác khác với mục tiêu đang kiểm thử.

Nếu kiểm tra API của thư viện, ghi kỳ vọng dựa trên hợp đồng API. Nếu kiểm tra hàm tự viết, ghi cả chính sách dữ liệu của ứng dụng. Một hàm có thể hợp lệ khi từ chối vô cực dù phép toán Java bên dưới xử lý được nó.

### Bài thực hành

1. Thêm hàm kiểm tra giá trị thuộc đoạn `[0, 1]`, chỉ nhận đầu vào hữu hạn. Viết trường hợp cho NaN, hai vô cực, hai dấu số không, `nextDown(0.0)`, `nextUp(0.0)`, `nextDown(1.0)`, `1.0`, `nextUp(1.0)`.
2. Thay phép so biểu diễn trong kiểm tra căn của `-0.0` bằng `==`, rồi chủ động đổi kết quả giả định thành `+0.0`. Giải thích vì sao bài kiểm tra mới có thể bỏ lọt lỗi dấu.
3. Chọn đơn vị đo cụ thể cho một phép tính gần đúng và giải thích hai ngưỡng sai số. Thêm một trường hợp ngay trong ngưỡng và một trường hợp vượt ngưỡng.
4. Tạo phiên bản thử `float`. Dự đoán trước những hằng giới hạn nào phải đổi, rồi chạy để kiểm chứng.

Khi hoàn thành, mỗi trường hợp cần trả lời được ba điều: vì sao chọn đầu vào này, kỳ vọng đến từ hợp đồng nào và phép xác nhận có phát hiện đúng loại lỗi đang nhắm tới không.
