# Tạo kiểm thử phát hiện một lỗi đã xác nhận

Trong chương **Thực hành** của module **CODE_QUALITY_FUNDAMENTALS**, bài này hướng dẫn cách biến một lỗi đã được xác nhận thành một kiểm thử có thể tái hiện và ngăn lỗi quay lại. Mục tiêu không chỉ là viết thêm một assertion. Người phát triển cần chỉ ra điều kiện gây lỗi, xác định hành vi đúng từ yêu cầu hoặc hợp đồng, tạo đầu vào nhỏ nhất làm lộ sai lệch, rồi giữ lại kiểm thử đó như bằng chứng hồi quy.

Module **CODE_QUALITY_FUNDAMENTALS** giúp người học hiểu những thuộc tính quyết định mã nguồn có **đáng tin cậy, dễ hiểu và dễ thay đổi** hay không. Một kiểm thử hồi quy tốt hỗ trợ cả ba thuộc tính: nó ghi lại hành vi cần giữ, giúp người khác hiểu một trường hợp nghiệp vụ quan trọng và cho phép thay đổi cấu trúc hoặc logic mà vẫn phát hiện sai lệch.

> **Với một lỗi đã xác nhận, hãy tạo một test tái hiện được lỗi trên phiên bản đang sai, kiểm tra kết quả mong đợi từ hợp đồng độc lập với cách cài đặt, rồi giữ test đó sau khi sửa để bảo vệ hành vi.**

Bài thực hành dùng ví dụ Java/JUnit 5 về ngưỡng miễn phí vận chuyển. Đặc tả nói rằng đơn hàng được miễn phí khi tổng tiền **từ ngưỡng trở lên**, nhưng code hiện tại chỉ miễn phí khi tổng tiền **lớn hơn** ngưỡng. Đây là một lỗi biên cụ thể, có đầu vào tái hiện nhỏ và kết quả mong đợi xác định.

## 1. Mục tiêu học tập

Sau bài này, người học có thể:

1. Phân biệt lỗi đã xác nhận với nghi ngờ, mùi mã hoặc một cảnh báo chưa được kiểm chứng.
2. Thu thập bằng chứng về đầu vào, điều kiện, kết quả thực tế và kết quả mong đợi.
3. Rút gọn một sự cố hoặc báo cáo lỗi thành tình huống tái hiện nhỏ, ổn định.
4. Chọn tầng kiểm thử phù hợp với nơi lỗi phát sinh và hợp đồng cần bảo vệ.
5. Viết test có oracle độc lập, tên mô tả hành vi và assertion kiểm tra kết quả quan sát được.
6. Xác minh test thất bại trên phiên bản có lỗi trước khi sửa và thành công sau khi sửa.
7. Bổ sung các trường hợp biên liên quan mà không biến một test hồi quy nhỏ thành bộ kiểm thử không có trọng tâm.
8. Đánh giá test về độ tin cậy, tính cô lập, khả năng đọc và giá trị bảo vệ lâu dài.

## 2. Khi nào có thể gọi một lỗi là đã xác nhận?

Một lỗi được xem là **đã xác nhận** khi có đủ căn cứ cho thấy hành vi hiện tại không đáp ứng một yêu cầu, hợp đồng hoặc bất biến đã được thống nhất. Việc ai đó nói “kết quả có vẻ sai” là tín hiệu cần điều tra, chưa phải bằng chứng hoàn chỉnh.

Một xác nhận thường cần bốn thành phần:

- **Điều kiện:** dữ liệu hoặc trạng thái nào làm lỗi xuất hiện?
- **Hành vi thực tế:** hệ thống đang làm gì?
- **Hành vi mong đợi:** đặc tả, quy tắc nghiệp vụ hoặc hợp đồng quy định điều gì?
- **Sai lệch:** thực tế khác mong đợi ở điểm nào?

Ví dụ:

| Thành phần | Nội dung |
| --- | --- |
| Điều kiện | Đơn STANDARD có subtotal bằng đúng 500.000 xu. |
| Hành vi thực tế | Hệ thống tính phí vận chuyển 30.000 xu. |
| Hành vi mong đợi | Đơn từ 500.000 xu trở lên được miễn phí. |
| Sai lệch | Trường hợp đúng ngưỡng bị tính phí. |

Điều kiện và kết quả có thể được tái hiện bằng một lời gọi hàm. Hành vi mong đợi đến từ quy tắc “từ ngưỡng trở lên”, không được suy ra bằng cách nhìn code đang chạy.

### 2.1. Phân biệt bug với nghi ngờ và mùi mã

| Nhận định | Điều đã biết | Bước tiếp theo |
| --- | --- | --- |
| “Phương thức có nhiều nhánh.” | Có một dấu hiệu cấu trúc. | Xem luồng điều khiển và chi phí bảo trì. |
| “Có thể sai ở ngưỡng.” | Có giả thuyết về lỗi biên. | Đối chiếu đặc tả và tái hiện. |
| “Đơn đúng 500.000 bị tính phí dù đặc tả miễn phí từ 500.000.” | Có sai lệch xác định được. | Viết test hồi quy cho đầu vào này. |
| “Test thỉnh thoảng timeout.” | Có biểu hiện không ổn định. | Điều tra điều kiện môi trường, đồng thời và phụ thuộc trước khi quy kết bug. |

Không cần gọi mọi test thất bại là lỗi sản phẩm. Một test có thể sai kỳ vọng, dùng dữ liệu không hợp lệ hoặc phụ thuộc môi trường. **Test phải được đối chiếu với hợp đồng trước khi dùng làm bằng chứng.**

## 3. Thu thập bằng chứng trước khi viết test

Trước khi mở IDE, hãy ghi lại những gì đã biết. Việc này ngăn test được xây trên một cách diễn giải thiếu chính xác.

### 3.1. Bộ thông tin tối thiểu

1. **Phiên bản:** commit, build hoặc release nơi lỗi được quan sát.
2. **Điều kiện đầu vào:** giá trị, trạng thái, vai trò hoặc cấu hình có liên quan.
3. **Các bước tái hiện:** thao tác theo thứ tự để làm lỗi xuất hiện.
4. **Kết quả thực tế:** giá trị trả về, trạng thái lưu, exception hoặc tác dụng phụ.
5. **Kết quả mong đợi:** trích từ yêu cầu hoặc hợp đồng có thẩm quyền.
6. **Phạm vi:** chỉ xảy ra ở unit, một endpoint, một loại dữ liệu hay nhiều đường đi?
7. **Tính lặp lại:** lỗi xuất hiện mỗi lần với cùng điều kiện hay chỉ thỉnh thoảng?
8. **Bằng chứng:** log đã loại bỏ dữ liệu nhạy cảm, trace, test hiện có hoặc báo cáo sự cố.

Không cần sao chép toàn bộ log production vào test. Hãy giữ những giá trị tối thiểu đủ để tái hiện và không đưa token, mật khẩu, thông tin cá nhân hoặc dữ liệu khách hàng thật vào fixture.

### 3.2. Ghi rõ điều chưa biết

Nếu chưa biết lỗi xuất hiện từ phiên bản nào, hoặc chỉ tái hiện được ở một môi trường, hãy ghi điều đó. Đừng biến giả thuyết thành sự thật chỉ để có một test nhanh.

Ví dụ:

> “Đã tái hiện lỗi tính phí ở subtotal đúng 500.000 trên build X. Đặc tả hiện hành ghi ‘từ 500.000 trở lên’. Chưa xác minh ảnh hưởng tới các đơn đã lưu trước phiên bản X.”

Test có thể bảo vệ phép tính mới, nhưng không tự trả lời câu hỏi về dữ liệu lịch sử.

## 4. Tách điều kiện gây lỗi thành một tình huống nhỏ

Một báo cáo production có thể chứa nhiều thao tác: tạo tài khoản, nhập dữ liệu, gọi nhiều service, chạy queue và cập nhật database. Để viết test tốt, hãy tìm phần nhỏ nhất vẫn giữ nguyên nguyên nhân gây lỗi.

### 4.1. Thu nhỏ từng bước

- Bỏ các thao tác không ảnh hưởng đến điều kiện lỗi.
- Giữ lại dữ liệu làm thay đổi nhánh quyết định.
- Thay phụ thuộc bên ngoài bằng fixture hoặc fake nếu lỗi không nằm ở phụ thuộc đó.
- Giữ đúng đơn vị, timezone, locale và trạng thái cần thiết.
- Thử bỏ từng giá trị để xem lỗi còn tái hiện không.
- So sánh kết quả với một trường hợp lân cận đã hoạt động đúng.

Ví dụ về ngưỡng phí, một request đầy đủ có thể được rút gọn thành:

~~~java
long actual = policy.fee(500_000L, CustomerTier.STANDARD);
~~~

Nếu lời gọi này vẫn cho kết quả sai theo đặc tả, không cần dựng HTTP server, database hay hàng đợi để kiểm tra chính phép tính.

### 4.2. Giữ nguyên yếu tố thật sự gây lỗi

Thu nhỏ không có nghĩa thay đổi ngữ cảnh đến mức không còn tái hiện cùng bug. Nếu lỗi chỉ xuất hiện khi hai request chạy đồng thời, một unit test tuần tự không chứng minh được race condition. Nếu lỗi phụ thuộc transaction database, fake repository có thể bỏ mất nguyên nhân.

Hãy chọn **mức cô lập nhỏ nhất vẫn giữ được điều kiện tạo ra lỗi**.

## 5. Chọn tầng kiểm thử phù hợp

Một lỗi có thể xuất hiện ở nhiều tầng. Chọn test ở nơi có thể kiểm tra hợp đồng một cách đáng tin và phản hồi nhanh nhất.

| Tầng kiểm thử | Phù hợp khi | Ví dụ |
| --- | --- | --- |
| **Unit test** | Lỗi nằm trong phép tính hoặc quy tắc cục bộ. | Toán tử sai ở ngưỡng miễn phí. |
| **Integration test** | Lỗi phụ thuộc vào tương tác với database, broker hoặc thư viện thật. | Migration làm sai dữ liệu tiền. |
| **Contract test** | Lỗi nằm ở cách producer và consumer diễn giải hợp đồng. | API trả sai mã trạng thái hoặc field. |
| **End-to-end test** | Lỗi chỉ xuất hiện qua một luồng người dùng xuyên nhiều thành phần. | Checkout hiển thị phí khác với xác nhận đơn. |
| **Concurrency test** | Lỗi phụ thuộc vào thứ tự hoặc tương tác đồng thời. | Hai request ghi đè trạng thái dùng chung. |

Không cần chọn E2E chỉ vì lỗi được báo từ giao diện. Nếu nguyên nhân là một hàm tính toán thuần túy, unit test ở hàm đó thường rõ và ổn định hơn. Ngược lại, nếu lỗi phát sinh từ serialization hoặc transaction, test unit không thể thay thế kiểm tra tích hợp.

### 5.1. Một test nhỏ có thể đi cùng test ở tầng cao hơn

Nếu unit test chứng minh phép tính đúng nhưng bug ban đầu còn phụ thuộc cách API truyền dữ liệu, hãy bổ sung integration hoặc contract test cho ranh giới ấy. Không cần lặp lại mọi assertion ở mọi tầng; mỗi test nên chứng minh một điều mà tầng khác không thể bảo đảm.

## 6. Xác định oracle: kết quả đúng đến từ đâu?

*Test oracle* là căn cứ để quyết định một kết quả có đúng hay không. Với bug đã xác nhận, oracle phải độc lập với cách cài đặt đang sai.

Nguồn oracle có thể là:

- Yêu cầu nghiệp vụ đã được phê duyệt.
- API contract hoặc schema.
- Quy định về dữ liệu và bất biến.
- Kết quả tính toán đã được xác minh độc lập.
- Hành vi đã được chấp nhận và ghi nhận từ phiên bản trước, nếu đó là hợp đồng cần giữ.
- Quy định pháp lý hoặc tiêu chuẩn liên quan.

Không nên viết test kiểu:

~~~java
assertEquals(policy.fee(input), policy.fee(input));
~~~

Assertion này luôn so sánh kết quả với chính nó. Nó không có oracle.

Cũng không nên sao chép nguyên công thức production vào test rồi dùng cùng công thức để tạo expected. Nếu cả hai cùng chứa sai sót, test vẫn xanh.

### 6.1. Oracle cho ví dụ vận chuyển

Đặc tả giả định đã xác nhận:

- STANDARD miễn phí khi subtotal từ 500.000 xu trở lên.
- PREMIUM miễn phí khi subtotal từ 300.000 xu trở lên.
- Dưới ngưỡng, phí là 30.000 xu.
- Tổng tiền âm không hợp lệ.
- Hạng khách hàng null không hợp lệ.

Từ đó, expected có thể được ghi rõ:

| Hạng | Subtotal | Phí mong đợi | Lý do |
| --- | ---: | ---: | --- |
| STANDARD | 499.999 | 30.000 | Dưới ngưỡng. |
| STANDARD | 500.000 | 0 | Đúng ngưỡng, thuộc “từ ngưỡng trở lên”. |
| STANDARD | 500.001 | 0 | Trên ngưỡng. |
| PREMIUM | 299.999 | 30.000 | Dưới ngưỡng. |
| PREMIUM | 300.000 | 0 | Đúng ngưỡng. |
| PREMIUM | 300.001 | 0 | Trên ngưỡng. |

Bảng này là oracle cho ví dụ. Trong hệ thống thật, hãy xác nhận đơn vị, thời điểm áp dụng ngưỡng và quy tắc chiết khấu trước khi dùng các con số.

## 7. Ví dụ lỗi đã xác nhận: sai toán tử ở ngưỡng miễn phí

Giả sử code Java hiện tại:

~~~java
import java.util.Objects;

enum CustomerTier {
    STANDARD, PREMIUM
}

final class ShippingFeePolicy {
    long fee(long subtotalCents, CustomerTier tier) {
        if (subtotalCents < 0) {
            throw new IllegalArgumentException("Negative subtotal");
        }
        Objects.requireNonNull(tier, "tier");

        long threshold = tier == CustomerTier.PREMIUM
                ? 300_000L
                : 500_000L;

        // BUG: đặc tả yêu cầu miễn phí từ ngưỡng trở lên.
        return subtotalCents > threshold ? 0L : 30_000L;
    }
}
~~~

Lỗi nằm ở phép so sánh `>`. Khi subtotal đúng bằng threshold, biểu thức trả về false, nên hàm tính phí 30.000 xu. Đặc tả lại nói “từ ngưỡng trở lên”, bao gồm cả giá trị bằng ngưỡng.

Điểm quan trọng: đây là **bug đã được xác nhận bởi hợp đồng**, không phải suy đoán rằng toán tử lớn hơn “trông đáng ngờ”.

## 8. Viết test hồi quy đầu tiên cho đúng trường hợp lỗi

Với JUnit 5, một test có thể mô tả trực tiếp hành vi bị lỗi:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import org.junit.jupiter.api.Test;

class ShippingFeePolicyTest {
    private final ShippingFeePolicy policy = new ShippingFeePolicy();

    @Test
    void standardOrderAtFreeShippingThresholdPaysNoFee() {
        long actual = policy.fee(500_000L, CustomerTier.STANDARD);

        assertEquals(0L, actual);
    }
}
~~~

Tên test nêu rõ:

- Hạng khách hàng: STANDARD.
- Điều kiện: subtotal đúng ngưỡng miễn phí.
- Kết quả mong đợi: không có phí.

Assertion kiểm tra kết quả công khai của hàm, không kiểm tra biến private hoặc cách viết toán tử.

### 8.1. Vì sao test này phải thất bại trước khi sửa?

Với code đang có:

- Đầu vào: `subtotalCents = 500_000`.
- Ngưỡng STANDARD: `500_000`.
- Điều kiện `500_000 > 500_000` là false.
- Hàm trả `30_000`.
- Test mong đợi `0`.

Vì vậy, trên phiên bản có bug, test phải báo sai lệch **expected 0, actual 30000**. Đây là kết quả suy ra trực tiếp từ ví dụ mã; bài học không tuyên bố đã chạy test trên một repository cụ thể.

### 8.2. Thứ tự thực hành quan trọng

1. Thêm test vào phiên bản có lỗi.
2. Chạy riêng test đó và xác nhận nó thất bại vì assertion về hành vi.
3. Kiểm tra rằng test không thất bại do compile, thiếu dependency, môi trường hoặc fixture sai.
4. Chỉ sau khi đã có bằng chứng RED, sửa code.
5. Chạy lại test để xác nhận GREEN.
6. Chạy thêm các test liên quan để phát hiện tác động phụ.

Nếu sửa code trước rồi mới viết test, test có thể vẫn hữu ích, nhưng ta đã mất bằng chứng trực tiếp rằng nó thực sự phát hiện phiên bản có lỗi.

## 9. Mở rộng test quanh ranh giới liên quan

Test đầu tiên bắt đúng bug đã xác nhận. Có thể bổ sung các trường hợp lân cận để bảo vệ hợp đồng và tránh một bản sửa quá rộng.

~~~java
import static org.junit.jupiter.api.Assertions.*;
import org.junit.jupiter.api.Test;

class ShippingFeePolicyTest {
    private final ShippingFeePolicy policy = new ShippingFeePolicy();

    @Test
    void standardJustBelowThresholdPaysFee() {
        assertEquals(30_000L,
                policy.fee(499_999L, CustomerTier.STANDARD));
    }

    @Test
    void standardAtThresholdIsFree() {
        assertEquals(0L,
                policy.fee(500_000L, CustomerTier.STANDARD));
    }

    @Test
    void standardAboveThresholdIsFree() {
        assertEquals(0L,
                policy.fee(500_001L, CustomerTier.STANDARD));
    }

    @Test
    void premiumJustBelowThresholdPaysFee() {
        assertEquals(30_000L,
                policy.fee(299_999L, CustomerTier.PREMIUM));
    }

    @Test
    void premiumAtThresholdIsFree() {
        assertEquals(0L,
                policy.fee(300_000L, CustomerTier.PREMIUM));
    }

    @Test
    void premiumAboveThresholdIsFree() {
        assertEquals(0L,
                policy.fee(300_001L, CustomerTier.PREMIUM));
    }

    @Test
    void negativeSubtotalIsRejected() {
        assertThrows(IllegalArgumentException.class,
                () -> policy.fee(-1L, CustomerTier.STANDARD));
    }

    @Test
    void nullTierIsRejected() {
        assertThrows(NullPointerException.class,
                () -> policy.fee(100_000L, null));
    }
}
~~~

Bộ test mở rộng kiểm tra ba điểm dưới, bằng và trên ngưỡng cho cả hai hạng. Hai test cuối bảo vệ validation đã có trong ví dụ.

Không phải mọi bug đều cần hàng chục test. Hãy thêm các trường hợp có liên quan tới nguyên nhân, hợp đồng và rủi ro hồi quy. Tránh biến một test cho một lỗi thành một bộ test toàn diện cho mọi chức năng không liên quan.

## 10. Sửa lỗi và xác minh test chuyển từ RED sang GREEN

Bản sửa tối thiểu cho ví dụ là đổi phép so sánh thành `>=`:

~~~java
final class ShippingFeePolicy {
    long fee(long subtotalCents, CustomerTier tier) {
        if (subtotalCents < 0) {
            throw new IllegalArgumentException("Negative subtotal");
        }
        Objects.requireNonNull(tier, "tier");

        long threshold = tier == CustomerTier.PREMIUM
                ? 300_000L
                : 500_000L;

        return subtotalCents >= threshold ? 0L : 30_000L;
    }
}
~~~

Kết quả cần xác minh:

| Giai đoạn | Kết quả | Ý nghĩa |
| --- | --- | --- |
| Trước sửa | Test đúng ngưỡng thất bại: expected 0, actual 30.000. | Test phát hiện bug đã xác nhận. |
| Sau sửa | Test đúng ngưỡng thành công. | Bản sửa đáp ứng trường hợp lỗi. |
| Sau khi thêm ca lân cận | Các test dưới/trên ngưỡng và validation đều thành công. | Bản sửa không làm sai các trường hợp đã mô tả. |

Đây là mô tả kết quả mong đợi từ ví dụ. Khi thực hành trên dự án, phải ghi lại output thật của công cụ test, commit và môi trường đã chạy.

### 10.1. Một test chỉ chuyển xanh chưa chứng minh mọi thứ đúng

Có thể test cụ thể pass nhưng:

- Hạng PREMIUM vẫn dùng ngưỡng sai.
- Một đường API truyền nhầm đơn vị tiền.
- Tổng tiền trước/sau chiết khấu bị dùng nhầm.
- Dữ liệu đã lưu không được xử lý đúng.
- Một client khác dùng phép tính riêng.
- Một tác dụng phụ hoặc exception contract đã thay đổi.

Hãy xem test hồi quy là **một bằng chứng có phạm vi**, rồi chọn các kiểm tra khác theo ranh giới bị ảnh hưởng.

## 11. Kiểm tra rằng test thật sự bắt được lỗi

Một test xanh sau khi sửa có thể vẫn yếu nếu nó không thất bại khi bug quay lại. Có thể kiểm tra chất lượng test bằng một số câu hỏi:

1. Nếu đổi `>=` trở lại `>`, test đúng ngưỡng có thất bại không?
2. Nếu ngưỡng thay đổi, expected có đến từ hợp đồng hay vô tình theo code?
3. Nếu test bị xóa, pipeline có còn phát hiện bug không?
4. Test có chạy trong bộ bắt buộc ở CI không?
5. Test có phụ thuộc môi trường hoặc dữ liệu không liên quan không?
6. Assertion có đủ cụ thể để phân biệt đúng và sai không?

Có thể dùng mutation testing nếu dự án có công cụ phù hợp: cố ý thay đổi một toán tử hoặc nhánh để xem test có phát hiện không. Nhưng không nhất thiết thêm mutation testing cho mọi lỗi; một kiểm tra thủ công có chủ đích có thể đủ cho ví dụ nhỏ.

### 11.1. Tránh test trùng lặp không tạo thêm bằng chứng

Ba test chỉ gọi cùng một đầu vào qua ba helper chuyển tiếp rồi kiểm tra cùng một giá trị có thể không tăng độ tin cậy. Thay vào đó, chọn test cho các ranh giới khác nhau: phép tính, endpoint truyền đúng hạng, hoặc integration với dữ liệu đã lưu.

## 12. Chọn fixture tối thiểu và làm test ổn định

Một test hồi quy nên tái hiện bug mà không phụ thuộc vào trạng thái ngẫu nhiên.

### 12.1. Dùng dữ liệu xác định

- Giá trị đầu vào cố định.
- Clock giả hoặc thời gian truyền qua tham số nếu bug liên quan ngày giờ.
- Locale/timezone được chỉ định khi có ảnh hưởng.
- ID và dữ liệu test duy nhất, không trùng giữa các test chạy song song.
- Seed rõ ràng cho dữ liệu ngẫu nhiên nếu cần.
- Không gọi API production hoặc phụ thuộc mạng thật nếu không phải nguyên nhân.

### 12.2. Không dùng sleep để đoán thời điểm

Nếu bug liên quan async processing, đợi một khoảng thời gian cố định có thể làm test chập chờn. Nên chờ điều kiện có timeout rõ, dùng đồng hồ điều khiển được hoặc cơ chế đồng bộ phù hợp với hệ thống.

### 12.3. Dọn trạng thái sau test

Test integration cần cô lập dữ liệu và tài nguyên. Hãy bảo đảm transaction, container, file tạm, queue hoặc thread được dọn ngay cả khi assertion thất bại.

Một test hồi quy không ổn định có thể khiến nhóm mất niềm tin và bị quarantine; khi đó bug có thể quay lại mà không bị phát hiện.

## 13. Khi bug nằm ở database hoặc ranh giới tích hợp

Giả sử lỗi không nằm trong hàm tính phí mà ở mapping database: cột tiền dùng kiểu dữ liệu hoặc phép chuyển đổi làm mất phần giá trị biên.

Trong trường hợp đó, unit test của policy không đủ.

Một integration test có thể:

1. Khởi tạo database test ở phiên bản tương thích.
2. Chạy migration liên quan.
3. Lưu một giá trị đúng ngưỡng.
4. Đọc lại qua repository.
5. Gọi logic nghiệp vụ hoặc kiểm tra dữ liệu sau mapping.
6. Xác nhận giá trị không bị đổi hoặc cắt cụt.

Ví dụ khái niệm:

~~~java
@Test
void repositoryPreservesExactThresholdValue() {
    Order order = new Order("order-1", 500_000L);
    orderRepository.save(order);

    Order loaded = orderRepository.findById("order-1").orElseThrow();

    assertEquals(500_000L, loaded.subtotalCents());
}
~~~

Đây chỉ là minh họa cho ý tưởng; các class, repository và thiết lập database phải theo dự án thực. Nếu bug nằm ở migration hoặc SQL type, test cần chạy trên database thật hoặc engine tương thích trong môi trường kiểm thử, không chỉ mock repository.

## 14. Khi bug nằm ở API hoặc hợp đồng giữa các thành phần

Một unit test có thể chứng minh hàm trả đúng 0, nhưng controller vẫn có thể:

- Nhận tiền theo đơn vị đồng thay vì xu.
- Ánh xạ hạng khách hàng sai.
- Serialize kết quả thành field hoặc mã lỗi không đúng.
- Bỏ qua quyền truy cập.
- Dùng phiên bản policy không phù hợp.

Với lỗi tại ranh giới API, hãy tạo contract hoặc integration test kiểm tra request, response, mã trạng thái và ý nghĩa dữ liệu. Chỉ dùng E2E khi bug thực sự phụ thuộc vào luồng xuyên nhiều thành phần hoặc không thể cô lập đáng tin ở tầng thấp hơn.

Một test tầng cao hơn có thể giữ lại làm bằng chứng cho luồng người dùng, trong khi unit test nhỏ hơn giúp định vị chính xác phép tính.

## 15. Khi bug chỉ xuất hiện dưới concurrency

Một lỗi race condition không thể được xác nhận bằng test tuần tự đơn giản. Cần giữ lại điều kiện đồng thời đã làm lỗi xuất hiện:

- Dùng barrier/latch để điều phối thời điểm hai luồng.
- Tránh dựa vào sleep để hy vọng hai luồng chạy xen kẽ.
- Tạo dữ liệu độc lập và trạng thái dùng chung giống production.
- Xác minh invariant cuối cùng, không chỉ thứ tự gọi method.
- Chạy lặp nhiều lần khi cần, nhưng không coi “đã chạy 100 lần không lỗi” là chứng minh tuyệt đối.

Ví dụ khái niệm: hai request giữ chỗ cùng một đơn vị tồn kho. Hợp đồng là tổng số lượng giữ chỗ không được vượt tồn kho. Test cần điều khiển hai giao dịch cùng đọc trạng thái ban đầu rồi cùng thử cập nhật; nếu chỉ gọi hai hàm tuần tự, nó có thể không tái hiện lỗi.

Với concurrency, integration test trên database hoặc thành phần thực thường cần thiết vì khóa, isolation level và transaction semantics là một phần của nguyên nhân.

## 16. Các lỗi thường gặp khi viết test cho bug đã xác nhận

### 16.1. Viết expected theo kết quả đang sai

Nếu code hiện trả 30.000 và test cũng đặt expected 30.000 vì “đó là output hiện tại”, test sẽ hợp thức hóa bug. Expected phải đến từ yêu cầu đã xác nhận.

### 16.2. Sửa code trước, rồi mới thử test

Test sau sửa có thể pass ngay cả khi không bắt được lỗi cũ. Hãy kiểm tra test trên phiên bản có bug nếu có thể, hoặc tái tạo bug trong branch/fixture an toàn để xác nhận test có khả năng phát hiện.

### 16.3. Test quá rộng và khó chẩn đoán

Một E2E dài thất bại vì phí vận chuyển sai có thể mất nhiều phút và log phức tạp. Nếu nguyên nhân nằm trong hàm policy, thêm unit test cụ thể giúp phát hiện nhanh và giải thích rõ hơn.

### 16.4. Test kiểm tra chi tiết triển khai

Assert rằng một helper private được gọi đúng hai lần có thể thất bại khi cấu trúc được refactor dù hành vi vẫn đúng. Hãy ưu tiên kết quả công khai hoặc hợp đồng của thành phần.

### 16.5. Dùng mock để thay thế chính nguyên nhân

Nếu bug đến từ SQL query, mock repository sẽ bỏ qua SQL. Nếu bug do serialization, mock HTTP client có thể không phát hiện schema sai. Mock chỉ hữu ích khi phần bị thay thế không phải đối tượng cần kiểm tra.

### 16.6. Thêm nhiều ca nhưng không có lý do

Test nhiều giá trị tùy ý không đảm bảo bao phủ rủi ro. Hãy chọn ca dựa trên nhánh, ranh giới, điều kiện lỗi và các giả định của đặc tả.

### 16.7. Bỏ qua test vì flaky

Nếu test mới không ổn định, cần điều tra fixture, môi trường, đồng bộ và cleanup. Không nên xóa test hồi quy chỉ vì nó đôi lúc đỏ; nếu phải quarantine tạm, ghi owner, lý do, test bù và thời hạn khắc phục.

## 17. Đưa test vào pipeline và bảo đảm nó tiếp tục chạy

Một test chỉ nằm trong máy cá nhân không bảo vệ được thay đổi sau này. Sau khi xác minh, cần bảo đảm test:

- Được lưu trong repository và đúng test suite.
- Có tên mô tả điều kiện và kết quả.
- Chạy trong task CI phù hợp.
- Không bị exclude bởi tag hoặc cấu hình ngoài ý muốn.
- Có fixture ổn định và thời gian chạy phù hợp.
- Có log đủ rõ khi thất bại.
- Được review cùng bản sửa và hợp đồng mong đợi.

Nếu test chỉ chạy ở pipeline phát hành nhưng bug có thể được phát hiện trong PR nhanh, cân nhắc đưa test nhỏ vào gate PR. Nếu test cần môi trường tích hợp đắt đỏ, đặt nó ở tầng phù hợp nhưng phải hoàn tất trước mốc release chịu rủi ro.

## 18. Ghi bằng chứng trong pull request

Một PR sửa bug nên giúp reviewer trả lời:

- Bug được xác nhận từ yêu cầu hoặc sự cố nào?
- Test mới tái hiện điều kiện gì?
- Test có thất bại trên code cũ không?
- Bản sửa thay đổi hành vi nào?
- Các trường hợp lân cận nào đã được kiểm tra?
- Còn rủi ro nào chưa được bao phủ?

Mẫu mô tả ngắn:

~~~markdown
## Lỗi đã xác nhận
Đơn STANDARD có subtotal đúng 500.000 xu bị tính phí vận chuyển,
trong khi quy tắc hiện hành miễn phí từ 500.000 xu trở lên.

## Kiểm thử hồi quy
- Thêm test cho subtotal đúng ngưỡng.
- Xác nhận test thất bại trên phiên bản có lỗi.
- Thêm test dưới và trên ngưỡng cho STANDARD/PREMIUM.

## Bản sửa
Đổi phép so sánh để bao gồm giá trị bằng ngưỡng.

## Xác minh
- Unit test chính sách vận chuyển.
- Các test liên quan tới luồng gọi chính sách.
- Ghi lại kết quả CI và phạm vi chưa kiểm tra.
~~~

Đây là mẫu minh họa. Khi dùng trong dự án, thay các chi tiết bằng test, link issue và kết quả chạy thật.

## 19. Bài tập thực hành

### Bài tập A: ngưỡng miễn phí vận chuyển

Đặc tả ghi: “STANDARD được miễn phí từ 500.000 xu trở lên.” Code dùng phép so sánh lớn hơn nghiêm ngặt.

**Yêu cầu:**

1. Viết test đúng 500.000 xu.
2. Giải thích vì sao test phải thất bại trên code cũ.
3. Sửa toán tử.
4. Thêm test 499.999 và 500.001.
5. Nêu phạm vi mà test chưa bao phủ.

**Kết quả mong đợi:** test đúng ngưỡng thất bại trước sửa và thành công sau sửa; hai ca lân cận bảo vệ hành vi dưới/trên ngưỡng.

### Bài tập B: lỗi làm tròn tiền

Một quy tắc đã xác nhận yêu cầu làm tròn tổng thuế một lần ở cấp hóa đơn, nhưng code làm tròn từng dòng rồi cộng. Với hai dòng nhỏ, kết quả lệch một đơn vị tiền nhỏ nhất.

**Yêu cầu:**

1. Viết đầu vào nhỏ nhất tái hiện chênh lệch.
2. Xác nhận oracle từ quy tắc làm tròn.
3. Viết test so sánh tổng hóa đơn với kết quả mong đợi độc lập.
4. Nêu vì sao test chỉ kiểm tra từng dòng không phát hiện lỗi tổng.
5. Xác định có cần test tích hợp persistence hay không.

**Gợi ý:** không tự chọn quy tắc làm tròn từ cách code hiện tại; phải lấy từ đặc tả về độ chính xác và thời điểm làm tròn.

### Bài tập C: lỗi timezone

Một báo cáo ngày bị thiếu giao dịch ở gần nửa đêm khi chạy tại timezone khác.

**Yêu cầu:**

1. Ghi lại timestamp, timezone, ngày nghiệp vụ và kết quả sai.
2. Dùng clock cố định hoặc đầu vào thời gian tường minh.
3. Viết test ở hai phía ranh giới ngày.
4. Xác định timezone thuộc người dùng, cửa hàng hay hệ thống.
5. Chọn unit hay integration test tùy nguyên nhân nằm ở phép tính hay truy vấn dữ liệu.

### Bài tập D: lỗi phân quyền

Một user thuộc tenant A có thể đọc tài nguyên tenant B qua endpoint.

**Yêu cầu:**

1. Tạo hai tenant và hai danh tính giả lập.
2. Viết test xác nhận A không đọc được tài nguyên B.
3. Kiểm tra cả trường hợp hợp lệ của tenant A.
4. Chọn tầng test tại nơi authorization thực sự được thực thi.
5. Không dùng dữ liệu người dùng production trong fixture.

**Gợi ý:** đây là lỗi bảo mật đã xác nhận; test unit policy có thể hữu ích nhưng cần kiểm tra ranh giới API/service nếu quyền được áp dụng tại đó.

### Bài tập E: race condition khi giữ chỗ tồn kho

Hai request cùng giữ đơn vị cuối cùng và cả hai đều nhận thành công.

**Yêu cầu:**

1. Viết invariant tồn kho.
2. Tạo test điều khiển hai giao dịch chạy đồng thời.
3. Xác minh số lượng giữ chỗ sau cùng không vượt tồn kho.
4. Chọn database/integration test nếu nguyên nhân liên quan transaction hoặc isolation.
5. Nêu cách tránh test phụ thuộc sleep ngẫu nhiên.

## 20. Checklist tạo kiểm thử cho lỗi đã xác nhận

- [ ] Lỗi được đối chiếu với yêu cầu, hợp đồng hoặc bất biến có thẩm quyền.
- [ ] Đã ghi điều kiện, kết quả thực tế và kết quả mong đợi.
- [ ] Đã xác định phiên bản và phạm vi nơi lỗi xuất hiện.
- [ ] Dữ liệu tái hiện là nhỏ nhất nhưng vẫn giữ nguyên nguyên nhân.
- [ ] Không đưa secret hoặc dữ liệu cá nhân thật vào fixture.
- [ ] Oracle độc lập với code đang sai.
- [ ] Test nằm ở tầng nhỏ nhất vẫn giữ được nguyên nhân lỗi.
- [ ] Tên test mô tả điều kiện và hành vi mong đợi.
- [ ] Assertion kiểm tra kết quả/hợp đồng, không khóa chi tiết triển khai.
- [ ] Test đã được xác nhận thất bại trên phiên bản có lỗi nếu có thể.
- [ ] Test chuyển xanh sau khi sửa.
- [ ] Có các trường hợp lân cận cần thiết: dưới, bằng, trên ngưỡng hoặc các điều kiện biên tương ứng.
- [ ] Các ngoại lệ, tác dụng phụ và trạng thái liên quan đã được xem xét.
- [ ] Mock không che khuất thành phần đang gây lỗi.
- [ ] Test ổn định, cô lập và có thể chạy lại.
- [ ] Test được đưa vào suite CI phù hợp.
- [ ] PR ghi rõ bug, test tái hiện, bản sửa và kết quả xác minh.
- [ ] Những giới hạn chưa kiểm tra được ghi trung thực.

## 21. Kết luận

**Tạo kiểm thử phát hiện một lỗi đã xác nhận** là quá trình biến một sai lệch cụ thể thành bằng chứng có thể lặp lại. Người viết cần biết lỗi xuất hiện khi nào, hợp đồng đòi hỏi điều gì, test phải quan sát kết quả nào và tại sao test đủ nhỏ để chỉ ra đúng nguyên nhân.

Trong ví dụ vận chuyển, test ở subtotal đúng ngưỡng thất bại vì code dùng `>` trong khi yêu cầu “từ ngưỡng trở lên” cần `>=`. Sau khi sửa, test hồi quy tiếp tục bảo vệ trường hợp đó cùng các giá trị lân cận. Cùng phương pháp này có thể áp dụng cho lỗi dữ liệu, API, timezone, phân quyền và concurrency, miễn là chọn đúng tầng kiểm thử để giữ nguyên điều kiện gây lỗi.

Trong **CODE_QUALITY_FUNDAMENTALS**, một test hồi quy có giá trị giúp mã nguồn **đáng tin cậy hơn nhờ bảo vệ hành vi, dễ hiểu hơn nhờ ghi lại hợp đồng và dễ thay đổi hơn nhờ phát hiện sai lệch sớm**. Hãy giữ lại test sau khi bug được sửa, chạy nó trong pipeline phù hợp và xem nó như một phần của tri thức kỹ thuật mà cả nhóm cùng duy trì.

