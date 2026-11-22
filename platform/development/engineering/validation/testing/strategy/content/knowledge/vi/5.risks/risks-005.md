# Xây danh mục rủi ro và xác định người phụ trách theo dõi

Trong chiến lược kiểm thử xác thực (**VALIDATION_TESTING_STRATEGY**), danh mục rủi ro giúp nhóm nhận diện những điều chưa chắc chắn có thể ảnh hưởng đến chất lượng, tiến độ và quyết định phát hành. Danh mục chỉ có giá trị khi mỗi rủi ro được mô tả rõ, được ưu tiên theo mức ảnh hưởng và có người chịu trách nhiệm theo dõi đến khi rủi ro được xử lý hoặc được chấp nhận.

Rủi ro không biến mất chỉ vì nhóm đã ghi nó vào bảng. Nhóm cần nhận biết dấu hiệu thay đổi, thực hiện hành động giảm thiểu, chuẩn bị phương án dự phòng và báo cáo đúng lúc. Bài học này hướng dẫn cách xây dựng danh mục rủi ro thực tế cho hoạt động kiểm thử, phân công người phụ trách và duy trì danh mục trong suốt vòng đời xác minh.

## 1. Hiểu đúng về rủi ro trong kiểm thử

### 1.1. Rủi ro là một sự kiện chưa chắc chắn trong tương lai

Rủi ro là một sự kiện hoặc điều kiện chưa chắc chắn; nếu xảy ra, nó có thể ảnh hưởng đến mục tiêu. Trong kiểm thử phần mềm, ảnh hưởng đó có thể là lỗi nghiêm trọng lọt đến người dùng, bằng chứng kiểm thử không đáng tin cậy, chậm tiến độ, chi phí tăng hoặc quyết định phát hành dựa trên thông tin thiếu hụt.

Một mô tả rủi ro hữu ích thường có ba phần:

**Do nguyên nhân X, sự kiện Y có thể xảy ra, dẫn đến hậu quả Z.**

Ví dụ: “Do môi trường kiểm thử dùng phiên bản cấu hình khác production, luồng xác thực có thể hoạt động đúng trên staging nhưng thất bại sau triển khai, dẫn đến người dùng không đăng nhập được.”

Cách mô tả này chỉ ra nguyên nhân, sự kiện có thể xảy ra và hậu quả. Nhóm có thể từ đó chọn hành động cụ thể như đồng bộ cấu hình, kiểm tra khác biệt và xác minh luồng xác thực trên môi trường gần production.

### 1.2. Phân biệt rủi ro với vấn đề đã xảy ra

Rủi ro nói về điều có thể xảy ra; vấn đề (issue) là điều đã xảy ra và cần xử lý ngay. Hai loại thông tin liên quan nhưng không nên nhập làm một.

| Khái niệm | Ý nghĩa | Ví dụ |
|---|---|---|
| Rủi ro | Sự kiện chưa chắc chắn có thể ảnh hưởng mục tiêu. | Dịch vụ thanh toán bên ngoài có thể gián đoạn trong đợt kiểm thử đầu cuối. |
| Vấn đề (issue) | Sự cố hoặc trở ngại đã hiện hữu. | Sandbox thanh toán đang trả lỗi 503 và các ca đầu cuối không thể chạy. |
| Giả định | Điều đang được tạm xem là đúng để lập kế hoạch, nhưng cần xác nhận. | Nhà cung cấp sẽ cấp tài khoản sandbox trước ngày kiểm thử tích hợp. |
| Phụ thuộc | Thành phần, nhóm hoặc sự kiện bên ngoài cần có để công việc tiến hành. | Nhóm hạ tầng phải cấp chứng thư và mở kết nối mạng cho môi trường staging. |

Một rủi ro có thể chuyển thành vấn đề khi sự kiện xảy ra. Khi đó, hãy cập nhật trạng thái và liên kết bản ghi vấn đề hoặc công việc xử lý để nhóm không tiếp tục theo dõi nó như một khả năng chưa xảy ra.

### 1.3. Phân biệt rủi ro sản phẩm và rủi ro dự án kiểm thử

Nhóm nên xem xét ít nhất hai góc độ:

- **Rủi ro sản phẩm:** khả năng phần mềm có hành vi sai hoặc không đáp ứng yêu cầu, chẳng hạn sai tính tiền, lộ dữ liệu, mất dữ liệu hoặc không chịu được tải.
- **Rủi ro dự án kiểm thử:** khả năng hoạt động kiểm thử không tạo ra bằng chứng đủ tin cậy hoặc không hoàn thành đúng lúc, chẳng hạn môi trường không ổn định, thiếu dữ liệu, thiếu kỹ năng, bộ kiểm thử flaky hoặc phụ thuộc chưa sẵn sàng.

Rủi ro sản phẩm giúp quyết định cần kiểm tra sâu phần nào. Rủi ro dự án kiểm thử giúp bảo đảm nhóm có thể thực hiện việc kiểm tra đó và diễn giải kết quả chính xác.

## 2. Nhận diện rủi ro có hệ thống

Không nên chỉ liệt kê những lo ngại xuất hiện trong cuộc họp gần nhất. Hãy tìm rủi ro từ yêu cầu, kiến trúc, thay đổi, dữ liệu, môi trường, cách kiểm thử và kế hoạch phát hành.

### 2.1. Xem xét yêu cầu và luồng nghiệp vụ

Đọc yêu cầu và tiêu chí chấp nhận để tìm những phần:

- Có hậu quả lớn nếu xử lý sai, như thanh toán, quyền truy cập hoặc dữ liệu cá nhân.
- Mơ hồ, mâu thuẫn hoặc chưa có quy tắc xử lý trường hợp biên.
- Có nhiều trạng thái, vai trò, điều kiện hoặc biến thể đầu vào.
- Khó quan sát hoặc khó khôi phục khi xảy ra lỗi.
- Có thay đổi gần đây nhưng chưa có kiểm thử hồi quy phù hợp.

Ví dụ, yêu cầu “người dùng có thể hủy đơn hàng” chưa nói rõ thời điểm nào được hủy, xử lý hoàn tiền ra sao, điều gì xảy ra khi kho đã gửi hàng hoặc khi yêu cầu hủy được gửi lặp. Những điểm chưa rõ này có thể tạo ra rủi ro về quy tắc nghiệp vụ và dữ liệu.

### 2.2. Xem xét kiến trúc và phụ thuộc

Lần theo luồng dữ liệu và giao tiếp giữa các thành phần. Chú ý đến dịch vụ bên ngoài, message broker, cơ sở dữ liệu, cache, hàng đợi, lịch chạy nền, xác thực, mạng và cấu hình triển khai.

Các câu hỏi hữu ích:

- Nếu một dịch vụ phụ thuộc chậm hoặc ngừng hoạt động thì hệ thống phản ứng thế nào?
- Có thể gửi lại một yêu cầu mà không tạo giao dịch trùng lặp không?
- Dữ liệu có thể bị cập nhật đồng thời hoặc đến sai thứ tự không?
- Có cách kiểm tra tích hợp trên môi trường đại diện không?
- Khi triển khai phiên bản mới, các thành phần cũ và mới có tương thích không?

Phụ thuộc càng khó kiểm soát hoặc càng ít khả năng quan sát thì nhóm càng cần ghi rõ giới hạn và phương án dự phòng.

### 2.3. Xem xét thay đổi và lịch sử lỗi

So sánh thay đổi hiện tại với phiên bản trước: mã nguồn, schema, API, cấu hình, thư viện, quyền truy cập và artifact triển khai. Một thay đổi nhỏ ở thành phần dùng chung có thể ảnh hưởng nhiều luồng.

Lịch sử lỗi cũng là nguồn nhận diện tốt. Lỗi từng tái diễn, lỗi khó tái lập, lỗi chỉ xuất hiện ở production hoặc lỗi có nguyên nhân chưa được loại bỏ nên được xem xét như dấu hiệu rủi ro. Không nên coi việc lỗi đã được sửa là bằng chứng rằng mọi nguyên nhân liên quan đã được xử lý.

### 2.4. Xem xét khả năng thực hiện kiểm thử

Rà soát các yếu tố có thể làm giảm chất lượng bằng chứng:

- Môi trường không ổn định hoặc khác biệt đáng kể so với production.
- Thiếu dữ liệu đại diện, dữ liệu biên hoặc dữ liệu trạng thái lịch sử.
- Bộ kiểm thử tự động chạy không ổn định hoặc phụ thuộc thứ tự.
- Thiếu quyền truy cập, tài khoản, chứng thư hoặc công cụ cần thiết.
- Thiếu người có kỹ năng phù hợp hoặc một cá nhân nắm giữ kiến thức quan trọng.
- Thời gian không đủ cho kiểm thử hồi quy, hiệu năng hoặc bảo mật.
- Không thể quan sát log, metric, trace hoặc kết quả từ hệ thống phụ thuộc.

### 2.5. Kết hợp nhiều phương pháp nhận diện

| Phương pháp | Cách thực hiện | Khi hữu ích |
|---|---|---|
| Workshop nhóm | Mời phát triển, kiểm thử, vận hành, sản phẩm và bảo mật cùng nêu rủi ro. | Khi thay đổi ảnh hưởng nhiều nhóm hoặc nhiều dịch vụ. |
| Phân tích kiến trúc | Vẽ luồng dữ liệu, giao tiếp và phụ thuộc; tìm điểm lỗi đơn lẻ. | Khi hệ thống phân tán hoặc có tích hợp phức tạp. |
| Phân tích thay đổi | Đối chiếu commit, schema, cấu hình và phiên bản với phạm vi trước đó. | Khi đánh giá một bản phát hành cụ thể. |
| Xem lại lỗi cũ | Phân loại lỗi production, lỗi kiểm thử và sự cố phát hành trước đây. | Khi có lịch sử vận hành hoặc kiểm thử đủ dữ liệu. |
| Phân tích giả định | Ghi các giả định về môi trường, dữ liệu, nhân lực và nhà cung cấp; xác định cách xác nhận. | Khi kế hoạch phụ thuộc vào điều chưa được bảo đảm. |
| Kịch bản “điều gì có thể sai?” | Lần theo một luồng và hỏi điều gì xảy ra khi từng bước thất bại. | Khi cần tìm lỗi biên, lỗi phục hồi hoặc lỗi vận hành. |

Một buổi nhận diện tốt nên kết thúc bằng các mô tả có thể hành động, không chỉ là danh sách từ khóa như “hiệu năng”, “tích hợp” hay “nhân lực”.

## 3. Xây dựng danh mục rủi ro

Danh mục rủi ro (risk register) là nơi lưu thông tin nhất quán để nhóm đánh giá, phân công, theo dõi và báo cáo. Có thể quản lý bằng bảng tính, công cụ quản lý công việc hoặc hệ thống quản trị rủi ro sẵn có. Công cụ không quan trọng bằng việc dữ liệu rõ ràng, có người cập nhật và có lịch xem xét.

### 3.1. Các trường thông tin nên có

Một bản ghi rủi ro nên có những trường sau:

| Trường | Nội dung cần ghi |
|---|---|
| ID | Mã duy nhất, ví dụ RISK-012, để tham chiếu trong cuộc họp và báo cáo. |
| Ngày ghi nhận và nguồn | Thời điểm phát hiện và nguồn phát hiện như yêu cầu, workshop, lỗi cũ hoặc phân tích kiến trúc. |
| Mô tả rủi ro | Nguyên nhân, sự kiện có thể xảy ra và hậu quả. |
| Danh mục | Nhóm sản phẩm, tích hợp, dữ liệu, môi trường, bảo mật, tiến độ, nhân lực hoặc vận hành. |
| Phạm vi bị ảnh hưởng | Tính năng, dịch vụ, phiên bản, nhóm người dùng hoặc mốc phát hành liên quan. |
| Khả năng xảy ra | Mức đánh giá khả năng sự kiện xảy ra trong khoảng thời gian xác định. |
| Mức ảnh hưởng | Hậu quả nếu sự kiện xảy ra đối với người dùng, dữ liệu, vận hành, chi phí hoặc tiến độ. |
| Mức ưu tiên | Kết quả đánh giá tổng hợp cùng mức khẩn cấp và thời điểm có thể xảy ra. |
| Người phụ trách rủi ro | Một cá nhân hoặc vai trò chịu trách nhiệm theo dõi và điều phối phản ứng. |
| Hành động và người thực hiện | Việc giảm thiểu, dự phòng, thời hạn và người trực tiếp thực hiện từng việc. |
| Dấu hiệu cảnh báo | Tín hiệu hoặc ngưỡng cho biết rủi ro đang tăng hoặc sự kiện sắp xảy ra. |
| Trạng thái và ngày xem xét | Trạng thái hiện tại, lần cập nhật gần nhất và ngày xem xét tiếp theo. |
| Rủi ro còn lại | Mức rủi ro sau khi áp dụng hành động giảm thiểu; ghi rõ nếu cần chấp nhận. |

Không nhất thiết phải có mọi trường trong một bảng nhỏ, nhưng tối thiểu phải biết rủi ro là gì, vì sao quan trọng, ai chịu trách nhiệm và khi nào cần hành động.

### 3.2. Viết mô tả rủi ro cụ thể

Tránh mô tả chỉ gồm một chủ đề như “thiếu dữ liệu” hoặc “API không ổn định”. Hãy dùng cấu trúc nguyên nhân – sự kiện – hậu quả.

| Mô tả chưa đủ rõ | Mô tả có thể hành động |
|---|---|
| Thiếu dữ liệu kiểm thử. | Do bộ dữ liệu staging chỉ có tài khoản mới, luồng gia hạn với dữ liệu lịch sử có thể không được kiểm tra, dẫn đến lỗi gia hạn lọt đến người dùng hiện tại. |
| Tích hợp thanh toán có rủi ro. | Do sandbox của nhà cung cấp không mô phỏng callback đến trễ, hệ thống có thể cập nhật trạng thái đơn không nhất quán khi callback thực tế đến sau timeout. |
| Test tự động không ổn định. | Do các ca kiểm thử dùng chung dữ liệu và phụ thuộc thứ tự chạy, pipeline có thể thất bại ngẫu nhiên, làm nhóm bỏ qua tín hiệu lỗi thật hoặc trì hoãn phát hành. |

Một mô tả cụ thể giúp người phụ trách biết cần theo dõi tín hiệu gì và nhóm cần giảm thiểu nguyên nhân nào.

### 3.3. Tránh bản ghi trùng lặp hoặc quá rộng

Nếu hai mô tả có cùng nguyên nhân, sự kiện và hậu quả, hãy cân nhắc gộp chúng và liên kết đến nhiều thành phần bị ảnh hưởng. Nếu một bản ghi chứa nhiều sự kiện khác nhau với cách xử lý khác nhau, hãy tách thành các rủi ro riêng.

Ví dụ, “dịch vụ bên ngoài không sẵn sàng” có thể cần tách thành rủi ro về môi trường kiểm thử không cấp được sandbox và rủi ro về dịch vụ production gián đoạn. Hai sự kiện có người phụ trách, dấu hiệu cảnh báo và phương án xử lý khác nhau.

## 4. Đánh giá và ưu tiên rủi ro

Không phải mọi rủi ro đều cần hành động ngay. Nhóm cần đánh giá để tập trung thời gian vào những rủi ro có thể gây hậu quả lớn hoặc có khả năng xảy ra cao.

### 4.1. Đánh giá khả năng xảy ra

Có thể dùng thang định tính năm mức. Nhóm cần thống nhất cách hiểu và khoảng thời gian đánh giá để các thành viên chấm nhất quán.

| Mức | Diễn giải tham khảo |
|---|---|
| 1 – Rất thấp | Khó xảy ra trong phạm vi và thời gian đang xét; chưa có dấu hiệu đáng kể. |
| 2 – Thấp | Có thể xảy ra nhưng ít khả năng; điều kiện kích hoạt hiếm gặp. |
| 3 – Trung bình | Có khả năng xảy ra; đã có yếu tố hoặc tiền lệ liên quan. |
| 4 – Cao | Khả năng xảy ra đáng kể; điều kiện kích hoạt đang hiện diện hoặc thường gặp. |
| 5 – Rất cao | Gần như chắc chắn hoặc đã có dấu hiệu mạnh cho thấy sự kiện sắp xảy ra. |

Khả năng xảy ra cần gắn với một khoảng thời gian, chẳng hạn trong chu kỳ kiểm thử hiện tại hoặc trước ngày phát hành. Không nên chấm điểm mà không nói rõ đang đánh giá giai đoạn nào.

### 4.2. Đánh giá mức ảnh hưởng

Mức ảnh hưởng nên phản ánh hậu quả nếu sự kiện xảy ra. Có thể xem xét nhiều khía cạnh:

- Người dùng: số lượng người bị ảnh hưởng, khả năng tiếp tục sử dụng và mức độ gián đoạn.
- Dữ liệu: mất mát, sai lệch, rò rỉ hoặc không thể khôi phục.
- Bảo mật và tuân thủ: truy cập trái phép, lộ thông tin hoặc vi phạm nghĩa vụ.
- Vận hành: thời gian gián đoạn, khả năng phục hồi và tải hỗ trợ.
- Kinh doanh: giao dịch thất bại, doanh thu, uy tín và nghĩa vụ với khách hàng.
- Dự án: chậm mốc kiểm thử, phát hành hoặc tăng chi phí đáng kể.

| Mức | Diễn giải tham khảo |
|---|---|
| 1 – Không đáng kể | Ảnh hưởng nhỏ, dễ khắc phục, không tác động đáng kể đến người dùng hoặc mục tiêu. |
| 2 – Nhẹ | Ảnh hưởng giới hạn, có cách xử lý đơn giản và ít làm gián đoạn công việc. |
| 3 – Trung bình | Một luồng hoặc nhóm người dùng bị ảnh hưởng; cần công sức đáng kể để khắc phục. |
| 4 – Nghiêm trọng | Chức năng quan trọng bị gián đoạn, dữ liệu hoặc hoạt động kinh doanh chịu ảnh hưởng lớn. |
| 5 – Rất nghiêm trọng | Có nguy cơ mất dữ liệu, lộ thông tin, vi phạm nghiêm trọng hoặc ngừng hoạt động trên diện rộng. |

Khi một rủi ro ảnh hưởng nhiều khía cạnh, hãy dùng hậu quả nghiêm trọng nhất có căn cứ hoặc ghi riêng từng khía cạnh. Không nên lấy trung bình để làm nhẹ đi một tác động bảo mật hay dữ liệu đặc biệt nghiêm trọng.

### 4.3. Dùng ma trận để hỗ trợ ưu tiên

Một cách đơn giản là nhân điểm khả năng xảy ra với điểm ảnh hưởng:

**Điểm rủi ro = Khả năng xảy ra × Mức ảnh hưởng**

Với thang 1–5, điểm nằm trong khoảng 1–25. Có thể dùng ngưỡng minh họa sau, sau đó điều chỉnh theo khẩu vị rủi ro và quy định của dự án:

| Điểm | Mức tham khảo | Hướng xử lý |
|---|---|---|
| 1–4 | Thấp | Theo dõi định kỳ; ghi nhận nếu có thay đổi. |
| 5–9 | Trung bình | Xác định biện pháp phù hợp và người theo dõi. |
| 10–16 | Cao | Có kế hoạch giảm thiểu, thời hạn và dấu hiệu cảnh báo rõ ràng. |
| 17–25 | Rất cao | Báo cáo cấp có thẩm quyền sớm; cần quyết định về giảm thiểu, trì hoãn hoặc chấp nhận rủi ro. |

Đây là cách xếp hạng hỗ trợ thảo luận, không phải xác suất toán học hay tiêu chuẩn chung cho mọi tổ chức. Nhóm cần áp dụng cùng một thang đo và ghi lại lý do khi điều chỉnh mức ưu tiên.

Điểm số cũng không nên là yếu tố duy nhất. Một rủi ro có ảnh hưởng rất nghiêm trọng có thể cần ưu tiên ngay cả khi khả năng xảy ra thấp. Thời điểm xảy ra, tốc độ lan rộng, khả năng phát hiện và thời gian cần để giảm thiểu cũng ảnh hưởng đến mức khẩn cấp.

### 4.4. Đánh giá lại sau khi có hành động

Phân biệt:

- **Rủi ro vốn có:** mức rủi ro trước khi áp dụng biện pháp kiểm soát bổ sung.
- **Rủi ro còn lại:** mức rủi ro vẫn tồn tại sau khi hành động giảm thiểu đã được thực hiện.

Ví dụ, bổ sung kiểm thử hợp đồng và cơ chế thử lại có thể giảm khả năng xảy ra lỗi tích hợp. Tuy nhiên, nhà cung cấp vẫn có thể ngừng hoạt động, nên rủi ro còn lại cần được theo dõi và có phương án dự phòng.

Không được tự động hạ điểm chỉ vì một hành động đã được lên kế hoạch. Chỉ đánh giá lại khi có bằng chứng rằng hành động đã hoàn tất và thực sự làm thay đổi khả năng xảy ra hoặc mức ảnh hưởng.

## 5. Xác định người phụ trách rủi ro

Một danh mục có nhiều bản ghi nhưng không có người chịu trách nhiệm sẽ nhanh chóng lỗi thời. Mỗi rủi ro quan trọng nên có một người phụ trách rõ ràng, có khả năng theo dõi và đưa vấn đề đến đúng người ra quyết định.

### 5.1. Người phụ trách rủi ro chịu trách nhiệm điều gì?

Người phụ trách rủi ro (risk owner) là người chịu trách nhiệm tổng thể đối với việc theo dõi và điều phối cách ứng phó. Họ cần:

- Hiểu nguyên nhân, sự kiện, hậu quả và phạm vi bị ảnh hưởng.
- Theo dõi dấu hiệu cảnh báo và thay đổi về mức rủi ro.
- Bảo đảm có hành động giảm thiểu hoặc phương án dự phòng phù hợp.
- Phối hợp với người thực hiện hành động và các nhóm phụ thuộc.
- Cập nhật trạng thái, điểm đánh giá và rủi ro còn lại.
- Báo cáo hoặc xin quyết định khi vượt thẩm quyền.
- Xác nhận khi rủi ro đã được xử lý, chuyển thành vấn đề hoặc được chấp nhận đúng thẩm quyền.

Người phụ trách không nhất thiết phải tự thực hiện mọi công việc kỹ thuật. Trách nhiệm của họ là bảo đảm rủi ro được quản lý và không bị bỏ quên.

### 5.2. Phân biệt người phụ trách rủi ro với người thực hiện hành động

Một rủi ro có thể cần nhiều hành động do nhiều người thực hiện. Cần phân biệt trách nhiệm tổng thể với trách nhiệm hoàn thành từng công việc.

| Vai trò | Trách nhiệm | Ví dụ |
|---|---|---|
| Người phụ trách rủi ro (risk owner) | Theo dõi toàn bộ rủi ro, điều phối phản ứng và báo cáo. | QA lead chịu trách nhiệm rủi ro thiếu dữ liệu hồi quy. |
| Người thực hiện hành động (action owner) | Hoàn thành một biện pháp cụ thể theo thời hạn. | Kỹ sư dữ liệu tạo tập dữ liệu lịch sử đã ẩn danh. |
| Người ra quyết định/chấp nhận | Có thẩm quyền chấp nhận rủi ro còn lại hoặc thay đổi quyết định phát hành. | Release manager hoặc chủ sở hữu sản phẩm theo quy định dự án. |
| Người được tham vấn | Cung cấp chuyên môn hoặc đánh giá tác động. | Kỹ sư bảo mật đánh giá rủi ro lộ dữ liệu. |

Một người có thể đảm nhiệm nhiều vai trò nếu phù hợp, nhưng tên người chịu trách nhiệm tổng thể phải được xác định rõ. Tránh ghi chung “QA team”, “Dev team” hoặc “mọi người” làm chủ sở hữu vì không ai có trách nhiệm cuối cùng để nhắc việc và báo cáo.

### 5.3. Tiêu chí chọn người phụ trách

Chọn người dựa trên khả năng kiểm soát và hiểu biết về rủi ro, không chỉ dựa trên chức danh. Người phù hợp nên:

- Có kiến thức về thành phần hoặc quy trình bị ảnh hưởng.
- Có quyền tiếp cận thông tin và các nhóm liên quan.
- Có khả năng yêu cầu hoặc điều phối hành động giảm thiểu.
- Có thời gian theo dõi trong suốt giai đoạn rủi ro tồn tại.
- Biết ngưỡng nào cần báo cáo hoặc xin quyết định.
- Có người thay thế hoặc cơ chế bàn giao khi vắng mặt.

Nếu rủi ro nằm ngoài quyền kiểm soát của người phụ trách, họ vẫn có thể theo dõi nhưng cần ghi rõ bên có thẩm quyền quyết định và cơ chế leo thang.

### 5.4. Gán trách nhiệm theo loại rủi ro

Bảng sau là gợi ý để chọn vai trò phù hợp; dự án cần chỉ định người cụ thể theo cơ cấu thực tế.

| Loại rủi ro | Vai trò thường phù hợp làm người phụ trách | Nhóm có thể thực hiện hành động |
|---|---|---|
| Độ bao phủ và chất lượng kiểm thử | QA lead hoặc test manager | QA engineer, developer |
| Lỗi logic hoặc thay đổi kiến trúc | Tech lead hoặc engineering lead | Developer, architect |
| Môi trường và triển khai | DevOps/SRE lead | Kỹ sư hạ tầng, vận hành |
| Dữ liệu và migration | Data lead hoặc database owner | Kỹ sư dữ liệu, DBA, developer |
| Bảo mật và quyền riêng tư | Security owner hoặc người được phân quyền | Security engineer, developer, privacy specialist |
| Tích hợp bên thứ ba | Owner của dịch vụ tích hợp | Developer tích hợp, nhà cung cấp |
| Tiến độ và phụ thuộc liên nhóm | Project manager hoặc delivery lead | Các trưởng nhóm liên quan |
| Quyết định phát hành và chấp nhận rủi ro | Release manager hoặc product owner theo thẩm quyền | QA lead, engineering lead cung cấp bằng chứng |

Không chuyển trách nhiệm của rủi ro sản phẩm sang riêng nhóm kiểm thử. Nhóm kiểm thử có thể phát hiện và báo cáo rủi ro, nhưng chủ sở hữu thành phần hoặc người có thẩm quyền nghiệp vụ thường phải tham gia quyết định xử lý.

## 6. Lập kế hoạch ứng phó và dấu hiệu cảnh báo

Sau khi ưu tiên và phân công, hãy xác định cách ứng phó. Một hành động tốt cần chỉ rõ việc phải làm, kết quả mong đợi, người thực hiện, thời hạn và bằng chứng hoàn tất.

### 6.1. Các chiến lược ứng phó phổ biến

| Chiến lược | Ý nghĩa | Ví dụ trong kiểm thử |
|---|---|---|
| Tránh (avoid) | Thay đổi kế hoạch hoặc thiết kế để loại bỏ nguyên nhân hoặc không tiếp xúc với rủi ro. | Hoãn bật tính năng mới cho đến khi hoàn tất kiểm thử bảo mật bắt buộc. |
| Giảm thiểu (mitigate) | Giảm khả năng xảy ra hoặc mức ảnh hưởng. | Bổ sung contract test, kiểm thử retry và cảnh báo cho tích hợp thanh toán. |
| Chuyển giao/chia sẻ (transfer/share) | Chuyển một phần trách nhiệm hoặc tác động theo thỏa thuận phù hợp. | Dùng dịch vụ kiểm thử chuyên biệt theo hợp đồng có quy định trách nhiệm rõ ràng. |
| Chấp nhận (accept) | Có chủ đích giữ lại rủi ro khi người có thẩm quyền hiểu và đồng ý với hậu quả. | Chấp nhận chưa kiểm thử một trình duyệt đã hết hỗ trợ vì nằm ngoài cam kết sản phẩm. |

Chuyển giao không làm rủi ro biến mất. Ví dụ, thuê nhà cung cấp thực hiện kiểm thử tải có thể chuyển phần công việc, nhưng nhóm vẫn cần xem xét chất lượng kết quả và trách nhiệm với quyết định phát hành.

### 6.2. Tách hành động giảm thiểu và phương án dự phòng

Hành động giảm thiểu nhằm giảm khả năng hoặc tác động trước khi sự kiện xảy ra. Phương án dự phòng (contingency plan) mô tả điều cần làm nếu sự kiện vẫn xảy ra.

Ví dụ với rủi ro nhà cung cấp thanh toán không sẵn sàng:

- **Giảm thiểu:** xác nhận lịch bảo trì, kiểm tra sandbox sớm, thêm contract test và thống nhất đầu mối hỗ trợ.
- **Dấu hiệu cảnh báo:** tỷ lệ timeout tăng, sandbox trả lỗi liên tục hoặc nhà cung cấp thông báo gián đoạn.
- **Phương án dự phòng:** chuyển sang bộ kiểm thử mô phỏng đã được xác nhận cho phần kiểm tra nội bộ, đánh dấu phần tích hợp thật chưa có bằng chứng và xin quyết định về mốc phát hành.
- **Điều kiện leo thang:** không có bằng chứng tích hợp thật trước thời điểm chốt phát hành hoặc luồng thanh toán trọng yếu chưa được xác minh.

Phương án dự phòng cần có người kích hoạt, điều kiện kích hoạt và hành động cụ thể. Nếu không, nó chỉ là một ý định chung chung.

### 6.3. Xác định dấu hiệu cảnh báo có thể quan sát

Dấu hiệu cảnh báo (risk trigger) là tín hiệu cho biết rủi ro đang tăng hoặc sự kiện có thể sắp xảy ra. Hãy chọn tín hiệu có thể đo hoặc quan sát, chẳng hạn:

- Tỷ lệ lỗi hoặc timeout vượt ngưỡng trong một khoảng thời gian.
- Số lượng ca kiểm thử flaky tăng qua các lần chạy.
- Môi trường không sẵn sàng trước mốc kiểm thử đã cam kết.
- Tập dữ liệu chưa được xác nhận trước ngày bắt đầu kiểm thử.
- Một lỗi nghiêm trọng mới xuất hiện ở luồng nghiệp vụ quan trọng.
- Thay đổi cấu hình hoặc artifact không khớp với phiên bản đã kiểm thử.
- Người phụ trách hoặc nhà cung cấp không phản hồi trước thời hạn đã thống nhất.

Tránh trigger mơ hồ như “nếu tình hình xấu đi”. Ghi ngưỡng, nguồn tín hiệu, người quan sát và hành động cần thực hiện khi ngưỡng bị vượt.

## 7. Ví dụ danh mục rủi ro cho một đợt kiểm thử

Giả sử nhóm chuẩn bị phát hành chức năng thanh toán mới. Danh mục ban đầu có thể gồm:

| ID | Mô tả ngắn | Khả năng | Ảnh hưởng | Điểm | Người phụ trách |
|---|---|---:|---:|---:|---|
| RISK-001 | Sandbox không mô phỏng đầy đủ callback đến trễ, có thể làm bỏ sót lỗi cập nhật trạng thái thanh toán. | 3 | 4 | 12 | Payment service owner |
| RISK-002 | Dữ liệu staging thiếu đơn hàng lịch sử, có thể làm kiểm thử migration không phát hiện lỗi tương thích. | 3 | 4 | 12 | Data lead |
| RISK-003 | Bộ kiểm thử đầu cuối dùng chung tài khoản và dữ liệu, có thể thất bại ngẫu nhiên khi chạy song song. | 4 | 3 | 12 | QA lead |
| RISK-004 | Cấu hình retry ở staging khác production, có thể tạo hành vi timeout khác sau triển khai. | 2 | 5 | 10 | DevOps lead |
| RISK-005 | Kiểm thử tải chưa bao phủ thời điểm nhiều callback đồng thời, có thể gây nghẽn khi lưu lượng tăng. | 3 | 5 | 15 | Engineering lead |

Điểm số chỉ là đánh giá ban đầu. Người phụ trách cần xác minh giả định, bổ sung dấu hiệu cảnh báo và điều chỉnh mức rủi ro khi có bằng chứng mới.

### 7.1. Ví dụ chi tiết một bản ghi

**ID:** RISK-001

**Mô tả:** Do sandbox của nhà cung cấp không mô phỏng đầy đủ callback đến trễ và gửi lặp, hệ thống có thể cập nhật trạng thái thanh toán không nhất quán trong production, dẫn đến đơn hàng đã thanh toán nhưng vẫn hiển thị chưa thanh toán hoặc phát sinh xử lý trùng.

**Phạm vi:** Payment callback handler, payment-api, luồng xác nhận đơn hàng của release candidate.

**Đánh giá ban đầu:** Khả năng 3/5, ảnh hưởng 4/5, điểm 12/25 — mức cao theo ngưỡng tham khảo của dự án.

**Người phụ trách rủi ro:** Payment service owner.

**Hành động giảm thiểu:**
1. Bổ sung kiểm thử contract cho định dạng callback và chữ ký.
2. Tạo kịch bản kiểm thử gửi callback trễ, lặp và sai thứ tự.
3. Xác minh cơ chế idempotency và đối soát trạng thái đơn hàng.
4. Thu thập log và trace để phát hiện cập nhật trạng thái bất thường.

**Người thực hiện:** Developer phụ trách callback handler và QA engineer phụ trách kịch bản tích hợp.

**Dấu hiệu cảnh báo:** Tỷ lệ callback trùng hoặc timeout tăng; số đơn có trạng thái payment và order không khớp vượt ngưỡng giám sát đã thống nhất.

**Phương án dự phòng:** Dừng bật tính năng cho toàn bộ người dùng, chuyển về luồng đã ổn định nếu cơ chế rollback cho phép và điều tra các giao dịch có trạng thái không nhất quán.

**Điều kiện báo cáo:** Không hoàn thành xác minh idempotency hoặc chưa có phương án đối soát trước thời điểm phê duyệt phát hành.

**Rủi ro còn lại:** Nhà cung cấp vẫn có thể gặp sự cố ngoài khả năng kiểm soát; cần theo dõi production và có quy trình xử lý giao dịch bất thường.

Ví dụ này cho thấy một bản ghi có thể được theo dõi xuyên suốt: từ nhận diện, đánh giá, phân công, hành động, trigger đến quyết định về rủi ro còn lại.

## 8. Theo dõi, cập nhật và báo cáo danh mục

Danh mục rủi ro cần được cập nhật khi có thông tin mới, không chỉ vào ngày lập kế hoạch. Người phụ trách phải biết khi nào xem xét lại và điều gì cần được báo cáo.

### 8.1. Thiết lập nhịp xem xét

Có thể xem xét rủi ro theo các mốc:

- Khi lập kế hoạch kiểm thử và xác định phạm vi.
- Trước khi bắt đầu một giai đoạn kiểm thử quan trọng.
- Trong các buổi họp theo dõi tiến độ hoặc họp rủi ro định kỳ.
- Khi có thay đổi lớn về yêu cầu, mã, cấu hình, môi trường hoặc phụ thuộc.
- Khi xuất hiện lỗi nghiêm trọng, sự cố hoặc trigger vượt ngưỡng.
- Trước khi ra quyết định phát hành và khi bàn giao sang vận hành.

Tần suất nên dựa trên mức độ rủi ro và tốc độ thay đổi. Rủi ro rất cao có thể cần theo dõi hằng ngày hoặc theo sự kiện; rủi ro thấp có thể xem xét theo chu kỳ ngắn gọn hơn.

### 8.2. Cập nhật trạng thái nhất quán

Có thể dùng các trạng thái sau:

| Trạng thái | Ý nghĩa |
|---|---|
| Mới ghi nhận | Rủi ro vừa được phát hiện, chưa đánh giá đầy đủ. |
| Đang đánh giá | Đang xác minh nguyên nhân, khả năng, ảnh hưởng hoặc người phụ trách. |
| Đang giảm thiểu | Các hành động giảm thiểu đã được giao và đang thực hiện. |
| Đang theo dõi | Biện pháp đã triển khai hoặc rủi ro được chấp nhận có điều kiện; cần theo dõi trigger. |
| Đã xảy ra / Chuyển thành issue | Sự kiện đã xảy ra và cần quản lý như một vấn đề. |
| Đã đóng | Rủi ro không còn áp dụng hoặc đã được xử lý với bằng chứng phù hợp. |
| Đã chấp nhận | Người có thẩm quyền đã chấp nhận rủi ro còn lại và điều kiện theo dõi nếu có đã được ghi nhận. |

Không đóng rủi ro chỉ vì một ticket hành động đã hoàn tất. Cần xác minh biện pháp có hiệu quả, đánh giá rủi ro còn lại và ghi lý do đóng hoặc chấp nhận.

### 8.3. Báo cáo theo điều người ra quyết định cần biết

Báo cáo không nên chỉ đếm số lượng rủi ro. Hãy nêu:

- Rủi ro rất cao hoặc cao đang tồn tại và xu hướng tăng/giảm.
- Rủi ro có trigger đã xuất hiện hoặc sắp vượt ngưỡng.
- Hành động quá hạn và người cần hỗ trợ.
- Rủi ro còn lại có thể ảnh hưởng đến quyết định phát hành.
- Các quyết định cần cấp quản lý hoặc chủ sở hữu sản phẩm đưa ra.
- Thay đổi trong phạm vi, giả định hoặc mức đánh giá kể từ lần báo cáo trước.

Nếu cần chấp nhận rủi ro, bản ghi phải nêu rõ người có thẩm quyền, lý do, phạm vi chấp nhận, thời hạn hiệu lực và điều kiện xem xét lại. Người phụ trách rủi ro có thể đề xuất nhưng không tự chấp nhận vượt thẩm quyền được giao.

### 8.4. Bàn giao trách nhiệm khi thay đổi nhân sự

Khi người phụ trách chuyển nhóm, nghỉ phép dài ngày hoặc không còn quyền kiểm soát, cần chỉ định người thay thế. Bàn giao gồm mô tả rủi ro, trạng thái, trigger, hành động đang mở, thời hạn, các quyết định đã đưa ra và đầu mối liên quan.

Không để một rủi ro quan trọng ở trạng thái không có người phụ trách. Nếu chưa thể chỉ định người thay thế, hãy báo cáo như một khoảng trống quản trị cần được xử lý.

## 9. Mẫu danh mục và mẫu rà soát rủi ro

Có thể dùng mẫu sau để tạo danh mục cho dự án. Các trường có thể được điều chỉnh theo quy trình nội bộ, nhưng cần giữ được mối liên hệ giữa mô tả, ưu tiên, người phụ trách, hành động và việc theo dõi.

~~~text
ID:
Ngày ghi nhận:
Nguồn phát hiện:
Danh mục rủi ro:

Mô tả (nguyên nhân - sự kiện - hậu quả):
Phạm vi / phiên bản bị ảnh hưởng:
Khả năng xảy ra (1-5):
Mức ảnh hưởng (1-5):
Điểm và mức ưu tiên:
Lý do đánh giá:

Người phụ trách rủi ro:
Người thực hiện hành động:
Hành động giảm thiểu:
Thời hạn:
Bằng chứng hoàn tất:

Dấu hiệu cảnh báo / ngưỡng kích hoạt:
Nguồn theo dõi:
Phương án dự phòng:
Điều kiện báo cáo / leo thang:

Rủi ro vốn có:
Rủi ro còn lại:
Trạng thái:
Người chấp nhận (nếu có):
Ngày xem xét gần nhất:
Ngày xem xét tiếp theo:
~~~

Trong mỗi buổi rà soát, người phụ trách có thể trả lời ngắn gọn:

1. Điều gì đã thay đổi kể từ lần cập nhật trước?
2. Khả năng xảy ra hoặc mức ảnh hưởng có tăng không? Bằng chứng là gì?
3. Trigger nào đã xuất hiện hoặc đang tiến gần ngưỡng?
4. Hành động nào đã hoàn tất, hành động nào quá hạn?
5. Rủi ro còn lại có cần quyết định hoặc hỗ trợ không?
6. Ai chịu trách nhiệm cho bước tiếp theo và thời hạn là khi nào?

## 10. Những sai lầm thường gặp

- **Ghi rủi ro quá chung chung:** “hiệu năng kém” không chỉ ra nguyên nhân hay hậu quả. Hãy mô tả sự kiện cụ thể trong một luồng và điều kiện có thể kích hoạt.
- **Không phân biệt rủi ro với issue:** sự cố đã xảy ra cần được xử lý như vấn đề; rủi ro còn lại cần tiếp tục theo dõi.
- **Chấm điểm theo cảm giác:** thống nhất thang đo, thời gian đánh giá và lý do để tránh điểm số tùy ý.
- **Chỉ ghi điểm mà không có hành động:** rủi ro cao cần người phụ trách, biện pháp, thời hạn và trigger.
- **Gán chủ sở hữu cho cả một nhóm:** chỉ định một người chịu trách nhiệm tổng thể, sau đó phân công người thực hiện từng hành động.
- **Đồng nhất người phụ trách với người làm:** người thực hiện một ticket chưa chắc chịu trách nhiệm theo dõi toàn bộ rủi ro.
- **Hạ điểm khi hành động chưa hoàn tất:** chỉ đánh giá lại khi có bằng chứng về hiệu quả của biện pháp.
- **Chấp nhận rủi ro không đúng thẩm quyền:** ghi rõ người quyết định, phạm vi và thời hạn chấp nhận.
- **Không cập nhật trigger:** dấu hiệu cảnh báo phải gắn với nguồn dữ liệu và người quan sát.
- **Không bàn giao:** rủi ro mất chủ sở hữu dễ bị bỏ quên khi thay đổi nhân sự hoặc giai đoạn dự án.

## 11. Danh sách rà soát trước khi chốt danh mục

- [ ] Rủi ro được nhận diện từ yêu cầu, kiến trúc, thay đổi, dữ liệu, môi trường và kế hoạch kiểm thử.
- [ ] Mỗi mô tả có nguyên nhân, sự kiện và hậu quả cụ thể.
- [ ] Rủi ro được phân biệt với vấn đề đã xảy ra, giả định và phụ thuộc.
- [ ] Phạm vi và phiên bản bị ảnh hưởng được ghi rõ.
- [ ] Thang khả năng, ảnh hưởng và ngưỡng ưu tiên được thống nhất.
- [ ] Rủi ro nghiêm trọng được ưu tiên dựa trên hậu quả và thời điểm, không chỉ dựa vào điểm số.
- [ ] Mỗi rủi ro quan trọng có một người phụ trách cụ thể.
- [ ] Người thực hiện, hành động và thời hạn được xác định.
- [ ] Dấu hiệu cảnh báo, nguồn theo dõi và điều kiện leo thang có thể quan sát.
- [ ] Phương án dự phòng được ghi cho rủi ro cần thiết.
- [ ] Rủi ro còn lại và quyết định chấp nhận có căn cứ, đúng thẩm quyền.
- [ ] Có lịch xem xét, cập nhật trạng thái và cơ chế bàn giao.

## Kết luận

Danh mục rủi ro là công cụ giúp nhóm biến sự không chắc chắn thành thông tin có thể theo dõi và hành động. Mỗi rủi ro cần được mô tả bằng nguyên nhân, sự kiện và hậu quả; được ưu tiên theo khả năng xảy ra và mức ảnh hưởng; có người phụ trách chịu trách nhiệm điều phối; và có hành động, dấu hiệu cảnh báo, phương án dự phòng cùng lịch xem xét rõ ràng. Khi danh mục được duy trì bằng bằng chứng và quyết định minh bạch, nhóm có thể tập trung kiểm thử vào những rủi ro quan trọng và đưa ra quyết định phát hành có cơ sở hơn.
