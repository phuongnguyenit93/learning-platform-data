# Không dùng một chỉ số để xếp hạng cá nhân hoặc khẳng định nguyên nhân

> **Chương:** Chỉ số chất lượng  
> **Học phần:** Code Quality Fundamentals (`CODE_QUALITY_FUNDAMENTALS`) — hiểu những thuộc tính quyết định mã nguồn có đáng tin cậy, dễ hiểu và dễ thay đổi hay không.

## Mục tiêu học tập

Sau bài học này, bạn có thể:

1. Phân biệt **thuộc tính chất lượng**, **chỉ số đo**, **tín hiệu quan sát được** và **kết luận quản trị**.
2. Giải thích vì sao số dòng mã, số commit, số lỗi, tỷ lệ coverage, thời gian review hoặc số lần deploy **không đủ để xếp hạng năng lực hay đóng góp cá nhân**.
3. Nhận diện các sai lệch thường gặp: **khác độ khó công việc, mẫu số không tương đương, kích thước mẫu nhỏ, phân nhóm sai, thay đổi cách ghi nhận và động cơ tối ưu số đo**.
4. Phân biệt **tương quan**, **thứ tự thời gian**, **giả thuyết cơ chế** và **bằng chứng nhân quả**; biết khi nào một quan sát chỉ nên dẫn đến câu hỏi mới.
5. Đọc được ví dụ nghịch lý Simpson, kiểm tra tính đúng đắn của phép tổng hợp tỷ lệ và giải thích vì sao ngay cả phép tính đúng cũng có thể dẫn đến kết luận sai.
6. Thiết kế một bộ chỉ số bổ sung nhau để cải thiện chất lượng ở **cấp hệ thống/nhóm**, có mô tả mẫu số, nguồn dữ liệu, giới hạn và cách hành động.
7. Giao tiếp kết quả đo một cách có trách nhiệm, tôn trọng quyền riêng tư và tránh dùng dashboard như công cụ giám sát hay đánh giá nhân sự đơn giản hóa.

## 1. Một con số có thể chính xác nhưng kết luận vẫn sai

Giả sử một dashboard cho thấy trong tháng:

- Nhóm A có **86%** thay đổi được chấp nhận ở lần review đầu.
- Nhóm B có **75%** thay đổi được chấp nhận ở lần review đầu.

Có người kết luận: “Nhóm A viết mã tốt hơn; hãy xếp hạng kỹ sư dựa trên tỷ lệ này.”

Lập luận đó bỏ qua nhiều câu hỏi quan trọng:

- Hai nhóm có xử lý cùng **loại công việc** hay không?
- Thay đổi nhỏ và thay đổi phức tạp có cùng xác suất cần sửa sau review không?
- “Được chấp nhận” có phản ánh chất lượng hay chỉ phản ánh **mức nghiêm ngặt của reviewer**?
- Các lỗi thực tế sau phát hành, bảo mật, khả năng đọc và mức độ hữu ích với người dùng có được xem xét không?
- Số lượng mẫu, thời gian, dữ liệu thiếu và thay đổi quy trình có tương đương không?

Một con số có thể được tính toán **hoàn toàn chính xác từ dữ liệu đã ghi** nhưng vẫn là đại diện **không đầy đủ** cho điều ta muốn biết.

**Chỉ số (metric)** là phép đo được định nghĩa trên một loại hiện tượng; **chất lượng mã** là tập thuộc tính rộng hơn, bao gồm tính đúng đắn, độ tin cậy, khả năng đọc, bảo mật, khả năng thay đổi, hiệu năng và tài nguyên. Chỉ số không tự mang theo nguyên nhân hay phán xét về người tạo ra nó.

> **Chỉ số là tín hiệu để đặt câu hỏi và kiểm tra giả thuyết, không phải bản án về cá nhân hoặc bằng chứng nhân quả chỉ bằng một đồ thị.**

### Bốn cấp suy luận nên tách biệt

| Cấp | Phát biểu | Có thể kết luận gì? |
| --- | --- | --- |
| **Dữ liệu gốc** | Có 86 lần được chấp nhận trên 100 thay đổi | Có 86 sự kiện theo định nghĩa thu thập |
| **Chỉ số** | Tỷ lệ chấp nhận lần đầu là 86% | Một tỷ lệ trong phạm vi và kỳ đo đã định |
| **Diễn giải** | Nhóm này dường như ít phải chỉnh sửa sau review | Một giả thuyết, phụ thuộc độ khó và cách review |
| **Khẳng định nhân quả/đánh giá người** | Do kỹ sư giỏi hơn nên tỷ lệ cao hơn | **Chưa đủ bằng chứng** để khẳng định |

Việc bỏ qua hai bước ở giữa là một nguồn gây sai lệch phổ biến khi sử dụng quality metrics.

## 2. Đo đúng thứ gì trước khi chọn công cụ và KPI

Một chất lượng đáng quan tâm có thể có nhiều biểu hiện quan sát được. Trước khi mở dashboard, nên xác định:

1. **Mục tiêu:** cần giảm lỗi thanh toán, phát hiện hồi quy sớm, cải thiện khả năng khôi phục, hay giảm thời gian người mới hiểu code?
2. **Đơn vị phân tích:** một request, một PR, một lần triển khai, một incident, một mô-đun hay một nhóm?
3. **Định nghĩa phép đo:** mẫu số, tử số, khoảng thời gian, dữ liệu nào bị loại và cách xử lý thiếu dữ liệu.
4. **Nguồn dữ liệu:** CI, issue tracker, production telemetry, review system hay khảo sát có cấu trúc?
5. **Những yếu tố làm nhiễu:** độ khó, khối lượng thay đổi, phạm vi hệ thống, lịch trực, đặc điểm khách hàng, tuổi đời mã, cách ghi nhận sự kiện.
6. **Hành động định làm:** nếu chỉ số thay đổi, nhóm sẽ kiểm tra hoặc cải thiện gì?
7. **Tác động tới hành vi:** nếu biến chỉ số thành mục tiêu, người tham gia có thể tối ưu nó theo cách nào ngoài mong đợi?

Nếu không xác định được mục tiêu hoặc quyết định cần hỗ trợ, **chưa nên đo thêm chỉ vì có công cụ xuất biểu đồ đẹp**.

### Những thuộc tính khác nhau cần bằng chứng khác nhau

| Thuộc tính | Tín hiệu có thể hữu ích | Bằng chứng phải bổ sung |
| --- | --- | --- |
| **Tính đúng đắn** | Lỗi hồi quy, kiểm thử thất bại, kết quả đối soát | Đặc tả, test trường hợp biên, đối chiếu nghiệp vụ |
| **Độ tin cậy** | Tỷ lệ lỗi, thời gian gián đoạn, thời gian phục hồi | Mức độ nghiêm trọng, loại incident, kiến trúc và lưu lượng |
| **Khả năng đọc** | Thời gian hiểu một thay đổi, câu hỏi lặp lại trong review | Review định tính, khả năng giải thích hợp đồng và trách nhiệm |
| **Khả năng thay đổi** | Lead time, mức phụ thuộc khi sửa, tỷ lệ rework | Độ phức tạp thay đổi, chất lượng thiết kế và kiểm thử hồi quy |
| **Bảo mật** | Cảnh báo được xác minh, kiểm thử quyền, thời gian sửa lỗ hổng | Threat model, kiểm thử theo tài nguyên, phạm vi ảnh hưởng |
| **Hiệu năng** | Latency p95/p99, throughput, CPU, memory, tỷ lệ lỗi | Workload đại diện, profiling, baseline và tiêu chí người dùng |
| **Chất lượng kiểm thử** | Coverage, mutation score, flaky rate | Assertion có ý nghĩa, ranh giới tích hợp và test hồi quy trọng yếu |

Không có chỉ số duy nhất thay thế được toàn bộ bảng. Thậm chí cùng một metric như `lead time` có thể chịu ảnh hưởng của lịch phê duyệt, tổ chức release và độ khó dự án hơn là chỉ bởi cấu trúc mã.

## 3. Vì sao không nên xếp hạng cá nhân bằng một chỉ số?

### 3.1. Công việc khác nhau về rủi ro và độ khó

Một người sửa chính tả UI có thể hoàn tất nhiều PR nhỏ. Người khác xử lý một lỗi cạnh tranh giao dịch hiếm, cần nhiều ngày thiết kế, thử nghiệm, đối soát và phối hợp với đối tác.

Nếu chỉ đếm PR/commit, người thứ nhất có thể có số cao hơn mà **không có nghĩa đóng góp lớn hơn hoặc mã đáng tin cậy hơn**.

Tương tự, số lỗi được giao xử lý phụ thuộc vào việc ai sở hữu code cũ nhiều vấn đề, ai trực on-call, mức sử dụng tính năng và thói quen báo lỗi. Không thể suy “nhiều bug gắn với tên X” thành “X viết code kém”.

### 3.2. Nhiều công việc quan trọng không xuất hiện trong thống kê code

Các đóng góp như review tìm ra lỗi bảo mật, hỗ trợ đồng nghiệp, đơn giản hóa đặc tả, cải thiện test infrastructure, làm rõ API contract, viết hướng dẫn onboarding hoặc ngăn sự cố trước khi merge có thể không tạo nhiều dòng mã.

Đếm đầu ra dễ đo có thể khiến nhóm **giảm động lực làm công việc khó đo nhưng giá trị cao**.

### 3.3. Chỉ số bị thay đổi bởi cách tổ chức công việc

Độ dài PR và số comment review chịu ảnh hưởng của quy ước chia PR, cặp reviewer, thời gian phản hồi và mức độ trao đổi. Tỷ lệ deploy thành công chịu ảnh hưởng hạ tầng, quyền phát hành và quy trình rollback; không thể quy về một cá nhân.

**Lựa chọn của tổ chức cũng là một nguyên nhân tiềm năng**, nên dashboard cá nhân hóa những metric nhóm có thể dẫn đến nhận định bất công.

### 3.4. Tối ưu số đo có thể làm chất lượng thật giảm

Nếu thưởng theo số commit, ta có thể khuyến khích commit vụn. Nếu thưởng theo số lỗi đóng, có thể khuyến khích đóng lỗi sớm hoặc phân loại lại. Nếu thưởng theo coverage, có thể xuất hiện bài test chỉ thực thi dòng mà không assert.

Đây là ví dụ của một vấn đề thường được diễn đạt bằng **định luật Goodhart**: khi một phép đo bị biến thành mục tiêu cứng, nó có thể mất giá trị như một tín hiệu đại diện. Không nên coi Goodhart là “mọi metric đều vô dụng”; nó nhắc nhóm phải **xem phản ứng hành vi do chính chính sách đo lường tạo ra**.

### Ví dụ về cơ chế tối ưu sai

| Chỉ số đơn lẻ | Hành vi có thể bị khuyến khích | Điều cần hỏi thêm |
| --- | --- | --- |
| Số dòng mã được viết | Viết nhiều, ngại xóa code thừa | Có đơn giản hóa chức năng và giảm lỗi không? |
| Số commit/PR | Chia nhỏ tùy tiện, bỏ qua phần khó | Thay đổi có mục tiêu và an toàn không? |
| Số lỗi được đóng | Đóng ticket nhanh, giảm ghi nhận lỗi | Lỗi có được xử lý tận gốc và không tái phát không? |
| Số comment review | Viết bình luận vụn để tăng lượt | Review có phát hiện rủi ro thật và hỗ trợ đồng đội không? |
| Tỷ lệ coverage | Test không có assertion có nghĩa | Test có bắt được hành vi sai quan trọng không? |
| Thời gian hoàn tất task | Ngại nhận việc phức tạp hoặc phụ thuộc nhiều nhóm | Luồng công việc có bớt điểm nghẽn không? |
| Số incident liên quan tới một người | Né trực vận hành hoặc né nhận trách nhiệm hệ thống cũ | Độ phơi nhiễm, nhiệm vụ và nguyên nhân incident là gì? |

**Không dùng bảng này để gắn nhãn một cá nhân**. Hãy sử dụng nó để thiết kế môi trường khuyến khích hành vi lành mạnh và tìm cơ hội cải thiện quy trình.

## 4. Một tỷ lệ đúng vẫn có thể đánh lừa: nghịch lý Simpson

Giả sử tỷ lệ “được chấp nhận ở lần review đầu” được thống kê theo **loại thay đổi đơn giản** và **loại thay đổi phức tạp**. Hai nhóm nhận phân bổ công việc rất khác nhau:

| Loại thay đổi | Nhóm A | Tỷ lệ A | Nhóm B | Tỷ lệ B |
| --- | --- | ---: | --- | ---: |
| Đơn giản | 81/90 | 90% | 19/20 | **95%** |
| Phức tạp | 5/10 | 50% | 56/80 | **70%** |
| **Gộp tất cả** | **86/100** | **86%** | **75/100** | **75%** |

Nhìn tổng thể, **A cao hơn B**: 86% so với 75%.

Nhưng trong **cả hai nhóm công việc**, B lại có tỷ lệ cao hơn: 95% so với 90% cho thay đổi đơn giản; 70% so với 50% cho thay đổi phức tạp.

Vì sao kết quả đảo chiều?

- A xử lý **90%** công việc đơn giản; B xử lý **20%** công việc đơn giản.
- Mức độ khó có liên quan mạnh tới tỷ lệ được chấp nhận ở lần review đầu.
- Tỷ lệ gộp trộn kết quả với **cơ cấu công việc khác nhau**.

Đây là một dạng **nghịch lý Simpson**: hướng so sánh trong những nhóm có ý nghĩa có thể đảo khi gộp dữ liệu. Bài học **không phải** “B giỏi hơn A”, mà là **không thể dùng một tỷ lệ gộp để xếp hạng**, kể cả khi phép tính không sai.

Ngay cả khi đã phân tầng theo độ khó, vẫn còn các biến khác: chất lượng reviewer, vùng code, quy mô team, việc hỗ trợ lẫn nhau hoặc tiêu chuẩn review. Một phép phân tầng không tự làm dữ liệu trở thành đánh giá năng lực.

### Lỗi gộp tỷ lệ không theo số lượng mẫu

Giả sử một nhóm có hai tuần:

- Tuần 1: 1/1 thay đổi được chấp nhận — 100%.
- Tuần 2: 80/100 thay đổi được chấp nhận — 80%.

Lấy trung bình đơn giản của hai tỷ lệ ra **90%**, nhưng tỷ lệ trên **toàn bộ 101 thay đổi** là:

\[
\frac{1+80}{1+100}=\frac{81}{101}\approx80{,}2\%.
\]

Nếu muốn tỷ lệ của mọi thay đổi trong kỳ, phải cộng **tử số và mẫu số** rồi chia. Trung bình các tỷ lệ chỉ phù hợp khi mục tiêu và trọng số được định nghĩa theo cách khác (ví dụ mỗi tuần được coi là một đơn vị có trọng số ngang nhau).

**Phép tổng hợp nào đúng phụ thuộc câu hỏi đang hỏi.** Tỷ lệ tính đúng không khiến diễn giải về con người tự nhiên đúng.

## 5. Java/JUnit: tính metric đúng về số học nhưng không suy diễn thành xếp hạng

Ví dụ Java 17 sau chỉ làm **phép tổng hợp thống kê cho một tập sự kiện**, không chứa logic đánh giá nhân sự. Kiểu `ReviewCount` giữ rõ tử số và mẫu số; khi chưa có mẫu, nó trả `OptionalDouble.empty()` thay vì ngầm coi tỷ lệ là 0%.

~~~java
import java.util.OptionalDouble;

record ReviewCount(long accepted, long total) {
    ReviewCount {
        if (accepted < 0 || total < 0 || accepted > total) {
            throw new IllegalArgumentException("Invalid review counts");
        }
    }

    OptionalDouble firstPassRate() {
        if (total == 0) {
            return OptionalDouble.empty();
        }
        return OptionalDouble.of((double) accepted / total);
    }

    ReviewCount combinedWith(ReviewCount other) {
        return new ReviewCount(
                Math.addExact(accepted, other.accepted()),
                Math.addExact(total, other.total()));
    }
}

final class ReviewMetrics {
    private ReviewMetrics() {}

    static ReviewCount combine(ReviewCount... groups) {
        ReviewCount result = new ReviewCount(0, 0);
        for (ReviewCount group : groups) {
            result = result.combinedWith(group);
        }
        return result;
    }
}
~~~

Phép kiểm thử JUnit 5 kiểm tra chính nghịch lý Simpson:

~~~java
import static org.junit.jupiter.api.Assertions.*;
import org.junit.jupiter.api.Test;

class ReviewMetricsTest {
    @Test
    void aggregateCanReverseEveryStratifiedComparison() {
        ReviewCount aEasy = new ReviewCount(81, 90);
        ReviewCount aHard = new ReviewCount(5, 10);
        ReviewCount bEasy = new ReviewCount(19, 20);
        ReviewCount bHard = new ReviewCount(56, 80);

        // Trong từng nhóm độ khó, tỷ lệ của B cao hơn A.
        assertTrue(bEasy.firstPassRate().orElseThrow()
                > aEasy.firstPassRate().orElseThrow());
        assertTrue(bHard.firstPassRate().orElseThrow()
                > aHard.firstPassRate().orElseThrow());

        ReviewCount aAll = ReviewMetrics.combine(aEasy, aHard);
        ReviewCount bAll = ReviewMetrics.combine(bEasy, bHard);

        assertEquals(86L, aAll.accepted());
        assertEquals(100L, aAll.total());
        assertEquals(75L, bAll.accepted());
        assertEquals(100L, bAll.total());

        // Gộp lại thì thứ tự đảo ngược.
        assertTrue(aAll.firstPassRate().orElseThrow()
                > bAll.firstPassRate().orElseThrow());
    }

    @Test
    void zeroObservationsAreMissingNotZeroPercent() {
        assertTrue(new ReviewCount(0, 0).firstPassRate().isEmpty());
    }

    @Test
    void invalidCountsAreRejected() {
        assertThrows(IllegalArgumentException.class,
                () -> new ReviewCount(2, 1));
        assertThrows(IllegalArgumentException.class,
                () -> new ReviewCount(-1, 10));
    }

    @Test
    void aggregationUsesSumOfCountsRatherThanMeanOfRates() {
        ReviewCount all = ReviewMetrics.combine(
                new ReviewCount(1, 1),
                new ReviewCount(80, 100));

        assertEquals(81.0 / 101.0,
                all.firstPassRate().orElseThrow(), 1e-12);
    }
}
~~~

Ở đây, kiểm thử giúp bảo vệ **hợp đồng của phép đo**:

- Không có quan sát khác với tỷ lệ thất bại 0%.
- Tử số không thể lớn hơn mẫu số.
- Không tràn số âm thầm khi cộng số lượng rất lớn.
- Gộp bằng tổng số lần thành công/tổng số lần quan sát, không trung bình tỷ lệ không trọng số.
- Có thể có đảo chiều khi trộn các nhóm với cơ cấu khác nhau.

**Điều mã không được phép kết luận:** một người hoặc nhóm “tốt hơn” dựa trên `firstPassRate`. Tên metric và số học chỉ mô tả sự kiện theo quy trình; chúng không giải thích cơ chế, độ khó, mức phơi nhiễm hay giá trị thực của thay đổi.

## 6. Tương quan không đủ để kết luận nguyên nhân

Giả sử dashboard cho thấy:

- Trong những tuần số lượt deploy tăng, số incident cũng tăng.
- Trong những tuần coverage tăng, số lỗi được báo cáo giảm.

Có thể quan sát **mối liên hệ** giữa hai chuỗi số. Nhưng từ đó chưa thể kết luận:

- “Deploy nhiều gây ra incident”.
- “Coverage tăng đã làm lỗi giảm”.

Một số giải thích thay thế:

- Tuần có chiến dịch lớn vừa có **nhiều deploy** vừa có **lưu lượng cao**, dẫn đến nhiều incident.
- Module phức tạp vừa có **coverage thấp** vừa có **nhiều lỗi**, nhưng nguyên nhân gốc có thể là độ phức tạp, không phải chỉ coverage.
- Sau một sự cố, nhóm có thể **viết thêm test**, nên có lúc lỗi tăng trước, coverage tăng sau; thứ tự thời gian đảo hướng so với suy đoán.
- Nhóm đổi cách phân loại lỗi, công cụ quét hoặc quy trình báo cáo khiến số liệu thay đổi dù chất lượng thực không đổi.

### Một sơ đồ nhân quả đơn giản

~~~mermaid
flowchart TD
    C["Quy mô/phức tạp thay đổi"] --> D["Số lượt deploy"]
    C --> I["Nguy cơ incident"]
    T["Lưu lượng và phụ thuộc ngoài"] --> I
    P["Cải tiến quy trình kiểm thử"] --> Q["Chất lượng phát hành"]
    P --> V["Coverage được ghi"]
    Q --> I
~~~

Sơ đồ là **giả thuyết để thảo luận**, không phải bằng chứng về một hệ thống có thật. Nó nhắc người đọc rằng quan hệ giữa deploy và incident có thể bị **biến gây nhiễu (confounder)** tác động.

### Bốn câu hỏi về nhân quả

1. **Thứ tự thời gian:** thay đổi nghi là nguyên nhân có xảy ra trước kết quả không?
2. **Cơ chế:** bằng cách nào nó có thể tạo ra kết quả? Có test, trace, log hoặc hiểu biết hệ thống hỗ trợ cơ chế không?
3. **Giải thích cạnh tranh:** điều gì khác thay đổi cùng lúc? Có sự kiện mùa vụ, dữ liệu, chính sách hoặc công cụ đo mới không?
4. **Phản thực (counterfactual):** nếu không thực hiện thay đổi đó, kết quả nhiều khả năng sẽ thế nào?

Không thể quan sát trực tiếp hai thế giới “cùng một hệ thống, cùng một thời điểm, có và không có thay đổi” nên cần thiết kế thí nghiệm hoặc phương pháp suy luận thận trọng.

## 7. Quan sát trước–sau chưa đủ để quy công

Một nhóm áp dụng rule linter mới vào tháng 6. Số incident trong tháng 7 giảm từ 10 xuống 6. Ta **không thể nói ngay** “linter làm giảm 40% incident”.

Có thể:

- Tháng 7 có ít deployment hoặc lưu lượng thấp hơn.
- Những incident nặng đã được xử lý từ tháng trước.
- Cách ghi nhận sự cố hoặc ngưỡng cảnh báo đã thay đổi.
- Incident vốn dao động giữa các tháng, và hai điểm dữ liệu chưa phản ánh xu hướng.
- Cùng lúc nhóm sửa lỗi kiến trúc hoặc triển khai kiểm thử tích hợp.

Nếu dùng kết quả như một giả thuyết cải thiện, nên:

1. Ghi rõ **khi nào và ở đâu** rule được bật; loại lỗi mà rule thực sự có thể phát hiện.
2. Kiểm tra dữ liệu theo **nhiều kỳ trước/sau**, mức lưu lượng, số lần thay đổi, độ nghiêm trọng và lịch phát hành.
3. Xác định **các thay đổi đồng thời** và cách phân loại incident.
4. Quan sát số lỗi mà **rule cụ thể nhắm tới**, không chỉ tổng số incident mọi loại.
5. So sánh nhóm hoặc dịch vụ tương đồng nếu có, hiểu khác biệt ban đầu.
6. Bổ sung dữ liệu định tính, ví dụ một lỗi cụ thể đã được chặn trước merge nhờ rule.
7. Báo cáo kết quả là “cùng xuất hiện” hoặc “phù hợp giả thuyết” khi chưa có bằng chứng nhân quả mạnh hơn.

**Khác biệt trước–sau là điểm xuất phát để điều tra, không tự chứng minh nguyên nhân.**

## 8. Làm sao tăng chất lượng bằng chứng nhân quả?

Không phải cải tiến kỹ thuật nào cũng cần thử nghiệm khoa học quy mô lớn. Nhưng khi định đưa ra một quyết định tốn kém hoặc áp đặt KPI cá nhân, mức độ chứng cứ phải tương xứng với hậu quả.

| Cách tiếp cận | Có thể giúp trả lời | Giới hạn cần nói rõ |
| --- | --- | --- |
| **Kiểm tra cơ chế ở mức code** | Thay đổi sửa đúng đường lỗi nào? | Một đường lỗi chưa phải toàn bộ tác động production |
| **Quan sát trước–sau nhiều kỳ** | Xu hướng có thay đổi quanh thời điểm áp dụng? | Vẫn có thời vụ và thay đổi đồng thời |
| **So sánh nhóm/đơn vị tương đồng** | Nhóm áp dụng có thay đổi khác nhóm chưa áp dụng? | Hai nhóm có thể khác về công việc và rủi ro |
| **Thử nghiệm ngẫu nhiên khi khả thi, an toàn** | Hiệu ứng của một can thiệp lên tiêu chí định nghĩa | Cần bảo vệ người dùng, không tùy tiện rút bỏ biện pháp an toàn |
| **A/B trên quy trình/công cụ có thể kiểm soát** | Cách làm nào tạo tín hiệu hữu ích hơn? | Kết quả phụ thuộc đối tượng, thời gian và cách ngẫu nhiên hóa |
| **Chuỗi thời gian gián đoạn** | Xu hướng/mức có thay đổi sau một can thiệp? | Cần đủ kỳ, xem mùa vụ, autocorrelation và can thiệp khác |
| **Difference-in-differences** | So thay đổi trước–sau giữa nhóm chịu tác động và đối chứng | Cần giả định xu hướng song song và không có nhiễu khác phá giả định |
| **Triangulation** | Nhiều nguồn bằng chứng độc lập cùng ủng hộ giả thuyết? | Nhiều chỉ số có thể cùng bị sai do một nguồn dữ liệu |

Trong thực hành code quality, thường rất hữu ích kết hợp **test hồi quy chứng minh một failure mode**, **telemetry trước/sau** và **review về cơ chế**, thay vì cố gắn một tỷ lệ tăng/giảm thành bằng chứng tuyệt đối.

### Một ví dụ về kết luận được phép và kết luận vượt chứng cứ

**Dữ liệu:** sau khi bổ sung contract test cho trường `totalVnd`, ba lần PR đổi schema khiến contract test thất bại trước merge. Không có lỗi tương ứng nào được ghi nhận ở production trong kỳ.

- Có thể nói: “Contract test đã phát hiện ba thay đổi vi phạm hợp đồng đang kiểm tra trước merge.”
- Có thể đặt giả thuyết: “Test này có khả năng giảm nguy cơ phá vỡ client cũ.”
- Chưa nên nói: “Nhờ contract test, tổng số lỗi production giảm đúng X%”, nếu chưa có dữ liệu đối chứng và cách loại yếu tố khác.

**Bằng chứng trực tiếp về cơ chế** thường đủ hữu ích để tiếp tục một biện pháp bảo vệ mà không cần tuyên bố nhân quả quá mức.

## 9. Các sai lệch làm metric khó so sánh

### 9.1. Mẫu số và định nghĩa không đồng nhất

“Tỷ lệ bug trên 100 PR” phụ thuộc một bug được gán cho PR nào, được phát hiện khi nào và công việc có được chia thành PR nhỏ hay không. “Bug trên 1.000 dòng mã” lại giả định số dòng là mẫu số phù hợp, trong khi ngôn ngữ, code generated và cách tổ chức khác nhau.

Một metric chỉ so được khi **cùng định nghĩa, phạm vi và cách thu thập**. Nếu đổi rule đếm, nên đánh dấu điểm thay đổi trên biểu đồ và tránh so liên kỳ như thể đo cùng một đại lượng.

### 9.2. Kích thước mẫu nhỏ

Một nhóm chỉ có hai lần deploy trong tuần, một lần lỗi sẽ có “50% change failure rate”. Một nhóm khác có 200 lần deploy và 10 lần lỗi sẽ có “5%”. Hai tỷ lệ có cỡ mẫu, loại thay đổi và mức biến thiên rất khác nhau.

Không nên công bố xếp hạng cá nhân theo những tỷ lệ có mẫu rất nhỏ. Với mục đích học hỏi, nên báo cả **tử số/mẫu số**, cỡ mẫu, thời gian quan sát và độ bất định nếu có thể.

### 9.3. Sai lệch chọn mẫu

Chỉ phân tích PR đã merge bỏ qua những thay đổi bị hủy, cần thiết kế lại hoặc chưa qua review. Chỉ tính bug được khách báo bỏ qua lỗi bị monitoring phát hiện trước khi khách gặp. Chỉ đo thời gian xử lý incident đã đóng bỏ qua incident còn mở kéo dài.

**Dữ liệu có mặt không nhất thiết là toàn bộ tập sự kiện cần quan tâm**.

### 9.4. Chất lượng ghi nhận thay đổi

Một đội tăng cường quan sát hệ thống có thể thấy **số lỗi được phát hiện tăng** dù mức rủi ro thực giảm, vì trước đó lỗi chưa được ghi nhận. Điều này không nên bị dùng làm tín hiệu trừng phạt; nếu làm vậy, nhóm có động lực ghi nhận ít hơn.

### 9.5. Tác động của độ trễ

Lỗi do một thay đổi phát hành hôm nay có thể chỉ lộ sau vài tuần. Gán mọi lỗi xảy ra trong tháng cho các commit cùng tháng có thể làm sai quan hệ thời gian.

Cần xem **cohort theo thời điểm phát hành**, khoảng theo dõi đủ dài và chính sách gắn lỗi với nguồn thay đổi khi có bằng chứng.

### 9.6. Tính tương quan của dữ liệu

Hàng trăm request từ cùng một sự cố không phải hàng trăm lỗi độc lập. Nhiều PR trên cùng thư viện dùng chung hoặc nhiều người tham gia một thay đổi có thể tạo dữ liệu liên quan nhau. Công cụ thống kê hoặc khoảng tin cậy giả định tính độc lập có thể không phù hợp nếu bỏ qua việc nhóm theo incident, dự án hoặc release.

## 10. Những chỉ số thường bị dùng sai trong đánh giá cá nhân

### 10.1. Số dòng mã, commit và pull request

Ba số này đo **hoạt động được ghi lại**. Chúng không đo độ khó, trách nhiệm, giá trị của phần mã xóa đi hay tác động đến khách hàng.

Một thay đổi **xóa 2.000 dòng code trùng lặp** có thể làm hệ thống đơn giản hơn, nhưng nếu thưởng số dòng thêm mới thì bị đánh giá thấp.

### 10.2. Số bug và “bug do ai gây ra”

Lỗi thường là kết quả của nhiều yếu tố: đặc tả thiếu, code review, test, interface, dữ liệu, cấu hình, áp lực thời gian và quyết định thiết kế lịch sử. Gán một incident cho “người viết dòng cuối cùng” vừa có thể sai về nguyên nhân vừa khiến đội ngũ ngại nhận trách nhiệm.

Phân tích sau sự cố nên ưu tiên **điều kiện hệ thống và các lớp phòng vệ đã thiếu**, không biến một metric thành danh sách đổ lỗi.

### 10.3. Độ bao phủ test

Coverage cao là tín hiệu về mã đã được thực thi trong test; nó không tự chứng minh **assertion đúng**, mức độ bao phủ rủi ro, hành vi khi lỗi DB hoặc quyền truy cập.

Dùng coverage để tìm vùng chưa được kiểm tra và thảo luận về rủi ro thích hợp hơn dùng nó để so kỹ sư có “năng lực tốt hơn”.

### 10.4. Thời gian review/lead time

Thời gian review phản ánh cả độ lớn PR, múi giờ, số reviewer, ưu tiên, hạ tầng CI và quy trình phê duyệt. Một PR bảo mật cần duyệt kỹ có thể chậm hơn đúng đắn. Ép mọi cá nhân đạt lead time giống nhau có thể gây áp lực **bỏ qua review quan trọng**.

### 10.5. Tỷ lệ deploy thành công, incident và thời gian khôi phục

Những chỉ số vận hành hữu ích để nhóm phát hiện bottleneck và năng lực phục hồi, nhưng chúng chịu ảnh hưởng của kiến trúc dịch vụ, hạ tầng, độ khó thay đổi, phạm vi người dùng và trách nhiệm vận hành. Không thể chuyển trực tiếp thành “điểm hiệu suất lập trình viên”.

Nhiều thước đo luồng phân phối phần mềm (ví dụ deployment frequency, lead time for changes, change failure và recovery) được thiết kế hữu ích hơn ở **cấp luồng giá trị hoặc nhóm/dịch vụ có ngữ cảnh**. Không nên lấy một trục làm “leaderboard” cá nhân, hoặc suy ngược quan hệ nhân quả chỉ từ thay đổi của nó.

## 11. Thay bảng xếp hạng bằng bảng điều khiển để học hỏi

Một dashboard hỗ trợ cải tiến nên trả lời **vấn đề hệ thống nào đang cần điều tra**, không đơn thuần “ai đứng đầu?”. Có thể nhóm các chỉ số theo các mục tiêu bổ sung nhau:

| Mục tiêu nhóm | Chỉ số hoặc bằng chứng | Guardrail để tránh tối ưu lệch |
| --- | --- | --- |
| Phát hành nhanh hơn nhưng an toàn | Lead time theo loại thay đổi, thời gian chờ review/CI | Change failures, rollback, lỗi khách hàng |
| Giảm lỗi hồi quy | Lỗi quan trọng lọt qua test, test theo failure mode | Không giảm ghi nhận lỗi hoặc che incident |
| Nâng khả năng phục hồi | Thời gian phát hiện/khôi phục theo loại sự cố | Độ nghiêm trọng, thời gian phơi nhiễm, lỗi lặp lại |
| Dễ thay đổi hơn | Những điểm nghẽn phụ thuộc, thời gian onboarding vào mô-đun | Review định tính, tính đúng đắn và kiến trúc |
| Bảo vệ người dùng | Lỗi quyền, dữ liệu sai, vi phạm hợp đồng được phát hiện | Test âm tính, phân quyền thật, giám sát production |
| Giảm chi phí kiểm tra | CI feedback time, tỷ lệ flaky, thời gian chẩn đoán | Không bỏ test bảo vệ rủi ro cao để làm pipeline xanh nhanh |

**Guardrail** là tiêu chí không được làm tệ đi trong khi cải thiện một tiêu chí khác. Ví dụ giảm lead time bằng cách bỏ security review là một “cải thiện” không đáng chấp nhận.

### Đọc nhiều chỉ số không có nghĩa cộng thành một điểm duy nhất

Nếu ghép coverage, bug count, PR count và deploy frequency thành “quality score” có trọng số tùy ý, nhóm vẫn có thể che các lựa chọn giá trị và biến nhiều nguồn sai lệch thành một con số có vẻ khách quan.

Một dashboard đa chiều có thể hữu ích **mà không cần tính xếp hạng tổng hợp**. Khi phải tạo mức cảnh báo cho một quyết định cụ thể, nên công bố trọng số, lý do, giới hạn, quyền phản biện và tác động lên hành vi.

## 12. Cách trình bày số liệu có trách nhiệm

Một báo cáo tốt cần giúp người đọc phân biệt **số liệu**, **cách tính**, **diễn giải** và **hành động đề xuất**.

### Mẫu ghi chú cho một metric

~~~text
Mục tiêu:
  Phát hiện điểm nghẽn trong quy trình review ở cấp nhóm.

Chỉ số:
  Thời gian từ lúc PR sẵn sàng review tới lần phản hồi đầu tiên.

Đơn vị / tập dữ liệu:
  PR trong repository và kỳ đo cụ thể; có gắn nhóm theo loại thay đổi.

Định nghĩa:
  Chỉ tính thời gian chờ review; nêu cách xử lý cuối tuần, PR draft,
  bot, PR bị đóng và trường hợp thiếu timestamp.

Kết quả:
  Báo phân bố p50/p95 và số PR trong kỳ, không chỉ giá trị trung bình.

Giới hạn:
  PR khác độ phức tạp và mức ưu tiên; không dùng để xếp hạng reviewer.

Giả thuyết:
  Một số giai đoạn bị nghẽn do thiếu người có quyền review.

Kiểm chứng tiếp:
  Đối chiếu lịch trực, yêu cầu phê duyệt và các ví dụ PR cụ thể.

Hành động thử:
  Cải thiện phân công reviewer, đo lại trong nhiều kỳ và theo dõi
  tỷ lệ lỗi lọt qua review như guardrail.
~~~

Đây là **mẫu đề xuất**, không phải kết quả đo từ một hệ thống đang chạy.

### Phân biệt ba câu trong báo cáo

**Quan sát:** “p95 thời gian phản hồi review tăng từ 12 giờ lên 20 giờ trong ba kỳ gần đây.”

**Giả thuyết:** “Có thể do nhóm reviewer chuyên trách phải xử lý nhiều thay đổi phức tạp hơn.”

**Bước kiểm chứng:** “Phân nhóm theo độ phức tạp, phạm vi, lịch nghỉ và mức tải trước khi thay đổi quy trình.”

Tránh viết: “Người review chậm làm giảm năng suất”, vì chưa có bằng chứng xác định tác nhân và cơ chế.

## 13. Quyền riêng tư, công bằng và an toàn tâm lý trong đo lường

Việc một hệ thống có thể trích xuất log, commit, timestamp và lịch review theo từng cá nhân **không có nghĩa nên dùng chúng để giám sát hoặc đánh giá nhân sự**. Dữ liệu kỹ thuật còn có thể bộc lộ thời gian làm việc, lịch trực, mức tham gia thảo luận và nhiều đặc điểm ngoài mục tiêu cải tiến.

Một hệ thống metric có trách nhiệm nên cân nhắc:

- **Mục đích minh bạch:** mọi người biết đang đo điều gì và để làm gì.
- **Tối thiểu hóa dữ liệu:** không thu thập danh tính hoặc hoạt động chi tiết hơn mức cần để cải thiện quy trình.
- **Báo cáo tổng hợp khi phù hợp:** ưu tiên nhóm/luồng công việc, cân nhắc ngưỡng đủ mẫu để tránh suy ra cá nhân.
- **Quyền truy cập:** người nào được thấy dữ liệu, mục đích và thời hạn lưu.
- **Chống diễn giải sai:** hiển thị mẫu số, phạm vi, thay đổi định nghĩa và giới hạn thống kê.
- **Cơ chế phản hồi:** người chịu tác động có thể giải thích bối cảnh hoặc báo lỗi dữ liệu.
- **Không trừng phạt việc báo cáo vấn đề:** số bug hoặc cảnh báo tăng do quan sát tốt hơn không nên thành động lực che lỗi.
- **Đánh giá tác động của chính KPI:** nếu tạo hành vi né việc khó, ít review hoặc ít báo lỗi, cần sửa thiết kế đo.

Khi đánh giá năng lực cá nhân cho những mục đích nhân sự, cần quá trình **công bằng, có bối cảnh và nhiều nguồn thông tin phù hợp**, không quy tắc tự động “top/bottom” từ một con số kỹ thuật.

Mục tiêu của chương này là **sử dụng metric để học và cải thiện chất lượng**, không thiết kế hệ thống giám sát cá nhân.

## 14. Case study: lead time giảm nhưng chất lượng thực thay đổi thế nào?

Giả sử nhóm đưa một công cụ tự động merge các PR đáp ứng điều kiện. Sau một tháng, lead time trung vị giảm từ 36 giờ xuống 16 giờ. Đây là tín hiệu tích cực cho **độ trễ của quy trình** trong khoảng đo. Nhưng trước khi coi thay đổi là thành công toàn diện, cần xem:

| Câu hỏi | Bằng chứng nên kiểm tra |
| --- | --- |
| Thay đổi có thật sự nhờ công cụ không? | Thời điểm rollout, loại PR được auto-merge, nhóm đối chứng nếu có |
| Số PR/độ khó có đổi không? | Phân bố kích thước, loại thay đổi, dependency và kỳ phát hành |
| Review có bị bỏ qua không? | Điều kiện merge, số lần cần phê duyệt và audit của policy |
| Lỗi production có tăng không? | Change failure, lỗi hồi quy theo cohort và mức độ nghiêm trọng |
| Có tăng rollback/hotfix không? | Lần rollback, thời gian sửa và ảnh hưởng người dùng |
| Kỹ sư có tin và hiểu cơ chế không? | Feedback định tính, các trường hợp bất thường |
| Đo có tương đương không? | Cách định nghĩa “bắt đầu” và “kết thúc” lead time trước/sau |

Một kết luận cân bằng có thể là:

> “Trong kỳ theo dõi được mô tả, lead time trung vị của các PR thuộc phạm vi auto-merge giảm. Chưa đủ dữ liệu để quy toàn bộ thay đổi cho công cụ hoặc kết luận tổng chất lượng tăng; cần tiếp tục theo dõi rủi ro và đối chiếu nhóm công việc.”

**Không nên nói:** “Người nào có lead time cao hơn sau rollout là người làm việc kém”, vì công việc và mức rủi ro không đồng nhất.

### Cách thử cải tiến có học hỏi

1. Xác định vấn đề: thời gian chờ phê duyệt là nút thắt đã được quan sát.
2. Xác định tiêu chí: giảm p50/p95 chờ review ở các PR tương đương.
3. Xác định guardrail: không tăng lỗi nghiêm trọng, không bỏ kiểm tra quyền hay contract.
4. Triển khai trong phạm vi có thể kiểm soát và an toàn.
5. Theo dõi trước/sau đủ kỳ, ghi lại thay đổi đồng thời.
6. Điều tra những PR ngoại lệ thay vì xem chúng là “cá nhân yếu kém”.
7. Điều chỉnh quy trình theo dữ liệu và phản hồi, không ép mọi PR qua cùng nhịp.

## 15. Thiết kế metric như một hợp đồng kỹ thuật

Một phép đo đáng tin cậy cần những điều kiện giống như hợp đồng của API: định nghĩa, kiểu, đơn vị, hành vi khi thiếu dữ liệu và cách thay đổi phiên bản.

### Ví dụ hợp đồng cho tỷ lệ review

| Thành phần | Quy định minh họa |
| --- | --- |
| Tên | `first_pass_acceptance_rate` |
| Tử số | Số PR trong cohort được chấp nhận ở lần review đầu theo quy tắc đã mô tả |
| Mẫu số | Tổng PR có review hợp lệ trong cùng cohort |
| Đơn vị | Tỷ lệ từ 0 tới 1, hiển thị theo % |
| Kỳ đo | Các PR được review lần đầu trong tuần đã chọn |
| Loại trừ | Bot-generated PR nếu đã được công bố, PR không có reviewer |
| Thiếu dữ liệu | Không đủ mẫu hiển thị “không có dữ liệu”, không biến thành 0% |
| Phân nhóm | Độ khó/loại thay đổi/repository khi có dữ liệu đủ tin cậy |
| Mục đích | Phát hiện thay đổi trong quy trình review, **không xếp hạng cá nhân** |
| Người sở hữu | Nhóm phụ trách quy trình review và định nghĩa dữ liệu |

Nếu đổi định nghĩa từ “lần review đầu” sang “lần CI đầu”, dù tên số liệu tương tự, đó là **một metric khác**. Phải ghi nhận thời điểm thay đổi, tránh nối dữ liệu hai giai đoạn thành một đường xu hướng liên tục rồi suy hiệu quả.

### Cần biết mức độ bất định

Không phải mọi dao động nhỏ là thay đổi có ý nghĩa. Khi so tỷ lệ hoặc phân vị, hãy xem:

- Số quan sát và phạm vi thời gian.
- Mức biến thiên trong những kỳ trước.
- Khoảng tin cậy hoặc phương pháp ước lượng bất định phù hợp với cách lấy mẫu.
- Mức sai lệch do việc thiếu ghi nhận hoặc thay đổi công cụ.
- Tầm quan trọng thực tế của thay đổi: giảm 1% có ý nghĩa với người dùng hay chỉ là nhiễu?

Một kết quả “có ý nghĩa thống kê” chưa chắc có ý nghĩa sản phẩm; ngược lại, sự cố bảo mật hiếm nhưng tác động lớn cần được xử lý dù dữ liệu thống kê chưa dày.

## 16. Một phương pháp đọc biểu đồ trước khi ra quyết định

Khi thấy một metric tăng hoặc giảm, có thể đi qua các câu hỏi theo trình tự:

1. **Nó đo gì?** Tử số, mẫu số, đơn vị, đối tượng, độ phân giải thời gian.
2. **Dữ liệu đáng tin không?** Có thay đổi pipeline, instrumentation, schema, cách loại trừ hay không?
3. **Mẫu có so được không?** Khối lượng, độ khó, lưu lượng và mức phơi nhiễm có tương tự?
4. **Phân bố thế nào?** Trung bình có che đuôi dài, outlier, nhóm công việc hoặc kỳ ít mẫu không?
5. **Những yếu tố nào cùng thay đổi?** Nhân sự, quy trình, kiến trúc, release, kỳ nghỉ, SLA?
6. **Có cơ chế giải thích không?** Test, trace, review hoặc dữ liệu hiện trường nào hỗ trợ?
7. **Cần thêm bằng chứng gì?** Phân tầng, so cohort, lấy mẫu thủ công, test có kiểm soát, quan sát thêm kỳ?
8. **Hành động nào ít rủi ro nhất?** Thử một cải tiến quy trình và theo dõi guardrail trước khi mở rộng.
9. **Tác động tới con người ra sao?** Có khuyến khích né công việc khó hoặc giảm báo cáo sự cố không?

Một biểu đồ không trả lời được các câu trên vẫn hữu ích như **tín hiệu chú ý**, nhưng chưa đủ làm căn cứ cho một kết luận nhân quả hoặc đánh giá con người.

## 17. Checklist khi xây dashboard chất lượng

### Xác định mục tiêu

- [ ] Tôi biết vấn đề chất lượng hoặc quy trình mà từng chỉ số muốn giúp cải thiện.
- [ ] Tôi có tiêu chí hành vi và phạm vi cụ thể, không chỉ tên “quality score”.
- [ ] Tôi không sử dụng số commit, dòng mã, bug hay coverage đơn lẻ để xếp hạng cá nhân.
- [ ] Tôi có ít nhất một guardrail chống việc tối ưu số đo mà làm chất lượng thật xấu đi.

### Kiểm tra dữ liệu và phép tính

- [ ] Mỗi tỷ lệ có tử số, mẫu số, thời gian và đối tượng đo rõ.
- [ ] Tôi phân biệt không có dữ liệu với tỷ lệ bằng 0.
- [ ] Khi gộp tỷ lệ, trọng số phù hợp với câu hỏi; không lấy trung bình tùy tiện.
- [ ] Tôi kiểm tra khác biệt về loại việc, độ khó, độ phơi nhiễm và mẫu nhỏ.
- [ ] Tôi ghi nhận thay đổi định nghĩa, instrumentation, cách phân loại và dữ liệu bị loại.
- [ ] Tôi xem nhiều kỳ/phân bố thay vì chỉ hai điểm hoặc một trung bình.

### Diễn giải và hành động

- [ ] Tôi phân biệt quan sát, giả thuyết và khẳng định nguyên nhân.
- [ ] Tôi tìm các biến gây nhiễu và lời giải thích cạnh tranh.
- [ ] Nếu đề xuất quan hệ nhân quả, tôi có mô hình hoặc phương pháp kiểm chứng phù hợp.
- [ ] Tôi không suy đánh giá về năng lực từ chỉ số bị chi phối bởi phân công và quy trình nhóm.
- [ ] Tôi bổ sung review định tính/test/telemetry tại ranh giới quan trọng.
- [ ] Tôi báo cáo giới hạn và rủi ro còn lại cùng hành động tiếp theo.

### Trách nhiệm và quyền riêng tư

- [ ] Mục đích thu thập dữ liệu được truyền đạt và giới hạn rõ.
- [ ] Tôi ưu tiên thông tin tổng hợp, tránh giám sát cá nhân không cần thiết.
- [ ] Quyền truy cập và thời hạn lưu dữ liệu phù hợp.
- [ ] Có cách phát hiện lỗi dữ liệu, phản biện diễn giải và sửa metric không còn phù hợp.

## 18. Những ngộ nhận thường gặp

**“Số liệu khách quan nên kết luận cũng khách quan.”** Phép đếm có thể chính xác nhưng cách chọn tập dữ liệu, mục tiêu, mẫu số và diễn giải vẫn là quyết định có thể sai.

**“Một chỉ số cao hơn chứng minh một kỹ sư giỏi hơn.”** Công việc khác nhau về độ khó, trách nhiệm và mức phơi nhiễm; nhiều đóng góp quan trọng không hiện trên chỉ số.

**“Nhiều commit và nhiều dòng mã nghĩa là năng suất cao.”** Loại bỏ code không cần thiết, review và giải quyết vấn đề khó có thể tạo giá trị lớn với rất ít dòng.

**“Nhiều bug được báo chứng minh code tệ hơn.”** Cách ghi nhận tốt hơn hoặc mức sử dụng cao hơn cũng có thể làm số bug quan sát tăng.

**“Coverage tăng rồi lỗi giảm, vậy coverage tăng gây giảm lỗi.”** Cần xem thứ tự thời gian, thay đổi đồng thời, mức độ rủi ro và bằng chứng cơ chế.

**“Hai số tương quan mạnh là đủ xác định nguyên nhân.”** Cùng tăng/giảm có thể do biến thứ ba, thiên lệch dữ liệu hoặc quan hệ ngược.

**“Đã phân nhóm theo một biến là so sánh công bằng.”** Còn có nhiều khác biệt khác và sai lệch chưa được đo.

**“Tỷ lệ 100% luôn tốt hơn 95%.”** 1/1 và 950/1.000 có độ tin cậy và mức phơi nhiễm khác nhau.

**“Nếu metric đạt mục tiêu, quy trình không còn vấn đề.”** Khi biến thước đo thành mục tiêu duy nhất, nhóm có thể cải thiện số mà không cải thiện chất lượng.

**“Để bảo đảm công bằng, phải đo kỹ mọi người.”** Thu thập nhiều dữ liệu cá nhân không tự giảm thiên lệch; có thể tạo tác hại và mất niềm tin.

**“Không có đủ bằng chứng nhân quả thì không nên cải tiến.”** Có thể thử biện pháp ít rủi ro dựa trên giả thuyết hợp lý, nhưng phải mô tả mức chắc chắn và đo tác động, không tuyên bố chắc chắn quá mức.

## 19. Bài tập thực hành

### Bài tập A — phân tích bảng xếp hạng

Một dashboard hiển thị:

~~~text
Kỹ sư X: 25 PR/tháng, 0 lỗi gắn với PR.
Kỹ sư Y:  5 PR/tháng, 3 lỗi gắn với PR.
~~~

Hãy viết ít nhất **sáu câu hỏi** cần trả lời trước khi đánh giá đóng góp của X và Y. Gợi ý: phân loại công việc, độ khó, số người cùng làm, thời gian theo dõi lỗi, cách gắn trách nhiệm, công việc vô hình và độ tin cậy của hệ thống ghi nhận.

Sau đó viết một câu **không nên kết luận** và một cách sử dụng dashboard **phù hợp hơn** ở cấp nhóm.

### Bài tập B — nghịch lý Simpson

Dùng bảng ở phần 4 để:

1. Tính lại tỷ lệ gộp A và B.
2. Xác định nhóm nào có tỷ lệ cao hơn ở **từng nhóm độ khó**.
3. Giải thích tại sao tỷ lệ gộp đảo thứ tự.
4. Nêu ít nhất ba biến khác có thể làm so sánh vẫn không công bằng.
5. Viết kết luận đúng: **điều đã quan sát**, **điều không được suy ra**.

### Bài tập C — kiểm tra giả thuyết nhân quả

Sau khi nhóm bật thêm static analysis, số incident nghiêm trọng giảm 30% trong hai tháng.

Hãy xây dựng kế hoạch điều tra gồm:

- Giả thuyết về những loại lỗi static analysis có thể trực tiếp ngăn.
- Các biến gây nhiễu: tải, thay đổi sản phẩm, mùa vụ, quy trình, cách báo cáo.
- Những dữ liệu trước/sau cần có và khả năng so với một nhóm tương đồng.
- Một ví dụ bằng chứng trực tiếp rằng rule đã chặn một lỗi trước khi phát hành.
- Cách viết kết luận nếu bằng chứng nhân quả vẫn chưa đủ.

### Bài tập D — thay một KPI gây hại bằng bộ tín hiệu cân bằng

Một nhóm bị đánh giá chỉ theo `lead time` nên có xu hướng chia PR quá nhỏ, bỏ qua test tích hợp và ngại nhận phần việc khó. Hãy thiết kế một dashboard nhóm có **lead time theo loại thay đổi**, **lỗi hồi quy**, **tỷ lệ flaky**, **thời gian CI**, **phản hồi định tính** và **guardrail bảo mật/độ tin cậy**.

Mô tả cách tránh biến dashboard mới thành một tổng điểm xếp hạng cá nhân.

### Bài tập E — nhận diện thay đổi cách đo

Một ngày, số cảnh báo bảo mật tăng gấp đôi sau khi cập nhật ruleset và bật quét thêm module. Hãy xác định những kết luận có thể và không thể rút ra từ đồ thị; đề xuất cách gắn mốc thay đổi định nghĩa, phân loại các cảnh báo mới và theo dõi rủi ro thật.

## 20. Câu hỏi tự kiểm tra

1. Chỉ số và tiêu chí chất lượng khác nhau như thế nào? Nêu một ví dụ về tính đúng đắn của Java.
2. Vì sao số lượng PR, commit hoặc dòng mã không đủ để đánh giá năng lực cá nhân?
3. Điều gì khiến coverage tăng nhưng giá trị kiểm thử không tăng tương ứng?
4. Định luật Goodhart nhắc nhở điều gì khi một metric bị biến thành mục tiêu?
5. Trong ví dụ Simpson, vì sao B cao hơn ở cả hai nhóm độ khó nhưng thấp hơn khi gộp?
6. Khi nào nên tính tỷ lệ bằng tổng tử số/tổng mẫu số thay vì trung bình phần trăm?
7. Tại sao 0/0 nên biểu diễn “không có dữ liệu” thay vì 0%?
8. Phân biệt quan sát, giả thuyết và khẳng định nhân quả bằng ví dụ deploy và incident.
9. “Sau khi áp dụng công cụ, bug giảm” còn cần những dữ kiện nào trước khi quy nguyên nhân cho công cụ?
10. Những yếu tố nào có thể cùng ảnh hưởng tới số deploy và số incident?
11. Một test trực tiếp chặn lỗi API contract hỗ trợ kết luận nào? Nó không hỗ trợ kết luận nào?
12. Difference-in-differences cần những giả định quan trọng nào để kết luận có ý nghĩa?
13. Vì sao chỉ dùng mean có thể che phân bố hoặc nhóm công việc khác nhau?
14. Tại sao tăng số lỗi được ghi nhận đôi khi là tín hiệu tích cực về chất lượng quan sát?
15. Một dashboard giúp phát triển phần mềm cần có những guardrail nào để không tối ưu sai mục tiêu?
16. Cần ghi gì trong hợp đồng của một metric để so sánh nhiều kỳ có ý nghĩa?
17. Vì sao các metric vận hành nên được diễn giải ở cấp luồng công việc/nhóm, với bối cảnh, thay vì xếp hạng cá nhân?
18. Khi muốn đánh giá một quy trình mới, bạn sẽ bổ sung bằng chứng định tính và cơ chế nào?
19. Làm thế nào để bảo vệ quyền riêng tư khi thu thập dữ liệu engineering?
20. Hãy viết ba câu mô tả một thay đổi metric: **quan sát**, **giả thuyết**, **bước kiểm chứng kế tiếp**.

## Ghi nhớ

**Chỉ số chất lượng giúp quan sát hệ thống, không tự chấm điểm con người hoặc chứng minh nguyên nhân.** Một phép đo đúng về số học vẫn có thể gây hiểu nhầm nếu mẫu số, độ khó, cách ghi nhận hoặc cách phân nhóm khác nhau. Hãy sử dụng các metric để xác định rủi ro, phát hiện xu hướng và kiểm chứng giả thuyết ở cấp hệ thống; kết hợp nhiều nguồn bằng chứng, guardrail, bối cảnh và đánh giá định tính. Khi trình bày kết quả, luôn tách **điều đã đo**, **điều giả định** và **điều còn phải kiểm tra**. Đó là cách metrics thực sự phục vụ mục tiêu của `CODE_QUALITY_FUNDAMENTALS`: mã đáng tin cậy, dễ hiểu và dễ thay đổi.
