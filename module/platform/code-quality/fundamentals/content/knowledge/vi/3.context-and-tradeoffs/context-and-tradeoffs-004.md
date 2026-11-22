# Tần suất thay đổi và số người cùng bảo trì

Trong chương **Bối cảnh và đánh đổi** của module **CODE_QUALITY_FUNDAMENTALS**, ta xem xét vì sao cùng một cách viết mã có thể phù hợp với dự án này nhưng lại tạo gánh nặng cho dự án khác. Mục tiêu của module là hiểu những thuộc tính quyết định mã nguồn có **đáng tin cậy, dễ hiểu và dễ thay đổi** hay không. Hai yếu tố bối cảnh tác động trực tiếp đến lựa chọn thiết kế là **tần suất mã phải thay đổi** và **số người cần cùng hiểu, sửa, kiểm thử, vận hành hoặc bàn giao mã đó**.

Một đoạn mã chỉ được sửa vài lần trong nhiều năm có thể không cần nhiều tầng trừu tượng. Nhưng nếu chính đoạn mã ấy phải đổi quy tắc mỗi tuần và nhiều nhóm cùng phụ thuộc vào nó, chi phí hiểu mã, phối hợp và xác minh thay đổi có thể lớn hơn nhiều so với thời gian gõ vài dòng lệnh.

**Thông điệp chính:** đừng đánh giá chất lượng mã chỉ theo vẻ đẹp của cấu trúc hiện tại. Hãy đánh giá **chi phí thay đổi có thể dự đoán được trong bối cảnh sử dụng thực tế**, bao gồm cả người sẽ thay đổi mã trong tương lai.

## 1. Mục tiêu học tập

Sau bài này, người học có thể:

1. Giải thích vì sao tần suất thay đổi làm thay đổi giá trị của tính dễ hiểu, khả năng kiểm thử và tính linh hoạt.
2. Phân biệt số người có thể đọc mã với số người thật sự cùng bảo trì hoặc phụ thuộc vào mã.
3. Phân tích bốn tình huống khi hai yếu tố “ít/nhiều thay đổi” và “ít/nhiều người bảo trì” kết hợp.
4. Quyết định khi nào nên giữ giải pháp trực tiếp, khi nào nên tách quy tắc, tạo hợp đồng hay bổ sung tài liệu.
5. Đánh giá lợi ích và chi phí của các biện pháp như code review, kiểm thử hồi quy, cấu hình, module ownership và tự động hóa.
6. Dùng dấu hiệu thực tế từ lịch sử sửa mã để điều chỉnh quyết định, tránh thiết kế quá mức dựa trên giả định.

## 2. Vì sao hai yếu tố này quan trọng?

### 2.1. Tần suất thay đổi làm lặp lại chi phí bảo trì

Mỗi lần thay đổi mã thường bao gồm nhiều hoạt động hơn việc sửa một dòng lệnh:

~~~text
Hiểu yêu cầu
    ↓
Đọc và hiểu mã hiện tại
    ↓
Chọn vị trí và cách sửa
    ↓
Sửa mã, dữ liệu hoặc cấu hình
    ↓
Kiểm thử và xác minh tác động
    ↓
Review, tích hợp, triển khai
    ↓
Theo dõi và xử lý vấn đề nếu có
~~~

Với một mô hình suy nghĩ đơn giản, có thể hình dung:

**Tổng công sức trong một giai đoạn ≈ chi phí thiết kế ban đầu + số lần thay đổi × chi phí trung bình mỗi lần thay đổi + chi phí vận hành phát sinh.**

Đây là **mô hình định tính để so sánh phương án**, không phải công thức định lượng chính xác: các lần thay đổi có độ khó khác nhau, việc đầu tư thiết kế ban đầu cũng có thể làm giảm hoặc tăng chi phí ở những lần sau.

Ví dụ minh họa:

- Phương án A mất 1 giờ để xây dựng, mỗi yêu cầu sửa mất khoảng 2 giờ.
- Phương án B mất 5 giờ để xây dựng, mỗi yêu cầu sửa mất khoảng 30 phút.
- Nếu chỉ có một lần sửa tương tự, A có thể kinh tế hơn; nếu có 10 lần sửa tương tự, tổng công sức ước tính của B thấp hơn.

Những con số này chỉ giúp thấy **điểm hòa vốn của việc đầu tư vào khả năng thay đổi**. Không nên suy ra mọi trường hợp “thay đổi nhiều” đều cần thêm abstraction; có những quy tắc thay đổi thường xuyên nhưng chỉ cần thay một giá trị cấu hình.

### 2.2. Nhiều người bảo trì làm tăng chi phí truyền đạt và phối hợp

Khi người viết mã đồng thời là người duy nhất đọc và sửa nó, một số ngữ cảnh có thể còn nằm trong trí nhớ cá nhân. Khi nhiều người tham gia, **ngữ cảnh ngầm trở thành rủi ro**:

- Người mới không biết vì sao một nhánh điều kiện phải chạy trước nhánh khác.
- Hai nhóm sửa cùng một module trong những nhánh phát triển khác nhau, gây xung đột hoặc làm sai giả định của nhau.
- Một thay đổi ở API nội bộ làm hỏng bên sử dụng mà người sửa không biết.
- Một cá nhân hiểu toàn bộ quy tắc; khi người đó vắng mặt, sửa lỗi bị trì hoãn.

Do đó, càng nhiều người phải bảo trì, ta càng hưởng lợi từ **tên rõ nghĩa, hợp đồng hành vi rõ ràng, kiểm thử dễ chạy, tài liệu đúng chỗ và cơ chế review hợp lý**.

Tuy nhiên, thêm người không tự động có nghĩa là thêm chi phí theo tỷ lệ cố định. Một nhóm biết rõ phạm vi trách nhiệm, có giao diện ổn định và công cụ tự động tốt vẫn có thể phối hợp hiệu quả.

### 2.3. Hai yếu tố có thể tác động qua lại

Mã đổi thường xuyên **và** nhiều người cùng sửa dễ trở thành điểm xung đột. Cùng một hàm bị sửa ở nhiều pull request có thể làm review chậm, tăng nguy cơ merge conflict và khiến các quyết định cục bộ thiếu nhất quán.

Ngược lại, mã rất ít đổi nhưng được nhiều nhóm sử dụng vẫn có rủi ro lớn: một lần đổi hiếm hoi có thể gây lỗi tương thích rộng. Vì vậy, cần xem **mức độ phụ thuộc** và **mức độ quan trọng của hành vi**, chứ không chỉ đếm số lần commit.

## 3. Đánh giá đúng hai trục bối cảnh

### 3.1. “Tần suất thay đổi” là tần suất nào?

Có thể phân biệt ba dạng thay đổi:

| Dạng thay đổi | Ví dụ | Hàm ý thiết kế |
| --- | --- | --- |
| **Thay đổi dữ liệu hoặc tham số** | Ngưỡng miễn phí vận chuyển đổi theo chương trình bán hàng. | Có thể cân nhắc cấu hình có kiểm tra hợp lệ và quy trình cập nhật rõ ràng. |
| **Thay đổi quy tắc nghiệp vụ** | Từ ngưỡng chung chuyển sang ngưỡng theo khu vực, hạng khách hàng. | Cần điểm chứa quy tắc rõ ràng, test cho trường hợp biên; có thể tách chính sách khi xuất hiện nhiều biến thể thật. |
| **Thay đổi hợp đồng hoặc tích hợp** | API đổi định dạng dữ liệu; service thanh toán mới. | Cần quản lý tương thích, versioning khi phù hợp, kiểm thử contract và phối hợp nhóm liên quan. |

Một file bị sửa nhiều do đổi định dạng, tự động sinh mã hoặc cập nhật comment chưa chắc chứa nghiệp vụ biến động cao. Ngược lại, một module chỉ có hai lần sửa nhưng cả hai lần đều gây sự cố nghiêm trọng vẫn đáng được đầu tư.

Hãy xem **mức độ thay đổi có ý nghĩa**, **mức độ khó dự đoán** và **hậu quả khi sửa sai**.

### 3.2. “Số người cùng bảo trì” là những ai?

Không nên lấy tổng số lập trình viên trong công ty làm đại diện. Với một module cụ thể, hãy xác định:

- Ai trực tiếp sửa mã và giải quyết sự cố?
- Ai review, kiểm thử, triển khai và chịu trách nhiệm vận hành?
- Bao nhiêu nhóm gọi API hoặc phụ thuộc vào dữ liệu của module?
- Ai sẽ nhận bàn giao khi chủ sở hữu hiện tại thay đổi?
- Quy tắc nghiệp vụ có được người bên ngoài nhóm phát triển cập nhật hay không?

Một module do hai người sửa nhưng được mười nhóm gọi có **ít người sửa trực tiếp nhưng phạm vi ảnh hưởng rộng**. Module đó vẫn cần hợp đồng và chiến lược tương thích đủ rõ.

**Bus factor** thường được dùng để nói về mức độ phụ thuộc kiến thức vào một số rất ít người. Số người từng commit không tự động đo được bus factor: một kho mã có 20 người đóng góp vẫn có thể chỉ một người hiểu các quyết định khó nhất.

### 3.3. Cách thu thập dấu hiệu thực tế

Trong phạm vi module cần đánh giá, có thể xem:

1. Lịch sử sửa đổi: phần nào thường thay đổi, lý do trong issue/PR là gì?
2. Sự cố và sửa lỗi hồi quy: lần sửa trước đã ảnh hưởng các thành phần khác thế nào?
3. Tần suất phát hành và tốc độ biến động yêu cầu: có chiến dịch hay luật nghiệp vụ đổi định kỳ không?
4. Hoạt động review: PR có thường phải đợi cùng một người giải thích hoặc phê duyệt không?
5. Mối quan hệ phụ thuộc: bao nhiêu người dùng và service bị ảnh hưởng nếu thay đổi hợp đồng?

Đừng dùng một chỉ số riêng lẻ làm “điểm chất lượng”. Số commit lớn có thể là dấu hiệu hoạt động lành mạnh; số commit nhỏ cũng có thể che giấu mã khó sửa vì mọi người ngại chạm vào.

## 4. Ma trận bốn bối cảnh bảo trì

Bảng sau là **gợi ý bắt đầu thảo luận**, không phải quy tắc cứng. “Ít” và “nhiều” luôn được xác định tương đối theo phạm vi dự án và chu kỳ phát triển.

| | **Ít người trực tiếp bảo trì** | **Nhiều người cùng bảo trì / nhiều nhóm phụ thuộc** |
| --- | --- | --- |
| **Ít thay đổi** | **Giữ đơn giản.** Ưu tiên luồng rõ ràng, chú giải những giả định khó hiểu, test tối thiểu theo rủi ro. Không tự tạo framework chỉ để “phòng sau này”. | **Ổn định và dễ bàn giao.** Ghi rõ hợp đồng, bất biến quan trọng, trách nhiệm sở hữu và cách kiểm tra tương thích khi hiếm khi phải sửa. |
| **Thay đổi thường xuyên** | **Tối ưu vòng lặp sửa–kiểm tra.** Cô lập các quy tắc hay đổi, tăng test tự động cho những nhánh thường chạm tới, giữ thao tác cập nhật gọn. | **Giảm chi phí phối hợp.** Thiết kế ranh giới rõ ràng, ưu tiên thay đổi nhỏ, quy ước review, kiểm thử CI, quản lý hợp đồng và tài liệu quyết định quan trọng. |

### 4.1. Ít thay đổi, ít người bảo trì

Ví dụ: một công cụ nội bộ chạy theo lịch, chỉ một hoặc hai người quản lý và quy tắc hầu như cố định.

Một hàm ngắn, mạch lạc, với kiểm thử cho trường hợp rủi ro cao có thể đủ tốt. Việc thêm interface cho từng class, hệ thống plugin, hoặc quy trình phê duyệt nhiều tầng có thể làm tổng chi phí tăng mà chưa có lợi ích tương ứng.

**Ngoại lệ quan trọng:** nếu công cụ xử lý tiền, quyền truy cập hoặc dữ liệu quan trọng, tần suất thay đổi thấp không phải lý do bỏ qua kiểm tra tính đúng đắn và khả năng khôi phục.

### 4.2. Thay đổi nhiều, ít người bảo trì

Ví dụ: một nhóm nhỏ liên tục chỉnh logic tính ưu đãi để thử nghiệm sản phẩm.

Độ rõ ràng của quy tắc, kiểm thử nhanh và khả năng thay đổi riêng từng chính sách quan trọng hơn hệ thống quy trình nặng. Nếu nhiều phiên bản chính sách thực sự đã xuất hiện, có thể tách chính sách thành thành phần riêng; nếu chỉ đổi một con số, cấu hình đơn giản có thể đủ.

Cần ghi lại những quyết định không hiển nhiên để tránh tình trạng “một người duy nhất biết vì sao”, kể cả khi hiện tại nhóm rất nhỏ.

### 4.3. Ít thay đổi, nhiều người bảo trì hoặc phụ thuộc

Ví dụ: thư viện mã hóa mã đơn hàng gần như không đổi nhưng được nhiều service sử dụng.

Điểm quan trọng là **khả năng dự đoán và tương thích**. Một lần thay đổi hành vi trả về, quy tắc chuẩn hóa hoặc định dạng lỗi có thể ảnh hưởng hàng loạt bên gọi. Tài liệu giao diện, test đặc tả và cơ chế công bố thay đổi thường giá trị hơn việc tạo nhiều tầng trừu tượng cho phần lõi ổn định.

Với hệ thống có hợp đồng bên ngoài, cần phân biệt sửa nội bộ không làm đổi hành vi và thay đổi tương thích ngược.

### 4.4. Thay đổi nhiều, nhiều người bảo trì hoặc phụ thuộc

Ví dụ: tính phí giao hàng được cập nhật thường xuyên và được sử dụng bởi giỏ hàng, thanh toán, ứng dụng di động và báo cáo.

Thiết kế nên giúp phân biệt rõ: **điều gì được phép thay đổi độc lập**, **điều gì là hợp đồng phải giữ ổn định**, **ai phê duyệt thay đổi có rủi ro**, và **bằng chứng nào cần có trước khi phát hành**.

Ở đây các biện pháp như API rõ ràng, kiểm thử tự động và thay đổi nhỏ thường đáng đầu tư. Nhưng vẫn phải tránh “tách microservice cho mọi quy tắc”: ranh giới mạng và triển khai độc lập cũng tạo thêm độ phức tạp, chi phí quan sát và rủi ro vận hành.

## 5. Ví dụ Java: khi quy tắc phí vận chuyển thay đổi theo thời gian

Giả sử cửa hàng có chính sách: **giỏ hàng từ 500.000 đơn vị tiền nhỏ nhất trở lên được miễn phí vận chuyển; giỏ thấp hơn chịu phí 30.000**. Để đơn giản, ví dụ giả định đơn hàng không có số tiền âm và quy tắc áp dụng chung cho mọi khách hàng.

### 5.1. Khi chính sách ổn định, cách viết trực tiếp có thể hợp lý

~~~java
final class ShippingFeeCalculator {
    int calculate(int subtotalCents) {
        if (subtotalCents < 0) {
            throw new IllegalArgumentException("Subtotal must not be negative");
        }

        return subtotalCents >= 500_000 ? 0 : 30_000;
    }
}
~~~

Đoạn mã trên có nhiều ưu điểm: ít mã, ít bước để hiểu, không cần phụ thuộc ngoài, dễ viết unit test. Nếu chính sách ít thay đổi và chỉ được một module sử dụng, **đây hoàn toàn có thể là lựa chọn chất lượng**.

Điểm hạn chế xuất hiện khi ngưỡng 500.000 và phí 30.000 bắt đầu thay đổi thường xuyên. Mỗi lần đổi cần sửa source code, kiểm tra lại và phát hành chương trình, ngay cả khi điều duy nhất thay đổi chỉ là một giá trị chính sách.

### 5.2. Khi tham số đổi thường xuyên, tách chúng khỏi thuật toán

~~~java
// Java 17+
public record ShippingPolicy(int freeFromCents, int flatFeeCents) {
    public ShippingPolicy {
        if (freeFromCents < 0 || flatFeeCents < 0) {
            throw new IllegalArgumentException("Policy values must be non-negative");
        }
    }
}
~~~

~~~java
import java.util.Objects;

public final class ShippingFeeCalculator {
    private final ShippingPolicy policy;

    public ShippingFeeCalculator(ShippingPolicy policy) {
        this.policy = Objects.requireNonNull(policy, "policy");
    }

    public int calculate(int subtotalCents) {
        if (subtotalCents < 0) {
            throw new IllegalArgumentException("Subtotal must not be negative");
        }

        return subtotalCents >= policy.freeFromCents()
                ? 0
                : policy.flatFeeCents();
    }
}
~~~

Ví dụ sử dụng với hai chính sách khác nhau:

~~~java
var regular = new ShippingFeeCalculator(
        new ShippingPolicy(500_000, 30_000));

var campaign = new ShippingFeeCalculator(
        new ShippingPolicy(300_000, 20_000));

int regularFee = regular.calculate(400_000);   // 30_000
int campaignFee = campaign.calculate(400_000); // 0
~~~

Khi chỉ đổi **ngưỡng** và **phí cố định**, phần thuật toán không phải sửa. Chính sách trở thành dữ liệu riêng có thể kiểm tra hợp lệ và đưa vào lúc khởi tạo. Giá trị chính sách có thể đọc từ cấu hình ứng dụng hoặc một nguồn được quản lý, nhưng ví dụ chưa triển khai chức năng đọc cấu hình.

Tách chính sách có những **chi phí mới**: thêm kiểu dữ liệu, thêm bước khởi tạo, cần quản lý nguồn và phiên bản của cấu hình. Nếu cấu hình thay đổi trong lúc ứng dụng chạy, còn phải xác định khi nào thay đổi có hiệu lực, cách triển khai đồng bộ và khôi phục khi cấu hình sai. Tách cấu hình vì thế **không tự giải quyết toàn bộ bài toán thay đổi**.

### 5.3. Kiểm thử bảo vệ hợp đồng khi nhiều người cùng sửa

~~~java
import static org.junit.jupiter.api.Assertions.*;
import org.junit.jupiter.api.Test;

class ShippingFeeCalculatorTest {
    @Test
    void usesFlatFeeJustBelowThreshold() {
        var fee = new ShippingFeeCalculator(
                new ShippingPolicy(500_000, 30_000));

        assertEquals(30_000, fee.calculate(499_999));
    }

    @Test
    void givesFreeShippingAtExactThreshold() {
        var fee = new ShippingFeeCalculator(
                new ShippingPolicy(500_000, 30_000));

        assertEquals(0, fee.calculate(500_000));
    }

    @Test
    void acceptsZeroSubtotalButChargesFlatFee() {
        var fee = new ShippingFeeCalculator(
                new ShippingPolicy(500_000, 30_000));

        assertEquals(30_000, fee.calculate(0));
    }

    @Test
    void rejectsNegativeSubtotal() {
        var fee = new ShippingFeeCalculator(
                new ShippingPolicy(500_000, 30_000));

        assertThrows(IllegalArgumentException.class,
                () -> fee.calculate(-1));
    }
}
~~~

Các bài test minh họa một hợp đồng dễ giải thích với người bảo trì khác: tại đúng ngưỡng thì phí bằng 0; thấp hơn một đơn vị thì thu phí; tổng tiền âm là dữ liệu không hợp lệ. Chúng không chứng minh rằng kết quả hiển thị trên mọi thiết bị, API hoặc hóa đơn đều đúng; các ranh giới đó cần kiểm thử tích hợp phù hợp.

**Lưu ý nghiệp vụ:** ví dụ chấp nhận giỏ hàng giá trị 0 và tính phí vận chuyển; sản phẩm thực tế có thể yêu cầu cấm đặt đơn rỗng. Nếu có, việc kiểm tra tính hợp lệ của đơn phải được đặt rõ ràng ở đúng ranh giới. Các con số chỉ minh họa việc bảo trì chính sách; không phải mức phí phổ quát.

### 5.4. Khi quy tắc đổi dạng, chỉ cấu hình là chưa đủ

Giả sử chính sách mới là:

> Ngưỡng miễn phí thay đổi theo tỉnh thành; đơn của thành viên VIP có phí khác; một số loại hàng không đủ điều kiện miễn phí.

Đây là **thay đổi cấu trúc quy tắc**, không còn là thay một hoặc hai giá trị. Cố thêm hàng chục cờ boolean hoặc các chuỗi biểu thức tùy ý vào cấu hình có thể khiến hệ thống khó hiểu hơn.

Lúc này cần mô hình hóa rõ các khái niệm nghiệp vụ và tìm ranh giới biến động thật sự: ví dụ tách bước **xác định chính sách áp dụng** khỏi bước **tính phí theo chính sách**. Có thể cân nhắc các implementation khác nhau khi tồn tại nhiều hành vi khác nhau đã được xác nhận. **Không nên dựng rule engine hoặc plugin framework chỉ vì dự đoán xa rằng “có thể sẽ thay đổi”.**

## 6. Điều gì cần dễ hiểu khi nhiều người cùng bảo trì?

### 6.1. Làm rõ ý định, hợp đồng và bất biến

Đối với một hàm hoặc module được nhiều người cùng đụng tới, điều khó nhất nhiều khi không phải đọc cú pháp mà là hiểu **vì sao một quyết định tồn tại**.

Ví dụ, comment sau có ích:

~~~java
// The promotional threshold applies to the merchandise subtotal
// before shipping, as specified by checkout policy SHIP-12.
~~~

Nó nêu một quyết định nghiệp vụ có thể bị sửa sai nếu người sau không biết. Trái lại, comment “Check if subtotal is above threshold” ngay bên cạnh câu lệnh `if` thường chỉ lặp lại điều mã đã thể hiện.

Một hợp đồng tốt nêu rõ:

- Giá trị nào được phép đưa vào và đơn vị đo là gì?
- Trường hợp biên được xử lý thế nào?
- Thành phần nào chịu trách nhiệm trả lỗi hoặc ghi log?
- Những hành vi nào bên gọi có thể phụ thuộc?
- Quy tắc nào đã được thống nhất và cần hỏi lại trước khi đổi?

### 6.2. Giữ cấu trúc dễ định vị trách nhiệm

Người mới nên có thể tìm ra nơi thay đổi quy tắc vận chuyển mà không cần đọc hàng trăm file. Tên class, package, phương thức và cấu trúc module nên bộc lộ trách nhiệm. Không nên chia nhỏ mọi lớp chỉ để đạt một con số “số dòng chuẩn”; chia nhỏ sai có thể buộc người đọc nhảy qua nhiều file mới hiểu nổi một luồng.

Một dấu hiệu tích cực là **một thay đổi nghiệp vụ thường có vị trí sửa chính dễ xác định và phạm vi tác động có thể giải thích được**.

### 6.3. Giảm kiến thức tập trung vào một người

Có thể sử dụng review luân phiên, pair programming theo nhu cầu, tài liệu bàn giao ngắn và kịch bản xử lý sự cố. Cần chú ý **khả năng thực sự sửa và xác minh mã**, không chỉ số người có quyền truy cập repository.

Một người chịu trách nhiệm rõ ràng giúp hạn chế bỏ sót; nhưng nếu tất cả thay đổi đều phải chờ người duy nhất đó, cơ chế sở hữu đã tạo nút thắt. Các quy tắc duyệt mã cần phù hợp mức rủi ro và bảo đảm có phương án thay thế khi chủ sở hữu vắng mặt.

## 7. Thực hành phối hợp khi mã đổi thường xuyên

Các biện pháp hữu ích cần giải quyết đúng loại chi phí đang phát sinh.

| Vấn đề thường gặp | Biện pháp đáng cân nhắc | Đánh đổi và giới hạn |
| --- | --- | --- |
| Nhiều PR cùng sửa một file lớn | Chia trách nhiệm theo ranh giới nghiệp vụ; ưu tiên PR nhỏ, có mục tiêu. | Chia quá nhỏ tạo nhiều giao tiếp và điều hướng hơn. |
| Thay đổi nhỏ liên tục phá chức năng cũ | Test hồi quy tập trung vào hợp đồng, chạy tự động trong CI. | Test cần bảo trì; test yếu có thể tạo cảm giác an toàn giả. |
| Review mất nhiều thời gian vì thiếu ngữ cảnh | Mô tả thay đổi, quyết định nghiệp vụ và các trường hợp biên trong PR. | Mẫu PR quá dài làm người viết điền đối phó. |
| Hai nhóm hiểu khác nhau về API | Tài liệu hợp đồng, contract test, thông báo thay đổi phá tương thích. | Quản lý phiên bản và hợp đồng làm tăng công việc duy trì. |
| Người mới thường sửa sai quy tắc cũ | Tài liệu lý do quyết định, test có tên thể hiện yêu cầu, review có giải thích. | Tài liệu có thể lỗi thời nếu không được cập nhật cùng thay đổi. |
| Một người phải duyệt mọi thay đổi | Quy định ownership hợp lý, có người thay thế, đào tạo chéo. | Review luân phiên cần tiêu chuẩn chung để giữ nhất quán. |
| Phát hành thường xuyên gây lỗi môi trường | Quy trình triển khai lặp lại được, quan sát vận hành và khôi phục. | Tự động hóa cần đầu tư, kiểm tra và vận hành. |

### 7.1. PR nhỏ và ranh giới thay đổi rõ

Một PR vừa đổi công thức phí, vừa đổi định dạng API và vừa thay cấu trúc database rất khó review. Nên chia khi các phần có thể phát triển độc lập và mỗi phần vẫn giữ hệ thống ở trạng thái hợp lệ.

Ngược lại, cố chia một sửa lỗi nguyên tử thành nhiều PR phụ thuộc nhau có thể làm tích hợp phức tạp hơn. Mục tiêu không phải “mỗi PR ít dòng nhất”, mà là **mỗi thay đổi có lý do, phạm vi và bằng chứng dễ đánh giá**.

### 7.2. Phân quyền trách nhiệm không có nghĩa là tạo silo

Cần chỉ ra nhóm hoặc người chịu trách nhiệm chính cho một ranh giới, nhưng phải có khả năng chuyển giao. Trong hệ thống lớn, quy ước về ownership và review có thể giúp xác định nơi hỏi khi đổi hợp đồng. Quy ước ấy không thay thế tài liệu và bài test, cũng không nên làm mọi chỉnh sửa tắc nghẽn.

### 7.3. CI và kiểm thử hỗ trợ phối hợp

Một bộ kiểm thử có thể chạy tự động giúp người sửa có tín hiệu sớm về ảnh hưởng của thay đổi. Khi có nhiều người, lợi ích tăng vì kiểm thử trở thành **bộ tiêu chí chung** thay vì các thao tác cá nhân khó tái hiện.

Tuy vậy, không phải mọi hành vi đều kiểm tra bằng unit test. Những thay đổi liên quan database, tích hợp, phân quyền, thời gian thực hoặc tính tương thích vẫn cần bằng chứng bổ sung.

## 8. Tránh hai cực đoan thiết kế

### 8.1. Đơn giản quá mức dù đã có bằng chứng mã thay đổi liên tục

Dấu hiệu:

- Mỗi chiến dịch lại sửa nhiều điểm chứa cùng một hằng số.
- Quy tắc thường đổi nhưng không có test cho giá trị biên.
- Một lần chỉnh sửa cần hỏi người viết ban đầu để biết hành vi nào “không được đụng”.
- API hoặc dữ liệu bị thay đổi tùy tiện và gây lỗi cho nhiều bên sử dụng.

Ở đây, chi phí bảo trì đã lặp lại đủ nhiều để cân nhắc tách trách nhiệm, đặt tên quy tắc, bổ sung test hoặc tạo cấu hình.

### 8.2. Trừu tượng hóa quá sớm khi chưa có biến thể thật

Dấu hiệu:

- Chỉ có một implementation nhưng tạo nhiều interface, factory, strategy và registry không có nhu cầu hiện tại.
- Quy tắc hai dòng bị phân tán qua nhiều package.
- Mọi thay đổi phải sửa cả lớp trừu tượng dù hành vi thực tế chỉ có một.
- Không ai giải thích được giá trị cụ thể của lớp mở rộng so với cách viết trực tiếp.

Trừu tượng hóa chỉ có ích khi nó **làm rõ một ranh giới thực sự ổn định hoặc cô lập một biến thể đang tồn tại**. Khi chưa biết phần nào sẽ thay đổi, mã dễ hiểu, có test và có ranh giới phụ thuộc rõ thường là điểm xuất phát tốt hơn.

### 8.3. Không đánh đồng mọi loại “linh hoạt”

| Nhu cầu thực tế | Thay đổi hợp lý thường cân nhắc | Điều cần tránh |
| --- | --- | --- |
| Chỉ ngưỡng giá đổi theo đợt | Tham số hoặc cấu hình có xác thực. | Rule engine cho một phép so sánh. |
| Có hai cách tính phí đang dùng | Hai chiến lược rõ nghĩa nếu thực sự giúp cô lập hành vi. | Một hàm chung dài với hàng loạt cờ khó hiểu. |
| Nhiều service phải giữ định dạng dữ liệu | Hợp đồng và kiểm thử tương thích. | Đổi API âm thầm vì chỉ thấy sửa ít dòng. |
| Một nhóm chuyển giao quyền bảo trì | Tài liệu quyết định, hướng dẫn chạy test và ownership rõ. | Viết lại toàn bộ thành kiến trúc mới chỉ để “dễ bàn giao”. |
| Dự đoán có thể có 20 biến thể trong tương lai | Thu thập ví dụ thực và để sẵn khả năng refactor an toàn. | Xây dựng trước 20 extension point chưa có người sử dụng. |

## 9. Một phương pháp quyết định có thể áp dụng trong review

Trước khi thêm lớp trừu tượng, công cụ hoặc quy trình bảo trì, hãy trả lời theo trình tự sau:

**Bước 1 — Gọi tên thay đổi đang xảy ra.** Đang đổi một giá trị, một quy tắc, giao diện với bên khác hay hạ tầng? Có bao nhiêu lần và trong khoảng thời gian nào? Dữ liệu đủ chưa hay chỉ là dự đoán?

**Bước 2 — Xác định người và phạm vi ảnh hưởng.** Ai trực tiếp sửa? Ai cần hiểu, review, vận hành? Module được bao nhiêu thành phần gọi? Lỗi có tác động đến người dùng hoặc dữ liệu quan trọng không?

**Bước 3 — Chỉ ra chi phí thực sự.** Mỗi lần thay đổi đang mất thời gian ở đâu: tìm vị trí sửa, hiểu hành vi, cập nhật test, chờ review, tích hợp, phát hành hay xử lý hồi quy?

**Bước 4 — Chọn cải thiện nhỏ nhất giải quyết được chi phí đó.** Có thể chỉ cần đặt tên lại, chuyển hằng số thành tham số, bổ sung test hồi quy, ghi một tài liệu hợp đồng hoặc tách một class. Chỉ tăng độ phức tạp kiến trúc nếu có lợi ích kiểm chứng được.

**Bước 5 — Xác định tín hiệu để đánh giá lại.** Sau vài chu kỳ thay đổi, có giảm thời gian sửa, số lỗi hồi quy và số lần chờ giải thích không? Có phát sinh thêm bước đồng bộ, cấu hình hoặc đường đi khó hiểu không?

Một cách diễn đạt trade-off trong review:

> “Chính sách phí vận chuyển đã đổi tham số trong bốn chiến dịch gần đây, nhưng thuật toán không đổi. Tách hai tham số sang `ShippingPolicy` giúp giảm việc sửa source code ở mỗi chiến dịch. Việc đọc cấu hình vẫn nằm tại tầng khởi tạo và cần test xác nhận giá trị hợp lệ. Chúng ta chưa cần framework chiến lược vì chưa có hai thuật toán tính phí khác nhau.”

Lập luận này cho thấy **bằng chứng về biến động, biện pháp chọn, lợi ích và chi phí**, giúp người review đánh giá quyết định thay vì tranh luận về sở thích kiến trúc.

## 10. Bài tập tình huống

Một nhóm quản lý service xuất hóa đơn. Trong sáu tháng:

- Thuật toán tạo số hóa đơn gần như không đổi.
- Danh sách mẫu hiển thị và nhãn thông tin được cập nhật gần như mỗi tuần.
- Ba nhóm phải phối hợp vì service được dùng bởi trang quản trị, ứng dụng khách hàng và hệ thống đối soát.
- Mỗi đợt cập nhật mẫu hiện tại đều phải sửa nhiều chỗ; đôi khi trang quản trị và bản PDF hiển thị khác nhau.

**Câu hỏi:**

1. Phần nào có tần suất thay đổi cao, phần nào ổn định?
2. Vì sao số lượng nhóm sử dụng service lại quan trọng dù chỉ một nhóm sửa mã lõi?
3. Nên thử cải thiện ở đâu trước và cần bằng chứng gì để biết đã tốt hơn?
4. Có cần tách toàn bộ service thành nhiều microservice không?

**Gợi ý phân tích:**

- **Biến động cao:** mẫu hiển thị và nhãn thông tin; **ổn định:** thuật toán tạo số. Tránh đặt phần thường đổi và phần ổn định vào cùng một cơ chế cấu hình/phát hành nếu không có lý do.
- Các nhóm phụ thuộc cần **hợp đồng dữ liệu và cách xử lý tương thích** rõ ràng. Một sửa đổi hiếm ở định dạng số hóa đơn có thể ảnh hưởng rất nhiều bên.
- Có thể bắt đầu bằng **một nguồn định nghĩa mẫu**, tách dữ liệu hiển thị khỏi thuật toán khi hợp lý, và thêm kiểm thử đối chiếu đầu ra ở các kênh tiêu thụ. Trước tiên xác định liệu hai kênh có thật sự phải hiển thị giống nhau theo yêu cầu sản phẩm.
- Không có đủ bằng chứng để kết luận phải tách microservice. Nên đo độ khó bảo trì, mức độ xung đột và yêu cầu triển khai độc lập trước khi nhận thêm chi phí mạng, vận hành và nhất quán dữ liệu.

## 11. Checklist đánh giá trong công việc hằng ngày

- [ ] Tôi đã xác định đúng phần mã và loại thay đổi cần tối ưu, thay vì nhìn tổng số commit của toàn repository.
- [ ] Tôi biết ai trực tiếp sửa, ai review/vận hành và những thành phần nào phụ thuộc vào hợp đồng của module.
- [ ] Tôi phân biệt được yêu cầu đã xảy ra với khả năng giả định trong tương lai.
- [ ] Quy tắc quan trọng được thể hiện rõ bằng tên, giao diện và test có ý nghĩa.
- [ ] Tôi đã cân nhắc chi phí đọc, sửa, xác minh, tích hợp, bàn giao và vận hành khi đề xuất cấu trúc.
- [ ] Giải pháp mới thực sự làm rẻ hơn một loại thay đổi đã quan sát được.
- [ ] Lớp trừu tượng hoặc cấu hình thêm vào có lợi ích rõ ràng lớn hơn chi phí duy trì của nó.
- [ ] Khi nhiều người cùng làm việc, có hợp đồng, trách nhiệm review và cách tái hiện lỗi phù hợp.
- [ ] Tôi có thể giải thích vì sao giải pháp đủ đơn giản cho hiện tại và khi nào cần đánh giá lại.

## 12. Kết luận

**Tần suất thay đổi** quyết định một chi phí bảo trì sẽ lặp lại thường xuyên đến mức nào. **Số người cùng bảo trì và số bên phụ thuộc** quyết định mức độ cần chia sẻ hiểu biết, giữ hợp đồng ổn định và phối hợp kiểm tra thay đổi. Hai yếu tố này làm thay đổi giá trị tương đối của tính đơn giản, khả năng kiểm thử, tài liệu, modularity và các quy trình phát triển.

Trong **CODE_QUALITY_FUNDAMENTALS**, chất lượng mã không có một hình thức cố định áp dụng cho mọi dự án. Mã chất lượng là mã **đáng tin cậy, dễ hiểu và dễ thay đổi đối với những người và kiểu thay đổi thật sự đang tồn tại**. Hãy bắt đầu từ thiết kế rõ ràng, quan sát chi phí thay đổi thực tế rồi đầu tư vào đúng điểm đau; tránh vừa bỏ mặc mã lặp lại lỗi, vừa xây dựng độ phức tạp chưa có nhu cầu.

