# Xác định câu hỏi cần trả lời trước khi chọn chỉ số

Trong chương **Chỉ số chất lượng** của module **CODE_QUALITY_FUNDAMENTALS**, chúng ta học một bước thường bị bỏ qua trước khi mở dashboard hay đặt mục tiêu “coverage trên 80%”: **xác định chính xác câu hỏi nào cần được trả lời để đưa ra quyết định kỹ thuật tốt hơn**.

Module **CODE_QUALITY_FUNDAMENTALS** hướng đến việc hiểu những thuộc tính quyết định mã nguồn có **đáng tin cậy, dễ hiểu và dễ thay đổi** hay không. Chỉ số (*metric*) là công cụ quan sát một phần của những thuộc tính ấy. Nó giúp phát hiện xu hướng, đặt câu hỏi, kiểm tra giả thuyết và theo dõi tác động của thay đổi. Nhưng một con số đẹp không tự đồng nghĩa phần mềm tốt: 100% độ bao phủ nhánh vẫn có thể bỏ sót lỗi tại đúng ngưỡng; một phương thức ngắn vẫn có thể rất khó hiểu; thời gian review giảm không bảo đảm review có chất lượng.

> **Đừng bắt đầu bằng câu hỏi “chúng ta nên đo chỉ số gì?”. Hãy bắt đầu bằng “điều gì chúng ta cần biết, để ai quyết định việc gì, trong phạm vi và khoảng thời gian nào?”.**

Bài này hướng dẫn cách chuyển **mục tiêu chất lượng → câu hỏi cần trả lời → bằng chứng phù hợp → chỉ số có định nghĩa rõ → hành động có thể thực hiện**, cùng các giới hạn khi dùng chỉ số trong phát triển Java.

## 1. Mục tiêu học tập

Sau bài học, người học có thể:

1. Phân biệt **mục tiêu chất lượng**, **câu hỏi cần trả lời**, **chỉ số** và **quyết định dựa trên bằng chứng**.
2. Viết một câu hỏi đo lường cụ thể về tính đúng đắn, khả năng đọc, khả năng kiểm thử, độ phức tạp hoặc khả năng thay đổi mã.
3. Chọn một hoặc nhiều chỉ số phù hợp với câu hỏi, thay vì mặc định dùng LOC, coverage hoặc số lượng bug cho mọi vấn đề.
4. Xác định đơn vị, mẫu số, phạm vi mã, khoảng thời gian, nguồn dữ liệu và điều kiện loại trừ của chỉ số.
5. Giải thích giới hạn của các chỉ số như coverage, cyclomatic complexity, defect count, lead time và độ trễ vận hành.
6. Nhận biết rủi ro tối ưu theo chỉ số (*Goodhart's law*), ngụy kết luận từ dữ liệu thiếu, mẫu nhỏ hoặc so sánh không tương đồng.
7. Kết hợp chỉ số định lượng với review, test và quan sát định tính để ra quyết định an toàn.
8. Thiết kế một kế hoạch đo lường nhỏ, có khả năng triển khai và kiểm tra lại khi mục tiêu thay đổi.

## 2. Vì sao phải xác định câu hỏi trước?

Một nhóm có thể bắt đầu bằng mục tiêu nghe có vẻ hợp lý:

- “Coverage phải đạt 90%.”
- “Mỗi hàm không được quá 30 dòng.”
- “Số lỗi được báo phải giảm 50%.”
- “Review mỗi PR trong vòng một giờ.”

Nếu không biết vấn đề cần giải quyết, những ngưỡng ấy dễ biến thành **mục tiêu hình thức**. Nhóm có thể tăng coverage bằng test không kiểm tra kết quả, chia một hàm thành nhiều helper tên mơ hồ, giảm số bug bằng cách không ghi nhận bug hoặc phê duyệt PR quá nhanh để đạt thời gian review.

Một câu hỏi có thể dẫn đến hành động hơn là:

> “Những thay đổi trong logic tính phí ba tháng gần đây bị lọt lỗi ở điều kiện biên nào, và các test hồi quy hiện đã bảo vệ những điều kiện đó chưa?”

Câu hỏi này gợi ý nhiều loại bằng chứng: lịch sử sự cố, các điều kiện biên trong đặc tả, test hiện có, branch coverage của đoạn mã liên quan và kết quả review. Một con số coverage tổng repository có thể **không phải câu trả lời phù hợp nhất**.

### 2.1. Hai cách bắt đầu

| Bắt đầu từ chỉ số | Bắt đầu từ câu hỏi |
| --- | --- |
| “Tăng line coverage lên 90%.” | “Phần logic quan trọng nào chưa được thực thi bởi test tự động?” |
| “Giảm số dòng mỗi phương thức.” | “Những phương thức nào khiến người mới khó hiểu hành vi hoặc thường bị sửa sai?” |
| “Giảm số bug mở.” | “Lỗi nghiêm trọng nào vẫn đến tay người dùng, và vì sao không được phát hiện sớm?” |
| “Tăng số commit mỗi ngày.” | “Các thay đổi cần thiết có được đưa vào sử dụng an toàn, với thời gian chờ và tỷ lệ thất bại chấp nhận được không?” |
| “Hạ p95 bằng mọi giá.” | “Tác vụ người dùng nào vượt yêu cầu độ trễ, trong mẫu tải nào, và thời gian bị tiêu hao ở đâu?” |

Cột bên phải chưa đưa ra chỉ số ngay. Đó là chủ ý: **câu hỏi quyết định cách đo**, còn phép đo cần được lựa chọn theo thuộc tính mà câu hỏi muốn làm rõ.

## 3. Phân biệt mục tiêu, câu hỏi, chỉ số và hành động

Một khung suy nghĩ đơn giản tương tự cách tiếp cận *Goal–Question–Metric (GQM)*:

~~~text
Mục tiêu chất lượng
        |
        v
Câu hỏi cần có câu trả lời
        |
        v
Bằng chứng và phép đo phù hợp
        |
        v
Diễn giải trong ngữ cảnh
        |
        v
Quyết định / hành động
        |
        v
Đo lại và xem xét kết quả
~~~

### 3.1. Mục tiêu là điều muốn cải thiện

Ví dụ: **giảm nguy cơ tính sai số tiền trong hệ thống đặt hàng khi chính sách giá được thay đổi**.

Mục tiêu tốt đủ gần nhu cầu thực: giảm sai lệch, cải thiện khả năng khôi phục, giúp người khác sửa logic an toàn. “Tăng điểm chất lượng lên 95” chưa cho biết vì sao con số ấy có ích.

### 3.2. Câu hỏi là khoảng trống tri thức cần làm rõ

Ví dụ:

1. Những thay đổi về tính giá thường gây lỗi ở nhóm điều kiện nào?
2. Bộ test đã kiểm tra đúng ngưỡng, ngay dưới và ngay trên ngưỡng chưa?
3. Các nhánh xử lý lỗi trong mã vừa sửa có được chạy hay không?
4. Khi phát hiện sai lệch, mất bao lâu để xác định quy tắc và nơi chịu trách nhiệm?
5. Quy trình phát hành có làm lỗi tính giá lọt vào production không?

Không phải tất cả câu hỏi đều cần một chỉ số phần trăm. Một câu hỏi như “tại sao phép tính phụ thuộc tổng trước chiết khấu?” có thể được trả lời tốt hơn bằng **đặc tả, ADR và review mã**, không phải dashboard.

### 3.3. Chỉ số là một phép quan sát cụ thể

Ví dụ: **tỷ lệ nhánh được thực thi của mã tính giá đã thay đổi trong PR**, đo bằng công cụ coverage đã chọn.

Chỉ số trả lời câu hỏi rất hẹp: các nhánh được công cụ đếm có được thực thi không? Nó **không trả lời** liệu kết quả tính tiền đúng, assertion có mạnh hoặc nghiệp vụ đã đủ trường hợp biên.

### 3.4. Hành động là điều sẽ làm khác đi khi có bằng chứng

Ví dụ:

- Nếu một nhánh quan trọng chưa được chạy, thêm test tạo đúng tình huống và assertion có ý nghĩa.
- Nếu đã có cả hai nhánh nhưng từng lỗi ở đúng ngưỡng, bổ sung test giá trị biên và xem lại oracle.
- Nếu vấn đề đến từ dữ liệu phiên bản cũ, thêm contract/integration test thay vì chỉ tăng unit coverage.
- Nếu chưa biết nguyên nhân, điều tra thêm thay vì vội chặn mọi PR bằng một tỷ lệ cố định.

**Chỉ số hữu ích khi có mối liên hệ rõ với một quyết định có thể thực hiện.**

## 4. Một câu hỏi đo lường tốt gồm những gì?

Trước khi chọn chỉ số, hãy hoàn thiện câu hỏi theo sáu thành phần.

| Thành phần | Câu cần trả lời | Ví dụ trong Java |
| --- | --- | --- |
| **Đối tượng** | Đang quan sát phần nào? | Module báo giá, không phải toàn bộ monorepo. |
| **Thuộc tính** | Muốn biết điều gì về nó? | Khả năng phát hiện hồi quy ở điều kiện biên. |
| **Bối cảnh** | Với dữ liệu, tải, yêu cầu nào? | Chính sách miễn phí vận chuyển theo hạng khách hàng. |
| **Khoảng thời gian** | Khi nào, so với giai đoạn nào? | Những PR trong sáu tuần gần đây. |
| **Người quyết định** | Ai sẽ dùng câu trả lời? | Người review và nhóm sở hữu logic tính phí. |
| **Hành động** | Có kết quả thì sẽ làm gì? | Bổ sung test, điều chỉnh hợp đồng hoặc ranh giới module. |

Một câu hỏi cụ thể:

> “Trong các PR sửa chính sách vận chuyển của module báo giá trong sáu tuần gần đây, có nhánh điều kiện mới nào chưa được test chạy qua và có tình huống biên nào chưa có assertion, để nhóm quyết định bổ sung test trước khi phát hành?”

Câu này chỉ rõ phạm vi, thời điểm, bằng chứng và người có thể hành động. Nó không ép phải dùng một chỉ số duy nhất.

### 4.1. Dùng câu hỏi “nếu biết con số này thì sao?”

Giả sử nhóm muốn thu thập số lượng phương thức trên mỗi class.

Hỏi tiếp: **“Nếu số đó tăng từ 12 lên 18, chúng ta sẽ quyết định điều gì?”**

- Nếu không biết, chỉ số có thể chỉ là số liệu trang trí.
- Nếu định dùng nó để nhận diện class gánh nhiều trách nhiệm, cần bổ sung bằng chứng: thay đổi có thường xuyên chạm những phương thức không liên quan không, class có nhiều lý do thay đổi hay không, có lỗi do trạng thái chung không?
- Nếu dùng nó để đánh giá năng suất của một lập trình viên, cần xem lại vì số phương thức **không có quan hệ đơn giản** với đóng góp hoặc chất lượng.

Không cần biến mọi câu hỏi thành quyết định tự động. Một số chỉ số là tín hiệu để **ưu tiên điều tra**, không phải để chấp nhận hay từ chối thay đổi ngay lập tức.

## 5. Chọn loại bằng chứng phù hợp với câu hỏi

**Định lượng** giúp quan sát phạm vi, tần suất và xu hướng. **Định tính** giúp hiểu nguyên nhân, ngữ nghĩa và bối cảnh. Kết hợp chúng thường tốt hơn dùng một bên.

| Câu hỏi cần trả lời | Bằng chứng có thể phù hợp | Chỉ dựa vào một con số dễ bỏ sót điều gì? |
| --- | --- | --- |
| Logic quan trọng đã có test thực thi chưa? | Line/branch coverage theo module hoặc diff, xem test liên quan. | Test có assertion đúng hay không. |
| Test có phát hiện sai lệch nhỏ trong logic không? | Test hồi quy, mutation testing, review các trường hợp biên. | Mutant tương đương và những yêu cầu chưa được mô hình hóa. |
| Người bảo trì có hiểu nhanh một chức năng không? | Review theo nhiệm vụ, khảo sát người mới, cognitive complexity như tín hiệu. | Chi phí đi qua nhiều file và ngữ nghĩa nghiệp vụ. |
| Thay đổi có thường gây lỗi sau khi triển khai không? | Sự cố có liên hệ với thay đổi, tỷ lệ thay đổi phải khôi phục/sửa nóng. | Mức độ khó của thay đổi, sai lệch về cách ghi nhận sự cố. |
| Nơi nào đang tiêu tốn độ trễ? | Profiling, trace, p95 theo endpoint và mẫu tải. | Thời gian của từng phụ thuộc và khác biệt dữ liệu/tải. |
| Thay đổi API có an toàn cho client không? | Contract test, phân tích phiên bản client, trường hợp tích hợp. | Những client hoặc đường dùng không được quan sát. |
| Chính sách bảo mật được thực thi chưa? | Kiểm thử phân quyền, review thiết kế, scan phù hợp, sự cố thực. | Lớp lỗi mà công cụ không kiểm tra được. |
| Đội đang chậm do chờ review hay chờ môi trường? | Dòng thời gian PR/pipeline, phỏng vấn và phân tích bottleneck. | Chất lượng review và nguyên nhân chậm thật. |

**Không có một bộ chỉ số chuẩn trả lời mọi câu hỏi về chất lượng.** Cần chọn theo mục đích và mức độ rủi ro cụ thể.

## 6. Phân biệt các nhóm chỉ số thường gặp

Các chỉ số dưới đây có thể hỗ trợ **CODE_QUALITY_FUNDAMENTALS**, nhưng ý nghĩa phụ thuộc vào câu hỏi đặt ra.

### 6.1. Chỉ số về cấu trúc mã

Ví dụ: số dòng mã (LOC), cyclomatic complexity, cognitive complexity, số phụ thuộc giữa module, mức trùng lặp.

Chúng hữu ích để **chọn nơi cần xem xét kỹ**. Tuy nhiên:

- Một hàm dài chưa chắc khó hiểu.
- Một hàm ngắn có thể chứa nhiều điều kiện phức tạp.
- Tách nhánh sang các helper có thể giảm điểm của hàm gọi nhưng không xóa số quyết định nghiệp vụ.
- Trùng lặp có thể có chủ đích khi hai khối tương tự nhưng thay đổi độc lập; gộp sai có thể tạo coupling.

### 6.2. Chỉ số về bằng chứng kiểm thử

Ví dụ: line coverage, instruction coverage, branch coverage, tỷ lệ test không ổn định, mutation score, tỷ lệ pass theo bộ test.

Chúng giúp trả lời những câu hỏi khác nhau:

- Coverage: **đã thực thi những phần nào?**
- Mutation score: **test có phát hiện một số thay đổi giả lập trong mã không?**
- Flaky test rate: **kết quả test có ổn định khi điều kiện đáng lẽ như nhau không?**

Không chỉ số nào trong số này tự chứng minh toàn bộ hệ thống đúng.

### 6.3. Chỉ số về thay đổi và lỗi

Ví dụ: số sự cố production liên quan đến một lần phát hành, tỷ lệ lần triển khai phải khôi phục, thời gian khôi phục, thời gian từ khi tạo PR tới khi triển khai.

Các chỉ số này gắn với **quy trình thay đổi và kết quả vận hành**, không trực tiếp đo người viết mã giỏi hay kém. Mức rủi ro và sự khác biệt giữa sản phẩm phải được xét khi so sánh.

### 6.4. Chỉ số hiệu năng và tài nguyên

Ví dụ: p95 độ trễ, throughput, CPU, heap, GC pauses, số truy vấn database mỗi request, cache hit rate.

Chúng có ích khi mục tiêu liên quan tốc độ, chi phí hoặc khả năng mở rộng. Nhưng cache hit rate cao có thể đi kèm dữ liệu sai; CPU thấp chưa chắc phản hồi nhanh nếu hệ thống đang chờ mạng.

### 6.5. Chỉ số vận hành và bảo mật

Ví dụ: tỷ lệ lỗi API theo mã/endpoint, thời gian phát hiện–khắc phục sự cố, cảnh báo có hành động thực, tỷ lệ kiểm tra bảo mật quan trọng được thực hiện.

Số lượng cảnh báo không tự đại diện mức an toàn. Cảnh báo ít có thể do cấu hình lỏng, ít quét hoặc bỏ sót; cảnh báo nhiều có thể là false positive. Cần xét **khả năng phát hiện, mức nghiêm trọng và việc xử lý vấn đề thực**.

## 7. Ví dụ Java: tại sao phải hỏi đúng câu trước khi xem coverage

Giả sử nhóm sửa quy tắc phí vận chuyển:

- Khách `STANDARD` miễn phí từ **500.000** đơn vị tiền nhỏ nhất trở lên.
- Khách `PREMIUM` miễn phí từ **300.000** trở lên.
- Đơn thấp hơn ngưỡng tương ứng chịu phí **30.000**.
- Tổng tiền hàng âm là đầu vào sai.
- Đây là ví dụ giả định cho một phép tính thuần túy; chưa có database, thanh toán hay chính sách thay đổi theo thời gian.

### 7.1. Phiên bản có lỗi ở đúng ngưỡng

~~~java
import java.util.Objects;

enum CustomerTier {
    STANDARD, PREMIUM
}

final class ShippingFeePolicy {
    private ShippingFeePolicy() {}

    static long fee(long subtotalCents, CustomerTier tier) {
        if (subtotalCents < 0) {
            throw new IllegalArgumentException("Negative subtotal");
        }
        Objects.requireNonNull(tier, "tier");

        long freeFrom = tier == CustomerTier.PREMIUM ? 300_000 : 500_000;

        // BUG: đúng ngưỡng phải được miễn phí.
        return subtotalCents > freeFrom ? 0 : 30_000;
    }
}
~~~

Người viết có thể nói: “Chúng tôi cần chứng minh tất cả nhánh của hàm đều chạy qua.”

Đó là một **câu hỏi về độ bao phủ**, chứ chưa phải câu hỏi đầy đủ về **tính đúng của quy tắc**.

### 7.2. Test đi qua các nhánh nhưng vẫn để lọt lỗi

Với JUnit 5:

~~~java
import static org.junit.jupiter.api.Assertions.*;
import org.junit.jupiter.api.Test;

class ShippingFeePolicyTest {
    @Test
    void standardClearlyBelowAndAboveThreshold() {
        assertEquals(30_000,
                ShippingFeePolicy.fee(400_000, CustomerTier.STANDARD));
        assertEquals(0,
                ShippingFeePolicy.fee(600_000, CustomerTier.STANDARD));
    }

    @Test
    void premiumClearlyBelowAndAboveThreshold() {
        assertEquals(30_000,
                ShippingFeePolicy.fee(250_000, CustomerTier.PREMIUM));
        assertEquals(0,
                ShippingFeePolicy.fee(350_000, CustomerTier.PREMIUM));
    }

    @Test
    void rejectsNegativeSubtotal() {
        assertThrows(IllegalArgumentException.class,
                () -> ShippingFeePolicy.fee(-1, CustomerTier.STANDARD));
    }
}
~~~

Trong mô hình nguồn đơn giản, các test trên đưa điều kiện âm, lựa chọn hạng khách hàng và điều kiện phí qua những kết quả cần thiết để thực thi cả hai hướng. Một báo cáo *branch coverage* có thể rất cao, thậm chí đạt 100% cho những nhánh được công cụ tính trong hàm.

**Nhưng cả bộ test vẫn đỗ dù hàm sai ở đúng ngưỡng.** Điều này không mâu thuẫn với coverage: chỉ số đo nhánh được thực thi, không đo việc mọi giá trị trong nhánh có trả đúng hay không. Chi tiết phần trăm còn phụ thuộc cách công cụ Java đếm bytecode/nhánh, nên cần đọc đúng định nghĩa của công cụ.

### 7.3. Đổi câu hỏi, ta chọn bằng chứng khác

Câu hỏi tốt hơn:

> “Hàm có thực hiện đúng quy tắc **từ ngưỡng trở lên** cho từng hạng khách hàng không?”

Khi ấy, test cần kiểm tra giá trị biên:

~~~java
@Test
void standardAtExactThresholdMustBeFree() {
    assertEquals(0,
            ShippingFeePolicy.fee(500_000, CustomerTier.STANDARD));
}

@Test
void premiumAtExactThresholdMustBeFree() {
    assertEquals(0,
            ShippingFeePolicy.fee(300_000, CustomerTier.PREMIUM));
}
~~~

Hai test này **thất bại ở phiên bản có lỗi**, dù tập test cũ đã kiểm tra cả hướng phí bằng 0 và bằng 30.000. Sửa đúng yêu cầu:

~~~java
// Trong ShippingFeePolicy.fee:
return subtotalCents >= freeFrom ? 0 : 30_000;
~~~

Bằng chứng có giá trị ở đây gồm:

1. Đặc tả nói rõ “từ ngưỡng trở lên”.
2. Test ở đúng 500.000 và 300.000 phát hiện điều kiện sai.
3. Test dưới và trên ngưỡng bảo vệ hai hướng.
4. Coverage giúp kiểm tra những nhánh mới chưa được đi qua, nhưng không thay thế việc chọn giá trị biên.

### 7.4. Cùng một hàm, những câu hỏi khác nhau

| Câu hỏi | Chỉ số/bằng chứng phù hợp | Điều không thể kết luận từ một chỉ số |
| --- | --- | --- |
| Các hướng rẽ trong `fee` đã được test chạy qua chưa? | Branch coverage của hàm và danh sách test. | Ngưỡng 300.000 hoặc 500.000 đã đúng. |
| Khi sửa chính sách, có phát sinh lỗi giá trị biên không? | Test biên, review oracle, lịch sử bug liên quan. | Coverage cao chắc chắn ngăn hết lỗi. |
| Hàm có tốn nhiều CPU ở production không? | Profiling và thời gian xử lý trong bối cảnh tải thực. | Hàm ngắn thì chắc chắn nhanh. |
| Client nhận đúng phí từ API không? | Contract/integration test, dữ liệu khách hàng và chính sách thực. | Unit test của hàm đủ bảo đảm tích hợp. |
| Người mới có sửa chính sách này dễ không? | Review theo tác vụ, thời gian tìm nơi sửa, đánh giá đặt tên/hợp đồng. | Ít dòng mã tự động đồng nghĩa dễ thay đổi. |

**Bài học của ví dụ:** câu hỏi quyết định chúng ta cần loại bằng chứng nào. Không có một tỷ lệ coverage duy nhất thay thế được mọi câu hỏi về chất lượng.

## 8. Từ câu hỏi đến định nghĩa chỉ số có thể tái lập

Sau khi chọn chỉ số, bước tiếp theo là mô tả đủ rõ để hai người đo lại có cùng cách hiểu.

Một đặc tả đo lường nên gồm:

- **Tên và mục đích:** chỉ số trả lời câu hỏi nào?
- **Đơn vị:** %, số lần, mili giây, số ngày, lỗi trên một đơn vị khối lượng?
- **Tử số và mẫu số:** những trường hợp nào được đếm và loại trừ?
- **Đối tượng và phạm vi:** module, endpoint, dịch vụ, PR hay toàn sản phẩm?
- **Khoảng thời gian:** mỗi lần build, tuần, tháng, trước/sau phát hành?
- **Nguồn dữ liệu:** công cụ CI, issue tracker, telemetry, logs, kết quả review?
- **Điều kiện so sánh:** cấu hình, loại tải, môi trường, phiên bản và phân bố dữ liệu?
- **Giới hạn:** những gì chỉ số không thể cho biết?
- **Hành động dự kiến:** khi tăng/giảm/bất thường, nhóm sẽ điều tra hoặc thay đổi gì?

### 8.1. Ví dụ: định nghĩa branch coverage của mã thay đổi

Giả sử mục tiêu là tìm những nhánh nghiệp vụ mới chưa được thực thi:

~~~text
Tên: Branch coverage của mã thay đổi
Đối tượng: Các nhánh do công cụ tính trong phần mã Java thay đổi của PR
Tử số: Những nhánh thuộc phạm vi đó đã được test chạy qua
Mẫu số: Tổng số nhánh thuộc phạm vi đo sau khi áp dụng quy tắc lọc
Thời điểm: Build CI của commit được review
Nguồn: Báo cáo từ công cụ coverage đang được cấu hình
Hành động: Review từng nhánh chưa chạy; bổ sung test có assertion
           hoặc giải thích vì sao không cần/không thể kích hoạt
Giới hạn: Không đo oracle, giá trị biên, lỗi tích hợp hay tính đúng đắn tổng quát
~~~

Bản định nghĩa này vẫn phải phù hợp với **cách công cụ hỗ trợ diff coverage thật sự**. Không nên tự nhận đã đo một chỉ số nếu pipeline chỉ cung cấp line coverage toàn repository.

### 8.2. Ví dụ: tỷ lệ test không ổn định

Định nghĩa có thể là:

\[
\text{Tỷ lệ lần chạy không ổn định} =
\frac{\text{Số lần test thất bại rồi đỗ lại mà không đổi mã liên quan}}
{\text{Số lần chạy test thuộc tập quan sát}}
\times 100\%
\]

Công thức này chỉ là **một định nghĩa vận hành minh họa**. Nhóm khác có thể đo theo *test case* chứ không theo lần chạy, hoặc dùng nhiều lượt lặp trong môi trường được kiểm soát.

Muốn kết luận test flaky, cần cân nhắc thay đổi môi trường, hạ tầng và dữ liệu test; một lần chạy lại đỗ chưa đủ chứng minh lỗi không phải ở sản phẩm. Nếu không làm rõ cách đếm, “flaky rate 2%” rất dễ bị hiểu sai.

### 8.3. Ví dụ: tỷ lệ thay đổi gây sự cố

Một phép đo có thể là số lần triển khai trong khoảng thời gian xác định cần rollback, hotfix hoặc khôi phục vì lỗi liên quan, chia cho tổng số lần triển khai thuộc phạm vi ấy.

Nhưng phải làm rõ:

- “Một lần triển khai” được xác định ở cấp dịch vụ hay toàn hệ thống?
- Sự cố nào được tính là do thay đổi này?
- Một sự cố ảnh hưởng nhiều lần triển khai được đếm ra sao?
- Hotfix theo kế hoạch có được tính không?
- Có cùng cách ghi nhận giữa các giai đoạn hoặc đội không?

**Mẫu số và quy tắc phân loại quan trọng không kém tử số.**

## 9. Đo đúng phạm vi trước khi so sánh

Một số liệu thiếu phạm vi dễ dẫn đến kết luận sai. “Lỗi giảm 30%” có thể chỉ là lượng người dùng giảm, phạm vi báo cáo thu hẹp hoặc cách phân loại đã đổi.

### 9.1. So sánh cùng đối tượng và cùng điều kiện

Ví dụ, hai module Java có đặc điểm khác nhau:

- Module A thực hiện phép tính thuần túy, dễ tạo test nhiều trường hợp.
- Module B điều phối database và API bên ngoài, có nhiều đường lỗi hạ tầng.

Nếu A có 95% line coverage và B có 75%, không đủ căn cứ kết luận B có chất lượng kém hơn. Cần xác định **câu hỏi, mức rủi ro, phạm vi và loại test** của từng module.

Tương tự, so sánh độ trễ p95 trước–sau khi số lượng request, kích thước dữ liệu hoặc tỷ lệ endpoint thay đổi có thể che nguyên nhân.

### 9.2. Mẫu số khác nhau tạo ấn tượng khác nhau

Giả sử trong hai tuần minh họa:

| Tuần | Lỗi được báo | Lượt xử lý | Lỗi trên 10.000 lượt xử lý |
| --- | ---: | ---: | ---: |
| A | 20 | 100.000 | 2 |
| B | 30 | 300.000 | 1 |

Số lỗi tuyệt đối tăng từ 20 lên 30, nhưng tỷ lệ trên lượng xử lý giảm từ 2 xuống 1 trên 10.000 lượt. Hai kết luận này **không mâu thuẫn**: chúng trả lời những câu hỏi khác nhau.

Dù vậy, “lượt xử lý” có thể không phải mẫu số đúng cho mọi lỗi. Nếu mỗi người dùng có khả năng báo lỗi khác nhau hoặc có thay đổi cách thu thập, còn cần điều tra thêm.

### 9.3. Tránh gộp những nhóm không tương đồng

Một p95 cho toàn bộ API có thể che việc endpoint thanh toán chậm đi trong khi endpoint đọc danh mục được gọi nhiều hơn và nhanh hơn. Có thể cần phân tách theo endpoint, loại tải, vùng hoặc phiên bản — với điều kiện việc phân tách phù hợp và không tạo dữ liệu nhạy cảm không cần thiết.

Khi gộp dữ liệu nhiều nhóm, những thay đổi về tỷ trọng nhóm có thể làm xu hướng tổng khác với xu hướng từng nhóm. Vì vậy, trước khi so sánh, hãy đặt câu hỏi: **“Chúng ta đang đo cùng một tập đối tượng theo thời gian hay không?”**

## 10. Độ biến động, cỡ mẫu và độ tin cậy

Dữ liệu nhỏ có thể khiến phần trăm dao động mạnh.

Giả sử một dịch vụ có 5 lần phát hành trong tháng và 1 lần cần rollback: tỷ lệ tính đơn giản là 20%. Tháng sau có 4 lần phát hành và không rollback: tỷ lệ là 0%. Ta **chưa thể khẳng định quy trình đã cải thiện bền vững** chỉ dựa trên hai mẫu nhỏ ấy.

Khi đọc chỉ số, cần chú ý:

1. **Số lượng quan sát thực tế:** bao nhiêu PR, build, request, sự cố?
2. **Phân bố dữ liệu:** trung bình có bị vài giá trị cực đoan kéo lệch không?
3. **Biến động tự nhiên:** chỉ số thường dao động bao nhiêu khi không đổi quy trình?
4. **Thay đổi nguồn dữ liệu:** có cập nhật công cụ, bộ lọc hoặc định nghĩa không?
5. **Ảnh hưởng của mùa vụ và tải:** chiến dịch, đợt phát hành lớn, kỳ nghỉ?
6. **Khoảng thời gian quan sát:** đủ dài để thấy xu hướng nhưng còn liên quan tới quyết định hiện tại không?

Không cần biến mọi dashboard thành nghiên cứu thống kê phức tạp. Nhưng việc ghi **mẫu số, thời gian và mức biến động** giúp tránh các kết luận tự tin quá mức.

### 10.1. Số trung bình và phân vị phục vụ mục tiêu khác nhau

Khi nghiên cứu độ trễ:

- **Trung bình** giúp hình dung chi phí bình quân trong điều kiện mẫu.
- **p50** mô tả giá trị trung vị.
- **p95/p99** giúp chú ý tới những yêu cầu chậm ở phần đuôi phân bố.

Nếu mục tiêu là người dùng không phải chờ quá lâu trong phần lớn request, p95 có thể phù hợp hơn trung bình. Nhưng p95 cũng cần **đủ quan sát và cách nhóm dữ liệu hợp lý**; từ ít request không thể đưa ra kết luận chắc chắn về phần đuôi.

### 10.2. Tương quan không tự chỉ ra nguyên nhân

Nếu coverage tăng và số lỗi production giảm trong cùng quý, đó là tín hiệu đáng mừng nhưng chưa chứng minh coverage tăng **gây ra** việc giảm lỗi. Có thể cùng lúc đội đã giảm phạm vi thay đổi, nâng chất lượng review, sửa kiến trúc hoặc lượng người dùng đổi.

Muốn quyết định đầu tư tiếp, cần tìm cơ chế hợp lý: những test mới đã bắt được loại lỗi nào, những lỗi nào trước đây lọt qua và liệu thay đổi quy trình thực sự tác động ra sao.

## 11. Chỉ số dẫn dắt và chỉ số kết quả

Một số chỉ số mô tả **hành động hoặc điều kiện sớm**, một số khác mô tả **kết quả đã xảy ra**.

| Nhóm | Ví dụ | Hữu ích vì | Giới hạn |
| --- | --- | --- | --- |
| **Dẫn dắt (leading)** | Nhánh rủi ro có test, kiểm thử bảo vệ bất biến, thời gian chờ review. | Có thể hành động trước khi sự cố xảy ra. | Chưa chắc dự báo kết quả nếu giả định sai. |
| **Kết quả (lagging)** | Lỗi nghiêm trọng tới người dùng, số lần rollback, thời gian khôi phục. | Gắn với tác động thực tế. | Thường xuất hiện muộn và chịu nhiều yếu tố bên ngoài. |

Không phải lúc nào một chỉ số cũng thuộc cố định một nhóm. Thời gian review có thể là kết quả của một quy trình, đồng thời là dấu hiệu sớm của chậm phát hành.

**Kết hợp hữu ích:** dùng chỉ số kết quả để biết có đạt mục tiêu không, dùng bằng chứng dẫn dắt để nhận biết **những thực hành cụ thể cần cải thiện**. Không coi leading metric là mục tiêu cuối cùng.

## 12. Chọn một tập tín hiệu cân bằng thay vì một con số duy nhất

Một câu hỏi lớn về chất lượng thường cần nhiều góc nhìn.

Ví dụ mục tiêu:

> “Trong ba tháng tới, thay đổi chính sách giá phải an toàn hơn mà không làm quá trình sửa mã chậm và khó hiểu hơn.”

Có thể chọn ba nhóm bằng chứng:

| Góc nhìn | Chỉ số/tín hiệu có thể dùng | Cách diễn giải |
| --- | --- | --- |
| **Tính đúng đắn** | Số sai lệch giá nghiêm trọng lọt tới production; test các giá trị biên quan trọng. | Lỗi thực tế có giảm không; các quy tắc có được bảo vệ không? |
| **Khả năng thay đổi** | Thời gian hoàn thành thay đổi tương đương; số nơi phải sửa cho một quy tắc. | Việc sửa chính sách có dễ hơn hay đang tăng coupling? |
| **Khả năng kiểm chứng** | Nhánh của mã thay đổi đã được chạy; review oracle; test hồi quy. | Có phát hiện khoảng trống test và kiểm tra kết quả đúng không? |

Nếu sau thay đổi thời gian giao hàng nhanh hơn nhưng số sai lệch giá tăng, không thể gọi đó là thành công toàn diện. Nếu coverage tăng nhưng mỗi yêu cầu phải sửa ở sáu module, có thể cấu trúc đang khó bảo trì hơn.

### 12.1. Chỉ số đối trọng (*guardrail metric*)

Khi tối ưu một mục tiêu, nên theo dõi những điều **không được xấu đi**.

Ví dụ:

- Tăng throughput → theo dõi tỷ lệ lỗi, độ trễ phần đuôi, bộ nhớ.
- Giảm thời gian review → theo dõi sự cố sau triển khai và chất lượng kiểm tra rủi ro.
- Tăng coverage → theo dõi test flaky, chất lượng assertion và thời gian CI.
- Giảm LOC → theo dõi số helper, mức coupling và thời gian tìm hiểu logic.

Guardrail không phải bảo đảm tuyệt đối. Nó giúp nhận diện **tác dụng phụ của việc tối ưu một con số**.

## 13. Rủi ro Goodhart: khi chỉ số trở thành mục tiêu hình thức

Một ý tưởng thường được tóm tắt là: **khi một phép đo bị biến thành mục tiêu, nó có thể mất khả năng đại diện tốt cho điều ban đầu muốn đo**.

Trong phát triển phần mềm, điều này có thể xuất hiện dưới nhiều dạng:

### 13.1. Coverage thành mục tiêu

Nếu chỉ yêu cầu 90% coverage, nhóm có thể thêm test chỉ gọi phương thức hoặc kiểm tra `assertNotNull` cho kết quả phức tạp. Coverage tăng nhưng lỗi nghiệp vụ vẫn không bị phát hiện.

**Cách giảm rủi ro:** review những tình huống quan trọng, assertion và oracle; dùng coverage để tìm khoảng trống thực thi, không làm chỉ tiêu duy nhất.

### 13.2. Số lượng bug thành mục tiêu

Nếu một nhóm bị đánh giá bằng “số bug càng ít càng tốt”, họ có thể phân loại lại vấn đề, trì hoãn ghi nhận hoặc không khuyến khích báo lỗi. Dữ liệu trở nên không đáng tin dù chất lượng thực không cải thiện.

**Cách giảm rủi ro:** khuyến khích ghi nhận trung thực, phân biệt mức nghiêm trọng, theo dõi tác động tới người dùng và nguyên nhân gốc.

### 13.3. Tốc độ giao hàng thành mục tiêu

Nếu đo số commit hoặc số PR được đóng, nhóm có thể chia thay đổi nhỏ một cách thiếu ý nghĩa hoặc ưu tiên số lượng hơn kiểm thử. Một nhiệm vụ phức tạp nhưng giá trị lớn có thể trông “kém năng suất”.

**Cách giảm rủi ro:** đo khả năng hoàn thành thay đổi có giá trị và an toàn ở mức **quy trình/nhóm**, kết hợp chất lượng, độ ổn định và phản hồi thực tế.

### 13.4. Điểm complexity thành mục tiêu

Nếu đặt giới hạn cứng cho mọi hàm, người viết có thể tách các nhánh thành helper rời rạc, làm điểm từng hàm đẹp hơn nhưng buộc người bảo trì mở nhiều file để hiểu một quy tắc.

**Cách giảm rủi ro:** dùng chỉ số như một tín hiệu review; xem xét trách nhiệm, tính gắn kết và chi phí điều hướng.

**Nguyên tắc:** không tạo động cơ che giấu vấn đề để làm đẹp số. Khi chỉ số đã làm thay đổi hành vi của nhóm, cần **đánh giá lại chính chỉ số ấy**.

## 14. Không dùng chỉ số kỹ thuật để xếp hạng cá nhân một cách máy móc

Các phép đo như số commit, số dòng thêm/xóa, số lỗi tìm thấy, số comment review hay thời gian xử lý PR thường bị ảnh hưởng mạnh bởi:

- Độ khó và mức rủi ro của nhiệm vụ.
- Vai trò đang đảm nhiệm: hỗ trợ người khác, review, vận hành, thiết kế.
- Kiến trúc và tuổi đời của hệ thống.
- Các phụ thuộc hoặc chờ quyết định bên ngoài.
- Mức độ ghi nhận và cách chia nhỏ công việc.

Vì vậy, chúng **không phải thước đo khách quan trực tiếp** về năng lực hay đóng góp của một cá nhân. Nếu dùng sai, chúng có thể khuyến khích bỏ việc khó, tăng số lượng hoạt động không cần thiết hoặc che giấu sự cố.

Với mục tiêu nâng chất lượng mã, nên ưu tiên phân tích **điều kiện của hệ thống và quy trình**: rào cản nào khiến review chậm, chỗ nào thiếu test, phần nào thay đổi thường làm lỗi, tài liệu nào chưa rõ. Phỏng vấn và trao đổi với người trực tiếp làm việc là bằng chứng quan trọng bên cạnh dữ liệu định lượng.

## 15. Thiết kế dashboard và quality gate đúng vai trò

Một dashboard nên giúp người xem **trả lời câu hỏi và quyết định hành động**, không chỉ hiển thị nhiều biểu đồ.

### 15.1. Bắt đầu với một câu hỏi trên mỗi nhóm biểu đồ

Ví dụ dashboard chất lượng cho module tính giá:

- Câu hỏi: “Các thay đổi gần đây có làm tăng lỗi tính giá tới người dùng không?”
- Tín hiệu: sự cố liên quan theo mức nghiêm trọng và phiên bản, có ghi mẫu số/tải khi phù hợp.
- Diễn giải: chỉ xem xu hướng trong những khoảng thời gian có cách ghi nhận tương đồng.
- Hành động: điều tra loại thay đổi gây lỗi, cập nhật test/đặc tả hoặc thay đổi ranh giới thiết kế.

Một biểu đồ chỉ ghi “quality score: 87” mà không có cách tính hoặc ý nghĩa hành động thường ít hữu ích.

### 15.2. Quality gate nên chặn điều gì?

Một *quality gate* là quy tắc yêu cầu kiểm tra hoặc đạt điều kiện trước khi tiếp tục một bước, chẳng hạn merge hay deploy. Một số điều kiện có thể chặn trực tiếp khi cần: build thất bại, test bắt buộc thất bại, vi phạm quy tắc bảo mật quan trọng đã xác định.

Với coverage hoặc complexity, cần cân nhắc ngữ cảnh:

- Nhánh chưa được test có thuộc hành vi rủi ro cao không?
- Test có thể tạo tình huống đó bằng cách hợp lý không?
- Một phần mã được sinh có cần loại trừ theo quy tắc minh bạch không?
- Có cơ chế ngoại lệ được review và ghi lý do không?
- Chỉ số có khuyến khích thêm test có ý nghĩa hay chỉ thúc đẩy “bôi xanh”?

Quality gate tốt giúp phát hiện rủi ro và thúc đẩy cải thiện. Nó không nên trở thành cớ **làm yếu test hoặc xóa cảnh báo** để qua ngưỡng.

### 15.3. Một bản ghi đo lường ngắn có thể đủ hơn dashboard lớn

Ở giai đoạn đầu, nhóm có thể dùng một bảng nhỏ:

| Câu hỏi | Bằng chứng hiện có | Khoảng trống | Hành động tiếp theo |
| --- | --- | --- | --- |
| Phí vận chuyển đúng tại ngưỡng? | Test 400.000 và 600.000. | Thiếu đúng ngưỡng từng hạng. | Thêm test 300.000, 500.000. |
| Nhánh mới đã chạy? | Báo cáo branch coverage của PR. | Một đường lỗi chưa chạy. | Tạo ca lỗi phù hợp. |
| Việc sửa chính sách có bị phân tán? | Review diff của ba PR gần nhất. | Hai nơi lặp điều kiện hạng. | Xem lại nguồn sở hữu quy tắc. |

Khi câu hỏi và dữ liệu đủ ổn định, mới có cơ sở để tự động hóa hoặc đưa lên dashboard.

## 16. Quy trình bảy bước để chọn chỉ số trong công việc

**Bước 1 — Nói rõ vấn đề.** Viết một câu về rủi ro, chi phí hoặc trải nghiệm đang muốn cải thiện. Tránh bắt đầu bằng ngưỡng phần trăm.

**Bước 2 — Chọn quyết định.** Ai sẽ hành động và họ có những phương án nào? Ví dụ: thêm test, sửa hợp đồng, tách thành phần hay điều chỉnh pipeline.

**Bước 3 — Viết câu hỏi có thể trả lời.** Xác định đối tượng, thuộc tính, khoảng thời gian, bối cảnh và hành động. Nếu chưa hiểu nguyên nhân, cho phép câu hỏi đầu tiên là câu hỏi khám phá.

**Bước 4 — Chọn bằng chứng nhỏ nhất đủ hữu ích.** Có thể chỉ cần review vài PR và test ở giá trị biên, không cần xây dashboard mới. Khi có nhu cầu quan sát lặp lại, chọn chỉ số định lượng phù hợp.

**Bước 5 — Định nghĩa phép đo.** Chỉ rõ tử số, mẫu số, đơn vị, công cụ, phạm vi, điều kiện loại trừ và cách phân loại sự kiện.

**Bước 6 — Kiểm tra giới hạn và tín hiệu đối trọng.** Dữ liệu có đủ đại diện không? Có động cơ làm đẹp số không? Chỉ số nào cảnh báo hậu quả ngoài ý muốn?

**Bước 7 — Dùng kết quả và xem lại câu hỏi.** Ghi nhận hành động đã làm, kiểm tra tác động và dừng hoặc thay chỉ số khi nó không còn giúp đưa ra quyết định.

### 16.1. Mẫu kế hoạch đo lường có thể dùng trong PR hoặc buổi review

~~~text
MỤC TIÊU
Giảm nguy cơ hồi quy ở các quy tắc tính phí khi thay đổi chính sách.

CÂU HỎI
Các nhánh mới và các ngưỡng nghiệp vụ quan trọng đã có test kiểm tra chưa?

ĐỐI TƯỢNG / THỜI GIAN
Các thay đổi của module báo giá trong những PR được review ở đợt hiện tại.

BẰNG CHỨNG
- Test cho đúng ngưỡng, sát dưới/sát trên và dữ liệu không hợp lệ.
- Branch coverage của mã bị thay đổi nếu pipeline có hỗ trợ.
- Review oracle dựa trên yêu cầu đã xác nhận.

GIỚI HẠN
Coverage không chứng minh kết quả đúng.
Test đơn vị không kiểm tra giao dịch hay cấu hình production.

HÀNH ĐỘNG
Thêm test có assertion cho nhánh/tình huống quan trọng còn thiếu;
điều tra riêng những thiếu sót thuộc hợp đồng hoặc tích hợp.

TÍN HIỆU ĐỐI TRỌNG
Test flaky, thời gian CI, số lỗi giá sau deploy, chi phí sửa chính sách.

KIỂM TRA LẠI
Sau một chu kỳ thay đổi, xem test mới có bắt được sai lệch có ý nghĩa không.
~~~

Đây là **mẫu minh họa**, không phải số đo đã được thực hiện. Mỗi nhóm cần thay bằng dữ liệu thật và điều kiện phù hợp.

## 17. Tình huống thực tế: dashboard đẹp nhưng lỗi production vẫn tăng

Một nhóm phát triển Java báo cáo:

- Line coverage của repository tăng từ 78% lên 91%.
- Trung bình số dòng mỗi phương thức giảm.
- Số PR merge mỗi tuần tăng.

Tuy nhiên, trong cùng giai đoạn, người dùng vẫn gặp lỗi tính giá ở các chiến dịch mới, và một số sự cố cần rollback.

### 17.1. Câu hỏi sai có thể đã dẫn đến những việc sai

Nếu câu hỏi ban đầu là “làm sao tăng điểm coverage và giảm LOC?”, nhóm có thể tối ưu đúng các con số ấy mà chưa đụng đến nguyên nhân của lỗi tính giá.

Các giả thuyết đáng kiểm tra:

- Test đã chạy qua mã nhưng assertion không kiểm tra ngưỡng đúng.
- Quy tắc chính sách bị sao chép ở nhiều service và sửa thiếu một nơi.
- Cấu hình chiến dịch được đọc khác nhau giữa các instance.
- Test chỉ dùng dữ liệu thông thường, thiếu điều kiện lỗi và tương tác.
- Quy trình triển khai không kiểm tra các trường hợp tích hợp quan trọng.

Đây là **những khả năng cần điều tra**, không thể kết luận nguyên nhân chỉ từ ba chỉ số đầu.

### 17.2. Viết lại bộ câu hỏi

1. Những lỗi giá nào thực sự tới người dùng, tác động theo mức nghiêm trọng ra sao?
2. Lỗi xuất phát từ quy tắc sai, cấu hình sai, dữ liệu, tích hợp hay lịch thực thi đồng thời?
3. Test nào lẽ ra phải phát hiện lỗi đó; vì sao không phát hiện?
4. Muốn sửa một thay đổi chính sách, cần chỉnh bao nhiêu nguồn quy tắc và hợp đồng?
5. Sau khi thay đổi quy trình, loại lỗi tương tự có còn tái diễn không?

Các câu hỏi dẫn đến **bằng chứng hành động được**: phân tích sự cố, test biên, kiểm thử hợp đồng, xem ownership và lịch sử thay đổi. Coverage và complexity vẫn có giá trị, nhưng là **những mảnh ghép**.

### 17.3. Tiêu chí cải thiện hợp lý hơn

Thay vì hứa “mọi chỉ số đều tăng”, nhóm có thể xác định:

- Những loại lỗi giá nghiêm trọng được tìm và chặn sớm hơn.
- Các quy tắc quan trọng có ví dụ/test thể hiện rõ hợp đồng.
- Những thay đổi tương đương dễ tìm nơi sửa và không phải đồng bộ nhiều bản sao.
- Tốc độ giao hàng không đạt được bằng cách bỏ qua kiểm chứng quan trọng.

Cần đo lại sau các đợt thay đổi và ghi rõ phạm vi kết luận. Đó là cách chuyển dashboard từ bảng điểm sang công cụ học hỏi.

## 18. Bài tập tự đánh giá

### Tình huống A: một ngưỡng coverage

Nhóm muốn đặt quy định “mọi class Java phải có 95% line coverage” vì gần đây hệ thống có lỗi phân quyền.

**Câu hỏi:** bạn nên hỏi điều gì trước khi chấp nhận quy định ấy?

**Gợi ý:** lỗi phân quyền xuất hiện ở ranh giới nào, test đã kiểm tra vai trò/quyền và trạng thái chưa, line coverage có phát hiện logic bị thiếu không, cần test tích hợp security nào, và ngưỡng mới sẽ ảnh hưởng như thế nào đến cách viết test?

### Tình huống B: review nhanh hơn

Dashboard cho thấy thời gian trung bình từ mở PR đến merge giảm một nửa.

**Câu hỏi:** có thể kết luận mã dễ thay đổi hơn chưa?

**Gợi ý:** chưa. Cần xem loại PR, kích thước và rủi ro, thời gian chờ CI, chất lượng review và sự cố sau merge. Có thể thời gian giảm vì nhóm chia PR tốt hơn, nhưng cũng có thể vì bỏ bớt bước kiểm tra.

### Tình huống C: phương thức ít dòng hơn

Một refactor chuyển phương thức 100 dòng thành mười phương thức 10 dòng. Điểm complexity của phương thức đầu giảm.

**Câu hỏi:** câu hỏi chất lượng thực sự là gì, và cần thêm bằng chứng gì?

**Gợi ý:** người bảo trì có dễ hiểu hành vi hơn, có ít trạng thái ngầm hơn và tìm đúng nơi sửa nhanh hơn không? Review đồ thị lời gọi, trách nhiệm, trạng thái, test hồi quy và các thay đổi tiếp theo; không chỉ xem điểm từng hàm.

### Tình huống D: số lỗi tăng

Sau một đợt marketing lớn, lỗi được báo tăng từ 10 lên 25 mỗi tuần.

**Câu hỏi:** thiếu thông tin nào trước khi nói chất lượng kém đi?

**Gợi ý:** số người dùng, số giao dịch, mức nghiêm trọng, loại lỗi, cách ghi nhận và so sánh trong điều kiện tương đồng. Lỗi tuyệt đối có thể tăng cùng lượng sử dụng trong khi tỷ lệ lỗi giảm.

### Tình huống E: chọn thước đo độ trễ

Người dùng phản ánh đôi lúc trang thanh toán mất rất lâu, nhưng độ trễ trung bình vẫn tốt.

**Câu hỏi:** nên đặt lại câu hỏi và phép đo ra sao?

**Gợi ý:** tập trung vào trải nghiệm ở phần đuôi phân bố theo endpoint thanh toán, mẫu tải và giai đoạn cụ thể; xem p95/p99, trace, phụ thuộc ngoài và tỷ lệ lỗi. Không cần ưu tiên CPU của một helper Java nếu nghẽn ở database hoặc mạng.

## 19. Checklist trước khi đưa chỉ số vào báo cáo hoặc quality gate

- [ ] Tôi có một **mục tiêu chất lượng** gắn với rủi ro hoặc nhu cầu thực tế.
- [ ] Tôi có **câu hỏi cụ thể** cần được trả lời trước khi chọn phép đo.
- [ ] Tôi biết **ai sẽ dùng kết quả và quyết định điều gì**.
- [ ] Chỉ số được chọn thực sự đo một phần liên quan của câu hỏi đó.
- [ ] Tử số, mẫu số, đơn vị, phạm vi và khoảng thời gian được định nghĩa rõ.
- [ ] Nguồn dữ liệu và cấu hình đo có thể được kiểm tra hoặc tái lập.
- [ ] Các nhóm/dữ liệu được so sánh có đủ tương đồng về bối cảnh.
- [ ] Tôi không diễn giải coverage, LOC hay complexity thành kết luận “mã đúng” hoặc “mã tốt” tuyệt đối.
- [ ] Có bằng chứng định tính hoặc kiểm thử bổ sung khi chỉ số không phản ánh ngữ nghĩa.
- [ ] Tôi đã xem cỡ mẫu, biến động và những thay đổi trong cách thu thập.
- [ ] Tôi biết những hành vi có thể bị khuyến khích sai khi biến chỉ số thành mục tiêu.
- [ ] Có chỉ số đối trọng khi tối ưu tốc độ, coverage hoặc quy mô mã.
- [ ] Quality gate có thể giải thích bằng rủi ro, không chỉ là một phần trăm tùy ý.
- [ ] Phép đo không bị dùng máy móc để xếp hạng cá nhân hoặc che giấu vấn đề.
- [ ] Kết quả dẫn tới hành động có thể kiểm chứng và được đánh giá lại.
- [ ] Khi câu hỏi đã đổi, tôi sẵn sàng bỏ hoặc thay chỉ số không còn hữu ích.

## 20. Kết luận

**Chỉ số chất lượng chỉ có giá trị trong mối liên hệ với câu hỏi mà nó được dùng để trả lời.** Một con số có thể chính xác về mặt tính toán mà vẫn ít hữu ích, hoặc gây hiểu sai, nếu thiếu phạm vi, mục đích, mẫu số và giới hạn diễn giải.

Trong **CODE_QUALITY_FUNDAMENTALS**, hãy bắt đầu bằng mục tiêu như “giảm hồi quy tính tiền”, “giúp người khác sửa mã an toàn” hoặc “giảm độ trễ của một luồng người dùng cụ thể”. Từ đó xác định **quyết định cần hỗ trợ**, đặt câu hỏi có thể kiểm chứng, chọn bằng chứng phù hợp và xây dựng chỉ số có định nghĩa rõ ràng.

Coverage, complexity, lỗi production, thời gian thay đổi và độ trễ đều là **những góc nhìn**, không phải sự thật đầy đủ về chất lượng. Khi sử dụng chúng để **tìm vấn đề, kiểm tra giả thuyết và học từ kết quả**, thay vì chỉ tối đa hóa bảng điểm, đội ngũ sẽ có cơ sở tốt hơn để xây dựng mã nguồn **đáng tin cậy, dễ hiểu và dễ thay đổi**.

