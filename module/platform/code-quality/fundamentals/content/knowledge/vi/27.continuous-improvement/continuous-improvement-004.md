# Ưu tiên thay đổi theo tác động, rủi ro và công sức

Một nhóm bảo trì hệ thống có 30 đề xuất cải tiến: giảm thời gian build, bổ sung test cho luồng thanh toán, cập nhật dependency có cảnh báo bảo mật, tách một service khó hiểu, sửa dashboard, giảm truy vấn chậm và chuẩn hóa log. Mỗi đề xuất đều có lý do hợp lý. Nhưng năng lực của nhóm chỉ đủ thực hiện một vài việc trong chu kỳ hiện tại.

Nếu chọn theo người đề xuất lớn tiếng nhất, công việc dễ bị chi phối bởi cảm giác cấp bách. Nếu chỉ chọn việc ít tốn công, nhóm có thể liên tục sửa những vấn đề nhỏ trong khi rủi ro lớn vẫn tồn tại. Nếu cộng mọi thứ thành một điểm số duy nhất, một con số trông khách quan có thể che giấu giả định và sự khác biệt giữa các loại tác động.

**Ưu tiên thay đổi theo tác động, rủi ro và công sức** là cách so sánh các cơ hội cải tiến bằng bằng chứng, bối cảnh và năng lực thực tế. Nhóm cần hiểu thay đổi có thể tạo ra giá trị gì, điều gì có thể xảy ra nếu trì hoãn, cần bao nhiêu công sức và còn bất định nào cần làm rõ trước khi quyết định.

Bài học thuộc chương **Cải thiện liên tục** của module `CODE_QUALITY_FUNDAMENTALS`. Mục tiêu của module là hiểu những thuộc tính quyết định mã nguồn có **đáng tin cậy, dễ hiểu và dễ thay đổi** hay không. Ưu tiên tốt giúp nhóm dành thời gian cho những thay đổi làm chất lượng sản phẩm tốt lên một cách có thể quan sát, thay vì chạy theo số lượng task đã đóng.

Sau bài học, bạn có thể:

- Phân biệt tác động, rủi ro, công sức, độ khẩn cấp và độ bất định.
- Xác định ai chịu ảnh hưởng, đường chạy nào bị tác động và hậu quả nếu không thay đổi.
- So sánh lợi ích của cải tiến với chi phí triển khai, vận hành và cơ hội bị bỏ lỡ.
- Dùng ma trận tác động–công sức hoặc cách xếp hạng đơn giản mà không tạo cảm giác chính xác giả.
- Hiểu cách dùng cost of delay và WSJF, cùng các giới hạn của chúng.
- Ưu tiên rủi ro nghiêm trọng ngay cả khi tần suất thấp hoặc lợi ích khó quy đổi thành tiền.
- Tách việc điều tra để giảm bất định khỏi việc triển khai giải pháp.
- Cân bằng cải tiến ngắn hạn, nợ kỹ thuật, độ tin cậy và năng lực dài hạn.
- Ghi lại lý do chọn, điều kiện xem lại và bằng chứng để cập nhật thứ tự ưu tiên.

## 1. Ưu tiên là quyết định phân bổ năng lực hữu hạn

Một backlog có thể chứa nhiều việc đúng, nhưng không phải việc nào cũng cần làm ngay. Nhóm có giới hạn về:

- Thời gian của developer, reviewer, QA và vận hành.
- Kiến thức chuyên môn và người hiểu các thành phần cũ.
- Cửa sổ triển khai, môi trường test và khả năng phối hợp.
- Ngân sách, cam kết sản phẩm và thời hạn pháp lý.
- Khả năng tiếp nhận thay đổi của hệ thống và người dùng.

Chọn một việc đồng nghĩa với việc chưa chọn một số việc khác. Đó là **chi phí cơ hội**: giá trị của lựa chọn tốt nhất bị trì hoãn hoặc bỏ qua.

Ví dụ, dành hai tuần giảm thời gian build có thể giúp cả nhóm tiết kiệm nhiều giờ trong các tháng tiếp theo. Nhưng nếu một dependency có lỗ hổng nghiêm trọng đang được khai thác, trì hoãn cập nhật có thể tạo rủi ro lớn hơn. Cùng là công việc kỹ thuật, nhưng tác động và thời điểm khác nhau.

Ưu tiên không phải cuộc thi tìm task “hay nhất” theo một tiêu chí. Đó là quyết định **việc nào nên làm trước trong bối cảnh hiện tại, vì sao và điều gì có thể khiến quyết định thay đổi**.

## 2. Tách các chiều đánh giá

Bốn khái niệm thường bị trộn lẫn:

| Chiều | Câu hỏi | Ví dụ |
| --- | --- | --- |
| **Tác động (impact)** | Nếu thay đổi thành công, điều gì được cải thiện hoặc bảo vệ? | Giảm lỗi thanh toán, giảm thời gian build |
| **Rủi ro (risk)** | Điều xấu nào có thể xảy ra nếu không làm hoặc nếu làm sai? | Lộ dữ liệu, mất giao dịch, downtime |
| **Công sức (effort)** | Cần nguồn lực nào để thực hiện và đưa thay đổi vào sử dụng? | 3 ngày công, phối hợp hai nhóm, migration |
| **Bất định (uncertainty)** | Ta chưa biết điều gì có thể làm thay đổi ước lượng hoặc quyết định? | Chưa rõ consumer nào dùng API cũ |

Có thể bổ sung:

- **Độ khẩn cấp:** thời điểm trước khi hậu quả xảy ra hoặc cơ hội biến mất.
- **Độ tin cậy của bằng chứng:** dữ liệu có đủ tốt để hỗ trợ ước lượng không?
- **Phụ thuộc:** có công việc nào phải hoàn thành trước?
- **Khả năng đảo ngược:** nếu lựa chọn sai, có thể rollback hoặc đổi hướng dễ không?

Một task có impact cao chưa chắc khẩn cấp. Một task có effort thấp chưa chắc đáng làm. Một rủi ro xác suất thấp vẫn có thể cần ưu tiên cao nếu hậu quả rất nghiêm trọng.

## 3. Xác định tác động bằng kết quả, không bằng tên task

Tên task như “refactor checkout”, “clean up service” hoặc “improve logging” mô tả hoạt động, chưa nói rõ giá trị.

Hãy chuyển từ hoạt động sang kết quả:

| Hoạt động | Kết quả cần làm rõ |
| --- | --- |
| Refactor checkout | Giảm số lỗi khi thay đổi chính sách giá; giảm số nơi phải sửa cùng một quy tắc |
| Bổ sung test | Phát hiện sớm lỗi ở ngưỡng tính tiền trước khi deploy |
| Giảm thời gian build | Rút ngắn thời gian phản hồi CI cho mọi PR |
| Cập nhật dependency | Loại bỏ phiên bản dễ tổn thương khỏi artifact đang triển khai |
| Tách module | Giảm phụ thuộc chéo và giúp thay đổi một quy tắc không cần build toàn hệ thống |
| Thêm dashboard | Phát hiện sớm giao dịch bị treo và giảm thời gian điều tra |

Một tác động tốt nên nói rõ:

1. **Ai hoặc điều gì được hưởng lợi?** Người dùng, developer, nhóm vận hành, hệ thống tích hợp.
2. **Đường chạy hoặc năng lực nào thay đổi?** Thanh toán, build, deploy, điều tra lỗi.
3. **Điều gì được cải thiện?** Tần suất lỗi, độ trễ, thời gian phục hồi, chi phí thay đổi.
4. **Bằng chứng nào xác nhận?** Incident, metric, test, ticket, lịch sử PR hoặc phản hồi người dùng.
5. **Khi nào lợi ích xuất hiện?** Ngay sau deploy, theo mỗi PR, trong quý tới hoặc chỉ khi tính năng mới được xây dựng.

Tránh nói “code sẽ sạch hơn” như một kết quả duy nhất. Hãy giải thích sự sạch hơn giúp thay đổi nào dễ hơn hoặc rủi ro nào giảm.

## 4. Phân biệt rủi ro với tác động tích cực

Tác động thường nói về lợi ích nếu cải tiến thành công. Rủi ro nói về hậu quả bất lợi và khả năng xảy ra.

Ví dụ, thêm kiểm tra quyền ở endpoint quản trị có thể không làm sản phẩm nhanh hơn, nhưng giảm nguy cơ người không đủ quyền đọc dữ liệu. Đây là thay đổi có giá trị bảo vệ.

Đánh giá rủi ro cần xem:

- **Hậu quả:** điều gì xảy ra nếu lỗi hoặc lỗ hổng bị kích hoạt?
- **Khả năng xảy ra:** điều kiện kích hoạt có thể xuất hiện đến đâu?
- **Exposure:** ai có thể tiếp cận đường chạy hoặc dữ liệu?
- **Phạm vi ảnh hưởng:** một người dùng, một tenant, nhiều dịch vụ hay toàn hệ thống?
- **Khả năng phát hiện:** nhóm có biết sự cố đang xảy ra không?
- **Khả năng phục hồi:** có rollback, backup, idempotency hoặc quy trình xử lý không?

Không nên tự gán xác suất chính xác khi thiếu dữ liệu. Có thể dùng mô tả định tính như “khả năng chưa rõ, hậu quả nghiêm trọng” và quyết định điều tra hoặc giảm thiểu trước.

### Rủi ro thấp xác suất nhưng hậu quả lớn

Một lỗi hiếm trong luồng tính tiền có thể ảnh hưởng hàng nghìn giao dịch nếu xảy ra. Một lỗ hổng phân quyền có thể ít được khai thác nhưng hậu quả lộ dữ liệu rất lớn. Tần suất thấp không tự làm rủi ro thấp.

Với những trường hợp này, dùng điểm trung bình có thể che khuất hậu quả cực đoan. Nên đặt ngưỡng hoặc quy tắc ưu tiên bắt buộc cho một số loại rủi ro như bảo mật, an toàn dữ liệu, tuân thủ và tính toàn vẹn giao dịch.

## 5. Công sức không chỉ là số ngày viết code

Ước lượng effort cần tính cả các công việc đưa thay đổi tới trạng thái dùng được:

- Khảo sát và xác nhận giả định.
- Thiết kế, triển khai và review.
- Unit, integration, contract hoặc performance test.
- Migration, backfill và xác minh dữ liệu.
- Cập nhật tài liệu, cấu hình và dashboard.
- Phối hợp consumer hoặc nhóm sở hữu phụ thuộc.
- Triển khai, quan sát, hỗ trợ rollout và rollback.
- Sửa phát sinh khi phát hiện điều chưa biết.

Một thay đổi ước tính “hai ngày code” có thể cần thêm nhiều thời gian chờ review, môi trường hoặc cửa sổ migration. Phải phân biệt **ngày công** với **thời gian lịch**.

### Ước lượng theo khoảng khi còn bất định

Ví dụ:

| Hạng mục | Effort minh họa |
| --- | ---: |
| Khảo sát consumer và hợp đồng | 1–2 ngày công |
| Bổ sung test và adapter tương thích | 2–4 ngày công |
| Triển khai migration/rollout | 2–5 ngày công |
| Tổng khoảng sơ bộ | 5–11 ngày công |

Các con số chỉ minh họa. Khoảng rộng cho thấy nhóm chưa biết đủ về consumer và migration. Không nên lấy trung điểm 8 ngày rồi trình bày như lời hứa chính xác.

Cũng không nên cộng ngày công thành ngày lịch bằng cách chia cho số người. Phụ thuộc, review và công việc tuần tự có thể khiến lịch dài hơn.

## 6. Dùng bằng chứng để mô tả tác động

Một đề xuất cải tiến có thể dựa trên nhiều loại bằng chứng:

- **Incident và defect:** số lần xảy ra, mức độ nghiêm trọng, thời gian khôi phục.
- **Metric vận hành:** latency, error rate, queue lag, tỷ lệ retry, tài nguyên.
- **Dữ liệu delivery:** thời gian build, thời gian chờ review, lead time, tần suất deploy.
- **Lịch sử thay đổi:** số PR phải sửa cùng một quy tắc, churn, số file bị ảnh hưởng.
- **Test:** nhánh chưa được kiểm tra, test flaky, thời gian chạy.
- **Phản hồi người dùng:** điểm gây khó khăn, thao tác lặp, lỗi hiển thị.
- **Yêu cầu bên ngoài:** deadline, audit, chính sách bảo mật hoặc tương thích.

Ghi nguồn, khoảng thời gian và giới hạn của dữ liệu. Ví dụ “CI chậm” nên đi kèm thời gian chạy p50/p90, số job, khoảng đo và thay đổi gần đây. Một lần build 20 phút không đủ chứng minh build trung bình chậm 20 phút.

### Dữ liệu quá khứ không tự dự đoán tương lai

Nếu module ít thay đổi trong sáu tháng, refactor có thể chưa tạo lợi ích ngay. Nhưng roadmap sắp mở rộng module có thể làm chi phí giữ cấu trúc cũ tăng. Dữ liệu lịch sử cần được đọc cùng kế hoạch sắp tới.

Ngược lại, roadmap chưa chắc sẽ xảy ra. Hãy phân biệt việc đã cam kết với giả định dự báo.

## 7. Ma trận tác động–công sức: công cụ sàng lọc ban đầu

Một cách đơn giản là đặt các đề xuất lên ma trận:

```text
Tác động cao
     |
     |  Ưu tiên xem xét      Lập kế hoạch kỹ
     |  sớm nếu effort thấp  nếu effort lớn
     |
     |  Việc nhỏ có ích      Cân nhắc hoãn,
     |  hoặc quick win       chia nhỏ/điều tra
     |
     +------------------------------------> Công sức
          Thấp                       Cao
Tác động thấp
```

Ma trận giúp mở cuộc thảo luận, không tự quyết định thứ tự. Nó không thể hiện rõ urgency, risk, dependency hoặc độ bất định.

Ví dụ:

| Đề xuất | Tác động | Công sức | Nhận định ban đầu |
| --- | --- | --- | --- |
| Sửa cảnh báo quyền truy cập nghiêm trọng | Rất cao | Thấp–trung bình | Xử lý sớm theo quy trình bảo mật |
| Tự động cache build artifact | Trung bình–cao | Trung bình | Đo lợi ích và thử nghiệm |
| Đổi tên một helper ít dùng | Thấp | Thấp | Chờ khi có thay đổi liên quan |
| Tách module thanh toán lớn | Cao | Cao | Khảo sát, chia giai đoạn |
| Thêm test cho tính phí ở ngưỡng | Cao | Thấp | Có thể ưu tiên sớm |

Các mức là ví dụ định tính. Đừng biến ma trận thành quy tắc “impact cao, effort thấp luôn thắng”: một rủi ro nghiêm trọng hoặc deadline bắt buộc có thể ưu tiên hơn.

## 8. Không tạo điểm số chính xác giả

Nhóm có thể dùng thang 1–5 để hỗ trợ so sánh, nhưng cần nhớ:

- Điểm 4 không nhất thiết gấp đôi điểm 2.
- Các người chấm có thể hiểu “impact cao” khác nhau.
- Một tiêu chí như severity bảo mật không thể cộng tùy tiện với lợi ích trải nghiệm.
- Dữ liệu đầu vào có thể chỉ là phỏng đoán.
- Điểm tổng không cho biết điều gì khiến thứ tự thay đổi.

Ví dụ bảng chấm:

| Đề xuất | Impact (1–5) | Risk reduction (1–5) | Effort (1–5) | Bằng chứng |
| --- | ---: | ---: | ---: | --- |
| Thêm test payment retry | 4 | 5 | 2 | Incident retry trùng |
| Rút ngắn build | 4 | 2 | 3 | CI p90 tăng |
| Đổi tên helper | 1 | 1 | 1 | Chưa có pain point rõ |

Các điểm ở đây chỉ là cách tóm tắt nhận định của nhóm. Không nên cộng 4 + 5 − 2 rồi coi kết quả 7 là đại lượng giá trị khách quan. Trước khi dùng scoring, hãy thống nhất định nghĩa thang điểm và ghi độ tin cậy của bằng chứng.

### Khi nào scoring có ích?

- Có nhiều đề xuất tương tự cần sàng lọc.
- Nhóm dùng cùng định nghĩa và cách chấm.
- Có dữ liệu đủ nhất quán.
- Kết quả được dùng để mở thảo luận, không thay thế quyết định chuyên môn.
- Có thể giải thích vì sao một đề xuất được xếp trên đề xuất khác.

Nếu hai đề xuất có loại rủi ro rất khác, so sánh trực tiếp bằng một điểm có thể không phù hợp. Hãy dùng ngưỡng bắt buộc hoặc phân loại riêng trước khi xếp phần còn lại.

## 9. Value versus effort: giá trị so với công sức

Một cách xếp hạng khác là so sánh giá trị mong đợi với công sức.

Giá trị có thể bao gồm:

- Lợi ích trực tiếp cho người dùng.
- Giảm sự cố và tổn thất.
- Giảm thời gian phát triển trong tương lai.
- Giảm chi phí vận hành.
- Mở khóa một khả năng sản phẩm.
- Giảm bất định hoặc giúp quyết định tiếp theo tốt hơn.

Effort nên tính tổng công sức để hoàn tất thay đổi, không chỉ số dòng code.

Một ma trận value–effort thường giúp nhận ra:

- Giá trị cao, effort thấp: ứng viên làm sớm.
- Giá trị cao, effort cao: chia giai đoạn hoặc lập kế hoạch.
- Giá trị thấp, effort thấp: làm khi có cơ hội hoặc gom cùng việc khác.
- Giá trị thấp, effort cao: cần lý do mạnh hoặc xem xét bỏ.

Nhưng “giá trị” có thể không quy đổi được thành tiền. Cải thiện bảo mật, tuân thủ hoặc khả năng khôi phục đôi khi là điều kiện cần chứ không phải khoản đầu tư tự nguyện.

## 10. Cost of delay: cái giá của việc chờ đợi

**Cost of delay** là giá trị bị mất hoặc chi phí/rủi ro tăng thêm do trì hoãn một thay đổi.

Ví dụ:

- Một dependency có lỗ hổng đang bị khai thác: mỗi ngày trì hoãn duy trì exposure.
- Một tối ưu CI giúp tiết kiệm thời gian cho mọi PR: lợi ích tích lũy theo số lần chạy.
- Một thay đổi contract phải hoàn thành trước khi đối tác ngừng API cũ: trì hoãn có deadline rõ.
- Một refactor không liên quan roadmap: chi phí trì hoãn có thể thấp trong ngắn hạn.

Cost of delay giúp hỏi: **nếu không làm trong chu kỳ này, điều gì sẽ mất đi hoặc trở nên đắt hơn?**

### Không phải mọi lợi ích đều tăng tuyến tính theo thời gian

Một số cơ hội có deadline cứng; một số rủi ro tăng theo exposure; một số lợi ích tích lũy theo lượt sử dụng. Không nên nhân một con số lợi ích theo tuần nếu chưa hiểu cách lợi ích biến đổi.

Hãy ghi:

- Mốc thời gian quan trọng.
- Cơ chế tạo chi phí khi chờ.
- Bằng chứng về tần suất hoặc mức tăng.
- Điều gì sẽ thay đổi nếu trì hoãn thêm một chu kỳ.

Ví dụ, nếu CI chạy 300 lần mỗi tuần và tối ưu giúp tiết kiệm trung bình 2 phút mỗi lần, nhóm có thể ước tính khoảng 600 phút CI time tiết kiệm mỗi tuần. Nhưng không thể kết luận nhóm tiết kiệm đúng 10 giờ lao động: build có thể chạy trên máy khác hoặc trong thời gian chờ không trực tiếp chiếm thời gian developer.

## 11. WSJF: một cách so sánh có điều kiện

**Weighted Shortest Job First (WSJF)** là cách ưu tiên công việc bằng cách so sánh cost of delay với job size. Một biểu diễn phổ biến:

\[
WSJF = \frac{Cost\ of\ Delay}{Job\ Size}
\]

Trong một số cách triển khai, cost of delay được phân thành business value, time criticality và risk reduction/opportunity enablement. Job size đại diện cho công sức tương đối.

Ví dụ minh họa:

| Công việc | Business value | Time criticality | Risk reduction | Job size |
| --- | ---: | ---: | ---: | ---: |
| Vá dependency rủi ro cao | 3 | 5 | 5 | 2 |
| Giảm thời gian CI | 4 | 2 | 2 | 3 |
| Refactor helper ít dùng | 1 | 1 | 1 | 1 |

Nếu các điểm chỉ là thứ bậc do nhóm tự chấm, kết quả WSJF chỉ là **tín hiệu xếp hạng tương đối**. Phép chia không biến điểm thứ bậc thành tỷ lệ đo lường khách quan.

WSJF có ích khi nhóm hiểu các thành phần, dùng cùng thang và cần so sánh nhiều công việc. Nó không phù hợp để thay thế quyết định bắt buộc về bảo mật, tuân thủ hoặc incident.

### Giới hạn của WSJF

- Kết quả phụ thuộc cách chấm cost of delay và job size.
- Điểm có thể thay đổi theo người đánh giá.
- Công việc có dependency hoặc thứ tự bắt buộc không thể xếp độc lập.
- Một rủi ro có hậu quả nghiêm trọng có thể bị điểm trung bình làm lu mờ.
- Chất lượng dữ liệu và giả định quyết định kết quả.
- Tối ưu điểm số có thể khuyến khích chia nhỏ công việc không hợp lý.

Hãy dùng WSJF như công cụ hỗ trợ hội thoại và kiểm tra độ nhạy: nếu thay đổi một giả định nhỏ mà thứ tự đảo lộn, nhóm cần điều tra thêm.

## 12. Đặt rủi ro nghiêm trọng qua ngưỡng ưu tiên riêng

Có những công việc không nên cạnh tranh với quick wins bằng cùng một điểm:

- Lỗ hổng bảo mật đang bị khai thác hoặc có exposure cao.
- Rủi ro mất hoặc sai dữ liệu tài chính.
- Vi phạm yêu cầu pháp lý hoặc hợp đồng sắp tới hạn.
- Khả năng mất dữ liệu hoặc không thể khôi phục.
- Sự cố production đang diễn ra.
- Một điểm lỗi có thể làm toàn bộ dịch vụ ngừng hoạt động.

Nhóm có thể định nghĩa **ngưỡng bắt buộc**: nếu finding đạt điều kiện nhất định, phải kích hoạt quy trình xử lý ngay hoặc có quyết định từ người chịu trách nhiệm rủi ro. Sau khi đáp ứng ngưỡng, các công việc còn lại mới được so sánh bằng ma trận hoặc scoring.

Ngưỡng cần được xác định theo chính sách tổ chức, không tự đặt chỉ từ một bài học. Ví dụ một CVE Critical không tự động đồng nghĩa mọi môi trường phải dừng toàn bộ công việc; nhưng nó phải được triage theo quy trình bảo mật, exposure và thời hạn cụ thể.

## 13. Tính đến phụ thuộc và thứ tự thực hiện

Một đề xuất có impact cao có thể chưa làm được nếu phụ thuộc chưa hoàn thành.

Ví dụ:

```text
A. Thêm metric theo dõi payment retry
          |
          v
B. Triển khai cơ chế idempotency
          |
          v
C. Bật retry tự động cho traffic production
```

Nếu bật retry trước khi có idempotency, nhóm có thể làm tăng giao dịch trùng. Thứ tự công việc là một phần của đánh giá rủi ro.

Khi xem backlog, hỏi:

- Có prerequisite kỹ thuật hoặc nghiệp vụ không?
- Có thể làm song song hay phải tuần tự?
- Có nhóm khác sở hữu dependency không?
- Có thay đổi nào mở khóa nhiều công việc sau?
- Có thể triển khai từng bước mà vẫn giữ trạng thái an toàn?
- Có deadline hoặc release train ràng buộc thứ tự?

Một việc effort thấp có thể là **enabler** cho nhiều thay đổi lớn hơn. Giá trị của nó không chỉ nằm ở kết quả trực tiếp mà còn ở những công việc được mở khóa.

## 14. Giá trị của việc giảm bất định

Khi chưa rõ effort hoặc impact, đừng ép nhóm chọn một con số duy nhất. Có thể ưu tiên một bước khảo sát nhỏ:

- Prototype để kiểm tra khả năng tương thích.
- Benchmark để xác định bottleneck.
- Spike để tìm consumer của API cũ.
- Test characterization để xác nhận hành vi.
- Threat modeling cho đường dữ liệu nhạy cảm.
- Kiểm tra dependency tree và artifact thực tế.

Một spike có giá trị khi kết quả có thể thay đổi quyết định. Nếu câu trả lời không ảnh hưởng thứ tự hoặc phạm vi, việc điều tra có thể chưa đáng làm.

Ví dụ:

```text
Trước khảo sát:
  Refactor payment module: 10–30 ngày công.
  Chưa rõ consumer và transaction boundary.

Spike:
  1–2 ngày công để liệt kê consumer, kiểm tra transaction,
  và chạy prototype với một adapter.

Sau khảo sát:
  Có thể chia thành một bước tách policy 4–6 ngày công
  và một migration riêng 5–9 ngày công.
```

Các con số chỉ minh họa. Spike không phải cam kết hoàn thành refactor; nó mua thêm thông tin để ra quyết định tốt hơn.

## 15. Cân bằng quick wins và cải tiến nền tảng

Nếu backlog chỉ có quick wins, nhóm có thể liên tục sửa những việc nhỏ nhưng không giảm các nguyên nhân gốc. Nếu chỉ làm refactor nền tảng, người dùng có thể không thấy giá trị trong thời gian dài và rủi ro thay đổi lớn tích tụ.

Có thể cân bằng danh mục công việc theo một số nhóm:

| Nhóm | Mục tiêu |
| --- | --- |
| **Reliability/security** | Giảm lỗi, exposure và nguy cơ mất dữ liệu |
| **Delivery flow** | Giảm thời gian phản hồi, build và review |
| **Maintainability** | Giảm coupling, complexity và chi phí thay đổi |
| **Product enablement** | Mở khả năng cho roadmap hoặc nhu cầu người dùng |
| **Operational excellence** | Cải thiện observability, recovery và xử lý sự cố |
| **Learning/uncertainty reduction** | Xác minh giả định và giảm rủi ro quyết định |

Không cần chia ngân sách cứng cho từng nhóm nếu dữ liệu không hỗ trợ. Nhưng việc nhìn danh mục giúp nhận ra nhóm đang bỏ quên một chiều chất lượng.

### Không để “nợ kỹ thuật” trở thành nhãn chung cho mọi việc

Mỗi mục nợ nên mô tả:

- Tình trạng kỹ thuật quan sát được.
- Chi phí hoặc rủi ro nó đang tạo.
- Thành phần và đường chạy bị ảnh hưởng.
- Thay đổi đề xuất và phạm vi.
- Effort theo khoảng cùng giả định.
- Điều kiện khiến việc xử lý trở nên cấp thiết.

Một mục “dọn code cho sạch” không đủ để cạnh tranh với các việc khác. Hãy nói rõ việc giữ nguyên cấu trúc đang làm chậm thay đổi nào hoặc làm tăng rủi ro gì.

## 16. Chia thay đổi lớn thành các bước tạo giá trị

Một cải tiến có effort lớn có thể chia thành bước nhỏ, miễn mỗi bước tạo kết quả có ý nghĩa và không để hệ thống ở trạng thái nguy hiểm.

Ví dụ giảm thời gian build:

1. Đo baseline và tìm job chậm nhất.
2. Cache dependency/artifact có thể tái sử dụng.
3. Chạy job độc lập song song.
4. Tách test chậm khỏi feedback loop nhanh nhưng vẫn giữ gate trước merge.
5. Đo lại p50/p90 và tỷ lệ flaky.
6. Chỉ xóa bước cũ khi bằng chứng cho thấy thay thế an toàn.

Chia nhỏ không phải đổi một dự án thành nhiều ticket chỉ để trông có tiến độ. Mỗi bước cần có tiêu chí hoàn thành, rủi ro và cách đo.

### Tránh tối ưu cục bộ

Nếu bỏ integration test khỏi pipeline PR để build nhanh hơn nhưng lỗi chỉ được phát hiện sau deploy, nhóm có thể giảm thời gian CI và tăng chi phí incident. Tối ưu phải nhìn toàn bộ feedback loop, không chỉ một metric.

## 17. Ví dụ Java: lưu dữ liệu ứng viên cải tiến

Một nhóm có thể biểu diễn đề xuất bằng dữ liệu rõ ràng để phục vụ thảo luận. Ví dụ Java 17:

```java
enum ImprovementArea {
    RELIABILITY,
    SECURITY,
    DELIVERY,
    MAINTAINABILITY,
    PRODUCT
}

record ImprovementCandidate(
        String id,
        String outcome,
        ImprovementArea area,
        int impactScore,
        int riskReductionScore,
        int effortScore,
        String evidence
) {
    ImprovementCandidate {
        if (id == null || id.isBlank()) {
            throw new IllegalArgumentException("id is required");
        }
        if (outcome == null || outcome.isBlank()) {
            throw new IllegalArgumentException("outcome is required");
        }
        if (area == null) {
            throw new IllegalArgumentException("area is required");
        }
        if (impactScore < 1 || impactScore > 5
                || riskReductionScore < 1 || riskReductionScore > 5
                || effortScore < 1 || effortScore > 5) {
            throw new IllegalArgumentException("scores must be 1..5");
        }
        if (evidence == null || evidence.isBlank()) {
            throw new IllegalArgumentException("evidence is required");
        }
    }
}
```

Record này chỉ biểu diễn thông tin để nhóm thảo luận. Nó chưa tạo ra một thuật toán ưu tiên đúng. Các score 1–5 vẫn là nhận định thứ bậc, và field `evidence` dạng chuỗi chỉ là chỗ ghi tham chiếu; hệ thống thật có thể dùng link issue, metric hoặc tài liệu.

Một hàm điểm đơn giản:

```java
int discussionScore(ImprovementCandidate candidate) {
    return candidate.impactScore()
            + candidate.riskReductionScore()
            - candidate.effortScore();
}
```

Tên `discussionScore` cố ý nhấn mạnh đây là **điểm hỗ trợ thảo luận**, không phải giá trị kinh tế hoặc xác suất. Không dùng nó để tự động sắp xếp mọi loại công việc nếu chưa kiểm tra ngưỡng bảo mật, deadline và dependency.

### Test tính hợp lệ của dữ liệu ứng viên

```java
import static org.junit.jupiter.api.Assertions.*;
import org.junit.jupiter.api.Test;

class ImprovementCandidateTest {
    @Test
    void acceptsValidCandidate() {
        ImprovementCandidate candidate = new ImprovementCandidate(
                "IMP-42",
                "Reduce duplicate payment processing",
                ImprovementArea.RELIABILITY,
                5, 5, 3,
                "Linked incident and retry metrics"
        );

        assertEquals("IMP-42", candidate.id());
        assertEquals(ImprovementArea.RELIABILITY, candidate.area());
    }

    @Test
    void rejectsScoreOutsideRange() {
        assertThrows(IllegalArgumentException.class,
                () -> new ImprovementCandidate(
                        "IMP-43",
                        "Improve build time",
                        ImprovementArea.DELIVERY,
                        6, 2, 2,
                        "CI timing report"
                ));
    }

    @Test
    void requiresEvidence() {
        assertThrows(IllegalArgumentException.class,
                () -> new ImprovementCandidate(
                        "IMP-44",
                        "Refactor legacy helper",
                        ImprovementArea.MAINTAINABILITY,
                        2, 1, 2,
                        " "
                ));
    }
}
```

Các test này chỉ kiểm tra tính hợp lệ của record, không kiểm chứng điểm số có phản ánh đúng giá trị. Chất lượng quyết định vẫn phụ thuộc bằng chứng, định nghĩa thang điểm và người chịu trách nhiệm.

## 18. Ra quyết định bằng bảng so sánh minh bạch

Giả sử nhóm cần chọn trong bốn đề xuất:

| Đề xuất | Tác động | Rủi ro nếu trì hoãn | Effort | Bất định | Bước tiếp theo |
| --- | --- | --- | --- | --- | --- |
| Vá dependency có exposure cao | Bảo vệ dữ liệu và dịch vụ | Cao, có thời hạn | 2–4 ngày công | Thấp–trung bình | Triage security và cập nhật có kiểm thử |
| Thêm test cho payment retry | Giảm giao dịch trùng | Cao nếu retry đang bật | 2–3 ngày công | Trung bình | Xác nhận behavior hiện tại và idempotency |
| Giảm thời gian build | Tăng tốc feedback của cả nhóm | Trung bình, tích lũy | 3–6 ngày công | Trung bình | Đo baseline và thử cache |
| Refactor helper ít thay đổi | Tăng readability cục bộ | Thấp hiện tại | 1–2 ngày công | Thấp | Gom với thay đổi liên quan sau |

Một quyết định có thể là:

1. Xử lý dependency theo quy trình bảo mật vì exposure và urgency cao.
2. Khảo sát payment retry song song nếu không xung đột nguồn lực; ưu tiên sửa nếu xác nhận có thể tạo giao dịch trùng.
3. Đo và thử cải thiện build sau khi có capacity.
4. Hoãn helper ít thay đổi cho tới khi có nhu cầu thực tế.

Đây không phải thứ tự phổ quát. Nếu dependency không reachable trong artifact triển khai hoặc đã có mitigation được xác minh, thứ tự có thể đổi. Nếu retry đang gây duplicate trong production, nó có thể trở thành incident ưu tiên cao nhất.

**Bảng giúp nhìn thấy lý do; bằng chứng mới quyết định kết luận.**

## 19. Ghi lại quyết định và điều kiện xem lại

Một quyết định ưu tiên tốt nên ghi:

- Việc được chọn và kết quả mong đợi.
- Những lựa chọn đã cân nhắc.
- Bằng chứng và giả định chính.
- Vì sao việc này đứng trước việc khác.
- Dependency hoặc điều kiện phải hoàn thành trước.
- Owner và năng lực dự kiến.
- Metric hoặc dấu hiệu để xác nhận lợi ích.
- Ngày hoặc sự kiện khiến nhóm xem lại thứ tự.

Ví dụ:

```text
Quyết định:
  Ưu tiên xử lý retry payment trước tối ưu build.

Lý do:
  Incident gần đây cho thấy request retry có thể tạo
  hai lần capture; hậu quả trực tiếp tới giao dịch khách hàng.

Bằng chứng:
  Incident INC-214, trace mẫu, retry configuration.

Giả định:
  Provider hỗ trợ idempotency key theo contract hiện tại.

Bước đầu:
  Xác minh contract và viết test cho timeout/duplicate.

Điều kiện xem lại:
  Nếu provider không hỗ trợ idempotency như giả định,
  thiết kế mitigation khác trước khi bật retry.
```

Ghi lại cả giả định sai và lý do đổi thứ tự. Không chỉnh sửa lịch sử để khiến quyết định cũ trông như đã biết trước mọi thứ.

## 20. Theo dõi kết quả sau khi triển khai

Ưu tiên không kết thúc ở lúc task được merge. Cần xác nhận thay đổi tạo ra tác động mong đợi.

Ví dụ:

| Mục tiêu | Chỉ báo trước thay đổi | Chỉ báo sau thay đổi |
| --- | --- | --- |
| Giảm lỗi retry trùng | Số giao dịch duplicate, incident | Tỷ lệ duplicate và reconciliation |
| Tăng tốc CI | p50/p90 thời gian pipeline | p50/p90 sau thay đổi, flaky rate |
| Giảm chi phí thay đổi | Số file/consumer phải sửa | Phạm vi PR tương tự sau refactor |
| Cải thiện khả năng phục hồi | Thời gian phát hiện/khôi phục | MTTD/MTTR hoặc thời gian theo dõi phù hợp |
| Giảm rủi ro dependency | Artifact chứa phiên bản dễ tổn thương | Scan trên artifact mới và trạng thái advisory |

Không nên chỉ đo một chỉ số. Ví dụ giảm build time nhưng tăng flaky test hoặc lỗi lọt là một kết quả xấu. Giảm số finding bằng cách tắt rule không phải cải thiện bảo mật.

### Chọn baseline và khoảng thời gian hợp lý

So sánh trước/sau cần cùng định nghĩa metric và workload tương đương. Nếu traffic, cấu hình hoặc phiên bản scanner thay đổi, cần ghi nhận để tránh gán nhầm nguyên nhân.

Một cải tiến maintainability có thể chưa thể hiện ngay qua incident rate. Có thể theo dõi chỉ báo gần hơn như thời gian sửa một quy tắc, số consumer bị ảnh hưởng hoặc số lỗi hồi quy trong các thay đổi tiếp theo.

## 21. Cải thiện thứ tự ưu tiên theo chu kỳ

Một backlog không nên được xếp một lần rồi giữ nguyên mãi. Bối cảnh thay đổi:

- Incident mới làm rủi ro tăng.
- Roadmap mới làm một module sắp được thay đổi nhiều.
- Dependency phát hành bản vá.
- Một dự án khác hoàn tất prerequisite.
- Metric cho thấy giả định về tác động không đúng.
- Năng lực hoặc nhân sự chủ chốt thay đổi.
- Một deadline pháp lý hoặc hợp đồng tiến gần.

Nhóm có thể xem lại theo chu kỳ hoặc khi có sự kiện quan trọng. Không cần xếp lại toàn bộ backlog mỗi ngày; tập trung vào những mục có bằng chứng mới hoặc nằm gần đầu danh sách.

### Một vòng lặp cải tiến

```text
Quan sát vấn đề và cơ hội
          |
          v
Thu thập bằng chứng
          |
          v
Đánh giá impact, risk, effort, uncertainty
          |
          v
Chọn việc và ghi lý do
          |
          v
Thực hiện theo bước có thể xác minh
          |
          v
Đo kết quả và rủi ro còn lại
          |
          v
Cập nhật backlog và giả định
          |
          +----------> Lặp lại
```

Vòng lặp này giữ mối liên hệ giữa ưu tiên và kết quả thực tế. Nếu thay đổi không tạo lợi ích như dự kiến, nhóm có thể học và điều chỉnh thay vì tiếp tục đầu tư chỉ vì đã bắt đầu.

## 22. Những sai lầm thường gặp

**Chọn việc dễ nhất trước.** Quick win hữu ích nhưng không nên lấn át rủi ro nghiêm trọng hoặc cơ hội có cost of delay cao.

**Chọn việc có người yêu cầu lớn tiếng nhất.** Quyết định nên dựa trên tác động, bằng chứng và trách nhiệm, không chỉ mức độ chú ý.

**Cộng mọi thứ thành một điểm duy nhất.** Điểm có thể che giấu sự khác nhau giữa rủi ro bảo mật, giá trị sản phẩm và maintainability.

**Dùng effort thấp như bằng chứng của giá trị cao.** Một task nhỏ vẫn có thể không tạo ra lợi ích đáng kể.

**Chỉ đo impact tích cực, bỏ qua rủi ro.** Một thay đổi có thể không tạo feature mới nhưng bảo vệ tính toàn vẹn dữ liệu.

**Xếp hạng mà không xét dependency.** Việc có điểm cao chưa chắc thực hiện được trước prerequisite.

**Dùng P0/P1 cho mọi việc.** Nếu mọi thứ khẩn cấp, nhóm không còn phân biệt được điều gì thực sự cần xử lý ngay.

**Tin số liệu lịch sử mà bỏ qua roadmap.** Hệ thống ít thay đổi trước đây có thể sắp trở thành vùng trọng tâm.

**Đánh giá effort chỉ bằng thời gian code.** Test, review, migration, rollout và phối hợp đều tiêu tốn năng lực.

**Dùng WSJF như công thức khách quan.** Kết quả phụ thuộc cách chấm và giả định; nó không thay thế ngưỡng an toàn hoặc quyết định chuyên môn.

**Bỏ qua bất định.** Một ước lượng chưa rõ cần spike hoặc điều tra, không cần ép thành một số chính xác.

**Không đo kết quả sau khi làm.** Task đóng không chứng minh mục tiêu cải thiện đã đạt.

**Không cập nhật thứ tự ưu tiên.** Backlog cũ có thể không còn phản ánh rủi ro và cơ hội hiện tại.

**Biến nợ kỹ thuật thành lý do chung chung.** Cần nêu chi phí hoặc rủi ro cụ thể mà cấu trúc hiện tại tạo ra.

## 23. Bài tập tình huống

### Tình huống A — Quick win hay rủi ro bảo mật?

Nhóm có hai việc: sửa cảnh báo format mất nửa ngày và nâng dependency có advisory bảo mật cần 3–5 ngày công. Dependency được đóng gói trong artifact production nhưng chưa xác định đường khai thác có reachable hay không.

Hãy so sánh impact, risk, effort, uncertainty và urgency. Bằng chứng nào cần có trước khi quyết định thứ tự? Có cần tạo một bước điều tra riêng không?

### Tình huống B — Tối ưu CI hay refactor module?

CI p90 mất 24 phút; module checkout thường cần sửa nhiều file cho một thay đổi giá. Nhóm có capacity một tuần.

Hãy xác định tác động của mỗi việc, người hưởng lợi, baseline cần đo và cost of delay. Có thể chia một việc thành spike hoặc bước nhỏ nào để giảm bất định?

### Tình huống C — Rủi ro hiếm nhưng hậu quả lớn

Một luồng hoàn tiền có lỗi concurrency chỉ xuất hiện trong điều kiện hiếm nhưng có thể hoàn tiền hai lần. Trong khi đó, nhóm có nhiều task readability nhỏ.

Hãy giải thích vì sao tần suất thấp không đủ để xếp rủi ro thấp. Đề xuất ngưỡng ưu tiên, bằng chứng và biện pháp giảm thiểu trước khi có refactor toàn diện.

### Tình huống D — WSJF cho kết quả bất ngờ

Một đề xuất có business value 5, time criticality 1, risk reduction 1, job size 1; một đề xuất khác có các điểm 3, 4, 5, job size 5. Theo công thức nhóm đang dùng, đề xuất thứ nhất đứng đầu.

Hãy kiểm tra định nghĩa từng thang, giả định về job size và liệu hai việc có cùng nhóm rủi ro hay không. Khi nào nên dùng ngưỡng bắt buộc thay cho xếp hạng?

### Tình huống E — Effort thấp nhưng chưa rõ tác động

Một developer đề xuất đổi tên và tách một helper trong module ít thay đổi, ước lượng một ngày. Không có incident hoặc ticket nào liên quan.

Hãy xác định evidence nào có thể làm tăng mức ưu tiên, và khi nào nên đợi đến lúc có thay đổi liên quan. Vì sao “dễ làm” không tự động có nghĩa “nên làm ngay”?

### Tình huống F — Dependency có deadline

Một API đối tác sẽ ngừng hỗ trợ phiên bản hiện tại sau sáu tuần. Việc nâng cấp cần phối hợp hai nhóm, migration và contract test. Nhóm còn một backlog reliability khác.

Hãy đánh giá cost of delay, dependency, effort theo khoảng và thứ tự rollout. Nêu điều kiện xem lại nếu đối tác thay đổi deadline hoặc cung cấp compatibility layer.

### Tình huống G — Lợi ích không xuất hiện sau refactor

Nhóm đã đầu tư hai tuần tách một service nhưng thời gian triển khai và số lỗi không thay đổi. Các PR tiếp theo vẫn phải sửa nhiều module.

Hãy kiểm tra giả định ban đầu, metric được chọn và ranh giới refactor. Nhóm nên tiếp tục, đổi hướng hay dừng? Bằng chứng nào giúp tránh sunk-cost bias?

### Tình huống H — Backlog có 30 đề xuất

Bạn phải lập kế hoạch chu kỳ tới với các đề xuất về security, reliability, delivery, maintainability và product enablement. Một số có deadline, một số phụ thuộc lẫn nhau, nhiều mục effort chưa rõ.

Hãy phân nhóm, xác định ngưỡng bắt buộc, chọn cách so sánh phần còn lại, tìm spike giảm bất định và ghi lý do cho những việc được hoãn.

Với mỗi tình huống, trả lời theo chuỗi: **kết quả mong muốn → bằng chứng → impact/risk → effort/uncertainty → dependency/urgency → quyết định → cách đo sau triển khai**.

## 24. Ghi nhớ

Ưu tiên thay đổi theo tác động, rủi ro và công sức là quyết định về **nơi nhóm nên đầu tư năng lực tiếp theo và vì sao**.

- Mô tả kết quả cần đạt thay vì chỉ ghi hoạt động kỹ thuật.
- Tách impact, risk, effort, urgency và uncertainty; chúng bổ sung cho nhau nhưng không thể thay thế nhau.
- Dùng bằng chứng từ incident, metric, test, lịch sử thay đổi, roadmap và hợp đồng.
- Xem cả hậu quả của việc trì hoãn, chi phí cơ hội và phụ thuộc.
- Ma trận impact–effort, scoring và WSJF là công cụ hỗ trợ thảo luận, không phải phán quyết khách quan.
- Đặt ngưỡng riêng cho rủi ro nghiêm trọng, bảo mật, dữ liệu và deadline bắt buộc.
- Dùng spike khi thông tin mới có thể thay đổi quyết định; ghi khoảng và giả định thay vì tạo độ chính xác giả.
- Cân bằng reliability, security, delivery, maintainability, product và learning.
- Chia việc lớn thành bước có giá trị và trạng thái tích hợp an toàn.
- Đo kết quả sau triển khai, cập nhật giả định và xem lại backlog khi bối cảnh thay đổi.

Một quyết định ưu tiên tốt không chỉ nói **làm việc gì trước**. Nó giải thích được **giá trị hoặc rủi ro nào đang được xử lý, bằng chứng nào hỗ trợ lựa chọn, công sức nào cần bỏ ra và điều gì sẽ khiến nhóm đổi quyết định**.
