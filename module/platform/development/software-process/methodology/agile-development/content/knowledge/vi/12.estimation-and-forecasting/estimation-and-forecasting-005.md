# Ước lượng theo độ lớn hoặc khoảng khi chưa đủ thông tin

## Mục tiêu học tập

Sau bài học, bạn có thể:

1. Giải thích vì sao một **ước lượng thô về độ lớn** hoặc một **khoảng ước lượng có điều kiện** thường phù hợp hơn một con số chính xác giả khi thông tin còn thiếu.
2. Phân biệt **độ lớn công việc (size)**, **nỗ lực (effort)**, **thời gian trôi qua (elapsed time)**, **dự báo (forecast)** và **cam kết (commitment)**.
3. Áp dụng T-shirt sizing, ước lượng tương đối bằng story point, so sánh theo hạng mục tham chiếu và ước lượng theo kịch bản để hỗ trợ quyết định backlog.
4. Nêu rõ giả định, rủi ro, phụ thuộc và mức độ tin cậy; nhận biết khi nào cần chia nhỏ user story hoặc thực hiện một hoạt động khám phá có giới hạn.
5. Dùng số liệu thực tế như throughput và cycle time để cải thiện dự báo mà không biến ước lượng thành thước đo năng suất cá nhân.

## 1. Vấn đề: cần quyết định khi chưa biết hết chi tiết

Trong phát triển phần mềm Agile, đội thường cần quyết định **có nên đầu tư**, **nên ưu tiên hạng mục nào** hoặc **có thể giao gì trước một mốc quan trọng** khi yêu cầu, thiết kế hoặc phụ thuộc chưa được làm rõ hoàn toàn.

Giả sử Product Owner nhận ba đề xuất cho nền tảng học trực tuyến:

- Hiển thị nút **“Tiếp tục học”** trên trang chủ.
- Đồng bộ vị trí học khi người dùng chuyển qua lại giữa hai thiết bị.
- Cho phép tải bài học để sử dụng khi không có mạng.

Nếu nhóm trả lời ngay rằng mỗi tính năng cần chính xác 6, 13 và 21 ngày mà chưa tìm hiểu dữ liệu, quyền truy cập, công nghệ hoặc bản quyền nội dung, các con số này có thể tạo **ảo tưởng chắc chắn**. Nếu nhóm từ chối mọi ước lượng cho đến khi đặc tả hoàn hảo, quyết định ưu tiên cũng bị đình trệ.

**Ước lượng theo độ lớn hoặc khoảng** là cách diễn đạt phù hợp với mức hiểu biết hiện có. Ví dụ:

> “Nút ‘Tiếp tục học’ hiện được xem là **nhỏ** nếu API tiến độ đã sẵn sàng; đồng bộ hai thiết bị là **trung bình đến lớn** vì chưa biết quy tắc xung đột; offline là **rất lớn/chưa đủ dữ liệu để ước lượng đáng tin**. Chúng ta cần một spike để xác minh ràng buộc bản quyền và lưu trữ trước khi chọn phạm vi.”

Phát biểu này không cung cấp ngày giao chính xác, nhưng **đủ giúp so sánh cơ hội và xác định điều cần học tiếp**.

### Nguyên tắc cốt lõi

> **Độ chính xác của câu trả lời không nên vượt quá độ chắc chắn của thông tin đầu vào.**

Ước lượng là một công cụ hỗ trợ thảo luận và quyết định, không phải mục tiêu của Agile. Với một số loại việc lặp lại, đội còn có thể dự báo từ dữ liệu dòng công việc **mà không cần gán story point cho từng hạng mục**.

## 2. Phân biệt năm khái niệm dễ nhầm

| Khái niệm | Câu hỏi trả lời | Ví dụ | Điều không nên suy diễn |
| --- | --- | --- | --- |
| **Size — độ lớn** | So với những việc khác, hạng mục này lớn hoặc phức tạp đến đâu? | Story A nhỏ hơn story B theo cách đánh giá của đội. | Size không tự động bằng số ngày. |
| **Effort — nỗ lực** | Cần bao nhiêu công sức lao động để hoàn tất theo phạm vi đã chọn? | Ước tính 5–9 ngày công cho một lát cắt trong điều kiện đã nêu. | Ngày công không phải ngày lịch; thêm người không luôn rút ngắn tương ứng. |
| **Duration/elapsed time — thời gian thực tế** | Từ lúc bắt đầu đến hoàn tất phải chờ bao lâu? | Việc cần 3 ngày công nhưng chờ đối tác 8 ngày, kéo dài hơn 1 tuần lịch. | Không thể suy ra chỉ từ effort. |
| **Forecast — dự báo** | Với dữ liệu, năng lực và giả định hiện có, khi nào hoặc bao nhiêu việc có khả năng hoàn thành? | “Dự kiến 3–5 tuần nếu không xuất hiện phụ thuộc mới.” | Không phải một cam kết chắc chắn. |
| **Commitment — cam kết** | Đội hoặc tổ chức xác nhận trách nhiệm gì, trong giới hạn nào? | “Chỉ phát hành khi test phân quyền và dữ liệu đạt tiêu chuẩn.” | Không thể tạo ra bằng cách viết một con số ước lượng lên hợp đồng. |

Trong Scrum, **Sprint Goal** là cam kết gắn với Sprint Backlog, chứ không đồng nghĩa “mọi Product Backlog Item được dự báo ở Sprint Planning phải hoàn tất bằng mọi giá”. Developers có thể làm rõ và thương lượng phạm vi khi học được điều mới, miễn không làm nguy hiểm Sprint Goal.

### Ví dụ ngày công và ngày lịch

Một công việc cần **6 ngày công** theo giả định có một người đủ kỹ năng. Nhưng nếu người đó chỉ có hai ngày mỗi tuần cho dự án và phải chờ môi trường tích hợp, thời gian hoàn tất theo lịch có thể lâu hơn nhiều. Ngược lại, một số phần độc lập có thể làm song song, nhưng phối hợp và tích hợp vẫn có chi phí.

Vì vậy, trước khi nói “6 ngày”, phải hỏi **đó là sáu ngày công, sáu ngày làm việc liên tiếp hay sáu ngày lịch** và giả định về nguồn lực là gì.

## 3. Vì sao bất định phải xuất hiện trong ước lượng?

Một tính năng có thể chứa nhiều nguồn bất định, không chỉ “viết code mất bao lâu”.

| Nguồn bất định | Dấu hiệu | Tác động lên ước lượng |
| --- | --- | --- |
| **Nhu cầu/nghiệp vụ** | Chưa biết người dùng cần gì; tiêu chí chấp nhận còn mâu thuẫn | Phạm vi có thể đổi hoặc cần thử nghiệm trước khi làm. |
| **Kỹ thuật** | API chưa được thử, kiến trúc lạ, hiệu năng chưa có dữ liệu | Công việc có thể cần spike và kiểm thử tích hợp. |
| **Dữ liệu** | Migration, quyền truy cập, tình trạng dữ liệu cũ chưa rõ | Phát sinh nhiều trường hợp xử lý ngoại lệ và rủi ro sửa sai. |
| **Phụ thuộc** | Đội khác hoặc nhà cung cấp chưa xác nhận khả năng và lịch | Lead time có thể tăng dù effort nội bộ ít. |
| **Năng lực** | Nhân sự còn phải trực vận hành hoặc xử lý việc khẩn | Throughput dự kiến có thể khác lịch sử. |
| **Chất lượng/tuân thủ** | Chưa rõ yêu cầu bảo mật, kiểm định, tải hoặc vận hành | Có thể cần thêm bằng chứng, quy trình phê duyệt và thời gian chờ. |

Một số bất định có thể giảm nhờ nghiên cứu; một số chỉ bộc lộ khi sản phẩm được thử trong thực tế. Mức hiểu biết thường tăng theo thời gian, nhưng **không có quy luật đảm bảo rằng khoảng ước lượng tự động thu hẹp đều đặn**. Nếu phát hiện rủi ro mới, khoảng hợp lý có thể còn rộng hơn.

### Ví dụ cùng một yêu cầu, hai mức hiểu biết

**Lần đầu nghe yêu cầu:**

> “Cho phép tải bài học ngoại tuyến” — có thể là **L/XL**, chưa rõ bản quyền, đồng bộ, dung lượng, mã hóa và thiết bị mục tiêu.

**Sau một cuộc khảo sát và spike:**

> “Chỉ tải tệp PDF được phép cho học viên còn quyền truy cập, trên ứng dụng di động hiện tại; không đồng bộ ghi chú khi offline” — có thể được chia thành vài story nhỏ hơn và mỗi story có cơ sở để ước lượng cụ thể hơn.

Khoảng ước lượng thay đổi **vì phạm vi và kiến thức đã thay đổi**, không phải vì người thực hiện “ước lượng chưa tốt” trong lần đầu.

## 4. Chọn mức ước lượng phù hợp với quyết định

Đừng dùng cùng một kỹ thuật cho mọi loại câu hỏi.

| Quyết định hiện tại | Thông tin thường đủ dùng | Ví dụ cách diễn đạt |
| --- | --- | --- |
| Có nên nghiên cứu cơ hội? | Phân loại nhỏ/vừa/lớn, rủi ro nổi bật, giá trị giả định | “Lớn nhưng tác động tiềm năng cao; cần xác minh nhu cầu.” |
| Nên xếp thứ tự những Product Backlog Item nào? | Độ lớn tương đối, phụ thuộc, chi phí trì hoãn, độ tin cậy | “Hạng mục A nhỏ và có bằng chứng; B lớn, cần spike.” |
| Có sẵn sàng bắt đầu lát cắt trong Sprint hoặc dòng việc? | User story, ví dụ, tiêu chí chấp nhận, phụ thuộc và khả năng kiểm thử | “Lát cắt đầu đủ rõ; phần đồng bộ cạnh tranh chưa sẵn sàng.” |
| Có thể giao trước mốc nào? | Dữ liệu throughput/cycle time, phạm vi tối thiểu, năng lực, dự báo có điều kiện | “Trong điều kiện hiện tại, có vài kịch bản thời gian; sẽ cập nhật sau test API.” |
| Có nên cam kết ngày cố định? | Phạm vi bắt buộc, quyền quyết định, dữ liệu, rủi ro, phương án dự phòng và nghĩa vụ | “Giữ ngày nhưng điều chỉnh phần tùy chọn; không bỏ tiêu chí an toàn.” |

### Quy tắc thực hành

1. **Hỏi quyết định sắp tới là gì**, trước khi chọn cách ước lượng.
2. **Chỉ làm rõ chi tiết có thể thay đổi quyết định**: một tính năng còn xa có thể không cần chia thành 30 task.
3. **Diễn đạt sự không chắc chắn** bằng khoảng, điều kiện hoặc nhãn “chưa đủ dữ liệu”.
4. **Làm rõ chuyện gì cần học tiếp**, ai chịu trách nhiệm và khi nào sẽ ước lượng lại.
5. **Dùng phản hồi thực tế** để cải thiện cách dự báo, không cố bảo vệ con số cũ.

## 5. Ước lượng thô bằng T-shirt sizing

**T-shirt sizing** phân loại độ lớn tương đối bằng các nhãn như **XS, S, M, L, XL**. Đây là công cụ trao đổi nhanh khi chưa cần số giờ hoặc ngày cụ thể.

### 5.1. Ví dụ bảng quy ước nội bộ

| Nhãn | Cách hiểu minh họa | Ví dụ trong nền tảng học |
| --- | --- | --- |
| **XS** | Thay đổi rất nhỏ, rủi ro thấp, ít thành phần bị ảnh hưởng | Sửa nhãn và thông điệp trạng thái đã có tiêu chí rõ. |
| **S** | Một hành vi đơn giản, có thể kiểm tra trong một lát cắt nhỏ | Hiển thị liên kết tới bài gần nhất từ dữ liệu sẵn có. |
| **M** | Cần phối hợp vài thành phần, có một số ngoại lệ cần kiểm tra | Thêm luồng lưu/đọc tiến độ với API đã được xác nhận. |
| **L** | Có nhiều quy tắc hoặc phụ thuộc; cần chia nhỏ trước khi thực hiện | Đồng bộ giữa hai thiết bị kèm xử lý cập nhật cạnh tranh. |
| **XL** | Phạm vi lớn hoặc chưa rõ đến mức ước lượng trực tiếp ít hữu ích | Offline cho mọi loại nội dung và mọi thiết bị. |

Những mô tả này **chỉ là quy ước ví dụ của một đội**. Đội khác có sản phẩm, nền tảng và kỹ năng khác nhau sẽ có mốc tham chiếu khác. Nhãn XL thường là tín hiệu cần **chia nhỏ hoặc khám phá thêm**, không phải lời tuyên bố rằng hạng mục chắc chắn mất một số tuần cố định.

### 5.2. Cách thực hiện nhanh

1. Chọn vài hạng mục mà đội đã hiểu và hoàn tất làm **mẫu tham chiếu**.
2. Cùng đọc mục tiêu và phạm vi của hạng mục mới.
3. Mỗi người chọn nhãn dựa trên độ lớn, tính phức tạp, kiểm thử và bất định mà đội đã thống nhất đưa vào quy ước.
4. Nếu ý kiến khác nhau, hỏi **“Điều gì khiến bạn xem việc này lớn hơn?”**, không hỏi “Ai chọn nhãn đúng?”.
5. Ghi giả định, rủi ro và phần còn mở; đánh dấu nhãn tạm thời nếu còn bất định lớn.
6. Khi hạng mục đến gần thời điểm thực hiện, chia nhỏ và làm rõ; không kéo nhãn thô trực tiếp thành cam kết ngày giao.

**Ví dụ:** Một developer chọn M cho đồng bộ tiến độ vì API đã có; tester chọn XL vì API chưa có cách xử lý gửi lại yêu cầu. Phần quan trọng không phải lấy trung bình thành L, mà là **phát hiện rủi ro bị bỏ sót** và quyết định thử API trước.

### Khi nào T-shirt sizing phù hợp?

- So sánh nhiều ý tưởng trong một phiên roadmap hoặc backlog sơ bộ.
- Thảo luận cơ hội khi công việc chưa chia thành story có thể bắt đầu ngay.
- Nhận diện hạng mục lớn cần khám phá hoặc phân tách.

Không phù hợp để quy định “M luôn bằng 3 ngày, L bằng 5 ngày” cho mọi trường hợp; việc đó làm mất ý nghĩa ước lượng thô và che bớt bất định.

## 6. Ước lượng tương đối bằng story point

**Story point** là đơn vị tương đối do **chính đội** định nghĩa để so sánh độ lớn của các Product Backlog Item. Một số đội xem xét tổng hợp công sức, phức tạp và bất định; đội cần thống nhất cách diễn giải và dùng nhất quán.

Các mức thường gặp như **1, 2, 3, 5, 8, 13, 21** tạo khoảng cách tăng dần khi độ lớn tăng. Đây không phải các số giờ, ngày hoặc công thức bắt buộc. Với hạng mục quá lớn (ví dụ 13 hoặc 21 theo quy ước của đội), việc chia nhỏ thường hữu ích hơn tranh luận xem nó phải là 13 hay 21.

### 6.1. Dùng story tham chiếu

Giả sử đội thống nhất:

- **2 điểm:** Hiển thị nhãn tiến độ từ API đã có, test đơn giản.
- **5 điểm:** Lưu và hiển thị bài gần nhất, có vài ngoại lệ, API ổn định.
- **8 điểm:** Thêm xử lý gửi lại yêu cầu và tình huống lỗi tích hợp.

Khi gặp hạng mục “Đồng bộ tiến độ trên hai thiết bị”, nhóm có thể so sánh:

> “Nó lớn hơn hạng mục 8 điểm vì phải giải quyết cập nhật cạnh tranh và kiểm thử lỗi mạng. Thay vì gán ngay 13 hay 21, chúng ta cần chia thành lát cắt và xác minh khả năng API.”

**Không có giá trị story point phổ quát.** Hai đội có thể cho cùng một story hai mức khác nhau mà cả hai vẫn nhất quán với thang đo riêng của họ.

### 6.2. Planning Poker và bất đồng hữu ích

Một vòng Planning Poker có thể diễn ra:

1. Product Owner hoặc người nắm nhu cầu trình bày story, outcome, tiêu chí chấp nhận và ràng buộc.
2. Developers và những người thực hiện/kiểm chứng đặt câu hỏi.
3. Các thành viên ước lượng **độc lập trước khi công khai**.
4. Cùng xem điểm thấp và cao nhất, hỏi về giả định khác nhau.
5. Điều chỉnh hiểu biết, chia nhỏ hoặc chọn ước lượng tạm thời nếu đủ rõ.

Đích đến không phải ép mọi người chọn cùng số sau nhiều vòng. **Bất đồng có thể là tín hiệu cần tìm hiểu**, nhất là khi một người biết phụ thuộc kỹ thuật hoặc ca lỗi mà người khác bỏ sót.

### 6.3. Những điều story point không đo

- Không đo số giờ làm việc của từng cá nhân.
- Không là cơ sở hợp lý để so sánh năng suất giữa các đội có thang đo khác nhau.
- Không phải tiền tệ để hứa “trả thêm hai người sẽ có thêm 20 điểm”.
- Không đo trực tiếp giá trị khách hàng.
- Không chứng minh chất lượng hoặc tính sẵn sàng phát hành.

Nếu ước lượng story point làm tốn quá nhiều thời gian, có thể dùng **đếm hạng mục tương đối nhỏ và nhất quán**, xem throughput/cycle time hoặc một cách dự báo khác. Agile không bắt buộc phải có story point.

## 7. Khi nào nên ước lượng bằng một khoảng?

Một **khoảng ước lượng** nói rằng kết quả hợp lý nằm giữa những mức khác nhau **với điều kiện được nêu rõ**, thay vì giả vờ tồn tại một điểm chắc chắn.

Ví dụ:

> “Với phạm vi chỉ đồng bộ **bài học gần nhất** qua API hiện có, và nếu contract test thành công, đội dự kiến cần **5–9 ngày công**. Nếu API thiếu cơ chế xử lý phiên bản và phải bổ sung dịch vụ, khoảng có thể mở rộng đáng kể; cần kiểm tra trước khi đưa ra lịch.”

Điểm mạnh của phát biểu này không chỉ ở “5–9”, mà còn ở **phạm vi, giả định và điều kiện thay đổi**.

### 7.1. Ba kịch bản thay vì một số cố định

Có thể nêu ba kịch bản:

| Kịch bản | Giả định minh họa | Nỗ lực ví dụ |
| --- | --- | ---: |
| **Thuận lợi** | API đã đủ, dữ liệu sạch, không có phụ thuộc mới | 5 ngày công |
| **Cơ sở** | Cần thêm kiểm thử và xử lý ngoại lệ đã biết | 8 ngày công |
| **Bất lợi nhưng còn trong phạm vi dự kiến** | API phải chỉnh, có thêm ca đồng bộ lỗi và kiểm thử lại | 13 ngày công |

Những con số là **giả định của tình huống học tập**, không phải chuẩn thời gian cho sản phẩm thật. Kịch bản bất lợi cũng **không phải mức tối đa tuyệt đối**: có thể xuất hiện rủi ro ngoài mô hình khiến công việc còn lớn hơn.

Có đội dùng cách hỏi “lạc quan – nhiều khả năng – bi quan” hoặc ước lượng ba điểm để tư duy. Tuy nhiên, nếu chưa có dữ liệu về phân bố, **không được tự biến ba điểm thành xác suất 80% hoặc 95%**. Các công thức kiểu PERT dựa trên những giả định mô hình riêng; một “giá trị kỳ vọng” tính từ chúng không phải khoảng tin cậy được bảo đảm.

### 7.2. Khoảng theo ngày công, ngày lịch hay số hạng mục?

Phải ghi **đơn vị và mốc đo**:

- **5–9 ngày công:** Tổng công sức dự kiến của phạm vi xác định; chưa xét đầy đủ chờ đợi và lịch.
- **2–4 tuần lịch:** Dự báo về thời gian từ mốc bắt đầu đến khi hoàn thành, đã giả định năng lực và phụ thuộc.
- **8–12 hạng mục tương đương:** Dự báo khối lượng công việc sau khi chia nhỏ; cần định nghĩa “hạng mục tương đương”.

Không thể cộng các khoảng không đồng nhất hoặc đổi story point sang giờ bằng một tỷ lệ phổ quát.

### 7.3. Cách ghi một khoảng có thể dùng để quyết định

~~~text
HẠNG MỤC: Hiển thị và mở lại bài học gần nhất từ thiết bị khác.
MỤC ĐÍCH ƯỚC LƯỢNG: So sánh phạm vi cho đợt phát hành sắp tới.
ĐƠN VỊ: Ngày công của đội cho lát cắt đã xác định.
PHẠM VI: Trực tuyến, cùng tài khoản, chưa hỗ trợ offline.
KHOẢNG THÔ: 5–9 ngày công theo các ví dụ và hệ thống hiện tại.
ĐIỀU KIỆN: API tiến độ đã có dữ liệu cần thiết, không đổi schema lớn.
ĐIỂM CHƯA BIẾT: Cơ chế gửi lại request và xử lý xung đột tiến độ.
RỦI RO: Nếu API không hỗ trợ phiên bản, cần điều tra lại phạm vi.
BƯỚC TIẾP: Contract test trước khi lập kế hoạch triển khai chi tiết.
NGƯỜI/THỜI ĐIỂM XEM LẠI: Developers cùng Product Owner sau kết quả test.
~~~

Khoảng này giúp Product Owner hiểu **điều gì có thể làm kế hoạch thay đổi**, thay vì chỉ đọc một con số rồi coi như lời hứa.

## 8. Nên chia nhỏ hay tiếp tục ước lượng?

Nếu một hạng mục có mức chênh lệch đánh giá rất lớn, khả năng cao nhóm đang nói về **những phạm vi khác nhau**.

### Ví dụ hạng mục quá rộng

> “Cho phép học offline cho tất cả video, PDF và bài kiểm tra trên mọi thiết bị, đồng bộ khi có mạng.”

Những phần có thể tách:

1. Quan sát nhu cầu offline với một nhóm người dùng mạng yếu.
2. Cho phép tải **một loại tài liệu được quyền tải** và truy cập khi offline.
3. Quản lý quyền truy cập và hạn sử dụng của tệp đã tải.
4. Đồng bộ trạng thái học khi có mạng trở lại theo quy tắc rõ.
5. Mở rộng hỗ trợ loại nội dung khác sau khi đánh giá giá trị và chi phí.

Mỗi lát cắt cần rõ **giá trị người dùng** và **tiêu chí an toàn**. Không được tách theo kiểu “làm database trước, giao chức năng không dùng được sau” rồi coi đó là increment đã tạo giá trị. Các task kỹ thuật có thể nằm trong một story xuyên suốt.

### Tín hiệu phải chia hoặc khám phá

- Các thành viên có hiểu khác nhau về kết quả của story.
- Hạng mục phụ thuộc một quyết định kiến trúc hoặc quy tắc nghiệp vụ chưa được xác nhận.
- Có nhiều dòng giá trị độc lập có thể giao riêng.
- Mức ước lượng chỉ là XL/“không biết” và sẽ được dùng để cam kết mốc gần.
- Có thể thực hiện một phép thử nhỏ để loại bỏ rủi ro chính.

### Timeboxed spike để giảm bất định

Ví dụ:

| Thành phần | Nội dung minh họa |
| --- | --- |
| **Câu hỏi** | API hiện tại có hỗ trợ lưu tiến độ an toàn khi hai thiết bị gửi cập nhật gần nhau không? |
| **Phạm vi** | Thiết lập tình huống gửi lặp/cạnh tranh trên môi trường thử, không đụng dữ liệu thật. |
| **Timebox** | Hai ngày làm việc, chỉ là giới hạn của ví dụ. |
| **Bằng chứng** | Kết quả contract/integration test và giới hạn kỹ thuật. |
| **Đầu ra** | Khuyến nghị cách xử lý, rủi ro còn lại, lát cắt backlog và khoảng mới nếu đủ thông tin. |

Một spike **không đảm bảo** giảm mọi bất định. Nó có thể cho thấy hạng mục lớn hơn dự kiến hoặc cần thay đổi Product Goal/phạm vi. Giá trị của spike là **tri thức đủ để quyết định tiếp**.

## 9. Quy trình ước lượng cộng tác khi thông tin còn thiếu

Thay vì yêu cầu từng cá nhân gửi “bao nhiêu ngày” vào cuối một cuộc họp, nhóm có thể tổ chức một phiên ngắn:

### Bước 1 — Chốt mục đích của ước lượng

Chỉ cần thứ tự ưu tiên sơ bộ, chọn một hạng mục để khám phá hay cần dự báo phát hành? Mục đích khác nhau dẫn đến độ chi tiết khác nhau.

### Bước 2 — Thống nhất phạm vi và điều kiện chất lượng

Đọc user story, ví dụ, tiêu chí chấp nhận, Definition of Done liên quan và ranh giới:

- Có bao gồm migration dữ liệu, bảo mật hoặc xử lý lỗi mạng không?
- Có cần test trên thiết bị mục tiêu và tích hợp hệ thống khác không?
- Có đủ quyền truy cập môi trường và người có quyền xác nhận nghiệp vụ không?

Một ước lượng chưa gồm kiểm thử và tích hợp không nên bị trình bày như nỗ lực cần để giao increment hoàn chỉnh.

### Bước 3 — Chọn cách biểu diễn phù hợp

- T-shirt size cho cơ hội hoặc hạng mục xa.
- Relative/story points cho các hạng mục đội đã có tham chiếu.
- Khoảng ngày công hoặc thời gian có điều kiện khi cần thảo luận nguồn lực.
- Dữ liệu throughput/cycle time để dự báo một tập hạng mục đã tương đối chuẩn hóa.

### Bước 4 — Mỗi người tự đánh giá trước

Cho những người có chuyên môn liên quan tự chọn mức thô, tránh để người có quyền lực hoặc phát biểu đầu tiên kéo cả nhóm đến một con số.

### Bước 5 — Khai thác bất đồng

Hỏi người chọn mức cao và thấp nhất:

- “Bạn đang tính cả bước nào mà người khác chưa tính?”
- “Điều kiện nào khiến việc này là S thay vì L?”
- “Có rủi ro nào khiến ta **không thể đưa ra khoảng hữu ích** lúc này không?”
- “Nếu chỉ làm lát cắt đầu, giá trị và mức độ lớn thay đổi thế nào?”

### Bước 6 — Ghi ước lượng cùng giả định

Ví dụ: “M–L theo quy ước đội; phụ thuộc API chưa xác nhận; chưa tính offline; sẽ đánh giá lại sau contract test”.

### Bước 7 — Quyết định và xem lại

Product Owner quyết định thứ tự Product Backlog dựa trên giá trị, rủi ro và ý kiến kỹ thuật; Developers quyết định cách thực hiện và cung cấp dự báo phù hợp. Kết thúc bằng **lát cắt, bước học tiếp, người chịu trách nhiệm và mốc đánh giá lại**.

**Tránh** dùng sự chênh lệch ước lượng để đánh giá cá nhân. Mục tiêu là phát hiện kiến thức ẩn và giảm nguy cơ ra quyết định sai.

## 10. Ví dụ xuyên suốt: ước lượng ba cơ hội sản phẩm

Một đội đang ưu tiên các thay đổi cho nền tảng học trực tuyến. Mục tiêu là giúp học viên quay lại bài học nhanh hơn, trong khi duy trì quyền truy cập và dữ liệu chính xác.

### 10.1. Vòng 1 — Chỉ biết nhu cầu tổng quát

| Cơ hội | Độ lớn thô | Bằng chứng hiện có | Điều còn chưa biết |
| --- | --- | --- | --- |
| Nút “Tiếp tục học” | S–M | Nhiều người dùng nói khó tìm bài đã học | API tiến độ hiện tại có đủ thông tin để hiển thị không? |
| Đồng bộ hai thiết bị | L–XL | Có phản hồi về mất vị trí khi đổi thiết bị | Quy tắc xung đột, gửi lại request, dữ liệu cũ |
| Học offline | XL/không đủ dữ liệu | Một số người dùng mạng yếu quan tâm | Tỷ lệ sử dụng thực, bản quyền, mã hóa, lưu trữ, đồng bộ |

Đội chưa nên công bố ngày giao chính xác. Họ có thể chọn nút “Tiếp tục học” để kiểm chứng giá trị sớm và một spike nhỏ cho rủi ro đồng bộ, đồng thời nghiên cứu nhu cầu offline.

### 10.2. Vòng 2 — Sau khi làm rõ lát cắt

Giả sử kết quả trao đổi xác nhận:

- API có thể trả về bài gần nhất còn quyền truy cập.
- Lát cắt đầu chỉ hỗ trợ **mở đúng bài**, không khẳng định đồng bộ vị trí từng giây.
- Cần kiểm tra trường hợp tài khoản không có tiến độ hoặc khóa học bị thu hồi quyền.
- Bản thử cần hỗ trợ điện thoại và trình duyệt thông dụng của nhóm người dùng mục tiêu.

Story được viết lại:

> **Là** học viên đã đăng nhập, **tôi muốn** mở lại bài học hợp lệ gần nhất từ trang chủ **để** tiếp tục học mà không cần tìm kiếm.

Tiêu chí chấp nhận minh họa:

1. Khi có bài đã lưu và còn quyền truy cập, trang chủ hiển thị đúng bài theo quy tắc “gần nhất” đã thống nhất.
2. Khi nhấn “Tiếp tục học”, hệ thống mở đúng bài.
3. Khi không có tiến độ hợp lệ, không hiển thị bài học giả.
4. Không đọc được tiến độ của tài khoản khác.
5. Trường hợp dịch vụ lỗi được phản ánh rõ, không báo sai rằng người dùng chưa từng học.

Đội có thể ước lượng lại lát cắt từ S–M thành một mức tương đối cụ thể hơn hoặc một khoảng ngày công theo dữ liệu nội bộ. Độ tin cậy tăng **vì quy tắc và phụ thuộc quan trọng đã rõ**, không phải vì nhóm đã đổi phương pháp.

### 10.3. Vòng 3 — Phát hiện thay đổi kỹ thuật

Giả sử test tích hợp cho thấy API đôi khi trả dữ liệu cũ khi người học gửi cập nhật liên tục. Đây là thông tin mới:

- Nếu chỉ cần mở bài gần nhất và có cơ chế xử lý dữ liệu cũ an toàn, story có thể vẫn giữ phạm vi nhỏ.
- Nếu phải sửa kiến trúc lưu tiến độ để tránh mất dữ liệu, hạng mục đồng bộ là phần việc lớn hơn dự đoán.
- Đội cần báo Product Owner sự thay đổi của **giả định**, điều chỉnh ưu tiên backlog, tiêu chí chấp nhận và dự báo phát hành.

Một ước lượng mới khác cũ **không tự động chứng minh ước lượng trước sai về phương pháp**. Ước lượng đầu chỉ đúng trong những điều kiện đã ghi; điều kiện thực tế đã thay đổi.

## 11. Từ ước lượng hạng mục đến dự báo thời gian giao

Độ lớn tương đối và khoảng effort vẫn chưa trực tiếp trả lời “khi nào xong?”. Để dự báo, cần xét **công suất thực tế của dòng công việc**, phạm vi, phụ thuộc, lịch và các sự cố có thể xảy ra.

### 11.1. Throughput: đếm công việc hoàn tất

Giả sử một đội có dữ liệu sáu tuần với cách đếm hạng mục tương đối nhất quán:

| Tuần | Hạng mục hoàn tất |
| --- | ---: |
| 1 | 3 |
| 2 | 4 |
| 3 | 2 |
| 4 | 5 |
| 5 | 4 |
| 6 | 3 |
| **Tổng** | **21** |

Throughput trung bình là **21 / 6 = 3,5 hạng mục/tuần**. Nếu còn **14 hạng mục tương tự** thì:

- Theo nhịp trung bình: **14 / 3,5 = 4 tuần**.
- Nếu chỉ đạt 2 hạng mục/tuần: **7 tuần**.
- Nếu đạt 5 hạng mục/tuần: **2,8 tuần**.

Đây chỉ là **ba kịch bản số học minh họa**, không phải khoảng xác suất hoặc dự báo có độ tin cậy 90%. Điều kiện quan trọng là các hạng mục còn lại đủ tương đồng với lịch sử, quy tắc Done không đổi và không có phụ thuộc lớn mới. Độ dài dự báo có thể cần thêm dự phòng hoặc phương án giảm phạm vi.

Nếu một story XL đang nằm trong 14 hạng mục, **đếm tất cả như nhau có thể gây sai lệch**. Lúc đó cần chia nhỏ, phân nhóm kích thước hoặc dùng phương pháp dự báo thích hợp hơn.

### 11.2. Cycle time và work item age

- **Cycle time:** Thời gian từ lúc bắt đầu xử lý đến khi hoàn thành một việc theo mốc đo đã thống nhất.
- **Work item age:** Thời gian đã trôi qua kể từ khi một việc đang làm bắt đầu; giúp thấy hạng mục có nguy cơ mắc kẹt.
- **Lead time:** Có thể đo từ lúc yêu cầu được ghi nhận đến lúc hoàn thành; mốc bắt đầu phải được nêu rõ.
- **WIP:** Lượng công việc đã bắt đầu nhưng chưa hoàn thành.

Ví dụ, một thay đổi cần 2 ngày công nhưng bị chặn 9 ngày vì chờ API; cycle time kéo dài hơn effort rất nhiều. Chỉ ước lượng “2 ngày công” rồi hứa giao sau 2 ngày là nhầm **effort** với **thời gian theo lịch**.

Trong **Kanban**, quan sát phân bố cycle time, work item age và throughput giúp phát hiện nút thắt, cải thiện chính sách WIP và lập dự báo từ dữ liệu thực. Trong **Scrum**, dữ liệu này cũng có thể bổ sung cho việc lập kế hoạch Sprint hoặc release; không bị giới hạn ở một phương pháp.

### 11.3. Khi có đủ dữ liệu để dùng dự báo xác suất

Một số đội dùng phân vị cycle time hoặc mô phỏng Monte Carlo dựa trên lịch sử throughput để ước lượng khả năng hoàn thành trước một mốc. Điều này **cần dữ liệu phù hợp và giả định minh bạch**:

- Cách đếm và loại hạng mục còn tương đối ổn định.
- Năng lực và chính sách dòng việc không thay đổi đến mức lịch sử mất ý nghĩa.
- Các phụ thuộc hoặc rủi ro chưa được phản ánh trong dữ liệu được nêu riêng.
- Mốc hoàn tất và Definition of Done được hiểu nhất quán.

Nếu chỉ có vài hạng mục hoặc bối cảnh thay đổi mạnh, đừng đưa ra “xác suất 95%” như một con số có cơ sở khoa học. Một **khoảng kịch bản với điều kiện rõ** có thể trung thực hơn.

## 12. Sử dụng độ lớn và khoảng trong Scrum, Kanban, XP

| Cách tiếp cận | Cách áp dụng phù hợp | Điều cần tránh |
| --- | --- | --- |
| **Scrum** | Product Backlog được làm rõ dần; Developers ước lượng kích thước Product Backlog Item khi hữu ích; Sprint Planning dựa trên mục tiêu, năng lực, Done và thông tin hiện tại | Coi story point là cam kết ngày giao hoặc coi mọi việc chọn ở đầu Sprint phải hoàn thành dù phạm vi mới xuất hiện |
| **Kanban** | Theo dõi WIP, throughput, cycle time, work item age; dự báo từ dữ liệu dòng việc và làm rõ chính sách chọn hạng mục | Cố gán story point cho mọi ticket dù dữ liệu thực tế đã đủ phục vụ dự báo |
| **XP** | TDD, kiểm thử tự động, CI, refactor, pair programming giảm lỗi và tạo phản hồi kỹ thuật sớm, giúp thu hẹp bất định | Xem “code nhanh” là đủ mà không tính tích hợp, vận hành hoặc nhu cầu người dùng |

Trong Scrum Guide, các Developers chịu trách nhiệm **sizing Product Backlog Items**; Product Owner có thể giúp họ hiểu giá trị và những đánh đổi. Việc dùng story point, T-shirt sizing hay giờ công là **lựa chọn thực hành**, không phải yêu cầu bắt buộc của Scrum.

### Liên hệ với bốn giá trị Agile

- **Cá nhân và tương tác:** Ước lượng bằng đối thoại để phát hiện giả định khác nhau, thay vì ép số từ cấp quản lý.
- **Phần mềm hoạt động được:** Dự báo phải xét kiểm thử, tích hợp, Definition of Done và khả năng dùng được; không chỉ tính giờ code.
- **Cộng tác với khách hàng:** Thảo luận phạm vi tối thiểu, giá trị và chi phí chậm trễ cùng người có quyền quyết định.
- **Đáp ứng thay đổi:** Cập nhật ước lượng khi có bằng chứng mới, không che giấu lệch kế hoạch.

Ước lượng hữu ích khi nó giúp **ra quyết định có trách nhiệm**, còn kiểm tra increment và phản hồi sớm giúp quyết định sau tốt hơn.

## 13. Những sai lầm phổ biến

| Sai lầm | Vì sao nguy hiểm | Cách cải thiện |
| --- | --- | --- |
| **Đưa ra một ngày chính xác dù chưa hiểu phạm vi** | Tạo ảo tưởng chắc chắn; dễ bị dùng như cam kết | Dùng nhãn độ lớn/khoảng và nêu giả định, mức bất định. |
| **Đổi story point sang ngày theo tỷ lệ cố định** | Điểm chỉ mang nghĩa tương đối của một đội và có thể thay đổi theo cách chia việc | Dùng dữ liệu giao hàng thực, phân biệt effort và duration. |
| **So story point giữa các đội** | Không có thang chuẩn chung; tạo động cơ tăng điểm thay vì tăng giá trị | Đo outcome, chất lượng và dòng công việc phù hợp từng đội. |
| **Bắt đầu story XL như một hạng mục nguyên khối** | Rất nhiều rủi ro bị phát hiện muộn, khó nhận phản hồi | Chia thành lát cắt giá trị hoặc spike để giảm bất định. |
| **Giấu rủi ro khỏi khoảng ước lượng** | Người nhận chỉ thấy số và hiểu sai điều kiện | Ghi phạm vi, phụ thuộc, điều kiện và điểm đánh giá lại. |
| **Cộng số ngày công rồi gọi đó là ngày lịch** | Bỏ qua chờ đợi, nghỉ phép, phối hợp, review và test | Xem năng lực thực, lịch phụ thuộc và dữ liệu cycle time. |
| **Tính mọi ticket là như nhau** | Hạng mục lớn nhỏ khác nhau làm méo throughput | Làm nhỏ, chuẩn hóa chính sách hoặc phân nhóm dự báo. |
| **Dùng giá trị trung bình làm hạn chắc chắn** | Biến động và phần đuôi dài của phân bố bị bỏ qua | Thảo luận kịch bản, phân vị có dữ liệu và rủi ro ngoài mô hình. |
| **Lấy điểm cao làm thước đo năng suất cá nhân** | Khuyến khích thổi điểm, chia việc hình thức, che lỗi | Sử dụng ước lượng để phối hợp, không thưởng phạt cá nhân. |
| **Bỏ test/DoD để “giữ đúng ước lượng”** | Chuyển nợ chất lượng sang người dùng và vận hành | Điều chỉnh phạm vi hoặc thời hạn, giữ tiêu chuẩn an toàn bắt buộc. |
| **Không cập nhật sau khi học được điều mới** | Kế hoạch dựa trên giả định đã bị bác bỏ | Thực hiện re-estimation khi dữ kiện có tác động đến quyết định. |
| **Ước lượng mọi thứ quá chi tiết** | Tốn thời gian cho việc xa có thể đổi hoặc bị bỏ | Dùng ước lượng thô ở chân trời xa, làm rõ dần khi gần thực hiện. |

## 14. Mẫu ngắn để ghi một ước lượng có trách nhiệm

Không cần biểu mẫu dài cho mọi ticket; mẫu sau hữu ích khi đang chọn phạm vi hoặc trao đổi với bên liên quan.

| Trường | Nội dung cần ghi |
| --- | --- |
| **Quyết định cần hỗ trợ** | Chọn ưu tiên, bắt đầu Sprint Item, lập dự báo release hay thương lượng phạm vi? |
| **Hạng mục/lát cắt** | Kết quả người dùng, ranh giới, phần không bao gồm. |
| **Đơn vị** | XS/S/M/L/XL, story point theo quy ước đội, ngày công, ngày lịch hoặc hạng mục. |
| **Ước lượng** | Một mức thô hoặc khoảng/kịch bản có điều kiện. |
| **Tham chiếu** | Story đã hoàn thành tương tự hoặc dữ liệu lịch sử liên quan. |
| **Giả định quan trọng** | API, dữ liệu, năng lực, quyền truy cập, phụ thuộc. |
| **Độ bất định** | Điều chưa biết có thể làm thay đổi kết luận. |
| **Tiêu chuẩn hoàn thành** | Acceptance criteria, Definition of Done, kiểm thử, vận hành và nghĩa vụ liên quan. |
| **Bước giảm bất định** | Làm rõ yêu cầu, chia nhỏ, spike, test tích hợp, phỏng vấn người dùng. |
| **Điểm xem lại** | Sau kết quả học hỏi hoặc khi bối cảnh thay đổi. |

### Một câu báo cáo tốt hơn “chắc chắn xong”

> “Với phạm vi chỉ mở bài gần nhất trên thiết bị có mạng và API hiện tại đã qua kiểm tra, đội đánh giá đây là hạng mục nhỏ đến vừa. Việc đồng bộ hai thiết bị còn chưa chắc do quy tắc xử lý xung đột chưa được xác nhận. Chúng tôi sẽ chạy contract test và chia nhỏ hạng mục trước khi đưa ra dự báo phát hành. Phần thử nghiệm phải đáp ứng tiêu chí phân quyền và Definition of Done trước khi xem là hoàn thành.”

Thông điệp này cho thấy **điều đã biết, điều chưa biết, ảnh hưởng quyết định và hành động tiếp theo**.

## 15. Bài tập thực hành

### Bài tập 1 — Chọn cách ước lượng

Đội có ba yêu cầu:

1. “Thêm một thông điệp hướng dẫn vào trang chủ” — tiêu chí và cách triển khai đã rõ.
2. “Đồng bộ toàn bộ tiến độ học trên hai thiết bị” — chưa có quy tắc xung đột.
3. “Phát triển chương trình học offline cho mọi khóa” — chưa khảo sát nhu cầu, bản quyền và nền tảng.

**Yêu cầu:** Với mỗi việc, chọn T-shirt size, relative story point, khoảng effort hay “chưa thể ước lượng đáng tin” cho **quyết định ưu tiên ban đầu**. Giải thích, chỉ ra câu hỏi hoặc phép thử để tăng mức hiểu biết.

**Gợi ý:** Việc 1 có thể so sánh với story đã hoàn tất; việc 2 cần làm rõ và có thể ước lượng thô L; việc 3 có thể chỉ xếp XL/chưa rõ rồi tách thành cơ hội khám phá.

### Bài tập 2 — Phân biệt size, effort và duration

Một developer nói: “Việc này cần khoảng 4 ngày công; chắc chắn thứ Năm là xong.” Nhưng developer chỉ rảnh hai ngày trong tuần này; API của đối tác chưa có lịch xác nhận.

**Yêu cầu:** Chỉ ra điểm suy luận sai, lập danh sách giả định cần xác nhận và viết lại thông điệp với dự báo có điều kiện.

**Gợi ý:** Bốn ngày công không bằng bốn ngày lịch. Cần xem năng lực, lịch nghỉ, phụ thuộc, kiểm thử, Definition of Done và tình trạng bị chặn.

### Bài tập 3 — Dự báo đơn giản từ throughput

Một đội hoàn tất số hạng mục mỗi tuần: **2, 4, 3, 5, 4, 3**. Backlog còn **14 hạng mục được xem là tương tự**.

**Yêu cầu:** Tính throughput trung bình, đưa ra ba kịch bản số học với nhịp 2, nhịp trung bình và nhịp 5 việc/tuần. Nêu ít nhất bốn yếu tố có thể làm dự báo sai.

**Đáp án tham khảo:** Tổng **21 hạng mục/6 tuần = 3,5/tuần**. Các kịch bản tương ứng: **7 tuần**, **4 tuần**, **2,8 tuần**. Đây là phép tính minh họa, **không phải xác suất hoàn thành**. Phụ thuộc, thay đổi phạm vi, lỗi sản xuất, độ lớn item khác nhau, nghỉ phép và chính sách Done có thể làm thay đổi thực tế.

### Bài tập 4 — Xây khoảng theo kịch bản

Nhóm đang cân nhắc chức năng hiển thị tiến độ học. Một ý kiến cho rằng chỉ cần dùng API có sẵn; ý kiến khác lo dữ liệu cũ cần migration.

**Yêu cầu:** Viết ba kịch bản (thuận lợi, cơ sở, bất lợi), trong mỗi kịch bản nêu **giả định, phạm vi cần làm và yếu tố khiến kịch bản xảy ra**. Bạn có thể dùng số ngày công minh họa nhưng phải giải thích nguồn gốc và không gắn xác suất tùy ý.

**Gợi ý:** Hãy xác định một test hoặc spike giúp phân biệt kịch bản sớm nhất, rồi thống nhất khi nào đánh giá lại.

### Bài tập 5 — Planning Poker có bất đồng

Trong một buổi ước lượng, ba người cho story “Ghi danh khóa miễn phí” các mức **3, 5 và 13 điểm**:

- Người chọn 3 nghĩ chỉ thêm nút và gọi API sẵn có.
- Người chọn 5 đã tính xác nhận ghi danh trùng.
- Người chọn 13 biết hệ thống có nguy cơ tạo bản ghi trùng khi gửi lại request và chưa có test tích hợp.

**Yêu cầu:** Viết kịch bản đối thoại để tìm hiểu bất đồng. Nêu ít nhất ba tiêu chí chấp nhận cần làm rõ, và quyết định nên ước lượng lại ngay hay thực hiện thử nghiệm trước.

**Gợi ý:** Không lấy trung bình (3 + 5 + 13)/3 rồi làm tròn. Hãy xem **mọi người có đang ước lượng cùng một phạm vi** và có bỏ sót rủi ro dữ liệu không.

### Bài tập 6 — Lập dự báo phục vụ một mốc cố định

Một trường chuẩn bị kỳ thi trực tuyến trong sáu tuần. Đội muốn thêm chức năng báo cáo mới nhưng hệ thống còn thiếu kiểm thử tải và xử lý bài nộp gửi lặp.

**Yêu cầu:** Nêu điều gì phải làm rõ ngay, có thể chia phạm vi thế nào, nên dùng dữ liệu gì để dự báo và nên báo cáo bất định với người quản lý ra sao. Phân biệt **ngày sự kiện cố định** với **phạm vi tính năng tùy chọn**.

**Gợi ý:** Không dùng ước lượng story point để hợp thức hóa việc bỏ test an toàn. Nên ưu tiên tính toàn vẹn bài nộp, kiểm thử tải và các mốc phê duyệt cần thiết.

## 16. Checklist trước khi công bố một ước lượng

- [ ] Tôi đã nói rõ **quyết định** mà ước lượng cần hỗ trợ?
- [ ] Phạm vi gồm gì, chưa gồm gì, và kết quả người dùng là gì?
- [ ] Đơn vị đang là **size, story point, ngày công, ngày lịch** hay throughput?
- [ ] Có dữ liệu/hạng mục tham chiếu và quy tắc so sánh nhất quán?
- [ ] Những giả định về **API, dữ liệu, năng lực và phụ thuộc** đã được ghi?
- [ ] Đã tính đến kiểm thử, tích hợp, bảo mật, vận hành, tài liệu và Definition of Done cần thiết?
- [ ] Có bất định nào quá lớn khiến cần **chia nhỏ, spike hoặc trả lời “chưa đủ dữ liệu”**?
- [ ] Khoảng/kịch bản có điều kiện rõ, tránh gắn xác suất không có cơ sở?
- [ ] Có phân biệt dự báo với cam kết và nghĩa vụ bắt buộc?
- [ ] Người có trách nhiệm ưu tiên và quyết định mốc giao đã được tham gia?
- [ ] Có điểm xem lại sau phản hồi hoặc khi một giả định bị thay đổi?
- [ ] Chỉ số có được dùng để cải tiến hệ thống, không so sánh hoặc thưởng phạt cá nhân?

Với việc nhỏ, có thể chỉ cần vài câu trả lời. Với công việc liên quan tiền bạc, quyền truy cập, dữ liệu hoặc mốc bên ngoài, độ rõ ràng về giả định và rủi ro đặc biệt quan trọng.

## 17. Ghi nhớ

- **Khi thông tin chưa đủ, hãy dùng độ lớn tương đối hoặc khoảng có điều kiện**, không đưa ra một con số chính xác giả.
- **Size khác effort, duration, forecast và commitment.** Story point không phải ngày và không phải thước đo năng suất giữa các đội.
- **T-shirt sizing** giúp so sánh cơ hội sớm; **story point** hỗ trợ một số đội ước lượng tương đối theo tham chiếu; **khoảng/kịch bản** làm rõ hậu quả của bất định.
- **Bất đồng là tín hiệu học hỏi.** Khi ước lượng chênh lệch lớn, làm rõ phạm vi, tiêu chí chấp nhận và rủi ro thay vì ép thống nhất một số.
- **Lát cắt nhỏ và spike có giới hạn** giúp giảm bất định; mỗi Increment được giao vẫn phải đáp ứng chất lượng cần thiết.
- **Throughput, cycle time, WIP và phản hồi thực tế** giúp cải thiện dự báo. Dữ liệu quá ít hoặc không tương đồng thì không nên ngụy tạo xác suất.
- **Ước lượng có tuổi thọ:** khi nhu cầu, dữ liệu hay phụ thuộc đổi, hãy cập nhật dự báo và giao tiếp minh bạch với các bên liên quan.

Khi được hỏi “Bao lâu nữa xong?” mà thông tin vẫn thiếu, câu trả lời chuyên nghiệp không nhất thiết là một ngày cụ thể. Hãy trả lời: **“Với phạm vi và những điều kiện hiện biết, độ lớn/khoảng hợp lý là gì, chúng ta chưa chắc điều gì, và bước nào sẽ giúp dự báo tốt hơn?”**
