# Biểu diễn khả năng hoàn thành bằng khoảng cùng xác suất dự báo

Một nhóm đang phát triển tính năng “Học tiếp” cho nền tảng học trực tuyến. Bên liên quan hỏi: “Bao giờ tính năng hoàn thành?”. Nếu câu trả lời chỉ là “ngày thứ Sáu tuần sau”, người nghe dễ hiểu đó là một lời hứa chắc chắn, dù nhóm còn phải xử lý đồng bộ tiến độ giữa thiết bị và chưa biết có bao nhiêu lỗi tích hợp. Ngược lại, trả lời “không thể biết được” cũng không giúp Product Owner lựa chọn phạm vi, mức rủi ro hay thời điểm ra mắt.

**Dự báo theo xác suất** đưa ra một cách trao đổi hữu ích hơn: “Với phạm vi và điều kiện hiện tại, mô hình của nhóm ước tính khoảng 85% khả năng hoàn thành trước cuối tuần thứ tư; để đạt mức tin cậy khoảng 95%, cần tính đến tuần thứ năm”. Câu trả lời như vậy **không hứa chắc kết quả**, nhưng làm rõ mức bất định và giúp mọi người đưa ra quyết định có trách nhiệm.

Bài thuộc chương **Ước lượng và dự báo** của module **AGILE_DEVELOPMENT**. Tinh thần Agile là giao giá trị tăng dần, nhận phản hồi sớm và thích ứng với điều mới học được. Vì vậy, dự báo cần hỗ trợ quản lý Product Backlog, lập kế hoạch với Scrum, đo dòng công việc theo Kanban, sử dụng phản hồi kỹ thuật từ XP và cải tiến liên tục — thay vì chỉ tạo một ngày kết thúc có vẻ chính xác.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Phân biệt **ước lượng**, **dự báo xác suất**, **cam kết** và **mục tiêu kinh doanh**.
2. Diễn đạt dự báo bằng **xác suất hoàn thành trước một mốc thời gian**, **mốc theo phân vị (percentile)** hoặc **khoảng thời gian đi kèm xác suất**.
3. Hiểu cách dữ liệu throughput, cycle time, WIP, khối lượng việc còn lại và độ biến thiên ảnh hưởng dự báo.
4. Giải thích nguyên tắc mô phỏng Monte Carlo và tự đọc một bảng kết quả dự báo.
5. Tránh nhầm **khoảng dự báo** với **khoảng tin cậy của tham số thống kê** hoặc lời bảo đảm không có rủi ro.
6. Cập nhật dự báo khi phạm vi, năng lực, chất lượng và bằng chứng thay đổi; biết khi nào không nên tin vào mô hình.
7. Trình bày dự báo cho Product Owner và các bên liên quan theo cách hỗ trợ quyết định về phạm vi, thời gian, rủi ro và giá trị sản phẩm.

## 2. Ước lượng, dự báo và cam kết là ba việc khác nhau

| Khái niệm | Câu hỏi chính | Ví dụ | Cạm bẫy |
| --- | --- | --- | --- |
| **Ước lượng (estimate)** | Công việc này có thể tốn bao nhiêu công sức, thời gian hoặc độ phức tạp? | “Story đồng bộ tiến độ có nhiều bất định hơn story hiển thị nút.” | Nghĩ một con số ước lượng là sự thật đã biết |
| **Dự báo (forecast)** | Với dữ liệu và giả định hiện tại, khi nào hoặc với xác suất nào kết quả sẽ xảy ra? | “Có khoảng 80% khả năng hoàn tất 12 mục còn lại trong 5–7 tuần, tùy phân bố thực tế.” | Chỉ đưa một ngày không kèm điều kiện và mức bất định |
| **Mục tiêu (target)** | Tổ chức muốn đạt kết quả vào mốc nào? | “Cần thử với học viên trước chiến dịch tuyển sinh.” | Dùng ngày mong muốn thay cho bằng chứng năng lực |
| **Cam kết (commitment)** | Chúng ta sẽ chịu trách nhiệm thực hiện hoặc bảo đảm điều gì trong ranh giới đã thống nhất? | “Nhóm cam kết minh bạch tiến độ, bảo vệ Definition of Done và báo sớm khi dự báo thay đổi.” | Biến dự báo 80% thành lời bảo đảm 100% |

Ước lượng có thể là **đầu vào** của dự báo, nhưng không phải mọi dự báo đều cần ước lượng từng story. Chẳng hạn, khi nhóm có lịch sử hoàn thành nhiều mục có kích thước tương đối nhất quán, có thể dùng **throughput thực tế** để dự báo số mục có thể hoàn tất mà không cộng story point.

Cam kết cũng không biến mất trong Agile: nhóm vẫn cần trách nhiệm với chất lượng, minh bạch và các thỏa thuận áp dụng. Tuy nhiên, **cam kết về cách quản lý rủi ro** khác với **khẳng định chắc chắn một ngày hoàn thành** trước khi có bằng chứng đủ mạnh.

### Một câu trả lời tốt thường gồm bốn phần

> “Với **12 backlog item được xác định tại thời điểm dự báo**, dựa trên **dòng công việc của nhóm trong giai đoạn gần đây**, chúng tôi ước tính **80% khả năng hoàn tất trước mốc X**. Dự báo sẽ thay đổi nếu **phạm vi tăng, phụ thuộc kéo dài hoặc năng lực nhóm thay đổi**. Chúng tôi sẽ kiểm tra lại sau mỗi tuần hoặc khi có sự kiện quan trọng.”

Con số 80% trong ví dụ chỉ minh họa cách diễn đạt, không phải kết quả tính toán của một dự án cụ thể.

## 3. Biểu diễn khả năng hoàn thành bằng xác suất

Giả sử ta định nghĩa:

- **T**: số tuần cần để hoàn tất toàn bộ phạm vi đang xét, tính từ thời điểm dự báo.
- **d**: số tuần hoặc một hạn chót được quan tâm.
- **p**: mức xác suất mong muốn, chẳng hạn 0,50; 0,85; 0,95.

Khi đó:

\[
P(T \le d)
\]

là **xác suất mô hình dự báo công việc được hoàn tất không muộn hơn mốc d**, với điều kiện các giả định của mô hình phù hợp thực tế. Đây thường là cách trực tiếp nhất để trả lời câu hỏi: “Nếu phải hoàn thành trước ngày này thì chúng ta có bao nhiêu khả năng?”.

### Ba cách trình bày chính

| Dạng trình bày | Câu hỏi | Cách hiểu |
| --- | --- | --- |
| **Xác suất theo hạn chót** | “Đến hết tuần thứ tư, khả năng hoàn thành là bao nhiêu?” | “Mô hình cho 90% xác suất hoàn tất không muộn hơn tuần 4.” |
| **Mốc thời gian theo phân vị** | “Khi nào đạt mức tin cậy 85%?” | “Mốc P85 là cuối tuần 4: khoảng 85% kịch bản hoàn tất vào hoặc trước đó.” |
| **Khoảng thời gian kèm xác suất** | “Khả năng hoàn thành nằm trong khoảng tuần 3–5 là bao nhiêu?” | “Có x% kịch bản hoàn tất trong khoảng đó, theo mô hình đã chọn.” |

**Phân vị P85 (85th percentile)** là mốc thời gian mà xác suất hoàn thành **vào hoặc trước** mốc ấy đạt ít nhất khoảng 85%. P85 **không** có nghĩa 85% chức năng đã được xây xong, và cũng **không** nói rằng sau mốc ấy nhóm chắc chắn hoàn tất.

### Phân vị và độ dài công việc là hai trục khác nhau

Một dự báo có thể nói: “P50 ở tuần 3, P85 ở tuần 4, P95 ở tuần 5”. Nghĩa là:

- Có ít nhất khoảng 50% khả năng hoàn tất vào hoặc trước tuần 3.
- Có ít nhất khoảng 85% khả năng hoàn tất vào hoặc trước tuần 4.
- Có ít nhất khoảng 95% khả năng hoàn tất vào hoặc trước tuần 5.

**Các giá trị này là mốc của phân bố thời gian**, không phải ba lịch triển khai khác nhau. Độ tin cậy mong muốn càng cao, mốc thời gian cần chừa thường càng xa.

## 4. Trước khi tính xác suất, phải định nghĩa thế nào là “hoàn thành”

Nếu các bên dùng từ “xong” theo nghĩa khác nhau, mô hình dự báo chính xác đến đâu cũng sẽ gây hiểu nhầm.

| Mốc hoàn thành | Điều thực sự được xác nhận | Ví dụ |
| --- | --- | --- |
| **Task kỹ thuật Done** | Một phần việc kỹ thuật đáp ứng điều kiện nội bộ | API lưu tiến độ đã kiểm thử |
| **User story đạt Done** | Một hành vi người dùng/nghiệp vụ hoàn chỉnh đáp ứng Definition of Done | Học viên hợp lệ mở lại đúng bài đang học |
| **Increment sẵn sàng sử dụng** | Phần sản phẩm tích hợp đạt chuẩn cần thiết để dùng được | Luồng “Học tiếp” hoạt động an toàn với phạm vi đã nêu |
| **Đã phát hành** | Increment tới môi trường hoặc nhóm người dùng được xác định | Tính năng được bật cho 10% học viên đủ điều kiện |
| **Đạt outcome** | Người dùng thực sự được lợi theo thước đo đã thống nhất | Tỷ lệ học viên tìm lại bài đúng nhanh hơn trong thời gian quan sát |

Một backlog có 15 mục được đánh dấu Done **không tự chứng minh** tính năng đã được phát hành hay đã tạo ra outcome mong muốn. Nếu dự báo “ngày phát hành”, lịch phải tính những hoạt động và điều kiện phát hành thực tế; nếu dự báo “đạt mục tiêu giữ chân học viên sau bảy ngày”, phải tính cả **cửa sổ quan sát** cần thiết.

### Cần ghi năm ranh giới

1. **Phạm vi:** có bao nhiêu story, hạng mục hay hành vi cần hoàn thành; có bao gồm lỗi cần sửa, migration, tài liệu bắt buộc không?
2. **Điểm bắt đầu:** tính từ bây giờ, từ ngày bắt đầu Sprint, hay từ lúc hạng mục vào trạng thái Doing?
3. **Điểm kết thúc:** Done, được phê duyệt, phát hành, hay có dữ liệu outcome?
4. **Đơn vị:** ngày làm việc, tuần lịch, Sprint hoặc số item; phải thống nhất quy đổi.
5. **Điều kiện chất lượng:** những yêu cầu nào không thể hạ thấp chỉ để đạt mốc, ví dụ phân quyền và bảo toàn dữ liệu.

Phạm vi không rõ là một trong những nguyên nhân phổ biến nhất khiến dự báo tạo ra **độ chính xác giả**. Cần tách “12 mục đã làm rõ” khỏi “còn một tập yêu cầu chưa được phát hiện”.

## 5. Dữ liệu nào hữu ích cho dự báo?

Một số nguồn thường gặp trong phát triển Agile:

| Dữ liệu | Định nghĩa thực hành | Hữu ích cho | Lưu ý |
| --- | --- | --- | --- |
| **Throughput** | Số hạng mục hoàn tất trong một khoảng thời gian, theo ranh giới Done nhất quán | Dự báo số item có thể hoàn tất theo tuần/ngày | Nếu kích thước, loại việc hoặc cách chia story đổi mạnh, lịch sử có thể không đại diện |
| **Cycle time** | Thời gian từ bắt đầu làm tới Done cho từng hạng mục | Dự báo thời gian một item, phân tích biến thiên và điểm nghẽn | Không tự động là thời gian hoàn tất toàn bộ backlog gồm nhiều item song song |
| **Lead time** | Thời gian từ mốc nhận yêu cầu tới mốc giao/Done được định nghĩa | Dự báo thời gian chờ của người yêu cầu | Mốc đầu/cuối phải thống nhất |
| **WIP** | Số item đã bắt đầu nhưng chưa hoàn tất | Hiểu luồng, nguy cơ quá tải và chờ đợi | WIP cao không trực tiếp cho biết ngày hoàn thành nếu không xét throughput |
| **Work item age** | Thời gian một item hiện đang được làm nhưng chưa Done | Phát hiện việc có nguy cơ kéo dài và ưu tiên tháo chặn | Không nên nhầm với cycle time của item đã hoàn tất |
| **Velocity / story points** | Tổng điểm ước lượng của những mục đạt Done theo quy ước một nhóm | Hỗ trợ lập kế hoạch tương đối trong cùng nhóm nếu dùng nhất quán | Điểm không phải giờ, không chuẩn hóa giữa nhóm và không đo giá trị người dùng |
| **Phạm vi còn lại** | Số item/đơn vị việc cần đưa tới mốc kết thúc đã chọn | Đầu vào trực tiếp cho dự báo thời gian hoàn thành | Backlog có thể phát sinh mục mới hoặc đổi kích thước |
| **Khả dụng năng lực** | Sự thay đổi về nhân lực, lịch nghỉ, trực vận hành, phụ thuộc | Điều chỉnh giả định mô hình | Lịch sử “đội đủ người” khó áp nguyên xi vào giai đoạn có nhiều người vắng |

### Dữ liệu tốt cần có bối cảnh

Trước khi dùng số liệu lịch sử, nhóm nên hỏi:

- Item hoàn tất có được xác nhận **đạt Definition of Done** hay chỉ được đóng ticket?
- Công việc có tương đối đồng dạng, hoặc đã phân lớp theo loại như bug, story nhỏ, thay đổi tích hợp?
- Có tuần nào throughput bằng **0**? Có giữ các tuần đó trong dữ liệu không? Việc bỏ các tuần khó khăn sẽ khiến dự báo lạc quan.
- Có đợt nghỉ dài, đổi nhóm, thay pipeline, chuyển kiến trúc hoặc thay cách chia story nào khiến dữ liệu cũ không còn đại diện?
- Có công việc đang dở, phụ thuộc bên ngoài hoặc lỗi chất lượng chưa được tính vào phạm vi?
- Dữ liệu được đo bằng **ngày làm việc** hay **ngày lịch**, đã tính nghỉ lễ và sự cố chưa?

Không có quy tắc “cần đúng N tuần dữ liệu” cho mọi tình huống. Dữ liệu càng ít và càng biến thiên thì độ bất định càng lớn; nhóm cần nói rõ giới hạn và tránh diễn giải phân vị một cách chắc chắn quá mức.

## 6. Các cách tạo dự báo và điều kiện sử dụng

| Cách tiếp cận | Cách làm | Khi hữu ích | Giới hạn |
| --- | --- | --- | --- |
| **Ước lượng chuyên gia theo khoảng** | Hỏi những người thực hiện về kịch bản thuận lợi, điển hình, bất lợi và điều kiện đi kèm | Việc mới chưa có lịch sử phù hợp; cần trao đổi sớm về rủi ro | Dễ chịu thiên lệch lạc quan, neo vào ngày mong muốn hoặc áp lực cấp trên |
| **Dự báo bằng tốc độ trung bình** | Lấy khối lượng còn lại chia throughput hoặc velocity trung bình phù hợp | Ước tính sơ bộ rất nhanh | Trung bình làm mất biến thiên và không tự cho xác suất |
| **Dự báo thực nghiệm theo cycle time/SLE** | Xem phân bố thời gian hoàn tất các item tương tự | Dự báo một item hoặc kỳ vọng dịch vụ | Không được dùng một phân vị item như phân vị hoàn tất một dự án nhiều item |
| **Monte Carlo từ lịch sử throughput** | Mô phỏng nhiều đường hoàn thành bằng cách lấy mẫu các kỳ throughput | Dự báo số kỳ cần hoàn tất một tập item | Phụ thuộc tính đại diện, mô hình lấy mẫu và việc kiểm soát phạm vi |
| **Mô hình có biến phụ thuộc rõ** | Kết hợp giai đoạn, năng lực, lịch nghỉ, rủi ro và phụ thuộc | Công việc có cấu trúc đặc biệt hoặc nhiều thay đổi năng lực | Càng nhiều giả định càng cần kiểm định và giải thích mô hình |

Một mô hình đơn giản nhưng **minh bạch, dựa trên dữ liệu phù hợp** thường hữu ích hơn mô hình phức tạp mà nhóm không giải thích được. Nếu chỉ có vài item rất khác nhau, mô phỏng throughput lịch sử có thể tạo ra con số rất đẹp nhưng thiếu cơ sở.

## 7. Ví dụ tính xác suất từ một mô hình nhỏ

Để hiểu khái niệm, ta dùng mô hình cố ý đơn giản và **tính xác suất chính xác**, chưa cần mô phỏng máy tính.

**Tình huống giả định:** Nhóm còn **3 story nhỏ có kích thước tương tự**, và mỗi tuần có thể hoàn tất:

| Số story Done trong tuần | Xác suất giả định |
| ---: | ---: |
| 0 | 20% |
| 1 | 50% |
| 2 | 30% |

Giả sử các tuần có phân bố trên và **độc lập nhau**, số story chưa tăng, không có phần việc nào bị tính Done trước khi đạt chuẩn và mọi story có thể hoàn tất trong các khoảng tuần như mô hình. Đây là **giả định giảng dạy**, không phải mô tả tự nhiên của mọi nhóm phát triển.

Gọi **X₁, X₂, ...** là throughput từng tuần. Số story hoàn tất sau n tuần là:

\[
S_n = X_1 + X_2 + \cdots + X_n
\]

Nhóm hoàn thành phạm vi trong n tuần nếu tổng số story Done **ít nhất bằng 3**:

\[
P(T\le n)=P(S_n\ge 3)
\]

### 7.1. Xác suất hoàn tất trong hai tuần

Trong hai tuần, muốn có ít nhất 3 story phải gặp một trong ba cặp:

| Tuần 1 | Tuần 2 | Xác suất cặp |
| ---: | ---: | ---: |
| 1 | 2 | 0,50 × 0,30 = 0,15 |
| 2 | 1 | 0,30 × 0,50 = 0,15 |
| 2 | 2 | 0,30 × 0,30 = 0,09 |

Cộng ba trường hợp:

\[
P(T\le2)=0{,}15+0{,}15+0{,}09=0{,}39=39\%
\]

Diễn đạt: **Theo mô hình minh họa này, khả năng hoàn tất cả ba story không muộn hơn cuối tuần thứ hai là 39%.**

Không được nói “hai tuần chắc chắn đủ”, và cũng không được nói “nhóm chỉ hoàn thành 39% công việc trong hai tuần”. 39% là **xác suất của một sự kiện hoàn thành toàn bộ phạm vi**.

### 7.2. Xác suất hoàn tất trong ba tuần

Một cách tính gọn là lấy 1 trừ xác suất vẫn hoàn thành **không quá 2 story** sau ba tuần:

- Tổng 0 story: cả ba tuần đều có throughput 0 → xác suất 0,2³ = **0,008**.
- Tổng 1 story: một tuần có 1, hai tuần còn lại 0 → xác suất 3 × 0,5 × 0,2² = **0,060**.
- Tổng 2 story: hoặc một tuần có 2 và hai tuần 0, hoặc hai tuần có 1 và một tuần 0 → xác suất **0,036 + 0,150 = 0,186**.

Vậy:

\[
P(T\le3)=1-(0{,}008+0{,}060+0{,}186)
=0{,}746=74{,}6\%
\]

### 7.3. Xác suất theo nhiều mốc

Tiếp tục tính bằng cùng phân bố sẽ được bảng sau:

| Hạn chót | Xác suất hoàn tất ít nhất 3 story trước hoặc tại mốc | Cách nói |
| --- | ---: | --- |
| Cuối tuần 1 | 0% | Trong mô hình, một tuần tối đa chỉ có 2 story |
| Cuối tuần 2 | **39,00%** | Khoảng 39% khả năng hoàn tất trong hai tuần |
| Cuối tuần 3 | **74,60%** | Khoảng 74,6% khả năng hoàn tất trong ba tuần |
| Cuối tuần 4 | **91,28%** | Khoảng 91,3% khả năng hoàn tất trong bốn tuần |
| Cuối tuần 5 | **97,33%** | Khoảng 97,3% khả năng hoàn tất trong năm tuần |

Các con số tuần 4 và 5 có thể kiểm tra bằng cách tính xác suất còn dưới 3 story, rồi lấy 1 trừ kết quả. Bảng là **kết quả toán học của giả định phân bố**, không phải bằng chứng một nhóm thực tế sẽ đạt mức đó.

### 7.4. Đọc phân vị từ bảng

- **P50:** tuần 3, vì cuối tuần 2 mới đạt 39%, còn cuối tuần 3 đã đạt 74,6%.
- **P85:** tuần 4, vì cuối tuần 3 chưa đạt 85%, còn cuối tuần 4 đã vượt 85%.
- **P95:** tuần 5, vì cuối tuần 4 là 91,28%, còn cuối tuần 5 vượt 95%.

Trong phân bố rời rạc theo tuần, mốc P85 ở tuần 4 có thể có **91,28%** xác suất tích lũy chứ không phải đúng 85%; đó là mốc nguyên đầu tiên đạt ít nhất 85%.

### 7.5. “Trong khoảng” khác “trước mốc”

Ví dụ muốn diễn đạt xác suất hoàn tất **từ tuần thứ 3 đến hết tuần thứ 5**, cần lấy xác suất hoàn tất trước hoặc trong tuần 5 trừ xác suất đã hoàn tất trước tuần 3 (tức trước hoặc trong tuần 2):

\[
P(3\le T\le5)=P(T\le5)-P(T\le2)
=0{,}97328-0{,}39=0{,}58328
\]

Vậy **khoảng 58,3%** khả năng thời điểm hoàn thành rơi **vào tuần 3, 4 hoặc 5**. Điều này **khác** với phát biểu “97,3% khả năng hoàn thành **không muộn hơn** tuần 5”. Khi giao tiếp dự báo theo khoảng, luôn nói rõ **có bao gồm việc hoàn thành sớm hơn đầu khoảng hay không**.

## 8. Dự báo theo phân vị và khoảng: trình bày thế nào cho đúng?

Phân vị giúp người ra quyết định chọn mức chấp nhận rủi ro:

| Mốc | Cách diễn đạt | Cân nhắc trong ví dụ |
| --- | --- | --- |
| **P50 = 3 tuần** | Có ít nhất 50% cơ hội hoàn tất không muộn hơn tuần 3 | Hữu ích làm mốc trung tâm để trao đổi, nhưng vẫn có rủi ro trễ đáng kể |
| **P85 = 4 tuần** | Có ít nhất 85% cơ hội hoàn tất không muộn hơn tuần 4 | Thích hợp nếu tổ chức chấp nhận còn một phần rủi ro |
| **P95 = 5 tuần** | Có ít nhất 95% cơ hội hoàn tất không muộn hơn tuần 5 | Chừa nhiều thời gian hơn nếu trễ có chi phí cao |

Không có chuẩn rằng mọi nhóm phải dùng P85 hay P95. Chọn mức rủi ro theo hậu quả thực tế: ra mắt để thu thập phản hồi có thể linh hoạt hơn một nghĩa vụ với đối tác, nhưng bảo mật và an toàn là tiêu chuẩn không được đánh đổi.

### Khi muốn trình bày một khoảng thời gian

Có hai cách nên nói rõ:

1. **Khoảng mốc theo hai phân vị:** “Mốc P50–P95 nằm từ tuần 3 đến tuần 5”. Đây là **khoảng giữa hai mốc phân vị**, không tự động là khoảng chứa 95% tất cả kết quả.
2. **Khoảng dự báo có xác suất:** “Trong mô hình, xác suất hoàn thành từ tuần 3 đến hết tuần 5 là khoảng 58,3%”. Đây là xác suất **rơi vào khoảng** cụ thể, không tính những lần đã hoàn thành trước tuần 3.

Nếu muốn nói “xác suất hoàn thành **trước hoặc trong** tuần 5 là 97,3%”, hãy nói đúng dạng đó, thay vì diễn đạt mơ hồ “dự án nằm trong tuần 3–5 với độ tin cậy 97,3%”.

### Phân biệt khoảng dự báo với khoảng tin cậy

- **Khoảng dự báo (prediction interval / predictive range)** nói về **kết quả tương lai** dưới một mô hình và những giả định cụ thể.
- **Khoảng tin cậy (confidence interval)** trong thống kê tần suất mô tả **độ bất định khi ước lượng một tham số** bằng một phương pháp có tính chất bao phủ qua nhiều lần lấy mẫu; không đồng nghĩa “có x% xác suất dự án sẽ nằm trong khoảng”.
- **Khoảng xác suất theo cách tiếp cận Bayes (credible interval)** có diễn giải xác suất về đại lượng chưa biết khi đã xác định mô hình và giả định tiên nghiệm; vẫn khác dự báo đầu ra tương lai nếu chưa mô hình hóa biến động tương lai.

Trong giao tiếp quản lý sản phẩm, nên ưu tiên cách nói cụ thể: **“Với mô hình hiện tại, khoảng x% lần mô phỏng hoàn tất trước mốc d”**, kèm điều kiện và giới hạn. Đừng gọi mọi cặp ngày là “khoảng tin cậy 90%” nếu chưa xác định đúng phương pháp thống kê.

## 9. Monte Carlo: từ lịch sử throughput đến phân bố hoàn thành

Ví dụ ở mục 7 có phân bố đơn giản và xác suất đã biết. Với backlog thực tế gồm nhiều item, mỗi tuần throughput biến thiên và có thể có hàng nghìn tổ hợp, nhóm thường dùng **mô phỏng Monte Carlo** để tạo phân bố số kỳ còn lại.

### 9.1. Ý tưởng cơ bản

Giả sử nhóm:

- Đã xác định **18 backlog item còn lại** trong một phạm vi nhất định.
- Có lịch sử throughput tuần gần đây, ví dụ: **[2, 3, 4, 1, 5, 3, 2, 4, 0, 3]** mục/tuần.
- Tạm giả định phân bố các tuần này có thể đại diện cho giai đoạn tới, dù phải kiểm tra mức tương đồng về loại việc, nhân sự và chính sách Done.

Một lượt mô phỏng bắt đầu từ 18 item, lần lượt **lấy ngẫu nhiên một giá trị throughput** từ lịch sử cho mỗi tuần, trừ số mục đã hoàn thành và dừng khi không còn item. Lặp nhiều lượt, ta thu được phân bố số tuần cần hoàn tất. Sau đó tính:

- Bao nhiêu phần trăm lượt mô phỏng xong **trước hoặc trong tuần 5**?
- Mốc tuần nhỏ nhất để có **ít nhất 85%** lượt mô phỏng hoàn tất là gì?
- Mô hình có **đuôi trễ** đáng lo, ví dụ những lượt kéo dài do nhiều tuần throughput thấp không?

### 9.2. Giả mã minh họa

~~~text
remaining_items = 18
historical_weekly_throughput = [2, 3, 4, 1, 5, 3, 2, 4, 0, 3]
simulations = 10000
max_weeks = 52
finish_weeks = []
unfinished_at_limit = 0

repeat simulations times:
    remaining = remaining_items
    weeks = 0

    while remaining > 0 and weeks < max_weeks:
        completed = random_choice(historical_weekly_throughput)
        remaining = max(0, remaining - completed)
        weeks = weeks + 1

    if remaining == 0:
        finish_weeks.append(weeks)
    else:
        unfinished_at_limit = unfinished_at_limit + 1

for each candidate deadline d:
    probability_by_d =
        count(finish_weeks where weeks <= d) / simulations

report:
    probability_by_deadline
    observed_percentiles
    unfinished_at_limit / simulations
    assumptions_and_data_quality
~~~

Đây là **giả mã giải thích thuật toán**, không phải một công cụ thống kê hoàn chỉnh hoặc kết quả mô phỏng đã được chạy. Khi có lượt chưa hoàn tất trong giới hạn mô phỏng, không được bỏ chúng khỏi mẫu số và giả vờ rằng toàn bộ các lượt đều hoàn thành. Cần nêu rõ giới hạn thời gian mô phỏng và tỷ lệ chưa hoàn thành.

### 9.3. Những giả định quan trọng

Mô phỏng lấy mẫu độc lập các tuần từ lịch sử thường giả định ngầm:

1. **Cách chia backlog item và Definition of Done đủ nhất quán**.
2. **Throughput quá khứ đại diện cho tương lai** trong phạm vi dự báo.
3. Các kỳ có thể **lấy mẫu theo cách đã chọn** mà không bỏ sót tính phụ thuộc theo mùa vụ, nghỉ lễ, công việc theo đợt hoặc hiệu ứng tồn đọng.
4. Phạm vi còn lại **không phát sinh thêm**, trừ khi mô hình có mô phỏng scope growth.
5. Những rủi ro tích hợp, rework, lỗi chất lượng hoặc phụ thuộc đã phản ánh phần nào trong dữ liệu hoặc được mô hình hóa riêng.

Nếu năng lực nhóm thay đổi đáng kể hoặc công việc sắp tới khác hẳn lịch sử, dự báo bằng cách bốc mẫu trực tiếp có thể **rất sai**. Cần phân nhóm dữ liệu, dùng kịch bản năng lực khác, kết hợp phán đoán chuyên môn hoặc nói thẳng rằng chưa có cơ sở để gán xác suất đáng tin.

### 9.4. Số lượt mô phỏng không sửa được dữ liệu xấu

Chạy 100.000 lượt từ dữ liệu bị thiếu tuần throughput 0 vẫn cho kết quả thiên lệch, dù các con số phần trăm ổn định đến nhiều chữ số sau dấu phẩy. **Độ lặp mô phỏng cao không đồng nghĩa độ đúng của giả định cao.** Khi báo cáo, làm tròn phù hợp và nhấn mạnh nguồn bất định lớn nhất.

## 10. Dự báo hai hướng: “Khi nào xong?” và “Đến hạn có xong không?”

Cùng một phân bố hoàn thành có thể giải hai loại câu hỏi quản lý khác nhau:

~~~mermaid
flowchart TD
    A["Phạm vi, dữ liệu throughput<br/>và giả định chất lượng"] --> B["Tạo phân bố thời gian<br/>hoàn tất theo mô hình"]
    B --> C{"Câu hỏi quyết định"}
    C --> D["Hạn chót cố định?<br/>Tính P(hoàn tất trước hạn)"]
    C --> E["Chọn mức rủi ro?<br/>Đọc mốc P50/P85/P95"]
    C --> F["Cần dải thời gian?<br/>Tính xác suất trong khoảng"]
    D --> G["Cập nhật phạm vi, phương án<br/>và quản trị rủi ro"]
    E --> G
    F --> G
~~~

### Câu hỏi 1: “Với phạm vi này, khi nào khả năng hoàn thành đạt ít nhất 85%?”

Trả lời bằng phân vị: “Theo mô hình và giả định đã nêu, **mốc P85** là cuối tuần X”.

### Câu hỏi 2: “Nếu bắt buộc phát hành trước ngày D, khả năng đạt được bao nhiêu?”

Trả lời bằng xác suất tích lũy: “Mô hình cho **x% khả năng đạt mốc D** với phạm vi hiện tại; các kịch bản trễ chủ yếu do phụ thuộc tích hợp và biến động throughput.”

### Câu hỏi 3: “Phải bỏ bớt gì để tăng khả năng đạt ngày D?”

Mô phỏng lại theo **các phương án phạm vi có căn cứ**. Ví dụ:

| Phương án | Điều thay đổi | Điều cần kiểm tra |
| --- | --- | --- |
| A — giữ toàn bộ phạm vi | 18 item như hiện tại | Xác suất tới hạn chót và rủi ro nếu trễ |
| B — giao lát cắt giá trị sớm | Giữ 11 item thiết yếu, chuyển 7 item nâng cao sang đợt sau | 11 item có thực sự tạo hành vi sử dụng được và đạt chất lượng không? |
| C — thay đổi năng lực | Bổ sung năng lực kiểm thử hoặc loại bỏ điểm nghẽn | Năng lực có tăng throughput thực, hay tăng người lại tạo thêm chi phí phối hợp? |
| D — đổi thời điểm | Giữ chất lượng và phạm vi, chọn mốc P85/P95 muộn hơn | Chi phí cơ hội, nghĩa vụ đối tác và giá trị kinh doanh bị ảnh hưởng thế nào? |

**Không được giảm mẫu số của mô hình bằng cách loại bỏ công việc bắt buộc** như phân quyền, bảo mật, kiểm thử tính đúng đắn, migration cần thiết hoặc yêu cầu tuân thủ. Nếu phương án chỉ giao phần sản phẩm hẹp hơn, phải nói rõ **điều người dùng thật sự nhận được**.

## 11. Dự báo phạm vi khi thời gian đã cố định

Không phải lúc nào mục tiêu là tìm ngày hoàn thành một backlog cố định. Đôi khi nhóm có mốc phát hành không thể thay đổi và cần trả lời:

> “Trong bốn tuần tới, với mức độ tin cậy đã chọn, nhóm có thể hoàn tất khoảng bao nhiêu item tương đối đồng dạng?”

Đây là **bài toán số lượng công việc theo thời gian cố định**, khác với bài toán số tuần để làm xong N item.

Nếu mô hình có throughput ngẫu nhiên Xᵢ cho từng tuần, số lượng hoàn thành sau bốn tuần là:

\[
S_4=X_1+X_2+X_3+X_4
\]

Nhóm có thể mô phỏng phân bố của **S₄**, rồi hỏi:

- Có bao nhiêu xác suất hoàn tất **ít nhất 12 item** trong bốn tuần?
- Với yêu cầu an toàn 85%, số item lớn nhất có thể dự báo hoàn tất là bao nhiêu?
- Những item **nào** tạo một lát cắt giá trị sử dụng được, thay vì chỉ đạt số lượng ticket?

Ví dụ minh họa mô hình ở mục 7: trong bốn tuần, xác suất hoàn tất **ít nhất 3 story** là 91,28%. Đây cũng chính là xác suất hoàn tất **phạm vi 3 story trước tuần 4**. Nếu thay phạm vi thành 4 hoặc 5 story, xác suất phải tính lại; không được suy từ 3 story bằng tỷ lệ tuyến tính đơn giản.

**Quyết định phạm vi luôn cần Product Owner và Developers trao đổi về giá trị, phụ thuộc và Definition of Done**; dự báo số item đơn thuần không biết item nào quan trọng.

## 12. Cycle time, phân vị từng item và Service Level Expectation

Kanban thường dùng **phân bố cycle time** của những item tương tự để tạo kỳ vọng dịch vụ.

Ví dụ minh họa: Trong 40 hạng mục đã hoàn tất cùng loại, có 34 hạng mục đạt Done trong **không quá 10 ngày làm việc**. Quan sát thực nghiệm là:

\[
\frac{34}{40}=85\%
\]

Nhóm có thể dùng tín hiệu ấy để trao đổi một **Service Level Expectation (SLE)** kiểu: “Với lớp công việc này và ranh giới đo hiện tại, chúng ta kỳ vọng phần lớn item hoàn tất trong 10 ngày làm việc; lịch sử cho thấy 85% item trong mẫu đạt mốc đó”.

Tuy nhiên:

- 40 quan sát không bảo đảm rằng chính xác 85% item tương lai sẽ đạt mốc.
- Một item đang chờ 11 ngày là tín hiệu cần chú ý, nhưng **không chứng minh** tất cả item sẽ trễ tương tự.
- SLE của **một item** không thể chuyển thành “85% xác suất cả 10 item đều xong trong 10 ngày”; đó là một sự kiện khác.
- Nếu item hiện tại đã bắt đầu từ vài ngày trước, dự báo **thời gian còn lại có điều kiện theo tuổi hiện tại** cần xem xét thêm, thay vì dùng nguyên phân bố từ lúc bắt đầu một cách máy móc.

### Cách kết hợp SLE với quản lý WIP

Khi một work item có **age** gần hoặc vượt vùng thời gian thường hoàn tất, nhóm có thể chủ động hỏi: nó bị chặn ở đâu, có nên tập trung hoàn tất trước khi kéo việc mới, hoặc cần phối hợp bên ngoài? Cải thiện flow và giới hạn WIP phù hợp có thể làm phân bố cycle time tương lai thay đổi; khi đó cũng cần **cập nhật SLE và dự báo**.

## 13. Giả định về phạm vi và năng lực: nguồn bất định lớn

Nhiều dự báo sai không phải do tính toán xác suất kém, mà do người dùng tưởng **phạm vi và năng lực giữ nguyên** trong khi thực tế thay đổi.

### Bốn nguồn biến động thường gặp

| Nguồn | Biểu hiện | Ảnh hưởng đến dự báo |
| --- | --- | --- |
| **Scope growth** | Xuất hiện lỗi phải sửa, quy tắc nghiệp vụ mới, yêu cầu tuân thủ hoặc user story bổ sung | Tăng tổng khối lượng còn lại, phân bố ngày hoàn thành dịch sang muộn |
| **Năng lực thay đổi** | Nghỉ phép, trực sự cố, mất người chủ chốt, onboarding người mới | Throughput tương lai có thể khác lịch sử |
| **Đặc tính item thay đổi** | Các story còn lại khó hơn hoặc nhiều phụ thuộc hơn | Đếm item đơn thuần có thể đánh giá thấp công sức |
| **Chất lượng/rework** | Lỗi tích hợp, thay thiết kế, kiểm thử không ổn định | Nhiều thời gian dành cho việc không thể hiện qua số item mới Done |

### Mô hình hóa các kịch bản

Không nhất thiết phải gán xác suất ngay cho mọi sự kiện chưa đủ dữ liệu. Có thể bắt đầu bằng ba kịch bản có điều kiện:

| Kịch bản | Giả định | Thông điệp cần truyền đạt |
| --- | --- | --- |
| **Phạm vi giữ nguyên** | Chỉ các story đã thống nhất, không phát sinh thêm ràng buộc | Dự báo có điều kiện theo baseline |
| **Phạm vi tăng** | Bổ sung vài story do phát hiện quy tắc hoặc lỗi cần xử lý | Mốc phân vị muộn hơn; công việc mới phải được đếm thật |
| **Năng lực giảm** | Một người hỗ trợ sự cố, có kỳ nghỉ hoặc phụ thuộc kéo dài | Phải dùng phân bố throughput khác hoặc dự báo theo năng lực mới |

Khi tổ chức muốn một **dự báo gộp** cho các kịch bản, phải có cơ sở về xác suất của từng kịch bản; không nên tự gán “30% xấu, 50% trung bình, 20% tốt” chỉ để có biểu đồ hấp dẫn.

### Tránh “đếm hai lần” rủi ro

Nếu lịch sử throughput đã bao gồm những tuần có người nghỉ và xử lý lỗi thông thường, rồi mô hình lại tự động trừ thêm toàn bộ thời gian nghỉ và lỗi đó, có thể dự báo quá bi quan. Ngược lại, nếu dự báo lấy những tuần tốt nhất rồi không tính công việc vận hành, có thể quá lạc quan. Cần chỉ rõ **rủi ro nào đã phản ánh trong dữ liệu, rủi ro nào là mới**.

## 14. Đánh giá độ tin cậy của một dự báo

Một dự báo xác suất không tự đúng chỉ vì có tên “Monte Carlo”. Cần có cơ chế kiểm tra:

### 14.1. Kiểm tra dữ liệu nguồn

- Có đủ quan sát và có đại diện cho công việc sắp tới?
- Có tính các tuần không hoàn thành item nào?
- Ranh giới Ready, Doing và Done nhất quán?
- Có thay đổi chính sách review, CI, phân công hoặc Definition of Done?
- Có việc đã bắt đầu nhưng không bao giờ đóng và bị bỏ sót trong lịch sử?

### 14.2. Kiểm tra thực tế với những dự báo đã qua

Một cách hữu ích là **backtesting**: sử dụng dữ liệu có tại một thời điểm cũ để dự báo giai đoạn sau, rồi so kết quả dự báo với kết quả thực, tránh vô tình dùng thông tin tương lai làm đầu vào.

Ví dụ:

1. Ở đầu một tuần trong quá khứ, lấy backlog và lịch sử throughput **đã biết tại thời điểm đó**.
2. Tạo dự báo P50/P85/P95 cho phạm vi được xác định lúc ấy.
3. Quan sát thời điểm thực sự hoàn tất, ghi nhận việc phạm vi có thay đổi không.
4. Lặp ở nhiều thời điểm phù hợp để xem mốc P85 có được đáp ứng gần mức kỳ vọng qua nhiều trường hợp hay không.
5. Phân tích những lần sai lệch lớn: mô hình thiếu scope growth, item còn lại rất khác, lỗi đo hay phụ thuộc kéo dài?

**Một dự án trễ mốc P85 không tự động chứng minh mô hình sai**: dự báo 85% vốn có khả năng khoảng 15% không đạt mốc, nếu hiệu chuẩn tốt và giả định đúng. Nhưng nếu nhiều dự báo P85 liên tục chỉ đạt 40–50% thì nhóm cần xem lại dữ liệu và mô hình, không đổ lỗi cho “xác suất xui”.

### 14.3. Phân biệt hai lớp bất định

- **Biến thiên tự nhiên của quá trình:** throughput tuần nào cũng không giống nhau dù hệ thống tương đối ổn định.
- **Thiếu hiểu biết về mô hình hoặc tương lai:** không biết throughput sẽ đổi thế nào khi tuyển người, thay kiến trúc hoặc phát sinh quy tắc.

Monte Carlo lấy mẫu từ lịch sử chủ yếu biểu diễn loại biến thiên mà dữ liệu/mô hình đã đưa vào. Nó **không tự bao phủ những sự kiện chưa được mô hình hóa**. Truyền đạt dự báo cần nêu cả các điều kiện chưa chắc chắn ngoài mô hình.

## 15. Cập nhật dự báo theo nhịp thay vì đóng băng một ngày

Trong Agile, dự báo nên được **kiểm tra và điều chỉnh** khi có dữ liệu mới hoặc biến động lớn. Nhịp cập nhật phù hợp tùy mức rủi ro, thời gian ra quyết định và độ trễ của các phép đo.

~~~mermaid
flowchart TD
    A["Xác định mục tiêu, phạm vi<br/>và mức rủi ro chấp nhận"] --> B["Thu thập throughput/cycle time<br/>và thông tin phụ thuộc"]
    B --> C["Tạo phân bố dự báo<br/>với giả định rõ"]
    C --> D["Trình bày P(đạt hạn),<br/>phân vị và phương án"]
    D --> E["Giao lát cắt giá trị,<br/>nhận phản hồi kỹ thuật và sản phẩm"]
    E --> F{"Phạm vi, dữ liệu,<br/>năng lực có thay đổi?"}
    F -->|Có| G["Cập nhật baseline,<br/>mô hình và dự báo"]
    F -->|Không đáng kể| H["Kiểm tra lại theo<br/>nhịp đã thống nhất"]
    G --> D
    H --> D
~~~

### Lịch cập nhật ví dụ

| Khi nào | Nên xem lại điều gì |
| --- | --- |
| Khi Product Backlog được làm rõ, tách/gộp story lớn | Số lượng và loại item còn lại có còn so được với lịch sử không? |
| Kết thúc một Sprint hoặc mỗi tuần theo Kanban | Throughput mới, work item age, việc bị chặn và phạm vi Done thật |
| Khi rủi ro kỹ thuật quan trọng được xác nhận hoặc bác bỏ | Có cần thay đổi kịch bản, thứ tự backlog hoặc điểm kết thúc không? |
| Khi nhân sự, lịch nghỉ, chính sách kiểm thử/phát hành thay đổi | Phân bố năng lực và thời gian chờ có còn phù hợp không? |
| Trước một quyết định cam kết với bên ngoài | Xác suất đạt ngày mong muốn, mức rủi ro chấp nhận và phương án ứng phó |

**Không nhất thiết tạo lại toàn bộ báo cáo mỗi ngày** nếu công việc và dữ liệu không thay đổi có ý nghĩa. Quan trọng là người ra quyết định luôn biết dự báo dựa trên **ảnh chụp phạm vi và dữ liệu ở thời điểm nào**.

## 16. Kết nối với Scrum, Kanban, XP và Agile

### Scrum: dự báo hỗ trợ Sprint Planning và quản lý sản phẩm

Scrum Guide không bắt buộc dùng story points, velocity hoặc Monte Carlo. Trong Scrum, Developers lựa chọn công việc cho Sprint dựa trên mục tiêu, năng lực và hiểu biết về Product Backlog; Product Owner có trách nhiệm tối đa hóa giá trị và thứ tự ưu tiên backlog.

Một dự báo theo xác suất giúp:

- Thảo luận các **phương án phạm vi** để đạt Sprint Goal và Product Goal.
- Minh bạch hậu quả nếu thay đổi Product Backlog hoặc công việc chưa đạt Definition of Done.
- Hỗ trợ dự đoán nhiều Sprint cần cho một nhóm backlog item, **không thay thế** việc kiểm tra/thích ứng theo Sprint.
- Tránh dùng velocity làm mục tiêu bắt buộc hoặc thước đo so sánh nhân sự.

Với Sprint dài hai tuần, có thể dùng lịch sử số story Done mỗi Sprint để dự báo số Sprint còn lại, nhưng chỉ khi story và Definition of Done đủ nhất quán. Nếu mục tiêu là ngày lịch, cần tính ngày nghỉ và mối quan hệ giữa chu kỳ Sprint với mốc phát hành.

### Kanban: dùng dữ liệu flow và cải thiện hệ thống

Kanban cung cấp cách nhìn trực tiếp về **throughput, cycle time, WIP và work item age**, hữu ích cho dự báo lẫn phát hiện chỗ nghẽn. Khi giới hạn WIP và làm rõ chính sách giúp luồng ổn định hơn, phân bố throughput và thời gian hoàn thành có thể thay đổi, nên mô hình cũng cần được cập nhật.

Nhóm có thể dùng **SLE** cho thời gian hoàn thành một item và dự báo throughput cho một tập item. Không nên đánh đồng hai loại xác suất đó hoặc áp một con số chung cho mọi lớp công việc.

### XP: cải thiện độ ổn định kỹ thuật của dự báo

Khi kiểm thử không ổn định, mã khó thay đổi hoặc tích hợp muộn, lịch sử Done thường biến động và dễ phát sinh rework. TDD, refactoring, tích hợp liên tục, review/cặp lập trình và phát hành nhỏ có thể giúp **phát hiện lỗi sớm, giảm các đợt làm lại lớn và tạo nhịp giao hàng tin cậy hơn**.

Tuy nhiên, **độ ổn định kỹ thuật không tự chứng minh giá trị của sản phẩm**. Dự báo hoàn tất backlog cần đi cùng phản hồi người dùng để tránh hoàn thành “đúng hạn” một giải pháp không ai cần.

### Giá trị Agile trong việc cập nhật dự báo

- **Phản hồi sớm:** dùng lát cắt nhỏ để học thêm về nhu cầu và rủi ro.
- **Tăng dần:** ưu tiên một Increment sử dụng được thay vì chờ đến mốc có 100% epic.
- **Minh bạch:** nói rõ phân vị, giới hạn mô hình, điều chưa biết và việc chưa Done.
- **Thích ứng:** cập nhật thứ tự backlog và kế hoạch khi dữ liệu mới khác giả định.
- **Cải tiến liên tục:** đo chất lượng dự báo, lý do sai lệch và điểm nghẽn của dòng công việc.

## 17. Tình huống xuyên suốt: dự báo phát hành tính năng “Học tiếp”

Nhóm phát triển nền tảng học trực tuyến muốn giao một luồng người dùng có ích: học viên đã đăng nhập có thể tiếp tục đúng bài đang dở. Qua refinement, Product Owner và Developers chia epic thành các lát cắt:

| Nhóm việc | Ví dụ | Tính chất |
| --- | --- | --- |
| **Giá trị cốt lõi** | Lưu tiến độ, hiện nút “Học tiếp”, mở đúng bài trong phạm vi tài khoản hợp lệ | Cần để tạo trải nghiệm sử dụng được |
| **Chất lượng bắt buộc** | Phân quyền, kiểm thử truy xuất đúng dữ liệu, xử lý tiến độ không hợp lệ | Không được loại bỏ chỉ để giảm số item |
| **Mở rộng trải nghiệm** | Học tiếp giữa thiết bị, trợ giúp khi không có tiến độ, ngoại lệ đã hoàn thành | Có thể ưu tiên theo nhu cầu và rủi ro |
| **Rủi ro kỹ thuật** | Cập nhật đồng thời, sự cố mạng, migration dữ liệu cũ | Cần kiểm chứng sớm nếu hậu quả cao |
| **Đo lường** | Sự kiện học tiếp, thời gian tìm bài và lỗi mất tiến độ | Cần định nghĩa để học từ người dùng |

Giả sử bản thân **phạm vi phát hành tối thiểu** đã được xác định gồm 12 item tương đối nhỏ, những điều kiện chất lượng bắt buộc có mặt trong phạm vi. Nhóm có lịch sử throughput tuần phù hợp nhưng biến thiên. Không nên lấy “12 / trung bình 4 = đúng 3 tuần” rồi tuyên bố chắc chắn sẽ giao.

### 17.1. Chọn câu hỏi dự báo

Bên liên quan có hai nhu cầu:

1. “Nếu phát hành cho nhóm học viên thử nghiệm vào mốc D, **xác suất đạt mốc** là bao nhiêu?”
2. “Nếu muốn **ít nhất 85% xác suất hoàn tất**, nên đặt mốc nào?”

Để trả lời, nhóm xác định mốc bắt đầu, phạm vi 12 item, điều kiện Done, lịch nghỉ, phụ thuộc API và xem lịch sử có đại diện cho giai đoạn tới. Sau đó mới tạo phân bố theo mô hình đã chọn.

### 17.2. Ví dụ một bảng báo cáo dự báo

Các tỷ lệ sau **chỉ là kết quả giả định để minh họa cấu trúc báo cáo**, không phải kết quả mô phỏng đã chạy và cũng không suy trực tiếp từ dữ liệu của một nhóm thực:

| Mốc kể từ lúc dự báo | Xác suất hoàn tất 12 item theo kịch bản minh họa |
| --- | ---: |
| Hết tuần 3 | 35% |
| Hết tuần 4 | 63% |
| Hết tuần 5 | 84% |
| Hết tuần 6 | 94% |
| Hết tuần 7 | 98% |

Với bảng minh họa này, **P85 nằm ở tuần 6**, không phải tuần 5, vì tại tuần 5 mới đạt 84%. Nếu tổ chức chấp nhận khoảng 80% xác suất, tuần 5 là mốc có thể cân nhắc; nếu mong muốn ít nhất khoảng 95%, cần nhìn tới tuần 7 theo các mốc trong bảng.

Nhóm không nên chỉ nói “P85 = 6 tuần” mà bỏ qua điều kiện: dự báo giả định 12 item ổn định, throughput được lấy từ giai đoạn đại diện và các phụ thuộc lớn không thay đổi. Nếu một API quan trọng chưa được xác nhận, cần nêu riêng rủi ro vượt ngoài mô hình.

### 17.3. Đưa dự báo thành quyết định sản phẩm

Product Owner có thể cân nhắc:

- **Giữ phạm vi 12 item** và công bố mốc có độ tin cậy phù hợp với hậu quả trễ.
- **Chia phát hành thành hai đợt**, đưa lát cắt “Học tiếp trên cùng thiết bị” đạt Done tới nhóm thử trước, rồi mở rộng đa thiết bị.
- **Giải quyết phụ thuộc sớm** hoặc làm spike giảm rủi ro đồng bộ dữ liệu, nếu nó có khả năng gây làm lại lớn.
- **Đổi mốc hoặc cách truyền thông**, khi ngày mong muốn không phù hợp xác suất và chất lượng.

Khi nhóm phát hành một lát cắt đầu, cần thu thập phản hồi thực tế: học viên có tìm thấy nút, mở đúng bài và tiếp tục học thuận tiện không? **Dự báo hoàn thành** và **kiểm chứng giá trị** là hai vòng học liên quan nhưng khác nhau.

### 17.4. Sau một tuần có gì thay đổi?

Giả sử thực tế nhóm hoàn thành ít hơn dự kiến vì một lỗi dữ liệu chưa biết. Bản cập nhật dự báo phải:

1. Ghi số item thực sự đạt Done, không cộng những mục mới “gần xong”.
2. Ghi nhận lỗi mới là scope growth hay rework, không ẩn khỏi backlog.
3. Kiểm tra throughput tuần thấp là biến động bình thường hay tín hiệu năng lực/mô hình thay đổi.
4. Tạo lại phân bố dự báo từ số item và điều kiện hiện tại.
5. Nêu cách giảm rủi ro và thời điểm kiểm tra lại.

Thông điệp đúng là: “Mốc dự báo thay đổi do bằng chứng mới”, **không phải** “Agile cho phép bỏ mọi cam kết” hoặc “cứ giữ ngày cũ và cắt kiểm thử”.

## 18. Cách truyền đạt dự báo cho các bên liên quan

### Mẫu ngắn, dễ dùng trong cuộc họp

> “Tại ngày cập nhật này, phạm vi là **N hạng mục đạt Done mới xem là hoàn tất**. Dựa trên dữ liệu dòng công việc được kiểm tra, mô hình cho **x% khả năng hoàn thành trước hạn D**; mốc P85 là **D₂**. Phạm vi hiện chưa bao gồm/đã bao gồm các rủi ro ... Nếu cần tăng xác suất đạt hạn, nhóm đề xuất hai phương án: giao lát cắt giá trị nhỏ hơn hoặc giải quyết phụ thuộc ... Chúng tôi sẽ cập nhật vào mốc ...”

Đừng chỉ gửi hình biểu đồ mà thiếu bối cảnh. Người nhận cần hiểu **đang dự báo sự kiện gì, xác suất của sự kiện nào, sử dụng dữ liệu nào và quyết định nào đang được đề nghị**.

### Mẫu bảng báo cáo

| Trường | Nội dung cần có |
| --- | --- |
| **Mục tiêu và điều kiện Done** | Những hành vi nào thực sự phải có; tiêu chuẩn chất lượng bắt buộc |
| **Ngày/thời điểm chụp dự báo** | Khi nào phạm vi và dữ liệu được lấy |
| **Phạm vi còn lại** | Số item và các ngoại lệ, loại việc chưa xác định |
| **Nguồn dữ liệu** | Throughput/cycle time trong kỳ nào; cách lọc; các tuần không có item Done |
| **Mô hình** | Lấy mẫu từ lịch sử, kịch bản năng lực hoặc phương pháp khác |
| **Xác suất theo hạn** | P(hoàn tất không muộn hơn ngày D) |
| **Các mốc phân vị** | P50, P85, P95 hoặc mức được các bên thỏa thuận |
| **Giới hạn và rủi ro ngoài mô hình** | Scope growth, nghỉ lễ, phụ thuộc, dữ liệu chưa đủ |
| **Lựa chọn hành động** | Giữ, giảm phạm vi có giá trị, tháo phụ thuộc, đổi mốc hoặc điều chỉnh nguồn lực |
| **Nhịp cập nhật và người chịu trách nhiệm** | Khi nào dự báo được xem lại và ai truyền đạt quyết định |

### Trả lời ba câu hỏi khó

**“Tại sao không cho tôi một ngày duy nhất?”**  
Có thể đưa một mốc phục vụ lập kế hoạch, chẳng hạn P85, nhưng phải nói rõ đây là mốc với **xác suất và điều kiện**. Một ngày đơn lẻ không cho biết mức rủi ro.

**“Nếu P85 mà vẫn trễ thì dự báo vô ích sao?”**  
Không hẳn. Dự báo 85% có thể trễ trong một phần các trường hợp nếu được hiệu chuẩn tốt. Điều cần kiểm tra là dữ liệu và giả định có phù hợp, khả năng bao phủ qua nhiều dự báo, và liệu thay đổi phạm vi hoặc sự cố ngoài mô hình có xảy ra.

**“Sao không cộng thêm một tuần dự phòng để chắc chắn?”**  
Dự phòng có thể là quyết định hợp lý, nhưng **không thể tuyên bố chắc chắn 100%** chỉ bằng cộng một con số tùy ý. Hãy xét phân vị, hậu quả trễ, phạm vi tạo giá trị và các rủi ro đặc biệt không được mô hình hóa.

## 19. Những sai lầm thường gặp

### 19.1. Gắn xác suất với một ngày do cấp trên đã chọn

“Chúng ta muốn ngày 30 nên khả năng đạt là 90%” là đảo ngược logic. Xác suất phải được tính hoặc đánh giá có căn cứ **từ mô hình và dữ liệu**, không suy từ mong muốn.

### 19.2. Dùng trung bình như ngày chắc chắn

Nếu throughput trung bình là 4 item/tuần và backlog còn 20 item, phép chia 20/4 cho mốc sơ bộ 5 tuần, **không** cho xác suất hoàn thành trong 5 tuần. Biến thiên và phạm vi còn lại có thể làm đuôi phân bố kéo dài.

### 19.3. Nói “trong khoảng P50–P95 có 95% xác suất”

P50 và P95 là **hai mốc phân vị**. Xác suất rơi giữa hai mốc phải tính từ phân bố, kể cả cách xử lý ranh giới và các điểm có xác suất tập trung. Không mặc định chính là 95%.

### 19.4. Bỏ các tuần throughput bằng 0

Nếu nhóm từng có tuần không hoàn thành item nào do chờ kiểm thử hoặc sự cố, bỏ chúng khỏi dữ liệu mà không có lý do phù hợp có thể khiến mô hình quá lạc quan.

### 19.5. Đếm các story rất khác nhau như nhau mà không xem xét

Một story nhỏ chỉnh nhãn và một story di chuyển kiến trúc dữ liệu có thể có thời gian và rủi ro khác xa. Dự báo số item chỉ hợp lý khi **đặc tính phân bố tương lai tương đối phù hợp lịch sử**; nếu không, cần tách loại công việc, làm rõ phạm vi hoặc dùng phương pháp khác.

### 19.6. Coi story point là giờ hoặc thước đo chuẩn giữa các nhóm

Story points là quy ước tương đối của một nhóm nếu họ sử dụng. “Nhóm A có 40 điểm, nhóm B 20 điểm nên nhóm A nhanh gấp đôi” không có cơ sở nếu cách ước lượng khác nhau.

### 19.7. Dùng SLE một item làm dự báo cả dự án

“85% item hoàn tất trong 10 ngày” không có nghĩa “85% khả năng tất cả 20 item hoàn tất trong 10 ngày”. Cần mô hình hóa tổng luồng, WIP, phụ thuộc và thời gian còn lại.

### 19.8. Quên scope growth, bug và việc chưa Done

Forecast cho 20 item nhưng thực tế phát sinh 8 quy tắc mới, trong khi biểu đồ không cập nhật phạm vi, sẽ sai ngay cả khi throughput dự báo đúng.

### 19.9. Coi mô phỏng nhiều lần là bằng chứng về độ chính xác

Một triệu lượt mô phỏng trên giả định sai tạo ra một triệu kịch bản **theo giả định sai**. Chất lượng dữ liệu và khả năng kiểm định quan trọng hơn số lượt chạy.

### 19.10. Thay đổi cách đo giữa các kỳ nhưng so số như cũ

Nếu tuần trước Done nghĩa là QA đã xác nhận, tuần này Done nghĩa là lập trình xong, throughput tăng không chứng minh nhóm giao nhanh hơn. Phải giữ hoặc chú giải thay đổi ranh giới.

### 19.11. Biến dự báo thành chỉ tiêu gây áp lực

Nếu người làm việc bị đánh giá chỉ bằng việc “đạt P50”, họ có thể đóng ticket sớm, chia vụn story hoặc che giấu rủi ro. Hãy dùng dự báo để **học, ra quyết định và tháo trở ngại**, bảo vệ chất lượng và an toàn tâm lý.

### 19.12. Không cập nhật khi có thông tin mới

Một dự báo đã công bố tháng trước có thể mất tính phù hợp khi team đổi, backlog tăng hoặc tìm thấy lỗi dữ liệu. Tính minh bạch không phải bảo vệ ngày cũ bằng mọi giá, mà là giải thích **vì sao xác suất và phương án hành động thay đổi**.

## 20. Bài tập thực hành

### Bài tập A — Diễn đạt đúng xác suất

Với phân bố minh họa ở mục 7, hãy đánh giá:

1. “Có 74,6% khả năng cả ba story hoàn tất **không muộn hơn** cuối tuần 3.”
2. “Có 74,6% số công việc sẽ xong trong tuần 3.”
3. “Mốc P85 là cuối tuần 4.”
4. “Với P95, dự án chắc chắn hoàn thành trong năm tuần.”
5. “Xác suất rơi vào tuần 3–5 phải trừ đi khả năng hoàn tất trước tuần 3.”

**Gợi ý:** (1), (3), (5) đúng theo cách đặt mô hình; (2) nhầm xác suất hoàn tất phạm vi với phần trăm công việc; (4) biến 95% thành chắc chắn. Dù kết luận toán học đúng với mô hình, dự báo thực tế vẫn phụ thuộc giả định.

### Bài tập B — Tính xác suất đơn giản

Giả sử mỗi tuần nhóm hoàn tất đúng **1 hoặc 2 item**, mỗi khả năng có xác suất **50%**, các tuần được giả định độc lập. Phạm vi còn **3 item**.

1. Liệt kê các cặp throughput trong hai tuần.
2. Xác suất hoàn tất **ít nhất 3 item sau hai tuần** là bao nhiêu?
3. Nếu mức xác suất cần đạt là 85%, mốc hai tuần có đủ không?

**Đáp án gợi ý:** Bốn cặp có xác suất bằng nhau là (1,1), (1,2), (2,1), (2,2). Ba cặp cuối đạt ít nhất 3 item, nên xác suất là **3/4 = 75%**. Mốc hai tuần chưa đạt mức 85% theo mô hình.

### Bài tập C — Chẩn đoán một dự báo không còn phù hợp

Nhóm có dự báo hoàn thành 15 story trong năm tuần dựa trên lịch sử. Sau hai tuần:

- Có 4 story thực sự Done, 5 story đang dở.
- Product Owner thêm 3 story vì phát hiện yêu cầu phân quyền bắt buộc.
- Một Developer chuyển sang hỗ trợ sự cố.
- Các story còn lại có nhiều tích hợp hơn giai đoạn dùng làm dữ liệu.

Hãy nêu:

1. Phạm vi còn lại cần được định nghĩa lại thế nào để tránh đếm sai item?
2. Những giả định nào của mô hình đã thay đổi?
3. Có nên dùng nguyên phân bố throughput lịch sử không? Vì sao?
4. Cần những kịch bản và thông điệp nào cho bên liên quan?
5. Có thể giao một lát cắt giá trị an toàn sớm hơn mà không bỏ qua phân quyền không?

**Gợi ý:** Các item đang dở **không tự được tính Done**. Cần ghi cả scope growth và giảm năng lực; lịch sử cần được đánh giá lại về tính đại diện. Phương án điều chỉnh phạm vi chỉ hợp lệ khi phần còn lại tạo giá trị và đạt tiêu chuẩn bắt buộc.

### Bài tập D — Viết một báo cáo dự báo

Sử dụng mẫu ngắn sau và tự chọn số liệu **có nguồn** (hoặc ghi rõ nếu chỉ là dữ liệu giả định):

~~~text
Điều kiện được coi là hoàn thành:
Phạm vi còn lại và cách chia item:
Ngày bắt đầu/đơn vị thời gian:
Nguồn throughput/cycle time:
Phương pháp tạo phân bố:
Xác suất hoàn thành trước hạn D:
Các mốc P50/P85/P95:
Khoảng thời gian và xác suất tương ứng (nếu cần):
Giả định quan trọng:
Rủi ro chưa được mô hình hóa:
Phương án giữ/giảm phạm vi/tháo phụ thuộc/đổi mốc:
Khi nào cập nhật, ai chịu trách nhiệm:
~~~

Một báo cáo tốt phải **diễn giải được xác suất bằng ngôn ngữ dễ hiểu** và tách dữ liệu đã quan sát khỏi các giả định chưa chắc chắn.

## 21. Checklist trước khi công bố dự báo

- [ ] Đã nói rõ **đang dự báo sự kiện gì**: Done, release hay outcome.
- [ ] Phạm vi còn lại có danh sách, định nghĩa và **không bỏ sót công việc chất lượng bắt buộc**.
- [ ] Đã thống nhất mốc đầu/cuối, ngày làm việc hay tuần lịch, đơn vị và ranh giới đo.
- [ ] Dữ liệu lịch sử đủ phù hợp; đã xem cả kỳ throughput bằng 0 và các item lâu chưa Done.
- [ ] Đã xem sự khác biệt về kích thước/loại item, phụ thuộc, năng lực và ngày nghỉ.
- [ ] Đã chọn mô hình có thể giải thích được, không tạo sự chính xác giả.
- [ ] Đã tách **xác suất đạt hạn D**, **mốc phân vị** và **xác suất rơi trong một khoảng**.
- [ ] Không đánh đồng phân vị với phần trăm công việc đã hoàn thành.
- [ ] Không gọi mốc P85/P95 là lời bảo đảm và không lạm dụng thuật ngữ “khoảng tin cậy”.
- [ ] Đã nêu những rủi ro có thể **nằm ngoài dữ liệu hoặc mô hình**.
- [ ] Các phương án điều chỉnh phạm vi vẫn tạo giá trị và bảo vệ Definition of Done.
- [ ] Đã so kết quả dự báo cũ với kết quả thực tế khi có đủ dữ liệu để cải thiện mô hình.
- [ ] Product Owner, Developers và các bên liên quan hiểu **đánh đổi giữa thời gian, phạm vi và rủi ro**.
- [ ] Có người phụ trách và nhịp cập nhật khi điều kiện thay đổi.
- [ ] Các chỉ số giúp cải thiện hệ thống, không bị dùng làm chỉ tiêu đánh giá cá nhân thiếu ngữ cảnh.

## 22. Tài liệu đọc tiếp và kết luận

- [Manifesto for Agile Software Development](https://agilemanifesto.org/): các giá trị và nguyên tắc về giao phần mềm tăng dần, hợp tác và thích ứng với thay đổi.
- [The Scrum Guide](https://scrumguides.org/): Product Backlog, Sprint Planning, Sprint Goal, Increment và Definition of Done; Scrum không yêu cầu một phương pháp ước lượng cụ thể.
- [The Kanban Guide](https://kanbanguides.org/): workflow, WIP, throughput, cycle time, work item age và Service Level Expectation.
- [Kanban University](https://kanban.university/): các tài nguyên thực hành về flow, dự báo và quản lý dịch vụ theo Kanban.
- Douglas W. Hubbard, *How to Measure Anything* (nhiều ấn bản): tư duy đo lường bất định và ra quyết định bằng xác suất.
- Daniel S. Vacanti, *Actionable Agile Metrics for Predictability* (2015): góc nhìn thực hành về phân bố flow, tính dự đoán và số liệu cycle time.

**Điểm cần nhớ:** Dự báo Agile có ích không phải vì biến tương lai thành chắc chắn, mà vì **biểu diễn được bất định đủ trung thực để đưa ra lựa chọn tốt hơn**. Khi nói “x% khả năng hoàn thành trước ngày D” hoặc “mốc P85 là tuần X”, hãy luôn nói kèm **sự kiện được dự báo, dữ liệu, giả định, phạm vi, chất lượng và kế hoạch cập nhật**. Nhóm càng giao giá trị sớm, đo flow nhất quán và học từ phản hồi thực tế, dự báo càng có cơ hội trở thành công cụ cải tiến thay vì một con số hứa hẹn thiếu căn cứ.
