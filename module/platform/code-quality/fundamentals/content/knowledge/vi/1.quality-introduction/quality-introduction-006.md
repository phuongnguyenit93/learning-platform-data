# Chất lượng nội tại và hành vi quan sát được

Một chương trình có thể chạy đúng hôm nay nhưng rất khó sửa vào ngày mai. Ngược lại, mã nguồn có cấu trúc gọn gàng vẫn có thể trả kết quả sai hoặc làm mất dữ liệu. Để đánh giá chất lượng phần mềm một cách đầy đủ, cần phân biệt **chất lượng nội tại** của cách xây dựng hệ thống với **hành vi quan sát được** khi hệ thống hoạt động.

Trong nền tảng chất lượng mã nguồn (*Code Quality Fundamentals*), sự phân biệt này giúp trả lời hai câu hỏi khác nhau:

1. **Hệ thống làm gì, và người sử dụng hoặc hệ thống khác quan sát được điều gì?**
2. **Hệ thống được tổ chức như thế nào, và việc hiểu, kiểm thử, sửa đổi nó có dễ và an toàn không?**

Hai góc nhìn liên quan chặt chẽ, nhưng không thể thay thế cho nhau.

## 1. Hai khái niệm cốt lõi

### 1.1. Chất lượng nội tại là gì?

**Chất lượng nội tại** (*internal quality*) là chất lượng của cấu trúc và cách triển khai phần mềm, chủ yếu thể hiện khi lập trình viên đọc, kiểm tra, bảo trì hoặc mở rộng hệ thống. Những đặc điểm thường được xem xét gồm:

| Khía cạnh | Câu hỏi kiểm tra | Dấu hiệu thường gặp |
| --- | --- | --- |
| Tính dễ đọc | Người mới có hiểu mục đích của đoạn mã không? | Tên rõ nghĩa, luồng xử lý dễ theo dõi, ít thông tin thừa |
| Tính mô-đun | Mỗi thành phần có trách nhiệm tương đối rõ không? | Phân tách hợp lý giữa tính toán, lưu trữ, giao tiếp bên ngoài |
| Tính gắn kết (*cohesion*) | Các phần trong một mô-đun có cùng phục vụ một mục đích không? | Lớp ít trách nhiệm không liên quan |
| Mức độ phụ thuộc (*coupling*) | Sửa một thành phần có kéo theo nhiều thay đổi ngoài dự kiến không? | Phụ thuộc được kiểm soát, giao diện rõ |
| Khả năng kiểm thử | Có thể cô lập các quy tắc quan trọng để xác minh không? | Ít phụ thuộc ngầm vào thời gian, mạng hoặc trạng thái toàn cục |
| Khả năng thay đổi | Có thể sửa yêu cầu mà vẫn kiểm soát được ảnh hưởng không? | Quy tắc tập trung, ít lặp logic, ít nhánh rối |

Đây không phải các con số có thể tổng hợp thành một điểm số chính xác cho mọi dự án. Chẳng hạn, một hàm ngắn chưa chắc dễ hiểu hơn hàm dài; tách thêm lớp có thể làm giảm phụ thuộc hoặc lại tạo ra sự phân mảnh không cần thiết. Phải xem cấu trúc đó có phục vụ nhu cầu thực tế của hệ thống hay không.

### 1.2. Hành vi quan sát được là gì?

**Hành vi quan sát được** (*observable behavior*) là những gì một tác nhân có thể nhận biết khi tương tác với phần mềm qua một **ranh giới xác định**. Tác nhân có thể là người dùng, một chương trình gọi API, một hệ thống tích hợp, bộ kiểm thử hoặc bộ phận vận hành.

Tùy ranh giới đang xét, hành vi có thể bao gồm:

- Giá trị trả về, nội dung màn hình, mã trạng thái HTTP và dữ liệu trong phản hồi.
- Lỗi hoặc ngoại lệ có thể nhận biết, kể cả loại lỗi và thông điệp nếu chúng thuộc hợp đồng giao tiếp.
- Tác động bên ngoài: ghi cơ sở dữ liệu, gửi thông báo, tạo tệp, phát sự kiện, gọi dịch vụ khác.
- Thứ tự và số lần xảy ra tác động, khi điều đó ảnh hưởng tới người quan sát.
- Các đặc tính đo được như độ trễ, mức sử dụng tài nguyên, khả năng sẵn sàng và tính an toàn, nếu chúng liên quan tới yêu cầu hoặc cam kết của hệ thống.

Khái niệm **hợp đồng hành vi** (*behavioral contract*) mô tả các điều kiện đầu vào, đầu ra, lỗi và tác động mà một thành phần cam kết. Không phải mọi chi tiết quan sát được đều mặc nhiên là cam kết. Ví dụ, định dạng log nội bộ có thể thay đổi tự do ở một ứng dụng, nhưng lại là giao diện quan trọng nếu một hệ thống giám sát đang phân tích log theo định dạng đó.

### 1.3. Sự khác biệt quan trọng

| Tiêu chí | Chất lượng nội tại | Hành vi quan sát được |
| --- | --- | --- |
| Trọng tâm | Cách tổ chức và triển khai | Kết quả và tác động khi thực thi |
| Người thường đánh giá | Người phát triển, người bảo trì, người review | Người dùng, hệ thống tích hợp, kiểm thử, vận hành |
| Ví dụ vấn đề | Logic lặp, đặt tên mơ hồ, phụ thuộc vòng, hàm khó kiểm thử | Tính tiền sai, API trả sai mã lỗi, ghi trùng đơn hàng |
| Cách thu thập bằng chứng | Đọc mã, review thiết kế, phân tích tĩnh, thử thay đổi | Kiểm thử hành vi, kiểm thử tích hợp, đo hiệu năng, giám sát |
| Kết quả mong đợi | Dễ hiểu và dễ phát triển an toàn | Thực hiện đúng yêu cầu trong điều kiện xác định |

**Điểm mấu chốt:** Hai phiên bản có thể tạo ra cùng kết quả quan sát được nhưng có chất lượng nội tại khác nhau. Đồng thời, hai phiên bản đều được viết sạch sẽ vẫn có thể khác nhau về tính đúng đắn.

## 2. Ví dụ Java: cùng hành vi, khác cách triển khai

Giả sử một cửa hàng có quy tắc tính phí vận chuyển:

- Tổng giá trị đơn hàng âm là đầu vào không hợp lệ.
- Đơn hàng từ **500.000 VND** trở lên được miễn phí vận chuyển.
- Các đơn hàng hợp lệ còn lại có phí vận chuyển **30.000 VND**.

Phiên bản đầu tiên chạy đúng quy tắc, nhưng có tên biến thiếu ý nghĩa, các giá trị số nằm trực tiếp trong biểu thức và một nhánh lồng nhau không cần thiết.

**Phiên bản A**

~~~java
public final class ShippingFeeCalculator {
    public int calculate(int amount) {
        if (amount >= 0) {
            int result = 30_000;
            if (amount >= 500_000) {
                result = 0;
            }
            return result;
        }
        throw new IllegalArgumentException("Subtotal must be non-negative");
    }
}
~~~

**Phiên bản B**

~~~java
public final class ShippingFeeCalculator {
    private static final int FREE_SHIPPING_FROM_VND = 500_000;
    private static final int STANDARD_SHIPPING_FEE_VND = 30_000;

    public int calculate(int subtotalVnd) {
        if (subtotalVnd < 0) {
            throw new IllegalArgumentException("Subtotal must be non-negative");
        }

        return subtotalVnd >= FREE_SHIPPING_FROM_VND
                ? 0
                : STANDARD_SHIPPING_FEE_VND;
    }
}
~~~

Ở phiên bản B:

1. *subtotalVnd* cho biết đầu vào biểu diễn số tiền và đơn vị tiền tệ.
2. Các hằng số diễn đạt ý nghĩa nghiệp vụ của ngưỡng miễn phí và phí tiêu chuẩn.
3. Kiểm tra đầu vào không hợp lệ được xử lý ngay, khiến đường xử lý chính ít lồng nhau hơn.
4. Phần lựa chọn phí chỉ còn một biểu thức, dễ đối chiếu với quy tắc.

Đây là một **cải thiện chất lượng nội tại** ở phạm vi ví dụ: mã dễ đọc và dễ tìm chỗ sửa quy tắc hơn. Không nên suy ra rằng mọi lần sử dụng toán tử ba ngôi hoặc mọi lần tách hằng số đều làm mã tốt hơn; giá trị nằm ở sự rõ nghĩa trong ngữ cảnh.

Hai phiên bản có cùng hành vi theo hợp đồng đã nêu:

| Đầu vào (*subtotalVnd*) | Kết quả phiên bản A | Kết quả phiên bản B |
| ---: | ---: | ---: |
| -1 | Ném *IllegalArgumentException* | Ném *IllegalArgumentException* |
| 0 | 30.000 VND | 30.000 VND |
| 499.999 | 30.000 VND | 30.000 VND |
| 500.000 | 0 VND | 0 VND |
| 500.001 | 0 VND | 0 VND |

Thông điệp ngoại lệ cũng được giữ nguyên trong hai phiên bản. Việc bảo toàn thông điệp có cần thiết hay không phụ thuộc vào hợp đồng thực tế; ở đây nó giúp đối chiếu đầy đủ.

### Một thay đổi nhỏ có thể làm sai hành vi

Giả sử trong phiên bản B, lập trình viên vô tình thay điều kiện:

~~~java
return subtotalVnd > FREE_SHIPPING_FROM_VND
        ? 0
        : STANDARD_SHIPPING_FEE_VND;
~~~

Mã vẫn ngắn, vẫn dễ đọc, nhưng đơn hàng **đúng 500.000 VND** sẽ bị thu phí. Chỉ đổi một ký hiệu từ *lớn hơn hoặc bằng* thành *lớn hơn* đã tạo ra hồi quy hành vi (*behavioral regression*).

Vì vậy, **mã sạch không chứng minh mã đúng**. Mục tiêu khi cải tiến cấu trúc là tăng chất lượng nội tại **đồng thời bảo toàn hợp đồng hành vi** trong phạm vi thay đổi.

## 3. Xác định chính xác những gì phải được bảo toàn

Phát biểu “không thay đổi hành vi” chỉ có ý nghĩa khi biết **ai quan sát**, **quan sát qua giao diện nào**, và **những điều gì đã được cam kết**.

Ví dụ, khi tái cấu trúc một dịch vụ tạo đơn hàng, chỉ so sánh mã HTTP trả về là chưa đủ. Cần xác định thêm:

| Khía cạnh | Câu hỏi cụ thể |
| --- | --- |
| Giá trị phản hồi | Tổng tiền, mã đơn hàng và trạng thái có giữ nguyên quy tắc không? |
| Kiểm tra dữ liệu | Đầu vào thiếu, sai định dạng hoặc trùng lặp có còn được xử lý đúng không? |
| Tác động bền vững | Đơn hàng có được lưu đúng một lần, với dữ liệu chính xác không? |
| Tác động tới hệ thống khác | Sự kiện đặt hàng hoặc email có được gửi đúng điều kiện không? |
| Xử lý lỗi | Khi lưu thất bại, hệ thống có tránh để lại dữ liệu dở dang không? |
| Điều kiện phi chức năng | Độ trễ, quyền truy cập và tính nhất quán có còn đáp ứng yêu cầu không? |

Một số chi tiết không nên bị “đóng băng” tùy tiện: tên biến, cách chia hàm hoặc thứ tự tính toán trung gian thuần túy thường là chi tiết triển khai. Ngược lại, thứ tự phát sự kiện có thể là hành vi quan sát được nếu bên nhận dựa vào thứ tự đó.

Có thể diễn đạt quan hệ tương đương theo cách thực dụng:

> Với cùng những đầu vào và điều kiện môi trường nằm trong phạm vi cam kết, hai phiên bản được xem là tương đương về hành vi khi các quan sát quan trọng tại ranh giới đã chọn đều thỏa cùng hợp đồng.

Điều này không yêu cầu hai phiên bản có cùng số dòng, cùng thuật toán hoặc cùng biểu diễn dữ liệu nội bộ. Nhưng nó cũng không có nghĩa rằng mọi khác biệt trong thời gian chạy hay tác động phụ đều được phép bỏ qua.

## 4. Kiểm thử hành vi và đánh giá chất lượng nội tại bổ sung cho nhau

### 4.1. Kiểm thử xác minh các ví dụ quan sát được

Với bài toán phí vận chuyển, có thể dùng JUnit 5 để kiểm tra các trường hợp điển hình và giá trị biên:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.CsvSource;

class ShippingFeeCalculatorTest {
    private final ShippingFeeCalculator calculator =
            new ShippingFeeCalculator();

    @ParameterizedTest
    @CsvSource({
        "0, 30000",
        "499999, 30000",
        "500000, 0",
        "500001, 0"
    })
    void calculatesFeeAccordingToThreshold(
            int subtotalVnd,
            int expectedFeeVnd
    ) {
        assertEquals(expectedFeeVnd, calculator.calculate(subtotalVnd));
    }

    @Test
    void rejectsNegativeSubtotal() {
        IllegalArgumentException error = assertThrows(
                IllegalArgumentException.class,
                () -> calculator.calculate(-1)
        );
        assertEquals("Subtotal must be non-negative", error.getMessage());
    }
}
~~~

Các bài kiểm thử này cung cấp bằng chứng có thể chạy lại rằng một số hành vi quan trọng được giữ nguyên. Giá trị biên 500.000 VND đặc biệt hữu ích vì nó phát hiện lỗi đổi toán tử so sánh. Tuy nhiên, **kiểm thử không thể tự nó chứng minh hai chương trình tương đương cho mọi đầu vào và mọi môi trường**; mức độ tin cậy phụ thuộc vào chất lượng bộ ca kiểm thử và hiểu biết về hợp đồng.

Với hệ thống có cơ sở dữ liệu hoặc tích hợp, kiểm thử cấp đơn vị chưa đủ để kiểm tra tất cả tác động. Nên kết hợp các mức kiểm thử phù hợp: kiểm thử thành phần, hợp đồng API, tích hợp và luồng nghiệp vụ đầu cuối.

### 4.2. Đánh giá nội tại cần bằng chứng khác

Các bài kiểm thử đều xanh không trả lời trực tiếp những câu hỏi như:

- Quy tắc phí vận chuyển có bị lặp ở nhiều nơi không?
- Một thay đổi nhỏ có buộc sửa hàng loạt lớp không?
- Tên phương thức có làm người đọc hiểu sai nghiệp vụ không?
- Có thể kiểm thử quy tắc mà không phải khởi động toàn bộ hạ tầng không?

Để đánh giá các vấn đề đó, cần đọc mã, review thiết kế và xem cách thay đổi lan truyền. Công cụ phân tích tĩnh có thể hỗ trợ phát hiện mã lặp, độ phức tạp hoặc các phụ thuộc đáng ngờ, nhưng số lượng cảnh báo chỉ là **tín hiệu cần xem xét**, không phải kết luận tuyệt đối về chất lượng thiết kế.

Một bộ kiểm thử tốt có thể cùng tồn tại với thiết kế khó bảo trì; một cấu trúc tốt cũng có thể tồn tại cùng các lỗi nghiệp vụ chưa được kiểm thử.

## 5. Tái cấu trúc, sửa lỗi và thay đổi tính năng

Ba loại công việc này có mục tiêu khác nhau:

| Hoạt động | Điều cần thay đổi | Điều cần kiểm soát |
| --- | --- | --- |
| **Tái cấu trúc** (*refactoring*) | Cấu trúc bên trong: tên, hàm, mô-đun, phụ thuộc | Giữ nguyên hành vi thuộc hợp đồng hiện hành |
| **Sửa lỗi** (*bug fix*) | Hành vi hiện tại đang vi phạm yêu cầu | Chỉ thay đổi kết quả sai và tránh hồi quy ở phần đúng |
| **Phát triển tính năng** (*feature development*) | Bổ sung hoặc điều chỉnh hành vi theo yêu cầu mới | Giữ tương thích ở các phần không được chủ đích thay đổi |

Ví dụ:

- Đổi tên *amount* thành *subtotalVnd* và đưa ngưỡng miễn phí vào hằng số là tái cấu trúc.
- Sửa điều kiện sai *lớn hơn* thành *lớn hơn hoặc bằng* theo quy tắc đã có là sửa lỗi.
- Đổi ngưỡng miễn phí từ 500.000 lên 600.000 VND theo chính sách mới là thay đổi tính năng.

Trong thực tế, một nhánh công việc có thể chứa cả ba loại thay đổi. Khi đó, nên làm rõ mục tiêu và tạo bằng chứng kiểm thử phù hợp cho từng phần, tránh gọi mọi thay đổi là “refactor” để bỏ qua việc kiểm tra hành vi.

## 6. Các tình huống dễ hiểu nhầm

**“Chạy đúng là đủ tốt.”** Một chương trình có thể trả kết quả đúng nhưng chứa logic trùng lặp, phụ thuộc chằng chịt và các quy tắc khó phát hiện. Những vấn đề này làm chi phí và rủi ro của thay đổi tương lai tăng lên, dù người dùng chưa thấy lỗi.

**“Mã đẹp thì chắc chắn đúng.”** Cách đặt tên và phân tách hợp lý giúp lập luận, nhưng không đảm bảo quy tắc nghiệp vụ, quyền truy cập hay phép tính đã đúng. Lỗi tại ngưỡng 500.000 VND ở ví dụ trên minh họa điều này.

**“Hành vi chỉ là giá trị trả về.”** Một API có thể trả đúng phản hồi nhưng ghi dữ liệu hai lần hoặc gửi hai email. Những tác động này cũng là hành vi quan sát được tại ranh giới tích hợp.

**“Tất cả chi tiết triển khai đều không quan sát được.”** Nếu thay đổi thứ tự xử lý khiến giao dịch chậm vượt cam kết, hoặc việc thay đổi log làm hỏng hệ thống cảnh báo đang phụ thuộc vào log đó, ảnh hưởng đã vượt ra ngoài cấu trúc nội bộ thuần túy.

**“Càng nhiều lớp và mẫu thiết kế thì chất lượng nội tại càng cao.”** Trừu tượng hóa không đúng chỗ làm mã khó tìm kiếm và khó thay đổi. Chọn mức phân tách dựa trên trách nhiệm, biến động dự kiến và nhu cầu kiểm thử.

## 7. Quy trình thực hành khi cải thiện mã

Khi muốn nâng chất lượng nội tại của một thành phần đang hoạt động:

1. **Viết rõ hợp đồng hiện tại:** đầu vào hợp lệ, kết quả, lỗi, tác động phụ và các ràng buộc đáng kể.
2. **Xác định điểm rủi ro:** giá trị biên, dữ liệu rỗng, lỗi tích hợp, trường hợp đồng thời hoặc các tác động không thể dễ dàng hoàn tác.
3. **Tạo bằng chứng hành vi:** bổ sung hoặc rà soát các kiểm thử phản ánh yêu cầu. Ghi nhận số đo phi chức năng nếu công việc có nguy cơ tác động đến chúng.
4. **Cải thiện một phần cấu trúc có mục đích:** đổi tên, giảm lặp, chia trách nhiệm hoặc đơn giản hóa luồng điều khiển để giải quyết vấn đề nội tại cụ thể.
5. **Kiểm chứng lại:** chạy kiểm thử liên quan, review những khác biệt bên ngoài và xem xét kết quả phân tích tĩnh. Khi cần, đo lại hiệu năng và kiểm tra tích hợp.
6. **Đánh giá kết quả bằng khả năng thay đổi thực tế:** mã mới có khiến quy tắc dễ tìm, dễ giải thích, dễ sửa và dễ kiểm thử hơn không?

Không nên lấy số dòng bị giảm, tỉ lệ bao phủ kiểm thử hay số cảnh báo tĩnh làm mục tiêu duy nhất. Chúng có ích khi hỗ trợ một nhận định dựa trên hợp đồng và ngữ cảnh cụ thể.

## 8. Tình huống luyện tập

Một hệ thống đăng ký tài khoản luôn trả HTTP 201 sau khi tạo người dùng. Nhóm phát triển thay một phương thức dài bằng nhiều phương thức nhỏ có tên rõ ràng. Kiểm thử API vẫn xác nhận mã 201 và cấu trúc JSON như cũ. Sau khi triển khai, mỗi lần đăng ký lại gửi hai email chào mừng.

**Hãy thử trả lời:**

1. Chất lượng nội tại có thể đã được cải thiện ở điểm nào?
2. Hành vi quan sát được nào đã thay đổi?
3. Vì sao chỉ kiểm tra HTTP 201 và nội dung JSON không phát hiện được lỗi?
4. Cần bổ sung bằng chứng gì trước lần chỉnh sửa tiếp theo?

**Gợi ý đối chiếu:** Việc tách phương thức có thể cải thiện tính dễ đọc và phân tách trách nhiệm, nhưng phải review thiết kế thực tế mới kết luận được. Gửi hai email thay vì một là thay đổi hành vi tại ranh giới với dịch vụ gửi thư. Bộ kiểm thử chỉ quan sát phản hồi API nên bỏ sót tác động phụ. Nên có kiểm thử tích hợp hoặc kiểm thử với cổng gửi email giả để xác nhận số lần gửi, điều kiện gửi và cách xử lý lỗi.

## 9. Ghi nhớ

- **Chất lượng nội tại** trả lời câu hỏi hệ thống có dễ hiểu, dễ kiểm thử và dễ thay đổi một cách an toàn không.
- **Hành vi quan sát được** trả lời câu hỏi hệ thống thực sự trả gì và gây ra những tác động nào trong phạm vi hợp đồng.
- **Tái cấu trúc tốt** cải thiện tổ chức bên trong trong khi bảo toàn các cam kết hành vi; **kiểm thử tốt** giúp phát hiện sai lệch, nhưng không thay thế việc review chất lượng nội tại.
- **Chất lượng phần mềm cần cả hai góc nhìn:** đáp ứng yêu cầu hiện tại và giữ khả năng đáp ứng yêu cầu tương lai.
