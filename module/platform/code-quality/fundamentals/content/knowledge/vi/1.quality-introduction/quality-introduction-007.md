# Phân biệt lỗi, mùi mã, vi phạm quy ước và nợ kỹ thuật

Trong hoạt động phát triển phần mềm, một đoạn mã có thể chạy sai, khó đọc, không tuân thủ quy ước hoặc khiến việc thay đổi trong tương lai trở nên tốn kém. Bốn hiện tượng này liên quan đến chất lượng mã nguồn nhưng không đồng nghĩa với nhau. Phân biệt đúng giúp nhóm chọn cách xử lý, mức ưu tiên và tiêu chí kiểm chứng phù hợp.

Bài học thuộc phần **Nhập môn** của **CODE_QUALITY_FUNDAMENTALS**, tập trung vào các thuộc tính quyết định mã nguồn có **đáng tin cậy, dễ hiểu và dễ thay đổi** hay không.

## 1. Bốn khái niệm cốt lõi

### 1.1. Lỗi (bug/defect): mã thực hiện sai điều cần thực hiện

**Lỗi** là khi phần mềm không đáp ứng một yêu cầu, quy tắc nghiệp vụ hoặc thuộc tính chất lượng đã được xác định. Lỗi có thể làm kết quả sai, phát sinh ngoại lệ, làm mất dữ liệu, tạo lỗ hổng bảo mật hoặc vi phạm ngưỡng hiệu năng đã cam kết.

Ví dụ: yêu cầu nêu “đơn hàng từ 500.000 VND trở lên được miễn phí vận chuyển”, nhưng mã chỉ miễn phí khi tổng tiền **lớn hơn** 500.000 VND. Với đơn đúng 500.000 VND, kết quả tính phí sai: đây là lỗi biên.

Cần phân biệt **defect** (khiếm khuyết trong mã hoặc thiết kế) với **failure** (biểu hiện sai được quan sát khi chạy). Một defect có thể chưa bộc lộ thành failure vì chưa gặp điều kiện kích hoạt. Ngược lại, trước khi kết luận là bug, nên xác nhận hành vi mong đợi từ yêu cầu, hợp đồng API hoặc quyết định nghiệp vụ.

Dấu hiệu nhận biết:

- Có sự khác biệt kiểm chứng được giữa **kết quả thực tế** và **kết quả mong đợi**.
- Có thể mô tả điều kiện tái hiện, dữ liệu đầu vào và ảnh hưởng.
- Thường chứng minh được bằng bài kiểm thử thất bại, log hoặc bản ghi sự cố.

**Hướng xử lý:** sửa logic hoặc điều kiện gây sai; bổ sung kiểm thử hồi quy để lỗi không tái xuất hiện. Mức ưu tiên phụ thuộc vào tác động và khả năng xảy ra, không chỉ phụ thuộc vào số dòng cần sửa.

### 1.2. Mùi mã (code smell): tín hiệu cấu trúc có thể gây khó khăn

**Mùi mã** là dấu hiệu trong cách tổ chức hoặc biểu đạt mã cho thấy thiết kế có thể khó hiểu, khó kiểm thử, khó mở rộng hoặc khó bảo trì. Bản thân mùi mã **không chứng minh chương trình đang chạy sai**.

Ví dụ thường gặp:

- **Long Method:** một phương thức xử lý nhiều trách nhiệm, phải cuộn qua hàng trăm dòng mới hiểu được.
- **Duplicated Code:** cùng quy tắc tính toán xuất hiện ở nhiều nơi, tăng nguy cơ sửa thiếu.
- **Magic Number:** các số như 500_000 hay 30_000 nằm trực tiếp trong nhiều nhánh mà không có tên diễn giải ý nghĩa.
- **Large Class / God Class:** một lớp vừa truy cập dữ liệu, áp dụng nghiệp vụ, định dạng đầu ra và gửi thông báo.
- **Feature Envy:** phương thức liên tục truy cập dữ liệu nội bộ của đối tượng khác để thực hiện phần lớn công việc của đối tượng ấy.

Mùi mã là **tín hiệu để điều tra**, không phải phán quyết tự động. Chẳng hạn, hai dòng giống nhau chưa chắc cần trừu tượng hóa: chúng có thể đại diện cho hai quy tắc nghiệp vụ độc lập, dự kiến thay đổi khác nhau. Chất lượng thiết kế phải được đánh giá trong ngữ cảnh thay đổi thực tế.

**Hướng xử lý:** refactor có kiểm soát, chẳng hạn đặt tên hằng số, tách phương thức, gom quy tắc dùng chung hoặc phân chia trách nhiệm. Khi refactor đúng nghĩa, **hành vi bên ngoài vẫn giữ nguyên**; kiểm thử hiện có giúp chứng minh điều đó.

### 1.3. Vi phạm quy ước (convention violation): không theo chuẩn đã thống nhất

**Vi phạm quy ước** xảy ra khi mã không tuân thủ quy tắc đặt tên, định dạng, cấu trúc import, tổ chức file hoặc hướng dẫn lập trình mà dự án đã chấp nhận.

Ví dụ trong một dự án Java áp dụng quy ước đặt tên phương thức theo **lowerCamelCase**, tên **calculate_fee()** vi phạm quy ước, dù phương thức vẫn có thể biên dịch và tính đúng. Một nhóm khác có thể có ngoại lệ hợp lý hoặc quy ước riêng; phải dựa vào **chuẩn thực tế của dự án**, không suy diễn từ sở thích cá nhân.

Các vi phạm thường gặp gồm khoảng trắng, indent, độ dài dòng, tên biến, thứ tự import và cách trình bày khai báo. Công cụ formatter, linter và kiểm tra trong CI thường phù hợp để phát hiện các vi phạm có thể cơ giới hóa.

**Hướng xử lý:** đổi tên, định dạng hoặc sửa theo quy ước, ưu tiên công cụ tự động khi an toàn. Với thay đổi tên API công khai, cần kiểm tra mã gọi, tương thích và phạm vi ảnh hưởng thay vì coi đó là thay đổi hình thức thuần túy.

### 1.4. Nợ kỹ thuật (technical debt): chi phí tương lai do lựa chọn hoặc tồn đọng kỹ thuật

**Nợ kỹ thuật** là gánh nặng mà nhóm sẽ phải trả khi phát triển, vận hành hoặc thay đổi hệ thống vì một giải pháp kỹ thuật chưa phù hợp với nhu cầu dài hạn. Nợ có thể được chấp nhận có chủ đích để đạt mốc phát hành, hoặc hình thành ngoài ý muốn do thiếu hiểu biết, yêu cầu thay đổi và các quyết định cũ không còn phù hợp.

Ví dụ: để kịp phát hành, nhóm sao chép quy tắc tính phí vận chuyển vào ba dịch vụ thay vì xây dựng một nguồn quy tắc thống nhất. Hệ thống hiện vẫn tính đúng, nhưng mỗi lần thay đổi mức phí phải sửa ba nơi, dễ thiếu đồng bộ và tốn công kiểm thử. **Chi phí phát sinh mỗi lần thay đổi** là “lãi” của khoản nợ; việc hợp nhất và kiểm chứng quy tắc là phần công trả nợ.

Không phải mọi quyết định đi đường ngắn đều là nợ xấu. Một lựa chọn tạm thời có giới hạn rõ ràng, được theo dõi và có kế hoạch xử lý có thể hợp lý về mặt kinh doanh. Vấn đề là **chi phí, rủi ro và khả năng kiểm soát khoản nợ**, không phải việc có dùng giải pháp hoàn hảo ngay từ đầu hay không.

**Hướng xử lý:** ghi nhận vị trí, lý do, hệ quả và điểm kích hoạt cần xử lý; ưu tiên trả nợ theo mức cản trở thực tế. Có khoản nợ nên xử lý ngay, khoản khác nên xử lý khi chạm đến khu vực mã liên quan.

## 2. Bảng phân biệt nhanh

| Tiêu chí | Lỗi (bug) | Mùi mã (code smell) | Vi phạm quy ước | Nợ kỹ thuật |
| --- | --- | --- | --- | --- |
| Câu hỏi chính | Hành vi có sai yêu cầu không? | Cấu trúc có gây khó hiểu, khó thay đổi không? | Mã có lệch chuẩn đã thống nhất không? | Lựa chọn hoặc tồn đọng này tạo chi phí tương lai nào? |
| Bằng chứng điển hình | Ca kiểm thử thất bại, kết quả sai, sự cố thực tế | Độ phức tạp cao, trùng lặp, khó kiểm thử | Quy tắc style, cảnh báo linter/formatter | Lịch sử quyết định, chi phí sửa đổi lặp lại, rủi ro tích lũy |
| Có nhất thiết làm chương trình chạy sai? | Có sai lệch so với yêu cầu/thuộc tính đã xác định | Không | Không | Không nhất thiết |
| Cách xử lý chính | Sửa hành vi và thêm kiểm thử hồi quy | Refactor, giữ nguyên hành vi | Sửa theo quy ước, tự động hóa khi phù hợp | Giảm hoặc quản lý khoản nợ theo tác động |
| Cách xác nhận đã xử lý | Ca lỗi qua kiểm thử; hành vi đúng | Mã dễ hiểu/kiểm thử/thay đổi hơn, bài kiểm thử vẫn qua | Kiểm tra quy ước thông qua | Chi phí/rủi ro dự kiến giảm, tiêu chí hoàn tất rõ ràng |

**Lưu ý:** đây là bốn *góc nhìn*, không phải bốn ngăn loại trừ nhau. Một đoạn mã có thể đồng thời chứa bug, smell và biểu hiện của technical debt. Chọn nhãn theo **vấn đề muốn giải quyết** và lưu những quan hệ còn lại khi cần.

## 3. Ví dụ xuyên suốt bằng Java

Giả sử đặc tả nghiệp vụ quy định:

- Phí vận chuyển tiêu chuẩn là **30.000 VND**.
- Khách VIP **hoặc** đơn hàng có tổng tiền **từ 500.000 VND trở lên** được miễn phí.
- Tổng tiền đơn hàng không âm.

Một phiên bản triển khai ban đầu:

~~~java
final class ShippingFeeCalculator {
    int calculate_fee(int orderTotalVnd, boolean isVip) {
        int fee = 30_000;

        if (orderTotalVnd > 500_000) {
            fee = 0;
        }
        if (isVip) {
            fee = 0;
        }

        return fee;
    }
}
~~~

**Phân tích từng hiện tượng:**

1. **Bug:** điều kiện **orderTotalVnd > 500_000** bỏ sót trường hợp bằng 500.000. Với khách không phải VIP, đầu vào 500.000 trả về 30.000 thay vì 0. Ngoài ra, đoạn mã chưa kiểm tra tổng tiền âm theo giả định đầu vào; việc này chỉ được coi là bug nếu hợp đồng yêu cầu phương thức từ chối giá trị âm.
2. **Code smell:** các con số nghiệp vụ nằm trực tiếp trong thân phương thức, không có tên giải thích; giá trị **fee = 0** được gán trong hai nhánh. Với quy tắc nhỏ, sự lặp này chưa nghiêm trọng, nhưng sẽ bất tiện nếu chính sách phát triển phức tạp hơn.
3. **Convention violation:** tên phương thức **calculate_fee** không theo lowerCamelCase được áp dụng trong ví dụ này.
4. **Technical debt:** giả sử để kịp phát hành, nhóm đã sao chép cùng logic ở nhiều dịch vụ và hoãn thống nhất chính sách. Quyết định và chi phí bảo trì đó là nợ kỹ thuật. **Chỉ nhìn vào một phương thức ở trên chưa đủ cơ sở kết luận có nợ**.

Phiên bản cải thiện sau khi sửa bug và làm rõ cấu trúc:

~~~java
final class ShippingFeeCalculator {
    private static final int FREE_SHIPPING_THRESHOLD_VND = 500_000;
    private static final int STANDARD_SHIPPING_FEE_VND = 30_000;

    int calculateFee(int orderTotalVnd, boolean isVip) {
        if (orderTotalVnd < 0) {
            throw new IllegalArgumentException(
                    "orderTotalVnd must not be negative");
        }

        if (isVip || orderTotalVnd >= FREE_SHIPPING_THRESHOLD_VND) {
            return 0;
        }
        return STANDARD_SHIPPING_FEE_VND;
    }
}
~~~

Ví dụ kiểm thử hồi quy với JUnit 5 (minh họa; cần có JUnit 5 trong dự án để chạy):

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import org.junit.jupiter.api.Test;

class ShippingFeeCalculatorTest {
    private final ShippingFeeCalculator calculator =
            new ShippingFeeCalculator();

    @Test
    void waivesShippingAtExactThreshold() {
        assertEquals(0, calculator.calculateFee(500_000, false));
    }

    @Test
    void waivesShippingForVipBelowThreshold() {
        assertEquals(0, calculator.calculateFee(100_000, true));
    }

    @Test
    void chargesStandardFeeBelowThreshold() {
        assertEquals(30_000, calculator.calculateFee(499_999, false));
    }

    @Test
    void rejectsNegativeTotal() {
        assertThrows(IllegalArgumentException.class,
                () -> calculator.calculateFee(-1, false));
    }
}
~~~

Bài kiểm thử tại **đúng ngưỡng 500.000** trực tiếp phát hiện bug. Việc đổi tên phương thức và đưa các con số vào hằng số cải thiện khả năng đọc. Tuy nhiên, nếu logic vẫn còn bị sao chép ở nhiều dịch vụ, **khoản nợ kỹ thuật ở cấp hệ thống chưa được giải quyết**; cần kiểm tra các nơi dùng quy tắc và chọn một nguồn duy trì phù hợp.

## 4. Các khái niệm liên hệ với nhau ra sao?

### 4.1. Mùi mã có thể làm tăng nguy cơ lỗi

Phương thức quá dài, nhiều nhánh hoặc quy tắc lặp ở nhiều chỗ khiến người sửa dễ bỏ qua trường hợp biên. Điều này làm tăng **xác suất xuất hiện bug**, nhưng mùi mã không tự động trở thành bug nếu hiện tại chương trình đáp ứng yêu cầu.

### 4.2. Mùi mã có thể là biểu hiện của nợ kỹ thuật

Việc sao chép logic giữa nhiều dịch vụ vừa là dấu hiệu **duplicated code** vừa có thể là **nợ kỹ thuật** khi nhóm biết chi phí đồng bộ tương lai và chấp nhận trì hoãn việc xử lý. Mùi mã mô tả **hình thái trong mã**; nợ kỹ thuật nhấn mạnh **chi phí và hệ quả qua thời gian**.

### 4.3. Vi phạm quy ước có thể tồn tại cùng bug hoặc smell

Một tên phương thức không chuẩn có thể khiến mã khó tìm, nhưng việc đổi tên không nhất thiết sửa lỗi tính toán. Ngược lại, mã đẹp và đúng format vẫn có thể sai nghiệp vụ. Không nên dùng chỉ số linter như bằng chứng duy nhất cho tính đúng đắn.

### 4.4. Lỗi bị hoãn xử lý không đồng nghĩa mọi khoản nợ kỹ thuật

Một bug còn nằm trong backlog là **lỗi chưa sửa**. Nếu nhóm chủ động chấp nhận giải pháp tạm hoặc trì hoãn cải thiện kỹ thuật tạo ra chi phí bảo trì tương lai, quyết định đó có thể cần được **quản lý như nợ**. Vẫn phải theo dõi riêng mức độ ảnh hưởng của bug, nhất là khi liên quan dữ liệu, tiền hoặc bảo mật.

## 5. Quy trình phân loại khi review hoặc nhận cảnh báo

Khi gặp vấn đề trong mã, hãy theo thứ tự sau:

**Bước 1 — Xác định hành vi và nguồn yêu cầu.** Mô tả đầu vào, đầu ra, quy tắc nghiệp vụ, hợp đồng API hoặc yêu cầu phi chức năng. Nếu có chênh lệch kiểm chứng được, ghi nhận **bug** kèm ca tái hiện. Khi đặc tả chưa rõ, hỏi người chịu trách nhiệm nghiệp vụ trước khi khẳng định kết quả là sai.

**Bước 2 — Đánh giá khả năng đọc và thay đổi.** Nếu mã đang đúng nhưng phải hiểu nhiều điều kiện ngầm, có trách nhiệm trộn lẫn hoặc khó kiểm thử, ghi nhận **code smell**. Mô tả khó khăn cụ thể thay vì chỉ ghi “code xấu”.

**Bước 3 — Đối chiếu quy ước dự án.** Nếu có quy định rõ ràng bị vi phạm, ghi nhận **convention violation**, dẫn quy tắc và ưu tiên formatter/linter. Tránh biến ý kiến chủ quan thành quy ước bắt buộc.

**Bước 4 — Xem xét chi phí tích lũy.** Hỏi vì sao thiết kế hiện tại tồn tại, sửa ở đây kéo theo bao nhiêu nơi, tần suất thay đổi ra sao và rủi ro nếu tiếp tục trì hoãn. Khi chi phí tương lai rõ ràng, ghi nhận **technical debt** cùng tác động và cách xử lý dự kiến.

**Bước 5 — Ghi nhận nhiều nhãn nếu thực sự có nhiều vấn đề.** Ví dụ “bug ở điều kiện biên” cần sửa ngay và “nợ do chính sách bị nhân bản” cần một đầu việc riêng. Không dùng một nhãn duy nhất để che khuất các tác động khác nhau.

Có thể ghi một phát hiện theo mẫu ngắn: **Hiện tượng → Bằng chứng → Tác động → Cách xử lý → Điều kiện hoàn tất**. Ví dụ: “Bug phí vận chuyển tại 500.000 VND → test ngưỡng trả 30.000 thay vì 0 → thu phí sai → đổi > thành >= và thêm test → test biên qua”.

## 6. Ưu tiên xử lý theo tác động, không theo nhãn

| Tình huống | Ưu tiên gợi ý | Lý do và hành động |
| --- | --- | --- |
| Bug làm sai số tiền, mất dữ liệu hoặc mở lỗ hổng | Rất cao | Hạn chế tác động, sửa nguyên nhân, kiểm thử và theo dõi sau phát hành |
| Bug hiếm gặp, ảnh hưởng nhỏ, có cách khắc phục tạm | Theo rủi ro thực tế | Xem tần suất, phạm vi và chi phí trì hoãn |
| Code smell tại vùng mã thường xuyên thay đổi | Cao khi chuẩn bị sửa vùng đó | Refactor từng bước, bảo vệ hành vi bằng kiểm thử |
| Code smell ở mã ổn định, ít phải đụng đến | Có thể theo dõi | Tránh refactor lớn khi chưa có lợi ích đủ rõ |
| Vi phạm format có thể tự sửa và ít rủi ro | Xử lý tự động qua công cụ/CI | Giảm tranh luận thủ công, giữ codebase nhất quán |
| Nợ kỹ thuật khiến mỗi thay đổi phải sửa nhiều nơi | Cao nếu “lãi” tăng nhanh | Ước lượng chi phí, xác định thời điểm trả nợ và người phụ trách |

Một mô hình ưu tiên thực dụng là xem xét **mức ảnh hưởng × khả năng xảy ra × phạm vi lan rộng**, sau đó cân nhắc công sức sửa và nguy cơ gây hồi quy. Không có thứ tự tuyệt đối kiểu “mọi bug luôn ưu tiên trước mọi khoản nợ”: một khoản nợ làm chậm mọi đợt phát hành có thể đáng xử lý trước một bug giao diện rất nhỏ.

## 7. Những nhầm lẫn thường gặp

**“Linter không báo gì thì không có vấn đề chất lượng.”** Sai. Linter phát hiện được một tập quy tắc nhất định; nó không chứng minh chương trình đúng nghiệp vụ hoặc kiến trúc dễ bảo trì.

**“Có code smell tức là phải refactor ngay.”** Chưa chắc. Cần đánh giá bối cảnh, tần suất thay đổi, lợi ích so với nguy cơ và mức kiểm thử hiện có.

**“Mã chạy đúng thì không có nợ kỹ thuật.”** Sai. Nợ kỹ thuật thường biểu hiện rõ nhất khi cần bổ sung tính năng, sửa đổi hoặc vận hành, ngay cả khi chức năng hiện tại vẫn đúng.

**“Vi phạm quy ước là lỗi chức năng.”** Không mặc nhiên. Đặt tên sai quy ước thường không làm thay đổi kết quả chạy, dù có thể gây khó bảo trì hoặc làm build thất bại nếu CI áp dụng rule bắt buộc.

**“Sửa được bug nghĩa là đã trả hết nợ.”** Không nhất thiết. Sửa điều kiện biên trong một bản sao không giải quyết vấn đề cùng logic xuất hiện ở nhiều dịch vụ.

**“Nợ kỹ thuật luôn do lập trình viên làm ẩu.”** Không đúng. Nợ còn xuất hiện do thay đổi mục tiêu sản phẩm, giới hạn thời gian, sự phụ thuộc công nghệ và hiểu biết tăng lên. Điều quan trọng là làm rõ tác động và quản lý minh bạch.

## 8. Nguyên tắc áp dụng trong dự án

Khi đánh giá mã nguồn, nên kết hợp bốn nhóm bằng chứng:

1. **Tính đúng đắn:** yêu cầu, ca kiểm thử, dữ liệu thực tế, điều kiện biên.
2. **Tính dễ hiểu:** trách nhiệm rõ, tên có ý nghĩa, cấu trúc hợp lý, phụ thuộc có kiểm soát.
3. **Tính nhất quán:** chuẩn code style đã thống nhất, formatter, linter và quy trình review.
4. **Tính dễ thay đổi lâu dài:** số nơi phải sửa, chi phí kiểm thử, rủi ro hồi quy và các quyết định kỹ thuật còn tồn đọng.

Với bất kỳ phát hiện nào, hãy diễn đạt **điều gì xảy ra, bằng chứng ở đâu và vì sao cần sửa**. Cách làm này giúp tránh tranh luận cảm tính, chọn đúng biện pháp và giữ trọng tâm của chất lượng mã: **đáng tin cậy khi chạy, dễ hiểu khi đọc và dễ thay đổi khi yêu cầu phát triển**.
