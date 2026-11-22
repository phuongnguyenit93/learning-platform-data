# Ghép cặp và hướng dẫn để truyền cách suy luận

Một người có kinh nghiệm có thể sửa một lỗi trong vài phút, nhưng nếu chỉ gửi bản vá cho đồng đội, người nhận có thể vẫn chưa biết cách nhận ra lỗi tương tự lần sau. Khi gặp tình huống mới, họ lại phải hỏi đúng người đó. Ngược lại, nếu cùng đọc yêu cầu, đặt giả thuyết, tìm bằng chứng, thử nghiệm và giải thích lựa chọn, người học dần hiểu **cách suy luận dẫn đến quyết định kỹ thuật**, không chỉ ghi nhớ một đoạn mã.

**Ghép cặp lập trình (pair programming)** và **hướng dẫn (mentoring)** tạo cơ hội truyền kiến thức ngầm qua công việc thật. Giá trị của chúng không nằm ở việc hai người cùng nhìn một màn hình hay người có kinh nghiệm gõ nhanh hơn. Giá trị nằm ở việc làm rõ cách hiểu vấn đề, tiêu chí lựa chọn, cách kiểm chứng và những đánh đổi mà người viết mã đang cân nhắc.

Bài học thuộc chương **Cộng tác và trách nhiệm** của **CODE_QUALITY_FUNDAMENTALS**. Theo mục tiêu module — hiểu những thuộc tính quyết định mã nguồn có **đáng tin cậy, dễ hiểu và dễ thay đổi hay không** — bài này trình bày cách ghép cặp và hướng dẫn để truyền cách suy luận, tăng khả năng tự giải quyết vấn đề, chia sẻ trách nhiệm và giảm phụ thuộc vào một vài cá nhân.

## 1. Truyền cách suy luận khác với truyền đáp án

Giả sử một thành viên mới gặp test tính phí vận chuyển thất bại. Người hướng dẫn có thể lập tức sửa dấu so sánh từ lớn hơn thành lớn hơn hoặc bằng, chạy test và kết thúc phiên. Lỗi đã được sửa, nhưng người học chưa chắc hiểu:

- Đặc tả nói “từ ngưỡng trở lên” có nghĩa gì?
- Vì sao giá trị đúng bằng ngưỡng là trường hợp cần kiểm tra riêng?
- Làm sao biết test hiện tại thực sự bắt được lỗi?
- Có nên đổi cả cấu trúc tính phí trong cùng thay đổi không?
- Bằng chứng nào cho thấy bản sửa không làm hỏng trường hợp khác?

Một phiên hướng dẫn có ích giúp người học **tự đi qua những câu hỏi đó**. Người hướng dẫn có thể gợi ý khi cần, nhưng mục tiêu là để người học dần tự hình thành cách tiếp cận.

| Chỉ truyền đáp án | Truyền cách suy luận |
| --- | --- |
| “Đổi dấu này thành lớn hơn hoặc bằng.” | “Đặc tả đang nói từ ngưỡng trở lên; đầu vào nào phân biệt hai toán tử?” |
| “Dùng HashSet đi.” | “Danh sách có kích thước bao nhiêu, số lần tra cứu thế nào, chi phí tạo index có đáng không?” |
| “Tách method này ra.” | “Phương thức đang có những lý do thay đổi nào? Phần nào có thể kiểm thử độc lập?” |
| “Test thiếu rồi.” | “Trường hợp nào nếu sai sẽ làm assertion hiện tại vẫn xanh?” |
| “Đừng bắt Exception.” | “Nếu ghi dữ liệu thất bại, caller nhận trạng thái gì và hợp đồng yêu cầu điều gì?” |

Không phải lúc nào cũng cần đặt câu hỏi thay vì đưa câu trả lời. Khi có sự cố nghiêm trọng, một chỉ dẫn trực tiếp có thể cần thiết để khôi phục dịch vụ. Nhưng sau khi xử lý, hãy dành thời gian giải thích **vì sao chọn cách đó và bằng chứng nào hỗ trợ quyết định**.

## 2. Kiến thức ngầm thường nằm trong quá trình làm việc

Tài liệu có thể mô tả API, cấu trúc module và quy tắc coding. Tuy nhiên, một số kiến thức khó truyền qua văn bản đơn thuần:

- Cách đọc stack trace để tìm nguyên nhân gốc thay vì sửa dòng cuối cùng.
- Cách xác định test nào là oracle đáng tin khi test cũ có thể đang khóa một bug.
- Cách nhận biết abstraction đang bảo vệ ranh giới thật hay chỉ thêm tầng.
- Cách cân nhắc giữa sửa nhỏ và refactor rộng.
- Cách kiểm tra ảnh hưởng của một thay đổi tới consumer, database và vận hành.
- Cách biết khi nào cần hỏi người sở hữu nghiệp vụ hoặc chuyên gia bảo mật.
- Cách nói “chưa đủ bằng chứng” thay vì đoán.

Ghép cặp cho phép người học quan sát **các bước trung gian**: người có kinh nghiệm đọc gì trước, loại bỏ giả thuyết nào, tìm tài liệu ở đâu, khi nào chạy test và vì sao chưa chọn một phương án.

### 2.1. Nói thành lời những điều thường chỉ nghĩ trong đầu

Một kỹ sư giàu kinh nghiệm có thể đọc code và nhanh chóng nhận ra rủi ro, nhưng người mới chỉ thấy kết luận. Hãy diễn đạt suy nghĩ theo trình tự:

1. “Yêu cầu nói đơn hàng từ 500.000 VND trở lên được miễn phí.”
2. “Điều kiện hiện dùng toán tử lớn hơn, nên giá trị đúng 500.000 không vào nhánh miễn phí.”
3. “Tôi sẽ kiểm tra test hiện tại có ca đúng ngưỡng chưa.”
4. “Test chỉ có 400.000 và 600.000 nên cả hai đều qua dù toán tử sai.”
5. “Tôi thêm ca 500.000 trước, xác nhận nó thất bại trên code hiện tại.”
6. “Sau đó sửa điều kiện và chạy lại cả ba trường hợp.”

Đây là **tư duy thành tiếng (think aloud)**. Nó giúp người học hiểu đường đi từ yêu cầu đến bằng chứng và quyết định.

### 2.2. Chia sẻ cả điều chưa biết

Người hướng dẫn không cần giả vờ biết mọi thứ. Có thể nói:

> “Tôi chưa biết endpoint có middleware kiểm tra tenant ở trước hay không. Trước khi kết luận đây là lỗi phân quyền, ta sẽ tìm đường gọi và test tích hợp liên quan.”

Cách này truyền một thói quen quan trọng: **không biến giả thiết thành sự thật**. Nó cũng cho người học thấy kỹ sư có kinh nghiệm vẫn cần tìm hiểu và kiểm chứng.

## 3. Ghép cặp lập trình là gì?

Trong pair programming, hai người cùng làm một nhiệm vụ trên cùng một phần mã trong một khoảng thời gian. Họ có thể dùng một máy, chia sẻ màn hình hoặc công cụ cộng tác từ xa.

Mô hình phổ biến gồm hai vai trò:

- **Driver:** điều khiển bàn phím, viết hoặc thay đổi mã, chạy lệnh theo trao đổi.
- **Navigator:** theo dõi mục tiêu, đọc luồng rộng hơn, đặt câu hỏi, kiểm tra giả thiết và cân nhắc bước tiếp theo.

Hai vai trò cần **luân phiên**. Navigator không phải người ngồi chờ để bắt lỗi; driver cũng không phải người chỉ gõ theo chỉ dẫn.

~~~mermaid
flowchart TD
    A[Cùng đọc yêu cầu và xác định mục tiêu] --> B[Driver thực hiện bước nhỏ]
    B --> C[Navigator theo dõi, hỏi và kiểm tra giả thiết]
    C --> D[Cùng đọc diff và kết quả test]
    D --> E{Đã đạt mục tiêu phiên?}
    E -- Chưa --> F[Đổi vai hoặc chọn bước tiếp theo]
    F --> B
    E -- Rồi --> G[Ghi quyết định và việc còn lại]
~~~

### 3.1. Driver cần làm gì?

Driver nên:

- Nói rõ mình đang định thay đổi gì trước khi gõ.
- Giữ diff nhỏ và dễ đọc.
- Chạy kiểm tra sau bước có ý nghĩa.
- Hỏi khi chưa hiểu đề xuất hoặc giả thiết.
- Không biến mình thành người đánh máy thụ động.
- Chủ động giải thích lựa chọn và thử phương án của chính mình.

### 3.2. Navigator cần làm gì?

Navigator nên:

- Giữ bối cảnh yêu cầu và mục tiêu phiên.
- Theo dõi tác động ngoài dòng đang sửa.
- Hỏi về điều kiện biên, lỗi và hợp đồng.
- Nhắc kiểm tra test, log hoặc tài liệu phù hợp.
- Đưa ra gợi ý theo mức cần thiết, không giành quyền quyết định mọi chi tiết.
- Để driver có thời gian suy nghĩ và tự thử.

Navigator không nên đọc từng ký tự rồi ra lệnh. Cách đó biến phiên ghép cặp thành một người làm việc và một người điều khiển từ xa.

### 3.3. Luân phiên vai trò

Có thể đổi vai sau một khoảng thời gian ngắn, sau một test hoặc sau một checkpoint. Không cần áp dụng lịch cứng cho mọi phiên. Điều quan trọng là cả hai đều có cơ hội **thực hiện và giải thích**, không để người ít kinh nghiệm luôn ở vai navigator.

Nếu một người mới chưa quen công cụ, có thể bắt đầu bằng việc họ điều khiển các bước đơn giản như chạy test, tìm symbol và đọc diff. Sau đó tăng dần phần họ tự thiết kế và viết mã.

## 4. Chọn mục tiêu ghép cặp có ích

Không phải mọi công việc đều cần hai người cùng làm. Ghép cặp phù hợp khi có một mục tiêu học tập hoặc phối hợp rõ ràng.

| Công việc | Lý do ghép cặp có thể hữu ích |
| --- | --- |
| Điều tra bug khó tái hiện | Hai người cùng xây giả thuyết và đối chiếu bằng chứng |
| Thay đổi module ít người hiểu | Truyền kiến thức ngầm và giảm rủi ro bus factor |
| Sửa luồng bảo mật hoặc tiền tệ | Cần kiểm tra nhiều giả thiết và trường hợp biên |
| Refactor ranh giới module | Cùng đánh giá hợp đồng và tác động tới consumer |
| Thiết lập test cho code legacy | Người có kinh nghiệm chia sẻ cách chọn oracle và fixture |
| Onboarding vào codebase | Người mới quan sát cách tìm luồng, tài liệu và owner |
| Chuẩn bị một kỹ thuật mới | Hai người cùng thử, đánh giá trade-off và ghi lại kết quả |

Ghép cặp có thể ít phù hợp khi:
- Công việc rất cơ học, có hướng dẫn rõ và không có mục tiêu trao đổi.
- Một người cần thời gian tập trung độc lập để hoàn thành phần việc đã hiểu.
- Hai người không có cùng mục tiêu hoặc không thể dành thời gian liên tục.
- Nhiệm vụ chứa thông tin cần giới hạn quyền truy cập mà công cụ cộng tác chưa đáp ứng.

Khi không cần ghép cặp, có thể dùng review, demo, tài liệu ngắn hoặc một phiên hỏi đáp để truyền kiến thức.

## 5. Chuẩn bị một phiên ghép cặp

Một phiên tốt bắt đầu trước khi mở IDE. Hãy thống nhất:

- **Mục tiêu:** cuối phiên cần hiểu, quyết định hoặc hoàn thành điều gì?
- **Phạm vi:** file, module, test hoặc câu hỏi nào nằm trong phiên?
- **Vai trò:** ai bắt đầu driver, ai navigator và khi nào đổi?
- **Thời lượng:** ví dụ 45–90 phút, có nghỉ nếu cần.
- **Môi trường:** branch, fixture, quyền truy cập và công cụ đã sẵn sàng?
- **Điều kiện kết thúc:** test nào phải chạy, quyết định nào cần ghi, việc gì có thể để lại?

Ví dụ mục tiêu cụ thể:

> “Trong 60 phút, cùng tìm nguyên nhân test tính phí thất bại ở đúng ngưỡng, thêm regression test và thống nhất phạm vi sửa. Nếu phát hiện cần đổi API hoặc schema, ghi thành việc riêng thay vì mở rộng phiên.”

Mục tiêu này rõ hơn “cùng xem module checkout” vì cả hai biết **điều gì được xem là kết quả**.

### 5.1. Chuẩn bị vừa đủ

Không cần viết một tài liệu dài trước mỗi phiên. Có thể gửi trước:
- Link issue hoặc yêu cầu.
- Test hoặc log đã biết.
- Vị trí code liên quan.
- Những điều đã thử và kết quả.
- Câu hỏi người học muốn hiểu.

Nếu người học đã thử một hướng, hãy hỏi họ **đã suy luận thế nào** thay vì yêu cầu làm lại từ đầu.

## 6. Một cấu trúc phiên ghép cặp 60 phút

Thời lượng dưới đây là gợi ý, có thể điều chỉnh theo độ khó:

| Thời gian | Hoạt động | Kết quả mong đợi |
| --- | --- | --- |
| 0–5 phút | Thống nhất mục tiêu và vai trò | Cùng hiểu vấn đề cần giải quyết |
| 5–15 phút | Đọc yêu cầu, code và test | Xác định hợp đồng và giả thiết |
| 15–35 phút | Thực hiện một hoặc vài bước nhỏ | Có thay đổi hoặc bằng chứng cụ thể |
| 35–45 phút | Đổi vai, đọc diff và kiểm tra | Cả hai đều tham gia suy luận |
| 45–55 phút | Chạy test, review rủi ro còn lại | Biết điều gì đã được xác minh |
| 55–60 phút | Tóm tắt và ghi việc tiếp theo | Người học có thể giải thích cách làm |

Không nên coi lịch này là một cuộc họp bắt buộc phải kết thúc bằng code đã merge. Một phiên điều tra tốt có thể kết thúc bằng **giả thuyết bị bác bỏ, log cần thu thập hoặc câu hỏi phải hỏi owner**.

### 6.1. Dừng đúng lúc

Nếu phiên bắt đầu mở rộng sang nhiều vấn đề không liên quan, hãy ghi lại và chọn một trong hai hướng:
- Dừng để xử lý mục tiêu đã thống nhất.
- Chủ động thống nhất lại mục tiêu và thời gian.

Không nên để một phiên mentoring biến thành cuộc viết lại toàn bộ module mà người học không còn theo kịp.

## 7. Hướng dẫn (mentoring) là quá trình tăng dần quyền tự chủ

Mentoring có thể diễn ra trong một phiên ghép cặp hoặc kéo dài qua nhiều tuần. Người hướng dẫn giúp người học phát triển năng lực, hiểu hệ thống và tự đưa ra quyết định.

Một tiến trình hữu ích:

1. **Làm mẫu:** người hướng dẫn giải thích cách tiếp cận và nói thành lời các quyết định.
2. **Làm cùng:** người học và người hướng dẫn cùng phân tích, luân phiên thực hiện.
3. **Người học dẫn dắt:** người học đề xuất kế hoạch; người hướng dẫn đặt câu hỏi và phản hồi.
4. **Người học tự thực hiện:** người hướng dẫn review kết quả và chỉ hỗ trợ ở điểm cần thiết.
5. **Người học truyền lại:** người học giải thích lại cho đồng đội hoặc cập nhật tài liệu.

~~~mermaid
flowchart LR
    A[Quan sát người hướng dẫn] --> B[Thực hiện cùng nhau]
    B --> C[Người học dẫn dắt]
    C --> D[Tự thực hiện với review]
    D --> E[Chia sẻ lại cho người khác]
~~~

Đây không phải thang đánh giá cứng. Một người có thể tự chủ trong Java unit test nhưng vẫn cần hỗ trợ ở migration hoặc bảo mật. Mức hỗ trợ nên theo **năng lực và rủi ro của nhiệm vụ**, không gắn nhãn tổng quát junior hay senior.

### 7.1. Giảm hỗ trợ theo từng bước

Người hướng dẫn có thể bắt đầu bằng chỉ dẫn trực tiếp:
- “Mở test này và chạy riêng.”
- “Đặt breakpoint trước nhánh so sánh.”
- “Kiểm tra giá trị bằng đúng ngưỡng.”

Sau đó chuyển sang câu hỏi:
- “Test nào phân biệt hai toán tử?”
- “Nếu không chạy debugger, log nào giúp xác nhận giả thuyết?”
- “Bằng chứng nào đủ để kết luận?”

Cuối cùng để người học tự đề xuất:
- “Bạn sẽ bắt đầu ở đâu?”
- “Những trường hợp nào cần test?”
- “Điều gì có thể bị ảnh hưởng ngoài method này?”

Mục tiêu là **giảm dần sự phụ thuộc**, không phải giữ người học ở trạng thái luôn cần mentor duyệt từng bước.

## 8. Đặt câu hỏi gợi mở thay vì đưa đáp án ngay

Câu hỏi mentoring tốt giúp người học tự nhìn thấy thông tin còn thiếu.

| Mục tiêu | Câu hỏi gợi mở |
| --- | --- |
| Hiểu yêu cầu | “Từ ‘trở lên’ bao gồm trường hợp bằng ngưỡng không?” |
| Tìm giả thiết | “Đoạn này đang giả định dữ liệu đến từ đâu?” |
| Đọc luồng | “Ai gọi method này và kết quả được dùng tiếp ở đâu?” |
| Xem trường hợp biên | “Input nhỏ nhất, lớn nhất hoặc thiếu dữ liệu sẽ thế nào?” |
| Chọn test | “Test nào sẽ thất bại nếu giả thuyết của ta sai?” |
| Cân nhắc thiết kế | “Nếu yêu cầu thay đổi, phần nào phải sửa và vì sao?” |
| Xác định rủi ro | “Nếu lời gọi này timeout sau khi ghi thành công thì caller biết gì?” |
| Xác minh | “Bằng chứng nào cho thấy bản sửa giữ hợp đồng?” |
| Phản tư | “Lần sau gặp vấn đề tương tự, bạn sẽ bắt đầu từ đâu?” |

### 8.1. Hỏi từng câu, cho thời gian suy nghĩ

Một chuỗi mười câu hỏi liên tiếp có thể khiến người học cảm thấy bị kiểm tra. Hãy hỏi một câu, lắng nghe câu trả lời, rồi dựa vào đó chọn câu tiếp theo.

Nếu người học im lặng, đừng vội xem đó là thiếu năng lực. Có thể họ đang suy nghĩ, chưa biết thuật ngữ hoặc không thoải mái nói khi bị quan sát. Có thể đưa gợi ý nhỏ hoặc cho họ viết suy nghĩ ra trước.

### 8.2. Không dùng câu hỏi như cách che giấu kỳ vọng

Nếu có một yêu cầu bắt buộc, nói rõ:
> “API này phải kiểm tra quyền ở server trước khi trả dữ liệu. Ta cùng tìm vị trí phù hợp trong luồng hiện tại.”

Không nên hỏi vòng quanh để người học đoán một tiêu chuẩn mà mentor đã biết là bắt buộc.

## 9. Ví dụ thực hành: cùng điều tra lỗi tính phí ở đúng ngưỡng

Giả sử đặc tả ghi: “Đơn hàng từ 500.000 VND trở lên được miễn phí vận chuyển; đơn thấp hơn ngưỡng chịu phí 30.000 VND.”

Mã hiện tại:

~~~java
final class ShippingPolicy {
    static long feeVnd(long subtotalVnd) {
        if (subtotalVnd > 500_000L) {
            return 0L;
        }
        return 30_000L;
    }
}
~~~

Người học nói: “Có lẽ thiếu test.” Người hướng dẫn không cần sửa ngay. Hai người có thể đi qua các bước sau.

### 9.1. Làm rõ hợp đồng

Mentor hỏi:
- “Từ ‘từ 500.000 trở lên’ có bao gồm 500.000 không?”
- “Nếu tổng là 499.999 thì phí bao nhiêu?”
- “Nếu tổng là 500.001 thì sao?”

Người học có thể lập bảng:

| Tổng tiền | Kết quả theo đặc tả |
| ---: | ---: |
| 499.999 VND | 30.000 VND |
| 500.000 VND | 0 VND |
| 500.001 VND | 0 VND |

Bảng này chuyển câu mô tả thành các ví dụ có thể kiểm chứng.

### 9.2. Tìm test phân biệt

Mentor hỏi:
> “Nếu chỉ test 400.000 và 600.000, cả hai toán tử lớn hơn và lớn hơn hoặc bằng cho kết quả giống nhau ở hai trường hợp đó. Giá trị nào làm hai biểu thức khác nhau?”

Người học nhận ra cần test **500.000**. Sau đó họ tự viết:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;

import org.junit.jupiter.api.Test;

class ShippingPolicyTest {
    @Test
    void waivesFeeAtExactThreshold() {
        assertEquals(0L, ShippingPolicy.feeVnd(500_000L));
    }
}
~~~

Test thất bại trên code hiện tại vì phương thức trả 30.000.

### 9.3. Người học đề xuất bản sửa

~~~java
if (subtotalVnd >= 500_000L) {
    return 0L;
}
~~~

Cùng bổ sung test hai phía:

~~~java
@Test
void chargesBelowThreshold() {
    assertEquals(30_000L, ShippingPolicy.feeVnd(499_999L));
}

@Test
void waivesAboveThreshold() {
    assertEquals(0L, ShippingPolicy.feeVnd(500_001L));
}
~~~

### 9.4. Kết thúc bằng giải thích, không chỉ bằng test xanh

Mentor hỏi:
- “Điều gì khiến test đúng ngưỡng quan trọng hơn test một giá trị bất kỳ?”
- “Nếu đặc tả đổi thành ‘trên 500.000’, test nào cần thay?”
- “Có đầu vào âm không, và hợp đồng xử lý thế nào?”
- “Bạn sẽ giải thích bug này trong PR ra sao?”

Người học nên có thể nói: **test đúng ranh giới phân biệt hai cách hiểu của điều kiện; expected lấy từ đặc tả; bản sửa thay đổi đúng toán tử và các ca lân cận vẫn giữ hành vi**.

Đây là dấu hiệu kiến thức đã được truyền qua quá trình suy luận.

## 10. Hướng dẫn đọc codebase hiện hữu

Khi người mới vào một repository, đừng bắt đầu bằng việc đọc tuần tự tất cả file. Người hướng dẫn có thể làm mẫu một quy trình tìm hiểu:

1. Bắt đầu từ yêu cầu hoặc một luồng người dùng cụ thể.
2. Tìm entry point: controller, consumer, scheduled job hoặc CLI.
3. Lần theo dữ liệu đầu vào và đầu ra.
4. Xác định nơi chứa quy tắc nghiệp vụ.
5. Tìm ranh giới I/O: database, HTTP, filesystem, queue.
6. Tìm test gần nhất và xem chúng bảo vệ hành vi nào.
7. Đọc lịch sử thay đổi hoặc quyết định kiến trúc khi cần.
8. Tự vẽ luồng ngắn và nhờ người hiểu module xác nhận.

Mentor nên giải thích **vì sao chọn đường đi đó**. Ví dụ: “Ta bắt đầu từ controller vì issue nói về HTTP request; nếu bug xuất hiện trong job nền, ta sẽ tìm entry point của scheduler thay vì giả định controller là nơi duy nhất.”

### 10.1. Dạy cách tìm thông tin, không chỉ cung cấp link

Một người có thể gửi ngay đường dẫn tới class đúng, nhưng người học vẫn không biết tìm class tương tự ở module khác.

Hãy chỉ cách:
- Tìm symbol và caller.
- Tìm test theo tên nghiệp vụ.
- Dùng Git history để hiểu lý do thay đổi.
- Đọc cấu hình DI và build profile.
- Tìm contract hoặc schema.
- Nhận diện generated code và mã do framework tạo.

Khi người học tự tìm được thông tin, họ có thể chuyển kỹ năng sang một vùng codebase mới.

## 11. Ghép cặp khi debug: cùng xây giả thuyết và kiểm tra

Debug dễ biến thành chuỗi thử ngẫu nhiên nếu không có cách suy luận rõ. Một phiên ghép cặp có thể dùng bảng:

| Quan sát | Giả thuyết | Bằng chứng cần tìm | Kết quả |
| --- | --- | --- | --- |
| Test fail khi chạy suite | State dùng chung | Chạy riêng và parallel; tìm static field | Chưa xác nhận |
| API trả sai tenant | ID lấy từ request không được ràng buộc | Theo caller, middleware và integration test | Đã/Chưa xác nhận |
| Timeout khi CI tải cao | Connection pool cạn | Metrics pool, thời gian chờ và log | Đã/Chưa xác nhận |
| Giá sai ở đúng ngưỡng | Điều kiện dùng sai toán tử | Test dưới, đúng, trên ngưỡng | Đã/Chưa xác nhận |

Mentor có thể làm mẫu cách **bác bỏ giả thuyết**. Khi một giả thuyết sai, đó vẫn là tiến triển nếu nhóm biết vì sao nó sai và không lặp lại cùng thử nghiệm.

### 11.1. Không thay đổi nhiều biến cùng lúc

Nếu vừa đổi timeout, vừa thêm retry, vừa sửa thread pool rồi test qua, không biết thay đổi nào đã tạo tác dụng. Hãy kiểm soát mỗi thử nghiệm, ghi lại kết quả và giữ cách tái hiện.

### 11.2. Phân biệt lỗi sản phẩm với lỗi môi trường

Một test timeout trên runner chậm có thể do hạ tầng, nhưng cũng có thể lộ race condition. Người hướng dẫn nên hỏi:
- Điều kiện timeout có nằm trong SLA không?
- Runner có thiếu tài nguyên?
- Test có sleep cố định?
- Hệ thống có thể gặp concurrency tương tự khi chạy thật?
- Log có cho thấy request đang chờ ở đâu?

Không nên dạy người mới thói quen “CI đỏ thì rerun đến xanh”.

## 12. Ghép cặp để refactor an toàn

Refactor thường cần một người nhìn vào cấu trúc hiện tại và một người theo dõi hợp đồng, test cùng tác động rộng.

Một phiên có thể chia:
- Driver trích một method mà không đổi công thức.
- Navigator kiểm tra thứ tự phép tính, ngoại lệ và dữ liệu biên.
- Cả hai đọc diff để xác nhận không có thay đổi nghiệp vụ.
- Đổi vai khi chuyển sang bước tiếp theo.
- Chạy test và ghi checkpoint trước khi mở rộng phạm vi.

Câu hỏi mentor có thể dùng:
- “Bước này thay đổi cấu trúc hay hành vi?”
- “Test nào sẽ thất bại nếu ta vô tình đổi hành vi?”
- “Có caller nào dùng method qua reflection hoặc API public không?”
- “Nếu dừng ở commit này, code có ở trạng thái hợp lệ không?”
- “Có thể revert riêng bước này không?”

### 12.1. Tránh mentor làm thay phần khó

Nếu mentor luôn tự sửa phần kiến trúc khó và chỉ giao người học việc đổi tên biến, người học không được thực hành quyết định quan trọng. Có thể để người học đề xuất thiết kế trước, mentor phản biện bằng câu hỏi về hợp đồng, phụ thuộc và rủi ro.

Với thay đổi nguy hiểm, mentor có thể giữ quyền phê duyệt hoặc yêu cầu chuyên gia khác review. **Trao quyền học tập không có nghĩa bỏ kiểm soát rủi ro**.

## 13. Phản hồi cụ thể và tôn trọng

Mentoring cần phản hồi đủ rõ để người học biết điều gì đã tốt, điều gì cần thay đổi và vì sao.

Một cấu trúc đơn giản:

1. **Quan sát:** điều gì đã xảy ra hoặc đã được viết?
2. **Tác động:** nó ảnh hưởng đến chất lượng hoặc phối hợp ra sao?
3. **Đề xuất:** bước tiếp theo hoặc cách luyện tập là gì?

Ví dụ:

> “Bạn đã viết test cho 499.999 và 500.001, nên hai phía ngưỡng đã được kiểm tra. Trường hợp 500.000 vẫn thiếu, vì đây là đầu vào duy nhất phân biệt toán tử lớn hơn với lớn hơn hoặc bằng. Hãy thêm ca đó và giải thích expected dựa trên câu chữ trong đặc tả.”

Phản hồi này nói rõ **điều đã làm được** và **khoảng trống còn lại**, không đánh giá con người là “cẩu thả”.

### 13.1. Tránh những cách nói làm giảm khả năng học

| Nên tránh | Thay bằng |
| --- | --- |
| “Cái này quá cơ bản.” | “Ta cùng xem hợp đồng và kiểm tra một ví dụ nhỏ.” |
| “Em phải biết điều này rồi.” | “Đây là quy tắc thường gặp; mình sẽ giải thích cách nhận ra trong codebase.” |
| “Làm sai hết rồi.” | “Hai test hiện tại chưa kiểm tra trường hợp đúng ngưỡng; phần còn lại đang phản ánh đúng đặc tả.” |
| “Cứ làm theo anh/chị.” | “Đây là lý do mình chọn cách này; bạn có thấy trade-off nào khác không?” |
| “Tôi sẽ sửa cho nhanh.” | “Bạn thử đề xuất bản sửa trước, mình sẽ cùng review rủi ro.” |

### 13.2. Phản hồi riêng và phản hồi công khai

Góp ý kỹ thuật trong code review nên gắn với code và có thể được cả nhóm đọc. Những phản hồi về tiến bộ cá nhân, khó khăn hoặc mục tiêu phát triển thường phù hợp hơn trong trao đổi riêng.

Không dùng mentoring để làm người học xấu hổ trước nhóm hoặc biến một lỗi nhỏ thành đánh giá năng lực tổng thể.

## 14. Tạo không gian để người học đặt câu hỏi

Một người mới có thể không hỏi vì:
- Sợ bị đánh giá là thiếu kiến thức.
- Không biết thuật ngữ để mô tả điều chưa hiểu.
- Mentor trả lời quá nhanh hoặc ngắt lời.
- Phiên ghép cặp có quá nhiều người quan sát.
- Mục tiêu phiên không rõ, người học sợ làm chậm tiến độ.
- Trước đó câu hỏi đã bị phản hồi thiếu tôn trọng.

Mentor có thể tạo điều kiện bằng cách:
- Nói rõ việc hỏi là một phần của phiên.
- Cho người học thời gian suy nghĩ.
- Hỏi “phần nào chưa rõ?” thay vì “hiểu chưa?”.
- Bình thường hóa việc tra tài liệu và xác minh.
- Chia nhỏ nhiệm vụ nếu người học mất bối cảnh.
- Ghi lại câu hỏi chưa giải quyết và tìm câu trả lời sau.

### 14.1. Không đồng nhất im lặng với đồng ý

Sau khi giải thích một quyết định, hãy mời người học **diễn đạt lại bằng lời của họ**:
> “Nếu tuần sau cần đổi ngưỡng giảm giá, bạn sẽ tìm ở đâu và test nào cần cập nhật?”

Câu hỏi này cho biết người học có thể vận dụng ý tưởng không. Chỉ hỏi “rõ chưa?” thường nhận được câu “rõ” dù còn nhiều điều chưa hiểu.

## 15. Ghép cặp từ xa

Pair programming từ xa cần chủ động hơn vì hai người không dễ quan sát trạng thái và tín hiệu của nhau.

### 15.1. Chuẩn bị công cụ và quyền truy cập

- Dùng công cụ chia sẻ IDE hoặc màn hình phù hợp chính sách tổ chức.
- Kiểm tra quyền đọc/ghi repository và môi trường test.
- Không chia sẻ token, mật khẩu, dữ liệu khách hàng hoặc bí mật qua màn hình/chat.
- Nếu cần dữ liệu mẫu, dùng fixture đã được phép.
- Thống nhất ai điều khiển bàn phím, cách yêu cầu đổi vai và cách dừng chia sẻ.
- Giữ ghi chú phiên ở nơi được phép và không ghi nội dung nhạy cảm không cần thiết.

### 15.2. Nói rõ thao tác và bối cảnh

Khi điều khiển từ xa, driver nên nói:
- File đang mở và mục tiêu bước này.
- Lệnh sắp chạy và lý do.
- Kết quả đang thấy.
- Điều gì sẽ được kiểm tra tiếp.

Navigator nên báo khi mất bối cảnh:
> “Mình chưa theo kịp vì vừa chuyển từ test sang implementation. Có thể quay lại assertion đang thất bại trước không?”

### 15.3. Chia sẻ quyền điều khiển

Nếu chỉ một người luôn điều khiển, người kia dễ trở thành khán giả. Hãy đổi vai có chủ đích, kể cả khi phải dành vài phút để người mới làm quen thao tác.

Nếu môi trường kỹ thuật không hỗ trợ cùng sửa, có thể dùng nhịp **driver chia sẻ màn hình → navigator giải thích → đổi vai ở checkpoint**, hoặc hai người cùng xem diff và test.

## 16. Các hình thức cộng tác khác nhau

Không phải mọi phiên đều cần hai người viết code cùng lúc.

| Hình thức | Cách làm | Phù hợp khi |
| --- | --- | --- |
| **Pair programming** | Hai người cùng làm một nhiệm vụ, luân phiên driver/navigator | Debug, thiết kế, code khó hoặc onboarding |
| **Ping-pong pairing** | Một người viết test thất bại, người kia viết phần tối thiểu để qua, rồi đổi | Tập trung vào TDD và phản hồi ngắn |
| **Mob programming** | Nhóm nhỏ cùng giải quyết một vấn đề, một người điều khiển tại một thời điểm | Quyết định liên chức năng hoặc kiến thức phân tán |
| **Mentoring session** | Một người hỗ trợ mục tiêu học tập qua nhiều buổi | Phát triển kỹ năng và tự chủ |
| **Design walkthrough** | Tác giả trình bày luồng và trade-off, nhóm đặt câu hỏi | Thay đổi kiến trúc hoặc hợp đồng |
| **Shadowing** | Người học quan sát một công việc thật và ghi câu hỏi | Onboarding ban đầu hoặc hoạt động vận hành |
| **Reverse shadowing** | Người học tự thực hiện, người có kinh nghiệm quan sát và hỗ trợ | Kiểm tra mức tự chủ trước khi nhận trách nhiệm |

Chọn hình thức theo mục tiêu. Nếu vấn đề chỉ cần một quyết định kiến trúc, design walkthrough có thể hiệu quả hơn ghép cặp nhiều giờ. Nếu người học cần thực hành debug, shadowing đơn thuần có thể chưa đủ; họ cần tự điều khiển.

## 17. Chuyển giao trách nhiệm và quyền sở hữu

Mục tiêu cộng tác không phải để mọi việc đều cần mentor. Người học cần dần nhận trách nhiệm phù hợp với năng lực và rủi ro.

Một lộ trình có thể là:

| Giai đoạn | Trách nhiệm của người học | Hỗ trợ |
| --- | --- | --- |
| **Quan sát** | Theo dõi luồng, ghi câu hỏi và giải thích lại | Mentor làm mẫu và cung cấp bối cảnh |
| **Thực hiện có hướng dẫn** | Viết test hoặc sửa một bước nhỏ | Mentor cùng kiểm tra giả thiết |
| **Dẫn dắt thay đổi nhỏ** | Đề xuất phương án, thực hiện và mở PR | Mentor review các điểm rủi ro |
| **Sở hữu thành phần** | Theo dõi lỗi, tài liệu, metric và thay đổi | Mentor hỗ trợ khi có vấn đề ngoài phạm vi |
| **Truyền lại** | Hướng dẫn đồng đội khác và cập nhật tri thức | Mentor phản hồi, không điều khiển thay |

Không nên dùng thời gian làm việc hoặc số lần ghép cặp làm bằng chứng duy nhất cho năng lực. Hãy quan sát **người học có tự giải thích quyết định, tìm bằng chứng, nhận diện rủi ro và biết khi nào cần trợ giúp hay không**.

### 17.1. Quyền tự chủ đi cùng ranh giới trách nhiệm

Người học có thể tự sửa unit test, nhưng thay đổi production permission hoặc migration có thể vẫn cần review của owner. Đây không phải thiếu tin tưởng; đó là kiểm soát tương xứng với tác động.

Hãy giải thích:
- Ai sở hữu quyết định?
- Những thay đổi nào cần approval?
- Khi nào phải gọi người phụ trách hệ thống?
- Sự cố cần escalation theo kênh nào?
- Những gì người học có thể tự quyết trong phạm vi được giao?

Minh bạch trách nhiệm giúp người mới không phải đoán quyền hạn và tránh cả hai thái cực: tự ý thay đổi rủi ro cao hoặc không dám làm bất kỳ việc gì.

## 18. Ghi lại kiến thức sau phiên ghép cặp

Một phiên hữu ích không nên chỉ tồn tại trong trí nhớ của hai người. Ghi lại những điều **có giá trị tái sử dụng**, không cần chép nguyên toàn bộ hội thoại.

Có thể ghi:

- Vấn đề hoặc luồng đã tìm hiểu.
- Giả thuyết quan trọng và bằng chứng xác nhận/bác bỏ.
- Quyết định kỹ thuật và trade-off.
- Test hoặc lệnh kiểm tra có ích.
- Vị trí tài liệu, owner và dependency liên quan.
- Điều còn chưa rõ.
- Bước tiếp theo và người chịu trách nhiệm.

Ví dụ:

~~~markdown
### Pairing note — Điều tra phí vận chuyển

Mục tiêu:
- Xác minh hành vi tại ngưỡng miễn phí.

Quan sát:
- Đặc tả: từ 500.000 VND trở lên được miễn phí.
- Code dùng toán tử lớn hơn.
- Test cũ chỉ có 499.999 và 500.001.

Kết luận:
- Thiếu test đúng ngưỡng; test mới thất bại trên code cũ.
- Bản sửa dùng lớn hơn hoặc bằng, các ca biên đã qua.

Cách suy luận cần giữ:
- Chuyển từ câu chữ đặc tả thành bảng input/expected.
- Chọn giá trị phân biệt hai biểu thức.
- Chạy test thất bại trước, rồi sửa nhỏ.

Việc tiếp theo:
- Kiểm tra caller của chính sách phí và cập nhật tài liệu nếu cần.
~~~

Ghi chú là ví dụ minh họa. Không ghi token, dữ liệu cá nhân hoặc log nhạy cảm vào tài liệu chia sẻ.

### 18.1. Khi nào cần ADR hoặc tài liệu dài hơn?

Nếu phiên phát hiện một quyết định kiến trúc ảnh hưởng nhiều module, hãy ghi vào ADR hoặc tài liệu chính thức theo quy trình của dự án. Pairing note chỉ nên là **điểm truy cập ngắn**, không thay thế nơi lưu quyết định chuẩn.

## 19. Tránh các anti-pattern khi ghép cặp và mentoring

| Anti-pattern | Tác động | Cách điều chỉnh |
| --- | --- | --- |
| **Mentor độc chiếm bàn phím** | Người học không được thực hành | Đổi vai và để người học tự triển khai |
| **Driver chỉ gõ theo lệnh** | Không hiểu mục đích hoặc trade-off | Yêu cầu driver giải thích bước tiếp theo |
| **Navigator vi mô hóa từng dòng** | Mất quyền tự chủ và nhịp suy nghĩ | Tập trung vào mục tiêu, hợp đồng và rủi ro |
| **Không có mục tiêu phiên** | Trao đổi lan man, khó biết đã xong chưa | Chốt một kết quả có thể kiểm chứng |
| **Sửa ngay mọi lỗi nhìn thấy** | Phạm vi phình to | Ghi việc ngoài phạm vi thành issue |
| **Giải thích bằng thuật ngữ không định nghĩa** | Người học ngại hỏi, mất bối cảnh | Dùng ví dụ và giải thích từ chuyên môn |
| **Chỉ làm việc dễ** | Người học không được tiếp cận suy luận quan trọng | Tăng dần độ khó với hỗ trợ phù hợp |
| **Mentor luôn đưa đáp án** | Tạo phụ thuộc vào một người | Dùng câu hỏi và giảm dần hỗ trợ |
| **Không đổi vai** | Một người làm, một người xem | Đổi vai theo checkpoint |
| **Không ghi lại quyết định** | Kiến thức biến mất khi hai người rời phiên | Tóm tắt ngắn và liên kết tài liệu |
| **Dùng ghép cặp để đánh giá cá nhân** | Tạo áp lực, giảm khả năng thử nghiệm | Tách học tập khỏi đánh giá hiệu suất |
| **Quarantine mọi việc khó** | Người học không có cơ hội phát triển | Chia nhỏ nhiệm vụ và giữ kiểm soát rủi ro |
| **Ghép cặp mọi công việc** | Chi phí phối hợp cao, mất thời gian tập trung | Chọn nhiệm vụ có lợi ích cộng tác rõ |

### 19.1. Không biến mentoring thành kiểm tra liên tục

Nếu mentor liên tục hỏi “tại sao?” với giọng chất vấn, người học có thể tập trung đoán câu trả lời mong muốn thay vì suy nghĩ thật. Hãy giải thích mục tiêu: câu hỏi dùng để làm rõ lập luận, không phải tìm lỗi của người học.

### 19.2. Đừng đánh đồng tốc độ gõ với năng lực

Người mới có thể gõ chậm vì chưa quen IDE, nhưng vẫn có suy luận tốt. Người gõ nhanh có thể hoàn thành code mà bỏ qua hợp đồng. Đánh giá qua **chất lượng quyết định, bằng chứng và khả năng tự chủ**, không qua số dòng hoặc tốc độ thao tác.

## 20. Xử lý bất đồng trong phiên ghép cặp

Hai người có thể có quan điểm khác nhau về abstraction, test, naming hoặc cách sửa bug. Đây là cơ hội làm rõ tiêu chí.

Một cách trao đổi:

1. Mỗi người mô tả vấn đề theo hợp đồng hoặc bằng chứng.
2. Nêu giả thiết và điều chưa biết.
3. So sánh phương án theo tính đúng, khả năng kiểm thử, chi phí thay đổi và rủi ro.
4. Nếu có thể, tạo thử nghiệm nhỏ để phân biệt.
5. Nếu cần quyết định thuộc owner khác, ghi câu hỏi và xin ý kiến đúng người.
6. Ghi kết luận và lý do để nhóm không phải tranh luận lại.

Ví dụ:
- Người A muốn thêm interface để tách database.
- Người B muốn giữ class hiện tại vì chỉ có một implementation.

Thay vì tranh luận “SOLID hay YAGNI”, hãy hỏi:
- Logic nghiệp vụ có đang phụ thuộc JDBC?
- Test có cần database thật để kiểm tra phép tính?
- Interface có tạo ranh giới I/O hẹp và ổn định?
- Có thể đạt mục tiêu bằng một thay đổi nhỏ hơn không?

Kết luận phải dựa vào **vấn đề cần giải quyết**, không phải thâm niên hoặc chức danh của người đề xuất.

## 21. Đánh giá hiệu quả mentoring mà không biến thành KPI hình thức

Một chương trình mentoring không nên đo thành công chỉ bằng số giờ ghép cặp, số PR hoặc số câu hỏi người học đặt ra.

Những tín hiệu hữu ích hơn:

| Tín hiệu | Cách quan sát |
| --- | --- |
| **Tự giải thích quyết định** | Người học nêu được hợp đồng, giả thiết và trade-off |
| **Tự tìm bằng chứng** | Biết tìm caller, test, log, config và tài liệu |
| **Chọn test phù hợp** | Viết expected theo đặc tả và kiểm tra trường hợp biên |
| **Nhận diện rủi ro** | Biết hỏi về dữ liệu, quyền, side effect và rollback |
| **Tự xử lý nhiệm vụ nhỏ** | Có thể hoàn thành và review một thay đổi trong phạm vi |
| **Biết khi nào cần trợ giúp** | Escalate đúng lúc thay vì đoán hoặc chờ quá lâu |
| **Chia sẻ lại kiến thức** | Cập nhật note hoặc hướng dẫn đồng đội |
| **Giảm phụ thuộc vào một cá nhân** | Nhiều người có thể duy trì module và xử lý tình huống thường gặp |

### 21.1. Không dùng số liệu để trừng phạt người học

Số câu hỏi nhiều có thể cho thấy người học chủ động tìm hiểu, không phải kém. Số lần cần mentor hỗ trợ cũng phụ thuộc độ khó nhiệm vụ và chất lượng tài liệu hiện tại.

Dữ liệu mentoring nên dùng để **cải thiện cách hỗ trợ và tổ chức tri thức**, không tạo bảng xếp hạng cá nhân.

### 21.2. Xin phản hồi hai chiều

Người học có thể nói:
- Phần nào dễ hiểu?
- Mentor nói hoặc làm quá nhanh ở đâu?
- Họ muốn tự thử thêm bước nào?
- Chủ đề nào cần tài liệu trước phiên sau?

Mentor cũng cần phản hồi:
- Người học đã tự làm được gì?
- Giả thiết nào cần kiểm tra thêm?
- Nhiệm vụ tiếp theo có thể giao ở mức tự chủ nào?

## 22. Một kế hoạch mentoring bốn tuần minh họa

Kế hoạch sau chỉ là ví dụ cho người mới tham gia một module Java hiện hữu. Có thể điều chỉnh theo kinh nghiệm, nhiệm vụ và thời gian thực tế.

| Tuần | Trọng tâm | Hoạt động | Dấu hiệu tiến bộ |
| --- | --- | --- | --- |
| **1. Hiểu luồng** | Entry point, cấu trúc và test | Shadowing một bug nhỏ, vẽ luồng dữ liệu | Giải thích được caller, domain logic và I/O |
| **2. Kiểm chứng** | Test, debug và hợp đồng | Ghép cặp thêm regression test | Tự chọn input/expected và tái hiện lỗi |
| **3. Thay đổi** | Refactor bước nhỏ | Người học làm driver, mentor navigator | Có thể sửa trong phạm vi và giải thích rủi ro |
| **4. Tự chủ** | PR và bàn giao | Người học dẫn dắt thay đổi nhỏ, mentor review | Tự xử lý, ghi quyết định và biết khi cần escalation |

Không nên ép mọi người hoàn thành cùng tốc độ. Nếu tuần đầu phát hiện nền tảng test còn thiếu, có thể kéo dài phần đó. Nếu người học đã hiểu luồng, tăng độ khó sớm hơn.

## 23. Mẫu kế hoạch một phiên ghép cặp

~~~markdown
### Pairing session — <chủ đề>

Người tham gia:
- Driver ban đầu:
- Navigator ban đầu:
- Người sở hữu module nếu cần:

Mục tiêu:
- Cuối phiên cần hiểu hoặc kiểm chứng điều gì?

Bối cảnh:
- Issue / PR / module:
- Yêu cầu hoặc hợp đồng:
- Điều đã thử và kết quả:

Cách làm:
- Vai trò và thời điểm đổi:
- Test/log/tài liệu sẽ xem:
- Rủi ro cần chú ý:

Kết quả:
- Điều đã xác nhận:
- Giả thuyết đã bác bỏ:
- Quyết định và lý do:
- Test hoặc thay đổi đã thực hiện:

Điều chưa rõ:
- Câu hỏi cần owner trả lời:
- Bằng chứng cần thu thập:

Bước tiếp theo:
- Người phụ trách:
- Thời điểm:
- Điều kiện kết thúc:
~~~

Mẫu này giúp buổi làm việc có mục tiêu và ghi lại tri thức. Với một phiên ngắn về một câu hỏi đơn giản, có thể chỉ cần ghi ba dòng: vấn đề, kết luận và việc tiếp theo.

## 24. Bài tập vận dụng

### Tình huống A — Người mới chờ mentor chỉ từng dòng

Một thành viên mới mở PR nhưng không bắt đầu sửa cho đến khi mentor nói chính xác tên file, method và dòng cần đổi.

**Câu hỏi:** mentor nên làm gì trong phiên tiếp theo?

**Gợi ý:** cùng đọc yêu cầu, hỏi người học cách tìm entry point và test liên quan, để họ đề xuất bước đầu. Mentor có thể cung cấp gợi ý theo mức tăng dần, nhưng để người học tự điều khiển và giải thích lựa chọn.

### Tình huống B — Mentor sửa quá nhanh

Một test fail vì sai ngưỡng. Mentor lập tức sửa toán tử và merge. Người học vẫn không hiểu tại sao test cũ không bắt được lỗi.

**Câu hỏi:** phần học tập nào còn thiếu?

**Gợi ý:** cần cùng lập bảng input/expected, tìm giá trị phân biệt toán tử lớn hơn và lớn hơn hoặc bằng, chạy test thất bại trước khi sửa và giải thích oracle. Kết quả không chỉ là code xanh mà là người học biết chọn test biên.

### Tình huống C — Hai người bất đồng về interface

Một người muốn tạo PaymentGateway, người kia cho rằng chỉ có một provider nên không cần interface.

**Câu hỏi:** dùng câu hỏi nào để đi tới quyết định?

**Gợi ý:** xem ranh giới I/O, hợp đồng của use case, khả năng test, thay đổi provider đã được xác nhận và chi phí thêm tầng. Một implementation không tự chứng minh interface thừa; cũng không tự chứng minh nó cần thiết.

### Tình huống D — Ghép cặp từ xa nhưng một người luôn điều khiển

Trong ba phiên liên tiếp, mentor chia sẻ màn hình và viết toàn bộ code. Người học chỉ nghe và trả lời “đúng”.

**Câu hỏi:** thay đổi cách tổ chức thế nào?

**Gợi ý:** chuyển người học thành driver ở một bước phù hợp, thống nhất mục tiêu và cho họ giải thích trước khi thao tác. Đổi vai ở checkpoint; nếu cần, dành vài phút làm quen công cụ.

### Tình huống E — Debug không có giả thuyết

Hai người liên tục thay timeout, sleep, retry và thread pool cho đến khi test qua.

**Câu hỏi:** mentor nên đưa nhóm quay lại bước nào?

**Gợi ý:** dừng thử ngẫu nhiên, ghi quan sát, xây giả thuyết và chọn một thử nghiệm phân biệt. Giữ lại log và kết quả mỗi lần; không xem một lần pass là bản sửa.

### Tình huống F — Người học sợ hỏi

Một thành viên không hiểu cấu hình DI nhưng không hỏi vì lần trước bị nói “cái này cơ bản”. Sau đó họ sửa nhầm scope singleton và tạo race condition.

**Câu hỏi:** cần thay đổi điều gì ở mentoring và trách nhiệm?

**Gợi ý:** tạo không gian hỏi không bị phán xét, giải thích lifecycle và ranh giới trách nhiệm, yêu cầu review phù hợp trước thay đổi state dùng chung. Không chỉ trách người học vì chưa biết.

### Tình huống G — Phiên ghép cặp kéo dài không mục tiêu

Hai người bắt đầu sửa một bug nhưng tiếp tục đổi tên package, nâng framework và thiết kế lại module. Sau hai giờ không có test hoặc checkpoint nào xanh.

**Câu hỏi:** làm sao điều chỉnh?

**Gợi ý:** quay lại mục tiêu ban đầu, tách công việc ngoài phạm vi thành issue, chọn một bước có thể kiểm chứng và đặt điều kiện kết thúc. Pairing không phải lý do để mở rộng PR vô hạn.

### Tình huống H — Người học hoàn thành nhanh nhưng không giải thích được

Một thành viên làm theo hướng dẫn và PR qua CI, nhưng khi được hỏi vì sao dùng HashSet, họ chỉ nói “mentor bảo vậy”.

**Câu hỏi:** làm sao đánh giá hiểu biết?

**Gợi ý:** hỏi về kích thước dữ liệu, số lần lookup, chi phí xây set, bộ nhớ và kết quả benchmark. Có thể yêu cầu người học giải thích khi nào phương án cũ tốt hơn. Không đánh giá chỉ dựa trên việc hoàn thành task.

## 25. Checklist trước, trong và sau mentoring

### Trước phiên

- **Mục tiêu:** có một kết quả học tập hoặc kỹ thuật rõ ràng?
- **Bối cảnh:** yêu cầu, code, test và những điều đã thử có sẵn?
- **Vai trò:** ai bắt đầu driver/navigator và khi nào đổi?
- **Thời gian:** đủ tập trung nhưng có điểm dừng?
- **Rủi ro:** dữ liệu, credential và quyền truy cập được xử lý đúng?

### Trong phiên

- **Tư duy thành tiếng:** người tham gia có giải thích giả thiết và bằng chứng?
- **Tham gia:** cả hai có cơ hội điều khiển và đặt câu hỏi?
- **Câu hỏi:** mentor gợi mở nhưng không biến phiên thành kiểm tra?
- **Kiểm chứng:** mỗi thay đổi quan trọng có test hoặc bằng chứng phù hợp?
- **Phạm vi:** công việc có còn phục vụ mục tiêu?
- **Tôn trọng:** bất đồng tập trung vào hợp đồng và mã, không đánh giá con người?

### Sau phiên

- **Kết quả:** điều gì đã xác nhận, điều gì còn chưa rõ?
- **Tự chủ:** người học có thể giải thích cách suy luận và bước tiếp theo?
- **Tài liệu:** quyết định hoặc kiến thức có cần ghi lại?
- **Trách nhiệm:** ai sở hữu việc tiếp theo và quyền quyết định nào?
- **Theo dõi:** phiên sau nên giảm hay tăng mức hỗ trợ?
- **Phản hồi:** người học và mentor có cơ hội cải thiện cách cộng tác?

## 26. Kết luận

**Ghép cặp và mentoring có giá trị khi giúp người học tự suy luận và tự hành động tốt hơn qua mỗi lần cộng tác.** Người hướng dẫn làm mẫu cách hiểu yêu cầu, đọc code, đặt giả thuyết, chọn test, cân nhắc trade-off và tìm bằng chứng; người học dần đảm nhận vai trò chủ động hơn, giải thích quyết định và truyền lại kiến thức.

Một phiên thành công không chỉ được đo bằng số dòng code hoặc việc PR đã merge. Hãy nhìn vào việc người học có thể **tự tìm đúng luồng, nhận diện rủi ro, kiểm chứng giả thuyết, giải thích lựa chọn và biết khi nào cần hỗ trợ** hay không.

Trong **CODE_QUALITY_FUNDAMENTALS**, ghép cặp và hướng dẫn để truyền cách suy luận giúp nhóm **đáng tin cậy hơn nhờ nhiều người cùng kiểm tra quyết định, dễ hiểu hơn nhờ kiến thức ngầm được diễn đạt và ghi lại, và dễ thay đổi hơn nhờ trách nhiệm cùng khả năng duy trì không tập trung vào một cá nhân**.
