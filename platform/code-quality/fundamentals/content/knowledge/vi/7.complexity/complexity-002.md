# Số nhánh, đường đi và trạng thái cần suy nghĩ

Một phương thức có thể chỉ dài 20 dòng nhưng vẫn khó sửa vì người đọc phải theo dõi nhiều điều kiện, nhiều cách thực thi và nhiều trạng thái có thể xảy ra. Ngược lại, một đoạn mã dài hơn nhưng diễn đạt các bước tuần tự, rõ ràng có thể dễ hiểu hơn. Vì vậy, **độ phức tạp của mã không thể được kết luận chỉ từ số dòng**.

Trong module **CODE_QUALITY_FUNDAMENTALS**, chúng ta tìm hiểu những thuộc tính quyết định mã nguồn **đáng tin cậy, dễ hiểu và dễ thay đổi**. Ở chương **Độ phức tạp**, bài này tập trung vào ba câu hỏi: **mã có bao nhiêu nhánh quyết định, có những đường thực thi nào và người bảo trì phải ghi nhớ bao nhiêu trạng thái khi suy luận về hành vi?**

## Mục tiêu học tập

Sau bài này, bạn có thể:

- Phân biệt **nhánh (branch)**, **đường thực thi (execution path)** và **trạng thái (state)**.
- Giải thích vì sao số tổ hợp điều kiện có thể tăng nhanh hơn số câu lệnh `if`.
- Hiểu ý nghĩa và giới hạn của **độ phức tạp chu trình (cyclomatic complexity)**, **độ phức tạp nhận thức (cognitive complexity)** và **branch coverage**.
- Nhận diện những trạng thái không hợp lệ do sử dụng nhiều cờ Boolean độc lập.
- Thiết kế kiểm thử và cải tổ mã nhằm giảm lượng thông tin người đọc phải giữ trong đầu, trong khi bảo toàn quy tắc nghiệp vụ.

## 1. Ba khái niệm dễ bị nhầm

Xem ví dụ Java:

~~~java
int fee = 30_000;
if (vip) {
    fee -= 10_000;
}
if (hasVoucher) {
    fee -= 5_000;
}
if (express) {
    fee += 20_000;
}
return fee;
~~~

Ba câu lệnh `if` tạo ra ba điểm ra quyết định trong luồng điều khiển. Tuy nhiên, để hiểu hành vi, ta còn phải xét những tổ hợp đúng/sai của `vip`, `hasVoucher` và `express`.

| Khái niệm | Ý nghĩa | Trong ví dụ |
| --- | --- | --- |
| **Nhánh** | Hướng thực thi tại một quyết định điều khiển | Một `if` có hướng điều kiện đúng và sai |
| **Đường thực thi** | Chuỗi các hướng mà chương trình đi qua trong một lần chạy | Điều kiện VIP đúng, voucher sai, giao nhanh đúng |
| **Trạng thái** | Những dữ liệu và điều kiện đang có thể ảnh hưởng đến hành vi | Ba cờ được truyền vào cùng giá trị hiện tại của `fee` |

**Nhánh là lựa chọn cục bộ; đường thực thi là chuỗi lựa chọn; trạng thái là thông tin cần có để quyết định hành vi.** Chúng liên quan với nhau nhưng không phải một đại lượng.

Mã có ít nhánh vẫn có thể phải xử lý nhiều trạng thái. Chẳng hạn, một phương thức chỉ gọi `order.advance(event)` nhưng đằng sau nó là toàn bộ các trạng thái và chuyển đổi của đơn hàng.

## 2. Vì sao ít câu lệnh điều kiện vẫn có nhiều tổ hợp?

Giả sử **ba điều kiện độc lập** và mỗi điều kiện có hai khả năng: đúng hoặc sai. Số tổ hợp đầu vào là:

\[
2^3 = 8.
\]

Đây là bảng cho quy tắc phí giao hàng **giả định** ở ví dụ trên: phí cơ bản 30.000 VND; khách VIP được giảm 10.000 VND; voucher giảm thêm 5.000 VND; giao nhanh cộng 20.000 VND. Giả sử cả ba ưu đãi/lựa chọn có thể kết hợp và không có điều kiện khác.

| VIP | Voucher | Giao nhanh | Phí (VND) |
| --- | --- | --- | ---: |
| Không | Không | Không | 30.000 |
| Không | Không | Có | 50.000 |
| Không | Có | Không | 25.000 |
| Không | Có | Có | 45.000 |
| Có | Không | Không | 20.000 |
| Có | Không | Có | 40.000 |
| Có | Có | Không | 15.000 |
| Có | Có | Có | 35.000 |

Nếu quy tắc nghiệp vụ cho phép đủ tám trường hợp và cả ba `if` đều được thực thi khi chạy qua phương thức, có **tám tổ hợp lựa chọn** tương ứng với tám đường điều khiển phân biệt theo các kết quả đúng/sai.

Với `n` điều kiện Boolean độc lập, số tổ hợp tối đa là:

\[
2^n.
\]

Chẳng hạn bốn điều kiện có tối đa 16 tổ hợp, sáu điều kiện có tối đa 64 và mười điều kiện có tối đa 1.024. Đó là lý do các chính sách chứa nhiều cờ tùy chọn có thể khó kiểm tra dù từng `if` riêng lẻ rất đơn giản.

**Không được máy móc xem `2^n` là số đường đi thực tế của mọi phương thức.** Công thức này chỉ đếm tổ hợp giá trị Boolean độc lập. Trong chương trình:

- Hai điều kiện có thể phụ thuộc nhau, làm một số tổ hợp không thể xảy ra.
- Một nhánh `return` hoặc `throw` sớm có thể ngăn các điều kiện phía sau được đánh giá.
- Biểu thức có `&&` hoặc `||` sử dụng *short-circuit*, nên một số toán hạng không được tính trong mọi lần chạy.
- Vòng lặp có thể lặp nhiều lần; khi không giới hạn số vòng, số đường đi theo số lần lặp có thể không bị chặn bởi `2^n`.
- Ngoại lệ, callback và xử lý đồng thời có thể bổ sung những đường hoặc thứ tự thực thi cần quan sát.

Vì vậy cần tách bạch **số tổ hợp đầu vào**, **số đường điều khiển khả thi** và **số hành vi nghiệp vụ khác biệt**. Chúng có thể rất khác nhau.

## 3. Cyclomatic complexity đo điều gì?

**Cyclomatic complexity** là một phép đo dựa trên đồ thị luồng điều khiển. Với đồ thị có `N` nút, `E` cạnh và `P` thành phần liên thông theo cách định nghĩa của phép đo, công thức thường dùng là:

\[
M = E - N + 2P.
\]

Với một phương thức có một luồng điều khiển liên thông và các quyết định nhị phân đơn giản, ta thường có thể ước lượng:

\[
M \approx 1 + \text{số điểm quyết định nhị phân}.
\]

Đoạn tính phí gồm **ba câu lệnh `if` độc lập**, không có vòng lặp hoặc điều kiện phức hợp, nên độ phức tạp chu trình theo mô hình cơ bản là **4**. Con số **4 không có nghĩa chỉ tồn tại bốn tổ hợp**: ba điều kiện có thể tạo ra tám đường đi như bảng trên.

Sự khác biệt xuất hiện vì cyclomatic complexity đo cấu trúc và số **đường độc lập tuyến tính** trong đồ thị điều khiển; nó không đếm mọi tổ hợp thực thi từ đầu tới cuối. Các đường độc lập là một cơ sở để phân tích luồng, không đồng nghĩa với toàn bộ tập tình huống nghiệp vụ cần kiểm thử.

### Một ví dụ có trả về sớm

~~~java
boolean canProceed(Request request) {
    if (!request.isAuthenticated()) {
        return false;
    }
    if (!request.hasPermission()) {
        return false;
    }
    if (request.isExpired()) {
        return false;
    }
    return true;
}
~~~

Ba câu lệnh `if` vẫn tạo ba quyết định và cyclomatic complexity cơ bản vẫn là **4**. Nhưng theo luồng điều khiển của đoạn mã này, chỉ có **bốn đường thực thi chính**:

1. Không được xác thực → trả `false` ngay.
2. Được xác thực nhưng không có quyền → trả `false`.
3. Đủ hai điều kiện đầu nhưng yêu cầu hết hạn → trả `false`.
4. Qua cả ba kiểm tra → trả `true`.

Ở đường thứ nhất, Java không gọi `hasPermission()` hay `isExpired()`. Vì vậy, mặc dù ba thuộc tính Boolean có thể có tối đa tám tổ hợp giá trị về mặt dữ liệu, luồng thực thi đã gom nhiều tổ hợp thành cùng một đường do **trả về sớm**.

### Giới hạn khi dùng chỉ số

- Công cụ phân tích tĩnh có thể áp dụng quy tắc khác nhau cho `switch`, `catch`, toán tử điều kiện, biểu thức logic kết hợp và cú pháp hiện đại; phải hiểu định nghĩa của công cụ đang dùng.
- Độ phức tạp chu trình cao thường là tín hiệu cần xem lại khả năng kiểm thử, nhưng **không chứng minh mã sai**.
- Một quy tắc nghiệp vụ phức tạp thực sự có thể cần nhiều quyết định; không nên cố giảm điểm số bằng cách giấu toàn bộ logic vào helper khó tìm.
- Một phương thức có điểm thấp vẫn có thể khó hiểu nếu tên mơ hồ, chứa tác dụng phụ bất ngờ hoặc phụ thuộc trạng thái ẩn.

Hãy dùng chỉ số để **định hướng nơi cần đọc và kiểm tra kỹ**, không xem một ngưỡng chung là phép chứng nhận chất lượng cho mọi trường hợp.

## 4. Độ phức tạp nhận thức: người đọc phải giữ điều gì trong đầu?

**Cognitive complexity** tập trung vào mức khó theo dõi luồng điều khiển đối với con người. Những điều kiện lồng nhau thường khiến người đọc phải ghi nhớ nhiều giả định cùng lúc; việc chuyển qua nhiều mức lồng nhau cũng có thể làm mất mạch xử lý chính.

Ví dụ:

~~~java
boolean canProceed(Request request) {
    if (request.isAuthenticated()) {
        if (request.hasPermission()) {
            if (!request.isExpired()) {
                return true;
            }
        }
    }
    return false;
}
~~~

Người đọc ở lệnh `return true` phải nhớ rằng ba điều kiện bao ngoài đều đã được thỏa mãn. Nếu phần thân mỗi khối còn có thêm xử lý, gánh nặng suy luận sẽ tăng.

Có thể tổ chức lại:

~~~java
boolean canProceed(Request request) {
    if (!request.isAuthenticated()) {
        return false;
    }
    if (!request.hasPermission()) {
        return false;
    }
    if (request.isExpired()) {
        return false;
    }
    return true;
}
~~~

Phiên bản dùng **guard clauses** làm rõ các lý do từ chối, giảm mức lồng nhau và cho phép đọc luồng thành từng bước. Tuy nhiên, để nói hai bản **tương đương về hành vi**, cần giả định các phương thức kiểm tra có thể được gọi an toàn theo thứ tự này và không có tác dụng phụ làm thay đổi kết quả.

Hai cách viết trên cùng có ba quyết định nhị phân theo phép tính cyclomatic đơn giản. Do đó, **độ phức tạp chu trình có thể giữ nguyên trong khi việc đọc mã dễ hơn**. Đây là điểm khác nhau giữa phép đo cấu trúc luồng và mức khó suy luận.

Một tên gọi như `canProceed` cũng có thể còn quá rộng. Nếu nghiệp vụ thực sự nói về quyền tải tài liệu, tên `canDownloadDocument` sẽ làm rõ ý định hơn nữa. Độ phức tạp cần được đánh giá cùng **ngôn ngữ nghiệp vụ, mức độ lồng nhau, độ phụ thuộc và tác dụng phụ**.

## 5. Trạng thái: nguồn phức tạp không nằm hết trong câu lệnh `if`

Giả sử một hệ thống lưu ba cờ cho đơn hàng:

~~~java
boolean paid;
boolean packingStarted;
boolean shipped;
~~~

Về mặt biểu diễn, ba cờ có thể tạo **tám tổ hợp**. Nhưng không phải tổ hợp nào cũng hợp lệ: `shipped == true` trong khi `paid == false` có thể mâu thuẫn với quy trình đơn hàng đã được quy định.

Khi dùng nhiều cờ, mọi phương thức phải tự nhớ các quy tắc liên hệ giữa chúng: giao hàng chỉ sau khi đóng gói, đóng gói chỉ sau khi thanh toán, đơn đã hủy không thể giao. Nếu mỗi nơi kiểm tra một phần, hệ thống dễ phát sinh **trạng thái bất khả thi về mặt nghiệp vụ**.

Một lựa chọn là biểu diễn **giai đoạn chính** bằng kiểu có tên:

~~~java
enum OrderState {
    NEW,
    PAID,
    PACKING,
    SHIPPED,
    CANCELLED
}
~~~

Mô hình này thể hiện năm trạng thái nghiệp vụ đã xác định, giúp loại bỏ những tổ hợp cờ không hợp lệ trong phạm vi **giai đoạn chính**. Tuy nhiên, nếu nghiệp vụ còn có thanh toán một phần, hoàn tiền, giao nhiều kiện hoặc trạng thái giao hàng riêng, một `enum` duy nhất có thể không đủ. Khi đó cần mô hình hóa các chiều trạng thái có quan hệ rõ ràng, không ép tất cả vào một danh sách giá trị khổng lồ.

### Bảng chuyển trạng thái

Giả sử hệ thống có bốn sự kiện: `PAY` (thanh toán), `START_PACKING` (bắt đầu đóng gói), `SHIP` (giao hàng) và `CANCEL` (hủy). Với **quy tắc giả định** sau, các chuyển đổi được phép là:

| Trạng thái hiện tại | PAY | START_PACKING | SHIP | CANCEL |
| --- | --- | --- | --- | --- |
| **NEW** | PAID | Từ chối | Từ chối | CANCELLED |
| **PAID** | Từ chối | PACKING | Từ chối | CANCELLED |
| **PACKING** | Từ chối | Từ chối | SHIPPED | Từ chối |
| **SHIPPED** | Từ chối | Từ chối | Từ chối | Từ chối |
| **CANCELLED** | Từ chối | Từ chối | Từ chối | Từ chối |

Năm trạng thái kết hợp bốn sự kiện cho **20 cặp đầu vào**, nhưng chỉ **5 cặp** cho phép chuyển trạng thái. Bảng này buộc nhóm thiết kế trả lời điều gì xảy ra với mọi cặp: chuyển đi đâu, hay bị từ chối.

Ví dụ, bản thân bảng chưa giải quyết câu hỏi **nếu hủy một đơn đã thanh toán thì có phải hoàn tiền không?** Nếu có, hoàn tiền là một hành vi bổ sung cần đặc tả và kiểm thử. Việc mã hóa các trạng thái bằng `enum` không tự giải quyết những tác dụng phụ hoặc tính nhất quán giữa các hệ thống.

### Cần phân biệt số trạng thái và số chuyển đổi

Năm trạng thái không có nghĩa chỉ có năm hành vi phải kiểm tra. Một trạng thái có thể nhận nhiều sự kiện; một sự kiện có thể hợp lệ ở trạng thái này nhưng bị từ chối ở trạng thái khác. Do đó, ngoài các test cho **trạng thái**, cần kiểm tra **chuyển đổi**, **sự kiện bất hợp lệ**, và nếu có tác dụng phụ thì cả **hành vi sau chuyển đổi**.

## 6. Chiều trạng thái độc lập làm không gian suy luận phình lên

Giả sử một yêu cầu thanh toán còn phụ thuộc vào:

- Trạng thái đơn hàng: **5** giá trị.
- Phương thức thanh toán: **3** giá trị.
- Trạng thái kết nối đối tác: **2** giá trị.
- Khách hàng có quyền ưu tiên hay không: **2** giá trị.

Nếu các chiều này hoàn toàn độc lập, không gian kết hợp tối đa là:

\[
5 \times 3 \times 2 \times 2 = 60.
\]

Trong thực tế, một số kết hợp có thể bị cấm hoặc không ảnh hưởng đến chức năng đang xét. Nhưng để xác định điều đó, ta phải hiểu **ràng buộc giữa các chiều**.

Đây là một dạng **bùng nổ tổ hợp (combinatorial explosion)**. Không thể khắc phục chỉ bằng việc tách một phương thức 100 dòng thành năm phương thức 20 dòng. Mức độ phức tạp của quy tắc vẫn tồn tại; việc tổ chức mã tốt chỉ giúp chia nhỏ phạm vi phải suy nghĩ tại một thời điểm.

Các cách kiểm soát hữu ích:

1. **Loại bỏ trạng thái không hợp lệ từ mô hình** bằng kiểu dữ liệu, bất biến và ràng buộc ở tầng lưu trữ khi cần.
2. **Phân tách trách nhiệm** theo các quy tắc tương đối độc lập, ví dụ quyết định quyền thao tác khác với quyết định cách giao tiếp với đối tác.
3. **Diễn đạt quy tắc bằng bảng quyết định hoặc bảng trạng thái** khi số điều kiện khiến một biểu thức logic dài khó theo dõi.
4. **Đưa các kiểm tra quan trọng về một ranh giới nhất quán**, tránh mỗi nơi tự tái tạo một phần quy tắc.
5. **Kiểm thử theo rủi ro**, ưu tiên tổ hợp có hậu quả lỗi cao, giá trị biên và những tương tác giữa điều kiện.

Mục tiêu là giảm **những điều người bảo trì phải đồng thời ghi nhớ**, không phải xóa bỏ các quy tắc mà nghiệp vụ thật sự yêu cầu.

## 7. Branch coverage không đồng nghĩa bao phủ mọi đường đi

Quay lại ba `if` độc lập của tính phí giao hàng. Để chạy được cả nhánh đúng và nhánh sai của từng `if`, hai ca sau có thể đủ để đạt **100% branch coverage** cho ba quyết định trong ví dụ đơn giản:

| Ca | VIP | Voucher | Giao nhanh |
| --- | --- | --- | --- |
| A | Không | Không | Không |
| B | Có | Có | Có |

Nhưng hai ca đó chỉ kiểm tra **2 trong 8 tổ hợp**. Một lỗi xuất hiện riêng khi **VIP và voucher cùng bật nhưng không giao nhanh** sẽ không được phát hiện bởi hai ca này.

Vì vậy cần phân biệt:

| Mục tiêu kiểm thử | Câu hỏi được trả lời | Điều chưa thể kết luận |
| --- | --- | --- |
| Statement coverage | Các dòng nào đã được chạy? | Không chứng minh kết quả đúng hay đủ trường hợp |
| Branch coverage | Các hướng đúng/sai tại quyết định đã được đi qua chưa? | Không chứng minh mọi chuỗi điều kiện đã được thử |
| Path coverage | Những đường điều khiển nào đã được thực hiện? | Có thể không thực tế để bao phủ hết khi có vòng lặp |
| Decision table testing | Những tổ hợp quy tắc nghiệp vụ nào đã được xét? | Phụ thuộc độ đầy đủ của bảng quy tắc |
| State transition testing | Các chuyển đổi trạng thái hợp lệ/bất hợp lệ đã được thử? | Chưa tự bao phủ lỗi đồng thời, tích hợp hoặc tác dụng phụ |

**Độ bao phủ cao là bằng chứng về phạm vi mã hoặc luồng đã đi qua, không phải tỷ lệ phần trăm xác suất chương trình đúng.**

### Kiểm thử cặp điều kiện (pairwise) giúp được gì?

Với ba cờ Boolean, bốn trường hợp sau kiểm tra đủ cả bốn kết hợp đúng/sai cho **từng cặp cờ**:

| Ca | VIP | Voucher | Giao nhanh |
| --- | --- | --- | --- |
| 1 | Không | Không | Không |
| 2 | Không | Có | Có |
| 3 | Có | Không | Có |
| 4 | Có | Có | Không |

Pairwise là kỹ thuật chọn tập trường hợp để giảm số tổ hợp cần thử khi nhiều điều kiện độc lập. Nó có thể phát hiện lỗi do tương tác giữa hai điều kiện, nhưng **không bảo đảm bắt được lỗi chỉ xuất hiện khi cả ba cùng đúng**. Trong bảng trên, ca `VIP = true`, `voucher = true`, `express = true` chưa được kiểm tra.

Với quy tắc tính phí chỉ có tám tổ hợp, việc viết đủ tám ca có thể đơn giản và đáng làm hơn. Với hàng chục chiều đầu vào, phải ưu tiên theo quy tắc, rủi ro, giá trị biên và kỹ thuật chọn trường hợp phù hợp.

## 8. Kiểm thử Java theo bảng quyết định

Ta đóng gói ví dụ tính phí thành phương thức thuần để dễ xác minh:

~~~java
public final class ShippingFee {
    private ShippingFee() {
    }

    public static int calculate(
            boolean vip,
            boolean hasVoucher,
            boolean express) {
        int feeVnd = 30_000;

        if (vip) {
            feeVnd -= 10_000;
        }
        if (hasVoucher) {
            feeVnd -= 5_000;
        }
        if (express) {
            feeVnd += 20_000;
        }
        return feeVnd;
    }
}
~~~

Kiểm thử JUnit 5 có thể lấy kết quả mong đợi trực tiếp từ bảng quy tắc:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;

import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.CsvSource;

class ShippingFeeTest {
    @ParameterizedTest
    @CsvSource({
        "false, false, false, 30000",
        "false, false, true,  50000",
        "false, true,  false, 25000",
        "false, true,  true,  45000",
        "true,  false, false, 20000",
        "true,  false, true,  40000",
        "true,  true,  false, 15000",
        "true,  true,  true,  35000"
    })
    void feeMatchesDecisionTable(
            boolean vip,
            boolean voucher,
            boolean express,
            int expectedFeeVnd) {
        assertEquals(
            expectedFeeVnd,
            ShippingFee.calculate(vip, voucher, express)
        );
    }
}
~~~

Kết quả mong đợi ở đây đến từ **quy tắc nghiệp vụ giả định**, chứ không được tạo bằng cách sao chép thuật toán trong `calculate`. Nhờ đó, nếu ai đó đổi thứ tự hoặc công thức tính sai, test có khả năng phát hiện chênh lệch.

Nếu chính sách mới quy định **không được dùng đồng thời VIP và voucher**, cần cập nhật hợp đồng và tập trường hợp: tổ hợp đó có thể phải trả lỗi thay vì cộng hai khoản giảm giá. Những đường đi trong code hiện tại không tự quyết định đâu là trạng thái nghiệp vụ hợp lệ.

## 9. Cách giảm độ phức tạp mà không che giấu vấn đề

Một số thay đổi kỹ thuật có ích nhưng mỗi cách giải quyết một dạng gánh nặng suy luận khác nhau:

| Dấu hiệu | Hướng cải thiện | Điều cần kiểm tra |
| --- | --- | --- |
| Nhiều `if` lồng nhau để kiểm tra điều kiện tiên quyết | Guard clause, trả về sớm có tên lý do | Thứ tự kiểm tra, lỗi trả về và tác dụng phụ |
| Cờ Boolean phối hợp tạo trạng thái vô lý | `enum` hoặc mô hình trạng thái được ràng buộc | Các trạng thái và chuyển đổi hợp lệ |
| Một biểu thức chứa nhiều điều kiện nghiệp vụ | Phương thức có tên thể hiện ý định hoặc bảng quyết định | Quy tắc ưu tiên và các tổ hợp điều kiện |
| Quy tắc bị sao chép tại nhiều nơi | Đưa quyết định về thành phần chịu trách nhiệm | Không làm thay đổi hành vi hay bỏ qua kiểm soát |
| Hàm lớn trộn quyết định và thao tác I/O | Phân tách tính toán thuần và thao tác bên ngoài | Đảm bảo thứ tự và tính nhất quán của tác dụng phụ |
| Các nhánh có cấu trúc giống nhau nhưng khác chính sách | Cân nhắc Strategy hoặc bảng cấu hình có kiểm soát | Đừng trừu tượng hóa quá mức khi chưa có nhu cầu thật |

Ví dụ, tách ba `if` tính phí vào ba phương thức nhỏ không làm giảm số tổ hợp nghiệp vụ cần xét. Nhưng việc tách **quyết định tính phí** khỏi **đọc dữ liệu giỏ hàng**, **gọi cổng thanh toán** và **lưu đơn hàng** có thể giảm số yếu tố người đọc phải theo dõi cùng lúc, đồng thời giúp kiểm thử quy tắc dễ hơn.

### Đừng cố giảm chỉ số bằng mọi giá

Một số thay đổi làm điểm cyclomatic của **một phương thức** giảm nhưng không làm quy tắc trở nên đơn giản hơn:

~~~java
int calculateFee(Options options) {
    return externalPolicyEngine.evaluate(options);
}
~~~

Phương thức rất ngắn, nhưng người đọc vẫn cần tìm hiểu quy tắc bên trong `externalPolicyEngine`. Nếu quy tắc bị đẩy sang cấu hình không có kiểm thử hoặc không rõ thứ tự ưu tiên, độ khó bảo trì có thể tăng.

**Phân tách mã tốt là phân tách theo trách nhiệm và khái niệm có ý nghĩa**, giữ cho quyết định quan trọng có thể tìm thấy và kiểm chứng. Chia nhỏ chỉ để cải thiện con số đo mà làm người đọc phải mở nhiều tệp hơn có thể phản tác dụng.

## 10. Thực hành đánh giá một đoạn mã phức tạp

Khi tiếp cận mã lạ, hãy trả lời lần lượt:

1. **Hành vi đang được quyết định là gì?** Ghi lại đầu vào, kết quả, trạng thái và tác dụng phụ.
2. **Có bao nhiêu điểm rẽ?** Xem `if`, `switch`, vòng lặp, bắt ngoại lệ, trả về sớm và toán tử logic.
3. **Điều kiện có độc lập không?** Nếu phụ thuộc, ghi rõ những tổ hợp không thể xảy ra hoặc không được phép.
4. **Có bao nhiêu trạng thái phải nhớ cùng lúc?** Phân biệt trạng thái bền vững của nghiệp vụ với biến trung gian được tính lại mỗi lần.
5. **Những đường nào quan trọng về rủi ro?** Ưu tiên chuyển tiền, phân quyền, ghi dữ liệu, retry, lỗi mạng và xử lý đồng thời khi chúng hiện diện.
6. **Bằng chứng kiểm thử hiện có bao phủ điều gì?** Kiểm tra cả kết quả mong đợi, biên, tổ hợp điều kiện, trạng thái và tác dụng phụ.
7. **Có thể làm rõ mã bằng tên gọi, bảng quyết định hoặc mô hình trạng thái không?** Chọn thay đổi làm giảm suy luận và giữ hành vi được cam kết.

Số nhánh lớn là dấu hiệu đáng kiểm tra, nhưng quyết định thay đổi phải dựa vào **ngữ cảnh nghiệp vụ, nơi phát sinh lỗi và khả năng kiểm chứng**. Mục tiêu không phải mọi phương thức đều có cùng điểm đo, mà là người bảo trì có thể suy luận đúng với công sức hợp lý.

## 11. Bài tập tự kiểm tra

Một chức năng xét duyệt yêu cầu có ba điều kiện Boolean:

- `isAuthenticated`: người gửi đã đăng nhập.
- `hasPermission`: người gửi có quyền phê duyệt.
- `isExpired`: yêu cầu đã hết hạn.

Luật nghiệp vụ giả định: **chỉ chấp nhận khi đã đăng nhập, có quyền và yêu cầu chưa hết hạn**.

~~~java
boolean approve(
        boolean isAuthenticated,
        boolean hasPermission,
        boolean isExpired) {
    if (!isAuthenticated) {
        return false;
    }
    if (!hasPermission) {
        return false;
    }
    if (isExpired) {
        return false;
    }
    return true;
}
~~~

**Câu hỏi A.** Có bao nhiêu tổ hợp Boolean có thể đưa vào? Có bao nhiêu đường thực thi chính với các lệnh trả về sớm?

**Câu hỏi B.** Hai test “cả ba điều kiện hợp lệ” và “cả ba điều kiện bất lợi” có bảo đảm đã kiểm tra được mọi lý do từ chối không?

**Câu hỏi C.** Nếu có thêm trạng thái `REVOKED` (đã thu hồi), có nên thêm một cờ Boolean riêng hay mô hình hóa bằng trạng thái yêu cầu? Cần tìm hiểu gì trước khi chọn?

### Gợi ý đáp án

**A.** Có tối đa **8 tổ hợp giá trị Boolean**; với điều khiển trả về sớm như đoạn mã, có **4 đường thực thi chính**: từ chối ở từng kiểm tra trong ba kiểm tra, hoặc chấp nhận sau cả ba.

**B.** Không. Test “cả ba bất lợi” dừng ở `!isAuthenticated` và không kiểm tra nhánh từ chối vì **thiếu quyền** hoặc **hết hạn** khi các điều kiện trước đã hợp lệ. Ít nhất cần những ca riêng để đi đến từng điểm trả về.

**C.** Cần xác định `REVOKED` có phải là trạng thái loại trừ với `EXPIRED`, có thể xảy ra đồng thời hay là khía cạnh độc lập; ai được thu hồi, thời điểm hiệu lực và các chuyển đổi nào được phép. Nếu các trạng thái loại trừ nhau, `enum` có thể tránh tổ hợp vô lý. Nếu chúng thực sự là các chiều độc lập, cần mô hình rõ quan hệ và điều kiện hợp lệ thay vì thêm cờ tùy tiện.

## Ghi nhớ

**Số nhánh, đường đi và trạng thái** là ba góc nhìn khác nhau về độ phức tạp. Một vài nhánh có thể tạo nhiều tổ hợp hành vi; nhiều cờ có thể tạo trạng thái bất hợp lệ; điểm cyclomatic thấp chưa chắc làm mã dễ hiểu hoặc kiểm thử đầy đủ.

Để quản lý độ phức tạp, hãy xác định **quy tắc nghiệp vụ**, làm rõ **những tổ hợp khả thi**, đặt các **quyết định đúng trách nhiệm**, mô hình hóa **trạng thái hợp lệ** và lựa chọn **kiểm thử phù hợp với rủi ro**. Mã tốt giúp người khác suy luận đáng tin cậy về hành vi mà không phải giữ quá nhiều điều kiện trong đầu cùng một lúc.
