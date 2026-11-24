# Discount rounding: làm tròn giảm giá nhất quán và chống lạm dụng

## 1. Làm tròn giảm giá là một quy tắc nghiệp vụ

Giả sử một giỏ có ba dòng hàng, mỗi dòng 3,35 đơn vị tiền, được giảm 10%. Nếu làm tròn giảm giá từng dòng đến hai chữ số thập phân, mỗi dòng giảm 0,34 và tổng giảm là 1,02. Nếu tính trên tổng giỏ 10,05 rồi làm tròn, tổng giảm là 1,01.

Hai cách đều có thể thực hiện bằng số thập phân chính xác, nhưng cho kết quả khác nhau vì phạm vi làm tròn khác nhau. Nếu backend, màn hình thanh toán và chức năng hoàn tiền chọn các cách khác nhau, hệ thống không còn một số tiền thống nhất để kiểm tra và ghi nhận.

Kẻ tấn công có thể lợi dụng điều này bằng cách tách dòng, tách đơn, thay số lượng hoặc hoàn từng phần nhiều lần. Sai lệch một đơn vị nhỏ nhất có thể trở thành lợi ích có hệ thống khi thao tác được lặp lại.

*Discount rounding* là quy tắc lượng tử hóa khoản giảm giá về đơn vị tiền được hỗ trợ, tại một bước và phạm vi nghiệp vụ xác định. Để bảo vệ logic nghiệp vụ, cần kiểm soát đồng thời số tiền đủ điều kiện, tỷ lệ, trần giảm, thứ tự áp dụng, phân bổ phần dư và cách hoàn lại.

Mục tiêu của bài là thiết kế một luồng trong đó số giảm đã tính, số giảm được duyệt, số tiền phải trả và số được hoàn có thể đối chiếu với nhau. Việc làm tròn không thay thế kiểm tra quyền sử dụng mã, giới hạn lượt dùng, transaction hay idempotency.

## 2. Viết rõ chính sách trước khi viết hàm làm tròn

Một cấu hình chỉ có `discount_percent = 10` chưa đủ. Chính sách cần trả lời các câu hỏi sau:

| Thành phần | Cần xác định |
|---|---|
| Cơ sở tính | Giá gốc, giá sau giảm trước đó, tổng hàng đủ điều kiện hay tổng cả đơn? |
| Phạm vi | Từng sản phẩm, từng dòng, từng đơn hay tổng theo kỳ? |
| Đơn vị | Tiền tệ, đơn vị nhỏ nhất, bước tiền nếu có |
| Làm tròn | Chế độ, thời điểm và số lần làm tròn |
| Giới hạn | Giảm tối đa, giá trị đơn tối thiểu, ngân sách, lượt dùng |
| Cộng dồn | Mã nào được kết hợp, thứ tự áp dụng và cơ sở tính tiếp theo |
| Phân bổ | Khoản giảm tổng đơn được gán về các dòng thế nào? |
| Hoàn hàng | Hoàn theo phân bổ gốc hay có tính lại điều kiện, theo chính sách nào? |
| Phiên bản | Báo giá và đơn hàng gắn với bản chính sách nào? |

Ví dụ chính sách dùng xuyên suốt phần tính toán chính của bài:

- Một đơn chỉ có một tiền tệ, được cấu hình hai chữ số thập phân.
- Giá trị các dòng đủ điều kiện được biểu diễn bằng số nguyên đơn vị nhỏ nhất.
- Khoản giảm phần trăm tính trên tổng hàng đủ điều kiện sau các điều chỉnh trước đó đã được xác định.
- Phí vận chuyển và thuế không nằm trong cơ sở tính của ví dụ.
- Tổng giảm được làm tròn một lần bằng `HALF_UP` về số nguyên đơn vị nhỏ nhất.
- Áp dụng trần giảm theo đơn; số giảm không vượt cơ sở đủ điều kiện.
- Phân bổ khoản giảm cuối cùng về dòng bằng phần nguyên và phần dư lớn nhất.
- Hoàn hàng tham chiếu phân bổ đã lưu của đơn gốc.

Đây là lựa chọn minh họa, không phải chính sách bắt buộc cho mọi sản phẩm. Nếu có thuế, phí hoặc quy định của chương trình khác, phải xác định thứ tự và cơ sở tương ứng; không tự suy ra từ ví dụ này.

## 3. Các invariant cần giữ

Gọi:

- `b_i`: giá trị đủ điều kiện của dòng `i`, theo đơn vị nhỏ nhất.
- `B = Σ b_i`: tổng cơ sở tính giảm.
- `D`: tổng giảm cuối cùng.
- `d_i`: khoản giảm phân bổ cho dòng `i`.
- `p_i = b_i - d_i`: phần còn phải trả của cơ sở đó.

Các invariant tối thiểu là:

```text
0 <= D <= B

0 <= d_i <= b_i

Σ d_i = D

Σ p_i = B - D

Mọi b_i, D, d_i, p_i đều dùng cùng tiền tệ và đơn vị.
```

Nếu đơn có dòng không đủ điều kiện, phí hoặc thuế, tổng phải trả đầy đủ còn bao gồm các thành phần đó theo chính sách. Không nhầm `B - D` trong ví dụ với tổng cuối của mọi loại đơn hàng.

Các invariant bảo mật bổ sung:

- Cơ sở tính và chính sách đến từ dữ liệu backend có thẩm quyền.
- Người gọi được sử dụng mã giảm giá cho đơn và tài khoản đang thao tác.
- Đơn đã chốt không bị tính lại âm thầm bằng phiên bản chính sách khác.
- Một lượt áp dụng mã và hiệu lực tiền không được ghi lặp do retry.
- Tổng hoàn hoặc giữ hạn mức hoàn không vượt khoản được phép hoàn.
- Các thay đổi số lượng, loại hàng hoặc người mua làm mất điều kiện phải được xử lý theo state machine đã định.

Ràng buộc số học đúng không chứng minh quyền dùng mã đúng. Một mã dành riêng cho khách hàng khác vẫn có thể tạo ra phép tính hoàn toàn cân bằng.

## 4. Tính tổng giảm tại đúng phạm vi

### 4.1. Tỷ lệ dạng nguyên giúp tránh đầu vào mơ hồ

Trong ví dụ, tỷ lệ được lưu bằng basis point, viết tắt là bps:

```text
10000 bps = 100%
 1000 bps =  10%
  125 bps = 1.25%
```

Đây là độ phân giải tỷ lệ của sản phẩm minh họa. Nếu chương trình cần tỷ lệ nhỏ hơn 0,01%, phải chọn biểu diễn khác có hợp đồng rõ ràng; không tự làm tròn tỷ lệ khi nhập cấu hình.

Không lấy `rate`, `cap`, giá gốc hoặc cờ đủ điều kiện trực tiếp từ payload client để tính số giảm. Backend phải tải chính sách được phép áp dụng và xác định cơ sở từ dữ liệu đơn hàng đã xác minh.

### 4.2. Công thức của chính sách minh họa

Gọi `r` là số basis point và `C` là trần giảm theo đơn, đều đã được xác minh:

```text
raw_discount = B × r / 10000

rounded_discount = round_to_integer_minor_unit(raw_discount, HALF_UP)

D = min(B, C, rounded_discount)
```

Ở đây `C` là số nguyên theo cùng đơn vị với `B`. Nếu có trần ngân sách theo chiến dịch hoặc theo người dùng, đó còn là một giới hạn dùng chung cần kiểm soát đồng thời, không chỉ là một phép `min` trên dữ liệu vừa đọc.

Giá trị âm của cơ sở, tỷ lệ hoặc trần phải bị từ chối theo miền của thao tác. Không dùng `abs()` hay tự ép về 0 để che một cấu hình sai.

### 4.3. Ví dụ ba dòng hàng

Mỗi dòng có cơ sở 335 đơn vị nhỏ nhất, tổng là 1005. Giảm 1000 bps, tức 10%, và giả sử trần không làm giảm kết quả:

```text
B = 335 + 335 + 335 = 1005

raw_discount = 1005 × 1000 / 10000 = 100.5

D = HALF_UP(100.5) = 101

Tổng còn phải trả trên cơ sở này = 1005 - 101 = 904
```

Nếu tự làm tròn từng dòng, khoản giảm là `34 + 34 + 34 = 102`. Kết quả đó không tuân theo chính sách giảm trên tổng đơn đã chọn.

Muốn hiển thị giảm giá theo dòng, cần phân bổ `D = 101` về các dòng. Không tính thêm ba khoản giảm độc lập rồi hy vọng tổng sẽ khớp.

### 4.4. Không làm tròn cả giảm giá và số còn lại độc lập

Với cơ sở 1 đơn vị nhỏ nhất và tỷ lệ 50%:

```text
Giảm thô = 0.5 -> HALF_UP -> 1
Còn lại thô = 0.5 -> HALF_UP -> 1

Nếu giữ cả hai kết quả: giảm 1 + phải trả 1 = 2, khác cơ sở 1.
```

Theo chính sách làm tròn khoản giảm, phải tính `D = 1`, sau đó lấy phần còn lại bằng phép trừ chính xác `1 - 1 = 0`.

Một chính sách khác có thể chọn làm tròn số phải trả trước rồi suy ra giảm giá. Điều quan trọng là xác định một đại lượng làm tròn có thẩm quyền và tính đại lượng bù từ nó để giữ invariant.

## 5. Phân bổ phần dư mà không tạo thêm tiền giảm

### 5.1. Phân bổ theo tỷ trọng của cơ sở

Khi `B > 0`, hạn mức lý tưởng cho dòng `i` là:

```text
ideal_i = D × b_i / B

floor_i = phần nguyên không âm của ideal_i

remaining = D - Σ floor_i
```

Sau đó phân phối từng đơn vị còn lại cho những dòng có phần dư lớn nhất. Nếu phần dư bằng nhau, dùng một thứ tự khóa ổn định do backend xác định.

Không dùng thứ tự mảng do client gửi để quyết định dòng được hưởng thêm phần giảm. Các khóa cũng cần ổn định trong bản chụp đơn; sinh khóa ngẫu nhiên mỗi lần tính có thể làm kết quả phân bổ thay đổi giữa các lần xem lại.

### 5.2. Tiếp tục ví dụ tổng giảm 101

Ba dòng cùng có cơ sở 335, nên tỷ trọng bằng nhau:

| Dòng | Cơ sở | Hạn mức lý tưởng | Phần nguyên | Phân bổ cuối | Còn phải trả |
|---|---:|---:|---:|---:|---:|
| L1 | 335 | 33,666... | 33 | 34 | 301 |
| L2 | 335 | 33,666... | 33 | 34 | 301 |
| L3 | 335 | 33,666... | 33 | 33 | 302 |
| Tổng | 1005 | 101 | 99 | 101 | 904 |

Hai đơn vị dư được cấp cho L1 và L2 theo thứ tự khóa ổn định đã chọn. Dòng L3 không nhận đúng kết quả làm tròn riêng 10% của nó; điều này phù hợp vì chính sách giảm và làm tròn ở tổng đơn, rồi phân bổ.

Nếu trần giảm làm `D` nhỏ hơn số giảm phần trăm ban đầu, cần phân bổ `D` cuối cùng. Không phân bổ số chưa áp trần rồi chỉ sửa trường tổng trên đơn.

### 5.3. Tránh sai số khi so phần dư

Không tính `ideal_i` bằng `double` rồi sắp xếp phần lẻ gần bằng nhau. Với cơ sở và tổng giảm nguyên, có thể tính chính xác:

```text
numerator_i = D × b_i

floor_i     = numerator_i DIV B
remainder_i = numerator_i MOD B
```

Mọi dòng dùng cùng mẫu số `B`, nên chỉ cần so `remainder_i` để xếp phần dư. Phép nhân `D × b_i` có thể vượt miền `long` dù kết quả cuối hợp lệ; cần số nguyên lớn hoặc phép toán có kiểm tra phù hợp.

## 6. Ví dụ Java tính và phân bổ chính xác

Đoạn code dùng Java 17 trở lên. Nó giả định các dòng đã thuộc cùng tiền tệ, cơ sở đã được backend xác minh và `lineId` là khóa ổn định do backend quản lý. Giới hạn 1000 dòng và định dạng ID là lựa chọn của ví dụ.

`discountMinor` là kết quả từ chính sách có thẩm quyền, không phải tổng giảm do client yêu cầu. Đoạn code xử lý số học và phân bổ; kiểm tra quyền, lượt dùng mã và transaction được thực hiện ở luồng nghiệp vụ bên ngoài.

```java
import java.math.BigDecimal;
import java.math.BigInteger;
import java.math.RoundingMode;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.HashSet;
import java.util.List;
import java.util.Set;

public final class DiscountRounding {
    public record Line(String lineId, long eligibleMinor) {}
    public record Allocation(String lineId, long discountMinor) {}

    private record Share(
        String lineId,
        long baseMinor,
        long floorMinor,
        BigInteger remainder
    ) {}

    public static long percentageDiscount(
        long eligibleMinor,
        int basisPoints,
        long capMinor
    ) {
        if (eligibleMinor < 0 || capMinor < 0
                || basisPoints < 0 || basisPoints > 10000) {
            throw new IllegalArgumentException("Invalid discount inputs");
        }

        long rounded = BigDecimal.valueOf(eligibleMinor)
            .multiply(BigDecimal.valueOf(basisPoints))
            .divide(BigDecimal.valueOf(10000), 0, RoundingMode.HALF_UP)
            .longValueExact();

        return Math.min(eligibleMinor, Math.min(capMinor, rounded));
    }

    public static List<Allocation> allocate(
        long discountMinor,
        List<Line> lines
    ) {
        if (lines == null || lines.size() > 1000 || discountMinor < 0) {
            throw new IllegalArgumentException("Invalid allocation inputs");
        }

        long total = 0;
        Set<String> ids = new HashSet<>();
        for (Line line : lines) {
            if (line == null || line.lineId() == null
                    || !line.lineId().matches("[A-Za-z0-9_-]{1,64}")
                    || !ids.add(line.lineId()) || line.eligibleMinor() < 0) {
                throw new IllegalArgumentException("Invalid eligible line");
            }
            total = Math.addExact(total, line.eligibleMinor());
        }

        if (discountMinor > total) {
            throw new IllegalArgumentException("Discount exceeds eligible total");
        }
        if (total == 0) {
            return lines.stream()
                .map(line -> new Allocation(line.lineId(), 0))
                .sorted(Comparator.comparing(Allocation::lineId))
                .toList();
        }

        BigInteger denominator = BigInteger.valueOf(total);
        BigInteger discount = BigInteger.valueOf(discountMinor);
        List<Share> shares = new ArrayList<>();
        long assigned = 0;

        for (Line line : lines) {
            BigInteger[] qr = discount
                .multiply(BigInteger.valueOf(line.eligibleMinor()))
                .divideAndRemainder(denominator);
            long floor = qr[0].longValueExact();
            assigned = Math.addExact(assigned, floor);
            shares.add(new Share(
                line.lineId(), line.eligibleMinor(), floor, qr[1]
            ));
        }

        long remaining = Math.subtractExact(discountMinor, assigned);
        shares.sort(
            Comparator.comparing(Share::remainder).reversed()
                .thenComparing(Share::lineId)
        );

        List<Allocation> result = new ArrayList<>();
        for (int i = 0; i < shares.size(); i++) {
            Share share = shares.get(i);
            long allocated = Math.addExact(
                share.floorMinor(), i < remaining ? 1L : 0L
            );
            if (allocated > share.baseMinor()) {
                throw new IllegalStateException("Allocation exceeds line base");
            }
            result.add(new Allocation(share.lineId(), allocated));
        }

        return result.stream()
            .sorted(Comparator.comparing(Allocation::lineId))
            .toList();
    }
}
```

Những điểm cần giữ khi tích hợp:

- Phép tính tỷ lệ dùng decimal chính xác, chỉ làm tròn về số nguyên ở bước cuối đã chọn.
- Phép cộng cơ sở dùng `Math.addExact`; lỗi tràn phải được xử lý, không tiếp tục với tổng sai.
- Phép nhân để phân bổ dùng `BigInteger`, tránh tràn ở tích trung gian.
- Dòng có khóa trùng bị từ chối; không cho hai dòng che lấp nhau khi lưu kết quả theo khóa.
- Thứ tự phân bổ dựa trên phần dư rồi `lineId`, không dựa trên thứ tự đầu vào.
- Cơ sở tổng bằng 0 chỉ cho tổng giảm bằng 0, không thực hiện phép chia.

Với `0 <= D <= B` và các cơ sở không âm, số đơn vị dư nhỏ hơn số dòng; phương pháp cấp thêm tối đa một đơn vị cho các phần dư lớn nhất giữ được tổng và không làm giảm vượt cơ sở dòng. Các giả định này phải tiếp tục đúng khi thay đổi thuật toán.

## 7. Những kiểu lạm dụng làm tròn cần dự liệu

### 7.1. Tách dòng để tăng tổng giảm

Giả sử có 10 đơn vị hàng, mỗi đơn vị giá 5 đơn vị nhỏ nhất, giảm 10%:

```text
Tính trên tổng:
  B = 10 × 5 = 50
  D = HALF_UP(50 × 10%) = 5

Tính riêng mỗi đơn vị:
  D_i = HALF_UP(5 × 10%) = 1
  Tổng giảm = 10 × 1 = 10
```

Nếu một API tính theo số dòng client gửi, kẻ tấn công có thể biến một dòng số lượng 10 thành 10 dòng số lượng 1 để tăng khoản giảm gấp đôi trong ví dụ.

Nếu chính sách ở tổng đơn, tổng cơ sở của các hàng tương đương phải được tính từ dữ liệu chuẩn; cách biểu diễn dòng không được thay đổi tổng giảm. Có thể cần hợp nhất hoặc nhận diện các dòng tương đương theo quy tắc backend.

Tính trên tổng đơn không tự ngăn việc tách thành nhiều đơn khác nhau. Nếu chương trình giới hạn theo người dùng, kỳ hoặc nhóm giao dịch, phải có quy tắc tổng hợp và lượt dùng tương ứng.

### 7.2. Tách đơn để dùng lại trần hoặc ngân sách

Trần “giảm tối đa 100” có thể là theo đơn, theo mã, theo khách hàng hoặc toàn chiến dịch. Ghi nhãn không rõ khiến client dùng lại trần ở mỗi request.

Nếu trần theo người dùng trong ngày, việc tính `min(raw, 100)` độc lập cho mọi đơn không bảo vệ được giới hạn đó. Cần theo dõi phần đã dùng và phần đang giữ theo đúng phạm vi, cập nhật an toàn khi có nhiều request đồng thời.

Audit số giảm không thay thế constraint hoặc thao tác cập nhật có điều kiện để chặn vượt ngân sách ngay khi ghi.

### 7.3. Khoản giảm làm tròn về 0 vẫn gây tác dụng phụ

Một mã phần trăm có thể cho kết quả cuối bằng 0 trên đơn rất nhỏ. Cần xác định mã có được xem là đã sử dụng, có tiêu hao lượt, có mở quyền miễn phí khác hoặc có tính vào điều kiện chiến dịch hay không.

Không suy ra “được miễn phí vận chuyển” chỉ từ cờ `coupon_applied = true` nếu quyền đó yêu cầu mức giảm hoặc điều kiện riêng. Các hiệu lực phụ phải dựa trên quy tắc rõ ràng, không dựa vào một cờ giao diện.

### 7.4. Giảm 100% không bỏ qua kiểm tra bảo mật

Đơn có số phải trả bằng 0 có thể hợp lệ sau giảm giá. Nó vẫn cần kiểm tra quyền dùng mã, tồn kho, giới hạn lượt, trạng thái và idempotency khi xác nhận.

Không gọi cổng thanh toán với số tiền 0 nếu hợp đồng không hỗ trợ. Cần luồng hoàn tất đơn miễn thanh toán được kiểm soát; không để việc bỏ bước thanh toán đồng thời bỏ luôn xác thực hoặc phê duyệt cần thiết.

## 8. Ngưỡng áp dụng và cộng dồn mã phải có thứ tự

### 8.1. Không tạo vòng lặp điều kiện tối thiểu

Giả sử mã yêu cầu cơ sở đủ điều kiện tối thiểu 1000 đơn vị nhỏ nhất. Một giỏ có cơ sở 1005 được giảm 101, còn phải trả 904.

Nếu chính sách xét ngưỡng trước giảm, đơn vẫn đủ điều kiện. Không dùng số còn phải trả 904 để hủy mã, rồi vì hủy mã mà cơ sở lại lên 1005 và áp mã trở lại.

Cần ghi rõ ngưỡng xét trên thành phần nào và tại bước nào. Phí vận chuyển, hàng không đủ điều kiện hoặc thuế không được tự cộng vào ngưỡng nếu chương trình loại trừ chúng.

### 8.2. Hai mã 10% không mặc định thành 20%

Nếu hai mã áp tuần tự lên phần còn lại:

```text
Cơ sở đầu:          1000
Mã 1 giảm 10%:       100 -> còn 900
Mã 2 giảm 10%:        90 -> còn 810

Tổng giảm:           190
```

Gộp tỷ lệ thành 20% sẽ giảm 200, là chính sách khác. Khi có trần và làm tròn, thứ tự mã còn có thể ảnh hưởng kết quả nhiều hơn.

Luồng tính cần xác định:

1. Mã nào được phép cộng dồn.
2. Thứ tự do backend quyết định.
3. Cơ sở của từng mã sau các bước trước.
4. Trần riêng từng mã và trần chung nếu có.
5. Cách lưu phân bổ của từng khoản giảm về các dòng.

Không cho client đổi thứ tự mã để tự chọn kết quả có lợi nếu chương trình đã quy định thứ tự. Nếu sản phẩm cho chọn tổ hợp tốt nhất, đó phải là chức năng có quy tắc và giới hạn rõ ràng.

### 8.3. Chốt phiên bản chính sách

Báo giá cần gắn với nội dung giỏ, phiên bản giá, chính sách giảm và thời hạn theo thiết kế. Khi xác nhận đơn, backend phải kiểm tra báo giá còn hợp lệ hoặc tính lại và yêu cầu người dùng chấp nhận kết quả mới theo luồng sản phẩm.

Không duyệt một khoản giảm theo phiên bản cũ rồi thực thi bằng cách làm tròn, trần hoặc cơ sở khác. Với đơn đã chốt, giữ snapshot đủ để giải thích số tiền đã thu.

## 9. Hoàn hàng phải tôn trọng phần giảm đã ghi nhận

### 9.1. Vì sao tính lại từ phần trăm có thể hoàn vượt?

Ở ví dụ ba dòng, tổng thực trả trên cơ sở là 904, được phân bổ thành `301, 301, 302`.

Nếu khi hoàn từng dòng, hệ thống tự tính lại `335 × 90% = 301,5` và làm tròn thành 302, ba lần hoàn sẽ trả `302 × 3 = 906`. Khách hàng nhận nhiều hơn 2 đơn vị so với khoản thực trả trong ví dụ.

Nếu chính sách hoàn theo khoản đã trả, cần dùng số phải trả sau phân bổ đã lưu của từng dòng. Không suy ngược từ tỷ lệ giảm rồi làm tròn lại độc lập.

### 9.2. Hoàn một phần số lượng cần phân bổ ở cấp phù hợp

Một dòng có nhiều đơn vị hàng có thể cần hoàn một phần. Không được lấy giá trị dòng sau giảm chia số lượng rồi làm tròn lên ở mỗi lần hoàn mà không theo dõi phần còn lại.

Có thể lưu phân bổ đến từng đơn vị logic hoặc dùng cơ chế tính hoàn có trạng thái và phân bổ phần dư xác định được. Cần giữ:

```text
Tổng hoàn thành công
+ số tiền đang giữ hạn mức cho yêu cầu còn có thể thành công
<= số tiền được phép hoàn của phần hàng đó
```

Với hàng hoặc dịch vụ không có đơn vị vật lý rõ ràng, chọn phạm vi phân bổ phù hợp. Các khoản phí, thuế và điều chỉnh khác phải có quy tắc hoàn riêng; không mặc định chúng giống tiền hàng sau giảm.

### 9.3. Trường hợp mất điều kiện sau hoàn

Một chương trình có thể quy định thu hồi một phần ưu đãi khi hoàn hàng làm đơn không còn đủ ngưỡng. Nếu có quy tắc này, phải mô hình hóa rõ phép tính, giới hạn khoản thu hồi và cách trình bày cho người dùng.

Không lặng lẽ thay toàn bộ lịch sử đơn bằng cách chạy lại chính sách hiện tại. Giữ bản gốc và ghi khoản điều chỉnh có liên kết, phiên bản và lý do. Nếu chính sách không thu hồi ưu đãi, không tự áp thêm việc tính lại đó.

### 9.4. Retry và đồng thời

Hai yêu cầu hoàn có thể cùng nhìn thấy một phần tiền chưa hoàn. Kiểm tra tổng bằng truy vấn đọc rồi ghi ở transaction khác sẽ không đủ.

Cần phối hợp kiểm tra và giữ hạn mức trong transaction hoặc phép cập nhật có điều kiện, cùng khóa duy nhất cho hiệu lực hoàn. Idempotency key giúp nhận ra retry của cùng hành động; giới hạn hoàn vẫn phải chặn các yêu cầu khác key cố nhận cùng một phần tiền.

Yêu cầu hoàn bị timeout ở nhà cung cấp có thể vẫn thành công. Không giải phóng hạn mức chỉ vì chưa nhận phản hồi; cần trạng thái chưa rõ và quy trình xác minh kết quả.

## 10. Đưa phép tính vào luồng backend đáng tin cậy

### 10.1. Client gửi lựa chọn, backend quyết định số tiền

Payload có thể chứa mã ưu đãi và số lượng mong muốn. Các trường như `discount_total`, `line_discount`, `final_price`, `rate` hoặc `rounding_mode` không được dùng làm nguồn có thẩm quyền chỉ vì đã qua kiểm tra kiểu dữ liệu.

Backend cần xác minh:

- Đơn và các dòng thuộc quyền của actor trong tenant hiện tại.
- Giá, loại sản phẩm, số lượng và điều kiện hàng được giảm.
- Mã còn hiệu lực, đúng đối tượng và không vượt lượt hoặc ngân sách.
- Nội dung tính khớp bước phê duyệt hoặc báo giá đã chấp nhận.

UUID khó đoán không thay thế kiểm tra quyền đối với coupon, đơn và tài khoản.

### 10.2. Transaction bảo vệ trạng thái và quota

Một luồng xác nhận đơn có thể tổ chức như sau; đây là mô hình điều khiển, không phải SQL chạy trực tiếp:

```text
BEGIN
  Nhận diện yêu cầu theo khóa idempotency và nội dung nghiệp vụ.
  Khóa hoặc kiểm soát phiên bản giỏ và các tài nguyên cần thiết.
  Xác minh quyền, trạng thái và điều kiện mã từ dữ liệu backend.
  Tính cơ sở, tổng giảm, trần và phân bổ theo chính sách đã chọn.
  Giữ hoặc tiêu hao quota trong cùng cơ chế nhất quán.
  Lưu đơn cùng snapshot tiền và phân bổ cuối.
  Ghi audit, bản ghi sử dụng mã và outbox nếu cần.
COMMIT
```

Tài nguyên dùng chung như lượt theo khách hàng và ngân sách chiến dịch phải được cập nhật an toàn khi có cạnh tranh. Cần thứ tự khóa ổn định hoặc cơ chế cập nhật có điều kiện; một phép tính làm tròn đúng không tự ngăn hai đơn cùng tiêu khoản ngân sách còn lại.

Nếu thanh toán nằm ở dịch vụ ngoài, transaction nội bộ không bao trùm cuộc gọi đó. Cần định nghĩa giữ chỗ, xác nhận, hủy và giải phóng ưu đãi khi biết kết quả, tránh hai lần áp mã do retry hoặc giải phóng quá sớm.

### 10.3. Dữ liệu cần lưu để không tính lại sai

Một snapshot có thể bao gồm:

| Cấp dữ liệu | Trường quan trọng |
|---|---|
| Đơn hoặc lần tính | Tiền tệ, đơn vị, tổng cơ sở đủ điều kiện, tổng giảm, số phải trả liên quan |
| Chính sách | Mã/chiến dịch, phiên bản, tỷ lệ, trần, ngưỡng và thứ tự |
| Làm tròn | Phạm vi, chế độ, bước tiền và phiên bản thuật toán phân bổ |
| Dòng | Khóa ổn định, cơ sở, khoản giảm phân bổ, phần phải trả và số lượng |
| Quyền và hiệu lực | Người yêu cầu, phê duyệt nếu có, lượt dùng, movement và idempotency liên quan |

Không chỉ lưu chuỗi “giảm 10%” hoặc một tham chiếu đến chính sách có thể bị sửa. Cần đủ bằng chứng để tái dựng kết quả tại thời điểm chốt đơn.

## 11. Cơ sở dữ liệu và audit hỗ trợ invariant

### 11.1. Ràng buộc cục bộ và ràng buộc tổng

Với số nguyên đơn vị nhỏ nhất, có thể bảo vệ các điều kiện cục bộ như:

```text
eligible_minor >= 0
discount_minor >= 0
discount_minor <= eligible_minor
payable_minor = eligible_minor - discount_minor
```

Các điều kiện tổng như `Σ line_discount = order_discount` không được bảo vệ chỉ bằng `CHECK` thông thường trên một dòng riêng lẻ. Cần luồng ghi được giới hạn, kiểm tra trong transaction hoặc cơ chế database phù hợp với mô hình dữ liệu.

Constraint duy nhất cho lượt áp dụng hoặc hiệu lực tiền phải có đúng phạm vi tenant, chương trình và đối tượng nghiệp vụ. Không chỉ kiểm tra “chưa có” trong Java trước một lệnh `INSERT` không có chống trùng tại nơi lưu.

Kiểu decimal có scale cố định có thể làm tròn đầu vào trước khi lưu tùy hệ quản trị. Không để database tự sửa giá trị không hợp lệ rồi dùng dữ liệu đã sửa làm bằng chứng rằng request ban đầu hợp lệ.

### 11.2. Audit giải thích được chênh lệch

Audit nên cho biết cơ sở nào được giảm, số thô hoặc bằng chứng phép tính, tổng cuối, trần, cách phân bổ và phiên bản chính sách. Khi có chênh một đơn vị giữa hai dòng, có thể giải thích đó là phân bổ phần dư theo quy tắc, thay vì nghi ngờ mất tiền.

Ghi audit bắt buộc cùng transaction với việc chốt số tiền và sử dụng mã trong phạm vi database. Nếu phát thông điệp sau commit, dùng cơ chế như outbox cùng consumer chống trùng phù hợp.

Không đưa bí mật của mã nội bộ, token thanh toán hoặc dữ liệu cá nhân không cần thiết vào log. Mã có quyền lợi cao cần được bảo vệ về truy cập; biết mã không tự chứng minh quyền sử dụng.

### 11.3. Đối soát số tiền đã lưu

Các kiểm tra định kỳ có thể tìm:

- Tổng giảm theo dòng không khớp tổng giảm đơn.
- Khoản giảm vượt cơ sở hoặc trần đã lưu.
- Số phải trả không khớp các thành phần theo chính sách.
- Nhiều bản ghi tiêu lượt cho cùng một hiệu lực được phép duy nhất.
- Tổng hoàn vượt phần thực trả hoặc hạn mức chính sách.
- Đơn dùng phân bổ không tương ứng với phiên bản thuật toán được lưu.

Đối soát giúp phát hiện dữ liệu lịch sử và đường ghi bỏ sót, nhưng không thay thế kiểm soát ngăn vi phạm ở thời điểm xác nhận.

## 12. Kiểm thử các tình huống tấn công logic

### 12.1. Ma trận số học và chính sách

| Tình huống | Kết quả cần chứng minh |
|---|---|
| Ba dòng 335, giảm 10% theo tổng | Tổng giảm 101; phân bổ giữ đúng tổng |
| Khoản giảm thô ngay dưới, đúng và trên nửa đơn vị | Kết quả theo đúng chế độ, không theo mặc định thư viện |
| Một cơ sở rất nhỏ, giảm 50% hoặc 100% | Không làm tròn hai đại lượng bù độc lập; không tạo số âm |
| Tổng giảm vượt trần | Dùng tổng sau trần để phân bổ |
| Tỷ lệ âm hoặc trên miền cho phép | Từ chối cấu hình hoặc yêu cầu sai |
| Dòng không đủ điều kiện | Không được đưa vào cơ sở hoặc nhận phân bổ trái chính sách |
| Cơ sở bằng 0, danh sách rỗng hoặc dòng bằng 0 | Không chia cho 0 và không tạo giảm từ cơ sở rỗng |
| Tích trung gian rất lớn | Không tràn số hoặc mất chính xác |
| Đổi thứ tự dòng nhưng giữ khóa và nội dung | Cùng phân bổ theo khóa ổn định |
| Khóa dòng trùng | Bị từ chối thay vì ghi đè phân bổ |
| Cộng dồn hai mã | Đúng thứ tự, cơ sở và trần từng bước |
| Đơn sát ngưỡng tối thiểu | Xét đúng thành phần và thời điểm quy định |

### 12.2. Ma trận lạm dụng và đồng thời

| Cách thao tác | Invariant cần giữ |
|---|---|
| Tách một dòng số lượng lớn thành nhiều dòng nhỏ | Tổng giảm không đổi nếu các hàng tương đương theo chính sách tổng đơn |
| Tách thành nhiều đơn | Trần hoặc lượt dùng theo người/kỳ vẫn được kiểm soát nếu chính sách có giới hạn đó |
| Sửa tỷ lệ, trần hoặc `final_price` trong JSON | Backend không dùng dữ liệu client làm giá trị có thẩm quyền |
| Dùng mã của người khác hoặc tenant khác | Bị kiểm tra quyền và phạm vi |
| Đổi giỏ sau bước duyệt | Không thực thi bản tính không còn khớp nội dung đã duyệt |
| Retry sau commit nhưng trước phản hồi | Không tiêu lượt hoặc áp hiệu lực tiền lần hai |
| Hai đơn đồng thời dùng lượt cuối | Không cùng vượt giới hạn lượt |
| Hai yêu cầu hoàn cùng phần tiền | Không hoàn quá khoản được phép |
| Hoàn từng dòng nhiều lần | Tổng hoàn theo phân bổ gốc, không cộng thêm phần dư |
| Timeout khi thanh toán hoặc hoàn | Không giải phóng quyền lợi hoặc hạn mức khi kết quả còn có thể thành công |

Với cuộc đua, dùng hai kết nối và điểm đồng bộ rõ ràng để điều khiển thứ tự đọc, giữ chỗ và commit. Chỉ kiểm thử tuần tự không phát hiện được lỗi cùng đọc một ngân sách còn lại.

### 12.3. Các thuộc tính nên kiểm tra trên nhiều đầu vào

```text
0 <= tổng giảm <= tổng cơ sở

Tổng phân bổ = tổng giảm

Mỗi phân bổ nằm trong cơ sở tương ứng

Tổng còn phải trả = tổng cơ sở - tổng giảm

Cùng snapshot và cùng chính sách -> cùng kết quả

Đổi thứ tự đầu vào nhưng giữ khóa -> cùng kết quả theo khóa

Retry cùng hành động -> cùng hiệu lực nghiệp vụ
```

Không khẳng định mọi dòng luôn được giảm đúng tỷ lệ sau làm tròn: chính sách tổng đơn và phân bổ phần dư có thể làm các dòng lệch một đơn vị. Cũng không khẳng định tách thành các đơn độc lập luôn cho tổng giống một đơn nếu chương trình cố ý áp trần riêng theo đơn.

Sau kiểm thử, kiểm tra đơn, dòng, lượt dùng, audit, số đã thu và số đã hoàn. Phản hồi HTTP hoặc tổng hiển thị khớp chưa chứng minh mọi hiệu lực bên dưới nhất quán.

## 13. Những quyết định cần chốt khi triển khai

- Giảm trên cơ sở nào và làm tròn tại phạm vi nào?
- Đại lượng có thẩm quyền là tổng giảm hay tổng phải trả, và đại lượng còn lại được suy ra thế nào?
- Trần, lượt dùng và ngân sách thuộc đơn, người dùng hay chiến dịch?
- Phân bổ phần dư dựa trên khóa ổn định nào, có bị client thao túng không?
- Thứ tự cộng dồn, ngưỡng tối thiểu và phiên bản chính sách được giữ ra sao?
- Hoàn từng phần có dùng phân bổ gốc và giới hạn còn lại an toàn khi chạy đồng thời không?
- Backend, database, audit và nhà cung cấp có cùng hiểu tiền tệ và đơn vị không?

Một quy tắc giảm giá an toàn cần cho ra số tiền xác định được, giữ đúng tổng và chống được thay đổi cách biểu diễn giao dịch để nhận thêm lợi ích. Khi số giảm, phân bổ, quyền sử dụng và hiệu lực hoàn cùng được bảo vệ, làm tròn trở thành phần có thể kiểm chứng của logic nghiệp vụ.
