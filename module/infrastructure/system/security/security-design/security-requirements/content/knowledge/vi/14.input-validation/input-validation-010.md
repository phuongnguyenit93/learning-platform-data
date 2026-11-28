# Business input validation

## 1. Đúng kiểu dữ liệu chưa có nghĩa là thao tác hợp lệ

Một request hoàn tiền có thể là JSON hợp lệ, chứa đúng kiểu string và number, không vượt giới hạn kích thước, nhưng vẫn yêu cầu hoàn nhiều hơn số tiền còn được phép hoàn. Một request đặt hàng có thể gửi đúng mã sản phẩm nhưng tự chọn mức giá thấp hơn giá server đang áp dụng. Đây là những đầu vào đúng về hình thức nhưng có thể làm sai quy tắc của hệ thống.

Business input validation là việc kiểm tra dữ liệu đầu vào theo các điều kiện của miền nghiệp vụ: quan hệ giữa các field, trạng thái tài nguyên, dữ liệu có thẩm quyền, thời gian, hạn mức và các bất biến phải được giữ trong quá trình thay đổi trạng thái.

Trong thiết kế yêu cầu bảo mật, kiểm tra nghiệp vụ giúp ngăn việc dùng chức năng hợp lệ theo một cách tạo ra kết quả không được phép. Kẻ tấn công không nhất thiết phải gửi SQL hoặc một chuỗi kỳ lạ; họ có thể gửi một số tiền bình thường, lặp lại request hoặc khai thác khoảng thời gian giữa kiểm tra và cập nhật.

Một yêu cầu tốt phải xác định được:

- Quy tắc nào cần giữ và rủi ro nếu quy tắc bị phá vỡ.
- Những dữ liệu nào được dùng để ra quyết định, lấy từ nguồn nào.
- Thời điểm kiểm tra và thời điểm tạo tác động nghiệp vụ.
- Cách xử lý thay đổi đồng thời, request lặp và trạng thái chưa xác định.
- Phản hồi lỗi, bằng chứng kiểm thử và chủ sở hữu quy tắc.

Ví dụ, “validate số tiền hoàn” còn quá mơ hồ. Yêu cầu rõ hơn là: “Trước khi giữ chỗ một khoản hoàn tiền, hệ thống phải xác nhận số tiền lớn hơn 0, biểu diễn chính xác theo đơn vị tiền tệ của giao dịch và không vượt số tiền có thể hoàn còn lại tại thời điểm cập nhật nguyên tử”.

## 2. Đặt business validation đúng vị trí trong tập kiểm soát

| Kiểm soát | Câu hỏi cần trả lời | Ví dụ |
|---|---|---|
| Kiểm tra cú pháp và kiểu | Dữ liệu có đọc được và có đúng cấu trúc không? | `amount` được parse thành kiểu tiền đã thống nhất |
| Kiểm tra định dạng | Giá trị có đúng ngữ pháp cần thiết không? | Mã đơn hàng tuân theo định dạng của API |
| Kiểm tra nghiệp vụ cục bộ | Các giá trị trong một command có hợp lệ khi xét cùng nhau không? | Số tiền dương; lý do phù hợp với loại thao tác |
| Kiểm tra nghiệp vụ có trạng thái | Command có hợp lệ với dữ liệu hiện tại không? | Số tiền không vượt phần còn có thể hoàn |
| Phân quyền | Chủ thể có quyền thực hiện thao tác với tài nguyên này không? | Nhân viên được quyền yêu cầu hoàn tiền cho đơn hàng trong đúng tenant |
| Bảo vệ sink | Dữ liệu được dùng an toàn ở nơi tiêu thụ chưa? | Query được tham số hóa, HTML được encode theo ngữ cảnh |

Các điều kiện liên quan nhưng không thay thế nhau. Một người có quyền hoàn tiền vẫn không được hoàn quá số tiền cho phép. Một command có số tiền đúng vẫn phải bị từ chối nếu người gọi không có quyền với đơn hàng đó.

Không nên gọi phân quyền là một phép kiểm tra định dạng, hoặc cho rằng “đã validate input” thì mọi field đều có thể được tin cậy. Thiết kế cần liệt kê rõ các cổng kiểm soát và bảo đảm mọi đường thực thi có tác động đều đi qua các cổng cần thiết.

Kiểm tra phía client giúp phản hồi sớm nhưng không phải ranh giới bảo mật. API, consumer của message broker, file import và công cụ quản trị cần tuân theo các bất biến chung của hệ thống, dù cách nhập dữ liệu khác nhau.

## 3. Bắt đầu từ bất biến thay vì danh sách annotation

Bất biến là điều kiện phải luôn được duy trì trong phạm vi mà thiết kế cam kết. Chẳng hạn:

- Tổng số tiền hoàn thành công và số tiền đang được giữ chỗ để hoàn không vượt số tiền đã thu được phép hoàn.
- Số lượng hàng đã phân bổ không vượt lượng hàng có thể phân bổ theo chính sách kho.
- Một mã khuyến mại không được sử dụng vượt số lần cho phép đối với cùng chủ thể và khoảng thời gian đã định nghĩa.
- Một chuyển trạng thái chỉ xảy ra từ các trạng thái nguồn được phép.
- Một giao dịch không tự thay đổi tenant, chủ sở hữu hoặc mức quyền bằng field do người gọi tự khai báo.

Annotation như kiểm tra số dương có thể thực thi một phần yêu cầu. Nó không tự kiểm tra lịch sử hoàn tiền, trạng thái thanh toán hoặc hai request chạy đồng thời.

Có thể xây dựng quy tắc theo bảng sau:

| Thành phần đặc tả | Ví dụ với hoàn tiền |
|---|---|
| Rủi ro | Hoàn vượt mức do sửa số tiền hoặc gửi nhiều request đồng thời |
| Bất biến | Phần đã hoàn và đang giữ chỗ không vượt ngân sách hoàn của giao dịch |
| Dữ liệu đầu vào được phép | Mã đơn, số tiền yêu cầu, loại tiền, lý do, khóa chống lặp |
| Dữ liệu có thẩm quyền | Giao dịch đã thu, ngân sách hoàn hiện tại, các khoản giữ chỗ, chính sách của tenant |
| Điểm thực thi | Bước tạo giữ chỗ hoàn tiền trong cơ chế cập nhật nguyên tử |
| Phản ứng khi vi phạm | Từ chối command; không tạo giữ chỗ hoặc yêu cầu tới nhà cung cấp |
| Bằng chứng | Kiểm tra biên và kịch bản cạnh tranh có cùng ngân sách |

Việc chỉ viết quy tắc cho trường hợp bình thường sẽ bỏ sót những trạng thái quan trọng: giao dịch chưa hoàn tất, thao tác trước đang chờ, dữ liệu đã thay đổi hoặc nhà cung cấp chưa cho biết kết quả cuối cùng.

## 4. Xác định dữ liệu nào do client khai báo và dữ liệu nào do server quyết định

Giả sử API nhận command sau. Các giá trị chỉ là dữ liệu minh họa:

```json
{
  "orderId": "ord-example-031",
  "amount": "125.00",
  "currency": "USD",
  "reason": "CUSTOMER_REQUEST"
}
```

Ở endpoint này, số tiền được truyền dưới dạng chuỗi thập phân theo hợp đồng để giữ biểu diễn chính xác. Lớp cú pháp và kiểu chịu trách nhiệm parse nó thành giá trị tiền hợp lệ trước khi kiểm tra nghiệp vụ. Một API khác có thể chọn biểu diễn khác nếu bảo toàn được ý nghĩa và độ chính xác.

Không vì command có `orderId` mà tin mọi thuộc tính đi kèm do client gửi. Cần phân loại:

| Dữ liệu | Nguồn dùng để quyết định |
|---|---|
| Số tiền muốn hoàn | Đề nghị của client; phải được kiểm tra |
| Tiền đã thu và phần còn được hoàn | Trạng thái có thẩm quyền do hệ thống quản lý |
| Loại tiền của giao dịch | Bản ghi giao dịch; so khớp với đề nghị nếu API nhận field này |
| Tenant của thao tác | Ngữ cảnh xác thực và quy tắc truy cập, không tự tin field trong body |
| Quyền hoàn tiền và yêu cầu phê duyệt | Chính sách hiện hành và danh tính được xác thực |
| Người sở hữu giao dịch | Dữ liệu server dùng trong kiểm tra quyền |
| Mức chiết khấu hoặc tỷ giá được áp dụng | Nguồn được phê duyệt và thời điểm hiệu lực theo chính sách |
| Thời điểm xử lý | Đồng hồ hoặc nguồn thời gian được thiết kế, không tự tin timestamp client |

Một command nên thể hiện **ý định được phép yêu cầu**, không phải toàn bộ đối tượng database. Nếu client gửi thêm `alreadyRefunded`, `approved`, `ownerId` hoặc `role`, hệ thống không được dùng chúng để thay thế dữ liệu có thẩm quyền.

Nên dùng mô hình command dành riêng cho từng thao tác và ánh xạ field được phép. Bind trực tiếp request vào entity có các thuộc tính quản trị làm tăng nguy cơ cập nhật quá quyền, ngay cả khi từng field đều có kiểu đúng.

## 5. Kiểm tra quan hệ giữa các field

Một field có thể hợp lệ riêng lẻ nhưng không hợp lệ khi kết hợp với field khác:

- `startAt` và `endAt` đều là thời gian hợp lệ nhưng `endAt` phải sau `startAt`.
- Nếu chọn giao hàng thì phải có địa chỉ; nếu chọn nhận tại cửa hàng thì phải có cửa hàng hợp lệ theo hợp đồng.
- Một khoản tiền phải có loại tiền tương thích với giao dịch, không chỉ thuộc danh sách mã được hỗ trợ.
- Nếu thao tác được phân loại là hoàn toàn bộ, số tiền phải khớp phần được phép hoàn toàn bộ theo định nghĩa nghiệp vụ.
- Một mã giảm giá không được dùng đồng thời với ưu đãi khác nếu chính sách không cho phép kết hợp.

Không nên giải quyết mâu thuẫn bằng cách âm thầm bỏ qua một field hoặc tự chọn một nhánh mặc định. Ví dụ, gửi cả hai phương thức thanh toán nhưng server tự lấy phương thức đầu có thể tạo hành vi khác nhau giữa các thành phần.

Với API cập nhật từng phần, phải phân biệt field không có mặt, field gửi `null` và field có giá trị. Một quy tắc liên field cần áp dụng lên trạng thái sau cập nhật, không chỉ lên các field vừa được gửi. Nếu client chỉ sửa `startAt`, vẫn phải kiểm tra nó với `endAt` đang lưu.

Yêu cầu nên nêu rõ quy tắc được áp dụng trước hay sau những bước chuẩn hóa đã phê duyệt. Không tự sửa giá trị gây thay đổi ý định nghiệp vụ, chẳng hạn tự làm tròn tiền hoặc đổi ngày kết thúc để request có vẻ hợp lệ.

## 6. Tiền, hạn mức và thời gian cần hợp đồng chính xác

### 6.1. Tiền không chỉ là một số dương

Với số tiền hoàn, cần xác định:

- Đơn vị và loại tiền được dùng trong phép so sánh.
- Độ chính xác cho phép và quy tắc về phần lẻ.
- Cách tính phần đã hoàn, phần giữ chỗ và các khoản điều chỉnh.
- Các điều kiện cần phê duyệt trước khi thực hiện.
- Chính sách khi giá trị không thể biểu diễn chính xác theo đơn vị được hỗ trợ.

Không so sánh `125 USD` với `125 JPY` chỉ vì phần số bằng nhau. Không mặc định mọi loại tiền có hai chữ số thập phân. Nếu nghiệp vụ cần chuyển đổi tiền tệ, phải có quy tắc tỷ giá, thời điểm và làm tròn riêng; không giấu việc chuyển đổi trong một hàm “validate”.

Khi hợp đồng không cho phép làm tròn, giá trị có phần lẻ không được hỗ trợ phải bị từ chối. Không cắt phần lẻ để rồi kiểm tra một giá trị khác với giá trị client đã yêu cầu.

### 6.2. Hạn mức là điều kiện trên trạng thái tích lũy

Giới hạn mỗi request khác với giới hạn cộng dồn theo tài khoản, tenant hoặc khoảng thời gian. Một request dưới hạn mức vẫn có thể làm tổng vượt hạn mức.

Đặc tả cần xác định đơn vị đếm, chủ thể, cửa sổ thời gian và các trạng thái được tính vào tổng. Với hoàn tiền, nếu chỉ tính các khoản đã thành công mà bỏ qua các khoản đang giữ chỗ, nhiều request đồng thời có thể cùng vượt mức.

Rate limit giúp hạn chế tần suất nhưng không thay thế bất biến tài chính. Hai request hợp lệ về tần suất vẫn có thể vi phạm tổng tiền còn lại.

### 6.3. Điều kiện theo thời gian cần điểm đánh giá

“Được hoàn trong 30 ngày” chưa đủ rõ. Đội nghiệp vụ cần chọn mốc bắt đầu, cách hiểu ngày theo lịch hay khoảng thời gian, múi giờ nếu có và điều kiện tại ranh giới.

Quy tắc cũng phải xác định thời điểm quyết định: lúc người dùng mở form, lúc API tiếp nhận, lúc tạo giữ chỗ hay lúc thực hiện ở nhà cung cấp. Một phiên phê duyệt hoặc báo giá có thể hết hiệu lực giữa các bước; cần chính sách xử lý thay vì giữ nguyên kết quả kiểm tra cũ vô thời hạn.

Các con số thời hạn và ngưỡng tiền trong hệ thống thật phải được chọn theo rủi ro, hợp đồng và chính sách liên quan. Ví dụ trong bài không đặt ra một ngưỡng chung cho mọi sản phẩm.

## 7. Trạng thái có thể thay đổi sau khi đã kiểm tra

Một cách triển khai dễ sai là:

```text
1. Đọc số tiền còn có thể hoàn: 50.
2. Xác nhận request muốn hoàn 40 là hợp lệ.
3. Gửi lệnh hoàn 40.
4. Cập nhật số đã hoàn.
```

Nếu hai request cùng đọc `50`, mỗi request đều vượt qua bước 2 nhưng tổng yêu cầu là `80`. Validator không sai khi xét từng ảnh chụp; điều sai là thiết kế không giữ bất biến tại thời điểm thay đổi trạng thái.

Yêu cầu phải gắn kiểm tra với cập nhật bằng một cơ chế có thể chứng minh được. Một số lựa chọn là:

- Transaction với khóa trên bản ghi ngân sách hoặc phạm vi tài nguyên tương ứng.
- Cập nhật có điều kiện, chỉ thành công nếu phần còn lại đủ cho khoản mới.
- Optimistic concurrency với phiên bản và xử lý xung đột đúng cách.
- Một cơ chế tuần tự hóa theo tài nguyên có độ bền và ranh giới thực thi phù hợp.

Không phải chỉ thêm annotation transaction là tự động ngăn mọi cạnh tranh. Hiệu quả phụ thuộc isolation, câu query, đối tượng bị khóa và việc mọi đường ghi liên quan có cùng tuân thủ giao thức hay không.

Nếu dùng optimistic concurrency, khi xung đột phải đọc lại và đánh giá lại các điều kiện phụ thuộc trạng thái. Không retry bằng kết quả kiểm tra cũ. Nếu dùng khóa trong bộ nhớ của một instance nhưng hệ thống có nhiều instance, khóa đó không bảo vệ toàn bộ luồng cập nhật.

Database constraint có thể hỗ trợ các điều kiện cục bộ và tính duy nhất. Những quy tắc trải nhiều bản ghi hoặc nhiều hệ thống vẫn cần cơ chế phối hợp phù hợp; không nên tuyên bố một constraint đơn lẻ đã bảo vệ tất cả nghiệp vụ.

## 8. Ví dụ Java: kiểm tra những điều kiện chưa cần đọc database

Ví dụ dùng Java 17 và giả định lớp tiếp nhận đã kiểm tra field bắt buộc, kiểu, định dạng cơ bản và giới hạn kích thước. `TypedRefund` là dữ liệu sau bước đó; các field bắt buộc không được `null`.

Đoạn mã chỉ kiểm tra quy tắc cục bộ của command và chuẩn hóa biểu diễn tiền theo chính sách đã chọn. Nó không xác nhận quyền, trạng thái đơn hàng hoặc số tiền còn được hoàn.

```java
import java.math.BigDecimal;
import java.math.RoundingMode;
import java.util.Map;

public final class RefundLocalRules {

    // Chỉ là tập tiền tệ được hỗ trợ trong ví dụ.
    private static final Map<String, Integer> MINOR_UNITS = Map.of(
        "USD", 2,
        "JPY", 0
    );

    private RefundLocalRules() {
    }

    public enum Reason {
        CUSTOMER_REQUEST,
        DUPLICATE_CHARGE
    }

    public record TypedRefund(
        String orderId,
        BigDecimal amount,
        String currency,
        Reason reason
    ) {
    }

    public record NormalizedRefund(
        String orderId,
        BigDecimal amount,
        String currency,
        Reason reason
    ) {
    }

    public static NormalizedRefund check(TypedRefund input) {
        Integer minorUnits = MINOR_UNITS.get(input.currency());
        if (minorUnits == null) {
            throw violation("UNSUPPORTED_CURRENCY");
        }

        if (input.amount().signum() <= 0) {
            throw violation("AMOUNT_MUST_BE_POSITIVE");
        }

        BigDecimal normalizedAmount;
        try {
            normalizedAmount = input.amount().setScale(
                minorUnits,
                RoundingMode.UNNECESSARY
            );
        } catch (ArithmeticException exception) {
            throw violation("AMOUNT_PRECISION_NOT_SUPPORTED");
        }

        return new NormalizedRefund(
            input.orderId(),
            normalizedAmount,
            input.currency(),
            input.reason()
        );
    }

    private static IllegalArgumentException violation(String code) {
        return new IllegalArgumentException(code);
    }
}
```

Theo chính sách của ví dụ, `125`, `125.0` và `125.00` USD đều có thể được chuẩn hóa về cùng giá trị và scale mà không làm tròn. `125.001` USD bị từ chối. Việc thêm hoặc bỏ những số `0` không có ý nghĩa ở phần lẻ là lựa chọn biểu diễn đã khai báo, không phải cho phép làm tròn tùy ý.

Danh sách loại tiền và đơn vị nhỏ nhất trong hệ thống thật cần có nguồn quản lý phù hợp. Nếu chính sách đó thay đổi, phải biết phiên bản nào đã được dùng để quyết định command đang xử lý.

Khi so sánh giá trị `BigDecimal`, cần phân biệt so sánh giá trị số với so sánh cả biểu diễn. Chẳng hạn, cách kiểm tra số tiền không vượt ngân sách phải dựa trên giá trị tiền đã thống nhất đơn vị, không vô tình từ chối hai biểu diễn bằng nhau chỉ vì scale khác nhau.

`NormalizedRefund` không có nghĩa là giao dịch đã được chấp thuận. Service thực hiện hoàn tiền vẫn phải áp dụng các điều kiện có trạng thái và phân quyền. Nếu chỉ gọi `check` rồi gửi ngay tới nhà cung cấp thanh toán, hệ thống vẫn có thể hoàn vượt mức hoặc hoàn sai tài nguyên.

Lý do `DUPLICATE_CHARGE` trong command chỉ biểu đạt lý do người gọi đề nghị. Nó không phải bằng chứng rằng thực sự có một lần thu trùng hoặc rằng khoản hoàn được miễn phê duyệt. Những quyết định này phải dùng dữ liệu và chính sách có thẩm quyền.

## 9. Gắn kiểm tra trạng thái với cơ chế giữ bất biến

Trong mô hình minh họa, mỗi giao dịch có một ngân sách hoàn được quản lý bằng các giá trị:

```text
C = tổng ngân sách được phép hoàn theo chính sách
S = tổng các khoản đã hoàn thành công
P = tổng các khoản đang giữ chỗ và chưa được kết luận cuối cùng

Phần còn có thể giữ chỗ = C - S - P
Bất biến cần giữ: S + P <= C
```

`C` không nhất thiết bằng toàn bộ số tiền đã thu trong mọi nghiệp vụ; có thể có phí hoặc điều kiện điều chỉnh. Hệ thống phải định nghĩa ngân sách đủ rõ và không tính trùng một khoản ở cả `S` lẫn `P` khi chuyển trạng thái.

Một luồng thiết kế có thể là:

```text
Tiếp nhận command và ngữ cảnh đã xác thực
  -> Kiểm tra cấu trúc, kiểu và quy tắc cục bộ
  -> Bắt đầu phạm vi cập nhật nguyên tử
       -> Xác định tài nguyên trong đúng phạm vi truy cập
       -> Kiểm tra quyền với tài nguyên và chính sách liên quan
       -> Xử lý khóa chống lặp theo scope đã định nghĩa
       -> Đọc trạng thái và ngân sách bằng cơ chế chống cạnh tranh
       -> Kiểm tra trạng thái cho phép hoàn và loại tiền
       -> Kiểm tra số tiền yêu cầu <= C - S - P
       -> Tạo khoản giữ chỗ và tăng P tương ứng
       -> Ghi công việc gửi yêu cầu thanh toán một cách bền vững
     Commit
  -> Thành phần xử lý công việc gọi nhà cung cấp
  -> Đối soát kết quả và chuyển trạng thái bằng quy tắc nguyên tử
```

Đây là mô hình trách nhiệm, không phải một đoạn chương trình có thể dùng nguyên trạng. Thiết kế cụ thể cần chọn cơ chế khóa, ràng buộc tính duy nhất, isolation và cách xử lý lỗi phù hợp với database.

Nếu dùng một outbox trong cùng transaction với khoản giữ chỗ, có thể tránh tình huống đã commit giữ chỗ nhưng quên ghi công việc cần gửi. Tuy nhiên, outbox không tự làm cho lời gọi bên ngoài diễn ra đúng một lần. Worker có thể gửi lại; phía xử lý và giao thức với nhà cung cấp vẫn cần chống lặp và đối soát.

Không giữ một transaction database mở lâu chỉ để chờ mạng nếu điều đó tạo khóa kéo dài và làm hệ thống cạn tài nguyên. Dù chọn phương án nào, khoảng cách giữa database và hệ thống bên ngoài phải được mô hình hóa bằng trạng thái, chứ không coi như một thao tác nguyên tử mặc nhiên.

Khi hoàn thành công, khoản tương ứng chuyển từ phần giữ chỗ sang phần đã hoàn. Khi có thất bại cuối cùng đã được xác nhận, có thể giải phóng giữ chỗ theo quy trình. **Timeout không tự chứng minh nhà cung cấp chưa thực hiện hoàn tiền.** Nếu kết quả chưa xác định, phải giữ trạng thái cần đối soát hoặc biện pháp bảo vệ tương đương; giải phóng ngay rồi cho hoàn tiếp có thể làm vượt ngân sách.

Mọi đường cập nhật ngân sách, bao gồm callback, tác vụ quản trị và công việc đối soát, phải tuân theo cùng bất biến. Một endpoint được khóa đúng không thể bảo vệ dữ liệu nếu một công cụ nội bộ cập nhật trực tiếp theo quy tắc khác.

## 10. Request lặp cũng là một dạng đầu vào nghiệp vụ

Người dùng bấm hai lần, client retry sau timeout hoặc một message được giao lại đều có thể làm cùng ý định xuất hiện nhiều lần. Hệ thống cần xác định hai request nào là một thao tác và khi nào chúng là hai thao tác riêng biệt.

Với khóa chống lặp, hợp đồng cần nêu:

- Scope của khóa, chẳng hạn theo tenant, loại thao tác và chủ thể hoặc danh tính tích hợp.
- Những field tạo nên nội dung command để so sánh cùng khóa.
- Cách chuẩn hóa đã được phê duyệt trước khi so sánh.
- Phản hồi khi cùng khóa đi kèm nội dung khác.
- Thời gian lưu khóa và bằng chứng về kết quả, tương ứng với khả năng retry thực tế.
- Cách xử lý hai request cùng khóa đến đồng thời.

Cùng khóa và cùng command phải quy về cùng thao tác theo hợp đồng, không tạo thêm khoản giữ chỗ. Cùng khóa nhưng đổi số tiền hoặc đơn hàng phải bị xử lý như xung đột, không coi đó là một yêu cầu hợp lệ mới.

Không chỉ kiểm tra “khóa chưa tồn tại” rồi insert mà thiếu bảo vệ cạnh tranh. Có thể cần ràng buộc duy nhất ở kho bền vững; khi hai request tranh cùng khóa, transaction thua phải rollback các tác động của nó trước khi đọc kết quả thao tác đã tồn tại. Cách thực hiện phải được kiểm chứng theo cơ chế transaction cụ thể.

Kiểm tra quyền vẫn áp dụng khi trả lại kết quả cũ. Không để người biết một khóa bất kỳ đọc được dữ liệu của thao tác ngoài phạm vi quyền của mình.

Hết thời gian lưu khóa không làm bất biến nghiệp vụ mất hiệu lực. Nếu hợp đồng cho phép khóa được tái sử dụng sau một khoảng thời gian, thiết kế vẫn cần bảo vệ các quy tắc như không hoàn vượt ngân sách. Khi có định danh nghiệp vụ duy nhất bền vững, cần xác định vai trò của nó độc lập với cache chống lặp.

## 11. Đặc tả yêu cầu có mã và bằng chứng

Các mã dưới đây minh họa một tập yêu cầu cho chức năng hoàn tiền. Hệ thống khác cần xây dựng tập quy tắc theo mô hình đe dọa và nghiệp vụ của mình.

| Mã | Yêu cầu | Bằng chứng nghiệm thu |
|---|---|---|
| BIZ-01 | Mỗi command chỉ nhận các field thể hiện ý định được phép; không dùng field client để xác lập quyền hoặc trạng thái có thẩm quyền | Schema command, ánh xạ field và thử gửi thuộc tính quản trị |
| BIZ-02 | Quy tắc liên field được áp dụng lên trạng thái dự kiến sau thay đổi, kể cả cập nhật từng phần | Kịch bản sửa riêng từng field và các kết hợp mâu thuẫn |
| BIZ-03 | Số tiền phải dương, đúng loại tiền và biểu diễn chính xác theo chính sách | Kiểm tra số âm, bằng 0, phần lẻ không được hỗ trợ và loại tiền không khớp |
| BIZ-04 | Quyết định dựa trên dữ liệu có thẩm quyền và chính sách tại thời điểm đã định nghĩa | Truy vết nguồn dữ liệu, phiên bản chính sách và thử trạng thái đã thay đổi |
| BIZ-05 | Bất biến ngân sách hoàn được bảo vệ tại điểm cập nhật bằng cơ chế chống cạnh tranh | Kịch bản hai hoặc nhiều request đồng thời với tổng vượt phần còn lại |
| BIZ-06 | Chuyển trạng thái chỉ xuất phát từ các trạng thái nguồn được phép | Ma trận chuyển trạng thái và thử mọi chuyển bị cấm |
| BIZ-07 | Retry cùng ý định không tạo thêm tác động; nội dung khác dùng cùng khóa không được thực hiện như thao tác mới | Kịch bản lặp tuần tự, đồng thời và retry sau timeout |
| BIZ-08 | Trạng thái kết quả bên ngoài chưa xác định không được xử lý như thất bại chắc chắn để giải phóng ngân sách | Diễn tập timeout và đối soát với kết quả đến muộn |
| BIZ-09 | Command bị từ chối không tạo tác động nghiệp vụ ngoài hành vi từ chối đã thiết kế | Quan sát database, outbox và lời gọi bên ngoài |
| BIZ-10 | Mọi kênh nhập có khả năng thay đổi cùng tài nguyên phải giữ cùng bất biến | Kiểm kê API, consumer, import và công cụ quản trị; thử qua từng kênh |
| BIZ-11 | Lỗi và audit đủ để giải thích quyết định nhưng không lộ dữ liệu nhạy cảm ngoài quyền | Kiểm tra phản hồi, log và dữ liệu audit trong các nhánh lỗi |
| BIZ-12 | Thay đổi quy tắc có owner, phiên bản và cách xử lý thao tác đang chờ | Hồ sơ thay đổi và kịch bản command đi qua thời điểm đổi chính sách |

Yêu cầu cần gán người chịu trách nhiệm: chủ nghiệp vụ xác nhận bất biến và ngoại lệ; đội ứng dụng thực thi; đội dữ liệu hoặc nền tảng xác nhận cơ chế đồng thời; đội kiểm thử cung cấp bằng chứng. “Một service khác sẽ kiểm tra” chỉ có giá trị khi trách nhiệm, giao thức và hành vi lỗi đã rõ.

Ngoại lệ cũng phải là một phần chính sách. Nếu một nhóm quản trị được phép điều chỉnh ngân sách, cần thao tác và quyền riêng, audit và điều kiện cụ thể; không thêm một field `skipValidation` vào command thông thường rồi tin giá trị client gửi.

## 12. Ma trận nghiệm thu theo rủi ro

Các kịch bản sau là hướng dẫn thiết kế kiểm thử, không phải báo cáo rằng một ứng dụng thực tế đã được kiểm thử trong bài học này.

| Kịch bản | Kết quả cần quan sát |
|---|---|
| Số tiền bằng 0 hoặc âm | Từ chối trước khi tạo giữ chỗ hoặc gửi yêu cầu thanh toán |
| Số tiền có phần lẻ không hỗ trợ | Không tự làm tròn; trả lỗi theo hợp đồng |
| Loại tiền khác giao dịch | Từ chối; không tự đổi loại tiền hoặc so sánh chỉ phần số |
| Số tiền đúng bằng phần còn lại | Có thể chấp nhận nếu các điều kiện khác đều đạt |
| Số tiền vượt phần còn lại một đơn vị nhỏ nhất | Từ chối; ngân sách không thay đổi |
| Giao dịch ở trạng thái chưa được phép hoàn | Từ chối chuyển trạng thái |
| Client tự gửi `approved` hoặc `alreadyRefunded` | Không dùng làm dữ liệu có thẩm quyền hoặc cập nhật ngoài quyền |
| Quy tắc liên field bị phá bằng một PATCH nhỏ | Trạng thái sau cập nhật vẫn bị kiểm tra đầy đủ |
| Hai request cùng muốn hoàn 40 khi chỉ còn 50 | Tổng được giữ chỗ không vượt 50; kết quả từng request rõ ràng |
| Hai request cùng khóa và cùng nội dung | Chỉ có một thao tác và một khoản giữ chỗ theo hợp đồng |
| Cùng khóa nhưng thay số tiền | Trả xung đột, không tạo tác động mới |
| Timeout sau khi nhà cung cấp có thể đã nhận lệnh | Không coi như chắc chắn chưa hoàn; trạng thái được đối soát an toàn |
| Callback hoặc message kết quả được gửi lại | Không cộng trùng tiền đã hoàn hoặc giải phóng giữ chỗ hai lần |
| Quyền hoặc chính sách thay đổi trong quá trình xử lý | Áp dụng chính sách thời điểm đã được đặc tả; không dùng quyết định cũ ngoài phạm vi hiệu lực |

Kiểm thử cạnh tranh cần tạo được sự chồng lấn ở điểm quan trọng, không chỉ gửi hai request cách nhau rồi gọi đó là chạy đồng thời. Bằng chứng cần quan sát bất biến sau các transaction và sau khi xử lý công việc bất đồng bộ, không chỉ mã phản hồi HTTP ban đầu.

Với tổng ngân sách `C`, kiểm tra `S + P <= C` trên dữ liệu thực tế sau diễn tập. Đồng thời kiểm tra không mất tác động hợp lệ và không có bản ghi treo ngoài mô hình trạng thái. Một hệ thống từ chối mọi request có thể giữ được bất biến nhưng vẫn không đáp ứng chức năng.

Đối với thời gian, thử ngay trước, đúng tại và ngay sau ranh giới theo định nghĩa đã chọn. Đối với hạn mức cộng dồn, thử trên các tài khoản, tenant và cửa sổ thời gian khác nhau để kiểm tra scope, không chỉ thử một lần vượt ngưỡng.

Nếu có đường bù hoặc rollback, cần phân biệt rollback database với bù một tác động đã xảy ra ở hệ thống ngoài. Một exception trong Java không thể mặc nhiên thu hồi lời gọi thanh toán mà nhà cung cấp đã thực hiện.

## 13. Phản hồi lỗi, audit và vận hành

Phản hồi lỗi nên diễn đạt quy tắc bị vi phạm theo mức chi tiết mà người gọi được phép biết. Ví dụ, sau khi đã kiểm tra quyền với tài nguyên, API có thể trả mã `REFUND_AMOUNT_EXCEEDS_AVAILABLE` mà không đưa toàn bộ lịch sử thanh toán vào response.

Trước khi tiết lộ trạng thái tài nguyên, cần áp dụng chính sách truy cập và chống lộ thông tin tương ứng. Không để một người chưa có quyền suy ra đơn hàng có tồn tại, đã thanh toán bao nhiêu hoặc đang được xử lý bởi ai thông qua các lỗi nghiệp vụ khác nhau.

Đối với HTTP, mã trạng thái cho command sai điều kiện, xung đột trạng thái hoặc lỗi nguồn phụ thuộc cần được thống nhất trong hợp đồng API. Với message, phải xác định khi nào retry, khi nào đưa vào hàng đợi xử lý riêng và khi nào đánh dấu từ chối cuối cùng. Không retry vô hạn một command không thể hợp lệ vì số tiền âm.

Audit có thể cần lưu chủ thể, tài nguyên, loại thao tác, mã quy tắc, trạng thái trước và sau trong phạm vi cần thiết, phiên bản chính sách và ID tương quan. Việc lưu số tiền hoặc dữ liệu khách hàng cần tuân theo phân loại, quyền đọc và thời gian lưu của hệ thống. Không đưa credential hoặc toàn bộ payload vào log để “giải thích vì sao validate lỗi”.

Khi nguồn dữ liệu cần thiết không sẵn sàng, không tự xem điều kiện là đã đạt. Hệ thống có thể từ chối tạm thời hoặc giữ command ở trạng thái chờ theo thiết kế; không thực hiện hoàn tiền chỉ vì không đọc được ngân sách hiện tại.

Nếu nghiệp vụ cho phép chế độ suy giảm, cần ghi rõ dữ liệu nào có thể dùng từ cache, giới hạn hiệu lực và những thao tác nào vẫn được phép. Một quyết định tài chính dựa trên trạng thái cũ cần cơ chế giữ bất biến tương ứng, không chỉ một thời gian cache tùy ý.

## 14. Những cách triển khai dễ tạo cảm giác đã an toàn

| Cách làm | Điều còn thiếu |
|---|---|
| Chỉ dùng annotation số dương | Chưa so khớp loại tiền, trạng thái hoặc ngân sách hiện tại |
| Chỉ validate trong giao diện | API và các đường nhập khác vẫn có thể bị gọi trực tiếp |
| Tin tổng tiền client gửi | Chưa xác định nguồn giá, chiết khấu và các thành phần có thẩm quyền |
| Kiểm tra xong rồi cập nhật ở bước không được bảo vệ | Có khoảng cạnh tranh làm kết quả kiểm tra cũ mất hiệu lực |
| Thêm transaction nhưng không xem query và isolation | Chưa chứng minh hai request không cùng vượt qua một trạng thái |
| Dùng cache chống lặp trong một instance | Không bảo vệ toàn hệ thống hoặc sau khi tiến trình khởi động lại |
| Giải phóng giữ chỗ khi timeout | Có thể giải phóng dù nhà cung cấp đã thực hiện thao tác |
| Bỏ qua validation cho công cụ nội bộ | Một đường ghi khác vẫn có thể phá cùng bất biến |
| Tự chỉnh đầu vào để qua rule | Thay đổi ý định mà không có hợp đồng và có thể che hành vi lạm dụng |

Không có một lớp `BusinessValidator` duy nhất tự giải quyết toàn bộ các vấn đề này. Một số điều kiện là hàm thuần trên command; một số phải nằm ở điểm cập nhật; một số là chính sách xử lý trạng thái bất đồng bộ. Thiết kế cần đặt mỗi điều kiện ở nơi có đủ dữ liệu và đủ khả năng giữ cam kết.

## 15. Bài tập chuyển yêu cầu mơ hồ thành hợp đồng

Một hệ thống bán hàng nhận `productId`, `quantity`, `unitPrice`, `couponCode` và `deliveryDate`. Nhân viên cũng có thể nhập cùng đơn hàng qua file. Tồn kho thay đổi liên tục; mã khuyến mại giới hạn một lần cho mỗi khách hàng; client có thể retry khi thanh toán timeout.

Hãy xây dựng:

1. Danh sách dữ liệu client được đề nghị và dữ liệu phải được server xác định.
2. Các quy tắc liên field và trạng thái cần kiểm tra trước khi xác nhận đơn.
3. Ít nhất hai bất biến cần được giữ khi có nhiều request đồng thời.
4. Chính sách chống lặp cho yêu cầu tạo đơn và thao tác thanh toán.
5. Cách áp dụng cùng bất biến cho API và file import.
6. Ma trận nghiệm thu gồm dữ liệu đúng kiểu nhưng sai nghiệp vụ, cạnh tranh tài nguyên và kết quả thanh toán chưa xác định.

Kết quả cần chỉ ra owner, nguồn dữ liệu, điểm thực thi và bằng chứng. Một câu như “giá phải hợp lệ” chưa đủ nếu không biết giá được lấy từ đâu, có hiệu lực vào lúc nào và điều gì xảy ra khi giá thay đổi giữa báo giá và xác nhận.

Business input validation có ý nghĩa bảo mật khi các quy tắc được biến thành điều kiện rõ ràng và bất biến được giữ tại điểm tạo tác động. Đầu vào không chỉ là các field trong request; còn có thứ tự, số lần gửi, thời điểm và trạng thái mà command được áp dụng lên.
