# Phân biệt mức nghiêm trọng với mức ưu tiên sửa

Trong module **VALIDATION_TESTING_STRATEGY**, khi phát hiện lỗi phần mềm, nhóm cần đánh giá hai câu hỏi khác nhau: lỗi gây ảnh hưởng nghiêm trọng đến mức nào và cần xử lý sớm đến mức nào. Hai câu hỏi này thường được biểu diễn bằng **mức nghiêm trọng (severity)** và **mức ưu tiên sửa (priority)**. Nếu dùng hai khái niệm thay thế cho nhau, nhóm có thể tập trung sai nguồn lực, trì hoãn lỗi cần xử lý gấp hoặc làm gián đoạn kế hoạch chỉ vì một lỗi có mức ảnh hưởng lớn nhưng chưa cần sửa ngay.

**Severity** mô tả mức độ tác động của lỗi đối với chức năng, dữ liệu, người dùng, hoạt động nghiệp vụ, bảo mật hoặc các thuộc tính chất lượng. **Priority** mô tả thứ tự và mức khẩn cấp mà tổ chức cần xử lý lỗi so với các công việc khác, xét đến thời điểm phát hành, rủi ro, cam kết và nguồn lực. Severity chủ yếu trả lời “nếu lỗi xảy ra, hậu quả lớn đến đâu?”; priority trả lời “cần giải quyết lỗi này khi nào và trước những việc nào?”.

Một lỗi có thể có severity cao nhưng priority chưa phải cao nhất nếu lỗi hiếm gặp, có phương án giảm thiểu an toàn và chưa ảnh hưởng đến bản phát hành hiện tại. Ngược lại, một lỗi có severity thấp vẫn có thể có priority cao nếu xuất hiện trên trang chủ trước một sự kiện lớn, ảnh hưởng nhiều khách hàng hoặc vi phạm cam kết đã công bố. Không có quy tắc phổ quát rằng severity cao luôn đồng nghĩa priority cao; quyết định cần dựa trên tác động, khả năng xảy ra, phạm vi, thời điểm và bối cảnh kinh doanh.

Bài học này trình bày cách định nghĩa hai thang đánh giá, thu thập dữ liệu để phân loại, sử dụng ma trận severity–priority, tổ chức triage, phân định trách nhiệm, cập nhật quyết định khi bối cảnh thay đổi và báo cáo nhất quán. Mục tiêu là giúp nhóm đánh giá lỗi minh bạch, ưu tiên đúng việc và giải thích được vì sao một lỗi được xử lý ở thời điểm cụ thể.

## 1. Hiểu đúng severity và priority

### 1.1. Mức nghiêm trọng (severity)

Severity mô tả mức độ hậu quả khi lỗi xảy ra trong điều kiện xác định. Nó tập trung vào tác động của lỗi, không trực tiếp quyết định lịch sửa.

Các khía cạnh có thể ảnh hưởng severity:

- Chức năng cốt lõi có bị ngừng hoặc hoạt động sai không?
- Có mất, sai lệch, rò rỉ hoặc hỏng dữ liệu không?
- Có ảnh hưởng đến bảo mật, quyền riêng tư hoặc quyền truy cập không?
- Có làm gián đoạn quy trình nghiệp vụ quan trọng không?
- Có bao nhiêu người dùng, tổ chức hoặc giao dịch bị ảnh hưởng?
- Người dùng có thể tiếp tục bằng cách khác không?
- Hậu quả có thể đảo ngược hoặc phục hồi được không?
- Có rủi ro an toàn, pháp lý, tài chính hoặc uy tín không?

Severity nên được đánh giá theo hậu quả có thể xác minh, với điều kiện tái hiện và phạm vi ảnh hưởng rõ ràng. Một lỗi hiển thị sai màu thường có severity thấp; một lỗi làm lộ dữ liệu của tenant khác có thể có severity rất cao dù chỉ cần một request để tái hiện.

### 1.2. Mức ưu tiên sửa (priority)

Priority mô tả mức độ khẩn cấp và thứ tự xử lý lỗi trong kế hoạch. Nó tập trung vào thời điểm cần hành động và chi phí của việc trì hoãn.

Các yếu tố ảnh hưởng priority:

- Lỗi có đang ảnh hưởng người dùng hoặc hoạt động thực tế không?
- Có ảnh hưởng đến phát hành, triển khai hoặc mốc cam kết không?
- Có workaround an toàn và khả thi không?
- Tác động có đang tăng nhanh theo thời gian không?
- Có sự kiện, chiến dịch hoặc thời hạn sắp tới không?
- Lỗi có ảnh hưởng đến nhiều nhóm hoặc phụ thuộc khác không?
- Việc sửa có cần thiết trước khi triển khai thay đổi liên quan không?
- Chi phí trì hoãn có lớn hơn chi phí sửa hoặc rủi ro hồi quy không?
- Có yêu cầu pháp lý, hợp đồng hoặc chính sách cần đáp ứng ngay không?

Priority là quyết định quản lý công việc, thường do Product Owner, người quản lý phát hành, support lead hoặc vai trò được tổ chức giao quyền quyết định. Tester cung cấp bằng chứng và phân tích rủi ro; không nên tự quyết lịch sửa nếu không có thẩm quyền.

### 1.3. So sánh trực tiếp

| Khía cạnh | Severity | Priority |
|---|---|---|
| Câu hỏi chính | Hậu quả của lỗi nghiêm trọng đến đâu? | Cần xử lý sớm đến mức nào? |
| Trọng tâm | Tác động và mức độ thiệt hại | Tính khẩn cấp và thứ tự công việc |
| Căn cứ | Chức năng, dữ liệu, người dùng, bảo mật, nghiệp vụ | Tác động hiện tại, thời hạn, phát hành, workaround, nguồn lực |
| Người đóng góp | Tester, developer, support, nghiệp vụ, security | Product Owner, release owner, quản lý sản phẩm hoặc người được ủy quyền |
| Thay đổi khi nào? | Khi có bằng chứng mới về tác động hoặc phạm vi | Khi bối cảnh, thời hạn, workaround hoặc kế hoạch thay đổi |
| Ví dụ | Giao dịch bị ghi nhận sai số tiền | Cần sửa trước đợt đối soát cuối ngày |

Severity và priority có liên quan nhưng không đồng nhất. Severity là đánh giá tác động của lỗi; priority là quyết định xử lý trong bối cảnh tổ chức.

### 1.4. Severity không phải mức độ dễ sửa

Một lỗi khó tái hiện hoặc cần thay đổi kiến trúc có thể có severity thấp; một lỗi sửa bằng một dòng cấu hình có thể có severity rất cao. Effort sửa, độ phức tạp kỹ thuật và severity là các thuộc tính khác nhau.

Tương tự, priority không phải cách thể hiện ai đã báo lỗi trước hoặc ai có chức danh cao hơn. Lỗi cần được ưu tiên theo tác động và mục tiêu đã thống nhất, không theo áp lực cá nhân hoặc số lần nhắc.

## 2. Xây dựng thang severity rõ ràng

### 2.1. Vì sao cần thang đánh giá thống nhất?

Nếu mỗi người tự hiểu “Critical”, “Major” hoặc “Minor”, cùng một lỗi có thể được phân loại khác nhau giữa các nhóm. Thang severity cần mô tả mức tác động bằng tiêu chí có thể quan sát và ví dụ đại diện.

Tên mức và số lượng mức phụ thuộc quy trình tổ chức. Một thang bốn mức thường dễ áp dụng, nhưng không phải tiêu chuẩn bắt buộc cho mọi dự án.

### 2.2. Ví dụ thang severity bốn mức

| Mức | Tên minh họa | Đặc điểm tác động | Ví dụ |
|---|---|---|---|
| S1 | Critical / Nghiêm trọng đặc biệt | Hệ thống hoặc chức năng trọng yếu không thể sử dụng; có nguy cơ lớn về dữ liệu, bảo mật, an toàn hoặc tài chính; không có biện pháp giảm thiểu chấp nhận được | Lộ dữ liệu giữa tenant; ghi nhận hoặc chuyển tiền sai diện rộng; mất dữ liệu không thể phục hồi |
| S2 | High / Cao | Chức năng quan trọng bị lỗi đáng kể; nhiều người dùng hoặc quy trình bị ảnh hưởng; workaround hạn chế hoặc tốn kém | Không thể thanh toán qua phương thức chính; không thể tạo đơn cho một nhóm khách hàng lớn |
| S3 | Medium / Trung bình | Một phần chức năng hoạt động sai nhưng tác vụ chính còn có thể hoàn tất bằng cách khác; phạm vi hoặc hậu quả có giới hạn | Bộ lọc tìm kiếm sai trong một điều kiện; một trường phụ không lưu đúng nhưng có thể sửa bằng luồng khác |
| S4 | Low / Thấp | Lỗi nhỏ về trình bày, nội dung hoặc trải nghiệm; không làm sai kết quả nghiệp vụ trọng yếu | Lệch khoảng cách giao diện; lỗi chính tả ở nội dung không quan trọng |

Đây là thang minh họa. Tổ chức cần điều chỉnh định nghĩa theo sản phẩm, mức rủi ro và yêu cầu tuân thủ. Không nên dùng ví dụ như một quy tắc tuyệt đối nếu hậu quả thực tế khác nhau theo bối cảnh.

### 2.3. Xác định severity dựa trên hậu quả

Khi đánh giá, hãy lần lượt hỏi:

1. Hành vi mong đợi là gì và thực tế đã xảy ra điều gì?
2. Chức năng hoặc quy trình nào bị ảnh hưởng?
3. Dữ liệu có bị mất, sai, trùng hoặc lộ không?
4. Người dùng nào và bao nhiêu người bị ảnh hưởng?
5. Tác động có thể phục hồi hoặc đảo ngược không?
6. Có rủi ro bảo mật, an toàn, tài chính hoặc tuân thủ không?
7. Điều kiện nào kích hoạt lỗi và hậu quả có thể mở rộng không?

Không nên suy severity chỉ từ mức độ gây khó chịu của người báo lỗi. Cần xác minh tác động bằng dữ liệu, tái hiện, log, phản hồi hỗ trợ hoặc phân tích nghiệp vụ.

### 2.4. Phân biệt phạm vi ảnh hưởng và mức hậu quả

Một lỗi ảnh hưởng ít người vẫn có thể nghiêm trọng nếu hậu quả với từng người rất lớn. Ví dụ, một lỗi chỉ ảnh hưởng người dùng có quyền truy cập dữ liệu tài chính nhưng làm lộ dữ liệu đó có thể là severity cao.

Ngược lại, lỗi ảnh hưởng nhiều người nhưng chỉ làm lệch một chi tiết trang trí có thể có severity thấp hơn, dù priority có thể tăng do độ phủ lớn hoặc thời điểm xuất hiện.

Do đó, số người dùng bị ảnh hưởng là một yếu tố quan trọng nhưng không phải yếu tố duy nhất.

### 2.5. Phân loại khi chưa đủ thông tin

Nếu chưa xác định được hậu quả, không nên khẳng định mức severity thấp chỉ vì chưa có bằng chứng. Có thể ghi:

- Severity tạm thời.
- Mức tác động đã quan sát.
- Điều chưa biết.
- Bằng chứng cần thu thập.
- Người chịu trách nhiệm xác minh.
- Thời điểm xem xét lại.

Với dấu hiệu liên quan bảo mật, dữ liệu hoặc an toàn, cần chuyển đúng kênh chuyên môn để đánh giá ngay theo quy trình tổ chức, kể cả khi phạm vi chưa rõ.

## 3. Xây dựng thang priority phù hợp với quy trình

### 3.1. Priority biểu thị thời điểm xử lý

Priority thường được dùng để sắp xếp backlog hoặc xác định yêu cầu phải sửa trước một mốc. Một thang bốn mức có thể được định nghĩa như sau:

| Mức | Tên minh họa | Hướng xử lý |
|---|---|---|
| P1 | Urgent / Khẩn cấp | Hành động ngay; có thể cần dừng phát hành, giảm thiểu sự cố hoặc triển khai hotfix theo quy trình |
| P2 | High / Cao | Xử lý trong chu kỳ hoặc bản phát hành gần nhất; cần kế hoạch và chủ sở hữu rõ |
| P3 | Normal / Bình thường | Đưa vào kế hoạch backlog theo năng lực và giá trị |
| P4 | Low / Thấp | Có thể xử lý khi phù hợp hoặc gộp với cải tiến liên quan |

Mốc thời gian cụ thể cần được quy định bởi tổ chức. Ví dụ “P1 trong vòng 4 giờ” chỉ có ý nghĩa nếu có SLA, người trực và quy trình đáp ứng tương ứng. Không nên gán thời hạn tùy ý cho nhãn priority.

### 3.2. Các yếu tố quyết định priority

**Tác động hiện tại:** lỗi đã xảy ra ở production hay chỉ được phát hiện trong môi trường test? Có bao nhiêu giao dịch hoặc người dùng đang chịu ảnh hưởng?

**Tính khẩn cấp:** có mốc phát hành, thời hạn hợp đồng, chiến dịch hoặc hoạt động nghiệp vụ sắp diễn ra không?

**Workaround:** người dùng có cách thay thế an toàn, dễ hiểu và có thể mở rộng không? Workaround có tạo thêm rủi ro hoặc chi phí vận hành không?

**Phạm vi và tốc độ lan rộng:** lỗi chỉ ảnh hưởng một tài khoản hay toàn bộ khách hàng? Tác động có tăng theo thời gian không?

**Phụ thuộc:** lỗi có chặn nhóm khác, pipeline, migration hoặc release train không?

**Chi phí trì hoãn:** nếu không sửa ngay, có thể phát sinh mất dữ liệu, giao dịch sai, vi phạm cam kết hoặc chi phí hỗ trợ lớn hơn không?

**Khả năng sửa và rủi ro hồi quy:** một bản sửa vội có thể gây hại hơn nếu chưa đủ kiểm chứng. Priority cao có thể yêu cầu hành động giảm thiểu trước, rồi sửa triệt để sau.

### 3.3. Priority không chỉ là “khách hàng đang phàn nàn”

Phản hồi khách hàng là tín hiệu quan trọng, nhưng cần đặt trong bối cảnh:

- Mức độ ảnh hưởng thực tế.
- Số lượng khách hàng gặp vấn đề.
- Phân khúc hoặc quy trình bị tác động.
- Có giải pháp thay thế không.
- Cam kết dịch vụ hoặc hợp đồng.
- Khả năng tái hiện và bằng chứng.
- Rủi ro nếu chờ đến release kế tiếp.

Một lỗi được nhiều người báo có thể cần priority cao vì phạm vi lớn. Tuy nhiên, một lỗi bảo mật chưa có báo cáo khách hàng vẫn có thể cần xử lý khẩn cấp do hậu quả tiềm tàng.

### 3.4. Priority có thể thay đổi theo thời gian

Một lỗi có thể chuyển từ P3 sang P1 nếu:

- Một tính năng được bật rộng hơn.
- Lỗi xuất hiện trong production.
- Workaround không còn khả thi.
- Sự kiện hoặc mốc cam kết sắp đến.
- Phạm vi ảnh hưởng tăng.
- Một phát hiện mới cho thấy có rủi ro dữ liệu hoặc bảo mật.
- Một bản phát hành sắp tới phụ thuộc vào phần đang lỗi.

Ngược lại, priority có thể giảm nếu lỗi đã được giảm thiểu, tính năng bị tắt, mốc phát hành thay đổi hoặc một phương án thay thế an toàn được xác nhận. Lịch sử quyết định cần được giữ để giải thích vì sao priority thay đổi.

## 4. Ma trận severity và priority

### 4.1. Hai chiều đánh giá độc lập

Ma trận giúp thảo luận hai thuộc tính cùng lúc mà không đồng nhất chúng. Một cách nhìn đơn giản:

| Severity  Priority | P1 Khẩn cấp | P2 Cao | P3 Bình thường | P4 Thấp |
|---|---|---|---|---|
| S1 Critical | Có thể chặn phát hành hoặc cần xử lý sự cố ngay | Có thể dùng khi đã giảm thiểu và có kế hoạch kiểm soát | Chỉ khi có căn cứ đặc biệt và người có thẩm quyền chấp nhận | Hiếm; cần xem lại phân loại |
| S2 High | Nếu tác động hiện tại hoặc mốc gần | Thường cần xử lý sớm | Có thể chấp nhận khi workaround và kế hoạch rõ | Cần giải thích vì sao trì hoãn |
| S3 Medium | Có thể xảy ra khi độ phủ hoặc thời điểm rất quan trọng | Có thể cần trước một mốc cụ thể | Phổ biến trong backlog | Có thể để sau nếu tác động thấp |
| S4 Low | Có thể nếu lỗi nhỏ nhưng ảnh hưởng chiến dịch hoặc cam kết gần | Có thể khi sửa nhanh và cần trước phát hành | Thường phù hợp | Thường phù hợp |

Ma trận này không tự động gán priority từ severity. Nó nêu các tổ hợp có thể xảy ra và những câu hỏi cần giải thích. Mọi ngoại lệ, đặc biệt S1 với P3/P4, cần có lý do, biện pháp giảm thiểu và người chấp nhận rủi ro.

### 4.2. Ví dụ S1 nhưng priority không phải P1

Giả sử một lỗi nghiêm trọng được phát hiện trong một công cụ nội bộ chưa được triển khai cho người dùng. Lỗi có thể làm sai lệch dữ liệu nếu một thao tác đặc biệt xảy ra, nên severity được đánh giá cao. Tuy nhiên:

- Tính năng đang bị tắt bằng feature flag.
- Không có dữ liệu thật đi qua luồng đó.
- Có biện pháp ngăn kích hoạt.
- Không có release nào sử dụng tính năng trong vài tháng.
- Chủ sở hữu sản phẩm và kỹ thuật đã thống nhất kế hoạch sửa trước khi bật tính năng.

Trong bối cảnh đó, priority có thể thấp hơn mức khẩn cấp ngay lập tức, nhưng cần ghi rõ điều kiện không được bật tính năng khi chưa sửa. Nếu điều kiện thay đổi, priority phải được đánh giá lại.

### 4.3. Ví dụ S4 nhưng priority cao

Một lỗi chính tả nhỏ xuất hiện trên trang đăng ký công khai ngay trước chiến dịch tuyển sinh lớn. Lỗi không làm sai chức năng nên severity thấp. Tuy nhiên, trang là điểm tiếp xúc chính, nội dung đã được phê duyệt và chiến dịch sắp bắt đầu. Sửa lỗi có thể cần priority cao vì thời điểm và uy tín.

Điều này không có nghĩa mọi lỗi giao diện trước release đều phải P1. Cần đánh giá độ phủ, mức độ nhìn thấy, cam kết nội dung và chi phí trì hoãn.

### 4.4. Ma trận không thay thế phán đoán

Không nên tạo quy tắc cứng như “S1 luôn P1” hoặc “S4 luôn P4” nếu sản phẩm có nhiều bối cảnh. Ma trận là công cụ để làm rõ lý do. Các yêu cầu pháp lý, bảo mật, an toàn hoặc chính sách bắt buộc có thể áp đặt thời hạn xử lý độc lập với ma trận thông thường.

## 5. Thu thập bằng chứng trước khi phân loại

### 5.1. Mô tả lỗi có thể tái hiện

Một báo cáo lỗi hữu ích cần có:

- Tiêu đề mô tả triệu chứng.
- Phiên bản, build và môi trường.
- Tiền điều kiện và dữ liệu.
- Các bước tái hiện.
- Kết quả mong đợi.
- Kết quả thực tế.
- Tần suất tái hiện.
- Phạm vi người dùng hoặc dữ liệu bị ảnh hưởng.
- Ảnh, video, request, response, log hoặc trace phù hợp.
- Workaround đã thử và hiệu quả.
- Thời điểm phát hiện và lần cuối xác nhận.

Báo cáo cần tách quan sát khỏi giả thuyết. “API trả 500 ở bước xác nhận thanh toán” là quan sát; “database bị lỗi” là giả thuyết nếu chưa có bằng chứng.

### 5.2. Đánh giá phạm vi ảnh hưởng

Cần xác định:

- Một người dùng, một tenant hay nhiều tenant?
- Một trình duyệt, thiết bị hoặc cấu hình hay mọi nền tảng?
- Một giao dịch hay một loại giao dịch?
- Một phiên bản hay nhiều phiên bản đang được sử dụng?
- Có dữ liệu đã bị sai hoặc chỉ hành động mới bị chặn?
- Có thể xác định các bản ghi đã bị ảnh hưởng không?

Nếu chưa biết phạm vi, ghi rõ “chưa xác định” và tạo hành động điều tra. Không mặc định phạm vi nhỏ chỉ vì mới nhận được một báo cáo.

### 5.3. Xác minh tần suất và điều kiện kích hoạt

Tần suất có thể ảnh hưởng priority và đánh giá rủi ro. Ghi:

- Luôn xảy ra hay chỉ đôi khi?
- Có phụ thuộc dữ liệu, thời điểm, tải hoặc thứ tự thao tác không?
- Có xảy ra trên môi trường production không?
- Có thể tái hiện bằng test case ổn định không?
- Có xuất hiện sau một thay đổi cụ thể không?
- Tỷ lệ lỗi trên tổng số lần thực hiện là bao nhiêu nếu có dữ liệu?

Không dùng tần suất thấp để hạ severity nếu mỗi lần xảy ra gây hậu quả nghiêm trọng. Tần suất là một yếu tố của khả năng xảy ra, không xóa bỏ mức hậu quả.

### 5.4. Đánh giá khả năng phục hồi và workaround

Workaround chỉ làm giảm urgency khi thực sự khả thi:

- Người dùng có biết cách sử dụng không?
- Có áp dụng được cho mọi trường hợp bị ảnh hưởng không?
- Có cần hỗ trợ thủ công hoặc quyền đặc biệt không?
- Có làm tăng nguy cơ sai dữ liệu hoặc gian lận không?
- Có tạo chi phí đáng kể hoặc vi phạm chính sách không?
- Có thể duy trì đến khi bản sửa sẵn sàng không?

Ví dụ, hướng dẫn người dùng thử lại có thể là workaround an toàn cho lỗi tải tạm thời. Yêu cầu nhân viên nhập tay số tiền hoàn hoặc chia sẻ dữ liệu qua email không an toàn không phải workaround chấp nhận được.

## 6. Quy trình triage lỗi

### 6.1. Triage là gì?

Triage là hoạt động xem xét, phân loại và quyết định cách xử lý các lỗi mới hoặc lỗi đang tồn đọng. Triage cần thống nhất:

- Lỗi có hợp lệ và có thể tái hiện không?
- Mức severity là gì?
- Priority hiện tại là gì?
- Có cần giảm thiểu hoặc hành động sự cố ngay không?
- Ai chịu trách nhiệm xử lý?
- Khi nào cần sửa hoặc xem xét lại?
- Cần kiểm thử xác nhận và hồi quy nào?

Triage không chỉ là chọn nhãn trong công cụ quản lý lỗi. Đó là quyết định dựa trên bằng chứng, rủi ro và kế hoạch.

### 6.2. Quy trình triage gợi ý

1. **Tiếp nhận:** kiểm tra thông tin tối thiểu và loại trùng.
2. **Xác minh:** tái hiện hoặc xác định bằng chứng đủ tin cậy.
3. **Đánh giá tác động:** chức năng, dữ liệu, người dùng, bảo mật và nghiệp vụ.
4. **Gán severity:** theo thang định nghĩa của nhóm.
5. **Đánh giá urgency:** thời điểm, phạm vi hiện tại, workaround, mốc phát hành và phụ thuộc.
6. **Gán priority:** người có thẩm quyền xác định thứ tự xử lý.
7. **Phân công:** owner, thời hạn và hành động tiếp theo.
8. **Theo dõi:** cập nhật khi có bằng chứng hoặc bối cảnh mới.
9. **Đóng:** xác nhận bản sửa, hồi quy và bằng chứng giải quyết.

### 6.3. Ai tham gia và ai quyết định?

Vai trò có thể khác nhau theo tổ chức, nhưng nên phân định:

| Vai trò | Đóng góp chính |
|---|---|
| Tester / QA | Tái hiện, mô tả tác động, bằng chứng, severity đề xuất và phạm vi kiểm thử |
| Developer | Phân tích nguyên nhân, phạm vi kỹ thuật, phương án sửa và rủi ro hồi quy |
| Product Owner / Business | Xác định tác động nghiệp vụ, khách hàng, workaround và giá trị ưu tiên |
| Support / Operations | Cung cấp dữ liệu production, tần suất, người dùng ảnh hưởng và biện pháp giảm thiểu |
| Security / Privacy | Đánh giá rủi ro bảo mật, quyền riêng tư và quy trình xử lý chuyên biệt |
| Release owner / Manager | Điều phối mốc phát hành, nguồn lực và quyết định promotion theo thẩm quyền |

Không nhất thiết mọi vai trò tham dự mọi buổi triage. Lỗi bảo mật cần đúng kênh bảo mật; lỗi nội dung nhỏ có thể được xử lý trong backlog thông thường. Người có quyền quyết định priority cần được xác định trước.

### 6.4. Triage khẩn cấp và triage định kỳ

- **Triage khẩn cấp:** dành cho lỗi đang gây tác động nghiêm trọng, rủi ro bảo mật, mất dữ liệu hoặc gián đoạn dịch vụ. Cần kích hoạt quy trình incident/escalation phù hợp, không đợi cuộc họp backlog tiếp theo.
- **Triage định kỳ:** xem xét lỗi mới, backlog, priority thay đổi và kế hoạch release.
- **Triage theo release:** xác nhận lỗi nào chặn phát hành, lỗi nào có thể chấp nhận kèm biện pháp và người phê duyệt.

Thời gian phản hồi và kênh escalation cần được quy định theo tổ chức và mức độ dịch vụ.

## 7. Severity và priority trong bối cảnh khác nhau

### 7.1. Lỗi trong môi trường phát triển hoặc kiểm thử

Một lỗi được phát hiện trong môi trường test chưa chắc có priority thấp. Nếu nó cho thấy lỗ hổng nghiêm trọng có thể xuất hiện ở production, cần xử lý sớm trước khi triển khai.

Ngược lại, một lỗi chỉ xảy ra do dữ liệu seed sai trong môi trường test có thể không phải defect của sản phẩm. Cần phân biệt lỗi test, lỗi môi trường và lỗi ứng dụng trước khi gán severity.

### 7.2. Lỗi đang ảnh hưởng production

Khi lỗi đã ảnh hưởng production, priority thường tăng do tác động hiện tại và chi phí trì hoãn. Tuy nhiên, severity vẫn phải mô tả hậu quả của lỗi; priority quyết định hành động như giảm thiểu, hotfix, rollback hoặc sửa trong release kế tiếp.

Nếu lỗi gây gián đoạn dịch vụ, cần xử lý theo incident management. Không chờ hoàn tất mọi phân tích nguyên nhân gốc mới thực hiện biện pháp giảm thiểu an toàn.

### 7.3. Lỗi bảo mật và quyền riêng tư

Lỗi liên quan đến xác thực, phân quyền, rò rỉ dữ liệu hoặc lỗ hổng có thể cần quy trình phân loại riêng. Không nên đưa chi tiết nhạy cảm vào ticket công khai. Cần:

- Chuyển đến kênh security/privacy được phê duyệt.
- Bảo vệ bằng chứng và giới hạn người truy cập.
- Xác định phạm vi dữ liệu hoặc tài khoản có thể bị ảnh hưởng.
- Đánh giá nghĩa vụ thông báo hoặc xử lý theo chính sách.
- Thực hiện giảm thiểu và theo dõi theo người chịu trách nhiệm.

Severity và priority cần tuân theo chính sách chuyên môn; không hạ mức chỉ vì chưa có khiếu nại hoặc chưa xác nhận khai thác.

### 7.4. Lỗi nội dung và trải nghiệm

Lỗi nội dung, giao diện hoặc khả năng truy cập có thể có severity khác nhau theo tác động. Một lỗi chính tả ở trang phụ có thể thấp; nhãn sai trên nút thanh toán hoặc thông báo lỗi khiến người dùng không thể hoàn thành tác vụ có thể cao hơn.

Priority phụ thuộc vào độ phủ, thời điểm, khả năng thay thế và mức độ quan trọng của hành trình. Không nên coi tất cả lỗi giao diện là cosmetic.

### 7.5. Lỗi hiếm gặp nhưng hậu quả lớn

Một lỗi chỉ xuất hiện trong điều kiện hiếm vẫn có thể có severity cao. Ví dụ, lỗi xử lý số tiền rất lớn hoặc một chuỗi retry đặc biệt gây ghi nhận giao dịch trùng. Cần đánh giá khả năng kích hoạt, điều kiện bảo vệ, hậu quả và khả năng phát hiện.

Priority có thể phụ thuộc vào việc điều kiện đó có thể xảy ra trong release hiện tại hay không, nhưng rủi ro phải được ghi lại và có điều kiện tái đánh giá.

## 8. Ví dụ thực tế phân biệt severity và priority

### 8.1. Ví dụ 1: Không thể thanh toán bằng phương thức chính

**Quan sát:** khách hàng không thể hoàn tất thanh toán bằng thẻ; các đơn đã tạo vẫn ở trạng thái chờ.

- Severity đề xuất: S2 hoặc S1 tùy mức độ ảnh hưởng, phạm vi và khả năng sử dụng phương thức khác.
- Priority đề xuất: P1 nếu đang ảnh hưởng nhiều khách hàng và không có workaround khả thi.
- Bằng chứng cần có: tỷ lệ lỗi, số giao dịch, provider response, thời điểm bắt đầu và phương thức thanh toán thay thế.
- Hành động: kích hoạt quy trình incident nếu đang ảnh hưởng production, cân nhắc chuyển traffic hoặc tắt phương thức lỗi theo quy trình an toàn.

Severity không thể xác định chỉ từ một ảnh chụp lỗi; cần dữ liệu về giao dịch và phạm vi.

### 8.2. Ví dụ 2: Lỗi chính tả trên trang giới thiệu

**Quan sát:** một từ trên trang giới thiệu bị sai chính tả, không ảnh hưởng chức năng.

- Severity đề xuất: S4.
- Priority đề xuất: P4 trong điều kiện bình thường.
- Có thể tăng priority nếu trang chuẩn bị xuất hiện trong chiến dịch hoặc tài liệu đã được phê duyệt phải phát hành đúng hạn.
- Bằng chứng: URL, ảnh chụp, nội dung đúng đã được xác nhận.

Severity vẫn thấp dù priority có thể tăng do thời điểm.

### 8.3. Ví dụ 3: Lộ dữ liệu giữa hai tenant

**Quan sát:** người dùng tenant A có thể đọc hồ sơ của tenant B bằng cách thay ID trong request.

- Severity đề xuất: S1 do vi phạm ranh giới dữ liệu và quyền truy cập.
- Priority đề xuất: P1, cần chuyển quy trình bảo mật ngay.
- Bằng chứng: request/response đã được bảo vệ, tài khoản thử, phạm vi tenant và log liên quan.
- Hành động: giảm thiểu truy cập, xác định phạm vi ảnh hưởng, xử lý theo quy trình security/privacy.

Không cần đợi xác nhận có bao nhiêu người đã xem dữ liệu mới bắt đầu giảm thiểu rủi ro.

### 8.4. Ví dụ 4: Báo cáo sai định dạng ở một locale ít dùng

**Quan sát:** số tiền trong báo cáo dùng dấu phân cách không đúng locale đã chọn; giá trị lưu trữ không bị thay đổi.

- Severity đề xuất: S3 hoặc S2 tùy khả năng người dùng hiểu nhầm và ra quyết định sai.
- Priority đề xuất: P2 nếu báo cáo được dùng cho kỳ đối soát sắp tới; P3 nếu có cách xuất dữ liệu chính xác và chưa đến kỳ.
- Bằng chứng: locale, dữ liệu, ảnh hiển thị, giá trị nội bộ và quy tắc định dạng.
- Hành động: xác định phạm vi locale và báo cáo bị ảnh hưởng, sửa formatter và kiểm tra hồi quy.

Nếu định dạng khiến số tiền bị diễn giải sai trong chứng từ tài chính, severity có thể cao hơn.

### 8.5. Ví dụ 5: Kiểm thử tự động không ổn định

**Quan sát:** một test E2E thất bại ngẫu nhiên do timing nhưng chức năng sản phẩm chưa có bằng chứng lỗi.

- Severity: chưa gán cho sản phẩm nếu chưa xác nhận defect; có thể ghi loại vấn đề test/flaky.
- Priority: có thể P2 nếu test nằm trong release gate và chặn pipeline thường xuyên; thấp hơn nếu là test không quan trọng và có phạm vi riêng.
- Bằng chứng: lịch sử lần chạy, log, trace, điều kiện môi trường và tần suất.
- Hành động: điều tra nguyên nhân test, cô lập khỏi gate theo quy trình nếu cần và giữ lịch sử thất bại.

Không nên gán severity sản phẩm chỉ vì test đỏ.

### 8.6. Bảng tổng hợp ví dụ

| Tình huống | Severity minh họa | Priority có thể có | Lý do priority |
|---|---|---|---|
| Lộ dữ liệu giữa tenant | S1 | P1 | Rủi ro bảo mật và dữ liệu cần xử lý ngay |
| Thanh toán chính bị gián đoạn | S1/S2 | P1 | Tác động đang xảy ra và ảnh hưởng doanh thu |
| Sai chính tả trang giới thiệu | S4 | P4 hoặc P2 | Phụ thuộc thời điểm chiến dịch |
| Báo cáo sai định dạng locale | S2/S3 | P2/P3 | Phụ thuộc kỳ đối soát và nguy cơ diễn giải sai |
| Flaky test chặn pipeline | Chưa xác định severity sản phẩm | P2/P3 | Phụ thuộc mức độ chặn release và tần suất |
| Lỗi hiếm trong luồng phục hồi dữ liệu | S1/S2 | P2 hoặc P1 | Phụ thuộc khả năng kích hoạt và biện pháp giảm thiểu |

Các mức trong bảng chỉ là ví dụ. Cần dùng thang đã được tổ chức phê duyệt và bằng chứng của sản phẩm.

## 9. Ghi nhận severity và priority trong hệ thống quản lý lỗi

### 9.1. Các trường nên có

Một defect record nên lưu:

| Trường | Mục đích |
|---|---|
| Defect ID | Định danh lỗi |
| Summary | Mô tả ngắn triệu chứng |
| Environment / Build | Điều kiện phát hiện |
| Reproduction steps | Các bước tái hiện |
| Expected / Actual | Kết quả mong đợi và thực tế |
| Evidence | Log, trace, ảnh, request hoặc dữ liệu |
| Impact scope | Người dùng, tenant, chức năng và dữ liệu bị ảnh hưởng |
| Severity | Mức hậu quả theo thang đã thống nhất |
| Priority | Thứ tự xử lý hiện tại |
| Workaround | Biện pháp tạm thời và giới hạn |
| Owner | Người hoặc nhóm chịu trách nhiệm |
| Target release / Due date | Mốc dự kiến xử lý |
| Status | Trạng thái vòng đời lỗi |
| Decision rationale | Lý do gán hoặc thay đổi mức |
| Review trigger | Điều kiện cần đánh giá lại |

Không phải công cụ nào cũng có trường severity và priority riêng. Nếu hệ thống dùng một field, cần có quy ước bổ sung để không làm mất sự khác biệt giữa tác động và urgency.

### 9.2. Ghi lý do phân loại

Không chỉ điền S2/P1. Thêm một câu giải thích:

> Severity S2 vì luồng thanh toán thẻ bị chặn với một nhóm giao dịch; dữ liệu đơn vẫn được giữ và phương thức chuyển khoản còn hoạt động. Priority P1 vì lỗi đang ảnh hưởng production trong giờ cao điểm và không có workaround phù hợp cho khách dùng thẻ.

Lý do giúp người khác hiểu quyết định và đánh giá lại khi có thông tin mới.

### 9.3. Lưu lịch sử thay đổi

Khi severity hoặc priority thay đổi, ghi:

- Giá trị cũ và mới.
- Thời điểm.
- Người thay đổi.
- Bằng chứng hoặc bối cảnh mới.
- Lý do thay đổi.
- Hành động tiếp theo.

Không ghi đè lịch sử khiến nhóm không thể giải thích vì sao lỗi từng bị xem là thấp rồi trở thành khẩn cấp, hoặc vì sao một lỗi được hạ priority sau khi có workaround.

## 10. Theo dõi từ triage đến xác nhận sửa

### 10.1. Severity và priority không thay thế trạng thái lỗi

Một lỗi có thể đi qua các trạng thái:

~~~mermaid
stateDiagram-v2
    [*] --> New
    New --> Triaged
    Triaged --> Assigned
    Assigned --> InProgress
    InProgress --> Fixed
    Fixed --> ReadyForRetest
    ReadyForRetest --> Verified
    ReadyForRetest --> Reopened
    Reopened --> Assigned
    Verified --> Closed
    Triaged --> Deferred
    Deferred --> Assigned
    Closed --> [*]
~~~

Tên trạng thái phụ thuộc công cụ và quy trình. Severity và priority là thuộc tính phân loại; status cho biết lỗi đang ở giai đoạn xử lý nào.

### 10.2. Xác nhận bản sửa

Khi developer báo đã sửa:

- Xác nhận đúng build hoặc commit chứa bản sửa.
- Tái hiện lại trường hợp gốc nếu điều kiện cho phép.
- Xác nhận hành vi mong đợi.
- Kiểm tra dữ liệu hoặc tác dụng phụ liên quan.
- Chạy hồi quy trên vùng chức năng có rủi ro.
- Kiểm tra workaround hoặc cấu hình tạm có còn cần không.
- Lưu bằng chứng retest.

Không đóng lỗi chỉ vì code đã merge hoặc deployment hoàn tất. Cần xác minh hành vi trong môi trường và điều kiện phù hợp.

### 10.3. Đóng, mở lại hoặc hoãn

- **Closed:** có bằng chứng xác nhận lỗi đã được giải quyết theo tiêu chí.
- **Reopened:** lỗi vẫn xảy ra hoặc tái xuất hiện.
- **Deferred:** quyết định hoãn có lý do, người chịu trách nhiệm và mốc xem xét.
- **Duplicate:** liên kết đến lỗi gốc, không xóa mất bằng chứng riêng nếu chúng thể hiện phạm vi khác.
- **Won't fix / Accepted:** chỉ dùng theo quy trình, ghi rõ lý do và người có thẩm quyền.

Một lỗi được hoãn không có nghĩa severity đã giảm. Priority có thể thay đổi do quyết định kế hoạch, nhưng tác động của lỗi vẫn cần được mô tả chính xác.

## 11. Quản lý backlog và rà soát priority định kỳ

### 11.1. Sắp xếp backlog theo nhiều yếu tố

Backlog không nên chỉ được sắp theo severity. Có thể xem xét:

- Priority hiện tại.
- Severity và tác động.
- Giá trị hoặc rủi ro nghiệp vụ.
- Số lượng người dùng và phạm vi.
- Mốc phát hành hoặc thời hạn.
- Workaround và chi phí duy trì.
- Phụ thuộc kỹ thuật.
- Effort sửa và rủi ro hồi quy.
- Tuổi lỗi và thời gian đã chờ.
- Lỗi lặp lại hoặc có xu hướng tăng.

Effort sửa có thể ảnh hưởng thứ tự khi các lỗi có urgency tương đương, nhưng không nên làm giảm mức độ hậu quả của lỗi.

### 11.2. Rà soát lỗi tồn đọng

Theo chu kỳ, xem xét:

- Lỗi P1/P2 còn mở.
- Lỗi severity cao chưa có kế hoạch.
- Lỗi bị deferred lâu.
- Lỗi không có owner.
- Lỗi đã có workaround nhưng workaround sắp hết hiệu lực.
- Lỗi có liên quan đến thay đổi hoặc release mới.
- Lỗi có báo cáo mới hoặc phạm vi ảnh hưởng tăng.

Một lỗi P4 tồn đọng lâu không tự động trở thành P1. Tuổi lỗi là tín hiệu để rà soát, không phải công thức tự nâng priority.

### 11.3. Tránh dùng severity/priority để đánh giá cá nhân

Không dùng số lượng lỗi severity cao do một developer sửa hoặc số lỗi được tester báo để đánh giá năng suất cá nhân. Số lượng và mức phân loại chịu ảnh hưởng của phạm vi sản phẩm, độ phức tạp, khả năng phát hiện và chính sách triage.

Các chỉ số nên phục vụ cải tiến hệ thống như thời gian xử lý, lỗi tái mở, lỗi lọt production, nguyên nhân lặp lại và thời gian chờ theo priority.

## 12. Những sai lầm thường gặp

1. **Đồng nhất severity với priority:** giả định lỗi nghiêm trọng luôn phải sửa trước mọi việc khác.
2. **Gán severity theo độ khó sửa:** nhầm hậu quả với effort kỹ thuật.
3. **Gán priority theo chức danh người báo:** ưu tiên theo áp lực cá nhân thay vì tác động.
4. **Dựa vào tần suất để hạ severity:** bỏ qua hậu quả rất lớn của lỗi hiếm.
5. **Coi workaround là hết rủi ro:** không kiểm tra tính an toàn và khả năng mở rộng của workaround.
6. **Gán mức khi chưa có bằng chứng:** không ghi giả định hoặc điều chưa biết.
7. **Dùng thang không có định nghĩa:** mỗi nhóm diễn giải S1/P1 khác nhau.
8. **Coi mọi lỗi production là P1:** không phân biệt phạm vi và mức khẩn cấp.
9. **Coi mọi lỗi UI là thấp:** bỏ qua tác động đến hoàn thành tác vụ hoặc khả năng truy cập.
10. **Không cập nhật priority khi bối cảnh đổi:** giữ nguyên quyết định cũ dù phạm vi ảnh hưởng đã tăng.
11. **Không ghi lý do phân loại:** người khác không hiểu vì sao lỗi được xử lý theo thứ tự hiện tại.
12. **Dùng priority để thay trạng thái:** không phân biệt lỗi đang chờ, đang sửa, đã xác minh hay bị hoãn.
13. **Đóng lỗi khi chỉ mới merge code:** chưa xác nhận hành vi sau triển khai.
14. **Dùng số lỗi để xếp hạng cá nhân:** tạo động cơ phân loại sai và làm mất tính minh bạch.

## 13. Checklist phân biệt mức nghiêm trọng với mức ưu tiên sửa

- [ ] Severity và priority được định nghĩa riêng trong quy trình.
- [ ] Thang severity mô tả hậu quả về chức năng, dữ liệu, người dùng, bảo mật và nghiệp vụ.
- [ ] Thang priority mô tả urgency, thứ tự và kỳ vọng thời điểm xử lý.
- [ ] Báo cáo lỗi có bước tái hiện, expected/actual và bằng chứng.
- [ ] Phạm vi ảnh hưởng, tần suất và điều kiện kích hoạt được đánh giá.
- [ ] Khả năng phục hồi và workaround được xác minh.
- [ ] Severity phản ánh hậu quả, không phụ thuộc độ khó sửa.
- [ ] Priority phản ánh bối cảnh, thời hạn, phát hành và chi phí trì hoãn.
- [ ] Ma trận severity–priority được dùng để thảo luận, không tự động quyết định.
- [ ] Lỗi bảo mật, dữ liệu hoặc an toàn được chuyển đúng quy trình chuyên môn.
- [ ] Người có thẩm quyền gán priority và quyết định ngoại lệ được xác định.
- [ ] Lý do gán mức và lịch sử thay đổi được lưu.
- [ ] Lỗi P1/P2, lỗi severity cao và lỗi deferred được rà soát định kỳ.
- [ ] Bản sửa được retest và hồi quy trước khi đóng.
- [ ] Kết luận và rủi ro còn lại được liên kết với release hoặc quyết định sản phẩm.

Phân biệt severity với priority giúp nhóm mô tả đúng hậu quả của lỗi và quyết định đúng thời điểm xử lý. Khi thang đánh giá rõ ràng, bằng chứng được thu thập đầy đủ, quyền quyết định được phân định và các thay đổi được ghi lại, hoạt động triage trở nên nhất quán hơn, nguồn lực được tập trung vào rủi ro phù hợp và quyết định phát hành có căn cứ hơn.
