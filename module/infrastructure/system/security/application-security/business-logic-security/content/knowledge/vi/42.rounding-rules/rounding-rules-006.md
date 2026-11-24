# Làm tròn khi quyết toán — Settlement rounding

## 1. Bài toán cần bảo vệ

Settlement rounding là việc đưa số tiền quyết toán về đơn vị mà sổ tiền hoặc tuyến chuyển tiền chấp nhận, theo một chính sách đã xác định. Số tiền trước bước này có thể có phần lẻ phát sinh từ phí theo tỷ lệ, phân bổ doanh thu, chuyển đổi ngoại tệ hoặc kết chuyển từ kỳ trước.

Ví dụ giả định một bên nhận có khoản được hưởng 100,01 USD và phí được tính chính xác tại bước tính toán là 2,345 USD:

```text
Nghĩa vụ trước làm tròn: 100.01 - 2.345 = 97.665 USD
Đơn vị quyết toán:      0.01 USD
Quy tắc HALF_EVEN:      97.665 → 97.66 USD
Điều chỉnh tính toán:   97.66 - 97.665 = -0.005 USD
```

Nếu một thành phần khác làm tròn phí trước thành 2,34 USD, kết quả lại là 97,67 USD. Cả hai đường tính đều có thể dùng số thập phân chính xác nhưng khác chính sách về **thời điểm làm tròn**. Hệ thống phải biết hợp đồng nghiệp vụ yêu cầu đường nào, không để từng service tự chọn.

Trong chương **Rounding Rules**, mục tiêu bảo mật là ngăn phần lẻ trở thành cơ hội lạm dụng: chia nhỏ yêu cầu để nhận thêm tiền, chọn cách làm tròn có lợi, thay phạm vi batch, sửa khoản điều chỉnh hoặc retry để quyết toán hai lần.

Các chính sách và số liệu trong bài là ví dụ kỹ thuật. Quy tắc thực tế phải được xác định theo sản phẩm, thỏa thuận quyết toán, đơn vị tiền và khả năng tuyến xử lý. Không có một rounding mode đúng cho mọi hệ thống.

## 2. Xác định đúng đối tượng được làm tròn

### 2.1. Quyết toán là một nghĩa vụ có phạm vi

Một phạm vi quyết toán có thể được nhận diện bởi:

```text
tenant + pháp nhân + bên nhận + tài khoản nhận
+ settlement currency + kỳ/cửa sổ quyết toán
+ nhóm nghiệp vụ được phép bù trừ + tuyến xử lý
```

Không phải mọi hệ thống đều dùng toàn bộ các chiều này, nhưng những chiều có ảnh hưởng phải được xác định ở server. Không gộp hai merchant, hai pháp nhân hoặc hai currency chỉ để giảm phần lẻ, trừ khi có một nghiệp vụ bù trừ được định nghĩa và cấp quyền rõ ràng.

Phạm vi làm tròn có thể là từng sự kiện, từng khoản phí, mỗi bên nhận trong một batch hoặc tổng cuối kỳ. Nó là một phần của chính sách. Việc chuyển từ làm tròn tổng kỳ sang làm tròn từng request có thể làm thay số tiền, dù cùng rounding mode và cùng số giao dịch gốc.

### 2.2. Một phương trình cần rõ dấu và đơn vị

Với mọi thành phần đã ở cùng settlement currency, đặt:

```text
G = tổng khoản được hưởng trước các khoản khấu trừ
F = phí phải khấu trừ
H = hoàn tiền/đảo nghĩa vụ được đưa vào kỳ
V = phần giữ lại theo chính sách reserve
A = điều chỉnh nghiệp vụ có dấu, đã được phê duyệt
C = kết chuyển từ kỳ trước có dấu theo hợp đồng

N = G - F - H - V + A + C
P = Q(N)
R = P - N

P = N + R
```

`Q` là hàm làm tròn đã được phê duyệt. `R` dương nghĩa là kết quả lớn hơn giá trị trước bước làm tròn; `R` âm nghĩa là nhỏ hơn. Quy ước này phải được dùng nhất quán trong tính toán, audit và đối soát.

Phương trình chỉ đúng sau khi mỗi thành phần đã được phân loại và quy đổi theo đúng quy tắc. Không cộng trực tiếp phí USD với doanh thu VND. Nếu có FX, cần dữ liệu tỷ giá/báo giá có thẩm quyền, chiều chuyển đổi, phí, thời điểm và thứ tự làm tròn tương ứng.

Nếu `N` bằng không hoặc âm, không tự biến nó thành một lệnh chi tiền dương bằng `abs()`. Cần chính sách cho số dư âm, kết chuyển, thu hồi hoặc không tạo payout. Đó là quyết định nghiệp vụ riêng.

### 2.3. Ba mức đơn vị cần phân biệt

| Mức | Ví dụ giả định | Vai trò |
| --- | --- | --- |
| Độ chính xác tính toán | Phí nội bộ 2,345 USD | Giữ đủ dữ liệu trước ranh giới làm tròn |
| Đơn vị lưu/ghi sổ | Một đơn vị nhỏ nhất là 0,01 USD | Biểu diễn tiền đã được chốt trong book tương ứng |
| Quantum chuyển tiền | Bội số 0,01 hoặc một mức khác theo tuyến | Khoản chuyển cuối phải chia hết cho bước này |

Quantum là bước lượng tử hóa, ký hiệu `q`. Một quantum giả định 0,05 không được bảo đảm chỉ bằng `setScale(2)`: số 1,02 có hai chữ số thập phân nhưng không phải bội của 0,05. Không suy quy tắc quyết toán ngân hàng từ quy tắc làm tròn tiền mặt của một sản phẩm khác.

## 3. Chính sách làm tròn phải đầy đủ và có phiên bản

Một cấu hình chỉ có `scale=2` chưa mô tả đủ quyết toán. Cần trả lời các câu hỏi sau:

| Thành phần chính sách | Câu hỏi cần chốt |
| --- | --- |
| Currency và đơn vị lưu trữ | Số nguyên cuối cùng đại diện cho đơn vị nào? |
| Quantum | Kết quả phải là bội của bao nhiêu đơn vị tiền? |
| Mode | Xử lý phần lẻ và trường hợp đúng giữa hai mốc như thế nào? |
| Ranh giới tính | Làm tròn từng phí, từng giao dịch hay tổng của phạm vi nào? |
| Thứ tự phép tính | Khấu trừ, FX, phân bổ và làm tròn diễn ra theo thứ tự nào? |
| Dữ liệu nguồn | Sự kiện nào đủ điều kiện, có phiên bản và mốc cắt nào? |
| Phân bổ phần dư | Ai nhận thêm một đơn vị, xử lý đồng hạng ra sao? |
| Kết chuyển/điều chỉnh | Phần chênh bị tất toán hay vẫn còn là nghĩa vụ? |
| Giới hạn | Miền giá trị, hạn mức payout, ngưỡng ngoại lệ nào được áp dụng? |
| Hiệu lực và phê duyệt | Ai phát hành chính sách, áp từ khi nào và cho batch nào? |

Rounding policy phải gắn với snapshot quyết toán. Nếu cấu hình thay đổi khi batch đang chờ duyệt, cần chính sách chuyển tiếp: giữ snapshot đã có hiệu lực hoặc tính lại và phê duyệt lại. Không tự tính bằng mode mới rồi dùng phê duyệt dành cho số tiền cũ.

### 3.1. Mode có ảnh hưởng đến cả số âm

Ví dụ làm tròn về 0,01:

| Mode | `2.345` | `-2.345` | Ý nghĩa |
| --- | ---: | ---: | --- |
| `HALF_UP` | 2.35 | -2.35 | Gần nhất; nếu đúng giữa thì ra xa số 0 |
| `HALF_EVEN` | 2.34 | -2.34 | Gần nhất; nếu đúng giữa thì chọn bội có chỉ số chẵn |
| `DOWN` | 2.34 | -2.34 | Về phía số 0 |
| `FLOOR` | 2.34 | -2.35 | Về phía âm vô cùng |

Với `HALF_EVEN`, `2.355` lại thành `2.36`. Tên `DOWN` không đồng nghĩa với “giảm giá trị đại số” cho số âm. Xem [tài liệu Java về RoundingMode](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/math/RoundingMode.html).

Một mode có thể giảm thiên lệch trên một phân bố dữ liệu nhất định nhưng không tự chống được người cố ý chọn phần lẻ hoặc cách chia nhóm. Không dùng lý do “đã dùng HALF_EVEN” để bỏ kiểm tra chia nhỏ quyết toán.

### 3.2. Giới hạn sai số chỉ đúng với ranh giới được xác định

Với phép làm tròn gần nhất về quantum `q`:

```text
abs(Q(x) - x) <= q / 2
```

Đây là giới hạn cho **một lần** làm tròn gần nhất. Nó không phải quyền chấp nhận mọi chênh lệch giữa số tiền nhà cung cấp báo về với nghĩa vụ dự kiến. Nó cũng không phải giới hạn áp dụng nguyên xi cho `DOWN` hoặc `FLOOR`.

Nếu làm tròn nhiều bước hoặc nhiều dòng, cần phân tích sai số theo toàn bộ công thức. Một ngưỡng hằng số `0.01` không có currency, quantum, số ranh giới tính và lý do cụ thể không đủ làm bằng chứng rằng chênh lệch là hợp lệ.

## 4. Thời điểm làm tròn và cách chia batch có thể đổi kết quả

### 4.1. Làm tròn tổng khác tổng các số đã làm tròn

Với ba khoản được hưởng, mỗi khoản 0,005 USD và mode `HALF_UP`:

```text
Làm tròn từng khoản:
    0.005 → 0.01
    0.005 → 0.01
    0.005 → 0.01
    Tổng = 0.03 USD

Cộng trước, làm tròn một lần:
    0.005 + 0.005 + 0.005 = 0.015
    0.015 → 0.02 USD
```

Nếu chính sách yêu cầu quyết toán tổng kỳ, nhưng API cho bên nhận biến mỗi khoản thành một payout riêng, họ có thể nhận thêm tiền chỉ nhờ thay cách đóng gói. Tất cả request vẫn có thể hợp lệ về kiểu dữ liệu và được thực hiện bởi đúng chủ tài khoản.

Giải pháp là cố định phạm vi tính theo nghĩa vụ có thẩm quyền và quản lý số dư/phần lẻ trong phạm vi đó. Rate limit có thể giảm lưu lượng lạm dụng nhưng không sửa phép tính cho mỗi lần được phép gọi.

### 4.2. Tránh làm tròn hai lần ngoài chính sách

Ví dụ với `HALF_UP`:

```text
Đi thẳng về hai chữ số:
    1.2449 → 1.24

Qua một bước trung gian ba chữ số:
    1.2449 → 1.245 → 1.25
```

Bước trung gian đã thay thông tin cần cho quyết định cuối. Không tự thêm `setScale` vào từng helper chỉ để làm dữ liệu dễ lưu hoặc dễ hiển thị. Ranh giới nào được phép mất độ chính xác phải thuộc chính sách.

Với phép chia không có biểu diễn thập phân hữu hạn, cần biểu diễn hữu tỷ hoặc độ chính xác trung gian có quy tắc và giới hạn sai số được xác định. Chọn tùy ý nhiều chữ số thập phân chưa chứng minh được kết quả cuối đúng ở mọi điểm sát ranh giới.

## 5. Phân bổ số tiền đã chốt mà không tạo hoặc làm mất tổng

Sau khi chốt tổng quyết toán, có thể cần chia tổng đó cho các dòng chi tiết trong **cùng phạm vi được phép phân bổ**. Các dòng phải cộng lại đúng tổng đã chốt.

Ví dụ chia 1,00 USD cho ba thành phần có trọng số bằng nhau, với đơn vị phân bổ là cent:

| Dòng | Phần lý tưởng | Phần nguyên ban đầu | Kết quả sau phân bổ |
| --- | --- | ---: | ---: |
| A | 100/3 cent | 33 cent | 34 cent |
| B | 100/3 cent | 33 cent | 33 cent |
| C | 100/3 cent | 33 cent | 33 cent |
| **Tổng** | **100 cent** | **99 cent** | **100 cent** |

Một cách thực hiện là phương pháp phần dư lớn nhất, dùng số nguyên để không xấp xỉ `1/3`:

```text
T = tổng số đơn vị cần phân bổ, T >= 0
w[i] = trọng số nguyên dương của dòng i
W = SUM(w[i])

numerator[i] = T * w[i]
base[i]      = numerator[i] DIV W
remainder[i] = numerator[i] MOD W

delta = T - SUM(base[i])
Sắp dòng theo remainder giảm dần
Nếu bằng nhau, dùng khóa ổn định do server kiểm soát
Cộng 1 đơn vị cho delta dòng đầu

SUM(result[i]) = T
```

Nếu quantum lớn hơn một đơn vị nhỏ nhất, trước hết biểu diễn tổng bằng số quantum nguyên, phân bổ trên đơn vị đó rồi nhân lại. Tổng đầu vào phải chia hết quantum. Không phân bổ theo cent rồi giả định mỗi dòng đã đáp ứng điều kiện chuyển tiền theo bước 0,05.

Khóa phá hòa phải được định nghĩa, chẳng hạn ID sự kiện ổn định do server cấp. Không dùng thứ tự mảng do caller gửi, vì người gọi có thể sắp lại để luôn nhận phần dư có lợi. Tính quyết định giúp retry ra cùng kết quả, nhưng nếu caller được tạo vô hạn dòng/trọng số hoặc chọn thời điểm chia nhóm thì vẫn có thể thao túng; cần bảo vệ cả dữ liệu phân bổ.

Thuật toán trên dành cho trọng số dương và tổng không âm. Số âm, hạn mức từng dòng, mức chuyển tối thiểu hoặc quy tắc ưu tiên riêng cần mô hình khác được xác định rõ. Không chạy trên trị tuyệt đối rồi gắn dấu trở lại cho mọi trường hợp.

Phân bổ tổng đã chốt khác với ép các dòng khớp một tổng tùy ý. Nếu tổng của nhà cung cấp chứa phí hoặc reserve chưa được phân loại, không lấy phần chênh đó rải vào các dòng dưới tên “rounding”.

## 6. Ví dụ Java: làm tròn theo quantum có kiểm soát

Ví dụ Java 17 dưới đây thực hiện một ranh giới làm tròn gần nhất. Nó chỉ hỗ trợ hai mode đã chọn cho ví dụ, không cho caller tùy ý gửi mọi mode của JDK.

```java
import java.math.BigDecimal;
import java.math.BigInteger;
import java.math.RoundingMode;
import java.util.Objects;

final class SettlementRounding {
    record Policy(
        String version,
        String currency,
        int currencyScale,
        BigInteger quantumMinor,
        RoundingMode mode
    ) {
        Policy {
            Objects.requireNonNull(version);
            Objects.requireNonNull(currency);
            Objects.requireNonNull(quantumMinor);
            Objects.requireNonNull(mode);

            if (version.isBlank() || !currency.matches("[A-Z]{3}")) {
                throw new IllegalArgumentException("INVALID_POLICY_IDENTITY");
            }
            // Đây là miền hỗ trợ của sản phẩm minh họa.
            if (currencyScale < 0 || currencyScale > 9
                    || quantumMinor.signum() <= 0
                    || quantumMinor.toString().length() > 30) {
                throw new IllegalArgumentException("INVALID_QUANTUM");
            }
            if (mode != RoundingMode.HALF_EVEN
                    && mode != RoundingMode.HALF_UP) {
                throw new IllegalArgumentException("MODE_NOT_APPROVED");
            }
        }
    }

    record Result(
        BigDecimal rawNet,
        BigDecimal payable,
        BigDecimal roundingAdjustment,
        BigInteger payableMinor,
        Policy policy
    ) {}

    static Result calculate(BigDecimal rawNet, Policy policy) {
        Objects.requireNonNull(rawNet);
        Objects.requireNonNull(policy);

        // Giới hạn đầu vào tính toán; không thay thế kiểm tra nguồn tiền.
        if (rawNet.precision() > 50
                || rawNet.scale() < 0 || rawNet.scale() > 18) {
            throw new IllegalArgumentException("INVALID_CALCULATION_RANGE");
        }

        BigDecimal quantum = new BigDecimal(
            policy.quantumMinor(), policy.currencyScale()
        );

        BigDecimal quantumCount = rawNet.divide(
            quantum, 0, policy.mode()
        );
        BigDecimal payable = quantumCount.multiply(quantum)
            .setScale(policy.currencyScale(), RoundingMode.UNNECESSARY);
        BigInteger payableMinor = payable
            .movePointRight(policy.currencyScale()).toBigIntegerExact();

        if (payableMinor.abs().toString().length() > 30) {
            throw new IllegalArgumentException("PAYABLE_OUT_OF_RANGE");
        }

        return new Result(
            rawNet,
            payable,
            payable.subtract(rawNet),
            payableMinor,
            policy
        );
    }
}
```

Cách dùng với chính sách lấy từ nguồn tin cậy:

```java
var policy = new SettlementRounding.Policy(
    "settlement-rounding-v4",
    "USD",
    2,
    BigInteger.ONE,
    RoundingMode.HALF_EVEN
);

var result = SettlementRounding.calculate(
    new BigDecimal("97.665"), policy
);
// payable = 97.66
// payableMinor = 9766
// roundingAdjustment = -0.005
```

Nếu `quantumMinor=5` và scale bằng 2 thì quantum là 0,05. Hàm sẽ làm tròn theo bội 0,05, thay vì chỉ cắt về hai chữ số thập phân.

`BigDecimal` cho phép quy định rõ scale và mode. Phép chia chính xác không có mode có thể thất bại với kết quả thập phân vô hạn; phép chia trong ví dụ chủ động làm tròn số quantum về một số nguyên. Xem [tài liệu Java về BigDecimal](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/math/BigDecimal.html).

Các tiền điều kiện và giới hạn của ví dụ:

- `rawNet` đã được tính đúng theo thứ tự, nguồn và độ chính xác trung gian của chính sách. Hàm không sửa sai số đã phát sinh trước đó.
- Policy được server nạp theo phạm vi quyết toán. Kiểm tra chuỗi ba chữ hoa không chứng minh currency được phép hoặc metadata đúng.
- Giới hạn precision/scale chỉ là miền hỗ trợ minh họa; các tầng nhận dữ liệu vẫn cần giới hạn độ dài trước khi tạo đối tượng số.
- Hàm chấp nhận số âm để mô hình hóa kết quả tính toán; luồng tạo payout phải quyết định riêng có được phát sinh lệnh chi hay không.
- Kết quả chưa bao gồm quyền đối tượng, chọn batch, phân bổ, transaction, idempotency, phê duyệt hoặc hạch toán.
- `roundingAdjustment` có thể nhỏ hơn đơn vị ghi sổ; lưu được trong kết quả tính không có nghĩa có thể ghi nguyên giá trị đó thành một dòng ledger.

### 6.1. Không để DB tự chọn rounding mode thay ứng dụng

Cột decimal có scale cố định có thể làm tròn khi giá trị được ép về scale của cột. Trong PostgreSQL, kiểu `numeric` xử lý trường hợp đúng giữa bằng cách ra xa số 0; điều này có thể khác `HALF_EVEN` ở Java. Xem [PostgreSQL: Numeric Types](https://www.postgresql.org/docs/18/datatype-numeric.html).

Nếu policy yêu cầu `HALF_EVEN`, không ghi thẳng `97.665` vào một cột hai số lẻ rồi giả định DB tạo đúng `97.66`. Cần chốt giá trị ở đúng ranh giới, kiểm tra biểu diễn cuối và lưu các trường nguồn/điều chỉnh với độ chính xác thích hợp. SQL, Java, adapter và công cụ đối soát phải dùng cùng hợp đồng tính.

## 7. Từ tính toán tới gửi quyết toán: state machine và transaction

Một state machine minh họa:

```text
+ DRAFT → CALCULATED → APPROVED → SUBMITTED → SETTLED
+            |            |
+            └→ REVISED ←──┘  nếu thay dữ liệu quan trọng trước khi gửi
+
+ SUBMITTED → UNKNOWN  khi chưa rõ kết quả bên ngoài
+ UNKNOWN   → SETTLED hoặc FAILED_CONFIRMED sau xác minh
```

Không cho caller chuyển trực tiếp từ `DRAFT` sang `SETTLED`. Tính xong payout cũng chưa chứng minh tiền đã đến bên nhận. Một kết quả timeout không đủ để kết luận thất bại và tạo lệnh mới.

### 7.1. Chốt tập nguồn trước khi duyệt

Một snapshot quyết toán cần giữ các sự kiện nghĩa vụ đã được chọn, mốc cắt/watermark, phí và FX có liên quan, policy version, kết quả làm tròn và cách phân bổ. Không để một truy vấn “lấy mọi dòng đang đủ điều kiện” chạy lại sau phê duyệt rồi làm đổi số tiền.

Việc gán nguồn vào batch phải có thao tác nguyên tử hoặc unique constraint tương ứng để hai worker không cùng quyết toán một nghĩa vụ. Nếu nghiệp vụ cho phép quyết toán một phần, cần định danh phần nghĩa vụ do server quản lý và theo dõi phần còn lại; không mở lại toàn bộ nguồn chỉ vì một batch chưa thanh toán hết.

Sự kiện đến muộn sau mốc cắt được đưa vào kỳ hoặc nghiệp vụ điều chỉnh theo chính sách. Không lén chèn thêm vào snapshot đã được duyệt. Một hash nội dung có thể giúp so khớp phiên bản, nhưng vẫn phải có dữ liệu nguồn và kiểm soát quyền.

### 7.2. Tính toán và chốt lệnh tiền

Có thể tách bước tính/duyệt với bước chốt lệnh gửi, nhưng mỗi bước cần transaction phù hợp:

```text
+ Tính snapshot:
+   Khóa phạm vi cần bảo vệ và claim các nghĩa vụ đủ điều kiện
+   Tính theo policy được chọn, kiểm tra tổng và quantum
+   Lưu snapshot, phân bổ và phiên bản để phê duyệt
+
+ Chốt lệnh từ snapshot đã duyệt:
+ BEGIN
+   Claim idempotency key hoặc trả kết quả đã có sau kiểm tra quyền
+   Khóa settlement và trạng thái kết chuyển/nghĩa vụ liên quan
+   Kiểm tra đúng APPROVED, đúng phiên bản và đúng nội dung đã duyệt
+   Kiểm tra bên nhận, route, hạn mức và chính sách hiệu lực
+   Dùng số tiền đã chốt; không lấy policy mới để tính lại ngầm
+   Tạo duy nhất một instruction cho settlement version này
+   Ghi các thay đổi nghĩa vụ/ledger theo mô hình kế toán được chọn
+   Ghi kết chuyển hoặc điều chỉnh đúng một lần
+   Ghi outbox và kết quả idempotency
+ COMMIT
+
+ Worker gửi instruction với danh tính idempotency ổn định
```

Kết chuyển phải được nhận diện là đã có hiệu lực ở bước nào. Bấm xem preview hoặc tính lại một snapshot chưa được chốt không được cộng thêm phần dư vào số dư thực. Nếu có cơ chế giữ chỗ nghĩa vụ ngay khi tính, nó cũng phải có trạng thái, quyền giải phóng và chống claim trùng.

Không giữ transaction DB chờ một lời gọi mạng lâu tới nhà cung cấp. Outbox bảo đảm instruction và bản tin cần gửi được lưu cùng transaction cục bộ; worker có thể gửi lại nên cần giao thức idempotency ở biên ngoài và đối soát kết quả.

### 7.3. Hai lớp chống trùng

Khóa idempotency của request cần nằm trong phạm vi tenant/loại thao tác và gắn với settlement ID/phiên bản cùng command có ý nghĩa. Cùng key nhưng đổi batch, bên nhận hoặc chỉ dẫn tiền phải bị từ chối.

Ngoài ra cần ràng buộc nghiệp vụ bảo đảm cùng một settlement version không tạo hai instruction chỉ vì caller đổi key. Các sự kiện nguồn và khoản kết chuyển cũng phải được bảo vệ khỏi áp dụng hai lần.

Nếu commit đã thành công nhưng response bị mất, retry trả lại instruction/kết quả cũ sau kiểm tra quyền. Không tính lại phần lẻ bằng policy mới, không lấy nguồn đã claim để tạo một batch độc lập khác.

## 8. Quyền, phê duyệt và thay đổi cấu hình

Quyền `SETTLEMENT_EXECUTE` chưa đủ. Server phải xác định người gọi được thao tác với tenant, pháp nhân, merchant, bên nhận và route nào. Một settlement cân số học nhưng trả cho tài khoản ngân hàng khác vẫn là một thao tác sai.

Những trường quan trọng cần được ràng buộc với phê duyệt gồm:

- Tập nghĩa vụ nguồn và mốc cắt.
- Bên nhận, tài khoản nhận và settlement currency.
- Policy version, quantum, rounding mode và thứ tự tính.
- Phí, FX, reserve, điều chỉnh và dữ liệu kết chuyển.
- Số tiền cuối và cách phân bổ có ảnh hưởng tới quyền lợi.

Sửa các trường này sau phê duyệt cần tạo phiên bản mới hoặc làm mất hiệu lực phê duyệt theo chính sách. Không chỉ gắn phê duyệt với một `batchId` rồi cho phép thay nội dung bên trong.

Rounding mode, quantum và tài khoản điều chỉnh không phải tham số tùy ý của endpoint payout. Chúng là cấu hình có ảnh hưởng tiền, cần quyền sửa theo phạm vi và quy trình phát hành. Nếu yêu cầu kiểm soát tách người tạo/người duyệt, phải thực thi ở server cho đúng phiên bản cấu hình hoặc settlement.

Khi chính sách đang thay đổi đồng thời với chốt lệnh, cần một ranh giới hiệu lực rõ. Có thể khóa hoặc kiểm tra phiên bản bằng giao thức nguyên tử tương ứng; đọc cấu hình từ cache rồi ghi `policyVersion` vào DB không tự loại bỏ khoảng đua. Snapshot đã duyệt chỉ được tiếp tục nếu chính sách chuyển tiếp cho phép.

## 9. Phần chênh, nghĩa vụ kết chuyển và ledger

### 9.1. Chênh lệch tính toán không luôn là một dòng tiền ghi sổ

Ở ví dụ đầu, `R=-0.005 USD`. Nếu book chỉ cho ghi số nguyên cent, không được tạo một entry có giá trị nửa cent chỉ vì bảng tính có thể giữ số đó.

Cần phân biệt:

| Loại dữ liệu | Cách quản lý |
| --- | --- |
| Chênh lệch dưới đơn vị ghi sổ | Giữ trong dữ liệu tính toán hoặc bộ tích lũy phần lẻ được kiểm soát theo chính sách |
| Chênh lệch biểu diễn được trong book | Có thể được phân bổ/ghi điều chỉnh theo chính sách hạch toán đã duyệt |
| Nghĩa vụ chưa chuyển do quantum/hạn mức tuyến | Vẫn theo dõi là phần còn phải xử lý nếu hợp đồng không tất toán nó |
| Phí, reserve hoặc thiếu tiền chưa rõ nguồn | Phân loại theo bản chất; không đổi tên thành rounding để bỏ qua |

Nếu dùng bộ tích lũy phần lẻ, phải có currency, độ chính xác, chủ thể hưởng/chịu, phiên bản, lịch sử chuyển vào/ra và quy tắc khi đạt một đơn vị có thể ghi sổ. Tổng phần lẻ không được reset hoặc chuyển cho chủ thể khác khi thay batch.

### 9.2. Kết chuyển không phải thu nhập tự động

Giả sử nghĩa vụ đã ghi nhận là 1,02 đơn vị tiền, tuyến chỉ chuyển theo bội 0,05 và hợp đồng giả định yêu cầu chuyển xuống 1,00, giữ 0,02 cho kỳ sau:

```text
+ Nghĩa vụ có trước:       1.02
+ Đã chuyển:              1.00
+ Còn phải trả/kết chuyển: 0.02
+
+ 1.02 = 1.00 + 0.02
```

Ví dụ này dùng chính sách chuyển xuống riêng, không phải mode gần nhất trong hàm Java. Phần 0,02 vẫn là nghĩa vụ nếu hợp đồng quy định như vậy; không đồng thời đưa nó vào doanh thu rounding.

Nếu hợp đồng cho tất toán nghĩa vụ theo kết quả làm tròn và có điều chỉnh tương ứng, đó là một mô hình khác. Phải chốt bên chịu/chủ thể hưởng chênh lệch và cách hạch toán. Không vừa kết chuyển một phần dư vừa ghi nhận cùng phần đó như khoản đã được tất toán có lợi cho nền tảng.

Khi lệnh gửi thất bại chắc chắn hoặc bị hủy, cần quy tắc giải phóng/đảo phần nghĩa vụ đã giữ và kết chuyển liên quan. Khi kết quả còn `UNKNOWN`, không giải phóng rồi cho payout mới chi lại cùng nghĩa vụ.

### 9.3. Điều chỉnh phải có nguồn và giới hạn

Một trường `roundingAdjustment` do client gửi không đủ làm chứng từ hợp lệ. Server phải tính lại từ snapshot và policy, kiểm tra đúng dấu, currency, quantum và phạm vi.

Nếu cần dòng ledger điều chỉnh, tài khoản đối ứng do server xác định theo chính sách book. Giữ liên kết tới settlement, nguồn tính, phiên bản và người phê duyệt. Journal vẫn phải cân trong từng book/currency và được ghi nguyên tử với thay đổi liên quan.

Không sửa journal hoặc payout đã chốt để ép khớp báo cáo mới. Sai sót sau ghi sổ cần nghiệp vụ điều chỉnh có liên kết và quyền tương ứng. Tài khoản rounding không phải nơi hấp thụ mọi sai lệch đối soát.

## 10. Đối soát với nhà cung cấp và kết quả thực tế

### 10.1. Hợp đồng adapter phải nói rõ đơn vị

Một tuyến có thể nhận số nguyên đơn vị nhỏ nhất; tuyến khác có thể nhận chuỗi thập phân theo một hợp đồng riêng. Adapter cần biết rõ currency, scale và quantum tương ứng, rồi kiểm tra khoản gửi biểu diễn đúng số tiền đã duyệt.

Không làm tròn lần nữa ở adapter chỉ vì kiểu dữ liệu đích ít chữ số hơn. Nếu số tiền đã chốt không biểu diễn được, phải dừng hoặc đi qua quy trình tính lại hợp lệ trước khi gửi. Không đổi currency để vượt lỗi đơn vị.

Nếu nhà cung cấp yêu cầu quy tắc khác, cấu hình quyết toán phải phản ánh điều đó trước khi batch được chốt. Cùng tên “settlement” giữa hai hệ thống không bảo đảm chúng đang dùng cùng phạm vi phí, thời điểm hoặc số tiền gộp.

### 10.2. So sánh đúng vai trò tiền

| Khoản tiền | Điều cần kiểm tra |
| --- | --- |
| Nghĩa vụ đã duyệt | Nguồn, policy, bên nhận và số tiền cuối có thẩm quyền |
| Số tiền instruction | Khớp định nghĩa khoản được gửi theo hợp đồng adapter |
| Số tiền bị ghi nợ | Có thể có phí riêng; cần phân loại và đối chiếu đúng khoản |
| Số tiền bên nhận được ghi có | Có thể khác khoản gửi do phí/FX theo hợp đồng, cần bằng chứng tương ứng |
| Chênh lệch chưa phân loại | Giữ là ngoại lệ để điều tra, không tự nhận là rounding |

Không so tiền gộp với tiền ròng hoặc tiền khác currency rồi bỏ qua chênh lệch bằng một tolerance. Các phí/FX thực tế cần được đối chiếu với dữ liệu có thẩm quyền của đúng giao dịch.

Khi nhận callback, xác thực thông điệp rồi so khớp transaction ID, merchant, bên nhận theo khả năng của giao thức, currency, vai trò amount và trạng thái thực sự mà nhà cung cấp công bố. Caller ở frontend không có quyền tự khai payout đã thành công.

Nếu timeout sau khi gửi, dùng danh tính instruction ban đầu để tra cứu hoặc retry theo hợp đồng idempotency. Không tạo instruction mới, đổi quantum hoặc chuyển tuyến ngay khi chưa biết lệnh cũ có được thực hiện không.

### 10.3. Tolerance phải có nguồn giải thích

Một rounding delta hợp lệ phải được suy ra từ cùng tập nguồn và cùng công thức. Nếu instruction đã chốt là 97,66 USD nhưng callback khai một số khác, việc sai lệch nằm dưới một cent không tự chứng minh là hợp lệ.

Nếu quy trình đối soát thật sự cho một ngưỡng ngoại lệ, cần nêu rõ currency, phạm vi, nguyên nhân, hành động tiếp theo và bên phê duyệt. Ngưỡng để phân loại/cảnh báo không mặc nhiên cho phép đổi nghĩa vụ, tự tất toán hoặc trả thêm tiền.

Mọi điều chỉnh cần truy được từ `N`, policy, `P`, `R` và dữ liệu bên ngoài. Một khoản thiếu phí, một khoản chi trùng và một sai scale đều có thể làm lệch số tiền; chỉ nhìn độ nhỏ của chênh lệch không phân biệt được chúng.

## 11. Các cách lạm dụng và dấu vết cần quan sát

| Cách lạm dụng | Invariant bị đe dọa | Hàng rào cần có |
| --- | --- | --- |
| Chia một nghĩa vụ thành nhiều request sát ngưỡng làm tròn | Tổng chi phụ thuộc đóng gói request | Phạm vi nghĩa vụ và kết chuyển do server kiểm soát |
| Đổi rounding mode hoặc quantum trong payload | Caller tự chọn số tiền có lợi | Policy tin cậy theo phạm vi, không mass assignment |
| Sắp lại dòng phân bổ | Caller chiếm phần dư | Phá hòa ổn định bằng định danh được kiểm soát |
| Tạo dòng giả hoặc nhân đôi trọng số | Nhận thêm quyền hưởng | Nguồn phân bổ có thẩm quyền và chống trùng |
| Đổi key để gửi lại cùng settlement | Chi hai lần | Unique instruction theo nghiệp vụ, idempotency request |
| Chạy hai worker chốt cùng batch | Áp nguồn/kết chuyển hai lần | Claim nguyên tử, khóa/phiên bản và unique phù hợp |
| Sửa số tiền hoặc bên nhận sau duyệt | Phê duyệt không còn đúng nội dung | Phiên bản/hash nội dung và kiểm tra trạng thái |
| Gộp phạm vi khác currency/tenant | Bù trừ hoặc chuyển phần dư sai chủ thể | Quyền đối tượng và ranh giới quyết toán |
| Dùng mọi chênh lệch nhỏ làm rounding | Che gian lận hoặc phí sai | Tính lại delta, phân loại nguyên nhân, audit điều chỉnh |
| Reset phần dư khi tạo batch mới | Làm mất nghĩa vụ của bên nhận | Sổ phần lẻ/kết chuyển theo chủ thể, cập nhật đúng một lần |
| Gọi lại sau timeout bằng instruction mới | Tiền có thể đã đi ở lần trước | Trạng thái UNKNOWN và đối soát instruction cũ |

Thông tin truy vết nên bao gồm:

- Định danh phạm vi quyết toán, tập nguồn/mốc cắt và settlement version.
- Snapshot phí, tỷ giá, reserve, điều chỉnh và kết chuyển có liên quan.
- Currency, đơn vị lưu trữ, quantum, mode, thứ tự tính và policy version.
- Giá trị trước làm tròn, giá trị cuối, delta và phân bổ từng dòng.
- Người tạo, người duyệt, người chốt lệnh, thời điểm và lý do ngoại lệ.
- Journal/instruction ID, danh tính idempotency và kết quả nhà cung cấp.

Không cần đưa khóa bí mật hoặc toàn bộ thông tin ngân hàng nhạy cảm vào log để tính được rounding delta. Dữ liệu nhạy cảm nên được giữ trong nơi có quyền phù hợp và tham chiếu bằng định danh khi có thể.

Có thể theo dõi dấu và độ lớn delta theo merchant, policy, quantum, số dòng, số batch và khoảng thời gian. Một bên luôn có delta thuận lợi hoặc đột ngột tăng số batch nhỏ sát ngưỡng cần được xem xét theo dữ liệu nguồn. Phân bố khác kỳ vọng là tín hiệu điều tra, không tự chứng minh gian lận: mode và loại giao dịch có thể tạo thiên lệch hợp lệ đã biết.

## 12. Kiểm thử các ranh giới và tình huống tấn công

### 12.1. Ma trận kiểm thử

| Tình huống | Kết quả cần chứng minh |
| --- | --- |
| Giá trị sát dưới, đúng giữa và sát trên một mốc quantum | Kết quả đúng policy đã chọn |
| Tie `2.345` và `2.355` với `HALF_EVEN`, scale 2 | Lần lượt 2.34 và 2.36; không dùng HALF_UP ngầm |
| Giá trị âm ở cùng ranh giới | Giữ đúng ngữ nghĩa mode; không nhầm DOWN với FLOOR |
| Quantum 0,05 với đầu vào 1,02 | Kết quả là bội 0,05, không chỉ có hai số lẻ |
| Làm tròn trực tiếp so với thêm bước trung gian | Luồng production chỉ dùng những bước thuộc chính sách |
| Thay đóng gói API nhưng giữ nguyên các nghĩa vụ nguồn | Không đổi tổng quyết toán do caller tự chia request ngoài phạm vi cho phép |
| Chia 100 đơn vị cho ba trọng số bằng nhau | Tổng phân bổ đúng 100, kết quả phá hòa có thể lặp lại |
| Sắp lại mảng dòng nhưng giữ ID/trọng số có thẩm quyền | Phân bổ không đổi vì thứ tự request |
| Dòng giả, ID nguồn trùng hoặc trọng số bị sửa | Bị từ chối, không tăng quyền hưởng |
| Số âm đưa vào thuật toán chỉ dành cho trọng số/tổng dương | Bị từ chối hoặc xử lý bằng mô hình riêng đã định nghĩa |
| Client gửi mode, quantum, delta hoặc tài khoản điều chỉnh | Không thay được quyết định server |
| Nguồn/merchant/bên nhận thuộc tenant khác | Không được xem hoặc chốt quyết toán sai phạm vi |
| Phí/FX hoặc tổng đổi sau phê duyệt | Snapshot mới cần được xử lý theo quy trình phê duyệt lại |
| Hai worker cùng claim một nghĩa vụ | Không đưa cùng phần nghĩa vụ vào hai lệnh chi |
| Hai lần chốt đồng thời, cùng hoặc khác idempotency key | Tối đa một instruction cho settlement version đó |
| Crash giữa ghi ledger, cập nhật carry và ghi outbox | Toàn bộ thay đổi cục bộ cùng commit hoặc cùng rollback |
| Preview hoặc tính lại nhiều lần | Không cộng kết chuyển hoặc tiêu thụ nghĩa vụ nhiều lần |
| Retry sau commit khi response bị mất | Trả kết quả cũ; không tính lại policy mới hoặc chi thêm |
| Timeout nhà cung cấp chưa rõ kết quả | Không giải phóng nguồn rồi phát sinh lệnh chi mới tùy ý |
| Kết quả làm tròn bằng 0 | Không gửi lệnh 0 ngoài hợp đồng; nghĩa vụ/phần dư được xử lý đúng policy |
| Phần dư dưới đơn vị ghi sổ | Không tạo entry sai đơn vị hoặc làm mất dữ liệu cần kết chuyển |
| Chuyển từ kỳ này sang kỳ khác | Phần dư đi đúng chủ thể/currency và áp dụng đúng một lần |
| Ghi tie vào cột numeric scale thấp hơn | Không để DB làm đổi mode so với kết quả đã chốt |
| Giá trị vượt miền lưu trữ hoặc chuỗi số quá lớn | Từ chối có kiểm soát trước khi tạo hiệu ứng tiền |
| Nhà cung cấp báo amount khác nhưng nằm trong tolerance cũ | Không tự coi là rounding; cần nguồn giải thích hợp lệ |
| Nâng policy khi batch đang APPROVED | Kết quả theo đúng quy tắc hiệu lực/chuyển tiếp, không trộn hai phiên bản |

Kiểm thử transaction và cạnh tranh cần chạy với cơ chế DB tương ứng, có điểm đồng bộ để tạo cuộc đua thực tế. Chỉ kiểm tra helper số học hoặc gửi request nối tiếp không chứng minh được chống claim trùng hay mất cập nhật kết chuyển.

Ở biên nhà cung cấp, nên quan sát cả số lần gọi, danh tính instruction, currency và amount thực sự được gửi. Một test chỉ assert HTTP 200 không phát hiện payout hai lần hoặc adapter tự làm tròn lần nữa.

### 12.2. Các tính chất toán học và nghiệp vụ

Với policy gần nhất trong ví dụ Java và các đầu vào nằm trong miền hỗ trợ, có thể kiểm tra:

```text
+ payable là bội của quantum.
+ payable = rawNet + roundingAdjustment.
+ abs(roundingAdjustment) <= quantum / 2.
+ Q(Q(x)) = Q(x), với cùng policy.
+ Q(-x) = -Q(x), với HALF_UP/HALF_EVEN đối xứng trong ví dụ.
+ SUM(allocation) = tổng đã chốt trên cùng đơn vị phân bổ.
+ Hoán vị request không đổi phân bổ khi khóa phá hòa giữ nguyên.
```

Các tính chất này không chứng minh toàn bộ nghiệp vụ đúng. Chẳng hạn, `Q(Q(x))=Q(x)` không hợp thức hóa việc làm tròn từng bước về các quantum khác nhau; một tổng phân bổ bảo toàn vẫn có thể thuộc sai merchant.

Các bất biến nghiệp vụ cần kiểm tra riêng:

```text
+ Một phần nghĩa vụ nguồn không bị quyết toán hai lần.
+ Phê duyệt áp dụng đúng nội dung và bên nhận đã chốt.
+ Tổng tiền đã chi, nghĩa vụ còn lại và điều chỉnh hợp lệ bảo toàn giá trị.
+ Chỉ các phần chênh do chính sách xác định mới được phân loại là rounding.
+ Replay không tăng payout, ledger effect hoặc carry.
```

Với dữ liệu sinh ngẫu nhiên, chú trọng giá trị sát tie, nhiều dòng nhỏ, thứ tự nguồn khác nhau, số âm và ngưỡng miền số. Kết quả kỳ vọng nên đến từ đặc tả độc lập hoặc trường hợp chuẩn được tính rõ, tránh dùng lại chính helper production làm bộ tính đáp án.

## 13. Những dấu hiệu thiết kế cần xem lại

| Dấu hiệu | Rủi ro | Hướng xử lý |
| --- | --- | --- |
| Mỗi service tự `setScale(2)` | Khác thời điểm, mode và currency | Ranh giới tính và policy có phiên bản |
| `scale=2` được xem là đủ cho quantum 0,05 | Gửi số không chia hết bước chuyển | Làm tròn theo số quantum nguyên |
| Dùng `double` cho phí, tỷ giá hoặc net cần chính xác | Mất thông tin ở sát ngưỡng | Số thập phân/hữu tỷ theo hợp đồng độ chính xác |
| Cứ lệch nhỏ là ghi vào tài khoản rounding | Che lỗi nguồn hoặc chi trùng | Tính delta từ snapshot, phân loại và phê duyệt |
| Gán toàn bộ phần dư cho dòng cuối do client gửi | Caller đổi thứ tự để hưởng chênh | Phân bổ quyết định theo dữ liệu được kiểm soát |
| Gửi lại batch bằng key mới để khắc phục timeout | Có thể trả hai lần | Chống trùng theo settlement/instruction và đối soát |
| Phần dư chỉ nằm trong biến tạm của worker | Mất nghĩa vụ khi crash/chuyển kỳ | Dữ liệu kết chuyển có transaction và lịch sử |
| Payout dùng nội dung khác nội dung được duyệt | Vượt kiểm soát hạn mức và quyền | Snapshot bất biến, khóa/phiên bản tại lúc chốt |
| DB hoặc adapter tự làm tròn thêm | Kết quả không còn đúng policy | Kiểm tra biểu diễn cuối ở từng biên tích hợp |

Một luồng settlement rounding đạt yêu cầu khi giải thích được **nguồn nào tạo nghĩa vụ, phạm vi nào được làm tròn, công thức nào tạo số tiền cuối, phần chênh thuộc ai và vì sao retry không làm phát sinh thêm tiền**. Câu trả lời phải tồn tại trong chính sách, dữ liệu đã chốt và các hàng rào thực thi tại thời điểm giao dịch.

