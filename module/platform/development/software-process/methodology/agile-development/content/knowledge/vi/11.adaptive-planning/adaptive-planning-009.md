# Phân biệt dự báo thực hiện với cam kết thời hạn cố định trong Agile

> **Trọng tâm:** Dự báo trả lời “**Với những gì hiện biết, khi nào công việc *có khả năng* hoàn thành và mức bất định là bao nhiêu?**”. Cam kết thời hạn cố định trả lời “**Điều gì phải có trước một mốc không được tự ý dời, ai chịu trách nhiệm và chúng ta sẽ quản lý đánh đổi ra sao?**”. Phát triển phần mềm Agile cần cả khả năng dự báo trung thực lẫn trách nhiệm với cam kết, nhưng không nên biến một con số ước lượng thành lời hứa chắc chắn.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Phân biệt **ước lượng (estimate)**, **dự báo (forecast)**, **mục tiêu thời hạn (target date)** và **cam kết thời hạn cố định (fixed-date commitment)**.
2. Giải thích vì sao kế hoạch Agile cần cập nhật khi xuất hiện dữ liệu mới, dù nhóm vẫn có thể chịu ràng buộc về thời gian.
3. Dùng dữ liệu **throughput, cycle time, lead time, work item age và WIP** để đặt câu hỏi và lập dự báo có điều kiện.
4. Nhận diện giới hạn của dự báo dựa trên velocity, trung bình, các phân vị hoặc mô phỏng Monte Carlo.
5. Làm rõ **phạm vi tối thiểu, chất lượng, mốc quyết định, phụ thuộc và phương án dự phòng** trước một ngày phát hành bắt buộc.
6. Phối hợp **Scrum, Kanban và các thực hành kỹ thuật XP** để giảm bất định và giao phần mềm tăng dần.
7. Trình bày dự báo, thay đổi dự báo và nguy cơ trễ hạn một cách minh bạch cho Product Owner, nhóm phát triển và bên liên quan.

## 2. Tình huống mở đầu: “Bao giờ xong?” có hai ý nghĩa

Một nhóm xây dựng nền tảng học trực tuyến đang chuẩn bị phiên bản cho đối tác dùng thử. Người phụ trách sản phẩm hỏi: **“Bao giờ hoàn thành chức năng học và lưu tiến độ?”**

Nhóm có thể trả lời:

> “Theo phạm vi hiện tại và dữ liệu các tuần trước, nhóm dự kiến cần thêm khoảng bốn đến sáu tuần. Chúng ta cần xem lại sau khi kiểm chứng phần đồng bộ tiến độ vì còn phụ thuộc hệ thống lưu trữ.”

Đó là **dự báo**: dựa vào dữ liệu và giả định hiện có, chứa khoảng bất định và có thể cập nhật.

Nhưng nếu hợp đồng ghi ngày **30/06/2027** phải có bản dùng thử với một số khả năng tối thiểu, câu hỏi khác xuất hiện:

> “Đến ngày 30/06/2027, chúng ta phải giao được **luồng nào**, đạt **chuẩn chất lượng nào**, cần **ai chấp thuận**, và nếu một tính năng chưa kịp thì xử lý ra sao?”

Đó là vấn đề của **cam kết thời hạn**. Ngày đã được xác lập có thể không tự động đổi theo dự báo, nhưng **phạm vi, cách triển khai, lộ trình và quyết định chấp nhận rủi ro** cần được quản lý chủ động. Nếu yêu cầu không thể thỏa mãn với nguồn lực và ràng buộc hiện có, nhóm phải báo sớm để các bên có thẩm quyền thương lượng.

Hai câu trả lời không mâu thuẫn: **dự báo cung cấp bằng chứng để quản lý cam kết**. Sai lầm xảy ra khi nhóm trình bày dự báo “có thể xong cuối tháng” thành “chắc chắn xong cuối tháng”, hoặc dùng sự tồn tại của deadline để phủ nhận mọi rủi ro thực tế.

## 3. Bốn khái niệm cần phân biệt

| Khái niệm | Bản chất | Ví dụ | Cần nói rõ |
|---|---|---|---|
| **Ước lượng (estimate)** | Nhận định về quy mô, công sức hoặc độ phức tạp của một việc | “Tích hợp lưu tiến độ có thể cần 3–5 ngày làm việc.” | Cơ sở, người tham gia, điều chưa biết và khoảng biến động |
| **Dự báo (forecast)** | Nhận định về kết quả tương lai dựa trên dữ liệu, giả định và cách mô hình hóa | “Nếu throughput và phạm vi tương tự hiện tại, có khả năng hoàn tất nhóm PBI trong 4–6 tuần.” | Ngữ cảnh, điều kiện, mốc tính, mức độ tin cậy, lúc cập nhật |
| **Ngày mục tiêu (target date)** | Mốc nhóm muốn đạt; có thể điều chỉnh khi học được thông tin mới | “Muốn phát hành bản thử trong tháng 6.” | Lý do chọn mốc và ai quyết định khi phải đổi |
| **Cam kết thời hạn cố định (fixed-date commitment)** | Nghĩa vụ phải đáp ứng một mốc thời gian đã xác lập với các điều kiện cụ thể | “Bản dùng thử tối thiểu phải được cung cấp cho đối tác vào 30/06/2027.” | Kết quả bắt buộc, tiêu chí nghiệm thu, trách nhiệm, hệ quả khi không đạt và cách xử lý |

**Một ước lượng không tự là dự báo.** Cộng các ước lượng công việc rồi ghi ngày hoàn thành có thể bỏ sót thời gian chờ, phụ thuộc, năng lực thực tế, lỗi, tích hợp và sự thay đổi phạm vi.

**Một dự báo không tự là cam kết.** Dự báo có thể thay đổi mà vẫn trung thực khi điều kiện đầu vào thay đổi. Trách nhiệm ở đây là cung cấp căn cứ, cập nhật sớm và giải thích nguyên nhân.

**Một cam kết cũng không khiến bất định biến mất.** Nếu ngày phải giữ, nhóm phải chủ động lựa chọn phạm vi và cách làm khả thi hoặc thông báo rõ khi tổ hợp điều kiện hiện tại không thể bảo đảm.

### 3.1. Cam kết về điều gì?

Trong Scrum Guide, có ba **commitment** gắn với ba artifact:

- **Product Backlog → Product Goal:** cam kết về trạng thái tương lai của sản phẩm.
- **Sprint Backlog → Sprint Goal:** cam kết về mục tiêu duy nhất của Sprint.
- **Increment → Definition of Done:** cam kết về trạng thái chất lượng cần đạt để được coi là hoàn thành.

Đó **không phải** ba lời hứa rằng tất cả Product Backlog Item (PBI) sẽ xong vào một ngày cố định. **Sprint có timebox cố định**, tối đa một tháng, nhưng Sprint Goal khác với việc bắt buộc hoàn thành mọi hạng mục từng được chọn trong Sprint. Trong Sprint, Developers có thể cùng Product Owner làm rõ hoặc thương lượng phạm vi khi hiểu biết tăng, miễn không làm nguy hại Sprint Goal; chất lượng không được suy giảm.

Cam kết hợp đồng, cam kết với đối tác hoặc mốc pháp lý là **loại ràng buộc khác**, có thể tồn tại bên cạnh Scrum. Cần diễn đạt tường minh nghĩa vụ nào bắt buộc và ai có quyền thương lượng thay đổi.

## 4. Vì sao dự báo phần mềm có bất định?

Công việc phát triển phần mềm bao gồm nhiều hoạt động khám phá. Hai user story cùng được ước lượng “nhỏ” có thể hoàn thành rất khác nhau vì phụ thuộc dịch vụ ngoài, dữ liệu chưa được làm rõ, lỗi hồi quy hoặc thời gian chờ phản hồi nghiệp vụ.

Các nguồn bất định thường gặp:

| Nguồn | Biểu hiện | Việc có thể làm |
|---|---|---|
| **Độ rõ yêu cầu** | Người dùng hoặc bên liên quan còn hiểu khác nhau về hành vi | Làm rõ bằng ví dụ, acceptance criteria, thử nghiệm nhỏ |
| **Bất định kỹ thuật** | API, kiến trúc hoặc dữ liệu chưa được kiểm chứng | Spike giới hạn thời gian, kiểm thử tích hợp sớm |
| **Biến động năng lực** | Nghỉ phép, hỗ trợ sự cố, thành viên chuyển nhiệm vụ | Dự báo dựa trên năng lực thực tế, cập nhật khi thay đổi |
| **Phụ thuộc ngoài nhóm** | Chờ môi trường, dữ liệu, phê duyệt hoặc đơn vị tích hợp | Công khai phụ thuộc, người phụ trách, điểm phải có quyết định |
| **Chất lượng và làm lại** | Lỗi kiểm thử, yêu cầu sai, thay đổi kéo theo hồi quy | Definition of Done, tự động hóa kiểm thử phù hợp, CI |
| **Thay đổi phạm vi** | Thêm PBI, đổi yêu cầu hoặc phát hiện công việc còn thiếu | Giữ Product Backlog minh bạch, phân biệt việc thêm mới với dự báo cũ |
| **Độ lớn hạng mục** | Một PBI quá lớn, khó thấy tiến triển và khó dự báo | Chia theo lát cắt giá trị có thể hoàn tất |
| **Thời gian chờ và WIP** | Nhiều việc đang dở nhưng ít việc thật sự hoàn thành | Giới hạn WIP, tháo điểm tắc, ưu tiên hoàn tất |

Không phải mọi bất định đều có thể hoặc nên triệt tiêu trước khi bắt đầu. Agile tạo vòng phản hồi ngắn: làm rõ phần gần, giao Increment nhỏ, kiểm tra thực tế và **cập nhật dự báo khi có bằng chứng mới**.

### 4.1. Ba câu hỏi trước khi dự báo

1. **Phạm vi đang được dự báo là gì?** Bao nhiêu PBI, loại công việc nào, có còn hạng mục chưa khám phá hoặc yêu cầu đang tăng không?
2. **Năng lực và dòng công việc có đủ tương đồng với dữ liệu trước không?** Nhóm, công cụ, quy trình, loại việc và phụ thuộc có thay đổi đáng kể không?
3. **Mức bất định được trình bày thế nào?** Đây là điểm ước lượng, khoảng kịch bản hay xác suất đạt một mốc cụ thể?

Nếu không trả lời được, có thể bắt đầu bằng **dự báo thô kèm giả định**, nhưng không nên gắn một ngày chính xác để tạo cảm giác chắc chắn giả.

## 5. Lập kế hoạch thích ứng theo nhiều chân trời

Thay vì lập một kế hoạch chi tiết cứng nhắc cho toàn bộ dự án, nhóm có thể tăng mức chi tiết khi thời điểm thực hiện đến gần.

| Chân trời | Điều muốn hiểu | Mức chi tiết hợp lý | Nhịp cập nhật |
|---|---|---|---|
| **Product Goal/định hướng sản phẩm** | Kết quả dài hơn cần đạt cho người dùng | Mục tiêu, giả thuyết giá trị, rủi ro chính | Khi có bằng chứng hoặc thay đổi bối cảnh đáng kể |
| **Release/roadmap** | Khi nào có khả năng giao nhóm năng lực phục vụ một mục đích? | Các lát cắt, phụ thuộc, mốc quyết định và phạm vi tối thiểu | Khi throughput, phạm vi hoặc rủi ro thay đổi |
| **Sprint hoặc chu kỳ ngắn** | Trong vài ngày/tuần, nhóm cần đạt kết quả nào? | Mục tiêu cụ thể, PBI được chọn, kế hoạch thực hiện có thể sửa | Kiểm tra thường xuyên trong chu kỳ |
| **Ngày làm việc/luồng hiện tại** | Công việc nào đang nghẽn và ai cần phối hợp? | Việc đang làm, blocker, ưu tiên hoàn tất | Khi công việc và thông tin thay đổi |

Đây là ví dụ của **rolling-wave planning**: lập kế hoạch chi tiết cho phạm vi gần, giữ nhiều lựa chọn cho phạm vi xa còn bất định. Nó khác với “không lập kế hoạch”; thực tế nhóm phải liên tục so sánh mục tiêu với những gì đã học.

Nếu deadline không thể dời, mốc đó là **ràng buộc ở chân trời release**, nhưng nội dung các chu kỳ gần vẫn được điều chỉnh để giữ một kết quả tối thiểu đáng tin.

## 6. Các số đo dòng công việc hỗ trợ dự báo

Kanban cung cấp các phép đo giúp nhóm nhận biết công việc đi qua workflow như thế nào. Một định nghĩa nhất quán quan trọng hơn việc chọn tên cột “đúng chuẩn”.

| Phép đo | Ý nghĩa | Câu hỏi hỗ trợ |
|---|---|---|
| **Throughput** | Số hạng mục **hoàn thành** trong một khoảng thời gian | “Thông thường mỗi tuần nhóm hoàn tất được bao nhiêu hạng mục cùng loại?” |
| **Cycle time** | Thời gian từ khi một hạng mục **bắt đầu thực hiện** đến lúc hoàn thành, theo quy tắc nhóm | “Việc đã được bắt đầu thường cần bao lâu để đi hết luồng?” |
| **Work in Progress (WIP)** | Số hạng mục đã bắt đầu nhưng chưa hoàn thành | “Nhóm có đang mở quá nhiều việc so với năng lực hoàn tất?” |
| **Work item age** | Thời gian trôi qua từ khi bắt đầu đối với **hạng mục chưa hoàn thành** | “Việc nào đang già đi và có nguy cơ vượt mức thường thấy?” |
| **Lead time** | Thời gian từ một mốc yêu cầu/cam kết được nhóm định nghĩa đến hoàn thành | “Người yêu cầu phải chờ bao lâu từ lúc bắt đầu tính nhu cầu?” |

**Lưu ý:** định nghĩa lead time khác nhau theo tổ chức; có nơi tính từ khi yêu cầu được gửi, nơi khác tính từ lúc chấp nhận. Muốn so sánh, phải công bố điểm bắt đầu/kết thúc và giữ nhất quán.

Một PBI được chuyển vào “Done” chỉ để làm đẹp dashboard nhưng chưa đạt Definition of Done sẽ làm sai số liệu và gây dự báo lạc quan giả.

### 6.1. Ví dụ throughput đơn giản

Giả sử một nhóm đã hoàn thành số PBI tương đối đồng nhất ở sáu tuần gần nhất như sau:

| Tuần | Số PBI hoàn thành |
|---|---:|
| 1 | 8 |
| 2 | 10 |
| 3 | 9 |
| 4 | 11 |
| 5 | 7 |
| 6 | 10 |

Tổng cộng **55 PBI trong sáu tuần**, trung bình khoảng **9,2 PBI/tuần**. Nếu còn **38 PBI** có đặc điểm tương tự, một tính toán nhanh là:

\[
\frac{38}{9{,}2} \approx 4{,}1\ \text{tuần}.
\]

Khi xét mức throughput từng tuần đã quan sát là **7–11 PBI**, các kịch bản rất thô cho thấy khoảng **4–6 tuần** (làm tròn lên số tuần trọn). Đây là **khoảng kịch bản**, chưa phải khoảng tin cậy thống kê hay lời hứa “chắc chắn trong sáu tuần”.

Dự báo sẽ khác đi nếu 38 PBI có kích thước rất lớn, chưa tách được, phải chờ tích hợp hoặc trong đó có nhiều việc chưa biết. Nên ghi rõ **cơ sở tính và thời điểm chụp backlog** trước khi đưa kết quả ra quyết định.

### 6.2. Phân vị cycle time và Service Level Expectation

Giả sử 20 PBI đã hoàn thành có cycle time (ngày) sắp tăng:

~~~text
2, 3, 3, 4, 4, 5, 5, 5, 6, 6,
7, 7, 7, 8, 9, 9, 10, 12, 15, 19
~~~

Có **17/20 PBI (85%)** hoàn thành trong **10 ngày hoặc ít hơn**. Nhóm có thể xem “85% hạng mục tương tự hoàn tất trong vòng 10 ngày” là một **Service Level Expectation (SLE)** tham khảo nếu phép đo, loại việc và workflow vẫn phù hợp. SLE là dự báo về thời gian luồng với một mức xác suất/khả năng, không phải cam kết thời hạn cho từng PBI.

Ba hạng mục còn lại trong mẫu mất 12, 15 và 19 ngày. Một người dùng cần giao đúng ngày có thể rơi vào những trường hợp kéo dài này, đặc biệt nếu có rủi ro mới.

**Vì vậy:**

- Không diễn đạt P85 = 10 ngày thành “mọi PBI sẽ xong trước ngày thứ 10”.
- Không áp dụng phân vị của PBI nhỏ cho một epic lớn chưa được chia.
- Không áp dụng cycle time của **một PBI** để kết luận ngày hoàn tất **toàn bộ 38 PBI** mà không xem throughput, phụ thuộc và việc làm song song.
- Không coi mẫu 20 quan sát là bằng chứng đủ mạnh cho mọi thời điểm; cần xem xu hướng và tính đại diện.

SLE giúp đặt kỳ vọng, nhận diện work item age đáng chú ý và kích hoạt trao đổi trước khi công việc bị kẹt quá lâu.

## 7. Dự báo theo xác suất: từ khoảng kịch bản đến Monte Carlo

### 7.1. Khi nào dự báo định tính là đủ?

Khi backlog còn chưa rõ, dữ liệu quá ít hoặc loại việc khác biệt lớn, nhóm có thể bắt đầu bằng kịch bản:

| Kịch bản | Giả định | Cách trình bày |
|---|---|---|
| **Thuận lợi** | Ít lỗi tích hợp, không thêm phạm vi, throughput giữ ở mức cao gần đây | “Có thể đạt bản thử trong khoảng bốn tuần nếu các điều kiện này đúng.” |
| **Cơ sở** | Tốc độ tương tự dữ liệu đa số các tuần, một số việc cần làm rõ | “Nên chuẩn bị kế hoạch khoảng năm tuần và kiểm tra mỗi tuần.” |
| **Bất lợi** | Phụ thuộc kéo dài, nhiều lỗi hoặc yêu cầu tăng | “Có nguy cơ sáu tuần hoặc hơn; phải điều chỉnh phạm vi/nguồn lực nếu giữ ngày cố định.” |

Các kịch bản làm rõ điều kiện, **không tự gắn được xác suất đáng tin** nếu chưa có dữ liệu hoặc mô hình phù hợp.

### 7.2. Mô phỏng Monte Carlo hoạt động như thế nào?

Khi có lịch sử throughput đủ đại diện, mô phỏng Monte Carlo có thể tạo ra **phân phối các thời điểm hoàn thành** bằng cách lấy mẫu nhiều kịch bản tương lai từ dữ liệu hoặc một mô hình xác định trước.

Một cách khái niệm:

~~~text
Đầu vào:
  Số PBI còn lại, lịch sử throughput theo tuần,
  các điều kiện về phạm vi và năng lực nhóm.

Cho mỗi lần mô phỏng:
  remaining = số PBI còn lại
  weeks = 0
  Trong khi remaining > 0:
      Lấy mẫu throughput của một tuần từ dữ liệu/mô hình
      remaining -= throughput được lấy mẫu
      weeks += 1
  Ghi lại weeks

Lặp lại nhiều lần:
  Tổng hợp số tuần trong các kịch bản mô phỏng.
  Xem tỷ lệ kịch bản hoàn thành trước mốc cần quyết định.
~~~

Ví dụ cách diễn đạt kết quả **minh họa, không phải kết quả tính từ dữ liệu ở trên**:

> “Theo mô hình và giả định hiện tại, khoảng 70% các kịch bản mô phỏng hoàn thành phạm vi đã xác định trước ngày mục tiêu. Con số này chỉ có ý nghĩa với phạm vi, lịch sử và cách lấy mẫu đang dùng; nếu tăng phạm vi hoặc có phụ thuộc mới, chúng ta phải dự báo lại.”

Mô phỏng không xóa được bất định do thay đổi kiến trúc, yêu cầu mới, tương quan giữa các tuần hay các sự cố chưa xuất hiện trong dữ liệu. Dùng các kết quả xác suất để **chuẩn bị quyết định và phương án dự phòng**, không để gắn “bảo đảm 95%” khi giả định yếu.

### 7.3. Chọn mức tin cậy phù hợp với rủi ro

Một buổi demo nội bộ có thể chấp nhận mức bất định cao hơn một mốc chuyển dữ liệu không thể đảo ngược. Cần làm rõ **hậu quả nếu trễ hoặc giao thiếu**, người có quyền chấp nhận rủi ro và mức dư địa phù hợp.

Không có ngưỡng “85%” hay “95%” bắt buộc cho mọi nhóm. Mức tin cậy cần được thảo luận trong ngữ cảnh tác động, chi phí dự phòng và độ tin cậy của dữ liệu.

## 8. Làm thế nào để quản lý deadline thật sự cố định?

Một mốc cố định có thể đến từ hội nghị ra mắt, thời điểm hợp đồng, nghĩa vụ pháp lý, hạn chuyển đổi của hệ thống cũ hoặc lịch làm việc với đối tác. Khi không thể dời ngày, nhóm cần biến cam kết thành **kết quả cụ thể có thể xác nhận**, không chỉ là “toàn bộ backlog phải Done”.

### 8.1. Xác định phần không thể thương lượng

Một thỏa thuận phát hành cần làm rõ:

1. **Ngày và múi giờ:** ví dụ 30/06/2027 lúc 17:00 ICT, nếu thực sự được thống nhất.
2. **Kết quả tối thiểu phải có:** người dùng nào phải hoàn thành được luồng nào?
3. **Tiêu chí nghiệm thu:** điều kiện nghiệp vụ và bằng chứng kiểm chứng nào?
4. **Chuẩn chất lượng bắt buộc:** Definition of Done, bảo mật, an toàn dữ liệu, tuân thủ và khả năng vận hành.
5. **Phạm vi có thể thương lượng:** chức năng nào có thể hoãn, chia đợt hoặc thay bằng giải pháp tạm có kiểm soát?
6. **Phụ thuộc và người chịu trách nhiệm:** ai cần cung cấp API, dữ liệu, phê duyệt, môi trường hay thiết bị?
7. **Quyền quyết định và xử lý trượt hạn:** ai có quyền đổi phạm vi, điều chỉnh ngày, kích hoạt phương án dự phòng hoặc không phát hành?

Nếu cả **ngày, phạm vi lớn, nguồn lực và chất lượng** đều được coi là cố định trong khi dự báo cho thấy không khả thi, nhóm phải làm rõ mâu thuẫn thay vì biến nó thành áp lực âm thầm cho Developers.

### 8.2. Giữ ngày bằng cách quản lý phạm vi, không che trạng thái

Một cách làm thường phù hợp:

- **Must-have:** phần thực sự không thể thiếu để đạt kết quả cam kết và đáp ứng ràng buộc.
- **Should-have:** giá trị cao nhưng có thể giao sau mà luồng cốt lõi vẫn hữu ích.
- **Could-have:** cải tiến mong muốn nếu còn năng lực, không dựa vào chúng để xác nhận nghĩa vụ chính.
- **Không làm trong đợt này:** những ý tưởng chưa có bằng chứng, phụ thuộc cao hoặc không phục vụ mục tiêu gần.

Đây là cách phân nhóm ưu tiên có tính tham khảo, không phải thứ tự chính thức của Scrum. “Must-have” phải được kiểm tra bằng câu hỏi: **Nếu bỏ hạng mục này, người dùng còn hoàn thành mục tiêu tối thiểu không? Có vi phạm chuẩn an toàn hoặc ràng buộc đã cam kết không?**

Không được gọi một phần là “hoàn thành” nếu chưa đạt DoD. Nếu giải pháp tạm cần thiết, phải mô tả rõ phạm vi, giới hạn, rủi ro và việc còn phải hoàn tất.

### 8.3. Khi thật sự không thể đáp ứng

Nhóm nên chủ động đưa ra những lựa chọn cụ thể:

| Lựa chọn | Khi có thể cân nhắc | Đánh đổi/rủi ro |
|---|---|---|
| **Giảm hoặc tách phạm vi** | Có một luồng tối thiểu vẫn tạo giá trị và đáp ứng nghĩa vụ | Chức năng phụ giao sau, cần thông báo rõ |
| **Phát hành theo giai đoạn** | Có thể giới hạn nhóm người dùng hoặc khu vực mà không vi phạm điều kiện bắt buộc | Cần giám sát, khả năng quay lui và hỗ trợ |
| **Giải quyết phụ thuộc sớm** | Điểm tắc nằm ở môi trường, API hoặc quyết định bị chờ | Có thể cần phối hợp thêm các nhóm khác |
| **Điều chỉnh nguồn lực/cách phối hợp** | Có kỹ năng và công việc có thể chia hiệu quả | Thêm người có chi phí hòa nhập; không bảo đảm tốc độ tăng tuyến tính |
| **Đàm phán điều chỉnh thời hạn** | Người có thẩm quyền chấp nhận thay đổi ngày | Có thể ảnh hưởng hợp đồng hoặc kế hoạch bên liên quan |
| **Không phát hành khi chưa đạt điều kiện an toàn** | Có lỗi nghiêm trọng, mất dữ liệu hoặc rủi ro không thể chấp nhận | Cần kích hoạt kênh thông báo, phương án dự phòng và trách nhiệm phù hợp |

**Phương án không nên chọn:** đổi tên hạng mục thành Done, bỏ kiểm thử quan trọng, giấu lỗi hoặc yêu cầu làm thêm giờ kéo dài như cơ chế mặc định để bù cho mọi dự báo sai.

## 9. Tình huống xuyên suốt: ngày bàn giao cố định cho đối tác

### 9.1. Bối cảnh

Nhóm phát triển nền tảng học trực tuyến có mục tiêu sản phẩm: **người mới có thể đăng ký, mở bài và tiếp tục học mà không mất tiến độ**. Một đối tác đã đặt lịch nhận bản dùng thử vào **30/06/2027** (ngày ví dụ).

Danh sách triển khai đầy đủ hiện còn **38 PBI**. Dữ liệu throughput của sáu tuần trước là **8, 10, 9, 11, 7, 10 PBI/tuần**, nhưng PBI tương đối đồng nhất mới chỉ là một giả định cần kiểm tra. Vào thời điểm lập kế hoạch, còn **năm tuần** đến mốc bàn giao.

### 9.2. Dự báo phạm vi đầy đủ

Nếu dùng mức cao **11 PBI/tuần**, hoàn tất 38 việc cần ít nhất khoảng **bốn tuần**. Với mức thấp từng quan sát **7 PBI/tuần**, cần khoảng **sáu tuần**. Trung bình khoảng **9,2 PBI/tuần** gợi ý khoảng **năm tuần** khi làm tròn tuần.

Kết quả là:

> “Trong điều kiện giống lịch sử và không đổi phạm vi, toàn bộ 38 PBI có thể cần khoảng 4–6 tuần. Vì mốc bàn giao còn năm tuần, **khả năng hoàn tất toàn bộ phạm vi chưa đủ chắc chắn**. Dự báo phải cập nhật khi làm rõ các PBI chưa biết và dữ liệu tiến độ tiếp theo.”

Đây vẫn chỉ là phép nhìn nhanh từ throughput, **không phải phân phối xác suất có kiểm chứng**. Nếu một số PBI lớn bất thường hoặc chứa phụ thuộc chưa giải quyết, nguy cơ cao hơn.

### 9.3. Thỏa thuận lại nội dung tối thiểu

Product Owner, Developers và các bên liên quan xác định bản bàn giao phải có:

- **Luồng đăng ký và đăng nhập** hoạt động đúng cho nhóm người dùng thử.
- **Luồng mở bài đầu tiên và lưu tiến độ** sử dụng được trên thiết bị mục tiêu.
- **Hành vi khi lỗi mạng/lưu tiến độ** được kiểm soát, không tuyên bố lưu thành công khi chưa có kết quả.
- **Kiểm thử, quyền truy cập, an toàn dữ liệu và khả năng hỗ trợ** theo chuẩn áp dụng.
- **Hướng dẫn sử dụng và kênh hỗ trợ** cho đối tác trong phạm vi dùng thử.

Sau khi chia nhỏ và thương lượng, giả sử phần tối thiểu tương đương **24 PBI** có đặc tính tương đối giống công việc trước. Các chức năng như bảng xếp hạng, chủ đề giao diện bổ sung hoặc báo cáo phân tích nâng cao được chuyển sang đợt sau.

Với throughput **7–11 PBI/tuần**, 24 PBI có thể cần khoảng **3–4 tuần** trong kịch bản đơn giản, tạo thêm dư địa trong năm tuần còn lại. Điều này **giảm áp lực theo giả định hiện có nhưng không bảo đảm deadline**: việc còn có thể phát sinh lỗi, phụ thuộc, yêu cầu hợp đồng hoặc công việc chưa khám phá.

### 9.4. Lập bảng điều kiện và quyết định

| Điểm kiểm tra | Bằng chứng cần xem | Quyết định có thể kích hoạt |
|---|---|---|
| Sau tuần 1 | Số PBI đạt DoD, lỗi tích hợp, phụ thuộc hệ thống lưu tiến độ | Điều chỉnh dự báo, sớm tách chức năng phụ |
| Sau tuần 2 | Luồng đăng nhập → mở bài → lưu tiến độ có chạy đầu–cuối không? | Ưu tiên chốt lát cắt cốt lõi, giảm việc mở mới |
| Sau tuần 3 | Kiểm thử hồi quy, work item age, lỗi nghiêm trọng, khả năng vận hành thử | Kích hoạt phương án phát hành giới hạn nếu phù hợp |
| Trước ngày bàn giao | Bằng chứng nghiệm thu, trạng thái triển khai, hỗ trợ và phương án quay lui | Quyết định có đủ điều kiện phát hành, hoặc báo và xử lý không đạt |

Các điểm kiểm tra là **mốc ra quyết định**, không phải lời hứa rằng cứ hết tuần là tất cả việc của tuần đó đã xong. Nhóm có thể cập nhật chúng theo thông tin mới, nhưng phải giữ tính minh bạch của nghĩa vụ với đối tác.

### 9.5. Mẫu báo cáo dự báo cho bên liên quan

~~~text
Mục tiêu: Bản thử đăng ký -> mở bài -> lưu tiến độ
Deadline bên ngoài: 30/06/2027 (ví dụ)
Phạm vi bắt buộc: 24 PBI đã được làm rõ cùng các điều kiện nghiệm thu
Phạm vi hoãn: 14 PBI còn lại của kế hoạch đầy đủ
Dữ liệu dự báo: throughput 6 tuần gần nhất = 8, 10, 9, 11, 7, 10
Nhận định hiện tại: phần tối thiểu có kịch bản hoàn thành khoảng 3-4 tuần
Điều kiện: backlog ổn định, loại việc tương tự, phụ thuộc không trễ lớn
Rủi ro lớn: tích hợp lưu tiến độ, kiểm thử dữ liệu khi mất kết nối
Tín hiệu phải xem: throughput, tuổi việc mở, lỗi nghiêm trọng, luồng đầu-cuối
Mốc xem lại: cuối tuần tiếp theo và ngay khi giả định thay đổi
Người quyết định phạm vi sản phẩm: Product Owner theo trách nhiệm Scrum
Phê duyệt phát hành/rủi ro: theo chính sách và thẩm quyền thực tế
Phương án dự phòng: giới hạn nhóm dùng thử hoặc thương lượng với đối tác
~~~

Mẫu minh họa không tự tạo thẩm quyền cho Product Owner đối với hợp đồng hoặc rủi ro an toàn. Vai trò ký kết, nghiệm thu và phê duyệt phát hành cần theo thực tế tổ chức.

### 9.6. Sau khi phát hành, còn phải kiểm chứng giá trị

Đạt ngày bàn giao chỉ cho biết một mốc đã được đáp ứng. Nhóm vẫn phải xem liệu người học **mở bài, hoàn thành bài và giữ được tiến độ** có ổn định không. Một Increment chạy đúng theo acceptance criteria và DoD là điều kiện cần, nhưng **không tự chứng minh Product Goal đã đạt**.

Nhờ phản hồi sớm, Product Backlog có thể thay đổi thứ tự: nếu người dùng vướng ở việc chọn bài, ưu tiên trải nghiệm khởi đầu; nếu nhiều lỗi lưu tiến độ, sửa chất lượng trước khi thêm báo cáo nâng cao.

## 10. Scrum, Kanban và XP hỗ trợ quản lý dự báo như thế nào?

### 10.1. Scrum: thời gian Sprint cố định, kế hoạch có thể điều chỉnh

Trong Scrum:

- **Product Owner** chịu trách nhiệm tối đa hóa giá trị và quản lý hiệu quả Product Backlog.
- **Developers** tạo và điều chỉnh kế hoạch Sprint Backlog, chịu trách nhiệm chất lượng theo Definition of Done.
- **Sprint Planning** hình thành Sprint Goal, chọn PBI và lập kế hoạch; không tự biến mọi ước lượng PBI thành lời bảo đảm hoàn thành.
- **Daily Scrum** kiểm tra tiến độ tới Sprint Goal và điều chỉnh kế hoạch trong ngày.
- **Sprint Review** kiểm tra Increment và bối cảnh mới, làm đầu vào cho việc thích ứng Product Backlog.
- **Sprint Retrospective** giúp cải thiện quy trình, gồm cách làm rõ và dự báo công việc.

Sprint có thời lượng cố định, **không quá một tháng**. Nếu Sprint Goal trở nên lỗi thời, Product Owner có thể hủy Sprint; đây không phải công cụ thông thường để “giải quyết” dự báo trễ vài PBI.

**Velocity**, nếu nhóm dùng, có thể giúp dự báo năng lực của **chính nhóm đó** dựa trên cách ước lượng nhất quán. Story point không phải giờ công chuẩn, cũng không dùng để so sánh năng suất giữa các nhóm hoặc áp chỉ tiêu velocity phải tăng đều. Khi cách chia story thay đổi, dự báo từ lịch sử cũ phải được xem lại.

### 10.2. Kanban: dự báo từ luồng và dấu hiệu trễ sớm

Kanban tập trung quản lý luồng công việc. **Throughput** có ích cho câu hỏi “Bao nhiêu việc có khả năng hoàn thành trong thời hạn?”, còn **cycle time/SLE** cho câu hỏi “Một hạng mục đã bắt đầu thường mất bao lâu?”. **Work item age** giúp phát hiện một việc đang đi chậm hơn lịch sử trong khi vẫn chưa Done.

Giới hạn **WIP** giúp nhóm ưu tiên hoàn tất việc đang dở, giảm chuyển ngữ cảnh và làm điểm tắc hiển thị. Điều chỉnh WIP, phân loại công việc và chính sách khẩn cần dựa trên quan sát, không chỉ vì muốn làm các biểu đồ đẹp hơn.

Nếu áp dụng **lớp dịch vụ có ngày cố định (fixed-date class of service)** trong một hệ thống Kanban, nhóm có thể dành quy tắc xử lý đặc biệt cho việc phải hoàn thành trước mốc đã biết. Cách tổ chức này **không xóa rủi ro**, và không thể thay thế việc đàm phán phạm vi, phụ thuộc và điều kiện nghiệm thu.

### 10.3. XP: giảm bất định kỹ thuật để dự báo đáng tin hơn

Một kế hoạch có vẻ khả thi có thể trễ mạnh nếu tích hợp cuối kỳ mới phát hiện lỗi. Các thực hành **Extreme Programming (XP)** như kiểm thử tự động, TDD khi phù hợp, tích hợp liên tục, refactoring và cộng tác kỹ thuật giúp:

- Phát hiện sớm khác biệt giữa hành vi mong muốn và sản phẩm chạy thật.
- Giao lát cắt tích hợp thường xuyên thay vì chờ gộp cuối giai đoạn.
- Giảm chi phí làm lại do lỗi hồi quy.
- Thay đổi phạm vi an toàn hơn khi bằng chứng mới xuất hiện.

Những thực hành này hỗ trợ dự báo bằng cách **giảm biến động và rủi ro kỹ thuật**, không bảo đảm rằng mọi yêu cầu sẽ hoàn thành đúng ngày bất kể độ phức tạp.

## 11. Giao tiếp dự báo và rủi ro mà không tạo cam kết giả

### 11.1. Câu trả lời nên có cấu trúc

Khi bên liên quan hỏi “Có kịp không?”, nên trả lời với bốn phần:

1. **Phạm vi:** chúng ta đang nói tới phần sản phẩm nào và tiêu chí hoàn thành nào?
2. **Dự báo hiện tại:** ngày hoặc khoảng thời gian, nếu có dữ liệu thì thêm mức tin cậy và cách tính.
3. **Giả định/rủi ro:** điều gì phải đúng; yếu tố nào có thể làm thay đổi kết quả?
4. **Hành động và thời điểm cập nhật:** nhóm đang giảm bất định như thế nào và khi nào bên liên quan có thông tin mới?

Ví dụ cách trình bày:

> “Đối với luồng đăng ký và lưu tiến độ đã chốt, dự báo hiện tại là ba đến bốn tuần theo throughput của sáu tuần gần nhất. Mốc đối tác là năm tuần nữa. Rủi ro lớn nhất là tích hợp lưu tiến độ trên mạng không ổn định; nhóm sẽ kiểm thử đầu–cuối trong tuần này và cập nhật dự báo sau đó. Các phần báo cáo nâng cao đã được để sang đợt sau.”

Cách diễn đạt này hữu ích hơn cả “chắc chắn kịp” khi chưa có căn cứ lẫn “không thể biết” khi thực ra nhóm có dữ liệu để dự báo có điều kiện.

### 11.2. Khi dự báo thay đổi, cần thông báo điều gì?

| Nội dung | Ví dụ báo cáo |
|---|---|
| **Điều đã thay đổi** | Phát hiện phụ thuộc API mới hoặc ước lượng sai độ phức tạp lưu tiến độ |
| **Tác động** | Dự báo phạm vi đầy đủ dịch từ 4–6 sang 5–7 tuần theo giả định mới |
| **Ảnh hưởng cam kết** | Mốc đối tác còn năm tuần nên cần giảm phạm vi hoặc thương lượng |
| **Lựa chọn** | Bàn giao luồng cốt lõi, phát hành giới hạn hoặc đổi mốc theo thẩm quyền |
| **Quyết định và người chịu trách nhiệm** | Product Owner/bên có thẩm quyền chốt phạm vi, nhóm cập nhật kế hoạch |
| **Điểm xem lại** | Sau kiểm thử tích hợp và cập nhật số liệu luồng tuần tới |

**Trách nhiệm không phải giữ nguyên con số dự báo cũ.** Trách nhiệm là làm rõ điều gì đã thay đổi, vì sao và quyết định nào cần đưa ra.

### 11.3. Không tạo áp lực để dữ liệu trông tốt

Những hành vi có thể làm sai dự báo:

- Chuyển PBI sang Done dù chưa đạt Definition of Done.
- Chia ticket chỉ để throughput trông tăng, không giữ tính tương đồng loại việc.
- Tăng điểm ước lượng để velocity cao hơn mà không thay đổi giá trị hay năng lực.
- Loại khỏi báo cáo những PBI bị chặn hoặc lỗi khó.
- Dùng trung bình một vài Sprint tốt nhất rồi bỏ qua tuần có sự cố.
- Gắn xác suất 90% khi chưa nêu mô hình, dữ liệu và giả định.
- Đổi định nghĩa “bắt đầu”, “hoàn thành” giữa các kỳ mà vẫn so sánh như cũ.

Số liệu chỉ giúp lập kế hoạch tốt khi **trung thực về cách ghi nhận**.

## 12. Những ngộ nhận phổ biến

| Ngộ nhận | Hệ quả | Cách hiểu phù hợp |
|---|---|---|
| “Agile là không cam kết deadline.” | Các bên không có cơ sở phối hợp với sự kiện/hợp đồng thực | Vẫn có thể quản lý deadline, nhưng cần xác định kết quả tối thiểu và đánh đổi |
| “Có deadline thì dự báo không còn cần thiết.” | Rủi ro bị che đến sát ngày | Dùng forecast để cập nhật khả năng đáp ứng cam kết |
| “Estimate 5 ngày tức là chắc chắn xong sau 5 ngày.” | Nhầm ước lượng với kết quả tương lai | Nêu giả định, biến động, thời gian chờ và phụ thuộc |
| “Sprint kết thúc cố định nên mọi PBI phải hoàn thành.” | Hạ chất lượng hoặc báo cáo sai Done | Bảo vệ Sprint Goal, điều chỉnh phạm vi khi cần, giữ DoD |
| “Velocity càng tăng thì ngày hoàn thành càng chắc chắn.” | Động cơ tăng điểm ước lượng, bỏ qua outcome | Dùng velocity trong bối cảnh nhóm, xem chất lượng và năng lực thực |
| “P85 cycle time nghĩa là 100% việc xong ở mốc đó.” | Tạo cam kết không có căn cứ | P85 là mức quan sát/phân vị, vẫn có việc vượt mốc |
| “Monte Carlo cho ra ngày chính xác tuyệt đối.” | Quên giả định về dữ liệu, biến động và phạm vi | Diễn giải như phân phối kịch bản có điều kiện |
| “Thêm người vào cuối dự án là lập tức tăng tốc tương ứng.” | Chi phí phối hợp, hòa nhập và lỗi có thể tăng | Chỉ thêm nguồn lực khi công việc chia được và lợi ích khả thi |
| “Để kịp ngày có thể bỏ kiểm thử.” | Lỗi sản phẩm và rủi ro sau phát hành tăng | Điều chỉnh phạm vi/ngày và giữ chuẩn chất lượng bắt buộc |
| “Báo rủi ro là thể hiện không cam kết.” | Nhóm giấu vấn đề, giảm cơ hội xử lý sớm | Báo rủi ro có căn cứ là hành vi có trách nhiệm |
| “Phạm vi đã đưa vào roadmap thì không được đổi.” | Đầu tư vào tính năng ít giá trị khi bối cảnh đổi | Ưu tiên lại backlog theo phản hồi và nghĩa vụ thực |

## 13. Bộ câu hỏi cho một buổi lập kế hoạch phát hành

Trước khi công bố ngày, Product Owner, Developers và các bên liên quan có thể cùng làm rõ:

### Về mục tiêu và phạm vi

- **Product Goal** hoặc kết quả người dùng nào mà bản phát hành cần phục vụ?
- Những luồng sử dụng **bắt buộc** và acceptance criteria là gì?
- Hạng mục nào là lựa chọn thêm nếu còn thời gian?
- Có giả định nghiệp vụ nào cần kiểm chứng trước khi chốt phạm vi không?

### Về dữ liệu và rủi ro

- Lịch sử throughput/cycle time có đại diện cho công việc sắp tới không?
- Có bao nhiêu PBI chưa được chia nhỏ hoặc chưa rõ phụ thuộc?
- Những hạng mục đang bị chặn hoặc già bất thường là gì?
- Phạm vi mới có bao gồm bảo mật, dữ liệu, vận hành và kiểm thử chưa?

### Về cam kết và lựa chọn

- Ngày là **mục tiêu nội bộ** hay **nghĩa vụ cố định**?
- Ai có quyền đổi ngày, phạm vi và ra quyết định phát hành?
- Phải có bằng chứng nào để gọi bản phát hành là hoàn thành?
- Nếu dự báo cho thấy nguy cơ trễ, phần nào có thể hoãn và khi nào cần quyết định?
- Khi nào cập nhật dự báo, ai nhận thông tin và ở đâu tìm được lịch sử?

Không nhất thiết cần một cuộc họp dài cho mọi câu hỏi. Có thể chuẩn bị dữ liệu bất đồng bộ, tập trung hội thoại vào những điểm chưa rõ rồi ghi lại quyết định.

## 14. Bài tập vận dụng

### Bài tập 1 — Phân biệt lời nói

Xác định mỗi phát biểu sau là **estimate**, **forecast**, **target** hay **fixed-date commitment**; nêu thông tin còn thiếu:

1. “Dựa trên 8 tuần gần đây, phần backlog này có khả năng mất 5–7 tuần nếu không thêm yêu cầu.”
2. “Tích hợp API có vẻ cần khoảng 3 ngày sau khi nhận tài liệu đầy đủ.”
3. “Chúng ta muốn công bố bản thử trong tháng 8.”
4. “Hợp đồng yêu cầu bàn giao luồng tra cứu đơn trước 17:00 ngày 15/09/2027.”
5. “Tôi hứa 100% mọi PBI sẽ xong trong Sprint vì Sprint chỉ có hai tuần.”

**Gợi ý:** (1) là forecast cần mức bất định và giả định; (2) estimate; (3) target; (4) fixed-date commitment cần làm rõ tiêu chí nghiệm thu, múi giờ và thẩm quyền; (5) là khẳng định thiếu căn cứ, đồng thời hiểu sai commitment của Scrum.

### Bài tập 2 — Dự báo từ throughput

Nhóm có throughput sáu tuần là **8, 10, 9, 11, 7, 10** hạng mục/tuần và còn **38** hạng mục tương tự.

1. Tính tổng throughput và giá trị trung bình mỗi tuần.
2. Tính kịch bản thời gian từ mức **7** và **11** hạng mục/tuần, làm tròn lên tuần.
3. Giải thích vì sao khoảng thời gian này **chưa phải xác suất đạt deadline**.
4. Nếu chỉ còn năm tuần, đề xuất **hai biện pháp** giảm rủi ro mà không hạ Definition of Done.

**Gợi ý:** tổng 55, trung bình khoảng 9,2/tuần. Kịch bản thô là **4–6 tuần**. Cần kiểm tra kích thước việc, phạm vi, phụ thuộc, lỗi, dữ liệu lịch sử và có thể tách một lát cắt tối thiểu.

### Bài tập 3 — Đọc Service Level Expectation

Trong 20 hạng mục hoàn thành, có 17 hạng mục mất **10 ngày hoặc ít hơn** kể từ khi bắt đầu; ba việc còn lại mất nhiều hơn.

1. Tỷ lệ quan sát trong 10 ngày là bao nhiêu?
2. Vì sao nhóm không thể hứa mọi việc đều xong trong 10 ngày?
3. Một PBI đang mở 13 ngày cho thấy điều gì cần kiểm tra?
4. Nếu workflow thay đổi mạnh, cần làm gì với SLE cũ?

**Gợi ý:** 85%; đây là tín hiệu dự báo theo mẫu quan sát, không phải thời hạn bảo đảm. Work item age 13 ngày cần được xem blocker/phụ thuộc; SLE phải được xem lại khi dữ liệu không còn đại diện.

### Bài tập 4 — Đàm phán mốc bàn giao cố định

Một đối tác yêu cầu bản dùng thử vào ngày đã ký hợp đồng. Nhóm dự báo cần **6–8 tuần** để hoàn thành toàn bộ chức năng, trong khi chỉ còn **5 tuần**.

Hãy viết một phương án thương lượng gồm:

- **Luồng tối thiểu** thật sự cần giao và bằng chứng nghiệm thu.
- Những chức năng có thể hoãn hoặc chia đợt.
- Những ràng buộc bảo mật, dữ liệu và chất lượng không được bỏ qua.
- Hai rủi ro lớn và cách giảm bất định trong tuần đầu.
- Mốc kiểm tra tiếp theo, người cần quyết định và cách thông báo nguy cơ trượt.

**Gợi ý:** không tự khẳng định “thêm người sẽ kịp”; cần nêu tác động và năng lực thực tế. Nếu hợp đồng không cho điều chỉnh phạm vi, việc thương lượng phải do bên có thẩm quyền thực hiện.

### Bài tập 5 — Sửa báo cáo làm sai lệch cam kết

Một nhóm báo cáo: “Sprint đã đạt 60 story point, nên chắc chắn bàn giao đúng ngày.” Nhưng một số PBI chưa đạt DoD, nhiều lỗi tích hợp chưa được giải quyết và cả hai tuần gần nhất đều có việc phát sinh ngoài kế hoạch.

**Yêu cầu:** chỉ ra ít nhất **bốn thiếu sót** của kết luận; viết lại báo cáo ngắn có **phạm vi, dữ liệu, bất định, rủi ro và hành động cập nhật**.

**Gợi ý:** story point không tự đo outcome hay thời gian hoàn tất; PBI chưa đạt DoD không thể coi là Increment hoàn thành; việc phát sinh và lỗi tích hợp phải được tính vào dự báo.

### Bài tập 6 — Lập thẻ dự báo cho dự án của bạn

Điền mẫu sau bằng một dự án thực tế:

~~~text
Product Goal / kết quả người dùng:
Ngày cần giao và tính chất ngày (target / fixed commitment):
Phạm vi tối thiểu và acceptance criteria:
Định nghĩa hoàn thành / Definition of Done:
Hạng mục còn lại và mức độ đồng nhất của chúng:
Dữ liệu throughput / cycle time hoặc lý do chưa có dữ liệu:
Dự báo hiện tại (khoảng, xác suất nếu có căn cứ):
Các giả định của dự báo:
Ba rủi ro/phụ thuộc quan trọng nhất:
Phạm vi có thể thương lượng:
Phương án dự phòng:
Người quyết định và người cần được thông báo:
Ngày/điểm kiểm tra tiếp theo:
Bằng chứng giúp cập nhật dự báo:
~~~

**Tự đánh giá:** một người chưa tham gia dự án có phân biệt được **điều nhóm dự kiến**, **điều nhóm đã thực sự cam kết**, **điều kiện để giữ cam kết** và **việc cần làm khi dự báo đổi** hay không?

## 15. Tổng kết

Trong Agile, lập kế hoạch không phải dự đoán chính xác tương lai rồi không được đổi. Nhóm sử dụng **phản hồi sớm, sản phẩm giao tăng dần và dữ liệu luồng công việc** để cải thiện quyết định dưới sự bất định.

Ghi nhớ các điểm sau:

1. **Estimate** mô tả quy mô hoặc nỗ lực dự kiến; **forecast** mô tả kết quả tương lai có điều kiện; **target** là mốc mong muốn; **fixed-date commitment** là ràng buộc cần quản lý và đáp ứng theo điều kiện đã thống nhất.
2. **Scrum có cam kết về Product Goal, Sprint Goal và Definition of Done**; một Sprint có thời lượng cố định không có nghĩa mọi PBI ban đầu đều được hứa chắc chắn sẽ hoàn thành.
3. **Throughput, cycle time, WIP, work item age và SLE** giúp nhóm nhìn vào lịch sử thật; mô phỏng Monte Carlo có thể bổ sung phân phối kịch bản khi dữ liệu và giả định phù hợp.
4. **Deadline cố định cần phạm vi tối thiểu rõ, tiêu chí nghiệm thu, chuẩn chất lượng, người có thẩm quyền và phương án dự phòng.** Nếu điều kiện không khả thi, báo sớm và thương lượng có căn cứ.
5. **Scrum hỗ trợ kiểm tra và thích ứng theo nhịp, Kanban hỗ trợ dự báo luồng, XP giảm rủi ro thay đổi kỹ thuật.** Không phương pháp nào biến bất định thành lời hứa tuyệt đối.
6. **Cập nhật dự báo là một hành động có trách nhiệm** khi bối cảnh hoặc bằng chứng đổi. Điều nguy hiểm là giữ nguyên con số cũ rồi che đi vấn đề.

> **Câu hỏi ghi nhớ:** “Mốc này là điều chúng ta *muốn đạt*, điều chúng ta *dự báo có thể đạt*, hay điều chúng ta *đã cam kết phải đáp ứng* — và bằng chứng nào đủ để phân biệt ba điều đó?”

### Tài liệu tham khảo

- [Manifesto for Agile Software Development](https://agilemanifesto.org/) và [12 Principles](https://agilemanifesto.org/principles.html) — phản hồi sớm, giao giá trị tăng dần, thích ứng và nhịp phát triển bền vững.
- [The Scrum Guide](https://scrumguides.org/scrum-guide.html) — Product Goal, Sprint Goal, Definition of Done, Sprint timebox và kiểm tra/thích ứng.
- [The Kanban Guide](https://kanbanguides.org/) — throughput, cycle time, work item age, WIP và Service Level Expectation.
- [Agile Alliance — Extreme Programming](https://agilealliance.org/glossary/xp/) — thực hành kỹ thuật giúp tích hợp thường xuyên, kiểm thử và thay đổi an toàn.
