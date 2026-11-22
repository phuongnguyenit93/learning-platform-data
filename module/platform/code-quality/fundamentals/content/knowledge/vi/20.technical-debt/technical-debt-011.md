# Kiểm chứng chi phí hoặc rủi ro đã giảm sau khi xử lý

Một nhóm dành ba ngày để xử lý nợ kỹ thuật trong chức năng tính phí giao hàng. Hai đoạn điều kiện giống nhau được đưa về một lớp chính sách chung, độ trùng lặp trong báo cáo giảm và số dòng mã ít hơn. Bản thay đổi được merge, mọi test đều xanh. Người quản lý hỏi: **“Vậy từ nay việc sửa chức năng có nhanh hơn, hay khả năng tính phí sai đã giảm đi bao nhiêu?”**

Nếu nhóm chỉ trả lời “đã xóa được 80 dòng” hoặc “điểm chất lượng tăng”, họ mới mô tả **hoạt động đã thực hiện**, chưa chứng minh **lợi ích của việc trả nợ**. Xử lý nợ kỹ thuật không kết thúc ở lúc refactor hoàn tất; nó còn cần xác minh rủi ro nào được giảm, chi phí nào thay đổi và bằng chứng nào đủ sức hỗ trợ kết luận.

Trong module **CODE_QUALITY_FUNDAMENTALS**, chúng ta học các thuộc tính giúp mã nguồn **đáng tin cậy, dễ hiểu và dễ thay đổi**. Ở chương **Nợ kỹ thuật**, bài này tập trung vào cách **kiểm chứng chi phí hoặc rủi ro đã giảm sau khi xử lý**, từ việc xác định giả thuyết trước khi sửa, bảo vệ hành vi hiện có, thu thập số liệu so sánh được, đến đánh giá kết quả và rủi ro còn lại.

## Mục tiêu học tập

Sau bài học, bạn có thể:

- Phân biệt **nợ đã được xử lý về mặt cấu trúc** với **chi phí hoặc rủi ro được chứng minh là đã giảm**.
- Đặt giả thuyết cải tiến có chỉ số, đường cơ sở (baseline), phạm vi, mốc đo và tiêu chí xác nhận rõ ràng.
- Kết hợp các tín hiệu như trùng lặp, độ phức tạp, thời gian sửa đổi, tỷ lệ lỗi hồi quy, thời gian xử lý sự cố và bằng chứng kiểm thử.
- Thiết kế kiểm thử Java/JUnit 5 để **bảo toàn hành vi** khi refactor và kiểm chứng quy tắc nghiệp vụ quan trọng.
- Đọc kết quả trước–sau mà không đánh đồng tương quan với quan hệ nguyên nhân–kết quả hoặc xem số sự cố bằng không là không còn rủi ro.
- Báo cáo minh bạch lợi ích đã quan sát, giới hạn bằng chứng, chi phí xử lý và phần nợ còn lại.

## 1. Trả nợ kỹ thuật nhằm thay đổi điều gì?

**Nợ kỹ thuật (technical debt)** là cách nói về những lựa chọn hoặc cấu trúc kỹ thuật làm tăng **chi phí hay rủi ro của công việc về sau** so với một phương án phù hợp hơn trong bối cảnh dự án. Nợ có thể phát sinh từ một quyết định đánh đổi có chủ đích để ra mắt sớm, hoặc từ thiết kế cũ không còn phù hợp sau khi yêu cầu và quy mô thay đổi.

Một khoản nợ có thể biểu hiện ở:

- **Chi phí thay đổi:** muốn sửa một quy tắc phải chỉnh nhiều lớp, nhiều module hoặc phối hợp nhiều nhóm.
- **Chi phí kiểm chứng:** mỗi lần sửa phải dựng môi trường phức tạp, test không ổn định, cần kiểm tra thủ công nhiều đường đi.
- **Chi phí vận hành:** sự cố khó chẩn đoán, thời gian phục hồi lâu, nhiều bước triển khai thủ công.
- **Rủi ro đúng đắn và an toàn:** logic bị lặp dễ sửa lệch, cấu trúc dữ liệu cho phép trạng thái bất hợp lệ, thiếu điểm kiểm soát quyền hoặc transaction.
- **Rủi ro tương lai:** thay đổi đối tác, tăng tải hoặc bổ sung loại nghiệp vụ có thể làm giải pháp hiện tại trở nên mong manh.

Tư duy hữu ích là phân biệt **chi phí xử lý** một khoản nợ với **chi phí tiếp tục mang nợ**. Chẳng hạn, bỏ hai ngày để gom quy tắc tính phí có thể đáng giá nếu mỗi thay đổi tiếp theo bớt phải sửa ở nhiều nơi và giảm nguy cơ áp dụng chính sách không nhất quán. Nhưng lợi ích ấy cần được **đánh giá theo công việc thực tế**, không được mặc định chỉ vì mã ngắn hơn.

### Ba mức kết luận khác nhau

| Mức | Câu hỏi | Ví dụ bằng chứng |
| --- | --- | --- |
| **Đã thực hiện việc sửa** | Cấu trúc có thay đổi như kế hoạch không? | PR đã merge, hai nhánh logic lặp được thay bằng một chính sách chung |
| **Hành vi vẫn đúng** | Refactor có giữ hợp đồng và sửa đúng những sai lệch được phép không? | Test đặc tả, test biên, integration test và kết quả review |
| **Chi phí/rủi ro đã giảm** | Công việc tương lai có thực sự bớt tốn kém, ít lỗi hơn hoặc dễ khôi phục hơn không? | Số nơi cần sửa, thời gian thay đổi thực tế, lỗi hồi quy theo cơ hội thay đổi, sự cố và dữ liệu vận hành |

Mức thứ nhất **không tự chứng minh** mức thứ hai; hai mức đầu cũng **không tự chứng minh** mức thứ ba. Một khoản nợ có thể đã được xử lý tốt về cấu trúc nhưng chưa có đủ lần thay đổi tiếp theo để quan sát lợi ích dài hạn. Khi đó, kết luận đúng là **“đã hoàn tất cải tiến và có chỉ báo sớm tích cực; hiệu quả dài hạn cần tiếp tục đo”**.

## 2. Bắt đầu bằng giả thuyết, không bắt đầu bằng công cụ

Trước khi refactor, hãy ghi rõ:

1. **Vấn đề hiện tại:** Điều gì khiến chi phí hoặc rủi ro tăng? Có ví dụ công việc hoặc sự cố cụ thể không?
2. **Cơ chế gây ra vấn đề:** Tại sao cấu trúc mã hiện tại dẫn đến chi phí hoặc rủi ro ấy?
3. **Thay đổi dự kiến:** Sẽ sửa ranh giới, dữ liệu, phụ thuộc hoặc luồng xử lý nào?
4. **Tác động kỳ vọng:** Sau sửa, điều gì sẽ ít xảy ra hơn, nhanh hơn hoặc dễ kiểm tra hơn?
5. **Cách kiểm chứng:** Chỉ số, test, review và dữ liệu thực tế nào có thể xác nhận hoặc bác bỏ giả thuyết?
6. **Điều kiện không được đánh đổi:** Những hành vi, giới hạn hiệu năng, phân quyền và điều kiện vận hành nào phải được giữ?

Ví dụ:

> **Giả thuyết:** Hai nơi tự tính phí giao hàng khiến mỗi lần đổi ngưỡng miễn phí phải sửa ở hai điểm, dễ quên một nơi và gây kết quả không nhất quán. Nếu gom chính sách vào một thành phần dùng chung, những thay đổi chính sách sau đó chỉ cần sửa **một nơi chịu trách nhiệm**, trong khi checkout và hóa đơn vẫn cho cùng kết quả đối với cùng loại đơn hàng.

Giả thuyết này tốt hơn mục tiêu “giảm độ trùng lặp xuống 0%” vì nó nêu **tại sao trùng lặp gây hại** và **hành vi nào cần bảo vệ**.

### Mẫu kế hoạch đo lường tối giản

| Trường | Ví dụ minh họa |
| --- | --- |
| Vấn đề | Quy tắc phí giao hàng bị lặp ở checkout và lập hóa đơn |
| Mục tiêu | Một thay đổi chính sách cần sửa ít nơi hơn và không tạo kết quả lệch |
| Baseline | Hai vị trí triển khai chính sách; số file sửa và thời gian review của những thay đổi tương tự trong kỳ trước |
| Tiêu chí tức thời | Chỉ còn một nguồn quy tắc; hai đường gọi dùng cùng hợp đồng; test giá trị biên đạt |
| Tiêu chí theo dõi | Thời gian/độ rộng thay đổi chính sách, số lỗi hồi quy trên số thay đổi có cơ hội gây lỗi |
| Điều không được làm xấu đi | Quy tắc nghiệp vụ đã xác nhận, thời gian xử lý trong giới hạn, khả năng tính hóa đơn cũ |
| Mốc xem lại | Sau một số thay đổi cùng loại hoặc sau giai đoạn quan sát đã thống nhất |
| Chủ sở hữu | Nhóm chịu trách nhiệm chính sách vận chuyển |

Các mốc thời gian, tiêu chí và ngưỡng phải được **đội dự án quyết định theo điều kiện thật**; không có một con số chung chứng minh mọi khoản nợ đã được trả hiệu quả.

## 3. Đo chi phí thực tế khác với đo hình dạng mã

Những chỉ số cấu trúc rất hữu ích để phát hiện và theo dõi một dấu hiệu nợ, nhưng chúng thường là **chỉ số thay thế (proxy)** cho chi phí hoặc rủi ro.

| Nhóm tín hiệu | Ví dụ | Có thể kết luận gì? | Chưa thể kết luận gì? |
| --- | --- | --- | --- |
| **Cấu trúc** | Số nơi lặp quy tắc, coupling, complexity | Phạm vi cấu trúc đã thay đổi theo hướng nào | Thời gian sửa lỗi chắc chắn giảm |
| **Quy trình thay đổi** | Thời gian từ bắt đầu đến review xong, số file phải sửa | Độ rộng và chi phí của những thay đổi đã quan sát | Tất cả thay đổi tương lai sẽ nhanh hơn |
| **Kiểm chứng** | Test biên, mutation score, thời gian chạy test | Một số đường hành vi được kiểm tra tốt hơn | Không còn bug hoặc test đã đúng mọi yêu cầu |
| **Vận hành** | Lỗi hồi quy, thời gian khôi phục, số lần rollback | Những hậu quả đã được ghi nhận trong một kỳ | Không xảy ra lỗi nếu chưa quan sát thấy |
| **Đánh giá định tính** | Review về trách nhiệm, độ dễ hiểu, ranh giới thay đổi | Lý do giảm liên kết hoặc rủi ro được giải thích | Nhận định chủ quan tự nó là kết quả sản xuất |

Ví dụ, sau khi gộp hai phương thức thành một, **số nơi sửa giảm từ hai xuống một** là kết quả có thể kiểm tra ngay. Nhưng “thời gian thay đổi giảm 50%” vẫn chỉ là **dự đoán** cho đến khi có dữ liệu về những lần sửa sau đó trong điều kiện tương đối so sánh được.

Một mô hình suy luận thực tế:

~~~text
Vấn đề & cơ chế gây nợ
          |
          v
Thay đổi cấu trúc đã hoàn tất
          |
          +----> Test/review chứng minh hành vi còn đúng
          |
          v
Chỉ báo sớm: số nơi phải sửa, điểm phụ thuộc, độ dễ kiểm thử
          |
          v
Kết quả thực tế: thời gian thay đổi, lỗi hồi quy, sự cố, MTTR
          |
          v
Kết luận có phạm vi + rủi ro còn lại
~~~

**Không nên đánh đồng một chỉ báo sớm tích cực với kết quả dài hạn đã được xác nhận.**

## 4. Ví dụ xuyên suốt: nợ do lặp quy tắc phí giao hàng

Giả sử hệ thống Java có hai luồng: **checkout** tính phí giao hàng để hiển thị cho khách và **lập hóa đơn** tính lại phí để ghi chứng từ. Chính sách giả định đã được xác nhận:

- Tổng tiền hàng được biểu diễn bằng số nguyên VND, không âm.
- Giao **STANDARD** được miễn phí nếu tổng tiền hàng **từ 500.000 VND trở lên**; nếu thấp hơn, phí là 20.000 VND.
- Giao **EXPRESS** luôn có phí 30.000 VND, không áp dụng miễn phí theo ngưỡng trên.
- Hai luồng cần dùng cùng chính sách đối với cùng một yêu cầu nghiệp vụ.
- Hàm tính phí không tự ghi database hoặc thu tiền.

Ví dụ dùng **Java 17 trở lên**; trong dự án thật, mỗi kiểu `public` cần đặt ở file Java riêng. Các con số và chính sách là **dữ liệu minh họa**, không phải quy định áp dụng cho một doanh nghiệp cụ thể.

### 4.1. Trước khi xử lý: hai nơi tự quyết định cùng một quy tắc

~~~java
public enum DeliveryType {
    STANDARD,
    EXPRESS
}
~~~

~~~java
import java.util.Objects;

public final class CheckoutDeliveryCalculator {
    public long calculateFee(long subtotalVnd, DeliveryType type) {
        if (subtotalVnd < 0) {
            throw new IllegalArgumentException("Negative subtotal");
        }
        Objects.requireNonNull(type, "type");

        if (type == DeliveryType.EXPRESS) {
            return 30_000;
        }
        if (subtotalVnd >= 500_000) {
            return 0;
        }
        return 20_000;
    }
}
~~~

~~~java
import java.util.Objects;

public final class InvoiceDeliveryCalculator {
    public long calculateFee(long subtotalVnd, DeliveryType type) {
        if (subtotalVnd < 0) {
            throw new IllegalArgumentException("Negative subtotal");
        }
        Objects.requireNonNull(type, "type");

        if (type == DeliveryType.EXPRESS) {
            return 30_000;
        }
        if (subtotalVnd >= 500_000) {
            return 0;
        }
        return 20_000;
    }
}
~~~

**Mùi nợ kỹ thuật** là hai nơi cùng chịu trách nhiệm một chính sách. Khi ngưỡng miễn phí đổi từ 500.000 sang một giá trị khác, người sửa phải nhớ cập nhật **cả hai**. Nếu chỉ cập nhật checkout, khách có thể nhìn thấy một khoản phí nhưng hóa đơn ghi khoản khác.

Lưu ý: **hai đoạn giống nhau không tự động là nợ kỹ thuật**. Nếu checkout và hóa đơn có các quy tắc thực sự khác nhau, gộp chúng có thể là thiết kế sai. Trong ví dụ này, yêu cầu đã xác nhận rằng chúng phải **dùng cùng một chính sách**; đó là cơ sở để gộp.

### 4.2. Sau khi xử lý: một trách nhiệm chính sách

~~~java
import java.util.Objects;

public final class DeliveryFeePolicy {
    private static final long FREE_STANDARD_THRESHOLD_VND = 500_000;
    private static final long STANDARD_FEE_VND = 20_000;
    private static final long EXPRESS_FEE_VND = 30_000;

    public long calculateFee(long subtotalVnd, DeliveryType type) {
        if (subtotalVnd < 0) {
            throw new IllegalArgumentException("Negative subtotal");
        }
        Objects.requireNonNull(type, "type");

        if (type == DeliveryType.EXPRESS) {
            return EXPRESS_FEE_VND;
        }
        return subtotalVnd >= FREE_STANDARD_THRESHOLD_VND
            ? 0
            : STANDARD_FEE_VND;
    }
}
~~~

Hai thành phần sử dụng lại chính sách:

~~~java
import java.util.Objects;

public final class CheckoutDeliveryCalculator {
    private final DeliveryFeePolicy policy;

    public CheckoutDeliveryCalculator(DeliveryFeePolicy policy) {
        this.policy = Objects.requireNonNull(policy, "policy");
    }

    public long calculateFee(long subtotalVnd, DeliveryType type) {
        return policy.calculateFee(subtotalVnd, type);
    }
}
~~~

~~~java
import java.util.Objects;

public final class InvoiceDeliveryCalculator {
    private final DeliveryFeePolicy policy;

    public InvoiceDeliveryCalculator(DeliveryFeePolicy policy) {
        this.policy = Objects.requireNonNull(policy, "policy");
    }

    public long calculateFee(long subtotalVnd, DeliveryType type) {
        return policy.calculateFee(subtotalVnd, type);
    }
}
~~~

Ví dụ trước và sau minh họa **hai phiên bản thiết kế thay thế**, không phải các class trùng tên cần biên dịch cùng lúc. Trong phiên bản sau, có thể tạo một `DeliveryFeePolicy` và truyền vào cả hai thành phần ở nơi khởi tạo ứng dụng.

**Điểm cải thiện được thấy ngay:** quy tắc ngưỡng và mức phí có một nơi chịu trách nhiệm. Nhưng sự tập trung này cũng tạo **điểm ảnh hưởng chung**: nếu sửa sai `DeliveryFeePolicy`, cả checkout và hóa đơn cùng sai. Vì vậy giảm số bản sao phải đi kèm **hợp đồng và bộ kiểm thử mạnh tại ranh giới chính sách**, không chỉ giảm dòng mã.

## 5. Bước đầu tiên của kiểm chứng: giữ đúng hành vi

Refactor khác với thay đổi chính sách. Với ví dụ trên, mục tiêu là **giữ nguyên kết quả được xác nhận** cho những đầu vào hợp lệ, và giữ cách xử lý đầu vào sai nếu đó là hợp đồng đã được công bố.

Trước khi xóa hai nhánh cũ, nhóm nên có **bảng quyết định dựa trên yêu cầu**, không chỉ sao chép biểu thức từ implementation cũ:

| Tổng tiền (VND) | Loại giao | Kỳ vọng phí (VND) | Vì sao cần test? |
| ---: | --- | ---: | --- |
| 0 | STANDARD | 20.000 | Biên thấp hợp lệ |
| 499.999 | STANDARD | 20.000 | Ngay dưới ngưỡng |
| **500.000** | **STANDARD** | **0** | **Đúng ngưỡng, dễ nhầm `>=` với `>`** |
| 500.001 | STANDARD | 0 | Ngay trên ngưỡng |
| 500.000 | EXPRESS | 30.000 | EXPRESS không dùng ưu đãi |
| -1 | STANDARD | Lỗi | Không cho giá trị âm |

### Kiểm thử quy tắc bằng JUnit 5

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.CsvSource;

class DeliveryFeePolicyTest {
    private final DeliveryFeePolicy policy = new DeliveryFeePolicy();

    @ParameterizedTest
    @CsvSource({
        "0,      STANDARD, 20000",
        "499999, STANDARD, 20000",
        "500000, STANDARD, 0",
        "500001, STANDARD, 0",
        "500000, EXPRESS,  30000"
    })
    void followsConfirmedBusinessPolicy(
            long subtotalVnd, DeliveryType type, long expectedFee) {
        assertEquals(
            expectedFee,
            policy.calculateFee(subtotalVnd, type)
        );
    }

    @Test
    void rejectsInvalidSubtotalAndType() {
        assertThrows(
            IllegalArgumentException.class,
            () -> policy.calculateFee(-1, DeliveryType.STANDARD)
        );
        assertThrows(
            NullPointerException.class,
            () -> policy.calculateFee(100_000, null)
        );
    }
}
~~~

### Kiểm thử hai đường gọi dùng cùng chính sách

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;

import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.CsvSource;

class DeliveryFeeIntegrationOfComponentsTest {
    private final DeliveryFeePolicy policy = new DeliveryFeePolicy();
    private final CheckoutDeliveryCalculator checkout =
        new CheckoutDeliveryCalculator(policy);
    private final InvoiceDeliveryCalculator invoice =
        new InvoiceDeliveryCalculator(policy);

    @ParameterizedTest
    @CsvSource({
        "499999, STANDARD, 20000",
        "500000, STANDARD, 0",
        "500001, STANDARD, 0",
        "500000, EXPRESS, 30000"
    })
    void bothCallersFollowSamePolicy(
            long subtotalVnd, DeliveryType type, long expectedFee) {
        assertEquals(expectedFee, checkout.calculateFee(subtotalVnd, type));
        assertEquals(expectedFee, invoice.calculateFee(subtotalVnd, type));
    }
}
~~~

Test thứ hai **không chỉ kiểm tra hai kết quả bằng nhau**. Nếu cả hai cùng trả kết quả sai, phép so sánh `checkoutFee == invoiceFee` vẫn xanh. Vì vậy test dùng **giá trị kỳ vọng độc lập từ chính sách**, sau đó xác minh cả hai thành phần cùng tuân thủ.

### Có thể dùng differential testing không?

Trong quá trình chuyển đổi, có thể chạy cùng tập đầu vào qua **phiên bản cũ và mới** để tìm sai khác ngoài ý muốn (*differential testing*). Cách này giúp phát hiện lỗi refactor khi hành vi cũ đã được xác nhận đúng trong phạm vi đó.

Nhưng nếu phiên bản cũ vốn có lỗi nghiệp vụ, kết quả giống nhau **không chứng minh** hai bên đều đúng. Hãy kết hợp so sánh cũ–mới với **bộ đặc tả độc lập** và quyết định rõ những sai khác nào là sửa lỗi có chủ đích. Với mã điều khiển tác dụng phụ như thanh toán, không chạy hai triển khai cùng tạo giao dịch thật chỉ để so sánh; cần môi trường thử an toàn và chiến lược quan sát thích hợp.

## 6. Sau khi test xanh, chi phí thay đổi đã giảm chưa?

Ngay sau refactor, nhóm có thể kiểm chứng những điều **cấu trúc** sau:

- Một chính sách về ngưỡng và mức phí chỉ có một điểm cài đặt.
- Hai đường gọi phụ thuộc vào cùng hợp đồng `DeliveryFeePolicy`.
- Khi đổi ngưỡng trong mô phỏng review, không phải cập nhật hai biểu thức phí độc lập.
- Test có thể kiểm tra riêng chính sách mà không dựng môi trường checkout và hóa đơn đầy đủ.

Đây là **bằng chứng sớm** rằng chi phí sửa đổi *có khả năng* giảm. Để biết chi phí **thực tế**, cần quan sát những lần thay đổi tương tự sau đó.

### Chọn chỉ số phản ánh đúng công việc

| Chỉ số | Cách thu thập | Rủi ro diễn giải |
| --- | --- | --- |
| **Số nơi phải đổi quy tắc** | Review diff của những PR thay chính sách | Một nơi sửa ít hơn chưa chắc toàn bộ việc ít công hơn |
| **Số file/module bị tác động** | Git diff/PR và tài liệu review | Đếm file không phản ánh mức khó của thay đổi |
| **Thời gian làm thay đổi** | Mốc bắt đầu hợp lý → PR sẵn sàng review/hoàn tất | Phụ thuộc độ lớn yêu cầu, người làm, lịch chờ review |
| **Thời gian kiểm chứng** | Thời gian chạy test, setup và kiểm tra thủ công | Test chạy nhanh hơn nhưng có thể bỏ sót ca quan trọng |
| **Số lần review lại** | Chu kỳ review cho thay đổi cùng loại | Review kỹ hơn có thể tăng số vòng nhưng giảm lỗi |
| **Lỗi hồi quy theo cơ hội thay đổi** | Số thay đổi gây lỗi / số thay đổi cùng loại trong kỳ | Mẫu nhỏ, chất lượng phát hiện, mức tác động khác nhau |
| **Thời gian xử lý sự cố** | Từ nhận diện tới khôi phục theo quy ước | Phụ thuộc severity, vận hành và hệ thống ngoài |

Các chỉ số này cần được định nghĩa **trước khi so sánh**. Chẳng hạn, “thời gian sửa” có tính thời gian đợi người review nghỉ phép không? Nếu tính toàn bộ lead time, thay đổi ở lịch review có thể làm số đo giảm/tăng mà không liên quan tới cấu trúc code.

**Không nên đo năng suất chỉ bằng số dòng code xóa đi.** Xóa 500 dòng nhưng thêm một tầng trừu tượng khó hiểu có thể tăng chi phí sửa; đôi khi thêm một lớp domain rõ nghĩa lại làm việc về sau dễ hơn dù số dòng tăng.

## 7. So sánh trước và sau phải cùng phạm vi

Giả sử nhóm có dữ liệu minh họa từ các thay đổi **cùng loại** về chính sách phí giao hàng:

| Số liệu minh họa | Trước khi xử lý | Sau khi xử lý |
| --- | ---: | ---: |
| Số vị trí độc lập chứa quy tắc | 2 | 1 |
| Trung vị thời gian làm một thay đổi chính sách | 6 giờ | 4 giờ |
| Trung vị số file mã phải sửa | 4 | 2 |
| Số thay đổi cùng loại được quan sát | 20 | 24 |
| Thay đổi phát sinh lỗi hồi quy được ghi nhận | 3 | 1 |

Từ bảng:

- Số điểm cài đặt quy tắc giảm **2 → 1**: đây là kết quả cấu trúc trực tiếp.
- Trung vị thời gian thay đổi giảm **6 → 4 giờ** trong hai mẫu đã quan sát.
- Tỷ lệ thay đổi có lỗi hồi quy được ghi nhận là **3/20 = 15%** trước và **1/24 ≈ 4,2%** sau.

**Đây chỉ là số liệu minh họa về cách đọc báo cáo**, không phải kết quả đo của dự án nào. Sự khác biệt trong mẫu **không đủ chứng minh riêng refactor gây ra mức giảm**. Ngoài ra, 20 và 24 thay đổi là mẫu khá nhỏ để rút ra kết luận chắc chắn về tỷ lệ lỗi tương lai.

### Các yếu tố gây nhiễu cần kiểm tra

- **Độ khó của yêu cầu:** sau refactor chỉ có thay đổi đổi hằng số, trước đó gồm bổ sung nhiều loại giao hàng mới?
- **Nhân sự:** nhóm có thêm người nhiều kinh nghiệm hoặc vừa hoàn thành onboarding?
- **Quy trình:** CI, test automation hoặc thời gian review có đổi cùng kỳ không?
- **Mức độ sử dụng:** số đơn hàng, thị trường và các loại đơn có tương đương không?
- **Cách ghi nhận lỗi:** nhóm có thay đổi định nghĩa hồi quy hoặc hệ thống báo lỗi không?
- **Phiên bản và cấu hình:** cùng JDK, cùng luồng nghiệp vụ, cùng cách triển khai hay không?
- **Tác động ngoài vùng sửa:** một quy tắc dùng chung có làm tăng lỗi ở tính năng khác không?

Nếu những yếu tố này thay đổi lớn, cần **ghi nhận và điều chỉnh cách diễn giải**. Có thể so sánh các nhóm thay đổi tương tự, phân tầng theo độ khó, xem xu hướng trước cải tiến hoặc dùng một vùng đối chứng phù hợp nếu có. Tuy nhiên, không được thực hiện thí nghiệm nguy hiểm trên người dùng thật chỉ để đo rủi ro đã giảm.

## 8. “Ít sự cố hơn” phải được đọc cùng cơ hội phát sinh sự cố

Giả sử sau sửa, trong một tháng không có lỗi tính phí nào được báo. Có thể nói:

> “Trong phạm vi theo dõi của tháng này, chưa ghi nhận lỗi tính phí.”

**Không nên nói:**

> “Đã loại bỏ hoàn toàn khả năng tính phí sai.”

Lỗi có thể rất hiếm; số giao dịch có thể ít; một số dữ liệu chưa được đi qua; giám sát có thể chưa phát hiện các sai khác nhỏ. **Số quan sát bằng không không có nghĩa xác suất bằng không.**

Khi đo rủi ro vận hành, nên ghi:

| Trường | Câu hỏi |
| --- | --- |
| **Sự kiện cần ngăn** | “Hóa đơn khác phí đã báo ở checkout” hay “mọi lỗi giao hàng”? |
| **Mẫu số / cơ hội xảy ra** | Số đơn được xử lý, số lần đổi chính sách, số yêu cầu của tính năng? |
| **Khoảng thời gian** | Quan sát từ ngày nào đến ngày nào và phiên bản nào? |
| **Cách phát hiện** | Đối soát dữ liệu, cảnh báo, báo cáo của khách hay test hồi quy? |
| **Mức tác động** | Sai phí bao nhiêu, số khách bị ảnh hưởng, có cần hoàn tiền không? |
| **Khả năng bỏ sót** | Có dữ liệu không được đối soát hoặc luồng ngoài hệ thống không? |

Một chỉ số có thể là **số đơn phát hiện lệch phí trên 10.000 đơn có cả dữ liệu checkout và hóa đơn**, thay vì chỉ đếm số ticket. Nhưng chỉ số này có ý nghĩa khi hai nguồn dữ liệu **được đối soát đúng cách**, mẫu số được định nghĩa rõ và độ phủ ghi nhận được biết.

Ngay cả khi xu hướng lỗi giảm, cần xem liệu **một lỗi đơn lẻ có tác động lớn hơn trước không**. Gộp logic vào một thành phần chung có thể làm nhiều luồng cùng phụ thuộc vào cùng một sai sót.

## 9. Kiểm chứng giảm rủi ro bằng chứng cứ theo tầng

Với một khoản nợ liên quan tới đúng đắn, bảo mật hoặc đồng thời, không nên đợi lỗi production xuất hiện mới đánh giá.

| Tầng bằng chứng | Điều có thể kiểm chứng sớm | Giới hạn |
| --- | --- | --- |
| **Code/design review** | Một nơi sở hữu quy tắc; phụ thuộc, tiền điều kiện và tác dụng phụ rõ | Review không tự chứng minh mọi đường chạy |
| **Unit test** | Kết quả đúng ở giá trị biên và tổ hợp chính | Chưa kiểm tra database, API hoặc cấu hình thật |
| **Mutation/property testing** | Test nhạy với một số biến thể logic, bất biến được giữ trên tập đầu vào sinh | Chỉ trong phạm vi mutant/generator và oracle đã chọn |
| **Integration/contract test** | Hai thành phần thật trao đổi kết quả và dữ liệu theo hợp đồng | Môi trường test có thể khác production |
| **Staging/canary có kiểm soát** | Hành vi qua luồng gần thực tế, hiệu năng và tín hiệu lỗi khi triển khai | Không đại diện mọi tải/trạng thái |
| **Quan sát production** | Lỗi lệch phí, khiếu nại và sự cố sau phát hành | Có độ trễ, yếu tố gây nhiễu và vấn đề phát hiện |

### Những kiểm chứng quan trọng trong ví dụ phí giao hàng

1. **Tính đúng đắn:** phí tại 499.999, 500.000, 500.001 VND và loại EXPRESS có khớp quy tắc không?
2. **Tính nhất quán:** checkout và hóa đơn lấy kết quả từ cùng chính sách, hay còn một đường khác tự tính riêng?
3. **Tương thích:** những hóa đơn đã phát hành có bị tính lại sai khi chính sách thay đổi theo thời gian không?
4. **Hiệu năng:** lớp chính sách chung có thêm I/O hoặc làm tăng độ trễ trên đường quan trọng không?
5. **Tính sẵn sàng:** một thay đổi chính sách sai có làm tất cả kênh cùng ảnh hưởng không? Có test, giám sát và phương án rollback không?
6. **Dữ liệu đầu vào:** `subtotalVnd` ở checkout và hóa đơn có cùng định nghĩa về thuế, giảm giá, làm tròn và thời điểm áp dụng không?

Điểm thứ sáu đặc biệt quan trọng: **cùng gọi một hàm không đủ bảo đảm cùng kết quả nếu hai nơi truyền vào các giá trị mang ngữ nghĩa khác nhau**. Cần xác nhận hợp đồng dữ liệu chứ không chỉ hợp nhất mã.

## 10. Đừng biến mục tiêu giảm rủi ro thành việc chạy theo điểm số

Một số trường hợp dễ dẫn tới kết luận sai:

| Sau khi sửa, chỉ số... | Điều có thể đã tốt lên | Điều vẫn cần kiểm chứng |
| --- | --- | --- |
| Duplication giảm | Bớt bản sao logic, giảm điểm phải sửa | Hai trường hợp có thật sự cùng quy tắc? |
| Complexity giảm | Ít nhánh trong một phương thức | Tổng luồng có dễ hiểu hơn hay logic bị dàn trải? |
| Coverage tăng | Nhiều dòng/nhánh được chạy trong test | Assertion có đúng kỳ vọng nghiệp vụ không? |
| Cảnh báo phân tích tĩnh giảm | Một số vấn đề đã được xử lý | Có tắt rule hoặc exclude tệp không? |
| Thời gian CI giảm | Feedback có thể nhanh hơn | Test quan trọng có bị bỏ đi hoặc giảm mức kiểm chứng không? |
| Số ticket lỗi giảm | Ít lỗi được ghi nhận hơn | Mẫu số, tải sử dụng, cơ chế phát hiện có đổi không? |
| Thời gian review giảm | PR có thể dễ hiểu hơn | Review có còn kiểm tra đúng rủi ro không? |

Vì vậy, trước khi công bố “đã giảm nợ”, cần kết hợp **chỉ số + lời giải thích cơ chế + kiểm chứng hành vi**. Một chỉ số bị tối ưu vì nó có thể đánh mất giá trị như tín hiệu chất lượng.

## 11. Chi phí trả nợ và lợi ích không đến cùng lúc

Xử lý nợ kỹ thuật cũng có chi phí:

- Thời gian phân tích, thiết kế và viết test đặc tả.
- Thời gian thực hiện refactor và review.
- Chi phí triển khai, chuyển dữ liệu hoặc hỗ trợ tương thích.
- Rủi ro hồi quy do thay đổi cấu trúc.
- Chi phí bảo trì abstraction mới hoặc vận hành hệ thống sau sửa.

Vì vậy, **lợi ích thuần** nên được đánh giá theo giai đoạn, không chỉ theo những giờ tiết kiệm ở một PR.

Ví dụ **giả định**: nhóm bỏ ra 16 giờ để hợp nhất chính sách và viết test. Nếu sau đó mỗi thay đổi chính sách tương đương bớt trung bình 2 giờ, thì sau **8 thay đổi cùng loại**, phần giờ tiết kiệm quan sát được có thể **bù 16 giờ xử lý ban đầu**, *nếu* cách đo và phạm vi công việc so sánh được.

Đây chỉ là **mô hình hòa vốn giản lược**; chưa tính chi phí vận hành, chi phí kiểm thử mới, hiệu quả của những công việc khác, mức độ chắc chắn của lợi ích hoặc giá trị tránh được sự cố. Với một rủi ro có tác động rất cao, lợi ích chính có thể là **giảm xác suất thiệt hại**, không phải tiết kiệm ngay vài giờ làm việc.

Không nên giả vờ tính được giá trị tiền tệ chính xác của mọi rủi ro nếu không có dữ liệu về xác suất và mức tác động. Có thể trình bày **khoảng ước lượng**, giả định và những yếu tố chưa biết, thay vì một điểm ROI giả chính xác.

## 12. Khi nào kết luận “đã giảm”, “có dấu hiệu” hay “chưa rõ”?

Một báo cáo trung thực cần phân biệt **mức độ bằng chứng**:

| Trạng thái đánh giá | Khi nào phù hợp | Ví dụ cách viết |
| --- | --- | --- |
| **Đã xác nhận cải tiến cấu trúc** | Có diff/review chứng minh trách nhiệm hoặc phụ thuộc được thay đổi | “Hai nơi tính phí độc lập đã được hợp nhất thành một chính sách.” |
| **Đã xác nhận hành vi trong phạm vi test** | Test và review phù hợp đã đạt | “Các ca biên STANDARD/EXPRESS đạt ở mức unit và các caller đã kiểm tra.” |
| **Có chỉ báo sớm giảm chi phí/rủi ro** | Số nơi phải sửa hoặc khả năng kiểm thử cải thiện, chưa có đủ dữ liệu dài hạn | “Thay đổi chính sách nay cần sửa một nơi; sẽ theo dõi PR cùng loại.” |
| **Đã quan sát chi phí/rủi ro giảm trong mẫu đo** | Có dữ liệu trước–sau cùng định nghĩa, số mẫu và điều kiện công bố | “Trung vị thời gian sửa giảm trong các PR cùng loại thuộc kỳ quan sát.” |
| **Chưa đủ bằng chứng** | Ít lần thay đổi, thiếu baseline, môi trường không so sánh được | “Chưa thể kết luận ảnh hưởng tới tỷ lệ hồi quy.” |
| **Không đạt hoặc phát sinh nợ mới** | Sau sửa có hồi quy, cấu trúc chung cản thay đổi hoặc chi phí tăng | “Bộ policy chung làm tăng phạm vi ảnh hưởng; cần điều chỉnh ranh giới.” |

**Không nên dùng một trạng thái “DONE” duy nhất cho cả tiến độ thực hiện và lợi ích đã kiểm chứng.** Một ticket có thể hoàn thành về mặt kỹ thuật trong khi phần theo dõi tác động vẫn đang mở với mốc và người phụ trách cụ thể.

## 13. Quy trình kiểm chứng sau khi xử lý nợ kỹ thuật

Một quy trình có thể áp dụng cho nhiều khoản nợ:

1. **Lập hồ sơ trước khi sửa.** Mô tả cơ chế gây nợ, những thay đổi/sự cố làm bằng chứng, phạm vi mã và tác động nghiệp vụ. Tránh chỉ viết “code rất xấu”.
2. **Chọn baseline và tiêu chí thành công.** Định nghĩa cùng cách đo, kỳ quan sát, mẫu số và giới hạn. Tách tiêu chí cấu trúc, hành vi và kết quả thực tế.
3. **Bảo vệ hành vi trước refactor.** Viết test đặc tả và kiểm thử hồi quy cho những đường quan trọng. Xác nhận đúng yêu cầu thay vì mặc định mã cũ là chuẩn.
4. **Sửa theo phạm vi có thể kiểm soát.** Refactor từng bước, giữ ranh giới API và tác dụng phụ; tách thay đổi chính sách có chủ đích khỏi thay đổi cấu trúc.
5. **Kiểm chứng ngay sau sửa.** Unit/integration tests, review cấu trúc, so sánh hành vi và test biên; ghi rõ phần chưa kiểm tra.
6. **Theo dõi thay đổi và sự cố sau đó.** Đo số lần sửa, thời gian, khả năng tái hiện lỗi, sự cố theo cơ hội xảy ra và hiệu năng theo những điều kiện đã định.
7. **Đánh giá yếu tố gây nhiễu.** Thay đổi nhân sự, tải, quy trình, công cụ, độ khó yêu cầu và cách báo lỗi có ảnh hưởng kết quả không?
8. **Kết luận theo mức bằng chứng.** Có thể xác nhận cấu trúc tốt hơn nhưng chưa kết luận chi phí dài hạn đã giảm. Nếu hiệu quả không đạt, điều chỉnh cách tổ chức hoặc giả thuyết.
9. **Lưu rủi ro còn lại và bài học.** Bổ sung vào ADR, ticket nợ, tài liệu thiết kế hoặc báo cáo đo, tùy cách dự án quản lý.

Khi code review, câu hỏi hữu ích là: **“Chúng ta đã loại bỏ cơ chế nào khiến thay đổi trở nên đắt đỏ hoặc dễ lỗi, và bằng chứng nào cho thấy điều đó không chỉ đúng trên sơ đồ?”**

## 14. Mẫu báo cáo kết quả có thể hành động

Một bản tổng kết ngắn có thể ghi:

| Mục | Nội dung minh họa |
| --- | --- |
| **Khoản nợ** | Hai nhánh tính phí giao hàng độc lập ở checkout và hóa đơn |
| **Vấn đề đã gặp** | Sửa chính sách phải động vào nhiều nơi; có nguy cơ kết quả lệch |
| **Giả thuyết** | Gom quy tắc sẽ giảm điểm phải sửa và rủi ro bỏ sót một luồng |
| **Thay đổi đã làm** | Tạo `DeliveryFeePolicy` và đưa hai caller dùng lại |
| **Bằng chứng cấu trúc** | Hai điểm cài đặt → một điểm; không còn hai hằng ngưỡng độc lập |
| **Bằng chứng hành vi** | Test tại 499.999/500.000/500.001 VND và EXPRESS; test cả hai caller |
| **Dữ liệu sau thay đổi** | Theo dõi thời gian, số file sửa và lỗi hồi quy ở các PR cùng loại |
| **Giới hạn** | Chưa có đủ thay đổi tương đương để kết luận tỷ lệ lỗi dài hạn |
| **Rủi ro còn lại** | Cùng một bug policy ảnh hưởng cả hai luồng; khác biệt nguồn subtotal |
| **Hành động tiếp theo** | Thêm integration test end-to-end và xem lại kết quả sau kỳ quan sát |

Không cần biến mỗi khoản nợ nhỏ thành một báo cáo lớn. Nhưng với khoản nợ ảnh hưởng **thanh toán, quyền truy cập, dữ liệu nhạy cảm hoặc khả dụng**, việc giữ bằng chứng, giả định và quyết định xử lý sẽ đặc biệt quan trọng.

## 15. Bài tập tình huống

Một nhóm vừa thay thế ba đoạn xử lý timeout trùng nhau bằng `RetryPolicy` dùng chung. Họ đưa ra báo cáo:

~~~text
Trước: 3 nơi có logic retry, 420 dòng, 12 bài kiểm thử.
Sau: 1 nơi có logic retry, 300 dòng, 20 bài kiểm thử.
Kết luận: Nợ kỹ thuật đã giảm 50%, hệ thống an toàn hơn.
~~~

Giả sử hệ thống gửi yêu cầu tạo giao dịch sang một đối tác. Có trường hợp **đối tác đã xử lý thành công nhưng phản hồi tới ứng dụng bị mất**.

**Câu hỏi A.** Báo cáo trên đã chứng minh được những điều gì? Điều gì chưa được chứng minh?

**Câu hỏi B.** Nêu một rủi ro quan trọng nếu gộp retry nhưng chưa xử lý idempotency.

**Câu hỏi C.** Hãy đề xuất những kiểm thử và bằng chứng vận hành phù hợp trước khi khẳng định rủi ro đã giảm.

**Câu hỏi D.** Sau một tháng không có sự cố được báo cáo, có thể khẳng định rủi ro trùng giao dịch bằng 0 không? Cần thêm dữ liệu nào?

**Câu hỏi E.** Hãy viết lại kết luận theo cách phân biệt kết quả cấu trúc, hành vi đã kiểm chứng và hiệu quả dài hạn còn phải theo dõi.

### Gợi ý đáp án

**A.** Báo cáo cho thấy **số vị trí chứa logic retry** và **số dòng mã** giảm, số bài test tăng. Nó **chưa đo** thời gian sửa đổi, độ phủ những đường lỗi quan trọng, số giao dịch trùng, tỷ lệ sự cố hoặc chi phí vận hành. Số test tăng không chứng minh test đã kiểm tra đúng rủi ro; không có cơ sở nói “nợ giảm 50%” chỉ từ số dòng.

**B.** Khi đối tác đã hoàn tất giao dịch nhưng client nhận timeout, retry có thể tạo **giao dịch lần thứ hai** nếu không có khóa nhận diện yêu cầu lặp lại hoặc cơ chế đối soát. Việc gom logic có thể khiến cùng một lỗi được áp dụng cho nhiều luồng hơn.

**C.** Cần review hợp đồng retry và idempotency; test đường thành công bình thường; test timeout trước khi đối tác xử lý; **test timeout sau khi đối tác đã xử lý**; test nhận lại cùng request ID; test giới hạn số lần retry, backoff và lỗi không được phép retry. Ở ranh giới tích hợp, cần xác minh không phát sinh hai giao dịch cho cùng yêu cầu logic, và quan sát số giao dịch lặp, timeout, retry thực tế theo mẫu số phù hợp.

**D.** Không. Có thể chưa có đủ giao dịch, chưa gặp đúng kiểu timeout hoặc không có cơ chế phát hiện giao dịch trùng. Cần số lượng request, số lần timeout/retry, dữ liệu đối soát, độ phủ giám sát, khoảng thời gian và môi trường triển khai. Ngay cả số ghi nhận bằng không vẫn có độ bất định.

**E.** Có thể báo cáo: “Đã hợp nhất logic retry từ ba vị trí còn một và bổ sung tám test. Các tình huống đã kiểm chứng được liệt kê theo phạm vi; hiện chưa đủ dữ liệu khẳng định nguy cơ giao dịch trùng hoặc chi phí thay đổi dài hạn đã giảm. Nhóm sẽ bổ sung test timeout sau thành công, đối soát giao dịch và theo dõi thay đổi cùng loại trong kỳ tiếp theo.” Đó là kết luận có cơ sở hơn một tỷ lệ “giảm nợ” không được định nghĩa.

## Ghi nhớ

**Xử lý nợ kỹ thuật là một khoản đầu tư nhằm giảm chi phí hoặc rủi ro của công việc về sau.** PR được merge, mã ít dòng hơn, complexity hay duplication giảm chỉ là **bằng chứng về thay đổi cấu trúc**. Để chứng minh lợi ích, cần kiểm tra **hành vi còn đúng**, xác nhận **cơ chế gây nợ đã bị loại bỏ**, rồi quan sát **chi phí và rủi ro ở những thay đổi hoặc hoạt động thực tế**.

Hãy đặt giả thuyết và baseline trước khi sửa, đo cùng định nghĩa, nêu mẫu số và yếu tố gây nhiễu, dùng kiểm thử/review phù hợp, đồng thời báo cáo rõ **điều đã xác nhận, điều mới là chỉ báo và điều chưa đủ bằng chứng**. Mục tiêu không phải làm bảng đo đẹp hơn, mà là khiến mã nguồn **đáng tin cậy hơn, dễ hiểu hơn và có thể thay đổi với ít chi phí và rủi ro hơn**.
