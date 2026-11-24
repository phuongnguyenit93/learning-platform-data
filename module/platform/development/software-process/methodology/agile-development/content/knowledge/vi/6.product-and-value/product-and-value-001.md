# Phân biệt đầu ra bàn giao với kết quả mang lại cho người dùng

Một nhóm phát triển phần mềm hoàn tất 12 user story, phát hành giao diện mới đúng hạn và đóng toàn bộ ticket trong Sprint. Báo cáo dự án màu xanh. Tuy nhiên, người dùng vẫn phải gọi bộ phận hỗ trợ để thực hiện tác vụ mà giao diện mới được thiết kế nhằm giải quyết. **Nhóm đã tạo ra đầu ra, nhưng chưa chứng minh được kết quả mong muốn.**

Đây là một khác biệt nền tảng của tư duy sản phẩm trong Agile: **bàn giao thứ đã xây dựng** không đồng nghĩa với **tạo ra thay đổi có ích trong thực tế sử dụng**. Đầu ra là điều nhóm trực tiếp tạo hoặc phát hành; kết quả là thay đổi quan sát được ở hành vi, năng lực hoặc tình trạng của người dùng sau khi giải pháp được đưa vào bối cảnh thực tế.

Trong module **AGILE_DEVELOPMENT**, việc phân biệt này giúp đội xây dựng user story có mục đích, ưu tiên Product Backlog hợp lý, dùng Sprint Review để học từ phần mềm hoạt động được, sử dụng Kanban để rút ngắn thời gian đưa giá trị đến người dùng và dùng các thực hành XP để thay đổi sản phẩm an toàn. Agile khuyến khích giao sản phẩm tăng dần, phản hồi sớm và cải tiến liên tục; muốn biết đang cải tiến *đúng điều gì*, đội phải nhìn vượt ra ngoài số tính năng đã bàn giao.

## Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt **hoạt động (activity)**, **đầu ra (output)**, **kết quả người dùng (outcome)** và **tác động rộng hơn (impact)** bằng ví dụ phần mềm.
2. Giải thích vì sao giao đúng hạn, đạt Definition of Done (DoD) và có nhiều lượt sử dụng vẫn chưa đủ chứng minh sản phẩm giải quyết vấn đề.
3. Chuyển một yêu cầu theo tính năng thành phát biểu vấn đề, giả thuyết kết quả và tiêu chí kiểm chứng có thể quan sát.
4. Lựa chọn chỉ số kết quả và chỉ số kiểm soát rủi ro; xác định cách đo, mẫu quan sát, mốc thời gian và các giới hạn diễn giải.
5. Kết nối kết quả người dùng với user story, Product Backlog, Sprint Goal, Scrum, Kanban và XP mà không biến một chỉ số thành mục tiêu đối phó.
6. Sử dụng phản hồi để quyết định tiếp tục, điều chỉnh, mở rộng hoặc dừng một giải pháp, kể cả khi giải pháp đã được bàn giao đầy đủ.

## 1. Bốn lớp: hoạt động, đầu ra, kết quả và tác động

Khi đọc báo cáo tiến độ, hãy hỏi: “Thông tin này mô tả **chúng ta đã làm gì**, **đã tạo ra gì**, **điều gì thay đổi cho người dùng**, hay **giá trị rộng hơn đã xuất hiện**?”

| Lớp | Ý nghĩa | Ví dụ ở nền tảng học trực tuyến | Bằng chứng thường dùng |
|---|---|---|---|
| **Hoạt động (activity)** | Những việc nhóm tiến hành | Phỏng vấn học viên, viết mã, kiểm thử, họp Sprint Review | Lịch thực hiện, công việc trong tiến độ |
| **Đầu ra (output)** | Sản phẩm, chức năng hoặc hiện vật được tạo ra | Phát hành luồng đăng ký mới, video hướng dẫn, chức năng gợi ý khóa học | Increment đã đạt DoD, bản phát hành, tính năng có thể sử dụng |
| **Kết quả (outcome)** | Sự thay đổi có ý nghĩa trong hành vi hoặc khả năng của đối tượng mục tiêu | Nhiều học viên đăng ký thành công mà không cần trợ giúp; họ bắt đầu học sớm hơn | Tỷ lệ hoàn tất tác vụ, thời gian thực hiện, phản hồi định tính |
| **Tác động (impact)** | Hiệu quả dài hơn hoặc rộng hơn đối với người dùng, tổ chức, cộng đồng | Học viên duy trì học tập, nâng cao kỹ năng; tổ chức giảm chi phí hỗ trợ hợp lý | Xu hướng duy trì, kết quả học tập, chi phí phục vụ, đánh giá chất lượng |

**Đầu ra** thường nằm trong vùng kiểm soát trực tiếp của đội: xây tính năng, tạo tài liệu, triển khai một thay đổi. **Kết quả** phụ thuộc thêm vào người dùng, ngữ cảnh, khả năng tiếp cận, giá trị thực và các yếu tố ngoài sản phẩm. **Tác động** có thể xuất hiện muộn, khó quy kết cho một thay đổi riêng lẻ và chịu ảnh hưởng của thị trường hoặc hệ sinh thái.

Ranh giới giữa *outcome* và *impact* thay đổi theo mô hình quản trị sản phẩm. Trong bài này, **outcome** nhấn mạnh thay đổi quan sát được đối với người dùng trong thời gian ra quyết định của nhóm; **impact** nhấn mạnh hiệu ứng dài hạn hoặc rộng hơn. Đừng mất thời gian tranh luận nhãn gọi nếu đội đã thống nhất rõ **ai thay đổi điều gì và bằng chứng nào cho thấy thay đổi có ích**.

### 1.1. Một chuỗi từ ý tưởng đến giá trị

~~~mermaid
flowchart LR
    A["Vấn đề hoặc nhu cầu người dùng"] --> B["Giả thuyết giải pháp"]
    B --> C["Hoạt động xây dựng"]
    C --> D["Đầu ra: phần mềm hoạt động được"]
    D --> E["Người dùng tiếp cận và sử dụng"]
    E --> F["Kết quả: hành vi hoặc năng lực thay đổi"]
    F --> G["Tác động: giá trị dài hạn"]
    E -. "Phản hồi" .-> B
    F -. "Kiểm chứng giả thuyết" .-> B
    G -. "Xem lại mục tiêu" .-> A
~~~

Mũi tên thể hiện **giả định cần kiểm chứng**, không phải bảo đảm nhân quả. Một chức năng có thể chạy hoàn hảo nhưng người dùng không biết đến; người dùng có thể thử một lần nhưng vẫn không giải quyết được vấn đề; kết quả ngắn hạn có thể tăng trong khi hệ quả dài hạn xấu đi.

Ví dụ đầy đủ:

1. **Vấn đề:** Học viên mới lạc hướng trong màn hình chọn lớp.
2. **Hoạt động:** Nhóm nghiên cứu hành trình, thử thiết kế và triển khai hướng dẫn.
3. **Đầu ra:** Tính năng gợi ý bước tiếp theo được phát hành.
4. **Kết quả mong muốn:** Học viên tự chọn lớp phù hợp nhanh hơn, ít bỏ dở.
5. **Tác động kỳ vọng:** Học viên bắt đầu khóa học đúng mục tiêu và duy trì học tập tốt hơn.

Nếu chỉ biết bước 3 đã hoàn tất, đội **chưa biết** bước 4 và 5 có xảy ra không.

### 1.2. “Outcome” không đồng nghĩa “feature được sử dụng”

Một tính năng có nhiều lượt mở là dấu hiệu người dùng *tiếp xúc* với đầu ra. Nó có thể đóng góp vào kết quả nhưng không đủ tự thân chứng minh lợi ích.

- **Số lần mở trang trợ giúp tăng:** Có thể vì tài liệu hữu ích hơn; cũng có thể vì sản phẩm khó dùng hơn.
- **Thời gian ở trong ứng dụng tăng:** Có thể vì học viên tham gia bài học sâu hơn; cũng có thể vì họ không tìm được nút hoàn tất.
- **Số lượt nhấp vào nút “Gửi” tăng:** Có thể vì nhiều người hoàn tất hơn; cũng có thể vì nút lỗi buộc họ nhấp lại.
- **Số người đăng nhập tăng:** Có thể cho thấy tăng sử dụng, nhưng chưa chứng minh người dùng đã hoàn thành nhiệm vụ quan trọng.

Muốn đo kết quả, phải nối hành vi với **việc người dùng thực sự muốn đạt**. Với trải nghiệm học tập, “hoàn tất bài thực hành có ý nghĩa” có thể phù hợp hơn chỉ số “mở bài học”, dù cả hai đều cung cấp thông tin.

## 2. Vì sao các đội dễ nhầm đầu ra với kết quả?

### 2.1. Đầu ra dễ lên kế hoạch và xác nhận

Đội có thể cam kết “giao ba màn hình trước ngày 30” rồi kiểm tra xem các màn hình có tồn tại và đạt tiêu chuẩn hay không. Kết quả như “giảm khó khăn khi đăng ký” phụ thuộc vào người dùng, mức độ nhận biết tính năng và thời gian đủ để quan sát. Vì đầu ra dễ đếm, các báo cáo dự án thường ưu tiên số lượng tính năng, ticket, story point hoặc phần trăm phạm vi đã hoàn thành.

Điều này không khiến quản lý đầu ra trở nên vô ích. Tiến độ giao hàng, dự báo phạm vi và chất lượng là thông tin cần thiết. Vấn đề xuất hiện khi chúng bị dùng như **bằng chứng thay thế** cho việc sản phẩm có ích.

### 2.2. Kế hoạch có thể được viết dưới dạng danh sách giải pháp

Khách hàng nói: “Hãy thêm chatbot”. Một nhóm chỉ quản lý đầu ra sẽ tạo ticket “xây chatbot”, rồi đánh giá thành công qua việc chatbot được phát hành. Một nhóm hướng kết quả sẽ hỏi thêm: “Người dùng đang gặp khó khăn nào? Họ cần giải quyết nhanh vấn đề gì? Chatbot có phải cách tốt nhất không?”

Nếu mục tiêu là giúp khách tự xử lý lỗi thanh toán, các lựa chọn có thể bao gồm sửa nội dung thông báo lỗi, cải thiện trung tâm trợ giúp, thiết kế lại luồng thao tác hoặc xây chatbot. Giải pháp tốt nhất không nhất thiết là giải pháp được nhắc đến đầu tiên.

### 2.3. Phản hồi đến quá muộn

Nếu tất cả tính năng chỉ được tích hợp và ra mắt ở cuối quý, giả định về nhu cầu người dùng khó được kiểm tra sớm. Nhóm có thể hoàn tất danh sách bàn giao nhưng bỏ lỡ cơ hội phát hiện một giả định sai ở tuần thứ hai. Giao **Increment nhỏ, có thể sử dụng** giúp tạo bằng chứng sớm để thay đổi thứ tự ưu tiên.

### 2.4. Cách thưởng phạt có thể khiến đội tối ưu sai

Nếu thành công được gắn cứng với “bao nhiêu story point”, “bao nhiêu tính năng” hoặc “bao nhiêu lượt nhấp”, đội có động lực tăng các con số đó ngay cả khi chúng không giúp người dùng. Đây là một biểu hiện của rủi ro khi biến **chỉ số đại diện** thành mục tiêu tự thân.

Ví dụ, thưởng theo số ticket Done có thể dẫn đến chia ticket nhỏ hơn nhưng không giao được luồng hoàn chỉnh. Thưởng theo thời gian dùng ứng dụng có thể khuyến khích thêm bước không cần thiết, trong khi người dùng lại muốn hoàn thành tác vụ nhanh chóng.

## 3. Bắt đầu từ vấn đề người dùng, không bắt đầu từ danh sách tính năng

Để chuyển trọng tâm sang kết quả, nhóm cần mô tả vấn đề trước khi khẳng định một giải pháp cụ thể là đáp án.

### 3.1. Mô tả vấn đề bằng ngữ cảnh có thể quan sát

Một phát biểu vấn đề hữu ích trả lời bốn câu hỏi:

- **Ai** là đối tượng cần hỗ trợ?
- **Họ muốn hoàn thành công việc gì** trong tình huống nào?
- **Trở ngại hiện tại** là gì và có bằng chứng ban đầu nào?
- **Nếu được giải quyết**, điều có ý nghĩa sẽ thay đổi như thế nào?

Ví dụ:

> Học viên mới đăng ký một khóa học trên điện thoại thường không biết phải bắt đầu từ đâu sau khi thanh toán. Trong các phiên quan sát gần đây, nhiều người quay lại trang danh sách khóa mà chưa mở bài đầu tiên. Chúng ta muốn họ tìm và bắt đầu bài phù hợp mà không cần liên hệ hỗ trợ.

Phát biểu này để ngỏ nhiều giải pháp và chỉ rõ hành vi có thể kiểm chứng. Nó mạnh hơn yêu cầu “thêm màn hình chào mừng”, vì màn hình đó có thể không giải quyết nguyên nhân.

### 3.2. Viết giả thuyết nối giải pháp với kết quả

Một mẫu ngắn:

~~~text
ĐỐI TƯỢNG: [Nhóm người dùng và bối cảnh]
VẤN ĐỀ: [Việc họ chưa thể làm tốt, bằng chứng hiện có]
GIẢ THUYẾT: Nếu chúng ta [thay đổi nhỏ có thể kiểm chứng],
           thì [hành vi/năng lực người dùng] sẽ cải thiện,
           vì [cơ chế tác động dự kiến].
KẾT QUẢ CẦN ĐO: [Chỉ số, định nghĩa, thời điểm đánh giá]
ĐIỀU CẦN BẢO VỆ: [Chất lượng, bảo mật, sự công bằng, hiệu năng...]
NẾU KHÔNG ĐẠT: [Học thêm, đổi giải pháp hoặc xem lại giả thuyết]
~~~

Ví dụ:

> Nếu đưa nút “Bắt đầu bài đầu tiên” vào trang xác nhận đăng ký cho học viên mới, chúng ta kỳ vọng tăng tỷ lệ học viên tự hoàn thành bài học đầu tiên trong bảy ngày, vì họ không phải tự dò tìm trong danh mục khóa. Chúng ta vẫn cần bảo đảm học viên chọn đúng khóa, không tăng lỗi truy cập và không gây hiểu nhầm rằng bài học đã hoàn thành.

Giả thuyết này có thể sai. Đó không phải điều xấu: **một giả thuyết sai được kiểm tra sớm** có thể giúp đội tránh dành nhiều Sprint xây một giải pháp kém hiệu quả.

### 3.3. Đặt mục tiêu kết quả rõ nhưng không hứa hẹn tuyệt đối

Một mục tiêu thực dụng thường chứa:

| Thành phần | Câu hỏi |
|---|---|
| Đối tượng | Áp dụng cho nhóm người dùng nào? |
| Hành vi hoặc năng lực | Người dùng cần làm được điều gì? |
| Mức ban đầu (baseline) | Hiện trạng đo được là bao nhiêu và trong giai đoạn nào? |
| Mức thay đổi mong muốn | Mong muốn tăng, giảm hoặc duy trì giá trị nào? |
| Thời gian | Đánh giá thay đổi trong khoảng nào và sau bao lâu sử dụng? |
| Chỉ số bảo vệ | Điều gì không được xấu đi trong quá trình tối ưu? |

Chẳng hạn: “Trong nhóm học viên mới tự đăng ký, nâng tỷ lệ **hoàn thành bài học đầu tiên trong 7 ngày từ lúc đăng ký** từ mức tham chiếu 35% lên khoảng 45% trong giai đoạn thử nghiệm, đồng thời không làm tăng lỗi truy cập và yêu cầu hỗ trợ liên quan đến đăng ký”.

Các số liệu trên **chỉ là ví dụ giả định**. Chúng không phải chuẩn ngành hay lời dự báo. Nhóm chỉ nên chọn mục tiêu thực tế sau khi xem dữ liệu ban đầu, nguồn lực và các ràng buộc.

Không nên đặt mục tiêu kiểu “mọi người dùng đều phải hoàn thành trong 7 ngày” nếu người dùng có hành vi và nhu cầu rất khác nhau. Mục tiêu tạo định hướng; dữ liệu thực tế vẫn quyết định có nên tiếp tục giải pháp hay không.

## 4. Chọn chỉ số kết quả có ý nghĩa

Chỉ số tốt giúp đội học và quyết định. Nó cần liên quan đến vấn đề, đo được một cách nhất quán, đủ nhạy để phản ánh thay đổi và khó bị cải thiện bằng cách làm hại người dùng.

### 4.1. Phân biệt chỉ số đầu ra, sử dụng, kết quả và chất lượng

| Câu hỏi | Chỉ số ví dụ | Vai trò |
|---|---|---|
| Đã giao gì? | Số Increment đạt DoD, danh sách khả năng đã phát hành | Theo dõi **đầu ra** |
| Có ai tiếp cận giải pháp? | Tỷ lệ người dùng nhìn thấy hướng dẫn mới | Kiểm tra **mức tiếp xúc** với giải pháp |
| Người dùng có tương tác? | Tỷ lệ nhấp nút “Bắt đầu bài” | Tín hiệu **sử dụng**, chưa đủ chứng minh kết quả |
| Họ có hoàn thành việc quan trọng? | Tỷ lệ hoàn tất bài đầu tiên trong 7 ngày | Chỉ số **kết quả người dùng** |
| Việc đó có dễ dàng hơn? | Thời gian để tìm bài học, số lần cần hỗ trợ | Chỉ số **trải nghiệm và khả năng tự phục vụ** |
| Có tác dụng phụ không? | Tỷ lệ lỗi truy cập, tỷ lệ vào nhầm khóa, khiếu nại | **Chỉ số bảo vệ (guardrail)** |
| Giá trị dài hạn ra sao? | Tỷ lệ duy trì học tập, mức tiến bộ theo đánh giá | Tín hiệu **tác động dài hạn**, cần quan sát thêm |

Một đội không nhất thiết phải theo dõi tất cả. Hãy chọn **một hoặc vài chỉ số kết quả chính** cho giả thuyết hiện tại, cộng các chỉ số bảo vệ tối cần thiết.

### 4.2. Định nghĩa công thức, mẫu số và cửa sổ quan sát

“Tỷ lệ kích hoạt tăng” là một câu mơ hồ nếu mỗi người hiểu “kích hoạt” khác nhau. Giả sử định nghĩa kích hoạt là **học viên hoàn thành một bài học đầu tiên hợp lệ trong vòng 7 ngày kể từ đăng ký**:

\[
\text{Tỷ lệ kích hoạt 7 ngày} =
\frac{\text{Số học viên mới hoàn thành bài đầu tiên trong 7 ngày}}
{\text{Tổng số học viên mới đủ điều kiện trong cùng nhóm quan sát}}
\times 100\%
\]

Để số đo đáng tin, nhóm phải thống nhất:

1. **Đơn vị đếm:** người dùng duy nhất, không phải số lượt nhấp hoặc lượt hoàn thành.
2. **Điều kiện tham gia:** học viên mới có đăng ký hợp lệ, phân biệt tài khoản thử nghiệm/nội bộ và người dùng thực.
3. **Mốc bắt đầu:** thời điểm đăng ký thành công, theo một múi giờ và nguồn thời gian nhất quán.
4. **Cửa sổ đo:** người đăng ký ở ngày cuối kỳ phải được theo dõi đủ 7 ngày; không dùng ngay một cohort chưa trưởng thành để so với cohort cũ.
5. **Sự kiện hoàn thành:** bài nào được tính, hoàn thành theo tiêu chuẩn nào; tránh tính nhấp nút khi bài vẫn chưa làm xong.
6. **Độ tin cậy dữ liệu:** xử lý sự kiện trùng, thiếu dữ liệu, khác biệt giữa thiết bị và những trường hợp đăng nhập nhiều tài khoản.

Ví dụ: nếu trong một cohort có **1.200 học viên mới đủ điều kiện**, và **420 người** hoàn thành bài đầu trong 7 ngày, tỷ lệ là **420/1.200 = 35%**. Nếu một cohort sau có **1.100 người** và **473 người** hoàn thành, tỷ lệ là **43%**. Đội nhận thấy tín hiệu tăng 8 **điểm phần trăm**, nhưng chưa thể kết luận thay đổi sản phẩm là nguyên nhân duy nhất nếu hai cohort khác nhau về nguồn truy cập, mùa vụ, khóa học hoặc cách ghi nhận sự kiện.

### 4.3. Đọc mức thay đổi cho đúng

Khi tỷ lệ từ 35% lên 43%:

- **Thay đổi tuyệt đối:** 43% − 35% = **8 điểm phần trăm**.
- **Thay đổi tương đối:** (43% − 35%) / 35% ≈ **22,9%** so với ban đầu.

Hai con số diễn đạt cùng một quan sát nhưng không thể thay thế tùy tiện. Trong báo cáo cần nêu rõ mẫu số, giai đoạn và cách tính. Với chỉ số sự cố hiếm, mức thay đổi tương đối lớn vẫn có thể đến từ số lượng sự kiện rất nhỏ.

### 4.4. Phân nhóm đúng để tránh kết luận sai

Một tỷ lệ tổng hợp có thể che giấu vấn đề của một nhóm cụ thể:

- Người dùng **di động** có thể gặp khó khăn khác người dùng máy tính.
- Học viên **mới hoàn toàn** có hành vi khác học viên đã từng tham gia khóa khác.
- Người dùng **mạng chậm**, sử dụng **công nghệ hỗ trợ** hoặc có các nhu cầu tiếp cận khác nhau có thể bị ảnh hưởng không đều.
- Các khóa học có độ dài và mức độ yêu cầu khác nhau có thể khiến “hoàn thành bài đầu tiên” không tương đương.

Hãy chọn phân nhóm liên quan đến giả thuyết và có đủ dữ liệu, đồng thời bảo vệ quyền riêng tư. Không phân nhỏ đến mức người dùng có thể bị nhận diện hoặc kết luận từ mẫu quá ít.

### 4.5. Chỉ số bảo vệ ngăn cải thiện sai hướng

Giả sử đội tối ưu “hoàn thành bài đầu trong 7 ngày” bằng cách tự đánh dấu bài là hoàn thành khi người dùng chỉ mới mở trang. Chỉ số tăng nhưng trải nghiệm học không tốt hơn. Hoặc đội làm việc bắt đầu bài quá dễ nhưng vô tình cho phép người chưa thanh toán truy cập nội dung trả phí.

Chỉ số bảo vệ có thể là:

- Tỷ lệ truy cập sai quyền không tăng.
- Các sự cố hoặc lỗi quan trọng không tăng.
- Người dùng vẫn có thể hiểu mình đang học khóa nào.
- Không làm giảm khả năng sử dụng với bàn phím, trình đọc màn hình hoặc thiết bị hạn chế.
- Không khuyến khích thao tác gây phiền hà, đánh lừa hoặc thu thập dữ liệu quá mức.

**Tăng một con số không đủ nếu phải đánh đổi bằng chất lượng, an toàn hoặc sự tin cậy.**

## 5. Đo được khác với chứng minh nguyên nhân

Khi thấy kết quả cải thiện sau một bản phát hành, đội có thể muốn tuyên bố “tính năng mới đã giúp tăng 8 điểm phần trăm”. Đây là kết luận mạnh hơn dữ liệu trước–sau đơn thuần cho phép.

### 5.1. Các nguyên nhân thay thế cần xem xét

Kết quả có thể đổi vì:

- Nguồn người dùng thay đổi: chiến dịch thu hút khác, mùa đăng ký khác.
- Người dùng trong cohort sau vốn có động lực hoặc kỹ năng cao hơn.
- Đội hỗ trợ triển khai thêm hướng dẫn qua email đồng thời với thay đổi sản phẩm.
- Một lỗi khác được sửa hoặc một hệ thống phụ thuộc nhanh hơn.
- Định nghĩa sự kiện đo lường thay đổi, mất dữ liệu hoặc ghi trùng.
- Số lượng quan sát quá ít nên thay đổi có thể chỉ là dao động.

Vì vậy, hãy dùng ngôn ngữ đúng mức: “**Sau khi phát hành, tỷ lệ quan sát tăng** từ 35% lên 43% trong hai cohort được đo” thay vì ngay lập tức nói “**tính năng đã gây ra mức tăng**”.

### 5.2. Tạo bằng chứng mạnh hơn khi phù hợp

Một số cách tiếp cận:

| Phương pháp | Giúp trả lời | Giới hạn cần chú ý |
|---|---|---|
| Phỏng vấn và quan sát tác vụ | Người dùng vướng ở bước nào, họ hiểu và hành động ra sao? | Không tự đại diện cho toàn bộ quần thể; có thể có thiên lệch người tham gia |
| So sánh cohort trước–sau | Hành vi thay đổi thế nào theo thời gian? | Dễ bị nhiễu do mùa vụ, nguồn người dùng và nhiều thay đổi đồng thời |
| Thử nghiệm A/B ngẫu nhiên khi phù hợp | Nhóm dùng cách A và nhóm dùng cách B có khác nhau như thế nào dưới điều kiện kiểm soát? | Cần phân nhóm đúng, đủ dữ liệu và cân nhắc an toàn/đạo đức; không phù hợp mọi tình huống |
| Thử nghiệm giới hạn / phát hành theo giai đoạn | Giải pháp có hoạt động và có dấu hiệu hữu ích trong phạm vi nhỏ không? | Có thể cần thêm kiểm chứng trước khi khái quát hoặc mở rộng |
| Kiểm tra dữ liệu hỗ trợ và vận hành | Chất lượng sử dụng có thay đổi cùng lúc không? | Kênh hỗ trợ và cách ghi nhận lỗi có thể thay đổi |

Không cần tiến hành A/B test cho mọi quyết định nhỏ. Điều quan trọng là **mức chắc chắn của kết luận phù hợp với quy mô rủi ro và chi phí của quyết định**. Trong những tình huống bắt buộc khắc phục lỗi bảo mật nghiêm trọng, không được trì hoãn sửa lỗi chỉ để làm thử nghiệm đối chứng.

### 5.3. Xem định tính và định lượng là bổ sung cho nhau

Chỉ số cho biết “bao nhiêu và thay đổi theo hướng nào”; quan sát thực tế giúp hiểu “vì sao và bằng cách nào”. Nếu tỷ lệ hoàn tất vẫn thấp, phỏng vấn và xem hành trình người dùng có thể cho thấy vấn đề không nằm ở nút bắt đầu mà ở việc nội dung bài quá khó hoặc người dùng thiếu quyền truy cập.

Đội nên ghi rõ điều đã **biết**, điều **nghi ngờ** và điều **chưa thể kết luận**; từ đó chọn thử nghiệm kế tiếp. Sự trung thực này quan trọng hơn một báo cáo kết quả trông hoàn hảo.

## 6. Liên kết kết quả với user story và Product Backlog

Chuyển sang tư duy kết quả không có nghĩa bỏ backlog hoặc không cam kết sản phẩm. Nó thay đổi **cách lựa chọn và diễn giải các hạng mục cần xây**.

### 6.1. User story nêu nhu cầu; tiêu chí chấp nhận nêu điều phần mềm phải làm

Một user story:

> **Là** học viên mới, **tôi muốn** dễ dàng tìm bài học đầu tiên của khóa vừa đăng ký, **để** có thể bắt đầu học ngay mà không cần tìm kiếm hoặc nhờ hỗ trợ.

Ví dụ tiêu chí chấp nhận của một giải pháp được lựa chọn:

- Sau khi đăng ký thành công, học viên thấy rõ đường dẫn tới bài học đầu trong khóa đã đăng ký.
- Nếu chưa có quyền truy cập, sản phẩm hiển thị trạng thái chính xác và hướng dẫn tiếp theo phù hợp.
- Giao diện có thể dùng bằng bàn phím và đáp ứng yêu cầu truy cập đã thống nhất.
- Điều hướng không mở sai khóa hoặc làm mất thông tin phiên đăng nhập.

Các tiêu chí chấp nhận xác định **đầu ra phải hoạt động thế nào**. Chúng khác với mục tiêu kết quả “tăng tỷ lệ tự bắt đầu học trong bảy ngày”. Một story có thể đáp ứng toàn bộ tiêu chí mà không làm outcome cải thiện như kỳ vọng, vì giả thuyết về vấn đề người dùng có thể sai.

### 6.2. Definition of Done bảo vệ chất lượng đầu ra

Trong Scrum, Increment đáp ứng Definition of Done là bằng chứng phần mềm thực sự được hoàn thiện theo tiêu chuẩn chất lượng sản phẩm. DoD có thể bao gồm kiểm thử, tích hợp, bảo mật, khả năng truy cập và những điều kiện liên quan.

**Đạt DoD là điều cần để gọi Increment là hoàn tất trong Scrum; đạt mục tiêu outcome là câu hỏi tiếp theo về giá trị.** Không nên kéo định nghĩa Done vô hạn đến mức yêu cầu một tỷ lệ người dùng dùng tính năng mới phải đạt mục tiêu trước khi công nhận phần mềm hoàn tất. Khi đó đội sẽ mất khả năng phân biệt chất lượng giao hàng với hiệu quả sản phẩm.

Có thể diễn đạt bằng hai câu độc lập:

1. **Delivery:** “Increment hướng dẫn bài học đầu đã đạt DoD và được phát hành.”
2. **Outcome:** “Chúng ta sẽ kiểm tra xem học viên có tự bắt đầu và hoàn thành bài học đầu tiên nhiều hơn trong các cohort tiếp theo không.”

### 6.3. Từ backlog tính năng sang backlog phương án

Một backlog chỉ chứa “chatbot”, “video hướng dẫn”, “popup nhắc học” dễ khiến giải pháp trở thành mục đích. Có thể nhóm các phương án quanh vấn đề hoặc cơ hội:

| Vấn đề/cơ hội | Phương án có thể thử | Bằng chứng mong muốn |
|---|---|---|
| Học viên không biết bắt đầu từ đâu | Nút bắt đầu rõ hơn; hướng dẫn ngắn đúng ngữ cảnh; đơn giản hóa menu | Tự bắt đầu bài đầu dễ hơn, ít phải liên hệ hỗ trợ |
| Học viên nhập sai mã khóa học | Kiểm tra định dạng tức thời; giải thích lỗi; quét mã nếu phù hợp | Ít lượt nhập sai, thời gian đăng ký giảm |
| Người dùng không biết trạng thái thanh toán | Hiển thị trạng thái; gửi thông báo rõ; cải thiện trang hỗ trợ | Ít giao dịch bị thao tác lặp, ít câu hỏi về trạng thái |

Product Owner có thể ưu tiên phương án dựa trên giá trị dự kiến, rủi ro, chi phí, độ không chắc chắn và điều kiện kinh doanh. Không cần chọn giải pháp có nhiều tính năng nhất; có khi việc **gỡ một bước thừa** đem lại kết quả tốt hơn việc xây một tính năng mới.

### 6.4. Quyết định khi outcome không đạt

Sau khi một giải pháp được phát hành đạt chất lượng, Product Owner và đội có thể:

- **Tiếp tục:** Tín hiệu cho thấy giả thuyết hợp lý và còn cơ hội cải thiện.
- **Mở rộng có kiểm soát:** Kết quả tích cực, rủi ro chấp nhận được và dữ liệu đủ tin cậy.
- **Điều chỉnh:** Người dùng thích giải pháp nhưng vướng một bước cụ thể.
- **Thử giả thuyết khác:** Vấn đề thực tế khác điều đội đã nghĩ.
- **Dừng:** Giải pháp không đem lại lợi ích tương xứng hoặc tạo tác dụng phụ lớn.

Nếu chưa đủ bằng chứng, lựa chọn hợp lý có thể là **thu thập thêm dữ liệu**. Không phải mọi lần kiểm tra đều phải dẫn đến thay đổi; giữ nguyên hướng đi có chủ đích cũng là một quyết định.

## 7. Scrum, Kanban và XP giúp chuyển từ đầu ra sang kết quả như thế nào?

Ba cách tiếp cận này hỗ trợ các phần khác nhau của vòng học tập. Không có khung nào tự động bảo đảm outcome tốt nếu đội không xác định đúng vấn đề người dùng.

### 7.1. Scrum: kiểm tra Increment và thích ứng Product Backlog

Trong Scrum:

- **Product Goal** mô tả mục tiêu dài hạn mà Scrum Team hướng tới; nó tạo bối cảnh để lựa chọn Product Backlog Items. Một mục tiêu tốt thường dễ liên hệ với vấn đề hoặc giá trị sản phẩm.
- **Product Owner** chịu trách nhiệm tối đa hóa giá trị sản phẩm và quản lý Product Backlog hiệu quả; họ phải cân nhắc thông tin người dùng và các ràng buộc.
- **Sprint Goal** nêu mục tiêu chung của Sprint, tạo sự tập trung và khả năng linh hoạt về cách thực hiện.
- **Increment** đáp ứng DoD là bằng chứng đầu ra phần mềm hoạt động được, có thể đem đến người liên quan để kiểm tra.
- **Sprint Review** là cơ hội Scrum Team và stakeholders kiểm tra kết quả Sprint, hoàn cảnh thay đổi và lựa chọn bước tiếp theo; Product Backlog có thể được điều chỉnh.
- **Sprint Retrospective** giúp cải thiện chất lượng và hiệu quả tạo sản phẩm, giảm cản trở đối với vòng phản hồi.

Một Sprint Review hữu ích không chỉ hỏi “đã làm xong bao nhiêu?”. Nó còn hỏi “chúng ta biết thêm gì về nhu cầu, hành vi và kết quả người dùng?”, “những điều mới học ảnh hưởng tới ưu tiên nào?”.

**Lưu ý:** Scrum không bắt buộc mỗi Sprint phải chứng minh cải thiện một chỉ số kinh doanh trong thời gian ngắn. Nhiều outcome cần theo dõi dài hơn Sprint hoặc chịu tác động của nhiều Increment. Trách nhiệm của đội là giữ bằng chứng minh bạch và liên tục thu hẹp bất định về giá trị.

### 7.2. Kanban: rút ngắn thời gian từ ý tưởng đến bằng chứng

Kanban giúp hiển thị dòng công việc, giới hạn WIP khi phù hợp và phát hiện các điểm chờ. Chỉ số như **work item age, cycle time, throughput, WIP** phục vụ quản lý và dự báo luồng công việc.

Ví dụ, khi mười hạng mục đồng thời đang “phát triển” nhưng chưa hạng mục nào được tích hợp, nhóm có ít cơ hội đưa phần mềm tới người dùng để học. Quyết định giảm WIP, cùng xử lý một mục bị chặn và hoàn tất lát cắt quan trọng có thể rút ngắn **thời gian đến phản hồi**.

Tuy vậy, **cycle time giảm không tự chứng minh outcome người dùng tốt hơn**. Nó cho thấy đội có thể đưa thay đổi qua hệ thống nhanh hơn. Đội vẫn phải xem thay đổi đó có thực sự giúp người dùng không.

### 7.3. XP: giảm chi phí kiểm chứng giả thuyết

Những thực hành như TDD khi phù hợp, kiểm thử hồi quy, tích hợp liên tục, refactoring, lập trình cặp hoặc phát hành nhỏ giúp đội đưa thay đổi vào hệ thống an toàn hơn. Khi có phản hồi rằng một giả thuyết sai, đội có cơ hội sửa nhanh mà không đánh đổi chất lượng.

Giả sử hướng dẫn mới khiến tỷ lệ hoàn tất tăng ở máy tính nhưng làm người dùng điện thoại gặp lỗi. Nếu đội có kiểm thử trải nghiệm và cơ chế triển khai an toàn, đội dễ sửa hoặc quay lui hơn. Khả năng kỹ thuật tốt giúp **học nhanh với rủi ro kiểm soát được**; nó không thay thế nghiên cứu nhu cầu và quyết định về giá trị.

## 8. Tình huống xuyên suốt: kích hoạt học viên mới

> **Tình huống giả định để học tập:** Tất cả số lượng, tỷ lệ, mục tiêu và quan sát dưới đây được đặt ra để minh họa cách phân biệt đầu ra với kết quả; chúng không phải số liệu nghiên cứu hay chuẩn áp dụng cho mọi sản phẩm.

Một nền tảng học trực tuyến nhận thấy nhiều tài khoản mới đăng ký thành công nhưng không thực sự bắt đầu học. Đội phát triển được đề xuất xây một trang onboarding gồm năm bước, một video giới thiệu, bảng thành tích và hệ thống email nhắc học.

### 8.1. Cách làm chỉ dựa trên đầu ra

Product Backlog chứa bốn nhóm tính năng đã liệt kê. Kế hoạch Sprint đặt mục tiêu hoàn thành đủ các hạng mục. Báo cáo sau sáu tuần ghi:

- Đã bàn giao trang onboarding.
- Đã phát hành video giới thiệu.
- Đã kích hoạt email nhắc học.
- 100% ticket được đóng; tất cả kiểm thử đã thỏa DoD.

Đây là thông tin **có giá trị về giao hàng và chất lượng**. Nhưng nó chưa trả lời: học viên mới có bắt đầu học nhiều hơn, nhanh hơn, ít lúng túng hơn hay không?

### 8.2. Đổi câu hỏi trước khi chọn giải pháp

Đội đặt câu hỏi: “Trong bảy ngày đầu sau đăng ký, bao nhiêu học viên hoàn thành một bài học đầu tiên hợp lệ? Những ai không hoàn thành đang vướng ở đâu?”

Họ thống nhất:

- **Đối tượng:** tài khoản học viên mới đăng ký khóa học đủ điều kiện.
- **Outcome chính:** tỷ lệ học viên hoàn thành bài học đầu tiên trong vòng 7 ngày.
- **Baseline minh họa:** cohort gần nhất có 1.200 người, 420 người hoàn thành bài đầu, tương ứng 35%.
- **Mục tiêu thử nghiệm giả định:** đạt khoảng 45% với nhóm phù hợp, không đánh đổi chất lượng hoặc an toàn.
- **Guardrails:** lỗi truy cập, nhầm khóa, yêu cầu hỗ trợ về đăng ký và phản hồi tiêu cực không tăng đáng kể.
- **Thông tin định tính:** quan sát người học và trao đổi với bộ phận hỗ trợ về nguyên nhân bỏ dở.

Nhóm không coi “45%” là một lời hứa chắc chắn. Đây là một giả thuyết mục tiêu để xem mức cải thiện có ý nghĩa; kế hoạch sẽ được điều chỉnh theo bằng chứng.

### 8.3. Phát hiện một vấn đề nhỏ nhưng có tác động

Khi quan sát một số phiên sử dụng, nhóm thấy người đăng ký xong thường quay về trang danh mục, không nhận ra khóa học của mình đang nằm trong mục “Khóa của tôi”. Giả thuyết mới là **lối vào bài học đầu tiên chưa đủ rõ**, không nhất thiết là người dùng thiếu video hướng dẫn.

Nhóm chọn một lát cắt nhỏ:

1. Hiển thị nút “Bắt đầu học” đúng khóa vừa đăng ký.
2. Cho phép truy cập bài học đầu tiên khi đã có quyền.
3. Thông báo rõ nếu cần hoàn tất bước đăng ký khác.
4. Kiểm thử các hành vi, quyền truy cập, lỗi và khả năng sử dụng phù hợp.

Đây là **đầu ra có thể bàn giao và kiểm tra**. Bản thân nút mới chưa phải outcome. Sau khi Increment đạt DoD và được phát hành có kiểm soát, đội theo dõi việc học viên thực sự có hoàn thành tác vụ hơn không.

### 8.4. Đọc kết quả thử nghiệm một cách thận trọng

Giả sử cohort sau có 1.100 học viên đủ điều kiện, 473 người hoàn thành bài đầu trong 7 ngày. Tỷ lệ quan sát là **43%**. So với baseline 35%, mức tăng là **8 điểm phần trăm**.

Nhóm cần phân biệt:

| Kết luận | Có đủ căn cứ từ dữ liệu minh họa không? | Vì sao? |
|---|---|---|
| “Nút Bắt đầu học đã được phát hành đạt DoD.” | **Có**, nếu chứng cứ kiểm thử và phát hành xác nhận | Đây là kết luận về **đầu ra và chất lượng** |
| “Tỷ lệ kích hoạt quan sát tăng từ 35% lên 43%.” | **Có**, nếu dữ liệu cohort và định nghĩa đo nhất quán | Đây là mô tả **kết quả quan sát** |
| “Chính nút mới gây ra toàn bộ mức tăng 8 điểm phần trăm.” | **Chưa đủ** | Cần xem nhóm người dùng, các thay đổi đồng thời và cách kiểm soát yếu tố nhiễu |
| “Giải pháp đã đạt mục tiêu 45%.” | **Chưa** | Chỉ số hiện quan sát là 43%, dù có tín hiệu tích cực |
| “Chúng ta phải tiếp tục xây ba tính năng còn lại.” | **Không suy ra được** | Phải xem vấn đề còn lại, giá trị dự kiến và bằng chứng mới |

Nhóm xem thêm dữ liệu theo thiết bị, các bước người dùng bỏ dở và phản hồi. Nếu phần lớn người dùng đã tìm được bài nhưng chưa hoàn thành vì bài quá dài, họ có thể ưu tiên cải thiện cấu trúc bài học thay vì tiếp tục xây video onboarding dài. Nếu phát hiện cohort mới có nguồn truy cập khác, nhóm cần điều chỉnh cách so sánh trước khi khẳng định tác động.

### 8.5. Sau Sprint Review, điều gì thay đổi?

Trong Sprint Review, đội trình diễn Increment đã hoàn tất và chia sẻ tín hiệu outcome cùng giới hạn của dữ liệu. Stakeholders đóng góp bối cảnh mới: nhiều học viên trên điện thoại kết nối chậm nên gặp khó khi mở bài đầu tiên. Product Owner cân nhắc thay đổi ưu tiên:

- Giữ khả năng dẫn vào bài học đầu đã được phát hành.
- Đưa xử lý tải chậm và thông báo lỗi của trình phát lên trước bảng thành tích.
- Tiếp tục theo dõi tỷ lệ hoàn thành bài đầu và chất lượng trên thiết bị di động.
- Chỉ mở rộng giải pháp khi đủ bằng chứng và chấp nhận được các rủi ro.

Đội đã đi từ chuỗi “**xây tính năng → đánh dấu xong**” sang “**xây Increment → quan sát sử dụng → điều chỉnh quyết định**”. Lịch Sprint, các vai trò và tiêu chuẩn chất lượng vẫn hữu ích, nhưng chúng phục vụ mục tiêu kết quả rõ ràng hơn.

## 9. Đầu ra và kết quả trong các tình huống thực tế khác

### 9.1. Sản phẩm thương mại điện tử

| Đầu ra | Kết quả người dùng cần xem | Guardrail |
|---|---|---|
| Bộ lọc sản phẩm mới | Người mua tìm được sản phẩm phù hợp nhanh hơn, ít phải thử lại | Không che giấu sản phẩm hợp lệ hoặc làm giảm khả năng truy cập |
| Nút “Mua ngay” | Người mua hoàn thành giao dịch mong muốn với ít thao tác khó hiểu | Không tăng mua nhầm, hoàn tiền do lỗi hoặc vấn đề bảo mật |
| Email nhắc giỏ hàng | Người mua nhớ và hoàn tất giao dịch họ thật sự muốn | Không tạo spam, khó chịu hoặc vi phạm lựa chọn nhận thông báo |

### 9.2. Sản phẩm nội bộ doanh nghiệp

| Đầu ra | Kết quả người dùng cần xem | Guardrail |
|---|---|---|
| Dashboard theo dõi xử lý yêu cầu | Nhân viên xác định yêu cầu cần ưu tiên nhanh và chính xác hơn | Không tạo áp lực xử lý sai quy trình hoặc đánh giá cá nhân thiếu bối cảnh |
| Tự động nhập liệu từ biểu mẫu | Nhân viên giảm thao tác nhập lặp và sửa lỗi dữ liệu | Không tăng lỗi đối soát hoặc truy cập sai quyền |
| Chức năng phê duyệt trên điện thoại | Người có trách nhiệm duyệt đúng hạn mà vẫn có đủ thông tin ra quyết định | Không bỏ qua kiểm soát phân quyền và truy vết |

Đội xây sản phẩm nội bộ vẫn cần phỏng vấn người dùng thực, quan sát công việc và kiểm tra các tác động ngoài ý muốn. “Có người dùng nội bộ bắt buộc sử dụng” không chứng minh trải nghiệm có hiệu quả.

### 9.3. Công việc kỹ thuật không hiển thị thành tính năng

Không phải mọi đầu ra là màn hình. Một pipeline CI ổn định, cơ chế khôi phục dữ liệu, refactoring hoặc kiểm soát bảo mật có thể tạo **năng lực tổ chức** và **kết quả vận hành**.

| Đầu ra kỹ thuật | Kết quả mong muốn | Cách kiểm chứng |
|---|---|---|
| Tự động hóa kiểm thử hồi quy | Đội phát hiện lỗi sớm, giảm lỗi lọt ra môi trường sử dụng | Số sự cố phù hợp, thời gian phát hiện, phân tích lỗi |
| Cải thiện pipeline triển khai | Thay đổi nhỏ đến người dùng an toàn và đều hơn | Thời gian đưa thay đổi qua pipeline, tỷ lệ lỗi thay đổi |
| Cơ chế backup và phục hồi | Có thể khôi phục dữ liệu khi xảy ra sự cố | Diễn tập phục hồi, tính toàn vẹn dữ liệu, mục tiêu khôi phục |
| Refactoring hệ thống phân quyền | Giảm nguy cơ cấp quyền sai, dễ phát triển nghiệp vụ mới an toàn | Kiểm thử quyền, lỗi phân quyền, khả năng sửa đổi đã kiểm chứng |

Tránh đòi hỏi mọi công việc nền tảng phải làm tăng một chỉ số chuyển đổi ngay lập tức. Hãy gắn nó với **rủi ro hoặc năng lực có thể kiểm chứng**, đồng thời nhìn rõ mục tiêu lớn hơn mà công việc phục vụ.

## 10. Giá trị có nhiều mặt và có các ràng buộc

Người dùng, khách hàng trả tiền, người vận hành và tổ chức có thể có lợi ích khác nhau. Một outcome tốt trong một mặt chưa chắc tốt cho toàn hệ thống.

Ví dụ: giảm thời gian xử lý ticket hỗ trợ là kết quả có vẻ tích cực. Nhưng nếu đội đóng ticket sớm khi vấn đề chưa được giải quyết, người dùng phải liên hệ lại nhiều lần, tổng chi phí và mức khó chịu đều tăng. Vì vậy, ngoài thời gian xử lý, cần xem **tỷ lệ giải quyết đúng vấn đề, yêu cầu mở lại và phản hồi người dùng**.

### 10.1. Mối quan hệ giữa outcome người dùng và mục tiêu kinh doanh

Nhiều mục tiêu kinh doanh được phục vụ gián tiếp qua việc người dùng đạt được mục tiêu:

~~~mermaid
flowchart TD
    A["Người học tự bắt đầu và hoàn thành bài đầu"] --> B["Trải nghiệm ban đầu rõ ràng, ít trở ngại"]
    B --> C["Có thêm cơ hội duy trì học tập"]
    C --> D["Giá trị dài hạn cho người học và tổ chức"]
    E["Bảo mật, chất lượng, khả năng truy cập"] --> A
    E --> B
~~~

Các mũi tên biểu thị giả thuyết kinh doanh cần kiểm tra theo thời gian. Một thay đổi giúp hoàn tất bài đầu có thể không cải thiện duy trì sau một tháng nếu nội dung bài học không phù hợp. Tránh coi một tín hiệu ngắn hạn là bảo đảm tác động dài hạn.

### 10.2. Có những đầu ra bắt buộc

Trong dự án có nghĩa vụ hợp đồng, pháp lý, kiểm toán hoặc an toàn, một đầu ra cụ thể có thể là điều bắt buộc: báo cáo theo quy định, quy trình lưu trữ hồ sơ, chức năng kiểm soát truy cập. Tư duy hướng outcome không cho phép bỏ qua các nghĩa vụ này.

Cách áp dụng phù hợp là **nói rõ đầu ra bắt buộc, tiêu chuẩn chất lượng phải đạt và kết quả dự kiến cần bảo vệ**. Ví dụ, một chức năng xác thực đa yếu tố bắt buộc có outcome về an toàn; không thể trì hoãn triển khai chỉ vì tỷ lệ chuyển đổi giảm trong một thử nghiệm ngắn.

## 11. Quy trình thực hành: từ yêu cầu tính năng đến quyết định dựa trên kết quả

Một nhóm có thể sử dụng chu trình nhỏ sau trong công việc hằng ngày:

~~~mermaid
flowchart TD
    A["Nhận yêu cầu hoặc phát hiện vấn đề"] --> B["Làm rõ người dùng và việc họ muốn hoàn tất"]
    B --> C["Đặt giả thuyết kết quả và guardrail"]
    C --> D["Chọn giải pháp nhỏ, kiểm chứng được"]
    D --> E["Xây Increment đạt chất lượng"]
    E --> F["Đưa tới môi trường hoặc người dùng phù hợp"]
    F --> G["Đo kết quả và quan sát phản hồi"]
    G --> H{"Bằng chứng dẫn đến quyết định nào?"}
    H -->|Tiếp tục| D
    H -->|Đổi giải pháp| C
    H -->|Cần hiểu thêm| B
    H -->|Đạt mục tiêu hoặc dừng| I["Ghi nhận bài học và chọn vấn đề tiếp theo"]
~~~

### 11.1. Mẫu chuyển đổi một yêu cầu

Giả sử đầu vào là “**Thêm chức năng chatbot hỏi đáp**”. Thay vì đưa trực tiếp vào Sprint:

| Bước | Câu trả lời minh họa |
|---|---|
| Yêu cầu ban đầu | Thêm chatbot hỏi đáp |
| Người dùng | Học viên mới đang gặp lỗi khi bắt đầu khóa học |
| Vấn đề | Họ không hiểu cách xử lý lỗi truy cập và phải chờ nhân viên hỗ trợ |
| Outcome mong muốn | Nhiều học viên tự giải quyết lỗi thông thường, ít phải liên hệ hỗ trợ, thời gian khắc phục giảm |
| Bằng chứng hiện có | Ticket hỗ trợ, nội dung lỗi thường gặp, quan sát thao tác |
| Phương án 1 | Viết lại thông báo lỗi và hướng dẫn ngay tại màn hình |
| Phương án 2 | Cải thiện trang trợ giúp theo mã lỗi |
| Phương án 3 | Thử chatbot trong phạm vi câu hỏi phù hợp |
| Guardrail | Không hướng dẫn sai gây mất dữ liệu, không làm lộ thông tin tài khoản, có đường chuyển sang hỗ trợ con người |
| Quyết định ban đầu | Thử phương án nhỏ nhất có thể kiểm chứng trước khi đầu tư giải pháp lớn |

Cách làm này không tự mặc định chatbot là lựa chọn sai. Nó yêu cầu **so sánh giải pháp theo khả năng tạo kết quả** thay vì mức hấp dẫn của công nghệ.

### 11.2. Nhật ký quyết định gọn

~~~text
VẤN ĐỀ: [Ai đang gặp trở ngại gì?]
MỤC TIÊU KẾT QUẢ: [Thay đổi nào cần quan sát?]
BASELINE: [Giá trị ban đầu, thời kỳ đo, đối tượng]
GIẢ THUYẾT GIẢI PHÁP: [Nếu làm X, kỳ vọng Y vì Z]
ĐẦU RA DỰ KIẾN: [Lát cắt phần mềm/hiện vật sẽ giao]
CHẤT LƯỢNG: [Tiêu chí chấp nhận, DoD và ràng buộc]
CHỈ SỐ / GUARDRAIL: [Định nghĩa, mẫu số, cửa sổ đo]
NGƯỜI QUYẾT ĐỊNH: [Vai trò và người cần được tham vấn]
BẰNG CHỨNG SAU TRIỂN KHAI: [Thực tế, nguồn, giới hạn]
QUYẾT ĐỊNH TIẾP THEO: [Giữ, sửa, mở rộng, dừng, thử thêm]
MỐC XEM LẠI: [Khi nào hoặc sau điều kiện nào]
~~~

Đây là công cụ hỗ trợ tư duy, không phải biểu mẫu bắt buộc. Với một thay đổi nhỏ, vài dòng có thể đủ; với quyết định lớn hoặc rủi ro cao, cần lưu bằng chứng đầy đủ hơn.

## 12. Những sai lầm cần tránh khi chuyển sang outcome

### Sai lầm 1: Chỉ đổi tên KPI nhưng không đổi quyết định

Nhóm gọi “số lượt nhấp” là outcome rồi vẫn xây toàn bộ tính năng theo danh sách cũ. Từ ngữ không giúp ích nếu phản hồi không thể thay đổi ưu tiên, phạm vi hoặc thiết kế.

**Cách khắc phục:** Ghi rõ “nếu kết quả trái giả thuyết, chúng ta sẽ làm gì khác?” trước khi triển khai.

### Sai lầm 2: Coi tất cả tỷ lệ chuyển đổi tăng là tốt

Tỷ lệ mua hàng có thể tăng nhờ thiết kế gây hiểu nhầm; thời gian ở lại ứng dụng có thể tăng vì điều hướng khó. Một chỉ số có thể tốt cho báo cáo nhưng xấu cho người dùng.

**Cách khắc phục:** Chọn outcome liên quan trực tiếp đến việc người dùng muốn hoàn tất, bổ sung guardrail và quan sát định tính.

### Sai lầm 3: Hứa outcome như cam kết giao một tính năng

Đội kiểm soát khá trực tiếp tiến độ và chất lượng phát triển, nhưng không kiểm soát hoàn toàn hành vi người dùng hoặc thị trường. Việc khẳng định “chắc chắn tăng 20% chuyển đổi” ngay khi chưa có bằng chứng gây áp lực che giấu kết quả không thuận lợi.

**Cách khắc phục:** Cam kết rõ chất lượng thực hiện, minh bạch giả thuyết, mốc học tập và mục tiêu kết quả cần hướng tới; làm rõ mức độ chắc chắn của dự báo.

### Sai lầm 4: Bỏ qua chất lượng đầu ra vì chỉ quan tâm outcome

Một đội có thể cố tăng lượt đăng ký bằng cách bỏ kiểm tra bảo mật, giấu lỗi thanh toán hoặc hạ DoD. Kết quả ngắn hạn có thể cải thiện trong khi rủi ro tăng.

**Cách khắc phục:** Duy trì tiêu chuẩn chất lượng và ràng buộc đạo đức; kết hợp outcome với khả năng vận hành an toàn.

### Sai lầm 5: Dùng outcome để xếp hạng cá nhân

Một kỹ sư không tự kiểm soát tỷ lệ duy trì người dùng; kết quả phụ thuộc vào nhiều quyết định liên chức năng. Gắn lương thưởng cá nhân trực tiếp với một outcome dễ tạo hành vi đối phó.

**Cách khắc phục:** Xem outcome ở cấp độ sản phẩm hoặc đội phù hợp, với trách nhiệm cộng tác và bối cảnh rõ ràng.

### Sai lầm 6: Kết luận sớm từ mẫu nhỏ

Hai người dùng khen giao diện hoặc một ngày chỉ số tăng không chứng minh giải pháp hiệu quả cho toàn bộ tập người dùng. Dữ liệu còn thiếu hoặc cohort chưa đủ thời gian có thể gây sai lệch.

**Cách khắc phục:** Thống nhất mốc đánh giá, kiểm tra chất lượng dữ liệu và giới hạn suy luận; với quyết định quan trọng, thu thập bằng chứng mạnh hơn.

### Sai lầm 7: Bỏ quên những người chưa thể sử dụng sản phẩm

Chỉ đo người dùng đã nhấp vào tính năng sẽ bỏ qua nhóm không tìm thấy tính năng hoặc bị chặn vì thiết bị, khả năng truy cập hay quyền sử dụng. Một cải thiện trong nhóm tiếp xúc có thể che giấu sự loại trừ ở nhóm còn lại.

**Cách khắc phục:** Xem cả tỷ lệ tiếp xúc, phạm vi tiếp cận, quá trình hoàn tất và nhóm bị ảnh hưởng.

## 13. Bài tập vận dụng

### Bài tập A — Phân loại dữ kiện

Một đội có các phát biểu:

1. “Nhóm đã tổ chức ba buổi phỏng vấn và hoàn tất kiểm thử.”
2. “Chúng tôi phát hành tính năng lưu khóa học yêu thích.”
3. “Người học quay lại đúng khóa quan tâm nhanh hơn mà không cần tìm lại.”
4. “Tỷ lệ học viên duy trì hoạt động sau ba tháng tăng trong cohort được theo dõi.”

Hãy phân loại **hoạt động, đầu ra, outcome hoặc impact**, đồng thời cho biết mỗi phát biểu còn thiếu bằng chứng gì để ra quyết định tiếp theo.

<details>
<summary>Gợi ý đáp án</summary>

1 là hoạt động; 2 là đầu ra; 3 là outcome vì mô tả khả năng và hành vi của người học; 4 là tín hiệu tác động dài hơn (có thể được quản lý như outcome dài hạn trong mô hình khác). Cần biết số lượng/mẫu người dùng, định nghĩa chỉ số, baseline, điều kiện chất lượng và các yếu tố ngoài sản phẩm. Không thể kết luận tính năng lưu khóa học là nguyên nhân của thay đổi ở câu 4 nếu chưa kiểm tra giả thuyết và các yếu tố nhiễu.

</details>

### Bài tập B — Đổi từ yêu cầu tính năng sang giả thuyết kết quả

Một stakeholder yêu cầu: “Hãy thêm năm loại email nhắc học để tăng mức độ tham gia”.

Hãy viết lại yêu cầu theo cấu trúc:

1. Người dùng và vấn đề cụ thể.
2. Outcome mong muốn, có cách đo.
3. Hai phương án có thể thử ngoài việc thêm email.
4. Ít nhất hai guardrail chống làm phiền hoặc gây hiểu nhầm.

<details>
<summary>Gợi ý đáp án</summary>

Ví dụ, vấn đề là học viên đã đăng ký không nhớ bước học tiếp theo. Outcome là tăng tỷ lệ họ tự tiếp tục đúng bài trong 7 ngày. Hai phương án khác: nút “Tiếp tục học” rõ ràng khi mở ứng dụng hoặc lịch học tự chọn với thông báo theo sở thích. Guardrail: tỷ lệ hủy đăng ký thông báo không tăng quá mức đội chấp nhận, không gửi sai khóa, không làm lộ dữ liệu học tập và phải tôn trọng lựa chọn nhận thông báo. Cần kiểm tra xem quên lịch có thực sự là nguyên nhân trước khi triển khai nhiều email.

</details>

### Bài tập C — Đọc dữ liệu mà không suy diễn

Một sản phẩm báo cáo tỷ lệ người dùng hoàn tất đăng ký tăng từ 40% lên 46% sau khi phát hành màn hình mới. Cùng lúc, chiến dịch quảng cáo chuyển từ nhóm khách hàng mới sang nhóm khách hàng đã biết sản phẩm.

Hãy nêu:

- Thay đổi tuyệt đối theo điểm phần trăm.
- Vì sao chưa đủ căn cứ quy kết toàn bộ mức tăng cho màn hình mới.
- Hai loại dữ liệu cần bổ sung để ra quyết định tự tin hơn.

<details>
<summary>Gợi ý đáp án</summary>

Mức tăng tuyệt đối là **6 điểm phần trăm**. Đặc điểm người dùng đã thay đổi cùng thời điểm phát hành, nên khác biệt về động lực và kiến thức trước đó có thể ảnh hưởng tỷ lệ hoàn tất. Có thể xem phân nhóm theo nguồn người dùng/cohort, dữ liệu quan sát bước bỏ dở, kiểm tra tính nhất quán của sự kiện và cân nhắc thử nghiệm đối chứng phù hợp nếu đủ điều kiện. Mục tiêu là giảm bất định, không khẳng định nhân quả từ một biểu đồ trước–sau.

</details>

### Bài tập D — Outcome có cải thiện nhưng guardrail xấu đi

Đội triển khai tính năng thanh toán “một nhấp”. Tỷ lệ giao dịch hoàn tất tăng, nhưng phản ánh về mua nhầm và hoàn tiền cũng tăng đáng kể.

Bạn là Product Owner. Bạn sẽ đặt câu hỏi nào, kiểm tra dữ liệu nào và có các lựa chọn quyết định nào trước Sprint tiếp theo?

<details>
<summary>Gợi ý đáp án</summary>

Cần xem người dùng nào bị ảnh hưởng, điều kiện xác nhận giao dịch, tỷ lệ hoàn tiền do thao tác nhầm, dữ liệu khiếu nại và rủi ro bảo mật. Các lựa chọn có thể là giảm phạm vi phát hành, thêm xác nhận phù hợp ngữ cảnh, khôi phục luồng trước hoặc thử một phương án ít gây nhầm hơn. Không nên coi tỷ lệ hoàn tất tăng là thành công vô điều kiện khi guardrail về sự tin cậy và chất lượng xấu đi.

</details>

### Bài tập E — Phân biệt Done với đạt outcome

Một đội Scrum đã hoàn thành Increment “hiển thị lịch học cá nhân” theo tất cả tiêu chí chấp nhận và DoD. Sau ba tuần, tỷ lệ học viên bỏ lỡ buổi học không giảm.

Hãy trả lời: Increment có được coi là hoàn tất không? Nhóm nên xem lại điều gì và nên báo cáo như thế nào?

<details>
<summary>Gợi ý đáp án</summary>

Nếu thực sự đáp ứng DoD, Increment vẫn hoàn tất về mặt giao hàng. Outcome mong muốn chưa đạt, nên Product Owner và đội cần xem mức độ người dùng thấy và sử dụng lịch học, giả thuyết ban đầu, các nguyên nhân khác khiến bỏ lỡ buổi học và chất lượng dữ liệu. Báo cáo nên tách **“đã giao Increment đạt DoD”** và **“chưa quan sát thấy cải thiện outcome”**, sau đó đề xuất bước học tập hoặc giải pháp kế tiếp.

</details>

## 14. Bộ câu hỏi kiểm tra cho Sprint Review hoặc Product Backlog Refinement

Khi thảo luận một tính năng đã hoặc sắp xây, thử trả lời:

1. Người dùng cần hoàn thành việc gì, trong tình huống nào?
2. Chúng ta đang ghi nhận vấn đề thật hay chỉ một đề xuất giải pháp?
3. Đầu ra sẽ bàn giao có hành vi rõ và tiêu chuẩn chất lượng phù hợp không?
4. Nếu đầu ra hoạt động chính xác, hành vi người dùng nào *được kỳ vọng* thay đổi?
5. Outcome đó có mức ban đầu, mẫu quan sát, định nghĩa và thời gian đo không?
6. Những người không thể tiếp cận tính năng có bị bỏ qua trong phép đo không?
7. Còn giải pháp nào ít tốn kém hoặc ít rủi ro hơn mà vẫn có thể giải quyết vấn đề?
8. Chỉ số bảo vệ nào giúp tránh tối ưu một con số bằng cách gây bất lợi khác?
9. Bằng chứng từ Increment, người dùng và hệ thống đã nói gì; điều gì vẫn chưa rõ?
10. Sau khi kiểm tra, Product Backlog hoặc quyết định tiếp theo thay đổi cụ thể ra sao?

Không phải câu hỏi nào cũng cần một tài liệu dài. Điều quan trọng là đội có thể đưa ra **minh chứng đủ tin cậy, quyền quyết định rõ và lựa chọn tiếp theo có trách nhiệm**.

## 15. Tổng kết

- **Đầu ra** là thứ đội xây và bàn giao: tính năng, Increment, tài liệu, thay đổi hệ thống. Nó thường được đội kiểm soát trực tiếp hơn và có thể kiểm chứng bằng tiêu chí chấp nhận, Definition of Done và bằng chứng phát hành.
- **Kết quả** là thay đổi có ích đối với người dùng: hoàn tất việc quan trọng hơn, nhanh hơn, an toàn hơn hoặc với ít nỗ lực hơn. Nó cần quan sát trong bối cảnh thực tế và có thể không đạt dù đầu ra đúng kế hoạch.
- **Tác động dài hạn** là tầng giá trị rộng hơn cho người dùng và tổ chức. Nó thường xuất hiện chậm và không nên quy kết vội cho một tính năng đơn lẻ.
- **Outcome tốt cần được định nghĩa và đo đúng**: đối tượng, hành vi, baseline, cửa sổ quan sát, mẫu số và guardrail. Dữ liệu trước–sau là tín hiệu hữu ích nhưng chưa đủ tự động chứng minh nguyên nhân.
- **Agile sử dụng đầu ra để học về kết quả**: xây lát cắt nhỏ có chất lượng, kiểm tra Increment, nhận phản hồi, điều chỉnh Product Backlog và cải tiến dòng công việc lẫn kỹ thuật.

Với mỗi tính năng được yêu cầu hoặc vừa phát hành, hãy hỏi: **“Chúng ta đã giao được gì, người dùng thực sự làm tốt hơn điều gì, bằng chứng nào cho thấy điều đó, và lựa chọn tiếp theo nên thay đổi ra sao?”** Trả lời được cả bốn câu hỏi sẽ giúp nhóm phát triển sản phẩm hướng tới giá trị thay vì chỉ hoàn tất danh sách bàn giao.

## Tài liệu tham khảo định hướng

- [Manifesto for Agile Software Development](https://agilemanifesto.org/): các giá trị và nguyên tắc Agile, đặc biệt là phối hợp với khách hàng, phản hồi thay đổi và phần mềm hoạt động được.
- [The Scrum Guide (2020)](https://scrumguides.org/scrum-guide.html): Product Goal, Product Backlog, Increment, Definition of Done, Sprint Review và trách nhiệm Product Owner.
- [The Kanban Guide](https://kanbanguides.org/the-kanban-guide/): quản lý luồng công việc, giới hạn WIP và các phép đo dòng công việc.
- [Agile Alliance — Glossary](https://agilealliance.org/agile101/agile-glossary/): thuật ngữ liên quan đến user story, thực hành Agile và phát triển tăng dần.
