# Nhận diện điều kiện khi có thể giảm nhu cầu ước lượng từng hạng mục

Trong một nhóm phát triển phần mềm, việc ước lượng từng user story có thể chiếm đáng kể thời gian: cả nhóm thảo luận một hạng mục là 3 hay 5 story point, tranh luận các rủi ro chưa đủ dữ liệu rồi lặp lại quá trình với hàng chục hạng mục khác. Nếu những cuộc thảo luận đó giúp phát hiện hiểu lầm, phụ thuộc hoặc rủi ro lớn, chúng rất có giá trị. Nhưng nếu hạng mục đã được chia nhỏ, tương đối đồng đều, nhóm có lịch sử hoàn thành đáng tin và việc gắn điểm số không làm thay đổi quyết định, **ước lượng từng hạng mục có thể mang lại ít thông tin mới so với chi phí bỏ ra**.

Tư duy **Agile** không yêu cầu nhóm phải ước lượng mọi đầu việc bằng giờ hoặc story point. Điều quan trọng hơn là chọn việc tạo giá trị, giao phần mềm tăng dần, nhận phản hồi và đưa ra **dự báo có mức bất định phù hợp**. Khi đủ điều kiện, nhóm có thể dựa nhiều hơn vào **throughput, cycle time, Work In Progress (WIP), việc chia nhỏ công việc và dữ liệu quan sát** thay vì cố gán một con số độ lớn cho từng hạng mục.

Tuy nhiên, **giảm nhu cầu ước lượng không có nghĩa bỏ lập kế hoạch, bỏ phân tích hoặc hứa ngày giao thiếu căn cứ**. Với những việc mới, rủi ro cao, kích thước quá khác nhau hoặc có nghĩa vụ cố định, ước lượng có mục tiêu vẫn cần thiết.

Bài học thuộc chương **Ước lượng và dự báo** của module **AGILE_DEVELOPMENT**, nơi người học kết nối user story, backlog, Scrum, Kanban, XP và đo lường dòng công việc để phối hợp phát triển thích ứng. Mục tiêu là biết **nhận diện điều kiện cho phép giảm hoạt động ước lượng từng hạng mục, lựa chọn phương pháp thay thế và nhận ra lúc nào không nên áp dụng**.

## 1. Phân biệt ước lượng, dự báo và cam kết

Ba khái niệm này liên quan nhưng không giống nhau.

| Khái niệm | Câu hỏi chính | Đầu ra thường gặp | Điều cần tránh |
| --- | --- | --- | --- |
| **Ước lượng hạng mục** (*item estimation*) | Một việc có độ lớn, độ phức tạp hoặc công sức dự kiến như thế nào? | Giờ/ngày, khoảng công sức, story point, cỡ tương đối | Coi một con số là thời gian chính xác chắc chắn |
| **Dự báo** (*forecasting*) | Với dữ liệu và điều kiện hiện tại, khi nào hoặc bao nhiêu việc có khả năng hoàn thành? | Kịch bản, khoảng thời gian, dự báo theo xác suất khi có cơ sở | Gắn phần trăm tin cậy cho phỏng đoán không có phương pháp |
| **Cam kết** (*commitment*) | Nhóm hoặc tổ chức chịu trách nhiệm đạt điều gì, với phạm vi và điều kiện nào? | Product Goal, Sprint Goal, mốc giao hàng hoặc nghĩa vụ cụ thể | Đồng nhất mọi dự báo với lời hứa không thể thay đổi |
| **Lập kế hoạch** (*planning*) | Việc gì nên làm, bằng cách nào, với năng lực, rủi ro và phụ thuộc nào? | Thứ tự backlog, lát cắt giá trị, phương án phối hợp, thời điểm xem lại | Biến một bản danh sách ước lượng thành toàn bộ kế hoạch |

Giả sử nhóm có 18 Product Backlog Item đang cần hoàn thành. **Ước lượng từng item** có thể là gán 2, 3 hoặc 5 điểm cho từng việc. Một cách **dự báo khác** là dùng số hạng mục thực tế đã hoàn tất mỗi tuần, nếu các hạng mục đủ tương đồng và bối cảnh ổn định. Hai cách có thể hỗ trợ cùng một quyết định, nhưng không nhất thiết phải áp dụng đồng thời.

Giảm ước lượng có nghĩa **chỉ chi công sức ước lượng khi thông tin tạo ra giúp quyết định tốt hơn**. Nhóm vẫn phải hiểu hạng mục, kiểm chứng khả thi, giữ chất lượng và công khai giới hạn của dự báo.

## 2. Khi nào hoạt động ước lượng từng hạng mục tạo giá trị?

Trước khi quyết định bỏ hoặc giảm, cần hiểu tại sao nhóm từng dùng ước lượng. Nó có thể phục vụ nhiều mục đích khác nhau:

1. **Làm rõ công việc:** Khi cả nhóm thảo luận lý do một story được xem là lớn, họ có thể phát hiện các quy tắc nghiệp vụ bị hiểu khác nhau.
2. **Phát hiện rủi ro và phụ thuộc:** Một phần việc tích hợp chưa có API hoặc dữ liệu có thể phức tạp hơn tưởng tượng.
3. **So sánh phương án đầu tư:** Nếu hai lựa chọn tạo giá trị tương đương nhưng một lựa chọn tốn nhiều nguồn lực hơn đáng kể, thông tin độ lớn có ích.
4. **Điều phối năng lực hoặc chuyên môn khan hiếm:** Việc cần một chuyên gia duy nhất, một môi trường thử nghiệm đặc biệt hoặc sự tham gia của đối tác cần được nhìn thấy sớm.
5. **Đánh giá một cam kết có điều kiện:** Hợp đồng, ngân sách, mốc pháp lý hoặc kế hoạch vận hành có thể yêu cầu phân tích quy mô công việc và rủi ro.
6. **Hỗ trợ dự báo khi thiếu dữ liệu hoàn tất:** Đội mới hoặc loại công việc hoàn toàn mới chưa có lịch sử dòng chảy đủ đại diện.

Ngược lại, nếu nhóm cùng hiểu một story nhỏ, có tiêu chí chấp nhận rõ, không có rủi ro đặc biệt và thường hoàn thành các việc như vậy trong một khoảng tương đối ổn định, cuộc tranh luận “2 hay 3 điểm” có thể không còn giúp thay đổi ưu tiên, phạm vi hoặc dự báo.

### Câu hỏi quyết định nên ước lượng hay không

> **Nếu biết hạng mục này là 3 thay vì 5 điểm, chúng ta sẽ thay đổi quyết định gì?**

Nếu câu trả lời là **“không thay đổi gì”**, hãy cân nhắc giảm hoặc bỏ bước gán điểm riêng cho hạng mục. Nếu sự khác biệt đó làm thay đổi phạm vi Sprint, thứ tự backlog, chi phí đầu tư hoặc mức rủi ro được chấp nhận, hãy giữ một hình thức làm rõ hoặc ước lượng thích hợp.

## 3. Những điều kiện hỗ trợ giảm ước lượng từng hạng mục

Không có một ngưỡng tuyệt đối kiểu “nhóm có 20 story thì được bỏ estimation”. Quyết định cần dựa trên **tập điều kiện được quan sát trong công việc thực tế**.

| Điều kiện | Dấu hiệu có thể kiểm chứng | Vì sao hữu ích |
| --- | --- | --- |
| **Hạng mục được chia tương đối nhỏ** | Phần lớn hạng mục đi qua luồng làm việc trong thời gian không quá chênh lệch; ít việc tồn quá lâu | Đếm số item trở nên có ý nghĩa hơn khi mỗi item không khác biệt hàng chục lần về độ lớn |
| **Độ biến thiên kích thước được kiểm soát** | Công việc quá lớn hoặc khác thường được nhận diện để chia nhỏ hoặc xử lý riêng | Hạn chế một số ít item rất lớn làm sai dự báo theo số lượng |
| **Định nghĩa hoàn thành nhất quán** | Có chính sách Done hoặc Definition of Done rõ; công việc đã hoàn tất được tích hợp, kiểm thử tương ứng | Dữ liệu throughput phản ánh công việc thực sự có thể bàn giao, không chỉ mã đã viết |
| **Có lịch sử dữ liệu phù hợp** | Các tuần/Sprint gần đây có throughput, cycle time và WIP được ghi với mốc đo ổn định | Dự báo có căn cứ thực nghiệm thay vì chỉ dựa vào cảm giác |
| **Bối cảnh tương đối ổn định** | Năng lực, loại việc, quy trình, mức độ phụ thuộc không biến đổi quá lớn so với giai đoạn dữ liệu | Quá khứ có thể cung cấp thông tin hữu ích hơn cho tương lai |
| **Quy trình và điểm chờ minh bạch** | Bảng công việc cho thấy hạng mục đang ở đâu; có chính sách rõ khi kéo việc, kiểm thử và hoàn tất | Nhóm có thể cải thiện dòng chảy thay vì chỉ tinh chỉnh ước lượng |
| **Ưu tiên và mục tiêu sản phẩm rõ** | Product Backlog được sắp thứ tự theo giá trị/rủi ro; nhóm biết mục tiêu cần đạt | Không phụ thuộc vào điểm ước lượng để quyết định điều gì quan trọng |
| **Có cơ chế xem lại dự báo** | Nhóm định kỳ so sánh dự báo với kết quả, ghi lý do sai lệch, cập nhật cách làm | Giảm estimation không dẫn tới lập kế hoạch mù |
| **Người liên quan hiểu độ bất định** | Báo cáo gồm giả định, kịch bản, yếu tố có thể thay đổi kết quả | Tránh hiểu số đếm công việc thành ngày giao chắc chắn |

**Thiếu một điều kiện không có nghĩa phải quay về ước lượng tất cả.** Nhóm có thể giữ cách đếm cho một nhóm công việc nhỏ, đồng thời ước lượng riêng các hạng mục không tương đồng hoặc rủi ro cao.

### 3.1. Vì sao kích thước hạng mục là điều kiện quan trọng nhất?

Nếu một backlog gồm mười việc sửa nhãn nút và một việc thay toàn bộ cơ chế đăng nhập, **đếm 11 việc** khó phản ánh khối lượng thực tế. Một việc có thể mất vài giờ, việc khác kéo dài nhiều tuần. Dự báo chỉ dựa vào throughput trung bình sẽ dễ sai.

Khi hạng mục được **chia theo lát cắt giá trị nhỏ và đủ hoàn chỉnh**, kích thước thường dễ kiểm soát hơn. Chẳng hạn, thay vì một item “Hoàn thiện toàn bộ quy trình workshop”, nhóm có thể có các lát cắt:

- Học viên xem danh sách workshop còn chỗ.
- Học viên đăng ký một chỗ hợp lệ và nhận trạng thái xác nhận.
- Học viên xem các đăng ký của mình.
- Học viên tự hủy theo chính sách và số chỗ được cập nhật đúng.
- Nhân viên có quyền xem trạng thái đăng ký để hỗ trợ.

Mỗi lát cắt đi qua các tầng kỹ thuật cần thiết và phải đạt tiêu chuẩn chất lượng. **Không nên chia giả thành 10 item “thiết kế giao diện”, “viết controller”, “viết repository”** chỉ để nâng throughput: chúng chưa phải những phần giá trị hoàn chỉnh mà người dùng đánh giá được.

### 3.2. “Đủ đồng đều” không có nghĩa tất cả hạng mục phải bằng nhau

Nhóm không cần đo từng việc bằng một độ lớn chính xác để chứng minh chúng hoàn toàn đồng nhất. Thay vào đó, hãy kiểm tra thực tế:

- Có thường xuyên xuất hiện hạng mục kéo dài hơn hẳn phần còn lại không?
- Việc không hoàn tất có thường bị chuyển từ chu kỳ này sang chu kỳ khác không?
- Kích thước thay đổi có đi cùng loại công việc đặc biệt (tích hợp, bảo mật, thay schema, dịch vụ ngoài) không?
- Nếu chia nhỏ các item quá lớn, dự báo theo số lượng có trở nên ổn định hơn không?

Khi đuôi phân phối rất dài, nhóm có thể dùng **phân nhóm loại việc**, cải thiện slicing hoặc ước lượng mục tiêu cho ngoại lệ thay vì kết luận rằng không thể giảm bất kỳ hoạt động ước lượng nào.

## 4. Cần đo đúng những gì trước khi giảm estimation?

Để dự báo từ dòng công việc, phải thống nhất các khái niệm và mốc đo.

| Chỉ số | Mô tả | Giá trị khi không ước lượng từng item |
| --- | --- | --- |
| **Throughput** | Số work item hoàn tất theo định nghĩa Done trong mỗi đơn vị thời gian | Cho biết lịch sử hoàn tất được bao nhiêu việc |
| **Cycle time** | Thời gian từ lúc item bắt đầu đi vào luồng được đo tới khi hoàn tất | Cho biết một item đã bắt đầu thường mất bao lâu để đi hết luồng |
| **Lead time** | Thời gian từ mốc tiếp nhận/đặt hàng đã thỏa thuận tới mốc giao/hoàn tất | Giúp dự báo thời gian bên yêu cầu chờ nhận giá trị |
| **Work item age** | Thời gian một item đang thực hiện đã tồn tại, chưa Done | Phát hiện sớm công việc bị mắc kẹt trước khi hoàn tất |
| **WIP** | Số item đã bắt đầu nhưng chưa hoàn thành | Giúp quản lý số việc song song và năng lực hoàn tất |
| **Sự cố và chất lượng** | Lỗi sau phát hành, làm lại, tình huống không đạt DoD | Bảo đảm tăng tốc không nhờ bỏ kiểm thử hoặc chuyển gánh nặng sang vận hành |

Điều quan trọng là **định nghĩa nhất quán**. Nếu một tuần tính Done khi merge code còn tuần khác tính Done khi đã kiểm thử và tích hợp, throughput của hai tuần không đại diện cùng kết quả. Nếu một nhóm đo lead time từ ngày đề xuất còn nhóm khác đo từ khi Developers bắt đầu làm, hai số không thể so sánh trực tiếp.

### 4.1. Dữ liệu đo có đáng tin không?

Trước khi dùng làm căn cứ, hãy kiểm tra:

1. Các item có cùng chính sách bắt đầu/hoàn tất không?
2. Những việc khẩn, lỗi, công việc vận hành và hạng mục bị bỏ giữa chừng có được xử lý nhất quán?
3. Có backlog item “khổng lồ” bị bỏ ngoài thống kê vì chưa bao giờ Done?
4. Có thay đổi đáng kể về đội hình, kiến trúc, yêu cầu kiểm thử hoặc môi trường không?
5. Những item được chia nhỏ có còn tạo giá trị hoặc điều kiện hoàn thành thực chất?
6. Số lần quan sát có đủ để nhìn biến động, hay chỉ có một tuần thuận lợi?

Nếu dữ liệu chưa tốt, bước đầu có thể là **làm rõ chính sách đo và thu dữ liệu đúng**, không phải thay ước lượng bằng một phép chia bất kỳ.

## 5. Ví dụ tính thử dự báo không cần story point

Giả sử một nhóm làm việc theo luồng Kanban, các item được chia nhỏ theo hành vi người dùng và đã ghi nhận throughput trong **8 tuần** gần đây:

| Tuần | Hạng mục hoàn tất đạt điều kiện chung |
| --- | ---: |
| 1 | 4 |
| 2 | 5 |
| 3 | 4 |
| 4 | 6 |
| 5 | 5 |
| 6 | 4 |
| 7 | 5 |
| 8 | 3 |
| **Tổng** | **36** |
| **Trung bình mỗi tuần** | **4,5** |

Giả sử Product Backlog có **18 item** được xem là tương đối tương đồng với nhóm item vừa hoàn tất và chưa tính những phụ thuộc đặc biệt.

\[
\text{Thời gian tham khảo theo throughput trung bình}
= \frac{18}{4{,}5} = 4\ \text{tuần}.
\]

Con số **4 tuần chỉ là phép kiểm tra quy mô thô**, không phải một thời hạn cam kết. Những tuần vừa quan sát có throughput từ 3 tới 6; nếu lấy cực trị lịch sử làm minh họa, 18 item có thể tương ứng khoảng **3–6 tuần** khi tốc độ tương lai trùng với những cực trị đó. **Khoảng ấy cũng không phải khoảng tin cậy thống kê**, và thực tế hoàn toàn có thể nằm ngoài vì công việc hoặc bối cảnh mới khác đi.

### 5.1. Trước khi sử dụng kết quả, phải kiểm tra điều kiện

Trong 18 item có thể có một item “thay thế toàn bộ hệ thống xác thực” lớn hơn nhiều so với các việc trước. Nếu vậy, phép chia 18/4,5 **không còn đại diện tốt**. Nhóm nên:

- Tách item lớn thành những lát cắt có thể kiểm chứng, nếu kỹ thuật và nghiệp vụ cho phép.
- Nếu chưa chia được, thử một spike để hiểu rủi ro và giải pháp trước.
- Dự báo riêng công việc ngoại lệ theo phương pháp phù hợp, không nhét vào cùng nhóm đếm.
- Làm rõ các phụ thuộc, hạn hoặc điều kiện vận hành có thể làm khác lịch sử.

**Giảm ước lượng từng item không phải công thức thay thế mọi khó khăn bằng phép đếm.** Nó có ích khi đơn vị công việc thực sự có ý nghĩa và dữ liệu lịch sử đủ phù hợp.

### 5.2. Vì sao không chỉ báo cáo giá trị trung bình?

Hai nhóm có cùng trung bình 4,5 item/tuần nhưng một nhóm dao động quanh 4–5, nhóm kia lúc 0 lúc 9 sẽ có rủi ro về mốc giao rất khác nhau. Vì thế, khi dự báo cần xem:

- Dãy số theo thời gian và mức biến động.
- Loại item hoàn tất, mức độ khác biệt và số item đang làm dở.
- Công việc khẩn hoặc lỗi đã chiếm bao nhiêu năng lực.
- Độ trễ ở các bước chờ, đặc biệt review, kiểm thử và tích hợp.
- Những điều kiện của tương lai khác quá khứ: nghỉ phép, nhà cung cấp, sự kiện sản phẩm, thay đổi kiến trúc.

Nếu thiếu thông tin này, một dự báo có nhiều chữ số sau dấu phẩy có thể **chính xác về phép tính nhưng thiếu chính xác về thực tế**.

## 6. Dùng cycle time để hỗ trợ lựa chọn và kiểm soát rủi ro

Throughput giúp trả lời câu hỏi **“khoảng bao nhiêu item có thể hoàn tất?”**, còn cycle time giúp nhóm hiểu **“một item đang làm thường mất bao lâu?”**.

Ví dụ minh họa về cycle time của tám item đã hoàn tất trong cùng một loại công việc:

| Item | Cycle time |
| --- | ---: |
| 1 | 3 ngày |
| 2 | 4 ngày |
| 3 | 5 ngày |
| 4 | 5 ngày |
| 5 | 6 ngày |
| 6 | 7 ngày |
| 7 | 8 ngày |
| 8 | 11 ngày |

Trong **mẫu nhỏ này**, sáu trong tám item (75%) hoàn tất trong tối đa 7 ngày. Đây là một mô tả lịch sử, **không đủ để tuyên bố với độ tin cậy cao rằng 75% tất cả việc tương lai chắc chắn hoàn thành trong 7 ngày**.

Nếu một item đã bắt đầu được 10 ngày mà chưa Done, nhóm nên xem xét ngay **work item age**, hỏi vì sao nó chờ và có thể trợ giúp hoặc chia nhỏ phần còn lại không. Chờ tới khi item hoàn thành rồi mới tính cycle time sẽ bỏ lỡ cơ hội xử lý điểm tắc.

### 6.1. Service Level Expectation (SLE) cần được hình thành có cơ sở

Trong Kanban, một **Service Level Expectation** có thể diễn đạt kỳ vọng về cycle time cùng mức xác suất hoặc tỷ lệ phù hợp, dựa trên **dữ liệu lịch sử hoặc thông tin có căn cứ** và được xem lại khi có dữ liệu mới.

Ví dụ, sau khi có đủ quan sát của một loại việc ổn định, nhóm có thể nói: “Dựa trên lịch sử đã định nghĩa, khoảng X% hạng mục loại này hoàn tất trong Y ngày hoặc ít hơn.” Nếu mới có tám item, tốt hơn nên nói thẳng **mẫu nhỏ, còn bất định**, thay vì tự gắn nhãn P85 hoặc P95.

### 6.2. Giới hạn WIP góp phần giảm nhu cầu ước lượng

Nếu mọi người liên tục bắt đầu việc mới, nhiều item sẽ cùng nằm chờ; cycle time tăng và thông tin lịch sử khó áp dụng. Một hệ thống kéo việc, giới hạn WIP và tập trung hoàn tất có thể làm dòng chảy ổn định hơn.

Trong điều kiện ổn định dài hạn, có một quan hệ tổng quát được gọi là **Little's Law**:

\[
\text{WIP trung bình} \approx
\text{Throughput trung bình}\times\text{Cycle time trung bình}.
\]

Quan hệ này phụ thuộc **ranh giới hệ thống, thời gian đo và tính ổn định của dòng chảy**; không nên dùng như định luật dự đoán chính xác cho một Sprint đơn lẻ hoặc để suy ra mỗi người phải làm bao nhiêu việc. Ý nghĩa thực hành là: **mở quá nhiều việc cùng lúc** thường tạo hàng đợi và kéo dài thời gian hoàn tất.

## 7. Khi nào đếm item tốt hơn gán điểm?

Đếm số item và dự báo theo throughput thường phù hợp khi:

1. Nhóm hoàn thành nhiều hạng mục tương đối nhỏ và **đã có lịch sử của cùng loại công việc**.
2. Việc chia nhỏ diễn ra tự nhiên theo giá trị người dùng, không phải chia giả để tăng số lượng.
3. Chất lượng được bảo vệ bằng tiêu chí chấp nhận và Definition of Done/chính sách hoàn tất.
4. Nhóm có quyền điều phối WIP, giảm điểm chờ, liên tục kiểm tra độ lệch dữ liệu.
5. Thứ tự backlog không phụ thuộc vào việc tranh cãi điểm tương đối cho từng item.
6. Người liên quan chấp nhận **dự báo có điều kiện** và cơ chế cập nhật.

Khi đó, phần lớn hội thoại nên tập trung vào **“điều kiện nào khiến việc này đủ nhỏ và đủ rõ?”**, **“điều gì có thể khiến nó bị mắc kẹt?”** và **“chúng ta nên làm việc nào trước?”** thay vì cố chọn một số point.

### Hai cách dùng số liệu khác nhau

| Tình huống | Cách dùng ước lượng từng item | Cách dùng dữ liệu dòng công việc |
| --- | --- | --- |
| Backlog có nhiều hạng mục nhỏ tương đồng | Có thể bỏ gán điểm hoặc chỉ phân loại ngoại lệ | Dùng throughput và cycle time phù hợp để dự báo |
| Một vài item lớn xen giữa các việc nhỏ | Ước lượng/rà soát riêng ngoại lệ, chia nhỏ khi có thể | Dự báo nhóm việc nhỏ theo lịch sử, xử lý ngoại lệ tách biệt |
| Có mốc phát hành đã thương lượng, phạm vi có thể điều chỉnh | Dùng độ lớn khi giúp chọn phần tối thiểu | Dùng throughput lịch sử và kịch bản để nhìn khả năng hoàn tất |
| Dự án mới hoàn toàn, chưa có dữ liệu | Có thể dùng khoảng ước lượng chuyên gia, spike và rủi ro | Bắt đầu thu dữ liệu sớm; chưa được suy ra phân bố tin cậy |
| Công việc liên quan an toàn hoặc quyết định khó đảo ngược | Cần thẩm định chuyên môn/đánh giá tác động và kế hoạch riêng | Dữ liệu flow hỗ trợ điều phối, không thay thế phân tích an toàn |

Một nhóm không cần tuyên bố “chỉ dùng story point” hoặc “không bao giờ estimate”. **Phương pháp là công cụ; quyết định cần thông tin mới là mục tiêu.**

## 8. Những tình huống không nên giảm ước lượng một cách máy móc

Các trường hợp sau thường cần **làm rõ thêm, ước lượng có mục đích hoặc xử lý bằng cách khác trước khi dự báo**.

### 8.1. Kích thước và loại công việc quá khác nhau

Backlog có sửa lỗi đơn giản, viết chức năng mới, thay cơ sở dữ liệu lớn và nâng cấp hệ thống nhận diện. Không nên dự báo bằng cách coi tất cả là những hạng mục bằng nhau. Giải pháp: chia theo lát cắt, phân lớp công việc, xử lý hạng mục đặc biệt và cân nhắc ước lượng những phần ảnh hưởng quyết định đầu tư.

### 8.2. Nhóm mới hoặc thay đổi bối cảnh mạnh

Nhóm chưa có lịch sử hoặc vừa thay đổi nhiều thành viên, chuyển nền tảng kỹ thuật, nâng đáng kể Definition of Done, hoặc đổi phần lớn loại việc. Throughput cũ có thể **không còn đại diện**. Có thể thu dữ liệu mới, làm thử một lát cắt, dùng dự báo theo khoảng và một số đánh giá chuyên gia có kiểm soát.

### 8.3. Phụ thuộc bên ngoài chưa chắc chắn

Đối tác chưa có API, môi trường bảo mật chưa được cấp quyền, hoặc cần phê duyệt từ bộ phận khác. Gán story point có thể không giải quyết được thời gian chờ. Cần **xác định phụ thuộc, người chịu trách nhiệm, mốc quyết định và phương án dự phòng**; có thể ước lượng riêng phần công việc nội bộ nhưng phải công khai giới hạn.

### 8.4. Công việc có rủi ro hoặc tác động cao

Thay đổi phân quyền, thanh toán, dữ liệu nhạy cảm, phục hồi dữ liệu hoặc nghiệp vụ chịu quy định có thể cần phân tích thiết kế, kiểm thử chuyên sâu, phê duyệt và kế hoạch khôi phục. Dữ liệu throughput giúp lên lịch, **không thay thế thẩm định bắt buộc**.

### 8.5. Có quyết định đầu tư lớn hoặc hợp đồng

Một hạng mục cần thuê dịch vụ đắt tiền, mua bản quyền, thay đổi kiến trúc khó đảo ngược hoặc phụ thuộc ngân sách được phê duyệt. Nhóm có thể cần **khoảng chi phí, phương án, rủi ro và độ bất định** để ra quyết định, dù không gán story point cho từng task nhỏ.

### 8.6. Hạn giao không được bỏ lỡ, phạm vi khó thương lượng

Khi có nghĩa vụ pháp lý, thời điểm vận hành hay hợp đồng không linh hoạt, việc chỉ dùng trung bình throughput là chưa đủ. Cần phân tích tình huống bất lợi, chất lượng, phụ thuộc và cơ chế giảm rủi ro; một ước lượng chuyên sâu có thể cần thiết cho công việc trọng yếu. **Không tự biến dự báo trung bình thành cam kết chắc chắn**.

### 8.7. Độ biến động cao nhưng chưa biết nguyên nhân

Throughput dao động mạnh và work item age tăng bất thường có thể báo hiệu công việc quá lớn, quá nhiều việc đang làm, thiếu năng lực kiểm thử hoặc sự cố thường xuyên. Nên tìm nguyên nhân, cải thiện dòng chảy và phân loại số liệu trước khi kết luận “đếm item đã thay thế được mọi ước lượng”.

## 9. Chọn mức độ ước lượng theo quyết định cần hỗ trợ

Một chính sách thực dụng có thể chia các hạng mục thành bốn cách xử lý. Đây là **mô hình hướng dẫn**, không phải bộ trạng thái bắt buộc của Scrum hoặc Kanban.

| Trường hợp | Cách xử lý | Kết quả cần có |
| --- | --- | --- |
| **A. Nhỏ, rõ và thuộc loại công việc quen thuộc** | Không ước lượng riêng; kiểm tra đủ điều kiện Ready theo thỏa thuận và kéo làm | Hạng mục đủ nhỏ, có tiêu chí hoàn thành và nằm trong dữ liệu dòng chảy có thể dùng |
| **B. Có vẻ lớn hoặc chưa rõ ranh giới** | Chia nhỏ, làm rõ tiêu chí, so sánh tương đối rất nhẹ nếu cần | Các lát cắt có thể hoàn tất và kiểm chứng sớm |
| **C. Rủi ro kỹ thuật hoặc nhu cầu chưa chắc** | Spike/experiment giới hạn thời gian, xác định điều cần học | Bằng chứng cho quyết định tiếp theo, không chỉ một con số công sức |
| **D. Phụ thuộc, chi phí hoặc nghĩa vụ đặc biệt** | Ước lượng có mục đích, đánh giá chuyên môn, phân tích kịch bản và rủi ro | Cơ sở quyết định đầu tư/cam kết, kèm giới hạn và người có thẩm quyền |

### Sơ đồ lựa chọn cách xử lý

~~~mermaid
flowchart TD
    A["Có một hạng mục cần xem xét"] --> B{"Đủ nhỏ, rõ và tương đồng với dữ liệu lịch sử?"}
    B -->|"Có"| C{"Có quyết định hoặc rủi ro đặc biệt cần ước lượng?"}
    C -->|"Không"| D["Không gán điểm riêng: chọn việc, kiểm chứng và đo flow"]
    C -->|"Có"| E["Ước lượng có mục tiêu hoặc phân tích kịch bản"]
    B -->|"Chưa"| F{"Có thể chia thành lát cắt giá trị nhỏ?"}
    F -->|"Có"| G["Chia nhỏ và làm rõ; đánh giá lại"]
    G --> B
    F -->|"Chưa, vì thiếu thông tin"| H["Spike/experiment để giảm bất định"]
    H --> B
    F -->|"Không, do ràng buộc đặc biệt"| E
    D --> I["Quan sát kết quả và cập nhật dự báo"]
    E --> I
~~~

Mục tiêu của sơ đồ là tránh **hai cực đoan**: làm một nghi thức estimation dài với mọi việc, và bỏ qua hoàn toàn thông tin cần thiết cho quyết định lớn.

## 10. Ví dụ xuyên suốt: nhóm phát triển tính năng workshop

Một nhóm phát triển nền tảng học tập có backlog:

| Mã | Hạng mục | Đánh giá ban đầu |
| --- | --- | --- |
| A | Hiển thị trạng thái đăng ký của chính học viên | Hành vi nhỏ, quen thuộc |
| B | Sửa lỗi thông báo “đã xác nhận” khi thực tế hết chỗ | Lỗi nghiệp vụ quan trọng, cần xử lý sớm |
| C | Cho phép hủy trước hạn theo chính sách hiện tại | Có thể chia thành lát cắt nhỏ sau khi làm rõ chính sách |
| D | Bổ sung bộ lọc workshop theo chủ đề | Hạng mục nhỏ, có thể thử sau khi có phản hồi |
| E | Tích hợp nhà cung cấp thanh toán hoàn toàn mới | Khác loại việc, phụ thuộc và rủi ro lớn |
| F | Chuyển dữ liệu đăng ký sang mô hình lưu trữ mới | Khó đảo ngược, cần kiểm tra di trú và phục hồi |
| G | Gắn mã tương quan vào log lỗi đăng ký | Cải tiến vận hành nhỏ, thuộc quy trình quen thuộc |

Nhóm đã có dữ liệu throughput khá ổn định cho **A, C, D, G và các việc tương tự**, nhưng chưa từng thực hiện loại công việc giống **E hoặc F**.

### 10.1. Cách làm kém hiệu quả

Nhóm dành nhiều giờ gán story point cho mọi item, kể cả thay đổi nhỏ đã hiểu rõ. Cuối cùng họ lấy tổng điểm chia velocity rồi công bố ngày giao cho cả E và F, dù phụ thuộc thanh toán chưa rõ và không có dữ liệu về rủi ro di trú.

Cách này tạo **ảo giác chính xác**: nhiều con số không có nghĩa nhiều bằng chứng.

### 10.2. Cách làm thích ứng hơn

- **A, D, G:** Không nhất thiết gán điểm riêng nếu đủ nhỏ, rõ và so sánh được với lịch sử. Chọn theo ưu tiên backlog, dùng throughput/cycle time để dự báo gần.
- **B:** Dù có thể nhỏ, vẫn phải ưu tiên theo mức độ ảnh hưởng; kiểm chứng tính đúng đắn và chất lượng trước khi tuyên bố Done. Không dùng “khỏi estimate” làm lý do trì hoãn lỗi nghiêm trọng.
- **C:** Làm rõ quy tắc hủy, chia phần có thể hoàn tất, kiểm thử phân quyền và cập nhật chỗ; sau đó có thể đưa vào cùng nhóm hạng mục nhỏ để theo dõi flow.
- **E:** Làm spike về API, xử lý lỗi, bảo mật, thanh toán và thời điểm phản hồi từ nhà cung cấp; có thể cần dự báo riêng theo phụ thuộc và chi phí.
- **F:** Phân tích rủi ro dữ liệu, thiết kế chuyển đổi, diễn tập khôi phục; cân nhắc chia giai đoạn tương thích và ước lượng riêng các hoạt động quan trọng.

Kết quả là **nhóm vẫn lập kế hoạch và dự báo** nhưng chỉ dành công sức ước lượng sâu cho những nơi thông tin thực sự có thể thay đổi quyết định.

### 10.3. Phản hồi thay đổi ưu tiên như thế nào?

Sau khi phát hành một lát cắt, người dùng phản ánh khó nhìn thấy trạng thái đã xác nhận hơn là thiếu bộ lọc chủ đề. Product Owner có thể đưa **A và B** lên trước **D**. Nhóm không cần gán lại điểm cho mọi PBI để nhận ra điều đó: **giá trị, rủi ro và bằng chứng người dùng** mới là lý do của thay đổi ưu tiên.

## 11. Cách dự báo có cơ sở khi không ước lượng từng item

Có thể áp dụng một quy trình từng bước:

### Bước 1. Thống nhất loại công việc và tiêu chí Done

Xác định nhóm item nào đủ tương đồng, khi nào bắt đầu/hoàn tất, chất lượng nào được yêu cầu và công việc nào cần dự báo riêng. Nếu mục tiêu là giao Increment hoạt động được, đừng tính item đã code xong nhưng chưa tích hợp/kiểm thử là hoàn tất.

### Bước 2. Lấy dữ liệu lịch sử phù hợp

Sử dụng throughput theo tuần hoặc Sprint, cycle time và WIP với định nghĩa nhất quán. Ghi lại thay đổi đội hình, sự cố, loại công việc hoặc quy trình khiến lịch sử kém đại diện.

### Bước 3. Làm rõ và chia backlog gần

Tách item quá lớn, xác minh phụ thuộc và rủi ro. Không cần làm rõ chi tiết mọi ý tưởng xa trong tương lai; nhưng **đếm một danh sách toàn việc chưa rõ** sẽ làm dự báo rất yếu.

### Bước 4. Xác định câu hỏi dự báo

Phân biệt:

- **“Khi nào 18 item được chọn có thể hoàn tất?”** (*When?*)
- **“Trong bốn tuần tới có thể hoàn tất khoảng bao nhiêu item loại này?”** (*How many?*)
- **“Một item đã bắt đầu thường cần bao lâu để hoàn tất?”** (*How long for this item?*)

Ba câu hỏi sử dụng cùng nguồn dữ liệu ở những cách khác nhau; không được tráo câu hỏi để lựa chọn con số đẹp nhất.

### Bước 5. Chọn mức tinh vi tương xứng dữ liệu

Với dữ liệu ít, dùng **kịch bản có điều kiện và phân tích độ biến động**. Khi có nhiều chu kỳ đại diện, có thể dùng **mô phỏng Monte Carlo hoặc phương pháp dự báo khác**, nhưng phải công khai giả định và kiểm tra độ phù hợp.

### Bước 6. Công bố dự báo kèm giới hạn

Ví dụ: “Nếu loại hạng mục và năng lực giống tám tuần gần đây, 18 việc nhỏ có mốc tham khảo khoảng bốn tuần theo throughput trung bình; rủi ro lớn là phụ thuộc thanh toán nên chưa tính chung.” Đây là thông tin hữu ích hơn một ngày giao chính xác thiếu căn cứ.

### Bước 7. Theo dõi công việc đang làm và cập nhật thường xuyên

Theo dõi WIP, work item age, item phát sinh và tình huống chờ. Khi có dữ liệu mới hoặc bối cảnh thay đổi, cập nhật phạm vi hoặc dự báo; không giữ số cũ chỉ vì đã gửi trong báo cáo.

### Vòng phản hồi

~~~mermaid
flowchart LR
    A["Mục tiêu và backlog có thứ tự"] --> B["Hạng mục đủ nhỏ, DoD rõ"]
    B --> C["Dữ liệu throughput / cycle time / WIP"]
    C --> D["Dự báo có điều kiện"]
    D --> E["Thực hiện, kiểm thử, hoàn tất"]
    E --> F["Quan sát phản hồi và dòng công việc"]
    F --> G["Kiểm tra sai lệch, thay đổi cách chia hoặc xử lý ngoại lệ"]
    G --> A
~~~

Điểm quan trọng: **dự báo từ dữ liệu không phải hoạt động làm một lần rồi đóng băng**, mà là một phần của vòng kiểm tra và thích ứng.

## 12. Dự báo xác suất: có thể hỗ trợ nhưng không tự sinh ra độ tin cậy

**Monte Carlo** là một cách mô phỏng nhiều kịch bản hoàn tất bằng cách lấy mẫu từ dữ liệu quá khứ hoặc từ mô hình đã định. Trong dự báo throughput, một cách tiếp cận đơn giản là lặp lại việc lấy mẫu throughput của các tuần đại diện, cộng dồn cho đến khi đạt số item cần giao, rồi quan sát phân bố số tuần.

Mô tả ý tưởng (không phải công thức áp dụng máy móc):

~~~text
Đầu vào:
  - Lịch sử throughput của những tuần tương đồng
  - Số hạng mục còn lại đã đủ rõ và được chia hợp lý
  - Giả định về đội hình, loại công việc, phụ thuộc

Lặp nhiều kịch bản:
  1. Số item còn lại = số item cần dự báo
  2. Lấy ngẫu nhiên một mức throughput từ lịch sử phù hợp
  3. Trừ số item hoàn tất trong tuần mô phỏng
  4. Lặp lại bước 2–3 cho tới khi hoàn tất
  5. Ghi số tuần của kịch bản

Sau các lần mô phỏng:
  - Xem phân bố các mốc hoàn tất
  - Trình bày ngưỡng theo phương pháp thống kê đã chọn
  - Ghi rõ giả định và rủi ro không có trong dữ liệu
~~~

Nếu nguồn dữ liệu chỉ gồm vài tuần, có nhiều loại việc khác nhau, hoặc tương lai thay đổi mạnh so với lịch sử, mô phỏng cũng có thể cho con số **trông tinh vi nhưng không đáng tin**. Việc lấy mẫu ngẫu nhiên không sửa được dữ liệu đầu vào thiếu đại diện.

### Các điều kiện cần nói rõ khi dùng dự báo xác suất

- **Tính đại diện:** Đội hình, DoD, loại item và phụ thuộc có gần với lịch sử không?
- **Cấu trúc công việc:** Các item có kích thước tương đối kiểm soát được? Có việc lớn phải dự báo riêng?
- **Độ độc lập hoặc phụ thuộc:** Nhiều item có bị chặn cùng lúc bởi một hệ thống ngoài hoặc một người duy nhất?
- **Rủi ro hiếm gặp:** Sự cố lớn hoặc biến cố chưa từng có trong lịch sử sẽ không tự xuất hiện trong mô phỏng lấy mẫu lịch sử.
- **Số quan sát:** Mẫu quá ít có thể khiến ước lượng các phần đuôi phân phối rất không ổn định.
- **Kiểm tra ngược:** Nếu chạy dự báo từ dữ liệu của các giai đoạn cũ, kết quả có thường bao phủ thời gian thực tế hay không?

Chỉ báo cáo “85% khả năng hoàn tất trước ngày X” khi **có quy trình tính, dữ liệu và phạm vi hiệu lực rõ ràng**. Nếu không đủ cơ sở, hãy đưa ra kịch bản và giải thích bất định thay vì tự gắn P85.

## 13. Scrum và việc giảm ước lượng từng Product Backlog Item

Scrum Guide 2020 **không bắt buộc story point, Planning Poker hoặc velocity**. Trong Scrum, Developers chịu trách nhiệm **đánh giá độ lớn** (*sizing*) của Product Backlog Item; Product Owner có thể tác động tới thảo luận bằng cách giúp làm rõ giá trị và đánh đổi. Đánh giá độ lớn không có nghĩa bắt buộc phải gán điểm cho mọi item.

Điều quan trọng là Product Backlog đủ minh bạch và các PBI đủ nhỏ, đủ rõ để Developers có thể lựa chọn trong Sprint Planning, tạo Sprint Goal và lập kế hoạch đạt Increment đáp ứng Definition of Done.

### 13.1. Những gì vẫn phải xảy ra dù không gán story point

| Hoạt động Scrum | Điều vẫn cần làm |
| --- | --- |
| **Product Backlog Refinement** | Làm rõ, chia nhỏ PBI; trao đổi rủi ro, phụ thuộc, điều kiện chấp nhận và độ lớn tới mức giúp ra quyết định |
| **Sprint Planning** | Chọn Sprint Goal; Developers đánh giá công việc khả thi theo năng lực và thông tin hiện có; xác định PBI được chọn và kế hoạch thực hiện |
| **Daily Scrum** | Kiểm tra tiến độ tới Sprint Goal và điều chỉnh kế hoạch của Developers; làm rõ điểm nghẽn đang ảnh hưởng việc hoàn tất |
| **Sprint Review** | Đánh giá Increment và điều đã học, cập nhật Product Backlog |
| **Sprint Retrospective** | Nhận diện vấn đề của quá trình, thử thay đổi cách chia việc, phối hợp và đo lường |
| **Definition of Done** | Giữ tiêu chuẩn chất lượng; phần chưa đạt DoD chưa phải Increment hoàn chỉnh |

Nếu nhóm đã làm PBI nhỏ và ổn định, có thể dựa vào **số item hoàn tất trong những Sprint gần đây** khi thảo luận phạm vi Sprint, đồng thời xem năng lực và rủi ro riêng của Sprint sắp tới. Không nên đổi từ “chạy theo số point” sang “chạy theo số item”; mục tiêu là **Sprint Goal và giá trị**, không phải đạt chỉ tiêu số lượng.

### 13.2. Product Owner vẫn cần quyết định ưu tiên theo giá trị

Việc giảm ước lượng không đồng nghĩa Product Owner chỉ sắp backlog theo kích thước. Một lỗi khiến học viên đăng ký vượt sức chứa có thể được ưu tiên trước hàng chục cải tiến giao diện dù không biết chính xác nó là 3 hay 5 điểm.

**Người phụ trách sản phẩm chịu trách nhiệm về giá trị và thứ tự; Developers cung cấp hiểu biết kỹ thuật, rủi ro và năng lực thực thi.** Cần trao đổi để đưa ra lựa chọn chung, không để một số điểm trở thành người ra quyết định thay các vai trò.

## 14. Kanban và XP hỗ trợ điều kiện giảm ước lượng như thế nào?

### 14.1. Kanban: làm cho dữ liệu dòng chảy đáng sử dụng

Các thực hành quản lý dòng công việc của Kanban tạo điều kiện:

- Trực quan hóa trạng thái và nơi công việc thường bị chờ.
- Làm rõ chính sách bắt đầu và hoàn tất hạng mục.
- Hạn chế WIP để tập trung hoàn tất thay vì mở thêm.
- Theo dõi throughput, cycle time, work item age và trạng thái bị tắc.
- Xem lại chính sách, kích thước item và năng lực dựa trên dữ liệu.

Một hệ thống ổn định hơn sẽ giúp dự báo theo dòng công việc **bớt phụ thuộc vào ước lượng riêng cho từng item nhỏ**. Nhưng Kanban không tự bảo đảm mọi công việc giống nhau; nhóm vẫn cần xử lý ngoại lệ và chất lượng.

### 14.2. XP: giảm chi phí thay đổi và công việc làm lại

Các thực hành kỹ thuật trong Extreme Programming như **kiểm thử tự động, tích hợp liên tục, refactoring, thiết kế đơn giản và phản hồi nhanh** giúp nhóm chia lát cắt nhỏ và giao thường xuyên mà không tích tụ lỗi khó sửa.

Nếu nhóm luôn phải sửa lại mã lớn, chờ tích hợp lâu hoặc không kiểm thử tự động, cycle time sẽ biến động mạnh. Khi ấy, **cải thiện năng lực hoàn tất** thường đem lại giá trị hơn việc dành thêm thời gian tranh luận điểm số.

### 14.3. Dùng kết hợp theo nhu cầu

Một Scrum Team có thể dùng Scrum cho mục tiêu và nhịp kiểm tra, Kanban để đo dòng công việc trong Sprint và các kỹ thuật XP để tạo Increment đáng tin cậy. Khi đã quan sát đủ điều kiện, nhóm có thể giảm nghi thức gán điểm mà vẫn quản lý rủi ro và dự báo có cơ sở.

## 15. Thử nghiệm chuyển từ ước lượng từng item sang dự báo bằng flow

Không nhất thiết phải đổi chính sách của toàn tổ chức trong một ngày. Hãy coi đây là **thử nghiệm cải tiến quy trình**, có phạm vi và cách đánh giá rõ.

### Bước 1. Nêu vấn đề thật sự cần giải quyết

Ví dụ: “Nhóm mất nhiều thời gian gán point cho các thay đổi nhỏ nhưng độ chính xác của dự báo không cải thiện.” Ghi một mức nền: thời gian refinement, mức chênh lệch dự báo và vấn đề chất lượng gần đây.

### Bước 2. Chọn một nhóm hạng mục phù hợp

Bắt đầu với việc nhỏ, quen thuộc, ít phụ thuộc và có thể hoàn thành đạt DoD. **Không chọn ngay một chương trình di trú dữ liệu phức tạp** để chứng minh mọi ước lượng đều vô ích.

### Bước 3. Thống nhất điều kiện “đủ nhỏ”

Nhóm trao đổi và xác định dấu hiệu thực dụng: hạng mục có kết quả rõ, kiểm chứng được đầu cuối, ít phụ thuộc, không có rủi ro ẩn lớn, có thể hoàn tất theo dòng công việc thường thấy. Nếu không đáp ứng, chia nhỏ hoặc đưa sang cách xử lý ngoại lệ.

### Bước 4. Chuẩn hóa quy tắc đo

Xác định khi nào item vào WIP, khi nào Done, cách xử lý chặn việc, lỗi phát sinh và item bị hủy. Tiếp tục giữ Definition of Done hoặc tiêu chuẩn chất lượng hiện có.

### Bước 5. Theo dõi một giai đoạn và đối chiếu

So sánh dự báo theo throughput/cycle time với kết quả thực tế, đồng thời xem thời gian thảo luận tiết kiệm, biến động, mức tập trung, chất lượng và mức độ minh bạch cho người liên quan. Giai đoạn thử cần đủ dài để quan sát vài vòng công việc; **không có một số tuần cố định phù hợp mọi nhóm**.

### Bước 6. Giữ cơ chế ước lượng cho ngoại lệ

Nếu xuất hiện hạng mục lớn, mới, bị chặn bởi đối tác hoặc rủi ro cao, nhóm có thể ước lượng riêng, làm spike hoặc phân tích kịch bản. Không được yêu cầu mọi người “không estimate” ngay cả khi đang thiếu thông tin ra quyết định.

### Bước 7. Đánh giá và điều chỉnh chính sách

Nếu dự báo giữ hoặc tăng mức hữu ích, chất lượng không giảm và thời gian thảo luận không tạo giá trị giảm, cân nhắc mở rộng cách làm. Nếu dự báo liên tục sai vì size biến động hoặc DoD thiếu nhất quán, xử lý nguyên nhân trước; có thể tạm giữ một số hình thức ước lượng.

### Tiêu chí xem thử nghiệm có hữu ích không

| Cần quan sát | Câu hỏi đánh giá |
| --- | --- |
| **Chi phí trao đổi** | Nhóm có giảm thời gian tranh cãi con số nhưng vẫn hiểu rõ rủi ro và yêu cầu? |
| **Chất lượng dự báo** | Mốc và khoảng dự báo có phù hợp kết quả thực tế hơn hay ít nhất không kém đi? |
| **Dòng công việc** | Cycle time, work item age và WIP có ổn định hơn? |
| **Chất lượng sản phẩm** | Có tăng lỗi sau phát hành hoặc làm lại vì bỏ sót kiểm tra? |
| **Giá trị người dùng** | Nhóm có giao lát cắt có ích sớm hơn và dùng phản hồi để điều chỉnh backlog? |
| **Minh bạch** | Người liên quan có hiểu giả định, giới hạn và thay đổi dự báo? |

Đừng biến việc giảm thời gian estimate thành mục tiêu duy nhất. Nếu nhóm tiết kiệm được hai giờ họp nhưng liên tục phát hành phần mềm thiếu kiểm thử, thử nghiệm đã đánh đổi sai điều quan trọng.

## 16. Những sai lầm thường gặp

| Sai lầm | Vì sao nguy hiểm | Cách khắc phục |
| --- | --- | --- |
| “No estimates nghĩa là không cần kế hoạch” | Không có căn cứ về phạm vi, năng lực hoặc mốc phối hợp | Vẫn dùng backlog, dữ liệu flow, kịch bản, điều kiện và lịch xem lại |
| “Mọi item đều bằng một” | Việc lớn và nhỏ bị coi tương đương, dự báo méo | Chia nhỏ, phân loại, tách ngoại lệ hoặc estimate khi cần |
| “Không gán điểm thì khỏi refinement” | Yêu cầu và rủi ro bị hiểu sai, làm lại tăng | Vẫn thảo luận ví dụ, tiêu chí chấp nhận, phụ thuộc và slicing |
| “Đếm được bao nhiêu item thì giao đúng bấy nhiêu” | Throughput lịch sử không phải cam kết chắc chắn | Xem biến động, năng lực tương lai và bất định |
| “Tăng item Done là tăng năng suất” | Khuyến khích chia giả và đóng việc chưa đạt chất lượng | Giữ Done rõ, theo dõi kết quả người dùng và lỗi |
| “Kết quả Monte Carlo có số phần trăm nên chắc đáng tin” | Mô hình có thể dựa trên dữ liệu ít hoặc khác bối cảnh | Kiểm tra nguồn dữ liệu, giả định và khả năng dự báo ngược |
| “Thấy cycle time trung bình thấp nên việc nào cũng làm xong nhanh” | Việc mới có thể ở đuôi dài hoặc bị chặn | Xem phân phối và work item age; xử lý item đặc biệt |
| “Không cần ước lượng các thay đổi bảo mật lớn” | Quyết định rủi ro cao không được thẩm định | Phân tích chuyên môn, phương án và kế hoạch khôi phục |
| “Nhóm khác làm 5 item/tuần nên chúng ta cũng phải làm 5” | Item, DoD, kỹ năng và công nghệ khác nhau | Dùng dữ liệu của hệ thống làm việc tương đồng, không xếp hạng đội |
| “Đổi chính sách đo giữa chừng nhưng vẫn ghép lịch sử” | So sánh throughput/cycle time không đồng nhất | Ghi mốc đổi, tách dữ liệu hoặc hiệu chỉnh cách diễn giải |
| “Chỉ ưu tiên việc nhỏ vì dễ đếm” | Lỗi trọng yếu và công việc kiến trúc khó bị bỏ quên | Ưu tiên theo giá trị/rủi ro, xử lý ngoại lệ riêng |
| “Giữ ngày giao cố định dù điều kiện đã khác” | Cam kết mất căn cứ, chất lượng dễ bị cắt | Báo thay đổi sớm, thương lượng phạm vi và giải pháp |

**Đếm việc không phải mục đích của Agile**, cũng như gán điểm không phải mục đích. Cả hai chỉ hữu ích nếu giúp nhóm đưa ra quyết định và giao phần mềm tạo giá trị an toàn hơn.

## 17. Mẫu kiểm tra nhanh trước khi giảm ước lượng

Nhóm có thể dùng biểu mẫu dưới đây trong retrospective hoặc buổi cải tiến quy trình. Một câu trả lời “Chưa” không tự động cấm áp dụng; nó chỉ báo cần **hành động khắc phục hoặc phạm vi áp dụng nhỏ hơn**.

~~~text
PHẠM VI CÔNG VIỆC MUỐN GIẢM ESTIMATION:
MỤC ĐÍCH GIẢM: Tiết kiệm thời gian? Dự báo tốt hơn? Giảm tranh luận?

[ ] Item được chia nhỏ thành lát cắt có giá trị và kiểm chứng được
[ ] Kích thước item không biến động quá lớn, hoặc ngoại lệ được tách
[ ] Tiêu chí Done/Definition of Done rõ và dùng nhất quán
[ ] Có dữ liệu throughput/cycle time/WIP đủ đại diện cho loại việc
[ ] Đội hình, quy trình và loại việc sắp tới tương đối gần lịch sử
[ ] Có chính sách giới hạn WIP và xử lý công việc bị chặn
[ ] Product Backlog được sắp thứ tự theo giá trị/rủi ro
[ ] Có cách kiểm soát bảo mật, chất lượng và vận hành
[ ] Người liên quan hiểu dự báo có điều kiện, không phải bảo đảm
[ ] Có mốc xem lại dự báo, điều kiện dừng và cách học từ sai lệch

NGOẠI LỆ CẦN ESTIMATE / THẨM ĐỊNH RIÊNG:
- Công việc lớn, chưa rõ hoặc khác lịch sử:
- Phụ thuộc bên ngoài:
- Quyết định chi phí/đầu tư hoặc cam kết bắt buộc:
- Rủi ro an toàn, dữ liệu hoặc pháp lý:

THỬ NGHIỆM:
- Phạm vi và thời gian quan sát:
- Dữ liệu nền và cách đo:
- Cách dự báo dự kiến:
- Cách so sánh với kết quả thực tế:
- Người chịu trách nhiệm cập nhật chính sách:
~~~

### Ba mức khuyến nghị theo tình trạng hiện tại

| Tình trạng | Cách tiến hành |
| --- | --- |
| **Đủ phần lớn điều kiện, ngoại lệ được quản lý** | Giảm hoặc bỏ gán điểm cho item nhỏ; dùng throughput/cycle time để dự báo; thường xuyên kiểm tra sai lệch |
| **Điều kiện đạt một phần** | Thử với một loại công việc; cải thiện slicing và chính sách đo; giữ estimation nhẹ cho hạng mục khó |
| **Thiếu dữ liệu, kích thước quá khác hoặc rủi ro cao** | Chưa chuyển hàng loạt; ưu tiên làm rõ, thu dữ liệu, spike/ước lượng có mục đích và quản lý rủi ro |

## 18. Bài tập ứng dụng

**Tình huống:** Một nhóm xây nền tảng học tập có các thông tin sau:

- Tám tuần gần đây nhóm hoàn tất lần lượt **4, 5, 4, 6, 5, 4, 5, 3 item**; các item này chủ yếu là chỉnh sửa giao diện và API nhỏ, đã đạt tiêu chuẩn Done chung.
- Sắp tới có **15 item nhỏ thuộc cùng loại**, hai item tích hợp hệ thống thanh toán mới và một công việc di trú dữ liệu học viên.
- Trong ba tuần tới có một người phụ trách thanh toán nghỉ phép và nhà cung cấp mới chưa xác nhận tài liệu API.
- Product Owner muốn công bố một ngày hoàn tất **tất cả 18 item** chỉ bằng phép lấy số item chia cho throughput trung bình.
- Nhóm muốn bỏ Planning Poker vì thường phải tranh luận lâu về các item nhỏ đã rõ.

Hãy trả lời:

1. Lịch sử throughput của nhóm có thể hỗ trợ dự báo tốt nhất cho **nhóm item nào**? Vì sao không thể gộp cả 18 item vào một phép chia?
2. Trung bình tám tuần là bao nhiêu item/tuần? Dự báo thô cho 15 item nhỏ là bao nhiêu tuần nếu giả định mọi điều kiện tương đương?
3. Ngoài trung bình, bạn cần xem những thông tin nào về biến động, độ lớn, WIP, work item age và chất lượng?
4. Hai item thanh toán và việc di trú cần hoạt động làm rõ, spike, ước lượng hoặc phương án phối hợp nào?
5. Khi chuyên gia vắng mặt và nhà cung cấp chưa sẵn sàng, dự báo nên thể hiện giới hạn gì?
6. Trong trường hợp nào có thể bỏ gán point cho 15 item nhỏ mà vẫn duy trì Sprint Planning hoặc chính sách kéo việc?
7. Bạn sẽ diễn đạt dự báo với Product Owner ra sao để tránh nhầm “trung bình lịch sử” thành ngày giao chắc chắn?
8. Nếu sau khi chuyển sang đếm item, số item Done tăng nhưng lỗi sau phát hành tăng, nhóm cần xem lại những điều gì?

### Gợi ý hướng giải

Tổng throughput quan sát là **36 item** trong **8 tuần**, trung bình **4,5 item/tuần**. Với **15 item nhỏ tương đồng**, phép chia tham khảo là:

\[
\frac{15}{4{,}5} \approx 3{,}33\ \text{tuần}.
\]

Đây chỉ là **mốc toán học minh họa**, không phải cam kết 3,33 tuần hoặc khoảng tin cậy. Cần xem biến động, khả năng hoàn tất theo Done, năng lực mới và những công việc đang dở. Hai item thanh toán và việc di trú khác loại lịch sử, có rủi ro/phụ thuộc lớn; nên xử lý riêng, tìm bằng chứng kỹ thuật và lên phương án rõ ràng. Phần vắng mặt và nhà cung cấp chưa xác nhận cần được đưa vào kế hoạch, không “ẩn” trong dự báo trung bình.

Nhóm có thể **giảm gán point cho các item nhỏ**, vẫn refinement, lập Sprint Goal, theo dõi WIP và đo kết quả; đồng thời giữ đánh giá có mục đích cho hạng mục lớn hoặc chưa rõ. Nếu lỗi sau phát hành tăng, trước hết kiểm tra DoD, cách chia công việc, áp lực đóng item và chất lượng kiểm thử. **Dự báo tốt phải phục vụ việc giao giá trị đáng tin cậy**, không chỉ làm bảng số liệu trông nhanh hơn.

## 19. Ghi nhớ và tự kiểm tra

**Thông điệp chính:** Có thể giảm nhu cầu ước lượng từng hạng mục khi công việc được chia nhỏ phù hợp, mức biến thiên được kiểm soát, Definition of Done nhất quán, dữ liệu dòng công việc đủ đại diện và nhóm thường xuyên kiểm tra dự báo. Trong điều kiện đó, throughput, cycle time, WIP và khả năng phát hiện ngoại lệ có thể cung cấp thông tin lập kế hoạch tốt mà không cần gán điểm cho mọi story. Nhưng **không thể thay việc phân tích rủi ro, phụ thuộc và cam kết bằng phép đếm**, nhất là với công việc mới, lớn hoặc có hậu quả đáng kể.

Tự kiểm tra:

1. Ước lượng từng item khác dự báo và cam kết như thế nào?
2. Vì sao gán điểm cho mọi story không phải yêu cầu bắt buộc của Scrum?
3. Điều kiện nào khiến phép đếm số item có giá trị hơn là cộng story point?
4. Vì sao chia một chức năng thành các tầng kỹ thuật rời rạc chưa chắc cải thiện dự báo theo throughput?
5. Sự khác nhau giữa throughput, cycle time và work item age là gì?
6. Khi lịch sử có 8 tuần throughput, có thể khẳng định “P85 hoàn tất đúng ngày X” chỉ bằng trung bình hay không?
7. Vì sao cần kiểm soát WIP và dùng một chính sách Done nhất quán nếu muốn dự báo từ dữ liệu dòng công việc?
8. Hãy nêu ba trường hợp vẫn nên ước lượng hoặc thẩm định riêng một hạng mục.
9. Một dự báo theo throughput có thể sai vì những lý do nào dù phép tính trung bình hoàn toàn đúng?
10. Nếu thử bỏ story point giúp tiết kiệm họp nhưng chất lượng giảm, nhóm nên quyết định điều gì?

Trước khi dành công sức gán một con số cho hạng mục, hãy hỏi: **“Con số này giúp thay đổi quyết định nào, dữ liệu đã có có trả lời được câu hỏi đó không, và ngoại lệ nào cần được đánh giá riêng?”** Đó là cách dùng ước lượng **có chủ đích**, dự báo **dựa trên bằng chứng** và giữ khả năng thích ứng, giao sản phẩm tăng dần, cải tiến liên tục trong Agile.
