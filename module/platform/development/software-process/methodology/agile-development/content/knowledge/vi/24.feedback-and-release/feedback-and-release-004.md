# Kết hợp phản hồi định tính với dữ liệu sử dụng

## Mục tiêu học tập

Sau bài học, bạn có thể:

1. Phân biệt **phản hồi định tính** với **dữ liệu sử dụng định lượng**, nhận ra điểm mạnh, giới hạn và giá trị bổ sung của mỗi nguồn khi phát triển sản phẩm theo Agile.
2. Chuyển **Product Goal, vấn đề người dùng và giả thuyết sản phẩm** thành câu hỏi học hỏi, phương án thu thập phản hồi và những chỉ số có ý nghĩa.
3. Thu thập, tổng hợp và diễn giải phỏng vấn, quan sát sử dụng, phiếu góp ý, phản hồi hỗ trợ khách hàng mà không biến ý kiến của một vài người thành kết luận về toàn bộ người dùng.
4. Thiết kế **event tracking, funnel, cohort, segmentation và guardrail metrics** với mẫu số, phạm vi thời gian và chất lượng dữ liệu rõ ràng.
5. Kết hợp những nguồn bằng chứng đôi khi **đồng thuận hoặc mâu thuẫn**, hình thành giả thuyết nguyên nhân và chọn thí nghiệm hoặc thay đổi sản phẩm phù hợp.
6. Sử dụng phản hồi trong **Sprint Review, refinement, lập kế hoạch phát hành, đánh giá sau phát hành và cải tiến dòng công việc**, đồng thời bảo vệ quyền riêng tư và tiêu chuẩn chất lượng.

## 1. Vì sao một nguồn phản hồi là chưa đủ?

Một nhóm phát triển nền tảng học trực tuyến vừa phát hành chức năng **“Tiếp tục học”**. Dashboard cho thấy số lượt mở bài từ trang chủ tăng. Tuy nhiên, bộ phận hỗ trợ nhận nhiều lời than phiền: “Tôi không biết bài nào vừa được lưu”, “Nút học tiếp không thấy ở điện thoại” và “Tôi bấm nhưng bị đưa về bài cũ”.

Vậy tính năng đã thành công hay chưa?

Nếu chỉ nhìn số lượt nhấn, đội có thể tuyên bố thành công dù người dùng nhấn nhiều lần vì bối rối. Nếu chỉ nghe ba lời phàn nàn, đội có thể cho rằng tất cả học viên gặp lỗi dù hàng nghìn người vẫn sử dụng tốt.

**Phản hồi định tính** giúp hiểu trải nghiệm, suy nghĩ, bối cảnh và *vì sao một hành vi có thể xảy ra*. **Dữ liệu sử dụng** giúp quan sát *điều gì xảy ra, với mức độ và xu hướng ra sao* trong phạm vi đo được.

> **Tư duy trọng tâm:** Dùng dữ liệu định lượng để xác định **mẫu hình và phạm vi vấn đề**, dùng bằng chứng định tính để hiểu **bối cảnh và cơ chế có thể gây ra mẫu hình ấy**; kiểm tra giả thuyết trước khi khẳng định nguyên nhân.

Phát triển Agile không chỉ là giao nhiều bản cập nhật; nó là **giao tăng dần, nhận phản hồi sớm và thích nghi**. Việc kết hợp bằng chứng giúp đội học được điều đáng tin hơn sau mỗi Increment hoặc lần phát hành.

### Ba câu hỏi cần giữ riêng

1. **Sản phẩm có hoạt động đúng và đạt chất lượng không?** Cần test, Definition of Done, giám sát và các kiểm tra an toàn.
2. **Người dùng thực sự có sử dụng nó không?** Cần event, funnel, cohort và dữ liệu hành vi đáng tin.
3. **Nó có giúp họ đạt kết quả quan trọng không?** Cần phỏng vấn/quan sát, outcome metric, so sánh có điều kiện và đôi khi thí nghiệm.

Một câu trả lời tích cực cho câu hỏi thứ hai **không tự động chứng minh** hai câu còn lại.

## 2. Phản hồi định tính và dữ liệu sử dụng khác nhau thế nào?

| Khía cạnh | Phản hồi định tính | Dữ liệu sử dụng định lượng |
| --- | --- | --- |
| **Câu hỏi mạnh nhất** | Người dùng hiểu, kỳ vọng, khó khăn và ra quyết định **như thế nào, vì sao**? | Hành vi được ghi nhận **bao nhiêu, khi nào, theo nhóm nào và thay đổi ra sao**? |
| **Nguồn điển hình** | Phỏng vấn, quan sát tác vụ, usability test, nhật ký trải nghiệm, phiếu góp ý dạng mở, ticket hỗ trợ | Sự kiện sản phẩm, funnel, log vận hành được tổng hợp, tỷ lệ sử dụng, cohort, kết quả thí nghiệm |
| **Dạng bằng chứng** | Trích dẫn có ngữ cảnh, hành động được quan sát, chủ đề lặp, ngoại lệ, mâu thuẫn | Số đếm, tỷ lệ, phân bố, xu hướng, nhóm người dùng và khoảng thời gian |
| **Điểm mạnh** | Phát hiện nhu cầu chưa được hỏi, cách hiểu sai, động cơ và tình huống khó | Nhìn quy mô, mức biến động, nhóm bị ảnh hưởng, hành vi qua nhiều lần |
| **Giới hạn** | Mẫu thường nhỏ hoặc tự chọn; câu hỏi dễ dẫn dắt; ý kiến không bằng hành vi | Event có thể thiếu/sai; hành vi không tự giải thích nguyên nhân; tương quan không đồng nghĩa nhân quả |
| **Câu hỏi kiểm tra chất lượng** | Ai được hỏi, trong bối cảnh nào, làm gì, có thiên lệch tuyển mẫu không? | Mẫu số là ai, event được định nghĩa thế nào, mất dữ liệu hoặc định danh trùng có không? |

### “Định tính” không đồng nghĩa “cảm tính”

Quan sát một học viên thực hiện tác vụ với kịch bản, ghi điểm vấp, điều kiện thiết bị và sự kiện xảy ra là **bằng chứng có phương pháp**, dù không phải một tỷ lệ thống kê của toàn bộ dân số.

### “Định lượng” không đồng nghĩa “khách quan tuyệt đối”

Một dashboard có thể sai khi event được gửi trùng, chỉ ghi nhận người đồng ý theo dõi, bỏ qua người gặp lỗi trước khi event được phát, hoặc đếm thiết bị thành người dùng. Những lựa chọn **định nghĩa và thu thập** luôn ảnh hưởng kết quả.

## 3. Bắt đầu từ mục tiêu sản phẩm, không từ một dashboard có sẵn

Trước khi mở công cụ phân tích, đội nên trả lời:

- **Product Goal hoặc mục tiêu dịch vụ** là gì?
- Ai là nhóm người dùng cần giúp và họ đang gặp vấn đề nào?
- Thay đổi sắp giao dự định tạo **khả năng sản phẩm** và **kết quả người dùng** gì?
- Có giả thuyết nào cần kiểm chứng thay vì coi là sự thật?
- Những rủi ro chất lượng, dữ liệu và quyền truy cập nào phải được bảo vệ?

### Ví dụ ba tầng mục tiêu

| Tầng | Ví dụ | Cách xác minh |
| --- | --- | --- |
| **Product Goal** | Học viên học liên tục trên thiết bị thường dùng mà không mất tiến độ được xác nhận | Theo dõi kết quả sử dụng dài hơn và phản hồi về độ tin cậy |
| **Sprint Goal / lát cắt ngắn hạn** | Học viên đăng nhập có thể mở lại đúng bài hợp lệ gần nhất từ trang chủ | Increment đáp ứng DoD; test quyền/truy cập; quan sát người dùng hoàn thành luồng |
| **Giả thuyết outcome** | Luồng “Tiếp tục học” giúp giảm thời gian tìm bài và tăng khả năng quay lại học | Thử tác vụ, đo hành vi theo cohort và quan sát qua thời gian |

**Tạo được chức năng** không đồng nghĩa **đã chứng minh tăng tỷ lệ quay lại học**. Một Sprint ngắn có thể tạo khả năng dùng được, nhưng outcome dài hạn cần thêm thời gian quan sát.

### Từ mục tiêu đến câu hỏi học hỏi

> **Mục tiêu:** Học viên dễ dàng tiếp tục việc học.
>
> **Giả thuyết:** Nút “Tiếp tục học” trên trang chủ sẽ giảm thao tác tìm lại bài.
>
> **Câu hỏi định tính:** Người học có nhận ra nút và hiểu “bài gần nhất” nghĩa là gì không? Khi không có tiến độ họ mong chờ điều gì?
>
> **Câu hỏi định lượng:** Trong số học viên đủ điều kiện nhìn thấy nút, bao nhiêu người bấm, bao nhiêu người mở thành công, thời gian từ trang chủ đến bài học ra sao?
>
> **Câu hỏi chất lượng:** API có trả dữ liệu đúng tài khoản và còn quyền, xử lý lỗi không báo thành công giả không?

Khi câu hỏi rõ, việc chọn sự kiện cần ghi và người cần phỏng vấn trở nên đơn giản hơn.

## 4. Phân biệt tín hiệu đầu vào, hành vi và outcome

Các chỉ số có thể đo những điều khác nhau. Không nên gọi mọi số đều là “tác động sản phẩm”.

| Nhóm tín hiệu | Ví dụ | Giới hạn |
| --- | --- | --- |
| **Hoạt động của đội / output** | Số story Done, số bản phát hành, số PR | Không tự chứng minh người dùng nhận giá trị |
| **Tiếp cận (exposure/reach)** | Số học viên đủ điều kiện đã thấy nút trong phiên được đo | Không chứng minh họ hiểu hoặc muốn dùng |
| **Tương tác (engagement/action)** | Người dùng bấm “Tiếp tục học”, tỷ lệ bấm trên số được thấy | Bấm có thể do tò mò hoặc lỗi; cần xét thành công |
| **Hoàn thành tác vụ (task success)** | Mở thành công đúng bài còn quyền | Gần với giá trị tức thời hơn nhưng chưa đo kết quả học lâu dài |
| **Outcome người dùng** | Thời gian tìm lại bài giảm; học viên quay lại học đúng nhu cầu | Có thể chịu ảnh hưởng của lịch học, nội dung và động lực khác |
| **Guardrail chất lượng** | Lỗi phân quyền, mất dữ liệu, crash, latency ở phân vị cần thiết | Phải xem cùng hành vi; tốc độ không được đổi bằng an toàn |
| **Hiệu quả vận hành** | Thời gian phát hiện/sửa lỗi, số ticket hỗ trợ có phân loại | Bị ảnh hưởng bởi chất lượng quan sát và cách ghi ticket |

**North Star Metric**, KPI hay OKR có thể hỗ trợ định hướng, nhưng **không có bộ chỉ số bắt buộc cho mọi đội Agile**. Chỉ số tốt là chỉ số phục vụ một quyết định cụ thể, có cách đo nhất quán và phản ánh giá trị cần tạo.

### Câu hỏi phản biện một chỉ số

> “Nếu con số này tăng, chúng ta có thể chắc điều gì đã tốt lên? Có cách nào nó tăng trong khi trải nghiệm hoặc chất lượng thực tế xấu đi không?”

Ví dụ, số lượt nhấn nút tăng khi nút liên tục tải lỗi và người dùng phải thử lại. Vì vậy cần xem **tỷ lệ hoàn thành tác vụ và số lần thao tác lại**, không chỉ đếm click.

## 5. Thu thập phản hồi định tính có phương pháp

Phản hồi định tính nên bắt đầu từ **câu hỏi mở và quan sát hành vi**, không bắt đầu từ việc thuyết phục người dùng thích tính năng vừa làm.

### Một số cách thu thập

| Cách | Phù hợp khi | Điểm cần kiểm soát |
| --- | --- | --- |
| **Phỏng vấn theo ngữ cảnh** | Muốn hiểu hành trình học, động cơ, điều khó chịu và giải pháp người dùng tự tạo | Tránh câu hỏi dẫn dắt và nhớ lại thiếu chính xác |
| **Usability test có tác vụ** | Muốn biết người dùng có tìm thấy và hoàn thành luồng mới | Không hướng dẫn trước vị trí nút; ghi những lần vấp |
| **Quan sát sử dụng thực tế** | Muốn hiểu thiết bị, gián đoạn, điều kiện mạng và tình huống ngoài dự kiến | Cần sự đồng ý và giới hạn dữ liệu quan sát |
| **Phiếu phản hồi mở** | Muốn người dùng tự mô tả vấn đề vào thời điểm thuận tiện | Người trả lời thường tự chọn, không đại diện cho tất cả |
| **Ticket hỗ trợ/đánh giá ứng dụng** | Muốn phát hiện tác động nghiêm trọng và lỗi lặp lại | Người gặp vấn đề có xu hướng xuất hiện nhiều hơn |
| **Nhật ký trải nghiệm** | Muốn hiểu hành vi qua nhiều ngày và hoàn cảnh khác nhau | Dễ thiếu dữ liệu hoặc bị ảnh hưởng bởi việc phải tự ghi |
| **Trao đổi với bộ phận vận hành** | Muốn hiểu lỗi hệ thống, quy trình hỗ trợ và cách khôi phục | Cần tách nhận định chủ quan với dấu vết sự cố |

### Ví dụ câu hỏi phỏng vấn trung lập

- “Lần gần nhất bạn quay lại một bài đang học, bạn đã làm gì từ đầu đến cuối?”
- “Ở bước nào bạn phải dừng lại hoặc suy nghĩ?”
- “Bạn kỳ vọng nút ‘Tiếp tục học’ đưa mình đến đâu?”
- “Có thể cho xem một ví dụ khi bạn không tìm được bài không?”
- “Khi thấy thông báo này, bạn nghĩ tiến độ đã được lưu hay chưa?”
- “Bạn đã xử lý tình huống ấy như thế nào trước khi có tính năng mới?”

Tránh hỏi:

> “Nút mới rất thuận tiện phải không?”

Vì câu hỏi đã **gợi ý câu trả lời tích cực**. Cũng không nên hỏi “Bạn có muốn AI tự động chọn bài thay không?” rồi coi “có” là bằng chứng về nhu cầu được ưu tiên; hãy kiểm tra **vấn đề thực tế trước giải pháp dự đoán**.

## 6. Tuyển người tham gia và tránh thiên lệch mẫu

Không có một cỡ mẫu phỏng vấn đúng cho mọi dự án. Số người cần trao đổi phụ thuộc **mức đa dạng của người dùng, loại câu hỏi, rủi ro và việc các chủ đề mới còn xuất hiện không**.

### Một số nhóm đáng phân biệt

- Người mới bắt đầu khóa học so với người có lịch sử học dài.
- Người học chủ yếu trên điện thoại so với desktop.
- Người thường đổi thiết bị so với chỉ sử dụng một thiết bị.
- Người có mạng không ổn định hoặc dùng công nghệ hỗ trợ.
- Người sử dụng tính năng thường xuyên so với người **đã được thấy nhưng không dùng**.
- Người từng gặp lỗi hoặc liên hệ hỗ trợ so với người không có vấn đề đã biết.

Nếu chỉ phỏng vấn năm người dùng nhiệt tình nhất, đội có thể bỏ lỡ lý do **người không sử dụng** không tìm thấy hoặc không tin tưởng tính năng.

### Các thiên lệch thường gặp

| Thiên lệch | Ví dụ | Hướng giảm rủi ro |
| --- | --- | --- |
| **Self-selection** | Chỉ người bực bội mới bấm “Gửi góp ý” | Chủ động tiếp cận thêm người dùng không gửi phản hồi |
| **Selection/sampling bias** | Chỉ tuyển học viên desktop ở nhóm nội bộ | Phân lớp mẫu theo các nhóm phù hợp với quyết định |
| **Recall bias** | Hỏi người dùng nhớ lại chi tiết đã diễn ra một tháng trước | Quan sát tác vụ hoặc hỏi tình huống gần đây |
| **Leading question** | “Tính năng mới giúp bạn nhiều đúng không?” | Dùng câu hỏi trung lập và yêu cầu kể việc đã làm |
| **Courtesy/social desirability** | Người tham gia trả lời tích cực để làm hài lòng người nghiên cứu | Nhấn mạnh không đánh giá họ; tìm hành vi cụ thể |
| **Survivorship bias** | Chỉ phân tích người đã mở bài thành công | Xem cả người không thấy nút, thoát giữa luồng và bị lỗi |

**Nghiên cứu định tính nhỏ giúp phát hiện cơ chế và câu hỏi mới**, không cho phép tự suy rộng: “5/8 người nói khó tìm nghĩa là 62,5% toàn bộ học viên gặp vấn đề.” Tỷ lệ trong nhóm người được tuyển **không tự là ước lượng dân số**.

## 7. Tổng hợp phản hồi định tính thành bằng chứng hành động được

Đọc vài câu góp ý riêng lẻ dễ khiến đội ưu tiên câu chuyện gây xúc động nhất. Thay vào đó, hãy phân tích **chủ đề, bối cảnh, bằng chứng và độ tin cậy**.

### Ví dụ dữ liệu giả định từ tám buổi quan sát

| Mã quan sát | Điều xảy ra trong tác vụ | Người dùng diễn giải | Câu hỏi cần kiểm chứng |
| --- | --- | --- | --- |
| O1 | Không tìm thấy nút khi cuộn trên điện thoại | “Tôi tưởng học tiếp ở trang khóa học.” | Nút có bị bỏ qua thường xuyên ở mobile? |
| O2 | Nhấn nút nhưng mở bài cũ | “Có lẽ hệ thống chưa lưu lần trước.” | Lỗi dữ liệu, quy tắc “gần nhất” hay kỳ vọng khác nhau? |
| O3 | Không có nút do chưa từng bắt đầu khóa | “Trang chủ bị lỗi à?” | Trạng thái rỗng có đủ rõ? |
| O4 | Nhấn hai lần vì màn hình phản hồi chậm | “Không biết nút có nhận thao tác không.” | Latency và feedback trạng thái có vấn đề? |
| O5 | Mở đúng bài và tiếp tục ngay | “Tôi không phải tìm trong danh sách nữa.” | Luồng tốt trong điều kiện nào? |

Năm dòng ở đây chỉ là **mẫu ghi chép minh họa**, không đại diện toàn bộ tám người hay toàn bộ học viên.

### Cách xử lý từng bước

1. **Lưu ngữ cảnh tối thiểu:** Loại người dùng, thiết bị, tác vụ, phiên bản sản phẩm, điều kiện mạng nếu liên quan.
2. **Tách quan sát khỏi diễn giải:** “Nhấn hai lần” là điều quan sát; “do hệ thống chậm” là giả thuyết cần kiểm tra.
3. **Nhóm thành chủ đề:** Khả năng tìm thấy, hiểu trạng thái, dữ liệu sai, độ trễ, giá trị nhận được.
4. **Giữ ngoại lệ và tiếng nói trái chiều:** Người dùng không gặp lỗi cho biết điều kiện nào đang hoạt động tốt.
5. **Gắn tác động và mức chắc chắn:** Lỗi lộ dữ liệu có mức nghiêm trọng cao dù ít người nêu.
6. **Đề xuất kiểm tra tiếp:** Event, log, phỏng vấn bổ sung, usability test hoặc tái hiện lỗi.

### Cách viết insight không phóng đại

Không nên viết:

> “Người dùng không thích nút Tiếp tục học.”

Nên viết:

> “Trong các phiên thử có người dùng chủ yếu dùng điện thoại, một số người không tìm thấy nút ở vị trí hiện tại. Chúng ta cần xem dữ liệu exposure/click theo thiết bị và thử tác vụ với mẫu mobile đa dạng hơn.”

Insight tốt **có bằng chứng, phạm vi áp dụng và câu hỏi tiếp theo**.

## 8. Thiết kế dữ liệu sử dụng: bắt đầu từ sự kiện có nghĩa

Để biết người dùng có thực hiện hành trình dự định hay không, đội cần định nghĩa các **product events**. Không nên ghi mọi click chỉ vì công cụ analytics cho phép.

### Ví dụ event cho “Tiếp tục học”

| Sự kiện minh họa | Khi nào xảy ra? | Thuộc tính cần có nếu được phép | Cần tránh |
| --- | --- | --- | --- |
| **resume_entry_visible** | Nút/entry point thực sự được hiển thị cho người dùng đủ điều kiện | Mã phiên giả danh, loại thiết bị, phiên bản giao diện, thời gian | Gọi event khi component chỉ được khởi tạo nhưng chưa hiển thị |
| **resume_entry_clicked** | Người dùng chủ động chọn “Tiếp tục học” | Mã phiên, event ID, vị trí entry point | Đếm nhấn tự động hoặc retry như ý định người dùng mới |
| **resume_open_succeeded** | Luồng đã mở bài hợp lệ theo điều kiện success đã định nghĩa | Mã phiên, thời gian từ thao tác, nhóm nội dung nếu cần | Gọi “success” ngay khi API trả 200 nhưng nội dung chưa mở |
| **resume_open_failed** | Luồng không hoàn thành do một lỗi xác định | Loại lỗi đã được phân loại, phiên bản, mã phiên | Log token, nội dung bài học nhạy cảm hoặc dữ liệu cá nhân không cần thiết |
| **resume_empty_state_seen** | Học viên đủ điều kiện truy cập trang nhưng không có tiến độ hợp lệ | Mã phiên/thiết bị, trạng thái nghiệp vụ | Trộn trạng thái không có dữ liệu với lỗi API |
| **lesson_learning_resumed** | Người dùng thực sự bắt đầu tương tác với bài sau khi mở | Mã phiên, dấu thời gian phù hợp | Tự coi chỉ số này đồng nghĩa học hiệu quả hay hoàn thành khóa |

**Tên event không phải chuẩn Agile hay Scrum**; đây là bộ ví dụ để đội cùng thỏa thuận. Sự kiện phải được định nghĩa theo hành vi thực tế, tránh thuật ngữ “success” mơ hồ.

### Event taxonomy cần ổn định

Đối với mỗi event, cần ghi ngắn:

- Ý nghĩa nghiệp vụ và **điểm kích hoạt chính xác**.
- Các thuộc tính được cho phép, kiểu dữ liệu và danh mục giá trị.
- Cách nhận diện **một lần thao tác**, session và người dùng trong phạm vi có quyền đo.
- Event phát từ client/server nào; độ tin cậy khi mạng hoặc trình duyệt bị chặn.
- Phiên bản schema và thay đổi tương thích.
- Quy tắc làm sạch, chống event trùng, xử lý thời gian và độ trễ thu thập.
- Chủ sở hữu quyết định khi số liệu khác kỳ vọng.

Sự kiện có nghĩa rõ giúp kết nối định lượng với **câu hỏi từ phỏng vấn**, thay vì tạo hàng trăm biểu đồ khó giải thích.

## 9. Độ tin cậy của telemetry: event đúng không chỉ vì có dữ liệu

Một phép đếm chính xác về mặt SQL vẫn sai nếu **quá trình ghi sự kiện** sai.

### Nguồn sai thường gặp

1. **Gửi trùng:** Client retry làm một click xuất hiện hai lần.
2. **Thiếu event:** Người dùng mất mạng, chặn tracking hoặc đóng trình duyệt trước khi event được gửi.
3. **Sai thời gian:** Đồng hồ thiết bị lệch; event_time khác thời điểm server nhận.
4. **Sai định danh:** Một người dùng nhiều thiết bị hoặc đổi tài khoản trên một máy.
5. **Sai định nghĩa:** Có code gửi success ngay khi request bắt đầu, không phải khi bài học mở.
6. **Thay phiên bản:** Event từ ứng dụng cũ và mới cùng tên nhưng ý nghĩa khác.
7. **Sai phạm vi:** Gộp traffic test, bot, tài khoản nội bộ hoặc nhóm không đủ điều kiện.
8. **Không đủ consent/cơ sở xử lý:** Dữ liệu thu thập không phù hợp quyền riêng tư hoặc chính sách hiện hành.

### Bảng kiểm thử sự kiện

| Tình huống | Điều cần kiểm tra |
| --- | --- |
| Một người nhấn một lần | Có một thao tác logic, không bị đếm hai lần do retry |
| Nhấn rồi network timeout | Có thể thiếu một số event client; không được coi số liệu là toàn bộ sự thật |
| Nút không hiển thị trên mobile | Không gửi exposure sai; phân biệt không đủ điều kiện với lỗi UI |
| Client mở bài rồi đóng tab rất nhanh | Định nghĩa success có phản ánh đúng tác vụ hay chỉ navigation? |
| A đăng xuất, B đăng nhập cùng thiết bị | Không trộn session/định danh gây lộ dữ liệu hoặc sai phân khúc |
| Release phiên bản mới | Event schema còn tương thích; dashboard không đổi nghĩa âm thầm |
| Người dùng từ chối theo dõi tùy chọn | Tôn trọng lựa chọn; không cố vượt kiểm soát riêng tư |

Một thay đổi sản phẩm có thể trông “đột ngột tăng chuyển đổi” chỉ vì **instrumentation được sửa**. Vì vậy mọi phân tích cần biết phiên bản release và thay đổi tracking liên quan.

## 10. Funnel: từ việc nhìn thấy đến hoàn thành tác vụ

**Funnel** mô tả các bước có thứ tự trong một hành trình và số người/phiên đủ điều kiện đi tới mỗi bước. Muốn funnel hữu ích phải nêu:

- **Đơn vị phân tích:** Người dùng duy nhất, phiên hay lượt thao tác?
- **Mốc bắt đầu:** Ai được tính vào nhóm đủ điều kiện?
- **Thời gian hoàn thành:** Ví dụ cùng session hay trong vòng vài phút sau khi nhấn?
- **Thứ tự sự kiện:** Có bắt buộc các bước theo thứ tự và cùng phiên không?
- **Cách tính khi lặp:** Một người nhấn ba lần được đếm một hay ba?
- **Loại bỏ và giới hạn:** Tài khoản thử, consent, lỗi dữ liệu và những nhóm không đủ điều kiện.

### Ví dụ funnel giả định theo người dùng duy nhất

Giả sử trong một tuần, đội ghi nhận:

| Bước | Số học viên duy nhất | Tỷ lệ so với bước trước | Tỷ lệ so với người thấy entry point |
| --- | ---: | ---: | ---: |
| Đủ điều kiện và thật sự thấy nút | 1.000 | — | 100% |
| Nhấn nút ít nhất một lần | 260 | 26% | 26% |
| Mở đúng bài hợp lệ trong cửa sổ đo | 208 | 80% | 20,8% |

Các con số là **ví dụ minh họa, không phải dữ liệu thực**. Mỗi người được đếm tối đa một lần trong từng bước theo quy ước đã chọn.

- **Tỷ lệ nhấn (CTR) theo exposure:** 260 / 1.000 = **26%**.
- **Tỷ lệ thành công sau khi nhấn:** 208 / 260 = **80%**.
- **Tỷ lệ hoàn thành từ exposure:** 208 / 1.000 = **20,8%**.

Nếu 52 người đã nhấn nhưng không có sự kiện thành công, **không được tự kết luận cả 52 gặp lỗi kỹ thuật**. Có thể có lỗi, người dùng bỏ giữa chừng, bị chuyển trang hoặc thiếu event. Cần xem error events, log, định nghĩa success và mẫu session cụ thể.

### Một sơ đồ funnel

~~~mermaid
flowchart TD
    A["1.000 học viên thấy nút"] --> B["260 học viên nhấn (26%)"]
    B --> C["208 học viên mở bài hợp lệ (80% sau click)"]
    B --> D["52 chưa ghi nhận success"]
    D --> E["Cần phân loại: lỗi / bỏ dở / dữ liệu thiếu"]
    C --> F["Tiếp tục học? Cần đo thêm outcome"]
~~~

**Funnel trả lời nơi xảy ra mất bước**, không tự chỉ ra tại sao. Phản hồi định tính giúp đội điều tra từng điểm rơi.

## 11. Chọn mẫu số phù hợp để tránh kết luận sai

Ví dụ số liệu “200 người mở bài” có thể nghe tốt hoặc xấu tùy mẫu số:

- **200/1.000 người đủ điều kiện** khác với **200/250 người bấm**.
- Tính theo **lượt thao tác** khác với **người dùng duy nhất**.
- Tính trên **tất cả học viên** khác với chỉ **học viên đã có tiến độ**.
- Tính trong **một phiên** khác với **bảy ngày**.

### Ví dụ dữ liệu không nên trộn

| Chỉ số | Công thức gợi ý | Ý nghĩa |
| --- | --- | --- |
| **Exposure rate** | Người đủ điều kiện thấy nút / người đủ điều kiện trong phạm vi đo | UI có thực sự tiếp cận người cần tính năng? |
| **CTR** | Người nhấn / người thật sự thấy nút | Entry point có được tương tác? |
| **Task success after click** | Người mở bài đúng / người nhấn | Luồng sau thao tác có hoàn tất? |
| **End-to-end conversion** | Người mở bài đúng / người đủ điều kiện đã thấy nút | Toàn hành trình có đi đến kết quả tức thời? |
| **Error rate** | Số yêu cầu lỗi / số yêu cầu hợp lệ đã quan sát | Độ tin cậy của dịch vụ trong phạm vi đo, không trực tiếp là tỷ lệ người dùng gặp lỗi |
| **Time to resume** | Thời gian từ mốc rõ ràng đến mở bài thành công | Mức ma sát thời gian của tác vụ, cần xem phân bố |

Nếu có nhóm **không có tiến độ**, không nên đưa họ vào mẫu số của funnel “mở lại bài đã học” như thể họ thất bại. Có thể xây một funnel riêng cho **trạng thái bắt đầu học**.

### Khi cần một đoạn truy vấn minh họa

~~~sql
-- SQL khái niệm: mỗi bước đếm người duy nhất trong cùng kỳ,
-- cần lọc user đủ điều kiện, sự kiện theo đúng thứ tự
-- và cửa sổ thời gian trước khi dùng cho dashboard thật.
SELECT event_name,
       COUNT(DISTINCT analytics_subject_id) AS distinct_subjects
FROM product_events
WHERE event_date BETWEEN DATE '2026-11-01' AND DATE '2026-11-07'
  AND event_name IN (
      'resume_entry_visible',
      'resume_entry_clicked',
      'resume_open_succeeded'
  )
GROUP BY event_name;
~~~

**Giới hạn quan trọng:** Truy vấn này chỉ đếm riêng từng event; **chưa phải funnel theo thứ tự và cùng cohort**. Một dashboard thực phải nối đúng session/đối tượng được phép phân tích, loại trùng, kiểm tra thứ tự và thời gian. Không nên mang ba số độc lập này chia cho nhau rồi coi chắc là tỷ lệ chuyển đổi nếu các nhóm không lồng nhau.

## 12. Cohort và segmentation: người dùng nào gặp vấn đề?

Một tỷ lệ tổng có thể che khác biệt rất lớn giữa các nhóm người dùng. **Segmentation** chia dữ liệu theo đặc điểm có ý nghĩa; **cohort** thường là tập người dùng được xác định bởi một sự kiện hoặc thời điểm chung để theo dõi về sau.

### Ví dụ phân tích theo thiết bị

Giả sử cùng một funnel và cùng một tuần:

| Thiết bị | Thấy nút | Nhấn | Mở thành công | CTR | Thành công sau nhấn |
| --- | ---: | ---: | ---: | ---: | ---: |
| Mobile | 650 | 130 | 91 | 20% | 70% |
| Desktop | 350 | 130 | 117 | 37,1% | 90% |
| **Tổng** | **1.000** | **260** | **208** | **26%** | **80%** |

Đây là số liệu **giả định**. Tín hiệu cần điều tra:

- Người dùng mobile ít nhấn hơn; có thể nút khó thấy, nhu cầu khác, hoặc cách ghi exposure sai.
- Trong nhóm đã nhấn, mobile mở bài thành công ít hơn; có thể do mạng, phiên đăng nhập, lỗi hiển thị hoặc khác biệt kiểu nội dung.
- Desktop có thể gồm nhóm học viên với lịch học hoặc thiết bị khác; **không thể tự quy mọi khác biệt cho giao diện**.

### Cohort theo thời điểm lần đầu dùng

Ví dụ, nhóm học viên **lần đầu mở bài từ nút “Tiếp tục học” trong tuần 1** được theo dõi liệu họ có quay lại học trong các ngày sau hay không. Để so sánh cần:

1. Định nghĩa rõ “quay lại” là sự kiện nào: đăng nhập, mở bài hay học có ý nghĩa.
2. Dùng cùng **cửa sổ theo dõi** cho các cohort đã đủ thời gian quan sát.
3. Phân biệt người mới và người đã học lâu năm.
4. Xem có thay đổi chiến dịch, nội dung hoặc lịch học cùng thời kỳ không.
5. Không nhầm **retention** với số lượt click ngay sau khi phát hành.

### Tránh phân khúc quá vụn

Nếu cắt theo thiết bị, vùng, khóa học, phiên bản, loại tài khoản, tuần đăng ký và nguồn tiếp cận cùng lúc, một ô có thể chỉ còn vài người. Tỷ lệ nhìn rất khác nhưng **dao động mạnh và có nguy cơ tái nhận diện**. Hãy giới hạn phân khúc theo câu hỏi, mức mẫu phù hợp và chính sách riêng tư.

## 13. Khi định tính và định lượng cùng chỉ về một vấn đề

**Tam giác hóa bằng chứng (triangulation)** là đối chiếu các nguồn độc lập tương đối để hiểu một hiện tượng tốt hơn, không phải lấy trung bình ý kiến với phần trăm.

### Ví dụ tín hiệu đồng thuận

- **Phỏng vấn/quan sát:** Nhiều học viên thử trên mobile không nhìn thấy nút.
- **Dữ liệu sử dụng:** CTR mobile thấp hơn desktop khi đã kiểm tra cùng định nghĩa exposure.
- **Kiểm tra kỹ thuật:** Trên một số chiều cao màn hình, nút nằm dưới vùng nội dung phải cuộn.

Ba nguồn **phù hợp với giả thuyết** rằng khả năng tìm thấy trên mobile có vấn đề. Đội có thể thử thiết kế entry point dễ thấy hơn và theo dõi cả khả năng hoàn thành tác vụ lẫn lỗi/khả năng tiếp cận.

### Ma trận tổng hợp

| Chủ đề từ định tính | Tín hiệu định lượng | Kiểm tra kỹ thuật/bối cảnh | Quyết định tiếp theo |
| --- | --- | --- | --- |
| “Khó thấy nút” | CTR mobile thấp trong cohort phù hợp | Vị trí trên màn hình, exposure trigger có đúng | Usability test bố cục khác và đo funnel |
| “Bấm nhưng không vào bài” | Drop-off sau click cao hơn trên mobile | Lỗi API, session, mạng yếu, event mất | Tái hiện lỗi, thêm test và telemetry theo chính sách |
| “Tôi không chắc đã lưu tiến độ” | Nhiều thao tác thử lại, tỷ lệ báo lỗi thấp | Quy tắc lưu, feedback trạng thái, request retry | Làm rõ trạng thái lưu, test hành vi và thử thông điệp |
| “Tôi rất thích mở nhanh” | Time-to-resume giảm trong nhóm sử dụng | Nhóm có thể đã quen UI từ trước | Xem retention và thu phản hồi thêm ở nhóm mới |

Ma trận giúp đội tách **điều đã quan sát** khỏi **nguyên nhân còn cần xác minh**.

## 14. Khi các nguồn mâu thuẫn nhau: đừng chọn nguồn mình thích

Hai nguồn có thể không cùng kết luận. Mâu thuẫn là thông tin hữu ích để kiểm tra **phạm vi, mẫu, phép đo và giả định**.

### Trường hợp A: phỏng vấn tích cực, funnel thấp

Người dùng trong buổi usability test khen chức năng dễ dùng; nhưng chỉ 15% người đủ điều kiện nhấn ngoài sản phẩm thật.

Các khả năng:

- Mẫu phỏng vấn gồm người học có động lực cao.
- Người dùng ngoài thực tế không nhìn thấy nút.
- Nhiều người không cần tiếp tục ngay trong phiên đó.
- Event exposure hoặc click bị ghi sai.
- Buổi phỏng vấn có hướng dẫn khiến người dùng biết nơi cần nhấn.

**Hành động:** Kiểm tra event/eligibility, tuyển người không sử dụng, quan sát tác vụ không hướng dẫn và phân tích theo bối cảnh.

### Trường hợp B: chỉ số tăng, phản hồi tiêu cực

Click tăng nhưng có thêm ticket “mở sai bài”.

Các khả năng:

- Nhiều lần click do retry hoặc bối rối.
- Chỉ số tăng nhờ nhóm người dùng mới, trong khi một nhóm bị lỗi.
- Có regression về quyền hoặc dữ liệu.
- Bộ phận hỗ trợ phân loại phản hồi kỹ hơn nên số ticket tăng.

**Hành động:** Kiểm tra guardrail chất lượng ngay, xác minh dữ liệu, phân tích theo cohort và tái hiện kịch bản. **Không dùng thành công KPI để bỏ qua lỗi an toàn**.

### Trường hợp C: số lỗi được ghi nhận tăng sau release

Khi bổ sung giám sát, số lỗi trong báo cáo tăng. Điều đó có thể do **phát hiện tốt hơn**, không đủ để khẳng định sản phẩm xấu đi. Cần xem mức nghiêm trọng, tỷ lệ người dùng ảnh hưởng, điều kiện đo và dữ liệu trước/sau.

### Những câu hỏi kiểm tra mâu thuẫn

1. Hai nguồn đang nói về **cùng nhóm người dùng và cùng hành trình** không?
2. Thời gian thu thập có trùng hay có release/chiến dịch ở giữa?
3. Định nghĩa success, lỗi và exposure có nhất quán không?
4. Ai bị loại khỏi dữ liệu do consent, tracking blocker hoặc thiết bị?
5. Có nhóm nhỏ bị tác động nghiêm trọng bị trung bình tổng che lấp không?
6. Có bằng chứng kỹ thuật nào đủ mạnh để khẳng định hoặc bác bỏ một giả thuyết?

## 15. Tránh nhầm tương quan với nguyên nhân

Sau khi phát hành nút “Tiếp tục học”, tỷ lệ học viên quay lại học tăng. Ta **chưa thể tự kết luận** nút mới gây ra sự tăng đó.

Cùng lúc có thể đã xảy ra:

- Học kỳ mới bắt đầu hoặc có lịch kiểm tra sắp đến.
- Nhóm marketing gửi chiến dịch nhắc học.
- Nội dung khóa học được đổi hoặc có bài mới hấp dẫn hơn.
- Số người dùng mới tăng, làm thay đổi cấu trúc cohort.
- Tính năng khác được phát hành cùng thời điểm.
- Tracking và định nghĩa “quay lại” vừa thay đổi.

### Ba cấp độ phát biểu

| Cấp độ | Phát biểu phù hợp | Điều không được khẳng định |
| --- | --- | --- |
| **Mô tả** | “Tỷ lệ quay lại trong nhóm được quan sát tăng sau release.” | Không khẳng định do tính năng gây ra |
| **Giả thuyết** | “Nút mới có thể giúp giảm thao tác và góp phần tăng quay lại.” | Không trình bày như nguyên nhân đã chứng minh |
| **Bằng chứng nhân quả mạnh hơn** | “Trong thí nghiệm phân nhóm hợp lệ, phiên bản mới tạo chênh lệch ở metric đã định nghĩa.” | Không mở rộng ngoài đối tượng, thời gian hoặc điều kiện thí nghiệm |

Ngay cả thí nghiệm cũng có giới hạn về cỡ mẫu, thực thi, thời gian, quyền riêng tư và ảnh hưởng giữa các nhóm. **Phương pháp càng rõ thì kết luận càng có giới hạn đáng tin**.

### Hiệu ứng trộn nhóm

Một chỉ số tổng có thể tăng do tỷ trọng nhóm mobile/desktop thay đổi trong khi tỷ lệ từng nhóm không cải thiện. Đây là dạng rủi ro thường được nhắc khi nói về **hiệu ứng Simpson**. Vì vậy cần xem cohort và tỷ trọng trước khi kết luận về nguyên nhân.

## 16. Chuyển bằng chứng thành giả thuyết và quyết định

Thu thập dữ liệu không phải đích cuối. Giá trị nằm ở việc đội quyết định **nên học thêm, sửa lỗi, thay đổi sản phẩm hay tiếp tục đầu tư**.

### Mẫu giả thuyết có thể kiểm chứng

> **Vì** [quan sát định tính có ngữ cảnh] và [tín hiệu sử dụng đáng tin] gợi ý [vấn đề], **chúng ta tin rằng** [thay đổi cụ thể] có thể giúp [nhóm người dùng] đạt [kết quả]. **Chúng ta sẽ kiểm tra bằng** [tác vụ, metric, cohort, thời gian], **đồng thời bảo vệ** [guardrail chất lượng và quyền riêng tư].

**Ví dụ:**

> “Vì người dùng mobile trong quan sát khó tìm entry point và CTR mobile thấp hơn trong cùng kỳ đo, chúng ta giả thuyết đưa nút ‘Tiếp tục học’ lên vị trí dễ thấy sẽ tăng tỷ lệ hoàn thành luồng trên mobile. Chúng ta sẽ thử với nhóm phù hợp, đo tỷ lệ mở bài đúng và thời gian thực hiện, đồng thời không tăng lỗi phân quyền, crash hoặc cản trở khả năng tiếp cận.”

### Ưu tiên theo giá trị và rủi ro

| Phát hiện | Việc nên cân nhắc | Lý do |
| --- | --- | --- |
| Bị lộ hoặc đọc sai dữ liệu tài khoản | **Xử lý an toàn ngay theo mức nghiêm trọng** | Không chờ đủ mẫu phỏng vấn hay thí nghiệm tăng CTR |
| Nhiều người không nhìn thấy nút | Thử cải thiện khả năng tìm thấy | Có vấn đề trải nghiệm và tín hiệu funnel gợi ý |
| Một người đề nghị một hệ thống gợi ý AI phức tạp | Tìm hiểu nhu cầu thực trước khi xây | Ý tưởng đơn lẻ chưa chứng minh giá trị |
| Sau click có drop-off cao nhưng không có error telemetry | Sửa phép đo và tái hiện hành trình | Thiếu dữ liệu để chọn đúng can thiệp |
| Thời gian tìm bài giảm, không tăng lỗi | Tiếp tục quan sát và cân nhắc mở rộng | Tín hiệu hứa hẹn, cần xem cohort và outcome dài hơn |

Không có công thức chấm điểm ưu tiên nào thay được **đánh giá rủi ro, nghĩa vụ và mục tiêu sản phẩm**.

## 17. Thiết kế thí nghiệm sản phẩm có trách nhiệm

Không phải mọi giả thuyết đều cần A/B test. Có thể dùng:

- **Usability test có tác vụ:** Khi chưa biết người dùng có hiểu thiết kế hay không.
- **Prototype thử trên nhóm nhỏ:** Khi muốn chọn cách diễn đạt hoặc bố cục trước khi phát triển đầy đủ.
- **A/B test hoặc randomized experiment:** Khi cần đánh giá tác động giữa hai biến thể trong điều kiện có thể phân nhóm và đo đủ tin cậy.
- **Phát hành theo giai đoạn (staged rollout):** Khi cần kiểm soát rủi ro và quan sát một Increment đã đủ chất lượng.
- **Quan sát trước/sau có bối cảnh:** Khi không thể thử nghiệm ngẫu nhiên nhưng vẫn muốn hiểu tín hiệu; kết luận nhân quả cần khiêm tốn.
- **Nghiên cứu sâu với người gặp lỗi:** Khi rủi ro an toàn hoặc nguyên nhân phức tạp cần tái hiện.

### Bảy yếu tố của một thí nghiệm

1. **Giả thuyết và đối tượng:** Ví dụ học viên mobile đủ điều kiện thấy “Tiếp tục học”.
2. **Can thiệp duy nhất nếu khả thi:** Đổi vị trí nút, không đồng thời thay thuật toán chọn bài và tracking.
3. **Metric chính:** Ví dụ tỷ lệ mở đúng bài từ người được exposure trong cửa sổ thống nhất.
4. **Guardrail:** Lỗi phân quyền, mất tiến độ, latency, crash, tiếp cận, phản hồi tiêu cực.
5. **Thiết kế phân nhóm:** Nếu dùng ngẫu nhiên, giữ assignment ổn định ở cấp đối tượng phù hợp để tránh một người thấy cả hai biến thể lẫn lộn.
6. **Thời gian và cỡ mẫu:** Xác định kế hoạch quan sát trước, cân nhắc biến động theo lịch học và độ tin cậy thống kê.
7. **Điểm quyết định:** Tiếp tục, quay lại, điều chỉnh, mở rộng hoặc thu thêm bằng chứng.

### Không thực nghiệm bằng cách cố ý gây hại

Không nên cố tình cho một nhóm người dùng **lộ dữ liệu, thiếu bảo vệ quyền hoặc mất tiến độ** chỉ để đo khả năng tăng trưởng. Các biến thể phải đáp ứng tiêu chuẩn chất lượng và nghĩa vụ bắt buộc. Việc thu thập dữ liệu cũng phải tuân thủ quyền riêng tư, consent và chính sách của tổ chức.

### Khi kết quả không rõ

Nếu thí nghiệm không cho bằng chứng chênh lệch đủ mạnh, không được tự diễn đạt “hai biến thể chắc chắn giống nhau”. Có thể vì hiệu quả nhỏ, mẫu thiếu, phép đo nhiễu, test thiếu thời gian hoặc giả thuyết sai. Cần nêu rõ **độ bất định và giới hạn kết luận**.

## 18. Phản hồi và phát hành: phân biệt Increment, release và outcome

Trong Scrum, **Increment** là bước tiến cụ thể hướng tới Product Goal, bổ sung vào những Increment trước, có thể sử dụng và đáp ứng **Definition of Done**. Một Sprint có thể tạo **nhiều Increment**. Increment có thể được giao cho các bên liên quan **trước khi Sprint kết thúc**; Sprint Review không phải cổng bắt buộc cho phát hành.

### Bốn trạng thái không đồng nghĩa

| Trạng thái | Nghĩa | Điều chưa thể suy ra |
| --- | --- | --- |
| **Code đã merge** | Thay đổi nằm trong dòng code tích hợp | Chưa đủ để gọi Done hoặc đã có giá trị |
| **Increment đạt DoD** | Phần sản phẩm sử dụng được, được kiểm chứng với chất lượng chung | Không có nghĩa tất cả người dùng đã được bật tính năng |
| **Đã phát hành** | Người dùng mục tiêu có thể dùng theo phạm vi và chính sách release | Không tự chứng minh nhu cầu đã được giải quyết |
| **Đạt outcome** | Có bằng chứng người dùng nhận kết quả mong muốn theo cách đo đã định nghĩa | Không chứng minh mọi giả thuyết hoặc tác động dài hạn |

### Chu trình phản hồi theo từng lát cắt

~~~mermaid
flowchart LR
    A["User story + giả thuyết"] --> B["Increment đạt DoD"]
    B --> C["Phát hành theo chính sách"]
    C --> D["Theo dõi hành vi + chất lượng"]
    D --> E["Phỏng vấn / quan sát / hỗ trợ"]
    E --> F["Đối chiếu và quyết định"]
    F --> G["Điều chỉnh Product Backlog"]
    G --> A
~~~

**Không cần chờ tới cuối Sprint mới thu phản hồi.** Nhưng cũng không thể lấy lý do “phát hành sớm để học” để bỏ qua kiểm tra an toàn hoặc điều kiện DoD.

### Trước khi mở rộng release

Đội cần biết:

- Feature đã hoạt động đúng và đạt DoD chưa?
- Event cần theo dõi có được kiểm chứng, tuân thủ quyền riêng tư và không làm lộ dữ liệu?
- Có tiêu chí dừng, giám sát và cách khôi phục khi gặp lỗi?
- Cách nhận phản hồi người dùng đã rõ và tránh gây gián đoạn không cần thiết?
- Những mục tiêu và guardrail nào cần được xem trước khi tăng phạm vi?

## 19. Quyền riêng tư và đạo đức khi thu thập phản hồi

**Dữ liệu sử dụng và phỏng vấn thường liên quan con người**, nên yêu cầu tối thiểu là minh bạch mục đích, thu thập vừa đủ và bảo vệ quyền của người tham gia.

### Những nguyên tắc cần áp dụng theo chính sách và pháp luật liên quan

1. **Mục đích rõ:** Thu dữ liệu nào để trả lời câu hỏi sản phẩm nào?
2. **Tối thiểu hóa:** Không ghi tên học viên, email, nội dung bài, token hoặc dữ liệu nhạy cảm khi không cần.
3. **Cơ sở xử lý/consent phù hợp:** Tôn trọng lựa chọn người dùng và nghĩa vụ đã áp dụng; không vượt cơ chế kiểm soát.
4. **Hạn chế truy cập:** Người phân tích chỉ cần xem dữ liệu được cho phép, ưu tiên dữ liệu tổng hợp hoặc giả danh đúng mục đích.
5. **Giới hạn lưu giữ:** Có chính sách giữ, xóa, xuất hoặc rút lại dữ liệu theo nghĩa vụ áp dụng.
6. **Đảm bảo dữ liệu đúng mục đích:** Không sử dụng event học tập để giám sát người học hoặc nhân viên ngoài phạm vi đã công bố.
7. **Tôn trọng trong nghiên cứu:** Không ép người tham gia, bảo vệ danh tính và tránh đưa trích dẫn có thể nhận diện vào báo cáo mở.
8. **Nhận diện rủi ro nhóm nhỏ:** Phân khúc quá chi tiết có thể khiến một học viên bị nhận ra dù đã bỏ tên.

### Một event payload minh họa theo hướng tối thiểu

~~~json
{
  "event_name": "resume_open_succeeded",
  "event_id": "evt-example-007",
  "occurred_at": "2026-11-23T09:30:00Z",
  "analytics_subject_id": "pseudonymous-id",
  "device_class": "mobile",
  "app_version": "example-version"
}
~~~

Đây là **minh họa cấu trúc**, không phải hướng dẫn thu thập mọi trường trong mọi tình huống. Một ID giả danh vẫn **có thể là dữ liệu cá nhân** nếu liên kết ngược hoặc theo dõi được; phải bảo vệ và chỉ thu khi có căn cứ. Không bao giờ biến ví dụ này thành quy định cho phép bỏ qua consent hoặc cơ chế bảo mật.

### Điều gì cần tránh trong phỏng vấn?

- Chụp hoặc chia sẻ màn hình có thông tin học viên thật mà không có quyền và biện pháp bảo vệ phù hợp.
- Ghi lại chi tiết nhạy cảm không phục vụ câu hỏi nghiên cứu.
- Đưa một lời phàn nàn có khả năng nhận diện vào slide gửi rộng rãi.
- Gộp dữ liệu nghiên cứu với mục đích kỷ luật hoặc đánh giá cá nhân không được công bố.

## 20. Phân biệt dữ liệu sản phẩm với tín hiệu chất lượng và dòng công việc

Trong Agile, Kanban và XP, đội có thể dùng nhiều dữ liệu để cải tiến, nhưng cần biết **mỗi loại đo điều gì**.

| Dữ liệu | Giúp quyết định điều gì? | Không thể kết luận một mình |
| --- | --- | --- |
| **Product usage:** exposure, click, success, cohort | Có ai dùng và hoàn thành luồng không? | Vì sao họ dùng, hiệu quả học có tăng không |
| **Qualitative feedback:** quan sát, phỏng vấn, hỗ trợ | Họ gặp vấn đề gì, kỳ vọng gì, điều gì gây khó? | Bao nhiêu phần trăm dân số gặp giống vậy |
| **Flow metrics:** WIP, throughput, cycle time, work item age | Khả năng giao và chờ của đội thế nào? | Giá trị người dùng hoặc chất lượng sản phẩm |
| **Technical quality:** test, incident, error, latency | Phần mềm có đúng, an toàn và ổn định không? | Mọi nhu cầu người dùng đã được đáp ứng |
| **Business/outcome:** quay lại học, duy trì sử dụng, hoàn thành tác vụ | Kết quả dài hơn đang diễn biến ra sao? | Một thay đổi đơn lẻ là nguyên nhân nếu không có kiểm chứng |

Ví dụ, giảm **cycle time** có thể giúp đội kiểm tra giả thuyết sớm hơn. Nhưng chu kỳ giao nhanh không chứng minh **CTR hoặc task success** sẽ tăng, cũng không cho phép cắt bớt kiểm thử.

### Dữ liệu phải trở thành quyết định, không thành giám sát cá nhân

Một dashboard xếp hạng số PR hoặc số interview từng thành viên có thể khiến mọi người tối ưu số lượng thay vì học hỏi. Hãy đo **hệ thống tạo giá trị** và dùng kết quả để làm rõ trở ngại, không tìm người để đổ lỗi.

## 21. Tình huống hoàn chỉnh: hai vòng phát hành “Tiếp tục học”

### 21.1. Bối cảnh ban đầu

Một Scrum Team có Product Goal:

> “Học viên học liên tục giữa các thiết bị mà không mất tiến độ đã được xác nhận.”

Đội hoàn thành Increment đầu tiên cho chức năng **mở lại bài gần nhất**; các kiểm thử phân quyền và tiêu chuẩn DoD liên quan đã được xác nhận trong phạm vi release. Product Owner muốn biết **người dùng có tìm thấy và tin tưởng chức năng không** trước khi mở rộng khả năng đồng bộ video.

### 21.2. Kế hoạch học hỏi

| Câu hỏi | Bằng chứng định tính | Bằng chứng định lượng | Guardrail |
| --- | --- | --- | --- |
| Học viên có thấy nút không? | Quan sát tác vụ không hướng dẫn trên mobile/desktop | Exposure, CTR theo thiết bị và nhóm đủ điều kiện | Nút không cản thao tác khác, khả năng tiếp cận |
| Nhấn có mở được bài đúng không? | Quan sát lỗi, phỏng vấn người thất bại | Success after click, error rate, thời gian đến bài | Quyền truy cập và dữ liệu đúng tài khoản |
| Người dùng có hiểu trạng thái lưu? | Hỏi kỳ vọng, quan sát thử lại khi mạng lỗi | Tỷ lệ thao tác lặp, lỗi lưu, trạng thái chưa xác nhận | Không thông báo lưu thành công giả |
| Tính năng có giúp tiếp tục học? | Phỏng vấn sau tác vụ, nhật ký học | Cohort quay lại học và thời gian tìm bài | Không tăng sự cố, hỗ trợ hoặc crash nghiêm trọng |

### 21.3. Kết quả vòng 1 giả định

Trong một tuần, funnel của **1.000 học viên đủ điều kiện đã thấy nút**:

- 260 học viên nhấn (26%).
- 208 mở bài đúng được ghi nhận (80% trong nhóm nhấn).
- Nhóm mobile có CTR 20%, desktop 37,1%.
- Ở một số phiên quan sát, học viên mobile cuộn qua nút mà không nhận ra.
- Một vài người nhấn nhiều lần do không thấy tín hiệu đang tải.

Các số liệu là **giả định cho bài học**, chưa xác định tác động thống kê hay nguyên nhân. Đội còn cần kiểm tra:

1. Event exposure có thật sự phát khi nút nhìn thấy hay chỉ khi component render?
2. Có mất event success trên mạng yếu hoặc client cũ không?
3. Hai nhóm thiết bị có cùng loại học viên và mức nhu cầu tương tự không?
4. Có lỗi API/latency riêng ở mobile không?
5. Buổi quan sát có đang tuyển quá nhiều người mới không?

### 21.4. Tổng hợp và quyết định

Đội tạo giả thuyết:

> “Khả năng tìm thấy entry point và tín hiệu phản hồi sau click trên mobile có thể đang tạo ma sát.”

Họ **không** vội xây AI gợi ý bài vì một người đề nghị. Product Owner ưu tiên hai việc nhỏ:

- Thử một vị trí nút rõ hơn với cùng hành vi nghiệp vụ, kiểm tra accessibility.
- Bổ sung trạng thái tải dễ hiểu, đảm bảo không phát sinh click/ghi dữ liệu trùng nguy hiểm.

Developers đảm bảo mỗi thay đổi đạt DoD; đội sử dụng test, CI và điều kiện release phù hợp.

### 21.5. Vòng 2 giả định

Sau bản cập nhật, đội thấy tỷ lệ thành công từ exposure trên mobile tăng ở giai đoạn được quan sát. Tuy nhiên, cùng kỳ hệ thống cũng sửa lỗi tracking và chiến dịch nhắc học bắt đầu.

**Kết luận có trách nhiệm:**

> “Có tín hiệu tích cực về việc người dùng mobile hoàn thành hành trình, và quan sát tác vụ mới cho thấy họ dễ tìm nút hơn. Vì instrumentation cùng thời kỳ có thay đổi, chúng ta chưa gán toàn bộ chênh lệch chỉ số cho vị trí nút. Cần tiếp tục kiểm chứng trên cohort và cửa sổ đo nhất quán, đồng thời theo dõi lỗi phân quyền và tiến độ.”

### 21.6. Học hỏi từ một phản hồi trái chiều

Một học viên cho biết: “Nút tốt nhưng mở sai vị trí video.” Đây có thể là **nhu cầu đồng bộ vị trí** khác với mở đúng bài. Đội:

1. Ghi lại ngữ cảnh và tần suất sử dụng video trong mẫu.
2. Xem sự kiện và hành vi liên quan loại nội dung, theo phạm vi được phép.
3. Làm rõ cách định nghĩa “tiếp tục” với Product Owner và người học.
4. Thử một lát cắt video có phạm vi rõ nếu bằng chứng và giá trị ủng hộ.
5. Không tự gọi chức năng ban đầu thất bại toàn bộ nếu nó đã đạt đúng phạm vi đã cam kết.

Phản hồi mới là **đầu vào cho Product Backlog**, không tự động thành nhiệm vụ chen vào Sprint đang có.

## 22. Đưa bằng chứng vào các vòng phản hồi Agile

### Sprint Review

Sprint Review là cơ hội Scrum Team và các bên liên quan **kiểm tra kết quả Sprint và điều chỉnh hướng tiếp theo**. Một phiên Review hữu ích có thể trình bày:

1. **Sprint Goal**, Increment đã đạt DoD và giới hạn những gì được giao.
2. Tình trạng release: đã phát hành cho ai, chưa phát hành gì và vì sao.
3. **Dữ liệu sử dụng** với đúng mẫu số, kỳ đo, phân khúc và hạn chế tracking.
4. **Phản hồi định tính** có ngữ cảnh, cả ý kiến trái chiều hoặc vấn đề nghiêm trọng.
5. Những rủi ro chất lượng và bất định còn lại.
6. Các lựa chọn Product Backlog cần được ưu tiên hoặc kiểm chứng tiếp.

Review không chỉ là buổi báo cáo KPI hoặc phê duyệt demo. **Product Backlog có thể được điều chỉnh dựa trên điều học được**.

### Refinement và Sprint Planning

- Dữ liệu được dùng để làm rõ **vấn đề**, không chỉ liệt kê tính năng được yêu cầu.
- Phản hồi định tính cung cấp **ví dụ, trường hợp biên và tiêu chí chấp nhận**.
- Developers xem năng lực, phụ thuộc, DoD và rủi ro instrumentation.
- Scrum Team xác định **một Sprint Goal có giá trị** và chọn các hạng mục có thể tạo Increment dùng được.

### Sprint Retrospective

Nếu đội thu nhiều dữ liệu nhưng quyết định chậm hoặc không tin tưởng dashboard, Retrospective có thể xem:

- Event thiếu nghĩa hoặc tracking sai từ khi nào?
- Phản hồi người dùng có đến được đúng người quyết định không?
- Có quá nhiều cuộc họp mà không thay đổi Product Backlog?
- Có thể rút ngắn thời gian từ phát hiện → giả thuyết → thử nghiệm → học hỏi không?
- Chất lượng hay quyền riêng tư có bị đánh đổi để có số liệu nhanh?

### Kanban và luồng liên tục

Một đội quản lý yêu cầu liên tục vẫn có thể tổ chức vòng phản hồi phù hợp: bổ sung việc theo nhu cầu, theo dõi WIP và cycle time, xem dữ liệu sản phẩm, thử thay đổi nhỏ. Không cần tạo Sprint giả nếu bối cảnh vận hành không phù hợp; vẫn cần **mục tiêu, trách nhiệm và kiểm soát chất lượng**.

## 23. Các sai lầm phổ biến

| Sai lầm | Hệ quả | Cách cải thiện |
| --- | --- | --- |
| **Chỉ nghe người phản hồi to nhất** | Mẫu bị lệch; ưu tiên sai nhu cầu | Chủ động tuyển nhóm không gửi phản hồi và xem dữ liệu sử dụng |
| **Chỉ xem CTR hoặc số click** | Có thể tối ưu hành vi nhấn lặp, không phải thành công | Đo task success, lỗi và outcome liên quan |
| **Biến lời nói của 5 người thành tỷ lệ toàn dân số** | Suy rộng sai | Trình bày phạm vi nghiên cứu, dùng định tính để nêu giả thuyết |
| **Dùng tổng số mà không có mẫu số** | Không thể đánh giá chuyển đổi | Định nghĩa eligible, exposed, click, success theo cùng cohort |
| **Trộn người dùng, phiên và lượt thao tác** | Tỷ lệ sai hoặc so sánh không nhất quán | Chọn đơn vị phân tích và cách loại trùng rõ |
| **Không kiểm tra event instrumentation** | Dashboard đẹp nhưng không phản ánh hành vi | Test sự kiện, schema, client/server, version và missing data |
| **Gọi tương quan là nguyên nhân** | Đầu tư sai giải pháp | Xét confounders, cohort, thí nghiệm khi phù hợp |
| **Bỏ qua người không dùng tính năng** | Chỉ học từ người đã thành công | Nghiên cứu non-users và drop-off theo chính sách |
| **Phân khúc đến nhóm quá nhỏ** | Dao động mạnh và nguy cơ nhận diện lại | Hạn chế phân khúc, bảo vệ riêng tư, nêu mức mẫu |
| **Sửa sản phẩm và event cùng lúc rồi so trực tiếp trước/sau** | Không biết phần chênh lệch đến từ đâu | Ghi release, thay đổi schema, kiểm tra baseline và phép đo |
| **Thu thập mọi dữ liệu có thể** | Tăng rủi ro riêng tư, chi phí và nhiễu | Chỉ thu dữ liệu phục vụ quyết định có căn cứ |
| **Phỏng vấn bằng câu hỏi dẫn dắt** | Người dùng chiều ý nhóm nghiên cứu | Dùng tác vụ thực, câu hỏi trung lập và quan sát |
| **Bỏ qua lỗi nghiêm trọng vì KPI tăng** | Gây hại về dữ liệu và niềm tin | Guardrail chất lượng, xử lý sự cố và DoD bắt buộc |
| **Coi Sprint Review là cổng phát hành** | Trì hoãn phản hồi không cần thiết | Giao Increment đạt DoD khi điều kiện release phù hợp |
| **Coi release là bằng chứng đạt outcome** | Tuyên bố giá trị chưa được kiểm chứng | Theo dõi sử dụng, tác vụ và kết quả trong kỳ thích hợp |
| **Thử A/B nhưng không xác định trước metric và nhóm** | Dễ chọn kết quả đẹp sau khi nhìn dữ liệu | Ghi kế hoạch, assignment, metric và guardrail trước |
| **Chạy thí nghiệm dù một biến thể có rủi ro an toàn** | Có thể cố ý gây hại | Chỉ thử phương án đáp ứng điều kiện chất lượng và nghĩa vụ |
| **Có dashboard nhưng không quyết định** | Tốn chi phí đo mà không học được gì | Gắn mỗi phân tích với câu hỏi, người quyết định và hành động |

## 24. Quy trình thực hành từ phát hiện đến quyết định

Một đội có thể dùng chu trình sau mà không cần tạo thêm nhiều thủ tục:

### Bước 1 — Xác định quyết định cần hỗ trợ

Ví dụ: “Có nên ưu tiên cải thiện vị trí nút ‘Tiếp tục học’ trên mobile hơn đồng bộ vị trí video ngay lúc này không?”

### Bước 2 — Ghi điều đang biết và chưa biết

Nêu Product Goal, giá trị mong muốn, phản hồi đã có, các sự kiện đã ghi, rủi ro và giả định. **Phân biệt quan sát với cách giải thích**.

### Bước 3 — Chọn hai nguồn bằng chứng bổ sung

Ví dụ dữ liệu funnel theo thiết bị và usability test không hướng dẫn với người dùng mobile; thêm kiểm tra kỹ thuật về exposure tracking nếu dashboard đáng nghi.

### Bước 4 — Kiểm tra chất lượng và tính hợp pháp của dữ liệu

Định nghĩa mẫu số, thời gian, event, consent/cơ sở xử lý, định danh, nhóm không có dữ liệu. Không phân tích một số liệu sai chỉ vì dashboard có sẵn.

### Bước 5 — Tổng hợp insight và mức chắc chắn

Viết một câu mô tả **đã thấy gì**, một câu **có thể do đâu**, và câu **còn cần kiểm chứng gì**.

### Bước 6 — Chọn can thiệp nhỏ, an toàn

Sửa lỗi nghiêm trọng khi có bằng chứng, hoặc thử thiết kế mới trong phạm vi phù hợp, bảo vệ DoD và guardrail.

### Bước 7 — Đo và quan sát sau thay đổi

Theo dõi task success, sự cố, phản hồi người dùng và những yếu tố khác cùng thay đổi. Không khẳng định nhân quả vượt mức bằng chứng.

### Bước 8 — Quyết định và cập nhật backlog

Giữ, mở rộng, điều chỉnh, quay lại hoặc nghiên cứu tiếp. Ghi người chịu trách nhiệm và mốc kiểm tra lại. Kết quả cần đi vào **Product Backlog/roadmap theo giá trị**, không nằm mãi ở một slide.

## 25. Mẫu phiếu tổng hợp bằng chứng

~~~text
VẤN ĐỀ / CÂU HỎI QUYẾT ĐỊNH:
  Ai đang gặp vấn đề nào? Quyết định sản phẩm cần làm là gì?

GIẢ THUYẾT:
  Thay đổi nào được kỳ vọng tạo kết quả gì, vì sao?

ĐỊNH TÍNH:
  Nguồn và cách tuyển người:
  Quan sát trực tiếp:
  Trích dẫn đã xử lý riêng tư:
  Những trường hợp trái chiều:
  Giới hạn của mẫu:

ĐỊNH LƯỢNG:
  Event và định nghĩa:
  Đối tượng / mẫu số / thời gian / cohort:
  Kết quả và phân bố theo nhóm:
  Kiểm tra chất lượng dữ liệu:
  Những confounders / điều chưa biết:

AN TOÀN VÀ CHẤT LƯỢNG:
  Definition of Done và điều kiện release:
  Guardrail chất lượng, riêng tư, dữ liệu:
  Rủi ro còn lại và người có thẩm quyền:

KẾT LUẬN:
  Điều quan sát được:
  Giả thuyết được hỗ trợ đến mức nào:
  Điều chưa thể kết luận:
  Hành động / thí nghiệm tiếp theo:
  Người quyết định / mốc xem lại:
~~~

Mẫu này là **công cụ tư duy**, không bắt buộc tạo file riêng cho mọi thay đổi. Thông tin có thể nằm trong một user story, kết quả nghiên cứu, dashboard đã được kiểm chứng hoặc biên bản quyết định ngắn.

## 26. Bài tập thực hành

### Bài tập 1 — Phân loại nguồn bằng chứng

Đội có những thông tin:

1. Sáu học viên trong buổi thử nói nút khó tìm.
2. Dashboard cho thấy 260 trong 1.000 học viên đã thấy nút có nhấn.
3. Integration test phát hiện API có thể trả dữ liệu của tài khoản khác.
4. 30 ticket hỗ trợ tháng này liên quan “Tiếp tục học”.
5. Một học viên được quan sát nhấn ba lần khi loading.
6. Một cohort có tỷ lệ quay lại học sau bảy ngày cao hơn cohort trước.

**Yêu cầu:** Phân loại định tính, định lượng, chất lượng kỹ thuật và outcome; giải thích điều gì chưa thể kết luận từ từng nguồn.

**Gợi ý:** Test phân quyền là bằng chứng lỗi kỹ thuật; 30 ticket không là 30 người dùng duy nhất nếu một người gửi nhiều lần.

### Bài tập 2 — Thiết kế phỏng vấn trung lập

Product Owner hỏi: “Tại sao học viên không thích nút mới?”

**Yêu cầu:** Viết lại thành ít nhất năm câu hỏi không dẫn dắt và một tác vụ quan sát thực tế; nêu nhóm người dùng cần tuyển để tránh chỉ nghe từ người đang dùng thường xuyên.

**Gợi ý:** Hỏi lần gần nhất họ cần tìm lại bài và quan sát cách họ thực hiện trước khi giới thiệu giải pháp.

### Bài tập 3 — Tính funnel đúng mẫu số

Một tuần có **1.000 học viên duy nhất đã thấy nút**, **260 người nhấn**, **208 người mở đúng bài**. Trong đó mobile: 650 thấy, 130 nhấn, 91 thành công; desktop: 350 thấy, 130 nhấn, 117 thành công.

**Yêu cầu:** Tính CTR tổng, thành công sau click tổng, thành công từ exposure tổng, CTR mobile/desktop và thành công sau click từng nhóm. Đề xuất hai giả thuyết cần kiểm chứng.

**Gợi ý:** Tổng lần lượt **26%, 80%, 20,8%**; mobile **20% CTR, 70% sau click**; desktop **xấp xỉ 37,1% CTR, 90% sau click**. Các tỷ lệ chưa chứng minh thiết bị là nguyên nhân.

### Bài tập 4 — Tìm lỗi trong thiết kế event

Một developer gửi **resume_open_succeeded** khi nút được nhấn, **resume_entry_visible** khi component render ngoài màn hình và gửi mỗi click hai lần nếu mạng yếu.

**Yêu cầu:** Nêu các sai lệch dashboard có thể xuất hiện, thiết kế lại thời điểm kích hoạt của ba event và chọn test instrumentation trước khi release.

**Gợi ý:** Success phải có định nghĩa kết quả, exposure phải là được thấy theo quy tắc đo, retry không tạo ý định mới.

### Bài tập 5 — Đọc hai nguồn mâu thuẫn

Tám người tham gia usability test đánh giá chức năng dễ hiểu, nhưng dữ liệu thật cho thấy tỷ lệ chuyển đổi từ exposure thấp và tỷ lệ lỗi trên mobile cao.

**Yêu cầu:** Nêu bốn nguyên nhân giả định (gồm ít nhất một vấn đề tuyển mẫu và một vấn đề tracking), cùng kế hoạch thu bằng chứng để kiểm chứng từng nguyên nhân.

**Gợi ý:** Không chọn nguồn mình thích; kiểm tra bối cảnh, mẫu số, thứ tự sự kiện và khác biệt thiết bị.

### Bài tập 6 — Phân biệt retention và click

Một đội tuyên bố: “Tăng số click ‘Tiếp tục học’ chứng minh tỷ lệ duy trì học viên tăng.”

**Yêu cầu:** Giải thích điểm sai và thiết kế một cohort metric về **quay lại thực sự học sau bảy ngày**, gồm nhóm vào cohort, hành vi đủ điều kiện, cửa sổ quan sát, ngoại lệ và ít nhất hai yếu tố gây nhiễu.

**Gợi ý:** Người dùng có thể click nhiều mà không quay lại học; cohort phải đủ thời gian để quan sát.

### Bài tập 7 — Ưu tiên giữa hai insight

Insight A: Có phản hồi rằng nút hơi khó tìm, không có lỗi nghiêm trọng đã biết. Insight B: Một test xác nhận có thể đọc sai tiến độ khi đổi tài khoản trên cùng thiết bị.

**Yêu cầu:** Xác định thứ tự hành động, giải thích vai trò của risk guardrail, DoD và người có quyền quyết định, không dùng CTR để che lỗi dữ liệu.

### Bài tập 8 — Lập kế hoạch A/B test

Đội muốn so sánh vị trí nút hiện tại và vị trí dễ thấy hơn. **Yêu cầu:** Xác định giả thuyết, cohort đủ điều kiện, randomization unit, primary metric, hai guardrail, yêu cầu dữ liệu, thời gian xem kết quả và điều kiện dừng an toàn.

**Gợi ý:** Không đổi đồng thời tracking và logic chọn bài; cần đánh giá khả năng tiếp cận ở cả hai biến thể.

### Bài tập 9 — Viết một cập nhật Sprint Review

Increment đã đạt DoD và được phát hành cho một nhóm học viên. Có 1.000 exposure, 260 click và 208 success; nhóm quan sát nhỏ nêu vấn đề về vị trí mobile; cohort quay lại học chưa đủ kỳ theo dõi.

**Yêu cầu:** Viết cập nhật khoảng 150–200 từ, phân biệt **đã giao**, **đã quan sát**, **đã hiểu**, **chưa thể kết luận** và **hành động tiếp theo**.

### Bài tập 10 — Bảo vệ quyền riêng tư

Đội muốn gắn email, tên khóa học, toàn bộ nội dung lỗi và mã phiên vào mọi event để phân tích sâu hơn.

**Yêu cầu:** Đặt câu hỏi về mục đích, tối thiểu hóa dữ liệu, cơ sở xử lý, quyền truy cập, thời gian lưu, dữ liệu có thể nhận diện và phương án thay thế bằng dữ liệu tổng hợp hoặc giả danh có kiểm soát.

### Bài tập 11 — Đánh giá before/after có nhiễu

Sau release, tỷ lệ người mở bài từ nút tăng. Cùng tuần, đội sửa instrumentation và tổ chức gửi thông báo nhắc học cho học viên.

**Yêu cầu:** Viết đoạn kết luận có trách nhiệm, nêu vì sao chưa thể quy nhân quả cho release, cách tách cohort và quyết định nghiên cứu tiếp.

### Bài tập 12 — Thiết kế vòng phản hồi của đội

Một đội phát triển tính năng theo Sprint nhưng cũng xử lý lỗi hỗ trợ liên tục. **Yêu cầu:** Thiết kế nhịp quan sát dữ liệu sử dụng, tổng hợp feedback định tính, xử lý lỗi khẩn, Sprint Review và Retrospective. Xác định người quyết định và nơi lưu bằng chứng để không thêm cuộc họp vô ích.

## 27. Checklist trước khi quyết định dựa trên phản hồi

- [ ] Đã mô tả **vấn đề người dùng và quyết định cần hỗ trợ**, không chỉ chọn chỉ số có sẵn?
- [ ] Product Goal hoặc mục tiêu dịch vụ và outcome mong muốn rõ?
- [ ] Đã phân biệt dữ liệu về **output, exposure, tương tác, hoàn thành tác vụ, outcome và guardrail**?
- [ ] Phản hồi định tính có nguồn, bối cảnh, cách tuyển người và giới hạn mẫu?
- [ ] Câu hỏi nghiên cứu có trung lập, có quan sát hành vi thay vì chỉ hỏi ý kiến?
- [ ] Những người không dùng hoặc thất bại giữa luồng có được cân nhắc?
- [ ] Event có ý nghĩa rõ, trigger đúng và schema được quản lý?
- [ ] Mẫu số, đơn vị đếm, cửa sổ đo và điều kiện đủ tư cách được thống nhất?
- [ ] Đã xem mất event, event trùng, version, thiết bị và định danh theo quyền phân tích?
- [ ] Funnel có cùng cohort, đúng thứ tự và cùng phạm vi thời gian?
- [ ] Phân khúc có mục đích, đủ dữ liệu và không làm tăng nguy cơ tái nhận diện?
- [ ] Đã đối chiếu quan sát định tính với sử dụng và kiểm tra kỹ thuật?
- [ ] Mâu thuẫn giữa nguồn được điều tra, không bị bỏ vì trái kỳ vọng?
- [ ] Phát biểu nguyên nhân có đúng mức bằng chứng, không biến tương quan thành nhân quả?
- [ ] Những biến động cùng thời gian như chiến dịch, sửa tracking và thay đổi người dùng đã được ghi?
- [ ] Có guardrail về **quyền truy cập, dữ liệu, lỗi, hiệu năng, khả năng tiếp cận** phù hợp?
- [ ] Increment chỉ được gọi Done khi **Definition of Done** đáp ứng?
- [ ] Release có điều kiện an toàn, giám sát và phương án ứng phó?
- [ ] Thu thập, lưu giữ và sử dụng dữ liệu phù hợp mục đích, cơ sở xử lý và quyền riêng tư?
- [ ] Phản hồi được chuyển thành **giả thuyết, thử nghiệm hoặc quyết định backlog** cụ thể?
- [ ] Có người có thẩm quyền và thời điểm xem lại kết quả?
- [ ] Có đánh giá **tác động thực tế** chứ không chỉ dashboard trông đẹp?

Checklist để hỗ trợ **học hỏi có trách nhiệm**, không phải bắt buộc mọi story tạo thêm một bộ báo cáo. Đội nhỏ có thể bắt đầu với ít tín hiệu quan trọng, nhưng phải đủ để ra quyết định an toàn và tránh tự lừa mình bằng số liệu.

## 28. Tổng kết

- **Phản hồi định tính** giúp khám phá trải nghiệm, động cơ và cơ chế có thể gây ra vấn đề; **dữ liệu sử dụng** cho thấy phạm vi, phân bố và xu hướng hành vi đã ghi nhận. Cả hai đều có thiên lệch và giới hạn.
- **Bắt đầu từ Product Goal, nhu cầu và giả thuyết**, rồi mới chọn câu hỏi phỏng vấn, event tracking và chỉ số. Không tối ưu click nếu điều người dùng cần là mở đúng bài hoặc học liên tục.
- **Funnel phải có mẫu số và định nghĩa rõ**; cohort và segmentation giúp thấy khác biệt, nhưng không tự chứng minh nguyên nhân. Kiểm tra instrumentation trước khi tin biểu đồ.
- **Tam giác hóa bằng chứng**: đối chiếu quan sát, dữ liệu sử dụng và kiểm tra kỹ thuật; khi mâu thuẫn, điều tra mẫu, bối cảnh, mất dữ liệu và những thay đổi đồng thời.
- **Thử nghiệm phải có giả thuyết, chỉ số chính, guardrail và giới hạn kết luận**. Không cố ý gây hại hoặc bỏ bảo vệ dữ liệu để đổi lấy thống kê.
- **Increment, release và outcome là ba trạng thái khác nhau**. Scrum có thể giao Increment đạt DoD trước Sprint Review; giá trị thực cần được quan sát và học hỏi sau phát hành.
- **Quyền riêng tư là điều kiện của phép đo đáng tin**, không phải việc phụ. Thu đủ cho câu hỏi, quản lý truy cập, lưu giữ và trách nhiệm sử dụng.
- **Dữ liệu chỉ có giá trị khi thay đổi quyết định**: sửa lỗi, điều chỉnh Product Backlog, thử nghiệm, mở rộng hoặc dừng một hướng không hiệu quả.

Khi một người nói **“Chức năng này được dùng nhiều nên chắc chắn đã thành công”**, hãy hỏi: **“Ai đang dùng, họ hoàn thành việc gì, có nhóm nào gặp khó, họ kể điều gì về trải nghiệm và bằng chứng nào đủ để quyết định bước tiếp theo?”**
