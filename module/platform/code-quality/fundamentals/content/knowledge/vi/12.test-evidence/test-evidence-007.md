# Kiểm thử chạy qua mã nhưng không phát hiện lỗi

Một bộ kiểm thử có thể chạy thành công, báo độ bao phủ mã cao và vẫn bỏ lọt lỗi nghiệp vụ nghiêm trọng. Lý do là **việc thực thi một dòng mã không đồng nghĩa với việc kiểm chứng dòng mã ấy cho kết quả đúng**. Kiểm thử chỉ phát hiện lỗi khi nó tạo ra tình huống làm lỗi bộc lộ, có cơ chế xác định kết quả mong đợi và khẳng định đủ mạnh để nhận ra sự sai khác.

Bài học thuộc chương **Bằng chứng kiểm thử** của **CODE_QUALITY_FUNDAMENTALS**. Mục tiêu của module là hiểu những thuộc tính quyết định mã nguồn có **đáng tin cậy, dễ hiểu và dễ thay đổi** hay không. Trọng tâm ở đây là cách đọc bằng chứng kiểm thử một cách đúng đắn: phân biệt **mã được chạy qua** với **hành vi được kiểm chứng**, tìm những ca kiểm thử “xanh” nhưng yếu và cải thiện khả năng phát hiện hồi quy.

## 1. Một bài kiểm thử cần chứng minh điều gì?

Một bài kiểm thử hữu ích thường có ba phần:

1. **Arrange — Chuẩn bị:** tạo dữ liệu đầu vào, trạng thái hoặc phụ thuộc cần thiết.
2. **Act — Thực hiện:** gọi hành vi đang kiểm chứng.
3. **Assert — Đối chiếu:** so sánh kết quả quan sát được với điều kiện đúng đã xác định trước.

Ví dụ, quy tắc nghiệp vụ là: **đơn hàng từ 500.000 VND trở lên được miễn phí vận chuyển**. Một bài test không chỉ cần gọi hàm với đơn 500.000 VND, mà còn cần xác nhận **phí trả về bằng 0 VND**.

Nếu test chỉ gọi hàm mà không kiểm tra kết quả, nó có thể chứng minh “hàm không ném ngoại lệ trong lần chạy này”, nhưng không chứng minh hàm đã tính phí đúng.

### 1.1. Bốn câu hỏi quan trọng

| Câu hỏi | Nếu câu trả lời là “không” |
| --- | --- |
| Test có **đưa mã vào tình huống liên quan đến lỗi** không? | Nhánh lỗi, điều kiện biên hoặc trạng thái cần kiểm tra có thể chưa xuất hiện |
| Test có **quan sát được hệ quả của lỗi** không? | Lỗi có thể xảy ra nhưng không thể nhìn thấy từ điểm khẳng định |
| Test có **biết kết quả mong đợi độc lập với mã đang thử** không? | Nó có thể so sánh hai giá trị sai giống nhau và vẫn qua |
| Test có **thất bại khi kết quả sai** không? | Khẳng định quá yếu hoặc ngoại lệ bị nuốt có thể khiến test xanh giả |

Ba yếu tố đầu thường được gọi lần lượt là **khả năng kích hoạt**, **khả năng quan sát** và **test oracle** — cơ sở để quyết định điều gì là đúng. Việc khẳng định và báo lỗi đúng cách khiến sai lệch thực sự làm bài test thất bại.

## 2. Coverage cho biết mã đã được thực thi, không cho biết đã được kiểm chứng

**Code coverage** là nhóm chỉ số mô tả phần mã đã được thực thi khi chạy các bài kiểm thử. Coverage hỗ trợ phát hiện vùng chưa được chạm tới, nhưng không trực tiếp đo chất lượng các khẳng định.

| Phép đo | Nó phản ánh điều gì? | Điều không thể kết luận |
| --- | --- | --- |
| **Line coverage** | Những dòng thực thi nào đã được chạy qua | Kết quả của các dòng đó có được kiểm chứng không |
| **Statement coverage** | Những câu lệnh được công cụ tính đã được thực thi hay chưa | Các trường hợp dữ liệu và lỗi đã đủ chưa |
| **Branch coverage** | Các nhánh điều khiển được mô hình hóa đã đi qua bao nhiêu hướng | Đã thử mọi giá trị biên hoặc điều kiện con chưa |
| **Method coverage** | Phương thức nào được gọi ít nhất một lần | Mọi hành vi của phương thức đã được xác nhận chưa |
| **Condition/decision coverage** | Một số giá trị logic của điều kiện/quyết định đã được xem xét | Các tổ hợp quan trọng hoặc ảnh hưởng độc lập của từng điều kiện đều đã chứng minh chưa |
| **Path coverage** | Những đường đi thực thi đã được xét đến | Mọi đường đi đều khả thi hoặc có thể kiểm thử hết trong chương trình thực không |

Cách đếm branch, condition và path **khác nhau tùy công cụ, ngôn ngữ, compiler và cách biểu diễn bytecode**. Không nên giả định hai báo cáo từ hai công cụ có cùng quy tắc. Với Java, các trình đo coverage dựa trên bytecode có thể báo nhiều nhánh hơn số câu lệnh **if** người đọc nhìn thấy.

Một kết quả “100% line coverage” có nghĩa các dòng được tính trong phạm vi báo cáo đã được đi qua, **không phải** phần mềm không có lỗi.

### 2.1. Vì sao coverage cao và hiệu quả phát hiện lỗi là hai thứ khác nhau?

Một dòng như:

~~~java
return subtotalVnd > 500_000L ? 0L : 30_000L;
~~~

có thể được chạy với cả đơn 400.000 VND và đơn 600.000 VND. Hai kết quả đều đúng nên test qua, nhưng trường hợp **đúng 500.000 VND** vẫn sai.

Lỗi không nằm ở nhánh hoàn toàn chưa được chạy. Nó nằm ở **ranh giới phân chia giữa hai nhánh**. Muốn bắt lỗi, phải chọn dữ liệu đầu vào ở ngưỡng và khẳng định phí được miễn.

## 3. Ví dụ đầy đủ: độ bao phủ tốt nhưng vẫn bỏ sót lỗi điều kiện biên

### 3.1. Đặc tả nghiệp vụ

Giả sử phí vận chuyển:

- Tổng tiền đơn hàng không âm.
- Nếu tổng tiền **từ 500.000 VND trở lên**, phí là **0 VND**.
- Nếu tổng tiền dưới ngưỡng, phí là **30.000 VND**.

Phiên bản Java sau chứa một lỗi cố ý:

~~~java
final class ShippingPolicy {
    private static final long FREE_THRESHOLD_VND = 500_000L;
    private static final long STANDARD_FEE_VND = 30_000L;

    static long feeVnd(long subtotalVnd) {
        if (subtotalVnd < 0L) {
            throw new IllegalArgumentException(
                    "subtotalVnd must not be negative");
        }

        // BUG: đáng lẽ phải là >= thay vì >.
        if (subtotalVnd > FREE_THRESHOLD_VND) {
            return 0L;
        }
        return STANDARD_FEE_VND;
    }
}
~~~

Lỗi: với **subtotalVnd = 500_000L**, hàm trả 30.000 VND, trái với quy tắc “từ ... trở lên”.

### 3.2. Bộ test chạy qua cả hai hướng nhưng bỏ qua đúng ngưỡng

Ví dụ JUnit 5:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import org.junit.jupiter.api.Test;

class ShippingPolicyIncompleteTest {
    @Test
    void waivesFeeAboveThreshold() {
        assertEquals(0L, ShippingPolicy.feeVnd(600_000L));
    }

    @Test
    void chargesFeeBelowThreshold() {
        assertEquals(30_000L, ShippingPolicy.feeVnd(400_000L));
    }

    @Test
    void rejectsNegativeSubtotal() {
        assertThrows(IllegalArgumentException.class,
                () -> ShippingPolicy.feeVnd(-1L));
    }
}
~~~

Bộ test này chạy qua:

- Nhánh xác thực đầu vào âm và không âm.
- Nhánh miễn phí khi giá trị lớn hơn ngưỡng.
- Nhánh tính phí tiêu chuẩn khi giá trị dưới ngưỡng.

Theo phép đo nhánh cơ bản của đoạn mã này, các hướng chính đều được chạy. Một báo cáo coverage có thể vì thế rất cao, thậm chí bao phủ toàn bộ các nhánh được tính. **Tuy nhiên, không test nào gọi mức 500.000 VND**, nên cả ba test vẫn qua dù chính sách thực tế sai ở mức đó.

### 3.3. Thêm khẳng định ở đúng điểm có rủi ro

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;

import org.junit.jupiter.api.Test;

class ShippingPolicyBoundaryTest {
    @Test
    void waivesFeeAtExactThreshold() {
        assertEquals(0L, ShippingPolicy.feeVnd(500_000L));
    }

    @Test
    void chargesFeeJustBelowThreshold() {
        assertEquals(30_000L, ShippingPolicy.feeVnd(499_999L));
    }

    @Test
    void waivesFeeJustAboveThreshold() {
        assertEquals(0L, ShippingPolicy.feeVnd(500_001L));
    }
}
~~~

Test **waivesFeeAtExactThreshold** thất bại với bản triển khai có lỗi. Để sửa, cần thay:

~~~java
if (subtotalVnd > FREE_THRESHOLD_VND) {
~~~

bằng:

~~~java
if (subtotalVnd >= FREE_THRESHOLD_VND) {
~~~

Sau khi sửa, test biên cùng các test trước đó giúp chứng minh quy tắc đã được thực hiện đúng tại những đầu vào cụ thể. Chúng vẫn **không chứng minh mọi trường hợp của toàn hệ thống**: có thể còn quy tắc thuế, khuyến mãi, giá trị vượt giới hạn hoặc vấn đề tích hợp cần bằng chứng riêng.

**Bài học cốt lõi:** coverage nhắc rằng mã đã chạy; **lựa chọn dữ liệu ở ngưỡng và test oracle độc lập** giúp phát hiện lỗi.

## 4. Những kiểu test “xanh” nhưng không đủ sức phát hiện lỗi

### 4.1. Test chỉ kiểm tra không có ngoại lệ

~~~java
@Test
void smokeTest() {
    assertDoesNotThrow(() -> ShippingPolicy.feeVnd(500_000L));
}
~~~

Test này qua ngay cả khi phí vận chuyển trả về 30.000 VND. Nó chỉ chứng minh phép gọi không phát sinh ngoại lệ trong trường hợp đó. Nếu mục tiêu là **kiểm tra smoke test để biết chương trình khởi động**, điều này có thể phù hợp. Nếu mục tiêu là **kiểm chứng tính đúng của phí**, nó chưa đủ.

Nên thêm khẳng định giá trị nghiệp vụ:

~~~java
assertEquals(0L, ShippingPolicy.feeVnd(500_000L));
~~~

### 4.2. Test chỉ assert kết quả không null hoặc có giá trị “trông hợp lý”

~~~java
@Test
void returnsFee() {
    long fee = ShippingPolicy.feeVnd(500_000L);
    assertTrue(fee >= 0L);
}
~~~

Phí 0 VND và 30.000 VND đều không âm, nên test không phát hiện sai khác. Dạng khẳng định rộng như “giá không âm” hữu ích cho **bất biến tổng quát**, nhưng không thể thay thế việc khẳng định quy tắc miễn phí tại ngưỡng.

Một bộ kiểm thử tốt có thể có **cả hai loại**: khẳng định nghiệp vụ chính xác cho các trường hợp then chốt và kiểm tra bất biến cho không gian đầu vào rộng.

### 4.3. Test so sánh kết quả với chính nó

~~~java
long actual = ShippingPolicy.feeVnd(500_000L);
assertEquals(actual, actual);
~~~

Khẳng định này không mang thông tin độc lập về hành vi. Nó sẽ qua với mọi giá trị `long` trả về và không thể kiểm tra phí đúng. Lỗi tương tự xảy ra khi tính **expected** bằng cùng biểu thức sai đã sao chép nguyên từ mã đang thử.

**Expected phải bắt nguồn từ đặc tả, bảng quyết định, ví dụ đã được xác nhận hoặc một nguồn đáng tin độc lập**, không phải từ chính hàm cần kiểm tra.

### 4.4. Test có thao tác nhưng không có khẳng định quan sát được

~~~java
@Test
void executesCalculation() {
    ShippingPolicy.feeVnd(500_000L);
}
~~~

Trường hợp này có thể tăng coverage nhưng không kiểm tra giá trị trả về. Với một phương thức **void**, đôi khi cần kiểm tra thay đổi trạng thái, dữ liệu ghi, thông điệp gửi hoặc hành vi quan sát được ở ranh giới tương ứng. Không phải cứ thêm một khẳng định bất kỳ là đủ.

### 4.5. Ngoại lệ bị nuốt, bài test vẫn hoàn tất bình thường

~~~java
@Test
void dangerousExceptionHandling() {
    try {
        performOperation();
    } catch (Exception ignored) {
        // Không fail test, nên lỗi bất ngờ có thể bị bỏ qua.
    }
}
~~~

Nếu lỗi của `performOperation()` phải được coi là thất bại, cách bắt và bỏ qua ngoại lệ sẽ cho phép test xanh dù thao tác không thành công. Nên để ngoại lệ lan ra, hoặc dùng `assertThrows` **chỉ khi ngoại lệ đó là kết quả mong đợi**, đồng thời kiểm tra loại lỗi và điều kiện thích hợp.

### 4.6. Mock xác nhận tương tác mà không xác nhận kết quả nghiệp vụ

Giả sử test xác nhận `repository.save(...)` được gọi một lần. Điều đó có thể quan trọng nếu hợp đồng yêu cầu lưu đúng một lần, nhưng nó không chứng minh dữ liệu được lưu có **số tiền, chủ sở hữu hoặc trạng thái chính xác**.

Nếu đối tượng ghi chứa dữ liệu quan trọng, cần kiểm tra nội dung tham số, trạng thái sau thao tác hoặc kết quả ở ranh giới có ý nghĩa. Đồng thời không nên khóa chặt những lời gọi nội bộ không phải hợp đồng; test quá phụ thuộc triển khai sẽ dễ vỡ khi refactor an toàn.

### 4.7. Test chỉ kiểm tra kích thước tập kết quả

Kiểm tra danh sách có ba phần tử không chứng minh đó là **ba phần tử đúng** hoặc chúng thuộc đúng người dùng. Với nghiệp vụ có phân quyền, chỉ kiểm tra **size** có thể bỏ sót lỗi trả dữ liệu của người khác.

Nên kiểm tra các thuộc tính có giá trị nghiệp vụ: mã bản ghi, chủ sở hữu, thứ tự nếu hợp đồng yêu cầu, trạng thái và giới hạn quyền truy cập.

### 4.8. Dữ liệu thử quá giống nhau

Nếu mọi ca đều dùng một khách VIP, cùng một mức tiền cao hơn ngưỡng và cùng một loại sản phẩm, chúng có thể lặp lại một đường đi dù số lượng test lớn. Nên thiết kế **phân lớp tương đương** và **giá trị biên**, đồng thời bổ sung các tổ hợp trạng thái quan trọng.

## 5. Test oracle: dựa vào đâu để biết kết quả đúng?

**Test oracle** là quy tắc hoặc nguồn thông tin cho phép đánh giá kết quả thực tế. Đối với bài tính phí, oracle là đặc tả “từ 500.000 VND trở lên miễn phí”, không phải một phép tính trích từ chính hàm đang thử.

Có nhiều nguồn oracle:

| Nguồn | Khi nào hữu ích | Nguy cơ cần tránh |
| --- | --- | --- |
| Đặc tả nghiệp vụ đã thống nhất | Phí, quyền, giới hạn, trạng thái | Đặc tả mơ hồ hoặc đã cũ |
| Ví dụ đầu vào/đầu ra được xác nhận | Trường hợp thường, biên, hồi quy lỗi | Chỉ lấy ví dụ dễ và bỏ các tình huống khó |
| Bất biến (invariant) | Tổng không âm, không tạo bản ghi trùng, không rò dữ liệu | Bất biến quá yếu không xác nhận giá trị chính xác |
| Triển khai tham chiếu độc lập | Đối chiếu thuật toán mới với bản tin cậy | Hai bản sao cùng chứa lỗi hoặc cùng phụ thuộc quy tắc sai |
| Quan hệ biến hình (metamorphic relation) | Kết quả khó biết chính xác nhưng có quan hệ phải giữ | Quan hệ được giả định mà không đúng với nghiệp vụ |
| Kết quả hệ thống bên ngoài có hợp đồng | Đối soát tích hợp hoặc tính đúng ở ranh giới | Dữ liệu chưa nhất quán, chậm cập nhật hoặc sai phiên bản |

### 5.1. Tránh xây oracle từ cùng giả thiết sai

Một test có thể tạo `expectedFee` bằng cách sao chép nguyên điều kiện `subtotal > 500_000` từ mã sản xuất. Nếu cả mã sản xuất và test đều dùng dấu **>** sai, test vẫn xanh. Đó là lỗi **chia sẻ cùng nguồn sai**.

Thay vì sao chép công thức, hãy dùng **bảng quyết định từ quy tắc nghiệp vụ**:

| Tổng đơn (VND) | Phí mong đợi (VND) | Lý do |
| ---: | ---: | --- |
| 0 | 30.000 | Dưới ngưỡng |
| 499.999 | 30.000 | Sát dưới ngưỡng |
| 500.000 | 0 | Đúng ngưỡng, được miễn |
| 500.001 | 0 | Sát trên ngưỡng |
| 800.000 | 0 | Trên ngưỡng |
| -1 | Ngoại lệ | Dữ liệu không hợp lệ |

Bảng này tạo ra kết quả mong đợi **trước khi nhìn vào cách triển khai**. Nó cũng làm rõ điểm cần xác nhận nếu yêu cầu chưa nói đến trường hợp tổng âm.

### 5.2. Bất biến bổ sung nhưng không thay thế ví dụ chính xác

Ví dụ, hệ thống báo giá có thể có bất biến:

- **amountDueVnd = subtotalVnd - discountVnd + shippingFeeVnd**
- **discountVnd ≥ 0**
- **shippingFeeVnd ≥ 0**

Những bất biến này phát hiện nhiều loại lỗi tính toán, nhưng một báo giá có phí vận chuyển 30.000 VND sai ở ngưỡng vẫn có thể thỏa bất biến tổng. Vì vậy, cần test **ngưỡng chính sách** bên cạnh kiểm tra quan hệ tổng quát.

### 5.3. Kiểm thử biến hình khi đáp án chính xác khó tính

Đối với hàm tính tổng các giá không âm, có thể dùng quan hệ: nếu thêm một dòng hàng có giá `x` không âm và không xảy ra tràn số, tổng mới phải bằng tổng cũ cộng `x`. Với chức năng tìm kiếm, một số phép biến đổi dữ liệu có thể giữ nguyên tập kết quả.

Cần chứng minh hoặc xác nhận **quan hệ đó thực sự đúng với hợp đồng**. Ví dụ, thêm một món hàng có thể làm thay đổi chiết khấu hoặc phí vận chuyển, nên quan hệ cộng tuyến tính **không nhất thiết đúng với số tiền cuối cùng**. Kiểm thử biến hình không cho phép bỏ qua các quy tắc nghiệp vụ làm thay đổi quan hệ.

## 6. Chọn dữ liệu để lỗi có cơ hội bộc lộ

### 6.1. Phân lớp tương đương

Thay vì thử ngẫu nhiên nhiều số tiền gần nhau, hãy chia thành nhóm có hành vi kỳ vọng tương tự: **âm**, **dưới ngưỡng**, **đúng ngưỡng**, **trên ngưỡng**. Từ mỗi nhóm, chọn ca đại diện và quan tâm đặc biệt đến ranh giới chuyển hành vi.

Nếu chính sách còn phụ thuộc loại khách, tình trạng đơn hoặc ngày áp dụng, phải xem các phân lớp mới và tương tác giữa điều kiện.

### 6.2. Giá trị biên

Lỗi `>` so với `>=` xuất hiện đúng tại biên. Với số nguyên, bộ ba **ngưỡng - 1, ngưỡng, ngưỡng + 1** thường hữu ích.

Không phải mọi biên đều là con số. Còn có:

- Danh sách rỗng, một phần tử, nhiều phần tử.
- Trường bắt buộc thiếu hoặc có giá trị **null**.
- Chuỗi rỗng, chỉ gồm khoảng trắng, Unicode.
- Thời gian đúng lúc hết hạn hoặc chuyển ngày, múi giờ.
- Số lớn nhất biểu diễn được, giá trị gây tràn số.
- Kết quả đúng bằng giới hạn phân trang hoặc kích thước tối đa.
- Trạng thái chuyển tiếp ngay trước/sau giao dịch hoặc timeout.

### 6.3. Tổ hợp điều kiện và thứ tự ưu tiên

Với quy tắc `vip || total >= threshold`, các tình huống **VIP dưới ngưỡng**, **không VIP đúng ngưỡng**, **không VIP trên ngưỡng** và **không VIP dưới ngưỡng** đều có ý nghĩa. Chỉ dùng toàn khách VIP có thể che mất lỗi của phần kiểm tra tổng tiền vì toán tử **||** dừng sớm.

Các mức bao phủ điều kiện hoặc phương pháp như MC/DC có thể hữu ích trong bối cảnh đòi hỏi đảm bảo nghiêm ngặt, nhưng không thay thế việc hiểu quy tắc nghiệp vụ, trạng thái đầu vào và hậu quả nếu sai.

### 6.4. Đường lỗi và sự cố

Bài test chỉ chạy đường thành công có thể bỏ sót nhiều vấn đề:

- Dịch vụ ngoài timeout sau khi đã thực hiện tác dụng phụ.
- DB trả lỗi giữa giao dịch.
- File có dòng hỏng hoặc thiếu quyền truy cập.
- Hàng đợi gửi lại cùng thông điệp.
- Hai luồng cùng sửa trạng thái dùng chung.
- Dữ liệu mới thêm một enum/status chưa được client cũ nhận biết.

Đối với đường lỗi, cần khẳng định **không chỉ có ngoại lệ**, mà còn trạng thái sau lỗi, tác dụng phụ đã xảy ra hay chưa, khả năng retry và việc giữ bất biến.

## 7. Mutation testing: phép thử đối với sức phát hiện của bộ test

**Mutation testing** cố ý tạo những thay đổi nhỏ trong mã sản xuất, gọi là **mutant**, rồi chạy test để xem bộ test có phát hiện hành vi thay đổi không. Đây là cách kiểm tra chất lượng khẳng định chứ không chỉ việc mã đã được đi qua.

Ví dụ một mutant đổi:

~~~java
if (subtotalVnd >= FREE_THRESHOLD_VND) {
~~~

thành:

~~~java
if (subtotalVnd > FREE_THRESHOLD_VND) {
~~~

Nếu bộ test gồm ca **đúng ngưỡng 500.000 VND** và khẳng định phí bằng 0, mutant bị **killed**: test thất bại vì thay đổi sai. Nếu test chỉ có 400.000 và 600.000, mutant có thể **survive**: tất cả test vẫn qua.

### 7.1. Hiểu các trạng thái mutant

| Trạng thái | Ý nghĩa thường gặp | Cách đọc |
| --- | --- | --- |
| **Killed** | Có test thất bại do mã bị biến đổi, theo quy tắc công cụ | Bằng chứng bộ test nhạy với thay đổi đó |
| **Survived** | Các test được chạy vẫn qua dù mutant tồn tại | Có thể thiếu dữ liệu, thiếu oracle hoặc mutant không đổi hành vi |
| **Not covered** | Không có test liên quan đi tới chỗ bị biến đổi theo cách công cụ đo | Vùng chưa có tác động thực thi cần chú ý |
| **Timed out / error** | Test không hoàn tất hoặc công cụ không chạy được ca tương ứng | Cần phân tích riêng, không tự đồng nhất với phát hiện lỗi nghiệp vụ |
| **Equivalent mutant** | Thay đổi cú pháp nhưng hành vi quan sát được không đổi trong phạm vi hợp đồng | Có thể không tồn tại test hợp lệ nào giết được mutant |

Ví dụ, đổi **x + 0** thành **x - 0** không làm thay đổi kết quả toán học đối với kiểu số và tình huống thông thường; một mutant tương đương như vậy có thể tồn tại mà không biểu thị test yếu. Trong thực tế, việc chứng minh tương đương cho mã tổng quát có thể khó.

**Mutation score** thường tính tỷ lệ mutant bị giết trong tập mutant được công cụ tính là hợp lệ/đủ điều kiện. Mẫu số và cách xử lý mutant không được chạy, timeout hay bị loại **phụ thuộc công cụ**; muốn so sánh số liệu phải đọc định nghĩa của báo cáo. Điểm cao là một bằng chứng hữu ích, **không phải chứng chỉ phần mềm không có lỗi**.

### 7.2. Tại sao test thực thi dòng nhưng mutant vẫn sống?

Giả sử hệ thống tính điểm thưởng:

~~~java
final class RewardPolicy {
    static long points(long subtotalVnd, boolean vip) {
        if (subtotalVnd < 0) {
            throw new IllegalArgumentException("subtotalVnd < 0");
        }

        long basePoints = subtotalVnd / 1_000L;
        return vip ? Math.multiplyExact(basePoints, 2L) : basePoints;
    }
}
~~~

Một test yếu:

~~~java
@Test
void returnsNonnegativePoints() {
    assertTrue(RewardPolicy.points(100_000L, true) >= 0L);
}
~~~

Nếu mutant thay **nhân 2** thành **nhân 1**, test vẫn qua: 100 và 200 đều không âm. Có thể cải thiện:

~~~java
@Test
void doublesVipPoints() {
    assertEquals(200L, RewardPolicy.points(100_000L, true));
}

@Test
void keepsNormalPoints() {
    assertEquals(100L, RewardPolicy.points(100_000L, false));
}
~~~

Các khẳng định mới nêu rõ **kết quả nghiệp vụ** và sẽ phát hiện thay đổi làm mất cơ chế nhân đôi. Chúng không đòi thêm nhiều dòng sản xuất được chạy; chúng **tăng độ nhạy với sai lệch** trên những dòng đã chạy.

### 7.3. Khi nào dùng mutation testing?

- Trước khi refactor một khu vực quan trọng, muốn biết test có đủ nhạy với lỗi thường gặp không.
- Khi coverage rất cao nhưng vẫn liên tục lọt bug hồi quy.
- Để định hướng bổ sung test cho điều kiện biên, phép tính hoặc nhánh có khẳng định yếu.
- Để kiểm tra test của các quy tắc tài chính, phân quyền hoặc dữ liệu có rủi ro cao.

Mutation testing có chi phí chạy đáng kể và có thể sinh mutant tương đương hoặc nhiễu do test flaky. Nên bắt đầu ở **các module/quy tắc quan trọng**, đọc từng mutant sống sót có ý nghĩa và tránh biến mutation score thành mục tiêu số học tách khỏi nhu cầu nghiệp vụ.

Trong dự án Java, công cụ như **PIT (Pitest)** có thể hỗ trợ tạo mutant và báo cáo, nhưng cần chọn phiên bản, plugin và cấu hình tương thích với dự án. Bài học này mô tả phương pháp, không yêu cầu chạy một lệnh hay công cụ cụ thể.

## 8. Từ độ bao phủ đến bằng chứng phát hiện lỗi

Có thể xem việc phát hiện lỗi qua chuỗi sau:

~~~mermaid
flowchart LR
    A[Chọn tình huống phù hợp] --> B[Thực thi đường mã liên quan]
    B --> C[Kích hoạt sai lệch]
    C --> D[Quan sát kết quả/tác dụng phụ]
    D --> E[Đối chiếu oracle độc lập]
    E --> F[Test thất bại khi sai]
~~~

Nếu thiếu một mắt xích, test có thể xanh nhưng không tạo đủ bằng chứng:

- **Không chọn đúng dữ liệu:** điều kiện biên không bị kích hoạt.
- **Không đi qua vùng liên quan:** mã có lỗi chưa được chạy.
- **Không bộc lộ sai lệch:** đường thực thi chưa tạo ra kết quả khác.
- **Không quan sát hệ quả:** tác dụng phụ nằm trong DB, hàng đợi hoặc output chưa được kiểm tra.
- **Oracle sai hoặc yếu:** expected sai, quá rộng hoặc lấy từ chính mã thử.
- **Sai lệch không làm test thất bại:** assert thiếu, bị bỏ qua, ngoại lệ bị nuốt.

Trong thực tế, những mắt xích này giúp đọc một báo cáo test thất bại hoặc survivor mutation một cách có hệ thống thay vì chỉ bổ sung ngẫu nhiên thêm test.

## 9. Kiểm thử ở nhiều cấp độ: một test xanh không bao phủ mọi ranh giới

Ngay cả một unit test mạnh cũng thường chỉ kiểm chứng logic cục bộ. Với chức năng đặt hàng, test logic tính phí **không thể tự xác nhận** SQL, API vận chuyển, giao dịch hoặc quyền truy cập.

| Cấp kiểm thử | Câu hỏi có thể trả lời tốt | Điều vẫn cần bằng chứng khác |
| --- | --- | --- |
| **Unit test** | Một quy tắc hoặc đối tượng trả kết quả đúng với đầu vào đã chọn không? | Wiring, query, I/O và trạng thái thật |
| **Component/integration test** | Các thành phần tích hợp đúng hợp đồng trong môi trường kiểm soát không? | Mọi lỗi ngoài sản xuất và cấu hình khác biệt |
| **Contract test** | Hai phía có thống nhất schema, trạng thái và ngữ nghĩa giao tiếp không? | Đối tác luôn sẵn sàng, dữ liệu nghiệp vụ luôn đúng |
| **End-to-end test** | Luồng chính qua nhiều thành phần có hoạt động theo kịch bản đã chọn không? | Toàn bộ tổ hợp đầu vào, tốc độ và lỗi hiếm |
| **Property/metamorphic test** | Bất biến hoặc quan hệ tổng quát có giữ qua nhiều dữ liệu không? | Mọi quy tắc chưa được diễn tả trong property |
| **Mutation test** | Bộ test có nhạy với những biến đổi mã được đưa vào không? | Mọi bug thực tế hoặc mọi sai lệch yêu cầu |

Không nên thay tất cả unit test bằng end-to-end test, cũng không nên chỉ mock mọi phụ thuộc rồi bỏ test tích hợp. Cần đặt khẳng định ở **ranh giới nơi hành vi có thể quan sát và được kiểm chứng**.

### 9.1. Đừng đánh đồng việc mock trả giá trị với việc hệ thống thật hoạt động

Một mock repository trả đủ dữ liệu có thể giúp kiểm chứng logic tính toán, nhưng nó không chứng minh câu SQL đúng hay transaction ghi thành công. Nếu lỗi thực tế là API trả trường thiếu, mock luôn trả object hoàn hảo sẽ không phát hiện.

Cần thiết kế test adapter với dữ liệu sai cấu trúc, timeout hoặc lỗi giao tiếp, và kiểm tra cách phần ứng dụng diễn giải các trạng thái này. Một ranh giới tốt giúp test cô lập, song **không được làm mất bằng chứng tích hợp**.

### 9.2. Kiểm tra tác dụng phụ và trạng thái sau lỗi

Ví dụ khi thao tác thanh toán timeout, test chỉ xác nhận “phương thức ném ngoại lệ” chưa đủ. Hệ thống có thể đã tạo giao dịch trước khi mất kết nối. Cần kiểm tra trạng thái **chưa xác định**, chiến lược idempotency hoặc đối soát theo hợp đồng. Với yêu cầu ghi DB, kiểm tra đúng trạng thái sau transaction quan trọng hơn chỉ kiểm tra phương thức trả về bình thường.

## 10. Dữ liệu và môi trường test có thể khiến lỗi bị che khuất

### 10.1. Fixture không đại diện cho đầu vào thực

Một bộ dữ liệu test chỉ có tên ASCII, số dương nhỏ và danh sách ngắn sẽ bỏ qua lỗi Unicode, kích thước lớn, null và cấu trúc nested. Chọn dữ liệu từ **phân loại đầu vào thực**, lịch sử lỗi và rủi ro, không phải chỉ từ những fixture dễ viết.

Không nhất thiết đưa dữ liệu khách hàng thật vào test; dữ liệu giả được thiết kế đại diện thường an toàn và dễ kiểm soát hơn.

### 10.2. Test chạy nhưng assertion không được thực thi

Ví dụ đặt assertion trong một nhánh chỉ chạy khi có dữ liệu, nhưng fixture test tạo danh sách rỗng:

~~~java
for (Order order : orders) {
    assertEquals("PAID", order.status());
}
~~~

Nếu `orders` rỗng, vòng lặp không thực thi và không có assertion nào kiểm tra trạng thái đơn hàng. Nên xác nhận điều kiện tiền đề hoặc kích thước mong đợi:

~~~java
assertFalse(orders.isEmpty(), "Expected at least one order");
for (Order order : orders) {
    assertEquals("PAID", order.status());
}
~~~

Ngược lại, nếu hợp đồng cho phép kết quả rỗng và đó chính là điều cần kiểm tra, hãy viết test riêng khẳng định **isEmpty()** với đầu vào tương ứng.

### 10.3. Một test có thể chạy nhưng bị bỏ qua phần quan trọng

Các bài test bị đánh dấu **disabled**, lọc khỏi phạm vi CI, chạy trên môi trường khác hoặc có giả định khiến test được skip sẽ không tạo bằng chứng như test đã thực sự thực hiện khẳng định. Báo cáo chất lượng phải phân biệt **passed**, **failed**, **skipped/aborted** và các trường hợp không được chọn chạy.

### 10.4. Test flaky làm yếu tín hiệu

Test phụ thuộc đồng hồ thực, thứ tự thực thi, thread scheduling hoặc dịch vụ mạng không ổn định có thể thất bại ngẫu nhiên khi mã đúng. Khi nhóm quen bỏ qua hoặc tự retry đến khi xanh, tín hiệu lỗi thực bị nhiễu. Cần cô lập phụ thuộc, kiểm soát thời gian và dữ liệu, quản lý trạng thái chung, đồng thời bảo đảm retry test không dùng để che lỗi sản phẩm.

**Test thất bại ngẫu nhiên** và **test qua dù sản phẩm sai** là hai vấn đề khác nhau; cả hai làm giảm độ tin cậy của bằng chứng kiểm thử.

## 11. Phương pháp cải thiện một bộ test có coverage cao nhưng vẫn lọt bug

### Bước 1 — Ghi lại lỗi thực theo điều kiện kích hoạt

Mô tả đầu vào, trạng thái, hành vi đúng, hành vi sai và hậu quả. Ví dụ: “đơn đúng 500.000 VND vẫn bị thu 30.000 VND; chính sách quy định miễn phí từ ngưỡng”.

### Bước 2 — Viết test hồi quy phải thất bại trên bản lỗi

Tạo test có **oracle độc lập** và dữ liệu tái hiện. Chạy test trên phiên bản đang lỗi sẽ cho bằng chứng rằng nó thật sự phân biệt đúng và sai. Nếu test vẫn xanh, phải xem lại điều kiện kích hoạt hoặc assert.

### Bước 3 — Sửa mã và xác nhận test chuyển xanh

Sửa nguyên nhân, chạy lại cả test mới lẫn bộ kiểm thử liên quan. Test hồi quy có giá trị khi nó từng **đỏ vì bug**, rồi **xanh vì sửa bug**; không nên làm test luôn xanh bằng cách đổi expected cho giống mã sai.

### Bước 4 — Tìm các trường hợp lân cận

Kiểm tra biên dưới, đúng ngưỡng, biên trên; thêm loại khách, trạng thái đơn, dữ liệu không hợp lệ hoặc tác dụng phụ nếu có ảnh hưởng. Tránh thêm hàng chục test giống nhau nhưng không mở rộng khả năng phát hiện.

### Bước 5 — Xem lại chất lượng khẳng định

Với mỗi test, tự hỏi:

- Nếu trả về sai một giá trị quan trọng, test có thất bại không?
- Nếu không ghi dữ liệu hoặc ghi nhầm đối tượng, test có phát hiện không?
- Nếu đổi toán tử, dấu so sánh, thứ tự hoặc bỏ một bước xử lý, test nào báo?
- Nếu phụ thuộc trả lỗi, việc khẳng định có chứng minh trạng thái sau lỗi an toàn không?

### Bước 6 — Kết hợp coverage với mutation và review theo rủi ro

Dùng coverage để chỉ vùng chưa chạy; dùng test oracle và mutation để tìm vùng **đã chạy nhưng thiếu sức phát hiện**; dùng review nghiệp vụ để xem yêu cầu nào chưa được kiểm chứng. Với code quan trọng, có thể bổ sung property test hoặc test tích hợp.

### Bước 7 — Giữ test dễ hiểu, đáng tin và dễ thay đổi

Tên test nên mô tả hành vi, dữ liệu fixture nhỏ nhưng có ý nghĩa, khẳng định nêu chính xác điều cần bảo vệ. Giảm phụ thuộc vào chi tiết nội bộ; test nên thất bại khi **hợp đồng bị vi phạm**, không phải vì refactor an toàn đổi thứ tự gọi hàm phụ trợ.

## 12. Ma trận kiểm thử minh họa cho chính sách vận chuyển

Giả sử chính sách thêm một điều kiện: khách VIP luôn được miễn phí vận chuyển, bất kể tổng tiền; khách thường được miễn nếu đơn từ 500.000 VND.

| Tình huống | VIP? | Tổng đơn (VND) | Phí mong đợi (VND) | Mục tiêu |
| --- | --- | ---: | ---: | --- |
| Khách thường dưới ngưỡng | Không | 499.999 | 30.000 | Nhánh có tính phí |
| Khách thường đúng ngưỡng | Không | 500.000 | 0 | Ranh giới **>=** |
| Khách thường trên ngưỡng | Không | 500.001 | 0 | Nhánh miễn phí |
| VIP dưới ngưỡng | Có | 100.000 | 0 | Đường miễn phí do VIP |
| VIP đúng ngưỡng | Có | 500.000 | 0 | Hai lý do miễn phí trùng nhau |
| Tổng tiền âm | Có/Không | -1 | Ngoại lệ | Bất biến đầu vào |

Bảng này không chỉ nhằm “đi qua các nhánh”; nó nối **quy tắc**, **đầu vào** và **kết quả mong đợi**. Khi thêm điều kiện khác, chẳng hạn trạng thái hủy đơn, cần cập nhật ma trận theo ngữ nghĩa nghiệp vụ. Có thể chuyển các hàng thành parameterized test, nhưng **dữ liệu và expected** mới là phần mang giá trị phát hiện.

## 13. Những ngộ nhận phổ biến

**“100% coverage nghĩa là không có bug.”** Không đúng. Coverage chỉ mô tả phần mã được thực thi theo quy tắc đo. Lỗi dữ liệu biên, điều kiện nghiệp vụ, trạng thái dùng chung và phụ thuộc ngoài vẫn có thể tồn tại.

**“Thêm nhiều test là tăng chất lượng.”** Chưa chắc. Nhiều test chạy cùng một đường và cùng một assertion yếu chỉ làm tăng thời gian chạy. Hãy bổ sung tình huống và oracle có ý nghĩa.

**“Có assert là đủ.”** Không đúng. Assertion phải kiểm tra thuộc tính cần bảo vệ. **assertNotNull** trên đối tượng báo giá không chứng minh số tiền đúng.

**“Đã thử cả true và false của if thì đủ.”** Không nhất thiết. Đường điều khiển đã qua nhưng biên đúng ngưỡng, tổ hợp điều kiện, trạng thái lỗi hoặc giá trị lớn vẫn có thể chưa được thử.

**“Mutation score cao là bảo đảm tuyệt đối.”** Không. Nó phụ thuộc loại mutant, công cụ, phạm vi, test flaky và mutant tương đương; đây là bằng chứng bổ sung, không thay yêu cầu nghiệp vụ.

**“Mock mọi phụ thuộc giúp test chắc chắn tin cậy.”** Mock giúp cô lập một phần trách nhiệm nhưng có thể che sai hợp đồng thật, lỗi mapping, lỗi transaction và trạng thái lỗi khi giao tiếp.

**“Test qua trên máy cá nhân chứng minh release an toàn.”** Không. Môi trường, phiên bản cấu hình, dữ liệu thực và concurrency có thể khác. Cần lựa chọn kiểm thử tích hợp, quan sát và triển khai theo mức rủi ro.

**“Expected có thể lấy từ kết quả đang chạy vì nó hiện là đúng.”** Nếu không có nguồn xác nhận độc lập, làm vậy có thể biến bug thành “golden output”. Trước khi lưu kết quả làm chuẩn, cần review nghiệp vụ hoặc đối chiếu với bằng chứng đáng tin.

**“Độ bao phủ thấp thì mọi test đều kém.”** Không nhất thiết. Một số test có oracle rất tốt cho các khu vực quan trọng dù coverage tổng thể chưa cao. Tuy nhiên, vùng chưa được kiểm tra vẫn là rủi ro cần nhận diện.

## 14. Bài tập tự kiểm tra

### Tình huống A — Test xanh ở cả hai nhánh

Hàm tính phí dùng điều kiện `amount > 500_000`. Nhóm có test với 400.000 và 600.000, cả hai đều qua; báo cáo cho thấy đã thực thi đủ hướng của phép so sánh.

**Câu hỏi:** bug còn sót là gì, test nào cần thêm?

**Gợi ý:** yêu cầu là miễn phí từ **500.000**, nên `>` là sai. Cần test đúng **500.000** và mong đợi phí 0; sau đó sửa mã thành `>=`.

### Tình huống B — Mock ghi dữ liệu nhưng không kiểm tra giá trị

Use case gọi **repository.save(invoice)**. Test chỉ xác nhận **save()** được gọi. Trong thực tế, invoice được lưu với tổng tiền sai vì áp dụng chiết khấu hai lần.

**Câu hỏi:** test còn thiếu điều gì?

**Gợi ý:** kiểm tra số tiền, mã khách và những bất biến quan trọng trong dữ liệu được gửi ghi hoặc trạng thái đã lưu. Test interaction có thể giữ lại, nhưng không thay thế kiểm tra kết quả nghiệp vụ.

### Tình huống C — Mutation sống sót dù hàm đã được gọi

Một mutant đổi điều kiện `isVip && total >= threshold` thành `isVip || total >= threshold`. Test hiện chỉ có khách VIP với tổng trên ngưỡng.

**Câu hỏi:** dữ liệu nào phân biệt hai biểu thức?

**Gợi ý:** thử khách **không VIP** nhưng tổng trên ngưỡng, hoặc khách **VIP** dưới ngưỡng, tùy chính sách gốc. Phải chọn ca mà hai biểu thức cho kết quả khác và assert đúng theo đặc tả, không chỉ để gọi qua mã.

### Tình huống D — Vòng lặp assert không chạy

Test gọi repository tìm các bản ghi đã thanh toán rồi lặp từng bản ghi để assert **status == PAID**. Fixture tạo danh sách rỗng.

**Câu hỏi:** vì sao test vẫn qua, cần bổ sung gì?

**Gợi ý:** vòng lặp không có phần tử nên không có assertion nào chạy. Nếu hợp đồng đòi ít nhất một bản ghi, assert tập kết quả không rỗng và kiểm tra danh tính/dữ liệu mong đợi. Nếu tập rỗng là hành vi đúng, viết riêng test cho trường hợp rỗng.

### Tình huống E — Dùng lại kết quả làm chuẩn

Một nhóm ghi lại response JSON hiện tại làm golden file mà không xác nhận với nghiệp vụ. Sau đó mọi test snapshot đều qua, nhưng trường **taxAmount** đã sai từ trước.

**Câu hỏi:** snapshot test có vô ích không?

**Gợi ý:** snapshot có thể phát hiện thay đổi ngoài ý muốn của định dạng hoặc kết quả, nhưng không chứng minh snapshot gốc đúng. Cần thẩm định giá trị quan trọng và bổ sung oracle dựa trên quy tắc thuế; khi cập nhật snapshot cũng phải review ý nghĩa thay đổi.

## 15. Checklist để biết test thật sự tạo bằng chứng

Trước khi nói một chức năng “đã được kiểm thử”, hãy hỏi:

- **Yêu cầu:** test đang chứng minh quy tắc hoặc bất biến cụ thể nào?
- **Tình huống:** dữ liệu có kích hoạt điều kiện liên quan, nhất là các ngưỡng và trạng thái lỗi?
- **Quan sát:** kết quả và tác dụng phụ cần thiết có thực sự được đọc/kiểm tra?
- **Oracle:** expected xuất phát từ đặc tả hoặc bằng chứng độc lập, hay được sao chép từ mã sản xuất?
- **Khẳng định:** nếu phần mềm trả một kết quả sai quan trọng, assertion có làm test thất bại?
- **Môi trường:** test có thực sự được chạy, không bị skip, và ổn định đủ để đáng tin?
- **Tích hợp:** phần adapter, dữ liệu bền vững và giao tiếp ngoài có bằng chứng riêng?
- **Hồi quy:** lỗi đã gặp có test tái hiện đỏ trước khi sửa và xanh sau khi sửa không?
- **Mutation:** một số thay đổi sai hợp lý có bị test phát hiện, và survivor nào có ý nghĩa?
- **Bảo trì:** test có mô tả hành vi rõ, tránh phụ thuộc chi tiết triển khai không cần thiết?

Bằng chứng kiểm thử hữu ích nhất không phải là câu “mã này đã được chạy qua”, mà là **“với điều kiện xác định, nếu mã vi phạm quy tắc này thì bài kiểm thử sẽ thất bại”**. Trong **CODE_QUALITY_FUNDAMENTALS**, xây dựng những bài test có sức phát hiện lỗi là cách làm mã nguồn **đáng tin cậy hơn khi vận hành, dễ hiểu hơn qua các ví dụ thực thi được và dễ thay đổi hơn nhờ phát hiện hồi quy đúng lúc**.
