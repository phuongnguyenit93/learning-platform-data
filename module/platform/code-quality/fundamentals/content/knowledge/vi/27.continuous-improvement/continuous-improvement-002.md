# Chọn một mục tiêu cải thiện đủ cụ thể để kiểm chứng

Trong buổi họp cải tiến, cả nhóm thống nhất rằng “chất lượng mã cần tốt hơn”. Mọi người đưa ra nhiều ý tưởng: tăng coverage, giảm độ phức tạp, viết lại module cũ, rút ngắn thời gian review và thêm static analysis. Sau vài tuần, nhóm có thêm nhiều test và một dashboard mới, nhưng vẫn chưa trả lời được câu hỏi: **vấn đề nào của người dùng hoặc của nhóm phát triển đã thực sự giảm?**

Một lời kêu gọi chung thường tạo ra nhiều hoạt động nhưng khó tạo ra một quyết định cải tiến có thể kiểm chứng. Để cải thiện liên tục, nhóm cần chọn **một mục tiêu đủ cụ thể**, có phạm vi, kết quả mong muốn, cách đo, mốc thời gian và người chịu trách nhiệm. Khi mục tiêu rõ, nhóm mới có thể chọn hành động phù hợp và xác định bằng chứng nào cho thấy tình hình đã tốt hơn.

Trong module **CODE_QUALITY_FUNDAMENTALS**, chúng ta học những thuộc tính quyết định mã nguồn có **đáng tin cậy, dễ hiểu và dễ thay đổi hay không**. Ở chương **Cải thiện liên tục**, bài này tập trung vào cách **chọn một mục tiêu cải thiện đủ cụ thể để kiểm chứng**. Trọng tâm là chuyển nhận định mơ hồ thành mục tiêu có thể đo, gắn với một vấn đề thực tế, đồng thời giữ những điều kiện bảo vệ chất lượng không bị hy sinh để đạt chỉ tiêu.

## Mục tiêu học tập

Sau bài học, bạn có thể:

- Phân biệt mong muốn chung, hoạt động cần làm, đầu ra và kết quả cải thiện.
- Chọn vấn đề dựa trên bằng chứng về tác động, tần suất, chi phí và khả năng kiểm soát.
- Viết mục tiêu có phạm vi, đối tượng, baseline, mức mong muốn, thời hạn và người chịu trách nhiệm.
- Chọn outcome metric, leading indicator và guardrail metric phù hợp.
- Xác định định nghĩa đo, mẫu số, nguồn dữ liệu, khoảng quan sát và yếu tố gây nhiễu.
- Tránh đặt chỉ tiêu khiến nhóm tối ưu điểm số nhưng làm giảm chất lượng thực.
- Chuyển mục tiêu thành giả thuyết, thử nghiệm nhỏ và vòng cải tiến có thể đánh giá.

## 1. Bắt đầu từ vấn đề cần cải thiện, không bắt đầu từ giải pháp

Những câu như sau thường xuất hiện trong kế hoạch kỹ thuật:

- “Nâng chất lượng code.”
- “Tăng test coverage.”
- “Giảm technical debt.”
- “Làm CI nhanh hơn.”
- “Cải thiện khả năng maintain.”

Những câu này thể hiện hướng quan tâm, nhưng **chưa chỉ ra vấn đề cụ thể cần giải quyết**. Ví dụ “tăng coverage” là một hoạt động hoặc chỉ số; nó không nói nhóm đang thiếu bằng chứng ở hành vi nào, lỗi nào đang xảy ra hay người dùng đang chịu tác động gì.

Hãy bắt đầu bằng câu hỏi:

> **Điều gì đang xảy ra mà chúng ta muốn thay đổi, và ai đang chịu ảnh hưởng?**

Ví dụ:

| Nhận định ban đầu | Vấn đề cụ thể hơn |
| --- | --- |
| Code khó bảo trì | Mỗi lần thay chính sách phí giao hàng phải sửa hai module và thường phải kiểm tra thủ công để tránh kết quả lệch |
| Test chưa tốt | Các test của chính sách miễn phí giao hàng chưa kiểm tra đúng giá trị ngưỡng, nên lỗi dùng `>` thay vì `>=` đã lọt qua |
| CI quá chậm | p95 thời gian nhận kết quả PR vượt 45 phút, trong đó phần lớn thời gian là chờ runner và khởi tạo môi trường |
| Review chưa hiệu quả | Các PR thay đổi cùng loại thường có nhiều vòng yêu cầu làm rõ vì mục tiêu và hành vi mong đợi không được mô tả |
| Nhiều nợ kỹ thuật | Một module thay đổi thường xuyên gây nhiều lỗi hồi quy và có thời gian khôi phục dài |

Một vấn đề tốt để cải thiện thường có **bằng chứng ban đầu**, một nhóm người hoặc thành phần chịu ảnh hưởng và một cơ chế có thể điều tra.

### Không nhầm triệu chứng với nguyên nhân

Giả sử số lỗi hồi quy tăng. Nguyên nhân có thể là:

- Thiếu test cho một quy tắc nghiệp vụ.
- Module có nhiều phụ thuộc và thay đổi lan rộng.
- CI bỏ qua integration tests.
- PR quá lớn khiến review không đủ sâu.
- Yêu cầu thay đổi liên tục hoặc dữ liệu đầu vào không được kiểm soát.

Nếu nhóm chọn mục tiêu “tăng coverage” trước khi tìm hiểu nguyên nhân, họ có thể viết thêm test không liên quan tới lỗi hồi quy. **Một mục tiêu tốt gắn với vấn đề; giải pháp chỉ được chọn sau khi có giả thuyết về nguyên nhân.**

## 2. Phân biệt hoạt động, đầu ra và kết quả

Một kế hoạch cải tiến thường có ba lớp:

| Lớp | Câu hỏi | Ví dụ |
| --- | --- | --- |
| **Hoạt động (activity)** | Nhóm sẽ làm gì? | Refactor chính sách phí, thêm test biên, cập nhật pipeline |
| **Đầu ra (output)** | Việc làm tạo ra sản phẩm gì? | Một policy dùng chung, test cho 499.999/500.000/500.001 VND |
| **Kết quả (outcome)** | Điều gì trong công việc hoặc hành vi hệ thống thay đổi? | Tỷ lệ hóa đơn lệch phí giảm; một thay đổi chính sách cần sửa ít nơi hơn |

Mục tiêu cải thiện nên mô tả **outcome**. Hoạt động và output là phương tiện để đạt kết quả.

Ví dụ:

- “Viết thêm 20 test” là hoạt động/đầu ra.
- “Tăng branch coverage lên 90%” là mục tiêu chỉ số.
- “Giảm lỗi tính phí sai tại ngưỡng miễn phí trong checkout và hóa đơn” là mục tiêu hướng tới kết quả.

Coverage có thể được dùng làm **leading indicator** nếu test mới thực sự kiểm tra nhánh quan trọng. Nhưng coverage tăng không tự chứng minh lỗi tính phí giảm. Cần test có expected độc lập và dữ liệu về sai lệch thực tế.

### Cây liên kết mục tiêu

~~~text
VẤN ĐỀ
Khách nhận hóa đơn có phí giao hàng khác với phí đã báo
                 |
                 v
GIẢ THUYẾT
Hai module tự triển khai cùng chính sách nên dễ sửa lệch
                 |
                 v
HOẠT ĐỘNG
Gom policy + thêm test biên + kiểm tra hai caller
                 |
                 v
ĐẦU RA
Một nơi sở hữu quy tắc và bộ test hợp đồng
                 |
                 v
KẾT QUẢ MONG MUỐN
Tỷ lệ đơn có chênh lệch phí giảm
                 |
                 v
KIỂM CHỨNG
Đối soát cùng định nghĩa, mẫu số và khoảng thời gian
~~~

Hoạt động có thể hoàn thành đúng kế hoạch nhưng outcome không đổi. Nếu vậy, nhóm cần học từ kết quả và điều chỉnh giả thuyết, không mặc định phải thêm nhiều hoạt động hơn.

## 3. Chọn một vấn đề đủ quan trọng và đủ khả năng tác động

Không phải mọi vấn đề đều nên trở thành mục tiêu của chu kỳ tiếp theo. Hãy cân nhắc ít nhất năm yếu tố:

1. **Tác động:** vấn đề ảnh hưởng tới người dùng, dữ liệu, doanh thu, an toàn hoặc thời gian của nhóm ở mức nào?
2. **Tần suất:** vấn đề xảy ra thường xuyên hay chỉ xuất hiện trong một tình huống hiếm?
3. **Chi phí hiện tại:** nhóm mất bao nhiêu thời gian xử lý, kiểm tra, rollback hoặc hỗ trợ?
4. **Khả năng tác động:** nhóm có quyền và năng lực thay đổi cơ chế gây ra vấn đề không?
5. **Mức bất định:** đã có đủ bằng chứng để hành động hay cần một bước khám phá trước?

### Bảng ưu tiên minh họa

| Vấn đề | Tác động | Bằng chứng hiện có | Khả năng tác động | Bước hợp lý |
| --- | --- | --- | --- | --- |
| Hóa đơn lệch phí giao hàng | Cao, ảnh hưởng số tiền khách trả | Có các trường hợp đối soát lệch | Nhóm sở hữu cả hai module | Chọn làm mục tiêu cải thiện |
| Tên biến khó hiểu ở một tiện ích nội bộ | Thấp, ít thay đổi | Review ghi nhận khó đọc | Có thể sửa nhanh | Gộp vào công việc thường ngày |
| CI đôi lúc chờ runner lâu | Trung bình, ảnh hưởng nhiều PR | Có số liệu queue time | Cần phối hợp nhóm hạ tầng | Khảo sát nguyên nhân trước |
| Một dependency sắp hết hỗ trợ | Có thể cao về bảo mật/vận hành | Có ngày hết hỗ trợ đã xác nhận | Nhóm có thể nâng cấp | Đưa vào kế hoạch rủi ro riêng |

Đây không phải thang điểm cố định. Với rủi ro bảo mật hoặc mất dữ liệu, **mức độ nghiêm trọng có thể quan trọng hơn tần suất**. Một sự cố hiếm nhưng hậu quả rất lớn vẫn có thể là ưu tiên cao.

### Giữ phạm vi đủ nhỏ để có thể học

“Cải thiện toàn bộ chất lượng module” thường quá rộng. Có thể thu hẹp thành:

- “Giảm lỗi lệch phí trong luồng checkout và hóa đơn.”
- “Giảm p95 thời gian phản hồi CI cho các PR chỉ thay đổi module pricing.”
- “Giảm số lần test flaky trong suite integration của billing.”
- “Giảm số nơi cần sửa khi thay ngưỡng miễn phí giao hàng.”

Một mục tiêu nhỏ không có nghĩa tác động nhỏ. Nó giúp nhóm biết **thay đổi nào đã tạo ra kết quả nào**.

## 4. Viết mục tiêu có thể kiểm chứng

Một mục tiêu đủ cụ thể thường trả lời được:

- **Đối tượng/phạm vi:** module, luồng, nhóm người dùng hoặc loại thay đổi nào?
- **Kết quả:** điều gì cần tăng, giảm hoặc được bảo đảm?
- **Baseline:** hiện tại đang ở mức nào?
- **Target:** mức mong muốn là bao nhiêu?
- **Thời hạn:** đánh giá vào thời điểm nào?
- **Phép đo:** dùng định nghĩa, nguồn dữ liệu và mẫu số nào?
- **Owner:** ai chịu trách nhiệm điều phối và báo cáo?
- **Guardrails:** điều gì không được xấu đi khi đạt mục tiêu?

### Mẫu câu mục tiêu

> Trong **[phạm vi/đối tượng]**, giảm hoặc tăng **[kết quả cần thay đổi]** từ **[baseline]** tới **[target]** trước **[thời hạn]**, đo bằng **[định nghĩa metric + nguồn dữ liệu]**, với **[guardrails]** được giữ trong giới hạn đã thống nhất. **[Owner]** chịu trách nhiệm theo dõi và báo cáo.

Ví dụ:

> Trong luồng checkout và lập hóa đơn cho giao hàng STANDARD, giảm tỷ lệ đơn có phí giao hàng khác nhau giữa hai bước từ baseline 8 trường hợp trên 10.000 đơn đủ điều kiện xuống không quá 2 trên 10.000 đơn trong 8 tuần sau khi triển khai. Đo bằng đối soát cùng mã đơn và cùng phiên bản chính sách; theo dõi trên ít nhất 20.000 đơn đủ điều kiện. Không làm tăng p95 thời gian checkout quá 5% so với baseline và không tạo lỗi ghi hóa đơn. Nhóm Billing chịu trách nhiệm báo cáo hằng tuần.

**Các con số trên chỉ là ví dụ minh họa.** Trong dự án thật, target phải dựa trên dữ liệu baseline, mức rủi ro chấp nhận được, số lượng giao dịch và khả năng đo. Nếu 20.000 đơn không đủ để đánh giá một lỗi rất hiếm, nhóm cần kéo dài kỳ quan sát hoặc dùng thêm kiểm thử có kiểm soát.

### Mục tiêu tốt có thể được kiểm tra bằng câu hỏi

| Câu hỏi | Nếu câu trả lời là “không” |
| --- | --- |
| Người khác có hiểu chính xác phạm vi không? | Thu hẹp module, luồng hoặc loại thay đổi |
| Có biết trạng thái hiện tại không? | Thu thập baseline trước khi cam kết target |
| Có định nghĩa metric không? | Viết rõ tử số, mẫu số, nguồn và kỳ đo |
| Có thể ảnh hưởng tới kết quả không? | Chọn vấn đề trong phạm vi kiểm soát hoặc phối hợp owner |
| Có thời hạn đánh giá không? | Chốt mốc và thời gian quan sát |
| Có điều kiện bảo vệ chất lượng không? | Thêm guardrails |
| Có người chịu trách nhiệm không? | Chỉ định owner rõ ràng |

## 5. Dùng SMART như công cụ kiểm tra, không phải công thức máy móc

Khung SMART giúp xem mục tiêu có đủ rõ không:

| Thành phần | Ý nghĩa | Câu hỏi |
| --- | --- | --- |
| **Specific** | Cụ thể | Chính xác phần nào cần cải thiện? |
| **Measurable** | Đo được | Biết bằng chứng nào cho thấy đã tiến bộ? |
| **Achievable** | Có thể đạt | Mục tiêu có phù hợp nguồn lực và phạm vi? |
| **Relevant** | Liên quan | Kết quả có giải quyết vấn đề quan trọng không? |
| **Time-bound** | Có thời hạn | Khi nào đánh giá kết quả? |

SMART không tự bảo đảm mục tiêu đúng. Một target “coverage đạt 100% trong hai tuần” có thể rất cụ thể và đo được nhưng không liên quan tới nguyên nhân lỗi. Một mục tiêu “không có lỗi bảo mật nghiêm trọng” có thể quan trọng nhưng cần định nghĩa phạm vi, cách phát hiện và kỳ quan sát.

Hãy dùng SMART để phát hiện **chỗ còn mơ hồ**, sau đó bổ sung baseline, metric definition và guardrails.

## 6. Chọn chỉ số kết quả và chỉ số dẫn dắt

Một mục tiêu cải thiện thường cần nhiều loại chỉ số:

### Outcome metric — đo kết quả

Outcome metric trả lời điều gì đã thay đổi đối với người dùng, sản phẩm hoặc công việc:

- Tỷ lệ hóa đơn lệch phí.
- Tỷ lệ lỗi hồi quy sau khi phát hành.
- Thời gian trung vị để hoàn thành một thay đổi cùng loại.
- Số sự cố trên một lượng yêu cầu có thể so sánh.
- p95 latency của một luồng nghiệp vụ.

### Leading indicator — tín hiệu dẫn dắt

Leading indicator cho biết nhóm đã thực hiện những điều có khả năng dẫn tới kết quả:

- Số nơi triển khai một quy tắc đã giảm từ hai xuống một.
- Có test cho các giá trị biên đã xác nhận.
- Tỷ lệ PR thay đổi chính sách dùng chung policy mới.
- Tỷ lệ test flaky đã được phân loại và có owner.
- Số module có thể build/test độc lập.

Leading indicator thường xuất hiện sớm hơn outcome, nhưng **không thay thế kết quả cuối**.

### Guardrail metric — chỉ số bảo vệ

Guardrail giúp tránh cải thiện một mặt bằng cách làm xấu mặt khác:

- Không tăng lỗi ghi hóa đơn.
- Không làm p95 checkout vượt giới hạn đã thống nhất.
- Không giảm test tích hợp bảo vệ quyền hoặc transaction.
- Không tăng tỷ lệ rollback hoặc incident nghiêm trọng.
- Không làm số lần review giảm bằng cách bỏ qua reviewer bắt buộc.

### Bộ chỉ số minh họa cho mục tiêu lệch phí

| Loại | Chỉ số | Vai trò |
| --- | --- | --- |
| Outcome | Đơn có chênh lệch phí / tổng đơn đủ điều kiện | Đo vấn đề cần giảm |
| Leading | Số nơi sở hữu quy tắc phí | Kiểm tra thay đổi cấu trúc |
| Leading | Test đạt ở ngay dưới, đúng và trên ngưỡng | Kiểm tra các trường hợp quan trọng đã được bảo vệ |
| Guardrail | p95 thời gian checkout | Ngăn giải pháp làm luồng chậm đáng kể |
| Guardrail | Lỗi ghi hóa đơn và rollback | Bảo vệ tính toàn vẹn và khả năng triển khai |

Không cần theo dõi hàng chục metric cho một mục tiêu nhỏ. Chọn **một outcome chính**, một vài leading indicators có ý nghĩa và guardrails liên quan.

## 7. Định nghĩa phép đo trước khi đặt target

Một metric có tên rõ vẫn có thể gây hiểu nhầm nếu cách tính không được xác định.

Với “tỷ lệ đơn có chênh lệch phí”, cần làm rõ:

| Thành phần | Định nghĩa cần chốt |
| --- | --- |
| **Tử số** | Số mã đơn có phí giao hàng ở checkout khác phí được ghi trên hóa đơn sau khi chuẩn hóa cùng chính sách |
| **Mẫu số** | Tổng số đơn đủ điều kiện có cả hai giá trị để đối soát |
| **Đơn vị** | Số trường hợp trên 10.000 đơn đủ điều kiện |
| **Phạm vi** | Giao hàng STANDARD trong các kênh checkout đã chọn |
| **Thời gian** | Theo tuần, tính từ thời điểm triển khai phiên bản mới |
| **Loại trừ** | Đơn test, đơn bị hủy trước khi lập hóa đơn, dữ liệu không đầy đủ — phải định nghĩa rõ |
| **Nguồn** | Bảng đối soát hoặc sự kiện có mã đơn và phiên bản chính sách |
| **Tần suất** | Tổng hợp hằng tuần, rà soát dữ liệu thiếu |

Công thức:

\[
\text{Tỷ lệ lệch phí trên 10.000 đơn}
=
\frac{\text{Số đơn có chênh lệch phí}}
{\text{Số đơn đủ điều kiện đã đối soát}}
\times 10.000
\]

Nếu một đơn bị tính lệch nhiều lần, tử số nên đếm **đơn duy nhất** hay **sự kiện sai lệch**? Câu trả lời tùy mục tiêu, nhưng phải được quyết định trước và dùng nhất quán.

### Đừng thay đổi định nghĩa giữa baseline và kết quả

Giả sử baseline tính cả đơn EXPRESS nhưng kỳ sau chỉ tính STANDARD. Tỷ lệ có thể giảm dù hệ thống không cải thiện. Nếu đổi cách loại trừ đơn test hoặc bổ sung một nguồn dữ liệu mới, cần ghi rõ và tính lại baseline nếu có thể.

Khi không thể so sánh trực tiếp, hãy báo cáo rằng **phương pháp đo đã thay đổi** và tránh khẳng định mức giảm chính xác.

## 8. Baseline và target phải có cơ sở

Baseline cho biết tình trạng trước khi can thiệp. Nó có thể đến từ:

- Dữ liệu production đã được đối soát.
- Lịch sử PR và ticket trong một khoảng thời gian xác định.
- Thời gian CI và runner-minutes từ pipeline.
- Test failures và incident đã phân loại.
- Một mẫu công việc đại diện được quan sát có phương pháp.

Nếu chưa có baseline, mục tiêu đầu tiên có thể là **thiết lập phép đo đáng tin cậy** thay vì hứa một mức giảm chưa có cơ sở.

### Chọn target theo mức ảnh hưởng và khả năng đo

Không nên đặt target chỉ vì con số tròn hoặc vì nhóm khác đạt được. Hãy xem:

- Baseline biến động nhiều hay ổn định?
- Có đủ lượng quan sát để phân biệt thay đổi với dao động thông thường không?
- Hành động của nhóm có thể ảnh hưởng trực tiếp tới metric không?
- Có giới hạn kỹ thuật hoặc vận hành nào khiến target không khả thi?
- Mức cải thiện có đủ ý nghĩa đối với người dùng hoặc chi phí nhóm không?

Với lỗi hiếm, một vài tuần không có sự cố có thể không đủ bằng chứng. Có thể kết hợp **kiểm thử có chủ đích cho rủi ro** với theo dõi production lâu hơn. Không dùng số sự cố bằng không để kết luận xác suất lỗi đã bằng không.

## 9. Viết giả thuyết có thể bị bác bỏ

Sau khi chọn vấn đề và mục tiêu, hãy nêu giả thuyết về cơ chế:

> Nếu **[thay đổi cụ thể]** được thực hiện trong **[phạm vi]**, thì **[outcome]** sẽ thay đổi theo **[hướng/mức kỳ vọng]**, vì **[cơ chế gây ra kết quả]**. Chúng ta sẽ kiểm chứng bằng **[metric/test]**, đồng thời theo dõi **[guardrails]**.

Ví dụ:

> Nếu checkout và lập hóa đơn cùng gọi một DeliveryFeePolicy, số trường hợp hai luồng áp dụng ngưỡng khác nhau sẽ giảm, vì quy tắc không còn được triển khai độc lập ở hai module. Nhóm sẽ đối soát phí theo mã đơn và kiểm tra test tại 499.999, 500.000 và 500.001 VND. Đồng thời theo dõi p95 checkout và lỗi ghi hóa đơn.

Giả thuyết tốt có thể bị bác bỏ. Nếu policy dùng chung được triển khai nhưng dữ liệu đầu vào giữa hai luồng khác nhau, chênh lệch phí vẫn có thể tồn tại. Khi đó, giả thuyết về nguyên nhân ban đầu chưa đầy đủ.

## 10. Chuyển mục tiêu thành thử nghiệm nhỏ

Đừng bắt đầu bằng một chương trình refactor rộng nếu chưa biết thay đổi có tác động không. Chọn một phạm vi nhỏ có thể quan sát:

1. Chọn một loại đơn hoặc một module có vấn đề đã được xác nhận.
2. Thu thập baseline và xác minh dữ liệu đo.
3. Viết acceptance tests cho quy tắc nghiệp vụ và các giá trị biên.
4. Thay đổi một cơ chế chính: ví dụ đưa chính sách về một thành phần dùng chung.
5. Chạy unit/integration tests và review các caller.
6. Triển khai trong phạm vi có thể quan sát, nếu rủi ro cho phép.
7. Đối soát kết quả trong kỳ đã định.
8. So sánh với baseline, kiểm tra guardrails và ghi lại yếu tố gây nhiễu.

### Ví dụ Java: test bảo vệ ranh giới chính sách

Giả sử quy tắc STANDARD miễn phí từ 500.000 VND trở lên:

~~~java
public final class DeliveryFeePolicy {
    private static final long FREE_THRESHOLD_VND = 500_000;
    private static final long STANDARD_FEE_VND = 20_000;

    public long calculateStandardFee(long subtotalVnd) {
        if (subtotalVnd < 0) {
            throw new IllegalArgumentException("Negative subtotal");
        }
        return subtotalVnd >= FREE_THRESHOLD_VND
            ? 0
            : STANDARD_FEE_VND;
    }
}
~~~

Test:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import org.junit.jupiter.api.Test;

class DeliveryFeePolicyTest {
    private final DeliveryFeePolicy policy = new DeliveryFeePolicy();

    @Test
    void standardDeliveryIsChargedBelowThreshold() {
        assertEquals(20_000, policy.calculateStandardFee(499_999));
    }

    @Test
    void standardDeliveryIsFreeAtThreshold() {
        assertEquals(0, policy.calculateStandardFee(500_000));
    }

    @Test
    void standardDeliveryIsFreeAboveThreshold() {
        assertEquals(0, policy.calculateStandardFee(500_001));
    }

    @Test
    void rejectsNegativeSubtotal() {
        assertThrows(
            IllegalArgumentException.class,
            () -> policy.calculateStandardFee(-1)
        );
    }
}
~~~

Những test này là **leading evidence**: chúng cho thấy các ca đã chọn được bảo vệ trong unit test. Chúng chưa chứng minh tỷ lệ lệch phí production đã giảm. Muốn xác nhận outcome, cần kiểm tra cả hai luồng thực tế và đối soát dữ liệu phù hợp.

## 11. Theo dõi tiến độ mà không biến metric thành mục tiêu sai lệch

Khi một metric trở thành target, nhóm có thể vô tình tối ưu nó bằng cách làm giảm ý nghĩa:

| Target dễ bị thao túng | Hành vi có thể phát sinh | Cách bảo vệ |
| --- | --- | --- |
| Coverage phải đạt 95% | Thêm test chỉ gọi code mà không assert | Review chất lượng expected và test các tình huống rủi ro |
| PR phải đóng trong 1 ngày | Chia nhỏ quá mức hoặc đóng ticket chưa giải quyết | Đo cả chất lượng, rework và lỗi lọt qua |
| Không có bug được báo | Không ghi nhận hoặc phân loại lỗi thấp | Đối chiếu telemetry, hỗ trợ và dữ liệu người dùng |
| CI phải dưới 10 phút | Bỏ integration tests khỏi required gate | Theo dõi lỗi sau merge và giữ suite rộng theo lịch/mốc |
| Số dòng giảm 20% | Gộp code thành abstraction khó hiểu | Review trách nhiệm và chi phí thay đổi thực tế |
| Không có finding | Tắt rule hoặc loại trừ thư mục | Theo dõi cấu hình scan, baseline và suppression |

Không nên dùng metric như công cụ đánh giá cá nhân một cách máy móc. Mục tiêu chất lượng nên giúp nhóm **học và cải thiện hệ thống**, không tạo động lực che giấu vấn đề hoặc chọn việc dễ đạt điểm.

### Theo dõi cả kết quả ngoài dự kiến

Một cải tiến có thể đạt outcome chính nhưng gây tác dụng phụ:

- Tỷ lệ lệch phí giảm nhưng p95 checkout tăng.
- CI nhanh hơn nhưng lỗi integration lọt qua nhiều hơn.
- Số module bị ảnh hưởng giảm nhưng một module chung trở thành điểm nghẽn.
- Số lỗi được ghi nhận giảm nhưng telemetry cũng bị giảm.

Đây là lý do cần guardrails và review định tính, không chỉ một bảng target.

## 12. Dùng vòng PDCA để học từ kết quả

PDCA gồm bốn bước:

| Bước | Việc cần làm | Câu hỏi |
| --- | --- | --- |
| **Plan** | Chọn vấn đề, baseline, giả thuyết, target, metric và guardrails | Ta muốn thay đổi điều gì và vì sao? |
| **Do** | Thử nghiệm thay đổi trong phạm vi kiểm soát | Ta đã thực hiện đúng thay đổi dự kiến chưa? |
| **Check** | Đo outcome, leading indicators và guardrails | Bằng chứng cho thấy điều gì đã thay đổi? |
| **Act** | Chuẩn hóa, điều chỉnh hoặc dừng cách làm | Nên mở rộng, sửa giả thuyết hay quay lại? |

~~~text
        +-----------------------+
        | PLAN                  |
        | Vấn đề, baseline,     |
        | target, giả thuyết    |
        +-----------+-----------+
                    |
                    v
        +-----------------------+
        | DO                    |
        | Thử nghiệm có phạm vi |
        +-----------+-----------+
                    |
                    v
        +-----------------------+
        | CHECK                 |
        | Đo kết quả và rủi ro  |
        +-----------+-----------+
                    |
                    v
        +-----------------------+
        | ACT                   |
        | Chuẩn hóa/điều chỉnh  |
        +-----------+-----------+
                    |
                    +------> Vòng tiếp theo
~~~

Nếu target chưa đạt, không mặc định nhóm làm chưa đủ việc. Có thể:

- Giả thuyết nguyên nhân sai.
- Thay đổi chưa được áp dụng đủ phạm vi.
- Metric đo sai hoặc dữ liệu thiếu.
- Kỳ quan sát chưa đủ dài.
- Yếu tố bên ngoài thay đổi.
- Giải pháp tạo tác dụng phụ làm mất lợi ích.

Một vòng cải tiến có giá trị ngay cả khi giả thuyết bị bác bỏ, miễn là nhóm ghi nhận điều học được và điều chỉnh dựa trên bằng chứng.

## 13. Mẫu mục tiêu cải thiện có thể sử dụng

Có thể dùng mẫu ngắn sau trong issue hoặc kế hoạch nhóm:

~~~text
VẤN ĐỀ
Điều gì đang xảy ra? Ai/cái gì chịu ảnh hưởng?

BẰNG CHỨNG BAN ĐẦU
Incident, PR, dữ liệu, test, phản hồi hoặc quan sát nào xác nhận vấn đề?

PHẠM VI
Module, luồng, loại thay đổi, nhóm người dùng và phần không nằm trong phạm vi.

BASELINE
Metric hiện tại, định nghĩa, tử số/mẫu số, nguồn dữ liệu, khoảng thời gian.

MỤC TIÊU
Kết quả cần đạt, mức thay đổi và thời hạn đánh giá.

GIẢ THUYẾT
Thay đổi nào sẽ tác động tới kết quả, qua cơ chế nào?

LEADING INDICATORS
Những đầu ra/tín hiệu sớm nào cho biết hành động đang đi đúng hướng?

GUARDRAILS
Điều gì không được xấu đi?

OWNER
Ai điều phối, ai cung cấp dữ liệu và ai xác nhận nghiệp vụ?

KẾ HOẠCH KIỂM CHỨNG
Test, review, dashboard, kỳ quan sát và cách xử lý khi không đạt.

RỦI RO / YẾU TỐ GÂY NHIỄU
Điều gì có thể làm kết quả khó diễn giải?
~~~

Mẫu này không cần được điền dài cho mọi công việc. Với một cải tiến nhỏ, có thể rút gọn thành vài dòng; với thay đổi ảnh hưởng tiền, dữ liệu hoặc bảo mật, cần lưu đủ giả định và bằng chứng để người khác xem lại.

## 14. Bài tập tình huống

Một nhóm phát triển hệ thống billing có ba đề xuất cho chu kỳ cải tiến tiếp theo:

**Đề xuất A — Tăng coverage**

> Đưa line coverage của toàn module từ 68% lên 90% trong một tháng.

**Đề xuất B — Giảm lỗi lệch phí**

> Trong luồng checkout và hóa đơn STANDARD, giảm tỷ lệ đơn có phí khác nhau từ baseline đã đo xuống một mức thấp hơn trong tám tuần; đối soát theo mã đơn và giữ p95 checkout trong giới hạn hiện tại.

**Đề xuất C — Viết lại billing**

> Thay toàn bộ module billing bằng framework mới trong quý tới vì mã hiện tại khó đọc.

Nhóm hiện có một số dữ liệu:

- Có nhiều trường hợp hóa đơn và checkout lệch phí tại đúng ngưỡng miễn phí.
- Hai module có hai đoạn code tính phí gần giống nhau.
- Chưa có báo cáo coverage theo branch cho các giá trị biên.
- Chưa thống nhất định nghĩa “đơn lệch phí” và nguồn dữ liệu đối soát.
- Chưa có bằng chứng cho thấy framework hiện tại không thể nâng cấp.

**Câu hỏi A.** Đề xuất nào đang gần với một mục tiêu outcome nhất? Vì sao?

**Câu hỏi B.** Cần thu thập dữ liệu gì trước khi đặt target cụ thể cho đề xuất B?

**Câu hỏi C.** Hãy đề xuất một outcome metric, hai leading indicators và hai guardrails cho mục tiêu B.

**Câu hỏi D.** Vì sao không nên dùng line coverage làm mục tiêu duy nhất?

**Câu hỏi E.** Hãy viết lại mục tiêu B theo cấu trúc có phạm vi, baseline, target, thời hạn, phép đo và owner. Nếu chưa có baseline đáng tin, nên làm gì trước?

### Gợi ý đáp án

**A.** B gần với outcome nhất vì gắn với một vấn đề cụ thể mà người dùng chịu ảnh hưởng: checkout và hóa đơn tính phí khác nhau. A chỉ đặt target cho một chỉ số thay thế, chưa chỉ ra lỗi hoặc hành vi cần cải thiện. C là một giải pháp lớn nhưng chưa có bằng chứng rằng framework hiện tại là nguyên nhân.

**B.** Cần xác định đơn nào đủ điều kiện, cách so sánh phí, tử số/mẫu số, kênh và loại giao hàng, cách xử lý đơn hủy hoặc dữ liệu thiếu, khoảng thời gian baseline và phiên bản chính sách. Cũng cần biết số lượng đơn để đánh giá target có ý nghĩa hay không.

**C.**

- Outcome: số đơn có phí checkout khác phí hóa đơn trên 10.000 đơn đủ điều kiện.
- Leading indicator 1: số nơi độc lập cài đặt chính sách phí giảm từ hai xuống một.
- Leading indicator 2: test có expected độc lập cho ngay dưới, đúng và trên ngưỡng, cùng test xác minh hai caller.
- Guardrail 1: p95 checkout không vượt giới hạn đã thống nhất.
- Guardrail 2: lỗi ghi hóa đơn/rollback không tăng.

**D.** Coverage đo mã được thực thi theo mô hình công cụ, không chứng minh expected đúng hoặc tình huống nghiệp vụ quan trọng đã được chọn. Test có thể chạy qua điều kiện nhưng không assert đúng kết quả tại ngưỡng. Cần xem test oracle, branch và dữ liệu thực tế.

**E.** Ví dụ khi đã có baseline: “Trong luồng checkout và hóa đơn giao STANDARD, giảm tỷ lệ đơn lệch phí từ 8/10.000 xuống không quá 2/10.000 trong tám tuần sau triển khai, đo bằng đối soát mã đơn trên cùng chính sách và tối thiểu 20.000 đơn đủ điều kiện; p95 checkout và lỗi ghi hóa đơn không vượt guardrails đã thống nhất. Nhóm Billing chịu trách nhiệm theo dõi hằng tuần.” Các con số chỉ minh họa. Nếu chưa có baseline đáng tin, bước đầu tiên là thống nhất định nghĩa và thu thập dữ liệu; không bịa một baseline để điền vào mẫu.

## Ghi nhớ

**Một mục tiêu cải thiện tốt mô tả kết quả cần thay đổi, phạm vi, baseline, target, thời hạn, cách đo và người chịu trách nhiệm.** Hoạt động như thêm test, refactor hoặc nâng cấp CI chỉ là phương tiện; cần chỉ ra chúng giúp giải quyết vấn đề nào.

Hãy chọn một vấn đề đủ quan trọng, có bằng chứng và nằm trong khả năng tác động. Dùng outcome metric để đo kết quả, leading indicators để theo dõi tiến độ và guardrails để bảo vệ chất lượng. Nếu dữ liệu chưa đủ, hãy bắt đầu bằng việc tạo baseline đáng tin cậy. **Cải thiện liên tục không phải đặt càng nhiều target càng tốt; đó là chọn đúng điều cần thay đổi, thử có kiểm soát và học từ bằng chứng.**
