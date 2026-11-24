# Rounding mode selection — Lựa chọn chế độ làm tròn

## 1. Làm tròn là một quyết định nghiệp vụ

Trong chương **Rounding Rules**, lựa chọn chế độ làm tròn quyết định giá trị nào được ghi nợ, ghi có, thu phí hoặc hoàn lại khi kết quả tính toán không nằm đúng trên đơn vị mà hệ thống hỗ trợ. Sai lệch một đơn vị nhỏ có thể lặp lại trên nhiều giao dịch, hoặc bị khai thác bằng cách chia nhỏ yêu cầu và chọn giá trị sát biên.

Một chính sách làm tròn đầy đủ không chỉ là `HALF_UP` hay `HALF_EVEN`. Nó cần xác định:

```text
loại phép tính và phạm vi nghiệp vụ
mã tiền, đơn vị ghi nhận và bước lượng tử hóa
chế độ làm tròn
thời điểm làm tròn và thứ tự tính toán
phạm vi tổng hợp: từng dòng, từng đơn hay một kỳ
cách phân bổ phần chênh lệch
phiên bản chính sách và dữ liệu đầu vào
```

Bài học tập trung vào thiết kế ứng dụng Java có xử lý tiền. Các quy tắc riêng của hợp đồng, kênh thanh toán hoặc nghĩa vụ áp dụng phải được đưa vào cấu hình được kiểm soát; không suy ra một chế độ mặc định bắt buộc cho mọi sản phẩm.

## 2. Tách scale, precision và quantum

### 2.1. Scale: số chữ số thập phân cần biểu diễn

Ví dụ `12.34` có scale 2. Nếu chính sách ghi nhận hỗ trợ một đơn vị bằng `0.01`, một số tiền cuối cùng có thể được biểu diễn bằng số nguyên minor unit như `1234`.

Scale cần lấy từ hợp đồng của sản phẩm và thao tác cụ thể. Không mặc định mọi mã tiền, tài khoản, charge và payout đều dùng hai chữ số thập phân. Tài liệu Stripe, chẳng hạn, mô tả minor unit và một số ngoại lệ theo loại tiền/thao tác. Xem [Stripe: Supported currencies](https://docs.stripe.com/currencies).

### 2.2. Precision: tổng số chữ số có nghĩa

Precision không đồng nghĩa với số chữ số sau dấu thập phân. Làm tròn đến 2 chữ số có nghĩa có thể biến `123.45` thành `120`, trong khi làm tròn đến 2 chữ số sau dấu thập phân giữ `123.45`.

Trong Java, cần phân biệt `MathContext` theo precision với `setScale` theo số chữ số thập phân. Nếu vô tình đặt precision nhỏ cho một phép nhân trung gian, dữ liệu có thể đã bị làm tròn trước khi áp dụng chính sách ghi nhận cuối.

### 2.3. Quantum: bước giá trị được phép

Một kênh có thể yêu cầu bước `0.05` trong khi dữ liệu vẫn có scale 2. Khi đó `1.03` có hai chữ số thập phân nhưng chưa nằm trên bước hợp lệ.

Công thức lượng tử hóa theo bước `q > 0`:

```text
units = exact_amount / q
rounded_units = làm tròn units về số nguyên theo mode
booked_amount = rounded_units × q
```

Với bước `0.05` và `HALF_UP`, `1.03` thành `1.05`, còn `1.02` thành `1.00`. Chỉ gọi `setScale(2, ...)` không thực hiện quy tắc bước `0.05`.

Đơn vị API, bước tiền mặt và precision tính toán có thể khác nhau. Cần đặt tên và phiên bản cho từng khái niệm thay vì gom tất cả vào một field `decimalPlaces`.

## 3. Các chế độ làm tròn trong Java

Bảng sau dùng đầu vào thập phân chính xác và làm tròn đến scale 2:

| Mode | Cách chọn | `2.345` | `-2.345` |
| --- | --- | --- | --- |
| `UP` | Xa 0 | `2.35` | `-2.35` |
| `DOWN` | Về 0 | `2.34` | `-2.34` |
| `CEILING` | Về phía dương vô cùng | `2.35` | `-2.34` |
| `FLOOR` | Về phía âm vô cùng | `2.34` | `-2.35` |
| `HALF_UP` | Gần nhất; hòa thì xa 0 | `2.35` | `-2.35` |
| `HALF_DOWN` | Gần nhất; hòa thì về 0 | `2.34` | `-2.34` |
| `HALF_EVEN` | Gần nhất; hòa thì chọn chữ số cuối được giữ là chẵn | `2.34` | `-2.34` |
| `UNNECESSARY` | Yêu cầu kết quả biểu diễn được chính xác | Ném lỗi | Ném lỗi |

Tên gọi và ngữ nghĩa của các mode được quy định trong [Java SE 21: RoundingMode](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/math/RoundingMode.html).

Ở ví dụ `2.355`, `HALF_EVEN` cho `2.36`, vì chữ số hàng phần trăm được chọn là 6. Nó không có nghĩa mọi giá trị kết thúc bằng 5 đều bị làm tròn xuống.

“Điểm hòa” là trường hợp giá trị nằm đúng giữa hai giá trị được phép. Một số nhận từ `double` có thể không còn nằm đúng giữa dù khi hiển thị trông như vậy. Ví dụ kiểm thử biên cần tạo từ chuỗi thập phân chính xác.

### UNNECESSARY dùng để kiểm tra tính biểu diễn được

Với scale 2, `2.3400` có thể chuyển thành `2.34` mà không đổi giá trị; `UNNECESSARY` cho phép trường hợp này. `2.341` cần thay đổi giá trị nên bị từ chối.

Nếu hợp đồng API yêu cầu cả định dạng chuỗi có đúng hai chữ số, cần kiểm tra định dạng riêng. Tính biểu diễn được về số học và quy tắc định dạng đầu vào là hai điều kiện khác nhau.

## 4. Chọn mode dựa trên nghĩa vụ cụ thể

Không có một mode duy nhất giải quyết được mọi quy tắc. Một bảng quyết định có thể bắt đầu như sau:

| Loại yêu cầu | Hướng lựa chọn | Điều kiện cần làm rõ |
| --- | --- | --- |
| Làm tròn gần nhất theo hợp đồng | Chọn một trong các mode `HALF_*` phù hợp | Quy tắc hòa, scale/quantum và thời điểm áp dụng |
| Hạn chế thiên lệch khi nhiều lần gặp điểm hòa | Có thể chọn `HALF_EVEN` | Phân bố dữ liệu, phạm vi tổng hợp và khả năng người dùng chọn đầu vào |
| Phí dương phải được nâng tới một đơn vị theo chính sách | Có thể cần `CEILING` trên độ lớn dương | Hướng tiền, phí tối thiểu, trần phí và cách hoàn phí |
| Ghi nhận chỉ được phép với giá trị chính xác | `UNNECESSARY` tại ranh giới kiểm tra | Đầu vào đã được tính theo chính sách ở bước nào |
| Đảo một khoản đã ghi nhận | Đảo đúng số minor unit đã ghi | Không tính lại giá trị gốc rồi làm tròn theo cấu hình mới |
| Phân bổ tổng đã chốt | Thuật toán phân bổ có bảo toàn tổng | Mode từng phần, thứ tự xử lý phần dư và danh tính dòng |

`HALF_EVEN` có thể giảm thiên lệch do các điểm hòa trong những điều kiện phù hợp. Nó không tự bảo đảm dữ liệu thực tế không thiên lệch, và không chống được người dùng chủ động chọn các giá trị có lợi. Vẫn phải bảo vệ phạm vi tổng hợp, phí và giới hạn nghiệp vụ.

Nếu nguồn chính sách yêu cầu một quy tắc khác, triển khai đúng quy tắc đó và ghi nhận phiên bản. Không thay bằng mode được coi là “hợp lý hơn” chỉ vì một thư viện đang dùng nó làm mặc định.

### Xác định rõ ai chịu phần chênh lệch

Khi `booked_amount` khác `exact_amount`, cần biết phần chênh thuộc người mua, người bán, nền tảng hay một tài khoản xử lý chênh lệch. Không để quyết định này phát sinh ngẫu nhiên từ việc một dịch vụ dùng `FLOOR`, dịch vụ khác dùng `HALF_UP`.

Có thể lưu:

```text
rounding_delta = booked_amount - exact_amount
```

Quy ước dấu phải nhất quán và gắn với mã tiền. Nếu delta nhỏ hơn đơn vị ghi sổ, nó có thể chỉ là dữ kiện tính toán; việc tích lũy hoặc ghi sổ phần lẻ cần mô hình riêng.

## 5. Số âm, hoàn tiền và hướng ghi sổ

### 5.1. DOWN không đồng nghĩa với FLOOR

Với số âm, `DOWN` đưa về 0 còn `FLOOR` đưa về phía âm vô cùng. `-2.345` thành `-2.34` bằng `DOWN`, nhưng thành `-2.35` bằng `FLOOR`.

Nhiều hệ thống lưu số tiền nghiệp vụ dưới dạng độ lớn dương và dùng loại thao tác để chỉ hướng tiền. Một hệ thống khác dùng số có dấu cho biến động sổ cái. Chính sách phải xác định đang làm tròn đại lượng nào; không suy ra “có lợi cho người nhận” chỉ từ tên mode.

### 5.2. Đảo khoản đã ghi nhận bằng giá trị đã ghi nhận

Giả sử phí chính xác là `0.001`, chính sách phí dương dùng `CEILING` đến `0.01`, nên đã thu `0.01`.

Nếu muốn đảo toàn bộ phí đã thu, phải đảo đúng `0.01` theo nghiệp vụ. Lấy `-0.001` làm tròn bằng `CEILING` đến hai chữ số sẽ cho `0.00`; thao tác đó không triệt tiêu khoản phí đã ghi.

Do đó, snapshot và minor unit của giao dịch đã chốt là đầu vào quan trọng cho hoàn/đảo. Hoàn tiền một phần cần chính sách phân bổ riêng và tổng tích lũy không vượt phần được phép hoàn; không áp dụng lại công thức giá hiện tại cho từng lần thử rồi bỏ qua lịch sử.

### 5.3. Không giả định mọi mode đối xứng theo dấu

Với mode gần nhất có quy tắc hòa đối xứng, có thể kiểm tra quan hệ `R(-x) = -R(x)` trong miền hợp lệ. Với `CEILING` và `FLOOR`, quan hệ tương ứng là `CEILING(-x) = -FLOOR(x)`.

Chỉ dùng thuộc tính phù hợp với mode đã chọn. Một bộ kiểm thử mặc định đòi mọi mode phải đối xứng sẽ đánh giá sai thiết kế có chủ đích.

## 6. Chọn thời điểm làm tròn và phạm vi tổng hợp

### 6.1. Tổng các giá trị đã làm tròn có thể khác làm tròn tổng

Giả sử có ba dòng, mỗi dòng có giá trị chính xác `0.335`, dùng `HALF_UP` đến scale 2:

```text
Làm tròn từng dòng:
  0.335 -> 0.34
  0.335 -> 0.34
  0.335 -> 0.34
  Tổng = 1.02

Cộng chính xác rồi làm tròn tổng:
  0.335 × 3 = 1.005
  1.005 -> 1.01
```

Cả hai kết quả đều có thể phù hợp với một hợp đồng cụ thể, nhưng chúng không được thay thế nhau tùy dịch vụ. Nếu tổng đơn đã chốt là `1.01`, việc phân bổ xuống các dòng phải bảo toàn `1.01` thay vì tự tạo `1.02`.

Chính sách phải nói rõ làm tròn theo dòng, theo nhóm thuế/phí, theo đơn hay theo kỳ. Chỉ dùng một mode thống nhất vẫn có thể cho kết quả khác nếu các điểm làm tròn khác nhau.

### 6.2. Tránh làm tròn trung gian ngoài chủ đích

Ví dụ cùng dùng `HALF_UP`:

```text
Trực tiếp đến 2 chữ số:
  1.2449 -> 1.24

Qua một bước 3 chữ số rồi đến 2 chữ số:
  1.2449 -> 1.245 -> 1.25
```

Đây là double rounding. Giữ đủ dữ liệu tính toán đến ranh giới chính sách thay vì liên tục ép scale theo cột lưu hoặc định dạng hiển thị.

Một số phép chia cần precision trung gian hữu hạn. Khi đó phải thiết kế precision và kiểm tra sai số để quyết định cuối đáng tin cậy, hoặc dùng biểu diễn hữu tỷ/thuật toán phù hợp. Không chọn tùy ý vài chữ số trung gian rồi cho rằng kết quả cuối luôn giống tính toán chính xác.

### 6.3. Chia nhỏ yêu cầu có thể làm đổi nghĩa vụ

Nếu phí chính xác cho mỗi phần là `0.0049` và hệ thống làm tròn từng phần xuống `0.00` bằng một mode gần nhất, 100 phần có thể tạo tổng phí bằng 0. Trong khi đó, tính trên tổng cơ sở tương ứng rồi làm tròn một lần có thể tạo phí `0.49`.

Sự khác biệt chỉ là lỗ hổng khi trái chính sách đã định nghĩa. Nếu chính sách yêu cầu tổng hợp theo một đơn hoặc một kỳ, hệ thống phải ngăn client dùng nhiều request, dòng hoặc key để đổi phạm vi đó. Các biện pháp có thể gồm định danh nhóm nghiệp vụ, phí tối thiểu được công bố và bộ đếm tích lũy được cập nhật nguyên tử.

Không thay mode một cách ngẫu nhiên khi phát hiện yêu cầu nhỏ. Điều chỉnh quy tắc phải có phiên bản và áp dụng nhất quán cho nghĩa vụ tương ứng.

## 7. Phân bổ phần dư mà vẫn bảo toàn tổng

Khi phân bổ một tổng đã chốt, không thể chỉ làm tròn độc lập từng phần rồi bỏ qua chênh lệch.

Ví dụ chia tổng 10 cent cho ba dòng có trọng số bằng nhau:

```text
Giá trị lý tưởng: 3.333... cent cho mỗi dòng
Lấy phần nguyên: 3 + 3 + 3 = 9 cent
Còn dư: 1 cent
Phân bổ phần dư theo quy tắc ổn định: 4 + 3 + 3 = 10 cent
```

Một thuật toán phổ biến cho phần dương là lấy phần nguyên theo đơn vị nhỏ nhất, sau đó phân phối phần dư theo phần lẻ lớn nhất. Khi phần lẻ bằng nhau, dùng khóa dòng ổn định hoặc quy tắc đã công bố. Phải lưu kết quả phân bổ để hoàn tiền từng phần có thể dùng lại.

Một khóa ổn định chỉ giải quyết tính tái lập. Nếu client được tùy ý tạo thêm dòng hoặc đổi danh tính dòng để lấy nhiều phần dư, vẫn cần bảo vệ cấu trúc nhóm và quyền tạo dòng. Kiểm tra bất biến:

```text
Tổng các phần đã phân bổ = tổng đã chốt
Mỗi phần tuân thủ đơn vị của loại tiền
Không phân bổ cho dòng không đủ điều kiện
Kết quả replay với cùng dữ kiện và chính sách không đổi
```

Với giá trị âm hoặc nhóm có cả hai hướng tiền, không tự dùng nguyên thuật toán phần dương. Có thể phân bổ độ lớn rồi gắn hướng nếu chính sách cho phép, nhưng phải chứng minh kết quả giữ đúng tổng và giới hạn của từng dòng.

## 8. Mã Java áp dụng policy có phiên bản

Ví dụ dưới đây minh họa một bộ lượng tử hóa dùng policy từ registry đáng tin ở máy chủ. Các giới hạn miền tiền, quyền, công thức giá và thời điểm áp dụng vẫn thuộc tầng nghiệp vụ gọi nó:

```java
import java.math.BigDecimal;
import java.math.RoundingMode;
import java.util.Objects;

record RoundingPolicy(
        String id,
        int version,
        String currency,
        int scale,
        BigDecimal quantum,
        RoundingMode mode) {}

final class MoneyRounding {
    static BigDecimal apply(
            BigDecimal exact,
            String currency,
            RoundingPolicy policy) {
        Objects.requireNonNull(exact);
        Objects.requireNonNull(currency);
        Objects.requireNonNull(policy);
        Objects.requireNonNull(policy.quantum());
        Objects.requireNonNull(policy.mode());

        if (!currency.equals(policy.currency())) {
            throw new IllegalArgumentException("Currency mismatch");
        }
        if (policy.scale() < 0 || policy.scale() > 6) {
            throw new IllegalArgumentException("Unsupported scale");
        }
        if (policy.quantum().signum() <= 0) {
            throw new IllegalArgumentException("Invalid quantum");
        }

        // Quantum phải biểu diễn được bằng minor unit của policy.
        policy.quantum()
                .movePointRight(policy.scale())
                .toBigIntegerExact();

        BigDecimal units = exact.divide(
                policy.quantum(), 0, policy.mode());
        return units.multiply(policy.quantum())
                .setScale(policy.scale(), RoundingMode.UNNECESSARY);
    }
}
```

Khoảng scale `0..6` chỉ là ví dụ miền hỗ trợ của sản phẩm này, không phải giới hạn của `BigDecimal` hoặc quy tắc cho mọi loại tiền. Policy cần được kiểm tra khi nạp cấu hình, có mã tiền, giá trị hợp lệ và phiên bản được phép dùng.

Phép chia về số đơn vị nguyên là điểm làm tròn có chủ đích. `setScale(..., UNNECESSARY)` cuối cùng chỉ xác minh biểu diễn, không âm thầm thêm một lần làm tròn mới.

Ví dụ sử dụng:

```java
RoundingPolicy policy = new RoundingPolicy(
        "order-total-usd", 3, "USD", 2,
        new BigDecimal("0.01"), RoundingMode.HALF_EVEN);

BigDecimal exact = new BigDecimal("2.345");
BigDecimal booked = MoneyRounding.apply(exact, "USD", policy);
long bookedMinor = booked.movePointRight(policy.scale()).longValueExact();
// booked = 2.34; bookedMinor = 234
```

Các thao tác scale, precision, chia và chuyển đổi chính xác được mô tả trong [Java SE 21: BigDecimal](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/math/BigDecimal.html).

### Những kiểm tra cần nằm ngoài bộ lượng tử hóa

- Số tiền có nguồn gốc từ quy tắc giá đáng tin, không phải giá client tự chọn.
- Miền độ dài, precision, exponent và trị tuyệt đối của đầu vào được giới hạn trước tính toán tốn kém.
- Dấu của giá trị phù hợp với loại nghiệp vụ; API thu tiền không tự chấp nhận số âm.
- Kết quả sau lượng tử hóa nằm trong giới hạn, không tràn kiểu số nguyên và không vi phạm mức tối thiểu.
- Policy được chọn theo loại nghiệp vụ, mã tiền, kênh và phiên bản, không theo tham số tùy ý của người dùng.

Nếu `UNNECESSARY`, `longValueExact()` hoặc kiểm tra miền thất bại, không bắt lỗi rồi thử lại bằng `DOWN` để “cứu” giao dịch. Phải phân loại nguyên nhân: dữ liệu không biểu diễn được, cấu hình không tương thích hoặc kết quả vượt miền hỗ trợ.

## 9. Đồng nhất quy tắc giữa API, Java, cơ sở dữ liệu và adapter

### 9.1. Tránh phụ thuộc vào mode mặc định của từng tầng

Một phép tính có thể đi qua frontend, dịch vụ Java, cơ sở dữ liệu và nhà cung cấp. Tên hàm `round` giống nhau không chứng minh ngữ nghĩa giống nhau.

Ví dụ PostgreSQL `numeric` làm tròn điểm hòa ra xa 0. Vì vậy:

```sql
SELECT round(2.345::numeric, 2);
-- 2.35
```

Trong khi Java với `HALF_EVEN` và scale 2 cho `2.34`. PostgreSQL cũng có thể làm tròn khi giá trị được đưa vào cột `numeric` có scale giới hạn. Xem [PostgreSQL 18: Numeric Types](https://www.postgresql.org/docs/18/datatype-numeric.html).

Không để phép ép kiểu khi lưu tự chọn kết quả nghiệp vụ. Một cách thiết kế là lưu số tiền đã chốt bằng minor unit nguyên, đồng thời lưu snapshot tính toán riêng với precision phù hợp. Nếu dùng cột thập phân, cần bảo đảm giá trị đưa vào đã đúng miền và không còn bước làm tròn ngoài chủ đích.

### 9.2. Tách hiển thị khỏi số tiền thực thi

Giao diện có thể định dạng số tiền theo locale, dấu phân cách và số chữ số để dễ đọc. Chuỗi hiển thị không được dùng ngược làm dữ liệu tính tiền có thẩm quyền.

Client cần gửi ý định như đơn hàng, báo giá hoặc nguồn tiền; máy chủ xác định số tiền và policy. Khi cần người dùng chấp thuận nghĩa vụ, hiển thị đúng giá trị sẽ ghi nhận và ràng buộc sự chấp thuận với snapshot đó.

Ở adapter, ghi rõ đơn vị API, giới hạn và quy tắc theo từng loại thao tác. Không chia/nhân 100 theo thói quen rồi để nhà cung cấp sửa phần lẻ. Nếu hai bên không thể biểu diễn cùng số tiền, từ chối hoặc dùng luồng xử lý đã thiết kế trước khi tạo hiệu ứng bên ngoài.

### 9.3. Dùng bộ dữ liệu chuẩn chung

Các tầng có thể chia sẻ một bộ trường hợp có:

```text
policy_id, policy_version
currency, scale, quantum, mode, stage
exact_input và các thành phần tạo ra nó
expected_booked_minor
expected_allocation nếu có
expected_failure khi không biểu diễn được
```

Dùng cùng dữ liệu để kiểm chứng dịch vụ tính giá, API thanh toán, job đối soát và adapter. Mục tiêu là kiểm tra hợp đồng, không chỉ gọi lại đúng hàm triển khai rồi khẳng định kết quả khớp.

## 10. Ràng buộc policy với giao dịch và quyền thay đổi

### 10.1. Không cho client chọn mode có lợi

Một request thanh toán không nên tự điều khiển `roundingMode`, scale hoặc công thức tổng hợp. Máy chủ chọn policy từ dữ kiện đã xác minh, như sản phẩm, loại tiền, kênh và loại thao tác.

Việc đổi từ `HALF_UP` sang `DOWN` có thể chỉ thay một enum nhưng làm thay đổi nghĩa vụ trên nhiều giao dịch. Quyền chỉnh cấu hình tiền phải được giới hạn, có phiên bản, thời điểm hiệu lực và dấu vết phê duyệt phù hợp với mức ảnh hưởng.

Các đường thực thi như API quản trị, import, batch và consumer phải dùng cùng quy tắc hoặc một policy riêng được định nghĩa rõ. Không để công cụ nội bộ mặc định bỏ qua mode vì người gọi là nhân viên.

### 10.2. Thực hiện trên đúng snapshot đã được chấp nhận

Một luồng có thể là:

```text
Tính giá theo policy có phiên bản
  -> tạo snapshot các thành phần và số tiền cuối
  -> hiển thị/xin phê duyệt theo quy trình nghiệp vụ
  -> thực thi đúng snapshot còn hợp lệ
  -> ghi số tiền, policy và hiệu ứng cùng transaction phù hợp
```

Nếu thay giá, phí, mode hoặc phạm vi tổng hợp, snapshot mới có thể cần được chấp thuận lại. Một cờ `approved = true` không đủ nếu số tiền thực thi đã đổi.

Kiểm tra giới hạn phải dựa trên đại lượng cuối sẽ thực hiện theo hợp đồng. Ví dụ giá trị chính xác `99.995` được `HALF_UP` thành `100.00`; nếu người dùng chỉ cho phép chi tối đa `99.99`, hệ thống không được chấp nhận vì trước làm tròn trông gần với giới hạn.

Với mức tối thiểu, giá trị dương có thể làm tròn thành 0. Xác định rõ có cho miễn khoản đó, gộp tích lũy hay từ chối. Không để nó vô tình đi qua nhánh thanh toán miễn phí khi chính sách yêu cầu thu tiền.

### 10.3. Idempotency và thay đổi cấu hình

Replay cùng ý định đã được nhận phải tìm kết quả hoặc snapshot cũ, không tính lại bằng mode hiện tại. Fingerprint cần ràng buộc ý định và phiên bản dữ liệu phù hợp; kết quả đã chốt gắn với policy thực sự được dùng.

Nếu một yêu cầu đang chờ còn được phép dùng policy cũ, lưu quyết định đó. Nếu phải chuyển sang policy mới, cần một phiên bản ý định mới và quy trình xác nhận tương ứng. Không để một lần retry do mất mạng tự đổi số tiền.

Cơ chế idempotency không ngăn client chia một nghĩa vụ thành nhiều ý định mới. Việc bảo vệ phạm vi tổng hợp và hạn mức tích lũy vẫn phải dựa trên định danh nghiệp vụ, transaction và ràng buộc phù hợp.

## 11. Lưu bằng chứng và xử lý điều chỉnh

Một snapshot làm tròn tối thiểu có thể gồm:

```json
{
  "calculationId": "calc-62",
  "currency": "USD",
  "exactAmount": "2.345",
  "bookedMinor": "234",
  "scale": 2,
  "quantum": "0.01",
  "mode": "HALF_EVEN",
  "stage": "ORDER_TOTAL",
  "policyId": "order-total-usd",
  "policyVersion": 3,
  "roundingDelta": "-0.005",
  "deltaConvention": "BOOKED_MINUS_EXACT"
}
```

Hồ sơ đầy đủ còn cần các thành phần tính giá, dữ liệu chấp thuận, execution, journal, thời điểm và phiên bản cấu hình liên quan. Nếu chỉ lưu `mode`, không thể biết đã làm tròn trước hay sau thuế, phí hoặc phân bổ.

Tái dựng từ dữ liệu lịch sử và so sánh với số tiền đã ghi nhận. Một rounding delta có thể giải thích được không đồng nghĩa việc tính giá ban đầu có thẩm quyền; vẫn cần xác minh nguồn giá, quyền sửa và công thức nghiệp vụ.

Khi phát hiện lỗi chính sách hoặc triển khai:

1. Xác định phiên bản, khoảng thời gian và nhóm giao dịch chịu ảnh hưởng.
2. Tính chênh lệch bằng dữ kiện gốc và quy tắc đúng đã được xác định.
3. Quyết định nghiệp vụ xử lý chênh lệch, quyền phê duyệt và người chịu tiền.
4. Tạo điều chỉnh có định danh, chống trùng và liên kết với giao dịch gốc.
5. Giữ nguyên bằng chứng cũ, bổ sung kết quả sửa sai và đối soát.

Không sửa hàng loạt số tiền cũ theo mode mới mà không tạo hiệu ứng tài chính và dấu vết tương ứng. Không gộp một khoản thu sai giá, sai phí hoặc sai tỷ giá vào “sai số làm tròn” chỉ để bỏ qua kiểm tra.

## 12. Thiết kế kiểm thử cho lựa chọn mode

### 12.1. Điểm hòa và lân cận

Dùng chuỗi thập phân chính xác và giá trị kỳ vọng được xác định độc lập:

| Đầu vào | Policy | Kết quả |
| --- | --- | --- |
| `2.3449` | scale 2, `HALF_EVEN` | `2.34` |
| `2.3450` | scale 2, `HALF_EVEN` | `2.34` |
| `2.3451` | scale 2, `HALF_EVEN` | `2.35` |
| `2.3550` | scale 2, `HALF_EVEN` | `2.36` |
| `-2.3450` | scale 2, `HALF_EVEN` | `-2.34` |
| `-2.3550` | scale 2, `HALF_EVEN` | `-2.36` |
| `2.3400` | scale 2, `UNNECESSARY` | `2.34` |
| `2.3410` | scale 2, `UNNECESSARY` | Lỗi biểu diễn chính xác |
| `1.025` | quantum `0.05`, `HALF_EVEN` | `1.00` |
| `1.025` | quantum `0.05`, `HALF_UP` | `1.05` |

Bổ sung các mode còn lại, số 0, giá trị rất nhỏ và giới hạn lớn nhất của miền sản phẩm. Kiểm tra quantum không hợp lệ, scale không hỗ trợ và tràn kiểu khi chuyển sang minor unit.

### 12.2. Thuộc tính số học phù hợp với chính sách

Với `R` là phép lượng tử hóa và miền hợp lệ:

```text
R(R(x)) = R(x) với cùng policy.
R(x) là một bội số nguyên của quantum.
Mode gần nhất: |R(x) - x| <= quantum / 2.
Kết quả và lỗi xác định được từ cùng snapshot/policy.
Tổng phân bổ bằng tổng đã chốt.
```

Không áp dụng giới hạn `quantum / 2` cho `CEILING`, `FLOOR`, `UP` hay `DOWN`; chúng có hướng làm tròn khác. Không giả định `R(x + y) = R(x) + R(y)` vì chính sự không bằng nhau đó là một nguồn rủi ro cần kiểm tra.

### 12.3. Tình huống tấn công logic

- Sửa mode, scale hoặc quantum trong request: không thay policy có thẩm quyền.
- Tạo nhiều dòng hoặc nhiều request để giảm phí trái phạm vi tổng hợp: tổng nghĩa vụ vẫn theo chính sách.
- Đổi thứ tự dòng để nhận phần dư: kết quả theo quy tắc phân bổ, không theo thứ tự tùy ý từ client.
- Hoàn nhiều lần bằng các key khác nhau: tổng hoàn và phân bổ không vượt giá trị gốc được phép.
- Tạo giá trị âm trên API thu tiền: bị chặn theo loại nghiệp vụ, không biến làm tròn thành cộng tiền.
- Chọn giá trị khiến số tiền sau làm tròn vượt mức đã chấp thuận: không thực thi vượt mức.
- Replay sau khi đổi cấu hình: không tính lại hiệu ứng đã chốt bằng policy mới.
- Dùng API quản trị hoặc batch để ghi giá trị chưa lượng tử hóa: vẫn chịu kiểm tra tương ứng.

Nếu quy tắc gộp phí theo kỳ hoặc cộng dồn phần lẻ được hỗ trợ, kiểm thử nhiều transaction đồng thời để chắc chắn không mất cập nhật và không tiêu thụ cùng phần dư hai lần.

### 12.4. Kiểm thử xuyên tầng và thất bại

Đưa cùng bộ dữ liệu qua service, cơ sở dữ liệu, adapter và đối soát. Xác minh không có coercion hoặc định dạng làm đổi giá trị. Gây lỗi khi lưu snapshot, journal hoặc trạng thái xử lý và kiểm tra không có hiệu ứng tiền đã commit thiếu căn cứ bắt buộc.

Những tình huống này là thiết kế kiểm thử cho triển khai thực tế, không phải khẳng định các ví dụ mã trong bài đã được tích hợp với một ứng dụng cụ thể.

## 13. Các câu hỏi cần chốt trước khi phát hành một policy

- Đại lượng cần làm tròn là giá, thuế, phí, tổng thanh toán hay số tiền phân bổ?
- Đơn vị ghi nhận và quantum được lấy từ đâu, cho thao tác và mã tiền nào?
- Vì sao mode được chọn phù hợp với nghĩa vụ đã cam kết?
- Các bước trung gian và phạm vi tổng hợp có được định nghĩa đầy đủ không?
- Số âm, khoản hoàn và phần dư được xử lý theo quy tắc nào?
- Ai có quyền thay đổi policy, và phiên bản mới ảnh hưởng yêu cầu đang chờ ra sao?
- Snapshot nào cho phép tái dựng, replay và đối soát kết quả lịch sử?
- Các đường API, batch, quản trị và adapter có cho cùng kết quả theo hợp đồng không?

Lựa chọn mode chỉ hoàn chỉnh khi nó gắn với đúng đơn vị, thời điểm, phạm vi và quyền quyết định. Những ràng buộc đó giúp việc làm tròn trở thành một phần kiểm soát được của logic nghiệp vụ, thay vì một mặc định khó thấy trong thư viện.
