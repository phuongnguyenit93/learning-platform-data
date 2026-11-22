# Phân biệt lỗi cần sửa, đề xuất cải thiện và sở thích

Một người review nhìn thấy điều kiện tính phí sai ở đúng ngưỡng miễn phí giao hàng. Người khác muốn đổi tên một biến cho dễ hiểu. Người thứ ba thích dùng câu lệnh if thay cho toán tử điều kiện. Nếu cả ba ý kiến đều được viết thành “phải sửa trước khi merge”, pull request sẽ bị kéo dài và nhóm khó nhận ra điều gì thực sự quan trọng.

Trong module **CODE_QUALITY_FUNDAMENTALS**, mục tiêu là hiểu những yếu tố làm mã nguồn **đáng tin cậy, dễ hiểu và dễ thay đổi**. Ở chương **Rà soát mã**, code review giúp nhóm kiểm chứng tính đúng đắn, hợp đồng, bảo mật, khả năng bảo trì và mức rủi ro của thay đổi. Muốn review hiệu quả, phải phân biệt được:

1. **Lỗi cần sửa:** Có bằng chứng rằng mã không đáp ứng một yêu cầu hoặc tạo rủi ro không chấp nhận được.
2. **Đề xuất cải thiện:** Có cách làm có thể khiến mã rõ ràng, dễ sửa hoặc vận hành tốt hơn, nhưng chưa chứng minh là điều kiện bắt buộc để thay đổi hiện tại an toàn.
3. **Sở thích:** Một cách viết cá nhân trong nhiều phương án đều phù hợp với hợp đồng và quy ước đã thống nhất.

Bài này hướng dẫn cách phân loại nhận xét, viết phản hồi có bằng chứng, xử lý bất đồng và giữ cho review tập trung vào rủi ro thay vì tranh luận phong cách.

## 1. Code review không phải cuộc thi tìm nhiều lỗi nhất

Một code review tốt không nhất thiết tạo ra nhiều comment. Kết quả cần đạt là **mức tin cậy cao hơn rằng thay đổi đúng mục đích, không gây hồi quy nghiêm trọng và còn dễ duy trì**.

Các mục tiêu thường gặp:

- **Tính đúng đắn:** Đầu vào và trạng thái có dẫn đến kết quả được yêu cầu không?
- **Độ tin cậy:** Các đường lỗi, timeout, null, retry và tác dụng phụ có được xử lý đúng không?
- **Bảo mật:** Kiểm soát quyền, dữ liệu nhạy cảm và ranh giới tin cậy có bị vi phạm không?
- **Hợp đồng:** API, schema, mã lỗi, tương thích hoặc hành vi của caller có bị đổi ngoài ý muốn không?
- **Khả năng thay đổi:** Mã có trách nhiệm rõ, phụ thuộc hợp lý và không tạo chi phí bảo trì không cần thiết không?
- **Bằng chứng kiểm thử:** Test có kiểm tra tình huống quan trọng với kết quả kỳ vọng đáng tin không?
- **Vận hành:** Tài nguyên, hiệu năng, khả năng quan sát và quy trình triển khai có được cân nhắc theo mức rủi ro không?

Code review còn có giá trị chia sẻ hiểu biết giữa các thành viên. Nhưng điều đó không có nghĩa mọi sự khác biệt về cách viết đều nên trở thành yêu cầu chỉnh sửa.

**Một comment tốt cần trả lời được ít nhất hai câu hỏi:** “Vấn đề hoặc cơ hội nằm ở đâu?” và “Vì sao người nhận nên quan tâm?”

## 2. Ba nhóm nhận xét và mức độ bắt buộc

| Nhóm | Bản chất | Ví dụ | Cách diễn đạt phù hợp |
| --- | --- | --- | --- |
| **Lỗi cần sửa** | Vi phạm yêu cầu, rủi ro đã được chứng minh hoặc thiếu điều kiện quan trọng để an toàn. | Dùng > thay vì >= tại ngưỡng; bỏ kiểm tra quyền; gửi thông báo hai lần. | Nêu hành vi sai, bằng chứng và lý do cần sửa trước merge. |
| **Đề xuất cải thiện** | Có phương án giúp mã rõ hơn hoặc giảm chi phí bảo trì, nhưng thay đổi hiện tại vẫn có thể chấp nhận được. | Tách công thức thành helper có tên; bổ sung giải thích cho một quy tắc khó. | Nêu lợi ích và tính tùy chọn hoặc thời điểm phù hợp. |
| **Sở thích** | Một trong nhiều lựa chọn hợp lệ không tạo khác biệt đáng kể về hợp đồng hoặc chất lượng. | Thích switch thay if trong trường hợp đơn giản; thích một cách xuống dòng cụ thể. | Ghi rõ là không bắt buộc, hoặc không comment nếu không có giá trị. |

**Mức độ bắt buộc không nên suy ra từ âm lượng của câu chữ.** Một lời bình “em thấy không ổn lắm” có thể là lỗi bảo mật quan trọng, nhưng cũng có thể chỉ là sở thích. Reviewer phải nói rõ **bằng chứng, ảnh hưởng và quyết định mong muốn**.

Tương tự, một nhận xét về khả năng bảo trì đôi khi **có thể trở thành yêu cầu bắt buộc** khi rủi ro đủ lớn hoặc vi phạm tiêu chuẩn đã thống nhất. Ba nhóm trên là cách định hướng, không phải hộp phân loại bất biến cho mọi ngữ cảnh.

## 3. Lỗi cần sửa là gì?

**Lỗi cần sửa** là vấn đề mà nếu để nguyên, thay đổi chưa đạt tiêu chuẩn chấp nhận đã được xác định. Nó có thể thuộc các nhóm:

- **Sai hành vi:** Kết quả không khớp đặc tả ở một đầu vào hoặc trạng thái cụ thể.
- **Sai hợp đồng:** API đổi mã lỗi, dữ liệu trả về, nullability hoặc schema ngoài phạm vi yêu cầu.
- **Lỗi bảo mật:** Người không có quyền có đường đọc/ghi dữ liệu được bảo vệ.
- **Lỗi độ tin cậy:** Mất dữ liệu, gửi thao tác lặp, nuốt lỗi phụ thuộc hoặc vi phạm bất biến.
- **Lỗi tài nguyên nghiêm trọng:** Hàng đợi không giới hạn trong đường nhận tải không kiểm soát, hoặc mở tài nguyên mà không giải phóng khi lỗi.
- **Thiếu bằng chứng cần thiết:** Một thay đổi rủi ro cao không có kiểm thử/kiểm chứng phù hợp, dù chưa tái hiện bug.

Không phải lúc nào reviewer cũng phải chạy một bài test mới chứng minh được lỗi. Có những vấn đề có thể được lý giải chắc chắn từ code, hợp đồng và đường đi. Tuy nhiên, **nhận xét phải cho thấy cơ sở kết luận** thay vì chỉ nói “cách này có vẻ sai”.

### Dấu hiệu của một comment lỗi có chất lượng

Một nhận xét thường rõ hơn khi có:

1. **Vị trí:** Dòng code, nhánh hoặc đường xử lý liên quan.
2. **Điều kiện kích hoạt:** Đầu vào hoặc trạng thái nào làm vấn đề xuất hiện.
3. **Kết quả thực tế/dự kiến:** Code hiện làm gì và hợp đồng yêu cầu gì.
4. **Tác động:** Sai lệch ảnh hưởng người dùng, dữ liệu hay sự ổn định thế nào.
5. **Hướng xác minh hoặc sửa:** Test, ràng buộc hoặc giải pháp đơn giản có thể áp dụng.

Ví dụ câu “sai ở đây” không đủ rõ. Một câu như “Với tổng đơn đúng 500.000 VND, điều kiện > vẫn thu phí 30.000 VND; chính sách yêu cầu miễn phí từ 500.000 trở lên, nên cần dùng >= và thêm test tại biên” vừa cụ thể, vừa kiểm chứng được.

## 4. Đề xuất cải thiện là gì?

**Đề xuất cải thiện** nhắm tới lợi ích thực tế, nhưng không nhất thiết chặn pull request hiện tại.

Ví dụ:

- Đặt tên biến thể hiện ý nghĩa nghiệp vụ thay vì viết tắt mơ hồ.
- Trích xuất một nhánh dài để người đọc nhận diện bước xử lý nhanh hơn.
- Thêm test cho trường hợp ít rủi ro nhưng có thể tăng khả năng bảo vệ hồi quy.
- Di chuyển một cấu hình ra khỏi nơi gọi để giảm trùng lặp.
- Viết lại tài liệu để caller hiểu chính sách rõ hơn.
- Giảm lặp lại ở hai đoạn mã nếu chúng thực sự cùng một trách nhiệm.

Một đề xuất có giá trị cần giải thích **vì sao cải thiện đáng làm**. Nếu nó chỉ làm thay đổi hình thức theo gu cá nhân, có thể thuộc nhóm sở thích.

### Khi đề xuất nên để lại cho lần sau

Nếu cải thiện yêu cầu sửa nhiều file, tăng phạm vi review hoặc không liên quan trực tiếp tới yêu cầu hiện tại, có thể:

- Ghi comment **không chặn merge**.
- Tạo issue có phạm vi, owner và lý do rõ khi lợi ích đáng theo dõi.
- Chờ đến khi thành phần đó được thay đổi vì nhu cầu nghiệp vụ phù hợp.
- Đề nghị một PR riêng nếu việc tối ưu hóa/chuẩn hóa đủ lớn.

Không nên tạo issue cho mọi sở thích nhỏ. Backlog trở nên kém hữu ích nếu chứa hàng trăm nhận xét “đổi tên này cho đẹp” mà không có tác động.

## 5. Sở thích là gì và khi nào không còn là sở thích?

Những lựa chọn có thể là sở thích:

- Dùng **if/else** hay toán tử điều kiện ở biểu thức ngắn, rõ ràng.
- Thích gọi biến là **fee** hay **shippingFee** khi cả hai đều đủ ngữ cảnh.
- Chọn thứ tự các helper private không ảnh hưởng hành vi.
- Xuống dòng theo một kiểu formatter chưa được nhóm quy định.

Nhưng cùng một vấn đề có thể **không còn là sở thích** nếu:

- Repository có **quy ước đã thống nhất**.
- Một cách viết khiến hành vi bị hiểu sai hoặc khó kiểm chứng thực sự.
- Tên đang được dùng trong **API công khai**, JSON hoặc công cụ giám sát.
- Cách viết vi phạm yêu cầu ngôn ngữ hoặc bộ công cụ dự án.
- Chênh lệch ảnh hưởng tính tương thích, bảo mật, đồng thời hoặc hiệu năng.

Ví dụ, đổi tên biến local giữa hai tên đều rõ có thể chỉ là sở thích. Nhưng đổi **field trong JSON response** sẽ ảnh hưởng client; đó là vấn đề hợp đồng.

**Quy ước của nhóm phải được xác định và có thể tìm thấy**, chứ không phải sở thích của reviewer được áp đặt sau khi tác giả đã hoàn thành mã.

## 6. Cây quyết định để phân loại một nhận xét

~~~mermaid
flowchart TD
    A["Phát hiện điểm cần xem trong diff"] --> B{"Có vi phạm hợp đồng, rủi ro quan trọng hoặc chuẩn bắt buộc?"}
    B -- "Có bằng chứng" --> C["Lỗi / yêu cầu cần xử lý"]
    B -- "Chưa rõ" --> D{"Có thông tin đủ để xác minh?"}
    D -- "Chưa" --> E["Đặt câu hỏi, yêu cầu bằng chứng"]
    D -- "Có" --> F{"Phương án mới cải thiện chất lượng đáng kể?"}
    F -- "Có" --> G["Đề xuất cải thiện"]
    F -- "Không rõ hoặc không" --> H{"Chủ yếu là khác gu viết?"}
    H -- "Có" --> I["Sở thích: không bắt buộc hoặc bỏ qua"]
    H -- "Không" --> J["Làm rõ bối cảnh và mục tiêu"]
    C --> K["Nêu tác động và tiêu chí xác minh"]
    G --> L["Nêu lợi ích, chi phí và tính tùy chọn"]
~~~

Cây trên là **hướng dẫn suy nghĩ**, không phải chương trình chấm điểm tự động. Reviewer cần xét mức độ chắc chắn của bằng chứng, mức nghiêm trọng, phạm vi PR và tiêu chuẩn chấp nhận đã được thỏa thuận.

Đặc biệt, câu hỏi “Tại sao dùng cách này?” **không đồng nghĩa yêu cầu thay cách làm**. Một câu hỏi tìm hiểu có thể giúp reviewer xác định còn thiếu bối cảnh hay không.

## 7. Ví dụ xuyên suốt: một pull request tính phí giao hàng

Giả sử nhóm có hợp đồng nghiệp vụ đã phê duyệt:

1. **subtotalVnd** là số VND nguyên không âm.
2. Đơn **dưới 500.000 VND** trả phí giao tiêu chuẩn **30.000 VND**.
3. Đơn **từ 500.000 VND trở lên** miễn phí giao tiêu chuẩn.
4. Nếu chọn **express**, cộng phụ phí **20.000 VND**.
5. Hàm chỉ tính phí và trả kết quả, **không có tác dụng phụ**.

Đây là **quy tắc giả định của bài học**, không phải chính sách mặc định của một cửa hàng thực tế.

Một bản PR Java 17 được gửi review:

~~~java
public final class ShippingFeeCalculator {
    private ShippingFeeCalculator() {
    }

    public static long calculate(long subtotalVnd, boolean express) {
        long fee = subtotalVnd > 500_000L ? 0L : 30_000L;
        return fee + (express ? 20_000L : 0L);
    }
}
~~~

Với yêu cầu này, code có ít nhất **hai lỗi chức năng**:

- Dùng **>** thay vì **>=** tại ngưỡng 500.000 VND.
- Không từ chối **subtotalVnd âm**, dù hợp đồng yêu cầu giá trị không âm.

Trong khi đó, tên biến **fee** và cách viết toán tử điều kiện là những điểm có thể thảo luận theo khả năng đọc, nhưng **không cùng mức nghiêm trọng** với hai lỗi trên.

## 8. Review phải bắt đầu từ dữ liệu biên và hợp đồng

Bảng sau so sánh kết quả thực tế của code với kết quả kỳ vọng:

| subtotalVnd | express | Kỳ vọng | Code hiện tại | Đánh giá |
| ---: | :---: | ---: | ---: | --- |
| 0 | false | 30.000 | 30.000 | Đúng. |
| 499.999 | false | 30.000 | 30.000 | Đúng. |
| 500.000 | false | **0** | **30.000** | **Bug tại biên.** |
| 500.000 | true | **20.000** | **50.000** | **Bug tại biên với giao nhanh.** |
| 500.001 | false | 0 | 0 | Đúng. |
| -1 | false | **Từ chối** | **30.000** | **Bug vi phạm tiền điều kiện.** |

Nếu chỉ nhìn input 300.000 và 700.000 VND, reviewer có thể bỏ sót lỗi. Nếu chỉ kiểm tra hàm “chạy không ném exception”, test còn có thể xanh trong khi kết quả sai.

**Bằng chứng cụ thể làm rõ tính bắt buộc của nhận xét.** Không cần biến mọi khác biệt style thành blocker khi đã có hai sai lệch nghiệp vụ cần được ưu tiên.

## 9. Ba comment trên cùng một đoạn code

### Comment A — Lỗi cần sửa, chặn merge

> **Cần sửa – tính đúng đắn:** Theo hợp đồng, tổng đơn từ 500.000 VND được miễn phí tiêu chuẩn. Với subtotalVnd = 500_000 và express = false, toán tử > hiện trả 30.000 thay vì 0. Đề nghị đổi thành >= và thêm test tại 499.999, 500.000, 500.001 để bảo vệ biên này.

Vì sao tốt:

- Chỉ ra chính xác **điều kiện gây lỗi**.
- Nêu **actual** và **expected**.
- Dẫn tới **quy tắc đã được xác nhận**.
- Đề nghị một sửa đổi nhỏ và cách kiểm chứng.
- Giúp tác giả hiểu đây là **điều kiện merge**, không phải ý kiến tùy chọn.

Một comment lỗi khác:

> **Cần sửa – hợp đồng đầu vào:** Phương thức hiện chấp nhận subtotalVnd âm và trả phí như một đơn hợp lệ. Hợp đồng yêu cầu từ chối giá trị âm, nên cần kiểm tra trước khi tính và bổ sung test cho -1.

### Comment B — Đề xuất cải thiện

> **Đề xuất, không chặn:** Các giá trị 500.000, 30.000 và 20.000 là quy tắc nghiệp vụ. Đặt tên hằng số như FREE_THRESHOLD và EXPRESS_SURCHARGE sẽ giúp lần thay đổi phí sau dễ tìm hơn. Có thể làm ngay nếu diff vẫn nhỏ, hoặc tách một PR dọn cấu trúc.

Tại sao đây thường chỉ là đề xuất?

- Code có thể đúng theo hợp đồng ngay cả khi dùng literal.
- Giá trị của việc đặt tên phụ thuộc vào mức biến động chính sách và quy ước dự án.
- Reviewer giải thích **lợi ích bảo trì**, không chỉ “tôi thích hằng số”.

Nếu dự án có tiêu chuẩn bắt buộc cấm literal cho giá trị chính sách hoặc đây là nguyên nhân khiến thay đổi bị bỏ sót nhiều lần, tính bắt buộc có thể khác. Reviewer cần nói rõ **căn cứ đó**.

### Comment C — Sở thích cá nhân

> **Nit, hoàn toàn tùy chọn:** Mình quen đọc if/else hơn toán tử điều kiện ở đây. Nếu nhóm không có quy ước khác và tác giả thấy biểu thức hiện tại rõ, có thể giữ nguyên.

Tại sao không nên chặn merge?

- Hai cách viết có thể tương đương về hành vi.
- Không có bằng chứng một cách rõ hơn hẳn trong ngữ cảnh này.
- Tính nhất quán với formatter hoặc style guide của dự án quan trọng hơn thói quen cá nhân.

Một review tốt có thể **không gửi Comment C** để tiết kiệm sự chú ý cho lỗi thực sự.

## 10. Phiên bản sửa lỗi tối thiểu và kiểm thử JUnit 5

Sau khi sửa hai lỗi chức năng, mã có thể là:

~~~java
public final class ShippingFeeCalculator {
    private ShippingFeeCalculator() {
    }

    public static long calculate(long subtotalVnd, boolean express) {
        if (subtotalVnd < 0L) {
            throw new IllegalArgumentException(
                    "Subtotal must be non-negative");
        }

        long fee = subtotalVnd >= 500_000L ? 0L : 30_000L;
        return fee + (express ? 20_000L : 0L);
    }
}
~~~

Đây là **bản sửa lỗi tối thiểu**, chưa bắt buộc phải đổi tên biến hay trích xuất hằng số. Làm như vậy giúp reviewer nhìn rõ **hai thay đổi thuộc hợp đồng** trước khi thảo luận cải thiện khác.

Một tập JUnit 5 minh họa:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.CsvSource;

class ShippingFeeCalculatorTest {
    @ParameterizedTest
    @CsvSource({
            "0, false, 30000",
            "499999, false, 30000",
            "500000, false, 0",
            "500000, true, 20000",
            "500001, false, 0",
            "500001, true, 20000"
    })
    void respectsShippingPolicy(
            long subtotalVnd, boolean express, long expected) {
        assertEquals(expected,
                ShippingFeeCalculator.calculate(subtotalVnd, express));
    }

    @Test
    void rejectsNegativeSubtotal() {
        assertThrows(IllegalArgumentException.class,
                () -> ShippingFeeCalculator.calculate(-1L, false));
    }
}
~~~

Ví dụ sử dụng **JUnit Jupiter** và **JUnit Jupiter Params**. Không có hàm test nào được thực thi trong bước soạn tài liệu này; đoạn mã dùng để minh họa cách chứng minh nhận xét của reviewer.

Test nên sử dụng **kết quả kỳ vọng từ hợp đồng**, không lấy expected bằng cách gọi lại chính phương thức cần kiểm tra.

## 11. Cách nhận biết lỗi cần sửa khi không phải lỗi tính toán

Không phải mọi lỗi đều có bảng actual/expected đơn giản như tính phí. Nhưng vẫn có thể xác định **đường đi, bất biến và hậu quả**.

| Vấn đề nhìn thấy | Phân loại thường phù hợp | Bằng chứng cần quan tâm |
| --- | --- | --- |
| Truy vấn tài liệu bằng ID từ client mà không kiểm tra quyền trên tài liệu | **Lỗi bảo mật cần xử lý**. | Đường truy cập trái phép, tenant/resource và kiểm soát hiện có. |
| Dịch vụ phân quyền timeout rồi mặc định cho phép | **Lỗi bảo mật cần xử lý**. | Không có quyết định PERMIT đáng tin cậy nhưng vẫn vào đường đọc/ghi. |
| Gửi lệnh hoàn tiền hai lần khi cùng request được gửi lại | **Lỗi nghiệp vụ/độ tin cậy cần xử lý**. | Bất biến idempotency, side effect và ca tái hiện. |
| Không đóng tài nguyên khi nhánh lỗi xuất hiện | **Lỗi tài nguyên**, mức nghiêm trọng theo tác động. | Đường exception và rò rỉ file/connection. |
| Đổi tên field JSON công khai mà không có kế hoạch chuyển đổi | **Vấn đề tương thích cần đánh giá**. | Contract của client và chính sách versioning. |
| Một truy vấn trong vòng lặp tạo N+1 và vượt SLO đã đặt | **Lỗi hiệu năng hoặc blocker theo SLO**. | Workload đại diện, số query và ngân sách latency. |
| Nhiều wrapper chỉ chuyển lời gọi qua nhau | **Đề xuất cải thiện thiết kế** nếu chưa có hậu quả trực tiếp nghiêm trọng. | Chi phí lần theo hành vi, số nơi phải sửa và phương án đơn giản hơn. |
| Biến đặt tên kém nhưng không gây nhầm trong ngữ cảnh hiện tại | **Đề xuất hoặc sở thích**. | Tác động lên khả năng đọc và quy ước nhóm. |
| Khoảng trắng không theo formatter bắt buộc | **Vi phạm quy ước có thể kiểm tra tự động**. | Cấu hình/CI đã thống nhất, không cần tranh luận gu cá nhân. |

Một lỗi **có thể cần sửa** ngay cả khi test chưa thất bại, ví dụ khi review phát hiện đường truy cập dữ liệu không qua phân quyền. Ngược lại, một điểm khác style chưa chắc cần sửa dù reviewer có kinh nghiệm.

## 12. Mức độ nghiêm trọng khác với độ chắc chắn

Đừng nhầm **tác động tiềm tàng** với **mức chắc chắn rằng vấn đề tồn tại**.

Ví dụ:

- “Đã tái hiện: input 500.000 VND trả sai phí” → **chắc chắn cao**, tác động nghiệp vụ rõ.
- “Có thể có race condition khi hai request trừ tồn kho” → **nguy cơ tiềm tàng cao**, nhưng cần xem transaction/atomic update thực tế.
- “Tên biến có thể gây hiểu nhầm” → nhận xét bảo trì, mức chắc chắn phụ thuộc ngữ cảnh.
- “Mình thích dùng Stream hơn vòng lặp” → chủ yếu là sở thích, không nên trình bày như bug.

Một ma trận phản hồi:

| Mức ảnh hưởng tiềm tàng | Mức chắc chắn | Phản hồi thích hợp |
| --- | --- | --- |
| Cao | Cao | Nêu blocker kèm bằng chứng và điều kiện chấp nhận. |
| Cao | Thấp/chưa đủ dữ liệu | Đặt câu hỏi ưu tiên, yêu cầu làm rõ/kiểm chứng trước merge nếu rủi ro không thể chấp nhận. |
| Thấp | Cao | Đề xuất sửa nhỏ hoặc ghi nhận để xử lý theo quy ước. |
| Thấp | Thấp | Tránh kết luận vội; hỏi ngắn hoặc bỏ qua nếu ít giá trị. |

**Không nên dùng câu hỏi thay cho việc cảnh báo rủi ro rõ ràng.** Nếu một đường bảo mật đáng lo, nêu phạm vi nghi ngờ và yêu cầu kiểm chứng, dù chưa kết luận chắc chắn.

Cũng không nên tuyên bố “đây là lỗi” chỉ vì có khả năng xảy ra theo suy đoán; cần tìm cấu hình, điều kiện và nơi kiểm soát liên quan.

## 13. Dùng câu hỏi để làm rõ, không dùng câu hỏi để ngụy trang yêu cầu

Có những câu hỏi hiệu quả:

> “Ở đường gọi này, subtotalVnd âm được kiểm tra ở tầng nào? Hợp đồng của calculate đang cho phép âm hay yêu cầu tự từ chối?”

> “Hai endpoint này có cùng chính sách phí không? Nếu cùng một hợp đồng, chúng ta có thể cân nhắc gom quy tắc để tránh cập nhật lệch.”

Những câu hỏi trên giúp xác minh **nguồn yêu cầu và ranh giới trách nhiệm**.

Kém hiệu quả hơn:

> “Sao không biết dùng hằng số?”

> “Bạn không thấy cách này khó chịu à?”

> “Không phải ai cũng biết phải dùng Stream sao?”

Các câu này đưa ra đánh giá về con người hoặc gu cá nhân thay vì vấn đề kỹ thuật có thể xử lý.

Nếu thực sự có một quy ước bắt buộc, nói thẳng và dẫn nguồn:

> “Theo formatter/rule đã áp dụng trong repository, phần này cần được format bằng cùng cấu hình; CI hiện báo lệch ở file này.”

**Rõ ràng về tính bắt buộc tốt hơn dùng ngữ điệu mạnh để gây áp lực.**

## 14. Nhãn review giúp ích khi ý nghĩa được thống nhất

Một nhóm có thể thống nhất quy ước nhãn:

| Nhãn gợi ý | Ý nghĩa | Có chặn merge không? |
| --- | --- | --- |
| **Blocker / Must fix** | Vi phạm hợp đồng, rủi ro nghiêm trọng hoặc thiếu điều kiện chấp nhận bắt buộc. | Có, cho đến khi xử lý hoặc có quyết định chấp nhận rủi ro hợp lệ. |
| **Suggestion** | Phương án cải thiện có lợi ích cụ thể. | Mặc định không; có thể thảo luận phạm vi. |
| **Nit / Optional** | Sở thích nhỏ hoặc chỉnh lý không quan trọng. | Không. |
| **Question** | Chưa đủ bối cảnh để đánh giá. | Không tự động; có thể trở thành blocker nếu lộ rủi ro cao. |
| **Praise / Note** | Ghi nhận thiết kế tốt hoặc kiến thức cần chia sẻ. | Không. |

Tên nhãn chỉ là ví dụ. Nếu nhóm đã có quy ước khác, cần tuân theo quy ước đó để tránh mỗi reviewer tự diễn giải “nit” hoặc “suggestion” khác nhau.

**Không dùng nhãn để trốn trách nhiệm giải thích.** “Blocker” phải nêu được lý do; “Suggestion” phải nói rõ cải thiện nào được kỳ vọng.

## 15. Khi đề xuất cải thiện trở thành điều kiện bắt buộc

Không có ranh giới tuyệt đối giữa **cần sửa** và **nên cải thiện**. Phân loại phải phản ánh rủi ro và tiêu chuẩn của sản phẩm.

Ví dụ:

**Tình huống A:** Một phương thức 80 dòng khó đọc nhưng mới chỉ xử lý một phép chuyển đổi dữ liệu, có test tốt và ít nhánh. Việc tách helper có thể là đề xuất.

**Tình huống B:** Một phương thức 80 dòng vừa xác thực quyền, ghi dữ liệu, gọi thanh toán và gửi sự kiện trong các nhánh khó theo dõi. Code mới làm mất transaction boundary và có nguy cơ gửi thanh toán lặp. Khi ấy vấn đề không còn đơn thuần là “phương thức dài”; ranh giới và tác dụng phụ có thể là **lỗi cần sửa**.

**Tình huống C:** Một SDK không còn được hỗ trợ được thêm mới vào luồng xử lý thông tin nhạy cảm. Dù chưa có ca thất bại đang thấy, chính sách bảo mật và mức rủi ro có thể khiến việc thay dependency hoặc có biện pháp giảm thiểu là điều kiện chấp nhận.

**Tình huống D:** Dự án đã có tiêu chí bắt buộc cho naming/schema theo hợp đồng. Đổi một tên public trái tiêu chí có thể là blocker tương thích, không phải sở thích.

Vì vậy, reviewer nên mô tả **vấn đề nền tảng** thay vì chỉ nói “class này quá dài”, “đoạn này chưa clean” hay “cần SOLID hơn”.

## 16. Review trong phạm vi pull request

Một PR có mục tiêu cụ thể, chẳng hạn sửa ngưỡng phí. Review tốt cần bảo đảm mục tiêu đó đúng và không tạo hồi quy.

**Nên ưu tiên:**

1. Thay đổi có thực hiện đúng yêu cầu không?
2. Có đường đầu vào, lỗi hoặc tác dụng phụ quan trọng bị bỏ sót không?
3. Test có bảo vệ ranh giới và kết quả mong muốn không?
4. Có ảnh hưởng hợp đồng ngoài phạm vi không?
5. Có rủi ro bảo mật, dữ liệu, độ tin cậy hoặc tài nguyên chưa xử lý không?

**Cần cân nhắc khi đề nghị thêm:**

- Refactor toàn bộ module không liên quan.
- Đổi cấu hình formatter diện rộng.
- Viết lại thư viện hoặc thay công nghệ vì thói quen nhóm.
- Đổi tên nhiều lớp ngoài vùng chịu ảnh hưởng.
- Tối ưu hóa chưa có số liệu hoặc không liên quan SLO.

Một cải thiện lớn có thể chính đáng, nhưng nên được **tách thành issue hoặc PR riêng** nếu làm tăng phạm vi và rủi ro của bản thay đổi hiện tại.

Đừng để comment về dấu cách hoặc tên local chiếm hết thời gian xem **điều kiện cho phép, giao dịch và dữ liệu khách hàng**.

## 17. Tính đúng và tính nhất quán không phải lựa chọn loại trừ nhau

Quy ước được thống nhất là hữu ích: nó giảm tranh luận lặp lại và giúp người đọc nhanh hiểu code.

Tuy vậy, cách vận hành quy ước nên là:

- **Formatter/checker** xử lý các khác biệt có thể quyết định tự động.
- **Style guide hoặc conventions** được viết rõ cho các trường hợp cần con người áp dụng.
- **Code review** tập trung vào ý nghĩa, hợp đồng, rủi ro và các ngoại lệ có lý do.
- **Thay đổi quy ước mới** được thảo luận và chấp nhận ở cấp nhóm, không áp đặt trong từng PR bất kỳ.

Nếu người review muốn thay quy ước đã thống nhất, nên mở thảo luận riêng. Không nên giữ một PR chức năng làm “con tin” để giải quyết tranh luận về kiểu đặt dấu ngoặc của cả dự án.

### Khi formatter hoặc linter báo lỗi

Đây có thể là **yêu cầu quy trình bắt buộc**, nhưng cần phân biệt với bug hành vi:

- “CI format fail” nghĩa là chưa đạt điều kiện chất lượng/công cụ mà nhóm đã chốt.
- Nó **không tự chứng minh** phép tính hoặc logic nghiệp vụ sai.
- Hướng sửa thường là chạy đúng formatter/config hoặc điều chỉnh ngoại lệ hợp lý.
- Reviewer không cần viết hàng chục comment cùng một lỗi whitespace nếu máy có thể báo rõ.

Phân biệt lý do giúp tác giả ưu tiên và giải quyết nhanh.

## 18. Một comment hiệu quả có cấu trúc đơn giản

Có thể dùng khuôn mẫu:

~~~text
[Phân loại và mức độ bắt buộc]
Bối cảnh: dòng/đường xử lý nào?
Bằng chứng: với input/trạng thái X, actual khác expected ở đâu?
Tác động: vì sao cần quan tâm?
Đề nghị: hành động hoặc test nào giải quyết được?
~~~

Không cần điền như một form cho mọi comment. Mục tiêu là truyền tải **sự kiện, lý do và mong muốn** bằng ngôn ngữ dễ hợp tác.

Ví dụ mẫu comment cho ba nhóm:

~~~text
[Must fix] Nếu subtotalVnd = 500_000, nhánh > vẫn thu phí
30_000, trái quy tắc miễn phí từ ngưỡng trở lên. Cần sửa
điều kiện và thêm test tại biên trước merge.

[Suggestion] Có thể đặt tên hằng số cho ngưỡng và phụ phí
để lần đổi chính sách sau dễ tìm hơn. Không chặn PR này.

[Nit/optional] Mình quen đọc if/else hơn ternary ở đây,
nhưng cả hai cách đều rõ theo style hiện tại; có thể bỏ qua.
~~~

Những câu trên khác nhau về **căn cứ và tính bắt buộc**, không phải chỉ khác từ ngữ.

## 19. Review tập trung vào code, không công kích con người

Ngôn ngữ nhận xét ảnh hưởng chất lượng trao đổi. Ví dụ:

| Ít hiệu quả | Tốt hơn |
| --- | --- |
| “Bạn viết sai rồi.” | “Ở input này, kết quả không khớp hợp đồng; đây là ca tái hiện.” |
| “Sao lại code kiểu này?” | “Quyết định dùng hướng này có ràng buộc nào mình chưa thấy không?” |
| “Chắc chắn phải refactor toàn bộ.” | “Đoạn này khiến sửa quy tắc phải chạm ba nơi; có thể tách phần trùng lặp trong thay đổi riêng không?” |
| “Tất cả mọi người đều biết dùng Stream.” | “Cách dùng Stream ở đây có lợi ích cụ thể so với vòng lặp hiện tại không? Nếu không, mình nghiêng về giữ cách đang rõ hơn.” |
| “LGTM, nhìn ổn.” | “Đã kiểm tra ngưỡng, đầu vào âm và test; chưa thấy vấn đề trong phạm vi này.” |

Tránh nhận xét về năng lực hoặc thái độ của người viết. **Code có thể có lỗi mà người viết vẫn đang làm công việc tốt trong ràng buộc khó**, và người review cũng có thể thiếu bối cảnh.

Điều này không có nghĩa né tránh các nhận xét quan trọng. Một blocker có bằng chứng nên được nói **rõ ràng, lịch sự và kịp thời**.

## 20. Trách nhiệm của tác giả khi nhận nhận xét

Tác giả cũng có vai trò giúp review hiệu quả:

1. **Đọc nội dung và phân loại:** Đây là blocker, suggestion, nit hay câu hỏi?
2. **Xác minh bằng chứng:** Nếu một ví dụ bị sai, kiểm tra yêu cầu và test tương ứng.
3. **Sửa vấn đề cần sửa:** Tập trung vào kết quả và trạng thái có thể kiểm chứng.
4. **Trả lời khi không đồng ý:** Đưa ra lý do kỹ thuật hoặc tài liệu hợp đồng, không chỉ “mình thấy vậy tốt hơn”.
5. **Nêu phạm vi:** Nếu suggestion quá lớn, đề xuất issue/PR riêng hoặc lý do giữ nguyên.
6. **Thông báo thay đổi:** Chỉ ra commit hoặc test nào giải quyết comment.
7. **Không sửa để làm đẹp con số review:** Nếu hành vi đúng nhưng comment chưa rõ, trao đổi để thống nhất thay vì thực hiện refactor không cần thiết.

Ví dụ trả lời blocker:

> “Đúng, ca 500.000 VND đang trả 30.000. Mình đã đổi sang >= và thêm test 499.999/500.000/500.001, cùng ca subtotal âm. Nhờ bạn xem lại diff.”

Ví dụ trả lời suggestion:

> “Mình đồng ý hằng số có tên sẽ hữu ích. PR này đang cần vá ngưỡng gấp nên mình giữ phạm vi nhỏ, sẽ mở một thay đổi riêng để gom các giá trị phí sau khi hợp đồng được xác nhận.”

Một cuộc trao đổi tốt không yêu cầu người review luôn đúng hoặc tác giả luôn đồng ý. Nó yêu cầu **lý do minh bạch và quyết định dựa trên bằng chứng**.

## 21. Khi reviewer và tác giả không thống nhất

Bất đồng có thể đến từ:

- Hai người đang dựa trên **hai phiên bản yêu cầu khác nhau**.
- Một người biết quy tắc vận hành chưa được tài liệu hóa.
- Hai người đánh giá **rủi ro và chi phí** khác nhau.
- Một comment thật ra là sở thích nhưng bị trình bày như blocker.
- Phạm vi sở hữu hoặc tiêu chí merge chưa rõ.

Quy trình phù hợp:

~~~mermaid
flowchart TD
    A["Có bất đồng review"] --> B["Làm rõ nhận xét là lỗi, đề xuất hay sở thích"]
    B --> C["Đối chiếu hợp đồng và bằng chứng"]
    C --> D{"Có rủi ro cần xử lý theo tiêu chí merge?"}
    D -- "Có" --> E["Chọn cách sửa/giảm thiểu, thêm kiểm chứng"]
    D -- "Chưa rõ" --> F["Nhờ owner/nhóm liên quan xác nhận"]
    D -- "Không" --> G["Giữ phương án phù hợp; ghi cải thiện tùy chọn"]
    F --> H["Chốt quyết định và lý do"]
    E --> H
    G --> H
~~~

Nếu bất đồng liên quan tiền, phân quyền, mất dữ liệu hoặc tính tương thích, nên tìm **người sở hữu hợp đồng** hoặc reviewer chuyên trách phù hợp, thay vì bỏ qua vì “hai người có hai quan điểm”.

Nếu chỉ là sở thích về cách viết, nên ưu tiên style guide hiện có hoặc một quyết định đơn giản, rồi kết thúc tranh luận. **Không nên kéo dài PR bằng vòng lặp comment không tạo thêm bằng chứng.**

## 22. Tránh dùng số lượng comment để đánh giá chất lượng review

Một review có 30 comment về tên biến và khoảng trắng chưa chắc giá trị hơn một review phát hiện đúng một lỗi kiểm soát quyền nghiêm trọng.

Những tín hiệu hữu ích hơn khi đánh giá quy trình:

- Có **bỏ sót lỗi nghiêm trọng** có thể phát hiện qua diff và hợp đồng không?
- Người review có nêu **điều kiện tái hiện hoặc cơ sở kỹ thuật** không?
- Nhận xét có giúp tác giả biết **phải sửa hay có thể cân nhắc** không?
- PR có bị trì hoãn dài vì tranh luận sở thích không?
- Những lỗi lặp lại có được chuyển thành **test hoặc quy ước tự động** không?
- Những cải thiện cấu trúc lớn có được theo dõi phù hợp thay vì chen vào bản vá gấp không?
- Sau review, người sửa khác có hiểu rõ hơn về rủi ro và hợp đồng không?

**Không nên tối ưu số comment, số blocker hoặc thời gian review như các chỉ tiêu đơn lẻ.** Chúng chỉ là dữ liệu vận hành, cần đi cùng tác động thật.

## 23. Checklist nhanh trước khi gửi một comment

Tự hỏi:

1. **Mình đang nói về hành vi sai, cải thiện có ích hay sở thích?**
2. **Nếu coi là lỗi, nguồn yêu cầu hoặc bất biến nào bị vi phạm?**
3. **Có input/trạng thái hoặc đường code cụ thể nào để kiểm chứng không?**
4. **Hậu quả là gì và có đủ quan trọng để chặn merge không?**
5. **Mình có đang suy đoán khi chưa đọc đủ ngữ cảnh không?**
6. **Đây có phải quy ước chung hay chỉ là gu cá nhân?**
7. **Đề xuất có đúng phạm vi PR không?**
8. **Một công cụ tự động đã đủ để xử lý vấn đề này chưa?**
9. **Comment có nêu rõ mức độ bắt buộc không?**
10. **Lời văn tập trung vào code và hợp đồng, không phán xét người viết chứ?**

Nếu một comment chỉ còn ý “mình thích phương án khác”, cân nhắc **không gửi**, hoặc ghi rõ là nit/optional. Sự chú ý của reviewer và tác giả là nguồn lực hữu hạn.

## 24. Tình huống tự luyện

### Tình huống A — Thiếu điều kiện phân quyền

Một endpoint trả nội dung tài liệu theo documentId. Người viết đã kiểm tra user đăng nhập nhưng không kiểm tra user có quyền với tài liệu cụ thể.

**Câu hỏi:** Lỗi cần sửa, đề xuất hay sở thích?

**Gợi ý:** Đây là nghi vấn **lỗi bảo mật có rủi ro cao**. Cần xác minh cơ chế kiểm soát quyền ở các lớp khác và đảm bảo người không có quyền không thể đọc tài liệu; không xem đây là stylistic improvement.

### Tình huống B — Đặt tên biến

Một phương thức ngắn tính tổng phí dùng biến **fee**; các dòng xung quanh rõ nghĩa và không có quy ước yêu cầu tên chi tiết hơn.

**Câu hỏi:** Có nên chặn merge để đổi thành shippingFee không?

**Gợi ý:** Thường không. Có thể là đề xuất hoặc sở thích, phụ thuộc khả năng đọc trong ngữ cảnh. Nêu lợi ích cụ thể nếu muốn góp ý.

### Tình huống C — Thêm test tại biên

Một thay đổi sửa điều kiện **quantity > 10** thành **quantity >= 10** nhưng chỉ có test với quantity = 20.

**Câu hỏi:** Reviewer nên góp ý thế nào?

**Gợi ý:** Yêu cầu test cho 9, 10, 11 vì thay đổi trực tiếp điểm biên; thiếu test ở đúng trường hợp đổi hành vi làm bằng chứng chấp nhận chưa đủ.

### Tình huống D — Tranh luận Stream và vòng lặp

Một đoạn duyệt 5 phần tử dùng for-each rõ ràng. Reviewer thích Stream vì ít dòng hơn, không có quy ước bắt buộc.

**Câu hỏi:** Nên xếp vào nhóm nào?

**Gợi ý:** Chủ yếu là sở thích nếu không có lợi ích cụ thể về độ rõ, tính đúng hoặc khả năng sửa. Không nên thay chỉ vì LOC giảm.

### Tình huống E — Lỗi tài nguyên chỉ xảy ra ở đường thất bại

Mã mở InputStream nhưng chỉ đóng khi parse thành công. Khi parser ném exception, stream không được đóng.

**Câu hỏi:** Cần góp ý ra sao?

**Gợi ý:** Nêu đường ngoại lệ, nguy cơ rò rỉ tài nguyên, đề nghị dùng try-with-resources và có kiểm chứng phù hợp. Đây thường là lỗi cần sửa, không chỉ là sở thích.

### Tình huống F — Đề xuất hợp nhất hai chính sách

Hai service có công thức phí giống nhau hôm nay, nhưng do hai bộ phận quản lý và thay đổi độc lập theo từng thị trường.

**Câu hỏi:** Có nên ép dùng một class chung để “xóa trùng lặp” không?

**Gợi ý:** Không mặc định. Cần xác nhận **quy tắc có cùng nơi sở hữu và cùng lý do thay đổi**. Hợp nhất những khái niệm khác nhau có thể tăng ghép nối.

### Tình huống G — Quy ước được kiểm tra bằng CI

Một PR thay đổi code đúng nghiệp vụ nhưng không đạt formatter check đã được nhóm thống nhất. Reviewer yêu cầu chạy formatter trước merge.

**Câu hỏi:** Đây có phải chỉ là sở thích cá nhân?

**Gợi ý:** Không. Đây là **điều kiện quy trình/công cụ đã chốt**. Nên xử lý bằng formatter/CI, đồng thời không nhầm nó với bug nghiệp vụ.

### Tình huống H — Rủi ro chưa chắc chắn

Reviewer nghi hai luồng có thể cùng hoàn tiền cho một giao dịch, nhưng chưa rõ repository đã dùng optimistic locking hay idempotency key chưa.

**Câu hỏi:** Nên khẳng định có bug hay hỏi thêm?

**Gợi ý:** Nêu rủi ro nghiêm trọng, điều kiện cạnh tranh và yêu cầu kiểm chứng ranh giới lưu trữ; chưa nên kết luận chắc chắn khi thiếu thông tin. Có thể giữ review ở trạng thái cần làm rõ trước merge do mức hậu quả cao.

## 25. Bài tập viết lại nhận xét

Thử chuyển các câu sau thành comment có căn cứ và mức độ rõ:

| Câu ban đầu | Cách cải thiện |
| --- | --- |
| “Code này dở.” | Chỉ ra input/trạng thái, hành vi sai và kết quả kỳ vọng. |
| “Tên này không đẹp.” | Giải thích tác động lên khả năng hiểu; nếu không có tác động, ghi rõ sở thích. |
| “Phải refactor.” | Nêu trách nhiệm nào bị trộn, thay đổi nào trở nên khó và phạm vi cải thiện. |
| “Thêm test đi.” | Chỉ ra ca biên, đường lỗi hoặc tác dụng phụ mà test hiện chưa bảo vệ. |
| “Tôi thích cách cũ.” | So sánh hai phương án bằng yêu cầu, rủi ro và quy ước; nếu chỉ là gu, không chặn. |

Một mẫu viết lại cho câu “Thêm test đi”:

> “Phần điều kiện mới chuyển ngưỡng từ > sang >=. Các test hiện có chưa có quantity = 10, nên có thể không phát hiện lỗi ở điểm chuyển. Đề nghị bổ sung 9/10/11 với expected theo yêu cầu trước khi merge.”

Nhận xét này dễ xử lý vì tác giả biết **test nào thiếu và vì sao nó quan trọng**.

---

**Ghi nhớ:** Code review có chất lượng không phải là buộc mọi người viết theo cùng sở thích. Hãy phân biệt **lỗi cần sửa** với **đề xuất cải thiện** và **sở thích**, dựa trên **hợp đồng, tác động và bằng chứng**. Nêu rõ comment nào chặn merge, comment nào tùy chọn, hỏi thêm khi chưa đủ ngữ cảnh và ưu tiên đường xử lý có rủi ro cao. Một review tốt giúp mã **đúng hơn, an toàn hơn, dễ thay đổi hơn**, đồng thời giữ cho sự hợp tác giữa người viết và người review hiệu quả.
