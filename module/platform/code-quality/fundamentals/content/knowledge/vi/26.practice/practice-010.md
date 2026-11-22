# Thực hiện tái cấu trúc nhỏ có bằng chứng trước và sau

> **Chương:** Thực hành  
> **Học phần:** CODE_QUALITY_FUNDAMENTALS — hiểu những thuộc tính quyết định mã nguồn có đáng tin cậy, dễ hiểu và dễ thay đổi hay không.

## Mục tiêu học tập

Sau bài thực hành, bạn có thể:

1. Chọn một phạm vi tái cấu trúc nhỏ dựa trên vấn đề có thể quan sát và mục tiêu rõ ràng.
2. Phân biệt refactor bảo toàn hành vi với sửa lỗi hoặc thay đổi nghiệp vụ.
3. Ghi nhận hành vi hiện tại bằng characterization test trước khi thay đổi cấu trúc.
4. Thu thập bằng chứng nền trước refactor: test, kết quả đầu ra, phạm vi phụ thuộc và những chỉ số liên quan.
5. Thực hiện một phép biến đổi nhỏ, có thể review và hoàn tác độc lập.
6. Chạy lại cùng bộ kiểm tra sau refactor và so sánh kết quả theo cùng điều kiện.
7. Dùng bằng chứng hành vi và cấu trúc để đánh giá thành công, không chỉ dựa vào số dòng code hoặc cảm giác “trông sạch hơn”.
8. Xử lý test thất bại, phát hiện thay đổi hành vi ngoài ý muốn và quyết định tiếp tục, sửa hoặc rollback.
9. Trình bày kết quả trước/sau để đồng đội có thể xác minh và tiếp tục bảo trì.

## 1. Refactor nhỏ là thay đổi cấu trúc có mục tiêu

Tái cấu trúc (refactoring) là thay đổi cách tổ chức bên trong của mã để làm nó dễ hiểu, kiểm thử hoặc thay đổi hơn, trong khi giữ nguyên hành vi bên ngoài đã được xác định.

Một refactor nhỏ thường có các đặc điểm:

- **Phạm vi hẹp:** một hàm, một chính sách, một dependency hoặc một ranh giới module.
- **Mục tiêu cụ thể:** loại bỏ một bản sao tri thức, đặt tên rõ trách nhiệm hoặc tạo điểm tách để kiểm thử.
- **Có đường kiểm chứng:** biết test nào phải giữ nguyên và bằng chứng nào sẽ thay đổi.
- **Dễ review:** diff tập trung, không trộn hàng loạt format, đổi tên và sửa nghiệp vụ.
- **Có thể hoàn tác:** nếu phát hiện hồi quy, có thể quay lại thay đổi vừa thực hiện mà không phải phục hồi một đợt viết lại lớn.

Ví dụ, đưa một quy tắc giảm giá đang bị lặp ở báo giá và checkout về một policy có tên là refactor nhỏ nếu cả hai nơi thật sự phải tuân thủ cùng hợp đồng. Viết lại toàn bộ module bán hàng, đổi API, thay schema và điều chỉnh chính sách giá cùng lúc không còn là một bước nhỏ có thể dễ dàng đánh giá.

### Refactor khác sửa lỗi ở điểm nào?

| Loại thay đổi | Điều thay đổi | Ví dụ |
| --- | --- | --- |
| **Refactor bảo toàn hành vi** | Cấu trúc nội bộ | Trích xuất quy tắc VIP giống nhau vào một policy |
| **Sửa lỗi (bug fix)** | Kết quả sai được thay bằng kết quả đúng theo đặc tả | Sửa điều kiện ngưỡng đang bỏ sót đơn hợp lệ |
| **Thay đổi nghiệp vụ** | Hợp đồng hoặc quy tắc sản phẩm | Đổi mức giảm VIP từ 10% thành 12% |
| **Thay đổi tương thích** | API, schema, dữ liệu hoặc hành vi consumer | Đổi tên trường JSON công khai |

Một PR có thể cần nhiều loại thay đổi, nhưng phải nói rõ loại nào đang diễn ra và kiểm thử tương ứng. Nếu hai implementation hiện cho kết quả khác nhau, hợp nhất chúng có thể đồng thời sửa lỗi. Hãy xác nhận đặc tả và ghi nhận phần sửa hành vi; đừng gọi toàn bộ việc đó là refactor bảo toàn hành vi.

## 2. Bài thực hành: loại bỏ một bản sao của chính sách giá VIP

Ta dùng một ví dụ Java nhỏ. Một hệ thống có hai luồng:

- QuoteService tính số tiền hiển thị trong báo giá.
- CheckoutService tính số tiền trước khi tạo giao dịch thanh toán.

Chính sách được xác nhận cho bài thực hành:

1. subtotalVnd là số nguyên VND không âm.
2. Khách VIP được giảm 10% khi tổng tiền **từ 1.000.000 VND trở lên**.
3. Tiền giảm là subtotalVnd chia 10 bằng phép chia nguyên, tức làm tròn xuống số VND giảm.
4. Khách không phải VIP không nhận giảm giá này.
5. Với cùng subtotal và trạng thái VIP, báo giá và checkout phải trả cùng số tiền theo chính sách này.
6. Phần ví dụ chưa bao gồm thuế, phí vận chuyển, voucher hoặc side effect thanh toán.

Đây là hợp đồng giả định dùng để luyện tập. Trong một hệ thống thật, cần xác nhận quy tắc với chủ sở hữu nghiệp vụ trước khi dùng làm kỳ vọng kiểm thử.

### Vấn đề quan sát được

Hai service cùng chứa ngưỡng, điều kiện và công thức giảm giá. Khi chính sách đổi, người phát triển phải tìm và sửa hai nơi. Nếu một nơi bị bỏ sót, khách có thể thấy một giá trong báo giá nhưng bị tính số tiền khác ở checkout.

Mục tiêu refactor là **một nơi sở hữu chính sách VIP**, trong khi hai use case vẫn là hai service riêng.

## 3. Bước 1 — xác định phạm vi và điều không được thay đổi

Trước khi sửa code, hãy viết mục tiêu trong một hoặc hai câu:

> “Đưa quy tắc tính số tiền sau giảm VIP dùng chung cho báo giá và checkout vào một policy có tên. Giữ nguyên kết quả với mọi đầu vào hợp lệ và giữ nguyên hành vi từ chối subtotal âm.”

Sau đó ghi rõ phạm vi:

**Trong phạm vi**

- Quy tắc ngưỡng VIP.
- Công thức và quy tắc làm tròn.
- Hai caller báo giá và checkout.
- Test chứng minh cả policy và caller sử dụng policy.

**Ngoài phạm vi**

- Đổi mức giảm hoặc ngưỡng nghiệp vụ.
- Thêm currency khác VND.
- Thay mô hình thuế, phí hoặc voucher.
- Viết lại checkout hoặc payment gateway.
- Đổi public API không liên quan.

### Các bất biến cần giữ

| Đầu vào | Kết quả mong đợi |
| --- | ---: |
| VIP, 999.999 VND | 999.999 VND |
| VIP, 1.000.000 VND | 900.000 VND |
| VIP, 1.000.005 VND | 900.005 VND |
| Không VIP, 1.200.000 VND | 1.200.000 VND |
| Subtotal âm | Ném IllegalArgumentException |

Bảng này là oracle độc lập từ hợp đồng. Nó giúp phát hiện trường hợp cả hai implementation cùng sai nhưng vẫn cho kết quả giống nhau.

## 4. Bước 2 — đọc caller và phụ thuộc trước khi sửa

Không chỉ xem hai method có cùng vài dòng hay không. Hãy xác minh:

- Cả báo giá và checkout có thực sự dùng cùng chính sách VIP không?
- Giá trị truyền vào là subtotal trước giảm hay một số tiền đã điều chỉnh?
- Đơn vị có phải VND nguyên ở cả hai nơi không?
- Quy tắc làm tròn có giống nhau không?
- Hai luồng có khác điều kiện về trạng thái, thời điểm hoặc quyền không?
- Có caller nào khác dùng một trong hai method không?
- Phương thức có side effect hoặc transaction nào cần giữ ở service không?

Nếu báo giá dùng policy hiện tại còn hóa đơn đã chốt phải giữ giá lịch sử, hai nơi có thể trông giống nhau nhưng không cùng lý do thay đổi. Đừng gộp chúng chỉ vì công thức hiện tại giống nhau.

### Lập bản đồ phụ thuộc ngắn

~~~text
QuoteController
    -> QuoteService
        -> quy tắc VIP (bản sao A)

CheckoutController
    -> CheckoutService
        -> quy tắc VIP (bản sao B)
        -> PaymentGateway
~~~

Ta chỉ muốn thay vị trí sở hữu quy tắc VIP. Controller, payment gateway và ranh giới transaction không cần đổi trong bước này.

## 5. Bước 3 — ghi nhận bằng chứng nền trước refactor

Bằng chứng trước refactor trả lời câu hỏi: **trước khi thay đổi, hệ thống đang hoạt động như thế nào và ta đã kiểm tra những gì?**

Hãy lưu thông tin đủ để so sánh sau này:

| Bằng chứng | Ghi nhận trước refactor | Mục đích |
| --- | --- | --- |
| Commit hoặc revision | Mã revision đang làm việc | Biết chính xác phiên bản nền |
| Test liên quan | Bộ test và kết quả chạy | Biết trạng thái ban đầu |
| Kết quả ở các đầu vào biên | Giá trị kỳ vọng và thực tế | Bảo vệ hợp đồng |
| Số nơi sở hữu quy tắc | Hai method định nghĩa cùng chính sách | Đo thay đổi cấu trúc |
| Caller | Báo giá và checkout | Đảm bảo không bỏ sót luồng |
| Build/static checks | Kết quả trước thay đổi | Phân biệt lỗi có sẵn với lỗi mới |
| Performance | Chỉ ghi nếu hiệu năng thuộc mục tiêu | Tránh tuyên bố cải thiện không có số đo |

Không cần thu thập mọi metric của hệ thống cho một refactor nhỏ. Chỉ ghi bằng chứng liên quan tới mục tiêu và rủi ro của thay đổi.

### Chạy test nền

Dùng lệnh mà dự án thực sự hỗ trợ và cùng cấu hình sẽ dùng sau refactor. Ví dụ minh họa:

~~~bash
./gradlew test --tests "*Pricing*"
~~~

Hoặc với Maven:

~~~bash
mvn -Dtest=PricingTest test
~~~

Tên task và pattern test cần điều chỉnh theo dự án. Không chạy cả hai lệnh nếu repository chỉ dùng một build tool.

Nếu test nền thất bại:

1. Xác định lỗi có sẵn, lỗi môi trường hay lỗi do thay đổi chưa được lưu.
2. Chạy lại trong cùng điều kiện nếu kết quả có dấu hiệu không ổn định.
3. Ghi nhận test và nguyên nhân đã biết.
4. Không sửa kỳ vọng test chỉ để tạo trạng thái xanh trước khi hiểu hành vi.

Một baseline đỏ không phải lý do để bỏ qua test. Nó là thông tin cần giải quyết hoặc ghi rõ trước khi tiếp tục.

## 6. Bước 4 — thêm characterization test trước khi trích xuất

Nếu chưa có test đủ rõ, hãy thêm test mô tả hành vi hiện tại. Với ví dụ này, ta cần xác nhận hai luồng cùng trả kết quả theo chính sách đã thống nhất.

### Code trước refactor

~~~java
final class QuoteService {
    private static final long VIP_THRESHOLD_VND = 1_000_000L;

    long amountDueVnd(long subtotalVnd, boolean vip) {
        if (subtotalVnd < 0) {
            throw new IllegalArgumentException("Negative subtotal");
        }

        if (vip && subtotalVnd >= VIP_THRESHOLD_VND) {
            return subtotalVnd - subtotalVnd / 10;
        }

        return subtotalVnd;
    }
}
~~~

~~~java
final class CheckoutService {
    private static final long VIP_THRESHOLD_VND = 1_000_000L;

    long amountDueVnd(long subtotalVnd, boolean vip) {
        if (subtotalVnd < 0) {
            throw new IllegalArgumentException("Negative subtotal");
        }

        if (vip && subtotalVnd >= VIP_THRESHOLD_VND) {
            return subtotalVnd - subtotalVnd / 10;
        }

        return subtotalVnd;
    }
}
~~~

Hai method đang giữ cùng một quyết định ở hai nơi. Test có thể dùng các giá trị kỳ vọng cụ thể:

~~~java
import static org.junit.jupiter.api.Assertions.*;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.CsvSource;

class PricingCharacterizationTest {
    private final QuoteService quote = new QuoteService();
    private final CheckoutService checkout = new CheckoutService();

    @ParameterizedTest
    @CsvSource({
        "999999, true, 999999",
        "1000000, true, 900000",
        "1000005, true, 900005",
        "1200000, false, 1200000"
    })
    void bothFlowsFollowTheConfirmedVipPolicy(
            long subtotalVnd,
            boolean vip,
            long expectedVnd
    ) {
        assertEquals(expectedVnd,
                quote.amountDueVnd(subtotalVnd, vip));
        assertEquals(expectedVnd,
                checkout.amountDueVnd(subtotalVnd, vip));
    }

    @Test
    void bothFlowsRejectNegativeSubtotal() {
        assertThrows(IllegalArgumentException.class,
                () -> quote.amountDueVnd(-1L, true));
        assertThrows(IllegalArgumentException.class,
                () -> checkout.amountDueVnd(-1L, true));
    }
}
~~~

Test này có hai vai trò:

- Xác nhận kết quả cụ thể theo hợp đồng.
- Xác nhận cả hai đường đi đều tuân thủ kết quả đó.

Không chỉ so sánh báo giá với checkout. Nếu cả hai cùng trả sai 910.000 VND ở ngưỡng, một assertion chỉ so sánh hai kết quả vẫn xanh. Giá trị kỳ vọng độc lập mới giúp phát hiện sai lệch đó.

### Nếu characterization test phát hiện khác biệt

Giả sử checkout trả 1.000.000 VND ở đúng ngưỡng trong khi quote trả 900.000 VND. Dừng việc gộp code và xác minh đặc tả:

- Khác biệt là defect?
- Có chương trình hoặc trạng thái riêng?
- Một bên đang nhận subtotal khác?
- Quy tắc đã thay đổi nhưng một caller chưa cập nhật?

Nếu đặc tả xác nhận đây là bug, hãy ghi nhận phần sửa lỗi riêng và kiểm tra phạm vi ảnh hưởng. Sau khi thống nhất kết quả mong muốn, mới thực hiện refactor hoặc tách hai thay đổi để review rõ hơn.

## 7. Bước 5 — chọn một phép biến đổi nhỏ

Với trường hợp này, phép biến đổi là **Extract Class/Policy**:

1. Tạo VipPricingPolicy.
2. Chuyển ngưỡng và công thức vào policy.
3. Để QuoteService và CheckoutService nhận policy qua constructor.
4. Không chuyển logic payment, controller hoặc dữ liệu lịch sử vào policy.
5. Xóa hai bản sao sau khi các caller đã dùng policy chung.

Một policy có tên nghiệp vụ rõ hơn CommonUtils hoặc DiscountHelper, vì nó cho biết ai sở hữu quyết định và quyết định đó là gì.

Không cần thêm framework dependency injection mới cho bài tập. Có thể nối dependency bằng constructor ở composition root của ứng dụng.

## 8. Bước 6 — thực hiện refactor

### Code sau refactor: một nguồn sở hữu chính sách

~~~java
final class VipPricingPolicy {
    private static final long VIP_THRESHOLD_VND = 1_000_000L;

    long amountDueVnd(long subtotalVnd, boolean vip) {
        if (subtotalVnd < 0) {
            throw new IllegalArgumentException("Negative subtotal");
        }

        if (vip && subtotalVnd >= VIP_THRESHOLD_VND) {
            long discountVnd = subtotalVnd / 10;
            return subtotalVnd - discountVnd;
        }

        return subtotalVnd;
    }
}
~~~

### Hai caller vẫn giữ trách nhiệm riêng

~~~java
import java.util.Objects;

final class QuoteService {
    private final VipPricingPolicy vipPricing;

    QuoteService(VipPricingPolicy vipPricing) {
        this.vipPricing = Objects.requireNonNull(vipPricing);
    }

    long amountDueVnd(long subtotalVnd, boolean vip) {
        return vipPricing.amountDueVnd(subtotalVnd, vip);
    }
}
~~~

~~~java
import java.util.Objects;

final class CheckoutService {
    private final VipPricingPolicy vipPricing;

    CheckoutService(VipPricingPolicy vipPricing) {
        this.vipPricing = Objects.requireNonNull(vipPricing);
    }

    long amountDueVnd(long subtotalVnd, boolean vip) {
        return vipPricing.amountDueVnd(subtotalVnd, vip);
    }
}
~~~

### Nối dependency tại nơi khởi tạo

~~~java
VipPricingPolicy vipPricing = new VipPricingPolicy();

QuoteService quoteService = new QuoteService(vipPricing);
CheckoutService checkoutService = new CheckoutService(vipPricing);
~~~

Trong ứng dụng thực tế, composition root hoặc DI container đảm nhiệm việc tạo và nối dependency. Hai service vẫn có thể có transaction, quyền, I/O và hợp đồng riêng; policy chỉ sở hữu quy tắc tính VIP.

### Vì sao đây là một bước nhỏ?

- Chỉ có một chính sách được chuyển.
- Hai caller vẫn giữ API và mục đích của chúng.
- Không thay đổi công thức hoặc ngưỡng.
- Không thêm side effect.
- Có thể kiểm tra bằng test đã viết trước đó.
- Nếu có hồi quy, diff tập trung giúp tìm nguyên nhân và rollback.

## 9. Bước 7 — chạy lại cùng bằng chứng sau refactor

Chạy lại **cùng bộ test, cùng môi trường và cùng cấu hình** đã dùng ở baseline. Nếu trước đó chạy test riêng cho pricing, sau refactor cũng chạy lại test đó; sau đó chạy thêm test liên quan rộng hơn nếu phạm vi dependency yêu cầu.

Test cho policy sau refactor:

~~~java
import static org.junit.jupiter.api.Assertions.*;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.CsvSource;

class VipPricingPolicyTest {
    private final VipPricingPolicy policy = new VipPricingPolicy();

    @ParameterizedTest
    @CsvSource({
        "999999, true, 999999",
        "1000000, true, 900000",
        "1000005, true, 900005",
        "1200000, false, 1200000"
    })
    void calculatesAmountUsingTheConfirmedPolicy(
            long subtotalVnd,
            boolean vip,
            long expectedVnd
    ) {
        assertEquals(expectedVnd,
                policy.amountDueVnd(subtotalVnd, vip));
    }

    @Test
    void rejectsNegativeSubtotal() {
        assertThrows(IllegalArgumentException.class,
                () -> policy.amountDueVnd(-1L, true));
    }
}
~~~

Và test hai caller cùng dùng policy:

~~~java
import static org.junit.jupiter.api.Assertions.*;
import org.junit.jupiter.api.Test;

class PricingCallersTest {
    @Test
    void quoteAndCheckoutUseTheSamePolicy() {
        VipPricingPolicy policy = new VipPricingPolicy();
        QuoteService quote = new QuoteService(policy);
        CheckoutService checkout = new CheckoutService(policy);

        assertEquals(900_000L,
                quote.amountDueVnd(1_000_000L, true));
        assertEquals(900_000L,
                checkout.amountDueVnd(1_000_000L, true));
    }
}
~~~

Test policy bảo vệ quy tắc; test caller bảo vệ wiring. Nếu chỉ test policy, một service có thể vô tình giữ implementation cũ. Nếu chỉ test caller bằng cách so sánh hai kết quả, hai bên có thể cùng sai. Cần cả kỳ vọng độc lập và kiểm tra đường gọi phù hợp.

## 10. Bước 8 — so sánh bằng chứng trước và sau

Một báo cáo trước/sau nên nói rõ **điều gì giữ nguyên và điều gì đã thay đổi**.

| Bằng chứng | Trước refactor | Sau refactor | Diễn giải |
| --- | --- | --- | --- |
| Kết quả dưới ngưỡng | 999.999 VND | 999.999 VND | Giữ hành vi |
| Kết quả tại ngưỡng | 900.000 VND | 900.000 VND | Giữ điều kiện biên |
| Kết quả với subtotal 1.000.005 | 900.005 VND | 900.005 VND | Giữ quy tắc chia nguyên |
| Khách không VIP | Không giảm | Không giảm | Giữ hành vi |
| Subtotal âm | Ném exception | Ném exception | Giữ validation |
| Nơi định nghĩa policy | Hai method | Một policy | Cấu trúc được đơn giản hóa |
| Caller nghiệp vụ | Quote và checkout | Quote và checkout | Ranh giới use case được giữ |
| Test | Characterization test | Policy + caller tests | Bằng chứng được phân lớp |

Các kết quả trong bảng là **expected values của bài thực hành**, không phải output của một lần chạy build thực tế. Khi áp dụng vào repository, hãy điền kết quả thật từ test runner và revision đang làm.

### Báo cáo trước/sau tối thiểu

~~~text
Mục tiêu:
  Đưa chính sách VIP dùng chung về một nơi sở hữu.

Phạm vi:
  QuoteService, CheckoutService, VipPricingPolicy và test liên quan.

Bằng chứng trước:
  - 2 định nghĩa cùng ngưỡng và công thức.
  - Characterization tests: [kết quả chạy thực tế].
  - Build/static checks: [kết quả thực tế].

Thay đổi:
  - Thêm VipPricingPolicy.
  - Hai service nhận policy qua constructor.
  - Xóa hai bản sao logic tính VIP.

Bằng chứng sau:
  - Cùng test baseline: [kết quả chạy thực tế].
  - Policy tests: [kết quả thực tế].
  - Caller tests: [kết quả thực tế].
  - Diff/checks: [kết quả thực tế].

Kết luận:
  - Hành vi: giữ nguyên theo các trường hợp đã kiểm tra.
  - Cấu trúc: một nơi sở hữu policy thay cho hai bản sao.
  - Giới hạn: chưa đo hiệu năng vì không phải mục tiêu.
~~~

Không ghi “tất cả test đều pass” nếu chỉ chạy một nhóm test. Nêu đúng phạm vi kiểm tra và những gì chưa được xác minh.

## 11. Bằng chứng nào phù hợp với loại mục tiêu?

Không có một con số duy nhất chứng minh refactor tốt. Chọn bằng chứng theo mục tiêu:

| Mục tiêu refactor | Bằng chứng trước/sau phù hợp |
| --- | --- |
| Loại logic nghiệp vụ nhân bản | Số nơi sở hữu chính sách, test từng caller, kết quả theo hợp đồng |
| Tách dependency để dễ test | Có thể kiểm soát dependency bằng fake, test không cần dịch vụ ngoài |
| Làm rõ tên và trách nhiệm | Reviewer có thể xác định nơi sửa policy và trách nhiệm mỗi lớp |
| Giảm coupling | Số dependency/caller bị ảnh hưởng khi thay đổi, ranh giới module |
| Cải thiện hiệu năng | Benchmark cùng workload, dữ liệu, cấu hình và môi trường |
| Giảm lỗi lặp lại | Regression test, incident theo failure mode và thời gian theo dõi |
| Rút ngắn CI | Thời gian p50/p95 qua đủ lần chạy, tỷ lệ flaky và mức kiểm tra giữ lại |

### Không dùng số dòng làm bằng chứng duy nhất

Sau refactor, số dòng có thể tăng vì thêm tên, validation hoặc test. Điều đó không có nghĩa refactor thất bại. Ngược lại, giảm 50 dòng không chứng minh trách nhiệm đã rõ hơn.

Câu hỏi hữu ích hơn:

- Một chính sách có bao nhiêu nơi được phép định nghĩa?
- Người phát triển biết phải sửa ở đâu không?
- Caller có còn giữ trách nhiệm đúng không?
- Test có bắt được sai khác quan trọng không?
- Phạm vi ảnh hưởng của thay đổi tiếp theo có nhỏ và dễ dự đoán hơn không?

## 12. Nếu test thất bại sau refactor

Không vội sửa expected value để test xanh. Hãy phân loại nguyên nhân:

1. **Hồi quy do refactor:** code mới thay đổi hành vi dù không chủ định.
2. **Test chưa mô tả đúng hợp đồng:** baseline test ghi nhận defect hoặc kỳ vọng sai.
3. **Thiếu test caller/wiring:** policy đúng nhưng một service vẫn dùng đường cũ hoặc được nối sai.
4. **Vấn đề môi trường:** test phụ thuộc timezone, database, dữ liệu dùng chung hoặc thứ tự chạy.
5. **Thay đổi khác bị trộn:** một chỉnh sửa ngoài phạm vi làm test thay đổi.

### Quy trình điều tra

- Xác định test đầu tiên thất bại và đầu vào gây lỗi.
- So sánh kết quả thực tế với hợp đồng đã xác nhận.
- Kiểm tra diff nhỏ nhất liên quan tới thất bại.
- Nếu là hồi quy, sửa implementation hoặc hoàn tác bước vừa thực hiện.
- Nếu là defect cũ, tách việc sửa hành vi và cập nhật test với lý do rõ.
- Chạy lại cùng test và kiểm tra caller liên quan.

Một test thất bại là bằng chứng cần giải thích, không phải trở ngại cần làm biến mất.

## 13. Khi mã cũ chưa có test đủ tin cậy

Không phải lúc nào cũng có thể viết characterization test ngay. Có thể code phụ thuộc database, thời gian thật hoặc singleton toàn cục.

Trong trường hợp đó:

1. Chọn một luồng có thể quan sát qua API, log hoặc kết quả lưu trữ.
2. Tạo fixture dữ liệu nhỏ và có thể tái lập.
3. Ghi nhận đầu vào, trạng thái môi trường và đầu ra.
4. Nếu cần, thêm một seam nhỏ như Clock, repository hoặc gateway adapter.
5. Viết test ở ranh giới gần nhất có thể kiểm chứng.
6. Không mở rộng refactor sang vùng chưa có đường kiểm chứng.

Ví dụ, nếu không thể test CheckoutService độc lập vì nó tự tạo gateway, có thể trước hết truyền PaymentGateway qua constructor và dùng fake trong test. Nhưng nếu đang refactor policy giá, đừng đồng thời viết lại toàn bộ payment flow trừ khi đó là điều kiện cần để bảo vệ hành vi.

### Khi chưa thể chứng minh hành vi

Hãy thu hẹp thay đổi hoặc bổ sung quan sát trước. Có thể trì hoãn refactor nếu không có cách đáng tin để phát hiện hồi quy. Việc ghi rõ “chưa có test cho đường timeout” hữu ích hơn tuyên bố an toàn không có bằng chứng.

## 14. Kiểm tra diff và phạm vi thay đổi

Sau khi test chạy, đọc lại diff như một reviewer độc lập:

- Chỉ file và trách nhiệm liên quan có thay đổi?
- Có thay đổi format toàn file không cần thiết?
- Có public API hoặc schema bị đổi ngoài ý định?
- Có logic nghiệp vụ bị chuyển hoặc sửa công thức?
- Có dependency mới không cần thiết?
- Có test nào bị xóa hoặc giảm độ bao phủ hợp đồng?
- Có comment, TODO hoặc constructor cũ khiến hai đường triển khai tiếp tục tồn tại?
- Có mã không còn được dùng sau khi chuyển caller?

Một số kiểm tra thường hữu ích, tùy dự án:

~~~bash
git diff --check
git diff --stat
git diff
~~~

Lệnh git diff --check giúp phát hiện một số lỗi whitespace; nó không chứng minh logic đúng. Lệnh git diff --stat chỉ mô tả phạm vi file/dòng. Review nội dung diff vẫn cần thiết.

## 15. Khi nào cần rollback thay vì tiếp tục vá?

Rollback bước refactor vừa làm khi:

- Hành vi quan trọng thay đổi mà chưa hiểu nguyên nhân.
- Diff đã lan sang nhiều phần và không còn kiểm soát được phạm vi.
- Test nền không thể tái lập và chưa có bằng chứng thay thế.
- Ranh giới mới tạo coupling hoặc side effect ngoài dự kiến.
- Có nguy cơ dữ liệu/API bị phá mà chưa có phương án migration.
- Thời gian còn lại không đủ để kiểm chứng an toàn.

Rollback không phải thất bại cá nhân. Nó là một công cụ kiểm soát rủi ro. Sau khi quay lại trạng thái an toàn, ghi nhận điều còn thiếu: test, đặc tả, fixture, seam hoặc người sở hữu quyết định.

Với thay đổi đã được triển khai production, rollback cần theo quy trình phát hành và dữ liệu; không mặc định revert code là đủ nếu đã có migration hoặc side effect không thể đảo ngược.

## 16. Những lỗi thực hành thường gặp

| Lỗi | Hậu quả | Cách tránh |
| --- | --- | --- |
| Bắt đầu bằng việc đổi tên/format hàng loạt | Diff lớn, khó thấy thay đổi thật | Chỉ sửa phần cần cho mục tiêu |
| Không có baseline | Không biết lỗi đã tồn tại hay do refactor | Chạy test và ghi nhận revision trước |
| Chỉ so sánh hai caller với nhau | Cả hai có thể cùng sai | Dùng expected values độc lập từ đặc tả |
| Gộp policy khác nhau | Thay đổi một nghiệp vụ ảnh hưởng nghiệp vụ khác | Kiểm tra lý do thay đổi và ownership |
| Sửa expected test sau khi fail mà không điều tra | Che giấu hồi quy | Xác nhận hợp đồng và nguyên nhân |
| Trộn refactor với đổi nghiệp vụ | Không biết test đang bảo vệ thay đổi nào | Tách commit/PR hoặc mô tả từng phần |
| Chỉ chạy unit test | Bỏ sót wiring, SQL, API hoặc transaction | Chạy integration/contract test ở ranh giới bị tác động |
| Đo performance dù không có giả thuyết | Tốn công và dễ kết luận sai | Chỉ benchmark khi hiệu năng là mục tiêu |
| Xóa test cũ vì test mới đã có | Có thể mất kiểm tra caller hoặc regression | So sánh hợp đồng được bảo vệ trước khi xóa |
| Giữ đường khởi tạo cũ vô thời hạn | Caller tiếp tục bỏ qua seam mới | Chuyển caller và có kế hoạch loại bỏ |

## 17. Viết báo cáo refactor để người khác xác minh

Một báo cáo ngắn nên có:

- **Vấn đề:** điều gì đang gây chi phí hoặc rủi ro?
- **Mục tiêu:** cấu trúc nào sẽ thay đổi?
- **Hành vi cần giữ:** những trường hợp và hợp đồng nào?
- **Thay đổi:** phép biến đổi đã thực hiện.
- **Bằng chứng trước/sau:** test, output, checks và phạm vi.
- **Giới hạn:** phần nào chưa kiểm tra hoặc chưa đo.
- **Rủi ro còn lại:** điều gì cần follow-up?

### Ví dụ báo cáo

> “Hai service báo giá và checkout cùng định nghĩa chính sách VIP. Tôi đã thêm VipPricingPolicy, chuyển cả hai caller sang constructor injection và xóa hai bản sao. Các trường hợp dưới ngưỡng, đúng ngưỡng, làm tròn, không VIP và subtotal âm giữ nguyên theo test đặc tả. Test policy và test caller đều chạy đạt trong môi trường dự án. Chưa đo hiệu năng vì refactor không nhằm tối ưu tốc độ. Phí giao và voucher vẫn là các chính sách riêng.”

Báo cáo nêu thay đổi và bằng chứng, không tuyên bố “chất lượng tăng 50%” khi không có cách đo hợp lý.

## 18. Bài tập mở rộng: chọn một refactor nhỏ trong code của bạn

Chọn một vấn đề có thể mô tả bằng một câu:

- Một điều kiện nghiệp vụ bị lặp ở hai nơi.
- Một method vừa đọc thời gian vừa tính kết quả.
- Một service tự tạo HTTP client hoặc repository.
- Một hàm có tên không phản ánh đơn vị hoặc ý nghĩa đầu ra.
- Một lớp có hai trách nhiệm thường xuyên thay đổi độc lập.
- Một test không ổn định vì phụ thuộc trạng thái toàn cục.

### Thực hiện theo phiếu công việc

~~~text
VẤN ĐỀ
  Vị trí:
  Dấu hiệu quan sát được:
  Chi phí hoặc rủi ro:

MỤC TIÊU
  Một thay đổi cấu trúc cụ thể:
  Những gì nằm ngoài phạm vi:

HÀNH VI CẦN GIỮ
  Đầu vào:
  Kết quả mong đợi:
  Trường hợp biên:
  Lỗi/hợp đồng:

BẰNG CHỨNG TRƯỚC
  Revision:
  Test đã chạy:
  Kết quả:
  Kiểm tra bổ sung:

PHÉP BIẾN ĐỔI
  Bước 1:
  Bước 2:
  Bước 3:

BẰNG CHỨNG SAU
  Cùng test baseline:
  Test mới:
  Diff/check:
  Kết quả hành vi:
  Thay đổi cấu trúc:

GIỚI HẠN
  Chưa kiểm tra:
  Rủi ro còn lại:
  Người cần xem:
~~~

Không cần chọn vấn đề lớn nhất. Chọn vấn đề có giá trị, có thể kiểm tra và có đường hoàn tác rõ ràng.

## 19. Checklist trước khi kết thúc một refactor nhỏ

### Trước khi sửa

- [ ] Tôi mô tả được vấn đề bằng một quan sát cụ thể.
- [ ] Mục tiêu refactor nằm trong phạm vi nhỏ và rõ.
- [ ] Tôi phân biệt refactor với bug fix và thay đổi nghiệp vụ.
- [ ] Tôi đã đọc caller, dependency và ownership liên quan.
- [ ] Hợp đồng và các trường hợp biên đã được xác nhận.
- [ ] Tôi đã chạy và ghi nhận baseline phù hợp.

### Trong khi sửa

- [ ] Mỗi bước chỉ thực hiện một phép biến đổi có thể giải thích.
- [ ] Không trộn format hoặc đổi tên hàng loạt không liên quan.
- [ ] Các caller vẫn giữ trách nhiệm đúng.
- [ ] Test bảo vệ hành vi độc lập, không chỉ so sánh hai implementation.
- [ ] Nếu phát hiện defect, tôi ghi nhận và xử lý có chủ đích.

### Sau khi sửa

- [ ] Tôi chạy lại cùng test baseline trong điều kiện tương đương.
- [ ] Test mới kiểm tra mục tiêu cấu trúc hoặc ranh giới cần bảo vệ.
- [ ] Tôi xem diff và kiểm tra phạm vi file thay đổi.
- [ ] Tôi so sánh bằng chứng trước/sau theo đúng mục tiêu.
- [ ] Tôi không tuyên bố cải thiện hiệu năng nếu chưa đo.
- [ ] Tôi ghi rõ giới hạn và rủi ro chưa được kiểm tra.
- [ ] Tôi có thể rollback bước vừa làm nếu cần.
- [ ] Người review có thể hiểu lý do và xác minh kết quả.

## 20. Câu hỏi tự kiểm tra

1. Refactor bảo toàn hành vi khác sửa lỗi ở điểm nào?
2. Vì sao cần giới hạn phạm vi trước khi bắt đầu?
3. Baseline trước refactor nên gồm những bằng chứng gì?
4. Characterization test giúp gì khi tài liệu nghiệp vụ chưa đầy đủ?
5. Vì sao test chỉ so sánh báo giá với checkout có thể bỏ sót lỗi?
6. Một oracle độc lập trong test là gì?
7. Khi phát hiện hai caller có kết quả khác nhau, cần làm gì trước khi hợp nhất?
8. Vì sao nên đọc caller và dependency trước khi trích xuất policy?
9. Bước nào trong ví dụ tạo một nguồn sở hữu chính sách VIP?
10. Vì sao hai service vẫn nên giữ trách nhiệm riêng sau khi dùng chung policy?
11. Cần test policy và test caller để bảo vệ hai loại rủi ro nào?
12. Vì sao phải chạy lại cùng bộ test sau refactor?
13. Những điều kiện nào khiến việc so sánh trước/sau không công bằng?
14. Khi nào cần benchmark và khi nào không?
15. Số dòng giảm có chứng minh khả năng bảo trì tốt hơn không?
16. Nếu test fail sau refactor, vì sao không nên sửa expected value ngay?
17. Khi nào nên rollback thay vì tiếp tục vá?
18. Nếu chưa có test, có thể tạo bằng chứng trước refactor bằng cách nào?
19. Báo cáo refactor cần nêu những giới hạn nào?
20. Hãy chọn một thay đổi nhỏ trong hệ thống bạn biết và viết phiếu bằng chứng trước/sau.

## Ghi nhớ

**Một refactor nhỏ có chất lượng bắt đầu bằng vấn đề quan sát được, bảo vệ hành vi bằng bằng chứng trước thay đổi, thực hiện một phép biến đổi hẹp rồi kiểm tra lại trong điều kiện tương đương.** Hãy xác nhận hợp đồng, đọc caller, viết characterization test, lưu baseline, thay đổi từng bước và so sánh kết quả sau đó. Khi test thất bại, điều tra nguyên nhân thay vì làm xanh bằng cách sửa kỳ vọng tùy tiện. Báo cáo cả điều đã chứng minh lẫn giới hạn còn lại. Mục tiêu là làm cấu trúc dễ hiểu và dễ thay đổi hơn trong khi giữ mã **đáng tin cậy, dễ hiểu và dễ thay đổi**.
