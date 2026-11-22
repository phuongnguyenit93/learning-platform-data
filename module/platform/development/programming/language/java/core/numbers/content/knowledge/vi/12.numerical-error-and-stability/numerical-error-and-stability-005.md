# Tổng bù và tư tưởng Kahan summation

Khi cộng nhiều số thực trong Java bằng `double`, vòng lặp `sum += x` có thể tích lũy sai số làm tròn. Đặc biệt, một số nhỏ cộng vào tổng đang rất lớn có thể **không làm tổng thay đổi**, dù số nhỏ đó có ý nghĩa thực tế. **Kahan summation** (*compensated summation*, thuật toán cộng có bù) dùng thêm một biến để ghi nhận một phần sai lệch trong các phép cộng, rồi bù vào các lần cộng tiếp theo.

Ví dụ:

```java
double sum = 0.0;
for (int i = 0; i < 10; i++) {
    sum += 0.1;
}
System.out.println(sum); // 0.9999999999999999
```

Với cùng các phần tử, phiên bản Kahan trong bài cho kết quả `1.0`. Nhưng **Kahan không biến `double` thành số học chính xác tuyệt đối**: nó giảm một loại sai số khi cộng, không sửa được mọi sai số đầu vào hoặc mọi tình huống triệt tiêu.

## 1. Nguồn gốc của sai số khi tính tổng

`double` là kiểu dấu phẩy động nhị phân 64 bit với **53 bit độ chính xác phần trị hiệu dụng**. Không phải mọi số thập phân đều biểu diễn được bằng nhị phân hữu hạn: `0.1` chỉ được lưu thành một giá trị gần đúng. Sau đó mỗi phép cộng trên `double` còn có thể làm tròn kết quả sang số gần nhất biểu diễn được.

Có hai nguồn sai số cần phân biệt:

1. **Sai số biểu diễn:** giá trị nhập như `0.1` đã được chuyển sang một số nhị phân gần đúng. Kahan không khôi phục chính xác ý nghĩa thập phân gốc.
2. **Sai số phép cộng:** một số bit thấp của kết quả toán học có thể bị mất sau mỗi phép `+`. Kahan được thiết kế để hạn chế phần sai số tích lũy này.

Phép cộng số thực máy tính **không kết hợp tuyệt đối**:

```java
double a = 1e16;
double b = 1.0;
double c = -1e16;

double first = (a + b) + c;  // 0.0
double second = (a + c) + b; // 1.0
```

Về toán học, tổng đều bằng `1`. Nhưng ở độ lớn `1e16`, khoảng cách (ULP) giữa hai số `double` liên tiếp là **2**. Do đó `1e16 + 1.0` nằm giữa hai số có thể biểu diễn và được làm tròn về `1e16`. Nếu triệt tiêu hai số lớn trước, đóng góp `1.0` được giữ.

Một ví dụ thực tế hơn: cộng `10_000` giá trị `1.0` vào `1e16` bằng cách thường, từng số `1.0` có thể lần lượt bị bỏ qua do làm tròn. Kết quả chỉ còn `1e16` thay vì tổng toán học `1e16 + 10000`.

## 2. Ý tưởng: đừng vứt bỏ phần nhỏ sau mỗi phép cộng

Nếu `sum` rất lớn và `x` nhỏ, biểu thức `sum + x` có thể quay về chính `sum` vì độ phân giải của `double` tại đó không đủ. Kahan cố ghi lại **phần thay đổi mà phép cộng chưa đưa được vào tổng**, để hiệu chỉnh số hạng tiếp theo.

Thuật toán có hai biến trạng thái:

- `sum`: tổng xấp xỉ hiện tại.
- `compensation` (thường ký hiệu `c`): lượng bù có dấu theo dõi một phần mất mát do làm tròn. Đây **không phải sai số tuyệt đối thật** so với tổng toán học lý tưởng.

Với mỗi phần tử `x`, thực hiện đúng thứ tự:

```java
double y = x - compensation;
double t = sum + y;
compensation = (t - sum) - y;
sum = t;
```

Diễn giải:

1. `y = x - compensation`: điều chỉnh số hạng mới bằng lượng bù đã tích lũy.
2. `t = sum + y`: thực hiện phép cộng dấu phẩy động thông thường, vẫn có thể làm tròn.
3. `compensation = (t - sum) - y`: xác định phần khác biệt giữa lượng tăng được phản ánh và số hạng `y` muốn cộng.
4. `sum = t`: chấp nhận tổng mới, dùng cho lần lặp kế tiếp.

**Không cập nhật `sum` trước dòng tính `compensation`**. Dòng thứ ba cần giá trị `sum` trước khi đổi.

### Ví dụ bằng trực giác với `1e16` và các số `1`

Giả sử `sum = 1e16` và `compensation = 0`:

- Với `x = 1`, `y = 1`. Phép cộng `1e16 + 1` làm tròn về `1e16`, nên `t - sum = 0` và `compensation = -1`.
- Với số `x = 1` tiếp theo, `y = 1 - (-1) = 2`. Ở độ lớn `1e16`, bước tăng `2` có thể được biểu diễn, và phần đóng góp từ hai số `1` sẽ được phản ánh.
- Quá trình tiếp tục, thay vì bỏ từng số nhỏ như vòng lặp `sum += 1` thông thường.

Dấu âm của lượng bù trong ví dụ nghĩa là phần cộng bị thiếu sẽ được **cộng bổ sung** tại bước sau. Không nên xem `compensation` là một số luôn dương.

## 3. Hàm Kahan cơ bản trong Java 17+

```java
static double kahanSum(double[] values) {
    double sum = 0.0;
    double compensation = 0.0;

    for (double x : values) {
        double y = x - compensation;
        double t = sum + y;
        compensation = (t - sum) - y;
        sum = t;
    }

    return sum;
}
```

Đây là một **phương thức minh họa** cần đặt trong class. Mảng rỗng cho `0.0` theo cách khởi tạo này. Phiên bản cơ bản giả định đầu vào và các kết quả trung gian **hữu hạn**; cách xử lý `NaN`, vô cực và overflow cần chính sách riêng.

Hàm đối chiếu dùng phép cộng thường:

```java
static double naiveSum(double[] values) {
    double sum = 0.0;
    for (double x : values) {
        sum += x;
    }
    return sum;
}
```

Cả hai hàm đều đi qua các phần tử một lần, có **độ phức tạp thời gian `O(n)`** và dùng **bộ nhớ phụ `O(1)`**. Kahan tốn thêm một số phép trừ/cộng trên mỗi phần tử, đổi lại có thể giảm đáng kể sai số tích lũy.

**Điều Kahan không đảm bảo:** một kết quả `double` có 53 bit phần trị hiệu dụng vẫn có thể không biểu diễn được tổng toán học. Ví dụ `1e16 + 1` không có biểu diễn `double` chính xác; dù thuật toán biết “phần bị mất”, một số `double` trả về không thể lưu toàn bộ thông tin của tổng này. Kahan đặc biệt hữu ích khi **nhiều** phần nhỏ có thể được tích lũy và bù dần.

## 4. Chương trình Java hoàn chỉnh: so sánh cộng thường, Kahan và Neumaier

Lưu tệp `KahanDemo.java`:

```java
public class KahanDemo {
    static double naive(double[] values) {
        double sum = 0.0;
        for (double x : values) {
            sum += x;
        }
        return sum;
    }

    static double kahan(double[] values) {
        double sum = 0.0;
        double compensation = 0.0;

        for (double x : values) {
            double y = x - compensation;
            double t = sum + y;
            compensation = (t - sum) - y;
            sum = t;
        }
        return sum;
    }

    static double neumaier(double[] values) {
        double sum = 0.0;
        double correction = 0.0;

        for (double x : values) {
            double t = sum + x;
            if (Math.abs(sum) >= Math.abs(x)) {
                correction += (sum - t) + x;
            } else {
                correction += (x - t) + sum;
            }
            sum = t;
        }
        return sum + correction;
    }

    public static void main(String[] args) {
        double[] tenths = new double[10];
        java.util.Arrays.fill(tenths, 0.1);
        System.out.println("0.1 x 10 naive: " + naive(tenths));
        System.out.println("0.1 x 10 Kahan: " + kahan(tenths));

        double[] mixed = new double[10_001];
        mixed[0] = 1e16;
        java.util.Arrays.fill(mixed, 1, mixed.length, 1.0);
        System.out.println("large + ones naive extra: " + (naive(mixed) - 1e16));
        System.out.println("large + ones Kahan extra: " + (kahan(mixed) - 1e16));

        double[] cancel = {1e16, 1.0, -1e16};
        System.out.println("cancellation naive: " + naive(cancel));
        System.out.println("cancellation Kahan: " + kahan(cancel));
        System.out.println("cancellation Neumaier: " + neumaier(cancel));

        double[] finite = {1.0, 2.0, 3.0};
        System.out.println("simple Kahan: " + kahan(finite));
    }
}
```

Biên dịch/chạy bằng JDK 17 trở lên:

```bash
javac KahanDemo.java
java KahanDemo
```

Stdout:

```text
0.1 x 10 naive: 0.9999999999999999
0.1 x 10 Kahan: 1.0
large + ones naive extra: 0.0
large + ones Kahan extra: 10000.0
cancellation naive: 0.0
cancellation Kahan: 0.0
cancellation Neumaier: 1.0
simple Kahan: 6.0
```

Kết quả cho thấy:

- **Mười lần cộng `0.1`:** bản thường in giá trị hơi nhỏ hơn 1.0, Kahan in 1.0.
- **Một tổng `1e16` rồi thêm 10.000 số `1`:** bản thường không giữ được phần tăng; Kahan giữ lại đủ `10000.0` trong thử nghiệm.
- **Dãy `[1e16, 1, -1e16]`:** tổng toán học là 1, nhưng cả cộng thường lẫn Kahan cơ bản cho 0.0. Phiên bản Neumaier cho 1.0.
- **Dãy đơn giản `[1,2,3]`:** phép cộng không gặp vấn đề và Kahan cũng trả tổng đúng.

Không nên kết luận rằng Kahan luôn cho nhiều chữ số chính xác hơn trong mọi ví dụ chỉ vì những trường hợp đầu thành công.

## 5. Giới hạn quan trọng: triệt tiêu số lớn có thể đánh bại Kahan

Trường hợp `[1e16, 1, -1e16]` có tổng toán học 1.0, nhưng Kahan cơ bản trả 0.0. Nguyên nhân nằm ở cách cập nhật phần bù: khi số hạng `-1e16` xuất hiện, **bản thân phép điều chỉnh `y = x - compensation`** có thể làm tròn và mất thông tin của `1`. Sau đó hai số lớn triệt tiêu, nhưng phần nhỏ không còn nằm trong tổng.

Đây là lý do Kahan không phải một “thuật toán tổng chính xác” nói chung. Sai số với dãy **đổi dấu, triệt tiêu mạnh hoặc có độ lớn thay đổi đột ngột** có thể phức tạp hơn các trường hợp chỉ cộng số dương.

Một phương pháp liên quan là **Neumaier summation**, sử dụng biến `correction` để tích lũy lượng bù riêng ngoài tổng:

```java
static double neumaierSum(double[] values) {
    double sum = 0.0;
    double correction = 0.0;

    for (double x : values) {
        double t = sum + x;
        if (Math.abs(sum) >= Math.abs(x)) {
            correction += (sum - t) + x;
        } else {
            correction += (x - t) + sum;
        }
        sum = t;
    }

    return sum + correction;
}
```

Neumaier kiểm tra độ lớn của hai toán hạng để chọn cách ước lượng lượng mất do cộng, rồi **cộng phần hiệu chỉnh khi trả kết quả**. Điều này giúp trong một số trường hợp triệt tiêu mà Kahan cơ bản thất bại. Tuy vậy, `correction` vẫn là `double`, cũng có thể làm tròn; **Neumaier không luôn đạt tổng toán học chính xác**.

Sự khác biệt có thể tóm tắt:

| Phương pháp | Cách giữ bù | Điểm mạnh | Hạn chế |
| --- | --- | --- | --- |
| `sum += x` | Không có biến bù | Đơn giản, nhanh | Dễ mất số nhỏ |
| Kahan | Điều chỉnh số hạng kế tiếp bằng `compensation` | Giảm sai số tích lũy trên nhiều dãy | Có dãy triệt tiêu khó vẫn sai |
| Neumaier | Tích lũy `correction` riêng, cuối cùng cộng vào tổng | Có thể xử lý một số trường hợp triệt tiêu tốt hơn | Cũng bị giới hạn bởi `double` và thứ tự số học |

## 6. Sai số, độ ổn định và thứ tự cộng

Tính chất cơ bản của tổng số thực máy tính là **thứ tự ảnh hưởng kết quả**. Xét `[1e16, 1, -1e16]`: thay đổi thứ tự thành `[1e16, -1e16, 1]` có thể cho kết quả đúng 1.0 ngay với cộng thường. Nhưng không nên tự ý sắp xếp lại đầu vào nếu thứ tự mang ý nghĩa nghiệp vụ, hoặc cho rằng có một thứ tự tối ưu cho mọi dãy.

Về mặt thuật toán, cần phân biệt:

- **Sai số tuyệt đối:** `|computed - reference|` khi biết giá trị tham chiếu đủ chính xác.
- **Sai số tương đối:** sai số tuyệt đối chia cho độ lớn tổng tham chiếu, thường không có ý nghĩa tốt nếu tổng thật gần 0.
- **Mức độ điều kiện của bài toán:** tổng của nhiều số lớn với dấu trái chiều có thể gần 0; chỉ một thay đổi rất nhỏ ở dữ liệu đầu vào cũng khiến sai số tương đối tăng mạnh.
- **Sai số của phép tính:** phần phát sinh thêm khi thuật toán dùng các phép dấu phẩy động, là điều Kahan cố hạn chế.

Có thể chọn Kahan để **ổn định hơn** trong một miền dữ liệu mà vẫn không có bảo đảm “đúng tuyệt đối”. Nếu đầu vào đã bị làm tròn từ phép đo hoặc khi chuyển từ số nguyên lớn sang `double`, tổng bù không thể khôi phục chính xác giá trị đầu vào ban đầu.

### Hiệu năng và khả năng tái lập

Cộng Kahan tuần tự dùng **`O(n)` thời gian**, **`O(1)` bộ nhớ phụ**. Nó làm nhiều phép toán hơn cộng thường và trạng thái bù phụ thuộc **thứ tự**. Vì vậy không được cho nhiều luồng tùy ý cập nhật chung `sum`/`compensation`: ngoài data race, nó còn phá trình tự tính bù.

Trong parallel reduction, có thể tính các tổng con riêng rồi kết hợp có kiểm soát. Tuy nhiên, kết quả cuối có thể khác bit so với phép cộng tuần tự do thứ tự nhóm phép cộng khác. Nếu cần tính tái lập, hãy quy định rõ thứ tự/chiến lược reduction, và kiểm thử với chính thuật toán đó.

## 7. Khi nào không nên dùng Kahan làm giải pháp duy nhất?

### `NaN`, vô cực và tràn số

Công thức bù có phép trừ `t - sum`. Nếu `sum` hoặc `t` trở thành vô cực, phép `Infinity - Infinity` có thể tạo NaN và sau đó làm `compensation` hoặc kết quả cuối thành NaN. Kahan **không có nhiệm vụ** xử lý ngoại lệ dữ liệu số thực.

Với ứng dụng chỉ chấp nhận số hữu hạn:

```java
for (double x : values) {
    if (!Double.isFinite(x)) {
        throw new IllegalArgumentException("non-finite input");
    }
}
```

Đây là mảnh mã trong phương thức. Kiểm tra đầu vào hữu hạn chưa bảo đảm các **phép cộng trung gian không overflow**; cần đánh giá miền dữ liệu và kiểm tra kết quả theo yêu cầu hệ thống. Không biến NaN thành 0 nếu điều đó không được chính sách dữ liệu cho phép.

### Số thập phân chính xác: dùng biểu diễn phù hợp

Nếu bài toán yêu cầu cộng chính xác các số thập phân từ chuỗi (ví dụ tiền tệ), cân nhắc `BigDecimal`:

```java
java.math.BigDecimal total = java.math.BigDecimal.ZERO;
for (int i = 0; i < 10; i++) {
    total = total.add(new java.math.BigDecimal("0.1"));
}
System.out.println(total); // 1.0
```

Đây là **mảnh mã minh họa**, cần đặt trong phương thức. `new BigDecimal("0.1")` chứa giá trị thập phân một phần mười đúng theo chuỗi. **`new BigDecimal(0.1)` không tương đương** vì constructor nhận `double` phản ánh giá trị nhị phân gần `0.1` đã được lưu; nếu nguồn là chuỗi thập phân thì hãy parse trực tiếp từ chuỗi để giữ ý nghĩa nguồn.

Với số lượng nguyên, có thể dùng `long`, `BigInteger` hoặc đơn vị nguyên phù hợp, và kiểm tra overflow. Dùng đúng kiểu dữ liệu từ đầu có thể đơn giản hơn việc cố bù sai số của `double`.

### Tổng chính xác hơn bằng thuật toán khác

Ngoài Neumaier, **pairwise summation** chia dãy thành các nhóm rồi cộng các tổng con theo cây cân bằng; nó thường cải thiện sai số so với cộng tuần tự, đặc biệt với dãy dài, và phù hợp hơn với một số mô hình chia để trị. Nhưng kết quả vẫn phụ thuộc cách nhóm và không chính xác tuyệt đối.

Có thể cân nhắc thư viện/hệ thống có **accumulator mở rộng độ chính xác** nếu miền yêu cầu rất chặt chẽ; thuật toán tổng bù cơ bản không đảm bảo mọi mẫu bit đầu vào được cộng chính xác trước khi làm tròn kết quả cuối cùng.

## 8. Dùng trong tổng thống kê và trung bình

Nếu tính trung bình của dãy `n > 0`, viết:

```java
double mean = kahanSum(values) / values.length;
```

Dòng này cải thiện khâu tính tổng so với vòng lặp thường trong những dãy phù hợp. Nhưng phép chia cuối vẫn tạo số `double` làm tròn. Nếu tổng trung gian có thể overflow thành vô cực dù trung bình nằm trong phạm vi, nên dùng cách tính trung bình được thiết kế để tránh overflow trung gian; Kahan cơ bản không giải quyết trường hợp đó.

Trong dữ liệu cảm biến, thống kê mô phỏng, cộng thời gian hoặc tổng các đại lượng có độ lớn thay đổi, Kahan có thể là lựa chọn tốt nhờ bộ nhớ phụ nhỏ. Tuy nhiên, cần phân biệt **độ chính xác số học** với **độ tin cậy của phép đo**: thuật toán không xóa lỗi cảm biến, NaN hoặc sai số do dữ liệu nhập.

### Kế hoạch kiểm thử hữu ích

Đánh giá thuật toán trên những dãy có ý nghĩa rõ ràng:

1. Dãy ngắn chính xác: `[1, 2, 3]` → 6.
2. Dãy thập phân: mười số `0.1`.
3. Chênh lệch lớn: `1e16` cộng nhiều số `1.0`.
4. Triệt tiêu mạnh: `[1e16, 1, -1e16]`.
5. Dãy âm/dương, dãy dài, dữ liệu sắp xếp theo các thứ tự khác nhau.
6. Dữ liệu có NaN, Infinity và giá trị rất gần biên (nếu là đầu vào có thể xảy ra).

Khi có thể, sử dụng tổng tham chiếu bằng số học chính xác hoặc độ chính xác cao từ **dữ liệu nguồn đáng tin**, rồi đo sai số tuyệt đối và tương đối. Đừng mặc định một thuật toán đúng chỉ vì nó trùng kết quả thuật toán khác.

## 9. Những nhầm lẫn thường gặp

1. **“`double` luôn cộng chính xác các số nguyên nhỏ.”** Sai: dù từng số `1` biểu diễn được chính xác, `1e16 + 1` vẫn bị làm tròn.
2. **“Kahan khiến `0.1` có biểu diễn thập phân chính xác.”** Sai: nó không đổi bit của giá trị đầu vào.
3. **“Chỉ cần thêm biến `compensation` thì tổng mọi dãy đều đúng.”** Sai: `[1e16, 1, -1e16]` vẫn cho 0.0 với Kahan cơ bản.
4. **“`compensation` chính là tổng sai số tuyệt đối.”** Sai: đó là trạng thái hiệu chỉnh có dấu; không phải giá trị tham chiếu toán học.
5. **“Có thể cập nhật `sum` trước khi tính `compensation`.”** Sai: công thức cần tổng cũ.
6. **“Kahan không phụ thuộc thứ tự cộng.”** Sai: các phép tính vẫn có làm tròn và kết quả có thể phụ thuộc thứ tự.
7. **“Neumaier luôn chính xác tuyệt đối.”** Sai: vẫn có các phép `double` và sai số.
8. **“`BigDecimal` tạo từ `double` bất kỳ sẽ phục hồi các chữ số đã mất.”** Sai: nguồn đã làm tròn không thể tự đảo ngược.
9. **“Kahan phù hợp để âm thầm bỏ qua NaN và vô cực.”** Sai: cần chính sách xử lý đầu vào rõ ràng.
10. **“Kahan có thể cập nhật chung `sum` từ nhiều luồng mà vẫn ổn.”** Sai: phụ thuộc trình tự bù và có nguy cơ data race.
11. **“Khi in ra `1.0`, ta đã chứng minh mọi bước tính chính xác.”** Sai: đó chỉ là một giá trị biểu diễn cuối cùng.
12. **“Độ chính xác của tổng và độ chính xác của dữ liệu cảm biến là cùng một thứ.”** Sai: thuật toán cộng không sửa được sai số đo ban đầu.

## 10. Câu hỏi tự kiểm tra

**1. Vì sao `1e16 + 1` có thể bằng `1e16` trong `double`?** Vì ULP gần `1e16` là 2, nên phần tăng 1 có thể bị làm tròn mất.

**2. Vai trò của `compensation` là gì?** Lưu một phần sai lệch do phép cộng đã làm tròn, để điều chỉnh số hạng ở lần cộng tiếp theo.

**3. Vì sao phải tính `compensation = (t - sum) - y` trước `sum = t`?** Vì công thức cần `sum` cũ.

**4. Dãy mười giá trị `0.1` có luôn được lưu chính xác như thập phân trong `double` nhờ Kahan không?** Không; các giá trị đầu vào vẫn là số nhị phân gần `0.1`.

**5. Với `[1e16, 1, -1e16]`, tổng toán học và tổng Kahan là gì?** Tổng toán học là 1; Kahan cơ bản trong ví dụ cho 0.0, Neumaier cho 1.0.

**6. Bộ nhớ phụ Kahan phụ thuộc `n` như thế nào?** `O(1)` khi cộng tuần tự vì chỉ thêm một biến bù.

**7. Nếu cần tổng chính xác các giá trị thập phân từ chuỗi, nên dùng gì?** Một biểu diễn thập phân chính xác phù hợp như `BigDecimal` từ chuỗi, hoặc số nguyên theo đơn vị quy ước nếu thích hợp.

**8. Nếu đầu vào có vô cực, có thể tin rằng Kahan sẽ cho kết quả hợp lý hơn cộng thường không?** Không. Các phép cộng/trừ bù có thể đưa `compensation` thành NaN; phải kiểm tra miền và xử lý ngoại lệ theo bài toán.

**Ghi nhớ:** Kahan summation dùng **tổng `sum` và lượng bù `compensation`** để giảm tác hại của sai số làm tròn tích lũy. Nó thường tốt hơn cộng tuần tự trong dãy dài có giá trị chênh lệch độ lớn, vẫn chạy `O(n)` và dùng `O(1)` bộ nhớ phụ. Tuy nhiên, nó **không biến số thực máy tính thành số học chính xác**, không bảo đảm xử lý triệt tiêu mạnh, NaN/Infinity hoặc overflow. Chọn Kahan, Neumaier, pairwise hay biểu diễn số chính xác dựa trên **yêu cầu sai số, dữ liệu và miền giá trị**.
