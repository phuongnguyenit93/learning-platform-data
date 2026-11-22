# Ghi lại giả thiết và điều kiện cần xem xét lại

Trong phát triển phần mềm, nhiều quyết định kỹ thuật chỉ hợp lý khi một số điều kiện còn đúng: số lượng người dùng chưa lớn, dữ liệu thay đổi ít, yêu cầu bảo mật đã xác định, nhóm có đủ thời gian hoặc một thư viện còn được duy trì. Vấn đề thường không nằm ở bản thân quyết định mà ở việc **những điều kiện khiến quyết định hợp lý đã thay đổi nhưng không ai nhận ra**.

Bài học thuộc chương **Bối cảnh và đánh đổi** của **CODE_QUALITY_FUNDAMENTALS**, với mục tiêu hiểu những thuộc tính quyết định mã nguồn có **đáng tin cậy, dễ hiểu và dễ thay đổi** hay không. Kỹ năng trọng tâm là diễn đạt giả thiết rõ ràng, ghi nhận căn cứ của quyết định và xác định **khi nào cần đánh giá lại**, nhằm duy trì chất lượng mã phù hợp với bối cảnh thực tế.

## 1. Vì sao quyết định kỹ thuật cần đi kèm giả thiết?

Giả sử nhóm chọn cách tải toàn bộ dữ liệu đơn hàng vào bộ nhớ để tạo báo cáo. Ở thời điểm ban đầu, mỗi tệp chỉ vài nghìn bản ghi, chạy một lần mỗi ngày và hoàn tất nhanh. Quyết định đơn giản này có thể hoàn toàn hợp lý.

Sáu tháng sau, báo cáo chạy mỗi giờ và dữ liệu tăng hàng chục lần. Nếu người duy trì mới chỉ thấy mã đọc toàn bộ tệp, họ có thể tưởng đây là lựa chọn đã được cân nhắc cho quy mô hiện tại. Hệ thống có thể bắt đầu chậm, hết bộ nhớ hoặc gặp lỗi gián đoạn.

Khi ấy, điều cần có không chỉ là lời giải thích “đã chọn đọc vào bộ nhớ”, mà còn là:

- **Giả thiết ban đầu:** kích thước dữ liệu và tần suất chạy ở mức nào?
- **Bằng chứng:** con số dựa trên đo đạc, yêu cầu nghiệp vụ hay ước lượng?
- **Đánh đổi:** giải pháp tiết kiệm điều gì và chấp nhận rủi ro gì?
- **Điều kiện xem xét lại:** dấu hiệu định lượng hoặc sự kiện nào cho thấy giả thiết không còn đủ đúng?
- **Hành động và người chịu trách nhiệm:** ai kiểm tra và làm gì khi dấu hiệu xuất hiện?

Ghi lại các thông tin này biến quyết định từ một lựa chọn chỉ người viết nhớ thành **lập luận có thể kiểm tra và điều chỉnh**. Nó hỗ trợ review, bàn giao, khắc phục sự cố và tránh biến một thỏa hiệp tạm thời thành ràng buộc kéo dài vô hạn.

## 2. Phân biệt dữ kiện, giả thiết, ràng buộc và quyết định

Các khái niệm liên quan nhưng không thay thế cho nhau.

| Khái niệm | Ý nghĩa | Ví dụ trong hệ thống báo cáo |
| --- | --- | --- |
| **Dữ kiện (fact)** | Điều đã quan sát hoặc kiểm chứng tại một thời điểm, trong phạm vi cụ thể | “30 lần chạy gần nhất có tệp lớn nhất 4,2 MiB”, ghi nhận ngày đo |
| **Giả thiết (assumption)** | Điều đang tạm coi là đúng khi ra quyết định; có thể chưa đủ bằng chứng hoặc có thể thay đổi | “Trong quý tới, kích thước tệp thường không vượt 5 MiB” |
| **Ràng buộc (constraint)** | Giới hạn phải tuân theo trong phạm vi hiện tại | “Job phải chạy trên máy có giới hạn heap 256 MiB” |
| **Quyết định (decision)** | Phương án được chọn để đáp ứng mục tiêu dưới các điều kiện nêu trên | “Dùng cách đọc toàn bộ tệp trước khi tổng hợp” |
| **Đánh đổi (trade-off)** | Lợi ích nhận được và chi phí/rủi ro chấp nhận | “Triển khai nhanh, đổi lại dùng bộ nhớ tăng theo kích thước dữ liệu” |
| **Điều kiện xem lại (revisit trigger)** | Tín hiệu hoặc sự kiện yêu cầu kiểm tra lại quyết định | “p95 kích thước tệp vượt 8 MiB trong 7 ngày liên tiếp” |
| **Rủi ro (risk)** | Điều bất lợi có thể xảy ra cùng khả năng và mức ảnh hưởng | “Job hết bộ nhớ trong đợt dữ liệu tăng đột biến” |

Một **dữ kiện tại thời điểm T** không chứng minh giả thiết về tương lai. Nếu kết quả đo được thu thập từ dữ liệu thử, hãy nêu rõ phạm vi và độ tin cậy; không gọi nó là dữ kiện đại diện cho sản xuất.

**Giả thiết khác với yêu cầu.** Yêu cầu “không làm mất bản ghi” cần được bảo đảm bằng thiết kế và kiểm thử. Giả thiết “khối lượng dữ liệu sẽ tăng chậm” là điều có thể sai và cần theo dõi. Không nên dùng giả thiết để hạ thấp một yêu cầu bắt buộc, đặc biệt liên quan đến bảo mật, dữ liệu hay hợp đồng với người dùng.

## 3. Viết giả thiết có thể kiểm tra được

Một câu như “hệ thống chưa lớn” quá mơ hồ: chưa lớn là bao nhiêu, trong khoảng thời gian nào và bằng chứng từ đâu? Giả thiết hữu ích cần đủ cụ thể để người khác hiểu **khi nào nó có thể không còn đúng**.

Một mẫu ghi nhận:

> **Trong [phạm vi / khoảng thời gian], chúng ta giả định [điều kiện có thể kiểm tra] vì [bằng chứng hoặc lập luận]. Nếu [tín hiệu/giới hạn], cần xem lại [quyết định] do [rủi ro].**

Ví dụ:

> Trong ba tháng đầu, mỗi lần nhập báo cáo được kỳ vọng có tối đa 10.000 dòng vì ba đợt đo thử gần nhất đều dưới 6.000 dòng. Nếu số dòng thực tế vượt 8.000 trong nhiều kỳ liên tiếp, cần đánh giá lại cách nạp toàn bộ dữ liệu vào bộ nhớ vì chi phí bộ nhớ và thời gian xử lý có thể tăng đáng kể.

Các con số trong ví dụ là **minh họa cách viết**, không phải ngưỡng chung cho mọi hệ thống.

### 3.1. Những trường nên lưu

| Trường | Câu hỏi cần trả lời |
| --- | --- |
| Mã hoặc tên giả thiết | Người khác dẫn chiếu giả thiết này như thế nào? |
| Phạm vi và thời điểm | Áp dụng cho môi trường, phiên bản, nhóm người dùng và giai đoạn nào? |
| Nội dung giả thiết | Điều gì đang được tin là đúng? |
| Nguồn và độ tin cậy | Đã đo, được xác nhận hay mới là phỏng đoán? Dữ liệu có còn mới không? |
| Quyết định phụ thuộc | Nếu giả thiết sai, lựa chọn nào cần xem lại? |
| Hệ quả nếu sai | Tính đúng đắn, bảo mật, hiệu năng, khả năng bảo trì sẽ chịu ảnh hưởng gì? |
| Tín hiệu và ngưỡng xem lại | Ai hoặc công cụ nào phát hiện điều kiện kích hoạt? |
| Người phụ trách | Ai xác minh và tổ chức quyết định tiếp theo? |
| Mốc rà soát | Ngày rà soát định kỳ hoặc sự kiện cần rà soát? |
| Trạng thái | Còn hiệu lực, cần xác minh, đã thay đổi hay đã thay thế? |

Không phải giả thiết nhỏ nào cũng cần biểu mẫu dài. Một dòng trong mô tả pull request hoặc issue có thể đủ. Với quyết định chi phối kiến trúc, dữ liệu hoặc rủi ro vận hành, cần bản ghi dễ tìm, có người phụ trách và lịch sử cập nhật.

### 3.2. Mức độ chắc chắn phải được diễn đạt trung thực

Ba cách viết sau mang ý nghĩa rất khác nhau:

- **Đã kiểm chứng:** “Số đơn tối đa trong 30 ngày qua là 70.000, lấy từ chỉ số thống kê môi trường sản xuất ngày 15/11.”
- **Ước lượng có căn cứ:** “Đội nghiệp vụ dự kiến lưu lượng tăng không quá 30% trong quý tới; chưa có số đo trong mùa cao điểm.”
- **Chưa xác nhận:** “Có thể chỉ một nhóm dùng tính năng này; cần xác nhận với người phụ trách sản phẩm trước khi phát hành rộng.”

Khi mức chắc chắn thấp nhưng hậu quả nếu sai cao, nên ưu tiên **đo đạc, thử nghiệm hoặc kiểm soát rủi ro** trước khi phụ thuộc vào giả thiết đó.

## 4. Điều kiện xem xét lại cần đủ rõ để hành động

Điều kiện xem xét lại không phải là cam kết phải thiết kế lại ngay. Nó là **tín hiệu cần đánh giá xem phương án hiện tại còn phù hợp hay không**.

Có thể chia điều kiện thành ba nhóm:

1. **Theo số liệu:** lưu lượng, tỷ lệ lỗi, độ trễ, mức sử dụng bộ nhớ, thời gian triển khai, chi phí thay đổi hoặc số trường hợp phát sinh.
2. **Theo sự kiện:** thêm đối tác tích hợp, mở khu vực kinh doanh, thay đổi yêu cầu pháp lý, đưa dữ liệu thật vào, nâng cấp phụ thuộc hoặc thay đổi giới hạn hạ tầng.
3. **Theo mốc thời gian:** sau một đợt phát hành, trước mùa cao điểm, sau 30 ngày vận hành hoặc tại kỳ rà soát hằng quý.

Ví dụ về cách viết:

| Câu mơ hồ | Điều kiện có thể hành động |
| --- | --- |
| “Khi dữ liệu lớn thì tối ưu” | “Nếu p95 kích thước đầu vào vượt 8 MiB trong 7 ngày, đo peak heap và so sánh cách đọc theo luồng” |
| “Khi có nhiều người dùng thì phân quyền” | “Trước khi cấp quyền cho nhóm ngoài đội vận hành, đánh giá mô hình phân quyền và ghi vết thao tác” |
| “Nếu cache gây lỗi thì sửa” | “Nếu có báo cáo dữ liệu cũ vượt quá 5 phút theo hợp đồng, đánh giá lại thời gian sống và cơ chế vô hiệu hóa cache” |
| “Sau này sẽ tách lớp” | “Khi thêm nguồn dữ liệu thứ hai có quy tắc xử lý khác, review ranh giới giữa đọc dữ liệu và logic nghiệp vụ” |
| “Nhớ xem lại sau” | “Người phụ trách rà soát giả thiết tại buổi review vận hành cuối quý” |

Ngưỡng nên **gắn với lý do kỹ thuật hoặc nghiệp vụ**: thời gian đáp ứng đã cam kết, ngân sách bộ nhớ, tỷ lệ lỗi chịu được hoặc lượng công bảo trì thực tế. Nếu mới là ngưỡng cảnh báo tạm, phải ghi rõ để sau khi có dữ liệu đo đạc có thể điều chỉnh.

Không phải điều gì cũng đo thành một con số chính xác. Ví dụ sự kiện “dữ liệu bắt đầu chứa thông tin cá nhân” có thể kích hoạt đánh giá bảo mật ngay, không cần chờ đủ số lượt truy cập.

## 5. Ví dụ đầy đủ: quyết định xử lý báo cáo trong bộ nhớ

Đội phát triển cần cung cấp báo cáo tổng hợp đơn hàng bằng Java. Hiện tại có một job chạy định kỳ trên máy nội bộ. Nhóm cân nhắc hai cách:

- **Phương án A:** đọc toàn bộ các dòng, sau đó tính tổng hợp trong bộ nhớ. Dễ triển khai và gỡ lỗi trên tập nhỏ.
- **Phương án B:** xử lý từng dòng hoặc phân trang. Phức tạp hơn ở phần quản lý trạng thái, lỗi đầu vào và kiểm thử nhưng ít phụ thuộc vào việc nạp toàn bộ dữ liệu cùng lúc.

Chọn A có thể phù hợp **nếu dữ liệu đủ nhỏ, tác động khi job thất bại có thể kiểm soát và nhóm có tín hiệu để xem xét lại**.

### 5.1. Bản ghi quyết định ngắn

~~~markdown
# ADR-012 — Xử lý báo cáo bằng cách đọc toàn bộ đầu vào
Trạng thái: Chấp nhận có điều kiện (ví dụ giả định)
Ngày: 2026-11-16
Người phụ trách: Nhóm phát triển báo cáo

Bối cảnh:
- Job tạo báo cáo chỉ đọc, chạy một lần mỗi ngày.
- Máy chạy giới hạn heap 256 MiB.
- Cần hoàn thành phiên bản ban đầu với phạm vi sử dụng nhỏ.

Quyết định:
- Dùng cách đọc toàn bộ tệp vào bộ nhớ để tổng hợp.
- Giới hạn kích thước đầu vào và trả lỗi rõ ràng nếu vượt mức cho phép.

Giả thiết:
- A1: Trong 3 tháng đầu, tệp thường <= 5 MiB.
- A2: Tần suất chạy không vượt 1 lần/ngày.
- A3: Job chỉ đọc và đầu ra có thể tái tạo từ dữ liệu nguồn.

Bằng chứng:
- Số liệu thử nghiệm trên dữ liệu đại diện hiện có; chưa đo mùa cao điểm.
- Các giới hạn và số liệu phải được kiểm tra lại trước khi dùng dữ liệu mới.

Đánh đổi:
- Lợi: đơn giản, nhanh triển khai, dễ kiểm thử trên dữ liệu nhỏ.
- Hại: dùng bộ nhớ tăng theo dữ liệu; có rủi ro khi đầu vào tăng mạnh.

Điều kiện xem lại:
- R1: p95 kích thước tệp > 8 MiB trong 7 ngày liên tiếp.
- R2: Bộ nhớ đỉnh đo được > 60% giới hạn heap trong 3 lần chạy.
- R3: Có yêu cầu chạy thường xuyên hơn hoặc cần ghi/chỉnh sửa dữ liệu.
- R4: Rà soát định kỳ sau 30 ngày vận hành.

Khi kích hoạt:
- Đo lại thời gian, bộ nhớ và mức sử dụng thật.
- So sánh đọc theo luồng, phân trang hoặc tổng hợp tại nguồn.
- Ghi quyết định giữ nguyên hay thay thế, kèm lý do.
~~~

**Lưu ý:** tên nhóm, ngưỡng và mốc thời gian ở bản ghi trên là dữ liệu minh họa. Trong dự án thật, phải thay bằng người phụ trách, số đo và giới hạn thực tế.

Bản ghi giúp người đến sau biết *vì sao* giải pháp đơn giản được chọn. Nếu lượng dữ liệu không tăng và job tiếp tục chạy ổn định, quyết định có thể được **giữ lại sau rà soát**. Ngược lại, nếu có yêu cầu ghi dữ liệu, rủi ro đã đổi bản chất và phải đánh giá lại cả tính đúng đắn lẫn khả năng khôi phục, không chỉ tối ưu hiệu năng.

### 5.2. Thể hiện một ràng buộc bằng Java

Để tránh đầu vào lớn vượt phạm vi thiết kế ban đầu mà không có cảnh báo, có thể kiểm tra kích thước tệp trước khi đọc:

~~~java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;

final class ReportInputPolicy {
    // Giới hạn minh họa: phải được chọn theo đo đạc thực tế.
    private static final long MAX_FILE_BYTES = 10L * 1024 * 1024;

    static void validateInput(Path file) throws IOException {
        long size = Files.size(file);
        if (size > MAX_FILE_BYTES) {
            throw new IllegalArgumentException(
                    "Input file exceeds supported size: " + size);
        }
    }
}
~~~

Kiểm tra này giúp **từ chối sớm một số trường hợp ngoài giới hạn**. Nó không tự đảm bảo job không hết bộ nhớ: biểu diễn các dòng và đối tượng Java có thể chiếm nhiều bộ nhớ hơn kích thước tệp, và tệp có thể thay đổi sau khi kiểm tra. Quyết định vẫn cần đo bộ nhớ đỉnh, xử lý lỗi rõ ràng và chọn phương án đọc phù hợp.

Ngoài ra, **ngưỡng từ chối thực thi** và **ngưỡng yêu cầu xem xét lại** có vai trò khác nhau: 10 MiB là giới hạn minh họa để từ chối; 8 MiB là tín hiệu cần đánh giá trước khi chạm giới hạn. Không nên nhầm cảnh báo với bằng chứng rằng hệ thống đã hỏng.

### 5.3. Diễn biến sau vài tháng

Giả sử lần đo mới cho thấy p95 đầu vào đạt 9 MiB trong hơn một tuần. Điều kiện R1 đã xảy ra. Nhóm có thể:

1. Xác nhận số liệu, loại trừ lỗi đo hoặc thay đổi định dạng đầu vào.
2. Đo thời gian xử lý và peak heap với bộ dữ liệu đại diện hiện tại.
3. Thử phiên bản đọc theo luồng trên cùng bộ ca, so sánh tính đúng và chi phí triển khai.
4. Chọn giữ A thêm một giai đoạn với giới hạn mới có căn cứ, hoặc chuyển sang B nếu lợi ích rõ ràng.
5. Ghi lại quyết định mới, liên kết bản ghi cũ, cập nhật điều kiện theo dõi và người phụ trách.

Điều kiện R1 làm xuất hiện **nghĩa vụ xem xét**, chứ không tự động chứng minh B tốt hơn. Đây là trọng tâm của việc quản lý đánh đổi có trách nhiệm.

## 6. Cách tổ chức việc xem xét lại

Một bản ghi chỉ có giá trị khi có cách để phát hiện và xử lý tín hiệu.

### 6.1. Gắn tín hiệu với nguồn kiểm chứng

Ví dụ:

- Lưu lượng và độ trễ: metric hoặc dashboard có đơn vị, khoảng thời gian và cách tổng hợp rõ ràng.
- Mức sử dụng bộ nhớ: thống kê từ các lần chạy thực, lưu cả dữ liệu cao điểm.
- Số người sử dụng và nhu cầu mới: yêu cầu sản phẩm, thông tin từ vận hành.
- Chi phí sửa đổi: số vị trí phải sửa, lỗi hồi quy, thời gian hoàn thành các thay đổi cùng loại.
- Thay đổi phụ thuộc: thông báo bỏ hỗ trợ API, lịch cập nhật nền tảng, cảnh báo bảo mật.

Một chỉ số trung bình có thể che khuất trường hợp xấu. Với thời gian phản hồi hoặc kích thước dữ liệu, **p95/p99, giá trị đỉnh và xu hướng** thường bổ sung thông tin quan trọng. Tuy nhiên, phải ghi rõ cửa sổ thời gian và khối lượng mẫu để tránh kết luận từ vài điểm dữ liệu nhiễu.

### 6.2. Tạo quy trình khi tín hiệu xuất hiện

~~~mermaid
flowchart TD
    A[Quyết định được ghi cùng giả thiết] --> B[Theo dõi chỉ số, sự kiện và mốc rà soát]
    B --> C{Điều kiện xem lại xuất hiện?}
    C -- Chưa --> B
    C -- Có --> D[Xác minh dữ kiện và bối cảnh mới]
    D --> E[Đánh giá phương án và rủi ro]
    E --> F{Phương án hiện tại còn phù hợp?}
    F -- Có --> G[Ghi lý do giữ nguyên và ngưỡng mới nếu cần]
    F -- Không --> H[Lập kế hoạch thay đổi và kiểm chứng]
    G --> B
    H --> I[Cập nhật quyết định, kiểm thử và theo dõi]
    I --> B
~~~

Khi điều kiện đã xuất hiện, không nên đóng việc chỉ bằng câu “đã xem”. Kết quả tối thiểu cần nêu: **đã kiểm tra gì, kết luận ra sao, ai đồng ý, bước tiếp theo hoặc mốc xem lại nào**. Nếu quyết định dẫn tới thay đổi code, phải thực hiện kiểm thử và đánh giá tác động phù hợp.

### 6.3. Chọn nơi lưu phù hợp

| Quy mô quyết định | Nơi ghi khả dĩ | Điều cần bảo đảm |
| --- | --- | --- |
| Thỏa hiệp cục bộ trong một thay đổi nhỏ | Pull request hoặc issue | Giả thiết, tác động, điều kiện xem lại dễ tìm |
| Quyết định ở cấp thành phần/hệ thống | ADR hoặc tài liệu thiết kế trong repository | Lý do, phương án thay thế, liên kết đến các lần thay đổi sau |
| Tạm hoãn cải tiến tạo chi phí bảo trì | Technical-debt backlog | Chi phí, rủi ro, người phụ trách, điều kiện ưu tiên xử lý |
| Giới hạn phải theo dõi liên tục | Metric, cảnh báo và tài liệu vận hành | Tín hiệu có nguồn đo và có người nhận, không chỉ ghi trong tài liệu |

Bình luận trong mã hữu ích khi một giả thiết giải thích một đoạn logic khó hiểu; tuy nhiên nó không thay thế bản ghi quyết định có phạm vi rộng. Nếu lặp lại cùng thông tin ở nhiều nơi, hãy có **một nguồn chính** và liên kết đến đó, tránh các bản sao mâu thuẫn nhau.

## 7. Điều chỉnh cách ghi nhận theo tuổi thọ và tác động

Không nên áp dụng một mẫu tài liệu nặng cho mọi đoạn mã. Mức chi tiết có thể tăng cùng thời gian sử dụng, phạm vi ảnh hưởng và độ khó khôi phục.

### Mã thử nghiệm

Với một PoC dùng dữ liệu giả, có thể ghi vài dòng: giả thuyết muốn kiểm tra, điều kiện thử, kết quả đo, giới hạn kết luận và ngày kết thúc. **Điều kiện xem lại** có thể là “trước khi dùng dữ liệu thật hoặc đưa vào sản xuất phải kiểm chứng lại quy mô và tính an toàn”.

Viết quá nhiều tài liệu có thể làm chậm quá trình học; nhưng thiếu giả thiết khiến kết quả thử nghiệm dễ bị diễn giải quá mức. “Chạy được trên 100 bản ghi giả” không chứng minh “an toàn cho một triệu bản ghi thật”.

### Công cụ nội bộ

Nếu script chỉ chạy một lần và có thể hoàn tác, bản ghi trong issue đôi khi đủ. Nếu công cụ xử lý dữ liệu thật hoặc chạy định kỳ, cần ghi rõ quyền, dữ liệu đầu vào, giả thiết về khả năng chạy lại, cách xác nhận kết quả và điều kiện phát hiện rủi ro. Một thay đổi “chuyển từ chỉ đọc sang có quyền ghi” là tín hiệu xem lại bắt buộc dù số dòng mã không đổi nhiều.

### Mã duy trì lâu dài

Với dịch vụ nhiều người dùng và nhiều năm bảo trì, cần lịch sử quyết định, người phụ trách, bằng chứng về hiệu năng và tính đúng đắn, khả năng tương thích, ranh giới API và cơ chế theo dõi. Khi thay đổi yêu cầu nghiệp vụ hoặc hạ tầng, các giả thiết liên quan phải được đánh giá cùng code và kiểm thử.

Nguyên tắc xuyên suốt: đầu tư đúng mức vào **độ tin cậy, khả năng hiểu và khả năng thay đổi** trong bối cảnh cụ thể. Những thuộc tính này liên quan nhưng không đồng nhất: có thể cần ưu tiên an toàn dữ liệu trước khi tối ưu khả năng mở rộng.

## 8. Đánh đổi giữa độ chắc chắn và chi phí đo lường

Không thể xác minh mọi giả thiết trước khi ra quyết định. Đo đạc và thử nghiệm cũng tốn thời gian, chi phí hạ tầng và công sức triển khai. Có thể ưu tiên bằng hai câu hỏi:

1. **Nếu giả thiết sai, thiệt hại lớn đến đâu?**
2. **Chi phí và tốc độ xác minh giả thiết là bao nhiêu?**

Ví dụ:

- “Tên một biến có đủ rõ với nhóm hay không?” thường có thể xử lý qua review thông thường, ít cần thiết lập hệ thống metric.
- “Dữ liệu có thể phục hồi nếu job cập nhật thất bại hay không?” có hậu quả cao; cần kiểm chứng cơ chế sao lưu/khôi phục và khả năng dừng ngay trước khi chạy thật.
- “Lưu lượng dự kiến chỉ tăng nhẹ hay sẽ tăng đột biến?” có thể chưa đo được chính xác; cần ghi phạm vi ước lượng, có phương án quan sát, giới hạn an toàn và mốc cập nhật.

Hệ thống còn có **những giả thiết ẩn**: “đồng hồ giữa máy đồng bộ”, “API bên thứ ba luôn trả dữ liệu đúng định dạng”, “chỉ một tiến trình xử lý cùng một công việc”. Các giả thiết này dễ trở thành nguồn lỗi khi môi trường thay đổi. Review kiến trúc nên tìm những tiền đề có hậu quả cao dù chưa ai viết chúng ra.

Một giả thiết **được chấp nhận** không có nghĩa là không cần kiểm soát. Nếu rủi ro còn lại lớn, cần thêm giới hạn, cảnh báo, kế hoạch phục hồi hoặc thay đổi thiết kế ngay thay vì chỉ thêm một dòng “sẽ xem xét sau”.

## 9. Những sai lầm thường gặp

**Chỉ ghi quyết định mà không ghi điều kiện đi kèm.** “Dùng bộ nhớ đệm cục bộ” không nói rõ giả thiết về số instance, độ tươi dữ liệu hay cách đồng bộ. Người đến sau khó biết lúc nào quyết định hết phù hợp.

**Ghi giả thiết như một sự thật bất biến.** “Hệ thống chỉ có 100 người dùng” có thể đúng hôm nay nhưng sai sau khi ra mắt. Nên lưu nguồn, ngày xác minh, phạm vi và mốc rà soát.

**Đặt điều kiện mơ hồ hoặc không ai theo dõi.** “Nếu hiệu năng kém thì xem lại” không tạo tín hiệu vận hành. Cần ngưỡng phù hợp và người chịu trách nhiệm nhận kết quả.

**Đưa ra ngưỡng quá chính xác dù chưa có dữ liệu.** Một con số tròn không tự trở thành tiêu chuẩn kỹ thuật. Hãy ghi đó là ngưỡng thử nghiệm, giải thích vì sao chọn và khi nào hiệu chỉnh.

**Xem điều kiện kích hoạt như lệnh viết lại ngay.** Thay đổi kiến trúc có thể tạo rủi ro lớn hơn vấn đề hiện tại. Trước tiên cần kiểm tra bằng chứng, so sánh các phương án và ghi rõ quyết định.

**Không cập nhật lịch sử.** Khi phạm vi, phụ thuộc hoặc yêu cầu đã thay đổi, bản ghi cũ vẫn ghi “đang hiệu lực” sẽ gây hiểu lầm. Nên đánh dấu đã thay thế, liên kết bản ghi mới và giữ phần giải thích lịch sử.

**Dùng tài liệu để trì hoãn sửa lỗi nghiêm trọng.** Một bug có khả năng gây mất dữ liệu hoặc lỗ hổng bảo mật cần được xử lý theo mức độ tác động thực tế. Ghi giả thiết và lịch xem lại không thay thế biện pháp bảo vệ cần thiết.

**Biến mọi quyết định nhỏ thành cuộc họp dài.** Quy trình ghi nhận quá nặng khiến nhóm ngừng cập nhật. Chỉ cần lưu thông tin đủ để người khác hiểu và kiểm chứng quyết định, tăng mức chi tiết khi rủi ro tăng.

## 10. Mẫu ngắn áp dụng ngay

~~~markdown
### Quyết định: <tên>
- Ngày / người phụ trách:
- Mục tiêu và phạm vi:
- Phương án được chọn và lý do:
- Phương án khác đã cân nhắc:
- Giả thiết A1: <điều kiện + thời gian áp dụng>
- Bằng chứng / độ tin cậy:
- Đánh đổi và rủi ro nếu A1 sai:
- Điều kiện xem lại: <chỉ số + ngưỡng + thời gian> hoặc <sự kiện>
- Cách phát hiện / người tiếp nhận:
- Hành động khi kích hoạt:
- Mốc rà soát định kỳ:
- Trạng thái và liên kết tới quyết định kế tiếp:
~~~

Có thể sử dụng ba phép kiểm tra trước khi chốt:

- **Kiểm tra tính kiểm chứng:** người không tham gia quyết định có hiểu điều gì sẽ làm giả thiết sai không?
- **Kiểm tra trách nhiệm:** nếu điều kiện xuất hiện ngày mai, có ai biết và có nơi ghi kết luận không?
- **Kiểm tra chất lượng:** nếu giả thiết không còn đúng, phần nào của tính đúng đắn, khả năng hiểu hoặc khả năng thay đổi chịu ảnh hưởng?

### Bài tập tự áp dụng

Một nhóm chỉ có một service ghi dữ liệu và chọn không triển khai cơ chế khóa phân tán. Nhóm dự kiến sau này sẽ chạy nhiều instance. Hãy đề xuất một giả thiết và một điều kiện cần xem lại.

**Gợi ý lời giải:**

- **Giả thiết:** tại thời điểm ra quyết định, chỉ một tiến trình được phép thực thi tác vụ cập nhật có thể gây xung đột trên cùng nhóm bản ghi.
- **Rủi ro nếu sai:** hai tiến trình có thể ghi đè hoặc xử lý trùng, gây sai dữ liệu.
- **Điều kiện xem lại:** trước khi triển khai instance thứ hai có thể chạy cùng tác vụ, hoặc trước khi thêm worker song song, phải đánh giá lại cách phối hợp truy cập và tính idempotent của thao tác.
- **Hành động:** mô phỏng chạy đồng thời, xác định yêu cầu nhất quán, rồi lựa chọn giao dịch, điều kiện cập nhật, khóa hoặc cơ chế điều phối phù hợp theo nguồn dữ liệu. Không mặc định khóa phân tán là phương án duy nhất.

Ở ví dụ này, điều kiện xem lại là **sự kiện kiến trúc cụ thể**, không phải chờ tới khi có lỗi ghi dữ liệu.

## 11. Kết luận

Ghi lại giả thiết và điều kiện cần xem xét lại là cách duy trì **lý do của quyết định kỹ thuật** qua thời gian. Khi nêu rõ bối cảnh, nguồn bằng chứng, rủi ro và dấu hiệu kích hoạt, nhóm có thể chọn giải pháp đơn giản đúng lúc mà vẫn biết khi nào cần điều chỉnh.

Một bản ghi tốt giúp mã nguồn của **CODE_QUALITY_FUNDAMENTALS** tiếp tục **đáng tin cậy khi hoàn cảnh thay đổi, dễ hiểu với người tiếp quản và dễ thay đổi khi giả thiết ban đầu không còn phù hợp**. Điều kiện xem lại khiến đánh đổi trở thành lựa chọn có thể quản lý, thay vì lời hứa “để sau tính” không có điểm kết thúc.
