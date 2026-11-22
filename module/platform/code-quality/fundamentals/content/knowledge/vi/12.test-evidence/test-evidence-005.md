# Chất lượng dữ liệu thử và kết quả kỳ vọng

Một bài kiểm thử có thể chạy thành công, thậm chí làm tăng độ bao phủ mã, nhưng vẫn không chứng minh được chương trình xử lý đúng yêu cầu. Chẳng hạn, kiểm thử tính khuyến mãi chỉ dùng đơn hàng thông thường có thể bỏ sót lỗi ở ngưỡng áp dụng, còn phép khẳng định lấy **kết quả kỳ vọng từ chính phương thức đang kiểm thử** thì có thể lặp lại lỗi của phương thức đó.

Trong module **CODE_QUALITY_FUNDAMENTALS**, mục tiêu là hiểu những thuộc tính giúp mã nguồn đáng tin cậy, dễ hiểu và dễ thay đổi. Ở chương **Bằng chứng kiểm thử**, hai câu hỏi cần được đặt cạnh nhau:

1. **Dữ liệu thử có đủ chất lượng để làm lộ những lỗi quan trọng không?**
2. **Kết quả kỳ vọng có cơ sở độc lập, rõ ràng và đủ chính xác để phát hiện sai lệch không?**

Một kiểm thử đáng tin cậy cần cả **đầu vào có chủ đích** và **test oracle (cơ sở xác định đúng/sai)**. Chạy nhiều lần với dữ liệu nghèo nàn hoặc khẳng định yếu có thể tạo cảm giác an toàn giả.

## 1. Dữ liệu thử và kết quả kỳ vọng có vai trò khác nhau

Một ca kiểm thử có thể được mô tả bằng bộ ba:

> **Bối cảnh và đầu vào → hành động → kết quả cần quan sát**

Ví dụ, “khách hàng thân thiết mua hàng trị giá 200.000 VND” mới chỉ là **dữ liệu đầu vào**. Cần biết thêm “giảm giá phải là 20.000 VND” và “không có trạng thái ngoài mong đợi bị thay đổi” để quyết định chương trình đúng hay sai.

| Thành phần | Câu hỏi cần trả lời | Ví dụ |
| --- | --- | --- |
| **Dữ liệu đầu vào** | Điều gì được truyền vào hệ thống? | Tổng đơn hàng 200.000 VND, khách hàng thân thiết. |
| **Trạng thái trước khi chạy** | Hệ thống đang ở điều kiện nào? | Voucher còn hạn, đơn chưa thanh toán, tài khoản đủ quyền. |
| **Hành động** | Thao tác thực sự được thực hiện là gì? | Gọi hàm tính chiết khấu hoặc API tạo đơn. |
| **Kết quả kỳ vọng** | Giá trị, lỗi hoặc thay đổi trạng thái nào là đúng? | Trả giảm giá 20.000 VND. |
| **Bằng chứng quan sát** | Điều gì cho thấy kỳ vọng được đáp ứng? | Assertion, dữ liệu sau giao dịch, số lần gửi sự kiện, phản hồi API. |

Nếu dữ liệu không tạo ra tình huống có khả năng phát hiện lỗi, ca kiểm thử có thể **không nhạy với khiếm khuyết**. Nếu kỳ vọng chỉ là “không ném ngoại lệ”, ca kiểm thử có thể bỏ qua một giá trị trả về sai nghiêm trọng.

### Chất lượng dữ liệu thử không đồng nghĩa số lượng bản ghi

Một nghìn số ngẫu nhiên đều lớn hơn ngưỡng có thể kém giá trị hơn ba số **ngay dưới, bằng và ngay trên ngưỡng**. Đánh giá dữ liệu theo **rủi ro, phân lớp hành vi và sức phát hiện sai lệch**, thay vì chỉ đếm số dòng.

## 2. Những phẩm chất của dữ liệu thử tốt

| Phẩm chất | Ý nghĩa thực tế | Dấu hiệu dữ liệu chưa tốt |
| --- | --- | --- |
| **Liên quan đến yêu cầu** | Mỗi trường hợp kiểm tra một quy tắc hoặc rủi ro được xác định. | Chọn giá trị tùy ý nhưng không biết vì sao chúng cần thiết. |
| **Đại diện cho các lớp hành vi** | Có trường hợp bình thường, biên, bất hợp lệ và tổ hợp quan trọng. | Mọi trường hợp đều nằm sâu trong miền hợp lệ. |
| **Có khả năng phân biệt đúng/sai** | Khi điều kiện hoặc phép tính sai, ít nhất một ca có thể thất bại. | Đầu vào không khiến nhánh sai được kích hoạt. |
| **Tái lập được** | Cùng dữ liệu và bối cảnh kiểm soát cho kết quả nhất quán. | Dựa vào thời gian thực, dữ liệu dùng chung hoặc ngẫu nhiên không lưu seed. |
| **Độc lập và cô lập** | Ca kiểm thử không phụ thuộc thứ tự chạy hay dữ liệu còn lại của ca trước. | Chỉ vượt qua khi chạy sau một test đã tạo bản ghi. |
| **Dễ hiểu và truy vết** | Có thể giải thích vì sao giá trị được chọn và kết quả đúng là gì. | Dữ liệu tạo tự động rất lớn nhưng không ghi nhận trường hợp gây lỗi. |
| **An toàn và phù hợp môi trường** | Không làm lộ dữ liệu thật hoặc gây tác dụng phụ ngoài phạm vi test. | Copy dữ liệu cá nhân từ sản xuất vào repository kiểm thử. |

**Tính đại diện luôn có giới hạn.** Không thể khẳng định một bộ nhỏ dữ liệu bao phủ mọi tình huống thực tế. Nên chọn dữ liệu theo miền đầu vào, đặc tả, lỗi từng gặp và hậu quả nếu mã sai.

## 3. Ví dụ xuyên suốt: tính giảm giá theo quy tắc đã chốt

Giả sử hệ thống có hàm tính số tiền giảm giá, dùng đơn vị **VND nguyên**. Đặc tả của bài tập:

1. Tổng giá trị hàng (**subtotalVnd**) là số nguyên trong đoạn **0 đến 2.000.000.000**, gồm cả hai đầu mút. Ngoài đoạn này thì từ chối bằng **IllegalArgumentException**.
2. Nếu subtotalVnd **nhỏ hơn 200.000**, không giảm giá.
3. Từ **200.000** trở lên, khách thông thường giảm **5%**, khách thân thiết (**loyalCustomer = true**) giảm **10%**.
4. Số tiền giảm giá được **làm tròn xuống đến VND nguyên**, sau đó giới hạn tối đa **50.000 VND**.
5. Hàm chỉ tính toán và trả giá trị; **không ghi dữ liệu hoặc gọi hệ thống bên ngoài**.

Đặc tả này là **nguồn xác định kỳ vọng**. Nó phải được thống nhất trước khi xem kết quả từ code. Nếu quy tắc còn mơ hồ (ví dụ làm tròn theo cách nào), cần làm rõ trước khi viết assertion.

### Cách tính kỳ vọng độc lập

Với một tổng đơn hàng hợp lệ:

- Nếu dưới 200.000: giảm giá **0**.
- Nếu từ 200.000: lấy **5% hoặc 10%**, làm tròn xuống VND nguyên, rồi lấy giá trị nhỏ hơn giữa kết quả đó và **50.000**.
- Nếu ngoài miền: phải ném **IllegalArgumentException**.

Ví dụ: với subtotalVnd = **200.015** và khách thân thiết, 10% là **20.001,5** VND. Làm tròn xuống cho kết quả **20.001 VND**.

Ví dụ khác: 10% của **500.010** là 50.001 VND; áp trần 50.000 thì kỳ vọng là **50.000 VND**. Nếu bỏ bước áp trần, hàm sẽ trả 50.001 và ca kiểm thử có thể phát hiện lỗi.

Việc tính tay từ yêu cầu và ghi rõ phép biến đổi tạo ra một **oracle độc lập ở mức đặc tả**. Không lấy kết quả chương trình đang kiểm thử làm chuẩn cho chính nó.

## 4. Chọn dữ liệu theo lớp tương đương và giá trị biên

**Phân lớp tương đương (equivalence partitioning)** nhóm những đầu vào dự kiến kích hoạt hành vi tương tự. **Phân tích giá trị biên (boundary value analysis)** tập trung vào điểm chuyển giữa các lớp.

Với yêu cầu vừa nêu, có các vùng đáng chú ý:

| Phân lớp | Giá trị đại diện | Lý do cần kiểm tra |
| --- | --- | --- |
| Tổng tiền âm | -1 | Bị từ chối; không tính giảm giá cho dữ liệu sai. |
| Tổng tiền bằng 0 | 0 | Giá trị hợp lệ nhỏ nhất. |
| Dưới ngưỡng áp dụng | 199.999 | Chưa được giảm dù là khách thân thiết. |
| Bằng ngưỡng áp dụng | 200.000 | Phải bắt đầu áp dụng mức 5% hoặc 10%. |
| Ngay trên ngưỡng | 200.001 | Phát hiện điều kiện so sánh và lỗi biên. |
| Phần trăm không ra VND nguyên | 200.015 | Phát hiện làm tròn sai hoặc cắt số sai thứ tự. |
| Trước trần 10% | 499.999 | Giảm 49.999 VND sau khi làm tròn xuống. |
| Bằng trần 10% | 500.000 | Giảm đúng 50.000 VND. |
| Sau trần 10% | 500.010 | Không được vượt quá 50.000 VND. |
| Bằng trần 5% | 1.000.000 | Khách thông thường đạt trần giảm 50.000 VND. |
| Tổng tiền tối đa hợp lệ | 2.000.000.000 | Giá trị lớn nhưng vẫn phải tính được an toàn. |
| Lớn hơn tối đa | 2.000.000.001 | Bị từ chối thay vì tính sai hoặc tràn số. |

Không nhất thiết kiểm tra mọi số nguyên trong đoạn rộng như vậy. Mục tiêu là chọn những giá trị **đại diện cho hành vi khác nhau**, ưu tiên nơi sai một dấu so sánh hoặc cách làm tròn sẽ cho kết quả khác.

### Bảng ca kiểm thử kèm kết quả kỳ vọng

| ID | subtotalVnd | loyalCustomer | Kỳ vọng | Quy tắc đang kiểm tra |
| --- | ---: | :---: | ---: | --- |
| D01 | 0 | false | 0 | Đầu dưới hợp lệ. |
| D02 | 199.999 | true | 0 | Chưa đạt ngưỡng. |
| D03 | 200.000 | false | 10.000 | Đúng ngưỡng, tỷ lệ 5%. |
| D04 | 200.000 | true | 20.000 | Đúng ngưỡng, tỷ lệ 10%. |
| D05 | 200.001 | false | 10.000 | Ngay trên ngưỡng, làm tròn xuống. |
| D06 | 200.015 | true | 20.001 | Phần lẻ khi tính 10%. |
| D07 | 499.999 | true | 49.999 | Chưa đạt trần 10%. |
| D08 | 500.000 | true | 50.000 | Đúng trần 10%. |
| D09 | 500.010 | true | 50.000 | Trên trần, phải giới hạn. |
| D10 | 999.999 | false | 49.999 | Chưa đạt trần 5%. |
| D11 | 1.000.000 | false | 50.000 | Đúng trần 5%. |
| D12 | 2.000.000.000 | true | 50.000 | Giới hạn trên hợp lệ. |
| D13 | -1 | true | IllegalArgumentException | Tổng tiền âm. |
| D14 | 2.000.000.001 | false | IllegalArgumentException | Vượt giới hạn trên. |

Các kết quả trong bảng là **giá trị kỳ vọng suy từ đặc tả**, không phải sản phẩm của hàm đã viết. Với các ca lỗi, kỳ vọng là **loại ngoại lệ**, không phải một giá trị số.

Một bảng như vậy giúp người review hỏi: “Nếu đổi điều kiện từ **>= 200.000** thành **> 200.000**, ca nào sẽ thất bại?” Câu trả lời là ít nhất **D03 và D04**.

## 5. Mã Java minh họa và sự khác nhau giữa chạy được với đúng

Một implementation Java 17 cho đặc tả trên:

~~~java
public final class DiscountCalculator {
    private static final long MIN_SUBTOTAL = 0L;
    private static final long MAX_SUBTOTAL = 2_000_000_000L;
    private static final long ELIGIBLE_THRESHOLD = 200_000L;
    private static final long DISCOUNT_CAP = 50_000L;

    private DiscountCalculator() {
    }

    public static long calculate(long subtotalVnd, boolean loyalCustomer) {
        if (subtotalVnd < MIN_SUBTOTAL || subtotalVnd > MAX_SUBTOTAL) {
            throw new IllegalArgumentException("Subtotal is out of range");
        }

        if (subtotalVnd < ELIGIBLE_THRESHOLD) {
            return 0L;
        }

        int percent = loyalCustomer ? 10 : 5;
        long rawDiscount = subtotalVnd * percent / 100L;
        return Math.min(rawDiscount, DISCOUNT_CAP);
    }
}
~~~

Vì tổng tiền đã được giới hạn tối đa 2.000.000.000 và phần trăm tối đa 10, phép nhân bằng **long** vẫn nằm trong miền biểu diễn của long. Phép chia nguyên cho **100** thực hiện làm tròn xuống đúng với số không âm trong đặc tả.

Nếu bỏ giới hạn đầu vào hoặc đổi kiểu dữ liệu, phải đánh giá lại nguy cơ **tràn số**. Đối với bài toán tiền tệ thực tế, đơn vị nhỏ nhất, cách làm tròn và loại số cần thống nhất với hợp đồng nghiệp vụ.

Mã này ngắn, nhưng chỉ nhìn vào implementation không đủ chứng minh quy tắc đúng. Bằng chứng đến từ **đặc tả độc lập, dữ liệu phân biệt sai lệch và assertion cụ thể**.

## 6. Viết assertion dựa trên kỳ vọng, không dựa trên code đang kiểm thử

Một kiểm thử yếu:

~~~java
// SAI: dùng cùng phương thức để tính cả actual và expected.
long actual = DiscountCalculator.calculate(200_015L, true);
long expected = DiscountCalculator.calculate(200_015L, true);
assertEquals(expected, actual);
~~~

Nếu implementation làm tròn sai, cả actual và expected đều sai theo cùng một cách. Test vẫn xanh.

Một kiểm thử có giá trị:

~~~java
long actual = DiscountCalculator.calculate(200_015L, true);

// Kỳ vọng 20.001 đã được tính độc lập từ quy tắc 10%,
// làm tròn xuống VND nguyên.
assertEquals(20_001L, actual);
~~~

Bằng chứng càng rõ khi ca test liên hệ với **một quy tắc được công bố**. Việc hard-code số kỳ vọng không tự động tạo ra chất lượng: cần biết số đó được suy ra từ đâu và có được review với nghiệp vụ hay không.

**Không nên:**

- Viết test chỉ để khẳng định hàm không ném ngoại lệ, khi nghiệp vụ đòi hỏi giá trị cụ thể.
- Copy công thức trong implementation sang test rồi gọi đó là một oracle độc lập.
- Thay số expected theo kết quả thực tế chỉ để test xanh mà không kiểm chứng đặc tả.
- Dùng cùng một cấu hình sai hoặc cùng bộ dữ liệu sai cho cả hệ thống tham chiếu và hệ thống đang kiểm thử.

## 7. Biến bảng kỳ vọng thành kiểm thử JUnit 5

Ví dụ kiểm thử tham số hóa. Phần này cần **JUnit Jupiter** và **junit-jupiter-params** trong môi trường kiểm thử của dự án.

~~~java
import static org.junit.jupiter.api.Assertions.*;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.CsvSource;
import org.junit.jupiter.params.provider.ValueSource;

class DiscountCalculatorTest {
    @ParameterizedTest(
            name = "subtotal={0}, loyal={1}, expected={2}")
    @CsvSource({
            "0, false, 0",
            "199999, true, 0",
            "200000, false, 10000",
            "200000, true, 20000",
            "200001, false, 10000",
            "200015, true, 20001",
            "499999, true, 49999",
            "500000, true, 50000",
            "500010, true, 50000",
            "999999, false, 49999",
            "1000000, false, 50000",
            "2000000000, true, 50000"
    })
    void matchesBusinessExamples(
            long subtotal, boolean loyal, long expected) {
        assertEquals(expected,
                DiscountCalculator.calculate(subtotal, loyal));
    }

    @ParameterizedTest
    @ValueSource(longs = {-1L, 2_000_000_001L})
    void rejectsOutOfRangeSubtotal(long subtotal) {
        assertThrows(IllegalArgumentException.class,
                () -> DiscountCalculator.calculate(subtotal, true));
    }

    @Test
    void loyaltyNeverReducesDiscountForSameValidAmount() {
        long subtotal = 300_000L;

        assertTrue(
                DiscountCalculator.calculate(subtotal, true)
                >= DiscountCalculator.calculate(subtotal, false));
    }
}
~~~

Kiểm thử tham số hóa giúp giữ **dữ liệu thử và kỳ vọng** ở cùng một nơi, đồng thời giảm trùng lặp cấu trúc Arrange–Act–Assert. Dòng dữ liệu cũng dễ đối chiếu với bảng nghiệp vụ khi review.

Nhưng **số dòng dữ liệu không tự bảo đảm độ tin cậy**. Nếu toàn bộ expected trong bảng bị tính sai do hiểu nhầm đặc tả, việc test xanh chỉ cho thấy code và bảng cùng phù hợp với một cách hiểu sai.

Bên cạnh test unit cho hàm thuần, với API thật còn cần test cho **parse đầu vào, phân quyền, ghi dữ liệu, tác dụng phụ và phản hồi lỗi**.

## 8. Kết quả kỳ vọng không chỉ là giá trị trả về

Khi thao tác có tác dụng phụ, kết quả đúng còn gồm **trạng thái** và **điều không được xảy ra**.

Ví dụ lệnh hoàn tiền: API trả HTTP 200 chưa chắc đủ chứng minh hoàn tiền đúng. Cần kiểm tra:

| Khía cạnh | Kỳ vọng cần nêu |
| --- | --- |
| **Giá trị hoặc response** | Trả mã giao dịch và trạng thái theo hợp đồng. |
| **Trạng thái lưu trữ** | Tổng tiền đã hoàn không vượt số tiền được phép hoàn. |
| **Tác dụng phụ** | Lệnh thanh toán được gửi đúng số lần theo cơ chế chống lặp. |
| **Trường hợp từ chối** | Đơn chưa thanh toán bị từ chối; không tạo bản ghi hoàn tiền hợp lệ giả. |
| **Trường hợp timeout** | Không kết luận chắc chắn giao dịch chưa diễn ra; có cách tra cứu hoặc đối soát. |
| **Dữ liệu không liên quan** | Trạng thái đơn khác và số dư tài khoản khác không bị sửa. |

Một test chỉ kiểm tra **assertNotNull(response)** có thể bỏ qua lỗi ghi dữ liệu sai. Ngược lại, assertion về “không có side effect” có thể là phần quan trọng nhất của ca đầu vào không hợp lệ.

Ví dụ mô hình kiểm tra một thao tác ở mức cao:

~~~java
// Ý tưởng kiểm thử tích hợp (các dependency là giả định):
// 1. Sắp xếp một đơn chưa thanh toán.
// 2. Gọi refundService.refund(orderId).
// 3. Khẳng định nhận BusinessRejectedException.
// 4. Khẳng định paymentGateway chưa bị gọi.
// 5. Khẳng định dữ liệu hoàn tiền không được tạo.
~~~

Đây là **mô tả mục tiêu kiểm thử**, không phải đoạn chương trình chạy độc lập. Ở dự án thật, phương thức và công cụ giám sát lời gọi phụ thuộc vào kiến trúc cụ thể.

## 9. Dữ liệu trạng thái và thứ tự sự kiện cũng là dữ liệu thử

Với hàm thuần, dữ liệu thử thường là tham số. Với hệ thống có CSDL hoặc nhiều dịch vụ, **bối cảnh trước khi chạy** cũng quyết định kết quả.

Giả sử kiểm thử chuyển trạng thái đơn từ PENDING sang PAID:

- Đơn đang PENDING → được phép thanh toán.
- Đơn đã PAID → không tạo giao dịch thanh toán mới khi gọi lặp.
- Đơn CANCELLED → từ chối.
- Hai yêu cầu thanh toán chạy gần nhau → phải bảo vệ khỏi xử lý trùng.
- Dịch vụ thanh toán nhận yêu cầu nhưng phản hồi bị mất → kết quả có thể chưa xác định.

Trong các trường hợp này, chỉ thay đổi một tham số **orderId** không đủ. Bộ dữ liệu cần mô tả **trạng thái khởi tạo**, các yêu cầu đã xảy ra, quyền, thời gian và kết quả của phụ thuộc.

### Chất lượng test fixture

**Fixture** là tập dữ liệu và bối cảnh chuẩn bị trước một ca kiểm thử. Một fixture tốt nên:

1. Tạo đủ dữ liệu để hành vi được kiểm thử có thể xảy ra.
2. Không tạo nhiều đối tượng không liên quan, gây khó hiểu điều kiện quyết định.
3. Làm rõ trạng thái nào là yếu tố chính để phân biệt kết quả.
4. Không chia sẻ trạng thái mutable khiến test này phụ thuộc test khác.
5. Có cơ chế dọn dẹp hoặc rollback phù hợp khi ghi ra CSDL test.

Một test chỉ chạy khi **đã có người dùng với ID cố định trong database của lập trình viên** là bằng chứng yếu: kết quả không tái lập khi chạy trên CI hoặc máy khác.

## 10. Dữ liệu âm, dữ liệu bất thường và hành vi bảo vệ

Dữ liệu thử tốt cần bao gồm những trường hợp hệ thống **phải từ chối hoặc xử lý an toàn**, không chỉ dữ liệu hợp lệ.

| Dạng dữ liệu | Ví dụ | Điều cần kiểm chứng |
| --- | --- | --- |
| **Thiếu hoặc null** | Không có mã sản phẩm, body null. | Phản hồi validation hoặc hành vi đã công bố. |
| **Rỗng hoặc khoảng trắng** | Chuỗi rỗng, nhiều dấu cách. | Có chấp nhận/chuẩn hóa theo hợp đồng không? |
| **Biên số học** | -1, 0, giá trị max và max+1. | Không vượt miền hoặc tràn số. |
| **Unicode** | Ký tự có dấu, emoji, chuỗi kết hợp. | Xử lý độ dài, chuẩn hóa và hiển thị đúng. |
| **Ngày giờ và múi giờ** | Cuối tháng, ngày nhuận, thời điểm đổi ngày. | Không phụ thuộc sai vào timezone hoặc giờ máy. |
| **Mảng lớn hoặc nested** | Danh sách ở giới hạn và vượt giới hạn. | Từ chối hoặc xử lý theo tài nguyên cho phép. |
| **Giá trị tương quan sai** | Ngày kết thúc trước ngày bắt đầu. | Phát hiện vi phạm liên trường. |
| **Trạng thái không hợp lệ** | Hoàn tiền cho đơn chưa thanh toán. | Không ghi dữ liệu và báo lỗi đúng loại. |
| **Lỗi phụ thuộc** | Timeout, mất kết nối, trả phản hồi không hợp lệ. | Không biến thành kết quả nghiệp vụ sai hoặc thử lại không an toàn. |

Không có một danh sách “đầu vào xấu” phù hợp mọi API. Hãy chọn theo **hợp đồng**, **đường đi** và **tác hại của việc xử lý sai**. Ví dụ một chuỗi Unicode phức tạp quan trọng hơn trong chức năng xử lý tên người dùng so với hàm tính tổng hai số nguyên.

## 11. Làm sao tạo kết quả kỳ vọng khi khó tính chính xác?

Không phải mọi đầu ra đều dễ tính tay. Với thuật toán lớn hoặc tích hợp nhiều bước, có thể dùng những loại **test oracle** khác nhau:

| Loại oracle | Cách sử dụng | Giới hạn cần nhớ |
| --- | --- | --- |
| **Đặc tả và ví dụ nghiệp vụ** | Định nghĩa kết quả đã được chủ sản phẩm, chuyên gia miền hoặc tài liệu hợp đồng chấp nhận. | Đặc tả có thể thiếu trường hợp biên hoặc hiểu sai. |
| **Tính toán độc lập** | Dùng một cách suy luận/công cụ khác để xác định kết quả. | Cần tránh sao chép công thức và lỗi từ code đang thử. |
| **Implementation tham chiếu** | So sánh với hệ thống đã được kiểm chứng ở phạm vi phù hợp. | Hệ thống tham chiếu cũng có thể có bug hoặc quy tắc cũ. |
| **Golden file / snapshot** | Lưu output đã được review để phát hiện thay đổi bất ngờ. | Dễ “approve lại” cả lỗi nếu không xem nội dung khác biệt. |
| **Bất biến (invariant)** | Xác nhận điều luôn phải đúng, ví dụ giảm giá không vượt trần. | Bất biến cần thiết nhưng có thể chưa chỉ ra giá trị đúng chính xác. |
| **Quan hệ biến hình (metamorphic relation)** | Kiểm tra quan hệ giữa nhiều lần chạy, ví dụ tăng tổng tiền không làm giảm mức giảm trong cùng chính sách. | Nhiều implementation sai vẫn có thể thỏa mãn quan hệ. |
| **Kết quả từ hệ thống bên ngoài** | Đối soát dữ liệu hoặc sự kiện với một nguồn đáng tin cậy. | Phụ thuộc thời gian, độ mới của dữ liệu và tính toàn vẹn của nguồn. |

Ví dụ với DiscountCalculator:

- **Kỳ vọng cụ thể:** 200.015 VND, khách thân thiết → **20.001 VND**.
- **Bất biến:** Kết quả luôn nằm trong **0 đến 50.000 VND** với đầu vào hợp lệ.
- **Quan hệ biến hình:** Với cùng loại khách và đầu vào hợp lệ, tăng tổng tiền không được làm giảm số tiền giảm trong chính sách này.

Cả ba bổ sung cho nhau. Một implementation luôn trả **0** thỏa bất biến **0 ≤ discount ≤ 50.000** và tính không giảm khi subtotal tăng, nhưng vẫn sai ở mọi đơn đủ điều kiện. Vì vậy, **không thay thế các kết quả kỳ vọng cụ thể bằng những thuộc tính quá yếu**.

## 12. Dữ liệu ngẫu nhiên và property-based testing

Sinh dữ liệu tự động có thể mở rộng phạm vi khám phá trường hợp mà người viết chưa nghĩ tới. Tuy nhiên, sinh nhiều giá trị từ một miền không bảo đảm chúng rơi vào những điểm quyết định.

Ví dụ, nếu sinh subtotal đều trong khoảng 1 triệu đến 2 triệu, hầu hết trường hợp đều đã chạm trần giảm giá, khó phát hiện lỗi ở ngưỡng 200.000 hoặc lỗi làm tròn.

Kết hợp hợp lý:

1. **Ví dụ cố định có expected rõ ràng** ở ngưỡng 200.000, trần 500.000/1.000.000 và các giá trị ngay quanh biên.
2. **Dữ liệu sinh tự động** trong các phân vùng đã xác định, gồm cả giá trị hợp lệ và bất hợp lệ.
3. **Thuộc tính có ý nghĩa** được suy ra từ quy tắc, không chỉ khẳng định rằng kết quả không null.
4. **Ghi seed hoặc trường hợp thất bại đã rút gọn** để có thể tái lập lỗi.
5. **Giới hạn và phân phối phù hợp** để dữ liệu được sinh không tập trung hết vào những vùng kém giá trị.

Ví dụ một kiểm tra thuộc tính có phạm vi hữu hạn:

~~~java
import static org.junit.jupiter.api.Assertions.*;

import org.junit.jupiter.api.Test;

class DiscountPropertiesTest {
    @Test
    void discountIsBoundedAndLoyaltyDoesNotReduceIt() {
        long[] samples = {
                0L, 199_999L, 200_000L, 200_015L,
                499_999L, 500_000L, 999_999L,
                1_000_000L, 2_000_000_000L
        };

        for (long subtotal : samples) {
            long standard = DiscountCalculator.calculate(subtotal, false);
            long loyal = DiscountCalculator.calculate(subtotal, true);

            assertTrue(standard >= 0L && standard <= 50_000L);
            assertTrue(loyal >= 0L && loyal <= 50_000L);
            assertTrue(loyal >= standard);
        }
    }
}
~~~

Đoạn trên là **kiểm tra thuộc tính với tập dữ liệu cố định**, chưa phải một framework property-based testing có khả năng sinh và rút gọn dữ liệu. Nó bổ trợ cho các assertion kết quả cụ thể ở phần 7, không thay thế chúng.

## 13. Tránh dữ liệu thử gây kết quả không ổn định

Dữ liệu tốt cần **tái lập được**. Một số nguồn làm test lúc xanh lúc đỏ:

- Gọi **LocalDateTime.now()** hoặc đồng hồ hệ điều hành ở nhiều bước, rồi kỳ vọng mốc thời gian cố định.
- Dùng **UUID/ngẫu nhiên** nhưng không ghi lại seed hoặc dữ liệu thực tế gây lỗi.
- Phụ thuộc vào **thứ tự bản ghi CSDL** khi truy vấn không yêu cầu sắp xếp.
- Dựa trên **dữ liệu test dùng chung** có thể bị pipeline khác thay đổi.
- Dùng **API ngoài thực tế** với mạng, quota hoặc dữ liệu biến động làm oracle cho test đơn vị.
- Cố định ngày tháng nhưng không cố định **múi giờ, locale hoặc quy tắc chuyển đổi**.

Đối với logic thời gian, nên inject **Clock** hoặc cung cấp thời điểm giả định để test xác minh trước/sau hạn một cách xác định. Đối với dữ liệu ngẫu nhiên, cần seed tái lập. Đối với CSDL, mỗi test nên quản lý fixture và trạng thái riêng.

Không phải mọi kiểm thử tích hợp đều có thể loại bỏ toàn bộ biến động. Khi cần môi trường thật, phải phân biệt **thất bại của môi trường** với **kết quả nghiệp vụ sai**, đồng thời lưu log và thông tin giúp tái hiện.

## 14. Dữ liệu gần thực tế nhưng phải an toàn

Sử dụng dữ liệu đại diện cho hành vi sản xuất là cần thiết, đặc biệt với độ dài, ký tự, phân phối giá trị, trạng thái hiếm và mối quan hệ giữa nhiều bảng. Nhưng không nên sao chép tùy tiện dữ liệu người dùng thật vào test.

Những cách tiếp cận phù hợp:

- Tạo **dữ liệu tổng hợp (synthetic data)** có hình dạng và phân phối cần thiết.
- Giữ **các ràng buộc quan hệ**: đơn hàng phải tham chiếu người dùng và sản phẩm được tạo phù hợp.
- Ẩn danh theo quy trình được phê duyệt nếu bắt buộc dùng dữ liệu gốc, và đánh giá nguy cơ tái định danh.
- Tách tài khoản, token, số điện thoại và địa chỉ nhận thông báo khỏi môi trường thật.
- Khi dữ liệu giả cần mô phỏng lỗi vận hành, ghi nhận rõ **điều kiện mô phỏng** và không khiến test gửi tác dụng phụ ra bên ngoài.

Một dữ liệu nhìn “thật” nhưng có khóa ngoại sai, thiếu trạng thái lịch sử hoặc không phản ánh phân bố trường hợp biên vẫn có thể là dữ liệu thử kém chất lượng.

## 15. Bằng chứng kiểm thử tốt phải giải thích được thất bại

Khi ca kiểm thử thất bại, bản ghi cần đủ thông tin để điều tra:

| Thông tin | Ví dụ |
| --- | --- |
| **Tên ca và quy tắc** | D06 – 10%, làm tròn xuống VND nguyên. |
| **Đầu vào quan trọng** | subtotalVnd = 200.015, loyalCustomer = true. |
| **Kết quả kỳ vọng** | 20.001 VND, từ đặc tả. |
| **Kết quả thực tế** | 20.000 VND. |
| **Điều kiện chạy** | Phiên bản code, seed, cấu hình hoặc thời điểm giả định khi liên quan. |
| **Tác động phụ quan sát được** | Có/không ghi CSDL, gửi sự kiện, gọi dependency. |

Từ sai lệch **20.001 so với 20.000**, người điều tra có thể nghi ngờ cách nhân chia đã cắt phần lẻ quá sớm. Tuy vậy, không nên kết luận nguyên nhân chỉ từ một assertion: cần xem code, dữ liệu và điều kiện chạy để xác nhận.

Một kiểm thử có tên mơ hồ như **testCalculate()** và thông báo “expected true but was false” thường cung cấp ít ngữ cảnh hơn ca kiểm thử gắn với quy tắc.

### Mutation testing như một phép thử chất lượng test

Có thể đánh giá độ nhạy của bộ test bằng cách **cố tình tạo sai lệch nhỏ trong implementation**: đổi điều kiện >= thành >, đổi 10% thành 5%, bỏ giới hạn trần hoặc thay cách làm tròn.

Một bộ dữ liệu và oracle tốt phải phát hiện nhiều sai lệch có ý nghĩa:

| Sai lệch giả định | Ca dự kiến phát hiện |
| --- | --- |
| Dùng subtotalVnd > 200.000 thay vì >= | D03, D04. |
| Khách thân thiết chỉ còn giảm 5% | D04, D06, D07. |
| Làm tròn phần trăm sai | D06, D07, D10. |
| Bỏ trần 50.000 | D09, D12. |
| Chấp nhận subtotal âm | D13. |

Các dòng trên là **phân tích lý thuyết**, không phải kết quả đã chạy mutation testing. Trong thực tế, một mutant không bị phát hiện có thể chỉ ra bộ kiểm thử thiếu nhạy hoặc mutant tương đương về hành vi trên miền hợp lệ; cần xem xét trước khi kết luận.

## 16. Quy trình thiết kế dữ liệu thử và expected theo rủi ro

Có thể dùng quy trình sau cho một thay đổi nghiệp vụ cụ thể:

1. **Lấy đặc tả làm chuẩn.** Ghi rõ đầu vào hợp lệ, quy tắc tính toán, làm tròn, ngoại lệ và tác dụng phụ.
2. **Vạch phân lớp hành vi.** Phân biệt bình thường, tại ngưỡng, sát ngưỡng, ngoài miền, trạng thái và điều kiện phụ thuộc.
3. **Chọn dữ liệu có lý do.** Mỗi ca nên liên hệ với một quy tắc hoặc sai lệch muốn phát hiện.
4. **Tính expected độc lập.** Dùng ví dụ được xác nhận, tính tay, nguồn tham chiếu đã kiểm chứng hoặc bất biến phù hợp.
5. **Viết assertion đủ mạnh.** Kiểm tra giá trị, loại lỗi, trạng thái và tác dụng phụ có liên quan.
6. **Bảo đảm tái lập.** Cố định thời gian, seed, fixture, cấu hình và trạng thái khi cần.
7. **Kiểm tra chất lượng bằng thay đổi giả định.** Hỏi mỗi lỗi phổ biến sẽ làm ca nào thất bại, và ca nào đang thiếu.
8. **Cập nhật bằng chứng khi hợp đồng đổi.** Không tự đổi expected theo actual; kiểm tra lý do thay đổi và khả năng tương thích.

**Mức công sức phải tương xứng với rủi ro.** Một hàm định dạng nhãn có thể cần vài ví dụ điển hình và trường hợp biên. Một chức năng thanh toán, cấp quyền hoặc khôi phục dữ liệu cần dữ liệu trạng thái, đường thất bại và bằng chứng kiểm thử chặt chẽ hơn.

## 17. Tình huống tự luyện

### Bài 1 — Đủ dữ liệu nhưng thiếu expected

Một nhóm tạo 10.000 đơn ngẫu nhiên, gọi DiscountCalculator, rồi chỉ khẳng định rằng kết quả không âm.

**Câu hỏi:** Bộ kiểm thử có thể bỏ sót lỗi nào?

**Gợi ý:** Kết quả 0 cho mọi đơn đều không âm nhưng sai khi đủ điều kiện giảm. Cần expected cụ thể tại các điểm quyết định và kiểm tra giới hạn, tỷ lệ, làm tròn.

### Bài 2 — Tìm lỗi ở điểm chuyển nhánh

Bộ kiểm thử đang có subtotal **250.000**, **300.000** và **400.000** cho khách thường.

**Câu hỏi:** Thêm tối thiểu những giá trị nào để kiểm tra điều kiện áp dụng ngưỡng 200.000?

**Gợi ý:** Thử **199.999**, **200.000**, **200.001**; khi có hai nhóm khách cần cân nhắc cả **loyalCustomer = true/false** ở điểm quyết định.

### Bài 3 — Oracle bị phụ thuộc implementation

Test tự tính expected bằng cách gọi chính hàm đang được kiểm thử rồi đối chiếu với kết quả lần gọi thứ hai.

**Câu hỏi:** Vì sao test gần như không kiểm chứng tính đúng đắn?

**Gợi ý:** Cả hai giá trị có thể sai theo cùng cách. Phải xác định expected từ quy tắc hoặc nguồn độc lập.

### Bài 4 — Test phụ thuộc thứ tự

Một test tạo đơn với ID cố định; test tiếp theo giả định đơn ấy đã tồn tại trong database. Chạy cả suite thì xanh, chạy riêng test thứ hai thì đỏ.

**Câu hỏi:** Cần cải thiện điều gì?

**Gợi ý:** Mỗi test tự chuẩn bị fixture hoặc có cơ chế setup rõ, tách trạng thái và dọn dẹp; kết quả không phụ thuộc thứ tự các test.

### Bài 5 — Kết quả đúng nhưng tác dụng phụ sai

API hoàn tiền trả trạng thái SUCCESS theo expected nhưng gửi lệnh hoàn tiền hai lần.

**Câu hỏi:** Assertion nào còn thiếu?

**Gợi ý:** Cần kiểm tra số lần gọi nhà cung cấp, định danh giao dịch, trạng thái lưu trữ và cơ chế xử lý lặp. Chỉ so sánh response không đủ chứng minh tính đúng đắn.

---

**Ghi nhớ:** Chất lượng bằng chứng kiểm thử phụ thuộc cả **dữ liệu thử có khả năng kích hoạt sai lệch** và **kết quả kỳ vọng được xác định độc lập, đủ rõ để nhận ra sai lệch**. Hãy lựa chọn dữ liệu theo phân lớp và điểm biên, kiểm tra cả trạng thái và tác dụng phụ, giữ test có thể tái lập, rồi đối chiếu expected với yêu cầu nghiệp vụ thay vì với code đang kiểm thử.
