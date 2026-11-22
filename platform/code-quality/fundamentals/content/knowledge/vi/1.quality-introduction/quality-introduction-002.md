# Một đoạn mã chạy đúng đã đủ tốt chưa?

Giả sử bạn viết xong một chức năng, chạy thử vài lần và thấy kết quả đúng. Bạn có thể tự tin rằng công việc đã hoàn tất chưa? **Chưa hẳn.** Chạy đúng là điều kiện quan trọng đầu tiên, nhưng một phần mềm còn phải được đọc hiểu, kiểm thử, sửa lỗi, mở rộng và vận hành trong suốt thời gian tồn tại của nó.

Trong phần nhập môn về **chất lượng mã nguồn (code quality)**, chúng ta sẽ xem vì sao “chạy được” và “đủ tốt để sử dụng, bảo trì” là hai mức đánh giá khác nhau. Mục tiêu không phải biến mọi đoạn mã thành một tác phẩm hoàn hảo, mà là biết nhận diện rủi ro và đầu tư công sức cải thiện đúng chỗ.

## 1. “Chạy đúng” thực sự có nghĩa là gì?

Một chương trình được xem là **đúng về chức năng** khi hành vi của nó phù hợp với yêu cầu đã xác định, với những đầu vào và điều kiện mà yêu cầu đó bao phủ.

Ví dụ, một cửa hàng có quy tắc tính phí giao hàng như sau:

- Khách hàng VIP được miễn phí giao hàng.
- Khách thường có đơn hàng từ **300.000 đồng** trở lên được miễn phí giao hàng.
- Những đơn hàng hợp lệ còn lại chịu phí **30.000 đồng**.

Nếu chương trình cho kết quả `30_000` với đơn hàng thường trị giá `250_000` đồng và `0` với đơn hàng thường trị giá `350_000` đồng, đó là tín hiệu tốt. Tuy nhiên, hai lần thử này chưa chứng minh chương trình đáp ứng **mọi** trường hợp thuộc yêu cầu. Điều gì xảy ra khi đơn hàng đúng `300_000` đồng? Khách VIP mua một món hàng rất rẻ thì sao? Nếu dữ liệu đơn hàng bị âm, hệ thống có chấp nhận không?

Điều cần phân biệt:

| Khái niệm | Câu hỏi cần trả lời |
| --- | --- |
| **Chạy được** | Chương trình có biên dịch, khởi động và thực thi được không? |
| **Đúng với ví dụ thử** | Một vài đầu vào đã thử có cho kết quả mong đợi không? |
| **Đúng theo yêu cầu** | Các trường hợp hợp lệ, điều kiện biên và quy tắc nghiệp vụ có được xử lý đúng không? |
| **Có chất lượng tốt** | Ngoài tính đúng, mã có đủ dễ hiểu, dễ thay đổi, dễ kiểm chứng và an toàn để sử dụng trong bối cảnh thực tế không? |

**Một lần chạy thành công không phải là bằng chứng rằng không còn lỗi.** Kiểm thử giúp tăng mức tin cậy, nhưng chỉ kiểm tra được những trường hợp và thuộc tính mà ta đã thiết kế để kiểm tra.

## 2. Vì sao mã chạy đúng vẫn có thể gây vấn đề?

Hãy hình dung sau khi chức năng giao hàng được đưa vào sử dụng, cửa hàng đổi ngưỡng miễn phí từ 300.000 lên 350.000 đồng. Một đồng nghiệp cần tìm nơi chứa quy tắc đó, sửa chương trình và đảm bảo không ảnh hưởng đến ưu đãi VIP. Nếu các con số xuất hiện rải rác, tên biến khó hiểu và logic lồng nhau nhiều tầng, việc thay đổi nhỏ có thể trở nên tốn thời gian, dễ sai sót.

Những vấn đề phổ biến gồm:

1. **Khó đọc:** Người khác không nhận ra ngay đoạn mã đang thực hiện quy tắc nào, phải đọc từng nhánh để đoán ý định.
2. **Khó thay đổi:** Một quy tắc bị sao chép ở nhiều nơi; sửa sót một chỗ có thể tạo ra kết quả không nhất quán.
3. **Khó kiểm thử:** Mã phụ thuộc quá nhiều vào cơ sở dữ liệu, thời gian hệ thống hoặc trạng thái toàn cục khiến các ca kiểm thử khó cô lập.
4. **Dễ lỗi khi gặp dữ liệu bất thường:** Chương trình hoạt động ở đường đi quen thuộc nhưng không xử lý rõ dữ liệu thiếu, sai định dạng, giá trị biên hay lỗi từ dịch vụ khác.
5. **Khó vận hành:** Khi xảy ra lỗi, thiếu thông tin chẩn đoán hoặc cách xử lý phù hợp khiến thời gian khắc phục kéo dài.
6. **Có rủi ro bảo mật hoặc hiệu năng:** Chương trình trả kết quả đúng trong thử nghiệm nhỏ nhưng để lộ dữ liệu nhạy cảm, tiêu tốn quá nhiều tài nguyên hoặc quá chậm khi tải tăng.

Chi phí lớn nhất của mã kém chất lượng đôi khi **không xuất hiện vào ngày viết mã**. Nó xuất hiện trong những tháng tiếp theo, khi nhóm phải sửa lỗi, bổ sung tính năng và bàn giao cho người mới.

## 3. Ví dụ Java: cùng kết quả, khác khả năng bảo trì

Xét chức năng tính phí giao hàng theo quy tắc ở mục 1. Trong ví dụ này, giả sử `orderTotalVnd` luôn là số nguyên không âm do tầng tiếp nhận dữ liệu đã kiểm tra. Chúng ta tập trung vào chất lượng cấu trúc mã mà không thay đổi quy tắc nghiệp vụ.

### Phiên bản A: chạy đúng nhưng khó đọc hơn cần thiết

```java
public final class ShippingFeeCalculator {
    public static int fee(int a, boolean b) {
        int result = 30_000;

        if (b == true) {
            result = 0;
        } else {
            if (a >= 300_000) {
                result = 0;
            }
        }

        return result;
    }
}
```

Với các đầu vào hợp lệ, phương thức trên có thể cho kết quả đúng. Nhưng người đọc phải tự trả lời: `a` là gì, `b` biểu thị điều gì, vì sao dùng `300_000`, và `30_000` có ý nghĩa nào? Các câu lệnh `if` lồng nhau cũng làm việc nhận ra quy tắc miễn phí giao hàng trở nên chậm hơn.

Đây chưa phải một lỗi chức năng. Đây là **chi phí đọc hiểu và nguy cơ sai sót khi bảo trì**.

### Phiên bản B: diễn đạt rõ ý định

```java
public final class ShippingFeeCalculator {
    private static final int FREE_SHIPPING_THRESHOLD_VND = 300_000;
    private static final int STANDARD_SHIPPING_FEE_VND = 30_000;

    public static int calculateFee(int orderTotalVnd, boolean isVipCustomer) {
        boolean qualifiesForFreeShipping =
                isVipCustomer || orderTotalVnd >= FREE_SHIPPING_THRESHOLD_VND;

        if (qualifiesForFreeShipping) {
            return 0;
        }

        return STANDARD_SHIPPING_FEE_VND;
    }
}
```

Các cải thiện có thể quan sát được:

- **Tên biểu thị ý nghĩa:** `orderTotalVnd`, `isVipCustomer` và `calculateFee` mô tả dữ liệu và mục đích xử lý.
- **Hằng số có tên:** Người bảo trì biết `300_000` là ngưỡng miễn phí và `30_000` là phí tiêu chuẩn. Đơn vị `VND` tránh nhầm lẫn với loại tiền khác.
- **Điều kiện dễ đọc:** Biến `qualifiesForFreeShipping` diễn đạt trực tiếp quy tắc nghiệp vụ.
- **Luồng xử lý đơn giản:** Trường hợp miễn phí được trả về ngay, giảm nhánh lồng nhau và trạng thái `result` trung gian.

Hai phiên bản là **hai cách triển khai thay thế nhau**, không phải hai lớp cần đặt cùng một dự án. Với hợp đồng đầu vào đã nêu, chúng có cùng kết quả tính phí. Việc thay đổi cách tổ chức mã nhưng vẫn giữ nguyên hành vi quan sát được được gọi là **refactoring (tái cấu trúc mã)**.

> Refactoring làm cho mã dễ hiểu hoặc dễ bảo trì hơn mà không chủ đích thay đổi chức năng. Nếu thêm quy tắc từ chối đơn hàng âm, tính năng sẽ có hành vi mới; hãy xem đó là thay đổi yêu cầu hoặc sửa lỗi cần kiểm thử riêng, thay vì mặc nhiên coi là refactoring thuần túy.

### Kiểm thử hành vi trước và sau khi cải thiện

Một bộ kiểm thử nhỏ có thể ghi lại những ví dụ quan trọng của hợp đồng tính phí:

```java
import static org.junit.jupiter.api.Assertions.assertEquals;

import org.junit.jupiter.api.Test;

class ShippingFeeCalculatorTest {
    @Test
    void calculatesFeeAtImportantBoundaries() {
        assertEquals(30_000, ShippingFeeCalculator.calculateFee(299_999, false));
        assertEquals(0, ShippingFeeCalculator.calculateFee(300_000, false));
        assertEquals(0, ShippingFeeCalculator.calculateFee(300_001, false));
        assertEquals(0, ShippingFeeCalculator.calculateFee(10_000, true));
    }
}
```

Đoạn kiểm thử trên dùng **JUnit 5** và áp dụng cho phiên bản B. Nếu muốn dùng cùng các ca kiểm thử cho phiên bản A, cần đổi tên phương thức gọi từ `calculateFee` thành `fee`. Các giá trị **ngay dưới, đúng bằng và ngay trên ngưỡng** giúp kiểm tra lỗi thường gặp giữa `>` và `>=`. Trường hợp VIP xác nhận rằng tư cách khách hàng có thể quyết định miễn phí dù tổng tiền chưa đạt ngưỡng.

Bộ kiểm thử này vẫn chưa thể khẳng định chương trình hoàn toàn đúng: nó chưa kiểm tra đầu vào không hợp lệ hay các quy tắc có thể được bổ sung sau này. Khi yêu cầu nói rõ dữ liệu âm phải bị từ chối, cần bổ sung kiểm tra đầu vào cùng ca kiểm thử tương ứng.

## 4. Các khía cạnh tạo nên chất lượng mã

Không có một chỉ số duy nhất đo trọn vẹn chất lượng mã nguồn. Tùy hệ thống, nhóm phát triển cần cân nhắc nhiều khía cạnh:

| Khía cạnh | Dấu hiệu tích cực | Điều cần tránh |
| --- | --- | --- |
| **Tính đúng (correctness)** | Hành vi phù hợp yêu cầu; trường hợp biên được xem xét | Chỉ thử “đường đi đẹp” rồi kết luận đúng hoàn toàn |
| **Dễ đọc (readability)** | Tên rõ nghĩa, luồng xử lý mạch lạc, quy tắc dễ tìm | Tên mơ hồ, biểu thức rối, lạm dụng viết tắt |
| **Dễ bảo trì (maintainability)** | Thay đổi một quy tắc ở ít nơi, phạm vi ảnh hưởng dễ dự đoán | Trùng lặp logic và phụ thuộc chằng chịt |
| **Dễ kiểm thử (testability)** | Thành phần có đầu vào, đầu ra và phụ thuộc rõ ràng | Phụ thuộc ngầm vào trạng thái toàn cục hoặc môi trường |
| **Độ tin cậy (reliability)** | Xử lý lỗi hợp lý, giải phóng tài nguyên, phục hồi phù hợp | Giả định mọi kết nối và thao tác luôn thành công |
| **Bảo mật (security)** | Kiểm tra dữ liệu đầu vào, kiểm soát quyền truy cập, bảo vệ bí mật | Ghép dữ liệu thẳng vào câu lệnh SQL, ghi mật khẩu vào log |
| **Hiệu năng (performance)** | Đáp ứng mục tiêu về tốc độ và tài nguyên với tải dự kiến | Chỉ tối ưu theo cảm giác hoặc bỏ qua điểm nghẽn đã đo được |
| **Tính nhất quán (consistency)** | Tuân theo quy ước chung của dự án, dễ phối hợp nhóm | Mỗi file dùng một cách đặt tên hoặc xử lý lỗi khác nhau |

Các khía cạnh có liên hệ với nhau nhưng **không hoàn toàn đồng nhất**. Mã viết ngắn chưa chắc dễ hiểu; mã có nhiều lớp trừu tượng chưa chắc dễ bảo trì; mã vượt qua toàn bộ bài kiểm thử hiện có cũng chưa chắc an toàn. Cách đánh giá phải gắn với bối cảnh sử dụng và rủi ro thực tế.

### Chất lượng không đồng nghĩa với viết càng nhiều mã càng tốt

Trong ví dụ giao hàng, tách mỗi điều kiện thành một lớp, xây dựng nhiều interface và tạo một hệ thống cấu hình phức tạp có thể làm mã **khó theo dõi hơn**, dù trông có vẻ “kiến trúc”. Mức tổ chức hợp lý phải tương xứng với vấn đề đang giải quyết.

Một cải thiện đáng làm thường giúp người tiếp theo trả lời nhanh ba câu hỏi: **Mã này làm gì? Vì sao có quy tắc này? Nếu yêu cầu thay đổi thì cần sửa ở đâu?**

## 5. Khi nào có thể nói mã đã “đủ tốt”?

“Đủ tốt” không phải một trạng thái tuyệt đối. Một chương trình học tập chạy với dữ liệu mẫu và một dịch vụ xử lý thanh toán cho hàng nghìn người dùng cần mức kiểm chứng khác nhau. Thời gian, độ phức tạp, mức độ ảnh hưởng khi xảy ra lỗi và khả năng thay đổi yêu cầu đều quyết định mức đầu tư hợp lý.

Trước khi hoàn tất một chức năng, hãy tự rà soát theo trình tự sau:

1. **Đối chiếu yêu cầu:** Có thể mô tả rõ đầu vào, đầu ra và các quy tắc mà mã phải thực hiện không? Những giả định nào đã được xác nhận?
2. **Xem trường hợp biên và lỗi:** Đã nghĩ đến giá trị ngay tại ngưỡng, dữ liệu trống, dữ liệu sai và lỗi của các hệ thống phụ thuộc chưa?
3. **Kiểm tra bằng bằng chứng:** Đã có các ca kiểm thử phù hợp hoặc cách kiểm chứng đáng tin cậy cho những hành vi quan trọng chưa?
4. **Đọc lại như một người mới:** Tên và cấu trúc có giúp hiểu ý định mà không phải đoán không? Có phần trùng lặp hoặc nhánh phức tạp nào nên đơn giản hóa không?
5. **Xem xét rủi ro vận hành:** Có dữ liệu nhạy cảm, quyền truy cập, thao tác tốn tài nguyên hoặc lỗi cần xử lý đặc biệt không?
6. **Cân nhắc phạm vi cải thiện:** Việc đổi cấu trúc có tạo ra lợi ích rõ ràng hơn chi phí và nguy cơ phát sinh lỗi hay không?

Nếu gặp vấn đề, hãy ưu tiên **tính đúng và rủi ro lớn trước**, sau đó mới cải thiện khả năng đọc và bảo trì phù hợp với phạm vi thay đổi. Đừng dành hàng giờ để tối ưu vài phần nghìn giây khi chưa đo hiệu năng, và cũng đừng để một lỗi bảo mật rõ ràng tồn tại chỉ vì chương trình vẫn chạy đúng ở môi trường thử nghiệm.

### Một tình huống thực tế

Giả sử nhóm phát hiện hai vấn đề trong cùng một đợt rà soát:

- **Vấn đề A:** Tên phương thức `processData()` quá chung chung, nhưng đoạn mã chỉ dài năm dòng, có kiểm thử và ít được thay đổi.
- **Vấn đề B:** Một truy vấn SQL ghép trực tiếp dữ liệu nhập từ người dùng vào chuỗi lệnh, dù kết quả tìm kiếm hiện đang đúng.

Vấn đề B cần được ưu tiên vì có thể gây ra **SQL injection** và tác động đến dữ liệu. Vấn đề A đáng cải thiện khi chạm vào đoạn mã liên quan, nhưng thường có rủi ro thấp hơn. Chất lượng mã vì thế gắn với **khả năng đưa ra quyết định kỹ thuật có cân nhắc**, không chỉ là việc chấm điểm hình thức.

## 6. Tự kiểm tra hiểu bài

**Câu 1.** Phương thức tính phí giao hàng trả kết quả đúng cho hai đơn hàng mẫu. Có thể kết luận chức năng đã đúng theo toàn bộ yêu cầu chưa?

*Gợi ý trả lời:* Chưa. Cần kiểm tra thêm điều kiện VIP, ngưỡng đúng bằng 300.000 đồng, các trường hợp biên và hợp đồng đầu vào.

**Câu 2.** Đổi tên `a` thành `orderTotalVnd` và thay `300_000` bằng hằng số có tên đem lại lợi ích gì nếu kết quả không đổi?

*Gợi ý trả lời:* Mã thể hiện ý nghĩa nghiệp vụ rõ hơn, giảm thời gian đọc hiểu và giúp người bảo trì nhận diện đúng vị trí cần sửa khi quy tắc thay đổi.

**Câu 3.** Nếu một đoạn mã đã dễ đọc nhưng thỉnh thoảng làm lộ thông tin nhạy cảm trong log, có thể xem là chất lượng tốt không?

*Gợi ý trả lời:* Không. Dễ đọc chỉ là một khía cạnh; bảo mật và độ tin cậy cũng là những yêu cầu quan trọng.

## Ghi nhớ

**Chạy đúng là điều kiện cần, nhưng chưa đủ để kết luận mã có chất lượng tốt.** Hãy đánh giá một đoạn mã theo khả năng đáp ứng yêu cầu, xử lý trường hợp biên, được kiểm chứng, được đọc hiểu, thay đổi an toàn và vận hành phù hợp. Mục tiêu của code quality là giúp phần mềm **tiếp tục hoạt động đáng tin cậy khi con người và yêu cầu thay đổi**, với mức đầu tư tương xứng với rủi ro của hệ thống.
