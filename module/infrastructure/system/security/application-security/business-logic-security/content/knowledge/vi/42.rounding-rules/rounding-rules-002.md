# Rounding point: xác định đúng thời điểm làm tròn tiền

## 1. Làm tròn ở đâu cũng là một quy tắc nghiệp vụ

*Rounding point* là điểm trong chuỗi xử lý mà một giá trị được chuyển sang độ chia tiền tệ đã quy định. Đó có thể là lúc chốt giá một dòng hàng, tính tổng giảm giá của đơn, xác định thuế, tính phí hoặc ghi nhận số tiền thanh toán.

Trong chương **Rounding Rules**, điều cần bảo vệ không chỉ là chọn một chế độ như `HALF_UP`. Backend còn phải xác định **làm tròn giá trị nào, ở cấp độ nào, trước hay sau phép tính nào, và kết quả nào trở thành nghĩa vụ tiền tệ chính thức**.

Xét mô hình tiền giả định **U**, có đơn vị hạch toán nhỏ nhất là **0,01 U**. Các tỷ lệ và cách tính trong bài chỉ là chính sách minh họa, không đại diện cho quy định thuế, kế toán hoặc thanh toán của một quốc gia.

Có ba dòng hàng, mỗi dòng có cơ sở tính thuế là `0,05 U`. Thuế suất minh họa là `10%`, làm tròn hai chữ số bằng `HALF_UP`:

~~~text
Tính và làm tròn thuế từng dòng:
  round(0,05 × 10%) = round(0,005) = 0,01
  Tổng thuế = 0,01 + 0,01 + 0,01 = 0,03 U

Tính thuế trên tổng hóa đơn:
  round((0,05 + 0,05 + 0,05) × 10%)
  = round(0,015)
  = 0,02 U
~~~

Cùng dữ liệu, cùng chế độ làm tròn nhưng khác điểm làm tròn tạo ra hai kết quả khác nhau. Mỗi cách có thể đúng nếu đó là chính sách được lựa chọn cho nghiệp vụ tương ứng. Lỗi xuất hiện khi các thành phần dùng lẫn hai cách hoặc cho người gọi tự chọn cách có lợi.

Trong bảo mật logic nghiệp vụ, chênh lệch nhỏ có thể trở thành cơ chế lạm dụng nếu được lặp lại qua hàng nghìn lần tách dòng hàng, chia thanh toán, đổi tiền hoặc hoàn tiền. Một lỗi chỉ lệch một đơn vị nhỏ nhất vẫn có thể vi phạm business invariant.

## 2. Phân biệt độ chính xác, độ chia, chế độ và điểm làm tròn

### 2.1. Bốn khái niệm khác nhau

| Khái niệm | Câu hỏi cần trả lời | Ví dụ |
|---|---|---|
| Độ chính xác tính toán | Cần giữ bao nhiêu thông tin trong phép tính trung gian? | Giữ giá đơn vị `1,005 U` để nhân số lượng |
| Độ chia hạch toán, hay quantum | Số tiền chính thức phải là bội số của đơn vị nào? | `0,01 U` |
| Chế độ làm tròn | Chọn giá trị nào khi số gốc nằm giữa hai mức? | `HALF_UP`, `HALF_EVEN` hoặc quy tắc khác |
| Điểm làm tròn | Thực hiện phép làm tròn ở bước nghiệp vụ nào? | Sau khi cộng thuế cả hóa đơn |

Scale là số chữ số sau dấu thập phân trong một biểu diễn số. Scale bằng hai có thể biểu diễn bước `0,01` nhưng không tự diễn tả quy tắc chỉ được thanh toán theo bước `0,05`. Nếu quantum không phải lũy thừa của mười, chỉ gọi `setScale` là chưa đủ.

Độ chia dùng để hiển thị, hạch toán và thanh toán tiền mặt cũng có thể khác nhau. Khi có nhiều độ chia, phải đặt tên và điểm áp dụng riêng, chẳng hạn tổng hạch toán và tổng tiền mặt. Không âm thầm ghi đè một giá trị bằng giá trị khác.

### 2.2. Chế độ giống nhau chưa đủ

Với giá đơn vị có độ chính xác cao `1,005 U` và số lượng ba:

~~~text
Làm tròn đơn giá trước:
  round(1,005) × 3 = 1,01 × 3 = 3,03 U

Nhân số lượng rồi làm tròn dòng:
  round(1,005 × 3) = round(3,015) = 3,02 U
~~~

Nếu mô hình sản phẩm cho phép đơn giá chính thức có ba chữ số thập phân, việc cắt đơn giá về hai chữ số khi đọc request là một thay đổi chính sách, không chỉ là làm sạch dữ liệu.

Nếu sản phẩm chỉ chấp nhận đơn giá theo bước `0,01 U`, backend nên từ chối giá không hợp lệ hoặc đi qua quy trình định giá quy định sẵn. Không tùy tiện làm tròn đầu vào rồi coi nó vẫn là mức giá người dùng đã xác nhận.

### 2.3. Dùng số thập phân chính xác không tự sửa điểm làm tròn

`BigDecimal` giúp tránh nhiều sai số biểu diễn của số thực nhị phân, nhưng vẫn có thể cho ra kết quả sai nghiệp vụ nếu gọi `setScale` quá sớm hoặc ở sai cấp.

Ví dụ có rủi ro:

~~~java
// Sai nếu chính sách yêu cầu tính thuế trên tổng hóa đơn.
BigDecimal tax = lines.stream()
        .map(line -> line.taxableBase()
                .multiply(taxRate)
                .setScale(2, RoundingMode.HALF_UP))
        .reduce(BigDecimal.ZERO, BigDecimal::add);
~~~

Đoạn mã không sai cú pháp. Điều cần đối chiếu là chính sách quy định thuế theo dòng hay theo hóa đơn.

Tránh khởi tạo số tiền bằng `new BigDecimal(0.1)` vì giá trị `double` đã có biểu diễn nhị phân trước khi chuyển đổi. Với dữ liệu thập phân, phân tích từ chuỗi đã kiểm tra hoặc từ biểu diễn số nguyên theo đơn vị nhỏ nhất phù hợp.

## 3. Invariant cần bảo vệ

### 3.1. Một chính sách được áp dụng nhất quán

Một kết quả tiền tệ phải được tính theo một phiên bản chính sách xác định, gồm ít nhất:

~~~text
Đơn vị tiền và quantum.
Chế độ làm tròn theo từng thành phần.
Cấp áp dụng: đơn vị hàng, dòng, nhóm thuế, đơn hàng hoặc nghiệp vụ.
Thứ tự giảm giá, phí, thuế và chuyển đổi tiền.
Điểm làm tròn của từng thành phần.
Quy tắc phân bổ phần dư.
Quy tắc hoàn hoặc đảo giao dịch.
~~~

Không để frontend, backend, worker và hệ thống thanh toán tự suy diễn khác nhau. Dùng chung một helper toán học cũng chưa đủ nếu các bên gọi helper ở những điểm khác nhau.

### 3.2. Client không được quyết định ranh giới kinh tế

Người gọi có thể đề nghị mua một số lượng hoặc trả lại hàng, nhưng backend phải xác định các đối tượng nghiệp vụ có thẩm quyền: đơn hàng, dòng hàng, khoản phí, lần thanh toán hoặc giao dịch gốc.

Nếu phí được tính cho một đơn hàng, việc client gửi đơn đó thành nhiều request không được tự động biến thành nhiều phạm vi tính phí độc lập. Nếu phí thực sự áp dụng theo mỗi giao dịch thanh toán, chia thành nhiều giao dịch có thể hợp lệ và cho kết quả khác. Chính sách phải nói rõ phạm vi nào được dùng.

Không áp đặt tính bất biến khi tách giao dịch cho mọi sản phẩm. Một sự khác biệt chỉ trở thành lỗi bảo mật khi nó vi phạm ranh giới hoặc điều kiện mà sản phẩm đã chọn.

### 3.3. Tổng các phần phải khớp tổng đã chốt

Trong cùng một loại tiền:

~~~text
Tổng giảm giá phân bổ cho các dòng = giảm giá của đơn.
Tổng thuế phân bổ cho các dòng = thuế đã chốt của nhóm hoặc hóa đơn.
Tổng phần phải trả = tổng thanh toán đã chấp nhận.
Tổng hoàn thành công không vượt quyền hoàn của giao dịch gốc.
~~~

Các thành phần có thể chịu những quy tắc khác nhau, nhưng sau khi chốt phải đối soát được. Không bỏ phần dư hoặc cộng thêm một đơn vị nhỏ nhất vào mọi dòng để làm các số có vẻ hợp lệ.

Nếu cho phép hoàn toàn bộ một khoản tiền, tổng các lần hoàn phải đạt đúng số tiền có quyền hoàn khi đã hoàn đủ. Chỉ bảo đảm “không hoàn vượt” mà luôn giữ lại phần dư ngoài chính sách cũng là lỗi.

### 3.4. Tính lặp lại phải ổn định

Cùng dữ liệu nghiệp vụ bất biến và cùng phiên bản chính sách phải cho cùng kết quả chính thức, không phụ thuộc thứ tự request, thứ tự duyệt dòng hàng hoặc số lần retry.

Một quote đã được chấp nhận không được bị tính lại bằng chính sách mới để thay số tiền đã cam kết. Hoàn hoặc đối soát cần tham chiếu giá trị gốc đã lưu.

### 3.5. Quyền và trạng thái vẫn phải được kiểm tra

Tính đúng số tiền không tạo ra quyền thu hoặc hoàn tiền. Backend vẫn phải kiểm tra quyền trên đối tượng, phê duyệt, trạng thái thanh toán và hạn mức tương ứng.

Một yêu cầu hoàn `0,01 U` vẫn có thể là lạm dụng nếu người gọi không có quyền đối với giao dịch gốc hoặc dùng lại cùng sự kiện trả hàng nhiều lần.

## 4. Các điểm làm tròn thường bị nhầm

### 4.1. Trước hay sau khi cộng

Gọi `R(x)` là phép làm tròn về quantum đã chọn. Nói chung:

~~~text
R(a) + R(b) không nhất thiết bằng R(a + b).
~~~

Với `HALF_UP` tới `0,01 U`:

~~~text
R(0,005) + R(0,005) = 0,02
R(0,005 + 0,005)   = 0,01
~~~

Do đó, chuyển `setScale` từ sau `sum` vào trong `map` có thể thay đổi giá, dù người sửa nghĩ chỉ đang refactor.

### 4.2. Theo đơn vị hàng hay theo dòng hàng

Một dòng có số lượng ba có thể được tính bằng đơn giá chính xác nhân ba, rồi làm tròn. Nếu frontend tách thành ba dòng và backend làm tròn từng dòng, kết quả có thể khác.

Nếu chính sách dựa trên dòng nghiệp vụ do server tạo, không để việc client đổi cách nhóm JSON tự sinh ra ba ranh giới làm tròn mới. Cần xác định khi nào các dòng có cùng sản phẩm và điều kiện giá phải được hợp nhất hoặc tính trong cùng nhóm.

Không gộp máy móc những dòng thực sự có điều kiện khác nhau, chẳng hạn mức thuế, khuyến mại, người bán hoặc phiên bản giá khác. Danh tính kinh tế của dòng phải được xác định trước khi tính tiền.

### 4.3. Trước hay sau giảm giá

Ví dụ ba đơn vị hàng có giá `0,05 U`, giảm `10%`:

~~~text
Giảm giá trên cả nhóm:
  gross = 0,15
  discount = R(0,15 × 10%) = R(0,015) = 0,02
  net = 0,13 U

Giảm từng đơn vị:
  discountPerUnit = R(0,05 × 10%) = 0,01
  totalDiscount = 0,03
  net = 0,12 U
~~~

Cả hai phép tính đều dùng `HALF_UP`. Nếu khuyến mại được định nghĩa ở cấp đơn, cho phép chia dòng để được giảm `0,03` thay vì `0,02` là một đường lách nghiệp vụ.

### 4.4. Phí trên phạm vi nào?

Một khoản phí minh họa bằng `1%` giá trị, làm tròn `HALF_UP`:

~~~text
Một phạm vi tính phí 0,50 U:
  R(0,50 × 1%) = R(0,005) = 0,01 U

Hai phạm vi riêng, mỗi phạm vi 0,25 U:
  R(0,25 × 1%) + R(0,25 × 1%) = 0,00 U
~~~

Nếu phạm vi đúng là một đơn hàng, việc chia request thanh toán không nên làm mất phí của đơn. Nếu phạm vi đúng là từng thanh toán, sản phẩm cần chấp nhận khác biệt hoặc xác định thêm quy tắc phù hợp, như phí tối thiểu. Không tự thêm phí tối thiểu trong mã để che lỗi xác định phạm vi.

### 4.5. Chuyển đổi tiền và làm tròn nhiều lần

Giả sử một giá trị trung gian là `1,0049`:

~~~text
Làm tròn trực tiếp hai chữ số:
  R2(1,0049) = 1,00

Làm tròn ba chữ số rồi hai chữ số:
  R2(R3(1,0049)) = R2(1,005) = 1,01
~~~

Đây là lỗi làm tròn hai lần ở các độ chia khác nhau. Nếu phép tính tiền tệ cần chia hoặc đổi ngoại tệ, phải quy định độ chính xác trung gian và điểm chốt cuối. Một số chữ số dự phòng tùy tiện chưa đủ để chứng minh kết quả đúng cho mọi đầu vào.

Với các tỷ lệ có thể biểu diễn chính xác bằng tử số và mẫu số, có thể dùng phép tính hữu tỉ hoặc số nguyên độ dài lớn để quyết định làm tròn tại ranh giới cần thiết. Nếu dùng phép chia thập phân có độ chính xác giới hạn, cần quy định và đánh giá sai số theo phạm vi dữ liệu hỗ trợ.

Không liên tục đổi qua lại giữa tiền chính thức và số hiển thị trong chuỗi xử lý. Kết quả đã làm tròn để hiển thị không nên trở thành đầu vào mới cho định giá.


## 5. Biến điểm làm tròn thành chính sách có thể kiểm chứng

### 5.1. Mô tả từng ranh giới bằng dữ liệu nghiệp vụ

Một chính sách minh họa cho tiền U, một nhóm thuế và các dòng đủ điều kiện giảm giá:

| Bước | Đầu vào | Điểm làm tròn | Kết quả chính thức |
|---|---|---|---|
| Tính giá dòng thô | Đơn giá chính xác × số lượng | Chưa làm tròn | Giá trị trung gian |
| Cộng giá dòng thô | Tất cả dòng trong nhóm tính giá | Chốt tổng gross theo `0,01 U` | `gross` |
| Tính giảm giá đơn | `gross × discountRate` | Làm tròn tại tổng giảm giá của đơn | `discount` |
| Tính cơ sở thuế | `gross - discount` | Không tạo thêm phép làm tròn không cần thiết | `net` |
| Tính thuế | `net × taxRate` | Làm tròn tại tổng thuế nhóm | `tax` |
| Tổng thanh toán | `net + tax` | Đã là tổng các số tiền chính thức | `payable` |
| Phân bổ | Các tổng đã chốt và trọng số đủ điều kiện | Phân bổ phần dư theo quy tắc xác định | Thành phần theo dòng |

Đây là một chính sách được chọn để minh họa. Không suy ra rằng thuế thực tế luôn phải tính theo tổng hóa đơn hoặc luôn sau giảm giá. Với nhiều nhóm thuế, nhiều người bán hoặc nhiều loại phí, mỗi nhóm có phạm vi và thứ tự riêng được xác định trước.

Bảng cũng cho thấy “chỉ làm tròn ở cuối mọi thứ” không phải lời giải tổng quát. Nếu giảm giá hoặc thuế đã là một nghĩa vụ tiền tệ được chốt riêng, nó cần điểm làm tròn riêng. Quan trọng là các điểm đó có tên, có phạm vi và có phiên bản.

### 5.2. Ví dụ hoàn chỉnh

Giả sử ba dòng A, B, C, mỗi dòng `0,05 U`, giảm giá cả đơn `10%`, thuế cả nhóm `10%`, cùng dùng `HALF_UP`:

~~~text
gross    = R(0,05 + 0,05 + 0,05) = 0,15
discount = R(0,15 × 10%)         = 0,02
net      = 0,15 - 0,02          = 0,13
tax      = R(0,13 × 10%)         = 0,01
payable  = 0,13 + 0,01          = 0,14 U
~~~

Sau khi chốt tổng, phân bổ giảm giá `0,02` theo trọng số giá dòng. Ba dòng có trọng số bằng nhau, phần dư được ưu tiên theo thứ tự ID dòng ổn định do server xác lập. Kết quả giảm giá là A `0,01`, B `0,01`, C `0,00`.

Thuế `0,01` được phân bổ theo cơ sở sau giảm giá. C có cơ sở lớn nhất nên nhận đơn vị thuế còn dư trong ví dụ:

| Dòng | Gross | Giảm giá phân bổ | Net | Thuế phân bổ | Phải trả |
|---|---:|---:|---:|---:|---:|
| A | 0,05 | 0,01 | 0,04 | 0,00 | 0,04 |
| B | 0,05 | 0,01 | 0,04 | 0,00 | 0,04 |
| C | 0,05 | 0,00 | 0,05 | 0,01 | 0,06 |
| Tổng | 0,15 | 0,02 | 0,13 | 0,01 | 0,14 |

Đây là phân bổ một tổng đã chốt, không phải tính thuế độc lập từng dòng rồi buộc tổng của chúng thay đổi kết quả `0,01`.

Khi cần hoàn hoặc đối soát từng dòng, những phần phân bổ này là dữ liệu nghiệp vụ quan trọng. Không bỏ chúng rồi tính lại từ tỷ lệ hiện hành.

### 5.3. Lưu bằng chứng về cách tính

Một quote hoặc snapshot giá có thể lưu:

~~~text
pricingSnapshotId
tenantId
orderId
currency
quantum
pricingPolicyVersion
lineInputs hoặc tham chiếu bất biến tới đầu vào
gross
discount
net
tax
fees
payable
allocatedComponentsByLine
allocationRuleVersion
createdAt
status
~~~

Cần truy được mức giá, tỷ lệ và điều kiện khuyến mại đã dùng. Một số nguyên tổng tiền không đủ giải thích vì sao hoàn một dòng được một khoản nhất định.

Không dùng một trường `roundingMode` duy nhất nếu các thành phần có quy tắc khác nhau. Cũng không để client truyền `roundingPoint=PER_LINE` rồi thay chính sách backend.

## 6. Java minh họa chuỗi tính tiền có điểm làm tròn rõ ràng

Đoạn mã sau minh họa chính sách ở mục trước: cùng tiền U, một nhóm thuế, không có phí và không có khoản tài trợ bên ngoài. Các phép nhân và cộng trung gian là phép tính thập phân chính xác; phép làm tròn chỉ xuất hiện ở những điểm đã đặt tên.

~~~java
import java.math.BigDecimal;
import java.math.RoundingMode;
import java.util.List;

record PriceLine(
        String lineId,
        BigDecimal unitPrice,
        long quantity) {}

record PricingPolicy(
        String version,
        int settlementScale,
        RoundingMode grossMode,
        RoundingMode discountMode,
        RoundingMode taxMode) {}

record QuoteTotals(
        BigDecimal gross,
        BigDecimal discount,
        BigDecimal net,
        BigDecimal tax,
        BigDecimal payable,
        String policyVersion) {}

QuoteTotals calculateOrder(
        List<PriceLine> lines,
        BigDecimal discountRate,
        BigDecimal taxRate,
        PricingPolicy policy) {

    if (discountRate.signum() < 0
            || discountRate.compareTo(BigDecimal.ONE) > 0
            || taxRate.signum() < 0) {
        throw new IllegalArgumentException("Invalid rate");
    }

    BigDecimal rawGross = BigDecimal.ZERO;

    for (PriceLine line : lines) {
        if (line.quantity() <= 0 || line.unitPrice().signum() < 0) {
            throw new IllegalArgumentException("Invalid line");
        }

        // Không làm tròn đơn giá hoặc dòng trước khi cộng.
        BigDecimal rawLine = line.unitPrice()
                .multiply(BigDecimal.valueOf(line.quantity()));

        rawGross = rawGross.add(rawLine);
    }

    // Ranh giới 1: chốt tổng giá hàng.
    BigDecimal gross = rawGross.setScale(
            policy.settlementScale(), policy.grossMode());

    // Ranh giới 2: chốt tổng giảm giá của đơn.
    BigDecimal discount = gross.multiply(discountRate).setScale(
            policy.settlementScale(), policy.discountMode());

    // Hai toán hạng đã ở đơn vị chính thức.
    BigDecimal net = gross.subtract(discount);

    // Ranh giới 3: chốt thuế của nhóm.
    BigDecimal tax = net.multiply(taxRate).setScale(
            policy.settlementScale(), policy.taxMode());

    BigDecimal payable = net.add(tax);

    return new QuoteTotals(
            gross, discount, net, tax, payable, policy.version());
}
~~~

Chính sách minh họa được backend chọn:

~~~java
PricingPolicy policy = new PricingPolicy(
        "U_ORDER_V1",
        2,
        RoundingMode.HALF_UP,
        RoundingMode.HALF_UP,
        RoundingMode.HALF_UP);
~~~

Đoạn mã chưa bao gồm kiểm tra dữ liệu rỗng, quyền đối tượng, phân bổ, lưu quote, hạn mức và transaction. Tầng đầu vào thực tế còn phải giới hạn số lượng dòng, số chữ số, scale đầu vào, số lượng hàng và phạm vi số tiền. `BigDecimal` không tự ngăn một request tạo phép tính quá lớn hoặc vượt độ chính xác cột dữ liệu.

Điểm cần quan sát là vị trí `setScale`. Chuyển nó vào vòng lặp, thêm vào `unitPrice` hoặc làm tròn `discountRate` trước khi nhân đều có thể thay đổi nghĩa của chính sách.

Nếu đầu vào được yêu cầu đã là số tiền chính thức theo scale hai, có thể dùng `setScale(2, RoundingMode.UNNECESSARY)` để kiểm tra việc chuyển đổi không cần làm tròn. `UNNECESSARY` không phải chế độ làm tròn giúp tiết kiệm tiền; nó báo lỗi nếu phép chuyển đổi sẽ làm mất giá trị.

Nếu quantum là `0,05`, ví dụ này chưa đủ. Cần chuyển sang đơn vị quantum, chọn bội theo chế độ quy định rồi chuyển lại bằng phương pháp tránh sai số trung gian. Không thay `settlementScale` bằng một giá trị khác rồi kỳ vọng có bước `0,05`.

Một bất biến kỹ thuật hữu ích của phép làm tròn trực tiếp về cùng quantum là `R(R(x)) = R(x)` với cùng chính sách. Tuy nhiên, nó không bảo vệ việc làm tròn qua hai quantum khác nhau hoặc việc đưa số đã chốt trở lại chuỗi tính giá mới.

## 7. Phân bổ phần dư mà không tạo hoặc làm mất tiền

### 7.1. Vì sao phải phân bổ riêng?

Giả sử giảm giá đã chốt là `0,02 U`, cần chia đều cho ba dòng:

~~~text
Phần lý tưởng mỗi dòng = 0,02 / 3 = 0,006666... U

Làm tròn độc lập từng phần bằng HALF_UP:
  0,01 + 0,01 + 0,01 = 0,03 U
~~~

Kết quả đã vượt tổng giảm giá một đơn vị nhỏ nhất. Làm tròn từng phần bằng `DOWN` lại cho tổng bằng không. Cần một quy tắc phân bổ có ràng buộc tổng.

### 7.2. Phương pháp phần dư lớn nhất

Với tổng không âm A được biểu diễn bằng **số nguyên đơn vị nhỏ nhất**, trọng số không âm `w_i` và `W = tổng w_i > 0`:

~~~text
Phần lý tưởng:       A × w_i / W
Phần nguyên ban đầu: b_i = floor(A × w_i / W)
Phần dư tử số:       r_i = (A × w_i) mod W
Số đơn vị còn lại:   L = A - tổng b_i
~~~

Sau đó:

1. Gán mỗi dòng phần nguyên `b_i`.
2. Sắp các dòng theo `r_i` giảm dần.
3. Nếu phần dư bằng nhau, dùng khóa dòng ổn định do server xác định.
4. Cộng một đơn vị nhỏ nhất cho L dòng đầu đủ điều kiện.

Các phép tính tử số nên dùng kiểu số nguyên có phạm vi đủ lớn, chẳng hạn `BigInteger`, hoặc cơ chế kiểm tra tràn phù hợp. Trọng số thập phân hữu hạn có thể được đưa về cùng đơn vị nguyên chính xác trước khi phân bổ, với giới hạn dữ liệu đã kiểm tra.

Không cần cắt tỷ lệ `1/3` thành một số thập phân có vài chữ số rồi so sánh phần dư xấp xỉ. So sánh các phần dư tử số khi cùng mẫu W giúp tránh sai khác do độ chính xác tùy ý.

Ví dụ giảm giá `0,02 U` tương đương A = 2 đơn vị nhỏ nhất, trọng số các dòng là `5, 5, 5`:

~~~text
W = 15
A × w_i = 10 cho mỗi dòng
b_i = 0 cho mỗi dòng
r_i = 10 cho mỗi dòng
L = 2

Sau khi phá hòa bằng ID:
  A nhận 1 đơn vị = 0,01 U
  B nhận 1 đơn vị = 0,01 U
  C nhận 0 đơn vị = 0,00 U
~~~

Với thuế `0,01 U` và trọng số net `4, 4, 5`, phần dư lớn nhất thuộc về C, nên C nhận `0,01 U`.

### 7.3. Ràng buộc và tính ổn định

Chỉ phân bổ cho những dòng đủ điều kiện. Dòng không chịu thuế hoặc không được giảm giá không được nhận phần dư của thành phần đó.

Nếu có trần theo dòng, thuật toán phải xử lý trần trong lúc phân bổ hoặc chia lại trên tập còn đủ điều kiện. Không phân bổ xong rồi cắt các phần vượt trần mà bỏ mất phần dư, vì tổng sẽ không còn đúng.

Tránh phá hòa bằng vị trí trong request hoặc một thứ tự do client tùy chọn. Nếu người gọi đảo dòng để nhận thêm đơn vị giảm giá trên phần sẽ được giữ lại và hoàn phần khác, quy tắc đó có thể trở thành một công cụ chọn lợi ích.

Một khóa ổn định cũng không tự ngăn người gọi tạo dòng mới để thao túng kết quả. Phạm vi dòng và nhóm được phân bổ vẫn phải dựa trên danh tính nghiệp vụ có thẩm quyền. Nếu quyền chọn dòng ảnh hưởng lớn đến giá hoặc hoàn tiền, sản phẩm cần đánh giá chính sách đó rõ ràng.

Lưu kết quả phân bổ cùng snapshot. Khi retry, không phân bổ lại dựa trên thứ tự truy vấn khác. Khi hoàn hoặc đảo một phần, tham chiếu phân bổ gốc hoặc quy tắc cộng dồn đã xác định.

Với số tiền âm, không áp dụng nguyên xi phép floor của công thức không âm. Nếu nghiệp vụ là đảo một khoản đã hạch toán, ưu tiên đảo chính số tiền đã lưu. Nếu phải phân bổ một khoản âm mới, cần quy tắc dấu và phá hòa được định nghĩa riêng, có thể phân bổ trị tuyệt đối rồi phục hồi dấu khi chính sách yêu cầu đối xứng.

## 8. Chốt giá, phê duyệt và ghi tiền phải dùng cùng kết quả

Một luồng tham khảo:

~~~mermaid
sequenceDiagram
    participant C as Client
    participant P as Dịch vụ định giá
    participant D as Cơ sở dữ liệu
    C->>P: Ý định mua và các dòng hợp lệ
    P->>P: Xác định phạm vi, chính sách, điểm làm tròn
    P->>D: Lưu snapshot giá và phân bổ bất biến
    P-->>C: Quote ID và tổng tiền đã chốt
    C->>P: Xác nhận quote + khóa idempotency
    P->>D: Bắt đầu transaction và khóa dữ liệu liên quan
    P->>P: Kiểm tra quyền, trạng thái, phê duyệt, hạn sử dụng
    P->>D: Ghi tiền theo snapshot, tiêu thụ lệnh và lưu ledger
    P->>D: Commit toàn bộ
    P-->>C: Kết quả đã commit
~~~

Client có thể gửi số tiền kỳ vọng để xác nhận, nhưng backend phải đối chiếu với số đã chốt. Không ghi nợ bằng `clientTotal` trong khi ledger, hóa đơn hoặc gateway dùng một tổng khác.

Nếu giá, số lượng hoặc điều kiện khuyến mại thay đổi trước khi chấp nhận, tạo phiên bản hoặc quote mới theo quy trình sản phẩm. Phê duyệt gắn với số tiền và đối tượng cũ không được tự áp dụng cho nội dung mới.

Trong transaction ghi tiền, số dư, trạng thái lệnh, hạn mức và ledger cần cùng tuân theo invariant tương ứng. Không dùng trạng thái “đã tính xong” làm bằng chứng rằng một lần thu tiền chưa từng xảy ra.

Idempotency bảo đảm cùng lệnh không tạo thêm lần thu hoặc hoàn. Fingerprint phải bao gồm quote hoặc snapshot và những trường ảnh hưởng đến lệnh. Cùng khóa nhưng khác quote phải được coi là xung đột theo chính sách.

Retry sau khi lệnh đã commit trả lại kết quả cũ, không tính lại số tiền theo danh mục giá hoặc cách làm tròn mới. Nếu lệnh chưa commit, retry phải tiếp tục tuân theo quyền, trạng thái và hiệu lực hiện tại của snapshot.

Ràng buộc nghiệp vụ vẫn cần tồn tại ngoài khóa request, chẳng hạn một lần thu toàn phần chỉ gắn với một payment của đơn. Dùng khóa idempotency mới không được mở thêm một ranh giới làm tròn hoặc một lần chi trả ngoài chính sách.


## 9. Hoàn tiền từng phần: không tạo một điểm làm tròn mới cho mỗi request

### 9.1. Lỗi tính lại độc lập

Giả sử một nhóm gồm ba đơn vị hàng giống nhau có tổng tiền được phép hoàn đã chốt là `0,05 U`. Một cách tính sai là:

~~~text
Mỗi lần hoàn một đơn vị:
  R(0,05 / 3) = 0,02 U

Ba lần hoàn độc lập:
  0,02 + 0,02 + 0,02 = 0,06 U
~~~

Không có phép chia nào bị tính sai theo chế độ đã chọn. Lỗi nằm ở việc mỗi request tự tạo một điểm làm tròn độc lập, không bị ràng buộc bởi tổng quyền hoàn của giao dịch gốc.

Chỉ thêm điều kiện “lần hoàn không vượt số tiền thanh toán” cũng không đủ. Cả ba lần hoàn `0,02` đều nhỏ hơn `0,05`. Cần kiểm tra tổng đã hoàn và phần đang được dành cho các lệnh hoàn chưa rõ kết quả.

### 9.2. Hai cách giữ tổng đúng

**Cách thứ nhất: dùng phân bổ gốc.** Nếu giao dịch đã lưu quyền hoàn theo từng dòng hoặc từng đơn vị, hoàn theo đúng phần đó, có quy tắc cho phần dư và các thành phần không hoàn được. Không tính lại từ đơn giá hiện tại.

**Cách thứ hai: dùng quyền hoàn cộng dồn.** Với N đơn vị giống nhau, tổng có thể hoàn P và k là tổng số đơn vị đã được chấp nhận trả:

~~~text
E(k) = R(P × k / N)
refundDelta = E(k_mới) - E(k_cũ)
~~~

`E(k)` là quyền hoàn lũy kế, không phải số tiền của riêng request. Với `P = 0,05 U`, `N = 3`, làm tròn `HALF_UP`:

| Tổng số đơn vị đã trả k | Quyền hoàn lũy kế E(k) | Phần hoàn thêm |
|---|---:|---:|
| 0 | 0,00 | 0,00 |
| 1 | 0,02 | 0,02 |
| 2 | 0,03 | 0,01 |
| 3 | 0,05 | 0,02 |

Tổng phần hoàn thêm là `0,05 U`. Nhờ hiệu hai giá trị lũy kế, các phần cộng lại khớp quyền hoàn cuối cùng.

Phép tính `P × k / N` nên được xử lý như một tỷ lệ chính xác tới điểm làm tròn cần thiết, không cắt `P / N` trước rồi nhân lại.

Công thức này chỉ mô tả mô hình các đơn vị có cùng quyền lợi và cùng chính sách. Với hàng khác giá, coupon riêng, thuế khác nhóm hoặc phí không được hoàn, phải dựa vào trọng số, thành phần và phân bổ gốc tương ứng. Không lấy tổng tiền của toàn đơn chia đều cho mọi món hàng.

### 9.3. Cập nhật quyền hoàn nguyên tử

Quy trình hoàn cần bảo vệ đồng thời:

~~~text
Danh tính và quyền trên giao dịch gốc.
Đơn vị hàng hoặc số lượng đã trả, chưa trả và đang xử lý.
Số tiền được phép hoàn theo từng thành phần.
Số tiền đã hoàn thành công.
Số tiền đang dành cho lệnh hoàn chưa kết thúc.
Danh tính lệnh để chống thực hiện trùng.
~~~

Hai request cùng đọc `k_cũ = 0` rồi cùng cấp quyền hoàn đầu tiên có thể phá vỡ tổng. Cần khóa hoặc cập nhật có điều kiện trên dữ liệu hoàn và quyền lợi liên quan trong cùng transaction.

Request retry không được tăng k thêm lần nữa. Nếu đơn vị hàng có danh tính riêng, cần ràng buộc để cùng một đơn vị không được trả lại hoặc nhận tiền nhiều lần.

Khi gọi hệ thống thanh toán bên ngoài, timeout không chứng minh hoàn tiền đã thất bại. Phần quyền hoàn đang dành cho lệnh chưa rõ kết quả không được tự giải phóng để một request mới nhận tiền lần nữa. Cần đối soát hoặc tiếp tục theo cùng định danh lệnh.

### 9.4. Đảo giao dịch không phải tính lại một số âm

Một khoản đảo đúng thường là đảo chính số tiền chính thức đã ghi nhận, trong phạm vi chính sách cho phép. Không lấy dữ liệu thô ban đầu, đổi dấu rồi làm tròn lại để suy ra số tiền đảo.

Ví dụ với `CEILING` tới hai chữ số:

~~~text
CEILING( 0,005) = 0,01
CEILING(-0,005) = 0,00
~~~

Do đó, tính lại từ số âm không đảo được khoản `0,01` đã thu. `CEILING` làm tròn về phía dương vô cùng, không có nghĩa là luôn tăng trị tuyệt đối. Tương tự, `FLOOR` và `DOWN` có hành vi khác nhau đối với số âm.

Nếu nghiệp vụ là đảo toàn bộ một bút toán `+0,01 U`, bút toán đối ứng cần phản ánh `-0,01 U` theo mô hình sổ của hệ thống, thay vì tính lại `CEILING(-0,005)`. Với hoàn một phần, áp dụng quyền hoàn và phân bổ gốc đã được xác định.

## 10. Ledger, đối soát và khoản chênh lệch làm tròn

### 10.1. Sổ chính thức phải dùng số tiền đã chốt

Nếu sổ ghi theo đơn vị `0,01 U`, các bút toán chính thức phải biểu diễn được bằng đơn vị đó. Giá trị trung gian `0,005 U` có thể được lưu làm bằng chứng tính toán, nhưng không được tùy ý ghi vào cột số dư chỉ hỗ trợ phần trăm U.

Trong mô hình đơn giản không có tài trợ bên ngoài, cùng một loại tiền và các khoản tách biệt:

~~~text
Tổng ghi nợ người mua
  = khoản được hưởng của người bán
  + nghĩa vụ thuế
  + phí được hưởng
  + khoản điều chỉnh đã được chính sách định nghĩa
~~~

Ví dụ ở mục 5 không có phí hoặc điều chỉnh riêng:

~~~text
0,14 U = 0,13 U + 0,01 U
~~~

Khi có nhiều bên, phí, thuế, trợ giá hoặc tài khoản trung gian, phương trình cần thêm đúng các thành phần đó. Không cộng trực tiếp số tiền khác loại tiền để tuyên bố ledger đã cân bằng.

### 10.2. Chênh lệch tính toán và bút toán điều chỉnh là hai thứ khác nhau

Có thể lưu:

~~~text
rawAmount
roundedAmount
roundingDelta = roundedAmount - rawAmount
roundingPoint
roundingMode
quantum
policyVersion
businessReference
~~~

`roundingDelta` có thể nhỏ hơn quantum, nên phù hợp với dữ liệu giải thích tính toán có độ chính xác cao. Nó không mặc nhiên là một số tiền có thể hạch toán độc lập.

Nếu sản phẩm có khoản điều chỉnh làm tròn chính thức, khoản đó cần biểu diễn bằng đơn vị hạch toán, có nguồn gốc, quy tắc dấu và tài khoản đối ứng phù hợp.

Ví dụ, thuế chốt theo hóa đơn là `0,02` nhưng tổng các giá trị thuế được làm tròn độc lập theo dòng là `0,03`. Không được thu `0,03` ở gateway rồi ghi `0,02` trong ledger và coi phần `0,01` là không đáng kể. Cần thống nhất điểm làm tròn, phân bổ đúng hoặc áp dụng khoản điều chỉnh đã được chính sách cho phép.

Một tài khoản “rounding” không phải nơi đẩy mọi sai lệch do lỗi quyền, thu trùng hoặc dùng sai giá. Chênh lệch bất thường phải được điều tra, không hợp thức hóa bằng bút toán tự động.

### 10.3. Ranh giới với cơ sở dữ liệu và gateway

Cột decimal có scale cố định hoặc thư viện chuyển đổi sang đơn vị nhỏ nhất có thể vô tình trở thành một điểm làm tròn mới. Tùy hệ thống, giá trị vượt scale có thể bị từ chối hoặc bị chuyển đổi. Backend không nên dựa vào hành vi ngầm đó để xác định số tiền chính thức.

Trước khi lưu hoặc gửi ra ngoài:

- Chuyển từ số tiền đã chốt sang biểu diễn giao tiếp bằng phép chuyển đổi không làm mất giá trị.
- Kiểm tra phạm vi số nguyên hoặc độ chính xác của cột đích.
- Giữ đúng loại tiền và đơn vị.
- Đối chiếu số tiền nhà cung cấp thực sự chấp nhận với lệnh gốc.

Với ví dụ scale hai, `amount.movePointRight(2).longValueExact()` có thể dùng để chuyển một số tiền đã hợp lệ sang số nguyên đơn vị nhỏ nhất và phát hiện phần lẻ hoặc tràn. Không thay bằng `longValue()` để âm thầm cắt phần lẻ.

Cách chuyển này gắn với mô hình scale hai đang xét; không hard-code số hai cho mọi loại tiền hoặc mọi cơ chế thanh toán.

## 11. Kiểm thử theo cách người dùng có thể lạm dụng

Các kiểm thử cần kiểm tra số tiền bền vững, phân bổ, ledger, quyền hoàn, trạng thái lệnh và kết quả idempotency. Một response thành công hoặc một phép tính đúng trong bộ nhớ chưa chứng minh được invariant.

| Tình huống | Kết quả cần chứng minh |
|---|---|
| Ba dòng `0,05`, thuế `10%` theo tổng nhóm, không giảm giá | Thuế `0,02`, không vô tình thành `0,03` |
| Đơn giá cho phép `1,005`, số lượng ba, chốt sau tổng | Gross `3,02`, không chốt đơn giá sớm thành `3,03` |
| Ví dụ giảm giá và thuế ở mục 5 | Gross `0,15`, giảm `0,02`, net `0,13`, thuế `0,01`, phải trả `0,14` |
| Tách một dòng thành nhiều dòng tương đương trong cùng phạm vi kinh tế | Không tạo thêm lợi ích ngoài chính sách nhóm dòng của server |
| Hai dòng có mức thuế hoặc điều kiện giá khác nhau | Không bị gộp sai chỉ để giảm sai lệch làm tròn |
| Đảo thứ tự dòng trong request | Tổng và phân bổ không đổi nếu danh tính dòng kinh tế không đổi |
| Chia một đơn thành nhiều request thanh toán | Không bỏ phí vốn được định nghĩa ở cấp đơn |
| Nhiều quote cho cùng ý định | Mỗi quote tuân theo chính sách; xác nhận không sửa được tổng bằng dữ liệu client |
| Client gửi `roundingMode`, `scale` hoặc `clientTotal` có lợi | Không thay đổi quyết định tiền tệ của backend |
| Giá trị `1,0049` tại ranh giới hai chữ số | Không bị làm tròn trung gian thành `1,01` nếu chính sách yêu cầu làm tròn trực tiếp |
| Giá trị nằm đúng nửa quantum | Kết quả đúng chế độ tại từng thành phần, không phụ thuộc mặc định thư viện |
| Tổng phân bổ `0,02` cho ba trọng số bằng nhau | Các phần cộng lại đúng `0,02`; phá hòa ổn định |
| Dòng không đủ điều kiện khuyến mại | Không nhận phần dư giảm giá |
| Phân bổ có trần theo dòng | Không vượt trần, không đánh mất phần dư và vẫn bảo toàn tổng hợp lệ |
| Hoàn ba đơn vị có tổng quyền hoàn `0,05` | Tổng hoàn đúng `0,05` khi hoàn đủ, không thành `0,06` |
| Hai yêu cầu hoàn cùng chạy trên một phần quyền lợi | Chỉ phần hợp lệ được chấp nhận; quyền hoàn được cập nhật nguyên tử |
| Retry lệnh hoàn hoặc thu đã commit | Trả kết quả cũ; không tính hoặc ghi tiền thêm |
| Dùng khóa idempotency mới để hoàn lại cùng đơn vị hàng | Không tạo thêm quyền hoàn |
| Cùng khóa nhưng đổi snapshot hoặc số tiền | Báo xung đột; không thay lệnh cũ |
| Chính sách làm tròn thay đổi sau thanh toán | Hoàn, đảo và đối soát vẫn bám quyền lợi gốc theo chính sách đã lưu |
| Đảo một khoản tính bằng `CEILING` | Đảo đúng số đã hạch toán, không suy từ làm tròn lại số thô âm |
| Cột dữ liệu hoặc adapter không chứa được số tiền | Bị từ chối có kiểm soát; không cắt số hoặc cập nhật một phần |
| Request quá nhiều chữ số, scale hoặc số lượng quá lớn | Bị chặn theo giới hạn, không gây phép tính ngoài phạm vi hỗ trợ |
| Lỗi ledger sau khi đã ghi câu lệnh cập nhật số dư | Transaction rollback toàn bộ thay đổi liên quan |
| Provider timeout với một lần hoàn chưa rõ kết quả | Không giải phóng quyền hoàn để chi thêm trước khi có căn cứ |
| Quantum thanh toán là `0,05` | Dùng đúng quy tắc quantum, không coi scale hai là đủ |

Với kiểm thử đồng thời, điều khiển thời điểm các transaction cùng đọc hoặc cùng cập nhật bằng barrier hoặc cơ chế tương đương trong môi trường kiểm thử. Hai request chạy nối tiếp không kiểm chứng được lỗi mất cập nhật.

Ngoài các ví dụ, có thể kiểm tra những tính chất sau trên dữ liệu hợp lệ trong phạm vi mô hình:

~~~text
Cùng đầu vào và phiên bản chính sách cho cùng kết quả tiền chính thức.
Mỗi khoản đã chốt là bội số của quantum tương ứng.
Tổng phần phân bổ đúng bằng tổng cần phân bổ.
Đổi thứ tự danh sách không đổi kết quả nếu danh tính nghiệp vụ giữ nguyên.
Tổng hoàn không vượt quyền hoàn gốc.
Khi hoàn đủ phần có thể hoàn, tổng hoàn khớp quyền hoàn cuối cùng.
Retry không tạo thêm tác động tiền tệ.
Mọi biến động tiền truy được snapshot và phiên bản chính sách.
~~~

Tính bất biến khi tách hoặc gộp chỉ kiểm tra trong phạm vi chính sách yêu cầu. Không viết một tính chất bắt buộc phí theo từng thanh toán phải giống phí theo cả đơn nếu đó vốn là hai nghiệp vụ khác nhau.

Giá trị sát nửa quantum, bằng không, sát giới hạn số và phép chia không hữu hạn là các đầu vào quan trọng. Giá trị âm cần có bộ quy tắc riêng cho điều chỉnh hoặc đảo; không mở rộng bộ kiểm thử giao dịch dương bằng cách đổi dấu một cách máy móc.

## 12. Đọc một luồng tiền theo các ranh giới làm tròn

Khi rà soát luồng nghiệp vụ, lần theo:

~~~text
Đầu vào và danh tính dòng kinh tế
    → phạm vi áp dụng của giá, giảm giá, phí và thuế
    → phép tính trung gian chính xác
    → các điểm chốt tiền có tên và có phiên bản
    → phân bổ phần dư bảo toàn tổng
    → quote và phê duyệt đúng nội dung
    → ghi tiền nguyên tử và chống trùng
    → hoàn, đảo và đối soát theo dữ liệu gốc
~~~

Ở mỗi bước, xác định phép chuyển đổi nào có thể làm mất phần lẻ. Điều đó bao gồm phép chia, helper định dạng, serializer, cột cơ sở dữ liệu và adapter thanh toán, không chỉ lời gọi `setScale` dễ nhìn thấy.

Một thiết kế bảo vệ tốt rounding point giải thích được **vì sao làm tròn tại bước đó, trên phạm vi nào, theo chính sách nào và phần dư đi đâu**. Khi những câu trả lời đã được lưu cùng giao dịch, hệ thống có cơ sở để ngăn chia nhỏ yêu cầu nhằm nhận lợi ích ngoài quy tắc, hoàn tiền quá mức hoặc làm lệch số dư giữa các thành phần.
