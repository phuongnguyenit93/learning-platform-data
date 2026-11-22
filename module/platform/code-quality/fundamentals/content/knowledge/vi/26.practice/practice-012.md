# Lập kế hoạch xử lý một khoản nợ kỹ thuật cụ thể

Một nhóm biết module đơn hàng có “nhiều nợ kỹ thuật”, nhưng khi lập kế hoạch sprint lại chưa biết nên bắt đầu từ đâu. Có người muốn viết lại toàn bộ service, người khác muốn tăng coverage, còn người phụ trách sản phẩm cần giao một thay đổi giá mới trong tuần tới. Nếu không xác định rõ khoản nợ nào đang gây chi phí và kế hoạch nào giảm được rủi ro, công việc dễ biến thành một đợt refactor rộng, khó đo kết quả và khó hoàn tác.

**Lập kế hoạch xử lý một khoản nợ kỹ thuật cụ thể** bắt đầu bằng việc chọn một vấn đề có phạm vi xác định, mô tả bằng chứng và tác động, so sánh các phương án, rồi chia công việc thành những bước nhỏ có tiêu chí hoàn thành. Kế hoạch tốt không chỉ nói “refactor class này”; nó giải thích **vì sao cần xử lý, xử lý phần nào, làm theo thứ tự nào, giữ hành vi gì, đo kết quả ra sao và điều gì sẽ khiến nhóm dừng hoặc đổi hướng**.

Bài học thuộc chương **Thực hành** của **CODE_QUALITY_FUNDAMENTALS**. Theo mục tiêu module — hiểu những thuộc tính quyết định mã nguồn có **đáng tin cậy, dễ hiểu và dễ thay đổi hay không** — bài này hướng dẫn lập một kế hoạch thực tế cho một khoản nợ kỹ thuật, từ nhận diện đến theo dõi sau khi hoàn thành.

## 1. Nợ kỹ thuật là gì trong một quyết định cụ thể?

**Nợ kỹ thuật (technical debt)** là chi phí tương lai phát sinh từ một lựa chọn kỹ thuật khiến việc phát triển, vận hành hoặc thay đổi hệ thống tốn kém hơn. Có thể khoản nợ được tạo ra có chủ ý để giao hàng nhanh, hoặc hình thành dần khi yêu cầu và hệ thống thay đổi.

Ví dụ:
- Quy tắc tính giá nằm trong một phương thức điều phối lớn, khiến mỗi lần đổi chính sách phải sửa cả luồng checkout.
- Một module dùng thư viện đã ngừng hỗ trợ, làm tăng rủi ro bảo mật và khó nâng cấp.
- Test phụ thuộc vào database dùng chung, chạy chậm và khó tái hiện.
- Một schema event không có phiên bản rõ, khiến thay đổi producer dễ làm consumer lỗi.
- Cấu hình được sao chép ở nhiều nơi, dẫn đến môi trường chạy không nhất quán.
- Một service giữ state mutable dùng chung, khiến lỗi đồng thời khó chẩn đoán.

Nợ kỹ thuật không đồng nghĩa với:
- Mọi đoạn mã cũ.
- Mọi class dài.
- Mọi cảnh báo từ analyzer.
- Mọi chỗ chưa theo sở thích của reviewer.
- Mọi lựa chọn kiến trúc chưa dùng pattern phổ biến.

Một thiết kế đơn giản có thể là lựa chọn phù hợp dù không “hoàn hảo”. Chỉ nên gọi một vấn đề là khoản nợ cần xử lý khi có **chi phí, rủi ro hoặc giới hạn thay đổi có thể giải thích bằng bối cảnh thực tế**.

### 1.1. Tách nợ kỹ thuật khỏi bug và công việc tính năng

| Loại công việc | Câu hỏi chính | Ví dụ |
| --- | --- | --- |
| **Bug** | Hành vi hiện tại có sai so với hợp đồng không? | Đơn đúng ngưỡng bị tính phí sai |
| **Feature** | Người dùng cần hành vi mới nào? | Thêm phương thức thanh toán |
| **Nợ kỹ thuật** | Cấu trúc hiện tại làm việc cần thiết trở nên đắt hoặc rủi ro ra sao? | Quy tắc giá gắn chặt với I/O nên khó thay đổi và kiểm thử |
| **Vận hành** | Hệ thống có thiếu khả năng quan sát, phục hồi hoặc quản lý không? | Không có cảnh báo khi job nhập liệu bị kẹt |
| **Nâng cấp bắt buộc** | Thành phần nào sắp hết hỗ trợ hoặc không còn đáp ứng yêu cầu? | Nâng runtime do phiên bản hiện tại hết vòng đời |

Một khoản nợ có thể làm bug dễ xảy ra hơn, nhưng kế hoạch cần chỉ ra quan hệ đó. Nếu phát hiện một lỗi đang ảnh hưởng người dùng, cần có **kế hoạch sửa lỗi** phù hợp; không nên trì hoãn việc khắc phục bằng cách chỉ tạo ticket “refactor sau”.

## 2. Chọn một khoản nợ có phạm vi đủ rõ

Danh sách nợ kỹ thuật thường dài. Đừng chọn việc chỉ vì nó “trông xấu” hoặc có nhiều dòng code. Chọn một khoản nợ mà nhóm có thể mô tả được **ranh giới, người chịu tác động và chi phí hiện tại**.

Một ứng viên tốt thường đáp ứng một số câu hỏi:
- Có thể chỉ ra class, module, quy trình hoặc dependency liên quan không?
- Có tình huống thực tế khiến nhóm phải trả chi phí vì vấn đề này không?
- Có bằng chứng như PR phải sửa nhiều nơi, lỗi lặp lại, test chậm, deploy khó hoặc thời gian điều tra cao không?
- Có người sở hữu nghiệp vụ hoặc thành phần để xác nhận tác động không?
- Có thể chia giải pháp thành bước nhỏ, kiểm chứng được không?

### 2.1. Từ mô tả mơ hồ đến khoản nợ cụ thể

| Mô tả ban đầu | Vấn đề của mô tả | Cách thu hẹp |
| --- | --- | --- |
| “Checkout rất rối” | Không biết phần nào và rối gây hậu quả gì | “Quy tắc giảm giá nằm trong `CheckoutService.placeOrder`, test phải khởi tạo DB để kiểm tra ngưỡng” |
| “Cần nâng chất lượng test” | Quá rộng, không có tiêu chí | “`PricingPolicy` chưa có test cho đúng ngưỡng và phép tính hiện gắn với repository” |
| “Nên tách microservice” | Đã chọn giải pháp trước khi xác định vấn đề | “Thay đổi schema đơn hàng buộc ba module phát hành cùng lúc; cần xác định coupling và hợp đồng” |
| “Có nhiều code trùng lặp” | Chưa biết trùng lặp nào cùng ý nghĩa | “Quy tắc kiểm tra quyền tenant được sao chép ở ba endpoint và đã lệch nhau” |
| “Nâng Java cho hiện đại” | Không nêu lợi ích hoặc yêu cầu | “Runtime hiện tại hết hỗ trợ bảo mật vào mốc X; cần kế hoạch nâng runtime và kiểm tra tương thích” |

Một khoản nợ cụ thể có thể được viết trong một câu:

> “Quy tắc tính giá của checkout đang trộn trong phương thức điều phối có phụ thuộc database; vì vậy thay đổi chính sách phải chạy integration test chậm và từng gây sai sót ở ngưỡng, nên nhóm cần tách phần tính toán thuần và bảo vệ bằng test biên.”

Câu này xác định **vị trí, chi phí, rủi ro và hướng cải thiện sơ bộ** mà chưa cam kết phải viết lại toàn bộ module.

## 3. Thu thập bằng chứng trước khi đề xuất giải pháp

Một kế hoạch dựa trên bằng chứng dễ được review và ưu tiên hơn một nhận xét cảm tính.

### 3.1. Bằng chứng về chi phí thay đổi

Có thể thu thập:
- Số PR trong một khoảng thời gian chạm vào vùng mã.
- Số file hoặc module thường phải sửa cùng nhau.
- Thời gian từ khi bắt đầu sửa đến khi review/merge.
- Số vòng review cần thiết để làm rõ cùng một quy tắc.
- Số lần phải chạy integration suite chỉ để kiểm tra logic thuần.
- Thời gian điều tra khi xảy ra regression.
- Số thay đổi bị trì hoãn do thiếu owner hoặc tài liệu.

Những số liệu này cần có **cửa sổ thời gian và cách đếm rõ**. Ví dụ “6 PR trong 90 ngày chạm vào PricingPolicy” cụ thể hơn “file này thường thay đổi”. Nhưng số PR cao tự nó không chứng minh thiết kế tệ; sản phẩm có thể đang phát triển đúng kế hoạch.

### 3.2. Bằng chứng về rủi ro và độ tin cậy

- Lỗi đã xác nhận và incident liên quan.
- Regression test còn thiếu.
- Đường dữ liệu hoặc quyền truy cập khó kiểm tra.
- Dependency đã hết hỗ trợ hoặc có lỗ hổng.
- Tác dụng phụ và trạng thái dùng chung không có ranh giới rõ.
- Cảnh báo analyzer đã được xác minh.
- Thiếu backup, rollback hoặc quan sát ở luồng quan trọng.

Phân biệt **lỗi đã xảy ra**, **điều kiện có thể gây lỗi** và **giả thuyết chưa được kiểm tra**. Không ghi một rủi ro giả định thành incident đã xảy ra.

### 3.3. Bằng chứng từ người sử dụng và người bảo trì

Nói chuyện với người thường xuyên thay đổi hoặc vận hành thành phần:
- Họ phải đọc những phần nào trước khi sửa?
- Bước nào thường làm PR bị kéo dài?
- Có loại lỗi nào lặp lại?
- Khi có sự cố, dữ liệu nào khó tìm?
- Phần nào chỉ một người hiểu?
- Có thay đổi sắp tới nào sẽ chạm vào vùng này?

Ý kiến cá nhân là đầu mối để điều tra. Hãy đối chiếu với code, lịch sử, test, metric và yêu cầu.

## 4. Đánh giá tác động: ai đang trả chi phí?

Một khoản nợ đáng ưu tiên khi nó gây ảnh hưởng có ý nghĩa. Tác động có thể nằm ở nhiều khía cạnh:

| Khía cạnh | Câu hỏi |
| --- | --- |
| **Tính đúng đắn** | Cấu trúc hiện tại có làm lỗi nghiệp vụ dễ xuất hiện hoặc khó phát hiện không? |
| **Bảo mật** | Có làm kiểm tra quyền, dữ liệu nhạy cảm hoặc cập nhật dependency khó kiểm soát không? |
| **Độ tin cậy** | Có tăng khả năng timeout, retry sai, ghi trùng hoặc mất dữ liệu không? |
| **Khả năng thay đổi** | Một yêu cầu bình thường phải sửa bao nhiêu nơi và cần hiểu bao nhiêu tầng? |
| **Khả năng kiểm thử** | Test có chậm, flaky hoặc phụ thuộc môi trường không cần thiết? |
| **Vận hành** | Có khó quan sát, rollback, nâng cấp hoặc khôi phục không? |
| **Tổ chức** | Kiến thức tập trung ở một người, tạo nút thắt review hoặc hỗ trợ không? |

### 4.1. Phân biệt tần suất và mức độ hậu quả

Một vùng ít thay đổi nhưng quản lý phân quyền có thể có hậu quả cao nếu sai. Một vùng thay đổi liên tục nhưng được test tốt và dễ rollback có thể có rủi ro thấp hơn.

Không nên chỉ xếp hạng theo:
- Số dòng code.
- Tuổi của file.
- Số finding analyzer.
- Số commit.
- Coverage tổng.
- Điểm complexity.

Các chỉ số đó là tín hiệu. Cần đặt cạnh **xác suất, tác động, khả năng phát hiện và khả năng phục hồi**.

### 4.2. Viết tác động theo dạng có thể kiểm chứng

Thay vì:
> “Code khó bảo trì.”

Hãy viết:
> “Trong 4 thay đổi về chính sách giá gần đây, cả 4 đều phải sửa `CheckoutService` và chạy toàn bộ integration test vì công thức nằm cùng phương thức ghi đơn. Hai lần review yêu cầu làm rõ điều kiện ngưỡng. Tách phép tính thuần có thể giúp kiểm tra chính sách độc lập và giảm phạm vi thay đổi.”

Các con số trong câu trên chỉ nên dùng khi nhóm đã xác minh. Nếu chưa có dữ liệu, viết “các PR gần đây” và ghi rõ cần thu thập thêm.

## 5. Xác định nguyên nhân gốc trước khi chọn giải pháp

Một triệu chứng có thể có nhiều nguyên nhân. Ví dụ “test tính giá chậm” có thể vì:
- Logic tính toán gắn với database.
- Test dùng fixture quá lớn.
- Database test khởi động chậm.
- Mỗi test tạo lại container.
- Test thực sự cần kiểm tra transaction.
- Pipeline chạy quá nhiều test end-to-end.

Nếu chỉ tách method mà test vẫn phải khởi động DB do fixture hoặc setup, khoản nợ chưa được giải quyết.

Dùng câu hỏi:
1. Điều gì đang xảy ra?
2. Khi nào nó xảy ra?
3. Thành phần nào chịu trách nhiệm?
4. Cơ chế nào tạo ra chi phí hoặc rủi ro?
5. Có bằng chứng nào bác bỏ giả thuyết?
6. Nếu thay đổi đề xuất được thực hiện, chi phí nào sẽ giảm?

### 5.1. Phân biệt nguyên nhân với giải pháp

| Quan sát | Giả thuyết nguyên nhân | Giải pháp có thể cân nhắc |
| --- | --- | --- |
| Unit test cần DB | Logic nghiệp vụ gọi repository trực tiếp | Tách hàm thuần hoặc port I/O hẹp |
| Ba endpoint kiểm tra tenant khác nhau | Quy tắc quyền bị sao chép | Tạo policy chung có hợp đồng rõ và test |
| PR sửa nhiều module cùng lúc | Phụ thuộc vòng hoặc hợp đồng không ổn định | Làm rõ boundary, adapter hoặc versioning |
| CI hay timeout | Test chờ thời gian cố định hoặc runner thiếu tài nguyên | Điều tra timing và hạ tầng riêng |
| Nâng dependency khó | Phiên bản bị khóa bởi API nội bộ hoặc cấu hình | Kiểm tra tương thích, nâng theo từng bước |

Không nên quyết định “tách service”, “thêm interface” hoặc “viết lại” trước khi xác nhận nguyên nhân. Một thay đổi nhỏ hơn có thể giải quyết phần lớn chi phí.

## 6. So sánh phương án và chọn phạm vi nhỏ nhất có ích

Với một khoản nợ, thường có nhiều phương án:
- **Giữ nguyên và theo dõi:** phù hợp khi chi phí hiện tại thấp hoặc chưa đủ bằng chứng.
- **Thêm test/quan sát:** giảm rủi ro trước khi thay cấu trúc.
- **Refactor cục bộ:** tách một trách nhiệm, giữ hợp đồng.
- **Thay dependency hoặc cấu hình:** xử lý nguyên nhân ở hạ tầng.
- **Di chuyển dần:** cần khi hợp đồng hoặc schema có nhiều consumer.
- **Viết lại:** chỉ cân nhắc khi chi phí duy trì và giới hạn kiến trúc được chứng minh, có lộ trình chuyển đổi rõ.

| Phương án | Lợi ích | Chi phí/rủi ro |
| --- | --- | --- |
| Giữ nguyên | Không tạo rủi ro thay đổi ngay | Tiếp tục trả chi phí hiện tại |
| Thêm test | Tăng bằng chứng và giảm nguy cơ regression | Không tự giải quyết coupling hoặc cấu trúc |
| Refactor cục bộ | Phạm vi nhỏ, dễ kiểm chứng | Có thể chưa xử lý hết nguyên nhân rộng hơn |
| Thay dependency | Có thể loại bỏ rủi ro hỗ trợ/bảo mật | Tương thích, cấu hình và hành vi thư viện |
| Di chuyển theo giai đoạn | Giữ hệ thống hoạt động trong chuyển đổi | Cần adapter, theo dõi và quản lý hai đường tạm thời |
| Viết lại lớn | Có thể thay đổi ranh giới sâu | Chi phí cao, nguy cơ bỏ sót hành vi và kéo dài bàn giao |

### 6.1. Chọn phương án nhỏ nhất giải quyết được vấn đề

“Nhỏ nhất” không có nghĩa chỉ sửa một dòng. Nó là **phạm vi hẹp nhất đủ làm giảm chi phí hoặc rủi ro đã xác định**.

Nếu nợ nằm ở việc logic giá phụ thuộc JDBC, trích phép tính thuần có thể đủ. Không cần đồng thời đổi framework, schema, định dạng API và cấu trúc deployment.

### 6.2. Ghi rõ điều gì không nằm trong kế hoạch

Một kế hoạch tốt có phần phạm vi không bao gồm:
- Không đổi chính sách giá.
- Không đổi response API.
- Không di chuyển database.
- Không thêm loại tiền mới.
- Không thay toàn bộ checkout orchestration.

Điều này giúp reviewer nhận ra khi PR bắt đầu mở rộng khỏi mục tiêu ban đầu. Nếu phát hiện nhu cầu mới, tạo kế hoạch riêng hoặc điều chỉnh có lý do.

## 7. Ưu tiên khoản nợ trong bối cảnh nguồn lực hữu hạn

Không phải khoản nợ nào cũng cần xử lý ngay. Một cách xem xét định tính là đặt các yếu tố cạnh nhau:

- **Tác động nếu vấn đề tiếp tục tồn tại.**
- **Khả năng vấn đề được kích hoạt hoặc chi phí lặp lại.**
- **Mức độ phơi lộ trước thay đổi sắp tới.**
- **Khả năng phát hiện và phục hồi.**
- **Chi phí và rủi ro của việc xử lý.**
- **Phụ thuộc và thời điểm cần phối hợp.**

Có thể dùng ma trận:

| Hậu quả nếu xảy ra | Tần suất/khả năng gặp thấp | Tần suất/khả năng gặp cao |
| --- | --- | --- |
| **Thấp** | Theo dõi hoặc xử lý khi chạm code | Cân nhắc cải thiện chi phí thay đổi |
| **Cao** | Đánh giá kiểm soát, test và kế hoạch giảm rủi ro | Ưu tiên điều tra và hành động sớm |

Ma trận này là công cụ thảo luận, không phải mô hình xác suất chính xác.

### 7.1. Tránh điểm số tạo cảm giác chính xác giả

Có thể nhóm tạo score để so sánh nhiều khoản nợ, nhưng cần:
- Định nghĩa từng thang đo.
- Giải thích trọng số.
- Ghi độ tin cậy của dữ liệu.
- Không để điểm tổng che rủi ro bảo mật hoặc dữ liệu nghiêm trọng.
- Review kết quả với người hiểu nghiệp vụ.
- Kiểm tra xem thay đổi trọng số nhỏ có đảo thứ tự ưu tiên không.

Với một khoản nợ đơn lẻ, mô tả bằng chứng và quyết định thường hữu ích hơn một điểm 87/100 không rõ nguồn gốc.

### 7.2. Xem lịch thay đổi sắp tới

Một module ít thay đổi có thể trở thành ưu tiên nếu quý tới có tính năng lớn chạm vào nó. Ngược lại, khoản nợ có chi phí nhỏ và chưa nằm trong roadmap có thể được theo dõi.

Ưu tiên không chỉ là “vấn đề nào tệ nhất”, mà còn là **vấn đề nào nên xử lý vào thời điểm nào để tránh chi phí lặp lại hoặc giảm rủi ro của công việc sắp đến**.

## 8. Ví dụ xuyên suốt: tách quy tắc giá khỏi luồng checkout

Giả sử một ứng dụng Java có `CheckoutService` thực hiện nhiều việc trong cùng một phương thức:
- Đọc dòng hàng từ repository.
- Tính subtotal và discount.
- Lưu đơn hàng.
- Gửi thông báo.
- Tạo response cho API.

Mỗi lần thay quy tắc giá, người phát triển phải dựng database trong test. Một lỗi trước đây xảy ra ở đúng ngưỡng giảm giá. Nhóm muốn xử lý khoản nợ này.

### 8.1. Mô tả khoản nợ

> **Khoản nợ:** Quy tắc tính giá đang nằm trong luồng điều phối checkout có phụ thuộc database và thông báo. Điều này làm unit test cho quy tắc giá phải dựng hạ tầng, tăng thời gian phản hồi và khiến thay đổi chính sách có nguy cơ ảnh hưởng phần lưu đơn.

### 8.2. Phạm vi minh họa

- Module: checkout.
- Thành phần chính: `CheckoutService`.
- Phần cần tách: tính subtotal, discount và amount due.
- Hợp đồng cần giữ: cùng input hợp lệ phải cho cùng kết quả; không đổi thời điểm lưu đơn hoặc gửi thông báo.
- Không thuộc phạm vi: thay đổi mức giảm, API response, schema DB hoặc cơ chế thanh toán.

### 8.3. Bằng chứng cần có

Ví dụ dữ liệu giả định để minh họa một kế hoạch:
- 5 PR trong 90 ngày đã chạm vào `CheckoutService`.
- 3 PR thay đổi điều kiện giá.
- 2 lần review phải bổ sung test tích hợp vì không thể gọi phép tính độc lập.
- Có một regression đã xác nhận tại ngưỡng 500.000 VND.
- Test checkout cần database test để xác nhận kết quả cuối.

Các con số này **không phải dữ liệu của repository thực**. Trong một kế hoạch thật, thay bằng link PR, test report và ticket/incident cụ thể.

### 8.4. Nguyên nhân giả định cần xác minh

- Phép tính giá nằm trong phương thức orchestration.
- Không có type kết quả giá độc lập.
- Test gọi đường checkout đầy đủ thay vì kiểm tra policy thuần.
- Quy tắc ngưỡng chưa được bảo vệ bằng test đúng biên.

Nếu điều tra cho thấy test chậm chủ yếu do database container, việc tách phép tính vẫn có ích nhưng có thể không giải quyết toàn bộ thời gian pipeline. Cần đo lại để tránh tuyên bố quá mức.

## 9. Thiết kế các bước thực hiện

Không lập một task duy nhất “refactor CheckoutService”. Hãy chia thành các checkpoint mà mỗi bước có thể review và kiểm chứng.

| Bước | Công việc | Bằng chứng hoàn thành |
| --- | --- | --- |
| **1. Xác nhận hợp đồng** | Ghi quy tắc giá, lỗi đầu vào và hành vi hiện tại | Bảng input/expected được owner xác nhận |
| **2. Bảo vệ hành vi** | Thêm test cho dưới, đúng và trên ngưỡng; trường hợp VIP/không VIP | Test bắt được lỗi toán tử trên bản cũ |
| **3. Trích kết quả giá** | Tạo `PriceQuote` để biểu diễn subtotal, discount, amount due | Test xác nhận giá trị và đơn vị |
| **4. Tách phép tính** | Chuyển công thức sang `PricingPolicy` thuần | Unit test chạy không cần DB |
| **5. Kết nối lại orchestration** | `CheckoutService` gọi policy rồi giữ nguyên lưu đơn/thông báo | Integration test xác nhận toàn luồng |
| **6. Đo và review** | So sánh thời gian test, diff và các lỗi còn lại | Có báo cáo trước/sau, không thay hợp đồng |
| **7. Theo dõi sau merge** | Quan sát regression và trải nghiệm sửa chính sách tiếp theo | Không có regression đã biết; owner xác nhận |

Thứ tự có thể thay đổi nếu hệ thống hiện thiếu test hoặc có hợp đồng khó xác định. Nhưng nên giữ nguyên tắc: **hiểu hành vi trước, bảo vệ hành vi, rồi mới thay cấu trúc**.

### 9.1. Xác định test trước khi tách

Với chính sách minh họa:
- VIP, subtotal 499.999 VND → discount 0.
- VIP, subtotal 500.000 VND → discount 50.000.
- VIP, subtotal 500.001 VND → discount 50.000.
- Không VIP, subtotal 800.000 VND → discount 0.
- Giá trị âm → bị từ chối theo hợp đồng.
- Phép nhân/cộng vượt giới hạn → báo overflow thay vì trả số sai.

Expected phải lấy từ yêu cầu nghiệp vụ, không chỉ sao chép kết quả của code hiện tại nếu code có thể đang sai.

## 10. Ví dụ Java 17: đích đến của khoản nợ

Một type kết quả đơn giản:

~~~java
record PriceQuote(
        String orderId,
        long subtotalVnd,
        long discountVnd,
        long amountDueVnd) {
    PriceQuote {
        if (orderId == null || orderId.isBlank()) {
            throw new IllegalArgumentException(
                    "orderId is required");
        }
        if (subtotalVnd < 0L
                || discountVnd < 0L
                || amountDueVnd < 0L) {
            throw new IllegalArgumentException(
                    "price values must be non-negative");
        }
        if (Math.subtractExact(subtotalVnd, discountVnd)
                != amountDueVnd) {
            throw new IllegalArgumentException(
                    "amountDueVnd does not match quote");
        }
    }
}
~~~

Chính sách giá thuần:

~~~java
final class PricingPolicy {
    private static final long VIP_THRESHOLD_VND = 500_000L;

    PriceQuote quote(
            String orderId,
            long subtotalVnd,
            boolean vip) {

        if (subtotalVnd < 0L) {
            throw new IllegalArgumentException(
                    "subtotalVnd must be non-negative");
        }

        long discountVnd =
                vip && subtotalVnd >= VIP_THRESHOLD_VND
                        ? subtotalVnd / 10L
                        : 0L;

        long amountDueVnd = Math.subtractExact(
                subtotalVnd, discountVnd);

        return new PriceQuote(
                orderId, subtotalVnd, discountVnd, amountDueVnd);
    }
}
~~~

Unit test:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import org.junit.jupiter.api.Test;

class PricingPolicyTest {
    private final PricingPolicy policy = new PricingPolicy();

    @Test
    void discountsVipAtExactThreshold() {
        PriceQuote quote = policy.quote("O-01", 500_000L, true);

        assertEquals(50_000L, quote.discountVnd());
        assertEquals(450_000L, quote.amountDueVnd());
    }

    @Test
    void doesNotDiscountVipBelowThreshold() {
        PriceQuote quote = policy.quote("O-02", 499_999L, true);

        assertEquals(0L, quote.discountVnd());
        assertEquals(499_999L, quote.amountDueVnd());
    }

    @Test
    void doesNotDiscountNonVip() {
        PriceQuote quote = policy.quote("O-03", 800_000L, false);

        assertEquals(0L, quote.discountVnd());
        assertEquals(800_000L, quote.amountDueVnd());
    }

    @Test
    void rejectsNegativeSubtotal() {
        assertThrows(IllegalArgumentException.class,
                () -> policy.quote("O-04", -1L, true));
    }
}
~~~

Ví dụ minh họa **đích cấu trúc** chứ không phải hướng dẫn thay code trực tiếp. Khi áp dụng thật, phải đối chiếu quy tắc làm tròn, loại tiền, giới hạn số, exception và dữ liệu hiện tại. Không tự ý đổi hợp đồng vì đoạn code ví dụ ngắn hơn.

### 10.1. Điều gì được phép thay đổi và điều gì phải giữ?

| Thành phần | Trong kế hoạch này |
| --- | --- |
| Nơi chứa phép tính | Được chuyển sang `PricingPolicy` |
| Kiểu kết quả trung gian | Có thể thêm `PriceQuote` nội bộ |
| Công thức/điều kiện giá | Phải giữ theo hợp đồng đã xác nhận |
| Thứ tự lưu đơn và gửi thông báo | Giữ nguyên |
| API response và schema | Không đổi |
| Database transaction | Không đổi trong phạm vi này |
| Test tính giá | Chuyển sang unit test độc lập |
| Integration test checkout | Vẫn giữ để kiểm tra wiring và side effect |

Ranh giới này giúp reviewer biết refactor đang giải quyết khoản nợ nào và tránh mở rộng PR sang feature hoặc migration.

## 11. Lập lịch và chia công việc

Một kế hoạch có thể chia thành các task nhỏ:

| Task | Phụ thuộc | Ước lượng minh họa | Người chịu trách nhiệm |
| --- | --- | --- | --- |
| Xác nhận đặc tả và ví dụ biên | Không | 0,5 ngày | Dev + owner nghiệp vụ |
| Bổ sung regression test | Đặc tả đã xác nhận | 0,5–1 ngày | Dev |
| Tách `PriceQuote` và policy | Test baseline xanh | 1 ngày | Dev |
| Kết nối checkout và integration test | Policy có unit test | 0,5–1 ngày | Dev + reviewer |
| Theo dõi sau merge | Deploy thành công | Theo cửa sổ quan sát | Owner module |

Đây là ước lượng giả định để minh họa, không phải cam kết thời gian. Hãy tính cả:
- Thời gian review.
- Chờ người sở hữu nghiệp vụ xác nhận.
- Chạy test tích hợp hoặc môi trường staging.
- Phụ thuộc team khác.
- Rủi ro phải điều tra thêm.
- Chi phí triển khai và theo dõi.

Không nên cộng các task thành một con số chắc chắn nếu còn nhiều giả thiết chưa xác minh. Ghi **ước lượng và độ tin cậy** hoặc dùng khoảng thời gian.

### 11.1. Xác định owner theo trách nhiệm

Một task có thể cần nhiều vai:
- **Owner kỹ thuật:** chịu trách nhiệm thay đổi và chất lượng triển khai.
- **Owner nghiệp vụ:** xác nhận hợp đồng tính giá.
- **Reviewer:** kiểm tra cấu trúc, test và phạm vi.
- **Owner vận hành:** xác nhận khả năng quan sát/triển khai nếu có tác động runtime.

Một người có thể giữ nhiều vai trong nhóm nhỏ. Điều quan trọng là không để câu hỏi quan trọng “không thuộc về ai”.

## 12. Rủi ro, phụ thuộc và điều kiện dừng

Mọi kế hoạch đều có giả thiết. Hãy ghi chúng trước khi bắt đầu.

| Rủi ro/giả thiết | Hậu quả nếu sai | Cách giảm thiểu |
| --- | --- | --- |
| Test hiện tại phản ánh đúng đặc tả | Có thể khóa bug cũ | Owner xác nhận expected và ghi rõ bug đã biết |
| Không có caller ngoài module | Có thể phá API | Tìm reference, kiểm tra public contract và cấu hình |
| Policy không có state | Có thể vô tình thay đổi lifecycle/concurrency | Giữ policy stateless, review scope |
| Không đổi transaction | Có thể làm side effect xảy ra sai thứ tự | Giữ orchestration, integration test |
| Test chậm do coupling logic/I/O | Refactor không giảm thời gian | Đo riêng thời gian unit và integration trước/sau |
| Không có thay đổi schema | Rollback đơn giản hơn | Giữ phạm vi, không trộn migration |

### 12.1. Điều kiện dừng hoặc đổi kế hoạch

Dừng để đánh giá lại nếu:
- Không xác định được hợp đồng tính giá.
- Test baseline cho thấy behavior cũ đang sai và cần quyết định sửa bug riêng.
- Phát hiện caller ngoài module hoặc API public phụ thuộc cấu trúc cũ.
- Tách policy buộc phải đổi transaction hoặc thứ tự side effect.
- Phần lớn thời gian test chậm đến từ hạ tầng, không phải coupling đã chọn.
- PR bắt đầu kéo theo schema, API hoặc payment flow ngoài phạm vi.

Dừng không có nghĩa thất bại. Nó giúp tránh tiếp tục đầu tư vào một giả thuyết đã bị bằng chứng bác bỏ.

## 13. Tiêu chí hoàn thành phải đo được

Không dùng câu “code sạch hơn” làm tiêu chí duy nhất. Viết tiêu chí theo kết quả quan sát:

- `PricingPolicy` có thể được unit test mà không cần khởi tạo database hoặc gửi thông báo.
- Các trường hợp dưới, đúng và trên ngưỡng được kiểm tra với expected từ đặc tả.
- Integration test xác nhận checkout vẫn lưu đơn và phát thông báo theo hợp đồng hiện tại.
- API response, schema và thứ tự side effect không thay đổi.
- Không thêm finding blocker mới từ các kiểm tra bắt buộc.
- Reviewer có thể tìm nơi thay đổi quy tắc giá mà không phải lần theo repository hoặc notification adapter.
- Thời gian chạy test policy được đo và báo cáo; không tuyên bố cải thiện nếu không có số liệu so sánh tương đương.
- Tài liệu module hoặc ghi chú thiết kế được cập nhật nếu cách tìm policy đã thay đổi.

### 13.1. Chọn metric đúng với mục tiêu

| Mục tiêu | Metric/bằng chứng |
| --- | --- |
| Test giá độc lập | Test chạy không cần DB; thời gian chạy riêng |
| Bảo vệ đúng hành vi | Test oracle cho trường hợp biên |
| Giảm phạm vi thay đổi | Số nơi phải sửa khi đổi policy trong thay đổi tiếp theo |
| Giảm lỗi lặp lại | Regression cùng nguyên nhân trong cửa sổ theo dõi |
| Giữ side effect | Integration test và đối chiếu thứ tự |
| Dễ tiếp quản | Reviewer hoặc thành viên khác giải thích được luồng mới |

Không phải metric nào cũng cần đặt thành KPI. Một số tiêu chí được xác nhận qua test và review là đủ.

## 14. Kế hoạch rollout và hoàn tác

Với refactor nội bộ không đổi hợp đồng, rollout có thể đơn giản. Nhưng vẫn cần biết:
- Có thể revert commit nếu phát hiện regression không?
- Artifact trước có tương thích với dữ liệu hiện tại không?
- Có thay đổi cấu hình hoặc wiring không?
- Có side effect mới hoặc thay đổi thứ tự không?
- Có cách theo dõi lỗi sau deploy không?

Trong ví dụ tách policy thuần, nếu API, schema và thứ tự side effect giữ nguyên, revert source thường khả thi hơn một migration. Tuy vậy, cần xác minh cách DI khởi tạo policy và integration tests trên môi trường đại diện.

Nếu kế hoạch bắt đầu kéo theo schema hoặc event version, hãy tách phần đó thành kế hoạch tương thích riêng. **Git revert không hoàn tác dữ liệu đã ghi hoặc message đã gửi.**

### 14.1. Dấu hiệu cần rollback hoặc dừng rollout

- Tỷ lệ lỗi checkout tăng vượt ngưỡng đã thống nhất.
- Tổng tiền hoặc discount không khớp giữa phiên bản cũ và mới.
- Integration test hoặc smoke test cho thấy side effect đổi thứ tự.
- Thời gian phản hồi hoặc lỗi database tăng bất thường do wiring mới.
- Log cho thấy policy được gọi sai hoặc không được khởi tạo đúng.

Các ngưỡng cụ thể phải theo SLO và baseline vận hành của hệ thống, không tự đặt số tùy ý trong kế hoạch.

## 15. Theo dõi sau khi xử lý

Một khoản nợ được coi là hoàn thành khi **vấn đề đã được giải quyết theo tiêu chí và có bằng chứng**, không chỉ khi PR merge.

Sau khi triển khai:
1. Theo dõi metric hoặc lỗi liên quan trong cửa sổ phù hợp.
2. Kiểm tra regression và phản hồi của người dùng/vận hành.
3. Xem thay đổi tiếp theo có thực sự chỉ chạm policy khi đổi quy tắc giá không.
4. Ghi nhận nợ mới phát sinh hoặc phần chưa xử lý.
5. Cập nhật tài liệu, owner và trạng thái ticket.
6. Rút kinh nghiệm về cách chọn và chia nhỏ khoản nợ.

Không đóng ticket chỉ vì class cũ đã được xóa. Nếu test vẫn phải dựng DB để kiểm tra giá, hoặc mọi thay đổi vẫn cần sửa nhiều nơi, khoản nợ ban đầu có thể chưa được giải quyết.

## 16. Mẫu kế hoạch xử lý một khoản nợ kỹ thuật

Mẫu dưới đây có thể dùng cho một issue hoặc tài liệu ngắn. Không cần điền mọi trường với độ chi tiết như nhau; phần nào chưa biết nên ghi rõ “chưa xác minh”.

~~~markdown
# TECH-DEBT-012 — <tên khoản nợ>

## 1. Mô tả
- Vị trí/module:
- Hành vi hoặc cấu trúc hiện tại:
- Vấn đề cụ thể:
- Vì sao đây là nợ kỹ thuật, không chỉ là sở thích:

## 2. Bằng chứng
- PR/incident/test/log liên quan:
- Cửa sổ và cách đo:
- Tác động đã xác nhận:
- Giả thiết chưa xác minh:

## 3. Tác động
- Người dùng/nghiệp vụ bị ảnh hưởng:
- Rủi ro correctness/security/reliability:
- Chi phí thay đổi/kiểm thử/vận hành:
- Nếu trì hoãn thì điều gì có thể xảy ra?

## 4. Phương án
- Giữ nguyên và theo dõi:
- Cải thiện nhỏ:
- Phương án rộng hơn:
- Trade-off và rủi ro của từng phương án:
- Phương án được chọn và lý do:

## 5. Phạm vi
- Bao gồm:
- Không bao gồm:
- Consumer/dependency liên quan:

## 6. Kế hoạch từng bước
1. <bước> — owner — bằng chứng hoàn thành
2. <bước> — owner — bằng chứng hoàn thành
3. <bước> — owner — bằng chứng hoàn thành

## 7. Kiểm thử và chấp nhận
- Baseline:
- Unit/integration/contract tests:
- Expected và trường hợp biên:
- Tiêu chí cấu trúc:
- Tiêu chí vận hành:

## 8. Rủi ro và rollback
- Giả thiết:
- Điều kiện dừng:
- Cách hoàn tác source:
- Tác động dữ liệu/deploy nếu có:
- Người quyết định rollback:

## 9. Theo dõi
- Metric và nguồn:
- Cửa sổ quan sát:
- Owner:
- Điều kiện đóng:
- Phần nợ còn lại hoặc việc tiếp theo:
~~~

## 17. Những sai lầm thường gặp khi lập kế hoạch nợ kỹ thuật

**“Viết lại module” là một kế hoạch.** Không đủ. Cần xác định vấn đề, phạm vi, các bước, hợp đồng và tiêu chí kiểm chứng.

**“Class quá dài nên phải tách.”** Độ dài là tín hiệu, không phải tác động. Cần nêu trách nhiệm bị trộn hoặc chi phí thay đổi cụ thể.

**“Nợ càng cũ càng phải xử lý trước.”** Tuổi không đại diện cho rủi ro. Một khoản mới nhưng liên quan bảo mật có thể quan trọng hơn một khoản cũ ít ảnh hưởng.

**“Coverage tăng là đã trả nợ.”** Coverage không chứng minh test có oracle đúng hoặc cấu trúc đã dễ thay đổi.

**“Cứ thêm interface là giảm coupling.”** Interface không có hợp đồng hoặc ranh giới có ý nghĩa có thể chỉ thêm tầng.

**“Có thể vừa refactor vừa đổi nghiệp vụ để tiết kiệm PR.”** Điều đó làm khó phân biệt hành vi cũ/mới và tăng rủi ro rollback. Chỉ kết hợp khi có lý do rõ và test phân biệt được từng thay đổi.

**“Ước lượng chính xác đến giờ khi chưa rõ nguyên nhân.”** Nên ghi khoảng và độ tin cậy, rồi cập nhật sau bước điều tra.

**“Tổng số finding giảm nghĩa là khoản nợ đã hết.”** Có thể rule bị tắt, file bị loại hoặc finding chuyển vị trí. Phải xác minh bằng chứng.

**“Không cần owner vì ai cũng có thể sửa.”** Công việc không có người chịu trách nhiệm dễ bị trì hoãn và không ai quyết định khi phạm vi thay đổi.

**“Merge xong là đóng ticket.”** Cần theo dõi sau deploy và xác nhận tiêu chí hoàn thành.

**“Nợ kỹ thuật phải được xử lý ngay khi phát hiện.”** Ưu tiên phụ thuộc tác động, khả năng gặp, thời điểm thay đổi và chi phí xử lý. Có thể ghi nhận và theo dõi nếu chưa phải thời điểm phù hợp.

**“Điểm ưu tiên là sự thật khách quan.”** Mọi score đều phụ thuộc định nghĩa và trọng số; phải giải thích, kiểm tra và kết hợp đánh giá của người hiểu hệ thống.

## 18. Bài tập vận dụng

### Tình huống A — Test chậm vì logic và DB trộn lẫn

Một phương thức tính phí gọi repository để lấy cấu hình, tính giá rồi ghi log. Mỗi test mất vài giây vì dựng database.

**Yêu cầu:** viết mô tả khoản nợ trong một hoặc hai câu và đề xuất bằng chứng cần thu thập.

**Gợi ý:** xác định phần tính giá và I/O đang trộn; thu thập thời gian test, số PR thay đổi chính sách, hợp đồng cấu hình và test hiện tại. Không kết luận tách method chắc chắn giảm toàn bộ thời gian nếu DB setup mới là nút thắt chính.

### Tình huống B — Nhiều cảnh báo analyzer trong module cũ

Một module có 150 finding, trong đó 2 finding liên quan dữ liệu nhạy cảm, còn lại chủ yếu là complexity và style.

**Yêu cầu:** lập cách ưu tiên và phạm vi kế hoạch đầu tiên.

**Gợi ý:** triage hai finding nhạy cảm theo quy trình bảo mật; không dùng tổng số để xếp tất cả ngang nhau. Chọn một nhóm nợ có tác động và owner rõ để xử lý theo bước, giữ baseline cho finding còn lại nếu chính sách cho phép.

### Tình huống C — Dependency sắp hết hỗ trợ

Một thư viện xác thực sắp hết hỗ trợ, nhưng có nhiều module phụ thuộc vào API cũ.

**Yêu cầu:** xác định đây là loại nợ nào và những phụ thuộc cần đưa vào kế hoạch.

**Gợi ý:** nợ có thời hạn và rủi ro bảo mật/vận hành. Kiểm tra phiên bản, API dùng, test tương thích, consumer, lịch release và phương án rollback; có thể cần adapter hoặc nâng theo giai đoạn.

### Tình huống D — Refactor rộng không có tiêu chí

Đề xuất “tái cấu trúc toàn bộ OrderService trong sprint này” không nêu lý do, test hoặc phạm vi.

**Yêu cầu:** viết lại thành kế hoạch có thể review.

**Gợi ý:** chọn một trách nhiệm gây chi phí cụ thể, ví dụ tách phép tính giá khỏi lưu đơn; mô tả hành vi phải giữ, test baseline, các bước, tiêu chí hoàn thành và phần ngoài phạm vi.

### Tình huống E — Nợ kỹ thuật có thể chưa cần xử lý

Một helper ít thay đổi, không nằm trên luồng quan trọng và chưa gây chi phí đáng kể. Team muốn xóa vì tên chưa đẹp.

**Yêu cầu:** quyết định có nên lập kế hoạch ngay không.

**Gợi ý:** có thể ghi nhận và theo dõi, hoặc đổi tên trong một thay đổi nhỏ khi chạm tới. Không tạo dự án refactor lớn nếu lợi ích không tương xứng.

### Tình huống F — Khoản nợ làm tăng rủi ro dữ liệu

Một job import không có idempotency. Khi timeout sau khi ghi thành công, retry có thể tạo bản ghi trùng.

**Yêu cầu:** lập các câu hỏi nguyên nhân và bước đầu tiên.

**Gợi ý:** xác định khóa nghiệp vụ, ranh giới transaction, trạng thái timeout không xác định, hành vi retry và cách đối soát. Bảo vệ bằng test cho retry cùng request ID; đánh giá tác động dữ liệu trước khi chọn cách sửa. Đây có thể là ưu tiên cao hơn một khoản nợ readability.

### Tình huống G — Sau refactor, metric không cải thiện

Nhóm đã tách PricingPolicy nhưng test pipeline vẫn chậm vì thời gian khởi động container DB chiếm phần lớn.

**Yêu cầu:** có nên kết luận refactor thất bại?

**Gợi ý:** xem mục tiêu ban đầu. Nếu unit test policy đã độc lập và nhanh, khoản nợ về testability đã giảm; thời gian tổng pipeline là vấn đề khác cần kế hoạch riêng về test environment. Không dùng một metric không trực tiếp đo mục tiêu để phủ nhận mọi kết quả.

### Tình huống H — Phạm vi tăng giữa chừng

Khi tách policy, nhóm phát hiện API response đang dùng tên field không rõ và muốn đổi luôn schema.

**Yêu cầu:** xử lý thế nào?

**Gợi ý:** ghi nhận vấn đề mới và tác động tương thích. Nếu không cần để hoàn thành khoản nợ ban đầu, tách issue/PR riêng; nếu phải đổi cùng, cập nhật kế hoạch, consumer, contract test và rollback trước khi tiếp tục.

## 19. Checklist trước khi đưa kế hoạch vào backlog

- **Khoản nợ:** có một vấn đề cụ thể, không phải nhãn chung “code xấu”?
- **Vị trí:** biết module, thành phần và luồng liên quan?
- **Bằng chứng:** có PR, test, incident, log hoặc quan sát hỗ trợ?
- **Tác động:** giải thích được ai trả chi phí và trong điều kiện nào?
- **Nguyên nhân:** phân biệt triệu chứng với cơ chế tạo ra nợ?
- **Ưu tiên:** cân nhắc hậu quả, khả năng gặp, thời điểm và chi phí xử lý?
- **Phương án:** có so sánh giữ nguyên, cải thiện nhỏ và thay đổi rộng?
- **Phạm vi:** nêu rõ bao gồm và không bao gồm?
- **Bước:** chia được thành checkpoint có thể review và hoàn tác?
- **Kiểm thử:** có baseline, expected và test phù hợp rủi ro?
- **Owner:** có người xác nhận nghiệp vụ, triển khai, review và vận hành khi cần?
- **Rủi ro:** có giả thiết, dependency và điều kiện dừng?
- **Hoàn thành:** tiêu chí đo được và gắn với mục tiêu ban đầu?
- **Theo dõi:** có owner, cửa sổ quan sát và điều kiện đóng?
- **Giao tiếp:** người khác đọc kế hoạch có hiểu vì sao khoản nợ đáng xử lý không?

## 20. Kết luận

**Một khoản nợ kỹ thuật chỉ trở thành công việc có thể thực hiện khi nhóm chuyển nó từ nhận xét mơ hồ thành một quyết định có bằng chứng, phạm vi và tiêu chí hoàn thành.** Bắt đầu bằng một vấn đề cụ thể, tìm nguyên nhân gốc, đánh giá tác động, so sánh phương án và chia thay đổi thành những checkpoint có thể kiểm chứng.

Kế hoạch tốt cũng nói rõ điều gì sẽ không thay đổi, ai chịu trách nhiệm, khi nào cần dừng và làm sao biết khoản nợ đã thực sự giảm. Sau khi triển khai, nhóm phải xem lại bằng chứng và chi phí còn lại, không chỉ đóng ticket vì PR đã merge.

Trong **CODE_QUALITY_FUNDAMENTALS**, lập kế hoạch xử lý một khoản nợ kỹ thuật cụ thể giúp mã **đáng tin cậy hơn nhờ giảm rủi ro đã xác định, dễ hiểu hơn nhờ trách nhiệm và quyết định rõ ràng, và dễ thay đổi hơn nhờ đầu tư đúng phạm vi với kết quả có thể kiểm chứng**.
