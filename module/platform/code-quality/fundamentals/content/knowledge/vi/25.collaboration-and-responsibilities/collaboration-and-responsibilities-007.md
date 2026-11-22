# Phản hồi dựa trên mã và tác động thay vì đánh giá con người

## 1. Mục tiêu bài học

Trong chương **Cộng tác và trách nhiệm** của module **CODE_QUALITY_FUNDAMENTALS**, chúng ta tìm hiểu cách đưa ra phản hồi kỹ thuật trong code review và trao đổi nhóm sao cho người nhận hiểu rõ vấn đề, tác động và bước xử lý tiếp theo. Trọng tâm là **đánh giá bằng chứng trong mã và hệ quả của thay đổi**, không gán nhãn năng lực, tính cách hoặc động cơ của người viết.

Module hướng đến việc **hiểu những thuộc tính quyết định mã nguồn có đáng tin cậy, dễ hiểu và dễ thay đổi hay không**. Chất lượng phần mềm là trách nhiệm chung: một lỗi có thể xuất phát từ yêu cầu chưa rõ, API khó dùng, thiếu kiểm thử, công cụ không phát hiện hoặc áp lực tiến độ. Phản hồi có ích giúp nhóm cải thiện cả mã lẫn cách làm việc.

Sau bài học, bạn có thể:

- Phân biệt **nhận xét về hành vi của mã** với **đánh giá con người viết mã**.
- Viết phản hồi nêu rõ vị trí, bằng chứng, tác động và hành động đề xuất.
- Chọn cách diễn đạt phù hợp cho vấn đề bắt buộc sửa, đề xuất cải thiện và câu hỏi cần làm rõ.
- Thảo luận bất đồng kỹ thuật dựa trên hợp đồng, ví dụ và rủi ro có thể kiểm chứng.
- Phản hồi khi nhận review mà không biến trao đổi thành tranh luận cá nhân.
- Xây dựng thói quen xem lỗi và nợ kỹ thuật là cơ hội cải thiện hệ thống, quy trình và công cụ của cả nhóm.

## 2. Vì sao phản hồi nên tập trung vào mã và tác động?

Một nhận xét như:

> “Bạn viết code cẩu thả quá. Sao lại mắc lỗi cơ bản này?”

không cho người nhận biết chính xác điều gì sai, điều kiện nào làm lỗi xuất hiện hoặc cần sửa thế nào. Nó còn chuyển cuộc trao đổi từ **vấn đề kỹ thuật có thể kiểm tra** sang **đánh giá cá nhân khó phản hồi**.

Ngược lại:

> “Khi quantity bằng 0, phép tính vẫn trả về một dòng hàng có tổng bằng 0. Hợp đồng của endpoint yêu cầu số lượng dương. Có thể xác thực đầu vào trước khi tính và thêm test cho trường hợp này không?”

Nhận xét thứ hai chỉ ra:

- **Điều quan sát được:** đầu vào bằng 0 vẫn được xử lý.
- **Chuẩn để đối chiếu:** hợp đồng yêu cầu số lượng dương.
- **Tác động:** hệ thống có thể tạo dòng hàng không hợp lệ.
- **Hành động:** xác thực đầu vào và bổ sung kiểm thử.

Người viết có thể xác minh hoặc cung cấp thêm bối cảnh mà không cần bảo vệ danh dự. Reviewer cũng có thể thay đổi nhận định nếu hợp đồng thực tế khác điều mình nghĩ.

### Tác động đến chất lượng và cộng tác

Phản hồi tập trung vào bằng chứng giúp:

1. **Tìm đúng nguyên nhân:** nhóm sửa điều kiện, hợp đồng hoặc thiết kế thay vì chỉ sửa biểu hiện.
2. **Giảm hiểu lầm:** người viết biết reviewer đang lo về hành vi nào và vì sao.
3. **Giữ khả năng học hỏi:** người mới có thể hỏi lại và hiểu nguyên tắc kỹ thuật mà không bị gắn nhãn.
4. **Tạo lịch sử quyết định tốt:** comment trong PR có thể giải thích vì sao nhóm chọn một giải pháp.
5. **Chia sẻ trách nhiệm:** vấn đề được xem xét trong bối cảnh hệ thống, yêu cầu, test và quy trình.

Điều này không có nghĩa phải làm nhẹ mọi nhận xét. Nếu một thay đổi có nguy cơ mất dữ liệu, lộ thông tin hoặc thu tiền sai, cần nói rõ mức độ nghiêm trọng và yêu cầu xử lý. **Tôn trọng người nhận không đồng nghĩa giảm độ chính xác hoặc né tránh vấn đề.**

## 3. Một cấu trúc phản hồi có thể hành động

Một nhận xét kỹ thuật tốt thường có bốn phần:

1. **Vị trí hoặc hành vi:** đoạn code, điều kiện, luồng dữ liệu hoặc kết quả đang được nói đến.
2. **Bằng chứng và điều kiện:** ví dụ đầu vào, đường thực thi, hợp đồng hoặc kết quả test.
3. **Tác động:** điều gì có thể xảy ra với người dùng, dữ liệu, bảo mật, vận hành hoặc khả năng bảo trì?
4. **Yêu cầu hoặc hướng xử lý:** cần sửa, cần làm rõ hay chỉ là đề xuất?

Có thể dùng cấu trúc ngắn:

> **Khi [điều kiện], đoạn [hành vi] dẫn đến [tác động] vì [bằng chứng/hợp đồng]. Có thể [hành động cụ thể] không?**

Không phải comment nào cũng cần đủ bốn câu. Với một lỗi hiển nhiên, một câu có thể đủ. Với một quyết định kiến trúc phức tạp, cần thêm giả định, phương án và đánh đổi.

### Ví dụ chuyển từ đánh giá cá nhân sang phản hồi kỹ thuật

| Cách nói không hữu ích | Cách nói dựa trên mã và tác động |
| --- | --- |
| “Bạn không hiểu transaction à?” | “Nếu lưu đơn thất bại sau khi giữ tồn kho, số lượng có thể bị giữ dù đơn chưa tồn tại. Luồng này có transaction hoặc cơ chế hoàn tác bao phủ cả hai thao tác không?” |
| “Code này quá rối.” | “Phương thức đang xác thực request, tính phí và gửi email trong cùng một luồng. Khi chính sách phí đổi, phần gửi email cũng phải sửa hoặc test lại. Có thể tách phần tính phí khỏi bước thông báo không?” |
| “Bạn luôn quên test.” | “PR chưa có test cho trường hợp SKU không tồn tại. Khi catalog trả lỗi, endpoint cần phản hồi thế nào? Có thể thêm test cho hợp đồng lỗi này không?” |
| “Cách dùng API này ngớ ngẩn.” | “Map.copyOf không cam kết thứ tự duyệt. Caller có yêu cầu thứ tự SKU không? Nếu có, kiểu trả về nên thể hiện rõ hợp đồng có thứ tự.” |
| “Đừng làm như vậy nữa.” | “Cách gọi adapter trực tiếp khiến application phụ thuộc vào JDBC. Dự án đang giữ hướng phụ thuộc qua port; có thể đưa interface đọc dữ liệu vào hợp đồng application không?” |

Nhận xét tốt không cần tránh từ ngữ kỹ thuật. Điều quan trọng là **mô tả vấn đề kiểm chứng được**, thay vì dùng thuật ngữ như nhãn đánh giá người viết.

## 4. Phân biệt quan sát, suy luận và giả định

Trong trao đổi kỹ thuật, ba loại phát biểu dễ bị trộn lẫn:

- **Quan sát:** điều trực tiếp thấy trong diff, log, test hoặc cấu hình.
- **Suy luận:** kết luận có thể rút ra từ quan sát và một số giả định.
- **Giả định:** điều chưa được xác nhận nhưng đang dùng để phân tích.

Ví dụ:

| Phát biểu | Loại | Cách sử dụng |
| --- | --- | --- |
| findBySku có thể trả Optional.empty(). | Quan sát hợp đồng trong chữ ký/implementation | Có thể dẫn tới nhánh xử lý cần kiểm tra. |
| Nếu caller không xử lý empty, request có thể thất bại hoặc trả kết quả sai. | Suy luận | Nêu tác động và chỉ ra đường gọi cần xác minh. |
| SKU không tồn tại có thể xảy ra trong dữ liệu production. | Giả định nếu chưa có số liệu | Hỏi hoặc dẫn nguồn dữ liệu trước khi coi là chắc chắn. |
| Test hiện tại chỉ bao phủ SKU tồn tại. | Quan sát từ test | Có thể đề nghị bổ sung ca thiếu SKU. |

Một phản hồi đáng tin nên thể hiện mức chắc chắn:

- **Chắc chắn:** “Ở nhánh này, phép chia dùng số nguyên nên phần thập phân bị bỏ.”
- **Có điều kiện:** “Nếu customer có thể vắng mặt theo hợp đồng API, lời gọi này có thể ném NullPointerException.”
- **Cần xác nhận:** “Mình chưa thấy quy tắc khi hai dòng có cùng SKU. Hệ thống muốn cộng dồn hay từ chối?”

Khi chưa biết đủ, đặt câu hỏi cụ thể. Không cần giả vờ chắc chắn để comment có vẻ mạnh mẽ.

## 5. Ví dụ Java 17: góp ý về điều kiện biên của phép tính tiền

Giả sử một PR bổ sung hàm tính giá sau giảm hội viên. Hợp đồng đã xác nhận:

- unitPriceVnd là giá đơn vị, tính bằng VND nguyên và không âm.
- Nếu là hội viên, giảm 10.000 VND nhưng **không giảm quá giá gốc**.
- Nếu không phải hội viên, giữ nguyên giá.
- Số tiền trả về không âm.

### 5.1. Đoạn mã có vấn đề

```java
public final class MemberPricing {
    private MemberPricing() {}

    public static long finalPriceVnd(
            long unitPriceVnd, boolean member) {
        if (!member) {
            return unitPriceVnd;
        }
        return unitPriceVnd - 10_000L;
    }
}
```

Với giá 5.000 VND và khách là hội viên, hàm trả về **-5.000 VND**. Lỗi nằm ở điều kiện áp dụng giảm giá, không nằm ở năng lực hay thái độ của người viết.

### 5.2. Comment review có ích

> “Với unitPriceVnd = 5_000 và member = true, hàm trả -5_000, trong khi hợp đồng yêu cầu giá cuối không âm và mức giảm không vượt giá gốc. Có thể giới hạn mức giảm ở min(unitPriceVnd, 10_000) và thêm test cho giá 0/5.000/10.000 không?”

Comment này cung cấp đầu vào tái hiện, chỉ ra hợp đồng bị vi phạm và đề xuất bước sửa có thể kiểm chứng. Người viết có thể trả lời bằng test hoặc làm rõ nếu hợp đồng được hiểu khác.

### 5.3. Một cách sửa phù hợp

```java
public final class MemberPricing {
    private static final long MEMBER_DISCOUNT_VND = 10_000L;

    private MemberPricing() {}

    public static long finalPriceVnd(
            long unitPriceVnd, boolean member) {
        if (unitPriceVnd < 0) {
            throw new IllegalArgumentException(
                    "unitPriceVnd must not be negative");
        }
        if (!member) {
            return unitPriceVnd;
        }
        long discountVnd = Math.min(
                unitPriceVnd, MEMBER_DISCOUNT_VND);
        return unitPriceVnd - discountVnd;
    }
}
```

### 5.4. Kiểm thử JUnit 5 cho hợp đồng

```java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import org.junit.jupiter.api.Test;

class MemberPricingTest {
    @Test
    void keepsRegularCustomerPriceUnchanged() {
        assertEquals(15_000L,
                MemberPricing.finalPriceVnd(15_000L, false));
    }

    @Test
    void appliesDiscountWithoutMakingPriceNegative() {
        assertEquals(0L,
                MemberPricing.finalPriceVnd(0L, true));
        assertEquals(0L,
                MemberPricing.finalPriceVnd(5_000L, true));
        assertEquals(0L,
                MemberPricing.finalPriceVnd(10_000L, true));
        assertEquals(5_000L,
                MemberPricing.finalPriceVnd(15_000L, true));
    }

    @Test
    void rejectsNegativeUnitPrice() {
        assertThrows(IllegalArgumentException.class,
                () -> MemberPricing.finalPriceVnd(-1L, true));
    }
}
```

Khi review, không cần yêu cầu người viết dùng đúng Math.min nếu có cách khác giữ cùng hợp đồng và dễ hiểu. Reviewer đánh giá **bảo đảm và bằng chứng**, không bắt buộc một cách hiện thực duy nhất khi nhiều cách đều phù hợp.

## 6. Phân loại phản hồi theo mức độ và mục đích

Không phải mọi nhận xét đều có cùng trọng lượng. Nếu mọi góp ý đều được diễn đạt như blocker, người viết khó biết điều gì thật sự ngăn việc merge. Nếu mọi vấn đề đều chỉ là “gợi ý”, rủi ro nghiêm trọng có thể bị bỏ qua.

Một nhóm có thể thống nhất cách phân loại như sau:

| Mức | Khi nào dùng | Cách diễn đạt gợi ý |
| --- | --- | --- |
| **Blocker / Must fix** | Vi phạm hợp đồng, lỗi dữ liệu, lỗ hổng bảo mật, tác dụng phụ ngoài ý muốn hoặc lỗi làm chức năng không dùng được | “Cần xử lý trước khi merge vì…” |
| **Should fix** | Có rủi ro đáng kể về bảo trì, độ tin cậy hoặc thiếu bằng chứng ở đường quan trọng | “Nên sửa trong PR này vì…” |
| **Question / Clarification** | Thiếu thông tin để kết luận, hợp đồng hoặc giả định chưa rõ | “Mình muốn xác nhận…” |
| **Suggestion / Nit** | Cải thiện nhỏ, không ảnh hưởng đáng kể tới tính đúng đắn | “Một lựa chọn khác là…; không chặn nếu nhóm muốn giữ cách hiện tại.” |

Tên nhãn và mức ưu tiên có thể khác nhau giữa các nhóm. Điều quan trọng là mọi người **hiểu cùng một ý nghĩa** và reviewer không dùng nhãn nghiêm trọng để nhấn mạnh sở thích cá nhân.

### Một comment cần có điều kiện kết thúc

Nhận xét như “cần làm tốt hơn” không cho biết khi nào đã giải quyết. Hãy chỉ rõ bằng chứng cần có:

- “Thêm test chứng minh giá 5.000 VND sau giảm không âm.”
- “Bổ sung kiểm tra để application không import package adapter.”
- “Xác nhận transaction rollback khi lưu thất bại.”
- “Cập nhật tài liệu API về mã lỗi SKU không tồn tại.”

Khi điều kiện hoàn tất rõ, tác giả có thể sửa và reviewer có thể xác nhận mà không phải đoán kỳ vọng.

## 7. Đặt câu hỏi thay vì áp đặt khi ngữ cảnh chưa đầy đủ

Không phải lúc nào reviewer cũng biết toàn bộ quyết định đã được thống nhất. Khi thiếu bối cảnh, một câu hỏi tốt có thể mở ra thông tin quan trọng:

- “Hợp đồng có cho phép customer vắng mặt không? Nếu có, nhánh này đang xử lý trường hợp đó ở đâu?”
- “Giá được đọc tại thời điểm preview hay được khóa khi tạo đơn? Có thể thay đổi giữa hai bước không?”
- “Vì sao adapter này được đặt trong module application? Có ràng buộc triển khai nào khiến nó phải nằm ở đây?”
- “Test này đang xác nhận yêu cầu mới hay ghi lại hành vi cũ? Có ticket/đặc tả để đối chiếu không?”

Một câu hỏi tốt **nêu rõ điều chưa biết**. Tránh câu hỏi mang tính kết tội như:

- “Bạn có đọc yêu cầu không?”
- “Sao lại nghĩ cách này đúng?”
- “Bạn có hiểu transaction là gì không?”

Nếu cần yêu cầu thay đổi rõ ràng, hãy nói thẳng và nêu lý do. Không cần biến mọi comment thành câu hỏi lịch sự đến mức người viết không biết đó là yêu cầu bắt buộc.

## 8. Bất đồng kỹ thuật: tranh luận về bằng chứng và đánh đổi

Hai kỹ sư có thể hiểu cùng yêu cầu nhưng chọn thiết kế khác nhau. Ví dụ:

- Người A muốn dùng cache để giảm độ trễ.
- Người B muốn đọc database trực tiếp để giảm cơ chế đồng bộ và dữ liệu cũ.

Trao đổi có ích cần làm rõ:

1. **Mục tiêu:** độ trễ, tính nhất quán, chi phí vận hành hay khả năng đơn giản?
2. **Ràng buộc:** dữ liệu được phép cũ bao lâu, tải dự kiến, số instance, khả năng chịu lỗi?
3. **Bằng chứng:** benchmark, số liệu production, test tích hợp hay mới chỉ là giả định?
4. **Đánh đổi:** phương án nào làm tăng độ phức tạp, rủi ro hoặc chi phí ở đâu?
5. **Điều kiện xem xét lại:** số liệu hoặc thay đổi yêu cầu nào sẽ khiến nhóm đổi lựa chọn?

Ví dụ comment:

> “Cache có thể giảm lượt đọc lặp, nhưng mình chưa thấy cách invalidation khi mô tả sản phẩm được cập nhật. Nếu yêu cầu là đọc thấy nội dung mới trong thời gian ngắn, ta cần xác định giới hạn stale data trước khi chọn TTL. Có số liệu tải hoặc yêu cầu freshness nào để so sánh hai phương án không?”

Đây là một phản hồi có lập luận, không gán cho người đề xuất cache là “không hiểu consistency”.

### Khi nào nên chuyển bất đồng thành quyết định thiết kế?

Nếu lựa chọn có tác động lâu dài tới nhiều module, public API, dữ liệu hoặc vận hành, cuộc thảo luận có thể cần một bản ghi quyết định:

- Bối cảnh và yêu cầu.
- Các phương án đã cân nhắc.
- Bằng chứng và giả định.
- Phương án được chọn cùng lý do.
- Hệ quả và điều kiện xem xét lại.

Khi đó, code review tập trung xác nhận PR **thực hiện đúng quyết định đã thống nhất**, thay vì lặp lại toàn bộ tranh luận ở từng dòng.

## 9. Người nhận review cũng có trách nhiệm trong cuộc trao đổi

Phản hồi là hoạt động hai chiều. Khi nhận comment, người viết có thể:

1. **Đọc để hiểu vấn đề trước khi phản hồi.** Xác định comment đang nói về hành vi, hợp đồng hay sở thích.
2. **Yêu cầu ví dụ khi chưa rõ.** “Bạn có thể chỉ đầu vào làm kết quả sai không?” là câu hỏi hợp tác.
3. **Trả lời bằng bằng chứng.** Dẫn test, đặc tả, log hoặc quyết định đã có thay vì chỉ nói “code vẫn chạy”.
4. **Chấp nhận và sửa khi nhận định đúng.** Ghi ngắn gọn thay đổi và test đã bổ sung.
5. **Giải thích khi không đồng ý.** Nêu bối cảnh, đánh đổi và bằng chứng; tránh suy diễn động cơ của reviewer.
6. **Thống nhất cách kết thúc comment.** Đánh dấu resolved khi đã sửa hoặc có quyết định được chấp nhận; không chỉ đóng để làm sạch giao diện.

Ví dụ trả lời:

**Khi đồng ý:**

> “Đúng, với giá thấp hơn mức giảm, kết quả có thể âm. Mình đã giới hạn mức giảm theo giá gốc và thêm test cho giá 0, 5.000 và 10.000 VND.”

**Khi cần làm rõ:**

> “Mình hiểu rủi ro bạn nêu. Endpoint hiện được gọi sau bước xác thực SKU, nhưng mình chưa thấy điều đó được bảo vệ ở tầng service. Mình sẽ thêm validation tại ranh giới này để use case không phụ thuộc vào controller.”

**Khi không đồng ý:**

> “Mình giữ LinkedHashMap vì hợp đồng file xuất yêu cầu giữ thứ tự dòng đầu tiên. Test exportPreservesFirstSeenOrder đang kiểm tra điều đó. Nếu nhóm muốn thay đổi hợp đồng thứ tự, mình nghĩ nên cập nhật API và test riêng.”

Không cần đồng ý với mọi comment. Điều cần thiết là **phản hồi vào luận điểm và bằng chứng**, đồng thời sẵn sàng điều chỉnh khi có thông tin mới.

## 10. Phân biệt vấn đề cá nhân với vấn đề của hệ thống

Khi lỗi lặp lại, cách phản ứng chỉ nhắc “hãy cẩn thận hơn” thường không đủ. Nhóm nên hỏi:

- Yêu cầu có rõ và dễ tìm không?
- API có dễ sử dụng sai không?
- Test có bao phủ trường hợp quan trọng không?
- CI có chạy đúng rule và đúng source set không?
- Review có đủ thời gian và đúng người có bối cảnh không?
- Quy trình phát hành có khuyến khích bỏ qua kiểm tra không?
- Có quá nhiều trách nhiệm hoặc phụ thuộc khiến một người khó hiểu toàn bộ thay đổi không?

Ví dụ, nếu nhiều PR liên tục quên kiểm tra tràn số trong tính tiền, nhóm có thể:

- Tạo kiểu tiền hoặc hàm tính toán an toàn dùng chung.
- Thêm rule static analysis phù hợp.
- Bổ sung test mẫu cho biên số học.
- Cải thiện checklist review phần thanh toán.
- Đưa ví dụ vào hướng dẫn nội bộ.

Mục tiêu là **giảm khả năng lỗi lặp lại**, không chỉ yêu cầu từng người nhớ thêm một điều.

### Không dùng “trách nhiệm chung” để xóa trách nhiệm cụ thể

Chia sẻ trách nhiệm không có nghĩa không ai chịu trách nhiệm. Một issue vẫn cần người xử lý, người review và người quyết định khi có bất đồng. Nhưng việc giao owner không đồng nghĩa quy lỗi cá nhân cho người tạo ra tình huống.

Có thể nói:

> “Nhóm thanh toán sẽ bổ sung kiểm tra tràn số vào API tiền tệ và thêm test dùng chung. PR hiện tại cần áp dụng kiểm tra đó trước khi merge.”

Câu này có **owner và hành động cụ thể**, đồng thời xử lý nguyên nhân lặp lại ở cấp hệ thống.

## 11. Những phản hồi nên tránh và cách viết lại

| Tránh dùng | Vì sao không hữu ích | Viết lại theo hướng có thể kiểm chứng |
| --- | --- | --- |
| “Code ngu quá.” | Xúc phạm, không chỉ ra lỗi | “Với quantity = 0, hàm vẫn tạo dòng hàng; hợp đồng yêu cầu số lượng dương.” |
| “Bạn lúc nào cũng quên xử lý null.” | Khái quát con người và lịch sử | “Nhánh này chưa xử lý trường hợp customer vắng mặt; hợp đồng có cho phép trạng thái đó không?” |
| “Làm đúng chuẩn clean code đi.” | Không nêu chuẩn cụ thể | “Phương thức đang vừa truy vấn database vừa tính phí. Có thể tách truy vấn qua port và giữ phép tính trong policy không?” |
| “Cái này hiển nhiên mà.” | Không giúp học hoặc xác minh | “Điều kiện > bỏ sót đúng ngưỡng 500.000; test hiện có chỉ kiểm tra 499.999.” |
| “Không thích cách này.” | Chỉ nêu sở thích | “Cách này tạo thêm một phụ thuộc runtime. Mình chưa thấy lợi ích thay thế; có thể giải thích nhu cầu của abstraction này không?” |
| “Đã bảo sửa rồi mà.” | Tạo xung đột, không nhắc lại yêu cầu cụ thể | “Vấn đề về rollback vẫn còn ở nhánh lưu thất bại. Cần có test chứng minh reservation được hoàn tác trước khi đóng comment.” |
| “Tác giả phải chịu trách nhiệm.” | Cá nhân hóa lỗi và bỏ qua bối cảnh | “PR này cần owner của luồng đơn hàng xác nhận thứ tự commit và phát sự kiện.” |

### Tránh ngôn ngữ tuyệt đối khi chưa có đủ dữ liệu

Các từ như **“luôn luôn”**, **“không bao giờ”**, **“rõ ràng”**, **“ai cũng biết”** dễ làm nhận xét trở nên khó kiểm chứng. Thay bằng điều kiện cụ thể:

- “Trong test này…”
- “Với request có trường…”
- “Nếu endpoint được gọi đồng thời…”
- “Theo hợp đồng API hiện tại…”
- “Trong cấu hình module đang dùng…”

Điều đó làm nhận xét chính xác hơn và mở đường cho người khác bổ sung bằng chứng.

## 12. Cách xử lý khi comment bị hiểu khác ý

Văn bản ngắn trong PR thiếu giọng nói và ngữ cảnh. Một câu hỏi có thể bị đọc thành mệnh lệnh; một đề xuất có thể bị hiểu là blocker.

Khi nhận thấy hiểu lầm:

1. **Nhắc lại ý định kỹ thuật:** “Mình đang lo về khả năng gửi message trước commit.”
2. **Nêu tác động cụ thể:** “Nếu transaction rollback, consumer có thể nhận sự kiện cho đơn không tồn tại.”
3. **Làm rõ mức độ:** “Đây là điều kiện cần xử lý trước merge vì có thể làm sai dữ liệu.”
4. **Mời bổ sung bối cảnh:** “Nếu có cơ chế outbox hoặc transaction bao phủ, bạn có thể dẫn tới phần cấu hình đó không?”
5. **Chuyển kênh khi cần:** nếu trao đổi kéo dài hoặc có nhiều giả định, gọi một cuộc trao đổi ngắn rồi ghi quyết định lại trong PR.

Không nên để một cuộc tranh luận cá nhân kéo dài qua nhiều comment. Khi đã thống nhất giải pháp, hãy ghi lại **quyết định, người phụ trách và điều kiện hoàn tất** để người đọc sau hiểu được kết quả.

## 13. Review có chất lượng là trách nhiệm của cả nhóm

Một nhóm có thể thống nhất một số thực hành:

- **Tác giả cung cấp bối cảnh:** mục tiêu PR, phạm vi, rủi ro và test đã chạy.
- **Reviewer kiểm tra có trọng tâm:** bắt đầu từ hợp đồng và thiết kế, sau đó đi vào hiện thực.
- **Cả hai phân biệt sự thật và giả định:** khi thiếu thông tin, đặt câu hỏi và dẫn nguồn.
- **Nhóm thống nhất ngôn ngữ mức độ:** blocker, should-fix, question và suggestion có nghĩa nhất quán.
- **Người có quyền quyết định được xác định:** bất đồng về nghiệp vụ, bảo mật hoặc kiến trúc cần owner phù hợp.
- **Lỗi được chuyển thành cải tiến:** thêm test, rule, tài liệu hoặc cải thiện quy trình khi có thể.
- **Lịch sử review có thể đọc lại:** quyết định quan trọng được ghi rõ, không chỉ nằm trong trao đổi miệng.

### Đánh giá review bằng kết quả, không bằng số comment

Một reviewer viết 30 comment về format không nhất thiết tạo ra review tốt hơn người viết 3 comment về lỗi giao dịch và hợp đồng. Một tác giả sửa hết comment cũng chưa chắc hiểu được vấn đề nếu không có trao đổi.

Những tín hiệu có ích hơn:

- Lỗi có tác động lớn được phát hiện trước khi phát hành.
- Nhận xét gắn với bằng chứng và có thể hoàn tất.
- Thời gian xử lý comment hợp lý, không tạo vòng lặp tranh luận không cần thiết.
- Các vấn đề lặp lại được xử lý ở cấp hệ thống.
- Người mới hiểu thêm về codebase và quy tắc nhóm.
- Quyết định kiến trúc quan trọng được lưu lại.

Không nên biến các tín hiệu này thành bảng xếp hạng cá nhân. Mục tiêu là cải thiện cách cộng tác và chất lượng sản phẩm.

## 14. Bài tập áp dụng

### Bài tập 1 — viết lại một comment

Một reviewer viết:

> “Bạn chẳng kiểm tra gì cả. Hàm này rất nguy hiểm.”

Trong code, phép chia có thể nhận quantity = 0, và test chỉ kiểm tra quantity = 1.

**Yêu cầu:** Viết lại comment bằng cách nêu điều kiện, tác động, hợp đồng và hành động đề xuất.

**Gợi ý:**

> “Khi quantity = 0, phép chia này có thể ném ArithmeticException; test hiện tại chỉ kiểm tra giá trị 1. Hợp đồng có yêu cầu số lượng dương không? Nếu có, nên từ chối đầu vào tại ranh giới và thêm test cho 0.”

### Bài tập 2 — phân biệt blocker và suggestion

Một PR có hai vấn đề:

- A: nhánh lỗi vẫn trả HTTP 200 với nội dung thành công dù database rollback.
- B: tên biến tmp có thể đổi thành subtotalVnd.

**Câu hỏi:** Vấn đề nào cần chặn trước merge? Vì sao?

**Gợi ý:** A có thể làm caller tin thao tác thành công dù dữ liệu chưa được lưu; cần xử lý theo hợp đồng API. B là cải thiện khả năng đọc, có thể là suggestion nếu không vi phạm quy ước bắt buộc.

### Bài tập 3 — trả lời khi không đồng ý

Reviewer yêu cầu thay LinkedHashMap bằng HashMap. Tác giả biết endpoint xuất file cần giữ thứ tự SKU theo lần xuất hiện đầu tiên.

**Yêu cầu:** Viết phản hồi có bằng chứng thay vì trả lời “mình thích LinkedHashMap hơn”.

**Gợi ý:**

> “Endpoint xuất file đang cam kết giữ thứ tự xuất hiện đầu tiên của SKU. HashMap không bảo đảm thứ tự đó; test exportPreservesFirstSeenOrder đang xác nhận hợp đồng. Mình đề xuất giữ LinkedHashMap, hoặc nếu muốn đổi hợp đồng thứ tự thì cần cập nhật API và test riêng.”

### Bài tập 4 — biến lỗi cá nhân thành cải tiến hệ thống

Trong ba PR liên tiếp, nhóm phát hiện lỗi do phép nhân tiền tệ bị tràn long.

**Câu hỏi:** Ngoài nhắc từng tác giả cẩn thận, nhóm có thể thay đổi điều gì để giảm lỗi tái diễn?

**Gợi ý:** Xem xét kiểu tiền/hàm tính toán dùng chung, rule phân tích tĩnh phù hợp, test biên trong template, checklist review và tài liệu cho luồng tính tiền. Giao owner cho việc cải tiến và xác minh hiệu quả.

### Bài tập 5 — comment thiếu bối cảnh

Một reviewer ghi “Không nên dùng cache”. Tác giả không biết đây là yêu cầu bắt buộc hay ý kiến cá nhân.

**Câu hỏi:** Reviewer nên làm rõ điều gì?

**Gợi ý:** Nêu yêu cầu freshness, tải, dữ liệu stale có thể gây tác động gì, bằng chứng hoặc giả định hiện có và mức độ của nhận xét. Nếu chưa có quyết định, chuyển thành câu hỏi so sánh phương án và ghi lại quyết định khi nhóm thống nhất.

## 15. Checklist trước khi gửi phản hồi

- **Đang nói về code hay đánh giá người viết?** Bỏ các nhãn như cẩu thả, yếu kém, thiếu hiểu biết.
- **Có vị trí và điều kiện tái hiện không?** Nêu nhánh, đầu vào hoặc đường gọi cụ thể.
- **Có hợp đồng hoặc quy tắc làm căn cứ không?** Tránh chỉ dùng sở thích cá nhân.
- **Tác động có được giải thích không?** Người dùng, dữ liệu, bảo mật, vận hành hay bảo trì bị ảnh hưởng thế nào?
- **Yêu cầu có hành động được không?** Sửa, bổ sung test, làm rõ hợp đồng hay cung cấp bằng chứng?
- **Mức độ có phù hợp không?** Blocker chỉ dành cho vấn đề thực sự cần chặn.
- **Mức chắc chắn có trung thực không?** Phân biệt quan sát, suy luận và giả định.
- **Có để chỗ cho bối cảnh mới không?** Đặt câu hỏi khi thông tin chưa đủ.
- **Có thể giải thích bằng ví dụ hoặc test không?** Bằng chứng thường rõ hơn khẳng định chung.
- **Nếu vấn đề lặp lại, có cách cải thiện hệ thống không?** Tránh chỉ nhắc cá nhân cẩn thận hơn.

## 16. Ghi nhớ

**Phản hồi dựa trên mã và tác động thay vì đánh giá con người** giúp code review trở thành một hoạt động giải quyết vấn đề chung. Hãy mô tả điều quan sát được, đối chiếu với hợp đồng, giải thích hệ quả và nêu bước tiếp theo có thể kiểm chứng. Phân biệt yêu cầu bắt buộc với đề xuất, nói rõ mức chắc chắn và thảo luận bất đồng bằng bằng chứng cùng đánh đổi. Khi lỗi lặp lại, nhóm cần cải thiện API, test, công cụ hoặc quy trình bên cạnh việc giao người xử lý. Cách cộng tác này giúp mọi người **giữ tiêu chuẩn kỹ thuật cao, học hỏi từ nhau và cùng chịu trách nhiệm về chất lượng mã nguồn**.
